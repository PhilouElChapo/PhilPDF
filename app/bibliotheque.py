"""Bibliotheque personnelle : tampons, signatures, filigranes.

Doctrine :
 - tout est range EN LOCAL (dossier de donnees de PhilPDF) : PhilPDF marche sans Internet ;
 - le Drive (Google Drive, OneDrive, Dropbox... via leur dossier sur le PC) sert de
   SAUVEGARDE : PhilPDF y recopie la bibliotheque dans <Drive>/PhilPDF/sauvegarde et
   sait la restaurer sur une autre machine ;
 - la session partagee ne contient que des EMPLACEMENTS de fichiers, jamais les PDF.
"""
import hashlib, json, os, shutil, string, sys, time, uuid
from .config import dossier_donnees

GENRES = ("tampons", "signatures", "filigranes")


# ------------------------------------------------------------------ Drive
def detecter_clouds():
    """Dossiers de synchronisation presents sur ce PC : [(nom, chemin)]."""
    trouves, maison = [], os.path.expanduser("~")

    def ajoute(nom, p):
        if p and os.path.isdir(p) and all(os.path.normcase(p) != os.path.normcase(q) for _, q in trouves):
            trouves.append((nom, p))
    if sys.platform == "win32":
        for lettre in string.ascii_uppercase:
            for sous in ("Mon Drive", "My Drive"):
                ajoute(f"Google Drive ({lettre}:)", f"{lettre}:\\{sous}")
    for sous in ("Google Drive\\Mon Drive", "Google Drive\\My Drive", "Google Drive", "GoogleDrive", "Mon Drive", "My Drive"):
        ajoute("Google Drive", os.path.join(maison, *sous.split("\\")))
    for var in ("OneDriveConsumer", "OneDrive", "OneDriveCommercial"):
        ajoute("OneDrive", os.environ.get(var))
    ajoute("OneDrive", os.path.join(maison, "OneDrive"))
    for base in (os.environ.get("APPDATA", ""), os.environ.get("LOCALAPPDATA", ""), os.path.join(maison, ".dropbox")):
        info = os.path.join(base, "Dropbox", "info.json") if base and not base.endswith(".dropbox") else os.path.join(base, "info.json")
        try:
            with open(info, encoding="utf-8") as f:
                for v in json.load(f).values():
                    ajoute("Dropbox", v.get("path"))
        except (OSError, ValueError, AttributeError):
            pass
    ajoute("Dropbox", os.path.join(maison, "Dropbox"))
    return trouves


def dossier_philpdf_drive(params):
    racine = params.get("drive") or ""
    if not racine or not os.path.isdir(racine):
        return None
    d = os.path.join(racine, "PhilPDF")
    os.makedirs(d, exist_ok=True)
    return d


