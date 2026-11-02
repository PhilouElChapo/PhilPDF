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
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.widthIn
import androidx.compose.material3.Surface
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
    var creer by remember { mutableStateOf(false) }
    var ranger by remember { mutableStateOf(false) }
    // certificats de vos postes : ceux qui ne sont pas encore ici (et pourquoi), synchronisation automatique
    var distantes by remember { mutableStateOf<List<org.json.JSONObject>>(emptyList()) }
    LaunchedEffect(Unit) {
        if (Identites.synchroAuto(ctx) > 0) liste = Identites.liste(ctx)
        distantes = Identites.distantes(ctx)
        if (Identites.nettoyer(ctx, distantes)) liste = Identites.liste(ctx)
    }
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
            Icon(Icones.get("certificat", if (choisie) ROUGE else Color(0xFF444444)), null, tint = Color.Unspecified)
            Spacer(Modifier.width(10.dp))
            Column(Modifier.weight(1f)) {
                Text(e.nom.ifEmpty { e.email }, fontWeight = FontWeight.SemiBold, fontSize = 14.sp)
                Text(listOfNotNull(e.email.takeIf { it.isNotEmpty() && it != e.nom },
                    e.fin.takeIf { it.isNotEmpty() }?.let { ctx.getString(R.string.sig_valide_jusqu, it) },
                    if (e.autosigne) ctx.getString(R.string.sig_autosigne) else e.emetteur.takeIf { it.isNotEmpty() }).joinToString(" · "),
                    fontSize = 11.sp, color = Color.Gray)
            }
            if (ranger) {
                val i = liste.indexOf(e)
                TextButton(onClick = { Identites.deplacer(ctx, e.id, -1); liste = Identites.liste(ctx) }, enabled = i > 0,
                    contentPadding = PaddingValues(4.dp)) { Text("↑") }
                TextButton(onClick = { Identites.deplacer(ctx, e.id, 1); liste = Identites.liste(ctx) }, enabled = i < liste.size - 1,
                    contentPadding = PaddingValues(4.dp)) { Text("↓") }
                IconButton(onClick = { Identites.retirer(ctx, e.id); liste = Identites.liste(ctx) }) {
                    Icon(Icones.get("supprimer", Color(0xFF888888)), stringResource(R.string.supprimer), tint = Color.Unspecified)
                }
            }
        }
    }
    val ici = liste.map { it.id }.toSet() + liste.map { it.empreinte }.filter { it.isNotEmpty() }
    val retirees = Identites.retirees(ctx)
    val absentes = distantes.filter { it.optString("id") !in ici && it.optString("id") !in retirees && it.optString("empreinte").uppercase() !in ici }
    absentes.forEach { d ->
        val windows = d.optBoolean("windows")
        Row(Modifier.fillMaxWidth().padding(vertical = 3.dp).background(Color(0xFFF5F5F5), RoundedCornerShape(8.dp))
            .clickable(enabled = !windows) { recuperer = true }.padding(10.dp), verticalAlignment = Alignment.CenterVertically) {
            Icon(Icones.get("certificat", Color(0xFFAAAAAA)), null, tint = Color.Unspecified)
            Spacer(Modifier.width(10.dp))
            Column(Modifier.weight(1f)) {
                Text(d.optString("nom").ifEmpty { d.optString("email") }, fontSize = 14.sp, color = Color.Gray)
                Text(stringResource(if (windows) R.string.sig_magasin_windows else R.string.sig_a_recuperer), fontSize = 11.sp,
                    color = if (windows) Color(0xFF9A5B00) else Color(0xFF0F6CBD))
            }
        }
    }
    if (liste.isEmpty() && absentes.isEmpty()) Text(stringResource(R.string.sig_aucune), fontSize = 12.sp, color = Color.Gray)
    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        OutlinedButton(onClick = { creer = true }) { Text(stringResource(R.string.sig_creer), fontSize = 13.sp) }
        OutlinedButton(onClick = { choisirPfx.launch(arrayOf("application/x-pkcs12", "application/octet-stream", "*/*")) }) {
            Text(stringResource(R.string.sig_importer), fontSize = 13.sp)
        }
        if (liste.size > 0) OutlinedButton(onClick = { ranger = !ranger }) {
            Text(stringResource(if (ranger) R.string.sig_ranger_fini else R.string.sig_ranger), fontSize = 13.sp)
        }
        OutlinedButton(onClick = { recuperer = true }, enabled = Nuage.synchro(ctx) != null) {
            Text(stringResource(R.string.sig_recuperer), fontSize = 13.sp)
        }
        OutlinedButton(onClick = { verifier = true }) { Text(stringResource(R.string.sig_verifier), fontSize = 13.sp) }
    }
    importer?.let { o -> DialogueImporterPfx(o, { importer = null }) { liste = Identites.liste(ctx) } }
    if (recuperer) DialogueRecuperer({ recuperer = false }) { liste = Identites.liste(ctx); portee.launch { distantes = Identites.distantes(ctx) } }
    if (verifier) DialogueVerifier(etat) { verifier = false }
    if (creer) DialogueCreerCertificat({ creer = false }) { liste = Identites.liste(ctx) }
}

