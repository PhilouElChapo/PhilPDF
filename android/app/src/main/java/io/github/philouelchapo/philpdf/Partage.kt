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

/** « Partager » : envoyer le fichier lui-meme, ou un lien. Le PDF est depose dans PhilPDF/Partages du compte (dossier
 *  cree s'il manque) et le lien public part dans le texte du message, quel que soit le compte : Google Drive en
 *  direct, ou un autre compte relie qui sait faire un lien (OneDrive, Dropbox, Box). */
@Composable
fun ChoixPartage(etat: EtatLecteur, fermer: () -> Unit) {
    val ctx = LocalContext.current
    val portee = rememberCoroutineScope()
    val possibles = remember { Nuage.liste(ctx).filter { Nuage.peutLien(ctx, it) } }
    // Google Drive : celui de la synchronisation s'il y en a un, sinon le premier relie
    val drive = remember { possibles.filter { it.fournisseur(ctx).cle == "gdrive" }
        .let { l -> l.firstOrNull { it.id == Nuage.synchro(ctx)?.id } ?: l.firstOrNull() } }
    val autres = remember { possibles.filter { it.id != drive?.id } }
    var deplier by remember { mutableStateOf(false) }
    var occupe by remember { mutableStateOf<Nuage?>(null) }
    var erreur by remember { mutableStateOf<String?>(null) }
    fun lien(n: Nuage) {
        occupe = n; erreur = null
        portee.launch {
            try {
                val f = etat.doc.copieAJour(ctx)
                val lien = n.partagerParLien(ctx, etat.doc.nom, f.readBytes())
                envoyerLien(ctx, etat.doc.nom, lien)
                fermer()
            } catch (e: Exception) {
                Journal.ecrire("partage", "${n.fournisseur(ctx).nom} : lien impossible ($e)")
                erreur = e.message ?: e.toString()
            } finally { occupe = null }
        }
    }
    val libre = occupe == null
    AlertDialog(onDismissRequest = { if (libre) fermer() },
        title = { Text(stringResource(R.string.partager)) },
        text = {
            // defile si l'ecran est bas (telephone a l'horizontale) : rien d'ecrase
            Column(Modifier.verticalScroll(androidx.compose.foundation.rememberScrollState())) {
                Ligne("courriel", stringResource(R.string.partage_fichier), stringResource(R.string.partage_fichier_aide), libre) {
                    fermer(); portee.launch { partager(ctx, etat.doc) }
                }
                Spacer(Modifier.height(6.dp))
                if (drive != null) Ligne("lien", stringResource(R.string.lien_drive),
                    stringResource(R.string.partage_lien_aide, "Google Drive · " + drive.libelle(ctx)), libre) { lien(drive) }
                if (autres.isNotEmpty()) {
                    Spacer(Modifier.height(6.dp))
                    Ligne("lien", stringResource(R.string.lien_autre) + if (deplier) "  ▴" else "  ▾",
                        stringResource(R.string.lien_autre_aide), libre) { deplier = !deplier }
                    if (deplier) autres.forEach { c ->
                        Row(Modifier.fillMaxWidth().clickable(enabled = libre) { lien(c) }
                            .padding(start = 36.dp, top = 6.dp, bottom = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                            AvatarCompte(c, 0, 28.dp)
                            Spacer(Modifier.width(10.dp))
                            Column {
                                Text(c.fournisseur(ctx).nom, fontSize = 14.sp, fontWeight = FontWeight.SemiBold)
                                Text(c.libelle(ctx), fontSize = 12.sp, color = Color.Gray)
                            }
                        }
                    }
                }
                if (possibles.isEmpty()) Ligne("lien", stringResource(R.string.partage_lien),
                    if (Nuage.liste(ctx).isNotEmpty()) stringResource(R.string.lien_aucun_compte) else stringResource(R.string.partage_sans_compte), false) {}
                occupe?.let { n -> Row(Modifier.padding(top = 10.dp), verticalAlignment = Alignment.CenterVertically) {
                    CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp)
                    Spacer(Modifier.width(10.dp))
                    Text(stringResource(R.string.partage_envoi) + " (" + n.fournisseur(ctx).nom + ")", fontSize = 13.sp)
                } }
                erreur?.let { Text(it, color = ROUGE, fontSize = 13.sp, modifier = Modifier.padding(top = 8.dp)) }
            }
        },
        confirmButton = {},
        dismissButton = { TextButton(onClick = fermer, enabled = libre) { Text(stringResource(R.string.annuler)) } })
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
