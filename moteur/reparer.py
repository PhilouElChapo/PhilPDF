"""Reparation des fichiers abimes par d'anciennes versions de PhilPDF Android (jusqu'a 1.10.0).

Un defaut du moteur MuPDF Java laissait, dans la liste des contenus d'une page (Contents) ou de ses annotations
(Annots), des « debris » : des valeurs qui ne sont pas des references a des objets (<00000000B0EC00>...).
PhilPDF et les lecteurs bases sur MuPDF les ignorent, mais Acrobat refuse alors toute la liste : la page s'affiche
vide (images et texte absents). On retire ces debris ; le reste de la page est intact.
"""
import pymupdf as fitz


def _elements(doc, xref, cle):
    """(type, valeur) de doc[xref][cle], et les elements du tableau s'il s'agit d'un tableau direct ou indirect."""
    t, v = doc.xref_get_key(xref, cle)
    if t == "xref":
        ref = int(v.split()[0])
        if doc.xref_is_stream(ref):
            return t, v, None, None
        brut = doc.xref_object(ref, compressed=True).strip()
        if brut.startswith("["):
            return t, v, ref, brut
        return t, v, None, None
    if t == "array":
        return t, v, None, v
    return t, v, None, None


def _nettoyer_tableau(texte):
    """« [<00..>12 0 R<00..>] » -> (« [12 0 R] », 1) ; (None, 0) s'il n'y a pas de debris.
    Seuls les debris connus (chaines hexadecimales et null) sont retires ; tout le reste est garde tel quel."""
    import re
    motif = r"(?<!<)<[0-9A-Fa-f\s]*>(?!>)|\bnull\b"
    if not re.search(motif, texte):
        return None, 0
    return re.sub(r"\s+", " ", re.sub(motif, " ", texte)).replace("[ ", "[").replace(" ]", "]"), 1


def debris(doc):
    """Retire les debris des pages ; renvoie [(numero de page, quoi)] (vide si rien a faire)."""
    faits = []
    for p in doc:
        x = p.xref
        for cle, quoi in (("Contents", "contenu"), ("Annots", "annotations")):
            t, v, ref, tableau = _elements(doc, x, cle)
            if tableau is None:
                continue
            nouveau, n = _nettoyer_tableau(tableau)
            if not n:
                continue
            if ref:
                doc.update_object(ref, nouveau)
            else:
                doc.xref_set_key(x, cle, nouveau)
            faits.append((p.number, quoi))
        # page marquee « texte reconnu » mais dont le texte reconnu a disparu avec les debris : marque retiree
        if doc.xref_get_key(x, "PhilPDF_OCR")[0] != "null" and any(q == "contenu" for n, q in faits if n == p.number):
            try:
                contenu = b"".join(doc.xref_stream(c) or b"" for c in p.get_contents())
            except Exception:
                contenu = b"PhilOCR"
            if b"PhilOCR" not in contenu:
                doc.xref_set_key(x, "PhilPDF_OCR", "null")
    return faits
