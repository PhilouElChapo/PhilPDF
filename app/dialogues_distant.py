"""Fenetres des emplacements distants : compte (NAS, FTP, WebDAV...), choix d'un fichier ou d'un dossier."""
import os, posixpath, urllib.parse
from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit, QPushButton, QComboBox,
                               QCheckBox, QSpinBox, QDialogButtonBox, QListWidget, QListWidgetItem, QMessageBox,
                               QInputDialog, QApplication, QWidget, QMenu, QToolButton)
from .langue import _
from .icones import icone
from . import distant, coffre

ICONES = {"reseau": "ouvrir", "synology": "archiver", "webdav": "lot", "ftp": "exporter", "gdrive": "synchro",
          "onedrive": "synchro", "dropbox": "synchro", "box": "synchro"}
AIDE = {
    "reseau": _("Un dossier partagé déjà accessible depuis ce PC : \\\\NAS\\partage, une lettre de lecteur (Z:\\) ou /mnt/nas."),
    "synology": _("L'adresse de votre Synology dans le navigateur : http://nas:5000, https://nas:5001 ou une adresse "
                "personnelle (monnas.exemple.org). Si la vérification en deux étapes est active, le code sera demandé "
                "une seule fois."),
    "webdav": _("Adresse WebDAV complète, par exemple https://nas:5006 (paquet « WebDAV Server » du Synology) ou "
              "https://cloud.exemple.fr/remote.php/dav/files/nom/."),
    "ftp": _("Nom ou adresse du serveur (ftp.exemple.fr, 192.168.1.20). Chiffrement conseillé ; « aucun » = FTP en clair."),
    "gdrive": _("Google Drive en direct, sans l'application de bureau : votre navigateur s'ouvre, vous autorisez PhilPDF, "
                "c'est tout. PhilPDF ne voit que les fichiers qu'il crée ou que vous ouvrez avec lui."),
    "onedrive": _("OneDrive en direct, sans l'application de bureau : votre navigateur s'ouvre, vous autorisez PhilPDF, "
                  "c'est tout."),
    "dropbox": _("Dropbox en direct : votre navigateur s'ouvre, vous autorisez PhilPDF, c'est tout."),
    "box": _("Box en direct : votre navigateur s'ouvre, vous autorisez PhilPDF, c'est tout."),
}


def erreur(parent, titre, ex, e=None, info=False):
    """Message (erreur ou reussite) avec l'echange complet avec le serveur, a deplier et a copier."""
    from PySide6.QtWidgets import QPlainTextEdit, QStyle
    from PySide6.QtGui import QFont
    d = QDialog(parent)
    d.setWindowTitle(titre)
    v = QVBoxLayout(d)
    h = QHBoxLayout()
    ic = QLabel()
    ic.setPixmap(d.style().standardIcon(QStyle.SP_MessageBoxInformation if info else QStyle.SP_MessageBoxWarning).pixmap(36, 36))
    ic.setAlignment(Qt.AlignTop)
    h.addWidget(ic)
    t = QLabel(str(ex))
    t.setWordWrap(True)
    t.setMinimumWidth(460)
    t.setTextInteractionFlags(Qt.TextSelectableByMouse)
    h.addWidget(t, 1)
    v.addLayout(h)
    journal = QPlainTextEdit(e.texte_journal() if e is not None else "")
    journal.setReadOnly(True)
    journal.setFont(QFont("Consolas" if os.name == "nt" else "DejaVu Sans Mono", 9))
    journal.setLineWrapMode(QPlainTextEdit.NoWrap)
    journal.setMinimumSize(720, 260)
    journal.hide()
    v.addWidget(journal, 1)
    bb = QDialogButtonBox()
    if e is not None:
        bd = bb.addButton(_("Détails de l'échange"), QDialogButtonBox.ActionRole)
        bd.setCheckable(True)
        bd.toggled.connect(lambda on: (journal.setVisible(on), d.adjustSize()))
        bc = bb.addButton(_("Copier"), QDialogButtonBox.ActionRole)
        bc.setToolTip(_("Copier l'échange (mots de passe masqués), par exemple pour me l'envoyer"))
        bc.clicked.connect(lambda: QApplication.clipboard().setText(str(ex) + "\n\n" + e.texte_journal()))
    ok = bb.addButton("OK", QDialogButtonBox.AcceptRole)
    ok.setDefault(True)
    bb.accepted.connect(d.accept)
    v.addWidget(bb)
    d.exec()


