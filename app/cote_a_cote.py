"""Deux fichiers cote a cote dans la fenetre : le fichier de droite sort de sa ligne d'onglets et s'affiche a cote
de l'onglet courant. Chacun garde son zoom, son defilement et ses outils ; le dernier clique est le document
« courant » (menus, raccourcis). « Remettre en onglet » le replace ou il etait."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QSplitter, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QToolButton, QMenu,
                               QApplication, QFrame)

from .langue import _
from .icones import icone


class MixinCoteACote:
    def _construire_cote_a_cote(self):
        """A appeler apres la creation de self.onglets : la zone centrale devient un separateur a deux volets."""
        self.doc_droite = None
        self._focus_droite = False
        self.sep_central = QSplitter(Qt.Horizontal)
        self.sep_central.setChildrenCollapsible(False)
        self.sep_central.addWidget(self.onglets)
        self.droite = QFrame()
        self.droite.setObjectName("cote_a_cote")
        self.droite.setStyleSheet("QFrame#cote_a_cote{border-left:3px solid #0f6cbd;background:#fff}")
        v = QVBoxLayout(self.droite)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        tete = QWidget()
        tete.setStyleSheet("background:#eef4fb")
        h = QHBoxLayout(tete)
        h.setContentsMargins(10, 6, 6, 6)
        self.l_droite = QLabel()
        self.l_droite.setStyleSheet("font-weight:600;font-size:14px")
        h.addWidget(self.l_droite, 1)
        b = QToolButton()
        b.setText(_("Changer de fichier"))
        b.setPopupMode(QToolButton.InstantPopup)
        self.menu_droite = QMenu(b)
        self.menu_droite.aboutToShow.connect(self._remplir_menu_droite)
        b.setMenu(self.menu_droite)
        h.addWidget(b)
        b = QToolButton()
        b.setText(_("Échanger"))
        b.setToolTip(_("Passer le fichier de droite à gauche et inversement"))
        b.clicked.connect(self.echanger_cote_a_cote)
        h.addWidget(b)
        b = QToolButton()
        b.setIcon(icone("fermer", "#444444"))
        b.setText(_("Remettre en onglet"))
        b.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        b.setToolTip(_("Fin du côte à côte : le fichier retourne dans les onglets"))
        b.clicked.connect(self.fermer_cote_a_cote)
        h.addWidget(b)
        v.addWidget(tete)
        self.porte_droite = QVBoxLayout()
        self.porte_droite.setContentsMargins(0, 0, 0, 0)
        v.addLayout(self.porte_droite, 1)
        self.sep_central.addWidget(self.droite)
        self.droite.hide()
        QApplication.instance().focusChanged.connect(self._focus_change)
        return self.sep_central

    def _focus_change(self, _ancien, nouveau):
        if self.doc_droite is None or nouveau is None:
            return
        d = self.doc_droite.isAncestorOf(nouveau) or nouveau is self.doc_droite
        g = self.onglets.isAncestorOf(nouveau)
        if d or g:
            self._focus_droite = d
            self.droite.setStyleSheet("QFrame#cote_a_cote{border-left:3px solid %s;background:#fff}"
                                      % ("#0f6cbd" if d else "#c8d6e8"))
            o = self.doc_courant()
            if o is not None:
                self._maj_titre(o)

    def autres_documents(self, sauf=None):
        return [o for o in self.documents() if o is not sauf and o is not self.doc_droite]

    def afficher_a_cote(self, o):
        """Met le document o a droite (s'il etait dans les onglets) ; l'onglet courant reste a gauche."""
        if o is None or o is self.doc_droite:
            return
        gauche = self.onglets.currentWidget()
        if gauche is o:                              # le document courant passe a droite : a gauche, un autre
            autres = self.autres_documents(sauf=o)
            if not autres:
                self.statusBar().showMessage(_("Ouvrez un deuxième fichier pour le côte à côte."), 6000)
                return
            gauche = autres[-1]
        if self.doc_droite is not None:
            self._rendre_onglet(self.doc_droite)
        i = self.onglets.indexOf(o)
        o._index_onglet = i
        self.onglets.removeTab(i)
        self.porte_droite.addWidget(o)
        o.show()
        self.doc_droite = o
        self.droite.show()
        if self.onglets.indexOf(gauche) >= 0:
            self.onglets.setCurrentWidget(gauche)
        t = self.sep_central.width()
        self.sep_central.setSizes([t // 2, t - t // 2])
        for x in (o, gauche):                        # place pour les pages : volets d'outils en icones, le temps
            self._volet_reduit(x)                    # du cote a cote (votre reglage n'est pas change)
        self._maj_titre(o)
        self._maj_onglets_fixes()
        self.statusBar().showMessage(_("Côte à côte : chaque fichier a son zoom ; cliquez dans un fichier pour "
                                       "que les menus s'appliquent à lui."), 8000)

    def _volet_reduit(self, o, reduire=True):
        from .document import OngletDocument
        if not isinstance(o, OngletDocument):
            return
        if reduire and not hasattr(o, "_volet_avant_cote"):
            o._volet_avant_cote = getattr(o, "_mode_volet", "complet")
            if o._volet_avant_cote == "complet":
                o.mode_volet("icones", memoriser=False)
        elif not reduire and hasattr(o, "_volet_avant_cote"):
            o.mode_volet(o.__dict__.pop("_volet_avant_cote"), memoriser=False)

    def _rendre_onglet(self, o):
        self._volet_reduit(o, False)
        self.porte_droite.removeWidget(o)
        i = min(getattr(o, "_index_onglet", self.onglets.count()), self.onglets.count())
        i = max(2, i)
        self.onglets.insertTab(i, o, icone("creer", "#c9252d"), o.nom)
        self.doc_droite = None
        self._focus_droite = False
        self._maj_titre(o)
        return i

    def fermer_cote_a_cote(self):
        if self.doc_droite is None:
            self.droite.hide()
            return
        o = self.doc_droite
        self._rendre_onglet(o)
        self.droite.hide()
        for x in self.documents():
            self._volet_reduit(x, False)
        self._maj_onglets_fixes()

    def echanger_cote_a_cote(self):
        g, d = self.onglets.currentWidget(), self.doc_droite
        from .document import OngletDocument
        if d is None or not isinstance(g, OngletDocument):
            return
        i = self._rendre_onglet(d)
        self.onglets.setCurrentIndex(i)
        self.afficher_a_cote(g)

    def _remplir_menu_droite(self):
        m = self.menu_droite
        m.clear()
        autres = self.autres_documents(sauf=self.onglets.currentWidget())
        for o in autres:
            m.addAction(o.nom, lambda o=o: self.afficher_a_cote(o))
        if autres:
            m.addSeparator()
        m.addAction(_("Ouvrir un autre fichier..."), lambda: self._ouvrir_a_cote())

    def _ouvrir_a_cote(self):
        avant = set(map(id, self.documents()))
        gauche = self.onglets.currentWidget()
        self.dialogue_ouvrir()
        nouveaux = [o for o in self.documents() if id(o) not in avant]
        if nouveaux:
            if self.onglets.indexOf(gauche) >= 0:
                self.onglets.setCurrentWidget(gauche)
            self.afficher_a_cote(nouveaux[-1])

    def menu_cote_a_cote(self):
        """Menu Affichage › Cote a cote : choisir le fichier a mettre a droite."""
        from .document import OngletDocument
        courant = self.onglets.currentWidget()
        autres = self.autres_documents(sauf=courant if isinstance(courant, OngletDocument) else None)
        m = QMenu(self)
        for o in autres:
            m.addAction(_("A côté : {nom}", nom=o.nom), lambda o=o: self.afficher_a_cote(o))
        if autres:
            m.addSeparator()
        m.addAction(_("Ouvrir un fichier à côté..."), self._ouvrir_a_cote)
        if self.doc_droite is not None:
            m.addAction(_("Fin du côte à côte"), self.fermer_cote_a_cote)
        from PySide6.QtGui import QCursor
        m.exec(QCursor.pos())

    def onglet_precedent(self):
        n = self.onglets.count()
        i = self.onglets.currentIndex()
        for k in range(1, n + 1):
            j = (i - k) % n
            if self.onglets.tabBar().isTabVisible(j):
                self.onglets.setCurrentIndex(j)
                return
