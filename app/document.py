"""Onglet d'un fichier ouvert : visionneuse, vignettes, selection, barre rapide,
mode Modifier facon Acrobat (deplacer, editer dans la page), objets deplacables
(tampons, signatures, annotations), organisation des pages."""
import os
import pymupdf as fitz
from PySide6.QtCore import Qt, Signal, QRectF, QPointF, QTimer, QSize, QPoint
from PySide6.QtGui import QImage, QPainter, QColor, QPen, QPixmap, QGuiApplication, QFont, QIcon
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QFrame, QLabel, QToolButton,
                               QListWidget, QListWidgetItem, QSplitter, QPushButton, QInputDialog, QMenu,
                               QMessageBox, QLineEdit, QDialog, QDialogButtonBox, QCheckBox, QFormLayout,
                               QAbstractItemView, QComboBox, QSpinBox, QStackedWidget, QColorDialog, QFileDialog,
                               QDoubleSpinBox)
from .icones import icone
from .outils import outil, famille
from .dialogues import boutons_fr, DialogueBibliotheque
from moteur.modifier import Editeur, CANDIDATS
from moteur import objets

ECRAN = 96 / 72                 # points PDF -> pixels a 100 %
POIGNEE = 8                      # taille des poignees (pixels)
DEPLACABLES = (fitz.PDF_ANNOT_STAMP, fitz.PDF_ANNOT_FREE_TEXT, fitz.PDF_ANNOT_TEXT, fitz.PDF_ANNOT_INK,
               fitz.PDF_ANNOT_SQUARE, fitz.PDF_ANNOT_CIRCLE, fitz.PDF_ANNOT_LINE)


def question(parent, titre, texte, boutons):
    """Boite de question en francais. boutons = [(libelle, role)] ; renvoie l'indice clique."""
    m = QMessageBox(parent)
    m.setWindowTitle(titre)
    m.setText(texte)
    bs = [m.addButton(lib, role) for lib, role in boutons]
    m.exec()
    return bs.index(m.clickedButton()) if m.clickedButton() in bs else len(bs) - 1


# ================================================================ page
class PageWidget(QWidget):
    def __init__(self, onglet, num):
        super().__init__()
        self.o, self.num = onglet, num
        self.image, self.image_zoom = None, None
        self.survol = None
        self.glisse = None
        self.editeur = None
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.ClickFocus)
        self.maj_taille()

    # ---- geometrie
    def rect_page(self):
        r = self.o.doc[self.num].rect
        rot = self.o.rotation_vue.get(self.num, 0)
        return (r.height, r.width) if rot in (90, 270) else (r.width, r.height)

    def echelle(self):
        return self.o.zoom * ECRAN

    def maj_taille(self):
        w, h = self.rect_page()
        e = self.echelle()
        self.setFixedSize(int(w * e), int(h * e))
        self.image = None

    def _mat_affichage(self):
        page = self.o.doc[self.num]
        m = fitz.Matrix(self.echelle(), self.echelle()).prerotate(self.o.rotation_vue.get(self.num, 0))
        r = page.rect * m
        return m * fitz.Matrix(1, 0, 0, 1, -r.x0, -r.y0)

    def _mat_texte(self):
        return self.o.doc[self.num].rotation_matrix * self._mat_affichage()

    def vers_pdf(self, pos):
        return fitz.Point(pos.x(), pos.y()) * ~self._mat_texte()

    def vers_ecran(self, rect):
        r = fitz.Rect(rect) * self._mat_texte()
        r.normalize()
        return QRectF(r.x0, r.y0, r.width, r.height)

    # ---- dessin
    def paintEvent(self, ev):
        p = QPainter(self)
        if self.image is None or self.image_zoom != self.o.zoom:
            dpr = self.devicePixelRatioF()
            pm = self.o.doc[self.num].get_pixmap(matrix=self._mat_affichage() * fitz.Matrix(dpr, dpr), alpha=False)
            img = QImage(pm.samples, pm.width, pm.height, pm.stride, QImage.Format_RGB888).copy()
            img.setDevicePixelRatio(dpr)
            self.image, self.image_zoom = img, self.o.zoom
        p.drawImage(0, 0, self.image)
        o = self.o
        sel = o.selection
        if sel and sel["page"] == self.num:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(20, 98, 194, 70))
            for r in sel["lignes"]:
                p.drawRect(self.vers_ecran(r))
        for (pg, r) in o.resultats:
            if pg == self.num:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(255, 210, 0, 110) if (pg, r) != o.resultat_courant else QColor(255, 140, 0, 150))
                p.drawRect(self.vers_ecran(r))
        if o.mode == "modifier":
            for r, _t in o.lignes_page(self.num):
                actif = self.survol is not None and fitz.Rect(r).contains(self.survol)
                p.setPen(QPen(QColor("#1462c2"), 2 if actif else 1, Qt.SolidLine if actif else Qt.DotLine))
                p.setBrush(QColor(20, 98, 194, 25) if actif else Qt.NoBrush)
                p.drawRect(self.vers_ecran(fitz.Rect(r) + (-1.5, -1, 1.5, 1)))
            for xref, r in o.images_page(self.num):
                p.setPen(QPen(QColor("#a35c00"), 1, Qt.DotLine))
                p.setBrush(Qt.NoBrush)
                p.drawRect(self.vers_ecran(r))
        obj = o.objet
        if obj and obj["page"] == self.num and not self.editeur:
            r = self.vers_ecran(obj["rect"])
            p.setPen(QPen(QColor("#1462c2"), 1.5))
            p.setBrush(Qt.NoBrush)
            p.drawRect(r)
            p.setBrush(QColor("#ffffff"))
            for c in self._poignees(r):
                p.drawRect(c)
        if self.glisse and self.glisse.get("fantome") is not None:
            p.setPen(QPen(QColor("#1462c2"), 1.5, Qt.DashLine))
            p.setBrush(QColor(20, 98, 194, 30))
            p.drawRect(self.vers_ecran(self.glisse["fantome"]))
        p.end()

    def _poignees(self, r):
        h = POIGNEE / 2
        return [QRectF(x - h, y - h, POIGNEE, POIGNEE) for x, y in
                ((r.left(), r.top()), (r.right(), r.top()), (r.left(), r.bottom()), (r.right(), r.bottom()))]

    def _sur_poignee(self, pos):
        obj = self.o.objet
        if not obj or obj["page"] != self.num or obj["type"] == "ligne":
            return None
        for i, c in enumerate(self._poignees(self.vers_ecran(obj["rect"]))):
            if c.adjusted(-3, -3, 3, 3).contains(pos):
                return i
        return None

    # ---- souris
    def mousePressEvent(self, e):
        o = self.o
        o.barre_rapide.hide()
        if self.editeur:
            self.editeur.valider()
        pt = self.vers_pdf(e.position())
        if e.button() == Qt.RightButton:
            o.menu_contexte(self, pt, e.globalPosition().toPoint())
            return
        if e.button() != Qt.LeftButton:
            return
        if o.mode == "poser":
            o.poser_objet(self.num, pt)
            return
        if o.mode == "ajout_texte":
            self.ouvrir_editeur(None, pt)
            return
        if o.mode == "ajout_image":
            o.ajouter_image_ici(self.num, pt)
            return
        if o.mode in ("lien", "recadrer"):
            self.glisse = {"genre": "zone", "debut": pt, "fantome": fitz.Rect(pt, pt)}
            return
        poignee = self._sur_poignee(e.position())
        if poignee is not None:
            self.glisse = {"genre": "redim", "coin": poignee, "debut": pt, "rect0": fitz.Rect(o.objet["rect"]), "fantome": None}
            return
        trouve = o.objet_sous(self.num, pt)
        if trouve:
            o.choisir_objet(trouve)
            self.glisse = {"genre": "deplacer", "debut": pt, "rect0": fitz.Rect(trouve["rect"]), "fantome": None}
            return
        o.choisir_objet(None)
        if o.mode is None:
            o.debut_selection(self.num, pt)

    def mouseMoveEvent(self, e):
        o = self.o
        pt = self.vers_pdf(e.position())
        g = self.glisse
        if g and e.buttons() & Qt.LeftButton:
            d = pt - g["debut"]
            if g["genre"] == "zone":
                g["fantome"] = fitz.Rect(g["debut"], pt).normalize()
            elif g["genre"] == "deplacer":
                if abs(d.x) + abs(d.y) > 2:
                    g["fantome"] = g["rect0"] + (d.x, d.y, d.x, d.y)
            elif g["genre"] == "redim":
                r = fitz.Rect(g["rect0"])
                if g["coin"] in (1, 3):
                    r.x1 += d.x
                else:
                    r.x0 += d.x
                if o.objet.get("garder_proportions", True):
                    k = r.width / max(1, g["rect0"].width)
                    if g["coin"] in (2, 3):
                        r.y1 = r.y0 + g["rect0"].height * k
                    else:
                        r.y0 = r.y1 - g["rect0"].height * k
                else:
                    if g["coin"] in (2, 3):
                        r.y1 += d.y
                    else:
                        r.y0 += d.y
                g["fantome"] = r.normalize()
            self.update()
            return
        if o.mode is None and e.buttons() & Qt.LeftButton and o.selection:
            o.etendre_selection(self.num, pt)
            return
        # curseurs
        self.survol = pt
        if self._sur_poignee(e.position()) is not None:
            self.setCursor(Qt.SizeFDiagCursor)
        elif o.objet_sous(self.num, pt, survol=True):
            self.setCursor(Qt.SizeAllCursor)
        elif o.mode in ("poser", "ajout_texte", "ajout_image", "lien", "recadrer"):
            self.setCursor(Qt.CrossCursor)
        elif o.mode is None and o.mot_sous(self.num, pt) is not None:
            self.setCursor(Qt.IBeamCursor)
        else:
            self.setCursor(Qt.ArrowCursor)
        if o.mode == "modifier":
            self.update()

    def mouseReleaseEvent(self, e):
        o = self.o
        g, self.glisse = self.glisse, None
        if g:
            if g["genre"] == "zone" and g["fantome"] is not None and g["fantome"].width > 4:
                o.zone_tracee(self.num, g["fantome"])
            elif g["genre"] in ("deplacer", "redim") and g["fantome"] is not None:
                o.appliquer_deplacement(g["fantome"])
            self.update()
            return
        if o.mode is None and o.selection and o.selection["page"] == self.num:
            o.montrer_barre_rapide(self)

    def mouseDoubleClickEvent(self, e):
        pt = self.vers_pdf(e.position())
        o = self.o
        if o.mode == "modifier":
            for r, t in o.lignes_page(self.num):
                if fitz.Rect(r).contains(pt):
                    self.ouvrir_editeur(fitz.Rect(r), None, t)
                    return
        obj = o.objet_sous(self.num, pt)
        if obj and obj["type"] == "annot":
            o.editer_annotation(obj)

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Delete, Qt.Key_Backspace) and self.o.objet:
            self.o.supprimer()
        elif e.key() == Qt.Key_Escape:
            self.o.choisir_objet(None)
            self.o.changer_mode(None if self.o.mode != "modifier" else "modifier")
        else:
            super().keyPressEvent(e)

    # ---- edition directe dans la page (WYSIWYG)
    def ouvrir_editeur(self, rect, pt, texte=""):
        self.editeur = EditeurEnLigne(self, rect, pt, texte)


