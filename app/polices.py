"""Polices disponibles : celles fournies avec PhilPDF et celles installees sur ce poste (Windows ou Linux).

La liste est affichee « telle quelle » (WYSIWYG) : chaque nom est ecrit dans sa propre police. Elle est gardee en
cache dans le dossier de donnees et refaite seulement quand les dossiers de polices changent.
"""
import json, os, re, sys

import pymupdf as fitz

_BASE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STYLES = r"\b(Regular|Bold|Italic|Oblique|Light|Medium|SemiBold|Semibold|Demibold|ExtraBold|Black|Thin|Book|Roman|Condensed|Narrow|ExtraLight|Heavy)\b"


def dossiers():
    d = [os.path.join(_BASE, "fonts")]
    if sys.platform == "win32":
        d += [os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"),
              os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Windows", "Fonts")]
    else:
        d += ["/usr/share/fonts", "/usr/local/share/fonts", os.path.expanduser("~/.local/share/fonts"),
              os.path.expanduser("~/.fonts"), "/Library/Fonts", os.path.expanduser("~/Library/Fonts")]
    return [x for x in d if x and os.path.isdir(x)]


def _signature(ds):
    return ";".join(f"{x}:{int(os.path.getmtime(x))}" for x in ds)


def _decrire(fichier):
    try:
        f = fitz.Font(fontfile=fichier)
    except Exception:
        return None
    nom = (f.name or "").strip()
    if not nom or nom.startswith(("Unnamed", ".")):
        return None
    famille = re.sub(r"\s+", " ", re.sub(STYLES, "", nom)).strip(" -,") or nom
    return {"nom": nom, "famille": famille, "gras": bool(f.is_bold), "italique": bool(f.is_italic), "fichier": fichier}


def liste(limite=1500):
    """[{"nom", "famille", "gras", "italique", "fichier"}], polices de PhilPDF d'abord puis par ordre alphabetique."""
    from .config import dossier_donnees
    ds = dossiers()
    cache = os.path.join(dossier_donnees(), "polices.json")
    sig = _signature(ds)
    try:
        with open(cache, encoding="utf-8") as f:
            d = json.load(f)
        if d.get("signature") == sig:
            return d["polices"]
    except (OSError, ValueError):
        pass
    out, vus = [], set()
    for k, dossier in enumerate(ds):
        for racine, _s, fichiers in os.walk(dossier):
            for n in sorted(fichiers):
                if not n.lower().endswith((".ttf", ".otf")):
                    continue
                p = _decrire(os.path.join(racine, n))
                if p and p["nom"].lower() not in vus:
                    vus.add(p["nom"].lower())
                    p["fournie"] = k == 0
                    out.append(p)
                if len(out) >= limite:
                    break
    out.sort(key=lambda p: (not p["fournie"], p["nom"].lower()))
    try:
        with open(cache, "w", encoding="utf-8") as f:
            json.dump({"signature": sig, "polices": out}, f, ensure_ascii=False)
    except OSError:
        pass
    return out


_enregistrees = {}
_fam_qt = []


def _familles_qt():
    from PySide6.QtGui import QFontDatabase
    if not _fam_qt:
        _fam_qt.append(set(QFontDatabase.families()))
    return _fam_qt[0]


def qfont(p, taille=11):
    """QFont qui affiche la police p (fichier enregistre aupres de Qt au besoin)."""
    from PySide6.QtGui import QFont, QFontDatabase
    fam = p["famille"]
    if p.get("fournie") or fam not in _familles_qt():
        if p["fichier"] not in _enregistrees and len(_enregistrees) < 250:
            i = QFontDatabase.addApplicationFont(p["fichier"])
            fams = QFontDatabase.applicationFontFamilies(i) if i >= 0 else []
            _enregistrees[p["fichier"]] = fams[0] if fams else fam
        fam = _enregistrees.get(p["fichier"], fam)
    f = QFont(fam)
    f.setPointSize(taille)
    f.setBold(p["gras"])
    f.setItalic(p["italique"])
    return f


EQUIVALENTS = {"helvetica": ["arial", "liberationsans"], "arialmt": ["arial", "liberationsans"],
               "times": ["timesnewroman", "liberationserif"], "timesnewromanpsmt": ["timesnewroman", "liberationserif"],
               "courier": ["couriernew", "liberationmono"], "calibri": ["calibri", "carlito"], "cambria": ["cambria", "caladea"]}


def _norme(t):
    return re.sub(r"[^a-z0-9]", "", (t or "").lower())


def _famille_pdf(base):
    """'ABCDEF+Arial-BoldMT' -> 'arial' ; 'TimesNewRomanPS-ItalicMT' -> 'timesnewroman'."""
    b = base.split("+", 1)[-1]
    b = re.split(r"[-,]", b)[0]
    b = re.sub(STYLES, "", b)
    n = _norme(b)
    for fin in ("psmt", "mt", "ps"):
        if n.endswith(fin) and len(n) > len(fin) + 2:
            n = n[:-len(fin)]
    return n


def polices_document(doc, pages=60):
    """(polices installees correspondant a celles du PDF, noms du PDF sans equivalent installe)."""
    noms = []
    for k in range(min(len(doc), pages)):
        try:
            for f in doc[k].get_fonts():
                if f[3] and f[3] not in noms:
                    noms.append(f[3])
        except Exception:
            pass
    toutes = liste()
    par_famille = {}
    for p in toutes:
        par_famille.setdefault(_norme(p["famille"]), []).append(p)
    trouvees, absentes, vus = [], [], set()
    for base in noms:
        fam = _famille_pdf(base)
        cands = []
        for f in [fam] + EQUIVALENTS.get(fam, []):
            cands = par_famille.get(f) or [p for k, ps in par_famille.items() if k.startswith(f) and len(f) >= 4 for p in ps]
            if cands:
                break
        if not cands:
            nom = base.split("+", 1)[-1]
            if nom not in absentes:
                absentes.append(nom)
        for p in cands:
            if p["fichier"] not in vus:
                vus.add(p["fichier"])
                trouvees.append(p)
    trouvees.sort(key=lambda p: p["nom"].lower())
    return trouvees, absentes


def _classe_combo():
    from PySide6.QtCore import Qt, Signal
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import QComboBox, QCompleter, QWidget, QVBoxLayout
    from .langue import _

    class ComboPolices(QComboBox):
        """Liste des polices, chaque nom ecrit dans sa police. Une petite liste au-dessus choisit
        « Polices du document » (courte) ou « Toutes les polices ». En survolant la liste deroulante,
        la police s'applique aussitot au texte en cours (signal apercu) ; Echap revient a la police choisie."""
        apercu = Signal(object)                     # dict de police (ou None = police du document)

        def __init__(self, parent=None, automatique=True, doc=None):
            super().__init__(parent)
            self.automatique, self._doc = automatique, doc
            self.setEditable(True)
            self.setInsertPolicy(QComboBox.NoInsert)
            self.setMaxVisibleItems(18)
            self.portee = QComboBox()
            self.portee.addItem(_("Polices du document"), "document")
            self.portee.addItem(_("Toutes les polices"), "toutes")
            self.portee.setToolTip(_("Liste courte (polices utilisées par ce PDF) ou toutes les polices de l'ordinateur"))
            self.portee.setCurrentIndex(0 if doc is not None else 1)
            self.portee.currentIndexChanged.connect(lambda _i: self.remplir())
            self.lineEdit().setPlaceholderText(_("Tapez pour chercher une police"))
            self.highlighted.connect(self._survol)
            self.currentIndexChanged.connect(self._choisie)
            self._par_fichier = {}
            self.remplir()

        def set_document(self, doc):
            self._doc = doc
            if self.portee.currentData() == "document":
                self.remplir()

        def document(self):
            d = self._doc() if callable(self._doc) else self._doc
            return d

        def ligne(self):
            w = QWidget()
            v = QVBoxLayout(w)
            v.setContentsMargins(0, 0, 0, 0)
            v.setSpacing(3)
            v.addWidget(self.portee)
            v.addWidget(self)
            return w

        def remplir(self):
            garde = self.currentData()
            self.blockSignals(True)
            self.clear()
            if self.automatique:
                self.addItem(_('Police du document (automatique)'), None)
            doc = self.document()
            if self.portee.currentData() == "document" and doc is not None:
                ps, absentes = polices_document(doc)
            else:
                ps, absentes = liste(), []
            for p in ps:
                self._par_fichier[p["fichier"]] = p
                self.addItem(p["nom"], p["fichier"])
                try:
                    self.setItemData(self.count() - 1, qfont(p, 11), Qt.FontRole)
                except Exception:
                    pass
            for nom in absentes:
                self.addItem(_("{nom} (dans le PDF, non installée)", nom=nom), None)
                it = self.model().item(self.count() - 1)
                it.setEnabled(False)
            if self.portee.currentData() == "document" and not ps:
                self.addItem(_("(aucune police du document installée : voir « Toutes les polices »)"), None)
                self.model().item(self.count() - 1).setEnabled(False)
            comp = QCompleter(self.model(), self)
            comp.setFilterMode(Qt.MatchContains)
            comp.setCaseSensitivity(Qt.CaseInsensitive)
            self.setCompleter(comp)
            i = self.findData(garde) if garde else 0
            self.setCurrentIndex(max(0, i))
            self.blockSignals(False)
            self._choisie(self.currentIndex())

        def police(self, i=None):
            f = self.itemData(self.currentIndex() if i is None else i)
            return self._par_fichier.get(f) if f else None

        def showPopup(self):
            if self.portee.currentData() == "document":
                self.remplir()
            super().showPopup()

        def _survol(self, i):
            f = self.itemData(i, Qt.FontRole)
            self.lineEdit().setFont(f if isinstance(f, QFont) else QFont())
            self.apercu.emit(self.police(i))

        def _choisie(self, i):
            f = self.itemData(i, Qt.FontRole)
            self.lineEdit().setFont(f if isinstance(f, QFont) else QFont())
            self.apercu.emit(self.police(i))

        def hidePopup(self):
            super().hidePopup()
            self._choisie(self.currentIndex())      # Echap ou clic dehors : retour a la police choisie

    return ComboPolices


_Combo = []


def combo(parent=None, automatique=True, doc=None):
    """Liste deroulante des polices (voir ComboPolices) ; combo.ligne() = liste + choix document / toutes."""
    if not _Combo:
        _Combo.append(_classe_combo())
    return _Combo[0](parent, automatique, doc)
