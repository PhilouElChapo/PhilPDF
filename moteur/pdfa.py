"""PDF/A-2b : le format d'archivage demande par les administrations (norme ISO 19005-2, niveau « b » : l'aspect du
document est garanti a l'identique dans le temps).

Ce que la conversion fait :
- toutes les polices integrees : celles qui ne le sont pas (Helvetica, Arial, Times, Courier...) recoivent une police
  aux memes largeurs (Liberation), les cases a cocher dessinees en ZapfDingbats sont redessinees en traits ;
- profil de couleurs sRGB (OutputIntent) ;
- metadonnees XMP coherentes avec le dictionnaire Info, identifiant PDF/A ;
- retire ce que la norme interdit : JavaScript et actions automatiques, fichiers joints, chiffrement,
  compression LZW, annotations sans apparence ou invisibles a l'impression.
La verification relit le resultat regle par regle et dit ce qui reste.
"""
import datetime
import os
import re

import logging

import pymupdf as fitz

from . import metadonnees as MD

logging.getLogger("fontTools").setLevel(logging.ERROR)

_POLICES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fonts")


def _dossier_polices():
    import sys
    for d in ([os.path.join(sys._MEIPASS, "fonts")] if getattr(sys, "_MEIPASS", None) else []) + [_POLICES]:
        if os.path.isdir(d):
            return d
    return _POLICES


def _remplacante(nom):
    """Police libre aux memes largeurs que la police d'origine (Liberation = Arial / Times / Courier)."""
    n = (nom or "").split("+")[-1].lower().replace(" ", "").replace("-", "").replace(",", "")
    gras = any(k in n for k in ("bold", "gras", "black", "heavy", "semibold"))
    ital = any(k in n for k in ("italic", "oblique", "ital"))
    if any(k in n for k in ("courier", "mono", "consol")):
        fam = "LiberationMono"
        return os.path.join(_dossier_polices(), fam + ("-Bold" if gras else "-Regular") + ".ttf")
    fam = "LiberationSerif" if any(k in n for k in ("times", "serif", "georgia", "garamond", "roman")) and \
        "sans" not in n else "LiberationSans"
    style = "BoldItalic" if gras and ital else "Bold" if gras else "Italic" if ital else "Regular"
    return os.path.join(_dossier_polices(), f"{fam}-{style}.ttf")


def _polices_non_integrees(doc):
    """{xref police: nom} des polices simples sans programme de police (dans les pages, formulaires, apparences)."""
    out = {}
    for x in range(1, doc.xref_length()):
        try:
            if doc.xref_get_key(x, "Type")[1] != "/Font":
                continue
        except Exception:
            continue
        st = doc.xref_get_key(x, "Subtype")[1]
        nom = doc.xref_get_key(x, "BaseFont")[1].lstrip("/")
        if st in ("/Type3", "/Type0"):
            continue
        td, vd = doc.xref_get_key(x, "FontDescriptor")
        integre = False
        if td == "xref":
            dx = int(vd.split()[0])
            integre = any(doc.xref_get_key(dx, k)[0] == "xref" for k in ("FontFile", "FontFile2", "FontFile3"))
        if not integre:
            out[x] = nom
    return out


_PROGRAMMES = {}


def _programme(doc, f):
    """Flux FontFile2 de la police f, reduite aux lettres du clavier (latin) et partage entre les polices du
    document qui l'utilisent (une seule copie dans le fichier)."""
    cle = (id(doc), f)
    if cle in _PROGRAMMES:
        return _PROGRAMMES[cle]
    with open(f, "rb") as h:
        programme = h.read()
    try:
        import io
        from fontTools.ttLib import TTFont
        from fontTools import subset
        t = TTFont(io.BytesIO(programme))
        o = subset.Options()
        o.name_IDs = ["*"]
        o.notdef_outline = True
        o.glyph_names = True
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
    ff = doc.get_new_xref()
    doc.update_object(ff, f"<</Length1 {len(programme)}>>")
    doc.update_stream(ff, programme, compress=True)
    _PROGRAMMES[cle] = ff
    return ff


