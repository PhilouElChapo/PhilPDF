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
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectTransformGestures
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material.icons.filled.Share
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.FileProvider
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun Lecteur(doc: DocumentPdf, fermer: () -> Unit) {
    val ctx = LocalContext.current
    BackHandler(onBack = fermer)
    var deverrouille by remember(doc) { mutableStateOf(!doc.besoinMotDePasse()) }
    var tailles by remember(doc) { mutableStateOf<List<Pair<Float, Float>>?>(null) }
    LaunchedEffect(doc, deverrouille) {
        if (deverrouille) {
            tailles = doc.tailles()
            Recents.ajouter(ctx, doc.uri, doc.nom, tailles!!.size)
            Miniatures.fabriquer(ctx, doc)
        }
    }
    var menu by remember { mutableStateOf(false) }

    Scaffold(topBar = {
        TopAppBar(
            title = { Text(doc.nom, maxLines = 1, overflow = TextOverflow.Ellipsis, fontSize = 17.sp) },
            navigationIcon = {
                IconButton(onClick = fermer) { Icon(Icons.AutoMirrored.Filled.ArrowBack, stringResource(R.string.retour)) }
            },
            actions = {
                IconButton(onClick = { partager(ctx, doc) }) { Icon(Icons.Default.Share, stringResource(R.string.partager)) }
                Box {
                    IconButton(onClick = { menu = true }) { Icon(Icons.Default.MoreVert, stringResource(R.string.plus)) }
                    DropdownMenu(expanded = menu, onDismissRequest = { menu = false }) {
                        DropdownMenuItem(text = { Text(stringResource(R.string.imprimer)) },
                            onClick = { menu = false; imprimer(ctx, doc) })
                    }
                }
            })
    }) { marges ->
        Box(Modifier.padding(marges).fillMaxSize().background(Color(0xFFE6E6E6))) {
            val t = tailles
            when {
                !deverrouille -> DemandeMotDePasse(doc, { deverrouille = true }, fermer)
                t == null -> Text(stringResource(R.string.ouverture), Modifier.align(Alignment.Center))
                else -> BoxWithConstraints(Modifier.fillMaxSize()) {
                    // tablette ou ecran large : vignettes a gauche, comme sous Windows
                    val large = maxWidth >= 720.dp
                    val etat = rememberLazyListState()
                    val portee = rememberCoroutineScope()
                    Row(Modifier.fillMaxSize()) {
                        if (large) {
                            Vignettes(doc, t, etat.firstVisibleItemIndex) { n -> portee.launch { etat.scrollToItem(n) } }
                        }
                        Pages(doc, t, etat, Modifier.weight(1f))
                    }
                    Text(stringResource(R.string.page_sur, etat.firstVisibleItemIndex + 1, t.size),
                        Modifier.align(Alignment.BottomEnd).padding(12.dp)
                            .background(Color(0xAA000000), RoundedCornerShape(12.dp))
                            .padding(horizontal = 10.dp, vertical = 4.dp),
                        color = Color.White, fontSize = 13.sp)
                }
            }
        }
    }
}

@Composable
private fun Pages(doc: DocumentPdf, tailles: List<Pair<Float, Float>>, etat: androidx.compose.foundation.lazy.LazyListState,
                  modifier: Modifier) {
    var echelle by remember { mutableFloatStateOf(1f) }
    var decalage by remember { mutableStateOf(androidx.compose.ui.geometry.Offset.Zero) }
    BoxWithConstraints(modifier.fillMaxHeight()
        .pointerInput(Unit) {
            // deux doigts : zoom de 1x a 5x, et deplacement quand on est zoome
            detectTransformGestures { _, pan, zoom, _ ->
                echelle = (echelle * zoom).coerceIn(1f, 5f)
                decalage = if (echelle == 1f) androidx.compose.ui.geometry.Offset.Zero else decalage + pan
            }
        }) {
        val largeurPx = with(LocalDensity.current) { (maxWidth - 16.dp).toPx().toInt() }
        LazyColumn(state = etat, modifier = Modifier.fillMaxSize().graphicsLayer(
            scaleX = echelle, scaleY = echelle, translationX = decalage.x, translationY = decalage.y),
            contentPadding = PaddingValues(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            itemsIndexed(tailles) { n, (w, h) ->
                ImagePage(doc, n, largeurPx, w, h, Modifier.fillMaxWidth())
            }
        }
    }
}

@Composable
private fun ImagePage(doc: DocumentPdf, n: Int, largeurPx: Int, w: Float, h: Float, modifier: Modifier) {
    val image by produceState<Bitmap?>(null, doc, n, largeurPx) {
        value = try { doc.rendre(n, largeurPx) } catch (_: Exception) { null }
    }
    Box(modifier.aspectRatio((w / h).coerceIn(0.1f, 10f)).background(Color.White)) {
        image?.let { Image(it.asImageBitmap(), null, Modifier.fillMaxSize()) }
    }
}

@Composable
private fun Vignettes(doc: DocumentPdf, tailles: List<Pair<Float, Float>>, courante: Int, aller: (Int) -> Unit) {
    val largeurPx = with(LocalDensity.current) { 110.dp.toPx().toInt() }
    LazyColumn(Modifier.width(140.dp).fillMaxHeight().background(Color(0xFFF3F3F3)),
        contentPadding = PaddingValues(12.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        itemsIndexed(tailles) { n, (w, h) ->
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                ImagePage(doc, n, largeurPx, w, h, Modifier.width(110.dp)
                    .border(if (n == courante) 2.dp else 1.dp, if (n == courante) ROUGE else Color(0xFFCFCFCF))
                    .clickable { aller(n) })
                Text("${n + 1}", fontSize = 12.sp, color = Color.Gray)
            }
        }
    }
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
