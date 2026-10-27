"""Emplacements distants avec de vrais serveurs lances sur ce poste : FTP, FTPS non, WebDAV, et un
Synology simule (connexion, verification en deux etapes, liste, telechargement, envoi)."""
import json, os, socket, sys, tempfile, threading, time, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import annotations  # noqa: F401  (erreurs lisibles sur GitHub)
os.environ["PHILPDF_LANGUE"] = "fr"
base = tempfile.mkdtemp()
os.environ["HOME"] = os.environ["APPDATA"] = base
from app import distant, coffre

ok = 0
def verifie(cond, msg):
    global ok
    assert cond, msg
    ok += 1
    print("OK ", msg)

def port_libre():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p

racine = os.path.join(base, "serveur"); os.makedirs(os.path.join(racine, "Factures"))
open(os.path.join(racine, "Factures", "edf.pdf"), "wb").write(b"%PDF-1.7 edf")
local = os.path.join(base, "local.pdf"); open(local, "wb").write(b"%PDF-1.7 modifie")

# --- coffre : jamais en clair
coffre.enregistrer("essai", "M0tDeP@sse")
verifie(coffre.lire("essai") == "M0tDeP@sse", "coffre : mot de passe relu")
if not coffre.systeme():
    verifie("M0tDeP@sse" not in open(os.path.join(base, ".config", "philpdf", "coffre.json") if os.path.exists(
        os.path.join(base, ".config", "philpdf", "coffre.json")) else coffre._fichier()[0]).read(), "coffre : pas de mot de passe en clair")

def scenario(nom, e, dossier="/Factures"):
    l = e.lister(dossier)
    verifie(any(x.nom == "edf.pdf" and not x.dossier for x in l), f"{nom} : liste du dossier")
    dst = os.path.join(base, f"{nom}.pdf"); e.telecharger(dossier + "/edf.pdf", dst)
    verifie(open(dst, "rb").read() == b"%PDF-1.7 edf", f"{nom} : téléchargement")
    e.envoyer(local, dossier + "/nouveau.pdf")
    verifie(any(x.nom == "nouveau.pdf" for x in e.lister(dossier)), f"{nom} : envoi")
    os.remove(os.path.join(racine, "Factures", "nouveau.pdf"))

# --- dossier reseau
c = distant.nouveau_compte("reseau"); c["adresse"] = racine
scenario("Dossier réseau", distant.emplacement(c, ""))

# --- FTP
from pyftpdlib.authorizers import DummyAuthorizer
from pyftpdlib.handlers import FTPHandler
from pyftpdlib.servers import FTPServer
import logging
from pyftpdlib.log import config_logging
config_logging(level=logging.ERROR)
auth = DummyAuthorizer(); auth.add_user("phil", "secret", racine, perm="elradfmw")
h = FTPHandler; h.authorizer = auth
pf = port_libre(); srv = FTPServer(("127.0.0.1", pf), h)
threading.Thread(target=srv.serve_forever, daemon=True).start()
c = distant.nouveau_compte("ftp"); c.update(adresse="127.0.0.1", port=pf, utilisateur="phil", chiffrement="")
scenario("FTP", distant.emplacement(c, "secret"))
try:
    distant.emplacement(c, "faux").lister("/")
    verifie(False, "FTP : mauvais mot de passe refusé")
except distant.ErreurDistant as e:
    verifie("refusé" in str(e), "FTP : mauvais mot de passe refusé proprement")

# --- WebDAV
from wsgidav.wsgidav_app import WsgiDAVApp
from cheroot import wsgi
pw = port_libre()
app = WsgiDAVApp({"provider_mapping": {"/": racine}, "simple_dc": {"user_mapping": {"*": {"phil": {"password": "secret"}}}},
                  "http_authenticator": {"accept_basic": True, "accept_digest": False, "default_to_digest": False},
                  "verbose": 0, "logging": {"enable": False}})
