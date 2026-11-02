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


def en_couleur(p):
    """Vrai si la page a de la couleur (photo, tampon, logo) : on garde alors son image telle quelle au lieu de la
    remplacer par une image noir et blanc nettoyee."""
    try:
        pm = p.get_pixmap(dpi=30, colorspace=fitz.csRGB, alpha=False)
        rgb = np.frombuffer(pm.samples, np.uint8).reshape(pm.height, pm.width, 3).astype(np.int16)
        sat = rgb.max(axis=2) - rgb.min(axis=2)
        return float((sat > 40).mean()) > 0.01
    except Exception:
        return False


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


def poser_couche_texte(page, mots, dpi, effacer=True):
    """Pose le texte invisible des mots (coordonnees en pixels de l'image a `dpi`) ; efface d'abord l'ancien."""
    if effacer and page.get_text("text").strip():
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
        rot = ms[0].get("rot", 0)
        cote = rot in (90, 270)                        # texte couche : la hauteur des lettres est en x
        a0 = min((m["x"] if cote else m["y"]) for m in ms) * k
        a1 = max((m["x"] + m["l"] if cote else m["y"] + m["h"]) for m in ms) * k
        taille = max(4.0, (a1 - a0) * 0.82)
        for m in ms:
            t = m["texte"].strip()
            if not t:
                continue
            x0, y0, x1, y1 = m["x"] * k, m["y"] * k, (m["x"] + m["l"]) * k, (m["y"] + m["h"]) * k
            longueur = max(1.0, (y1 - y0) if cote else (x1 - x0))
            lt = mesure.text_length(t, fontsize=taille) or longueur
            e = longueur / lt
            # point de depart sur la ligne de base, sens de l'ecriture, etirement dans ce sens
            if rot == 180:
                pt, mat = fitz.Point(x1, a0 + (a1 - a0) * 0.18), fitz.Matrix(e, 1)
            elif rot == 90:                            # se lit de bas en haut
                pt, mat = fitz.Point(a1 - (a1 - a0) * 0.18, y1), fitz.Matrix(1, e)
            elif rot == 270:                           # se lit de haut en bas
                pt, mat = fitz.Point(a0 + (a1 - a0) * 0.18, y0), fitz.Matrix(1, e)
            else:
                pt, mat = fitz.Point(x0, a1 - (a1 - a0) * 0.18), fitz.Matrix(e, 1)
            try:
                page.insert_text(pt, t, fontname=nom_police, fontsize=taille, render_mode=3, rotate=rot,
                                 morph=(pt, mat))
            except Exception:
                pass                                   # caractere hors police : le mot reste sans texte
    try:
        page.clean_contents()                          # un seul flux par page au lieu d'un par mot : fichier leger
    except Exception:
        pass


def qualite(mots):
    """Confiance moyenne de Tesseract, ponderee par la longueur des mots (0 a 100)."""
    n = sum(len(m["texte"]) for m in mots)
    return sum(m["conf"] * len(m["texte"]) for m in mots) / n if n else 0.0


