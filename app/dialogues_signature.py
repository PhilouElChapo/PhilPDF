"""Signature numerique : identites, signer, verifier, champs de signature pour d'autres personnes.

Tout est fait pour ressembler a Acrobat (memes champs, meme apparence), en plus simple : une seule fenetre pour signer,
un volet pour voir qui a signe et si le document a change depuis.
"""
import base64
import datetime as _dt
import os

import pymupdf as fitz
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap, QImage, QColor
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QPushButton, QLineEdit,
                               QComboBox, QCheckBox, QListWidget, QListWidgetItem, QTabWidget, QWidget, QFileDialog,
                               QMessageBox, QDialogButtonBox, QTreeWidget, QTreeWidgetItem, QSpinBox, QRadioButton,
                               QButtonGroup, QGroupBox, QFrame, QSizePolicy)

from .langue import _
from .dialogues import boutons_fr, oeil
from .icones import icone
from . import identites as ID
from moteur import signature_num as S

# mots de passe des identites retenus jusqu'a la fermeture de PhilPDF (jamais ecrits)
_RETENUS = {}


def motifs():
    return ["", _("J'approuve ce document"), _("Je suis l'auteur de ce document"), _("J'ai relu ce document"),
            _("Je certifie l'exactitude de ce document"), _("Lu et approuvé")]


def _date(iso):
    try:
        return _dt.datetime.fromisoformat(iso).astimezone().strftime("%d/%m/%Y")
    except (TypeError, ValueError):
        return ""


def libelle_identite(e):
    t = e.get("nom", "?")
    if e.get("email"):
        t += f" <{e['email']}>"
    if e.get("expire"):
        t += "  — " + _("expirée le {d}", d=_date(e.get("fin")))
    elif e.get("fin"):
        t += "  — " + _("valable jusqu'au {d}", d=_date(e.get("fin")))
    if e.get("windows"):
        t += "  — " + _("gardée par Windows sur « {poste} »", poste=e.get("poste", "?"))
    elif not e.get("ici"):
        t += "  — " + _("absente de ce poste")
    return t


def message_erreur(e):
    code = str(e)
    return {"mot_de_passe": _("Mot de passe incorrect pour cette identité."),
            "pas_de_clef": _("Ce fichier ne contient pas de clef de signature (seulement un certificat ?)."),
            "pdf_protege": _("Ce PDF est protégé par un mot de passe : ouvrez-le avec son mot de passe d'abord."),
            "deja_signe": _("Ce champ est déjà signé."),
            "nom_pris": _("Un champ porte déjà ce nom."),
            "nom vide": _("Indiquez un nom."),
            "mot de passe vide": _("Choisissez un mot de passe.")}.get(code, code)


# ================================================================ identites
def _biblio(w):
    while w is not None and not hasattr(w, "biblio"):
        w = w.parent()
    return getattr(w, "biblio", None) if w is not None else None


def index_apparence(c, genre, manuscrite=None):
    """Position de (genre, signature manuscrite) dans une liste d'apparences (-1 si absente)."""
    for i in range(c.count()):
        d = c.itemData(i)
        if d and tuple(d)[0] == (genre or "nom") and (tuple(d)[1] == manuscrite or tuple(d)[0] != "manuscrite"):
            return i
    return -1


def combo_apparence(biblio, genre="nom", manuscrite=None):
    """Apparence de la signature : nom en grand, une de vos signatures manuscrites, ou texte seulement."""
    c = QComboBox()
    c.addItem(_("Mon nom en grand (comme Acrobat)"), ("nom", None))
    for e in (biblio.elements("signatures") if biblio else []):
        c.addItem(icone("signer", "#333"), _("Ma signature manuscrite : {nom}", nom=e["nom"]), ("manuscrite", e["id"]))
    c.addItem(_("Texte seulement"), ("texte", None))
    c.setCurrentIndex(max(0, index_apparence(c, genre, manuscrite)))
    return c


class DialogueReglagesIdentite(QDialog):
    """Indice pour se souvenir du mot de passe, et apparence proposee par defaut pour cette identite."""

    def __init__(self, parent, params, e, titre=None):
        super().__init__(parent)
        self.params, self.e = params, e
        self.setWindowTitle(titre or _("Identité de {nom}", nom=e.get("nom", "")))
        self.setMinimumWidth(460)
        f = QFormLayout(self)
        self.indice = QLineEdit(e.get("indice", ""))
        self.indice.setObjectName("id_indice")
        self.indice.setPlaceholderText(_("une phrase pour vous en souvenir, sans le mot de passe lui-même"))
        f.addRow(_("Indice du mot de passe"), self.indice)
        app_ = e.get("apparence") or {}
        self.apparence = combo_apparence(_biblio(parent), app_.get("genre", "nom"), app_.get("manuscrite"))
        self.apparence.setObjectName("id_apparence")
        f.addRow(_("Apparence par défaut"), self.apparence)
        n = QLabel(_("L'indice est enregistré en clair et suit sur vos autres postes : n'y mettez jamais le mot de passe."))
        n.setWordWrap(True)
        n.setStyleSheet("color:#555")
        f.addRow(n)
        bb = boutons_fr(QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel))
        bb.accepted.connect(self.valider)
        bb.rejected.connect(self.reject)
        f.addRow(bb)

    def valider(self):
        genre, ident = self.apparence.currentData()
        ID.regler(self.params, self.e["id"], indice=self.indice.text().strip(),
                  apparence={"genre": genre, "manuscrite": ident})
        self.accept()


