package io.github.philouelchapo.philpdf

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.PointF
import android.net.Uri
import com.artifex.mupdf.fitz.Image
import com.artifex.mupdf.fitz.PDFDocument
import com.artifex.mupdf.fitz.Rect
import java.io.ByteArrayOutputStream
import java.io.File
import kotlin.math.hypot
import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToInt

/**
 * Numeriser un document avec l'appareil photo : bords du document reperes, page redressee, puis amelioree selon le
 * modele choisi (noir et blanc, couleur, pour e-mail, photo), et PDF fabrique. Tout se fait sur le telephone.
 */
object Numerisation {
    enum class Modele(val texte: Int, val grandCote: Int, val qualite: Int) {
        NOIR_BLANC(R.string.scan_nb, 2200, 0),        // PNG : texte net, fichier leger
        COULEUR(R.string.scan_couleur, 2200, 82),
        EMAIL(R.string.scan_email, 1400, 60),
        PHOTO(R.string.scan_photo, 2400, 88),
        MAGNIFICENCE(R.string.scan_magnificence, 2200, 85)   // Gemini nettoie la page ; apercu : comme Couleur
    }

    /** Consigne de « Magnificence IA » (la meme sous Windows, moteur/photo_doc.py). */
    const val CONSIGNE_MAGNIFICENCE = "Voici la photo d'une page de document, prise avec un téléphone, déjà recadrée. " +
        "Rends l'image de cette même page comme si elle sortait d'un bon scanner à plat, pour une reconnaissance du texte (OCR) parfaite : " +
        "page parfaitement droite et à plat (perspective, inclinaison et pliures corrigées), bords de la feuille au bord de l'image, " +
        "fond blanc uniforme sans ombre, reflet, grain ni taches, texte noir net et bien contrasté. " +
        "Ne change, n'ajoute, ne retire et ne réécris AUCUN mot, chiffre, signature, tampon, logo ou tableau : seulement nettoyer, " +
        "redresser et rendre lisible. Garde les couleurs des logos, tampons, surlignages et photos. Garde les proportions de la page."

    /** Page nettoyee par Gemini (image), ou null si sa reponse n'est pas une image lisible. */
    suspend fun magnifier(ctx: Context, bm: Bitmap): Bitmap? {
        val petite = reduire(bm, 2000)
        val o = ByteArrayOutputStream().also { petite.setHasAlpha(false); petite.compress(Bitmap.CompressFormat.JPEG, 90, it) }.toByteArray()
        val r = Ia.image(ctx, o, CONSIGNE_MAGNIFICENCE)
        return android.graphics.BitmapFactory.decodeByteArray(r, 0, r.size)
    }

    /** Image d'un fichier, tournee selon l'appareil photo (EXIF) et reduite si elle est enorme. */
    fun charger(ctx: Context, u: Uri, maxCote: Int = 3200): Bitmap? {
        val o = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        ctx.contentResolver.openInputStream(u)?.use { BitmapFactory.decodeStream(it, null, o) }
        if (o.outWidth <= 0) return null
        var ech = 1
        while (max(o.outWidth, o.outHeight) / (ech * 2) >= maxCote) ech *= 2
        val bm = ctx.contentResolver.openInputStream(u)?.use {
            BitmapFactory.decodeStream(it, null, BitmapFactory.Options().apply { inSampleSize = ech })
        } ?: return null
        val angle = try {
            ctx.contentResolver.openInputStream(u)?.use {
                when (androidx.exifinterface.media.ExifInterface(it).getAttributeInt(
                    androidx.exifinterface.media.ExifInterface.TAG_ORIENTATION, 1)) {
                    6 -> 90f; 3 -> 180f; 8 -> 270f; else -> 0f
                }
            } ?: 0f
        } catch (_: Exception) { 0f }
        if (angle == 0f) return bm
        val m = android.graphics.Matrix().apply { postRotate(angle) }
        return Bitmap.createBitmap(bm, 0, 0, bm.width, bm.height, m, true)
    }

