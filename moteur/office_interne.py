"""Conversion en PDF sans Office ni LibreOffice (dernier recours) : Word (.docx), Excel (.xlsx, .csv) et texte (.txt)
mis en page par PhilPDF lui-meme (PyMuPDF, Story HTML).

Le rendu est simplifie mais fidele au contenu : titres, gras / italique / souligne, couleurs, tailles, alignements,
listes, tableaux (fonds de cellules, largeurs, bordures), images, orientation et marges de la page. Ce qui n'est pas
repris (en-tetes et pieds de page, zones de texte, notes) est dit dans l'avertissement renvoye.
"""
import csv
import html
import os

import pymupdf as fitz

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"

INTERNES = (".docx", ".docm", ".dotx", ".xlsx", ".xlsm", ".csv", ".txt")

CSS = """
body { margin: 0; padding: 0; font-family: sans-serif; font-size: 11pt; line-height: 1.2; }
p { margin: 0 0 4pt 0; }
h1 { font-size: 16pt; margin: 10pt 0 4pt 0; } h2 { font-size: 13pt; margin: 8pt 0 4pt 0; }
h3 { font-size: 12pt; margin: 6pt 0 3pt 0; }
table { border-collapse: collapse; margin: 0; }
td, th { vertical-align: top; padding: 3pt 5pt; }
ul, ol { margin: 0 0 4pt 0; }
"""


class ErreurInterne(Exception):
    pass


def _val(el, tag, attr="val"):
    e = el.find(tag) if el is not None else None
    return None if e is None else e.get(W + attr, "")


def _on(el, tag):
    v = _val(el, tag)
    return v is not None and v not in ("0", "false", "none")


