"""Creer un PDF : page vierge, images, fichier Office (Word, Excel, PowerPoint, LibreOffice), presse-papiers,
capture d'ecran ; et les reglages de l'imprimante PhilPDF (comme l'onglet « Parametres Adobe PDF »)."""
import datetime
import os

import pymupdf as fitz
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QPushButton, QComboBox,
                               QCheckBox, QLineEdit, QFileDialog, QMessageBox, QApplication, QDialogButtonBox,
                               QGroupBox)

from .langue import _
from .icones import icone


class DialogueCreer(QDialog):
    """Un bouton par source ; resultat = (genre, donnee)."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle(_("Créer un PDF"))
        self.setMinimumWidth(520)
        v = QVBoxLayout(self)
        self.resultat = None
        for genre, ic, titre, aide in (
                ("vierge", "creer", _("Page vierge"), _("Une page A4 blanche")),
                ("images", "image", _("Depuis des images"), _("JPG, PNG, TIFF... une page par image")),
                ("office", "exporter", _("Depuis un fichier Word, Excel ou PowerPoint"),
                 _("Converti par Office (ou LibreOffice), polices intégrées : le document exact")),
                ("presse_papiers", "copier", _("Depuis le presse-papiers"), _("L'image ou le texte copié")),
                ("capture", "numeriser", _("Capture d'écran"), _("Tout l'écran ; recadrez ensuite si besoin")),
                ("imprimante", "imprimer", _("Imprimante PhilPDF..."),
                 _("Imprimer vers PhilPDF depuis n'importe quel logiciel (comme Adobe PDF)"))):
            b = QPushButton(icone(ic, "#c9252d"), "  " + titre)
            b.setObjectName("creer_" + genre)
            b.setToolTip(aide)
            b.setStyleSheet("QPushButton{text-align:left;padding:10px 14px;font-size:14px}")
            b.clicked.connect(lambda _c=False, g=genre: self._choisir(g))
            v.addWidget(b)
            l = QLabel(aide)
            l.setStyleSheet("color:#666;margin-left:40px;margin-bottom:4px")
            v.addWidget(l)
        bb = QDialogButtonBox(QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Cancel).setText(_("Annuler"))
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def _choisir(self, g):
        self.resultat = g
        self.accept()


def doc_presse_papiers():
    """PDF fait de l'image (ou du texte) du presse-papiers ; None s'il est vide."""
    cb = QApplication.clipboard()
    img = cb.image()
    if not img.isNull():
        from PySide6.QtCore import QBuffer, QIODevice
        buf = QBuffer()
        buf.open(QIODevice.WriteOnly)
        img.save(buf, "PNG")
        im = fitz.open("png", bytes(buf.data()))
        return fitz.open("pdf", im.convert_to_pdf())
    t = cb.text()
    if t.strip():                                    # texte : 55 lignes par page
        d = fitz.open()
        lignes = []
        for l in t.splitlines():
            while len(l) > 95:
                coupe = l.rfind(" ", 0, 95)
                coupe = coupe if coupe > 40 else 95
                lignes.append(l[:coupe])
                l = l[coupe:].lstrip()
            lignes.append(l)
        for i in range(0, len(lignes), 55):
            p = d.new_page()
            p.insert_textbox(fitz.Rect(56, 56, p.rect.width - 56, p.rect.height - 56),
                             "\n".join(lignes[i:i + 55]), fontsize=10.5, fontname="helv")
        return d
    return None


def capture_ecran(fenetre, rappel):
    """Cache PhilPDF, capture l'ecran ou se trouve la fenetre, puis appelle rappel(doc)."""
    ecran = fenetre.screen() or QApplication.primaryScreen()
    fenetre.showMinimized()

    def prendre():
        pm = ecran.grabWindow(0)
        fenetre.showNormal()
        fenetre.raise_()
        fenetre.activateWindow()
        from PySide6.QtCore import QBuffer, QIODevice
        buf = QBuffer()
        buf.open(QIODevice.WriteOnly)
        pm.save(buf, "PNG")
        im = fitz.open("png", bytes(buf.data()))
        rappel(fitz.open("pdf", im.convert_to_pdf()))
    QTimer.singleShot(700, prendre)


QUALITES = [("standard", _("Standard (équilibré, comme Adobe « Standard »)")),
            ("haute", _("Qualité supérieure (images intactes, pour imprimer)")),
            ("leger", _("Taille minimale (envoi par e-mail)")),
            ("pdfa", _("Archivage PDF/A"))]


