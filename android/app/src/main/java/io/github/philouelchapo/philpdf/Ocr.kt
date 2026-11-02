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

    /** Mot reconnu, dans le repere de la page (ou de l'image avant mise a l'echelle) : boite droite (x0..y1), et pour
     *  le placer : debut de la ligne de base (ox, oy), sens d'ecriture (dx, dy), vers le haut des lettres (ux, uy),
     *  longueur et hauteur. Un mot tourne (livret plie, texte vertical) a un sens autre que (1, 0). */
    data class Mot(val texte: String, val x0: Float, val y0: Float, val x1: Float, val y1: Float,
                   val ox: Float, val oy: Float, val dx: Float, val dy: Float, val ux: Float, val uy: Float,
                   val l: Float, val h: Float, val confiance: Float) {
        fun echelle(k: Float) = Mot(texte, x0 * k, y0 * k, x1 * k, y1 * k, ox * k, oy * k, dx, dy, ux, uy, l * k, h * k, confiance)
    }

    /** Langues proposees (code Tesseract, nom, taille approximative a telecharger). Le francais est livre avec l'appli. */
    data class Langue(val code: String, val nom: String, val mo: Float, val iso: String)
    val LANGUES = listOf(
        Langue("fra", "Français", 1.1f, "fr"), Langue("eng", "Anglais", 4.0f, "en"), Langue("spa", "Espagnol", 2.2f, "es"),
        Langue("ita", "Italien", 2.4f, "it"), Langue("deu", "Allemand", 1.5f, "de"), Langue("por", "Portugais", 1.9f, "pt"),
        Langue("nld", "Néerlandais", 1.8f, "nl"))

    private fun dossier(ctx: Context) = File(ctx.filesDir, "tesseract")
    private fun fichier(ctx: Context, code: String) = File(dossier(ctx), "tessdata/$code.traineddata")

    fun disponible(ctx: Context, code: String) = code == "fra" || fichier(ctx, code).let { it.exists() && it.length() > 0 }

    /** Langues choisies la derniere fois ; au depart : le francais, et la langue du telephone si elle est proposee. */
    fun choisies(ctx: Context): List<String> {
        ctx.getSharedPreferences("ocr", Context.MODE_PRIVATE).getString("langues", null)?.split("+")?.filter { c -> LANGUES.any { it.code == c } }
            ?.takeIf { it.isNotEmpty() }?.let { return it }
        val tel = java.util.Locale.getDefault().language
        return (listOf("fra") + listOfNotNull(LANGUES.firstOrNull { it.iso == tel }?.code)).distinct()
    }
    /** Chercher aussi le texte couche ou a l'envers (livret plie, texte vertical) : plus lent. */
    fun tourne(ctx: Context) = ctx.getSharedPreferences("ocr", Context.MODE_PRIVATE).getBoolean("tourne", false)
    fun retenirTourne(ctx: Context, oui: Boolean) = ctx.getSharedPreferences("ocr", Context.MODE_PRIVATE).edit().putBoolean("tourne", oui).apply()
    fun retenir(ctx: Context, codes: List<String>) =
        ctx.getSharedPreferences("ocr", Context.MODE_PRIVATE).edit().putString("langues", codes.joinToString("+")).apply()

    /** Telecharge le modele d'une langue (projet Tesseract, version rapide) ; une seule fois, garde ensuite. */
    fun telecharger(ctx: Context, code: String) {
        if (disponible(ctx, code)) return
        val f = fichier(ctx, code); f.parentFile?.mkdirs()
        val tmp = File(f.parentFile, "$code.part")
        var url = java.net.URL("https://github.com/tesseract-ocr/tessdata_fast/raw/main/$code.traineddata")
        repeat(5) {                                          // github -> raw.githubusercontent.com (redirections)
            val c = url.openConnection() as java.net.HttpURLConnection
            c.instanceFollowRedirects = false; c.connectTimeout = 10000; c.readTimeout = 30000
            when (c.responseCode) {
                in 300..399 -> { url = java.net.URL(url, c.getHeaderField("Location")); c.disconnect() }
                200 -> {
                    c.inputStream.use { e -> tmp.outputStream().use { e.copyTo(it) } }
                    if (tmp.length() < 100_000) { tmp.delete(); throw IllegalStateException("fichier de langue incomplet") }
                    tmp.renameTo(f)
                    Journal.ecrire("ocr", "langue $code téléchargée (${f.length() / 1024} Ko)")
                    return
                }
                else -> throw IllegalStateException("téléchargement refusé (${c.responseCode})")
            }
        }
        throw IllegalStateException("téléchargement impossible")
    }

    private fun donnees(ctx: Context): String {
        val f = fichier(ctx, "fra")
        if (!f.exists() || f.length() == 0L) {
            f.parentFile?.mkdirs()
            ctx.assets.open("tessdata/fra.traineddata").use { e -> f.outputStream().use { e.copyTo(it) } }
        }
        return dossier(ctx).absolutePath
    }

    /** Mots reconnus dans l'image, lue tournee de « rotation » degres (0, 90, 180, 270 : texte couche ou a l'envers).
     *  Les positions sont rendues dans le repere de l'image d'origine. */
    fun mots(ctx: Context, bm: Bitmap, langues: String = "fra", rotation: Int = 0): List<Mot> {
        val w = bm.width.toFloat(); val hh = bm.height.toFloat()
        val img = if (rotation == 0) bm
            else Bitmap.createBitmap(bm, 0, 0, bm.width, bm.height, android.graphics.Matrix().apply { postRotate(rotation.toFloat()) }, true)
        // point de l'image tournee -> point de l'image d'origine
        fun orig(u: Float, v: Float): Pair<Float, Float> = when (rotation) {
            90 -> v to hh - u
            180 -> w - u to hh - v
            270 -> w - v to u
            else -> u to v
        }
        val t = TessBaseAPI()
        try {
            if (!t.init(donnees(ctx), langues)) throw IllegalStateException("Tesseract : langue introuvable ($langues)")
            t.pageSegMode = TessBaseAPI.PageSegMode.PSM_AUTO
            t.setImage(img)
            t.getUTF8Text()                                  // lance la reconnaissance
            val out = ArrayList<Mot>()
            val it = t.resultIterator ?: return out
            try {
                it.begin()
                do {
                    val texte = it.getUTF8Text(TessBaseAPI.PageIteratorLevel.RIL_WORD)?.trim() ?: continue
                    if (texte.none { c -> c.isLetterOrDigit() }) continue
                    val conf = it.confidence(TessBaseAPI.PageIteratorLevel.RIL_WORD)
                    val r = it.getBoundingRect(TessBaseAPI.PageIteratorLevel.RIL_WORD)
                    val h = (r.bottom - r.top).toFloat().coerceAtLeast(1f); val l = (r.right - r.left).toFloat().coerceAtLeast(1f)
                    val base = r.bottom - h * 0.18f
                    val (sx, sy) = orig(r.left.toFloat(), base)
                    val (ex, ey) = orig(r.right.toFloat(), base)
                    val (tx, ty) = orig(r.left.toFloat(), base - h)
                    val coins = listOf(orig(r.left.toFloat(), r.top.toFloat()), orig(r.right.toFloat(), r.top.toFloat()),
                        orig(r.left.toFloat(), r.bottom.toFloat()), orig(r.right.toFloat(), r.bottom.toFloat()))
                    out += Mot(texte, coins.minOf { it.first }, coins.minOf { it.second }, coins.maxOf { it.first }, coins.maxOf { it.second },
                        sx, sy, (ex - sx) / l, (ey - sy) / l, (tx - sx) / h, (ty - sy) / h, l, h, conf)
                } while (it.next(TessBaseAPI.PageIteratorLevel.RIL_WORD))
            } finally { it.delete() }
            return out
        } finally { t.recycle(); if (img !== bm) img.recycle() }
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
        val fobj = pdf.addSimpleFont(police, Font.SIMPLE_ENCODING_LATIN)
        fobj.put("BaseFont", pdf.newName("PhilOCR-Helvetica"))   // « Modifier le texte » reconnait ainsi le texte reconnu
        fonts.put(nom, fobj)
        val cp = java.nio.charset.Charset.forName("windows-1252")
        val inv = page.getTransform().invert()
        val flux = StringBuilder("q BT 3 Tr\n")             // 3 Tr : texte invisible (l'image reste ce qu'on voit)
        // vecteur de la page (y vers le bas) -> repere PDF (y vers le haut)
        fun vec(x: Float, y: Float): Pair<Float, Float> = (x * inv.a + y * inv.c) to (x * inv.b + y * inv.d)
        for (m in mots) {
            val taille = m.h * 0.95f
            val naturel = m.texte.sumOf { c -> police.advanceGlyph(police.encodeCharacter(c.code), false).toDouble() }.toFloat() * taille
            val tz = if (naturel > 0) (100f * m.l / naturel).coerceIn(20f, 400f) else 100f
            val (ax, ay) = vec(m.dx, m.dy)
            val (bx, by) = vec(m.ux, m.uy)
            val ox = m.ox * inv.a + m.oy * inv.c + inv.e
            val oy = m.ox * inv.b + m.oy * inv.d + inv.f
            val hex = m.texte.toByteArray(cp).joinToString("") { "%02X".format(it.toInt() and 255) }
            flux.append("/$nom ${f(taille)} Tf ${f(tz)} Tz ${f(ax)} ${f(ay)} ${f(bx)} ${f(by)} ${f(ox)} ${f(oy)} Tm <$hex> Tj\n")
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
