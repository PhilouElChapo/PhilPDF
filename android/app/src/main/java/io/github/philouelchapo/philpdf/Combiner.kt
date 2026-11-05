package io.github.philouelchapo.philpdf

import android.content.Context
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.artifex.mupdf.fitz.Document
import com.artifex.mupdf.fitz.Image
import com.artifex.mupdf.fitz.PDFDocument
import com.artifex.mupdf.fitz.Rect
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File

/**
 * Combiner des fichiers, comme sous Windows (Fichier > Creer un PDF > A partir de plusieurs fichiers) : des PDF et des
 * images, dans l'ordre voulu, avec des pages vierges intercalees, assembles dans un nouveau PDF.
 */
object Combiner {
    sealed class Element {
        class Fichier(val uri: Uri, val nom: String, val image: Boolean) : Element()
        object PageVierge : Element()
    }

    fun estImage(ctx: Context, u: Uri, nom: String): Boolean {
        val t = try { ctx.contentResolver.getType(u) } catch (_: Exception) { null } ?: ""
        return t.startsWith("image/") || Regex("(?i)\\.(jpe?g|png|webp|gif|bmp|heic)$").containsMatchIn(nom)
    }

    /** Copie locale d'un fichier choisi (les PDF des comptes et du telephone se lisent ainsi tous de la meme facon). */
    fun copie(ctx: Context, u: Uri, nom: String): File {
        val f = File(ctx.cacheDir, "ouverts/combiner/" + System.nanoTime() + "_" + nom.replace('/', '_'))
        f.parentFile?.mkdirs()
        ctx.contentResolver.openInputStream(u)?.use { e -> f.outputStream().use { e.copyTo(it) } }
            ?: throw IllegalStateException(Textes.t(R.string.err_lecture))
        return f
    }

    /** Pages d'une image : une page, largeur A4, hauteur selon l'image. */
    fun ajouterImage(pdf: PDFDocument, octets: ByteArray, a: Int) {
        val img = Image(octets)
        val w = 595f
        val h = (w * img.height / img.width.coerceAtLeast(1)).coerceIn(10f, 2000f)
        val res = pdf.newDictionary()
        val xo = pdf.newDictionary()
        xo.put("Im0", pdf.addImage(img))
        res.put("XObject", xo)
        pdf.insertPage(a, pdf.addPage(Rect(0f, 0f, w, h), 0, res, "q $w 0 0 $h 0 0 cm /Im0 Do Q"))
    }

    /** Ajoute un fichier (PDF ou image) a la place « a » ; renvoie le nombre de pages ajoutees (0 : illisible). */
    fun ajouterFichier(pdf: PDFDocument, f: File, image: Boolean, a: Int): Int {
        if (image) { ajouterImage(pdf, f.readBytes(), a); return 1 }
        val src = Document.openDocument(f.absolutePath) as? PDFDocument ?: return 0
        try {
            if (src.needsPassword()) return 0
            for (i in 0 until src.countPages()) pdf.graftPage(a + i, src, i)
            return src.countPages()
        } finally { src.destroy() }
    }

    /**
     * Assemble les elements dans dest ; progression(i, n). Renvoie les noms illisibles (laisses de cote).
     * Format de la page vierge : celui de la page precedente (A4 au debut).
     */
    fun fabriquer(ctx: Context, elements: List<Element>, dest: File, progression: (Int, Int) -> Unit): List<String> {
        val illisibles = ArrayList<String>()
        val pdf = PDFDocument()
        try {
            elements.forEachIndexed { k, e ->
                progression(k, elements.size)
                when (e) {
                    is Element.PageVierge -> {
                        val n = pdf.countPages()
                        val (w, h) = if (n > 0) pdf.loadPage(n - 1).let { p -> try { p.bounds.let { (it.x1 - it.x0) to (it.y1 - it.y0) } } finally { p.destroy() } } else 595f to 842f
                        pdf.insertPage(n, pdf.addPage(Rect(0f, 0f, w, h), 0, pdf.newDictionary(), ""))
                    }
                    is Element.Fichier -> {
                        val ok = try { ajouterFichier(pdf, copie(ctx, e.uri, e.nom), e.image, pdf.countPages()) > 0 }
                        catch (x: Exception) { Journal.ecrire("combiner", "${e.nom} : $x"); false }
                        if (!ok) illisibles += e.nom
                    }
                }
            }
            if (pdf.countPages() == 0) throw IllegalStateException(Textes.t(R.string.combiner_rien))
            dest.parentFile?.mkdirs()
            pdf.save(dest.absolutePath, "garbage=compact")
        } finally { pdf.destroy() }
        return illisibles
    }
}

