"""Regles des champs de formulaire, en simple : format (nombre, montant, pourcentage, date, heure, masque), valeur
automatique (date ou heure quand on clique), calcul (somme, produit, moyenne, min, max, formule), plage autorisee,
listes dependantes, afficher / masquer un champ selon une case ou une valeur.

Chaque regle est gardee telle quelle dans le champ (cle /PhilPDF_Regles, en JSON) et traduite en JavaScript standard
d'Acrobat (AFNumber_Format, AFDate_FormatEx, AFSimple_Calculate...) : le formulaire marche pareil dans Acrobat,
Acrobat Reader et PhilPDF. Les formulaires faits dans Acrobat sont relus depuis leur JavaScript (fonctions AF...).
"""
import datetime as _dt
import json
import re

import pymupdf as fitz

CLE = "PhilPDF_Regles"
DEBUT, FIN = "/* PhilPDF */", "/* fin PhilPDF */"

# separateurs d'Acrobat (AFNumber_Format, 2e argument)
SEPARATEURS = {0: ("1,234.56", ",", "."), 1: ("1234.56", "", "."), 2: ("1.234,56", ".", ","), 3: ("1234,56", "", ","),
               4: ("1'234.56", "'", ".")}
DATES = ["dd/mm/yyyy", "dd/mm/yy", "d/m/yyyy", "dd.mm.yyyy", "yyyy-mm-dd", "dd mmmm yyyy", "mm/dd/yyyy",
         "dd/mm/yyyy HH:MM"]
HEURES = ["HH:MM", "HH:MM:ss", "h:MM tt"]
MASQUES = {"telephone": "99 99 99 99 99", "code_postal": "99999", "siret": "999 999 999 99999"}
CALCULS = {"somme": "SUM", "produit": "PRD", "moyenne": "AVG", "min": "MIN", "max": "MAX"}
AUTO = ("date_clic", "date_heure_clic", "heure_clic")
_MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre",
         "décembre"]


def vide():
    return {"format": {"genre": "aucun"}, "auto": None, "calcul": None, "plage": None, "depend": None, "affiche": None}


# ------------------------------------------------------------------ lecture / ecriture dans le PDF
def xref_champ(doc, w):
    try:
        if doc.xref_get_key(w.xref, "T")[0] == "null":
            t, par = doc.xref_get_key(w.xref, "Parent")
            if t == "xref":
                return int(par.split()[0])
    except Exception:                                     # noqa: BLE001
        pass
    return w.xref


def _js(doc, x, cle):
    """Texte d'un script (/AA/<cle> ou /A pour MouseUp) d'un objet."""
    chemin = "A" if cle == "A" else "AA/" + cle
    t, v = doc.xref_get_key(x, chemin)
    if t == "xref":
        rx = int(v.split()[0])
        t2, v2 = doc.xref_get_key(rx, "JS")
        if t2 == "xref":
            return doc.xref_stream(int(v2.split()[0])).decode("latin-1", "replace")
        return v2 if t2 == "string" else ""
    if t == "dict":
        m = re.search(r"/JS\s*(\d+)\s+0\s+R", v)
        if m:
            return doc.xref_stream(int(m.group(1))).decode("latin-1", "replace")
        t2, v2 = doc.xref_get_key(x, chemin + "/JS")
        return v2 if t2 == "string" else ""
    return ""


def scripts(doc, w):
    """{K, F, V, C, Fo, Bl, A} : scripts du champ et de son widget."""
    out = {}
    for x in {xref_champ(doc, w), w.xref}:
        for k in ("K", "F", "V", "C", "Fo", "Bl", "U", "A"):
            s = _js(doc, x, k)
            if s:
                out[k] = (out.get(k, "") + "\n" + s).strip()
    return out


def lire(doc, w):
    """Regles d'un champ : celles de PhilPDF, sinon reconnues dans le JavaScript d'Acrobat."""
    fx = xref_champ(doc, w)
    t, v = doc.xref_get_key(fx, CLE)
    if t == "string" and v:
        try:
            r = dict(vide(), **json.loads(v))
            r["_philpdf"] = True
            return r
        except ValueError:
            pass
    return depuis_js(scripts(doc, w))


