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
oauth.FOURNISSEURS["pcloud"]["jeton"] = "http://{hote}/oauth2_token"
oauth.HOTE_PCLOUD = r"127\.0\.0\.1:\d+"


def navigateur(url):
    """pCloud accepte, puis renvoie le navigateur vers PhilPDF avec le code et le serveur du compte."""
    q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
    assert url.startswith("https://my.pcloud.com/oauth2/authorize") and q["client_id"] == "id-pcloud"
    assert "code_challenge" not in q, "pCloud : pas de PKCE"
    retour = q["redirect_uri"] + "?" + urllib.parse.urlencode({"code": "CODE-1", "state": q["state"], "locationid": "2",
                                                               "hostname": f"127.0.0.1:{P}"})
    threading.Thread(target=lambda: urllib.request.urlopen(retour, timeout=10).read(), daemon=True).start()


verifie("pcloud" in distant.NUAGES and distant.TYPES["pcloud"] == "pCloud" and oauth.disponible("pcloud"),
        "pCloud : proposé parmi les Drives en direct")
j = oauth.autoriser("pcloud", ouvrir=navigateur, delai=20)
verifie(j["refresh_token"] == f"127.0.0.1:{P}|{JETON}", "pCloud : jeton reçu du serveur du compte, gardé avec lui")
c = distant.nouveau_compte("pcloud")
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
params = {"comptes": [{"id": "a1", "type": "gdrive"}, {"id": "b2", "type": "dropbox"}, {"id": c["id"], "type": "pcloud"}],
          "compte_prefere": c["id"]}
verifie([x["id"] for x in distant.comptes_ordonnes(params)] == [c["id"], "a1", "b2"], "compte préféré en tête de liste")
params["compte_prefere"] = "supprime"
verifie(distant.prefere(params) is None and [x["id"] for x in distant.comptes_ordonnes(params)] == ["a1", "b2", c["id"]],
        "compte préféré supprimé : ordre normal")
srv.shutdown()
print(f"\n{ok} vérifications pCloud réussies")
