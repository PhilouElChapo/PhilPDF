"""Fenetre principale de PhilPDF : menus, onglets, aiguillage des outils."""
import os, sys
import pymupdf as fitz
from PySide6.QtCore import Qt, QThread, Signal, QSize
from PySide6.QtGui import QAction, QKeySequence, QImage, QPainter
from PySide6.QtWidgets import (QMainWindow, QTabWidget, QFileDialog, QMessageBox, QDialog, QFormLayout,
                               QLineEdit, QCheckBox, QComboBox, QDialogButtonBox, QListWidget, QVBoxLayout,
                               QHBoxLayout, QPushButton, QLabel, QProgressDialog, QApplication, QInputDialog,
                               QListWidgetItem, QWidget)
from PySide6.QtPrintSupport import QPrinter, QPrintDialog
from .config import Parametres, VERSION, est_portable, associer_pdf, dossier_donnees
from .icones import icone, logo
from .pages import PageOutils, PageAccueil
from .document import OngletDocument, DialogueRemplacer, question
from .outils import outil
from .bibliotheque import Bibliotheque, detecter_clouds
from .session import session_de, date_fr, nb_fichiers
from .dialogues import (boutons_fr, DialogueFiligrane, DialogueEntete, DialogueNumeriser, DialogueExporter,
                        DialogueBibliotheque, DialogueReprise)

FILTRE = "Documents PDF (*.pdf *.PDF)"


class TacheScan(QThread):
    fini = Signal(str, str)

    def __init__(self, entree, sortie):
        super().__init__()
        self.entree, self.sortie = entree, sortie

    def run(self):
        try:
            from moteur.scan import traiter
            traiter(self.entree, self.sortie)
            self.fini.emit(self.sortie, "")
        except Exception as e:
            self.fini.emit("", str(e))


class TacheMaj(QThread):
    trouve = Signal(object)

    def __init__(self, params):
        super().__init__()
        self.params = params

    def run(self):
        from .mise_a_jour import chercher
        self.trouve.emit(chercher(self.params))


