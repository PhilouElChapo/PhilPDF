"""JBIG2 sans perte pour les images noir et blanc des PDF (scans de texte) : en general 20 a 40 % plus leger que la
compression fax (CCITT G4) et 5 a 10 fois plus que Flate. Sans perte : chaque pixel est garde, aucune lettre ne
peut etre remplacee par une autre (le defaut connu des JBIG2 « avec perte »).

Le codage se fait dans une petite bibliotheque C (jbig2.c, compilee avec PhilPDF) ; sinon en Python, plus lent.
"""
import ctypes
import os
import sys

import pymupdf as fitz

_LIB = None
_ESSAYE = False


def _bibliotheque():
    global _LIB, _ESSAYE
    if _ESSAYE:
        return _LIB
    _ESSAYE = True
    noms = ["philpdf_jbig2.dll"] if sys.platform == "win32" else ["libphilpdf_jbig2.so", "libphilpdf_jbig2.dylib"]
    dossiers = [os.path.dirname(os.path.abspath(__file__))]
    if getattr(sys, "_MEIPASS", None):
        dossiers.insert(0, os.path.join(sys._MEIPASS, "moteur", "jbig2"))
    for d in dossiers:
        for n in noms:
            f = os.path.join(d, n)
            if os.path.exists(f):
                try:
                    lib = ctypes.CDLL(f)
                    lib.philpdf_jbig2.restype = ctypes.c_long
                    lib.philpdf_jbig2.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                                  ctypes.c_char_p, ctypes.c_long]
                    _LIB = lib
                    return lib
                except OSError:
                    pass
    return None


def rapide():
    """True si le codage C est disponible (sinon Python : reserve aux petites images)."""
    return _bibliotheque() is not None


def encoder(bits, largeur, hauteur, pas=None):
    """bits : bitmap 1 bit/pixel, 1 = noir, lignes de « pas » octets. Renvoie le flux pour /JBIG2Decode."""
    pas = pas or (largeur + 7) // 8
    lib = _bibliotheque()
    if lib is not None:
        cap = max(4096, len(bits) * 2 + 1024)
        out = ctypes.create_string_buffer(cap)
        n = lib.philpdf_jbig2(bytes(bits), largeur, hauteur, pas, out, cap)
        if n < 0:
            raise ValueError("JBIG2 : tampon trop petit")
        return out.raw[:n]
    return _encoder_python(bytes(bits), largeur, hauteur, pas)


# ------------------------------------------------------------------ repli en Python (meme algorithme que jbig2.c)
_QE = [0x5601, 0x3401, 0x1801, 0x0AC1, 0x0521, 0x0221, 0x5601, 0x5401, 0x4801, 0x3801, 0x3001, 0x2401, 0x1C01,
       0x1601, 0x5601, 0x5401, 0x5101, 0x4801, 0x3801, 0x3401, 0x3001, 0x2801, 0x2401, 0x2201, 0x1C01, 0x1801,
       0x1601, 0x1401, 0x1201, 0x1101, 0x0AC1, 0x09C1, 0x08A1, 0x0521, 0x0441, 0x02A1, 0x0221, 0x0141, 0x0111,
       0x0085, 0x0049, 0x0025, 0x0015, 0x0009, 0x0005, 0x0001, 0x5601]
_NMPS = [1, 2, 3, 4, 5, 38, 7, 8, 9, 10, 11, 12, 13, 29, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28,
         29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 45, 46]
_NLPS = [1, 6, 9, 12, 29, 33, 6, 14, 14, 14, 17, 18, 20, 21, 14, 14, 15, 16, 17, 18, 19, 19, 20, 21, 22, 23, 24,
         25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 46]
_SW = [1, 0, 0, 0, 0, 0, 1] + [0] * 7 + [1] + [0] * 32