sw = wsgi.Server(("127.0.0.1", pw), app)
threading.Thread(target=sw.safe_start, daemon=True).start(); time.sleep(0.5)
c = distant.nouveau_compte("webdav"); c.update(adresse=f"http://127.0.0.1:{pw}", utilisateur="phil")
scenario("WebDAV", distant.emplacement(c, "secret"))

# --- Synology simule (API File Station)
ETAT = {"2fa": True}
class DSM(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _json(self, d):
        b = json.dumps(d).encode(); self.send_response(200); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def _traiter(self, q, corps=b""):
        api = q.get("api"); m = q.get("method")
        if api == "SYNO.API.Auth" and m == "login":
            if q.get("account") != "phil" or q.get("passwd") != "secret":
                return self._json({"success": False, "error": {"code": 400}})
            if ETAT["2fa"] and q.get("otp_code") != "123456" and q.get("device_id") != "APPAREIL":
                return self._json({"success": False, "error": {"code": 403}})
            d = {"sid": "SID1"}
            if q.get("enable_device_token") == "yes":
                d["did"] = "APPAREIL"
            return self._json({"success": True, "data": d})
        if api == "SYNO.API.Auth":
            return self._json({"success": True})
        if q.get("_sid") != "SID1":
            return self._json({"success": False, "error": {"code": 119}})
        if api == "SYNO.FileStation.List" and m == "list_share":
            return self._json({"success": True, "data": {"shares": [{"name": "Factures", "path": "/Factures", "isdir": True}]}})
        if api == "SYNO.FileStation.List":
            p = os.path.join(racine, q["folder_path"].strip("/"))
            return self._json({"success": True, "data": {"files": [
                {"name": n, "path": q["folder_path"] + "/" + n, "isdir": os.path.isdir(os.path.join(p, n)),
                 "additional": {"size": os.path.getsize(os.path.join(p, n))}} for n in os.listdir(p)]}})
        if api == "SYNO.FileStation.Download":
            b = open(os.path.join(racine, q["path"].strip("/")), "rb").read()
            self.send_response(200); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b); return
        return self._json({"success": False, "error": {"code": 101}})
    def do_GET(self):
        self._traiter(dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(self.path).query)))
    def do_POST(self):
        q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(self.path).query))
        corps = self.rfile.read(int(self.headers["Content-Length"]))
        bord = self.headers["Content-Type"].split("boundary=")[1].encode()
        champs, fichier = {}, None
        for part in corps.split(b"--" + bord):
            if b"Content-Disposition" not in part: continue
            tete, _s, val = part.partition(b"\r\n\r\n"); val = val[:-2]
            nom = tete.split(b'name="')[1].split(b'"')[0].decode()
            if b"filename=" in tete:
                fichier = (tete.split(b'filename="')[1].split(b'"')[0].decode(), val)
            else:
                champs[nom] = val.decode()
        if q.get("_sid") != "SID1" or champs.get("api") != "SYNO.FileStation.Upload":
            return self._json({"success": False, "error": {"code": 119}})
        open(os.path.join(racine, champs["path"].strip("/"), fichier[0]), "wb").write(fichier[1])
        self._json({"success": True})
ps = port_libre(); hs = ThreadingHTTPServer(("127.0.0.1", ps), DSM)
threading.Thread(target=hs.serve_forever, daemon=True).start()
c = distant.nouveau_compte("synology"); c.update(adresse=f"127.0.0.1:{ps}", utilisateur="phil")
try:
    distant.emplacement(c, "secret").lister("/")
    verifie(False, "Synology : code demandé")
except distant.BesoinCode:
    verifie(True, "Synology : le code de vérification en deux étapes est demandé")
e = distant.emplacement(c, "secret", code="123456")
verifie([x.nom for x in e.lister("/")] == ["Factures"], "Synology : dossiers partagés listés après le code")
verifie(coffre.lire(c["id"] + ".appareil") == "APPAREIL", "Synology : appareil mémorisé (plus de code ensuite)")
scenario("Synology", distant.emplacement(c, "secret"))

