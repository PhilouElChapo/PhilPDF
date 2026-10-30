@file:OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class)

package io.github.philouelchapo.philpdf

import android.content.Context
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import kotlinx.coroutines.launch
import org.json.JSONArray
import org.json.JSONObject
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/** Signature ou paraphe dessine : traits en coordonnees 0..1, rapport largeur / hauteur du cadre. */
data class Trace(val id: String, val genre: String, val ratio: Float, val traits: List<List<Pair<Float, Float>>>)

/** Ce que l'on va poser d'un toucher sur la page. */
sealed class APoser {
    data class Traits(val t: Trace, val largeur: Float) : APoser()
    data class Tampon(val texte: String, val couleur: Color, val taille: Float) : APoser()
    /** Signature ou tampon repris de PhilPDF Windows (image PNG transparente). */
    data class Image(val png: java.io.File, val ratio: Float, val largeur: Float) : APoser()
}

/** Largeur et hauteur (en points) de ce qui sera pose : sert a l'apercu sur la page. */
fun APoser.taillePt(): Pair<Float, Float> = when (this) {
    is APoser.Traits -> largeur to largeur / t.ratio.coerceAtLeast(0.05f)
    is APoser.Image -> largeur to largeur / ratio.coerceAtLeast(0.05f)
    is APoser.Tampon -> texte.split("\n").let { l -> (l.maxOf { it.length } * taille * 0.62f + 16f) to (l.size * taille * 1.25f + 12f) }
}

/** Signatures et paraphes gardes sur l'appareil (repris de PhilPDF Windows a l'etape suivante). */
object Signatures {
    private fun prefs(ctx: Context) = ctx.getSharedPreferences("philpdf", Context.MODE_PRIVATE)

    fun liste(ctx: Context): List<Trace> = try {
        val a = JSONArray(prefs(ctx).getString("signatures", "[]"))
        (0 until a.length()).map { a.getJSONObject(it) }.map { o ->
            val tr = o.getJSONArray("traits")
            Trace(o.getString("id"), o.optString("genre", "signature"), o.optDouble("ratio", 3.0).toFloat(),
                (0 until tr.length()).map { i ->
                    val t = tr.getJSONArray(i)
                    (0 until t.length() / 2).map { j -> t.getDouble(2 * j).toFloat() to t.getDouble(2 * j + 1).toFloat() }
                })
        }
    } catch (_: Exception) { emptyList() }

    private fun ecrire(ctx: Context, l: List<Trace>) {
        val a = JSONArray()
        l.forEach { t ->
            val tr = JSONArray()
            t.traits.forEach { trait -> tr.put(JSONArray().apply { trait.forEach { (x, y) -> put(x.toDouble()); put(y.toDouble()) } }) }
            a.put(JSONObject().put("id", t.id).put("genre", t.genre).put("ratio", t.ratio.toDouble()).put("traits", tr))
        }
        prefs(ctx).edit().putString("signatures", a.toString()).apply()
    }

    fun ajouter(ctx: Context, t: Trace) = ecrire(ctx, liste(ctx) + t)
    fun supprimer(ctx: Context, id: String) = ecrire(ctx, liste(ctx).filter { it.id != id })
}

/** Encre des signatures et paraphes (bleu stylo), modifiable ensuite par appui long. */
val ENCRE = Color(0xFF0F3C8C)

/** Tampons prets a l'emploi (comme sous Windows) ; {date} = date du jour. */
val TAMPONS = listOf("REÇU LE", "PAYÉ LE", "VALIDÉ LE", "TRAITÉ LE", "COPIE CONFORME", "ANNULÉ", "BON POUR ACCORD", "URGENT")

/** Date ajoutee au tampon (comme sous Windows) : aucune, date du jour, ou date et heure. */
enum class Horodatage(val texte: Int) { AUCUN(R.string.h_aucun), DATE(R.string.h_date), DATE_HEURE(R.string.h_date_heure), HEURE(R.string.h_heure) }

fun maintenant(h: Horodatage): String = when (h) {
    Horodatage.AUCUN -> ""
    Horodatage.DATE -> SimpleDateFormat("dd/MM/yyyy", Locale.FRANCE).format(Date())
    Horodatage.DATE_HEURE -> SimpleDateFormat("dd/MM/yyyy 'à' HH:mm", Locale.FRANCE).format(Date())
    Horodatage.HEURE -> SimpleDateFormat("HH:mm", Locale.FRANCE).format(Date())
}

