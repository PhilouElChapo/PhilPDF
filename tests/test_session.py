"""Cascade de reprise de session : deux machines simulees, fichiers deplaces, renommes, appris."""
import os, shutil, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.session import Session

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
sess = os.path.join(drive, "session.json"); corr = os.path.join(drive, "correspondances.json")
pharma = os.path.join(base, "Users", "Phil"); maison = os.path.join(base, "Users", "Autre")
nas = os.path.join(base, "NAS")
def pdf(chemin, contenu):
    os.makedirs(os.path.dirname(chemin), exist_ok=True)
    open(chemin, "wb").write(b"%PDF-1.7\n" + contenu * 5000)
    return chemin

a = pdf(os.path.join(pharma, "Documents", "Ordonnances", "a.pdf"), b"A")
b = pdf(os.path.join(pharma, "Documents", "Ordonnances", "b.pdf"), b"B")
c = pdf(os.path.join(pharma, "Factures", "c.pdf"), b"C")
d = pdf(os.path.join(pharma, "d.pdf"), b"D")
e_ = pdf(os.path.join(pharma, "e.pdf"), b"E")

# machine Pharmacie ecrit sa session
os.environ["HOME"] = pharma; os.environ["USERPROFILE"] = pharma
S1 = Session(P(machine="Pharmacie", racines=[], drive=""), sess, corr)
S1.ecrire([(a, 3, 1.5), (b, 0, None), (c, 0, None), (d, 0, None), (e_, 0, None)])

# copie sur la machine Maison, a des endroits differents
pdf(os.path.join(maison, "Documents", "Ordonnances", "a.pdf"), b"A")       # meme relatif au dossier utilisateur
pdf(os.path.join(nas, "Archives", "Ordo", "b.pdf"), b"B")                   # autre dossier, meme nom
pdf(os.path.join(nas, "Archives", "Ordo", "c_renomme.pdf"), b"C")           # renomme
pdf(os.path.join(maison, "d.pdf"), b"X")                                    # meme nom, contenu different
shutil.rmtree(pharma)                                                       # l'autre PC ne voit pas Pharmacie

os.environ["HOME"] = maison; os.environ["USERPROFILE"] = maison
S2 = Session(P(machine="Maison", racines=[nas], drive=""), sess, corr)
verifie(S2.autres_machines()[0][:1] == ("Pharmacie",) and S2.autres_machines()[0][2] == 5, "autre machine proposée avec 5 fichiers")
F = S2.lire()["Pharmacie"]["fichiers"]
verifie(F[0]["page"] == 3 and F[0]["zoom"] == 1.5, "page et zoom mémorisés")
ch, comment = S2.retrouver_rapide("Pharmacie", F[0])
verifie(ch and ch.startswith(maison) and comment == "dossier utilisateur de ce PC", "a.pdf : transposé sur le dossier utilisateur")
ch, comment = S2.retrouver_rapide("Pharmacie", F[1])
verifie(ch and "Ordo" in ch and comment == "retrouvé par son nom", "b.pdf : retrouvé par son nom dans le NAS déclaré")
S2.apprendre_depuis("Pharmacie", F[1], ch)
verifie(S2.retrouver_rapide("Pharmacie", F[2]) == (None, None), "c.pdf : pas trouvé par nom (renommé)")
ch = S2.retrouver_par_empreinte(F[2])
verifie(ch and ch.endswith("c_renomme.pdf"), "c.pdf : retrouvé par son empreinte")
verifie(S2.retrouver_rapide("Pharmacie", F[3]) == (None, None) and not S2.retrouver_par_empreinte(F[3]),
        "d.pdf : même nom mais autre contenu -> introuvable (pas de faux positif)")
verifie(not S2.retrouver_par_empreinte(F[4]), "e.pdf : introuvable")
# apprentissage : un nouveau fichier du meme dossier source est trouve tout de suite
pdf(os.path.join(nas, "Archives", "Ordo", "z.pdf"), b"Z")
src_z = F[1]["chemin"].replace("b.pdf", "z.pdf")
import app.session as m
ez = {"chemin": src_z, "nom": "z_autre_nom.pdf", "taille": os.path.getsize(os.path.join(nas, "Archives", "Ordo", "z.pdf")),
      "empreinte": m.empreinte(os.path.join(nas, "Archives", "Ordo", "z.pdf"))}
ez["chemin"] = src_z  # le nom d'origine z.pdf, dans le dossier appris
ch, comment = S2.retrouver_rapide("Pharmacie", ez)
verifie(comment == "dossier déjà appris", "dossier appris : correspondance réutilisée")
# ecriture de Maison ne detruit pas la session de Pharmacie
S2.ecrire([(ch, 0, None)])
verifie(set(S2.lire()) == {"Pharmacie", "Maison"}, "les deux machines coexistent dans la session")
shutil.rmtree(base)
print(f"\n{ok} vérifications de session réussies")
