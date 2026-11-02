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
                      val serif: Boolean, val mono: Boolean, val polices: Set<String> = emptySet(),
                      /** police de chaque lettre du texte (gras et normal melanges dans une ligne) */
                      val fontes: List<String> = emptyList(),
                      /** bord gauche de la ligne, et sens d'ecriture (1, 0) ; (-1, 0) : texte a l'envers (livret plie) */
                      val gauche: Float = x0, val dx: Float = 1f, val dy: Float = 0f)

/** Codes d'une police du PDF : lettre -> code (1 ou 2 octets), largeurs (1/1000 de la taille). */
class TablePolice(val nomRessource: String, val objet: PDFObject, val octets: Int, val codes: Map<Char, Int>,
                  val largeurs: Map<Int, Float>, val largeurDefaut: Float, val nomBase: String) {
    /** Polices Type3 decoupees (une police par paquet de lettres, meme dessin) : les autres morceaux du jeu. */
    var autres: List<TablePolice> = emptyList()
    private fun codeSeul(c: Char): Int? = codes[c] ?: EQUIVALENTS[c]?.let { codes[it] }
    /** Le morceau du jeu qui sait ecrire cette lettre. */
    fun source(c: Char): TablePolice? = if (codeSeul(c) != null) this else autres.firstOrNull { it.codeSeul(c) != null }
    fun code(c: Char): Int? = source(c)?.codeSeul(c)
    fun peutEcrire(t: String) = t.all { code(it) != null }
    fun manquantes(t: String) = t.filter { code(it) == null }.toSet()
    fun largeur(t: String, taille: Float): Float? {
        if (largeurs.isEmpty()) return null
        return t.sumOf { c ->
            val s = source(c)
            (s?.codeSeul(c)?.let { s.largeurs[it] ?: s.largeurDefaut } ?: largeurDefaut).toDouble()
        }.toFloat() * taille / 1000f
    }

    companion object {
        /** Espace insecable, apostrophe typographique, tiret : l'un remplace l'autre si la police n'a que l'un. */
        val EQUIVALENTS = mapOf(' ' to ' ', ' ' to ' ', '\'' to '’', '’' to '\'', '-' to '‐',
            '‐' to '-', '"' to '”', '“' to '"', '”' to '"')
    }
}

