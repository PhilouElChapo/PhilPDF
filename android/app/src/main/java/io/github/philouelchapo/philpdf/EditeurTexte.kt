@file:OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class)

package io.github.philouelchapo.philpdf

import androidx.compose.foundation.layout.*
import androidx.compose.ui.Alignment
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.TextRange
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.OffsetMapping
import androidx.compose.ui.text.input.TextFieldValue
import androidx.compose.ui.text.input.TransformedText
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import kotlinx.coroutines.launch

/** Fenetre « Modifier le texte » : une ligne tapee = une ligne de la page, a la meme place. */
@Composable
fun EditeurTexte(etat: EtatLecteur, par: Paragraphe, fermer: () -> Unit) {
    val ctx = LocalContext.current
    val l0 = par.lignes.first()
    // texte et style de chaque caractere (gras, italique) : G et I ne touchent que la selection, s'il y en a une
    var valeur by remember(par) { mutableStateOf(TextFieldValue(par.texte, TextRange(par.texte.length))) }
    val stylesDepart = remember(par) { TexteModif.stylesDe(par).let { if (it.size == par.texte.length) it else List(par.texte.length) { l0.gras to l0.italique } } }
    var styles by remember(par) { mutableStateOf(stylesDepart) }
    var stylesTouches by remember(par) { mutableStateOf(false) }
    val texte = valeur.text
    fun changerTexte(v: String) { styles = suivreStyles(valeur.text, v, styles, valeur.selection.min); valeur = TextFieldValue(v, TextRange(v.length)) }
    var taille by remember(par) { mutableFloatStateOf(l0.taille) }
    val sel = valeur.selection
    val partie = if (sel.collapsed) styles else styles.subList(sel.min.coerceIn(0, styles.size), sel.max.coerceIn(0, styles.size))
    val gras = if (sel.collapsed) styles.any { it.first } else partie.isNotEmpty() && partie.all { it.first }
    val italique = if (sel.collapsed) styles.any { it.second } else partie.isNotEmpty() && partie.all { it.second }
    fun basculer(i: Int) {
        val actif = if (i == 0) !gras else !italique
        val a = if (sel.collapsed) 0 else sel.min; val z = if (sel.collapsed) styles.size else sel.max
        styles = styles.mapIndexed { k, st -> if (k in a until z) (if (i == 0) actif to st.second else st.first to actif) else st }
        stylesTouches = true
    }
    val couleurOrigine = Color(l0.argb or (0xFF shl 24))
    var couleur by remember(par) { mutableStateOf(couleurOrigine) }
    var droite by remember(par) { mutableStateOf(false) }
    var occupe by remember { mutableStateOf(false) }
    // IA : action choisie (corriger, reformuler...), texte d'avant pour revenir en arriere
    var menuIa by remember { mutableStateOf(false) }
    var actionIa by remember { mutableStateOf<Pair<String, String?>?>(null) }   // consigne, moteur force
    var libre by remember { mutableStateOf(false) }
    var avantIa by remember(par) { mutableStateOf<String?>(null) }
    val t = par.table
    val manquantes = t?.manquantes(texte.replace("\n", ""))?.filter { !it.isWhitespace() || t.code(' ') == null } ?: emptyList()
    val styleChange = stylesTouches && styles != stylesDepart
    val originale = t != null && !styleChange && manquantes.isEmpty()
    val secours = TexteModif.policeSecours(l0, styles.firstOrNull { it != (l0.gras to l0.italique) }?.first ?: l0.gras,
        styles.firstOrNull { it != (l0.gras to l0.italique) }?.second ?: l0.italique)
    val nomOrigine = t?.nomBase?.substringAfter('+')?.ifEmpty { null }
        ?: if (l0.police.startsWith("Type3")) stringResource(R.string.police_integree) else l0.police

    Fenetre({ if (!occupe) fermer() }) {
        Surface(Modifier.fillMaxWidth(0.96f).widthIn(max = 620.dp), shape = RoundedCornerShape(16.dp)) {
            Column(Modifier.padding(16.dp)) {
              // tout defile, sauf les boutons « Annuler » / « Appliquer », toujours visibles en bas
              Column(Modifier.weight(1f, fill = false).verticalScroll(rememberScrollState())) {
                Text(stringResource(R.string.modifier_texte), fontWeight = FontWeight.SemiBold, fontSize = 19.sp)
                Spacer(Modifier.height(8.dp))
                OutlinedTextField(valeur, { v ->
                        styles = suivreStyles(valeur.text, v.text, styles, valeur.selection.min)
                        valeur = v
                    }, Modifier.fillMaxWidth(), minLines = 2, maxLines = 9,
                    label = { Text(stringResource(R.string.texte_lignes)) },
                    visualTransformation = VisualTransformation { t -> TransformedText(enStyles(t, styles), OffsetMapping.Identity) })
                Text(stringResource(R.string.aide_gras_selection), fontSize = 12.sp, color = Color.Gray)
                FlowRow(verticalArrangement = Arrangement.Center) {
                    Box {
                        OutlinedButton(onClick = { menuIa = true }, enabled = !occupe && texte.isNotBlank()) {
                            Icon(Icones.get("ia", ROUGE), null, tint = Color.Unspecified)
                            Spacer(Modifier.width(6.dp)); Text(stringResource(R.string.ia_ameliorer))
                        }
                        DropdownMenu(menuIa, { menuIa = false }) {
                            ActionsTexteIa.forEach { (cle, lib) ->
                                DropdownMenuItem(text = { Text(stringResource(lib)) }, onClick = {
                                    menuIa = false
                                    if (cle == "libre") libre = true else actionIa = ConsignesTexteIa.getValue(cle) to null
                                })
                            }
                        }
                    }
                    avantIa?.let { a -> TextButton(onClick = { changerTexte(a); avantIa = null }) { Text(stringResource(R.string.ia_revenir)) } }
                    if (avantIa != null) BoutonSignalerIa("Améliorer le texte") { texte }
                }
                if (avantIa != null) Text(stringResource(R.string.ia_texte_recoupe), fontSize = 12.sp, color = Color.Gray)
                Spacer(Modifier.height(8.dp))
                // police : gardee, ou remplacee (et pourquoi), dit AVANT d'appliquer
                val (msg, coul) = when {
                    t == null -> stringResource(R.string.police_illisible, nomOrigine, secours) to Color(0xFF9A5B00)
                    styleChange -> stringResource(R.string.police_style, secours) to Color(0xFF9A5B00)
                    manquantes.isNotEmpty() -> stringResource(R.string.police_lettres, manquantes.joinToString(" "), secours) to Color(0xFF9A5B00)
                    else -> stringResource(R.string.police_gardee, nomOrigine) to Color(0xFF2E7D32)
                }
                Text(msg, fontSize = 13.sp, color = coul)
                Spacer(Modifier.height(10.dp))
                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    OutlinedButton(onClick = { taille = (taille - 0.5f).coerceAtLeast(4f) }) { Text("A−") }
                    Text(stringResource(R.string.taille_pt, String.format(java.util.Locale.FRANCE, "%.1f", taille)),
                        Modifier.align(androidx.compose.ui.Alignment.CenterVertically))
                    OutlinedButton(onClick = { taille = (taille + 0.5f).coerceAtMost(96f) }) { Text("A+") }
                    FilterChip(gras, { basculer(0) }, label = { Text("G", fontWeight = FontWeight.Bold) })
                    FilterChip(italique, { basculer(1) }, label = { Text("I", fontStyle = androidx.compose.ui.text.font.FontStyle.Italic) })
                    FilterChip(!droite, { droite = false }, label = { Text(stringResource(R.string.aligner_gauche)) })
                    FilterChip(droite, { droite = true }, label = { Text(stringResource(R.string.aligner_droite)) })
                }
                Spacer(Modifier.height(8.dp))
                Text(stringResource(R.string.couleur), fontSize = 13.sp)
                Palette(couleur) { couleur = it }
                TextButton(onClick = { couleur = couleurOrigine }) { Text(stringResource(R.string.couleur_origine)) }
                Spacer(Modifier.height(4.dp))
                Text(stringResource(R.string.aide_texte_fenetre), fontSize = 12.sp, color = Color.Gray)
              }
                Spacer(Modifier.height(12.dp))
                FlowRow(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(4.dp, Alignment.End)) {   // passe a la ligne, jamais coupe
                    TextButton(onClick = fermer, enabled = !occupe) { Text(stringResource(R.string.annuler)) }
                    Button(onClick = {
                        occupe = true
                        val lignes = texte.split("\n")
                        // styles choisis : par ligne (le retour a la ligne n'a pas de style)
                        val voulus = if (!styleChange || styles.size != texte.length) null else {
                            var k = 0
                            lignes.map { l -> styles.subList(k, k + l.length).also { k += l.length + 1 } }
                        }
                        (etat.portee ?: return@Button).launch {
                            val r = etat.doc.reecrireTexte(par, lignes, taille, couleur.toArgb() and 0xFFFFFF, l0.gras, l0.italique,
                                droite, voulus)
                            android.widget.Toast.makeText(ctx,
                                if (!r.ok) ctx.getString(R.string.texte_echec, r.message)
                                else if (r.originale) ctx.getString(R.string.texte_ok_origine, r.police)
                                else ctx.getString(R.string.texte_ok_secours, r.police), android.widget.Toast.LENGTH_LONG).show()
                            if (r.ok && r.deborde) etat.message = ctx.getString(R.string.texte_deborde_cadre)
                            occupe = false
                            fermer()
                        }
                    }, enabled = !occupe && texte.isNotBlank(), colors = ButtonDefaults.buttonColors(containerColor = ROUGE)) {
                        Text(stringResource(R.string.appliquer))
                    }
                }
            }
        }
    }
    IaTexte(texte, actionIa, libre, { c -> libre = false; actionIa = c }, { r ->
        actionIa = null
        if (r.isNotBlank() && r != texte) { avantIa = texte; changerTexte(Ia.recouper(r, texte)) }
        else android.widget.Toast.makeText(ctx, ctx.getString(R.string.ia_rien_change), android.widget.Toast.LENGTH_SHORT).show()
    }) { actionIa = null }
}

