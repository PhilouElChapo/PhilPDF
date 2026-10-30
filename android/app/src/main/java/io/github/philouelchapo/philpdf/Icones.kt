package io.github.philouelchapo.philpdf

// Fichier genere par outils_dev/icones_android.py a partir de app/icones.py (icones de PhilPDF Windows).
// Ne pas modifier a la main : relancer le script.

import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.graphics.vector.PathParser
import androidx.compose.ui.unit.dp

object Icones {
    val TRAITS: Map<String, List<String>> = mapOf(
        "ouvrir" to listOf("M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"),
        "creer" to listOf("M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z", "M14 2v6h6", "M12 18v-6M9 15h6"),
        "combiner" to listOf("M10.0 8.0h8.0a2.0 2.0 0 0 1 2.0 2.0v10.0a2.0 2.0 0 0 1 -2.0 2.0h-8.0a2.0 2.0 0 0 1 -2.0 -2.0v-10.0a2.0 2.0 0 0 1 2.0 -2.0z", "M4 16V4a2 2 0 0 1 2-2h10"),
        "organiser" to listOf("M4.0 3.0h5.0a1.0 1.0 0 0 1 1.0 1.0v7.0a1.0 1.0 0 0 1 -1.0 1.0h-5.0a1.0 1.0 0 0 1 -1.0 -1.0v-7.0a1.0 1.0 0 0 1 1.0 -1.0z", "M15.0 3.0h5.0a1.0 1.0 0 0 1 1.0 1.0v3.0a1.0 1.0 0 0 1 -1.0 1.0h-5.0a1.0 1.0 0 0 1 -1.0 -1.0v-3.0a1.0 1.0 0 0 1 1.0 -1.0z", "M15.0 12.0h5.0a1.0 1.0 0 0 1 1.0 1.0v7.0a1.0 1.0 0 0 1 -1.0 1.0h-5.0a1.0 1.0 0 0 1 -1.0 -1.0v-7.0a1.0 1.0 0 0 1 1.0 -1.0z", "M4.0 16.0h5.0a1.0 1.0 0 0 1 1.0 1.0v3.0a1.0 1.0 0 0 1 -1.0 1.0h-5.0a1.0 1.0 0 0 1 -1.0 -1.0v-3.0a1.0 1.0 0 0 1 1.0 -1.0z"),
        "exporter" to listOf("M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z", "M14 2v6h6", "M8 15h8M13 12l3 3-3 3"),
        "imprimer" to listOf("M6 9V2h12v7", "M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2", "M6.0 14.0h12.0v8.0h-12.0z"),
        "modifier" to listOf("M12 20h9", "M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"),
        "remplacer" to listOf("M4.0 10.0a6.0 6.0 0 1 0 12.0 0a6.0 6.0 0 1 0 -12.0 0", "M20 20l-5.6-5.6", "M8 10h4"),
        "entete" to listOf("M6.0 3.0h12.0a2.0 2.0 0 0 1 2.0 2.0v14.0a2.0 2.0 0 0 1 -2.0 2.0h-12.0a2.0 2.0 0 0 1 -2.0 -2.0v-14.0a2.0 2.0 0 0 1 2.0 -2.0z", "M4 8h16M4 16h16"),
        "filigrane" to listOf("M12 2.7l5.7 5.7a8 8 0 1 1-11.4 0z"),
        "carnet" to listOf("M5 3h12a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5z", "M5 3v18", "M9.5 10.0a2.5 2.5 0 1 0 5.0 0a2.5 2.5 0 1 0 -5.0 0", "M8.5 16c.8-1.8 2-2.6 3.5-2.6s2.7.8 3.5 2.6", "M19 7h2M19 12h2M19 17h2"),
        "courriel" to listOf("M4.0 4.0h16.0a2.0 2.0 0 0 1 2.0 2.0v12.0a2.0 2.0 0 0 1 -2.0 2.0h-16.0a2.0 2.0 0 0 1 -2.0 -2.0v-12.0a2.0 2.0 0 0 1 2.0 -2.0z", "M22 6l-10 7L2 6"),
        "liste_fichiers" to listOf("M8 6h13M8 12h13M8 18h13", "M3 6h.01M3 12h.01M3 18h.01"),
        "fractionner" to listOf("M3.0 6.0a3.0 3.0 0 1 0 6.0 0a3.0 3.0 0 1 0 -6.0 0", "M3.0 18.0a3.0 3.0 0 1 0 6.0 0a3.0 3.0 0 1 0 -6.0 0", "M20 4L8.1 15.9M14.5 14.5L20 20M8.1 8.1L12 12"),
        "paraphe" to listOf("M4 15c2-6 4-9 5-9s-1 9 1 9 2-5 4-5 1 4 3 4", "M14 20h7", "M3 20h8"),
        "commentaire" to listOf("M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z", "M8 9h8M8 13h5"),
        "tampon" to listOf("M5 22h14", "M19.3 13.7A2.5 2.5 0 0 0 17.5 13h-11A2.5 2.5 0 0 0 4 15.5V17a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-1.5c0-.7-.3-1.3-.7-1.8z", "M14 13V8.5C14 7 15 7 15 5a3 3 0 0 0-6 0c0 2 1 2 1 3.5V13"),
        "signer" to listOf("M3 17c3-3 4-9 6-9s1 7 3 7 3-4 5-4 2 2 4 2", "M3 21h18"),
        "certificat" to listOf("M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z", "M9 12l2 2 4-4"),
        "formulaire" to listOf("M9.0 2.0h6.0a1.0 1.0 0 0 1 1.0 1.0v2.0a1.0 1.0 0 0 1 -1.0 1.0h-6.0a1.0 1.0 0 0 1 -1.0 -1.0v-2.0a1.0 1.0 0 0 1 1.0 -1.0z", "M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2", "M9 12h6M9 16h6"),
        "champ_signature" to listOf("M5.0 7.0h14.0a2.0 2.0 0 0 1 2.0 2.0v6.0a2.0 2.0 0 0 1 -2.0 2.0h-14.0a2.0 2.0 0 0 1 -2.0 -2.0v-6.0a2.0 2.0 0 0 1 2.0 -2.0z", "M6 14c1.5-1.5 2-3 3-3s.5 2 1.5 2 1.5-1 2.5-1", "M15 14h3"),
        "numeriser" to listOf("M3 7V5a2 2 0 0 1 2-2h2M17 3h2a2 2 0 0 1 2 2v2M21 17v2a2 2 0 0 1-2 2h-2M7 21H5a2 2 0 0 1-2-2v-2", "M7 12h10"),
        "ocr" to listOf("M3 7V5a2 2 0 0 1 2-2h2M17 3h2a2 2 0 0 1 2 2v2M21 17v2a2 2 0 0 1-2 2h-2M7 21H5a2 2 0 0 1-2-2v-2", "M7 8h8M7 12h10M7 16h6"),
        "nettoyer" to listOf("M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z", "M19 3v4M17 5h4"),
        "alleger" to listOf("M8 3v3a2 2 0 0 1-2 2H3M21 8h-3a2 2 0 0 1-2-2V3M3 16h3a2 2 0 0 1 2 2v3M16 21v-3a2 2 0 0 1 2-2h3"),
        "motdepasse" to listOf("M6.0 11.0h12.0a2.0 2.0 0 0 1 2.0 2.0v6.0a2.0 2.0 0 0 1 -2.0 2.0h-12.0a2.0 2.0 0 0 1 -2.0 -2.0v-6.0a2.0 2.0 0 0 1 2.0 -2.0z", "M8 11V7a4 4 0 0 1 8 0v4"),
        "image" to listOf("M5.0 5.0h14.0a2.0 2.0 0 0 1 2.0 2.0v10.0a2.0 2.0 0 0 1 -2.0 2.0h-14.0a2.0 2.0 0 0 1 -2.0 -2.0v-10.0a2.0 2.0 0 0 1 2.0 -2.0z", "M7.4 10.0a1.6 1.6 0 1 0 3.2 0a1.6 1.6 0 1 0 -3.2 0", "M4 17l5-5 4 4 3-3 4 4"),
        "excel" to listOf("M6.0 3.0h12.0a2.0 2.0 0 0 1 2.0 2.0v14.0a2.0 2.0 0 0 1 -2.0 2.0h-12.0a2.0 2.0 0 0 1 -2.0 -2.0v-14.0a2.0 2.0 0 0 1 2.0 -2.0z", "M4 9h16M4 15h16M10 3v18"),
        "mesure" to listOf("M3 17 17 3l4 4L7 21z", "M7 13l2 2M10 10l2 2M13 7l2 2"),
        "biffer" to listOf("M4 7h16M4 17h10", "M5.0 10.0h14.0a1.0 1.0 0 0 1 1.0 1.0v2.0a1.0 1.0 0 0 1 -1.0 1.0h-14.0a1.0 1.0 0 0 1 -1.0 -1.0v-2.0a1.0 1.0 0 0 1 1.0 -1.0z"),
        "archiver" to listOf("M3.0 3.0h18.0a1.0 1.0 0 0 1 1.0 1.0v3.0a1.0 1.0 0 0 1 -1.0 1.0h-18.0a1.0 1.0 0 0 1 -1.0 -1.0v-3.0a1.0 1.0 0 0 1 1.0 -1.0z", "M4 8v11a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8M10 12h4"),
        "comparer_ia" to listOf("M3.0 7.0h5.0a1.0 1.0 0 0 1 1.0 1.0v12.0a1.0 1.0 0 0 1 -1.0 1.0h-5.0a1.0 1.0 0 0 1 -1.0 -1.0v-12.0a1.0 1.0 0 0 1 1.0 -1.0z", "M13.0 7.0h5.0a1.0 1.0 0 0 1 1.0 1.0v12.0a1.0 1.0 0 0 1 -1.0 1.0h-5.0a1.0 1.0 0 0 1 -1.0 -1.0v-12.0a1.0 1.0 0 0 1 1.0 -1.0z", "M9 13h3", "M19 1.5l1 2.3 2.3 1-2.3 1-1 2.3-1-2.3-2.3-1 2.3-1z"),
        "comparer" to listOf("M4.0 4.0h5.0a1.0 1.0 0 0 1 1.0 1.0v14.0a1.0 1.0 0 0 1 -1.0 1.0h-5.0a1.0 1.0 0 0 1 -1.0 -1.0v-14.0a1.0 1.0 0 0 1 1.0 -1.0z", "M15.0 4.0h5.0a1.0 1.0 0 0 1 1.0 1.0v14.0a1.0 1.0 0 0 1 -1.0 1.0h-5.0a1.0 1.0 0 0 1 -1.0 -1.0v-14.0a1.0 1.0 0 0 1 1.0 -1.0z", "M10 10h4M12 8l2 2-2 2"),
        "lot" to listOf("M12 2l10 5-10 5L2 7z", "M2 12l10 5 10-5M2 17l10 5 10-5"),
        "ia" to listOf("M4 6h9M4 12h7M4 18h5", "M18 8l1.2 2.8L22 12l-2.8 1.2L18 16l-1.2-2.8L14 12l2.8-1.2z"),
        "enregistrer" to listOf("M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z", "M17 21v-8H7v8M7 3v5h8"),
        "langue" to listOf("M4 5h9M8.5 3v2M6 5c0 4 3 7 6 8M11 5c-.5 4-3 7-7 9", "M13 21l4-9 4 9M14.5 18h5"),
        "rechercher" to listOf("M4.0 11.0a7.0 7.0 0 1 0 14.0 0a7.0 7.0 0 1 0 -14.0 0", "M21 21l-4.3-4.3"),
        "zoom_plus" to listOf("M4.0 11.0a7.0 7.0 0 1 0 14.0 0a7.0 7.0 0 1 0 -14.0 0", "M21 21l-4.3-4.3M8 11h6M11 8v6"),
        "zoom_moins" to listOf("M4.0 11.0a7.0 7.0 0 1 0 14.0 0a7.0 7.0 0 1 0 -14.0 0", "M21 21l-4.3-4.3M8 11h6"),
        "pivoter" to listOf("M21 12a9 9 0 1 1-3-6.7L21 8", "M21 3v5h-5"),
        "annuler" to listOf("M9 14L4 9l5-5", "M4 9h11a5 5 0 0 1 0 10h-3"),
        "surligner" to listOf("M9 11l-6 6v3h9l3-3", "M22 12l-4.6 4.6a2 2 0 0 1-2.8 0l-5.2-5.2a2 2 0 0 1 0-2.8L14 4"),
        "souligner" to listOf("M6 4v6a6 6 0 0 0 12 0V4", "M4 21h16"),
        "barrer" to listOf("M16 6a4 4 0 0 0-4-2c-3 0-4.5 1.6-4.5 3.5S9 10.5 12 11.5", "M4 12h16", "M8 18a4 4 0 0 0 4 2c3 0 4.5-1.6 4.5-3.5"),
        "copier" to listOf("M11.0 9.0h8.0a2.0 2.0 0 0 1 2.0 2.0v8.0a2.0 2.0 0 0 1 -2.0 2.0h-8.0a2.0 2.0 0 0 1 -2.0 -2.0v-8.0a2.0 2.0 0 0 1 2.0 -2.0z", "M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"),
        "parametres" to listOf("M9.0 12.0a3.0 3.0 0 1 0 6.0 0a3.0 3.0 0 1 0 -6.0 0", "M12 2v3M12 19v3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M2 12h3M19 12h3M4.9 19.1L7 17M17 7l2.1-2.1"),
        "etoile" to listOf("M12 2l3 6.5 7 .8-5.2 4.8 1.4 7L12 17.6 5.8 21l1.4-7L2 9.3l7-.8z"),
        "plus" to listOf("M12 5v14M5 12h14"),
        "synchro" to listOf("M21 12a9 9 0 0 1-15.5 6.2L3 16", "M3 21v-5h5", "M3 12a9 9 0 0 1 15.5-6.2L21 8", "M21 3v5h-5"),
        "retablir" to listOf("M15 14l5-5-5-5", "M20 9H9a5 5 0 0 0 0 10h3"),
        "couper" to listOf("M3.0 6.0a3.0 3.0 0 1 0 6.0 0a3.0 3.0 0 1 0 -6.0 0", "M3.0 18.0a3.0 3.0 0 1 0 6.0 0a3.0 3.0 0 1 0 -6.0 0", "M20 4L8.1 15.9M14.5 14.5L20 20M8.1 8.1L12 12"),
        "coller" to listOf("M9.0 2.0h6.0a1.0 1.0 0 0 1 1.0 1.0v2.0a1.0 1.0 0 0 1 -1.0 1.0h-6.0a1.0 1.0 0 0 1 -1.0 -1.0v-2.0a1.0 1.0 0 0 1 1.0 -1.0z", "M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"),
        "supprimer" to listOf("M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6", "M10 11v6M14 11v6"),
        "tout" to listOf("M5 3h2M11 3h2M17 3h2M5 21h2M11 21h2M17 21h2M3 5v2M3 11v2M3 17v2M21 5v2M21 11v2M21 17v2", "M8.0 7.0h8.0a1.0 1.0 0 0 1 1.0 1.0v8.0a1.0 1.0 0 0 1 -1.0 1.0h-8.0a1.0 1.0 0 0 1 -1.0 -1.0v-8.0a1.0 1.0 0 0 1 1.0 -1.0z"),
        "aucun" to listOf("M5 3h2M11 3h2M17 3h2M5 21h2M11 21h2M17 21h2M3 5v2M3 11v2M3 17v2M21 5v2M21 11v2M21 17v2"),
        "recent" to listOf("M3.0 12.0a9.0 9.0 0 1 0 18.0 0a9.0 9.0 0 1 0 -18.0 0", "M12 7v5l3 2"),
        "enregistrer_sous" to listOf("M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v4", "M7 3v5h8", "M14 20l6-6 2 2-6 6h-2z"),
        "info" to listOf("M3.0 12.0a9.0 9.0 0 1 0 18.0 0a9.0 9.0 0 1 0 -18.0 0", "M12 11v6M12 7.5v.5"),
        "quitter" to listOf("M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4", "M16 17l5-5-5-5M21 12H9"),
        "fermer_doc" to listOf("M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z", "M14 2v6h6", "M9.5 12.5l5 5M14.5 12.5l-5 5"),
        "taille_reelle" to listOf("M5.0 3.0h14.0a2.0 2.0 0 0 1 2.0 2.0v14.0a2.0 2.0 0 0 1 -2.0 2.0h-14.0a2.0 2.0 0 0 1 -2.0 -2.0v-14.0a2.0 2.0 0 0 1 2.0 -2.0z", "M9 9v6M14 9l2 0v6"),
        "largeur" to listOf("M3 12h18M7 8l-4 4 4 4M17 8l4 4-4 4"),
        "plein_ecran" to listOf("M8 3H5a2 2 0 0 0-2 2v3M21 8V5a2 2 0 0 0-2-2h-3M3 16v3a2 2 0 0 0 2 2h3M16 21h3a2 2 0 0 0 2-2v-3"),
        "volet_gauche" to listOf("M5.0 3.0h14.0a2.0 2.0 0 0 1 2.0 2.0v14.0a2.0 2.0 0 0 1 -2.0 2.0h-14.0a2.0 2.0 0 0 1 -2.0 -2.0v-14.0a2.0 2.0 0 0 1 2.0 -2.0z", "M9 3v18"),
        "volet_droit" to listOf("M5.0 3.0h14.0a2.0 2.0 0 0 1 2.0 2.0v14.0a2.0 2.0 0 0 1 -2.0 2.0h-14.0a2.0 2.0 0 0 1 -2.0 -2.0v-14.0a2.0 2.0 0 0 1 2.0 -2.0z", "M15 3v18"),
        "barre" to listOf("M5.0 8.0h14.0a2.0 2.0 0 0 1 2.0 2.0v4.0a2.0 2.0 0 0 1 -2.0 2.0h-14.0a2.0 2.0 0 0 1 -2.0 -2.0v-4.0a2.0 2.0 0 0 1 2.0 -2.0z", "M7 12h2M11 12h2M15 12h2"),
        "onglet" to listOf("M3 7h7l2 2h9v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z", "M15 14h4M17 12l2 2-2 2"),
        "aide" to listOf("M3.0 12.0a9.0 9.0 0 1 0 18.0 0a9.0 9.0 0 1 0 -18.0 0", "M9.5 9a2.5 2.5 0 1 1 3.5 2.3c-.7.3-1 .9-1 1.7M12 17v.5"),
        "clavier" to listOf("M4.0 6.0h16.0a2.0 2.0 0 0 1 2.0 2.0v8.0a2.0 2.0 0 0 1 -2.0 2.0h-16.0a2.0 2.0 0 0 1 -2.0 -2.0v-8.0a2.0 2.0 0 0 1 2.0 -2.0z", "M6 10h.01M10 10h.01M14 10h.01M18 10h.01M7 14h10"),
        "mise_a_jour" to listOf("M12 3v12M7 10l5 5 5-5", "M5 21h14"),
        "premiere" to listOf("M17 18l-6-6 6-6M7 6v12"),
        "precedente" to listOf("M15 18l-6-6 6-6"),
        "suivante" to listOf("M9 18l6-6-6-6"),
        "derniere" to listOf("M7 18l6-6-6-6M17 6v12"),
        "oeil" to listOf("M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z", "M9.0 12.0a3.0 3.0 0 1 0 6.0 0a3.0 3.0 0 1 0 -6.0 0"),
        "oeil_barre" to listOf("M3 3l18 18", "M10.6 5.1A10 10 0 0 1 12 5c6.4 0 10 7 10 7a17 17 0 0 1-3.2 4.2M6.6 6.6C3.9 8.4 2 12 2 12s3.6 7 10 7a9.7 9.7 0 0 0 5.4-1.6", "M9.9 9.9a3 3 0 0 0 4.2 4.2"),
        "valide" to listOf("M2.0 12.0a10.0 10.0 0 1 0 20.0 0a10.0 10.0 0 1 0 -20.0 0", "M7.5 12.5l3 3 6-6.5"),
        "attention" to listOf("M10.3 3.9L1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z", "M12 9v4M12 17h.01"),
        "erreur" to listOf("M2.0 12.0a10.0 10.0 0 1 0 20.0 0a10.0 10.0 0 1 0 -20.0 0", "M15 9l-6 6M9 9l6 6"),
        "fermer" to listOf("M6 6l12 12M18 6L6 18"),
    )
    private val cache = HashMap<String, ImageVector>()

    /** Icone au trait (24 x 24, trait 1,8, extremites arrondies), comme sous Windows. */
    fun get(nom: String, couleur: Color = Color(0xFF333333)): ImageVector = cache.getOrPut(nom + couleur.value) {
        val b = ImageVector.Builder(name = nom, defaultWidth = 24.dp, defaultHeight = 24.dp, viewportWidth = 24f, viewportHeight = 24f)
        for (d in TRAITS[nom] ?: TRAITS.getValue("creer")) {
            b.addPath(PathParser().parsePathString(d).toNodes(), stroke = SolidColor(couleur), strokeLineWidth = 1.8f,
                strokeLineCap = StrokeCap.Round, strokeLineJoin = StrokeJoin.Round)
        }
        b.build()
    }
}
