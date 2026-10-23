"""Choix de l'emplacement de synchronisation entre vos postes (Preferences et assistant de premiere installation).

L'emplacement peut etre :
  - un Drive « en direct » (Google Drive, OneDrive, Dropbox, Box) : PhilPDF s'y connecte lui-meme ;
  - un NAS (Synology, WebDAV), un serveur FTP ou un dossier reseau : PhilPDF y cree un dossier PhilPDF ;
  - le dossier de l'application de bureau d'un Drive (Google Drive, OneDrive... installes sur ce PC) ;
  - aucun : chaque poste reste independant.
"""
from PySide6.QtWidgets import QComboBox, QDialog, QFileDialog, QMessageBox

from .langue import _
from .icones import icone
from . import distant

AJOUTABLES = ("synology", "webdav", "ftp", "reseau")


def libelle_compte(c):
    t = c.get("type")
    if t in distant.NUAGES:
        return _("{nom} — en direct", nom=distant.libelle(c))
    return _("{nom} — {genre}, dossier « {dossier} »", nom=distant.libelle(c), genre=_(distant.TYPES.get(t, t)),
             dossier=c.get("dossier") or "/")


def combo_emplacements(parent, params):
    """QComboBox des emplacements possibles ; la donnee est "" (aucun), "compte:<id>" ou un chemin de dossier."""
    from .bibliotheque import detecter_clouds
    from .dialogues_distant import ICONES
    from . import oauth
    cb = QComboBox()
    cb.addItem(_("(aucun : chaque poste reste indépendant)"), "")
    for c in params.get("comptes", []):
        cb.addItem(icone(ICONES.get(c["type"], "ouvrir"), "#0f6cbd"), libelle_compte(c), "compte:" + c["id"])
    for nom, chemin in detecter_clouds():
        cb.addItem(icone("ouvrir", "#c8a000"), _("{nom} — dossier de l'application de bureau ({chemin})", nom=nom, chemin=chemin), chemin)
    if params.get("drive") and not params.get("drive_compte") and cb.findData(params["drive"]) < 0:
        cb.addItem(params["drive"], params["drive"])
    for t in distant.NUAGES:
        if oauth.disponible(t):
            cb.addItem(icone("plus", "#0f6cbd"), _("{nom} en direct : ajouter et autoriser...", nom=distant.TYPES[t]), "nouveau:" + t)
    for t in AJOUTABLES:
        cb.addItem(icone("plus", "#0f6cbd"), _("{nom} : ajouter un compte...", nom=_(distant.TYPES[t])), "nouveau:" + t)
    cb.addItem(icone("ouvrir", "#555"), _("Autre dossier de ce PC..."), "dossier:")
    actuel = "compte:" + params["drive_compte"] if params.get("drive_compte") else params.get("drive", "")
    cb.setCurrentIndex(max(0, cb.findData(actuel)))
    cb._precedent = cb.currentIndex()

    def choisi(i):
        donnee = cb.itemData(i) or ""
        if donnee == "dossier:":
            p = QFileDialog.getExistingDirectory(parent, _("Dossier partagé entre vos postes"))
            if p:
                cb.blockSignals(True)
                cb.insertItem(1, p, p)
                cb.setCurrentIndex(1)
                cb.blockSignals(False)
            else:
                cb.setCurrentIndex(cb._precedent)
        elif donnee.startswith("nouveau:"):
            from .dialogues_distant import DialogueCompte
            dc = DialogueCompte(parent, distant.nouveau_compte(donnee[8:]))
            if dc.exec() == QDialog.Accepted:
                c = dc.compte()
                if c["type"] == "synology" and (c.get("dossier") or "/") == "/":
                    c["dossier"] = "/home"
                    QMessageBox.information(parent, _("Synchronisation"), _(
                        "Le dossier PhilPDF sera créé dans « /home » (votre dossier personnel sur le NAS). Pour un autre "
                        "dossier partagé, modifiez le « Dossier de départ » du compte (Préférences › Comptes)."))
                params["comptes"] = [x for x in params.get("comptes", []) if x["id"] != c["id"]] + [c]
                params.enregistrer()
                cb.blockSignals(True)
                cb.insertItem(1, icone(ICONES.get(c["type"], "ouvrir"), "#0f6cbd"), libelle_compte(c), "compte:" + c["id"])
                cb.setCurrentIndex(1)
                cb.blockSignals(False)
            else:
                cb.blockSignals(True)
                cb.setCurrentIndex(cb._precedent)
                cb.blockSignals(False)
        cb._precedent = cb.currentIndex()
    cb.currentIndexChanged.connect(choisi)
    return cb


def valeurs(cb, params):
    """(drive, drive_compte) a enregistrer dans les parametres pour le choix du combo."""
    from . import miroir
    donnee = cb.currentData() or ""
    if donnee.startswith("compte:"):
        c = next((x for x in params.get("comptes", []) if x["id"] == donnee[7:]), None)
        return (miroir.dossier_miroir(c), c["id"]) if c else ("", "")
    if donnee.startswith(("nouveau:", "dossier:")):
        return "", ""
    return donnee, ""