def ouvrir_emplacement(parent, compte):
    """Connexion avec demande du code de verification si le NAS l'exige. None si abandon."""
    e = distant.emplacement(compte)
    for _essai in range(2):
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                e.lister(e.racine())
            finally:
                QApplication.restoreOverrideCursor()
            return e
        except distant.BesoinCode:
            code, ok = QInputDialog.getText(parent, distant.libelle(compte),
                                            _("Code de vérification (application d'authentification) :"))
            if not ok or not code.strip():
                return None
            e = distant.emplacement(compte, code=code.strip())
        except distant.ErreurDistant as ex:
            erreur(parent, distant.libelle(compte), ex, e)
            return None
    return None


# ------------------------------------------------------------------------------------------- autorisation OAuth
from PySide6.QtCore import QThread, Signal


class TacheAutorisation(QThread):
    fini = Signal(object, str)          # jetons, erreur
    ligne = Signal(str)                 # etape de l'echange, affichee en direct

    def __init__(self, fournisseur):
        super().__init__()
        self.f, self.stop, self.journal = fournisseur, False, []

    def _noter(self, t):
        self.journal.append(t)
        self.ligne.emit(distant.masquer(t))

    def run(self):
        from . import oauth
        import webbrowser
        try:
            j = oauth.autoriser(self.f, ouvrir=webbrowser.open, arret=lambda: self.stop, journal=self._noter)
            self.fini.emit(j, "")
        except Exception as e:
            self.fini.emit(None, str(e))


def autoriser_compte(parent, compte):
    """Ouvre le navigateur pour l'autorisation ; jeton durable range dans le coffre. True si accorde.
    La fenetre d'attente montre chaque etape (navigateur, retour, echange du jeton)."""
    from . import oauth
    from PySide6.QtCore import QEventLoop
    from .dialogues_ia import Avancement
    nom = distant.TYPES[compte["type"]]
    if not oauth.disponible(compte["type"]):
        QMessageBox.information(parent, nom, _("Cette version de PhilPDF n'a pas l'identifiant d'application pour {nom}.", nom=nom))
        return False
    t = TacheAutorisation(compte["type"])
    dlg = Avancement(parent, _("Autorisation"))
    dlg.etape(_("Votre navigateur s'ouvre sur la page de {nom}.\nConnectez-vous si besoin, puis cliquez sur "
                "« Autoriser » (ou « Continuer »). Revenez ensuite ici.", nom=nom), 0, 0)
    dlg.b_stop.setText(_("Annuler"))
    res = {}
    boucle = QEventLoop()
    t.ligne.connect(dlg.noter)
    t.fini.connect(lambda j, err: (res.update(j=j, err=err), boucle.quit()))
    annule = []

    def annuler():                                 # seulement un vrai clic de l'utilisateur, pendant l'attente
        if not res:
            annule.append(1)
            t.stop = True
    dlg.b_stop.clicked.connect(annuler)
    dlg.rejected.connect(annuler)
    t.start()
    dlg.show()
    boucle.exec()
    t.wait(3000)
    dlg.blockSignals(True)
    dlg.close()
    if res.get("j"):
        coffre.enregistrer(compte["id"] + ".jeton", res["j"]["refresh_token"])
        if coffre.lire(compte["id"] + ".jeton") != res["j"]["refresh_token"]:
            QMessageBox.warning(parent, _("Autorisation"), _(
                "L'autorisation a été accordée, mais le coffre des mots de passe de ce poste a refusé de la garder. "
                "Réessayez ; si cela recommence, envoyez-moi ce message."))
            return False
        # verification immediate : on se connecte vraiment et on dit a qui
        try:
            qui = distant.emplacement(compte).qui()
            if qui and compte.get("nom", "") in ("", distant.TYPES[compte["type"]], _(distant.TYPES[compte["type"]])):
                compte["nom"] = f"{distant.TYPES[compte['type']]} ({qui})"
            QMessageBox.information(parent, _("Autorisation"), _("Connexion réussie : PhilPDF accède au {nom} de {qui}.",
                                                                 nom=distant.TYPES[compte["type"]], qui=qui or "?"))
        except Exception as ex:
            erreur(parent, _("Autorisation"), _("L'autorisation est enregistrée, mais la connexion de test a échoué : {e}", e=ex),
                   getattr(ex, "emplacement", None))
        return True
    if annule and not res.get("j"):
        QMessageBox.information(parent, _("Autorisation"), _("Autorisation annulée : rien n'a été enregistré."))
        return False
    if not res.get("j"):
        class _J:
            def texte_journal(self_):
                return "\n".join(distant.masquer(l) for l in t.journal) or _("Aucun échange enregistré.")
        erreur(parent, _("Autorisation"), _("Autorisation non obtenue : {raison}", raison=res.get("err", "?")), _J())
    return False


