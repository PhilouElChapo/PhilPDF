package io.github.philouelchapo.philpdf

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.artifex.mupdf.fitz.PDFAnnotation
import kotlinx.coroutines.launch

/** Outils d'annotation (comme sous Windows). MAIN = lire, faire defiler ; appui long sur une annotation = la modifier. */
enum class Outil(val icone: String, val texte: Int) {
    MAIN("oeil", R.string.outil_lire),
    SURLIGNER("surligner", R.string.outil_surligner),
    SOULIGNER("souligner", R.string.outil_souligner),
    BARRER("barrer", R.string.outil_barrer),
    NOTE("commentaire", R.string.outil_note),
    DESSIN("modifier", R.string.outil_dessin),
    RECTANGLE("tout", R.string.outil_rectangle),
    ELLIPSE("aucun", R.string.outil_ellipse),
    FLECHE("suivante", R.string.outil_fleche),
    GOMME("supprimer", R.string.outil_gomme),
    POSER("signer", R.string.outil_poser);          // signature, paraphe ou tampon a poser d'un toucher

    val texteSurligne: Boolean get() = this == SURLIGNER || this == SOULIGNER || this == BARRER
    val forme: Boolean get() = this == RECTANGLE || this == ELLIPSE || this == FLECHE
}

/** Couleurs proposees (memes teintes par defaut que PhilPDF Windows). */
val PALETTE = listOf(0xFFFFE600, 0xFF0F6CBD, 0xFFD32F2F, 0xFF2E7D32, 0xFFFF9800, 0xFF8E24AA, 0xFF000000, 0xFF9E9E9E)
    .map { Color(it) }

fun couleurDefaut(o: Outil): Color = when (o) {
    Outil.SURLIGNER, Outil.NOTE -> PALETTE[0]
    Outil.SOULIGNER -> PALETTE[1]
    Outil.BARRER -> PALETTE[2]
    else -> PALETTE[2]
}

fun Color.versPdf(): FloatArray = floatArrayOf(red, green, blue)
fun FloatArray.versCouleur(): Color = when (size) {
    1 -> Color(this[0], this[0], this[0])
    3 -> Color(this[0], this[1], this[2])
    4 -> Color((1 - this[0]) * (1 - this[3]), (1 - this[1]) * (1 - this[3]), (1 - this[2]) * (1 - this[3]))
    else -> Color.Black
}

/** Reglages de l'outil choisi : couleur, epaisseur, opacite (gardes par outil pendant la session). */
class ReglagesAnnot {
    var outil by mutableStateOf(Outil.MAIN)
    private val couleurs = mutableStateMapOf<Outil, Color>()
    var epaisseur by mutableFloatStateOf(2f)
    var opaciteSurlignage by mutableFloatStateOf(0.45f)
    fun couleur(o: Outil = outil): Color = couleurs[o] ?: couleurDefaut(o)
    fun choisirCouleur(c: Color) { couleurs[outil] = c }
    fun opacite(o: Outil = outil): Float = if (o == Outil.SURLIGNER) opaciteSurlignage else 1f
}

