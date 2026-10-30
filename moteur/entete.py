"""En-tete, pied de page et numerotation Bates.

Ce que PhilPDF pose est marque (comme Acrobat : « /Artifact /Pagination ») pour pouvoir etre retrouve, remplace ou
retire plus tard ; les reglages sont gardes dans le PDF et reproposes a la prochaine ouverture du dialogue.
Une numerotation Bates posee par un autre logiciel est reconnue (prefixe, nombre de chiffres, numeros) et peut
etre remplacee."""
import json
import math
import re

import pymupdf as fitz

MARQUE = b"/Artifact <</Type /Pagination /PhilPDF (entete)>> BDC\n"
_BLOC = re.compile(rb"/Artifact <</Type /Pagination /PhilPDF \(entete\)>> BDC\n.*?\nEMC\n", re.S)
CLEF = "PhilPDFEntete"

# position : (cote, alignement) ; les marges laterales sont ecrites a la verticale
POSITIONS = ("bas_droite", "bas_centre", "bas_gauche", "haut_droite", "haut_centre", "haut_gauche",
             "marge_gauche", "marge_droite")


def poser(page, texte, position="bas_droite", taille=9, marge=36, angle=0.0, couleur=(0.2, 0.2, 0.2)):
    """Ecrit le texte a la position voulue, incline de « angle » degres (sens inverse des aiguilles d'une montre).
    Marge gauche : se lit de bas en haut ; marge droite : de haut en bas (comme les numeros sur le cote d'Acrobat)."""
    if not texte:
        return
    R = page.rect
    L = fitz.get_text_length(texte, fontname="helv", fontsize=taille)
    if position == "marge_gauche":
        base, c = 90.0, fitz.Point(marge * 0.66 + taille / 2, R.height / 2)
    elif position == "marge_droite":
        base, c = -90.0, fitz.Point(R.width - marge * 0.66 - taille / 2, R.height / 2)
    else:
        cote, align = position.split("_")
        y = (marge * 0.66 + taille) if cote == "haut" else (R.height - marge * 0.55)
        x = {"gauche": marge, "centre": (R.width - L) / 2, "droite": R.width - marge - L}[align]
        base, c = 0.0, fitz.Point(x + L / 2, y - taille * 0.35)
    a = base + (angle or 0.0)
    r = math.radians(a)
    sens = fitz.Point(math.cos(r), -math.sin(r))          # direction de la ligne de texte
    haut = fitz.Point(-math.sin(r), -math.cos(r))         # vers le haut des lettres
    debut = c - sens * (L / 2) - haut * (taille * 0.35)
    if abs(a) < 0.01:
        page.insert_text(debut, texte, fontname="helv", fontsize=taille, color=couleur, overlay=True)
    else:
        page.insert_text(debut, texte, fontname="helv", fontsize=taille, color=couleur, overlay=True,
                         morph=(debut, fitz.Matrix(a)))


def marquer(page, avant):
    """Les flux ajoutes depuis « avant » (liste des contenus de la page) sont marques comme pose par PhilPDF."""
    doc = page.parent
    for x in page.get_contents():
        if x not in avant:
            doc.update_stream(x, MARQUE + doc.xref_stream(x) + b"\nEMC\n")


def retirer(doc):
    """Retire tout ce que PhilPDF a pose (en-tetes, pieds, numeros Bates). Renvoie le nombre de pages touchees."""
    n = 0
    for page in doc:
        touche = False
        for x in page.get_contents():
            s = doc.xref_stream(x) or b""
            if b"/PhilPDF (entete)" in s:
                doc.update_stream(x, _BLOC.sub(b"", s))
                touche = True
        n += touche
    return n


def deja_pose(doc):
    """Vrai si le document contient un en-tete / pied / Bates pose par PhilPDF."""
    for page in doc:
        for x in page.get_contents():
            if b"/PhilPDF (entete)" in (doc.xref_stream(x) or b""):
                return True
    return False


def reglages(doc):
    """Reglages enregistres la derniere fois dans ce PDF, ou None."""
    try:
        t, v = doc.xref_get_key(doc.pdf_catalog(), CLEF)
        if t == "string":
            return json.loads(v)
    except Exception:                                    # noqa: BLE001
        pass
    return None


def enregistrer_reglages(doc, d):
    try:
        doc.xref_set_key(doc.pdf_catalog(), CLEF, fitz.get_pdf_str(json.dumps(d, ensure_ascii=False)))
    except Exception:                                    # noqa: BLE001
        pass


def chercher_bates(doc, pages_max=60):
    """Numerotation Bates deja presente (posee par un autre logiciel, ou par PhilPDF) : un meme prefixe suivi d'un
    numero qui augmente de 1 a chaque page, pres d'un bord. Renvoie {prefixe, chiffres, suffixe, premier, dernier,
    rects: {page: [Rect]}, pages} ou None."""
    motif = re.compile(r"^(.{0,30}?)(\d{3,12})([^\d]{0,10})$")
    vus = {}
    for n, page in enumerate(doc):
        if n >= pages_max:
            break
        R = page.rect
        bord = fitz.Rect(R.x0 + R.width * 0.13, R.y0 + R.height * 0.10, R.x1 - R.width * 0.13, R.y1 - R.height * 0.10)
        for b in page.get_text("dict")["blocks"]:
            for l in b.get("lines", []):
                txt = "".join(sp["text"] for sp in l["spans"]).strip()
                m = motif.match(txt)
                if not m:
                    continue
                r = fitz.Rect(l["bbox"])
                if bord.contains(r):                       # au milieu de la page : pas un numero Bates
                    continue
                cle = (m.group(1), len(m.group(2)), m.group(3))
                vus.setdefault(cle, []).append((n, int(m.group(2)), r))
    meilleur = None
    for (pre, ch, suf), l in vus.items():
        par_page = {}
        for n, num, r in l:
            par_page.setdefault(n, (num, r))
        if len(par_page) < max(1, min(len(doc), pages_max) * 0.6):
            continue
        pages = sorted(par_page)
        ok = sum(1 for a, b in zip(pages, pages[1:]) if par_page[b][0] - par_page[a][0] == b - a)
        if len(pages) > 1 and ok < (len(pages) - 1) * 0.8:
            continue
        premier = par_page[pages[0]][0] - pages[0]
        res = {"prefixe": pre, "chiffres": ch, "suffixe": suf, "premier": premier,
               "dernier": premier + len(doc) - 1, "pages": len(pages),
               "rects": {n: [r for n2, _num, r in l if n2 == n] for n in pages}}
        if meilleur is None or res["pages"] > meilleur["pages"]:
            meilleur = res
    return meilleur


def effacer_bates(doc, trouve, decalage=0):
    """Efface les numeros Bates trouves (seulement leur texte, ni images ni traits). « decalage » : numero de la
    premiere page de doc dans le document d'origine (apercu sur une copie d'une seule page)."""
    for n, page in enumerate(doc):
        rs = trouve["rects"].get(n + decalage) or trouve["rects"].get(str(n + decalage)) or []
        for r in rs:
            page.add_redact_annot(fitz.Rect(r) + (-1, -1, 1, 1))
        if rs:
            page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE, graphics=fitz.PDF_REDACT_LINE_ART_NONE)
