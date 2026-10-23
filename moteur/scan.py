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


def image_de_page(d, p, dpi_defaut=300):
    """(image en gris, dpi) d'une page : l'image scannee d'origine si la page n'est qu'un scan droit,
    sinon un rendu de la page (pages sans image, plusieurs images, page tournee ou recadree)."""
    imgs = p.get_images(full=True)
    if len(imgs) == 1 and p.rotation == 0:
        try:
            r = p.get_image_rects(imgs[0][0])
            if r and r[0].width >= p.rect.width * 0.9 and r[0].height >= p.rect.height * 0.9:
                info = d.extract_image(imgs[0][0])
                gris = cv2.imdecode(np.frombuffer(info["image"], np.uint8), cv2.IMREAD_GRAYSCALE)
                if gris is not None and gris.shape[1] > 300:
                    return gris, max(72, round(gris.shape[1] / (p.rect.width / 72)))
        except Exception:
            pass
    pm = p.get_pixmap(dpi=dpi_defaut, colorspace=fitz.csGRAY, alpha=False)
    gris = np.frombuffer(pm.samples, np.uint8).reshape(pm.height, pm.width).copy()
    return gris, dpi_defaut


def a_du_texte(p):
    return len(p.get_text("text").strip()) > 30


def traiter(entree, sortie, dpi_source=None, progression=None):
    """Reconnait le texte des pages scannees ; les pages qui ont deja du texte restent telles quelles.
    Renvoie [(page, angle, dpi ou None si gardee)]."""
    d = fitz.open(entree)
    if d.needs_pass:
        raise ValueError("document protégé par mot de passe")
    rapport, morceaux = [], []
    tmp = tempfile.mkdtemp()
    for i, p in enumerate(d):
        if progression:
            progression(i, len(d))
        if a_du_texte(p):
            morceaux.append(("garder", i))
            rapport.append((i + 1, 0.0, None))
            continue
        gris, dpi = image_de_page(d, p)
        a = angle_inclinaison(gris)
        nb = nettoyer(redresser(gris, a) if abs(a) > 0.05 else gris)
        tif = os.path.join(tmp, f"p{i:03d}.tif")
        Image.fromarray(nb).convert("1").save(tif, compression="group4", dpi=(dpi, dpi))
        base = os.path.join(tmp, f"p{i:03d}")
        r = subprocess.run([tesseract_exe() or "tesseract", tif, base, "-l", "fra", "--dpi", str(dpi), "pdf"],
                           env={**os.environ, "TESSDATA_PREFIX": TESS}, stdout=subprocess.DEVNULL,
                           stderr=subprocess.PIPE, creationflags=0x08000000 if sys.platform == "win32" else 0)
        if r.returncode != 0 or not os.path.exists(base + ".pdf"):
            raise RuntimeError(f"Tesseract, page {i + 1} : " + r.stderr.decode("utf-8", "replace")[-300:])
        morceaux.append(("ocr", base + ".pdf"))
        rapport.append((i + 1, a, dpi))
    out = fitz.open()
    for genre, x in morceaux:
        if genre == "garder":
            out.insert_pdf(d, from_page=x, to_page=x)
        else:
            out.insert_pdf(fitz.open(x))
    out.set_metadata({"producer": "PhilPDF", "title": os.path.basename(entree)})
    out.save(sortie, garbage=3, deflate=True)
    return rapport