/** Volet (tablette) ou tiroir (telephone) « Annoter » : outils, couleur, epaisseur, opacite. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun PanneauAnnoter(etat: EtatLecteur, choisi: () -> Unit = {}) {
    val r = etat.annot
    if (!etat.doc.modifiable) {
        Text(stringResource(R.string.non_modifiable), Modifier.padding(16.dp), color = Color.Gray)
        return
    }
    Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).padding(12.dp)) {
        Text(stringResource(R.string.annoter), fontWeight = FontWeight.SemiBold)
        Spacer(Modifier.height(8.dp))
        FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Outil.entries.filter { it != Outil.POSER }.forEach { o ->
                val actif = r.outil == o
                Column(Modifier.width(76.dp).background(if (actif) Color(0xFFFCEBEC) else Color.White, RoundedCornerShape(8.dp))
                    .border(1.dp, if (actif) ROUGE else Color(0xFFE2E2E2), RoundedCornerShape(8.dp))
                    .clickable { r.outil = o; choisi() }.padding(vertical = 8.dp),
                    horizontalAlignment = Alignment.CenterHorizontally) {
                    Icon(Icones.get(o.icone, if (actif) ROUGE else Color(0xFF444444)), null)
                    Text(stringResource(o.texte), fontSize = 11.sp, maxLines = 2)
                }
            }
        }
        if (r.outil != Outil.MAIN && r.outil != Outil.GOMME && r.outil != Outil.POSER) {
            Spacer(Modifier.height(14.dp))
            Text(stringResource(R.string.couleur), fontSize = 13.sp)
            Palette(r.couleur()) { r.choisirCouleur(it) }
            if (r.outil == Outil.DESSIN || r.outil.forme) {
                Spacer(Modifier.height(10.dp))
                Text(stringResource(R.string.epaisseur, r.epaisseur.toInt()), fontSize = 13.sp)
                Slider(r.epaisseur, { r.epaisseur = it }, valueRange = 1f..12f, steps = 10)
            }
            if (r.outil == Outil.SURLIGNER) {
                Spacer(Modifier.height(10.dp))
                Text(stringResource(R.string.opacite, (r.opaciteSurlignage * 100).toInt()), fontSize = 13.sp)
                Slider(r.opaciteSurlignage, { r.opaciteSurlignage = it }, valueRange = 0.15f..1f)
            }
        }
        Spacer(Modifier.height(12.dp))
        Text(stringResource(aideOutil(r.outil)), fontSize = 12.sp, color = Color.Gray)
    }
}

fun aideOutil(o: Outil): Int = when {
    o == Outil.MAIN -> R.string.aide_main
    o.texteSurligne -> R.string.aide_texte
    o == Outil.NOTE -> R.string.aide_note
    o == Outil.GOMME -> R.string.aide_gomme
    o == Outil.POSER -> R.string.aide_poser
    else -> R.string.aide_dessin
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun Palette(actuelle: Color, choisir: (Color) -> Unit) {
    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp),
        modifier = Modifier.padding(top = 6.dp)) {
        PALETTE.forEach { c ->
            val oui = c.value == actuelle.value
            Box(Modifier.size(34.dp).background(c, CircleShape)
                .border(if (oui) 3.dp else 1.dp, if (oui) Color(0xFF1462C2) else Color(0xFFBDBDBD), CircleShape)
                .clickable { choisir(c) })
        }
    }
}

/** Appui long sur une annotation : couleur, epaisseur, opacite, texte de la note, ou suppression. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun FeuilleAnnotation(etat: EtatLecteur, info: InfoAnnot, fermer: () -> Unit) {
    val portee = rememberCoroutineScope()
    var couleur by remember(info) { mutableStateOf(info.couleur.versCouleur()) }
    var epaisseur by remember(info) { mutableFloatStateOf(info.epaisseur.coerceIn(1f, 12f)) }
    var opacite by remember(info) { mutableFloatStateOf(info.opacite.coerceIn(0.15f, 1f)) }
    var texte by remember(info) { mutableStateOf(info.texte) }
    val trait = info.genre == PDFAnnotation.TYPE_INK || info.genre == PDFAnnotation.TYPE_SQUARE ||
        info.genre == PDFAnnotation.TYPE_CIRCLE || info.genre == PDFAnnotation.TYPE_LINE
    ModalBottomSheet(onDismissRequest = fermer, containerColor = Color(0xFFF7F7F7)) {
        Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).padding(16.dp)) {
            Text(stringResource(R.string.annotation_titre), fontWeight = FontWeight.SemiBold)
            Spacer(Modifier.height(10.dp))
            Text(stringResource(R.string.couleur), fontSize = 13.sp)
            Palette(couleur) { couleur = it }
            if (trait) {
                Spacer(Modifier.height(10.dp))
                Text(stringResource(R.string.epaisseur, epaisseur.toInt()), fontSize = 13.sp)
                Slider(epaisseur, { epaisseur = it }, valueRange = 1f..12f, steps = 10)
            }
            Spacer(Modifier.height(10.dp))
            Text(stringResource(R.string.opacite, (opacite * 100).toInt()), fontSize = 13.sp)
            Slider(opacite, { opacite = it }, valueRange = 0.15f..1f)
            Spacer(Modifier.height(10.dp))
            OutlinedTextField(texte, { texte = it }, Modifier.fillMaxWidth(), label = { Text(stringResource(R.string.texte_note)) },
                minLines = 2)
            Spacer(Modifier.height(14.dp))
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                TextButton(onClick = {
                    portee.launch { etat.doc.supprimerAnnotation(info); fermer() }
                }) { Text(stringResource(R.string.supprimer), color = Color(0xFFC62828)) }
                Row {
                    TextButton(onClick = fermer) { Text(stringResource(R.string.annuler)) }
                    Button(onClick = {
                        portee.launch {
                            etat.doc.modifierAnnotation(info, couleur.versPdf(), opacite, if (trait) epaisseur else null,
                                if (texte != info.texte) texte else null)
                            fermer()
                        }
                    }, colors = ButtonDefaults.buttonColors(containerColor = ROUGE)) { Text(stringResource(R.string.appliquer)) }
                }
            }
        }
    }
}
