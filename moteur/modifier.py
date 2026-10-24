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
    # polices libres "jumelles" (memes largeurs de lettres que les polices commerciales), fournies
    for nom, fichier in [("Liberation Sans", "LiberationSans-Regular"), ("Liberation Sans Bold", "LiberationSans-Bold"),
                         ("Liberation Sans Italic", "LiberationSans-Italic"), ("Liberation Sans Bold Italic", "LiberationSans-BoldItalic"),
                         ("Liberation Serif", "LiberationSerif-Regular"), ("Liberation Serif Bold", "LiberationSerif-Bold"),
                         ("Liberation Serif Italic", "LiberationSerif-Italic"), ("Liberation Serif Bold Italic", "LiberationSerif-BoldItalic"),
                         ("Liberation Mono", "LiberationMono-Regular"), ("Liberation Mono Bold", "LiberationMono-Bold"),
                         ("Carlito", "Carlito-Regular"), ("Carlito Bold", "Carlito-Bold"), ("Carlito Italic", "Carlito-Italic"),
                         ("Carlito Bold Italic", "Carlito-BoldItalic"), ("Caladea", "Caladea-Regular"), ("Caladea Bold", "Caladea-Bold")]:
        c.append((nom, os.path.join(FONT_DIR, fichier + ".ttf")))
    dossiers = [os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"),
                "/usr/share/fonts/truetype/liberation", "/usr/share/fonts/truetype/dejavu",
                os.path.expanduser("~/.local/share/fonts")]
    systeme = [("Arial", "arial.ttf"), ("Arial Bold", "arialbd.ttf"), ("Calibri", "calibri.ttf"),
               ("Calibri Bold", "calibrib.ttf"), ("Verdana", "verdana.ttf"), ("Tahoma", "tahoma.ttf"),
               ("Segoe UI", "segoeui.ttf"), ("Times New Roman", "times.ttf"),
               ("Microsoft Sans Serif", "micross.ttf"),
               ("Courier New", "cour.ttf"), ("Cambria", "cambria.ttc"),
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
            fc = doc.xref_get_key(xref, "FirstChar")
            ws = (_resolve(doc, xref, "Widths") or "").strip("[] ").split()
            if fc[0] == "int" and ws:                  # largeurs donnees par le PDF (ReportLab, Word...)
                first = int(fc[1])
                for i, v in enumerate(ws):
                    try:
                        self.width[first + i] = float(v) / 1000
                    except ValueError:
                        pass
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
                        self.width.setdefault(c, f.glyph_advance(ord(ch)))
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
                       "TimesNewRoman": ["Times New Roman", "Liberation Serif"],
                       "TimesNewRomanPSMT": ["Times New Roman", "Liberation Serif"],
                       "Courier": ["Courier New", "Liberation Mono"], "CourierNew": ["Courier New", "Liberation Mono"],
                       "Calibri": ["Calibri", "Carlito"], "Cambria": ["Cambria", "Caladea"],
                       "Microsoft Sans Serif": ["Microsoft Sans Serif", "Arial", "Liberation Sans"],
                       "Nunito": ["Nunito"]}
        voulus = [f"{fam} {poids}"]
        for f in equivalents.get(fam, [fam]):
            voulus.append(f"{f} Bold" if gras else f)
        for v in voulus:
            for n, f in CANDIDATS:
                if n.lower() == v.lower():
                    return PoliceIncorporee(n, f)
        return None

    def deplacer_ligne(self, num_page, zone, dx, dy):
        """Deplace une ligne entiere, chaque lettre gardant sa police, sa taille et sa couleur."""
        page = self.doc[num_page]
        zone = fitz.Rect(zone)
        for chars in self._lignes(page):
            r = fitz.Rect()
            for c, _ in chars:
                r |= fitz.Rect(c["bbox"])
            if not r.intersects(zone) or (r & zone).get_area() < 0.5 * min(r.get_area(), zone.get_area()):
                continue
            plan, repli = [], None
            for c, s in chars:
                ch = c["c"]
                p = self._police_du_span(page, s)
                cible = p if p and p.a(ch) else next((q for q in self._polices(page).values()
                                                      if p and q.famille() == p.famille() and q.a(ch)), None)
                if cible is None and ch != " ":
                    if repli is None:
                        repli = self._police_par_nom(p) or PoliceIncorporee(*self._choisir_par_rendu(page, chars[:12])[1:])
                    cible = repli
                plan.append((ch, cible, s["size"], fitz.sRGB_to_pdf(s["color"]), c["origin"][0] + dx, "", c["origin"][1] + dy))
            h = r.height
            page.add_redact_annot(fitz.Rect(r.x0 + 0.3, r.y0 + h * 0.25, r.x1 + 0.5, r.y1 - h * 0.25), fill=False)
            page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE, graphics=fitz.PDF_REDACT_LINE_ART_NONE,
                                  text=fitz.PDF_REDACT_TEXT_REMOVE)
            self._ecrire(page, [x for x in plan if x[1] is not None], plan[0][6])
            self.journal.append(f"ligne déplacée de {dx:+.0f} / {dy:+.0f} pt, polices d'origine conservées")
            return True
        raise ValueError("Ligne introuvable à cet endroit")

    def restyler_ligne(self, num_page, zone, taille=None, couleur=None, texte=None):
        """Change taille et/ou couleur (et eventuellement le texte) d'une ligne entiere."""
        page = self.doc[num_page]
        for chars in self._lignes(page):
            r = fitz.Rect()
            for c, _ in chars:
                r |= fitz.Rect(c["bbox"])
            if r.intersects(fitz.Rect(zone)):
                t = "".join(c["c"] for c, _ in chars).rstrip()
                n = len(t)
                return self._remplacer_dans_ligne(page, chars, 0, n, texte if texte is not None else t, taille, couleur)
        raise ValueError("Ligne introuvable à cet endroit")

    def ligne_a(self, num_page, zone):
        """(chars, rect, texte) de la ligne qui recoupe le plus la zone."""
        page = self.doc[num_page]
        zone = fitz.Rect(zone)
        meilleur = None
        for chars in self._lignes(page):
            r = fitz.Rect()
            for c, _ in chars:
                r |= fitz.Rect(c["bbox"])
            inter = (r & zone).get_area() if r.intersects(zone) else 0
            if inter > 0 and (meilleur is None or inter > meilleur[0]):
                meilleur = (inter, chars, r)
        if not meilleur:
            raise ValueError("Ligne introuvable à cet endroit")
        _, chars, r = meilleur
        return chars, r, "".join(c["c"] for c, _ in chars)

    def modifier_ligne(self, num_page, zone, nouveau, taille=None, couleur=None):
        """Remplace le texte d'une ligne. Seule la partie changee est reecrite, pour garder
        le style (gras, couleur) des parties intactes."""
        page = self.doc[num_page]
        chars, r, ancien = self.ligne_a(num_page, zone)
        ancien_net = ancien.rstrip()
        if not nouveau.strip():
            page.add_redact_annot(fitz.Rect(r.x0 + 0.3, r.y0 + r.height * 0.25, r.x1 + 0.5, r.y1 - r.height * 0.25), fill=False)
            page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE, graphics=fitz.PDF_REDACT_LINE_ART_NONE,
                                  text=fitz.PDF_REDACT_TEXT_REMOVE)
            self.journal.append("ligne supprimée")
            return
        if taille or couleur:
            return self._remplacer_dans_ligne(page, chars, 0, len(ancien_net), nouveau, taille, couleur)
        p = 0
        while p < min(len(ancien_net), len(nouveau)) and ancien_net[p] == nouveau[p]:
            p += 1
        s = 0
        while s < min(len(ancien_net), len(nouveau)) - p and ancien_net[-1 - s] == nouveau[-1 - s]:
            s += 1
        if p == len(ancien_net) == len(nouveau):
            return
        fin = len(ancien_net) - s
        mid = nouveau[p:len(nouveau) - s]
        if p == fin:   # insertion pure : on reecrit au moins une lettre pour prendre son style
            if p > 0:
                p -= 1
                mid = ancien_net[p] + mid
            else:
                fin += 1
                mid = mid + ancien_net[0]
        return self._remplacer_dans_ligne(page, chars, p, fin, mid)

    # ---- images
    # ------------------------------------------------------------- paragraphes
    def _infos_lignes(self, page):
        out = []
        for chars in self._lignes(page):
            vis = [(c, sp) for c, sp in chars if c["c"].strip()]
            if not vis:
                continue
            r = fitz.Rect()
            for c, _sp in chars:
                r |= fitz.Rect(c["bbox"])
            tailles = sorted(sp["size"] for _c, sp in vis)
            out.append({"chars": chars, "rect": r, "base": vis[0][0]["origin"][1], "x0": vis[0][0]["bbox"][0],
                        "x1": vis[-1][0]["bbox"][2], "taille": tailles[len(tailles) // 2],
                        "texte": "".join(c["c"] for c, _sp in chars).rstrip()})
        return out

    def paragraphe_a(self, num_page, pt):
        """Paragraphe sous le point : lignes de la meme colonne, de meme taille, regulierement espacees.
        Renvoie {"lignes": [...], "rect", "texte", "taille", "interligne", "justifie"} ou None."""
        page = self.doc[num_page]
        lignes = self._infos_lignes(page)
        pt = fitz.Point(pt)
        dep = next((l for l in lignes if (l["rect"] + (-1, -2, 1, 2)).contains(pt)), None)
        if dep is None:
            return None
        para = [dep]

        def meme_colonne(a, b):
            inter = min(a["x1"], b["x1"]) - max(a["x0"], b["x0"])
            return inter > 0.4 * min(a["x1"] - a["x0"], b["x1"] - b["x0"]) and abs(a["x0"] - b["x0"]) < max(4 * a["taille"], 40)

        pas = None
        for sens in (1, -1):
            cur = dep
            while True:
                cands = [l for l in lignes if l not in para and (l["base"] - cur["base"]) * sens > 0.5
                         and meme_colonne(cur, l) and abs(l["taille"] - cur["taille"]) <= 0.8]
                if not cands:
                    break
                nxt = min(cands, key=lambda l: abs(l["base"] - cur["base"]))
                d = abs(nxt["base"] - cur["base"])
                if d > 1.8 * cur["taille"] or (pas and d > pas * 1.3):
                    break
                # un trou (autre texte entre les deux) arrete le paragraphe
                if any(l is not nxt and meme_colonne(cur, l) and min(cur["base"], nxt["base"]) < l["base"] < max(cur["base"], nxt["base"])
                       for l in lignes):
                    break
                pas = pas or d
                para.append(nxt)
                cur = nxt
        para.sort(key=lambda l: l["base"])
        r = fitz.Rect()
        for l in para:
            r |= l["rect"]
        bases = [l["base"] for l in para]
        ecarts = sorted(b - a for a, b in zip(bases, bases[1:]))
        interligne = ecarts[len(ecarts) // 2] if ecarts else dep["taille"] * 1.2
        droite = max(l["x1"] for l in para)
        justifie = len(para) >= 3 and all(droite - l["x1"] < 1.5 for l in para[:-1])
        return {"lignes": para, "rect": r, "texte": self._texte_paragraphe(para)[0], "taille": dep["taille"],
                "interligne": interligne, "justifie": justifie, "x0": min(l["x0"] for l in para), "x1": droite,
                "retrait": para[0]["x0"] - min(l["x0"] for l in para)}

    @staticmethod
    def _texte_paragraphe(lignes):
        """Texte continu (lignes recollees, cesures retirees) et style de chaque caractere."""
        texte, styles = "", []
        for l in lignes:
            chars = [(c, sp) for c, sp in l["chars"]]
            while chars and not chars[-1][0]["c"].strip():
                chars.pop()
            while chars and not chars[0][0]["c"].strip():
                chars.pop(0)
            if not chars:
                continue
            if texte:
                if texte.endswith("-") and chars[0][0]["c"].islower() and len(texte) > 1 and texte[-2].isalpha():
                    texte, styles = texte[:-1], styles[:-1]
                else:
                    texte += " "
                    styles.append(styles[-1])
            for c, sp in chars:
                texte += c["c"]
                styles.append(sp)
        return texte, styles

    def modifier_paragraphe(self, num_page, para, nouveau, taille=None, couleur=None, police=None):
        """Reecrit le paragraphe avec le nouveau texte (retours a la ligne compris), coupe a la largeur d'origine.
        Chaque lettre garde le style (police, gras, taille, couleur) du texte d'origine a cet endroit."""
        import difflib
        page = self.doc[num_page]
        ancien, styles = self._texte_paragraphe(para["lignes"])
        if nouveau == ancien and not (taille or couleur or police):
            return None
        k = (taille / para["taille"]) if taille else 1.0
        # style de chaque nouveau caractere : celui du caractere d'origine correspondant
        st = [None] * len(nouveau)
        for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, ancien, nouveau, autojunk=False).get_opcodes():
            for j in range(j1, j2):
                i = min(i1 + (j - j1), i2 - 1) if i2 > i1 else max(0, i1 - 1)
                st[j] = styles[min(i, len(styles) - 1)] if styles else None
        pol = self._polices(page)
        repli_par_police = {}
        incorporee = PoliceIncorporee(os.path.basename(police), police) if police else None

        def cible_de(ch, sp):
            if incorporee:
                return incorporee if incorporee.a(ch) else None
            p_sp = self._police_du_span(page, sp)
            if p_sp and p_sp.a(ch):
                return p_sp
            for q in pol.values():
                if p_sp and q.famille() == p_sp.famille() and q.a(ch):
                    return q
            cle = p_sp.ref if p_sp else sp["font"]
            if cle not in repli_par_police:
                r = self._police_par_nom(p_sp) if p_sp else None
                if r is None:
                    sc = self._choisir_par_rendu(page, para["lignes"][0]["chars"][:12])
                    r = PoliceIncorporee(sc[1], sc[2])
                repli_par_police[cle] = r
                self.journal.append(f"police de remplacement : {r.nom}")
            r = repli_par_police[cle]
            return r if r.a(ch) else None
        # mots avec leurs lettres (police, taille, couleur, avance)
        lettres = []
        for ch, sp in zip(nouveau, st):
            if ch == "\n":
                lettres.append(("\n", None, 0, None, 0))
                continue
            sp = sp or styles[-1]
            sz = sp["size"] * k
            cible = cible_de(ch if ch != " " else "a", sp) if ch != " " else None
            if ch != " " and cible is None:
                continue
            av = (cible.avance(ch) if cible else (self._police_du_span(page, sp).avance(" ")
                                                    if self._police_du_span(page, sp) and self._police_du_span(page, sp).a(" ") else 0.28)) * sz
            coul = couleur or fitz.sRGB_to_pdf(sp["color"])
            lettres.append((ch, cible, sz, coul, av))
        # coupure en lignes a la largeur du paragraphe
        x0, x1 = para["x0"], para["x1"] + 0.5
        lignes, ligne, mot, larg_ligne, larg_mot = [], [], [], 0.0, 0.0
        retrait = para["retrait"]

        def fin_mot():
            nonlocal ligne, mot, larg_ligne, larg_mot
            dispo = x1 - x0 - (retrait if not lignes else 0)
            if ligne and larg_ligne + larg_mot > dispo:
                while ligne and ligne[-1][0] == " ":
                    larg_ligne -= ligne.pop()[4]
                lignes.append((ligne, False))
                ligne, larg_ligne = [], 0.0
            ligne += mot
            larg_ligne += larg_mot
            mot, larg_mot = [], 0.0
        for l in lettres:
            if l[0] == "\n":
                fin_mot()
                lignes.append((ligne, True))
                ligne, larg_ligne = [], 0.0
            elif l[0] == " ":
                fin_mot()
                if ligne:
                    ligne.append(l)
                    larg_ligne += l[4]
            else:
                mot.append(l)
                larg_mot += l[4]
        fin_mot()
        if ligne:
            lignes.append((ligne, True))
        # plan d'ecriture
        plan = []
        y = para["lignes"][0]["base"]
        pas = para["interligne"] * k
        for n, (ligne, fin_par) in enumerate(lignes):
            while ligne and ligne[-1][0] == " ":
                ligne = ligne[:-1]
            x = x0 + (retrait if n == 0 else 0)
            extra = 0.0
            if para["justifie"] and not fin_par:
                espaces = sum(1 for l in ligne if l[0] == " ")
                if espaces:
                    extra = (x1 - x - sum(l[4] for l in ligne)) / espaces
            for ch, cible, sz, coul, av in ligne:
                if ch != " ":
                    plan.append((ch, cible, sz, coul, x, "paragraphe", y))
                x += av + (extra if ch == " " else 0)
            y += pas
        # effacer l'ancien paragraphe (texte seulement), puis ecrire
        for l in para["lignes"]:
            r = l["rect"]
            page.add_redact_annot(fitz.Rect(r.x0 + 0.3, r.y0 + r.height * 0.25, r.x1 + 0.5, r.y1 - r.height * 0.25), fill=False)
        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE, graphics=fitz.PDF_REDACT_LINE_ART_NONE,
                              text=fitz.PDF_REDACT_TEXT_REMOVE)
        self._ecrire(page, plan, para["lignes"][0]["base"])
        en_plus = len(lignes) - len(para["lignes"])
        self.journal.append(f"paragraphe réécrit : {len(lignes)} ligne(s)" +
                            (f" ({en_plus:+d} par rapport à avant)" if en_plus else ""))
        return {"lignes": len(lignes), "en_plus": en_plus, "bas": y - pas}

    def images(self, num_page):
        """[(xref, rect)] des images visibles de la page."""
        out = []
        for info in self.doc[num_page].get_image_info(xrefs=True):
            if info.get("xref") and info.get("width", 2) > 1 and info.get("height", 2) > 1:
                out.append((info["xref"], fitz.Rect(info["bbox"])))
        return out

    def _pixmap_image(self, xref):
        info = self.doc.extract_image(xref)
        if info.get("smask"):
            pix = fitz.Pixmap(fitz.Pixmap(self.doc, xref), fitz.Pixmap(self.doc, info["smask"]))
            return dict(pixmap=pix)
        if info.get("ext") in ("jpeg", "jpg", "png", "jpx"):
            return dict(stream=info["image"])
        return dict(pixmap=fitz.Pixmap(self.doc, xref))

    def deplacer_image(self, num_page, xref, nouveau_rect):
        page = self.doc[num_page]
        src = self._pixmap_image(xref)
        page.delete_image(xref)
        page.insert_image(fitz.Rect(nouveau_rect), keep_proportion=False, **src)
        self.journal.append("image déplacée")

    def supprimer_image(self, num_page, xref):
        self.doc[num_page].delete_image(xref)
        self.journal.append("image supprimée")

    def remplacer_image(self, num_page, xref, rect, fichier):
        page = self.doc[num_page]
        page.delete_image(xref)
        page.insert_image(fitz.Rect(rect), filename=fichier)
        self.journal.append("image remplacée")

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

    def _remplacer_dans_ligne(self, page, chars, deb, fin, nouveau, taille=None, couleur=None):
        pol = self._polices(page)
        # 1) style : celui du 1er caractere remplace, applique a tout le fragment
        s_ref = chars[deb][1]
        p_ref = self._police_du_span(page, s_ref)
        size = taille or s_ref["size"]
        coul = couleur or fitz.sRGB_to_pdf(s_ref["color"])
        # espacement entre lettres mesure sur la ligne (equivalent du Tc)
        ecarts = []
        for k in range(len(chars) - 1):
            (c1, s1), (c2, s2) = chars[k], chars[k + 1]
            p1 = self._police_du_span(page, s1)
            if p1 and p1.a(c1["c"]) and c1["c"] != " " and s1["size"] == s2["size"]:
                ecarts.append(c2["origin"][0] - c1["origin"][0] - p1.avance(c1["c"]) * s1["size"])
        tc = sorted(ecarts)[len(ecarts) // 2] if ecarts else 0
        tc = max(-0.5, min(0.8, tc))
        # 2) toute la ligne est reecrite d'un seul tenant (debut garde a l'identique, suite decalee) :
        #    elle reste ainsi une seule ligne pour les modifications suivantes
        prefixe, suite = chars[:deb], chars[fin:]
        a_ecrire = [(ch, s_ref) for ch in nouveau] + [(c["c"], s) for c, s in suite]
        # 3) choix de la police caractere par caractere
        soeurs = [p for p in pol.values() if p_ref and p.famille() == p_ref.famille()]
        repli = None
        plan, x = [], chars[deb][0]["origin"][0] if deb < len(chars) else chars[-1][0]["origin"][0]
        y = chars[deb][0]["origin"][1] if deb < len(chars) else chars[-1][0]["origin"][1]
        for c, s in prefixe:
            p_s = self._police_du_span(page, s)
            cible = p_s if p_s and p_s.a(c["c"]) else next((q for q in pol.values() if p_s and q.famille() == p_s.famille() and q.a(c["c"])), None)
            if cible is not None or c["c"] == " ":
                plan.append((c["c"], cible, s["size"], fitz.sRGB_to_pdf(s["color"]), c["origin"][0], "prefixe", c["origin"][1]))
        n_prefixe = len(plan)
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
        # 4) effacer l'ancien texte (toute la ligne), sans toucher images ni traits
        zone = fitz.Rect()
        for c, _ in chars:
            zone |= fitz.Rect(c["bbox"])
        h = zone.height
        zone = fitz.Rect(zone.x0 + 0.3, zone.y0 + h * 0.25, zone.x1 + 0.5, zone.y1 - h * 0.25)
        page.add_redact_annot(zone, fill=False)
        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE,
                              graphics=fitz.PDF_REDACT_LINE_ART_NONE,
                              text=fitz.PDF_REDACT_TEXT_REMOVE)
        # 5) reecrire
        self._ecrire(page, [x for x in plan if x[1] is not None or x[0] == " "], y)
        usages = {}
        for entree in plan[n_prefixe: n_prefixe + len(nouveau)]:
            usages.setdefault(entree[5], []).append(entree[0])
        self.journal.append(f"'{''.join(c['c'] for c, _ in chars[deb:fin])}' -> '{nouveau}' : " +
                            "; ".join(f"{how} [{''.join(v)}]" for how, v in usages.items()) +
                            f" ; corps {size:.1f} pt, interlettrage {tc:+.2f} pt")

    def _ecrire(self, page, plan, y):
        inv = ~page.transformation_matrix
        flux = ["q"]
        incorporees = {}
        for entree in plan:
            ch, cible, sz, coul, x, how = entree[:6]
            if len(entree) > 6:
                y = entree[6]
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

    def ajouter_texte(self, num_page, point, texte, taille=None, couleur=None, police=None):
        if police:  # police choisie explicitement (fichier .ttf)
            page = self.doc[num_page]
            page.insert_font(fontname="PhilAjout", fontfile=police)
            page.insert_text(point, texte, fontname="PhilAjout", fontsize=taille or 11, color=couleur or (0, 0, 0))
            self.journal.append(f"texte ajouté ({os.path.basename(police)}, {taille or 11:.0f} pt)")
            return
        return self._ajouter_texte_auto(num_page, point, texte, taille, couleur)

    def ajouter_paragraphe(self, num_page, coin, texte, largeur, taille=11, couleur=None, police=None):
        """Bloc de texte sur plusieurs lignes : coupe a la largeur donnee, retours a la ligne respectes.
        coin = haut gauche du bloc. Police : fichier choisi, sinon celle de la page (glyphes d'origine)."""
        mesure = PoliceIncorporee(os.path.basename(police), police) if police else None
        if mesure is None:
            page = self.doc[num_page]
            lignes = list(self._lignes(page))
            p = None
            if lignes:
                compte = {}
                for chars in lignes:
                    for c, sp in chars:
                        compte[sp["font"]] = compte.get(sp["font"], 0) + 1
                fnt = max(compte, key=compte.get)
                sp = next(sp for chars in lignes for c, sp in chars if sp["font"] == fnt)
                p = self._police_du_span(page, sp)
            mesure = self._police_par_nom(p) if p else None
            mesure = mesure or PoliceIncorporee("Liberation Sans", os.path.join(FONT_DIR, "LiberationSans-Regular.ttf"))
        espace = mesure.avance(" ") * taille if mesure.a(" ") else taille * 0.28
        y = coin[1] + taille * 0.9
        n = 0
        for bloc in texte.split("\n"):
            ligne, larg = [], 0.0
            mots = bloc.split(" ")
            for m in mots + [None]:
                lm = sum((mesure.avance(c) if mesure.a(c) else 0.5) for c in (m or "")) * taille
                if m is None or (ligne and larg + espace + lm > largeur):
                    if ligne or m is None:
                        self.ajouter_texte(num_page, fitz.Point(coin[0], y), " ".join(ligne), taille, couleur, police)
                        y += taille * 1.22
                        n += 1
                    ligne, larg = ([m], lm) if m is not None else ([], 0.0)
                else:
                    larg += (espace if ligne else 0) + lm
                    ligne.append(m)
        self.journal.append(f"bloc de texte ajouté : {n} ligne(s)")
        return n

    def _ajouter_texte_auto(self, num_page, point, texte, taille=None, couleur=None):
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
        coul = couleur or fitz.sRGB_to_pdf(span["color"])
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