/** Creer un certificat personnel sur le telephone (comme PhilPDF Windows) : nom, e-mail, organisation, mot de passe. */
@Composable
private fun DialogueCreerCertificat(fermer: () -> Unit, fait: () -> Unit) {
    val ctx = LocalContext.current
    val portee = rememberCoroutineScope()
    var nom by remember { mutableStateOf(Nuage.synchro(ctx)?.nom(ctx).orEmpty()) }
    var email by remember { mutableStateOf(Nuage.synchro(ctx)?.email(ctx).orEmpty()) }
    var organisation by remember { mutableStateOf("") }
    var service by remember { mutableStateOf("") }
    var pays by remember { mutableStateOf("FR") }
    var annees by remember { mutableStateOf(5) }
    var mdp by remember { mutableStateOf("") }
    var mdp2 by remember { mutableStateOf("") }
    var occupe by remember { mutableStateOf(false) }
    var erreur by remember { mutableStateOf<String?>(null) }
    val pareils = mdp == mdp2
    val ok = nom.isNotBlank() && mdp.length >= 6 && pareils && !occupe
    Fenetre({ if (!occupe) fermer() }) {
        Surface(Modifier.fillMaxWidth(0.94f).widthIn(max = 560.dp).heightIn(max = 640.dp), shape = RoundedCornerShape(16.dp)) {
            Column(Modifier.padding(16.dp)) {
                Text(stringResource(R.string.sig_creer_titre), fontWeight = FontWeight.SemiBold, fontSize = 20.sp)
                Spacer(Modifier.height(6.dp))
                Column(Modifier.weight(1f, fill = false).verticalScroll(rememberScrollState())) {
                    Text(stringResource(R.string.sig_creer_aide), fontSize = 12.sp, color = Color.Gray)
                    OutlinedTextField(nom, { nom = it }, label = { Text(stringResource(R.string.sig_creer_nom)) }, singleLine = true, modifier = Modifier.fillMaxWidth())
                    OutlinedTextField(email, { email = it }, label = { Text(stringResource(R.string.sig_creer_email)) }, singleLine = true, modifier = Modifier.fillMaxWidth())
                    OutlinedTextField(organisation, { organisation = it }, label = { Text(stringResource(R.string.sig_creer_organisation)) }, singleLine = true, modifier = Modifier.fillMaxWidth())
                    OutlinedTextField(service, { service = it }, label = { Text(stringResource(R.string.sig_creer_service)) }, singleLine = true, modifier = Modifier.fillMaxWidth())
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        OutlinedTextField(pays, { pays = it.take(2).uppercase() }, label = { Text(stringResource(R.string.sig_creer_pays)) },
                            singleLine = true, modifier = Modifier.width(90.dp))
                        Spacer(Modifier.width(12.dp))
                        Text(stringResource(R.string.sig_creer_duree), fontSize = 13.sp)
                        TextButton(onClick = { if (annees > 1) annees-- }, contentPadding = PaddingValues(4.dp)) { Text("−") }
                        Text(stringResource(R.string.sig_creer_ans, annees), fontSize = 13.sp)
                        TextButton(onClick = { if (annees < 30) annees++ }, contentPadding = PaddingValues(4.dp)) { Text("+") }
                    }
                    ChampMotDePasse(mdp, { mdp = it }, stringResource(R.string.sig_creer_mdp))
                    ChampMotDePasse(mdp2, { mdp2 = it }, stringResource(R.string.sig_creer_mdp2))
                    if (mdp2.isNotEmpty() && !pareils) Text(stringResource(R.string.sig_creer_differents), color = ROUGE, fontSize = 12.sp)
                    if (occupe) LinearProgressIndicator(Modifier.fillMaxWidth().padding(top = 8.dp))
                    erreur?.let { Text(it, color = ROUGE, fontSize = 13.sp, modifier = Modifier.padding(top = 6.dp)) }
                }
                // boutons fixes, toujours visibles
                Row(Modifier.fillMaxWidth().padding(top = 8.dp), horizontalArrangement = Arrangement.End) {
                    TextButton(onClick = fermer, enabled = !occupe) { Text(stringResource(R.string.annuler)) }
                    TextButton(onClick = {
                        occupe = true; erreur = null
                        portee.launch {
                            try {
                                Identites.creer(ctx, nom, mdp, organisation, service, email, pays, annees)
                                fait(); fermer()
                            } catch (x: Exception) { erreur = x.message ?: x.toString() } finally { occupe = false }
                        }
                    }, enabled = ok) { Text(stringResource(R.string.sig_creer_bouton)) }
                }
            }
        }
    }
}

