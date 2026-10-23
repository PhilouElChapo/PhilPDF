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


# ------------------------------------------------------------------ mots reconnus et apprentissage
def lire_tsv(chemin):
    """Mots reconnus par Tesseract : [{"texte", "x", "y", "l", "h", "conf", "ligne"}] (pixels de l'image)."""
    mots = []
    with open(chemin, encoding="utf-8", errors="replace") as f:
        next(f, None)
        for l in f:
            c = l.rstrip("\n").split("\t")
            if len(c) < 12 or c[0] != "5" or not c[11].strip():
                continue
            mots.append({"texte": c[11], "x": int(c[6]), "y": int(c[7]), "l": int(c[8]), "h": int(c[9]),
                         "conf": float(c[10]), "ligne": (c[2], c[3], c[4])})
    return mots


def appliquer_regles(mots, regles, seuil=2):
    """Corrections apprises : {"avant\u2192apres": {"n": k}} appliquees si validees au moins `seuil` fois.
    Renvoie [(indice, avant, apres)]."""
    table = {}
    for cle, v in (regles or {}).items():
        if "\u2192" in cle and v.get("n", 0) >= seuil:
            avant, apres = cle.split("\u2192", 1)
            if avant not in table or v["n"] > table[avant][1]:
                table[avant] = (apres, v["n"])
    faites = []
    for i, m in enumerate(mots):
        if m["texte"] in table:
            apres = table[m["texte"]][0]
            faites.append((i, m["texte"], apres))
            m["texte"] = apres
    return faites


def poser_couche_texte(page, mots, dpi):
    """Remplace le texte invisible de la page (scan + texte) par les mots fournis, a leur place."""
    page.add_redact_annot(page.rect)
    page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE, graphics=fitz.PDF_REDACT_LINE_ART_NONE,
                          text=fitz.PDF_REDACT_TEXT_REMOVE)
    k = 72.0 / dpi
    police = os.path.join(_BASE, "fonts", "LiberationSans-Regular.ttf")
    nom_police = "helv"
    if os.path.exists(police):                         # tous les caracteres (€, œ...) : police libre embarquee
        page.insert_font(fontname="PhilOCR", fontfile=police)
        nom_police = "PhilOCR"
        mesure = fitz.Font(fontfile=police)
    else:
        mesure = fitz.Font("helv")
    lignes = {}
    for m in mots:
        lignes.setdefault(m["ligne"], []).append(m)
    for ms in lignes.values():
        y0 = min(m["y"] for m in ms) * k
        y1 = max(m["y"] + m["h"] for m in ms) * k
        taille = max(4.0, (y1 - y0) * 0.82)
        base = y1 - (y1 - y0) * 0.18
        for m in ms:
            t = m["texte"].strip()
            if not t:
                continue
            x0, largeur = m["x"] * k, max(1.0, m["l"] * k)
            lt = mesure.text_length(t, fontsize=taille) or largeur
            mat = fitz.Matrix(largeur / lt, 1)
            try:
                page.insert_text((x0, base), t, fontname=nom_police, fontsize=taille, render_mode=3,
                                 morph=(fitz.Point(x0, base), mat))
            except Exception:
                pass                                   # caractere hors police : le mot reste sans texte


def ocr_image(gris, dpi, base, mots_perso=None):
    """Nettoie, redresse et reconnait une image : (pdf de la page, mots, angle, image nettoyee)."""
    a = angle_inclinaison(gris)
    nb = nettoyer(redresser(gris, a) if abs(a) > 0.05 else gris)
    tif = base + ".tif"
    Image.fromarray(nb).convert("1").save(tif, compression="group4", dpi=(dpi, dpi))
    cmd = [tesseract_exe() or "tesseract", tif, base, "-l", "fra", "--dpi", str(dpi)]
    if mots_perso:
        liste = base + ".mots.txt"
        with open(liste, "w", encoding="utf-8") as f:
            f.write("\n".join(mots_perso) + "\n")
        cmd += ["--user-words", liste]
    r = subprocess.run(cmd + ["pdf", "tsv"], env={**os.environ, "TESSDATA_PREFIX": TESS}, stdout=subprocess.DEVNULL,
                       stderr=subprocess.PIPE, creationflags=0x08000000 if sys.platform == "win32" else 0)
    if r.returncode != 0 or not os.path.exists(base + ".pdf"):
        raise RuntimeError("Tesseract : " + r.stderr.decode("utf-8", "replace")[-300:])
    return base + ".pdf", lire_tsv(base + ".tsv"), a, nb


