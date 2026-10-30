package io.github.philouelchapo.philpdf

import android.accounts.AccountManager
import android.app.Activity
import android.graphics.BitmapFactory
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AccountCircle
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import kotlinx.coroutines.launch
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/** Rond en haut a droite de l'Accueil : photo (ou initiale) du compte Google relie, sinon silhouette grise. */
@Composable
fun PastilleCompte(version: Int, taille: Dp = 40.dp, onClick: () -> Unit) {
    val ctx = LocalContext.current
    val email = remember(version) { Google.email(ctx) }
    val photo = remember(version) {
        Google.photo(ctx).takeIf { it.exists() }?.let { BitmapFactory.decodeFile(it.absolutePath)?.asImageBitmap() }
    }
    Box(Modifier.size(taille).clip(CircleShape).clickable(onClick = onClick), contentAlignment = Alignment.Center) {
        when {
            email == null -> Icon(Icons.Filled.AccountCircle, stringResource(R.string.compte), Modifier.fillMaxSize(), tint = Color.Gray)
            photo != null -> Image(photo, email, Modifier.fillMaxSize().border(2.dp, Color(0xFF1A73E8), CircleShape).clip(CircleShape),
                contentScale = ContentScale.Crop)
            else -> Box(Modifier.fillMaxSize().background(ROUGE, CircleShape), contentAlignment = Alignment.Center) {
                Text((Google.nom(ctx)?.takeIf { it.isNotBlank() } ?: email).take(1).uppercase(), color = Color.White,
                    fontWeight = FontWeight.Bold, fontSize = 18.sp)
            }
        }
    }
}

/** Date ISO de PhilPDF Windows (2026-10-30T18:42:05) en clair. */
fun dateIso(t: String): String = try {
    val d = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss", Locale.FRANCE).parse(t.take(19))!!
    SimpleDateFormat("dd/MM/yyyy 'à' HH:mm", Locale.FRANCE).format(d)
} catch (_: Exception) { t.ifEmpty { "—" } }

