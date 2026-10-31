"""Autre methode pour modifier un paragraphe (celle de PhilPDF Android), proposee en secours par le bouton « ↻ »
quand le resultat de la methode habituelle ne convient pas.

 - Seules les lettres des lignes du paragraphe sont retirees (caviardage « texte seul ») : fond, cadres, traits
   et images restent, rien n'est decale ni redistribue.
 - Chaque ligne tapee est ecrite a la place de l'ancienne ligne (meme depart, meme ligne de base), avec la police
   d'origine du PDF, retrouvee par sa table ToUnicode (ou WinAnsi), quand elle a toutes les lettres ; sinon la
   police standard la plus proche (Helvetica, Times, Courier ; gras, italique).
"""
import re
import pymupdf as fitz

EQUIV = {" ": "\xa0", "\xa0": " ", "'": "’", "’": "'", "-": "‐", "‐": "-",
         '"': "”", "“": '"', "”": '"'}


def _hex(s):
    return bytes.fromhex(s)


def table_police(doc, xref):
    """{'n': octets par code, 'rev': {lettre: code}, 'w': {code: largeur/1000}, 'dw'} ou None."""
    t = doc.xref_get_key(xref, "Subtype")[1]
    n, w, dw = 1, {}, 1000.0
    if t == "/Type0":
        if doc.xref_get_key(xref, "Encoding")[1] != "/Identity-H":
            return None
        n = 2
        m = re.search(r"(\d+) 0 R", doc.xref_get_key(xref, "DescendantFonts")[1])
        if not m:
            return None
        dx = int(m.group(1))
        dwv = doc.xref_get_key(dx, "DW")
        if dwv[0] in ("int", "real"):
            dw = float(dwv[1])
        W = doc.xref_get_key(dx, "W")
        txt = doc.xref_object(int(W[1].split()[0])) if W[0] == "xref" else W[1]
        tok = re.findall(r"\[|\]|[-\d.]+", txt or "")
        if tok and tok[0] == "[" and tok[-1] == "]":
            tok = tok[1:-1]
        i = 0
        while i < len(tok):
            c0 = int(float(tok[i]))
            if i + 1 < len(tok) and tok[i + 1] == "[":
                j, c = i + 2, c0
                while j < len(tok) and tok[j] != "]":
                    w[c] = float(tok[j])
                    c, j = c + 1, j + 1
                i = j + 1
            elif i + 2 < len(tok):
                for c in range(c0, int(float(tok[i + 1])) + 1):
                    w[c] = float(tok[i + 2])
                i += 3
            else:
                break
    else:
        fc = doc.xref_get_key(xref, "FirstChar")
        ws = doc.xref_get_key(xref, "Widths")
        if fc[0] == "int" and ws[0] in ("array", "xref"):
            txt = ws[1] if ws[0] == "array" else doc.xref_object(int(ws[1].split()[0]))
            for k, v in enumerate(re.findall(r"[-\d.]+", txt)):
                w[int(fc[1]) + k] = float(v)
    rev = {}
    tu = doc.xref_get_key(xref, "ToUnicode")
    if tu[0] == "xref":
        cm = doc.xref_stream(int(tu[1].split()[0])).decode("latin-1")
        for bloc in re.findall(r"beginbfchar(.*?)endbfchar", cm, re.S):
            for s, d in re.findall(r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]*)>", bloc):
                u = _hex(d).decode("utf-16-be", "ignore")
                if len(u) == 1:
                    rev.setdefault(u, int(s, 16))
        for bloc in re.findall(r"beginbfrange(.*?)endbfrange", cm, re.S):
            for lo, hi, d in re.findall(r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*(<[0-9A-Fa-f]*>|\[[^\]]*\])", bloc):
                lo, hi = int(lo, 16), int(hi, 16)
                if d.startswith("<"):
                    base = int(d[1:-1], 16)
                    for k in range(min(hi - lo, 4096) + 1):
                        rev.setdefault(chr(base + k), lo + k)
                else:
                    for k, x in enumerate(re.findall(r"<([0-9A-Fa-f]*)>", d)):
                        u = _hex(x).decode("utf-16-be", "ignore")
                        if len(u) == 1:
                            rev.setdefault(u, lo + k)
    elif n == 1:
        enc = doc.xref_get_key(xref, "Encoding")
        txt = doc.xref_object(int(enc[1].split()[0])) if enc[0] == "xref" else (enc[1] or "")
        m = re.search(r"/Differences\s*\[(.*?)\]", txt, re.S)
        if m:                                             # noms de glyphes (/A /eacute /zero...) : polices OCR-B, Type3
            from .noms_glyphes import differences
            for code, ch in differences(m.group(1)).items():
                rev.setdefault(ch, code)
            return {"n": n, "rev": rev, "w": w, "dw": dw} if rev else None
        if enc[1] == "/WinAnsiEncoding":
            for c in range(32, 256):
                try:
                    rev.setdefault(bytes([c]).decode("cp1252"), c)
                except UnicodeDecodeError:
                    pass
        else:                                             # StandardEncoding : seulement l'ASCII commun
            for c in range(32, 127):
                if c not in (0x27, 0x60):
                    rev.setdefault(chr(c), c)
    return {"n": n, "rev": rev, "w": w, "dw": dw} if rev else None


def _code(T, ch):
    for x in (ch, EQUIV.get(ch, "")):
        if x and x in T["rev"]:
            return T["rev"][x]
    return None


def _largeur(T, texte, taille):
    if not T["w"]:
        return None
    return sum(T["w"].get(_code(T, c), T["dw"]) for c in texte) * taille / 1000


