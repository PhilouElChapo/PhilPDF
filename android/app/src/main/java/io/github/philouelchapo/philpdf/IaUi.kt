@file:OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class)

package io.github.philouelchapo.philpdf

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.provider.CalendarContract
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.launch
import org.json.JSONObject
import java.text.SimpleDateFormat
import java.util.Locale

// ================================================================ reglages : IA choisie et clefs
/** Reglages de l'IA : Claude ou Gemini, vos clefs (gardees chiffrees ici), reprise des clefs de vos postes Windows. */
@Composable
fun ReglagesIa(fermer: () -> Unit) {
    val ctx = LocalContext.current
    val portee = rememberCoroutineScope()
    var moteur by remember { mutableStateOf(Ia.moteurPrefere(ctx)) }
    var kc by remember { mutableStateOf(Ia.clef(ctx, "claude")) }
    var kg by remember { mutableStateOf(Ia.clef(ctx, "gemini")) }
    var etatTest by remember { mutableStateOf<String?>(null) }
    var occupe by remember { mutableStateOf(false) }
    var phrase by remember { mutableStateOf<String?>(null) }           // non null : on demande la phrase secrete
    val relie = remember { Nuage.synchro(ctx) != null }
    fun garder() { Ia.poserClef(ctx, "claude", kc); Ia.poserClef(ctx, "gemini", kg); Ia.poserMoteur(ctx, moteur) }
    fun reprendre(p: String) {
        occupe = true; etatTest = ctx.getString(R.string.ia_reprise_en_cours)
        portee.launch {
            etatTest = try {
                val r = Ia.reprendreDePostes(ctx, p)
                kc = Ia.clef(ctx, "claude"); kg = Ia.clef(ctx, "gemini"); moteur = Ia.moteurPrefere(ctx)
                if (r.isEmpty()) ctx.getString(R.string.ia_reprise_aucune) else ctx.getString(R.string.ia_reprise_ok, r.joinToString(", ") { Ia.nom(it) })
            } catch (e: Exception) { e.message ?: e.toString() }
            occupe = false
        }
    }
    Fenetre({ if (!occupe) fermer() }) {
        Surface(Modifier.fillMaxWidth(0.96f).widthIn(max = 620.dp), shape = RoundedCornerShape(16.dp)) {
            Column(Modifier.padding(16.dp)) {
                Column(Modifier.weight(1f, fill = false).verticalScroll(rememberScrollState())) {
                    Text(stringResource(R.string.ia_reglages), fontWeight = FontWeight.SemiBold, fontSize = 19.sp)
                    Spacer(Modifier.height(6.dp))
                    Text(stringResource(R.string.ia_reglages_aide), fontSize = 13.sp, color = Color(0xFF555555))
                    Spacer(Modifier.height(10.dp))
                    Text(stringResource(R.string.ia_choisie), fontSize = 14.sp)
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        FilterChip(moteur == "claude", { moteur = "claude" }, label = { Text("Claude (Anthropic)") })
                        FilterChip(moteur == "gemini", { moteur = "gemini" }, label = { Text("Gemini (Google)") })
                    }
                    Spacer(Modifier.height(8.dp))
                    ChampSecret(kc, { kc = it }, stringResource(R.string.ia_clef_claude))
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        TextButton(onClick = { ouvrirLien(ctx, "https://console.anthropic.com/settings/keys") }) { Text(stringResource(R.string.ia_obtenir_clef)) }
                        Spacer(Modifier.weight(1f))
                        TextButton(enabled = kc.isNotBlank() && !occupe, onClick = { garder(); tester(ctx, portee, "claude", { occupe = it }) { etatTest = it } }) {
                            Text(stringResource(R.string.ia_tester))
                        }
                    }
                    ChampSecret(kg, { kg = it }, stringResource(R.string.ia_clef_gemini))
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        TextButton(onClick = { ouvrirLien(ctx, "https://aistudio.google.com/apikey") }) { Text(stringResource(R.string.ia_obtenir_clef)) }
                        Spacer(Modifier.weight(1f))
                        TextButton(enabled = kg.isNotBlank() && !occupe, onClick = { garder(); tester(ctx, portee, "gemini", { occupe = it }) { etatTest = it } }) {
                            Text(stringResource(R.string.ia_tester))
                        }
                    }
                    Text(stringResource(R.string.ia_gemini_images), fontSize = 12.sp, color = Color.Gray)
                    if (relie) {
                        Spacer(Modifier.height(8.dp))
                        OutlinedButton(onClick = {
                            val p = Identites.phraseRetenue(ctx)
                            if (p != null) reprendre(p) else phrase = ""
                        }, enabled = !occupe, modifier = Modifier.fillMaxWidth()) { Text(stringResource(R.string.ia_reprendre_postes)) }
                        Text(stringResource(R.string.ia_reprendre_aide), fontSize = 12.sp, color = Color.Gray)
                    }
                    etatTest?.let { Spacer(Modifier.height(8.dp)); Text(it, fontSize = 13.sp, color = Color(0xFF1A4F8B)) }
                    if (occupe) LinearProgressIndicator(Modifier.fillMaxWidth().padding(top = 6.dp))
                }
                Spacer(Modifier.height(12.dp))
                FlowRow(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(4.dp, Alignment.End)) {   // passe a la ligne, jamais coupe
                    TextButton(onClick = fermer, enabled = !occupe) { Text(stringResource(R.string.annuler)) }
                    Button(onClick = { garder(); Journal.ecrire("IA", "réglages : ${Ia.nom(moteur)}, clefs ${listOfNotNull(
                        "Claude".takeIf { kc.isNotBlank() }, "Gemini".takeIf { kg.isNotBlank() }).joinToString().ifEmpty { "aucune" }}"); fermer() },
                        enabled = !occupe, colors = ButtonDefaults.buttonColors(containerColor = ROUGE)) { Text(stringResource(R.string.enregistrer)) }
                }
            }
        }
    }
    phrase?.let { p ->
        AlertDialog(onDismissRequest = { phrase = null },
            title = { Text(stringResource(R.string.ia_reprendre_postes)) },
            text = { Column { Text(stringResource(R.string.ia_phrase_aide), fontSize = 13.sp); Spacer(Modifier.height(8.dp))
                ChampSecret(p, { phrase = it }, stringResource(R.string.sig_phrase)) } },
            confirmButton = { TextButton(onClick = { phrase = null; reprendre(p) }, enabled = p.isNotBlank()) { Text(stringResource(R.string.ok)) } },
            dismissButton = { TextButton(onClick = { phrase = null }) { Text(stringResource(R.string.annuler)) } })
    }
}