    /**
     * Coins du document dans la photo (haut-gauche, haut-droite, bas-droite, bas-gauche), en pixels de la photo :
     * la plus grande zone claire, ses points extremes. Toute la photo si rien de net n'est trouve.
     */
    fun coins(bm: Bitmap): List<PointF> {
        val tout = listOf(PointF(0f, 0f), PointF(bm.width.toFloat(), 0f), PointF(bm.width.toFloat(), bm.height.toFloat()),
            PointF(0f, bm.height.toFloat()))
        val k = max(1f, max(bm.width, bm.height) / 400f)
        val w = (bm.width / k).toInt().coerceAtLeast(8); val h = (bm.height / k).toInt().coerceAtLeast(8)
        val petit = Bitmap.createScaledBitmap(bm, w, h, true)
        val px = IntArray(w * h).also { petit.getPixels(it, 0, w, 0, 0, w, h) }
        val g = IntArray(w * h) { gris(px[it]) }
        // seuil d'Otsu
        val hist = IntArray(256).also { hh -> g.forEach { hh[it]++ } }
        var somme = 0.0; for (i in 0..255) somme += i * hist[i].toDouble()
        var sB = 0.0; var wB = 0; var meilleur = 0.0; var seuil = 128
        for (t in 0..255) {
            wB += hist[t]; if (wB == 0) continue
            val wF = g.size - wB; if (wF == 0) break
            sB += t * hist[t].toDouble()
            val mB = sB / wB; val mF = (somme - sB) / wF
            val v = wB.toDouble() * wF * (mB - mF) * (mB - mF)
            if (v > meilleur) { meilleur = v; seuil = t }
        }
        // plus grande zone claire (4-voisins)
        val vu = BooleanArray(w * h)
        var grande = IntArray(0)
        val pile = IntArray(w * h)
        for (s in g.indices) {
            if (vu[s] || g[s] <= seuil) continue
            var n = 0; var top = 0; pile[top++] = s; vu[s] = true
            val zone = ArrayList<Int>()
            while (top > 0) {
                val p = pile[--top]; zone += p; n++
                val x = p % w; val y = p / w
                for (q in intArrayOf(if (x > 0) p - 1 else -1, if (x < w - 1) p + 1 else -1, if (y > 0) p - w else -1, if (y < h - 1) p + w else -1)) {
                    if (q >= 0 && !vu[q] && g[q] > seuil) { vu[q] = true; pile[top++] = q }
                }
            }
            if (n > grande.size) grande = zone.toIntArray()
        }
        if (grande.size < 0.15 * w * h || grande.size > 0.97 * w * h) return tout
        var tl = grande[0]; var tr = tl; var br = tl; var bl = tl
        fun s(p: Int) = p % w + p / w
        fun d(p: Int) = p % w - p / w
        for (p in grande) {
            if (s(p) < s(tl)) tl = p
            if (s(p) > s(br)) br = p
            if (d(p) > d(tr)) tr = p
            if (d(p) < d(bl)) bl = p
        }
        return listOf(tl, tr, br, bl).map { PointF((it % w + 0.5f) * k, (it / w + 0.5f) * k) }
    }

    private fun gris(c: Int): Int = ((c shr 16 and 255) * 30 + (c shr 8 and 255) * 59 + (c and 255) * 11) / 100

    /** La zone des quatre coins, remise a plat (perspective corrigee). */
    fun redresser(bm: Bitmap, c: List<PointF>, maxCote: Int = 2600): Bitmap {
        var lw = (hypot(c[1].x - c[0].x, c[1].y - c[0].y) + hypot(c[2].x - c[3].x, c[2].y - c[3].y)) / 2
        var lh = (hypot(c[3].x - c[0].x, c[3].y - c[0].y) + hypot(c[2].x - c[1].x, c[2].y - c[1].y)) / 2
        val e = min(1f, maxCote / max(lw, lh).coerceAtLeast(1f))
        lw *= e; lh *= e
        val out = Bitmap.createBitmap(lw.roundToInt().coerceAtLeast(1), lh.roundToInt().coerceAtLeast(1), Bitmap.Config.ARGB_8888)
        val m = android.graphics.Matrix()
        m.setPolyToPoly(floatArrayOf(c[0].x, c[0].y, c[1].x, c[1].y, c[2].x, c[2].y, c[3].x, c[3].y), 0,
            floatArrayOf(0f, 0f, lw, 0f, lw, lh, 0f, lh), 0, 4)
        Canvas(out).apply { drawColor(android.graphics.Color.WHITE); drawBitmap(bm, m, Paint(Paint.FILTER_BITMAP_FLAG or Paint.ANTI_ALIAS_FLAG)) }
        return aplomb(out)
    }

