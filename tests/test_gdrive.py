"""Google Drive en direct, contre un Google simule : autorisation par le navigateur (PKCE), jetons,
dossiers, envoi, mise a jour, telechargement, jeton expire renouvele, autorisation retiree."""
import base64, hashlib, json, os, re, socket, sys, tempfile, threading, urllib.parse, urllib.request, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import annotations  # noqa: F401  (erreurs lisibles sur GitHub)
os.environ["PHILPDF_LANGUE"] = "fr"
base = tempfile.mkdtemp()
os.environ["HOME"] = os.environ["APPDATA"] = base
os.environ["PHILPDF_GOOGLE_ID"], os.environ["PHILPDF_GOOGLE_SECRET"] = "id-test", "secret-test"
from app import distant, oauth, coffre

ok = 0
def verifie(cond, msg):
    global ok
    assert cond, msg
    ok += 1
    print("OK ", msg)

FICHIERS = {"root": {"name": "", "mime": distant.DOSSIER_MIME, "parents": [], "data": b"", "mod": 0}}
HORLOGE = [0]
def horodater(f):
    HORLOGE[0] += 1; f["mod"] = HORLOGE[0]
ETAT = {"jetons_valides": set(), "refresh": None, "defi": None, "revoque": False}

class Google(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _json(self, d, code=200):
        b = json.dumps(d).encode(); self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def _auth(self):
        if self.headers.get("Authorization", "")[7:] not in ETAT["jetons_valides"]:
            self._json({"error": {"code": 401, "message": "Invalid Credentials"}}, 401); return False
        return True
    def do_GET(self):
        u = urllib.parse.urlsplit(self.path); q = dict(urllib.parse.parse_qsl(u.query))
        if u.path == "/auth":                       # le « navigateur » accepte et revient sur PhilPDF
            assert q["scope"].endswith("drive.file") and q["code_challenge_method"] == "S256"
            ETAT["defi"] = q["code_challenge"]
            self.send_response(302)
            self.send_header("Location", q["redirect_uri"] + "?" + urllib.parse.urlencode({"code": "CODE1", "state": q["state"]}))
            self.end_headers(); return
        if not self._auth(): return
        if u.path == "/drive/v3/about":
            return self._json({"user": {"emailAddress": "phil@example.org"}})
        m = re.match(r"/drive/v3/files/(\w+)$", u.path)
        if m and q.get("alt") == "media":
            b = FICHIERS[m.group(1)]["data"]; self.send_response(200); self.send_header("Content-Length", str(len(b)))
            self.end_headers(); self.wfile.write(b); return
        if u.path == "/drive/v3/files":
            r = q["q"]; nom = re.search(r"name = '((?:[^'\\]|\\.)*)'", r); par = re.search(r"'(\w+)' in parents", r).group(1)
            l = [{"id": i, "name": f["name"], "mimeType": f["mime"], "size": str(len(f["data"])), "modifiedTime": f"2026-10-23T20:{f.get('mod', 0) // 60:02d}:{f.get('mod', 0) % 60:02d}Z"}
                 for i, f in FICHIERS.items() if par in f["parents"] and (not nom or f["name"] == nom.group(1).replace("\\'", "'"))]
            return self._json({"files": l})
        self._json({}, 404)
    def _corps(self):
        return self.rfile.read(int(self.headers.get("Content-Length", 0)))
    def do_POST(self):
        u = urllib.parse.urlsplit(self.path); corps = self._corps()
        if u.path == "/token":
            f = dict(urllib.parse.parse_qsl(corps.decode()))
            assert f["client_id"] == "id-test" and f["client_secret"] == "secret-test"
            if f["grant_type"] == "authorization_code":
                defi = base64.urlsafe_b64encode(hashlib.sha256(f["code_verifier"].encode()).digest()).rstrip(b"=").decode()
                assert f["code"] == "CODE1" and defi == ETAT["defi"], "PKCE"
                ETAT["refresh"] = "RT1"; ETAT["jetons_valides"].add("AT1")
                return self._json({"access_token": "AT1", "refresh_token": "RT1", "expires_in": 3600})
            if ETAT["revoque"] or f["refresh_token"] != ETAT["refresh"]:
                return self._json({"error": "invalid_grant", "error_description": "Token has been expired or revoked."}, 400)
            t = "AT" + uuid.uuid4().hex[:6]; ETAT["jetons_valides"].add(t)
            return self._json({"access_token": t, "expires_in": 3600})
        if not self._auth(): return
        if u.path == "/drive/v3/files":
            d = json.loads(corps); i = uuid.uuid4().hex[:10]
            FICHIERS[i] = {"name": d["name"], "mime": d["mimeType"], "parents": d["parents"], "data": b""}; horodater(FICHIERS[i])
            return self._json({"id": i})
        if u.path == "/upload/drive/v3/files":
            bord = self.headers["Content-Type"].split("boundary=")[1].encode()
            parts = [p for p in corps.split(b"--" + bord) if b"Content-Type" in p]
            meta = json.loads(parts[0].split(b"\r\n\r\n", 1)[1].strip())
            data = parts[1].split(b"\r\n\r\n", 1)[1][:-2]
            i = uuid.uuid4().hex[:10]
            FICHIERS[i] = {"name": meta["name"], "mime": "application/pdf", "parents": meta["parents"], "data": data}; horodater(FICHIERS[i])
            return self._json({"id": i})
        self._json({}, 404)
    def do_PATCH(self):
        u = urllib.parse.urlsplit(self.path); corps = self._corps()
        if not self._auth(): return
        m = re.match(r"/upload/drive/v3/files/(\w+)$", u.path)
        FICHIERS[m.group(1)]["data"] = corps; horodater(FICHIERS[m.group(1)])
        self._json({"id": m.group(1)})

s = socket.socket(); s.bind(("127.0.0.1", 0)); P = s.getsockname()[1]; s.close()
srv = ThreadingHTTPServer(("127.0.0.1", P), Google); threading.Thread(target=srv.serve_forever, daemon=True).start()
B = f"http://127.0.0.1:{P}"
oauth.FOURNISSEURS["gdrive"].update(auth=B + "/auth", jeton=B + "/token")
distant.DRIVE_API, distant.DRIVE_ENVOI = B + "/drive/v3", B + "/upload/drive/v3"

def navigateur(url):                      # simule le navigateur : suit la redirection jusqu'a PhilPDF
    threading.Thread(target=lambda: urllib.request.urlopen(url, timeout=10).read(), daemon=True).start()

verifie(oauth.disponible("gdrive"), "identifiant d'application trouvé")
journal = []
j = oauth.autoriser("gdrive", ouvrir=navigateur, delai=10, journal=journal.append)
verifie(j["refresh_token"] == "RT1", "autorisation par le navigateur (PKCE) : jeton durable reçu")
c = distant.nouveau_compte("gdrive"); coffre.enregistrer(c["id"] + ".jeton", j["refresh_token"])
e = distant.emplacement(c)
verifie("phil@example.org" in e.tester(), "test de connexion : compte Google reconnu")
local = os.path.join(base, "a.pdf"); open(local, "wb").write(b"%PDF-1.7 version 1")
e.envoyer(local, "/PhilPDF/Factures/a.pdf")
verifie([x.nom for x in e.lister("/PhilPDF")] == ["Factures"], "dossiers créés à la volée")
verifie([x.nom for x in e.lister("/PhilPDF/Factures")] == ["a.pdf"], "fichier envoyé")
open(local, "wb").write(b"%PDF-1.7 version 2"); e.envoyer(local, "/PhilPDF/Factures/a.pdf")
verifie(len([f for f in FICHIERS.values() if f["name"] == "a.pdf"]) == 1, "ré-envoi = mise à jour, pas de doublon")
dst = os.path.join(base, "b.pdf"); e.telecharger("/PhilPDF/Factures/a.pdf", dst)
verifie(open(dst, "rb").read() == b"%PDF-1.7 version 2", "téléchargement de la dernière version")
ETAT["jetons_valides"].clear()          # le jeton d'acces expire
verifie(len(e.lister("/PhilPDF/Factures")) == 1, "jeton expiré renouvelé automatiquement")
ETAT["revoque"] = True; ETAT["jetons_valides"].clear()
e2 = distant.emplacement(c)
try:
    e2.lister("/"); verifie(False, "autorisation retirée détectée")
except distant.ErreurDistant as ex:
    verifie("autorisez à nouveau" in str(ex), "autorisation retirée : message clair")
verifie("Bearer ****" in e.texte_journal() and "AT1" not in e.texte_journal() and "RT1" not in e.texte_journal(), "jetons masqués dans le journal")

# --- boite aux lettres PhilPDF sur le Drive, sans l'application de bureau : deux postes
ETAT["revoque"] = False
from app import miroir
import time as _t
class P(dict):
    def enregistrer(self): pass
def poste(nom):
    os.environ["HOME"] = os.environ["APPDATA"] = os.path.join(base, nom); os.makedirs(os.environ["HOME"], exist_ok=True)
    coffre.enregistrer(c["id"] + ".jeton", "RT1")
    p = P(machine=nom, comptes=[c], drive_compte=c["id"])
    return p, os.path.join(miroir.dossier_miroir(c), "PhilPDF")
def ecrire(d, rel, contenu):
    p = os.path.join(d, *rel.split("/")); os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f: json.dump(contenu, f)
    _t.sleep(0.02)
def lire(d, rel):
    with open(os.path.join(d, *rel.split("/")), encoding="utf-8") as f: return json.load(f)
pa, la = poste("A")
ecrire(la, "session.json", {"A": {"maj": "2026-10-23T10:00", "fichiers": ["a.pdf"]}})
ecrire(la, "sauvegarde/tampons/t1.pdf", {"tampon": 1})
verifie(miroir.synchroniser(pa)[1] == 2, "poste A : session et tampon envoyés sur le Drive")
pb, lb = poste("B")
r = miroir.synchroniser(pb); verifie(r[0] >= 2 and lire(lb, "session.json")["A"]["fichiers"] == ["a.pdf"], "poste B : les reçoit")
_h = os.path.getmtime(os.path.join(lb, "session.json"))
ecrire(lb, "session.json", dict(lire(lb, "session.json"), B={"maj": "2026-10-23T11:00", "fichiers": ["b.pdf"]}))
os.utime(os.path.join(lb, "session.json"), (_h, _h))   # horloge grossiere de Windows : meme heure qu'avant
miroir.synchroniser(pb)
os.environ["HOME"] = os.environ["APPDATA"] = os.path.join(base, "A")
ecrire(la, "session.json", {"A": {"maj": "2026-10-23T12:00", "fichiers": ["a2.pdf"]}})   # A n'a pas encore vu B
miroir.synchroniser(pa)
sa = lire(la, "session.json")
verifie(sa["A"]["fichiers"] == ["a2.pdf"] and sa["B"]["fichiers"] == ["b.pdf"], "modifs des deux côtés : session fusionnée, rien de perdu")
verifie(miroir.synchroniser(pa) == (0, 0), "plus rien à faire ensuite")
srv.shutdown()
from PySide6.QtGui import QGuiApplication
_app = QGuiApplication.instance() or QGuiApplication([])
from app import avatars
verifie(not avatars.recuperer_photo(c, distant.emplacement(c)) and not avatars.photo_a_demander(c),
        "compte sans photo : pastille, et on ne redemande pas à chaque synchro")
verifie(not avatars.icone_compte(c, {"comptes_icone": "photo"}).isNull(), "icône du compte dessinée quand même")
print(f"\n{ok} vérifications Google Drive réussies")