private fun tester(ctx: Context, portee: kotlinx.coroutines.CoroutineScope, m: String, occupe: (Boolean) -> Unit, dire: (String) -> Unit) {
    occupe(true); dire(ctx.getString(R.string.ia_test_en_cours, Ia.nom(m)))
    portee.launch {
        dire(try { ctx.getString(R.string.ia_test_ok, Ia.nom(m), Ia.tester(ctx, m)) } catch (e: Exception) { ctx.getString(R.string.ia_test_echec, Ia.nom(m), e.message ?: e.toString()) })
        occupe(false)
    }
}

fun ouvrirLien(ctx: Context, url: String) {
    try { ctx.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url))) } catch (_: Exception) {}
}

// ================================================================ envoi : clef, donnees sensibles, attente
/**
 * Envoi a l'IA : une clef est-elle reglee ? des donnees sensibles dans le texte ? (on demande avant d'envoyer),
 * puis attente annulable et erreur dite en clair, avec « Reessayer ». gemini : seul Gemini sait faire (images).
 */
@Composable
fun <T> EnvoiIa(controle: String, attente: String, travail: suspend () -> T, fini: (T) -> Unit, annule: () -> Unit,
                gemini: Boolean = false, force: String? = null) {
    val ctx = LocalContext.current
    var reglages by remember { mutableStateOf(false) }
    var version by remember { mutableIntStateOf(0) }
    val pret = remember(version) { if (gemini) Ia.clef(ctx, "gemini").isNotEmpty() else Ia.disponible(ctx) }
    val trouves = remember(controle) { Ia.sensibles(controle) }
    var accord by remember { mutableStateOf(trouves.isEmpty()) }
    var erreur by remember { mutableStateOf<String?>(null) }
    var essai by remember { mutableIntStateOf(0) }
    val qui = if (gemini) "Gemini" else Ia.nom(Ia.moteurs(ctx, force).firstOrNull()?.first)
    when {
        reglages -> ReglagesIa { reglages = false; version++ }
        !pret -> AlertDialog(onDismissRequest = annule,
            title = { Text(stringResource(R.string.ia_titre)) },
            text = { Text(stringResource(if (gemini) R.string.ia_pas_de_clef_gemini else R.string.ia_pas_de_clef)) },
            confirmButton = { TextButton(onClick = { reglages = true }) { Text(stringResource(R.string.ia_regler)) } },
            dismissButton = { TextButton(onClick = annule) { Text(stringResource(R.string.annuler)) } })
        !accord -> AlertDialog(onDismissRequest = annule,
            title = { Text(stringResource(R.string.ia_sensibles_titre)) },
            text = { Text(stringResource(R.string.ia_sensibles_question,
                trouves.take(8).joinToString("\n") { "• ${it.first} : ${it.second}" } + if (trouves.size > 8) "\n• ..." else "", qui)) },
            confirmButton = { TextButton(onClick = { Journal.ecrire("IA", "données sensibles signalées (${trouves.size}) : envoi confirmé"); accord = true }) {
                Text(stringResource(R.string.ia_envoyer_quand_meme), color = Color(0xFFC62828)) } },
            dismissButton = { TextButton(onClick = { Journal.ecrire("IA", "données sensibles signalées : envoi abandonné"); annule() }) {
                Text(stringResource(R.string.annuler)) } })
        erreur != null -> AlertDialog(onDismissRequest = annule,
            title = { Text(stringResource(R.string.ia_erreur_titre, qui)) },
            text = { Text(erreur ?: "") },
            confirmButton = { TextButton(onClick = { erreur = null; essai++ }) { Text(stringResource(R.string.reessayer)) } },
            dismissButton = { TextButton(onClick = annule) { Text(stringResource(R.string.fermer)) } })
        else -> {
            LaunchedEffect(essai) {
                try { fini(travail()) }
                catch (e: kotlinx.coroutines.CancellationException) { throw e }
                catch (e: Exception) { erreur = e.message ?: e.toString() }
            }
            Fenetre({}) {
                Surface(Modifier.widthIn(min = 260.dp, max = 420.dp), shape = RoundedCornerShape(16.dp)) {
                    Column(Modifier.padding(20.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                        CircularProgressIndicator()
                        Spacer(Modifier.height(12.dp))
                        Text(attente, fontSize = 15.sp)
                        Text(stringResource(R.string.ia_attente_qui, qui), fontSize = 12.sp, color = Color.Gray)
                        Spacer(Modifier.height(8.dp))
                        TextButton(onClick = { Journal.ecrire("IA", "demande annulée par l'utilisateur"); annule() }) { Text(stringResource(R.string.annuler)) }
                    }
                }
            }
        }
    }
}

// ================================================================ consigne personnelle (facultative ou libre)
/**
 * Fenetre avant l'envoi : votre consigne ajoutee a celle de PhilPDF (ou seule, si obligatoire), consignes deja
 * gardees a reprendre d'un geste, IA a choisir pour cette fois. lancer(consigne, moteur force ou null).
 */
@Composable
fun ConsigneIa(titre: String, sujet: String, consignePhilpdf: String, obligatoire: Boolean, annuler: () -> Unit,
               lancer: (String, String?) -> Unit) {
    val ctx = LocalContext.current
    var texte by remember { mutableStateOf("") }
    var garder by remember { mutableStateOf(false) }
    var voir by remember { mutableStateOf(false) }
    var gardees by remember { mutableStateOf(Ia.consignes(ctx, sujet)) }
    val dispo = remember { Ia.moteurs(ctx).map { it.first } }
    var moteur by remember { mutableStateOf(dispo.firstOrNull()) }
    Fenetre(annuler) {
        Surface(Modifier.fillMaxWidth(0.96f).widthIn(max = 620.dp), shape = RoundedCornerShape(16.dp)) {
            Column(Modifier.padding(16.dp)) {
                Column(Modifier.weight(1f, fill = false).verticalScroll(rememberScrollState())) {
                    Text(titre, fontWeight = FontWeight.SemiBold, fontSize = 19.sp)
                    Spacer(Modifier.height(6.dp))
                    Text(stringResource(if (obligatoire) R.string.ia_consigne_libre_aide else R.string.ia_consigne_aide), fontSize = 13.sp, color = Color(0xFF555555))
                    if (gardees.isNotEmpty()) {
                        Spacer(Modifier.height(8.dp))
                        Text(stringResource(R.string.ia_consignes_gardees), fontSize = 13.sp)
                        gardees.forEach { c ->
                            Row(Modifier.fillMaxWidth().clickable { texte = c }.padding(vertical = 2.dp), verticalAlignment = Alignment.CenterVertically) {
                                Text("› " + c, Modifier.weight(1f), fontSize = 13.sp, maxLines = 2, overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis)
                                TextButton(onClick = { Ia.oublierConsigne(ctx, sujet, c); gardees = Ia.consignes(ctx, sujet) }) {
                                    Text("✕", color = Color(0xFFC62828)) }
                            }
                        }
                    }
                    Spacer(Modifier.height(8.dp))
                    OutlinedTextField(texte, { texte = it }, Modifier.fillMaxWidth(), minLines = 2, maxLines = 6,
                        label = { Text(stringResource(if (obligatoire) R.string.ia_votre_consigne else R.string.ia_votre_consigne_facultative)) })
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Checkbox(garder, { garder = it }); Text(stringResource(R.string.ia_garder_consigne), fontSize = 13.sp)
                    }
                    if (dispo.size > 1) {
                        Text(stringResource(R.string.ia_envoyer_a), fontSize = 13.sp)
                        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            dispo.forEach { m -> FilterChip(moteur == m, { moteur = m }, label = { Text(Ia.nom(m)) }) }
                        }
                    }
                    TextButton(onClick = { voir = !voir }) { Text(stringResource(R.string.ia_voir_consigne_philpdf)) }
                    if (voir) Text(consignePhilpdf, fontSize = 12.sp, color = Color.Gray)
                }
                Spacer(Modifier.height(12.dp))
                FlowRow(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(4.dp, Alignment.End)) {   // passe a la ligne, jamais coupe
                    TextButton(onClick = annuler) { Text(stringResource(R.string.annuler)) }
                    Button(onClick = {
                        val t = texte.trim()
                        if (t.isNotEmpty() && garder) Ia.garderConsigne(ctx, sujet, t)
                        lancer(t, if (dispo.size > 1) moteur else null)
                    }, enabled = !obligatoire || texte.isNotBlank(), colors = ButtonDefaults.buttonColors(containerColor = ROUGE)) {
                        Text(stringResource(R.string.ia_lancer))
                    }
                }
            }
        }
    }
}

