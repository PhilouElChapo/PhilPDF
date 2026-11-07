"""Aide TWAIN 32 bits : dialogue avec un faux programme d'aide (messages JSON, pages en fichiers), relais
automatique quand le pilote 64 bits plante a l'ouverture, et commande inconnue de l'aide reelle."""
import io, json, os, stat, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("PHILPDF_LANGUE", "fr")
from moteur import scanner as S

ok = 0


def verif(c, m):
    global ok
    assert c, m
    ok += 1
    print("✓", m)


# faux programme d'aide : liste une source, numerise 2 pages
d = tempfile.mkdtemp()
faux = os.path.join(d, "aide.py")
with open(faux, "w") as f:
    f.write(f"""#!{sys.executable}
import json, os, sys
from PIL import Image
a = sys.argv[1:]
def dire(**k): print(json.dumps(k), flush=True)
if a[0] == "liste":
    dire(journal="essai")
    dire(sources=[{{"nom": "AD225WN-AEG", "gestionnaire": "twain_32.dll"}}])
elif a[0] == "numeriser":
    if a[2] == "plante":
        dire(erreur="OSError : access violation", etapes=["DAT_IDENTITY/MSG_OPENDS"], ouverture=True); sys.exit(1)
    for i in range(2):
        p = os.path.join(a[1], "p%03d.bmp" % i); Image.new("RGB", (30, 40), "white").save(p); dire(page=p)
    dire(fin=2, args=a)
""")
os.chmod(faux, os.stat(faux).st_mode | stat.S_IEXEC)
S.aide32 = lambda: faux
S._journal = lambda m: JOURNAL.append(m)
JOURNAL = []

src = S.scanners_twain32()
verif(src == {"AD225WN-AEG": "twain_32.dll"}, "liste des sources 32 bits lue")
verif(any("essai" in x for x in JOURNAL), "messages de l'aide recopiés au journal")
im = S.numeriser("twain32:AD225WN-AEG", "gris", 200, "chargeur")
verif(len(im) == 2 and im[0][:2] == b"BM", "2 pages BMP rendues par l'aide")

# pilote 64 bits qui plante a l'ouverture : relais automatique par l'aide 32 bits
appels = []


def plante(nom, *a, **k):
    appels.append(nom)
    raise S.OuvertureImpossible("plante")


S._numeriser_twain = plante
im = S.numeriser("twain:AD225WN-AEG", "couleur", 300, "chargeur", fenetre=1)
verif(len(im) == 2 and appels == ["AD225WN-AEG"], "pilote 64 bits planté : pages numérisées par le 32 bits")
verif(any("pilote 32 bits" in x for x in JOURNAL), "relais noté au journal")
im = S.numeriser("twain:AD225WN-AEG", "couleur", 300, "chargeur", fenetre=1)
verif(len(im) == 2 and appels == ["AD225WN-AEG"], "ensuite, 32 bits directement (pas de nouveau plantage)")

# source inconnue du 32 bits : l'erreur 64 bits remonte telle quelle
try:
    S.numeriser("twain:Autre", "couleur", 300, "chargeur")
    verif(False, "erreur attendue")
except S.OuvertureImpossible:
    verif(True, "source inconnue du 32 bits : message d'ouverture impossible conservé")

# l'aide elle-meme plante a l'ouverture : message clair
S._SOURCES32["plante"] = ""
try:
    S.numeriser("twain32:plante", "couleur", 300, "chargeur")
    verif(False, "erreur attendue")
except S.OuvertureImpossible as e:
    verif("32 bits" in str(e), "aide 32 bits plantée à l'ouverture : message clair")

# l'aide reelle : commande inconnue -> code 2, message JSON
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "twain32"))
import aide_twain32 as A
b = io.StringIO(); vrai = sys.stdout; sys.stdout = b
r = A.main(["n'importe"])
sys.stdout = vrai
verif(r == 2 and "erreur" in json.loads(b.getvalue()), "aide réelle : commande inconnue refusée proprement")
print("RESULTAT : OK" if ok == 9 else "RESULTAT : ECHEC")