# --- synchronisation entre deux postes par un NAS, un FTP ou un dossier reseau (sans Drive)
from app import miroir
def miroir_scenario(nom, compte, mdp):
    def poste(n):
        os.environ["HOME"] = os.environ["APPDATA"] = os.path.join(base, nom.replace(" ", "_"), n)
        os.makedirs(os.environ["HOME"], exist_ok=True)
        return dict(machine=n, comptes=[compte], drive_compte=compte["id"]), os.path.join(miroir.dossier_miroir(compte), "PhilPDF")
    def ecrire(d, rel, contenu):
        q = os.path.join(d, *rel.split("/")); os.makedirs(os.path.dirname(q), exist_ok=True)
        with open(q, "w", encoding="utf-8") as f: json.dump(contenu, f)
    pa, la = poste("A")
    ecrire(la, "session.json", {"A": {"maj": "2026-10-24T10:00", "fichiers": ["a.pdf"]}})
    ecrire(la, "sauvegarde/tampons/t1.json", {"t": 1})
    verifie(miroir.synchroniser(pa, emplacement=distant.emplacement(compte, mdp))[1] == 2, f"{nom} : poste A envoie sa session et un tampon")
    pb, lb = poste("B")
    miroir.synchroniser(pb, emplacement=distant.emplacement(compte, mdp))
    with open(os.path.join(lb, "sauvegarde", "tampons", "t1.json"), encoding="utf-8") as f:
        verifie(json.load(f) == {"t": 1}, f"{nom} : poste B les reçoit (dossiers créés sur le serveur)")
    verifie(miroir.synchroniser(pb, emplacement=distant.emplacement(compte, mdp)) == (0, 0), f"{nom} : plus rien à faire ensuite")
    # conflit : les deux postes modifient la session entre deux synchros -> les deux entrees sont gardees partout
    import time as _t; _t.sleep(1.1)
    ecrire(lb, "session.json", {"A": {"maj": "2026-10-24T10:00", "fichiers": ["a.pdf"]}, "B": {"maj": "2026-10-25T10:00", "fichiers": ["b.pdf"]}})
    miroir.synchroniser(pb, emplacement=distant.emplacement(compte, mdp))
    _t.sleep(1.1)
    os.environ["HOME"] = os.environ["APPDATA"] = os.path.join(base, nom.replace(" ", "_"), "A")
    ecrire(la, "session.json", {"A": {"maj": "2026-10-26T10:00", "fichiers": ["a2.pdf"]}})
    miroir.synchroniser(pa, emplacement=distant.emplacement(compte, mdp))
    with open(os.path.join(la, "session.json"), encoding="utf-8") as f:
        s = json.load(f)
    verifie(set(s) == {"A", "B"} and s["A"]["fichiers"] == ["a2.pdf"], f"{nom} : conflit fusionné, rien de l'autre poste n'est perdu")
    verifie(not os.path.exists(os.path.join(la, "session.json.distant")), f"{nom} : aucun fichier temporaire laissé")
    # conflit avec une copie du Drive illisible : on garde la version du Drive, on ne l'ecrase jamais
    _t.sleep(1.1)
    os.environ["HOME"] = os.environ["APPDATA"] = os.path.join(base, nom.replace(" ", "_"), "B")
    miroir.synchroniser(pb, emplacement=distant.emplacement(compte, mdp))   # B recupere d'abord la fusion de A
    _t.sleep(1.1)
    q = os.path.join(lb, "session.json")
    with open(q, "w", encoding="utf-8") as f: f.write("{abime")
    miroir.synchroniser(pb, emplacement=distant.emplacement(compte, mdp))
    _t.sleep(1.1)
    os.environ["HOME"] = os.environ["APPDATA"] = os.path.join(base, nom.replace(" ", "_"), "A")
    ecrire(la, "session.json", {"A": {"maj": "2026-10-27T10:00", "fichiers": ["a3.pdf"]}})
    miroir.synchroniser(pa, emplacement=distant.emplacement(compte, mdp))
    with open(os.path.join(la, "session.json"), encoding="utf-8") as f:
        verifie(f.read() == "{abime", f"{nom} : fusion impossible -> version du Drive gardée, pas écrasée")
    # plan puis choix : rien n'est recu sans accord, ce qui est decoche reste en attente
    _t.sleep(1.1)
    os.environ["HOME"] = os.environ["APPDATA"] = os.path.join(base, nom.replace(" ", "_"), "B")
    ecrire(lb, "sauvegarde/tampons/t2.json", {"t": 2})
    miroir.synchroniser(pb, emplacement=distant.emplacement(compte, mdp), sens={"envoyer"})
    os.environ["HOME"] = os.environ["APPDATA"] = os.path.join(base, nom.replace(" ", "_"), "A")
    plan = miroir.planifier(pa, emplacement=distant.emplacement(compte, mdp))
    verifie([(x["rel"], x["action"]) for x in plan] == [("sauvegarde/tampons/t2.json", "recevoir")],
            f"{nom} : le plan annonce le nouveau tampon sans le recevoir")
    t2 = os.path.join(la, "sauvegarde", "tampons", "t2.json")
    verifie(not os.path.exists(t2), f"{nom} : rien reçu pendant le plan")
    miroir.synchroniser(pa, emplacement=distant.emplacement(compte, mdp), choix=set())
    verifie(not os.path.exists(t2) and len(miroir.planifier(pa, emplacement=distant.emplacement(compte, mdp))) == 1,
            f"{nom} : décoché -> pas reçu, proposé à nouveau")
    miroir.synchroniser(pa, emplacement=distant.emplacement(compte, mdp), choix={"sauvegarde/tampons/t2.json"})
    verifie(os.path.exists(t2) and miroir.planifier(pa, emplacement=distant.emplacement(compte, mdp)) == [],
            f"{nom} : coché -> reçu, plus rien en attente")
    os.utime(t2, None)                                      # reecrit a l'identique : pas un changement
    verifie(miroir.planifier(pa, emplacement=distant.emplacement(compte, mdp)) == [], f"{nom} : heure changée seule -> rien à envoyer")
    os.environ["HOME"] = os.environ["APPDATA"] = base

