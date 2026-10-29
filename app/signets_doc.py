"""Signets dans le volet gauche, a cote des vignettes : un onglet « Pages | Signets » en haut du volet.
Le volet garde sa largeur et se masque avec le meme bouton que les vignettes ; il s'ouvre toujours sur les pages
(les signets ne s'imposent jamais), et l'onglet Signets indique combien le document en a."""
import pymupdf as fitz
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QToolButton, QStackedWidget, QTreeWidget,
                               QTreeWidgetItem, QLabel, QMenu, QAbstractItemView, QPushButton, QSizePolicy)

from .langue import _


class MixinSignets:
    def _volet_gauche(self):
        """Le volet gauche : onglets Pages / Signets, puis les vignettes ou l'arbre des signets."""
        self.gauche = QWidget()
        self.gauche.setObjectName("volet_gauche")
        self.gauche.setMinimumWidth(110)
        self.gauche.setStyleSheet("QWidget#volet_gauche{background:#fafafa;border-right:1px solid #e2e2e2}")
        v = QVBoxLayout(self.gauche)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        h = QHBoxLayout()
        h.setContentsMargins(4, 4, 4, 2)
        h.setSpacing(2)
        style = ("QToolButton{border:none;border-radius:4px;padding:3px 4px;color:#555;font-size:12px}"
                 "QToolButton:checked{background:#e4e9f2;color:#123;font-weight:600}")
        self.b_onglet_pages = QToolButton()
        self.b_onglet_pages.setText(_("Pages"))
        self.b_onglet_signets = QToolButton()
        for b in (self.b_onglet_pages, self.b_onglet_signets):
            b.setCheckable(True)
            b.setAutoExclusive(True)
            b.setStyleSheet(style)
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            h.addWidget(b)
        self.b_onglet_pages.setChecked(True)
        self.b_onglet_pages.clicked.connect(lambda: self.montrer_signets(False))
        self.b_onglet_signets.clicked.connect(lambda: self.montrer_signets(True))
        v.addLayout(h)
        self.pile_gauche = QStackedWidget()
        self.pile_gauche.addWidget(self.vignettes)
        self.pile_gauche.addWidget(self._panneau_signets())
        v.addWidget(self.pile_gauche, 1)
        return self.gauche

    def _panneau_signets(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(4, 2, 4, 4)
        v.setSpacing(4)
        self.arbre_signets = QTreeWidget()
        self.arbre_signets.setObjectName("arbre_signets")
        self.arbre_signets.setHeaderHidden(True)
        self.arbre_signets.setStyleSheet("QTreeWidget{background:#fafafa;border:none}")
        self.arbre_signets.setEditTriggers(QAbstractItemView.EditKeyPressed | QAbstractItemView.SelectedClicked)
        self.arbre_signets.setDragDropMode(QAbstractItemView.InternalMove)
        self.arbre_signets.itemClicked.connect(self._aller_signet)
        self.arbre_signets.itemChanged.connect(self._signet_renomme)
        self.arbre_signets.setContextMenuPolicy(Qt.CustomContextMenu)
        self.arbre_signets.customContextMenuRequested.connect(self._menu_signets)
        self.arbre_signets.model().rowsMoved.connect(lambda *_a: self._signets_deplaces())
        self.arbre_signets.setWordWrap(True)
        v.addWidget(self.arbre_signets, 1)
        self.l_sans_signet = QLabel(_("Aucun signet dans ce document."))
        self.l_sans_signet.setWordWrap(True)
        self.l_sans_signet.setStyleSheet("color:#777;font-size:12px;padding:6px")
        v.addWidget(self.l_sans_signet)
        b = QPushButton(_("+ Signet ici"))
        b.setToolTip(_("Signet sur la page affichée, nommé d'après le texte sélectionné, sinon « Page n » ; "
                       "clic droit sur un signet : renommer, sous-signet, supprimer ; glisser pour réordonner"))
        b.clicked.connect(lambda: self.ajouter_signet())
        v.addWidget(b)
        return w

    def montrer_signets(self, oui):
        self.pile_gauche.setCurrentIndex(1 if oui else 0)
        (self.b_onglet_signets if oui else self.b_onglet_pages).setChecked(True)
        if oui:
            self.remplir_signets()
        if not self.gauche.isVisible():
            self.basculer_vignettes()

    def maj_onglet_signets(self):
        if not hasattr(self, "b_onglet_signets"):
            return
        n = len(self.doc.get_toc())
        self.b_onglet_signets.setText(_("Signets · {n}", n=n) if n else _("Signets"))
        if self.pile_gauche.currentIndex() == 1:
            self.remplir_signets()

    # ---- lecture / ecriture de la table des signets
    def remplir_signets(self):
        a = self.arbre_signets
        a.blockSignals(True)
        a.clear()
        pile = [(0, a.invisibleRootItem())]
        toc = self.doc.get_toc(simple=False)
        for i, (lvl, titre, page, *reste) in enumerate(toc):
            while pile and pile[-1][0] >= lvl:
                pile.pop()
            parent = pile[-1][1] if pile else a.invisibleRootItem()
            it = QTreeWidgetItem([titre])
            it.setToolTip(0, _("{t} — page {p}", t=titre, p=page) if page > 0 else titre)
            it.setData(0, Qt.UserRole, (page, (reste[0] if reste else {}) or {}))
            it.setFlags(it.flags() | Qt.ItemIsEditable)
            parent.addChild(it)
            pile.append((lvl, it))
        a.expandToDepth(0)
        a.blockSignals(False)
        self.l_sans_signet.setVisible(not toc)

    def _toc_depuis_arbre(self):
        out = []

        def parcourir(it, lvl):
            for k in range(it.childCount()):
                c = it.child(k)
                page, dest = c.data(0, Qt.UserRole) or (1, {})
                out.append([lvl, c.text(0), page, dest] if dest else [lvl, c.text(0), page])
                parcourir(c, lvl + 1)
        parcourir(self.arbre_signets.invisibleRootItem(), 1)
        return out

    def _ecrire_signets(self, toc, libelle):
        self.memoriser(libelle)
        propre = []
        for e in toc:
            d = dict(e[3]) if len(e) > 3 and isinstance(e[3], dict) else None
            if d:                                    # garder le point vise dans la page
                d = {k: v for k, v in d.items() if k in ("kind", "page", "to", "zoom", "collapse", "color", "bold",
                                                         "italic")}
            propre.append([e[0], e[1], e[2], d] if d else [e[0], e[1], e[2]])
        try:
            self.doc.set_toc(propre)
        except Exception:                            # noqa: BLE001  (destination illisible : on garde la page seule)
            self.doc.set_toc([e[:3] for e in propre])
        self.modifie = True
        self.titre_change.emit()
        self.maj_onglet_signets()

    def _aller_signet(self, it, _col=0):
        page, dest = it.data(0, Qt.UserRole) or (0, {})
        if page and page > 0:
            to = dest.get("to") if isinstance(dest, dict) else None
            r = None
            if isinstance(to, fitz.Point) and (to.x or to.y):
                r = fitz.Rect(to.x, to.y, to.x + 1, to.y + 1)
            self.aller_a(page - 1, r)

    def _signet_renomme(self, it, _col=0):
        self._ecrire_signets(self._toc_depuis_arbre(), _("Signet renommé"))

    def _signets_deplaces(self):
        self._ecrire_signets(self._toc_depuis_arbre(), _("Signets réordonnés"))

    def ajouter_signet(self, parent_it=None):
        n = self.page_courante()
        titre = (self.selection or {}).get("texte", "").split("\n")[0].strip()[:120] if getattr(self, "selection", None) else ""
        titre = titre or _("Page {n}", n=n + 1)
        toc = self.doc.get_toc(simple=False)
        lvl = 1
        if parent_it is not None:                    # sous-signet : juste apres le parent et ses enfants
            idx = self._index_signet(parent_it)
            lvl = toc[idx][0] + 1
            pos = idx + 1
            while pos < len(toc) and toc[pos][0] >= lvl:
                pos += 1
        else:                                        # a sa place dans l'ordre des pages
            pos = next((i for i, e in enumerate(toc) if e[0] == 1 and e[2] > n + 1), len(toc))
        toc.insert(pos, [lvl, titre, n + 1])
        self._ecrire_signets(toc, _("Signet ajouté"))
        self.montrer_signets(True)
        it = self._item_signet(pos)
        if it is not None:
            self.arbre_signets.setCurrentItem(it)
            self.arbre_signets.editItem(it, 0)

    def _index_signet(self, item):
        k, cible = 0, None
        pile = [self.arbre_signets.invisibleRootItem()]
        ordre = []

        def parcourir(it):
            for j in range(it.childCount()):
                ordre.append(it.child(j))
                parcourir(it.child(j))
        parcourir(pile[0])
        return ordre.index(item)

    def _item_signet(self, idx):
        ordre = []

        def parcourir(it):
            for j in range(it.childCount()):
                ordre.append(it.child(j))
                parcourir(it.child(j))
        parcourir(self.arbre_signets.invisibleRootItem())
        return ordre[idx] if 0 <= idx < len(ordre) else None

    def supprimer_signet(self, it):
        toc = self.doc.get_toc(simple=False)
        i = self._index_signet(it)
        lvl = toc[i][0]
        j = i + 1
        while j < len(toc) and toc[j][0] > lvl:      # le signet et ses sous-signets
            j += 1
        del toc[i:j]
        self._ecrire_signets(toc, _("Signet supprimé"))

    def _menu_signets(self, pos):
        it = self.arbre_signets.itemAt(pos)
        m = QMenu(self)
        m.addAction(_("Ajouter un signet sur la page affichée"), lambda: self.ajouter_signet())
        if it is not None:
            m.addAction(_("Ajouter un sous-signet"), lambda: self.ajouter_signet(it))
            m.addAction(_("Renommer"), lambda: self.arbre_signets.editItem(it, 0))
            m.addAction(_("Mettre sur la page affichée"), lambda: self._signet_ici(it))
            m.addSeparator()
            m.addAction(_("Supprimer"), lambda: self.supprimer_signet(it))
        if self.doc.get_toc():
            m.addSeparator()
            m.addAction(_("Tout déplier"), self.arbre_signets.expandAll)
            m.addAction(_("Tout replier"), self.arbre_signets.collapseAll)
        m.exec(self.arbre_signets.viewport().mapToGlobal(pos))

    def _signet_ici(self, it):
        toc = self.doc.get_toc(simple=False)
        i = self._index_signet(it)
        toc[i] = [toc[i][0], toc[i][1], self.page_courante() + 1]
        self._ecrire_signets(toc, _("Signet déplacé"))
