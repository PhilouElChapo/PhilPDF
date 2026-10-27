"""Retouche d'une image d'un PDF : niveaux, lumiere, couleurs, nettete, bruit, correction automatique,
baguette magique (selection par couleur) et effacement (rempli avec le fond ou rendu transparent).

Les images sont des tableaux numpy RGBA (uint8). Tout se fait sur le poste, rien n'est envoye.
"""
import io

import numpy as np
import pymupdf as fitz

REGLAGES = {"auto": False, "luminosite": 0, "contraste": 0, "noir": 0, "blanc": 255, "gamma": 100,
            "saturation": 0, "temperature": 0, "teinte": 0, "nettete": 0, "bruit": 0, "noir_blanc": False}


def depuis_pdf(doc, xref):
    """Image du PDF -> RGBA (masque de transparence compris)."""
    pix = fitz.Pixmap(doc, xref)
    info = doc.extract_image(xref)
    if pix.n - pix.alpha >= 4 or (pix.colorspace and pix.colorspace.n not in (1, 3)):
        pix = fitz.Pixmap(fitz.csRGB, pix)
    if pix.alpha:
        pix = fitz.Pixmap(pix, 0)
    if pix.n == 1:
        pix = fitz.Pixmap(fitz.csRGB, pix)
    rgb = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)[:, :, :3].copy()
    alpha = np.full(rgb.shape[:2], 255, np.uint8)
    if info.get("smask"):
        m = fitz.Pixmap(doc, info["smask"])
        a = np.frombuffer(m.samples, dtype=np.uint8).reshape(m.height, m.width, m.n)[:, :, 0]
        if a.shape == alpha.shape:
            alpha = a.copy()
        else:
            import cv2
            alpha = cv2.resize(a, (rgb.shape[1], rgb.shape[0]), interpolation=cv2.INTER_LINEAR)
    return np.dstack([rgb, alpha])


def vers_png(img):
    """RGBA -> octets PNG (transparence gardee seulement si elle sert)."""
    from PIL import Image
    if (img[:, :, 3] == 255).all():
        im = Image.fromarray(img[:, :, :3], "RGB")
    else:
        im = Image.fromarray(img, "RGBA")
    b = io.BytesIO()
    im.save(b, "PNG", optimize=True)
    return b.getvalue()


def vers_jpeg(img, qualite=90):
    from PIL import Image
    b = io.BytesIO()
    Image.fromarray(img[:, :, :3], "RGB").save(b, "JPEG", quality=qualite)
    return b.getvalue()


def reduire(img, cote=900):
    """Copie reduite (apercu rapide pendant que l'on bouge les curseurs)."""
    import cv2
    h, w = img.shape[:2]
    k = cote / max(h, w)
    if k >= 1:
        return img.copy()
    return cv2.resize(img, (int(w * k), int(h * k)), interpolation=cv2.INTER_AREA)


def _auto(rgb):
    """Correction automatique : niveaux etires (0,5 % de chaque cote) et balance des blancs (monde gris)."""
    out = rgb.astype(np.float32)
    for c in range(3):
        bas, haut = np.percentile(out[:, :, c], (0.5, 99.5))
        if haut - bas > 8:
            out[:, :, c] = (out[:, :, c] - bas) * 255.0 / (haut - bas)
    out = np.clip(out, 0, 255)
    moy = out.reshape(-1, 3).mean(axis=0)
    g = moy.mean()
    out = out * (g / np.maximum(moy, 1))[None, None, :] * 0.5 + out * 0.5
    return np.clip(out, 0, 255)