def _encoder_python(img, w, h, pas):
    import struct
    sortie = bytearray()
    st = {"a": 0x8000, "c": 0, "ct": 12, "b": -1}
    I = bytearray(65536)
    M = bytearray(65536)

    def sortir(o):
        if st["b"] >= 0:
            sortie.append(st["b"] & 0xFF)
        st["b"] = o

    def byteout():
        if st["b"] == 0xFF:
            sortir(st["c"] >> 20)
            st["c"] &= 0xFFFFF
            st["ct"] = 7
        elif st["c"] < 0x8000000:
            sortir(st["c"] >> 19)
            st["c"] &= 0x7FFFF
            st["ct"] = 8
        else:
            if st["b"] >= 0:
                st["b"] += 1
            if st["b"] == 0xFF:
                st["c"] &= 0x7FFFFFF
                sortir(st["c"] >> 20)
                st["c"] &= 0xFFFFF
                st["ct"] = 7
            else:
                sortir(st["c"] >> 19)
                st["c"] &= 0x7FFFF
                st["ct"] = 8

    def coder(cx, d):
        i = I[cx]
        qe = _QE[i]
        st["a"] -= qe
        if d == M[cx]:
            if st["a"] & 0x8000:
                st["c"] += qe
                return
            if st["a"] < qe:
                st["a"] = qe
            else:
                st["c"] += qe
            I[cx] = _NMPS[i]
        else:
            if st["a"] < qe:
                st["c"] += qe
            else:
                st["a"] = qe
            if _SW[i]:
                M[cx] = 1 - M[cx]
            I[cx] = _NLPS[i]
        while True:
            st["a"] <<= 1
            st["c"] <<= 1
            st["ct"] -= 1
            if st["ct"] == 0:
                byteout()
            if st["a"] & 0x8000:
                break

    lignes = [img[y * pas:(y + 1) * pas] for y in range(h)]
    vide = bytes(pas)

    def pix(l, x):
        if l is None or x < 0 or x >= w:
            return 0
        return (l[x >> 3] >> (7 - (x & 7))) & 1
    ltp = 0
    for y in range(h):
        l0 = lignes[y]
        pareil = l0 == (lignes[y - 1] if y else vide)
        coder(0x9B25, ltp ^ pareil)
        ltp = int(pareil)
        if pareil:
            continue
        l1 = lignes[y - 1] if y >= 1 else None
        l2 = lignes[y - 2] if y >= 2 else None
        for x in range(w):
            cx = (pix(l0, x - 1) | pix(l0, x - 2) << 1 | pix(l0, x - 3) << 2 | pix(l0, x - 4) << 3 |
                  pix(l1, x + 3) << 4 | pix(l1, x + 2) << 5 | pix(l1, x + 1) << 6 | pix(l1, x) << 7 |
                  pix(l1, x - 1) << 8 | pix(l1, x - 2) << 9 | pix(l1, x - 3) << 10 | pix(l2, x + 2) << 11 |
                  pix(l2, x + 1) << 12 | pix(l2, x) << 13 | pix(l2, x - 1) << 14 | pix(l2, x - 2) << 15)
            coder(cx, pix(l0, x))
    t = st["c"] + st["a"]
    st["c"] |= 0xFFFF
    if st["c"] >= t:
        st["c"] -= 0x8000
    st["c"] <<= st["ct"]
    byteout()
    st["c"] <<= st["ct"]
    byteout()
    sortir(-1)
    if not sortie or sortie[-1] != 0xFF:
        sortie.append(0xFF)
    sortie.append(0xAC)
    page = struct.pack(">IBBBI", 0, 48, 0, 1, 19) + struct.pack(">IIIIBH", w, h, 0, 0, 1, 0)
    region = struct.pack(">IIIIB", w, h, 0, 0, 0) + bytes([0x08, 3, 0xFF, 0xFD, 0xFF, 2, 0xFE, 0xFE, 0xFE])
    gen = struct.pack(">IBBBI", 1, 38, 0, 1, len(region) + len(sortie)) + region
    return page + gen + bytes(sortie)


# ------------------------------------------------------------------ dans un PDF
def _bitmap_noir(doc, x):
    """(bits 1 = noir, largeur, hauteur) d'une image 1 bit du PDF, ou None si elle ne s'y prete pas."""
    try:
        if doc.xref_get_key(x, "Subtype")[1] != "/Image":
            return None
        bpc = doc.xref_get_key(x, "BitsPerComponent")[1]
        masque = doc.xref_get_key(x, "ImageMask")[1] == "true"
        if not masque and bpc != "1":
            return None
        cs = doc.xref_get_key(x, "ColorSpace")
        if not masque and cs[1] not in ("/DeviceGray", "/CalGray") and not cs[1].startswith("[/Indexed"):
            if cs[0] != "null":
                return None
        filtre = doc.xref_get_key(x, "Filter")[1]
        if "JBIG2" in filtre or "DCT" in filtre or "JPX" in filtre:
            return None
        w = int(doc.xref_get_key(x, "Width")[1])
        h = int(doc.xref_get_key(x, "Height")[1])
        brut = doc.xref_stream(x)
    except Exception:
        return None
    pas = (w + 7) // 8
    if not brut or len(brut) < pas * h:
        return None
    # dans le PDF : 0 = noir (gris) ou 0 = peint (masque) ; JBIG2 : 1 = noir, le filtre inverse au decodage
    inv = bytes(255 - b for b in brut[:pas * h]) if not hasattr(brut, "translate") else \
        brut[:pas * h].translate(bytes(range(255, -1, -1)))
    return inv, w, h


