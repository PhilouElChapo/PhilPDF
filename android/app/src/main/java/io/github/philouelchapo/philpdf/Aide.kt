@file:OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class)

package io.github.philouelchapo.philpdf

import android.content.Intent
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.core.content.FileProvider

/** Aide : Nouveautes (readme.txt livre dans l'APK) et Journal (a partager pour signaler un probleme). */
@Composable
fun EcranAide(fermer: () -> Unit) {
    val ctx = LocalContext.current
    var onglet by remember { mutableIntStateOf(0) }
    var journal by remember { mutableStateOf(Journal.lire(ctx)) }
    val nouveautes = remember {
        try { ctx.assets.open("readme.txt").bufferedReader().use { it.readText() } } catch (_: Exception) { "" }
    }
    Fenetre(fermer) {
        Surface(Modifier.fillMaxWidth(0.96f).widthIn(max = 720.dp).fillMaxHeight(0.94f), shape = RoundedCornerShape(16.dp)) {
            Column(Modifier.fillMaxSize().padding(vertical = 12.dp)) {
                Text(stringResource(R.string.aide), Modifier.padding(horizontal = 16.dp), fontWeight = FontWeight.SemiBold, fontSize = 20.sp)
                TabRow(selectedTabIndex = onglet) {
                    Tab(onglet == 0, { onglet = 0 }, text = { TexteAjuste(stringResource(R.string.nouveautes), 14.sp) })
                    Tab(onglet == 1, { onglet = 1 }, text = { TexteAjuste(stringResource(R.string.journal), 14.sp) })
                }
                Box(Modifier.weight(1f).fillMaxWidth().padding(horizontal = 12.dp, vertical = 8.dp)) {
                    if (onglet == 0) {
                        SelectionContainer {
                            Text(nouveautes.ifEmpty { "—" }, Modifier.verticalScroll(rememberScrollState()), fontSize = 13.sp)
                        }
                    } else {
                        Column {
                            Text(stringResource(R.string.journal_explication), fontSize = 12.sp, color = androidx.compose.ui.graphics.Color.Gray)
                            Spacer(Modifier.height(6.dp))
                            // les lignes les plus recentes en haut ; defilement horizontal plutot que lignes coupees
                            SelectionContainer(Modifier.weight(1f)) {
                                Text(journal.lines().filter { it.isNotBlank() }.reversed().joinToString("\n").ifEmpty { stringResource(R.string.journal_vide) },
                                    Modifier.verticalScroll(rememberScrollState()).horizontalScroll(rememberScrollState()),
                                    fontFamily = FontFamily.Monospace, fontSize = 11.sp, softWrap = false)
                            }
                        }
                    }
                }

                // Noter (version Google Play seulement) et Partager PhilPDF : suggestion des testeurs
                FlowRow(Modifier.fillMaxWidth().padding(horizontal = 8.dp), horizontalArrangement = Arrangement.Start) {
                    if (BuildConfig.PLAY_STORE) TextButton(onClick = { noterPhilpdf(ctx) }) {
                        Text("★ " + stringResource(R.string.noter_philpdf))
                    }
                    TextButton(onClick = { partagerPhilpdf(ctx) }) { Text(stringResource(R.string.partager_philpdf)) }
                }
                FlowRow(Modifier.fillMaxWidth().padding(horizontal = 8.dp), horizontalArrangement = Arrangement.End) {
                    if (onglet == 1) {
                        TextButton(onClick = {
                            val f = Journal.fichier(ctx)
                            if (f.exists()) {
                                val copie = java.io.File(ctx.cacheDir, "ouverts/partage/journal_philpdf.txt").apply { parentFile?.mkdirs() }
                                f.copyTo(copie, overwrite = true)
                                val u = FileProvider.getUriForFile(ctx, "${ctx.packageName}.fichiers", copie)
                                ctx.startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).setType("text/plain")
                                    .putExtra(Intent.EXTRA_STREAM, u).putExtra(Intent.EXTRA_SUBJECT, "Journal PhilPDF Android ${BuildConfig.VERSION_NAME}")
                                    .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION), null))
                            }
                        }) { Text(stringResource(R.string.partager)) }
                        TextButton(onClick = { Journal.effacer(ctx); journal = "" }) { Text(stringResource(R.string.effacer)) }
                    }
                    TextButton(onClick = fermer) { Text(stringResource(R.string.fermer)) }
                }
            }
        }
    }
}


private const val LIEN_PLAY = "https://play.google.com/store/apps/details?id=io.github.philouelchapo.philpdf"
private const val LIEN_GITHUB = "https://github.com/PhilouElChapo/PhilPDF"

/** Page de PhilPDF dans l'appli Play Store (navigateur si elle n'est pas la) : l'utilisateur y met sa note. */
fun noterPhilpdf(ctx: android.content.Context) {
    val play = Intent(Intent.ACTION_VIEW, android.net.Uri.parse("market://details?id=" + ctx.packageName))
        .addFlags(Intent.FLAG_ACTIVITY_NEW_DOCUMENT or Intent.FLAG_ACTIVITY_MULTIPLE_TASK)
    try { ctx.startActivity(play) }
    catch (_: android.content.ActivityNotFoundException) { ctx.startActivity(Intent(Intent.ACTION_VIEW, android.net.Uri.parse(LIEN_PLAY))) }
}

/** Message tout pret avec le lien (Google Play pour la version Play, sinon la page du projet) ; l'utilisateur
 *  choisit l'appli et peut modifier le texte avant l'envoi. */
fun partagerPhilpdf(ctx: android.content.Context) {
    val lien = if (BuildConfig.PLAY_STORE) LIEN_PLAY else LIEN_GITHUB
    val texte = Textes.t(R.string.partager_philpdf_message, lien)
    ctx.startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).setType("text/plain")
        .putExtra(Intent.EXTRA_SUBJECT, "PhilPDF").putExtra(Intent.EXTRA_TEXT, texte), null))
}
