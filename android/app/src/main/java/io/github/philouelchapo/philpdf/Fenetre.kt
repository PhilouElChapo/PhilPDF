package io.github.philouelchapo.philpdf

import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxScope
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.runtime.remember
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties

/** Marges des barres d'Android (etat, retour/accueil) et du clavier, mesurees par l'activite (ou elles sont fiables). */
val LocalMarges = staticCompositionLocalOf { PaddingValues(0.dp) }

/**
 * Fenetre plein ecran de PhilPDF : elle s'arrete TOUJOURS au-dessus des boutons d'Android et du clavier, pour qu'aucun
 * bouton (Appliquer, barre d'actions) ne passe dessous. Toucher a cote ferme, comme une fenetre ordinaire.
 */
@Composable
fun Fenetre(fermer: () -> Unit, alignement: Alignment = Alignment.Center, contenu: @Composable BoxScope.() -> Unit) {
    val marges = LocalMarges.current
    Dialog(onDismissRequest = fermer,
        properties = DialogProperties(usePlatformDefaultWidth = false, decorFitsSystemWindows = false)) {
        Box(Modifier.fillMaxSize()
            .clickable(remember { MutableInteractionSource() }, null) { fermer() }
            .padding(marges), contentAlignment = alignement) {
            // le contenu ne transmet pas ses touches au fond (qui fermerait la fenetre)
            Box(Modifier.clickable(remember { MutableInteractionSource() }, null) {}) { contenu() }
        }
    }
}

/** Champ de mot de passe (ou de tout texte cache) : un oeil a droite montre ou cache ce qui est tape. Partout. */
@Composable
fun ChampSecret(valeur: String, changer: (String) -> Unit, libelle: String, modifier: Modifier = Modifier.fillMaxWidth(),
                erreur: Boolean = false, aide: (@Composable () -> Unit)? = null) {
    var voir by remember { mutableStateOf(false) }
    androidx.compose.material3.OutlinedTextField(valeur, changer, modifier,
        label = { androidx.compose.material3.Text(libelle) }, singleLine = true, isError = erreur, supportingText = aide,
        visualTransformation = if (voir) androidx.compose.ui.text.input.VisualTransformation.None
            else androidx.compose.ui.text.input.PasswordVisualTransformation(),
        keyboardOptions = androidx.compose.foundation.text.KeyboardOptions(keyboardType = androidx.compose.ui.text.input.KeyboardType.Password),
        trailingIcon = {
            androidx.compose.material3.IconButton(onClick = { voir = !voir }) {
                androidx.compose.material3.Icon(Icones.get(if (voir) "oeil_barre" else "oeil", androidx.compose.ui.graphics.Color(0xFF555555)),
                    androidx.compose.ui.res.stringResource(if (voir) R.string.mdp_cacher else R.string.mdp_voir))
            }
        })
}
