package io.github.philouelchapo.philpdf

import androidx.compose.foundation.background
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.artifex.mupdf.fitz.PDFWidget
import kotlinx.coroutines.launch

private fun coul(t: Triple<Float, Float, Float>) = Color(t.first, t.second, t.third)

@Composable
private fun Case(oui: Boolean, texte: String, changer: (Boolean) -> Unit) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Checkbox(oui, changer)
        Text(texte, fontSize = 13.sp)
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun Couleurs(actuelle: Triple<Float, Float, Float>, choisir: (Triple<Float, Float, Float>) -> Unit) {
    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        ChampsPdf.COULEURS.forEach { c ->
            val oui = kotlin.math.abs(c.first - actuelle.first) + kotlin.math.abs(c.second - actuelle.second) + kotlin.math.abs(c.third - actuelle.third) < 0.05f
            Box(Modifier.padding(vertical = 4.dp).size(if (oui) 34.dp else 28.dp).background(coul(c), CircleShape),
                contentAlignment = Alignment.Center) {
                TextButton(onClick = { choisir(c) }, Modifier.fillMaxSize(), contentPadding = PaddingValues(0.dp)) {
                    if (oui) Text("✓", color = Color.White, fontSize = 14.sp)
                }
            }
        }
    }
}

/**
 * Reglages generaux d'un champ, comme la fenetre Windows : info-bulle, obligatoire, lecture seule, affichage ;
 * texte (plusieurs lignes, longueur, alignement, valeur par defaut) ; police, taille, couleur ; liste (tri, choix par
 * defaut, saisie libre) ; case (signe, couleur, valeur, cochee par defaut) ; bouton (texte, action).
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun SectionsReglages(c: InfoChamp, p: ChampsPdf.Proprietes, r: org.json.JSONObject, choix: String, nbPages: Int, maj: (() -> Unit) -> Unit) {
    val g = c.genre
    val estTexte = g == PDFWidget.TYPE_TEXT
    val estListe = g == PDFWidget.TYPE_COMBOBOX || g == PDFWidget.TYPE_LISTBOX || (c.options.isNotEmpty() && g != PDFWidget.TYPE_RADIOBUTTON)
    val estCase = g == PDFWidget.TYPE_CHECKBOX || g == PDFWidget.TYPE_RADIOBUTTON
    val estBouton = g == PDFWidget.TYPE_BUTTON
    // ---- general
    Titre(R.string.prop_general)
    Champ(p.info, stringResource(R.string.prop_info_bulle)) { p.info = it }
    Row {
        Case(p.obligatoire, stringResource(R.string.prop_obligatoire)) { maj { p.obligatoire = it } }
        Case(p.lecture, stringResource(R.string.prop_lecture_seule)) { maj { p.lecture = it } }
    }
    Puces(listOf("0" to stringResource(R.string.aff_visible), "1" to stringResource(R.string.aff_masque),
        "2" to stringResource(R.string.aff_non_imprime), "3" to stringResource(R.string.aff_masque_imprime)), "${p.affichage}") { k -> maj { p.affichage = k.toInt() } }
    // ---- texte
    if (estTexte) {
        Titre(R.string.prop_texte)
        Case(p.multi, stringResource(R.string.prop_plusieurs_lignes)) { maj { p.multi = it } }
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(stringResource(R.string.prop_longueur_max), fontSize = 13.sp)
            TextButton(onClick = { maj { p.maxlen = (p.maxlen - 1).coerceAtLeast(0) } }) { Text("−") }
            Text(if (p.maxlen == 0) stringResource(R.string.prop_illimitee) else "${p.maxlen}", fontSize = 13.sp)
            TextButton(onClick = { maj { p.maxlen += 1 } }) { Text("+") }
            TextButton(onClick = { maj { p.maxlen += 10 } }) { Text("+10") }
        }
        Puces(listOf("0" to stringResource(R.string.prop_gauche), "1" to stringResource(R.string.prop_centre),
            "2" to stringResource(R.string.prop_droite)), "${p.alignement}") { k -> maj { p.alignement = k.toInt() } }
        Champ(p.defaut, stringResource(R.string.prop_valeur_defaut)) { p.defaut = it }
    }
    // ---- police du texte
    if (estTexte || estListe) {
        Titre(R.string.prop_police)
        Puces(ChampsPdf.POLICES.map { (k, v) -> k to v }, p.police) { k -> maj { p.police = k } }
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(stringResource(R.string.prop_taille), fontSize = 13.sp)
            TextButton(onClick = { maj { p.taille = (p.taille - 1).coerceAtLeast(0f) } }) { Text("−") }
            Text(if (p.taille == 0f) stringResource(R.string.prop_taille_auto) else "${p.taille.toInt()} pt", fontSize = 13.sp)
            TextButton(onClick = { maj { p.taille = (if (p.taille == 0f) 9f else p.taille + 1).coerceAtMost(96f) } }) { Text("+") }
        }
        Couleurs(p.couleur) { co -> maj { p.couleur = co } }
    }
    // ---- liste : tri, choix par defaut, saisie libre
    if (estListe) {
        Titre(R.string.prop_liste)
        val l = choix.lines().map { it.trim() }.filter { it.isNotEmpty() }
        Case(p.trier, stringResource(R.string.prop_trier)) { maj { p.trier = it } }
        if (g != PDFWidget.TYPE_LISTBOX) Case(p.libre, stringResource(R.string.prop_saisie_libre)) { maj { p.libre = it } }
        Text(stringResource(R.string.prop_choix_defaut), fontSize = 13.sp)
        Puces(listOf("" to stringResource(R.string.prop_aucun_vide)) + (if (p.trier) l.sortedBy { it.lowercase() } else l).map { it to it }, p.defaut) { k ->
            maj { p.defaut = k } }
    }
    // ---- case a cocher : signe, couleur, valeur, cochee par defaut
    if (estCase) {
        Titre(R.string.prop_coche)
        Puces(ChampsPdf.STYLES_COCHE.map { (k, v) -> k to v.second }, p.style) { k -> maj { p.style = k } }
        Couleurs(p.couleurSigne) { co -> maj { p.couleurSigne = co } }
        if (g == PDFWidget.TYPE_CHECKBOX) {
            Champ(p.valeurCochee, stringResource(R.string.prop_valeur_cochee)) { p.valeurCochee = it }
            Case(p.cocheeDefaut, stringResource(R.string.prop_cochee_defaut)) { maj { p.cocheeDefaut = it } }
        }
    }
    // ---- bouton : texte, action
    if (estBouton) {
        Titre(R.string.prop_bouton)
        Champ(p.legende, stringResource(R.string.prop_texte_bouton)) { p.legende = it }
        val a = r.optJSONObject("action") ?: org.json.JSONObject().put("genre", "reinitialiser").also { r.put("action", it) }
        Puces(ChampsPdf.ACTIONS.map { it to stringResource(nomAction(it)) }, a.optString("genre")) { k -> maj { a.put("genre", k) } }
        when (a.optString("genre")) {
            "email" -> {
                Champ(a.optString("email"), stringResource(R.string.bouton_destinataire)) { a.put("email", it) }
                Champ(a.optString("sujet"), stringResource(R.string.bouton_objet)) { a.put("sujet", it) }
            }
            "page" -> Row(verticalAlignment = Alignment.CenterVertically) {
                Text(stringResource(R.string.page_n, a.optInt("page", 1)), fontSize = 13.sp)
                TextButton(onClick = { maj { a.put("page", (a.optInt("page", 1) - 1).coerceAtLeast(1)) } }) { Text("−") }
                TextButton(onClick = { maj { a.put("page", (a.optInt("page", 1) + 1).coerceAtMost(nbPages)) } }) { Text("+") }
            }
        }
    }
}

fun nomAction(k: String) = when (k) {
    "imprimer" -> R.string.action_imprimer
    "email" -> R.string.action_email
    "page" -> R.string.action_page
    else -> R.string.action_reinitialiser
}

/** JavaScript du champ, evenement par evenement : le code produit par PhilPDF (lecture) et le votre (modifiable). */
@Composable
fun SectionJavaScript(js: Map<String, Pair<String, String>>, perso: MutableMap<String, String>, r: org.json.JSONObject, maj: (() -> Unit) -> Unit) {
    var ouvert by remember { mutableStateOf(false) }
    Spacer(Modifier.height(12.dp))
    TextButton(onClick = { ouvert = !ouvert }, contentPadding = PaddingValues(0.dp)) {
        Text((if (ouvert) "▾ " else "▸ ") + stringResource(R.string.prop_javascript), fontSize = 14.sp)
    }
    if (!ouvert) return
    Text(stringResource(R.string.js_aide), fontSize = 12.sp, color = Color.Gray)
    val seul = (0 until (r.optJSONArray("js_seul")?.length() ?: 0)).map { r.getJSONArray("js_seul").getString(it) }.toMutableSet()
    for (k in ChampsPdf.EVENEMENTS) {
        val (phil, _) = js[k] ?: ("" to "")
        Spacer(Modifier.height(8.dp))
        Text(stringResource(nomEvenement(k)), fontSize = 13.sp, color = Color(0xFF0F6CBD))
        if (phil.isNotEmpty()) Text(phil, fontSize = 11.sp, fontFamily = FontFamily.Monospace, color = Color(0xFF555555),
            modifier = Modifier.fillMaxWidth().background(Color(0xFFF2F2F2), RoundedCornerShape(6.dp)).padding(6.dp))
        var t by remember(k) { mutableStateOf(perso[k] ?: "") }
        OutlinedTextField(t, { t = it; perso[k] = it }, label = { Text(stringResource(R.string.js_votre_code)) },
            textStyle = LocalTextStyle.current.copy(fontFamily = FontFamily.Monospace, fontSize = 12.sp),
            minLines = 1, maxLines = 6, modifier = Modifier.fillMaxWidth())
        if (phil.isNotEmpty() || k in seul) Row(verticalAlignment = Alignment.CenterVertically) {
            Checkbox(k in seul, { oui -> maj { val s = if (oui) seul + k else seul - k; r.put("js_seul", org.json.JSONArray(s.toList())) } })
            Text(stringResource(R.string.js_mon_code_seul), fontSize = 12.sp)
        }
    }
}

