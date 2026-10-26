"""OneDrive, Dropbox et Box en direct, contre des serveurs simules : autorisation par le navigateur,
envoi (dossiers crees), mise a jour sans doublon, telechargement, liste, jeton durable renouvele (Box)."""
import base64, hashlib, json, os, re, socket, sys, tempfile, threading, urllib.parse, urllib.request, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import annotations  # noqa: F401
os.environ["PHILPDF_LANGUE"] = "fr"
base = tempfile.mkdtemp()
os.environ["HOME"] = os.environ["APPDATA"] = base
for t in ("ONEDRIVE", "DROPBOX", "BOX"):
    os.environ[f"PHILPDF_{t}_ID"] = "id-" + t.lower()
os.environ["PHILPDF_BOX_SECRET"] = "secret-box"
from app import distant, oauth, coffre
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtGui import QImage, QColor
appli = QApplication.instance() or QApplication([])
_img = QImage(40, 40, QImage.Format_RGB32); _img.fill(QColor("#ff8800"))
_buf = QBuffer(); _buf.open(QIODevice.WriteOnly); _img.save(_buf, "PNG"); PHOTO = bytes(_buf.data())
from app import avatars

ok = 0
def verifie(cond, msg):
    global ok
    assert cond, msg
    ok += 1
    print("OK ", msg)

ARBRE = {}                       # chemin -> octets ; les dossiers sont deduits ou crees
DOSSIERS = {"/"}
JETONS = {"valides": set(), "refresh": {}}
BOX_IDS = {"/": "0"}
def box_id(chemin):
    if chemin not in BOX_IDS:
        BOX_IDS[chemin] = str(len(BOX_IDS) + 100)
    return BOX_IDS[chemin]
def box_chemin(i):
    return next(c for c, x in BOX_IDS.items() if x == i)
def creer_parents(c):
    p = os.path.dirname(c)
    while p not in DOSSIERS:
        DOSSIERS.add(p); p = os.path.dirname(p)
def enfants(d):
    d = d.rstrip("/") or "/"
    out = []
    for x in sorted(DOSSIERS | set(ARBRE)):
        if x != "/" and os.path.dirname(x) == d:
            out.append((os.path.basename(x), x in DOSSIERS, len(ARBRE.get(x, b"")), x))
    return out