def versions_moteurs():
    """{'PyMuPDF': '1.26.x', 'MuPDF': '...', 'Tesseract': '5.x', 'Qt': '...'} ; 'absent' si introuvable."""
    v = {}
    try:
        import pymupdf
        v["PyMuPDF"] = getattr(pymupdf, "__version__", None) or pymupdf.VersionBind
        v["MuPDF"] = pymupdf.VersionFitz
    except Exception:
        v["PyMuPDF"] = "absent"
    try:
        exe = tesseract_exe()
        r = subprocess.run([exe or "tesseract", "--version"], capture_output=True, text=True, timeout=15,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        premiere = (r.stdout or r.stderr).strip().splitlines()[0]
        v["Tesseract"] = premiere.split()[-1].lstrip("v")
    except Exception:
        v["Tesseract"] = "absent"
    try:
        import PySide6
        from PySide6.QtCore import qVersion
        v["Qt"] = qVersion()
        v["PySide6"] = PySide6.__version__
    except Exception:
        pass
    return v


def _tesseract(image, base, dpi, sorties, mots_perso=None, parallele=False):
    cmd = [tesseract_exe() or "tesseract", image, base, "-l", "fra", "--dpi", str(dpi)]
    if mots_perso:
        liste = base + ".mots.txt"
        with open(liste, "w", encoding="utf-8") as f:
            f.write("\n".join(mots_perso) + "\n")
        cmd += ["--user-words", liste]
    env = {**os.environ, "TESSDATA_PREFIX": TESS}
    if parallele:                                      # plusieurs lectures en meme temps : un coeur chacune
        env["OMP_THREAD_LIMIT"] = "1"
    r = subprocess.run(cmd + sorties, env=env, stdout=subprocess.DEVNULL,
                       stderr=subprocess.PIPE, creationflags=0x08000000 if sys.platform == "win32" else 0)
    if r.returncode != 0 or not os.path.exists(base + ".tsv"):
        raise RuntimeError("Tesseract : " + r.stderr.decode("utf-8", "replace")[-300:])


def tiff_g4(nb, dpi):
    import io
    t = io.BytesIO()
    Image.fromarray(nb).convert("1").save(t, "TIFF", compression="group4", dpi=(dpi, dpi), tiffinfo={278: nb.shape[0]})
    return t.getvalue()


def image_de_tiff(tif):
    import io
    return np.array(Image.open(io.BytesIO(tif)).convert("L"))


def page_scan(doc, tif, largeur_pt, hauteur_pt):
    """Ajoute une page avec l'image noir et blanc compressee en G4 (comme un fax : tres leger)."""
    import io
    r = Image.open(io.BytesIO(tif))
    w, h = r.size
    brut = b"".join(tif[o:o + c] for o, c in zip(r.tag_v2[273], r.tag_v2[279]))
    page = doc.new_page(width=largeur_pt, height=hauteur_pt)
    # keep_proportion=False : l'image provisoire (1 x 1) est carree ; sans cela la vraie image, posee ensuite a sa
    # place, etait tassee dans un carre (page « aplatie » apres l'OCR)
    x = page.insert_image(page.rect, pixmap=fitz.Pixmap(fitz.csGRAY, fitz.IRect(0, 0, 1, 1), False),
                          keep_proportion=False)
    doc.update_stream(x, brut, compress=False)
    for cle, val in (("Filter", "/CCITTFaxDecode"), ("DecodeParms", f"<</K -1/Columns {w}/Rows {h}/BlackIs1 true>>"),
                     ("Width", str(w)), ("Height", str(h)), ("BitsPerComponent", "1"), ("ColorSpace", "/DeviceGray")):
        doc.xref_set_key(x, cle, val)
    return page


def _lire(image, base, dpi, mots_perso, echelle, rotation=0, parallele=False):
    """Mots de l'image, lue tournee de `rotation` degres (90, 180, 270 : texte couche ou a l'envers) ; positions
    rendues dans le repere de l'image d'origine (a l'echelle 1), avec "rot" = sens du texte sur la page."""
    h0, w0 = image.shape[:2]
    if rotation:
        image = cv2.rotate(image, {90: cv2.ROTATE_90_CLOCKWISE, 180: cv2.ROTATE_180,
                                   270: cv2.ROTATE_90_COUNTERCLOCKWISE}[rotation])
    cv2.imwrite(base + ".png", image)
    _tesseract(base + ".png", base, dpi, ["tsv"], mots_perso, parallele)
    # mot lu « debout » dans une ligne horizontale : Tesseract lit parfois aussi du texte vertical, mais sa boite
    # n'est alors pas fiable (mot place ailleurs) ; ce texte-la est lu par la passe tournee qui le met a l'endroit
    mots = [m for m in lire_tsv(base + ".tsv") if len(m["texte"]) < 3 or m["l"] >= m["h"] * 0.8]
    for m in mots:
        x, y, l, h = m["x"], m["y"], m["l"], m["h"]
        if rotation == 90:                             # image tournee d'un quart a droite : (u, v) -> (v, h0 - u)
            x, y, l, h = y, h0 - (x + l), h, l
        elif rotation == 180:
            x, y = w0 - (x + l), h0 - (y + h)
        elif rotation == 270:
            x, y, l, h = w0 - (y + h), x, h, l
        m["x"], m["y"], m["l"], m["h"] = x, y, l, h
        m["rot"] = rotation
        if echelle != 1:
            for c in ("x", "y", "l", "h"):
                m[c] = int(round(m[c] / echelle))
    return mots


SEUIL_QUALITE = 60
CONF_MINI = 25
CONF_TOURNE = 60                                   # lectures tournees : seulement les mots surs
DPI_LECTURE = 300


def fusionner(lectures):
    """Plusieurs lectures de la meme image -> une seule : a chaque endroit, le mot le plus sur est garde."""
    cand = []
    for k, ms in enumerate(lectures):
        for m in ms:
            m = dict(m)
            m["ligne"] = (k,) + tuple(m["ligne"])
            cand.append(m)
    cand.sort(key=lambda m: -m["conf"] * min(len(m["texte"]), 6))

    def commun(a, b):
        x = min(a["x"] + a["l"], b["x"] + b["l"]) - max(a["x"], b["x"])
        y = min(a["y"] + a["h"], b["y"] + b["h"]) - max(a["y"], b["y"])
        return max(0, x) * max(0, y)
    garde = []
    for m in cand:
        s = max(1, m["l"] * m["h"])
        if all(commun(m, g) < 0.3 * min(s, max(1, g["l"] * g["h"])) for g in garde):
            garde.append(m)
    # ordre de lecture : par sens d'ecriture, puis par ligne (centres alignes), puis le long de la ligne
    out, n = [], 0
    for rot in (0, 90, 180, 270):
        ms = [m for m in garde if m.get("rot", 0) == rot]
        cote = rot in (90, 270)
        travers = (lambda m: m["x"] + m["l"] / 2) if cote else (lambda m: m["y"] + m["h"] / 2)
        epais = (lambda m: m["l"]) if cote else (lambda m: m["h"])
        lignes = []
        for m in sorted(ms, key=travers, reverse=rot in (180, 270)):
            c = travers(m)
            if lignes and abs(c - lignes[-1][0]) < 0.5 * max(epais(m), lignes[-1][1]):
                lignes[-1][2].append(m)
            else:
                lignes.append([c, epais(m), [m]])
        long = {0: lambda m: m["x"], 180: lambda m: -m["x"], 90: lambda m: -m["y"], 270: lambda m: m["y"]}[rot]
        for _, _, l in lignes:
            for m in sorted(l, key=long):
                m["ligne"] = (n,)                      # une ligne visuelle = une ligne de texte (copier-coller)
                out.append(m)
            n += 1
    return out


def ocr_image(gris, dpi, base, mots_perso=None, tourne=True):
    """Nettoie, redresse et reconnait une image : (tiff G4 de la page, mots, angle, qualite).
    Plusieurs lectures, faites en meme temps (une par coeur du processeur) :
    - l'image nettoyee, a 300 dpi au plus (plus rapide, et Tesseract lit mieux) ;
    - l'image en gris non nettoyee : texte clair sur fond fonce ou en couleur, que le nettoyage efface ;
    - un scan peu fin (fax, 200 dpi) agrandi a 300 dpi : les petites lettres se lisent mieux (les grandes, sans
      agrandir : on garde les deux) ;
    - si `tourne` : l'image tournee d'un demi-tour et d'un quart de tour dans chaque sens (texte a l'envers ou
      couche : livret plie, page retournee) ; seuls les mots surs de ces lectures comptent.
    Si le resultat est peu sur (lettres fines ou cassees : machine a ecrire, fax, photocopie pale), d'autres
    lectures se font sur une copie aux traits epaissis. A chaque endroit, le mot le plus sur est garde.
    L'image du PDF reste l'image nettoyee, non epaissie."""
    from concurrent.futures import ThreadPoolExecutor
    a = angle_inclinaison(gris)
    droit = redresser(gris, a) if abs(a) > 0.05 else gris
    nb = nettoyer(droit)
    echelle = min(1.0, DPI_LECTURE / dpi)
    dpi_l = int(round(dpi * echelle))

    def reduire(img):
        return img if echelle == 1 else cv2.resize(img, None, fx=echelle, fy=echelle, interpolation=cv2.INTER_AREA)
    lecture, gris_l = reduire(nb), reduire(droit)
    taches = [(lecture, base, dpi_l, echelle, 0), (gris_l, f"{base}_g", dpi_l, echelle, 0)]
    if dpi < DPI_LECTURE * 0.9:
        kg = DPI_LECTURE / dpi
        taches.append((cv2.resize(droit, None, fx=kg, fy=kg, interpolation=cv2.INTER_CUBIC), f"{base}_a",
                       DPI_LECTURE, kg, 0))
    if tourne:
        taches += [(gris_l, f"{base}_r{r}", dpi_l, echelle, r) for r in (180, 90, 270)]

    def lire(t):
        img, b, d, e, r = t
        ms = _lire(img, b, d, mots_perso, e, r, parallele=True)
        if r:
            ms = [m for m in ms if m["conf"] >= CONF_TOURNE and sum(c.isalnum() for c in m["texte"]) >= 2]
        return ms
    with ThreadPoolExecutor(max(1, min(len(taches), os.cpu_count() or 2))) as ex:
        lectures = list(ex.map(lire, taches))
    mots = fusionner(lectures)
    q = qualite(mots)
    for k in (2, 3):
        if q >= SEUIL_QUALITE:
            break
        lectures.append(_lire(cv2.erode(lecture, np.ones((k, k), np.uint8)), f"{base}_e{k}", dpi_l, mots_perso, echelle))
        mots = fusionner(lectures)
        q = qualite(mots)
    mots = [m for m in mots if m["conf"] >= CONF_MINI]
    return tiff_g4(nb, dpi), mots, a, q


def analyser(entree, progression=None, apprentissage=None):
    """Premiere etape : reconnaissance page par page (les pages qui ont deja du texte sont gardees).
    progression(page, total, qualite_page_precedente). apprentissage = {"mots": [...], "regles": {...}}."""
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
        tif, mots, angle, q = ocr_image(gris, dpi, os.path.join(tmp, f"p{i:03d}"), app.get("mots"))
        auto = appliquer_regles(mots, app.get("regles"))
        couleur = p.rotation == 0 and en_couleur(p)
        if couleur and abs(angle) > 0.05:              # image gardee non redressee : mots replaces sur l'image d'origine
            h, w = gris.shape
            M = cv2.getRotationMatrix2D((w / 2, h / 2), -angle, 1)
            for m in mots:
                cx, cy = m["x"] + m["l"] / 2, m["y"] + m["h"] / 2
                nx, ny = M[0, 0] * cx + M[0, 1] * cy + M[0, 2], M[1, 0] * cx + M[1, 1] * cy + M[1, 2]
                m["x"], m["y"] = int(round(nx - m["l"] / 2)), int(round(ny - m["h"] / 2))
        pages.append({"num": i, "garder": False, "tif": tif, "mots": mots, "dpi": dpi, "angle": angle, "qualite": q,
                      "auto": auto, "taille": (p.rect.width, p.rect.height), "couleur": couleur})
    if progression:
        progression(len(d), len(d))
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
        if pg.get("couleur"):                          # page en couleur : son image reste, le texte s'y ajoute
            out.insert_pdf(d, from_page=pg["num"], to_page=pg["num"])
            poser_couche_texte(out[-1], pg["mots"], pg["dpi"], effacer=False)
        else:
            page = page_scan(out, pg["tif"], *pg["taille"])
            poser_couche_texte(page, pg["mots"], pg["dpi"], effacer=False)
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
