"""Creer un formulaire a partir d'un document : reperer les zones a remplir et y poser de vrais champs PDF.

Reperes (comme « Preparer un formulaire » d'Acrobat) :
  - pointilles et soulignes tapes au clavier (_____ ou ......) ;
  - traits horizontaux dessines sous un espace vide ;
  - petits carres dessines ou caracteres case (☐ □ ❑) -> cases a cocher ;
  - cadres vides -> zones de texte (sur plusieurs lignes si le cadre est haut).
Chaque champ prend le nom du libelle le plus proche (a gauche, sinon au-dessus).
"""
import re
import pymupdf as fitz

CASES = "☐□❑❒▢◻"


def _libelle(page, r, mots, case=False):
    """Texte juste a gauche sur la meme ligne, sinon juste au-dessus (case a cocher : le texte a droite)."""
    if case:
        droite = sorted((w for w in mots if abs((w[1] + w[3]) / 2 - (r.y0 + r.y1) / 2) < max(6, r.height) and
                         w[0] >= r.x1 - 1 and w[0] - r.x1 < 200), key=lambda w: w[0])
        sel = []
        for w in droite:
            if sel and w[0] - sel[-1][2] > 12:
                break
            sel.append(w)
        if sel:
            return " ".join(w[4] for w in sel[:6]).strip(" :")[:60]
    gauche = [w for w in mots if abs((w[1] + w[3]) / 2 - (r.y0 + r.y1) / 2) < max(6, r.height * 0.6) and w[2] <= r.x0 + 2
              and r.x0 - w[2] < 200 and not re.fullmatch(r"[_.…]+", w[4])]
    if gauche:
        gauche.sort(key=lambda w: w[0])
        # derniers mots avant le champ, jusqu'a un grand blanc
        sel = [gauche[-1]]
        for w in reversed(gauche[:-1]):
            if sel[0][0] - w[2] > 12:
                break
            sel.insert(0, w)
        t = " ".join(w[4] for w in sel[-6:])
    else:
        dessus = [w for w in mots if 0 < r.y0 - w[3] < 22 and w[0] < r.x1 and w[2] > r.x0 - 20]
        t = " ".join(w[4] for w in sorted(dessus, key=lambda w: w[0])[:6])
    t = re.sub(r"[_.…:]+$", "", t.strip()).strip(" :")
    return t[:60] or "Champ"


def _libre(r, occupes):
    return not any(r.intersects(o) and (r & o).get_area() > 0.25 * min(r.get_area(), o.get_area()) for o in occupes)