class Serveur(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _json(self, d, code=200):
        b = json.dumps(d).encode(); self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def _octets(self, b):
        self.send_response(200); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def _corps(self):
        return self.rfile.read(int(self.headers.get("Content-Length", 0) or 0))
    def _auth(self):
        if self.headers.get("Authorization", "")[7:] not in JETONS["valides"]:
            self._json({"error": "invalid_token"}, 401); return False
        return True
    def do_GET(self):
        u = urllib.parse.urlsplit(self.path); q = dict(urllib.parse.parse_qsl(u.query)); p = urllib.parse.unquote(u.path)
        if p.endswith("/auth"):
            JETONS["defi"] = q["code_challenge"]
            self.send_response(302)
            self.send_header("Location", q["redirect_uri"] + ("&" if "?" in q["redirect_uri"] else "?") +
                             urllib.parse.urlencode({"code": "CODE", "state": q["state"]}))
            self.end_headers(); return
        if p == "/photo.png": return self._octets(PHOTO)          # adresse publique (Dropbox)
        if not self._auth(): return
        if p == "/graph/me": return self._json({"mail": "phil@outlook.fr"})
        if p in ("/graph/me/photos/96x96/$value", "/box/2.0/users/me/avatar"): return self._octets(PHOTO)
        m = re.match(r"/graph/me/drive/root(?::(.*?):)?/(children|content)$", p)
        if m:
            c = m.group(1) or "/"
            if m.group(2) == "children":
                if c not in DOSSIERS: return self._json({"error": {"code": "itemNotFound"}}, 404)
                return self._json({"value": [dict({"name": n, "size": t, "lastModifiedDateTime": f"t{len(ARBRE.get(x, b''))}"},
                                                  **({"folder": {}} if d else {})) for n, d, t, x in enfants(c)]})
            return self._octets(ARBRE[c])
        if p == "/box/2.0/users/me": return self._json({"login": "phil@box.fr"})
        m = re.match(r"/box/2.0/folders/(\w+)/items$", p)
        if m:
            e = [{"id": box_id(x), "type": "folder" if d else "file", "name": n, "size": t, "modified_at": "x"}
                 for n, d, t, x in enfants(box_chemin(m.group(1)))]
            return self._json({"entries": e, "total_count": len(e)})
        m = re.match(r"/box/2.0/files/(\w+)/content$", p)
        if m: return self._octets(ARBRE[box_chemin(m.group(1))])
        self._json({}, 404)
    def do_PUT(self):
        p = urllib.parse.unquote(urllib.parse.urlsplit(self.path).path); corps = self._corps()
        if not self._auth(): return
        m = re.match(r"/graph/me/drive/root:(.*?):/content$", p)
        ARBRE[m.group(1)] = corps; creer_parents(m.group(1)); self._json({"id": "x"})
    def do_POST(self):
        u = urllib.parse.urlsplit(self.path); p = urllib.parse.unquote(u.path); corps = self._corps()
        if p.endswith("/token"):
            f = dict(urllib.parse.parse_qsl(corps.decode())); four = p.split("/")[1]
            if four == "box": assert f.get("client_secret") == "secret-box"
            if f["grant_type"] == "authorization_code":
                d = base64.urlsafe_b64encode(hashlib.sha256(f["code_verifier"].encode()).digest()).rstrip(b"=").decode()
                assert d == JETONS["defi"], "PKCE"
                rt = f"RT-{four}-1"
            else:
                if f["refresh_token"] != JETONS["refresh"].get(four):
                    return self._json({"error": "invalid_grant"}, 400)
                rt = f"RT-{four}-{uuid.uuid4().hex[:4]}" if four == "box" else f["refresh_token"]   # Box : rotation
            JETONS["refresh"][four] = rt
            at = "AT" + uuid.uuid4().hex[:6]; JETONS["valides"].add(at)
            return self._json({"access_token": at, "refresh_token": rt, "expires_in": 3600})
        if not self._auth(): return
        if p == "/dbx/2/users/get_current_account":
            return self._json({"email": "phil@dropbox.fr", "profile_photo_url": f"http://127.0.0.1:{P}/photo.png"})
        if p == "/dbx/2/files/list_folder":
            c = json.loads(corps)["path"] or "/"
            if c not in DOSSIERS: return self._json({"error_summary": "path/not_found/"}, 409)
            return self._json({"entries": [{".tag": "folder" if d else "file", "name": n, "size": t, "server_modified": f"t{t}"}
                                           for n, d, t, x in enfants(c)], "has_more": False})
        if p in ("/dbxc/2/files/download", "/dbxc/2/files/upload"):
            a = json.loads(self.headers["Dropbox-API-Arg"])
            if p.endswith("download"): return self._octets(ARBRE[a["path"]])
            assert a["mode"] == "overwrite"
            ARBRE[a["path"]] = corps; creer_parents(a["path"]); return self._json({"name": os.path.basename(a["path"])})
        if p == "/box/2.0/folders":
            d = json.loads(corps); c = os.path.join(box_chemin(d["parent"]["id"]), d["name"]); DOSSIERS.add(c)
            return self._json({"id": box_id(c)})
        m = re.match(r"/boxup/2.0/files(?:/(\w+))?/content$", p)
        if m:
            bord = self.headers["Content-Type"].split("boundary=")[1].encode()
            parts = [x for x in corps.split(b"--" + bord) if b"Content-Disposition" in x]
            attr = json.loads(parts[0].split(b"\r\n\r\n", 1)[1].strip())
            data = parts[1].split(b"\r\n\r\n", 1)[1][:-2]
            c = box_chemin(m.group(1)) if m.group(1) else os.path.join(box_chemin(attr["parent"]["id"]), attr["name"])
            ARBRE[c] = data
            return self._json({"entries": [{"id": box_id(c)}]})
        self._json({}, 404)

s = socket.socket(); s.bind(("127.0.0.1", 0)); P = s.getsockname()[1]; s.close()
srv = ThreadingHTTPServer(("127.0.0.1", P), Serveur); threading.Thread(target=srv.serve_forever, daemon=True).start()
B = f"http://127.0.0.1:{P}"
distant.GRAPH, distant.DROPBOX_API, distant.DROPBOX_CONTENU = B + "/graph", B + "/dbx/2", B + "/dbxc/2"
distant.BOX_API, distant.BOX_ENVOI = B + "/box/2.0", B + "/boxup/2.0"
for t in ("onedrive", "dropbox", "box"):
    oauth.FOURNISSEURS[t].update(auth=f"{B}/{t}/auth", jeton=f"{B}/{t}/token")
    oauth.FOURNISSEURS[t]["retour"] = oauth.FOURNISSEURS[t]["retour"].replace("localhost", "127.0.0.1")

PRECONNEXIONS = []
def navigateur(url):
    """Comme Chrome ou Edge : une connexion vide ouverte d'avance vers le retour, puis la vraie requete."""
    retour = urllib.parse.urlsplit(dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))["redirect_uri"])
    vide = socket.create_connection((retour.hostname, retour.port))
    PRECONNEXIONS.append(vide)                     # gardee ouverte, sans rien envoyer
    threading.Thread(target=lambda: urllib.request.urlopen(url, timeout=10).read(), daemon=True).start()