def _integrer(doc, x, nom, journal):
    """Donne un programme de police a la police x (sans changer les largeurs ni les codes des caracteres)."""
    if "zapf" in nom.lower() or "dingbat" in nom.lower() or "symbol" in nom.lower() or nom in ("ZaDb",):
        return False
    f = _remplacante(nom)
    if not os.path.exists(f):
        return False
    font = fitz.Font(fontfile=f)
    # largeurs : celles du PDF si elles existent, sinon celles de la police remplacante (memes metriques)
    t_enc, enc = doc.xref_get_key(x, "Encoding")
    if t_enc == "null":
        doc.xref_set_key(x, "Encoding", "/WinAnsiEncoding")
    if doc.xref_get_key(x, "Widths")[0] == "null":
        larg = []
        for c in range(32, 256):
            try:
                u = bytes([c]).decode("cp1252")
            except UnicodeDecodeError:
                u = " "
            larg.append(round(font.glyph_advance(ord(u)) * 1000))
        doc.xref_set_key(x, "FirstChar", "32")
        doc.xref_set_key(x, "LastChar", "255")
        doc.xref_set_key(x, "Widths", "[" + " ".join(map(str, larg)) + "]")
    ff = _programme(doc, f)
    bbox = font.bbox
    nom_ps = re.sub(r"[^A-Za-z0-9+-]", "", nom) or "Police"
    fd_t, fd_v = doc.xref_get_key(x, "FontDescriptor")
    desc = (f"<</Type/FontDescriptor/FontName/{nom_ps}/Flags 32"
            f"/FontBBox[{round(bbox.x0 * 1000)} {round(bbox.y0 * 1000)} {round(bbox.x1 * 1000)} {round(bbox.y1 * 1000)}]"
            f"/ItalicAngle {-12 if 'Italic' in f else 0}/Ascent {round(font.ascender * 1000)}"
            f"/Descent {round(font.descender * 1000)}/CapHeight 700/StemV 80/FontFile2 {ff} 0 R>>")
    if fd_t == "xref":
        dx = int(fd_v.split()[0])
        doc.xref_set_key(dx, "FontFile2", f"{ff} 0 R")
        doc.xref_set_key(dx, "Flags", "32")
        for k in ("FontFile", "FontFile3"):
            doc.xref_set_key(dx, k, "null")
    else:
        dx = doc.get_new_xref()
        doc.update_object(dx, desc)
        doc.xref_set_key(x, "FontDescriptor", f"{dx} 0 R")
    doc.xref_set_key(x, "Subtype", "/TrueType")
    doc.xref_set_key(x, "BaseFont", "/" + nom_ps)
    journal.append(f"Police « {nom} » intégrée ({os.path.basename(f)[:-4]}, mêmes largeurs)")
    return True


def _cases_en_traits(doc, journal):
    """Apparences de cases a cocher / boutons radio ecrites avec ZapfDingbats : redessinees en traits vectoriels."""
    n = 0
    for page in doc:
        for w in page.widgets() or []:
            if w.field_type not in (fitz.PDF_WIDGET_TYPE_CHECKBOX, fitz.PDF_WIDGET_TYPE_RADIOBUTTON):
                continue
            t, v = doc.xref_get_key(w.xref, "AP/N")
            if t != "dict":
                continue
            r = w.rect
            lw, lh = r.width, r.height
            for etat, ref in re.findall(r"/([^\s/<>]+)\s+(\d+)\s+0\s+R", v):
                ax = int(ref)
                try:
                    flux = doc.xref_stream(ax) or b""
                except Exception:
                    continue
                if b"ZaDb" not in flux and b"ZapfDingbats" not in flux:
                    continue
                if etat == "Off":
                    neuf = b""
                elif w.field_type == fitz.PDF_WIDGET_TYPE_RADIOBUTTON:
                    k = 0.5523 * min(lw, lh) * 0.28
                    cx, cy, ry = lw / 2, lh / 2, min(lw, lh) * 0.28
                    neuf = (f"0 g {cx + ry:.2f} {cy:.2f} m {cx + ry:.2f} {cy + k:.2f} {cx + k:.2f} {cy + ry:.2f} {cx:.2f} {cy + ry:.2f} c "
                            f"{cx - k:.2f} {cy + ry:.2f} {cx - ry:.2f} {cy + k:.2f} {cx - ry:.2f} {cy:.2f} c "
                            f"{cx - ry:.2f} {cy - k:.2f} {cx - k:.2f} {cy - ry:.2f} {cx:.2f} {cy - ry:.2f} c "
                            f"{cx + k:.2f} {cy - ry:.2f} {cx + ry:.2f} {cy - k:.2f} {cx + ry:.2f} {cy:.2f} c f").encode()
                else:
                    neuf = (f"0 G {max(1.0, min(lw, lh) * 0.12):.2f} w 1 J 1 j "
                            f"{lw * 0.2:.2f} {lh * 0.52:.2f} m {lw * 0.42:.2f} {lh * 0.25:.2f} l "
                            f"{lw * 0.8:.2f} {lh * 0.78:.2f} l S").encode()
                doc.update_stream(ax, neuf, compress=True)
                doc.xref_set_key(ax, "Resources", "<<>>")
                n += 1
    if n:
        journal.append(f"{n} apparence(s) de case à cocher redessinée(s) sans police")


