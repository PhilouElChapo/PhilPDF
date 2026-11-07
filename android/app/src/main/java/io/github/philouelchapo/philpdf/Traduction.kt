package io.github.philouelchapo.philpdf

import android.content.Context
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.artifex.mupdf.fitz.Document
import com.artifex.mupdf.fitz.Font
import com.artifex.mupdf.fitz.Image
import com.artifex.mupdf.fitz.Matrix
import com.artifex.mupdf.fitz.PDFAnnotation
import com.artifex.mupdf.fitz.PDFDocument
import com.artifex.mupdf.fitz.PDFPage
import com.artifex.mupdf.fitz.Point
import com.artifex.mupdf.fitz.Quad
import com.artifex.mupdf.fitz.Rect
import com.artifex.mupdf.fitz.StructuredTextWalker
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

/** Traduire le document en gardant la mise en page, comme sous Windows (moteur/traduire.py) : chaque paragraphe
 *  est traduit par l'IA (par lots), le texte d'origine retire (images et dessins gardes), la traduction posee dans le
 *  meme cadre, plus petite si elle est plus longue. Le resultat est un NOUVEAU fichier « nom (EN).pdf ». */
object Traduction {
    data class Bloc(val page: Int, val r: Rect, val texte: String, val taille: Float, val argb: Int, val gras: Boolean)

    const val CONSIGNES = "Tu traduis les textes d'un document PDF en %s. On te donne un objet JSON {\"textes\": [...]} ; " +
        "réponds par {\"textes\": [...]} avec exactement le même nombre d'éléments, dans le même ordre, chacun traduit. " +
        "Garde les nombres, montants, dates, références, noms propres et adresses tels quels (adapte seulement le format " +
        "si c'est l'usage dans la langue cible). Traduction fidèle et naturelle, registre du document, sans commentaire."

    /** Paragraphes a traduire (les nombres, dates et codes seuls sont laisses tels quels). */
    fun blocs(pdf: PDFDocument): List<Bloc> {
        val out = ArrayList<Bloc>()
        for (n in 0 until pdf.countPages()) {
            val page = pdf.loadPage(n) as PDFPage
            try {
                val st = page.toStructuredText()
                var lignes = ArrayList<String>(); var ligne = StringBuilder()
                var r: Rect? = null; val tailles = ArrayList<Float>(); var argb = 0; var gras = false; var premier = true
                st.walk(object : StructuredTextWalker {
                    override fun onImageBlock(bbox: Rect?, transform: Matrix?, image: Image?) {}
                    override fun beginTextBlock(bbox: Rect?, flags: Int) {
                        lignes = ArrayList(); r = bbox?.let { Rect(it.x0, it.y0, it.x1, it.y1) }; tailles.clear(); premier = true
                    }
                    override fun endTextBlock() {
                        val texte = lignes.fold("") { acc, t -> if (acc.endsWith("-") && t.firstOrNull()?.isLowerCase() == true) acc.dropLast(1) + t else (acc + " " + t).trim() }
                        val b = r
                        if (b != null && Regex("[\\p{L}]{2,}").containsMatchIn(texte))
                            out += Bloc(n, b, texte, tailles.sorted().getOrElse(tailles.size / 2) { 10f }, argb, gras)
                    }
                    override fun beginLine(bbox: Rect?, wmode: Int, dir: Point?) { ligne = StringBuilder() }
                    override fun endLine() { ligne.toString().trim().takeIf { it.isNotEmpty() }?.let { lignes += it } }
                    override fun onChar(c: Int, origin: Point?, font: Font?, size: Float, q: Quad?, argb_: Int, flags: Int, bidi: Int) {
                        ligne.appendCodePoint(c)
                        if (c > 32) {
                            tailles += size
                            if (premier) { argb = argb_; gras = font?.isBold == true || font?.name?.contains("Bold", true) == true; premier = false }
                        }
                    }
                    override fun beginStruct(standard: String?, raw: String?, index: Int) {}
                    override fun endStruct() {}
                    override fun onVector(bbox: Rect?, info: StructuredTextWalker.VectorInfo?, argb_: Int) {}
                })
                st.destroy()
            } finally { page.destroy() }
        }
        return out
    }

    fun lots(textes: List<String>, maxCar: Int = 6000): List<List<Int>> {
        val out = ArrayList<List<Int>>(); var lot = ArrayList<Int>(); var n = 0
        textes.forEachIndexed { i, t -> if (lot.isNotEmpty() && n + t.length > maxCar) { out += lot; lot = ArrayList(); n = 0 }; lot += i; n += t.length }
        if (lot.isNotEmpty()) out += lot
        return out
    }