class EditeurEnLigne(QWidget):
    """Champ de saisie pose sur la page, a la taille du texte ; bouton … pour la boite de dialogue."""

    def __init__(self, pw, rect, pt, texte):
        super().__init__(pw)
        self.pw, self.rect, self.pt, self.initial = pw, rect, pt, texte.rstrip()
        o = pw.o
        self.taille = o.format_taille.value() if rect is None else None
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(2)
        self.champ = QLineEdit(self.initial)
        e = pw.echelle()
        if rect is not None:
            r = pw.vers_ecran(rect)
            taille_px = max(9, r.height() * 0.78)
            x, y, w, hh = r.x(), r.y(), max(r.width() + 40, 120), r.height() + 6
        else:
            taille_px = max(9, self.taille * e * 0.95)
            p = fitz.Point(pt) * pw._mat_texte()
            x, y, w, hh = p.x, p.y - taille_px * 1.15, 360, taille_px * 1.6
        f = QFont()
        f.setPixelSize(int(taille_px))
        self.champ.setFont(f)
        self.champ.setStyleSheet("QLineEdit{background:rgba(234,242,253,235);border:1.5px solid #1462c2;border-radius:3px;padding:0 3px}")
        h.addWidget(self.champ, 1)
        plus = QToolButton()
        plus.setText("…")
        plus.setToolTip("Ouvrir la boîte de dialogue (texte, taille, couleur)")
        plus.clicked.connect(self.dialogue)
        h.addWidget(plus)
        self.setGeometry(int(x - 3), int(y - 3), int(w + 30), int(hh))
        self.champ.returnPressed.connect(self.valider)
        self.champ.installEventFilter(self)
        self.show()
        self.champ.setFocus()
        self.champ.selectAll() if rect is None else self.champ.setCursorPosition(len(self.initial))
        self._fini = False

    def eventFilter(self, obj, ev):
        if ev.type() == ev.Type.KeyPress and ev.key() == Qt.Key_Escape:
            self.annuler()
            return True
        return False

    def dialogue(self):
        d = DialogueTexte(self.pw.o, self.champ.text(), self.pw.o)
        if d.exec() == QDialog.Accepted:
            self.champ.setText(d.texte.text())
            self.valider(d.taille.value(), d.couleur.getRgbF()[:3] if d.couleur_modifiee else None, d.police())

    def annuler(self):
        self._fini = True
        self.pw.editeur = None
        self.hide()
        self.deleteLater()
        self.pw.update()

    def valider(self, taille=None, couleur=None, police=None):
        if self._fini:
            return
        self._fini = True
        texte = self.champ.text()
        self.pw.editeur = None
        self.hide()
        self.deleteLater()
        o = self.pw.o
        if self.rect is not None:
            if texte.rstrip() != self.initial or taille or couleur:
                o.modifier_ligne_texte(self.pw.num, self.rect, texte, taille, couleur)
        elif texte.strip():
            o.ajouter_texte(self.pw.num, self.pt, texte, taille or self.taille, couleur, police)
        self.pw.update()


class DialogueTexte(QDialog):
    def __init__(self, parent, texte, onglet):
        super().__init__(parent)
        self.setWindowTitle("Texte")
        f = QFormLayout(self)
        self.texte = QLineEdit(texte)
        self.texte.setMinimumWidth(420)
        f.addRow("Texte", self.texte)
        self.taille = QDoubleSpinBox()
        self.taille.setRange(4, 96)
        self.taille.setValue(onglet.format_taille.value())
        self.taille.setSuffix(" pt")
        f.addRow("Taille", self.taille)
        self.couleur, self.couleur_modifiee = QColor("#000000"), False
        b = QPushButton("Choisir...")
        b.clicked.connect(self._coul)
        f.addRow("Couleur", b)
        self.combo = QComboBox()
        self.combo.addItem("Police du document (automatique)", None)
        for n, fichier in CANDIDATS:
            self.combo.addItem(n, fichier)
        f.addRow("Police", self.combo)
        bb = boutons_fr(QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel))
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        f.addRow(bb)

    def _coul(self):
        c = QColorDialog.getColor(self.couleur, self)
        if c.isValid():
            self.couleur, self.couleur_modifiee = c, True

    def police(self):
        return self.combo.currentData()


# ================================================================ barre rapide
class BarreRapide(QFrame):
    """Actions rapides sur le texte selectionne (comme Office et Acrobat)."""

    def __init__(self, onglet, parent):
        super().__init__(parent)
        self.o = onglet
        self.setObjectName("barre")
        self.setStyleSheet("#barre{background:#2b2b2b;border-radius:8px} QToolButton{color:#fff;padding:4px 6px;border-radius:6px}"
                           "QToolButton:hover{background:#4a4a4a}")
        h = QHBoxLayout(self)
        h.setContentsMargins(6, 4, 6, 4)
        h.setSpacing(2)
        for ic, txt, f in [("surligner", "Surligner", lambda: self.o.annoter("surligner")),
                           ("souligner", "Souligner", lambda: self.o.annoter("souligner")),
                           ("barrer", "Barrer", lambda: self.o.annoter("barrer")),
                           ("commentaire", "Note", lambda: self.o.annoter("note")),
                           ("copier", "Copier", self.o.copier),
                           ("modifier", "Modifier le texte", self.o.modifier_selection),
                           ("biffer", "Biffer (effacer pour de vrai)", self.o.biffer)]:
            b = QToolButton()
            b.setIcon(icone(ic, "#ffffff", 40))
            b.setIconSize(QSize(18, 18))
            b.setToolTip(txt)
            b.setAccessibleName(txt)
            b.setAutoRaise(True)
            b.clicked.connect(f)
            b.clicked.connect(self.hide)
            h.addWidget(b)
        self.hide()


