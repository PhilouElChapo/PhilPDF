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
from .langue import _


def _pix_depuis_png(octets, h=56):
    pm = QPixmap()
    pm.loadFromData(octets, "PNG")
    return pm.scaledToHeight(h, Qt.SmoothTransformation) if not pm.isNull() else pm


def boutons_fr(bb):
    """Libelles francais pour les boutons standard."""
    noms = {QDialogButtonBox.Ok: "OK", QDialogButtonBox.Cancel: _('Annuler'), QDialogButtonBox.Save: _('Enregistrer'),
            QDialogButtonBox.Discard: _('Ne pas enregistrer'), QDialogButtonBox.Close: _('Fermer'),
            QDialogButtonBox.Yes: "Oui", QDialogButtonBox.No: "Non", QDialogButtonBox.Apply: _('Appliquer')}
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
        self.setWindowTitle(_('Choisir la zone à importer'))
        self.resize(900, 760)
        self.chemin, self.num, self.zone = chemin, 0, None
        self.est_pdf = chemin.lower().endswith(".pdf")
        self.doc = fitz.open(chemin) if self.est_pdf else None
        v = QVBoxLayout(self)
        aide = QLabel(_('Tracez un rectangle autour du tampon ou de la signature. ')
                      + (_('Les tampons Acrobat trouvés dans le fichier sont proposés ci-dessous.') if self.est_pdf else ""))
        aide.setWordWrap(True)
        v.addWidget(aide)
        h = QHBoxLayout()
        self.tampons = objets.tampons_du_pdf(chemin) if self.est_pdf else []
        if self.tampons:
            h.addWidget(QLabel(_('Tampons du fichier :')))
            for pg, r, nom in self.tampons:
                b = QPushButton(nom)
                b.clicked.connect(lambda _x=False, pg=pg, r=r: self._choisir(pg, r))
                h.addWidget(b)
        h.addStretch()
        if self.est_pdf and len(self.doc) > 1:
            self.pg = QSpinBox()
            self.pg.setRange(1, len(self.doc))
            self.pg.valueChanged.connect(lambda n: (setattr(self, "num", n - 1), self._rendre()))
            h.addWidget(QLabel(_('Page')))
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
        self.transparent = QCheckBox(_('Rendre le fond blanc transparent (pour un scan ou une photo)'))
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
        self.setWindowTitle(_('Dessiner votre signature'))
        self.traits, self.courant = [], None
        v = QVBoxLayout(self)
        v.addWidget(QLabel(_('Signez avec la souris, le pavé tactile ou un stylet.')))
        self.zone = QLabel()
        self.zone.setFixedSize(600, 220)
        self.zone.setStyleSheet("background:#fff;border:1px solid #cfcfcf;border-radius:8px")
        self.zone.mousePressEvent = lambda e: self._ajout(e, True)
        self.zone.mouseMoveEvent = lambda e: self._ajout(e, False)
        v.addWidget(self.zone)
        h = QHBoxLayout()
        self.coul = QComboBox()
        self.coul.addItems([_('Bleu'), _('Noir')])
        h.addWidget(QLabel(_('Encre')))
        h.addWidget(self.coul)
        eff = QPushButton(_('Effacer'))
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
class PanneauBibliotheque(QWidget):
    """Liste des tampons ou des signatures avec ses boutons : sert dans la fenetre « Mes tampons »
    et dans l'onglet Tampons et signatures des Preferences."""
    choisi_double = Signal()

    def __init__(self, parent, biblio, genre, auteur="", compact=False):
        super().__init__(parent)
        self.b, self.genre, self.auteur = biblio, genre, auteur
        v = QHBoxLayout(self) if compact else QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        self.liste = QListWidget()
        self.liste.setViewMode(QListWidget.IconMode)
        self.liste.setIconSize(QSize(150, 50) if compact else QSize(200, 70))
        self.liste.setGridSize(QSize(170, 84) if compact else QSize(220, 110))
        self.liste.setResizeMode(QListWidget.Adjust)
        self.liste.setMovement(QListWidget.Static)
        self.liste.itemDoubleClicked.connect(lambda _x: self.choisi_double.emit())
        v.addWidget(self.liste, 1)
        h = QVBoxLayout() if compact else QHBoxLayout()
        h.setSpacing(4)
        if genre == "tampons":
            b = QPushButton(_("Prêt à l'emploi..."))
            b.setToolTip(_('Payé, Vu, Reçu, Approuvé… datés automatiquement'))
            b.clicked.connect(self.predefini)
            h.addWidget(b)
            b = QPushButton(_('Texte personnalisé...'))
            b.clicked.connect(self.texte_perso)
            h.addWidget(b)
        else:
            b = QPushButton(_('Dessiner...'))
            b.clicked.connect(self.dessiner)
            h.addWidget(b)
        b = QPushButton(_('Importer un fichier...'))
        b.setToolTip(_('Image (PNG, JPG…) ou PDF de ce PC, avec choix de la zone'))
        b.clicked.connect(self.importer)
        h.addWidget(b)
        for txt, f in [(_('Renommer'), self.renommer), (_('Supprimer'), self.supprimer), (_('Par défaut'), self.defaut)]:
            b = QPushButton(txt)
            b.clicked.connect(f)
            h.addWidget(b)
        h.addStretch()
        v.addLayout(h)
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
        noms = [n for n, _x, _x in objets.PREDEFINIS]
        nom, ok = QInputDialog.getItem(self, _("Tampon prêt à l'emploi"), _('Tampon :'), noms, 0, False)
        if ok:
            n, t, c = next(x for x in objets.PREDEFINIS if x[0] == nom)
            e = self.b.ajouter("tampons", nom, objets.tampon_predefini(t, c, self.auteur), dynamique=True, texte=t,
                               couleur=list(c))
            self.rafraichir(e)

    def texte_perso(self):
        d = DialogueTamponTexte(self, self.auteur)
        if d.exec() == QDialog.Accepted and d.texte.text().strip():
            t = d.texte.text().strip().upper()
            rgb = d.couleur.getRgbF()[:3]
            e = self.b.ajouter("tampons", d.texte.text().strip(), objets.tampon_predefini(t, rgb, self.auteur, d.date.isChecked()),
                               dynamique=True, texte=t, couleur=list(rgb), date=d.date.isChecked())
            self.rafraichir(e)

    def dessiner(self):
        d = PaveSignature(self)
        if d.exec() == QDialog.Accepted and d.resultat():
            nom, ok = QInputDialog.getText(self, _('Nom'), _('Nom de cette signature :'), text=_('Signature'))
            e = self.b.ajouter("signatures", nom if ok and nom else _('Signature'), d.resultat())
            self.rafraichir(e)

    def importer(self):
        f, _x = QFileDialog.getOpenFileName(self, _('Importer'), "", _('Images et PDF (*.png *.jpg *.jpeg *.bmp *.tif *.pdf)'))
        if not f:
            return
        z = SelecteurZone(self, f)
        if z.exec() != QDialog.Accepted:
            return
        nom, ok = QInputDialog.getText(self, _('Nom'), _('Nom :'), text=os.path.splitext(os.path.basename(f))[0])
        e = self.b.ajouter(self.genre, nom if ok and nom else _('Importé'), z.resultat())
        self.rafraichir(e)

    def renommer(self):
        e = self.courant()
        if e:
            nom, ok = QInputDialog.getText(self, _('Renommer'), _('Nouveau nom :'), text=e["nom"])
            if ok and nom:
                self.b.renommer(e, nom)
                self.rafraichir(e)

    def supprimer(self):
        e = self.courant()
        if e and QMessageBox.question(self, _('Supprimer'), _('Supprimer « {nom} » de la bibliothèque ?', nom=e['nom'])) == QMessageBox.Yes:
            self.b.supprimer(e)
            self.rafraichir()

    def defaut(self):
        e = self.courant()
        if e:
            self.b.par_defaut(self.genre, e)
            self.rafraichir(e)

    def synchroniser(self):
        r = self.b.synchroniser_drive()
        if r is None:
            QMessageBox.information(self, "Drive", _("Choisissez d'abord votre Drive (Préférences › Drive et dossiers)."))
        else:
            QMessageBox.information(self, "Drive", _('{x} élément(s) reçu(s) de vos autres postes, {x2} envoyé(s) sur le Drive.', x=r[0], x2=r[1]))
        self.rafraichir()

    def choisi(self):
        """(element, octets PDF) a poser ; les tampons a date sont regeneres au jour."""
        e = self.courant() or self.b.par_defaut(self.genre)
        if not e:
            return None, None
        if e.get("dynamique"):
            pdf = tampon_a_poser(self, e, self.auteur)
            return (e, pdf) if pdf else (None, None)
        return e, self.b.lire(e)


