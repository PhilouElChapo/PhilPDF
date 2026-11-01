@file:OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class)

package io.github.philouelchapo.philpdf

import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/** Demande d'ouvrir un PDF depuis n'importe quel ecran (le PDF signe remplace celui qui etait ouvert). */
object Ouvrir {
    val demande = mutableStateOf<Uri?>(null)
}

/** Partie « Signature numerique » du volet Signer : vos certificats, importer, recuperer, signer, verifier. */
@Composable
fun SectionSignatureNumerique(etat: EtatLecteur, choisi: () -> Unit) {
    val ctx = LocalContext.current
    val portee = rememberCoroutineScope()
    var liste by remember { mutableStateOf(Identites.liste(ctx)) }
    var importer by remember { mutableStateOf<ByteArray?>(null) }
    var recuperer by remember { mutableStateOf(false) }
    var verifier by remember { mutableStateOf(false) }
    val choisirPfx = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { u: Uri? ->
        if (u != null) portee.launch {
            importer = withContext(Dispatchers.IO) { ctx.contentResolver.openInputStream(u)?.use { it.readBytes() } }
        }
    }
    Spacer(Modifier.height(16.dp))
    HorizontalDivider()
    Spacer(Modifier.height(10.dp))
    Text(stringResource(R.string.sig_num_titre), fontWeight = FontWeight.SemiBold)
    Text(stringResource(R.string.sig_num_aide), fontSize = 12.sp, color = Color.Gray)
    Spacer(Modifier.height(6.dp))
    liste.forEach { e ->
        val choisie = etat.signerAvec?.id == e.id
        Row(Modifier.fillMaxWidth().padding(vertical = 3.dp)
            .background(if (choisie) Color(0xFFFCEBEC) else Color.White, RoundedCornerShape(8.dp))
            .border(1.dp, if (choisie) ROUGE else Color(0xFFE2E2E2), RoundedCornerShape(8.dp))
            .clickable {
                etat.signerAvec = e
                etat.annot.outil = Outil.SIGNER_NUM
                choisi()
            }.padding(10.dp), verticalAlignment = Alignment.CenterVertically) {
            Icon(Icones.get("certificat", if (choisie) ROUGE else Color(0xFF444444)), null)
            Spacer(Modifier.width(10.dp))
            Column(Modifier.weight(1f)) {
                Text(e.nom.ifEmpty { e.email }, fontWeight = FontWeight.SemiBold, fontSize = 14.sp)
                Text(listOfNotNull(e.email.takeIf { it.isNotEmpty() && it != e.nom },
                    e.fin.takeIf { it.isNotEmpty() }?.let { ctx.getString(R.string.sig_valide_jusqu, it) },
                    if (e.autosigne) ctx.getString(R.string.sig_autosigne) else e.emetteur.takeIf { it.isNotEmpty() }).joinToString(" · "),
                    fontSize = 11.sp, color = Color.Gray)
            }
            IconButton(onClick = { Identites.retirer(ctx, e.id); liste = Identites.liste(ctx) }) {
                Icon(Icones.get("supprimer", Color(0xFF888888)), stringResource(R.string.supprimer))
            }
        }
    }
    if (liste.isEmpty()) Text(stringResource(R.string.sig_aucune), fontSize = 12.sp, color = Color.Gray)
    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        OutlinedButton(onClick = { choisirPfx.launch(arrayOf("application/x-pkcs12", "application/octet-stream", "*/*")) }) {
            Text(stringResource(R.string.sig_importer), fontSize = 13.sp)
        }
        OutlinedButton(onClick = { recuperer = true }, enabled = Nuage.synchro(ctx) != null) {
            Text(stringResource(R.string.sig_recuperer), fontSize = 13.sp)
        }
        OutlinedButton(onClick = { verifier = true }) { Text(stringResource(R.string.sig_verifier), fontSize = 13.sp) }
    }
    importer?.let { o -> DialogueImporterPfx(o, { importer = null }) { liste = Identites.liste(ctx) } }
    if (recuperer) DialogueRecuperer({ recuperer = false }) { liste = Identites.liste(ctx) }
    if (verifier) DialogueVerifier(etat) { verifier = false }
}

@Composable
private fun ChampMotDePasse(v: String, changer: (String) -> Unit, libelle: String) {
    OutlinedTextField(v, changer, label = { Text(libelle) }, singleLine = true, visualTransformation = PasswordVisualTransformation(),
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password), modifier = Modifier.fillMaxWidth())
}

