"""Outil de developpement pour la traduction de PhilPDF.

  python outils_dev/i18n.py liste       textes d'interface pas encore passes par _()
  python outils_dev/i18n.py envelopper  les entoure de _() (f-strings converties en _("... {x}", x=...))
  python outils_dev/i18n.py extraire    met a jour langues/*.json avec tous les textes _("...")

Seuls les textes passes a des fonctions d'interface (setText, QLabel, addRow, question, act...)
ou ranges dans les tables d'outils sont concernes ; identifiants, raccourcis, styles, chemins
et couleurs sont laisses tels quels.
"""
import ast, json, os, re, sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FICHIERS = [os.path.join("app", f) for f in sorted(os.listdir(os.path.join(RACINE, "app")))
                             if f.endswith(".py") and f not in ("langue.py", "theme.py", "icones.py")] + \
           [os.path.join("moteur", f) for f in ("objets.py", "scanner.py")]

UI = {"setText", "setToolTip", "setWindowTitle", "setPlaceholderText", "setStatusTip", "showMessage", "message",
      "addTab", "addMenu", "addItem", "addItems", "insertItem", "setItemText", "QLabel", "QPushButton", "QCheckBox",
      "QRadioButton", "QAction", "QGroupBox", "setTitle", "question", "information", "warning", "critical",
      "getText", "getItem", "getInt", "getDouble", "getOpenFileName", "getOpenFileNames", "getSaveFileName",
      "getExistingDirectory", "getColor", "addRow", "act", "_bouton", "_petit", "QListWidgetItem", "QTableWidgetItem",
      "setHorizontalHeaderLabels", "Notification", "addButton", "setLabelText", "QProgressDialog", "setSuffix",
      "setPrefix", "setSpecialValueText", "emit", "showText", "Tuile", "setWhatsThis", "addSection",
      "insertSeparator", "note", "page", "setCancelButtonText", "_etape", "montrer", "ajouter_ligne"}
# tables de textes rangees dans des variables (nom de variable -> on enveloppe toutes les valeurs)
TABLES = {"FAMILLES", "OUTILS", "LIBELLES", "PREDEFINIS", "FILIGRANES", "CONNUS", "RACCOURCIS", "MODES", "NOMS_MODES"}
PASSAGE = (ast.IfExp, ast.BinOp, ast.BoolOp, ast.Tuple, ast.List, ast.JoinedStr, ast.Starred)

RE_CSS = re.compile(r"[a-z-]+\s*:\s*[^;]+;|^\s*Q[A-Z]\w*[\s{:#]|\{[^}]*:[^}]*;")
RE_RACCOURCI = re.compile(r"^(Ctrl|Shift|Alt|Meta|Maj|F\d+|Del|Esc|Return|Enter|Home|End|PgUp|PgDown)\b")
RE_IDENT = re.compile(r"^[a-z0-9_./\\:-]*$")


def textuel(s):
    """Vrai si la chaine est un texte a traduire (et non un identifiant, un style, un raccourci...)."""
    t = s.strip()
    if len(t) < 2 or not re.search(r"[A-Za-zÀ-ÿ]", t):
        return False
    if RE_IDENT.match(t) or RE_RACCOURCI.match(t) or RE_CSS.search(t):
        return False
    if t.startswith("#") or t.startswith("http") or re.match(r"^[\w.-]+\.(pdf|png|json|txt|exe|ico|svg)$", t, re.I):
        return False
    if t in ("OK", "PhilPDF", "PDF", "Word", "Claude", "Gemini", "GitHub", "Drive", "NAS", "OCR", "JPG", "PNG", "TXT",
             "DOCX", "IA", "API", "AES", "A4", "DPI", "WIA", "SANE"):
        return False
    return True


def nom_fonction(call):
    f = call.func
    return f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else None


def est_enveloppe(call):
    return nom_fonction(call) in ("_", "N_")


class Collecte(ast.NodeVisitor):
    def __init__(self, src):
        self.src, self.cibles, self.parents = src, [], []

    def generic_visit(self, node):
        self.parents.append(node)
        super().generic_visit(node)
        self.parents.pop()

    def _sous_arbre(self, n):
        """Constantes et f-strings textuelles d'un argument, a travers les noeuds de passage seulement."""
        if isinstance(n, ast.Constant) and isinstance(n.value, str):
            if textuel(n.value):
                self.cibles.append(n)
        elif isinstance(n, ast.JoinedStr):
            fixe = "".join(v.value for v in n.values if isinstance(v, ast.Constant))
            if textuel(fixe + " x") and re.search(r"[A-Za-zÀ-ÿ]{2}", fixe):
                self.cibles.append(n)
        elif isinstance(n, PASSAGE):
            for c in ast.iter_child_nodes(n):
                if isinstance(n, ast.BinOp) and not isinstance(n.op, ast.Add):
                    return
                self._sous_arbre(c)
        elif isinstance(n, ast.Dict):
            for v in n.values:
                self._sous_arbre(v)

    def visit_Call(self, node):
        if est_enveloppe(node):
            return
        if nom_fonction(node) in UI:
            for a in node.args:
                self._sous_arbre(a)
            for k in node.keywords:
                if k.arg in (None, "text", "aide", "titre", "texte", "caption", "label", "title", "bouton"):
                    self._sous_arbre(k.value)
        self.generic_visit(node)

    def visit_Assign(self, node):
        noms = [t.id for t in node.targets if isinstance(t, ast.Name)]
        if any(n in TABLES for n in noms):
            self._table(node.value)
        self.generic_visit(node)

    def _table(self, n):
        if isinstance(n, ast.Dict):
            for v in n.values:
                self._table(v)
        elif isinstance(n, (ast.Tuple, ast.List)):
            for v in n.elts:
                self._table(v)
        else:
            self._sous_arbre(n)