class _Word:
    def __init__(self, chemin, dossier_images):
        try:
            import docx
        except ImportError as e:
            raise ErreurInterne("python-docx absent") from e
        self.d = docx.Document(chemin)
        self.part = self.d.part
        self.images = dossier_images
        self.n_img = 0
        self.manques = set()
        self.largeur_utile = self.page()[2] + 4

    # -- styles ---------------------------------------------------------------
    def _style_para(self, p):
        st = _val(p.find(W + "pPr"), W + "pStyle") or ""
        if not hasattr(self, "_noms"):
            self._noms = {}
            for x in self.d.styles:
                try:
                    self._noms[x.style_id] = x.name or ""
                except Exception:                        # noqa: BLE001
                    pass
        return self._noms.get(st, st) or "", st

    def _run(self, r):
        texte = []
        for e in r:
            t = e.tag
            if t == W + "t":
                texte.append(html.escape(e.text or ""))
            elif t == W + "tab":
                texte.append("&#160;&#160;&#160;&#160;")
            elif t in (W + "br", W + "cr"):
                texte.append("<br/>")
            elif t == W + "drawing":
                texte.append(self._image(e))
            elif t == W + "pict":
                self.manques.add("formes")
        s = "".join(texte)
        if not s:
            return ""
        rp = r.find(W + "rPr")
        styles = []
        if rp is not None:
            if _on(rp, W + "b"):
                s = f"<b>{s}</b>"
            if _on(rp, W + "i"):
                s = f"<i>{s}</i>"
            u = _val(rp, W + "u")
            if u and u != "none":
                s = f"<u>{s}</u>"
            if _on(rp, W + "strike"):
                s = f"<s>{s}</s>"
            c = _val(rp, W + "color")
            if c and c not in ("auto", "000000"):
                styles.append(f"color:#{c}")
            sz = _val(rp, W + "sz")
            if sz and sz.isdigit():
                styles.append(f"font-size:{int(sz) / 2:g}pt")
            hl = _val(rp, W + "highlight")
            couleurs = {"yellow": "#FFFF00", "green": "#00FF00", "cyan": "#00FFFF", "lightGray": "#D3D3D3",
                        "magenta": "#FF00FF", "red": "#FF0000", "blue": "#0000FF", "darkYellow": "#808000"}
            if hl in couleurs:
                styles.append(f"background-color:{couleurs[hl]}")
            shd = rp.find(W + "shd")
            if shd is not None and shd.get(W + "fill", "auto") not in ("auto", "FFFFFF"):
                styles.append(f"background-color:#{shd.get(W + 'fill')}")
            va = _val(rp, W + "vertAlign")
            if va == "superscript":
                s = f"<sup>{s}</sup>"
            elif va == "subscript":
                s = f"<sub>{s}</sub>"
        return f'<span style="{";".join(styles)}">{s}</span>' if styles else s

    def _image(self, dessin):
        blip = dessin.find(".//" + A + "blip")
        if blip is None:
            self.manques.add("formes")
            return ""
        rid = blip.get(R + "embed")
        try:
            img = self.part.related_parts[rid]
            ext = os.path.splitext(img.partname)[1].lower() or ".png"
            if ext not in (".png", ".jpg", ".jpeg", ".gif", ".bmp"):
                self.manques.add("images")
                return ""
            self.n_img += 1
            nom = f"img{self.n_img}{ext}"
            with open(os.path.join(self.images, nom), "wb") as f:
                f.write(img.blob)
        except Exception:                                # noqa: BLE001
            self.manques.add("images")
            return ""
        ext_el = dessin.find(".//{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}extent")
        largeur = ""
        if ext_el is not None and ext_el.get("cx", "").isdigit():
            largeur = f' width="{int(ext_el.get("cx")) / 12700:.0f}"'      # EMU -> points
        return f'<img src="{nom}"{largeur}/>'

    def _para(self, p, dans_cellule=False):
        nom, _st = self._style_para(p)
        ppr = p.find(W + "pPr")
        contenu = []
        for e in p:
            if e.tag == W + "r":
                contenu.append(self._run(e))
            elif e.tag in (W + "hyperlink", W + "ins", W + "smartTag", W + "sdt"):
                for r in e.iter(W + "r"):
                    contenu.append(self._run(r))
        s = "".join(contenu) or "&#160;"
        styles = []
        jc = _val(ppr, W + "jc")
        if jc in ("center", "right", "both", "end"):
            styles.append("text-align:" + {"both": "justify", "end": "right"}.get(jc, jc))
        if ppr is not None:
            sp = ppr.find(W + "spacing")
            if sp is not None:
                if sp.get(W + "before", "").isdigit():
                    styles.append(f"margin-top:{int(sp.get(W + 'before')) / 20:g}pt")
                if sp.get(W + "after", "").isdigit():
                    styles.append(f"margin-bottom:{int(sp.get(W + 'after')) / 20:g}pt")
            ind = ppr.find(W + "ind")
            if ind is not None:
                g = ind.get(W + "left") or ind.get(W + "start") or ""
                if g.lstrip("-").isdigit() and int(g) > 0 and ppr.find(W + "numPr") is None:
                    styles.append(f"margin-left:{int(g) / 20:g}pt")
            shd = ppr.find(W + "shd")
            if shd is not None and shd.get(W + "fill", "auto") not in ("auto", "FFFFFF"):
                styles.append(f"background-color:#{shd.get(W + 'fill')}")
        st = f' style="{";".join(styles)}"' if styles else ""
        bas = nom.lower()
        if not dans_cellule:
            for niv in (1, 2, 3):
                if bas in (f"heading {niv}", f"titre {niv}") or bas == ("title" if niv == 1 else "-"):
                    return ("h", f"<h{niv}{st}>{s}</h{niv}>")
        num = ppr.find(W + "numPr") if ppr is not None else None
        if num is not None or bas.startswith("list"):
            niveau = _val(num, W + "ilvl") if num is not None else "0"
            return ("li", (int(niveau) if niveau and niveau.isdigit() else 0, f"<li{st}>{s}</li>"))
        return ("p", f"<p{st}>{s}</p>")

    def _bloc(self, elements, dans_cellule=False, fragments=None):
        """HTML des elements ; au premier niveau (fragments = liste), chaque bloc y est ajoute a part et chaque ligne
        de tableau aussi, pour une mise en page bloc par bloc."""
        sortie, liste = [], []

        def vider():
            if liste:
                sortie.append("<ul>" + "".join(li for _n, li in liste) + "</ul>")
                liste.clear()
        for e in elements:
            if e.tag == W + "p":
                genre, h = self._para(e, dans_cellule)
                if genre == "li":
                    liste.append(h)
                    continue
                vider()
                sortie.append(h)
            elif e.tag == W + "tbl":
                vider()
                if fragments is not None:
                    sortie.extend(self._tableau(e, fragments=True))
                else:
                    sortie.append(self._tableau(e))
            elif e.tag == W + "sdt":
                c = e.find(W + "sdtContent")
                if c is not None:
                    vider()
                    sortie.append(self._bloc(list(c), dans_cellule))
        vider()
        if fragments is not None:
            for x in sortie:
                fragments.append(x if isinstance(x, tuple) else ("bloc", x, None))
            return fragments
        return "".join(sortie)

    def _tableau(self, t, fragments=False):
        tp = t.find(W + "tblPr")
        bord = "1px solid #999"
        bords = tp.find(W + "tblBorders") if tp is not None else None
        interieur = True
        if bords is not None:
            ext = bords.find(W + "top")
            if ext is not None and ext.get(W + "val") not in (None, "none", "nil"):
                c = ext.get(W + "color", "auto")
                bord = f"1px solid #{c}" if c not in ("auto", "") else "1px solid #000"
            ih = bords.find(W + "insideH")
            interieur = ih is None or ih.get(W + "val") not in ("none", "nil")
        grille = [int(g.get(W + "w", "0") or 0) for g in t.findall(f"{W}tblGrid/{W}gridCol")]
        total = sum(grille) or 1
        lignes, entetes = [], []
        for tr in t.findall(W + "tr"):
            cellules, col = [], 0
            for tc in tr.findall(W + "tc"):
                tcp = tc.find(W + "tcPr")
                span = _val(tcp, W + "gridSpan")
                span = int(span) if span and span.isdigit() else 1
                if tcp is not None and tcp.find(W + "vMerge") is not None and _val(tcp, W + "vMerge") in ("", "continue"):
                    if _val(tcp, W + "vMerge") == "":         # suite d'une fusion verticale : cellule vide
                        pass
                styles = [f"border:{bord}" if interieur else ""]
                largeur = sum(grille[col:col + span]) if grille else 0
                if largeur:                              # en points (les % sont mal suivis par la mise en page)
                    styles.append(f"width:{max(8, largeur * self.largeur_utile / total - 12):.0f}pt")
                shd = tcp.find(W + "shd") if tcp is not None else None
                if shd is not None and shd.get(W + "fill", "auto") not in ("auto", ""):
                    styles.append(f"background-color:#{shd.get(W + 'fill')}")
                cs = f' colspan="{span}"' if span > 1 else ""
                st = ";".join(s for s in styles if s)
                cellules.append(f'<td{cs} style="{st}">{self._bloc(list(tc), True)}</td>')
                col += span
            ligne = "<tr>" + "".join(cellules) + "</tr>"
            lignes.append(ligne)
            trp = tr.find(W + "trPr")
            if trp is not None and trp.find(W + "tblHeader") is not None and len(entetes) == len(lignes) - 1:
                entetes.append(ligne)                    # lignes d'en-tete, repetees en haut de chaque page
        cadre = "" if interieur else f' style="border:{bord}"'
        if fragments:
            ouv = f"<table{cadre}>"
            corps = lignes[len(entetes):]
            if not corps:
                return [("bloc", ouv + "".join(lignes) + "</table>", None)]
            entete = ouv + "".join(entetes) + "</table>" if entetes else None
            # la 1re ligne emporte l'en-tete avec elle (jamais un en-tete seul en bas de page)
            return [("ligne", ouv + ("".join(entetes) if i == 0 else "") + l + "</table>", entete)
                    for i, l in enumerate(corps)] + [("bloc", "<p style='margin:0 0 4pt 0;font-size:4pt'>&#160;</p>", None)]
        return f"<table{cadre}>" + "".join(lignes) + "</table>"

    def html(self):
        corps = self.d.element.body
        if any(s.header.paragraphs and any(p.text.strip() for p in s.header.paragraphs) for s in self.d.sections):
            self.manques.add("en-têtes")
        if any(s.footer.paragraphs and any(p.text.strip() for p in s.footer.paragraphs) for s in self.d.sections):
            self.manques.add("pieds de page")
        return self._bloc(list(corps), fragments=[])

    def page(self):
        s = self.d.sections[0]
        pt = lambda v, defaut: (v.pt if v is not None else defaut)   # noqa: E731
        larg, haut = pt(s.page_width, 595), pt(s.page_height, 842)
        marges = (pt(s.left_margin, 56), pt(s.top_margin, 56), pt(s.right_margin, 56), pt(s.bottom_margin, 56))
        return fitz.Rect(0, 0, larg, haut), marges, larg - marges[0] - marges[2] - 4