def _args(s):
    return [a.strip().strip('"\'') for a in re.split(r",(?=(?:[^\"]*\"[^\"]*\")*[^\"]*$)", s)]


def depuis_js(sc):
    """Reconnait les fonctions standard d'Acrobat dans les scripts d'un champ."""
    r = vide()
    f = sc.get("F", "") + "\n" + sc.get("K", "")
    m = re.search(r"AFNumber_Format\s*\(([^)]*)\)", f)
    if m:
        a = _args(m.group(1)) + [""] * 6
        try:
            r["format"] = {"genre": "nombre", "decimales": int(float(a[0] or 0)), "separateur": int(float(a[1] or 0)),
                           "negatif": int(float(a[2] or 0)), "symbole": a[4], "symbole_avant": a[5].lower() == "true"}
        except ValueError:
            pass
    m = re.search(r"AFPercent_Format\s*\(([^)]*)\)", f)
    if m:
        a = _args(m.group(1)) + ["0", "0"]
        r["format"] = {"genre": "pourcentage", "decimales": int(float(a[0] or 0)), "separateur": int(float(a[1] or 0))}
    m = re.search(r"AFDate_(?:Format|Keystroke)Ex\s*\(\s*[\"']([^\"']+)", f)
    if m:
        r["format"] = {"genre": "date", "date": m.group(1)}
    else:
        m = re.search(r"AFDate_(?:Format|Keystroke)\s*\(\s*(\d+)", f)
        if m:
            anciens = ["m/d", "m/d/yy", "mm/dd/yy", "mm/yy", "d-mmm", "d-mmm-yy", "dd-mmm-yy", "yy-mm-dd", "mmm-yy",
                       "mmmm-yy", "mmm d, yyyy", "mmmm d, yyyy", "m/d/yy h:MM tt", "m/d/yy HH:MM"]
            r["format"] = {"genre": "date", "date": anciens[min(int(m.group(1)), len(anciens) - 1)]}
    m = re.search(r"AFTime_(?:Format|Keystroke)Ex\s*\(\s*[\"']([^\"']+)", f)
    if m:
        r["format"] = {"genre": "heure", "heure": m.group(1)}
    else:
        m = re.search(r"AFTime_(?:Format|Keystroke)\s*\(\s*(\d+)", f)
        if m:
            r["format"] = {"genre": "heure", "heure": ["HH:MM", "h:MM tt", "HH:MM:ss", "h:MM:ss tt"][min(int(m.group(1)), 3)]}
    m = re.search(r"AFSpecial_KeystrokeEx\s*\(\s*[\"']([^\"']+)", f)
    if m:
        r["format"] = {"genre": "masque", "masque": m.group(1)}
    c = sc.get("C", "")
    m = re.search(r"AFSimple_Calculate\s*\(\s*[\"'](\w+)[\"']\s*,\s*new\s+Array\s*\(([^)]*)\)", c)
    if m:
        inv = {v: k for k, v in CALCULS.items()}
        r["calcul"] = {"genre": inv.get(m.group(1).upper(), "somme"), "champs": [x for x in _args(m.group(2)) if x]}
    else:
        m = re.search(r"/\*\*\s*BVCALC\s*(.*?)\s*EVCALC\s*\*\*/", c, re.S)
        if m:
            r["calcul"] = {"genre": "formule", "formule": _sfn_vers_crochets(m.group(1))}
    m = re.search(r"AFRange_Validate\s*\(([^)]*)\)", sc.get("V", ""))
    if m:
        a = _args(m.group(1)) + [""] * 4
        try:
            r["plage"] = {"min": float(a[1]) if a[0].lower() == "true" else None,
                          "max": float(a[3]) if a[2].lower() == "true" else None}
        except ValueError:
            pass
    fo = sc.get("Fo", "") + sc.get("A", "")
    if "util.printd" in fo and "new Date" in fo:
        m = re.search(r"util\.printd\s*\(\s*[\"']([^\"']+)", fo)
        fmt = m.group(1) if m else "dd/mm/yyyy"
        r["auto"] = "date_heure_clic" if ("H" in fmt and "d" in fmt) else ("heure_clic" if "H" in fmt or "h:" in fmt else "date_clic")
        if r["format"]["genre"] == "aucun":
            r["format"] = {"genre": "date", "date": fmt} if r["auto"] != "heure_clic" else {"genre": "heure", "heure": fmt}
    return r