def tampon_a_poser(parent, e, auteur=""):
    """PDF du tampon a poser. Tampon date : on demande la date (du jour, autre, ou aucune). None si abandon."""
    if not e.get("date", True):
        return objets.tampon_predefini(e["texte"], tuple(e["couleur"]), auteur, False)
    d = DialogueDateTampon(parent, e, auteur)
    if d.exec() != QDialog.Accepted:
        return None
    return objets.tampon_predefini(e["texte"], tuple(e["couleur"]), auteur, d.date_choisie())


class DialogueDateTampon(QDialog):
    """Au moment de poser un tampon date : date du jour (par defaut), autre date ou sans date ; apercu."""
    memoire = "jour"

    def __init__(self, parent, e, auteur=""):
        super().__init__(parent)
        from PySide6.QtWidgets import QDateEdit
        from PySide6.QtCore import QDate
        self.e, self.auteur = e, auteur
        self.setWindowTitle(_("Date du tampon « {nom} »", nom=e.get("nom", "")))
        self.setMinimumWidth(380)
        v = QVBoxLayout(self)
        self.r_jour = QRadioButton(_("Date du jour ({date})", date=datetime.date.today().strftime("%d/%m/%Y")))
        self.r_autre = QRadioButton(_("Autre date :"))
        self.r_sans = QRadioButton(_("Sans date"))
        self.quand = QDateEdit(QDate.currentDate())
        self.quand.setCalendarPopup(True)
        self.quand.setDisplayFormat("dd/MM/yyyy")
        v.addWidget(self.r_jour)
        h = QHBoxLayout()
        h.addWidget(self.r_autre)
        h.addWidget(self.quand)
        h.addStretch()
        v.addLayout(h)
        v.addWidget(self.r_sans)
        {"jour": self.r_jour, "autre": self.r_autre, "sans": self.r_sans}[DialogueDateTampon.memoire].setChecked(True)
        self.apercu = QLabel()
        self.apercu.setAlignment(Qt.AlignCenter)
        self.apercu.setMinimumHeight(90)
        self.apercu.setStyleSheet("background:#fff;border:1px solid #e5e5e5;border-radius:6px")
        v.addWidget(self.apercu)
        bb = boutons_fr(QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel))
        bb.button(QDialogButtonBox.Ok).setText(_("Poser"))
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        for r in (self.r_jour, self.r_autre, self.r_sans):
            r.toggled.connect(self._maj)
        self.quand.dateChanged.connect(lambda *_a: (self.r_autre.setChecked(True), self._maj()))
        self._maj()

    def date_choisie(self):
        if self.r_sans.isChecked():
            return None
        if self.r_autre.isChecked():
            q = self.quand.date()
            return datetime.date(q.year(), q.month(), q.day())
        return True

    def _maj(self, *_a):
        DialogueDateTampon.memoire = "sans" if self.r_sans.isChecked() else "autre" if self.r_autre.isChecked() else "jour"
        pdf = objets.tampon_predefini(self.e["texte"], tuple(self.e["couleur"]), self.auteur, self.date_choisie())
        self.apercu.setPixmap(_pix_depuis_png(objets.apercu(pdf, 70), 70))


