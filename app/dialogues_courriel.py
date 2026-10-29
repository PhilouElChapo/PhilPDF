"""Fenetre « Envoyer par e-mail » et reglage des comptes d'envoi."""
import os

from PySide6.QtCore import Qt, QThread, Signal, QTimer
from .icones import icone
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QPushButton, QComboBox,
                               QLineEdit, QPlainTextEdit, QRadioButton, QButtonGroup, QCheckBox, QSpinBox,
                               QMessageBox, QApplication, QDialogButtonBox, QGroupBox, QCompleter, QListWidget,
                               QListWidgetItem, QWidget, QScrollArea, QFrame, QToolButton)

from .langue import _
from . import courriel as C, coffre, agenda


def _taille(n):
    return f"{n / 1048576:.1f} Mo".replace(".", ",") if n >= 1048576 else f"{max(1, n // 1024)} Ko"


class _Tache(QThread):
    fini = Signal(object)

    def __init__(self, f):
        super().__init__()
        self.f = f

    def run(self):
        try:
            self.fini.emit(self.f())
        except Exception as e:                       # noqa: BLE001
            self.fini.emit(e)


_EN_COURS = set()          # taches gardees jusqu'a leur fin, meme si la fenetre qui les a lancees est fermee


def lancer(f, rappel):
    """Execute f() hors de l'interface ; rappel(resultat ou exception) ensuite. Fermer la fenetre pendant
    l'attente ne fait plus planter PhilPDF (la tache vit jusqu'au bout)."""
    t = _Tache(f)
    _EN_COURS.add(t)

    def fin(r):
        _EN_COURS.discard(t)
        try:
            rappel(r)
        except RuntimeError:                         # fenetre deja fermee : rien a afficher
            pass
    t.fini.connect(fin)
    t.finished.connect(t.deleteLater)
    t.start()
    return t


