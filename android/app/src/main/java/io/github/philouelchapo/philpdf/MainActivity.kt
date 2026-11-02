package io.github.philouelchapo.philpdf

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Box
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
        super.onCreate(savedInstanceState)
        Journal.demarrer(this)
        // plantage : la cause est notee dans le journal (Accueil > Aide > Journal) avant que l'application se ferme
        val avant = Thread.getDefaultUncaughtExceptionHandler()
        Thread.setDefaultUncaughtExceptionHandler { t, e ->
            try { Journal.ecrire("plantage", e.stackTraceToString().take(3000)) } catch (_: Exception) {}
            avant?.uncaughtException(t, e)
        }
        DocumentPdf.nettoyerCache(this)
        recu.value = uriDe(intent)
        setContent {
            MaterialTheme(colorScheme = lightColorScheme(primary = ROUGE)) {
                Surface(Modifier.fillMaxSize()) {
                    // marges des barres d'Android et du clavier, transmises aux fenetres (Fenetre) : rien ne passe dessous
                    val marges = androidx.compose.foundation.layout.WindowInsets.safeDrawing.asPaddingValues()
                    androidx.compose.runtime.CompositionLocalProvider(LocalMarges provides marges) {
                        Box(Modifier.safeDrawingPadding()) { Application(recu) }
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

    val d = doc
    if (d == null) {
        Accueil(ouvrir = { ouvrir(it) }, choisir = { selecteur.launch(arrayOf("application/pdf")) })
    } else {
        Lecteur(d) { d.fermer(); doc = null }
    }
    erreur?.let { e ->
        AlertDialog(onDismissRequest = { erreur = null }, text = { Text(e) },
            confirmButton = { TextButton(onClick = { erreur = null }) { Text(stringResource(R.string.ok)) } })
    }
}
