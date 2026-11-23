@file:OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class)

package io.github.philouelchapo.philpdf

import android.content.Intent
import android.graphics.BitmapFactory
import android.net.Uri
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Date
import java.util.Locale
import kotlinx.coroutines.launch

val ROUGE = Color(0xFFC9252D)

@Composable
fun Accueil(ouvrir: (Uri) -> Unit, choisir: () -> Unit, numeriser: () -> Unit = {}, combiner: () -> Unit = {}) {
    val ctx = LocalContext.current
    var recents by remember { mutableStateOf(Recents.liste(ctx)) }
    var maj by remember { mutableStateOf<NouvelleVersion?>(null) }
    LaunchedEffect(Unit) { maj = MiseAJour.chercher(BuildConfig.VERSION_NAME) }
    var versionCompte by remember { mutableIntStateOf(0) }
    var ecranCompte by remember { mutableStateOf(false) }
    var parcourir by remember { mutableStateOf<Nuage?>(null) }
    // comptes que PhilPDF parcourt lui-meme (pCloud, kDrive, WebDAV, OneDrive...) : petit bouton nuage a cote de l'avatar
    val parcourables = remember(versionCompte) { comptesParcourables(ctx) }
    var aide by remember { mutableStateOf(false) }
    var reglagesIa by remember { mutableStateOf(false) }
    // compte prefere (envois et lecture) en tete
    val comptes = remember(versionCompte) { Nuage.liste(ctx).sortedBy { if (Nuage.estPrefere(ctx, it)) 0 else 1 } }
    // Google Drive (autorisation limitee) : ses PDF passent par le selecteur d'Android, qui le propose deja
    val voir: (Nuage) -> Unit = { n -> if (n.parcourable(ctx)) parcourir = n else choisir() }
    var nouveautes by remember { mutableIntStateOf(0) }
    // compte relie : on regarde (sans rien recuperer) si vos postes ont de nouvelles signatures ou de nouveaux tampons
    LaunchedEffect(versionCompte) {
        nouveautes = if (!(Nuage.synchro(ctx) != null)) 0 else try {
            Bibliotheque.lireDrive(ctx).let { e -> e.nouveaux + Bibliotheque.locaux(ctx).count { l -> e.distants.none { it.id == l.id } } }
        } catch (_: Exception) { 0 }
    }
    // fichiers ouverts sur vos autres postes depuis un Drive : lus en arriere-plan, l'Accueil ne les attend pas
    var autres by remember { mutableStateOf<List<FichierPoste>>(emptyList()) }
    var telechargement by remember { mutableStateOf<FichierPoste?>(null) }
    var erreurAutre by remember { mutableStateOf<String?>(null) }
    LaunchedEffect(versionCompte) { autres = try { AutresPostes.lire(ctx, versionCompte > 0) } catch (_: Exception) { emptyList() } }
    LaunchedEffect(telechargement) {
        val f = telechargement ?: return@LaunchedEffect
        try {
            val u = f.compte.ouvrirChemin(ctx, f.chemin)
            Journal.ecrire("autres postes", "ouvert : ${f.lieu} ${f.chemin}")
            telechargement = null
            ouvrir(u)
        } catch (e: Exception) {
            Journal.ecrire("autres postes", "${f.chemin} : $e")
            erreurAutre = (e as? ErreurCompte)?.message ?: ctx.getString(R.string.autres_echec, f.nom, e.message ?: e.javaClass.simpleName)
            telechargement = null
        }
    }
    // partages par lien (PhilPDF/Partages du Drive de synchronisation) : lus en arriere-plan, comme les autres postes
    var partages by remember { mutableStateOf<List<PartageLien>>(emptyList()) }
    var versionPartages by remember { mutableIntStateOf(0) }
    var menuPartage by remember { mutableStateOf<PartageLien?>(null) }
    var ouvrirPartage by remember { mutableStateOf<PartageLien?>(null) }
    var nettoyer by remember { mutableStateOf(false) }
    var partagesOuverts by remember { mutableStateOf(ctx.getSharedPreferences("philpdf", 0).getBoolean("partages_ouverts", true)) }
    val portee = rememberCoroutineScope()
    LaunchedEffect(versionCompte, versionPartages) {
        partages = try { Nuage.synchro(ctx)?.listerPartages(ctx) ?: emptyList() } catch (e: Exception) {
            Journal.ecrire("partage", "liste des partages illisible ($e)"); emptyList() }
        try { Appareil.publier(ctx) } catch (_: Exception) { }
    }
    LaunchedEffect(ouvrirPartage) {
        val p = ouvrirPartage ?: return@LaunchedEffect
        try {
            val u = p.compte.ouvrirFichier(ctx, Entree(p.id, p.nom, false, 0, p.modifie))
            Distants.marquerPartage(ctx, u, p.modifie)
            ouvrirPartage = null
            ouvrir(u)
        } catch (e: Exception) {
            Journal.ecrire("partage", "${p.nom} : $e")
            erreurAutre = (e as? ErreurCompte)?.message ?: ctx.getString(R.string.autres_echec, p.nom, e.message ?: e.javaClass.simpleName)
            ouvrirPartage = null
        }
    }
    fun agirPartage(p: List<PartageLien>, faire: suspend (PartageLien) -> String?) {
        portee.launch {
            var lien: String? = null
            for (x in p) try { lien = faire(x) } catch (e: Exception) {
                erreurAutre = (e as? ErreurCompte)?.message ?: e.toString() }
            lien?.let { envoyerLienPartage(ctx, p.first().nom, it) }
            versionPartages++
        }
    }
    val pastille: @Composable () -> Unit = {
        Row(verticalAlignment = Alignment.CenterVertically) {
            // « Ouvrir depuis le cloud » : le compte prefere s'ouvre, on peut changer de compte en haut de la liste
            if (parcourables.isNotEmpty()) IconButton(onClick = { parcourir = parcourables.first() }, Modifier.size(40.dp)) {
                Icon(Icones.get("nuage", Color(0xFF777777)), stringResource(R.string.ouvrir_cloud), Modifier.size(24.dp), tint = Color.Unspecified)
            }
            PastilleCompte(versionCompte) { ecranCompte = true }
        }
    }

    Column(Modifier.fillMaxSize().background(Color(0xFFF3F3F3)).padding(16.dp)) {
        // en-tete : logo, nom, bouton principal (passe sous le titre si l'ecran est etroit : rien de coupe)
        BoxWithConstraints(Modifier.fillMaxWidth()) {
            val etroit = maxWidth < 420.dp
            val titre: @Composable () -> Unit = {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Image(painterResource(R.drawable.logo), null, Modifier.size(44.dp))
                    Spacer(Modifier.width(10.dp))
                    Text(buildAnnotatedString {
                        withStyle(SpanStyle(fontWeight = FontWeight.Bold)) { append("Phil") }
                        withStyle(SpanStyle(fontWeight = FontWeight.Bold, color = ROUGE)) { append("PDF") }
                    }, fontSize = 26.sp)
                }
            }
            val bouton: @Composable () -> Unit = {
                // ouvrir, numeriser, combiner : trois boutons sur une seule ligne (icone et nom court dessous)
                Row(if (etroit) Modifier.fillMaxWidth() else Modifier.widthIn(max = 420.dp),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    BoutonAccueil("ouvrir", stringResource(R.string.accueil_ouvrir), true, Modifier.weight(1f)) {
                        choisir() }
                    BoutonAccueil("numeriser", stringResource(R.string.accueil_numeriser), false, Modifier.weight(1f), numeriser)
                    BoutonAccueil("combiner", stringResource(R.string.accueil_combiner), false, Modifier.weight(1f), combiner)
                }
            }
            if (etroit) {
                Column {
                    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                        titre(); Spacer(Modifier.weight(1f)); pastille()
                    }
                    Spacer(Modifier.height(10.dp)); bouton()
                }
            } else {
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    titre(); Spacer(Modifier.weight(1f)); bouton(); Spacer(Modifier.width(12.dp)); pastille()
                }
            }
        }
        maj?.let { v ->
            Spacer(Modifier.height(12.dp))
            Card(colors = CardDefaults.cardColors(containerColor = Color(0xFFFFF4E5))) {
                Column(Modifier.padding(12.dp)) {
                    Text(stringResource(R.string.maj_dispo, v.version, BuildConfig.VERSION_NAME))
                    Row {
                        TextButton(onClick = {
                            Journal.ecrire("mise à jour", "${v.version} : téléchargement demandé (${v.lien})")
                            ctx.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(v.lien)))
                        }) {
                            Text(stringResource(R.string.telecharger))
                        }
                        TextButton(onClick = { Journal.ecrire("mise à jour", "${v.version} : « Plus tard »"); maj = null }) { Text(stringResource(R.string.plus_tard)) }
                    }
                }
            }
        }
        if (nouveautes > 0) {
            Spacer(Modifier.height(12.dp))
            Card(colors = CardDefaults.cardColors(containerColor = Color(0xFFE8F0FE))) {
                Row(Modifier.fillMaxWidth().padding(start = 12.dp, end = 4.dp), verticalAlignment = Alignment.CenterVertically) {
                    Text(stringResource(R.string.nouveautes_postes, nouveautes), Modifier.weight(1f), fontSize = 14.sp)
                    TextButton(onClick = { ecranCompte = true }) { Text(stringResource(R.string.voir)) }
                }
            }
        }
        if (partages.isNotEmpty()) {
            Spacer(Modifier.height(12.dp))
            Card(colors = CardDefaults.cardColors(containerColor = Color.White)) {
                Column(Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 6.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text((if (partagesOuverts) "▾  " else "▸  ") + stringResource(R.string.partages_titre, partages.size),
                            Modifier.weight(1f).clickable {
                                partagesOuverts = !partagesOuverts
                                ctx.getSharedPreferences("philpdf", 0).edit().putBoolean("partages_ouverts", partagesOuverts).apply()
                            }.padding(vertical = 6.dp), fontWeight = FontWeight.SemiBold)
                        val autresComptes = parcourables.filter { it.id != Nuage.synchro(ctx)?.id }
                        if (autresComptes.isNotEmpty()) TextButton(onClick = { parcourir = autresComptes.first() }) {
                            Text(stringResource(R.string.partages_autres_comptes), fontSize = 12.sp) }
                    }
                    val anciens = partages.filter { it.ancien }
                    if (anciens.isNotEmpty()) Row(Modifier.fillMaxWidth().background(Color(0xFFFFF8E6), RoundedCornerShape(6.dp))
                        .padding(horizontal = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                        Text(stringResource(R.string.partages_anciens, anciens.size), Modifier.weight(1f), fontSize = 13.sp)
                        TextButton(onClick = { nettoyer = true }) { Text(stringResource(R.string.partages_voir_supprimer)) }
                    }
                    if (partagesOuverts) Column(Modifier.heightIn(max = 190.dp).verticalScroll(androidx.compose.foundation.rememberScrollState())) {
                        partages.forEach { p -> LignePartage(p, { ouvrirPartage = p }, { menuPartage = p }) }
                    }
                }
            }
        }
        Spacer(Modifier.height(16.dp))
        Text(stringResource(R.string.recents), fontWeight = FontWeight.SemiBold)
        Spacer(Modifier.height(8.dp))
        Box(Modifier.weight(1f).fillMaxWidth().background(Color.White, RoundedCornerShape(10.dp))
            .border(1.dp, Color(0xFFE2E2E2), RoundedCornerShape(10.dp))) {
            if (recents.isEmpty() && autres.isEmpty()) {
                Text(stringResource(R.string.aucun_recent), Modifier.padding(16.dp), color = Color.Gray)
            } else {
                LazyColumn {
                    if (recents.isEmpty()) item { Text(stringResource(R.string.aucun_recent), Modifier.padding(16.dp), color = Color.Gray) }
                    items(recents, key = { it.uri }) { r ->
                        LigneRecent(r, { ouvrir(Uri.parse(r.uri)) }, {
                            Recents.retirer(ctx, r.uri)
                            recents = Recents.liste(ctx)
                        })
                        HorizontalDivider(color = Color(0xFFEEEEEE))
                    }
                    if (autres.isNotEmpty()) {
                        item {
                            Text(stringResource(R.string.autres_postes_titre), Modifier.fillMaxWidth().background(Color(0xFFF7F7F7))
                                .padding(horizontal = 12.dp, vertical = 6.dp), fontSize = 13.sp, fontWeight = FontWeight.SemiBold, color = Color(0xFF555555))
                        }
                        items(autres, key = { "autre|" + it.compte.id + it.chemin }) { f ->
                            LigneAutrePoste(f) { telechargement = f }
                            HorizontalDivider(color = Color(0xFFEEEEEE))
                        }
                    }
                }
            }
        }
        Spacer(Modifier.height(6.dp))
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(stringResource(R.string.version, BuildConfig.VERSION_NAME), Modifier.weight(1f), fontSize = 12.sp, color = Color.Gray)
            TextButton(onClick = { reglagesIa = true }) { Text(stringResource(R.string.ia_court_accueil)) }
            TextButton(onClick = { aide = true }) { Text(stringResource(R.string.aide)) }
        }
    }
    if (ecranCompte) EcranComptes(fermer = { ecranCompte = false; versionCompte++ },
        parcourir = { n -> ecranCompte = false; versionCompte++; voir(n) })
    parcourir?.let { n -> EcranFichiers(n, fermer = { parcourir = null }, ouvrir = ouvrir) }
    if (aide) EcranAide { aide = false }
    telechargement?.let { f ->
        AlertDialog(onDismissRequest = {}, confirmButton = {}, title = { Text(stringResource(R.string.accueil_ouvrir)) },
            text = { Row(verticalAlignment = Alignment.CenterVertically) {
                CircularProgressIndicator(Modifier.size(24.dp)); Spacer(Modifier.width(12.dp))
                Text(stringResource(R.string.autres_telechargement, f.nom, f.lieu)) } })
    }
    erreurAutre?.let { m ->
        AlertDialog(onDismissRequest = { erreurAutre = null }, confirmButton = { TextButton(onClick = { erreurAutre = null }) { Text("OK") } },
            title = { Text(stringResource(R.string.accueil_ouvrir)) }, text = { Text(m) })
    }
    if (reglagesIa) ReglagesIa { reglagesIa = false }
    ouvrirPartage?.let { p ->
        AlertDialog(onDismissRequest = {}, confirmButton = {}, title = { Text(stringResource(R.string.accueil_ouvrir)) },
            text = { Row(verticalAlignment = Alignment.CenterVertically) {
                CircularProgressIndicator(Modifier.size(24.dp)); Spacer(Modifier.width(12.dp))
                Text(stringResource(R.string.autres_telechargement, p.nom, p.compte.fournisseur(ctx).nom)) } })
    }
    menuPartage?.let { p ->
        var confirmer by remember { mutableStateOf(false) }
        AlertDialog(onDismissRequest = { menuPartage = null }, title = { Text(p.nom) },
            text = {
                Column {
                    if (confirmer) Text(stringResource(R.string.partage_supprimer_q, p.nom))
                    else {
                        TextButton(onClick = { menuPartage = null; ouvrirPartage = p }) { Text(stringResource(R.string.accueil_ouvrir)) }
                        if (p.actif) {
                            TextButton(onClick = { menuPartage = null; envoyerLienPartage(ctx, p.nom, p.lien) }) {
                                Text(stringResource(R.string.partage_envoyer_lien)) }
                            TextButton(onClick = { menuPartage = null; agirPartage(listOf(p)) { it.compte.lienPartage(ctx, it, false) } }) {
                                Text(stringResource(R.string.partage_arreter)) }
                        } else TextButton(onClick = { menuPartage = null; agirPartage(listOf(p)) { it.compte.lienPartage(ctx, it, true) } }) {
                            Text(stringResource(R.string.partage_reprendre)) }
                        TextButton(onClick = { confirmer = true }) { Text(stringResource(R.string.partage_supprimer), color = ROUGE) }
                    }
                }
            },
            confirmButton = { if (confirmer) TextButton(onClick = {
                menuPartage = null; agirPartage(listOf(p)) { it.compte.corbeillePartage(ctx, it); null } }) {
                Text(stringResource(R.string.partage_supprimer), color = ROUGE) } },
            dismissButton = { TextButton(onClick = { menuPartage = null }) { Text(stringResource(R.string.annuler)) } })
    }
    if (nettoyer) {
        val anciens = partages.filter { it.ancien }
        AlertDialog(onDismissRequest = { nettoyer = false }, title = { Text(stringResource(R.string.partages_anciens_titre)) },
            text = { Text(stringResource(R.string.partages_anciens_q, anciens.joinToString("\n") { "• " + it.nom })) },
            confirmButton = { TextButton(onClick = { nettoyer = false; agirPartage(anciens) { it.compte.corbeillePartage(ctx, it); null } }) {
                Text(stringResource(R.string.partage_supprimer), color = ROUGE) } },
            dismissButton = { TextButton(onClick = { nettoyer = false }) { Text(stringResource(R.string.annuler)) } })
    }
}