# ================================================================ comptes d'envoi
class DialogueCompteMail(QDialog):
    def __init__(self, parent, compte=None):
        super().__init__(parent)
        self.setWindowTitle(_("Compte d'envoi"))
        self.setMinimumWidth(560)
        self.compte = dict(compte or C.nouveau_compte())
        v = QVBoxLayout(self)
        f = QFormLayout()
        self.adresse = QLineEdit(self.compte.get("adresse", ""))
        self.adresse.setPlaceholderText("prenom.nom@exemple.fr")
        f.addRow(_("Adresse e-mail"), self.adresse)
        self.nom = QLineEdit(self.compte.get("nom", ""))
        self.nom.setPlaceholderText(_("Nom affiché chez le destinataire"))
        f.addRow(_("Nom"), self.nom)
        self.fourn = QComboBox()
        for k, lib, *_r in C.FOURNISSEURS:
            self.fourn.addItem(lib, k)
        f.addRow(_("Fournisseur"), self.fourn)
        self.aide = QLabel()
        self.aide.setWordWrap(True)
        self.aide.setStyleSheet("color:#555")
        f.addRow("", self.aide)
        self.mdp = QLineEdit(C.mot_de_passe(self.compte) if compte else "")
        self.mdp.setEchoMode(QLineEdit.Password)
        f.addRow(_("Mot de passe"), self.mdp)
        v.addLayout(f)
        self.avance = QGroupBox(_("Serveur d'envoi (rempli tout seul)"))
        self.avance.setCheckable(True)
        self.avance.setChecked(False)
        fa = QFormLayout(self.avance)
        self.ident = QLineEdit(self.compte.get("identifiant", ""))
        self.ident.setPlaceholderText(_("(l'adresse e-mail)"))
        fa.addRow(_("Identifiant"), self.ident)
        self.serveur = QLineEdit(self.compte.get("serveur", ""))
        fa.addRow(_("Serveur SMTP"), self.serveur)
        h = QHBoxLayout()
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(int(self.compte.get("port") or 465))
        h.addWidget(self.port)
        self.secu = QComboBox()
        self.secu.addItem("SSL/TLS", "ssl")
        self.secu.addItem("STARTTLS", "starttls")
        self.secu.addItem(_("Aucune"), "aucune")
        self.secu.setCurrentIndex(max(0, self.secu.findData(self.compte.get("securite", "ssl"))))
        h.addWidget(self.secu)
        h.addStretch(1)
        fa.addRow(_("Port"), h)
        self.imap = QLineEdit(self.compte.get("imap", ""))
        self.imap.setPlaceholderText(_("pour déposer un brouillon (rempli tout seul)"))
        fa.addRow(_("Serveur IMAP"), self.imap)
        self.webmail = QLineEdit(self.compte.get("webmail", ""))
        self.webmail.setPlaceholderText("https://...")
        fa.addRow(_("Messagerie web"), self.webmail)
        v.addWidget(self.avance)
        v.addWidget(QLabel(_("Signature (ajoutée sous chaque message)")))
        self.signature = QPlainTextEdit(self.compte.get("signature", ""))
        self.signature.setMaximumHeight(90)
        v.addWidget(self.signature)
        self.etat = QLabel()
        self.etat.setWordWrap(True)
        v.addWidget(self.etat)
        h = QHBoxLayout()
        self.b_test = QPushButton(_("Tester la connexion"))
        self.b_test.clicked.connect(self.tester)
        h.addWidget(self.b_test)
        h.addStretch(1)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText(_("Enregistrer"))
        bb.button(QDialogButtonBox.Cancel).setText(_("Annuler"))
        bb.accepted.connect(self.valider)
        bb.rejected.connect(self.reject)
        h.addWidget(bb)
        v.addLayout(h)
        k = C.fournisseur_de(self.compte.get("adresse")) if not self.compte.get("serveur") else next(
            (x[0] for x in C.FOURNISSEURS if x[2] == self.compte.get("serveur")), "autre")
        self.fourn.setCurrentIndex(max(0, self.fourn.findData(k)))
        self._fourn(None, garder=bool(self.compte.get("serveur")))
        self.fourn.currentIndexChanged.connect(self._fourn)
        self.adresse.textChanged.connect(self._adresse)

    def _adresse(self, t):
        k = C.fournisseur_de(t)
        if k != "autre":
            self.fourn.setCurrentIndex(self.fourn.findData(k))

    def _fourn(self, _i, garder=False):
        k, lib, serveur, port, secu, aide = next(x for x in C.FOURNISSEURS if x[0] == self.fourn.currentData())
        self.aide.setText(aide)
        if not garder and k != "autre":
            self.imap.setText(C.IMAP.get(k, ("", ""))[0])
            self.webmail.setText(C.IMAP.get(k, ("", ""))[1])
            self.serveur.setText(serveur)
            self.port.setValue(port)
            self.secu.setCurrentIndex(self.secu.findData(secu))
        if k == "autre":
            self.avance.setChecked(True)

    def _lire(self):
        c = dict(self.compte)
        c.update(adresse=self.adresse.text().strip(), nom=self.nom.text().strip(),
                 identifiant=self.ident.text().strip(), serveur=self.serveur.text().strip(),
                 port=self.port.value(), securite=self.secu.currentData(), fournisseur=self.fourn.currentData(),
                 imap=self.imap.text().strip(), webmail=self.webmail.text().strip(),
                 signature=self.signature.toPlainText().rstrip())
        return c

    def tester(self):
        c = self._lire()
        if not c["serveur"] or "@" not in c["adresse"]:
            self.etat.setText(_("Indiquez l'adresse et le serveur."))
            return
        self.etat.setText(_("Connexion à {s}...", s=c["serveur"]))
        self.b_test.setEnabled(False)
        mdp = self.mdp.text()
        self._t = lancer(lambda: C.tester(c, mdp), self._teste)

    def _teste(self, r):
        self.b_test.setEnabled(True)
        if r is None:
            self.etat.setText("<span style='color:#1e6b34'>✓ " + _("Connexion et mot de passe acceptés.") + "</span>")
        else:
            self.etat.setText("<span style='color:#b3261e'>✕ " + str(r) + "</span>")

    def valider(self):
        c = self._lire()
        if "@" not in c["adresse"] or not c["serveur"]:
            QMessageBox.information(self, self.windowTitle(), _("Indiquez l'adresse e-mail et le serveur d'envoi."))
            return
        self.compte = c
        coffre.enregistrer(C.ident_coffre(c), self.mdp.text())
        self.accept()


class PanneauComptesMail(QWidget):
    """Liste des adresses d'envoi, a ajouter / modifier / supprimer (Preferences › E-mail et fenetre « Comptes »)."""
    change = Signal()

    def __init__(self, params, parent=None):
        super().__init__(parent)
        self.params = params
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        self.liste = QListWidget()
        self.liste.setObjectName("comptes_mail")
        self.liste.setMinimumHeight(80)
        self.liste.itemDoubleClicked.connect(lambda _i: self.modifier())
        v.addWidget(self.liste, 1)
        h = QHBoxLayout()
        for t, f in ((_("Ajouter..."), self.ajouter), (_("Modifier..."), self.modifier), (_("Supprimer"), self.supprimer)):
            b = QPushButton(t)
            b.clicked.connect(f)
            h.addWidget(b)
        h.addStretch(1)
        v.addLayout(h)
        self._remplir()

    def _remplir(self):
        self.liste.clear()
        for c in C.comptes(self.params):
            it = QListWidgetItem(icone("courriel", "#0f6cbd"),
                                 f"{c.get('nom') or c['adresse']}  <{c['adresse']}>  · {c['serveur']}")
            it.setData(Qt.UserRole, c["id"])
            self.liste.addItem(it)

    def _ecrire(self, liste):
        self.params["comptes_mail"] = liste
        self.params.enregistrer()
        self._remplir()
        self.change.emit()

    def ajouter(self):
        d = DialogueCompteMail(self)
        if d.exec():
            self._ecrire(C.comptes(self.params) + [d.compte])
            return d.compte
        return None

    def _choisi(self):
        it = self.liste.currentItem()
        return next((c for c in C.comptes(self.params) if it and c["id"] == it.data(Qt.UserRole)), None)

    def modifier(self):
        c = self._choisi()
        if c:
            d = DialogueCompteMail(self, c)
            if d.exec():
                self._ecrire([d.compte if x["id"] == c["id"] else x for x in C.comptes(self.params)])

    def supprimer(self):
        c = self._choisi()
        if c and QMessageBox.question(self, _("Adresses d'envoi"), _("Supprimer le compte {a} ?", a=c["adresse"])) == QMessageBox.Yes:
            coffre.supprimer(C.ident_coffre(c))
            self._ecrire([x for x in C.comptes(self.params) if x["id"] != c["id"]])


