package io.github.philouelchapo.philpdf

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Color
import android.net.Uri
import android.provider.OpenableColumns
import com.artifex.mupdf.fitz.Cookie
import com.artifex.mupdf.fitz.Document
import com.artifex.mupdf.fitz.Matrix
import com.artifex.mupdf.fitz.Outline
import com.artifex.mupdf.fitz.PDFAnnotation
import com.artifex.mupdf.fitz.PDFDocument
import com.artifex.mupdf.fitz.PDFPage
import com.artifex.mupdf.fitz.Point
import com.artifex.mupdf.fitz.Quad
import com.artifex.mupdf.fitz.Rect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import com.artifex.mupdf.fitz.android.AndroidDrawDevice
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import java.io.File
import java.security.MessageDigest

/** Empreinte courte d'un texte (nom de fichier de cache). */
fun empreinte(texte: String): String =
    MessageDigest.getInstance("SHA-1").digest(texte.toByteArray()).joinToString("") { "%02x".format(it) }.take(16)

/** Nom affiche d'un fichier (« Facture.pdf »), quel que soit l'endroit d'ou il vient (Drive, telechargements...). */
fun nomDuFichier(ctx: Context, uri: Uri): String {
    try {
        ctx.contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { c ->
            if (c.moveToFirst()) {
                val n = c.getString(0)
                if (!n.isNullOrBlank()) return n
            }
        }
    } catch (_: Exception) {
    }
    return uri.lastPathSegment?.substringAfterLast('/') ?: "document.pdf"
}

/**
 * Un PDF ouvert. Le fichier est d'abord copie dans le cache de l'appli (un PDF venant d'un Drive ou d'un
 * partage n'est souvent lisible qu'une fois) ; MuPDF lit cette copie. MuPDF ne supporte pas d'etre appele
 * depuis plusieurs fils a la fois : tout passe par un verrou.
 */
class DocumentPdf private constructor(val uri: Uri, val nom: String, val fichier: File, private val doc: Document) {
    private val verrou = Mutex()
    private val pdf: PDFDocument? = doc as? PDFDocument

    /** Augmente a chaque modification : les pages et vignettes se redessinent. */
    var version by mutableIntStateOf(0)
    var modifie by mutableStateOf(false)
    var peutAnnuler by mutableStateOf(false)
    var peutRetablir by mutableStateOf(false)
    val modifiable: Boolean get() = pdf != null

    init {
        try { pdf?.enableJournal() } catch (_: Exception) { }   // annuler / retablir
    }

    private fun apres(change: Boolean) {
        if (change) {
            modifie = true
            version++
        }
        peutAnnuler = try { pdf?.canUndo() ?: false } catch (_: Exception) { false }
        peutRetablir = try { pdf?.canRedo() ?: false } catch (_: Exception) { false }
    }

    /** Une modification annulable (une etape du journal). bloc renvoie vrai si quelque chose a change. */
    private suspend fun operation(nom: String, bloc: (PDFDocument) -> Boolean): Boolean {
        val p = pdf ?: return false
        val r = verrou.withLock {
            withContext(Dispatchers.IO) {
                p.beginOperation(nom)
                try { bloc(p) } catch (_: Exception) { false } finally { p.endOperation() }
            }
        }
        apres(r)
        return r
    }

    suspend fun annuler() {
        val p = pdf ?: return
        verrou.withLock { withContext(Dispatchers.IO) { if (p.canUndo()) p.undo() } }
        apres(true)
    }

    suspend fun retablir() {
        val p = pdf ?: return
        verrou.withLock { withContext(Dispatchers.IO) { if (p.canRedo()) p.redo() } }
        apres(true)
    }

    private fun <T> surPage(p: PDFDocument, n: Int, f: (PDFPage) -> T): T {
        val page = p.loadPage(n) as PDFPage
        try {
            val r = f(page)
            page.update()
            return r
        } finally {
            page.destroy()
        }
    }

