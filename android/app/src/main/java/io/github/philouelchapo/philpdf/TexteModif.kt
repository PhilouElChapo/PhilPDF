package io.github.philouelchapo.philpdf

import com.artifex.mupdf.fitz.Font
import com.artifex.mupdf.fitz.Image
import com.artifex.mupdf.fitz.Matrix
import com.artifex.mupdf.fitz.PDFDocument
import com.artifex.mupdf.fitz.PDFObject
import com.artifex.mupdf.fitz.PDFPage
import com.artifex.mupdf.fitz.Point
import com.artifex.mupdf.fitz.Quad
import com.artifex.mupdf.fitz.Rect
import com.artifex.mupdf.fitz.StructuredTextWalker

/*
 * Modifier le texte d'une page (methode « A », comme Acrobat) :
 *  1. on retire SEULEMENT les lettres de la ligne (caviardage « texte seul » de MuPDF) : le fond, les cadres,
 *     les images et les traits restent intacts, aucun rectangle blanc ;
 *  2. on reecrit la ligne avec la POLICE D'ORIGINE du PDF, en retrouvant les codes de chaque lettre par sa table
 *     ToUnicode (ou WinAnsi) ; le texte reste du vrai texte, selectionnable et cherchable.
 *  Secours (« B ») : si la police d'origine n'a pas une lettre tapee (police reduite aux lettres utilisees),
 *  la ligne est ecrite dans la police standard la plus proche (Helvetica, Times, Courier ; gras, italique) — on
 *  le dit avant d'appliquer.
 */

/** Une ligne de texte de la page (coordonnees de la page en points, y vers le bas). */
data class LigneTexte(val texte: String, val x0: Float, val x1: Float, val base: Float, val haut: Float, val bas: Float,
                      val taille: Float, val argb: Int, val police: String, val gras: Boolean, val italique: Boolean,
                      val serif: Boolean, val mono: Boolean)

/** Codes d'une police du PDF : lettre -> code (1 ou 2 octets), largeurs (1/1000 de la taille). */
class TablePolice(val nomRessource: String, val objet: PDFObject, val octets: Int, val codes: Map<Char, Int>,
                  val largeurs: Map<Int, Float>, val largeurDefaut: Float, val nomBase: String) {
    fun code(c: Char): Int? = codes[c] ?: EQUIVALENTS[c]?.let { codes[it] }
    fun peutEcrire(t: String) = t.all { code(it) != null }
    fun manquantes(t: String) = t.filter { code(it) == null }.toSet()
    fun largeur(t: String, taille: Float): Float? {
        if (largeurs.isEmpty()) return null
        return t.sumOf { c -> (code(c)?.let { largeurs[it] ?: largeurDefaut } ?: largeurDefaut).toDouble() }.toFloat() * taille / 1000f
    }

    companion object {
        /** Espace insecable, apostrophe typographique, tiret : l'un remplace l'autre si la police n'a que l'un. */
        val EQUIVALENTS = mapOf(' ' to ' ', ' ' to ' ', '\'' to '’', '’' to '\'', '-' to '‐',
            '‐' to '-', '"' to '”', '“' to '"', '”' to '"')
    }
}

/** Un paragraphe (bloc) touche sur la page, et la police d'origine retrouvee (ou null : secours). */
data class Paragraphe(val page: Int, val lignes: List<LigneTexte>, val table: TablePolice?) {
    val texte: String get() = lignes.joinToString("\n") { it.texte }
}

/** Ce qui a ete fait, a dire a l'utilisateur. */
data class ResultatTexte(val ok: Boolean, val originale: Boolean, val police: String, val message: String = "")

