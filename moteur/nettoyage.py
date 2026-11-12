"""Nettoyage d'une page scannee : redresser, effacer les bords noirs (bord de la vitre, ombre de la feuille, traits
de la photocopie), retirer les taches et le grain isoles, noir et blanc net. Tout se fait sur le poste.

Les reglages sont ceux de la fenetre « Nettoyer un scan » ; par defaut (REGLAGES), c'est ce qui est applique a la
numerisation et a la reconnaissance du texte. Une tache n'est retiree que si elle est ISOLEE : le point d'un i, un
accent ou une ponctuation, proches des lettres, sont gardes."""
import cv2
import numpy as np

REGLAGES = {"redresser": "auto",      # "auto", "non", ou un angle en degres (choisi a la main)
            "taches": 1,              # 0 aucune, 1 petites taches isolees, 2 aussi les taches moyennes (fort)
            "bords": True,            # bords noirs et traits colles au bord de la page
            "contraste": 18}          # seuil du noir et blanc : plus haut = plus clair (moins de grain)


def _encre(gris, seuil=None):
    """Masque de l'encre (1 = noir)."""
    if seuil is None:
        _t, nb = cv2.threshold(gris, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        return (nb == 0).astype(np.uint8)
    return (gris < seuil).astype(np.uint8)


def angle(gris):
    """Angle (degres) qui met les lignes de texte a l'horizontale. Les bords de la page sont laisses de cote (le
    bord de la vitre ou de la feuille, souvent penche autrement que le texte, faussait la mesure)."""
    h, w = gris.shape[:2]
    k = 1200 / max(h, w)
    petit = cv2.resize(gris, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
    enc = _encre(petit, 170)
    hh, ww = enc.shape
    enc = enc[int(hh * 0.06):int(hh * 0.94), int(ww * 0.06):int(ww * 0.94)]
    if enc.sum() < 50:
        return 0.0

    def score(a):
        M = cv2.getRotationMatrix2D((enc.shape[1] / 2, enc.shape[0] / 2), a, 1)
        r = cv2.warpAffine(enc, M, (enc.shape[1], enc.shape[0]), flags=cv2.INTER_NEAREST)
        return float(np.var(r.sum(axis=1).astype(float)))
    zero = score(0)
    best = max(np.arange(-6, 6.01, 0.25), key=score)
    best = max(np.arange(best - 0.25, best + 0.26, 0.05), key=score)
    # gain trop faible (page presque vide, dessin) : on ne tourne pas
    return float(best) if score(best) > zero * 1.04 else 0.0


def tourner(img, a, fond=255):
    h, w = img.shape[:2]
    M = cv2.getRotationMatrix2D((w / 2, h / 2), a, 1)
    bv = fond if img.ndim == 2 else (fond, fond, fond)
    return cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_CUBIC, borderValue=bv)


def tramee(gris):
    """Vrai si l'image est deja en noir et blanc TRAME (points alternes) : pilote de scanner en « noir et blanc »
    avec diffusion d'erreur, papier securise (ordonnance), photocopie d'un fond gris. Les gris y sont faits de
    points noirs et blancs melanges : un seuil ne les retire pas, il faut d'abord les lisser."""
    h, w = gris.shape[:2]
    c = gris[h // 4:3 * h // 4, w // 4:3 * w // 4]
    if c.size < 10000 or float(((c > 20) & (c < 235)).mean()) > 0.02:
        return False                        # vrais gris : image en niveaux de gris, pas tramee
    b = (c < 128).astype(np.int8)
    alternance = (np.abs(np.diff(b, axis=1)).mean() + np.abs(np.diff(b, axis=0)).mean()) / 2
    return float(alternance) > 0.15         # texte net en noir et blanc : bien moins de 0.1


def detramer(gris, contraste=18):
    """Noir et blanc net d'une image tramee : les points sont lisses en gris, puis le seuil passe entre l'encre
    (le plus sombre) et le fond (le plus courant, motif du papier compris), qui part au blanc."""
    flou = cv2.GaussianBlur(gris, (0, 0), 1.6 * max(gris.shape) / 3508)
    noir = min(float(np.percentile(flou, 1)), 80.0)        # encre (peu de texte : le 1 % serait le motif)
    # fond du voisinage (le motif du papier est plus fonce par endroits) : mediane sur une image reduite
    k = 0.1
    petit = cv2.resize(flou, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
    fond = cv2.resize(cv2.medianBlur(petit, 15), (flou.shape[1], flou.shape[0]), interpolation=cv2.INTER_LINEAR)
    fond = np.maximum(fond.astype(np.float32), float(np.percentile(flou, 50)) * 0.85)
    # contraste 18 (reglage par defaut) : seuil a 45 % entre l'encre et le fond ; plus haut = plus clair
    seuil = noir + (fond - noir) * (0.45 - (contraste - 18) / 200)
    return np.where(flou < seuil, 0, 255).astype(np.uint8)


def noir_blanc(gris, contraste=18):
    """Fond eclairci (ombres, jaunissement) puis noir et blanc net (255 blanc, 0 noir). Une image deja tramee
    (points noirs et blancs) est d'abord lissee : sinon son fond gris pointille resterait tel quel."""
    if tramee(gris):
        return detramer(gris, contraste)
    fond = cv2.medianBlur(cv2.dilate(gris, np.ones((7, 7), np.uint8)), 31)
    norm = cv2.divide(gris, fond, scale=255)
    return cv2.adaptiveThreshold(norm, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 41, int(contraste))


def bords(nb):
    """Efface ce qui touche le bord de l'image et ressemble a un bord (trait le long du bord, bande noire, coin
    d'ombre), et les traits fins collés au bord. Le texte proche du bord, qui ne le touche pas, est garde.
    Renvoie (image, nombre d'elements effaces)."""
    h, w = nb.shape
    enc = (nb < 128).astype(np.uint8)
    n, lab, st, _c = cv2.connectedComponentsWithStats(enc, 8)
    if n <= 1:
        return nb, 0
    x, y, bw, bh, a = (st[1:, i] for i in range(5))
    m = max(2, int(0.004 * max(h, w)))
    touche = (x <= m) | (y <= m) | (x + bw >= w - m) | (y + bh >= h - m)
    bande_x, bande_y = 0.045 * w, 0.035 * h
    dans_bande = (x + bw <= bande_x) | (x >= w - bande_x) | (y + bh <= bande_y) | (y >= h - bande_y)
    trait = ((bh > 0.08 * h) & (bw < 0.03 * w)) | ((bw > 0.08 * w) & (bh < 0.03 * h))
    pres = (x <= 2 * bande_x) | (x + bw >= w - 2 * bande_x) | (y <= 2 * bande_y) | (y + bh >= h - 2 * bande_y)
    # bande noire le long d'un bord (table, ombre autour de la feuille photographiee) : haute et etroite, ou l'inverse
    bande_bord = touche & (((bh > 0.5 * h) & (bw < 0.2 * w)) | ((bw > 0.5 * w) & (bh < 0.2 * h)))
    effacer = (touche & (trait | dans_bande)) | (dans_bande & trait) | (pres & trait & (a < 0.25 * bw * bh)) | bande_bord
    ids = np.where(effacer)[0] + 1
    if not len(ids):
        return nb, 0
    out = nb.copy()
    out[np.isin(lab, ids)] = 255
    return out, int(len(ids))


def taches(nb, dpi=300, force=1):
    """Retire les taches et le grain ISOLES (rien d'ecrit tout pres). Renvoie (image, nombre de taches retirees)."""
    if force <= 0:
        return nb, 0
    k = dpi / 300.0
    enc = (nb < 128).astype(np.uint8)
    n, lab, st, _c = cv2.connectedComponentsWithStats(enc, 8)
    if n <= 1:
        return nb, 0
    a = st[:, cv2.CC_STAT_AREA].copy()
    a[0] = 0
    petit = (20 if force == 1 else 45) * k * k
    moyen = 160 * k * k
    gros = a > (moyen if force >= 2 else petit)
    gros[0] = False
    masque_gros = gros[lab].astype(np.uint8)
    out = nb.copy()
    retires = 0
    # 1. petites taches : retirees si aucune lettre a moins de ~2 mm (le point du i, les accents restent)
    r = max(3, int(24 * k))
    voisin = cv2.dilate(masque_gros, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1)))
    candidats = (a > 0) & (a <= petit)
    proches = np.unique(lab[(voisin > 0) & candidats[lab]])
    ok = candidats.copy()
    ok[proches] = False
    ok[0] = False
    retires += int(ok.sum())
    out[ok[lab]] = 255
    # 2. fort : taches moyennes, petites et compactes, loin de tout (~4 mm)
    if force >= 2:
        bw, bh = st[:, cv2.CC_STAT_WIDTH], st[:, cv2.CC_STAT_HEIGHT]
        cand = (a > petit) & (a <= moyen) & (bw <= 30 * k) & (bh <= 30 * k)
        autres = ((a > 0) & ~cand & ~ok)
        autres[0] = False
        r2 = max(5, int(48 * k))
        v2 = cv2.dilate(autres[lab].astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r2 + 1, 2 * r2 + 1)))
        pres2 = np.unique(lab[(v2 > 0) & cand[lab]])
        ok2 = cand.copy()
        ok2[pres2] = False
        ok2[0] = False
        retires += int(ok2.sum())
        out[ok2[lab]] = 255
    return out, retires


