"""Noms de glyphes Adobe (polices dont l'encodage est une liste « Differences » : /A /eacute /zero...) -> lettre.
Les plus courants en francais et en Europe de l'Ouest ; « uniXXXX » et « uXXXX » aussi."""
import unicodedata

_PONCT = {
    "space": " ", "exclam": "!", "quotedbl": '"', "numbersign": "#", "dollar": "$", "percent": "%", "ampersand": "&",
    "quotesingle": "'", "quoteright": "’", "quoteleft": "‘", "parenleft": "(", "parenright": ")",
    "asterisk": "*", "plus": "+", "comma": ",", "hyphen": "-", "minus": "−", "period": ".", "slash": "/",
    "colon": ":", "semicolon": ";", "less": "<", "equal": "=", "greater": ">", "question": "?", "at": "@",
    "bracketleft": "[", "backslash": "\\", "bracketright": "]", "underscore": "_", "grave": "`", "braceleft": "{",
    "bar": "|", "braceright": "}", "asciitilde": "~", "asciicircum": "^", "degree": "°", "Euro": "€",
    "euro": "€", "sterling": "£", "section": "§", "paragraph": "¶", "guillemotleft": "«",
    "guillemotright": "»", "endash": "–", "emdash": "—", "bullet": "•", "ellipsis": "…",
    "quotedblleft": "“", "quotedblright": "”", "quotesinglbase": "‚", "quotedblbase": "„",
    "ordmasculine": "º", "ordfeminine": "ª", "copyright": "©", "registered": "®",
    "trademark": "™", "multiply": "×", "divide": "÷", "nbspace": " ", "uni00A0": " ",
    "germandbls": "ß", "oe": "œ", "OE": "Œ", "ae": "æ", "AE": "Æ", "oslash": "ø",
    "Oslash": "Ø", "exclamdown": "¡", "questiondown": "¿", "periodcentered": "·",
    "twosuperior": "²", "threesuperior": "³", "onesuperior": "¹", "mu": "µ", "plusminus": "±",
    "onehalf": "½", "onequarter": "¼", "threequarters": "¾", "fi": "ﬁ", "fl": "ﬂ",
}
_CHIFFRES = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"]
_ACCENTS = {"acute": "ACUTE", "grave": "GRAVE", "circumflex": "CIRCUMFLEX", "dieresis": "DIAERESIS",
            "tilde": "TILDE", "cedilla": "CEDILLA", "ring": "RING ABOVE", "caron": "CARON"}


def table():
    """{nom de glyphe: lettre} : lettres, chiffres, ponctuation, lettres accentuees."""
    t = dict(_PONCT)
    for i, n in enumerate(_CHIFFRES):
        t[n] = str(i)
    for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz":
        t[c] = c
    for base in "AEIOUYCNSZaeiouycnsz":
        for nom, u in _ACCENTS.items():
            try:
                t[base + nom] = unicodedata.lookup(f"LATIN {'CAPITAL' if base.isupper() else 'SMALL'} LETTER {base.upper()} WITH {u}")
            except KeyError:
                pass
    return t


_TABLE = table()


def lettre(nom):
    """Lettre d'un nom de glyphe, ou None."""
    if nom in _TABLE:
        return _TABLE[nom]
    for p in ("uni", "u"):
        if nom.startswith(p) and len(nom) in (len(p) + 4, len(p) + 5):
            try:
                return chr(int(nom[len(p):], 16))
            except ValueError:
                return None
    return None


def differences(texte):
    """« [ 32 /space 48 /zero /one ] » -> {code: lettre}."""
    import re
    out, code = {}, None
    for tok in re.findall(r"-?\d+|/[^\s/\[\]<>()]+", texte):     # « 32/space 48/zero » : sans espaces aussi
        if tok.lstrip("-").isdigit():
            code = int(tok)
        elif tok.startswith("/") and code is not None:
            l = lettre(tok[1:])
            if l:
                out[code] = l
            code += 1
    return out
