package io.github.philouelchapo.philpdf

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import androidx.compose.foundation.clickable
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.launch

/** « Partager » : envoyer le fichier lui-meme, ou un lien (le PDF est depose dans PhilPDF/Partages du compte de
 *  synchronisation ; le lien part dans le texte de l'e-mail, pratique pour un gros fichier). */
@Composable
fun ChoixPartage(etat: EtatLecteur, fermer: () -> Unit) {
    val ctx = LocalContext.current
    val portee = rememberCoroutineScope()
    // le lien passe par un compte qui sait en faire (Google Drive par defaut) ; « Changer » en choisit un autre
    var compte by remember { mutableStateOf(Nuage.compteLien(ctx)) }
    val possibles = remember { Nuage.liste(ctx).filter { Nuage.peutLien(ctx, it) } }
    var changer by remember { mutableStateOf(false) }
    var occupe by remember { mutableStateOf(false) }
    var erreur by remember { mutableStateOf<String?>(null) }
    AlertDialog(onDismissRequest = { if (!occupe) fermer() },
        title = { Text(stringResource(R.string.partager)) },
        text = {
            // defile si l'ecran est bas (telephone a l'horizontale) : rien d'ecrase
            Column(Modifier.verticalScroll(androidx.compose.foundation.rememberScrollState())) {
                Ligne("courriel", stringResource(R.string.partage_fichier), stringResource(R.string.partage_fichier_aide), !occupe) {
                    fermer(); portee.launch { partager(ctx, etat.doc) }
                }
                Spacer(Modifier.height(6.dp))
                Ligne("synchro", stringResource(R.string.partage_lien),
                    compte?.let { stringResource(R.string.partage_lien_aide, it.fournisseur(ctx).nom + " · " + it.libelle(ctx)) }
                        ?: if (Nuage.liste(ctx).isNotEmpty()) stringResource(R.string.lien_aucun_compte) else
                    stringResource(R.string.partage_sans_compte), !occupe && compte != null) {
                    val n = compte ?: return@Ligne
                    occupe = true; erreur = null
                    portee.launch {
                        try {
                            val f = etat.doc.copieAJour(ctx)
                            val lien = n.partagerParLien(ctx, etat.doc.nom, f.readBytes())
                            envoyerLien(ctx, etat.doc.nom, lien)
                            fermer()
                        } catch (e: Exception) {
                            Journal.ecrire("partage", "lien impossible ($e)")
                            erreur = e.message ?: e.toString()
                        } finally { occupe = false }
                    }
                }
                if (compte != null && possibles.size > 1) {
                    TextButton(onClick = { changer = !changer }, enabled = !occupe, modifier = Modifier.padding(start = 36.dp)) {
                        Text(stringResource(R.string.lien_changer), fontSize = 13.sp) }
                    if (changer) possibles.forEach { c ->
                        Row(Modifier.fillMaxWidth().clickable { compte = c; Nuage.choisirLien(ctx, c); changer = false }
                            .padding(start = 44.dp, top = 6.dp, bottom = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                            RadioButton(c.id == compte?.id, { compte = c; Nuage.choisirLien(ctx, c); changer = false })
                            Column {
                                Text(c.fournisseur(ctx).nom, fontSize = 14.sp)
                                Text(c.libelle(ctx), fontSize = 12.sp, color = Color.Gray)
                            }
                        }
                    }
                }
                if (occupe) Row(Modifier.padding(top = 10.dp), verticalAlignment = Alignment.CenterVertically) {
                    CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp)
                    Spacer(Modifier.width(10.dp))
                    Text(stringResource(R.string.partage_envoi), fontSize = 13.sp)
                }
                erreur?.let { Text(it, color = ROUGE, fontSize = 13.sp, modifier = Modifier.padding(top = 8.dp)) }
            }
        },
        confirmButton = {},
        dismissButton = { TextButton(onClick = fermer, enabled = !occupe) { Text(stringResource(R.string.annuler)) } })
}

@Composable
private fun Ligne(icone: String, titre: String, aide: String, actif: Boolean, faire: () -> Unit) {
    Row(Modifier.fillMaxWidth().clickable(enabled = actif, onClick = faire).padding(vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically) {
        Icon(Icones.get(icone, if (actif) ROUGE else Color(0xFFBBBBBB)), null, tint = Color.Unspecified)
        Spacer(Modifier.width(12.dp))
        Column {
            Text(titre, fontWeight = FontWeight.SemiBold, color = if (actif) Color.Unspecified else Color.Gray)
            Text(aide, fontSize = 12.sp, color = Color.Gray)
        }
    }
}

/** Le lien part dans le texte du message (messagerie au choix) ; il est aussi copie. */
private fun envoyerLien(ctx: Context, nom: String, lien: String) {
    (ctx.getSystemService(Context.CLIPBOARD_SERVICE) as? ClipboardManager)?.setPrimaryClip(ClipData.newPlainText(nom, lien))
    val texte = ctx.getString(R.string.partage_message, nom, lien)
    val i = Intent(Intent.ACTION_SEND).setType("text/plain")
        .putExtra(Intent.EXTRA_SUBJECT, nom).putExtra(Intent.EXTRA_TEXT, texte)
    ctx.startActivity(Intent.createChooser(i, ctx.getString(R.string.partage_lien)))
}