    /**
     * Angle (degres) qui remet les lignes de texte a l'horizontale : profil de projection (comme PhilPDF Windows),
     * recherche grossiere puis fine, sur une copie reduite. 0 si la page n'a presque pas d'encre.
     */
    fun inclinaison(bm: Bitmap): Float {
        val k = max(1f, max(bm.width, bm.height) / 700f)
        val w = (bm.width / k).toInt().coerceAtLeast(8); val h = (bm.height / k).toInt().coerceAtLeast(8)
        val px = IntArray(w * h).also { Bitmap.createScaledBitmap(bm, w, h, true).getPixels(it, 0, w, 0, 0, w, h) }
        val xs = ArrayList<Float>(); val ys = ArrayList<Float>()
        for (i in px.indices) if (gris(px[i]) < 140) { xs += (i % w - w / 2f); ys += (i / w - h / 2f) }
        if (xs.size < 200) return 0f
        val xa = xs.toFloatArray(); val ya = ys.toFloatArray()
        val diag = kotlin.math.hypot(w.toFloat(), h.toFloat()).toInt() + 2
        fun score(deg: Float): Double {
            val r = Math.toRadians(deg.toDouble()); val c = kotlin.math.cos(r); val sn = kotlin.math.sin(r)
            val rangs = IntArray(diag)
            for (i in xa.indices) {
                val y = (xa[i] * sn + ya[i] * c + diag / 2).toInt()
                if (y in 0 until diag) rangs[y]++
            }
            var t = 0.0; for (v in rangs) t += v.toDouble() * v
            return t
        }
        var best = 0f; var bs = -1.0
        var a = -6f
        while (a <= 6f) { val sc = score(a); if (sc > bs) { bs = sc; best = a }; a += 0.5f }
        var f = best - 0.5f; val fin = best + 0.5f
        while (f <= fin) { val sc = score(f); if (sc > bs) { bs = sc; best = f }; f += 0.1f }
        return best
    }

    /** Lignes de texte remises a l'horizontale (petite inclinaison restee apres le recadrage). */
    fun aplomb(bm: Bitmap): Bitmap {
        val a = inclinaison(bm)
        if (kotlin.math.abs(a) < 0.2f) return bm
        return tourner(bm, a)
    }

    /**
     * Correction (repere image, y vers le bas) : rotation de a degres (sens des aiguilles d'une montre) puis
     * inclinaison des verticales de v degres (les lignes horizontales restent horizontales), autour du centre.
     */
    fun matrice(a: Float, v: Float, w: Float, h: Float): android.graphics.Matrix = android.graphics.Matrix().apply {
        setRotate(a, w / 2, h / 2)
        postSkew(kotlin.math.tan(Math.toRadians(v.toDouble())).toFloat(), 0f, w / 2, h / 2)
    }

    /** Image redressee : rotation a et inclinaison des verticales v (degres), meme taille, coins blancs. */
    fun transformer(bm: Bitmap, a: Float, v: Float): Bitmap {
        if (kotlin.math.abs(a) < 0.01f && kotlin.math.abs(v) < 0.01f) return bm
        val out = Bitmap.createBitmap(bm.width, bm.height, Bitmap.Config.ARGB_8888)
        Canvas(out).apply {
            drawColor(android.graphics.Color.WHITE)
            drawBitmap(bm, matrice(a, v, bm.width.toFloat(), bm.height.toFloat()), Paint(Paint.FILTER_BITMAP_FLAG or Paint.ANTI_ALIAS_FLAG))
        }
        return out
    }

