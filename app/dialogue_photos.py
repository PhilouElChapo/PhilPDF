"""Numeriser depuis des photos (comme PhilPDF Android) : photos de documents prises au telephone ou a l'appareil,
bords de la feuille reperes (quatre coins ajustables), page redressee, modele au choix, PDF cree puis texte reconnu."""
import datetime
import os

import cv2
import numpy as np
from PySide6.QtCore import Qt, QPointF, QSize, QTimer
from PySide6.QtGui import QImage, QPixmap, QPen, QBrush, QColor, QPolygonF, QIcon, QPainter
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem, QPushButton, QLabel,
                               QGraphicsView, QGraphicsScene, QGraphicsEllipseItem, QGraphicsPolygonItem, QRadioButton,
                               QButtonGroup, QCheckBox, QDialogButtonBox, QFileDialog, QMessageBox, QSplitter, QWidget,
                               QGraphicsItem, QApplication)

from .langue import _
from moteur import photo_doc as P

MODELES = [("nb", _("Noir et blanc"), _("Texte net sur fond blanc, fichier très léger : courriers, factures, formulaires.")),
           ("couleur", _("Couleur"), _("Couleurs gardées, fond éclairci et ombres retirées : documents en couleur, cartes.")),
           ("email", _("Pour e-mail"), _("Comme Couleur, mais allégé au maximum pour l'envoyer par e-mail.")),
           ("photo", _("Photo"), _("Aucune retouche, seulement recadré et redressé : tickets, photos, pièces d'identité."))]


def qimage(img):
    """Image OpenCV (BGR ou gris) -> QImage (copie)."""
    if img.ndim == 2:
        h, w = img.shape
        return QImage(img.data, w, h, w, QImage.Format_Grayscale8).copy()
    h, w = img.shape[:2]
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    return QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888).copy()


class _Poignee(QGraphicsEllipseItem):
    def __init__(self, vue, k):
        super().__init__(-9, -9, 18, 18)
        self.vue, self.k = vue, k
        self.setBrush(QBrush(QColor("#ffffff")))
        self.setPen(QPen(QColor("#1a73e8"), 3))
        self.setFlag(QGraphicsItem.ItemIsMovable)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges)
        self.setFlag(QGraphicsItem.ItemIgnoresTransformations)
        self.setCursor(Qt.OpenHandCursor)          # objet a deplacer : une main (regle des curseurs)
        self.setZValue(3)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange and self.vue.taille is not None:
            w, h = self.vue.taille
            return QPointF(min(max(value.x(), 0), w), min(max(value.y(), 0), h))
        if change == QGraphicsItem.ItemPositionHasChanged:
            self.vue.bouge(self.k, self.pos())
        return super().itemChange(change, value)


class VueCadrage(QGraphicsView):
    """La photo et ses quatre coins a faire glisser."""

    def __init__(self, change):
        super().__init__()
        self.change = change
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setScene(QGraphicsScene(self))
        self.setBackgroundBrush(QBrush(QColor("#2b2b2b")))
        self.taille = None
        self.poignees = []
        self.poly = None
        self._calme = False

    def montrer(self, img, coins):
        s = self.scene()
        s.clear()
        self.poignees = []
        if img is None:
            self.taille = None
            return
        h, w = img.shape[:2]
        self.taille = (w, h)
        s.addPixmap(QPixmap.fromImage(qimage(img)))
        s.setSceneRect(0, 0, w, h)
        self.poly = QGraphicsPolygonItem()
        self.poly.setPen(QPen(QColor("#1a73e8"), 3 * max(w, h) / 900))
        self.poly.setBrush(QBrush(QColor(26, 115, 232, 45)))
        self.poly.setZValue(2)
        s.addItem(self.poly)
        self._calme = True
        for k in range(4):
            p = _Poignee(self, k)
            s.addItem(p)
            self.poignees.append(p)
            p.setPos(QPointF(*coins[k]))
        self._calme = False
        self._poly()
        self.fitInView(s.sceneRect(), Qt.KeepAspectRatio)

    def _poly(self):
        if self.poly is not None and len(self.poignees) == 4:
            self.poly.setPolygon(QPolygonF([p.pos() for p in self.poignees]))

    def bouge(self, _k, _pos):
        self._poly()
        if not self._calme and len(self.poignees) == 4:
            self.change([(p.pos().x(), p.pos().y()) for p in self.poignees])

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.taille:
            self.fitInView(self.scene().sceneRect(), Qt.KeepAspectRatio)


