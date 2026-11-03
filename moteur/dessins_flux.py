"""Deplacer, agrandir, tourner, retourner ou supprimer un dessin vectoriel SANS le redessiner.

Le dessin reste ecrit tel quel dans le PDF (degrades, motifs, transparence, epaisseurs, pointilles, decoupes) : on
retrouve, dans le contenu de la page ou du sous-objet qui le dessine, les blocs « q ... Q » (ou les traces isoles)
qui le composent, et on les entoure de « q <matrice> cm ... Q ». Pour supprimer, on retire ces blocs.

Lecture du contenu : chaque trace (chemin peint, degrade « sh », sous-objet « Do ») recoit son cadre sur la page
(matrice courante et decoupe comprises). Un bloc est retenu s'il ne contient que du dessin (ni texte, ni image) et
si tout ce qu'il peint est dans le cadre du dessin choisi. Si le dessin n'est pas range ainsi, on renvoie None :
l'appelant garde alors l'autre methode (traces relus puis redessines).
"""
import re

import pymupdf as fitz

PEINTURE = {"S", "s", "f", "F", "f*", "B", "B*", "b", "b*"}
CHEMIN = {"m", "l", "c", "v", "y", "re", "h"}
_JETON = re.compile(rb"""
    (?P<esp>\s+) | (?P<com>%[^\r\n]*) |
    (?P<chaine>\() | (?P<dict><<|>>) | (?P<hexa><[0-9A-Fa-f\s]*>) |
    (?P<tab>[\[\]{}]) | (?P<nom>/[^\s/\[\]<>(){}%]*) |
    (?P<mot>[^\s/\[\]<>(){}%]+)""", re.X)


class _M:
    """Matrice PDF (a b c d e f), points en vecteur ligne."""
    __slots__ = ("a", "b", "c", "d", "e", "f")

    def __init__(self, a=1, b=0, c=0, d=1, e=0, f=0):
        self.a, self.b, self.c, self.d, self.e, self.f = a, b, c, d, e, f

    def __mul__(self, o):
        return _M(self.a * o.a + self.b * o.c, self.a * o.b + self.b * o.d, self.c * o.a + self.d * o.c,
                  self.c * o.b + self.d * o.d, self.e * o.a + self.f * o.c + o.e, self.e * o.b + self.f * o.d + o.f)

    def pt(self, x, y):
        return x * self.a + y * self.c + self.e, x * self.b + y * self.d + self.f

    def texte(self):
        """Les six nombres, sans notation exponentielle (le PDF ne la connait pas)."""
        def n(x):
            t = f"{x:.6f}".rstrip("0").rstrip(".")
            return "0" if t in ("-0", "") else t
        return " ".join(n(v) for v in (self.a, self.b, self.c, self.d, self.e, self.f))

    def fitz(self):
        return fitz.Matrix(self.a, self.b, self.c, self.d, self.e, self.f)

    @staticmethod
    def de(m):
        return _M(m.a, m.b, m.c, m.d, m.e, m.f)


def _operations(texte):
    """[(operateur, operandes, debut, fin)] ; images en ligne (BI ... EI) sautees."""
    out, pile, debut = [], [], None
    i, n = 0, len(texte)
    while i < n:
        m = _JETON.match(texte, i)
        if not m:
            i += 1
            continue
        g = m.lastgroup
        if g in ("esp", "com"):
            i = m.end()
            continue
        if g == "chaine":                                   # chaine entre parentheses (imbriquees, echappees)
            j, prof = i, 0
            while j < n:
                c = texte[j:j + 1]
                if c == b"\\":
                    j += 2
                    continue
                if c == b"(":
                    prof += 1
                elif c == b")":
                    prof -= 1
                    if prof == 0:
                        j += 1
                        break
                j += 1
            if debut is None:
                debut = i
            pile.append(texte[i:j])
            i = j
            continue
        jeton = m.group(0)
        if g in ("dict", "hexa", "tab", "nom") or (g == "mot" and (jeton[:1].isdigit() or jeton[:1] in b"-+." or
                                                                   jeton in (b"true", b"false", b"null"))):
            if debut is None:
                debut = i
            pile.append(jeton)
            i = m.end()
            continue
        op = jeton.decode("latin-1")
        if op == "BI":
            e = re.compile(rb"\sEI(?=[\s/\[<(]|$)").search(texte, i)
            i = e.end() if e else n
            pile, debut = [], None
            continue
        out.append((op, pile, debut if debut is not None else i, m.end()))
        pile, debut = [], None
        i = m.end()
    return out


