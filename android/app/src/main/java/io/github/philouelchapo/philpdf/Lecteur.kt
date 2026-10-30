package io.github.philouelchapo.philpdf

import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.os.Bundle
import android.os.CancellationSignal
import android.os.ParcelFileDescriptor
import android.print.PageRange
import android.print.PrintAttributes
import android.print.PrintDocumentAdapter
import android.print.PrintDocumentInfo
import android.print.PrintManager
import androidx.activity.compose.BackHandler
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.gestures.detectTransformGestures
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyListState
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.input.nestedscroll.NestedScrollConnection
import androidx.compose.ui.input.nestedscroll.NestedScrollSource
import androidx.compose.ui.input.nestedscroll.nestedScroll
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.FileProvider
import kotlinx.coroutines.launch

/** Ce que montre le volet (tablette) ou le tiroir (telephone). */
enum class Volet { VIGNETTES, SIGNETS, COMMENTAIRES, RECHERCHE, ANNOTER, SIGNER, PLUS }

/** Etat partage du lecteur : page, zoom, recherche. */
class EtatLecteur(val doc: DocumentPdf, val liste: LazyListState) {
    var echelle by mutableFloatStateOf(1f)
    var decalage by mutableStateOf(Offset.Zero)
    var recherche by mutableStateOf("")
    var trouves by mutableStateOf<List<Trouve>>(emptyList())
    var cherche by mutableStateOf(false)
    val page: Int get() = liste.firstVisibleItemIndex
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun Lecteur(doc: DocumentPdf, fermer: () -> Unit) {
    val ctx = LocalContext.current
    BackHandler(onBack = fermer)
    var deverrouille by remember(doc) { mutableStateOf(!doc.besoinMotDePasse()) }
    var tailles by remember(doc) { mutableStateOf<List<Pair<Float, Float>>?>(null) }
    val etat = remember(doc) { EtatLecteur(doc, LazyListState()) }
    LaunchedEffect(doc, deverrouille) {
        if (deverrouille) {
            val t = doc.tailles()
            tailles = t
            Recents.ajouter(ctx, doc.uri, doc.nom, t.size)
            val p = PagesLues.lire(ctx, doc.uri.toString())        // on reprend la ou on s'etait arrete
            if (p in 1 until t.size) etat.liste.scrollToItem(p)
            Miniatures.fabriquer(ctx, doc)
        }
    }
    LaunchedEffect(etat.liste.firstVisibleItemIndex) { PagesLues.ecrire(ctx, doc.uri.toString(), etat.page) }

    val t = tailles
    when {
        !deverrouille -> Box(Modifier.fillMaxSize()) { DemandeMotDePasse(doc, { deverrouille = true }, fermer) }
        t == null -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { Text(stringResource(R.string.ouverture)) }
        else -> BoxWithConstraints(Modifier.fillMaxSize()) {
            // grand ecran (tablette, telephone a l'horizontale) : disposition Windows ; sinon : telephone
            if (maxWidth >= 720.dp) DispositionTablette(etat, t, fermer) else DispositionTelephone(etat, t, fermer)
        }
    }
}

// ================================================================ tablette : barre d'outils + volets retractables
@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun DispositionTablette(etat: EtatLecteur, tailles: List<Pair<Float, Float>>, fermer: () -> Unit) {
    val ctx = LocalContext.current
    var gauche by remember { mutableStateOf<Volet?>(Volet.VIGNETTES) }
    var droite by remember { mutableStateOf<Volet?>(null) }
    var allerA by remember { mutableStateOf(false) }
    val portee = rememberCoroutineScope()
    Column(Modifier.fillMaxSize().background(Color(0xFFF3F3F3))) {
        // barre du haut : nom, puis outils (passe a la ligne si la place manque)
        Row(Modifier.fillMaxWidth().background(Color.White).padding(horizontal = 4.dp, vertical = 2.dp),
            verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = fermer) { Icon(Icons.AutoMirrored.Filled.ArrowBack, stringResource(R.string.retour)) }
            Text(etat.doc.nom, Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis, fontWeight = FontWeight.SemiBold)
            FlowRow(horizontalArrangement = Arrangement.End) {
                Bouton("rechercher", stringResource(R.string.rechercher)) { droite = if (droite == Volet.RECHERCHE) null else Volet.RECHERCHE }
                Bouton("zoom_moins", stringResource(R.string.zoom_moins)) { etat.echelle = (etat.echelle / 1.25f).coerceAtLeast(1f); if (etat.echelle == 1f) etat.decalage = Offset.Zero }
                Bouton("zoom_plus", stringResource(R.string.zoom_plus)) { etat.echelle = (etat.echelle * 1.25f).coerceAtMost(5f) }
                Bouton("largeur", stringResource(R.string.ajuster)) { etat.echelle = 1f; etat.decalage = Offset.Zero }
                Bouton("suivante", stringResource(R.string.aller_page)) { allerA = true }
                Bouton("courriel", stringResource(R.string.partager)) { partager(ctx, etat.doc) }
                Bouton("imprimer", stringResource(R.string.imprimer)) { imprimer(ctx, etat.doc) }
            }
        }
        HorizontalDivider(color = Color(0xFFE2E2E2))
        Row(Modifier.weight(1f).fillMaxWidth()) {
            // volet gauche : replie, il reste une colonne d'icones (jamais disparu)
            Rail(listOf(Volet.VIGNETTES to "organiser", Volet.SIGNETS to "liste_fichiers", Volet.COMMENTAIRES to "commentaire"), gauche) {
                gauche = if (gauche == it) null else it
            }
            gauche?.let { v ->
                Box(Modifier.width(230.dp).fillMaxHeight().background(Color(0xFFF7F7F7))) {
                    ContenuVolet(v, etat, tailles) { n -> portee.launch { etat.liste.scrollToItem(n) } }
                }
                VerticalDivider(color = Color(0xFFE2E2E2))
            }
            Box(Modifier.weight(1f).fillMaxHeight()) {
                Pages(etat, tailles, Modifier.fillMaxSize())
                IndicateurPage(etat, tailles.size, Modifier.align(Alignment.BottomEnd))
            }
            droite?.let { v ->
                VerticalDivider(color = Color(0xFFE2E2E2))
                Box(Modifier.width(280.dp).fillMaxHeight().background(Color(0xFFF7F7F7))) {
                    ContenuVolet(v, etat, tailles) { n -> portee.launch { etat.liste.scrollToItem(n) } }
                }
            }
            Rail(listOf(Volet.RECHERCHE to "rechercher", Volet.ANNOTER to "surligner", Volet.SIGNER to "signer", Volet.PLUS to "info"), droite) {
                droite = if (droite == it) null else it
            }
        }
    }
    if (allerA) AllerALaPage(tailles.size, { allerA = false }) { n -> portee.launch { etat.liste.scrollToItem(n) } }
}

