"""Correcteur d'orthographe embarque (dictionnaires de pyspellchecker, sans Internet).

Les mots soulignes en rouge se corrigent d'un clic droit (suggestions, « Ajouter au dictionnaire »).
Le dictionnaire personnel est celui de la reconnaissance de texte : un mot ajoute ici est aussi connu de l'OCR,
et il suit vos postes par la synchronisation des apprentissages.
"""
import re

LANGUES = {"fr", "en", "es", "de", "it", "pt", "nl", "ru", "ar", "eu", "lv", "fa"}
NOMS = {"fr": "Français", "en": "English", "de": "Deutsch", "es": "Español", "it": "Italiano", "pt": "Português",
        "nl": "Nederlands"}
# mots tres courants : suffisent a reconnaitre la langue d'un texte sans charger les dictionnaires
COURANTS = {
    "fr": "le la les des du de et est un une pour dans que qui sur pas par au aux avec ce cette sont nous vous il elle".split(),
    "en": "the and of to is in that for it with as was on are be this by have from or not you your we".split(),
    "de": "der die das und ist nicht mit den von zu sie ein eine für auf dem des sich auch wir ich".split(),
    "es": "el la los las de y que en es por con para una un del se no su al como más pero".split(),
    "it": "il la le di e che è per un una con non del della sono si da gli al nel ma".split(),
    "pt": "o a os as de e que em é um uma para com não do da no na se por".split(),
    "nl": "de het een en van is dat op te in voor met niet zijn er aan ook".split(),
}
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


def detecter(texte, defaut="fr"):
    """Langue d'un texte d'apres ses mots courants (rapide, sans dictionnaire) ; defaut si trop court."""
    mots = [m.lower() for m in MOT.findall(texte)]
    if len(mots) < 3:
        return defaut
    scores = {l: sum(1 for m in mots if m in set(c)) for l, c in COURANTS.items()}
    l, n = max(scores.items(), key=lambda kv: kv[1])
    return l if n >= 2 and n > scores.get(defaut, 0) else defaut


def langue_pour(texte, params):
    """Langue du correcteur : choisie par l'utilisateur, sinon detectee sur le texte (langue de PhilPDF par defaut)."""
    choix = (params or {}).get("orthographe_langue") or "auto"
    return choix if choix != "auto" else detecter(texte, langue(params))


def correcteur(params=None, l=None):
    l = l or langue(params)
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


def fautes(texte, params=None, l=None):
    """[(debut, fin, mot)] des mots inconnus ; noms propres et sigles evites autant que possible."""
    try:
        sc = correcteur(params, l)
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


def suggestions(mot, params=None, n=6, l=None):
    try:
        sc = correcteur(params, l)
    except Exception:
        return []
    c = sc.candidates(mot.lower()) or set()
    meilleurs = sorted(c, key=lambda w: -sc.word_usage_frequency(w))[:n]
    if mot[:1].isupper():
        meilleurs = [w[:1].upper() + w[1:] for w in meilleurs]
    return [w for w in meilleurs if w.lower() != mot.lower()]


def surligneur(document, params, contexte=""):
    """QSyntaxHighlighter : vague rouge sous les mots inconnus. La langue est detectee sur le texte en cours
    et le contexte (le reste de la page), sauf si l'utilisateur l'a choisie."""
    from PySide6.QtGui import QSyntaxHighlighter, QTextCharFormat, QColor

    class Surligneur(QSyntaxHighlighter):
        langue = langue_pour(document.toPlainText() + " " + contexte, params)

        def highlightBlock(self, texte):
            f = QTextCharFormat()
            f.setUnderlineStyle(QTextCharFormat.SpellCheckUnderline)
            f.setUnderlineColor(QColor("#d01c1c"))
            for a, b, _m in fautes(texte, params, self.langue):
                self.setFormat(a, b - a, f)
    return Surligneur(document)


def menu_correction(zone, pos, params, menu):
    """Ajoute en tete du menu (clic droit) les suggestions pour le mot sous le curseur. Renvoie True si mot fautif."""
    from PySide6.QtGui import QAction
    from .langue import _
    c = zone.cursorForPosition(pos)
    bloc = c.block()
    texte, x = bloc.text(), c.positionInBlock()
    h = getattr(zone, "_surligneur", None)
    l = h.langue if h is not None else None
    for a, b, mot in fautes(texte, params, l):
        if a <= x <= b:
            premier = menu.actions()[0] if menu.actions() else None
            sugg = suggestions(mot, params, l=l)

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
                correcteur(params, l)
                zone.document().markContentsDirty(0, zone.document().characterCount())
                h = getattr(zone, "_surligneur", None)
                h and h.rehighlight()
            act = QAction(_("Ajouter « {mot} » au dictionnaire", mot=mot), menu)
            act.triggered.connect(ajouter)
            menu.insertAction(premier, act)
            menu.insertSeparator(premier)
            return True
    return False


def menu_langue(menu, params, langue_detectee, rappel):
    """Sous-menu « Langue du correcteur » : automatique (detectee) ou une langue imposee."""
    from PySide6.QtGui import QActionGroup
    from .langue import _
    sm = menu.addMenu(_("Langue du correcteur"))
    g = QActionGroup(sm)
    actuel = params.get("orthographe_langue") or "auto"
    for code, nom in [("auto", _("Automatique (détectée : {langue})", langue=NOMS.get(langue_detectee, langue_detectee)))] + \
            list(NOMS.items()):
        a = sm.addAction(nom)
        a.setCheckable(True)
        a.setChecked(code == actuel)
        g.addAction(a)
        a.triggered.connect(lambda _c=False, k=code: rappel(k))
    return sm
