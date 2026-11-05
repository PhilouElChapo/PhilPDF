package io.github.philouelchapo.philpdf

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import androidx.activity.enableEdgeToEdge
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.asPaddingValues
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.core.content.IntentCompat
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {
    /** PDF recu d'une autre application (« Ouvrir avec », « Partager »). */
    private val recu = mutableStateOf<Uri?>(null)

    override fun onCreate(savedInstanceState: Bundle?) {
        // affichage de bord a bord sur toutes les versions d'Android (Android 15 l'impose) ; les marges des barres
        // sont deja respectees partout (safeDrawingPadding, Fenetre)
        enableEdgeToEdge()
        super.onCreate(savedInstanceState)
        Journal.demarrer(this)
        // plantage : la cause est notee dans le journal (Accueil > Aide > Journal) avant que l'application se ferme
        val avant = Thread.getDefaultUncaughtExceptionHandler()
        Thread.setDefaultUncaughtExceptionHandler { t, e ->
            try { Journal.ecrire("plantage", e.stackTraceToString().take(3000)) } catch (_: Exception) {}
            avant?.uncaughtException(t, e)
        }
        recu.value = uriDe(intent)
        setContent {
            MaterialTheme(colorScheme = lightColorScheme(primary = ROUGE)) {
                Surface(Modifier.fillMaxSize()) {
                    // marges des barres d'Android et du clavier, transmises aux fenetres (Fenetre) : rien ne passe dessous
                    val marges = androidx.compose.foundation.layout.WindowInsets.safeDrawing.asPaddingValues()
                    androidx.compose.runtime.CompositionLocalProvider(LocalMarges provides marges) {
                        // ecran de demarrage (logo, version, etape) tant que le moteur PDF se charge
                        var pret by androidx.compose.runtime.saveable.rememberSaveable { mutableStateOf(false) }
                        Box(Modifier.safeDrawingPadding()) { if (pret) Application(recu) else Demarrage(recu.value != null) { pret = true } }
                    }
                }
            }
        }
    }

    override fun onResume() {
        super.onResume()
        Nuage.activite = java.lang.ref.WeakReference(this)   // Android y montre « Autoriser » si besoin
        Nuage.premierPlan.value = true
    }

    override fun onPause() {
        Nuage.premierPlan.value = false
        super.onPause()
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        uriDe(intent)?.let { recu.value = it }
    }

    private fun uriDe(i: Intent?): Uri? = when (i?.action) {
        Intent.ACTION_VIEW -> i.data?.takeIf { it.scheme != "philpdf" }   // philpdf://connecte = retour du navigateur
        Intent.ACTION_SEND -> IntentCompat.getParcelableExtra(i, Intent.EXTRA_STREAM, Uri::class.java)
        else -> null
    }
}

@Composable
fun Application(recu: MutableState<Uri?>) {
    val ctx = LocalContext.current
    val portee = rememberCoroutineScope()
    var doc by remember { mutableStateOf<DocumentPdf?>(null) }
    var erreur by remember { mutableStateOf<String?>(null) }
    val texteInaccessible = stringResource(R.string.inaccessible)

    fun ouvrir(uri: Uri) {
        portee.launch {
            try {
                Distants.rafraichir(ctx, uri)          // fichier venu d'un compte : derniere version si possible
                val d = DocumentPdf.ouvrir(ctx, uri)
                doc?.fermer()
                doc = d
                val reparees = d.reparerDebris()
                if (reparees.isNotEmpty()) erreur = ctx.getString(R.string.repare_debris, reparees.joinToString(", "))
            } catch (e: SecurityException) {
                erreur = texteInaccessible
            } catch (e: java.io.FileNotFoundException) {
                erreur = texteInaccessible
            } catch (e: Exception) {
                Journal.ecrire("ouverture", "${uri.scheme} : échec ($e)")
                erreur = ctx.getString(R.string.illisible, e.message ?: e.javaClass.simpleName)
            }
        }
    }

    val selecteur = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { u -> u?.let { ouvrir(it) } }
    LaunchedEffect(recu.value) {
        recu.value?.let { ouvrir(it); recu.value = null }
    }
    LaunchedEffect(Ouvrir.demande.value) {                   // PDF signe : rouvert a la place de l'autre
        Ouvrir.demande.value?.let { ouvrir(it); Ouvrir.demande.value = null }
    }

    var numeriser by remember { mutableStateOf(false) }
    val d = doc
    if (numeriser) EcranNumerisation(fermer = { numeriser = false }) { f ->
        numeriser = false
        portee.launch {
            try {
                val nd = DocumentPdf.ouvrir(ctx, Uri.fromFile(f))
                nd.neuf = true; nd.modifie = true; nd.ocrAuto = true
                doc?.fermer(); doc = nd
            } catch (e: Exception) { erreur = ctx.getString(R.string.illisible, e.message ?: e.javaClass.simpleName) }
        }
    }
    if (d == null) {
        Accueil(ouvrir = { ouvrir(it) }, choisir = { selecteur.launch(arrayOf("application/pdf")) }, numeriser = { numeriser = true })
    } else {
        Lecteur(d) { d.fermer(); doc = null }
    }
    erreur?.let { e ->
        AlertDialog(onDismissRequest = { erreur = null }, text = { Text(e) },
            confirmButton = { TextButton(onClick = { erreur = null }) { Text(stringResource(R.string.ok)) } })
    }
}

/** Ecran de demarrage : on voit tout de suite que PhilPDF demarre, et ce qu'il fait. */
@Composable
fun Demarrage(avecDocument: Boolean, fini: () -> Unit) {
    val ctx = LocalContext.current
    var etape by remember { mutableIntStateOf(R.string.demarrage_moteur) }
    LaunchedEffect(Unit) {
        val debut = System.currentTimeMillis()
        kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.IO) {
            // charge la bibliotheque MuPDF (la plus longue etape au premier lancement)
            try { Class.forName("com.artifex.mupdf.fitz.Context") } catch (_: Throwable) {}
        }
        etape = R.string.demarrage_nettoyage
        kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.IO) { DocumentPdf.nettoyerCache(ctx) }
        if (avecDocument) etape = R.string.demarrage_document
        // assez long pour etre lu, sans retarder : 0,6 s au plus en tout
        val reste = 600 - (System.currentTimeMillis() - debut)
        if (reste > 0) kotlinx.coroutines.delay(reste)
        fini()
    }
    androidx.compose.foundation.layout.Column(Modifier.fillMaxSize().background(androidx.compose.ui.graphics.Color.White),
        horizontalAlignment = androidx.compose.ui.Alignment.CenterHorizontally,
        verticalArrangement = androidx.compose.foundation.layout.Arrangement.Center) {
        androidx.compose.foundation.Image(androidx.compose.ui.res.painterResource(R.drawable.logo), null,
            Modifier.size(112.dp))
        androidx.compose.foundation.layout.Spacer(Modifier.height(18.dp))
        Text("PhilPDF", fontSize = 26.sp, fontWeight = androidx.compose.ui.text.font.FontWeight.SemiBold)
        Text(BuildConfig.VERSION_NAME, fontSize = 13.sp, color = androidx.compose.ui.graphics.Color.Gray)
        androidx.compose.foundation.layout.Spacer(Modifier.height(28.dp))
        LinearProgressIndicator(Modifier.width(180.dp), color = ROUGE)
        androidx.compose.foundation.layout.Spacer(Modifier.height(10.dp))
        Text(stringResource(etape), fontSize = 13.sp, color = androidx.compose.ui.graphics.Color(0xFF555555))
    }
}