local = os.path.join(base, "f.pdf")
for t, qui in (("onedrive", "phil@outlook.fr"), ("dropbox", "phil@dropbox.fr"), ("box", "phil@box.fr")):
    ARBRE.clear(); DOSSIERS.clear(); DOSSIERS.add("/")
    nom = distant.TYPES[t]
    j = oauth.autoriser(t, ouvrir=navigateur, delai=10)
    c = distant.nouveau_compte(t); coffre.enregistrer(c["id"] + ".jeton", j["refresh_token"])
    e = distant.emplacement(c)
    verifie(qui in e.tester(), f"{nom} : autorisation (malgré une connexion vide du navigateur) et test de connexion")
    open(local, "wb").write(b"%PDF v1"); e.envoyer(local, "/PhilPDF/Factures/a.pdf")
    verifie([x.nom for x in e.lister("/PhilPDF")] == ["Factures"] and [x.nom for x in e.lister("/PhilPDF/Factures")] == ["a.pdf"],
            f"{nom} : envoi, dossiers créés")
    open(local, "wb").write(b"%PDF version 2"); e.envoyer(local, "/PhilPDF/Factures/a.pdf")
    verifie(list(ARBRE.values()).count(b"%PDF version 2") == 1 and len(ARBRE) == 1, f"{nom} : mise à jour sans doublon")
    dst = os.path.join(base, "g.pdf"); e.telecharger("/PhilPDF/Factures/a.pdf", dst)
    verifie(open(dst, "rb").read() == b"%PDF version 2", f"{nom} : téléchargement")
    verifie(set(e.modifies("/PhilPDF/Factures")) == {"a.pdf"} and e.modifies("/Absent") == {}, f"{nom} : état pour la synchronisation")
    verifie(avatars.recuperer_photo(c, e) and os.path.exists(avatars.chemin_photo(c)), f"{nom} : photo du compte récupérée")
    pm = avatars.icone_compte(c, {"comptes_icone": "photo"}, 48).pixmap(48, 48).toImage()
    verifie(pm.pixelColor(24, 24).name() == "#ff8800", f"{nom} : la photo est au centre de la roue")
    pm = avatars.icone_compte(c, {"comptes_icone": "pastille"}, 48).pixmap(48, 48).toImage()
    verifie(pm.pixelColor(17, 17).name() == avatars.PASTILLES[t][1], f"{nom} : pastille de couleur du service")
    if t == "box":
        JETONS["valides"].clear(); e2 = distant.emplacement(c); e2.lister("/")
        JETONS["valides"].clear(); e3 = distant.emplacement(c); e3.lister("/")
        verifie(coffre.lire(c["id"] + ".jeton") == JETONS["refresh"]["box"], "Box : jeton durable renouvelé et gardé à chaque fois")
srv.shutdown()
print(f"\n{ok} vérifications OneDrive, Dropbox et Box réussies")
