@file:OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class, androidx.compose.foundation.ExperimentalFoundationApi::class)

package io.github.philouelchapo.philpdf

import android.graphics.Bitmap
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.gestures.detectDragGesturesAfterLongPress
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.itemsIndexed
import androidx.compose.foundation.lazy.grid.rememberLazyGridState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.scale
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.compose.ui.zIndex
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File

/** Ecran « Organiser les pages » : vignettes en grille. Toucher selectionne ; appui long puis glisser deplace
 *  (la selection entiere si la page touchee en fait partie). Barre du bas : pivoter, supprimer, extraire, page
 *  blanche, ajouter un PDF, compresser, mot de passe. Tout s'annule avec la fleche « Annuler ». */
@Composable
fun OrganiserPages(etat: EtatLecteur, tailles: List<Pair<Float, Float>>, fermer: () -> Unit) {
    val ctx = LocalContext.current
    val d = etat.doc
    val portee = rememberCoroutineScope()
    var choix by remember { mutableStateOf(setOf<Int>()) }
    val nb = tailles.size
    LaunchedEffect(nb) { choix = choix.filter { it < nb }.toSet() }
    val tries = choix.sorted()
    var confirmerSuppression by remember { mutableStateOf(false) }
    var dialogueMdp by remember { mutableStateOf(false) }
    var dialogueCompresser by remember { mutableStateOf(false) }
    var occupe by remember { mutableStateOf(false) }
    fun dire(t: String) = android.widget.Toast.makeText(ctx, t, android.widget.Toast.LENGTH_LONG).show()
    fun lancer(bloc: suspend () -> Unit) {
        if (occupe) return
        occupe = true
        portee.launch { try { bloc() } catch (e: Exception) { dire(e.message ?: e.toString()) } finally { occupe = false } }
    }
    // place des ajouts : apres la derniere page choisie, sinon a la fin
    val apres = if (tries.isEmpty()) nb else tries.last() + 1

    val extraireVers = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("application/pdf")) { u: Uri? ->
        if (u != null) lancer {
            val tmp = d.extraire(tries, File(ctx.cacheDir, "ouverts/extraction/pages.pdf"))
            withContext(Dispatchers.IO) {
                ctx.contentResolver.openOutputStream(u, "wt")?.use { s -> tmp.inputStream().use { it.copyTo(s) } }
                    ?: throw IllegalStateException(ctx.getString(R.string.enregistrement_impossible))
            }
            Journal.ecrire("organiser", "${d.nom} : ${tries.size} page(s) extraite(s)")
            dire(ctx.getString(R.string.pages_extraites, tries.size))
        }
    }
    val ajouterPdf = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { u: Uri? ->
        if (u != null) lancer {
            val f = withContext(Dispatchers.IO) {
                val f = File(ctx.cacheDir, "ouverts/ajout/" + nomDuFichier(ctx, u).replace('/', '_'))
                f.parentFile?.mkdirs()
                ctx.contentResolver.openInputStream(u)?.use { e -> f.outputStream().use { e.copyTo(it) } }
                    ?: throw IllegalStateException(ctx.getString(R.string.ajout_impossible))
                f
            }
            val n = d.inserer(f, apres)
            if (n == 0) dire(ctx.getString(R.string.ajout_impossible))
            else {
                Journal.ecrire("organiser", "${d.nom} : $n page(s) ajoutée(s) depuis ${f.name}")
                choix = (apres until apres + n).toSet()
                dire(ctx.getString(R.string.pages_ajoutees, n))
            }
        }
    }

    Fenetre(fermer) {
        Surface(Modifier.fillMaxSize(), color = Color(0xFFF3F3F3)) {
            // Fenetre s'arrete au-dessus des barres d'Android (retour, accueil) : la barre d'actions reste visible
            Column(Modifier.fillMaxSize()) {
                // barre du haut : retour, titre, annuler / retablir / enregistrer
                Row(Modifier.fillMaxWidth().background(Color.White).padding(horizontal = 4.dp, vertical = 2.dp),
                    verticalAlignment = Alignment.CenterVertically) {
                    IconButton(onClick = fermer) { Icon(Icons.AutoMirrored.Filled.ArrowBack, stringResource(R.string.retour)) }
                    Column(Modifier.weight(1f)) {
                        TexteAjuste(stringResource(R.string.organiser_pages), 17.sp)
                        Text(if (choix.isEmpty()) stringResource(R.string.organiser_aide)
                             else stringResource(R.string.pages_choisies, choix.size, nb),
                            fontSize = 12.sp, color = Color.Gray, maxLines = 2)
                    }
                    BoutonsEdition(etat)
                }
                HorizontalDivider(color = Color(0xFFE2E2E2))
                Box(Modifier.weight(1f).fillMaxWidth()) {
                    Grille(etat, tailles, choix, { n -> choix = if (n in choix) choix - n else choix + n },
                        { n -> fermer(); portee.launch { etat.liste.scrollToItem(n) } }) { de, vers ->
                        // deplacer : la selection entiere si la page tenue en fait partie, sinon cette page seule
                        val bloc = if (de in choix) tries else listOf(de)
                        if (vers in bloc) return@Grille
                        val reste = (0 until nb).filter { it !in bloc }
                        val i = reste.indexOf(vers).let { if (vers > de) it + 1 else it }
                        val ordre = reste.subList(0, i) + bloc + reste.subList(i, reste.size)
                        lancer {
                            if (d.ordonner(ordre)) {
                                choix = bloc.indices.map { i + it }.toSet()
                                Journal.ecrire("organiser", "${d.nom} : ${bloc.size} page(s) déplacée(s)")
                            }
                        }
                    }
                    if (occupe) CircularProgressIndicator(Modifier.align(Alignment.Center))
                }
                HorizontalDivider(color = Color(0xFFE2E2E2))
                // barre d'actions : passe a la ligne si la place manque (jamais tronquee)
                FlowRow(Modifier.fillMaxWidth().background(Color.White).padding(horizontal = 4.dp, vertical = 4.dp),
                    horizontalArrangement = Arrangement.SpaceEvenly) {
                    val un = choix.isNotEmpty()
                    Action(if (choix.size == nb) "aucun" else "tout",
                        stringResource(if (choix.size == nb) R.string.aucune_page else R.string.toutes_pages)) {
                        choix = if (choix.size == nb) emptySet() else (0 until nb).toSet()
                    }
                    Action("pivoter", stringResource(R.string.pivoter_gauche), un, miroir = true) { lancer { d.pivoter(tries, -90) } }
                    Action("pivoter", stringResource(R.string.pivoter_droite), un) { lancer { d.pivoter(tries, 90) } }
                    Action("supprimer", stringResource(R.string.supprimer), un && choix.size < nb) { confirmerSuppression = true }
                    Action("exporter", stringResource(R.string.extraire), un) {
                        val pages = if (tries.size == 1) "${tries[0] + 1}" else "${tries.first() + 1}-${tries.last() + 1}"
                        extraireVers.launch(d.nom.removeSuffix(".pdf").removeSuffix(".PDF") + " - p$pages.pdf")
                    }
                    Action("creer", stringResource(R.string.page_blanche)) {
                        val (w, h) = tailles.getOrElse((apres - 1).coerceAtLeast(0)) { 595f to 842f }
                        lancer { if (d.pageBlanche(apres, w, h)) choix = setOf(apres) }
                    }
                    Action("combiner", stringResource(R.string.ajouter_pdf)) { ajouterPdf.launch(arrayOf("application/pdf")) }
                    Action("alleger", stringResource(R.string.compresser)) { dialogueCompresser = true }
                    Action("motdepasse", stringResource(R.string.mot_de_passe)) { dialogueMdp = true }
                }
            }
        }
    }

    if (confirmerSuppression) AlertDialog(
        onDismissRequest = { confirmerSuppression = false },
        title = { Text(stringResource(R.string.supprimer_pages_titre, choix.size)) },
        text = { Text(stringResource(R.string.supprimer_pages_texte)) },
        confirmButton = {
            TextButton(onClick = {
                confirmerSuppression = false
                val pages = tries
                lancer {
                    if (d.supprimerPages(pages)) {
                        Journal.ecrire("organiser", "${d.nom} : ${pages.size} page(s) supprimée(s)")
                        choix = emptySet()
                    }
                }
            }) { Text(stringResource(R.string.supprimer), color = ROUGE) }
        },
        dismissButton = { TextButton(onClick = { confirmerSuppression = false }) { Text(stringResource(R.string.annuler)) } })

    if (dialogueCompresser) DialogueCompresser(d) { dialogueCompresser = false }
    if (dialogueMdp) DialogueMotDePasse(d) { dialogueMdp = false }
}

