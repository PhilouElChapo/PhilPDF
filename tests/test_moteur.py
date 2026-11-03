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

# --- fichier abime par une ancienne version Android : debris dans Contents, retires sans rien perdre
from moteur import reparer
d = fitz.open()
p = d.new_page()
p.insert_text((72, 100), "Texte garde", fontsize=20)
x = p.get_contents()[0]
d.xref_set_key(p.xref, "Contents", f"[<00000000B0EC00>{x} 0 R<00000000B0EC00><00000000B0EC00>]")
src3 = os.path.join(tempfile.mkdtemp(), "abime.pdf")
d.save(src3)
d = fitz.open(src3)
assert reparer.debris(d) == [(0, "contenu")], "debris non vus"
assert d.xref_get_key(d[0].xref, "Contents") == ("array", f"[{x} 0 R]"), d.xref_get_key(d[0].xref, "Contents")
assert "Texte garde" in d[0].get_text() and reparer.debris(d) == []
print("Debris d'Android retires : OK")

# --- image rangee dans un sous-objet (PDF Mac, InDesign...) : tourner, retourner, recadrer, deplacer
import numpy as np
from moteur import retouche as R, dessins
src = fitz.open()
sp = src.new_page(width=300, height=200)
pm = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 60, 40), False)
pm.set_rect(fitz.IRect(0, 0, 30, 40), (220, 30, 30))
pm.set_rect(fitz.IRect(30, 0, 60, 40), (30, 30, 220))
sp.insert_image(fitz.Rect(50, 50, 250, 150), pixmap=pm)
d = fitz.open()
p = d.new_page(width=400, height=300)
p.show_pdf_page(fitz.Rect(50, 50, 350, 250), src, 0)          # l'image est dans un sous-objet de la page
ed = Editeur(d)
x = ed.images(0)[0][0]
assert any(im[9] for im in d[0].get_images(full=True)), "image attendue dans un sous-objet"
ed.tourner_image(0, x, 90)
assert abs(ed.geometrie_image(0, x)[3] - 90) < 0.5, ed.geometrie_image(0, x)
ed.tourner_image(0, x, -90)
ed.retourner_image(0, x, True)
r = ed.images(0)[0][1]
pix = d[0].get_pixmap(clip=fitz.Rect(r.x0 + 5, r.y0 + 5, r.x0 + 15, r.y0 + 15))
assert pix.pixel(2, 2)[2] > 150 and pix.pixel(2, 2)[0] < 100, ("apres miroir, le bleu doit etre a gauche", pix.pixel(2, 2))
img = R.depuis_pdf(d, x)
nx = ed.recadrer_image(0, x, (0, 0, img.shape[1] // 2, img.shape[0]), img)
r2 = next(rr for xx, rr in ed.images(0) if xx == nx)
# image retournee : la moitie gauche des pixels est a droite sur la page, et y reste
assert abs(r2.width - r.width / 2) < 2 and abs(r2.x1 - r.x1) < 2, (r, r2)
ed.deplacer_image(0, nx, fitz.Rect(10, 10, 60, 60))
assert abs(next(rr for xx, rr in ed.images(0) if xx == nx).x0 - 10) < 1
print("Image dans un sous-objet : tournee, retournee, recadree, deplacee : OK")

# --- dessin vectoriel (schema) : choisi comme un objet, deplace sans changer d'aspect, tourne, supprime
d = fitz.open()
p = d.new_page()
p.draw_rect(fitz.Rect(100, 100, 200, 160), color=(0, 0, 0), fill=(0.8, 0.8, 0.8), width=1.5)
p.draw_line(fitz.Point(100, 130), fitz.Point(200, 130), color=(0, 0, 0))
p.draw_circle(fitz.Point(400, 600), 30, color=(1, 0, 0), fill=(0, 0, 1))
g = dessins.groupes(p)
assert len(g) == 2, g
avant = np.frombuffer(p.get_pixmap(dpi=40).samples, np.uint8).astype(int)
for r in g:
    dessins.deplacer(d[0], r, r)
apres = np.frombuffer(d[0].get_pixmap(dpi=40).samples, np.uint8).astype(int)
assert np.abs(avant - apres).mean() < 0.5, np.abs(avant - apres).mean()
cadre = next(r for r in dessins.groupes(d[0]) if r.x0 < 300)
nouveau = dessins.deplacer(d[0], cadre, cadre + (200, 300, 200, 300))
assert any(abs(r.x0 - nouveau.x0) < 2 for r in dessins.groupes(d[0])), "dessin deplace introuvable"
dessins.tourner(d[0], nouveau, 90)
dessins.supprimer(d[0], next(r for r in dessins.groupes(d[0]) if r.y0 > 500 and r.x0 > 350))
assert len(dessins.groupes(d[0])) == 1
print("Dessins vectoriels : deplaces, tournes, supprimes : OK")

# --- dessins avec degrades et motifs : deplaces tels qu'ecrits dans le PDF (rien n'est redessine ni perdu)
d = fitz.open()
p = d.new_page(width=420, height=300)
fn = d.get_new_xref(); d.update_object(fn, "<</FunctionType 2/Domain[0 1]/C0[0.1 0.3 0.9]/C1[1 0.8 0.1]/N 1>>")
sh = d.get_new_xref(); d.update_object(sh, f"<</ShadingType 2/ColorSpace/DeviceRGB/Coords[40 160 160 260]/Function {fn} 0 R/Extend[true true]>>")
sh2 = d.get_new_xref(); d.update_object(sh2, f"<</ShadingType 3/ColorSpace/DeviceRGB/Coords[260 210 0 260 210 60]/Function {fn} 0 R/Extend[true true]>>")
pat = d.get_new_xref(); d.update_object(pat, f"<</PatternType 2/Shading {sh2} 0 R/Matrix[1 0 0 1 0 0]>>")
c = d.get_new_xref(); d.update_object(c, "<<>>")
d.update_stream(c, b"q 40 160 120 100 re W n /Sh1 sh Q 0 0 0 RG 2 w 40 160 120 100 re S\nq /Pattern cs /P1 scn 200 150 120 120 re f Q")
d.xref_set_key(p.xref, "Contents", f"{c} 0 R")
d.xref_set_key(p.xref, "Resources", f"<</Shading<</Sh1 {sh} 0 R>>/Pattern<</P1 {pat} 0 R>>>>")
g = dessins.groupes(d[0])
assert any(abs(r.x0 - 200) < 1 and abs(r.y0 - 30) < 1 for r in g), ("degrade seul (motif) choisi comme un dessin", g)
def _px(page):
    pm = page.get_pixmap(dpi=72)
    return np.frombuffer(pm.samples, np.uint8).reshape(pm.h, pm.w, pm.n).astype(int)
av = _px(d[0])
for r in g:
    dessins.deplacer(d[0], r, fitz.Rect(r) + (10, 20, 10, 20) if r.x0 < 100 else fitz.Rect(r) + (60, 100, 60, 100))
ap = _px(d[0])
assert np.abs(av[40:140, 40:160] - ap[60:160, 50:170]).mean() < 1, "le degrade suit le dessin"
assert np.abs(av[30:150, 200:320] - ap[130:250, 260:380]).mean() < 1, "le motif suit le dessin"
dessins.tourner(d[0], fitz.Rect(260, 130, 380, 250), 90)
ap2 = _px(d[0])
assert ap2[190, 320, 2] > 150 and ap2[190, 320, 0] < 120, "centre du degrade tourne : toujours bleu"
print("Dessins avec degrades et motifs : deplaces et tournes sans rien perdre : OK")

# --- retouche : « Effacer » sur le fond d'un scan choisi a la baguette (grande zone) : rapide, et pas noirci
import time as _t
_img = np.full((2300, 1650, 4), 255, np.uint8)
_img[500:540, 200:900, :3] = 0                                     # une ligne de « texte » noir
_m = R.baguette(_img, 10, 10, 30)
_d0 = _t.time()
_o = R.effacer(_img, _m, "fond")
assert _t.time() - _d0 < 5 and _o[:, :, :3][_m].mean() > 240, ("grande zone : remplie de sa couleur", _t.time() - _d0)
assert _o[520, 500, 0] == 0, "le texte hors zone reste"
print("Retouche, grande zone effacee : OK")
