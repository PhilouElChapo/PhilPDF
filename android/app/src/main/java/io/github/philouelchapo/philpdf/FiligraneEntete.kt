package io.github.philouelchapo.philpdf

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
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
import com.artifex.mupdf.fitz.Font
import com.artifex.mupdf.fitz.PDFDocument
import com.artifex.mupdf.fitz.PDFObject
import com.artifex.mupdf.fitz.PDFPage
import kotlinx.coroutines.launch

/** Filigrane (texte en travers) et en-tete / pied de page, version allegee de Windows.
 *  Memes marquages que PhilPDF Windows et Acrobat : un filigrane ou un en-tete pose ici se retire aussi sous
 *  Windows (et inversement). */
data class ReglagesFiligrane(val texte: String, val couleur: Int, val opacite: Float, val angle: Float)

data class ReglagesEntete(val haut: String, val alignHaut: Int, val bas: String, val alignBas: Int, val taille: Float)

object Pagination {
    const val FILIGRANE = "/Artifact <</Subtype /Watermark /Type /Pagination >>BDC\n"
    const val ENTETE = "/Artifact <</Type /Pagination /PhilPDF (entete)>> BDC\n"
    private val BLOC_FILIGRANE = Regex("/Artifact\\s*<<[^>]*?/Watermark[^>]*?>>\\s*BDC.*?EMC", RegexOption.DOT_MATCHES_ALL)
    private val BLOC_ENTETE = Regex("/Artifact <</Type /Pagination /PhilPDF \\(entete\\)>> BDC\\n.*?\\nEMC\\n", RegexOption.DOT_MATCHES_ALL)
    private val latin = java.nio.charset.Charset.forName("windows-1252")

    private fun f(v: Float) = String.format(java.util.Locale.US, "%.3f", v)

    internal fun dico(pdf: PDFDocument, parent: PDFObject, cle: String): PDFObject {
        var d = parent.get(cle)
        if (d.isNull) { d = pdf.newDictionary(); parent.put(cle, d) }
        return d
    }

    internal fun ressources(pdf: PDFDocument, page: PDFPage): PDFObject {
        val pobj = page.getObject()
        var res = pobj.get("Resources")
        if (res.isNull) {
            res = pobj.getInheritable("Resources")
            if (res.isNull) res = pdf.newDictionary()
            pobj.put("Resources", res)
        }
        return res
    }

    internal fun nom(d: PDFObject, prefixe: String): String { var i = 1; while (!d.get("$prefixe$i").isNull) i++; return "$prefixe$i" }

    /** Ajoute le flux a la fin du contenu de la page (le contenu d'origine est mis entre q ... Q). */
    internal fun ajouterFlux(pdf: PDFDocument, page: PDFPage, flux: String) {
        val pobj = page.getObject()
        val contenu = pobj.get("Contents")
        val t = pdf.newArray()
        t.ajouter(pdf.addStream("q\n"))
        if (contenu.isArray) { for (k in 0 until contenu.size()) t.ajouter(contenu.get(k)) } else if (!contenu.isNull) t.ajouter(contenu)
        t.ajouter(pdf.addStream("Q\n"))
        t.ajouter(pdf.addStream(flux))
        pobj.put("Contents", t)
    }

    /** Texte dans le repere de la page affichee (y vers le bas) : depart, angle en degres (sens inverse des
     *  aiguilles), converti dans le repere PDF de la page (pages tournees ou decalees comprises). */
    internal fun texte(page: PDFPage, police: String, taille: Float, x: Float, y: Float, angle: Float, s: String): String {
        val inv = page.getTransform().invert()
        val a = Math.toRadians(angle.toDouble())
        val dx = Math.cos(a).toFloat(); val dy = -Math.sin(a).toFloat()          // sens de la ligne (ecran)
        val ux = -Math.sin(a).toFloat(); val uy = -Math.cos(a).toFloat()         // vers le haut des lettres (ecran)
        val ox = x * inv.a + y * inv.c + inv.e; val oy = x * inv.b + y * inv.d + inv.f
        val xa = dx * inv.a + dy * inv.c; val xb = dx * inv.b + dy * inv.d
        val ya = ux * inv.a + uy * inv.c; val yb = ux * inv.b + uy * inv.d
        val hex = s.toByteArray(latin).joinToString("") { "%02X".format(it.toInt() and 255) }
        return "BT /$police ${f(taille)} Tf ${f(xa)} ${f(xb)} ${f(ya)} ${f(yb)} ${f(ox)} ${f(oy)} Tm <$hex> Tj ET\n"
    }

