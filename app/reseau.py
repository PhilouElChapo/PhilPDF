"""Connexions HTTPS fiables sur tous les PC.

Python verifie les certificats avec sa propre methode (OpenSSL) ; sur certains Windows, il manque un certificat
racine ou intermediaire que Windows irait chercher tout seul (« unable to get issuer certificate »). On demande donc
a Windows de verifier, comme le navigateur (module truststore) ; en secours, les racines de Windows ET celles du
paquet certifi sont acceptees ensemble.
"""
import ssl

_SECOURS = None
_MODE = None


def _contexte_union():
    c = ssl.create_default_context()                 # racines du systeme (magasin Windows)
    try:
        import certifi
        c.load_verify_locations(cafile=certifi.where())
    except Exception:
        pass
    return c


def activer():
    """A appeler au demarrage. Renvoie "windows" (verification par Windows) ou "python"."""
    global _SECOURS, _MODE
    if _MODE:
        return _MODE
    _SECOURS = _contexte_union()                     # cree AVANT l'injection : contexte OpenSSL classique
    try:
        import truststore
        truststore.inject_into_ssl()
        _MODE = "windows"
    except Exception:
        ssl._create_default_https_context = lambda *a, **k: _contexte_union()
        _MODE = "python"
    return _MODE


def secours():
    """Contexte OpenSSL avec les racines de Windows et de certifi (si la verification par Windows echoue)."""
    return _SECOURS or _contexte_union()


def erreur_certificat(e):
    import urllib.error
    r = getattr(e, "reason", e)
    return isinstance(r, ssl.SSLCertVerificationError) or "CERTIFICATE_VERIFY_FAILED" in str(e)


def ouvrir(req, timeout=30, *handlers):
    """urlopen avec une seconde chance si le certificat n'a pas pu etre verifie."""
    import urllib.request
    try:
        return urllib.request.build_opener(*handlers).open(req, timeout=timeout)
    except Exception as e:
        if not erreur_certificat(e):
            raise
        op = urllib.request.build_opener(urllib.request.HTTPSHandler(context=secours()), *handlers)
        return op.open(req, timeout=timeout)
