"""Dessins vectoriels de la page (illustrations, schemas, logos traces) traites comme des objets, comme Acrobat :
on peut en choisir un, le deplacer, l'agrandir, le tourner ou le supprimer.

Un « dessin » est un groupe de traces voisins (regroupes par le moteur). Pour le deplacer ou le tourner, ses traces
sont relus (forme, couleurs, epaisseur, transparence), effaces de la page, puis redessines a la nouvelle place.
Le reste de la page (texte, images, autres dessins) n'est pas touche.
"""
import math

import pymupdf as fitz

MARGE = 1.0


def groupes(page):
    """Cadres des dessins de la page : ni les tout petits traits, ni les fonds qui couvrent presque toute la page."""
    try:
        cadres = page.cluster_drawings()
    except Exception:                                  # noqa: BLE001
        return []
    aire = page.rect.width * page.rect.height
    out = []
    for r in cadres:
        r = fitz.Rect(r)
        if r.width < 4 and r.height < 4:
            continue
        if r.width * r.height > 0.6 * aire:
            continue
        out.append(r)
    return out


def chemins(page, cadre):
    """Traces entierement dans le cadre du dessin."""
    z = fitz.Rect(cadre) + (-MARGE, -MARGE, MARGE, MARGE)
    return [d for d in page.get_drawings() if fitz.Rect(d["rect"]) in z]


def _effacer(page, cadre):
    """Efface les traces du dessin. Le moteur n'efface que les traces entierement couverts par la zone (epaisseur
    du trait comprise) : la zone est elargie autant que possible sans couvrir entierement un autre trace."""
    c = fitz.Rect(cadre)
    a_moi = chemins(page, c)
    autres = [fitz.Rect(d["rect"]) for d in page.get_drawings() if d not in a_moi]
    marge = MARGE
    for m in (3.0, 6.0, 10.0):
        z = c + (-m, -m, m, m)
        if any(r in z for r in autres):
            break
        marge = m
    page.add_redact_annot(c + (-marge, -marge, marge, marge))
    page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE, text=fitz.PDF_REDACT_TEXT_NONE,
                          graphics=fitz.PDF_REDACT_LINE_ART_REMOVE_IF_COVERED)


def _transparence_formes(page):
    """[(cadre, ca, CA)] des sous-objets de la page peints avec une transparence (« /Gs4 gs /Fm4 Do ») : le moteur
    ne la compte pas dans les traces qu'il relit, il faut la reporter sur les traces redessinees."""
    import re
    doc = page.parent
    out = []
    try:
        flux = "\n".join((doc.xref_stream(c) or b"").decode("latin-1") for c in page.get_contents())
        t, v = doc.xref_get_key(page.xref, "Resources")
        res = int(v.split()[0]) if t == "xref" else None
        for x, nom, invoquant, bb in page.get_xobjects():
            if invoquant != 0:
                continue
            m = re.search(r"/" + re.escape(nom) + r"\s+Do", flux)
            if not m:
                continue
            avant = flux[:m.start()]
            avant = avant[avant.rfind(" q") + 1 if " q" in avant else 0:]
            g = re.findall(r"/([^\s/\[\]<>()]+)\s+gs", avant)
            if not g:
                continue
            cle = f"Resources/ExtGState/{g[-1]}" if res is None else f"ExtGState/{g[-1]}"
            tg, vg = doc.xref_get_key(page.xref if res is None else res, cle)
            if tg != "xref":
                continue
            gx = int(vg.split()[0])
            ca = doc.xref_get_key(gx, "ca")
            ce = doc.xref_get_key(gx, "CA")
            ca = float(ca[1]) if ca[0] in ("float", "int") else 1.0
            ce = float(ce[1]) if ce[0] in ("float", "int") else 1.0
            if ca < 1 or ce < 1:
                out.append((fitz.Rect(bb) * page.transformation_matrix, ca, ce))
    except Exception:                                  # noqa: BLE001
        pass
    return out