class DialogueComptesMail(QDialog):
    """Fenetre des adresses d'envoi (les memes reglages sont dans Preferences › E-mail)."""

    def __init__(self, parent, params):
        super().__init__(parent)
        self.params = params
        self.setWindowTitle(_("Comptes d'envoi d'e-mails"))
        self.setMinimumSize(560, 360)
        v = QVBoxLayout(self)
        l = QLabel(_("Pour que PhilPDF envoie lui-même le PDF, depuis votre adresse. Les comptes suivent sur vos "
                     "autres postes ; les mots de passe restent dans le coffre de Windows et voyagent chiffrés, "
                     "comme ceux du NAS. Les mêmes réglages sont dans Préférences › E-mail."))
        l.setWordWrap(True)
        v.addWidget(l)
        self.panneau = PanneauComptesMail(params, self)
        v.addWidget(self.panneau, 1)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.button(QDialogButtonBox.Close).setText(_("Fermer"))
        bb.rejected.connect(self.accept)
        v.addWidget(bb)

    def ajouter(self):
        return self.panneau.ajouter()


# ================================================================ carnet d'adresses
class PanneauCarnet(QWidget):
    """Carnet d'adresses : recherche, ajout, modification, import d'un export Google / Outlook (CSV) ou vCard.
    En mode choix (fenetre d'envoi), un double-clic ou « Ajouter à » met l'adresse dans A, Cc ou Cci."""
    choisi = Signal(str, str)                    # champ ("a", "cc", "cci"), adresse formatee

    def __init__(self, params, parent=None, choix=False):
        super().__init__(parent)
        self.params, self.choix = params, choix
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        self.cherche = QLineEdit()
        self.cherche.setPlaceholderText(_("Rechercher un nom ou une adresse"))
        self.cherche.setClearButtonEnabled(True)
        self.cherche.textChanged.connect(self._remplir)
        v.addWidget(self.cherche)
        self.liste = QListWidget()
        self.liste.setObjectName("carnet")
        self.liste.setMinimumHeight(120)
        self.liste.setSelectionMode(QListWidget.ExtendedSelection)
        self.liste.itemDoubleClicked.connect(lambda it: self.choisi.emit("a", it.data(Qt.UserRole)) if choix
                                             else self.modifier())
        v.addWidget(self.liste, 1)
        fl = FluxBoutons()
        if choix:
            for k, t in (("a", _("À")), ("cc", _("Cc")), ("cci", _("Cci"))):
                b = QPushButton(_("Ajouter en {x}", x=t))
                b.clicked.connect(lambda _c=False, k=k: [self.choisi.emit(k, it.data(Qt.UserRole))
                                                         for it in self.liste.selectedItems()])
                fl.ajouter(b)
        for t, f in ((_("Nouveau..."), self.nouveau), (_("Modifier..."), self.modifier), (_("Supprimer"), self.supprimer),
                     (_("Importer (Google, Outlook, vCard)..."), self.importer)):
            b = QPushButton(t)
            b.clicked.connect(f)
            fl.ajouter(b)
        v.addWidget(fl)
        self._remplir()

    def _remplir(self, *_a):
        q = self.cherche.text().strip().lower()
        self.liste.clear()
        for c in C.carnet(self.params):
            lib = C.formater(c)
            if q and q not in lib.lower():
                continue
            it = QListWidgetItem(lib)
            it.setData(Qt.UserRole, lib)
            it.setData(Qt.UserRole + 1, c["email"])
            self.liste.addItem(it)

    def _editer(self, c=None):
        from PySide6.QtWidgets import QFormLayout as _F
        d = QDialog(self)
        d.setWindowTitle(_("Contact"))
        f = _F(d)
        nom, mail = QLineEdit((c or {}).get("nom", "")), QLineEdit((c or {}).get("email", ""))
        mail.setPlaceholderText("prenom.nom@exemple.fr")
        f.addRow(_("Nom"), nom)
        f.addRow(_("Adresse e-mail"), mail)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText(_("Enregistrer"))
        bb.button(QDialogButtonBox.Cancel).setText(_("Annuler"))
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        f.addRow(bb)
        if d.exec() and "@" in mail.text():
            return {"nom": nom.text().strip(), "email": mail.text().strip()}
        return None

    def nouveau(self):
        c = self._editer()
        if c:
            C.ajouter_contacts(self.params, [c])
            self._remplir()

    def _courant(self):
        it = self.liste.currentItem()
        return next((c for c in C.carnet(self.params) if it and c["email"] == it.data(Qt.UserRole + 1)), None)

    def modifier(self):
        c = self._courant()
        if c:
            n = self._editer(c)
            if n:
                self.params["carnet"] = [n if x is c or x["email"] == c["email"] else x for x in C.carnet(self.params)]
                self.params.enregistrer()
                self._remplir()

    def supprimer(self):
        mails = {it.data(Qt.UserRole + 1) for it in self.liste.selectedItems()}
        if mails and QMessageBox.question(self, _("Carnet d'adresses"),
                                          _("Supprimer {n} contact(s) du carnet ?", n=len(mails))) == QMessageBox.Yes:
            self.params["carnet"] = [x for x in C.carnet(self.params) if x["email"] not in mails]
            self.params.enregistrer()
            self._remplir()

    def importer(self):
        from PySide6.QtWidgets import QFileDialog
        f, _x = QFileDialog.getOpenFileName(self, _("Importer des contacts"), "",
                                           _("Contacts (*.csv *.vcf);;Tous les fichiers (*)"))
        if not f:
            return
        try:
            contacts = C.lire_contacts(f)
        except Exception as e:                       # noqa: BLE001
            QMessageBox.warning(self, _("Carnet d'adresses"), _("Fichier illisible : {e}", e=e))
            return
        n = C.ajouter_contacts(self.params, contacts)
        self._remplir()
        QMessageBox.information(self, _("Carnet d'adresses"),
                                _("{n} contact(s) ajouté(s) ({t} lu(s) dans le fichier).", n=n, t=len(contacts)))


