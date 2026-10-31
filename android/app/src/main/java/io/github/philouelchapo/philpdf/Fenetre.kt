package io.github.philouelchapo.philpdf

import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxScope
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.runtime.Composable
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
