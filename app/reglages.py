"""Sauvegarde, export et import des preferences.

Deux familles de reglages :
  - COMMUNS a tous vos postes : votre nom, la langue, les comptes (NAS, FTP, WebDAV, Drives), l'ordre des
    outils et des favoris, l'etat des volets et des barres, le zoom, les filigranes personnels, l'IA,
    les mises a jour, les tampons et signatures par defaut ;
  - PROPRES A UN POSTE : son nom (alias), ses dossiers et chemins (NAS, emplacements, dernier dossier),
    le choix du Drive sur ce PC, l'association des .pdf.

Automatiquement : a chaque validation des Preferences et a la fermeture, <Drive>/PhilPDF/preferences.json
recoit les reglages communs et ceux de ce poste (sans aucun mot de passe). Une nouvelle installation qui
trouve ce fichier propose de les reprendre.

A la main (Preferences > General) : export dans un fichier, avec ou sans les mots de passe et clefs ;
s'ils sont inclus, le fichier est chiffre en AES-256 par une phrase secrete.
"""
import datetime, json, os
from . import coffre

COMMUNS = ["auteur", "langue", "outils_epingles", "barre_rapide", "volet", "vignettes", "fixer_objets",
           "filigranes_perso", "ia_moteur", "maj_source", "maj_auto", "synchro", "comptes", "defaut_tampons",
           "defaut_signatures", "theme", "synchro_secrets", "barre", "couleurs_annotations",
           "style_souligne", "opacite_surlignage", "ia_consignes_resume", "orthographe", "barre_style"]
POSTE = ["machine", "zoom", "racines", "nas", "dernier_dossier", "drive", "drive_compte", "association_pdf", "recherche_racines"]
CLEFS_IA = ["clef_claude", "clef_gemini"]
FICHIER_DRIVE = "preferences.json"


def maintenant():
    return datetime.datetime.now().isoformat(timespec="minutes")


def instantane(params, avec_secrets=False):
    d = {"philpdf": 1, "date": maintenant(), "machine": params.get("machine", ""),
         "communs": {k: params[k] for k in COMMUNS if k in params},
         "poste": {k: params[k] for k in POSTE if k in params}}
    if avec_secrets:
        s = {k: params.get(k, "") for k in CLEFS_IA}
        for c in params.get("comptes", []):
            for suffixe in ("", ".jeton", ".appareil"):
                v = coffre.lire(c["id"] + suffixe)
                if v:
                    s["coffre:" + c["id"] + suffixe] = v
        d["secrets"] = s
    return d


def appliquer(params, d, communs=True, poste=False, secrets=True):
    if communs:
        for k, v in d.get("communs", {}).items():
            if k in COMMUNS:
                params[k] = v
    if poste:
        for k, v in d.get("poste", {}).items():
            if k in POSTE:
                params[k] = v
    if secrets:
        for k, v in (d.get("secrets") or {}).items():
            if k.startswith("coffre:"):
                coffre.enregistrer(k[7:], v)
            elif k in CLEFS_IA and v:
                params[k] = v
    params.enregistrer()


# ------------------------------------------------------------------ fichier (export / import)
def exporter(chemin, d, phrase=None):
    """JSON lisible sans phrase ; avec une phrase : PDF chiffre AES-256 contenant le JSON."""
    contenu = json.dumps(d, ensure_ascii=False, indent=1).encode("utf-8")
    if not phrase:
        with open(chemin, "wb") as f:
            f.write(contenu)
        return
    import pymupdf as fitz
    doc = fitz.open()
    p = doc.new_page(width=420, height=200)
    p.insert_text((36, 60), "PhilPDF - preferences (chiffrees)", fontsize=14)
    p.insert_text((36, 90), "A importer dans PhilPDF : Edition > Preferences > General.", fontsize=10)
    doc.embfile_add("preferences.json", contenu, filename="preferences.json")
    doc.save(chemin, encryption=fitz.PDF_ENCRYPT_AES_256, user_pw=phrase, owner_pw=phrase,
             permissions=0)