class DialogueCreerIdentite(QDialog):
    """Comme « Ajouter un ID numérique » d'Acrobat : un certificat autosigné a votre nom."""

    def __init__(self, parent, params):
        super().__init__(parent)
        self.params, self.resultat = params, None
        self.setWindowTitle(_("Créer une identité numérique"))
        self.setMinimumWidth(460)
        f = QFormLayout(self)
        intro = QLabel(_("Comme les ID numériques d'Acrobat : un certificat à votre nom, qui sert à signer. Acrobat "
                         "et PhilPDF afficheront votre signature ; vos correspondants peuvent approuver votre "
                         "certificat une fois pour toutes."))
        intro.setWordWrap(True)
        f.addRow(intro)
        self.nom = QLineEdit(params.get("auteur", ""))
        self.org = QLineEdit()
        self.service = QLineEdit()
        self.email = QLineEdit()
        self.pays = QLineEdit("FR")
        self.pays.setMaxLength(2)
        self.pays.setMaximumWidth(50)
        self.duree = QSpinBox()
        self.duree.setRange(1, 20)
        self.duree.setValue(5)
        self.duree.setSuffix(" " + _("ans"))
        self.mdp = oeil(QLineEdit())
        self.mdp2 = oeil(QLineEdit())
        f.addRow(_("Nom"), self.nom)
        f.addRow(_("Organisation (facultatif)"), self.org)
        f.addRow(_("Service (facultatif)"), self.service)
        f.addRow(_("Adresse e-mail"), self.email)
        f.addRow(_("Pays"), self.pays)
        f.addRow(_("Validité"), self.duree)
        f.addRow(_("Mot de passe de l'identité"), self.mdp)
        f.addRow(_("Confirmer le mot de passe"), self.mdp2)
        self.indice = QLineEdit()
        self.indice.setObjectName("cree_indice")
        self.indice.setPlaceholderText(_("une phrase pour vous en souvenir, sans le mot de passe lui-même"))
        f.addRow(_("Indice du mot de passe"), self.indice)
        self.apparence = combo_apparence(_biblio(parent))
        self.apparence.setObjectName("cree_apparence")
        if self.apparence.count() > 2:                    # une signature manuscrite existe : proposee d'office
            self.apparence.setCurrentIndex(1)
        f.addRow(_("Apparence par défaut"), self.apparence)
        n = QLabel(_("Ce mot de passe vous sera demandé à chaque signature. Il ne peut pas être retrouvé : notez-le."))
        n.setWordWrap(True)
        n.setStyleSheet("color:#555")
        f.addRow(n)
        bb = boutons_fr(QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel))
        bb.button(QDialogButtonBox.Ok).setText(_("Créer"))
        bb.accepted.connect(self.creer)
        bb.rejected.connect(self.reject)
        f.addRow(bb)

    def creer(self):
        if not self.nom.text().strip():
            QMessageBox.warning(self, self.windowTitle(), _("Indiquez un nom."))
            return
        if len(self.mdp.text()) < 6:
            QMessageBox.warning(self, self.windowTitle(), _("Mot de passe trop court (6 caractères au moins)."))
            return
        if self.mdp.text() != self.mdp2.text():
            QMessageBox.warning(self, self.windowTitle(), _("Les deux mots de passe ne sont pas identiques."))
            return
        try:
            self.resultat = ID.creer(self.params, self.nom.text(), self.mdp.text(), self.org.text(),
                                     self.service.text(), self.email.text(), self.pays.text() or "FR",
                                     self.duree.value())
            genre, ident = self.apparence.currentData()
            ID.regler(self.params, self.resultat["id"], indice=self.indice.text().strip(),
                      apparence={"genre": genre, "manuscrite": ident})
            self.resultat = next(x for x in ID.liste(self.params) if x["id"] == self.resultat["id"])
        except Exception as e:                            # noqa: BLE001
            QMessageBox.warning(self, self.windowTitle(), message_erreur(e))
            return
        self.accept()


class DialogueSourcesID(QDialog):
    """Les identites deja sur ce PC : fichiers d'ID d'Acrobat (.pfx) et ID du magasin Windows ; ou un autre fichier."""

    def __init__(self, parent):
        super().__init__(parent)
        from . import identites_systeme as IS
        self.setWindowTitle(_("Importer mon ID numérique"))
        self.resize(640, 380)
        v = QVBoxLayout(self)
        n = QLabel(_("Les ID numériques trouvés sur ce PC. Le bouton « Exporter » d'Acrobat ne donne que le certificat "
                     "(.fdf, .p7c, .cer), sans la clef qui permet de signer : PhilPDF reprend directement le fichier "
                     "d'ID d'Acrobat, ou exporte l'ID du magasin Windows."))
        n.setWordWrap(True)
        v.addWidget(n)
        self.liste = QListWidget()
        self.liste.setObjectName("sources_id")
        for f, quand in IS.fichiers_acrobat():
            it = QListWidgetItem(icone("certificat", "#0f6cbd"),
                                 _("Fichier d'ID d'Acrobat : {nom}  (modifié le {d})", nom=os.path.basename(f),
                                   d=quand.strftime("%d/%m/%Y")) + "\n" + f)
            it.setData(Qt.UserRole, ("fichier", f))
            self.liste.addItem(it)
        for w in IS.windows_identites():
            fin = _date(w["fin"])
            it = QListWidgetItem(icone("certificat", "#2e7d32"),
                                 _("Magasin Windows : {nom}  (émis par {e}, valable jusqu'au {d})", nom=w["nom"] or w["sujet"],
                                   e=w["emetteur"], d=fin) + "\n" + w["sujet"])
            it.setData(Qt.UserRole, ("windows", w))
            self.liste.addItem(it)
        if not self.liste.count():
            it = QListWidgetItem(_("Aucun ID trouvé automatiquement : choisissez un fichier .pfx ci-dessous."))
            it.setFlags(Qt.NoItemFlags)
            self.liste.addItem(it)
        else:
            self.liste.setCurrentRow(0)
        self.liste.itemDoubleClicked.connect(lambda _i: self.accept())
        v.addWidget(self.liste, 1)
        h = QHBoxLayout()
        b = QPushButton(_("Autre fichier .pfx..."))
        b.clicked.connect(self.autre)
        h.addWidget(b)
        h.addStretch(1)
        bb = boutons_fr(QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel))
        bb.button(QDialogButtonBox.Ok).setText(_("Importer"))
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        h.addWidget(bb)
        v.addLayout(h)
        self.choix = None

    def autre(self):
        f, _x = QFileDialog.getOpenFileName(self, _("Importer une identité numérique"), "",
                                            _("Identités numériques (*.pfx *.p12)"))
        if f:
            self.choix = ("fichier", f)
            super().accept()

    def accept(self):
        it = self.liste.currentItem()
        if it is not None and it.data(Qt.UserRole):
            self.choix = it.data(Qt.UserRole)
            super().accept()