object TexteModif {
    // ------------------------------------------------------------ lecture de la page
    /** Bloc de texte sous le point (en points de la page), lignes et police de chaque ligne. */
    fun paragraphe(page: PDFPage, n: Int, pt: Point): Paragraphe? {
        val st = page.toStructuredText("preserve-whitespace")
        val blocs = ArrayList<MutableList<LigneTexte>>()
        var bloc: MutableList<LigneTexte>? = null
        var ligne = StringBuilder()
        var x0 = 0f; var x1 = 0f; var base = 0f; var haut = 0f; var bas = 0f
        var taille = 0f; var argb = 0; var police: Font? = null
        var premier = true
        st.walk(object : StructuredTextWalker {
            override fun onImageBlock(bbox: Rect?, transform: Matrix?, image: Image?) {}
            override fun beginTextBlock(bbox: Rect?, flags: Int) { bloc = ArrayList<LigneTexte>().also { blocs += it } }
            override fun endTextBlock() { bloc = null }
            override fun beginLine(bbox: Rect?, wmode: Int, dir: Point?) {
                ligne = StringBuilder(); premier = true
                haut = bbox?.y0 ?: 0f; bas = bbox?.y1 ?: 0f; x1 = bbox?.x1 ?: 0f
            }
            override fun endLine() {
                val f = police
                if (ligne.isNotBlank() && f != null) bloc?.add(LigneTexte(ligne.toString().trimEnd(), x0, x1, base, haut, bas,
                    taille, argb, f.name ?: "", f.isBold, f.isItalic, f.isSerif, f.isMono))
            }
            override fun onChar(c: Int, origin: Point?, font: Font?, size: Float, q: Quad?, argb_: Int, flags: Int, bidi: Int) {
                if (premier && origin != null) {
                    x0 = origin.x; base = origin.y; taille = size; argb = argb_; police = font; premier = false
                }
                ligne.appendCodePoint(c)
            }
            override fun beginStruct(standard: String?, raw: String?, index: Int) {}
            override fun endStruct() {}
            override fun onVector(bbox: Rect?, info: StructuredTextWalker.VectorInfo?, argb_: Int) {}
        })
        st.destroy()
        val choisi = blocs.firstOrNull { b -> b.any { l -> pt.x >= l.x0 - 4 && pt.x <= l.x1 + 4 && pt.y >= l.haut - 2 && pt.y <= l.bas + 2 } }
            ?: return null
        // la ligne touchee et ses voisines de meme taille (un vrai paragraphe), pas tout le bloc (tableaux)
        val i = choisi.indexOfFirst { l -> pt.y >= l.haut - 2 && pt.y <= l.bas + 2 }.coerceAtLeast(0)
        var a = i; var b = i
        val t0 = choisi[i].taille
        while (a > 0 && kotlin.math.abs(choisi[a - 1].taille - t0) < 0.6f && choisi[a].haut - choisi[a - 1].bas < t0 * 0.9f) a--
        while (b < choisi.size - 1 && kotlin.math.abs(choisi[b + 1].taille - t0) < 0.6f && choisi[b + 1].haut - choisi[b].bas < t0 * 0.9f) b++
        val lignes = choisi.subList(a, b + 1).toList()
        return Paragraphe(n, lignes, trouverPolice(page, lignes))
    }

    // ------------------------------------------------------------ polices du PDF
    /** Polices de la page (et des formulaires XObject qu'elle dessine) : nom de ressource -> objet police. */
    private fun polices(page: PDFPage): List<Pair<String, PDFObject>> {
        val out = ArrayList<Pair<String, PDFObject>>()
        fun parcourir(res: PDFObject?, profondeur: Int) {
            if (res == null || res.isNull) return
            val fonts = res.get("Font")
            if (fonts != null && fonts.isDictionary) for (k in fonts) out += k.asName() to fonts.get(k)
            val xo = res.get("XObject")
            if (profondeur < 2 && xo != null && xo.isDictionary) for (k in xo) {
                val x = xo.get(k)
                if (x.get("Subtype").asName() == "Form") parcourir(x.get("Resources"), profondeur + 1)
            }
        }
        parcourir(page.getObject().getInheritable("Resources"), 0)
        return out
    }

