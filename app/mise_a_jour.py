"""Mises a jour de PhilPDF.

Deux sources possibles (Parametres) :
 - "github"  : derniere version publiee sur GitHub (Releases du depot PhilPDF) ;
 - "dossier" : un fichier PhilPDF_version.json depose dans <Drive>/PhilPDF,
               pratique pour mettre a jour toutes ses machines sans Internet direct.

Application :
 - version portable : le nouveau zip est decompresse puis recopie par-dessus le programme
   une fois PhilPDF ferme (le dossier 'donnees' et portable.txt sont conserves) ;
 - version installee : l'installateur se lance en mode silencieux ;
 - Linux : simple avertissement pour l'instant.
"""
import json, os, subprocess, sys, tempfile, urllib.error, urllib.request, zipfile
from .config import VERSION, est_portable, dossier_programme

DEPOT = "PhilouElChapo/PhilPDF"


def _v(t):
    return tuple(int(x) for x in t.lstrip("vV").split(".") if x.isdigit())


class _SansRedirection(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def _statut(url):
    """(code HTTP, adresse de redirection) sans suivre la redirection."""
    from .reseau import ouvrir
    try:
        with ouvrir(urllib.request.Request(url, method="HEAD", headers={"User-Agent": "PhilPDF"}), 10,
                    _SansRedirection) as r:
            return r.status, r.headers.get("Location", "")
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Location", "") if e.headers else ""


def _depuis_page(nom):
    """Sans l'API de GitHub (limitee a 60 demandes par heure et par adresse Internet : vite atteint avec deux postes
    derriere la meme box) : la page « derniere version » redirige vers .../tag/vX.Y.Z."""
    code, ou = _statut(f"https://github.com/{DEPOT}/releases/latest")
    tag = (ou or "").rstrip("/").rsplit("/", 1)[-1]
    if code not in (301, 302, 303, 307, 308) or not tag.lower().startswith("v"):
        raise ValueError(f"GitHub {code}")
    paquet = f"https://github.com/{DEPOT}/releases/download/{tag}/{nom}"
    code, _ou = _statut(paquet)
    if code == 404:
        paquet = None                                       # version annoncee, paquet pas encore depose
    elif code not in (200, 301, 302, 303, 307, 308):
        raise ValueError(f"GitHub {code}")
    return tag, paquet, ""


def chercher(params):
    """Version plus recente : (version, paquet, notes). A jour : None.
    Sinon un dict : {"preparation": version} (publiee, paquet en cours de fabrication) ou {"erreur": texte}
    (pas de reponse : on ne pretend plus que tout est a jour)."""
    source = params.get("maj_source", "github")
    nom = "PhilPDF_portable.zip" if est_portable() else "PhilPDF_Setup.exe"
    try:
        from .bibliotheque import dossier_philpdf_drive
        dd = dossier_philpdf_drive(params) if source == "dossier" else None
        if dd:
            p = os.path.join(dd, "PhilPDF_version.json")
            with open(p, encoding="utf-8") as f:
                info = json.load(f)
            version = info["version"]
            paquet = os.path.join(dd, info["portable" if est_portable() else "installateur"])
            notes = info.get("notes", "")
        else:
            try:
                req = urllib.request.Request(f"https://api.github.com/repos/{DEPOT}/releases/latest",
                                             headers={"User-Agent": "PhilPDF", "Accept": "application/vnd.github+json"})
                from .reseau import ouvrir
                with ouvrir(req, 10) as r:
                    info = json.load(r)
                version = info["tag_name"]
                paquet = next((a["browser_download_url"] for a in info.get("assets", []) if a["name"] == nom), None)
                notes = info.get("body", "")
            except Exception:                               # noqa: BLE001 (limite de l'API, panne passagere)
                version, paquet, notes = _depuis_page(nom)
        if _v(version) > _v(VERSION):
            if not paquet:
                return {"preparation": version.lstrip("vV")}
            return version, paquet, notes
    except Exception as e:                                  # noqa: BLE001
        return {"erreur": str(e) or e.__class__.__name__}
    return None


def recuperer(paquet, progression=None, arret=lambda: False):
    """Telecharge le paquet (ou le prend dans le dossier synchronise). progression(fait, total)."""
    if os.path.exists(paquet):
        return paquet
    dest = os.path.join(tempfile.mkdtemp(), os.path.basename(paquet.split("?")[0]))
    req = urllib.request.Request(paquet, headers={"User-Agent": "PhilPDF"})
    from .reseau import ouvrir
    with ouvrir(req, 60) as r, open(dest, "wb") as f:
        total, fait = int(r.headers.get("Content-Length") or 0), 0
        while True:
            if arret():
                raise RuntimeError("annule")
            b = r.read(1 << 20)
            if not b:
                break
            f.write(b)
            fait += len(b)
            if progression:
                progression(fait, total)
    if fichier_valide(dest):
        return dest
    raise RuntimeError("paquet incomplet")


def fichier_valide(f):
    if f.lower().endswith(".zip"):
        try:
            with zipfile.ZipFile(f) as z:
                return "PhilPDF.exe" in z.namelist()
        except zipfile.BadZipFile:
            return False
    return os.path.getsize(f) > 10_000_000


def debloquer():
    """Windows marque les fichiers sortis d'un zip telecharge (« Mark of the Web ») : d'ou l'avertissement
    « L'editeur n'a pas pu etre verifie » a chaque lancement. PhilPDF ayant deja ete lance par
    l'utilisateur, on retire cette marque de ses propres fichiers (comme Proprietes > Debloquer)."""
    if not possible():
        return 0
    n = 0
    for base, _d, fichiers in os.walk(dossier_programme()):
        for f in fichiers:
            if f.lower().endswith((".exe", ".dll", ".pyd")):
                try:
                    os.remove(os.path.join(base, f) + ":Zone.Identifier")
                    n += 1
                except OSError:
                    pass
    return n


def possible():
    return sys.platform == "win32" and getattr(sys, "frozen", False)


def appliquer(fichier):
    """Lance la mise a jour a partir du paquet deja telecharge ; PhilPDF doit se fermer juste apres."""
    if not possible():
        return False
    if fichier.lower().endswith(".exe"):
        subprocess.Popen([fichier, "/SILENT", "/CLOSEAPPLICATIONS", "/RESTARTAPPLICATIONS"], close_fds=True)
        return True
    tmp = tempfile.mkdtemp()
    with zipfile.ZipFile(fichier) as z:
        z.extractall(tmp)
    prog = dossier_programme()
    script = os.path.join(tmp, "maj_philpdf.bat")
    with open(script, "w", encoding="mbcs") as f:
        f.write("@echo off\r\n"
                f"echo Mise a jour de PhilPDF...\r\n"
                f":attente\r\ntasklist /FI \"PID eq {os.getpid()}\" | find \"{os.getpid()}\" >nul && (timeout /t 1 >nul & goto attente)\r\n"
                f'robocopy "{tmp}" "{prog}" /E /R:5 /W:1 /XD donnees /XF portable.txt maj_philpdf.bat >nul\r\n'
                f'start "" "{os.path.join(prog, "PhilPDF.exe")}"\r\n')
    subprocess.Popen(["cmd", "/c", script], creationflags=0x08000000, close_fds=True)
    return True