def importer_pfx(parent, params, source=None):
    """Importe une identite : fichier d'ID d'Acrobat, ID du magasin Windows, ou autre .pfx. Renvoie l'entree ou None."""
    if source is None:
        d = DialogueSourcesID(parent)
        if d.exec() != QDialog.Accepted or not d.choix:
            return None
        source = d.choix
    if source[0] == "windows":
        return _importer_windows(parent, params, source[1])
    f = source[1]
    with open(f, "rb") as h:
        octets = h.read()
    from .dialogues import demander_secret
    while True:
        mdp, ok = demander_secret(parent, _("Importer une identité numérique"),
                                  _("Mot de passe de « {f} » :", f=os.path.basename(f)))
        if not ok:
            return None
        try:
            e = ID.ajouter_pfx(params, octets, mdp, origine="acrobat")
        except S.ErreurSignature as ex:
            QMessageBox.warning(parent, _("Importer une identité numérique"), message_erreur(ex))
            if str(ex) == "mot_de_passe":
                continue
            return None
        _ecrire_secrets(parent)
        QMessageBox.information(parent, _("Importer une identité numérique"),
                                _("Identité de {nom} ajoutée.", nom=e.get("nom")) +
                                ("\n" + _("Attention : elle a expiré le {d}.", d=_date(e.get("fin"))) if e.get("expire") else ""))
        return e


def _importer_windows(parent, params, w):
    """ID du magasin Windows : exporte en .pfx avec un mot de passe choisi pour PhilPDF, puis importe."""
    from . import identites_systeme as IS
    d = QDialog(parent)
    d.setWindowTitle(_("Importer mon ID numérique"))
    f = QFormLayout(d)
    l = QLabel(_("Choisissez le mot de passe de cet ID dans PhilPDF (il sera demandé à chaque signature) :"))
    l.setWordWrap(True)
    f.addRow(l)
    m1, m2 = oeil(QLineEdit()), oeil(QLineEdit())
    f.addRow(_("Mot de passe"), m1)
    f.addRow(_("Confirmer le mot de passe"), m2)
    bb = boutons_fr(QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel))
    bb.accepted.connect(d.accept)
    bb.rejected.connect(d.reject)
    f.addRow(bb)
    while True:
        if d.exec() != QDialog.Accepted:
            return None
        if len(m1.text()) < 6:
            QMessageBox.warning(parent, d.windowTitle(), _("Mot de passe trop court (6 caractères au moins)."))
        elif m1.text() != m2.text():
            QMessageBox.warning(parent, d.windowTitle(), _("Les deux mots de passe ne sont pas identiques."))
        else:
            break
    try:
        octets = IS.windows_exporter(w["empreinte"], m1.text())
        e = ID.ajouter_pfx(params, octets, m1.text(), origine="windows")
        _ecrire_secrets(parent)
    except Exception as ex:                               # noqa: BLE001
        # clef « non exportable » (cas des ID crees par Acrobat dans Windows) : Windows signera lui-meme
        if not w.get("der"):
            QMessageBox.warning(parent, d.windowTitle(), _("Windows refuse d'exporter cet ID ({e}).", e=ex))
            return None
        e = ID.ajouter_windows(params, w)
        QMessageBox.information(parent, d.windowTitle(),
                                _("La clef de cet ID ne peut pas sortir de Windows : PhilPDF demandera à Windows de "
                                  "signer, sans mot de passe PhilPDF. Il sert donc sur ce PC seulement ; sur vos autres "
                                  "postes, importez-y le même ID, ou créez une identité PhilPDF (elle, synchronisée)."))
    QMessageBox.information(parent, d.windowTitle(), _("Identité de {nom} ajoutée.", nom=e.get("nom")) +
                            ("\n" + _("Attention : elle a expiré le {d}.", d=_date(e.get("fin"))) if e.get("expire") else ""))
    return e


def _ecrire_secrets(w):
    """Envoie l'identite (chiffree) sur le Drive, avec les autres mots de passe, si la synchro est active."""
    while w is not None and not hasattr(w, "_ecrire_secrets"):
        w = w.parent()
    if w is not None:
        QTimer.singleShot(0, w._ecrire_secrets)


def aide_acrobat():
    return ("<b>" + _("Reprendre votre ID numérique d'Acrobat") + "</b><br>" +
            _("Cliquez sur « Importer mon ID d'Acrobat... » : PhilPDF trouve tout seul les fichiers d'ID d'Acrobat "
              "et les ID du magasin Windows de ce PC. Il vous demande ensuite le mot de passe de l'ID, le même "
              "que dans Acrobat. (Le bouton « Exporter » d'Acrobat ne donne que le certificat, sans la clef : "
              "inutile ici.)"))


