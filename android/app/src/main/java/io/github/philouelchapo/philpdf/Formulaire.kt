package io.github.philouelchapo.philpdf

import com.artifex.mupdf.fitz.ColorSpace
import com.artifex.mupdf.fitz.Cookie
import com.artifex.mupdf.fitz.DefaultColorSpaces
import com.artifex.mupdf.fitz.Device
import com.artifex.mupdf.fitz.Image
import com.artifex.mupdf.fitz.Matrix
import com.artifex.mupdf.fitz.PDFDocument
import com.artifex.mupdf.fitz.PDFObject
import com.artifex.mupdf.fitz.PDFPage
import com.artifex.mupdf.fitz.Path
import com.artifex.mupdf.fitz.PathWalker
import com.artifex.mupdf.fitz.Point
import com.artifex.mupdf.fitz.Quad
import com.artifex.mupdf.fitz.Rect
import com.artifex.mupdf.fitz.Shade
import com.artifex.mupdf.fitz.StrokeState
import com.artifex.mupdf.fitz.StructuredTextWalker
import com.artifex.mupdf.fitz.Text

/** Un champ trouve (ou dessine) : genre « texte » ou « case », rectangle en points de la page (y vers le bas). */
data class ChampDetecte(val page: Int, val genre: String, val rect: Rect, var nom: String, val lignes: Boolean = false,
                        var garder: Boolean = true)

/** Appareil qui ne dessine rien : base des appareils de mesure (images, traits). */
open class DeviceMuet : Device() {
    override fun close() {}
    override fun fillPath(path: Path?, evenOdd: Boolean, ctm: Matrix?, cs: ColorSpace?, color: FloatArray?, alpha: Float, cp: Int) {}
    override fun strokePath(path: Path?, stroke: StrokeState?, ctm: Matrix?, cs: ColorSpace?, color: FloatArray?, alpha: Float, cp: Int) {}
    override fun clipPath(path: Path?, evenOdd: Boolean, ctm: Matrix?) {}
    override fun clipStrokePath(path: Path?, stroke: StrokeState?, ctm: Matrix?) {}
    override fun fillText(text: Text?, ctm: Matrix?, cs: ColorSpace?, color: FloatArray?, alpha: Float, cp: Int) {}
    override fun strokeText(text: Text?, stroke: StrokeState?, ctm: Matrix?, cs: ColorSpace?, color: FloatArray?, alpha: Float, cp: Int) {}
    override fun clipText(text: Text?, ctm: Matrix?) {}
    override fun clipStrokeText(text: Text?, stroke: StrokeState?, ctm: Matrix?) {}
    override fun ignoreText(text: Text?, ctm: Matrix?) {}
    override fun fillShade(shd: Shade?, ctm: Matrix?, alpha: Float, cp: Int) {}
    override fun fillImage(img: Image?, ctm: Matrix?, alpha: Float, cp: Int) {}
    override fun fillImageMask(img: Image?, ctm: Matrix?, cs: ColorSpace?, color: FloatArray?, alpha: Float, cp: Int) {}
    override fun clipImageMask(img: Image?, ctm: Matrix?) {}
    override fun popClip() {}
    override fun beginMask(area: Rect?, luminosity: Boolean, cs: ColorSpace?, bc: FloatArray?, cp: Int) {}
    override fun endMask() {}
    override fun beginGroup(area: Rect?, cs: ColorSpace?, isolated: Boolean, knockout: Boolean, blendmode: Int, alpha: Float) {}
    override fun endGroup() {}
    override fun beginTile(area: Rect?, view: Rect?, xstep: Float, ystep: Float, ctm: Matrix?, id: Int, doc_id: Int): Int = 0
    override fun endTile() {}
    override fun renderFlags(set: Int, clear: Int) {}
    override fun setDefaultColorSpaces(dcs: DefaultColorSpaces?) {}
    override fun beginLayer(name: String?) {}
    override fun endLayer() {}
    override fun beginStructure(standard: Int, raw: String?, idx: Int) {}
    override fun endStructure() {}
    override fun beginMetatext(meta: Int, text: String?) {}
    override fun endMetatext() {}
}

/**
 * Creer un formulaire a partir d'un document (comme PhilPDF Windows et « Preparer un formulaire » d'Acrobat) :
 * pointilles et soulignes tapes (_____ ......), traits dessines sous un blanc, petits carres et caracteres case
 * -> cases a cocher, cadres vides -> zones de texte. Chaque champ prend le nom du libelle le plus proche.
 */
object Formulaire {
    private const val CASES = "☐□❑❒▢◻"

    private class Mot(val texte: String, val r: Rect)