@Composable
private fun DialogueImporterPfx(octets: ByteArray, fermer: () -> Unit, fait: () -> Unit) {
    val ctx = LocalContext.current
    var mdp by remember { mutableStateOf("") }
    var erreur by remember { mutableStateOf<String?>(null) }
    AlertDialog(onDismissRequest = fermer, title = { Text(stringResource(R.string.sig_importer)) },
        text = {
            Column {
                Text(stringResource(R.string.sig_importer_aide), fontSize = 13.sp)
                Spacer(Modifier.height(8.dp))
                ChampMotDePasse(mdp, { mdp = it }, stringResource(R.string.sig_mdp_certificat))
                erreur?.let { Text(it, color = ROUGE, fontSize = 13.sp) }
            }
        },
        confirmButton = {
            TextButton(onClick = {
                try { Identites.ajouter(ctx, octets, mdp); fait(); fermer() } catch (e: Exception) { erreur = e.message }
            }, enabled = mdp.isNotEmpty()) { Text(stringResource(R.string.ok)) }
        },
        dismissButton = { TextButton(onClick = fermer) { Text(stringResource(R.string.annuler)) } })
}

@Composable
private fun DialogueRecuperer(fermer: () -> Unit, fait: () -> Unit) {
    val ctx = LocalContext.current
    val portee = rememberCoroutineScope()
    var phrase by remember { mutableStateOf("") }
    var indice by remember { mutableStateOf<String?>(null) }
    var erreur by remember { mutableStateOf<String?>(null) }
    var occupe by remember { mutableStateOf(false) }
    LaunchedEffect(Unit) { indice = Identites.indice(ctx) }
    AlertDialog(onDismissRequest = { if (!occupe) fermer() }, title = { Text(stringResource(R.string.sig_recuperer)) },
        text = {
            Column {
                Text(stringResource(R.string.sig_recuperer_aide), fontSize = 13.sp)
                indice?.let { Text(stringResource(R.string.sig_indice, it), fontSize = 12.sp, color = Color.Gray) }
                Spacer(Modifier.height(8.dp))
                ChampMotDePasse(phrase, { phrase = it }, stringResource(R.string.sig_phrase))
                if (occupe) LinearProgressIndicator(Modifier.fillMaxWidth().padding(top = 8.dp))
                erreur?.let { Text(it, color = ROUGE, fontSize = 13.sp) }
            }
        },
        confirmButton = {
            TextButton(onClick = {
                occupe = true; erreur = null
                portee.launch {
                    try {
                        val n = Identites.recupererWindows(ctx, phrase)
                        fait()
                        android.widget.Toast.makeText(ctx, ctx.getString(R.string.sig_recuperees, n), android.widget.Toast.LENGTH_LONG).show()
                        fermer()
                    } catch (e: Exception) { erreur = e.message ?: e.toString() } finally { occupe = false }
                }
            }, enabled = phrase.isNotEmpty() && !occupe) { Text(stringResource(R.string.ok)) }
        },
        dismissButton = { TextButton(onClick = fermer, enabled = !occupe) { Text(stringResource(R.string.annuler)) } })
}

