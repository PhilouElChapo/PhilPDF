"""Outil Mesure : distances, perimetres et surfaces sur plans et cadastre.

Echelle : facteur « c » = unites reelles par point PDF (1 pt = 1/72 de pouce sur le papier) et unite « u ».
Elle se regle page par page, au moment de mesurer :
- rapport 1:N (plan a la taille d'impression) : c = N x 0,0254/72 m ;
- equivalence « 1 cm sur le papier = X m » ;
- etalonnage sur une longueur connue (cote, echelle graphique) : c = longueur reelle / longueur dans le PDF ;
- lue dans le PDF : dictionnaire /VP /Measure (plans issus de logiciels de DAO, ou deja regle dans Acrobat),
  ou texte « Echelle 1/500 » (cadastre : l'echelle d'edition de preference).

Les mesures sont gardees dans le PDF comme les annotations de mesure d'Acrobat (Line / PolyLine / Polygon avec
/IT et /Measure), accompagnees d'une etiquette (FreeText) portant la valeur ; les deux sont liees par /NM.
"""
import json
import math
import re
import uuid

import pymupdf as fitz

PT_M = 0.0254 / 72                    # un point PDF, en metres, sur le papier
UNITES = {"m": 1.0, "cm": 0.01, "mm": 0.001, "km": 1000.0, "ft": 0.3048, "in": 0.0254}
CLE = "PhilPDF_Mesure"


# ------------------------------------------------------------------ echelle
def depuis_rapport(n, unite="m"):
    """Echelle 1:N -> {c, u, texte}."""
    n = float(n)
    return {"c": n * PT_M / UNITES[unite], "u": unite, "texte": f"1:{_n(n)}", "genre": "rapport"}


def depuis_equivalence(papier_cm, reel, unite="m"):
    """« papier_cm cm sur le papier = reel <unite> »."""
    c = reel / (papier_cm / 2.54 * 72)
    return {"c": c, "u": unite, "texte": f"{_n(papier_cm)} cm = {_n(reel)} {unite}", "genre": "equivalence"}


def depuis_etalon(longueur_pt, reel, unite="m"):
    """Une longueur connue : longueur_pt points dans le PDF valent « reel » dans la realite."""
    if longueur_pt <= 0:
        raise ValueError("longueur nulle")
    c = reel / longueur_pt
    e = {"c": c, "u": unite, "genre": "etalon"}
    e["texte"] = f"1:{_n(rapport(e))}"
    return e


def sans_echelle():
    return {"c": 2.54 / 72, "u": "cm", "texte": "1:1", "genre": "papier"}


def rapport(e):
    """Rapport N equivalent (1:N), arrondi a une valeur lisible."""
    n = e["c"] * UNITES[e["u"]] / PT_M
    return round(n) if n >= 10 else round(n, 2)


def dans_unite(e, unite):
    """La meme echelle, exprimee dans une autre unite."""
    e2 = dict(e)
    e2["c"] = e["c"] * UNITES[e["u"]] / UNITES[unite]
    e2["u"] = unite
    return e2


def _n(x):
    x = float(x)
    return str(int(x)) if x == int(x) else f"{x:g}".replace(".", ",")


def lire_vp(doc, n):
    """Echelle du dictionnaire /VP de la page (Acrobat, DAO). None si aucune."""
    page = doc[n]
    t, v = doc.xref_get_key(page.xref, "VP")
    if t == "null" or not v:
        return None
    if t == "xref":
        v = doc.xref_object(int(v.split()[0]))
    # objets indirects dans le tableau : on les deplie
    for x in re.findall(r"(\d+) 0 R", v):
        try:
            v = v.replace(f"{x} 0 R", doc.xref_object(int(x)), 1)
        except Exception:
            pass
    m_c = re.search(r"/X\s*\[\s*<<(.*?)>>", v, re.S)
    if not m_c:
        return None
    c = re.search(r"/C\s+([\d.eE+-]+)", m_c.group(1))
    u = re.search(r"/U\s*\(([^)]*)\)", m_c.group(1))
    r = re.search(r"/R\s*\(([^)]*)\)", v)
    if not c:
        return None
    unite = (u.group(1).strip() if u else "m") or "m"
    if unite not in UNITES:
        unite = {"metres": "m", "meters": "m", "feet": "ft", "inch": "in"}.get(unite.lower(), unite)
    e = {"c": float(c.group(1)), "u": unite, "genre": "pdf", "philpdf": "/PhilPDF" in v or "(PhilPDF)" in v}
    e["texte"] = r.group(1) if r else (f"1:{_n(rapport(e))}" if unite in UNITES else "")
    return e