def _sfn_vers_crochets(sfn):
    """« Quantite*Prix\\ unitaire » (notation simplifiee d'Acrobat) -> « [Quantite] * [Prix unitaire] »."""
    jetons = re.findall(r"(?:\\.|[^\s+\-*/()])+|[+\-*/()]", sfn)
    out = []
    for j in jetons:
        if j in "+-*/()":
            out.append(j)
        elif re.fullmatch(r"\d+(?:[.,]\d+)?", j):
            out.append(j)
        else:
            out.append("[" + re.sub(r"\\(.)", r"\1", j) + "]")
    return " ".join(out)


def ecrire(doc, w, regles):
    """Garde les regles dans le champ. Le JavaScript est regenere pour tout le formulaire par generer_js()."""
    fx = xref_champ(doc, w)
    propre = {k: v for k, v in regles.items() if not k.startswith("_")}
    if propre == {k: v for k, v in vide().items()}:
        doc.xref_set_key(fx, CLE, "null")
    else:
        doc.xref_set_key(fx, CLE, fitz.get_pdf_str(json.dumps(propre, ensure_ascii=False)))


# ------------------------------------------------------------------ JavaScript pour Acrobat
def _jsstr(t):
    return '"' + str(t).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _js_format(fmt):
    g = fmt.get("genre", "aucun")
    if g == "nombre":
        sym = fmt.get("symbole") or ""
        avant = bool(fmt.get("symbole_avant"))
        if sym and not avant and not sym.startswith(" "):
            sym = " " + sym
        if sym and avant and not sym.endswith(" "):
            sym = sym + " "
        a = f'{int(fmt.get("decimales", 2))}, {int(fmt.get("separateur", 2))}, {int(fmt.get("negatif", 0))}, 0, {_jsstr(sym)}, {"true" if avant else "false"}'
        return f"AFNumber_Format({a});", f"AFNumber_Keystroke({a});"
    if g == "pourcentage":
        a = f'{int(fmt.get("decimales", 0))}, {int(fmt.get("separateur", 2))}'
        return f"AFPercent_Format({a});", f"AFPercent_Keystroke({a});"
    if g == "date":
        d = _jsstr(fmt.get("date") or "dd/mm/yyyy")
        return f"AFDate_FormatEx({d});", f"AFDate_KeystrokeEx({d});"
    if g == "heure":
        h = _jsstr(fmt.get("heure") or "HH:MM")
        return f"AFTime_FormatEx({h});", f"AFTime_KeystrokeEx({h});"
    if g == "masque":
        m = _jsstr(fmt.get("masque") or "")
        return f"AFSpecial_KeystrokeEx({m});", f"AFSpecial_KeystrokeEx({m});"
    return "", ""


def jetons_formule(formule):
    """« [Quantite] * [Prix] + 2 » -> [("champ", "Quantite"), ("op", "*"), ...] ; ValueError si incorrecte."""
    out, i = [], 0
    while i < len(formule):
        c = formule[i]
        if c.isspace():
            i += 1
        elif c == "[":
            j = formule.find("]", i)
            if j < 0:
                raise ValueError("crochet")
            out.append(("champ", formule[i + 1:j]))
            i = j + 1
        elif c in "+-*/()":
            out.append(("op", c))
            i += 1
        else:
            m = re.match(r"\d+(?:[.,]\d+)?", formule[i:])
            if not m:
                raise ValueError(formule[i:i + 10])
            out.append(("nombre", m.group(0).replace(",", ".")))
            i += len(m.group(0))
    return out