/** Ecran « Combiner des fichiers » (Accueil). */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun EcranCombiner(fermer: () -> Unit, ouvrirPdf: (File) -> Unit) {
    val ctx = LocalContext.current
    val portee = rememberCoroutineScope()
    val liste = remember { mutableStateListOf<Combiner.Element>() }
    var occupe by remember { mutableStateOf<String?>(null) }
    var message by remember { mutableStateOf<String?>(null) }
    var numeriser by remember { mutableStateOf(false) }
    val choix = rememberLauncherForActivityResult(ActivityResultContracts.OpenMultipleDocuments()) { l ->
        l.forEach { u ->
            val nom = try { nomDuFichier(ctx, u) } catch (_: Exception) { u.lastPathSegment ?: "?" }
            liste += Combiner.Element.Fichier(u, nom, Combiner.estImage(ctx, u, nom))
        }
    }
    LaunchedEffect(Unit) { choix.launch(arrayOf("application/pdf", "image/*")) }
    Fenetre(fermer) {
        Surface(Modifier.fillMaxSize(), color = Color(0xFFF3F3F3)) {
            Column(Modifier.fillMaxSize()) {
                Row(Modifier.fillMaxWidth().background(Color.White).padding(horizontal = 4.dp, vertical = 2.dp),
                    verticalAlignment = Alignment.CenterVertically) {
                    IconButton(onClick = fermer) { Icon(Icons.AutoMirrored.Filled.ArrowBack, stringResource(R.string.retour)) }
                    Column(Modifier.weight(1f)) {
                        TexteAjuste(stringResource(R.string.combiner_titre), 17.sp)
                        Text(stringResource(R.string.combiner_aide), fontSize = 12.sp, color = Color.Gray, maxLines = 3)
                    }
                }
                HorizontalDivider(color = Color(0xFFE2E2E2))
                Box(Modifier.weight(1f).fillMaxWidth()) {
                    if (liste.isEmpty()) Text(stringResource(R.string.combiner_vide), Modifier.align(Alignment.Center).padding(24.dp), color = Color.Gray)
                    LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(10.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        itemsIndexed(liste, key = { _, e -> System.identityHashCode(e) }) { i, e ->
                            Row(Modifier.fillMaxWidth().background(Color.White, RoundedCornerShape(8.dp)).padding(start = 10.dp),
                                verticalAlignment = Alignment.CenterVertically) {
                                val (ic, nom) = when (e) {
                                    is Combiner.Element.PageVierge -> "creer" to stringResource(R.string.page_blanche)
                                    is Combiner.Element.Fichier -> (if (e.image) "image" else "combiner") to e.nom
                                }
                                Icon(Icones.get(ic, ROUGE), null, tint = Color.Unspecified)
                                Spacer(Modifier.width(8.dp))
                                Text("${i + 1}. $nom", Modifier.weight(1f), fontSize = 14.sp, maxLines = 2, overflow = TextOverflow.Ellipsis)
                                TextButton(onClick = { liste.removeAt(i); liste.add(i - 1, e) }, enabled = i > 0, contentPadding = PaddingValues(4.dp)) { Text("↑") }
                                TextButton(onClick = { liste.removeAt(i); liste.add(i + 1, e) }, enabled = i < liste.size - 1, contentPadding = PaddingValues(4.dp)) { Text("↓") }
                                TextButton(onClick = { liste.removeAt(i) }, contentPadding = PaddingValues(4.dp)) { Text("✕", color = Color(0xFFC62828)) }
                            }
                        }
                    }
                    occupe?.let { o ->
                        Column(Modifier.align(Alignment.Center).background(Color(0xEEFFFFFF), RoundedCornerShape(12.dp)).padding(20.dp),
                            horizontalAlignment = Alignment.CenterHorizontally) {
                            CircularProgressIndicator(); Spacer(Modifier.height(8.dp)); Text(o, fontSize = 14.sp)
                        }
                    }
                }
                FlowRow(Modifier.fillMaxWidth().background(Color.White).padding(6.dp),
                    horizontalArrangement = Arrangement.spacedBy(8.dp, Alignment.CenterHorizontally)) {
                    OutlinedButton(onClick = { choix.launch(arrayOf("application/pdf", "image/*")) }, enabled = occupe == null) {
                        Text(stringResource(R.string.combiner_ajouter))
                    }
                    OutlinedButton(onClick = { numeriser = true }, enabled = occupe == null) {
                        Text(stringResource(R.string.accueil_numeriser))
                    }
                    OutlinedButton(onClick = { liste += Combiner.Element.PageVierge }, enabled = occupe == null) {
                        Text("+ " + stringResource(R.string.page_blanche))
                    }
                    Button(onClick = {
                        val l = liste.toList()
                        occupe = ctx.getString(R.string.combiner_en_cours)
                        portee.launch {
                            try {
                                val f = File(ctx.cacheDir, "ouverts/combiner/" + System.currentTimeMillis() + "/" + ctx.getString(R.string.combiner_nom) + ".pdf")
                                val illisibles = withContext(Dispatchers.IO) {
                                    Combiner.fabriquer(ctx, l, f) { i, n -> occupe = ctx.getString(R.string.combiner_progression, i + 1, n) }
                                }
                                Journal.ecrire("combiner", "${l.size} élément(s), ${illisibles.size} illisible(s)")
                                occupe = null
                                if (illisibles.isNotEmpty()) Toast(ctx, ctx.getString(R.string.combiner_illisibles, illisibles.joinToString(", ")))
                                ouvrirPdf(f)
                            } catch (e: Exception) {
                                occupe = null; message = e.message ?: e.toString()
                            }
                        }
                    }, enabled = liste.any { it is Combiner.Element.Fichier } && occupe == null,
                        colors = ButtonDefaults.buttonColors(containerColor = ROUGE)) { Text(stringResource(R.string.combiner_bouton)) }
                }
            }
        }
    }
    if (numeriser) EcranNumerisation(fermer = { numeriser = false }) { f ->
        numeriser = false
        liste += Combiner.Element.Fichier(android.net.Uri.fromFile(f), f.name, false)
    }
    message?.let { m ->
        AlertDialog(onDismissRequest = { message = null }, text = { Text(m) },
            confirmButton = { TextButton(onClick = { message = null }) { Text(stringResource(R.string.ok)) } })
    }
}

private fun Toast(ctx: Context, t: String) = android.widget.Toast.makeText(ctx, t, android.widget.Toast.LENGTH_LONG).show()
