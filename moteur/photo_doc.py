"""Photo d'un document -> page propre (comme la numerisation par photo de PhilPDF Android) : bords de la feuille
reperes, perspective corrigee, puis amelioration selon le modele (noir et blanc, couleur, pour e-mail, photo).
Tout se fait sur le poste (OpenCV), rien n'est envoye."""
import cv2
import numpy as np
import pymupdf as fitz

MODELES = {               # grand cote (pixels), qualite JPEG (0 = PNG noir et blanc)
    "nb": (2200, 0),
    "couleur": (2200, 82),
    "email": (1400, 60),
    "photo": (2400, 88),
}


def lire(chemin):
    """Image couleur (BGR) d'un fichier, tournee selon l'appareil photo (EXIF)."""
    data = np.fromfile(chemin, dtype=np.uint8)          # chemins avec accents (Windows)
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("image illisible")
    try:
        from PIL import Image
        o = Image.open(chemin).getexif().get(0x0112, 1)
        img = {3: cv2.rotate(img, cv2.ROTATE_180), 6: cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE),
               8: cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)}.get(o, img)
    except Exception:                                   # noqa: BLE001
        pass
    return img


def _ordonner(p):
    """Haut-gauche, haut-droite, bas-droite, bas-gauche."""
    p = np.array(p, dtype=np.float32).reshape(4, 2)
    s, d = p.sum(1), p[:, 0] - p[:, 1]
    return np.array([p[np.argmin(s)], p[np.argmax(d)], p[np.argmax(s)], p[np.argmin(d)]], dtype=np.float32)


def coins(img):
    """Quatre coins de la feuille (pixels de la photo) ; toute la photo si rien de net n'est trouve."""
    h, w = img.shape[:2]
    tout = np.array([[0, 0], [w, 0], [w, h], [0, h]], dtype=np.float32)
    k = max(1.0, max(w, h) / 800.0)
    petit = cv2.resize(img, (int(w / k), int(h / k)), interpolation=cv2.INTER_AREA)
    g = cv2.GaussianBlur(cv2.cvtColor(petit, cv2.COLOR_BGR2GRAY), (5, 5), 0)
    aire = petit.shape[0] * petit.shape[1]
    candidats = []
    # 1) contours (bords nets) ; 2) zone claire (seuil d'Otsu), utile sur fond uni
    bords = cv2.dilate(cv2.Canny(g, 40, 120), np.ones((3, 3), np.uint8), iterations=2)
    _t, clair = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    clair = cv2.morphologyEx(clair, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    for m in (bords, clair):
        cs, _h = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in sorted(cs, key=cv2.contourArea, reverse=True)[:5]:
            a = cv2.contourArea(c)
            if a < 0.15 * aire or a > 0.98 * aire:
                continue
            per = cv2.arcLength(c, True)
            for eps in (0.02, 0.03, 0.05):
                ap = cv2.approxPolyDP(c, eps * per, True)
                if len(ap) == 4 and cv2.isContourConvex(ap):
                    candidats.append((a, ap.reshape(4, 2)))
                    break
            else:
                # pas un quadrilatere net : les points extremes de la zone
                p = c.reshape(-1, 2)
                candidats.append((a * 0.9, _ordonner([p[np.argmin(p.sum(1))], p[np.argmax(p[:, 0] - p[:, 1])],
                                                       p[np.argmax(p.sum(1))], p[np.argmin(p[:, 0] - p[:, 1])]])))
    if not candidats:
        return tout
    best = max(candidats, key=lambda t: t[0])[1]
    return _ordonner(best) * k


def redresser(img, c, max_cote=2600):
    c = _ordonner(c)
    lw = (np.linalg.norm(c[1] - c[0]) + np.linalg.norm(c[2] - c[3])) / 2
    lh = (np.linalg.norm(c[3] - c[0]) + np.linalg.norm(c[2] - c[1])) / 2
    e = min(1.0, max_cote / max(lw, lh, 1))
    lw, lh = max(1, int(round(lw * e))), max(1, int(round(lh * e)))
    m = cv2.getPerspectiveTransform(c, np.array([[0, 0], [lw, 0], [lw, lh], [0, lh]], dtype=np.float32))
    return cv2.warpPerspective(img, m, (lw, lh), flags=cv2.INTER_CUBIC, borderValue=(255, 255, 255))


def _reduire(img, cote):
    h, w = img.shape[:2]
    if max(w, h) <= cote:
        return img
    e = cote / max(w, h)
    return cv2.resize(img, (max(1, int(w * e)), max(1, int(h * e))), interpolation=cv2.INTER_AREA)


def ameliorer(img, modele):
    """Fond eclairci (ombres et lumiere inegale retirees) ; noir et blanc net ; ou rien (photo)."""
    cote, _q = MODELES[modele]
    img = _reduire(img, cote)
    if modele == "photo":
        return img
    # fond : le plus clair du voisinage (le texte disparait), lisse
    k = max(15, (max(img.shape[:2]) // 40) | 1)
    fond = cv2.GaussianBlur(cv2.dilate(img, np.ones((k, k), np.uint8)), (k | 1, k | 1), 0)
    n = np.clip(img.astype(np.float32) * 255.0 / np.maximum(fond.astype(np.float32), 40), 0, 255)
    t = np.clip((n - 40) / (235 - 40), 0, 1)
    out = (255 * t * t * (3 - 2 * t)).astype(np.uint8)
    if modele == "nb":
        g = cv2.cvtColor(out, cv2.COLOR_BGR2GRAY)
        return np.where(g < 165, 0, 255).astype(np.uint8)
    return out


def octets(img, modele):
    """PNG pour le noir et blanc, JPEG sinon."""
    _c, q = MODELES[modele]
    ok, buf = cv2.imencode(".png", img) if q == 0 else cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, q])
    if not ok:
        raise ValueError("encodage impossible")
    return buf.tobytes()


def pdf(pages):
    """PDF d'une page par image, largeur A4 (595 points), hauteur selon l'image."""
    d = fitz.open()
    for o in pages:
        im = fitz.open(stream=o)
        r = im[0].rect
        p = d.new_page(width=595, height=595 * r.height / max(r.width, 1))
        p.insert_image(p.rect, stream=o)
    return d