@Composable
private fun Rail(elements: List<Pair<Volet, String>>, actif: Volet?, choisir: (Volet) -> Unit) {
    Column(Modifier.width(52.dp).fillMaxHeight().background(Color.White).padding(top = 6.dp),
        horizontalAlignment = Alignment.CenterHorizontally) {
        elements.forEach { (v, icone) ->
            val oui = v == actif
            IconButton(onClick = { choisir(v) }, modifier = Modifier.background(if (oui) Color(0xFFFCEBEC) else Color.Transparent, RoundedCornerShape(8.dp))) {
                Icon(Icones.get(icone, if (oui) ROUGE else Color(0xFF444444)), libelleVolet(v))
            }
            Spacer(Modifier.height(4.dp))
        }
    }
}

@Composable
private fun Bouton(icone: String, aide: String, action: () -> Unit) {
    IconButton(onClick = action) { Icon(Icones.get(icone), aide) }
}

@Composable
private fun libelleVolet(v: Volet): String = stringResource(when (v) {
    Volet.VIGNETTES -> R.string.pages_volet
    Volet.SIGNETS -> R.string.signets
    Volet.COMMENTAIRES -> R.string.commentaires
    Volet.RECHERCHE -> R.string.rechercher
    Volet.ANNOTER -> R.string.annoter
    Volet.SIGNER -> R.string.signer
    Volet.PLUS -> R.string.plus_court
})

