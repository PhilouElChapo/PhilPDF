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
           "filigranes_perso", "ia_moteur", "maj_source", "maj_auto", "synchro", "comptes", "comptes_icone", "theme", "synchro_secrets", "barre", "couleurs_annotations",
           "style_souligne", "opacite_surlignage", "ia_consignes_resume", "orthographe", "orthographe_langue", "barre_style", "agenda", "messagerie", "ia_styles_perso",
           "identites", "certificats_approuves", "signature_reglages", "identites_supprimees", "certificats_retires",
           "formulaire_detection", "formulaire_types_auto"]
POSTE = ["disposition_vue", "volet_largeur", "vignettes_largeur", "biblio_replies", "sessions_vues", "synchro_etat", "machine", "zoom", "racines", "nas", "dernier_dossier", "drive", "drive_compte", "association_pdf", "recherche_racines"]
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
        try:
            from . import identites
            s.update(identites.secrets(params))
        except Exception:                                 # noqa: BLE001
            pass
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
            elif k.startswith("identite:") and v:
                from . import identites
                identites.reprendre_secret(params, k, v, ecraser=True)
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
    dc = d.get("communs") or {}
    sur_drive = dc.get("maj") or ""
    # ceux d'un autre poste que vous n'avez pas encore vus (fenetre de choix) ne sont jamais remplaces en silence
    pas_vus = bool(dc) and dc.get("par") not in ("", None, i["machine"]) and sur_drive != (params.get("communs_drive_vu") or "")
    # sinon, les reglages communs de ce poste remplacent ceux du Drive s'ils ont ete changes plus recemment
    if local and local > sur_drive and not pas_vus:
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


FICHIER_INDICE = "indice_phrase.json"


def ecrire_indice(params, indice):
    """Indice (en clair, facultatif) de la phrase secrete, a cote du fichier chiffre : vu sur les autres postes."""
    p = chemin_secrets(params)
    if not p:
        return
    f = os.path.join(os.path.dirname(p), FICHIER_INDICE)
    try:
        if indice:
            with open(f, "w", encoding="utf-8") as fh:
                json.dump({"indice": indice, "maj": maintenant(), "par": params.get("machine", "")}, fh, ensure_ascii=False)
        elif os.path.exists(f):
            os.remove(f)
    except OSError:
        pass


def lire_indice(params):
    p = chemin_secrets(params)
    try:
        with open(os.path.join(os.path.dirname(p), FICHIER_INDICE), encoding="utf-8") as fh:
            return json.load(fh).get("indice", "")
    except (OSError, ValueError, TypeError):
        return ""


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
        elif k.startswith("identite:") and v:
            from . import identites
            if identites.reprendre_secret(params, k, v, ecraser=ecraser):
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
            params[k] = _valeur_reprise(params, c, k, v)
    params["communs_maj"] = maj
    params["communs_drive_vu"] = maj
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
            "comptes_icone": _("Style des icônes des comptes"),
            "defaut_tampons": _("Tampons par défaut"), "defaut_signatures": _("Signatures par défaut"),
            "theme": _("Thème"), "synchro_secrets": _("Synchroniser les mots de passe"),
            "barre": _("Barre d'outils des documents"), "couleurs_annotations": _("Couleurs des annotations"),
            "style_souligne": _("Style du soulignement"), "opacite_surlignage": _("Opacité du surlignage"),
            "ia_consignes_resume": _("Consignes personnelles pour le résumé IA"),
            "agenda": _("Agenda pour les rendez-vous"), "messagerie": _("Messagerie pour les e-mails"),
            "orthographe": _("Correcteur d'orthographe"), "orthographe_langue": _("Langue du correcteur"),
            "barre_style": _("Boutons de la barre (icône, nom)"), "ia_styles_perso": _("Mes styles d'image pour l'IA"),
            "identites": _("Identités numériques (signature)"), "certificats_approuves": _("Certificats approuvés"),
            "signature_reglages": _("Réglages de la signature numérique"),
            "formulaire_detection": _("Repérage des champs en mode Formulaire"),
            "formulaire_types_auto": _("Type des champs deviné d'après le libellé")}.get(k, k)


# valeur utilisee quand le reglage n'a jamais ete touche sur un poste (absent = cette valeur)
DEFAUTS_COMMUNS = {"agenda": "google", "messagerie": "gmail", "comptes_icone": "photo", "barre_style": "auto",
                   "orthographe": True, "orthographe_langue": "auto", "ia_consignes_resume": "",
                   "filigranes_perso": [], "comptes": [], "barre": None}


def _effectif(params, k):
    v = params.get(k)
    if v in (None, "") and k in DEFAUTS_COMMUNS:
        return DEFAUTS_COMMUNS[k]
    return v


def _meme(a, b):
    vide = (None, "", [], {})
    return a == b or (a in vide and b in vide)


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


def _valeur_reprise(params, communs, k, v):
    """Valeur d'un reglage commun repris d'un autre poste : les identites et certificats sont reunis (ceux d'ici
    restent), jamais remplaces par une liste plus courte."""
    from .miroir import UNIONS, unir
    if k in UNIONS and isinstance(v, list):
        ret = set(params.get(UNIONS[k][1]) or []) | set(communs.get(UNIONS[k][1]) or [])
        return unir(k, params.get(k) or [], v, ret)
    if k in ("identites_supprimees", "certificats_retires") and isinstance(v, list):
        return sorted(set(v) | set(params.get(k) or []))
    return v


