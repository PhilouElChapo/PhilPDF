"""Apparence des champs texte et listes dans LEUR police : PyMuPDF ne sait dessiner un champ qu'en Helvetica,
Courier ou Times, et remplace toute autre police (une police manuscrite du formulaire, Helvetica gras...) par
Helvetica. Ici on dessine nous-memes le texte avec la police des ressources du formulaire (/AcroForm/DR), comme
Acrobat, a la taille et dans la couleur du champ, aligne et coupe en lignes."""
import logging
import re

import pymupdf as fitz

logging.getLogger("fontTools").setLevel(logging.ERROR)

# polices standard proposees : nom de ressource -> (police PostScript, police PyMuPDF pour mesurer)
STANDARD = {"Helv": ("Helvetica", "helv"), "HeBo": ("Helvetica-Bold", "hebo"), "HeOb": ("Helvetica-Oblique", "heit"),
            "TiRo": ("Times-Roman", "tiro"), "TiBo": ("Times-Bold", "tibo"), "TiIt": ("Times-Italic", "tiit"),
            "Cour": ("Courier", "cour"), "CoBo": ("Courier-Bold", "cobo")}
PYMUPDF = ("Helv", "Cour", "TiRo")         # celles que PyMuPDF dessine lui-meme


def _acroform(doc):
    cat = doc.pdf_catalog()
    t, v = doc.xref_get_key(cat, "AcroForm")
    if t == "xref":
        return int(v.split()[0]), ""
    return cat, "AcroForm/"


def polices_formulaire(doc):
    """{nom de ressource: xref} des polices du formulaire (/AcroForm/DR/Font)."""
    ax, pre = _acroform(doc)
    t, v = doc.xref_get_key(ax, pre + "DR/Font")
    if t == "xref":
        v = doc.xref_object(int(v.split()[0]), compressed=True)
    elif t != "dict":
        return {}
    return {n: int(x) for n, x in re.findall(r"/([^\s/<>\[\]()]+)\s+(\d+)\s+0\s+R", v)}


def assurer_police(doc, nom):
    """La police « nom » existe dans les ressources du formulaire (ajoutee si c'est une police standard).
    Renvoie son xref, ou None."""
    pol = polices_formulaire(doc)
    if nom in pol:
        return pol[nom]
    if nom not in STANDARD:
        return None
    x = doc.get_new_xref()
    doc.update_object(x, f"<</Type/Font/Subtype/Type1/BaseFont/{STANDARD[nom][0]}/Encoding/WinAnsiEncoding>>")
    ax, pre = _acroform(doc)
    t, v = doc.xref_get_key(ax, pre + "DR/Font")
    if t == "xref":
        doc.xref_set_key(int(v.split()[0]), nom, f"{x} 0 R")
    elif t == "dict":
        doc.xref_set_key(ax, pre + "DR/Font/" + nom, f"{x} 0 R")
    else:
        if doc.xref_get_key(ax, pre + "DR")[0] == "null":
            doc.xref_set_key(ax, pre + "DR", "<<>>")
        doc.xref_set_key(ax, pre + "DR/Font", f"<</{nom} {x} 0 R>>")
    return x


def lire_da(doc, w):
    """(police, taille, couleur) du /DA du champ (ou du formulaire)."""
    da = doc.xref_get_key(w.xref, "DA")[1]
    if not da or da == "null":
        tp, par = doc.xref_get_key(w.xref, "Parent")
        if tp == "xref":
            da = doc.xref_get_key(int(par.split()[0]), "DA")[1]
    if not da or da == "null":
        ax, pre = _acroform(doc)
        da = doc.xref_get_key(ax, pre + "DA")[1] or ""
    m = re.search(r"/([^\s/]+)\s+([\d.]+)\s+Tf", da or "")
    police, taille = (m.group(1), float(m.group(2))) if m else ("Helv", 0.0)
    c = re.search(r"([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+rg", da or "")
    g = re.search(r"(?<![\d.])([\d.]+)\s+g\b", da or "")
    couleur = tuple(float(x) for x in c.groups()) if c else ((float(g.group(1)),) * 3 if g else (0, 0, 0))
    return police, taille, couleur


def ecrire_da(doc, w, police, taille, couleur):
    da = f"/{police} {taille:g} Tf {couleur[0]:g} {couleur[1]:g} {couleur[2]:g} rg"
    doc.xref_set_key(w.xref, "DA", fitz.get_pdf_str(da))


def _mesureur(doc, police):
    if police in STANDARD:
        return fitz.Font(STANDARD[police][1])
    x = polices_formulaire(doc).get(police)
    if x:
        dx = doc.xref_get_key(x, "FontDescriptor")[1]
        if dx.endswith("R"):
            for k in ("FontFile2", "FontFile3", "FontFile"):
                t, v = doc.xref_get_key(int(dx.split()[0]), k)
                if t == "xref":
                    try:
                        return fitz.Font(fontbuffer=doc.xref_stream(int(v.split()[0])))
                    except Exception:
                        break
    return fitz.Font("helv")


