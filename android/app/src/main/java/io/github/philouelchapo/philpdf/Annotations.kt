@file:OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class)

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
    TEXTE("modifier", R.string.outil_texte),        // modifier le texte de la page (police d'origine gardee)
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
        if (r.outil != Outil.MAIN && r.outil != Outil.GOMME && r.outil != Outil.POSER && r.outil != Outil.TEXTE) {
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
    o == Outil.TEXTE -> R.string.aide_texte_modif
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

/** Nom de ce qui est sous le doigt (titre de la feuille d'appui long). */
fun nomGenre(g: Int): Int = when (g) {
    PDFAnnotation.TYPE_HIGHLIGHT -> R.string.g_surlignage
    PDFAnnotation.TYPE_UNDERLINE, PDFAnnotation.TYPE_SQUIGGLY -> R.string.g_soulignement
    PDFAnnotation.TYPE_STRIKE_OUT -> R.string.g_barre
    PDFAnnotation.TYPE_TEXT -> R.string.g_note
    PDFAnnotation.TYPE_INK -> R.string.g_trace
    PDFAnnotation.TYPE_SQUARE -> R.string.outil_rectangle
    PDFAnnotation.TYPE_CIRCLE -> R.string.outil_ellipse
    PDFAnnotation.TYPE_LINE -> R.string.outil_fleche
    PDFAnnotation.TYPE_FREE_TEXT -> R.string.g_tampon
    PDFAnnotation.TYPE_STAMP -> R.string.g_image
    else -> R.string.g_autre
}

/** Appui long sur un marquage, un dessin, une note, un tampon : le changer ou le supprimer. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun FeuilleAnnotation(etat: EtatLecteur, info: InfoAnnot, fermer: () -> Unit) {
    val portee = rememberCoroutineScope()
    var couleur by remember(info) { mutableStateOf(info.couleur.versCouleur()) }
    var epaisseur by remember(info) { mutableFloatStateOf(info.epaisseur.coerceIn(1f, 12f)) }
    var opacite by remember(info) { mutableFloatStateOf(info.opacite.coerceIn(0.15f, 1f)) }
    var texte by remember(info) { mutableStateOf(info.texte) }
    var genre by remember(info) { mutableIntStateOf(info.genre) }
    val marquage = info.genre in listOf(PDFAnnotation.TYPE_HIGHLIGHT, PDFAnnotation.TYPE_UNDERLINE,
        PDFAnnotation.TYPE_SQUIGGLY, PDFAnnotation.TYPE_STRIKE_OUT)
    val trait = info.genre == PDFAnnotation.TYPE_INK || info.genre == PDFAnnotation.TYPE_SQUARE ||
        info.genre == PDFAnnotation.TYPE_CIRCLE || info.genre == PDFAnnotation.TYPE_LINE || info.genre == PDFAnnotation.TYPE_FREE_TEXT
    val avecTexte = info.genre == PDFAnnotation.TYPE_TEXT || info.genre == PDFAnnotation.TYPE_FREE_TEXT
    ModalBottomSheet(onDismissRequest = fermer, containerColor = Color(0xFFF7F7F7),
        sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)) {
        Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).padding(horizontal = 16.dp, vertical = 4.dp)) {
            // en tete : ce que c'est, et le supprimer tout de suite
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Text(stringResource(nomGenre(info.genre)), Modifier.weight(1f), fontWeight = FontWeight.SemiBold, fontSize = 17.sp)
                OutlinedButton(onClick = { portee.launch { etat.doc.supprimerAnnotation(info); fermer() } }) {
                    Icon(Icones.get("supprimer", Color(0xFFC62828)), null)
                    Spacer(Modifier.width(6.dp))
                    Text(stringResource(R.string.supprimer), color = Color(0xFFC62828))
                }
            }
            if (marquage) {
                Spacer(Modifier.height(10.dp))
                Text(stringResource(R.string.changer_en), fontSize = 13.sp)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    for ((g, o) in listOf(PDFAnnotation.TYPE_HIGHLIGHT to Outil.SURLIGNER, PDFAnnotation.TYPE_UNDERLINE to Outil.SOULIGNER,
                        PDFAnnotation.TYPE_STRIKE_OUT to Outil.BARRER)) {
                        FilterChip(selected = genre == g || (g == PDFAnnotation.TYPE_UNDERLINE && genre == PDFAnnotation.TYPE_SQUIGGLY),
                            onClick = { genre = g; if (g == PDFAnnotation.TYPE_HIGHLIGHT && opacite > 0.9f) opacite = 0.45f
                                else if (g != PDFAnnotation.TYPE_HIGHLIGHT) opacite = 1f },
                            label = { Text(stringResource(o.texte)) },
                            leadingIcon = { Icon(Icones.get(o.icone), null, Modifier.size(18.dp)) })
                    }
                }
            }
            if (info.objet) {
                // signature, paraphe, tampon : deplacer, taille, en mettre un autre a la place
                Spacer(Modifier.height(10.dp))
                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedButton(onClick = { etat.decalageDepl = androidx.compose.ui.geometry.Offset.Zero; etat.deplacement = info; fermer() }) {
                        Text(stringResource(R.string.deplacer))
                    }
                    OutlinedButton(onClick = { (etat.portee ?: portee).launch { etat.doc.transformer(info, 0f, 0f, 1f / 1.2f) } }) { Text("−") }
                    OutlinedButton(onClick = { (etat.portee ?: portee).launch { etat.doc.transformer(info, 0f, 0f, 1.2f) } }) { Text("+") }
                    OutlinedButton(onClick = { etat.remplacer = info; etat.ouvrirSigner = true; fermer() }) {
                        Text(stringResource(R.string.changer))
                    }
                }
            }
            // une image (signature ou tampon de vos postes) n'a pas de couleur a changer
            if (info.genre != PDFAnnotation.TYPE_STAMP) {
                Spacer(Modifier.height(10.dp))
                Text(stringResource(R.string.couleur), fontSize = 13.sp)
                Palette(couleur) { couleur = it }
            }
            if (trait) {
                Spacer(Modifier.height(10.dp))
                Text(stringResource(R.string.epaisseur, epaisseur.toInt()), fontSize = 13.sp)
                Slider(epaisseur, { epaisseur = it }, valueRange = 1f..12f, steps = 10)
            }
            Spacer(Modifier.height(10.dp))
            Text(stringResource(R.string.opacite, (opacite * 100).toInt()), fontSize = 13.sp)
            Slider(opacite, { opacite = it }, valueRange = 0.15f..1f)
            if (avecTexte) {
                Spacer(Modifier.height(10.dp))
                OutlinedTextField(texte, { texte = it }, Modifier.fillMaxWidth(), label = { Text(stringResource(R.string.texte_note)) },
                    minLines = 2)
            }
            Spacer(Modifier.height(14.dp))
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                TextButton(onClick = fermer) { Text(stringResource(R.string.annuler)) }
                Button(onClick = {
                    portee.launch {
                        if (marquage && genre != info.genre) etat.doc.changerGenre(info, genre, couleur.versPdf(), opacite)
                        else etat.doc.modifierAnnotation(info, if (info.genre == PDFAnnotation.TYPE_STAMP) null else couleur.versPdf(), opacite, if (trait) epaisseur else null,
                            if (avecTexte && texte != info.texte) texte else null)
                        fermer()
                    }
                }, colors = ButtonDefaults.buttonColors(containerColor = ROUGE)) { Text(stringResource(R.string.appliquer)) }
            }
            Spacer(Modifier.height(16.dp))
        }
    }
}