# ------------------------------------------------------------------ bibliotheque locale
class Bibliotheque:
    def __init__(self, params):
        self.params = params
        self.racine = os.path.join(dossier_donnees(), "bibliotheque")
        for g in GENRES:
            os.makedirs(os.path.join(self.racine, g), exist_ok=True)
        self.index_chemin = os.path.join(self.racine, "index.json")
        try:
            with open(self.index_chemin, encoding="utf-8") as f:
                self.index = json.load(f)
        except (OSError, ValueError):
            self.index = []

    def _ecrire(self):
        with open(self.index_chemin, "w", encoding="utf-8") as f:
            json.dump(self.index, f, ensure_ascii=False, indent=1)

    def elements(self, genre):
        return [e for e in self.index if e["genre"] == genre and os.path.exists(self.fichier(e))]

    def fichier(self, e):
        return os.path.join(self.racine, e["genre"], e["id"] + e.get("ext", ".pdf"))

    def lire(self, e):
        with open(self.fichier(e), "rb") as f:
            return f.read()

    def ajouter(self, genre, nom, octets, ext=".pdf", **extra):
        h = hashlib.sha1(octets).hexdigest()
        for e in self.index:
            if e["genre"] == genre and e.get("hash") == h:
                return e
        e = {"id": uuid.uuid4().hex[:12], "genre": genre, "nom": nom, "ext": ext, "hash": h,
             "date": time.strftime("%Y-%m-%d %H:%M"), "machine": self.params.get("machine", ""), **extra}
        with open(self.fichier(e), "wb") as f:
            f.write(octets)
        self.index.append(e)
        self._ecrire()
        self._auto()
        return e

    def renommer(self, e, nom):
        e["nom"] = nom
        self._ecrire()
        self._auto()

    def supprimer(self, e):
        try:
            os.remove(self.fichier(e))
        except OSError:
            pass
        self.index = [x for x in self.index if x["id"] != e["id"]]
        e["supprime"] = True
        self._ecrire()
        if e.get("hash"):
            self.params["biblio_supprimes"] = sorted(self._supprimes_ici() | {e["hash"]})
            self.params.enregistrer()
        self._auto()

    def par_defaut(self, genre, e=None):
        cle = f"defaut_{genre}"
        if e is not None:
            self.params[cle] = e["id"]
            self.params.enregistrer()
        ident = self.params.get(cle)
        el = self.elements(genre)
        return next((x for x in el if x["id"] == ident), el[0] if el else None)

    # ---- synchronisation avec le Drive (dans les deux sens)
    def _distant(self):
        """(elements, supprimes) de la sauvegarde du Drive. Ancien format : simple liste."""
        d = dossier_philpdf_drive(self.params)
        try:
            with open(os.path.join(d, "sauvegarde", "index.json"), encoding="utf-8") as f:
                x = json.load(f)
        except (OSError, ValueError, TypeError):
            return [], set()
        if isinstance(x, list):
            return x, set()
        return x.get("elements", []), set(x.get("supprimes", []))

    def _supprimes_ici(self):
        return set(self.params.get("biblio_supprimes", []))

    def nouveautes_drive(self):
        """Elements presents dans la sauvegarde du Drive mais pas ici (et pas supprimes)."""
        if not dossier_philpdf_drive(self.params):
            return []
        distant, supp = self._distant()
        ici = {e.get("hash") for e in self.index}
        supp |= self._supprimes_ici()
        return [e for e in distant if e.get("hash") not in ici and e.get("hash") not in supp]

    def synchroniser_drive(self):
        """Recupere ce que les autres postes ont ajoute, applique leurs suppressions, puis envoie
        ce qui manque sur le Drive. Renvoie (recus, envoyes) ou None sans Drive."""
        d = dossier_philpdf_drive(self.params)
        if not d:
            return None
        cible = os.path.join(d, "sauvegarde")
        for g in GENRES:
            os.makedirs(os.path.join(cible, g), exist_ok=True)
        distant, supp = self._distant()
        supp |= self._supprimes_ici()
        recus = envoyes = 0
        # suppressions faites ailleurs
        avant = len(self.index)
        for e in [x for x in self.index if x.get("hash") in supp]:
            try:
                os.remove(self.fichier(e))
            except OSError:
                pass
        self.index = [x for x in self.index if x.get("hash") not in supp]
        # ajouts faits ailleurs
        ici = {e.get("hash") for e in self.index}
        for e in distant:
            if e.get("hash") in ici or e.get("hash") in supp:
                continue
            src = os.path.join(cible, e["genre"], e["id"] + e.get("ext", ".pdf"))
            if os.path.exists(src):
                shutil.copy2(src, self.fichier(e))
                self.index.append(e)
                ici.add(e.get("hash"))
                recus += 1
        # envoi de ce qui manque
        for e in self.index:
            dst = os.path.join(cible, e["genre"], e["id"] + e.get("ext", ".pdf"))
            if not os.path.exists(dst):
                shutil.copy2(self.fichier(e), dst)
                envoyes += 1
        with open(os.path.join(cible, "index.json"), "w", encoding="utf-8") as f:
            json.dump({"elements": self.index, "supprimes": sorted(supp)}, f, ensure_ascii=False, indent=1)
        if recus or len(self.index) != avant:
            self._ecrire()
        return recus, envoyes

    def _auto(self):
        if self.params.get("drive"):
            try:
                self.synchroniser_drive()
            except OSError:
                pass

    # anciens noms
    def sauvegarder_drive(self, silencieux=False):
        r = self.synchroniser_drive()
        return (0 if silencieux else None) if r is None else r[1]

    def restaurer_drive(self):
        r = self.synchroniser_drive()
        return 0 if r is None else r[0]
