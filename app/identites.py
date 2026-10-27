"""Identites numeriques (signature PAdES) et certificats approuves.

- Chaque identite est un fichier .pfx (protege par SON mot de passe, demande a chaque signature) range dans le dossier
  de donnees de ce poste ; la liste (nom, e-mail, validite, empreinte) suit sur vos autres postes avec les reglages
  communs, et le .pfx lui-meme voyage avec les autres secrets, chiffre (AES-256) par votre mot de passe principal.
- Certificats approuves : ceux de vos correspondants (et les votres) ; une signature faite avec l'un d'eux est
  « approuvee » dans PhilPDF, comme dans la liste des certificats approuves d'Acrobat. Ils ne sont pas secrets.
"""
import base64
import datetime as _dt
import os
import uuid

from moteur import signature_num as S


def _dossier():
    from .config import dossier_donnees
    d = os.path.join(dossier_donnees(), "identites")
    os.makedirs(d, exist_ok=True)
    return d


def _fichier(ident):
    return os.path.join(_dossier(), ident + ".pfx")


def _iso(d):
    return d.isoformat(timespec="seconds") if isinstance(d, _dt.datetime) else (d or "")


def liste(params):
    """Identites connues (sur tous vos postes) ; « ici » dit si le .pfx est present sur ce poste."""
    out = []
    for e in params.get("identites", []) or []:
        e = dict(e)
        e["ici"] = os.path.exists(_fichier(e["id"]))
        e["expire"] = bool(e.get("fin")) and e["fin"] < _dt.datetime.now(_dt.timezone.utc).isoformat()
        out.append(e)
    out.sort(key=lambda e: (not e.get("defaut"), e.get("expire"), e.get("nom", "").lower()))
    return out


def par_defaut(params):
    """Identite proposee pour signer : celle par defaut, sinon la premiere valide presente ici."""
    l = [e for e in liste(params) if e["ici"]]
    return next((e for e in l if e.get("defaut") and not e["expire"]), None) or \
        next((e for e in l if not e["expire"]), None) or (l[0] if l else None)


def _enregistrer_liste(params, l):
    params["identites"] = [{k: v for k, v in e.items() if k not in ("ici", "expire")} for e in l]
    params.enregistrer()


def ajouter_pfx(params, octets, mot_de_passe, origine="fichier"):
    """Ajoute une identite (verifie le mot de passe). Deja presente (meme empreinte) : on la reprend telle quelle.
    Renvoie l'entree."""
    info = S.infos_pfx(octets, mot_de_passe)
    l = [dict(e) for e in params.get("identites", []) or []]
    e = next((x for x in l if x.get("empreinte") == info["empreinte"]), None)
    if e is None:
        e = {"id": uuid.uuid4().hex[:12], "origine": origine, "ajoute": _iso(_dt.datetime.now().astimezone()),
             "defaut": not any(x.get("defaut") for x in l)}
        l.append(e)
    e.update({"nom": info["nom"], "email": info["email"], "organisation": info["organisation"],
              "emetteur": info["emetteur"], "autosigne": info["autosigne"], "empreinte": info["empreinte"],
              "debut": _iso(info["debut"]), "fin": _iso(info["fin"])})
    with open(_fichier(e["id"]), "wb") as f:
        f.write(octets)
    _enregistrer_liste(params, l)
    try:
        approuver(params, S.exporter_cer(octets, mot_de_passe), soi=True)   # vos propres signatures sont approuvees
    except S.ErreurSignature:
        pass
    return next(x for x in liste(params) if x["id"] == e["id"])


def creer(params, nom, mot_de_passe, organisation="", service="", email="", pays="FR", annees=5):
    pfx = S.creer_identite(nom, mot_de_passe, organisation, service, email, pays, annees)
    return ajouter_pfx(params, pfx, mot_de_passe, origine="philpdf")


def lire(e):
    """Octets du .pfx sur ce poste, ou None."""
    try:
        with open(_fichier(e["id"]), "rb") as f:
            return f.read()
    except OSError:
        return None


def supprimer(params, ident):
    l = [e for e in params.get("identites", []) or [] if e["id"] != ident]
    if l and not any(e.get("defaut") for e in l):
        l[0]["defaut"] = True
    try:
        os.remove(_fichier(ident))
    except OSError:
        pass
    _enregistrer_liste(params, l)


def definir_defaut(params, ident):
    l = [dict(e, defaut=(e["id"] == ident)) for e in params.get("identites", []) or []]
    _enregistrer_liste(params, l)


def changer_mot_de_passe(params, e, ancien, nouveau):
    octets = S.changer_mot_de_passe(lire(e), ancien, nouveau)
    with open(_fichier(e["id"]), "wb") as f:
        f.write(octets)


# ------------------------------------------------------------------ certificats approuves
def approuves(params):
    return list(params.get("certificats_approuves", []) or [])


def approuver(params, der, soi=False):
    """Ajoute un certificat (octets DER, PEM ou objet) a la liste des approuves. Renvoie l'entree."""
    from asn1crypto import x509 as ax, pem
    if not isinstance(der, bytes):
        from cryptography.hazmat.primitives import serialization
        der = der.public_bytes(serialization.Encoding.DER)
    if pem.detect(der):
        der = pem.unarmor(der)[2]
    c = ax.Certificate.load(der)
    info = S._infos_asn1(c)
    info["fin"] = info["fin"].isoformat() if info.get("fin") else ""
    l = approuves(params)
    e = next((x for x in l if x.get("empreinte") == info["empreinte"]), None)
    if e is None:
        e = {"empreinte": info["empreinte"], "nom": info["nom"], "email": info["email"],
             "organisation": info["organisation"], "fin": info["fin"], "soi": soi,
             "der": base64.b64encode(der).decode("ascii"), "ajoute": _iso(_dt.datetime.now().astimezone())}
        l.append(e)
        params["certificats_approuves"] = l
        params.enregistrer()
    return e


def retirer(params, empreinte):
    params["certificats_approuves"] = [x for x in approuves(params) if x.get("empreinte") != empreinte]
    params.enregistrer()


def approuves_der(params):
    out = []
    for x in approuves(params):
        try:
            out.append(base64.b64decode(x["der"]))
        except (KeyError, ValueError):
            pass
    return out


# ------------------------------------------------------------------ secrets synchronises
def secrets(params):
    """{"identite:<id>": base64(pfx)} pour les identites presentes sur ce poste."""
    out = {}
    for e in params.get("identites", []) or []:
        b = lire(e)
        if b:
            out["identite:" + e["id"]] = base64.b64encode(b).decode("ascii")
    return out


def reprendre_secret(params, cle, valeur, ecraser=False):
    """Pose ici le .pfx venu d'un autre poste. Renvoie True si quelque chose a ete ecrit."""
    ident = cle.split(":", 1)[1]
    if not ident or "/" in ident or "\\" in ident or ".." in ident:
        return False
    p = _fichier(ident)
    if os.path.exists(p) and not ecraser:
        return False
    try:
        octets = base64.b64decode(valeur)
    except ValueError:
        return False
    with open(p, "wb") as f:
        f.write(octets)
    return True


def nom_identite(params, cle):
    ident = cle.split(":", 1)[1]
    e = next((x for x in params.get("identites", []) or [] if x["id"] == ident), None)
    return e.get("nom", ident) if e else ident