/** Grille des vignettes. choisir(n) : toucher ; deplacer(de, vers) : appui long puis glisser sur une autre page. */
@Composable
private fun Grille(etat: EtatLecteur, tailles: List<Pair<Float, Float>>, choix: Set<Int>, choisir: (Int) -> Unit,
                   allerA: (Int) -> Unit, deplacer: (Int, Int) -> Unit) {
    val grille = rememberLazyGridState()
    var tenue by remember { mutableStateOf<Int?>(null) }
    var glisse by remember { mutableStateOf(Offset.Zero) }
    var cible by remember { mutableStateOf<Int?>(null) }
    val largeurPx = with(LocalDensity.current) { 120.dp.toPx().toInt() }
    fun pageSous(n: Int, depl: Offset): Int? {
        val info = grille.layoutInfo.visibleItemsInfo
        val depart = info.firstOrNull { it.index == n } ?: return null
        val x = depart.offset.x + depart.size.width / 2 + depl.x
        val y = depart.offset.y + depart.size.height / 2 + depl.y
        return info.firstOrNull { x >= it.offset.x && x < it.offset.x + it.size.width && y >= it.offset.y && y < it.offset.y + it.size.height }?.index
    }
    LazyVerticalGrid(GridCells.Adaptive(118.dp), Modifier.fillMaxSize(), state = grille,
        contentPadding = PaddingValues(10.dp), horizontalArrangement = Arrangement.spacedBy(10.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)) {
        itemsIndexed(tailles, key = { n, _ -> "$n-${etat.doc.pagesVersion}" }) { n, (w, h) ->
            val oui = n in choix
            val enMain = tenue == n
            Column(Modifier
                .zIndex(if (enMain) 1f else 0f)
                .graphicsLayer {
                    if (enMain) { translationX = glisse.x; translationY = glisse.y; scaleX = 1.06f; scaleY = 1.06f; alpha = 0.9f }
                }
                .pointerInput(n, tailles.size) {
                    detectDragGesturesAfterLongPress(
                        onDragStart = { tenue = n; glisse = Offset.Zero; cible = null },
                        onDrag = { c, delta -> c.consume(); glisse += delta; cible = pageSous(n, glisse)?.takeIf { it != n } },
                        onDragEnd = {
                            val v = cible
                            if (v != null) deplacer(n, v) else if (glisse.getDistance() < 20f) choisir(n)
                            tenue = null; glisse = Offset.Zero; cible = null
                        },
                        onDragCancel = { tenue = null; glisse = Offset.Zero; cible = null })
                }
                // toucher : choisir la page ; toucher deux fois : y aller (retour a la lecture)
                .combinedClickable(onClick = { choisir(n) },
                    onDoubleClick = { allerA(n) }),
                horizontalAlignment = Alignment.CenterHorizontally) {
                Box {
                    Vignette(etat.doc, n, largeurPx, w, h, Modifier.fillMaxWidth()
                        .border(if (oui || cible == n) 3.dp else 1.dp,
                            if (cible == n) Color(0xFF0F6CBD) else if (oui) ROUGE else Color(0xFFCFCFCF)))
                    if (oui) Box(Modifier.align(Alignment.TopEnd).padding(4.dp).size(22.dp).background(ROUGE, CircleShape),
                        contentAlignment = Alignment.Center) { Text("✓", color = Color.White, fontSize = 13.sp, fontWeight = FontWeight.Bold) }
                }
                Text("${n + 1}", fontSize = 12.sp, color = if (oui) ROUGE else Color.Gray,
                    fontWeight = if (oui) FontWeight.SemiBold else FontWeight.Normal)
            }
        }
    }
}