def _nombres(ops):
    try:
        return [float(x) for x in ops]
    except ValueError:
        return None


class _Bloc:
    def __init__(self, debut, ctm, parent):
        self.debut, self.fin, self.ctm, self.parent = debut, None, ctm, parent
        self.cadre = fitz.EMPTY_RECT()                            # ce qui est peint (repere de la page)
        self.texte = False                                  # contient du texte ou une image : pas un dessin seul
        self.enfants = []


def lire(doc, page, flux, texte, ctm0, vers_page, clip0=None, speciaux=None):
    """Blocs et traces isoles du contenu `texte` : [(debut, fin, ctm au debut, cadre, flux, decoupe)].
    decoupe : la zone hors de laquelle rien n'est peint a cet endroit (None : la page).
    speciaux : si c'est une liste, on y ajoute les zones peintes d'un degrade ou d'un motif (le moteur ne les voit pas)."""
    racine = _Bloc(0, ctm0, None)
    bloc = racine
    ctm, pile_ctm, clip, pile_clip = ctm0, [], clip0, []
    largeur, pile_larg = 1.0, []
    motif, pile_motif = [False, False], []                 # remplissage / contour par un motif
    chemin, debut_chemin, clip_attente = fitz.EMPTY_RECT(), None, False
    elements = []                                   # (debut, fin, ctm, cadre, est_bloc, bloc, decoupe)

    def point(x, y):
        nonlocal chemin
        px, py = (ctm * vers_page).pt(x, y)
        chemin |= fitz.Point(px, py)

    for op, ops, debut, fin in _operations(texte):
        if op in CHEMIN and debut_chemin is None:
            debut_chemin, chemin = (debut, fitz.EMPTY_RECT()), fitz.EMPTY_RECT()
        if op == "q":
            pile_ctm.append(ctm)
            pile_clip.append(clip)
            pile_larg.append(largeur)
            pile_motif.append(list(motif))
            nb = _Bloc(debut, ctm, bloc)
            nb.clip = clip
            bloc.enfants.append(nb)
            bloc = nb
        elif op == "Q":
            if pile_ctm:
                ctm, clip, largeur = pile_ctm.pop(), pile_clip.pop(), pile_larg.pop()
                motif = pile_motif.pop() if pile_motif else [False, False]
            if bloc.parent is not None:
                bloc.fin = fin
                elements.append((bloc.debut, bloc.fin, bloc.ctm, fitz.Rect(bloc.cadre), True, bloc, bloc.clip))
                p = bloc.parent
                p.cadre |= bloc.cadre
                p.texte = p.texte or bloc.texte
                bloc = p
        elif op == "cm":
            v = _nombres(ops)
            if v and len(v) == 6:
                ctm = _M(*v) * ctm
        elif op == "w":
            v = _nombres(ops)
            if v:
                largeur = v[0]
        elif op in ("m", "l"):
            v = _nombres(ops)
            if v and len(v) >= 2:
                point(v[0], v[1])
        elif op in ("c", "v", "y"):
            v = _nombres(ops)
            if v:
                for k in range(0, len(v) - 1, 2):
                    point(v[k], v[k + 1])
        elif op == "re":
            v = _nombres(ops)
            if v and len(v) == 4:
                for x, y in ((v[0], v[1]), (v[0] + v[2], v[1]), (v[0], v[1] + v[3]), (v[0] + v[2], v[1] + v[3])):
                    point(x, y)
        elif op in ("scn", "SCN"):
            motif[op == "SCN"] = bool(ops) and ops[-1].startswith(b"/")
        elif op in ("rg", "g", "k", "sc", "RG", "G", "K", "SC"):
            motif[op.isupper()] = False
        elif op in ("W", "W*"):
            clip_attente = True
        elif op in PEINTURE or op == "n":
            r = fitz.Rect(chemin)
            decoupe_ici = clip_attente                    # trace qui decoupe aussi : on ne peut pas l'entourer seul
            if clip_attente and r.is_valid:
                clip = r if clip is None else (clip & r)
            clip_attente = False
            if op != "n" and r.is_valid:
                t = ctm * vers_page
                k = abs(t.a * t.d - t.b * t.c) ** 0.5 * largeur / 2 + 0.5 if op not in ("f", "F", "f*") else 0
                peint = r + (-k, -k, k, k)
                if clip is not None:
                    peint &= clip
                bloc.cadre |= peint
                remplit = op in ("f", "F", "f*", "B", "B*", "b", "b*")
                trace = op in ("S", "s", "B", "B*", "b", "b*")
                if speciaux is not None and ((remplit and motif[0]) or (trace and motif[1])):
                    speciaux.append(fitz.Rect(peint))
                if debut_chemin is not None and not decoupe_ici:                     # trace (chemin + peinture), dans un bloc ou non
                    elements.append((debut_chemin[0], fin, ctm, fitz.Rect(peint), False, None, clip))
            debut_chemin, chemin = None, fitz.EMPTY_RECT()
        elif op == "sh":
            z = fitz.Rect(clip if clip is not None else page.rect)
            bloc.cadre |= z
            if speciaux is not None:
                speciaux.append(z)
        elif op == "Do" and ops:
            nom = ops[-1].decode("latin-1").lstrip("/")
            x = _xobjet(doc, page, flux, nom)
            if x and doc.xref_get_key(x, "Subtype")[1] == "/Form":
                bb = doc.xref_get_key(x, "BBox")
                mt = doc.xref_get_key(x, "Matrix")
                b = [float(t) for t in bb[1].strip("[]").split()] if bb[0] == "array" else [0, 0, 0, 0]
                m = _M(*[float(t) for t in mt[1].strip("[]").split()]) if mt[0] == "array" else _M()
                full = m * ctm * vers_page
                pts = [full.pt(b[0], b[1]), full.pt(b[2], b[1]), full.pt(b[0], b[3]), full.pt(b[2], b[3])]
                bloc.cadre |= fitz.Rect(min(p[0] for p in pts), min(p[1] for p in pts),
                                        max(p[0] for p in pts), max(p[1] for p in pts))
            else:
                bloc.texte = True                         # image : ce n'est pas un dessin (outil Images)
        elif op in ("BT", "Tj", "TJ", "'", '"', "BI", "EI"):
            bloc.texte = True
    return [(d, f, c, r, flux, k) for d, f, c, r, est_bloc, b, k in elements
            if r.is_valid and not (est_bloc and b.texte)]


