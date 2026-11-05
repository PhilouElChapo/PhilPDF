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


def noir_blanc(gris, contraste=18):
    """Fond eclairci (ombres, jaunissement) puis noir et blanc net (255 blanc, 0 noir)."""
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
    effacer = (touche & (trait | dans_bande)) | (dans_bande & trait) | (pres & trait & (a < 0.25 * bw * bh))
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