def detecter(page):
    """[{"genre": "texte"|"case", "rect": Rect, "nom": str, "lignes": bool}] pour une page."""
    mots = page.get_text("words")
    champs, occupes = [], [fitz.Rect(w.rect) for w in page.widgets()]

    def ajouter(genre, r, multi=False):
        r = fitz.Rect(r)
        if r.is_empty or not _libre(r, occupes + [c["rect"] for c in champs]):
            return
        champs.append({"genre": genre, "rect": r, "nom": _libelle(page, r, mots, genre == "case"), "lignes": multi})

    texte_rects = [fitz.Rect(w[:4]) for w in mots if not re.fullmatch(r"[_.…]{3,}", w[4])]
    # 1. soulignes et pointilles tapes
    for w in mots:
        t = w[4]
        m = re.search(r"[_]{4,}|[.…]{5,}", t)
        if not m:
            continue
        r = fitz.Rect(w[:4])
        if m.start() > 0 and len(t) > 0:              # « Nom:_____ » : le champ commence apres le libelle
            r.x0 += r.width * m.start() / len(t)
        h = max(r.height, 12)
        ajouter("texte", fitz.Rect(r.x0, r.y1 - h, r.x1, r.y1 + 1))
    # 2. cases tapees
    for w in mots:
        for k, ch in enumerate(w[4]):
            if ch in CASES:
                r = fitz.Rect(w[:4])
                l = r.width / max(1, len(w[4]))
                c = fitz.Rect(r.x0 + k * l, r.y0, r.x0 + (k + 1) * l, r.y1)
                cote = min(c.width, c.height)
                ajouter("case", fitz.Rect(c.x0, c.y1 - cote - 1, c.x0 + cote, c.y1 - 1))
    # 3. dessins : traits et carres
    for d in page.get_drawings():
        for it in d["items"]:
            if it[0] == "l":
                a, b = it[1], it[2]
                if abs(a.y - b.y) < 0.8 and abs(b.x - a.x) > 40:
                    x0, x1 = sorted((a.x, b.x))
                    zone = fitz.Rect(x0, a.y - 14, x1, a.y - 0.5)
                    if not any(zone.intersects(t) and (zone & t).width > 6 for t in texte_rects):
                        ajouter("texte", zone)
            elif it[0] in ("re", "qu"):
                r = fitz.Rect(it[1]) if it[0] == "re" else it[1].rect
                if 5 <= r.width <= 18 and 5 <= r.height <= 18 and abs(r.width - r.height) < 2.5:
                    ajouter("case", r)
                elif r.height < 1.6 and r.width > 40:  # trait dessine comme un rectangle fin
                    zone = fitz.Rect(r.x0, r.y0 - 14, r.x1, r.y0 - 0.5)
                    if not any(zone.intersects(t) and (zone & t).width > 6 for t in texte_rects):
                        ajouter("texte", zone)
                elif 12 <= r.height <= 160 and r.width > 50 and r.width < page.rect.width * 0.95:
                    interieur = fitz.Rect(r.x0 + 1.5, r.y0 + 1.5, r.x1 - 1.5, r.y1 - 1.5)
                    if not any(interieur.intersects(t) for t in texte_rects):
                        ajouter("texte", interieur, multi=r.height > 30)
    return champs


def noms_uniques(champs):
    vus = {}
    for c in champs:
        base = c["nom"] or "Champ"
        n = vus.get(base, 0) + 1
        vus[base] = n
        c["nom"] = base if n == 1 else f"{base} {n}"
    return champs


def creer(doc, champs_par_page):
    """Pose les champs : {num_page: [champ, ...]} -> nombre de champs crees."""
    n = 0
    existants = {w.field_name for p in doc for w in p.widgets()}
    for num, champs in champs_par_page.items():
        page = doc[num]
        for c in champs:
            nom = c["nom"]
            k = 2
            while nom in existants:
                nom = f"{c['nom']} {k}"
                k += 1
            existants.add(nom)
            w = fitz.Widget()
            w.rect = fitz.Rect(c["rect"])
            w.field_name = nom
            w.field_label = c.get("info") or c["nom"]
            if c["genre"] == "case":
                w.field_type = fitz.PDF_WIDGET_TYPE_CHECKBOX
                w.field_value = False
            elif c["genre"] in ("liste", "liste_multiple"):
                w.field_type = fitz.PDF_WIDGET_TYPE_COMBOBOX if c["genre"] == "liste" else fitz.PDF_WIDGET_TYPE_LISTBOX
                w.choice_values = list(c.get("choix") or [])
                w.text_fontsize = 0
                w.text_font = "Helv"
            else:
                w.field_type = fitz.PDF_WIDGET_TYPE_TEXT
                w.text_fontsize = 0 if not c.get("lignes") else 10
                w.text_font = "Helv"
                if c.get("lignes"):
                    w.field_flags |= fitz.PDF_TX_FIELD_IS_MULTILINE
            w.border_width = 0
            w.fill_color = None
            page.add_widget(w)
            n += 1
    normaliser(doc)
    return n


