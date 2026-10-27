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
import json, os, re, sys
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
def _effacer_lettres(page, chars):
    """Marque chaque lettre a effacer par un petit carre en son centre : rien d'autre autour n'est touche
    (une ligne penchee a un cadre qui deborde sur ses voisines)."""
    for c, _s in chars:
        b = fitz.Rect(c["bbox"])
        if b.is_empty:
            continue
        m = fitz.Point((b.x0 + b.x1) / 2, (b.y0 + b.y1) / 2)
        e = max(0.4, min(b.width, b.height) * 0.2)
        page.add_redact_annot(fitz.Rect(m.x - e, m.y - e, m.x + e, m.y + e), fill=False)


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
        import math
        page = self.doc[num_page]
        zone = fitz.Rect(zone)
        lignes = [([(c, sp) for sp in l["spans"] for c in sp["chars"]], l["dir"])
                  for b in page.get_text("rawdict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"] for l in b.get("lines", [])]
        for chars, direction in lignes:
            if not chars:
                continue
            angle = math.degrees(math.atan2(-direction[1], direction[0]))    # une ligne tournee le reste
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
                plan.append((ch, cible, s["size"], fitz.sRGB_to_pdf(s["color"]), c["origin"][0] + dx, "", c["origin"][1] + dy,
                             angle if abs(angle) > 0.05 else 0))
            h = r.height
            if abs(angle) <= 0.05:
                page.add_redact_annot(fitz.Rect(r.x0 + 0.3, r.y0 + h * 0.25, r.x1 + 0.5, r.y1 - h * 0.25), fill=False)
            else:
                _effacer_lettres(page, chars)
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

    # ---- paragraphes ecrits par PhilPDF : gardes dans le PDF (texte exact, retours a la ligne compris)
    CLE_PARAS = "PhilPDFParagraphes"

    def _registre(self):
        try:
            t, v = self.doc.xref_get_key(self.doc.pdf_catalog(), self.CLE_PARAS)
            return json.loads(v) if t == "string" and v else {}
        except Exception:
            return {}

    def _ecrire_registre(self, reg):
        try:
            self.doc.xref_set_key(self.doc.pdf_catalog(), self.CLE_PARAS,
                                  fitz.get_pdf_str(json.dumps(reg, ensure_ascii=True)))
        except Exception:
            pass

    def _retenir_paragraphe(self, num_page, rect, texte, ancien=None):
        reg = self._registre()
        cle = str(self.doc[num_page].xref)
        l = [e for e in reg.get(cle, []) if not (ancien is not None and fitz.Rect(e["r"]).intersects(ancien))
             and not fitz.Rect(e["r"]).intersects(rect)]
        l.append({"r": [round(v, 2) for v in rect], "t": texte})
        reg[cle] = l
        self._ecrire_registre(reg)

    @staticmethod
    def _norm(t):
        return " ".join(t.split())

    def _paragraphes_retenus(self, page, lignes):
        """[(lignes, texte exact, rect)] des paragraphes ecrits par PhilPDF encore intacts sur la page."""
        out = []
        for e in self._registre().get(str(page.xref), []):
            r = fitz.Rect(e["r"]) + (-2, -2, 2, 2)
            dedans = sorted([l for l in lignes if r.contains(fitz.Point((l["rect"].x0 + l["rect"].x1) / 2,
                                                                       (l["rect"].y0 + l["rect"].y1) / 2))],
                            key=lambda l: l["base"])
            if dedans and self._norm(self._texte_paragraphe(dedans)[0]) == self._norm(e["t"]):
                out.append((dedans, e["t"], r))
        return out

    def _bords_horizontaux(self, page):
        """Traits et bords de fonds (tableaux, bandeaux) : un paragraphe ne les traverse pas."""
        if getattr(self, "_bords_cache", (None,))[0] is page.xref:
            return self._bords_cache[1]
        bords = []
        try:
            for d in page.get_drawings():
                for it in d.get("items", []):
                    if it[0] == "re":
                        rr = fitz.Rect(it[1])
                        if rr.height > 2 and d.get("fill") is not None:
                            bords += [(rr.x0, rr.x1, rr.y0), (rr.x0, rr.x1, rr.y1)]
                        elif rr.height <= 2:
                            bords.append((rr.x0, rr.x1, (rr.y0 + rr.y1) / 2))
                    elif it[0] == "l":
                        a, b = it[1], it[2]
                        if abs(a.y - b.y) < 1:
                            bords.append((min(a.x, b.x), max(a.x, b.x), a.y))
        except Exception:
            pass
        self._bords_cache = (page.xref, bords)
        return bords

    def paragraphes_page(self, num_page):
        """Rectangles des paragraphes de plusieurs lignes (pour les signaler par un trait a gauche)."""
        page = self.doc[num_page]
        lignes = self._infos_lignes(page)
        vus, out = set(), []
        retenus = self._paragraphes_retenus(page, lignes)
        for l in lignes:
            if id(l) in vus:
                continue
            c = fitz.Point(l["rect"].x0 + 1, (l["rect"].y0 + l["rect"].y1) / 2)
            p = self.paragraphe_a(num_page, c, lignes, retenus)
            if not p:
                continue
            for x in p["lignes"]:
                vus.add(id(x))
            if len(p["lignes"]) > 1:
                out.append((p["rect"], bool(p.get("retenu"))))
        return out

    def paragraphe_a(self, num_page, pt, lignes=None, retenus=None):
        """Paragraphe sous le point : lignes de la meme colonne, de meme taille, regulierement espacees.
        Renvoie {"lignes": [...], "rect", "texte", "taille", "interligne", "justifie"} ou None."""
        page = self.doc[num_page]
        lignes = lignes if lignes is not None else self._infos_lignes(page)
        pt = fitz.Point(pt)
        sous = [l for l in lignes if (l["rect"] + (-1, -2, 1, 2)).contains(pt)]
        dep = min(sous, key=lambda l: abs((l["rect"].y0 + l["rect"].y1) / 2 - pt.y)) if sous else None
        if dep is None:
            return None
        retenus = retenus if retenus is not None else self._paragraphes_retenus(page, lignes)
        exact = None
        pris = {id(x) for ls, _t, _r in retenus for x in ls}
        for ls, t, _r in retenus:
            if any(x is dep for x in ls):
                para, exact = list(ls), t
                break
        else:
            para = [dep]
        bords = self._bords_horizontaux(page)

        def traverse_bord(a, b):
            ya, yb = sorted(((a["rect"].y0 + a["rect"].y1) / 2, (b["rect"].y0 + b["rect"].y1) / 2))
            g, d = min(a["x0"], b["x0"]) - 4, max(a["x1"], b["x1"]) + 4
            return any(ya + 0.5 < y < yb - 0.5 and x0 <= g and x1 >= d for x0, x1, y in bords)

        def meme_colonne(a, b):
            inter = min(a["x1"], b["x1"]) - max(a["x0"], b["x0"])
            return inter > 0.4 * min(a["x1"] - a["x0"], b["x1"] - b["x0"]) and abs(a["x0"] - b["x0"]) < max(4 * a["taille"], 40)

        pas = None
        for sens in ((1, -1) if exact is None else ()):
            cur = dep
            while True:
                cands = [l for l in lignes if l not in para and id(l) not in pris and (l["base"] - cur["base"]) * sens > 0.5
                         and meme_colonne(cur, l) and abs(l["taille"] - cur["taille"]) <= 0.8]
                if not cands:
                    break
                nxt = min(cands, key=lambda l: abs(l["base"] - cur["base"]))
                d = abs(nxt["base"] - cur["base"])
                if d > 1.8 * cur["taille"] or (pas and d > pas * 1.3) or traverse_bord(cur, nxt):
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
        return {"lignes": para, "rect": r, "texte": exact if exact is not None else self._texte_paragraphe(para)[0],
                "retenu": exact is not None, "taille": dep["taille"],
                "interligne": interligne, "justifie": justifie, "x0": min(l["x0"] for l in para), "x1": droite,
                "retrait": para[0]["x0"] - min(l["x0"] for l in para)}

    @staticmethod
    def _texte_paragraphe(lignes):
        """Texte continu (lignes recollees, cesures retirees) et style de chaque caractere.
        Une ligne qui s'arrete bien avant la marge alors que le premier mot de la suivante y tenait : c'etait un
        vrai retour a la ligne (liste, montants...), garde tel quel."""
        texte, styles = "", []
        droite = max((l["x1"] for l in lignes), default=0)

        def premier_mot(l):
            vis = [c for c, _sp in l["chars"]]
            while vis and not vis[0]["c"].strip():
                vis.pop(0)
            fin = next((k for k, c in enumerate(vis) if not c["c"].strip()), len(vis))
            return (vis[fin - 1]["bbox"][2] - vis[0]["bbox"][0]) if fin else 0
        precedente = None
        largeurs = [l["x1"] - l["x0"] for l in lignes[:-1]]
        # lignes de longueurs tres inegales (hors derniere) : c'est une liste, pas un texte qui revient a la ligne
        liste = len(largeurs) >= 2 and (max(largeurs) - min(largeurs)) > 0.3 * max(largeurs)
        for l in lignes:
            chars = [(c, sp) for c, sp in l["chars"]]
            while chars and not chars[-1][0]["c"].strip():
                chars.pop()
            while chars and not chars[0][0]["c"].strip():
                chars.pop(0)
            if not chars:
                continue
            if texte:
                place = droite - precedente["x1"]
                if texte.endswith("-") and chars[0][0]["c"].islower() and len(texte) > 1 and texte[-2].isalpha():
                    texte, styles = texte[:-1], styles[:-1]
                elif liste or place > premier_mot(l) + precedente["taille"] * 0.6:
                    texte += "\n"
                    styles.append(styles[-1])
                else:
                    texte += " "
                    styles.append(styles[-1])
            for c, sp in chars:
                texte += c["c"]
                styles.append(sp)
            precedente = l
        return texte, styles

    def modifier_paragraphe(self, num_page, para, nouveau, taille=None, couleur=None, police=None):
        """Reecrit le paragraphe avec le nouveau texte (retours a la ligne compris), coupe a la largeur d'origine.
        Chaque lettre garde le style (police, gras, taille, couleur) du texte d'origine a cet endroit."""
        import difflib
        page = self.doc[num_page]
        ancien, styles = self._texte_paragraphe(para["lignes"])
        if para.get("retenu") and len(para["texte"]) == len(ancien):
            ancien = para["texte"]                     # meme longueur : retours a la ligne exacts, styles alignes
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
        haut = min(l["rect"].y0 for l in para["lignes"][:1])
        tmax = max((l[2] for lg, _f in lignes for l in lg), default=para["taille"])
        self._retenir_paragraphe(num_page, fitz.Rect(x0, haut, x1, y - pas + tmax * 0.3), nouveau.rstrip("\n"), para["rect"])
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

    def geometrie_image(self, num_page, xref):
        """(centre, largeur, hauteur, angle) d'une image de la page ; angle en degres, sens inverse des aiguilles."""
        import math
        for info in self.doc[num_page].get_image_info(xrefs=True):
            if info.get("xref") == xref:
                # MuPDF donne le placement avec le carre unite retourne et en coordonnees d'ecran : on revient au PDF
                t = fitz.Matrix(1, 0, 0, -1, 0, 1) * fitz.Matrix(info["transform"]) * ~self.doc[num_page].transformation_matrix
                bb = fitz.Rect(info["bbox"])
                return (fitz.Point((bb.x0 + bb.x1) / 2, (bb.y0 + bb.y1) / 2), math.hypot(t.a, t.b), math.hypot(t.c, t.d),
                        round(math.degrees(math.atan2(t.b, t.a)), 2))
        raise ValueError("Image introuvable")

    def _placer(self, num_page, xref, centre, w, h, angle):
        """Change la place, la taille et l'angle d'une image sans la recopier : seule la matrice qui la place
        dans le contenu de la page est reecrite (image intacte, aucune recompression). False si introuvable."""
        import math, re
        page = self.doc[num_page]
        noms = [im[7] for im in page.get_images(full=True) if im[0] == xref]
        info = next((i for i in page.get_image_info(xrefs=True) if i.get("xref") == xref), None)
        if not noms or info is None:
            return False
        tpdf = fitz.Matrix(1, 0, 0, -1, 0, 1) * fitz.Matrix(info["transform"]) * ~page.transformation_matrix   # en PDF
        cp = centre * ~page.transformation_matrix
        a = math.radians(angle)
        flip = 1 if (tpdf.a * tpdf.d - tpdf.b * tpdf.c) >= 0 else -1          # image retournee : elle le reste
        voulu = fitz.Matrix(w, 0, 0, h * flip, -w / 2, -h * flip / 2) * \
            fitz.Matrix(math.cos(a), math.sin(a), -math.sin(a), math.cos(a), 0, 0) * fitz.Matrix(1, 0, 0, 1, cp.x, cp.y)
        motif = re.compile(r"([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+cm\s*/("
                           + "|".join(re.escape(n) for n in noms) + r")\s+Do")
        for cx in page.get_contents():
            flux = self.doc.xref_stream(cx).decode("latin-1")
            m = list(motif.finditer(flux))
            if len(m) != 1:
                continue
            local = fitz.Matrix(*[float(x) for x in m[0].groups()[:6]])
            exterieur = ~local * tpdf                      # transformations deja en place autour (q ... cm)
            nl = voulu * ~exterieur
            nouveau = f"{nl.a:.5f} {nl.b:.5f} {nl.c:.5f} {nl.d:.5f} {nl.e:.4f} {nl.f:.4f} cm /{m[0].group(7)} Do"
            self.doc.update_stream(cx, (flux[:m[0].start()] + nouveau + flux[m[0].end():]).encode("latin-1"))
            return True
        return False

    def deplacer_image(self, num_page, xref, nouveau_rect):
        """Deplace ou agrandit une image ; une image tournee garde son angle (le cadre donne est son encombrement)."""
        import math
        page = self.doc[num_page]
        centre, w, h, angle = self.geometrie_image(num_page, xref)
        nr = fitz.Rect(nouveau_rect)
        a = math.radians(angle)
        if abs(angle) < 0.01:
            nw, nh = nr.width, nr.height
        else:
            k = nr.width / max(0.01, abs(w * math.cos(a)) + abs(h * math.sin(a)))
            nw, nh = w * k, h * k
        if not self._placer(num_page, xref, fitz.Point((nr.x0 + nr.x1) / 2, (nr.y0 + nr.y1) / 2), nw, nh, angle):
            src = self._pixmap_image(xref)                     # image dans un sous-objet : ancienne methode
            page.delete_image(xref)
            page.insert_image(nr, keep_proportion=False, **src)
        self.journal.append("image déplacée")

    def tourner_image(self, num_page, xref, delta):
        """Tourne une image de la page autour de son centre (delta en degres, sens inverse des aiguilles)."""
        centre, w, h, angle = self.geometrie_image(num_page, xref)
        nouvel = (angle + delta) % 360
        if not self._placer(num_page, xref, centre, w, h, nouvel):
            raise ValueError("Cette image est rangée dans un sous-objet de la page : rotation impossible ici")
        self.journal.append(f"image tournée ({nouvel:.0f}°)")
        return nouvel

    def tourner_lignes(self, num_page, zones, delta, centre=None):
        """Tourne une ligne ou un bloc de lignes autour de son centre, chaque lettre gardant police, taille et couleur
        (delta en degres, sens inverse des aiguilles d'une montre). Renvoie l'encombrement apres rotation."""
        import math
        page = self.doc[num_page]
        d = page.get_text("rawdict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
        choisies = []
        for b in d["blocks"]:
            for l in b.get("lines", []):
                chars = [(c, s) for s in l["spans"] for c in s["chars"]]
                if not chars:
                    continue
                r = fitz.Rect(l["bbox"])
                for z in zones:
                    z = fitz.Rect(z)
                    if r.intersects(z) and (r & z).get_area() >= 0.4 * min(r.get_area(), z.get_area()):
                        choisies.append((l, chars, r))
                        break
        if not choisies:
            raise ValueError("Texte introuvable à cet endroit")
        tout = fitz.Rect()
        for _l, _c, r in choisies:
            tout |= r
        cx, cy = (centre.x, centre.y) if centre else ((tout.x0 + tout.x1) / 2, (tout.y0 + tout.y1) / 2)
        a = math.radians(delta)
        ca, sa = math.cos(a), math.sin(a)
        plans = []
        for l, chars, r in choisies:
            dx_, dy_ = l["dir"]
            angle0 = math.degrees(math.atan2(-dy_, dx_))
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
                ox, oy = c["origin"]
                nx = cx + (ox - cx) * ca + (oy - cy) * sa
                ny = cy - (ox - cx) * sa + (oy - cy) * ca
                plan.append((ch, cible, s["size"], fitz.sRGB_to_pdf(s["color"]), nx, "", ny, angle0 + delta))
            plans.append(plan)
            _effacer_lettres(page, chars)
        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE, graphics=fitz.PDF_REDACT_LINE_ART_NONE,
                              text=fitz.PDF_REDACT_TEXT_REMOVE)
        for plan in plans:
            self._ecrire(page, [x for x in plan if x[1] is not None], plan[0][6])
        self.journal.append(f"texte tourné de {delta:+.0f}°, polices d'origine conservées")
        pts = [fitz.Point(cx + (x0 - cx) * ca + (y0 - cy) * sa, cy - (x0 - cx) * sa + (y0 - cy) * ca)
               for x0, y0 in ((tout.x0, tout.y0), (tout.x1, tout.y0), (tout.x0, tout.y1), (tout.x1, tout.y1))]
        return fitz.Rect(min(q.x for q in pts), min(q.y for q in pts), max(q.x for q in pts), max(q.y for q in pts))

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
            angle = entree[7] if len(entree) > 7 else 0
            if ch == " ":
                continue
            if isinstance(cible, PoliceIncorporee):
                alias = incorporees.get(cible.fichier)
                if alias is None:
                    alias = f"PhilF{len(incorporees)}"
                    page.insert_font(fontname=alias, fontfile=cible.fichier)
                    incorporees[cible.fichier] = alias
                flux.append(None)  # marqueur : on ecrira via insert_text apres
                if angle:
                    page.insert_text((x, y), ch, fontname=alias, fontsize=sz, color=coul,
                                     morph=(fitz.Point(x, y), fitz.Matrix(angle)))
                else:
                    page.insert_text((x, y), ch, fontname=alias, fontsize=sz, color=coul)
                continue
            pt = fitz.Point(x, y) * inv
            # espace glyphe deja remis a l'endroit par la FontMatrix : toujours positif ici
            d = sz
            code = cible.code_of[ch].to_bytes(cible.octets, "big").hex()
            if angle:
                import math
                ra = math.radians(angle)
                ca_, sa_ = math.cos(ra), math.sin(ra)
                flux.append(f"BT /{cible.ref} 1 Tf {sz * ca_:.4f} {sz * sa_:.4f} {-d * sa_:.4f} {d * ca_:.4f} {pt.x:.3f} {pt.y:.3f} Tm "
                            f"{coul[0]:.3f} {coul[1]:.3f} {coul[2]:.3f} rg <{code}> Tj ET")
                continue
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
        n, droite = 0, coin[0]
        for bloc in texte.split("\n"):
            ligne, larg = [], 0.0
            mots = bloc.split(" ")
            for m in mots + [None]:
                lm = sum((mesure.avance(c) if mesure.a(c) else 0.5) for c in (m or "")) * taille
                if m is None or (ligne and larg + espace + lm > largeur):
                    if ligne or m is None:
                        self.ajouter_texte(num_page, fitz.Point(coin[0], y), " ".join(ligne), taille, couleur, police)
                        droite = max(droite, coin[0] + larg)
                        y += taille * 1.22
                        n += 1
                    ligne, larg = ([m], lm) if m is not None else ([], 0.0)
                else:
                    larg += (espace if ligne else 0) + lm
                    ligne.append(m)
        if n > 1:
            self._retenir_paragraphe(num_page, fitz.Rect(coin[0] - 0.5, coin[1], max(droite, coin[0] + 5) + 1,
                                                         y - taille * 1.22 + taille * 0.3), texte.rstrip("\n"))
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