_RE_ECH = re.compile(r"[ÉEée]chelle\s*(d['’]\s*(?:[ée]dition|origine))?\s*:?\s*1\s*[/:]\s*(\d[\d\s.  ]*\d|\d)", re.I)


def lire_texte(doc, n):
    """Echelle ecrite sur le plan (« Echelle : 1/200 », cadastre « Echelle d'edition : 1/500 »).
    Renvoie (N, libelle) ou None ; l'echelle d'edition passe avant celle d'origine."""
    try:
        txt = doc[n].get_text()
    except Exception:
        return None
    trouves = []
    for m in _RE_ECH.finditer(txt):
        try:
            val = int(re.sub(r"[\s.  ]", "", m.group(2)))
        except ValueError:
            continue
        if 2 <= val <= 1000000:
            genre = (m.group(1) or "").lower()
            trouves.append((0 if "dition" in genre else 2 if "origine" in genre else 1, val, m.group(0).strip()))
    if not trouves:
        m = re.search(r"(?<![\d/])1\s*[/:]\s*(50|100|200|250|500|1000|2000|2500|5000|10000)(?![\d/])", txt)
        if m and re.search(r"[ée]ch|scale", txt, re.I):
            trouves.append((3, int(m.group(1)), m.group(0)))
    if not trouves:
        return None
    trouves.sort()
    return trouves[0][1], " ".join(trouves[0][2].split())


def ecrire_vp(doc, n, e):
    """Pose l'echelle dans la page (/VP), pour qu'Acrobat la reprenne dans son outil Mesure. Ne remplace pas un /VP
    venu d'un autre logiciel (plans de DAO a plusieurs vues) : renvoie False dans ce cas."""
    page = doc[n]
    t, v = doc.xref_get_key(page.xref, "VP")
    if t != "null" and v and "PhilPDF" not in (doc.xref_object(int(v.split()[0])) if t == "xref" else v):
        return False
    r = page.mediabox
    vp = (f"[<</Type/Viewport/Name(PhilPDF)/BBox[{r.x0:g} {r.y0:g} {r.x1:g} {r.y1:g}]"
          f"/Measure{dict_measure(e)}>>]")
    doc.xref_set_key(page.xref, "VP", vp)
    return True


def dict_measure(e):
    u = e["u"]
    return (f"<</Type/Measure/Subtype/RL/R{fitz.get_pdf_str(e.get('texte') or '')}"
            f"/X[<</Type/NumberFormat/U{fitz.get_pdf_str(u)}/C {e['c']:.10g}/D 100>>]"
            f"/D[<</Type/NumberFormat/U{fitz.get_pdf_str(u)}/C 1/D 100>>]"
            f"/A[<</Type/NumberFormat/U{fitz.get_pdf_str(u + '²')}/C 1/D 100>>]>>")


# ------------------------------------------------------------------ calculs
def longueur(points):
    return sum(math.dist(a, b) for a, b in zip(points, points[1:]))


def aire(points):
    """Aire d'un polygone (formule du lacet), en points² PDF."""
    s = 0.0
    for (x1, y1), (x2, y2) in zip(points, points[1:] + points[:1]):
        s += x1 * y2 - x2 * y1
    return abs(s) / 2


def centre(points):
    """Centre de gravite d'un polygone (repli : moyenne des sommets)."""
    a, cx, cy = 0.0, 0.0, 0.0
    for (x1, y1), (x2, y2) in zip(points, points[1:] + points[:1]):
        k = x1 * y2 - x2 * y1
        a += k
        cx += (x1 + x2) * k
        cy += (y1 + y2) * k
    if abs(a) < 1e-9:
        return (sum(p[0] for p in points) / len(points), sum(p[1] for p in points) / len(points))
    return (cx / (3 * a), cy / (3 * a))


def valeurs(genre, points, e):
    """{longueur, aire} reelles (unite de l'echelle, et son carre)."""
    if genre == "surface":
        return {"longueur": longueur(points + points[:1]) * e["c"], "aire": aire(points) * e["c"] ** 2}
    return {"longueur": longueur(points) * e["c"], "aire": None}


def nombre(x, dec=2):
    """12 345,67 (espace fine insecable pour les milliers, virgule decimale)."""
    s = f"{x:,.{dec}f}".replace(",", " ").replace(".", ",")
    return s


def texte_valeur(genre, v, unite):
    if genre == "surface":
        a = v["aire"]
        t = f"{nombre(a)} {unite}²"
        if unite == "m" and a >= 10000:
            t += f" ({nombre(a / 10000, 4)} ha)"
        return t
    return f"{nombre(v['longueur'])} {unite}"