def _redessiner(page, traces, m, transparences=()):
    """Redessine les traces, chaque point passe par la matrice m (deplacement, taille, rotation)."""
    k = math.sqrt(abs(m.a * m.d - m.b * m.c)) or 1.0
    sh = page.new_shape()
    for d in traces:
        fo = d.get("fill_opacity") if d.get("fill_opacity") is not None else 1
        so = d.get("stroke_opacity") if d.get("stroke_opacity") is not None else 1
        for cadre, ca, ce in transparences:
            if fitz.Rect(d["rect"]) in cadre + (-MARGE, -MARGE, MARGE, MARGE):
                fo, so = fo * ca, so * ce
        for it in d["items"]:
            op = it[0]
            if op == "l":
                sh.draw_line(fitz.Point(it[1]) * m, fitz.Point(it[2]) * m)
            elif op == "c":
                sh.draw_bezier(*(fitz.Point(p) * m for p in it[1:5]))
            elif op == "re":
                sh.draw_quad(fitz.Rect(it[1]).quad * m)
            elif op == "qu":
                sh.draw_quad(fitz.Quad(it[1]) * m)
        largeur = (d.get("width") or 0) * k
        # le moteur ne rend pas le sens de parcours des rectangles : un rectangle pose dans un autre du meme trace
        # est un trou (fenetres d'un cadre) ; la regle pair-impair les garde vides
        rects = [fitz.Rect(it[1]) for it in d["items"] if it[0] == "re"]
        trous = any(a != b and a in b for a in rects for b in rects)
        sh.finish(fill=d.get("fill"), color=d.get("color"), width=largeur if d.get("color") else 0,
                  even_odd=bool(d.get("even_odd")) or trous, closePath=bool(d.get("closePath")),
                  fill_opacity=fo, stroke_opacity=so,
                  lineCap=max(d.get("lineCap") or (0,)) if isinstance(d.get("lineCap"), (tuple, list)) else (d.get("lineCap") or 0),
                  lineJoin=d.get("lineJoin") or 0, dashes=d.get("dashes") or None)
    sh.commit()


def transformer(page, cadre, m):
    """Deplace / agrandit / tourne le dessin (matrice m, en coordonnees de la page). Renvoie son nouveau cadre."""
    traces = chemins(page, cadre)
    if not traces:
        raise ValueError("Dessin introuvable à cet endroit")
    transparences = _transparence_formes(page)
    _effacer(page, cadre)
    _redessiner(page, traces, m, transparences)
    return fitz.Rect(cadre).quad.transform(m).rect if hasattr(fitz.Quad, "transform") else (fitz.Rect(cadre).quad * m).rect


def deplacer(page, cadre, nouveau):
    """Le dessin occupe le cadre `nouveau` (deplace et/ou agrandi)."""
    a, b = fitz.Rect(cadre), fitz.Rect(nouveau)
    sx, sy = b.width / max(a.width, 0.01), b.height / max(a.height, 0.01)
    m = fitz.Matrix(1, 0, 0, 1, -a.x0, -a.y0) * fitz.Matrix(sx, 0, 0, sy, 0, 0) * fitz.Matrix(1, 0, 0, 1, b.x0, b.y0)
    return transformer(page, cadre, m)


def tourner(page, cadre, delta):
    """Tourne le dessin autour de son centre ; delta en degres, sens inverse des aiguilles d'une montre."""
    c = fitz.Rect(cadre)
    cx, cy = (c.x0 + c.x1) / 2, (c.y0 + c.y1) / 2
    a = math.radians(delta)
    # page : y vers le bas ; sens inverse des aiguilles a l'ecran
    rot = fitz.Matrix(math.cos(a), -math.sin(a), math.sin(a), math.cos(a), 0, 0)
    m = fitz.Matrix(1, 0, 0, 1, -cx, -cy) * rot * fitz.Matrix(1, 0, 0, 1, cx, cy)
    return transformer(page, cadre, m)


def retourner(page, cadre, horizontal=True):
    c = fitz.Rect(cadre)
    cx, cy = (c.x0 + c.x1) / 2, (c.y0 + c.y1) / 2
    f = fitz.Matrix(-1, 0, 0, 1, 0, 0) if horizontal else fitz.Matrix(1, 0, 0, -1, 0, 0)
    m = fitz.Matrix(1, 0, 0, 1, -cx, -cy) * f * fitz.Matrix(1, 0, 0, 1, cx, cy)
    return transformer(page, cadre, m)


def supprimer(page, cadre):
    if not chemins(page, cadre):
        raise ValueError("Dessin introuvable à cet endroit")
    _effacer(page, cadre)