def _html_tableur(chemin):
    ext = os.path.splitext(chemin)[1].lower()
    feuilles = []
    if ext == ".csv":
        with open(chemin, newline="", encoding="utf-8-sig", errors="replace") as f:
            echant = f.read(4096)
            f.seek(0)
            try:
                dialecte = csv.Sniffer().sniff(echant, delimiters=";,\t")
            except csv.Error:
                dialecte = csv.excel
            feuilles.append((os.path.basename(chemin), [list(l) for l in csv.reader(f, dialecte)]))
    else:
        try:
            import openpyxl
        except ImportError as e:
            raise ErreurInterne("openpyxl absent") from e
        cl = openpyxl.load_workbook(chemin, data_only=True, read_only=True)
        for ws in cl.worksheets:
            lignes = [["" if v is None else v for v in r] for r in ws.iter_rows(values_only=True)]
            while lignes and not any(str(v).strip() for v in lignes[-1]):
                lignes.pop()
            if lignes:
                n = max(len(r) for r in lignes)
                while n and not any(str(r[n - 1]).strip() for r in lignes if len(r) >= n):
                    n -= 1
                feuilles.append((ws.title, [r[:n] for r in lignes]))
        cl.close()
    morceaux = []
    for titre, lignes in feuilles:
        morceaux.append(("bloc", f"<h2>{html.escape(str(titre))}</h2>", None))
        n = max((len(r) for r in lignes), default=1) or 1
        larg = f"width:{max(20, (770 if n > 6 else 523) / n - 12):.0f}pt"
        entete = None
        for i, r in enumerate(list(lignes)):
            r = list(r) + [""] * (n - len(r))
            cell = "".join(f'<td style="border:1px solid #bbb;{larg};{"font-weight:bold;background-color:#EEEEEE" if i == 0 else ""}">'
                           f"{html.escape(str(v))}</td>" for v in r)
            t = f"<table><tr>{cell}</tr></table>"
            if i == 0:
                entete = t
            morceaux.append(("ligne", t, entete if i else None))
    return morceaux, max((max((len(r) for r in l), default=0) for _t, l in feuilles), default=0)