def contraindre(a, b):
    """Maj : segment horizontal, vertical ou a 45°."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    ang = round(math.atan2(dy, dx) / (math.pi / 4)) * (math.pi / 4)
    d = math.hypot(dx, dy)
    return (a[0] + d * math.cos(ang), a[1] + d * math.sin(ang))


# ------------------------------------------------------------------ aimant (extremites des traits du plan)
class Aimant:
    """Points remarquables des traits vectoriels d'une page (extremites, coins), pour s'y accrocher."""

    def __init__(self, page, maxi=200000):
        self.grille, self.pas = {}, 8.0
        n = 0
        try:
            dessins = page.get_drawings()
        except Exception:
            dessins = []
        for d in dessins:
            for it in d.get("items", []):
                pts = []
                if it[0] == "l":
                    pts = [it[1], it[2]]
                elif it[0] == "c":
                    pts = [it[1], it[4]]
                elif it[0] == "re":
                    r = it[1]
                    pts = [r.tl, r.tr, r.bl, r.br]
                elif it[0] == "qu":
                    q = it[1]
                    pts = [q.ul, q.ur, q.ll, q.lr]
                for p in pts:
                    k = (int(p.x // self.pas), int(p.y // self.pas))
                    self.grille.setdefault(k, []).append((p.x, p.y))
                    n += 1
                if n > maxi:
                    return

    def proche(self, x, y, rayon):
        """Point le plus proche a moins de « rayon » points PDF, ou None."""
        meilleur, dmin = None, rayon
        r = int(rayon // self.pas) + 1
        kx, ky = int(x // self.pas), int(y // self.pas)
        for i in range(kx - r, kx + r + 1):
            for j in range(ky - r, ky + r + 1):
                for p in self.grille.get((i, j), ()):
                    d = math.dist(p, (x, y))
                    if d < dmin:
                        meilleur, dmin = p, d
        return meilleur


# ------------------------------------------------------------------ annotations
COULEURS = {"distance": (0.08, 0.38, 0.76), "perimetre": (0.55, 0.16, 0.65), "surface": (0.13, 0.52, 0.24)}
_IT = {"distance": "LineDimension", "perimetre": "PolyLineDimension", "surface": "PolygonDimension"}


def ecrire(doc, n, genre, points, e, nom=""):
    """Pose la mesure (annotation de mesure + etiquette). Renvoie (texte, identifiant)."""
    page = doc[n]
    v = valeurs(genre, points, e)
    valeur = texte_valeur(genre, v, e["u"])
    lib = f"{nom} : {valeur}" if nom else valeur
    contenu = lib
    if genre == "surface":
        contenu += f" (périmètre {nombre(v['longueur'])} {e['u']})"
    ident = "philpdf-mesure-" + uuid.uuid4().hex[:10]
    coul = COULEURS[genre]
    # les points viennent de l'ecran (page non tournee) ; l'annotation les veut dans l'espace de la page
    pts = [fitz.Point(p) for p in points]
    if genre == "distance":
        a = page.add_line_annot(pts[0], pts[-1])
        a.set_line_ends(fitz.PDF_ANNOT_LE_BUTT, fitz.PDF_ANNOT_LE_BUTT)
    elif genre == "perimetre":
        a = page.add_polyline_annot(pts)
    else:
        a = page.add_polygon_annot(pts)
        a.set_colors(stroke=coul, fill=tuple(1 - (1 - c) * 0.18 for c in coul))
        a.set_opacity(0.85)
    if genre != "surface":
        a.set_colors(stroke=coul)
    a.set_border(width=1.2)
    a.set_info(content=contenu, title="PhilPDF", subject={"distance": "Distance", "perimetre": "Périmètre",
                                                            "surface": "Surface"}[genre])
    a.set_name(ident)
    a.update()
    infos = {"genre": genre, "valeur": v, "unite": e["u"], "echelle": e.get("texte", ""), "c": e["c"], "nom": nom,
             "points": [list(map(float, p)) for p in points]}
    doc.xref_set_key(a.xref, "IT", "/" + _IT[genre])
    doc.xref_set_key(a.xref, "Measure", dict_measure(e))
    doc.xref_set_key(a.xref, "NM", fitz.get_pdf_str(ident))
    doc.xref_set_key(a.xref, CLE, fitz.get_pdf_str(json.dumps(infos, ensure_ascii=False)))
    _etiquette(doc, n, genre, points, lib, ident, coul)
    return contenu, ident


def _etiquette(doc, n, genre, points, lib, ident, coul):
    page = doc[n]
    taille = 9
    lt = fitz.get_text_length(lib, fontname="helv", fontsize=taille) + 8
    if genre == "surface":
        cx, cy = centre(points)
    elif genre == "distance":
        cx, cy = (points[0][0] + points[-1][0]) / 2, (points[0][1] + points[-1][1]) / 2 - 9
    else:
        i = len(points) // 2
        cx, cy = (points[i - 1][0] + points[i][0]) / 2, (points[i - 1][1] + points[i][1]) / 2 - 9
    r = fitz.Rect(cx - lt / 2, cy - 7, cx + lt / 2, cy + 7)
    if page.rotation in (90, 270):                # page tournee : le texte est tourne, la boite aussi
        r = fitz.Rect(cx - 7, cy - lt / 2, cx + 7, cy + lt / 2)
    t = page.add_freetext_annot(r, lib, fontsize=taille, fontname="helv", text_color=coul, fill_color=(1, 1, 1),
                                align=fitz.TEXT_ALIGN_CENTER, rotate=page.rotation)
    t.set_border(width=0)
    t.set_opacity(0.92)
    t.set_info(title="PhilPDF", subject="Mesure")
    t.update()
    doc.xref_set_key(t.xref, "NM", fitz.get_pdf_str(ident + "-etiquette"))
    doc.xref_set_key(t.xref, CLE + "_Etiquette", fitz.get_pdf_str(ident))
    return t


def _info(doc, a):
    t, v = doc.xref_get_key(a.xref, CLE)
    if t != "string":
        return None
    try:
        return json.loads(v)
    except ValueError:
        return None


def identifiant(doc, a):
    """Identifiant de la mesure a laquelle appartient l'annotation (mesure ou etiquette), ou None."""
    t, v = doc.xref_get_key(a.xref, CLE + "_Etiquette")
    if t == "string":
        return v
    if _info(doc, a) is not None:
        return a.info.get("name") or doc.xref_get_key(a.xref, "NM")[1]
    return None


