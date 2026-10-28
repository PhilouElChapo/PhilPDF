"""Retrouver les identites numeriques deja sur ce PC, pour les importer sans manipulation :

- les « Fichiers d'ID numériques » d'Acrobat : ce sont deja des fichiers .pfx, ranges dans
  %APPDATA%\\Adobe\\Acrobat\\<version>\\Security (le bouton « Exporter » d'Acrobat ne donne que le certificat,
  sans la clef : .fdf, .p7c, .cer, inutilisables pour signer) ;
- les ID ranges dans le magasin de certificats de Windows (« Magasin de certificats Windows » dans Acrobat) :
  exportes en .pfx par PowerShell, avec un mot de passe choisi pour PhilPDF.
"""
import datetime as _dt
import glob
import os
import subprocess
import sys
import tempfile


def fichiers_acrobat():
    """[(chemin, date de modification)] des .pfx / .p12 d'Acrobat et Acrobat Reader sur ce poste."""
    racines = []
    if sys.platform == "win32":
        for v in ("APPDATA", "LOCALAPPDATA"):
            if os.environ.get(v):
                racines.append(os.path.join(os.environ[v], "Adobe"))
    else:
        racines.append(os.path.expanduser("~/.adobe"))
    vus, out = set(), []
    for r in racines:
        for motif in ("**/Security/*.pfx", "**/Security/*.p12", "**/Security/*.PFX"):
            for f in glob.glob(os.path.join(r, motif), recursive=True):
                k = os.path.normcase(os.path.abspath(f))
                if k in vus:
                    continue
                vus.add(k)
                try:
                    out.append((f, _dt.datetime.fromtimestamp(os.path.getmtime(f))))
                except OSError:
                    pass
    out.sort(key=lambda x: x[1], reverse=True)
    return out


def _powershell(script, timeout=40):
    flags = 0x08000000 if sys.platform == "win32" else 0          # CREATE_NO_WINDOW
    script = "[Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; " + script
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
                       capture_output=True, text=True, timeout=timeout, creationflags=flags, encoding="utf-8",
                       errors="replace")
    return r.returncode, r.stdout, r.stderr


def windows_identites():
    """Certificats AVEC clef privee du magasin « Personnel » de Windows : [{empreinte, sujet, nom, emetteur, fin}]."""
    if sys.platform != "win32":
        return []
    script = ("[Console]::OutputEncoding=[Text.Encoding]::UTF8; "
              "Get-ChildItem Cert:\\CurrentUser\\My | Where-Object { $_.HasPrivateKey } | ForEach-Object { "
              "$n = $_.GetNameInfo([Security.Cryptography.X509Certificates.X509NameType]::SimpleName, $false); "
              "$i = $_.GetNameInfo([Security.Cryptography.X509Certificates.X509NameType]::SimpleName, $true); "
              "\"$($_.Thumbprint)`t$n`t$i`t$($_.NotAfter.ToString('o'))`t$($_.Subject)`t$([Convert]::ToBase64String($_.RawData))\" }")
    try:
        code, sortie, _e = _powershell(script)
    except (OSError, subprocess.SubprocessError):
        return []
    out = []
    for l in sortie.splitlines():
        p = l.strip().split("\t")
        if len(p) >= 5 and p[0]:
            out.append({"empreinte": p[0], "nom": p[1], "emetteur": p[2], "fin": p[3], "sujet": p[4],
                        "der": p[5] if len(p) > 5 else ""})
    return out


class ErreurExport(Exception):
    pass


def windows_exporter(empreinte, mot_de_passe):
    """Exporte l'ID (certificat + clef) du magasin Windows en .pfx protege par mot_de_passe ; renvoie ses octets."""
    if not all(c in "0123456789abcdefABCDEF" for c in empreinte):
        raise ErreurExport("empreinte")
    f = os.path.join(tempfile.mkdtemp(prefix="philpdf-id-"), "id.pfx")
    mdp = mot_de_passe.replace("'", "''")
    script = (f"$p = ConvertTo-SecureString -String '{mdp}' -Force -AsPlainText; "
              f"Export-PfxCertificate -Cert 'Cert:\\CurrentUser\\My\\{empreinte}' -FilePath '{f}' -Password $p | Out-Null")
    try:
        code, _s, err = _powershell(script, timeout=60)
    except (OSError, subprocess.SubprocessError) as e:
        raise ErreurExport(str(e)) from e
    try:
        if code != 0 or not os.path.exists(f):
            raise ErreurExport((err or "").strip().splitlines()[0] if (err or "").strip() else "export")
        with open(f, "rb") as h:
            return h.read()
    finally:
        try:
            os.remove(f)
            os.rmdir(os.path.dirname(f))
        except OSError:
            pass


def windows_signer(empreinte, donnees):
    """Fait signer par Windows (RSA, SHA-256, PKCS#1 v1.5) avec la clef de l'ID du magasin, sans l'exporter.
    Windows peut afficher sa propre fenetre si la clef est protegee."""
    import base64
    if not all(c in "0123456789abcdefABCDEF" for c in empreinte):
        raise ErreurExport("empreinte")
    b64 = base64.b64encode(donnees).decode("ascii")
    script = ("$c = Get-Item 'Cert:\\CurrentUser\\My\\" + empreinte + "'; "
              "$k = [System.Security.Cryptography.X509Certificates.RSACertificateExtensions]::GetRSAPrivateKey($c); "
              "if ($k -eq $null) { throw 'clef RSA introuvable' }; "
              "$d = [Convert]::FromBase64String('" + b64 + "'); "
              # ancienne clef CryptoAPI (fournisseur sans SHA-256) : on la rouvre avec le fournisseur AES de Windows
              "if ($k -is [System.Security.Cryptography.RSACryptoServiceProvider]) { "
              "$ci = $k.CspKeyContainerInfo; "
              "$p = New-Object System.Security.Cryptography.CspParameters(24, 'Microsoft Enhanced RSA and AES Cryptographic Provider', $ci.KeyContainerName); "
              "$p.Flags = [System.Security.Cryptography.CspProviderFlags]::UseExistingKey; "
              "if ($ci.MachineKeyStore) { $p.Flags = $p.Flags -bor [System.Security.Cryptography.CspProviderFlags]::UseMachineKeyStore }; "
              "$k2 = New-Object System.Security.Cryptography.RSACryptoServiceProvider($p); "
              "$s = $k2.SignData($d, 'SHA256') } else { "
              "$s = $k.SignData($d, [Security.Cryptography.HashAlgorithmName]::SHA256, "
              "[Security.Cryptography.RSASignaturePadding]::Pkcs1) }; [Convert]::ToBase64String($s)")
    code, sortie, err = _powershell(script, timeout=120)
    if code != 0 or not sortie.strip():
        raise ErreurExport((err or "").strip().splitlines()[0] if (err or "").strip() else "signature Windows")
    return base64.b64decode(sortie.strip().splitlines()[-1])