def police_de_ligne(doc, page, ligne):
    """(xref, nom de ressource, table) de la police qui a ecrit cette ligne, ou (None, None, None)."""
    spans = [sp for c, sp in ligne["chars"] if c["c"].strip()]
    if not spans:
        return None, None, None
    sp = spans[0]
    texte = ligne["texte"]
    meilleur, ecart = (None, None, None), 1e9
    for x in page.get_fonts(full=True):
        xref, refname, base = x[0], x[4], x[3].split("+", 1)[-1]
        T = table_police(doc, xref)
        if not T or any(_code(T, c) is None for c in texte):
            continue
        lw = _largeur(T, texte, ligne["taille"])
        e = abs(lw - (ligne["x1"] - ligne["x0"])) if lw is not None else 50
        f = sp["font"] or ""
        if f and (base == f or f == f"Type3 ({xref} 0 R)" or (len(f) >= 24 and base.startswith(f))):
            e -= 40                                       # meme nom (MuPDF tronque les noms longs)
        elif f and base and (base.startswith(f) or f.startswith(base)):
            e -= 15                                       # meme famille (Helvetica / Helvetica-Bold : pas le meme)
        elif f:
            continue                                      # une autre police de la page : jamais (sinon secours)
        if e < ecart:
            meilleur, ecart = (xref, refname, T), e
    return meilleur


def _secours(span, gras=None, italique=None):
    f = span.get("flags", 0)
    g = bool(f & 16) if gras is None else gras
    i = bool(f & 2) if italique is None else italique
    fam = "cour" if f & 8 else "tiro" if f & 4 else "helv"
    return {("helv", 0, 0): "helv", ("helv", 1, 0): "hebo", ("helv", 0, 1): "heit", ("helv", 1, 1): "hebi",
            ("tiro", 0, 0): "tiro", ("tiro", 1, 0): "tibo", ("tiro", 0, 1): "tiit", ("tiro", 1, 1): "tibi",
            ("cour", 0, 0): "cour", ("cour", 1, 0): "cobo", ("cour", 0, 1): "coit", ("cour", 1, 1): "cobi"}[(fam, int(g), int(i))]


def reecrire(doc, num_page, para, texte, taille=None, couleur=None):
    """Remplace les lignes du paragraphe par celles du texte. Renvoie {'originale': bool, 'police': nom, 'journal'}."""
    page = doc[num_page]
    lignes = para["lignes"]
    nouvelles = texte.split("\n")
    infos = [police_de_ligne(doc, page, l) for l in lignes]
    l0 = lignes[0]
    sp0 = next(sp for c, sp in l0["chars"] if c["c"].strip())
    t0 = taille or l0["taille"]
    coul = couleur or fitz.sRGB_to_pdf(sp0.get("color", 0))
    # 1. retirer seulement les lettres (fond, cadres, images gardes)
    for l in lignes:
        r = fitz.Rect(l["rect"])
        h = r.height * 0.15
        page.add_redact_annot(fitz.Rect(r.x0, r.y0 + h, r.x1, r.y1 - h), fill=False)
    page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE, graphics=fitz.PDF_REDACT_LINE_ART_NONE,
                          text=fitz.PDF_REDACT_TEXT_REMOVE)
    page = doc[num_page]
    # 2. ecrire chaque ligne a sa place
    interligne = para.get("interligne") or t0 * 1.2
    inv = ~page.transformation_matrix
    flux, journal, toutes_origine, nom = [], [], True, ""
    page.wrap_contents()
    for i, s in enumerate(nouvelles):
        if not s.strip():
            continue
        ref = lignes[i] if i < len(lignes) else None
        info = infos[i] if i < len(infos) else infos[-1]
        base = ref["base"] if ref else lignes[-1]["base"] + interligne * (i - len(lignes) + 1)
        x = ref["x0"] if ref else l0["x0"]
        xref, refname, T = info
        if T and all(_code(T, c) is not None for c in s):
            # le caviardage reecrit les ressources de la page : la police est rattachee sous un nom a nous
            refname = f"PhilA{xref}"
            doc.xref_set_key(page.xref, f"Resources/Font/{refname}", f"{xref} 0 R")
            code = b"".join(_code(T, c).to_bytes(T["n"], "big") for c in s).hex().upper()
            o = fitz.Point(x, base) * inv
            flux.append(f"BT /{refname} {t0:.3f} Tf {coul[0]:.3f} {coul[1]:.3f} {coul[2]:.3f} rg "
                        f"{inv.a:.4f} {inv.b:.4f} {-inv.c:.4f} {-inv.d:.4f} {o.x:.3f} {o.y:.3f} Tm <{code}> Tj ET")
            nom = nom or doc.xref_get_key(xref, "BaseFont")[1].lstrip("/").split("+")[-1]
        else:
            toutes_origine = False
            spr = next((sp for c, sp in (ref or l0)["chars"] if c["c"].strip()), sp0)
            fn = _secours(spr)
            page.insert_text((x, base), s, fontname=fn, fontsize=t0, color=coul)
            manque = sorted({c for c in s if not T or _code(T, c) is None})
            journal.append(f"ligne {i + 1} : police de remplacement ({fn})" + (f", lettres absentes : {' '.join(manque)}" if T else ""))
    if flux:
        x = doc.get_new_xref()
        doc.update_object(x, "<<>>")
        doc.update_stream(x, ("q\n" + "\n".join(flux) + "\nQ\n").encode())
        c = doc.xref_get_key(page.xref, "Contents")
        arr = c[1] if c[0] == "array" else f"[{c[1]}]"
        doc.xref_set_key(page.xref, "Contents", arr[:-1].rstrip() + f" {x} 0 R]")
    return {"originale": toutes_origine, "police": nom, "journal": journal}
