"""Creer un formulaire a partir d'un document : reperer les zones a remplir et y poser de vrais champs PDF.

Reperes (comme « Preparer un formulaire » d'Acrobat) :
  - pointilles et soulignes tapes au clavier (_____ ou ......) ;
  - traits horizontaux dessines sous un espace vide ;
  - petits carres dessines ou caracteres case (☐ □ ❑) -> cases a cocher ;
  - cadres vides -> zones de texte (sur plusieurs lignes si le cadre est haut).
Chaque champ prend le nom du libelle le plus proche (a gauche, sinon au-dessus).
"""
import re
import pymupdf as fitz

CASES = "☐□❑❒▢◻"


def _libelle(page, r, mots, case=False):
    """Texte juste a gauche sur la meme ligne, sinon juste au-dessus (case a cocher : le texte a droite)."""
    if case:
        droite = sorted((w for w in mots if abs((w[1] + w[3]) / 2 - (r.y0 + r.y1) / 2) < max(6, r.height) and
                         w[0] >= r.x1 - 1 and w[0] - r.x1 < 200), key=lambda w: w[0])
        sel = []
        for w in droite:
            if sel and w[0] - sel[-1][2] > 12:
                break
            sel.append(w)
        if sel:
            return " ".join(w[4] for w in sel[:6]).strip(" :")[:60]
    gauche = [w for w in mots if abs((w[1] + w[3]) / 2 - (r.y0 + r.y1) / 2) < max(6, r.height * 0.6) and w[2] <= r.x0 + 2
              and r.x0 - w[2] < 200 and not re.fullmatch(r"[_.…]+", w[4])]
    if gauche:
        gauche.sort(key=lambda w: w[0])
        # derniers mots avant le champ, jusqu'a un grand blanc
        sel = [gauche[-1]]
        for w in reversed(gauche[:-1]):
            if sel[0][0] - w[2] > 12:
                break
            sel.insert(0, w)
        t = " ".join(w[4] for w in sel[-6:])
    else:
        dessus = [w for w in mots if 0 < r.y0 - w[3] < 22 and w[0] < r.x1 and w[2] > r.x0 - 20]
        t = " ".join(w[4] for w in sorted(dessus, key=lambda w: w[0])[:6])
    t = re.sub(r"[_.…:]+$", "", t.strip()).strip(" :")
    return t[:60] or "Champ"


def _libre(r, occupes):
    return not any(r.intersects(o) and (r & o).get_area() > 0.25 * min(r.get_area(), o.get_area()) for o in occupes)


def detecter(page):
    """[{"genre": "texte"|"case", "rect": Rect, "nom": str, "lignes": bool}] pour une page."""
    mots = page.get_text("words")
    champs, occupes = [], [fitz.Rect(w.rect) for w in page.widgets()]

    def ajouter(genre, r, multi=False):
        r = fitz.Rect(r)
        if r.is_empty or not _libre(r, occupes + [c["rect"] for c in champs]):
            return
        champs.append({"genre": genre, "rect": r, "nom": _libelle(page, r, mots, genre == "case"), "lignes": multi})

    texte_rects = [fitz.Rect(w[:4]) for w in mots if not re.fullmatch(r"[_.…]{3,}", w[4])]
    # 1. soulignes et pointilles tapes
    for w in mots:
        t = w[4]
        m = re.search(r"[_]{4,}|[.…]{5,}", t)
        if not m:
            continue
        r = fitz.Rect(w[:4])
        if m.start() > 0 and len(t) > 0:              # « Nom:_____ » : le champ commence apres le libelle
            r.x0 += r.width * m.start() / len(t)
        h = max(r.height, 12)
        ajouter("texte", fitz.Rect(r.x0, r.y1 - h, r.x1, r.y1 + 1))
    # 2. cases tapees
    for w in mots:
        for k, ch in enumerate(w[4]):
            if ch in CASES:
                r = fitz.Rect(w[:4])
                l = r.width / max(1, len(w[4]))
                c = fitz.Rect(r.x0 + k * l, r.y0, r.x0 + (k + 1) * l, r.y1)
                cote = min(c.width, c.height)
                ajouter("case", fitz.Rect(c.x0, c.y1 - cote - 1, c.x0 + cote, c.y1 - 1))
    # 3. dessins : traits et carres
    for d in page.get_drawings():
        for it in d["items"]:
            if it[0] == "l":
                a, b = it[1], it[2]
                if abs(a.y - b.y) < 0.8 and abs(b.x - a.x) > 40:
                    x0, x1 = sorted((a.x, b.x))
                    zone = fitz.Rect(x0, a.y - 14, x1, a.y - 0.5)
                    if not any(zone.intersects(t) and (zone & t).width > 6 for t in texte_rects):
                        ajouter("texte", zone)
            elif it[0] in ("re", "qu"):
                r = fitz.Rect(it[1]) if it[0] == "re" else it[1].rect
                if 5 <= r.width <= 18 and 5 <= r.height <= 18 and abs(r.width - r.height) < 2.5:
                    ajouter("case", r)
                elif r.height < 1.6 and r.width > 40:  # trait dessine comme un rectangle fin
                    zone = fitz.Rect(r.x0, r.y0 - 14, r.x1, r.y0 - 0.5)
                    if not any(zone.intersects(t) and (zone & t).width > 6 for t in texte_rects):
                        ajouter("texte", zone)
                elif 12 <= r.height <= 160 and r.width > 50 and r.width < page.rect.width * 0.95:
                    interieur = fitz.Rect(r.x0 + 1.5, r.y0 + 1.5, r.x1 - 1.5, r.y1 - 1.5)
                    if not any(interieur.intersects(t) for t in texte_rects):
                        ajouter("texte", interieur, multi=r.height > 30)
    return champs


def noms_uniques(champs):
    vus = {}
    for c in champs:
        base = c["nom"] or "Champ"
        n = vus.get(base, 0) + 1
        vus[base] = n
        c["nom"] = base if n == 1 else f"{base} {n}"
    return champs


def creer(doc, champs_par_page):
    """Pose les champs : {num_page: [champ, ...]} -> nombre de champs crees."""
    n = 0
    existants = {w.field_name for p in doc for w in p.widgets()}
    for num, champs in champs_par_page.items():
        page = doc[num]
        for c in champs:
            nom = c["nom"]
            k = 2
            while nom in existants:
                nom = f"{c['nom']} {k}"
                k += 1
            existants.add(nom)
            w = fitz.Widget()
            w.rect = fitz.Rect(c["rect"])
            w.field_name = nom
            w.field_label = c["nom"]
            if c["genre"] == "case":
                w.field_type = fitz.PDF_WIDGET_TYPE_CHECKBOX
                w.field_value = False
            else:
                w.field_type = fitz.PDF_WIDGET_TYPE_TEXT
                w.text_fontsize = 0 if not c.get("lignes") else 10
                w.text_font = "Helv"
                if c.get("lignes"):
                    w.field_flags |= fitz.PDF_TX_FIELD_IS_MULTILINE
            w.border_width = 0
            w.fill_color = None
            page.add_widget(w)
            n += 1
    return n
