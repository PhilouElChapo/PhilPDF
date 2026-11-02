"""Sous-objets d'une page (« formulaires XObject ») ramenes dans la page.

Beaucoup de PDF (Mac, InDesign, Illustrator, Word...) rangent images et dessins dans des sous-objets, appeles par
la page (« /Fm1 Do »). Acrobat les ouvre quand on modifie un objet ; PhilPDF fait pareil : le contenu du sous-objet
est recopie a sa place dans la page (meme matrice, meme decoupe), ses ressources (images, polices, etats
graphiques...) rejoignent celles de la page, renommees si un nom est deja pris. L'aspect de la page ne change pas,
et l'image peut ensuite etre deplacee, tournee, retournee ou recadree comme une image de la page.
"""
import re

import pymupdf as fitz

CATEGORIES = ("ExtGState", "ColorSpace", "Pattern", "Shading", "XObject", "Font", "Properties")
_FIN_NOM = r"(?=[\s/\[\]<>(){}%]|$)"


class _Lecteur:
    """Lit les cles d'un dictionnaire PDF ecrit en texte (via un objet temporaire, reutilise)."""

    def __init__(self, doc):
        self.doc, self.tmp = doc, None

    def cles(self, texte):
        if not texte or not texte.strip().startswith("<<"):
            return {}
        if self.tmp is None:
            self.tmp = self.doc.get_new_xref()
        self.doc.update_object(self.tmp, texte)
        return {k: self.doc.xref_get_key(self.tmp, k) for k in self.doc.xref_get_keys(self.tmp)}

    def fin(self):
        if self.tmp is not None:
            self.doc.update_object(self.tmp, "null")


def _texte(doc, t, v):
    """Valeur (type, texte) -> texte du dictionnaire (une reference est suivie)."""
    if t == "xref":
        return doc.xref_object(int(v.split()[0]), compressed=True)
    return v if t == "dict" else ""


def _ressources_page(doc, page):
    """xref du dictionnaire de ressources de la page (cree, ou recopie depuis le parent, si besoin)."""
    t, v = doc.xref_get_key(page.xref, "Resources")
    if t == "xref":
        return int(v.split()[0])
    if t == "dict":
        texte = v
    else:                                              # heritee du parent : recopiee sur la page
        texte, parent = "<<>>", page.xref
        while True:
            tp, vp = doc.xref_get_key(parent, "Parent")
            if tp != "xref":
                break
            parent = int(vp.split()[0])
            tr, vr = doc.xref_get_key(parent, "Resources")
            if tr in ("xref", "dict"):
                texte = _texte(doc, tr, vr)
                break
    x = doc.get_new_xref()
    doc.update_object(x, texte)
    doc.xref_set_key(page.xref, "Resources", f"{x} 0 R")
    return x


def formes_directes(doc, page):
    """{nom: xref} des sous-objets (formulaires XObject) appeles directement par la page."""
    out = {}
    for x, nom, invoquant, _bb in page.get_xobjects():
        if invoquant == 0 and doc.xref_get_key(x, "Subtype")[1] == "/Form":
            out[nom] = x
    return out


def contient(doc, forme, xref, vus=None):
    """Vrai si le sous-objet `forme` dessine l'objet `xref` (directement ou dans un sous-sous-objet)."""
    vus = vus if vus is not None else set()
    if forme in vus:
        return False
    vus.add(forme)
    lecteur = _Lecteur(doc)
    try:
        res = lecteur.cles(_texte(doc, *doc.xref_get_key(forme, "Resources")))
        xo = res.get("XObject")
        if not xo:
            return False
        for _k, (t, v) in lecteur.cles(_texte(doc, *xo)).items():
            if t != "xref":
                continue
            x = int(v.split()[0])
            if x == xref:
                return True
            if doc.xref_get_key(x, "Subtype")[1] == "/Form" and contient(doc, x, xref, vus):
                return True
        return False
    finally:
        lecteur.fin()


