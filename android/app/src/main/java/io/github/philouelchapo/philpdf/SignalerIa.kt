package io.github.philouelchapo.philpdf

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder

/** Signaler un resultat de l'IA (regle Google Play sur le contenu genere par l'IA) : envoye au developpeur, sans quitter
 *  l'appli, par un formulaire Google (le meme que sous Windows). Part : la fonction, le service, le motif, votre
 *  commentaire et le texte de la reponse (que vous voyez et pouvez raccourcir) ; jamais le document. */
object Signalement {
    private const val FORMULAIRE =
        "https://docs.google.com/forms/d/e/1FAIpQLSfNWw9iPeSQqrQkJOjrQd6BacqPP63cTXqero6QcU7biwfVJA/formResponse"
    private const val FONCTION = "entry.1590891463"
    private const val SERVICE = "entry.2084492064"
    private const val MOTIF = "entry.1760884179"
    private const val COMMENTAIRE = "entry.723269897"
    private const val TEXTE = "entry.1436294086"
    private const val VERSION = "entry.1122929308"
    const val MAX_TEXTE = 8000

    /** Derniere reponse de l'IA (pour « Signaler un resultat de l'IA » du menu Plus). */
    @Volatile var derniere: String = ""

    suspend fun envoyer(fonction: String, motif: String, commentaire: String, texte: String): Boolean = withContext(Dispatchers.IO) {
        val qui = Ia.dernier?.let { Ia.nom(it.first) + " " + it.second } ?: "?"
        val corps = listOf(FONCTION to fonction, SERVICE to qui, MOTIF to motif, COMMENTAIRE to commentaire,
            TEXTE to texte.take(MAX_TEXTE), VERSION to "Android " + BuildConfig.VERSION_NAME)
            .joinToString("&") { (k, v) -> k + "=" + URLEncoder.encode(v, "UTF-8") }
        try {
            val c = URL(FORMULAIRE).openConnection() as HttpURLConnection
            c.requestMethod = "POST"
            c.doOutput = true
            c.connectTimeout = 20_000; c.readTimeout = 30_000
            c.setRequestProperty("Content-Type", "application/x-www-form-urlencoded; charset=UTF-8")
            c.outputStream.use { it.write(corps.toByteArray()) }
            val code = c.responseCode
            c.disconnect()
            Journal.ecrire("signalement IA", "$fonction / $motif : réponse $code")
            code in 200..399
        } catch (e: Exception) {
            Journal.ecrire("signalement IA", "$fonction / $motif : échec ${e.message}")
            false
        }
    }
}

/** Petit bouton « Signaler ce resultat » a mettre sous chaque reponse de l'IA. */
@Composable
fun BoutonSignalerIa(fonction: String, texte: () -> String) {
    var ouvert by remember { mutableStateOf(false) }
    TextButton(onClick = { ouvert = true }) { Text(stringResource(R.string.sig_bouton), fontSize = 13.sp, color = Color(0xFF666666)) }
    if (ouvert) SignalerIa(fonction, texte()) { ouvert = false }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun SignalerIa(fonction: String, texte: String, fermer: () -> Unit) {
    val ctx = LocalContext.current
    val portee = rememberCoroutineScope()
    val motifs = listOf(R.string.sig_choquant, R.string.sig_dangereux, R.string.sig_faux, R.string.sig_autre)
    var motif by remember { mutableIntStateOf(-1) }
    var commentaire by remember { mutableStateOf("") }
    var envoye by remember { mutableStateOf(texte.take(Signalement.MAX_TEXTE)) }
    var occupe by remember { mutableStateOf(false) }
    AlertDialog(onDismissRequest = { if (!occupe) fermer() },
        title = { Text(stringResource(R.string.sig_titre)) },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState())) {
                Text(stringResource(R.string.sig_aide), fontSize = 13.sp, color = Color.Gray)
                Spacer(Modifier.height(8.dp))
                Text(stringResource(R.string.sig_motif), fontSize = 14.sp)
                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    motifs.forEachIndexed { i, m -> FilterChip(motif == i, { motif = i }, { Text(stringResource(m)) }) }
                }
                OutlinedTextField(commentaire, { commentaire = it }, Modifier.fillMaxWidth(), minLines = 2,
                    label = { Text(stringResource(R.string.sig_commentaire)) })
                Spacer(Modifier.height(6.dp))
                OutlinedTextField(envoye, { envoye = it.take(Signalement.MAX_TEXTE) }, Modifier.fillMaxWidth().heightIn(max = 220.dp),
                    label = { Text(stringResource(R.string.sig_texte)) })
            }
        },
        confirmButton = {
            Button(onClick = {
                occupe = true
                portee.launch {
                    val ok = Signalement.envoyer(fonction, ctx.getString(motifs[motif]), commentaire.trim(), envoye)
                    occupe = false
                    android.widget.Toast.makeText(ctx, ctx.getString(if (ok) R.string.sig_merci else R.string.sig_echec),
                        android.widget.Toast.LENGTH_LONG).show()
                    if (ok) fermer()
                }
            }, enabled = motif >= 0 && !occupe, colors = ButtonDefaults.buttonColors(containerColor = ROUGE)) {
                Text(stringResource(if (occupe) R.string.sig_envoi else R.string.sig_envoyer))
            }
        },
        dismissButton = { TextButton(onClick = fermer, enabled = !occupe) { Text(stringResource(R.string.annuler)) } })
}