# ------------------------------------------------------------------------------------------- compte
PORTS = {"synology": _("par défaut : 5000 en http, 5001 en https"), "webdav": _("Synology : 5005 en http, 5006 en https"),
         "ftp": _("par défaut : 21")}
EXEMPLES = {"reseau": r"\\NAS\partage", "synology": "http://monnas.exemple.org:5000", "webdav": "https://monnas.exemple.org:5006",
            "ftp": "ftp.exemple.org"}


class DialogueCompte(QDialog):
    def __init__(self, parent, compte):
        super().__init__(parent)
        self.c = dict(compte)
        self.setWindowTitle(_("Compte"))
        self.setMinimumWidth(560)
        f = self.f = QFormLayout(self)
        self.type = QComboBox()
        for t, lib in distant.TYPES.items():
            self.type.addItem(icone(ICONES[t], "#0f6cbd"), lib, t)
        self.type.setCurrentIndex(max(0, self.type.findData(self.c["type"])))
        f.addRow(_("Type"), self.type)
        self.aide = QLabel()
        self.aide.setWordWrap(True)
        self.aide.setStyleSheet("color:#555")
        f.addRow(self.aide)
        self.nom = QLineEdit(self.c.get("nom", ""))
        f.addRow(_("Nom affiché"), self.nom)
        # adresse (+ bouton Choisir pour un dossier reseau)
        self.adresse = QLineEdit(self.c.get("adresse", ""))
        self.b_choisir = QPushButton(_("Choisir..."))
        from PySide6.QtWidgets import QFileDialog
        self.b_choisir.clicked.connect(lambda: (lambda p: p and self.adresse.setText(p))(
            QFileDialog.getExistingDirectory(self, _("Dossier réseau"))))
        ha = QWidget()
        h = QHBoxLayout(ha)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(self.adresse, 1)
        h.addWidget(self.b_choisir)
        f.addRow(_("Adresse"), ha)
        self.port = QSpinBox()
        self.port.setRange(0, 65535)
        self.port.setSpecialValueText(_("par défaut"))
        self.port.setValue(int(self.c.get("port") or 0))
        f.addRow(_("Port"), self.port)
        self.utilisateur = QLineEdit(self.c.get("utilisateur", ""))
        f.addRow(_("Utilisateur"), self.utilisateur)
        self.mdp = QLineEdit(coffre.lire(self.c["id"]) or "")
        self.mdp.setEchoMode(QLineEdit.Password)
        self.oeil = self.mdp.addAction(icone("oeil", "#555555"), QLineEdit.TrailingPosition)
        self.oeil.setToolTip(_("Afficher le mot de passe"))
        self.oeil.triggered.connect(self._basculer_mdp)
        f.addRow(_("Mot de passe"), self.mdp)
        self.chiffrement = QComboBox()
        self.chiffrement.addItem(_("Chiffré (FTPS, conseillé)"), "tls")
        self.chiffrement.addItem(_("Aucun (FTP en clair)"), "")
        self.chiffrement.setCurrentIndex(0 if self.c.get("chiffrement", "tls") == "tls" else 1)
        f.addRow(_("Chiffrement"), self.chiffrement)
        self.dossier = QLineEdit(self.c.get("dossier", "/"))
        f.addRow(_("Dossier de départ"), self.dossier)
        self.libre = QCheckBox(_("Accepter un certificat non vérifié (NAS avec certificat auto-signé)"))
        self.libre.setChecked(self.c.get("certificat_libre", False))
        f.addRow(self.libre)
        self.b_autoriser = QPushButton()
        self.b_autoriser.setIcon(icone("certificat", "#0f6cbd"))
        self.b_autoriser.clicked.connect(self._autoriser)
        self.etat_auth = QLabel()
        self.etat_auth.setWordWrap(True)
        wa = QWidget()
        ha2 = QVBoxLayout(wa)
        ha2.setContentsMargins(0, 0, 0, 0)
        ha2.addWidget(self.b_autoriser)
        ha2.addWidget(self.etat_auth)
        f.addRow(_("Accès"), wa)
        self.note = QLabel(_("Le mot de passe est rangé dans le coffre de Windows (ou de Linux), jamais en clair."))
        self.note.setStyleSheet("color:#555;font-size:12px")
        self.note.setWordWrap(True)
        f.addRow(self.note)
        bb = QDialogButtonBox()
        self.b_test = bb.addButton(_("Tester la connexion"), QDialogButtonBox.ActionRole)
        self.b_test.clicked.connect(self.tester)
        b_ok = bb.addButton(_("Enregistrer"), QDialogButtonBox.AcceptRole)
        b_ok.setDefault(True)
        bb.addButton(_("Annuler"), QDialogButtonBox.RejectRole)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        f.addRow(bb)
        self.type.currentIndexChanged.connect(lambda _i: self._maj_type())
        self.adresse.textChanged.connect(self._maj_port)
        self._maj_type()

    def _maj_auth(self):
        from . import oauth
        t = self.c["type"]
        nom = distant.TYPES[t]
        if t not in oauth.FOURNISSEURS or not oauth.disponible(t):
            self.b_autoriser.setEnabled(False)
            self.b_autoriser.setText(_("Autoriser l'accès à {nom}", nom=nom))
            self.etat_auth.setText(_("Pas encore disponible dans cette version (identifiant d'application de PhilPDF à venir)."))
            return
        self.b_autoriser.setEnabled(True)
        if coffre.lire(self.c["id"] + ".jeton"):
            self.b_autoriser.setText(_("Autoriser à nouveau (autre compte)"))
            self.etat_auth.setText("✓ " + _("Accès autorisé. PhilPDF ne voit que les fichiers qu'il crée ou que vous ouvrez avec lui."))
            self.etat_auth.setStyleSheet("color:#1d5a2b")
        else:
            self.b_autoriser.setText(_("Autoriser l'accès à {nom}...", nom=nom))
            self.etat_auth.setText(_("Le navigateur s'ouvrira : connectez-vous et cliquez sur « Autoriser ». Aucun mot de passe "
                                     "n'est donné à PhilPDF."))
            self.etat_auth.setStyleSheet("color:#555")

    def _autoriser(self):
        c = self.compte()
        if autoriser_compte(self, c):
            self._maj_auth()
            self.b_test.setEnabled(True)
            try:
                qui = distant.emplacement(c).qui()
                if qui and self.nom.text().strip() in ("", distant.TYPES[c["type"]]):
                    self.nom.setText(f"{distant.TYPES[c['type']]} ({qui})")
            except distant.ErreurDistant:
                pass

    def _basculer_mdp(self):
        visible = self.mdp.echoMode() == QLineEdit.Password
        self.mdp.setEchoMode(QLineEdit.Normal if visible else QLineEdit.Password)
        self.oeil.setIcon(icone("oeil_barre" if visible else "oeil", "#555555"))
        self.oeil.setToolTip(_("Masquer le mot de passe") if visible else _("Afficher le mot de passe"))

    def _maj_type(self):
        t = self.type.currentData()
        ancien = self.c.get("type")
        if self.nom.text().strip() in ("", distant.TYPES.get(ancien, "")):
            self.nom.setText(distant.TYPES[t])
        self.c["type"] = t
        self.aide.setText(AIDE[t])
        self.adresse.setPlaceholderText(EXEMPLES.get(t, ""))
        serveur = t in ("synology", "webdav", "ftp")
        for w, vis in ((self.adresse.parentWidget(), t not in distant.NUAGES), (self.port, serveur),
                       (self.utilisateur, serveur), (self.mdp, serveur), (self.chiffrement, t == "ftp"),
                       (self.dossier, serveur), (self.libre, serveur), (self.note, serveur),
                       (self.b_autoriser.parentWidget(), t in distant.NUAGES)):
            self.f.setRowVisible(w, vis)
        if t in distant.NUAGES:
            self._maj_auth()
        self.b_choisir.setVisible(t == "reseau")
        self.port.setToolTip(PORTS.get(t, ""))
        from . import oauth
        self.b_test.setEnabled(t not in distant.NUAGES or bool(coffre.lire(self.c["id"] + ".jeton")))
        self._maj_port()
        self.adjustSize()

    def _maj_port(self, *_a):
        """Un port ecrit dans l'adresse (…:5006) l'emporte : le champ Port le montre et se grise."""
        a = self.adresse.text().strip()
        try:
            u = urllib.parse.urlsplit(a if "://" in a else "x://" + a)
            p = u.port
        except ValueError:
            p = None
        if p and self.c.get("type") != "reseau":
            self.port.setValue(p)
            self.port.setEnabled(False)
            self.port.setToolTip(_("Port indiqué dans l'adresse."))
        else:
            self.port.setEnabled(True)
            self.port.setToolTip(PORTS.get(self.c.get("type"), ""))

    def compte(self):
        t = self.type.currentData()
        self.c.update(type=t, nom=self.nom.text().strip() or distant.TYPES[t],
                      adresse=self.adresse.text().strip(), port=self.port.value() if self.port.isEnabled() else 0,
                      utilisateur=self.utilisateur.text().strip(), dossier=self.dossier.text().strip() or "/",
                      chiffrement=self.chiffrement.currentData() if t == "ftp" else "",
                      certificat_libre=self.libre.isChecked())
        return self.c

    def tester(self):
        c = self.compte()
        e = distant.emplacement(c, self.mdp.text())
        for _essai in range(2):
            try:
                QApplication.setOverrideCursor(Qt.WaitCursor)
                try:
                    msg = e.tester()
                finally:
                    QApplication.restoreOverrideCursor()
                erreur(self, _("Tester la connexion"), msg, e, info=True)
                return
            except distant.BesoinCode:
                code, ok = QInputDialog.getText(self, c["nom"], _("Code de vérification (application d'authentification) :"))
                if not ok:
                    return
                coffre.enregistrer(c["id"], self.mdp.text())
                e = distant.emplacement(c, self.mdp.text(), code=code.strip())
            except distant.ErreurDistant as ex:
                erreur(self, _("Tester la connexion"), ex, e)
                return

    def accept(self):
        self.compte()
        if self.c["type"] in ("synology", "webdav", "ftp"):
            coffre.enregistrer(self.c["id"], self.mdp.text())
        super().accept()


