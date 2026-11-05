package io.github.philouelchapo.philpdf

import android.app.Activity
import android.content.Context
import android.content.ContextWrapper
import android.graphics.Bitmap
import android.graphics.PointF
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.IntentSenderRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.IntSize
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.FileProvider
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File

/** Une page numerisee : l'image redressee (avant amelioration) et sa version amelioree pour le modele en cours. */
private class PageScan(val image: Bitmap) {
    var apercu by mutableStateOf<Bitmap?>(null)
    var modeleApercu: Numerisation.Modele? = null
}

private fun Context.activite(): Activity? {
    var c: Context? = this
    while (c is ContextWrapper) { if (c is Activity) return c; c = c.baseContext }
    return null
}

/**
 * Ecran « Numeriser un document » : le scanner de Google s'il est sur le telephone (bords trouves en direct), sinon
 * l'appareil photo d'Android et notre recadrage (quatre coins a ajuster). Pages a la suite, modele au choix, puis le
 * PDF est cree, ouvert, et son texte reconnu (OCR).
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun EcranNumerisation(fermer: () -> Unit, ouvrirPdf: (File) -> Unit) {
    val ctx = LocalContext.current
    val portee = rememberCoroutineScope()
    val pages = remember { mutableStateListOf<PageScan>() }
    var modele by remember { mutableStateOf(Numerisation.Modele.valueOf(
        ctx.getSharedPreferences("numerisation", Context.MODE_PRIVATE).getString("modele", null) ?: "NOIR_BLANC")) }
    var aCadrer by remember { mutableStateOf<Pair<Bitmap, List<PointF>>?>(null) }
    var aRemplacer by remember { mutableStateOf<PageScan?>(null) }       // recadrer une page deja prise
    var aTourner by remember { mutableStateOf<PageScan?>(null) }         // redresser une page (angle)
    var occupe by remember { mutableStateOf<String?>(null) }
    var message by remember { mutableStateOf<String?>(null) }
    var googleEssaye by remember { mutableStateOf(false) }
    // « Magnificence IA » : pages a envoyer a Gemini (accord demande), avancement
    var magnifier by remember { mutableStateOf<List<Bitmap>?>(null) }
    var accordMagnifier by remember { mutableStateOf(false) }
    var avanceMagnifier by remember { mutableStateOf("") }
    val photo = remember { File(ctx.cacheDir, "ouverts/scan/photo.jpg").apply { parentFile?.mkdirs() } }

    fun ajouterBrute(bm: Bitmap) { aCadrer = bm to Numerisation.coins(bm) }
    fun charger(uris: List<Uri>, cadrer: Boolean) {
        occupe = ctx.getString(R.string.scan_preparation)
        portee.launch {
            val l = withContext(Dispatchers.IO) { uris.mapNotNull { runCatching { Numerisation.charger(ctx, it) }.getOrNull() } }
            occupe = null
            if (l.isEmpty()) { message = ctx.getString(R.string.scan_illisible); return@launch }
            if (cadrer && l.size == 1) ajouterBrute(l[0])
            else if (cadrer) {
                // plusieurs photos importees : chacune redressee automatiquement (a corriger en la retouchant)
                occupe = ctx.getString(R.string.scan_preparation)
                val r = withContext(Dispatchers.Default) { l.map { Numerisation.redresser(it, Numerisation.coins(it)) } }
                r.forEach { pages += PageScan(it) }; occupe = null
            } else {
                // pages du scanner de Google (deja recadrees) : lignes remises a l'horizontale
                occupe = ctx.getString(R.string.scan_preparation)
                val r = withContext(Dispatchers.Default) { l.map { Numerisation.aplomb(it) } }
                r.forEach { pages += PageScan(it) }; occupe = null
            }
        }
    }
    val appareil = rememberLauncherForActivityResult(ActivityResultContracts.TakePicture()) { ok ->
        if (ok) charger(listOf(Uri.fromFile(photo)), true)
    }
    fun prendrePhoto() {
        val u = FileProvider.getUriForFile(ctx, ctx.packageName + ".fichiers", photo)
        try { appareil.launch(u) } catch (e: Exception) { message = ctx.getString(R.string.scan_pas_appareil) }
    }
    val galerie = rememberLauncherForActivityResult(ActivityResultContracts.GetMultipleContents()) { l ->
        if (l.isNotEmpty()) charger(l, true)
    }
    val google = rememberLauncherForActivityResult(ActivityResultContracts.StartIntentSenderForResult()) { r ->
        if (r.resultCode == Activity.RESULT_OK) {
            val res = com.google.mlkit.vision.documentscanner.GmsDocumentScanningResult.fromActivityResultIntent(r.data)
            val l = res?.pages?.map { it.imageUri } ?: emptyList()
            Journal.ecrire("numérisation", "scanner Google : ${l.size} page(s)")
            if (l.isNotEmpty()) charger(l, false)          // deja recadrees et redressees par le scanner
        }
    }
    /** Le scanner de Google, sinon l'appareil photo. */
    fun numeriser() {
        val act = ctx.activite()
        if (act == null) { prendrePhoto(); return }
        try {
            val opt = com.google.mlkit.vision.documentscanner.GmsDocumentScannerOptions.Builder()
                .setGalleryImportAllowed(true).setPageLimit(30)
                .setResultFormats(com.google.mlkit.vision.documentscanner.GmsDocumentScannerOptions.RESULT_FORMAT_JPEG)
                .setScannerMode(com.google.mlkit.vision.documentscanner.GmsDocumentScannerOptions.SCANNER_MODE_FULL).build()
            com.google.mlkit.vision.documentscanner.GmsDocumentScanning.getClient(opt).getStartScanIntent(act)
                .addOnSuccessListener { s -> google.launch(IntentSenderRequest.Builder(s).build()) }
                .addOnFailureListener { e -> Journal.ecrire("numérisation", "scanner Google absent ($e) : appareil photo"); prendrePhoto() }
        } catch (e: Throwable) {
            Journal.ecrire("numérisation", "scanner Google indisponible ($e) : appareil photo"); prendrePhoto()
        }
    }
    LaunchedEffect(Unit) { if (!googleEssaye) { googleEssaye = true; numeriser() } }
    // apercus du modele choisi, page par page, sans bloquer l'ecran
    LaunchedEffect(modele, pages.size) {
        for (p in pages.toList()) if (p.modeleApercu != modele) {
            val m = modele
            p.apercu = withContext(Dispatchers.Default) { Numerisation.ameliorer(Numerisation.reduirePourApercu(p.image), m) }
            p.modeleApercu = m
        }
    }

    Fenetre(fermer) {
        Surface(Modifier.fillMaxSize(), color = Color(0xFFF3F3F3)) {
            Column(Modifier.fillMaxSize()) {
                Row(Modifier.fillMaxWidth().background(Color.White).padding(horizontal = 4.dp, vertical = 2.dp),
                    verticalAlignment = Alignment.CenterVertically) {
                    IconButton(onClick = fermer) { Icon(Icons.AutoMirrored.Filled.ArrowBack, stringResource(R.string.retour)) }
                    Column(Modifier.weight(1f)) {
                        TexteAjuste(stringResource(R.string.scan_titre), 17.sp)
                        Text(stringResource(R.string.scan_pages, pages.size), fontSize = 12.sp, color = Color.Gray)
                    }
                }
                HorizontalDivider(color = Color(0xFFE2E2E2))
                val ac = aCadrer
                if (ac != null) {
                    Cadrage(ac.first, ac.second, Modifier.weight(1f)) { c -> aCadrer = ac.first to c }
                    FlowRow(Modifier.fillMaxWidth().background(Color.White).padding(6.dp),
                        horizontalArrangement = Arrangement.spacedBy(8.dp, Alignment.CenterHorizontally)) {
                        if (aRemplacer == null) OutlinedButton(onClick = { aCadrer = null; prendrePhoto() }) { Text(stringResource(R.string.scan_reprendre)) }
                        else OutlinedButton(onClick = { aCadrer = null; aRemplacer = null }) { Text(stringResource(R.string.annuler)) }
                        OutlinedButton(onClick = { val b = ac.first; aCadrer = b to listOf(PointF(0f, 0f), PointF(b.width.toFloat(), 0f),
                            PointF(b.width.toFloat(), b.height.toFloat()), PointF(0f, b.height.toFloat())) }) { Text(stringResource(R.string.scan_toute_photo)) }
                        Button(onClick = {
                            val (b, c) = ac; aCadrer = null
                            occupe = ctx.getString(R.string.scan_preparation)
                            val rp = aRemplacer; aRemplacer = null
                            portee.launch {
                                val r = withContext(Dispatchers.Default) { Numerisation.redresser(b, c) }
                                val k = rp?.let { pages.indexOf(it) } ?: -1
                                if (k >= 0) pages[k] = PageScan(r) else pages += PageScan(r)
                                occupe = null
                            }
                        }, colors = ButtonDefaults.buttonColors(containerColor = ROUGE)) { Text(stringResource(R.string.scan_valider_cadre)) }
                    }
                } else {
                    // modele, pages, actions
                    FlowRow(Modifier.fillMaxWidth().background(Color.White).padding(horizontal = 8.dp, vertical = 4.dp),
                        horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        Numerisation.Modele.entries.forEach { m ->
                            FilterChip(selected = modele == m, onClick = {
                                modele = m
                                ctx.getSharedPreferences("numerisation", Context.MODE_PRIVATE).edit().putString("modele", m.name).apply()
                            }, label = { Text(stringResource(m.texte)) })
                        }
                    }
                    Text(stringResource(when (modele) {
                        Numerisation.Modele.NOIR_BLANC -> R.string.scan_nb_aide
                        Numerisation.Modele.COULEUR -> R.string.scan_couleur_aide
                        Numerisation.Modele.EMAIL -> R.string.scan_email_aide
                        Numerisation.Modele.PHOTO -> R.string.scan_photo_aide
                        Numerisation.Modele.MAGNIFICENCE -> R.string.scan_magnificence_aide
                    }), Modifier.fillMaxWidth().background(Color.White).padding(horizontal = 12.dp, vertical = 2.dp), fontSize = 12.sp, color = Color.Gray)
                    Box(Modifier.weight(1f).fillMaxWidth()) {
                        if (pages.isEmpty()) Text(stringResource(R.string.scan_vide), Modifier.align(Alignment.Center).padding(24.dp), color = Color.Gray)
                        LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(12.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                            itemsIndexed(pages, key = { _, p -> System.identityHashCode(p) }) { i, p ->
                                Column(Modifier.fillMaxWidth().background(Color.White, RoundedCornerShape(8.dp)).padding(8.dp)) {
                                    val a = p.apercu
                                    if (a != null) Image(a.asImageBitmap(), null, Modifier.fillMaxWidth().heightIn(max = 420.dp)
                                        .border(1.dp, Color(0xFFDDDDDD)), contentScale = ContentScale.Fit)
                                    else Box(Modifier.fillMaxWidth().height(160.dp), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
                                    FlowRow(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(4.dp, Alignment.CenterHorizontally)) {
                                        Text(stringResource(R.string.page_n, i + 1), Modifier.align(Alignment.CenterVertically), fontSize = 13.sp)
                                        TextButton(onClick = { if (i > 0) { pages.removeAt(i); pages.add(i - 1, p) } }, enabled = i > 0) { Text("↑") }
                                        TextButton(onClick = { if (i < pages.size - 1) { pages.removeAt(i); pages.add(i + 1, p) } }, enabled = i < pages.size - 1) { Text("↓") }
                                        TextButton(onClick = {
                                            portee.launch {
                                                val r = withContext(Dispatchers.Default) { Numerisation.quartDeTour(p.image) }
                                                val n = PageScan(r); pages[pages.indexOf(p)] = n
                                            }
                                        }) { Text("↻") }
                                        TextButton(onClick = { aTourner = p }) { Text(stringResource(R.string.redresser_bouton)) }
                                        TextButton(onClick = { aRemplacer = p; aCadrer = p.image to Numerisation.coins(p.image) }) {
                                            Text(stringResource(R.string.scan_recadrer)) }
                                        TextButton(onClick = { pages.remove(p) }) { Text(stringResource(R.string.supprimer), color = Color(0xFFC62828)) }
                                    }
                                }
                            }
                        }
                        occupe?.let { o ->
                            Column(Modifier.align(Alignment.Center).background(Color(0xEEFFFFFF), RoundedCornerShape(12.dp)).padding(20.dp),
                                horizontalAlignment = Alignment.CenterHorizontally) {
                                CircularProgressIndicator(); Spacer(Modifier.height(8.dp)); Text(o, fontSize = 14.sp)
                            }
                        }
                    }
                    // boutons fixes en bas (jamais sous les barres d'Android : Fenetre s'arrete au-dessus)
                    FlowRow(Modifier.fillMaxWidth().background(Color.White).padding(6.dp),
                        horizontalArrangement = Arrangement.spacedBy(8.dp, Alignment.CenterHorizontally)) {
                        OutlinedButton(onClick = { numeriser() }, enabled = occupe == null) { Text(stringResource(R.string.scan_page_suivante)) }
                        OutlinedButton(onClick = { galerie.launch("image/*") }, enabled = occupe == null) { Text(stringResource(R.string.scan_importer)) }
                        Button(onClick = {
                            val m = modele
                            val l = pages.map { it.image }
                            if (m == Numerisation.Modele.MAGNIFICENCE) { magnifier = l; return@Button }
                            occupe = ctx.getString(R.string.scan_creation)
                            portee.launch {
                                try {
                                    val f = withContext(Dispatchers.Default) {
                                        val o = l.mapIndexed { k, b ->
                                            occupe = ctx.getString(R.string.scan_creation_page, k + 1, l.size)
                                            Numerisation.octets(Numerisation.ameliorer(b, m), m)
                                        }
                                        Numerisation.fabriquerPdf(o, File(ctx.cacheDir, "ouverts/scan/" + System.currentTimeMillis() + "/" + Numerisation.nom()))
                                    }
                                    Journal.ecrire("numérisation", "${l.size} page(s), modèle $m, ${f.length() / 1024} Ko")
                                    occupe = null
                                    ouvrirPdf(f)
                                } catch (e: Exception) {
                                    occupe = null; message = ctx.getString(R.string.scan_echec, e.message ?: e.toString())
                                    Journal.ecrire("numérisation", "échec : $e")
                                }
                            }
                        }, enabled = pages.isNotEmpty() && occupe == null, colors = ButtonDefaults.buttonColors(containerColor = ROUGE)) {
                            Text(stringResource(R.string.scan_creer))
                        }
                    }
                }
            }
        }
    }
    aTourner?.let { p ->
        RedresserImage(p.image, stringResource(R.string.redresser_page_n, pages.indexOf(p) + 1), { aTourner = null }) { a, _t ->
            aTourner = null
            portee.launch {
                val r = withContext(Dispatchers.Default) { Numerisation.tourner(p.image, a) }
                val k = pages.indexOf(p); if (k >= 0) pages[k] = PageScan(r)
            }
        }
    }
    magnifier?.let { l ->
        if (!accordMagnifier) AlertDialog(onDismissRequest = { magnifier = null },
            title = { Text(stringResource(R.string.scan_magnificence)) },
            text = { Text(stringResource(R.string.scan_magnificence_accord, l.size)) },
            confirmButton = { TextButton(onClick = { accordMagnifier = true }) { Text(stringResource(R.string.ia_envoyer)) } },
            dismissButton = { TextButton(onClick = { magnifier = null }) { Text(stringResource(R.string.annuler)) } })
        else EnvoiIa("", avanceMagnifier.ifEmpty { stringResource(R.string.scan_magnificence_en_cours, 1, l.size) }, {
            val locales = ArrayList<Int>()
            var derniere: Exception? = null
            val o = l.mapIndexed { k, b ->
                avanceMagnifier = ctx.getString(R.string.scan_magnificence_en_cours, k + 1, l.size)
                val r = try { Numerisation.magnifier(ctx, b) } catch (e: Ia.ErreurIa) { derniere = e; null }
                // page non rendue par Gemini : amelioree ici, comme « Couleur », et on le dit
                if (r == null) { locales += k + 1; withContext(Dispatchers.Default) { Numerisation.octets(Numerisation.ameliorer(b, Numerisation.Modele.COULEUR), Numerisation.Modele.COULEUR) } }
                else withContext(Dispatchers.Default) { Numerisation.octets(r, Numerisation.Modele.MAGNIFICENCE) }
            }
            if (locales.size == l.size) throw derniere ?: Ia.ErreurIa(ctx.getString(R.string.ia_e_pas_image, "?"))
            withContext(Dispatchers.IO) { Numerisation.fabriquerPdf(o, File(ctx.cacheDir, "ouverts/scan/" + System.currentTimeMillis() + "/" + Numerisation.nom())) } to locales
        }, { (f, locales) ->
            Journal.ecrire("numérisation", "${l.size} page(s), Magnificence IA (${Ia.dernier?.second}), ${locales.size} améliorée(s) ici, ${f.length() / 1024} Ko")
            magnifier = null; accordMagnifier = false; avanceMagnifier = ""
            if (locales.isNotEmpty()) android.widget.Toast.makeText(ctx, ctx.getString(R.string.scan_magnificence_locales, locales.joinToString(", ")), android.widget.Toast.LENGTH_LONG).show()
            ouvrirPdf(f)
        }, { magnifier = null; accordMagnifier = false; avanceMagnifier = "" }, gemini = true)
    }
    message?.let { m ->
        AlertDialog(onDismissRequest = { message = null }, text = { Text(m) },
            confirmButton = { TextButton(onClick = { message = null }) { Text(stringResource(R.string.ok)) } })
    }
}

