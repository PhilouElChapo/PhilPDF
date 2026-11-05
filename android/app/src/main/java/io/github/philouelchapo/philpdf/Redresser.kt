@file:OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class)

package io.github.philouelchapo.philpdf

import android.graphics.Bitmap
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clipToBounds
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.util.Locale

/**
 * Redresser une image ou une page : apercu tourne en direct sur une grille (pour juger les lignes), angle au
 * dixieme de degre, « Auto » (inclinaison mesuree sur le texte), 0°. toutes : choix « cette page / toutes » (null :
 * pas de choix). valider(angle en degres, sens des aiguilles d'une montre, toutes les pages ?).
 */
@Composable
fun RedresserImage(image: Bitmap?, titre: String, fermer: () -> Unit, toutes: Boolean? = null,
                   valider: (Float, Boolean) -> Unit) {
    var angle by remember { mutableFloatStateOf(0f) }
    var trouve by remember { mutableStateOf<Float?>(null) }
    var surToutes by remember { mutableStateOf(toutes ?: false) }
    // inclinaison mesuree au debut : proposee d'office (on la voit, on la corrige, rien n'est applique avant « Appliquer »)
    LaunchedEffect(image) {
        val bm = image ?: return@LaunchedEffect
        val a = withContext(Dispatchers.Default) { try { Numerisation.inclinaison(bm) } catch (_: Exception) { 0f } }
        trouve = a; angle = a
    }
    fun deg(a: Float) = String.format(Locale.FRANCE, "%+.1f°", a)
    Fenetre(fermer) {
        Surface(Modifier.fillMaxSize(), color = Color(0xFFF3F3F3)) {
            Column(Modifier.fillMaxSize()) {
                Column(Modifier.fillMaxWidth().background(Color.White).padding(12.dp)) {
                    TexteAjuste(titre, 17.sp)
                    Text(stringResource(R.string.redresser_aide), fontSize = 12.sp, color = Color.Gray)
                }
                // apercu tourne, grille fixe par-dessus
                Box(Modifier.weight(1f).fillMaxWidth().padding(10.dp).clipToBounds(), contentAlignment = Alignment.Center) {
                    if (image == null) CircularProgressIndicator()
                    else Image(image.asImageBitmap(), null, Modifier.fillMaxSize().graphicsLayer(rotationZ = angle), contentScale = ContentScale.Fit)
                    Canvas(Modifier.fillMaxSize()) {
                        val pas = 28.dp.toPx()
                        var y = pas
                        while (y < size.height) { drawLine(Color(0x551A73E8), Offset(0f, y), Offset(size.width, y), 1.5f); y += pas }
                        var x = pas
                        while (x < size.width) { drawLine(Color(0x331A73E8), Offset(x, 0f), Offset(x, size.height), 1f); x += pas * 2 }
                    }
                }
                Column(Modifier.fillMaxWidth().background(Color.White).padding(horizontal = 10.dp, vertical = 6.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(deg(angle), fontWeight = FontWeight.SemiBold, fontSize = 18.sp, modifier = Modifier.width(80.dp))
                        Slider(angle, { angle = (Math.round(it * 10) / 10f) }, Modifier.weight(1f), valueRange = -15f..15f)
                    }
                    FlowRow(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(6.dp, Alignment.CenterHorizontally)) {
                        listOf(-1f, -0.1f, 0.1f, 1f).forEach { d ->
                            OutlinedButton(onClick = { angle = (angle + d).coerceIn(-15f, 15f) }, contentPadding = PaddingValues(horizontal = 10.dp)) {
                                Text(String.format(Locale.FRANCE, "%+.1f°", d))
                            }
                        }
                        OutlinedButton(onClick = { trouve?.let { angle = it } }, enabled = trouve != null) {
                            Text(stringResource(R.string.redresser_auto) + (trouve?.let { " (" + deg(it) + ")" } ?: ""))
                        }
                        OutlinedButton(onClick = { angle = 0f }) { Text("0°") }
                    }
                    if (toutes != null) Row(verticalAlignment = Alignment.CenterVertically) {
                        FilterChip(!surToutes, { surToutes = false }, label = { Text(stringResource(R.string.redresser_cette_page)) })
                        Spacer(Modifier.width(8.dp))
                        FilterChip(surToutes, { surToutes = true }, label = { Text(stringResource(R.string.redresser_toutes)) })
                    }
                }
                // boutons fixes en bas
                Row(Modifier.fillMaxWidth().background(Color.White).padding(6.dp), horizontalArrangement = Arrangement.End) {
                    TextButton(onClick = fermer) { Text(stringResource(R.string.annuler)) }
                    Button(onClick = { valider(angle, surToutes) }, colors = ButtonDefaults.buttonColors(containerColor = ROUGE)) {
                        Text(stringResource(R.string.appliquer))
                    }
                }
            }
        }
    }
}

/** Redresser une page du document ouvert (Plus > Redresser la page). */
@Composable
fun RedresserPage(etat: EtatLecteur, n: Int, fermer: () -> Unit) {
    val ctx = androidx.compose.ui.platform.LocalContext.current
    val image by produceState<Bitmap?>(null, n) { value = try { etat.doc.rendre(n, 1100) } catch (_: Exception) { null } }
    val nb by produceState(1) { value = try { etat.doc.nombrePages() } catch (_: Exception) { 1 } }
    RedresserImage(image, stringResource(R.string.redresser_page_n, n + 1), fermer, toutes = if (nb > 1) false else null) { a, toutes ->
        fermer()
        (etat.portee ?: return@RedresserImage).launch {
            val ok = etat.doc.redresserPages(if (toutes) (0 until nb).toList() else listOf(n), a)
            Journal.ecrire("redresser", "page(s) ${if (toutes) "toutes" else n + 1} : ${"%.1f".format(Locale.ROOT, a)}°")
            android.widget.Toast.makeText(ctx, ctx.getString(if (ok) R.string.redresser_fait else R.string.redresser_rien), android.widget.Toast.LENGTH_SHORT).show()
        }
    }
}
