"""Parametres de PhilPDF.

Mode portable : si un fichier 'portable.txt' est a cote de l'executable, tout
(parametres, session, tampons) est range dans le dossier 'donnees' a cote,
et rien n'est ecrit ailleurs sur le PC ni dans le registre.
"""
import json, os, platform, sys

APP = "PhilPDF"
VERSION = "0.9.39"
LANCE_PAR_IMPRIMANTE = False      # PhilPDF ouvert tout seul pour une impression : pas de question de mise a jour


def dossier_programme():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def est_portable():
    return os.path.exists(os.path.join(dossier_programme(), "portable.txt"))


def dossier_donnees():
    if est_portable():
        d = os.path.join(dossier_programme(), "donnees")
    elif sys.platform == "win32":
        d = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), APP)
    else:
        d = os.path.join(os.path.expanduser("~/.config"), APP.lower())
    os.makedirs(d, exist_ok=True)
    return d


DEFAUTS = {
    "machine": platform.node() or "Ce PC",
    "recents": [],
    "outils_epingles": ["modifier", "combiner", "remplir_signer", "imprimer", "alleger"],
    "zoom": 1.25,
    "theme": "clair",
    "drive": "",                    # racine du Drive sur ce PC (ex. G:\\Mon Drive) : sauvegarde + session
    "drive_restaure": False,
    "ia_moteur": "claude",
    "clef_claude": "",
    "clef_gemini": "",
    "association_pdf": False,
    "barre_rapide": True,
    "maj_source": "github",         # "github" ou "dossier" (dossier synchronise)
    "maj_auto": True,               # verifier au demarrage (une fois par jour)
    "maj_derniere": "",
    "racines": [],                  # emplacements supplementaires a fouiller (mode avance)
    "nas": "",                      # dossier du NAS sur ce poste
    "synchro": True,                # synchroniser les fichiers ouverts entre postes
    "dernier_dossier": "",
    "bienvenue_vue": False,         # assistant de premiere installation deja montre
    "drive_compte": "",             # Drive « en direct » (compte Google...) au lieu du dossier de l'appli de bureau
}


class Parametres(dict):
    def __init__(self):
        super().__init__(DEFAUTS)
        self.chemin = os.path.join(dossier_donnees(), "parametres.json")
        self.nouveau = not os.path.exists(self.chemin)      # premiere installation sur ce poste
        try:
            with open(self.chemin, encoding="utf-8") as f:
                self.update(json.load(f))
        except (OSError, ValueError):
            pass
        if self.get("dossier_synchro") and not self.get("drive"):   # ancienne 0.1
            self["drive"] = self.pop("dossier_synchro")
        self._communs_vus = self._empreinte_communs()

    def _empreinte_communs(self):
        try:
            from .reglages import COMMUNS
        except ImportError:
            return ""
        return json.dumps({k: self.get(k) for k in COMMUNS}, sort_keys=True, ensure_ascii=False, default=str)

    def enregistrer(self):
        e = self._empreinte_communs() if hasattr(self, "_communs_vus") else ""
        if e and e != self._communs_vus:          # un reglage commun a vraiment change sur ce poste : il est date
            import datetime
            self["communs_maj"] = datetime.datetime.now().isoformat(timespec="seconds")
            self._communs_vus = e
        try:
            with open(self.chemin, "w", encoding="utf-8") as f:
                json.dump(self, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def ajouter_recent(self, chemin):
        import datetime
        r = [p for p in self["recents"] if os.path.normcase(p) != os.path.normcase(chemin)]
        self["recents"] = [chemin] + r[:49]
        dates = dict(self.get("recents_dates") or {})
        dates[chemin] = datetime.datetime.now().isoformat(timespec="minutes")
        self["recents_dates"] = {p: dates[p] for p in self["recents"] if p in dates}
        self.enregistrer()

    # ---- session partagee : voir app/session.py
    def chemin_session(self):
        """La session (emplacements des fichiers ouverts, pas les fichiers) vit sur le Drive."""
        try:
            from .bibliotheque import dossier_philpdf_drive
            d = dossier_philpdf_drive(self)          # copie locale du compte de synchronisation, jamais un ancien chemin
        except Exception:
            d = None
        if d:
            os.makedirs(d, exist_ok=True)
            return os.path.join(d, "session.json")
        return os.path.join(dossier_donnees(), "session.json")


def associer_pdf(activer):
    """Association .pdf -> PhilPDF pour l'utilisateur courant (Windows), reversible."""
    if sys.platform != "win32":
        return False
    import winreg
    exe = sys.executable if getattr(sys, "frozen", False) else f'"{sys.executable}" "{os.path.abspath(sys.argv[0])}"'
    cle = r"Software\Classes\PhilPDF.Document"
    if activer:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, cle + r"\shell\open\command") as k:
            winreg.SetValue(k, "", winreg.REG_SZ, f'{exe} "%1"' if getattr(sys, "frozen", False) else f'{exe} "%1"')
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\.pdf\OpenWithProgids") as k:
            winreg.SetValueEx(k, "PhilPDF.Document", 0, winreg.REG_NONE, b"")
    else:
        for c in (cle + r"\shell\open\command", cle + r"\shell\open", cle + r"\shell", cle):
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, c)
            except OSError:
                pass
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\.pdf\OpenWithProgids", 0, winreg.KEY_SET_VALUE) as k:
                winreg.DeleteValue(k, "PhilPDF.Document")
        except OSError:
            pass
    return True
