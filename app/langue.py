"""Traduction de PhilPDF.

Le logiciel est ecrit en francais : chaque texte affiche passe par _("texte francais").
Les autres langues sont des fichiers langues/<code>.json  {"texte francais": "traduction"}.
Une traduction vide ou absente laisse le francais. Pour ajouter une langue : copier en.json,
le renommer (es.json, de.json...), traduire les valeurs, et c'est tout.

Langue : variable PHILPDF_LANGUE, sinon le reglage "langue" des Preferences, sinon la langue du
systeme si un fichier existe pour elle, sinon le francais. Le choix est fait une fois, au demarrage
(avant la creation des menus et des tables d'outils) ; changer de langue demande de relancer PhilPDF.
"""
import json, locale, os, re, sys

SOURCE = "fr"
NOMS = {"fr": "Français", "en": "English", "es": "Español", "de": "Deutsch", "it": "Italiano", "pt": "Português",
        "nl": "Nederlands"}


def dossier_langues():
    base = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "langues")


def disponibles():
    """[(code, nom)] : le francais + chaque fichier langues/*.json."""
    out = [(SOURCE, NOMS[SOURCE])]
    try:
        for f in sorted(os.listdir(dossier_langues())):
            if f.endswith(".json") and f[:-5] != SOURCE:
                out.append((f[:-5], NOMS.get(f[:-5], f[:-5])))
    except OSError:
        pass
    return out


def langue_systeme():
    for v in ("LC_ALL", "LC_MESSAGES", "LANG"):
        if os.environ.get(v):
            return os.environ[v][:2].lower()
    try:
        if sys.platform == "win32":
            import ctypes
            return locale.windows_locale.get(ctypes.windll.kernel32.GetUserDefaultUILanguage(), "fr")[:2]
        return (locale.getlocale()[0] or "fr")[:2].lower()
    except Exception:
        return SOURCE


def _reglage():
    """Lit le reglage dans parametres.json sans importer config (pas d'import circulaire)."""
    try:
        from .config import dossier_donnees
        with open(os.path.join(dossier_donnees(), "parametres.json"), encoding="utf-8") as f:
            return json.load(f).get("langue", "auto")
    except Exception:
        return "auto"


def choisir():
    codes = {c for c, _x in disponibles()}
    voulu = os.environ.get("PHILPDF_LANGUE") or _reglage()
    if voulu in (None, "", "auto"):
        voulu = langue_systeme()
    return voulu if voulu in codes else SOURCE


LANGUE = choisir()
_TABLE = {}
if LANGUE != SOURCE:
    try:
        with open(os.path.join(dossier_langues(), LANGUE + ".json"), encoding="utf-8") as f:
            _TABLE = {k: v for k, v in json.load(f).items() if v and not k.startswith("_")}
    except (OSError, ValueError):
        _TABLE = {}


def _(texte, **valeurs):
    """Texte traduit ; les {noms} sont remplaces par les valeurs donnees.
    Un suffixe de contexte « |mot » distingue deux sens du meme mot francais (« Annuler|action »
    = annuler la derniere action, « Annuler » = bouton d'abandon) ; il n'est jamais affiche."""
    t = _TABLE.get(texte)
    if t is None:
        t = texte.split("|")[0] if "|" in texte and re.search(r"\|[a-z_]+$", texte) else texte
    if valeurs:
        try:
            return t.format(**valeurs)
        except (KeyError, IndexError, ValueError):
            return texte.split("|")[0].format(**valeurs)
    return t