class DialogueIdentites(QDialog):
    """Mes identités numériques et les certificats que j'approuve."""

    def __init__(self, parent, params):
        super().__init__(parent)
        self.params = params
        self.setWindowTitle(_("Signature numérique : mes identités"))
        self.resize(720, 460)
        v = QVBoxLayout(self)
        self.onglets = QTabWidget()
        v.addWidget(self.onglets)
        # --- mes identites
        w = QWidget()
        lv = QVBoxLayout(w)
        self.liste = QListWidget()
        self.liste.setObjectName("liste_identites")
        self.liste.currentRowChanged.connect(lambda _r: self._etat())
        lv.addWidget(self.liste, 1)
        aide = QLabel(aide_acrobat())
        aide.setWordWrap(True)
        aide.setStyleSheet("color:#444;background:#f4f7fb;border:1px solid #dbe4f0;border-radius:6px;padding:8px")
        aide.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lv.addWidget(aide)
        h = QHBoxLayout()
        for txt, f, nom in ((_("Importer mon ID d'Acrobat..."), self.importer, "imp"), (_("Créer..."), self.creer, "creer"),
                            (_("Par défaut"), self.defaut, "defaut"), (_("Indice, apparence..."), self.regler, "regler"),
                            (_("Exporter le certificat (.cer)..."), self.exporter_cer, "cer"),
                            (_("Exporter l'identité (.pfx)..."), self.exporter_pfx, "pfx"),
                            (_("Supprimer"), self.supprimer, "suppr")):
            b = QPushButton(txt)
            b.setObjectName("id_" + nom)
            b.clicked.connect(f)
            h.addWidget(b)
            setattr(self, "b_" + nom, b)
        h.addStretch(1)
        lv.addLayout(h)
        self.onglets.addTab(w, icone("certificat", "#0f6cbd"), _("Mes identités"))
        # --- certificats approuves
        w = QWidget()
        lv = QVBoxLayout(w)
        n = QLabel(_("Les signatures faites avec ces certificats sont affichées comme « approuvées ». Ajoutez ceux de vos "
                     "correspondants (fichier .cer qu'ils vous envoient, ou depuis une signature reçue, volet "
                     "Signatures). Ils suivent sur vos autres postes."))
        n.setWordWrap(True)
        lv.addWidget(n)
        self.certs = QListWidget()
        self.certs.setObjectName("liste_certificats")
        lv.addWidget(self.certs, 1)
        h = QHBoxLayout()
        b = QPushButton(_("Importer un certificat (.cer)..."))
        b.clicked.connect(self.importer_cer)
        h.addWidget(b)
        b = QPushButton(_("Retirer"))
        b.clicked.connect(self.retirer_cer)
        h.addWidget(b)
        h.addStretch(1)
        lv.addLayout(h)
        self.onglets.addTab(w, icone("valide", "#2e7d32"), _("Certificats approuvés"))
        bb = boutons_fr(QDialogButtonBox(QDialogButtonBox.Close))
        bb.rejected.connect(self.accept)
        v.addWidget(bb)
        self.rafraichir()

    def rafraichir(self, choisir=None):
        self.liste.clear()
        for e in ID.liste(self.params):
            it = QListWidgetItem(icone("certificat", "#b00020" if e["expire"] else "#0f6cbd"),
                                 ("★ " if e.get("defaut") else "") + libelle_identite(e))
            it.setData(Qt.UserRole, e)
            it.setToolTip(_("Emis par : {x}", x=e.get("emetteur", "")) + "\n" + _("Empreinte SHA-256 : {x}", x=e.get("empreinte", "")))
            if not e["ici"]:
                it.setForeground(QColor("#888"))
            self.liste.addItem(it)
            if choisir and e["id"] == choisir.get("id"):
                self.liste.setCurrentItem(it)
        if self.liste.currentRow() < 0 and self.liste.count():
            self.liste.setCurrentRow(0)
        self.certs.clear()
        for c in ID.approuves(self.params):
            t = c.get("nom", "?") + (f" <{c['email']}>" if c.get("email") else "")
            if c.get("soi"):
                t += "  — " + _("vous")
            it = QListWidgetItem(icone("valide", "#2e7d32"), t)
            it.setData(Qt.UserRole, c)
            it.setToolTip(_("Empreinte SHA-256 : {x}", x=c.get("empreinte", "")))
            self.certs.addItem(it)
        self._etat()

    def _choisie(self):
        it = self.liste.currentItem()
        return it.data(Qt.UserRole) if it else None

    def _etat(self):
        e = self._choisie()
        for b in (self.b_defaut, self.b_regler, self.b_cer, self.b_pfx, self.b_suppr):
            b.setEnabled(e is not None)
        if e is not None:
            self.b_cer.setEnabled(e["ici"] or bool(e.get("der")))
            self.b_pfx.setEnabled(e["ici"] and not e.get("windows"))

    def importer(self):
        e = importer_pfx(self, self.params)
        if e:
            DialogueReglagesIdentite(self, self.params, e, _("Réglages de l'identité importée")).exec()
            self.rafraichir(e)

    def regler(self):
        e = self._choisie()
        if e and DialogueReglagesIdentite(self, self.params, e).exec() == QDialog.Accepted:
            self.rafraichir(e)

    def creer(self):
        d = DialogueCreerIdentite(self, self.params)
        if d.exec() == QDialog.Accepted and d.resultat:
            _ecrire_secrets(self.parent())
            self.rafraichir(d.resultat)

    def defaut(self):
        e = self._choisie()
        if e:
            ID.definir_defaut(self.params, e["id"])
            self.rafraichir(e)

    def _mdp(self, e):
        from .dialogues import demander_secret
        mdp, ok = demander_secret(self, _("Identité numérique"), _("Mot de passe de l'identité « {nom} » :", nom=e["nom"]),
                                  indice=e.get("indice", ""))
        if not ok:
            return None
        try:
            S.ouvrir_pfx(ID.lire(e), mdp)
        except S.ErreurSignature as ex:
            QMessageBox.warning(self, _("Identité numérique"), message_erreur(ex))
            return None
        return mdp

    def exporter_cer(self):
        e = self._choisie()
        if not e:
            return
        f, _x = QFileDialog.getSaveFileName(self, _("Exporter le certificat"), e["nom"] + ".cer", _("Certificat (*.cer)"))
        if not f:
            return
        if e.get("der"):
            import base64
            cer = base64.b64decode(e["der"])
        else:
            mdp = self._mdp(e)
            if mdp is None:
                return
            cer = S.exporter_cer(ID.lire(e), mdp)
        with open(f, "wb") as h:
            h.write(cer)
        QMessageBox.information(self, _("Exporter le certificat"),
                                _("Envoyez ce fichier à vos correspondants : dans Acrobat, Edition › Préférences › "
                                  "Signatures › Identités et certificats approuvés › Certificats approuvés › Importer ; "
                                  "dans PhilPDF, Certificats approuvés › Importer. Il ne contient pas votre clef : il ne "
                                  "permet pas de signer à votre place."))

    def exporter_pfx(self):
        e = self._choisie()
        if not e:
            return
        f, _x = QFileDialog.getSaveFileName(self, _("Exporter l'identité"), e["nom"] + ".pfx", _("Identité numérique (*.pfx)"))
        if not f:
            return
        if self._mdp(e) is None:
            return
        with open(f, "wb") as h:
            h.write(ID.lire(e))
        QMessageBox.information(self, _("Exporter l'identité"),
                                _("Fichier protégé par le même mot de passe. Il s'importe dans Acrobat (Ajouter un ID "
                                  "numérique › Mon ID numérique existant › Un fichier). Gardez-le pour vous : il permet "
                                  "de signer à votre nom."))

    def supprimer(self):
        e = self._choisie()
        if not e:
            return
        if QMessageBox.question(self, _("Supprimer"), _("Supprimer l'identité de {nom} de PhilPDF (sur tous vos postes) ?\n\n"
                                                        "Les documents déjà signés restent valides.", nom=e["nom"])) != QMessageBox.Yes:
            return
        ID.supprimer(self.params, e["id"])
        self.rafraichir()

    def importer_cer(self):
        f, _x = QFileDialog.getOpenFileName(self, _("Importer un certificat"), "", _("Certificats (*.cer *.crt *.pem *.der)"))
        if not f:
            return
        try:
            with open(f, "rb") as h:
                ID.approuver(self.params, h.read())
        except Exception as e:                            # noqa: BLE001
            QMessageBox.warning(self, _("Importer un certificat"), _("Certificat illisible : {e}", e=e))
            return
        self.rafraichir()

    def retirer_cer(self):
        it = self.certs.currentItem()
        if it:
            ID.retirer(self.params, it.data(Qt.UserRole)["empreinte"])
            self.rafraichir()