def page(gris, dpi=300, reglages=None):
    """Page en gris -> (noir et blanc nettoye, angle applique, details). details : taches, bords retires."""
    r = dict(REGLAGES, **(reglages or {}))
    a = 0.0
    if r["redresser"] == "auto":
        a = angle(gris)
    elif r["redresser"] not in ("non", None, ""):
        a = float(r["redresser"])
    droit = tourner(gris, a) if abs(a) > 0.05 else gris
    nb = noir_blanc(droit, r["contraste"])
    nbords = 0
    if r["bords"]:
        nb, nbords = bords(nb)
    nb, ntaches = taches(nb, dpi, r["taches"])
    return nb, a, {"taches": ntaches, "bords": nbords}


def matrice(a, v, w, h):
    """Correction (3x3, repere image : y vers le bas) : rotation de a degres (sens inverse des aiguilles d'une
    montre, comme angle()) puis inclinaison des verticales de v degres (les lignes horizontales restent horizontales),
    autour du centre de l'image (w x h)."""
    import math
    R = np.vstack([cv2.getRotationMatrix2D((w / 2, h / 2), a, 1), [0, 0, 1]])
    k = math.tan(math.radians(v))
    S = np.array([[1, k, -k * h / 2], [0, 1, 0], [0, 0, 1]], dtype=float)
    return S @ R