    /** Surligner / souligner / barrer le texte entre deux points (en points de la page). */
    suspend fun annoterTexte(n: Int, genre: Int, a: Point, b: Point, couleur: FloatArray, opacite: Float): Boolean =
        operation("Annoter") { p ->
            surPage(p, n) { page ->
                val st = page.toStructuredText()
                val q: Array<Quad>? = try { st.highlight(a, b) } finally { st.destroy() }
                if (q.isNullOrEmpty()) false else {
                    val an = page.createAnnotation(genre)
                    an.setQuadPoints(q)
                    an.setColor(couleur)
                    an.setOpacity(opacite)
                    an.update()
                    true
                }
            }
        }

    /** Dessin a main levee. */
    suspend fun dessiner(n: Int, points: List<Point>, couleur: FloatArray, epaisseur: Float, opacite: Float): Boolean =
        if (points.size < 2) false else operation("Dessin") { p ->
            surPage(p, n) { page ->
                val an = page.createAnnotation(PDFAnnotation.TYPE_INK)
                an.setInkList(arrayOf(points.toTypedArray()))
                an.setColor(couleur)
                an.setBorderWidth(epaisseur)
                an.setOpacity(opacite)
                an.update()
                true
            }
        }

    /** Rectangle, ellipse ou fleche entre deux points. */
    suspend fun forme(n: Int, genre: Int, a: Point, b: Point, couleur: FloatArray, epaisseur: Float, opacite: Float): Boolean =
        operation("Forme") { p ->
            surPage(p, n) { page ->
                val an = page.createAnnotation(genre)
                if (genre == PDFAnnotation.TYPE_LINE) {
                    an.setLine(a, b)
                    an.setLineEndingStyles(PDFAnnotation.LINE_ENDING_NONE, PDFAnnotation.LINE_ENDING_OPEN_ARROW)
                } else {
                    an.setRect(Rect(minOf(a.x, b.x), minOf(a.y, b.y), maxOf(a.x, b.x), maxOf(a.y, b.y)))
                }
                an.setColor(couleur)
                an.setBorderWidth(epaisseur)
                an.setOpacity(opacite)
                an.update()
                true
            }
        }

    /** Note (bulle) a l'endroit touche. */
    suspend fun note(n: Int, a: Point, texte: String, couleur: FloatArray): Boolean =
        operation("Note") { p ->
            surPage(p, n) { page ->
                val an = page.createAnnotation(PDFAnnotation.TYPE_TEXT)
                an.setRect(Rect(a.x, a.y, a.x + 20f, a.y + 20f))
                an.setContents(texte)
                an.setColor(couleur)
                an.update()
                true
            }
        }

    /** Annotation sous le doigt (la plus au-dessus), ou null. */
    suspend fun annotationA(n: Int, a: Point): InfoAnnot? = verrou.withLock {
        withContext(Dispatchers.IO) {
            val page = doc.loadPage(n) as? PDFPage ?: return@withContext null
            try {
                val l = page.annotations ?: emptyArray()
                var trouve: InfoAnnot? = null
                for (i in l.indices.reversed()) {
                    val an = l[i]
                    val t = an.type
                    if (t == PDFAnnotation.TYPE_LINK || t == PDFAnnotation.TYPE_WIDGET || t == PDFAnnotation.TYPE_POPUP) continue
                    val r = an.bounds
                    if (a.x >= r.x0 - 8 && a.x <= r.x1 + 8 && a.y >= r.y0 - 8 && a.y <= r.y1 + 8) {
                        trouve = InfoAnnot(n, i, t, an.color ?: floatArrayOf(0f, 0f, 0f),
                            try { an.opacity } catch (_: Exception) { 1f },
                            try { an.borderWidth } catch (_: Exception) { 1f },
                            try { an.contents ?: "" } catch (_: Exception) { "" })
                        break
                    }
                }
                trouve
            } finally {
                page.destroy()
            }
        }
    }

    /** Change la couleur, l'opacite, l'epaisseur ou le texte d'une annotation. */
    suspend fun modifierAnnotation(info: InfoAnnot, couleur: FloatArray?, opacite: Float?, epaisseur: Float?, texte: String?): Boolean =
        operation("Modifier l'annotation") { p ->
            surPage(p, info.page) { page ->
                val an = page.annotations?.getOrNull(info.index)
                if (an == null) false else {
                    couleur?.let { an.setColor(it) }
                    opacite?.let { an.setOpacity(it) }
                    epaisseur?.let { an.setBorderWidth(it) }
                    texte?.let { an.setContents(it) }
                    an.update()
                    true
                }
            }
        }

