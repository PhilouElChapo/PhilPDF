"""Scanners reseau sans pilote (eSCL) : lecture d'une reponse mDNS, puis numerisation par un faux scanner HTTP."""
import io, os, socket, struct, sys, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from moteur import escl


def nom(n):
    return b"".join(bytes([len(p)]) + p.encode() for p in n.split(".")) + b"\0"


def rr(n, typ, rd):
    return nom(n) + struct.pack(">HHIH", typ, 0x8001, 120, len(rd)) + rd


inst = "HP OfficeJet 8020._uscan._tcp.local"
txt = b"".join(bytes([len(x)]) + x for x in (b"rs=eSCL", b"ty=HP OfficeJet Pro 8020"))
paquet = struct.pack(">HHHHHH", 0, 0x8400, 0, 1, 0, 3) + rr("_uscan._tcp.local", 12, nom(inst)) + \
    rr(inst, 33, struct.pack(">HHH", 0, 0, 8080) + nom("hp8020.local")) + rr(inst, 16, txt) + \
    rr("hp8020.local", 1, socket.inet_aton("192.168.1.40"))
e = {"ptr": set(), "srv": {}, "txt": {}, "a": {}}
escl._lire_reponse(paquet, e)
assert e["ptr"] == {inst} and e["srv"][inst] == ("hp8020.local", 8080), e
assert e["txt"][inst]["ty"] == "HP OfficeJet Pro 8020" and e["a"]["hp8020.local"] == "192.168.1.40"
print("mDNS : instance, port, modèle, adresse lus : OK")

# faux scanner : 2 pages au chargeur, puis 404
from PIL import Image
b = io.BytesIO(); Image.new("RGB", (100, 140), "white").save(b, "JPEG"); JPG = b.getvalue()
etat = {"pages": 2, "recu": b""}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path.endswith("ScannerCapabilities"):
            c = b'<scan:ScannerCapabilities xmlns:scan="http://schemas.hp.com/imaging/escl/2011/05/03"><scan:Platen/><scan:Adf/><scan:DocumentFormatExt>image/jpeg</scan:DocumentFormatExt></scan:ScannerCapabilities>'
            self.send_response(200); self.end_headers(); self.wfile.write(c); return
        if self.path.endswith("/NextDocument") and etat["pages"] > 0:
            etat["pages"] -= 1
            self.send_response(200); self.send_header("Content-Type", "image/jpeg"); self.end_headers(); self.wfile.write(JPG); return
        self.send_response(404); self.end_headers()

    def do_POST(self):
        etat["recu"] = self.rfile.read(int(self.headers["Content-Length"]))
        self.send_response(201); self.send_header("Location", "/eSCL/ScanJobs/42"); self.end_headers()

    def do_DELETE(self):
        self.send_response(200); self.end_headers()


srv = HTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
imgs = escl.numeriser(f"http://127.0.0.1:{srv.server_port}/eSCL", "auto", 300, "chargeur")
assert len(imgs) == 2 and imgs[0][:2] == b"\xff\xd8", len(imgs)
assert b"<pwg:InputSource>Feeder</pwg:InputSource>" in etat["recu"] and b"RGB24" in etat["recu"]
srv.shutdown()
print("eSCL : 2 pages au chargeur numérisées : OK")
from moteur import scanner
p = scanner.assembler(imgs, "auto", 300)
assert len(p) == 0 or len(p) == 2   # pages blanches retirees
# nettoyage : page penchee de 2 degres, taches isolees, trait du bord de la vitre
import cv2, numpy as np
from moteur import nettoyage as N
g = np.full((3300, 2500), 255, np.uint8)
for y in range(400, 2600, 90):
    cv2.putText(g, "Ligne de texte pour essayer le nettoyage", (180, y), cv2.FONT_HERSHEY_SIMPLEX, 2.2, 0, 5)
g = N.tourner(g, 2.0)
rng = np.random.default_rng(1)
for _ in range(120):
    x, y = rng.integers(100, 2400), rng.integers(2700, 3200)
    g[y:y + 3, x:x + 3] = 0
g[:, 4:9] = 0
a = N.angle(g)
assert abs(a + 2.0) < 0.3, a
nb, a2, d = N.page(g, 300)
assert d["taches"] >= 110 and d["bords"] >= 1, d
assert (nb[:, 4:9] < 128).mean() < 0.01, "trait du bord efface"
assert (nb[400:2600] < 128).mean() > 0.01, "texte garde"
print(f"Nettoyage : angle {a:+.2f}, {d['taches']} taches, {d['bords']} bord(s) : OK")
# redresser une page : contenu tourne, texte garde, angle remis a zero
import pymupdf as fitz
_d = fitz.open(); _p = _d.new_page()
for y in range(100, 700, 30):
    _p.insert_text((72, y), "Ligne de texte numero %d pour essayer le redressement" % y, fontsize=12)
def _ang(p):
    pm = p.get_pixmap(dpi=100, colorspace=fitz.csGRAY)
    return N.angle(np.frombuffer(pm.samples, np.uint8).reshape(pm.h, pm.w))
N.redresser_pages(_d, [0], 3.0)
_a = _ang(_d[0]); assert abs(_a + 3) < 0.3, _a
N.redresser_pages(_d, [0], _a); assert abs(_ang(_d[0])) < 0.2 and "numero 100" in _d[0].get_text()
for _x in (60, 300, 540):
    _p.draw_line((_x, 80), (_x, 760), width=1.5)
N.redresser_pages(_d, [0], -2.0, 3.0)
def _mes(p):
    pm = p.get_pixmap(dpi=100, colorspace=fitz.csGRAY)
    g = np.frombuffer(pm.samples, np.uint8).reshape(pm.h, pm.w)
    a = N.angle(g)
    return a, N.angle_vertical(g, a)
_a, _v = _mes(_d[0]); assert abs(_a - 2) < 0.3 and abs(_v + 3) < 0.4, (_a, _v)
N.redresser_pages(_d, [0], _a, _v); _a, _v = _mes(_d[0]); assert abs(_a) < 0.3 and abs(_v) < 0.3, (_a, _v)
print("Redresser la page (lignes et verticales) : OK")
print("RESULTAT : OK")
