"""Test du moteur Modifier sur un PDF fabrique a la volee (aucun fichier personnel)."""
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import annotations  # noqa: F401  (erreurs lisibles sur GitHub)
os.environ["PHILPDF_LANGUE"] = "fr"       # les tests verifient les textes francais
import pymupdf as fitz
from moteur.modifier import Editeur

d = fitz.open()
p = d.new_page()
p.insert_text((72, 100), "Net à payer : 130,00 EUR", fontname="hebo", fontsize=12)
p.insert_text((72, 130), "Facture du 10-05-2026", fontname="helv", fontsize=10)
src = os.path.join(tempfile.mkdtemp(), "test.pdf")
d.save(src)

e = Editeur(src)
e.remplacer(0, "Net à payer", "Montant payé")
e.remplacer(0, "10-05-2026", "10-09-2026")
out = src.replace(".pdf", "_ok.pdf")
e.enregistrer(out)
t = fitz.open(out)[0].get_text()
assert "Montant payé : 130,00 EUR" in t, t
assert "10-09-2026" in t, t
polices = {f[3] for f in fitz.open(out)[0].get_fonts()}
assert polices <= {"Helvetica", "Helvetica-Bold"}, polices
print("Moteur Modifier : OK (", "; ".join(e.journal), ")")

# autre methode (bouton « ↻ », celle de PhilPDF Android) : lettres seules retirees, police d'origine, cadre garde
from moteur import methode_lignes
d = fitz.open()
p = d.new_page()
p.draw_rect(fitz.Rect(60, 60, 400, 100), color=(0, 0, 0), fill=(0.9, 0.95, 1))
p.insert_text((72, 85), "Avis d'opération de virement", fontname="hebo", fontsize=14)
src2 = os.path.join(tempfile.mkdtemp(), "avis.pdf")
d.save(src2)
d = fitz.open(src2)
para = Editeur(d).paragraphe_a(0, fitz.Point(80, 80))
assert para, "paragraphe non trouve"
res = methode_lignes.reecrire(d, 0, para, "Avis de virement modifié")
t = d[0].get_text()
assert "Avis de virement modifié" in t and "opération" not in t, t
assert res["originale"] and res["police"] == "Helvetica-Bold", res
pix = d[0].get_pixmap(clip=fitz.Rect(300, 70, 390, 90))
assert pix.pixel(40, 10)[:3] != (255, 255, 255), "le fond bleu du cadre doit rester"
print("Autre methode (Android) : OK (", res, ")")
