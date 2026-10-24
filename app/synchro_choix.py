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
    """QComboBox des emplacements possibles ; la donnee est "" (aucun), "compte:<id>" ou un chemin de dossier.
    Les Drives sont proposes « en direct » (PhilPDF s'y connecte lui-meme, autorisation tout de suite)."""
    from .dialogues_distant import ICONES
    from . import oauth
    cb = QComboBox()
    cb.addItem(_("(aucun : chaque poste reste indépendant)"), "")
    for c in params.get("comptes", []):
        cb.addItem(icone(ICONES.get(c["type"], "ouvrir"), "#0f6cbd"), libelle_compte(c), "compte:" + c["id"])
    deja = {c["type"] for c in params.get("comptes", []) if c["type"] in distant.NUAGES}
    for t in distant.NUAGES:
        if t in deja:
            continue
        if oauth.disponible(t):
            cb.addItem(icone("synchro", "#0f6cbd"), _("{nom} en direct : se connecter et autoriser...", nom=distant.TYPES[t]), "nouveau:" + t)
        else:
            cb.addItem(icone("synchro", "#aaaaaa"), _("{nom} en direct (pas encore activé dans cette version)", nom=distant.TYPES[t]), "absent:" + t)
    for t in AJOUTABLES:
        cb.addItem(icone("plus", "#0f6cbd"), _("{nom} : ajouter un compte...", nom=_(distant.TYPES[t])), "nouveau:" + t)
    cb.addItem(icone("ouvrir", "#555"), _("Autre dossier de ce PC..."), "dossier:")
    if params.get("drive") and not params.get("drive_compte"):     # ancien reglage : on le montre tel quel
        cb.insertItem(1, icone("ouvrir", "#c8a000"), params["drive"], params["drive"])
    actuel = "compte:" + params["drive_compte"] if params.get("drive_compte") else params.get("drive", "")
    cb.setCurrentIndex(max(0, cb.findData(actuel)))
    cb._precedent = cb.currentIndex()

    def remettre():
        cb.blockSignals(True)
        cb.setCurrentIndex(cb._precedent)
        cb.blockSignals(False)

    def ajouter_compte(c):
        params["comptes"] = [x for x in params.get("comptes", []) if x["id"] != c["id"]] + [c]
        params.enregistrer()
        cb.blockSignals(True)
        cb.insertItem(1, icone(ICONES.get(c["type"], "ouvrir"), "#0f6cbd"), libelle_compte(c), "compte:" + c["id"])
        cb.setCurrentIndex(1)
        cb.blockSignals(False)

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
                remettre()
        elif donnee.startswith("absent:"):
            QMessageBox.information(parent, distant.TYPES[donnee[7:]], _(
                "{nom} en direct n'est pas encore activé dans cette version de PhilPDF : son identifiant d'application "
                "n'a pas été intégré à la fabrication. Il le sera dans une prochaine mise à jour.", nom=distant.TYPES[donnee[7:]]))
            remettre()
        elif donnee.startswith("nouveau:") and donnee[8:] in distant.NUAGES:
            from .dialogues_distant import autoriser_compte
            c = distant.nouveau_compte(donnee[8:])
            if autoriser_compte(parent, c):
                try:
                    qui = distant.emplacement(c).qui()
                    c["nom"] = f"{distant.TYPES[c['type']]} ({qui})"
                except Exception:
                    pass
                ajouter_compte(c)
            else:
                remettre()
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
                ajouter_compte(c)
            else:
                remettre()
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
    if donnee.startswith(("nouveau:", "dossier:", "absent:")):
        return "", ""
    return donnee, ""