// ================================================================ resume, points clefs, echeances
private const val CONSIGNES_RESUME = """Tu es l'assistant d'un éditeur PDF. Résume le document en LANGUE, de façon claire et utile pour
quelqu'un de pressé. Réponds en JSON : {"resume": "<texte en Markdown : un paragraphe de résumé, puis une section
'Points clefs' en liste à puces, puis 'Action attendue' si le document demande quelque chose>",
"echeances": [{"date": "AAAA-MM-JJ", "heure": "HH:MM ou vide", "type": "rendez-vous ou échéance",
"libelle": "<ce qui est dû ou prévu à cette date, avec le lieu pour un rendez-vous>"}]}.
'echeances' ne contient que les dates réelles (rendez-vous, convocation, délai de recours, date de paiement...),
calculées si le document donne un délai à partir d'une date. 'heure' seulement si le document la donne.
Liste vide s'il n'y en a pas."""

/** Nom de la langue du telephone, en francais (les consignes de PhilPDF sont en francais). */
fun langueTelephone(): String = when (Locale.getDefault().language) {
    "en" -> "anglais"; "de" -> "allemand"; "es" -> "espagnol"; "it" -> "italien"; "pt" -> "portugais"; "nl" -> "néerlandais"
    else -> "français"
}

fun consignesResume(): String = CONSIGNES_RESUME.replace("LANGUE", langueTelephone())

