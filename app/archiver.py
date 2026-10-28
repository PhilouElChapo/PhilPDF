"""Archiver (PDF/A) : PhilPDF montre ce qu'il va changer et le resultat de la verification avant d'enregistrer."""
import os

import pymupdf as fitz
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QListWidget, QListWidgetItem,
                               QFileDialog, QMessageBox, QApplication)

from moteur import pdfa
from .langue import _


class DialogueArchiver(QDialog):
    def __init__(self, parent, onglet):
        super().__init__(parent)
        self.o = onglet
        self.setWindowTitle(_("Archiver (PDF/A)"))
        self.resize(720, 560)
        v = QVBoxLayout(self)
        t = QLabel(_("Le PDF/A est le format d'archivage demandé par les administrations : le document s'affichera "
                     "à l'identique dans 30 ans, sur n'importe quel ordinateur. PhilPDF prépare une version PDF/A-2b "
                     "et la vérifie. <b>Votre document n'est pas modifié</b> tant que vous n'avez pas choisi."))
        t.setWordWrap(True)
        v.addWidget(t)
        v.addWidget(QLabel("<b>" + _("Ce qui va changer") + "</b>"))
        self.changes = QListWidget()
        self.changes.setObjectName("pdfa_changes")
        v.addWidget(self.changes, 1)
        v.addWidget(QLabel("<b>" + _("Vérification du résultat") + "</b>"))
        self.verif = QListWidget()
        self.verif.setObjectName("pdfa_verif")
        v.addWidget(self.verif, 1)
        self.bilan = QLabel()
        self.bilan.setWordWrap(True)
        v.addWidget(self.bilan)
        h = QHBoxLayout()
        h.addStretch(1)
        self.b_copie = QPushButton(_("Enregistrer une copie PDF/A..."))
        self.b_copie.setProperty("primaire", True)
        self.b_copie.clicked.connect(self.enregistrer_copie)
        h.addWidget(self.b_copie)
        self.b_appli = QPushButton(_("Appliquer au document"))
        self.b_appli.setToolTip(_("Le document ouvert devient PDF/A ; enregistrez-le ensuite (Ctrl+S) ou annulez (Ctrl+Z)."))
        self.b_appli.clicked.connect(self.appliquer)
        h.addWidget(self.b_appli)
        b = QPushButton(_("Fermer"))
        b.clicked.connect(self.reject)
        h.addWidget(b)
        v.addLayout(h)
        self.resultat = None
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.preparer()
        finally:
            QApplication.restoreOverrideCursor()

    def preparer(self):
        d = fitz.open("pdf", self.o.doc.tobytes())
        try:
            journal = pdfa.convertir(d)
        except Exception as e:
            self.bilan.setText("<span style='color:#c9252d'>" + _("Conversion impossible : {e}", e=e) + "</span>")
            self.b_copie.setEnabled(False)
            self.b_appli.setEnabled(False)
            return
        self.resultat = pdfa.octets(d)
        for l in journal or [_("Rien à changer : le document était presque prêt.")]:
            self.changes.addItem("•  " + l)
        d2 = fitz.open("pdf", self.resultat)
        res = pdfa.verifier(d2)
        for regle, ok, detail in res:
            it = QListWidgetItem(("✓  " if ok else "✕  ") + regle + (f" — {detail}" if detail else ""))
            it.setForeground(Qt.darkGreen if ok else Qt.red)
            self.verif.addItem(it)
        tout = all(ok for _r, ok, _d in res)
        avant, apres = len(self.o.doc.tobytes()) // 1024, len(self.resultat) // 1024
        self.bilan.setText((_("<b>Prêt : PDF/A-2b conforme aux vérifications de PhilPDF.</b>") if tout else
                            _("<b>Presque prêt</b> : les points en rouge restent (voir le détail).")) + " " +
                           _("Poids : {a} Ko → {b} Ko (les polices sont maintenant dans le fichier).", a=avant, b=apres)
                           + "<br><span style='color:#666'>" +
                           _("Pour un contrôle officiel, le validateur gratuit veraPDF fait référence.") + "</span>")

    def _signe_ok(self):
        if self.o.est_signe():
            return QMessageBox.question(self, self.windowTitle(),
                                        _("Ce document est signé : le passer en PDF/A réécrit tout le fichier et les "
                                          "signatures ne seront plus valides. Continuer ?")) == QMessageBox.Yes
        return True

    def enregistrer_copie(self):
        if not self.resultat or not self._signe_ok():
            return
        base = os.path.splitext(self.o.chemin or self.o.nom)[0]
        p, _f = QFileDialog.getSaveFileName(self, _("Enregistrer une copie PDF/A"), base + " (PDF-A).pdf", "PDF (*.pdf)")
        if not p:
            return
        with open(p, "wb") as f:
            f.write(self.resultat)
        self.chemin_copie = p
        QMessageBox.information(self, self.windowTitle(), _("Copie PDF/A enregistrée :\n{p}\n\nLe document d'origine "
                                                            "n'a pas été modifié.", p=p))
        self.accept()

    def appliquer(self):
        if not self.resultat or not self._signe_ok():
            return
        self.o.memoriser(_("Archivage PDF/A"))
        self.o.remplacer_document(self.resultat)
        self.accept()
