package io.github.philouelchapo.philpdf

import com.artifex.mupdf.fitz.ColorSpace
import com.artifex.mupdf.fitz.Cookie
import com.artifex.mupdf.fitz.DefaultColorSpaces
import com.artifex.mupdf.fitz.Device
import com.artifex.mupdf.fitz.DrawDevice
import com.artifex.mupdf.fitz.Image
import com.artifex.mupdf.fitz.Matrix
import com.artifex.mupdf.fitz.PDFDocument
import com.artifex.mupdf.fitz.PDFObject
import com.artifex.mupdf.fitz.Path
import com.artifex.mupdf.fitz.Pixmap
import com.artifex.mupdf.fitz.Rect
import com.artifex.mupdf.fitz.Shade
import com.artifex.mupdf.fitz.StrokeState
import com.artifex.mupdf.fitz.Text

/** Reglages d'allegement, les memes que PhilPDF Windows (Alleger) : resolution visee, qualite JPEG, et seuil
 *  (seules les images plus fines que le seuil sont reduites). dpi = 0 : sans toucher aux images. */
data class ReglageAlleger(val nom: Int, val dpi: Int, val qualite: Int, val seuil: Int)

object Alleger {
    val PREREGLAGES = listOf(
        ReglageAlleger(R.string.alleger_ecran, 150, 75, 200),
        ReglageAlleger(R.string.alleger_impression, 220, 85, 300),
        ReglageAlleger(R.string.alleger_mail, 110, 60, 140),
        ReglageAlleger(R.string.alleger_sans_perte, 0, 0, 0))

    /** Mesure la taille a laquelle chaque image est dessinee sur les pages (largeur en points, la plus grande). */
    private class Mesure : Device() {
        val largeurs = HashMap<Pair<Int, Int>, Float>()
        override fun fillImage(img: Image, ctm: Matrix, alpha: Float, cp: Int) {
            val k = img.width to img.height
            val l = kotlin.math.hypot(ctm.a, ctm.b)
            if (l > (largeurs[k] ?: 0f)) largeurs[k] = l
        }
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

    /** Reduit les images trop fines (photos, scans en couleur ou en gris) ; les images noir et blanc, masques et
     *  transparences restent telles quelles (le texte d'un scan resterait net). Renvoie le nombre d'images reduites. */
    fun images(p: PDFDocument, r: ReglageAlleger): Int {
        if (r.dpi <= 0) return 0
        val mesure = Mesure()
        for (i in 0 until p.countPages()) {
            val pg = p.loadPage(i)
            try { pg.run(mesure, Matrix(), null as Cookie?) } catch (_: Exception) { } finally { pg.destroy() }
        }
        val remplacees = HashMap<Int, PDFObject>()
        val vues = HashSet<Int>()
        var n = 0
        fun traiter(res: PDFObject?, profondeur: Int) {
            if (res == null || res.isNull) return
            val xo = res.get("XObject")
            if (!xo.isDictionary) return
            val cles = ArrayList<PDFObject>()
            for (k in xo) cles += k
            for (k in cles) {
                val ref = xo.get(k)
                val o = ref.resolve()
                val sous = o.get("Subtype").let { if (it.isName) it.asName() else "" }
                if (sous == "Form") { if (profondeur < 3) traiter(o.get("Resources"), profondeur + 1); continue }
                if (sous != "Image" || !ref.isIndirect) continue
                val num = ref.asIndirect()
                remplacees[num]?.let { xo.put(k, it); continue }
                if (!vues.add(num)) continue
                val nouvelle = try { reduire(p, o, mesure.largeurs, r) } catch (_: Exception) { null } ?: continue
                remplacees[num] = nouvelle
                xo.put(k, nouvelle)
                n++
            }
        }
        for (i in 0 until p.countPages()) traiter(p.findPage(i).getInheritable("Resources"), 0)
        // une meme image citee par une page deja vue avant d'etre reduite : seconde passe pour tout relier
        if (remplacees.isNotEmpty()) for (i in 0 until p.countPages()) traiter(p.findPage(i).getInheritable("Resources"), 0)
        return n
    }

    private fun reduire(p: PDFDocument, o: PDFObject, largeurs: Map<Pair<Int, Int>, Float>, r: ReglageAlleger): PDFObject? {
        val im = o.get("ImageMask")
        if (im.isBoolean && im.asBoolean()) return null
        if (!o.get("SMask").isNull || !o.get("Mask").isNull) return null
        if (o.get("BitsPerComponent").let { it.isNumber && it.asInteger() == 1 }) return null
        val w = o.get("Width").asInteger()
        val h = o.get("Height").asInteger()
        val pts = largeurs[w to h] ?: return null                 // jamais dessinee : on n'y touche pas
        if (pts <= 0f) return null
        val dpi = w / (pts / 72f)
        if (dpi <= r.seuil) return null
        val k = (r.dpi / dpi).coerceAtMost(1f)
        val nw = (w * k).toInt().coerceAtLeast(1)
        val nh = (h * k).toInt().coerceAtLeast(1)
        val img = p.loadImage(o)
        try {
            val cs = if (img.numberOfComponents == 1) ColorSpace.DeviceGray else ColorSpace.DeviceRGB
            val pix = Pixmap(cs, nw, nh, false)
            try {
                pix.clear(255)
                val dev = DrawDevice(pix)
                try {
                    dev.fillImage(img, Matrix(nw.toFloat(), 0f, 0f, nh.toFloat(), 0f, 0f), 1f, 0)
                    dev.close()
                } finally { dev.destroy() }
                val jpeg = pix.asJPEG(r.qualite, false)
                val avant = o.readRawStream().size
                if (jpeg.length >= avant * 0.9) return null             // aucun gain : l'image reste
                val nouvelle = Image(jpeg)
                try { return p.addImage(nouvelle) } finally { nouvelle.destroy() }
            } finally { pix.destroy() }
        } finally { img.destroy() }
    }
}
