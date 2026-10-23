"""PhilPDF - objets poses sur les pages : tampons, signatures, filigranes.

Principe : chaque tampon ou signature de la bibliotheque est un petit PDF d'une page
(vectoriel quand c'est possible, sinon image). Quand on le pose, il devient une
annotation "Tampon" (Stamp) dont l'apparence est ce PDF : il reste deplacable,
redimensionnable et supprimable, dans PhilPDF comme dans Acrobat.
"""
import datetime, io, os
import pymupdf as fitz
from app.langue import _

SUJET = "PhilPDF"   # marque nos objets (champ Subject de l'annotation)

PREDEFINIS = [
    # (nom, texte, couleur RVB 0-1)
    (_('Reçu'), _('REÇU'), (0.08, 0.38, 0.76)),
    (_('Validé'), _('VALIDÉ'), (0.10, 0.48, 0.18)),
    (_('Approuvé'), _('APPROUVÉ'), (0.10, 0.48, 0.18)),
    (_('Rejeté'), _('REJETÉ'), (0.79, 0.15, 0.18)),
    (_('Payé'), _('PAYÉ'), (0.10, 0.48, 0.18)),
    (_('A payer'), _('A PAYER'), (0.64, 0.36, 0.0)),
    (_('Urgent'), _('URGENT'), (0.79, 0.15, 0.18)),
    (_('Confidentiel'), _('CONFIDENTIEL'), (0.79, 0.15, 0.18)),
    (_('Copie'), _('COPIE'), (0.35, 0.35, 0.35)),
    (_('Original'), _('ORIGINAL'), (0.08, 0.38, 0.76)),
    (_('Brouillon'), _('BROUILLON'), (0.35, 0.35, 0.35)),
    (_('Pour accord'), _('POUR ACCORD'), (0.43, 0.25, 0.78)),
    (_('Vu'), _('VU'), (0.08, 0.38, 0.76)),
    (_('Classé'), _('CLASSÉ'), (0.35, 0.35, 0.35)),
]

FILIGRANES = [_('COPIE'), _('CONFIDENTIEL'), _('BROUILLON'), _('ORIGINAL'), _('DUPLICATA'), _('PAYÉ'), _('ANNULÉ'), _('NE PAS DIFFUSER')]


# ------------------------------------------------------------------ fabrication des objets
def tampon_predefini(texte, couleur, auteur="", date=True):
    """Tampon vectoriel : cadre arrondi, texte en gras, ligne de date dynamique."""
    font = fitz.Font("hebo")
    taille = 22
    larg = max(font.text_length(texte, fontsize=taille), 90) + 34
    ligne2 = ""
    if date:
        ligne2 = "le " + datetime.date.today().strftime("%d/%m/%Y") + (f"  par {auteur}" if auteur else "")
    haut = 44 + (16 if ligne2 else 0)
    larg = max(larg, fitz.Font("helv").text_length(ligne2, fontsize=10) + 30)
    d = fitz.open()
    p = d.new_page(width=larg, height=haut)
    r = p.rect + (3, 3, -3, -3)
    p.draw_rect(r, color=couleur, width=2.6, radius=0.18)
    p.draw_rect(r + (4, 4, -4, -4), color=couleur, width=0.8, radius=0.15)
    tl = font.text_length(texte, fontsize=taille)
    p.insert_text(((larg - tl) / 2, 33), texte, fontname="hebo", fontsize=taille, color=couleur)
    if ligne2:
        l2 = fitz.Font("helv").text_length(ligne2, fontsize=10)
        p.insert_text(((larg - l2) / 2, haut - 12), ligne2, fontname="helv", fontsize=10, color=couleur)
    return d.tobytes(garbage=3, deflate=True)