    /** La police d'origine de ces lignes : celle qui sait ecrire leur texte, avec la bonne largeur. */
    private fun trouverPolice(page: PDFPage, lignes: List<LigneTexte>): TablePolice? {
        val l = lignes.first()
        val echant = lignes.joinToString("") { it.texte }
        var meilleur: TablePolice? = null
        var ecart = Float.MAX_VALUE
        for ((nom, obj) in polices(page)) {
            val t = try { table(nom, obj) } catch (_: Exception) { null } ?: continue
            if (!t.peutEcrire(echant)) continue
            val lw = t.largeur(l.texte, l.taille)
            var e = if (lw != null) kotlin.math.abs(lw - (l.x1 - l.x0)) else 50f
            val base = t.nomBase.substringAfter('+')
            val p = l.police
            if (p.isNotEmpty() && (base == p || (p.length >= 24 && base.startsWith(p)))) e -= 40f          // meme nom (tronque)
            else if (p.isNotEmpty() && base.isNotEmpty() && (base.startsWith(p) || p.startsWith(base))) e -= 15f   // meme famille
            else if (p.isNotEmpty() && base.isNotEmpty()) continue                // une autre police de la page : jamais
            if (e < ecart) { ecart = e; meilleur = t }
        }
        return meilleur
    }

    private fun hex(s: String): ByteArray = ByteArray(s.length / 2) { s.substring(2 * it, 2 * it + 2).toInt(16).toByte() }

    /** Table d'une police : codes de chaque lettre (ToUnicode, ou WinAnsi pour les polices standard), largeurs. */
    fun table(nom: String, f0: PDFObject): TablePolice? {
        val f = f0.resolve()
        val sous = f.get("Subtype").asName()
        var octets = 1
        val largeurs = HashMap<Int, Float>()
        var dw = 1000f
        if (sous == "Type0") {
            if (f.get("Encoding").asName() != "Identity-H") return null
            octets = 2
            val d = f.get("DescendantFonts").resolve().get(0).resolve()
            d.get("DW").takeIf { it.isNumber }?.let { dw = it.asFloat() }
            val w = d.get("W").resolve()
            var i = 0
            while (w.isArray && i < w.size()) {
                val c0 = w.get(i).asInteger()
                val suiv = w.get(i + 1).resolve()
                if (suiv.isArray) {
                    for (k in 0 until suiv.size()) largeurs[c0 + k] = suiv.get(k).asFloat()
                    i += 2
                } else {
                    val c1 = suiv.asInteger(); val v = w.get(i + 2).asFloat()
                    for (c in c0..c1) largeurs[c] = v
                    i += 3
                }
            }
        } else {
            val fc = f.get("FirstChar")
            val ws = f.get("Widths").resolve()
            if (fc.isNumber && ws.isArray) for (k in 0 until ws.size()) largeurs[fc.asInteger() + k] = ws.get(k).asFloat()
        }
        val codes = HashMap<Char, Int>()
        val tu = f.get("ToUnicode")
        if (tu.isStream) {
            val cm = String(tu.readStream(), Charsets.ISO_8859_1)
            Regex("beginbfchar(.*?)endbfchar", RegexOption.DOT_MATCHES_ALL).findAll(cm).forEach { b ->
                Regex("<([0-9A-Fa-f]+)>\\s*<([0-9A-Fa-f]*)>").findAll(b.groupValues[1]).forEach { m ->
                    val u = String(hex(m.groupValues[2]), Charsets.UTF_16BE)
                    if (u.length == 1) codes.putIfAbsent(u[0], m.groupValues[1].toInt(16))
                }
            }
            Regex("beginbfrange(.*?)endbfrange", RegexOption.DOT_MATCHES_ALL).findAll(cm).forEach { b ->
                Regex("<([0-9A-Fa-f]+)>\\s*<([0-9A-Fa-f]+)>\\s*(<[0-9A-Fa-f]*>|\\[[^\\]]*\\])").findAll(b.groupValues[1]).forEach { m ->
                    val lo = m.groupValues[1].toInt(16); val hi = m.groupValues[2].toInt(16)
                    val d = m.groupValues[3]
                    if (d.startsWith("<")) {
                        val base = d.substring(1, d.length - 1).toInt(16)
                        for (k in 0..(hi - lo).coerceAtMost(4096)) codes.putIfAbsent((base + k).toChar(), lo + k)
                    } else {
                        Regex("<([0-9A-Fa-f]*)>").findAll(d).forEachIndexed { k, x ->
                            val u = String(hex(x.groupValues[1]), Charsets.UTF_16BE)
                            if (u.length == 1) codes.putIfAbsent(u[0], lo + k)
                        }
                    }
                }
            }
        } else if (octets == 1) {
            val enc = f.get("Encoding")
            val diff = if (enc.isDictionary) enc.get("Differences").resolve() else null
            if (diff != null && diff.isArray) {
                // noms de glyphes (/A /eacute /zero...) : polices OCR-B des banques, Type3
                var code = -1
                for (k in 0 until diff.size()) {
                    val x = diff.get(k)
                    if (x.isNumber) code = x.asInteger()
                    else if (x.isName && code >= 0) { NomsGlyphes.lettre(x.asName())?.let { codes.putIfAbsent(it, code) }; code++ }
                }
                return if (codes.isEmpty()) null else TablePolice(nom, f0, 1, codes, largeurs, dw,
                    (try { f.get("BaseFont").asName() } catch (_: Exception) { null }) ?: "")
            }
            if (enc.isName && enc.asName() == "WinAnsiEncoding") {
                val cp = java.nio.charset.Charset.forName("windows-1252")
                for (c in 32..255) {
                    val s = String(byteArrayOf(c.toByte()), cp)
                    if (s.length == 1 && s[0] != '\uFFFD') codes.putIfAbsent(s[0], c)
                }
            } else {                                          // StandardEncoding : seulement l'ASCII commun
                for (c in 32..126) if (c != 0x27 && c != 0x60) codes.putIfAbsent(c.toChar(), c)
            }
        }
        if (codes.isEmpty()) return null
        val base = (try { f.get("BaseFont").asName() } catch (_: Exception) { null }) ?: ""
        return TablePolice(nom, f0, octets, codes, largeurs, dw, base)
    }