class Echeance(val date: String, val heure: String, val libelle: String)
class ResultatResume(val texte: String, val echeances: List<Echeance>, val qui: Pair<String, String>?)

private fun dateValide(d: String): String? = try {
    SimpleDateFormat("yyyy-MM-dd", Locale.US).apply { isLenient = false }.parse(d.take(10)); d.take(10)
} catch (_: Exception) { null }

fun lireResume(j: JSONObject): ResultatResume {
    val a = j.optJSONArray("echeances")
    val e = (0 until (a?.length() ?: 0)).mapNotNull { a!!.optJSONObject(it) }.mapNotNull { o ->
        dateValide(o.optString("date"))?.let { Echeance(it, o.optString("heure").trim().takeIf { h -> Regex("\\d{1,2}:\\d{2}").matches(h) } ?: "", o.optString("libelle")) }
    }
    return ResultatResume(j.optString("resume"), e, Ia.dernier)
}

/** Resumer avec l'IA : consigne (facultative), envoi, puis le resume, ses dates (agenda), copier, partager, note. */
@Composable
fun ResumeIa(etat: EtatLecteur, fermer: () -> Unit) {
    val ctx = LocalContext.current
    val texte by produceState<String?>(null, etat.doc) { value = try { etat.doc.texteDocument() } catch (_: Exception) { "" } }
    var demande by remember { mutableStateOf<Pair<String, String?>?>(null) }
    var resultat by remember { mutableStateOf<ResultatResume?>(null) }
    val t = texte
    when {
        t == null -> Fenetre(fermer) { Surface(shape = RoundedCornerShape(16.dp)) { Column(Modifier.padding(20.dp)) { CircularProgressIndicator() } } }
        t.isBlank() -> AlertDialog(onDismissRequest = fermer, title = { Text(stringResource(R.string.ia_resumer)) },
            text = { Text(stringResource(R.string.ia_sans_texte)) },
            confirmButton = { if (etat.doc.modifiable) TextButton(onClick = { fermer(); etat.ocr = 0 }) { Text(stringResource(R.string.ocr_titre_menu)) } },
            dismissButton = { TextButton(onClick = fermer) { Text(stringResource(R.string.fermer)) } })
        resultat != null -> EcranResume(etat, resultat!!, fermer)
        demande == null -> ConsigneIa(stringResource(R.string.ia_resumer), "resume", consignesResume(), false, fermer) { c, m -> demande = c to m }
        else -> {
            val (perso, m) = demande!!
            EnvoiIa(t, stringResource(R.string.ia_lit_document), {
                val jour = SimpleDateFormat("yyyy-MM-dd", Locale.US).format(java.util.Date())
                lireResume(Ia.lireJson(Ia.demander(ctx, Ia.ajouterConsigne(consignesResume() + "\nDate du jour : $jour.", perso), t, json = true, force = m)))
            }, { resultat = it }, fermer, force = m)
        }
    }
}

