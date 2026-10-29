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
        e["ici"] = any(os.path.exists(_fichier(i)) for i in [e["id"]] + list(e.get("alias") or [])) or (bool(e.get("windows")) and e.get("poste") == params.get("machine")
                                                         and __import__("sys").platform == "win32")
        e["expire"] = bool(e.get("fin")) and e["fin"] < _dt.datetime.now(_dt.timezone.utc).isoformat()
        e.setdefault("nom", "")
        out.append(e)
    out.sort(key=lambda e: (not e.get("defaut"), e.get("expire"), e.get("nom", "").lower()))
    return out


def par_defaut(params):
    """Identite proposee pour signer : celle par defaut, sinon la premiere valide presente ici."""
    l = [e for e in liste(params) if e["ici"] and not e.get("orpheline")]
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
    e.pop("orpheline", None)
    params["identites_supprimees"] = [x for x in params.get("identites_supprimees") or [] if x != e["id"]]
    _enregistrer_liste(params, l)
    try:
        approuver(params, S.exporter_cer(octets, mot_de_passe), soi=True)   # vos propres signatures sont approuvees
    except S.ErreurSignature:
        pass
    return next(x for x in liste(params) if x["id"] == e["id"])


def ajouter_windows(params, w):
    """ID du magasin Windows dont la clef n'est pas exportable : PhilPDF le garde en reference (empreinte) et fait
    signer Windows. Il reste sur ce PC (pas de copie sur les autres postes)."""
    import base64
    from asn1crypto import x509 as ax
    der = base64.b64decode(w["der"])
    info = S._infos_asn1(ax.Certificate.load(der))
    l = [dict(e) for e in params.get("identites", []) or []]
    e = next((x for x in l if x.get("empreinte") == info["empreinte"]), None)
    if e is None:
        e = {"id": uuid.uuid4().hex[:12], "ajoute": _iso(_dt.datetime.now().astimezone()),
             "defaut": not any(x.get("defaut") for x in l)}
        l.append(e)
    e.update({"origine": "windows", "windows": w["empreinte"], "poste": params.get("machine", ""), "der": w["der"],
              "nom": info["nom"], "email": info["email"], "organisation": info["organisation"],
              "emetteur": info["emetteur"], "autosigne": info["autosigne"], "empreinte": info["empreinte"],
              "fin": info["fin"].isoformat() if info.get("fin") else ""})
    _enregistrer_liste(params, l)
    approuver(params, der, soi=True)
    return next(x for x in liste(params) if x["id"] == e["id"])


def creer(params, nom, mot_de_passe, organisation="", service="", email="", pays="FR", annees=5):
    pfx = S.creer_identite(nom, mot_de_passe, organisation, service, email, pays, annees)
    return ajouter_pfx(params, pfx, mot_de_passe, origine="philpdf")


def lire(e):
    """Octets du .pfx sur ce poste (sous son numero ou un de ses alias), ou None."""
    for i in [e["id"]] + list(e.get("alias") or []):
        try:
            with open(_fichier(i), "rb") as f:
                return f.read()
        except OSError:
            continue
    return None


def regler(params, ident, **valeurs):
    """Indice du mot de passe, apparence par defaut (« nom », « manuscrite » + id, « texte ») : suivent sur vos postes."""
    l = [dict(e) for e in params.get("identites", []) or []]
    for e in l:
        if e["id"] == ident:
            e.update(valeurs)
    _enregistrer_liste(params, l)


def supprimer(params, ident):
    params["identites_supprimees"] = sorted(set(params.get("identites_supprimees") or []) | {ident})
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
    params["certificats_retires"] = sorted(set(params.get("certificats_retires") or []) | {empreinte})
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
    from .langue import _
    ident = cle.split(":", 1)[1]
    e = next((x for x in params.get("identites", []) or [] if x["id"] == ident or ident in (x.get("alias") or [])),
             None)
    if e and e.get("nom"):
        fin = e.get("fin") or ""
        return e["nom"] + (" (" + _("valable jusqu'au {d}", d="/".join(reversed(fin[:10].split("-")))) + ")" if fin else "")
    return _("nom inconnu, n° {i}", i=ident[:8]) if not e else ident


def retrouver_orphelines(params):
    """Fichiers d'identite presents sur ce poste (repris des secrets synchronises) mais absents de la liste (liste
    perdue lors d'une fusion) : ajoutes comme « a deverrouiller » ; leur mot de passe redonne nom et validite.
    Renvoie le nombre d'identites retrouvees."""
    l = [dict(e) for e in params.get("identites", []) or []]
    connus = {e["id"] for e in l} | {a for e in l for a in (e.get("alias") or [])}
    supprimees = set(params.get("identites_supprimees") or [])
    n = 0
    for f in sorted(os.listdir(_dossier())):
        if not f.lower().endswith(".pfx"):
            continue
        ident = f[:-4]
        if ident in connus or ident in supprimees:
            continue
        l.append({"id": ident, "nom": "", "orpheline": True, "origine": "retrouvee",
                  "ajoute": _iso(_dt.datetime.now().astimezone()), "defaut": not any(x.get("defaut") for x in l)})
        n += 1
    if n:
        _enregistrer_liste(params, l)
    return n


def deverrouiller(params, ident, mot_de_passe):
    """Identite retrouvee : son mot de passe permet de relire nom, e-mail et validite. Renvoie l'entree."""
    e = next((x for x in params.get("identites", []) or [] if x["id"] == ident), None)
    octets = lire(e) if e else None
    if not octets:
        raise S.ErreurSignature("absent")
    info = S.infos_pfx(octets, mot_de_passe)
    l = [dict(x) for x in params.get("identites", []) or []]
    for x in l:
        if x["id"] == ident:
            x.pop("orpheline", None)
            x.update({"nom": info["nom"], "email": info["email"], "organisation": info["organisation"],
                      "emetteur": info["emetteur"], "autosigne": info["autosigne"], "empreinte": info["empreinte"],
                      "debut": _iso(info["debut"]), "fin": _iso(info["fin"])})
    from .miroir import _sans_doublons                  # deja connue sous un autre numero : une seule ligne
    _enregistrer_liste(params, _sans_doublons(l))
    try:
        approuver(params, S.exporter_cer(octets, mot_de_passe), soi=True)
    except S.ErreurSignature:
        pass
    emp = info["empreinte"]
    return next(x for x in liste(params) if x["id"] == ident or x.get("empreinte") == emp)