    /** Inclinaison des verticales (degres) apres la rotation a : bords de la feuille, colonnes, tableaux. */
    fun inclinaisonVerticale(bm: Bitmap, a: Float): Float {
        val k = max(1f, max(bm.width, bm.height) / 700f)
        val w = (bm.width / k).toInt().coerceAtLeast(8); val h = (bm.height / k).toInt().coerceAtLeast(8)
        val petit = tourner(Bitmap.createScaledBitmap(bm, w, h, true), a)
        val px = IntArray(w * h).also { petit.getPixels(it, 0, w, 0, 0, w, h) }
        val xs = ArrayList<Float>(); val ys = ArrayList<Float>()
        val mx = (w * 0.04f).toInt(); val my = (h * 0.04f).toInt()
        for (y in my until h - my) for (x in mx until w - mx) if (gris(px[y * w + x]) < 140) { xs += x.toFloat(); ys += y - h / 2f }
        if (xs.size < 200) return 0f
        val xa = xs.toFloatArray(); val ya = ys.toFloatArray()
        val marge = w / 2
        fun score(deg: Float): Double {
            val t = kotlin.math.tan(Math.toRadians(deg.toDouble())).toFloat()
            val col = IntArray(w + 2 * marge)
            for (i in xa.indices) { val x = (xa[i] + t * ya[i]).toInt() + marge; if (x in col.indices) col[x]++ }
            var s = 0.0; for (c in col) s += c.toDouble() * c
            return s
        }
        val zero = score(0f)
        var best = 0f; var bs = -1.0
        var d = -6f
        while (d <= 6f) { val sc = score(d); if (sc > bs) { bs = sc; best = d }; d += 0.25f }
        var f = best - 0.25f; val fin = best + 0.25f
        while (f <= fin) { val sc = score(f); if (sc > bs) { bs = sc; best = f }; f += 0.05f }
        return if (bs > zero * 1.04) best else 0f
    }

    /** Image tournee de deg degres (sens des aiguilles d'une montre), meme taille, coins blancs. */
    fun tourner(bm: Bitmap, a: Float): Bitmap {
        if (kotlin.math.abs(a) < 0.01f) return bm
        val out = Bitmap.createBitmap(bm.width, bm.height, Bitmap.Config.ARGB_8888)
        Canvas(out).apply {
            drawColor(android.graphics.Color.WHITE)
            rotate(a, bm.width / 2f, bm.height / 2f)
            drawBitmap(bm, 0f, 0f, Paint(Paint.FILTER_BITMAP_FLAG or Paint.ANTI_ALIAS_FLAG))
        }
        return out
    }

    /** Tourne la page d'un quart de tour (sens des aiguilles d'une montre). */
    fun quartDeTour(bm: Bitmap): Bitmap =
        Bitmap.createBitmap(bm, 0, 0, bm.width, bm.height, android.graphics.Matrix().apply { postRotate(90f) }, true)

    private fun reduire(bm: Bitmap, cote: Int): Bitmap {
        val g = max(bm.width, bm.height)
        if (g <= cote) return bm
        val e = cote.toFloat() / g
        return Bitmap.createScaledBitmap(bm, (bm.width * e).roundToInt().coerceAtLeast(1), (bm.height * e).roundToInt().coerceAtLeast(1), true)
    }

    /** Copie reduite pour l'apercu a l'ecran (rapide). */
    fun reduirePourApercu(bm: Bitmap): Bitmap = reduire(bm, 1000)