    private fun mots(page: PDFPage): List<Mot> {
        val out = ArrayList<Mot>()
        val st = page.toStructuredText("preserve-whitespace")
        var t = StringBuilder()
        var r: Rect? = null
        fun finir() { val rr = r; if (t.isNotBlank() && rr != null) out += Mot(t.toString(), rr); t = StringBuilder(); r = null }
        st.walk(object : StructuredTextWalker {
            override fun onImageBlock(bbox: Rect?, transform: Matrix?, image: Image?) {}
            override fun beginTextBlock(bbox: Rect?, flags: Int) {}
            override fun endTextBlock() {}
            override fun beginLine(bbox: Rect?, wmode: Int, dir: Point?) { finir() }
            override fun endLine() { finir() }
            override fun onChar(c: Int, origin: Point?, font: com.artifex.mupdf.fitz.Font?, size: Float, q: Quad?, argb: Int, flags: Int, bidi: Int) {
                if (Character.isWhitespace(c)) { finir(); return }
                t.appendCodePoint(c)
                val qr = q?.toRect() ?: return
                r = r?.let { Rect(minOf(it.x0, qr.x0), minOf(it.y0, qr.y0), maxOf(it.x1, qr.x1), maxOf(it.y1, qr.y1)) } ?: Rect(qr)
            }
            override fun beginStruct(standard: String?, raw: String?, index: Int) {}
            override fun endStruct() {}
            override fun onVector(bbox: Rect?, info: StructuredTextWalker.VectorInfo?, argb: Int) {}
        })
        st.destroy()
        return out
    }

    /** Traits et rectangles dessines sur la page (en points de la page). */
    private class Traits : DeviceMuet() {
        val lignes = ArrayList<Pair<Point, Point>>()
        val rects = ArrayList<Rect>()
        private fun lire(path: Path?, ctm: Matrix?) {
            if (path == null || ctm == null) return
            val pts = ArrayList<Point>()
            fun fin() {
                if (pts.size == 2) lignes += pts[0] to pts[1]
                else if (pts.size in 4..5) {
                    val xs = pts.map { it.x }; val ys = pts.map { it.y }
                    val droit = pts.zipWithNext().all { (a, b) -> kotlin.math.abs(a.x - b.x) < 0.8f || kotlin.math.abs(a.y - b.y) < 0.8f }
                    if (droit) rects += Rect(xs.min(), ys.min(), xs.max(), ys.max())
                }
                pts.clear()
            }
            path.walk(object : PathWalker {
                override fun moveTo(x: Float, y: Float) { fin(); pts += Point(x, y).transform(ctm) }
                override fun lineTo(x: Float, y: Float) { pts += Point(x, y).transform(ctm) }
                override fun curveTo(cx1: Float, cy1: Float, cx2: Float, cy2: Float, ex: Float, ey: Float) { pts.clear(); pts += Point(ex, ey).transform(ctm); pts += Point(ex, ey).transform(ctm); pts += Point(ex, ey).transform(ctm) }
                override fun closePath() { if (pts.isNotEmpty()) pts += pts[0] }
            })
            fin()
        }
        override fun fillPath(path: Path?, evenOdd: Boolean, ctm: Matrix?, cs: ColorSpace?, color: FloatArray?, alpha: Float, cp: Int) = lire(path, ctm)
        override fun strokePath(path: Path?, stroke: StrokeState?, ctm: Matrix?, cs: ColorSpace?, color: FloatArray?, alpha: Float, cp: Int) = lire(path, ctm)
    }

    private fun aire(r: Rect) = maxOf(0f, r.x1 - r.x0) * maxOf(0f, r.y1 - r.y0)
    private fun inter(a: Rect, b: Rect) = Rect(maxOf(a.x0, b.x0), maxOf(a.y0, b.y0), minOf(a.x1, b.x1), minOf(a.y1, b.y1))
    private fun touche(a: Rect, b: Rect) = a.x0 < b.x1 && b.x0 < a.x1 && a.y0 < b.y1 && b.y0 < a.y1