@Composable
private fun Vignette(d: DocumentPdf, n: Int, largeurPx: Int, w: Float, h: Float, modifier: Modifier) {
    val image by produceState<Bitmap?>(null, d, n, largeurPx, d.version) {
        value = try { d.rendre(n, largeurPx) } catch (_: Exception) { value }
    }
    val ratio = image?.let { it.width.toFloat() / it.height } ?: (w / h)
    Box(modifier.aspectRatio(ratio.coerceIn(0.1f, 10f)).background(Color.White)) {
        image?.let { Image(it.asImageBitmap(), null, Modifier.fillMaxSize()) }
    }
}

@Composable
private fun Action(icone: String, texte: String, actif: Boolean = true, miroir: Boolean = false, faire: () -> Unit) {
    Column(Modifier.width(76.dp).clickable(enabled = actif, onClick = faire).padding(vertical = 4.dp),
        horizontalAlignment = Alignment.CenterHorizontally) {
        Icon(Icones.get(icone, if (actif) Color(0xFF333333) else Color(0xFFBBBBBB)), null,
            Modifier.then(if (miroir) Modifier.scale(scaleX = -1f, scaleY = 1f) else Modifier), tint = Color.Unspecified)
        TexteAjuste(texte, 11.sp)
    }
}

private fun mo(o: Long): String = String.format(java.util.Locale.FRANCE, "%.2f Mo", o / 1048576.0)