    /** Applique le modele : fond eclairci (ombres et lumiere inegale retirees), noir et blanc net, ou rien (photo). */
    fun ameliorer(source: Bitmap, m: Modele): Bitmap {
        val bm = reduire(source, m.grandCote).copy(Bitmap.Config.ARGB_8888, true)
        if (m == Modele.PHOTO) return bm
        val w = bm.width; val h = bm.height
        val px = IntArray(w * h).also { bm.getPixels(it, 0, w, 0, 0, w, h) }
        // fond estime : image tres reduite (le texte disparait), lissee, puis agrandie
        val f = 24
        val fw = (w / f).coerceAtLeast(2); val fh = (h / f).coerceAtLeast(2)
        val fond0 = Bitmap.createScaledBitmap(bm, fw, fh, true)
        val fp = IntArray(fw * fh).also { fond0.getPixels(it, 0, fw, 0, 0, fw, fh) }
        // le texte assombrit le fond : on garde le plus clair du voisinage (dilatation), puis on lisse
        val clair = IntArray(fw * fh)
        for (y in 0 until fh) for (x in 0 until fw) {
            var r = 0; var gg = 0; var b = 0
            for (dy in -1..1) for (dx in -1..1) {
                val xx = (x + dx).coerceIn(0, fw - 1); val yy = (y + dy).coerceIn(0, fh - 1)
                val c = fp[yy * fw + xx]
                r = max(r, c shr 16 and 255); gg = max(gg, c shr 8 and 255); b = max(b, c and 255)
            }
            clair[y * fw + x] = (0xFF shl 24) or (r shl 16) or (gg shl 8) or b
        }
        val fondPetit = Bitmap.createBitmap(clair, fw, fh, Bitmap.Config.ARGB_8888)
        val fond = Bitmap.createScaledBitmap(fondPetit, w, h, true)
        val fd = IntArray(w * h).also { fond.getPixels(it, 0, w, 0, 0, w, h) }
        val nb = m == Modele.NOIR_BLANC
        for (i in px.indices) {
            val c = px[i]; val b0 = fd[i]
            fun canal(v: Int, fv: Int): Int {
                val n = (v * 255f / fv.coerceAtLeast(40)).coerceAtMost(255f)
                // contraste : le fond part au blanc, l'encre fonce
                val t = ((n - 40f) / (235f - 40f)).coerceIn(0f, 1f)
                return (255f * t * t * (3 - 2 * t)).roundToInt()
            }
            val r = canal(c shr 16 and 255, b0 shr 16 and 255)
            val g = canal(c shr 8 and 255, b0 shr 8 and 255)
            val b = canal(c and 255, b0 and 255)
            px[i] = if (nb) {
                val v = if ((r * 30 + g * 59 + b * 11) / 100 < 165) 0 else 255
                (0xFF shl 24) or (v shl 16) or (v shl 8) or v
            } else (0xFF shl 24) or (r shl 16) or (g shl 8) or b
        }
        if (nb) nettoyerNb(px, w, h, max(w, h) / 11.69f / 300f)
        bm.setPixels(px, 0, w, 0, 0, w, h)
        return bm
    }

