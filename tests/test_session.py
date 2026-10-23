"""Cascade de reprise de session : deux machines simulees, fichiers deplaces, renommes, appris."""
import os, shutil, sys, tempfile, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["PHILPDF_LANGUE"] = "fr"       # les tests verifient les textes francais
import app.session as m
from app.session import Session

ok = 0
def verifie(cond, msg):
    global ok
    assert cond, msg
    ok += 1
    print("OK ", msg)

class P(dict):
    def enregistrer(self): pass

def machine(home):
    """Simule un poste : dossier utilisateur et dossiers par defaut (sous Windows, les vrais dossiers
    connus de la machine de fabrication seraient renvoyes sinon)."""
    os.environ["HOME"] = os.environ["USERPROFILE"] = home
    m._cache_connus.clear()
    m._cache_connus.update(maison=home, documents=os.path.join(home, "Documents"),
                           telechargements=os.path.join(home, "Téléchargements"), bureau=os.path.join(home, "Bureau"))

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
f_ = pdf(os.path.join(pharma, "Clients", "Durand", "f.pdf"), b"F")
g_ = pdf(os.path.join(pharma, "Clients", "Martin", "g.pdf"), b"G")

# --- machine Pharmacie
machine(pharma)
S1 = Session(P(machine="Pharmacie", racines=[], drive=""), sess, corr)
S1.ecrire([(x, 3 if x == a else 0, 1.5 if x == a else None) for x in (a, b, c, d, e_, f_, g_)])
F = S1.lire()["Pharmacie"]["fichiers"]
verifie(F[0].get("connu") == "documents" and F[0]["relatif_connu"].replace("\\", "/") == "Ordonnances/a.pdf",
        "a.pdf noté dans le dossier par défaut Documents")
time.sleep(0.01)

# --- copie sur la machine Maison (autre utilisateur), a des endroits differents
pdf(os.path.join(maison, "Documents", "Ordonnances", "a.pdf"), b"A")       # meme dossier Documents
pdf(os.path.join(nas, "Archives", "Ordo", "b.pdf"), b"B")                   # autre dossier, meme nom
pdf(os.path.join(nas, "Archives", "Ordo", "c_renomme.pdf"), b"C")           # renomme
pdf(os.path.join(maison, "d.pdf"), b"X")                                    # meme nom, contenu different
pdf(os.path.join(nas, "Pharma", "Clients", "Durand", "f.pdf"), b"F")        # arborescence copiee sur le NAS
pdf(os.path.join(nas, "Pharma", "Clients", "Martin", "g.pdf"), b"G")
shutil.rmtree(pharma)

machine(maison)
S2 = Session(P(machine="Maison", racines=[], nas=nas, drive=""), sess, corr)
verifie(S2.autres_machines()[0][0] == "Pharmacie" and S2.autres_machines()[0][2] == 7, "autre machine vue avec 7 fichiers")
verifie(S2.discordance([])[0] == "Pharmacie", "discordance détectée (session plus récente, fichiers différents)")
F = S2.lire()["Pharmacie"]["fichiers"]
verifie(F[0]["page"] == 3 and F[0]["zoom"] == 1.5, "page et zoom mémorisés")
t = time.monotonic()
R = S2.retrouver_tous("Pharmacie", F[:5], delai=8)
verifie(time.monotonic() - t < 8, "recherche en quelques secondes au plus")
verifie(R[0][0] and R[0][0].startswith(maison) and "Documents" in R[0][1], "a.pdf : Documents de ce PC")
verifie(R[1][0] and "Ordo" in R[1][0] and R[1][1] == "retrouvé par son nom", "b.pdf : retrouvé par son nom dans le NAS")
verifie(R[2][0] and R[2][0].endswith("c_renomme.pdf"), "c.pdf : renommé, retrouvé par son contenu")
verifie(R[3][0] is None, "d.pdf : même nom, autre contenu -> introuvable (pas de confusion)")
verifie(R[4][0] is None and R[4][1].startswith("introuvable"), "e.pdf : introuvable")

# --- apprentissage : f.pdf trouve par son nom -> on apprend aussi la racine commune
r_f = S2.retrouver_tous("Pharmacie", [F[5]])[0]
S2.apprendre_depuis("Pharmacie", F[5], r_f[0])
appris = [x[1] for x in S2.correspondances()]
verifie(any(x.endswith("/Phil") for x in appris), "racine commune apprise (…/Users/Phil -> …/NAS/Pharma)")
verifie(S2.retrouver_direct("Pharmacie", F[6])[1] == "dossier déjà appris", "g.pdf (autre dossier) trouvé tout de suite grâce à l'apprentissage")
S2.oublier("Pharmacie", appris[0])
verifie(len(S2.correspondances()) == len(appris) - 1, "une correspondance peut être oubliée")

# --- l'ecriture de Maison ne detruit pas la session de Pharmacie ; plus de discordance ensuite
S2.ecrire([(R[0][0], 0, None)])
verifie(set(S2.lire()) == {"Pharmacie", "Maison"}, "les deux machines coexistent dans la session")
verifie(S2.discordance([R[0][0]]) is None, "plus de notification une fois la session d'ici à jour")

# --- limite de duree
m.LIMITE_FICHIERS, avant = 3, m.LIMITE_FICHIERS
R = S2.retrouver_tous("Pharmacie", [F[4]])
verifie(R[0][1] == "introuvable (recherche limitée)", "recherche arrêtée à la limite, signalée comme telle")
m.LIMITE_FICHIERS = avant
shutil.rmtree(base)
print(f"\n{ok} vérifications de session réussies")
