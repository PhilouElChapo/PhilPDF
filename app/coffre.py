"""Coffre des mots de passe des comptes (NAS, FTP, WebDAV...).

Windows : Gestionnaire d'identification de Windows ; Linux : trousseau du bureau (GNOME, KDE).
A defaut de coffre systeme (rare), le mot de passe est chiffre avec une cle propre a ce poste,
rangee dans le dossier de donnees ; il n'est jamais ecrit en clair dans les parametres.
"""
import base64, hashlib, json, os, secrets

SERVICE = "PhilPDF"


def _keyring():
    try:
        import keyring
        from keyring.backends import fail
        k = keyring.get_keyring()
        if isinstance(k, fail.Keyring) or getattr(k, "priority", 0) <= 0:
            return None
        return keyring
    except Exception:
        return None


def systeme():
    """Vrai si le coffre du systeme est utilise."""
    return _keyring() is not None


def _fichier():
    from .config import dossier_donnees
    return os.path.join(dossier_donnees(), "coffre.json"), os.path.join(dossier_donnees(), "coffre.cle")


def _cle():
    _f, c = _fichier()
    if not os.path.exists(c):
        with open(c, "wb") as f:
            f.write(secrets.token_bytes(32))
    with open(c, "rb") as f:
        return f.read()


def _xor(donnees, cle):
    flux = b""
    i = 0
    while len(flux) < len(donnees):
        flux += hashlib.sha256(cle + i.to_bytes(4, "big")).digest()
        i += 1
    return bytes(a ^ b for a, b in zip(donnees, flux))


def _lire_fichier():
    f, _c = _fichier()
    try:
        with open(f, encoding="utf-8") as g:
            return json.load(g)
    except (OSError, ValueError):
        return {}


def _ecrire_fichier(d):
    f, _c = _fichier()
    with open(f, "w", encoding="utf-8") as g:
        json.dump(d, g)


def enregistrer(ident, secret):
    k = _keyring()
    if k:
        try:
            k.set_password(SERVICE, ident, secret or "")
            return
        except Exception:
            pass
    d = _lire_fichier()
    sel = secrets.token_bytes(8)
    d[ident] = base64.b64encode(sel + _xor((secret or "").encode(), _cle() + sel)).decode()
    _ecrire_fichier(d)


def lire(ident):
    k = _keyring()
    if k:
        try:
            v = k.get_password(SERVICE, ident)
            if v is not None:
                return v
        except Exception:
            pass
    v = _lire_fichier().get(ident)
    if not v:
        return None
    b = base64.b64decode(v)
    return _xor(b[8:], _cle() + b[:8]).decode(errors="replace")


def supprimer(ident):
    k = _keyring()
    if k:
        try:
            k.delete_password(SERVICE, ident)
        except Exception:
            pass
    d = _lire_fichier()
    if ident in d:
        del d[ident]
        _ecrire_fichier(d)
