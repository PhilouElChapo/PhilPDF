"""PhilPDF - preuve de concept du moteur "Modifier".

Principe (inverse d'Acrobat sur les points ou il se trompe) :
 1. On retrouve le texte au niveau de la LIGNE, meme si le PDF l'a eclate en
    fragments ("D" "el" "a" "y").
 2. Pour chaque caractere a ecrire, on cherche le glyphe d'origine :
      a. dans la police du fragment ;
      b. sinon dans les polices "soeurs" (meme famille et meme graisse,
         decoupees en plusieurs sous-ensembles par le logiciel createur) ;
      c. sinon on incorpore la police la plus ressemblante, choisie en
         comparant le rendu des lettres d'origine (pas seulement le nom).
 3. On garde le style de TOUT le fragment remplace (gras compris), la taille,
    la couleur et l'espacement entre lettres mesure sur la ligne.
 4. Si le texte s'allonge, la suite de la ligne est decalee, pas coupee.
"""
import os, re, sys
import pymupdf as fitz

_BASE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FONT_DIR = os.path.join(_BASE, "fonts")


def _candidats():
    """Polices de remplacement : Nunito fournie + polices courantes du systeme."""
    c = [(f"Nunito {w}", os.path.join(FONT_DIR, f"Nunito-{w}.ttf")) for w in (300, 400, 500, 600, 700, 800)]
    dossiers = [os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"),
                "/usr/share/fonts/truetype/liberation", "/usr/share/fonts/truetype/dejavu",
                os.path.expanduser("~/.local/share/fonts")]
    systeme = [("Arial", "arial.ttf"), ("Arial Bold", "arialbd.ttf"), ("Calibri", "calibri.ttf"),
               ("Calibri Bold", "calibrib.ttf"), ("Verdana", "verdana.ttf"), ("Tahoma", "tahoma.ttf"),
               ("Segoe UI", "segoeui.ttf"), ("Times New Roman", "times.ttf"),
               ("Microsoft Sans Serif", "micross.ttf"),
               ("Liberation Sans", "LiberationSans-Regular.ttf"), ("Liberation Sans Bold", "LiberationSans-Bold.ttf"),
               ("Liberation Serif", "LiberationSerif-Regular.ttf"),
               ("DejaVu Sans", "DejaVuSans.ttf"), ("DejaVu Sans Bold", "DejaVuSans-Bold.ttf")]
    for nom, fichier in systeme:
        for d in dossiers:
            p = os.path.join(d, fichier)
            if os.path.exists(p):
                c.append((nom, p))
                break
    return [x for x in c if os.path.exists(x[1])]


CANDIDATS = _candidats()
BASE14 = {"Helvetica": "helv", "Helvetica-Bold": "hebo", "Helvetica-Oblique": "heit",
          "Helvetica-BoldOblique": "hebi", "Times-Roman": "tiro", "Times-Bold": "tibo",
          "Courier": "cour", "Courier-Bold": "cobo"}


# ----------------------------------------------------------------- polices
def _num(s):
    return float(s)