@Composable
private fun ChampMotDePasse(v: String, changer: (String) -> Unit, libelle: String) = ChampSecret(v, changer, libelle)

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
    var retenir by remember { mutableStateOf(true) }
    LaunchedEffect(Unit) { indice = Identites.indice(ctx) }
    AlertDialog(onDismissRequest = { if (!occupe) fermer() }, title = { Text(stringResource(R.string.sig_recuperer)) },
        text = {
            Column {
                Text(stringResource(R.string.sig_recuperer_aide), fontSize = 13.sp)
                indice?.let { Text(stringResource(R.string.sig_indice, it), fontSize = 12.sp, color = Color.Gray) }
                Spacer(Modifier.height(8.dp))
                ChampMotDePasse(phrase, { phrase = it }, stringResource(R.string.sig_phrase))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Checkbox(retenir, { retenir = it })
                    Text(stringResource(R.string.sig_retenir_phrase), fontSize = 13.sp)
                }
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
                        Identites.retenirPhrase(ctx, if (retenir) phrase else null)
                        fait()
                        // aucun .pfx dans les secrets : certificats ranges dans le magasin de Windows, ou partage desactive
                        android.widget.Toast.makeText(ctx, if (n > 0) ctx.getString(R.string.sig_recuperees, n) else ctx.getString(R.string.sig_rien_recupere),
                            android.widget.Toast.LENGTH_LONG).show()
                        fermer()
                    } catch (e: Exception) { erreur = e.message ?: e.toString() } finally { occupe = false }
                }
            }, enabled = phrase.isNotEmpty() && !occupe) { Text(stringResource(R.string.ok)) }
        },
        dismissButton = { TextButton(onClick = fermer, enabled = !occupe) { Text(stringResource(R.string.annuler)) } })
}