class FluxBoutons(QWidget):
    """Boutons qui passent a la ligne quand la place manque (rien de tronque)."""

    def __init__(self):
        super().__init__()
        from .document import FluxLayout
        self.fl = FluxLayout(self, marge=0, espace=6)

    def ajouter(self, w):
        self.fl.addWidget(w)


class DialogueCarnet(QDialog):
    def __init__(self, parent, params):
        super().__init__(parent)
        self.setWindowTitle(_("Carnet d'adresses"))
        self.resize(560, 460)
        v = QVBoxLayout(self)
        self.panneau = PanneauCarnet(params, self, choix=True)
        v.addWidget(self.panneau, 1)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.button(QDialogButtonBox.Close).setText(_("Fermer"))
        bb.rejected.connect(self.accept)
        v.addWidget(bb)


# ================================================================ envoyer (volet de droite)
VERSIONS = [("tel_quel", _("Tel quel"), _("Le document comme il est à l'écran, modifications comprises")),
            ("allege", _("Allégé pour l'envoi"), _("Images recompressées : même lecture à l'écran, poids réduit")),
            ("fige", _("Figé"), _("Formulaires et commentaires incrustés : le destinataire ne peut plus les modifier")),
            ("protege", _("Protégé par mot de passe"), _("À donner au destinataire par un autre moyen (SMS, téléphone)"))]
TITRE_STYLE = "font-size:12px;font-weight:600;color:#555;letter-spacing:1px;margin-top:6px"


class _Libelle(QLabel):
    """Texte d'un bouton radio qui passe a la ligne (rien de tronque dans un volet etroit) ; cliquable."""

    def __init__(self, texte, bouton):
        super().__init__(texte)
        self.bouton = bouton
        self.setWordWrap(True)
        self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, e):
        if self.bouton.isEnabled():
            if isinstance(self.bouton, QRadioButton):
                self.bouton.setChecked(True)
            else:
                self.bouton.toggle()


def ligne_radio(bouton, texte, layout, retrait=0):
    """Ajoute le bouton (sans texte) et son libelle a la ligne dans layout ; renvoie le libelle."""
    w = QWidget()
    h = QHBoxLayout(w)
    h.setContentsMargins(retrait, 0, 0, 0)
    h.setSpacing(6)
    bouton.setText("")
    h.addWidget(bouton, 0, Qt.AlignTop)
    l = _Libelle(texte, bouton)
    h.addWidget(l, 1)
    layout.addWidget(w)
    bouton._libelle, bouton._ligne = l, w
    return l


