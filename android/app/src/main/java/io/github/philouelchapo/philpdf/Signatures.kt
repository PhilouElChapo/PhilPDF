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

/** Meme chose, plus grand (k > 1) ou plus petit (k < 1), dans des limites raisonnables. */
fun APoser.agrandi(k: Float): APoser = when (this) {
    is APoser.Traits -> copy(largeur = (largeur * k).coerceIn(20f, 600f))
    is APoser.Image -> copy(largeur = (largeur * k).coerceIn(20f, 600f))
    is APoser.Tampon -> copy(taille = (taille * k).coerceIn(6f, 72f))
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

/** Mes tampons (texte) : ceux tout prets au depart, puis les votres ; ordre, favoris, categories, propres au telephone. */
data class MonTampon(val texte: String, val categorie: String, val favori: Boolean)

object MesTampons {
    val version = mutableIntStateOf(0)
    private fun prefs(ctx: Context) = ctx.getSharedPreferences("mes_tampons", Context.MODE_PRIVATE)
    fun liste(ctx: Context): List<MonTampon> = try {
        val t = prefs(ctx).getString("liste", null)
        if (t == null) TAMPONS.map { MonTampon(it, "", false) }
        else JSONArray(t).let { a -> (0 until a.length()).map { a.getJSONObject(it) }
            .map { MonTampon(it.optString("texte"), it.optString("categorie"), it.optBoolean("favori")) } }
    } catch (_: Exception) { TAMPONS.map { MonTampon(it, "", false) } }
    fun ecrire(ctx: Context, l: List<MonTampon>) {
        val a = JSONArray()
        l.forEach { a.put(JSONObject().put("texte", it.texte).put("categorie", it.categorie).put("favori", it.favori)) }
        prefs(ctx).edit().putString("liste", a.toString()).apply()
        version.intValue++
    }
    fun ajouter(ctx: Context, t: String) { if (t.isNotBlank() && liste(ctx).none { it.texte == t }) ecrire(ctx, liste(ctx) + MonTampon(t, "", false)) }
}

/** Liste de mes tampons : favoris en premier, categories repliables ; « Ranger » : fleches, modifier, supprimer. */
@Composable
fun MesTamponsListe(couleur: Color, horo: Horodatage, poser: (String) -> Unit) {
    val ctx = LocalContext.current
    val v = MesTampons.version.intValue
    val l = remember(v) { MesTampons.liste(ctx) }
    var ranger by remember { mutableStateOf(false) }
    var edite by remember { mutableStateOf<MonTampon?>(null) }
    Row(verticalAlignment = Alignment.CenterVertically) {
        Text(stringResource(R.string.mes_tampons), Modifier.weight(1f), fontSize = 13.sp, color = Color.Gray)
        TextButton(onClick = { ranger = !ranger }) { Text(stringResource(if (ranger) R.string.termine else R.string.ranger), fontSize = 12.sp) }
    }
    val groupes = LinkedHashMap<String, List<MonTampon>>()
    l.filter { it.favori }.takeIf { it.isNotEmpty() }?.let { groupes["★"] = it }
    l.groupBy { it.categorie }.toSortedMap(compareBy({ it.isEmpty() }, { it.lowercase() })).forEach { (c, x) -> groupes[c] = x }
    groupes.forEach { (cat, items) ->
        val cle = "tampons/$cat"
        var replie by remember(cle, v) { mutableStateOf(BiblioPerso.replie(ctx, cle)) }
        if (groupes.size > 1 || cat.isNotEmpty()) Row(Modifier.fillMaxWidth().clickable { replie = !replie; BiblioPerso.replier(ctx, cle, replie) }
            .padding(vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
            Text(if (replie) "▸" else "▾", color = Color.Gray)
            Spacer(Modifier.width(6.dp))
            Text((if (cat == "★") stringResource(R.string.favoris) else cat.ifEmpty { stringResource(R.string.sans_categorie) }) + "  (${items.size})",
                fontSize = 13.sp, fontWeight = FontWeight.SemiBold, color = Color(0xFF555555))
        }
        if (!replie) items.forEach { t ->
            Row(Modifier.fillMaxWidth().padding(vertical = 3.dp), verticalAlignment = Alignment.CenterVertically) {
                // apercu tel qu'il sera pose : texte et cadre de la couleur, centre, fond transparent
                Text(texteTampon(t.texte, horo), Modifier.weight(1f).border(2.dp, couleur, RoundedCornerShape(4.dp))
                    .clickable { poser(t.texte) }.padding(8.dp),
                    color = couleur, fontWeight = FontWeight.Bold, textAlign = androidx.compose.ui.text.style.TextAlign.Center)
                if (ranger && cat != "★") {
                    val i = l.indexOf(t)
                    // monter / descendre dans toute la liste (l'ordre vaut aussi dans la categorie)
                    TextButton(onClick = { if (i > 0) MesTampons.ecrire(ctx, l.toMutableList().apply { add(i - 1, removeAt(i)) }) },
                        enabled = i > 0, contentPadding = PaddingValues(4.dp)) { Text("↑") }
                    TextButton(onClick = { if (i < l.size - 1) MesTampons.ecrire(ctx, l.toMutableList().apply { add(i + 1, removeAt(i)) }) },
                        enabled = i < l.size - 1, contentPadding = PaddingValues(4.dp)) { Text("↓") }
                    TextButton(onClick = { edite = t }, contentPadding = PaddingValues(4.dp)) { Text("✎") }
                }
                IconButton(onClick = { MesTampons.ecrire(ctx, l.map { if (it == t) it.copy(favori = !it.favori) else it }) }) {
                    Icon(Icones.etoile(t.favori), stringResource(R.string.favoris), tint = Color.Unspecified)
                }
            }
        }
    }
    edite?.let { t ->
        var texte by remember(t) { mutableStateOf(t.texte) }
        var cat by remember(t) { mutableStateOf(t.categorie) }
        val cats = l.map { it.categorie }.filter { it.isNotEmpty() }.distinct()
        AlertDialog(onDismissRequest = { edite = null }, title = { Text(stringResource(R.string.tampon_modifier)) },
            text = {
                Column {
                    OutlinedTextField(texte, { texte = it }, label = { Text(stringResource(R.string.tampon_texte)) }, singleLine = true)
                    OutlinedTextField(cat, { cat = it }, label = { Text(stringResource(R.string.categorie)) }, singleLine = true)
                    if (cats.isNotEmpty()) FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        cats.forEach { c -> AssistChip(onClick = { cat = c }, label = { Text(c, fontSize = 12.sp) }) }
                    }
                    TextButton(onClick = { MesTampons.ecrire(ctx, l.filter { it != t }); edite = null }) {
                        Text(stringResource(R.string.supprimer), color = ROUGE)
                    }
                }
            },
            confirmButton = { TextButton(onClick = {
                MesTampons.ecrire(ctx, l.map { if (it == t) it.copy(texte = texte.trim().ifEmpty { it.texte }, categorie = cat.trim()) else it }); edite = null
            }) { Text(stringResource(R.string.appliquer)) } },
            dismissButton = { TextButton(onClick = { edite = null }) { Text(stringResource(R.string.annuler)) } })
    }
}

/** Favoris, ordre et categories repliees des elements de vos postes (propres a ce telephone). */
object BiblioPerso {
    private fun prefs(ctx: Context) = ctx.getSharedPreferences("biblio_perso", Context.MODE_PRIVATE)
    fun favori(ctx: Context, e: ElementBiblio): Boolean =
        if (prefs(ctx).contains("fav_" + e.id)) prefs(ctx).getBoolean("fav_" + e.id, false) else e.favori
    fun basculer(ctx: Context, e: ElementBiblio) = prefs(ctx).edit().putBoolean("fav_" + e.id, !favori(ctx, e)).apply()
    fun ordre(ctx: Context, e: ElementBiblio): Int = prefs(ctx).getInt("ordre_" + e.id, e.ordre)
    fun ranger(ctx: Context, l: List<ElementBiblio>) = prefs(ctx).edit().apply { l.forEachIndexed { i, e -> putInt("ordre_" + e.id, i) } }.apply()
    fun replie(ctx: Context, cle: String) = prefs(ctx).getBoolean("replie_$cle", false)
    fun replier(ctx: Context, cle: String, oui: Boolean) = prefs(ctx).edit().putBoolean("replie_$cle", oui).apply()
}

/** Tampons, signatures, paraphes de vos postes : favoris d'abord, puis par categorie (repliable), dans votre ordre.
 *  « Ranger » : fleches pour changer l'ordre ; etoile : favori. */
@Composable
fun BiblioVosPostes(genre: String, liste: List<ElementBiblio>, poser: (ElementBiblio) -> Unit, toutesPages: ((ElementBiblio) -> Unit)?) {
    val ctx = LocalContext.current
    var version by remember { mutableIntStateOf(0) }
    var ranger by remember { mutableStateOf(false) }
    val tries = remember(version, liste) {
        liste.sortedWith(compareBy({ BiblioPerso.ordre(ctx, it) }, { it.nom.lowercase() }))
    }
    Spacer(Modifier.height(12.dp))
    Row(verticalAlignment = Alignment.CenterVertically) {
        Text(stringResource(R.string.de_vos_postes, Bibliotheque.nomGenre(genre)), Modifier.weight(1f), fontWeight = FontWeight.SemiBold)
        TextButton(onClick = { ranger = !ranger }) { Text(stringResource(if (ranger) R.string.termine else R.string.ranger), fontSize = 12.sp) }
    }
    val favoris = tries.filter { BiblioPerso.favori(ctx, it) }
    val groupes = LinkedHashMap<String, List<ElementBiblio>>()
    if (favoris.isNotEmpty()) groupes["★"] = favoris
    tries.groupBy { it.categorie.ifBlank { "" } }.toSortedMap(compareBy({ it.isEmpty() }, { it.lowercase() })).forEach { (c, l) -> groupes[c] = l }
    key(version) {
        groupes.forEach { (cat, l) ->
            val cle = "$genre/$cat"
            var replie by remember(cle) { mutableStateOf(BiblioPerso.replie(ctx, cle)) }
            if (groupes.size > 1 || cat.isNotEmpty()) Row(Modifier.fillMaxWidth().clickable { replie = !replie; BiblioPerso.replier(ctx, cle, replie) }
                .padding(vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                Text(if (replie) "▸" else "▾", color = Color.Gray)
                Spacer(Modifier.width(6.dp))
                Text((if (cat == "★") stringResource(R.string.favoris) else cat.ifEmpty { stringResource(R.string.sans_categorie) }) + "  (${l.size})",
                    fontSize = 13.sp, fontWeight = FontWeight.SemiBold, color = Color(0xFF555555))
            }
            if (!replie) l.forEach { e ->
                val img = remember(e.id) { Bibliotheque.image(ctx, e)?.asImageBitmap() }
                Row(Modifier.fillMaxWidth().padding(vertical = 3.dp).background(Color.White, RoundedCornerShape(6.dp))
                    .border(1.dp, Color(0xFFE2E2E2), RoundedCornerShape(6.dp))
                    .clickable { poser(e) }.padding(6.dp), verticalAlignment = Alignment.CenterVertically) {
                    if (img != null) Image(img, null, Modifier.weight(1f).height(52.dp), contentScale = ContentScale.Fit)
                    else Spacer(Modifier.weight(1f))
                    Spacer(Modifier.width(6.dp))
                    Text(e.nom, Modifier.weight(1f), fontSize = 12.sp, color = Color.DarkGray, maxLines = 2, overflow = TextOverflow.Ellipsis)
                    if (ranger && cat != "★") {
                        val i = l.indexOf(e)
                        TextButton(onClick = {
                            if (i > 0) { val m = l.toMutableList(); m.add(i - 1, m.removeAt(i)); BiblioPerso.ranger(ctx, m); version++ }
                        }, enabled = i > 0, contentPadding = PaddingValues(4.dp)) { Text("↑") }
                        TextButton(onClick = {
                            if (i < l.size - 1) { val m = l.toMutableList(); m.add(i + 1, m.removeAt(i)); BiblioPerso.ranger(ctx, m); version++ }
                        }, enabled = i < l.size - 1, contentPadding = PaddingValues(4.dp)) { Text("↓") }
                    }
                    toutesPages?.let { f -> TextButton(onClick = { f(e) }, contentPadding = PaddingValues(4.dp)) {
                        Text(stringResource(R.string.toutes_pages), fontSize = 11.sp) } }
                    IconButton(onClick = { BiblioPerso.basculer(ctx, e); version++ }) {
                        Icon(Icones.etoile(BiblioPerso.favori(ctx, e)),
                            stringResource(R.string.favoris), tint = Color.Unspecified)
                    }
                }
            }
        }
    }
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
        // appui long > Changer : le nouveau prend la place (et la largeur) de l'ancien, sans apercu a placer
        etat.remplacer?.let { ancien ->
            etat.remplacer = null
            val cx = (ancien.rect[0] + ancien.rect[2]) / 2
            val cy = (ancien.rect[1] + ancien.rect[3]) / 2
            val larg = (ancien.rect[2] - ancien.rect[0]).coerceAtLeast(20f)
            val pt = com.artifex.mupdf.fitz.Point(cx, cy)
            val d = etat.doc
            (etat.portee ?: portee).launch {
                d.supprimerAnnotation(ancien)
                when (a) {
                    is APoser.Traits -> d.poserTraits(ancien.page, pt, larg, a.t.ratio, a.t.traits, ENCRE.versPdf(), if (a.t.genre == "paraphe") 1.6f else 2f)
                    is APoser.Image -> d.image(ancien.page, pt, larg, a.ratio, a.png.readBytes())
                    is APoser.Tampon -> d.tampon(ancien.page, pt, a.texte, a.couleur.versPdf(), a.taille)
                }
            }
            choisi()
            return
        }
        etat.aPoser = a
        etat.annot.outil = Outil.POSER
        // apercu tout de suite au milieu de la page affichee : on le fait glisser, puis « Poser ici »
        val n = etat.page.coerceIn(0, (tailles.size - 1).coerceAtLeast(0))
        etat.fantome = tailles.getOrNull(n)?.let { (w, h) -> n to Offset(w / 2, h / 2) }
        choisi()
    }
    Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).padding(12.dp)) {
        if (etat.remplacer != null) {
            Row(Modifier.fillMaxWidth().background(Color(0xFFE8F0FE), RoundedCornerShape(8.dp)).padding(8.dp),
                verticalAlignment = Alignment.CenterVertically) {
                Text(stringResource(R.string.remplacer_aide), Modifier.weight(1f), fontSize = 13.sp)
                TextButton(onClick = { etat.remplacer = null }) { Text(stringResource(R.string.annuler)) }
            }
            Spacer(Modifier.height(8.dp))
        }
        Text(stringResource(R.string.remplir_aide), fontSize = 12.sp, color = Color.Gray)
        // signatures et tampons de PhilPDF Windows, recuperes par le compte Google (Accueil, en haut a droite)
        val biblio = remember { Bibliotheque.locaux(ctx).filter { it.genre != "filigranes" } }
        if (biblio.isEmpty()) {
            Spacer(Modifier.height(8.dp))
            Text(stringResource(if ((Nuage.synchro(ctx) != null)) R.string.biblio_vide_connecte else R.string.biblio_vide),
                fontSize = 12.sp, color = Color.Gray)
        }
        biblio.groupBy { it.genre }.forEach { (genre, liste) ->
            BiblioVosPostes(genre, liste, poser = { e ->
                poser(APoser.Image(Bibliotheque.apercu(ctx, e), e.ratio, if (genre == "paraphes") tailleSig / 3 else tailleSig))
            }, toutesPages = if (genre != "paraphes") null else { e ->
                portee.launch {
                    val f = Bibliotheque.apercu(ctx, e)
                    if (f.exists()) etat.doc.imageToutesPages(tailleSig / 3, e.ratio, f.readBytes(), tailles)
                }
            })
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
        MesTamponsListe(couleurTampon, horo) { t -> poser(APoser.Tampon(texteTampon(t, horo), couleurTampon, 14f)) }
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
                color = couleurTampon, fontWeight = FontWeight.Bold, textAlign = androidx.compose.ui.text.style.TextAlign.Center)
            // le garder dans « Mes tampons » (on le retrouve, on le range, on le met en favori)
            OutlinedButton(onClick = { MesTampons.ajouter(ctx, perso.trim()); perso = ""; MesTampons.version.intValue++ }) {
                Text(stringResource(R.string.tampon_garder), fontSize = 13.sp)
            }
        }
        // signature numerique (certificat), comme PhilPDF Windows
        SectionSignatureNumerique(etat, choisi)
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
    Fenetre(fermer) {
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

/** Champ de formulaire touche : saisie du texte (avec son format : date, montant, telephone...) ou choix dans la liste. */
@Composable
fun SaisieChamp(etat: EtatLecteur, c: InfoChamp, fermer: () -> Unit) {
    val portee = rememberCoroutineScope()
    var t by remember(c) { mutableStateOf(c.valeur) }
    var erreur by remember { mutableStateOf<String?>(null) }
    val r = remember(c) { try { JSONObject(c.regles) } catch (_: Exception) { JSONObject() } }
    val fmt = r.optJSONObject("format")
    val genre = fmt?.optString("genre") ?: "aucun"
    // ce qui est attendu, dit avant de taper (comme les formats d'Acrobat)
    val attendu = when (genre) {
        "date" -> stringResource(R.string.attendu_date, fmt!!.optString("date", "dd/mm/yyyy").replace("yyyy", "aaaa").replace("dd", "jj"))
        "heure" -> stringResource(R.string.attendu_heure, fmt!!.optString("heure", "HH:MM"))
        "nombre" -> stringResource(R.string.attendu_nombre) + fmt!!.optString("symbole").let { if (it.isNotBlank()) " ($it)" else "" }
        "pourcentage" -> stringResource(R.string.attendu_pourcentage)
        "masque" -> stringResource(R.string.attendu_masque, fmt!!.optString("masque"))
        else -> null
    }
    val clavier = when (genre) {
        "nombre", "pourcentage" -> androidx.compose.ui.text.input.KeyboardType.Decimal
        "masque" -> if (fmt!!.optString("masque").all { it == '9' || !it.isLetterOrDigit() }) androidx.compose.ui.text.input.KeyboardType.Number
            else androidx.compose.ui.text.input.KeyboardType.Text
        else -> if (r.optString("controle") == "email") androidx.compose.ui.text.input.KeyboardType.Email else androidx.compose.ui.text.input.KeyboardType.Text
    }
    fun valider(v: String) = portee.launch { val e = etat.doc.remplir(c, v); if (e == null) fermer() else erreur = e }
    AlertDialog(onDismissRequest = fermer,
        title = { Text(c.nom.ifEmpty { stringResource(R.string.champ) }) },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState())) {
                r.optJSONObject("aide")?.optString("entree")?.takeIf { it.isNotBlank() }?.let { Text(it, fontSize = 13.sp, color = Color(0xFF0F6CBD)) }
                if (c.options.isNotEmpty()) c.options.forEach { o ->
                    Text(o, Modifier.fillMaxWidth().clickable { valider(o) }
                        .padding(vertical = 10.dp), fontWeight = if (o == c.valeur) FontWeight.Bold else FontWeight.Normal)
                } else {
                    OutlinedTextField(t, { t = it; erreur = null }, Modifier.fillMaxWidth(), singleLine = genre != "aucun",
                        keyboardOptions = androidx.compose.foundation.text.KeyboardOptions(keyboardType = clavier),
                        supportingText = attendu?.let { a -> { Text(a, fontSize = 12.sp) } })
                    if (genre == "date" || genre == "heure") TextButton(onClick = {
                        t = Regles.ecrireDate(if (genre == "date") fmt!!.optString("date", "dd/mm/yyyy") else fmt!!.optString("heure", "HH:MM"))
                    }) { Text(stringResource(if (genre == "date") R.string.bouton_aujourdhui else R.string.maintenant)) }
                }
                erreur?.let { Text(it, color = ROUGE, fontSize = 13.sp, modifier = Modifier.padding(top = 6.dp)) }
            }
        },
        confirmButton = {
            if (c.options.isEmpty()) TextButton(onClick = { valider(t) }) { Text(stringResource(R.string.ok)) }
        },
        dismissButton = { TextButton(onClick = fermer) { Text(stringResource(R.string.annuler)) } })
}