def creer_radio(doc, num_page, rect, groupe, choix, info=""):
    """Bouton radio « choix » du groupe « groupe » (cree le groupe s'il n'existe pas) ; Acrobat : un seul coche."""
    page = doc[num_page]
    w = fitz.Widget()
    w.field_type = fitz.PDF_WIDGET_TYPE_RADIOBUTTON
    w.field_name = groupe
    w.rect = fitz.Rect(rect)
    if info:
        w.field_label = info
    w.border_width = 1
    page.add_widget(w)
    nouveau = max((x for x in page.widgets(types=[fitz.PDF_WIDGET_TYPE_RADIOBUTTON]) if x.field_name == groupe),
                  key=lambda x: x.xref)
    renommer_etat(doc, nouveau.xref, choix)
    # PyMuPDF cree un groupe par bouton : on rattache le nouveau au premier groupe du meme nom
    groupes = []
    for p in doc:
        for x in p.widgets(types=[fitz.PDF_WIDGET_TYPE_RADIOBUTTON]) or []:
            if x.field_name == groupe:
                t, par = doc.xref_get_key(x.xref, "Parent")
                if t == "xref":
                    groupes.append((int(par.split()[0]), x.xref))
    if groupes:
        premier = groupes[0][0]
        tp, par = doc.xref_get_key(nouveau.xref, "Parent")
        if tp == "xref" and int(par.split()[0]) != premier:
            ancien = int(par.split()[0])
            doc.xref_set_key(nouveau.xref, "Parent", f"{premier} 0 R")
            t, kids = doc.xref_get_key(premier, "Kids")
            doc.xref_set_key(premier, "Kids", kids.rstrip("]").rstrip() + f" {nouveau.xref} 0 R]")
            racine = doc.pdf_catalog()
            t, arr = doc.xref_get_key(racine, "AcroForm/Fields")
            if t == "array":
                doc.xref_set_key(racine, "AcroForm/Fields", re.sub(rf"\s*\b{ancien}\s+0\s+R", "", arr))
            elif t == "xref":
                fx = int(arr.split()[0])
                doc.xref_set_key(fx, "Fields", re.sub(rf"\s*\b{ancien}\s+0\s+R", "", doc.xref_object(fx)))
        doc.xref_set_key(premier, "Ff", str((1 << 15) | (1 << 14)))
    return nouveau.xref


def renommer_etat(doc, xref, choix):
    """Etat « coche » d'une case ou d'un bouton radio = valeur exportee (au lieu du « Yes » / « None » par defaut)."""
    nom = "".join(chr(b) if (chr(b).isascii() and (chr(b).isalnum() or chr(b) in "-_.")) else f"#{b:02X}"
                  for b in (choix or "Oui").encode("utf-8"))
    t, ap = doc.xref_get_key(xref, "AP/N")
    if t != "dict":
        return nom
    refs = dict(re.findall(r"/([^\s/<>\[\]()]+)\s+(\d+\s+0\s+R)", ap))
    on = next((k for k in refs if k != "Off"), None)
    if on and on != nom:
        refs[nom] = refs.pop(on)
        doc.xref_set_key(xref, "AP/N", "<<" + "".join(f"/{k} {v}" for k, v in refs.items()) + ">>")
        tD, apD = doc.xref_get_key(xref, "AP/D")
        if tD == "dict":
            rd = dict(re.findall(r"/([^\s/<>\[\]()]+)\s+(\d+\s+0\s+R)", apD))
            ond = next((k for k in rd if k != "Off"), None)
            if ond:
                rd[nom] = rd.pop(ond)
                doc.xref_set_key(xref, "AP/D", "<<" + "".join(f"/{k} {v}" for k, v in rd.items()) + ">>")
    doc.xref_set_key(xref, "AS", "/Off")
    return nom