// ================================================================ telephone : barre du bas + tiroirs
@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun DispositionTelephone(etat: EtatLecteur, tailles: List<Pair<Float, Float>>, fermer: () -> Unit) {
    var barres by remember { mutableStateOf(true) }
    var tiroir by remember { mutableStateOf<Volet?>(null) }
    val portee = rememberCoroutineScope()
    // en faisant defiler vers le bas, les barres se cachent ; vers le haut, elles reviennent
    val defilement = remember {
        object : NestedScrollConnection {
            override fun onPreScroll(available: Offset, source: NestedScrollSource): Offset {
                if (available.y < -8) barres = false else if (available.y > 8) barres = true
                return Offset.Zero
            }
        }
    }
    Box(Modifier.fillMaxSize().background(Color(0xFFE6E6E6))) {
        Pages(etat, tailles, Modifier.fillMaxSize().nestedScroll(defilement), auToucher = { barres = !barres })
        AnimatedVisibility(barres, Modifier.align(Alignment.TopCenter)) {
            Row(Modifier.fillMaxWidth().background(Color.White).padding(horizontal = 4.dp, vertical = 2.dp),
                verticalAlignment = Alignment.CenterVertically) {
                IconButton(onClick = fermer) { Icon(Icons.AutoMirrored.Filled.ArrowBack, stringResource(R.string.retour)) }
                Text(etat.doc.nom, Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis, fontWeight = FontWeight.SemiBold)
            }
        }
        IndicateurPage(etat, tailles.size, Modifier.align(Alignment.BottomEnd).padding(bottom = if (barres) 72.dp else 0.dp))
        AnimatedVisibility(barres, Modifier.align(Alignment.BottomCenter)) {
            NavigationBar(containerColor = Color.White, tonalElevation = 2.dp) {
                listOf(Volet.VIGNETTES to "organiser", Volet.RECHERCHE to "rechercher", Volet.ANNOTER to "surligner",
                    Volet.SIGNER to "signer", Volet.PLUS to "plus").forEach { (v, icone) ->
                    NavigationBarItem(selected = tiroir == v, onClick = { tiroir = v },
                        icon = { Icon(Icones.get(icone, if (tiroir == v) ROUGE else Color(0xFF444444)), null) },
                        label = { Text(libelleVolet(v), fontSize = 11.sp, maxLines = 1) })
                }
            }
        }
    }
    tiroir?.let { v ->
        ModalBottomSheet(onDismissRequest = { tiroir = null }, containerColor = Color(0xFFF7F7F7)) {
            Box(Modifier.fillMaxWidth().heightIn(min = 200.dp, max = 560.dp)) {
                ContenuVolet(v, etat, tailles) { n ->
                    portee.launch { etat.liste.scrollToItem(n) }
                    if (v != Volet.RECHERCHE) tiroir = null
                }
            }
        }
    }
}

// ================================================================ contenu des volets / tiroirs
@Composable
private fun ContenuVolet(v: Volet, etat: EtatLecteur, tailles: List<Pair<Float, Float>>, aller: (Int) -> Unit) {
    val ctx = LocalContext.current
    when (v) {
        Volet.VIGNETTES -> Vignettes(etat, tailles, aller)
        Volet.SIGNETS -> Signets(etat.doc, aller)
        Volet.COMMENTAIRES -> Commentaires(etat.doc, aller)
        Volet.RECHERCHE -> Recherche(etat, aller)
        Volet.ANNOTER -> Bientot(stringResource(R.string.annoter), stringResource(R.string.bientot_annoter),
            listOf("surligner", "souligner", "barrer", "commentaire", "modifier"))
        Volet.SIGNER -> Bientot(stringResource(R.string.signer), stringResource(R.string.bientot_signer),
            listOf("signer", "paraphe", "tampon", "formulaire"))
        Volet.PLUS -> {
            var allerA by remember { mutableStateOf(false) }
            var signets by remember { mutableStateOf(false) }
            var comms by remember { mutableStateOf(false) }
            when {
                signets -> Signets(etat.doc, aller)
                comms -> Commentaires(etat.doc, aller)
                else -> Column(Modifier.padding(8.dp)) {
                    LigneAction("suivante", stringResource(R.string.aller_page)) { allerA = true }
                    LigneAction("liste_fichiers", stringResource(R.string.signets)) { signets = true }
                    LigneAction("commentaire", stringResource(R.string.commentaires)) { comms = true }
                    LigneAction("courriel", stringResource(R.string.partager)) { partager(ctx, etat.doc) }
                    LigneAction("imprimer", stringResource(R.string.imprimer)) { imprimer(ctx, etat.doc) }
                    LigneAction("largeur", stringResource(R.string.ajuster)) { etat.echelle = 1f; etat.decalage = Offset.Zero }
                    Spacer(Modifier.height(8.dp))
                    Text(stringResource(R.string.infos_doc, etat.doc.nom, tailles.size), Modifier.padding(8.dp),
                        fontSize = 12.sp, color = Color.Gray)
                }
            }
            if (allerA) AllerALaPage(tailles.size, { allerA = false }, aller)
        }
    }
}

