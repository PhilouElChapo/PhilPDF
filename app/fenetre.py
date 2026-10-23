"""Fenetre principale de PhilPDF : menus, onglets, aiguillage des outils."""
import os, sys
import pymupdf as fitz
from PySide6.QtCore import Qt, QThread, Signal, QSize
from PySide6.QtGui import QAction, QKeySequence, QImage, QPainter
from PySide6.QtWidgets import (QMainWindow, QTabWidget, QFileDialog, QMessageBox, QDialog, QFormLayout,
                               QLineEdit, QCheckBox, QComboBox, QDialogButtonBox, QListWidget, QVBoxLayout,
                               QHBoxLayout, QPushButton, QLabel, QProgressDialog, QApplication, QInputDialog,
                               QListWidgetItem, QWidget, QFrame, QGroupBox)
from PySide6.QtPrintSupport import QPrinter, QPrintDialog
from .config import Parametres, VERSION, est_portable, associer_pdf, dossier_donnees
from .icones import icone, logo
from .pages import PageOutils, PageAccueil
from .document import OngletDocument, DialogueRemplacer, question
from .outils import outil
from .bibliotheque import Bibliotheque, detecter_clouds
from . import distant, miroir, reglages
from .dialogues_distant import DialogueParcourir, PanneauComptes, ouvrir_emplacement, erreur as erreur_distant
from .session import session_de, date_fr, nb_fichiers, dossiers_connus, DELAI_SILENCIEUX
from .dialogues import (boutons_fr, DialogueFiligrane, DialogueEntete, DialogueNumeriser, DialogueExporter,
                        DialogueBibliotheque, DialogueSynchro, DialogueFond)
from .langue import _

FILTRE = _('Documents PDF (*.pdf *.PDF)')


class TacheScan(QThread):
    fini = Signal(str, str)

    def __init__(self, entree, sortie):
        super().__init__()
        self.entree, self.sortie = entree, sortie

    def run(self):
        try:
            from moteur.scan import traiter
            r = traiter(self.entree, self.sortie)
            if all(x[2] is None for x in r):          # aucune page scannee : rien a reconnaitre
                try:
                    os.remove(self.sortie)
                except OSError:
                    pass
                self.fini.emit("", "__deja__")
                return
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


def montrer_dans_explorateur(chemin):
    """Ouvre le gestionnaire de fichiers sur le dossier du fichier, le fichier selectionne."""
    import subprocess
    chemin = os.path.normpath(chemin)
    try:
        if sys.platform == "win32":
            subprocess.Popen(f'explorer /select,"{chemin}"')
            return
        try:                                     # Linux : gestionnaire de fichiers standard (Nautilus, Dolphin...)
            subprocess.run(["dbus-send", "--session", "--dest=org.freedesktop.FileManager1", "--type=method_call",
                            "/org/freedesktop/FileManager1", "org.freedesktop.FileManager1.ShowItems",
                            f"array:string:file://{chemin}", "string:"], check=True, timeout=5)
        except (OSError, subprocess.SubprocessError):
            subprocess.Popen(["xdg-open", os.path.dirname(chemin)])
    except OSError:
        pass