class PanneauComptes(QWidget):
    """Liste des comptes (onglet des Preferences)."""

    def __init__(self, parent, params):
        super().__init__(parent)
        self.params = params
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        self.liste = QListWidget()
        self.liste.setIconSize(QSize(22, 22))
        self.liste.itemDoubleClicked.connect(lambda _it: self.modifier())
        v.addWidget(self.liste, 1)
        h = QHBoxLayout()
        ajout = QPushButton(_("Ajouter un compte..."))
        m = QMenu(ajout)
        for t, lib in distant.TYPES.items():
            a = m.addAction(icone(ICONES[t], "#444444"), _(lib))
            a.triggered.connect(lambda _x=False, t=t: self.ajouter(t))
        ajout.setMenu(m)
        h.addWidget(ajout)
        for txt, f in ((_("Modifier..."), self.modifier), (_("Tester"), self.tester), (_("Supprimer"), self.supprimer)):
            b = QPushButton(txt)
            b.clicked.connect(f)
            h.addWidget(b)
        h.addStretch()
        v.addLayout(h)
        self.remplir()

    def comptes(self):
        return list(self.params.get("comptes", []))

    def remplir(self):
        self.liste.clear()
        for c in self.comptes():
            detail = c.get("adresse") or ""
            if c.get("utilisateur"):
                detail = f"{c['utilisateur']} @ {detail}"
            it = QListWidgetItem(icone(ICONES.get(c["type"], "ouvrir"), "#0f6cbd"),
                                 f"{distant.libelle(c)}   —   {_(distant.TYPES[c['type']])}   {detail}")
            it.setData(Qt.UserRole, c["id"])
            self.liste.addItem(it)

    def _courant(self):
        it = self.liste.currentItem()
        if it:
            return next((c for c in self.comptes() if c["id"] == it.data(Qt.UserRole)), None)

    def _enregistrer(self, c):
        cs = [x for x in self.comptes() if x["id"] != c["id"]] + [c]
        self.params["comptes"] = cs
        self.params.enregistrer()
        self.remplir()

    def ajouter(self, t):
        d = DialogueCompte(self, distant.nouveau_compte(t))
        if d.exec() == QDialog.Accepted:
            self._enregistrer(d.compte())

    def modifier(self):
        c = self._courant()
        if c:
            d = DialogueCompte(self, c)
            if d.exec() == QDialog.Accepted:
                self._enregistrer(d.compte())

    def tester(self):
        c = self._courant()
        if c and ouvrir_emplacement(self, c):
            QMessageBox.information(self, distant.libelle(c), _("Connexion réussie."))

    def supprimer(self):
        c = self._courant()
        if c and QMessageBox.question(self, _("Supprimer"), _("Supprimer le compte « {nom} » ?", nom=distant.libelle(c))) == QMessageBox.Yes:
            self.params["comptes"] = [x for x in self.comptes() if x["id"] != c["id"]]
            self.params.enregistrer()
            coffre.supprimer(c["id"])
            coffre.supprimer(c["id"] + ".appareil")
            self.remplir()


