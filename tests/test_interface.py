"""Test automatique de l'interface (sans ecran) + captures.
Lancement : QT_QPA_PLATFORM=offscreen python tests/test_interface.py <dossier_captures>"""
import os, sys, shutil, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("APPDATA", tempfile.mkdtemp())
from PySide6.QtWidgets import QApplication, QMessageBox, QInputDialog
from PySide6.QtCore import Qt, QPoint, QPointF
from PySide6.QtTest import QTest
import pymupdf as fitz

app = QApplication(sys.argv)
from app.fenetre import Fenetre
from app.document import DialogueRemplacer

SORTIE = sys.argv[1] if len(sys.argv) > 1 else "/tmp/captures"
os.makedirs(SORTIE, exist_ok=True)
TRAVAIL = tempfile.mkdtemp()


def fabriquer(nom, lignes):
    """PDF de test fabrique a la volee (aucun document reel)."""
    d = fitz.open()
    p = d.new_page()
    y = 90
    for txt, police, taille in lignes:
        p.insert_text((72, y), txt, fontname=police, fontsize=taille)
        y += taille * 1.8
    d.save(os.path.join(TRAVAIL, nom))


fabriquer("Facture_test.pdf", [("Dupont", "hebo", 12), ("Mas des Oliviers", "helv", 11),
                               ("06460 Saint-Vallier", "helv", 11), ("Facture N° 2", "hebo", 11)])
fabriquer("Avis_test.pdf", [("Avis d'opération de virement", "hebo", 12), ("Montant 130,00 EUR", "helv", 10)])
fabriquer("Devis_test.pdf", [("Devis du 10-05-2026", "helv", 9), ("Net à payer : 1 090,00 EUR", "helv", 9),
                             ("Net à payer : mille quatre-vingt-dix euros", "helv", 8)])
ok = []


def verif(cond, quoi):
    ok.append((bool(cond), quoi))
    print(("OK   " if cond else "ECHEC") + " " + quoi)


def capture(w, nom):
    app.processEvents()
    w.grab().save(os.path.join(SORTIE, nom))


# dialogues remplaces par des reponses automatiques
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
QMessageBox.information = staticmethod(lambda *a, **k: None)
QMessageBox.warning = staticmethod(lambda *a, **k: print("AVERTISSEMENT", a[2] if len(a) > 2 else a))
reponses = {}
QInputDialog.getText = staticmethod(lambda parent, titre, label, *a, **k: (reponses.get(titre, ""), True))
QInputDialog.getMultiLineText = staticmethod(lambda *a, **k: ("Note de test", True))

w = Fenetre()
w.resize(1440, 900)
w.show()
capture(w, "01_accueil.png")
w.onglets.setCurrentWidget(w.outils)
capture(w, "02_outils.png")
w.outils.recherche.setText("signer")
app.processEvents()
vis = [t.titre for t, _ in w.outils.tuiles if not t.isHidden()]
verif("Remplir et signer" in vis and "Combiner des fichiers" not in vis, f"recherche d'outil 'signer' -> {vis}")
w.outils.recherche.setText("")

# ouverture + rendu
o = w.ouvrir(os.path.join(TRAVAIL, "Facture_test.pdf"))
verif(o is not None and len(o.page_widgets) == 1, "ouverture de la facture")
o.changer_zoom(1.5)
capture(w, "03_document.png")

# selection de texte + barre rapide
pw = o.page_widgets[0]
lignes = o.lignes_page(0)
cible = next(r for r, t in lignes if "Mas des" in t)
r = pw.vers_ecran(cible)
QTest.mousePress(pw, Qt.LeftButton, Qt.NoModifier, QPoint(int(r.left() + 2), int(r.center().y())))
QTest.mouseMove(pw, QPoint(int(r.right() - 2), int(r.center().y())))
o.etendre_selection(0, pw.vers_pdf(QPointF(r.right() - 2, r.center().y())))
QTest.mouseRelease(pw, Qt.LeftButton, Qt.NoModifier, QPoint(int(r.right() - 2), int(r.center().y())))
app.processEvents()
verif(o.selection and "Oliviers" in o.selection["texte"], f"sélection : {o.selection and o.selection['texte']!r}")
verif(o.barre_rapide.isVisible(), "barre d'actions rapides affichée")
capture(w, "04_selection_barre_rapide.png")
o.annoter("surligner")
verif(len(list(o.doc[0].annots())) == 1, "surlignage ajouté")

# mode Modifier : corriger une ligne
o.changer_mode("modifier")
pw = o.page_widgets[0]
r_delay = next(r for r, t in o.lignes_page(0) if t.strip() == "Dupont")
rr = pw.vers_ecran(r_delay)
pw.survol = fitz.Rect(r_delay).tl + (3, 3)
capture(w, "05_mode_modifier.png")
reponses["Modifier la ligne"] = "Dupontel"
QTest.mouseClick(pw, Qt.LeftButton, Qt.NoModifier, QPoint(int(rr.center().x()), int(rr.center().y())))
app.processEvents()
verif(any(t.strip() == "Dupontel" for _, t in o.lignes_page(0)), "ligne corrigée en « Dupontel » (police d'origine)")
o.changer_mode(None)

# annuler
n_av = len(o.annulations)
o.annuler()
verif(any(t.strip() == "Dupont" for _, t in o.lignes_page(0)), "annuler rétablit « Dupont »")
o.changer_mode("modifier")
pw = o.page_widgets[0]
QTest.mouseClick(pw, Qt.LeftButton, Qt.NoModifier, QPoint(int(rr.center().x()), int(rr.center().y())))
o.changer_mode(None)

# rotation pour l'affichage seulement / dans le fichier
from PySide6.QtWidgets import QMessageBox as MB
orig_exec = MB.exec
MB.exec = lambda self: None  # aucun bouton clique -> affichage seulement
o.pivoter([0])
verif(o.rotation_vue.get(0) == 90 and o.doc[0].rotation == 0, "rotation d'affichage seulement")
o.rotation_vue[0] = 0
o.page_widgets[0].maj_taille()
MB.exec = orig_exec

# rechercher et remplacer
o2 = w.ouvrir(os.path.join(TRAVAIL, "Devis_test.pdf"))
d = DialogueRemplacer(o2, "Net à payer")
d.show()
app.processEvents()
verif("1 occurrence" in d.compte.text() or "2 occurrences" in d.compte.text(), f"compteur : {d.compte.text()}")
d.remp.setText("Montant payé")
capture(d, "06_rechercher_remplacer.png")
d.remplacer_tout()
txt = o2.doc[0].get_text()
verif("Montant payé" in txt and "Net à payer" not in txt, "remplacer tout")
d.close()

# enregistrer
w.onglets.setCurrentWidget(o)
chemin = os.path.join(TRAVAIL, "Facture_test_enregistree.pdf")
o.enregistrer(chemin)
re = fitz.open(chemin)
verif("Dupontel" in re[0].get_text() and len(list(re[0].annots())) == 1, f"enregistré et relu ({os.path.getsize(chemin) // 1024} Ko)")

# combiner (sans dialogue) et alleger
res = fitz.open()
for f in ("Facture_test_enregistree.pdf", "Avis_test.pdf"):
    res.insert_pdf(fitz.open(os.path.join(TRAVAIL, f)))
verif(len(res) == 2, "combinaison de 2 fichiers")

w.onglets.setCurrentWidget(o2)
capture(w, "07_facture_modifiee.png")
print(f"\n{sum(c for c, _ in ok)}/{len(ok)} vérifications réussies")
sys.exit(0 if all(c for c, _ in ok) else 1)