class Fenetre(QMainWindow):
    def __init__(self, fichiers=()):
        super().__init__()
        self.params = Parametres()
        self.biblio = Bibliotheque(self.params)
        self.dernier_doc = None
        self.setWindowTitle("PhilPDF")
        self.setWindowIcon(logo(64))
        self.resize(1400, 900)
        self.onglets = QTabWidget()
        self.onglets.setDocumentMode(True)
        self.onglets.setTabsClosable(True)
        self.onglets.setMovable(True)
        self.onglets.tabCloseRequested.connect(self.fermer_onglet)
        self.onglets.currentChanged.connect(self._onglet_change)
        self.onglets.setStyleSheet(
            "QTabBar::tab{padding:10px 18px;font-size:14px;background:#ececec;border:none}"
            "QTabBar::tab:selected{background:#fff;border-top:3px solid #c9252d;font-weight:600}"
            "QTabWidget::pane{border:none}")
        self.accueil = PageAccueil(self.params)
        self.accueil.ouvrir.connect(self.ouvrir)
        self.accueil.ouvrir_dialogue.connect(self.dialogue_ouvrir)
        self.accueil.reprendre.connect(self.reprendre_session)
        self.outils = PageOutils(self.params)
        self.outils.outil_choisi.connect(self.lancer_outil)
        self.outils.epingles_changes.connect(self._epingles)
        self.onglets.addTab(self.accueil, "Accueil")
        self.onglets.addTab(self.outils, "Outils")
        for i in (0, 1):
            self.onglets.tabBar().setTabButton(i, self.onglets.tabBar().ButtonPosition.RightSide, None)
        self.setCentralWidget(self.onglets)
        self._menus()
        self.statusBar().showMessage(f"PhilPDF {VERSION}" + (" · version portable" if est_portable() else ""))
        self.taches = []
        for f in fichiers:
            self.ouvrir(f)
        import datetime
        aujourd_hui = datetime.date.today().isoformat()
        if self.params.get("maj_auto", True) and self.params.get("maj_derniere") != aujourd_hui:
            self.params["maj_derniere"] = aujourd_hui
            self.params.enregistrer()
            self.verifier_maj(silencieux=True)
        from PySide6.QtCore import QTimer
        QTimer.singleShot(800, self.proposer_reprise)
        self._minuterie = QTimer(self)
        self._minuterie.timeout.connect(self._session)
        self._minuterie.start(60000)       # page courante memorisee chaque minute
        # nouveau PC : proposer de recuperer tampons et signatures sauvegardes sur le Drive
        nouv = self.biblio.nouveautes_drive()
        if nouv and not self.params.get("drive_restaure"):
            self.params["drive_restaure"] = True
            self.params.enregistrer()
            if question(self, "Drive", f"{len(nouv)} tampon(s) / signature(s) sauvegardés sur votre Drive ne sont pas sur ce PC. "
                        "Les récupérer ?", [("Récupérer", QMessageBox.AcceptRole), ("Plus tard", QMessageBox.RejectRole)]) == 0:
                self.biblio.restaurer_drive()

    # ------------------------------------------------------------ menus
    def _menus(self):
        mb = self.menuBar()

        def act(menu, texte, f, raccourci=None, ic=None, actif=True):
            a = QAction(icone(ic) if ic else QAction().icon(), texte, self) if ic else QAction(texte, self)
            if raccourci:
                a.setShortcut(QKeySequence(raccourci))
            a.triggered.connect(f)
            a.setEnabled(actif)
            menu.addAction(a)
            return a

        m = mb.addMenu("&Fichier")
        act(m, "Ouvrir...", self.dialogue_ouvrir, "Ctrl+O", "ouvrir")
        self.menu_recents = m.addMenu("Ouvrir un fichier récent")
        self.menu_recents.aboutToShow.connect(self._remplir_recents)
        act(m, "Reprendre la session d'une autre machine...", self.choisir_session)
        sm = m.addMenu(icone("creer"), "Créer un PDF")
        act(sm, "Page vierge", lambda: self.creer("vierge"))
        act(sm, "A partir d'images...", lambda: self.creer("images"))
        act(sm, "A partir de plusieurs fichiers (combiner)...", lambda: self.lancer_outil("combiner"))
        act(sm, "Depuis le scanner...", lambda: self.lancer_outil("numeriser"))
        m.addSeparator()
        act(m, "Enregistrer", lambda: self.enregistrer(), "Ctrl+S", "enregistrer")
        act(m, "Enregistrer sous...", lambda: self.enregistrer(sous=True), "Shift+Ctrl+S")
        act(m, "Enregistrer une copie allégée...", lambda: self.lancer_outil("alleger"))
        sm = m.addMenu("Exporter vers")
        act(sm, "Word (.docx)...", lambda: self.exporter("docx"))
        act(sm, "Images JPG...", lambda: self.exporter("jpg"))
        act(sm, "Images PNG...", lambda: self.exporter("png"))
        act(sm, "Texte (.txt)...", lambda: self.exporter("txt"))
        m.addSeparator()
        act(m, "Imprimer...", lambda: self.lancer_outil("imprimer"), "Ctrl+P", "imprimer")
        act(m, "Imprimer plusieurs documents...", self.imprimer_plusieurs)
        m.addSeparator()
        act(m, "Protéger à l'aide d'un mot de passe...", lambda: self.lancer_outil("motdepasse"))
        act(m, "Propriétés...", self.proprietes, "Ctrl+D")
        m.addSeparator()
        act(m, "Fermer le fichier", lambda: self.fermer_onglet(self.onglets.currentIndex()), "Ctrl+W")
        act(m, "Quitter", self.close, "Ctrl+Q")

        m = mb.addMenu("&Edition")
        d = lambda nom: (lambda: getattr(self.doc_courant(), nom)() if self.doc_courant() else None)
        act(m, "Annuler", d("annuler"), "Ctrl+Z", "annuler")
        act(m, "Rétablir", d("retablir"), "Shift+Ctrl+Z")
        m.addSeparator()
        act(m, "Couper", d("couper"), "Ctrl+X")
        act(m, "Copier", d("copier"), "Ctrl+C", "copier")
        act(m, "Coller", d("coller"), "Ctrl+V")
        act(m, "Supprimer", d("supprimer"), "Del")
        m.addSeparator()
        act(m, "Sélectionner tout", d("tout_selectionner"), "Ctrl+A")
        act(m, "Désélectionner tout", lambda: self.doc_courant() and (setattr(self.doc_courant(), "selection", None),
                                                                     self.doc_courant().choisir_objet(None)), "Shift+Ctrl+A")
        m.addSeparator()
        act(m, "Modifier le texte et les images", lambda: self.lancer_outil("modifier"), None, "modifier")
        act(m, "Rechercher et remplacer...", lambda: self.lancer_outil("remplacer"), "Ctrl+F", "rechercher")
        m.addSeparator()
        act(m, "Préférences...", self.preferences, "Ctrl+K", "parametres")

        m = mb.addMenu("&Affichage")
        act(m, "Pivoter la page (90°)", lambda: self.doc_courant() and self.doc_courant().pivoter_courante(), "Shift+Ctrl++", "pivoter")
        act(m, "Zoom avant", lambda: self.doc_courant() and self.doc_courant().changer_zoom(self.doc_courant().zoom * 1.2), "Ctrl++")
        act(m, "Zoom arrière", lambda: self.doc_courant() and self.doc_courant().changer_zoom(self.doc_courant().zoom / 1.2), "Ctrl+-")
        act(m, "Taille réelle", lambda: self.doc_courant() and self.doc_courant().changer_zoom(1.0), "Ctrl+1")
        act(m, "Ajuster à la largeur", self.ajuster_largeur, "Ctrl+2")
        m.addSeparator()
        a = act(m, "Barre d'actions rapides sur sélection", self._basculer_barre)
        a.setCheckable(True)
        a.setChecked(self.params.get("barre_rapide", True))
        act(m, "Plein écran", lambda: self.showNormal() if self.isFullScreen() else self.showFullScreen(), "F11")

        m = mb.addMenu("Fe&nêtre")
        act(m, "Onglet suivant", lambda: self.onglets.setCurrentIndex((self.onglets.currentIndex() + 1) % self.onglets.count()), "Ctrl+Tab")
        act(m, "Fermer tous les onglets", self.fermer_tout)
        self.menu_fen = m.addMenu("Fichiers ouverts")
        self.menu_fen.aboutToShow.connect(self._remplir_fenetres)

        m = mb.addMenu("&Aide")
        act(m, "Raccourcis clavier", self.raccourcis, "F1")
        act(m, "Mes tampons...", lambda: self.lancer_outil("tampons"))
        act(m, "Mes signatures...", lambda: self.lancer_outil("remplir_signer"))
        act(m, "Rechercher les mises à jour...", lambda: self.verifier_maj(silencieux=False))
        act(m, "A propos de PhilPDF", self.a_propos)

    def _remplir_recents(self):
        self.menu_recents.clear()
        for p in self.params["recents"][:15]:
            a = self.menu_recents.addAction(os.path.basename(p))
            a.setToolTip(p)
            a.setEnabled(os.path.exists(p))
            a.triggered.connect(lambda _=False, x=p: self.ouvrir(x))

    def _remplir_fenetres(self):
        self.menu_fen.clear()
        for i in range(2, self.onglets.count()):
            a = self.menu_fen.addAction(self.onglets.tabText(i))
            a.triggered.connect(lambda _=False, k=i: self.onglets.setCurrentIndex(k))

    # ------------------------------------------------------------ onglets
    def doc_courant(self):
        """Document affiche, ou le dernier consulte si l'on est sur Accueil / Outils."""
        w = self.onglets.currentWidget()
        if isinstance(w, OngletDocument):
            return w
        if self.dernier_doc is not None and self.onglets.indexOf(self.dernier_doc) >= 0:
            return self.dernier_doc
        return None

    def documents(self):
        return [self.onglets.widget(i) for i in range(self.onglets.count()) if isinstance(self.onglets.widget(i), OngletDocument)]

    def ajouter_onglet(self, o):
        o.titre_change.connect(lambda: self._maj_titre(o))
        o.outil_demande.connect(self.lancer_outil)
        o.statut.connect(lambda t: self.statusBar().showMessage(t, 8000))
        i = self.onglets.addTab(o, icone("creer", "#c9252d"), o.nom)
        self.onglets.setCurrentIndex(i)
        self._maj_titre(o)
        self._session()
        return o

    def _maj_titre(self, o):
        i = self.onglets.indexOf(o)
        if i >= 0:
            self.onglets.setTabText(i, o.nom + (" *" if o.modifie else ""))
            self.onglets.setTabToolTip(i, o.chemin or "Non enregistré")
        if o is self.doc_courant():
            self.setWindowTitle(f"{o.nom}{' *' if o.modifie else ''} – PhilPDF Editeur PDF")

    def _onglet_change(self, i):
        w = self.onglets.widget(i)
        if isinstance(w, OngletDocument):
            self.dernier_doc = w
        o = w if isinstance(w, OngletDocument) else None
        if o:
            self._maj_titre(o)
        else:
            self.setWindowTitle("PhilPDF – Editeur PDF")
            if i == 0:
                self.accueil.rafraichir()

    def _epingles(self, liste):
        for o in self.documents():
            o.remplir_volet()

    def _basculer_barre(self, on):
        self.params["barre_rapide"] = on
        self.params.enregistrer()

    def _session(self):
        """Ecrit les EMPLACEMENTS des fichiers ouverts (jamais les fichiers) dans la session du Drive."""
        session_de(self.params).ecrire([(o.chemin, o.page_courante(), o.zoom) for o in self.documents() if o.chemin])

    def ouvrir(self, chemin):
        chemin = os.path.abspath(chemin)
        for o in self.documents():
            if o.chemin and os.path.normcase(o.chemin) == os.path.normcase(chemin):
                self.onglets.setCurrentWidget(o)
                return o
        if not os.path.exists(chemin):
            QMessageBox.warning(self, "PhilPDF", f"Fichier introuvable sur ce PC :\n{chemin}")
            return None
        try:
            o = OngletDocument(self.params, chemin, biblio=self.biblio)
        except Exception as e:
            QMessageBox.warning(self, "PhilPDF", f"Impossible d'ouvrir ce fichier :\n{e}")
            return None
        if o.doc.needs_pass:
            mdp, ok = QInputDialog.getText(self, "Mot de passe", "Ce PDF est protégé. Mot de passe :", QLineEdit.Password)
            if not ok or not o.doc.authenticate(mdp):
                return None
            o.construire_pages()
        self.params.ajouter_recent(chemin)
        return self.ajouter_onglet(o)

    def dialogue_ouvrir(self):
        dep = os.path.dirname(self.params["recents"][0]) if self.params["recents"] else os.path.expanduser("~")
        for f in QFileDialog.getOpenFileNames(self, "Ouvrir", dep, FILTRE)[0]:
            self.ouvrir(f)

    def fermer_onglet(self, i):
        w = self.onglets.widget(i)
        if not isinstance(w, OngletDocument):
            return
        if w.modifie:
            r = self._demander_enregistrer(w)
            if r == 2 or (r == 0 and not self.enregistrer(w)):
                return
        self.onglets.removeTab(i)
        w.deleteLater()
        self._session()

    def _demander_enregistrer(self, o):
        return question(self, "PhilPDF", f"Enregistrer les modifications de « {o.nom} » ?",
                        [("Enregistrer", QMessageBox.AcceptRole), ("Ne pas enregistrer", QMessageBox.DestructiveRole),
                         ("Annuler", QMessageBox.RejectRole)])

    def fermer_tout(self):
        for i in range(self.onglets.count() - 1, 1, -1):
            self.fermer_onglet(i)

    def closeEvent(self, e):
        for o in self.documents():
            if o.modifie:
                self.onglets.setCurrentWidget(o)
                r = self._demander_enregistrer(o)
                if r == 2 or (r == 0 and not self.enregistrer(o)):
                    e.ignore()
                    return
        self._session()
        self.params.enregistrer()
        e.accept()

    def reprendre_session(self, machine):
        d = DialogueReprise(self, session_de(self.params), machine)
        if d.exec() != QDialog.Accepted:
            return
        for chemin, page, zoom in d.choisis():
            o = self.ouvrir(chemin)
            if o:
                if zoom:
                    o.changer_zoom(zoom)
                if page and page < len(o.doc):
                    from PySide6.QtCore import QTimer
                    QTimer.singleShot(200, lambda o=o, p=page: o.aller_a(p))

    def choisir_session(self):
        autres = session_de(self.params).autres_machines()
        if not autres:
            QMessageBox.information(self, "Session", "Aucune autre machine n'a encore de session. "
                                    "Indiquez votre Drive dans Edition › Préférences, sur chaque PC.")
            return
        libs = [f"{m} ({nb_fichiers(n)}, le {date_fr(d)})" for m, d, n in autres]
        m, ok = QInputDialog.getItem(self, "Reprendre une session", "Machine :", libs, 0, False)
        if ok:
            self.reprendre_session(autres[libs.index(m)][0])

    def proposer_reprise(self):
        """Au demarrage : une autre machine a une session plus recente que la notre -> proposer."""
        s = session_de(self.params)
        autres = s.autres_machines()
        if not autres:
            return
        m, date, n = autres[0]
        mienne = s.lire().get(self.params["machine"], {}).get("maj", "")
        if date > mienne and date != self.params.get("reprise_vue"):
            self.params["reprise_vue"] = date
            self.params.enregistrer()
            if question(self, "Session", f"Reprendre la session de {m} ({nb_fichiers(n)}, le {date_fr(date)}) ?",
                        [("Reprendre", QMessageBox.AcceptRole), ("Non merci", QMessageBox.RejectRole)]) == 0:
                self.reprendre_session(m)

    # ------------------------------------------------------------ enregistrer
    def enregistrer(self, o=None, sous=False):
        o = o or self.doc_courant()
        if not o:
            return False
        chemin = o.chemin
        if sous or not chemin:
            chemin, _ = QFileDialog.getSaveFileName(self, "Enregistrer sous", chemin or o.nom, FILTRE)
            if not chemin:
                return False
            if not chemin.lower().endswith(".pdf"):
                chemin += ".pdf"
        try:
            o.enregistrer(chemin)
        except Exception as e:
            QMessageBox.warning(self, "PhilPDF", f"Enregistrement impossible :\n{e}")
            return False
        self.params.ajouter_recent(chemin)
        self.statusBar().showMessage(f"Enregistré : {chemin} ({os.path.getsize(chemin) // 1024} Ko)", 8000)
        self._session()
        return True

    # ------------------------------------------------------------ outils
    def lancer_outil(self, oid):
        o = self.doc_courant()
        if oid == "__outils__":
            self.onglets.setCurrentWidget(self.outils)
            return
        if oid == "__epingles__":
            self._epingles(self.params["outils_epingles"])
            self.outils.maj_etoiles()
            return
        if oid == "numeriser":
            self.numeriser()
            return
        if oid == "__nouveau__" and o and getattr(o, "_extrait", None):
            self.ajouter_onglet(OngletDocument(self.params, biblio=self.biblio, doc=o._extrait, nom="Extrait.pdf"))
            return
        if oid == "enregistrer":
            self.enregistrer()
            return
        if oid == "creer":
            self.creer("vierge")
            return
        if oid == "combiner":
            self.combiner()
            return
        if oid == "imprimer" and not o:
            self.imprimer_plusieurs()
            return
        info = outil(oid)
        if info and not info[6]:
            QMessageBox.information(self, info[3], f"{info[5]}\n\nCet outil est prévu dans une prochaine version de PhilPDF.")
            return
        if not o:
            QMessageBox.information(self, "PhilPDF", "Ouvrez d'abord un fichier PDF.")
            self.dialogue_ouvrir()
            o = self.doc_courant()
            if not o:
                return
        if self.onglets.currentWidget() is not o:      # depuis la page Outils : retour au document
            self.onglets.setCurrentWidget(o)
        if oid == "modifier":
            o.changer_mode("modifier")
        elif oid == "remplacer":
            texte = o.selection["texte"].split("\n")[0] if o.selection else ""
            d = DialogueRemplacer(o, texte)
            d.finished.connect(lambda _: (setattr(o, "resultats", []), o.rafraichir_pages()))
            d.show()
        elif oid == "organiser":
            o.organiser(True)
        elif oid == "tampons":
            o.ouvrir_bibliotheque("tampons")
        elif oid in ("filigrane", "entete", "fond"):
            self.mise_en_page(o, oid)
        elif oid == "commentaires" or oid == "biffer":
            self.statusBar().showMessage("Sélectionnez du texte : la barre rapide apparaît au-dessus de la sélection.", 10000)
        elif oid == "remplir_signer":
            o.ouvrir_bibliotheque("signatures")
        elif oid == "exporter":
            d = DialogueExporter(self)
            if d.exec() == QDialog.Accepted:
                self.exporter(["docx", "jpg", "png", "txt"][d.format.currentIndex()], int(d.dpi.currentText()), d.qualite.value())
        elif oid == "imprimer":
            self.imprimer([o])
        elif oid == "alleger":
            self.alleger(o)
        elif oid == "motdepasse":
            self.mot_de_passe(o)
        elif oid in ("ocr", "nettoyer"):
            self.ocr(o)

    def creer(self, genre):
        doc = fitz.open()
        if genre == "images":
            fs = QFileDialog.getOpenFileNames(self, "Images", "", "Images (*.png *.jpg *.jpeg *.tif *.tiff *.bmp)")[0]
            if not fs:
                return
            for f in fs:
                img = fitz.open(f)
                pdfbytes = img.convert_to_pdf()
                doc.insert_pdf(fitz.open("pdf", pdfbytes))
        else:
            doc.new_page(width=595, height=842)
        self.ajouter_onglet(OngletDocument(self.params, biblio=self.biblio, doc=doc, nom="Nouveau.pdf"))

    def combiner(self):
        d = QDialog(self)
        d.setWindowTitle("Combiner des fichiers")
        d.resize(560, 420)
        v = QVBoxLayout(d)
        v.addWidget(QLabel("Glissez pour changer l'ordre. Les fichiers seront assemblés de haut en bas."))
        lst = QListWidget()
        lst.setDragDropMode(QListWidget.InternalMove)
        v.addWidget(lst, 1)
        for o in self.documents():
            if o.chemin:
                it = QListWidgetItem(icone("creer", "#c9252d"), os.path.basename(o.chemin))
                it.setData(Qt.UserRole, o.chemin)
                lst.addItem(it)
        h = QHBoxLayout()
        b = QPushButton("Ajouter des fichiers...")
        b.clicked.connect(lambda: [lst.addItem(self._item(f)) for f in QFileDialog.getOpenFileNames(d, "Ajouter", "", "PDF et images (*.pdf *.png *.jpg *.jpeg *.tif)")[0]])
        h.addWidget(b)
        r = QPushButton("Retirer")
        r.clicked.connect(lambda: [lst.takeItem(lst.row(i)) for i in lst.selectedItems()])
        h.addWidget(r)
        h.addStretch()
        v.addLayout(h)
        bb = boutons_fr(QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel))
        bb.button(QDialogButtonBox.Ok).setText("Combiner")
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        v.addWidget(bb)
        if d.exec() != QDialog.Accepted or lst.count() == 0:
            return
        res = fitz.open()
        for i in range(lst.count()):
            f = lst.item(i).data(Qt.UserRole)
            src = fitz.open(f)
            if not src.is_pdf:
                src = fitz.open("pdf", src.convert_to_pdf())
            res.insert_pdf(src)
        self.ajouter_onglet(OngletDocument(self.params, biblio=self.biblio, doc=res, nom="Combiné.pdf"))

    def _item(self, f):
        it = QListWidgetItem(icone("creer", "#c9252d"), os.path.basename(f))
        it.setData(Qt.UserRole, f)
        return it

    def exporter(self, genre, dpi=150, qualite=85):
        o = self.doc_courant()
        if not o:
            return
        base = os.path.splitext(o.chemin or o.nom)[0]
        if genre == "txt":
            f, _ = QFileDialog.getSaveFileName(self, "Exporter en texte", base + ".txt", "Texte (*.txt)")
            if f:
                with open(f, "w", encoding="utf-8") as fh:
                    fh.write("\n\f".join(p.get_text() for p in o.doc))
        elif genre == "docx":
            f, _ = QFileDialog.getSaveFileName(self, "Exporter en Word", base + ".docx", "Word (*.docx)")
            if not f:
                return
            import tempfile, logging
            from pdf2docx import Converter
            logging.getLogger().setLevel(logging.ERROR)
            src = os.path.join(tempfile.mkdtemp(), "source.pdf")
            o.doc.save(src)
            prog = QProgressDialog("Conversion en Word...", None, 0, 0, self)
            prog.setWindowModality(Qt.WindowModal)
            prog.show()
            QApplication.processEvents()
            try:
                c = Converter(src)
                c.convert(f)
                c.close()
                self.statusBar().showMessage(f"Exporté : {f}", 8000)
            except Exception as e:
                QMessageBox.warning(self, "Exporter", f"Conversion impossible :\n{e}")
            prog.close()
        else:
            dossier = QFileDialog.getExistingDirectory(self, "Dossier des images", os.path.dirname(base))
            if dossier:
                for n, p in enumerate(o.doc):
                    pm = p.get_pixmap(dpi=dpi, alpha=False)
                    cible = os.path.join(dossier, f"{os.path.basename(base)}_p{n + 1}.{genre}")
                    if genre == "jpg":
                        pm.save(cible, jpg_quality=qualite)
                    else:
                        pm.save(cible)
                self.statusBar().showMessage(f"{len(o.doc)} images {genre.upper()} enregistrées dans {dossier}", 8000)

    def mise_en_page(self, o, oid):
        if oid == "filigrane":
            choix = question(self, "Filigrane", "Que voulez-vous faire ?",
                             [("Ajouter un filigrane", QMessageBox.AcceptRole), ("Retirer un filigrane", QMessageBox.AcceptRole),
                              ("Annuler", QMessageBox.RejectRole)])
            if choix == 1:
                from moteur import objets
                o.memoriser()
                n = objets.retirer_filigranes(o.doc)
                if not n:
                    cand = objets.filigranes_texte_probables(o.doc)
                    if cand:
                        t, ok = QInputDialog.getItem(self, "Retirer un filigrane", "Filigrane trouvé :", cand, 0, False)
                        if ok:
                            objets.retirer_texte_penche(o.doc, t)
                            n = len(o.doc)
                if n:
                    o.apres_modif([f"Filigrane retiré ({n} page{'s' if n > 1 else ''})."], reconstruire=True)
                else:
                    o.annulations.pop()
                    QMessageBox.information(self, "Filigrane", "Aucun filigrane reconnu dans ce document.")
                return
            if choix != 0:
                return
            d = DialogueFiligrane(self, self.params, len(o.doc), o.page_courante())
            if d.exec() == QDialog.Accepted:
                o.memoriser()
                d.appliquer(o.doc)
                o.apres_modif(["Filigrane ajouté."])
        elif oid == "entete":
            d = DialogueEntete(self)
            if d.exec() == QDialog.Accepted:
                o.memoriser()
                d.appliquer(o.doc)
                o.apres_modif(["En-tête et pied de page ajoutés."])
        elif oid == "fond":
            from PySide6.QtWidgets import QColorDialog
            c = QColorDialog.getColor(Qt.white, self, "Couleur de fond des pages")
            if c.isValid():
                o.memoriser()
                for p in o.doc:
                    p.draw_rect(p.rect, color=None, fill=c.getRgbF()[:3], overlay=False)
                o.apres_modif(["Arrière-plan appliqué."])

    def numeriser(self):
        from moteur.scanner import scanners
        import sys as _s
        if _s.platform != "win32" and not scanners():
            QMessageBox.information(self, "Numériser", "Aucun scanner détecté sur ce PC.")
            return
        d = DialogueNumeriser(self)
        if d.exec() != QDialog.Accepted:
            return
        prog = QProgressDialog("Numérisation en cours...", None, 0, 0, self)
        prog.setWindowModality(Qt.WindowModal)
        prog.show()
        QApplication.processEvents()
        try:
            doc = d.numeriser()
        except Exception as e:
            prog.close()
            QMessageBox.warning(self, "Numériser", f"La numérisation a échoué :\n{e}")
            return
        prog.close()
        if len(doc) == 0:
            QMessageBox.information(self, "Numériser", "Aucune page numérisée.")
            return
        o = self.ajouter_onglet(OngletDocument(self.params, biblio=self.biblio, doc=doc, nom="Numérisation.pdf"))
        if d.ocr.isChecked():
            self.statusBar().showMessage("Enregistrez la numérisation pour lancer la reconnaissance du texte.", 10000)

    def imprimer(self, onglets_ou_docs):
        pr = QPrinter(QPrinter.HighResolution)
        dlg = QPrintDialog(pr, self)
        if dlg.exec() != QDialog.Accepted:
            return
        p = QPainter(pr)
        premier = True
        for d in onglets_ou_docs:
            doc = d.doc if isinstance(d, OngletDocument) else fitz.open(d)
            for page in doc:
                if not premier:
                    pr.newPage()
                premier = False
                cible = p.viewport()
                k = min(cible.width() / page.rect.width, cible.height() / page.rect.height)
                dpi = min(300, 72 * k)
                pm = page.get_pixmap(dpi=int(dpi), alpha=False)
                img = QImage(pm.samples, pm.width, pm.height, pm.stride, QImage.Format_RGB888)
                w, h = int(page.rect.width * k), int(page.rect.height * k)
                p.drawImage(cible.x() + (cible.width() - w) // 2, cible.y() + (cible.height() - h) // 2, img.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        p.end()

    def imprimer_plusieurs(self):
        fs = QFileDialog.getOpenFileNames(self, "Documents à imprimer", "", FILTRE)[0]
        if fs:
            self.imprimer(fs)

    def alleger(self, o):
        avant = len(o.doc.tobytes(garbage=3, deflate=True))
        o.memoriser()
        try:
            o.doc.rewrite_images(dpi_threshold=200, dpi_target=150, quality=75)
        except Exception:
            pass
        o.doc.subset_fonts()
        apres = len(o.doc.tobytes(garbage=4, deflate=True, deflate_fonts=True))
        o.apres_modif()
        QMessageBox.information(self, "Alléger le fichier",
                                f"Poids estimé : {avant // 1024} Ko → {apres // 1024} Ko ({100 - apres * 100 // max(1, avant)} % de moins).\n"
                                "Enregistrez pour appliquer (Enregistrer sous pour garder l'original).")

    def mot_de_passe(self, o):
        d = QDialog(self)
        d.setWindowTitle("Protéger par mot de passe")
        f = QFormLayout(d)
        ouv = QLineEdit()
        ouv.setEchoMode(QLineEdit.Password)
        prop = QLineEdit()
        prop.setEchoMode(QLineEdit.Password)
        imp = QCheckBox("Interdire l'impression")
        cop = QCheckBox("Interdire la copie du texte")
        f.addRow("Mot de passe d'ouverture (facultatif)", ouv)
        f.addRow("Mot de passe des droits", prop)
        f.addRow(imp)
        f.addRow(cop)
        bb = boutons_fr(QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel))
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        f.addRow(bb)
        if d.exec() != QDialog.Accepted:
            return
        perm = fitz.PDF_PERM_ACCESSIBILITY | fitz.PDF_PERM_MODIFY | fitz.PDF_PERM_ANNOTATE | fitz.PDF_PERM_FORM
        if not imp.isChecked():
            perm |= fitz.PDF_PERM_PRINT | fitz.PDF_PERM_PRINT_HQ
        if not cop.isChecked():
            perm |= fitz.PDF_PERM_COPY
        o.chiffrement = dict(encryption=fitz.PDF_ENCRYPT_AES_256, user_pw=ouv.text(),
                             owner_pw=prop.text() or ouv.text() or os.urandom(8).hex(), permissions=perm)
        o.modifie = True
        o.titre_change.emit()
        self.statusBar().showMessage("Protection appliquée à l'enregistrement (AES 256).", 8000)

    def signer(self, o):
        img = os.path.join(o.params_dossier(), "signature.png")
        if not os.path.exists(img):
            f, _ = QFileDialog.getOpenFileName(self, "Image de votre signature (fond transparent de préférence)", "",
                                               "Images (*.png *.jpg *.jpeg)")
            if not f:
                return
            fitz.Pixmap(f).save(img)
            self.statusBar().showMessage("Signature enregistrée : elle sera proposée sur toutes vos machines synchronisées.", 8000)
        o.changer_mode("signature")

    def ocr(self, o):
        from moteur.scan import tesseract_exe
        if not tesseract_exe():
            QMessageBox.information(self, "Reconnaître le texte",
                                    "Le module de reconnaissance de texte est absent de ce paquet PhilPDF.\n"
                                    "Téléchargez la version complète (elle l'embarque).")
            return
        if not o.chemin or o.modifie:
            QMessageBox.information(self, "Reconnaître le texte", "Enregistrez d'abord le document.")
            return
        sortie = os.path.splitext(o.chemin)[0] + "_OCR.pdf"
        prog = QProgressDialog("Redressement, nettoyage et reconnaissance du texte...", None, 0, 0, self)
        prog.setWindowTitle("PhilPDF")
        prog.setWindowModality(Qt.WindowModal)
        prog.show()
        t = TacheScan(o.chemin, sortie)
        self.taches.append(t)

        def fin(chemin, err):
            prog.close()
            if err:
                QMessageBox.warning(self, "Reconnaître le texte", err)
            else:
                self.ouvrir(chemin)
                self.statusBar().showMessage(f"Texte reconnu : {os.path.basename(chemin)}", 10000)
        t.fini.connect(fin)
        t.start()

    # ------------------------------------------------------------ divers
    def ajuster_largeur(self):
        o = self.doc_courant()
        if o:
            w = o.zone.viewport().width() - 60
            o.changer_zoom(w / (o.doc[0].rect.width * 96 / 72))

    def proprietes(self):
        o = self.doc_courant()
        if not o:
            return
        m = o.doc.metadata or {}
        polices = sorted({f[3] for p in o.doc for f in p.get_fonts()})
        QMessageBox.information(self, "Propriétés", f"Fichier : {o.chemin or o.nom}\nPages : {len(o.doc)}\n"
                                f"Créé par : {m.get('creator') or '-'}\nProduit par : {m.get('producer') or '-'}\n"
                                f"Polices : {', '.join(polices[:12]) or 'aucune (scan)'}")

    def preferences(self):
        d = QDialog(self)
        d.setWindowTitle("Préférences")
        d.setMinimumWidth(520)
        f = QFormLayout(d)
        machine = QLineEdit(self.params["machine"])
        auteur = QLineEdit(self.params.get("auteur", ""))
        auteur.setPlaceholderText("Nom inscrit sur les tampons et commentaires")
        drive = QComboBox()
        drive.setEditable(True)
        drive.addItem("(aucun)", "")
        for nom, chemin in detecter_clouds():
            drive.addItem(f"{nom} — {chemin}", chemin)
        if self.params.get("drive") and drive.findData(self.params["drive"]) < 0:
            drive.addItem(self.params["drive"], self.params["drive"])
        drive.setCurrentIndex(max(0, drive.findData(self.params.get("drive", ""))))
        b = QPushButton("Autre...")
        b.clicked.connect(lambda: (lambda p: p and (drive.addItem(p, p), drive.setCurrentIndex(drive.count() - 1)))(
            QFileDialog.getExistingDirectory(d, "Dossier du Drive sur ce PC")))
        hs = QHBoxLayout()
        hs.addWidget(drive, 1)
        hs.addWidget(b)
        sauver = QPushButton("Sauvegarder maintenant")
        sauver.clicked.connect(lambda: QMessageBox.information(d, "Drive", f"{self.biblio.sauvegarder_drive() or 0} élément(s) copiés sur le Drive."
                                                               if self.params.get("drive") else "Choisissez d'abord votre Drive."))
        racines = QListWidget()
        racines.setMaximumHeight(90)
        for r in self.params.get("racines", []) or [os.path.expanduser("~")]:
            racines.addItem(r)
        hr = QHBoxLayout()
        br = QPushButton("Ajouter un emplacement...")
        br.clicked.connect(lambda: (lambda p: p and racines.addItem(p))(QFileDialog.getExistingDirectory(d, "Emplacement de vos documents")))
        hr.addWidget(br)
        bs = QPushButton("Retirer")
        bs.clicked.connect(lambda: [racines.takeItem(racines.row(i)) for i in racines.selectedItems()])
        hr.addWidget(bs)
        hr.addStretch()
        fixer = QCheckBox("Fixer signatures et tampons dans la page à l'enregistrement (non déplaçables ensuite)")
        fixer.setChecked(self.params.get("fixer_objets", False))
        moteur = QComboBox()
        moteur.addItems(["Claude", "Gemini", "Les deux (double avis)"])
        moteur.setCurrentIndex({"claude": 0, "gemini": 1, "deux": 2}.get(self.params["ia_moteur"], 0))
        kc = QLineEdit(self.params["clef_claude"])
        kc.setEchoMode(QLineEdit.Password)
        kg = QLineEdit(self.params["clef_gemini"])
        kg.setEchoMode(QLineEdit.Password)
        assoc = QCheckBox("Ouvrir les fichiers PDF avec PhilPDF (proposé dans « Ouvrir avec »)")
        assoc.setChecked(self.params["association_pdf"])
        assoc.setEnabled(sys.platform == "win32" and not est_portable())
        f.addRow("Nom de cette machine (alias)", machine)
        f.addRow("Votre nom", auteur)
        f.addRow("Drive (Google Drive, OneDrive...)", hs)
        expl = QLabel("Tampons et signatures restent sur ce PC ; le Drive en garde une sauvegarde (dossier PhilPDF) "
                      "et la liste des fichiers ouverts, pour les retrouver sur vos autres machines.")
        expl.setWordWrap(True)
        expl.setStyleSheet("color:#555;font-size:12px")
        f.addRow(expl)
        f.addRow("", sauver)
        f.addRow("Emplacements de vos documents sur ce PC", racines)
        f.addRow("", hr)
        f.addRow(fixer)
        f.addRow("Moteur IA", moteur)
        f.addRow("Clef API Claude", kc)
        f.addRow("Clef API Gemini", kg)
        av = QLabel("Gemini en offre gratuite : Google peut réutiliser les documents envoyés. A éviter pour les documents sensibles.")
        av.setWordWrap(True)
        av.setStyleSheet("color:#a35c00")
        f.addRow(av)
        f.addRow(assoc)
        majs = QComboBox()
        majs.addItems(["GitHub (Internet)", "Dossier synchronisé"])
        majs.setCurrentIndex(1 if self.params.get("maj_source") == "dossier" else 0)
        maja = QCheckBox("Vérifier les mises à jour au démarrage (une fois par jour)")
        maja.setChecked(self.params.get("maj_auto", True))
        f.addRow("Mises à jour depuis", majs)
        f.addRow(maja)
        f.addRow(QLabel(f"Données : {dossier_donnees()}" + (" (version portable)" if est_portable() else "")))
        bb = boutons_fr(QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel))
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        f.addRow(bb)
        if d.exec() != QDialog.Accepted:
            return
        self.params.update(machine=machine.text().strip() or self.params["machine"],
                           drive=drive.currentData() if drive.currentData() is not None else drive.currentText().strip(),
                           auteur=auteur.text().strip(), fixer_objets=fixer.isChecked(),
                           racines=[racines.item(i).text() for i in range(racines.count())],
                           ia_moteur=["claude", "gemini", "deux"][moteur.currentIndex()],
                           clef_claude=kc.text().strip(), clef_gemini=kg.text().strip(),
                           maj_source=["github", "dossier"][majs.currentIndex()], maj_auto=maja.isChecked())
        if assoc.isChecked() != self.params["association_pdf"]:
            if associer_pdf(assoc.isChecked()):
                self.params["association_pdf"] = assoc.isChecked()
        self.params.enregistrer()
        self._session()
        self.accueil.rafraichir()

    def verifier_maj(self, silencieux):
        t = TacheMaj(self.params)
        self.taches.append(t)
        t.trouve.connect(lambda r: self._maj_trouvee(r, silencieux))
        t.start()

    def _maj_trouvee(self, res, silencieux):
        if not res:
            if not silencieux:
                QMessageBox.information(self, "Mises à jour", f"PhilPDF {VERSION} est à jour.")
            return
        version, paquet, notes = res
        r = QMessageBox.question(self, "Mise à jour disponible",
                                 f"PhilPDF {version} est disponible (vous avez {VERSION}).\n\n{notes[:600]}\n\n"
                                 "Installer maintenant ? PhilPDF se fermera puis se relancera.")
        if r != QMessageBox.Yes:
            return
        from .mise_a_jour import appliquer
        try:
            lance = appliquer(paquet)
        except Exception as e:
            QMessageBox.warning(self, "Mise à jour", f"Echec du téléchargement :\n{e}")
            return
        if lance:
            self.close()
        else:
            QMessageBox.information(self, "Mise à jour", f"Téléchargez la nouvelle version ici :\n{paquet}")

    def raccourcis(self):
        QMessageBox.information(self, "Raccourcis clavier",
                                "Ctrl+O  Ouvrir\nCtrl+S  Enregistrer\nShift+Ctrl+S  Enregistrer sous\nCtrl+P  Imprimer\n"
                                "Ctrl+Z  Annuler\nCtrl+C  Copier la sélection\nCtrl+F  Rechercher et remplacer\n"
                                "Ctrl+ +/-  Zoom\nCtrl+1  Taille réelle\nCtrl+2  Ajuster à la largeur\n"
                                "Shift+Ctrl++  Pivoter\nCtrl+W  Fermer le fichier\nF11  Plein écran")

    def a_propos(self):
        QMessageBox.about(self, "A propos de PhilPDF",
                          f"<b>PhilPDF {VERSION}</b> – Editeur PDF<br>Usage personnel et familial.<br><br>"
                          "Moteur PDF : PyMuPDF (AGPL). Interface : Qt / PySide6 (LGPL). OCR : Tesseract (Apache 2.0).<br>"
                          "Police de remplacement fournie : Nunito (SIL Open Font License).")
