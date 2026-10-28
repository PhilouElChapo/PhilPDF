"""Imprimante « PhilPDF » : depuis n'importe quel logiciel, Imprimer > PhilPDF ouvre le resultat dans PhilPDF
(comme l'imprimante Adobe PDF).

Windows : une imprimante qui utilise le pilote « Microsoft Print to PDF » de Windows (polices integrees au PDF),
reliee a un fichier du dossier d'impression de PhilPDF au lieu d'un port physique. Une petite surveillance (lancee
a l'ouverture de session, sans fenetre) voit arriver chaque impression et la donne a PhilPDF. L'installation de
l'imprimante demande une fois les droits d'administrateur (fenetre de Windows).
"""
import os
import subprocess
import sys

NOM = "PhilPDF"


def dossier():
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/.local/share")
    d = os.path.join(base, "PhilPDF", "impression")
    os.makedirs(d, exist_ok=True)
    return d


def fichier_port():
    return os.path.join(dossier(), "impression_en_cours.pdf")


def _ps(script, admin=False, timeout=120):
    flags = 0x08000000 if sys.platform == "win32" else 0
    if admin:                                            # fenetre de Windows « Autoriser les modifications ? »
        import base64
        enc = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
        script = ("$p = Start-Process powershell -Verb RunAs -Wait -PassThru -WindowStyle Hidden "
                  f"-ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-EncodedCommand','{enc}'; exit $p.ExitCode")
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
                       capture_output=True, text=True, timeout=timeout, creationflags=flags, encoding="utf-8",
                       errors="replace")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def installee():
    if sys.platform != "win32":
        return False
    try:
        code, out = _ps(f"if (Get-Printer -Name '{NOM}' -ErrorAction SilentlyContinue) {{ 'oui' }}", timeout=30)
        return "oui" in out
    except Exception:
        return False


def _commande():
    """(programme, [arguments avant le fichier]) qui lancent PhilPDF : l'exe fabrique, ou python + philpdf.py."""
    if getattr(sys, "frozen", False):
        return sys.executable, []
    racine = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return sys.executable, [os.path.join(racine, "philpdf.py")]


def _ps_chaine(t):
    return "'" + t.replace("'", "''") + "'"


def _script_surveillance():
    """Surveillance du dossier d'impression (PowerShell, sans fenetre) : chaque impression terminee est renommee
    puis donnee a PhilPDF (qui s'ouvre s'il ne l'etait pas, sinon il la recoit dans sa fenetre)."""
    exe, avant = _commande()
    args = " ".join(f'"`"{a}`""' for a in avant)
    return f"""$port = {_ps_chaine(fichier_port())}
$dossier = {_ps_chaine(dossier())}
while ($true) {{
  if (Test-Path -LiteralPath $port) {{
    try {{
      $f = [System.IO.File]::Open($port, 'Open', 'ReadWrite', 'None'); $f.Close()
      Start-Sleep -Milliseconds 400
      $nom = Join-Path $dossier ('Impression ' + (Get-Date -Format 'yyyy-MM-dd HH-mm-ss') + '.pdf')
      Move-Item -LiteralPath $port -Destination $nom -Force
      Start-Process -FilePath {_ps_chaine(exe)} -ArgumentList @({args + ", " if args else ""}'--impression', "`"$nom`"")
    }} catch {{ }}
  }}
  Start-Sleep -Seconds 1
}}
"""


def _demarrage():
    """Lanceur de la surveillance a l'ouverture de session (dossier Demarrage de l'utilisateur, sans droits)."""
    d = os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows", "Start Menu", "Programs", "Startup")
    return os.path.join(d, "PhilPDF imprimante.vbs")


def ecrire_surveillance():
    ps1 = os.path.join(dossier(), "surveillance.ps1")
    with open(ps1, "w", encoding="utf-8-sig") as f:
        f.write(_script_surveillance())
    vbs = _demarrage()
    os.makedirs(os.path.dirname(vbs), exist_ok=True)
    with open(vbs, "w", encoding="utf-16") as f:
        f.write('CreateObject("WScript.Shell").Run "powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden '
                f'-File ""{ps1}""", 0, False\r\n')
    return vbs