@Composable
private fun LigneAction(icone: String, texte: String, action: () -> Unit) {
    Row(Modifier.fillMaxWidth().clickable(onClick = action).padding(horizontal = 12.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically) {
        Icon(Icones.get(icone), null)
        Spacer(Modifier.width(14.dp))
        Text(texte)
    }
}

@Composable
private fun Bientot(titre: String, texte: String, icones: List<String>) {
    Column(Modifier.padding(16.dp)) {
        Text(titre, fontWeight = FontWeight.SemiBold)
        Spacer(Modifier.height(10.dp))
        Row { icones.forEach { Icon(Icones.get(it, Color(0xFFAAAAAA)), null, Modifier.padding(end = 12.dp)) } }
        Spacer(Modifier.height(10.dp))
        Text(texte, fontSize = 13.sp, color = Color.Gray)
    }
}

@Composable
private fun Vignettes(etat: EtatLecteur, tailles: List<Pair<Float, Float>>, aller: (Int) -> Unit) {
    val largeurPx = with(LocalDensity.current) { 110.dp.toPx().toInt() }
    val courante = etat.page
    LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(12.dp), verticalArrangement = Arrangement.spacedBy(10.dp),
        horizontalAlignment = Alignment.CenterHorizontally) {
        itemsIndexed(tailles) { n, (w, h) ->
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                ImagePage(etat, n, largeurPx, w, h, Modifier.width(110.dp)
                    .border(if (n == courante) 2.dp else 1.dp, if (n == courante) ROUGE else Color(0xFFCFCFCF))
                    .clickable { aller(n) }, marques = false)
                Text("${n + 1}", fontSize = 12.sp, color = Color.Gray)
            }
        }
    }
}

@Composable
private fun Signets(doc: DocumentPdf, aller: (Int) -> Unit) {
    val liste by produceState<List<Signet>?>(null, doc) { value = doc.signets() }
    val l = liste
    when {
        l == null -> Text(stringResource(R.string.ouverture), Modifier.padding(16.dp))
        l.isEmpty() -> Text(stringResource(R.string.aucun_signet), Modifier.padding(16.dp), color = Color.Gray)
        else -> LazyColumn(Modifier.fillMaxSize()) {
            items(l) { s ->
                Row(Modifier.fillMaxWidth().clickable(enabled = s.page >= 0) { aller(s.page) }
                    .padding(start = (12 + 14 * s.profondeur).dp, end = 12.dp, top = 10.dp, bottom = 10.dp)) {
                    Text(s.titre, Modifier.weight(1f), fontSize = 14.sp)
                    if (s.page >= 0) Text("${s.page + 1}", fontSize = 12.sp, color = Color.Gray)
                }
            }
        }
    }
}

@Composable
private fun Commentaires(doc: DocumentPdf, aller: (Int) -> Unit) {
    val liste by produceState<List<Commentaire>?>(null, doc) { value = doc.commentaires() }
    val l = liste
    when {
        l == null -> Text(stringResource(R.string.ouverture), Modifier.padding(16.dp))
        l.isEmpty() -> Text(stringResource(R.string.aucun_commentaire), Modifier.padding(16.dp), color = Color.Gray)
        else -> LazyColumn(Modifier.fillMaxSize()) {
            items(l) { c ->
                Column(Modifier.fillMaxWidth().clickable { aller(c.page) }.padding(horizontal = 12.dp, vertical = 8.dp)) {
                    Text(stringResource(R.string.page_n, c.page + 1) + if (c.auteur.isNotBlank()) " · " + c.auteur else "",
                        fontSize = 12.sp, color = Color.Gray)
                    Text(c.texte.ifBlank { "—" }, fontSize = 14.sp, maxLines = 3, overflow = TextOverflow.Ellipsis)
                }
                HorizontalDivider(color = Color(0xFFE6E6E6))
            }
        }
    }
}