def _xobjet(doc, page, flux, nom):
    """xref du XObject `nom` dans les ressources du flux (page ou sous-objet)."""
    if flux is None:
        for x, n, _inv, _bb in page.get_xobjects():
            if n == nom:
                return x
        return None
    t, v = doc.xref_get_key(flux, f"Resources/XObject/{nom}")
    return int(v.split()[0]) if t == "xref" else None


def _sous_objets(doc, page):
    """[(xref, matrice d'appel)] des sous-objets appeles directement par la page, une seule fois."""
    texte = b"\n".join(doc.xref_stream(c) or b"" for c in page.get_contents())
    out = []
    vers_page = _M.de(page.transformation_matrix)
    for x, nom, inv, _bb in page.get_xobjects():
        if inv != 0 or doc.xref_get_key(x, "Subtype")[1] != "/Form":
            continue
        appels = [m for m in re.finditer(rb"/" + re.escape(nom.encode("latin-1")) + rb"\s+Do", texte)]
        if len(appels) != 1:
            continue
        # matrice courante au moment de l'appel : on rejoue le contenu de la page jusqu'a l'appel
        ctm, pile = _M(), []
        for op, ops, debut, fin in _operations(texte):
            if debut >= appels[0].start():
                break
            if op == "q":
                pile.append(ctm)
            elif op == "Q" and pile:
                ctm = pile.pop()
            elif op == "cm":
                v = _nombres(ops)
                if v and len(v) == 6:
                    ctm = _M(*v) * ctm
        mt = doc.xref_get_key(x, "Matrix")
        m = _M(*[float(t) for t in mt[1].strip("[]").split()]) if mt[0] == "array" else _M()
        tout = m * ctm
        bb = doc.xref_get_key(x, "BBox")
        clip = None
        if bb[0] == "array":
            b = [float(t) for t in bb[1].strip("[]").split()]
            pts = [(tout * vers_page).pt(u, v) for u in (b[0], b[2]) for v in (b[1], b[3])]
            clip = fitz.Rect(min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))
        out.append((x, tout, clip))
    return out