# ================================================================ signer
def png_signature(biblio, e, hauteur=240):
    """Signature manuscrite de la bibliotheque -> PNG transparent."""
    try:
        d = fitz.open("pdf", biblio.lire(e))
        p = d[0]
        k = hauteur / max(p.rect.height, 1)
        return p.get_pixmap(matrix=fitz.Matrix(k, k), alpha=True).tobytes("png")
    except Exception:                                     # noqa: BLE001
        return None


class DialogueSigner(QDialog):
    """Une seule fenetre pour signer : identite, mot de passe, apparence (apercu), motif, lieu, certification."""

    def __init__(self, onglet, champ, rect, page, infos_champ=None, premiere=True):
        super().__init__(onglet)
        self.o, self.params, self.biblio = onglet, onglet.params, onglet.biblio
        self.champ, self.rect, self.page = champ, rect, page
        self.setWindowTitle(_("Signer avec une identité numérique"))
        self.setMinimumWidth(560)
        reg = dict(self.params.get("signature_reglages") or {})
        v = QVBoxLayout(self)
        f = QFormLayout()
        v.addLayout(f)
        hi = QHBoxLayout()
        self.identite = QComboBox()
        self.identite.setObjectName("sig_identite")
        hi.addWidget(self.identite, 1)
        b = QPushButton(_("Gérer..."))
        b.clicked.connect(self.gerer)
        hi.addWidget(b)
        f.addRow(_("Signer en tant que"), hi)
        self.mdp = oeil(QLineEdit())
        self.mdp.setObjectName("sig_mdp")
        f.addRow(_("Mot de passe de l'identité"), self.mdp)
        self.lbl_indice = QLabel()
        self.lbl_indice.setObjectName("sig_indice")
        self.lbl_indice.setStyleSheet("color:#555")
        self.lbl_indice.setWordWrap(True)
        f.addRow("", self.lbl_indice)
        self.retenir = QCheckBox(_("Retenir jusqu'à la fermeture de PhilPDF"))
        self.retenir.setChecked(bool(reg.get("retenir", False)))
        f.addRow("", self.retenir)
        self.apparence = QComboBox()
        self.apparence.setObjectName("sig_apparence")
        self.apparence.addItem(_("Mon nom en grand (comme Acrobat)"), ("nom", None))
        for e in (self.biblio.elements("signatures") if self.biblio else []):
            self.apparence.addItem(icone("signer", "#333"), _("Ma signature manuscrite : {nom}", nom=e["nom"]), ("manuscrite", e["id"]))
        self.apparence.addItem(_("Texte seulement"), ("texte", None))
        self.apparence.setCurrentIndex(max(0, index_apparence(self.apparence, reg.get("apparence", "nom"), reg.get("manuscrite"))))
        f.addRow(_("Apparence"), self.apparence)
        self.motif = QComboBox()
        self.motif.setEditable(True)
        self.motif.addItems(motifs())
        self.motif.setCurrentText(reg.get("motif", ""))
        f.addRow(_("Motif (facultatif)"), self.motif)
        self.lieu = QLineEdit(reg.get("lieu", ""))
        f.addRow(_("Lieu (facultatif)"), self.lieu)
        hm = QHBoxLayout()
        self.v_date = QCheckBox(_("la date"))
        self.v_date.setChecked(reg.get("date", True))
        self.v_motif = QCheckBox(_("le motif"))
        self.v_motif.setChecked(reg.get("v_motif", True))
        self.v_lieu = QCheckBox(_("le lieu"))
        self.v_lieu.setChecked(reg.get("v_lieu", True))
        for c in (self.v_date, self.v_motif, self.v_lieu):
            hm.addWidget(c)
        hm.addStretch(1)
        f.addRow(_("Afficher"), hm)
        self.apercu = QLabel()
        self.apercu.setObjectName("sig_apercu")
        self.apercu.setMinimumHeight(90)
        self.apercu.setAlignment(Qt.AlignCenter)
        self.apercu.setStyleSheet("background:white;border:1px solid #cfd6e0;border-radius:4px")
        f.addRow(_("Aperçu"), self.apercu)
        self.certifier = QCheckBox(_("Certifier le document (vous êtes le premier signataire)"))
        self.certifier.setObjectName("sig_certifier")
        self.permis = QComboBox()
        self.permis.addItem(_("Ensuite : aucune modification permise"), "rien")
        self.permis.addItem(_("Ensuite : remplir les formulaires et signer"), "formulaires")
        self.permis.addItem(_("Ensuite : remplir, signer et commenter"), "annotations")
        self.permis.setCurrentIndex(1)
        self.permis.setEnabled(False)
        self.certifier.toggled.connect(self.permis.setEnabled)
        if premiere:
            f.addRow("", self.certifier)
            f.addRow("", self.permis)
        else:
            self.certifier.hide()
            self.permis.hide()
        self.horodatage = QCheckBox(_("Horodater par Internet (si disponible)"))
        self.horodatage.setChecked(reg.get("horodatage", True))
        self.horodatage.setToolTip(_("Un serveur gratuit atteste l'heure de la signature : elle reste prouvable même "
                                     "après l'expiration de votre certificat."))
        f.addRow("", self.horodatage)
        for t in (infos_champ or []):
            l = QLabel(t)
            l.setWordWrap(True)
            l.setStyleSheet("color:#7a4a00")
            v.addWidget(l)
        bb = boutons_fr(QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel))
        self.b_signer = bb.button(QDialogButtonBox.Ok)
        self.b_signer.setText(_("Signer..."))
        bb.accepted.connect(self.valider)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        self.remplir_identites()
        for sig in (self.identite.currentIndexChanged, self.apparence.currentIndexChanged, self.motif.currentTextChanged,
                    self.lieu.textChanged, self.v_date.toggled, self.v_motif.toggled, self.v_lieu.toggled):
            sig.connect(self.maj_apercu)
        self.identite.currentIndexChanged.connect(self._mdp_retenu)
        self.maj_apercu()
        self._mdp_retenu()
        self.resultat = None

    def remplir_identites(self, choisir=None):
        self.identite.blockSignals(True)
        self.identite.clear()
        defaut = choisir or ID.par_defaut(self.params)
        for e in ID.liste(self.params):
            if not e["ici"]:
                continue
            self.identite.addItem(icone("certificat", "#b00020" if e["expire"] else "#0f6cbd"), libelle_identite(e), e)
            if defaut and e["id"] == defaut["id"]:
                self.identite.setCurrentIndex(self.identite.count() - 1)
        if not self.identite.count():
            self.identite.addItem(_("Aucune identité : importez votre ID d'Acrobat ou créez-en une (Gérer...)"), None)
        self.identite.blockSignals(False)
        self.b_signer.setEnabled(self.identite.currentData() is not None) if hasattr(self, "b_signer") else None

    def _mdp_retenu(self, *_a):
        e = self.identite.currentData()
        indice = (e or {}).get("indice", "")
        self.lbl_indice.setText(_("Indice : {x}", x=indice) if indice else "")
        self.lbl_indice.setVisible(bool(indice))
        app_ = (e or {}).get("apparence")
        if app_ and hasattr(self, "apparence"):
            i = index_apparence(self.apparence, app_.get("genre") or "nom", app_.get("manuscrite"))
            if i >= 0:
                self.apparence.setCurrentIndex(i)
        win = bool(e and e.get("windows") and not ID.lire(e))
        self.mdp.setEnabled(not win)
        self.mdp.setPlaceholderText(_("pas de mot de passe : Windows signe (il peut demander le sien)") if win else "")
        if e and e["id"] in _RETENUS:
            self.mdp.setText(_RETENUS[e["id"]])
        if hasattr(self, "b_signer"):
            self.b_signer.setEnabled(e is not None)

    def gerer(self):
        d = DialogueIdentites(self, self.params)
        d.exec()
        self.remplir_identites()
        self.maj_apercu()
        self._mdp_retenu()

    def _nom(self):
        e = self.identite.currentData()
        return (e or {}).get("nom") or self.params.get("auteur", "") or _("Votre nom")

    def reglages_apparence(self):
        genre, ident = self.apparence.currentData() or ("nom", None)
        nom = self._nom()
        lignes = S.lignes_apparence(nom, motif=self.motif.currentText().strip() if self.v_motif.isChecked() else "",
                                    lieu=self.lieu.text().strip() if self.v_lieu.isChecked() else "",
                                    date=self.v_date.isChecked(),
                                    libelles={"entete": _("Signature numérique de"), "date": _("Date : {x}"),
                                              "motif": _("Motif : {x}"), "lieu": _("Lieu : {x}")})
        png = None
        if genre == "manuscrite" and self.biblio:
            e = next((x for x in self.biblio.elements("signatures") if x["id"] == ident), None)
            png = png_signature(self.biblio, e) if e else None
        return nom, png, lignes, genre

    def maj_apercu(self, *_a):
        nom, png, lignes, genre = self.reglages_apparence()
        r = self.rect or fitz.Rect(0, 0, 180, 45)
        try:
            chemin = S.apparence_pdf(r.width, r.height, "" if genre == "texte" else nom, png, lignes)
            d = fitz.open(chemin)
            k = min(360 / r.width, 96 / r.height)
            pm = d[0].get_pixmap(matrix=fitz.Matrix(k, k), alpha=False)
            img = QImage(pm.samples, pm.width, pm.height, pm.stride, QImage.Format_RGB888).copy()
            d.close()
            os.remove(chemin)
            self.apercu.setPixmap(QPixmap.fromImage(img))
        except Exception as e:                            # noqa: BLE001
            self.apercu.setText(str(e))

    def valider(self):
        e = self.identite.currentData()
        if not e:
            return
        pfx = ID.lire(e)
        signataire = None
        if e.get("windows") and not pfx:                  # clef gardee par Windows : il signe lui-meme
            import base64
            from . import identites_systeme as IS
            signataire = S.signataire_windows(base64.b64decode(e["der"]),
                                              lambda donnees, t=e["windows"]: IS.windows_signer(t, donnees))
        else:
            try:
                S.ouvrir_pfx(pfx, self.mdp.text())
            except S.ErreurSignature as ex:
                QMessageBox.warning(self, self.windowTitle(), message_erreur(ex))
                self.mdp.setFocus()
                self.mdp.selectAll()
                return
        if e.get("expire") and QMessageBox.question(
                self, self.windowTitle(), _("Cette identité a expiré le {d} : Acrobat signalera la signature comme "
                                            "faite avec un certificat expiré. Signer quand même ?", d=_date(e.get("fin")))) != QMessageBox.Yes:
            return
        if self.retenir.isChecked():
            _RETENUS[e["id"]] = self.mdp.text()
        else:
            _RETENUS.pop(e["id"], None)
        genre, ident = self.apparence.currentData() or ("nom", None)
        self.params["signature_reglages"] = {"apparence": genre, "manuscrite": ident, "motif": self.motif.currentText().strip(),
                                             "lieu": self.lieu.text().strip(), "date": self.v_date.isChecked(),
                                             "v_motif": self.v_motif.isChecked(), "v_lieu": self.v_lieu.isChecked(),
                                             "horodatage": self.horodatage.isChecked(), "retenir": self.retenir.isChecked()}
        self.params.enregistrer()
        nom, png, lignes, genre = self.reglages_apparence()
        self.resultat = {"pfx": pfx, "mdp": self.mdp.text(), "identite": e, "signataire": signataire, "nom": nom, "png": png, "lignes": lignes,
                         "genre": genre, "motif": self.motif.currentText().strip(), "lieu": self.lieu.text().strip(),
                         "certifier": self.permis.currentData() if self.certifier.isChecked() else None,
                         "horodatage": self.horodatage.isChecked()}
        self.accept()


