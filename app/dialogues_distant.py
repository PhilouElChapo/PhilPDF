"""Fenetres des emplacements distants : compte (NAS, FTP, WebDAV...), choix d'un fichier ou d'un dossier."""
import os, posixpath
from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit, QPushButton, QComboBox,
                               QCheckBox, QSpinBox, QDialogButtonBox, QListWidget, QListWidgetItem, QMessageBox,
                               QInputDialog, QApplication, QWidget, QMenu, QToolButton)
from .langue import _
from .icones import icone
from . import distant, coffre

ICONES = {"reseau": "ouvrir", "synology": "archiver", "webdav": "lot", "ftp": "exporter", "gdrive": "synchro", "onedrive": "synchro"}
AIDE = {
    "reseau": _("Un dossier partagé déjà accessible depuis ce PC : \\\\NAS\\partage, une lettre de lecteur (Z:\\) ou /mnt/nas."),
    "synology": _("L'adresse de votre Synology dans le navigateur : http://nas:5000, https://nas:5001 ou une adresse "
                "personnelle (nasdelaye.homedns.org). Si la vérification en deux étapes est active, le code sera demandé "
                "une seule fois."),
    "webdav": _("Adresse WebDAV complète, par exemple https://nas:5006 (paquet « WebDAV Server » du Synology) ou "
              "https://cloud.exemple.fr/remote.php/dav/files/nom/."),
    "ftp": _("Nom ou adresse du serveur (ftp.exemple.fr, 192.168.1.20). Chiffrement conseillé ; « aucun » = FTP en clair."),
    "gdrive": _("Google Drive en direct, par autorisation dans le navigateur : arrive dès que l'identifiant d'application "
              "de PhilPDF sera enregistré."),
    "onedrive": _("OneDrive en direct, par autorisation dans le navigateur : arrive dès que l'identifiant d'application "
                "de PhilPDF sera enregistré."),
}


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
            QMessageBox.warning(parent, distant.libelle(compte), str(ex))
            return None
    return None


# ------------------------------------------------------------------------------------------- compte
class DialogueCompte(QDialog):
    def __init__(self, parent, compte):
        super().__init__(parent)
        self.c = dict(compte)
        t = self.c["type"]
        self.setWindowTitle(_(distant.TYPES[t]))
        self.setMinimumWidth(520)
        f = QFormLayout(self)
        aide = QLabel(AIDE[t])
        aide.setWordWrap(True)
        aide.setStyleSheet("color:#555")
        f.addRow(aide)
        self.nom = QLineEdit(self.c.get("nom", ""))
        f.addRow(_("Nom affiché"), self.nom)
        self.adresse = QLineEdit(self.c.get("adresse", ""))
        self.adresse.setPlaceholderText({"reseau": r"\\NAS\partage", "synology": "http://nasdelaye.homedns.org:5000",
                                         "webdav": "https://nas:5006", "ftp": "ftp.exemple.fr"}.get(t, ""))
        self.port = QSpinBox()
        self.port.setRange(0, 65535)
        self.port.setSpecialValueText(_("par défaut"))
        self.port.setValue(int(self.c.get("port") or 0))
        self.utilisateur = QLineEdit(self.c.get("utilisateur", ""))
        self.mdp = QLineEdit(coffre.lire(self.c["id"]) or "")
        self.mdp.setEchoMode(QLineEdit.Password)
        self.dossier = QLineEdit(self.c.get("dossier", "/"))
        self.chiffrement = QComboBox()
        self.chiffrement.addItem(_("Chiffré (FTPS, conseillé)"), "tls")
        self.chiffrement.addItem(_("Aucun (FTP en clair)"), "")
        self.chiffrement.setCurrentIndex(0 if self.c.get("chiffrement") == "tls" else 1)
        self.libre = QCheckBox(_("Accepter un certificat non vérifié (NAS avec certificat auto-signé)"))
        self.libre.setChecked(self.c.get("certificat_libre", False))
        if t == "reseau":
            h = QHBoxLayout()
            h.addWidget(self.adresse, 1)
            b = QPushButton(_("Choisir..."))
            from PySide6.QtWidgets import QFileDialog
            b.clicked.connect(lambda: (lambda p: p and self.adresse.setText(p))(
                QFileDialog.getExistingDirectory(self, _("Dossier réseau"))))
            h.addWidget(b)
            f.addRow(_("Dossier"), h)
        elif t in ("synology", "webdav", "ftp"):
            f.addRow(_("Adresse"), self.adresse)
            f.addRow(_("Port"), self.port)
            f.addRow(_("Utilisateur"), self.utilisateur)
            f.addRow(_("Mot de passe"), self.mdp)
            if t == "ftp":
                f.addRow(_("Chiffrement"), self.chiffrement)
            f.addRow(_("Dossier de départ"), self.dossier)
            f.addRow(self.libre)
            note = QLabel(_("Le mot de passe est rangé dans le coffre de Windows (ou de Linux), jamais en clair."))
            note.setStyleSheet("color:#555;font-size:12px")
            note.setWordWrap(True)
            f.addRow(note)
        bb = QDialogButtonBox()
        self.b_test = bb.addButton(_("Tester la connexion"), QDialogButtonBox.ActionRole)
        self.b_test.clicked.connect(self.tester)
        self.b_test.setEnabled(t not in ("gdrive", "onedrive"))
        b_ok = bb.addButton(_("Enregistrer"), QDialogButtonBox.AcceptRole)
        b_ok.setDefault(True)
        bb.addButton(_("Annuler"), QDialogButtonBox.RejectRole)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        f.addRow(bb)

    def compte(self):
        self.c.update(nom=self.nom.text().strip() or _(distant.TYPES[self.c["type"]]),
                      adresse=self.adresse.text().strip(), port=self.port.value(),
                      utilisateur=self.utilisateur.text().strip(), dossier=self.dossier.text().strip() or "/",
                      chiffrement=self.chiffrement.currentData() if self.c["type"] == "ftp" else "",
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
                QMessageBox.information(self, _("Tester la connexion"), msg)
                return
            except distant.BesoinCode:
                code, ok = QInputDialog.getText(self, c["nom"], _("Code de vérification (application d'authentification) :"))
                if not ok:
                    return
                coffre.enregistrer(c["id"], self.mdp.text())
                e = distant.emplacement(c, self.mdp.text(), code=code.strip())
            except distant.ErreurDistant as ex:
                QMessageBox.warning(self, _("Tester la connexion"), str(ex))
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
            QMessageBox.warning(self, self.windowTitle(), str(ex))
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
