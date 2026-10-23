"""Traduction d'un PDF en gardant la mise en page.

Chaque paragraphe (bloc de texte) est repere avec sa position, sa taille, sa couleur et sa graisse ; les textes
sont traduits par lots (fonction fournie par l'appelant, l'IA en pratique) ; puis le texte d'origine est retire
(sans toucher aux images ni aux dessins) et la traduction est posee dans le meme cadre. Si elle est plus longue,
sa taille est reduite pour tenir dans le cadre.
"""
import html, re
import pymupdf as fitz


def _couleur(c):
    return "#%06x" % (c or 0)


def blocs(doc):
    """[{"page", "rect", "texte", "taille", "couleur", "gras", "italique"}] des paragraphes a traduire."""
    out = []
    for i, p in enumerate(doc):
        for b in p.get_text("dict", flags=fitz.TEXTFLAGS_TEXT)["blocks"]:
            if b.get("type") != 0:
                continue
            lignes, tailles, spans = [], [], []
            for l in b["lines"]:
                t = "".join(s["text"] for s in l["spans"])
                if t.strip():
                    lignes.append(t.strip())
                    spans += [s for s in l["spans"] if s["text"].strip()]
            if not lignes or not re.search(r"[^\W\d_]{2,}", " ".join(lignes)):
                continue                              # nombres, dates, codes seuls : on ne touche pas
            texte = ""
            for t in lignes:                          # recolle les mots coupes en fin de ligne
                if texte.endswith("-") and t[:1].islower():
                    texte = texte[:-1] + t
                else:
                    texte = (texte + " " + t).strip()
            tailles = sorted(s["size"] for s in spans)
            s0 = max(spans, key=lambda s: len(s["text"]))
            out.append({"page": i, "rect": fitz.Rect(b["bbox"]), "texte": texte, "taille": tailles[len(tailles) // 2],
                        "couleur": _couleur(s0.get("color")), "gras": bool(s0["flags"] & 16) or "Bold" in s0["font"],
                        "italique": bool(s0["flags"] & 2), "lignes": len(lignes)})
    return out


def lots(textes, max_car=6000):
    """Decoupe la liste des textes en lots d'indices pour les envois a l'IA."""
    lot, n = [], 0
    for i, t in enumerate(textes):
        if lot and n + len(t) > max_car:
            yield lot
            lot, n = [], 0
        lot.append(i)
        n += len(t)
    if lot:
        yield lot


def appliquer(doc, bs, traductions):
    """Remplace le texte de chaque bloc par sa traduction (doc modifie en place)."""
    par_page = {}
    for b, t in zip(bs, traductions):
        if t and t.strip() and t.strip() != b["texte"]:
            par_page.setdefault(b["page"], []).append((b, t.strip()))
    for i, liste in par_page.items():
        p = doc[i]
        for b, _t in liste:
            p.add_redact_annot(b["rect"], fill=False)
        p.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE, graphics=fitz.PDF_REDACT_LINE_ART_NONE,
                           text=fitz.PDF_REDACT_TEXT_REMOVE)
        for b, t in liste:
            r = fitz.Rect(b["rect"])
            r.x1 += 2                                  # un peu d'air : la police de remplacement est plus large
            style = (f"font-family: sans-serif; font-size: {b['taille']:.1f}px; color: {b['couleur']};"
                     f"{' font-weight: bold;' if b['gras'] else ''}{' font-style: italic;' if b['italique'] else ''}"
                     " line-height: 1.15; margin: 0; padding: 0;")
            p.insert_htmlbox(r, f"<p style='{style}'>{html.escape(t)}</p>", scale_low=0)
    return sum(len(v) for v in par_page.values())