class TacheTelechargement(QThread):
    avance = Signal(int, int)
    fini = Signal(str, str)              # fichier, erreur

    def __init__(self, paquet):
        super().__init__()
        self.paquet, self.stop = paquet, False

    def run(self):
        from .mise_a_jour import recuperer
        try:
            self.fini.emit(recuperer(self.paquet, lambda a, b: self.avance.emit(a // 1024, b // 1024),
                                     lambda: self.stop), "")
        except Exception as e:
            self.fini.emit("", str(e))


class TacheMiroir(QThread):
    """Synchronise le dossier PhilPDF d'un Drive « en direct » avec son miroir local."""
    fini = Signal(object, str)

    def __init__(self, params):
        super().__init__()
        self.params = params

    def run(self):
        try:
            self.fini.emit(miroir.synchroniser(self.params), "")
        except Exception as e:
            self.fini.emit(None, str(e))


class TacheSynchro(QThread):
    """Verification silencieuse au demarrage : une autre machine a-t-elle une session plus recente
    et differente ? Si oui, recherche rapide (quelques secondes) de ses fichiers sur ce poste."""
    resultat = Signal(object)

    def __init__(self, session, ouverts):
        super().__init__()
        self.s, self.ouverts, self.stop = session, ouverts, False

    def run(self):
        try:
            d = self.s.discordance(self.ouverts)
            if d:
                m, date, fichiers = d
                self.resultat.emit((m, date, fichiers, self.s.retrouver_tous(m, fichiers, arret=lambda: self.stop, delai=DELAI_SILENCIEUX)))
        except Exception:
            pass


class Notification(QFrame):
    """Petite bulle non bloquante en bas a droite de la fenetre, disparait seule."""

    def __init__(self, parent, texte, bouton, action):
        super().__init__(parent)
        self.setObjectName("notif")
        self.setStyleSheet("#notif{background:#1f2933;border-radius:10px} QLabel{color:#fff;font-size:13px}"
                           "QPushButton{color:#9cc9ff;background:transparent;border:none;font-weight:600;padding:4px 8px}")
        h = QHBoxLayout(self)
        h.setContentsMargins(14, 10, 8, 10)
        ic = QLabel()
        ic.setPixmap(icone("synchro", "#9cc9ff").pixmap(22, 22))
        h.addWidget(ic)
        lb = QLabel(texte)
        lb.setWordWrap(True)
        lb.setMaximumWidth(360)
        h.addWidget(lb)
        b = QPushButton(bouton)
        b.clicked.connect(lambda: (action(), self.close()))
        h.addWidget(b)
        x = QPushButton("✕")
        x.clicked.connect(self.close)
        h.addWidget(x)
        self.adjustSize()
        self.placer()
        self.show()
        self.raise_()
        from PySide6.QtCore import QTimer
        QTimer.singleShot(12000, self.close)

    def placer(self):
        p = self.parent()
        self.move(p.width() - self.width() - 24, p.height() - self.height() - 40)


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
        self.accueil.ouvrir_distant.connect(lambda: self.ouvrir_distant())
        self.accueil.action_fichier.connect(self.action_fichier)
        self.accueil.reprendre.connect(self.reprendre_proposee)
        self.accueil.synchroniser.connect(self.synchroniser)
        self.synchro = None              # (machine, date, fichiers, resultats) trouve au demarrage
        self._session_touchee = False    # on n'ecrit la session que si des fichiers ont ete ouverts ou fermes
        self.outils = PageOutils(self.params)
        self.outils.outil_choisi.connect(self.lancer_outil)
        self.outils.epingles_changes.connect(self._epingles)
        self.onglets.addTab(self.accueil, _('Accueil'))
        self.onglets.addTab(self.outils, _('Outils'))
        for i in (0, 1):
            self.onglets.tabBar().setTabButton(i, self.onglets.tabBar().ButtonPosition.RightSide, None)
        self.setCentralWidget(self.onglets)
        self._menus()
        self.statusBar().showMessage(_('PhilPDF {VERSION}', VERSION=VERSION) + (_(' · version portable') if est_portable() else ""))
        self.taches = []
        for f in fichiers:
            self.ouvrir(f)
        import datetime
        aujourd_hui = datetime.date.today().isoformat()
        if self.params.get("maj_auto", True):
            self.params["maj_derniere"] = aujourd_hui
            self.params.enregistrer()
            self.verifier_maj(silencieux=True)
        from PySide6.QtCore import QTimer
        if getattr(self.params, "nouveau", False) or not (self.params.get("bienvenue_vue") or self.params.get("drive")
                                                          or self.params.get("drive_compte")):
            QTimer.singleShot(600, self.bienvenue)
        if miroir.compte_drive(self.params):
            QTimer.singleShot(800, lambda: self.synchro_miroir(au_demarrage=True))
        elif self.params.get("synchro", True):
            QTimer.singleShot(1500, self.verifier_synchro)
        self._minuterie = QTimer(self)
        self._minuterie.timeout.connect(self._session)
        self._minuterie.timeout.connect(lambda: self.synchro_miroir())
        self._minuterie.start(60000)       # page courante memorisee chaque minute
        # tampons et signatures : synchronisation silencieuse avec le Drive au demarrage
        if not miroir.compte_drive(self.params):
            QTimer.singleShot(1200, self._synchro_biblio)

    def _synchro_biblio(self):
        try:
            r = self.biblio.synchroniser_drive()
        except OSError:
            r = None
        if r and r[0]:
            self.statusBar().showMessage(_('{x} tampon(s) / signature(s) reçu(s) de vos autres postes.', x=r[0]), 8000)
        if r and r[1] and miroir.compte_drive(self.params):
            from PySide6.QtCore import QTimer
            QTimer.singleShot(1000, self.synchro_miroir)

    # ------------------------------------------------------------ menus
    def _menus(self):
        mb = self.menuBar()

        def act(menu, texte, f, raccourci=None, ic=None, actif=True):
            a = QAction(icone(ic, "#444444"), texte, self) if ic else QAction(texte, self)
            if raccourci:
                a.setShortcut(QKeySequence(raccourci))
            a.triggered.connect(f)
            a.setEnabled(actif)
            menu.addAction(a)
            return a

        m = mb.addMenu(_('&Fichier'))
        act(m, _('Ouvrir...'), self.dialogue_ouvrir, "Ctrl+O", "ouvrir")
        self.menu_recents = m.addMenu(icone("recent"), _('Ouvrir un fichier récent'))
        self.menu_recents.aboutToShow.connect(self._remplir_recents)
        act(m, _("Ouvrir depuis un emplacement (NAS, FTP, Drive)..."), lambda: self.ouvrir_distant(), "Shift+Ctrl+O", "archiver")
        act(m, _('Synchroniser avec les autres postes...'), self.synchroniser, None, "synchro")
        sm = m.addMenu(icone("creer"), _('Créer un PDF'))
        act(sm, _('Page vierge'), lambda: self.creer("vierge"), None, "creer")
        act(sm, _("A partir d'images..."), lambda: self.creer("images"), None, "exporter")
        act(sm, _('A partir de plusieurs fichiers (combiner)...'), lambda: self.lancer_outil("combiner"), None, "combiner")
        act(sm, _('Depuis le scanner...'), lambda: self.lancer_outil("numeriser"), None, "numeriser")
        m.addSeparator()
        act(m, _('Enregistrer'), lambda: self.enregistrer(), "Ctrl+S", "enregistrer")
        act(m, _('Enregistrer sous...'), lambda: self.enregistrer(sous=True), "Shift+Ctrl+S", "enregistrer_sous")
        act(m, _("Enregistrer vers un emplacement (NAS, FTP, Drive)..."), lambda: self.enregistrer_distant(), None, "archiver")
        act(m, _('Enregistrer une copie allégée...'), lambda: self.lancer_outil("alleger"), None, "alleger")
        sm = m.addMenu(icone("exporter"), _('Exporter vers'))
        act(sm, _('Word (.docx)...'), lambda: self.exporter("docx"))
        act(sm, _('Images JPG...'), lambda: self.exporter("jpg"))
        act(sm, _('Images PNG...'), lambda: self.exporter("png"))
        act(sm, _('Texte (.txt)...'), lambda: self.exporter("txt"))
        m.addSeparator()
        act(m, _('Imprimer...'), lambda: self.lancer_outil("imprimer"), "Ctrl+P", "imprimer")
        act(m, _('Imprimer plusieurs documents...'), self.imprimer_plusieurs, None, "lot")
        m.addSeparator()
        act(m, _("Protéger à l'aide d'un mot de passe..."), lambda: self.lancer_outil("motdepasse"), None, "motdepasse")
        act(m, _('Propriétés...'), self.proprietes, "Ctrl+D", "info")
        m.addSeparator()
        act(m, _('Fermer le fichier'), lambda: self.fermer_onglet(self.onglets.currentIndex()), "Ctrl+W", "fermer_doc")
        act(m, _('Quitter'), self.close, "Ctrl+Q", "quitter")

        m = mb.addMenu(_('&Edition'))
        d = lambda nom: (lambda: getattr(self.doc_courant(), nom)() if self.doc_courant() else None)
        act(m, _('Annuler|action'), d("annuler"), "Ctrl+Z", "annuler")
        act(m, _('Rétablir'), d("retablir"), "Shift+Ctrl+Z", "retablir")
        m.addSeparator()
        act(m, _('Couper'), d("couper"), "Ctrl+X", "couper")
        act(m, _('Copier'), d("copier"), "Ctrl+C", "copier")
        act(m, _('Coller'), d("coller"), "Ctrl+V", "coller")
        act(m, _('Supprimer'), d("supprimer"), "Del", "supprimer")
        m.addSeparator()
        act(m, _('Sélectionner tout'), d("tout_selectionner"), "Ctrl+A", "tout")
        act(m, _('Désélectionner tout'), lambda: self.doc_courant() and (setattr(self.doc_courant(), "selection", None),
                                                                     self.doc_courant().choisir_objet(None)), "Shift+Ctrl+A", "aucun")
        m.addSeparator()
        act(m, _('Modifier le texte et les images'), lambda: self.lancer_outil("modifier"), None, "modifier")
        act(m, _('Rechercher et remplacer...'), lambda: self.lancer_outil("remplacer"), "Ctrl+F", "rechercher")
        m.addSeparator()
        act(m, _('Préférences...'), self.preferences, "Ctrl+K", "parametres")

        m = mb.addMenu(_('&Affichage'))
        act(m, _('Pivoter la page (90°)'), lambda: self.doc_courant() and self.doc_courant().pivoter_courante(), "Shift+Ctrl++", "pivoter")
        act(m, _('Zoom avant'), lambda: self.doc_courant() and self.doc_courant().changer_zoom(self.doc_courant().zoom * 1.2), "Ctrl++", "zoom_plus")
        act(m, _('Zoom arrière'), lambda: self.doc_courant() and self.doc_courant().changer_zoom(self.doc_courant().zoom / 1.2), "Ctrl+-", "zoom_moins")
        act(m, _('Taille réelle'), lambda: self.doc_courant() and self.doc_courant().changer_zoom(1.0), "Ctrl+1", "taille_reelle")
        act(m, _('Ajuster à la largeur'), self.ajuster_largeur, "Ctrl+2", "largeur")
        m.addSeparator()
        act(m, _('Vignettes des pages'), lambda: self.doc_courant() and self.doc_courant().basculer_vignettes(), "F4", "volet_gauche")
        sm = m.addMenu(icone("volet_droit", "#444444"), _('Volet de droite'))
        for lib, mode in ((_('Complet'), "complet"), (_('Icônes seules'), "icones"), (_('Masqué'), "masque")):
            act(sm, lib, lambda _x=False, md=mode: [o.mode_volet(md) for o in self.documents()])
        act(m, _('Changer le volet de droite'), lambda: self.doc_courant() and self.doc_courant().basculer_volet(), "Shift+F4")
        m.addSeparator()
        a = act(m, _("Barre d'actions rapides sur sélection"), self._basculer_barre, None, "barre")
        a.setCheckable(True)
        a.setChecked(self.params.get("barre_rapide", True))
        act(m, _('Plein écran'), lambda: self.showNormal() if self.isFullScreen() else self.showFullScreen(), "F11", "plein_ecran")

        m = mb.addMenu(_('Fe&nêtre'))
        act(m, _('Onglet suivant'), lambda: self.onglets.setCurrentIndex((self.onglets.currentIndex() + 1) % self.onglets.count()), "Ctrl+Tab", "onglet")
        act(m, _('Fermer tous les onglets'), self.fermer_tout, None, "fermer")
        self.menu_fen = m.addMenu(_('Fichiers ouverts'))
        self.menu_fen.aboutToShow.connect(self._remplir_fenetres)

        m = mb.addMenu(_('&Aide'))
        act(m, _('Raccourcis clavier'), self.raccourcis, "F1", "clavier")
        act(m, _('Mes tampons...'), lambda: self.lancer_outil("tampons"), None, "tampon")
        act(m, _('Mes signatures...'), lambda: self.lancer_outil("remplir_signer"), None, "signer")
        act(m, _('Rechercher les mises à jour...'), lambda: self.verifier_maj(silencieux=False), None, "mise_a_jour")
        act(m, _('A propos de PhilPDF'), self.a_propos, None, "aide")

    def _remplir_recents(self):
        self.menu_recents.clear()
        for p in self.params["recents"][:15]:
            a = self.menu_recents.addAction(os.path.basename(p))
            a.setToolTip(p)
            a.setEnabled(os.path.exists(p))
            a.triggered.connect(lambda _x=False, x=p: self.ouvrir(x))

    def _remplir_fenetres(self):
        self.menu_fen.clear()
        for i in range(2, self.onglets.count()):
            a = self.menu_fen.addAction(self.onglets.tabText(i))
            a.triggered.connect(lambda _x=False, k=i: self.onglets.setCurrentIndex(k))

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
            dist = getattr(o, "distant", None)
            self.onglets.setTabToolTip(i, _("{lieu} : {chemin}", lieu=dist["lieu"], chemin=dist["chemin"]) if dist
                                       else o.chemin or _('Non enregistré'))
            self.onglets.setTabIcon(i, icone("archiver" if dist else "creer", "#0f6cbd" if dist else "#c9252d"))
        if o is self.doc_courant():
            self.setWindowTitle(_('{nom}{x} – PhilPDF Editeur PDF', nom=o.nom, x=' *' if o.modifie else ''))

    def _onglet_change(self, i):
        w = self.onglets.widget(i)
        if isinstance(w, OngletDocument):
            self.dernier_doc = w
        o = w if isinstance(w, OngletDocument) else None
        if o:
            self._maj_titre(o)
        else:
            self.setWindowTitle(_('PhilPDF – Editeur PDF'))
            if i == 0:
                self.accueil.rafraichir()

    def _epingles(self, liste):
        for o in self.documents():
            o.remplir_volet()

    def _basculer_barre(self, on):
        self.params["barre_rapide"] = on
        self.params.enregistrer()

    def _session(self, toucher=False):
        """Ecrit les EMPLACEMENTS des fichiers ouverts (jamais les fichiers) dans la session du Drive.
        Rien n'est ecrit tant qu'aucun fichier n'a ete ouvert ou ferme : lancer PhilPDF pour rien
        n'efface pas la session de ce poste."""
        self._session_touchee = self._session_touchee or toucher
        if not self._session_touchee or not self.params.get("synchro", True):
            return
        session_de(self.params).ecrire([(o.chemin, o.page_courante(), o.zoom, o.distant) for o in self.documents() if o.chemin])
        self.synchro_miroir()

    def ouvrir(self, chemin):
        chemin = os.path.abspath(chemin)
        for o in self.documents():
            if o.chemin and os.path.normcase(o.chemin) == os.path.normcase(chemin):
                self.onglets.setCurrentWidget(o)
                return o
        if not os.path.exists(chemin):
            QMessageBox.warning(self, "PhilPDF", _('Fichier introuvable sur ce PC :\n{chemin}', chemin=chemin))
            return None
        try:
            o = OngletDocument(self.params, chemin, biblio=self.biblio)
        except Exception as e:
            QMessageBox.warning(self, "PhilPDF", _("Impossible d'ouvrir ce fichier :\n{e}", e=e))
            return None
        if o.doc.needs_pass:
            mdp, ok = QInputDialog.getText(self, _('Mot de passe'), _('Ce PDF est protégé. Mot de passe :'), QLineEdit.Password)
            if not ok or not o.doc.authenticate(mdp):
                return None
            o.construire_pages()
        self.params.ajouter_recent(chemin)
        self.params["dernier_dossier"] = os.path.dirname(chemin)
        self._session_touchee = True
        return self.ajouter_onglet(o)

    def dialogue_ouvrir(self):
        for f in QFileDialog.getOpenFileNames(self, _('Ouvrir'), self.dossier_depart(), FILTRE)[0]:
            self.ouvrir(f)

    def action_fichier(self, chemin, action):
        """Menu clic droit d'un fichier recent de l'Accueil."""
        if action == "emplacement":
            montrer_dans_explorateur(chemin)
        elif action == "copier_chemin":
            QApplication.clipboard().setText(chemin)
            self.statusBar().showMessage(_("Chemin copié : {chemin}", chemin=chemin), 5000)
        elif action == "retirer":
            self.params["recents"] = [p for p in self.params["recents"] if p != chemin]
            self.params.enregistrer()
            self.accueil.rafraichir()
        else:
            o = self.ouvrir(chemin)
            if o and action != "ouvrir":
                self.lancer_outil({"resume": "ia_resume"}.get(action, action))

    def dossier_depart(self):
        """Dernier dossier ouvert ; a defaut Documents ; a defaut le dossier utilisateur."""
        d = self.params.get("dernier_dossier")
        if d and os.path.isdir(d):
            return d
        return dossiers_connus().get("documents") or os.path.expanduser("~")

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
        self._session(toucher=True)

    def _demander_enregistrer(self, o):
        return question(self, "PhilPDF", _('Enregistrer les modifications de « {nom} » ?', nom=o.nom),
                        [(_('Enregistrer'), QMessageBox.AcceptRole), (_('Ne pas enregistrer'), QMessageBox.DestructiveRole),
                         (_('Annuler'), QMessageBox.RejectRole)])

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
                    self._redemarrage = None
                    return
        self._session()
        self.params.enregistrer()
        reglages.ecrire_drive(self.params)
        for t in self.taches:
            if isinstance(t, TacheSynchro):
                t.stop = True
                t.wait(2000)
        if miroir.compte_drive(self.params):         # derniere synchro avec le Drive (8 s au plus)
            t = getattr(self, "_t_miroir", None)
            if t and t.isRunning():
                t.wait(8000)
            t = TacheMiroir(self.params)
            t.start()
            t.wait(8000)
        e.accept()
        if getattr(self, "_redemarrage", None):
            from PySide6.QtCore import QProcess
            QProcess.startDetached(*self._redemarrage)

    def synchro_miroir(self, au_demarrage=False):
        if not miroir.compte_drive(self.params) or getattr(self, "_t_miroir", None) and self._t_miroir.isRunning():
            return
        t = self._t_miroir = TacheMiroir(self.params)
        self.taches.append(t)

        def fini(res, err):
            if err:
                self.statusBar().showMessage(_("Emplacement de synchronisation injoignable : {raison}", raison=err[:120]), 8000)
            if au_demarrage:
                self._synchro_biblio()
                if self.params.get("synchro", True):
                    self.verifier_synchro()
        t.fini.connect(fini)
        t.start()

    def verifier_synchro(self):
        """Au demarrage, en silence : session plus recente et differente sur un autre poste ?"""
        t = TacheSynchro(session_de(self.params), [o.chemin for o in self.documents() if o.chemin])
        t.resultat.connect(self._synchro_trouvee)
        self.taches.append(t)
        t.start()

    def _synchro_trouvee(self, r):
        self.synchro = r
        m, date, fichiers, res = r
        self.accueil.montrer_synchro(m, date, fichiers, res)
        n = sum(1 for c, _x in res if c)
        Notification(self, _('Session plus récente sur {m} ({date}) : {nb}, {n} retrouvé{x} ici.', m=m, date=date_fr(date), nb=nb_fichiers(len(fichiers)), n=n, x='s' if n > 1 else ''), _('Voir'),
                     lambda: self.onglets.setCurrentWidget(self.accueil))

    def reprendre_proposee(self):
        if self.synchro:
            m, date, fichiers, res = self.synchro
            session = session_de(self.params)
            ouvrir = []
            for e, (c, _x) in zip(fichiers, res):
                if c:
                    session.apprendre_depuis(m, e, c)
                    ouvrir.append((c, e.get("page", 0), e.get("zoom")))
            self.reprendre(ouvrir, remplacer=True)

    def synchroniser(self):
        if not (self.params.get("drive") or miroir.compte_drive(self.params)):
            self.bienvenue(seulement_synchro=True)
            return
        s = session_de(self.params)
        if not s.autres_machines():
            QMessageBox.information(self, _('Synchroniser'), _("Aucun autre poste n'a encore de session. Choisissez le même emplacement de synchronisation dans Edition › Préférences sur chacun de vos PC."))
            return
        m, res = (self.synchro[0], self.synchro[3]) if self.synchro else (None, None)
        d = DialogueSynchro(self, s, m, res, len(self.documents()))
        if d.exec() == QDialog.Accepted:
            self.reprendre(d.choisis(), remplacer=d.remplacer.isChecked())

    def reprendre(self, fichiers, remplacer=True):
        """Ouvre [(chemin, page, zoom)] ; par defaut, remplace les fichiers deja ouverts."""
        if not fichiers:
            return
        if remplacer:
            garder = {os.path.normcase(c) for c, _x, _x2 in fichiers}
            for i in range(self.onglets.count() - 1, -1, -1):
                w = self.onglets.widget(i)
                if isinstance(w, OngletDocument) and (not w.chemin or os.path.normcase(w.chemin) not in garder):
                    self.fermer_onglet(i)
        from PySide6.QtCore import QTimer
        for chemin, page, zoom in fichiers:
            if chemin.startswith("distant:"):
                _p, cid, ch = chemin.split(":", 2)
                o = self.ouvrir_distant(compte_id=cid, chemin=ch)
            else:
                o = self.ouvrir(chemin)
            if o:
                if zoom:
                    o.changer_zoom(zoom)
                if page and page < len(o.doc):
                    QTimer.singleShot(300, lambda o=o, p=page: o.aller_a(p))
        self.synchro = None
        self.accueil.cacher_synchro()
        self._session(toucher=True)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        for n in self.findChildren(Notification):
            n.placer()

    # ------------------------------------------------------------ enregistrer
    def enregistrer(self, o=None, sous=False):
        o = o or self.doc_courant()
        if not o:
            return False
        chemin = o.chemin
        if sous or not chemin:
            chemin, _x = QFileDialog.getSaveFileName(self, _('Enregistrer sous'), chemin or o.nom, FILTRE)
            if not chemin:
                return False
            if not chemin.lower().endswith(".pdf"):
                chemin += ".pdf"
        if sous and getattr(o, "distant", None):
            o.distant = None                  # "Enregistrer sous" sur ce PC : le fichier n'est plus celui du NAS
        try:
            o.enregistrer(chemin)
        except Exception as e:
            QMessageBox.warning(self, "PhilPDF", _('Enregistrement impossible :\n{e}', e=e))
            return False
        if getattr(o, "distant", None):
            return self._renvoyer(o)
        self.params.ajouter_recent(chemin)
        self.statusBar().showMessage(_('Enregistré : {chemin} ({x} Ko)', chemin=chemin, x=os.path.getsize(chemin) // 1024), 8000)
        self._session()
        return True

    # ------------------------------------------------------------ emplacements distants
    def _compte(self, ident=None, cle=None):
        for c in self.params.get("comptes", []):
            if c["id"] == ident or (cle and distant.cle_compte(c) == cle):
                return c
        return None

    def ouvrir_distant(self, compte_id=None, chemin=None, cle=None):
        """Ouvre un PDF d'un NAS, d'un FTP ou d'un Drive : copie de travail sur ce PC, Ctrl+S le renvoie."""
        if not self.params.get("comptes"):
            QMessageBox.information(self, _("Emplacements"), _("Ajoutez d'abord votre NAS, FTP ou Drive dans "
                                                              "Edition › Préférences › Comptes."))
            self.preferences(onglet="comptes")
            return None
        c = self._compte(compte_id, cle)
        e = None
        if chemin is None or not c:
            d = DialogueParcourir(self, self.params, "ouvrir", compte_id=compte_id)
            if d.exec() != QDialog.Accepted or not d.choisi:
                return None
            c, e, chemin = d.compte(), d.e, d.choisi
        if e is None:
            e = ouvrir_emplacement(self, c)
            if not e:
                return None
        local = distant.cache(dossier_donnees(), c, chemin)
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                e.telecharger(chemin, local)
            finally:
                QApplication.restoreOverrideCursor()
        except distant.ErreurDistant as ex:
            erreur_distant(self, distant.libelle(c), ex, e)
            return None
        o = self.ouvrir(local)
        if o:
            o.distant = {"compte": c["id"], "cle": distant.cle_compte(c), "chemin": chemin, "lieu": distant.libelle(c)}
            self._maj_titre(o)
            self.statusBar().showMessage(_("Ouvert depuis {lieu} : {chemin}", lieu=distant.libelle(c), chemin=chemin), 8000)
            self._session(toucher=True)
        return o

    def _renvoyer(self, o):
        """Renvoie la copie de travail a son emplacement d'origine."""
        c = self._compte(o.distant["compte"], o.distant.get("cle"))
        if not c:
            QMessageBox.warning(self, "PhilPDF", _("Le compte d'origine n'existe plus sur ce poste : le fichier est "
                                                   "enregistré seulement ici :\n{chemin}", chemin=o.chemin))
            return False
        e = ouvrir_emplacement(self, c)
        if not e:
            QMessageBox.warning(self, "PhilPDF", _("Copie gardée sur ce PC : {chemin}", chemin=o.chemin))
            return False
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                e.envoyer(o.chemin, o.distant["chemin"])
            finally:
                QApplication.restoreOverrideCursor()
        except distant.ErreurDistant as ex:
            erreur_distant(self, distant.libelle(c), _("Envoi impossible ({erreur}). Copie gardée sur ce PC : {chemin}",
                                                     erreur=ex, chemin=o.chemin), e)
            return False
        self.statusBar().showMessage(_("Enregistré sur {lieu} : {chemin}", lieu=distant.libelle(c), chemin=o.distant["chemin"]), 8000)
        self._session()
        return True

    def enregistrer_distant(self, o=None):
        o = o or self.doc_courant()
        if not o:
            return False
        if not self.params.get("comptes"):
            self.preferences(onglet="comptes")
            return False
        d = DialogueParcourir(self, self.params, "enregistrer", nom=o.nom,
                              compte_id=(o.distant or {}).get("compte") if getattr(o, "distant", None) else None)
        if d.exec() != QDialog.Accepted or not d.choisi:
            return False
        c = d.compte()
        local = distant.cache(dossier_donnees(), c, d.choisi)
        try:
            o.enregistrer(local)
        except Exception as ex:
            QMessageBox.warning(self, "PhilPDF", _('Enregistrement impossible :\n{e}', e=ex))
            return False
        o.chemin, o.nom = local, os.path.basename(local)
        o.distant = {"compte": c["id"], "cle": distant.cle_compte(c), "chemin": d.choisi, "lieu": distant.libelle(c)}
        self._maj_titre(o)
        return self._renvoyer(o)

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
            QMessageBox.information(self, info[3], _('{x}\n\nCet outil est prévu dans une prochaine version de PhilPDF.', x=info[5]))
            return
        if not o:
            QMessageBox.information(self, "PhilPDF", _("Ouvrez d'abord un fichier PDF."))
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
            d.finished.connect(lambda _x: (setattr(o, "resultats", []), o.rafraichir_pages()))
            d.show()
        elif oid == "organiser":
            o.organiser(True)
        elif oid == "tampons":
            o.ouvrir_bibliotheque("tampons")
        elif oid in ("filigrane", "entete", "fond"):
            self.mise_en_page(o, oid)
        elif oid == "biffer":
            o.changer_mode("biffer")
        elif oid == "commentaires":
            self.statusBar().showMessage(_('Sélectionnez du texte : la barre rapide apparaît au-dessus de la sélection.'), 10000)
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
            fs = QFileDialog.getOpenFileNames(self, _('Images'), self.dossier_depart(), _('Images (*.png *.jpg *.jpeg *.tif *.tiff *.bmp)'))[0]
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
        d.setWindowTitle(_('Combiner des fichiers'))
        d.resize(560, 420)
        v = QVBoxLayout(d)
        v.addWidget(QLabel(_("Glissez pour changer l'ordre. Les fichiers seront assemblés de haut en bas.")))
        lst = QListWidget()
        lst.setDragDropMode(QListWidget.InternalMove)
        v.addWidget(lst, 1)
        for o in self.documents():
            if o.chemin:
                it = QListWidgetItem(icone("creer", "#c9252d"), os.path.basename(o.chemin))
                it.setData(Qt.UserRole, o.chemin)
                lst.addItem(it)
        h = QHBoxLayout()
        b = QPushButton(_('Ajouter des fichiers...'))
        b.clicked.connect(lambda: [lst.addItem(self._item(f)) for f in QFileDialog.getOpenFileNames(d, _('Ajouter'), self.dossier_depart(), _('PDF et images (*.pdf *.png *.jpg *.jpeg *.tif)'))[0]])
        h.addWidget(b)
        r = QPushButton(_('Retirer'))
        r.clicked.connect(lambda: [lst.takeItem(lst.row(i)) for i in lst.selectedItems()])
        h.addWidget(r)
        h.addStretch()
        v.addLayout(h)
        bb = boutons_fr(QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel))
        bb.button(QDialogButtonBox.Ok).setText(_('Combiner'))
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
            f, _x = QFileDialog.getSaveFileName(self, _('Exporter en texte'), base + ".txt", _('Texte (*.txt)'))
            if f:
                with open(f, "w", encoding="utf-8") as fh:
                    fh.write("\n\f".join(p.get_text() for p in o.doc))
        elif genre == "docx":
            f, _x = QFileDialog.getSaveFileName(self, _('Exporter en Word'), base + ".docx", _('Word (*.docx)'))
            if not f:
                return
            import tempfile, logging
            from pdf2docx import Converter
            logging.getLogger().setLevel(logging.ERROR)
            src = os.path.join(tempfile.mkdtemp(), "source.pdf")
            o.doc.save(src)
            prog = QProgressDialog(_('Conversion en Word...'), None, 0, 0, self)
            prog.setWindowModality(Qt.WindowModal)
            prog.show()
            QApplication.processEvents()
            try:
                c = Converter(src)
                c.convert(f)
                c.close()
                self.statusBar().showMessage(_('Exporté : {f}', f=f), 8000)
            except Exception as e:
                QMessageBox.warning(self, _('Exporter'), _('Conversion impossible :\n{e}', e=e))
            prog.close()
        else:
            dossier = QFileDialog.getExistingDirectory(self, _('Dossier des images'), os.path.dirname(base))
            if dossier:
                for n, p in enumerate(o.doc):
                    pm = p.get_pixmap(dpi=dpi, alpha=False)
                    cible = os.path.join(dossier, f"{os.path.basename(base)}_p{n + 1}.{genre}")
                    if genre == "jpg":
                        pm.save(cible, jpg_quality=qualite)
                    else:
                        pm.save(cible)
                self.statusBar().showMessage(_('{n} images {upper} enregistrées dans {dossier}', n=len(o.doc), upper=genre.upper(), dossier=dossier), 8000)

    def mise_en_page(self, o, oid):
        if oid == "filigrane":
            choix = question(self, _('Filigrane'), _('Que voulez-vous faire ?'),
                             [(_('Ajouter un filigrane'), QMessageBox.AcceptRole), (_('Retirer un filigrane'), QMessageBox.AcceptRole),
                              (_('Annuler'), QMessageBox.RejectRole)])
            if choix == 1:
                from moteur import objets
                o.memoriser(_('Retrait du filigrane'))
                n = objets.retirer_filigranes(o.doc)
                if not n:
                    cand = objets.filigranes_texte_probables(o.doc)
                    if cand:
                        t, ok = QInputDialog.getItem(self, _('Retirer un filigrane'), _('Filigrane trouvé :'), cand, 0, False)
                        if ok:
                            objets.retirer_texte_penche(o.doc, t)
                            n = len(o.doc)
                if n:
                    o.apres_modif([_("Filigrane retiré ({n} page{s}).", n=n, s='s' if n > 1 else '')], reconstruire=True)
                else:
                    o.annulations.pop()
                    o.maj_historique()
                    QMessageBox.information(self, _('Filigrane'), _('Aucun filigrane reconnu dans ce document.'))
                return
            if choix != 0:
                return
            d = DialogueFiligrane(self, self.params, len(o.doc), o.page_courante(), o.doc)
            if d.exec() == QDialog.Accepted:
                o.memoriser(_("Ajout d'un filigrane"))
                d.appliquer(o.doc)
                o.apres_modif([_('Filigrane ajouté.')])
        elif oid == "entete":
            d = DialogueEntete(self, o.doc, o.page_courante())
            if d.exec() == QDialog.Accepted:
                o.memoriser(_('En-tête et pied de page'))
                d.appliquer(o.doc)
                o.apres_modif([_('En-tête et pied de page ajoutés.')])
        elif oid == "fond":
            d = DialogueFond(self, o.doc, o.page_courante())
            if d.exec() == QDialog.Accepted:
                o.memoriser(_('Arrière-plan'))
                d.appliquer(o.doc)
                o.apres_modif([_('Arrière-plan appliqué.')])

    def numeriser(self):
        from moteur.scanner import scanners
        import sys as _s
        if _s.platform != "win32" and not scanners():
            QMessageBox.information(self, _('Numériser'), _('Aucun scanner détecté sur ce PC.'))
            return
        d = DialogueNumeriser(self)
        if d.exec() != QDialog.Accepted:
            return
        prog = QProgressDialog(_('Numérisation en cours...'), None, 0, 0, self)
        prog.setWindowModality(Qt.WindowModal)
        prog.show()
        QApplication.processEvents()
        try:
            doc = d.numeriser()
        except Exception as e:
            prog.close()
            QMessageBox.warning(self, _('Numériser'), _('La numérisation a échoué :\n{e}', e=e))
            return
        prog.close()
        if len(doc) == 0:
            QMessageBox.information(self, _('Numériser'), _('Aucune page numérisée.'))
            return
        o = self.ajouter_onglet(OngletDocument(self.params, biblio=self.biblio, doc=doc, nom="Numérisation.pdf"))
        if d.ocr.isChecked():
            self.statusBar().showMessage(_('Enregistrez la numérisation pour lancer la reconnaissance du texte.'), 10000)

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
        fs = QFileDialog.getOpenFileNames(self, _('Documents à imprimer'), self.dossier_depart(), FILTRE)[0]
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
        QMessageBox.information(self, _('Alléger le fichier'),
                                _("Poids estimé : {x} Ko → {x2} Ko ({x3} % de moins).\nEnregistrez pour appliquer (Enregistrer sous pour garder l'original).", x=avant // 1024, x2=apres // 1024, x3=100 - apres * 100 // max(1, avant)))

    def mot_de_passe(self, o):
        d = QDialog(self)
        d.setWindowTitle(_('Protéger par mot de passe'))
        f = QFormLayout(d)
        ouv = QLineEdit()
        ouv.setEchoMode(QLineEdit.Password)
        prop = QLineEdit()
        prop.setEchoMode(QLineEdit.Password)
        imp = QCheckBox(_("Interdire l'impression"))
        cop = QCheckBox(_('Interdire la copie du texte'))
        f.addRow(_("Mot de passe d'ouverture (facultatif)"), ouv)
        f.addRow(_('Mot de passe des droits'), prop)
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
        self.statusBar().showMessage(_("Protection appliquée à l'enregistrement (AES 256)."), 8000)

    def signer(self, o):
        img = os.path.join(o.params_dossier(), "signature.png")
        if not os.path.exists(img):
            f, _x = QFileDialog.getOpenFileName(self, _('Image de votre signature (fond transparent de préférence)'), "",
                                               _('Images (*.png *.jpg *.jpeg)'))
            if not f:
                return
            fitz.Pixmap(f).save(img)
            self.statusBar().showMessage(_('Signature enregistrée : elle sera proposée sur toutes vos machines synchronisées.'), 8000)
        o.changer_mode("signature")

    def ocr(self, o):
        from moteur.scan import tesseract_exe
        if not tesseract_exe():
            QMessageBox.information(self, _('Reconnaître le texte'),
                                    _("Le module de reconnaissance de texte est absent de ce paquet PhilPDF.\nTéléchargez la version complète (elle l'embarque)."))
            return
        if not o.chemin or o.modifie:
            QMessageBox.information(self, _('Reconnaître le texte'), _("Enregistrez d'abord le document."))
            return
        sortie = os.path.splitext(o.chemin)[0] + "_OCR.pdf"
        prog = QProgressDialog(_('Redressement, nettoyage et reconnaissance du texte...'), None, 0, 0, self)
        prog.setWindowTitle("PhilPDF")
        prog.setWindowModality(Qt.WindowModal)
        prog.show()
        t = TacheScan(o.chemin, sortie)
        self.taches.append(t)

        def fin(chemin, err):
            prog.close()
            if err == "__deja__":
                QMessageBox.information(self, _('Reconnaître le texte'),
                                        _("Ce document contient déjà du texte sur toutes ses pages : il n'y a rien à "
                                          "reconnaître. (La reconnaissance sert aux scans et aux photos de documents.)"))
            elif err:
                QMessageBox.warning(self, _('Reconnaître le texte'), _("La reconnaissance a échoué :\n{e}", e=err))
            else:
                self.ouvrir(chemin)
                self.statusBar().showMessage(_('Texte reconnu : {nom}', nom=os.path.basename(chemin)), 10000)
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
        QMessageBox.information(self, _('Propriétés'), _('Fichier : {x}\nPages : {n}\nCréé par : {x2}\nProduit par : {x3}\nPolices : {x4}', x=o.chemin or o.nom, n=len(o.doc), x2=m.get('creator') or '-', x3=m.get('producer') or '-', x4=', '.join(polices[:12]) or 'aucune (scan)'))

    def preferences(self, onglet=None):
        d = QDialog(self)
        d.setWindowTitle(_('Préférences'))
        d.setMinimumWidth(920)
        vd = QVBoxLayout(d)
        tabs = QTabWidget()
        vd.addWidget(tabs)

        def page(titre):
            w = QWidget()
            f = QFormLayout(w)
            tabs.addTab(w, titre)
            return f

        def note(f, texte, couleur="#555"):
            lb = QLabel(texte)
            lb.setWordWrap(True)
            lb.setStyleSheet(f"color:{couleur};font-size:12px")
            f.addRow(lb)

        def choisir_dossier(champ, titre):
            p = QFileDialog.getExistingDirectory(d, titre, champ.text() or os.path.expanduser("~"))
            if p:
                champ.setText(p)

        # ---------------- Général
        f = page(_('Général'))
        machine = QLineEdit(self.params["machine"])
        auteur = QLineEdit(self.params.get("auteur", ""))
        auteur.setPlaceholderText(_('Nom inscrit sur les tampons et commentaires'))
        f.addRow(_('Nom de ce poste (alias)'), machine)
        note(f, _("Par exemple « Pharmacie », « Maison », « Portable » : c'est le nom affiché sur vos autres postes."))
        f.addRow(_('Votre nom'), auteur)
        from .langue import disponibles, LANGUE
        langue = QComboBox()
        langue.addItem(_("Automatique (langue du système)"), "auto")
        for code, nom in disponibles():
            langue.addItem(nom, code)
        langue.setCurrentIndex(max(0, langue.findData(self.params.get("langue", "auto"))))
        f.addRow(_("Langue"), langue)
        hp = QHBoxLayout()
        be = QPushButton(_("Exporter mes préférences..."))
        be.clicked.connect(lambda: self.exporter_reglages(d))
        hp.addWidget(be)
        bi = QPushButton(_("Importer des préférences..."))
        bi.clicked.connect(lambda: (d.reject(), self.importer_reglages()))
        hp.addWidget(bi)
        hp.addStretch()
        f.addRow(_("Sauvegarde"), hp)
        note(f, _("Vos préférences sont aussi copiées automatiquement sur votre Drive (sans les mots de passe) : une "
                  "nouvelle installation propose de les reprendre."))
        note(f, _("Le changement de langue s'applique au prochain démarrage de PhilPDF. Pour ajouter une langue : "
                  "copier langues/en.json, le traduire et le renommer (es.json, de.json...)."))
        assoc = QCheckBox(_('Ouvrir les fichiers PDF avec PhilPDF (proposé dans « Ouvrir avec »)'))
        assoc.setChecked(self.params["association_pdf"])
        assoc.setEnabled(sys.platform == "win32" and not est_portable())
        f.addRow(assoc)

        # ---------------- Drive et dossiers
        f = page(_('Drive et dossiers'))
        from .synchro_choix import combo_emplacements
        drive = combo_emplacements(d, self.params)
        hs = QHBoxLayout()
        hs.addWidget(drive, 1)
        f.addRow(_('Synchronisation entre vos postes'), hs)
        note(f, _("Cet emplacement (Drive, NAS, FTP ou dossier partagé) sert de boîte aux lettres à PhilPDF entre vos postes : préférences, tampons et signatures, apprentissages, et liste des fichiers ouverts sur chaque poste (leurs emplacements, jamais les PDF eux-mêmes). Choisissez le même sur chaque poste."))
        connus = dossiers_connus()
        for clef, lib in (("documents", _('Documents')), ("telechargements", _('Téléchargements')), ("bureau", _('Bureau'))):
            lb = QLabel(connus.get(clef, _('(non trouvé)')))
            lb.setStyleSheet("color:#333")
            f.addRow(lib, lb)
        nas = QLineEdit(self.params.get("nas", ""))
        nas.setPlaceholderText(_('ex. \\\\NAS\\Partage, Z:\\ ou /mnt/nas'))
        bn = QPushButton(_('Choisir...'))
        bn.clicked.connect(lambda: choisir_dossier(nas, _('Dossier du NAS sur ce poste')))
        hn = QHBoxLayout()
        hn.addWidget(nas, 1)
        hn.addWidget(bn)
        f.addRow("NAS", hn)
        note(f, _("Documents, Téléchargements et Bureau sont détectés automatiquement, sous Windows comme sous Linux (%USERPROFILE%\\Documents ↔ ~/Documents). A l'ouverture, PhilPDF part du dernier dossier utilisé."))

        # ---------------- Comptes et emplacements
        w = QWidget()
        vc = QVBoxLayout(w)
        lc = QLabel(_("Vos NAS, serveurs FTP, WebDAV et Drives : on y ouvre et on y enregistre directement "
                      "(Fichier › Ouvrir depuis un emplacement). Chaque compte est enregistré une fois sur ce poste."))
        lc.setWordWrap(True)
        lc.setStyleSheet("color:#555")
        vc.addWidget(lc)
        vc.addWidget(PanneauComptes(w, self.params), 1)
        tabs.addTab(w, _("Comptes"))
        if onglet == "comptes":
            tabs.setCurrentWidget(w)

        # ---------------- Tampons et signatures
        from .dialogues import PanneauBibliotheque
        w = QWidget()
        vt = QVBoxLayout(w)
        tabs.addTab(w, _('Tampons et signatures'))
        panneaux = []
        for genre, titre in (("tampons", _('Mes tampons')), ("signatures", _('Mes signatures'))):
            t = QLabel(titre)
            t.setStyleSheet("font-weight:600;color:#616161")
            vt.addWidget(t)
            pb = PanneauBibliotheque(w, self.biblio, genre, self.params.get("auteur", ""), compact=True)
            pb.setMinimumHeight(215)
            vt.addWidget(pb, 1)
            panneaux.append(pb)
        hb = QHBoxLayout()
        bsync = QPushButton(_(' Synchroniser avec le Drive maintenant'))
        bsync.setIcon(icone("synchro", "#0f6cbd"))
        bsync.clicked.connect(lambda: (panneaux[0].synchroniser(), panneaux[1].rafraichir()))
        hb.addWidget(bsync)
        ls = QLabel(_('Chaque ajout, renommage ou suppression est envoyé tout seul au Drive ; vos autres postes les reçoivent à leur démarrage.'))
        ls.setWordWrap(True)
        ls.setStyleSheet("color:#555;font-size:12px")
        hb.addWidget(ls, 1)
        vt.addLayout(hb)
        fixer = QCheckBox(_("Incruster tampons et signatures dans la page à l'enregistrement"))
        fixer.setChecked(self.params.get("fixer_objets", False))
        vt.addWidget(fixer)
        lf = QLabel(_("Incrustés, ils font partie de la page : personne ne peut plus les déplacer ni les retirer, ni dans PhilPDF ni dans Acrobat. Sinon, ils restent des objets que l'on peut déplacer, agrandir ou supprimer."))
        lf.setWordWrap(True)
        lf.setStyleSheet("color:#555;font-size:12px")
        vt.addWidget(lf)

        # ---------------- Synchronisation (avancé)
        f = page(_('Avancé'))
        sync = QCheckBox(_('Synchroniser les fichiers ouverts sur mes différents postes'))
        sync.setChecked(self.params.get("synchro", True))
        f.addRow(sync)
        note(f, _("Au démarrage, PhilPDF vérifie en silence si un autre poste a une session plus récente ; si oui, il cherche ses fichiers ici quelques secondes, prévient par une bulle et laisse la proposition sur l'Accueil. Bouton de synchronisation manuelle sur l'Accueil et dans le menu Fichier."))
        racines = QListWidget()
        racines.setMaximumHeight(90)
        for r in self.params.get("racines", []):
            racines.addItem(r)
        hr = QHBoxLayout()
        br = QPushButton(_('Ajouter un emplacement...'))
        br.clicked.connect(lambda: (lambda p: p and racines.addItem(p))(QFileDialog.getExistingDirectory(d, _('Emplacement de vos documents'))))
        hr.addWidget(br)
        bs = QPushButton(_('Retirer'))
        bs.clicked.connect(lambda: [racines.takeItem(racines.row(i)) for i in racines.selectedItems()])
        hr.addWidget(bs)
        hr.addStretch()
        f.addRow(_('Autres emplacements à fouiller'), racines)
        f.addRow("", hr)
        bc = QPushButton(_(' Correspondances apprises et synchronisation...'))
        bc.setIcon(icone("synchro", "#2b6cb0"))
        bc.clicked.connect(self.synchroniser)
        f.addRow("", bc)

        # ---------------- IA
        f = page(_("IA"))
        moteur = QComboBox()
        moteur.addItems(["Claude", "Gemini", _('Les deux (double avis)')])
        moteur.setCurrentIndex({"claude": 0, "gemini": 1, "deux": 2}.get(self.params["ia_moteur"], 0))
        kc = QLineEdit(self.params["clef_claude"])
        kc.setEchoMode(QLineEdit.Password)
        kg = QLineEdit(self.params["clef_gemini"])
        kg.setEchoMode(QLineEdit.Password)
        f.addRow(_('Moteur IA'), moteur)
        f.addRow(_('Clef API Claude'), kc)
        f.addRow(_('Clef API Gemini'), kg)
        note(f, _('Gemini en offre gratuite : Google peut réutiliser les documents envoyés. A éviter pour les documents sensibles.'), "#a35c00")

        # ---------------- Mises à jour
        f = page(_('Mises à jour'))
        majs = QComboBox()
        majs.addItems([_('GitHub (Internet)'), _('Dossier synchronisé')])
        majs.setCurrentIndex(1 if self.params.get("maj_source") == "dossier" else 0)
        maja = QCheckBox(_('Vérifier les mises à jour à chaque démarrage'))
        maja.setChecked(self.params.get("maj_auto", True))
        f.addRow(_('Mises à jour depuis'), majs)
        f.addRow(maja)
        f.addRow(QLabel(_('Version {VERSION}. Données : {dossier_donnees}', VERSION=VERSION, dossier_donnees=dossier_donnees()) + (_(' (version portable)') if est_portable() else "")))

        bb = boutons_fr(QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel))
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        vd.addWidget(bb)
        if d.exec() != QDialog.Accepted:
            return
        ancienne_langue = self.params.get("langue", "auto")
        from .synchro_choix import valeurs as synchro_valeurs
        self.params.update(machine=machine.text().strip() or self.params["machine"],
                           drive=synchro_valeurs(drive, self.params)[0], drive_compte=synchro_valeurs(drive, self.params)[1],
                           auteur=auteur.text().strip(), fixer_objets=fixer.isChecked(),
                           nas=nas.text().strip(), synchro=sync.isChecked(), langue=langue.currentData(),
                           racines=[racines.item(i).text() for i in range(racines.count())],
                           ia_moteur=["claude", "gemini", "deux"][moteur.currentIndex()],
                           clef_claude=kc.text().strip(), clef_gemini=kg.text().strip(),
                           maj_source=["github", "dossier"][majs.currentIndex()], maj_auto=maja.isChecked())
        if assoc.isChecked() != self.params["association_pdf"]:
            if associer_pdf(assoc.isChecked()):
                self.params["association_pdf"] = assoc.isChecked()
        self.params.enregistrer()
        reglages.ecrire_drive(self.params)
        self._session()
        self.accueil.rafraichir()
        if miroir.compte_drive(self.params):
            self.synchro_miroir(au_demarrage=True)
        if self.params.get("langue", "auto") != ancienne_langue:
            if question(self, _("Langue"), _("La nouvelle langue s'applique au redémarrage. Redémarrer PhilPDF maintenant ?"),
                        [(_("Redémarrer"), QMessageBox.AcceptRole), (_("Plus tard"), QMessageBox.RejectRole)]) == 0:
                self.redemarrer()

    # ------------------------------------------------------------ sauvegarde des preferences
    def exporter_reglages(self, parent=None):
        parent = parent or self
        d = QDialog(parent)
        d.setWindowTitle(_("Exporter mes préférences"))
        f = QFormLayout(d)
        lb = QLabel(_("Le fichier contient les réglages communs (comptes, outils, barres, langue...) et ceux de ce poste "
                      "(nom, dossiers, chemins). A l'import, vous choisissez ce que vous reprenez."))
        lb.setWordWrap(True)
        f.addRow(lb)
        sec = QCheckBox(_("Inclure les mots de passe, autorisations des Drives et clefs IA"))
        f.addRow(sec)
        p1, p2 = QLineEdit(), QLineEdit()
        for p in (p1, p2):
            p.setEchoMode(QLineEdit.Password)
            p.setEnabled(False)
        sec.toggled.connect(lambda on: (p1.setEnabled(on), p2.setEnabled(on)))
        f.addRow(_("Phrase secrète"), p1)
        f.addRow(_("Confirmation"), p2)
        n2 = QLabel(_("Avec les mots de passe, le fichier est chiffré (AES-256) par cette phrase : sans elle, il est illisible."))
        n2.setWordWrap(True)
        n2.setStyleSheet("color:#555;font-size:12px")
        f.addRow(n2)
        bb = boutons_fr(QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel))
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        f.addRow(bb)
        while True:
            if d.exec() != QDialog.Accepted:
                return
            if sec.isChecked() and (len(p1.text()) < 6 or p1.text() != p2.text()):
                QMessageBox.warning(d, d.windowTitle(), _("Phrase secrète trop courte (6 caractères au moins) ou différente "
                                                           "de sa confirmation."))
                continue
            break
        nom = f"PhilPDF-preferences-{self.params['machine']}.philpdf"
        chemin, _x = QFileDialog.getSaveFileName(parent, _("Exporter mes préférences"),
                                                 os.path.join(self.dossier_depart(), nom), _("Préférences PhilPDF (*.philpdf)"))
        if not chemin:
            return
        reglages.exporter(chemin, reglages.instantane(self.params, sec.isChecked()), p1.text() if sec.isChecked() else None)
        self.statusBar().showMessage(_("Préférences exportées : {chemin}", chemin=chemin), 8000)

    def importer_reglages(self, donnees=None, origine=""):
        if donnees is None:
            chemin, _x = QFileDialog.getOpenFileName(self, _("Importer des préférences"), self.dossier_depart(),
                                                     _("Préférences PhilPDF (*.philpdf *.json)"))
            if not chemin:
                return
            phrase = None
            while True:
                try:
                    donnees = reglages.importer(chemin, phrase)
                    break
                except reglages.PhraseRequise:
                    phrase, ok = QInputDialog.getText(self, _("Importer des préférences"),
                                                      _("Ce fichier est chiffré. Phrase secrète :"), QLineEdit.Password)
                    if not ok:
                        return
                except (OSError, ValueError, KeyError):
                    QMessageBox.warning(self, _("Importer des préférences"), _("Ce fichier n'est pas un export de préférences PhilPDF."))
                    return
            origine = donnees.get("machine", "")
        d = QDialog(self)
        d.setWindowTitle(_("Importer des préférences"))
        v = QVBoxLayout(d)
        lb = QLabel(_("Préférences du poste « {poste} » ({date}). Que voulez-vous reprendre ?", poste=origine or "?",
                      date=date_fr(donnees.get("date", ""))))
        lb.setWordWrap(True)
        v.addWidget(lb)
        cc = QCheckBox(_("Réglages communs : comptes NAS / FTP / Drives, outils et favoris, barres et volets, langue, votre nom..."))
        cc.setChecked(True)
        v.addWidget(cc)
        cp = QCheckBox(_("Réglages propres au poste : nom du poste, dossiers et chemins (à cocher pour réinstaller ce même poste)"))
        cp.setChecked(origine == self.params.get("machine"))
        v.addWidget(cp)
        cs = QCheckBox(_("Mots de passe, autorisations et clefs contenus dans le fichier"))
        cs.setChecked(bool(donnees.get("secrets")))
        cs.setEnabled(bool(donnees.get("secrets")))
        v.addWidget(cs)
        bb = boutons_fr(QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel))
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        v.addWidget(bb)
        if d.exec() != QDialog.Accepted:
            return
        reglages.appliquer(self.params, donnees, cc.isChecked(), cp.isChecked(), cs.isChecked())
        if question(self, _("Importer des préférences"), _("Préférences reprises. Redémarrer PhilPDF pour tout appliquer ?"),
                    [(_("Redémarrer"), QMessageBox.AcceptRole), (_("Plus tard"), QMessageBox.RejectRole)]) == 0:
            self.redemarrer()

    def bienvenue(self, seulement_synchro=False):
        """Assistant : langue, nom, poste et emplacement de synchronisation ; puis reprise des preferences trouvees."""
        from .bienvenue import DialogueBienvenue
        nouveau = getattr(self.params, "nouveau", False)
        dl = DialogueBienvenue(self, self.params, seulement_synchro)
        if dl.exec() != QDialog.Accepted:
            self.params["bienvenue_vue"] = True
            self.params.enregistrer()
            return
        langue_changee = dl.appliquer()
        c = miroir.compte_drive(self.params)
        if c:                                        # premiere synchro tout de suite, pour trouver l'existant
            from PySide6.QtWidgets import QApplication
            from PySide6.QtGui import QCursor
            QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
            try:
                miroir.synchroniser(self.params, c)
            except distant.ErreurDistant as ex:
                QApplication.restoreOverrideCursor()
                erreur_distant(self, _("Synchronisation"), ex)
            else:
                QApplication.restoreOverrideCursor()
        trouve = None
        p = reglages.chemin_drive(self.params)
        if p:
            d = reglages.lire_drive(p)
            if d.get("communs") and (nouveau or d["communs"].get("par") != self.params.get("machine")):
                trouve = (miroir.libelle_compte(c) if c else os.path.dirname(os.path.dirname(p)), os.path.dirname(os.path.dirname(p)), d)
        if trouve:
            if self.proposer_reglages_drive(trouve):
                return
        reglages.ecrire_drive(self.params)
        if langue_changee:
            self.redemarrer()
        elif c:
            self.synchro_miroir(au_demarrage=True)
        else:
            self._synchro_biblio()

    def proposer_reglages_drive(self, trouve=None):
        """Des preferences PhilPDF existent sur l'emplacement de synchronisation -> proposer de les reprendre."""
        trouves = [trouve] if trouve else reglages.trouver_sur_drives()
        if not trouves:
            return False
        nom, racine, d = trouves[0]
        postes = sorted(d.get("postes", {}).items(), key=lambda kv: kv[1].get("maj", ""), reverse=True)
        if question(self, _("Bienvenue dans PhilPDF"),
                    _("Des préférences PhilPDF ont été trouvées sur votre {drive} (enregistrées par « {poste} », le {date}). "
                      "Les reprendre sur ce poste ?", drive=nom, poste=d["communs"].get("par", "?"),
                      date=date_fr(d["communs"].get("maj", ""))),
                    [(_("Reprendre"), QMessageBox.AcceptRole), (_("Non merci"), QMessageBox.RejectRole)]) != 0:
            return False
        donnees = {"philpdf": 1, "date": d["communs"].get("maj", ""), "communs": d["communs"], "poste": {}}
        if postes:
            libs = [_("Nouveau poste (garder le nom « {nom} »)", nom=self.params["machine"])] + \
                   [_("Réinstallation du poste « {poste} »", poste=p) for p, _v in postes]
            choix, ok = QInputDialog.getItem(self, _("Bienvenue dans PhilPDF"), _("Ce poste est :"), libs, 0, False)
            if ok and libs.index(choix) > 0:
                donnees["poste"] = postes[libs.index(choix) - 1][1]
        reglages.appliquer(self.params, donnees, True, bool(donnees["poste"]), False)
        if not self.params.get("drive") or not os.path.isdir(self.params.get("drive", "")):
            self.params["drive"] = racine
        self.params["bienvenue_vue"] = True
        self.params.enregistrer()
        self.redemarrer()
        return True

    def _chemin_drive(self, donnee):
        """Dossier « Drive » utilise par PhilPDF : dossier de l'application de bureau, ou miroir local d'un Drive en direct."""
        donnee = donnee or ""
        if donnee.startswith("compte:"):
            c = next((x for x in self.params.get("comptes", []) if x["id"] == donnee[7:]), None)
            return miroir.dossier_miroir(c) if c else ""
        return "" if donnee.startswith("nouveau:") else donnee

    def redemarrer(self):
        """Relance PhilPDF (apres un changement de langue, une importation de preferences...)."""
        from PySide6.QtCore import QProcess
        if getattr(sys, "frozen", False):
            prog, args = sys.executable, []
        else:
            prog, args = sys.executable, [os.path.abspath(sys.argv[0])]
        args += [o.chemin for o in self.documents() if o.chemin and not o.modifie and not o.distant]
        self._redemarrage = (prog, args)
        self.close()

    def verifier_maj(self, silencieux):
        t = TacheMaj(self.params)
        self.taches.append(t)
        t.trouve.connect(lambda r: self._maj_trouvee(r, silencieux))
        t.start()

    def _maj_trouvee(self, res, silencieux):
        if not res:
            if not silencieux:
                QMessageBox.information(self, _('Mises à jour'), _('PhilPDF {VERSION} est à jour.', VERSION=VERSION))
            return
        version, paquet, notes = res
        r = QMessageBox.question(self, _('Mise à jour disponible'),
                                 _('PhilPDF {version} est disponible (vous avez {VERSION}).\n\n{x}\n\nInstaller maintenant ? PhilPDF se fermera puis se relancera.', version=version, VERSION=VERSION, x=notes[:600]))
        if r != QMessageBox.Yes:
            return
        from .mise_a_jour import possible
        if not possible():
            QMessageBox.information(self, _('Mise à jour'), _('Téléchargez la nouvelle version ici :\n{paquet}', paquet=paquet))
            return
        # telechargement en arriere-plan : la fenetre reste utilisable, avec une barre de progression
        dlg = QProgressDialog(_("Téléchargement de PhilPDF {version}...", version=version), _("Annuler"), 0, 100, self)
        dlg.setWindowTitle(_('Mise à jour'))
        dlg.setMinimumDuration(0)
        dlg.setValue(0)
        t = TacheTelechargement(paquet)
        self.taches.append(t)

        def avance(fait, total):
            if total:
                dlg.setValue(int(fait * 100 / total))
                dlg.setLabelText(_("Téléchargement de PhilPDF {version}... {fait} / {total} Mo",
                                   version=version, fait=fait // 1024, total=total // 1024))

        def fini(fichier, erreur):
            dlg.close()
            if erreur:
                if not t.stop:
                    QMessageBox.warning(self, _('Mise à jour'), _('Echec du téléchargement :\n{e}', e=erreur))
                return
            from .mise_a_jour import appliquer
            try:
                lance = appliquer(fichier)
            except Exception as e:
                QMessageBox.warning(self, _('Mise à jour'), _("Installation impossible :\n{e}", e=e))
                return
            if lance:
                self._maj_en_cours = True
                self.close()
        t.avance.connect(avance)
        t.fini.connect(fini)
        dlg.canceled.connect(lambda: setattr(t, "stop", True))
        t.start()

    def raccourcis(self):
        QMessageBox.information(self, _('Raccourcis clavier'),
                                _("Ctrl+O  Ouvrir\nCtrl+S  Enregistrer\nShift+Ctrl+S  Enregistrer sous\nCtrl+P  Imprimer\n"
                                  "Ctrl+Z  Annuler\nShift+Ctrl+Z  Rétablir\nCtrl+C  Copier la sélection\nCtrl+F  Rechercher et remplacer\n"
                                  "Ctrl+ +/-  Zoom\nCtrl+1  Taille réelle\nCtrl+2  Ajuster à la largeur\n"
                                  "Shift+Ctrl++  Pivoter\nCtrl+W  Fermer le fichier\nF4  Vignettes\nShift+F4  Volet de droite\n"
                                  "F11  Plein écran"))

    def a_propos(self):
        QMessageBox.about(self, _('A propos de PhilPDF'),
                          _("<b>PhilPDF {version}</b> – Editeur PDF<br>Usage personnel et familial.<br><br>"
                            "Moteur PDF : PyMuPDF (AGPL). Interface : Qt / PySide6 (LGPL). OCR : Tesseract (Apache 2.0).<br>"
                            "Police de remplacement fournie : Nunito (SIL Open Font License).", version=VERSION))