class DialogueTamponTexte(QDialog):
    """Nouveau tampon texte : texte, couleur, et date en option (choisie a la pose)."""

    def __init__(self, parent, auteur=""):
        super().__init__(parent)
        self.auteur = auteur
        self.setWindowTitle(_('Tampon personnalisé'))
        f = QFormLayout(self)
        self.texte = QLineEdit()
        self.texte.setPlaceholderText(_("ex. SAISI, A TRAITER, TRANSMIS"))
        f.addRow(_('Texte du tampon :'), self.texte)
        self.couleur = QColor("#c9252d")
        self.b_coul = QPushButton()
        self.b_coul.clicked.connect(self._coul)
        f.addRow(_('Couleur'), self.b_coul)
        self.date = QCheckBox(_("Tampon daté (la date est choisie au moment de le poser)"))
        f.addRow(self.date)
        self.apercu = QLabel()
        self.apercu.setAlignment(Qt.AlignCenter)
        self.apercu.setMinimumHeight(90)
        self.apercu.setStyleSheet("background:#fff;border:1px solid #e5e5e5;border-radius:6px")
        f.addRow(self.apercu)
        bb = boutons_fr(QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel))
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        f.addRow(bb)
        self.texte.textChanged.connect(self._maj)
        self.date.toggled.connect(self._maj)
        self._maj()

    def _coul(self):
        c = QColorDialog.getColor(self.couleur, self, _('Couleur du tampon'))
        if c.isValid():
            self.couleur = c
            self._maj()

    def _maj(self, *_a):
        self.b_coul.setStyleSheet(f"background:{self.couleur.name()};min-height:22px;border:1px solid #999;border-radius:4px")
        t = self.texte.text().strip().upper() or _("TAMPON")
        pdf = objets.tampon_predefini(t, self.couleur.getRgbF()[:3], self.auteur, self.date.isChecked())
        self.apercu.setPixmap(_pix_depuis_png(objets.apercu(pdf, 70), 70))


class DialogueBibliotheque(QDialog):
    """Fenetre « Mes tampons » / « Mes signatures »."""

    def __init__(self, parent, biblio, genre, auteur=""):
        super().__init__(parent)
        self.setWindowTitle(_('Mes tampons') if genre == "tampons" else _('Mes signatures'))
        self.resize(760, 520)
        v = QVBoxLayout(self)
        info = QLabel(_('Rangés sur ce PC') + (_(' et synchronisés avec le Drive (vos autres postes les reçoivent).') if biblio.params.get("drive") else
                                            _('. Indiquez votre Drive dans Préférences pour les retrouver sur vos autres PC.')))
        info.setStyleSheet("color:#555")
        v.addWidget(info)
        self.panneau = PanneauBibliotheque(self, biblio, genre, auteur)
        self.panneau.choisi_double.connect(self.accept)
        v.addWidget(self.panneau, 1)
        bb = QDialogButtonBox()
        if biblio.params.get("drive"):
            b = bb.addButton(_(' Synchroniser avec le Drive'), QDialogButtonBox.ActionRole)
            b.setIcon(icone("synchro", "#0f6cbd"))
            b.clicked.connect(self.panneau.synchroniser)
        self.b_utiliser = bb.addButton(_('Utiliser'), QDialogButtonBox.AcceptRole)
        self.b_utiliser.setDefault(True)
        bb.addButton(_('Fermer'), QDialogButtonBox.RejectRole)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        self.liste = self.panneau.liste

    def courant(self):
        return self.panneau.courant()

    def choisi(self):
        return self.panneau.choisi()

    def rafraichir(self, choisir=None):
        self.panneau.rafraichir(choisir)


