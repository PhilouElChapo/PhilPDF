"""pCloud en direct, contre un serveur simule : autorisation par le navigateur (code + secret, serveur du compte
donne au retour), envoi (dossiers crees), mise a jour sans doublon, telechargement, liste, etat pour la
synchronisation ; compte prefere propose d'office. Exemples fictifs (Jean Martin)."""
import json, os, re, sys, tempfile, threading, urllib.parse, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import annotations  # noqa: F401
os.environ["PHILPDF_LANGUE"] = "fr"
base = tempfile.mkdtemp()
os.environ["HOME"] = os.environ["APPDATA"] = base
os.environ["PHILPDF_PCLOUD_ID"] = "id-pcloud"
os.environ["PHILPDF_PCLOUD_SECRET"] = "secret-pcloud"
from app import distant, oauth, coffre

ok = 0


def verifie(cond, msg):
    global ok
    assert cond, msg
    ok += 1
    print("OK ", msg)


ARBRE, DOSSIERS = {}, {"/"}
JETON = "JETON-PCLOUD-JEAN-MARTIN"


def enfants(d):
    d = d.rstrip("/") or "/"
    return [(os.path.basename(x), x in DOSSIERS, len(ARBRE.get(x, b"")))
            for x in sorted(DOSSIERS | set(ARBRE)) if x != "/" and os.path.dirname(x) == d]


class Serveur(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, d):
        b = json.dumps(d).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _traiter(self, corps=b""):
        u = urllib.parse.urlsplit(self.path)
        q = dict(urllib.parse.parse_qsl(u.query))
        p = u.path
        if p == "/oauth2_token":
            q.update(dict(urllib.parse.parse_qsl(corps.decode())))
            assert q.get("client_secret") == "secret-pcloud" and q.get("code") == "CODE-1", q
            return self._json({"result": 0, "access_token": JETON, "token_type": "bearer", "uid": 1})
        if p.startswith("/fichier"):
            b = ARBRE[urllib.parse.unquote(p[len("/fichier"):])]
            self.send_response(200)
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            return self.wfile.write(b)
        if q.get("access_token") != JETON:
            return self._json({"result": 2000, "error": "Log in failed."})
        if p == "/userinfo":
            return self._json({"result": 0, "email": "jean.martin@exemple.fr"})
        if p == "/listfolder":
            d = q["path"].rstrip("/") or "/"
            if d not in DOSSIERS:
                return self._json({"result": 2005, "error": "Directory does not exist."})
            return self._json({"result": 0, "metadata": {"contents": [
                {"name": n, "isfolder": dos, "size": t, "modified": "Tue, 10 Nov 2026 10:00:00 +0000", "hash": t}
                for n, dos, t in enfants(d)]}})
        if p == "/createfolderifnotexists":
            c = q["path"].rstrip("/")
            while c and c not in DOSSIERS:
                DOSSIERS.add(c)
                c = os.path.dirname(c)
            return self._json({"result": 0})
        if p == "/getfilelink":
            if q["path"] not in ARBRE:
                return self._json({"result": 2009, "error": "File not found."})
            return self._json({"result": 0, "hosts": [f"127.0.0.1:{P}"], "path": "/fichier" + urllib.parse.quote(q["path"])})
        if p == "/uploadfile":
            d = q["path"].rstrip("/") or "/"
            if d not in DOSSIERS:
                return self._json({"result": 2005, "error": "Directory does not exist."})
            m = re.search(rb"\r\n\r\n(.*)\r\n--PhilPDF", corps, re.S)
            ARBRE[(d.rstrip("/") + "/" + q["filename"])] = m.group(1)
            return self._json({"result": 0, "metadata": [{"name": q["filename"]}]})
        return self._json({"result": 1000, "error": "inconnu " + p})

    def do_GET(self):
        self._traiter()

    def do_POST(self):
        self._traiter(self.rfile.read(int(self.headers.get("Content-Length", 0))))


srv = ThreadingHTTPServer(("127.0.0.1", 0), Serveur)
P = srv.server_port
threading.Thread(target=srv.serve_forever, daemon=True).start()
distant.PCLOUD_SCHEMA = "http"
oauth.FOURNISSEURS["pcloud_api"]["jeton"] = "http://{hote}/oauth2_token"
oauth.HOTE_PCLOUD = r"127\.0\.0\.1:\d+"


