package io.github.philouelchapo.philpdf

import android.content.Intent
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.offset
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.PointerInputScope
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.FileProvider
import kotlinx.coroutines.launch
import java.io.File

/**
 * Images de la page, comme sous Windows : toucher une image la choisit (cadre bleu). On la glisse pour la deplacer,
 * la poignee carree (coin bas droit) l'agrandit, la poignee ronde (au-dessus) la tourne. Sous le cadre : quart de
 * tour, miroir, reconnaissance du texte, remplacer, enregistrer, supprimer.
 */
object GestesImage {
    private const val POIGNEE_PX = 34f

    /** Gestes de l'outil Images sur la page n (w : largeur de la page en points). */
    suspend fun PointerInputScope.gerer(etat: EtatLecteur, n: Int, w: Float, choisir: (com.artifex.mupdf.fitz.Point) -> Unit) {
        awaitEachGesture {
            val k = w / size.width                          // points de la page par pixel
            val bas = awaitFirstDown()
            val p0 = Offset(bas.position.x * k, bas.position.y * k)
            val choisie = etat.image?.takeIf { it.page == n }
            val t = etat.repereImage
            var genre = "toucher"
            var cx = 0f; var cy = 0f; var x0 = 0f; var y0 = 0f
            if (choisie != null) {
                val c = choisie.cadre(t)
                x0 = c[0]; y0 = c[1]; cx = (c[0] + c[2]) / 2; cy = (c[1] + c[3]) / 2
                val r = POIGNEE_PX * k
                genre = when {
                    kotlin.math.hypot(p0.x - c[2], p0.y - c[3]) < r -> "agrandir"
                    kotlin.math.hypot(p0.x - cx, p0.y - (c[1] - 40f * k)) < r -> "tourner"
                    choisie.contient(t, p0.x, p0.y) -> "deplacer"
                    else -> "toucher"
                }
            }
            var dernier = p0
            var bouge = false
            while (true) {
                val ev = awaitPointerEvent()
                val ch = ev.changes.firstOrNull() ?: break
                if (!ch.pressed) break
                dernier = Offset(ch.position.x * k, ch.position.y * k)
                if ((dernier - p0).getDistance() > 6f * k) bouge = true
                if (genre != "toucher" && bouge) {
                    ch.consume()
                    etat.gesteImage = when (genre) {
                        "deplacer" -> ImagesPdf.M.translation(dernier.x - p0.x, dernier.y - p0.y)
                        "agrandir" -> {
                            val d0 = kotlin.math.hypot(p0.x - x0, p0.y - y0).coerceAtLeast(1f)
                            val e = (kotlin.math.hypot(dernier.x - x0, dernier.y - y0) / d0).coerceIn(0.05f, 20f)
                            ImagesPdf.autour(x0, y0, ImagesPdf.M.echelle(e))
                        }
                        else -> {
                            val a0 = Math.toDegrees(kotlin.math.atan2(-(p0.y - cy), p0.x - cx).toDouble())
                            val a1 = Math.toDegrees(kotlin.math.atan2(-(dernier.y - cy), dernier.x - cx).toDouble())
                            ImagesPdf.autour(cx, cy, ImagesPdf.M.rotationEcran((a1 - a0).toFloat()))
                        }
                    }
                }
            }
            val g = etat.gesteImage
            etat.gesteImage = null
            if (genre == "toucher" || !bouge) {
                if (!bouge) choisir(com.artifex.mupdf.fitz.Point(p0.x, p0.y))
            } else if (g != null && choisie != null) {
                etat.portee?.launch { appliquer(etat, choisie) { etat.doc.transformerImage(choisie, g) } }
            }
        }
    }

    /** Fait l'operation, puis choisit de nouveau l'image (sa place a change). */
    suspend fun appliquer(etat: EtatLecteur, i: ImagesPdf.Placee, op: suspend () -> Boolean) {
        val ok = try { op() } catch (e: IllegalStateException) {
            if (e.message == "partage") { etat.message = etat.texteImagePartagee; false } else throw e
        } catch (e: Exception) { Journal.ecrire("image", e.toString()); false }
        if (!ok) return
        // l'image refaite : celle dont le centre est le plus proche de l'ancien
        val (liste, t) = etat.doc.images(i.page)
        val c = i.cadre(etat.repereImage).let { Pair((it[0] + it[2]) / 2, (it[1] + it[3]) / 2) }
        etat.repereImage = t
        etat.image = liste.filter { it.nom == i.nom || it.objet == i.objet || it.nom.startsWith("PhilIm") }
            .minByOrNull { x -> x.cadre(t).let { kotlin.math.hypot((it[0] + it[2]) / 2 - c.first, (it[1] + it[3]) / 2 - c.second) } }
    }
}

