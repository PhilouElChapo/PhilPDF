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
