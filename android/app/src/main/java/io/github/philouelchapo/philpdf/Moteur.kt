package io.github.philouelchapo.philpdf

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Color
import android.net.Uri
import android.provider.OpenableColumns
import com.artifex.mupdf.fitz.Cookie
import com.artifex.mupdf.fitz.Document
import com.artifex.mupdf.fitz.Matrix
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
