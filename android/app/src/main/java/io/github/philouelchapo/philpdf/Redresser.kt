@file:OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class)

package io.github.philouelchapo.philpdf

import android.graphics.Bitmap
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clipToBounds
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.drawIntoCanvas
import androidx.compose.ui.graphics.nativeCanvas
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
                   valider: (Float, Float, Boolean) -> Unit) {
    var angle by remember { mutableFloatStateOf(0f) }
    var vertical by remember { mutableFloatStateOf(0f) }
    var trouve by remember { mutableStateOf<Pair<Float, Float>?>(null) }
    var surToutes by remember { mutableStateOf(toutes ?: false) }
    // inclinaisons mesurees au debut : proposees d'office (on les voit, on les corrige, rien avant « Appliquer »)
    LaunchedEffect(image) {
        val bm = image ?: return@LaunchedEffect
        val t = withContext(Dispatchers.Default) {
            try { val a = Numerisation.inclinaison(bm); a to Numerisation.inclinaisonVerticale(bm, a) } catch (_: Exception) { 0f to 0f }
        }
        trouve = t; angle = t.first; vertical = t.second
    }
    fun deg(a: Float) = String.format(Locale.FRANCE, "%+.1f°", a)
    // apercu transforme en direct, grille fixe par-dessus
    val apercu: @Composable (Modifier) -> Unit = { m ->
        Box(m.padding(10.dp).clipToBounds(), contentAlignment = Alignment.Center) {
            if (image == null) CircularProgressIndicator()
            Canvas(Modifier.fillMaxSize()) {
                val bm = image
                if (bm != null) {
                    val e = minOf(size.width / bm.width, size.height / bm.height)
                    val mx = Numerisation.matrice(angle, vertical, bm.width.toFloat(), bm.height.toFloat())
                    mx.postScale(e, e)
                    mx.postTranslate((size.width - bm.width * e) / 2, (size.height - bm.height * e) / 2)
                    drawIntoCanvas { it.nativeCanvas.drawBitmap(bm, mx, android.graphics.Paint(android.graphics.Paint.FILTER_BITMAP_FLAG)) }
                }
                val pas = 28.dp.toPx()
                var y = pas
                while (y < size.height) { drawLine(Color(0x551A73E8), Offset(0f, y), Offset(size.width, y), 1.5f); y += pas }
                var x = pas
                while (x < size.width) { drawLine(Color(0x441A73E8), Offset(x, 0f), Offset(x, size.height), 1f); x += pas * 2 }
            }
        }
    }
    val entete: @Composable () -> Unit = {
        Column(Modifier.fillMaxWidth().background(Color.White).padding(12.dp)) {
            TexteAjuste(titre, 17.sp)
            Text(stringResource(R.string.redresser_aide), fontSize = 12.sp, color = Color.Gray)
        }
    }
    val reglages: @Composable () -> Unit = {
        Column(Modifier.fillMaxWidth().background(Color.White).padding(horizontal = 10.dp, vertical = 4.dp)) {
            Reglage(stringResource(R.string.redresser_lignes), angle) { angle = it }
            Reglage(stringResource(R.string.redresser_verticales), vertical) { vertical = it }
            FlowRow(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(6.dp, Alignment.CenterHorizontally)) {
                OutlinedButton(onClick = { trouve?.let { angle = it.first; vertical = it.second } }, enabled = trouve != null) {
                    Text(stringResource(R.string.redresser_auto) + (trouve?.let { " (" + deg(it.first) + " / " + deg(it.second) + ")" } ?: ""))
                }
                OutlinedButton(onClick = { angle = 0f; vertical = 0f }) { Text("0°") }
            }
            if (toutes != null) FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                FilterChip(!surToutes, { surToutes = false }, label = { Text(stringResource(R.string.redresser_cette_page)) })
                FilterChip(surToutes, { surToutes = true }, label = { Text(stringResource(R.string.redresser_toutes)) })
            }
        }
    }
    val boutons: @Composable () -> Unit = {
        FlowRow(Modifier.fillMaxWidth().background(Color.White).padding(6.dp), horizontalArrangement = Arrangement.spacedBy(4.dp, Alignment.End)) {
            TextButton(onClick = fermer) { Text(stringResource(R.string.annuler)) }
            Button(onClick = { valider(angle, vertical, surToutes) }, colors = ButtonDefaults.buttonColors(containerColor = ROUGE)) {
                Text(stringResource(R.string.appliquer))
            }
        }
    }
    Fenetre(fermer) {
        Surface(Modifier.fillMaxSize(), color = Color(0xFFF3F3F3)) {
            BoxWithConstraints(Modifier.fillMaxSize()) {
                val largeur = maxWidth
                val hauteur = maxHeight
                if (maxWidth > maxHeight) {
                    // telephone a l'horizontale : apercu a gauche, reglages a droite (ils defilent), boutons toujours visibles
                    Row(Modifier.fillMaxSize()) {
                        apercu(Modifier.weight(1f).fillMaxHeight())
                        Column(Modifier.width(minOf(360.dp, largeur * 0.55f)).fillMaxHeight()) {
                            Column(Modifier.weight(1f).verticalScroll(rememberScrollState())) { entete(); reglages() }
                            boutons()
                        }
                    }
                } else Column(Modifier.fillMaxSize()) {
                    // grande police ou petit ecran : le haut defile, les boutons restent fixes en bas, au-dessus de la
                    // barre d'Android (sinon « Appliquer » passe dessous et se touche mal)
                    val hApercu = maxOf(160.dp, hauteur * 0.42f)
                    Column(Modifier.weight(1f).verticalScroll(rememberScrollState())) {
                        entete()
                        apercu(Modifier.fillMaxWidth().height(hApercu))
                        reglages()
                    }
                    boutons()
                }
            }
        }
    }
}