@Composable
private fun Recherche(etat: EtatLecteur, aller: (Int) -> Unit) {
    val portee = rememberCoroutineScope()
    var texte by remember { mutableStateOf(etat.recherche) }
    fun lancer() {
        etat.recherche = texte
        etat.cherche = true
        portee.launch {
            etat.trouves = etat.doc.rechercher(texte)
            etat.cherche = false
            etat.trouves.firstOrNull()?.let { aller(it.page) }
        }
    }
    Column(Modifier.fillMaxSize().padding(12.dp)) {
        OutlinedTextField(texte, { texte = it }, Modifier.fillMaxWidth(), singleLine = true,
            placeholder = { Text(stringResource(R.string.rechercher_texte)) },
            trailingIcon = { IconButton(onClick = { lancer() }) { Icon(Icones.get("rechercher"), stringResource(R.string.rechercher)) } },
            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
            keyboardActions = KeyboardActions(onSearch = { lancer() }))
        Spacer(Modifier.height(8.dp))
        when {
            etat.cherche -> Text(stringResource(R.string.recherche_en_cours), color = Color.Gray)
            etat.recherche.isNotBlank() && etat.trouves.isEmpty() -> Text(stringResource(R.string.rien_trouve), color = Color.Gray)
            etat.trouves.isNotEmpty() -> {
                Text(stringResource(R.string.trouve_n, etat.trouves.sumOf { it.zones.size }, etat.trouves.size), fontSize = 13.sp)
                LazyColumn(Modifier.fillMaxSize()) {
                    items(etat.trouves) { t ->
                        Text(stringResource(R.string.page_n, t.page + 1) + " · " + t.zones.size,
                            Modifier.fillMaxWidth().clickable { aller(t.page) }.padding(vertical = 10.dp))
                    }
                }
            }
        }
    }
}

// ================================================================ pages
@Composable
private fun Pages(etat: EtatLecteur, tailles: List<Pair<Float, Float>>, modifier: Modifier, auToucher: (() -> Unit)? = null) {
    BoxWithConstraints(modifier
        .pointerInput(Unit) {
            // deux doigts : zoom de 1x a 5x, et deplacement quand on est zoome
            detectTransformGestures { _, pan, zoom, _ ->
                etat.echelle = (etat.echelle * zoom).coerceIn(1f, 5f)
                etat.decalage = if (etat.echelle == 1f) Offset.Zero else etat.decalage + pan
            }
        }
        .pointerInput(auToucher) {
            detectTapGestures(
                onTap = { auToucher?.invoke() },
                onDoubleTap = { etat.echelle = if (etat.echelle > 1.01f) 1f else 2f; if (etat.echelle == 1f) etat.decalage = Offset.Zero })
        }) {
        val largeurPx = with(LocalDensity.current) { (maxWidth - 16.dp).toPx().toInt() }
        LazyColumn(state = etat.liste, modifier = Modifier.fillMaxSize().graphicsLayer(
            scaleX = etat.echelle, scaleY = etat.echelle, translationX = etat.decalage.x, translationY = etat.decalage.y),
            contentPadding = PaddingValues(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            itemsIndexed(tailles) { n, (w, h) ->
                ImagePage(etat, n, largeurPx, w, h, Modifier.fillMaxWidth())
            }
        }
    }
}

@Composable
private fun ImagePage(etat: EtatLecteur, n: Int, largeurPx: Int, w: Float, h: Float, modifier: Modifier, marques: Boolean = true) {
    val image by produceState<Bitmap?>(null, etat.doc, n, largeurPx) {
        value = try { etat.doc.rendre(n, largeurPx) } catch (_: Exception) { null }
    }
    Box(modifier.aspectRatio((w / h).coerceIn(0.1f, 10f)).background(Color.White)) {
        image?.let { Image(it.asImageBitmap(), null, Modifier.fillMaxSize()) }
        val zones = if (marques) etat.trouves.firstOrNull { it.page == n }?.zones else null
        if (!zones.isNullOrEmpty()) {
            Canvas(Modifier.fillMaxSize()) {           // resultats de la recherche surlignes
                val k = size.width / w
                zones.forEach { z ->
                    drawRect(Color(0x66FFD200), Offset(z[0] * k, z[1] * k), Size((z[2] - z[0]) * k, (z[3] - z[1]) * k))
                }
            }
        }
    }
}

@Composable
private fun IndicateurPage(etat: EtatLecteur, total: Int, modifier: Modifier) {
    Text(stringResource(R.string.page_sur, etat.page + 1, total),
        modifier.padding(12.dp).background(Color(0xAA000000), RoundedCornerShape(12.dp)).padding(horizontal = 10.dp, vertical = 4.dp),
        color = Color.White, fontSize = 13.sp)
}

@Composable
private fun AllerALaPage(total: Int, fermer: () -> Unit, aller: (Int) -> Unit) {
    var t by remember { mutableStateOf("") }
    AlertDialog(onDismissRequest = fermer,
        title = { Text(stringResource(R.string.aller_page)) },
        text = {
            OutlinedTextField(t, { t = it.filter(Char::isDigit) }, singleLine = true,
                label = { Text("1 – $total") }, keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number))
        },
        confirmButton = {
            TextButton(onClick = { t.toIntOrNull()?.let { aller((it - 1).coerceIn(0, total - 1)) }; fermer() }) {
                Text(stringResource(R.string.ok))
            }
        },
        dismissButton = { TextButton(onClick = fermer) { Text(stringResource(R.string.annuler)) } })
}