@Composable
private fun EcranResume(etat: EtatLecteur, r: ResultatResume, fermer: () -> Unit) {
    val ctx = LocalContext.current
    val portee = rememberCoroutineScope()
    val brut = remember(r) { texteSimple(r.texte) }
    Fenetre(fermer) {
        Surface(Modifier.fillMaxSize(), color = Color(0xFFF3F3F3)) {
            Column(Modifier.fillMaxSize()) {
                Row(Modifier.fillMaxWidth().background(Color.White).padding(horizontal = 4.dp, vertical = 2.dp), verticalAlignment = Alignment.CenterVertically) {
                    IconButton(onClick = fermer) { Icon(Icons.AutoMirrored.Filled.ArrowBack, stringResource(R.string.retour)) }
                    Column(Modifier.weight(1f)) {
                        TexteAjuste(stringResource(R.string.ia_resume_titre), 17.sp)
                        Text(etat.doc.nom, fontSize = 12.sp, color = Color.Gray, maxLines = 1, overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis)
                    }
                }
                HorizontalDivider(color = Color(0xFFE2E2E2))
                Column(Modifier.weight(1f).fillMaxWidth().verticalScroll(rememberScrollState()).padding(14.dp)) {
                    r.qui?.let { Text(stringResource(R.string.ia_fait_par, Ia.nom(it.first), it.second), fontSize = 11.sp, color = Color.Gray) }
                    Spacer(Modifier.height(6.dp))
                    Surface(shape = RoundedCornerShape(10.dp), color = Color.White) {
                        Text(markdownSimple(r.texte), Modifier.fillMaxWidth().padding(12.dp), fontSize = 15.sp, lineHeight = 22.sp)
                    }
                    if (r.echeances.isNotEmpty()) {
                        Spacer(Modifier.height(12.dp))
                        Text(stringResource(R.string.ia_dates_reperees), fontWeight = FontWeight.SemiBold)
                        Text(stringResource(R.string.ia_dates_aide), fontSize = 12.sp, color = Color.Gray)
                        r.echeances.forEach { e ->
                            Surface(Modifier.fillMaxWidth().padding(top = 6.dp), shape = RoundedCornerShape(8.dp), color = Color.White) {
                                Row(Modifier.padding(start = 10.dp), verticalAlignment = Alignment.CenterVertically) {
                                    Column(Modifier.weight(1f).padding(vertical = 8.dp)) {
                                        Text(dateFr(e.date) + if (e.heure.isNotEmpty()) " · " + e.heure else "", fontWeight = FontWeight.SemiBold, fontSize = 14.sp)
                                        Text(e.libelle, fontSize = 13.sp)
                                    }
                                    TextButton(onClick = { agenda(ctx, e, etat.doc.nom) }) { Text(stringResource(R.string.ia_agenda)) }
                                }
                            }
                        }
                    }
                }
                val dates = r.echeances.joinToString("") { "\n- " + dateFr(it.date) + (if (it.heure.isNotEmpty()) " " + it.heure else "") + " : " + it.libelle }
                val tout = brut + if (dates.isNotEmpty()) "\n\n" + ctx.getString(R.string.ia_dates) + dates else ""
                FlowRow(Modifier.fillMaxWidth().background(Color.White).padding(6.dp), horizontalArrangement = Arrangement.spacedBy(8.dp, Alignment.CenterHorizontally)) {
                    OutlinedButton(onClick = {
                        (ctx.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager).setPrimaryClip(ClipData.newPlainText("PhilPDF", tout))
                        android.widget.Toast.makeText(ctx, ctx.getString(R.string.copie_faite), android.widget.Toast.LENGTH_SHORT).show()
                    }) { Text(stringResource(R.string.copier)) }
                    OutlinedButton(onClick = {
                        val i = Intent(Intent.ACTION_SEND).setType("text/plain").putExtra(Intent.EXTRA_SUBJECT, ctx.getString(R.string.ia_resume_de, etat.doc.nom))
                            .putExtra(Intent.EXTRA_TEXT, tout)
                        try { ctx.startActivity(Intent.createChooser(i, ctx.getString(R.string.partager))) } catch (_: Exception) {}
                    }) { Text(stringResource(R.string.partager)) }
                    if (etat.doc.modifiable) OutlinedButton(onClick = {
                        portee.launch {
                            val ok = etat.doc.note(0, com.artifex.mupdf.fitz.Point(20f, 20f), tout, floatArrayOf(1f, 0.85f, 0.2f))
                            android.widget.Toast.makeText(ctx, ctx.getString(if (ok) R.string.ia_note_ajoutee else R.string.action_impossible), android.widget.Toast.LENGTH_LONG).show()
                        }
                    }) { Text(stringResource(R.string.ia_note_page1)) }
                    Button(onClick = fermer, colors = ButtonDefaults.buttonColors(containerColor = ROUGE)) { Text(stringResource(R.string.fermer)) }
                }
            }
        }
    }
}