    // ------------------------------------------------------------ ecriture
    /** Police standard la plus proche (secours) : famille et style de la police d'origine. */
    fun policeSecours(l: LigneTexte, gras: Boolean, italique: Boolean): String {
        val fam = when { l.mono -> "Courier"; l.serif -> "Times"; else -> "Helvetica" }
        return when (fam) {
            "Times" -> when { gras && italique -> "Times-BoldItalic"; gras -> "Times-Bold"; italique -> "Times-Italic"; else -> "Times-Roman" }
            else -> fam + when { gras && italique -> "-BoldOblique"; gras -> "-Bold"; italique -> "-Oblique"; else -> "" }
        }
    }

    private fun nouveauNom(fonts: PDFObject, prefixe: String): String {
        var i = 1
        while (!fonts.get("$prefixe$i").isNull) i++
        return "$prefixe$i"
    }

    /**
     * Remplace les lignes du paragraphe par le nouveau texte (une ligne tapee = une ligne de la page, a la meme
     * place ; les lignes en plus continuent avec le meme interligne). Renvoie ce qui a ete fait.
     */
    fun reecrire(pdf: PDFDocument, page: PDFPage, par: Paragraphe, nouvelles: List<String>, taille: Float, argb: Int,
                 gras: Boolean, italique: Boolean, droite: Boolean): ResultatTexte {
        val l0 = par.lignes.first()
        val t = par.table
        val styleChange = gras != l0.gras || italique != l0.italique
        val texteTotal = nouvelles.joinToString("")
        val originale = t != null && !styleChange && t.peutEcrire(texteTotal)
        // 1. retirer seulement les lettres des anciennes lignes (fond, cadres, images gardes)
        val annot = page.createAnnotation(com.artifex.mupdf.fitz.PDFAnnotation.TYPE_REDACT)
        annot.setQuadPoints(par.lignes.map { l ->
            val y0 = l.haut + (l.bas - l.haut) * 0.15f; val y1 = l.bas - (l.bas - l.haut) * 0.15f
            Quad(l.x0, y0, l.x1, y0, l.x0, y1, l.x1, y1)
        }.toTypedArray())
        annot.update()
        page.applyRedactions(false, PDFPage.REDACT_IMAGE_NONE, PDFPage.REDACT_LINE_ART_NONE, PDFPage.REDACT_TEXT_REMOVE)
        // 2. la police : celle d'origine, ou la standard la plus proche
        val pobj = page.getObject()
        var res = pobj.get("Resources")
        if (res.isNull) { res = pobj.getInheritable("Resources"); if (res.isNull) res = pdf.newDictionary(); pobj.put("Resources", res) }
        var fonts = res.get("Font")
        if (fonts.isNull) { fonts = pdf.newDictionary(); res.put("Font", fonts) }
        val nomPolice: String
        val nomAffiche: String
        val coder: (String) -> String
        if (originale && t != null) {
            nomPolice = if (fonts.get(t.nomRessource).isNull || !fonts.get(t.nomRessource).resolve().equals(t.objet.resolve())) {
                nouveauNom(fonts, "PhilA").also { fonts.put(it, t.objet) }           // police venue d'un formulaire XObject
            } else t.nomRessource
            nomAffiche = t.nomBase.substringAfter('+').ifEmpty { l0.police }
            coder = { s -> s.map { c -> "%0${t.octets * 2}X".format(t.code(c)!!) }.joinToString("") }
        } else {
            val std = policeSecours(l0, gras, italique)
            val fobj = pdf.addSimpleFont(Font(std), Font.SIMPLE_ENCODING_LATIN)
            nomPolice = nouveauNom(fonts, "PhilB").also { fonts.put(it, fobj) }
            nomAffiche = std
            val cp = java.nio.charset.Charset.forName("windows-1252")
            coder = { s -> s.toByteArray(cp).joinToString("") { "%02X".format(it.toInt() and 255) } }
        }
        // 3. le texte, ligne par ligne, a l'emplacement des anciennes (repere de la page : y vers le haut)
        val inv = page.getTransform().invert()
        val pas = if (par.lignes.size > 1) (par.lignes.last().base - par.lignes.first().base) / (par.lignes.size - 1) else taille * 1.2f
        val r = ((argb shr 16) and 255) / 255f; val g = ((argb shr 8) and 255) / 255f; val b = (argb and 255) / 255f
        val flux = StringBuilder("q BT /$nomPolice ${f(taille)} Tf ${f(r)} ${f(g)} ${f(b)} rg\n")
        val fonteMesure = if (originale) null else try { Font(policeSecours(l0, gras, italique)) } catch (_: Exception) { null }
        nouvelles.forEachIndexed { i, s ->
            val ref = par.lignes.getOrNull(i)
            val base = ref?.base ?: (par.lignes.last().base + pas * (i - par.lignes.size + 1))
            var x = ref?.x0 ?: l0.x0
            if (droite) {
                val droiteRef = ref?.x1 ?: l0.x1
                val larg = if (originale) t?.largeur(s, taille) else fonteMesure?.let { fm ->
                    s.sumOf { c -> fm.advanceGlyph(fm.encodeCharacter(c.code), false).toDouble() }.toFloat() * taille
                }
                if (larg != null) x = droiteRef - larg
            }
            // repere de la page -> repere PDF : axe des x (a,b), axe des y vers le haut (-c,-d)
            val ox = x * inv.a + base * inv.c + inv.e
            val oy = x * inv.b + base * inv.d + inv.f
            flux.append("${f(inv.a)} ${f(inv.b)} ${f(-inv.c)} ${f(-inv.d)} ${f(ox)} ${f(oy)} Tm <${coder(s)}> Tj\n")
        }
        flux.append("ET Q\n")
        // contenu existant entre q ... Q (ses changements de repere ne touchent pas notre texte), puis le notre
        val contenu = pobj.get("Contents")
        val tableau = pdf.newArray()
        tableau.push(pdf.addStream("q\n"))
        if (contenu.isArray) for (k in 0 until contenu.size()) tableau.push(contenu.get(k)) else if (!contenu.isNull) tableau.push(contenu)
        tableau.push(pdf.addStream("Q\n"))
        tableau.push(pdf.addStream(flux.toString()))
        pobj.put("Contents", tableau)
        return ResultatTexte(true, originale, nomAffiche)
    }