def _sources(doc, page):
    sources = [(None, b"\n".join(doc.xref_stream(c) or b"" for c in page.get_contents()), _M(), None)]
    return sources + [(x, doc.xref_stream(x) or b"", m, k) for x, m, k in _sous_objets(doc, page)]


def degrades(doc, page):
    """Zones peintes par un degrade ou un motif (repere de la page) : le moteur ne les compte pas comme des traces."""
    vers_page = _M.de(page.transformation_matrix)
    out = []
    try:
        for flux, texte, ctm0, clip0 in _sources(doc, page):
            lire(doc, page, flux, texte, ctm0, vers_page, clip0, out)
    except Exception:                                  # noqa: BLE001
        return []
    return [r for r in out if not r.is_empty and r.width * r.height < 0.6 * page.rect.width * page.rect.height]


def trouver(doc, page, cadre, marge=1.5):
    """Morceaux du contenu qui composent le dessin choisi : [(flux, debut, fin, ctm)] ; None si introuvable."""
    z = fitz.Rect(cadre) + (-marge, -marge, marge, marge)
    vers_page = _M.de(page.transformation_matrix)
    sources = _sources(doc, page)
    meilleurs = []
    for flux, texte, ctm0, clip0 in sources:
        elems = [e for e in lire(doc, page, flux, texte, ctm0, vers_page, clip0) if e[3] in z]
        # les plus grands morceaux (un bloc dans un bloc deja retenu n'est pas repris)
        elems.sort(key=lambda e: (e[0], -(e[1] - e[0])))
        garde, fin_garde = [], -1
        for d, f, c, r, fl, k in elems:
            if d >= fin_garde:
                garde.append((fl, d, f, c, r, k, ctm0))
                fin_garde = f
        meilleurs += garde
    if not meilleurs:
        return None
    couvert = fitz.EMPTY_RECT()
    for *_x, r, _k, _c0 in meilleurs:
        couvert |= r
    c0 = fitz.Rect(cadre)
    if c0.width * c0.height > 0 and (couvert & c0).get_area() < 0.85 * c0.get_area():
        return None                                         # une partie du dessin n'est pas rangee en blocs
    return [(fl, d, f, c, k, c0) for fl, d, f, c, _r, k, c0 in meilleurs]


def _ecrire(doc, page, morceaux, remplacer):
    """remplacer(texte du morceau, ctm, flux, ctm du flux) -> nouveau texte ; reecrits de la fin vers le debut."""
    par_flux = {}
    for fl, d, f, c, _k, c0 in morceaux:
        par_flux.setdefault(fl, []).append((d, f, c, c0))
    for fl, l in par_flux.items():
        if fl is None:
            texte = b"\n".join(doc.xref_stream(x) or b"" for x in page.get_contents())
        else:
            texte = doc.xref_stream(fl) or b""
        for d, f, c, c0 in sorted(l, key=lambda t: t[0], reverse=True):
            texte = texte[:d] + remplacer(texte[d:f], c, fl, c0) + texte[f:]
        if fl is None:
            premier = page.get_contents()[0]
            doc.update_stream(premier, texte)
            doc.xref_set_key(page.xref, "Contents", f"{premier} 0 R")
        else:
            doc.update_stream(fl, texte)