def _dr_sans_dingbats(doc):
    """ZapfDingbats des ressources du formulaire (cases a cocher), inutile une fois les cases redessinees."""
    cat = doc.pdf_catalog()
    t, v = doc.xref_get_key(cat, "AcroForm")
    if t == "null":
        return
    ax, pre = (int(v.split()[0]), "") if t == "xref" else (cat, "AcroForm/")
    tf, vf = doc.xref_get_key(ax, pre + "DR/Font")
    texte = doc.xref_object(int(vf.split()[0]), compressed=True) if tf == "xref" else vf
    for nom in re.findall(r"/([^\s/<>]+)\s+\d+\s+0\s+R", texte or ""):
        if nom in ("ZaDb",) or "Dingbat" in nom:
            utilise = False
            for page in doc:
                for w in page.widgets() or []:
                    if f"/{nom} " in (doc.xref_get_key(w.xref, "DA")[1] or ""):
                        utilise = True
            if not utilise:
                if tf == "xref":
                    doc.xref_set_key(int(vf.split()[0]), nom, "null")
                else:
                    doc.xref_set_key(ax, pre + "DR/Font/" + nom, "null")


def _retirer_actions(doc, journal):
    """JavaScript, actions automatiques (AA), lancement d'applications : interdits en PDF/A."""
    n = 0
    cat = doc.pdf_catalog()
    for cle in ("AA", "Names/JavaScript"):
        if doc.xref_get_key(cat, cle)[0] != "null":
            doc.xref_set_key(cat, cle, "null")
            n += 1
    t, v = doc.xref_get_key(cat, "OpenAction")
    if t != "null" and ("JavaScript" in v or (t == "xref" and "JavaScript" in doc.xref_object(int(v.split()[0])))):
        doc.xref_set_key(cat, "OpenAction", "null")
        n += 1
    interdites = ("/JavaScript", "/Launch", "/Sound", "/Movie", "/ResetForm", "/ImportData", "/Hide", "/SetOCGState",
                  "/Rendition", "/Trans", "/GoTo3DView")
    for x in range(1, doc.xref_length()):
        try:
            o = doc.xref_object(x, compressed=True)
        except Exception:
            continue
        if "/AA" in o and doc.xref_get_key(x, "AA")[0] != "null":
            doc.xref_set_key(x, "AA", "null")
            n += 1
        if doc.xref_get_key(x, "S")[1] in interdites:          # action isolee
            doc.xref_set_key(x, "S", "/GoTo")
            doc.xref_set_key(x, "D", "[0 /Fit]") if len(doc) else None
            doc.xref_set_key(x, "JS", "null")
            n += 1
        ta, va = doc.xref_get_key(x, "A")
        if ta == "dict" and any(i in va for i in interdites):
            doc.xref_set_key(x, "A", "null")
            n += 1
    af = doc.xref_get_key(cat, "AcroForm")
    if af[0] != "null":
        ax = int(af[1].split()[0]) if af[0] == "xref" else None
        if ax:
            doc.xref_set_key(ax, "NeedAppearances", "null")
            doc.xref_set_key(ax, "XFA", "null")
        else:
            doc.xref_set_key(cat, "AcroForm/NeedAppearances", "null")
            doc.xref_set_key(cat, "AcroForm/XFA", "null")
    if n:
        journal.append(f"{n} script(s) ou action(s) automatique(s) retiré(s) (interdits en PDF/A : les calculs "
                       f"et contrôles du formulaire ne s'exécutent plus)")


def _retirer_joints(doc, journal):
    n = doc.embfile_count() if hasattr(doc, "embfile_count") else 0
    if n:
        for nom in list(doc.embfile_names()):
            doc.embfile_del(nom)
        journal.append(f"{n} fichier(s) joint(s) retiré(s) (interdits en PDF/A-2b)")
    for page in doc:
        for a in list(page.annots() or []):
            if a.type[0] in (fitz.PDF_ANNOT_FILE_ATTACHMENT, fitz.PDF_ANNOT_SOUND, fitz.PDF_ANNOT_MOVIE):
                page.delete_annot(a)