    internal fun largeur(fonte: Font, s: String, taille: Float): Float =
        String(s.toByteArray(latin), latin).sumOf { c -> fonte.advanceGlyph(fonte.encodeCharacter(c.code), false).toDouble() }.toFloat() * taille

    internal fun rgb(c: Int) = "${f(((c shr 16) and 255) / 255f)} ${f(((c shr 8) and 255) / 255f)} ${f((c and 255) / 255f)} rg"

    fun filigrane(pdf: PDFDocument, page: PDFPage, r: ReglagesFiligrane, fonte: Font, policeObj: PDFObject) {
        if (r.texte.isBlank()) return
        val res = ressources(pdf, page)
        val fonts = dico(pdf, res, "Font")
        val nf = nom(fonts, "PhilW"); fonts.put(nf, policeObj)
        val gs = dico(pdf, res, "ExtGState")
        val ng = nom(gs, "PhilGS")
        gs.put(ng, pdf.newDictionary().also { it.put("ca", r.opacite); it.put("CA", r.opacite) })
        val b = page.bounds
        val w = b.x1 - b.x0; val h = b.y1 - b.y0
        val t = minOf(w, h) / maxOf(4f, r.texte.length * 0.62f)
        val l = largeur(fonte, r.texte, t)
        // centre de la page ; le texte tourne autour de son milieu
        val a = Math.toRadians(r.angle.toDouble())
        val cx = b.x0 + w / 2; val cy = b.y0 + h / 2
        val x = cx - Math.cos(a).toFloat() * l / 2 + Math.sin(a).toFloat() * t * 0.35f
        val y = cy + Math.sin(a).toFloat() * l / 2 + Math.cos(a).toFloat() * t * 0.35f
        ajouterFlux(pdf, page, FILIGRANE + "q /$ng gs ${rgb(r.couleur)}\n" + texte(page, nf, t, x, y, r.angle, r.texte) + "Q\nEMC\n")
    }

    fun entete(pdf: PDFDocument, page: PDFPage, n: Int, total: Int, r: ReglagesEntete, fonte: Font, policeObj: PDFObject) {
        val date = java.text.DateFormat.getDateInstance(java.text.DateFormat.SHORT).format(java.util.Date())
        fun remplir(s: String) = s.replace("{page}", "${n + 1}").replace("{pages}", "$total").replace("{date}", date)
        val haut = remplir(r.haut).trim(); val bas = remplir(r.bas).trim()
        if (haut.isEmpty() && bas.isEmpty()) return
        val res = ressources(pdf, page)
        val fonts = dico(pdf, res, "Font")
        val nf = nom(fonts, "PhilH"); fonts.put(nf, policeObj)
        val b = page.bounds
        val w = b.x1 - b.x0; val h = b.y1 - b.y0
        val marge = 36f
        val sb = StringBuilder(ENTETE + "q 0.2 0.2 0.2 rg\n")
        for ((s, align, enHaut) in listOf(Triple(haut, r.alignHaut, true), Triple(bas, r.alignBas, false))) {
            if (s.isEmpty()) continue
            val l = largeur(fonte, s, r.taille)
            val x = b.x0 + when (align) { 0 -> marge; 2 -> w - marge - l; else -> (w - l) / 2 }
            val y = b.y0 + if (enHaut) marge * 0.66f + r.taille else h - marge * 0.55f
            sb.append(texte(page, nf, r.taille, x, y, 0f, s))
        }
        sb.append("Q\nEMC\n")
        ajouterFlux(pdf, page, sb.toString())
    }

    /** Retire les filigranes (ceux de PhilPDF, d'Acrobat et des logiciels qui suivent la norme) ou les en-tetes
     *  poses par PhilPDF. Renvoie le nombre de pages touchees. */
    fun retirer(pdf: PDFDocument, filigranes: Boolean): Int {
        val motif = if (filigranes) BLOC_FILIGRANE else BLOC_ENTETE
        var n = 0
        for (i in 0 until pdf.countPages()) {
            val c = pdf.findPage(i).get("Contents")
            val flux = if (c.isArray) (0 until c.size()).map { c.get(it) } else if (c.isNull) emptyList() else listOf(c)
            var touche = false
            for (o in flux) {
                if (!o.isStream) continue
                val s = String(o.readStream(), Charsets.ISO_8859_1)
                if (!motif.containsMatchIn(s)) continue
                o.writeStream(com.artifex.mupdf.fitz.Buffer().also { it.writeBytes(motif.replace(s, "").toByteArray(Charsets.ISO_8859_1)) })
                touche = true
            }
            if (touche) n++
        }
        return n
    }