# ------------------------------------------------------------------ filigrane
class Apercu(QLabel):
    """Apercu en direct (WYSIWYG) : la page courante du document, avec la modification appliquee
    sur une copie. Rien n'est change dans le document tant qu'on n'a pas valide."""

    def __init__(self, doc, num, appliquer, largeur=320):
        super().__init__()
        self.doc, self.num, self.appliquer, self.largeur = doc, num, appliquer, largeur
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(largeur + 16, int(largeur * 1.414) + 16)
        self.setStyleSheet("background:#e6e6e6;border-radius:6px")
        from PySide6.QtCore import QTimer
        self._t = QTimer(self)
        self._t.setSingleShot(True)
        self._t.timeout.connect(self._rendre)

    def maj(self, *_x):
        self._t.start(120)

    def _rendre(self):
        if self.doc is None:
            return
        tmp = fitz.open()
        tmp.insert_pdf(self.doc, from_page=self.num, to_page=self.num)
        try:
            self.appliquer(tmp)
        except Exception:
            pass
        page = tmp[0]
        k = min(self.largeur / page.rect.width, self.largeur * 1.414 / page.rect.height)
        pm = page.get_pixmap(matrix=fitz.Matrix(k, k), alpha=False)
        img = QImage(pm.samples, pm.width, pm.height, pm.stride, QImage.Format_RGB888).copy()
        self.setPixmap(QPixmap.fromImage(img))


def _avec_apercu(dlg, form_widget, apercu):
    """Formulaire a gauche, apercu a droite."""
    h = QHBoxLayout(dlg)
    form_widget.setMinimumWidth(380)
    h.addWidget(form_widget, 1)
    v = QVBoxLayout()
    t = QLabel(_('Aperçu'))
    t.setStyleSheet("color:#616161;font-weight:600")
    v.addWidget(t)
    v.addWidget(apercu)
    v.addStretch()
    h.addLayout(v)


