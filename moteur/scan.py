"""PhilPDF - preuve de concept : redresser, nettoyer et reconnaitre un scan."""
import os, subprocess, tempfile
import numpy as np, cv2
import pymupdf as fitz
from PIL import Image

import sys, shutil
_BASE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TESS = os.environ.get("PHILPDF_TESSDATA") or (os.path.join(_BASE, "tessdata") if os.path.isdir(os.path.join(_BASE, "tessdata")) else os.path.join(_BASE, "tessdata"))


def tesseract_exe():
    """Chemin de Tesseract (installe a part sous Windows), ou None."""
    for p in (shutil.which("tesseract"), os.path.join(_BASE, "tesseract", "tesseract.exe"),
              r"C:\Program Files\Tesseract-OCR\tesseract.exe"):
        if p and os.path.exists(p):
            return p
    return None


def angle_inclinaison(gris):
    """Angle (degres) qui rend les lignes de texte les plus horizontales.
    Methode : profil de projection, recherche grossiere puis fine."""
    h, w = gris.shape
    k = 1000 / max(h, w)
    petit = cv2.resize(gris, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
    enc = (petit < 160).astype(np.uint8) * 255
    def score(a):
        M = cv2.getRotationMatrix2D((enc.shape[1] / 2, enc.shape[0] / 2), a, 1)
        r = cv2.warpAffine(enc, M, (enc.shape[1], enc.shape[0]))
        p = r.sum(axis=1).astype(float)
        return np.var(p)
    best = max(np.arange(-5, 5.01, 0.5), key=score)
    best = max(np.arange(best - 0.5, best + 0.51, 0.05), key=score)
    return float(best)


def redresser(gris, angle):
    h, w = gris.shape
    M = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1)
    return cv2.warpAffine(gris, M, (w, h), flags=cv2.INTER_CUBIC, borderValue=255)


def nettoyer(gris):
    # fond : division par un flou large (efface jaunissement, ombres)
    fond = cv2.medianBlur(cv2.dilate(gris, np.ones((7, 7), np.uint8)), 31)
    norm = cv2.divide(gris, fond, scale=255)
    nb = cv2.adaptiveThreshold(norm, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 41, 18)
    n, lab, st, _ = cv2.connectedComponentsWithStats(255 - nb, 8)
    petits = np.where(st[:, cv2.CC_STAT_AREA] < 5)[0]
    nb[np.isin(lab, petits[petits > 0])] = 255
    return nb


def traiter(entree, sortie, dpi_source=None):
    d = fitz.open(entree)
    rapport, pages_pdf = [], []
    tmp = tempfile.mkdtemp()
    for i, p in enumerate(d):
        x = p.get_images()[0][0]
        info = d.extract_image(x)
        gris = cv2.imdecode(np.frombuffer(info["image"], np.uint8), cv2.IMREAD_GRAYSCALE)
        dpi = round(gris.shape[1] / (p.rect.width / 72))
        a = angle_inclinaison(gris)
        nb = nettoyer(redresser(gris, a) if abs(a) > 0.05 else gris)
        tif = os.path.join(tmp, f"p{i:03d}.tif")
        Image.fromarray(nb).convert("1").save(tif, compression="group4", dpi=(dpi, dpi))
        base = os.path.join(tmp, f"p{i:03d}")
        subprocess.run([tesseract_exe() or "tesseract", tif, base, "-l", "fra", "--dpi", str(dpi), "pdf"],
                       env={**os.environ, "TESSDATA_PREFIX": TESS},
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True,
                       creationflags=0x08000000 if sys.platform == "win32" else 0)
        pages_pdf.append(base + ".pdf")
        rapport.append((i + 1, a, dpi))
    out = fitz.open()
    for f in pages_pdf:
        out.insert_pdf(fitz.open(f))
    # format A4 exact, comme l'original
    for pg, src in zip(out, d):
        pg.set_mediabox(pg.mediabox)  # tesseract produit deja la taille physique
    out.set_metadata({"producer": "PhilPDF (preuve de concept)", "title": os.path.basename(entree)})
    out.save(sortie, garbage=3, deflate=True)
    return rapport