class PanneauEnvoyer(QWidget):
    """Volet « Envoyer par e-mail » (comme le volet Partager d'Acrobat, en plus complet) : la piece jointe et sa
    version (tel quel, allege, fige, protege, avec le poids de chacune), le moyen d'envoi, puis le message."""

    def __init__(self, onglet, fenetre):
        super().__init__()
        self.o, self.f, self.params = onglet, fenetre, onglet.params
        self.cache = {}
        r = self.params.get("courriel") or {}
        ext = QVBoxLayout(self)
        ext.setContentsMargins(0, 0, 0, 0)
        defil = QScrollArea()
        defil.setWidgetResizable(True)
        defil.setFrameShape(QFrame.NoFrame)
        defil.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        ext.addWidget(defil)
        corps = QWidget()
        defil.setWidget(corps)
        self._defil, self._corps = defil, corps
        defil.viewport().installEventFilter(self)      # le contenu suit la largeur du volet (rien de coupe a droite)
        v = QVBoxLayout(corps)
        v.setContentsMargins(14, 12, 14, 12)
        v.setSpacing(6)
        h = QHBoxLayout()
        t = QLabel(_("ENVOYER PAR E-MAIL"))
        t.setStyleSheet("font-size:12px;font-weight:600;color:#555;letter-spacing:1px")
        h.addWidget(t, 1)
        b = QToolButton()
        b.setText("✕")
        b.setAutoRaise(True)
        b.setToolTip(_("Fermer"))
        b.clicked.connect(self.fermer)
        h.addWidget(b)
        v.addLayout(h)
        # -- piece jointe
        self.nom = QLineEdit(onglet.nom if onglet.nom.lower().endswith(".pdf") else onglet.nom + ".pdf")
        self.nom.setToolTip(_("Nom de la pièce jointe"))
        self.nom.setCursorPosition(0)
        v.addWidget(self.nom)
        self.grp = QButtonGroup(self)
        self.radios, self.l_tailles = {}, {}
        signe = bool(onglet.octets_signes)
        for k, lib, aide in VERSIONS:
            hh = QHBoxLayout()
            rb = QRadioButton()
            rb.setToolTip(aide)
            self.grp.addButton(rb)
            self.radios[k] = rb
            hh.addWidget(rb, 0, Qt.AlignTop)
            ll = _Libelle(lib, rb)
            ll.setToolTip(aide)
            hh.addWidget(ll, 1)
            lt = QLabel()
            lt.setStyleSheet("color:#555")
            self.l_tailles[k] = lt
            hh.addWidget(lt)
            v.addLayout(hh)
            if signe and k != "tel_quel":
                rb.setEnabled(False)
                rb.setToolTip(_("Document signé : il part tel quel pour que les signatures restent valides."))
        self.mdp = QLineEdit()
        self.mdp.setPlaceholderText(_("Mot de passe d'ouverture"))
        self.mdp.setEchoMode(QLineEdit.Password)
        v.addWidget(self.mdp)
        self.l_aide_version = QLabel()
        self.l_aide_version.setWordWrap(True)
        self.l_aide_version.setStyleSheet("color:#777;font-size:11px")
        v.addWidget(self.l_aide_version)
        self.l_poids = QLabel()
        self.l_poids.setWordWrap(True)
        v.addWidget(self.l_poids)
        # -- moyen d'envoi
        t = QLabel(_("ENVOYER AVEC"))
        t.setStyleSheet(TITRE_STYLE)
        v.addWidget(t)
        self.grp_moyen = QButtonGroup(self)
        logi = C.logiciel_par_defaut()
        self.r_logiciel = QRadioButton()
        self.r_logiciel.setToolTip(_("Outlook, Thunderbird... : le message s'ouvre avec le PDF déjà joint"))
        self.r_compte = QRadioButton()
        self.r_web = QRadioButton()
        for rb in (self.r_logiciel, self.r_compte, self.r_web):
            self.grp_moyen.addButton(rb)
        ligne_radio(self.r_logiciel, _("Mon logiciel de messagerie") + (f" ({logi})" if logi else ""), v)
        ligne_radio(self.r_compte, _("Mon adresse e-mail (Orange, Gmail, Free...)"), v)
        self.bloc_compte = QWidget()
        bc = QVBoxLayout(self.bloc_compte)
        bc.setContentsMargins(22, 0, 0, 0)
        hc = QHBoxLayout()
        self.cb_compte = QComboBox()
        hc.addWidget(self.cb_compte, 1)
        b = QPushButton(_("Comptes..."))
        b.setToolTip(_("Ajouter ou régler une adresse d'envoi"))
        b.clicked.connect(self._comptes)
        hc.addWidget(b)
        bc.addLayout(hc)
        self.r_direct = QRadioButton(_("PhilPDF l'envoie directement"))
        self.r_brouillon = QRadioButton(_("Le mettre dans mes Brouillons (j'envoie depuis ma messagerie web)"))
        self.grp_mode = QButtonGroup(self)
        self.grp_mode.addButton(self.r_direct)
        self.grp_mode.addButton(self.r_brouillon)
        ligne_radio(self.r_direct, _("PhilPDF l'envoie directement"), bc)
        ligne_radio(self.r_brouillon, _("Le mettre dans mes Brouillons (j'envoie depuis ma messagerie web)"), bc)
        v.addWidget(self.bloc_compte)
        ligne_radio(self.r_web, _("Messagerie web, sans compte réglé"), v)
        self.cb_web = QComboBox()
        for k, nom in agenda.MESSAGERIES:
            if k != "mailto":
                self.cb_web.addItem(nom, k)
        self.cb_web.setCurrentIndex(max(0, self.cb_web.findData(r.get("web", self.params.get("messagerie") or "gmail"))))
        self.bloc_web = QWidget()
        bw = QVBoxLayout(self.bloc_web)
        bw.setContentsMargins(22, 0, 0, 0)
        bw.addWidget(self.cb_web)
        v.addWidget(self.bloc_web)
        self.l_moyen = QLabel()
        self.l_moyen.setWordWrap(True)
        self.l_moyen.setStyleSheet("color:#666;font-size:11px")
        v.addWidget(self.l_moyen)
        # -- message
        t = QLabel(_("MESSAGE"))
        t.setStyleSheet(TITRE_STYLE)
        v.addWidget(t)
        self.a, self.cc, self.cci = QLineEdit(), QLineEdit(), QLineEdit()
        for champ, aide in ((self.a, _("À : adresse@exemple.fr")), (self.cc, _("Cc (facultatif)")),
                            (self.cci, _("Cci, copie cachée (facultatif)"))):
            champ.setPlaceholderText(aide)
            champ.setCompleter(self._completeur())
            hh = QHBoxLayout()
            hh.setSpacing(4)
            hh.addWidget(champ, 1)
            b = QToolButton()
            b.setIcon(icone("carnet", "#0f6cbd"))
            b.setToolTip(_("Carnet d'adresses"))
            b.clicked.connect(lambda _c=False, ch=champ: self._carnet(ch))
            hh.addWidget(b)
            v.addLayout(hh)
        self.au_carnet = QCheckBox(_("Ajouter les nouvelles adresses au carnet"))
        self.au_carnet.setChecked(r.get("au_carnet", True))
        self.sujet = QLineEdit(os.path.splitext(self.nom.text())[0])
        self.sujet.setPlaceholderText(_("Objet"))
        self.sujet.setCursorPosition(0)
        v.addWidget(self.sujet)
        self.corps = QPlainTextEdit(_("Bonjour,\n\nVeuillez trouver ci-joint « {f} ».\n\nCordialement,\n{a}",
                                      f=self.nom.text(), a=self.params.get("auteur", "")).rstrip() + "\n")
        self.corps.setMinimumHeight(150)
        v.addWidget(self.corps, 1)
        v.addWidget(self.au_carnet)
        self.copie = QCheckBox(_("M'en envoyer une copie"))
        self.copie.setChecked(r.get("copie", False))
        v.addWidget(self.copie)
        self.etat = QLabel()
        self.etat.setWordWrap(True)
        v.addWidget(self.etat)
        self.b_ok = QPushButton()
        self.b_ok.setObjectName("b_envoyer")
        self.b_ok.setStyleSheet("QPushButton{background:#0f6cbd;color:#fff;border:none;border-radius:6px;"
                                "padding:8px 12px;font-weight:600}QPushButton:disabled{background:#9bbbe0}")
        self.b_ok.clicked.connect(self.valider)
        v.addWidget(self.b_ok)
        # -- etat de depart (memorise)
        self._remplir_comptes(r.get("compte"))
        moyen = r.get("moyen", "logiciel")
        {"compte": self.r_compte, "web": self.r_web}.get(moyen, self.r_logiciel).setChecked(True)
        (self.r_brouillon if r.get("mode") == "brouillon" else self.r_direct).setChecked(True)
        k = r.get("version", "tel_quel")
        (self.radios[k] if self.radios.get(k) and self.radios[k].isEnabled() else self.radios["tel_quel"]).setChecked(True)
        self.grp.buttonToggled.connect(lambda *_a: self._maj())
        for g in (self.grp_moyen, self.grp_mode):
            g.buttonToggled.connect(lambda *_a: (self.etat.clear(), self._maj(False)))
        self.cb_compte.currentIndexChanged.connect(lambda *_a: self._maj(False))
        self.nom.editingFinished.connect(self._maj)
        self._maj()

    def _completeur(self):
        l = [C.formater(c) for c in C.carnet(self.params)]
        l += [x for x in (self.params.get("courriel_recents") or []) if not any(x.lower() in y.lower() for y in l)]
        comp = QCompleter(l, self)
        comp.setCaseSensitivity(Qt.CaseInsensitive)
        comp.setFilterMode(Qt.MatchContains)
        return comp

    def _carnet(self, champ):
        d = DialogueCarnet(self, self.params)
        cibles = {"a": self.a, "cc": self.cc, "cci": self.cci}

        def mettre(k, adr):
            c = cibles[k] if k != "a" or champ is self.a else champ
            t = c.text().strip().rstrip(",;").strip()
            if adr.lower() not in t.lower():
                c.setText((t + ", " if t else "") + adr)
        d.panneau.choisi.connect(mettre)
        d.exec()
        for c in cibles.values():
            c.setCompleter(self._completeur())

    def eventFilter(self, obj, ev):
        from PySide6.QtCore import QEvent
        if ev.type() == QEvent.Resize and obj is self._defil.viewport():
            self._corps.setFixedWidth(obj.width())
        return False

    def fermer(self):
        self.o.pile_volet.setCurrentIndex(0)

    # ---- comptes
    def _remplir_comptes(self, choix=None):
        self.cb_compte.blockSignals(True)
        self.cb_compte.clear()
        for c in C.comptes(self.params):
            self.cb_compte.addItem(c["adresse"], c["id"])
        if not C.comptes(self.params):
            self.cb_compte.addItem(_("Aucune adresse réglée : cliquez « Comptes... »"), None)
        self.cb_compte.setCurrentIndex(max(0, self.cb_compte.findData(choix)))
        self.cb_compte.blockSignals(False)

    def _comptes(self):
        choix = self.cb_compte.currentData()
        d = DialogueComptesMail(self, self.params)
        if not C.comptes(self.params):
            QTimer.singleShot(0, d.ajouter)
        d.exec()
        self._remplir_comptes(choix or (C.comptes(self.params)[-1]["id"] if C.comptes(self.params) else None))
        self.r_compte.setChecked(bool(C.comptes(self.params)))
        self._maj(False)

    def compte(self):
        return next((c for c in C.comptes(self.params) if c["id"] == self.cb_compte.currentData()), None)

    # ---- piece jointe
    def version(self):
        return next(k for k, rb in self.radios.items() if rb.isChecked())

    def _fichier(self, k=None):
        k = k or self.version()
        cle = (k, self.mdp.text() if k == "protege" else "", self.nom.text())
        if cle not in self.cache:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                self.cache[cle] = C.preparer_fichier(self.o, k, self.nom.text(), self.mdp.text())
            finally:
                QApplication.restoreOverrideCursor()
        return self.cache[cle]

    def oublier(self):
        """Le document a change : les pieces jointes deja preparees sont a refaire."""
        self.cache.clear()
        for l in self.l_tailles.values():
            l.clear()

    def _maj(self, calculer=True):
        k = self.version()
        self.mdp.setVisible(k == "protege")
        self.l_aide_version.setText(next(a for kk, _l, a in VERSIONS if kk == k))
        if calculer:
            for kk in ("tel_quel", k):
                if kk != "protege" and self.radios[kk].isEnabled():
                    self.l_tailles[kk].setText(_taille(os.path.getsize(self._fichier(kk))))
            t = os.path.getsize(self._fichier(k if k != "protege" else "tel_quel"))
            trop = t > C.LIMITE_MO * 1048576
            self.l_poids.setText(("<span style='color:#b3261e'>" + _(
                "{t} : trop lourd pour la plupart des messageries (limite vers {l} Mo). Choisissez « Allégé » ou "
                "fractionnez le document.", t=_taille(t), l=C.LIMITE_MO) + "</span>") if trop else "")
        compte = self.r_compte.isChecked()
        self.bloc_compte.setVisible(compte)
        self.bloc_web.setVisible(self.r_web.isChecked())
        c = self.compte()
        direct = compte and self.r_direct.isChecked()
        brouillon = compte and self.r_brouillon.isChecked()
        self.r_brouillon.setEnabled(bool(c and C.imap_de(c)))
        self.copie.setVisible(direct)
        self.b_ok.setText(_("Envoyer") if direct else _("Mettre dans mes Brouillons") if brouillon
                          else _("Préparer le message"))
        self.b_ok.setEnabled(not compte or c is not None)
        if direct:
            t = _("PhilPDF envoie le message quand vous cliquez « Envoyer » ; il part de votre adresse et se "
                  "retrouve dans vos Envoyés (chez Gmail ; ailleurs, cochez « M'en envoyer une copie »).")
        elif brouillon:
            t = _("Le message, PDF joint, est déposé dans vos Brouillons puis votre messagerie web s'ouvre : il "
                  "ne reste qu'à l'ouvrir et cliquer « Envoyer ».")
        elif self.r_logiciel.isChecked():
            t = _("Le message s'ouvre dans votre logiciel avec le PDF joint : vous le relisez et l'envoyez.")
        else:
            t = _("Le message s'ouvre pré-rempli dans le navigateur, et le dossier du PDF s'ouvre à côté (fichier "
                  "sélectionné) : glissez-le dans le message. Avec une adresse réglée, le PDF est joint tout seul.")
        self.l_moyen.setText(t)

    def _retenir(self):
        recents = list(self.params.get("courriel_recents") or [])
        tous = C.adresses(self.a.text()) + C.adresses(self.cc.text()) + C.adresses(self.cci.text())
        if self.au_carnet.isChecked():
            C.ajouter_contacts(self.params, [{"nom": n, "email": m} for n, m in C.noms_adresses(
                ", ".join(x for x in (self.a.text(), self.cc.text(), self.cci.text()) if x))])
        for x in reversed(tous):
            recents = [x] + [y for y in recents if y.lower() != x.lower()]
        self.params["courriel_recents"] = recents[:40]
        self.params["courriel"] = {"moyen": "compte" if self.r_compte.isChecked() else "web" if self.r_web.isChecked()
                                   else "logiciel", "mode": "brouillon" if self.r_brouillon.isChecked() else "direct",
                                   "compte": self.cb_compte.currentData(), "web": self.cb_web.currentData(),
                                   "version": self.version(), "copie": self.copie.isChecked(),
                                   "au_carnet": self.au_carnet.isChecked()}
        self.params.enregistrer()

    def _mdp(self, c):
        mdp = C.mot_de_passe(c)
        if not mdp:
            from PySide6.QtWidgets import QInputDialog
            mdp, ok = QInputDialog.getText(self, _("Envoyer par e-mail"),
                                           _("Mot de passe de {a} sur ce poste :", a=c["adresse"]), QLineEdit.Password)
            if not ok or not mdp:
                return None
            coffre.enregistrer(C.ident_coffre(c), mdp)
        return mdp

    def valider(self):
        if self.version() == "protege" and not self.mdp.text():
            QMessageBox.information(self, _("Envoyer par e-mail"), _("Indiquez le mot de passe d'ouverture."))
            return
        chemin = self._fichier()
        a, cc, cci = self.a.text(), self.cc.text(), self.cci.text()
        sujet, corps = self.sujet.text(), self.corps.toPlainText()
        if self.r_compte.isChecked():
            c = self.compte()
            direct = self.r_direct.isChecked()
            if direct and not C.adresses(a):
                QMessageBox.information(self, _("Envoyer par e-mail"), _("Indiquez au moins un destinataire."))
                return
            mdp = self._mdp(c)
            if mdp is None:
                return
            self.b_ok.setEnabled(False)
            self.etat.setText(_("Envoi en cours ({t})...", t=_taille(os.path.getsize(chemin))) if direct else
                              _("Dépôt dans vos Brouillons..."))
            QApplication.setOverrideCursor(Qt.WaitCursor)
            if direct:
                copie = self.copie.isChecked()
                f = lambda: C.envoyer(c, mdp, a, cc, sujet, corps, chemin, copie, cci=cci)
            else:
                f = lambda: C.brouillon(c, mdp, a, cc, sujet, corps, chemin, cci=cci)
            self._t = lancer(f, lambda r: self._fini(r, a, c, direct))
            return
        self._retenir()
        if self.r_logiciel.isChecked():
            par = self.f

            def rappel(ok, msg):
                if not ok:
                    QTimer.singleShot(0, par, lambda: QMessageBox.warning(par, _("Envoyer par e-mail"), msg))
            C.par_logiciel(chemin, a, sujet, corps, rappel, cc=cc, cci=cci)
            self._dire(_("Message ouvert dans votre messagerie, PDF joint : relisez puis envoyez."))
        else:
            agenda.ouvrir(agenda.lien_message(self.cb_web.currentData(), sujet, corps, ", ".join(C.adresses(a)),
                                              cc=", ".join(C.adresses(cc)), cci=", ".join(C.adresses(cci))))
            C.montrer_fichier(chemin)
            self._dire(_("Glissez « {f} » (sélectionné dans le dossier ouvert) dans le message.",
                         f=os.path.basename(chemin)))

    def _dire(self, t):
        self.etat.setText("<span style='color:#1e6b34'>✓ " + t + "</span>")
        self.f.statusBar().showMessage(t, 12000)

    def _fini(self, r, a, c, direct):
        QApplication.restoreOverrideCursor()
        self.b_ok.setEnabled(True)
        if isinstance(r, Exception):
            self.etat.setText("<span style='color:#b3261e'>✕ " + C.expliquer(r) + "</span>")
            return
        self._retenir()
        if direct:
            self._dire(_("E-mail envoyé à {a}.", a=", ".join(C.adresses(a))))
        else:
            self._dire(_("Brouillon déposé dans « {d} », PDF joint : ouvrez-le dans votre messagerie et cliquez "
                         "« Envoyer ».", d=r))
            w = C.webmail_de(c)
            if w:
                agenda.ouvrir(w)