/** Cadre de l'image choisie (avec l'apercu du geste en cours) et ses boutons. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun CadreImage(etat: EtatLecteur, n: Int, w: Float) {
    val i = etat.image?.takeIf { it.page == n } ?: return
    val ctx = LocalContext.current
    val portee = rememberCoroutineScope()
    val choixFichier = rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { u ->
        if (u != null) portee.launch {
            val octets = try { ctx.contentResolver.openInputStream(u)?.use { it.readBytes() } } catch (_: Exception) { null }
            if (octets != null) GestesImage.appliquer(etat, i) { etat.doc.remplacerImage(i, octets) }
        }
    }
    BoxWithConstraints(Modifier.fillMaxSize()) {
        val dens = LocalDensity.current
        val s = with(dens) { maxWidth.toPx() } / w
        val t = etat.repereImage
        val g = etat.gesteImage ?: ImagesPdf.M.I
        val coins = i.coins(t).map { (x, y) -> g.point(x, y) }
        Canvas(Modifier.fillMaxSize()) {
            val chemin = Path().apply {
                coins.forEachIndexed { k, (x, y) -> if (k == 0) moveTo(x * s, y * s) else lineTo(x * s, y * s) }
                close()
            }
            drawPath(chemin, Color(0x221A73E8))
            drawPath(chemin, Color(0xFF1A73E8), style = Stroke(3f, pathEffect = PathEffect.dashPathEffect(floatArrayOf(14f, 10f))))
            if (etat.gesteImage == null) {
                val c = i.cadre(t)
                val r = 13f
                // poignee carree : agrandir ; poignee ronde au-dessus : tourner
                drawRect(Color.White, Offset(c[2] * s - r, c[3] * s - r), androidx.compose.ui.geometry.Size(2 * r, 2 * r))
                drawRect(Color(0xFF1A73E8), Offset(c[2] * s - r, c[3] * s - r), androidx.compose.ui.geometry.Size(2 * r, 2 * r), style = Stroke(3f))
                val cx = (c[0] + c[2]) / 2 * s
                val hy = c[1] * s - 40f
                drawLine(Color(0xFF1A73E8), Offset(cx, c[1] * s), Offset(cx, hy), 2f)
                drawCircle(Color.White, r, Offset(cx, hy))
                drawCircle(Color(0xFF1A73E8), r, Offset(cx, hy), style = Stroke(3f))
            }
        }
        if (etat.gesteImage == null) {
            val c = i.cadre(t)
            val hautBoutons = with(dens) { 100.dp.toPx() }
            val enDessous = c[3] * s + hautBoutons + 8 < with(dens) { maxHeight.toPx() }
            val yb = if (enDessous) c[3] * s + 24 else (c[1] * s - hautBoutons - 56).coerceAtLeast(0f)
            FlowRow(Modifier.fillMaxWidth().offset { IntOffset(0, yb.toInt()) },
                horizontalArrangement = Arrangement.spacedBy(6.dp, Alignment.CenterHorizontally)) {
                // chaque action est lancee dans la portee de l'ecran (operations du moteur : suspendues)
                fun lancer(f: suspend () -> Unit): () -> Unit = { portee.launch { f() } }
                val actions: List<Pair<String, () -> Unit>> = listOf(
                    "↺ 90°" to lancer { GestesImage.appliquer(etat, i) { etat.doc.transformerImage(i, centreRot(i, t, 90f)) } },
                    "↻ 90°" to lancer { GestesImage.appliquer(etat, i) { etat.doc.transformerImage(i, centreRot(i, t, -90f)) } },
                    "⇆" to lancer { GestesImage.appliquer(etat, i) { etat.doc.miroirImage(i, true) } },
                    "⇅" to lancer { GestesImage.appliquer(etat, i) { etat.doc.miroirImage(i, false) } },
                    ctx.getString(R.string.image_ocr) to lancer { etat.image = null; etat.ocr = n },
                    ctx.getString(R.string.image_remplacer) to lancer { choixFichier.launch("image/*") },
                    ctx.getString(R.string.image_enregistrer) to lancer {
                        val f = File(ctx.cacheDir, "ouverts/images/" + etat.doc.nom.substringBeforeLast('.') + "_image_p${n + 1}.png")
                        val ok = etat.doc.exporterImage(i, f)
                        if (ok == null) etat.message = ctx.getString(R.string.image_illisible)
                        else {
                            val u = FileProvider.getUriForFile(ctx, ctx.packageName + ".fichiers", ok)
                            ctx.startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).setType("image/png")
                                .putExtra(Intent.EXTRA_STREAM, u).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION),
                                ctx.getString(R.string.image_enregistrer)))
                        }
                    },
                    ctx.getString(R.string.image_supprimer) to lancer {
                        try { if (etat.doc.supprimerImage(i)) etat.image = null }
                        catch (e: IllegalStateException) { etat.message = etat.texteImagePartagee }
                    },
                    "✓" to lancer { etat.image = null })
                actions.forEach { (texte, action) ->
                    FilledTonalButton(onClick = action, contentPadding = PaddingValues(horizontal = 12.dp)) {
                        Text(texte, fontSize = 14.sp)
                    }
                }
            }
        }
    }
}

private fun centreRot(i: ImagesPdf.Placee, t: ImagesPdf.M, degres: Float): ImagesPdf.M {
    val c = i.cadre(t)
    return ImagesPdf.autour((c[0] + c[2]) / 2, (c[1] + c[3]) / 2, ImagesPdf.M.rotationEcran(degres))
}