# ================================================================ vignettes / organiser
class GrillePages(QListWidget):
    """Vignettes reordonnables par glisser-deposer (liste ou grille)."""
    ordre_change = Signal(list)

    def __init__(self, grille=False):
        super().__init__()
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)
        if grille:
            self.setViewMode(QListWidget.IconMode)
            self.setFlow(QListWidget.LeftToRight)
            self.setWrapping(True)
            self.setResizeMode(QListWidget.Adjust)
            self.setMovement(QListWidget.Snap)
            self.setIconSize(QSize(150, 200))
            self.setGridSize(QSize(180, 240))
            self.setSpacing(10)
        else:
            self.setViewMode(QListWidget.ListMode)
            self.setIconSize(QSize(96, 128))
            self.setSpacing(4)

    def dropEvent(self, ev):
        # reordonnancement fait a la main : fiable en liste comme en grille
        cible = self.indexAt(ev.position().toPoint()).row()
        choisis = sorted(self.row(i) for i in self.selectedItems())
        if not choisis:
            return
        ordre = [self.item(i).data(Qt.UserRole) for i in range(self.count())]
        if cible < 0:
            cible = len(ordre)
        else:
            r = self.visualItemRect(self.item(cible))
            p = ev.position().toPoint()
            apres = p.x() > r.center().x() if self.viewMode() == QListWidget.IconMode else p.y() > r.center().y()
            cible += 1 if apres else 0
        bouges = [ordre[i] for i in choisis]
        reste = [x for i, x in enumerate(ordre) if i not in choisis]
        pos = cible - sum(1 for i in choisis if i < cible)
        nouvel = reste[:pos] + bouges + reste[pos:]
        ev.setDropAction(Qt.IgnoreAction)
        ev.accept()
        if nouvel != ordre:
            self.ordre_change.emit(nouvel)