/** Un paragraphe (bloc) touche sur la page, et la police d'origine retrouvee (ou null : secours). */
data class Paragraphe(val page: Int, val lignes: List<LigneTexte>, val table: TablePolice?,
                      /** table de chaque police du paragraphe (par nom), pour garder gras et normal la ou ils etaient */
                      val tables: Map<String, TablePolice> = emptyMap()) {
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
        var x0 = 0f; var x1 = 0f; var base = 0f; var haut = 0f; var bas = 0f; var gauche = 0f; var sens = Point(1f, 0f)
        var taille = 0f; var argb = 0; var police: Font? = null
        var premier = true
        var noms = HashSet<String>()
        var fontes = ArrayList<String>()
        st.walk(object : StructuredTextWalker {
            override fun onImageBlock(bbox: Rect?, transform: Matrix?, image: Image?) {}
            override fun beginTextBlock(bbox: Rect?, flags: Int) { bloc = ArrayList<LigneTexte>().also { blocs += it } }
            override fun endTextBlock() { bloc = null }
            override fun beginLine(bbox: Rect?, wmode: Int, dir: Point?) {
                ligne = StringBuilder(); premier = true; noms = HashSet(); fontes = ArrayList()
                haut = bbox?.y0 ?: 0f; bas = bbox?.y1 ?: 0f; x1 = bbox?.x1 ?: 0f; gauche = bbox?.x0 ?: 0f; sens = dir ?: Point(1f, 0f)
            }
            override fun endLine() {
                val f = police
                val t = ligne.toString().trimEnd()
                if (ligne.isNotBlank() && f != null) bloc?.add(LigneTexte(t, x0, x1, base, haut, bas,
                    taille, argb, f.name ?: "", f.isBold, f.isItalic, f.isSerif, f.isMono, noms, fontes.take(t.length), gauche, sens.x, sens.y))
            }
            override fun onChar(c: Int, origin: Point?, font: Font?, size: Float, q: Quad?, argb_: Int, flags: Int, bidi: Int) {
                if (premier && origin != null) {
                    x0 = origin.x; base = origin.y; taille = size; argb = argb_; police = font; premier = false
                }
                val avant = ligne.length
                ligne.appendCodePoint(c)
                font?.name?.let { noms.add(it) }
                repeat(ligne.length - avant) { fontes += font?.name ?: "" }
            }
            override fun beginStruct(standard: String?, raw: String?, index: Int) {}
            override fun endStruct() {}
            override fun onVector(bbox: Rect?, info: StructuredTextWalker.VectorInfo?, argb_: Int) {}
        })
        st.destroy()
        val choisi = blocs.firstOrNull { b -> b.any { l -> pt.x >= l.gauche - 4 && pt.x <= l.x1 + 4 && pt.y >= l.haut - 2 && pt.y <= l.bas + 2 } }
            ?: return null
        // la ligne touchee et ses voisines de meme taille (un vrai paragraphe), pas tout le bloc (tableaux)
        val i = choisi.indexOfFirst { l -> pt.y >= l.haut - 2 && pt.y <= l.bas + 2 }.coerceAtLeast(0)
        var a = i; var b = i
        val t0 = choisi[i].taille
        while (a > 0 && kotlin.math.abs(choisi[a - 1].taille - t0) < 0.6f && choisi[a].haut - choisi[a - 1].bas < t0 * 0.9f) a--
        while (b < choisi.size - 1 && kotlin.math.abs(choisi[b + 1].taille - t0) < 0.6f && choisi[b + 1].haut - choisi[b].bas < t0 * 0.9f) b++
        val lignes = choisi.subList(a, b + 1).toList()
        // plusieurs polices dans le paragraphe (« Mode de paiement : » en gras, la suite normale) : la table de chacune
        val nomsPolices = lignes.flatMap { it.fontes }.filter { it.isNotEmpty() }.toSet()
        val tables = HashMap<String, TablePolice>()
        if (nomsPolices.size > 1 && nomsPolices.none { TYPE3.containsMatchIn(it) }) {
            val toutes = polices(page).mapNotNull { (nom, obj) -> try { table(nom, obj) } catch (_: Exception) { null } }
            for (nf in nomsPolices) {
                val court = nf.substringAfter('+')
                toutes.firstOrNull { t -> t.nomBase.substringAfter('+').let { b -> b == court || (court.length >= 24 && b.startsWith(court)) } }
                    ?.let { tables[nf] = it }
            }
        }
        return Paragraphe(n, lignes, trouverPolice(page, lignes, familles(blocs.flatten())), tables)
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

    private val TYPE3 = Regex("""Type3 \((\d+) 0 R\)""")

    /** Polices Type3 de la page regroupees par famille : celles qui se melent dans une meme ligne (un logiciel
     *  decoupe une police en morceaux de quelques lettres ; le gras forme une autre famille). numero -> famille. */
    private fun familles(lignes: List<LigneTexte>): Map<Int, Set<Int>> {
        val parent = HashMap<Int, Int>()
        fun racine(x: Int): Int { var r = x; while (parent[r] != null && parent[r] != r) r = parent[r]!!; return r }
        for (l in lignes) {
            val nums = l.polices.mapNotNull { TYPE3.find(it)?.groupValues?.get(1)?.toIntOrNull() }
            nums.forEach { parent.putIfAbsent(it, it) }
            for (k in 1 until nums.size) { val a = racine(nums[0]); val b = racine(nums[k]); if (a != b) parent[b] = a }
        }
        val groupes = parent.keys.groupBy { racine(it) }.mapValues { it.value.toSet() }
        return parent.keys.associateWith { groupes[racine(it)] ?: setOf(it) }
    }

    /** Jeu de morceaux Type3 de la meme famille que ces lignes (null si ce ne sont pas des polices Type3). */
    private fun jeuType3(page: PDFPage, lignes: List<LigneTexte>, fam: Map<Int, Set<Int>>): TablePolice? {
        val nums = lignes.flatMap { l -> l.polices.mapNotNull { TYPE3.find(it)?.groupValues?.get(1)?.toIntOrNull() } }
        if (nums.isEmpty()) return null
        val premier = TYPE3.find(lignes.first().police)?.groupValues?.get(1)?.toIntOrNull() ?: nums.first()
        val voulus = LinkedHashSet<Int>().apply { add(premier); addAll(nums); nums.forEach { addAll(fam[it] ?: emptySet()) } }
        val tables = HashMap<Int, TablePolice>()
        for ((nom, obj) in polices(page)) {
            val num = try { if (obj.isIndirect) obj.asIndirect() else -1 } catch (_: Exception) { -1 }
            if (num in voulus && num !in tables) (try { table(nom, obj) } catch (_: Exception) { null })?.let { tables[num] = it }
        }
        val ordre = voulus.mapNotNull { tables[it] }
        if (ordre.isEmpty()) return null
        return ordre.first().also { it.autres = ordre.drop(1) }
    }

    /** La police d'origine de ces lignes : celle qui sait ecrire leur texte, avec la bonne largeur. */
    private fun trouverPolice(page: PDFPage, lignes: List<LigneTexte>, fam: Map<Int, Set<Int>> = emptyMap()): TablePolice? {
        jeuType3(page, lignes, fam)?.let { j -> if (j.peutEcrire(lignes.joinToString("") { it.texte }.filter { !it.isWhitespace() })) return j }
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
            val p = l.police.substringAfter('+')                                 // nom sans prefixe de sous-ensemble
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
        val sans = l.police.contains("Sans", ignoreCase = true) || l.police.contains("Arial", ignoreCase = true) ||
            l.police.contains("Helvetica", ignoreCase = true)
        val fam = when { l.mono -> "Courier"; l.serif && !sans -> "Times"; else -> "Helvetica" }
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
        // page scannee dont le texte a ete reconnu (OCR) : les lettres visibles sont dans l'image, on efface aussi ses
        // pixels sous la ligne (sinon l'ancien texte resterait visible sous le nouveau)
        val pageOcr = try { page.getObject().get("PhilPDF_OCR").let { !it.isNull && it.asBoolean() } } catch (_: Exception) { false }
        // texte reconnu : police « PhilOCR » (ou Helvetica sur une page reconnue par les versions 1.8.0 a 1.8.9) ;
        // le vrai texte d'une page qui a aussi des images n'efface pas l'image dessous
        val ocr = par.lignes.any { l -> (l.polices + l.police).any { it.contains("PhilOCR") } } ||
            (pageOcr && par.lignes.all { l -> l.police.substringAfter('+').startsWith("Helvetica") })
        val annot = page.createAnnotation(com.artifex.mupdf.fitz.PDFAnnotation.TYPE_REDACT)
        annot.setQuadPoints(par.lignes.map { l ->
            val marge = if (ocr) -(l.bas - l.haut) * 0.08f else (l.bas - l.haut) * 0.15f
            val y0 = l.haut + marge; val y1 = l.bas - marge
            Quad(l.gauche, y0, l.x1, y0, l.gauche, y1, l.x1, y1)
        }.toTypedArray())
        annot.update()
        page.applyRedactions(false, if (ocr) PDFPage.REDACT_IMAGE_PIXELS else PDFPage.REDACT_IMAGE_NONE,
            PDFPage.REDACT_LINE_ART_NONE, PDFPage.REDACT_TEXT_REMOVE)
        // 2. la police : celle d'origine, ou la standard la plus proche
        val pobj = page.getObject()
        var res = pobj.get("Resources")
        if (res.isNull) { res = pobj.getInheritable("Resources"); if (res.isNull) res = pdf.newDictionary(); pobj.put("Resources", res) }
        var fonts = res.get("Font")
        if (fonts.isNull) { fonts = pdf.newDictionary(); res.put("Font", fonts) }
        // gras et normal melanges dans le paragraphe, style non change par l'utilisateur : chaque lettre garde la police
        // qu'elle avait (le texte tape prend celle du texte qu'il remplace)
        val nomsFontes = par.lignes.flatMap { it.fontes }.filter { it.isNotEmpty() }.toSet()
        if (!styleChange && nomsFontes.size > 1 && par.tables.isNotEmpty())
            return ecrireMixte(pdf, page, par, nouvelles, taille, argb, droite, fonts)
        val nomPolice: String
        val nomAffiche: String
        val coder: (String) -> String
        if (originale && t != null) {
            // le caviardage peut reecrire les ressources : chaque police (ou morceau Type3) est rattachee sous un nom sur
            val noms = HashMap<TablePolice, String>()
            fun nomDe(x: TablePolice): String = noms.getOrPut(x) {
                if (fonts.get(x.nomRessource).isNull || !fonts.get(x.nomRessource).resolve().equals(x.objet.resolve()))
                    nouveauNom(fonts, "PhilA").also { fonts.put(it, x.objet) }
                else x.nomRessource
            }
            nomPolice = nomDe(t)
            nomAffiche = t.nomBase.substringAfter('+').ifEmpty { if (l0.police.startsWith("Type3")) "Type3" else l0.police }
            coder = { s ->
                // une suite de lettres du meme morceau = un Tj ; changement de morceau = Tf puis Tj
                val sb = StringBuilder()
                var cour: TablePolice? = null
                for (c in s) {
                    val src = t.source(c)!!
                    if (src !== cour) {
                        if (cour != null) sb.append("> Tj ")
                        sb.append("/${nomDe(src)} ${f(taille)} Tf <")
                        cour = src
                    }
                    sb.append("%0${src.octets * 2}X".format(t.code(c)!!))
                }
                if (cour != null) sb.append(">") else sb.append("/$nomPolice ${f(taille)} Tf <>")
                sb.toString()
            }
        } else {
            val std = policeSecours(l0, gras, italique)
            val fobj = pdf.addSimpleFont(Font(std), Font.SIMPLE_ENCODING_LATIN)
            nomPolice = nouveauNom(fonts, "PhilB").also { fonts.put(it, fobj) }
            nomAffiche = std
            val cp = java.nio.charset.Charset.forName("windows-1252")
            coder = { s -> "<" + s.toByteArray(cp).joinToString("") { "%02X".format(it.toInt() and 255) } + ">" }
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
            flux.append("${axes(inv, ref ?: l0)} ${f(ox)} ${f(oy)} Tm ${coder(s)} Tj\n")
        }
        flux.append("ET Q\n")
        // contenu existant entre q ... Q (ses changements de repere ne touchent pas notre texte), puis le notre
        val contenu = pobj.get("Contents")
        val tableau = pdf.newArray()
        tableau.ajouter(pdf.addStream("q\n"))
        // contenu d'origine (un flux ou une liste de flux) ; debris laisses par une version precedente : ecartes
        if (contenu.isArray) { for (k in 0 until contenu.size()) contenu.get(k).takeIf { it.isIndirect }?.let { tableau.ajouter(it) } }
        else if (!contenu.isNull) tableau.ajouter(contenu)
        tableau.ajouter(pdf.addStream("Q\n"))
        tableau.ajouter(pdf.addStream(flux.toString()))
        pobj.put("Contents", tableau)
        return ResultatTexte(true, originale, nomAffiche)
    }

    /** Police de chaque lettre de la nouvelle ligne, d'apres l'ancienne : debut et fin inchanges gardent la leur ; le
     *  texte change prend la police du texte qu'il remplace (ou de la lettre d'avant, pour un ajout). */
    private fun styler(ancien: String, fa: List<String>, nouveau: String, defaut: String): List<String> {
        if (fa.size != ancien.length || fa.isEmpty()) return List(nouveau.length) { fa.lastOrNull() ?: defaut }
        var p = 0
        while (p < ancien.length && p < nouveau.length && ancien[p] == nouveau[p]) p++
        var q = 0
        while (q < ancien.length - p && q < nouveau.length - p && ancien[ancien.length - 1 - q] == nouveau[nouveau.length - 1 - q]) q++
        val milieu = if (p < ancien.length - q) fa[p] else if (p > 0) fa[p - 1] else fa[0]
        return List(nouveau.length) { i ->
            when {
                i < p -> fa[i]
                i >= nouveau.length - q -> fa[ancien.length - (nouveau.length - i)]
                else -> milieu
            }
        }
    }

    private fun ecrireMixte(pdf: PDFDocument, page: PDFPage, par: Paragraphe, nouvelles: List<String>, taille: Float, argb: Int,
                            droite: Boolean, fonts: PDFObject): ResultatTexte {
        val l0 = par.lignes.first()
        val noms = HashMap<PDFObject, String>()
        // la police d'origine, rattachee aux ressources sous un nom sur (le caviardage peut les avoir reecrites)
        fun nomDe(t: TablePolice): String = noms.getOrPut(t.objet) {
            if (fonts.get(t.nomRessource).isNull || !fonts.get(t.nomRessource).resolve().equals(t.objet.resolve()))
                nouveauNom(fonts, "PhilA").also { fonts.put(it, t.objet) }
            else t.nomRessource
        }
        val secours = HashMap<String, String>()
        val cp = java.nio.charset.Charset.forName("windows-1252")
        var secoursUtilise = false
        // police standard proche, pour une lettre absente de la police d'origine (sous-ensemble)
        fun nomSecours(fonte: String): String {
            val gras = fonte.contains("Bold", true) || fonte.contains("Black", true) || fonte.contains("Heavy", true)
            val ital = fonte.contains("Italic", true) || fonte.contains("Oblique", true)
            val std = policeSecours(l0.copy(police = fonte), gras, ital)
            return secours.getOrPut(std) {
                nouveauNom(fonts, "PhilB").also { fonts.put(it, pdf.addSimpleFont(Font(std), Font.SIMPLE_ENCODING_LATIN)) }
            }
        }
        fun morceau(texte: String, fonte: String): Pair<String, Float> {
            val t = par.tables[fonte]
            return if (t != null && t.peutEcrire(texte)) {
                val sb = StringBuilder(); var cour: TablePolice? = null
                for (c in texte) {
                    val src = t.source(c)!!
                    if (src !== cour) { if (cour != null) sb.append("> Tj "); sb.append("/${nomDe(src)} ${f(taille)} Tf <"); cour = src }
                    sb.append("%0${src.octets * 2}X".format(t.code(c)!!))
                }
                sb.append("> Tj ").toString() to (t.largeur(texte, taille) ?: 0f)
            } else {
                secoursUtilise = true
                val nom = nomSecours(fonte)
                val fm = try { Font(policeSecours(l0.copy(police = fonte), fonte.contains("Bold", true), fonte.contains("Italic", true))) } catch (_: Exception) { null }
                val larg = fm?.let { m -> texte.sumOf { c -> m.advanceGlyph(m.encodeCharacter(c.code), false).toDouble() }.toFloat() * taille } ?: 0f
                "/$nom ${f(taille)} Tf <" + texte.toByteArray(cp).joinToString("") { "%02X".format(it.toInt() and 255) } + "> Tj " to larg
            }
        }
        val inv = page.getTransform().invert()
        val pas = if (par.lignes.size > 1) (par.lignes.last().base - par.lignes.first().base) / (par.lignes.size - 1) else taille * 1.2f
        val r = ((argb shr 16) and 255) / 255f; val g = ((argb shr 8) and 255) / 255f; val b = (argb and 255) / 255f
        val flux = StringBuilder("q BT ${f(r)} ${f(g)} ${f(b)} rg\n")
        val derniere = par.lignes.last().fontes.lastOrNull { it.isNotEmpty() } ?: l0.police
        nouvelles.forEachIndexed { i, s ->
            val ref = par.lignes.getOrNull(i)
            val fs = if (ref != null) styler(ref.texte, ref.fontes, s, derniere) else List(s.length) { derniere }
            // morceaux de meme police
            val morceaux = ArrayList<Pair<String, Float>>()
            var debut = 0
            for (k in 1..s.length) if (k == s.length || fs[k] != fs[debut]) { morceaux += morceau(s.substring(debut, k), fs[debut]); debut = k }
            val base = ref?.base ?: (par.lignes.last().base + pas * (i - par.lignes.size + 1))
            var x = ref?.x0 ?: l0.x0
            if (droite) x = (ref?.x1 ?: l0.x1) - morceaux.sumOf { it.second.toDouble() }.toFloat()
            val ox = x * inv.a + base * inv.c + inv.e
            val oy = x * inv.b + base * inv.d + inv.f
            flux.append("${axes(inv, ref ?: l0)} ${f(ox)} ${f(oy)} Tm ")
            morceaux.forEach { flux.append(it.first) }
            flux.append("\n")
        }
        flux.append("ET Q\n")
        val pobj = page.getObject()
        val contenu = pobj.get("Contents")
        val tableau = pdf.newArray()
        tableau.ajouter(pdf.addStream("q\n"))
        // contenu d'origine (un flux ou une liste de flux) ; debris laisses par une version precedente : ecartes
        if (contenu.isArray) { for (k in 0 until contenu.size()) contenu.get(k).takeIf { it.isIndirect }?.let { tableau.ajouter(it) } }
        else if (!contenu.isNull) tableau.ajouter(contenu)
        tableau.ajouter(pdf.addStream("Q\n"))
        tableau.ajouter(pdf.addStream(flux.toString()))
        pobj.put("Contents", tableau)
        val affiche = par.tables.values.map { it.nomBase.substringAfter('+') }.distinct().joinToString(" + ")
        return ResultatTexte(true, !secoursUtilise, affiche)
    }

    /** Axes du texte (debut de Tm) dans le sens de la ligne d'origine : a l'endroit, ou a l'envers (livret plie). */
    private fun axes(inv: Matrix, l: LigneTexte): String {
        val n = kotlin.math.sqrt(l.dx * l.dx + l.dy * l.dy).takeIf { it > 0.01f } ?: 1f
        val dx = l.dx / n; val dy = l.dy / n
        val ux = dy; val uy = -dx                         // vers le haut des lettres (repere de la page, y vers le bas)
        return "${f(dx * inv.a + dy * inv.c)} ${f(dx * inv.b + dy * inv.d)} ${f(ux * inv.a + uy * inv.c)} ${f(ux * inv.b + uy * inv.d)}"
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