    /** Lignes du texte a la largeur donnee. */
    private fun couper(fonte: Font, t: String, taille: Float, largeur: Float): List<String> {
        val out = ArrayList<String>(); var cour = ""
        for (mot in t.split(Regex("\\s+")).filter { it.isNotEmpty() }) {
            val essai = if (cour.isEmpty()) mot else "$cour $mot"
            if (cour.isNotEmpty() && Pagination.largeur(fonte, essai, taille) > largeur) { out += cour; cour = mot } else cour = essai
        }
        if (cour.isNotEmpty()) out += cour
        return out
    }

    /** Remplace le texte de chaque paragraphe par sa traduction ; renvoie le nombre de paragraphes traduits. */
    fun appliquer(pdf: PDFDocument, blocs: List<Bloc>, trad: List<String>): Int {
        val normal = Font("Helvetica"); val gras = Font("Helvetica-Bold")
        val oN = pdf.addSimpleFont(normal, Font.SIMPLE_ENCODING_LATIN); val oG = pdf.addSimpleFont(gras, Font.SIMPLE_ENCODING_LATIN)
        var n = 0
        for ((p, liste) in blocs.indices.filter { trad[it].isNotBlank() && trad[it].trim() != blocs[it].texte }.groupBy { blocs[it].page }) {
            val page = pdf.loadPage(p) as PDFPage
            try {
                for (i in liste) {
                    val an = page.createAnnotation(PDFAnnotation.TYPE_REDACT); an.setRect(blocs[i].r); an.update()
                }
                page.applyRedactions(false, PDFPage.REDACT_IMAGE_NONE, PDFPage.REDACT_LINE_ART_NONE, PDFPage.REDACT_TEXT_REMOVE)
                val res = Pagination.ressources(pdf, page)
                val fonts = Pagination.dico(pdf, res, "Font")
                val nN = Pagination.nom(fonts, "PhilT"); fonts.put(nN, oN)
                val nG = Pagination.nom(fonts, "PhilT"); fonts.put(nG, oG)
                val sb = StringBuilder("q\n")
                for (i in liste) {
                    val b = blocs[i]; val f = if (b.gras) gras else normal
                    val larg = b.r.x1 - b.r.x0 + 2f; val haut = b.r.y1 - b.r.y0
                    var k = 1f; var lignes: List<String>
                    // plus petite si la traduction est plus longue, pour tenir dans le cadre (jusqu'a 50 %)
                    while (true) {
                        lignes = couper(f, trad[i].trim(), b.taille * k, larg)
                        if (lignes.size * b.taille * k * 1.15f <= haut + b.taille * 0.3f || k <= 0.5f) break
                        k -= 0.05f
                    }
                    val t = b.taille * k
                    sb.append(Pagination.rgb(b.argb and 0xFFFFFF)).append('\n')
                    lignes.forEachIndexed { j, l -> sb.append(Pagination.texte(page, if (b.gras) nG else nN, t, b.r.x0, b.r.y0 + t * 0.85f + j * t * 1.15f, 0f, l)) }
                    n++
                }
                sb.append("Q\n")
                Pagination.ajouterFlux(pdf, page, sb.toString())
                page.update()
            } finally { page.destroy() }
        }
        return n
    }

    /** Langues proposees (alphabet latin : la police de PhilPDF Android n'a pas les autres). */
    val LANGUES = listOf("EN" to R.string.trad_en, "ES" to R.string.trad_es, "IT" to R.string.trad_it, "DE" to R.string.trad_de,
        "PT" to R.string.trad_pt, "NL" to R.string.trad_nl, "FR" to R.string.trad_fr)
    /** Nom de la langue, en francais, pour la consigne. */
    val POUR_IA = mapOf("EN" to "anglais", "ES" to "espagnol", "IT" to "italien", "DE" to "allemand", "PT" to "portugais",
        "NL" to "néerlandais", "FR" to "français")