/** Styles apres une frappe : debut et fin inchanges gardent le leur ; le texte tape prend le style de la lettre
 *  d'avant (ou d'apres, en tout debut). */
internal fun suivreStyles(avant: String, apres: String, st: List<Pair<Boolean, Boolean>>, curseur: Int): List<Pair<Boolean, Boolean>> {
    if (avant == apres) return st
    if (st.size != avant.length) return List(apres.length) { st.firstOrNull() ?: (false to false) }
    var p = 0
    while (p < avant.length && p < apres.length && avant[p] == apres[p]) p++
    var q = 0
    while (q < avant.length - p && q < apres.length - p && avant[avant.length - 1 - q] == apres[apres.length - 1 - q]) q++
    val modele = st.getOrNull(p - 1) ?: st.getOrNull(p) ?: (false to false)
    return st.subList(0, p) + List(apres.length - p - q) { modele } + st.subList(avant.length - q, avant.length)
}

/** Le texte de la zone, avec ses parties en gras et en italique. */
internal fun enStyles(t: AnnotatedString, st: List<Pair<Boolean, Boolean>>): AnnotatedString {
    if (st.size != t.text.length) return t
    return AnnotatedString.Builder(t.text).apply {
        var k = 0
        while (k < st.size) {
            var j = k
            while (j < st.size && st[j] == st[k]) j++
            if (st[k].first || st[k].second)
                addStyle(SpanStyle(fontWeight = if (st[k].first) FontWeight.Bold else FontWeight.Normal,
                    fontStyle = if (st[k].second) FontStyle.Italic else FontStyle.Normal), k, j)
            k = j
        }
    }.toAnnotatedString()
}

