"""Tampons et signatures synchronises entre deux postes via le Drive (ajouts et suppressions)."""
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import annotations  # noqa: F401  (erreurs lisibles sur GitHub)
os.environ["PHILPDF_LANGUE"] = "fr"
import app.bibliotheque as B

ok = 0
def verifie(cond, msg):
    global ok
    assert cond, msg
    ok += 1
    print("OK ", msg)

class P(dict):
    def enregistrer(self): pass

base = tempfile.mkdtemp()
drive = os.path.join(base, "Drive"); os.makedirs(drive)
def poste(nom):
    os.environ["HOME"] = os.environ["APPDATA"] = os.path.join(base, nom)
    os.makedirs(os.environ["HOME"], exist_ok=True)
    return B.Bibliotheque(P(machine=nom, drive=drive))
def sur(nom):
    os.environ["HOME"] = os.environ["APPDATA"] = os.path.join(base, nom)

a = poste("Pharmacie"); a.ajouter("signatures", "Phil", b"%PDF-signature")
b = poste("Maison")
verifie(b.synchroniser_drive()[0] == 1 and [e["nom"] for e in b.index] == ["Phil"], "Maison reçoit la signature de Pharmacie")
b.ajouter("tampons", "Vu", b"%PDF-tampon-vu")
sur("Pharmacie")
verifie(a.synchroniser_drive()[0] == 1 and sorted(e["nom"] for e in a.index) == ["Phil", "Vu"], "Pharmacie reçoit le tampon de Maison")
a.supprimer(next(e for e in a.index if e["nom"] == "Vu"))
sur("Maison")
b.synchroniser_drive()
verifie([e["nom"] for e in b.index] == ["Phil"], "une suppression sur un poste est appliquée sur l'autre")
verifie(not b.nouveautes_drive(), "plus rien de nouveau ensuite")
print(f"\n{ok} vérifications de bibliothèque réussies")