# ------------------------------------------------------------------------------------------- parcourir
class DialogueParcourir(QDialog):
    """Choisir un PDF a ouvrir, ou un dossier et un nom pour enregistrer, sur un emplacement distant."""

    def __init__(self, parent, params, mode="ouvrir", nom="", compte_id=None):
        super().__init__(parent)
        self.params, self.mode = params, mode
        self.setWindowTitle(_("Ouvrir depuis un emplacement") if mode == "ouvrir" else _("Enregistrer vers un emplacement"))
        self.resize(760, 520)
        v = QVBoxLayout(self)
        h = QHBoxLayout()
        h.addWidget(QLabel(_("Emplacement :")))
        self.comptes = QComboBox()
        for c in params.get("comptes", []):
            self.comptes.addItem(icone(ICONES.get(c["type"], "ouvrir"), "#0f6cbd"), distant.libelle(c), c["id"])
        h.addWidget(self.comptes, 1)
        self.b_haut = QToolButton()
        self.b_haut.setIcon(icone("precedente", "#444444"))
        self.b_haut.setToolTip(_("Dossier parent"))
        self.b_haut.clicked.connect(self.monter)
        h.addWidget(self.b_haut)
        v.addLayout(h)
        self.lbl_chemin = QLabel()
        self.lbl_chemin.setStyleSheet("color:#555")
        v.addWidget(self.lbl_chemin)
        self.liste = QListWidget()
        self.liste.setIconSize(QSize(20, 20))
        self.liste.itemDoubleClicked.connect(self._double)
        self.liste.currentItemChanged.connect(self._choix)
        v.addWidget(self.liste, 1)
        self.nom = QLineEdit(nom)
        if mode == "enregistrer":
            hn = QHBoxLayout()
            hn.addWidget(QLabel(_("Nom du fichier :")))
            hn.addWidget(self.nom, 1)
            v.addLayout(hn)
        bb = QDialogButtonBox()
        self.b_ok = bb.addButton(_("Ouvrir") if mode == "ouvrir" else _("Enregistrer"), QDialogButtonBox.AcceptRole)
        self.b_ok.setDefault(True)
        bb.addButton(_("Annuler"), QDialogButtonBox.RejectRole)
        bb.accepted.connect(self._valider)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        self.e, self.dossier, self.choisi = None, "/", None
        self.comptes.currentIndexChanged.connect(lambda _i: self._connecter())
        if compte_id:
            self.comptes.setCurrentIndex(max(0, self.comptes.findData(compte_id)))
        self._connecter()

    def compte(self):
        cid = self.comptes.currentData()
        return next((c for c in self.params.get("comptes", []) if c["id"] == cid), None)

    def _connecter(self):
        c = self.compte()
        self.liste.clear()
        if not c:
            return
        self.e = ouvrir_emplacement(self, c)
        if self.e:
            self.aller(self.e.racine())

    def aller(self, dossier):
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                elems = self.e.lister(dossier)
            finally:
                QApplication.restoreOverrideCursor()
        except distant.ErreurDistant as ex:
            erreur(self, self.windowTitle(), ex, self.e)
            return
        self.dossier = dossier
        self.lbl_chemin.setText(dossier)
        self.liste.clear()
        for x in elems:
            if not x.dossier and not x.nom.lower().endswith(".pdf"):
                continue
            it = QListWidgetItem(icone("ouvrir" if x.dossier else "creer", "#c8a000" if x.dossier else "#c9252d"),
                                 x.nom + ("" if x.dossier else _("   ({n} Ko)", n=max(1, x.taille // 1024))))
            it.setData(Qt.UserRole, x)
            self.liste.addItem(it)

    def monter(self):
        if self.e and self.dossier not in ("", "/"):
            self.aller(posixpath.dirname(self.dossier.rstrip("/")) or "/")

    def _double(self, it):
        x = it.data(Qt.UserRole)
        if x.dossier:
            self.aller(x.chemin)
        elif self.mode == "ouvrir":
            self.choisi = x.chemin
            self.accept()

    def _choix(self, it, _ancien=None):
        x = it.data(Qt.UserRole) if it else None
        if x and not x.dossier and self.mode == "enregistrer":
            self.nom.setText(x.nom)

    def _valider(self):
        if not self.e:
            return
        if self.mode == "ouvrir":
            it = self.liste.currentItem()
            x = it.data(Qt.UserRole) if it else None
            if not x:
                return
            if x.dossier:
                self.aller(x.chemin)
                return
            self.choisi = x.chemin
        else:
            nom = self.nom.text().strip()
            if not nom:
                return
            if not nom.lower().endswith(".pdf"):
                nom += ".pdf"
            self.choisi = posixpath.join(self.dossier, nom)
        self.accept()
