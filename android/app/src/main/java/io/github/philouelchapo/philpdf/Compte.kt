@file:OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class)

package io.github.philouelchapo.philpdf

import android.accounts.AccountManager
import android.app.Activity
import android.graphics.BitmapFactory
import android.content.Intent
import android.net.Uri
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
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

/** Couleur de pastille de chaque service (quand il n'y a pas de photo). */
fun couleurService(cle: String) = when (cle) {
    "gdrive" -> Color(0xFF1A73E8); "onedrive" -> Color(0xFF0364B8); "dropbox" -> Color(0xFF0061FE); "box" -> Color(0xFF0075C9); "pcloud" -> Color(0xFF17BED0); "kdrive" -> Color(0xFF0098FF); "webdav" -> Color(0xFF6A1B9A)
    else -> ROUGE
}

/** Photo du compte, sinon initiale sur la couleur du service ; silhouette grise si aucun compte. */
@Composable
fun AvatarCompte(n: Nuage?, version: Int, taille: Dp) {
    val ctx = LocalContext.current
    val photo = remember(n?.id, version) {
        (n?.image(ctx)?.takeIf { it.exists() } ?: n?.photo(ctx)?.takeIf { it.exists() })
            ?.let { BitmapFactory.decodeFile(it.absolutePath)?.asImageBitmap() }
    }
    Box(Modifier.size(taille).clip(CircleShape), contentAlignment = Alignment.Center) {
        when {
            n == null -> Icon(Icons.Filled.AccountCircle, null, Modifier.fillMaxSize(), tint = Color.Gray)
            photo != null -> Image(photo, null, Modifier.fillMaxSize().border(2.dp, couleurService(n.fournisseur(ctx).cle), CircleShape)
                .clip(CircleShape), contentScale = ContentScale.Crop)
            else -> Box(Modifier.fillMaxSize().background(couleurService(n.fournisseur(ctx).cle), CircleShape), contentAlignment = Alignment.Center) {
                Text((n.nom(ctx) ?: n.libelle(ctx)).take(1).uppercase(), color = Color.White, fontWeight = FontWeight.Bold,
                    fontSize = (taille.value * 0.42f).sp)
            }
        }
    }
}

/** Rond en haut a droite de l'Accueil : le compte de synchronisation (ou le premier compte relie). */
@Composable
fun PastilleCompte(version: Int, taille: Dp = 40.dp, onClick: () -> Unit) {
    val ctx = LocalContext.current
    val n = remember(version) { Nuage.synchro(ctx) ?: Nuage.liste(ctx).firstOrNull() }
    Box(Modifier.size(taille).clip(CircleShape).clickable(onClick = onClick)) { AvatarCompte(n, version, taille) }
}

/** Date ISO de PhilPDF Windows (2026-10-30T18:42:05) en clair. */
fun dateIso(t: String): String = try {
    val d = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss", Locale.FRANCE).parse(t.take(19))!!
    SimpleDateFormat(Textes.t(R.string.format_date_heure), Locale.FRANCE).format(d)
} catch (_: Exception) { t.ifEmpty { "—" } }

/**
 * Ecran des comptes : comptes relies (parcourir, choisir celui de la synchronisation, retirer), ajout d'un compte,
 * puis postes et bibliotheque du compte de synchronisation. Rien n'est recupere sans votre accord.
 */
