"""Assistant IA contre des serveurs Claude et Gemini simules : donnees sensibles, appel, JSON, modele retire
remplace automatiquement, repli sur le second moteur ; renommer et classer, apprentissage, echeances."""
import json, os, socket, sys, tempfile, threading, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import annotations  # noqa: F401
os.environ["PHILPDF_LANGUE"] = "fr"
base = tempfile.mkdtemp()
os.environ["HOME"] = os.environ["APPDATA"] = base
from app import ia, apprentissage

ok = 0
def verifie(cond, msg):
    global ok
    assert cond, msg
    ok += 1
    print("OK ", msg)

# --- donnees sensibles
def nir(corps):
    return corps + f"{97 - int(corps) % 97:02d}"
n = nir("1850578006084")
t = f"""Virement sur FR76 3000 6000 0112 3456 7890 189 ; carte 4970 1012 3456 7893 ; assuré {n[0]} {n[1:3]} {n[3:5]} {n[5:7]} {n[7:10]} {n[10:13]} {n[13:]}.
Mot de passe : Azerty123"""
g = {x for x, _y in ia.donnees_sensibles(t)}
verifie({"IBAN (coordonnées bancaires)", "Numéro de carte bancaire", "Numéro de sécurité sociale", "Mot de passe ou code"} <= g,
        "données sensibles : IBAN, carte, sécurité sociale, mot de passe repérés")
verifie(all("189" not in x or x.startswith("FR76") for _g, x in ia.donnees_sensibles(t)), "données sensibles : extraits masqués")
verifie(ia.donnees_sensibles("Facture n° 1234567890123 du 12/10/2026, total 45,90 €") == [], "pas de fausse alerte sur une facture ordinaire")

