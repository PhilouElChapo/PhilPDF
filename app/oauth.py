"""Autorisation OAuth 2 des Drives (Google Drive, plus tard OneDrive, Dropbox, Box).

L'utilisateur clique « Autoriser » : le navigateur s'ouvre sur la page du fournisseur, il accepte,
le navigateur revient sur une petite page locale de PhilPDF (http://127.0.0.1:<port>) qui recoit le code.
PhilPDF l'echange contre un jeton de renouvellement, range dans le coffre du systeme.
Methode « application de bureau » avec PKCE, comme le recommandent Google et Microsoft.

Les identifiants d'application (client_id, secret) ne sont pas dans le code source public :
 - la fabrication sur GitHub les ecrit dans app/identifiants.py (secrets GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET) ;
 - pour une fabrication personnelle : variables PHILPDF_GOOGLE_ID / PHILPDF_GOOGLE_SECRET, ou fichier
   identifiants.json dans le dossier de donnees ({"gdrive": {"id": "...", "secret": "..."}}).
"""
import base64, hashlib, html, http.server, json, os, secrets, socket, threading, time, urllib.parse, urllib.request, webbrowser
from .langue import _

PORTS_FIXES = [53682, 53683, 53684]      # a declarer chez Dropbox (qui exige le port exact)

FOURNISSEURS = {
    "gdrive": {
        "nom": "Google Drive",
        "auth": "https://accounts.google.com/o/oauth2/v2/auth",
        "jeton": "https://oauth2.googleapis.com/token",
        "portee": "https://www.googleapis.com/auth/drive.file",
        "extra": {"access_type": "offline", "prompt": "consent"},
        "env": ("PHILPDF_GOOGLE_ID", "PHILPDF_GOOGLE_SECRET"),
        "retour": "http://127.0.0.1:{port}",
    },
    "onedrive": {
        "nom": "OneDrive",
        "auth": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        "jeton": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
        "portee": "Files.ReadWrite offline_access User.Read",
        "extra": {"prompt": "select_account"},
        "env": ("PHILPDF_ONEDRIVE_ID", "PHILPDF_ONEDRIVE_SECRET"),
        "retour": "http://localhost:{port}",          # Microsoft : « http://localhost » declare, port libre
    },
    "dropbox": {
        "nom": "Dropbox",
        "auth": "https://www.dropbox.com/oauth2/authorize",
        "jeton": "https://api.dropboxapi.com/oauth2/token",
        "portee": "",
        "extra": {"token_access_type": "offline"},
        "env": ("PHILPDF_DROPBOX_ID", "PHILPDF_DROPBOX_SECRET"),
        "retour": "http://localhost:{port}/",          # Dropbox : adresse exacte, port compris
        "ports": PORTS_FIXES,
    },
    "box": {
        "nom": "Box",
        "auth": "https://account.box.com/api/oauth2/authorize",
        "jeton": "https://api.box.com/oauth2/token",
        "portee": "",
        "extra": {},
        "env": ("PHILPDF_BOX_ID", "PHILPDF_BOX_SECRET"),
        "retour": "http://localhost:{port}/",
        "ports": PORTS_FIXES,
    },
}


class ErreurAutorisation(Exception):
    pass


# Identifiants d'application publics de PhilPDF (applications « client public » : ils ne sont pas secrets).
# Les secrets du depot GitHub ou les variables d'environnement passent avant.
PUBLICS = {"onedrive": "e6479a20-b120-476d-ba0a-e4f37aa9841c"}


def identifiants(fournisseur):
    """(client_id, secret) ou (None, None) si PhilPDF n'a pas d'identifiant pour ce fournisseur."""
    f = FOURNISSEURS[fournisseur]
    cid, sec = os.environ.get(f["env"][0]), os.environ.get(f["env"][1])
    if cid:
        return cid.strip(), (sec or "").strip() or None
    try:
        from . import identifiants as I
        d = getattr(I, "IDENTIFIANTS", {}).get(fournisseur)
        if d and d.get("id"):
            return d["id"].strip(), (d.get("secret") or "").strip() or None
    except ImportError:
        pass
    if fournisseur in PUBLICS:                    # identifiant public (application de bureau, sans secret)
        return PUBLICS[fournisseur], None
    try:
        from .config import dossier_donnees
        with open(os.path.join(dossier_donnees(), "identifiants.json"), encoding="utf-8") as fic:
            d = json.load(fic).get(fournisseur) or {}
        if d.get("id"):
            return d["id"], d.get("secret")
    except (OSError, ValueError):
        pass
    return None, None


def disponible(fournisseur):
    return identifiants(fournisseur)[0] is not None


PAGE = """<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>PhilPDF</title>
<style>body{{font:16px "Segoe UI",system-ui,sans-serif;background:#f6f6f4;color:#1f1f1f;display:flex;align-items:center;
justify-content:center;height:90vh;margin:0}}div{{background:#fff;border:1px solid #e4e4e0;border-radius:12px;padding:28px 36px;
max-width:460px}}h1{{font-size:22px;margin:0 0 8px}}b{{color:#c9252d}}</style></head><body><div><h1>Phil<b>PDF</b></h1>
<p>{texte}</p></div></body></html>"""


