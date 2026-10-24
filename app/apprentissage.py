"""Ce que PhilPDF apprend de vos validations, partage entre vos postes.

Range dans <emplacement de synchronisation>/PhilPDF/apprentissage/ (a defaut, dans le dossier de donnees de ce
poste) et fusionne comme la session : chaque entree porte sa date « maj », la plus recente gagne, rien ne se perd
quand deux postes apprennent en meme temps.
  - classement.json : expediteur -> dossier ou ranger ses courriers ;
  - echeances.json  : echeances reperees dans les courriers classes ou resumes ;
  - ocr.json        : mots personnels et regles de correction de l'OCR validees.

Les dossiers sont enregistres sous une forme valable sur chaque poste : {documents}/Factures,
{telechargements}/..., {nas}/..., ou distant:<compte>:/chemin pour un NAS, un FTP ou un Drive.
"""
import datetime, json, os

from .config import dossier_donnees


def dossier(params):
    from .bibliotheque import dossier_philpdf_drive
    d = dossier_philpdf_drive(params)
    d = os.path.join(d, "apprentissage") if d else os.path.join(dossier_donnees(), "apprentissage")
    os.makedirs(d, exist_ok=True)
    return d


def maintenant():
    return datetime.datetime.now().isoformat(timespec="seconds")


def lire(params, nom):
    try:
        with open(os.path.join(dossier(params), nom), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def ecrire(params, nom, d):
    p = os.path.join(dossier(params), nom)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    os.replace(tmp, p)


# ------------------------------------------------------------------ dossiers valables sur chaque poste
def _racines(params):
    from .session import dossiers_connus
    r = dict(dossiers_connus())
    if params.get("nas"):
        r["nas"] = params["nas"]
    return sorted(((k, os.path.normpath(v)) for k, v in r.items() if v), key=lambda kv: -len(kv[1]))


def abstraire(chemin, params):
    if chemin.startswith("distant:"):
        return chemin
    c = os.path.normpath(chemin)
    for k, racine in _racines(params):
        if os.path.normcase(c) == os.path.normcase(racine) or os.path.normcase(c).startswith(os.path.normcase(racine) + os.sep):
            reste = c[len(racine):].strip("\\/").replace("\\", "/")
            return "{" + k + "}" + ("/" + reste if reste else "")
    return c


def concret(forme, params):
    if forme.startswith("distant:") or not forme.startswith("{"):
        return forme
    k, _sep, reste = forme[1:].partition("}")
    racine = dict(_racines(params)).get(k)
    if not racine:
        return ""
    return os.path.join(racine, *[x for x in reste.split("/") if x])


# ------------------------------------------------------------------ classement
def cle_expediteur(nom):
    import unicodedata
    n = unicodedata.normalize("NFKD", nom or "").encode("ascii", "ignore").decode().lower()
    return " ".join("".join(c if c.isalnum() else " " for c in n).split())


def dossier_appris(params, expediteur):
    e = lire(params, "classement.json").get("expediteurs", {}).get(cle_expediteur(expediteur))
    return concret(e["dossier"], params) if e else ""


def dossiers_connus_classement(params):
    """Dossiers deja utilises pour classer (formes concretes sur ce poste), les plus frequents d'abord."""
    vus = {}
    for e in lire(params, "classement.json").get("expediteurs", {}).values():
        c = concret(e.get("dossier", ""), params)
        if c:
            vus[c] = vus.get(c, 0) + e.get("n", 1)
    return [c for c, _n in sorted(vus.items(), key=lambda kv: -kv[1])]


def retenir_classement(params, expediteur, chemin_dossier):
    d = lire(params, "classement.json")
    ex = d.setdefault("expediteurs", {})
    k = cle_expediteur(expediteur)
    if not k:
        return
    ancien = ex.get(k, {})
    forme = abstraire(chemin_dossier, params)
    ex[k] = {"nom": expediteur, "dossier": forme, "n": (ancien.get("n", 0) + 1) if ancien.get("dossier") == forme else 1,
             "maj": maintenant()}
    ecrire(params, "classement.json", d)


# ------------------------------------------------------------------ echeances
def ajouter_echeance(params, date_iso, libelle, fichier):
    d = lire(params, "echeances.json")
    cle = f"{date_iso}|{os.path.basename(fichier)}"
    d.setdefault("echeances", {})[cle] = {"date": date_iso, "libelle": libelle, "fichier": abstraire(fichier, params),
                                         "maj": maintenant()}
    ecrire(params, "echeances.json", d)


def echeances_a_venir(params, jours=60):
    aujourd_hui = datetime.date.today().isoformat()
    fin = (datetime.date.today() + datetime.timedelta(days=jours)).isoformat()
    out = [e for e in lire(params, "echeances.json").get("echeances", {}).values()
           if not e.get("fait") and aujourd_hui <= e.get("date", "") <= fin]
    return sorted(out, key=lambda e: e["date"])


# ------------------------------------------------------------------ OCR
def ocr_appris(params):
    """{"mots": [...], "regles": {"avant→apres": {"n", "maj"}}} pour moteur.scan."""
    d = lire(params, "ocr.json")
    return {"mots": sorted(d.get("mots", {})), "regles": d.get("regles", {})}


def retenir_ocr(params, corrections):
    """corrections : [(lu par Tesseract, valide par vous)] ; les mots valides rejoignent les mots personnels,
    les remplacements d'un seul mot deviennent des regles (appliquees seules apres deux validations).
    Garder la lecture de Tesseract alors qu'une regle proposait autre chose affaiblit la regle."""
    d = lire(params, "ocr.json")
    mots, regles = d.setdefault("mots", {}), d.setdefault("regles", {})
    nb_mots, nb_regles = 0, 0
    for avant, apres in corrections:
        if avant == apres:
            for cle, v in regles.items():
                if cle.split("\u2192", 1)[0] == avant and v.get("n", 0) > 0:
                    v["n"] -= 1
                    v["maj"] = maintenant()
            continue
        for m in apres.split():
            m = m.strip(".,;:!?()[]«»\"“”")
            if len(m) >= 3 and any(c.isalpha() for c in m):
                nb_mots += m not in mots
                mots[m] = {"maj": maintenant()}
        if len(avant.split()) == 1 and len(apres.split()) == 1:
            cle = f"{avant}\u2192{apres}"
            v = regles.get(cle, {"n": 0})
            regles[cle] = {"n": v.get("n", 0) + 1, "maj": maintenant()}
            nb_regles += 1
    ecrire(params, "ocr.json", d)
    return nb_mots, nb_regles
