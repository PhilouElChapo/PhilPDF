"""Test automatique de l'interface (sans ecran) + captures.
Lancement : QT_QPA_PLATFORM=offscreen python tests/test_interface.py <dossier_captures>
Aucun document reel : les PDF de test sont fabriques a la volee."""
import os, sys, shutil, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["APPDATA"] = tempfile.mkdtemp()
os.environ["HOME"] = os.environ["APPDATA"]
from PySide6.QtWidgets import QApplication, QMessageBox, QInputDialog, QFileDialog, QDialog
from PySide6.QtCore import Qt, QPoint, QPointF
from PySide6.QtTest import QTest
import pymupdf as fitz

app = QApplication(sys.argv)
import app.document as D
import app.fenetre as F
import app.dialogues as G
from app.fenetre import Fenetre
from app.document import DialogueRemplacer
from moteur import objets

SORTIE = sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp()
os.makedirs(SORTIE, exist_ok=True)
TRAVAIL = tempfile.mkdtemp()


def fabriquer(nom, lignes, image=False):
    d = fitz.open()
    p = d.new_page()
    y = 90
    for txt, police, taille in lignes:
        p.insert_text((72, y), txt, fontname=police, fontsize=taille)
        y += taille * 1.8
    if image:
        pm = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 60, 40), False)
        pm.clear_with(180)
        p.insert_image(fitz.Rect(400, 80, 520, 160), pixmap=pm)
    d.new_page()
    d[1].insert_text((72, 90), "Deuxième page", fontname="helv", fontsize=12)
    d.new_page()
    d[2].insert_text((72, 90), "Troisième page", fontname="helv", fontsize=12)
    d.save(os.path.join(TRAVAIL, nom))


fabriquer("Facture_test.pdf", [("Dupont", "hebo", 12), ("Mas des Oliviers", "helv", 11),
                               ("06460 Saint-Vallier", "helv", 11), ("Facture N° 2", "hebo", 11),
                               ("Total : 130,00 EUR", "helv", 11)], image=True)
fabriquer("Devis_test.pdf", [("Devis du 10-05-2026", "helv", 9), ("Net à payer : 1 090,00 EUR", "helv", 9),
                             ("Net à payer : mille quatre-vingt-dix euros", "helv", 8)])
ok = []


def verif(cond, quoi):
    ok.append((bool(cond), quoi))
    print(("OK   " if cond else "ECHEC") + " " + quoi)


def capture(w, nom):
    app.processEvents()
    w.grab().save(os.path.join(SORTIE, nom))


# reponses automatiques aux dialogues
reponse_question = [0]
D.question = F.question = lambda *a, **k: reponse_question[0]
QMessageBox.information = staticmethod(lambda *a, **k: None)
QMessageBox.warning = staticmethod(lambda *a, **k: print("AVERTISSEMENT", a[2] if len(a) > 2 else a))
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
QInputDialog.getMultiLineText = staticmethod(lambda *a, **k: ("Note de test", True))

w = Fenetre()
w.resize(1440, 900)
w.show()
w.onglets.setCurrentWidget(w.outils)
capture(w, "01_outils.png")

o = w.ouvrir(os.path.join(TRAVAIL, "Facture_test.pdf"))
verif(o is not None and len(o.page_widgets) == 3, "ouverture")
o.changer_zoom(1.25)

# --- menu Edition complet et en francais
noms = [a.text() for a in w.menuBar().actions()[1].menu().actions() if a.text()]
verif(all(x in noms for x in ("Couper", "Copier", "Coller", "Supprimer", "Sélectionner tout", "Rétablir")), f"menu Edition : {noms}")
verif(all("Paramètres" not in a.text() for m in w.menuBar().actions() for a in m.menu().actions()), "aucun « Paramètres » dans les menus")

# --- outil lance depuis la page Outils : applique au document ouvert
w.onglets.setCurrentWidget(w.outils)
w.lancer_outil("modifier")
verif(w.onglets.currentWidget() is o and o.mode == "modifier", "« Tous les outils » agit sur le document courant")

# --- mode Modifier : selectionner et deplacer une ligne
pw = o.page_widgets[0]
r_ligne = next(fitz.Rect(r) for r, t in o.lignes_page(0) if "Mas des" in t)
obj = o.objet_sous(0, r_ligne.tl + (3, 3))
o.choisir_objet(obj)
capture(w, "02_mode_modifier.png")
o.appliquer_deplacement(r_ligne + (0, 200, 0, 200))
verif(any("Mas des" in t and fitz.Rect(r).y0 > r_ligne.y0 + 150 for r, t in o.lignes_page(0)), "ligne déplacée")