# ================================================================ champ de signature (pour quelqu'un d'autre)
class DialogueChampSignature(QDialog):
    """Proprietes d'un champ de signature : nom, signataire prevu, ordre, champs verrouilles a la signature."""

    def __init__(self, parent, nom, autres_champs, signataire="", ordre=0, verrou=("aucun", [])):
        super().__init__(parent)
        self.setWindowTitle(_("Champ de signature"))
        self.setMinimumWidth(480)
        v = QVBoxLayout(self)
        f = QFormLayout()
        v.addLayout(f)
        self.nom = QLineEdit(nom)
        self.nom.setObjectName("cs_nom")
        f.addRow(_("Nom du champ"), self.nom)
        self.signataire = QLineEdit(signataire)
        self.signataire.setObjectName("cs_signataire")
        self.signataire.setPlaceholderText(_("ex. le client, le directeur..."))
        f.addRow(_("A signer par (facultatif)"), self.signataire)
        self.ordre = QSpinBox()
        self.ordre.setObjectName("cs_ordre")
        self.ordre.setRange(0, 20)
        self.ordre.setSpecialValueText(_("indifférent"))
        self.ordre.setValue(ordre)
        self.ordre.setToolTip(_("PhilPDF prévient si quelqu'un signe avant le signataire précédent."))
        f.addRow(_("Ordre de signature"), self.ordre)
        g = QGroupBox(_("Quand ce champ est signé, verrouiller"))
        gv = QVBoxLayout(g)
        self.modes = QButtonGroup(self)
        for i, (m, t) in enumerate((("aucun", _("rien")), ("tous", _("tous les champs du formulaire")),
                                    ("ceux", _("seulement les champs cochés")),
                                    ("tous_sauf", _("tous les champs sauf ceux cochés")))):
            r = QRadioButton(t)
            r.setObjectName("cs_verrou_" + m)
            r.setProperty("mode", m)
            self.modes.addButton(r, i)
            gv.addWidget(r)
            if m == (verrou[0] or "aucun"):
                r.setChecked(True)
        self.champs = QListWidget()
        self.champs.setObjectName("cs_champs")
        self.champs.setMaximumHeight(160)
        for n in autres_champs:
            it = QListWidgetItem(n)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if n in (verrou[1] or []) else Qt.Unchecked)
            self.champs.addItem(it)
        gv.addWidget(self.champs)
        v.addWidget(g)
        self.modes.buttonToggled.connect(lambda *_a: self.champs.setEnabled(self.mode() in ("ceux", "tous_sauf")))
        self.champs.setEnabled(self.mode() in ("ceux", "tous_sauf"))
        n = QLabel(_("Acrobat respecte ce verrouillage : après la signature, les champs verrouillés ne peuvent plus être "
                     "modifiés sans invalider la signature."))
        n.setWordWrap(True)
        n.setStyleSheet("color:#555")
        v.addWidget(n)
        bb = boutons_fr(QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel))
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def mode(self):
        b = self.modes.checkedButton()
        return b.property("mode") if b else "aucun"

    def valeurs(self):
        coches = [self.champs.item(i).text() for i in range(self.champs.count())
                  if self.champs.item(i).checkState() == Qt.Checked]
        return {"nom": self.nom.text().strip(), "signataire": self.signataire.text().strip(),
                "ordre": self.ordre.value(), "verrou": (self.mode(), coches)}


