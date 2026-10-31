@file:OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class)

package io.github.philouelchapo.philpdf

import androidx.compose.foundation.layout.*
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
import androidx.compose.ui.text.font.FontWeight
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
    var texte by remember(par) { mutableStateOf(par.texte) }
    var taille by remember(par) { mutableFloatStateOf(l0.taille) }
    var gras by remember(par) { mutableStateOf(l0.gras) }
    var italique by remember(par) { mutableStateOf(l0.italique) }
    val couleurOrigine = Color(l0.argb or (0xFF shl 24))
    var couleur by remember(par) { mutableStateOf(couleurOrigine) }
    var droite by remember(par) { mutableStateOf(false) }
    var occupe by remember { mutableStateOf(false) }
    val t = par.table
    val manquantes = t?.manquantes(texte.replace("\n", ""))?.filter { !it.isWhitespace() || t.code(' ') == null } ?: emptyList()
    val styleChange = gras != l0.gras || italique != l0.italique
    val originale = t != null && !styleChange && manquantes.isEmpty()
    val secours = TexteModif.policeSecours(l0, gras, italique)
    val nomOrigine = t?.nomBase?.substringAfter('+')?.ifEmpty { null } ?: l0.police

    Dialog(onDismissRequest = { if (!occupe) fermer() }, properties = DialogProperties(usePlatformDefaultWidth = false)) {
        Surface(Modifier.fillMaxWidth(0.96f).widthIn(max = 620.dp), shape = RoundedCornerShape(16.dp)) {
            Column(Modifier.verticalScroll(rememberScrollState()).padding(16.dp)) {
                Text(stringResource(R.string.modifier_texte), fontWeight = FontWeight.SemiBold, fontSize = 19.sp)
                Spacer(Modifier.height(8.dp))
                OutlinedTextField(texte, { texte = it }, Modifier.fillMaxWidth(), minLines = 2,
                    label = { Text(stringResource(R.string.texte_lignes)) })
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
                    FilterChip(gras, { gras = !gras }, label = { Text("G", fontWeight = FontWeight.Bold) })
                    FilterChip(italique, { italique = !italique }, label = { Text("I", fontStyle = androidx.compose.ui.text.font.FontStyle.Italic) })
                    FilterChip(!droite, { droite = false }, label = { Text(stringResource(R.string.aligner_gauche)) })
                    FilterChip(droite, { droite = true }, label = { Text(stringResource(R.string.aligner_droite)) })
                }
                Spacer(Modifier.height(8.dp))
                Text(stringResource(R.string.couleur), fontSize = 13.sp)
                Palette(couleur) { couleur = it }
                TextButton(onClick = { couleur = couleurOrigine }) { Text(stringResource(R.string.couleur_origine)) }
                Spacer(Modifier.height(4.dp))
                Text(stringResource(R.string.aide_texte_fenetre), fontSize = 12.sp, color = Color.Gray)
                Spacer(Modifier.height(12.dp))
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                    TextButton(onClick = fermer, enabled = !occupe) { Text(stringResource(R.string.annuler)) }
                    Button(onClick = {
                        occupe = true
                        val lignes = texte.split("\n")
                        (etat.portee ?: return@Button).launch {
                            val r = etat.doc.reecrireTexte(par, lignes, taille, couleur.toArgb() and 0xFFFFFF, gras, italique, droite)
                            android.widget.Toast.makeText(ctx,
                                if (!r.ok) ctx.getString(R.string.texte_echec, r.message)
                                else if (r.originale) ctx.getString(R.string.texte_ok_origine, r.police)
                                else ctx.getString(R.string.texte_ok_secours, r.police), android.widget.Toast.LENGTH_LONG).show()
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
}