cr = distant.nouveau_compte("reseau"); cr["adresse"] = os.path.join(base, "partage"); os.makedirs(cr["adresse"])
miroir_scenario("Dossier réseau", cr, "")
cf = distant.nouveau_compte("ftp"); cf.update(adresse="127.0.0.1", port=pf, utilisateur="phil", chiffrement="", dossier="/Factures")
miroir_scenario("FTP", cf, "secret")
cw = distant.nouveau_compte("webdav"); cw.update(adresse=f"http://127.0.0.1:{pw}", utilisateur="phil", dossier="/")
miroir_scenario("WebDAV", cw, "secret")
verifie(os.path.isfile(os.path.join(racine, "PhilPDF", "session.json")) and os.path.isfile(os.path.join(racine, "Factures", "PhilPDF", "session.json")),
        "dossier PhilPDF créé dans le dossier choisi du compte")

# --- journal : aucun secret lisible, meme sans « nom= » devant
fuites = ["GOCSPX-AbCdEf1234567890abcdefghij", "sk-ant-usr-1300abcdefXQAA", "AIzaSyAbcdefghijklmnopqrstuvwx123",
          "1//0gAbcdefghijklmnopqrstuvwxyz", "ya29.a0AfH6SMabc"]
masque = distant.masquer(" ".join(fuites) + ' {"client_secret": "abc123", "password": "x"} passwd=y&otp_code=1')
verifie(not any(f in masque for f in fuites) and "abc123" not in masque and "passwd=y" not in masque,
        "journal : secrets Google, Claude, Gemini et jetons masqués")

# --- comptes identiques sur deux postes (session)
c2 = dict(c, id="autre", nom="Mon NAS")
verifie(distant.cle_compte(c) == distant.cle_compte(c2), "même compte reconnu sur un autre poste")
srv.close_all(); sw.stop(); hs.shutdown()
print(f"\n{ok} vérifications d'emplacements distants réussies")