def _regrouper(fragments):
    """Blocs de texte consecutifs reunis (ils se coupent bien d'une page a l'autre) ; lignes de tableau a part."""
    out, texte = [], []
    for genre, h, entete in fragments:
        if genre == "bloc" and "<table" not in h:
            texte.append(h)
            continue
        if texte:
            out.append(("bloc", "".join(texte), None))
            texte = []
        out.append((genre, h, entete))
    if texte:
        out.append(("bloc", "".join(texte), None))
    return out


def _mettre_en_page(fragments, page, zone, archive, sortie):
    """Pose les fragments les uns sous les autres. Une ligne de tableau qui ne tient pas en bas de page passe a la
    page suivante (avec les lignes d'en-tete repetees) ; elle n'est coupee que si elle est plus haute qu'une page.
    (Laisser MuPDF couper lui-meme un tableau entier laisse des fonds de cellules au mauvais endroit.)"""
    ecrivain = fitz.DocumentWriter(sortie)
    etat = {"dispositif": None, "y": zone.y0, "pages": 0}

    def nouvelle_page():
        if etat["dispositif"] is not None:
            ecrivain.end_page()
        etat["dispositif"] = ecrivain.begin_page(page)
        etat["y"] = zone.y0
        etat["pages"] += 1
        if etat["pages"] > 3000:
            raise ErreurInterne("document trop long")

    def histoire(h):
        return fitz.Story(html=f"<body>{h}</body>", user_css=CSS, archive=archive)

    def hauteur(h):
        st = histoire(h)
        _plus, r = st.place(fitz.Rect(zone.x0, 0, zone.x1, 1e6))
        return fitz.Rect(r).y1

    def poser(h, couper=True):
        """Pose h a partir de y ; renvoie False (sans rien poser) s'il ne tient pas et que couper est faux.
        (Pour un tableau, MuPDF dit parfois « tout est pose » alors que la ligne deborde : on mesure d'abord.)"""
        if not couper and etat["y"] + hauteur(h) > zone.y1 + 0.5:
            return False
        st = histoire(h)
        plus, rempli = st.place(fitz.Rect(zone.x0, etat["y"], zone.x1, zone.y1))
        rempli = fitz.Rect(rempli)
        if plus and not couper:
            return False
        st.draw(etat["dispositif"])
        etat["y"] = rempli.y1 if rempli.y1 > etat["y"] else etat["y"]
        while plus:
            nouvelle_page()
            plus, rempli = st.place(zone)
            rempli = fitz.Rect(rempli)
            st.draw(etat["dispositif"])
            etat["y"] = rempli.y1
        return True

    nouvelle_page()
    for genre, h, entete in _regrouper(fragments):
        if genre == "bloc" and "<table" not in h:
            poser(h)
            continue
        if poser(h, couper=False):
            continue
        if etat["y"] > zone.y0 + 1:                      # pas la place en bas : page suivante
            nouvelle_page()
            if genre == "ligne" and entete:
                poser(entete)
            if poser(h, couper=False):
                continue
        poser(h)                                         # plus haute qu'une page : coupee
    ecrivain.end_page()
    ecrivain.close()