def recompresser(doc, journal=None, mini=2000):
    """Images noir et blanc du document recodees en JBIG2 sans perte, quand c'est plus leger.
    Renvoie (nombre d'images, octets gagnes)."""
    n, gain = 0, 0
    lent = not rapide()
    for x in range(1, doc.xref_length()):
        b = _bitmap_noir(doc, x)
        if b is None:
            continue
        bits, w, h = b
        if lent and w * h > 600000:                     # sans le module C : seulement les petites images
            continue
        avant = len(doc.xref_stream_raw(x))
        if avant < mini:
            continue
        try:
            j = encoder(bits, w, h)
        except Exception:
            continue
        if len(j) >= avant * 0.97:
            continue
        doc.update_stream(x, j, compress=False)
        doc.xref_set_key(x, "Filter", "/JBIG2Decode")
        doc.xref_set_key(x, "DecodeParms", "null")
        n += 1
        gain += avant - len(j)
    if journal is not None and n:
        journal.append(f"JBIG2 : {n} image(s) noir et blanc, {gain // 1024} Ko gagnés")
    return n, gain


def en_noir_et_blanc(doc, dpi_mini=150, journal=None):
    """Scans en gris ou en couleur qui ne sont que du texte (noir sur fond clair) : passes en noir et blanc
    (seuil d'Otsu), pour etre ensuite codes en JBIG2. Avec perte : les gris disparaissent. Renvoie le nombre."""
    import numpy as np
    n = 0
    vus = set()
    for page in doc:
        for im in page.get_images(full=True):
            x = im[0]
            if x in vus or im[1]:                        # deja vu, ou avec masque de transparence
                continue
            vus.add(x)
            try:
                pix = fitz.Pixmap(doc, x)
            except Exception:
                continue
            if pix.n - pix.alpha not in (1, 3) or pix.width * pix.height < 200000:
                continue
            try:
                r = page.get_image_rects(x)
                dpi = pix.width / (r[0].width / 72) if r and r[0].width else 0
            except Exception:
                dpi = 0
            if dpi and dpi < dpi_mini:
                continue
            if pix.n - pix.alpha == 3:
                pix = fitz.Pixmap(fitz.csGRAY, pix)
            a = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.stride)[:, :pix.width]
            hist = np.bincount(a.ravel(), minlength=256).astype(float)
            total = hist.sum()
            clair = hist[200:].sum() / total
            fonce = hist[:90].sum() / total
            if clair < 0.6 or clair + fonce < 0.88:      # pas un document noir sur blanc (photo, fond colore)
                continue
            # seuil d'Otsu
            p = hist / total
            w0 = np.cumsum(p)
            mu = np.cumsum(p * np.arange(256))
            mt = mu[-1]
            with np.errstate(divide="ignore", invalid="ignore"):
                sb = (mt * w0 - mu) ** 2 / (w0 * (1 - w0))
            s = int(np.nanargmax(sb))
            noir = a <= s
            bits = np.packbits(noir, axis=1)
            w, h = pix.width, pix.height
            j = encoder(bits.tobytes(), w, h, bits.shape[1])
            doc.update_stream(x, j, compress=False)
            for k, v in (("Filter", "/JBIG2Decode"), ("DecodeParms", "null"), ("ColorSpace", "/DeviceGray"),
                         ("BitsPerComponent", "1"), ("Decode", "null"), ("SMask", "null")):
                doc.xref_set_key(x, k, v)
            n += 1
    if journal is not None and n:
        journal.append(f"{n} scan(s) passé(s) en noir et blanc")
    return n