def _js_calcul(c):
    if not c:
        return ""
    if c.get("genre") == "formule":
        js = []
        for t, v in jetons_formule(c.get("formule", "")):
            js.append(f"AFMakeNumber(getField({_jsstr(v)}).value)" if t == "champ" else v)
        sfn = " ".join((re.sub(r"([\s+\-*/()\\])", r"\\\1", v) if t == "champ" else v)
                       for t, v in jetons_formule(c.get("formule", "")))
        return f"/** BVCALC {sfn} EVCALC **/ event.value = {' '.join(js) or '0'};"
    champs = ", ".join(_jsstr(x) for x in c.get("champs", []))
    return f'AFSimple_Calculate("{CALCULS.get(c.get("genre"), "SUM")}", new Array ({champs}));'


def _js_auto(auto, fmt):
    if not auto:
        return ""
    if auto == "date_clic":
        f = fmt.get("date") if fmt.get("genre") == "date" else "dd/mm/yyyy"
    elif auto == "heure_clic":
        f = fmt.get("heure") if fmt.get("genre") == "heure" else "HH:MM"
    else:
        f = fmt.get("date") if fmt.get("genre") == "date" and "H" in (fmt.get("date") or "") else "dd/mm/yyyy HH:MM"
    return f'if (event.target.value == "") event.target.value = util.printd({_jsstr(f)}, new Date());'


def _remplacer_bloc(ancien, bloc):
    """Remplace la partie PhilPDF d'un script, en gardant ce qu'un autre outil y a mis."""
    ancien = ancien or ""
    ancien = re.sub(re.escape(DEBUT) + r".*?" + re.escape(FIN), "", ancien, flags=re.S).strip()
    if not bloc:
        return ancien
    return ((ancien + "\n") if ancien else "") + f"{DEBUT}\n{bloc}\n{FIN}"


def _poser_js(doc, x, cle, texte):
    """Pose (ou retire) un script JavaScript /AA/<cle> (ou /A) sur l'objet x."""
    chemin = "A" if cle == "A" else "AA/" + cle
    if not texte:
        doc.xref_set_key(x, chemin, "null")
        t, v = doc.xref_get_key(x, "AA")
        if t == "dict" and v.replace(" ", "") in ("<<>>", ""):
            doc.xref_set_key(x, "AA", "null")
        return
    if doc.xref_get_key(x, "AA")[0] == "null" and cle != "A":
        doc.xref_set_key(x, "AA", "<<>>")
    doc.xref_set_key(x, chemin, "<</S/JavaScript/JS " + fitz.get_pdf_str(texte) + ">>")


def tous_les_champs(doc):
    """[(page, widget)] de tous les champs (signatures comprises)."""
    out = []
    for n, p in enumerate(doc):
        for w in p.widgets() or []:
            w._page_vivante = p
            out.append((n, w))
    return out


