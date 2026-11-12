"""Tables ToUnicode peu courantes (releves CAVP, banques) : plages en tableau, points de code ecrits en clair, et
glyphes en double (chiffres a chasse fixe ET proportionnels) dans une meme police. Aucun document reel."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from moteur.modifier import _parse_cmap, _chasses_fixes  # noqa: E402

ok = True


def verifier(cond, msg):
    global ok
    print(("OK   " if cond else "ECHEC ") + msg)
    ok = ok and cond


cmap = b"""begincmap
1 beginbfrange
<0000> <0005> [
<fffd> <0031> <0036> <004d> <0031> <0020>
]
endbfrange
2 beginbfrange
<0010> <0012> <0041>
endbfrange
1 beginbfchar
<0020> <1F600>
endbfchar
endcmap"""
t = _parse_cmap(cmap)
verifier(t.get(1) == "1" and t.get(2) == "6" and t.get(3) == "M" and t.get(4) == "1" and t.get(5) == " ",
         "plage en tableau : une valeur par code (avant : tout etait decale)")
verifier(t.get(0x10) == "A" and t.get(0x12) == "C", "plage ordinaire toujours lue")
verifier(t.get(0x20) == "\U0001F600", "point de code en nombre impair de chiffres (MuPDF) : plus d'erreur")


class P:            # police fusionnee : 12 glyphes a 0.6 (Courier), le reste proportionnel
    width = {**{c: 0.6 for c in range(1, 13)}, 20: 0.556, 21: 0.556, 22: 0.722}


verifier(_chasses_fixes([("M", 22, 0.722), ("A", 21, 0.556)], P) == {0.6},
         "ligne proportionnelle : la chasse fixe de la police fusionnee est evitee")
verifier(_chasses_fixes([("1", 1, 0.6), ("2", 2, 0.6)], P) == set(),
         "ligne a chasse fixe : rien n'est evite")
sys.exit(0 if ok else 1)