# ================================================================ verifier
def etat_signature(s):
    """(couleur, icone, texte court) d'une signature verifiee."""
    if s.get("erreur") and not s.get("intacte"):
        return "#b00020", "erreur", _("Signature illisible")
    if not s.get("intacte"):
        return "#b00020", "erreur", _("Non valide : le document a été modifié autrement que par un ajout")
    if not s.get("approuve"):
        return "#b26a00", "attention", _("Valide ; identité du signataire non vérifiée (certificat non approuvé)")
    return "#2e7d32", "valide", _("Valide, signataire approuvé")


def resume(signatures, vides):
    """Texte du bandeau, et sa couleur."""
    if not signatures:
        if vides:
            return _("{n} champ(s) de signature à signer. Cliquez sur un champ pour signer.", n=len(vides)), "#e8f1fb"
        return "", None
    mauvaises = [s for s in signatures if not s.get("intacte")]
    if mauvaises:
        t = _("Au moins une signature n'est pas valide ({n} sur {total}).", n=len(mauvaises), total=len(signatures))
        couleur = "#fdecea"
    elif any(not s.get("approuve") for s in signatures):
        t = _("Signé : {n} signature(s) valide(s) ; identité d'au moins un signataire non vérifiée.", n=len(signatures))
        couleur = "#fff4e0"
    else:
        t = _("Signé : toutes les signatures sont valides ({n}).", n=len(signatures))
        couleur = "#e6f4ea"
    if vides:
        t += " " + _("Reste à signer : {n} champ(s).", n=len(vides))
    return t, couleur