def navigateur(url):
    """pCloud accepte, puis renvoie le navigateur vers PhilPDF avec le code et le serveur du compte."""
    q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
    assert url.startswith("https://my.pcloud.com/oauth2/authorize") and q["client_id"] == "id-pcloud"
    assert "code_challenge" not in q, "pCloud : pas de PKCE"
    retour = q["redirect_uri"] + "?" + urllib.parse.urlencode({"code": "CODE-1", "state": q["state"], "locationid": "2",
                                                               "hostname": f"127.0.0.1:{P}"})
    threading.Thread(target=lambda: urllib.request.urlopen(retour, timeout=10).read(), daemon=True).start()


verifie("pcloud_api" in distant.NUAGES and oauth.disponible("pcloud_api") and "pcloud_api" in distant.types_proposes(),
        "pCloud (connexion directe) : proposé quand PhilPDF a son identifiant d'application")
j = oauth.autoriser("pcloud_api", ouvrir=navigateur, delai=20)
verifie(j["refresh_token"] == f"127.0.0.1:{P}|{JETON}", "pCloud : jeton reçu du serveur du compte, gardé avec lui")
c = distant.nouveau_compte("pcloud_api")
coffre.enregistrer(c["id"] + ".jeton", j["refresh_token"])
e = distant.emplacement(c)
verifie("jean.martin@exemple.fr" in e.tester(), "pCloud : test de connexion (adresse du compte)")
local = os.path.join(base, "a.pdf")
open(local, "wb").write(b"%PDF v1")
e.envoyer(local, "/PhilPDF/Factures/a.pdf")
verifie([x.nom for x in e.lister("/PhilPDF")] == ["Factures"] and [x.nom for x in e.lister("/PhilPDF/Factures")] == ["a.pdf"],
        "pCloud : envoi, dossiers créés")
open(local, "wb").write(b"%PDF version 2")
e.envoyer(local, "/PhilPDF/Factures/a.pdf")
verifie(list(ARBRE.values()).count(b"%PDF version 2") == 1 and len(ARBRE) == 1, "pCloud : mise à jour sans doublon")
dst = os.path.join(base, "g.pdf")
e.telecharger("/PhilPDF/Factures/a.pdf", dst)
verifie(open(dst, "rb").read() == b"%PDF version 2", "pCloud : téléchargement")
verifie(set(e.modifies("/PhilPDF/Factures")) == {"a.pdf"} and e.modifies("/Absent") == {}, "pCloud : état pour la synchronisation")
try:
    e.telecharger("/PhilPDF/absent.pdf", dst)
    verifie(False, "pCloud : fichier absent signalé")
except distant.ErreurDistant as ex:
    verifie("introuvable" in str(ex), "pCloud : fichier absent signalé clairement")
coffre.enregistrer(c["id"] + ".jeton", f"127.0.0.1:{P}|AUTRE")
try:
    distant.emplacement(c).lister("/")
    verifie(False, "pCloud : autorisation retirée signalée")
except distant.ErreurDistant as ex:
    verifie("autorisez à nouveau" in str(ex), "pCloud : autorisation retirée : on demande d'autoriser à nouveau")
verifie("access_token=****" in distant.masquer(f"GET http://x/listfolder?path=%2F&access_token={JETON}"),
        "pCloud : jeton masqué dans le journal")

# compte prefere : en tete et propose d'office
params = {"comptes": [{"id": "a1", "type": "gdrive"}, {"id": "b2", "type": "dropbox"}, {"id": c["id"], "type": "pcloud_api"}],
          "compte_prefere": c["id"]}
verifie([x["id"] for x in distant.comptes_ordonnes(params)] == [c["id"], "a1", "b2"], "compte préféré en tête de liste")
params["compte_prefere"] = "supprime"
verifie(distant.prefere(params) is None and [x["id"] for x in distant.comptes_ordonnes(params)] == ["a1", "b2", c["id"]],
        "compte préféré supprimé : ordre normal")

# ---- pCloud par WebDAV (adresse e-mail et mot de passe) : compte trouve seul en Europe ou aux Etats-Unis
import base64