def _chaine(texte):
    """Texte -> chaine PDF en WinAnsi (les caracteres absents deviennent « ? »)."""
    b = texte.encode("cp1252", errors="replace")
    return "(" + b.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)").decode("latin-1") + ")"


def _lignes(texte, mes, taille, largeur, multi):
    if not multi:
        return [texte.replace("\n", " ")]
    out = []
    for para in texte.split("\n"):
        mots, cour = para.split(" "), ""
        for m in mots:
            essai = (cour + " " + m).strip() if cour else m
            if cour and mes.text_length(essai, fontsize=taille) > largeur:
                out.append(cour)
                cour = m
            else:
                cour = essai
        out.append(cour)
    return out


def dessiner(doc, w, valeur=None):
    """Apparence du champ texte (ou liste deroulante) dans sa police, sa taille et sa couleur. True si dessine."""
    police, taille, couleur = lire_da(doc, w)
    fx = assurer_police(doc, police)
    if fx is None:
        return False
    texte = w.field_value if valeur is None else valeur
    if isinstance(texte, (list, tuple)):
        texte = ", ".join(map(str, texte))
    texte = "" if texte in (None, "Off") else str(texte)
    r = w.rect
    lw, lh = r.width, r.height
    multi = bool(w.field_flags & fitz.PDF_TX_FIELD_IS_MULTILINE) if w.field_type == fitz.PDF_WIDGET_TYPE_TEXT else False
    mes = _mesureur(doc, police)
    marge = 2
    t = taille
    if not t:                                        # taille automatique : tient dans le champ
        t = min(12.0, max(4.0, (lh - 2 * marge) * 0.78)) if multi else max(4.0, (lh - 2 * marge) * 0.72)
        if not multi and texte:
            t = min(t, max(4.0, (lw - 2 * marge) / max(1e-6, mes.text_length(texte, fontsize=1))))
    q = doc.xref_get_key(w.xref, "Q")[1]
    try:
        align = int(q) if q not in ("null", "") else 0
    except ValueError:
        align = 0
    asc, desc = (mes.ascender or 0.8), (mes.descender or -0.2)
    lignes = _lignes(texte, mes, t, lw - 2 * marge, multi)
    corps = [f"{couleur[0]:g} {couleur[1]:g} {couleur[2]:g} rg"]
    pas = t * 1.15
    if multi:
        y = lh - marge - t * asc
    else:
        y = (lh - t * (asc - desc)) / 2 - t * desc
    for l in lignes:
        lt = mes.text_length(l, fontsize=t)
        x = marge if align == 0 else (lw - lt) / 2 if align == 1 else lw - marge - lt
        corps.append(f"BT /{police} {t:.2f} Tf {x:.2f} {y:.2f} Td {_chaine(l)} Tj ET")
        y -= pas
    flux = ("/Tx BMC q 1 1 %.2f %.2f re W n " % (lw - 2, lh - 2) + " ".join(corps) + " Q EMC").encode("latin-1")
    t_ap, v_ap = doc.xref_get_key(w.xref, "AP/N")
    if t_ap == "xref":
        ax = int(v_ap.split()[0])
    else:
        ax = doc.get_new_xref()
        doc.update_object(ax, "<<>>")
        doc.xref_set_key(w.xref, "AP", f"<</N {ax} 0 R>>")
    doc.update_object(ax, f"<</Type/XObject/Subtype/Form/BBox[0 0 {lw:.2f} {lh:.2f}]"
                          f"/Resources<</Font<</{police} {fx} 0 R>>>>>>")
    doc.update_stream(ax, flux, compress=True)
    return True


# ------------------------------------------------------------------ polices du systeme
_SYSTEME = None