    private fun f(v: Float) = String.format(java.util.Locale.US, "%.3f", v)
}

/** Noms de glyphes Adobe (encodage « Differences » : /A /eacute /zero...) -> lettre (genere depuis moteur/noms_glyphes.py). */
object NomsGlyphes {
    private val TABLE: Map<String, String> = mapOf(
        "space" to " ", "exclam" to "!", "quotedbl" to "\"", "numbersign" to "#", "dollar" to "\$", "percent" to "%",
        "ampersand" to "&", "quotesingle" to "'", "quoteright" to "\u2019", "quoteleft" to "\u2018", "parenleft" to "(", "parenright" to ")",
        "asterisk" to "*", "plus" to "+", "comma" to ",", "hyphen" to "-", "minus" to "\u2212", "period" to ".",
        "slash" to "/", "colon" to ":", "semicolon" to ";", "less" to "<", "equal" to "=", "greater" to ">",
        "question" to "?", "at" to "@", "bracketleft" to "[", "backslash" to "\\", "bracketright" to "]", "underscore" to "_",
        "grave" to "`", "braceleft" to "{", "bar" to "|", "braceright" to "}", "asciitilde" to "~", "asciicircum" to "^",
        "degree" to "\u00B0", "Euro" to "\u20ac", "euro" to "\u20ac", "sterling" to "\u00A3", "section" to "\u00A7", "paragraph" to "\u00B6",
        "guillemotleft" to "\u00AB", "guillemotright" to "\u00BB", "endash" to "\u2013", "emdash" to "\u2014", "bullet" to "\u2022", "ellipsis" to "\u2026",
        "quotedblleft" to "\u201c", "quotedblright" to "\u201d", "quotesinglbase" to "\u201a", "quotedblbase" to "\u201e", "ordmasculine" to "\u00BA", "ordfeminine" to "\u00AA",
        "copyright" to "\u00A9", "registered" to "\u00AE", "trademark" to "\u2122", "multiply" to "\u00D7", "divide" to "\u00F7", "nbspace" to "\u00A0",
        "uni00A0" to "\u00A0", "germandbls" to "\u00DF", "oe" to "\u0153", "OE" to "\u0152", "ae" to "\u00E6", "AE" to "\u00C6",
        "oslash" to "\u00F8", "Oslash" to "\u00D8", "exclamdown" to "\u00A1", "questiondown" to "\u00BF", "periodcentered" to "\u00B7", "twosuperior" to "\u00B2",
        "threesuperior" to "\u00B3", "onesuperior" to "\u00B9", "mu" to "\u00B5", "plusminus" to "\u00B1", "onehalf" to "\u00BD", "onequarter" to "\u00BC",
        "threequarters" to "\u00BE", "fi" to "\ufb01", "fl" to "\ufb02", "zero" to "0", "one" to "1", "two" to "2",
        "three" to "3", "four" to "4", "five" to "5", "six" to "6", "seven" to "7", "eight" to "8",
        "nine" to "9", "A" to "A", "B" to "B", "C" to "C", "D" to "D", "E" to "E",
        "F" to "F", "G" to "G", "H" to "H", "I" to "I", "J" to "J", "K" to "K",
        "L" to "L", "M" to "M", "N" to "N", "O" to "O", "P" to "P", "Q" to "Q",
        "R" to "R", "S" to "S", "T" to "T", "U" to "U", "V" to "V", "W" to "W",
        "X" to "X", "Y" to "Y", "Z" to "Z", "a" to "a", "b" to "b", "c" to "c",
        "d" to "d", "e" to "e", "f" to "f", "g" to "g", "h" to "h", "i" to "i",
        "j" to "j", "k" to "k", "l" to "l", "m" to "m", "n" to "n", "o" to "o",
        "p" to "p", "q" to "q", "r" to "r", "s" to "s", "t" to "t", "u" to "u",
        "v" to "v", "w" to "w", "x" to "x", "y" to "y", "z" to "z", "Aacute" to "\u00C1",
        "Agrave" to "\u00C0", "Acircumflex" to "\u00C2", "Adieresis" to "\u00C4", "Atilde" to "\u00C3", "Aring" to "\u00C5", "Acaron" to "\u01cd",
        "Eacute" to "\u00C9", "Egrave" to "\u00C8", "Ecircumflex" to "\u00CA", "Edieresis" to "\u00CB", "Etilde" to "\u1ebc", "Ecedilla" to "\u0228",
        "Ecaron" to "\u011a", "Iacute" to "\u00CD", "Igrave" to "\u00CC", "Icircumflex" to "\u00CE", "Idieresis" to "\u00CF", "Itilde" to "\u0128",
        "Icaron" to "\u01cf", "Oacute" to "\u00D3", "Ograve" to "\u00D2", "Ocircumflex" to "\u00D4", "Odieresis" to "\u00D6", "Otilde" to "\u00D5",
        "Ocaron" to "\u01d1", "Uacute" to "\u00DA", "Ugrave" to "\u00D9", "Ucircumflex" to "\u00DB", "Udieresis" to "\u00DC", "Utilde" to "\u0168",
        "Uring" to "\u016e", "Ucaron" to "\u01d3", "Yacute" to "\u00DD", "Ygrave" to "\u1ef2", "Ycircumflex" to "\u0176", "Ydieresis" to "\u0178",
        "Ytilde" to "\u1ef8", "Cacute" to "\u0106", "Ccircumflex" to "\u0108", "Ccedilla" to "\u00C7", "Ccaron" to "\u010c", "Nacute" to "\u0143",
        "Ngrave" to "\u01f8", "Ntilde" to "\u00D1", "Ncedilla" to "\u0145", "Ncaron" to "\u0147", "Sacute" to "\u015a", "Scircumflex" to "\u015c",
        "Scedilla" to "\u015e", "Scaron" to "\u0160", "Zacute" to "\u0179", "Zcircumflex" to "\u1e90", "Zcaron" to "\u017d", "aacute" to "\u00E1",
        "agrave" to "\u00E0", "acircumflex" to "\u00E2", "adieresis" to "\u00E4", "atilde" to "\u00E3", "aring" to "\u00E5", "acaron" to "\u01ce",
        "eacute" to "\u00E9", "egrave" to "\u00E8", "ecircumflex" to "\u00EA", "edieresis" to "\u00EB", "etilde" to "\u1ebd", "ecedilla" to "\u0229",
        "ecaron" to "\u011b", "iacute" to "\u00ED", "igrave" to "\u00EC", "icircumflex" to "\u00EE", "idieresis" to "\u00EF", "itilde" to "\u0129",
        "icaron" to "\u01d0", "oacute" to "\u00F3", "ograve" to "\u00F2", "ocircumflex" to "\u00F4", "odieresis" to "\u00F6", "otilde" to "\u00F5",
        "ocaron" to "\u01d2", "uacute" to "\u00FA", "ugrave" to "\u00F9", "ucircumflex" to "\u00FB", "udieresis" to "\u00FC", "utilde" to "\u0169",
        "uring" to "\u016f", "ucaron" to "\u01d4", "yacute" to "\u00FD", "ygrave" to "\u1ef3", "ycircumflex" to "\u0177", "ydieresis" to "\u00FF",
        "ytilde" to "\u1ef9", "yring" to "\u1e99", "cacute" to "\u0107", "ccircumflex" to "\u0109", "ccedilla" to "\u00E7", "ccaron" to "\u010d",
        "nacute" to "\u0144", "ngrave" to "\u01f9", "ntilde" to "\u00F1", "ncedilla" to "\u0146", "ncaron" to "\u0148", "sacute" to "\u015b",
        "scircumflex" to "\u015d", "scedilla" to "\u015f", "scaron" to "\u0161", "zacute" to "\u017a", "zcircumflex" to "\u1e91", "zcaron" to "\u017e"
    )

    fun lettre(nom: String): Char? {
        TABLE[nom]?.let { return it[0] }
        for (p in listOf("uni", "u")) if (nom.startsWith(p) && nom.length in (p.length + 4)..(p.length + 5))
            return nom.substring(p.length).toIntOrNull(16)?.toChar()
        return null
    }
}
