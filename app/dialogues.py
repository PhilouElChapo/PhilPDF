"""Dialogues : bibliotheque de tampons et signatures, import de zone, signature dessinee,
filigrane, en-tete et pied de page, numerisation, export."""
import datetime, os
import pymupdf as fitz
from PySide6.QtCore import Qt, Signal, QRectF, QPointF, QSize, QPoint
from PySide6.QtGui import QImage, QPainter, QColor, QPen, QPixmap, QPainterPath, QIcon
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QListWidget, QListWidgetItem,
                               QFileDialog, QInputDialog, QDialogButtonBox, QCheckBox, QComboBox, QSpinBox,
                               QLineEdit, QFormLayout, QWidget, QColorDialog, QSlider, QRadioButton, QButtonGroup,
                               QGroupBox, QMessageBox, QScrollArea, QDoubleSpinBox, QTabWidget)
from moteur import objets
from .icones import icone


def _pix_depuis_png(octets, h=56):
    pm = QPixmap()
    pm.loadFromData(octets, "PNG")
    return pm.scaledToHeight(h, Qt.SmoothTransformation) if not pm.isNull() else pm


def boutons_fr(bb):
    """Libelles francais pour les boutons standard."""
    noms = {QDialogButtonBox.Ok: "OK", QDialogButtonBox.Cancel: "Annuler", QDialogButtonBox.Save: "Enregistrer",
            QDialogButtonBox.Discard: "Ne pas enregistrer", QDialogButtonBox.Close: "Fermer",
            QDialogButtonBox.Yes: "Oui", QDialogButtonBox.No: "Non", QDialogButtonBox.Apply: "Appliquer"}
    for k, v in noms.items():
        b = bb.button(k)
        if b:
            b.setText(v)
    return bb


# ------------------------------------------------------------------ choix d'une zone
class SelecteurZone(QDialog):
    """Affiche une page (PDF) ou une image ; on trace a la souris la zone a importer."""

    def __init__(self, parent, chemin):
        super().__init__(parent)
        self.setWindowTitle("Choisir la zone à importer")
        self.resize(900, 760)
        self.chemin, self.num, self.zone = chemin, 0, None
        self.est_pdf = chemin.lower().endswith(".pdf")
        self.doc = fitz.open(chemin) if self.est_pdf else None
        v = QVBoxLayout(self)
        aide = QLabel("Tracez un rectangle autour du tampon ou de la signature. "
                      + ("Les tampons Acrobat trouvés dans le fichier sont proposés ci-dessous." if self.est_pdf else ""))
        aide.setWordWrap(True)
        v.addWidget(aide)
        h = QHBoxLayout()
        self.tampons = objets.tampons_du_pdf(chemin) if self.est_pdf else []
        if self.tampons:
            h.addWidget(QLabel("Tampons du fichier :"))
            for pg, r, nom in self.tampons:
                b = QPushButton(nom)
                b.clicked.connect(lambda _=False, pg=pg, r=r: self._choisir(pg, r))
                h.addWidget(b)
        h.addStretch()
        if self.est_pdf and len(self.doc) > 1:
            self.pg = QSpinBox()
            self.pg.setRange(1, len(self.doc))
            self.pg.valueChanged.connect(lambda n: (setattr(self, "num", n - 1), self._rendre()))
            h.addWidget(QLabel("Page"))
            h.addWidget(self.pg)
        v.addLayout(h)
        self.toile = QLabel()
        self.toile.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.toile.setMouseTracking(True)
        self.toile.mousePressEvent = self._press
        self.toile.mouseMoveEvent = self._move
        self.toile.mouseReleaseEvent = lambda e: None
        sc = QScrollArea()
        sc.setWidget(self.toile)
        sc.setWidgetResizable(False)
        v.addWidget(sc, 1)
        self.transparent = QCheckBox("Rendre le fond blanc transparent (pour un scan ou une photo)")
        self.transparent.setChecked(not self.est_pdf)
        v.addWidget(self.transparent)
        bb = boutons_fr(QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel))
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        self._debut = None
        self._rendre()

    def _rendre(self):
        if self.est_pdf:
            p = self.doc[self.num]
            self.k = min(820 / p.rect.width, 1.6)
            pm = p.get_pixmap(matrix=fitz.Matrix(self.k, self.k), annots=True)
            self.base = QPixmap.fromImage(QImage(pm.samples, pm.width, pm.height, pm.stride, QImage.Format_RGB888).copy())
        else:
            self.base = QPixmap(self.chemin)
            self.k = min(820 / max(1, self.base.width()), 1.0)
            self.base = self.base.scaledToWidth(int(self.base.width() * self.k), Qt.SmoothTransformation)
        self._dessiner()

    def _dessiner(self):
        pm = QPixmap(self.base)
        if self.zone:
            p = QPainter(pm)
            p.setPen(QPen(QColor("#1462c2"), 2, Qt.DashLine))
            p.setBrush(QColor(20, 98, 194, 40))
            z = self.zone
            p.drawRect(QRectF(z[0] * self.k, z[1] * self.k, (z[2] - z[0]) * self.k, (z[3] - z[1]) * self.k))
            p.end()
        self.toile.setPixmap(pm)
        self.toile.resize(pm.size())

    def _press(self, e):
        self._debut = (e.position().x() / self.k, e.position().y() / self.k)

    def _move(self, e):
        if self._debut and e.buttons() & Qt.LeftButton:
            x, y = e.position().x() / self.k, e.position().y() / self.k
            x0, y0 = self._debut
            self.zone = (min(x0, x), min(y0, y), max(x0, x), max(y0, y))
            self._dessiner()

    def _choisir(self, pg, r):
        self.num = pg
        self._rendre()
        self.zone = (r.x0, r.y0, r.x1, r.y1)
        self._dessiner()

    def resultat(self):
        """PDF d'une page correspondant a la zone (ou a tout si rien n'est trace)."""
        if self.est_pdf:
            zone = self.zone or tuple(self.doc[self.num].rect)
            pdf = objets.pdf_depuis_zone(self.chemin, self.num, zone)
            if self.transparent.isChecked():   # scan colle dans un PDF : on passe par l'image
                p = fitz.open("pdf", pdf)[0]
                pdf = objets.pdf_depuis_image(p.get_pixmap(dpi=200).tobytes("png"), True)
            return pdf
        return objets.pdf_depuis_image(self.chemin, self.transparent.isChecked(), self.zone)