/** Texte final du tampon : « REÇU LE 30/10/2026 » ; « VALIDÉ » + date sur une 2e ligne ; codes {date} et {heure}. */
fun texteTampon(t: String, h: Horodatage): String {
    val d = maintenant(h)
    if ("{date}" in t || "{heure}" in t)
        return t.replace("{date}", SimpleDateFormat("dd/MM/yyyy", Locale.FRANCE).format(Date()))
            .replace("{heure}", SimpleDateFormat("HH:mm", Locale.FRANCE).format(Date()))
    if (d.isEmpty()) return t.removeSuffix(" LE").removeSuffix(" le")
    if (h == Horodatage.HEURE) return when {                // « REÇU A 14:32 » (majuscule sans accent)
        t.endsWith(" LE") -> t.removeSuffix(" LE") + " A $d"
        t.endsWith(" le") -> t.removeSuffix(" le") + " à $d"
        else -> "$t\n$d"
    }
    return if (t.endsWith(" LE") || t.endsWith(" le")) "$t $d" else "$t\n$d"
}

/** Volet / tiroir « Signer » : formulaires (toucher un champ), signatures, paraphes, tampons. */
@Composable
fun PanneauSigner(etat: EtatLecteur, tailles: List<Pair<Float, Float>>, choisi: () -> Unit = {}) {
    val ctx = LocalContext.current
    val portee = rememberCoroutineScope()
    var traces by remember { mutableStateOf(Signatures.liste(ctx)) }
    var dessiner by remember { mutableStateOf<String?>(null) }          // "signature" ou "paraphe"
    var tailleSig by remember { mutableFloatStateOf(150f) }
    var perso by remember { mutableStateOf("") }
    var couleurTampon by remember { mutableStateOf(PALETTE[2]) }
    var horo by remember { mutableStateOf(Horodatage.DATE) }
    if (!etat.doc.modifiable) {
        Text(stringResource(R.string.non_modifiable), Modifier.padding(16.dp), color = Color.Gray)
        return
    }
    fun poser(a: APoser) {
        etat.aPoser = a
        etat.annot.outil = Outil.POSER
        // apercu tout de suite au milieu de la page affichee : on le fait glisser, puis « Poser ici »
        val n = etat.page.coerceIn(0, (tailles.size - 1).coerceAtLeast(0))
        etat.fantome = tailles.getOrNull(n)?.let { (w, h) -> n to Offset(w / 2, h / 2) }
        choisi()
    }
    Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).padding(12.dp)) {
        Text(stringResource(R.string.remplir_aide), fontSize = 12.sp, color = Color.Gray)
        // signatures et tampons de PhilPDF Windows, recuperes par le compte Google (Accueil, en haut a droite)
        val biblio = remember { Bibliotheque.locaux(ctx).filter { it.genre != "filigranes" } }
        if (biblio.isEmpty()) {
            Spacer(Modifier.height(8.dp))
            Text(stringResource(if (Nuage.connecte(ctx)) R.string.biblio_vide_connecte else R.string.biblio_vide),
                fontSize = 12.sp, color = Color.Gray)
        }
        biblio.groupBy { it.genre }.forEach { (genre, liste) ->
            Spacer(Modifier.height(12.dp))
            Text(stringResource(R.string.de_vos_postes, Bibliotheque.nomGenre(genre)), fontWeight = FontWeight.SemiBold)
            liste.forEach { e ->
                val img = remember(e.id) { Bibliotheque.image(ctx, e)?.asImageBitmap() }
                Row(Modifier.fillMaxWidth().padding(vertical = 4.dp).background(Color.White, RoundedCornerShape(6.dp))
                    .border(1.dp, Color(0xFFE2E2E2), RoundedCornerShape(6.dp))
                    .clickable { poser(APoser.Image(Bibliotheque.apercu(ctx, e), e.ratio, if (genre == "paraphes") tailleSig / 3 else tailleSig)) }
                    .padding(6.dp), verticalAlignment = Alignment.CenterVertically) {
                    if (img != null) Image(img, null, Modifier.weight(1f).height(56.dp), contentScale = ContentScale.Fit)
                    else Spacer(Modifier.weight(1f))
                    Spacer(Modifier.width(8.dp))
                    Text(e.nom, Modifier.weight(1f), fontSize = 12.sp, color = Color.DarkGray, maxLines = 2, overflow = TextOverflow.Ellipsis)
                }
            }
        }
        for (genre in listOf("signature", "paraphe")) {
            Spacer(Modifier.height(12.dp))
            Text(stringResource(if (genre == "signature") R.string.mes_signatures else R.string.mes_paraphes), fontWeight = FontWeight.SemiBold)
            traces.filter { it.genre == genre }.forEach { t ->
                Row(Modifier.fillMaxWidth().padding(vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
                    ApercuTrace(t, Modifier.weight(1f).height(56.dp).background(Color.White, RoundedCornerShape(6.dp))
                        .border(1.dp, Color(0xFFE2E2E2), RoundedCornerShape(6.dp))
                        .clickable { poser(APoser.Traits(t, if (genre == "paraphe") tailleSig / 3 else tailleSig)) })
                    if (genre == "paraphe") TextButton(onClick = {
                        portee.launch {
                            etat.doc.parapherTout(tailleSig / 3, t.ratio, t.traits, ENCRE.versPdf(), 1.6f, tailles)
                        }
                    }) { Text(stringResource(R.string.toutes_pages), fontSize = 12.sp) }
                    TextButton(onClick = { Signatures.supprimer(ctx, t.id); traces = Signatures.liste(ctx) }) {
                        Text("✕", color = Color.Gray)
                    }
                }
            }
            OutlinedButton(onClick = { dessiner = genre }) {
                Text(stringResource(if (genre == "signature") R.string.ajouter_signature else R.string.ajouter_paraphe))
            }
        }
        Spacer(Modifier.height(8.dp))
        Text(stringResource(R.string.taille_signature, tailleSig.toInt()), fontSize = 13.sp)
        Slider(tailleSig, { tailleSig = it }, valueRange = 60f..300f)
        Spacer(Modifier.height(12.dp))
        Text(stringResource(R.string.tampons), fontWeight = FontWeight.SemiBold)
        Palette(couleurTampon) { couleurTampon = it }
        Spacer(Modifier.height(6.dp))

        FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            Horodatage.entries.forEach { h ->
                FilterChip(selected = horo == h, onClick = { horo = h }, label = { Text(stringResource(h.texte), fontSize = 12.sp) })
            }
        }
        Spacer(Modifier.height(6.dp))
        TAMPONS.forEach { t ->
            val final = texteTampon(t, horo)
            // apercu tel qu'il sera pose : texte et cadre de la couleur, fond transparent
            Text(final, Modifier.fillMaxWidth().padding(vertical = 3.dp)
                .border(2.dp, couleurTampon, RoundedCornerShape(4.dp))
                .clickable { poser(APoser.Tampon(texteTampon(t, horo), couleurTampon, 14f)) }.padding(8.dp),
                color = couleurTampon, fontWeight = FontWeight.Bold)
        }
        Spacer(Modifier.height(6.dp))
        OutlinedTextField(perso, { perso = it }, Modifier.fillMaxWidth(), singleLine = true,
            label = { Text(stringResource(R.string.tampon_perso)) })
        // codes a inserer : remplaces au moment de poser par la date ou l'heure du jour

        FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            AssistChip(onClick = { perso = (perso.trimEnd() + " {date}").trimStart() }, label = { Text(stringResource(R.string.code_date), fontSize = 12.sp) })
            AssistChip(onClick = { perso = (perso.trimEnd() + " {heure}").trimStart() }, label = { Text(stringResource(R.string.code_heure), fontSize = 12.sp) })
            AssistChip(onClick = { perso = (perso.trimEnd() + " {date} à {heure}").trimStart() }, label = { Text(stringResource(R.string.code_date_heure), fontSize = 12.sp) })
        }
        if (perso.isNotBlank()) {
            Text(texteTampon(perso, horo), Modifier.fillMaxWidth().padding(vertical = 3.dp)
                .border(2.dp, couleurTampon, RoundedCornerShape(4.dp))
                .clickable { poser(APoser.Tampon(texteTampon(perso, horo), couleurTampon, 14f)) }.padding(8.dp),
                color = couleurTampon, fontWeight = FontWeight.Bold)
        }
    }
    dessiner?.let { g ->
        PadSignature(g, { dessiner = null }) { t -> Signatures.ajouter(ctx, t); traces = Signatures.liste(ctx); dessiner = null }
    }
}

