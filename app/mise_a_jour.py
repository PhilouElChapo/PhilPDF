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
import json, os, subprocess, sys, tempfile, urllib.request, zipfile
from .config import VERSION, est_portable, dossier_programme

DEPOT = "PhilouElChapo/PhilPDF"


def _v(t):
    return tuple(int(x) for x in t.lstrip("vV").split(".") if x.isdigit())


def chercher(params):
    """Renvoie (version, url_ou_chemin_du_paquet, notes) si une version plus recente existe, sinon None."""
    source = params.get("maj_source", "github")
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
            req = urllib.request.Request(f"https://api.github.com/repos/{DEPOT}/releases/latest",
                                         headers={"User-Agent": "PhilPDF", "Accept": "application/vnd.github+json"})
            with urllib.request.urlopen(req, timeout=8) as r:
                info = json.load(r)
            version = info["tag_name"]
            nom = "PhilPDF_portable.zip" if est_portable() else "PhilPDF_Setup.exe"
            paquet = next((a["browser_download_url"] for a in info.get("assets", []) if a["name"] == nom), None)
            notes = info.get("body", "")
        if paquet and _v(version) > _v(VERSION):
            return version, paquet, notes
    except Exception:
        return None
    return None


def _recuperer(paquet):
    if os.path.exists(paquet):
        return paquet
    dest = os.path.join(tempfile.mkdtemp(), os.path.basename(paquet.split("?")[0]))
    req = urllib.request.Request(paquet, headers={"User-Agent": "PhilPDF"})
    with urllib.request.urlopen(req, timeout=60) as r, open(dest, "wb") as f:
        while True:
            b = r.read(1 << 20)
            if not b:
                break
            f.write(b)
    return dest


def appliquer(paquet):
    """Prepare la mise a jour ; PhilPDF doit se fermer juste apres (renvoie True si lancee)."""
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        return False
    fichier = _recuperer(paquet)
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
                f'robocopy "{tmp}" "{prog}" /E /XD donnees /XF portable.txt maj_philpdf.bat >nul\r\n'
                f'start "" "{os.path.join(prog, "PhilPDF.exe")}"\r\n')
    subprocess.Popen(["cmd", "/c", script], creationflags=0x08000000, close_fds=True)
    return True