    suspend fun supprimerAnnotation(info: InfoAnnot): Boolean =
        operation("Supprimer l'annotation") { p ->
            surPage(p, info.page) { page ->
                val an = page.annotations?.getOrNull(info.index)
                if (an == null) false else { page.deleteAnnotation(an); true }
            }
        }

    /** Etat actuel du document ecrit dans un fichier (pour enregistrer, partager, imprimer). */
    suspend fun ecrire(dest: File): File = verrou.withLock {
        withContext(Dispatchers.IO) {
            dest.parentFile?.mkdirs()
            val p = pdf
            if (p != null && modifie) p.save(dest.absolutePath, "garbage=compact") else fichier.copyTo(dest, overwrite = true)
            dest
        }
    }

    /** Copie a jour pour partager ou imprimer (le fichier d'origine n'est pas touche). */
    suspend fun copieAJour(ctx: Context): File =
        if (!modifie) fichier else ecrire(File(ctx.cacheDir, "ouverts/partage/" + nom.replace('/', '_')))

    /** Enregistre dans un fichier choisi (meme fichier ou autre nom). */
    suspend fun enregistrer(ctx: Context, cible: Uri) {
        val tmp = ecrire(File(ctx.cacheDir, "ouverts/enregistrement/" + nom.replace('/', '_')))
        withContext(Dispatchers.IO) {
            ctx.contentResolver.openOutputStream(cible, "wt")?.use { s -> tmp.inputStream().use { it.copyTo(s) } }
                ?: throw IllegalStateException("écriture impossible")
        }
        modifie = false
    }

    fun besoinMotDePasse(): Boolean = doc.needsPassword()
    fun motDePasse(m: String): Boolean = doc.authenticatePassword(m)
    fun nbPages(): Int = doc.countPages()

    /** Largeur et hauteur de chaque page, en points. */
    suspend fun tailles(): List<Pair<Float, Float>> = verrou.withLock {
        withContext(Dispatchers.IO) {
            (0 until doc.countPages()).map { n ->
                val p = doc.loadPage(n)
                try {
                    val b = p.bounds
                    Pair(b.x1 - b.x0, b.y1 - b.y0)
                } finally {
                    p.destroy()
                }
            }
        }
    }

    /** Image de la page n a la largeur demandee (en pixels). */
    suspend fun rendre(n: Int, largeurPx: Int): Bitmap = verrou.withLock {
        withContext(Dispatchers.IO) { rendreSansVerrou(n, largeurPx) }
    }

    private fun rendreSansVerrou(n: Int, largeurPx: Int): Bitmap {
        val page = doc.loadPage(n)
        try {
            val b = page.bounds
            val z = largeurPx.coerceAtLeast(1) / (b.x1 - b.x0).coerceAtLeast(1f)
            val h = ((b.y1 - b.y0) * z).toInt().coerceAtLeast(1)
            val bm = Bitmap.createBitmap(largeurPx.coerceAtLeast(1), h, Bitmap.Config.ARGB_8888)
            bm.eraseColor(Color.WHITE)
            val dev = AndroidDrawDevice(bm, 0, 0)
            try {
                page.run(dev, Matrix(z, z), null as Cookie?)
                dev.close()
            } finally {
                dev.destroy()
            }
            return bm
        } finally {
            page.destroy()
        }
    }

    /** Sommaire du document (signets) : titre, profondeur, page (0 = premiere). */
    suspend fun signets(): List<Signet> = verrou.withLock {
        withContext(Dispatchers.IO) {
            val out = ArrayList<Signet>()
            fun parcourir(l: Array<Outline>?, profondeur: Int) {
                l ?: return
                for (o in l) {
                    if (out.size >= 2000) return
                    if (o.title != null) {
                        val p = try { doc.pageNumberFromLocation(doc.resolveLink(o)) } catch (_: Exception) { -1 }
                        out.add(Signet(o.title, profondeur, p))
                    }
                    if (profondeur < 8) parcourir(o.down, profondeur + 1)
                }
            }
            try { parcourir(doc.loadOutline(), 0) } catch (_: Exception) { }
            out
        }
    }

