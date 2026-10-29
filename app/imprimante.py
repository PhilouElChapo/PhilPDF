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


def nom_installe():
    """Nom de l'imprimante PhilPDF dans Windows (retrouvee par son port, meme si vous l'avez renommee), ou ""."""
    if sys.platform != "win32":
        return ""
    port = fichier_port().replace("'", "''")
    try:
        code, out = _ps(f"Get-Printer -ErrorAction SilentlyContinue | Where-Object {{ $_.PortName -eq '{port}' }} | "
                        "Select-Object -First 1 | ForEach-Object { 'NOM=' + $_.Name }", timeout=30)
        for l in out.splitlines():
            if l.startswith("NOM="):
                return l[4:].strip()
    except Exception:
        pass
    return ""


def installee():
    return bool(nom_installe())


def etat():
    """Diagnostic : {nom, surveillance, travaux: [(document, etat)], fichier_en_attente}."""
    nom = nom_installe()
    travaux = []
    if nom:
        try:
            code, out = _ps(f"Get-PrintJob -PrinterName {_ps_chaine(nom)} -ErrorAction SilentlyContinue | "
                            "ForEach-Object { 'JOB=' + $_.DocumentName + '|' + $_.JobStatus }", timeout=30)
            travaux = [tuple(l[4:].split("|", 1)) for l in out.splitlines() if l.startswith("JOB=")]
        except Exception:
            pass
    return {"nom": nom, "surveillance": surveillance_active(), "travaux": travaux,
            "fichier_en_attente": os.path.exists(fichier_port())}


def renommer(nouveau):
    ancien = nom_installe()
    if not ancien or not nouveau or nouveau == ancien:
        return False, ""
    code, out = _ps(f"Rename-Printer -Name {_ps_chaine(ancien)} -NewName {_ps_chaine(nouveau)}", admin=True)
    return nom_installe() == nouveau, out.strip()[:300]


def page_essai():
    """Imprime une page de test de Windows sur l'imprimante PhilPDF (elle doit s'ouvrir dans PhilPDF)."""
    nom = nom_installe()
    if not nom:
        return False
    code, out = _ps(f"$p = Get-CimInstance Win32_Printer -Filter \"Name='{nom.replace(chr(39), chr(39) * 2)}'\"; "
                    "Invoke-CimMethod -InputObject $p -MethodName PrintTestPage | Out-Null", timeout=60)
    return code == 0


def prendre_impression():
    """Impression terminee dans le port (le pilote a fini d'ecrire) : renommee et renvoyee, sinon None.
    Utilise par PhilPDF ouvert (toutes les 2 secondes) ; la surveillance PowerShell fait de meme PhilPDF ferme."""
    import time
    p = fichier_port()
    try:
        if not os.path.exists(p) or os.path.getsize(p) == 0:
            return None
        if time.time() - os.path.getmtime(p) < 1.5:     # encore en cours d'ecriture
            return None
        with open(p, "r+b"):
            pass
        nom = os.path.join(dossier(), "Impression " + time.strftime("%Y-%m-%d %H-%M-%S") + ".pdf")
        os.replace(p, nom)
        return nom
    except OSError:
        return None


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


def installer(nom=None):
    """Cree l'imprimante (droits d'administrateur demandes par Windows) et la surveillance. Renvoie (ok, message)."""
    if sys.platform != "win32":
        return False, "Windows seulement pour l'instant (Linux : CUPS-PDF, plus tard)"
    port = fichier_port().replace("'", "''")
    script = (f"$ErrorActionPreference = 'Stop'; "
              f"if (-not (Get-PrinterPort -Name '{port}' -ErrorAction SilentlyContinue)) {{ Add-PrinterPort -Name '{port}' }}; "
              f"if (-not (Get-Printer -ErrorAction SilentlyContinue | Where-Object {{ $_.PortName -eq '{port}' }})) {{ "
              f"Add-Printer -Name '{(nom or NOM).replace(chr(39), chr(39) * 2)}' -DriverName 'Microsoft Print To PDF' "
              f"-PortName '{port}' }}")
    try:
        code, out = _ps(script, admin=True, timeout=180)
    except Exception as e:
        return False, str(e)
    if not installee():
        return False, (out.strip() or "installation refusée ou annulée")[:300]
    if nom and nom_installe() != nom:
        renommer(nom)
    ecrire_surveillance()
    lancer_surveillance()
    return True, ""


def desinstaller():
    port = fichier_port().replace("'", "''")
    nom = (nom_installe() or NOM).replace("'", "''")
    script = (f"Remove-Printer -Name '{nom}' -ErrorAction SilentlyContinue; "
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
        _n, dpi, qual, seuil = PREREGLAGES[2 if q == "leger" else 0]
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