@Composable
private fun DemandeMotDePasse(doc: DocumentPdf, ok: () -> Unit, annuler: () -> Unit) {
    var mdp by remember { mutableStateOf("") }
    var faux by remember { mutableStateOf(false) }
    AlertDialog(onDismissRequest = annuler,
        title = { Text(stringResource(R.string.mot_de_passe)) },
        text = {
            Column {
                Text(stringResource(R.string.protege, doc.nom))
                Spacer(Modifier.height(8.dp))
                OutlinedTextField(mdp, { mdp = it; faux = false }, singleLine = true,
                    visualTransformation = PasswordVisualTransformation(), isError = faux,
                    supportingText = { if (faux) Text(stringResource(R.string.mdp_faux)) })
            }
        },
        confirmButton = { TextButton(onClick = { if (doc.motDePasse(mdp)) ok() else faux = true }) { Text(stringResource(R.string.ok)) } },
        dismissButton = { TextButton(onClick = annuler) { Text(stringResource(R.string.annuler)) } })
}

/** Page ou l'on s'etait arrete, par document (reprise a la reouverture). */
object PagesLues {
    private fun prefs(ctx: Context) = ctx.getSharedPreferences("pages_lues", Context.MODE_PRIVATE)
    fun lire(ctx: Context, uri: String): Int = prefs(ctx).getInt(empreinte(uri), 0)
    fun ecrire(ctx: Context, uri: String, page: Int) { prefs(ctx).edit().putInt(empreinte(uri), page).apply() }
}

/** Partager : l'application e-mail d'Android, un Drive, une messagerie... (choix d'Android). */
fun partager(ctx: Context, doc: DocumentPdf) {
    val u = FileProvider.getUriForFile(ctx, ctx.packageName + ".fichiers", doc.fichier)
    val i = Intent(Intent.ACTION_SEND).setType("application/pdf").putExtra(Intent.EXTRA_STREAM, u)
        .putExtra(Intent.EXTRA_SUBJECT, doc.nom).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
    ctx.startActivity(Intent.createChooser(i, ctx.getString(R.string.partager)))
}

/** Imprimer : service d'impression d'Android (imprimantes du reseau, « Enregistrer au format PDF »...). */
fun imprimer(ctx: Context, doc: DocumentPdf) {
    val pm = ctx.getSystemService(Context.PRINT_SERVICE) as PrintManager
    pm.print(doc.nom, object : PrintDocumentAdapter() {
        override fun onLayout(ancien: PrintAttributes?, nouveau: PrintAttributes?, annul: CancellationSignal?,
                              rappel: LayoutResultCallback, extras: Bundle?) {
            if (annul?.isCanceled == true) { rappel.onLayoutCancelled(); return }
            rappel.onLayoutFinished(PrintDocumentInfo.Builder(doc.nom)
                .setContentType(PrintDocumentInfo.CONTENT_TYPE_DOCUMENT).setPageCount(doc.nbPages()).build(), true)
        }

        override fun onWrite(pages: Array<out PageRange>?, destination: ParcelFileDescriptor, annul: CancellationSignal?,
                             rappel: WriteResultCallback) {
            try {
                doc.fichier.inputStream().use { e ->
                    ParcelFileDescriptor.AutoCloseOutputStream(destination).use { s -> e.copyTo(s) }
                }
                rappel.onWriteFinished(arrayOf(PageRange.ALL_PAGES))
            } catch (e: Exception) {
                rappel.onWriteFailed(e.message)
            }
        }
    }, null)
}
