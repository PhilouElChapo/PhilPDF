package io.github.philouelchapo.philpdf

import android.content.Context
import android.graphics.Bitmap
import com.artifex.mupdf.fitz.Font
import com.artifex.mupdf.fitz.PDFDocument
import com.artifex.mupdf.fitz.PDFPage
import com.googlecode.tesseract.android.TessBaseAPI
import java.io.File

/**
 * Reconnaissance du texte des pages scannees (OCR), comme PhilPDF Windows : Tesseract, langue francaise, sur le
 * telephone (rien n'est envoye). Le texte reconnu est pose INVISIBLE sur l'image, a la place de chaque mot : la page
 * garde son aspect, mais on peut chercher, copier, et modifier le texte (« Modifier le texte » efface alors aussi les
 * lettres de l'image sous la ligne).
 */
object Ocr {
    /** Nom de la police du texte reconnu : « Modifier le texte » la reconnait (lettres de l'image a effacer aussi). */
    const val POLICE = "PhilOCR"

    data class Mot(val texte: String, val x0: Float, val y0: Float, val x1: Float, val y1: Float)

    private fun donnees(ctx: Context): String {
        val d = File(ctx.filesDir, "tesseract")
        val f = File(d, "tessdata/fra.traineddata")
        if (!f.exists() || f.length() == 0L) {
            f.parentFile?.mkdirs()
            ctx.assets.open("tessdata/fra.traineddata").use { e -> f.outputStream().use { e.copyTo(it) } }
        }
        return d.absolutePath
    }

    /** Mots reconnus dans l'image (coordonnees en pixels de l'image). */
    fun mots(ctx: Context, bm: Bitmap): List<Mot> {
        val t = TessBaseAPI()
        try {
            if (!t.init(donnees(ctx), "fra")) throw IllegalStateException("Tesseract : langue introuvable")
            t.pageSegMode = TessBaseAPI.PageSegMode.PSM_AUTO
            t.setImage(bm)
            t.getUTF8Text()                                  // lance la reconnaissance
            val out = ArrayList<Mot>()
            val it = t.resultIterator ?: return out
            try {
                it.begin()
                do {
                    val w = it.getUTF8Text(TessBaseAPI.PageIteratorLevel.RIL_WORD)?.trim() ?: continue
                    if (w.isEmpty() || it.confidence(TessBaseAPI.PageIteratorLevel.RIL_WORD) < 25f) continue
                    val r = it.getBoundingRect(TessBaseAPI.PageIteratorLevel.RIL_WORD)
                    out += Mot(w, r.left.toFloat(), r.top.toFloat(), r.right.toFloat(), r.bottom.toFloat())
                } while (it.next(TessBaseAPI.PageIteratorLevel.RIL_WORD))
            } finally { it.delete() }
            return out
        } finally { t.recycle() }
    }

    /** Pose le texte reconnu, invisible, sur la page (mots en points de la page, y vers le bas). */
    fun poser(pdf: PDFDocument, page: PDFPage, mots: List<Mot>) {
        if (mots.isEmpty()) return
        val pobj = page.getObject()
        var res = pobj.get("Resources")
        if (res.isNull) { res = pobj.getInheritable("Resources"); if (res.isNull) res = pdf.newDictionary(); pobj.put("Resources", res) }
        var fonts = res.get("Font")
        if (fonts.isNull) { fonts = pdf.newDictionary(); res.put("Font", fonts) }
        var nom = POLICE; var i = 1
        while (!fonts.get(nom).isNull) nom = POLICE + (i++)
        val police = Font("Helvetica")
        fonts.put(nom, pdf.addSimpleFont(police, Font.SIMPLE_ENCODING_LATIN))
        val cp = java.nio.charset.Charset.forName("windows-1252")
        val inv = page.getTransform().invert()
        val flux = StringBuilder("q BT 3 Tr\n")             // 3 Tr : texte invisible (l'image reste ce qu'on voit)
        for (m in mots) {
            val h = (m.y1 - m.y0).coerceAtLeast(1f)
            val taille = h * 0.95f
            val naturel = m.texte.sumOf { c -> police.advanceGlyph(police.encodeCharacter(c.code), false).toDouble() }.toFloat() * taille
            val tz = if (naturel > 0) (100f * (m.x1 - m.x0) / naturel).coerceIn(20f, 400f) else 100f
            val base = m.y1 - h * 0.18f
            val ox = m.x0 * inv.a + base * inv.c + inv.e
            val oy = m.x0 * inv.b + base * inv.d + inv.f
            val hex = m.texte.toByteArray(cp).joinToString("") { "%02X".format(it.toInt() and 255) }
            flux.append("/$nom ${f(taille)} Tf ${f(tz)} Tz ${f(inv.a)} ${f(inv.b)} ${f(-inv.c)} ${f(-inv.d)} ${f(ox)} ${f(oy)} Tm <$hex> Tj\n")
        }
        flux.append("ET Q\n")
        val contenu = pobj.get("Contents")
        val tableau = pdf.newArray()
        tableau.push(pdf.addStream("q\n"))
        if (contenu.isArray) for (k in 0 until contenu.size()) tableau.push(contenu.get(k)) else if (!contenu.isNull) tableau.push(contenu)
        tableau.push(pdf.addStream("Q\n"))
        tableau.push(pdf.addStream(flux.toString()))
        pobj.put("Contents", tableau)
        pobj.put("PhilPDF_OCR", true)                     // « Modifier le texte » effacera aussi les lettres de l'image
    }

    private fun f(v: Float) = String.format(java.util.Locale.US, "%.3f", v)
}