def generer_js(doc):
    """Regenere tout le JavaScript PhilPDF du formulaire a partir des regles (format, calcul, listes dependantes,
    afficher / masquer), et l'ordre de calcul. Les scripts ecrits par d'autres outils sont gardes."""
    champs = tous_les_champs(doc)
    par_nom = {}
    for n, w in champs:
        par_nom.setdefault(w.field_name, []).append((n, w))
    regles = {nom: lire(doc, l[0][1]) for nom, l in par_nom.items()}
    # scripts portes par d'autres champs : listes dependantes et affichage (sur le champ « source »)
    sur_source = {}
    for nom, r in regles.items():
        if not r.get("_philpdf"):
            continue
        dep = r.get("depend")
        if dep and dep.get("parent"):
            m = {k: list(v) for k, v in (dep.get("listes") or {}).items()}
            sur_source.setdefault(dep["parent"], []).append(
                f"var m = {json.dumps(m, ensure_ascii=False)}; var f = this.getField({_jsstr(nom)}); "
                f"if (f) {{ var l = m[event.value]; if (l) f.setItems(l); else f.clearItems(); }}")
    for nom, r in regles.items():
        a = r.get("affiche") if r.get("_philpdf") else None
        if not a or not a.get("cibles"):
            continue
        cond = 'event.target.value != "Off"' if a.get("quand") == "coche" else f'event.value == {_jsstr(a.get("valeur", ""))}'
        lignes = [f"this.getField({_jsstr(c)}).display = ({cond}) ? display.visible : display.hidden;"
                  for c in a["cibles"]]
        sur_source.setdefault(("affiche", nom), []).extend(lignes)
    calcules = []
    for nom, l in par_nom.items():
        r = regles[nom]
        source = nom in sur_source or ("affiche", nom) in sur_source
        if not r.get("_philpdf") and not source:
            continue                                      # formulaire d'Acrobat sans regle PhilPDF : on n'y touche pas
        n, w = l[0]
        fx = xref_champ(doc, w)
        fmt = (r.get("format") if r.get("_philpdf") else None) or {"genre": "aucun"}
        jf, jk = _js_format(fmt)
        cal = _js_calcul(r.get("calcul")) if r.get("_philpdf") else ""
        if r.get("calcul"):
            calcules.append(nom)
        plage = r.get("plage") if r.get("_philpdf") else None
        jv = ""
        if plage and (plage.get("min") is not None or plage.get("max") is not None):
            jv = "AFRange_Validate({}, {}, {}, {});".format(
                "true" if plage.get("min") is not None else "false", plage.get("min") or 0,
                "true" if plage.get("max") is not None else "false", plage.get("max") or 0)
        jv = "\n".join(x for x in [jv] + sur_source.get(nom, []) +
                       ([] if w.field_type in (fitz.PDF_WIDGET_TYPE_CHECKBOX, fitz.PDF_WIDGET_TYPE_RADIOBUTTON)
                        else sur_source.get(("affiche", nom), [])) if x)
        ja = "\n".join(sur_source.get(("affiche", nom), [])) if w.field_type in (
            fitz.PDF_WIDGET_TYPE_CHECKBOX, fitz.PDF_WIDGET_TYPE_RADIOBUTTON) else ""
        for cle, texte in (("F", jf), ("K", jk), ("C", cal), ("V", jv)):
            _poser_js(doc, fx, cle, _remplacer_bloc(_js(doc, fx, cle), texte))
        for nn, ww in l:                                  # widgets : valeur auto au clic, case qui affiche/masque
            _poser_js(doc, ww.xref, "Fo", _remplacer_bloc(_js(doc, ww.xref, "Fo"),
                                                           _js_auto(r.get("auto") if r.get("_philpdf") else None, fmt)))
            _poser_js(doc, ww.xref, "U", _remplacer_bloc(_js(doc, ww.xref, "U"), ja))
    _ordre_calcul(doc, par_nom, regles, calcules)


def _ordre_calcul(doc, par_nom, regles, calcules):
    """/AcroForm/CO : un champ calcule apres ceux dont il depend (comme « Ordre de calcul » d'Acrobat)."""
    racine = doc.pdf_catalog()
    if doc.xref_get_key(racine, "AcroForm")[0] == "null":
        return
    tous_calc = [n for n, r in regles.items() if r.get("calcul")]
    deps = {n: set(sources(regles[n]["calcul"])) for n in tous_calc}
    ordre, vus = [], set()

    def visiter(n, pile=()):
        if n in vus or n in pile:
            return
        for d in deps.get(n, ()):
            if d in deps:
                visiter(d, pile + (n,))
        vus.add(n)
        ordre.append(n)
    for n in tous_calc:
        visiter(n)
    refs = []
    for n in ordre:
        w = par_nom[n][0][1]
        refs.append(f"{xref_champ(doc, w)} 0 R")
    doc.xref_set_key(racine, "AcroForm/CO", "[" + " ".join(refs) + "]" if refs else "null")


def sources(calcul):
    if not calcul:
        return []
    if calcul.get("genre") == "formule":
        try:
            return [v for t, v in jetons_formule(calcul.get("formule", "")) if t == "champ"]
        except ValueError:
            return []
    return list(calcul.get("champs", []))