@Composable
fun EcranComptes(fermer: () -> Unit, parcourir: (Nuage) -> Unit) {
    val ctx = LocalContext.current
    val portee = rememberCoroutineScope()
    var version by remember { mutableIntStateOf(0) }
    val comptes = remember(version) { Nuage.liste(ctx) }
    val synchro = remember(version) { Nuage.synchro(ctx) }
    var occupe by remember { mutableStateOf<String?>(null) }
    var erreur by remember { mutableStateOf<String?>(null) }
    var proposerNavigateur by remember { mutableStateOf<String?>(null) }
    var etat by remember { mutableStateOf<EtatDrive?>(null) }
    var locaux by remember { mutableStateOf(Bibliotheque.locaux(ctx)) }
    var aRetirer by remember { mutableStateOf<Nuage?>(null) }
    val txtLecture = stringResource(R.string.lecture_drive)
    val txtNavigateur = stringResource(R.string.attente_navigateur)
    val txtConnexion = stringResource(R.string.connexion_en_cours)

    fun lireSynchro() {
        val s = Nuage.synchro(ctx) ?: run { etat = null; return }
        portee.launch {
            occupe = txtLecture; erreur = null
            try {
                s.profil(ctx); version++
                etat = Bibliotheque.lireDrive(ctx)
            } catch (e: Exception) { erreur = e.message ?: e.javaClass.simpleName }
            occupe = null
        }
    }

    var changer by remember { mutableStateOf(false) }

    // plusieurs comptes relies (comme sous Windows) : un pour la synchronisation des reglages, d'autres pour envoyer,
    // ouvrir, classer ; ajouter un compte ne retire jamais les autres
    var ajoutAutre by remember { mutableStateOf(false) }
    var davCle by remember { mutableStateOf<String?>(null) }      // compte par WebDAV en cours d'ajout
    var imagePour by remember { mutableStateOf<Nuage?>(null) }    // compte dont on change l'image
    val choisirImage = rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { uri ->
        val c = imagePour ?: return@rememberLauncherForActivityResult
        imagePour = null
        if (uri != null) portee.launch {
            val ok = kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.IO) {
                try {
                    val src = ctx.contentResolver.openInputStream(uri)?.use { BitmapFactory.decodeStream(it) } ?: return@withContext false
                    val cote = minOf(src.width, src.height)       // carre centre, 256 px
                    val carre = android.graphics.Bitmap.createBitmap(src, (src.width - cote) / 2, (src.height - cote) / 2, cote, cote)
                    val petit = android.graphics.Bitmap.createScaledBitmap(carre, 256, 256, true)
                    c.image(ctx).parentFile?.mkdirs()
                    c.image(ctx).outputStream().use { petit.compress(android.graphics.Bitmap.CompressFormat.PNG, 100, it) }
                    true
                } catch (e: Exception) { Journal.ecrire("compte", "image du compte : ${e.message}"); false }
            }
            if (!ok) erreur = ctx.getString(R.string.image_illisible)
            version++
        }
    }
    var menuImage by remember { mutableStateOf<Nuage?>(null) }
    fun apresConnexion(n: Nuage) {
        val commeSynchro = !ajoutAutre
        ajoutAutre = false
        portee.launch {
            try { n.profil(ctx) } catch (_: Exception) {}
            if (commeSynchro) Nuage.choisirSynchro(ctx, n)
            changer = false
            locaux = Bibliotheque.locaux(ctx)
            version++
            occupe = null
            lireSynchro()
        }
    }

    fun parNavigateur(f: Fournisseur, indice: String?) {
        portee.launch {
            occupe = txtNavigateur; erreur = null
            val n = Nuage.nouveau()
            try {
                n.connecterNavigateur(ctx, f, indice) { occupe = it }
                apresConnexion(n)
            } catch (ex: Exception) { erreur = ex.message; occupe = null }
        }
    }

    val choixGoogle = rememberLauncherForActivityResult(ActivityResultContracts.StartActivityForResult()) { r ->
        val adresse = r.data?.getStringExtra(AccountManager.KEY_ACCOUNT_NAME)
        if (r.resultCode == Activity.RESULT_OK && adresse != null) portee.launch {
            occupe = txtConnexion; erreur = null
            val n = Nuage.nouveau()
            try {
                if (n.connecterTelephone(ctx, adresse)) apresConnexion(n) else { occupe = null; proposerNavigateur = adresse }
            } catch (e: Exception) { erreur = e.message; occupe = null }
        }
    }

    LaunchedEffect(Unit) { if (synchro != null) lireSynchro() }

    Fenetre(fermer) {
        Surface(Modifier.fillMaxWidth(0.94f).widthIn(max = 560.dp).fillMaxHeight(0.92f), shape = RoundedCornerShape(16.dp)) {
            Column(Modifier.fillMaxSize().padding(16.dp)) {
                Text(stringResource(R.string.synchro_titre_ecran), fontWeight = FontWeight.SemiBold, fontSize = 20.sp)
                Spacer(Modifier.height(10.dp))
                Column(Modifier.weight(1f).verticalScroll(rememberScrollState())) {
                    // ---------------------------------------------------- emplacement de synchronisation
                    Text(stringResource(R.string.synchro_explication), fontSize = 14.sp)
                    Spacer(Modifier.height(8.dp))
                    synchro?.let { n ->
                        Row(Modifier.fillMaxWidth().background(Color(0xFFF6F6F6), RoundedCornerShape(10.dp)).padding(10.dp),
                            verticalAlignment = Alignment.CenterVertically) {
                            AvatarCompte(n, version, 40.dp)
                            Spacer(Modifier.width(10.dp))
                            Column(Modifier.weight(1f)) {
                                Text(n.libelle(ctx), fontWeight = FontWeight.Medium, maxLines = 1, overflow = TextOverflow.Ellipsis)
                                Text(n.fournisseur(ctx).nom, fontSize = 12.sp, color = Color(0xFF2E7D32), maxLines = 1)
                            }
                        }
                        FlowRow(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                            TextButton(onClick = { changer = !changer }, enabled = occupe == null) { Text(stringResource(R.string.changer_emplacement)) }
                            TextButton(onClick = { aRetirer = n }, enabled = occupe == null) { Text(stringResource(R.string.deconnecter), color = Color.Gray) }
                        }
                    }
                    if (synchro == null || changer) {
                        Spacer(Modifier.height(6.dp))
                        Text(stringResource(R.string.ou_synchro), fontWeight = FontWeight.SemiBold)
                        Spacer(Modifier.height(6.dp))
                        Button(onClick = { erreur = null; choixGoogle.launch(Nuage.intentChoisirGoogle()) }, enabled = occupe == null,
                            modifier = Modifier.fillMaxWidth(), colors = ButtonDefaults.buttonColors(containerColor = ROUGE)) {
                            Text(stringResource(R.string.choisir_compte), maxLines = 2, overflow = TextOverflow.Ellipsis)
                        }
                        FOURNISSEURS.drop(1).forEach { f ->
                            OutlinedButton(onClick = { if (parDav(f)) davCle = f.cle else parNavigateur(f, null) },
                                enabled = occupe == null && (Nuage.disponible(f) || parDav(f)),
                                modifier = Modifier.fillMaxWidth().padding(vertical = 2.dp)) {
                                Text(if (Nuage.disponible(f) || parDav(f)) f.nom else f.nom + " — " + stringResource(R.string.non_disponible),
                                    maxLines = 2, overflow = TextOverflow.Ellipsis)
                            }
                        }
                        Text(stringResource(R.string.navigateur_aide), fontSize = 12.sp, color = Color.Gray)
                        Spacer(Modifier.height(4.dp))
                        Text(stringResource(R.string.nas_bientot), fontSize = 12.sp, color = Color.Gray)
                    }
                    // ---------------------------------------------------- autres comptes (envoyer, ouvrir, classer)
                    if (synchro != null) {
                        Spacer(Modifier.height(14.dp))
                        Text(stringResource(R.string.autres_comptes), fontWeight = FontWeight.SemiBold)
                        Text(stringResource(R.string.autres_comptes_aide), fontSize = 12.sp, color = Color.Gray)
                        comptes.forEach { c ->
                            val pref = Nuage.estPrefere(ctx, c)
                            Row(Modifier.fillMaxWidth().padding(vertical = 3.dp).background(Color(0xFFF6F6F6), RoundedCornerShape(10.dp))
                                .padding(8.dp), verticalAlignment = Alignment.CenterVertically) {
                                Box(Modifier.size(32.dp).clip(CircleShape).clickable { menuImage = c }) { AvatarCompte(c, version, 32.dp) }
                                Spacer(Modifier.width(8.dp))
                                Column(Modifier.weight(1f)) {
                                    Text(c.libelle(ctx), maxLines = 1, overflow = TextOverflow.Ellipsis)
                                    Text(c.fournisseur(ctx).nom + (if (c.id == synchro.id) " · " + stringResource(R.string.compte_synchro) else "") +
                                        (if (pref) " · ★ " + stringResource(R.string.compte_prefere) else ""), fontSize = 12.sp, color = Color.Gray)
                                }
                                TextButton(onClick = { Nuage.choisirPrefere(ctx, if (pref) null else c); version++ }, enabled = occupe == null) {
                                    Text(if (pref) "★" else "☆", fontSize = 20.sp, color = if (pref) Color(0xFFE0A100) else Color.Gray)
                                }
                                if (c.id != synchro.id) TextButton(onClick = { aRetirer = c }, enabled = occupe == null) {
                                    Text(stringResource(R.string.deconnecter), color = Color.Gray, fontSize = 13.sp)
                                }
                            }
                        }
                        Text(stringResource(R.string.prefere_aide), fontSize = 12.sp, color = Color.Gray)
                        TextButton(onClick = { ajoutAutre = !ajoutAutre }, enabled = occupe == null) { Text(stringResource(R.string.ajouter_compte)) }
                        if (ajoutAutre) {
                            FOURNISSEURS.drop(1).forEach { f ->
                                OutlinedButton(onClick = { if (parDav(f)) davCle = f.cle else parNavigateur(f, null) },
                                enabled = occupe == null && (Nuage.disponible(f) || parDav(f)),
                                    modifier = Modifier.fillMaxWidth().padding(vertical = 2.dp)) {
                                    Text(if (Nuage.disponible(f) || parDav(f)) f.nom else f.nom + " — " + stringResource(R.string.non_disponible),
                                        maxLines = 2, overflow = TextOverflow.Ellipsis)
                                }
                            }
                        }
                    }
                    Spacer(Modifier.height(8.dp))
                    Text(stringResource(R.string.ouvrir_partout), fontSize = 12.sp, color = Color.Gray)

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

                    // ---------------------------------------------------- synchronisation avec vos postes
                    if (synchro != null) {
                        Spacer(Modifier.height(18.dp))
                        HorizontalDivider()
                        Spacer(Modifier.height(10.dp))

                        val e = etat
                        if (e != null && !e.trouve) {
                            Text(stringResource(R.string.philpdf_introuvable), fontSize = 14.sp, color = Color(0xFF9A5B00))
                        }
                        if (e != null && e.trouve) {
                            Text(stringResource(R.string.vos_postes), fontWeight = FontWeight.Medium)
                            if (e.postes.isEmpty()) Text("—", color = Color.Gray)
                            e.postes.forEach { p ->
                                Column(Modifier.fillMaxWidth().padding(vertical = 3.dp).background(Color(0xFFF6F6F6), RoundedCornerShape(8.dp)).padding(10.dp)) {
                                    Text(p.nom, fontWeight = FontWeight.Medium, maxLines = 1, overflow = TextOverflow.Ellipsis)
                                    Text(stringResource(R.string.poste_activite, dateIso(p.activite)), fontSize = 12.sp, color = Color.Gray)
                                    Text(stringResource(R.string.poste_fichiers, p.fichiers) +
                                        if (p.reglagesPar) " · " + stringResource(R.string.poste_reglages) else "", fontSize = 12.sp, color = Color.Gray)
                                }
                            }
                            Spacer(Modifier.height(12.dp))
                            Text(stringResource(R.string.biblio_titre), fontWeight = FontWeight.Medium)
                            val parGenre = e.distants.groupBy { it.genre }
                            Text(if (parGenre.isEmpty()) stringResource(R.string.biblio_drive_vide)
                                else parGenre.entries.joinToString(" · ") { "${it.value.size} ${Bibliotheque.nomGenre(it.key).lowercase()}" },
                                fontSize = 13.sp)
                            Text(stringResource(R.string.biblio_ici, locaux.size) +
                                (Bibliotheque.derniereRecuperation(ctx).takeIf { it > 0 }?.let {
                                    " · " + SimpleDateFormat("dd/MM/yyyy HH:mm", Locale.FRANCE).format(Date(it))
                                } ?: ""), fontSize = 12.sp, color = Color.Gray)
                            Spacer(Modifier.height(6.dp))
                            val aFaire = e.nouveaux + locaux.count { l -> e.distants.none { it.id == l.id } }
                            if (aFaire > 0) {
                                Button(onClick = {
                                    portee.launch {
                                        erreur = null
                                        try {
                                            val n = Bibliotheque.recuperer(ctx, e.distants) { i, t -> occupe = ctx.getString(R.string.recuperation, i, t) }
                                            locaux = Bibliotheque.locaux(ctx)
                                            etat = e.copy(nouveaux = 0)
                                            erreur = ctx.getString(R.string.recupere_n, n)
                                        } catch (ex: Exception) { erreur = ex.message }
                                        occupe = null
                                    }
                                }, enabled = occupe == null, colors = ButtonDefaults.buttonColors(containerColor = ROUGE)) {
                                    Text(stringResource(R.string.recuperer_n, aFaire), maxLines = 2)
                                }
                            } else if (e.distants.isNotEmpty()) {
                                Text(stringResource(R.string.biblio_a_jour), fontSize = 12.sp, color = Color(0xFF2E7D32))
                            }
                            Text(stringResource(R.string.biblio_usage), fontSize = 12.sp, color = Color.Gray)
                        }
                        TextButton(onClick = { lireSynchro() }, enabled = occupe == null) { Text(stringResource(R.string.actualiser)) }
                    }
                    SectionMiseAJour()
                }
                FlowRow(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(4.dp, Alignment.End)) {   // passe a la ligne, jamais coupe
                    TextButton(onClick = fermer) { Text(stringResource(R.string.fermer)) }
                }
            }
        }
    }

    aRetirer?.let { n ->
        AlertDialog(onDismissRequest = { aRetirer = null },
            text = { Text(stringResource(R.string.retirer_question, n.libelle(ctx), n.fournisseur(ctx).nom)) },
            confirmButton = {
                TextButton(onClick = {
                    Nuage.retirer(ctx, n); aRetirer = null; version++; etat = null; locaux = Bibliotheque.locaux(ctx); lireSynchro()
                }) { Text(stringResource(R.string.deconnecter)) }
            },
            dismissButton = { TextButton(onClick = { aRetirer = null }) { Text(stringResource(R.string.annuler)) } })
    }

    menuImage?.let { c ->
        AlertDialog(onDismissRequest = { menuImage = null }, title = { Text(stringResource(R.string.image_compte)) },
            text = {
                Column {
                    Text(stringResource(R.string.image_compte_aide))
                    if ((c.email(ctx) ?: "").contains("@")) OutlinedButton(onClick = {
                        menuImage = null
                        portee.launch { if (!c.gravatar(ctx)) erreur = ctx.getString(R.string.gravatar_absent, c.email(ctx) ?: ""); version++ }
                    }, Modifier.padding(top = 8.dp)) { Text(stringResource(R.string.gravatar)) }
                }
            },
            confirmButton = { TextButton(onClick = { imagePour = c; menuImage = null; choisirImage.launch("image/*") }) {
                Text(stringResource(R.string.image_choisir)) } },
            dismissButton = {
                Row {
                    if (c.image(ctx).exists()) TextButton(onClick = { c.image(ctx).delete(); menuImage = null; version++ }) {
                        Text(stringResource(R.string.image_par_defaut)) }
                    TextButton(onClick = { menuImage = null }) { Text(stringResource(R.string.annuler)) }
                }
            })
    }

    davCle?.let { cle ->
        var adresse by remember(cle) { mutableStateOf("") }
        var email by remember(cle) { mutableStateOf("") }
        var mdp by remember(cle) { mutableStateOf("") }
        var voir by remember { mutableStateOf(false) }
        val nom = FOURNISSEURS.first { it.cle == cle }.nom
        val pret = mdp.isNotEmpty() && email.isNotBlank() && (cle == "pcloud" || adresse.isNotBlank())
        AlertDialog(onDismissRequest = { davCle = null }, title = { Text(nom) },
            text = {
                Column(Modifier.verticalScroll(rememberScrollState())) {
                    Text(stringResource(when (cle) { "pcloud" -> R.string.pcloud_dav_aide; "kdrive" -> R.string.kdrive_aide
                        else -> R.string.webdav_aide }), fontSize = 13.sp, color = Color.Gray)
                    Spacer(Modifier.height(8.dp))
                    if (cle != "pcloud") OutlinedTextField(adresse, { adresse = it.trim() }, Modifier.fillMaxWidth(), singleLine = true,
                        label = { Text(stringResource(if (cle == "kdrive") R.string.kdrive_numero else R.string.webdav_adresse)) },
                        placeholder = { Text(if (cle == "kdrive") "123456" else "https://monnas.exemple.org:5006") },
                        keyboardOptions = androidx.compose.foundation.text.KeyboardOptions(keyboardType =
                            if (cle == "kdrive") androidx.compose.ui.text.input.KeyboardType.Number else androidx.compose.ui.text.input.KeyboardType.Uri))
                    OutlinedTextField(email, { email = it }, Modifier.fillMaxWidth(), singleLine = true,
                        label = { Text(stringResource(if (cle == "webdav") R.string.webdav_utilisateur else R.string.pcloud_email)) },
                        keyboardOptions = androidx.compose.foundation.text.KeyboardOptions(keyboardType = androidx.compose.ui.text.input.KeyboardType.Email))
                    OutlinedTextField(mdp, { mdp = it }, Modifier.fillMaxWidth(), singleLine = true,
                        label = { Text(stringResource(R.string.pcloud_mdp)) },
                        visualTransformation = if (voir) androidx.compose.ui.text.input.VisualTransformation.None
                            else androidx.compose.ui.text.input.PasswordVisualTransformation(),
                        trailingIcon = { IconButton(onClick = { voir = !voir }) {
                            Icon(Icones.get(if (voir) "oeil_barre" else "oeil"), stringResource(R.string.pcloud_mdp)) } })
                }
            },
            confirmButton = {
                TextButton(onClick = {
                    davCle = null
                    portee.launch {
                        occupe = txtConnexion; erreur = null
                        val n = Nuage.nouveau()
                        try {
                            if (cle == "pcloud") n.connecterPcloudDav(ctx, email, mdp) else n.connecterDav(ctx, cle, adresse, email, mdp)
                            apresConnexion(n)
                        } catch (e: Exception) { erreur = e.message; occupe = null }
                    }
                }, enabled = pret) { Text(stringResource(R.string.continuer)) }
            },
            dismissButton = { TextButton(onClick = { davCle = null }) { Text(stringResource(R.string.annuler)) } })
    }

    proposerNavigateur?.let { adresse ->
        AlertDialog(onDismissRequest = { proposerNavigateur = null },
            title = { Text(stringResource(R.string.compte_google)) },
            text = { Text(stringResource(R.string.navigateur_explication, adresse)) },
            confirmButton = {
                TextButton(onClick = { proposerNavigateur = null; parNavigateur(FOURNISSEURS[0], adresse) }) {
                    Text(stringResource(R.string.continuer))
                }
            },
            dismissButton = { TextButton(onClick = { proposerNavigateur = null }) { Text(stringResource(R.string.annuler)) } })
    }
}