    /** Traduit tout ; avance(lot, lots). Renvoie le nouveau fichier. */
    suspend fun traduire(ctx: Context, source: File, nom: String, code: String, langue: String, avance: (Int, Int) -> Unit): File =
        withContext(Dispatchers.IO) {
            val pdf = Document.openDocument(source.absolutePath) as PDFDocument
            try {
                val bs = blocs(pdf)
                val textes = bs.map { it.texte }
                val trad = textes.toMutableList()
                val ls = lots(textes)
                ls.forEachIndexed { k, lot ->
                    avance(k + 1, ls.size)
                    val r = Ia.lireJson(Ia.demander(ctx, CONSIGNES.format(langue),
                        JSONObject().put("textes", JSONArray(lot.map { textes[it] })).toString(), json = true, maxJetons = 8000))
                    val a = r.optJSONArray("textes")
                    if (a == null || a.length() != lot.size) throw Ia.ErreurIa(Textes.t(R.string.ia_e_incomplet, lot.size))
                    lot.forEachIndexed { j, i -> trad[i] = a.optString(j) }
                }
                val n = appliquer(pdf, bs, trad)
                val base = nom.substringBeforeLast('.')
                val f = File(ctx.filesDir, "traductions/$base ($code).pdf")
                f.parentFile?.mkdirs()
                pdf.save(f.absolutePath, "garbage=3,compress")
                Journal.ecrire("traduire", "$n paragraphe(s) traduit(s) en $langue : ${f.name}")
                f
            } finally { pdf.destroy() }
        }
}

/** Plus > Traduire le document : langue choisie, puis traduction par l'IA vers un nouveau fichier, ouvert ensuite. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun TraduireUi(etat: EtatLecteur, ouvrirFichier: (File) -> Unit, fermer: () -> Unit) {
    val ctx = LocalContext.current
    var code by remember { mutableStateOf<String?>(null) }
    var autre by remember { mutableStateOf("") }
    var lancer by remember { mutableStateOf(false) }
    var avance by remember { mutableStateOf(0 to 0) }
    val texte by produceState<String?>(null, etat.doc) { value = try { etat.doc.texteDocument() } catch (_: Exception) { "" } }
    val t = texte
    when {
        etat.doc.modifie -> AlertDialog(onDismissRequest = fermer, title = { Text(stringResource(R.string.trad_titre)) },
            text = { Text(stringResource(R.string.trad_enregistrer_avant)) },
            confirmButton = { TextButton(onClick = fermer) { Text(stringResource(R.string.ok)) } })
        t == null -> {}
        t.isBlank() -> AlertDialog(onDismissRequest = fermer, title = { Text(stringResource(R.string.trad_titre)) },
            text = { Text(stringResource(R.string.ia_sans_texte)) },
            confirmButton = { if (etat.doc.modifiable) TextButton(onClick = { fermer(); etat.ocr = 0 }) { Text(stringResource(R.string.ocr_titre_menu)) } },
            dismissButton = { TextButton(onClick = fermer) { Text(stringResource(R.string.fermer)) } })
        !lancer -> Fenetre(fermer) {
            Column(Modifier.fillMaxSize()) {
                Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(16.dp)) {
                    Text(stringResource(R.string.trad_titre), fontSize = 20.sp, fontWeight = FontWeight.SemiBold)
                    Text(stringResource(R.string.trad_aide), fontSize = 13.sp, color = Color.Gray)
                    Spacer(Modifier.height(10.dp))
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        Traduction.LANGUES.forEach { (c, nom) -> FilterChip(code == c, { code = c; autre = "" }, { Text(stringResource(nom)) }) }
                    }
                    OutlinedTextField(autre, { autre = it; if (it.isNotBlank()) code = null }, Modifier.fillMaxWidth(), singleLine = true,
                        label = { Text(stringResource(R.string.trad_autre)) })
                }
                FlowRow(Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 8.dp),
                    horizontalArrangement = Arrangement.spacedBy(4.dp, Alignment.End)) {
                    TextButton(onClick = fermer) { Text(stringResource(R.string.annuler)) }
                    Button(onClick = { lancer = true }, enabled = code != null || autre.isNotBlank(),
                        colors = ButtonDefaults.buttonColors(containerColor = ROUGE)) { Text(stringResource(R.string.trad_traduire)) }
                }
            }
        }
        else -> {
            val c = code ?: autre.trim().filter { it.isLetter() }.take(2).uppercase().ifEmpty { "TR" }
            val langue = code?.let { Traduction.POUR_IA[it] } ?: autre.trim()
            EnvoiIa(t, if (avance.second > 1) stringResource(R.string.trad_en_cours_lots, avance.first, avance.second) else stringResource(R.string.trad_en_cours), {
                Traduction.traduire(ctx, etat.doc.fichier, etat.doc.nom, c, langue) { i, n -> avance = i to n }
            }, { f -> fermer(); ouvrirFichier(f) }, fermer)
        }
    }
}
