"""Metadonnees d'un PDF : titre, auteur, objet, mots-cles, application, producteur, dates.

Un PDF les range a DEUX endroits : le dictionnaire « Info » (ancien) et le paquet XMP (XML, ecrit par Adobe et la
plupart des logiciels recents). Acrobat affiche en priorite le XMP : changer seulement « Info » ne change donc rien
dans Acrobat — d'ou la difficulte avec les fichiers d'Adobe. Ici on ecrit toujours les deux, coherents.
"""
import datetime
import re
from xml.sax.saxutils import escape

CHAMPS = ("title", "author", "subject", "keywords", "creator", "producer")


def _date_pdf(d):
    """datetime -> 'D:20261027221500+01'00'"."""
    if d.tzinfo is None:
        d = d.astimezone()
    off = d.utcoffset() or datetime.timedelta(0)
    m = int(off.total_seconds() // 60)
    signe = "+" if m >= 0 else "-"
    return d.strftime("D:%Y%m%d%H%M%S") + f"{signe}{abs(m) // 60:02d}'{abs(m) % 60:02d}'"


def lire_date(texte):
    """'D:20261027221500+01'00'' (ou ISO) -> datetime, ou None."""
    if not texte:
        return None
    t = texte.strip()
    m = re.match(r"D?:?(\d{4})(\d{2})?(\d{2})?(\d{2})?(\d{2})?(\d{2})?([Zz+\-])?(\d{2})?'?(\d{2})?", t)
    if m and not re.match(r"\d{4}-", t):
        a, mo, j, h, mi, s = (int(x) if x else d for x, d in zip(m.groups()[:6], (0, 1, 1, 0, 0, 0)))
        try:
            d = datetime.datetime(a, mo, j, h, mi, s)
        except ValueError:
            return None
        if m.group(7) in ("+", "-") and m.group(8):
            off = datetime.timedelta(hours=int(m.group(8)), minutes=int(m.group(9) or 0))
            d = d.replace(tzinfo=datetime.timezone(off if m.group(7) == "+" else -off))
        elif m.group(7) in ("Z", "z"):
            d = d.replace(tzinfo=datetime.timezone.utc)
        return d
    try:
        return datetime.datetime.fromisoformat(t.replace("Z", "+00:00"))
    except ValueError:
        return None


def _iso(d):
    if d.tzinfo is None:
        d = d.astimezone()
    return d.isoformat(timespec="seconds")


def lire(doc):
    """Ce qu'Acrobat affiche : le XMP quand il existe, sinon le dictionnaire Info."""
    m = dict(doc.metadata or {})
    out = {k: m.get(k) or "" for k in CHAMPS}
    out["creation"] = lire_date(m.get("creationDate"))
    out["modification"] = lire_date(m.get("modDate"))
    xmp = ""
    try:
        xmp = doc.get_xml_metadata() or ""
    except Exception:
        pass
    out["xmp"] = bool(xmp.strip())
    out["pdfa"] = "pdfaid:part" in xmp
    if xmp:
        def balise(nom):
            r = re.search(rf"<{nom}>\s*(?:<rdf:(?:Alt|Seq|Bag)>\s*)?(?:<rdf:li[^>]*>)?(.*?)(?:</rdf:li>)?\s*(?:</rdf:(?:Alt|Seq|Bag)>\s*)?</{nom}>",
                          xmp, re.S)
            if r:
                bloc = re.search(rf"<{nom}>(.*?)</{nom}>", xmp, re.S).group(1)
                items = re.findall(r"<rdf:li[^>]*>(.*?)</rdf:li>", bloc, re.S)
                if items:
                    return "; ".join(re.sub(r"<[^>]+>", "", x).strip() for x in items if x.strip())
                return re.sub(r"<[^>]+>", "", r.group(1)).strip()
            r = re.search(rf'{nom}="([^"]*)"', xmp)
            return r.group(1).strip() if r else None
        for cle, nom in (("title", "dc:title"), ("author", "dc:creator"), ("subject", "dc:description"),
                         ("keywords", "pdf:Keywords"), ("creator", "xmp:CreatorTool"), ("producer", "pdf:Producer")):
            v = balise(nom)
            if v:
                out[cle] = v
        for cle, nom in (("creation", "xmp:CreateDate"), ("modification", "xmp:ModifyDate")):
            v = balise(nom)
            if v and lire_date(v):
                out[cle] = lire_date(v)
    return out


def _paquet_xmp(v, pdfa=None):
    def alt(t):
        return f'<rdf:Alt><rdf:li xml:lang="x-default">{escape(t)}</rdf:li></rdf:Alt>'
    auteurs = "".join(f"<rdf:li>{escape(a.strip())}</rdf:li>" for a in (v.get("author") or "").split(";") if a.strip())
    morceaux = []
    if v.get("title"):
        morceaux.append(f"<dc:title>{alt(v['title'])}</dc:title>")
    if auteurs:
        morceaux.append(f"<dc:creator><rdf:Seq>{auteurs}</rdf:Seq></dc:creator>")
    if v.get("subject"):
        morceaux.append(f"<dc:description>{alt(v['subject'])}</dc:description>")
    if v.get("keywords"):
        morceaux.append(f"<pdf:Keywords>{escape(v['keywords'])}</pdf:Keywords>")
    if v.get("producer"):
        morceaux.append(f"<pdf:Producer>{escape(v['producer'])}</pdf:Producer>")
    if v.get("creator"):
        morceaux.append(f"<xmp:CreatorTool>{escape(v['creator'])}</xmp:CreatorTool>")
    if v.get("creation"):
        morceaux.append(f"<xmp:CreateDate>{_iso(v['creation'])}</xmp:CreateDate>")
    if v.get("modification"):
        morceaux.append(f"<xmp:ModifyDate>{_iso(v['modification'])}</xmp:ModifyDate>"
                        f"<xmp:MetadataDate>{_iso(v['modification'])}</xmp:MetadataDate>")
    if pdfa:
        morceaux.append(f"<pdfaid:part>{pdfa[0]}</pdfaid:part><pdfaid:conformance>{pdfa[1]}</pdfaid:conformance>")
    return ('<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>'
            '<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
            '<rdf:Description rdf:about="" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:pdf="http://ns.adobe.com/pdf/1.3/"'
            ' xmlns:xmp="http://ns.adobe.com/xap/1.0/" xmlns:pdfaid="http://www.aiim.org/pdfa/ns/id/">'
            + "".join(morceaux) + '</rdf:Description></rdf:RDF></x:xmpmeta><?xpacket end="w"?>')


def ecrire(doc, valeurs):
    """valeurs : title, author, subject, keywords, creator, producer (texte), creation, modification (datetime).
    Le dictionnaire Info ET le XMP sont reecrits : Acrobat affiche bien les nouvelles valeurs. Un PDF/A le reste."""
    ancien = ""
    try:
        ancien = doc.get_xml_metadata() or ""
    except Exception:
        pass
    pdfa = None
    r = re.search(r"pdfaid:part[>=\"]+\s*(\d)", ancien)
    if r:
        c = re.search(r"pdfaid:conformance[>=\"]+\s*([A-Za-z])", ancien)
        pdfa = (r.group(1), c.group(1) if c else "B")
    info = {k: valeurs.get(k) or "" for k in CHAMPS}
    for k, cle in (("creation", "creationDate"), ("modification", "modDate")):
        info[cle] = _date_pdf(valeurs[k]) if valeurs.get(k) else ""
    doc.set_metadata(info)
    doc.set_xml_metadata(_paquet_xmp(valeurs, pdfa))


def effacer(doc):
    """Retire toutes les metadonnees (Info et XMP) : rien sur l'auteur, le logiciel ni les dates."""
    doc.set_metadata({})
    try:
        doc.del_xml_metadata()
    except Exception:
        pass