def polices_systeme():
    """[(nom, chemin)] des polices TrueType / OpenType installees sur ce PC (une par fichier), triees par nom."""
    global _SYSTEME
    if _SYSTEME is not None:
        return _SYSTEME
    import os
    import sys
    vus, out = set(), []

    def ajouter(nom, chemin):
        if chemin.lower().endswith((".ttf", ".otf")) and os.path.exists(chemin):
            k = os.path.normcase(chemin)
            if k not in vus:
                vus.add(k)
                out.append((nom, chemin))
    if sys.platform == "win32":
        try:
            import winreg
            racine = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
            for ruche, cle in ((winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"),
                               (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts")):
                try:
                    k = winreg.OpenKey(ruche, cle)
                except OSError:
                    continue
                i = 0
                while True:
                    try:
                        nom, fichier, _t = winreg.EnumValue(k, i)
                    except OSError:
                        break
                    i += 1
                    nom = re.sub(r"\s*\((TrueType|OpenType)\)\s*$", "", nom)
                    if " & " in nom:
                        continue
                    ajouter(nom, fichier if os.path.isabs(fichier) else os.path.join(racine, fichier))
        except Exception:
            pass
    else:
        import subprocess
        try:
            r = subprocess.run(["fc-list", "--format", "%{file}\t%{fullname}\n"], capture_output=True, text=True,
                               timeout=20)
            for l in r.stdout.splitlines():
                f, _s, n = l.partition("\t")
                ajouter(n.split(",")[0] or os.path.basename(f)[:-4], f)
        except Exception:
            pass
    out.sort(key=lambda x: x[0].lower())
    _SYSTEME = out
    return out


def _nom_ressource(nom):
    return "PP" + re.sub(r"[^A-Za-z0-9]", "", nom)[:28]


def ajouter_police_fichier(doc, chemin):
    """Integre une police du PC dans le formulaire (reduite aux lettres du clavier). Renvoie son nom de ressource."""
    import io
    font = fitz.Font(fontfile=chemin)
    nom_ps = re.sub(r"[^A-Za-z0-9+-]", "", font.name) or "Police"
    res = _nom_ressource(font.name)
    if res in polices_formulaire(doc):
        return res
    with open(chemin, "rb") as h:
        programme = h.read()
    cff = programme[:4] == b"OTTO"
    try:
        from fontTools.ttLib import TTFont
        from fontTools import subset
        t = TTFont(io.BytesIO(programme))
        o = subset.Options()
        o.name_IDs = ["*"]
        o.notdef_outline = True
        o.drop_tables += ["GSUB", "GPOS", "DSIG"]
        o.layout_features = []
        sub = subset.Subsetter(o)
        sub.populate(text=bytes(range(32, 256)).decode("cp1252", errors="ignore") + "œŒ€’“”…–—«»•")
        sub.subset(t)
        out = io.BytesIO()
        t.save(out)
        programme = out.getvalue()
    except Exception:
        pass
    larg = []
    for c in range(32, 256):
        try:
            u = bytes([c]).decode("cp1252")
        except UnicodeDecodeError:
            u = " "
        larg.append(round(font.glyph_advance(ord(u)) * 1000))
    ff = doc.get_new_xref()
    doc.update_object(ff, "<</Subtype/OpenType>>" if cff else f"<</Length1 {len(programme)}>>")
    doc.update_stream(ff, programme, compress=True)
    b = font.bbox
    dx = doc.get_new_xref()
    doc.update_object(dx, f"<</Type/FontDescriptor/FontName/{nom_ps}/Flags 32"
                          f"/FontBBox[{round(b.x0 * 1000)} {round(b.y0 * 1000)} {round(b.x1 * 1000)} {round(b.y1 * 1000)}]"
                          f"/ItalicAngle 0/Ascent {round(font.ascender * 1000)}/Descent {round(font.descender * 1000)}"
                          f"/CapHeight 700/StemV 80/{'FontFile3' if cff else 'FontFile2'} {ff} 0 R>>")
    fx = doc.get_new_xref()
    doc.update_object(fx, f"<</Type/Font/Subtype/{'Type1' if cff else 'TrueType'}/BaseFont/{nom_ps}"
                          f"/FirstChar 32/LastChar 255/Widths[{' '.join(map(str, larg))}]"
                          f"/Encoding/WinAnsiEncoding/FontDescriptor {dx} 0 R>>")
    ax, pre = _acroform(doc)
    t, v = doc.xref_get_key(ax, pre + "DR/Font")
    if t == "xref":
        doc.xref_set_key(int(v.split()[0]), res, f"{fx} 0 R")
    elif t == "dict":
        doc.xref_set_key(ax, pre + "DR/Font/" + res, f"{fx} 0 R")
    else:
        if doc.xref_get_key(ax, pre + "DR")[0] == "null":
            doc.xref_set_key(ax, pre + "DR", "<<>>")
        doc.xref_set_key(ax, pre + "DR/Font", f"<</{res} {fx} 0 R>>")
    return res


def programme_police(doc, nom):
    """Octets du programme de la police « nom » des ressources du formulaire (pour l'afficher), ou None."""
    x = polices_formulaire(doc).get(nom)
    if not x:
        return None
    dx = doc.xref_get_key(x, "FontDescriptor")[1]
    if not dx.endswith("R"):
        return None
    for k in ("FontFile2", "FontFile3", "FontFile"):
        t, v = doc.xref_get_key(int(dx.split()[0]), k)
        if t == "xref":
            return doc.xref_stream(int(v.split()[0]))
    return None