def convertir(source, sortie, dossier_travail):
    """Ecrit le PDF ; renvoie la liste de ce qui n'a pas pu etre repris (vide si tout l'est)."""
    ext = os.path.splitext(source)[1].lower()
    if ext not in INTERNES:
        raise ErreurInterne("format non pris en charge sans Office")
    os.makedirs(dossier_travail, exist_ok=True)
    manques = []
    if ext in (".docx", ".docm", ".dotx"):
        w = _Word(source, dossier_travail)
        corps = w.html()
        page, marges, _l = w.page()
        manques = sorted(w.manques)
    elif ext == ".txt":
        with open(source, encoding="utf-8", errors="replace") as f:
            corps = [("bloc", "<pre style='font-family:monospace;font-size:10pt;white-space:pre-wrap'>" +
                      html.escape(f.read()) + "</pre>", None)]
        page, marges = fitz.paper_rect("a4"), (56, 56, 56, 56)
    else:
        corps, colonnes = _html_tableur(source)
        page = fitz.paper_rect("a4-l" if colonnes > 6 else "a4")
        marges = (36, 36, 36, 36)
    zone = fitz.Rect(page.x0 + marges[0], page.y0 + marges[1], page.x1 - marges[2], page.y1 - marges[3])
    _mettre_en_page(corps, page, zone, fitz.Archive(dossier_travail), sortie)
    if not os.path.exists(sortie):
        raise ErreurInterne("aucun PDF produit")
    return manques
