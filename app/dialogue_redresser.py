"""Redresser une page (Pages > Redresser la page, clic droit sur la page) ou une image en mode Modifier : apercu
tourne en direct sur une grille, angle au dixieme de degre, « Auto » (inclinaison mesuree sur le texte), 0°.
La page garde son texte, ses couleurs et sa qualite (son contenu est tourne). Rien ne change avant « Appliquer »."""
import cv2
import numpy as np
import pymupdf as fitz
from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QImage, QPixmap, QPainter, QPen, QColor
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QSlider, QDoubleSpinBox, QPushButton,
                               QDialogButtonBox, QRadioButton, QButtonGroup)

from .langue import _
from moteur import nettoyage as N


class DialogueRedresser(QDialog):
    """gris : image en niveaux de gris a redresser (page rendue ou image). plusieurs : proposer « toutes les pages »."""

    def __init__(self, parent, titre, gris, plusieurs=False, verticales=True):
        super().__init__(parent)
        self.setWindowTitle(titre)
        ecran = self.screen().availableGeometry()
        self.resize(min(780, ecran.width() - 40), min(940, ecran.height() - 60))
        e = min(1.0, 1100 / max(gris.shape[:2]))
        self.gris = cv2.resize(gris, None, fx=e, fy=e, interpolation=cv2.INTER_AREA) if e < 1 else np.ascontiguousarray(gris)
        v = QVBoxLayout(self)
        aide = QLabel(_("Réglez les angles pour que le texte suive la grille : « Lignes » tourne la page (lignes "
                        "horizontales), « Verticales » redresse les bords et les colonnes qui penchent (feuille "
                        "photographiée de biais). « Auto » mesure les deux. Rien n'est changé avant « Appliquer » ; "
                        "Ctrl+Z revient en arrière."))
        aide.setWordWrap(True)
        v.addWidget(aide)
        self.vue = QLabel()
        self.vue.setAlignment(Qt.AlignCenter)
        self.vue.setMinimumSize(300, 360)
        self.vue.setStyleSheet("background:#ffffff;border:1px solid #ddd")
        v.addWidget(self.vue, 1)
        self.trouve = N.angle(self.gris)
        self.trouve_v = N.angle_vertical(self.gris, self.trouve) if verticales else 0.0
        self._t = QTimer(self, singleShot=True, interval=60, timeout=self._apercu)
        self.angle = self._reglage(v, _("Lignes (horizontales)"), _("Tourne la page : les lignes du texte deviennent horizontales."))
        self.vertical = self._reglage(v, _("Verticales"), _("Redresse ce qui penche de haut en bas (bords de la feuille, "
                                                              "colonnes, tableaux) ; les lignes restent horizontales.")) if verticales else None
        hb = QHBoxLayout()
        b_auto = QPushButton(_("Auto (lignes {a} °, verticales {v} °)", a=f"{self.trouve:+.1f}".replace(".", ","),
                               v=f"{self.trouve_v:+.1f}".replace(".", ",")) if verticales else
                             _("Auto ({a} °)", a=f"{self.trouve:+.1f}".replace(".", ",")))
        b_auto.setToolTip(_("Inclinaison mesurée sur les lignes du texte"))
        b_auto.clicked.connect(self.auto)
        hb.addWidget(b_auto)
        b0 = QPushButton("0 °")
        b0.clicked.connect(lambda: (self.angle.setValue(0), self.vertical and self.vertical.setValue(0)))
        hb.addWidget(b0)
        hb.addStretch()
        v.addLayout(hb)
        self.portee = None
        if plusieurs:
            hp = QHBoxLayout()
            self.portee = QButtonGroup(self)
            for k, t in enumerate((_("Cette page"), _("Toutes les pages"))):
                r = QRadioButton(t)
                r.setChecked(k == 0)
                self.portee.addButton(r, k)
                hp.addWidget(r)
            hp.addStretch()
            v.addLayout(hp)
        bb = QDialogButtonBox()
        bb.addButton(_("Appliquer"), QDialogButtonBox.AcceptRole)
        bb.addButton(_("Annuler"), QDialogButtonBox.RejectRole)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        self.auto()                                       # proposee d'office : on la voit, on la corrige
        self._apercu()

    def _reglage(self, v, nom, aide):
        """Une ligne : nom, angle au dixieme, curseur, -1 / -0,1 / +0,1 / +1."""
        h = QHBoxLayout()
        lb = QLabel(nom)
        lb.setMinimumWidth(80)
        lb.setToolTip(aide)
        h.addWidget(lb)
        sp = QDoubleSpinBox()
        sp.setRange(-15, 15)
        sp.setSingleStep(0.1)
        sp.setDecimals(1)
        sp.setSuffix(" °")
        sp.setToolTip(aide)
        cur = QSlider(Qt.Horizontal)
        cur.setRange(-150, 150)
        h.addWidget(sp)
        h.addWidget(cur, 1)
        for d in (-1.0, -0.1, 0.1, 1.0):
            b = QPushButton(f"{d:+.1f}".replace(".", ","))
            b.setMaximumWidth(48)
            b.clicked.connect(lambda _c=False, d=d: sp.setValue(sp.value() + d))
            h.addWidget(b)
        sp.valueChanged.connect(lambda x: (cur.blockSignals(True), cur.setValue(round(x * 10)), cur.blockSignals(False),
                                           self._t.start()))
        cur.valueChanged.connect(lambda x: sp.setValue(x / 10))
        v.addLayout(h)
        return sp

    def auto(self):
        self.angle.setValue(self.trouve)
        if self.vertical is not None:
            self.vertical.setValue(self.trouve_v)

    def valeurs(self):
        """(angle des lignes, inclinaison des verticales), degres."""
        return self.angle.value(), (self.vertical.value() if self.vertical is not None else 0.0)

    def toutes(self):
        return bool(self.portee) and self.portee.checkedId() == 1

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._t.start()

    def _apercu(self):
        a, vv = self.valeurs()
        img = np.ascontiguousarray(N.transformer(self.gris, a, vv))
        h, w = img.shape
        pm = QPixmap.fromImage(QImage(img.data, w, h, w, QImage.Format_Grayscale8).copy())
        pm = pm.scaled(self.vue.size() - QSize(8, 8), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        p = QPainter(pm)
        p.setPen(QPen(QColor(26, 115, 232, 110), 1))
        for y in range(18, pm.height(), 18):
            p.drawLine(0, y, pm.width(), y)
        p.setPen(QPen(QColor(26, 115, 232, 80), 1))
        for x in range(36, pm.width(), 36):
            p.drawLine(x, 0, x, pm.height())
        p.end()
        self.vue.setPixmap(pm)


def gris_page(page, dpi=110):
    pm = page.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY, alpha=False)
    return np.frombuffer(pm.samples, np.uint8).reshape(pm.height, pm.width).copy()


