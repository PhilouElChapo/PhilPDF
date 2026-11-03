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
import com.artifex.mupdf.fitz.PDFObject
import com.artifex.mupdf.fitz.PDFPage
import com.artifex.mupdf.fitz.PDFWidget
import com.artifex.mupdf.fitz.PKCS7Verifier
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
    /** Augmente quand des pages sont ajoutees, retirees, deplacees ou pivotees : le lecteur relit leurs tailles. */
    var pagesVersion by mutableIntStateOf(0)
    /** A l'enregistrement : null = mot de passe inchange, "" = retire, sinon nouveau mot de passe. */
    var motDePasseNouveau by mutableStateOf<String?>(null)
    private val erreursRendu = HashSet<String>()
    /** A l'enregistrement : flux recompresses, objets en double retires. */
    var compresser by mutableStateOf(false)

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

    // ---------------------------------------------------------------- images de la page (comme sous Windows)
    /** Images placees sur la page et matrice du repere PDF vers la page affichee. */
    suspend fun images(n: Int): Pair<List<ImagesPdf.Placee>, ImagesPdf.M> = verrou.withLock {
        withContext(Dispatchers.IO) {
            val p = pdf ?: return@withContext emptyList<ImagesPdf.Placee>() to ImagesPdf.M.I
            val page = p.loadPage(n) as PDFPage
            try { ImagesPdf.lister(p, page, n) to ImagesPdf.transformations(page).first }
            catch (e: Exception) { Journal.ecrire("image", "lecture des images, page ${n + 1} : $e"); emptyList<ImagesPdf.Placee>() to ImagesPdf.M.I }
            finally { page.destroy() }
        }
    }

    /** L'image sous le doigt (la plus petite si plusieurs se superposent), ou null. */
    suspend fun imageA(n: Int, pt: Point): ImagesPdf.Placee? {
        val (l, t) = images(n)
        return l.filter { it.contient(t, pt.x, pt.y) }.minByOrNull { val c = it.cadre(t); (c[2] - c[0]) * (c[3] - c[1]) }
    }

    /** Transformation de l'image dans le repere de la page affichee (deplacer, agrandir, tourner). */
    suspend fun transformerImage(i: ImagesPdf.Placee, g: ImagesPdf.M): Boolean = operation("Image") { p ->
        surPage(p, i.page) { page -> ImagesPdf.placer(p, page, i, ImagesPdf.apres(page, i, g)) }
    }

    /** Miroir gauche-droite (horizontal) ou haut-bas, sur place. */
    suspend fun miroirImage(i: ImagesPdf.Placee, horizontal: Boolean): Boolean = operation("Miroir") { p ->
        val f = if (horizontal) ImagesPdf.M(-1f, 0f, 0f, 1f, 1f, 0f) else ImagesPdf.M(1f, 0f, 0f, -1f, 0f, 1f)
        surPage(p, i.page) { page -> ImagesPdf.placer(p, page, i, f * i.ctm) }
    }

    suspend fun supprimerImage(i: ImagesPdf.Placee): Boolean = operation("Supprimer l'image") { p ->
        surPage(p, i.page) { page -> ImagesPdf.supprimer(p, page, i) }
    }

    suspend fun remplacerImage(i: ImagesPdf.Placee, octets: ByteArray): Boolean = operation("Remplacer l'image") { p ->
        surPage(p, i.page) { page -> ImagesPdf.remplacer(p, page, i, com.artifex.mupdf.fitz.Image(octets)) }
    }

    /** L'image telle qu'elle est dans le PDF, enregistree en PNG (null si illisible). */
    suspend fun exporterImage(i: ImagesPdf.Placee, dest: File): File? = verrou.withLock {
        withContext(Dispatchers.IO) {
            val p = pdf ?: return@withContext null
            try {
                var pm = p.loadImage(p.newIndirect(i.objet, 0)).toPixmap()
                val n = pm.numberOfComponents
                if (n != 1 && n != 3) pm = pm.convertToColorSpace(com.artifex.mupdf.fitz.ColorSpace.DeviceRGB, null, null, 0, true)
                dest.parentFile?.mkdirs()
                pm.saveAsPNG(dest.absolutePath)
                dest
            } catch (e: Exception) { Journal.ecrire("image", "enregistrement impossible : $e"); null }
        }
    }

    /** Debris laisses par une version precedente de PhilPDF (jusqu'a 1.10.0) dans les listes Contents et Annots des
     *  pages : MuPDF les ignore, mais Acrobat affichait alors la page vide. Retires (sauf document signe : la
     *  signature serait cassee). Renvoie les numeros des pages reparees (a partir de 1). */
    suspend fun reparerDebris(): List<Int> {
        val p = pdf ?: return emptyList()
        val pages = ArrayList<Int>()
        val signe = verrou.withLock { withContext(Dispatchers.IO) {
            try {
                (0 until p.countPages()).any { n -> val an = p.findPage(n).get("Annots")
                    an.isArray && (0 until an.size()).any { i -> val a = an.get(i)
                        a.isDictionary && a.get("FT").asName() == "Sig" && !a.get("V").isNull } }
            } catch (_: Exception) { true }
        } }
        if (signe) return emptyList()
        operation("Réparation") { d ->
            for (n in 0 until d.countPages()) {
                val po = d.findPage(n)
                for (cle in listOf("Contents", "Annots")) {
                    val t = po.get(cle)
                    if (!t.isArray) continue
                    val garder = (0 until t.size()).map { t.get(it) }.filter { it.isIndirect || (cle == "Annots" && it.isDictionary) }
                    if (garder.size == t.size()) continue
                    val neuf = d.newArray()
                    garder.forEach { neuf.ajouter(it) }
                    po.put(cle, neuf)
                    if (n + 1 !in pages) pages += n + 1
                }
            }
            pages.isNotEmpty()
        }
        if (pages.isNotEmpty()) Journal.ecrire("ouverture", "débris d'une version précédente retirés, page(s) $pages")
        return pages
    }

    suspend fun annuler() {
        val p = pdf ?: return
        verrou.withLock { withContext(Dispatchers.IO) { if (p.canUndo()) p.undo() } }
        apres(true)
        pagesVersion++                       // l'etape annulee touchait peut-etre les pages
    }

    suspend fun retablir() {
        val p = pdf ?: return
        verrou.withLock { withContext(Dispatchers.IO) { if (p.canRedo()) p.redo() } }
        apres(true)
        pagesVersion++
    }

    // ------------------------------------------------------------ organiser les pages
    private suspend fun operationPages(nom: String, bloc: (PDFDocument) -> Boolean): Boolean =
        operation(nom, bloc).also { if (it) pagesVersion++ }

    /** Pivote les pages de 90 degres (sens = 90 a droite, -90 a gauche). */
    suspend fun pivoter(pages: List<Int>, sens: Int): Boolean = operationPages("Pivoter") { p ->
        for (n in pages) {
            val o = p.findPage(n)
            val r = o.getInheritable("Rotate")
            val actuel = if (r == null || r.isNull) 0 else r.asInteger()
            o.put("Rotate", ((actuel + sens) % 360 + 360) % 360)
        }
        pages.isNotEmpty()
    }

    suspend fun supprimerPages(pages: List<Int>): Boolean = operationPages("Supprimer des pages") { p ->
        if (pages.isEmpty() || pages.size >= p.countPages()) return@operationPages false   // jamais un PDF vide
        for (n in pages.distinct().sortedDescending()) p.deletePage(n)
        true
    }

    /** Nouvel ordre : ordre[i] = ancienne place de la page qui sera en position i. */
    suspend fun ordonner(ordre: List<Int>): Boolean = operationPages("Deplacer des pages") { p ->
        if (ordre == ordre.indices.toList() || ordre.size != p.countPages()) return@operationPages false
        p.rearrangePages(ordre.toIntArray())
        true
    }

    /** Page blanche de la taille donnee (en points), inseree a la place « a ». */
    suspend fun pageBlanche(a: Int, largeur: Float, hauteur: Float): Boolean = operationPages("Page blanche") { p ->
        val o = p.addPage(Rect(0f, 0f, largeur, hauteur), 0, p.newDictionary(), "")
        p.insertPage(a.coerceIn(0, p.countPages()), o)
        true
    }

    /** Ajoute toutes les pages d'un autre PDF a la place « a ». Renvoie le nombre de pages ajoutees (0 : illisible). */
    suspend fun inserer(autre: File, a: Int): Int {
        var n = 0
        operationPages("Combiner") { p ->
            val src = Document.openDocument(autre.absolutePath) as? PDFDocument ?: return@operationPages false
            try {
                if (src.needsPassword()) return@operationPages false
                val debut = a.coerceIn(0, p.countPages())
                for (i in 0 until src.countPages()) p.graftPage(debut + i, src, i)
                n = src.countPages()
                n > 0
            } finally { src.destroy() }
        }
        return n
    }

    /** Ecrit les pages choisies dans un nouveau PDF (le document ouvert n'est pas touche). */
    suspend fun extraire(pages: List<Int>, dest: File): File = verrou.withLock {
        withContext(Dispatchers.IO) {
            val p = pdf ?: throw IllegalStateException(Textes.t(R.string.err_pdf_non_modifiable))
            dest.parentFile?.mkdirs()
            val nouveau = PDFDocument()
            try {
                pages.forEachIndexed { i, n -> nouveau.graftPage(i, p, n) }
                nouveau.save(dest.absolutePath, "garbage=compact")
            } finally { nouveau.destroy() }
            dest
        }
    }

    /** Alleger : images trop fines reduites (comme PhilPDF Windows), annulable. Renvoie le nombre d'images reduites. */
    suspend fun alleger(r: ReglageAlleger): Int {
        var n = 0
        if (r.dpi > 0) operation("Alleger") { p -> n = Alleger.images(p, r); n > 0 }
        return n
    }

    /** Taille du fichier tel qu'il serait enregistre maintenant (pour montrer le gain d'une compression). */
    suspend fun tailleEnregistree(ctx: Context): Long =
        ecrire(File(ctx.cacheDir, "ouverts/estimation/" + nom.replace('/', '_'))).length().also {
            File(ctx.cacheDir, "ouverts/estimation").deleteRecursively()
        }

    fun tailleOrigine(): Long = fichier.length()

    /** Mot de passe ou compression choisis : le document est a enregistrer. */
    fun marquerModifie() {
        modifie = true
    }

    private fun optionsEcriture(): String {
        var o = if (compresser) "garbage=deduplicate,compress=yes,compress-fonts=yes,compress-images=yes,clean=yes" else "garbage=compact"
        // copie dechiffree : on la protege avec le nouveau mot de passe, ou celui d'origine s'il n'a pas ete retire
        val m = motDePasseNouveau ?: motDePasseOuverture?.takeIf { besoinMotDePasse() && !it.contains(',') }
        if (!m.isNullOrEmpty()) o += ",encrypt=aes-256,user-password=$m,owner-password=$m"
        return o
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
                        val coul = if (t == PDFAnnotation.TYPE_FREE_TEXT)
                            (try { an.defaultAppearance?.color } catch (_: Exception) { null } ?: an.color)
                        else an.color
                        trouve = InfoAnnot(n, i, t, if (coul == null || coul.isEmpty()) floatArrayOf(0f, 0f, 0f) else coul,
                            try { an.opacity } catch (_: Exception) { 1f },
                            try { an.borderWidth } catch (_: Exception) { 1f },
                            try { an.contents ?: "" } catch (_: Exception) { "" },
                            floatArrayOf(r.x0, r.y0, r.x1, r.y1))
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
                    if (couleur != null) {
                        if (info.genre == PDFAnnotation.TYPE_FREE_TEXT) {
                            val taille = try { an.defaultAppearance?.size ?: 14f } catch (_: Exception) { 14f }
                            an.setDefaultAppearance("Helv", taille, couleur)
                        } else an.setColor(couleur)
                    }
                    opacite?.let { an.setOpacity(it) }
                    epaisseur?.let { an.setBorderWidth(it) }
                    texte?.let { an.setContents(it) }
                    an.update()
                    true
                }
            }
        }

    /** Deplace (dx, dy en points) et agrandit (k) une signature, un paraphe ou un tampon deja pose, autour de son centre. */
    suspend fun transformer(info: InfoAnnot, dx: Float, dy: Float, k: Float): Boolean =
        operation(if (k == 1f) "Déplacer" else "Taille") { p ->
            surPage(p, info.page) { page ->
                val an = page.annotations?.getOrNull(info.index)
                if (an == null) false else {
                    val b = an.rect
                    val cx = (b.x0 + b.x1) / 2
                    val cy = (b.y0 + b.y1) / 2
                    val f = { x: Float, y: Float -> Point(cx + dx + (x - cx) * k, cy + dy + (y - cy) * k) }
                    when (an.type) {
                        PDFAnnotation.TYPE_INK -> {
                            an.setInkList(an.inkList.map { t -> t.map { q -> f(q.x, q.y) }.toTypedArray() }.toTypedArray())
                            if (k != 1f) an.setBorderWidth((an.borderWidth * k).coerceIn(0.5f, 12f))
                        }
                        PDFAnnotation.TYPE_FREE_TEXT -> {
                            if (k != 1f) {
                                val da = try { an.defaultAppearance } catch (_: Exception) { null }
                                an.setDefaultAppearance("Helv", ((da?.size ?: 14f) * k).coerceIn(4f, 96f), da?.color ?: floatArrayOf(0f, 0f, 0f))
                            }
                            val a0 = f(b.x0, b.y0); val a1 = f(b.x1, b.y1)
                            an.setRect(Rect(a0.x, a0.y, a1.x, a1.y))
                        }
                        else -> { val a0 = f(b.x0, b.y0); val a1 = f(b.x1, b.y1); an.setRect(Rect(a0.x, a0.y, a1.x, a1.y)) }
                    }
                    an.update()
                    true
                }
            }
        }

    // ---------------------------------------------------------------- modifier le texte de la page
    /** Paragraphe (lignes de meme taille) sous le point, avec sa police d'origine retrouvee. */
    suspend fun paragrapheA(n: Int, a: Point): Paragraphe? = verrou.withLock {
        withContext(Dispatchers.IO) {
            val page = doc.loadPage(n) as? PDFPage ?: return@withContext null
            try { TexteModif.paragraphe(page, n, a) } catch (e: Exception) {
                Journal.ecrire("texte", "lecture du paragraphe impossible ($e)"); null
            } finally { page.destroy() }
        }
    }

    /** Remplace le texte du paragraphe (une seule etape d'annulation). */
    suspend fun reecrireTexte(par: Paragraphe, lignes: List<String>, taille: Float, argb: Int, gras: Boolean,
                              italique: Boolean, droite: Boolean): ResultatTexte {
        val p = pdf ?: return ResultatTexte(false, false, "", "document non modifiable")
        var res = ResultatTexte(false, false, "")
        val r = verrou.withLock {
            withContext(Dispatchers.IO) {
                p.beginOperation("Modifier le texte")
                try {
                    surPage(p, par.page) { page -> res = TexteModif.reecrire(p, page, par, lignes, taille, argb, gras, italique, droite); res.ok }
                } catch (e: Exception) {
                    res = ResultatTexte(false, false, "", e.message ?: e.javaClass.simpleName); false
                } finally { p.endOperation() }
            }
        }
        apres(r)
        Journal.ecrire("texte", if (res.ok) "texte modifié (${if (res.originale) "police d'origine" else "police de remplacement"} ${res.police})"
            else "modification impossible (${res.message})")
        return res
    }

    /** Surlignage -> soulignement -> barre (meme texte, meme couleur). */
    suspend fun changerGenre(info: InfoAnnot, genre: Int, couleur: FloatArray, opacite: Float): Boolean =
        operation("Changer le marquage") { p ->
            surPage(p, info.page) { page ->
                val an = page.annotations?.getOrNull(info.index)
                val q = try { an?.quadPoints } catch (_: Exception) { null }
                if (an == null || q.isNullOrEmpty()) false else {
                    page.deleteAnnotation(an)
                    val nv = page.createAnnotation(genre)
                    nv.setQuadPoints(q)
                    nv.setColor(couleur)
                    nv.setOpacity(opacite)
                    nv.update()
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

    // ---------------------------------------------------------------- formulaires
    /** Champ de formulaire sous le doigt, ou null. */
    suspend fun champA(n: Int, a: Point): InfoChamp? = verrou.withLock {
        withContext(Dispatchers.IO) {
            val page = doc.loadPage(n) as? PDFPage ?: return@withContext null
            try {
                val l = page.widgets ?: emptyArray()
                var trouve: InfoChamp? = null
                for (i in l.indices) {
                    val w = l[i]
                    val r = w.bounds
                    if (a.x in r.x0..r.x1 && a.y in r.y0..r.y1) {
                        trouve = InfoChamp(n, i, w.fieldType, try { w.value ?: "" } catch (_: Exception) { "" },
                            try { w.options?.toList() ?: emptyList() } catch (_: Exception) { emptyList() },
                            try { w.isReadOnly } catch (_: Exception) { false }, try { w.name ?: "" } catch (_: Exception) { "" },
                            try { Regles.lire(w.getObject()).toString() } catch (_: Exception) { "" },
                            try { Regles.champDe(w.getObject()).get("Ff").let { !it.isNull && it.asInteger() and ChampsPdf.FF_LIBRE != 0 } } catch (_: Exception) { false },
                            try { Regles.champDe(w.getObject()).get("Ff").let { !it.isNull && it.asInteger() and ChampsPdf.FF_PLUSIEURS != 0 } } catch (_: Exception) { false },
                            try { Regles.champDe(w.getObject()).get("V").let { v -> when {
                                v.isArray -> (0 until v.size()).map { v.get(it).asString() }
                                v.isString -> listOf(v.asString())
                                else -> emptyList() } } } catch (_: Exception) { emptyList() })
                        break
                    }
                }
                trouve
            } finally {
                page.destroy()
            }
        }
    }

    /** Remplit un champ (texte, choix ; case a cocher / bouton radio : bascule), avec les regles du champ comme sous
     *  Windows : format, controle, plage ; puis listes dependantes, champs montres / caches, calculs.
     *  Renvoie null si c'est fait, sinon le message a montrer (saisie refusee). */
    suspend fun remplir(c: InfoChamp, valeur: String?): String? {
        var erreur: String? = null
        operation("Remplir") { p ->
            var nom = ""
            val ok = surPage(p, c.page) { page ->
                val w = page.widgets?.getOrNull(c.index) ?: return@surPage false
                nom = w.name ?: ""
                when (c.genre) {
                    PDFWidget.TYPE_TEXT -> {
                        val regles = Regles.lire(w.getObject())
                        val (v, err) = Regles.saisie(regles, valeur ?: "")
                        if (err != null || v == null) { erreur = messageSaisie(err ?: "", regles, valeur ?: ""); false }
                        else { ecrireValeur(p, w, v, regles); true }
                    }
                    PDFWidget.TYPE_COMBOBOX, PDFWidget.TYPE_LISTBOX -> w.setChoiceValue(valeur ?: "").also { w.update() }
                    PDFWidget.TYPE_CHECKBOX, PDFWidget.TYPE_RADIOBUTTON -> w.toggle().also { w.update() }
                    else -> false
                }
            }
            if (ok) apresValeur(p, nom)
            ok
        }
        return erreur
    }

    /** Liste ouverte a plusieurs choix : les choix faits (dans l'ordre de la liste), et leurs numeros (/I). */
    suspend fun remplirPlusieurs(c: InfoChamp, choix: List<String>): Boolean = operation("Remplir") { p ->
        var nom = ""
        val ok = surPage(p, c.page) { page ->
            val w = page.widgets?.getOrNull(c.index) ?: return@surPage false
            nom = w.name ?: ""
            val ch = Regles.champDe(w.getObject())
            val faits = c.options.filter { it in choix }
            when (faits.size) {
                0 -> { ch.delete("V"); ch.delete("I") }
                1 -> ch.put("V", p.newString(faits[0]))
                else -> { val a = p.newArray(); faits.forEach { a.push(it) }; ch.put("V", a) }
            }
            if (faits.size > 1) {
                val idx = p.newArray(); c.options.forEachIndexed { k, o -> if (o in faits) idx.push(k.toFloat()) }
                ch.put("I", idx)
            } else ch.delete("I")
            w.update()
            true
        }
        if (ok) apresValeur(p, nom)
        ok
    }

    /** Date ou heure du moment dans un champ vide qui le demande (comme Acrobat a l'entree du champ). */
    suspend fun valeurAuto(c: InfoChamp): Boolean = operation("Remplir") { p ->
        var nom = ""
        val ok = surPage(p, c.page) { page ->
            val w = page.widgets?.getOrNull(c.index) ?: return@surPage false
            nom = w.name ?: ""
            val r = Regles.lire(w.getObject())
            val auto = r.optString("auto").takeIf { !r.isNull("auto") && it.isNotEmpty() } ?: return@surPage false
            val fmt = Regles.format(r)
            val f = when {
                fmt.optString("genre") == "date" -> fmt.optString("date")
                fmt.optString("genre") == "heure" -> fmt.optString("heure")
                else -> mapOf("date_clic" to "dd/mm/yyyy", "heure_clic" to "HH:MM")[auto] ?: "dd/mm/yyyy HH:MM"
            }
            ecrireValeur(p, w, Regles.ecrireDate(f), r); true
        }
        if (ok) apresValeur(p, nom)
        ok
    }

    private fun messageSaisie(err: String, r: org.json.JSONObject, valeur: String): String {
        val fmt = Regles.format(r)
        return when (err) {
            "nombre" -> Textes.t(R.string.saisie_nombre, valeur)
            "date" -> Textes.t(R.string.saisie_date, fmt.optString("date", "dd/mm/yyyy").let { if (java.util.Locale.getDefault().language == "fr") it.replace("yyyy", "aaaa").replace("dd", "jj") else it })
            "heure" -> Textes.t(R.string.saisie_heure, fmt.optString("heure", "HH:MM"))
            "masque" -> Textes.t(R.string.saisie_masque, fmt.optString("masque"))
            "plage" -> r.optJSONObject("plage")?.let { pl ->
                val a = if (pl.isNull("min")) null else Regles.valeurBrute(pl.optDouble("min"))
                val b = if (pl.isNull("max")) null else Regles.valeurBrute(pl.optDouble("max"))
                when { a != null && b != null -> Textes.t(R.string.saisie_entre, a, b); a != null -> Textes.t(R.string.saisie_min, a)
                    else -> Textes.t(R.string.saisie_max, b) }
            } ?: Textes.t(R.string.saisie_limites)
            "controle" -> when (r.optString("controle")) {
                "email" -> Textes.t(R.string.controle_email); "nir" -> Textes.t(R.string.controle_nir)
                "iban" -> Textes.t(R.string.controle_iban); "siret" -> Textes.t(R.string.controle_siret)
                "rpps" -> Textes.t(R.string.controle_rpps); else -> Textes.t(R.string.saisie_incorrecte) }
            else -> Textes.t(R.string.saisie_incorrecte)
        }
    }

    /** Valeur gardee = brute (comme Acrobat) ; apparence = texte formate (1.234,50 €). */
    private fun ecrireValeur(p: PDFDocument, w: PDFWidget, brut: String, regles: org.json.JSONObject) {
        val aff = Regles.formater(regles, brut)
        w.setTextValue(aff)
        w.update()
        if (aff != brut || brut.isEmpty()) {
            val ch = Regles.champDe(w.getObject())
            if (brut.isEmpty()) ch.delete("V") else ch.put("V", p.newString(brut))
        }
    }

    /** Valeurs de tous les champs (texte brut, choix, « Off » / etat des cases). */
    private fun valeurs(p: PDFDocument): Map<String, String> {
        val out = HashMap<String, String>()
        for (n in 0 until p.countPages()) {
            val pg = p.loadPage(n) as PDFPage
            try { pg.widgets?.forEach { w -> out.putIfAbsent(w.name ?: "", try { w.value ?: "" } catch (_: Exception) { "" }) } } finally { pg.destroy() }
        }
        return out
    }

    /** Une valeur a change : listes dependantes, champs montres / caches, puis calculs (comme Windows). */
    private fun apresValeur(p: PDFDocument, nom: String) {
        if (nom.isEmpty()) return
        val v = valeurs(p)[nom] ?: ""
        for (n in 0 until p.countPages()) surPage(p, n) { page ->
            page.widgets?.forEach { x ->
                val r = try { Regles.lire(x.getObject()) } catch (_: Exception) { return@forEach }
                val dep = r.optJSONObject("depend")
                if (dep != null && dep.optString("parent") == nom) {
                    val l = dep.optJSONObject("listes")?.optJSONArray(v)
                    val items = (0 until (l?.length() ?: 0)).map { l!!.getString(it) }
                    val ch = Regles.champDe(x.getObject())
                    val opt = p.newArray(); items.forEach { opt.push(it) }
                    ch.put("Opt", opt)
                    if ((x.value ?: "") !in items) ch.delete("V")
                    x.update()
                }
                if ((x.name ?: "") == nom) r.optJSONObject("affiche")?.let { a ->
                    val vis = if (a.optString("quand") == "coche") v !in listOf("", "Off") else v == a.optString("valeur")
                    val cibles = a.optJSONArray("cibles") ?: return@let
                    val noms = (0 until cibles.length()).map { cibles.getString(it) }.toSet()
                    for (m in 0 until p.countPages()) surPage(p, m) { pg ->
                        pg.widgets?.forEach { y -> if ((y.name ?: "") in noms) { Regles.afficher(y, vis); y.update() } }
                        true
                    }
                }
            }
            true
        }
        recalculer(p)
    }

    /** Champs calcules, dans l'ordre de calcul (somme, produit, moyenne, min, max, formule, dates). */
    private fun recalculer(p: PDFDocument) {
        val calc = LinkedHashMap<String, org.json.JSONObject>()
        val formats = HashMap<String, String?>()
        for (ch in Regles.tous(p)) {
            val r = try { Regles.lire(ch.obj) } catch (_: Exception) { continue }
            val f = Regles.format(r)
            formats.putIfAbsent(ch.nom, if (f.optString("genre") == "date") f.optString("date") else null)
            if (r.optJSONObject("calcul") != null && ch.nom !in calc) calc[ch.nom] = r
        }
        if (calc.isEmpty()) return
        val deps = calc.mapValues { Regles.sources(it.value.optJSONObject("calcul")).toSet() intersect calc.keys }
        val ordre = ArrayList<String>(); val vus = HashSet<String>()
        fun visiter(n: String, pile: Set<String>) { if (n in vus || n in pile) return; deps[n]?.forEach { visiter(it, pile + n) }; vus += n; ordre += n }
        calc.keys.forEach { visiter(it, emptySet()) }
        for (nm in ordre) {
            val r = calc[nm]!!
            val v = Regles.calculer(r, valeurs(p), formats) ?: continue
            for (n in 0 until p.countPages()) surPage(p, n) { page ->
                page.widgets?.filter { (it.name ?: "") == nm }?.forEach { w -> if ((w.value ?: "") != v) ecrireValeur(p, w, v, r) }
                true
            }
        }
    }

    // ---------------------------------------------------------------- proprietes d'un champ (regles)
    /** Regles du champ, et noms de tous les champs du document (pour calculs, listes dependantes, affichage). */
    suspend fun reglesChamp(c: InfoChamp): Pair<org.json.JSONObject, List<String>> = verrou.withLock {
        withContext(Dispatchers.IO) {
            val p = pdf ?: return@withContext Regles.vide() to emptyList()
            val page = p.loadPage(c.page) as PDFPage
            val r = try { page.widgets?.getOrNull(c.index)?.let { Regles.lire(it.getObject()) } ?: Regles.vide() } finally { page.destroy() }
            r to Regles.tous(p).map { it.nom }.distinct().filter { it.isNotEmpty() && it != c.nom }
        }
    }

    /** Enregistre les regles du champ (et ses choix pour une liste), puis refait le JavaScript du formulaire. */
    suspend fun ecrireReglesChamp(c: InfoChamp, regles: org.json.JSONObject, choix: List<String>?,
                                  prop: ChampsPdf.Proprietes? = null, jsPerso: Map<String, String>? = null): Boolean =
        operation("Propriétés du champ") { p ->
        val ok = surPage(p, c.page) { page ->
            val w = page.widgets?.getOrNull(c.index) ?: return@surPage false
            Regles.ecrire(p, w.getObject(), regles)
            if (choix != null) {
                val opt = p.newArray(); choix.forEach { opt.push(it) }
                Regles.champDe(w.getObject()).put("Opt", opt)
            }
            if (prop != null) ChampsPdf.ecrire(p, w, prop) else w.update()
            if (jsPerso != null) ChampsPdf.poserJsPerso(p, listOf(w), jsPerso)
            // bouton-poussoir : le moteur vient de refaire son apparence a sa facon (bouton blanc) ; on remet la notre
            val o = w.getObject()
            if (o.get("FT").asName() == "Btn" && (o.get("Ff").asInteger() and ChampsPdf.FF_POUSSOIR) != 0) {
                val legende = o.get("MK").get("CA").let { if (it.isString) it.asString() else "" }.ifBlank { w.name ?: "" }
                ChampsPdf.dessinerBouton(p, o, legende)
            }
            true
        }
        if (ok) try { Regles.genererJs(p) } catch (e: Exception) { Journal.ecrire("formulaire", "JavaScript : $e") }
        ok
    }

    /** Reglages du champ (info-bulle, police, case, liste...) et son JavaScript, pour la fenetre des proprietes. */
    suspend fun proprietesChamp(c: InfoChamp): Pair<ChampsPdf.Proprietes, Map<String, Pair<String, String>>>? = verrou.withLock {
        withContext(Dispatchers.IO) {
            val p = pdf ?: return@withContext null
            val page = p.loadPage(c.page) as PDFPage
            try {
                val w = page.widgets?.getOrNull(c.index) ?: return@withContext null
                ChampsPdf.lire(p, w) to ChampsPdf.js(w)
            } catch (e: Exception) { Journal.ecrire("formulaire", "lecture des réglages : $e"); null } finally { page.destroy() }
        }
    }

    /** Bouton d'action (reinitialiser, imprimer, e-mail, aller a une page), comme sous Windows. */
    suspend fun creerBouton(n: Int, rect: Rect, legende: String, action: org.json.JSONObject): Boolean = operation("Bouton") { p ->
        val pris = Regles.tous(p).map { it.nom }.toSet()
        var k = 1
        while ("Bouton$k" in pris) k++
        val r = if (rect.x1 - rect.x0 < 40 || rect.y1 - rect.y0 < 14) Rect(rect.x0, rect.y0, rect.x0 + maxOf(rect.x1 - rect.x0, 110f),
            rect.y0 + maxOf(rect.y1 - rect.y0, 22f)) else rect
        surPage(p, n) { page -> ChampsPdf.creerBouton(p, page, r, "Bouton$k", legende, action) }
        try { Regles.genererJs(p) } catch (e: Exception) { Journal.ecrire("formulaire", "JavaScript : $e") }
        true
    }.also { if (it) pagesVersion++ }

    suspend fun nombrePages(): Int = verrou.withLock { withContext(Dispatchers.IO) { doc.countPages() } }

    /** Champs de la page dans l'ordre de tabulation : (index, nom, cadre). */
    suspend fun ordreChamps(n: Int): List<Triple<Int, String, Rect>> = verrou.withLock {
        withContext(Dispatchers.IO) {
            val page = doc.loadPage(n) as? PDFPage ?: return@withContext emptyList()
            try { ChampsPdf.ordre(page) } finally { page.destroy() }
        }
    }

    suspend fun poserOrdre(n: Int, indices: List<Int>): Boolean = operation("Ordre de tabulation") { p ->
        surPage(p, n) { page -> ChampsPdf.poserOrdre(p, page, indices) }; true
    }

    /** « Reinitialiser » d'un bouton : chaque champ reprend sa valeur par defaut (/DV), sinon vide. */
    suspend fun reinitialiserFormulaire(): Boolean = operation("Réinitialiser le formulaire") { p ->
        for (n in 0 until p.countPages()) surPage(p, n) { page ->
            page.widgets?.forEach { w ->
                try {
                    val o = w.getObject(); val ch = Regles.champDe(o); val dv = ch.get("DV")
                    when (w.fieldType) {
                        PDFWidget.TYPE_CHECKBOX, PDFWidget.TYPE_RADIOBUTTON -> {
                            val e = if (dv.isName) dv.asName() else "Off"
                            ch.put("V", p.newName(e)); o.resolve().put("AS", p.newName(if (o.resolve().get("AP").get("N").get(e).isNull) "Off" else e))
                        }
                        PDFWidget.TYPE_TEXT, PDFWidget.TYPE_COMBOBOX, PDFWidget.TYPE_LISTBOX -> {
                            if (dv.isString) ch.put("V", p.newString(dv.asString())) else ch.delete("V")
                            w.update()
                        }
                    }
                } catch (_: Exception) {}
            }
        }
        true
    }

    // ---------------------------------------------------------------- signature numerique (certificat)
    /** Signe une copie du document (cadre « rect », en points de la page) et renvoie le fichier signe, a enregistrer
     *  tel quel : toute reecriture ulterieure casserait la signature. Le document ouvert n'est pas touche. */
    suspend fun signerNumerique(ctx: Context, n: Int, rect: Rect, signataire: Signataire, raison: String, lieu: String,
                                image: ByteArray?, champ: String? = null): File {
        val dest = File(ctx.cacheDir, "ouverts/signature/" + nom.replace('/', '_'))
        dest.parentFile?.mkdirs()
        // sans modification : le fichier d'origine, octet pour octet (les signatures deja presentes restent valides)
        if (modifie) ecrire(dest) else withContext(Dispatchers.IO) { fichier.copyTo(dest, overwrite = true) }
        return verrou.withLock {
            withContext(Dispatchers.IO) {
                val d2 = Document.openDocument(dest.absolutePath) as? PDFDocument ?: throw ErreurCertificat(Textes.t(R.string.err_pdf_non_modifiable))
                try {
                    if (d2.needsPassword()) motDePasseOuverture?.let { d2.authenticatePassword(it) }
                    champsIndirects(d2)
                    val page = d2.loadPage(n) as PDFPage
                    try {
                        // champ de signature deja pose (vide) : on signe dedans ; sinon un nouveau cadre
                        val w = champ?.let { nm -> page.widgets?.firstOrNull { it.fieldType == PDFWidget.TYPE_SIGNATURE && it.name == nm } }
                            ?: page.createSignature().also { it.setRect(rect) }
                        val img = image?.let { com.artifex.mupdf.fitz.Image(it) }
                        val drapeaux = if (img != null) PDFWidget.SIGNATURE_SHOW_LABELS or PDFWidget.SIGNATURE_SHOW_TEXT_NAME or PDFWidget.SIGNATURE_SHOW_DATE
                            else PDFWidget.SIGNATURE_DEFAULT_APPEARANCE
                        if (!w.sign(signataire, drapeaux, img, raison.ifBlank { null }, lieu.ifBlank { null }))
                            throw ErreurCertificat(Textes.t(R.string.err_signature_refusee))
                        page.update()
                    } finally { page.destroy() }
                    // ajout a la fin du fichier (les signatures precedentes restent valides) ; sinon fichier reecrit
                    try { d2.save(dest.absolutePath, "incremental=yes,compress=yes,compress-images=yes") }
                    catch (e: Exception) {
                        Journal.ecrire("certificat", "enregistrement incrémental impossible ($e) : fichier réécrit")
                        val autre = File(dest.parentFile, "complet-" + dest.name)
                        d2.save(autre.absolutePath, "")
                        autre.copyTo(dest, overwrite = true); autre.delete()
                    }
                } finally { d2.destroy() }
                dest
            }
        }
    }

    /** Champs ecrits « en ligne » dans la page (et recopies a part dans la liste du formulaire) : le moteur signait une
     *  copie, la page en affichait une autre, restee vide. Chaque champ devient un objet unique, partage par la page et
     *  par le formulaire. */
    private fun champsIndirects(d: PDFDocument) {
        // copie neuve d'un objet ecrit en ligne (les objets deja numerotes restent partages)
        fun copie(o: PDFObject): PDFObject = when {
            o.isIndirect -> o
            o.isArray -> d.newArray().also { t -> for (i in 0 until o.size()) t.ajouter(copie(o.get(i))) }
            o.isDictionary -> d.newDictionary().also { t -> for (cle in o) t.put(cle, copie(o.get(cle))) }
            else -> o
        }
        fun nom(o: PDFObject) = try { o.get("T").asString() } catch (_: Exception) { "" }
        val refs = LinkedHashMap<String, PDFObject>()
        for (n in 0 until d.countPages()) {
            val po = d.findPage(n)
            val an = po.get("Annots")
            if (!an.isArray) continue
            var change = false
            val neuf = d.newArray()
            for (i in 0 until an.size()) {
                val a = an.get(i)
                if (!a.isIndirect && a.isDictionary && a.get("Subtype").asName() == "Widget") {
                    val nd = d.newDictionary()
                    for (cle in a) if (cle.asName() != "AP") nd.put(cle, copie(a.get(cle)))   // apparence refaite par le moteur
                    nd.put("P", po)
                    val ref = objetIndirect(d, nd)
                    neuf.ajouter(ref); refs[nom(a)] = ref; change = true
                } else if (a.isIndirect || a.isDictionary) neuf.ajouter(a)
                else change = true                               // debris (texte, null...) laisse par une version precedente
            }
            if (change) po.put("Annots", neuf)
        }
        // liste du formulaire : les copies en ligne remplacees par les champs de la page (une seule fois chacun)
        val af = d.getTrailer().get("Root").get("AcroForm")
        if (!af.isNull) {
            val f = af.get("Fields")
            val neuf = d.newArray()
            val places = HashSet<String>()
            var change = refs.isNotEmpty()
            if (f.isArray) for (i in 0 until f.size()) {
                val c = f.get(i)
                val enLigne = !c.isIndirect && c.isDictionary
                val r = if (enLigne) refs[nom(c)] else null
                when {
                    r != null -> if (places.add(nom(c))) neuf.ajouter(r)
                    // copie en ligne d'un champ qui n'est plus sur aucune page : retiree
                    enLigne && c.get("Subtype").asName() == "Widget" -> change = true
                    else -> neuf.ajouter(c)
                }
            }
            refs.forEach { (k, r) -> if (k !in places) neuf.ajouter(r) }
            if (change) af.put("Fields", neuf)
        }
        // controle : sinon la signature irait encore dans une copie invisible
        for (n in 0 until d.countPages()) {
            val an = d.findPage(n).get("Annots")
            if (an.isArray) for (i in 0 until an.size()) { val a = an.get(i)
                if (!a.isIndirect && a.isDictionary && a.get("Subtype").asName() == "Widget")
                    throw ErreurCertificat(Textes.t(R.string.err_champ_signature)) }
        }
        if (refs.isNotEmpty()) Journal.ecrire("certificat", "${refs.size} champ(s) du formulaire remis en objet unique avant de signer")
    }

    /** Signatures numeriques du document, verifiees (empreinte, certificat approuve, modifications apres). */
    suspend fun signatures(ctx: Context): List<InfoSignature> = verrou.withLock {
        withContext(Dispatchers.IO) {
            val p = pdf ?: return@withContext emptyList()
            val v = Verifieur(Identites.approuvesDer(ctx))
            val out = ArrayList<InfoSignature>()
            try {
                for (n in 0 until p.countPages()) {
                    val page = p.loadPage(n) as PDFPage
                    try {
                        page.widgets?.forEach { w ->
                            if (w.fieldType != PDFWidget.TYPE_SIGNATURE || !w.isSigned) return@forEach
                            // champ ecrit en ligne (PDF signe par une version precedente) : pas verifiable sans risque
                            if (!w.getObject().isIndirect) {
                                out += InfoSignature(n, "?", false, false, false, true, ""); return@forEach
                            }
                            val dig = try { w.checkDigest(v) } catch (_: Throwable) { -1 }
                            v.signataire = null
                            val cer = try { w.checkCertificate(v) } catch (_: Throwable) { -1 }
                            // jamais w.getSignatory / w.getDistinguishedName : avec un verificateur Java, MuPDF appelle une
                            // fonction absente et l'appli plante (le nom est lu ici dans le certificat de la signature)
                            val nomS = v.signataire ?: "?"
                            // jamais w.incrementalChangesSinceSigning : absente de la bibliotheque MuPDF livree (plantage).
                            // Modifie apres la signature : le fichier continue au-dela de la partie signee (ByteRange).
                            val apres = try {
                                val br = w.getObject().get("V").get("ByteRange")
                                fichier.length() > br.get(2).asInteger().toLong() + br.get(3).asInteger().toLong()
                            } catch (_: Throwable) { false }
                            out += InfoSignature(n, nomS, dig == PKCS7Verifier.PKCS7VerifierOK, cer == PKCS7Verifier.PKCS7VerifierOK,
                                cer == PKCS7Verifier.PKCS7VerifierSelfSigned, apres, "")
                        }
                    } finally { page.destroy() }
                }
            } finally { v.destroy() }
            out
        }
    }

    // ---------------------------------------------------------------- creer un formulaire
    /** Zones a remplir reperees sur toutes les pages (rien n'est encore pose). */
    suspend fun detecterChamps(): List<ChampDetecte> = verrou.withLock {
        withContext(Dispatchers.IO) {
            val p = pdf ?: return@withContext emptyList()
            val out = ArrayList<ChampDetecte>()
            for (n in 0 until p.countPages()) {
                val page = p.loadPage(n) as PDFPage
                try { out += Formulaire.detecter(page, n) } catch (e: Exception) { Journal.ecrire("formulaire", "page ${n + 1} : $e") }
                finally { page.destroy() }
            }
            Formulaire.nomsUniques(p, out)
            out
        }
    }

    /** Pose les champs choisis (une seule etape d'annulation). */
    suspend fun creerChamps(champs: List<ChampDetecte>): Boolean = if (champs.isEmpty()) false else operation("Creer des champs") { p ->
        for ((n, l) in champs.groupBy { it.page }) surPage(p, n) { page ->     // champ dessine : nom du libelle voisin
            l.filter { it.nom.isBlank() }.forEach { it.nom = Formulaire.nomAuto(page, it.rect, it.genre == "case") }
        }
        Formulaire.nomsUniques(p, champs)
        // « Signature » : champ de signature ; « Date », « Montant », « Téléphone »... : regles devinees (comme Windows)
        val prets = champs.map { c -> if (c.genre == "texte" && Regles.deviner(c.nom)?.first == "signature") c.copy(genre = "signature") else c }
        for ((n, l) in prets.groupBy { it.page }) surPage(p, n) { page -> l.forEach { Formulaire.creer(p, page, it) } }
        var regles = false
        for ((n, l) in prets.filter { it.genre == "texte" }.groupBy { it.page }) surPage(p, n) { page ->
            val noms = l.associateBy { it.nom }
            page.widgets?.forEach { w -> noms[w.name ?: ""]?.let { c ->
                Regles.deviner(c.nom)?.second?.let { r ->
                    val tout = Regles.vide(); for (k in r.keys()) tout.put(k, r.get(k))
                    Regles.ecrire(p, w.getObject(), tout); regles = true
                }
            } }
            true
        }
        if (regles) try { Regles.genererJs(p) } catch (e: Exception) { Journal.ecrire("formulaire", "JavaScript : $e") }
        // apparence des nouveaux champs (la page relue les connait)
        for (n in champs.map { it.page }.distinct()) surPage(p, n) { page ->
            val noms = champs.filter { it.page == n }.map { it.nom }.toSet()
            page.widgets?.forEach { w -> if (try { w.name } catch (_: Exception) { null } in noms) try { w.update() } catch (_: Exception) {} }
        }
        true
    }

    suspend fun supprimerChamp(c: InfoChamp): Boolean = operation("Supprimer un champ") { p ->
        surPage(p, c.page) { page -> Formulaire.supprimer(p, page, c.index) }
    }

    suspend fun renommerChamp(c: InfoChamp, nom: String): Boolean = operation("Renommer un champ") { p ->
        surPage(p, c.page) { page -> Formulaire.renommer(p, page, c.index, nom) }
    }

    // ---------------------------------------------------------------- signatures, paraphes, tampons
    /** Signature ou paraphe dessines (traits en coordonnees 0..1 d'un cadre largeur x hauteur), poses centres
     *  sur le point, a la largeur voulue (en points). Restent des traits : couleur et epaisseur modifiables. */
    suspend fun poserTraits(n: Int, centre: Point, largeur: Float, ratio: Float, traits: List<List<Pair<Float, Float>>>,
                            couleur: FloatArray, epaisseur: Float): Boolean =
        if (traits.isEmpty()) false else operation("Signature") { p ->
            surPage(p, n) { page ->
                val h = largeur / ratio
                val x0 = centre.x - largeur / 2
                val y0 = centre.y - h / 2
                val an = page.createAnnotation(PDFAnnotation.TYPE_INK)
                an.setInkList(traits.map { t -> t.map { (x, y) -> Point(x0 + x * largeur, y0 + y * h) }.toTypedArray() }.toTypedArray())
                an.setColor(couleur)
                an.setBorderWidth(epaisseur)
                an.update()
                true
            }
        }

    /** Meme paraphe en bas a droite de chaque page. */
    suspend fun parapherTout(largeur: Float, ratio: Float, traits: List<List<Pair<Float, Float>>>, couleur: FloatArray,
                             epaisseur: Float, tailles: List<Pair<Float, Float>>): Boolean =
        operation("Parapher") { p ->
            for (n in tailles.indices) {
                val (w, h) = tailles[n]
                val hh = largeur / ratio
                surPage(p, n) { page ->
                    val x0 = w - 30f - largeur
                    val y0 = h - 30f - hh
                    val an = page.createAnnotation(PDFAnnotation.TYPE_INK)
                    an.setInkList(traits.map { t -> t.map { (x, y) -> Point(x0 + x * largeur, y0 + y * hh) }.toTypedArray() }.toTypedArray())
                    an.setColor(couleur)
                    an.setBorderWidth(epaisseur)
                    an.update()
                }
            }
            tailles.isNotEmpty()
        }

    /** Tampon (texte encadre : « RECU LE 30/10/2026 », « PAYE »...) centre sur le point. */
    suspend fun tampon(n: Int, centre: Point, texte: String, couleur: FloatArray, taille: Float): Boolean =
        operation("Tampon") { p ->
            surPage(p, n) { page ->
                val lignes = texte.split("\n")
                val l = (lignes.maxOf { it.length } * taille * 0.62f) + 16f
                val h = lignes.size * taille * 1.25f + 12f
                val an = page.createAnnotation(PDFAnnotation.TYPE_FREE_TEXT)
                an.setRect(Rect(centre.x - l / 2, centre.y - h / 2, centre.x + l / 2, centre.y + h / 2))
                an.setContents(texte)
                an.setDefaultAppearance("Helv", taille, couleur)   // texte de la couleur choisie
                try { an.setQuadding(1) } catch (_: Exception) {}  // centre (« VALIDE » seul ou avec sa date)
                an.setColor(floatArrayOf())                        // fond transparent (pas de cadre plein)
                an.setBorderWidth(2f)                              // cadre fin, de la couleur du texte
                an.update()
                true
            }
        }

    /** Signature ou tampon de PhilPDF Windows (image transparente) centre sur le point, a la largeur voulue. */
    suspend fun image(n: Int, centre: Point, largeur: Float, ratio: Float, png: ByteArray): Boolean =
        operation("Signature") { p ->
            surPage(p, n) { page ->
                val h = largeur / ratio.coerceAtLeast(0.05f)
                val an = page.createAnnotation(PDFAnnotation.TYPE_STAMP)
                an.setRect(Rect(centre.x - largeur / 2, centre.y - h / 2, centre.x + largeur / 2, centre.y + h / 2))
                an.setStampImage(com.artifex.mupdf.fitz.Image(png))
                an.update()
                true
            }
        }

    /** Paraphe de vos postes (image) en bas a droite de chaque page, en une seule etape d'annulation. */
    suspend fun imageToutesPages(largeur: Float, ratio: Float, png: ByteArray, tailles: List<Pair<Float, Float>>): Boolean =
        operation("Parapher") { p ->
            val img = com.artifex.mupdf.fitz.Image(png)
            val h = largeur / ratio.coerceAtLeast(0.05f)
            for (n in tailles.indices) surPage(p, n) { page ->
                val (w, hp) = tailles[n]
                val an = page.createAnnotation(PDFAnnotation.TYPE_STAMP)
                an.setRect(Rect(w - 30f - largeur, hp - 30f - h, w - 30f, hp - 30f))
                an.setStampImage(img)
                an.update()
            }
            tailles.isNotEmpty()
        }

    /** Gomme : retire les annotations touchees par le doigt (un toucher ou un trait), en une etape. */
    suspend fun supprimerAnnotationsSur(n: Int, pts: List<Point>): Int {
        var k = 0
        operation("Gomme") { p ->
            surPage(p, n) { page ->
                val l = page.annotations ?: emptyArray()
                val touchees = l.filter { an ->
                    val t = an.type
                    t != PDFAnnotation.TYPE_LINK && t != PDFAnnotation.TYPE_WIDGET && t != PDFAnnotation.TYPE_POPUP &&
                        an.bounds.let { r -> pts.any { a -> a.x >= r.x0 - 6 && a.x <= r.x1 + 6 && a.y >= r.y0 - 6 && a.y <= r.y1 + 6 } }
                }
                touchees.forEach { page.deleteAnnotation(it) }
                k = touchees.size
                k > 0
            }
        }
        return k
    }

    /** Effacer le contenu de la page dans la zone (texte, images, traits), comme la retouche « effacer » de Windows. */
    suspend fun effacerZone(n: Int, r: Rect): Boolean = operation("Effacer") { p ->
        surPage(p, n) { page ->
            val an = page.createAnnotation(PDFAnnotation.TYPE_REDACT)
            an.setRect(r)
            an.update()
            page.applyRedactions(false, PDFPage.REDACT_IMAGE_PIXELS, PDFPage.REDACT_LINE_ART_REMOVE_IF_COVERED, PDFPage.REDACT_TEXT_REMOVE)
        }
    }

    /** Champs de la page (pour les montrer en bleu clair, comme Acrobat) : rectangle, genre, signe ou non. */
    suspend fun zonesChamps(n: Int): List<Triple<FloatArray, Int, Boolean>> = verrou.withLock {
        withContext(Dispatchers.IO) {
            val page = doc.loadPage(n) as? PDFPage ?: return@withContext emptyList()
            try {
                (page.widgets ?: emptyArray()).map { w ->
                    val r = w.bounds
                    Triple(floatArrayOf(r.x0, r.y0, r.x1, r.y1), w.fieldType,
                        w.fieldType == PDFWidget.TYPE_SIGNATURE && (try { w.isSigned } catch (_: Exception) { false }))
                }
            } catch (_: Exception) { emptyList() } finally { page.destroy() }
        }
    }

    /** Etat actuel du document ecrit dans un fichier (pour enregistrer, partager, imprimer). */
    suspend fun ecrire(dest: File): File = verrou.withLock {
        withContext(Dispatchers.IO) {
            dest.parentFile?.mkdirs()
            val p = pdf
            if (p != null && modifie) {
                // le document ouvert est ecrit tel quel (sans « garbage », qui renumerote ses objets en memoire et
                // derangeait la suite : modifications invisibles), puis la copie est nettoyee, allegee, protegee
                val brut = File(dest.parentFile, dest.name + ".brut")
                p.save(brut.absolutePath, "decrypt=yes")
                val copie = Document.openDocument(brut.absolutePath) as PDFDocument
                try { copie.save(dest.absolutePath, optionsEcriture()) } finally { copie.destroy(); brut.delete() }
            } else fichier.copyTo(dest, overwrite = true)
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
                ?: throw IllegalStateException(Textes.t(R.string.err_ecriture))
        }
        Distants.renvoyer(ctx, cible)        // copie d'un fichier OneDrive, Dropbox, Box... : renvoyee a sa place
        modifie = false
    }

    fun besoinMotDePasse(): Boolean = doc.needsPassword()
    /** Mot de passe tape a l'ouverture (garde en memoire seulement) : le PDF reste protege a l'enregistrement. */
    private var motDePasseOuverture: String? = null
    fun motDePasse(m: String): Boolean = doc.authenticatePassword(m).also { if (it) motDePasseOuverture = m }
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

    // ---------------------------------------------------------------- reconnaissance du texte (OCR)
    /** Vrai si la page n'a aucun texte (page scannee : une image). */
    suspend fun pageSansTexte(n: Int): Boolean = verrou.withLock {
        withContext(Dispatchers.IO) {
            val pg = doc.loadPage(n)
            try { val st = pg.toStructuredText(); try { st.asText().isBlank() } finally { st.destroy() } }
            catch (_: Exception) { false } finally { pg.destroy() }
        }
    }

    /** Images et lignes de texte de la page (repere de la page) : pour savoir ou chercher du texte dans les images. */
    data class ContenuPage(val images: List<Rect>, val lignes: List<Rect>)

    private fun contenuSansVerrou(n: Int): ContenuPage {
        val images = ArrayList<Rect>(); val lignes = ArrayList<Rect>()
        val pg = doc.loadPage(n)
        try {
            val st = pg.toStructuredText("preserve-images")
            try {
                st.walk(object : com.artifex.mupdf.fitz.StructuredTextWalker {
                    override fun onImageBlock(bbox: Rect?, transform: Matrix?, image: com.artifex.mupdf.fitz.Image?) { bbox?.let { images += Rect(it) } }
                    override fun beginTextBlock(bbox: Rect?, flags: Int) {}
                    override fun endTextBlock() {}
                    override fun beginLine(bbox: Rect?, wmode: Int, dir: Point?) { bbox?.let { lignes += Rect(it) } }
                    override fun endLine() {}
                    override fun onChar(c: Int, origin: Point?, font: com.artifex.mupdf.fitz.Font?, size: Float, q: com.artifex.mupdf.fitz.Quad?, argb: Int, flags: Int, bidi: Int) {}
                    override fun beginStruct(standard: String?, raw: String?, index: Int) {}
                    override fun endStruct() {}
                    override fun onVector(bbox: Rect?, info: com.artifex.mupdf.fitz.StructuredTextWalker.VectorInfo?, argb: Int) {}
                })
            } finally { st.destroy() }
        } catch (e: Exception) { Journal.ecrire("ocr", "lecture de la page ${n + 1} : $e") } finally { pg.destroy() }
        return ContenuPage(images, lignes)
    }

    /** Vrai si le texte peut etre reconnu ici : page sans texte, ou point sur une image. */
    suspend fun ocrPossible(n: Int, a: Point): Boolean = verrou.withLock {
        withContext(Dispatchers.IO) {
            val c = contenuSansVerrou(n)
            c.lignes.isEmpty() || c.images.any { a.x >= it.x0 && a.x <= it.x1 && a.y >= it.y0 && a.y <= it.y1 }
        }
    }

    /** Resultat d'une reconnaissance : pages traitees, mots poses, pages laissees (sans image a lire). */
    data class ResultatOcr(val pages: Int, val mots: Int, val ignorees: Int)

    /** Reconnait le texte des pages (null : toutes) : pages scannees entieres, ou texte dans les images d'une page qui a
     *  deja du texte (sans doubler celui-ci). tourne : cherche aussi le texte couche ou a l'envers (plus lent). Le texte
     *  est pose invisible (une seule etape d'annulation). avance(fait, total) pour la barre de progression. */
    suspend fun reconnaitre(ctx: Context, pages: List<Int>?, langues: String = "fra", tourne: Boolean = false,
                            avance: (Int, Int) -> Unit): ResultatOcr {
        if (pdf == null) return ResultatOcr(0, 0, 0)
        val liste = pages ?: (0 until verrou.withLock { withContext(Dispatchers.IO) { doc.countPages() } }).toList()
        val resultats = LinkedHashMap<Int, List<Ocr.Mot>>()
        var ignorees = 0
        fun aire(x0: Float, y0: Float, x1: Float, y1: Float) = ((x1 - x0).coerceAtLeast(0f)) * ((y1 - y0).coerceAtLeast(0f))
        fun recouvre(m: Ocr.Mot, x0: Float, y0: Float, x1: Float, y1: Float): Boolean {
            val i = aire(maxOf(m.x0, x0), maxOf(m.y0, y0), minOf(m.x1, x1), minOf(m.y1, y1))
            return i > 0.3f * aire(m.x0, m.y0, m.x1, m.y1).coerceAtLeast(0.01f)
        }
        val passes = if (tourne) listOf(0, 180, 90, 270) else listOf(0)
        for ((i, n) in liste.withIndex()) {
            avance(i, liste.size)
            val z = 200f / 72f                                   // 200 points par pouce : bon pour Tesseract, memoire raisonnable
            val (contenu, bm) = verrou.withLock {
                withContext(Dispatchers.IO) {
                    val c = contenuSansVerrou(n)
                    if (c.lignes.isNotEmpty() && c.images.isEmpty()) return@withContext c to null   // deja du texte, aucune image
                    val pg = doc.loadPage(n)
                    try {
                        val b = pg.bounds
                        val w = ((b.x1 - b.x0) * z).toInt().coerceIn(1, 4000); val h = ((b.y1 - b.y0) * z).toInt().coerceIn(1, 5600)
                        val bm = Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888)
                        bm.eraseColor(Color.WHITE)
                        val dev = AndroidDrawDevice(bm, 0, 0)
                        try { pg.run(dev, Matrix(z, z), null as Cookie?); dev.close() } finally { dev.destroy() }
                        c to bm
                    } finally { pg.destroy() }
                }
            }
            if (bm == null) { ignorees++; continue }
            val scan = contenu.lignes.isEmpty()                  // page entierement scannee
            val gardes = ArrayList<Ocr.Mot>()
            try {
                // toutes les lectures (a l'endroit, a l'envers, couchees), puis, a chaque endroit, la plus sure : un
                // texte a l'envers lu a l'endroit donne du charabia peu sur (« NOISSIN »), lu tourne il est net
                val candidats = ArrayList<Ocr.Mot>()
                for (r in passes) {
                    val trouves = withContext(Dispatchers.Default) { Ocr.mots(ctx, bm, langues, r) }.map { it.echelle(1f / z) }
                    val seuil = if (r != 0) 70f else if (scan) 25f else 50f   // tourne : seulement les mots surs
                    for (m in trouves) {
                        if (m.confiance < seuil) continue
                        if (!scan) {
                            val cx = (m.x0 + m.x1) / 2; val cy = (m.y0 + m.y1) / 2
                            if (contenu.images.none { cx >= it.x0 && cx <= it.x1 && cy >= it.y0 && cy <= it.y1 }) continue
                            if (contenu.lignes.any { recouvre(m, it.x0, it.y0, it.x1, it.y1) }) continue   // deja du vrai texte
                        }
                        candidats += m
                    }
                }
                for (m in candidats.sortedByDescending { it.confiance }) {
                    if (gardes.any { g -> recouvre(m, g.x0, g.y0, g.x1, g.y1) || recouvre(g, m.x0, m.y0, m.x1, m.y1) }) continue
                    gardes += m
                }
            } finally { bm.recycle() }
            resultats[n] = gardes
            Journal.ecrire("ocr", "$nom, page ${n + 1} : ${gardes.size} mots reconnus" + if (tourne) " (texte tourné cherché)" else "")
        }
        avance(liste.size, liste.size)
        val utiles = resultats.filterValues { it.isNotEmpty() }
        if (utiles.isNotEmpty()) operation("Reconnaître le texte") { d ->
            for ((n, m) in utiles) { val pg = d.loadPage(n) as PDFPage; try { Ocr.poser(d, pg, m) } finally { pg.destroy() } }
            true
        }
        return ResultatOcr(utiles.size, utiles.values.sumOf { it.size }, ignorees)
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
            } catch (e: Exception) {
                // page en partie illisible : on garde ce qui a ete dessine, et on le note (une fois par page)
                if (erreursRendu.add("$n-$version")) Journal.ecrire("affichage", "$nom, page ${n + 1} : $e")
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
            } ?: throw IllegalStateException(Textes.t(R.string.err_lecture))
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
                     val epaisseur: Float, val texte: String, val rect: FloatArray = floatArrayOf(0f, 0f, 0f, 0f)) {
    /** Signature, paraphe ou tampon (image, texte encadre ou trace) : deplacable, redimensionnable, remplacable. */
    val objet: Boolean get() = genre == PDFAnnotation.TYPE_STAMP || genre == PDFAnnotation.TYPE_FREE_TEXT || genre == PDFAnnotation.TYPE_INK
}
data class InfoChamp(val page: Int, val index: Int, val genre: Int, val valeur: String, val options: List<String>,
                     val lectureSeule: Boolean, val nom: String = "", val regles: String = "",
                     /** liste deroulante ou l'on peut aussi taper sa propre valeur (« saisie libre ») */
                     val libre: Boolean = false,
                     /** liste ouverte a plusieurs choix, et les choix faits */
                     val plusieurs: Boolean = false, val choisis: List<String> = emptyList())