def lancer_surveillance():
    """Demarre la surveillance tout de suite (sinon elle demarre a la prochaine ouverture de session)."""
    vbs = _demarrage()
    if sys.platform == "win32" and os.path.exists(vbs):
        if not surveillance_active():
            subprocess.Popen(["wscript", vbs], creationflags=0x08000000)


def surveillance_active():
    if sys.platform != "win32":
        return False
    try:
        code, out = _ps("Get-CimInstance Win32_Process -Filter \"Name='powershell.exe'\" | "
                        "Where-Object { $_.CommandLine -like '*PhilPDF*surveillance.ps1*' } | "
                        "Select-Object -First 1 | ForEach-Object { 'oui' }", timeout=30)
        return "oui" in out
    except Exception:
        return False


def installer():
    """Cree l'imprimante (droits d'administrateur demandes par Windows) et la surveillance. Renvoie (ok, message)."""
    if sys.platform != "win32":
        return False, "Windows seulement pour l'instant (Linux : CUPS-PDF, plus tard)"
    port = fichier_port().replace("'", "''")
    script = (f"$ErrorActionPreference = 'Stop'; "
              f"if (-not (Get-PrinterPort -Name '{port}' -ErrorAction SilentlyContinue)) {{ Add-PrinterPort -Name '{port}' }}; "
              f"if (-not (Get-Printer -Name '{NOM}' -ErrorAction SilentlyContinue)) {{ "
              f"Add-Printer -Name '{NOM}' -DriverName 'Microsoft Print To PDF' -PortName '{port}' }}")
    try:
        code, out = _ps(script, admin=True, timeout=180)
    except Exception as e:
        return False, str(e)
    if not installee():
        return False, (out.strip() or "installation refusée ou annulée")[:300]
    ecrire_surveillance()
    lancer_surveillance()
    return True, ""


def desinstaller():
    port = fichier_port().replace("'", "''")
    script = (f"Remove-Printer -Name '{NOM}' -ErrorAction SilentlyContinue; "
              f"Start-Sleep -Seconds 2; Remove-PrinterPort -Name '{port}' -ErrorAction SilentlyContinue")
    try:
        _ps(script, admin=True, timeout=120)
    except Exception:
        pass
    try:
        os.remove(_demarrage())
    except OSError:
        pass
    try:
        _ps("Get-CimInstance Win32_Process -Filter \"Name='powershell.exe'\" | Where-Object { $_.CommandLine -like "
            "'*PhilPDF*surveillance.ps1*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }", timeout=30)
    except Exception:
        pass
    return not installee()


def en_attente():
    """Impressions arrivees pendant que PhilPDF etait ferme (et pas encore ouvertes) : [chemin]."""
    d = dossier()
    return sorted(os.path.join(d, f) for f in os.listdir(d) if f.startswith("Impression ") and f.lower().endswith(".pdf"))


def traiter(chemin, reglages):
    """Applique les reglages de l'imprimante a une impression : qualite (comme les « Parametres par defaut » d'Adobe),
    infos du document, PDF/A. Renvoie les octets du PDF."""
    import pymupdf as fitz
    q = reglages.get("qualite", "standard")
    with open(chemin, "rb") as f:
        octets = f.read()
    if q in ("leger", "standard"):
        from .alleger import alleger, PREREGLAGES
        _n, dpi, qual, seuil = PREREGLAGES[2 if q == "leger" else 1]
        octets = alleger(octets, {"images": True, "dpi": dpi, "qualite": qual, "seuil": seuil, "gris": False,
                                  "polices": True, "nettoyer": True, "infos": False, "jbig2": True,
                                  "noir_blanc": False, "polices_formulaire": True})
    d = fitz.open("pdf", octets)
    if reglages.get("infos", True):
        m = dict(d.metadata or {})
        m["creator"] = m.get("creator") or "PhilPDF"
        m["producer"] = "PhilPDF (imprimante)"
        if reglages.get("auteur"):
            m["author"] = reglages["auteur"]
        d.set_metadata(m)
    if q == "pdfa":
        from moteur import pdfa
        pdfa.convertir(d)
        return pdfa.octets(d)
    return d.tobytes(garbage=3, deflate=True)
