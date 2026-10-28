"""Retouche d'une image par l'IA (Gemini) : style pret a l'emploi ou consigne libre, zones entourees a la souris
(chacune avec sa propre consigne), puis comparaison avant / apres et validation. Rien ne change sans votre accord."""
import io

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, QThread, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDialog, QHBoxLayout, QHeaderView, QInputDialog, QLabel,
                               QMessageBox, QPlainTextEdit, QPushButton, QRadioButton, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from .langue import _
from . import styles_ia

COULEURS = [("#e53935", _("rouge")), ("#1e88e5", _("bleue")), ("#43a047", _("verte")), ("#fb8c00", _("orange")),
            ("#8e24aa", _("violette")), ("#00acc1", _("turquoise"))]


def qimage(img):
    return QImage(img.data, img.shape[1], img.shape[0], img.shape[1] * 4, QImage.Format_RGBA8888).copy()


def png(img):
    from moteur import retouche as R
    return R.vers_png(img)


class VueZones(QWidget):
    """Image en grand ; en mode « zones », on entoure a la souris (trace libre) : chaque zone est numerotee."""
    zones_changees = Signal()

    def __init__(self, img):
        super().__init__()
        self.img, self.montre = img, qimage(img)
        self.zones, self.trace, self.actif = [], None, False
        self.setMinimumSize(460, 380)
        self.setMouseTracking(True)

    def montrer(self, img):
        self.montre = qimage(img)
        self.update()

    def _cadre(self):
        h, w = self.img.shape[:2]
        k = min(self.width() / w, self.height() / h)
        return QRectF((self.width() - w * k) / 2, (self.height() - h * k) / 2, w * k, h * k), k

    def vers_image(self, pos):
        r, k = self._cadre()
        return QPointF((pos.x() - r.x()) / k, (pos.y() - r.y()) / k)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.fillRect(self.rect(), QColor("#e9e9e9"))
        r, k = self._cadre()
        p.drawImage(r, self.montre)
        for i, z in enumerate(self.zones + ([{"points": self.trace, "couleur": COULEURS[len(self.zones) % 6][0]}] if self.trace else [])):
            pts = [QPointF(r.x() + q.x() * k, r.y() + q.y() * k) for q in z["points"]]
            if len(pts) < 2:
                continue
            p.setPen(QPen(QColor(z["couleur"]), 2.5))
            c = QColor(z["couleur"])
            c.setAlpha(45)
            p.setBrush(c)
            p.drawPolygon(QPolygonF(pts))
            if z is not None and i < len(self.zones):
                f = QFont()
                f.setBold(True)
                f.setPixelSize(16)
                p.setFont(f)
                p.setPen(QColor("#ffffff"))
                p.setBrush(QColor(z["couleur"]))
                b = QRectF(pts[0].x() - 11, pts[0].y() - 11, 22, 22)
                p.drawEllipse(b)
                p.drawText(b, Qt.AlignCenter, str(i + 1))
        if self.actif and not self.zones and not self.trace:
            p.setPen(QColor("#555555"))
            p.drawText(self.rect().adjusted(0, 0, 0, -8), Qt.AlignBottom | Qt.AlignHCenter,
                       _("Entourez une zone à la souris (maintenez le bouton enfoncé)"))
        p.end()

    def mousePressEvent(self, e):
        if self.actif and e.button() == Qt.LeftButton:
            self.trace = [self.vers_image(e.position())]

    def mouseMoveEvent(self, e):
        if self.trace is not None and e.buttons() & Qt.LeftButton:
            self.trace.append(self.vers_image(e.position()))
            self.update()

    def mouseReleaseEvent(self, e):
        if self.trace is not None:
            if len(self.trace) > 4:
                c, nom = COULEURS[len(self.zones) % 6]
                self.zones.append({"points": self.trace, "couleur": c, "couleur_nom": nom, "consigne": ""})
                self.zones_changees.emit()
            self.trace = None
            self.update()

    def image_zones(self):
        """L'image avec les zones entourees et numerotees (envoyee en deuxieme image a Gemini)."""
        q = qimage(self.img)
        p = QPainter(q)
        p.setRenderHint(QPainter.Antialiasing)
        ep = max(3, int(max(q.width(), q.height()) / 250))
        f = QFont()
        f.setBold(True)
        f.setPixelSize(ep * 7)
        p.setFont(f)
        for i, z in enumerate(self.zones):
            pts = [QPointF(t.x(), t.y()) for t in z["points"]]
            p.setPen(QPen(QColor(z["couleur"]), ep))
            p.setBrush(Qt.NoBrush)
            p.drawPolygon(QPolygonF(pts))
            p.setPen(QColor(z["couleur"]))
            p.drawText(pts[0] + QPointF(ep, -ep), str(i + 1))
        p.end()
        b = io.BytesIO()
        from PySide6.QtCore import QBuffer, QIODevice
        buf = QBuffer()
        buf.open(QIODevice.WriteOnly)
        q.save(buf, "PNG")
        return bytes(buf.data())


