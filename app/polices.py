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


def combo(parent=None, automatique=True):
    """Liste deroulante des polices, chaque nom ecrit dans sa police ; on peut taper pour chercher."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QComboBox, QCompleter
    from .langue import _
    cb = QComboBox(parent)
    cb.setEditable(True)
    cb.setInsertPolicy(QComboBox.NoInsert)
    cb.setMaxVisibleItems(18)
    if automatique:
        cb.addItem(_('Police du document (automatique)'), None)
    for p in liste():
        cb.addItem(p["nom"], p["fichier"])
        try:
            cb.setItemData(cb.count() - 1, qfont(p, 11), Qt.FontRole)
        except Exception:
            pass
    comp = QCompleter(cb.model(), cb)
    comp.setFilterMode(Qt.MatchContains)
    comp.setCaseSensitivity(Qt.CaseInsensitive)
    cb.setCompleter(comp)
    cb.lineEdit().setPlaceholderText(_("Tapez pour chercher une police"))

    def apercu(i):                                   # la police choisie s'affiche aussi dans le champ
        from PySide6.QtGui import QFont
        f = cb.itemData(i, Qt.FontRole)
        cb.lineEdit().setFont(f if isinstance(f, QFont) else QFont())
    cb.currentIndexChanged.connect(apercu)
    return cb