# --- edition directe dans la page (WYSIWYG)
r_dup = next(fitz.Rect(r) for r, t in o.lignes_page(0) if t.strip() == "Dupont")
pw = o.page_widgets[0]
pw.ouvrir_editeur(r_dup, None, "Dupont")
pw.editeur.champ.setText("Dupontel")
capture(w, "03_edition_directe.png")
pw.editeur.valider()
verif(any(t.strip() == "Dupontel" for _, t in o.lignes_page(0)), "correction directe dans la page")

# --- edition partielle : le gras d'origine est garde
r_tot = next(fitz.Rect(r) for r, t in o.lignes_page(0) if "Total" in t)
o.modifier_ligne_texte(0, r_tot, "Total : 1 130,00 EUR")
verif(any("1 130,00" in t for _, t in o.lignes_page(0)), "montant corrigé")

# --- ajouter du texte puis le deplacer
o.changer_mode("ajout_texte")
pw = o.page_widgets[0]
pw.ouvrir_editeur(None, fitz.Point(72, 500), "")
pw.editeur.champ.setText("Texte ajouté")
pw.editeur.valider()
r_aj = next((fitz.Rect(r) for r, t in o.lignes_page(0) if "Texte ajouté" in t), None)
verif(r_aj is not None, "texte ajouté")
o.choisir_objet(o.objet_sous(0, r_aj.tl + (2, 2)))
o.appliquer_deplacement(r_aj + (100, 30, 100, 30))
verif(any("Texte ajouté" in t and fitz.Rect(r).x0 > r_aj.x0 + 80 for r, t in o.lignes_page(0)), "texte ajouté puis déplacé")

# --- image : deplacer
im = o.images_page(0)
verif(len(im) == 1, "image détectée")
o.choisir_objet(o.objet_sous(0, im[0][1].tl + (5, 5)))
o.appliquer_deplacement(im[0][1] + (-300, 400, -300, 400))
verif(o.images_page(0) and o.images_page(0)[0][1].y0 > 400, "image déplacée")
o.changer_mode(None)

# --- tampon pret a l'emploi : poser, deplacer, redimensionner, supprimer
o.ouvrir_bibliotheque("tampons")
o._choisir_biblio(o.liste_biblio.item(0))
o.poser_objet(0, fitz.Point(300, 300))
st = [a for a in o.doc[0].annots() if objets.est_objet_philpdf(a)]
verif(len(st) == 1, "tampon « Reçu » posé")
capture(w, "04_tampon_pose.png")
r0 = fitz.Rect(o.objet["rect"])
o.appliquer_deplacement(r0 + (50, 80, 50, 80))
r1 = [fitz.Rect(a.rect) for a in o.doc[0].annots()][0]
verif(abs(r1.x0 - r0.x0 - 50) < 1 and abs(r1.y0 - r0.y0 - 80) < 1, "tampon déplacé")
o.choisir_objet(o.objet_sous(0, r1.tl + (5, 5)))
o.appliquer_deplacement(fitz.Rect(r1.x0, r1.y0, r1.x1 + 60, r1.y1 + 20))
r2 = [fitz.Rect(a.rect) for a in o.doc[0].annots()][0]
verif(r2.width > r1.width + 50, "tampon redimensionné")
o.copier()
o.coller(1, fitz.Point(100, 100))
verif(len(list(o.doc[1].annots())) == 1, "tampon copié-collé sur la page 2")
o.choisir_objet(o.objet_sous(0, r2.tl + (5, 5)))
o.supprimer()
verif(len(list(o.doc[0].annots())) == 0, "tampon supprimé")

# --- import d'un tampon depuis une zone d'un PDF (tampon Acrobat = annotation)
src = fitz.open()
sp = src.new_page()
a = sp.add_stamp_annot(fitz.Rect(50, 50, 250, 130), stamp=0)
a.set_info(subject="Tampon Pharmacie test")
a.update()
src.save(os.path.join(TRAVAIL, "tampon_source.pdf"))
trouves = objets.tampons_du_pdf(os.path.join(TRAVAIL, "tampon_source.pdf"))
verif(trouves and trouves[0][2] == "Tampon Pharmacie test", "tampon Acrobat détecté dans un PDF")
pdf = objets.pdf_depuis_zone(os.path.join(TRAVAIL, "tampon_source.pdf"), 0, trouves[0][1])
e = w.biblio.ajouter("tampons", "Tampon importé", pdf)
verif(any(x["nom"] == "Tampon importé" for x in w.biblio.elements("tampons")), "tampon importé dans la bibliothèque")