class TacheIA(QThread):
    fini = Signal(object, str)
    info = Signal(str)

    def __init__(self, params, image_png, consigne, zones_png):
        super().__init__()
        self.args = (params, image_png, consigne, zones_png)

    def run(self):
        from . import ia
        ia.suivre(self.info.emit)
        try:
            self.fini.emit(ia.retoucher_image(*self.args), "")
        except Exception as e:
            self.fini.emit(None, str(e))


def detourer(img):
    """Fond vert uni demande a l'IA -> transparent (et les bords verts adoucis)."""
    import cv2
    hsv = cv2.cvtColor(np.ascontiguousarray(img[:, :, :3]), cv2.COLOR_RGB2HSV)
    vert = cv2.inRange(hsv, (40, 80, 80), (85, 255, 255))
    vert = cv2.morphologyEx(vert, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    out = img.copy()
    out[:, :, 3] = np.where(vert > 0, 0, 255).astype(np.uint8)
    out[:, :, 3] = cv2.GaussianBlur(out[:, :, 3], (3, 3), 0)
    return out


class DialogueRetoucheIA(QDialog):
    def __init__(self, parent, img, params):
        super().__init__(parent)
        self.setWindowTitle(_("Retouche avec l'IA (Gemini)"))
        self.resize(1180, 720)
        self.params, self.img, self.resultat, self.tache = params, img, None, None
        h = QHBoxLayout(self)
        gauche = QVBoxLayout()
        self.vue = VueZones(img)
        gauche.addWidget(self.vue, 1)
        hb = QHBoxLayout()
        self.b_avant = QPushButton(_("Voir l'original"))
        self.b_avant.setToolTip(_("Maintenez enfoncé pour voir l'image d'avant"))
        self.b_avant.setEnabled(False)
        self.b_avant.pressed.connect(lambda: self.vue.montrer(self.img))
        self.b_avant.released.connect(lambda: self.vue.montrer(self.resultat if self.resultat is not None else self.img))
        hb.addWidget(self.b_avant)
        self.b_cote = QCheckBox(_("Côte à côte"))
        self.b_cote.setEnabled(False)
        self.b_cote.toggled.connect(self._cote_a_cote)
        hb.addWidget(self.b_cote)
        hb.addStretch(1)
        self.etat = QLabel(_("L'image part chez Google (Gemini) seulement quand vous cliquez sur « Envoyer »."))
        self.etat.setStyleSheet("color:#555")
        hb.addWidget(self.etat)
        gauche.addLayout(hb)
        self.suivi = QPlainTextEdit()              # ce qui se passe pendant l'envoi, en direct
        self.suivi.setObjectName("suivi_ia")
        self.suivi.setReadOnly(True)
        self.suivi.setMaximumHeight(130)
        self.suivi.setStyleSheet("QPlainTextEdit{font-family:Consolas,monospace;font-size:12px;background:#fafafa}")
        self.suivi.setVisible(False)
        gauche.addWidget(self.suivi)
        h.addLayout(gauche, 3)
        from PySide6.QtCore import QTimer
        self.chrono = QTimer(self)
        self.chrono.setInterval(1000)
        self.chrono.timeout.connect(self._tic)
        d = QVBoxLayout()
        d.addWidget(QLabel(_("<b>Style</b> (remplit la consigne)")))
        self.cb_style = QComboBox()
        self.cb_style.setMaxVisibleItems(24)
        self._remplir_styles()
        self.cb_style.currentIndexChanged.connect(self._style_choisi)
        d.addWidget(self.cb_style)
        hi = QHBoxLayout()
        self.r_leg, self.r_mar = QRadioButton(_("Effet léger")), QRadioButton(_("Effet marqué"))
        self.r_mar.setChecked(True)
        grp = QButtonGroup(self)
        grp.addButton(self.r_leg)
        grp.addButton(self.r_mar)
        hi.addWidget(self.r_leg)
        hi.addWidget(self.r_mar)
        hi.addStretch(1)
        d.addLayout(hi)
        self.c_garder = QCheckBox(_("Garder les visages et le cadrage"))
        self.c_garder.setChecked(True)
        d.addWidget(self.c_garder)
        d.addWidget(QLabel(_("<b>Consigne</b> (modifiable)")))
        self.consigne = QPlainTextEdit()
        self.consigne.setPlaceholderText(_("Décrivez ce que l'IA doit faire de l'image, ou choisissez un style ci-dessus."))
        self.consigne.setMinimumHeight(90)
        d.addWidget(self.consigne)
        b = QPushButton(_("Enregistrer comme mon style..."))
        b.setToolTip(_("Garde cette consigne dans « Mes styles » (suit sur vos autres postes)"))
        b.clicked.connect(self._enregistrer_style)
        d.addWidget(b)
        self.c_zones = QCheckBox(_("Mode avancé : entourer des zones"))
        self.c_zones.setToolTip(_("Entourez à la souris les zones à modifier et dites, pour chacune, ce qu'il faut en faire"))
        self.c_zones.toggled.connect(self._mode_zones)
        d.addWidget(self.c_zones)
        self.t_zones = QTableWidget(0, 2)
        self.t_zones.setHorizontalHeaderLabels([_("Zone"), _("Ce qu'il faut en faire")])
        self.t_zones.verticalHeader().hide()
        self.t_zones.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.t_zones.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.t_zones.itemChanged.connect(self._consigne_zone)
        self.t_zones.setVisible(False)
        d.addWidget(self.t_zones, 1)
        self.b_eff_zones = QPushButton(_("Effacer les zones"))
        self.b_eff_zones.setVisible(False)
        self.b_eff_zones.clicked.connect(self._effacer_zones)
        d.addWidget(self.b_eff_zones)
        self.vue.zones_changees.connect(self._maj_zones)
        d.addStretch(1)
        hb2 = QHBoxLayout()
        self.b_env = QPushButton(_("Envoyer à Gemini"))
        self.b_env.setStyleSheet("QPushButton{background:#0f6cbd;color:#fff;border:none;border-radius:6px;padding:7px 12px;font-weight:600}")
        self.b_env.clicked.connect(self.envoyer)
        hb2.addWidget(self.b_env)
        self.b_ok = QPushButton(_("Garder le résultat"))
        self.b_ok.setEnabled(False)
        self.b_ok.clicked.connect(self.accept)
        hb2.addWidget(self.b_ok)
        b = QPushButton(_("Annuler"))
        b.clicked.connect(self.reject)
        hb2.addWidget(b)
        d.addLayout(hb2)
        h.addLayout(d, 2)

    # ---- styles
    def _remplir_styles(self):
        self.cb_style.clear()
        self.cb_style.addItem(_("(consigne libre)"), None)
        groupe = None
        perso = [(_("Mes styles"), s["nom"], s["consigne"]) for s in self.params.get("ia_styles_perso") or []]
        for g, nom, consigne in perso + styles_ia.styles():
            if g != groupe:
                self.cb_style.insertSeparator(self.cb_style.count())
                self.cb_style.addItem(f"— {g} —", None)
                self.cb_style.model().item(self.cb_style.count() - 1).setEnabled(False)
                groupe = g
            self.cb_style.addItem("   " + nom, consigne)

    def _style_choisi(self, _i):
        c = self.cb_style.currentData()
        if not c:
            return
        if c == styles_ia.DETOURER:
            c = _("Remplace tout l'arrière-plan par un vert uni pur (#00FF00), sans ombre ni dégradé ; le sujet reste "
                  "parfaitement identique, contours nets.")
        self.consigne.setPlainText(c)

    def _enregistrer_style(self):
        t = self.consigne.toPlainText().strip()
        if not t:
            return
        nom, ok = QInputDialog.getText(self, _("Mon style"), _("Nom de ce style :"))
        if ok and nom.strip():
            ls = [s for s in self.params.get("ia_styles_perso") or [] if s["nom"] != nom.strip()]
            self.params["ia_styles_perso"] = ls + [{"nom": nom.strip(), "consigne": t}]
            self.params.enregistrer()
            self._remplir_styles()

    # ---- zones
    def _mode_zones(self, on):
        self.vue.actif = on
        self.t_zones.setVisible(on)
        self.b_eff_zones.setVisible(on)
        self.vue.update()

    def _maj_zones(self):
        self.t_zones.blockSignals(True)
        self.t_zones.setRowCount(len(self.vue.zones))
        for i, z in enumerate(self.vue.zones):
            it = QTableWidgetItem(f"{i + 1} ({z['couleur_nom']})")
            it.setForeground(QColor(z["couleur"]))
            it.setFlags(Qt.ItemIsEnabled)
            self.t_zones.setItem(i, 0, it)
            self.t_zones.setItem(i, 1, QTableWidgetItem(z["consigne"]))
        self.t_zones.blockSignals(False)
        if self.vue.zones:
            self.t_zones.editItem(self.t_zones.item(len(self.vue.zones) - 1, 1))

    def _consigne_zone(self, it):
        if it.column() == 1 and it.row() < len(self.vue.zones):
            self.vue.zones[it.row()]["consigne"] = it.text()

    def _effacer_zones(self):
        self.vue.zones = []
        self._maj_zones()
        self.vue.update()

    # ---- envoi et resultat
    def envoyer(self):
        texte = self.consigne.toPlainText().strip()
        zones = self.vue.zones if self.c_zones.isChecked() else []
        if not texte and not any(z["consigne"] for z in zones):
            QMessageBox.information(self, self.windowTitle(), _("Choisissez un style ou écrivez une consigne."))
            return
        from . import ia
        if not ia.nettoyer_clef(self.params.get("clef_gemini", "")):
            QMessageBox.information(self, self.windowTitle(), _("Il faut une clef Gemini (Edition › Préférences › IA) : "
                                                                "Claude ne sait pas modifier une image."))
            return
        from moteur import retouche as R
        envoi = R.reduire(self.img, 2048)
        consigne = styles_ia.consigne_complete(texte, "legere" if self.r_leg.isChecked() else "marquee",
                                               self.c_garder.isChecked(), zones)
        zones_png = None
        if zones:
            self.vue.img = envoi if envoi.shape == self.img.shape else self.img
            zones_png = self.vue.image_zones()
            self.vue.img = self.img
        self.b_env.setEnabled(False)
        self.setCursor(Qt.BusyCursor)
        self.suivi.setVisible(True)
        self.suivi.clear()
        import time
        self._debut = time.monotonic()
        self._ajouter_suivi(_("Préparation : image {l} × {h} px, style « {s} »", l=envoi.shape[1], h=envoi.shape[0],
                              s=self.cb_style.currentText() or _("consigne libre")) +
                            (_(", {n} zone(s)", n=len(zones)) if zones else ""))
        self._tic()
        self.chrono.start()
        self.tache = TacheIA(self.params, png(envoi), consigne, zones_png)
        self.tache.info.connect(self._ajouter_suivi)
        self.tache.fini.connect(self._recu)
        self.tache.start()

    def _ajouter_suivi(self, texte):
        import time
        s = int(time.monotonic() - getattr(self, "_debut", time.monotonic()))
        self.suivi.appendPlainText(f"[{s // 60:02d}:{s % 60:02d}] {texte}")
        self.suivi.verticalScrollBar().setValue(self.suivi.verticalScrollBar().maximum())

    def _tic(self):
        import time
        s = int(time.monotonic() - self._debut)
        self.etat.setText(_("Envoi en cours : {s} s écoulées (souvent 10 à 60 s)...", s=s))

    def _recu(self, octets, err):
        self.chrono.stop()
        self.unsetCursor()
        self.b_env.setEnabled(True)
        if not self.isVisible():                  # fenetre fermee pendant l'attente
            return
        if err:
            self.etat.setText("✕ " + _("Refusé : voir le détail ci-dessous"))
            self._ajouter_suivi(_("Terminé sans image."))
            QMessageBox.warning(self, self.windowTitle(), err)
            return
        self._ajouter_suivi(_("Terminé."))
        from PIL import Image
        import cv2
        im = Image.open(io.BytesIO(octets)).convert("RGBA")
        res = np.array(im)
        h, w = self.img.shape[:2]
        if res.shape[:2] != (h, w):                       # meme taille que l'image d'origine (meme place dans la page)
            res = cv2.resize(res, (w, h), interpolation=cv2.INTER_AREA if res.shape[1] > w else cv2.INTER_CUBIC)
        if self.cb_style.currentData() == styles_ia.DETOURER:
            res = detourer(res)
        else:
            res[:, :, 3] = self.img[:, :, 3]
        self.resultat = res
        self.vue.montrer(res)
        self.b_ok.setEnabled(True)
        self.b_avant.setEnabled(True)
        self.b_cote.setEnabled(True)
        self.etat.setText(_("✓ Résultat reçu : comparez (bouton « Voir l'original »), puis gardez-le ou réessayez."))

    def _cote_a_cote(self, on):
        if self.resultat is None:
            return
        if on:
            sep = np.full((self.img.shape[0], max(4, self.img.shape[1] // 60), 4), 255, np.uint8)
            self.vue.img = np.hstack([self.img, sep, self.resultat])
            self.vue.montrer(self.vue.img)
        else:
            self.vue.img = self.img
            self.vue.montrer(self.resultat)