def lister(doc):
    """Toutes les mesures du document : [{page, ident, genre, nom, texte, valeur, unite, echelle, xref}].
    Les mesures faites dans Acrobat (avec /Measure) sont reprises aussi, d'apres leur texte."""
    out = []
    for n, page in enumerate(doc):
        for a in page.annots():
            info = _info(doc, a)
            if info is not None:
                out.append({"page": n, "ident": identifiant(doc, a), "genre": info["genre"], "nom": info.get("nom", ""),
                            "texte": a.info.get("content", ""), "valeur": info["valeur"], "unite": info["unite"],
                            "echelle": info.get("echelle", ""), "xref": a.xref, "philpdf": True})
            elif doc.xref_get_key(a.xref, "Measure")[0] != "null":
                it = doc.xref_get_key(a.xref, "IT")[1]
                genre = {"/LineDimension": "distance", "/PolyLineDimension": "perimetre",
                         "/PolygonDimension": "surface"}.get(it, "distance")
                out.append({"page": n, "ident": None, "genre": genre, "nom": "", "texte": a.info.get("content", ""),
                            "valeur": None, "unite": "", "echelle": "", "xref": a.xref, "philpdf": False})
    return out


def supprimer(doc, n, ident):
    """Retire la mesure et son etiquette."""
    page = doc[n]
    for a in list(page.annots()):
        if identifiant(doc, a) == ident:
            page.delete_annot(a)


def renommer(doc, n, ident, nom):
    """Change le nom de la mesure (« Salon ») : etiquette et texte reecrits."""
    page = doc[n]
    mesure = next((a for a in page.annots() if _info(doc, a) and identifiant(doc, a) == ident), None)
    if mesure is None:
        return False
    info = _info(doc, mesure)
    valeur = texte_valeur(info["genre"], info["valeur"], info["unite"])
    lib = f"{nom} : {valeur}" if nom else valeur
    contenu = lib + (f" (périmètre {nombre(info['valeur']['longueur'])} {info['unite']})"
                     if info["genre"] == "surface" else "")
    info["nom"] = nom
    mesure.set_info(content=contenu)
    mesure.update()
    doc.xref_set_key(mesure.xref, CLE, fitz.get_pdf_str(json.dumps(info, ensure_ascii=False)))
    for a in list(page.annots()):
        if doc.xref_get_key(a.xref, CLE + "_Etiquette")[1] == ident:
            page.delete_annot(a)
    _etiquette(doc, n, info["genre"], [tuple(p) for p in info["points"]], lib, ident, COULEURS[info["genre"]])
    return True
