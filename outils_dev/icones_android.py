"""Genere android/.../Icones.kt a partir des icones de PhilPDF Windows (app/icones.py) : memes traits partout.
Lancement : python outils_dev/icones_android.py"""
import os, re, sys
ici = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ici)
src = open(os.path.join(ici, "app", "icones.py"), encoding="utf-8").read()
bloc = src[src.index("TRAITS = {"):src.index("\n}\n") + 2]
TRAITS = {}
exec(bloc, {}, {"TRAITS": TRAITS}) if False else None
ns = {}
exec(bloc, ns)
TRAITS = ns["TRAITS"]


def attr(e, k, d=0.0):
    m = re.search(r'\b' + k + r'="([^"]+)"', e)
    return float(m.group(1)) if m else d


def chemins(svg):
    out = []
    for e in re.findall(r"<(?:path|rect|circle)[^>]*>", svg):
        if e.startswith("<path"):
            out.append(re.search(r'\bd="([^"]+)"', e).group(1))
        elif e.startswith("<rect"):
            x, y, w, h, rx = attr(e, "x"), attr(e, "y"), attr(e, "width"), attr(e, "height"), attr(e, "rx")
            if rx:
                out.append(f"M{x+rx} {y}h{w-2*rx}a{rx} {rx} 0 0 1 {rx} {rx}v{h-2*rx}a{rx} {rx} 0 0 1 -{rx} {rx}"
                           f"h-{w-2*rx}a{rx} {rx} 0 0 1 -{rx} -{rx}v-{h-2*rx}a{rx} {rx} 0 0 1 {rx} -{rx}z")
            else:
                out.append(f"M{x} {y}h{w}v{h}h-{w}z")
        else:
            cx, cy, r = attr(e, "cx"), attr(e, "cy"), attr(e, "r")
            out.append(f"M{cx-r} {cy}a{r} {r} 0 1 0 {2*r} 0a{r} {r} 0 1 0 -{2*r} 0")
    return out


lignes = []
for nom, svg in TRAITS.items():
    if "<text" in svg:
        continue
    cs = ", ".join('"' + c.replace('"', '') + '"' for c in chemins(svg))
    lignes.append(f'        "{nom}" to listOf({cs}),')
kt = '''package io.github.philouelchapo.philpdf

// Fichier genere par outils_dev/icones_android.py a partir de app/icones.py (icones de PhilPDF Windows).
// Ne pas modifier a la main : relancer le script.

import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.graphics.vector.PathParser
import androidx.compose.ui.unit.dp

object Icones {
    val TRAITS: Map<String, List<String>> = mapOf(
''' + "\n".join(lignes) + '''
    )
    private val cache = HashMap<String, ImageVector>()

    /** Icone au trait (24 x 24, trait 1,8, extremites arrondies), comme sous Windows. */
    fun get(nom: String, couleur: Color = Color(0xFF333333)): ImageVector = cache.getOrPut(nom + couleur.value) {
        val b = ImageVector.Builder(name = nom, defaultWidth = 24.dp, defaultHeight = 24.dp, viewportWidth = 24f, viewportHeight = 24f)
        for (d in TRAITS[nom] ?: TRAITS.getValue("creer")) {
            b.addPath(PathParser().parsePathString(d).toNodes(), stroke = SolidColor(couleur), strokeLineWidth = 1.8f,
                strokeLineCap = StrokeCap.Round, strokeLineJoin = StrokeJoin.Round)
        }
        b.build()
    }
}
'''
out = os.path.join(ici, "android", "app", "src", "main", "java", "io", "github", "philouelchapo", "philpdf", "Icones.kt")
open(out, "w", encoding="utf-8").write(kt)
print(len(lignes), "icones ->", out)