private fun dateFr(iso: String): String = try {
    SimpleDateFormat("dd/MM/yyyy", Locale.FRANCE).format(SimpleDateFormat("yyyy-MM-dd", Locale.US).parse(iso)!!)
} catch (_: Exception) { iso }

/** Agenda du telephone, rendez-vous pre-rempli : vous verifiez et enregistrez vous-meme. */
private fun agenda(ctx: Context, e: Echeance, nom: String) {
    try {
        val jour = SimpleDateFormat("yyyy-MM-dd", Locale.US).parse(e.date)!!
        val i = Intent(Intent.ACTION_INSERT).setData(CalendarContract.Events.CONTENT_URI)
            .putExtra(CalendarContract.Events.TITLE, e.libelle)
            .putExtra(CalendarContract.Events.DESCRIPTION, ctx.getString(R.string.ia_d_apres, nom))
        if (e.heure.isNotEmpty()) {
            val (h, m) = e.heure.split(":").map { it.toInt() }
            val debut = java.util.Calendar.getInstance().apply { time = jour; set(java.util.Calendar.HOUR_OF_DAY, h); set(java.util.Calendar.MINUTE, m) }
            i.putExtra(CalendarContract.EXTRA_EVENT_BEGIN_TIME, debut.timeInMillis).putExtra(CalendarContract.EXTRA_EVENT_END_TIME, debut.timeInMillis + 3_600_000L)
        } else {
            val debut = java.util.Calendar.getInstance(java.util.TimeZone.getTimeZone("UTC")).apply { time = jour
                set(java.util.Calendar.HOUR_OF_DAY, 0); set(java.util.Calendar.MINUTE, 0) }
            i.putExtra(CalendarContract.EXTRA_EVENT_ALL_DAY, true).putExtra(CalendarContract.EXTRA_EVENT_BEGIN_TIME, debut.timeInMillis)
        }
        ctx.startActivity(i)
    } catch (x: Exception) {
        android.widget.Toast.makeText(ctx, ctx.getString(R.string.ia_pas_agenda), android.widget.Toast.LENGTH_LONG).show()
    }
}