/** Apres le cadre trace : mot de passe du certificat, raison, lieu, image, puis enregistrer le PDF signe. */
@Composable
fun DialogueSigner(etat: EtatLecteur, page: Int, rect: com.artifex.mupdf.fitz.Rect, champ: String? = null, fermer: () -> Unit) {
    val ctx = LocalContext.current
    val portee = rememberCoroutineScope()
    val toutes = remember { Identites.liste(ctx) }
    var e by remember { mutableStateOf(etat.signerAvec ?: toutes.firstOrNull()) }
    val ident = e ?: return fermer()
    var mdp by remember { mutableStateOf("") }
    var raison by remember { mutableStateOf("") }
    var lieu by remember { mutableStateOf("") }
    val images = remember { Bibliotheque.locaux(ctx).filter { it.genre == "signatures" } }
    var avecImage by remember { mutableStateOf(images.isNotEmpty()) }
    var erreur by remember { mutableStateOf<String?>(null) }
    var occupe by remember { mutableStateOf(false) }
    var signe by remember { mutableStateOf<java.io.File?>(null) }
    var travail by remember { mutableStateOf<kotlinx.coroutines.Job?>(null) }
    val autreNom = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("application/pdf")) { u: Uri? ->
        val f = signe
        if (u != null && f != null) portee.launch {
            try { ecrireSigne(ctx, f, u); Ouvrir.demande.value = u; fermer() } catch (x: Exception) { erreur = x.message }
        }
    }
    AlertDialog(onDismissRequest = { if (!occupe) fermer() }, title = { Text(stringResource(R.string.sig_signer_titre)) },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState())) {
                // plusieurs certificats : on choisit ici
                if (toutes.size > 1 && signe == null) FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    toutes.forEach { x ->
                        val n = x.nom.ifEmpty { x.email }
                        val pareil = toutes.count { it.nom.ifEmpty { it.email } == n } > 1
                        FilterChip(x.id == ident.id, { e = x; etat.signerAvec = x },
                            label = { Text(if (pareil) "$n (" + (x.email.takeIf { it.isNotEmpty() && it != n } ?: x.fin.ifEmpty { x.id.take(4) }) + ")" else n,
                                fontSize = 12.sp) })
                    }
                } else Text(stringResource(R.string.sig_avec, ident.nom.ifEmpty { ident.email }), fontSize = 13.sp)
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
                travail = portee.launch {
                    try {
                        val o = Identites.octets(ctx, ident.id) ?: throw ErreurCertificat(ctx.getString(R.string.sig_illisible))
                        val (clef, chaine) = withContext(Dispatchers.IO) { Identites.ouvrir(o, mdp) }
                        // identite venue de Windows : infos completes une fois le mot de passe connu
                        if (ident.empreinte.isEmpty()) try { Identites.ajouter(ctx, o, mdp, ident.id) } catch (_: Exception) {}
                        val sig = Signataire(clef, chaine)
                        val img = if (avecImage) images.firstOrNull()?.let { Bibliotheque.apercu(ctx, it) }?.takeIf { it.exists() }?.readBytes() else null
                        signe = etat.doc.signerNumerique(ctx, page, rect, sig, raison, lieu, img, champ)
                        Journal.ecrire("certificat", "${etat.doc.nom} : signé par ${ident.nom}" + if (sig.horodatee) " (horodaté)" else "")
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
        // Annuler reste possible pendant la signature (horodatage lent, reseau coupe...)
        dismissButton = { TextButton(onClick = { travail?.cancel(); occupe = false; fermer() }) { Text(stringResource(R.string.annuler)) } })
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

/** Liste deroulante dessinee : son nom et ses choix (un par ligne), ou une liste toute prete. */
@Composable
fun DialogueListe(etat: EtatLecteur, page: Int, rect: com.artifex.mupdf.fitz.Rect, fermer: () -> Unit) {
    val ctx = LocalContext.current
    val portee = rememberCoroutineScope()
    var nom by remember { mutableStateOf("") }
    var choix by remember { mutableStateOf("") }
    val pretes = listOf(R.string.liste_oui_non to "Oui\nNon", R.string.liste_civilite to "Madame\nMonsieur",
        R.string.liste_mois to "Janvier\nFévrier\nMars\nAvril\nMai\nJuin\nJuillet\nAoût\nSeptembre\nOctobre\nNovembre\nDécembre",
        R.string.liste_jours to "Lundi\nMardi\nMercredi\nJeudi\nVendredi\nSamedi\nDimanche")
    AlertDialog(onDismissRequest = fermer, title = { Text(stringResource(R.string.outil_champ_liste)) },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState())) {
                OutlinedTextField(nom, { nom = it }, label = { Text(stringResource(R.string.nom_champ)) }, singleLine = true,
                    placeholder = { Text(stringResource(R.string.nom_auto)) }, modifier = Modifier.fillMaxWidth())
                Spacer(Modifier.height(6.dp))
                OutlinedTextField(choix, { choix = it }, label = { Text(stringResource(R.string.liste_choix)) }, minLines = 3, maxLines = 8,
                    modifier = Modifier.fillMaxWidth())
                Text(stringResource(R.string.liste_pretes), fontSize = 12.sp, color = Color.Gray)
                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    pretes.forEach { (t, v) -> AssistChip(onClick = { choix = v }, label = { Text(stringResource(t), fontSize = 12.sp) }) }
                }
            }
        },
        confirmButton = {
            val l = choix.lines().map { it.trim() }.filter { it.isNotEmpty() }
            TextButton(onClick = {
                portee.launch {
                    etat.doc.creerChamps(listOf(ChampDetecte(page, "liste", rect, nom.trim(), choix = l)))
                    fermer()
                }
            }, enabled = l.isNotEmpty()) { Text(stringResource(R.string.appliquer)) }
        },
        dismissButton = { TextButton(onClick = fermer) { Text(stringResource(R.string.annuler)) } })
}