/** Ecran du compte : connexion, postes PhilPDF, signatures et tampons a recuperer. Rien n'est recupere sans votre accord. */
@Composable
fun EcranCompte(fermer: () -> Unit, change: () -> Unit) {
    val ctx = LocalContext.current
    val portee = rememberCoroutineScope()
    var email by remember { mutableStateOf(Google.email(ctx)) }
    var connecte by remember { mutableStateOf(Google.connecte(ctx)) }
    var occupe by remember { mutableStateOf<String?>(null) }
    var erreur by remember { mutableStateOf<String?>(null) }
    var proposerNavigateur by remember { mutableStateOf<String?>(null) }
    var etat by remember { mutableStateOf<EtatDrive?>(null) }
    var locaux by remember { mutableStateOf(Bibliotheque.locaux(ctx)) }
    var version by remember { mutableIntStateOf(0) }
    val txtConnexion = stringResource(R.string.connexion_en_cours)
    val txtLecture = stringResource(R.string.lecture_drive)
    val txtNavigateur = stringResource(R.string.attente_navigateur)

    fun lireDrive() {
        portee.launch {
            occupe = txtLecture; erreur = null
            try {
                Google.profil(ctx); version++; change()
                etat = Bibliotheque.lireDrive(ctx)
            } catch (e: Exception) {
                erreur = e.message ?: e.javaClass.simpleName
            }
            occupe = null
        }
    }

    fun connecter(adresse: String) {
        portee.launch {
            occupe = txtConnexion; erreur = null
            try {
                if (Google.connecterTelephone(ctx, adresse)) {
                    email = adresse; connecte = true; change(); occupe = null; lireDrive()
                } else {
                    occupe = null; proposerNavigateur = adresse
                }
            } catch (e: Exception) {
                erreur = e.message; occupe = null
            }
        }
    }

    val choix = rememberLauncherForActivityResult(ActivityResultContracts.StartActivityForResult()) { r ->
        val n = r.data?.getStringExtra(AccountManager.KEY_ACCOUNT_NAME)
        if (r.resultCode == Activity.RESULT_OK && n != null) connecter(n)
    }

    LaunchedEffect(Unit) { if (connecte) lireDrive() }

    Dialog(onDismissRequest = fermer, properties = DialogProperties(usePlatformDefaultWidth = false)) {
        Surface(Modifier.fillMaxWidth(0.94f).widthIn(max = 560.dp).fillMaxHeight(0.92f), shape = RoundedCornerShape(16.dp)) {
            Column(Modifier.fillMaxSize().padding(16.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    PastilleCompte(version, 52.dp) {}
                    Spacer(Modifier.width(12.dp))
                    Column(Modifier.weight(1f)) {
                        if (connecte) {
                            Google.nom(ctx)?.takeIf { it.isNotBlank() }?.let {
                                Text(it, fontWeight = FontWeight.SemiBold, maxLines = 1, overflow = TextOverflow.Ellipsis)
                            }
                            Text(email ?: "", fontSize = 13.sp, color = Color.Gray, maxLines = 1, overflow = TextOverflow.Ellipsis)
                            Text(stringResource(if (Google.mode(ctx) == "telephone") R.string.mode_telephone else R.string.mode_navigateur),
                                fontSize = 11.sp, color = Color.Gray)
                        } else {
                            Text(stringResource(R.string.compte_google), fontWeight = FontWeight.SemiBold)
                        }
                    }
                }
                Spacer(Modifier.height(12.dp))
                Column(Modifier.weight(1f).verticalScroll(rememberScrollState())) {
                    if (!connecte) {
                        Text(stringResource(R.string.compte_explication), fontSize = 14.sp)
                        Spacer(Modifier.height(16.dp))
                        Button(onClick = { erreur = null; choix.launch(Google.intentChoisir()) }, enabled = occupe == null,
                            colors = ButtonDefaults.buttonColors(containerColor = ROUGE)) {
                            Text(stringResource(R.string.choisir_compte))
                        }
                        Spacer(Modifier.height(10.dp))
                        Text(stringResource(R.string.autres_comptes), fontSize = 12.sp, color = Color.Gray)
                    } else {
                        val e = etat
                        if (e != null && !e.trouve) {
                            Text(stringResource(R.string.philpdf_introuvable), fontSize = 14.sp, color = Color(0xFF9A5B00))
                        }
                        if (e != null && e.trouve) {
                            Text(stringResource(R.string.vos_postes), fontWeight = FontWeight.SemiBold)
                            Spacer(Modifier.height(6.dp))
                            if (e.postes.isEmpty()) Text("—", color = Color.Gray)
                            e.postes.forEach { p ->
                                Row(Modifier.fillMaxWidth().padding(vertical = 4.dp)
                                    .background(Color(0xFFF6F6F6), RoundedCornerShape(8.dp)).padding(10.dp)) {
                                    Column(Modifier.weight(1f)) {
                                        Text(p.nom, fontWeight = FontWeight.Medium, maxLines = 1, overflow = TextOverflow.Ellipsis)
                                        Text(stringResource(R.string.poste_activite, dateIso(p.activite)), fontSize = 12.sp, color = Color.Gray)
                                        Text(stringResource(R.string.poste_fichiers, p.fichiers) +
                                            if (p.reglagesPar) " · " + stringResource(R.string.poste_reglages) else "",
                                            fontSize = 12.sp, color = Color.Gray)
                                    }
                                }
                            }
                            Spacer(Modifier.height(16.dp))
                            Text(stringResource(R.string.biblio_titre), fontWeight = FontWeight.SemiBold)
                            Spacer(Modifier.height(4.dp))
                            val parGenre = e.distants.groupBy { it.genre }
                            Text(if (parGenre.isEmpty()) stringResource(R.string.biblio_drive_vide)
                                else parGenre.entries.joinToString(" · ") { "${it.value.size} ${Bibliotheque.nomGenre(it.key).lowercase()}" },
                                fontSize = 13.sp)
                            Text(stringResource(R.string.biblio_ici, locaux.size) +
                                (Bibliotheque.derniereRecuperation(ctx).takeIf { it > 0 }?.let {
                                    " · " + SimpleDateFormat("dd/MM/yyyy HH:mm", Locale.FRANCE).format(Date(it))
                                } ?: ""), fontSize = 12.sp, color = Color.Gray)
                            Spacer(Modifier.height(8.dp))
                            val aFaire = e.nouveaux + locaux.count { l -> e.distants.none { it.id == l.id } }
                            if (aFaire > 0) {
                                Button(onClick = {
                                    portee.launch {
                                        erreur = null
                                        try {
                                            val n = Bibliotheque.recuperer(ctx, e.distants) { i, t ->
                                                occupe = ctx.getString(R.string.recuperation, i, t)
                                            }
                                            locaux = Bibliotheque.locaux(ctx)
                                            etat = e.copy(nouveaux = 0)
                                            erreur = ctx.getString(R.string.recupere_n, n)
                                        } catch (ex: Exception) { erreur = ex.message }
                                        occupe = null
                                    }
                                }, enabled = occupe == null, colors = ButtonDefaults.buttonColors(containerColor = ROUGE)) {
                                    Text(stringResource(R.string.recuperer_n, aFaire))
                                }
                            } else if (e.distants.isNotEmpty()) {
                                Text(stringResource(R.string.biblio_a_jour), fontSize = 12.sp, color = Color(0xFF2E7D32))
                            }
                            Text(stringResource(R.string.biblio_usage), fontSize = 12.sp, color = Color.Gray)
                        }
                    }
                    occupe?.let {
                        Spacer(Modifier.height(12.dp))
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp)
                            Spacer(Modifier.width(10.dp))
                            Text(it, fontSize = 13.sp)
                        }
                    }
                    erreur?.let {
                        Spacer(Modifier.height(12.dp))
                        Text(it, fontSize = 13.sp, color = Color(0xFF9A5B00))
                    }
                }
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                    if (connecte) {
                        TextButton(onClick = { lireDrive() }, enabled = occupe == null) { Text(stringResource(R.string.actualiser)) }
                        TextButton(onClick = {
                            Google.deconnecter(ctx); connecte = false; email = null; etat = null; locaux = emptyList()
                            version++; change()
                        }, enabled = occupe == null) { Text(stringResource(R.string.deconnecter)) }
                    }
                    TextButton(onClick = fermer) { Text(stringResource(R.string.fermer)) }
                }
            }
        }
    }

    proposerNavigateur?.let { adresse ->
        AlertDialog(onDismissRequest = { proposerNavigateur = null },
            title = { Text(stringResource(R.string.compte_google)) },
            text = { Text(stringResource(R.string.navigateur_explication, adresse)) },
            confirmButton = {
                TextButton(onClick = {
                    proposerNavigateur = null
                    portee.launch {
                        occupe = txtNavigateur; erreur = null
                        try {
                            Google.connecterNavigateur(ctx, adresse)
                            email = adresse; connecte = true; change(); occupe = null; lireDrive()
                        } catch (ex: Exception) { erreur = ex.message; occupe = null }
                    }
                }) { Text(stringResource(R.string.continuer)) }
            },
            dismissButton = { TextButton(onClick = { proposerNavigateur = null }) { Text(stringResource(R.string.annuler)) } })
    }
}