# --- signatures multiples (dessinee) posees et deplacables
pave = G.PaveSignature(None)
pave.traits = [[(30, 120), (80, 60), (130, 140), (200, 70), (260, 130)], [(60, 150), (240, 150)]]
w.biblio.ajouter("signatures", "Paraphe", pave.resultat())
w.biblio.ajouter("signatures", "Signature complète", pave.resultat() + b" ")
verif(len(w.biblio.elements("signatures")) == 2, "deux signatures gérées")
o.ouvrir_bibliotheque("signatures")
o._choisir_biblio(o.liste_biblio.item(1))
o.poser_objet(2, fitz.Point(300, 600))
verif(len(list(o.doc[2].annots())) == 1 and o.objet and o.objet["philpdf"], "signature posée et sélectionnée")
capture(w, "05_signatures.png")

# --- sauvegarde Drive et restauration sur un autre PC
drive = tempfile.mkdtemp()
w.params["drive"] = drive
n = w.biblio.sauvegarder_drive()
verif(n >= 3 and os.path.exists(os.path.join(drive, "PhilPDF", "sauvegarde", "index.json")), f"sauvegarde sur le Drive ({n} éléments)")
from app.bibliotheque import Bibliotheque
from app import config
autre = tempfile.mkdtemp()
ancien = config.dossier_donnees
config.dossier_donnees = lambda: autre
import app.bibliotheque as B
B.dossier_donnees = lambda: autre
b2 = Bibliotheque({"drive": drive, "machine": "Autre PC"})
verif(len(b2.nouveautes_drive()) >= 3 and b2.restaurer_drive() >= 3, "restauration sur un autre PC")
B.dossier_donnees = ancien
w._session()
verif(os.path.exists(os.path.join(drive, "PhilPDF", "session.json")), "session (emplacements) écrite sur le Drive")

# --- filigrane, en-tete
d = G.DialogueFiligrane(None, w.params, len(o.doc), 0)
d.modele.setCurrentText("CONFIDENTIEL")
o.memoriser()
d.appliquer(o.doc)
verif("CONFIDENTIEL" in o.doc[1].get_text(), "filigrane sur toutes les pages")
d = G.DialogueEntete(None)
d.appliquer(o.doc)
verif("Page 2 / 3" in o.doc[1].get_text(), "pied de page numéroté")

# --- organiser : reordonner (glisser-deposer)
o.organiser(True)
capture(w, "06_organiser.png")
o.reordonner([2, 0, 1])
verif("Troisième" in o.doc[0].get_text() and "Dupontel" in o.doc[1].get_text(), "pages réordonnées")
o.organiser(False)

# --- export JPG et Word
QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: TRAVAIL)
w.exporter("jpg", 96, 80)
verif(os.path.exists(os.path.join(TRAVAIL, "Facture_test_p1.jpg")), "export JPG")
QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (os.path.join(TRAVAIL, "export.docx"), ""))
w.exporter("docx")
verif(os.path.exists(os.path.join(TRAVAIL, "export.docx")), "export Word (.docx)")

# --- rechercher et remplacer
o2 = w.ouvrir(os.path.join(TRAVAIL, "Devis_test.pdf"))
dr = DialogueRemplacer(o2, "Net à payer")
dr.show()
app.processEvents()
verif("2 occurrences" in dr.compte.text(), f"compteur : {dr.compte.text()}")
dr.remp.setText("Montant payé")
dr.remplacer_tout()
verif("Net à payer" not in o2.doc[0].get_text(), "remplacer tout")
dr.close()

# --- enregistrer et relire
w.onglets.setCurrentWidget(o)
chemin = os.path.join(TRAVAIL, "Facture_enregistree.pdf")
o.enregistrer(chemin)
re_ = fitz.open(chemin)
verif("Dupontel" in re_[1].get_text() and len(list(re_[0].annots())) == 1, f"enregistré et relu ({os.path.getsize(chemin) // 1024} Ko)")

# --- fermeture : question en francais
vu = {}
F.question = lambda parent, titre, texte, boutons: (vu.setdefault("b", [b for b, _ in boutons]), 1)[1]
o.modifie = True
w.fermer_onglet(w.onglets.indexOf(o))
verif(vu.get("b") == ["Enregistrer", "Ne pas enregistrer", "Annuler"], f"fermeture : {vu.get('b')}")

print(f"\n{sum(c for c, _ in ok)}/{len(ok)} vérifications réussies")
sys.exit(0 if all(c for c, _ in ok) else 1)
