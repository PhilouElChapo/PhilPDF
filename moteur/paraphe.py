"""Paraphe : vos initiales (ecrites dans la police choisie) ou votre tampon « paraphe », posees en un clic sur
toutes les pages, au meme endroit. Chaque paraphe est un tampon PhilPDF : deplacable, supprimable, Ctrl+Z annule."""
import pymupdf as fitz

from . import objets

STANDARD = {"Helv": "helv", "HeBo": "hebo", "HeOb": "heit", "TiRo": "tiro", "TiBo": "tibo", "TiIt": "tiit",
            "Cour": "cour", "CoBo": "cobo"}
POSITIONS = ("bas_droite", "bas_centre", "bas_gauche", "haut_droite", "haut_gauche")


def polices_pages(doc, max_pages=30):
    """Polices integrees aux pages du document, reutilisables : [(nom lisible, xref)]."""
    vus, out = set(), []
    for n in range(min(len(doc), max_pages)):
        for xref, ext, _typ, base, *_r in doc.get_page_fonts(n):
            nom = base.split("+")[-1]
            if ext in ("ttf", "otf", "cff") and nom not in vus:
                try:
                    if doc.extract_font(xref)[3]:
                        vus.add(nom)
                        out.append((nom, xref))
                except Exception:                    # noqa: BLE001
                    pass
    return out


def _police(cle, doc=None):
    """(fitz.Font, arguments pour insert_text)."""
    if cle in STANDARD:
        return fitz.Font(STANDARD[cle]), {"fontname": STANDARD[cle]}
    if cle.startswith("fichier:"):
        chemin = cle[len("fichier:"):]
        return fitz.Font(fontfile=chemin), {"fontname": "PARAPHE", "fontfile": chemin}
    if cle.startswith("doc:") and doc is not None:
        buf = doc.extract_font(int(cle[4:]))[3]
        return fitz.Font(fontbuffer=buf), {"fontname": "PARAPHE", "fontbuffer": buf}
    return fitz.Font("helv"), {"fontname": "helv"}


def initiales_pdf(texte, police="TiIt", couleur=(0.1, 0.2, 0.55), souligne=False, doc=None):
    """Petit PDF (une page ajustee au texte) avec les initiales : la police est integree."""
    texte = (texte or "").strip() or "?"
    font, args = _police(police, doc)
    taille = 40
    larg = font.text_length(texte, fontsize=taille)
    asc, desc = font.ascender, font.descender
    haut = (asc - desc) * taille
    marge = 4
    d = fitz.open()
    p = d.new_page(width=larg + 2 * marge, height=haut + 2 * marge + (6 if souligne else 0))
    base = marge + asc * taille
    p.insert_text((marge, base), texte, fontsize=taille, color=couleur, **args)
    if souligne:
        y = base - desc * taille * 0.4 + 3
        p.draw_line((marge, y), (marge + larg, y), color=couleur, width=1.6)
    return d.tobytes(garbage=3, deflate=True)


def pages_choisies(nb, choix, plage=""):
    if choix == "sauf_derniere":
        return list(range(max(0, nb - 1))) or [0]
    if choix == "sauf_premiere":
        return list(range(1, nb)) or [0]
    if choix == "plage":
        from .fractionner import par_plages
        return sorted({p for g in par_plages(nb, plage) for p in g})
    return list(range(nb))


def cadre(page_rect, taille, position, hauteur, marge):
    """Rectangle du paraphe dans la page : hauteur fixe, largeur selon les proportions du paraphe."""
    w0, h0 = taille
    h = hauteur
    w = w0 * h / max(h0, 1)
    R = page_rect
    x = {"droite": R.x1 - marge - w, "gauche": R.x0 + marge, "centre": (R.x0 + R.x1 - w) / 2}[position.split("_")[1]]
    y = R.y1 - marge - h if position.startswith("bas") else R.y0 + marge
    return fitz.Rect(x, y, x + w, y + h)


def parapher(doc, pdf, pages, position="bas_droite", hauteur=28, marge=22, auteur="", nom="Paraphe"):
    """Pose le paraphe sur chaque page ; renvoie le nombre de pages paraphees."""
    t = objets.taille_naturelle(pdf)
    for n in pages:
        page = doc[n]
        objets.poser(doc, n, cadre(page.rect, t, position, hauteur, marge), pdf, nom, auteur, "paraphe")
    return len(pages)