/** Markdown courant (titres, puces, gras) : affiche sans les signes. */
fun markdownSimple(t: String): AnnotatedString = buildAnnotatedString {
    t.trim().lines().forEachIndexed { k, l0 ->
        if (k > 0) append("\n")
        var l = l0.trimEnd()
        val titre = Regex("^#{1,6}\\s+").find(l)
        if (titre != null) { withStyle(SpanStyle(fontWeight = FontWeight.Bold, fontSize = 17.sp)) { append(l.substring(titre.range.last + 1).replace("**", "")) }; return@forEachIndexed }
        Regex("^(\\s*)[-*•]\\s+").find(l)?.let { m -> append(m.groupValues[1] + "• "); l = l.substring(m.range.last + 1) }
        var i = 0
        while (i < l.length) {
            val d = l.indexOf("**", i)
            val f = if (d >= 0) l.indexOf("**", d + 2) else -1
            if (d < 0 || f < 0) { append(l.substring(i)); break }
            append(l.substring(i, d))
            withStyle(SpanStyle(fontWeight = FontWeight.Bold)) { append(l.substring(d + 2, f)) }
            i = f + 2
        }
    }
}

/** Le meme texte, sans les signes du Markdown (pour copier, partager, la note). */
fun texteSimple(t: String): String = markdownSimple(t).text


// ================================================================ nom propose apres une numerisation
private const val CONSIGNES_NOMMER = """Tu aides à nommer un document qui vient d'être numérisé. Lis-le et réponds en JSON :
{"date": "AAAA-MM-JJ (date du document)", "expediteur": "<organisme ou personne qui l'envoie, nom court usuel,
ex. CPAM, URSSAF, DGFiP, EDF, Maître Dupont>", "objet": "<objet en 2 à 6 mots>",
"type": "<facture, courrier, contrat, relevé, avis, attestation, ordonnance...>"}"""