    fun present(pdf: PDFDocument, filigranes: Boolean): Boolean {
        val motif = if (filigranes) BLOC_FILIGRANE else BLOC_ENTETE
        for (i in 0 until pdf.countPages()) {
            val c = pdf.findPage(i).get("Contents")
            val flux = if (c.isArray) (0 until c.size()).map { c.get(it) } else if (c.isNull) emptyList() else listOf(c)
            if (flux.any { it.isStream && motif.containsMatchIn(String(it.readStream(), Charsets.ISO_8859_1)) }) return true
        }
        return false
    }
}

// ================================================================ fenetre
private val COULEURS_FILIGRANE = listOf(0x999999, 0xD32F2F, 0x0F6CBD)

/** Filigrane et en-tete / pied de page (Plus > Filigrane, en-tete). Rien n'est change avant « Appliquer » ;
 *  « Annuler » (fleche du haut) retire ensuite ce qui a ete pose. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun FiligraneEnteteUi(etat: EtatLecteur, fermer: () -> Unit) {
    val ctx = LocalContext.current
    val portee = rememberCoroutineScope()
    var onglet by remember { mutableIntStateOf(0) }
    var occupe by remember { mutableStateOf(false) }
    // filigrane
    val modeles = listOf(stringResource(R.string.fil_confidentiel), stringResource(R.string.fil_copie), stringResource(R.string.fil_brouillon))
    var texteF by remember { mutableStateOf(modeles[0]) }
    var couleur by remember { mutableIntStateOf(COULEURS_FILIGRANE[0]) }
    var opacite by remember { mutableFloatStateOf(0.25f) }
    var penche by remember { mutableStateOf(true) }
    var toutes by remember { mutableStateOf(true) }
    // en-tete / pied
    var haut by remember { mutableStateOf("") }
    var alignHaut by remember { mutableIntStateOf(1) }
    val piedDefaut = stringResource(R.string.ent_pied_defaut)
    var bas by remember { mutableStateOf(piedDefaut) }
    var alignBas by remember { mutableIntStateOf(1) }
    var taille by remember { mutableFloatStateOf(9f) }
    var dejaF by remember { mutableStateOf(false) }
    var dejaE by remember { mutableStateOf(false) }
    LaunchedEffect(Unit) { dejaF = etat.doc.aPagination(true); dejaE = etat.doc.aPagination(false) }

    fun fini(msg: String) { occupe = false; etat.message = msg; fermer() }

    Fenetre(fermer) {
        Column(Modifier.fillMaxSize()) {
            Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(16.dp)) {
                Text(stringResource(R.string.fil_titre), fontSize = 20.sp, fontWeight = FontWeight.SemiBold)
                Spacer(Modifier.height(8.dp))
                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    FilterChip(onglet == 0, { onglet = 0 }, { Text(stringResource(R.string.fil_onglet_filigrane)) })
                    FilterChip(onglet == 1, { onglet = 1 }, { Text(stringResource(R.string.fil_onglet_entete)) })
                }
                Spacer(Modifier.height(12.dp))
                if (onglet == 0) {
                    OutlinedTextField(texteF, { texteF = it }, Modifier.fillMaxWidth(), singleLine = true,
                        label = { Text(stringResource(R.string.fil_texte)) })
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        modeles.forEach { m -> AssistChip({ texteF = m }, { Text(m, fontSize = 12.sp) }) }
                    }
                    Spacer(Modifier.height(8.dp))
                    Text(stringResource(R.string.fil_couleur), fontSize = 14.sp)
                    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        COULEURS_FILIGRANE.forEach { c ->
                            Box(Modifier.size(36.dp).background(Color(0xFF000000.toInt() or c), CircleShape)
                                .border(if (c == couleur) 3.dp else 1.dp, if (c == couleur) Color.Black else Color.LightGray, CircleShape)
                                .clickable { couleur = c })
                        }
                    }
                    Spacer(Modifier.height(8.dp))
                    Text(stringResource(R.string.fil_opacite, (opacite * 100).toInt()), fontSize = 14.sp)
                    Slider(opacite, { opacite = it }, valueRange = 0.1f..0.6f)
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        FilterChip(penche, { penche = true }, { Text(stringResource(R.string.fil_penche)) })
                        FilterChip(!penche, { penche = false }, { Text(stringResource(R.string.fil_droit)) })
                    }
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        FilterChip(toutes, { toutes = true }, { Text(stringResource(R.string.toutes_pages)) })
                        FilterChip(!toutes, { toutes = false }, { Text(stringResource(R.string.redresser_cette_page)) })
                    }
                    if (dejaF) {
                        Spacer(Modifier.height(8.dp))
                        Text(stringResource(R.string.fil_deja), fontSize = 13.sp, color = Color.Gray)
                        TextButton(onClick = {
                            occupe = true
                            portee.launch { val n = etat.doc.retirerPagination(true); fini(ctx.getString(R.string.fil_retires, n)) }
                        }, enabled = !occupe) { Text(stringResource(R.string.fil_retirer)) }
                    }
                } else {
                    Text(stringResource(R.string.ent_codes), fontSize = 13.sp, color = Color.Gray)
                    Spacer(Modifier.height(6.dp))
                    OutlinedTextField(haut, { haut = it }, Modifier.fillMaxWidth(), singleLine = true,
                        label = { Text(stringResource(R.string.ent_haut)) })
                    Alignements(alignHaut) { alignHaut = it }
                    OutlinedTextField(bas, { bas = it }, Modifier.fillMaxWidth(), singleLine = true,
                        label = { Text(stringResource(R.string.ent_bas)) })
                    Alignements(alignBas) { alignBas = it }
                    Text(stringResource(R.string.ent_taille, taille.toInt()), fontSize = 14.sp)
                    Slider(taille, { taille = it }, valueRange = 6f..16f, steps = 9)
                    if (dejaE) {
                        Text(stringResource(R.string.ent_deja), fontSize = 13.sp, color = Color.Gray)
                        TextButton(onClick = {
                            occupe = true
                            portee.launch { val n = etat.doc.retirerPagination(false); fini(ctx.getString(R.string.ent_retires, n)) }
                        }, enabled = !occupe) { Text(stringResource(R.string.ent_retirer)) }
                    }
                }
                Spacer(Modifier.height(8.dp))
                Text(stringResource(R.string.fil_annuler_aide), fontSize = 12.sp, color = Color.Gray)
            }
            // boutons fixes en bas, au-dessus de la barre d'Android
            FlowRow(Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 8.dp),
                horizontalArrangement = Arrangement.spacedBy(4.dp, Alignment.End)) {
                TextButton(onClick = fermer, enabled = !occupe) { Text(stringResource(R.string.annuler)) }
                Button(onClick = {
                    occupe = true
                    portee.launch {
                        if (onglet == 0) {
                            val pages = if (toutes) (0 until etat.doc.nombrePages()).toList() else listOf(etat.page)
                            val ok = etat.doc.poserFiligrane(pages, ReglagesFiligrane(texteF.trim(), couleur, opacite, if (penche) 45f else 0f))
                            fini(if (ok) ctx.getString(R.string.fil_pose, pages.size) else ctx.getString(R.string.fil_echec))
                        } else {
                            val ok = etat.doc.poserEntete(ReglagesEntete(haut, alignHaut, bas, alignBas, taille))
                            fini(if (ok) ctx.getString(R.string.ent_pose) else ctx.getString(R.string.fil_echec))
                        }
                    }
                }, enabled = !occupe && (if (onglet == 0) texteF.isNotBlank() else (haut.isNotBlank() || bas.isNotBlank())),
                    colors = ButtonDefaults.buttonColors(containerColor = ROUGE)) { Text(stringResource(R.string.appliquer)) }
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun Alignements(choisi: Int, choisir: (Int) -> Unit) {
    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        listOf(R.string.ent_gauche, R.string.ent_centre, R.string.ent_droite).forEachIndexed { i, t ->
            FilterChip(choisi == i, { choisir(i) }, { Text(stringResource(t)) })
        }
    }
}
