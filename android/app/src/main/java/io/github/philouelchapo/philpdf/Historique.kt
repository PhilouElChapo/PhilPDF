package io.github.philouelchapo.philpdf

import android.content.Context
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.launch

/** Noms des etapes d'annulation (ecrits dans le journal du PDF en francais) montres dans la langue du telephone. */
object Historique {
    private val NOMS = mapOf(
        "Alleger" to R.string.op_alleger,
        "Annoter" to R.string.op_annoter,
        "Bouton" to R.string.op_bouton,
        "Changer le marquage" to R.string.op_changer_le_marquage,
        "Combiner" to R.string.op_combiner,
        "Creer des champs" to R.string.op_creer_des_champs,
        "Deplacer des pages" to R.string.op_deplacer_des_pages,
        "Dessin" to R.string.op_dessin,
        "Déplacer" to R.string.op_deplacer,
        "Effacer" to R.string.op_effacer,
        "Forme" to R.string.op_forme,
        "Gomme" to R.string.op_gomme,
        "Image" to R.string.op_image,
        "Miroir" to R.string.op_miroir,
        "Modifier l'annotation" to R.string.op_modifier_l_annotation,
        "Note" to R.string.op_note,
        "Ordre de tabulation" to R.string.op_ordre_de_tabulation,
        "Page blanche" to R.string.op_page_blanche,
        "Parapher" to R.string.op_parapher,
        "Pivoter" to R.string.op_pivoter,
        "Propriétés du champ" to R.string.op_proprietes_du_champ,
        "Reconnaître le texte" to R.string.op_reconnaitre_le_texte,
        "Remplacer l'image" to R.string.op_remplacer_l_image,
        "Remplir" to R.string.op_remplir,
        "Renommer un champ" to R.string.op_renommer_un_champ,
        "Réinitialiser le formulaire" to R.string.op_reinitialiser_le_formulaire,
        "Réparation" to R.string.op_reparation,
        "Signature" to R.string.op_signature,
        "Supprimer des pages" to R.string.op_supprimer_des_pages,
        "Supprimer l'annotation" to R.string.op_supprimer_l_annotation,
        "Supprimer l'image" to R.string.op_supprimer_l_image,
        "Supprimer un champ" to R.string.op_supprimer_un_champ,
        "Taille" to R.string.op_taille,
        "Tampon" to R.string.op_tampon,
        "Modifier le texte" to R.string.op_modifier_le_texte)

    fun libelle(ctx: Context, nom: String?): String =
        nom?.let { NOMS[it] }?.let { ctx.getString(it) } ?: nom?.takeIf { it.isNotBlank() } ?: ctx.getString(R.string.op_autre)
}

/**
 * Bouton Annuler ou Retablir : un toucher annule (retablit) la derniere etape et dit laquelle ; un appui long montre
 * la liste des modifications pour revenir d'un coup a l'une d'elles.
 */
@OptIn(androidx.compose.foundation.ExperimentalFoundationApi::class)
@androidx.compose.runtime.Composable
internal fun BoutonHistorique(etat: EtatLecteur, retablir: Boolean) {
    val ctx = androidx.compose.ui.platform.LocalContext.current
    val portee = androidx.compose.runtime.rememberCoroutineScope()
    val d = etat.doc
    val actif = if (retablir) d.peutRetablir else d.peutAnnuler
    var menu by androidx.compose.runtime.remember { androidx.compose.runtime.mutableStateOf(false) }
    val aide = ctx.getString(if (retablir) R.string.retablir else R.string.annuler_action)
    androidx.compose.foundation.layout.Box(
        androidx.compose.ui.Modifier.size(48.dp)
            .combinedClickable(enabled = actif, onClickLabel = aide, onClick = {
                portee.launch {
                    val nom = if (retablir) d.retablir() else d.annuler()
                    if (nom != null) etat.message = ctx.getString(if (retablir) R.string.retabli_fait else R.string.annule_fait,
                        Historique.libelle(ctx, nom))
                }
            }, onLongClick = { menu = true }),
        contentAlignment = androidx.compose.ui.Alignment.Center) {
        androidx.compose.material3.Icon(Icones.get(if (retablir) "retablir" else "annuler",
            if (actif) androidx.compose.ui.graphics.Color(0xFF333333) else androidx.compose.ui.graphics.Color(0xFFBBBBBB)),
            aide, tint = androidx.compose.ui.graphics.Color.Unspecified)
        if (menu) MenuHistorique(etat) { menu = false }
    }
}

/** Liste des modifications : celles a retablir (grisees, en haut), le document actuel, celles a annuler. */
@androidx.compose.runtime.Composable
internal fun MenuHistorique(etat: EtatLecteur, fermer: () -> Unit) {
    val ctx = androidx.compose.ui.platform.LocalContext.current
    val portee = androidx.compose.runtime.rememberCoroutineScope()
    val d = etat.doc
    val e by androidx.compose.runtime.produceState<DocumentPdf.Etapes?>(null, d.version) { value = d.etapes() }
    androidx.compose.material3.DropdownMenu(expanded = true, onDismissRequest = fermer,
        modifier = androidx.compose.ui.Modifier.heightIn(max = 420.dp)) {
        val et = e ?: return@DropdownMenu
        androidx.compose.material3.Text(ctx.getString(if (et.annulables.isEmpty() && et.retablissables.isEmpty())
            R.string.historique_vide else R.string.historique_titre),
            androidx.compose.ui.Modifier.padding(horizontal = 14.dp, vertical = 6.dp), fontSize = 12.sp,
            color = androidx.compose.ui.graphics.Color.Gray)
        // a retablir : la plus lointaine en haut
        et.retablissables.withIndex().reversed().forEach { (j, nom) ->
            androidx.compose.material3.DropdownMenuItem(
                text = { androidx.compose.material3.Text(ctx.getString(R.string.retablir_etape, Historique.libelle(ctx, nom)),
                    color = androidx.compose.ui.graphics.Color(0xFF888888)) },
                leadingIcon = { androidx.compose.material3.Icon(Icones.get("retablir", androidx.compose.ui.graphics.Color(0xFF888888)), null,
                    tint = androidx.compose.ui.graphics.Color.Unspecified) },
                onClick = { fermer(); portee.launch {
                    val n = d.retablir(j + 1)
                    if (n != null) etat.message = ctx.getString(R.string.retabli_fait, Historique.libelle(ctx, n))
                } })
        }
        if (et.annulables.isNotEmpty() || et.retablissables.isNotEmpty())
            androidx.compose.material3.Text(ctx.getString(R.string.historique_maintenant),
                androidx.compose.ui.Modifier.padding(horizontal = 14.dp, vertical = 4.dp), fontSize = 12.sp,
                fontWeight = androidx.compose.ui.text.font.FontWeight.SemiBold)
        et.annulables.forEachIndexed { i, nom ->
            androidx.compose.material3.DropdownMenuItem(
                text = { androidx.compose.material3.Text(ctx.getString(R.string.annuler_etape, Historique.libelle(ctx, nom))) },
                leadingIcon = { androidx.compose.material3.Icon(Icones.get("annuler"), null, tint = androidx.compose.ui.graphics.Color.Unspecified) },
                onClick = { fermer(); portee.launch {
                    val n = d.annuler(i + 1)
                    if (n != null) etat.message = ctx.getString(R.string.annule_fait, Historique.libelle(ctx, n))
                } })
        }
    }
}