class DialogueFiligrane(QDialog):
    def __init__(self, parent, params, nb_pages, page_courante, doc=None):
        super().__init__(parent)
        self.params = params
        self.setWindowTitle(_('Filigrane'))
        corps = QWidget()
        f = QFormLayout(corps)
        f.setContentsMargins(0, 0, 0, 0)
        self.modele = QComboBox()
        self.modele.addItems(objets.FILIGRANES + params.get("filigranes_perso", []) + [_('Texte personnalisé...'), _('Image...')])
        f.addRow(_('Modèle'), self.modele)
        self.texte = QLineEdit()
        self.texte.setPlaceholderText(_('Votre texte (sera mémorisé)'))
        f.addRow(_('Texte'), self.texte)
        self.image = None
        self.modele.currentTextChanged.connect(self._modele)
        self.date = QCheckBox(_('Ajouter la date du jour'))
        f.addRow(self.date)
        self.coul = QPushButton()
        self.couleur = QColor("#999999")
        self._maj_coul()
        self.coul.clicked.connect(self._choisir_coul)
        f.addRow(_('Couleur'), self.coul)
        self.opa = QSlider(Qt.Horizontal)
        self.opa.setRange(5, 100)
        self.opa.setValue(25)
        f.addRow(_('Opacité'), self.opa)
        self.angle = QSpinBox()
        self.angle.setRange(-90, 90)
        self.angle.setValue(45)
        self.angle.setSuffix(" °")
        f.addRow(_('Angle'), self.angle)
        self.pos = QComboBox()
        self.pos.addItems([_('Centre (en diagonale)'), _('Haut'), _('Bas')])
        f.addRow(_('Position'), self.pos)
        self.dessous = QCheckBox(_('Derrière le contenu de la page'))
        f.addRow(self.dessous)
        self.pages = QComboBox()
        self.pages.addItems([_('Toutes les pages'), _('Page courante ({x})', x=page_courante + 1)])
        f.addRow(_('Pages'), self.pages)
        self.nb, self.pc = nb_pages, page_courante
        bb = boutons_fr(QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel))
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        f.addRow(bb)
        self.apercu = Apercu(doc, page_courante, lambda d: self.appliquer(d, [0]))
        _avec_apercu(self, corps, self.apercu)
        for sig in (self.modele.currentTextChanged, self.texte.textChanged, self.date.toggled, self.opa.valueChanged,
                    self.angle.valueChanged, self.pos.currentIndexChanged, self.dessous.toggled):
            sig.connect(self.apercu.maj)
        self._modele(self.modele.currentText())
        self.apercu.maj()

    def _maj_coul(self):
        self.coul.setStyleSheet(f"background:{self.couleur.name()};min-height:22px;border:1px solid #999;border-radius:4px")

    def _choisir_coul(self):
        c = QColorDialog.getColor(self.couleur, self)
        if c.isValid():
            self.couleur = c
            self._maj_coul()
            self.apercu.maj()

    def _modele(self, m):
        self.texte.setEnabled(m == _("Texte personnalisé..."))
        if m == _("Image..."):
            f, _x = QFileDialog.getOpenFileName(self, _('Image du filigrane'), "", _('Images (*.png *.jpg *.jpeg)'))
            self.image = f or None

    def _texte(self, memoriser=False):
        m = self.modele.currentText()
        texte = None
        if m == _("Texte personnalisé..."):
            texte = self.texte.text().strip() or None
            if texte and memoriser:
                perso = [x for x in self.params.get("filigranes_perso", []) if x != texte] + [texte]
                self.params["filigranes_perso"] = perso[-12:]
                self.params.enregistrer()
        elif m != _("Image..."):
            texte = m
        if texte and self.date.isChecked():
            texte += " – " + datetime.date.today().strftime("%d/%m/%Y")
        return texte

    def appliquer(self, doc, pages=None):
        apercu = pages is not None
        texte = self._texte(memoriser=not apercu)
        m = self.modele.currentText()
        if pages is None:
            pages = list(range(self.nb)) if self.pages.currentIndex() == 0 else [self.pc]
        if not texte and not (m == _("Image...") and self.image):
            return
        objets.appliquer_filigrane(doc, pages, texte=texte, image=self.image if m == _("Image...") else None,
                                   couleur=self.couleur.getRgbF()[:3], opacite=self.opa.value() / 100,
                                   angle=self.angle.value(), position=["centre", "haut", "bas"][self.pos.currentIndex()],
                                   dessous=self.dessous.isChecked())


# ------------------------------------------------------------------ en-tete et pied de page
class DialogueEntete(QDialog):
    def __init__(self, parent, doc=None, page_courante=0):
        super().__init__(parent)
        self.setWindowTitle(_('En-tête et pied de page'))
        corps = QWidget()
        f = QFormLayout(corps)
        f.setContentsMargins(0, 0, 0, 0)
        aide = QLabel(_('Codes : {page} numéro de page, {pages} nombre de pages, {date} date du jour.'))
        aide.setWordWrap(True)
        aide.setStyleSheet("color:#616161")
        f.addRow(aide)
        self.champs = {}
        for cle, lib, defaut in [("hg", _('En-tête gauche'), ""), ("hc", _('En-tête centre'), ""), ("hd", _('En-tête droite'), ""),
                                 ("bg", _('Pied gauche'), ""), ("bc", _('Pied centre'), _('Page {page} / {pages}')), ("bd", _('Pied droite'), "")]:
            e = QLineEdit(defaut)
            self.champs[cle] = e
            f.addRow(lib, e)
        self.taille = QSpinBox()
        self.taille.setRange(6, 24)
        self.taille.setValue(9)
        f.addRow(_('Taille (pt)'), self.taille)
        self.marge = QSpinBox()
        self.marge.setRange(10, 80)
        self.marge.setValue(36)
        self.marge.setSuffix(" pt")
        f.addRow(_('Marge'), self.marge)
        bb = boutons_fr(QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel))
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        f.addRow(bb)
        self.total = len(doc) if doc is not None else 1
        self.apercu = Apercu(doc, page_courante, lambda d: self.appliquer(d, premier=page_courante + 1, total=self.total))
        _avec_apercu(self, corps, self.apercu)
        for e in self.champs.values():
            e.textChanged.connect(self.apercu.maj)
        self.taille.valueChanged.connect(self.apercu.maj)
        self.marge.valueChanged.connect(self.apercu.maj)
        self.apercu.maj()

    def appliquer(self, doc, premier=1, total=None):
        date = datetime.date.today().strftime("%d/%m/%Y")
        t, m = self.taille.value(), self.marge.value()
        total = total or len(doc)
        font = fitz.Font("helv")
        for n, page in enumerate(doc):
            R = page.rect
            for cle, e in self.champs.items():
                try:
                    txt = e.text().format(page=premier + n, pages=total, date=date) if e.text() else ""
                except (KeyError, IndexError, ValueError):
                    txt = e.text()
                if not txt:
                    continue
                L = font.text_length(txt, fontsize=t)
                x = {"g": m, "c": (R.width - L) / 2, "d": R.width - m - L}[cle[1]]
                y = m * 0.66 + t if cle[0] == "h" else R.height - m * 0.55
                page.insert_text((x, y), txt, fontname="helv", fontsize=t, color=(0.2, 0.2, 0.2))