    /**
     * Noir et blanc : bords noirs (bord de la feuille, ombre) et taches isolees retires, comme sous Windows
     * (moteur/nettoyage.py). k : resolution / 300 dpi. Une tache proche des lettres (point du i, accent) reste.
     * Renvoie (taches, bords) retires.
     */
    fun nettoyerNb(px: IntArray, w: Int, h: Int, k: Float): Pair<Int, Int> {
        val n = w * h
        val lab = IntArray(n)                                   // 0 : blanc ; sinon numero de la tache d'encre
        val noir = { i: Int -> (px[i] and 255) < 128 }
        val pile = IntArray(n)
        val aire = ArrayList<Int>(); val x0 = ArrayList<Int>(); val y0 = ArrayList<Int>(); val x1 = ArrayList<Int>(); val y1 = ArrayList<Int>()
        aire += 0; x0 += 0; y0 += 0; x1 += 0; y1 += 0
        var nb = 0
        for (dep in 0 until n) {
            if (lab[dep] != 0 || !noir(dep)) continue
            nb++
            var sp = 0; pile[sp++] = dep; lab[dep] = nb
            var a = 0; var ax = w; var ay = h; var bx = 0; var by = 0
            while (sp > 0) {
                val i = pile[--sp]; val x = i % w; val y = i / w
                a++; if (x < ax) ax = x; if (y < ay) ay = y; if (x > bx) bx = x; if (y > by) by = y
                for (dy in -1..1) for (dx in -1..1) {
                    val xx = x + dx; val yy = y + dy
                    if (xx < 0 || yy < 0 || xx >= w || yy >= h) continue
                    val j = yy * w + xx
                    if (lab[j] == 0 && noir(j)) { lab[j] = nb; pile[sp++] = j }
                }
            }
            aire += a; x0 += ax; y0 += ay; x1 += bx; y1 += by
        }
        if (nb == 0) return 0 to 0
        val effacer = BooleanArray(nb + 1)
        // 1. bords : ce qui touche le bord et ressemble a un bord (trait le long du bord, bande noire)
        val m = max(2, (0.004f * max(w, h)).toInt())
        val bxw = 0.045f * w; val byh = 0.035f * h
        var bords = 0
        for (c in 1..nb) {
            val bw = x1[c] - x0[c] + 1; val bh = y1[c] - y0[c] + 1
            val touche = x0[c] <= m || y0[c] <= m || x1[c] >= w - 1 - m || y1[c] >= h - 1 - m
            val bande = x1[c] < bxw || x0[c] > w - bxw || y1[c] < byh || y0[c] > h - byh
            val trait = (bh > 0.08f * h && bw < 0.03f * w) || (bw > 0.08f * w && bh < 0.03f * h)
            // bande noire le long d'un bord (table ou ombre autour de la feuille) : haute et etroite, ou l'inverse
            val bandeBord = touche && ((bh > 0.5f * h && bw < 0.2f * w) || (bw > 0.5f * w && bh < 0.2f * h))
            if ((touche && (trait || bande)) || (bande && trait) || bandeBord) { effacer[c] = true; bords++ }
        }
        // 2. taches isolees : petites, sans lettre a moins de ~2 mm (somme cumulee de l'encre « grosse »)
        val petit = 20f * k * k
        val r = max(3, (24 * k).toInt())
        val cum = IntArray((w + 1) * (h + 1))
        for (y in 0 until h) {
            var ligne = 0
            for (x in 0 until w) {
                val c = lab[y * w + x]
                if (c != 0 && !effacer[c] && aire[c] > petit) ligne++
                cum[(y + 1) * (w + 1) + x + 1] = cum[y * (w + 1) + x + 1] + ligne
            }
        }
        fun somme(ax: Int, ay: Int, bx: Int, by: Int): Int {
            val a = ax.coerceIn(0, w); val b = ay.coerceIn(0, h); val c = (bx + 1).coerceIn(0, w); val d = (by + 1).coerceIn(0, h)
            return cum[d * (w + 1) + c] - cum[b * (w + 1) + c] - cum[d * (w + 1) + a] + cum[b * (w + 1) + a]
        }
        var taches = 0
        for (c in 1..nb) {
            if (effacer[c] || aire[c] > petit) continue
            if (somme(x0[c] - r, y0[c] - r, x1[c] + r, y1[c] + r) == 0) { effacer[c] = true; taches++ }
        }
        val blanc = (0xFF shl 24) or 0xFFFFFF
        for (i in 0 until n) { val c = lab[i]; if (c != 0 && effacer[c]) px[i] = blanc }
        return taches to bords
    }

    /** Octets de l'image pour le PDF : PNG pour le noir et blanc, JPEG sinon. */
    fun octets(bm: Bitmap, m: Modele): ByteArray = ByteArrayOutputStream().also {
        bm.setHasAlpha(false)
        if (m == Modele.NOIR_BLANC) bm.compress(Bitmap.CompressFormat.PNG, 100, it)
        else bm.compress(Bitmap.CompressFormat.JPEG, m.qualite, it)
    }.toByteArray()

    /** PDF d'une page par image, largeur A4 (595 points), hauteur selon l'image. */
    fun fabriquerPdf(pages: List<ByteArray>, f: File): File {
        val pdf = PDFDocument()
        try {
            for (o in pages) {
                val img = Image(o)
                val w = 595f
                val hh = (w * img.height / img.width.coerceAtLeast(1)).coerceAtLeast(10f)
                val res = pdf.newDictionary()
                val xo = pdf.newDictionary()
                xo.put("Im0", pdf.addImage(img))
                res.put("XObject", xo)
                pdf.insertPage(-1, pdf.addPage(Rect(0f, 0f, w, hh), 0, res, "q $w 0 0 $hh 0 0 cm /Im0 Do Q"))
            }
            f.parentFile?.mkdirs()
            pdf.save(f.absolutePath, "compress")
        } finally { pdf.destroy() }
        return f
    }

    /** Nom propose : « Scan 2026-11-05 11h04.pdf ». */
    fun nom(): String = Textes.t(R.string.scan_nom_fichier,
        java.text.SimpleDateFormat("yyyy-MM-dd HH'h'mm", java.util.Locale.ROOT).format(java.util.Date())) + ".pdf"
}
