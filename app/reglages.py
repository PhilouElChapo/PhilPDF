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

COMMUNS = ["auteur", "langue", "outils_epingles", "zoom", "barre_rapide", "volet", "vignettes", "fixer_objets",
           "filigranes_perso", "ia_moteur", "maj_source", "maj_auto", "synchro", "comptes", "defaut_tampons",
           "defaut_signatures", "theme"]
POSTE = ["machine", "racines", "nas", "dernier_dossier", "drive", "drive_compte", "association_pdf"]
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
    d["communs"] = dict(i["communs"], maj=i["date"], par=i["machine"])
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
