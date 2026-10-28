"""Alleger un PDF : on voit ce que fait chaque reglage, le poids obtenu et la qualite, avant de decider.

Rien n'est touche au document tant qu'on n'a pas choisi « Appliquer au document » ou « Enregistrer une copie ».
"""
import os

import pymupdf as fitz
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QCheckBox, QSpinBox, QComboBox,
                               QPushButton, QFileDialog, QGroupBox, QFormLayout, QMessageBox)

from .langue import _

PREREGLAGES = [  # nom, dpi max, qualite, seuil (on ne touche qu'aux images au-dessus)
    (_("Qualité écran (conseillé)"), 150, 75, 200),
    (_("Qualité impression"), 220, 85, 300),
    (_("Très léger (envoi par e-mail)"), 110, 60, 140),
]


def alleger(octets, reglages):
    """Copie allegee du PDF (octets) selon les reglages ; renvoie les octets."""
    d = fitz.open("pdf", octets)
    journal = reglages.setdefault("journal", [])
    from moteur import jbig2
    if reglages.get("noir_blanc"):                    # scans de texte en gris / couleur -> noir et blanc
        jbig2.en_noir_et_blanc(d, journal=journal)
    if reglages["images"]:
        # les images noir et blanc ne sont pas reduites (le texte deviendrait flou) : JBIG2 s'en charge
        try:
            d.rewrite_images(dpi_threshold=reglages["seuil"], dpi_target=reglages["dpi"], quality=reglages["qualite"],
                             set_to_gray=reglages["gris"], bitonal=False)
        except TypeError:                              # ancienne version de PyMuPDF
            d.rewrite_images(dpi_threshold=reglages["seuil"], dpi_target=reglages["dpi"], quality=reglages["qualite"])
    if reglages.get("jbig2", True):
        jbig2.recompresser(d, journal=journal)
    if reglages.get("polices_formulaire", True):
        from moteur import formulaire
        formulaire.alleger_polices(d, journal=journal)
    if reglages["polices"]:
        try:
            d.subset_fonts()
        except Exception:
            pass
    if reglages["infos"]:
        d.set_metadata({})
        try:
            d.del_xml_metadata()
        except Exception:
            pass
    return d.tobytes(garbage=4 if reglages["nettoyer"] else 1, deflate=True, deflate_images=True,
                     deflate_fonts=True, clean=reglages["nettoyer"])


class _Calcul(QThread):
    fini = Signal(object, str)

    def __init__(self, octets, reglages):
        super().__init__()
        self.octets, self.reglages = octets, reglages

    def run(self):
        try:
            self.fini.emit(alleger(self.octets, self.reglages), "")
        except Exception as e:
            self.fini.emit(None, str(e))