class DialogueImprimante(QDialog):
    """Installer l'imprimante PhilPDF et la regler (qualite, sortie, affichage), comme l'imprimante Adobe PDF."""

    def __init__(self, parent, params):
        super().__init__(parent)
        from . import imprimante as I
        self.I, self.params = I, params
        self.setWindowTitle(_("Imprimante PhilPDF"))
        self.setMinimumWidth(620)
        v = QVBoxLayout(self)
        t = QLabel(_("Depuis Word, Excel, un navigateur ou tout autre logiciel : Imprimer › <b>PhilPDF</b>. "
                     "Le PDF obtenu s'ouvre dans PhilPDF. Les polices sont toujours intégrées au PDF : le document "
                     "est exactement celui que vous voyez à l'écran."))
        t.setWordWrap(True)
        v.addWidget(t)
        self.etat = QLabel()
        self.etat.setWordWrap(True)
        v.addWidget(self.etat)
        h = QHBoxLayout()
        self.b_inst = QPushButton(_("Installer l'imprimante PhilPDF"))
        self.b_inst.setProperty("primaire", True)
        self.b_inst.clicked.connect(self.installer)
        h.addWidget(self.b_inst)
        self.b_desinst = QPushButton(_("La retirer"))
        self.b_desinst.clicked.connect(self.desinstaller)
        h.addWidget(self.b_desinst)
        h.addStretch(1)
        v.addLayout(h)
        g = QGroupBox(_("Paramètres de conversion"))
        f = QFormLayout(g)
        r = params.get("imprimante") or {}
        self.qualite = QComboBox()
        for k, lib in QUALITES:
            self.qualite.addItem(lib, k)
        self.qualite.setCurrentIndex(max(0, self.qualite.findData(r.get("qualite", "standard"))))
        f.addRow(_("Paramètres par défaut"), self.qualite)
        self.sortie = QComboBox()
        self.sortie.addItem(_("Ouvrir dans PhilPDF, je choisis le nom en enregistrant"), "ouvrir")
        self.sortie.addItem(_("Enregistrer tout seul dans un dossier"), "dossier")
        self.sortie.setCurrentIndex(max(0, self.sortie.findData(r.get("sortie", "ouvrir"))))
        f.addRow(_("Sortie"), self.sortie)
        hd = QHBoxLayout()
        self.dossier = QLineEdit(r.get("dossier") or os.path.join(os.path.expanduser("~"), "Documents"))
        b = QPushButton(_("Parcourir..."))
        b.clicked.connect(self._parcourir)
        hd.addWidget(self.dossier, 1)
        hd.addWidget(b)
        self.l_dossier = QLabel(_("Dossier"))
        f.addRow(self.l_dossier, hd)
        self.afficher = QCheckBox(_("Afficher le PDF obtenu"))
        self.afficher.setChecked(r.get("afficher", True))
        f.addRow("", self.afficher)
        self.infos = QCheckBox(_("Ajouter des informations sur le document (auteur, logiciel)"))
        self.infos.setChecked(r.get("infos", True))
        f.addRow("", self.infos)
        self.remplacer = QCheckBox(_("Remplacer un PDF du même nom (sinon : « (2) », « (3) »...)"))
        self.remplacer.setChecked(r.get("remplacer", False))
        f.addRow("", self.remplacer)
        v.addWidget(g)
        note = QLabel(_("Format de page, orientation et marges : dans la fenêtre d'impression de votre logiciel, comme "
                        "pour une imprimante papier."))
        note.setWordWrap(True)
        note.setStyleSheet("color:#666")
        v.addWidget(note)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText(_("OK"))
        bb.button(QDialogButtonBox.Cancel).setText(_("Annuler"))
        bb.accepted.connect(self.valider)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        self.sortie.currentIndexChanged.connect(self._maj)
        self._maj()

    def _parcourir(self):
        d = QFileDialog.getExistingDirectory(self, _("Dossier des PDF imprimés"), self.dossier.text())
        if d:
            self.dossier.setText(d)

    def _maj(self, *_a):
        dos = self.sortie.currentData() == "dossier"
        for w in (self.dossier, self.l_dossier):
            w.setEnabled(dos)
        import sys
        if sys.platform != "win32":
            self.etat.setText(_("Disponible sous Windows ; sous Linux, ce sera l'imprimante CUPS-PDF."))
            self.b_inst.setEnabled(False)
            self.b_desinst.setEnabled(False)
            return
        ok = self.I.installee()
        self.etat.setText(("<span style='color:#1e6b34'>✓ " + _("L'imprimante PhilPDF est installée.") + "</span>")
                          if ok else _("L'imprimante n'est pas encore installée. Windows demandera une fois "
                                       "l'autorisation (droits d'administrateur)."))
        self.b_inst.setVisible(not ok)
        self.b_desinst.setVisible(ok)

    def installer(self):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            ok, msg = self.I.installer()
        finally:
            QApplication.restoreOverrideCursor()
        if ok:
            self.params["imprimante_installee"] = True
            self.params.enregistrer()
            QMessageBox.information(self, self.windowTitle(), _("Imprimante PhilPDF installée. Essayez : Imprimer › "
                                                                 "PhilPDF depuis Word ou votre navigateur."))
        else:
            QMessageBox.warning(self, self.windowTitle(), _("Installation impossible : {e}", e=msg))
        self._maj()

    def desinstaller(self):
        if QMessageBox.question(self, self.windowTitle(), _("Retirer l'imprimante PhilPDF ?")) != QMessageBox.Yes:
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.I.desinstaller()
        finally:
            QApplication.restoreOverrideCursor()
        self.params["imprimante_installee"] = False
        self.params.enregistrer()
        self._maj()

    def valider(self):
        self.params["imprimante"] = {"qualite": self.qualite.currentData(), "sortie": self.sortie.currentData(),
                                     "dossier": self.dossier.text().strip(), "afficher": self.afficher.isChecked(),
                                     "infos": self.infos.isChecked(), "remplacer": self.remplacer.isChecked()}
        self.params.enregistrer()
        self.accept()


def nom_impression(chemin):
    """« Impression 2026-10-29 01-02-03.pdf » -> « Impression du 29-10-2026 01-02.pdf »."""
    b = os.path.basename(chemin)
    try:
        d = datetime.datetime.strptime(b[len("Impression "):-4], "%Y-%m-%d %H-%M-%S")
        return _("Impression du {d}", d=d.strftime("%d-%m-%Y %Hh%M")) + ".pdf"
    except ValueError:
        return b