def redresser_page(fenetre, onglet, n=None):
    """Pages > Redresser la page : la page en cours (ou toutes)."""
    from PySide6.QtWidgets import QDialog as _D
    n = onglet.page_courante() if n is None else n
    d = DialogueRedresser(fenetre, _("Redresser la page {n}", n=n + 1), gris_page(onglet.doc[n]), plusieurs=len(onglet.doc) > 1)
    a, vv = d.valeurs() if d.exec() == _D.Accepted else (0, 0)
    if abs(a) < 0.05 and abs(vv) < 0.05:
        return
    pages = list(range(len(onglet.doc))) if d.toutes() else [n]
    onglet.memoriser(_("Redresser la page"))
    N.redresser_pages(onglet.doc, pages, a, vv)
    onglet.apres_modif([_("{n} page(s) redressée(s) : lignes {a} °, verticales {v} °.", n=len(pages),
                          a=f"{a:+.1f}".replace(".", ","), v=f"{vv:+.1f}".replace(".", ","))], reconstruire=True)


def redresser_image(onglet):
    """Modifier > clic droit sur une image > Redresser l'image : l'image tourne sur la page de l'angle choisi."""
    from PySide6.QtWidgets import QDialog as _D
    obj = onglet.objet
    if not obj or obj.get("type") != "image":
        return
    # l'image telle qu'on la voit sur la page (sa rotation ou son miroir eventuels compris)
    pm = onglet.doc[obj["page"]].get_pixmap(clip=obj["rect"], dpi=150, colorspace=fitz.csGRAY, alpha=False)
    gris = np.frombuffer(pm.samples, np.uint8).reshape(pm.height, pm.width).copy()
    d = DialogueRedresser(onglet.window(), _("Redresser l'image"), gris, verticales=False)
    if d.exec() == _D.Accepted and abs(d.angle.value()) >= 0.05:
        onglet.tourner_objet(d.angle.value())