def appliquer(img, r):
    """Applique les reglages (voir REGLAGES) a une image RGBA ; renvoie une nouvelle image RGBA."""
    import cv2
    r = dict(REGLAGES, **(r or {}))
    rgb = img[:, :, :3].astype(np.float32)
    alpha = img[:, :, 3]
    if r["auto"]:
        rgb = _auto(rgb)
    if r["bruit"] > 0:                                   # reduction du bruit (avant la nettete)
        h = 3 + r["bruit"] / 100 * 15
        rgb = cv2.fastNlMeansDenoisingColored(np.clip(rgb, 0, 255).astype(np.uint8), None, h, h, 7, 21).astype(np.float32)
    # niveaux : point noir, point blanc, tons moyens (gamma)
    noir, blanc = float(r["noir"]), float(max(r["blanc"], r["noir"] + 1))
    rgb = np.clip((rgb - noir) / (blanc - noir), 0, 1)
    g = max(0.1, r["gamma"] / 100.0)
    rgb = np.power(rgb, 1.0 / g) * 255.0
    # lumiere et contraste
    if r["contraste"]:
        k = (100 + r["contraste"]) / 100.0
        rgb = (rgb - 128) * k + 128
    if r["luminosite"]:
        rgb = rgb + r["luminosite"] * 1.28
    # temperature : plus chaud = plus de rouge, moins de bleu
    if r["temperature"]:
        t = r["temperature"] * 0.6
        rgb[:, :, 0] += t
        rgb[:, :, 2] -= t
    rgb = np.clip(rgb, 0, 255)
    if r["saturation"] or r["teinte"]:
        hsv = cv2.cvtColor(rgb.astype(np.uint8), cv2.COLOR_RGB2HSV).astype(np.float32)
        if r["teinte"]:
            hsv[:, :, 0] = (hsv[:, :, 0] + r["teinte"] * 0.9) % 180
        if r["saturation"]:
            hsv[:, :, 1] = np.clip(hsv[:, :, 1] * (100 + r["saturation"]) / 100.0, 0, 255)
        rgb = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2RGB).astype(np.float32)
    if r["nettete"] > 0:                                 # masque flou : plus net
        flou = cv2.GaussianBlur(rgb, (0, 0), 1.2)
        rgb = np.clip(rgb + (rgb - flou) * (r["nettete"] / 40.0), 0, 255)
    elif r["nettete"] < 0:                               # flou
        s = -r["nettete"] / 100.0 * 8
        if s > 0.2:
            rgb = cv2.GaussianBlur(rgb, (0, 0), s)
    if r["noir_blanc"]:
        gris = cv2.cvtColor(rgb.astype(np.uint8), cv2.COLOR_RGB2GRAY)
        rgb = np.dstack([gris] * 3).astype(np.float32)
    return np.dstack([np.clip(rgb, 0, 255).astype(np.uint8), alpha])


def baguette(img, x, y, tolerance=32, masque=None):
    """Zone de couleur voisine du point (x, y) (pixels de l'image), comme la baguette magique. Ajoutee au masque
    existant s'il y en a un. Renvoie un masque booleen."""
    import cv2
    h, w = img.shape[:2]
    x, y = int(min(max(x, 0), w - 1)), int(min(max(y, 0), h - 1))
    rgb = np.ascontiguousarray(img[:, :, :3])
    m = np.zeros((h + 2, w + 2), np.uint8)
    t = (int(tolerance),) * 3
    cv2.floodFill(rgb.copy(), m, (x, y), (0, 0, 0), t, t, cv2.FLOODFILL_MASK_ONLY | cv2.FLOODFILL_FIXED_RANGE | (255 << 8) | 8)
    sel = m[1:-1, 1:-1] > 0
    return sel if masque is None else (masque | sel)


def effacer(img, masque, mode="fond"):
    """Efface la zone choisie : « fond » = remplie a partir de ce qui l'entoure, « transparent », « blanc »."""
    import cv2
    out = img.copy()
    if masque is None or not masque.any():
        return out
    if mode == "transparent":
        out[:, :, 3][masque] = 0
    elif mode == "blanc":
        out[:, :, :3][masque] = 255
    else:
        m = cv2.dilate(masque.astype(np.uint8) * 255, np.ones((3, 3), np.uint8), iterations=2)
        rayon = 5 if m.sum() / 255 < 4000 else 9
        out[:, :, :3] = cv2.inpaint(np.ascontiguousarray(img[:, :, :3]), m, rayon, cv2.INPAINT_TELEA)
    return out


def remplacer_dans_pdf(doc, num_page, xref, img):
    """Remet l'image retouchee a la meme place (meme taille, meme angle) dans le PDF."""
    page = doc[num_page]
    avant = next((fitz.Rect(i["bbox"]) for i in page.get_image_info(xrefs=True) if i.get("xref") == xref), None)
    png = vers_png(img)
    page.replace_image(xref, stream=png)
    infos = [i for i in doc[num_page].get_image_info(xrefs=True) if i.get("xref") and i.get("width", 0) > 1]
    if avant is not None and infos:                       # l'image a un nouveau numero : on le rend
        return min(infos, key=lambda i: abs(fitz.Rect(i["bbox"]).x0 - avant.x0) + abs(fitz.Rect(i["bbox"]).y0 - avant.y0))["xref"]
    return xref