# --- serveurs simules
ETAT = {"claude_modeles": ["claude-sonnet-9-0", "claude-haiku-9-0"], "appels": []}
class S(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _json(self, d, code=200):
        b = json.dumps(d).encode(); self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        u = urllib.parse.urlsplit(self.path)
        if u.path == "/claude/models":
            assert self.headers["x-api-key"] == "CLEF-C"
            return self._json({"data": [{"id": i} for i in ETAT["claude_modeles"]]})
        if u.path == "/gemini/models":
            return self._json({"models": [{"name": "models/gemini-9.5-flash", "supportedGenerationMethods": ["generateContent"]},
                                          {"name": "models/gemini-8.0-flash", "supportedGenerationMethods": ["generateContent"]},
                                          {"name": "models/gemini-9.5-flash-image", "supportedGenerationMethods": ["generateContent"]},
                                          {"name": "models/embedding-1", "supportedGenerationMethods": ["embedContent"]}]})
        self._json({}, 404)
    def do_POST(self):
        u = urllib.parse.urlsplit(self.path)
        corps = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if u.path == "/claude/messages":
            if self.headers.get("x-api-key") != "CLEF-C" and self.headers.get("Authorization") != "Bearer sk-ant-usr-B":
                return self._json({"error": {"message": "invalid x-api-key"}}, 401)
            if corps["model"] not in ETAT["claude_modeles"]:
                return self._json({"error": {"message": f"model: {corps['model']}"}}, 404)
            ETAT["appels"].append(("claude", corps["model"], corps["system"]))
            texte = corps["messages"][0]["content"][-1]["text"]
            if "ranger" in corps["system"]:
                r = {"date": "2026-10-20", "expediteur": "CPAM des Alpes-Maritimes", "objet": "rejet de facturation",
                     "type": "courrier", "dossier": "", "echeances": [{"date": "2026-12-20", "libelle": "délai de recours"}]}
                return self._json({"content": [{"type": "text", "text": "```json\n" + json.dumps(r) + "\n```"}]})
            return self._json({"content": [{"type": "text", "text": "Réponse à : " + texte[:20]}]})
        if u.path.startswith("/gemini/models/") and "image" in u.path:     # edition d'image : on renvoie l'image inversee
            import base64 as _b, io as _io
            from PIL import Image as _I, ImageOps as _O
            parts = corps["contents"][0]["parts"]
            ETAT["image"] = {"images": sum(1 for p in parts if "inline_data" in p), "texte": parts[-1]["text"],
                             "modalites": corps["generationConfig"]["responseModalities"]}
            im = _I.open(_io.BytesIO(_b.b64decode(parts[0]["inline_data"]["data"]))).convert("RGB")
            b = _io.BytesIO(); _O.invert(im).save(b, "PNG")
            return self._json({"candidates": [{"content": {"parts": [{"text": "voici"},
                               {"inlineData": {"mimeType": "image/png", "data": _b.b64encode(b.getvalue()).decode()}}]}}]})
        if u.path.startswith("/gemini/models/"):
            modele = u.path.split("/")[-1].split(":")[0]
            if modele in ETAT.get("surcharges", ()):
                return self._json({"error": {"message": "This model is currently experiencing high demand."}}, 503)
            if modele != "gemini-9.5-flash" and modele not in ETAT.get("acceptes", ()):
                return self._json({"error": {"message": "not found"}}, 404)
            ETAT["appels"].append(("gemini", modele, corps["system_instruction"]["parts"][0]["text"]))
            return self._json({"candidates": [{"content": {"parts": [{"text": '{"ok": true}'}]}}]})
        self._json({}, 404)

s = socket.socket(); s.bind(("127.0.0.1", 0)); P = s.getsockname()[1]; s.close()
srv = ThreadingHTTPServer(("127.0.0.1", P), S); threading.Thread(target=srv.serve_forever, daemon=True).start()
ia.CLAUDE_API, ia.GEMINI_API = f"http://127.0.0.1:{P}/claude", f"http://127.0.0.1:{P}/gemini"

p = {"ia_moteur": "claude", "clef_claude": "CLEF-C", "clef_gemini": ""}
r = ia.demander(p, "Consigne", "Bonjour PhilPDF")
verifie(r == "Réponse à : Bonjour PhilPDF" and ETAT["appels"][-1][1] == "claude-sonnet-9-0",
        "Claude : modèle retiré remplacé automatiquement par le plus récent")
try:
    ia.demander(dict(p, clef_claude="FAUX"), "c", "t"); verifie(False, "clef refusée")
except ia.ErreurIA as e:
    verifie("Clef Claude refusée" in str(e), "Claude : clef refusée, message clair")
r = ia.demander({"ia_moteur": "claude", "clef_claude": "  sk-ant-usr-B \n"}, "Consigne", "Bonjour")
verifie(r.startswith("Réponse"), "Claude : clef collée avec espaces, présentée autrement (Bearer) si besoin")
r = ia.demander({"ia_moteur": "gemini", "clef_gemini": "G"}, "Consigne", "x", json_attendu=True)
verifie(r == {"ok": True} and ETAT["appels"][-1][1] == "gemini-9.5-flash", "Gemini : JSON, modèle le plus récent choisi")
r = ia.demander({"ia_moteur": "deux", "clef_claude": "FAUX", "clef_gemini": "G"}, "c", "t", json_attendu=True)
verifie(r == {"ok": True}, "deux moteurs : Gemini prend le relais si Claude échoue")
ETAT["surcharges"], ETAT["acceptes"] = {"gemini-9.5-flash"}, {"gemini-8.0-flash"}
ia._modeles_trouves.pop("gemini_secours", None)
r = ia.demander({"ia_moteur": "gemini", "clef_gemini": "G"}, "Consigne", "x", json_attendu=True)
verifie(r == {"ok": True} and ETAT["appels"][-1][1] == "gemini-8.0-flash" and ia.dernier["modele"] == "gemini-8.0-flash",
        "Gemini surchargé (503) : un autre modèle Gemini répond")
ETAT["surcharges"] = {"gemini-9.5-flash", "gemini-8.0-flash"}
ia._modeles_trouves["gemini"] = "gemini-9.5-flash"
r = ia.demander({"ia_moteur": "gemini", "clef_gemini": "G", "clef_claude": "CLEF-C"}, "Consigne", "Bonjour")
verifie(r.startswith("Réponse à") and ia.dernier["moteur"] == "claude" and ia.dernier["secours"],
        "tout Gemini surchargé : Claude prend le relais et on le dit")
ETAT["surcharges"], ETAT["acceptes"] = set(), set()
ia._modeles_trouves["gemini"] = "gemini-9.5-flash"
try:
    ia.demander({}, "c", "t"); verifie(False, "sans clef")
except ia.ErreurIA as e:
    verifie("Préférences" in str(e), "sans clef : on dit où la mettre")

# --- renommer et classer : JSON, nom, apprentissage partage, echeances
from app.dialogues_ia import nom_propose, CONSIGNES_CLASSER
r = ia.demander(p, CONSIGNES_CLASSER, "Courrier CPAM", json_attendu=True)
verifie(nom_propose(r) == "2026-10-20 CPAM des Alpes-Maritimes – rejet de facturation.pdf", "nom proposé : date, expéditeur, objet")
class Params(dict):
    def enregistrer(self): pass
docs = os.path.join(base, "Documents"); os.makedirs(docs)
from app import session
session._cache_connus.clear(); session._cache_connus.update(documents=docs, telechargements=os.path.join(base, "Downloads"))
pa = Params(nas="")
dossier_cpam = os.path.join(docs, "Pharmacie", "CPAM")
verifie(apprentissage.abstraire(dossier_cpam, pa) == "{documents}/Pharmacie/CPAM", "dossier enregistré sous une forme valable sur chaque poste")
apprentissage.retenir_classement(pa, "CPAM des Alpes-Maritimes", dossier_cpam)
autre_docs = os.path.join(base, "AutrePoste", "Docs"); os.makedirs(autre_docs)
session._cache_connus.update(documents=autre_docs)
verifie(apprentissage.dossier_appris(pa, "cpam des alpes maritimes") == os.path.join(autre_docs, "Pharmacie", "CPAM"),
        "appris sur un poste, retrouvé sur un autre (Documents différent)")
apprentissage.retenir_classement(pa, "CPAM des Alpes-Maritimes", os.path.join(autre_docs, "Pharmacie", "CPAM"))
verifie(apprentissage.lire(pa, "classement.json")["expediteurs"]["cpam des alpes maritimes"]["n"] == 2, "choix confirmé : compteur augmenté")
import datetime
dans_dix = (datetime.date.today() + datetime.timedelta(days=10)).isoformat()
apprentissage.ajouter_echeance(pa, dans_dix, "délai de recours", os.path.join(docs, "a.pdf"))
apprentissage.ajouter_echeance(pa, "2020-01-01", "passé", os.path.join(docs, "b.pdf"))
e = apprentissage.echeances_a_venir(pa)
verifie(len(e) == 1 and e[0]["libelle"] == "délai de recours", "échéances : seules celles à venir sont rappelées")
from app import miroir
a = apprentissage.lire(pa, "classement.json")
b = json.loads(json.dumps(a)); b["expediteurs"]["urssaf"] = {"nom": "URSSAF", "dossier": "{documents}/URSSAF", "n": 1, "maj": "2026-10-24T10:00:00"}
f = miroir._fusion(a, b)
verifie(set(f["expediteurs"]) == {"cpam des alpes maritimes", "urssaf"}, "apprentissages de deux postes fusionnés sans perte")
# --- retouche d'image par Gemini (Claude ne sait pas rendre une image)
from PIL import Image as _I
import io as _io
_b = _io.BytesIO(); _I.new("RGB", (40, 20), (10, 200, 30)).save(_b, "PNG")
from app import styles_ia
cons = styles_ia.consigne_complete("Transforme en aquarelle.", "legere", True,
                                   [{"couleur_nom": "rouge", "consigne": "le ciel en orage"}])
r_ = ia.retoucher_image({"clef_gemini": "CLEF-G"}, _b.getvalue(), cons, zones_png=_b.getvalue())
px = _I.open(_io.BytesIO(r_)).convert("RGB").getpixel((5, 5))
verifie(px == (245, 55, 225), f"image : Gemini renvoie l'image modifiée ({px})")
verifie(ETAT["image"]["images"] == 2 and "zone 1 (rouge) : le ciel en orage" in ETAT["image"]["texte"]
        and "IMAGE" in ETAT["image"]["modalites"] and "léger" in ETAT["image"]["texte"], "image : zones et consigne envoyées")
try:
    ia.retoucher_image({"clef_claude": "x"}, _b.getvalue(), "x"); verifie(False, "sans clef Gemini")
except ia.ErreurIA as e:
    verifie("Gemini" in str(e), "image : sans clef Gemini, message clair (Claude ne sait pas faire d'image)")
verifie(len(styles_ia.styles()) >= 50 and not any(n.lower() in ("ghibli", "pixar", "disney") for _g, n, _c in styles_ia.styles()),
        "styles : catalogue complet, aucun nom de studio ou de marque")
srv.shutdown()
print(f"\n{ok} vérifications de l'assistant IA réussies")