@Composable
fun ApercuTrace(t: Trace, modifier: Modifier) {
    Canvas(modifier.padding(6.dp)) {
        val l = minOf(size.width, size.height * t.ratio)
        val h = l / t.ratio
        val x0 = (size.width - l) / 2
        val y0 = (size.height - h) / 2
        t.traits.forEach { trait ->
            for (i in 1 until trait.size) {
                drawLine(Color(0xFF0F3C8C), Offset(x0 + trait[i - 1].first * l, y0 + trait[i - 1].second * h),
                    Offset(x0 + trait[i].first * l, y0 + trait[i].second * h), 3f, StrokeCap.Round)
            }
        }
    }
}

/** Grand cadre pour dessiner sa signature (ou son paraphe) au doigt. */
@Composable
fun PadSignature(genre: String, fermer: () -> Unit, valider: (Trace) -> Unit) {
    var traits by remember { mutableStateOf<List<List<Offset>>>(emptyList()) }
    var courant by remember { mutableStateOf<List<Offset>>(emptyList()) }
    var taille by remember { mutableStateOf(androidx.compose.ui.unit.IntSize(1, 1)) }
    Dialog(onDismissRequest = fermer, properties = DialogProperties(usePlatformDefaultWidth = false)) {
        Column(Modifier.fillMaxWidth(0.95f).background(Color.White, RoundedCornerShape(12.dp)).padding(12.dp)) {
            Text(stringResource(if (genre == "signature") R.string.dessinez_signature else R.string.dessinez_paraphe), fontWeight = FontWeight.SemiBold)
            Spacer(Modifier.height(8.dp))
            Box(Modifier.fillMaxWidth().aspectRatio(if (genre == "signature") 2.6f else 1.4f)
                .background(Color(0xFFFAFAFA)).border(1.dp, Color(0xFFBDBDBD))
                .pointerInput(Unit) {
                    taille = size
                    detectDragGestures(
                        onDragStart = { courant = listOf(it) },
                        onDrag = { ch, _ -> courant = courant + ch.position },
                        onDragEnd = { traits = traits + listOf(courant); courant = emptyList() },
                        onDragCancel = { courant = emptyList() })
                }) {
                Canvas(Modifier.fillMaxSize()) {
                    (traits + listOf(courant)).forEach { t ->
                        for (i in 1 until t.size) drawLine(Color(0xFF0F3C8C), t[i - 1], t[i], 5f, StrokeCap.Round)
                    }
                }
            }
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                TextButton(onClick = { traits = emptyList() }) { Text(stringResource(R.string.effacer)) }
                TextButton(onClick = fermer) { Text(stringResource(R.string.annuler)) }
                Button(onClick = {
                    val tous = traits.flatten()
                    if (tous.isEmpty()) { fermer(); return@Button }
                    // cadre serre autour du dessin, coordonnees ramenees a 0..1
                    val x0 = tous.minOf { it.x }; val x1 = tous.maxOf { it.x }
                    val y0 = tous.minOf { it.y }; val y1 = tous.maxOf { it.y }
                    val l = (x1 - x0).coerceAtLeast(1f); val h = (y1 - y0).coerceAtLeast(1f)
                    valider(Trace(System.currentTimeMillis().toString(), genre, l / h,
                        traits.filter { it.size > 1 }.map { t -> t.map { ((it.x - x0) / l) to ((it.y - y0) / h) } }))
                }, colors = ButtonDefaults.buttonColors(containerColor = ROUGE)) { Text(stringResource(R.string.enregistrer)) }
            }
        }
    }
}

