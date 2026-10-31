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
            if (l.police.isNotEmpty() && (base.startsWith(l.police) || l.police.startsWith(base))) e -= 30f   // meme nom
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
            if (enc.isDictionary && enc.get("Differences").isArray) return null       // codes personnalises sans table
            val cp = java.nio.charset.Charset.forName("windows-1252")
            for (c in 32..255) {
                val s = String(byteArrayOf(c.toByte()), cp)
                if (s.length == 1 && s[0] != '�') codes.putIfAbsent(s[0], c)
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