/** « Date Expediteur – objet.pdf », comme sous Windows (dialogues_ia.nom_propose). */
fun nomPropose(j: JSONObject): String {
    val d = dateValide(j.optString("date")) ?: SimpleDateFormat("yyyy-MM-dd", Locale.US).format(java.util.Date())
    val exp = j.optString("expediteur").trim(); val obj = j.optString("objet").trim()
    val n = listOf(d, exp).filter { it.isNotEmpty() }.joinToString(" ") + if (obj.isNotEmpty()) " – $obj" else ""
    return n.replace(Regex("[\\\\/:*?\"<>|]+"), " ").replace(Regex("\\s+"), " ").trim().take(150) + ".pdf"
}

/**
 * Apres une numerisation (case cochee) : accord pour envoyer l'image de la premiere page, puis l'IA propose
 * « Date Expediteur – objet » ; l'utilisateur corrige. fini(fichier) : le PDF, renomme ou non.
 */
@Composable
fun NommerScan(pdf: java.io.File, premiere: android.graphics.Bitmap, fini: (java.io.File) -> Unit) {
    val ctx = LocalContext.current
    var accord by remember { mutableStateOf(false) }
    var propose by remember { mutableStateOf<String?>(null) }
    when {
        !accord -> AlertDialog(onDismissRequest = { fini(pdf) },
            title = { Text(stringResource(R.string.ia_nommer_titre)) },
            text = { Text(stringResource(R.string.ia_nommer_accord, Ia.nom(Ia.moteurs(ctx).firstOrNull()?.first))) },
            confirmButton = { TextButton(onClick = { accord = true }) { Text(stringResource(R.string.ia_envoyer)) } },
            dismissButton = { TextButton(onClick = { fini(pdf) }) { Text(stringResource(R.string.annuler)) } })
        propose == null -> EnvoiIa("", stringResource(R.string.ia_lit_document), {
            val petite = kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.Default) {
                val k = maxOf(1f, maxOf(premiere.width, premiere.height) / 1400f)
                val b = android.graphics.Bitmap.createScaledBitmap(premiere, (premiere.width / k).toInt(), (premiere.height / k).toInt(), true)
                java.io.ByteArrayOutputStream().also { b.compress(android.graphics.Bitmap.CompressFormat.JPEG, 80, it) }.toByteArray()
            }
            val jour = SimpleDateFormat("yyyy-MM-dd", Locale.US).format(java.util.Date())
            nomPropose(Ia.lireJson(Ia.demander(ctx, CONSIGNES_NOMMER + "\nDate du jour : $jour.", "Document numérisé : la première page est en image.",
                images = listOf(petite), json = true, maxJetons = 400)))
        }, { propose = it }, { fini(pdf) })
        else -> {
            var nom by remember { mutableStateOf(propose!!) }
            AlertDialog(onDismissRequest = { fini(pdf) },
                title = { Text(stringResource(R.string.ia_nommer_titre)) },
                text = { Column {
                    OutlinedTextField(nom, { nom = it }, Modifier.fillMaxWidth(), label = { Text(stringResource(R.string.ia_nommer_nom)) })
                    Spacer(Modifier.height(6.dp))
                    Text(stringResource(R.string.ia_nommer_verifier), fontSize = 12.sp, color = Color.Gray)
                } },
                confirmButton = { TextButton(onClick = {
                    val n = nom.trim().replace(Regex("[\\\\/:*?\"<>|]+"), " ").let { if (it.lowercase().endsWith(".pdf")) it else "$it.pdf" }
                    val cible = java.io.File(pdf.parentFile, n)
                    val ok = n.length > 4 && (cible == pdf || pdf.renameTo(cible))
                    Journal.ecrire("IA", "nom proposé après numérisation : $n${if (ok) "" else " (renommage impossible)"}")
                    fini(if (ok) cible else pdf)
                }) { Text(stringResource(R.string.ia_nommer_garder)) } },
                dismissButton = { TextButton(onClick = { fini(pdf) }) { Text(stringResource(R.string.ia_nommer_origine)) } })
        }
    }
}