# ================================================================ onglet
class OngletDocument(QWidget):
    titre_change = Signal()
    outil_demande = Signal(str)
    statut = Signal(str)

    def __init__(self, params, chemin=None, doc=None, nom=None, biblio=None):
        super().__init__()
        self.params, self.biblio = params, biblio
        self.chemin = chemin
        if doc is None:
            with open(chemin, "rb") as f:
                donnees = f.read()
            doc = fitz.open(stream=donnees, filetype="pdf")
            self.poids_initial = len(donnees)
        else:
            self.poids_initial = 0
        self.doc = doc
        self.nom = nom or os.path.basename(chemin or "Sans titre.pdf")
        self.modifie = chemin is None
        self.zoom = params.get("zoom", 1.25)
        self.rotation_vue = {}
        self.selection = None
        self.objet = None
        self.a_poser = None
        self.resultats, self.resultat_courant = [], None
        self.mode = None
        self.annulations, self.retablissements = [], []
        self.chiffrement = None
        self._cache_lignes, self._cache_mots, self._cache_images = {}, {}, {}
        self.objets_pdf = {}       # xref annotation -> (pdf, nom, genre) pour copier/coller
        self._construire()

    # ------------------------------------------------------------ interface
    def _construire(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        self.barre = self._barre_outils()
        v.addWidget(self.barre)
        v.addWidget(self._bandeau_modifier())
        self.bandeau_simple = QLabel()
        self.bandeau_simple.setStyleSheet("background:#f1ebfc;color:#3f2380;padding:8px 16px;border-bottom:1px solid #ddd0f6")
        self.bandeau_simple.hide()
        v.addWidget(self.bandeau_simple)
        self.sp = QSplitter()
        self.sp.setChildrenCollapsible(True)
        self.vignettes = GrillePages()
        self.vignettes.setMinimumWidth(110)
        self.vignettes.setStyleSheet("QListWidget{background:#fafafa;border:none;border-right:1px solid #e2e2e2}")
        self.vignettes.itemClicked.connect(lambda it: self.aller_a(it.data(Qt.UserRole)))
        self.vignettes.setContextMenuPolicy(Qt.CustomContextMenu)
        self.vignettes.customContextMenuRequested.connect(lambda p: self._menu_pages(self.vignettes, p))
        self.vignettes.ordre_change.connect(self.reordonner)
        self.sp.addWidget(self.vignettes)
        self.centre = QStackedWidget()
        self.zone = QScrollArea()
        self.zone.setWidgetResizable(True)
        self.zone.setStyleSheet("QScrollArea{background:#e6e6e6;border:none}")
        self.conteneur = QWidget()
        self.conteneur.setStyleSheet("background:#e6e6e6")
        self.pages_layout = QVBoxLayout(self.conteneur)
        self.pages_layout.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        self.pages_layout.setSpacing(16)
        self.pages_layout.setContentsMargins(24, 20, 24, 30)
        self.zone.setWidget(self.conteneur)
        self.zone.verticalScrollBar().valueChanged.connect(self._page_visible)
        self.centre.addWidget(self.zone)
        self.centre.addWidget(self._vue_organiser())
        self.sp.addWidget(self.centre)
        self.volet = self._volet()
        self.sp.addWidget(self.volet)
        self.sp.setStretchFactor(1, 1)
        self.sp.setSizes([140, 900, 320])
        v.addWidget(self.sp, 1)
        self.barre_rapide = BarreRapide(self, self.zone.viewport())
        self.construire_pages()

    def _bouton(self, ic, txt, f, coul="#333333", aide=None):
        b = QToolButton()
        b.setIcon(icone(ic, coul))
        b.setIconSize(QSize(22, 22))
        b.setText(txt)
        b.setToolTip(aide or txt)
        b.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        b.setAutoRaise(True)
        b.setMinimumWidth(60)
        b.clicked.connect(f)
        return b

    def _barre_outils(self):
        w = QFrame()
        w.setStyleSheet("QFrame{background:#fff;border-bottom:1px solid #e2e2e2} QToolButton{font-size:11px;color:#444}")
        h = QHBoxLayout(w)
        h.setContentsMargins(10, 2, 10, 2)
        h.setSpacing(2)
        h.addWidget(self._bouton("enregistrer", "Enregistrer", lambda: self.outil_demande.emit("enregistrer"), aide="Enregistrer (Ctrl+S)"))
        h.addWidget(self._bouton("imprimer", "Imprimer", lambda: self.outil_demande.emit("imprimer"), aide="Imprimer (Ctrl+P)"))
        h.addWidget(self._bouton("rechercher", "Rechercher", lambda: self.outil_demande.emit("remplacer"), aide="Rechercher et remplacer (Ctrl+F)"))
        h.addWidget(self._bouton("annuler", "Annuler", self.annuler, aide="Annuler (Ctrl+Z)"))
        h.addSpacing(8)
        self.lbl_page = QLabel()
        h.addWidget(self.lbl_page)
        h.addSpacing(8)
        h.addWidget(self._bouton("zoom_moins", "Zoom −", lambda: self.changer_zoom(self.zoom / 1.2)))
        self.lbl_zoom = QLabel()
        self.lbl_zoom.setMinimumWidth(44)
        self.lbl_zoom.setAlignment(Qt.AlignCenter)
        h.addWidget(self.lbl_zoom)
        h.addWidget(self._bouton("zoom_plus", "Zoom +", lambda: self.changer_zoom(self.zoom * 1.2)))
        h.addWidget(self._bouton("pivoter", "Pivoter", self.pivoter_courante, aide="Pivoter la page affichée de 90°"))
        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setStyleSheet("color:#e2e2e2")
        h.addWidget(sep)
        self.zone_favoris = QHBoxLayout()
        self.zone_favoris.setSpacing(2)
        h.addLayout(self.zone_favoris)
        h.addStretch()
        self.b_volet = self._bouton("organiser", "Volet", self.basculer_volet, aide="Afficher / masquer le volet de droite")
        h.addWidget(self.b_volet)
        self.remplir_favoris()
        return w

    def remplir_favoris(self):
        """Outils epingles (etoiles) dans la barre, dans l'ordre choisi dans le volet."""
        while self.zone_favoris.count():
            it = self.zone_favoris.takeAt(0)
            if it.widget():
                it.widget().hide()
                it.widget().setParent(None)
        for oid in self.params["outils_epingles"]:
            o = outil(oid)
            if o:
                _, _, coul, _ = famille(o[1])
                b = self._bouton(o[2], o[3].split(" ")[0] if len(o[3]) > 12 else o[3],
                                 lambda _=False, x=oid: self.outil_demande.emit(x), coul, o[3] + " — " + o[5])
                self.zone_favoris.addWidget(b)

    def _bandeau_modifier(self):
        self.bandeau = QFrame()
        self.bandeau.setStyleSheet("QFrame{background:#fbe8f2;border-bottom:1px solid #efc7dc}"
                                   "QToolButton{color:#6b0f41;font-size:11px;padding:2px 6px;border-radius:6px}"
                                   "QToolButton:checked{background:#f3c9df} QToolButton:hover{background:#f6d6e7}")
        h = QHBoxLayout(self.bandeau)
        h.setContentsMargins(12, 2, 12, 2)
        h.setSpacing(2)
        lbl = QLabel("<b>Modifier le PDF</b>")
        lbl.setStyleSheet("color:#6b0f41;margin-right:10px")
        h.addWidget(lbl)
        self.boutons_modif = {}
        for cle, ic, txt, aide in [("modifier", "modifier", "Modifier", "Cliquer : sélectionner et déplacer ; double-clic : corriger dans la page"),
                                   ("ajout_texte", "creer", "Ajouter du texte", "Cliquez où écrire"),
                                   ("ajout_image", "exporter", "Ajouter une image", "Choisissez une image puis cliquez où la placer"),
                                   ("lien", "remplacer", "Lien", "Tracez la zone du lien"),
                                   ("recadrer", "organiser", "Recadrer les pages", "Tracez la zone à garder"),
                                   ("entete", "entete", "En-tête et pied de page", None),
                                   ("filigrane", "filigrane", "Filigrane", None),
                                   ("fond", "nettoyer", "Arrière-plan", "Couleur de fond des pages")]:
            b = QToolButton()
            b.setIcon(icone(ic, "#b0186b"))
            b.setIconSize(QSize(18, 18))
            b.setText(txt)
            b.setToolTip(aide or txt)
            b.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            b.setCheckable(cle in ("modifier", "ajout_texte", "ajout_image", "lien", "recadrer"))
            b.clicked.connect(lambda _=False, c=cle: self._action_modifier(c))
            self.boutons_modif[cle] = b
            h.addWidget(b)
        h.addStretch()
        fin = QPushButton("Terminer")
        fin.setStyleSheet("QPushButton{background:#b0186b;color:#fff;border:none;border-radius:6px;padding:7px 14px;font-weight:600}")
        fin.clicked.connect(lambda: self.changer_mode(None))
        h.addWidget(fin)
        self.bandeau.hide()
        return self.bandeau

    def _action_modifier(self, cle):
        if cle in ("modifier", "ajout_texte", "lien", "recadrer"):
            self.changer_mode(cle)
        elif cle == "ajout_image":
            f, _ = QFileDialog.getOpenFileName(self, "Image à ajouter", "", "Images (*.png *.jpg *.jpeg *.bmp *.tif *.gif)")
            if f:
                self.image_a_ajouter = f
                self.changer_mode("ajout_image")
            else:
                self.changer_mode("modifier")
        else:
            self.outil_demande.emit(cle)

    def _vue_organiser(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(16, 10, 16, 10)
        h = QHBoxLayout()
        t = QLabel("<b>Organiser les pages</b> — glissez pour réordonner, clic droit pour plus d'actions")
        h.addWidget(t)
        h.addStretch()
        for txt, f in [("Pivoter ↺", lambda: self._sel_grille(lambda p: self.pivoter(p, -90, demander=False))),
                       ("Pivoter ↻", lambda: self._sel_grille(lambda p: self.pivoter(p, 90, demander=False))),
                       ("Supprimer", lambda: self._sel_grille(self.supprimer_pages)),
                       ("Extraire", lambda: self._sel_grille(self.extraire)),
                       ("Insérer un fichier...", self.inserer_fichier)]:
            b = QPushButton(txt)
            b.clicked.connect(f)
            h.addWidget(b)
        fin = QPushButton("Terminer")
        fin.setStyleSheet("QPushButton{background:#c9252d;color:#fff;border:none;border-radius:6px;padding:6px 14px;font-weight:600}")
        fin.clicked.connect(lambda: self.organiser(False))
        h.addWidget(fin)
        v.addLayout(h)
        self.grille = GrillePages(grille=True)
        self.grille.setStyleSheet("QListWidget{background:#ececec;border:none}")
        self.grille.ordre_change.connect(self.reordonner)
        self.grille.setContextMenuPolicy(Qt.CustomContextMenu)
        self.grille.customContextMenuRequested.connect(lambda p: self._menu_pages(self.grille, p))
        v.addWidget(self.grille, 1)
        return w

    def _sel_grille(self, f):
        pages = sorted(it.data(Qt.UserRole) for it in self.grille.selectedItems())
        if pages:
            f(pages)
        else:
            self.message("Sélectionnez d'abord des pages.")

    def organiser(self, actif=True):
        if actif:
            self._remplir_grille()
            self.centre.setCurrentIndex(1)
        else:
            self.centre.setCurrentIndex(0)

    def _volet(self):
        w = QFrame()
        w.setObjectName("volet")
        w.setMinimumWidth(200)
        w.setStyleSheet("QFrame#volet{background:#fff;border-left:1px solid #e2e2e2}")
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        self.pile_volet = QStackedWidget()
        v.addWidget(self.pile_volet)
        self.pile_volet.addWidget(self._volet_outils())
        self.pile_volet.addWidget(self._volet_format())
        self.pile_volet.addWidget(self._volet_bibliotheque())
        return w

    def basculer_volet(self):
        tailles = self.sp.sizes()
        if tailles[2] > 0:
            self._taille_volet = tailles[2]
            self.sp.setSizes([tailles[0], tailles[1] + tailles[2], 0])
        else:
            t = getattr(self, "_taille_volet", 300)
            self.sp.setSizes([tailles[0], max(200, tailles[1] - t), t])

    def _volet_outils(self):
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(14, 16, 14, 16)
        t = QLabel("MES OUTILS")
        t.setStyleSheet("font-size:12px;font-weight:600;color:#555;letter-spacing:1px")
        l.addWidget(t)
        aide = QLabel("Glissez pour changer l'ordre (barre du haut comprise).")
        aide.setStyleSheet("font-size:11px;color:#777")
        aide.setWordWrap(True)
        l.addWidget(aide)
        self.liste_outils = QListWidget()
        self.liste_outils.setDragDropMode(QAbstractItemView.InternalMove)
        self.liste_outils.setStyleSheet("QListWidget{border:none;font-size:14px} QListWidget::item{padding:8px 4px;border-radius:8px}"
                                        "QListWidget::item:hover{background:#f4f7fb}")
        self.liste_outils.setIconSize(QSize(20, 20))
        self.liste_outils.itemClicked.connect(lambda it: self.outil_demande.emit(it.data(Qt.UserRole)))
        self.liste_outils.model().rowsMoved.connect(self._ordre_outils)
        l.addWidget(self.liste_outils, 1)
        tous = QPushButton("  +  Tous les outils")
        tous.setStyleSheet("QPushButton{text-align:left;padding:9px 8px;border:1px dashed #cfcfcf;border-radius:8px;font-size:14px}")
        tous.clicked.connect(lambda: self.outil_demande.emit("__outils__"))
        l.addWidget(tous)
        ia = QLabel("✦ <b>Assistant IA</b><br><span style='font-size:12px'>Prévu en V3 : résumé, points clefs, remise en page "
                    "avec Claude ou Gemini. Rien n'est envoyé sans votre clic.</span>")
        ia.setWordWrap(True)
        ia.setStyleSheet("background:#f2fafa;border:1px solid #cfe9ea;border-radius:10px;padding:10px;color:#0b5e63")
        l.addWidget(ia)
        self.lbl_info = QLabel()
        self.lbl_info.setWordWrap(True)
        self.lbl_info.setStyleSheet("font-size:12px;color:#555")
        l.addWidget(self.lbl_info)
        self.remplir_volet()
        return w

    def remplir_volet(self):
        self.liste_outils.blockSignals(True)
        self.liste_outils.clear()
        for oid in self.params["outils_epingles"]:
            o = outil(oid)
            if o:
                it = QListWidgetItem(icone(o[2], famille(o[1])[2]), o[3])
                it.setToolTip(o[5])
                it.setData(Qt.UserRole, oid)
                self.liste_outils.addItem(it)
        self.liste_outils.blockSignals(False)
        self.remplir_favoris()
        self.maj_info()

    def _ordre_outils(self, *a):
        ordre = [self.liste_outils.item(i).data(Qt.UserRole) for i in range(self.liste_outils.count())]
        self.params["outils_epingles"] = ordre
        self.params.enregistrer()
        self.remplir_favoris()
        self.outil_demande.emit("__epingles__")

    def _volet_format(self):
        w = QWidget()
        f = QFormLayout(w)
        f.setContentsMargins(14, 16, 14, 16)
        t = QLabel("FORMAT")
        t.setStyleSheet("font-size:12px;font-weight:600;color:#555;letter-spacing:1px")
        f.addRow(t)
        self.format_info = QLabel("Cliquez sur une ligne pour la sélectionner, glissez pour la déplacer, "
                                  "double-cliquez pour corriger dans la page.")
        self.format_info.setWordWrap(True)
        self.format_info.setStyleSheet("color:#555;font-size:12px")
        f.addRow(self.format_info)
        self.format_police = QComboBox()
        self.format_police.addItem("Police du document (automatique)", None)
        for n, fichier in CANDIDATS:
            self.format_police.addItem(n, fichier)
        f.addRow("Police", self.format_police)
        self.format_taille = QDoubleSpinBox()
        self.format_taille.setRange(4, 96)
        self.format_taille.setValue(11)
        self.format_taille.setSuffix(" pt")
        f.addRow("Taille", self.format_taille)
        self.format_couleur = QColor("#000000")
        self.b_couleur = QPushButton()
        self._maj_b_couleur()
        self.b_couleur.clicked.connect(self._choisir_couleur)
        f.addRow("Couleur", self.b_couleur)
        self.b_appliquer = QPushButton("Appliquer à la ligne sélectionnée")
        self.b_appliquer.clicked.connect(self.appliquer_format)
        f.addRow(self.b_appliquer)
        t2 = QLabel("OBJETS")
        t2.setStyleSheet("font-size:12px;font-weight:600;color:#555;letter-spacing:1px;margin-top:12px")
        f.addRow(t2)
        for txt, fn in [("Supprimer l'objet sélectionné", self.supprimer),
                        ("Remplacer l'image...", self.remplacer_image)]:
            b = QPushButton(txt)
            b.clicked.connect(fn)
            f.addRow(b)
        return w

    def _maj_b_couleur(self):
        self.b_couleur.setStyleSheet(f"background:{self.format_couleur.name()};min-height:22px;border:1px solid #999;border-radius:4px")

    def _choisir_couleur(self):
        c = QColorDialog.getColor(self.format_couleur, self)
        if c.isValid():
            self.format_couleur = c
            self._maj_b_couleur()

    def _volet_bibliotheque(self):
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(14, 16, 14, 16)
        self.titre_biblio = QLabel()
        self.titre_biblio.setStyleSheet("font-size:12px;font-weight:600;color:#555;letter-spacing:1px")
        l.addWidget(self.titre_biblio)
        aide = QLabel("Cliquez un élément, puis cliquez sur la page pour le poser. Il reste déplaçable "
                      "et redimensionnable (poignées), Suppr pour l'enlever.")
        aide.setWordWrap(True)
        aide.setStyleSheet("color:#555;font-size:12px")
        l.addWidget(aide)
        self.liste_biblio = QListWidget()
        self.liste_biblio.setIconSize(QSize(240, 60))
        self.liste_biblio.setSpacing(4)
        self.liste_biblio.itemClicked.connect(self._choisir_biblio)
        l.addWidget(self.liste_biblio, 1)
        b = QPushButton("Gérer, importer, dessiner...")
        b.clicked.connect(self._gerer_biblio)
        l.addWidget(b)
        b = QPushButton("Fermer")
        b.clicked.connect(lambda: self.changer_mode(None))
        l.addWidget(b)
        return w

    def ouvrir_bibliotheque(self, genre):
        self.genre_biblio = genre
        self.titre_biblio.setText("MES TAMPONS" if genre == "tampons" else "MES SIGNATURES")
        self.liste_biblio.clear()
        auteur = self.params.get("machine", "")
        if genre == "tampons":
            for nom, t, c in objets.PREDEFINIS:
                pdf = objets.tampon_predefini(t, c, self.params.get("auteur", ""))
                self._ajout_item_biblio(nom, pdf, {"nom": nom, "dynamique": True, "texte": t, "couleur": list(c)},
                                        "Tampon à la date du jour")
        for e in self.biblio.elements(genre):
            self._ajout_item_biblio(e["nom"], None, e)
        self.pile_volet.setCurrentIndex(2)
        self._montrer_volet()
        if genre == "signatures" and not self.biblio.elements("signatures"):
            self._gerer_biblio()

    def _ajout_item_biblio(self, nom, pdf, e, aide=None):
        pdf = pdf or self.biblio.lire(e)
        pm = QPixmap()
        pm.loadFromData(objets.apercu(pdf, 60), "PNG")
        it = QListWidgetItem(QIcon(pm), "" if aide else nom)
        it.setToolTip(nom + (f" — {aide}" if aide else ""))
        it.setData(Qt.UserRole, e)
        self.liste_biblio.addItem(it)

    def _choisir_biblio(self, it):
        e = it.data(Qt.UserRole)
        pdf = (objets.tampon_predefini(e["texte"], tuple(e["couleur"]), self.params.get("auteur", ""))
               if e.get("dynamique") else self.biblio.lire(e))
        self.a_poser = (pdf, e["nom"], "signature" if self.genre_biblio == "signatures" else "tampon")
        self.mode = "poser"
        self.bandeau_simple.setText(f"<b>{e['nom']}</b> — cliquez sur la page pour le poser.")
        self.bandeau_simple.show()

    def _gerer_biblio(self):
        d = DialogueBibliotheque(self, self.biblio, self.genre_biblio, self.params.get("auteur", ""))
        ok = d.exec() == QDialog.Accepted
        self.ouvrir_bibliotheque(self.genre_biblio)
        if ok:
            e, pdf = d.choisi()
            if pdf:
                self.a_poser = (pdf, e["nom"], "signature" if self.genre_biblio == "signatures" else "tampon")
                self.mode = "poser"
                self.bandeau_simple.setText(f"<b>{e['nom']}</b> — cliquez sur la page pour le poser.")
                self.bandeau_simple.show()

    def _montrer_volet(self):
        if self.sp.sizes()[2] == 0:
            self.basculer_volet()

    def maj_info(self):
        if hasattr(self, "lbl_info"):
            self.lbl_info.setText(f"{len(self.doc)} page{'s' if len(self.doc) > 1 else ''}"
                                  + (f" · {self.poids_initial // 1024} Ko à l'ouverture" if self.poids_initial else "")
                                  + (" · modifié, non enregistré" if self.modifie else ""))

    # ------------------------------------------------------------ pages
    def construire_pages(self):
        while self.pages_layout.count():
            it = self.pages_layout.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        self.page_widgets = []
        for n in range(len(self.doc)):
            pw = PageWidget(self, n)
            self.page_widgets.append(pw)
            self.pages_layout.addWidget(pw, 0, Qt.AlignHCenter)
        self._vider_caches()
        self.construire_vignettes()
        self.lbl_zoom.setText(f"{round(self.zoom * 100)} %")
        self._page_visible()
        self.maj_info()

    def _vider_caches(self):
        self._cache_lignes.clear()
        self._cache_mots.clear()
        self._cache_images.clear()

    def _vignette(self, n, taille=120):
        page = self.doc[n]
        k = taille / max(page.rect.width, page.rect.height)
        pm = page.get_pixmap(matrix=fitz.Matrix(k, k).prerotate(self.rotation_vue.get(n, 0)), alpha=False)
        return QPixmap.fromImage(QImage(pm.samples, pm.width, pm.height, pm.stride, QImage.Format_RGB888).copy())

    def construire_vignettes(self):
        self.vignettes.clear()
        for n in range(len(self.doc)):
            it = QListWidgetItem(QIcon(self._vignette(n)), str(n + 1))
            it.setData(Qt.UserRole, n)
            it.setTextAlignment(Qt.AlignHCenter)
            self.vignettes.addItem(it)
        if self.centre.currentIndex() == 1:
            self._remplir_grille()

    def _remplir_grille(self):
        self.grille.clear()
        for n in range(len(self.doc)):
            it = QListWidgetItem(QIcon(self._vignette(n, 200)), str(n + 1))
            it.setData(Qt.UserRole, n)
            self.grille.addItem(it)

    def rafraichir_pages(self, refaire=False):
        if refaire:
            self._vider_caches()
        for pw in self.page_widgets:
            if refaire:
                pw.image = None
            pw.update()

    def page_courante(self):
        y = self.zone.verticalScrollBar().value() + self.zone.viewport().height() // 3
        for pw in self.page_widgets:
            if pw.y() + pw.height() >= y:
                return pw.num
        return len(self.page_widgets) - 1

    def _page_visible(self, *_):
        if getattr(self, "page_widgets", None):
            self.lbl_page.setText(f"Page {self.page_courante() + 1} sur {len(self.doc)}")

    def aller_a(self, n, rect=None):
        self.organiser(False) if self.centre.currentIndex() == 1 else None
        pw = self.page_widgets[n]
        y = pw.y()
        if rect is not None:
            y += int(pw.vers_ecran(rect).y()) - self.zone.viewport().height() // 3
        self.zone.verticalScrollBar().setValue(max(0, y))
        self.rafraichir_pages()

    def changer_zoom(self, z):
        self.zoom = max(0.25, min(6.0, z))
        self.params["zoom"] = self.zoom
        for pw in self.page_widgets:
            pw.maj_taille()
        self.lbl_zoom.setText(f"{round(self.zoom * 100)} %")

    # ------------------------------------------------------------ texte
    def lignes_page(self, n):
        if n not in self._cache_lignes:
            out = []
            for b in self.doc[n].get_text("dict")["blocks"]:
                for l in b.get("lines", []):
                    t = "".join(s["text"] for s in l["spans"])
                    if t.strip():
                        out.append((tuple(l["bbox"]), t))
            self._cache_lignes[n] = out
        return self._cache_lignes[n]

    def images_page(self, n):
        if n not in self._cache_images:
            try:
                self._cache_images[n] = Editeur(self.doc).images(n)
            except Exception:
                self._cache_images[n] = []
        return self._cache_images[n]

    def mots(self, n):
        if n not in self._cache_mots:
            self._cache_mots[n] = self.doc[n].get_text("words", sort=True)
        return self._cache_mots[n]

    def mot_sous(self, n, pt):
        for i, w in enumerate(self.mots(n)):
            if fitz.Rect(w[:4]).contains(pt):
                return i
        return None

    def _mot_proche(self, n, pt):
        best, bd = None, 1e9
        for i, w in enumerate(self.mots(n)):
            r = fitz.Rect(w[:4])
            dx = 0 if r.x0 <= pt.x <= r.x1 else min(abs(pt.x - r.x0), abs(pt.x - r.x1))
            dy = 0 if r.y0 <= pt.y <= r.y1 else min(abs(pt.y - r.y0), abs(pt.y - r.y1))
            d = dy * 4 + dx
            if d < bd:
                best, bd = i, d
        return best if bd < 40 else None

    def debut_selection(self, n, pt):
        i = self._mot_proche(n, pt)
        self.selection = {"page": n, "debut": i, "fin": i, "lignes": [], "texte": ""} if i is not None else None
        self._calculer_selection()

    def etendre_selection(self, n, pt):
        if not self.selection or self.selection["page"] != n:
            return
        i = self._mot_proche(n, pt)
        if i is not None:
            self.selection["fin"] = i
            self._calculer_selection()

    def tout_selectionner(self):
        n = self.page_courante()
        if self.mots(n):
            self.selection = {"page": n, "debut": 0, "fin": len(self.mots(n)) - 1, "lignes": [], "texte": ""}
            self._calculer_selection()

    def _calculer_selection(self):
        s = self.selection
        if s:
            a, b = sorted((s["debut"], s["fin"]))
            mots = self.mots(s["page"])[a:b + 1]
            groupes, lignes_txt, prec = {}, [], None
            for w in mots:
                cle = (w[5], w[6])
                groupes.setdefault(cle, fitz.Rect(w[:4]))
                groupes[cle] |= fitz.Rect(w[:4])
                if cle != prec:
                    lignes_txt.append([])
                lignes_txt[-1].append(w[4])
                prec = cle
            s["lignes"] = list(groupes.values())
            s["texte"] = "\n".join(" ".join(x) for x in lignes_txt)
        self.rafraichir_pages()

    def montrer_barre_rapide(self, pw):
        if not self.params.get("barre_rapide", True) or not self.selection or not self.selection["lignes"]:
            return
        r = pw.vers_ecran(self.selection["lignes"][0])
        p = pw.mapTo(self.zone.viewport(), QPoint(int(r.x()), int(r.y())))
        self.barre_rapide.adjustSize()
        x = max(4, min(p.x(), self.zone.viewport().width() - self.barre_rapide.width() - 4))
        y = p.y() - self.barre_rapide.height() - 8
        if y < 4:
            y = p.y() + int(r.height()) + 8
        self.barre_rapide.move(x, y)
        self.barre_rapide.show()
        self.barre_rapide.raise_()

    # ------------------------------------------------------------ objets (annotations, lignes, images)
    def objet_sous(self, n, pt, survol=False):
        page = self.doc[n]
        if self.mode in (None, "modifier", "poser"):
            for a in reversed(list(page.annots())):
                if a.type[0] in DEPLACABLES and fitz.Rect(a.rect).contains(pt):
                    return {"type": "annot", "page": n, "xref": a.xref, "rect": fitz.Rect(a.rect),
                            "philpdf": objets.est_objet_philpdf(a), "garder_proportions": a.type[0] == fitz.PDF_ANNOT_STAMP}
        if self.mode == "modifier":
            for r, t in self.lignes_page(n):
                if fitz.Rect(r).contains(pt):
                    return {"type": "ligne", "page": n, "rect": fitz.Rect(r), "texte": t}
            for xref, r in self.images_page(n):
                if r.contains(pt):
                    return {"type": "image", "page": n, "xref": xref, "rect": fitz.Rect(r), "garder_proportions": True}
        return None

    def choisir_objet(self, obj):
        self.objet = obj
        if obj and obj["type"] == "ligne" and self.mode == "modifier":
            try:
                chars, r, t = Editeur(self.doc).ligne_a(obj["page"], obj["rect"])
                s = chars[0][1]
                self.format_taille.setValue(round(s["size"], 1))
                self.format_couleur = QColor.fromRgbF(*fitz.sRGB_to_pdf(s["color"]))
                self._maj_b_couleur()
                self.format_info.setText(f"<b>{t.strip()[:40]}</b><br>{s['font']}, {s['size']:.1f} pt")
            except Exception:
                pass
        self.rafraichir_pages()

    def appliquer_deplacement(self, nouveau):
        obj = self.objet
        if not obj:
            return
        self.memoriser()
        n = obj["page"]
        try:
            if obj["type"] == "annot":
                objets.deplacer(self.doc, n, obj["xref"], nouveau)
                if not obj.get("philpdf"):
                    for a in self.doc[n].annots():
                        if a.xref == obj["xref"]:
                            a.set_rect(nouveau)
                            a.update()
                journal = ["Objet déplacé."]
            elif obj["type"] == "ligne":
                d = nouveau.tl - obj["rect"].tl
                ed = Editeur(self.doc)
                ed.deplacer_ligne(n, obj["rect"], d.x, d.y)
                journal = ed.journal
            elif obj["type"] == "image":
                ed = Editeur(self.doc)
                ed.deplacer_image(n, obj["xref"], nouveau)
                journal = ed.journal
        except Exception as e:
            self.annulations.pop()
            self.message(f"Déplacement impossible : {e}")
            return
        obj["rect"] = fitz.Rect(nouveau)
        if obj["type"] in ("image",):
            self.objet = None
        self.apres_modif(journal)
        if obj["type"] == "ligne":
            self.objet = {"type": "ligne", "page": n, "rect": nouveau, "texte": obj["texte"]}
            self.rafraichir_pages()

    def supprimer(self):
        obj = self.objet
        if not obj:
            return
        self.memoriser()
        n = obj["page"]
        if obj["type"] == "annot":
            for a in self.doc[n].annots():
                if a.xref == obj["xref"]:
                    self.doc[n].delete_annot(a)
                    break
        elif obj["type"] == "ligne":
            ed = Editeur(self.doc)
            ed.modifier_ligne(n, obj["rect"], "")
        elif obj["type"] == "image":
            Editeur(self.doc).supprimer_image(n, obj["xref"])
        self.objet = None
        self.apres_modif(["Objet supprimé."])

    def remplacer_image(self):
        obj = self.objet
        if not obj or obj["type"] != "image":
            self.message("Sélectionnez d'abord une image (mode Modifier).")
            return
        f, _ = QFileDialog.getOpenFileName(self, "Nouvelle image", "", "Images (*.png *.jpg *.jpeg *.bmp *.tif)")
        if f:
            self.memoriser()
            Editeur(self.doc).remplacer_image(obj["page"], obj["xref"], obj["rect"], f)
            self.objet = None
            self.apres_modif(["Image remplacée."])

    def editer_annotation(self, obj):
        for a in self.doc[obj["page"]].annots():
            if a.xref == obj["xref"] and not obj.get("philpdf"):
                t, ok = QInputDialog.getMultiLineText(self, "Commentaire", "Texte :", a.info.get("content", ""))
                if ok:
                    self.memoriser()
                    a.set_info(content=t)
                    a.update()
                    self.apres_modif()

    def menu_contexte(self, pw, pt, pos_globale):
        obj = self.objet_sous(pw.num, pt)
        if obj:
            self.choisir_objet(obj)
        m = QMenu(self)
        if self.objet:
            m.addAction(icone("copier"), "Copier", self.copier)
            m.addAction("Couper", self.couper)
            m.addAction(icone("fermer", "#c9252d"), "Supprimer", self.supprimer)
            if self.objet["type"] == "image":
                m.addAction("Remplacer l'image...", self.remplacer_image)
            if self.objet["type"] == "ligne":
                m.addAction("Corriger dans la page", lambda: pw.ouvrir_editeur(self.objet["rect"], None, self.objet["texte"]))
            m.addSeparator()
        m.addAction("Coller", lambda: self.coller(pw.num, pt))
        m.addAction("Ajouter du texte ici", lambda: pw.ouvrir_editeur(None, pt))
        m.exec(pos_globale)

    # ---- presse-papiers
    def copier(self):
        if self.objet:
            obj = self.objet
            if obj["type"] == "ligne":
                QGuiApplication.clipboard().setText(obj["texte"].strip())
            elif obj["type"] == "annot":
                pdf = self.objets_pdf.get(obj["xref"])
                if pdf is None:  # objet venu du fichier : on le recopie en image
                    page = self.doc[obj["page"]]
                    pm = page.get_pixmap(clip=obj["rect"], dpi=200, annots=True)
                    pdf = (objets.pdf_depuis_image(pm.tobytes("png"), True), "Objet", "tampon")
                self.presse_objet = (pdf, fitz.Rect(obj["rect"]))
            elif obj["type"] == "image":
                info = self.doc.extract_image(obj["xref"])
                self.presse_objet = (("image", info["image"]), fitz.Rect(obj["rect"]))
            self.message("Copié.")
        elif self.selection:
            QGuiApplication.clipboard().setText(self.selection["texte"])
            self.message("Texte copié.")

    def couper(self):
        if self.objet:
            self.copier()
            self.supprimer()

    def coller(self, n=None, pt=None):
        n = self.page_courante() if n is None else n
        po = getattr(self, "presse_objet", None)
        if po:
            data, r = po
            dec = 20
            cible = fitz.Rect(r) + (dec, dec, dec, dec) if pt is None else fitz.Rect(pt.x, pt.y, pt.x + r.width, pt.y + r.height)
            self.memoriser()
            if data[0] == "image":
                self.doc[n].insert_image(cible, stream=data[1])
            else:
                pdf, nom, genre = data
                x = objets.poser(self.doc, n, cible, pdf, nom, self.params.get("auteur", ""), genre)
                self.objets_pdf[x] = data
            self.apres_modif(["Collé."])
            return
        t = QGuiApplication.clipboard().text()
        if t:
            page = self.doc[n]
            pt = pt or fitz.Point(page.rect.width * 0.15, page.rect.height * 0.3)
            self.ajouter_texte(n, pt, t.splitlines()[0], self.format_taille.value(), None, None)

    # ------------------------------------------------------------ actions texte
    def annoter(self, genre):
        s = self.selection
        if not s:
            return
        self.memoriser()
        page = self.doc[s["page"]]
        if genre == "surligner":
            a = page.add_highlight_annot(s["lignes"])
        elif genre == "souligner":
            a = page.add_underline_annot(s["lignes"])
        elif genre == "barrer":
            a = page.add_strikeout_annot(s["lignes"])
        else:
            txt, ok = QInputDialog.getMultiLineText(self, "Note", "Texte de la note :")
            if not ok:
                self.annulations.pop()
                return
            r = s["lignes"][-1]
            a = page.add_text_annot(fitz.Point(r.x1 + 2, r.y0), txt, icon="Comment")
        a.set_info(title=self.params.get("auteur") or self.params["machine"])
        a.update()
        self.selection = None
        self.apres_modif()

    def biffer(self):
        s = self.selection
        if not s:
            return
        if question(self, "Biffer", "Le texte sélectionné sera supprimé définitivement du fichier "
                    "et remplacé par un rectangle noir. Continuer ?",
                    [("Biffer", QMessageBox.AcceptRole), ("Annuler", QMessageBox.RejectRole)]) != 0:
            return
        self.memoriser()
        page = self.doc[s["page"]]
        for r in s["lignes"]:
            page.add_redact_annot(r, fill=(0, 0, 0))
        page.apply_redactions()
        self.selection = None
        self.apres_modif(["Passage biffé : le texte n'existe plus dans le fichier."])

    def modifier_selection(self):
        s = self.selection
        if not s:
            return
        n = s["page"]
        self.selection = None
        self.changer_mode("modifier")
        pw = self.page_widgets[n]
        for r, t in self.lignes_page(n):
            if fitz.Rect(r).intersects(s["lignes"][0]):
                pw.ouvrir_editeur(fitz.Rect(r), None, t)
                return

    def modifier_ligne_texte(self, n, rect, texte, taille=None, couleur=None):
        self.memoriser()
        ed = Editeur(self.doc)
        try:
            ed.modifier_ligne(n, rect, texte, taille, couleur)
        except ValueError as e:
            self.annulations.pop()
            self.message(str(e))
            return
        self.objet = None
        self.apres_modif(ed.journal or ["Aucun changement."])

    def appliquer_format(self):
        obj = self.objet
        if not obj or obj["type"] != "ligne":
            self.message("Sélectionnez d'abord une ligne (mode Modifier).")
            return
        self.modifier_ligne_texte(obj["page"], obj["rect"], obj["texte"].rstrip(), self.format_taille.value(),
                                  self.format_couleur.getRgbF()[:3])

    def ajouter_texte(self, n, pt, texte, taille=None, couleur=None, police=None):
        self.memoriser()
        ed = Editeur(self.doc)
        police = police or self.format_police.currentData()
        coul = couleur or (self.format_couleur.getRgbF()[:3] if self.format_police.currentData() else None)
        ed.ajouter_texte(n, pt, texte, taille, coul, police)
        self.apres_modif(ed.journal)
        self.changer_mode("modifier")

    def ajouter_image_ici(self, n, pt):
        f = getattr(self, "image_a_ajouter", None)
        if not f:
            return
        self.memoriser()
        pix = fitz.Pixmap(f)
        w = min(200, self.doc[n].rect.width / 3)
        h = w * pix.height / pix.width
        self.doc[n].insert_image(fitz.Rect(pt.x, pt.y, pt.x + w, pt.y + h), filename=f)
        self.image_a_ajouter = None
        self.apres_modif(["Image ajoutée : sélectionnez-la pour la déplacer ou la redimensionner."])
        self.changer_mode("modifier")

    def zone_tracee(self, n, r):
        page = self.doc[n]
        if self.mode == "lien":
            choix = question(self, "Lien", "Ce lien mène vers :", [("Un site Internet", QMessageBox.AcceptRole),
                                                                  ("Une page du document", QMessageBox.AcceptRole),
                                                                  ("Annuler", QMessageBox.RejectRole)])
            if choix == 0:
                url, ok = QInputDialog.getText(self, "Lien", "Adresse :", text="https://")
                if ok and url:
                    self.memoriser()
                    page.insert_link({"kind": fitz.LINK_URI, "from": r, "uri": url})
                    self.apres_modif(["Lien ajouté."])
            elif choix == 1:
                num, ok = QInputDialog.getInt(self, "Lien", "Page :", 1, 1, len(self.doc))
                if ok:
                    self.memoriser()
                    page.insert_link({"kind": fitz.LINK_GOTO, "from": r, "page": num - 1, "to": fitz.Point(0, 0)})
                    self.apres_modif(["Lien ajouté."])
        elif self.mode == "recadrer":
            choix = question(self, "Recadrer", "Recadrer :", [("Cette page", QMessageBox.AcceptRole),
                                                            ("Toutes les pages", QMessageBox.AcceptRole),
                                                            ("Annuler", QMessageBox.RejectRole)])
            if choix in (0, 1):
                self.memoriser()
                for p in ([page] if choix == 0 else list(self.doc)):
                    zone = (fitz.Rect(r) + (p.cropbox.x0, p.cropbox.y0, p.cropbox.x0, p.cropbox.y0)) & p.mediabox
                    p.set_cropbox(zone)
                self.apres_modif(["Pages recadrées."], reconstruire=True)
        self.changer_mode("modifier")

    # ---- poser tampon / signature
    def poser_objet(self, n, pt):
        if not self.a_poser:
            return
        pdf, nom, genre = self.a_poser
        w, h = objets.taille_naturelle(pdf)
        maxi = 220 if genre == "signature" else 180
        k = min(1.0, maxi / max(w, 1))
        w, h = w * k, h * k
        self.memoriser()
        r = fitz.Rect(pt.x - w / 2, pt.y - h / 2, pt.x + w / 2, pt.y + h / 2)
        x = objets.poser(self.doc, n, r, pdf, nom, self.params.get("auteur", ""), genre)
        self.objets_pdf[x] = (pdf, nom, genre)
        self.mode = None
        self.bandeau_simple.hide()
        self.apres_modif([f"« {nom} » est en place : glissez pour déplacer, poignées pour la taille, Suppr pour enlever."])
        for a in self.doc[n].annots():
            if a.xref == x:
                self.choisir_objet({"type": "annot", "page": n, "xref": x, "rect": fitz.Rect(a.rect),
                                    "philpdf": True, "garder_proportions": True})

    def changer_mode(self, mode):
        if mode != "poser":
            self.a_poser = None if mode is None else self.a_poser
        self.mode = mode
        self.barre_rapide.hide()
        self.selection = None
        self.bandeau_simple.hide()
        modif = mode in ("modifier", "ajout_texte", "ajout_image", "lien", "recadrer")
        self.bandeau.setVisible(modif)
        for cle, b in self.boutons_modif.items():
            if b.isCheckable():
                b.setChecked(cle == mode)
        if modif:
            self.pile_volet.setCurrentIndex(1)
            self._montrer_volet()
        elif self.pile_volet.currentIndex() != 0:
            self.pile_volet.setCurrentIndex(0)
        if mode is None:
            self.objet = None
        self.rafraichir_pages()

    # ------------------------------------------------------------ pages : rotation, organisation
    def pivoter_courante(self):
        self.pivoter([self.page_courante()])

    def pivoter(self, pages, angle=90, demander=True):
        dans_fichier = True
        if demander:
            dans_fichier = question(self, "Pivoter", "Conserver cette orientation dans le fichier ?\n\n"
                                    "Oui : la page reste tournée à l'enregistrement.\nNon : seulement pour l'affichage.",
                                    [("Oui, dans le fichier", QMessageBox.YesRole),
                                     ("Seulement l'affichage", QMessageBox.NoRole)]) == 0
        if dans_fichier:
            self.memoriser()
            for n in pages:
                self.doc[n].set_rotation((self.doc[n].rotation + angle) % 360)
            self.apres_modif(reconstruire=True)
        else:
            for n in pages:
                self.rotation_vue[n] = (self.rotation_vue.get(n, 0) + angle) % 360
                self.page_widgets[n].maj_taille()
            self.construire_vignettes()

    def _menu_pages(self, liste, pos):
        pages = sorted(it.data(Qt.UserRole) for it in liste.selectedItems())
        if not pages:
            return
        m = QMenu(self)
        m.addAction(icone("pivoter"), "Pivoter à droite (90°)", lambda: self.pivoter(pages, 90, demander=False))
        m.addAction("Pivoter à gauche (90°)", lambda: self.pivoter(pages, -90, demander=False))
        m.addSeparator()
        m.addAction("Déplacer au début", lambda: self.reordonner(pages + [i for i in range(len(self.doc)) if i not in pages]))
        m.addAction("Déplacer à la fin", lambda: self.reordonner([i for i in range(len(self.doc)) if i not in pages] + pages))
        m.addAction("Insérer des pages d'un fichier après...", lambda: self.inserer_fichier(pages[-1] + 1))
        m.addAction("Remplacer par les pages d'un fichier...", lambda: self.remplacer_pages(pages))
        m.addAction(icone("exporter"), "Extraire dans un nouveau PDF", lambda: self.extraire(pages))
        m.addSeparator()
        m.addAction(icone("fermer", "#c9252d"), "Supprimer", lambda: self.supprimer_pages(pages))
        m.exec(liste.mapToGlobal(pos))

    def reordonner(self, ordre):
        self.memoriser()
        self.doc.select(ordre)
        self.apres_modif(["Pages réordonnées."], reconstruire=True)

    def supprimer_pages(self, pages):
        if len(pages) >= len(self.doc):
            self.message("Impossible de supprimer toutes les pages.")
            return
        self.memoriser()
        self.doc.delete_pages(pages)
        self.apres_modif(reconstruire=True)

    def inserer_fichier(self, apres=None):
        f, _ = QFileDialog.getOpenFileName(self, "Insérer des pages", "", "PDF et images (*.pdf *.png *.jpg *.jpeg *.tif)")
        if not f:
            return
        src = fitz.open(f)
        if not src.is_pdf:
            src = fitz.open("pdf", src.convert_to_pdf())
        self.memoriser()
        self.doc.insert_pdf(src, start_at=len(self.doc) if apres is None else apres)
        self.apres_modif(["Pages insérées."], reconstruire=True)

    def remplacer_pages(self, pages):
        f, _ = QFileDialog.getOpenFileName(self, "Pages de remplacement", "", "PDF (*.pdf)")
        if not f:
            return
        src = fitz.open(f)
        self.memoriser()
        debut = pages[0]
        self.doc.delete_pages(pages)
        self.doc.insert_pdf(src, from_page=0, to_page=min(len(pages), len(src)) - 1, start_at=debut)
        self.apres_modif(["Pages remplacées."], reconstruire=True)

    def extraire(self, pages):
        nd = fitz.open()
        for n in pages:
            nd.insert_pdf(self.doc, from_page=n, to_page=n)
        self._extrait = nd
        self.outil_demande.emit("__nouveau__")

    # ------------------------------------------------------------ historique
    def memoriser(self):
        self.annulations.append(self.doc.tobytes())
        self.annulations = self.annulations[-30:]
        self.retablissements.clear()

    def _recharger(self, octets):
        self.doc = fitz.open(stream=octets, filetype="pdf")
        self.objet = None
        self.modifie = True
        self.construire_pages()
        self.titre_change.emit()

    def annuler(self):
        if not self.annulations:
            self.message("Rien à annuler.")
            return
        self.retablissements.append(self.doc.tobytes())
        self._recharger(self.annulations.pop())

    def retablir(self):
        if not self.retablissements:
            self.message("Rien à rétablir.")
            return
        self.annulations.append(self.doc.tobytes())
        self._recharger(self.retablissements.pop())

    def apres_modif(self, journal=None, reconstruire=False):
        self.modifie = True
        if reconstruire or len(self.page_widgets) != len(self.doc):
            self.construire_pages()
        else:
            self.rafraichir_pages(refaire=True)
            self.construire_vignettes()
        self.maj_info()
        self.titre_change.emit()
        if journal:
            self.message(journal[-1])

    def message(self, t):
        self.statut.emit(t)

    # ------------------------------------------------------------ enregistrement
    def enregistrer(self, chemin):
        if self.params.get("fixer_objets"):
            for page in self.doc:
                for a in list(page.annots()):
                    if objets.est_objet_philpdf(a):
                        r = fitz.Rect(a.rect)
                        pm_doc = self.objets_pdf.get(a.xref)
                        if pm_doc:
                            page.show_pdf_page(r, fitz.open("pdf", pm_doc[0]), 0)
                            page.delete_annot(a)
        opts = dict(garbage=3, deflate=True)
        if self.chiffrement:
            opts.update(self.chiffrement)
        tmp = chemin + ".philpdf-tmp"
        self.doc.save(tmp, **opts)
        os.replace(tmp, chemin)
        self.chemin, self.nom, self.modifie = chemin, os.path.basename(chemin), False
        self.poids_initial = os.path.getsize(chemin)
        self.maj_info()
        self.titre_change.emit()


# ================================================================ rechercher et remplacer
class DialogueRemplacer(QDialog):
    def __init__(self, onglet, texte=""):
        super().__init__(onglet)
        self.o = onglet
        self.setWindowTitle("Rechercher et remplacer")
        self.setMinimumWidth(480)
        f = QFormLayout(self)
        self.rech = QLineEdit(texte)
        self.remp = QLineEdit()
        self.compte = QLabel()
        self.compte.setStyleSheet("color:#1462c2;font-weight:600")
        f.addRow("Rechercher", self.rech)
        f.addRow("", self.compte)
        f.addRow("Remplacer par", self.remp)
        self.casse = QCheckBox("Respecter la casse (Dupont ≠ DUPONT)")
        self.accents = QCheckBox("Ignorer les accents (e = é = è = ê)")
        self.accents.setChecked(True)
        f.addRow(self.casse)
        f.addRow(self.accents)
        info = QLabel("La police et la mise en forme d'origine sont conservées.")
        info.setStyleSheet("color:#555")
        f.addRow(info)
        bb = QDialogButtonBox()
        self.b_suiv = bb.addButton("Suivant ›", QDialogButtonBox.ActionRole)
        self.b_un = bb.addButton("Remplacer", QDialogButtonBox.ActionRole)
        self.b_tout = bb.addButton("Remplacer tout", QDialogButtonBox.ActionRole)
        bb.addButton("Fermer", QDialogButtonBox.RejectRole)
        f.addRow(bb)
        self.rech.textChanged.connect(self.compter)
        self.casse.toggled.connect(self.compter)
        self.accents.toggled.connect(self.compter)
        self.b_suiv.clicked.connect(self.suivant)
        self.b_un.clicked.connect(self.remplacer_un)
        self.b_tout.clicked.connect(self.remplacer_tout)
        bb.rejected.connect(self.reject)
        self.idx = -1
        self.compter()

    def _occ(self):
        t = self.rech.text()
        if not t:
            return []
        ed = Editeur(self.o.doc)
        out = []
        for n in range(len(self.o.doc)):
            for chars, d, f in ed.occurrences(n, t, self.casse.isChecked(), not self.accents.isChecked()):
                r = fitz.Rect()
                for c, _ in chars[d:f]:
                    r |= fitz.Rect(c["bbox"])
                out.append((n, r))
        return out

    def compter(self):
        occ = self._occ()
        self.o.resultats = occ
        self.compte.setText(f"{len(occ)} occurrence{'s' if len(occ) > 1 else ''}" if self.rech.text() else "")
        self.b_tout.setText(f"Remplacer tout ({len(occ)})")
        self.idx = -1
        self.o.rafraichir_pages()

    def suivant(self):
        occ = self.o.resultats
        if not occ:
            return
        self.idx = (self.idx + 1) % len(occ)
        self.o.resultat_courant = occ[self.idx]
        self.o.aller_a(*occ[self.idx])

    def remplacer_un(self):
        if self.idx < 0:
            self.suivant()
            return
        n, r = self.o.resultats[self.idx]
        self.o.memoriser()
        ed = Editeur(self.o.doc)
        ed.remplacer(n, self.rech.text(), self.remp.text(), zone=r,
                     casse=self.casse.isChecked(), accents=not self.accents.isChecked())
        self.o.apres_modif(ed.journal)
        self.compter()
        self.suivant()

    def remplacer_tout(self):
        self.o.memoriser()
        ed = Editeur(self.o.doc)
        n = ed.remplacer_tout(self.rech.text(), self.remp.text(), self.casse.isChecked(), not self.accents.isChecked())
        self.o.apres_modif(ed.journal)
        self.o.message(f"{n} remplacement{'s' if n > 1 else ''} effectué{'s' if n > 1 else ''}.")
        self.compter()