private val ActionsTexteIa = listOf("corriger" to R.string.ia_corriger, "clarifier" to R.string.ia_clarifier, "formel" to R.string.ia_formel,
    "simple" to R.string.ia_simple, "court" to R.string.ia_court, "libre" to R.string.ia_libre)

/** Memes consignes que sous Windows (app/ia_texte.py). */
private val ConsignesTexteIa = mapOf(
    "corriger" to "Corrige l'orthographe, la grammaire, les accords et la ponctuation du texte. Ne change ni le style, ni le vocabulaire, ni l'ordre des phrases.",
    "clarifier" to "Reformule le texte pour qu'il soit plus clair et plus fluide, en gardant exactement le même sens, les mêmes informations et à peu près la même longueur.",
    "formel" to "Reformule le texte dans un registre plus formel et professionnel (vouvoiement), même sens, mêmes informations.",
    "simple" to "Reformule le texte avec des phrases plus courtes et des mots plus simples, même sens, mêmes informations.",
    "court" to "Raccourcis le texte d'environ un tiers en gardant toutes les informations importantes.")

private const val REGLES_TEXTE_IA = "Réponds uniquement par le texte final, sans guillemets, sans commentaire ni explication. Garde les " +
    "retours à la ligne, les noms propres, les nombres, les dates et les montants tels quels. Écris en " +
    "français sauf si le texte est dans une autre langue : garde alors sa langue."

/** Fenetres de l'IA du texte (consigne libre, envoi), montrees par EditeurTexte. */
@Composable
private fun IaTexte(texte: String, action: Pair<String, String?>?, libre: Boolean, finLibre: (Pair<String, String?>?) -> Unit,
                    fini: (String) -> Unit, annule: () -> Unit) {
    val ctx = LocalContext.current
    if (libre) ConsigneIa(stringResource(R.string.ia_libre_titre), "texte",
        stringResource(R.string.ia_regles_texte) + "\n\n" + REGLES_TEXTE_IA, true, { finLibre(null) }) { c, m -> finLibre(c to m) }
    action?.let { (consigne, m) ->
        val envoi = texte.split("\n").joinToString(" ").replace(Regex(" {2,}"), " ").trim()
        EnvoiIa(envoi, stringResource(R.string.ia_travaille_texte), {
            var r = Ia.demander(ctx, consigne + "\n\n" + REGLES_TEXTE_IA, envoi, force = m).trim()
            if (r.length > 1 && r.first() in "«\"“" && r.last() in "»\"”" && envoi.firstOrNull() !in listOf('«', '"', '“')) r = r.substring(1, r.length - 1).trim()
            r
        }, { r -> fini(r) }, annule, force = m)
    }
}