@Composable
private fun DialogueCompresser(d: DocumentPdf, fermer: () -> Unit) {
    val ctx = LocalContext.current
    val avantModifie = remember { d.modifie }
    val avantCompresser = remember { d.compresser }
    val origine = remember { d.tailleOrigine() }
    var choix by remember { mutableStateOf(0) }
    var reduites by remember { mutableStateOf(0) }          // images reduites par le reglage applique (a defaire)
    var apres by remember { mutableStateOf<Long?>(null) }
    var calcul by remember { mutableStateOf(0) }
    LaunchedEffect(choix, calcul) {
        apres = null
        if (reduites > 0) { d.annuler(); reduites = 0 }    // reglage precedent defait avant d'essayer celui-ci
        d.compresser = true
        d.modifie = true
        apres = try {
            reduites = d.alleger(Alleger.PREREGLAGES[choix])
            d.tailleEnregistree(ctx)
        } catch (_: Exception) { -1L }
    }
    val portee = rememberCoroutineScope()
    AlertDialog(onDismissRequest = {},
        title = { Text(stringResource(R.string.compresser)) },
        text = {
            Column {
                Text(stringResource(R.string.compresser_texte), fontSize = 13.sp)
                Spacer(Modifier.height(6.dp))
                Alleger.PREREGLAGES.forEachIndexed { i, r ->
                    Row(Modifier.fillMaxWidth().clickable(enabled = apres != null) { choix = i },
                        verticalAlignment = Alignment.CenterVertically) {
                        RadioButton(choix == i, { choix = i }, enabled = apres != null)
                        Column {
                            Text(stringResource(r.nom), fontSize = 14.sp)
                            if (r.dpi > 0) Text(stringResource(R.string.alleger_detail, r.dpi, r.qualite), fontSize = 11.sp, color = Color.Gray)
                        }
                    }
                }
                Spacer(Modifier.height(8.dp))
                val a = apres
                Text(when {
                    a == null -> stringResource(R.string.compresser_calcul)
                    a < 0 -> stringResource(R.string.compresser_impossible)
                    else -> stringResource(R.string.compresser_resultat, mo(origine), mo(a)) +
                        if (reduites > 0) "\n" + stringResource(R.string.alleger_images, reduites) else ""
                }, fontWeight = FontWeight.SemiBold)
            }
        },
        confirmButton = {
            TextButton(onClick = {
                Journal.ecrire("organiser", "${d.nom} : allégé (${mo(origine)} → ${apres?.let { mo(it) }}, $reduites image(s) réduite(s))")
                fermer()
            }, enabled = (apres ?: -1) >= 0) { Text(stringResource(R.string.compresser_garder)) }
        },
        dismissButton = {
            TextButton(onClick = {
                portee.launch {
                    if (reduites > 0) d.annuler()
                    d.compresser = avantCompresser
                    d.modifie = avantModifie
                    fermer()
                }
            }, enabled = apres != null) { Text(stringResource(R.string.annuler)) }
        })
}

@Composable
private fun DialogueMotDePasse(d: DocumentPdf, fermer: () -> Unit) {
    var m1 by remember { mutableStateOf("") }
    var m2 by remember { mutableStateOf("") }
    var voir by remember { mutableStateOf(false) }
    val protege = remember { d.besoinMotDePasse() || !d.motDePasseNouveau.isNullOrEmpty() }
    val erreur = when {
        m1.contains(',') -> stringResource(R.string.mdp_virgule)
        m2.isNotEmpty() && m1 != m2 -> stringResource(R.string.mdp_differents)
        else -> null
    }
    AlertDialog(onDismissRequest = fermer,
        title = { Text(stringResource(R.string.mot_de_passe)) },
        text = {
            Column {
                Text(stringResource(R.string.mdp_texte), fontSize = 14.sp)
                Spacer(Modifier.height(8.dp))
                ChampSecret(m1, { m1 = it }, stringResource(R.string.mdp_nouveau))
                ChampSecret(m2, { m2 = it }, stringResource(R.string.mdp_confirmer))
                erreur?.let { Text(it, color = ROUGE, fontSize = 13.sp) }
                if (protege) TextButton(onClick = {
                    d.motDePasseNouveau = ""
                    d.marquerModifie()
                    Journal.ecrire("organiser", "${d.nom} : mot de passe retiré (à l'enregistrement)")
                    fermer()
                }) { Text(stringResource(R.string.mdp_retirer), color = ROUGE) }
            }
        },
        confirmButton = {
            TextButton(onClick = {
                d.motDePasseNouveau = m1
                d.marquerModifie()
                Journal.ecrire("organiser", "${d.nom} : mot de passe ajouté (à l'enregistrement)")
                fermer()
            }, enabled = m1.isNotEmpty() && m1 == m2 && erreur == null) { Text(stringResource(R.string.appliquer)) }
        },
        dismissButton = { TextButton(onClick = fermer) { Text(stringResource(R.string.annuler)) } })
}