class DialogueSignatures(QDialog):
    """Volet Signatures d'Acrobat : qui a signe, quand, si c'est intact, si le certificat est approuve."""

    def __init__(self, onglet, signatures, vides):
        super().__init__(onglet)
        self.o, self.params = onglet, onglet.params
        self.setWindowTitle(_("Signatures"))
        self.resize(700, 460)
        v = QVBoxLayout(self)
        self.arbre = QTreeWidget()
        self.arbre.setObjectName("arbre_signatures")
        self.arbre.setHeaderHidden(True)
        v.addWidget(self.arbre, 1)
        for i, s in enumerate(signatures, 1):
            coul, ic, txt = etat_signature(s)
            quand = s["date"].astimezone().strftime("%d/%m/%Y %H:%M") if s.get("date") else "?"
            it = QTreeWidgetItem([_("Rév. {i} : signé par {nom} le {d}", i=i, nom=s.get("nom") or "?", d=quand)])
            it.setIcon(0, icone(ic, coul))
            it.setData(0, Qt.UserRole, s)
            self.arbre.addTopLevelItem(it)
            for t in [txt,
                      _("Champ : {x}", x=s.get("champ")),
                      _("Motif : {x}", x=s["raison"]) if s.get("raison") else None,
                      _("Lieu : {x}", x=s["lieu"]) if s.get("lieu") else None,
                      _("Heure attestée par un serveur d'horodatage") if s.get("horodatee") else _("Heure de l'ordinateur du signataire (pas d'horodatage)"),
                      (_("Signature de certification : ensuite permis = {x}", x={"rien": _("aucune modification"),
                                                                                 "formulaires": _("remplir et signer"),
                                                                                 "annotations": _("remplir, signer, commenter")}.get(s["certification"], "?"))
                       if s.get("certification") else None),
                      _("Après cette signature : {x}", x={"aucune": _("aucune modification"),
                                                          "formulaires": _("remplissage de formulaire ou autres signatures"),
                                                          "annotations": _("commentaires ajoutés"),
                                                          "autres": _("d'autres modifications (enregistrées en ajout, la signature reste valide)")}.get(s.get("modifs"), "?")),
                      _("Certificat : {nom}, émis par {e}{auto}", nom=s.get("nom"), e=s.get("emetteur"),
                        auto=" (" + _("autosigné, comme les ID numériques d'Acrobat") + ")" if s.get("autosigne") else ""),
                      _("Empreinte SHA-256 : {x}", x=s.get("empreinte"))]:
                if t:
                    QTreeWidgetItem(it, [t])
            it.setExpanded(i == len(signatures))
        for nom in vides:
            it = QTreeWidgetItem([_("Champ « {x} » : pas encore signé", x=nom)])
            it.setIcon(0, icone("champ_signature", "#1462c2"))
            it.setData(0, Qt.UserRole, {"vide": nom})
            self.arbre.addTopLevelItem(it)
        h = QHBoxLayout()
        self.b_approuver = QPushButton(_("Approuver ce certificat"))
        self.b_approuver.setObjectName("sig_approuver")
        self.b_approuver.clicked.connect(self.approuver)
        h.addWidget(self.b_approuver)
        self.b_cer = QPushButton(_("Enregistrer ce certificat (.cer)..."))
        self.b_cer.clicked.connect(self.enregistrer_cer)
        h.addWidget(self.b_cer)
        self.b_aller = QPushButton(_("Aller à la signature"))
        self.b_aller.clicked.connect(self.aller)
        h.addWidget(self.b_aller)
        h.addStretch(1)
        bb = boutons_fr(QDialogButtonBox(QDialogButtonBox.Close))
        bb.rejected.connect(self.accept)
        h.addWidget(bb)
        v.addLayout(h)
        self.arbre.currentItemChanged.connect(lambda *_a: self._etat())
        if self.arbre.topLevelItemCount():
            self.arbre.setCurrentItem(self.arbre.topLevelItem(max(0, len(signatures) - 1)))
        self._etat()

    def _sig(self):
        it = self.arbre.currentItem()
        while it is not None and it.parent() is not None:
            it = it.parent()
        return it.data(0, Qt.UserRole) if it else None

    def _etat(self):
        s = self._sig() or {}
        self.b_approuver.setEnabled(bool(s.get("der")) and not s.get("approuve"))
        self.b_cer.setEnabled(bool(s.get("der")))
        self.b_aller.setEnabled(bool(s.get("champ") or s.get("vide")))

    def approuver(self):
        s = self._sig()
        if not s or not s.get("der"):
            return
        if QMessageBox.question(self, _("Approuver ce certificat"),
                                _("Approuver le certificat de {nom} ?\n\nEmpreinte SHA-256 :\n{e}\n\nSi vous avez un doute, "
                                  "comparez cette empreinte avec celle que {nom} vous communique.", nom=s.get("nom"),
                                  e=s.get("empreinte"))) != QMessageBox.Yes:
            return
        ID.approuver(self.params, s["der"])
        self.o.verifier_signatures()
        self.accept()

    def enregistrer_cer(self):
        s = self._sig()
        if not s or not s.get("der"):
            return
        f, _x = QFileDialog.getSaveFileName(self, _("Enregistrer le certificat"), (s.get("nom") or "certificat") + ".cer",
                                            _("Certificat (*.cer)"))
        if f:
            with open(f, "wb") as h:
                h.write(s["der"])

    def aller(self):
        s = self._sig() or {}
        self.o.aller_champ_signature(s.get("champ") or s.get("vide"))