# ------------------------------------------------------------------ dans PhilPDF : saisir, formater, calculer
def nombre(texte):
    """« 1 234,50 € » ou « 1,234.50 » -> 1234.5 ; None si ce n'est pas un nombre."""
    if texte is None:
        return None
    t = str(texte).strip().replace(" ", "").replace("\xa0", "").replace(" ", "").replace("'", "")
    t = re.sub(r"[^\d,.\-+()%]", "", t)
    if not t or t in "-+":
        return None
    neg = t.startswith("(") and t.endswith(")")
    t = t.strip("()%")
    if "," in t and "." in t:
        t = t.replace(".", "").replace(",", ".") if t.rfind(",") > t.rfind(".") else t.replace(",", "")
    elif "," in t:
        t = t.replace(",", ".") if t.count(",") == 1 else t.replace(",", "")
    elif t.count(".") > 1:
        t = t.replace(".", "")
    try:
        v = float(t)
    except ValueError:
        return None
    return -v if neg else v


def _nombre_txt(v, dec, sep):
    _ex, mil, decim = SEPARATEURS.get(int(sep), SEPARATEURS[2])
    s = f"{abs(v):,.{int(dec)}f}"                         # 1,234.56
    ent, _p, fr = s.partition(".")
    ent = ent.replace(",", mil)
    return ("-" if v < 0 else "") + ent + ((decim + fr) if fr else "")


def formater(regles, valeur):
    """Texte affiche dans le champ (comme Acrobat l'affiche hors saisie)."""
    fmt = (regles or {}).get("format") or {"genre": "aucun"}
    g = fmt.get("genre")
    if valeur in (None, ""):
        return ""
    if g == "nombre":
        v = nombre(valeur)
        if v is None:
            return str(valeur)
        t = _nombre_txt(v, fmt.get("decimales", 2), fmt.get("separateur", 2))
        if v < 0 and int(fmt.get("negatif", 0)) in (2, 3):
            t = "(" + t.lstrip("-") + ")"
        sym = fmt.get("symbole") or ""
        if sym:
            t = (sym.strip() + " " + t) if fmt.get("symbole_avant") else (t + " " + sym.strip())
        return t
    if g == "pourcentage":
        v = nombre(valeur)
        return str(valeur) if v is None else _nombre_txt(v * 100, fmt.get("decimales", 0), fmt.get("separateur", 2)) + " %"
    return str(valeur)


def _py_date(fmt):
    """Format Acrobat (dd/mm/yyyy HH:MM) -> strftime."""
    rep = [("yyyy", "%Y"), ("yy", "%y"), ("mmmm", "%B"), ("mmm", "%b"), ("mm", "%m"), ("dd", "%d"), ("HH", "%H"),
           ("MM", "%M"), ("ss", "%S"), ("tt", "%p")]
    out, i = "", 0
    while i < len(fmt):
        for a, b in rep:
            if fmt.startswith(a, i):
                out += b
                i += len(a)
                break
        else:
            c = fmt[i]
            out += {"d": "%-d", "m": "%-m", "H": "%-H", "h": "%-I"}.get(c, c)
            i += 1
    return out


def ecrire_date(fmt, quand=None):
    """Date (ou heure) du moment dans le format Acrobat du champ (mois en toutes lettres en francais)."""
    quand = quand or _dt.datetime.now()
    f = _py_date(fmt)
    if "%B" in f:
        f = f.replace("%B", _MOIS[quand.month - 1])
    if "%b" in f:
        f = f.replace("%b", _MOIS[quand.month - 1][:4].rstrip("."))
    import sys
    if sys.platform == "win32":
        f = f.replace("%-", "%#")
    return quand.strftime(f)


def lire_date(fmt, texte):
    """Texte saisi -> datetime selon le format (accepte aussi 28/10/2026, 28-10-26, 28.10.2026) ; None sinon."""
    texte = (texte or "").strip()
    if not texte:
        return None
    import sys
    f = _py_date(fmt).replace("%-", "%#" if sys.platform == "win32" else "%")
    for essai in (f, f.replace("%#", "%"), "%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d",
                  "%d/%m/%Y %H:%M", "%H:%M", "%H:%M:%S"):
        try:
            return _dt.datetime.strptime(texte, essai.replace("%#", "%").replace("%-", "%"))
        except ValueError:
            continue
    t = texte.lower()
    for i, m in enumerate(_MOIS):
        if m in t:
            j = re.search(r"(\d{1,2})\D+" + m + r"\D+(\d{4})", t)
            if j:
                return _dt.datetime(int(j.group(2)), i + 1, int(j.group(1)))
    return None