    private fun libelle(r: Rect, mots: List<Mot>, case: Boolean): String {
        val my = (r.y0 + r.y1) / 2
        val h = r.y1 - r.y0
        if (case) {
            val droite = mots.filter { kotlin.math.abs((it.r.y0 + it.r.y1) / 2 - my) < maxOf(6f, h) && it.r.x0 >= r.x1 - 1 && it.r.x0 - r.x1 < 200 }
                .sortedBy { it.r.x0 }
            val sel = ArrayList<Mot>()
            for (w in droite) { if (sel.isNotEmpty() && w.r.x0 - sel.last().r.x1 > 12) break; sel += w }
            if (sel.isNotEmpty()) return sel.take(6).joinToString(" ") { it.texte }.trim(' ', ':').take(60)
        }
        val gauche = mots.filter { kotlin.math.abs((it.r.y0 + it.r.y1) / 2 - my) < maxOf(6f, h * 0.6f) && it.r.x1 <= r.x0 + 2 &&
            r.x0 - it.r.x1 < 200 && !Regex("[_.…]+").matches(it.texte) }.sortedBy { it.r.x0 }
        var t = if (gauche.isNotEmpty()) {
            val sel = arrayListOf(gauche.last())
            for (w in gauche.dropLast(1).reversed()) { if (sel[0].r.x0 - w.r.x1 > 12) break; sel.add(0, w) }
            sel.takeLast(6).joinToString(" ") { it.texte }
        } else mots.filter { r.y0 - it.r.y1 in 0f..22f && it.r.x0 < r.x1 && it.r.x1 > r.x0 - 20 }.sortedBy { it.r.x0 }
            .take(6).joinToString(" ") { it.texte }
        t = t.trim().replace(Regex("[_.…:]+$"), "").trim(' ', ':')
        return t.take(60).ifEmpty { "Champ" }
    }

    /** Champs a creer sur une page (rien n'est pose ici). */
    fun detecter(page: PDFPage, n: Int): List<ChampDetecte> {
        val m = mots(page)
        val occupes = ArrayList<Rect>()
        page.widgets?.forEach { try { occupes += Rect(it.bounds) } catch (_: Exception) {} }
        val champs = ArrayList<ChampDetecte>()
        fun libre(r: Rect) = (occupes + champs.map { it.rect }).none { o -> touche(r, o) && aire(inter(r, o)) > 0.25f * minOf(aire(r), aire(o)) }
        fun ajouter(genre: String, r: Rect, multi: Boolean = false) {
            if (r.x1 - r.x0 < 4 || r.y1 - r.y0 < 4 || !libre(r)) return
            champs += ChampDetecte(n, genre, r, libelle(r, m, genre == "case"), multi)
        }
        val texteRects = m.filter { !Regex("[_.…]{3,}").matches(it.texte) }.map { it.r }
        // 1. soulignes et pointilles tapes
        for (w in m) {
            val f = Regex("_{4,}|[.…]{5,}").find(w.texte) ?: continue
            val r = Rect(w.r)
            if (f.range.first > 0) r.x0 += (r.x1 - r.x0) * f.range.first / w.texte.length
            val h = maxOf(r.y1 - r.y0, 12f)
            ajouter("texte", Rect(r.x0, r.y1 - h, r.x1, r.y1 + 1))
        }
        // 2. cases tapees
        for (w in m) w.texte.forEachIndexed { k, ch ->
            if (ch in CASES) {
                val l = (w.r.x1 - w.r.x0) / maxOf(1, w.texte.length)
                val x0 = w.r.x0 + k * l
                val cote = minOf(l, w.r.y1 - w.r.y0)
                ajouter("case", Rect(x0, w.r.y1 - cote - 1, x0 + cote, w.r.y1 - 1))
            }
        }
        // 3. dessins : traits et carres
        val t = Traits()
        try { page.run(t, Matrix(), null as Cookie?) } catch (_: Exception) {}
        val largeurPage = page.bounds.let { it.x1 - it.x0 }
        fun sousTrait(x0: Float, x1: Float, y: Float) {
            val zone = Rect(x0, y - 14, x1, y - 0.5f)
            if (texteRects.none { touche(zone, it) && inter(zone, it).let { i -> i.x1 - i.x0 } > 6 }) ajouter("texte", zone)
        }
        for ((a, b) in t.lignes) if (kotlin.math.abs(a.y - b.y) < 0.8f && kotlin.math.abs(b.x - a.x) > 40) sousTrait(minOf(a.x, b.x), maxOf(a.x, b.x), a.y)
        for (r in t.rects) {
            val w = r.x1 - r.x0; val h = r.y1 - r.y0
            when {
                w in 5f..18f && h in 5f..18f && kotlin.math.abs(w - h) < 2.5f -> ajouter("case", r)
                h < 1.6f && w > 40 -> sousTrait(r.x0, r.x1, r.y0)
                h in 12f..160f && w > 50 && w < largeurPage * 0.95f -> {
                    val dedans = Rect(r.x0 + 1.5f, r.y0 + 1.5f, r.x1 - 1.5f, r.y1 - 1.5f)
                    if (texteRects.none { touche(dedans, it) }) ajouter("texte", dedans, h > 30)
                }
            }
        }
        return champs
    }

    /** Nom d'un champ dessine a la main : le libelle le plus proche, comme a la detection. */
    fun nomAuto(page: PDFPage, r: Rect, case: Boolean): String = libelle(r, mots(page), case)