def transformer(img, a, v, fond=255):
    """Image redressee : rotation a et inclinaison verticale v (degres), meme taille, coins blancs."""
    h, w = img.shape[:2]
    bv = fond if img.ndim == 2 else (fond, fond, fond)
    return cv2.warpAffine(img, matrice(a, v, w, h)[:2], (w, h), flags=cv2.INTER_CUBIC, borderValue=bv)


def angle_vertical(gris, a=0.0):
    """Inclinaison des verticales (degres) apres la rotation a : bords de la feuille, colonnes, tableaux, marge."""
    import math
    h, w = gris.shape[:2]
    k = 1200 / max(h, w)
    petit = cv2.resize(gris, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
    if abs(a) > 0.01:
        petit = tourner(petit, a)
    enc = _encre(petit, 170)
    hh, ww = enc.shape
    enc = enc[int(hh * 0.04):int(hh * 0.96), int(ww * 0.04):int(ww * 0.96)]
    if enc.sum() < 50:
        return 0.0

    def score(v):
        t = math.tan(math.radians(v))
        M = np.array([[1, t, -t * enc.shape[0] / 2], [0, 1, 0]], dtype=np.float32)
        r = cv2.warpAffine(enc, M, (enc.shape[1], enc.shape[0]), flags=cv2.INTER_NEAREST)
        return float(np.var(r.sum(axis=0).astype(float)))
    zero = score(0)
    best = max(np.arange(-6, 6.01, 0.25), key=score)
    best = max(np.arange(best - 0.25, best + 0.26, 0.05), key=score)
    return float(best) if score(best) > zero * 1.04 else 0.0


def redresser_pages(doc, pages, angle, vertical=0.0):
    """Redresse le contenu des pages autour de leur centre : rotation de angle degres (sens inverse des aiguilles
    d'une montre, comme angle()) et inclinaison des verticales de vertical degres (comme angle_vertical()).
    Texte, couleurs et qualite gardes, le texte reconnu suit."""
    if abs(angle) < 0.01 and abs(vertical) < 0.01:
        return 0
    n = 0
    for i in pages:
        p = doc[i]
        mb = p.mediabox
        w, h = mb.width, mb.height
        A = matrice(angle, vertical, w, h)
        # repere PDF (y vers le haut) <-> repere image en points (y vers le bas, origine en haut a gauche)
        F = np.array([[1, 0, -mb.x0], [0, -1, mb.y1], [0, 0, 1]], dtype=float)
        T = np.linalg.inv(F) @ A @ F
        anciens = p.get_contents()
        avant, apres = doc.get_new_xref(), doc.get_new_xref()
        cm = f"q {T[0, 0]:.6f} {T[1, 0]:.6f} {T[0, 1]:.6f} {T[1, 1]:.6f} {T[0, 2]:.4f} {T[1, 2]:.4f} cm\n"
        for x, flux in ((avant, cm.encode()), (apres, b"\nQ\n")):
            doc.update_object(x, "<<>>")
            doc.update_stream(x, flux)
        doc.xref_set_key(p.xref, "Contents", "[" + " ".join(f"{x} 0 R" for x in [avant] + anciens + [apres]) + "]")
        n += 1
    return n
