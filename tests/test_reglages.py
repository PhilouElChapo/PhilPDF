"""Preferences : export chiffre, import selectif (communs / poste / secrets), copie automatique sur le Drive."""
import json, os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["PHILPDF_LANGUE"] = "fr"
base = tempfile.mkdtemp()
os.environ["HOME"] = os.environ["APPDATA"] = base
from app import reglages, coffre

ok = 0
def verifie(cond, msg):
    global ok
    assert cond, msg
    ok += 1
    print("OK ", msg)

class P(dict):
    def enregistrer(self): pass

drive = os.path.join(base, "Drive"); os.makedirs(drive)
a = P(machine="Pharmacie", auteur="Phil", langue="fr", outils_epingles=["modifier", "imprimer"], volet="icones",
      comptes=[{"id": "c1", "type": "webdav", "adresse": "https://nas:5006"}], nas="Z:\\", racines=["D:\\Docs"],
      drive=drive, clef_claude="sk-test")
coffre.enregistrer("c1", "motdepasse")
f = os.path.join(base, "p.philpdf")
reglages.exporter(f, reglages.instantane(a, avec_secrets=True), "phrase secrète")
verifie(b"motdepasse" not in open(f, "rb").read() and b"sk-test" not in open(f, "rb").read(), "export chiffré : rien de lisible")
try:
    reglages.importer(f, "mauvaise"); verifie(False, "phrase vérifiée")
except reglages.PhraseRequise:
    verifie(True, "mauvaise phrase refusée")
d = reglages.importer(f, "phrase secrète")
coffre.supprimer("c1")
b = P(machine="Maison", nas="")
reglages.appliquer(b, d, communs=True, poste=False, secrets=True)
verifie(b["machine"] == "Maison" and b["nas"] == "" and b["volet"] == "icones" and b["outils_epingles"] == ["modifier", "imprimer"],
        "nouveau poste : réglages communs repris, chemins du poste gardés")
verifie(coffre.lire("c1") == "motdepasse" and b["clef_claude"] == "sk-test", "mots de passe et clefs restaurés")
c = P(machine="?")
reglages.appliquer(c, d, communs=True, poste=True, secrets=False)
verifie(c["machine"] == "Pharmacie" and c["racines"] == ["D:\\Docs"], "réinstallation du même poste : ses chemins reviennent")
verifie(reglages.ecrire_drive(a), "copie automatique sur le Drive")
dd = reglages.lire_drive(os.path.join(drive, "PhilPDF", "preferences.json"))
verifie("Pharmacie" in dd["postes"] and dd["communs"]["auteur"] == "Phil" and "secrets" not in json.dumps(dd)
        and "motdepasse" not in json.dumps(dd), "Drive : communs + poste, jamais de mot de passe")
print(f"\n{ok} vérifications de préférences réussies")