def _dico(doc, xref, cle):
    """(xref, chemin) ou ecrire dans le dictionnaire `cle` de l'objet xref (suit les references)."""
    t, v = doc.xref_get_key(xref, cle)
    if t == "xref":
        return int(v.split()[0]), ""
    if t == "dict":
        return xref, cle + "/"
    return None


def _motifs_suivent(doc, page, fl, bout, h):
    """Chaque motif nomme dans le morceau est copie avec sa matrice multipliee par h, sous un nouveau nom."""
    noms = set(re.findall(rb"/([^\s/\[\]<>()]+)\s+(?:[-+.\d]+\s+)*(?:scn|SCN)\b", bout))
    if not noms:
        return bout
    proprio = page.xref if fl is None else fl
    r = _dico(doc, proprio, "Resources")
    if r is None:
        return bout
    rx, rc = r
    pat = _dico(doc, rx, rc + "Pattern")
    if pat is None:
        return bout
    px, pc = pat
    for nom in noms:
        n = nom.decode("latin-1")
        t, v = doc.xref_get_key(px, pc + n)
        if t != "xref":
            continue
        x = int(v.split()[0])
        tm, vm = doc.xref_get_key(x, "Matrix")
        m0 = _M(*[float(u) for u in vm.strip("[]").split()]) if tm == "array" else _M()
        m1 = m0 * h
        neuf = doc.get_new_xref()
        doc.update_object(neuf, doc.xref_object(x, compressed=True))
        if doc.xref_is_stream(x):
            doc.update_stream(neuf, doc.xref_stream_raw(x), compress=False)
            # le flux brut garde son filtre : on remet celui d'origine
            tf, vf = doc.xref_get_key(x, "Filter")
            doc.xref_set_key(neuf, "Filter", vf if tf != "null" else "null")
            tp, vp = doc.xref_get_key(x, "DecodeParms")
            doc.xref_set_key(neuf, "DecodeParms", vp if tp != "null" else "null")
        doc.xref_set_key(neuf, "Matrix", "[" + m1.texte() + "]")
        k = 1
        while doc.xref_get_key(px, f"{pc}{n}_{k}")[0] != "null":
            k += 1
        doc.xref_set_key(px, f"{pc}{n}_{k}", f"{neuf} 0 R")
        bout = re.sub(rb"/" + re.escape(nom) + rb"(?=\s+(?:[-+.\d]+\s+)*(?:scn|SCN)\b)", f"/{n}_{k}".encode("latin-1"), bout)
    return bout


def transformer(doc, page, cadre, g):
    """Le dessin subit la matrice g (repere de la page affichee). Renvoie son nouveau cadre, ou None."""
    morceaux = trouver(doc, page, cadre)
    if morceaux is None:
        return None
    vers_page = _M.de(page.transformation_matrix)
    inv_page = _M.de(~page.transformation_matrix)
    G = _M.de(g)
    nouveau = (fitz.Rect(cadre).quad * g).rect
    for *_x, k, _c0 in morceaux:
        # une decoupe couperait le dessin deplace hors d'elle : l'appelant le redessine autrement
        if k is not None and not (nouveau in k + (-1, -1, 1, 1)):
            return None

    def entourer(bout, ctm, fl, ctm0):
        # point x C x T x G = point x N x C x T  =>  N = C T G T^-1 C^-1
        n = ctm * vers_page * G * inv_page * _M.de(~ctm.fitz())
        # les motifs (degrades remplissant une forme) ne suivent pas la matrice courante : on leur donne la leur
        crel = ctm * _M.de(~ctm0.fitz())
        bout = _motifs_suivent(doc, page, fl, bout, _M.de(~crel.fitz()) * n * crel)
        return (f"q {n.texte()} cm\n".encode("latin-1") + bout + b"\nQ")
    _ecrire(doc, page, morceaux, entourer)
    return nouveau


def supprimer(doc, page, cadre):
    """Retire le dessin ; False si introuvable ainsi (l'appelant efface autrement)."""
    morceaux = trouver(doc, page, cadre)
    if morceaux is None:
        return False
    _ecrire(doc, page, morceaux, lambda bout, ctm, fl, c0: b"")
    return True
