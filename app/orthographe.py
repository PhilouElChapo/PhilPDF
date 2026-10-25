"""Correcteur d'orthographe embarque (dictionnaires de pyspellchecker, sans Internet).

Les mots soulignes en rouge se corrigent d'un clic droit (suggestions, « Ajouter au dictionnaire »).
Le dictionnaire personnel est celui de la reconnaissance de texte : un mot ajoute ici est aussi connu de l'OCR,
et il suit vos postes par la synchronisation des apprentissages.
"""
import re

LANGUES = {"fr", "en", "es", "de", "it", "pt", "nl", "ru", "ar", "eu", "lv", "fa"}
MOT = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿŒœ]+(?:['’][A-Za-zÀ-ÖØ-öø-ÿŒœ]+)?")
_cache = {}


def langue(params):
    l = (params.get("langue") or "auto") if params else "auto"
    if l == "auto":
        try:
            from .langue import langue_systeme
            l = langue_systeme()
        except Exception:
            l = "fr"
    l = (l or "fr")[:2]
    return l if l in LANGUES else "fr"


def correcteur(params=None):
    l = langue(params)
    if l not in _cache:
        from spellchecker import SpellChecker
        _cache[l] = SpellChecker(language=l, case_sensitive=False)
    sc = _cache[l]
    if params is not None:
        try:
            from .apprentissage import ocr_appris
            perso = [m.lower() for m in ocr_appris(params)["mots"]]
            if perso:
                sc.word_frequency.load_words(perso)
        except Exception:
            pass
    return sc


def _decouper(mot):
    """« l'orthographe » -> on verifie « orthographe » (elisions francaises)."""
    m = mot.replace("’", "'")
    if "'" in m:
        avant, apres = m.split("'", 1)
        if len(avant) <= 2 or avant.lower() in ("jusqu", "lorsqu", "puisqu", "quoiqu", "presqu", "quelqu"):
            return len(avant) + 1, apres
    return 0, m


def fautes(texte, params=None):
    """[(debut, fin, mot)] des mots inconnus ; noms propres et sigles evites autant que possible."""
    try:
        sc = correcteur(params)
    except Exception:
        return []
    out = []
    for m in MOT.finditer(texte):
        dec, mot = _decouper(m.group())
        if len(mot) < 2 or mot.isupper():
            continue
        if mot.lower() in sc:
            continue
        if mot[0].isupper() and m.start() > 0 and not re.search(r"[.!?:]\s*$", texte[:m.start()]):
            continue                                  # majuscule en milieu de phrase : sans doute un nom propre
        out.append((m.start() + dec, m.end(), mot))
    return out


def suggestions(mot, params=None, n=6):
    try:
        sc = correcteur(params)
    except Exception:
        return []
    c = sc.candidates(mot.lower()) or set()
    meilleurs = sorted(c, key=lambda w: -sc.word_usage_frequency(w))[:n]
    if mot[:1].isupper():
        meilleurs = [w[:1].upper() + w[1:] for w in meilleurs]
    return [w for w in meilleurs if w.lower() != mot.lower()]


def surligneur(document, params):
    """QSyntaxHighlighter : vague rouge sous les mots inconnus."""
    from PySide6.QtGui import QSyntaxHighlighter, QTextCharFormat, QColor

    class Surligneur(QSyntaxHighlighter):
        def highlightBlock(self, texte):
            f = QTextCharFormat()
            f.setUnderlineStyle(QTextCharFormat.SpellCheckUnderline)
            f.setUnderlineColor(QColor("#d01c1c"))
            for a, b, _m in fautes(texte, params):
                self.setFormat(a, b - a, f)
    return Surligneur(document)


def menu_correction(zone, pos, params, menu):
    """Ajoute en tete du menu (clic droit) les suggestions pour le mot sous le curseur. Renvoie True si mot fautif."""
    from PySide6.QtGui import QAction
    from .langue import _
    c = zone.cursorForPosition(pos)
    bloc = c.block()
    texte, x = bloc.text(), c.positionInBlock()
    for a, b, mot in fautes(texte, params):
        if a <= x <= b:
            premier = menu.actions()[0] if menu.actions() else None
            sugg = suggestions(mot, params)

            def remplacer(nouveau, a=a, b=b):
                cc = zone.textCursor()
                cc.setPosition(bloc.position() + a)
                cc.setPosition(bloc.position() + b, cc.MoveMode.KeepAnchor)
                cc.insertText(nouveau)
            for s in sugg or []:
                act = QAction(s, menu)
                f = act.font()
                f.setBold(True)
                act.setFont(f)
                act.triggered.connect(lambda _c=False, s=s: remplacer(s))
                menu.insertAction(premier, act)
            if not sugg:
                act = QAction(_("(aucune suggestion)"), menu)
                act.setEnabled(False)
                menu.insertAction(premier, act)

            def ajouter():
                from .apprentissage import ajouter_mot
                ajouter_mot(params, mot)
                correcteur(params)
                zone.document().markContentsDirty(0, zone.document().characterCount())
                h = getattr(zone, "_surligneur", None)
                h and h.rehighlight()
            act = QAction(_("Ajouter « {mot} » au dictionnaire", mot=mot), menu)
            act.triggered.connect(ajouter)
            menu.insertAction(premier, act)
            menu.insertSeparator(premier)
            return True
    return False