    /** Noms uniques dans tout le document (ceux deja presents compris). */
    fun nomsUniques(pdf: PDFDocument, champs: List<ChampDetecte>) {
        val pris = HashSet<String>()
        val f = pdf.getTrailer().get("Root").get("AcroForm").get("Fields")
        if (f.isArray) for (i in 0 until f.size()) try { pris += f.get(i).resolve().get("T").asString() } catch (_: Exception) {}
        for (c in champs) {
            var nom = c.nom.ifBlank { "Champ" }
            var k = 2
            while (nom in pris) nom = "${c.nom.ifBlank { "Champ" }} ${k++}"
            pris += nom
            c.nom = nom
        }
    }

    private fun formulaire(pdf: PDFDocument): PDFObject {
        val racine = pdf.getTrailer().get("Root")
        var af = racine.get("AcroForm")
        if (af.isNull) { af = pdf.addObject(pdf.newDictionary()); racine.put("AcroForm", af) }
        if (af.get("Fields").isNull) af.put("Fields", pdf.newArray())
        if (af.get("DA").isNull) af.put("DA", pdf.newString("/Helv 0 Tf 0 g"))
        var dr = af.get("DR")
        if (dr.isNull) { dr = pdf.newDictionary(); af.put("DR", dr) }
        var polices = dr.get("Font")
        if (polices.isNull) { polices = pdf.newDictionary(); dr.put("Font", polices) }
        for ((nom, base) in listOf("Helv" to "Helvetica", "ZaDb" to "ZapfDingbats")) if (polices.get(nom).isNull) {
            val p = pdf.newDictionary()
            p.put("Type", pdf.newName("Font")); p.put("Subtype", pdf.newName("Type1")); p.put("BaseFont", pdf.newName(base))
            if (base == "Helvetica") p.put("Encoding", pdf.newName("WinAnsiEncoding"))
            polices.put(nom, pdf.addObject(p))
        }
        af.put("NeedAppearances", pdf.newBoolean(true))      // les lecteurs redessinent les champs au besoin
        return af
    }

    /** Pose un vrai champ PDF (texte ou case a cocher), sans bordure ni fond, comme sous Windows. */
    fun creer(pdf: PDFDocument, page: PDFPage, c: ChampDetecte) {
        val af = formulaire(pdf)
        val pr = Rect(c.rect).transform(page.getTransform().invert())   // repere de la page -> repere PDF
        val a = pdf.newDictionary()
        a.put("Type", pdf.newName("Annot")); a.put("Subtype", pdf.newName("Widget"))
        a.put("Rect", pr)
        a.put("F", 4)
        a.put("T", pdf.newString(c.nom)); a.put("TU", pdf.newString(c.nom))
        a.put("P", page.getObject())
        val mk = pdf.newDictionary()
        if (c.genre == "case") {
            a.put("FT", pdf.newName("Btn")); a.put("V", pdf.newName("Off")); a.put("AS", pdf.newName("Off"))
            a.put("DA", pdf.newString("/ZaDb 0 Tf 0 g"))
            mk.put("CA", pdf.newString("4"))                  // coche
        } else {
            a.put("FT", pdf.newName("Tx"))
            a.put("DA", pdf.newString(if (c.lignes) "/Helv 10 Tf 0 g" else "/Helv 0 Tf 0 g"))
            if (c.lignes) a.put("Ff", 4096)                    // plusieurs lignes
        }
        a.put("MK", mk)
        val ref = pdf.addObject(a)
        val po = page.getObject()
        var annots = po.get("Annots")
        if (annots.isNull) { annots = pdf.newArray(); po.put("Annots", annots) }
        annots.push(ref)
        af.get("Fields").push(ref)
    }

    /** Retire un champ (de la page et de la liste du formulaire). */
    fun supprimer(pdf: PDFDocument, page: PDFPage, index: Int): Boolean {
        val w = page.widgets?.getOrNull(index) ?: return false
        val obj = w.getObject()
        val f = pdf.getTrailer().get("Root").get("AcroForm").get("Fields")
        val num = if (obj.isIndirect) obj.asIndirect() else -1
        if (f.isArray && num > 0) for (i in f.size() - 1 downTo 0) { val x = f.get(i); if (x.isIndirect && x.asIndirect() == num) f.delete(i) }
        page.deleteAnnotation(w)
        return true
    }

    fun renommer(pdf: PDFDocument, page: PDFPage, index: Int, nom: String): Boolean {
        val w = page.widgets?.getOrNull(index) ?: return false
        w.getObject().put("T", pdf.newString(nom))
        w.getObject().put("TU", pdf.newString(nom))
        return true
    }
}