def analyser(entree, progression=None, apprentissage=None):
    """Premiere etape : reconnaissance page par page (les pages qui ont deja du texte sont gardees).
    apprentissage = {"mots": [...], "regles": {...}}. Renvoie un dict a passer a assembler()."""
    d = fitz.open(entree)
    if d.needs_pass:
        raise ValueError("document protégé par mot de passe")
    app = apprentissage or {}
    tmp = tempfile.mkdtemp()
    pages = []
    for i, p in enumerate(d):
        if progression:
            progression(i, len(d))
        if a_du_texte(p):
            pages.append({"num": i, "garder": True})
            continue
        gris, dpi = image_de_page(d, p)
        pdf, mots, angle, nb = ocr_image(gris, dpi, os.path.join(tmp, f"p{i:03d}"), app.get("mots"))
        auto = appliquer_regles(mots, app.get("regles"))
        pages.append({"num": i, "garder": False, "pdf": pdf, "mots": mots, "dpi": dpi, "angle": angle,
                      "image": nb, "auto": auto, "modifie": bool(auto)})
    return {"doc": d, "pages": pages, "entree": entree}


def assembler(analyse, sortie):
    d = analyse["doc"]
    out = fitz.open()
    rapport = []
    for pg in analyse["pages"]:
        if pg["garder"]:
            out.insert_pdf(d, from_page=pg["num"], to_page=pg["num"])
            rapport.append((pg["num"] + 1, 0.0, None))
            continue
        morceau = fitz.open(pg["pdf"])
        if pg.get("modifie"):
            poser_couche_texte(morceau[0], pg["mots"], pg["dpi"])
        out.insert_pdf(morceau)
        rapport.append((pg["num"] + 1, pg["angle"], pg["dpi"]))
    out.set_metadata({"producer": "PhilPDF", "title": os.path.basename(analyse["entree"])})
    try:
        out.subset_fonts()                             # seulement les lettres utilisees : fichier leger
    except Exception:
        pass
    out.save(sortie, garbage=3, deflate=True)
    return rapport


def traiter(entree, sortie, dpi_source=None, progression=None, apprentissage=None):
    """Reconnait le texte des pages scannees ; les pages qui ont deja du texte restent telles quelles.
    Les mots personnels et les corrections apprises sont utilises. Renvoie [(page, angle, dpi ou None)]."""
    return assembler(analyser(entree, progression, apprentissage), sortie)


# ------------------------------------------------------------------ comparaison avec une autre lecture (IA)
def _norm(t):
    return t.strip().strip(".,;:!?()[]«»\"'“”").lower()


def differences(mots, texte_ia):
    """Compare les mots de Tesseract a la transcription de l'IA : [{"i1", "i2", "tesseract", "ia"}]
    (indices dans mots ; i1 == i2 : mots vus par l'IA seulement, ignores)."""
    import difflib
    jetons = texte_ia.split()
    sm = difflib.SequenceMatcher(None, [_norm(m["texte"]) for m in mots], [_norm(j) for j in jetons], autojunk=False)
    out = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal" or i1 == i2:
            continue
        if (i2 - i1) > 6 or (j2 - j1) > 8:             # passage illisible d'un cote : on ne propose pas
            continue
        out.append({"i1": i1, "i2": i2, "tesseract": " ".join(m["texte"] for m in mots[i1:i2]),
                    "ia": " ".join(jetons[j1:j2])})
    return out


def zone_mots(mots, i1, i2, marge=6):
    ms = mots[i1:i2]
    return (min(m["x"] for m in ms) - marge, min(m["y"] for m in ms) - marge,
            max(m["x"] + m["l"] for m in ms) + marge, max(m["y"] + m["h"] for m in ms) + marge)


def remplacer_mots(mots, i1, i2, texte):
    """Met texte a la place des mots i1..i2 (le premier recoit tout, les autres sont vides)."""
    for k in range(i1, i2):
        mots[k]["texte"] = texte if k == i1 else ""