/** Photo et ses quatre coins a faire glisser ; le cadre suit le doigt. */
@Composable
private fun Cadrage(bm: Bitmap, coins: List<PointF>, modifier: Modifier, changer: (List<PointF>) -> Unit) {
    var taille by remember { mutableStateOf(IntSize.Zero) }
    val img = remember(bm) { bm.asImageBitmap() }
    var choisi by remember { mutableIntStateOf(-1) }
    val actuels by rememberUpdatedState(coins)
    Box(modifier.fillMaxWidth().background(Color(0xFF222222)).padding(12.dp).onSizeChanged { taille = it }) {
        if (taille.width == 0) return@Box
        // image ajustee dans la zone
        val e = minOf(taille.width.toFloat() / bm.width, taille.height.toFloat() / bm.height)
        val ox = (taille.width - bm.width * e) / 2; val oy = (taille.height - bm.height * e) / 2
        Canvas(Modifier.fillMaxSize().pointerInput(bm, e) {
            detectDragGestures(onDragStart = { p ->
                choisi = actuels.withIndex().minByOrNull { (_, c) -> kotlin.math.hypot(c.x * e + ox - p.x, c.y * e + oy - p.y) }
                    ?.takeIf { (_, c) -> kotlin.math.hypot(c.x * e + ox - p.x, c.y * e + oy - p.y) < 90f }?.index ?: -1
            }, onDragEnd = { choisi = -1 }) { ch, d ->
                if (choisi >= 0) {
                    ch.consume()
                    val l = actuels.map { PointF(it.x, it.y) }
                    l[choisi].x = (l[choisi].x + d.x / e).coerceIn(0f, bm.width.toFloat())
                    l[choisi].y = (l[choisi].y + d.y / e).coerceIn(0f, bm.height.toFloat())
                    changer(l)
                }
            }
        }) {
            drawImage(img, dstOffset = androidx.compose.ui.unit.IntOffset(ox.toInt(), oy.toInt()),
                dstSize = IntSize((bm.width * e).toInt(), (bm.height * e).toInt()))
            val pts = coins.map { Offset(it.x * e + ox, it.y * e + oy) }
            val chemin = Path().apply { moveTo(pts[0].x, pts[0].y); pts.drop(1).forEach { lineTo(it.x, it.y) }; close() }
            drawPath(chemin, Color(0x331A73E8))
            drawPath(chemin, Color(0xFF1A73E8), style = Stroke(4f))
            pts.forEachIndexed { k, p ->
                drawCircle(Color.White, if (k == choisi) 30f else 24f, p)
                drawCircle(Color(0xFF1A73E8), if (k == choisi) 30f else 24f, p, style = Stroke(5f))
            }
        }
    }
}
