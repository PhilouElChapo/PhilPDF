"""Partages par lien : le dossier PhilPDF/Partages du Drive de synchronisation (decision du 23/11/2026).

Pour envoyer un lien, le PDF doit etre sur le Drive : PhilPDF le depose dans PhilPDF/Partages et le rend lisible
par toute personne qui a le lien (lecture seule). Ce dossier est la liste des partages, sur tous les postes et
telephones : rien d'autre a tenir a jour. Il n'est PAS recopie par la synchronisation (les PDF ne voyagent jamais
d'office) ; un partage n'est telecharge que si vous l'ouvrez, et « Enregistrer » le remplace sur le Drive (les
personnes qui ont le lien voient alors la nouvelle version).

Google Drive : lien, arret du partage, poste d'origine (description du fichier), corbeille.
Autres emplacements de synchronisation (OneDrive, NAS...) : la liste et l'ouverture seulement.
"""
import datetime, json, os, posixpath, urllib.parse

from . import distant, miroir
from .langue import _

DOSSIER = "Partages"
JOURS = 90                       # au-dela, le partage est propose au nettoyage (toujours avec votre accord)


def compte(params):
    """Compte de synchronisation (celui des partages), ou None."""
    return miroir.compte_drive(params)


def dossier(c):
    return posixpath.join(miroir.racine_distante(c), DOSSIER)


def chemin(c, nom):
    return posixpath.join(dossier(c), nom)


def est_partage(c, ch):
    """Vrai pour un fichier du dossier Partages de ce compte (Enregistrer previent alors que le lien suit)."""
    return bool(c and ch) and posixpath.dirname("/" + ch.strip("/")).rstrip("/") == "/" + dossier(c).strip("/")


def _age_jours(iso):
    try:
        d = datetime.datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        return (datetime.datetime.now(datetime.timezone.utc) - d).days
    except ValueError:
        return 0


def lister(params, e=None):
    """[{nom, chemin, id, cree, modifie, taille, poste, lien, actif, ancien}] du plus recent au plus ancien."""
    c = compte(params)
    if not c:
        return []
    e = e or distant.emplacement(c)
    d = dossier(c)
    out = []
    if c["type"] == "gdrive":
        i = e._id(d)
        if i is None:
            return []
        q = urllib.parse.urlencode({"q": f"'{i}' in parents and trashed = false", "pageSize": "1000", "spaces": "drive",
                                    "fields": "files(id,name,size,mimeType,createdTime,modifiedTime,description,"
                                              "webViewLink,permissions(id,type))"})
        for f in e._appel("GET", f"{distant.DRIVE_API}/files?{q}").get("files", []):
            if f.get("mimeType") == distant.DOSSIER_MIME:
                continue
            desc = f.get("description") or ""
            poste = desc.split("PhilPDF :", 1)[1].strip() if "PhilPDF :" in desc else ""
            actif = any(p.get("type") == "anyone" for p in f.get("permissions") or [])
            cree = f.get("createdTime") or f.get("modifiedTime") or ""
            out.append({"nom": f["name"], "chemin": posixpath.join(d, f["name"]), "id": f["id"], "cree": cree,
                        "modifie": f.get("modifiedTime") or "", "taille": int(f.get("size") or 0), "poste": poste,
                        "lien": f.get("webViewLink") or "", "actif": actif, "ancien": _age_jours(cree) > JOURS})
    else:
        try:
            elements = e.lister(d)
        except distant.ErreurDistant:
            return []
        for x in elements:
            if x.dossier:
                continue
            q_ = x.quand()
            date = q_.astimezone(datetime.timezone.utc).isoformat() if q_ else ""
            out.append({"nom": x.nom, "chemin": x.chemin, "id": "", "cree": date, "modifie": date, "taille": x.taille,
                        "poste": "", "lien": "", "actif": False, "ancien": _age_jours(date) > JOURS if date else False})
    return sorted(out, key=lambda p: p["cree"], reverse=True)