class PhraseRequise(Exception):
    pass


def importer(chemin, phrase=None):
    with open(chemin, "rb") as f:
        tete = f.read(5)
    if tete != b"%PDF-":
        with open(chemin, encoding="utf-8") as f:
            d = json.load(f)
    else:
        import pymupdf as fitz
        doc = fitz.open(chemin)
        if doc.needs_pass:
            if not phrase or not doc.authenticate(phrase):
                raise PhraseRequise()
        d = json.loads(doc.embfile_get("preferences.json").decode("utf-8"))
    if d.get("philpdf") != 1:
        raise ValueError("format")
    return d


# ------------------------------------------------------------------ Drive (automatique, sans secrets)
def chemin_drive(params):
    from .bibliotheque import dossier_philpdf_drive
    d = dossier_philpdf_drive(params)
    return os.path.join(d, FICHIER_DRIVE) if d else None


def lire_drive(chemin):
    try:
        with open(chemin, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError, TypeError):
        return {}


def ecrire_drive(params):
    p = chemin_drive(params)
    if not p:
        return False
    d = lire_drive(p)
    i = instantane(params)
    d["philpdf"] = 1
    local = params.get("communs_maj") or ""
    sur_drive = (d.get("communs") or {}).get("maj") or ""
    # les reglages communs de ce poste ne remplacent ceux du Drive que s'ils ont ete changes plus recemment
    if local and local > sur_drive:
        d["communs"] = dict(i["communs"], maj=local, par=i["machine"])
    d.setdefault("postes", {})[i["machine"]] = dict(i["poste"], maj=i["date"])
    try:
        with open(p, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
        return True
    except OSError:
        return False


def trouver_sur_drives():
    """Preferences laissees sur un Drive de ce PC (dossier de l'application de bureau) : [(nom, chemin, contenu)]."""
    from .bibliotheque import detecter_clouds
    out = []
    for nom, racine in detecter_clouds():
        p = os.path.join(racine, "PhilPDF", FICHIER_DRIVE)
        d = lire_drive(p)
        if d.get("communs"):
            out.append((nom, racine, d))
    return out


# ------------------------------------------------------------------ mots de passe sur le Drive (chiffres)
FICHIER_SECRETS = "secrets.philpdf"
PHRASE = "phrase_synchro"            # cle du coffre local qui garde la phrase de ce poste


def chemin_secrets(params):
    from .bibliotheque import dossier_philpdf_drive
    d = dossier_philpdf_drive(params)
    return os.path.join(d, FICHIER_SECRETS) if d else None


def _secrets_partageables(params):
    s = instantane(params, avec_secrets=True).get("secrets", {})
    # Box change de jeton durable a chaque usage : partage entre postes impossible, chacun autorise le sien
    box = {c["id"] for c in params.get("comptes", []) if c.get("type") == "box"}
    return {k: v for k, v in s.items() if v and not any(k == f"coffre:{b}.jeton" for b in box)}


def lire_secrets_drive(params, phrase):
    """Secrets du Drive ({cle: valeur}) ; leve PhraseRequise si la phrase est fausse, {} s'il n'y a rien."""
    p = chemin_secrets(params)
    if not p or not os.path.exists(p):
        return {}
    return importer(p, phrase).get("secrets", {})


def ecrire_secrets_drive(params, phrase=None):
    """Met les mots de passe, autorisations et clefs de ce poste sur le Drive, chiffres (AES-256) par la phrase.
    Ceux des autres postes deja presents sont gardes. Renvoie False si rien n'a ete ecrit."""
    phrase = phrase or coffre.lire(PHRASE)
    p = chemin_secrets(params)
    if not phrase or not p or not params.get("synchro_secrets"):
        return False
    try:
        anciens = lire_secrets_drive(params, phrase)
    except (PhraseRequise, OSError, ValueError, KeyError):
        anciens = {}
    tous = dict(anciens, **_secrets_partageables(params))
    tmp = p + ".tmp"
    exporter(tmp, {"philpdf": 1, "date": maintenant(), "machine": params.get("machine", ""), "communs": {}, "poste": {},
                   "secrets": tous}, phrase)
    os.replace(tmp, p)
    return True


def reprendre_secrets_drive(params, phrase, ecraser=False):
    """Copie dans le coffre de ce poste les secrets du Drive (sans ecraser ceux deja presents, sauf demande).
    Renvoie le nombre de secrets repris."""
    n = 0
    for k, v in lire_secrets_drive(params, phrase).items():
        if k.startswith("coffre:"):
            if ecraser or not coffre.lire(k[7:]):
                coffre.enregistrer(k[7:], v)
                n += 1
        elif k in CLEFS_IA and v and (ecraser or not params.get(k)):
            params[k] = v
            n += 1
    params.enregistrer()
    return n


def reprendre_communs_drive(params):
    """Au demarrage : si un autre poste a change des reglages communs plus recemment (favoris, outils, barres,
    comptes, langue...), on les reprend ici. Renvoie le nom de ce poste, ou None."""
    p = chemin_drive(params)
    if not p:
        return None
    c = (lire_drive(p).get("communs") or {})
    maj, par = c.get("maj") or "", c.get("par") or ""
    if not maj or maj <= (params.get("communs_maj") or "") or par == params.get("machine"):
        return None
    comptes_ici = {x["id"] for x in params.get("comptes", [])}
    for k, v in c.items():
        if k in COMMUNS:
            params[k] = v
    params["communs_maj"] = maj
    params._communs_vus = params._empreinte_communs() if hasattr(params, "_empreinte_communs") else ""
    params.enregistrer()
    nouveaux = [x for x in params.get("comptes", []) if x["id"] not in comptes_ici]
    return par, nouveaux


# ------------------------------------------------------------------ mise a jour choisie (jamais en silence)
def _(t, **k):
    from .langue import _ as tr
    return tr(t, **k)


def libelle_commun(k):
    return {"auteur": _("Votre nom (tampons, commentaires)"), "langue": _("Langue de PhilPDF"),
            "outils_epingles": _("Outils favoris"), "barre_rapide": _("Barre rapide de sélection"),
            "volet": _("Volet de droite"), "vignettes": _("Vignettes"), "fixer_objets": _("Fixer les objets à l'enregistrement"),
            "filigranes_perso": _("Filigranes personnels"), "ia_moteur": _("IA utilisée"),
            "maj_source": _("Source des mises à jour"), "maj_auto": _("Mises à jour automatiques"),
            "synchro": _("Synchronisation des fichiers"), "comptes": _("Comptes (NAS, FTP, Drives)"),
            "defaut_tampons": _("Tampons par défaut"), "defaut_signatures": _("Signatures par défaut"),
            "theme": _("Thème"), "synchro_secrets": _("Synchroniser les mots de passe"),
            "barre": _("Barre d'outils des documents"), "couleurs_annotations": _("Couleurs des annotations"),
            "style_souligne": _("Style du soulignement"), "opacite_surlignage": _("Opacité du surlignage"),
            "ia_consignes_resume": _("Consignes personnelles pour le résumé IA")}.get(k, k)


def _court(v):
    if isinstance(v, bool):
        return _("oui") if v else _("non")
    if v in (None, "", [], {}):
        return _("(vide)")
    t = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
    return t if len(t) <= 40 else t[:37] + "..."


def _nom_element(x):
    if isinstance(x, dict):
        return str(x.get("nom") or x.get("id") or x.get("texte") or "?")
    return str(x)


def decrire_changement(k, avant, apres):
    """Phrase lisible : ce qui va changer sur ce poste si on reprend ce reglage."""
    if k == "comptes":
        a = {c.get("id"): c for c in avant or []}
        b = {c.get("id"): c for c in apres or []}
        morceaux = []
        aj = [_nom_element(b[i]) for i in b if i not in a]
        rt = [_nom_element(a[i]) for i in a if i not in b]
        md = [_nom_element(b[i]) for i in b if i in a and a[i] != b[i]]
        if aj:
            morceaux.append(_("ajoute : {x}", x=", ".join(aj)))
        if rt:
            morceaux.append(_("retire : {x}", x=", ".join(rt)))
        if md:
            morceaux.append(_("modifie : {x}", x=", ".join(md)))
        return " ; ".join(morceaux) or _("ordre modifié")
    if isinstance(avant, list) and isinstance(apres, list):
        ka = [_nom_element(x) for x in avant]
        kb = [_nom_element(x) for x in apres]
        aj = [x for x in kb if x not in ka]
        rt = [x for x in ka if x not in kb]
        morceaux = []
        if aj:
            morceaux.append(_("ajoute : {x}", x=", ".join(aj[:8]) + ("..." if len(aj) > 8 else "")))
        if rt:
            morceaux.append(_("retire : {x}", x=", ".join(rt[:8]) + ("..." if len(rt) > 8 else "")))
        return " ; ".join(morceaux) or _("ordre modifié")
    if isinstance(avant, dict) and isinstance(apres, dict):
        cles = [c for c in set(avant) | set(apres) if avant.get(c) != apres.get(c)]
        return _("modifie : {x}", x=", ".join(sorted(map(str, cles))[:8]))
    return f"{_court(avant)}  →  {_court(apres)}"


def changements_communs(params):
    """None si rien de plus recent sur le Drive ; sinon {"par", "maj", "items": [{cle, libelle, detail, valeur}]}."""
    p = chemin_drive(params)
    if not p:
        return None
    c = (lire_drive(p).get("communs") or {})
    maj, par = c.get("maj") or "", c.get("par") or ""
    if not maj or maj <= (params.get("communs_maj") or "") or par == params.get("machine"):
        return None
    items = []
    for k in COMMUNS:
        if k in c and c[k] != params.get(k):
            items.append({"cle": k, "libelle": libelle_commun(k), "detail": decrire_changement(k, params.get(k), c[k]),
                          "valeur": c[k]})
    return {"par": par, "maj": maj, "items": items}


def appliquer_communs(params, changements, cles):
    """Reprend seulement les reglages choisis ; les autres restent ceux de ce poste. On ne redemande pas ensuite."""
    for it in changements["items"]:
        if it["cle"] in cles:
            params[it["cle"]] = it["valeur"]
    params["communs_maj"] = changements["maj"]
    params._communs_vus = params._empreinte_communs() if hasattr(params, "_empreinte_communs") else ""
    params.enregistrer()


def secrets_nouveaux(params, phrase):
    """Secrets du Drive absents de ce poste : [{cle, libelle}] (jamais les valeurs)."""
    noms = {c["id"]: c.get("nom") or c["id"] for c in params.get("comptes", [])}
    out = []
    for k, v in lire_secrets_drive(params, phrase).items():
        if k.startswith("coffre:"):
            if v and not coffre.lire(k[7:]):
                cid, _p, suffixe = k[7:].partition(".")
                quoi = _("autorisation") if suffixe in ("jeton", "appareil") else _("mot de passe")
                out.append({"cle": k, "libelle": f"{quoi} : {noms.get(cid, cid)}"})
        elif k in CLEFS_IA and v and not params.get(k):
            out.append({"cle": k, "libelle": _("clef IA : {x}", x="Claude" if "claude" in k else "Gemini")})
    return out


def reprendre_secrets_choisis(params, phrase, cles):
    n = 0
    for k, v in lire_secrets_drive(params, phrase).items():
        if k not in cles:
            continue
        if k.startswith("coffre:"):
            coffre.enregistrer(k[7:], v)
        else:
            params[k] = v
        n += 1
    params.enregistrer()
    return n