/** Comptes relies que PhilPDF sait parcourir lui-meme (Google Drive passe par le selecteur d'Android), prefere en tete. */
fun comptesParcourables(ctx: android.content.Context): List<Nuage> =
    Nuage.liste(ctx).filter { it.connecte(ctx) && it.parcourable(ctx) }.sortedBy { if (Nuage.estPrefere(ctx, it)) 0 else 1 }

/** Parcourir les dossiers d'un compte et ouvrir un PDF ; ou, avec enregistrer, choisir le dossier et le nom du PDF
 *  a y enregistrer (un fichier du meme nom n'est jamais remplace : « (2) » est ajoute). */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun EcranFichiers(depart: Nuage, fermer: () -> Unit, ouvrir: (Uri) -> Unit,
                  enregistrer: ((compte: Nuage, dossier: String, nom: String) -> Unit)? = null, nomDefaut: String = "") {
    var nomFichier by remember { mutableStateOf(nomDefaut) }
    val ctx = LocalContext.current
    val portee = rememberCoroutineScope()
    // compte affiche (le prefere au depart) ; un appui sur son nom en haut passe a un autre compte relie
    var n by remember { mutableStateOf(depart) }
    val autresComptes = remember { comptesParcourables(ctx) }
    var menuComptes by remember { mutableStateOf(false) }
    var chemin by remember { mutableStateOf(listOf(n.racineParcours(ctx) to n.fournisseur(ctx).nom)) }
    var entrees by remember { mutableStateOf<List<Entree>?>(null) }
    var erreur by remember { mutableStateOf<String?>(null) }
    var occupe by remember { mutableStateOf<String?>(null) }
    val txtTelechargement = stringResource(R.string.telechargement)

    LaunchedEffect(n, chemin) {
        entrees = null; erreur = null
        try { entrees = n.lister(ctx, chemin.last().first) } catch (e: Exception) { erreur = e.message ?: e.javaClass.simpleName }
    }
    fun remonter() { if (chemin.size > 1) chemin = chemin.dropLast(1) else fermer() }

    Fenetre(fermer) {
        BackHandler { remonter() }
        Surface(Modifier.fillMaxWidth(0.96f).widthIn(max = 640.dp).fillMaxHeight(0.94f), shape = RoundedCornerShape(16.dp)) {
            Column(Modifier.fillMaxSize().padding(vertical = 10.dp)) {
                Row(Modifier.padding(horizontal = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                    IconButton(onClick = { remonter() }) { Icon(Icons.AutoMirrored.Filled.ArrowBack, stringResource(R.string.retour)) }
                    Row(Modifier.weight(1f).clickable(enabled = autresComptes.size > 1 && occupe == null) { menuComptes = true },
                        verticalAlignment = Alignment.CenterVertically) {
                        AvatarCompte(n, 0, 28.dp)
                        Spacer(Modifier.width(8.dp))
                        Column(Modifier.weight(1f)) {
                            Text(chemin.last().second, fontWeight = FontWeight.SemiBold, maxLines = 1, overflow = TextOverflow.Ellipsis)
                            Text(n.libelle(ctx), fontSize = 12.sp, color = Color.Gray, maxLines = 1, overflow = TextOverflow.Ellipsis)
                        }
                        if (autresComptes.size > 1) Box {
                            Text(stringResource(R.string.changer_compte) + " ▾", fontSize = 12.sp, color = ROUGE, modifier = Modifier.padding(horizontal = 8.dp))
                            DropdownMenu(menuComptes, { menuComptes = false }) {
                                autresComptes.forEach { c ->
                                    DropdownMenuItem(leadingIcon = { AvatarCompte(c, 0, 24.dp) },
                                        text = { Column {
                                            Text(c.fournisseur(ctx).nom + if (Nuage.estPrefere(ctx, c)) "  ★" else "", fontWeight = FontWeight.SemiBold)
                                            Text(c.libelle(ctx), fontSize = 12.sp, color = Color.Gray)
                                        } },
                                        onClick = {
                                            menuComptes = false
                                            if (c.id != n.id) { n = c; chemin = listOf(c.racineParcours(ctx) to c.fournisseur(ctx).nom) }
                                        })
                                }
                            }
                        }
                    }
                }
                HorizontalDivider()
                Box(Modifier.weight(1f).fillMaxWidth()) {
                    val l = entrees
                    when {
                        erreur != null -> Text(erreur!!, Modifier.padding(16.dp), color = Color(0xFF9A5B00))
                        l == null -> CircularProgressIndicator(Modifier.align(Alignment.Center))
                        l.isEmpty() -> Text(stringResource(R.string.dossier_vide), Modifier.padding(16.dp), color = Color.Gray)
                        else -> LazyColumn {
                            items(l, key = { it.id }) { e ->
                                Row(Modifier.fillMaxWidth().clickable(enabled = occupe == null && (e.dossier || enregistrer == null)) {
                                    if (e.dossier) chemin = chemin + (e.id to e.nom)
                                    else portee.launch {
                                        occupe = txtTelechargement
                                        try { val u = n.ouvrirFichier(ctx, e); fermer(); ouvrir(u) }
                                        catch (ex: Exception) { erreur = ex.message }
                                        occupe = null
                                    }
                                }.padding(horizontal = 16.dp, vertical = 10.dp), verticalAlignment = Alignment.CenterVertically) {
                                    Icon(Icones.get(if (e.dossier) "ouvrir" else "creer", if (e.dossier) Color(0xFFE0A100) else ROUGE), null, Modifier.size(26.dp), tint = Color.Unspecified)
                                    Spacer(Modifier.width(12.dp))
                                    Column(Modifier.weight(1f)) {
                                        Text(e.nom, maxLines = 2, overflow = TextOverflow.Ellipsis)
                                        if (!e.dossier) Text(taille(e.taille) + (dateIso(e.date).takeIf { e.date.isNotEmpty() }?.let { " · $it" } ?: ""),
                                            fontSize = 12.sp, color = Color.Gray, maxLines = 1, overflow = TextOverflow.Ellipsis)
                                    }
                                }
                                HorizontalDivider(color = Color(0xFFEEEEEE))
                            }
                        }
                    }
                    occupe?.let {
                        Row(Modifier.align(Alignment.BottomCenter).padding(12.dp).background(Color(0xEE333333), RoundedCornerShape(20.dp))
                            .padding(horizontal = 16.dp, vertical = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                            CircularProgressIndicator(Modifier.size(18.dp), color = Color.White, strokeWidth = 2.dp)
                            Spacer(Modifier.width(10.dp))
                            Text(it, color = Color.White, fontSize = 13.sp)
                        }
                    }
                }
                if (enregistrer != null) {
                    HorizontalDivider()
                    Column(Modifier.padding(horizontal = 16.dp, vertical = 8.dp)) {
                        OutlinedTextField(nomFichier, { nomFichier = it }, Modifier.fillMaxWidth(), singleLine = true,
                            label = { Text(stringResource(R.string.empl_nom)) })
                        FlowRow(Modifier.fillMaxWidth().padding(top = 6.dp), horizontalArrangement = Arrangement.spacedBy(4.dp, Alignment.End)) {
                            TextButton(onClick = fermer) { Text(stringResource(R.string.annuler)) }
                            Button(onClick = {
                                val nom = nomFichier.trim().let { if (it.lowercase().endsWith(".pdf")) it else "$it.pdf" }
                                val dossier = "/" + chemin.drop(1).joinToString("/") { it.second }
                                fermer(); enregistrer(n, dossier, nom)
                            }, enabled = nomFichier.isNotBlank(), colors = ButtonDefaults.buttonColors(containerColor = ROUGE)) {
                                Text(stringResource(R.string.empl_enregistrer_ici)) }
                        }
                    }
                } else
                Text(stringResource(R.string.fichiers_aide), Modifier.padding(horizontal = 16.dp, vertical = 6.dp), fontSize = 11.sp, color = Color.Gray)
            }
        }
    }
}

fun taille(o: Long): String = when {
    o >= 1_000_000 -> String.format(Locale.FRANCE, "%.1f Mo", o / 1_000_000.0)
    o >= 1_000 -> "${o / 1_000} Ko"
    else -> "$o o"
}

/** Version installee et recherche d'une mise a jour a la demande (sans attendre le prochain demarrage). */
@Composable
private fun SectionMiseAJour() {
    val ctx = LocalContext.current
    val portee = rememberCoroutineScope()
    var cherche by remember { mutableStateOf(false) }
    var resultat by remember { mutableStateOf<String?>(null) }
    var trouvee by remember { mutableStateOf<NouvelleVersion?>(null) }
    Spacer(Modifier.height(16.dp))
    HorizontalDivider()
    Spacer(Modifier.height(8.dp))
    Text(stringResource(R.string.maj_titre), fontWeight = FontWeight.SemiBold)
    Text(stringResource(R.string.maj_installee, BuildConfig.VERSION_NAME), fontSize = 13.sp, color = Color.Gray)
    if (BuildConfig.PLAY_STORE) {
        Text(stringResource(R.string.maj_play), fontSize = 12.sp, color = Color.Gray)
        TextButton(onClick = {
            ctx.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("market://details?id=" + ctx.packageName)))
        }) { Text(stringResource(R.string.maj_ouvrir_play)) }
        return
    }
    Row(verticalAlignment = Alignment.CenterVertically) {
        OutlinedButton(onClick = {
            cherche = true; resultat = null; trouvee = null
            portee.launch {
                Journal.ecrire("mise à jour", "recherche demandée depuis l'écran des comptes")
                val v = MiseAJour.chercher(BuildConfig.VERSION_NAME)
                trouvee = v
                resultat = if (v == null) ctx.getString(R.string.maj_a_jour) else null
                cherche = false
            }
        }, enabled = !cherche) { Text(stringResource(R.string.maj_rechercher)) }
        if (cherche) { Spacer(Modifier.width(10.dp)); CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp) }
    }
    resultat?.let { Text(it, fontSize = 13.sp, color = Color(0xFF2E7D32)) }
    trouvee?.let { v ->
        Text(stringResource(R.string.maj_dispo, v.version, BuildConfig.VERSION_NAME), fontSize = 13.sp)
        TextButton(onClick = {
            Journal.ecrire("mise à jour", "${v.version} : téléchargement demandé (${v.lien})")
            ctx.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(v.lien)))
        }) { Text(stringResource(R.string.telecharger)) }
    }
}