def modifie_le(params, ch, e=None):
    """Date de modification sur le Drive d'un fichier partage (conflit : modifie ailleurs depuis l'ouverture)."""
    c = compte(params)
    if not c:
        return ""
    e = e or distant.emplacement(c)
    try:
        return (e.modifies(posixpath.dirname(ch)).get(posixpath.basename(ch)) or ("", ""))[1]
    except distant.ErreurDistant:
        return ""


def _nom_libre(e, c, nom):
    try:
        pris = {x.nom.lower() for x in e.lister(dossier(c))}
    except distant.ErreurDistant:
        pris = set()
    base, ext = os.path.splitext(nom)
    n, i = nom, 2
    while n.lower() in pris:
        n, i = f"{base} ({i}){ext}", i + 1
    return n


def partager(params, local, nom=None, e=None):
    """Depose une copie du PDF dans PhilPDF/Partages et renvoie (nom sur le Drive, lien). Google Drive seulement."""
    c = compte(params)
    if not c:
        raise distant.ErreurDistant(_("Choisissez d'abord votre Drive de synchronisation (Accueil, bouton de synchronisation)."))
    if c["type"] != "gdrive":
        raise distant.ErreurDistant(_("Le partage par lien se fait avec un Google Drive de synchronisation ; "
                                      "votre synchronisation passe par {lieu}.", lieu=distant.libelle(c)))
    e = e or distant.emplacement(c)
    nom = _nom_libre(e, c, nom or os.path.basename(local))
    ch = chemin(c, nom)
    e.envoyer(local, ch)
    i = e._id(ch)
    entete = {"Content-Type": "application/json"}
    e._appel("PATCH", f"{distant.DRIVE_API}/files/{i}",
             json.dumps({"description": "PhilPDF : " + (params.get("machine") or "")}).encode(), entete)
    e._appel("POST", f"{distant.DRIVE_API}/files/{i}/permissions",
             json.dumps({"role": "reader", "type": "anyone"}).encode(), entete)
    lien = e._appel("GET", f"{distant.DRIVE_API}/files/{i}?fields=webViewLink").get("webViewLink", "")
    _journal(f"{nom} déposé dans PhilPDF/Partages, lien créé")
    return nom, lien


def reprendre(params, p, e=None):
    """Remet le lien d'un partage arrete ; renvoie le lien."""
    c = compte(params)
    e = e or distant.emplacement(c)
    e._appel("POST", f"{distant.DRIVE_API}/files/{p['id']}/permissions",
             json.dumps({"role": "reader", "type": "anyone"}).encode(), {"Content-Type": "application/json"})
    _journal(f"{p['nom']} : partage repris")
    return e._appel("GET", f"{distant.DRIVE_API}/files/{p['id']}?fields=webViewLink").get("webViewLink", "")


def arreter(params, p, e=None):
    """Coupe le lien (le fichier reste sur le Drive)."""
    c = compte(params)
    e = e or distant.emplacement(c)
    e._appel("DELETE", f"{distant.DRIVE_API}/files/{p['id']}/permissions/anyoneWithLink", brut=True)
    _journal(f"{p['nom']} : partage arrêté (lien coupé)")


def supprimer(params, p, e=None):
    """Met le fichier partage a la corbeille du Drive (recuperable 30 jours) ; le lien ne marche plus."""
    c = compte(params)
    e = e or distant.emplacement(c)
    if c["type"] != "gdrive" or not p.get("id"):
        raise distant.ErreurDistant(_("Supprimez ce fichier directement dans {lieu}.", lieu=distant.libelle(c)))
    e._appel("PATCH", f"{distant.DRIVE_API}/files/{p['id']}", json.dumps({"trashed": True}).encode(),
             {"Content-Type": "application/json"})
    _journal(f"{p['nom']} : partage supprimé du Drive")


def _journal(texte):
    try:
        from .journal import ecrire
        ecrire("partage", texte)
    except Exception:          # noqa: BLE001
        pass
