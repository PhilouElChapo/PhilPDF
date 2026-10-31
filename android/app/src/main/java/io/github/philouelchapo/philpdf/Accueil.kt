@file:OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class)

package io.github.philouelchapo.philpdf

import android.content.Intent
import android.graphics.BitmapFactory
import android.net.Uri
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
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

val ROUGE = Color(0xFFC9252D)

@Composable
fun Accueil(ouvrir: (Uri) -> Unit, choisir: () -> Unit) {
    val ctx = LocalContext.current
    var recents by remember { mutableStateOf(Recents.liste(ctx)) }
    var maj by remember { mutableStateOf<NouvelleVersion?>(null) }
    LaunchedEffect(Unit) { maj = MiseAJour.chercher(BuildConfig.VERSION_NAME) }
    var versionCompte by remember { mutableIntStateOf(0) }
    var ecranCompte by remember { mutableStateOf(false) }
    var parcourir by remember { mutableStateOf<Nuage?>(null) }
    val comptes = remember(versionCompte) { Nuage.liste(ctx) }
    // Google Drive (autorisation limitee) : ses PDF passent par le selecteur d'Android, qui le propose deja
    val voir: (Nuage) -> Unit = { n -> if (n.parcourable(ctx)) parcourir = n else choisir() }
    var nouveautes by remember { mutableIntStateOf(0) }
    // compte relie : on regarde (sans rien recuperer) si vos postes ont de nouvelles signatures ou de nouveaux tampons
    LaunchedEffect(versionCompte) {
        nouveautes = if (!(Nuage.synchro(ctx) != null)) 0 else try {
            Bibliotheque.lireDrive(ctx).let { e -> e.nouveaux + Bibliotheque.locaux(ctx).count { l -> e.distants.none { it.id == l.id } } }
        } catch (_: Exception) { 0 }
    }
    val pastille: @Composable () -> Unit = { PastilleCompte(versionCompte) { ecranCompte = true } }

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
                Button(onClick = choisir, colors = ButtonDefaults.buttonColors(containerColor = ROUGE)) {
                    Text(stringResource(R.string.ouvrir_fichier))
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
                        TextButton(onClick = { ctx.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(v.lien))) }) {
                            Text(stringResource(R.string.telecharger))
                        }
                        TextButton(onClick = { maj = null }) { Text(stringResource(R.string.plus_tard)) }
                    }
                }
            }
        }
        // vos comptes : un toucher pour parcourir leurs PDF (comme « Fichiers » d'Acrobat)
        Spacer(Modifier.height(12.dp))
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            comptes.forEach { n ->
                AssistChip(onClick = { voir(n) }, label = {
                    Text(n.fournisseur(ctx).nom + (n.email(ctx)?.let { " · " + it.substringBefore('@') } ?: ""),
                        maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.widthIn(max = 220.dp))
                }, leadingIcon = { AvatarCompte(n, versionCompte, 20.dp) })
            }
            AssistChip(onClick = { ecranCompte = true }, label = { Text(stringResource(R.string.ajouter_compte_court)) })
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
        Spacer(Modifier.height(16.dp))
        Text(stringResource(R.string.recents), fontWeight = FontWeight.SemiBold)
        Spacer(Modifier.height(8.dp))
        Box(Modifier.weight(1f).fillMaxWidth().background(Color.White, RoundedCornerShape(10.dp))
            .border(1.dp, Color(0xFFE2E2E2), RoundedCornerShape(10.dp))) {
            if (recents.isEmpty()) {
                Text(stringResource(R.string.aucun_recent), Modifier.padding(16.dp), color = Color.Gray)
            } else {
                LazyColumn {
                    items(recents, key = { it.uri }) { r ->
                        LigneRecent(r, { ouvrir(Uri.parse(r.uri)) }, {
                            Recents.retirer(ctx, r.uri)
                            recents = Recents.liste(ctx)
                        })
                        HorizontalDivider(color = Color(0xFFEEEEEE))
                    }
                }
            }
        }
        Spacer(Modifier.height(6.dp))
        Text(stringResource(R.string.version, BuildConfig.VERSION_NAME), fontSize = 12.sp, color = Color.Gray)
    }
    if (ecranCompte) EcranComptes(fermer = { ecranCompte = false; versionCompte++ },
        parcourir = { n -> ecranCompte = false; versionCompte++; voir(n) })
    parcourir?.let { n -> EcranFichiers(n, fermer = { parcourir = null }, ouvrir = ouvrir) }
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
