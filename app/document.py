"""Onglet d'un fichier ouvert : visionneuse, vignettes, selection, barre rapide, mode Modifier."""
import os, unicodedata
import pymupdf as fitz
from PySide6.QtCore import Qt, Signal, QRectF, QPointF, QTimer, QSize, QPoint
from PySide6.QtGui import QImage, QPainter, QColor, QPen, QPixmap, QGuiApplication, QAction, QKeySequence
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QFrame, QLabel, QToolButton,
                               QListWidget, QListWidgetItem, QSplitter, QPushButton, QInputDialog, QMenu,
                               QMessageBox, QLineEdit, QDialog, QDialogButtonBox, QCheckBox, QFormLayout,
                               QAbstractItemView, QButtonGroup, QRadioButton, QComboBox, QSizePolicy, QTextEdit)
from .icones import icone
from .outils import outil, famille
from moteur.modifier import Editeur

ECRAN = 96 / 72   # points PDF -> pixels a 100 %


# ---------------------------------------------------------------- page
class PageWidget(QWidget):
    def __init__(self, onglet, num):
        super().__init__()
        self.o, self.num = onglet, num
        self.image, self.image_zoom = None, None
        self.survol = None
        self.setMouseTracking(True)
        self.maj_taille()

    def rect_page(self):
        p = self.o.doc[self.num]
        r = p.rect
        rot = self.o.rotation_vue.get(self.num, 0)
        return (r.height, r.width) if rot in (90, 270) else (r.width, r.height)

    def echelle(self):
        return self.o.zoom * ECRAN

    def maj_taille(self):
        w, h = self.rect_page()
        e = self.echelle()
        self.setFixedSize(int(w * e), int(h * e))
        self.image = None

    def matrice(self):
        rot = self.o.rotation_vue.get(self.num, 0)
        return fitz.Matrix(self.echelle(), self.echelle()).prerotate(rot)

    def vers_pdf(self, pos):
        """Point ecran -> point PDF (coordonnees PyMuPDF)."""
        return fitz.Point(pos.x(), pos.y()) * ~self._mat_texte()

    def _mat_affichage(self):
        page = self.o.doc[self.num]
        rot = self.o.rotation_vue.get(self.num, 0)
        e = self.echelle()
        m = fitz.Matrix(e, e).prerotate(rot)
        # recaler l'origine apres rotation
        r = page.rect * m
        return m * fitz.Matrix(1, 0, 0, 1, -r.x0, -r.y0)

    def _mat_texte(self):
        """Coordonnees du texte (page non pivotee) -> ecran."""
        return self.o.doc[self.num].rotation_matrix * self._mat_affichage()

    def vers_ecran(self, rect):
        r = fitz.Rect(rect) * self._mat_texte()
        return QRectF(r.x0, r.y0, r.width, r.height)

    def paintEvent(self, ev):
        p = QPainter(self)
        if self.image is None or self.image_zoom != self.o.zoom:
            dpr = self.devicePixelRatioF()
            pm = self.o.doc[self.num].get_pixmap(matrix=self._mat_affichage() * fitz.Matrix(dpr, dpr), alpha=False)
            img = QImage(pm.samples, pm.width, pm.height, pm.stride, QImage.Format_RGB888).copy()
            img.setDevicePixelRatio(dpr)
            self.image, self.image_zoom = img, self.o.zoom
        p.drawImage(0, 0, self.image)
        # selection
        sel = self.o.selection
        if sel and sel["page"] == self.num:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(20, 98, 194, 70))
            for r in sel["lignes"]:
                p.drawRect(self.vers_ecran(r))
        # resultats de recherche
        for (pg, r) in self.o.resultats:
            if pg == self.num:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(255, 210, 0, 110) if (pg, r) != self.o.resultat_courant else QColor(255, 140, 0, 150))
                p.drawRect(self.vers_ecran(r))
        # mode Modifier : cadres des lignes
        if self.o.mode == "modifier":
            pen = QPen(QColor("#1462c2"))
            pen.setStyle(Qt.DashLine)
            for r, _t in self.o.lignes_page(self.num):
                actif = self.survol is not None and fitz.Rect(r).contains(self.survol)
                p.setPen(QPen(QColor("#1462c2"), 2 if actif else 1, Qt.SolidLine if actif else Qt.DotLine))
                p.setBrush(QColor(20, 98, 194, 25) if actif else Qt.NoBrush)
                p.drawRect(self.vers_ecran(fitz.Rect(r) + (-1.5, -1, 1.5, 1)))
        p.end()

    # ---- souris
    def mousePressEvent(self, e):
        self.o.barre_rapide.hide()
        pt = self.vers_pdf(e.position())
        if e.button() != Qt.LeftButton:
            return
        if self.o.mode == "modifier":
            for r, t in self.o.lignes_page(self.num):
                if fitz.Rect(r).contains(pt):
                    self.o.modifier_ligne(self.num, r, t)
                    return
            return
        if self.o.mode == "ajout_texte":
            self.o.ajouter_texte_ici(self.num, pt)
            return
        if self.o.mode == "signature":
            self.o.placer_signature(self.num, pt)
            return
        self.o.debut_selection(self.num, pt)

    def mouseMoveEvent(self, e):
        pt = self.vers_pdf(e.position())
        if self.o.mode == "modifier":
            self.survol = pt
            self.setCursor(Qt.IBeamCursor if any(fitz.Rect(r).contains(pt) for r, _ in self.o.lignes_page(self.num)) else Qt.ArrowCursor)
            self.update()
            return
        if e.buttons() & Qt.LeftButton:
            self.o.etendre_selection(self.num, pt)
        else:
            self.setCursor(Qt.IBeamCursor if self.o.mot_sous(self.num, pt) is not None else
                           (Qt.CrossCursor if self.o.mode in ("ajout_texte", "signature") else Qt.ArrowCursor))

    def mouseReleaseEvent(self, e):
        if self.o.mode is None and self.o.selection and self.o.selection["page"] == self.num:
            self.o.montrer_barre_rapide(self, e.position())