/** Une ligne de reglage : nom, angle, curseur, -0,1 / +0,1 (le nom passe a la ligne plutot que d'etre coupe). */
@Composable
private fun Reglage(nom: String, valeur: Float, changer: (Float) -> Unit) {
    Column(Modifier.fillMaxWidth()) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(nom, Modifier.weight(1f), fontSize = 13.sp)
            Text(String.format(Locale.FRANCE, "%+.1f°", valeur), fontWeight = FontWeight.SemiBold, fontSize = 16.sp)
            TextButton(onClick = { changer((valeur - 0.1f).coerceIn(-15f, 15f)) }, contentPadding = PaddingValues(horizontal = 6.dp)) { Text("−0,1") }
            TextButton(onClick = { changer((valeur + 0.1f).coerceIn(-15f, 15f)) }, contentPadding = PaddingValues(horizontal = 6.dp)) { Text("+0,1") }
        }
        Slider(valeur, { changer(Math.round(it * 10) / 10f) }, Modifier.fillMaxWidth().height(32.dp), valueRange = -15f..15f)
    }
}

/** Redresser une page du document ouvert (Plus > Redresser la page). */
@Composable
fun RedresserPage(etat: EtatLecteur, n: Int, fermer: () -> Unit) {
    val ctx = androidx.compose.ui.platform.LocalContext.current
    val image by produceState<Bitmap?>(null, n) { value = try { etat.doc.rendre(n, 1100) } catch (_: Exception) { null } }
    val nb by produceState(1) { value = try { etat.doc.nombrePages() } catch (_: Exception) { 1 } }
    RedresserImage(image, stringResource(R.string.redresser_page_n, n + 1), fermer, toutes = if (nb > 1) false else null) { a, v, toutes ->
        fermer()
        (etat.portee ?: return@RedresserImage).launch {
            val ok = etat.doc.redresserPages(if (toutes) (0 until nb).toList() else listOf(n), a, v)
            Journal.ecrire("redresser", "page(s) ${if (toutes) "toutes" else n + 1} : lignes ${"%.1f".format(Locale.ROOT, a)}°, verticales ${"%.1f".format(Locale.ROOT, v)}°")
            android.widget.Toast.makeText(ctx, ctx.getString(if (ok) R.string.redresser_fait else R.string.redresser_rien), android.widget.Toast.LENGTH_SHORT).show()
        }
    }
}