def _poster(url, champs, journal=None):
    donnees = urllib.parse.urlencode(champs).encode()
    req = urllib.request.Request(url, data=donnees, headers={"Content-Type": "application/x-www-form-urlencoded"})
    if journal:
        journal(f"→ POST {url}  (grant_type={champs.get('grant_type')})")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            rep = json.load(r)
            if journal:
                journal(f"← {r.status} jeton reçu")
            return rep
    except urllib.error.HTTPError as e:
        try:
            detail = json.load(e)
        except Exception:
            detail = {}
        if journal:
            journal(f"← {e.code} {detail.get('error', '')} {detail.get('error_description', '')}")
        raise ErreurAutorisation(detail.get("error_description") or detail.get("error") or str(e))
    except (urllib.error.URLError, OSError) as e:
        if journal:
            journal(f"✕ {e}")
        raise ErreurAutorisation(_("Serveur injoignable : {raison}", raison=getattr(e, "reason", e)))


PORTEE_COMPLETE = {"gdrive": "https://www.googleapis.com/auth/drive"}   # tout le Drive (option du compte)


def autoriser(fournisseur, ouvrir=webbrowser.open, delai=300, arret=lambda: False, journal=None, complet=False):
    """Ouvre le navigateur et attend l'accord. Renvoie le dict de jetons (refresh_token, access_token...)."""
    f = FOURNISSEURS[fournisseur]
    cid, sec = identifiants(fournisseur)
    if not cid:
        raise ErreurAutorisation(_("PhilPDF n'a pas d'identifiant d'application pour {nom}.", nom=f["nom"]))
    verif = base64.urlsafe_b64encode(secrets.token_bytes(48)).rstrip(b"=").decode()
    defi = base64.urlsafe_b64encode(hashlib.sha256(verif.encode()).digest()).rstrip(b"=").decode()
    etat = secrets.token_urlsafe(16)
    recu = {}

    class Retour(http.server.BaseHTTPRequestHandler):
        timeout = 5                                # connexion ouverte d'avance par le navigateur sans requete : on la lache

        def log_message(self, *a):
            pass

        def do_GET(self):
            q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(self.path).query))
            if "code" not in q and "error" not in q:
                self.send_response(404)
                self.end_headers()
                return
            if recu:                               # deuxieme passage (rechargement de la page) : on ne refait rien
                q = recu
            else:
                recu.update(q)
                if journal:
                    journal("← retour du navigateur : " + ("code d'autorisation reçu" if "code" in q else f"refus ({q.get('error')})"))
            ok = "code" in q and q.get("state") == etat
            texte = (_("C'est fait : PhilPDF peut maintenant utiliser votre {nom}. Vous pouvez fermer cette page.", nom=f["nom"])
                     if ok else _("Autorisation refusée ou annulée. Vous pouvez fermer cette page."))
            corps = PAGE.format(texte=html.escape(texte)).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(corps)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(corps)

    class Serveur(http.server.ThreadingHTTPServer):
        daemon_threads = True

    serveur = None
    for port in f.get("ports") or [0]:
        try:
            serveur = Serveur(("127.0.0.1", port), Retour)
            break
        except OSError:
            continue
    if serveur is None:
        raise ErreurAutorisation(_("Les ports {ports} sont occupés : fermez l'application qui les utilise.",
                                   ports=", ".join(map(str, f.get("ports", [])))))
    redirection = f.get("retour", "http://127.0.0.1:{port}").format(port=serveur.server_port)
    params = {"client_id": cid, "redirect_uri": redirection, "response_type": "code",
              "code_challenge": defi, "code_challenge_method": "S256", "state": etat, **f["extra"]}
    portee = PORTEE_COMPLETE.get(fournisseur) if complet and fournisseur in PORTEE_COMPLETE else f["portee"]
    if portee:
        params["scope"] = portee
    url = f["auth"] + "?" + urllib.parse.urlencode(params)
    if journal:
        journal(f"→ navigateur : {f['auth']} (retour attendu sur {redirection})")
    fil = threading.Thread(target=serveur.serve_forever, kwargs={"poll_interval": 0.3}, daemon=True)
    fil.start()
    ouvrir(url)
    debut = time.monotonic()
    try:
        while not recu and time.monotonic() - debut < delai and not arret():
            time.sleep(0.2)
        time.sleep(0.3)                            # laisse la page « C'est fait » partir vers le navigateur
    finally:
        serveur.shutdown()
        serveur.server_close()
    if not recu:
        raise ErreurAutorisation(_("Pas de réponse du navigateur (délai dépassé ou annulé)."))
    if recu.get("state") != etat or "code" not in recu:
        raise ErreurAutorisation(_("Autorisation refusée : {raison}", raison=recu.get("error", "?")))
    champs = {"client_id": cid, "code": recu["code"], "code_verifier": verif, "grant_type": "authorization_code",
              "redirect_uri": redirection}
    if sec:
        champs["client_secret"] = sec
    if journal:
        journal("→ échange du code contre le jeton durable...")
    jetons = _poster(f["jeton"], champs, journal)
    if not jetons.get("refresh_token"):
        if journal:
            journal("✕ réponse sans jeton durable : " + ", ".join(sorted(jetons)))
        raise ErreurAutorisation(_("Le fournisseur n'a pas donné de jeton durable."))
    if journal:
        journal("✓ jeton durable reçu")
    jetons["expire"] = time.time() + int(jetons.get("expires_in", 3000)) - 60
    return jetons


def rafraichir(fournisseur, refresh_token, journal=None):
    """Nouveau jeton d'acces a partir du jeton durable."""
    f = FOURNISSEURS[fournisseur]
    cid, sec = identifiants(fournisseur)
    champs = {"client_id": cid, "refresh_token": refresh_token, "grant_type": "refresh_token"}
    if sec:
        champs["client_secret"] = sec
    j = _poster(f["jeton"], champs, journal)
    j["expire"] = time.time() + int(j.get("expires_in", 3000)) - 60
    return j