/** Apres le cadre trace : mot de passe du certificat, raison, lieu, image, puis enregistrer le PDF signe. */
@Composable
fun DialogueSigner(etat: EtatLecteur, page: Int, rect: com.artifex.mupdf.fitz.Rect, fermer: () -> Unit) {
    val ctx = LocalContext.current
    val portee = rememberCoroutineScope()
    val e = etat.signerAvec ?: return fermer()
    var mdp by remember { mutableStateOf("") }
    var raison by remember { mutableStateOf("") }
    var lieu by remember { mutableStateOf("") }
    val images = remember { Bibliotheque.locaux(ctx).filter { it.genre == "signatures" } }
    var avecImage by remember { mutableStateOf(images.isNotEmpty()) }
    var erreur by remember { mutableStateOf<String?>(null) }
    var occupe by remember { mutableStateOf(false) }
    var signe by remember { mutableStateOf<java.io.File?>(null) }
    val autreNom = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("application/pdf")) { u: Uri? ->
        val f = signe
        if (u != null && f != null) portee.launch {
            try { ecrireSigne(ctx, f, u); Ouvrir.demande.value = u; fermer() } catch (x: Exception) { erreur = x.message }
        }
    }
    AlertDialog(onDismissRequest = { if (!occupe) fermer() }, title = { Text(stringResource(R.string.sig_signer_titre)) },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState())) {
                Text(stringResource(R.string.sig_avec, e.nom.ifEmpty { e.email }), fontSize = 13.sp)
                Spacer(Modifier.height(6.dp))
                if (signe == null) {
                    ChampMotDePasse(mdp, { mdp = it }, stringResource(R.string.sig_mdp_certificat))
                    OutlinedTextField(raison, { raison = it }, label = { Text(stringResource(R.string.sig_raison)) }, singleLine = true, modifier = Modifier.fillMaxWidth())
                    OutlinedTextField(lieu, { lieu = it }, label = { Text(stringResource(R.string.sig_lieu)) }, singleLine = true, modifier = Modifier.fillMaxWidth())
                    if (images.isNotEmpty()) Row(verticalAlignment = Alignment.CenterVertically) {
                        Checkbox(avecImage, { avecImage = it })
                        Text(stringResource(R.string.sig_avec_image), fontSize = 13.sp)
                    }
                } else Text(stringResource(R.string.sig_ou_enregistrer), fontSize = 14.sp, fontWeight = FontWeight.SemiBold)
                if (occupe) LinearProgressIndicator(Modifier.fillMaxWidth().padding(top = 8.dp))
                erreur?.let { Text(it, color = ROUGE, fontSize = 13.sp, modifier = Modifier.padding(top = 6.dp)) }
            }
        },
        confirmButton = {
            if (signe == null) TextButton(onClick = {
                occupe = true; erreur = null
                portee.launch {
                    try {
                        val o = Identites.octets(ctx, e.id) ?: throw ErreurCertificat(ctx.getString(R.string.sig_illisible))
                        val (clef, chaine) = withContext(Dispatchers.IO) { Identites.ouvrir(o, mdp) }
                        // identite venue de Windows : infos completes une fois le mot de passe connu
                        if (e.empreinte.isEmpty()) try { Identites.ajouter(ctx, o, mdp, e.id) } catch (_: Exception) {}
                        val sig = Signataire(clef, chaine)
                        val img = if (avecImage) images.firstOrNull()?.let { Bibliotheque.apercu(ctx, it) }?.takeIf { it.exists() }?.readBytes() else null
                        signe = etat.doc.signerNumerique(ctx, page, rect, sig, raison, lieu, img)
                        Journal.ecrire("certificat", "${etat.doc.nom} : signé par ${e.nom}" + if (sig.horodatee) " (horodaté)" else "")
                    } catch (x: Exception) { erreur = x.message ?: x.toString() } finally { occupe = false }
                }
            }, enabled = mdp.isNotEmpty() && !occupe) { Text(stringResource(R.string.sig_signer)) }
            else Row {
                TextButton(onClick = {
                    val f = signe ?: return@TextButton
                    occupe = true
                    portee.launch {
                        try { ecrireSigne(ctx, f, etat.doc.uri); Ouvrir.demande.value = etat.doc.uri; fermer() }
                        catch (x: Exception) { erreur = ctx.getString(R.string.enregistrement_impossible) } finally { occupe = false }
                    }
                }, enabled = !occupe) { Text(stringResource(R.string.meme_fichier)) }
                TextButton(onClick = { autreNom.launch(etat.doc.nom.removeSuffix(".pdf") + " signé.pdf") }, enabled = !occupe) {
                    Text(stringResource(R.string.autre_nom))
                }
            }
        },
        dismissButton = { TextButton(onClick = fermer, enabled = !occupe) { Text(stringResource(R.string.annuler)) } })
}

/** Le fichier signe est copie tel quel (une reecriture casserait la signature), puis renvoye a son compte si besoin. */
private suspend fun ecrireSigne(ctx: android.content.Context, f: java.io.File, u: Uri) {
    withContext(Dispatchers.IO) {
        ctx.contentResolver.openOutputStream(u, "wt")?.use { s -> f.inputStream().use { it.copyTo(s) } }
            ?: throw IllegalStateException("écriture impossible")
    }
    try { Distants.renvoyer(ctx, u) } catch (_: Exception) {}
}

/** Signatures du PDF : intacte ou non, certificat approuve ou non, modifie apres la signature. */
@Composable
fun DialogueVerifier(etat: EtatLecteur, fermer: () -> Unit) {
    val ctx = LocalContext.current
    val l by produceState<List<InfoSignature>?>(null) { value = try { etat.doc.signatures(ctx) } catch (_: Exception) { emptyList() } }
    AlertDialog(onDismissRequest = fermer, title = { Text(stringResource(R.string.sig_verifier)) },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState())) {
                val x = l
                when {
                    x == null -> LinearProgressIndicator(Modifier.fillMaxWidth())
                    x.isEmpty() -> Text(stringResource(R.string.sig_aucune_pdf), color = Color.Gray)
                    else -> x.forEach { s ->
                        val (texte, coul) = etatSignature(ctx, s)
                        Column(Modifier.padding(vertical = 6.dp)) {
                            Text(s.nom + " · " + ctx.getString(R.string.page_n, s.page + 1), fontWeight = FontWeight.SemiBold)
                            Text(texte, color = coul, fontSize = 13.sp)
                        }
                    }
                }
            }
        },
        confirmButton = { TextButton(onClick = fermer) { Text(stringResource(R.string.fermer)) } })
}

fun etatSignature(ctx: android.content.Context, s: InfoSignature): Pair<String, Color> = when {
    !s.intacte -> ctx.getString(R.string.sig_cassee) to Color(0xFFC62828)
    s.modifieApres -> ctx.getString(R.string.sig_modifiee_apres) to Color(0xFF9A5B00)
    s.approuvee -> ctx.getString(R.string.sig_ok) to Color(0xFF2E7D32)
    s.autosignee -> ctx.getString(R.string.sig_ok_autosigne) to Color(0xFF9A5B00)
    else -> ctx.getString(R.string.sig_ok_inconnu) to Color(0xFF9A5B00)
}