def normaliser(doc):
    """Fusionne chaque champ a un seul widget avec ce widget, comme le fait Acrobat (PyMuPDF cree un champ « parent »
    et un widget « enfant »). Sans cela, apres une signature, remplir un champ est compte comme une « autre
    modification » par les outils de verification les plus stricts. Renvoie le nombre de champs fusionnes."""
    racine = doc.pdf_catalog()
    t, af = doc.xref_get_key(racine, "AcroForm")
    if t == "null":
        return 0
    af_xref = int(af.split()[0]) if t == "xref" else None
    n = 0
    for p in doc:
        for w in list(p.widgets() or []):
            x = w.xref
            if doc.xref_get_key(x, "T")[0] != "null":
                continue
            tp, par = doc.xref_get_key(x, "Parent")
            if tp != "xref":
                continue
            px = int(par.split()[0])
            tk, kids = doc.xref_get_key(px, "Kids")
            if tk != "array" or len(re.findall(r"\d+\s+0\s+R", kids)) != 1:
                continue
            for k in doc.xref_get_keys(px):
                if k in ("Kids", "Parent"):
                    continue
                if doc.xref_get_key(x, k)[0] != "null":
                    continue
                tv, v = doc.xref_get_key(px, k)
                doc.xref_set_key(x, k, fitz.get_pdf_str(v) if tv == "string" else v)
            tg, gp = doc.xref_get_key(px, "Parent")
            doc.xref_set_key(x, "Parent", gp if tg == "xref" else "null")
            ref_ancien, ref_nouveau = f"{px} 0 R", f"{x} 0 R"
            # le champ prend la place du parent dans la liste des champs (ou chez le grand-parent)
            cible, cle = (int(gp.split()[0]), "Kids") if tg == "xref" else (af_xref, "Fields")
            if cible is None:
                ta, arr = doc.xref_get_key(racine, "AcroForm/Fields")
                if ta == "array":
                    doc.xref_set_key(racine, "AcroForm/Fields", re.sub(rf"\b{px}\s+0\s+R", ref_nouveau, arr))
            else:
                ta, arr = doc.xref_get_key(cible, cle)
                if ta == "array":
                    doc.xref_set_key(cible, cle, re.sub(rf"\b{px}\s+0\s+R", ref_nouveau, arr))
            del ref_ancien
            n += 1
    return n


# ------------------------------------------------------------------ type devine d'apres le libelle
_TYPES = [  # (motif du libelle, genre du champ, regles PhilPDF)
    (r"signature|sign[ée] par|visa\b", "signature", None),
    (r"\bdate\b|n[ée]\(?e?\)?\s*le|\bfait le\b|\ble\s*:?$|d[ée]livr[ée] le|\bdu\b\s*:?$|\bau\b\s*:?$", "texte",
     {"format": {"genre": "date", "date": "dd/mm/yyyy"}}),
    (r"montant|prix|total|tarif|somme|co[uû]t|\b(ht|ttc)\b|€|euros?", "texte",
     {"format": {"genre": "nombre", "decimales": 2, "separateur": 2, "negatif": 0, "symbole": "€", "symbole_avant": False}}),
    (r"quantit[ée]|\bqt[ée]\b|nombre de|\bnb\b", "texte",
     {"format": {"genre": "nombre", "decimales": 0, "separateur": 2, "negatif": 0, "symbole": "", "symbole_avant": False}}),
    (r"t[ée]l[ée]?phone|\bt[ée]l\b|portable|mobile|\bfax\b|\bgsm\b", "texte",
     {"format": {"genre": "masque", "masque": "99 99 99 99 99"}}),
    (r"code\s*postal|\bc\.?p\.?\b", "texte", {"format": {"genre": "masque", "masque": "99999"}}),
    (r"e-?mail|courriel|m[ée]l\b|adresse [ée]lectronique", "texte", {"controle": "email"}),
    (r"s[ée]curit[ée] sociale|\bn\.?i\.?r\.?\b|n°\s*ss\b|immatriculation", "texte", {"controle": "nir"}),
    (r"\biban\b", "texte", {"controle": "iban", "majuscules": True}),
    (r"\bsiret\b", "texte", {"controle": "siret"}),
    (r"\brpps\b", "texte", {"controle": "rpps"}),
    (r"^nom\b|nom de famille|nom d'usage|\bville\b|commune", "texte", {"majuscules": True}),
]


def deviner(libelle):
    """(genre, regles) proposes pour un champ d'apres son libelle (« Date de naissance » -> date...) ; (None, None)."""
    t = (libelle or "").strip().lower()
    for motif, genre, regles in _TYPES:
        if re.search(motif, t):
            return genre, (dict(regles) if regles else None)
    return None, None
