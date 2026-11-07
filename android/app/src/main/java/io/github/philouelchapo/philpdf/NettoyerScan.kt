package io.github.philouelchapo.philpdf

import android.graphics.Bitmap
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/** Reglages de « Nettoyer un scan » (les memes que sous Windows, en plus simple). */
data class ReglagesNettoyage(val redresser: Boolean = true, val bords: Boolean = true, val taches: Boolean = true,
                             val noirBlanc: Boolean = true)

object Nettoyage {
    fun page(src: Bitmap, r: ReglagesNettoyage): Bitmap {
        val droit = if (r.redresser) Numerisation.aplomb(src) else src
        return Numerisation.ameliorer(droit, if (r.noirBlanc) Numerisation.Modele.NOIR_BLANC else Numerisation.Modele.COULEUR,
            r.bords, r.taches)
    }
}

/** Nettoyer un scan (Plus > Nettoyer un scan), comme sous Windows : avant / apres, reglages, puis « Nettoyer » sur
 *  cette page ou toutes. Les pages sont preparees d'abord (on peut arreter : rien n'est change), puis remplacees en
 *  une seule etape d'annulation ; la reconnaissance du texte (OCR) est proposee ensuite. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun NettoyerScanUi(etat: EtatLecteur, n0: Int, fermer: () -> Unit) {
    val ctx = LocalContext.current
    val portee = rememberCoroutineScope()
    var r by remember { mutableStateOf(ReglagesNettoyage()) }
    var toutes by remember { mutableStateOf(false) }
    var avant by remember { mutableStateOf<Bitmap?>(null) }
    var apres by remember { mutableStateOf<Bitmap?>(null) }
    var voirAvant by remember { mutableStateOf(false) }
    var avance by remember { mutableStateOf<Pair<Int, Int>?>(null) }
    var travail by remember { mutableStateOf<Job?>(null) }
    var verifie by remember { mutableStateOf<Pair<List<Int>, List<Int>>?>(null) }   // (pages voulues, pages avec du vrai texte)
    LaunchedEffect(n0) { avant = try { etat.doc.imageContenu(n0, 1000) } catch (_: Exception) { null } }
    LaunchedEffect(avant, r) {
        val a = avant ?: return@LaunchedEffect
        apres = null
        apres = withContext(Dispatchers.Default) { try { Nettoyage.page(a, r) } catch (_: Exception) { null } }
    }

    fun nettoyer(pages: List<Int>) {
        travail = portee.launch {
            val images = LinkedHashMap<Int, ByteArray>()
            try {
                for ((i, n) in pages.withIndex()) {
                    avance = i + 1 to pages.size
                    images[n] = withContext(Dispatchers.Default) {
                        val src = etat.doc.imageContenu(n, 2000)
                        Numerisation.octets(Nettoyage.page(src, r), if (r.noirBlanc) Numerisation.Modele.NOIR_BLANC else Numerisation.Modele.COULEUR)
                    }
                }
            } catch (e: kotlinx.coroutines.CancellationException) {
                avance = null; travail = null; etat.message = ctx.getString(R.string.net_arrete); return@launch
            } catch (e: Exception) {
                Journal.ecrire("nettoyer", e.toString())
                avance = null; travail = null; etat.message = ctx.getString(R.string.net_echec, 0); return@launch
            }
            val ok = try { etat.doc.remplacerParImages(images) } catch (e: Exception) { Journal.ecrire("nettoyer", e.toString()); false }
            Journal.ecrire("nettoyer", if (ok) "${images.size} page(s) nettoyée(s)" else "nettoyage impossible")
            avance = null; travail = null
            etat.message = ctx.getString(if (ok) R.string.net_fait else R.string.net_echec, images.size)
            fermer()
            if (ok) etat.ocr = pages.first()          // proposer de reconnaitre le texte des pages nettoyees
        }
    }

    // pages qui ont du vrai texte (pas un scan) : elles deviendraient une image ; on le demande d'abord
    fun verifier() {
        portee.launch {
            val pages = if (toutes) (0 until etat.doc.nombrePages()).toList() else listOf(n0)
            val texte = pages.filter { !etat.doc.pageScannee(it) }
            if (texte.isEmpty()) nettoyer(pages) else verifie = pages to texte
        }
    }

    verifie?.let { (pages, texte) -> ConfirmerTexte(pages, texte, { p -> verifie = null; nettoyer(p) }) { verifie = null } }
    Fenetre({ if (travail == null) fermer() }) {
        BoxWithConstraints(Modifier.fillMaxSize().background(Color.White)) {
            val large = maxWidth > maxHeight && maxWidth >= 560.dp
            val hauteur = maxHeight
            Column(Modifier.fillMaxSize()) {
                Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(horizontal = 16.dp, vertical = 12.dp)) {
                    Text(stringResource(R.string.net_titre) + " — " + stringResource(R.string.net_page_n, n0 + 1),
                        fontSize = 20.sp, fontWeight = FontWeight.SemiBold)
                    Text(stringResource(R.string.net_aide), fontSize = 13.sp, color = Color.Gray)
                    Spacer(Modifier.height(8.dp))
                    val hApercu = maxOf(220.dp, hauteur * 0.45f)
                    @Composable
                    fun vue(titre: String, bm: Bitmap?, m: Modifier) {
                        Column(m, horizontalAlignment = Alignment.CenterHorizontally) {
                            Text(titre, fontWeight = FontWeight.Bold, fontSize = 12.sp)
                            Box(Modifier.fillMaxWidth().height(hApercu).background(Color.White).border(1.dp, Color(0xFFDDDDDD)),
                                contentAlignment = Alignment.Center) {
                                if (bm != null) Image(bm.asImageBitmap(), titre, Modifier.fillMaxSize())
                                else CircularProgressIndicator(Modifier.size(28.dp))
                            }
                        }
                    }
                    if (large) Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        vue(stringResource(R.string.net_avant), avant, Modifier.weight(1f))
                        vue(stringResource(R.string.net_apres), apres, Modifier.weight(1f))
                    } else {
                        FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            FilterChip(!voirAvant, { voirAvant = false }, { Text(stringResource(R.string.net_apres)) })
                            FilterChip(voirAvant, { voirAvant = true }, { Text(stringResource(R.string.net_avant)) })
                        }
                        vue(if (voirAvant) stringResource(R.string.net_avant) else stringResource(R.string.net_apres),
                            if (voirAvant) avant else apres, Modifier.fillMaxWidth())
                    }
                    Spacer(Modifier.height(8.dp))
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        FilterChip(r.noirBlanc, { r = r.copy(noirBlanc = true) }, { Text(stringResource(R.string.net_nb)) })
                        FilterChip(!r.noirBlanc, { r = r.copy(noirBlanc = false) }, { Text(stringResource(R.string.net_couleur)) })
                    }
                    CaseTexte(r.redresser, stringResource(R.string.net_redresser)) { r = r.copy(redresser = it) }
                    CaseTexte(r.bords, stringResource(R.string.net_bords), r.noirBlanc) { r = r.copy(bords = it) }
                    CaseTexte(r.taches, stringResource(R.string.net_taches), r.noirBlanc) { r = r.copy(taches = it) }
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        FilterChip(!toutes, { toutes = false }, { Text(stringResource(R.string.redresser_cette_page)) })
                        FilterChip(toutes, { toutes = true }, { Text(stringResource(R.string.toutes_pages)) })
                    }
                    avance?.let { (i, t) ->
                        Spacer(Modifier.height(8.dp))
                        Text(stringResource(R.string.net_en_cours, i, t), fontSize = 13.sp)
                        LinearProgressIndicator({ i / t.toFloat() }, Modifier.fillMaxWidth())
                    }
                }
                // boutons fixes en bas, au-dessus de la barre d'Android
                FlowRow(Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 8.dp),
                    horizontalArrangement = Arrangement.spacedBy(4.dp, Alignment.End)) {
                    if (travail != null) TextButton(onClick = { travail?.cancel() }) { Text(stringResource(R.string.net_arreter)) }
                    else TextButton(onClick = fermer) { Text(stringResource(R.string.annuler)) }
                    Button(onClick = { verifier() }, enabled = travail == null && avant != null,
                        colors = ButtonDefaults.buttonColors(containerColor = ROUGE)) { Text(stringResource(R.string.net_nettoyer)) }
                }
            }
        }
    }
}

@Composable
private fun ConfirmerTexte(pages: List<Int>, texte: List<Int>, nettoyer: (List<Int>) -> Unit, annuler: () -> Unit) {
    val scans = pages - texte.toSet()
    AlertDialog(onDismissRequest = annuler, title = { Text(stringResource(R.string.net_titre)) },
        text = { Text(stringResource(R.string.net_vrai_texte, texte.size)) },
        confirmButton = {
            FlowRowBoutons {
                TextButton(onClick = annuler) { Text(stringResource(R.string.annuler)) }
                if (scans.isNotEmpty()) TextButton(onClick = { nettoyer(scans) }) { Text(stringResource(R.string.net_seulement_scans, scans.size)) }
                Button(onClick = { nettoyer(pages) }, colors = ButtonDefaults.buttonColors(containerColor = ROUGE)) {
                    Text(stringResource(R.string.net_quand_meme)) }
            }
        })
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun FlowRowBoutons(contenu: @Composable () -> Unit) =
    FlowRow(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(4.dp, Alignment.End)) { contenu() }

@Composable
private fun CaseTexte(coche: Boolean, texte: String, actif: Boolean = true, changer: (Boolean) -> Unit) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Checkbox(coche && actif, { changer(it) }, enabled = actif)
        Text(texte, fontSize = 14.sp, color = if (actif) Color.Unspecified else Color.Gray)
    }
}