# ------------------------------------------------------------------ arriere-plan
class DialogueFond(QDialog):
    def __init__(self, parent, doc, page_courante):
        super().__init__(parent)
        self.setWindowTitle(_('Arrière-plan'))
        corps = QWidget()
        f = QFormLayout(corps)
        f.setContentsMargins(0, 0, 0, 0)
        self.couleur = QColor("#fff8e1")
        self.coul = QPushButton()
        self.coul.clicked.connect(self._choisir)
        f.addRow(_('Couleur'), self.coul)
        self.pages = QComboBox()
        self.pages.addItems([_('Toutes les pages'), _('Page courante ({x})', x=page_courante + 1)])
        f.addRow(_('Pages'), self.pages)
        self.nb, self.pc = len(doc), page_courante
        bb = boutons_fr(QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel))
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        f.addRow(bb)
        self.apercu = Apercu(doc, page_courante, lambda d: self.appliquer(d, [0]))
        _avec_apercu(self, corps, self.apercu)
        self._maj()

    def _maj(self):
        self.coul.setStyleSheet(f"background:{self.couleur.name()};min-height:22px;border:1px solid #999;border-radius:4px")
        self.apercu.maj()

    def _choisir(self):
        c = QColorDialog.getColor(self.couleur, self, _('Couleur de fond des pages'))
        if c.isValid():
            self.couleur = c
            self._maj()

    def appliquer(self, doc, pages=None):
        if pages is None:
            pages = range(self.nb) if self.pages.currentIndex() == 0 else [self.pc]
        for n in pages:
            p = doc[n]
            p.draw_rect(p.rect, color=None, fill=self.couleur.getRgbF()[:3], overlay=False)


# ------------------------------------------------------------------ numerisation
class DialogueNumeriser(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        from moteur import scanner
        self.sc = scanner
        self.setWindowTitle(_('Numériser'))
        self.setMinimumWidth(560)
        v = QVBoxLayout(self)
        f = QFormLayout()
        self.app = QComboBox()
        self.liste = scanner.scanners()
        for i, n in self.liste:
            self.app.addItem(n, i)
        if not self.liste:
            self.app.addItem(_('Aucun scanner détecté (fenêtre de Windows)'), None)
        f.addRow(_('Scanner'), self.app)
        self.source = QComboBox()
        self.source.addItems([_('Chargeur, recto-verso'), _('Chargeur, recto'), _('Vitre')])
        self.source.setCurrentIndex(1)
        f.addRow(_('Source'), self.source)
        v.addLayout(f)
        g = QGroupBox(_('Mode'))
        gv = QVBoxLayout(g)
        self.modes = QButtonGroup(self)
        for i, (cle, titre, desc) in enumerate([
                ("auto", _('Automatique (conseillé)'), _('Texte en noir et blanc net, logos et photos gardés en couleur')),
                ("nb", _('Noir et blanc (monochrome)'), _('Courriers, factures, contrats : le plus léger')),
                ("gris", _('Niveaux de gris'), _('Tampons, signatures, documents pâles ou tramés')),
                ("couleur", _('Couleur'), _('Photos, plans, documents en couleur'))]):
            r = QRadioButton(f"{titre}  —  {desc}")
            r.setProperty("cle", cle)
            if i == 0:
                r.setChecked(True)
            self.modes.addButton(r, i)
            gv.addWidget(r)
        v.addWidget(g)
        h = QHBoxLayout()
        h.addWidget(QLabel(_('Résolution')))
        self.dpi = QComboBox()
        self.dpi.addItems(["150", "200", "300", "600"])
        self.dpi.setCurrentText("300")
        h.addWidget(self.dpi)
        h.addWidget(QLabel(_('dpi · 300 conseillé pour la reconnaissance du texte')))
        h.addStretch()
        v.addLayout(h)
        self.ocr = QCheckBox(_('Reconnaître le texte (OCR français)'))
        self.ocr.setChecked(True)
        self.blanches = QCheckBox(_('Supprimer les pages blanches'))
        self.blanches.setChecked(True)
        self.redresser = QCheckBox(_('Redresser les pages'))
        self.redresser.setChecked(True)
        for c in (self.ocr, self.blanches, self.redresser):
            v.addWidget(c)
        self.estimation = QLabel()
        self.estimation.setStyleSheet("background:#f7f7f7;border-radius:8px;padding:10px")
        v.addWidget(self.estimation)
        self.modes.buttonClicked.connect(self._estimer)
        self.dpi.currentTextChanged.connect(self._estimer)
        bb = QDialogButtonBox()
        bb.addButton(_('Numériser'), QDialogButtonBox.AcceptRole)
        bb.addButton(_('Annuler'), QDialogButtonBox.RejectRole)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        self._estimer()

    def mode(self):
        return self.modes.checkedButton().property("cle")

    def _estimer(self, *_x):
        m, dpi = self.mode(), int(self.dpi.currentText())
        self.estimation.setText(_('Estimation : <b>≈ {estimer_ko} Ko par page</b> · format conseillé : <b>PDF A4, {x} dpi, mode {x2}</b>', estimer_ko=self.sc.estimer_ko(m, dpi), x=self.sc.DPI_CONSEILLE[m], x2='automatique' if m == 'auto' else self.modes.checkedButton().text().split('  ')[0].lower()))

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
        self.setWindowTitle(_('Exporter'))
        f = QFormLayout(self)
        self.format = QComboBox()
        self.format.addItems([_('Word (.docx)'), _('Images JPG'), _('Images PNG'), _('Texte (.txt)')])
        f.addRow(_('Format'), self.format)
        self.dpi = QComboBox()
        self.dpi.addItems(["96", "150", "200", "300"])
        self.dpi.setCurrentText("150")
        f.addRow(_('Résolution des images (dpi)'), self.dpi)
        self.qualite = QSpinBox()
        self.qualite.setRange(30, 100)
        self.qualite.setValue(85)
        f.addRow(_('Qualité JPG'), self.qualite)
        bb = boutons_fr(QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel))
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        f.addRow(bb)


