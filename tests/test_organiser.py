"""Fractionner, parapher, signets et cote a cote."""
import os, sys, tempfile
racine = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, racine)
os.environ["PHILPDF_LANGUE"] = "fr"
os.environ["APPDATA"] = tempfile.mkdtemp()
os.environ["HOME"] = os.environ["APPDATA"]
import pymupdf as fitz

ok_total, n_total = 0, 0


def verif(cond, texte):
    global ok_total, n_total
    n_total += 1
    ok_total += bool(cond)
    print("OK   " if cond else "ECHEC", texte)


from moteur import fractionner as F, paraphe as P

d = fitz.open()
for i in range(12):
    d.new_page().insert_text((72, 100), f"Page {i + 1}", fontsize=30)
d.set_toc([[1, "Introduction", 1], [1, "Chapitre : un/deux", 4], [2, "Sous-partie", 5], [1, "Annexes", 9]])
plan = F.plan(d, "Contrat", "nombre", 5)
verif([len(p) for _n, p in plan] == [5, 5, 2] and plan[0][0] == "Contrat - partie 1.pdf", "toutes les 5 pages")
plan = F.plan(d, "Contrat", "plages", "1-3, 4-10, 11-")
verif([p[0] for _n, p in plan] == [0, 3, 10] and plan[2][1][-1] == 11, "plages, dont une ouverte (11-)")
try:
    F.plan(d, "Contrat", "plages", "9-4")
    verif(False, "plage a l'envers refusee")
except ValueError:
    verif(True, "plage a l'envers refusee")
plan = F.plan(d, "Contrat", "signets", 1)
verif([n for n, _p in plan] == ["1 - Introduction.pdf", "2 - Chapitre un-deux.pdf", "3 - Annexes.pdf"],
      "un fichier par signet, noms sans caracteres interdits")
dos = tempfile.mkdtemp()
faits = F.ecrire(d, dos, plan)
verif(fitz.open(faits[1]).get_toc() == [[1, "Chapitre : un/deux", 1], [2, "Sous-partie", 2]],
      "les signets suivent dans chaque partie")
faits2 = F.ecrire(d, dos, plan)
verif(faits2[0].endswith("Introduction (2).pdf"), "fichier existant garde, le nouveau en (2)")
import numpy as np
lourd = fitz.open()
for i in range(6):
    pl = lourd.new_page()
    bruit = np.random.default_rng(i).integers(0, 255, (300, 300, 3), dtype=np.uint8)
    pl.insert_image(pl.rect, pixmap=fitz.Pixmap(fitz.csRGB, 300, 300, bruit.tobytes(), False))
plan = F.plan(lourd, "Photos", "taille", 0.6)
tailles = [F._poids(lourd, p) for _n, p in plan]
verif(len(plan) > 1 and max(tailles) <= 0.6 * 1048576 and sum(len(p) for _n, p in plan) == 6,
      "par taille : chaque fichier sous le maximum, aucune page perdue")

pdf = P.initiales_pdf("J.-P. D.", "TiIt", souligne=True)
verif(fitz.open("pdf", pdf)[0].get_text().strip() == "J.-P. D.", "initiales ecrites dans la police")
n = P.parapher(d, pdf, P.pages_choisies(len(d), "sauf_derniere"))
verif(n == 11 and len(list(d[0].annots())) == 1 and not list(d[11].annots()), "paraphe sur toutes sauf la derniere")
pg = d[0]
r = list(pg.annots())[0].rect
verif(r.x1 > pg.rect.width - 60 and r.y1 > pg.rect.height - 60, "paraphe en bas a droite")

from PySide6.QtWidgets import QApplication, QDialog, QMessageBox
app = QApplication([])
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
import app.bienvenue as BV
BV.DialogueBienvenue.exec = lambda self: QDialog.Rejected
from app.fenetre import Fenetre
src = os.path.join(tempfile.mkdtemp(), "toc.pdf")
e = fitz.open()
for i in range(6):
    e.new_page().insert_text((72, 100), f"Page {i + 1}")
e.set_toc([[1, "Un", 1], [1, "Deux", 4]])
e.save(src)
src2 = os.path.join(os.path.dirname(src), "autre.pdf")
fitz.open(src).save(src2)
w = Fenetre()
w.resize(1400, 900)
w.show()
w.ouvrir(src)
w.ouvrir(src2)
app.processEvents()
a, b = w.documents()
verif(a.b_onglet_signets.text() == "Signets · 2" and a.pile_gauche.currentIndex() == 0,
      "volet gauche : s'ouvre sur les pages, l'onglet Signets montre leur nombre")
a.montrer_signets(True)
verif(a.arbre_signets.topLevelItemCount() == 2, "arbre des signets")
a._aller_signet(a.arbre_signets.topLevelItem(1))
verif(a.page_courante() == 3, "clic sur un signet : va a sa page")
a.ajouter_signet()
verif(len(a.doc.get_toc()) == 3 and a.modifie, "signet ajoute sur la page affichee")
a.annuler()
verif(len(a.doc.get_toc()) == 2, "Ctrl+Z retire le signet")
a.basculer_vignettes()
verif(not a.gauche.isVisible(), "volet gauche masquable (pages et signets)")
a.basculer_vignettes()
w.afficher_a_cote(a)
app.processEvents()
verif(w.doc_droite is a and w.onglets.currentWidget() is b and len(w.documents()) == 2, "cote a cote")
a.changer_zoom(0.5)
b.changer_zoom(1.5)
verif(a.zoom == 0.5 and b.zoom == 1.5, "chacun son zoom")
a.zone.setFocus()
app.processEvents()
verif(w.doc_courant() is a, "le fichier clique devient le document courant")
w.fermer_cote_a_cote()
verif(w.doc_droite is None and w.onglets.indexOf(a) >= 2, "fin du cote a cote : retour dans les onglets")

print()
print(f"{ok_total}/{n_total} vérifications d'organisation réussies")
sys.exit(0 if ok_total == n_total else 1)