class Dav(BaseHTTPRequestHandler):
    refuse = False

    def log_message(self, *a):
        pass

    def do_PROPFIND(self):
        attendu = "Basic " + base64.b64encode(b"jean.martin@exemple.fr:mdp").decode()
        if self.refuse or self.headers.get("Authorization") != attendu:
            self.send_response(401)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        b = (b'<?xml version="1.0"?><d:multistatus xmlns:d="DAV:"><d:response><d:href>/</d:href><d:propstat><d:prop>'
             b'<d:resourcetype><d:collection/></d:resourcetype></d:prop></d:propstat></d:response><d:response>'
             b'<d:href>/PhilPDF/</d:href><d:propstat><d:prop><d:resourcetype><d:collection/></d:resourcetype></d:prop>'
             b'</d:propstat></d:response></d:multistatus>')
        self.send_response(207)
        self.send_header("Content-Type", "application/xml")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)


    crees = []

    def do_MKCOL(self):
        Dav.crees.append(self.path)
        self.send_response(201)
        self.send_header("Content-Length", "0")
        self.end_headers()


class DavRefus(Dav):
    refuse = True


eu = ThreadingHTTPServer(("127.0.0.1", 0), DavRefus)
us = ThreadingHTTPServer(("127.0.0.1", 0), Dav)
for x in (eu, us):
    threading.Thread(target=x.serve_forever, daemon=True).start()
distant.PCLOUD_EUROPE, distant.PCLOUD_USA = f"http://127.0.0.1:{eu.server_port}", f"http://127.0.0.1:{us.server_port}"
cd = distant.nouveau_compte("pcloud")
verifie(cd["adresse"] == distant.PCLOUD_EUROPE and "pcloud" in distant.types_proposes() and "pcloud" not in distant.NUAGES,
        "pCloud par WebDAV : proposé, serveur européen par défaut, avec adresse e-mail et mot de passe")
cd["utilisateur"] = "jean.martin@exemple.fr"
ed = distant.emplacement(cd, "mdp")
verifie(isinstance(ed, distant.PcloudDav) and [x.nom for x in ed.lister("/")] == ["PhilPDF"],
        "pCloud par WebDAV : liste du dossier")
verifie(cd["adresse"] == distant.PCLOUD_USA, "pCloud par WebDAV : compte aux Etats-Unis trouvé seul et retenu")
mauvais = dict(cd, adresse=distant.PCLOUD_EUROPE)
try:
    distant.emplacement(mauvais, "faux").lister("/")
    verifie(False, "pCloud par WebDAV : mauvais mot de passe signalé")
except distant.ErreurDistant as ex:
    verifie("offre payante" in str(ex), "pCloud par WebDAV : mauvais mot de passe expliqué (offre payante, deux étapes)")
os.environ.pop("PHILPDF_PCLOUD_ID")
verifie("pcloud_api" not in distant.types_proposes(), "pCloud (connexion directe) caché tant que l'identifiant manque")
ck = distant.nouveau_compte("kdrive")
ck["adresse"] = "123456"
verifie(isinstance(distant.emplacement(ck, "x"), distant.KdriveDav) and
        distant.emplacement(ck, "x")._base() == "https://123456.connect.kdrive.infomaniak.com" and "kdrive" in distant.types_proposes(),
        "Infomaniak kDrive : le numéro du kDrive donne l'adresse WebDAV")


class Dav403(Dav):
    def do_PROPFIND(self):
        self.send_response(403)
        self.send_header("Content-Length", "0")
        self.end_headers()


# bouton « Nouveau dossier » de Ouvrir / Enregistrer : MKCOL sur le dossier voulu
ed = distant.PcloudDav(dict(cd, adresse=distant.PCLOUD_USA), "mdp")
ed.nouveau_dossier("/PhilPDF/Factures 2026")
verifie(Dav.crees and Dav.crees[-1] == "/PhilPDF/Factures%202026/", "WebDAV : nouveau dossier créé (MKCOL)")

k403 = ThreadingHTTPServer(("127.0.0.1", 0), Dav403)
threading.Thread(target=k403.serve_forever, daemon=True).start()
ck2 = dict(ck, adresse=f"http://127.0.0.1:{k403.server_port}", utilisateur="jean.martin@exemple.fr")
try:
    distant.emplacement(ck2, "mdp").tester()
    verifie(False, "Infomaniak kDrive : refus 403 signalé")
except distant.ErreurDistant as ex:
    verifie("offre kDrive ne le permet pas" in str(ex), "Infomaniak kDrive : refus 403 expliqué (offre sans WebDAV)")
k403.shutdown()
for x in (eu, us, srv):
    x.shutdown()
print(f"\n{ok} vérifications pCloud réussies")