@OptIn(androidx.compose.foundation.ExperimentalFoundationApi::class)
@Composable
private fun LignePartage(p: PartageLien, ouvrir: () -> Unit, menu: () -> Unit) {
    val date = try { java.time.Instant.parse(p.cree).toEpochMilli() } catch (_: Exception) { 0L }
    Row(Modifier.fillMaxWidth().combinedClickable(onClick = ouvrir, onLongClick = menu).padding(vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically) {
        Icon(Icones.get("lien", if (p.actif) Color(0xFF2B6CB0) else Color(0xFFAAAAAA)), null, Modifier.size(22.dp), tint = Color.Unspecified)
        Spacer(Modifier.width(10.dp))
        Column(Modifier.weight(1f)) {
            Text(p.nom, maxLines = 1, overflow = TextOverflow.Ellipsis, color = if (p.actif) Color.Unspecified else Color.Gray)
            Text(listOfNotNull(if (date > 0) dateFr(date) else null,
                p.poste.takeIf { it.isNotEmpty() }?.let { stringResource(R.string.partage_depuis, it) },
                if (!p.actif) stringResource(R.string.partage_arrete) else null).joinToString(" · "),
                fontSize = 12.sp, color = Color.Gray, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
        IconButton(onClick = menu, Modifier.size(36.dp)) { Text("⋯", fontSize = 18.sp, color = Color.Gray) }
    }
}

/** Le lien d'un partage part dans le texte du message (messagerie au choix) ; il est aussi copie. */
private fun envoyerLienPartage(ctx: android.content.Context, nom: String, lien: String) {
    (ctx.getSystemService(android.content.Context.CLIPBOARD_SERVICE) as? android.content.ClipboardManager)
        ?.setPrimaryClip(android.content.ClipData.newPlainText(nom, lien))
    val i = Intent(Intent.ACTION_SEND).setType("text/plain").putExtra(Intent.EXTRA_SUBJECT, nom)
        .putExtra(Intent.EXTRA_TEXT, ctx.getString(R.string.partage_message, nom, lien))
    ctx.startActivity(Intent.createChooser(i, ctx.getString(R.string.partage_lien)))
}

@Composable
private fun LigneRecent(r: Recent, ouvrir: () -> Unit, retirer: () -> Unit) {
    val ctx = LocalContext.current
    // miniature deja faite seulement : l'Accueil s'affiche tout de suite
    val image = remember(r.uri, r.date) {
        val f = Miniatures.fichier(ctx, r.uri)
        if (f.exists()) BitmapFactory.decodeFile(f.absolutePath)?.asImageBitmap() else null
    }
    Row(Modifier.fillMaxWidth().clickable(onClick = ouvrir).padding(horizontal = 12.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.size(40.dp, 52.dp).border(1.dp, Color(0xFFCFCFCF)).background(Color.White),
            contentAlignment = Alignment.Center) {
            if (image != null) Image(image, null, Modifier.fillMaxSize(), contentScale = ContentScale.Fit)
            else Image(painterResource(R.drawable.logo), null, Modifier.size(26.dp))
        }
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            Text(r.nom, maxLines = 2, overflow = TextOverflow.Ellipsis)
            Text(dateFr(r.date) + if (r.pages > 0) " · " + stringResource(R.string.pages, r.pages) else "",
                fontSize = 12.sp, color = Color.Gray)
        }
        IconButton(onClick = retirer) {
            Icon(Icons.Default.Close, stringResource(R.string.retirer_liste), tint = Color.Gray)
        }
    }
}

@Composable
private fun LigneAutrePoste(f: FichierPoste, ouvrir: () -> Unit) {
    val date = try { java.time.LocalDateTime.parse(f.date).atZone(java.time.ZoneId.systemDefault()).toInstant().toEpochMilli() } catch (_: Exception) { 0L }
    Row(Modifier.fillMaxWidth().clickable(onClick = ouvrir).padding(horizontal = 12.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.size(40.dp, 52.dp).border(1.dp, Color(0xFFCFCFCF)).background(Color.White), contentAlignment = Alignment.Center) {
            Icon(Icones.get("synchro", Color(0xFF0F6CBD)), null, tint = Color.Unspecified)
        }
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            Text(f.nom, maxLines = 2, overflow = TextOverflow.Ellipsis)
            Text(stringResource(if (f.ouvert) R.string.autres_ouvert_sur else R.string.autres_vu_sur, f.poste) +
                (if (date > 0) " · " + dateFr(date) else "") + " · " + f.lieu, fontSize = 12.sp, color = Color.Gray, maxLines = 2,
                overflow = TextOverflow.Ellipsis)
        }
    }
}

@Composable
private fun dateFr(t: Long): String {
    val heure = SimpleDateFormat("HH:mm", Locale.FRANCE).format(Date(t))
    val c = Calendar.getInstance()
    val j = Calendar.getInstance().apply { timeInMillis = t }
    val memeJour = c.get(Calendar.YEAR) == j.get(Calendar.YEAR) && c.get(Calendar.DAY_OF_YEAR) == j.get(Calendar.DAY_OF_YEAR)
    c.add(Calendar.DAY_OF_YEAR, -1)
    val hier = c.get(Calendar.YEAR) == j.get(Calendar.YEAR) && c.get(Calendar.DAY_OF_YEAR) == j.get(Calendar.DAY_OF_YEAR)
    return when {
        memeJour -> stringResource(R.string.aujourdhui, heure)
        hier -> stringResource(R.string.hier, heure)
        else -> SimpleDateFormat("dd/MM/yyyy HH:mm", Locale.FRANCE).format(Date(t))
    }
}

/** Bouton de l'Accueil : icone au-dessus d'un nom court (le nom retrecit plutot que d'etre coupe). */
@Composable
private fun BoutonAccueil(icone: String, texte: String, principal: Boolean, modifier: Modifier, action: () -> Unit) {
    val fond = if (principal) ROUGE else Color.White
    val encre = if (principal) Color.White else ROUGE
    Surface(onClick = action, modifier = modifier.heightIn(min = 64.dp), shape = RoundedCornerShape(14.dp), color = fond,
        border = if (principal) null else androidx.compose.foundation.BorderStroke(1.dp, Color(0xFFCCCCCC))) {
        Column(Modifier.padding(horizontal = 6.dp, vertical = 8.dp), horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center) {
            Icon(Icones.get(icone, encre), null, tint = Color.Unspecified)
            Spacer(Modifier.height(4.dp))
            CompositionLocalProvider(LocalContentColor provides encre) { TexteAjuste(texte, 14.sp) }
        }
    }
}