private fun nomEvenement(k: String) = when (k) {
    "K" -> R.string.js_k; "F" -> R.string.js_f; "V" -> R.string.js_v; "C" -> R.string.js_c
    "Fo" -> R.string.js_fo; "Bl" -> R.string.js_bl; else -> R.string.js_u
}

/** Ordre de tabulation de la page : fleches pour ranger, ou ordre automatique (lignes, de gauche a droite). */
@Composable
fun DialogueOrdre(etat: EtatLecteur, n: Int, fermer: () -> Unit) {
    val portee = rememberCoroutineScope()
    var liste by remember { mutableStateOf<List<Triple<Int, String, com.artifex.mupdf.fitz.Rect>>?>(null) }
    LaunchedEffect(n) { liste = etat.doc.ordreChamps(n) }
    Fenetre(fermer) {
        Surface(Modifier.fillMaxWidth(0.94f).widthIn(max = 560.dp).fillMaxHeight(0.85f), shape = RoundedCornerShape(16.dp)) {
            Column(Modifier.padding(16.dp)) {
                Text(stringResource(R.string.ordre_titre, n + 1), fontSize = 18.sp)
                Text(stringResource(R.string.ordre_aide), fontSize = 12.sp, color = Color.Gray)
                val l = liste
                Column(Modifier.weight(1f).padding(top = 8.dp)) {
                    if (l == null) CircularProgressIndicator()
                    else if (l.isEmpty()) Text(stringResource(R.string.ordre_aucun), fontSize = 13.sp)
                    else androidx.compose.foundation.lazy.LazyColumn {
                        items(l.size) { i ->
                            val e = l[i]
                            Row(Modifier.fillMaxWidth().padding(vertical = 2.dp).background(Color(0xFFF6F6F6), RoundedCornerShape(8.dp))
                                .padding(horizontal = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                                Text("${i + 1}.", fontSize = 13.sp, color = Color.Gray, modifier = Modifier.width(30.dp))
                                Text(e.second, fontSize = 14.sp, modifier = Modifier.weight(1f), maxLines = 1)
                                TextButton(onClick = { liste = l.toMutableList().apply { add(i - 1, removeAt(i)) } }, enabled = i > 0,
                                    contentPadding = PaddingValues(4.dp)) { Text("↑") }
                                TextButton(onClick = { liste = l.toMutableList().apply { add(i + 1, removeAt(i)) } }, enabled = i < l.size - 1,
                                    contentPadding = PaddingValues(4.dp)) { Text("↓") }
                            }
                        }
                    }
                }
                OutlinedButton(onClick = { liste = l?.sortedWith(compareBy({ Math.round(it.third.y0 / 8f) }, { it.third.x0 })) },
                    enabled = !l.isNullOrEmpty(), modifier = Modifier.fillMaxWidth()) { Text(stringResource(R.string.ordre_auto)) }
                Row(Modifier.fillMaxWidth().padding(top = 8.dp), horizontalArrangement = Arrangement.End) {
                    TextButton(onClick = fermer) { Text(stringResource(R.string.annuler)) }
                    Button(onClick = { portee.launch { liste?.let { etat.doc.poserOrdre(n, it.map { x -> x.first }) }; fermer() } },
                        enabled = !l.isNullOrEmpty(), colors = ButtonDefaults.buttonColors(containerColor = ROUGE)) { Text(stringResource(R.string.appliquer)) }
                }
            }
        }
    }
}

/** Nouveau bouton d'action (cadre trace) : son texte et ce qu'il fait. */
@Composable
fun DialogueBouton(etat: EtatLecteur, n: Int, rect: com.artifex.mupdf.fitz.Rect, nbPages: Int, fermer: () -> Unit) {
    val portee = rememberCoroutineScope()
    var genre by remember { mutableStateOf("reinitialiser") }
    val libelleAction = stringResource(nomAction(genre))
    var legende by remember(genre) { mutableStateOf(libelleAction) }
    var email by remember { mutableStateOf("") }
    var sujet by remember { mutableStateOf(etat.doc.nom.removeSuffix(".pdf")) }
    var page by remember { mutableIntStateOf(1) }
    AlertDialog(onDismissRequest = fermer, title = { Text(stringResource(R.string.prop_bouton)) },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState())) {
                Text(stringResource(R.string.bouton_quand_clic), fontSize = 13.sp)
                Puces(ChampsPdf.ACTIONS.map { it to stringResource(nomAction(it)) }, genre) { genre = it }
                OutlinedTextField(legende, { legende = it }, label = { Text(stringResource(R.string.prop_texte_bouton)) }, singleLine = true,
                    modifier = Modifier.fillMaxWidth())
                when (genre) {
                    "email" -> {
                        OutlinedTextField(email, { email = it }, label = { Text(stringResource(R.string.bouton_destinataire)) }, singleLine = true,
                            modifier = Modifier.fillMaxWidth())
                        OutlinedTextField(sujet, { sujet = it }, label = { Text(stringResource(R.string.bouton_objet)) }, singleLine = true,
                            modifier = Modifier.fillMaxWidth())
                    }
                    "page" -> Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(stringResource(R.string.page_n, page), fontSize = 13.sp)
                        TextButton(onClick = { page = (page - 1).coerceAtLeast(1) }) { Text("−") }
                        TextButton(onClick = { page = (page + 1).coerceAtMost(nbPages) }) { Text("+") }
                    }
                }
            }
        },
        confirmButton = {
            TextButton(onClick = {
                val a = org.json.JSONObject().put("genre", genre)
                if (genre == "email") a.put("email", email.trim()).put("sujet", sujet.trim())
                if (genre == "page") a.put("page", page)
                portee.launch { etat.doc.creerBouton(n, rect, legende.trim().ifEmpty { libelleAction }, a); fermer() }
            }) { Text(stringResource(R.string.appliquer)) }
        },
        dismissButton = { TextButton(onClick = fermer) { Text(stringResource(R.string.annuler)) } })
}