def deplier(doc, num_page, nom):
    """Recopie le sous-objet `nom` (appele par la page) dans le contenu de la page. Renvoie le nombre d'appels
    remplaces (0 si rien n'a ete fait)."""
    page = doc[num_page]
    formes = formes_directes(doc, page)
    if nom not in formes:
        return 0
    fx = formes[nom]
    if doc.xref_get_key(fx, "Group/S")[1] == "/Transparency":
        return 0                                       # groupe transparent : l'ouvrir changerait l'aspect
    lecteur = _Lecteur(doc)
    try:
        # matrice et decoupe du sous-objet
        t, v = doc.xref_get_key(fx, "Matrix")
        mat = [float(x) for x in v.strip("[]").split()] if t == "array" else [1, 0, 0, 1, 0, 0]
        t, v = doc.xref_get_key(fx, "BBox")
        bb = [float(x) for x in v.strip("[]").split()] if t == "array" else None
        contenu = (doc.xref_stream(fx) or b"").decode("latin-1")
        # ressources : celles du sous-objet rejoignent celles de la page (renommees si le nom est pris)
        rx = _ressources_page(doc, page)
        res_page = lecteur.cles(doc.xref_object(rx, compressed=True))
        res_forme = lecteur.cles(_texte(doc, *doc.xref_get_key(fx, "Resources")))
        renommes = {}
        for cat in CATEGORIES:
            if cat not in res_forme:
                continue
            a_ajouter = lecteur.cles(_texte(doc, *res_forme[cat]))
            if not a_ajouter:
                continue
            tp, vp = res_page.get(cat, ("null", "null"))
            if tp == "xref":                           # categorie partagee avec d'autres pages : copie propre
                existants = lecteur.cles(_texte(doc, tp, vp))
            elif tp == "dict":
                existants = lecteur.cles(vp)
            else:
                existants = {}
            for k, (t2, v2) in a_ajouter.items():
                if k in existants and existants[k] == (t2, v2):
                    continue
                nk, i = k, 1
                while nk in existants:
                    nk = f"{k}_p{i}"
                    i += 1
                if nk != k:
                    renommes[k] = nk
                existants[nk] = (t2, v2)
            texte = "<<" + "".join(f"/{k} {v2}" for k, (_t2, v2) in existants.items()) + ">>"
            doc.xref_set_key(rx, cat, texte)
            res_page = lecteur.cles(doc.xref_object(rx, compressed=True))
        for ancien, neuf in renommes.items():
            contenu = re.sub("/" + re.escape(ancien) + _FIN_NOM, "/" + neuf, contenu)
        decoupe = f"{bb[0]:g} {bb[1]:g} {bb[2] - bb[0]:g} {bb[3] - bb[1]:g} re W n\n" if bb else ""
        bloc = f"q {' '.join(f'{x:g}' for x in mat)} cm\n{decoupe}{contenu}\nQ"
        # appels du sous-objet dans la page remplaces par son contenu ; la page n'a plus qu'un flux
        flux = "\n".join((doc.xref_stream(c) or b"").decode("latin-1") for c in page.get_contents())
        motif = re.compile("/" + re.escape(nom) + r"\s+Do" + _FIN_NOM)
        n = len(motif.findall(flux))
        if not n:
            return 0
        flux = motif.sub(lambda _m: bloc, flux)
        premier = page.get_contents()[0]
        doc.update_stream(premier, flux.encode("latin-1"))
        doc.xref_set_key(page.xref, "Contents", f"{premier} 0 R")
        # le nom du sous-objet n'est plus utilise par la page : retire de ses ressources
        t, v = doc.xref_get_key(rx, "XObject")
        xo = lecteur.cles(_texte(doc, t, v))
        if nom in xo and not re.search("/" + re.escape(nom) + _FIN_NOM, flux):
            del xo[nom]
            doc.xref_set_key(rx, "XObject", "<<" + "".join(f"/{k} {v2}" for k, (_t, v2) in xo.items()) + ">>")
        return n
    finally:
        lecteur.fin()


def deplier_pour(doc, num_page, xref):
    """Ramene dans la page le(s) sous-objet(s) qui contiennent l'objet `xref` (image), niveau par niveau.
    Renvoie vrai si quelque chose a ete deplie."""
    fait = False
    for _tour in range(4):                             # sous-objets imbriques : un niveau a chaque tour
        page = doc[num_page]
        cible = next((nom for nom, fx in formes_directes(doc, page).items() if contient(doc, fx, xref)), None)
        if cible is None or not deplier(doc, num_page, cible):
            break
        fait = True
    return fait
