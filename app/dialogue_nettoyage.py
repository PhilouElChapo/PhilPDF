"""Nettoyer un scan (Outils > Nettoyer un scan, et apres une numerisation) : avant / apres cote a cote, page par
page, avec les reglages a la main : redresser (automatique, non, ou angle choisi), bords noirs, taches et grain,
contraste du noir et blanc. Rien n'est change avant « Nettoyer », et « Annuler » (Ctrl+Z) revient en arriere."""
import cv2
import numpy as np
import pymupdf as fitz
from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem, QLabel, QComboBox,
                               QCheckBox, QSlider, QDoubleSpinBox, QRadioButton, QButtonGroup, QDialogButtonBox,
                               QGroupBox, QFormLayout, QMessageBox, QApplication, QPushButton)

from .langue import _
from moteur import nettoyage as N, scan as S


def _pixmap(gris):
    h, w = gris.shape
    q = QImage(gris.data, w, h, w, QImage.Format_Grayscale8).copy()
    return QPixmap.fromImage(q)


class DialogueNettoyerScan(QDialog):
    def __init__(self, fenetre, onglet):
        super().__init__(fenetre)
        self.f, self.o = fenetre, onglet
        self.setWindowTitle(_("Nettoyer un scan") + " — " + onglet.nom)
        ecran = self.screen().availableGeometry()
        self.resize(min(1250, ecran.width() - 40), min(820, ecran.height() - 60))
        self.cache = {}                                    # page -> (gris reduit, dpi reduit)
        v = QVBoxLayout(self)
        aide = QLabel(_("Choisissez les réglages en regardant l'aperçu, puis « Nettoyer » : les pages cochées sont "
                        "remplacées par leur version nettoyée (noir et blanc net). Ctrl+Z revient en arrière."))
        aide.setWordWrap(True)
        v.addWidget(aide)
        h = QHBoxLayout()
        v.addLayout(h, 1)
        self.liste = QListWidget()
        self.liste.setMaximumWidth(150)
        for i, p in enumerate(onglet.doc):
            it = QListWidgetItem(_("Page {n}", n=i + 1))
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if self._est_scan(p) else Qt.Unchecked)
            self.liste.addItem(it)
        self.liste.currentRowChanged.connect(lambda _r: self._plus_tard())
        h.addWidget(self.liste)
        self.avant, self.apres = QLabel(), QLabel()
        for t, lb in ((_("AVANT"), self.avant), (_("APRES"), self.apres)):
            c = QVBoxLayout()
            c.addWidget(QLabel("<b>" + t + "</b>"))
            lb.setAlignment(Qt.AlignCenter)
            lb.setMinimumSize(260, 340)
            lb.setStyleSheet("background:#ffffff;border:1px solid #ddd")
            c.addWidget(lb, 1)
            h.addLayout(c, 1)
        # reglages
        g = QGroupBox(_("Réglages"))
        g.setMaximumWidth(330)
        fl = QFormLayout(g)
        self.redr = QButtonGroup(self)
        rv = QVBoxLayout()
        for k, t in enumerate((_("Automatique"), _("Ne pas tourner"), _("Angle choisi :"))):
            r = QRadioButton(t)
            self.redr.addButton(r, k)
            rv.addWidget(r)
        self.redr.button(0).setChecked(True)
        self.angle = QDoubleSpinBox()
        self.angle.setRange(-15, 15)
        self.angle.setSingleStep(0.1)
        self.angle.setSuffix(" °")
        rv.addWidget(self.angle)
        self.angle_trouve = QLabel()
        self.angle_trouve.setStyleSheet("color:#666")
        rv.addWidget(self.angle_trouve)
        fl.addRow(_("Redresser"), rv)
        self.bords = QCheckBox(_("Effacer les bords noirs et les traits du bord"))
        self.bords.setChecked(True)
        fl.addRow(self.bords)
        self.taches = QComboBox()
        self.taches.addItem(_("Aucune"), 0)
        self.taches.addItem(_("Petites taches isolées (conseillé)"), 1)
        self.taches.addItem(_("Fort : aussi les taches moyennes"), 2)
        self.taches.setCurrentIndex(1)
        self.taches.setToolTip(_("« Fort » peut effacer un trait de crayon très pâle : regardez l'aperçu."))
        fl.addRow(_("Taches et grain"), self.taches)
        self.contraste = QSlider(Qt.Horizontal)
        self.contraste.setRange(6, 40)
        self.contraste.setValue(N.REGLAGES["contraste"])
        hc = QHBoxLayout()
        hc.addWidget(QLabel(_("plus foncé")))
        hc.addWidget(self.contraste, 1)
        hc.addWidget(QLabel(_("plus clair")))
        fl.addRow(_("Noir et blanc"), hc)
        self.detail = QLabel()
        self.detail.setWordWrap(True)
        self.detail.setStyleSheet("color:#2e7d32")
        fl.addRow(self.detail)
        tout = QPushButton(_("Cocher toutes les pages"))
        tout.clicked.connect(lambda: [self.liste.item(i).setCheckState(Qt.Checked) for i in range(self.liste.count())])
        fl.addRow(tout)
        h.addWidget(g)
        for w in (self.redr.buttons()):
            w.toggled.connect(lambda _b: self._plus_tard())
        self.angle.valueChanged.connect(lambda _v: (self.redr.button(2).setChecked(True), self._plus_tard()))
        self.bords.toggled.connect(lambda _b: self._plus_tard())
        self.taches.currentIndexChanged.connect(lambda _i: self._plus_tard())
        self.contraste.valueChanged.connect(lambda _v: self._plus_tard())
        bb = QDialogButtonBox()
        self.b_ok = bb.addButton(_("Nettoyer les pages cochées"), QDialogButtonBox.AcceptRole)
        bb.addButton(_("Annuler"), QDialogButtonBox.RejectRole)
        bb.accepted.connect(self.appliquer)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        self._t = QTimer(self, singleShot=True, interval=250, timeout=self._apercu)
        self.liste.setCurrentRow(max(0, onglet.page_courante() if hasattr(onglet, "page_courante") else 0))
        self._plus_tard()

    @staticmethod
    def _est_scan(p):
        """Page faite d'une seule image qui la couvre (scan, photo)."""
        try:
            imgs = p.get_images(full=True)
            if len(imgs) != 1:
                return False
            r = p.get_image_rects(imgs[0][0])
            return bool(r) and r[0].width >= p.rect.width * 0.9 and r[0].height >= p.rect.height * 0.9
        except Exception:                                  # noqa: BLE001
            return False

    def reglages(self):
        k = self.redr.checkedId()
        return {"redresser": "auto" if k == 0 else "non" if k == 1 else self.angle.value(),
                "bords": self.bords.isChecked(), "taches": self.taches.currentData(), "contraste": self.contraste.value()}

    def _plus_tard(self):
        self._t.start()

    def _page_reduite(self, n):
        if n not in self.cache:
            gris, dpi = S.image_de_page(self.o.doc, self.o.doc[n], 200)
            e = min(1.0, 1500 / max(gris.shape))
            if e < 1:
                gris = cv2.resize(gris, None, fx=e, fy=e, interpolation=cv2.INTER_AREA)
            self.cache[n] = (gris, max(60, int(dpi * e)))
        return self.cache[n]

    def _apercu(self):
        n = self.liste.currentRow()
        if n < 0:
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            gris, dpi = self._page_reduite(n)
            nb, a, d = N.page(gris, dpi, self.reglages())
        finally:
            QApplication.restoreOverrideCursor()
        taille = self.avant.size() - QSize(8, 8)
        self.avant.setPixmap(_pixmap(gris).scaled(taille, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.apres.setPixmap(_pixmap(nb).scaled(taille, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        if self.redr.checkedId() == 0:
            self.angle_trouve.setText(_("Inclinaison trouvée : {a} °", a=f"{a:+.2f}".replace(".", ",")))
        else:
            self.angle_trouve.setText("")
        self.detail.setText(_("Page {n} : {t} tache(s) et {b} bord(s) retirés.", n=n + 1, t=d["taches"], b=d["bords"]))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._plus_tard()

    def appliquer(self):
        pages = [i for i in range(self.liste.count()) if self.liste.item(i).checkState() == Qt.Checked]
        if not pages:
            QMessageBox.information(self, self.windowTitle(), _("Cochez au moins une page."))
            return
        doc = self.o.doc
        avec_texte = [i + 1 for i in pages if S.a_du_texte(doc[i])]
        if avec_texte and QMessageBox.question(self, self.windowTitle(), _(
                "Page(s) {l} : leur texte reconnu (OCR) et leurs annotations seront retirés avec l'ancienne image. "
                "Relancez ensuite « Reconnaître le texte ».\n\nContinuer ?", l=", ".join(map(str, avec_texte)))) != QMessageBox.Yes:
            return
        r = self.reglages()
        from .dialogues_ia import executer_suivi

        def travail(t):
            out = fitz.open()
            bilan = {"taches": 0, "bords": 0}
            for i, p in enumerate(doc):
                if i not in pages:
                    out.insert_pdf(doc, from_page=i, to_page=i)
                    continue
                t.avancer(_("Nettoyage de la page {i} sur {n}...", i=pages.index(i) + 1, n=len(pages)), pages.index(i), len(pages))
                gris, dpi = S.image_de_page(doc, p)
                nb, a, d = N.page(gris, dpi, r)
                for k in bilan:
                    bilan[k] += d[k]
                t.noter(_("Page {p} : tournée de {a} °, {t} tache(s), {b} bord(s)", p=i + 1,
                          a=f"{a:+.2f}".replace(".", ","), t=d["taches"], b=d["bords"]))
                S.page_scan(out, S.tiff_g4(nb, dpi), p.rect.width, p.rect.height)
            return out.tobytes(garbage=3, deflate=True), bilan
        try:
            octets, bilan = executer_suivi(self, _("Nettoyer un scan"), travail)
        except InterruptedError:
            return
        except Exception as e:                             # noqa: BLE001
            QMessageBox.warning(self, self.windowTitle(), _("Nettoyage impossible : {e}", e=e))
            return
        self.o.memoriser(_("Nettoyer un scan"))
        self.o.remplacer_document(octets)
        self.o.apres_modif([_("{n} page(s) nettoyée(s) : {t} tache(s) et {b} bord(s) retirés.", n=len(pages),
                              t=bilan["taches"], b=bilan["bords"])])
        self.accept()