def changements_communs(params):
    """None si rien de plus recent sur le Drive ; sinon {"par", "maj", "items": [{cle, libelle, detail, valeur}]}."""
    p = chemin_drive(params)
    if not p:
        return None
    c = (lire_drive(p).get("communs") or {})
    maj, par = c.get("maj") or "", c.get("par") or ""
    # proposes des qu'un autre poste les a ecrits et que vous ne les avez pas encore vus, quelle que soit la date :
    # la case est cochee d'avance seulement si l'autre poste est le plus recent
    if not maj or par == params.get("machine") or maj == (params.get("communs_drive_vu") or ""):
        return None
    local = params.get("communs_maj") or ""
    plus_recent_ailleurs = maj > local
    items = []
    for k in COMMUNS:
        # « (vide) -> google » n'est pas un changement : jamais regle ici = valeur par defaut, la meme
        if k not in c:
            continue
        val = _valeur_reprise(params, c, k, c[k])
        if not _meme(val, _effectif(params, k)) and not _meme(_effectif({k: val}, k), _effectif(params, k)):
            from .miroir import UNIONS
            items.append({"cle": k, "libelle": libelle_commun(k), "detail": decrire_changement(k, _effectif(params, k), val),
                          "valeur": val, "coche": plus_recent_ailleurs or k in UNIONS})
    return {"par": par, "maj": maj, "local": local, "items": items, "plus_recent_ailleurs": plus_recent_ailleurs}


DISPOSITION = ("volet_largeur", "vignettes_largeur", "biblio_replies")


def disposition_autre(params):
    """Disposition (largeur des volets, categories ouvertes) changee sur un autre poste : proposee ici, une fois.
    Chaque poste garde la sienne ; refusee, la question ne revient que si l'autre poste la change encore.
    Renvoie {"poste", "sig", "items": [{cle, libelle, detail, valeur}]} ou None."""
    p = chemin_drive(params)
    if not p:
        return None
    postes = lire_drive(p).get("postes") or {}
    moi = params.get("machine")
    autres = sorted(((v.get("maj") or "", m, v) for m, v in postes.items() if m != moi and isinstance(v, dict)
                     and any(k in v for k in DISPOSITION)), reverse=True)
    if not autres:
        return None
    _d, m, v = autres[0]
    sig = m + "|" + json.dumps({k: v.get(k) for k in DISPOSITION}, sort_keys=True)
    if sig == params.get("disposition_vue"):
        return None
    libs = {"volet_largeur": _("Largeur du volet de droite"), "vignettes_largeur": _("Largeur des vignettes"),
            "biblio_replies": _("Groupes ouverts ou fermés dans le volet des tampons")}
    items = []
    for k in DISPOSITION:
        if k in v and v[k] != params.get(k):
            if k == "biblio_replies":
                det = _("comme sur « {poste} »", poste=m)
            else:
                det = f"{params.get(k) or '-'} px  →  {v[k]} px"
            items.append({"cle": k, "libelle": libs[k], "detail": det, "valeur": v[k]})
    if not items:
        params["disposition_vue"] = sig
        params.enregistrer()
        return None
    return {"poste": m, "sig": sig, "items": items}


def appliquer_disposition(params, dispo, cles):
    """Reprend ce qui est coche ; dans tous les cas, cette disposition n'est plus proposee."""
    for it in dispo["items"]:
        if it["cle"] in cles:
            params[it["cle"]] = it["valeur"]
    params["disposition_vue"] = dispo["sig"]
    params.enregistrer()


def appliquer_communs(params, changements, cles):
    """Reprend seulement les reglages choisis ; les autres restent ceux de ce poste. On ne redemande pas ensuite."""
    garde_ici = False
    for it in changements["items"]:
        if it["cle"] in cles:
            params[it["cle"]] = it["valeur"]
        else:
            garde_ici = True
    params["communs_drive_vu"] = changements["maj"]
    # tout repris : ce poste est a egalite avec le Drive ; sinon ses valeurs gardees deviennent la reference (envoyees)
    params["communs_maj"] = datetime.datetime.now().isoformat(timespec="seconds") if garde_ici else changements["maj"]
    params._communs_vus = params._empreinte_communs() if hasattr(params, "_empreinte_communs") else ""
    params.enregistrer()


def secrets_nouveaux(params, phrase, secrets=None):
    """Secrets du Drive (ou ceux donnes) absents de ce poste : [{cle, libelle}] (jamais les valeurs)."""
    noms = {c["id"]: c.get("nom") or c["id"] for c in params.get("comptes", [])}
    out = []
    for k, v in (lire_secrets_drive(params, phrase) if secrets is None else secrets).items():
        if k.startswith("coffre:"):
            if v and not coffre.lire(k[7:]):
                cid, _p, suffixe = k[7:].partition(".")
                quoi = _("autorisation") if suffixe in ("jeton", "appareil") else _("mot de passe")
                out.append({"cle": k, "libelle": f"{quoi} : {noms.get(cid, cid)}"})
        elif k in CLEFS_IA and v and not params.get(k):
            out.append({"cle": k, "libelle": _("clef IA : {x}", x="Claude" if "claude" in k else "Gemini")})
        elif k.startswith("identite:") and v:
            from . import identites
            if not os.path.exists(identites._fichier(k.split(":", 1)[1])):
                out.append({"cle": k, "libelle": _("identité numérique : {x}", x=identites.nom_identite(params, k))})
    return out


def reprendre_secrets_choisis(params, phrase, cles):
    n = 0
    for k, v in lire_secrets_drive(params, phrase).items():
        if k not in cles:
            continue
        if k.startswith("coffre:"):
            coffre.enregistrer(k[7:], v)
        elif k.startswith("identite:"):
            from . import identites
            identites.reprendre_secret(params, k, v, ecraser=True)
        else:
            params[k] = v
        n += 1
    params.enregistrer()
    return n
