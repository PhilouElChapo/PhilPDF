"""Alleger : JBIG2 sans perte (C et Python identiques, decodage exact par MuPDF), passage en noir et blanc des
scans de texte, images noir et blanc non reduites. Lancement : python tests/test_alleger.py"""
import os, sys, tempfile, io
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import annotations  # noqa: F401
import numpy as np
import pymupdf as fitz
from moteur import jbig2 as J

ok = []


def verif(c, quoi):
    ok.append((bool(c), quoi))
    print(("OK    " if c else "ECHEC ") + quoi)


# une page de texte, rendue en scan gris 300 dpi
src = fitz.open()
p = src.new_page()
for i in range(25):
    p.insert_text((50, 60 + i * 28), f"Ligne {i} : ordonnance n° 123456789 — Docteur Martin, Cannes", fontsize=11)
pm = p.get_pixmap(dpi=300, colorspace=fitz.csGRAY)
a = np.frombuffer(pm.samples, dtype=np.uint8).reshape(pm.height, pm.stride)[:, :pm.width]
noir = a < 128
bits = np.packbits(noir, axis=1)
w, h = pm.width, pm.height
print("module C :", J.rapide())
jc = J.encoder(bits.tobytes(), w, h, bits.shape[1])
# Python sur une bande (plus lent)
bande = np.packbits(noir[:300], axis=1)
lib, J._LIB, J._ESSAYE = J._LIB, None, True
jp = J.encoder(bande.tobytes(), w, 300, bande.shape[1])
J._LIB = lib
verif(not lib or jp == J.encoder(bande.tobytes(), w, 300, bande.shape[1]), "JBIG2 : C et Python donnent le même flux")
# PDF avec l'image en noir et blanc (Flate), puis allege
import zlib


def page_bitonale(doc):
    """Page avec une image 1 bit (0 = noir), compressee Flate, comme beaucoup de scanners."""
    q = doc.new_page()
    x = doc.get_new_xref()
    brut = np.packbits(~noir, axis=1).tobytes()
    doc.update_object(x, f"<</Type/XObject/Subtype/Image/Width {w}/Height {h}/ColorSpace/DeviceGray"
                         f"/BitsPerComponent 1>>")
    doc.update_stream(x, brut, compress=True)
    doc.xref_set_key(q.xref, "Resources", f"<</XObject<</Im0 {x} 0 R>>>>")
    c = doc.get_new_xref()
    doc.update_object(c, "<<>>")
    doc.update_stream(c, f"q {q.rect.width} 0 0 {q.rect.height} 0 0 cm /Im0 Do Q".encode())
    doc.xref_set_key(q.xref, "Contents", f"{c} 0 R")
    return x


d = fitz.open()
x = page_bitonale(d)
avant = len(d.xref_stream_raw(x))
n, gain = J.recompresser(d)
apres = len(d.xref_stream_raw(x))
verif(n == 1 and apres < avant / 2, f"image noir et blanc : {avant // 1024} Ko -> {apres // 1024} Ko en JBIG2")
pix = fitz.Pixmap(d, x)
b = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.stride)[:, :pix.width]
verif(np.array_equal(b < 128, noir), "JBIG2 sans perte : chaque point identique après décodage")
# scan gris -> noir et blanc
d2 = fitz.open()
q2 = d2.new_page()
q2.insert_image(q2.rect, pixmap=pm)
avant2 = len(d2.tobytes(garbage=3, deflate=True))
nb = J.en_noir_et_blanc(d2)
apres2 = len(d2.tobytes(garbage=3, deflate=True))
verif(nb == 1 and apres2 < avant2 / 3, f"scan gris passé en noir et blanc : {avant2 // 1024} Ko -> {apres2 // 1024} Ko")
txt = d2[0].get_pixmap(dpi=100)
verif(txt.width > 0, "page toujours lisible")
# une photo n'est pas touchee
d3 = fitz.open()
q3 = d3.new_page()
arr = (np.add.outer(np.arange(800), np.arange(800)) * 255 // 1600).astype(np.uint8)
g2 = fitz.Pixmap(fitz.csGRAY, 800, 800, arr.tobytes(), False)
q3.insert_image(q3.rect, pixmap=g2)
verif(J.en_noir_et_blanc(d3) == 0, "photo (dégradé) laissée en gris")
# alleger complet : les images noir et blanc ne sont pas reduites en resolution
from app.alleger import alleger
r = {"images": True, "dpi": 150, "qualite": 75, "seuil": 200, "gris": False, "polices": True, "nettoyer": True,
     "infos": False, "jbig2": True, "noir_blanc": False, "polices_formulaire": True}
d4 = fitz.open()
page_bitonale(d4)
res = fitz.open("pdf", alleger(d4.tobytes(), r))
img = res[0].get_images(full=True)[0]
verif(img[2] == w and "JBIG2" in img[8], f"Alléger : image noir et blanc gardée à sa résolution, en JBIG2 ({img[2]} px, {img[8]})")
n_ok = sum(1 for c, _q in ok if c)
print(f"\n{n_ok}/{len(ok)} vérifications d'allègement réussies")
sys.exit(0 if n_ok == len(ok) else 1)