class DialogueScanPhotos(QDialog):
    """Resultat : self.doc (pymupdf) et self.ocr (reconnaitre le texte ensuite)."""

    def __init__(self, parent, params, fichiers=None):
        super().__init__(parent)
        self.params = params
        self.setWindowTitle(_("Numériser depuis des photos"))
        ecran = (parent.screen() if parent else QApplication.primaryScreen()).availableGeometry()
        self.resize(min(1000, ecran.width() - 40), min(700, ecran.height() - 60))
        self.pages = []                                  # dict(img, coins)
        self.doc = None
        v = QVBoxLayout(self)
        aide = QLabel(_("Ajoutez les photos du document (prises au téléphone ou à l'appareil photo), une par page. "
                        "Les bords de la feuille sont repérés seuls : faites glisser les coins pour corriger."))
        aide.setWordWrap(True)
        v.addWidget(aide)
        sp = QSplitter(Qt.Horizontal)
        gauche = QWidget()
        vg = QVBoxLayout(gauche)
        vg.setContentsMargins(0, 0, 0, 0)
        self.liste = QListWidget()
        self.liste.setIconSize(QSize(90, 120))
        self.liste.setDragDropMode(QListWidget.InternalMove)
        self.liste.currentRowChanged.connect(self._choisir)
        self.liste.model().rowsMoved.connect(self._reordonner)
        vg.addWidget(self.liste, 1)
        for texte, f in ((_("Ajouter des photos..."), self.ajouter), (_("Tourner d'un quart de tour"), self.tourner),
                         (_("Retirer la page"), self.retirer)):
            b = QPushButton(texte)
            b.clicked.connect(f)
            vg.addWidget(b)
        sp.addWidget(gauche)
        milieu = QWidget()
        vm = QVBoxLayout(milieu)
        vm.setContentsMargins(0, 0, 0, 0)
        self.vue = VueCadrage(self._coins_changes)
        vm.addWidget(self.vue, 1)
        hc = QHBoxLayout()
        b = QPushButton(_("Coins automatiques"))
        b.clicked.connect(lambda: self._coins(auto=True))
        hc.addWidget(b)
        b = QPushButton(_("Toute la photo"))
        b.clicked.connect(lambda: self._coins(auto=False))
        hc.addWidget(b)
        hc.addStretch()
        vm.addLayout(hc)
        sp.addWidget(milieu)
        droite = QWidget()
        vd = QVBoxLayout(droite)
        vd.setContentsMargins(0, 0, 0, 0)
        vd.addWidget(QLabel("<b>" + _("RESULTAT") + "</b>"))
        self.apercu = QLabel()
        self.apercu.setAlignment(Qt.AlignCenter)
        self.apercu.setMinimumSize(200, 260)
        self.apercu.setStyleSheet("background:#ffffff;border:1px solid #ddd")
        vd.addWidget(self.apercu, 1)
        self.groupe = QButtonGroup(self)
        choix = params.get("scan_photo_modele", "nb")
        for i, (cle, nom, explication) in enumerate(MODELES):
            r = QRadioButton(nom)
            r.setToolTip(explication)
            r.setProperty("cle", cle)
            r.setChecked(cle == choix)
            self.groupe.addButton(r, i)
            vd.addWidget(r)
            l = QLabel(explication)
            l.setWordWrap(True)
            l.setStyleSheet("color:#666;margin-left:22px")
            vd.addWidget(l)
        self.groupe.buttonClicked.connect(lambda _b: self._apercu())
        sp.addWidget(droite)
        sp.setSizes([180, 520, 280])
        v.addWidget(sp, 1)
        self.ocr = QCheckBox(_("Reconnaître le texte (OCR) aussitôt le PDF créé"))
        self.ocr.setChecked(params.get("scan_photo_ocr", True))
        v.addWidget(self.ocr)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText(_("Créer le PDF"))
        bb.button(QDialogButtonBox.Cancel).setText(_("Annuler"))
        self.b_ok = bb.button(QDialogButtonBox.Ok)
        bb.accepted.connect(self.creer)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        self._t = QTimer(self, singleShot=True, interval=250, timeout=self._apercu)
        self._maj()
        if fichiers:
            self._ajouter_fichiers(fichiers)

    # ------------------------------------------------------------ pages
    def modele(self):
        b = self.groupe.checkedButton()
        return b.property("cle") if b else "nb"

    def ajouter(self):
        fs = QFileDialog.getOpenFileNames(self, _("Photos du document"), self.params.get("dossier_photos", ""),
                                          _("Images (*.jpg *.jpeg *.png *.heic *.webp *.tif *.tiff *.bmp)"))[0]
        if fs:
            self.params["dossier_photos"] = os.path.dirname(fs[0])
            self._ajouter_fichiers(fs)

    def _ajouter_fichiers(self, fs):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        refus = []
        try:
            for f in fs:
                try:
                    img = P.lire(f)
                except Exception:                    # noqa: BLE001
                    refus.append(os.path.basename(f))
                    continue
                self.pages.append({"img": img, "coins": P.coins(img).tolist()})
                self.liste.addItem(self._item(len(self.pages) - 1))
        finally:
            QApplication.restoreOverrideCursor()
        if refus:
            QMessageBox.warning(self, self.windowTitle(), _("Ces images ne peuvent pas être lues :") + "\n" + "\n".join(refus))
        if self.liste.currentRow() < 0 and self.pages:
            self.liste.setCurrentRow(0)
        self._maj()

    def _item(self, i):
        img = self.pages[i]["img"]
        petit = cv2.resize(img, (90, max(1, int(90 * img.shape[0] / img.shape[1]))))
        it = QListWidgetItem(QIcon(QPixmap.fromImage(qimage(petit))), _("Page {n}", n=i + 1))
        it.setData(Qt.UserRole, id(self.pages[i]))
        return it

    def _reordonner(self, *_a):
        par_id = {id(p): p for p in self.pages}
        self.pages = [par_id[self.liste.item(r).data(Qt.UserRole)] for r in range(self.liste.count())]
        for r in range(self.liste.count()):
            self.liste.item(r).setText(_("Page {n}", n=r + 1))

    def tourner(self):
        r = self.liste.currentRow()
        if r < 0:
            return
        p = self.pages[r]
        p["img"] = cv2.rotate(p["img"], cv2.ROTATE_90_CLOCKWISE)
        p["coins"] = P.coins(p["img"]).tolist()
        self.liste.takeItem(r)
        self.liste.insertItem(r, self._item(r))
        self.liste.setCurrentRow(r)

    def retirer(self):
        r = self.liste.currentRow()
        if r < 0:
            return
        self.pages.pop(r)
        self.liste.takeItem(r)
        self._reordonner()
        self._maj()

    def _choisir(self, r):
        if 0 <= r < len(self.pages):
            self.vue.montrer(self.pages[r]["img"], self.pages[r]["coins"])
        else:
            self.vue.montrer(None, None)
        self._apercu()

    def _coins(self, auto):
        r = self.liste.currentRow()
        if r < 0:
            return
        img = self.pages[r]["img"]
        h, w = img.shape[:2]
        self.pages[r]["coins"] = P.coins(img).tolist() if auto else [[0, 0], [w, 0], [w, h], [0, h]]
        self._choisir(r)

    def _coins_changes(self, c):
        r = self.liste.currentRow()
        if 0 <= r < len(self.pages):
            self.pages[r]["coins"] = c
            self._t.start()

    def _apercu(self):
        r = self.liste.currentRow()
        if not (0 <= r < len(self.pages)):
            self.apercu.clear()
            return
        p = self.pages[r]
        img = p["img"]
        e = min(1.0, 1100 / max(img.shape[:2]))
        petit = cv2.resize(img, (int(img.shape[1] * e), int(img.shape[0] * e)))
        out = P.ameliorer(P.redresser(petit, np.array(p["coins"], dtype=np.float32) * e), self.modele())
        pm = QPixmap.fromImage(qimage(out))
        self.apercu.setPixmap(pm.scaled(self.apercu.size() - QSize(8, 8), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def _maj(self):
        self.b_ok.setEnabled(bool(self.pages))

    # ------------------------------------------------------------ creation
    def creer(self):
        if not self.pages:
            return
        m = self.modele()
        self.params["scan_photo_modele"] = m
        self.params["scan_photo_ocr"] = self.ocr.isChecked()
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            pages = [P.octets(P.ameliorer(P.redresser(p["img"], np.array(p["coins"], dtype=np.float32)), m), m)
                     for p in self.pages]
            self.doc = P.pdf(pages)
        except Exception as e:                      # noqa: BLE001
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, self.windowTitle(), _("Création du PDF impossible : {e}", e=e))
            return
        QApplication.restoreOverrideCursor()
        self.accept()


def nom_scan():
    return _("Scan {d}", d=datetime.datetime.now().strftime("%Y-%m-%d %Hh%M")) + ".pdf"