def pdf_depuis_image(chemin_ou_octets, blanc_transparent=True, zone=None):
    """Image (scan de tampon, signature photographiee) -> PDF d'une page, fond blanc retire."""
    from PIL import Image
    im = Image.open(chemin_ou_octets if isinstance(chemin_ou_octets, str) else io.BytesIO(chemin_ou_octets))
    im = im.convert("RGBA")
    if zone:
        im = im.crop(tuple(int(v) for v in zone))
    if blanc_transparent:
        import numpy as np
        a = np.array(im).astype(np.float32)
        lum = a[..., :3].mean(axis=2)
        alpha = np.clip((225 - lum) / 45, 0, 1) * a[..., 3]
        a[..., 3] = alpha
        im = Image.fromarray(a.astype(np.uint8), "RGBA")
    bb = im.getbbox()
    if bb:
        im = im.crop(bb)
    if max(im.size) > 1200:                       # pas besoin de plus pour un tampon
        k = 1200 / max(im.size)
        im = im.resize((int(im.width * k), int(im.height * k)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "PNG", optimize=True)
    w, h = im.size
    d = fitz.open()
    k = 72 / 150                                   # 150 dpi
    p = d.new_page(width=w * k, height=h * k)
    p.insert_image(p.rect, stream=buf.getvalue())
    return d.tobytes(garbage=3, deflate=True)


def tampons_du_pdf(chemin):
    """Tampons Acrobat (annotations Stamp) presents dans un PDF : [(page, rect, nom)]."""
    d = fitz.open(chemin)
    out = []
    for p in d:
        for a in p.annots(types=[fitz.PDF_ANNOT_STAMP]):
            out.append((p.number, fitz.Rect(a.rect), a.info.get("subject") or a.info.get("content") or _('Tampon')))
    return out


def pdf_depuis_zone(chemin, num_page, zone):
    """Decoupe une zone d'une page PDF (annotations comprises) en PDF vectoriel d'une page."""
    src = fitz.open(chemin)
    try:
        src.bake(annots=True, widgets=False)       # les tampons Acrobat sont des annotations
    except Exception:
        pass
    zone = fitz.Rect(zone) & src[num_page].rect
    d = fitz.open()
    p = d.new_page(width=zone.width, height=zone.height)
    p.show_pdf_page(p.rect, src, num_page, clip=zone)
    return d.tobytes(garbage=3, deflate=True)


def apercu(pdf_octets, hauteur=64):
    """PNG d'apercu pour la bibliotheque."""
    d = fitz.open("pdf", pdf_octets)
    p = d[0]
    k = hauteur / p.rect.height
    return p.get_pixmap(matrix=fitz.Matrix(k * 2, k * 2), alpha=True).tobytes("png")


def taille_naturelle(pdf_octets):
    r = fitz.open("pdf", pdf_octets)[0].rect
    return r.width, r.height


# ------------------------------------------------------------------ pose sur une page
def poser(doc, num_page, rect, pdf_octets, nom=_('Tampon'), auteur="", genre="tampon"):
    """Pose l'objet comme annotation Stamp a l'apparence personnalisee. Renvoie son xref."""
    src = fitz.open("pdf", pdf_octets)
    tmp = doc.new_page(width=src[0].rect.width, height=src[0].rect.height)
    avant = set(doc.xref_get_key(tmp.xref, "Resources/XObject")[1].split()) if True else set()
    tmp.show_pdf_page(tmp.rect, src, 0)
    xo = doc.xref_get_key(tmp.xref, "Resources/XObject")[1]
    import re
    refs = re.findall(r"(\d+) 0 R", xo)
    form = int(refs[0])
    doc.delete_page(tmp.number)
    page = doc[num_page]
    a = page.add_stamp_annot(fitz.Rect(rect), stamp=0)
    a.set_info(title=auteur, subject=f"{SUJET}:{genre}", content=nom)
    a.update()
    doc.xref_set_key(a.xref, "AP/N", f"{form} 0 R")
    doc.xref_set_key(a.xref, "Name", f"/PhilPDF_{genre}")
    # PyMuPDF reajuste le cadre aux proportions de ses tampons standard : on impose le notre
    r = fitz.Rect(rect) * page.transformation_matrix
    r.normalize()
    doc.xref_set_key(a.xref, "Rect", f"[{r.x0:.2f} {r.y0:.2f} {r.x1:.2f} {r.y1:.2f}]")
    return a.xref


def est_objet_philpdf(annot):
    return (annot.info.get("subject") or "").startswith(SUJET)


def deplacer(doc, num_page, xref, nouveau_rect):
    """Deplace / redimensionne un objet sans regenerer son apparence."""
    page = doc[num_page]
    r = fitz.Rect(nouveau_rect) * page.transformation_matrix  # vers coordonnees PDF
    r.normalize()
    doc.xref_set_key(xref, "Rect", f"[{r.x0:.2f} {r.y0:.2f} {r.x1:.2f} {r.y1:.2f}]")


# ------------------------------------------------------------------ filigranes
def _marquer_filigrane(doc, page, avant):
    """Encadre le flux ajoute comme filigrane (meme marquage qu'Acrobat) : retirable ensuite."""
    for x in page.get_contents():
        if x not in avant:
            doc.update_stream(x, b"/Artifact <</Subtype /Watermark /Type /Pagination >>BDC\n"
                              + doc.xref_stream(x) + b"\nEMC\n")


def retirer_filigranes(doc):
    """Retire les filigranes marques (Acrobat, PhilPDF et logiciels qui suivent la norme).
    Renvoie le nombre de pages nettoyees."""
    import re
    motif = re.compile(rb"/Artifact\s*<<[^>]*?/Watermark[^>]*?>>\s*BDC.*?EMC", re.S)
    n = 0
    for page in doc:
        touche = False
        for x in page.get_contents():
            flux = doc.xref_stream(x)
            nouveau = motif.sub(b"", flux)
            if nouveau != flux:
                doc.update_stream(x, nouveau)
                touche = True
        n += touche
    return n


def filigranes_texte_probables(doc):
    """Textes penches repetes sur la plupart des pages (filigranes non marques)."""
    compte = {}
    for page in doc:
        vus = set()
        for b in page.get_text("dict")["blocks"]:
            for l in b.get("lines", []):
                dx, dy = l["dir"]
                t = "".join(s["text"] for s in l["spans"]).strip()
                if t and abs(dy) > 0.2 and t not in vus:
                    vus.add(t)
                    compte[t] = compte.get(t, 0) + 1
    return [t for t, c in compte.items() if c >= max(1, len(doc) // 2)]


def retirer_texte_penche(doc, texte):
    """Efface un texte penche donne sur toutes les pages (biffage sans rectangle)."""
    for page in doc:
        for b in page.get_text("dict")["blocks"]:
            for l in b.get("lines", []):
                if abs(l["dir"][1]) > 0.2 and "".join(s["text"] for s in l["spans"]).strip() == texte:
                    page.add_redact_annot(fitz.Rect(l["bbox"]), fill=False)
        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE, graphics=fitz.PDF_REDACT_LINE_ART_NONE)


def appliquer_filigrane(doc, pages, texte=None, image=None, couleur=(0.6, 0.6, 0.6), opacite=0.25,
                        angle=45, taille=None, position="centre", dessous=False):
    """Filigrane texte ou image sur les pages donnees (liste d'indices)."""
    for n in pages:
        page = doc[n]
        page.wrap_contents()
        avant = set(page.get_contents())
        R = page.rect
        if texte:
            font = fitz.Font("hebo")
            t = taille or min(R.width, R.height) / max(4, len(texte) * 0.62)
            L = font.text_length(texte, fontsize=t)
            centre = {"centre": R.tl + (R.width / 2, R.height / 2), "haut": R.tl + (R.width / 2, t * 1.2),
                      "bas": R.tl + (R.width / 2, R.height - t * 0.6)}[position]
            org = centre - (L / 2, -t * 0.35)
            page.insert_text(org, texte, fontname="hebo", fontsize=t, color=couleur, fill_opacity=opacite,
                             morph=(centre, fitz.Matrix(angle if position == "centre" else 0)), overlay=not dessous)
        elif image:
            from PIL import Image
            im = Image.open(image).convert("RGBA")
            alpha = im.getchannel("A").point(lambda v: int(v * opacite))
            im.putalpha(alpha)
            buf = io.BytesIO()
            im.save(buf, "PNG")
            w = R.width * 0.6
            h = w * im.height / im.width
            c = R.tl + (R.width / 2, R.height / 2)
            page.insert_image(fitz.Rect(c.x - w / 2, c.y - h / 2, c.x + w / 2, c.y + h / 2),
                              stream=buf.getvalue(), overlay=not dessous)
        _marquer_filigrane(doc, page, avant)