def nom_place(expr, src, pris):
    seg = ast.get_source_segment(src, expr) or "x"
    if isinstance(expr, ast.Name):
        base = expr.id
    elif isinstance(expr, ast.Attribute):
        base = expr.attr
    elif isinstance(expr, ast.Subscript) and isinstance(expr.slice, ast.Constant) and isinstance(expr.slice.value, str):
        base = expr.slice.value
    elif isinstance(expr, ast.Call) and nom_fonction(expr):
        base = {"len": "n", "basename": "nom", "date_fr": "date", "nb_fichiers": "nb"}.get(nom_fonction(expr), nom_fonction(expr))
    else:
        base = "x"
    base = re.sub(r"\W", "_", base).strip("_") or "x"
    if base[0].isdigit():
        base = "v" + base
    nom, i = base, 2
    while nom in pris and pris[nom] != seg:
        nom, i = f"{base}{i}", i + 1
    pris[nom] = seg
    return nom, seg


def remplacement(n, src):
    if isinstance(n, ast.Constant):
        return "_(" + repr(n.value) + ")"
    cle, pris = "", {}
    for v in n.values:
        if isinstance(v, ast.Constant):
            cle += v.value.replace("{", "{{").replace("}", "}}")
        else:
            nom, seg = nom_place(v.value, src, pris)
            spec = ""
            if v.conversion != -1:
                spec += "!" + chr(v.conversion)
            if v.format_spec is not None:
                spec += ":" + "".join(x.value for x in v.format_spec.values if isinstance(x, ast.Constant))
            cle += "{" + nom + spec + "}"
    args = ", ".join(f"{k}={s}" for k, s in pris.items())
    return "_(" + repr(cle) + (", " + args if args else "") + ")"


def cibles(chemin):
    src = open(chemin, encoding="utf-8").read()
    c = Collecte(src)
    c.visit(ast.parse(src))
    vus, out = set(), []
    for n in sorted(c.cibles, key=lambda n: (n.lineno, n.col_offset)):
        k = (n.lineno, n.col_offset)
        if k not in vus:
            vus.add(k)
            out.append(n)
    return src, out


def decalages(src):
    lignes = src.splitlines(keepends=True)
    pos, acc = [0], 0
    for l in lignes:
        acc += len(l.encode("utf-8"))
        pos.append(acc)
    return pos


def envelopper(chemin):
    src, cs = cibles(chemin)
    if not cs:
        return 0
    b = src.encode("utf-8")
    pos = decalages(src)
    morceaux, fin = [], len(b)
    for n in sorted(cs, key=lambda n: (n.lineno, n.col_offset), reverse=True):
        a = pos[n.lineno - 1] + n.col_offset
        z = pos[n.end_lineno - 1] + n.end_col_offset
        if z > fin:
            continue                     # imbrique dans une cible deja traitee
        morceaux.append(b[z:fin])
        morceaux.append(remplacement(n, src).encode("utf-8"))
        fin = a
    morceaux.append(b[:fin])
    nouveau = b"".join(reversed(morceaux)).decode("utf-8")
    if "from app.langue import _" not in nouveau and "from .langue import _" not in nouveau:
        imp = "from .langue import _\n" if chemin.startswith("app") else "from app.langue import _\n"
        lignes = nouveau.splitlines(keepends=True)
        arbre = ast.parse(nouveau)
        der = max((s.end_lineno for s in arbre.body if isinstance(s, (ast.Import, ast.ImportFrom))), default=0)
        lignes.insert(der, imp)
        nouveau = "".join(lignes)
    ast.parse(nouveau)
    open(chemin, "w", encoding="utf-8").write(nouveau)
    return len(cs)


def textes_du_code():
    out = {}
    for f in FICHIERS + [os.path.join("app", "session.py"), os.path.join("moteur", "modifier.py")]:
        p = os.path.join(RACINE, f)
        if not os.path.exists(p):
            continue
        for n in ast.walk(ast.parse(open(p, encoding="utf-8").read())):
            if isinstance(n, ast.Call) and est_enveloppe(n) and n.args and isinstance(n.args[0], ast.Constant):
                out.setdefault(n.args[0].value, f)
    return out


def extraire():
    textes = textes_du_code()
    d = os.path.join(RACINE, "langues")
    os.makedirs(d, exist_ok=True)
    for f in sorted(os.listdir(d)):
        if not f.endswith(".json"):
            continue
        p = os.path.join(d, f)
        ancien = json.load(open(p, encoding="utf-8"))
        nouveau = {"_langue": ancien.get("_langue", f[:-5]),
                   "_aide": "Cles = textes francais de PhilPDF ; valeurs = traduction. Garder les {noms} tels quels. "
                            "Valeur vide = francais affiche."}
        for t in sorted(textes, key=str.lower):
            nouveau[t] = ancien.get(t, "")
        manquants = sum(1 for t in textes if not nouveau[t])
        obsoletes = [k for k in ancien if not k.startswith("_") and k not in textes]
        json.dump(nouveau, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"{f} : {len(textes)} textes, {manquants} a traduire, {len(obsoletes)} obsoletes retires")


if __name__ == "__main__":
    os.chdir(RACINE)
    action = sys.argv[1] if len(sys.argv) > 1 else "liste"
    if action == "liste":
        total = 0
        for f in FICHIERS:
            src, cs = cibles(f)
            total += len(cs)
            for n in cs:
                print(f"{f}:{n.lineno}: {remplacement(n, src)[:110]}")
        print(f"\n{total} textes a envelopper")
    elif action == "envelopper":
        for f in FICHIERS:
            print(f, envelopper(f))
    elif action == "extraire":
        extraire()