def _parse_cmap(data):
    """ToUnicode -> {code: texte}"""
    txt = data.decode("latin1")
    out = {}
    for blk in re.findall(r"beginbfchar(.*?)endbfchar", txt, re.S):
        for a, b in re.findall(r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", blk):
            out[int(a, 16)] = bytes.fromhex(b).decode("utf-16-be", "ignore")
    for blk in re.findall(r"beginbfrange(.*?)endbfrange", txt, re.S):
        for a, b, c in re.findall(r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", blk):
            u = int(c, 16)
            for i, code in enumerate(range(int(a, 16), int(b, 16) + 1)):
                out[code] = chr(u + i)
    return out


def _resolve(doc, xref, key):
    t, v = doc.xref_get_key(xref, key)
    if t == "xref":
        return doc.xref_object(int(v.split()[0]))
    return v if t != "null" else None


class PolicePDF:
    """Une police deja presente dans la page, reutilisable telle quelle."""

    def __init__(self, doc, xref, refname):
        self.doc, self.xref, self.ref = doc, xref, refname
        self.sub = doc.xref_get_key(xref, "Subtype")[1].lstrip("/")
        self.base = (doc.xref_get_key(xref, "BaseFont")[1] or "").lstrip("/").replace("#20", " ")
        self.code_of = {}          # caractere -> code
        self.width = {}            # code -> largeur pour 1 pt de corps
        self.flip = False
        self.octets = 1
        tu = doc.xref_get_key(xref, "ToUnicode")
        cmap = _parse_cmap(doc.xref_stream(int(tu[1].split()[0]))) if tu[0] == "xref" else {}
        if self.sub == "Type0":
            self.octets = 2
            desc = int(doc.xref_get_key(xref, "DescendantFonts")[1].strip("[] ").split()[0])
            dw = doc.xref_get_key(desc, "DW")
            self.dw = _num(dw[1]) / 1000 if dw[0] == "int" or dw[0] == "real" else 1.0
            w = _resolve(doc, desc, "W") or ""
            w = re.sub(r"(\d+) 0 R", lambda m: doc.xref_object(int(m.group(1))), w)
            self._parse_W(w)
            fd = int(doc.xref_get_key(desc, "FontDescriptor")[1].split()[0])
        elif self.sub == "Type3":
            fm = [float(v) for v in doc.xref_get_key(xref, "FontMatrix")[1].strip("[] ").split()]
            self.flip = fm[3] < 0
            first = int(doc.xref_get_key(xref, "FirstChar")[1])
            ws = (_resolve(doc, xref, "Widths") or "").strip("[] ").split()
            for i, v in enumerate(ws):
                self.width[first + i] = float(v) * fm[0]
            fd = int(doc.xref_get_key(xref, "FontDescriptor")[1].split()[0])
        else:  # Type1 / TrueType simples
            fd = None
            if self.base in BASE14:
                f = fitz.Font(BASE14[self.base])
                enc = doc.xref_get_key(xref, "Encoding")[1]
                haut = 256 if enc == "/WinAnsiEncoding" else 127   # accents seulement si WinAnsi
                for c in range(32, haut):
                    try:
                        ch = bytes([c]).decode("cp1252")
                    except UnicodeDecodeError:
                        continue
                    if f.has_glyph(ord(ch)):
                        cmap.setdefault(c, ch)
                        self.width[c] = f.glyph_advance(ord(ch))
            t = doc.xref_get_key(xref, "FontDescriptor")
            fd = int(t[1].split()[0]) if t[0] == "xref" else None
        for code, ch in cmap.items():
            if len(ch) == 1 and ch not in self.code_of and ch != "�":
                self.code_of[ch] = code
        self.fontname = doc.xref_get_key(fd, "FontName")[1].lstrip("/") if fd else self.base
        wt = doc.xref_get_key(fd, "FontWeight")[1] if fd else ""
        self.weight = int(float(wt)) if wt and wt != "null" else (700 if "Bold" in self.base else 400)

    def _parse_W(self, w):
        toks = re.findall(r"\[|\]|[-\d.]+", w)
        if toks and toks[0] == "[" and toks[-1] == "]":
            toks = toks[1:-1]
        i = 0
        while i < len(toks):
            c1 = int(float(toks[i]))
            if toks[i + 1] == "[":
                j, k = i + 2, 0
                while toks[j] != "]":
                    self.width[c1 + k] = float(toks[j]) / 1000
                    j, k = j + 1, k + 1
                i = j + 1
            else:
                c2, v = int(float(toks[i + 1])), float(toks[i + 2]) / 1000
                for c in range(c1, c2 + 1):
                    self.width[c] = v
                i += 3

    def famille(self):
        """Cle de famille : nom sans prefixe de sous-ensemble ni numero de decoupe."""
        n = re.sub(r"^[A-Z]{6}\+", "", self.fontname or self.base).lstrip("*")
        n = re.sub(r"(-\d+)?(-Identity-H)?$", "", n)
        return (n, self.weight)

    def a(self, ch):
        return ch in self.code_of

    def avance(self, ch):
        return self.width.get(self.code_of[ch], getattr(self, "dw", 0.5))


class PoliceIncorporee:
    """Police ajoutee au PDF quand aucun glyphe d'origine n'existe."""

    def __init__(self, nom, fichier):
        self.nom, self.fichier, self.font = nom, fichier, fitz.Font(fontfile=fichier)
        self.flip = False

    def a(self, ch):
        return self.font.has_glyph(ord(ch))

    def avance(self, ch):
        return self.font.text_length(ch, fontsize=1)


# ----------------------------------------------------------------- moteur
class Editeur:
    def __init__(self, chemin_ou_doc):
        self.doc = chemin_ou_doc if isinstance(chemin_ou_doc, fitz.Document) else fitz.open(chemin_ou_doc)
        self.journal = []

    def _polices(self, page):
        if not hasattr(page, "_ph_polices"):
            page._ph_polices = {}
            for f in page.get_fonts(full=True):
                try:
                    page._ph_polices[f[0]] = PolicePDF(self.doc, f[0], f[4])
                except Exception as e:  # police exotique : ignoree
                    self.journal.append(f"police {f[0]} ignoree ({e})")
        return page._ph_polices

    def _police_du_span(self, page, span):
        pol = self._polices(page)
        m = re.search(r"\((\d+) 0 R\)", span["font"])  # Type3 : "Type3 (7 0 R)"
        if m:
            return pol.get(int(m.group(1)))
        def norm(n):
            n = re.sub(r"^[A-Z]{6}\+", "", n.replace(" ", "")).lstrip("*")
            return re.sub(r"-Identity-H$", "", n)
        nom = norm(span["font"])
        for p in pol.values():
            if norm(p.base) == nom:
                return p
        return None

    def _lignes(self, page):
        d = page.get_text("rawdict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
        for b in d["blocks"]:
            for l in b.get("lines", []):
                chars = []
                for s in l["spans"]:
                    for c in s["chars"]:
                        chars.append((c, s))
                if chars:
                    yield chars

    def _choisir_par_rendu(self, page, chars, exclure=()):
        """Compare le rendu des lettres d'origine avec chaque police candidate."""
        s0 = chars[0][1]
        texte = "".join(c["c"] for c, _ in chars)
        r = fitz.Rect()
        for c, _ in chars:
            r |= fitz.Rect(c["bbox"])
        r = r + (-1, -2, 1, 2)
        zoom = 6
        ref = page.get_pixmap(clip=r, matrix=fitz.Matrix(zoom, zoom), colorspace=fitz.csGRAY)
        import numpy as np
        A = np.frombuffer(ref.samples, np.uint8).reshape(ref.h, ref.w) < 128
        meilleur = None
        for nom, fichier in CANDIDATS:
            if nom in exclure:
                continue
            tmp = fitz.open()
            pg = tmp.new_page(width=page.rect.width, height=page.rect.height)
            pg.insert_font(fontname="cand", fontfile=fichier)
            pg.insert_text(chars[0][0]["origin"], texte, fontname="cand", fontsize=s0["size"])
            pm = pg.get_pixmap(clip=r, matrix=fitz.Matrix(zoom, zoom), colorspace=fitz.csGRAY)
            B = np.frombuffer(pm.samples, np.uint8).reshape(pm.h, pm.w) < 128
            h, w = min(A.shape[0], B.shape[0]), min(A.shape[1], B.shape[1])
            a, b = A[:h, :w], B[:h, :w]
            score = (a & b).sum() / max(1, (a | b).sum())
            if meilleur is None or score > meilleur[0]:
                meilleur = (score, nom, fichier)
        return meilleur

    def occurrences(self, num_page, ancien, casse=True, accents=True):
        """Liste des (chars, debut, fin) ou se trouve 'ancien' sur la page."""
        import unicodedata
        def norm(t):
            if not casse:
                t = t.lower()
            if not accents:
                t = "".join(ch for ch in unicodedata.normalize("NFD", t) if unicodedata.category(ch) != "Mn")
            return t
        page = self.doc[num_page]
        res, cible = [], norm(ancien)
        for chars in self._lignes(page):
            brut = "".join(c["c"] for c, _ in chars)
            texte = norm(brut) if len(norm(brut)) == len(brut) else brut
            i = texte.find(cible)
            while i >= 0 and cible:
                res.append((chars, i, i + len(ancien)))
                i = texte.find(cible, i + len(cible))
        return res

    def _police_par_nom(self, p):
        """Meme famille et meme graisse que la police d'origine, si disponible."""
        if p is None:
            return None
        nom, poids = p.famille()
        fam = nom.split("-")[0].split(",")[0].strip()
        gras = poids >= 600 or "Bold" in nom
        equivalents = {"Helvetica": ["Arial", "Liberation Sans"], "Arial": ["Arial", "Liberation Sans"],
                       "ArialMT": ["Arial", "Liberation Sans"], "Times": ["Times New Roman", "Liberation Serif"],
                       "TimesNewRoman": ["Times New Roman", "Liberation Serif"], "Nunito": ["Nunito"]}
        voulus = [f"{fam} {poids}"]
        for f in equivalents.get(fam, [fam]):
            voulus.append(f"{f} Bold" if gras else f)
        for v in voulus:
            for n, f in CANDIDATS:
                if n.lower() == v.lower():
                    return PoliceIncorporee(n, f)
        return None

    def remplacer(self, num_page, ancien, nouveau, occurrence=1, zone=None, casse=True, accents=True):
        page = self.doc[num_page]
        occ = self.occurrences(num_page, ancien, casse, accents)
        if zone is not None:
            zone = fitz.Rect(zone)
            occ = [o for o in occ if any(fitz.Rect(c["bbox"]).intersects(zone) for c, _ in o[0][o[1]:o[2]])] or occ
            occurrence = 1
        if len(occ) < occurrence:
            raise ValueError(f"'{ancien}' introuvable page {num_page + 1}")
        chars, deb, fin = occ[occurrence - 1]
        return self._remplacer_dans_ligne(page, chars, deb, fin, nouveau)

    def remplacer_tout(self, ancien, nouveau, casse=True, accents=True):
        """Remplace toutes les occurrences du document ; renvoie le nombre.
        On part de la fin de chaque page : les occurrences precedentes ne bougent pas."""
        n = 0
        for num in range(len(self.doc)):
            total = len(self.occurrences(num, ancien, casse, accents))
            for k in range(total - 1, -1, -1):
                occ = self.occurrences(num, ancien, casse, accents)
                chars, deb, fin = occ[k]
                self._remplacer_dans_ligne(self.doc[num], chars, deb, fin, nouveau)
                n += 1
        return n

    def _remplacer_dans_ligne(self, page, chars, deb, fin, nouveau):
        pol = self._polices(page)
        # 1) style : celui du 1er caractere remplace, applique a tout le fragment
        s_ref = chars[deb][1]
        p_ref = self._police_du_span(page, s_ref)
        size = s_ref["size"]
        coul = fitz.sRGB_to_pdf(s_ref["color"])
        # espacement entre lettres mesure sur la ligne (equivalent du Tc)
        ecarts = []
        for k in range(len(chars) - 1):
            (c1, s1), (c2, s2) = chars[k], chars[k + 1]
            p1 = self._police_du_span(page, s1)
            if p1 and p1.a(c1["c"]) and c1["c"] != " " and s1["size"] == s2["size"]:
                ecarts.append(c2["origin"][0] - c1["origin"][0] - p1.avance(c1["c"]) * s1["size"])
        tc = sorted(ecarts)[len(ecarts) // 2] if ecarts else 0
        tc = max(-0.5, min(0.8, tc))
        # 2) suite de la ligne a decaler si la longueur change
        suite = chars[fin:]
        a_ecrire = [(ch, s_ref) for ch in nouveau] + [(c["c"], s) for c, s in suite]
        # 3) choix de la police caractere par caractere
        soeurs = [p for p in pol.values() if p_ref and p.famille() == p_ref.famille()]
        repli = None
        plan, x = [], chars[deb][0]["origin"][0]
        y = chars[deb][0]["origin"][1]
        for ch, s in a_ecrire:
            p_span = self._police_du_span(page, s) if s is not s_ref else p_ref
            cible = None
            if p_span and p_span.a(ch):
                cible, how = p_span, "glyphe d'origine"
            else:
                fam = [p for p in pol.values() if p_span and p.famille() == p_span.famille()]
                for p in fam:
                    if p.a(ch):
                        cible, how = p, f"glyphe d'une police soeur ({p.ref})"
                        break
            if cible is None:
                if repli is None:
                    repli = self._police_par_nom(p_span or p_ref)
                    if repli:
                        self.journal.append(f"police de remplacement choisie par nom et graisse : {repli.nom}")
                    else:
                        sc = self._choisir_par_rendu(page, chars[deb:fin] or chars[:deb][-5:])
                        repli = PoliceIncorporee(sc[1], sc[2])
                        self.journal.append(f"police de remplacement choisie par comparaison du rendu : {sc[1]} (ressemblance {sc[0]:.0%})")
                cible, how = repli, f"police de remplacement {repli.nom}"
            sz = s["size"] if s is not s_ref else size
            plan.append((ch, cible, sz, fitz.sRGB_to_pdf(s["color"]) if s is not s_ref else coul, x, how))
            x += cible.avance(ch) * sz + (tc if ch != " " else tc)
        # 4) effacer l'ancien texte (fragment + suite de ligne), sans toucher images ni traits
        zone = fitz.Rect()
        for c, _ in chars[deb:]:
            zone |= fitz.Rect(c["bbox"])
        h = zone.height
        zone = fitz.Rect(zone.x0 + 0.3, zone.y0 + h * 0.25, zone.x1 + 0.5, zone.y1 - h * 0.25)
        page.add_redact_annot(zone, fill=False)
        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE,
                              graphics=fitz.PDF_REDACT_LINE_ART_NONE,
                              text=fitz.PDF_REDACT_TEXT_REMOVE)
        # 5) reecrire
        self._ecrire(page, plan, y)
        usages = {}
        for ch, cible, *_r, how in plan[: len(nouveau)]:
            usages.setdefault(how, []).append(ch)
        self.journal.append(f"'{''.join(c['c'] for c, _ in chars[deb:fin])}' -> '{nouveau}' : " +
                            "; ".join(f"{how} [{''.join(v)}]" for how, v in usages.items()) +
                            f" ; corps {size:.1f} pt, interlettrage {tc:+.2f} pt")

    def _ecrire(self, page, plan, y):
        inv = ~page.transformation_matrix
        flux = ["q"]
        incorporees = {}
        for ch, cible, sz, coul, x, how in plan:
            if ch == " ":
                continue
            if isinstance(cible, PoliceIncorporee):
                alias = incorporees.get(cible.fichier)
                if alias is None:
                    alias = f"PhilF{len(incorporees)}"
                    page.insert_font(fontname=alias, fontfile=cible.fichier)
                    incorporees[cible.fichier] = alias
                flux.append(None)  # marqueur : on ecrira via insert_text apres
                page.insert_text((x, y), ch, fontname=alias, fontsize=sz, color=coul)
                continue
            pt = fitz.Point(x, y) * inv
            # espace glyphe deja remis a l'endroit par la FontMatrix : toujours positif ici
            d = sz
            code = cible.code_of[ch].to_bytes(cible.octets, "big").hex()
            flux.append(f"BT /{cible.ref} 1 Tf {sz:.3f} 0 0 {d:.3f} {pt.x:.3f} {pt.y:.3f} Tm "
                        f"{coul[0]:.3f} {coul[1]:.3f} {coul[2]:.3f} rg <{code}> Tj ET")
        flux = [f for f in flux if f] + ["Q"]
        # la suppression de l'ancien texte peut retirer une police devenue inutilisee : on la remet
        presentes = {f[4] for f in page.get_fonts(full=True)}
        for ch, cible, *_r in plan:
            if isinstance(cible, PolicePDF) and cible.ref not in presentes:
                t, v = self.doc.xref_get_key(page.xref, "Resources")
                if t == "xref":
                    rx = int(v.split()[0])
                    self.doc.xref_set_key(rx, f"Font/{cible.ref}", f"{cible.xref} 0 R")
                else:
                    self.doc.xref_set_key(page.xref, f"Resources/Font/{cible.ref}", f"{cible.xref} 0 R")
                presentes.add(cible.ref)
        if len(flux) > 2:
            page.wrap_contents()
            x = self.doc.get_new_xref()
            self.doc.update_object(x, "<<>>")
            self.doc.update_stream(x, ("\n".join(flux)).encode())
            cont = page.get_contents()
            self.doc.xref_set_key(page.xref, "Contents", "[" + " ".join(f"{c} 0 R" for c in cont + [x]) + "]")

    def ajouter_texte(self, num_page, point, texte, taille=None):
        """Ajoute du texte avec la police dominante de la page (glyphes d'origine si possible)."""
        page = self.doc[num_page]
        lignes = list(self._lignes(page))
        if not lignes:
            page.insert_text(point, texte, fontname="helv", fontsize=taille or 11)
            return
        compte = {}
        for chars in lignes:
            for c, s in chars:
                cle = (s["font"], round(s["size"], 1), s["color"])
                compte[cle] = compte.get(cle, 0) + 1
        dom = max(compte, key=compte.get)
        span = next(s for chars in lignes for c, s in chars if (s["font"], round(s["size"], 1), s["color"]) == dom)
        p = self._police_du_span(page, span)
        sz = taille or span["size"]
        coul = fitz.sRGB_to_pdf(span["color"])
        soeurs = [q for q in self._polices(page).values() if p and q.famille() == p.famille()]
        plan, x, repli = [], point[0], None
        for ch in texte:
            cible = next((q for q in ([p] if p else []) + soeurs if q.a(ch)), None)
            if cible is None:
                if repli is None:
                    repli = self._police_par_nom(p)
                    if repli is None:
                        ref = next(chars for chars in lignes if any(s is span for _, s in chars))
                        sc = self._choisir_par_rendu(page, ref[:12])
                        repli = PoliceIncorporee(sc[1], sc[2])
                cible = repli
            plan.append((ch, cible, sz, coul, x, ""))
            x += cible.avance(ch) * sz
        self._ecrire(page, plan, point[1])
        self.journal.append(f"texte ajouté avec la police de la page ({p.fontname if p else '?'}, {sz:.1f} pt)")

    def enregistrer(self, chemin):
        self.doc.subset_fonts()
        self.doc.save(chemin, garbage=3, deflate=True)