def _annotations(doc, journal):
    """Chaque annotation : imprimable, visible, avec son apparence."""
    n = 0
    for page in doc:
        for a in page.annots() or []:
            if a.type[0] == fitz.PDF_ANNOT_POPUP:
                continue
            f = a.flags
            nf = (f | fitz.PDF_ANNOT_IS_PRINT) & ~(fitz.PDF_ANNOT_IS_HIDDEN | fitz.PDF_ANNOT_IS_INVISIBLE |
                                                    fitz.PDF_ANNOT_IS_NO_VIEW)
            if nf != f:
                a.set_flags(nf)
                n += 1
            if doc.xref_get_key(a.xref, "AP")[0] == "null":
                try:
                    a.update()
                except Exception:
                    pass
            doc.xref_set_key(a.xref, "CA", "null") if doc.xref_get_key(a.xref, "CA")[1] in ("1", "1.0") else None
        for w in page.widgets() or []:
            f = doc.xref_get_key(w.xref, "F")[1]
            try:
                fv = int(f) if f not in ("null", "") else 0
            except ValueError:
                fv = 0
            nv = (fv | 4) & ~(1 | 2 | 32)
            if nv != fv:
                doc.xref_set_key(w.xref, "F", str(nv))
                n += 1
    if n:
        journal.append(f"{n} annotation(s) rendue(s) imprimable(s) et visible(s)")


def _lzw(doc, journal):
    n = 0
    for x in range(1, doc.xref_length()):
        try:
            if not doc.xref_is_stream(x):
                continue
        except Exception:
            continue
        flt = doc.xref_get_key(x, "Filter")[1]
        if "LZW" in flt:
            data = doc.xref_stream(x)
            doc.update_stream(x, data, compress=True)
            doc.xref_set_key(x, "DecodeParms", "null")
            n += 1
    if n:
        journal.append(f"{n} flux LZW recompressés (LZW interdit)")


def _profil_srgb():
    try:
        from PIL import ImageCms
        return ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    except Exception:
        return None


def _intention(doc, journal):
    cat = doc.pdf_catalog()
    if doc.xref_get_key(cat, "OutputIntents")[0] != "null":
        t, v = doc.xref_get_key(cat, "OutputIntents")
        if "GTS_PDFA1" in (v if t != "xref" else doc.xref_object(int(v.split()[0]))):
            return
    icc = _profil_srgb()
    if not icc:
        raise RuntimeError("profil sRGB introuvable (Pillow avec ImageCms)")
    ix = doc.get_new_xref()
    doc.update_object(ix, "<</N 3>>")
    doc.update_stream(ix, icc, compress=True)
    doc.xref_set_key(cat, "OutputIntents",
                     f"[<</Type/OutputIntent/S/GTS_PDFA1/OutputConditionIdentifier(sRGB IEC61966-2.1)"
                     f"/RegistryName(http://www.color.org)/Info(sRGB IEC61966-2.1)/DestOutputProfile {ix} 0 R>>]")
    journal.append("Profil de couleurs sRGB ajouté")


def _metadonnees(doc, journal):
    v = MD.lire(doc)
    maint = datetime.datetime.now().astimezone()
    v["creation"] = v.get("creation") or maint
    v["modification"] = maint
    v["producer"] = v.get("producer") or "PhilPDF"
    v["title"] = v.get("title") or ""
    vals = {k: v.get(k) for k in MD.CHAMPS + ("creation", "modification")}
    info = {k: vals.get(k) or "" for k in MD.CHAMPS}
    info["creationDate"] = MD._date_pdf(vals["creation"])
    info["modDate"] = MD._date_pdf(vals["modification"])
    doc.set_metadata(info)
    doc.set_xml_metadata(MD._paquet_xmp(vals, ("2", "B")))
    cat = doc.pdf_catalog()
    if doc.xref_get_key(cat, "MarkInfo")[0] == "null":
        doc.xref_set_key(cat, "MarkInfo", "<</Marked false>>")
    journal.append("Métadonnées XMP PDF/A-2b écrites")