def _masque_ok(masque, texte):
    if len(texte) != len(masque):
        return False
    for m, c in zip(masque, texte):
        if m == "9" and not c.isdigit():
            return False
        if m == "A" and not c.isalpha():
            return False
        if m == "O" and not c.isalnum():
            return False
        if m not in "9AOX" and m != c:
            return False
    return True


def appliquer_masque(masque, texte):
    """Remet les espaces et separateurs du masque : « 0612345678 » -> « 06 12 34 56 78 »."""
    brut = [c for c in texte if c.isalnum()]
    out = []
    for m in masque:
        if m in "9AOX":
            if not brut:
                return None
            out.append(brut.pop(0))
        else:
            out.append(m)
    return "".join(out) if not brut else None


def saisie(regles, texte):
    """Valeur tapee par l'utilisateur -> (valeur a garder, message d'erreur ou None)."""
    fmt = (regles or {}).get("format") or {"genre": "aucun"}
    g = fmt.get("genre")
    texte = (texte or "").strip() if g != "aucun" else (texte or "")
    if texte == "":
        return "", None
    val = texte
    if g in ("nombre", "pourcentage"):
        v = nombre(texte)
        if v is None:
            return None, "nombre"
        if g == "pourcentage" and "%" in texte:
            v = v / 100
        val = valeur_brute(v)
    elif g == "date":
        d = lire_date(fmt.get("date") or "dd/mm/yyyy", texte)
        if d is None:
            return None, "date"
        val = ecrire_date(fmt.get("date") or "dd/mm/yyyy", d)
    elif g == "heure":
        d = lire_date(fmt.get("heure") or "HH:MM", texte)
        if d is None:
            return None, "heure"
        val = ecrire_date(fmt.get("heure") or "HH:MM", d)
    elif g == "masque":
        m = fmt.get("masque") or ""
        val = texte if _masque_ok(m, texte) else appliquer_masque(m, texte)
        if val is None:
            return None, "masque"
    plage = (regles or {}).get("plage")
    if plage and g in ("nombre", "pourcentage", "aucun"):
        v = nombre(val)
        if v is not None and ((plage.get("min") is not None and v < plage["min"]) or
                              (plage.get("max") is not None and v > plage["max"])):
            return None, "plage"
    return val, None


def calculer(regles, valeurs):
    """Valeur d'un champ calcule a partir des valeurs des autres ({nom: texte})."""
    c = (regles or {}).get("calcul")
    if not c:
        return None
    if c.get("genre") == "formule":
        try:
            jet = jetons_formule(c.get("formule", ""))
        except ValueError:
            return None
        expr = []
        for t, v in jet:
            if t == "champ":
                n = nombre(valeurs.get(v, ""))
                expr.append(repr(n if n is not None else 0.0))
            else:
                expr.append(v)
        e = " ".join(expr)
        if not re.fullmatch(r"[\d\s.+\-*/()e]*", e):
            return None
        try:
            return float(eval(e, {"__builtins__": {}}, {}))   # noqa: S307 (seulement chiffres et operateurs)
        except (ZeroDivisionError, SyntaxError, ValueError):
            return 0.0
    nums = [nombre(valeurs.get(x, "")) for x in c.get("champs", [])]
    nums = [x if x is not None else 0.0 for x in nums]
    if not nums:
        return 0.0
    g = c.get("genre")
    if g == "produit":
        r = 1.0
        for x in nums:
            r *= x
        return r
    if g == "moyenne":
        return sum(nums) / len(nums)
    if g == "min":
        return min(nums)
    if g == "max":
        return max(nums)
    return sum(nums)


def valeur_brute(v):
    """Nombre -> texte comme Acrobat le garde (point decimal, sans zeros inutiles)."""
    if v is None:
        return ""
    if abs(v - round(v)) < 1e-9:
        return str(int(round(v)))
    return ("%.6f" % v).rstrip("0").rstrip(".")