class DialogueAlleger(QDialog):
    def __init__(self, parent, onglet):
        super().__init__(parent)
        self.o = onglet
        self.setWindowTitle(_("Alléger le fichier"))
        self.setMinimumWidth(820)
        self.octets = onglet.doc.tobytes(garbage=1, deflate=True)
        self.resultat = None
        self.calcul = None
        v = QVBoxLayout(self)
        t = QLabel(_("Choisissez ce que PhilPDF a le droit de faire, puis regardez le poids obtenu et la qualité "
                     "(aperçu agrandi à droite). <b>Rien n'est modifié</b> tant que vous n'avez pas choisi « Appliquer » "
                     "ou « Enregistrer une copie »."))
        t.setWordWrap(True)
        v.addWidget(t)
        h = QHBoxLayout()
        g = QVBoxLayout()
        self.pre = QComboBox()
        for nom, *_r in PREREGLAGES:
            self.pre.addItem(nom)
        self.pre.addItem(_("Personnalisé"))
        self.pre.currentIndexChanged.connect(self._prereglage)
        f = QFormLayout()
        f.addRow(_("Réglage"), self.pre)
        g.addLayout(f)
        bi = QGroupBox(_("Images (là où l'on gagne le plus, avec perte de qualité)"))
        bi.setCheckable(True)
        bi.setChecked(True)
        self.b_images = bi
        fi = QFormLayout(bi)
        self.dpi = QSpinBox()
        self.dpi.setRange(50, 600)
        self.dpi.setSuffix(" dpi")
        self.seuil = QSpinBox()
        self.seuil.setRange(50, 1200)
        self.seuil.setSuffix(" dpi")
        self.qualite = QSpinBox()
        self.qualite.setRange(20, 100)
        self.qualite.setSuffix(" %")
        self.gris = QCheckBox(_("Passer les images en niveaux de gris"))
        fi.addRow(_("Ne retoucher que les images au-delà de"), self.seuil)
        fi.addRow(_("Les ramener à"), self.dpi)
        fi.addRow(_("Qualité JPEG"), self.qualite)
        fi.addRow(self.gris)
        g.addWidget(bi)
        bn = QGroupBox(_("Scans noir et blanc"))
        fn = QVBoxLayout(bn)
        self.jbig2 = QCheckBox(_("Compression JBIG2 sans perte des images noir et blanc (2 à 10 fois plus léger)"))
        self.jbig2.setObjectName("al_jbig2")
        self.jbig2.setToolTip(_("Chaque point est gardé : aucune lettre ni aucun chiffre ne peut changer (contrairement "
                                "au JBIG2 « avec perte » de certains scanners)."))
        self.jbig2.setChecked(True)
        fn.addWidget(self.jbig2)
        self.noir_blanc = QCheckBox(_("Passer en noir et blanc les scans de texte en gris ou en couleur "
                                      "(avec perte : les gris et couleurs disparaissent)"))
        self.noir_blanc.setObjectName("al_noir_blanc")
        self.noir_blanc.setToolTip(_("Seulement les pages qui ne sont que du texte foncé sur fond clair ; les photos "
                                     "et les fonds colorés ne sont pas touchés. Regardez l'aperçu."))
        fn.addWidget(self.noir_blanc)
        g.addWidget(bn)
        bs = QGroupBox(_("Sans perte (le document reste identique à l'œil)"))
        fs = QVBoxLayout(bs)
        self.polices = QCheckBox(_("Polices : ne garder que les lettres utilisées"))
        self.nettoyer = QCheckBox(_("Nettoyer le fichier (objets inutiles, compression maximale)"))
        self.infos = QCheckBox(_("Retirer les informations du fichier (auteur, logiciel, métadonnées)"))
        self.polices_form = QCheckBox(_("Polices des champs : garder les lettres du clavier (é, à, ç, €...) et "
                                        "retirer les autres alphabets"))
        self.polices_form.setObjectName("al_polices_form")
        fs.addWidget(self.polices_form)
        self.polices_form.setChecked(True)
        for c in (self.polices, self.nettoyer):
            c.setChecked(True)
            fs.addWidget(c)
        fs.addWidget(self.infos)
        g.addWidget(bs)
        self.poids = QLabel()
        self.poids.setWordWrap(True)
        self.poids.setStyleSheet("font-size:14px")
        g.addWidget(self.poids)
        g.addStretch(1)
        h.addLayout(g, 1)
        ap = QVBoxLayout()
        ap.addWidget(QLabel(_("<b>Aperçu agrandi</b> (même endroit de la page 1)")))
        gl = QGridLayout()
        self.av = QLabel()
        self.ap = QLabel()
        for i, (lbl, w) in enumerate(((_("Avant"), self.av), (_("Après"), self.ap))):
            gl.addWidget(QLabel(lbl), 0, i)
            w.setFixedSize(220, 300)
            w.setStyleSheet("background:#fff;border:1px solid #ccc")
            w.setAlignment(Qt.AlignCenter)
            gl.addWidget(w, 1, i)
        ap.addLayout(gl)
        ap.addStretch(1)
        h.addLayout(ap)
        v.addLayout(h)
        hb = QHBoxLayout()
        self.b_calc = QPushButton(_("Calculer le poids et l'aperçu"))
        self.b_calc.clicked.connect(self.calculer)
        hb.addWidget(self.b_calc)
        hb.addStretch(1)
        self.b_copie = QPushButton(_("Enregistrer une copie allégée..."))
        self.b_copie.clicked.connect(self.enregistrer_copie)
        hb.addWidget(self.b_copie)
        self.b_appli = QPushButton(_("Appliquer au document"))
        self.b_appli.setToolTip(_("Le document ouvert est allégé ; enregistrez-le ensuite (Ctrl+S) ou annulez (Ctrl+Z)."))
        self.b_appli.clicked.connect(self.appliquer)
        hb.addWidget(self.b_appli)
        b = QPushButton(_("Fermer"))
        b.clicked.connect(self.reject)
        hb.addWidget(b)
        v.addLayout(hb)
        for w in (self.dpi, self.seuil, self.qualite):
            w.valueChanged.connect(self._modifie)
        for w in (self.gris, self.polices, self.nettoyer, self.infos, self.jbig2, self.noir_blanc, self.polices_form):
            w.toggled.connect(self._modifie)
        bi.toggled.connect(self._modifie)
        self._prereglage(0)
        self.av.setPixmap(self._apercu(self.octets))
        self.calculer()

    def reglages(self):
        return {"images": self.b_images.isChecked(), "dpi": self.dpi.value(), "seuil": max(self.seuil.value(), self.dpi.value()),
                "qualite": self.qualite.value(), "gris": self.gris.isChecked(), "polices": self.polices.isChecked(),
                "nettoyer": self.nettoyer.isChecked(), "infos": self.infos.isChecked(), "jbig2": self.jbig2.isChecked(),
                "noir_blanc": self.noir_blanc.isChecked(), "polices_formulaire": self.polices_form.isChecked()}

    def _prereglage(self, i):
        if i >= len(PREREGLAGES):
            return
        _n, dpi, q, seuil = PREREGLAGES[i]
        for w, val in ((self.dpi, dpi), (self.qualite, q), (self.seuil, seuil)):
            w.blockSignals(True)
            w.setValue(val)
            w.blockSignals(False)
        self._modifie(garder_prereglage=True)

    def _modifie(self, *_a, garder_prereglage=False):
        if not garder_prereglage and self.pre.currentIndex() < len(PREREGLAGES):
            self.pre.blockSignals(True)
            self.pre.setCurrentIndex(len(PREREGLAGES))
            self.pre.blockSignals(False)
        self.resultat = None
        self.poids.setText(_("Réglages changés : cliquez sur « Calculer » pour voir le poids et la qualité."))

    def _apercu(self, octets):
        """Zoom x2 sur le haut gauche de la page 1 : on y voit la perte de qualite."""
        d = fitz.open("pdf", octets)
        p = d[0]
        r = p.rect
        zone = fitz.Rect(r.x0 + r.width * 0.08, r.y0 + r.height * 0.06, r.x0 + r.width * 0.38, r.y0 + r.height * 0.46)
        k = 300 / zone.height
        pm = p.get_pixmap(matrix=fitz.Matrix(k, k), clip=zone, alpha=False)
        return QPixmap.fromImage(QImage(pm.samples, pm.width, pm.height, pm.stride, QImage.Format_RGB888).copy()) \
            .scaled(220, 300, Qt.KeepAspectRatio, Qt.SmoothTransformation)

    def calculer(self):
        if self.calcul and self.calcul.isRunning():
            return
        self.poids.setText(_("Calcul en cours..."))
        self.b_calc.setEnabled(False)
        self._regl = self.reglages()
        self.calcul = _Calcul(self.octets, self._regl)

        def fini(res, err):
            self.b_calc.setEnabled(True)
            if err:
                self.poids.setText(_("Impossible d'alléger : {e}", e=err))
                return
            self.resultat = res
            avant, apres = len(self.octets), len(res)
            gain = 100 - apres * 100 // max(1, avant)
            self.poids.setText(_("<b>{a} Ko → {b} Ko</b> ({g} % de moins)", a=avant // 1024, b=apres // 1024, g=gain) +
                               ("" if gain > 3 else "<br>" + _("Peu de gain : ce document est déjà léger.")) +
                               "".join("<br><span style='color:#555;font-size:12px'>· " + l + "</span>"
                                       for l in self._regl.get("journal", [])[:6]))
            self.ap.setPixmap(self._apercu(res))
        self.calcul.fini.connect(fini)
        self.calcul.start()

    def _attendre(self):
        if self.resultat is None:
            self.calculer()
            if self.calcul:
                self.calcul.wait()
                from PySide6.QtWidgets import QApplication
                QApplication.processEvents()
        return self.resultat

    def enregistrer_copie(self):
        res = self._attendre()
        if not res:
            return
        base = os.path.splitext(self.o.chemin or self.o.nom)[0]
        p, _f = QFileDialog.getSaveFileName(self, _("Enregistrer une copie allégée"), base + "_allege.pdf", "PDF (*.pdf)")
        if not p:
            return
        with open(p, "wb") as f:
            f.write(res)
        QMessageBox.information(self, _("Alléger le fichier"), _("Copie allégée enregistrée ({k} Ko) :\n{p}\n\n"
                                                                 "Le document d'origine n'a pas été modifié.", k=len(res) // 1024, p=p))
        self.accept()

    def appliquer(self):
        if self.o.est_signe() and QMessageBox.question(
                self, _("Alléger le fichier"),
                _("Ce document est signé. L'alléger réécrit tout le fichier : les signatures ne seront plus valides. "
                  "Utilisez plutôt « Enregistrer une copie allégée ».\n\nAlléger quand même ?")) != QMessageBox.Yes:
            return
        res = self._attendre()
        if not res:
            return
        self.o.memoriser(_("Allègement du fichier"))
        self.o.remplacer_document(res)
        self.accept()