/** Champ de formulaire touche : saisie du texte ou choix dans la liste (cases a cocher : basculees directement). */
@Composable
fun SaisieChamp(etat: EtatLecteur, c: InfoChamp, fermer: () -> Unit) {
    val portee = rememberCoroutineScope()
    var t by remember(c) { mutableStateOf(c.valeur) }
    AlertDialog(onDismissRequest = fermer,
        title = { Text(stringResource(R.string.champ)) },
        text = {
            if (c.options.isNotEmpty()) Column(Modifier.verticalScroll(rememberScrollState())) {
                c.options.forEach { o ->
                    Text(o, Modifier.fillMaxWidth().clickable { portee.launch { etat.doc.remplir(c, o); fermer() } }
                        .padding(vertical = 10.dp), fontWeight = if (o == c.valeur) FontWeight.Bold else FontWeight.Normal)
                }
            } else OutlinedTextField(t, { t = it }, Modifier.fillMaxWidth())
        },
        confirmButton = {
            if (c.options.isEmpty()) TextButton(onClick = { portee.launch { etat.doc.remplir(c, t); fermer() } }) {
                Text(stringResource(R.string.ok))
            }
        },
        dismissButton = { TextButton(onClick = fermer) { Text(stringResource(R.string.annuler)) } })
}