# ------------------------------------------------------------------ signature dessinee
class PaveSignature(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Dessiner votre signature")
        self.traits, self.courant = [], None
        v = QVBoxLayout(self)
        v.addWidget(QLabel("Signez avec la souris, le pavé tactile ou un stylet."))
        self.zone = QLabel()
        self.zone.setFixedSize(600, 220)
        self.zone.setStyleSheet("background:#fff;border:1px solid #cfcfcf;border-radius:8px")
        self.zone.mousePressEvent = lambda e: self._ajout(e, True)
        self.zone.mouseMoveEvent = lambda e: self._ajout(e, False)
        v.addWidget(self.zone)
        h = QHBoxLayout()
        self.coul = QComboBox()
        self.coul.addItems(["Bleu", "Noir"])
        h.addWidget(QLabel("Encre"))
        h.addWidget(self.coul)
        eff = QPushButton("Effacer")
        eff.clicked.connect(lambda: (self.traits.clear(), self._dessiner()))
        h.addWidget(eff)
        h.addStretch()
        v.addLayout(h)
        bb = boutons_fr(QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel))
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        self._dessiner()

    def _ajout(self, e, nouveau):
        pt = (e.position().x(), e.position().y())
        if nouveau or not self.traits:
            self.traits.append([pt])
        else:
            self.traits[-1].append(pt)
        self._dessiner()

    def _encre(self):
        return (0.08, 0.2, 0.62) if self.coul.currentIndex() == 0 else (0.05, 0.05, 0.05)

    def _dessiner(self):
        pm = QPixmap(600, 220)
        pm.fill(Qt.white)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        c = self._encre()
        p.setPen(QPen(QColor.fromRgbF(*c), 2.4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        for t in self.traits:
            for a, b in zip(t, t[1:]):
                p.drawLine(QPointF(*a), QPointF(*b))
        p.setPen(QPen(QColor("#dddddd"), 1, Qt.DashLine))
        p.drawLine(30, 170, 570, 170)
        p.end()
        self.zone.setPixmap(pm)

    def resultat(self):
        """Signature vectorielle (traits) en PDF d'une page."""
        pts = [q for t in self.traits for q in t]
        if not pts:
            return None
        x0, y0 = min(p[0] for p in pts) - 4, min(p[1] for p in pts) - 4
        x1, y1 = max(p[0] for p in pts) + 4, max(p[1] for p in pts) + 4
        k = 0.5
        d = fitz.open()
        page = d.new_page(width=(x1 - x0) * k, height=(y1 - y0) * k)
        sh = page.new_shape()
        for t in self.traits:
            if len(t) > 1:
                sh.draw_polyline([((x - x0) * k, (y - y0) * k) for x, y in t])
        sh.finish(color=self._encre(), width=1.3, lineCap=1, lineJoin=1, closePath=False)
        sh.commit()
        return d.tobytes(garbage=3, deflate=True)


# ------------------------------------------------------------------ bibliotheque (tampons / signatures)
class DialogueBibliotheque(QDialog):
    """Gestion des tampons ou des signatures : ajouter, importer, renommer, supprimer, par defaut."""

    def __init__(self, parent, biblio, genre, auteur=""):
        super().__init__(parent)
        self.b, self.genre, self.auteur = biblio, genre, auteur
        titre = "Mes tampons" if genre == "tampons" else "Mes signatures"
        self.setWindowTitle(titre)
        self.resize(720, 520)
        v = QVBoxLayout(self)
        info = QLabel("Rangés sur ce PC" + (", avec une sauvegarde sur le Drive." if biblio.params.get("drive") else
                                            ". Indiquez votre Drive dans Préférences pour les retrouver sur vos autres PC."))
        info.setStyleSheet("color:#555")
        v.addWidget(info)
        self.liste = QListWidget()
        self.liste.setViewMode(QListWidget.IconMode)
        self.liste.setIconSize(QSize(200, 70))
        self.liste.setGridSize(QSize(220, 110))
        self.liste.setResizeMode(QListWidget.Adjust)
        self.liste.setMovement(QListWidget.Static)
        self.liste.itemDoubleClicked.connect(lambda _: self.accept())
        v.addWidget(self.liste, 1)
        h = QHBoxLayout()
        if genre == "tampons":
            b = QPushButton("Tampon prêt à l'emploi...")
            b.clicked.connect(self.predefini)
            h.addWidget(b)
            b = QPushButton("Tampon texte personnalisé...")
            b.clicked.connect(self.texte_perso)
            h.addWidget(b)
        else:
            b = QPushButton("Dessiner...")
            b.clicked.connect(self.dessiner)
            h.addWidget(b)
        b = QPushButton("Importer d'une image ou d'un PDF...")
        b.clicked.connect(self.importer)
        h.addWidget(b)
        h.addStretch()
        v.addLayout(h)
        h = QHBoxLayout()
        for txt, f in [("Renommer", self.renommer), ("Supprimer", self.supprimer), ("Par défaut", self.defaut)]:
            b = QPushButton(txt)
            b.clicked.connect(f)
            h.addWidget(b)
        if biblio.params.get("drive"):
            b = QPushButton("Récupérer depuis le Drive")
            b.clicked.connect(self.restaurer)
            h.addWidget(b)
        h.addStretch()
        v.addLayout(h)
        bb = QDialogButtonBox()
        self.b_utiliser = bb.addButton("Utiliser", QDialogButtonBox.AcceptRole)
        bb.addButton("Fermer", QDialogButtonBox.RejectRole)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        self.rafraichir()

    def rafraichir(self, choisir=None):
        self.liste.clear()
        defaut = self.b.par_defaut(self.genre)
        for e in self.b.elements(self.genre):
            it = QListWidgetItem(QIcon(_pix_depuis_png(objets.apercu(self.b.lire(e), 70), 70)),
                                 e["nom"] + ("  ★" if defaut and e["id"] == defaut["id"] else ""))
            it.setData(Qt.UserRole, e)
            self.liste.addItem(it)
            if choisir and e["id"] == choisir["id"]:
                self.liste.setCurrentItem(it)

    def courant(self):
        it = self.liste.currentItem()
        return it.data(Qt.UserRole) if it else None

    def predefini(self):
        noms = [n for n, _, _ in objets.PREDEFINIS]
        nom, ok = QInputDialog.getItem(self, "Tampon prêt à l'emploi", "Tampon :", noms, 0, False)
        if ok:
            n, t, c = next(x for x in objets.PREDEFINIS if x[0] == nom)
            e = self.b.ajouter("tampons", nom, objets.tampon_predefini(t, c, self.auteur), dynamique=True, texte=t,
                               couleur=list(c))
            self.rafraichir(e)

    def texte_perso(self):
        t, ok = QInputDialog.getText(self, "Tampon personnalisé", "Texte du tampon :")
        if ok and t.strip():
            c = QColorDialog.getColor(QColor("#c9252d"), self, "Couleur du tampon")
            rgb = c.getRgbF()[:3] if c.isValid() else (0.79, 0.15, 0.18)
            e = self.b.ajouter("tampons", t.strip(), objets.tampon_predefini(t.strip().upper(), rgb, self.auteur),
                               dynamique=True, texte=t.strip().upper(), couleur=list(rgb))
            self.rafraichir(e)

    def dessiner(self):
        d = PaveSignature(self)
        if d.exec() == QDialog.Accepted and d.resultat():
            nom, ok = QInputDialog.getText(self, "Nom", "Nom de cette signature :", text="Signature")
            e = self.b.ajouter("signatures", nom if ok and nom else "Signature", d.resultat())
            self.rafraichir(e)

    def importer(self):
        f, _ = QFileDialog.getOpenFileName(self, "Importer", "", "Images et PDF (*.png *.jpg *.jpeg *.bmp *.tif *.pdf)")
        if not f:
            return
        z = SelecteurZone(self, f)
        if z.exec() != QDialog.Accepted:
            return
        nom, ok = QInputDialog.getText(self, "Nom", "Nom :", text=os.path.splitext(os.path.basename(f))[0])
        e = self.b.ajouter(self.genre, nom if ok and nom else "Importé", z.resultat())
        self.rafraichir(e)

    def renommer(self):
        e = self.courant()
        if e:
            nom, ok = QInputDialog.getText(self, "Renommer", "Nouveau nom :", text=e["nom"])
            if ok and nom:
                self.b.renommer(e, nom)
                self.rafraichir(e)

    def supprimer(self):
        e = self.courant()
        if e and QMessageBox.question(self, "Supprimer", f"Supprimer « {e['nom']} » de la bibliothèque ?") == QMessageBox.Yes:
            self.b.supprimer(e)
            self.rafraichir()

    def defaut(self):
        e = self.courant()
        if e:
            self.b.par_defaut(self.genre, e)
            self.rafraichir(e)

    def restaurer(self):
        n = self.b.restaurer_drive()
        QMessageBox.information(self, "Drive", f"{n} élément(s) récupéré(s) depuis la sauvegarde du Drive.")
        self.rafraichir()

    def choisi(self):
        """(element, octets PDF) a poser ; les tampons a date sont regeneres au jour."""
        e = self.courant() or self.b.par_defaut(self.genre)
        if not e:
            return None, None
        if e.get("dynamique"):
            return e, objets.tampon_predefini(e["texte"], tuple(e["couleur"]), self.auteur)
        return e, self.b.lire(e)


# ------------------------------------------------------------------ filigrane
class DialogueFiligrane(QDialog):
    def __init__(self, parent, params, nb_pages, page_courante):
        super().__init__(parent)
        self.params = params
        self.setWindowTitle("Filigrane")
        f = QFormLayout(self)
        self.modele = QComboBox()
        self.modele.addItems(objets.FILIGRANES + params.get("filigranes_perso", []) + ["Texte personnalisé...", "Image..."])
        f.addRow("Modèle", self.modele)
        self.texte = QLineEdit()
        self.texte.setPlaceholderText("Votre texte (sera mémorisé)")
        f.addRow("Texte", self.texte)
        self.image = None
        self.modele.currentTextChanged.connect(self._modele)
        self.date = QCheckBox("Ajouter la date du jour")
        f.addRow(self.date)
        self.coul = QPushButton()
        self.couleur = QColor("#999999")
        self._maj_coul()
        self.coul.clicked.connect(self._choisir_coul)
        f.addRow("Couleur", self.coul)
        self.opa = QSlider(Qt.Horizontal)
        self.opa.setRange(5, 100)
        self.opa.setValue(25)
        f.addRow("Opacité", self.opa)
        self.angle = QSpinBox()
        self.angle.setRange(-90, 90)
        self.angle.setValue(45)
        self.angle.setSuffix(" °")
        f.addRow("Angle", self.angle)
        self.pos = QComboBox()
        self.pos.addItems(["Centre (en diagonale)", "Haut", "Bas"])
        f.addRow("Position", self.pos)
        self.dessous = QCheckBox("Derrière le contenu de la page")
        f.addRow(self.dessous)
        self.pages = QComboBox()
        self.pages.addItems(["Toutes les pages", f"Page courante ({page_courante + 1})"])
        f.addRow("Pages", self.pages)
        self.nb, self.pc = nb_pages, page_courante
        bb = boutons_fr(QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel))
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        f.addRow(bb)
        self._modele(self.modele.currentText())

    def _maj_coul(self):
        self.coul.setStyleSheet(f"background:{self.couleur.name()};min-height:22px;border:1px solid #999;border-radius:4px")

    def _choisir_coul(self):
        c = QColorDialog.getColor(self.couleur, self)
        if c.isValid():
            self.couleur = c
            self._maj_coul()

    def _modele(self, m):
        self.texte.setEnabled(m == "Texte personnalisé...")
        if m == "Image...":
            f, _ = QFileDialog.getOpenFileName(self, "Image du filigrane", "", "Images (*.png *.jpg *.jpeg)")
            self.image = f or None

    def appliquer(self, doc):
        m = self.modele.currentText()
        texte = None
        if m == "Texte personnalisé...":
            texte = self.texte.text().strip()
            if texte:
                perso = [x for x in self.params.get("filigranes_perso", []) if x != texte] + [texte]
                self.params["filigranes_perso"] = perso[-12:]
                self.params.enregistrer()
        elif m != "Image...":
            texte = m
        if texte and self.date.isChecked():
            texte += " – " + datetime.date.today().strftime("%d/%m/%Y")
        pages = list(range(self.nb)) if self.pages.currentIndex() == 0 else [self.pc]
        objets.appliquer_filigrane(doc, pages, texte=texte, image=self.image if m == "Image..." else None,
                                   couleur=self.couleur.getRgbF()[:3], opacite=self.opa.value() / 100,
                                   angle=self.angle.value(), position=["centre", "haut", "bas"][self.pos.currentIndex()],
                                   dessous=self.dessous.isChecked())


# ------------------------------------------------------------------ en-tete et pied de page
class DialogueEntete(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("En-tête et pied de page")
        f = QFormLayout(self)
        f.addRow(QLabel("Codes : {page} numéro de page, {pages} nombre de pages, {date} date du jour."))
        self.champs = {}
        for cle, lib, defaut in [("hg", "En-tête gauche", ""), ("hc", "En-tête centre", ""), ("hd", "En-tête droite", ""),
                                 ("bg", "Pied gauche", ""), ("bc", "Pied centre", "Page {page} / {pages}"), ("bd", "Pied droite", "")]:
            e = QLineEdit(defaut)
            self.champs[cle] = e
            f.addRow(lib, e)
        self.taille = QSpinBox()
        self.taille.setRange(6, 24)
        self.taille.setValue(9)
        f.addRow("Taille (pt)", self.taille)
        bb = boutons_fr(QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel))
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        f.addRow(bb)

    def appliquer(self, doc):
        date = datetime.date.today().strftime("%d/%m/%Y")
        t = self.taille.value()
        font = fitz.Font("helv")
        for n, page in enumerate(doc):
            R = page.rect
            for cle, e in self.champs.items():
                txt = e.text().format(page=n + 1, pages=len(doc), date=date) if e.text() else ""
                if not txt:
                    continue
                L = font.text_length(txt, fontsize=t)
                x = {"g": 36, "c": (R.width - L) / 2, "d": R.width - 36 - L}[cle[1]]
                y = 24 + t if cle[0] == "h" else R.height - 20
                page.insert_text((x, y), txt, fontname="helv", fontsize=t, color=(0.2, 0.2, 0.2))


# ------------------------------------------------------------------ numerisation
class DialogueNumeriser(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        from moteur import scanner
        self.sc = scanner
        self.setWindowTitle("Numériser")
        self.setMinimumWidth(560)
        v = QVBoxLayout(self)
        f = QFormLayout()
        self.app = QComboBox()
        self.liste = scanner.scanners()
        for i, n in self.liste:
            self.app.addItem(n, i)
        if not self.liste:
            self.app.addItem("Aucun scanner détecté (fenêtre de Windows)", None)
        f.addRow("Scanner", self.app)
        self.source = QComboBox()
        self.source.addItems(["Chargeur, recto-verso", "Chargeur, recto", "Vitre"])
        self.source.setCurrentIndex(1)
        f.addRow("Source", self.source)
        v.addLayout(f)
        g = QGroupBox("Mode")
        gv = QVBoxLayout(g)
        self.modes = QButtonGroup(self)
        for i, (cle, titre, desc) in enumerate([
                ("auto", "Automatique (conseillé)", "Texte en noir et blanc net, logos et photos gardés en couleur"),
                ("nb", "Noir et blanc (monochrome)", "Courriers, factures, contrats : le plus léger"),
                ("gris", "Niveaux de gris", "Tampons, signatures, documents pâles ou tramés"),
                ("couleur", "Couleur", "Photos, plans, documents en couleur")]):
            r = QRadioButton(f"{titre}  —  {desc}")
            r.setProperty("cle", cle)
            if i == 0:
                r.setChecked(True)
            self.modes.addButton(r, i)
            gv.addWidget(r)
        v.addWidget(g)
        h = QHBoxLayout()
        h.addWidget(QLabel("Résolution"))
        self.dpi = QComboBox()
        self.dpi.addItems(["150", "200", "300", "600"])
        self.dpi.setCurrentText("300")
        h.addWidget(self.dpi)
        h.addWidget(QLabel("dpi · 300 conseillé pour la reconnaissance du texte"))
        h.addStretch()
        v.addLayout(h)
        self.ocr = QCheckBox("Reconnaître le texte (OCR français)")
        self.ocr.setChecked(True)
        self.blanches = QCheckBox("Supprimer les pages blanches")
        self.blanches.setChecked(True)
        self.redresser = QCheckBox("Redresser les pages")
        self.redresser.setChecked(True)
        for c in (self.ocr, self.blanches, self.redresser):
            v.addWidget(c)
        self.estimation = QLabel()
        self.estimation.setStyleSheet("background:#f7f7f7;border-radius:8px;padding:10px")
        v.addWidget(self.estimation)
        self.modes.buttonClicked.connect(self._estimer)
        self.dpi.currentTextChanged.connect(self._estimer)
        bb = QDialogButtonBox()
        bb.addButton("Numériser", QDialogButtonBox.AcceptRole)
        bb.addButton("Annuler", QDialogButtonBox.RejectRole)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        self._estimer()

    def mode(self):
        return self.modes.checkedButton().property("cle")

    def _estimer(self, *_):
        m, dpi = self.mode(), int(self.dpi.currentText())
        self.estimation.setText(f"Estimation : <b>≈ {self.sc.estimer_ko(m, dpi)} Ko par page</b> · "
                                f"format conseillé : <b>PDF A4, {self.sc.DPI_CONSEILLE[m]} dpi, mode "
                                f"{'automatique' if m == 'auto' else self.modes.checkedButton().text().split('  ')[0].lower()}</b>")

    def numeriser(self):
        ident = self.app.currentData()
        src = ["recto_verso", "chargeur", "vitre"][self.source.currentIndex()]
        dpi = int(self.dpi.currentText())
        if ident is None:
            images = self.sc.dialogue_windows()
        else:
            images = self.sc.numeriser(ident, self.mode(), dpi, src)
        return self.sc.assembler(images, self.mode(), dpi, self.blanches.isChecked(), self.redresser.isChecked())


# ------------------------------------------------------------------ export
class DialogueExporter(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Exporter")
        f = QFormLayout(self)
        self.format = QComboBox()
        self.format.addItems(["Word (.docx)", "Images JPG", "Images PNG", "Texte (.txt)"])
        f.addRow("Format", self.format)
        self.dpi = QComboBox()
        self.dpi.addItems(["96", "150", "200", "300"])
        self.dpi.setCurrentText("150")
        f.addRow("Résolution des images (dpi)", self.dpi)
        self.qualite = QSpinBox()
        self.qualite.setRange(30, 100)
        self.qualite.setValue(85)
        f.addRow("Qualité JPG", self.qualite)
        bb = boutons_fr(QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel))
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        f.addRow(bb)