def convertir(doc, journal=None):
    """Met le document au format PDF/A-2b (sur place). Renvoie le journal ; leve une erreur si c'est impossible."""
    journal = [] if journal is None else journal
    if doc.is_encrypted or doc.needs_pass:
        raise RuntimeError("document protégé par mot de passe : retirez d'abord la protection")
    _retirer_actions(doc, journal)
    _retirer_joints(doc, journal)
    _annotations(doc, journal)
    _cases_en_traits(doc, journal)
    _dr_sans_dingbats(doc)
    for x, nom in _polices_non_integrees(doc).items():
        _integrer(doc, x, nom, journal)
    for k in [k for k in _PROGRAMMES if k[0] == id(doc)]:
        del _PROGRAMMES[k]
    _lzw(doc, journal)
    _intention(doc, journal)
    _metadonnees(doc, journal)
    return journal


def octets(doc):
    """Enregistrement compatible PDF/A : sans chiffrement, objets nettoyes, identifiant de fichier."""
    return doc.tobytes(garbage=3, deflate=True, encryption=fitz.PDF_ENCRYPT_NONE, no_new_id=False)


def verifier(doc):
    """Regles PDF/A-2b principales, relues sur le document : [(regle, ok, detail)]."""
    out = []
    cat = doc.pdf_catalog()
    xmp = ""
    try:
        xmp = doc.get_xml_metadata() or ""
    except Exception:
        pass
    part = re.search(r"pdfaid:part[>=\"]+\s*(\d)", xmp)
    out.append(("identifiant PDF/A dans le XMP", bool(part), f"partie {part.group(1)}" if part else "absent"))
    oi = doc.xref_get_key(cat, "OutputIntents")
    oi_txt = oi[1] if oi[0] != "xref" else doc.xref_object(int(oi[1].split()[0]))
    out.append(("profil de couleurs (OutputIntent)", "GTS_PDFA1" in (oi_txt or ""), ""))
    restantes = [n for n in _polices_non_integrees(doc).values()]
    out.append(("toutes les polices intégrées", not restantes, ", ".join(sorted(set(restantes))[:6])))
    out.append(("pas de chiffrement", not doc.is_encrypted, ""))
    js = doc.xref_get_key(cat, "Names/JavaScript")[0] != "null"
    aa = []
    lzw = 0
    for x in range(1, doc.xref_length()):
        try:
            o = doc.xref_object(x, compressed=True)
        except Exception:
            continue
        if re.search(r"/S\s*/(JavaScript|Launch|Sound|Movie|ResetForm|ImportData)", o):
            js = True
        if re.search(r"/AA\s*<<", o) or re.search(r"/AA\s+\d+\s+0\s+R", o):
            aa.append(x)
        if "/LZWDecode" in o:
            lzw += 1
    out.append(("pas de JavaScript ni d'action interdite", not js and not aa, f"{len(aa)} action(s) automatique(s)" if aa else ""))
    out.append(("pas de compression LZW", lzw == 0, f"{lzw} flux" if lzw else ""))
    joints = doc.embfile_count() if hasattr(doc, "embfile_count") else 0
    out.append(("pas de fichier joint", joints == 0, f"{joints}" if joints else ""))
    pb = 0
    for page in doc:
        for a in page.annots() or []:
            if a.type[0] == fitz.PDF_ANNOT_POPUP:
                continue
            if not (a.flags & fitz.PDF_ANNOT_IS_PRINT) or a.flags & fitz.PDF_ANNOT_IS_HIDDEN or \
                    doc.xref_get_key(a.xref, "AP")[0] == "null":
                pb += 1
    out.append(("annotations imprimables, avec apparence", pb == 0, f"{pb} à revoir" if pb else ""))
    cmyk = any("DeviceCMYK" in (doc.xref_object(x, compressed=True) or "") for x in range(1, min(doc.xref_length(), 20000))
               if _sur(doc, x))
    out.append(("couleurs compatibles avec le profil sRGB", not cmyk,
                "le document contient du CMJN (impression) : il reste lisible, mais un validateur strict le signalera"
                if cmyk else ""))
    info = doc.metadata or {}
    titre_ok = not info.get("title") or (info.get("title") in xmp)
    out.append(("métadonnées Info et XMP identiques", titre_ok, ""))
    return out


def _sur(doc, x):
    try:
        doc.xref_object(x, compressed=True)
        return True
    except Exception:
        return False


def conforme(doc):
    return all(ok for _r, ok, _d in verifier(doc))
