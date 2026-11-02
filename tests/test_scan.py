"""Reconnaissance du texte (OCR) : image gardee a ses proportions, texte a l'endroit et a l'envers, page en couleur."""
import os, sys, tempfile
racine = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, racine)
import pymupdf as fitz
from moteur import scan

ok_total, n_total = 0, 0


def verif(cond, texte):
    global ok_total, n_total
    n_total += 1
    ok_total += bool(cond)
    print("OK   " if cond else "ECHEC", texte)


if not scan.tesseract_exe():
    print("Tesseract absent : test saute")
    sys.exit(0)

tmp = tempfile.mkdtemp()
# un « scan » : page A4 portrait, texte a l'endroit en haut, a l'envers en bas, rendu en image a 200 dpi
src = fitz.open()
p = src.new_page(width=595, height=842)
p.insert_text((60, 120), "Ordonnance du docteur Martin", fontsize=22)
p.insert_text((60, 170), "Paracetamol un comprime matin et soir", fontsize=16)
p.insert_text((520, 700), "Pharmacie centrale de Cannes", fontsize=22, rotate=180)
p.draw_rect(fitz.Rect(400, 300, 500, 360), color=None, fill=(0.9, 0.2, 0.2))
for couleur, nom in ((False, "gris"), (True, "couleur")):
    pm = p.get_pixmap(dpi=200, colorspace=fitz.csRGB if couleur else fitz.csGRAY)
    d = fitz.open()
    q = d.new_page(width=595, height=842)
    q.insert_image(q.rect, pixmap=pm)
    entree, sortie = os.path.join(tmp, nom + ".pdf"), os.path.join(tmp, nom + "_OCR.pdf")
    d.save(entree)
    scan.traiter(entree, sortie)
    o = fitz.open(sortie)[0]
    r = o.get_image_rects(o.get_images()[0][0])[0]
    verif(abs(r.width - 595) < 1 and abs(r.height - 842) < 1, f"{nom} : image en pleine page, proportions gardees ({r})")
    t = o.get_text()
    verif("Ordonnance" in t and "Paracetamol" in t, f"{nom} : texte a l'endroit reconnu")
    verif("Pharmacie" in t and "Cannes" in t, f"{nom} : texte a l'envers reconnu")
    zone = o.search_for("Ordonnance")
    verif(zone and abs(zone[0].y1 - 120) < 15 and abs(zone[0].x0 - 60) < 15, f"{nom} : texte pose sur l'image ({zone})")
    verif(not any(w in t for w in ("ellertnec", "eicamrahP")), f"{nom} : pas de lecture a l'envers fautive")
    if couleur:
        img = fitz.open(sortie)[0].get_images(full=True)[0]
        verif(img[5] != "DeviceGray" and img[4] == 8, f"page en couleur : image d'origine gardee ({img[4]} bits, {img[5]})")

# texte reconnu modifie : lettres de l'image effacees, nouveau texte visible a la meme place, en gras si l'image l'est
from moteur.modifier import Editeur
src = fitz.open()
p = src.new_page(width=595, height=842)
p.insert_text((60, 120), "Ordonnance du docteur Martin", fontsize=22, fontname="hebo")
p.insert_text((60, 170), "Paracetamol un comprime matin et soir", fontsize=16)
pm = p.get_pixmap(dpi=200, colorspace=fitz.csGRAY)
d = fitz.open()
q = d.new_page(width=595, height=842)
q.insert_image(q.rect, pixmap=pm)
entree, sortie = os.path.join(tmp, "modif.pdf"), os.path.join(tmp, "modif_OCR.pdf")
d.save(entree)
scan.traiter(entree, sortie)
d = fitz.open(sortie)
ed = Editeur(d)
para = ed.paragraphe_a(0, fitz.Point(100, 112))
ancien = para["texte"]
ed.modifier_paragraphe(0, para, ancien.replace("Martin", "Durand"))
vis = [s for b in d[0].get_text("dict")["blocks"] for l in b.get("lines", []) for s in l["spans"]
       if "Durand" in s["text"]]
verif(vis and vis[0].get("alpha", 255) == 255 and abs(vis[0]["origin"][1] - 120) < 4,
      f"texte modifie visible, a la meme place ({[(s['text'], s['origin']) for s in vis]})")
verif(vis and "Bold" in vis[0]["font"], f"gras de l'image garde ({vis[0]['font'] if vis else None})")
im = d[0].get_pixmap(dpi=100, clip=fitz.Rect(300, 95, 420, 125), colorspace=fitz.csGRAY)
import numpy as np
noir = (np.frombuffer(im.samples, np.uint8) < 128).mean()
verif(noir > 0.02, "nouveau texte dessine sur la page")
verif("Martin" not in d[0].get_text(), "ancien mot retire")

print()
print(f"{ok_total}/{n_total} vérifications d'OCR réussies")
sys.exit(0 if ok_total == n_total else 1)