# ---------------------------------------------------------------- barre rapide
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


# ---------------------------------------------------------------- dialogues
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
        self.b_tout = bb.addButton("Remplacer tout", QDialogButtonBox.AcceptRole)
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


# ---------------------------------------------------------------- onglet
class OngletDocument(QWidget):
    titre_change = Signal()
    outil_demande = Signal(str)
    statut = Signal(str)

    def __init__(self, params, chemin=None, doc=None, nom=None):
        super().__init__()
        self.params = params
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
        self.resultats, self.resultat_courant = [], None
        self.mode = None
        self.annulations = []
        self.chiffrement = None
        self._cache_lignes = {}
        self._cache_mots = {}
        self._construire()

    # ---- interface
    def _construire(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        v.addWidget(self._barre_outils())
        self.bandeau = QFrame()
        self.bandeau.setStyleSheet("QFrame{background:#fbe8f2;border-bottom:1px solid #efc7dc} QLabel{color:#6b0f41}"
                                   "QPushButton{background:#fff;border:1px solid #e3b5cf;border-radius:6px;padding:6px 12px;color:#6b0f41}")
        bh = QHBoxLayout(self.bandeau)
        bh.setContentsMargins(16, 6, 16, 6)
        self.bandeau_txt = QLabel()
        bh.addWidget(self.bandeau_txt)
        bh.addStretch()
        self.b_ajout_texte = QPushButton("+ Texte")
        self.b_ajout_texte.clicked.connect(lambda: self.changer_mode("ajout_texte"))
        bh.addWidget(self.b_ajout_texte)
        fin = QPushButton("Terminer")
        fin.setStyleSheet("background:#b0186b;color:#fff;border:none;font-weight:600")
        fin.clicked.connect(lambda: self.changer_mode(None))
        bh.addWidget(fin)
        self.bandeau.hide()
        v.addWidget(self.bandeau)
        sp = QHBoxLayout()
        sp.setContentsMargins(0, 0, 0, 0)
        sp.setSpacing(0)
        self.vignettes = QListWidget()
        self.vignettes.setViewMode(QListWidget.IconMode)
        self.vignettes.setFlow(QListWidget.TopToBottom)
        self.vignettes.setMovement(QListWidget.Snap)
        self.vignettes.setDragDropMode(QAbstractItemView.InternalMove)
        self.vignettes.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.vignettes.setIconSize(QSize(96, 128))
        self.vignettes.setSpacing(6)
        self.vignettes.setFixedWidth(150)
        self.vignettes.setStyleSheet("QListWidget{background:#fafafa;border:none;border-right:1px solid #e2e2e2}")
        self.vignettes.itemClicked.connect(lambda it: self.aller_a(it.data(Qt.UserRole)))
        self.vignettes.setContextMenuPolicy(Qt.CustomContextMenu)
        self.vignettes.customContextMenuRequested.connect(self._menu_vignette)
        self.vignettes.model().rowsMoved.connect(self._pages_deplacees)
        sp.addWidget(self.vignettes)
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
        sp.addWidget(self.zone, 1)
        self.volet = self._volet()
        sp.addWidget(self.volet)
        v.addLayout(sp, 1)
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
        b.setMinimumWidth(64)
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
        h.addWidget(self._bouton("rechercher", "Rechercher", lambda: self.outil_demande.emit("remplacer"), aide="Rechercher (Ctrl+F)"))
        h.addWidget(self._bouton("annuler", "Annuler", self.annuler, aide="Annuler la dernière modification (Ctrl+Z)"))
        h.addSpacing(10)
        self.lbl_page = QLabel()
        h.addWidget(self.lbl_page)
        h.addSpacing(10)
        h.addWidget(self._bouton("zoom_moins", "Zoom −", lambda: self.changer_zoom(self.zoom / 1.2)))
        self.lbl_zoom = QLabel()
        self.lbl_zoom.setMinimumWidth(48)
        self.lbl_zoom.setAlignment(Qt.AlignCenter)
        h.addWidget(self.lbl_zoom)
        h.addWidget(self._bouton("zoom_plus", "Zoom +", lambda: self.changer_zoom(self.zoom * 1.2)))
        h.addWidget(self._bouton("pivoter", "Pivoter", self.pivoter_courante, aide="Pivoter la page affichée de 90°"))
        h.addSpacing(10)
        h.addWidget(self._bouton("modifier", "Modifier", lambda: self.changer_mode("modifier"), "#b0186b", "Modifier le texte en gardant la police d'origine"))
        h.addWidget(self._bouton("commentaire", "Note", lambda: self.message("Sélectionnez du texte : la barre rapide propose Note, Surligner, Barrer."), "#6d3fc6"))
        h.addWidget(self._bouton("signer", "Signer", lambda: self.outil_demande.emit("remplir_signer"), "#6d3fc6", "Apposer votre signature manuscrite"))
        h.addStretch()
        return w

    def _volet(self):
        w = QFrame()
        w.setFixedWidth(290)
        w.setStyleSheet("QFrame#volet{background:#fff;border-left:1px solid #e2e2e2}")
        w.setObjectName("volet")
        self.volet_layout = QVBoxLayout(w)
        self.volet_layout.setContentsMargins(14, 16, 14, 16)
        self.volet_layout.setSpacing(4)
        self.remplir_volet()
        return w

    def remplir_volet(self):
        l = self.volet_layout
        while l.count():
            it = l.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        t = QLabel("MES OUTILS")
        t.setStyleSheet("font-size:12px;font-weight:600;color:#555;letter-spacing:1px")
        l.addWidget(t)
        for oid in self.params["outils_epingles"]:
            o = outil(oid)
            if not o:
                continue
            _, _, coul, fond = famille(o[1])
            b = QPushButton("  " + o[3])
            b.setIcon(icone(o[2], coul))
            b.setIconSize(QSize(20, 20))
            b.setToolTip(o[5])
            b.setStyleSheet("QPushButton{text-align:left;padding:9px 8px;border:none;border-radius:8px;font-size:14px}"
                            f"QPushButton:hover{{background:{fond}}}")
            b.clicked.connect(lambda _=False, x=oid: self.outil_demande.emit(x))
            l.addWidget(b)
        tous = QPushButton("  +  Tous les outils")
        tous.setStyleSheet("QPushButton{text-align:left;padding:9px 8px;border:1px dashed #cfcfcf;border-radius:8px;font-size:14px}")
        tous.clicked.connect(lambda: self.outil_demande.emit("__outils__"))
        l.addWidget(tous)
        l.addSpacing(14)
        ia = QFrame()
        ia.setStyleSheet("QFrame{background:#f2fafa;border:1px solid #cfe9ea;border-radius:10px}")
        iv = QVBoxLayout(ia)
        it = QLabel("✦ Assistant IA")
        it.setStyleSheet("font-weight:600;color:#0b5e63;border:none")
        iv.addWidget(it)
        im = QLabel("Prévu en V3 : résumé, points clefs, remise en page avec Claude ou Gemini. Rien n'est envoyé sans votre clic.")
        im.setWordWrap(True)
        im.setStyleSheet("font-size:12px;color:#3d5c5e;border:none")
        iv.addWidget(im)
        l.addWidget(ia)
        l.addStretch()
        self.lbl_info = QLabel()
        self.lbl_info.setWordWrap(True)
        self.lbl_info.setStyleSheet("font-size:12px;color:#555")
        l.addWidget(self.lbl_info)
        self.maj_info()

    def maj_info(self):
        if hasattr(self, "lbl_info"):
            self.lbl_info.setText(f"{len(self.doc)} page{'s' if len(self.doc) > 1 else ''}"
                                  + (f" · {self.poids_initial // 1024} Ko à l'ouverture" if self.poids_initial else "")
                                  + (" · modifié, non enregistré" if self.modifie else ""))

    # ---- pages
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
        self._cache_lignes.clear()
        self._cache_mots.clear()
        self.construire_vignettes()
        self.lbl_zoom.setText(f"{round(self.zoom * 100)} %")
        self._page_visible()
        self.maj_info()

    def construire_vignettes(self):
        self.vignettes.blockSignals(True)
        self.vignettes.clear()
        for n, page in enumerate(self.doc):
            k = 120 / max(page.rect.width, page.rect.height)
            pm = page.get_pixmap(matrix=fitz.Matrix(k, k).prerotate(self.rotation_vue.get(n, 0)), alpha=False)
            img = QImage(pm.samples, pm.width, pm.height, pm.stride, QImage.Format_RGB888).copy()
            it = QListWidgetItem(icone("creer"), str(n + 1))
            it.setIcon(QPixmap.fromImage(img))
            it.setData(Qt.UserRole, n)
            it.setTextAlignment(Qt.AlignHCenter)
            self.vignettes.addItem(it)
        self.vignettes.blockSignals(False)

    def rafraichir_pages(self, refaire=False):
        if refaire:
            self._cache_lignes.clear()
            self._cache_mots.clear()
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
        if hasattr(self, "page_widgets") and self.page_widgets:
            self.lbl_page.setText(f"Page {self.page_courante() + 1} sur {len(self.doc)}")

    def aller_a(self, n, rect=None):
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

    # ---- texte
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

    def mots(self, n):
        if n not in self._cache_mots:
            w = self.doc[n].get_text("words", sort=True)
            self._cache_mots[n] = w
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

    def _calculer_selection(self):
        s = self.selection
        if s:
            a, b = sorted((s["debut"], s["fin"]))
            mots = self.mots(s["page"])[a:b + 1]
            groupes = {}
            for w in mots:
                cle = (w[5], w[6])
                groupes.setdefault(cle, fitz.Rect(w[:4]))
                groupes[cle] |= fitz.Rect(w[:4])
            s["lignes"] = list(groupes.values())
            lignes_txt, cle_prec = [], None
            for w in mots:
                cle = (w[5], w[6])
                if cle != cle_prec:
                    lignes_txt.append([])
                lignes_txt[-1].append(w[4])
                cle_prec = cle
            s["texte"] = "\n".join(" ".join(x) for x in lignes_txt)
        self.rafraichir_pages()

    def montrer_barre_rapide(self, pw, pos):
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

    def copier(self):
        if self.selection:
            QGuiApplication.clipboard().setText(self.selection["texte"])
            self.message("Texte copié.")

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
                return
            r = s["lignes"][-1]
            a = page.add_text_annot(fitz.Point(r.x1 + 2, r.y0), txt, icon="Comment")
        a.set_info(title=self.params["machine"])
        a.update()
        self.selection = None
        self.apres_modif()

    def biffer(self):
        s = self.selection
        if not s:
            return
        if QMessageBox.question(self, "Biffer", "Le texte sélectionné sera supprimé définitivement du fichier "
                                "et remplacé par un rectangle noir. Continuer ?") != QMessageBox.Yes:
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
        ancien = s["texte"].split("\n")[0]
        nouveau, ok = QInputDialog.getText(self, "Modifier le texte", "Nouveau texte :", text=ancien)
        if ok and nouveau != ancien:
            self._remplacer(s["page"], ancien, nouveau, s["lignes"][0])
        self.selection = None

    def modifier_ligne(self, n, rect, texte):
        nouveau, ok = QInputDialog.getText(self, "Modifier la ligne", "Texte :", text=texte)
        if ok and nouveau != texte:
            self._remplacer(n, texte.rstrip(), nouveau.rstrip(), rect)

    def _remplacer(self, n, ancien, nouveau, zone):
        self.memoriser()
        ed = Editeur(self.doc)
        try:
            ed.remplacer(n, ancien.strip(), nouveau.strip(), zone=zone)
        except ValueError as e:
            self.annulations.pop()
            self.message(str(e))
            return
        self.apres_modif(ed.journal)

    def ajouter_texte_ici(self, n, pt):
        txt, ok = QInputDialog.getText(self, "Ajouter du texte", "Texte :")
        if ok and txt:
            self.memoriser()
            ed = Editeur(self.doc)
            ed.ajouter_texte(n, pt, txt)
            self.apres_modif(ed.journal)
        self.changer_mode("modifier")

    def placer_signature(self, n, pt):
        img = os.path.join(self.params_dossier(), "signature.png")
        self.memoriser()
        page = self.doc[n]
        pix = fitz.Pixmap(img)
        w = 150
        h = w * pix.height / pix.width
        page.insert_image(fitz.Rect(pt.x - w / 2, pt.y - h / 2, pt.x + w / 2, pt.y + h / 2), filename=img)
        self.changer_mode(None)
        self.apres_modif(["Signature apposée."])

    def params_dossier(self):
        from .config import dossier_donnees
        return self.params["dossier_synchro"] or dossier_donnees()

    def changer_mode(self, mode):
        self.mode = mode
        self.barre_rapide.hide()
        self.selection = None
        if mode == "modifier":
            self.bandeau_txt.setText("<b>Mode Modifier</b> — cliquez sur une ligne pour la corriger, la police d'origine est conservée.")
            self.bandeau.show()
        elif mode == "ajout_texte":
            self.bandeau_txt.setText("<b>Ajouter du texte</b> — cliquez à l'endroit voulu.")
            self.bandeau.show()
        elif mode == "signature":
            self.bandeau_txt.setText("<b>Signer</b> — cliquez à l'endroit où placer votre signature.")
            self.bandeau.show()
        else:
            self.bandeau.hide()
        self.rafraichir_pages()

    # ---- pages : rotation, organisation
    def pivoter_courante(self):
        self.pivoter([self.page_courante()])

    def pivoter(self, pages, angle=90):
        m = QMessageBox(self)
        m.setWindowTitle("Pivoter")
        m.setText(f"Conserver cette orientation dans le fichier ?")
        m.setInformativeText("Oui : la page reste tournée à l'enregistrement.\nNon : seulement pour l'affichage.")
        oui = m.addButton("Oui, dans le fichier", QMessageBox.YesRole)
        m.addButton("Seulement l'affichage", QMessageBox.NoRole)
        m.exec()
        if m.clickedButton() is oui:
            self.memoriser()
            for n in pages:
                self.doc[n].set_rotation((self.doc[n].rotation + angle) % 360)
            self.apres_modif()
        else:
            for n in pages:
                self.rotation_vue[n] = (self.rotation_vue.get(n, 0) + angle) % 360
            for n in pages:
                self.page_widgets[n].maj_taille()
            self.construire_vignettes()

    def _menu_vignette(self, pos):
        pages = sorted(it.data(Qt.UserRole) for it in self.vignettes.selectedItems())
        if not pages:
            return
        m = QMenu(self)
        m.addAction(icone("pivoter"), "Pivoter de 90°", lambda: self.pivoter(pages))
        m.addAction(icone("exporter"), "Extraire dans un nouveau PDF", lambda: self.extraire(pages))
        m.addAction(icone("fermer", "#c9252d"), "Supprimer", lambda: self.supprimer_pages(pages))
        m.exec(self.vignettes.mapToGlobal(pos))

    def supprimer_pages(self, pages):
        if len(pages) >= len(self.doc):
            self.message("Impossible de supprimer toutes les pages.")
            return
        self.memoriser()
        self.doc.delete_pages(pages)
        self.apres_modif(reconstruire=True)

    def extraire(self, pages):
        nd = fitz.open()
        for n in pages:
            nd.insert_pdf(self.doc, from_page=n, to_page=n)
        self.outil_demande.emit("__nouveau__")
        self._extrait = nd

    def _pages_deplacees(self, *a):
        ordre = [self.vignettes.item(i).data(Qt.UserRole) for i in range(self.vignettes.count())]
        if ordre != sorted(ordre):
            self.memoriser()
            self.doc.select(ordre)
            QTimer.singleShot(0, lambda: self.apres_modif(reconstruire=True))

    # ---- historique
    def memoriser(self):
        self.annulations.append(self.doc.tobytes())
        self.annulations = self.annulations[-30:]

    def annuler(self):
        if not self.annulations:
            self.message("Rien à annuler.")
            return
        self.doc = fitz.open(stream=self.annulations.pop(), filetype="pdf")
        self.modifie = True
        self.construire_pages()
        self.titre_change.emit()

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

    # ---- enregistrement
    def enregistrer(self, chemin):
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