    /** Recherche dans tout le document : zones trouvees (en points) par page. */
    suspend fun rechercher(texte: String): List<Trouve> = verrou.withLock {
        withContext(Dispatchers.IO) {
            val out = ArrayList<Trouve>()
            if (texte.isBlank()) return@withContext out
            for (n in 0 until doc.countPages()) {
                val p = doc.loadPage(n)
                try {
                    val q = p.search(texte) ?: emptyArray()
                    if (q.isNotEmpty()) {
                        out.add(Trouve(n, q.map { morceaux ->
                            val xs = morceaux.flatMap { listOf(it.ul_x, it.ur_x, it.ll_x, it.lr_x) }
                            val ys = morceaux.flatMap { listOf(it.ul_y, it.ur_y, it.ll_y, it.lr_y) }
                            floatArrayOf(xs.min(), ys.min(), xs.max(), ys.max())
                        }))
                    }
                } finally {
                    p.destroy()
                }
            }
            out
        }
    }

    /** Commentaires (notes, surlignages...) de chaque page : page, genre, texte. */
    suspend fun commentaires(): List<Commentaire> = verrou.withLock {
        withContext(Dispatchers.IO) {
            val out = ArrayList<Commentaire>()
            for (n in 0 until doc.countPages()) {
                val p = doc.loadPage(n)
                try {
                    (p as? PDFPage)?.annotations?.forEach { a ->
                        val genre = try { a.type } catch (_: Exception) { -1 }
                        if (genre == com.artifex.mupdf.fitz.PDFAnnotation.TYPE_LINK || genre == com.artifex.mupdf.fitz.PDFAnnotation.TYPE_WIDGET) return@forEach
                        val texte = try { a.contents ?: "" } catch (_: Exception) { "" }
                        val auteur = try { a.author ?: "" } catch (_: Exception) { "" }
                        out.add(Commentaire(n, genre, texte, auteur))
                    }
                } finally {
                    p.destroy()
                }
            }
            out
        }
    }

    fun fermer() {
        try {
            doc.destroy()
        } catch (_: Exception) {
        }
    }

    companion object {
        /** Ouvre un PDF venant de n'importe ou (fichier, Drive, piece jointe...). */
        suspend fun ouvrir(ctx: Context, uri: Uri): DocumentPdf = withContext(Dispatchers.IO) {
            val nom = nomDuFichier(ctx, uri)
            val dossier = File(ctx.cacheDir, "ouverts/" + empreinte(uri.toString())).apply { mkdirs() }
            val copie = File(dossier, nom.replace('/', '_'))
            ctx.contentResolver.openInputStream(uri)?.use { entree ->
                copie.outputStream().use { sortie -> entree.copyTo(sortie) }
            } ?: throw IllegalStateException("lecture impossible")
            DocumentPdf(uri, nom, copie, Document.openDocument(copie.absolutePath))
        }

        /** Copies de plus de deux jours : effacees (la place sur le telephone compte). */
        fun nettoyerCache(ctx: Context) {
            val limite = System.currentTimeMillis() - 2L * 24 * 3600 * 1000
            File(ctx.cacheDir, "ouverts").listFiles()?.forEach { d ->
                if (d.lastModified() < limite) d.deleteRecursively()
            }
        }
    }
}

/** Miniature de la premiere page, gardee sur le telephone : l'Accueil l'affiche sans rouvrir le PDF. */
object Miniatures {
    fun fichier(ctx: Context, uri: String): File =
        File(File(ctx.filesDir, "miniatures").apply { mkdirs() }, empreinte(uri) + ".png")

    suspend fun fabriquer(ctx: Context, doc: DocumentPdf) {
        try {
            if (doc.nbPages() == 0) return
            val bm = doc.rendre(0, 120)
            withContext(Dispatchers.IO) {
                fichier(ctx, doc.uri.toString()).outputStream().use { bm.compress(Bitmap.CompressFormat.PNG, 90, it) }
            }
        } catch (_: Exception) {
        }
    }
}

data class Signet(val titre: String, val profondeur: Int, val page: Int)
data class Trouve(val page: Int, val zones: List<FloatArray>)
data class Commentaire(val page: Int, val genre: Int, val texte: String, val auteur: String)
data class InfoAnnot(val page: Int, val index: Int, val genre: Int, val couleur: FloatArray, val opacite: Float,
                     val epaisseur: Float, val texte: String)
