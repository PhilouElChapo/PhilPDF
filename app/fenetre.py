"""Fenetre principale de PhilPDF : menus, onglets, aiguillage des outils."""
import json, os, sys
import pymupdf as fitz
from PySide6.QtCore import Qt, QThread, Signal, QSize, QTimer
from PySide6.QtGui import QAction, QKeySequence, QImage, QPainter
from PySide6.QtWidgets import (QProgressBar, QToolButton, QMainWindow, QTabWidget, QFileDialog, QMessageBox, QDialog, QFormLayout,
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
from . import distant, miroir, reglages, coffre
from .dialogues_distant import DialogueParcourir, PanneauComptes, ouvrir_emplacement, erreur as erreur_distant
from .session import session_de, date_fr, nb_fichiers, dossiers_connus, DELAI_SILENCIEUX
from .dialogues import (boutons_fr, oeil, demander_secret, DialogueFiligrane, DialogueEntete, DialogueNumeriser, DialogueExporter,
                        DialogueBibliotheque, DialogueSynchro, DialogueFond)
from .langue import _

FILTRE = _('Documents PDF (*.pdf *.PDF)')


class TacheScan(QThread):
    fini = Signal(str, str)

    def __init__(self, entree, sortie, apprentissage=None):
        super().__init__()
        self.entree, self.sortie, self.apprentissage = entree, sortie, apprentissage

    def run(self):
        try:
            from moteur.scan import traiter
            r = traiter(self.entree, self.sortie, apprentissage=self.apprentissage)
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
    """Synchronise le dossier PhilPDF d'un Drive « en direct » avec son miroir local.
    mode : « tout » ; « plan » (ce qui changerait, decrit, sans rien faire) ; « choix » (seulement les fichiers choisis) ;
    « envois » (ce que ce poste a change, puis la liste de ce qui attend d'etre recu) ; « envois_seuls »."""
    fini = Signal(object, str)

    def __init__(self, params, mode="tout", choix=None):
        super().__init__()
        self.params, self.mode, self.choix = params, mode, choix

    def run(self):
        try:
            if self.mode == "plan":
                from .synchro_plan import decrire
                plan = miroir.planifier(self.params)
                self.fini.emit({"plan": plan, "lignes": decrire(plan, self.params) if plan else []}, "")
            elif self.mode == "choix":
                self.fini.emit(miroir.synchroniser(self.params, choix=self.choix), "")
            elif self.mode in ("envois", "envois_seuls"):
                r = miroir.synchroniser(self.params, sens=miroir.ENVOIS)
                attente = []
                if self.mode == "envois":
                    attente = [a for a in miroir.planifier(self.params) if a["action"] in miroir.RECEPTIONS]
                self.fini.emit({"res": r, "attente": attente}, "")
            else:
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
            plus_recente = bool(d)
            if not d:                     # pas plus recente : on montre quand meme sur l'Accueil ce qui est ouvert ailleurs
                autres = self.s.autres_machines()
                if autres:
                    m, date, _n = autres[0]
                    d = (m, date, self.s.lire()[m]["fichiers"])
            if d:
                m, date, fichiers = d
                res = self.s.retrouver_tous(m, fichiers, arret=lambda: self.stop, delai=DELAI_SILENCIEUX)
                self.resultat.emit((m, date, fichiers, res, plus_recente, dict(getattr(self.s, "doublons", {}))))
        except Exception:
            pass


EXTENSIONS_OUVRABLES = (".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp")


class PanneauSynchro(QFrame):
    """Encart en bas a droite pendant la synchronisation avec le Drive (ou NAS, FTP) : ce qui se passe, combien de
    fichiers recus et envoyes, et en cas d'echec la raison, avec « Autoriser » si ce poste n'a pas l'autorisation."""

    def __init__(self, fenetre, lieu, compte=None):
        super().__init__(fenetre)
        self.f, self.lieu = fenetre, lieu
        self.setObjectName("psync")
        self.setStyleSheet("#psync{background:#ffffff;border:1px solid #b9c9de;border-left:4px solid #2b6cb0;border-radius:8px}"
                           "QToolTip{background:#2b2b2b;color:#fff}")
        v = QVBoxLayout(self)
        v.setContentsMargins(12, 10, 12, 10)
        self.titre = QLabel(_("<b>Synchronisation avec {lieu}</b>", lieu=lieu))
        self.titre.setWordWrap(True)
        ht = QHBoxLayout()
        ht.setSpacing(8)
        self.ic = QLabel()
        self.ic.setFixedSize(28, 28)
        if compte:
            from . import avatars
            self.ic.setPixmap(avatars.icone_compte(compte, fenetre.params, 28).pixmap(28, 28))
        else:
            self.ic.setPixmap(icone("synchro", "#2b6cb0").pixmap(28, 28))
        ht.addWidget(self.ic, 0, Qt.AlignTop)
        ht.addWidget(self.titre, 1)
        v.addLayout(ht)
        self.texte = QLabel(_("Envoi de vos réglages, tampons et fichiers ouverts, réception de ceux de vos autres postes..."))
        self.texte.setWordWrap(True)
        self.texte.setStyleSheet("color:#444")
        v.addWidget(self.texte)
        self.barre = QProgressBar()
        self.barre.setRange(0, 0)
        self.barre.setMaximumHeight(6)
        self.barre.setTextVisible(False)
        v.addWidget(self.barre)
        self.boutons = QHBoxLayout()
        v.addLayout(self.boutons)
        self.setFixedWidth(420)
        self._placer()
        self.show()
        self.raise_()

    def _placer(self):
        m = self.layout().contentsMargins()
        lw = self.width() - m.left() - m.right() - 4
        h = m.top() + m.bottom() + max(28, self.titre.heightForWidth(lw - 36)) + self.texte.heightForWidth(lw) + 12
        h += (self.barre.sizeHint().height() + 6) if self.barre.isVisibleTo(self) else 0
        h += 36 if self.boutons.count() else 0
        self.setFixedHeight(max(60, h))
        p = self.f.rect()
        self.move(p.width() - self.width() - 16, p.height() - self.height() - 36)

    def _bouton(self, texte, f):
        b = QPushButton(texte)
        b.clicked.connect(f)
        self.boutons.addWidget(b)

    def etape(self, texte):
        self.texte.setText(texte)
        self.barre.show()
        self._placer()

    def terminer(self, etat, compte, message=None):
        self.barre.hide()
        if etat["ok"]:
            self.texte.setText(message or (_("✓ Tout est à jour.") if not (etat["recus"] or etat["envoyes"]) else
                               _("✓ Terminé : {r} élément(s) reçu(s) de vos autres postes, {e} envoyé(s).",
                                 r=etat["recus"], e=etat["envoyes"])))
            QTimer.singleShot(5000, self.deleteLater)
        else:
            self.setStyleSheet(self.styleSheet().replace("#2b6cb0", "#c9252d"))
            err = etat["erreur"]
            non_autorise = any(x in err.lower() for x in ("autoris", "401", "invalid_grant", "jeton", "token"))
            self.texte.setTextFormat(Qt.RichText)
            self.texte.setText(_("✕ Echec : {raison}", raison=err) + (
                "<br>" + _("Ce poste n'a pas (ou plus) l'autorisation d'accéder à {lieu} : cliquez sur « Autoriser ».",
                           lieu=self.lieu) if non_autorise else ""))
            if non_autorise:
                def autoriser():
                    from .dialogues_distant import autoriser_compte
                    if autoriser_compte(self.f, compte):
                        self.deleteLater()
                        self.f.synchro_miroir(au_demarrage=True)
                self._bouton(_("Autoriser..."), autoriser)
            self._bouton(_("Journal"), lambda: self.f.journal_echanges())
            self._bouton(_("Réessayer"), lambda: (self.deleteLater(), self.f.synchro_miroir(montrer=True)))
            self._bouton(_("Fermer"), self.deleteLater)
        self._placer()


class FenetreFermeture(QDialog):
    """Fenetre affichee pendant la fermeture : chaque etape (session, preferences, synchronisation) est montree,
    pour que l'attente s'explique. « Fermer sans attendre » saute la derniere synchronisation."""

    def __init__(self, parent, lieu):
        super().__init__(parent)
        self.lieu, self.presse = lieu, False
        self.setWindowTitle(_("Fermeture de PhilPDF"))
        self.setMinimumWidth(480)
        v = QVBoxLayout(self)
        t = QLabel(_("<b>PhilPDF range vos réglages avant de se fermer</b><br>"
                     "Vos autres postes retrouveront ainsi vos préférences et vos fichiers ouverts."))
        t.setWordWrap(True)
        v.addWidget(t)
        self.liste = QLabel()
        self.liste.setTextFormat(Qt.RichText)
        self.liste.setStyleSheet("color:#333;padding:6px 0")
        v.addWidget(self.liste)
        self.b = QPushButton(_("Fermer sans attendre"))
        self.b.clicked.connect(lambda: setattr(self, "presse", True))
        v.addWidget(self.b, 0, Qt.AlignRight)
        self.lignes = []
        self.show()
        self._peindre()

    def _peindre(self):
        self.liste.setText("<br>".join(self.lignes))
        self.adjustSize()
        for _i in range(3):
            QApplication.processEvents()

    def etape(self, texte, fonction):
        self.lignes.append("… " + texte)
        self._peindre()
        try:
            fonction()
            self.lignes[-1] = "✓ " + texte
        except Exception as ex:
            self.lignes[-1] = "✕ " + texte + f" <span style='color:#a33'>({str(ex)[:80]})</span>"
        self._peindre()

    def attendre(self, tache, ms, texte=None):
        if texte:
            self.lignes.append("… " + texte)
            self._peindre()
        import time
        fin = time.time() + ms / 1000
        while tache.isRunning() and time.time() < fin and not self.presse:
            tache.wait(100)
            QApplication.processEvents()
        if texte:
            self.lignes[-1] = ("✓ " if not tache.isRunning() else "– ") + texte
            self._peindre()


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
        self.setAcceptDrops(True)                  # deposer des PDF (ou des images) sur la fenetre les ouvre
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
        self.accueil.rechercher.connect(lambda: self.lancer_outil("ia_recherche"))
        self.accueil.action_fichier.connect(self.action_fichier)
        self.accueil.reprendre.connect(self.reprendre_proposee)
        self.accueil.synchroniser.connect(self.synchroniser)
        self.accueil.session_vue.connect(self.marquer_session_vue)
        self.accueil.synchro_drive.connect(self.synchro_manuelle)
        self.accueil.chercher_recent.connect(self.chercher_recent)
        self.accueil.doublon_choisi.connect(lambda m, e, p: session_de(self.params).apprendre_depuis(m, e, p))
        self.accueil.changer_synchro.connect(lambda: self.bienvenue(seulement_synchro=True))
        self.synchro = None              # (machine, date, fichiers, resultats) trouve au demarrage
        self._session_touchee = False    # on n'ecrit la session que si des fichiers ont ete ouverts ou fermes
        self.outils = PageOutils(self.params)
        self.outils.outil_choisi.connect(self.lancer_outil)
        self.outils.epingles_changes.connect(self._epingles)
        self.onglets.addTab(self.accueil, _('Accueil'))
        self.onglets.addTab(self.outils, _('Outils'))
        for i in (0, 1):
            self.onglets.tabBar().setTabButton(i, self.onglets.tabBar().ButtonPosition.RightSide, None)
        self._onglets_fixes()
        self.setCentralWidget(self.onglets)
        try:                                         # ancien chemin reste dans les reglages : on le remet sur la copie du compte
            c_ = miroir.compte_drive(self.params)
            if c_ and self.params.get("drive") != miroir.dossier_miroir(c_):
                from .journal import ecrire as _ecr
                _ecr("synchro", f"chemin de synchronisation corrigé : {self.params.get('drive')} → {miroir.dossier_miroir(c_)}")
                self.params["drive"] = miroir.dossier_miroir(c_)
                self.params.enregistrer()
        except Exception:
            pass
        from . import bibliotheque as _bib
        _bib.RAPPEL_ENVOI[:] = [lambda: QTimer.singleShot(800, self.synchro_miroir)]   # tampons envoyes tout de suite
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
            QTimer.singleShot(2200, self.communs_au_demarrage)
            QTimer.singleShot(2500, self.secrets_au_demarrage)

    def _synchro_biblio(self, envoyer=True):
        try:
            r = self.biblio.synchroniser_drive()
        except OSError:
            r = None
        if r and r[0]:
            self.statusBar().showMessage(_('{x} tampon(s) / signature(s) reçu(s) de vos autres postes.', x=r[0]), 8000)
        if envoyer and r and r[1] and miroir.compte_drive(self.params):
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
        act(m, _('Synchroniser maintenant...'), self.synchro_manuelle, None, "synchro")
        act(m, _('Fichiers ouverts sur mes autres postes...'), self.synchroniser, None, "recent")
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
        act(m, _('Propriétés du document...'), self.proprietes, "Ctrl+D", "info")
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
        act(m, _("Vérifier l'orthographe..."), self.verifier_orthographe, "F7", "modifier")
        act(m, _('Préférences...'), self.preferences, "Ctrl+K", "parametres")
        act(m, _('Identités numériques (signature)...'), self.identites_numeriques, None, "certificat")
        act(m, _('Emplacement de synchronisation...'), lambda: self.bienvenue(seulement_synchro=True), None, "synchro")

        m = mb.addMenu(_('&Affichage'))
        act(m, _('Pivoter la page (90°, sens horaire)'), lambda: self.doc_courant() and self.doc_courant().pivoter_courante(90), "Shift+Ctrl++", "pivoter")
        act(m, _('Pivoter la page (90°, sens anti-horaire)'), lambda: self.doc_courant() and self.doc_courant().pivoter_courante(-90), "Shift+Ctrl+-", "annuler")
        act(m, _('Zoom avant'), lambda: self.doc_courant() and self.doc_courant().changer_zoom(self.doc_courant().zoom * 1.2), "Ctrl++", "zoom_plus")
        act(m, _('Zoom arrière'), lambda: self.doc_courant() and self.doc_courant().changer_zoom(self.doc_courant().zoom / 1.2), "Ctrl+-", "zoom_moins")
        act(m, _('Taille réelle'), lambda: self.doc_courant() and self.doc_courant().changer_zoom(1.0), "Ctrl+1", "taille_reelle")
        act(m, _('Ajuster à la largeur'), self.ajuster_largeur, "Ctrl+2", "largeur")
        m.addSeparator()
        act(m, _('Vignettes des pages'), lambda: self.doc_courant() and self.doc_courant().basculer_vignettes(), "F4", "volet_gauche")
        sm = m.addMenu(icone("volet_droit", "#444444"), _('Volet de droite'))
        for lib, mode in ((_('Complet'), "complet"), (_('Icônes seules'), "icones"), (_('Masqué'), "masque")):
            act(sm, lib, lambda _x=False, md=mode: [o.mode_volet(md) for o in self.documents()])
        sm2 = m.addMenu(icone("volet_droit", "#444444"), _('Contenu du volet de droite'))
        for cle, lib, ic in OngletDocument.CONTENUS_VOLET():
            act(sm2, lib, lambda _x=False, c=cle: self.doc_courant() and self.doc_courant().contenu_volet(c), None, ic)
        act(m, _('Réduire ou afficher le volet de droite'), lambda: self.doc_courant() and self.doc_courant().basculer_volet(), "Shift+F4")
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
        act(m, _('Journal des échanges (Drives, NAS, IA)...'), self.journal_echanges, None, "lot")
        act(m, _('A propos de PhilPDF'), self.a_propos, None, "aide")

    def verifier_orthographe(self):
        o = self.doc_courant()
        if not o:
            QMessageBox.information(self, _("Orthographe"), _("Ouvrez d'abord un fichier PDF."))
            return
        from .orthographe import verifier_document
        verifier_document(self, o)

    def personnaliser_barre(self):
        """Choisir et ordonner les boutons de la barre d'outils des documents (independante du volet de droite)."""
        from .outils import OUTILS
        from types import SimpleNamespace
        o = self.doc_courant()
        ref = SimpleNamespace(params=self.params)
        par_defaut = OngletDocument.barre_par_defaut(ref)
        actuelle = list(self.params.get("barre") or par_defaut)
        d = QDialog(self)
        d.setWindowTitle(_("Personnaliser la barre d'outils"))
        d.resize(760, 560)
        v = QVBoxLayout(d)
        lb = QLabel(_("Glissez pour changer l'ordre. La barre passe sur plusieurs lignes si la fenêtre est étroite. "
                      "Elle est la même sur tous vos postes."))
        lb.setWordWrap(True)
        v.addWidget(lb)
        h = QHBoxLayout()
        dispo, barre = QListWidget(), QListWidget()
        barre.setDragDropMode(QListWidget.InternalMove)
        libelle = OngletDocument.libelle_element

        def item(cle):
            it = QListWidgetItem(libelle(ref, cle))
            it.setData(Qt.UserRole, cle)
            return it
        cles = OngletDocument.ELEMENTS_BARRE + [x[0] for x in OUTILS if x[6]]
        for c in actuelle:
            barre.addItem(item(c))

        def remplir_dispo():
            dispo.clear()
            presents = {barre.item(i).data(Qt.UserRole) for i in range(barre.count())}
            for c in cles:
                if c not in presents or c == "|":
                    dispo.addItem(item(c))
        remplir_dispo()
        vg = QVBoxLayout()
        vg.addWidget(QLabel(_("<b>Disponibles</b>")))
        vg.addWidget(dispo)
        h.addLayout(vg, 1)
        vb = QVBoxLayout()
        vb.addStretch(1)
        b_aj, b_ret = QPushButton(_("Ajouter →")), QPushButton(_("← Retirer"))
        vb.addWidget(b_aj)
        vb.addWidget(b_ret)
        vb.addStretch(1)
        h.addLayout(vb)
        vd = QVBoxLayout()
        vd.addWidget(QLabel(_("<b>Dans la barre</b> (de gauche à droite)")))
        vd.addWidget(barre)
        h.addLayout(vd, 1)
        v.addLayout(h, 1)

        def ajouter():
            for it in dispo.selectedItems() or ([dispo.currentItem()] if dispo.currentItem() else []):
                ligne = barre.currentRow() + 1 if barre.currentRow() >= 0 else barre.count()
                barre.insertItem(ligne, item(it.data(Qt.UserRole)))
            remplir_dispo()

        def retirer():
            for it in barre.selectedItems():
                barre.takeItem(barre.row(it))
            remplir_dispo()
        b_aj.clicked.connect(ajouter)
        b_ret.clicked.connect(retirer)
        dispo.itemDoubleClicked.connect(lambda _i: ajouter())
        barre.itemDoubleClicked.connect(lambda _i: retirer())
        hb = QHBoxLayout()
        b_def = QPushButton(_("Barre par défaut"))

        def defaut():
            barre.clear()
            for c in par_defaut:
                barre.addItem(item(c))
            remplir_dispo()
        b_def.clicked.connect(defaut)
        hb.addWidget(b_def)
        hb.addStretch(1)
        bb = boutons_fr(QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel))
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        hb.addWidget(bb)
        v.addLayout(hb)
        if d.exec() != QDialog.Accepted:
            return
        self.params["barre"] = [barre.item(i).data(Qt.UserRole) for i in range(barre.count())]
        self.params.enregistrer()
        for doc in self.documents():
            doc.construire_barre()

    def journal_echanges(self):
        """Les derniers echanges avec les Drives, NAS, FTP et IA (mots de passe masques), a copier pour un depannage."""
        from PySide6.QtWidgets import QPlainTextEdit
        from .journal import chemin
        p = chemin()
        try:
            with open(p, encoding="utf-8", errors="replace") as f:
                lignes = f.readlines()[-800:]
        except OSError:
            lignes = []
        d = QDialog(self)
        d.setWindowTitle(_("Journal des échanges"))
        d.resize(1000, 620)
        v = QVBoxLayout(d)
        lb = QLabel(_("Ce qu'ont échangé PhilPDF et vos Drives, NAS, FTP et IA (les 800 dernières lignes ; mots de passe, "
                      "codes et jetons masqués). Copiez-le pour signaler un problème."))
        lb.setWordWrap(True)
        v.addWidget(lb)
        t = QPlainTextEdit("".join(lignes) or _("Aucun échange enregistré."))
        t.setReadOnly(True)
        t.setLineWrapMode(QPlainTextEdit.NoWrap)
        f_ = t.font()
        f_.setFamily("Consolas")
        t.setFont(f_)
        v.addWidget(t, 1)
        h = QHBoxLayout()
        b = QPushButton(_("Copier"))
        b.clicked.connect(lambda: QApplication.clipboard().setText(t.toPlainText()))
        h.addWidget(b)
        b = QPushButton(_("Ouvrir le dossier"))
        b.clicked.connect(lambda: montrer_dans_explorateur(p))
        h.addWidget(b)
        h.addStretch(1)
        b = QPushButton(_("Fermer"))
        b.clicked.connect(d.accept)
        h.addWidget(b)
        v.addLayout(h)
        t.moveCursor(t.textCursor().MoveOperation.End)
        d.exec()

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

    def _onglets_fixes(self):
        """Accueil et Outils toujours visibles a gauche, meme quand beaucoup de fichiers sont ouverts
        (les onglets des fichiers defilent avec les fleches, pas ces deux-la)."""
        coin = QWidget()
        h = QHBoxLayout(coin)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        self.b_fixes = {}
        style = ("QToolButton{padding:10px 18px;font-size:14px;background:#ececec;border:none;color:#1f1f1f}"
                 "QToolButton:checked{background:#fff;border-top:3px solid #c9252d;font-weight:600}"
                 "QToolButton:hover:!checked{background:#e2e2e2}")
        for w, texte in ((self.accueil, _('Accueil')), (self.outils, _('Outils'))):
            b = QToolButton()
            b.setText(texte)
            b.setCheckable(True)
            b.setAutoRaise(True)
            b.setStyleSheet(style)
            b.clicked.connect(lambda _c=False, w=w: self.onglets.setCurrentWidget(w))
            h.addWidget(b)
            self.b_fixes[w] = b
        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setStyleSheet("color:#d0d0d0")
        h.addWidget(sep)
        self.coin_fixe = coin
        self.onglets.setCornerWidget(coin, Qt.TopLeftCorner)
        self._maj_onglets_fixes()

    def _maj_onglets_fixes(self):
        """Sans fichier ouvert : Accueil et Outils sont des onglets ordinaires. Avec des fichiers : ils deviennent
        deux boutons fixes a gauche (les onglets des fichiers defilent seuls)."""
        if not hasattr(self, "coin_fixe"):
            return
        docs = self.onglets.count() > 2
        for i in (0, 1):
            self.onglets.tabBar().setTabVisible(i, not docs)
        self.coin_fixe.setVisible(docs)
        w = self.onglets.currentWidget()
        for page, b in self.b_fixes.items():
            b.setChecked(page is w)

    def _onglet_change(self, i):
        w = self.onglets.widget(i)
        self._maj_onglets_fixes()
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

    # ------------------------------------------------------------ glisser-deposer de fichiers sur la fenetre
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls() and any(u.isLocalFile() and u.toLocalFile().lower().endswith(EXTENSIONS_OUVRABLES)
                                          for u in e.mimeData().urls()):
            e.acceptProposedAction()
        else:
            e.ignore()

    def dragMoveEvent(self, e):
        self.dragEnterEvent(e)

    def dropEvent(self, e):
        fichiers = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        pdfs = [f for f in fichiers if f.lower().endswith(".pdf")]
        images = [f for f in fichiers if f.lower().endswith(EXTENSIONS_OUVRABLES[1:])]
        for f in pdfs:
            self.ouvrir(f)
        if images:                                    # images deposees : un PDF est cree a partir d'elles
            try:
                import pymupdf as _f
                d = _f.open()
                for im in images:
                    i = _f.open(im)
                    d.insert_pdf(_f.open("pdf", i.convert_to_pdf()))
                from .config import dossier_donnees
                sortie = os.path.join(dossier_donnees(), os.path.splitext(os.path.basename(images[0]))[0] + ".pdf")
                d.save(sortie)
                self.ouvrir(sortie)
            except Exception as ex:
                QMessageBox.warning(self, "PhilPDF", _("Impossible d'ouvrir ce fichier :\n{e}", e=ex))
        e.acceptProposedAction()

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
            mdp, ok = demander_secret(self, _('Mot de passe'), _('Ce PDF est protégé. Mot de passe :'))
            if not ok or not o.doc.authenticate(mdp):
                return None
            o.mdp_pdf = mdp
            o.verifier_signe(chemin)
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
                self.lancer_outil({"resume": "ia_resume", "classer": "ia_classer"}.get(action, action))

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
        self._maj_onglets_fixes()
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
        fen = FenetreFermeture(self, self._lieu_court())
        fen.etape(_("Session enregistrée (fichiers ouverts, pages, zoom)"), lambda: (self._session(), self.params.enregistrer()))
        if reglages.chemin_drive(self.params):
            fen.etape(_("Préférences envoyées vers {lieu}", lieu=fen.lieu), lambda: reglages.ecrire_drive(self.params))
        if self.params.get("synchro_secrets"):
            fen.etape(_("Mots de passe chiffrés envoyés"), self._ecrire_secrets)
        for t in self.taches:
            if isinstance(t, TacheSynchro):
                t.stop = True
                fen.attendre(t, 2000)
        if miroir.compte_drive(self.params):         # derniere synchro avec le Drive (8 s au plus)
            t = getattr(self, "_t_miroir", None)
            if t and t.isRunning():
                fen.attendre(t, 8000, _("Synchronisation en cours avec {lieu}...", lieu=fen.lieu))
            t = TacheMiroir(self.params, "envois_seuls")     # a la fermeture : seulement ce que ce poste a change
            t.start()
            fen.attendre(t, 8000, _("Envoi de vos derniers changements à {lieu} (8 s au plus)...", lieu=fen.lieu))
        fen.close()
        srv = getattr(self, "serveur_instance", None)
        if srv is not None:                            # le PhilPDF relance (redemarrage) devient l'instance principale
            srv.close()
        e.accept()
        if getattr(self, "_redemarrage", None):
            from PySide6.QtCore import QProcess
            QProcess.startDetached(*self._redemarrage)

    def _lieu_court(self):
        try:
            c = miroir.compte_drive(self.params)
            return miroir.libelle_compte(c) if c else (self.params.get("drive") or _("votre emplacement de synchronisation"))
        except Exception:
            return _("votre emplacement de synchronisation")

    def _noter_synchro(self, ok, recus=0, envoyes=0, err=""):
        import datetime
        etat = {"quand": datetime.datetime.now().isoformat(timespec="minutes"), "ok": ok,
                "recus": recus, "envoyes": envoyes, "erreur": (err or "")[:300]}
        self.params["synchro_etat"] = etat
        self.params.enregistrer()
        self.accueil.rafraichir()
        return etat

    def _apres_synchro(self, au_demarrage, reglages_choisis=False):
        """Ce qui est arrive dans la copie locale passe dans PhilPDF : tampons, reglages (a choisir), mots de passe."""
        self._synchro_biblio(envoyer=False)
        self.communs_au_demarrage(ouvrir=reglages_choisis)
        self.secrets_au_demarrage()
        if au_demarrage and self.params.get("synchro", True):
            self.verifier_synchro()

    def synchro_miroir(self, au_demarrage=False, montrer=None, manuel=False, parent=None, apres=None):
        """Au demarrage et a la demande : on regarde d'abord ce qui a change, puis une fenetre montre ce qui va etre
        recu et envoye, a cocher. Chaque minute (et juste apres un changement de tampon) : seuls les changements faits
        sur ce poste partent ; ce qui arrive des autres postes attend votre accord (une bulle le signale)."""
        c = miroir.compte_drive(self.params)
        if not c:
            return
        t0 = getattr(self, "_t_miroir", None)
        if t0 is not None and t0.isRunning():
            if au_demarrage or manuel:
                QTimer.singleShot(1500, lambda: self.synchro_miroir(au_demarrage, montrer, manuel, parent, apres))
            return
        if not (au_demarrage or manuel or montrer):
            self._synchro_envois(c)
            return
        self._synchro_biblio(envoyer=False)          # tampons de ce poste copies dans la copie locale avant de regarder
        lieu = miroir.libelle_compte(c)
        panneau = PanneauSynchro(self, lieu, c)
        panneau.etape(_("Recherche de ce qui a changé sur {lieu} et sur ce poste...", lieu=lieu))
        t = self._t_miroir = TacheMiroir(self.params, "plan")
        self.taches.append(t)

        def finir(etat, message=None, choix=()):
            panneau.terminer(etat, c, message)
            self._apres_synchro(au_demarrage, "preferences.json" in choix)
            if apres:
                apres()

        def plan_pret(obj, err):
            if err:
                return finir(self._noter_synchro(False, err=err))
            plan, lignes = obj["plan"], obj["lignes"]
            if not plan:
                return finir(self._noter_synchro(True))
            from .synchro_plan import merite_fenetre, DialoguePlan
            if merite_fenetre(lignes):
                panneau.hide()
                from . import avatars
                d = DialoguePlan(parent or self, lignes, lieu, avatars.icone_compte(c, self.params))
                self._dlg_plan = d                       # pour les tests
                choix = d.choisis() if d.exec() == QDialog.Accepted else set()
                panneau.show()
                panneau.raise_()
                if not choix:
                    return finir(self._noter_synchro(True), _("Rien n'a été fait : ce sera proposé à la prochaine synchronisation."))
            else:
                choix = {a["rel"] for a in plan}           # seulement l'etat de ce poste a envoyer : pas besoin de demander
            panneau.etape(_("Synchronisation de {n} élément(s) avec {lieu}...", n=len(choix), lieu=lieu))
            t2 = self._t_miroir = TacheMiroir(self.params, "choix", choix)
            self.taches.append(t2)

            def fait(res, err2):
                finir(self._noter_synchro(not err2, res[0] if res else 0, res[1] if res else 0, err2), choix=choix)
            t2.fini.connect(fait)
            t2.start()
        t.fini.connect(plan_pret)
        t.start()

    def synchro_manuelle(self, parent=None, apres=None):
        if not miroir.compte_drive(self.params):
            return self.synchroniser()
        self.synchro_miroir(manuel=True, parent=parent, apres=apres)
        if self.params.get("synchro", True):
            QTimer.singleShot(4000, self.verifier_synchro)

    def _synchro_envois(self, c):
        t = self._t_miroir = TacheMiroir(self.params, "envois")
        self.taches.append(t)

        def fini(obj, err):
            if err:
                self._noter_synchro(False, err=err)
                PanneauSynchro(self, miroir.libelle_compte(c), c).terminer(self.params["synchro_etat"], c)
                return
            r = obj["res"]
            if r[1]:
                self._noter_synchro(True, 0, r[1])
                self.statusBar().showMessage(_("{n} changement(s) de ce poste envoyé(s) à vos autres postes.", n=r[1]), 6000)
            attente = obj["attente"]
            sig = tuple(sorted((a["rel"], a.get("date", "")) for a in attente))
            if attente and sig != getattr(self, "_attente_vue", None):
                self._attente_vue = sig
                Notification(self, _("{n} nouveauté(s) de vos autres postes attendent votre accord.", n=len(attente)),
                             _("Voir et choisir..."), lambda: self.synchro_miroir(manuel=True))
        t.fini.connect(fini)
        t.start()

    def verifier_synchro(self):
        """Au demarrage, en silence : session plus recente et differente sur un autre poste ?"""
        t = TacheSynchro(session_de(self.params), [o.chemin for o in self.documents() if o.chemin])
        t.resultat.connect(self._synchro_trouvee)
        self.taches.append(t)
        t.start()

    @staticmethod
    def _signature_session(m, fichiers):
        return m + "|" + ",".join(sorted((e.get("empreinte") or e.get("nom") or "") for e in fichiers))

    def marquer_session_vue(self):
        """Reprendre ou Ignorer : le bandeau ne revient que si l'autre poste ouvre d'autres fichiers."""
        if self.synchro:
            m, _d, fichiers, _r = self.synchro
            vues = dict(self.params.get("sessions_vues") or {})
            vues[m] = self._signature_session(m, fichiers)
            self.params["sessions_vues"] = vues
            self.params.enregistrer()

    def chercher_recent(self, machine, e):
        """Fichier recent d'un autre poste, introuvable ici d'un coup d'oeil : recherche sur ce poste (quelques
        secondes), sinon vous l'indiquez ; PhilPDF retient le dossier pour la suite."""
        from .session import retenir_trouve
        s = session_de(self.params)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            res = s.retrouver_tous(machine, [e], delai=8)
        finally:
            QApplication.restoreOverrideCursor()
        doublons = getattr(s, "doublons", {}).get(0)
        trouve = res[0][0]
        if doublons:
            self.accueil.doublons = {0: doublons}
            self.accueil._autre = (machine, "", [e], res, False, {0: doublons})
            trouve = self.accueil.choisir_doublon(0)
        if not trouve:
            r = QMessageBox.question(self, _("Fichier introuvable"),
                                     _("« {nom} » (ouvert sur {poste}) n'a pas été trouvé sur ce poste.\nVoulez-vous l'indiquer vous-même ?",
                                       nom=e.get("nom"), poste=machine))
            if r != QMessageBox.Yes:
                return
            trouve, _f = QFileDialog.getOpenFileName(self, _("Où est « {nom} » sur ce poste ?", nom=e.get("nom")),
                                                     self.dossier_depart(), "PDF (*.pdf)")
            if not trouve:
                return
        s.apprendre_depuis(machine, e, trouve)
        retenir_trouve(machine, e, trouve)
        self.ouvrir(trouve)
        self.accueil.rafraichir()

    def _synchro_trouvee(self, r):
        """Fichiers ouverts sur un autre poste : retrouves ici en arriere-plan, montres dans les Recents (plus de bandeau)."""
        from .session import retenir_trouve
        m, date, fichiers, res = r[:4]
        self.synchro = (m, date, fichiers, res)
        for e, (c, _x) in zip(fichiers, res):
            if c and not c.startswith("distant:"):
                retenir_trouve(m, e, c)
        self.accueil.rafraichir()
        return

    def _ancien_synchro_trouvee(self, r):
        m, date, fichiers, res, plus_recente = r[:5]
        doublons = r[5] if len(r) > 5 else {}
        self.synchro = (m, date, fichiers, res)
        ouverts = {os.path.normcase(o.chemin) for o in self.documents() if o.chemin}
        deja_ouverts = all(c and os.path.normcase(c) in ouverts for c, _x in res) if res else True
        deja_vu = deja_ouverts or (self.params.get("sessions_vues") or {}).get(m) == self._signature_session(m, fichiers)
        self.accueil.montrer_synchro(m, date, fichiers, res, plus_recente, doublons, deja_vu=deja_vu)
        n = sum(1 for c, _x in res if c)
        if not plus_recente or deja_vu:
            return
        Notification(self, _('Session plus récente sur {m} ({date}) : {nb}, {n} retrouvé{x} ici.', m=m, date=date_fr(date), nb=nb_fichiers(len(fichiers)), n=n, x='s' if n > 1 else ''), _('Voir'),
                     lambda: self.onglets.setCurrentWidget(self.accueil))

    def reprendre_proposee(self):
        if self.synchro and getattr(self.accueil, "doublons", None):     # d'abord choisir l'emplacement des doublons
            for i in list(self.accueil.doublons):
                if self.accueil.choisir_doublon(i) is None:
                    return
            m, date, fichiers, _r = self.synchro
            self.synchro = (m, date, fichiers, self.accueil._autre[3])
        self.marquer_session_vue()
        self.accueil.cacher_synchro()
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
        if o.mode != "formulaire" and any((w.field_value or "") not in ("", "Off") for p_ in o.doc for w in (p_.widgets() or [])
                                          if w.field_type not in (fitz.PDF_WIDGET_TYPE_BUTTON, fitz.PDF_WIDGET_TYPE_SIGNATURE)):
            if not o.avant_enregistrer():
                return False
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
        if oid == "__ouvrir__":
            self.dialogue_ouvrir()
            return
        if oid == "__barre__":
            self.personnaliser_barre()
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
        if oid == "ia_recherche":
            from .recherche import DialogueRecherche
            self._recherche = DialogueRecherche(self)
            self._recherche.show()
            return
        if oid in ("comparer", "ia_comparer"):
            from .dialogues_ia import comparer
            comparer(self, o, avec_ia=(oid == "ia_comparer"))
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
        if oid == "ia_resume":
            from .dialogues_ia import resumer
            resumer(self, o)
        elif oid == "ia_classer":
            from .dialogues_ia import classer
            classer(self, o)
        elif oid == "ia_traduire":
            from .dialogues_ia import traduire
            traduire(self, o)
        elif oid == "ocr_ia":
            from .dialogues_ia import ocr_ia
            ocr_ia(self, o)
        elif oid == "modifier":
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
        elif oid == "certificat":
            o.changer_mode("signer_num")
        elif oid == "champ_signature":
            o.changer_mode("champ_signature")
        elif oid == "formulaire":
            o.changer_mode("formulaire")
            mode_ = self.params.get("formulaire_detection", "auto")
            if not o.nb_champs() and mode_ != "jamais":
                if mode_ == "auto" or question(self, _("Formulaire"), _("Repérer tout seul les zones à remplir de ce document ?"),
                                               [(_("Repérer les champs"), QMessageBox.AcceptRole),
                                                (_("Non, je les trace"), QMessageBox.RejectRole)]) == 0:
                    o.detecter_champs()
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
        from .alleger import DialogueAlleger
        DialogueAlleger(self, o).exec()

    def identites_numeriques(self):
        from .dialogues_signature import DialogueIdentites
        DialogueIdentites(self, self.params).exec()
        o = self.doc_courant()
        if o is not None and hasattr(o, "verifier_signatures"):
            o.verifier_signatures()

    def mot_de_passe(self, o):
        if o.est_signe() and QMessageBox.question(
                self, _('Protéger par mot de passe'),
                _("Ce document est signé. Le protéger réécrit tout le fichier : les signatures ne seront plus "
                  "valides.\n\nContinuer quand même ?")) != QMessageBox.Yes:
            return
        d = QDialog(self)
        d.setWindowTitle(_('Protéger par mot de passe'))
        f = QFormLayout(d)
        ouv = QLineEdit()
        oeil(ouv)
        prop = QLineEdit()
        oeil(prop)
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
        o.chiffrement_change = True
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
        from .apprentissage import ocr_appris
        from .dialogues_ia import executer_suivi
        from moteur import scan
        appris = ocr_appris(self.params)

        def travail(t):
            def prog(i, n):
                t.avancer(_("Redressement, nettoyage et reconnaissance : page {i} sur {n}...", i=min(i + 1, n), n=n), i, n)
            an = scan.analyser(o.chemin, prog, appris)
            lues = [pg for pg in an["pages"] if not pg["garder"]]
            for pg in an["pages"]:
                t.noter(_("Page {p} : déjà du texte, gardée telle quelle", p=pg["num"] + 1) if pg["garder"] else
                        _("Page {p} : {m} mots, confiance {q} %{x}", p=pg["num"] + 1, m=len(pg["mots"]), q=round(pg["qualite"]),
                          x=_(", {n} correction(s) apprise(s)", n=len(pg["auto"])) if pg["auto"] else ""))
            if not lues:
                return None
            t.avancer(_("Enregistrement..."), len(an["pages"]), len(an["pages"]))
            scan.assembler(an, sortie)
            return sortie
        try:
            chemin = executer_suivi(self, _('Reconnaître le texte'), travail)
        except InterruptedError:
            return
        except Exception as e:
            QMessageBox.warning(self, _('Reconnaître le texte'), _("La reconnaissance a échoué :\n{e}", e=e))
            return
        if not chemin:
            QMessageBox.information(self, _('Reconnaître le texte'),
                                    _("Ce document contient déjà du texte sur toutes ses pages : il n'y a rien à "
                                      "reconnaître. (La reconnaissance sert aux scans et aux photos de documents.)"))
            return
        self.ouvrir(chemin)
        self.statusBar().showMessage(_('Texte reconnu : {nom}', nom=os.path.basename(chemin)), 10000)

    # ------------------------------------------------------------ divers
    def ajuster_largeur(self):
        o = self.doc_courant()
        if o:
            w = o.zone.viewport().width() - 60
            o.changer_zoom(w / (o.doc[0].rect.width * 96 / 72))

    def proprietes(self):
        """Proprietes du document : description (titre, auteur, objet, mots-cles), application et dates, modifiables.
        Ecrites a la fois dans le PDF et dans ses metadonnees XMP : Acrobat affiche bien les nouvelles valeurs."""
        o = self.doc_courant()
        if not o:
            return
        from moteur import metadonnees as M
        from PySide6.QtWidgets import QDateTimeEdit, QPlainTextEdit
        from PySide6.QtCore import QDateTime
        v = M.lire(o.doc)
        d = QDialog(self)
        d.setWindowTitle(_("Propriétés du document"))
        d.setMinimumWidth(620)
        vd = QVBoxLayout(d)
        tabs = QTabWidget()
        vd.addWidget(tabs)
        w1 = QWidget()
        f1 = QFormLayout(w1)
        tabs.addTab(w1, _("Description"))
        ch = {}
        for cle, lib, aide in (("title", _("Titre"), _("Affiché dans la barre de titre d'Acrobat et par les moteurs de recherche")),
                               ("author", _("Auteur"), _("Plusieurs auteurs : séparez-les par « ; »")),
                               ("subject", _("Objet"), ""), ("keywords", _("Mots-clés"), _("Séparés par des virgules"))):
            e = QLineEdit(v.get(cle) or "")
            e.setObjectName("prop_" + cle)
            e.setToolTip(aide)
            e.setPlaceholderText(aide)
            f1.addRow(lib, e)
            ch[cle] = e
        w2 = QWidget()
        f2 = QFormLayout(w2)
        tabs.addTab(w2, _("Application et dates"))
        for cle, lib, aide in (("creator", _("Créé avec"), _("Logiciel d'origine (ex. Word, Acrobat)")),
                               ("producer", _("Producteur PDF"), _("Programme qui a fabriqué le PDF"))):
            e = QLineEdit(v.get(cle) or "")
            e.setPlaceholderText(aide)
            f2.addRow(lib, e)
            ch[cle] = e
        dates = {}
        for cle, lib in (("creation", _("Créé le")), ("modification", _("Modifié le"))):
            de = QDateTimeEdit()
            de.setCalendarPopup(True)
            de.setDisplayFormat("dd/MM/yyyy HH:mm")
            x = v.get(cle)
            de.setDateTime(QDateTime(x.replace(tzinfo=None)) if x else QDateTime.currentDateTime())
            vide = QCheckBox(_("aucune"))
            vide.setChecked(x is None)
            de.setEnabled(x is not None)
            vide.toggled.connect(lambda c, de=de: de.setEnabled(not c))
            h = QHBoxLayout()
            h.addWidget(de, 1)
            h.addWidget(vide)
            f2.addRow(lib, h)
            dates[cle] = (de, vide)
        maj_auto = QCheckBox(_("Mettre la date de modification à maintenant à l'enregistrement"))
        f2.addRow(maj_auto)
        w3 = QWidget()
        f3 = QFormLayout(w3)
        tabs.addTab(w3, _("Fichier"))
        polices = sorted({f[3] for p in o.doc for f in p.get_fonts()})
        taille = os.path.getsize(o.chemin) if o.chemin and os.path.exists(o.chemin) else 0
        for lib, val in ((_("Fichier"), o.chemin or o.nom), (_("Pages"), str(len(o.doc))),
                         (_("Taille"), f"{taille / 1024:.0f} Ko" if taille else "-"),
                         (_("Format"), (o.doc.metadata or {}).get("format") or "PDF"),
                         (_("Archivage PDF/A"), _("oui (conservé)") if v.get("pdfa") else _("non")),
                         (_("Polices"), ", ".join(polices[:20]) or _("aucune (scan)"))):
            lb = QLabel(val)
            lb.setWordWrap(True)
            lb.setTextInteractionFlags(Qt.TextSelectableByMouse)
            f3.addRow(lib, lb)
        info = QLabel(_("Les valeurs sont écrites à la fois dans le PDF et dans ses métadonnées XMP (celles qu'Acrobat "
                        "affiche en priorité) : c'est pourquoi elles changent vraiment, même sur un fichier créé par Adobe."))
        info.setWordWrap(True)
        info.setStyleSheet("color:#555;font-size:12px")
        vd.addWidget(info)
        hb = QHBoxLayout()
        b_eff = QPushButton(icone("supprimer", "#a33"), _(" Tout effacer"))
        b_eff.setToolTip(_("Retire toutes les métadonnées (auteur, logiciel, dates) : utile avant d'envoyer un document"))
        hb.addWidget(b_eff)
        hb.addStretch(1)
        bb = boutons_fr(QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel))
        hb.addWidget(bb)
        vd.addLayout(hb)
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        efface = [False]

        def tout_effacer():
            if QMessageBox.question(d, _("Propriétés"), _("Effacer toutes les métadonnées de ce document ?")) == QMessageBox.Yes:
                efface[0] = True
                d.accept()
        b_eff.clicked.connect(tout_effacer)
        self._dlg_proprietes = d                         # pour les tests
        if d.exec() != QDialog.Accepted:
            return
        o.memoriser(_("Propriétés du document"))
        if efface[0]:
            M.effacer(o.doc)
        else:
            nv = {k: e.text().strip() for k, e in ch.items()}
            import datetime as _dt
            for cle, (de, vide) in dates.items():
                nv[cle] = None if vide.isChecked() else de.dateTime().toPython().astimezone()
            if maj_auto.isChecked():
                nv["modification"] = _dt.datetime.now().astimezone()
            M.ecrire(o.doc, nv)
        o.modifie = True
        o.titre_change.emit()
        o.maj_info()
        self.statusBar().showMessage(_("Propriétés modifiées : enregistrez le document pour les garder."), 8000)

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
        be_ = QPushButton(_("Envoyer ces réglages à mes autres postes"))
        be_.setToolTip(_("Les favoris, outils, barres, comptes et réglages communs de ce poste deviennent la référence : "
                         "vos autres postes les reprennent à leur prochain démarrage."))

        def envoyer_reglages():
            import datetime
            self.params["communs_maj"] = datetime.datetime.now().isoformat(timespec="seconds")
            self.params.enregistrer()
            ok = reglages.ecrire_drive(self.params)
            self.synchro_miroir()
            QMessageBox.information(d, _("Préférences"), _("Réglages envoyés : vos autres postes vous proposeront de les reprendre à leur prochain démarrage.")
                                    if ok else _("Aucun emplacement de synchronisation : choisissez-en un dans « Drive et dossiers »."))
        be_.clicked.connect(envoyer_reglages)
        hp.addWidget(be_)
        bv_ = QPushButton(_("Mes autres postes..."))
        bv_.setToolTip(_("La liste de vos postes (dernière activité, synchronisation, fichiers ouverts) et leurs réglages"))
        bv_.clicked.connect(lambda: self.mes_postes(d))
        hp.addWidget(bv_)
        hp.addStretch()
        f.addRow(_("Sauvegarde"), hp)
        note(f, _("Vos préférences sont aussi copiées automatiquement sur votre Drive : une nouvelle installation "
                  "propose de les reprendre."))
        hs_ = QHBoxLayout()
        sync_sec = QCheckBox(_("Synchroniser aussi les mots de passe, autorisations des Drives et clefs IA (chiffrés)"))
        sync_sec.setChecked(bool(self.params.get("synchro_secrets")) and bool(coffre.lire(reglages.PHRASE)))
        hs_.addWidget(sync_sec, 1)
        b_phrase = QPushButton(_("Mot de passe principal..."))
        hs_.addWidget(b_phrase)
        f.addRow(hs_)

        def activer_secrets(on):
            if on and not coffre.lire(reglages.PHRASE):
                if not self.choisir_phrase(d):
                    sync_sec.blockSignals(True)
                    sync_sec.setChecked(False)
                    sync_sec.blockSignals(False)
        sync_sec.toggled.connect(activer_secrets)
        b_phrase.clicked.connect(lambda: self.choisir_phrase(d) and sync_sec.setChecked(True))
        note(f, _("Chiffrés en AES-256 par un mot de passe principal que vous choisissez (le même sur tous vos postes) : "
                  "sans lui, le fichier est illisible, même pour le Drive. Chaque poste le demande une seule fois ; "
                  "un indice, que vous écrivez, vous aide à vous en souvenir."))
        note(f, _("Le changement de langue s'applique au prochain démarrage de PhilPDF. Pour ajouter une langue : "
                  "copier langues/en.json, le traduire et le renommer (es.json, de.json...)."))
        assoc = QCheckBox(_('Ouvrir les fichiers PDF avec PhilPDF (proposé dans « Ouvrir avec »)'))
        assoc.setChecked(self.params["association_pdf"])
        assoc.setEnabled(sys.platform == "win32")
        if est_portable():
            assoc.setToolTip(_("Version portable : c'est l'emplacement actuel de PhilPDF qui est enregistré. "
                               "Si vous déplacez le dossier, décochez puis recochez."))
        f.addRow(assoc)
        if sys.platform == "win32":
            note(f, _("Windows choisit ensuite le programme par défaut : clic droit sur un PDF › Ouvrir avec › "
                      "Choisir une autre application › PhilPDF › Toujours.") +
                 (_(" (Version portable : si vous déplacez le dossier de PhilPDF, décochez puis recochez.)") if est_portable() else ""))

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
        tabs.currentChanged.connect(lambda _i: drive.rafraichir())   # comptes ajoutes : aussitot proposes pour la synchro
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
            pb.setMinimumHeight(max(215, pb.minimumHeight()))
            vt.addWidget(pb, 1)
            panneaux.append(pb)
        hb = QHBoxLayout()
        bsync = QPushButton(_(' Synchroniser avec le Drive maintenant'))
        bsync.setIcon(icone("synchro", "#0f6cbd"))
        bsync.clicked.connect(lambda: self.synchro_manuelle(parent=w.window(), apres=lambda: [x.rafraichir() for x in panneaux])
                              if miroir.compte_drive(self.params) else (panneaux[0].synchroniser(), panneaux[1].rafraichir()))
        hb.addWidget(bsync)
        ls = QLabel(_("Chaque ajout, renommage, catégorie ou suppression part tout seul sur le Drive dans la minute ; "
                      "vos autres postes vous le proposent à leur démarrage (fenêtre à cocher)."))
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
        vt.addSpacing(8)
        lt = QLabel("<b>" + _("Formulaires") + "</b>")
        vt.addWidget(lt)
        hd = QHBoxLayout()
        hd.addWidget(QLabel(_("En passant en mode Formulaire, repérer les zones à remplir :")))
        detection = QComboBox()
        detection.setObjectName("pref_formulaire_detection")
        for k_, t_ in (("auto", _("tout seul (si le document n'a pas encore de champs)")), ("demander", _("me demander")),
                       ("jamais", _("jamais (bouton « Détecter les champs »)"))):
            detection.addItem(t_, k_)
        detection.setCurrentIndex(max(0, detection.findData(self.params.get("formulaire_detection", "auto"))))
        hd.addWidget(detection, 1)
        vt.addLayout(hd)
        types_auto = QCheckBox(_("Donner tout seul un type aux champs d'après leur libellé (date, montant, téléphone, "
                                 "code postal, e-mail, n° de Sécurité sociale, signature...)"))
        types_auto.setChecked(self.params.get("formulaire_types_auto", True))
        vt.addWidget(types_auto)

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
        moteur.addItems(["Claude", "Gemini", _("Claude, puis Gemini s'il ne répond pas")])
        moteur.setCurrentIndex({"claude": 0, "gemini": 1, "deux": 2}.get(self.params["ia_moteur"], 0))
        kc = QLineEdit(self.params["clef_claude"])
        oeil(kc)
        kg = QLineEdit(self.params["clef_gemini"])
        oeil(kg)
        f.addRow(_('Moteur IA'), moteur)
        f.addRow(_('Clef API Claude'), kc)
        f.addRow(_('Clef API Gemini'), kg)
        bt = QPushButton(_("Tester les clefs"))

        def tester_ia():
            from . import ia
            from .dialogues_ia import executer_suivi
            essai = dict(clef_claude=kc.text().strip(), clef_gemini=kg.text().strip())

            def tester(t):
                lignes = []
                moteurs_ = [(m, nom) for m, nom in (("claude", "Claude"), ("gemini", "Gemini"))]
                try:
                    for k, (m, nom) in enumerate(moteurs_):
                        clef = ia.nettoyer_clef(essai["clef_" + m])
                        if not clef:
                            lignes.append(_("{nom} : pas de clef.", nom=nom))
                            t.noter(lignes[-1])
                            continue
                        ia.DELAI = 30
                        t.avancer(_("Test de {nom} (30 s au plus par modèle)...", nom=nom), k, len(moteurs_))
                        import time as _t
                        debut = _t.time()
                        p = {"ia_moteur": m, "clef_" + m: clef}
                        try:
                            ia.demander(p, "Réponds seulement : OK", "Test", max_jetons=50)
                            lignes.append(_("{nom} : clef valide (modèle {modele}, réponse en {s} s)", nom=nom, s=round(_t.time() - debut, 1),
                                            modele=ia._modeles_trouves.get(m) or (ia.MODELE_CLAUDE if m == "claude" else ia.MODELE_GEMINI)))
                        except Exception as ex:
                            lignes.append(_("{nom} : {erreur}", nom=nom, erreur=ex))
                        t.noter(lignes[-1])
                finally:
                    ia.DELAI = 180
                return lignes
            try:
                lignes = executer_suivi(d, _("Test des clefs IA"), tester)
            except InterruptedError:
                return
            QMessageBox.information(d, _("IA"), "\n\n".join(lignes))
        bt.clicked.connect(tester_ia)
        f.addRow("", bt)
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
                           formulaire_detection=detection.currentData(), formulaire_types_auto=types_auto.isChecked(),
                           nas=nas.text().strip(), synchro=sync.isChecked(), langue=langue.currentData(),
                           racines=[racines.item(i).text() for i in range(racines.count())],
                           ia_moteur=["claude", "gemini", "deux"][moteur.currentIndex()],
                           clef_claude=kc.text().strip(), clef_gemini=kg.text().strip(),
                           maj_source=["github", "dossier"][majs.currentIndex()], maj_auto=maja.isChecked(),
                           synchro_secrets=sync_sec.isChecked())
        if assoc.isChecked() != self.params["association_pdf"]:
            if associer_pdf(assoc.isChecked()):
                self.params["association_pdf"] = assoc.isChecked()
        self.params.enregistrer()
        reglages.ecrire_drive(self.params)
        self._ecrire_secrets()
        self._session()
        self.accueil.rafraichir()
        if miroir.compte_drive(self.params):
            self.synchro_miroir(au_demarrage=True)
        if self.params.get("langue", "auto") != ancienne_langue:
            if question(self, _("Langue"), _("La nouvelle langue s'applique au redémarrage. Redémarrer PhilPDF maintenant ?"),
                        [(_("Redémarrer"), QMessageBox.AcceptRole), (_("Plus tard"), QMessageBox.RejectRole)]) == 0:
                self.redemarrer()

    # ------------------------------------------------------------ sauvegarde des preferences
    # ------------------------------------------------------------ mots de passe synchronises (chiffres)
    def _ecrire_secrets(self):
        try:
            if reglages.ecrire_secrets_drive(self.params):
                self.synchro_miroir()
        except Exception as ex:
            self.statusBar().showMessage(_("Mots de passe non synchronisés : {e}", e=ex), 8000)

    def choisir_phrase(self, parent=None):
        """Demande la phrase secrete de synchronisation (verifiee sur le Drive si un autre poste l'a deja choisie)."""
        parent = parent or self
        existe = bool(reglages.chemin_secrets(self.params) and os.path.exists(reglages.chemin_secrets(self.params)))
        while True:
            if existe:
                ph, ok, nouvel_indice = demander_secret(parent, _("Mot de passe principal"), _(
                    "Un autre de vos postes synchronise déjà ses mots de passe.\nEntrez le même mot de passe principal :"),
                    reglages.lire_indice(self.params), avec_indice=True)
                if not ok:
                    return False
                try:
                    n = reglages.reprendre_secrets_drive(self.params, ph)
                except reglages.PhraseRequise:
                    QMessageBox.warning(parent, _("Mot de passe principal"), _("Mot de passe principal incorrect."))
                    continue
                coffre.enregistrer(reglages.PHRASE, ph)
                self.params["synchro_secrets"] = True
                self.params.enregistrer()
                if nouvel_indice:                     # la phrase est la bonne : l'indice part vers vos autres postes
                    reglages.ecrire_indice(self.params, nouvel_indice)
                    self.synchro_miroir()
                QMessageBox.information(parent, _("Mot de passe principal"), _(
                    "{n} mot(s) de passe, autorisation(s) ou clef(s) repris de vos autres postes.", n=n))
                return True
            d = QDialog(parent)
            d.setWindowTitle(_("Mot de passe principal"))
            fl = QFormLayout(d)
            lb = QLabel(_("Choisissez votre mot de passe principal (8 caractères au moins) : il protège tous les mots de passe que "
                          "PhilPDF synchronise. Notez-le : il faudra le même sur vos autres postes, et personne ne peut le "
                          "retrouver pour vous."))
            lb.setWordWrap(True)
            fl.addRow(lb)
            p1, p2 = QLineEdit(), QLineEdit()
            for p in (p1, p2):
                oeil(p)
            fl.addRow(_("Mot de passe principal"), p1)
            fl.addRow(_("Confirmer le mot de passe"), p2)
            ind = QLineEdit()
            ind.setPlaceholderText(_("ex. « le code du carnet bleu », « titre de chanson + année » (jamais le mot de passe lui-même)"))
            fl.addRow(_("Indice pour vous en souvenir"), ind)
            ni = QLabel(_("L'indice est enregistré en clair à côté du fichier chiffré : il vous aide à vous souvenir, "
                          "il ne doit pas permettre de deviner le mot de passe."))
            ni.setWordWrap(True)
            ni.setStyleSheet("color:#666;font-size:11px")
            fl.addRow(ni)
            bb = boutons_fr(QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel))
            bb.accepted.connect(d.accept)
            bb.rejected.connect(d.reject)
            fl.addRow(bb)
            if d.exec() != QDialog.Accepted:
                return False
            if len(p1.text()) < 8 or p1.text() != p2.text():
                QMessageBox.warning(parent, _("Mot de passe principal"), _("Mot de passe trop court (8 caractères au moins) ou différent de sa confirmation."))
                continue
            if ind.text().strip() and p1.text().lower() in ind.text().lower():
                QMessageBox.warning(parent, _("Mot de passe principal"), _("L'indice ne doit pas contenir le mot de passe lui-même."))
                continue
            coffre.enregistrer(reglages.PHRASE, p1.text())
            self.params["synchro_secrets"] = True
            self.params.enregistrer()
            reglages.ecrire_indice(self.params, ind.text().strip())
            self._ecrire_secrets()
            return True

    def communs_au_demarrage(self, manuel=False, ouvrir=False):
        """Rien n'est repris en silence : si un autre poste a change des reglages (ou ajoute des mots de passe),
        une bulle le signale et une fenetre montre chaque changement, a cocher ou non."""
        try:
            ch = reglages.changements_communs(self.params)
        except Exception:
            ch = None
        try:
            dispo = reglages.disposition_autre(self.params)
        except Exception:
            dispo = None
        self._dispo = dispo
        sec = []
        phrase = coffre.lire(reglages.PHRASE)
        if phrase:
            try:
                sec = reglages.secrets_nouveaux(self.params, phrase)
            except Exception:
                sec = []
        if ch and not ch["items"] and not sec:       # meme contenu : on note juste la date
            reglages.appliquer_communs(self.params, ch, [])
            ch = None
        if not ch and not sec and not dispo:
            if manuel:
                QMessageBox.information(self, _("Réglages de vos autres postes"), _("Rien de nouveau : ce poste est à jour."))
            return
        n = len(ch["items"] if ch else []) + len(sec) + len(dispo["items"] if dispo else [])
        if manuel or ouvrir:
            self.choisir_reglages_distants(ch, sec)
            return
        Notification(self, _("{n} réglage(s) modifié(s) sur vos autres postes{par}.", n=n,
                             par=_(" (dernier : « {poste} »)", poste=ch["par"]) if ch else ""),
                     _("Voir et choisir..."), lambda: self.choisir_reglages_distants(ch, sec))

    def mes_postes(self, parent=None):
        """Liste de vos postes : derniere activite, derniere synchronisation, fichiers ouverts et recents ;
        puis comparer les reglages, ou oublier un ancien poste."""
        from PySide6.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView
        p = reglages.chemin_drive(self.params)
        postes = (reglages.lire_drive(p).get("postes") if p else None) or {}
        sess = session_de(self.params).lire()
        moi = self.params.get("machine", "")
        noms = sorted(set(postes) | {m for m in sess if isinstance(sess[m], dict)} | {moi},
                      key=lambda m: (m != moi, m.lower()))
        d = QDialog(parent or self)
        d.setWindowTitle(_("Mes postes"))
        d.resize(860, 380)
        v = QVBoxLayout(d)
        lb = QLabel(_("Les postes qui partagent le même emplacement de synchronisation ({lieu}).", lieu=self._lieu_court()))
        lb.setWordWrap(True)
        v.addWidget(lb)
        t = QTableWidget(len(noms), 5)
        t.setHorizontalHeaderLabels([_("Poste"), _("Dernière activité"), _("Dernière synchronisation"),
                                     _("Fichiers ouverts"), _("Récents")])
        t.verticalHeader().hide()
        t.setEditTriggers(QTableWidget.NoEditTriggers)
        t.setSelectionBehavior(QTableWidget.SelectRows)
        for r, m in enumerate(noms):
            pv, sv = postes.get(m) or {}, sess.get(m) if isinstance(sess.get(m), dict) else {}
            se = pv.get("synchro_etat") or (self.params.get("synchro_etat") if m == moi else {}) or {}
            synchro = (("✓ " if se.get("ok") else "✕ ") + date_fr(se["quand"])) if se.get("quand") else "—"
            act = max(pv.get("maj") or "", sv.get("maj") or "")
            for c, val in enumerate((m + (_("  (ce poste)") if m == moi else ""), date_fr(act) if act else "—", synchro,
                                     str(len(sv.get("fichiers", []))), str(len(sv.get("recents", []))))):
                it = QTableWidgetItem(val)
                if m == moi:
                    f_ = it.font()
                    f_.setBold(True)
                    it.setFont(f_)
                t.setItem(r, c, it)
        h = t.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.Stretch)
        for c in range(1, 5):
            h.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        v.addWidget(t, 1)
        hb = QHBoxLayout()
        b_cmp = QPushButton(_("Comparer les réglages avec ce poste..."))
        b_cmp.clicked.connect(lambda: self.communs_au_demarrage(manuel=True))
        hb.addWidget(b_cmp)
        b_oub = QPushButton(_("Oublier le poste choisi"))
        b_oub.setToolTip(_("Pour un ancien PC : il disparaît de la liste, de la session et des réglages partagés"))

        def oublier():
            r = t.currentRow()
            if r < 0 or noms[r] == moi:
                return
            m = noms[r]
            if QMessageBox.question(d, _("Mes postes"), _("Oublier le poste « {m} » ?", m=m)) != QMessageBox.Yes:
                return
            if p:
                dd = reglages.lire_drive(p)
                (dd.get("postes") or {}).pop(m, None)
                with open(p, "w", encoding="utf-8") as fh:
                    json.dump(dd, fh, ensure_ascii=False, indent=1)
            s_ = session_de(self.params)
            ds = s_.lire()
            if ds.pop(m, None) is not None:
                with open(s_.chemin, "w", encoding="utf-8") as fh:
                    json.dump(ds, fh, ensure_ascii=False, indent=1)
            t.removeRow(r)
            noms.pop(r)
            self.synchro_miroir()
            self.accueil.rafraichir()
        b_oub.clicked.connect(oublier)
        hb.addWidget(b_oub)
        hb.addStretch(1)
        bf = QPushButton(_("Fermer"))
        bf.clicked.connect(d.accept)
        hb.addWidget(bf)
        v.addLayout(hb)
        self._dlg_postes = d                         # pour les tests
        d.exec()

    def choisir_reglages_distants(self, ch, sec):
        def _date_heure(iso):
            j, _t, h = iso.partition("T")
            a_, m_, d_ = (j.split("-") + ["", "", ""])[:3]
            return f"{d_}/{m_}/{a_}" + (_(" à {h}", h=h[:5]) if h else "")
        from PySide6.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView
        d = QDialog(self)
        d.setWindowTitle(_("Réglages de vos autres postes"))
        d.resize(900, 480)
        v = QVBoxLayout(d)
        lb = QLabel(_("Voici ce qui a changé ailleurs. Cochez à droite ce que vous voulez reprendre sur ce poste ; "
                      "ce qui reste décoché garde la valeur de ce poste.") +
                    (_("<br>Réglages de « {poste} » : {date}. Réglages de ce poste ({ici}) : {date_ici}. "
                       "Les cases du plus récent sont cochées d'avance.", poste=ch["par"], date=_date_heure(ch["maj"]),
                       ici=self.params.get("machine", ""),
                       date_ici=_date_heure(ch["local"]) if ch.get("local") else _("jamais modifiés"))
                     + ("<br><b>" + _("« {poste} » est le plus récent.", poste=ch["par"]) + "</b>" if ch.get("plus_recent_ailleurs") else
                        "<br><b>" + _("Ce poste est le plus récent : rien n'est coché, ses réglages seront gardés et envoyés.") + "</b>")
                     if ch else ""))
        lb.setWordWrap(True)
        v.addWidget(lb)
        lignes = [("c", it["cle"], it["libelle"], it["detail"], it.get("coche", True)) for it in (ch["items"] if ch else [])] + \
                 [("s", it["cle"], it["libelle"], _("nouveau, absent de ce poste (valeur chiffrée, non affichée)"), True) for it in sec] + \
                 [("p", it["cle"], it["libelle"] + _(" (disposition de « {poste} »)", poste=self._dispo["poste"]), it["detail"], False)
                  for it in ((getattr(self, "_dispo", None) or {}).get("items") or [])]
        t = QTableWidget(len(lignes), 3)
        t.setHorizontalHeaderLabels([_("Réglage"), _("Ce qui va changer sur ce poste"), _("Reprendre")])
        t.verticalHeader().hide()
        t.setEditTriggers(QTableWidget.NoEditTriggers)
        t.setWordWrap(True)
        for r, (genre, cle, lib, detail, coche) in enumerate(lignes):
            t.setItem(r, 0, QTableWidgetItem(lib))
            it = QTableWidgetItem(detail)
            it.setToolTip(detail)
            t.setItem(r, 1, it)
            c = QTableWidgetItem()
            c.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            c.setCheckState(Qt.Checked if coche else Qt.Unchecked)
            c.setData(Qt.UserRole, (genre, cle))
            t.setItem(r, 2, c)
        h = t.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.Stretch)
        h.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        t.resizeRowsToContents()
        v.addWidget(t, 1)
        hb = QHBoxLayout()
        for txt, etat in ((_("Tout cocher"), Qt.Checked), (_("Tout décocher"), Qt.Unchecked)):
            b = QPushButton(txt)
            b.clicked.connect(lambda _c=False, e=etat: [t.item(r, 2).setCheckState(e) for r in range(t.rowCount())])
            hb.addWidget(b)
        hb.addStretch(1)
        b_ok = QPushButton(_("Appliquer la sélection"))
        b_ok.setDefault(True)
        b_tard = QPushButton(_("Plus tard"))
        b_tard.setToolTip(_("Rien n'est changé ; la question reviendra au prochain démarrage."))
        hb.addWidget(b_tard)
        hb.addWidget(b_ok)
        v.addLayout(hb)
        b_ok.clicked.connect(d.accept)
        b_tard.clicked.connect(d.reject)
        self._dlg_reglages = d                        # pour les tests
        if d.exec() != QDialog.Accepted:
            return
        choisis = [t.item(r, 2).data(Qt.UserRole) for r in range(t.rowCount()) if t.item(r, 2).checkState() == Qt.Checked]
        communs = [k for g, k in choisis if g == "c"]
        if getattr(self, "_dispo", None):              # disposition : reprise ou non, elle n'est plus proposee
            reglages.appliquer_disposition(self.params, self._dispo, [k for g, k in choisis if g == "p"])
            for o in self.documents():
                if self.params.get("volet_largeur"):
                    o._taille_volet = int(self.params["volet_largeur"])
                    if getattr(o, "_mode_volet", "complet") == "complet":
                        o.mode_volet("complet", memoriser=False)
        secrets = [k for g, k in choisis if g == "s"]
        langue_avant = self.params.get("langue")
        if ch:
            reglages.appliquer_communs(self.params, ch, communs)
            if reglages.ecrire_drive(self.params):    # ce poste a garde certaines valeurs : elles deviennent la reference
                self.synchro_miroir()
        n_sec = reglages.reprendre_secrets_choisis(self.params, coffre.lire(reglages.PHRASE), secrets) if secrets else 0
        for o in self.documents():
            o.remplir_volet()
            o.construire_barre()
        self.outils.rafraichir() if hasattr(self.outils, "rafraichir") else None
        self.accueil.rafraichir()
        msg = _("{n} réglage(s) et {s} mot(s) de passe repris.", n=len(communs), s=n_sec)
        if self.params.get("langue") != langue_avant:
            Notification(self, msg + " " + _("La langue change au redémarrage."), _("Redémarrer"), self.redemarrer)
        else:
            self.statusBar().showMessage(msg, 8000)

    def secrets_au_demarrage(self):
        """Sans phrase sur ce poste : une bulle propose de reprendre les mots de passe des autres postes.
        Avec la phrase, ils sont proposes dans la fenetre des reglages (communs_au_demarrage)."""
        p = reglages.chemin_secrets(self.params)
        if not p or not os.path.exists(p) or coffre.lire(reglages.PHRASE):
            return
        Notification(self, _("Les mots de passe de vos autres postes (NAS, FTP, Drives, IA) sont disponibles, chiffrés."),
                     _("Les reprendre..."), lambda: self.choisir_phrase())

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
            oeil(p)
            p.setEnabled(False)
        sec.toggled.connect(lambda on: (p1.setEnabled(on), p2.setEnabled(on)))
        f.addRow(_("Mot de passe du fichier"), p1)
        f.addRow(_("Confirmer le mot de passe"), p2)
        n2 = QLabel(_("Avec les mots de passe, le fichier est chiffré (AES-256) par ce mot de passe : sans lui, il est illisible."))
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
                QMessageBox.warning(d, d.windowTitle(), _("Mot de passe trop court (6 caractères au moins) ou différent "
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
                    phrase, ok = demander_secret(self, _("Importer des préférences"), _("Ce fichier est chiffré. Mot de passe du fichier :"))
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
        cs = QCheckBox(_("Mots de passe, autorisations et clefs contenus dans le fichier") if donnees.get("secrets") else
                       _("Ce fichier ne contient pas les mots de passe (à l'export, cochez « Inclure les mots de passe »)"))
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
        from moteur.scan import versions_moteurs
        v = versions_moteurs()
        moteurs = "<br>".join(f"{k} : <b>{x}</b>" for k, x in v.items())
        QMessageBox.about(self, _('A propos de PhilPDF'),
                          _("<b>PhilPDF {version}</b> – Editeur PDF<br>Usage personnel et familial.<br><br>"
                            "Moteur PDF : PyMuPDF (AGPL). Interface : Qt / PySide6 (LGPL). OCR : Tesseract (Apache 2.0).<br>"
                            "Police de remplacement fournie : Nunito (SIL Open Font License).", version=VERSION)
                          + "<br><br>" + _("<b>Moteurs embarqués</b> (mis à jour automatiquement à chaque nouvelle version) :")
                          + "<br>" + moteurs)