# ------------------------------------------------------------------ synchronisation des sessions
from PySide6.QtCore import QThread
from PySide6.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView


class TacheRecherche(QThread):
    """Recherche en cascade en arriere-plan ; `etape` a chaque fichier resolu."""
    etape = Signal(int, str, str)          # indice, chemin trouve ("" si non), comment
    fini = Signal(list)

    def __init__(self, session, machine, fichiers, delai=None):
        super().__init__()
        self.s, self.machine, self.fichiers, self.delai, self.stop = session, machine, fichiers, delai, False

    def run(self):
        res = self.s.retrouver_tous(self.machine, self.fichiers, arret=lambda: self.stop, delai=self.delai,
                                    progression=lambda i, c, cm: self.etape.emit(i, c or "", cm))
        self.fini.emit(res)


class DialogueSynchro(QDialog):
    """Synchronisation manuelle : etat de chaque fichier de l'autre poste, designation a la main des
    introuvables (PhilPDF apprend), et table des correspondances de dossiers apprises."""

    def __init__(self, parent, session, machine=None, resultats=None, fichiers_ouverts=0):
        super().__init__(parent)
        from .session import date_fr, nb_fichiers
        self.s, self._df, self._nb = session, date_fr, nb_fichiers
        self.setWindowTitle(_('Synchroniser les fichiers ouverts entre postes'))
        self.resize(900, 520)
        v = QVBoxLayout(self)
        h = QHBoxLayout()
        h.addWidget(QLabel(_('Ce poste : <b>{machine}</b>.  Reprendre les fichiers de :', machine=session.params['machine'])))
        self.machines = QComboBox()
        for m, d, n in session.autres_machines():
            self.machines.addItem(_('{m} — {nb}, le {date}', m=m, nb=nb_fichiers(n), date=date_fr(d)), m)
        if machine:
            self.machines.setCurrentIndex(max(0, self.machines.findData(machine)))
        h.addWidget(self.machines, 1)
        v.addLayout(h)
        self.onglets = QTabWidget()
        v.addWidget(self.onglets, 1)
        # --- onglet fichiers
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels([_('Fichier'), _('Emplacement sur ce poste'), _('Comment'), ""])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.verticalHeader().hide()
        self.onglets.addTab(self.table, _('Fichiers'))
        # --- onglet correspondances
        w = QWidget()
        vc = QVBoxLayout(w)
        vc.setContentsMargins(0, 6, 0, 0)
        expl = QLabel(_("Correspondances de dossiers apprises : quand un fichier de l'autre poste est retrouvé ailleurs ici, PhilPDF retient le lien entre les deux dossiers et leur racine commune (ex. C:\\Users\\Phil → C:\\Users\\Autre)."))
        expl.setWordWrap(True)
        expl.setStyleSheet("color:#555")
        vc.addWidget(expl)
        self.corr = QTableWidget(0, 4)
        self.corr.setHorizontalHeaderLabels([_('Poste'), _("Dossier sur l'autre poste"), _('Dossier ici'), ""])
        self.corr.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.corr.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.corr.verticalHeader().hide()
        vc.addWidget(self.corr, 1)
        self.onglets.addTab(w, _('Correspondances apprises'))
        # --- bas
        self.remplacer = QCheckBox(_('Remplacer les fichiers ouverts ici'))
        self.remplacer.setChecked(True)
        self.remplacer.setVisible(fichiers_ouverts > 0)
        v.addWidget(self.remplacer)
        bb = QDialogButtonBox()
        self.b_ouvrir = bb.addButton(_('Ouvrir les fichiers cochés'), QDialogButtonBox.AcceptRole)
        self.b_relancer = bb.addButton(_('Relancer la recherche'), QDialogButtonBox.ActionRole)
        bb.addButton(_('Fermer'), QDialogButtonBox.RejectRole)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        self.b_relancer.clicked.connect(lambda: self.charger(None))
        v.addWidget(bb)
        self.t = None
        self.machines.currentIndexChanged.connect(lambda _x: self.charger(None))
        self.remplir_corr()
        self.charger(resultats)

    # ------------------------------------------------------------ fichiers
    def machine(self):
        return self.machines.currentData()

    def charger(self, resultats):
        self._arreter()
        m = self.machine()
        self.fichiers = self.s.lire().get(m, {}).get("fichiers", []) if m else []
        self.date = self._df(self.s.lire().get(m, {}).get("maj", "")) if m else ""
        self.trouves = {}
        self.table.setRowCount(len(self.fichiers))
        for i, e in enumerate(self.fichiers):
            it = QTableWidgetItem(e["nom"])
            it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Unchecked)
            it.setToolTip(_('Sur {m} : {chemin}', m=m, chemin=e['chemin']))
            self.table.setItem(i, 0, it)
            self.table.setItem(i, 1, QTableWidgetItem(_("recherche...")))
            self.table.setItem(i, 2, QTableWidgetItem(""))
            b = QPushButton(_('Désigner...'))
            b.setToolTip(_('Indiquer à la main où est ce fichier sur ce poste ; PhilPDF retiendra le dossier'))
            b.clicked.connect(lambda _x=False, i=i: self.designer(i))
            self.table.setCellWidget(i, 3, b)
        if resultats is not None and len(resultats) == len(self.fichiers):
            for i, (c, cm) in enumerate(resultats):
                self._etape(i, c or "", cm)
        elif self.fichiers:
            self.t = TacheRecherche(self.s, m, self.fichiers)
            self.t.etape.connect(self._etape)
            self.t.start()
        self.table.resizeColumnToContents(0)

    def _etape(self, i, chemin, comment):
        if i >= self.table.rowCount():
            return
        gris, vert = QColor("#999999"), QColor("#1d5a2b")
        if chemin:
            self.trouves[i] = chemin
            self.table.item(i, 0).setCheckState(Qt.Checked)
            self.table.item(i, 1).setText(chemin)
            self.table.item(i, 2).setText(comment)
            for c in (0, 1, 2):
                self.table.item(i, c).setForeground(vert)
        elif comment:
            self.table.item(i, 1).setText(_('introuvable sur {machine} (ouvert sur {machine2} le {date})', machine=self.s.params['machine'], machine2=self.machine(), date=self.date))
            self.table.item(i, 2).setText(_("recherche limitée") if comment == _("introuvable (recherche limitée)") else "")
            for c in (0, 1, 2):
                self.table.item(i, c).setForeground(gris)
        else:
            self.table.item(i, 1).setText(_("recherche..."))

    def designer(self, i):
        from .session import empreinte
        e = self.fichiers[i]
        f, _x = QFileDialog.getOpenFileName(self, _('Où est « {nom} » sur ce poste ?', nom=e['nom']), "", _('PDF (*.pdf);;Tous (*)'))
        if not f:
            return
        if e.get("empreinte") and empreinte(f) != e["empreinte"]:
            if QMessageBox.question(self, _('Synchroniser'), _("Ce fichier n'a pas le même contenu que celui ouvert sur {machine}. L'utiliser quand même ?", machine=self.machine())) != QMessageBox.Yes:
                return
        self.s.apprendre_depuis(self.machine(), e, f)
        self._etape(i, f, _('désigné à la main (appris)'))
        self.remplir_corr()

    # ------------------------------------------------------------ correspondances
    def remplir_corr(self):
        lignes = self.s.correspondances()
        self.corr.setRowCount(len(lignes))
        for r, (m, a, b) in enumerate(lignes):
            for c, t in enumerate((m, a, b)):
                self.corr.setItem(r, c, QTableWidgetItem(t))
            bo = QPushButton(_('Oublier'))
            bo.clicked.connect(lambda _x=False, m=m, a=a: (self.s.oublier(m, a), self.remplir_corr()))
            self.corr.setCellWidget(r, 3, bo)
        self.corr.resizeColumnToContents(0)

    # ------------------------------------------------------------ resultat
    def choisis(self):
        """[(chemin, page, zoom)] a ouvrir ; les correspondances trouvees sont apprises."""
        out = []
        for i, c in sorted(self.trouves.items()):
            if self.table.item(i, 0).checkState() == Qt.Checked:
                e = self.fichiers[i]
                self.s.apprendre_depuis(self.machine(), e, c)
                out.append((c, e.get("page", 0), e.get("zoom")))
        return out

    def _arreter(self):
        if self.t:
            self.t.stop = True
            self.t.wait(3000)
            self.t = None

    def done(self, r):
        self._arreter()
        super().done(r)
