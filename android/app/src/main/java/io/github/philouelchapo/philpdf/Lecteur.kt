package io.github.philouelchapo.philpdf

import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.os.Bundle
import android.os.CancellationSignal
import android.os.ParcelFileDescriptor
import android.print.PageRange
import android.print.PrintAttributes
import android.print.PrintDocumentAdapter
import android.print.PrintDocumentInfo
import android.print.PrintManager
import androidx.activity.compose.BackHandler
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.ui.graphics.nativeCanvas
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.gestures.detectTransformGestures
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyListState
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawWithContent
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.input.nestedscroll.NestedScrollConnection
import androidx.compose.ui.input.nestedscroll.NestedScrollSource
import androidx.compose.ui.input.nestedscroll.nestedScroll
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.FileProvider
import kotlinx.coroutines.launch

/** Ce que montre le volet (tablette) ou le tiroir (telephone). */
enum class Volet { VIGNETTES, SIGNETS, COMMENTAIRES, RECHERCHE, ANNOTER, SIGNER, PLUS }

/** Etat partage du lecteur : page, zoom, recherche. */
class EtatLecteur(val doc: DocumentPdf, val liste: LazyListState) {
    var echelle by mutableFloatStateOf(1f)
    var decalage by mutableStateOf(Offset.Zero)
    var recherche by mutableStateOf("")
    var trouves by mutableStateOf<List<Trouve>>(emptyList())
    var cherche by mutableStateOf(false)
    val annot = ReglagesAnnot()
    var selection by mutableStateOf<InfoAnnot?>(null)       // annotation en cours de modification (appui long)
    var noteA by mutableStateOf<Pair<Int, com.artifex.mupdf.fitz.Point>?>(null)
    var demandeEnregistrer by mutableStateOf(false)
    var aPoser by mutableStateOf<APoser?>(null)            // signature, paraphe ou tampon choisi
    var champ by mutableStateOf<InfoChamp?>(null)           // champ de formulaire en cours de saisie
    var fantome by mutableStateOf<Pair<Int, Offset>?>(null) // apercu de ce qui va etre pose : page, centre en points
    /** Signature ou tampon pose en cours de deplacement (appui long > Deplacer) et decalage du doigt, en points. */
    var deplacement by mutableStateOf<InfoAnnot?>(null)
    var decalageDepl by mutableStateOf(Offset.Zero)
    /** Appui long > Changer : la prochaine signature ou le prochain tampon choisi prend sa place. */
    var remplacer by mutableStateOf<InfoAnnot?>(null)
    var ouvrirSigner by mutableStateOf(false)
    /** Modifier le texte : paragraphe touche (fenetre d'edition), et petit message a montrer. */
    var paragraphe by mutableStateOf<Paragraphe?>(null)
    var message by mutableStateOf<String?>(null)
    var organiser by mutableStateOf(false)                  // ecran « Organiser les pages »
    var ocr by mutableStateOf<Int?>(null)                   // reconnaissance du texte proposee (page de depart)
    var choixPartage by mutableStateOf(false)               // envoyer le fichier ou un lien
    var detecter by mutableStateOf(false)                   // creer un formulaire : champs reperes a choisir
    var champOptions by mutableStateOf<InfoChamp?>(null)    // appui long sur un champ : renommer, supprimer
    var signerAvec by mutableStateOf<Identite?>(null)       // signature numerique : certificat choisi
    var cadreSignature by mutableStateOf<Pair<Int, com.artifex.mupdf.fitz.Rect>?>(null)
    var verifierSignatures by mutableStateOf(false)
    var champSignature by mutableStateOf<String?>(null)     // champ de signature vide touche : signer dedans
    var nouvelleListe by mutableStateOf<Pair<Int, com.artifex.mupdf.fitz.Rect>?>(null)   // liste deroulante a remplir
    /** Portee du lecteur : une pose lancee ici va au bout meme quand l'apercu disparait de l'ecran. */
    var portee: kotlinx.coroutines.CoroutineScope? = null
    val page: Int get() = liste.firstVisibleItemIndex
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun Lecteur(doc: DocumentPdf, fermer: () -> Unit) {
    val ctx = LocalContext.current
    val etat = remember(doc) { EtatLecteur(doc, LazyListState()) }
    var quitter by remember { mutableStateOf(false) }
    var fermerApres by remember { mutableStateOf(false) }
    val portee = rememberCoroutineScope()
    etat.portee = portee
    val erreurEcriture = stringResource(R.string.enregistrement_impossible)
    val enregistre = stringResource(R.string.enregistre)
    fun ecrireVers(u: android.net.Uri, puisFermer: Boolean) {
        portee.launch {
            try {
                doc.enregistrer(ctx, u)
                Journal.ecrire("enregistrement", "${doc.nom} : enregistré (${if (u == doc.uri) "même fichier" else "autre nom"})")
                android.widget.Toast.makeText(ctx, enregistre, android.widget.Toast.LENGTH_SHORT).show()
                if (puisFermer) fermer()
            } catch (e: ErreurCompte) {       // copie gardee sur le telephone, mais pas renvoyee au compte
                Journal.ecrire("enregistrement", "${doc.nom} : renvoi au compte impossible (${e.message})")
                android.widget.Toast.makeText(ctx, e.message, android.widget.Toast.LENGTH_LONG).show()
            } catch (e: Exception) {
                Journal.ecrire("enregistrement", "${doc.nom} : écriture impossible ($e)")
                android.widget.Toast.makeText(ctx, erreurEcriture, android.widget.Toast.LENGTH_LONG).show()
            }
        }
    }
    val autreNom = androidx.activity.compose.rememberLauncherForActivityResult(
        androidx.activity.result.contract.ActivityResultContracts.CreateDocument("application/pdf")) { u ->
        if (u != null) ecrireVers(u, fermerApres)
    }
    // retour : si le document est modifie, on demande (rien ne se perd en silence)
    BackHandler { if (doc.modifie) quitter = true else fermer() }
    val fermerDemande = { if (doc.modifie) quitter = true else fermer() }
    var deverrouille by remember(doc) { mutableStateOf(!doc.besoinMotDePasse()) }
    var tailles by remember(doc) { mutableStateOf<List<Pair<Float, Float>>?>(null) }
    LaunchedEffect(doc, deverrouille) {
        if (deverrouille) {
            val t = doc.tailles()
            tailles = t
            Recents.ajouter(ctx, doc.uri, doc.nom, t.size)
            val p = PagesLues.lire(ctx, doc.uri.toString())        // on reprend la ou on s'etait arrete
            if (p in 1 until t.size) etat.liste.scrollToItem(p)
            Miniatures.fabriquer(ctx, doc)
        }
    }
    // pages ajoutees, retirees, deplacees ou pivotees (organiser, annuler) : leurs tailles sont relues
    LaunchedEffect(doc.pagesVersion) {
        if (deverrouille && doc.pagesVersion > 0) tailles = doc.tailles()
    }
    LaunchedEffect(etat.liste.firstVisibleItemIndex) { PagesLues.ecrire(ctx, doc.uri.toString(), etat.page) }

    val t = tailles
    when {
        !deverrouille -> Box(Modifier.fillMaxSize()) { DemandeMotDePasse(doc, { deverrouille = true }, fermer) }
        t == null -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { Text(stringResource(R.string.ouverture)) }
        else -> BoxWithConstraints(Modifier.fillMaxSize()) {
            // grand ecran (tablette, telephone a l'horizontale) : disposition Windows ; sinon : telephone
            if (maxWidth >= 720.dp) DispositionTablette(etat, t, fermerDemande) else DispositionTelephone(etat, t, fermerDemande)
        }
    }
    etat.selection?.let { FeuilleAnnotation(etat, it) { etat.selection = null } }
    etat.champ?.let { SaisieChamp(etat, it) { etat.champ = null } }
    etat.paragraphe?.let { p -> EditeurTexte(etat, p) { etat.paragraphe = null } }
    if (etat.choixPartage) ChoixPartage(etat) { etat.choixPartage = false }
    if (etat.detecter) DetectionChamps(etat) { etat.detecter = false }
    etat.cadreSignature?.let { (n, r) -> DialogueSigner(etat, n, r, etat.champSignature) {
        etat.cadreSignature = null; etat.champSignature = null; etat.annot.outil = Outil.MAIN } }
    etat.nouvelleListe?.let { (n, r) -> DialogueListe(etat, n, r) { etat.nouvelleListe = null } }
    if (etat.verifierSignatures) DialogueVerifier(etat) { etat.verifierSignatures = false }
    // PDF signe : on le dit a l'ouverture (valide, approuvee, modifie depuis...)
    LaunchedEffect(doc, deverrouille) {
        if (deverrouille) try {
            val l = doc.signatures(ctx)
            if (l.isNotEmpty()) etat.message = l.joinToString("\n") { s -> ctx.getString(R.string.sig_signe_par, s.nom) + " : " + etatSignature(ctx, s).first }
        } catch (_: Exception) {}
    }
    etat.champOptions?.let { c -> OptionsChamp(etat, c) { etat.champOptions = null } }
    if (etat.organiser && t != null) OrganiserPages(etat, t) { etat.organiser = false }
    etat.ocr?.let { n -> DialogueOcr(etat, n) { etat.ocr = null } }
    etat.message?.let { m ->
        val txt = if (m == "aucun_texte") stringResource(R.string.aucun_texte) else m
        LaunchedEffect(m) { android.widget.Toast.makeText(ctx, txt, android.widget.Toast.LENGTH_LONG).show(); etat.message = null }
    }
    etat.noteA?.let { (n, pt) -> DemandeNote({ etat.noteA = null }) { texte ->
        etat.noteA = null
        portee.launch { doc.note(n, pt, texte, etat.annot.couleur(Outil.NOTE).versPdf()) }
    } }
    // « Enregistrer » : toujours la question, meme fichier ou autre nom
    if (etat.demandeEnregistrer || quitter) {
        val q = quitter
        AlertDialog(onDismissRequest = { etat.demandeEnregistrer = false; quitter = false },
            title = { Text(stringResource(if (q) R.string.enregistrer_modifs else R.string.enregistrer)) },
            text = { Text(stringResource(R.string.ou_enregistrer, doc.nom)) },
            confirmButton = {
                Column(horizontalAlignment = Alignment.End) {
                    TextButton(onClick = { etat.demandeEnregistrer = false; quitter = false; ecrireVers(doc.uri, q) }) {
                        Text(stringResource(R.string.meme_fichier))
                    }
                    TextButton(onClick = {
                        etat.demandeEnregistrer = false; quitter = false; fermerApres = q
                        autreNom.launch(doc.nom.removeSuffix(".pdf").removeSuffix(".PDF") + " (modifié).pdf")
                    }) { Text(stringResource(R.string.autre_nom)) }
                    if (q) TextButton(onClick = { quitter = false; fermer() }) {
                        Text(stringResource(R.string.ne_pas_enregistrer), color = Color(0xFFC62828))
                    }
                }
            },
            dismissButton = { TextButton(onClick = { etat.demandeEnregistrer = false; quitter = false }) { Text(stringResource(R.string.annuler)) } })
    }
}

@Composable
private fun DemandeNote(fermer: () -> Unit, valider: (String) -> Unit) {
    var t by remember { mutableStateOf("") }
    AlertDialog(onDismissRequest = fermer, title = { Text(stringResource(R.string.outil_note)) },
        text = { OutlinedTextField(t, { t = it }, Modifier.fillMaxWidth(), minLines = 3) },
        confirmButton = { TextButton(onClick = { if (t.isNotBlank()) valider(t) else fermer() }) { Text(stringResource(R.string.ok)) } },
        dismissButton = { TextButton(onClick = fermer) { Text(stringResource(R.string.annuler)) } })
}

/** Annuler, retablir, enregistrer : dans la barre du haut (tablette et telephone). */
@Composable
internal fun BoutonsEdition(etat: EtatLecteur) {
    val portee = rememberCoroutineScope()
    val d = etat.doc
    IconButton(onClick = { portee.launch { d.annuler() } }, enabled = d.peutAnnuler) {
        Icon(Icones.get("annuler", if (d.peutAnnuler) Color(0xFF333333) else Color(0xFFBBBBBB)), stringResource(R.string.annuler_action))
    }
    IconButton(onClick = { portee.launch { d.retablir() } }, enabled = d.peutRetablir) {
        Icon(Icones.get("retablir", if (d.peutRetablir) Color(0xFF333333) else Color(0xFFBBBBBB)), stringResource(R.string.retablir))
    }
    IconButton(onClick = { etat.demandeEnregistrer = true }, enabled = d.modifie) {
        Icon(Icones.get("enregistrer", if (d.modifie) ROUGE else Color(0xFFBBBBBB)), stringResource(R.string.enregistrer))
    }
}

// ================================================================ tablette : barre d'outils + volets retractables
@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun DispositionTablette(etat: EtatLecteur, tailles: List<Pair<Float, Float>>, fermer: () -> Unit) {
    val ctx = LocalContext.current
    var gauche by remember { mutableStateOf<Volet?>(Volet.VIGNETTES) }
    var droite by remember { mutableStateOf<Volet?>(null) }
    LaunchedEffect(etat.ouvrirSigner) { if (etat.ouvrirSigner) { droite = Volet.SIGNER; etat.ouvrirSigner = false } }
    var allerA by remember { mutableStateOf(false) }
    val portee = rememberCoroutineScope()
    Column(Modifier.fillMaxSize().background(Color(0xFFF3F3F3))) {
        // barre du haut : nom, puis outils (passe a la ligne si la place manque)
        Row(Modifier.fillMaxWidth().background(Color.White).padding(horizontal = 4.dp, vertical = 2.dp),
            verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = fermer) { Icon(Icons.AutoMirrored.Filled.ArrowBack, stringResource(R.string.retour)) }
            Text(etat.doc.nom, Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis, fontWeight = FontWeight.SemiBold)
            FlowRow(horizontalArrangement = Arrangement.End) {
                BoutonsEdition(etat)
                Bouton("rechercher", stringResource(R.string.rechercher)) { droite = if (droite == Volet.RECHERCHE) null else Volet.RECHERCHE }
                Bouton("zoom_moins", stringResource(R.string.zoom_moins)) { etat.echelle = (etat.echelle / 1.25f).coerceAtLeast(1f); if (etat.echelle == 1f) etat.decalage = Offset.Zero }
                Bouton("zoom_plus", stringResource(R.string.zoom_plus)) { etat.echelle = (etat.echelle * 1.25f).coerceAtMost(5f) }
                Bouton("largeur", stringResource(R.string.ajuster)) { etat.echelle = 1f; etat.decalage = Offset.Zero }
                Bouton("suivante", stringResource(R.string.aller_page)) { allerA = true }
                Bouton("courriel", stringResource(R.string.partager)) { etat.choixPartage = true }
                Bouton("imprimer", stringResource(R.string.imprimer)) { portee.launch { imprimer(ctx, etat.doc) } }
            }
        }
        HorizontalDivider(color = Color(0xFFE2E2E2))
        Row(Modifier.weight(1f).fillMaxWidth()) {
            // volet gauche : replie, il reste une colonne d'icones (jamais disparu)
            Rail(listOf(Volet.VIGNETTES to "organiser", Volet.SIGNETS to "liste_fichiers", Volet.COMMENTAIRES to "commentaire"), gauche) {
                gauche = if (gauche == it) null else it
            }
            gauche?.let { v ->
                Box(Modifier.width(230.dp).fillMaxHeight().background(Color(0xFFF7F7F7))) {
                    ContenuVolet(v, etat, tailles) { n -> portee.launch { etat.liste.scrollToItem(n) } }
                }
                VerticalDivider(color = Color(0xFFE2E2E2))
            }
            Box(Modifier.weight(1f).fillMaxHeight()) {
                Pages(etat, tailles, Modifier.fillMaxSize())
                IndicateurPage(etat, tailles.size, Modifier.align(Alignment.BottomEnd))
            }
            droite?.let { v ->
                VerticalDivider(color = Color(0xFFE2E2E2))
                Box(Modifier.width(280.dp).fillMaxHeight().background(Color(0xFFF7F7F7))) {
                    ContenuVolet(v, etat, tailles) { n -> portee.launch { etat.liste.scrollToItem(n) } }
                }
            }
            Rail(listOf(Volet.RECHERCHE to "rechercher", Volet.ANNOTER to "surligner", Volet.SIGNER to "signer", Volet.PLUS to "info"), droite) {
                droite = if (droite == it) null else it
            }
        }
    }
    if (allerA) AllerALaPage(tailles.size, { allerA = false }) { n -> portee.launch { etat.liste.scrollToItem(n) } }
}

@Composable
private fun Rail(elements: List<Pair<Volet, String>>, actif: Volet?, choisir: (Volet) -> Unit) {
    Column(Modifier.width(52.dp).fillMaxHeight().background(Color.White).padding(top = 6.dp),
        horizontalAlignment = Alignment.CenterHorizontally) {
        elements.forEach { (v, icone) ->
            val oui = v == actif
            IconButton(onClick = { choisir(v) }, modifier = Modifier.background(if (oui) Color(0xFFFCEBEC) else Color.Transparent, RoundedCornerShape(8.dp))) {
                Icon(Icones.get(icone, if (oui) ROUGE else Color(0xFF444444)), libelleVolet(v))
            }
            Spacer(Modifier.height(4.dp))
        }
    }
}

@Composable
private fun Bouton(icone: String, aide: String, action: () -> Unit) {
    IconButton(onClick = action) { Icon(Icones.get(icone), aide) }
}

@Composable
private fun libelleVolet(v: Volet): String = stringResource(when (v) {
    Volet.VIGNETTES -> R.string.pages_volet
    Volet.SIGNETS -> R.string.signets
    Volet.COMMENTAIRES -> R.string.commentaires
    Volet.RECHERCHE -> R.string.rechercher
    Volet.ANNOTER -> R.string.annoter
    Volet.SIGNER -> R.string.signer
    Volet.PLUS -> R.string.plus_court
})

// ================================================================ telephone : barre du bas + tiroirs
@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun DispositionTelephone(etat: EtatLecteur, tailles: List<Pair<Float, Float>>, fermer: () -> Unit) {
    var barres by remember { mutableStateOf(true) }
    var tiroir by remember { mutableStateOf<Volet?>(null) }
    LaunchedEffect(etat.ouvrirSigner) { if (etat.ouvrirSigner) { tiroir = Volet.SIGNER; etat.ouvrirSigner = false } }
    val portee = rememberCoroutineScope()
    // en faisant defiler vers le bas, les barres se cachent ; vers le haut, elles reviennent
    val defilement = remember {
        object : NestedScrollConnection {
            override fun onPreScroll(available: Offset, source: NestedScrollSource): Offset {
                if (available.y < -8) barres = false else if (available.y > 8) barres = true
                return Offset.Zero
            }
        }
    }
    Box(Modifier.fillMaxSize().background(Color(0xFFE6E6E6))) {
        Pages(etat, tailles, Modifier.fillMaxSize().nestedScroll(defilement), auToucher = { barres = !barres })
        AnimatedVisibility(barres, Modifier.align(Alignment.TopCenter)) {
            Row(Modifier.fillMaxWidth().background(Color.White).padding(horizontal = 4.dp, vertical = 2.dp),
                verticalAlignment = Alignment.CenterVertically) {
                IconButton(onClick = fermer) { Icon(Icons.AutoMirrored.Filled.ArrowBack, stringResource(R.string.retour)) }
                Text(etat.doc.nom, Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis, fontWeight = FontWeight.SemiBold)
                BoutonsEdition(etat)
            }
        }
        // outil en cours (dessin, surlignage...) : petite barre en haut, toujours visible, pour finir
        if (etat.annot.outil != Outil.MAIN) {
            Row(Modifier.align(Alignment.TopCenter).padding(top = if (barres) 56.dp else 8.dp)
                .background(Color(0xEE2B2B2B), RoundedCornerShape(20.dp)).padding(horizontal = 10.dp, vertical = 2.dp),
                verticalAlignment = Alignment.CenterVertically) {
                Icon(Icones.get(etat.annot.outil.icone, Color.White), null)
                Spacer(Modifier.width(6.dp))
                Text(stringResource(etat.annot.outil.texte), color = Color.White, fontSize = 13.sp)
                TextButton(onClick = { tiroir = Volet.ANNOTER }) { Text(stringResource(R.string.reglages), color = Color(0xFF9CC3FF)) }
                TextButton(onClick = { etat.annot.outil = Outil.MAIN; etat.fantome = null; etat.aPoser = null }) { Text(stringResource(R.string.termine), color = Color.White) }
            }
        }
        IndicateurPage(etat, tailles.size, Modifier.align(Alignment.BottomEnd).padding(bottom = if (barres) 72.dp else 0.dp))
        AnimatedVisibility(barres, Modifier.align(Alignment.BottomCenter)) {
            NavigationBar(containerColor = Color.White, tonalElevation = 2.dp) {
                listOf(Volet.VIGNETTES to "organiser", Volet.RECHERCHE to "rechercher", Volet.ANNOTER to "surligner",
                    Volet.SIGNER to "signer", Volet.PLUS to "plus").forEach { (v, icone) ->
                    NavigationBarItem(selected = tiroir == v, onClick = { tiroir = v },
                        icon = { Icon(Icones.get(icone, if (tiroir == v) ROUGE else Color(0xFF444444)), null) },
                        label = { TexteAjuste(libelleVolet(v), 11.sp) })
                }
            }
        }
    }
    tiroir?.let { v ->
        ModalBottomSheet(onDismissRequest = { tiroir = null }, containerColor = Color(0xFFF7F7F7)) {
            Box(Modifier.fillMaxWidth().heightIn(min = 200.dp, max = 560.dp)) {
                if (v == Volet.ANNOTER) PanneauAnnoter(etat) { if (etat.annot.outil != Outil.MAIN) tiroir = null }
                else if (v == Volet.SIGNER) PanneauSigner(etat, tailles) { tiroir = null }
                else ContenuVolet(v, etat, tailles) { n ->
                    portee.launch { etat.liste.scrollToItem(n) }
                    if (v != Volet.RECHERCHE) tiroir = null
                }
            }
        }
    }
}

// ================================================================ contenu des volets / tiroirs
@Composable
private fun ContenuVolet(v: Volet, etat: EtatLecteur, tailles: List<Pair<Float, Float>>, aller: (Int) -> Unit) {
    val ctx = LocalContext.current
    val portee = rememberCoroutineScope()
    when (v) {
        Volet.VIGNETTES -> Vignettes(etat, tailles, aller)
        Volet.SIGNETS -> Signets(etat.doc, aller)
        Volet.COMMENTAIRES -> Commentaires(etat.doc, aller)
        Volet.RECHERCHE -> Recherche(etat, aller)
        Volet.ANNOTER -> PanneauAnnoter(etat)
        Volet.SIGNER -> PanneauSigner(etat, tailles)
        Volet.PLUS -> {
            var allerA by remember { mutableStateOf(false) }
            var signets by remember { mutableStateOf(false) }
            var comms by remember { mutableStateOf(false) }
            when {
                signets -> Signets(etat.doc, aller)
                comms -> Commentaires(etat.doc, aller)
                else -> Column(Modifier.padding(8.dp)) {
                    LigneAction("suivante", stringResource(R.string.aller_page)) { allerA = true }
                    LigneAction("liste_fichiers", stringResource(R.string.signets)) { signets = true }
                    LigneAction("commentaire", stringResource(R.string.commentaires)) { comms = true }
                    if (etat.doc.modifiable) LigneAction("organiser", stringResource(R.string.organiser_pages)) { etat.organiser = true }
                    if (etat.doc.modifiable) LigneAction("ocr", stringResource(R.string.ocr_titre_menu)) { etat.ocr = etat.page }
                    LigneAction("certificat", stringResource(R.string.sig_verifier)) { etat.verifierSignatures = true }
                    LigneAction("enregistrer", stringResource(R.string.enregistrer)) { etat.demandeEnregistrer = true }
                    LigneAction("courriel", stringResource(R.string.partager)) { etat.choixPartage = true }
                    LigneAction("imprimer", stringResource(R.string.imprimer)) { portee.launch { imprimer(ctx, etat.doc) } }
                    LigneAction("largeur", stringResource(R.string.ajuster)) { etat.echelle = 1f; etat.decalage = Offset.Zero }
                    Spacer(Modifier.height(8.dp))
                    Text(stringResource(R.string.infos_doc, etat.doc.nom, tailles.size), Modifier.padding(8.dp),
                        fontSize = 12.sp, color = Color.Gray)
                }
            }
            if (allerA) AllerALaPage(tailles.size, { allerA = false }, aller)
        }
    }
}

@Composable
private fun LigneAction(icone: String, texte: String, action: () -> Unit) {
    Row(Modifier.fillMaxWidth().clickable(onClick = action).padding(horizontal = 12.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically) {
        Icon(Icones.get(icone), null)
        Spacer(Modifier.width(14.dp))
        Text(texte)
    }
}

@Composable
private fun Bientot(titre: String, texte: String, icones: List<String>) {
    Column(Modifier.padding(16.dp)) {
        Text(titre, fontWeight = FontWeight.SemiBold)
        Spacer(Modifier.height(10.dp))
        Row { icones.forEach { Icon(Icones.get(it, Color(0xFFAAAAAA)), null, Modifier.padding(end = 12.dp)) } }
        Spacer(Modifier.height(10.dp))
        Text(texte, fontSize = 13.sp, color = Color.Gray)
    }
}

@Composable
private fun Vignettes(etat: EtatLecteur, tailles: List<Pair<Float, Float>>, aller: (Int) -> Unit) {
    val largeurPx = with(LocalDensity.current) { 110.dp.toPx().toInt() }
    val courante = etat.page
    LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(12.dp), verticalArrangement = Arrangement.spacedBy(10.dp),
        horizontalAlignment = Alignment.CenterHorizontally) {
        if (etat.doc.modifiable) item {
            OutlinedButton(onClick = { etat.organiser = true }, Modifier.fillMaxWidth()) {
                Icon(Icones.get("organiser", ROUGE), null)
                Spacer(Modifier.width(8.dp))
                TexteAjuste(stringResource(R.string.organiser_pages), 14.sp)
            }
        }
        itemsIndexed(tailles) { n, (w, h) ->
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                ImagePage(etat, n, largeurPx, w, h, Modifier.width(110.dp)
                    .border(if (n == courante) 2.dp else 1.dp, if (n == courante) ROUGE else Color(0xFFCFCFCF))
                    .clickable { aller(n) }, marques = false)
                Text("${n + 1}", fontSize = 12.sp, color = Color.Gray)
            }
        }
    }
}

@Composable
private fun Signets(doc: DocumentPdf, aller: (Int) -> Unit) {
    val liste by produceState<List<Signet>?>(null, doc) { value = doc.signets() }
    val l = liste
    when {
        l == null -> Text(stringResource(R.string.ouverture), Modifier.padding(16.dp))
        l.isEmpty() -> Text(stringResource(R.string.aucun_signet), Modifier.padding(16.dp), color = Color.Gray)
        else -> LazyColumn(Modifier.fillMaxSize()) {
            items(l) { s ->
                Row(Modifier.fillMaxWidth().clickable(enabled = s.page >= 0) { aller(s.page) }
                    .padding(start = (12 + 14 * s.profondeur).dp, end = 12.dp, top = 10.dp, bottom = 10.dp)) {
                    Text(s.titre, Modifier.weight(1f), fontSize = 14.sp)
                    if (s.page >= 0) Text("${s.page + 1}", fontSize = 12.sp, color = Color.Gray)
                }
            }
        }
    }
}

@Composable
private fun Commentaires(doc: DocumentPdf, aller: (Int) -> Unit) {
    val liste by produceState<List<Commentaire>?>(null, doc) { value = doc.commentaires() }
    val l = liste
    when {
        l == null -> Text(stringResource(R.string.ouverture), Modifier.padding(16.dp))
        l.isEmpty() -> Text(stringResource(R.string.aucun_commentaire), Modifier.padding(16.dp), color = Color.Gray)
        else -> LazyColumn(Modifier.fillMaxSize()) {
            items(l) { c ->
                Column(Modifier.fillMaxWidth().clickable { aller(c.page) }.padding(horizontal = 12.dp, vertical = 8.dp)) {
                    Text(stringResource(R.string.page_n, c.page + 1) + if (c.auteur.isNotBlank()) " · " + c.auteur else "",
                        fontSize = 12.sp, color = Color.Gray)
                    Text(c.texte.ifBlank { "—" }, fontSize = 14.sp, maxLines = 3, overflow = TextOverflow.Ellipsis)
                }
                HorizontalDivider(color = Color(0xFFE6E6E6))
            }
        }
    }
}

@Composable
private fun Recherche(etat: EtatLecteur, aller: (Int) -> Unit) {
    val portee = rememberCoroutineScope()
    var texte by remember { mutableStateOf(etat.recherche) }
    fun lancer() {
        etat.recherche = texte
        etat.cherche = true
        portee.launch {
            etat.trouves = etat.doc.rechercher(texte)
            etat.cherche = false
            etat.trouves.firstOrNull()?.let { aller(it.page) }
        }
    }
    Column(Modifier.fillMaxSize().padding(12.dp)) {
        OutlinedTextField(texte, { texte = it }, Modifier.fillMaxWidth(), singleLine = true,
            placeholder = { Text(stringResource(R.string.rechercher_texte)) },
            trailingIcon = { IconButton(onClick = { lancer() }) { Icon(Icones.get("rechercher"), stringResource(R.string.rechercher)) } },
            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
            keyboardActions = KeyboardActions(onSearch = { lancer() }))
        Spacer(Modifier.height(8.dp))
        when {
            etat.cherche -> Text(stringResource(R.string.recherche_en_cours), color = Color.Gray)
            etat.recherche.isNotBlank() && etat.trouves.isEmpty() -> Text(stringResource(R.string.rien_trouve), color = Color.Gray)
            etat.trouves.isNotEmpty() -> {
                Text(stringResource(R.string.trouve_n, etat.trouves.sumOf { it.zones.size }, etat.trouves.size), fontSize = 13.sp)
                LazyColumn(Modifier.fillMaxSize()) {
                    items(etat.trouves) { t ->
                        Text(stringResource(R.string.page_n, t.page + 1) + " · " + t.zones.size,
                            Modifier.fillMaxWidth().clickable { aller(t.page) }.padding(vertical = 10.dp))
                    }
                }
            }
        }
    }
}

// ================================================================ pages
@Composable
private fun Pages(etat: EtatLecteur, tailles: List<Pair<Float, Float>>, modifier: Modifier, auToucher: (() -> Unit)? = null) {
    val lire = etat.annot.outil == Outil.MAIN && etat.deplacement == null
    BoxWithConstraints(modifier
        .pointerInput(lire) {
            // deux doigts : zoom de 1x a 5x, et deplacement quand on est zoome (en lecture seulement :
            // avec un outil, le doigt dessine)
            if (lire) detectTransformGestures { _, pan, zoom, _ ->
                etat.echelle = (etat.echelle * zoom).coerceIn(1f, 5f)
                etat.decalage = if (etat.echelle == 1f) Offset.Zero else etat.decalage + pan
            }
        }) {
        val largeurPx = with(LocalDensity.current) { (maxWidth - 16.dp).toPx().toInt() }
        LazyColumn(state = etat.liste, userScrollEnabled = lire, modifier = Modifier.fillMaxSize().graphicsLayer(
            scaleX = etat.echelle, scaleY = etat.echelle, translationX = etat.decalage.x, translationY = etat.decalage.y),
            contentPadding = PaddingValues(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            itemsIndexed(tailles) { n, (w, h) ->
                ImagePage(etat, n, largeurPx, w, h, Modifier.fillMaxWidth(), auToucher = auToucher)
            }
        }
    }
}

@Composable
private fun ImagePage(etat: EtatLecteur, n: Int, largeurPx: Int, w: Float, h: Float, modifier: Modifier, marques: Boolean = true,
                      auToucher: (() -> Unit)? = null) {
    val d = etat.doc
    val portee = rememberCoroutineScope()
    val ctx = LocalContext.current
    val image by produceState<Bitmap?>(null, d, n, largeurPx, d.version) {
        value = try { d.rendre(n, largeurPx) } catch (_: Exception) { value }
    }
    // trace en cours (doigt pose) : points en pixels de la page affichee
    var trace by remember { mutableStateOf<List<Offset>>(emptyList()) }
    val r = etat.annot
    Box(modifier.aspectRatio((w / h).coerceIn(0.1f, 10f)).background(Color.White)
        .then(if (!marques) Modifier else Modifier.pointerInput(r.outil, n, etat.deplacement) {
            val k = { o: Offset -> com.artifex.mupdf.fitz.Point(o.x * w / size.width, o.y * w / size.width) }
            val dep = etat.deplacement
            if (dep != null) {
                // deplacer une signature ou un tampon deja pose : il suit le doigt, puis « Ici »
                if (dep.page == n) awaitEachGesture {
                    val bas = awaitFirstDown()
                    var dernier = bas.position
                    while (true) {
                        val ev = awaitPointerEvent()
                        val c = ev.changes.firstOrNull() ?: break
                        if (!c.pressed) break
                        val d0 = c.position - dernier
                        dernier = c.position
                        etat.decalageDepl += Offset(d0.x * w / size.width, d0.y * w / size.width)
                        c.consume()
                    }
                }
                return@pointerInput
            }
            when (r.outil) {
                Outil.MAIN -> detectTapGestures(
                    onTap = { o ->
                        // champ de formulaire touche : on le remplit ; sinon, toucher normal (barres)
                        portee.launch {
                            val c = d.champA(n, k(o))
                            when {
                                c == null || c.lectureSeule -> auToucher?.invoke()
                                c.genre == com.artifex.mupdf.fitz.PDFWidget.TYPE_CHECKBOX ||
                                    c.genre == com.artifex.mupdf.fitz.PDFWidget.TYPE_RADIOBUTTON -> d.remplir(c, null)
                                // champ vide qui se remplit seul (date ou heure du moment) : rempli d'un toucher
                                c.genre == com.artifex.mupdf.fitz.PDFWidget.TYPE_TEXT && c.valeur.isEmpty() &&
                                    (try { org.json.JSONObject(c.regles).optString("auto") } catch (_: Exception) { "" }).let { it.isNotEmpty() && it != "null" } ->
                                    d.valeurAuto(c)
                                c.genre == com.artifex.mupdf.fitz.PDFWidget.TYPE_TEXT || c.options.isNotEmpty() -> etat.champ = c
                                // champ de signature : vide -> signer avec un certificat ; signe -> verifier
                                c.genre == com.artifex.mupdf.fitz.PDFWidget.TYPE_SIGNATURE -> {
                                    val signe = d.zonesChamps(n).any { z -> z.second == c.genre && z.third &&
                                        k(o).let { p -> p.x in z.first[0]..z.first[2] && p.y in z.first[1]..z.first[3] } }
                                    if (signe) etat.verifierSignatures = true
                                    else {
                                        val ids = Identites.liste(ctx)
                                        if (ids.isEmpty()) etat.message = ctx.getString(R.string.sig_aucune)
                                        else {
                                            if (etat.signerAvec == null) etat.signerAvec = ids.first()
                                            etat.champSignature = c.nom
                                            etat.cadreSignature = n to com.artifex.mupdf.fitz.Rect()
                                        }
                                    }
                                }
                                else -> auToucher?.invoke()
                            }
                        }
                    },
                    onDoubleTap = { etat.echelle = if (etat.echelle > 1.01f) 1f else 2f; if (etat.echelle == 1f) etat.decalage = Offset.Zero },
                    onLongPress = { o -> portee.launch {
                        // un champ de formulaire : le renommer ou le supprimer ; sinon l'annotation touchee
                        val c = d.champA(n, k(o))
                        if (c != null) etat.champOptions = c else etat.selection = d.annotationA(n, k(o))
                    } })
                Outil.NOTE -> detectTapGestures(onTap = { o -> etat.noteA = n to k(o) })
                Outil.TEXTE -> detectTapGestures(onTap = { o ->
                    portee.launch {
                        val p = d.paragrapheA(n, k(o))
                        // page scannee (aucun texte) : on propose la reconnaissance du texte
                        if (p == null) { if (etat.doc.modifiable && d.pageSansTexte(n)) etat.ocr = n else etat.message = "aucun_texte" }
                        else etat.paragraphe = p
                    }
                })
                // l'apercu suit le doigt (toucher ou glisser) ; rien n'est pose avant « Poser ici »
                Outil.POSER -> awaitEachGesture {
                    val bas = awaitFirstDown()
                    val p = { o: Offset -> Offset(o.x * w / size.width, o.y * w / size.width) }
                    etat.fantome = n to p(bas.position)
                    while (true) {
                        val ev = awaitPointerEvent()
                        val c = ev.changes.firstOrNull() ?: break
                        if (!c.pressed) break
                        etat.fantome = n to p(c.position)
                        c.consume()
                    }
                }
                // gomme : toucher une annotation, ou frotter dessus, l'efface (le contenu de la page : « Effacer une zone »)
                Outil.GOMME -> awaitEachGesture {
                    val bas = awaitFirstDown()
                    val pts = arrayListOf(k(bas.position))
                    trace = listOf(bas.position)
                    while (true) {
                        val ev = awaitPointerEvent()
                        val c = ev.changes.firstOrNull() ?: break
                        if (!c.pressed) break
                        pts += k(c.position); trace = trace + c.position
                        c.consume()
                    }
                    trace = emptyList()
                    portee.launch {
                        try { if (d.supprimerAnnotationsSur(n, pts) == 0) etat.message = ctx.getString(R.string.gomme_rien) }
                        catch (e: Exception) { Journal.ecrire("gomme", e.toString()) }
                    }
                }
                else -> detectDragGestures(
                    onDragStart = { o -> trace = listOf(o) },
                    onDrag = { ch, _ -> trace = trace + ch.position },
                    onDragCancel = { trace = emptyList() },
                    onDragEnd = {
                        val pts = trace.map(k)
                        trace = emptyList()
                        val c = r.couleur().versPdf()
                        val op = r.opacite()
                        portee.launch {
                            when (r.outil) {
                                Outil.SURLIGNER -> d.annoterTexte(n, com.artifex.mupdf.fitz.PDFAnnotation.TYPE_HIGHLIGHT, pts.first(), pts.last(), c, op)
                                Outil.SOULIGNER -> d.annoterTexte(n, com.artifex.mupdf.fitz.PDFAnnotation.TYPE_UNDERLINE, pts.first(), pts.last(), c, op)
                                Outil.BARRER -> d.annoterTexte(n, com.artifex.mupdf.fitz.PDFAnnotation.TYPE_STRIKE_OUT, pts.first(), pts.last(), c, op)
                                Outil.DESSIN -> d.dessiner(n, pts, c, r.epaisseur, 1f)
                                Outil.RECTANGLE -> d.forme(n, com.artifex.mupdf.fitz.PDFAnnotation.TYPE_SQUARE, pts.first(), pts.last(), c, r.epaisseur, 1f)
                                Outil.ELLIPSE -> d.forme(n, com.artifex.mupdf.fitz.PDFAnnotation.TYPE_CIRCLE, pts.first(), pts.last(), c, r.epaisseur, 1f)
                                Outil.FLECHE -> d.forme(n, com.artifex.mupdf.fitz.PDFAnnotation.TYPE_LINE, pts.first(), pts.last(), c, r.epaisseur, 1f)
                                Outil.EFFACER_ZONE -> d.effacerZone(n, com.artifex.mupdf.fitz.Rect(minOf(pts.first().x, pts.last().x),
                                    minOf(pts.first().y, pts.last().y), maxOf(pts.first().x, pts.last().x), maxOf(pts.first().y, pts.last().y)))
                                Outil.CHAMP_LISTE -> {
                                    val a = pts.first(); val b = pts.last()
                                    etat.nouvelleListe = n to com.artifex.mupdf.fitz.Rect(minOf(a.x, b.x), minOf(a.y, b.y),
                                        maxOf(a.x, b.x).coerceAtLeast(minOf(a.x, b.x) + 60f), maxOf(a.y, b.y).coerceAtLeast(minOf(a.y, b.y) + 14f))
                                    true
                                }
                                Outil.CHAMP_SIGNATURE -> {
                                    val a = pts.first(); val b = pts.last()
                                    val petit = kotlin.math.abs(b.x - a.x) < 40 || kotlin.math.abs(b.y - a.y) < 15
                                    val rect = if (petit) com.artifex.mupdf.fitz.Rect(a.x, a.y, a.x + 180f, a.y + 55f)
                                        else com.artifex.mupdf.fitz.Rect(minOf(a.x, b.x), minOf(a.y, b.y), maxOf(a.x, b.x), maxOf(a.y, b.y))
                                    d.creerChamps(listOf(ChampDetecte(n, "signature", rect, ctx.getString(R.string.champ_signature_nom))))
                                }
                                Outil.SIGNER_NUM -> {
                                    val a = pts.first(); val b = pts.last()
                                    val petit = kotlin.math.abs(b.x - a.x) < 40 || kotlin.math.abs(b.y - a.y) < 15
                                    etat.cadreSignature = n to (if (petit) com.artifex.mupdf.fitz.Rect(a.x, a.y, a.x + 180f, a.y + 55f)
                                        else com.artifex.mupdf.fitz.Rect(minOf(a.x, b.x), minOf(a.y, b.y), maxOf(a.x, b.x), maxOf(a.y, b.y)))
                                    true
                                }
                                Outil.CHAMP_TEXTE, Outil.CHAMP_CASE -> {
                                    val a = pts.first(); val b = pts.last()
                                    val case = r.outil == Outil.CHAMP_CASE
                                    val rect = if (case) {             // case : carre de 12 pt (ou la taille dessinee)
                                        val cote = maxOf(10f, minOf(kotlin.math.abs(b.x - a.x), kotlin.math.abs(b.y - a.y)).coerceAtMost(24f))
                                        com.artifex.mupdf.fitz.Rect(minOf(a.x, b.x), minOf(a.y, b.y), minOf(a.x, b.x) + cote, minOf(a.y, b.y) + cote)
                                    } else com.artifex.mupdf.fitz.Rect(minOf(a.x, b.x), minOf(a.y, b.y),
                                        maxOf(a.x, b.x).coerceAtLeast(minOf(a.x, b.x) + 30f), maxOf(a.y, b.y).coerceAtLeast(minOf(a.y, b.y) + 14f))
                                    d.creerChamps(listOf(ChampDetecte(n, if (case) "case" else "texte", rect, "",
                                        lignes = !case && rect.y1 - rect.y0 > 30)))
                                }
                                else -> false
                            }
                        }
                    })
            }
        })) {
        image?.let { Image(it.asImageBitmap(), null, Modifier.fillMaxSize()) }
        if (marques) {
            val champs by produceState(emptyList<Triple<FloatArray, Int, Boolean>>(), d, n, d.version) { value = try { d.zonesChamps(n) } catch (_: Exception) { value } }
            if (champs.isNotEmpty()) Canvas(Modifier.fillMaxSize()) {   // champs en bleu clair (a l'ecran seulement)
                val kk = size.width / w
                champs.forEach { (r, genre, signe) ->
                    val o = Offset(r[0] * kk, r[1] * kk); val t = Size((r[2] - r[0]) * kk, (r[3] - r[1]) * kk)
                    if (genre == com.artifex.mupdf.fitz.PDFWidget.TYPE_SIGNATURE && !signe) {
                        drawRect(Color(0x22F5A623), o, t)
                        drawRect(Color(0xFFF5A623), o, t, style = androidx.compose.ui.graphics.drawscope.Stroke(2f,
                            pathEffect = androidx.compose.ui.graphics.PathEffect.dashPathEffect(floatArrayOf(10f, 6f))))
                    } else if (genre != com.artifex.mupdf.fitz.PDFWidget.TYPE_SIGNATURE) {
                        drawRect(Color(0x260F6CBD), o, t)
                        drawRect(Color(0x660F6CBD), o, t, style = androidx.compose.ui.graphics.drawscope.Stroke(1.5f))
                    }
                }
            }
        }
        val zones = if (marques) etat.trouves.firstOrNull { it.page == n }?.zones else null
        if (!zones.isNullOrEmpty()) {
            Canvas(Modifier.fillMaxSize()) {           // resultats de la recherche surlignes
                val k = size.width / w
                zones.forEach { z ->
                    drawRect(Color(0x66FFD200), Offset(z[0] * k, z[1] * k), Size((z[2] - z[0]) * k, (z[3] - z[1]) * k))
                }
            }
        }
        if (trace.size > 1) {
            Canvas(Modifier.fillMaxSize()) {           // apercu du trait pendant que le doigt bouge
                val c = r.couleur()
                val a = trace.first()
                val b = trace.last()
                val ep = (r.epaisseur * size.width / w).coerceAtLeast(2f)
                when (r.outil) {
                    Outil.DESSIN -> for (i in 1 until trace.size) drawLine(c, trace[i - 1], trace[i], ep)
                    Outil.RECTANGLE -> drawRect(c, Offset(minOf(a.x, b.x), minOf(a.y, b.y)), Size(kotlin.math.abs(b.x - a.x), kotlin.math.abs(b.y - a.y)),
                        style = androidx.compose.ui.graphics.drawscope.Stroke(ep))
                    Outil.ELLIPSE -> drawOval(c, Offset(minOf(a.x, b.x), minOf(a.y, b.y)), Size(kotlin.math.abs(b.x - a.x), kotlin.math.abs(b.y - a.y)),
                        style = androidx.compose.ui.graphics.drawscope.Stroke(ep))
                    Outil.FLECHE -> drawLine(c, a, b, ep)
                    Outil.EFFACER_ZONE -> drawRect(Color(0x55D32F2F), Offset(minOf(a.x, b.x), minOf(a.y, b.y)),
                        Size(kotlin.math.abs(b.x - a.x), kotlin.math.abs(b.y - a.y)))
                    Outil.GOMME -> for (i in 1 until trace.size) drawLine(Color(0x88D32F2F), trace[i - 1], trace[i], 18f)
                    Outil.SIGNER_NUM, Outil.CHAMP_TEXTE, Outil.CHAMP_CASE, Outil.CHAMP_LISTE, Outil.CHAMP_SIGNATURE -> drawRect(Color(0xFF0F6CBD), Offset(minOf(a.x, b.x), minOf(a.y, b.y)),
                        Size(kotlin.math.abs(b.x - a.x), kotlin.math.abs(b.y - a.y)), style = androidx.compose.ui.graphics.drawscope.Stroke(3f))
                    else -> drawRect(c.copy(alpha = 0.35f), Offset(minOf(a.x, b.x), minOf(a.y, b.y)),   // zone de texte choisie
                        Size(kotlin.math.abs(b.x - a.x).coerceAtLeast(4f), kotlin.math.abs(b.y - a.y).coerceAtLeast(24f)))
                }
            }
        }
        val f = etat.fantome
        val a = etat.aPoser
        if (marques && r.outil == Outil.POSER && a != null && f != null && f.first == n) Apercu(etat, a, f.second, w)
        etat.deplacement?.takeIf { marques && it.page == n }?.let { Deplacement(etat, it, w) }
    }
}

/** Apercu de la signature ou du tampon a poser, avec « Poser ici » / « Annuler » juste en dessous (ou au-dessus). */
@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun Apercu(etat: EtatLecteur, a: APoser, centre: Offset, w: Float) {
    val ctx = LocalContext.current
    val portee = rememberCoroutineScope()
    val image = remember(a) { (a as? APoser.Image)?.let { android.graphics.BitmapFactory.decodeFile(it.png.absolutePath)?.asImageBitmap() } }
    val (lw, lh) = a.taillePt()
    BoxWithConstraints(Modifier.fillMaxSize()) {
        val dens = LocalDensity.current
        val s = with(dens) { maxWidth.toPx() } / w
        val x0 = (centre.x - lw / 2) * s
        val y0 = (centre.y - lh / 2) * s
        Canvas(Modifier.fillMaxSize()) {
            val tl = Offset(x0, y0)
            val sz = Size(lw * s, lh * s)
            drawRect(Color(0x221A73E8), tl, sz)
            when (a) {
                is APoser.Traits -> a.t.traits.forEach { t ->
                    for (i in 1 until t.size) drawLine(ENCRE, Offset(x0 + t[i - 1].first * sz.width, y0 + t[i - 1].second * sz.height),
                        Offset(x0 + t[i].first * sz.width, y0 + t[i].second * sz.height), (2f * s).coerceAtLeast(2f),
                        androidx.compose.ui.graphics.StrokeCap.Round)
                }
                is APoser.Image -> image?.let {
                    drawImage(it, dstOffset = androidx.compose.ui.unit.IntOffset(x0.toInt(), y0.toInt()),
                        dstSize = androidx.compose.ui.unit.IntSize(sz.width.toInt().coerceAtLeast(1), sz.height.toInt().coerceAtLeast(1)))
                }
                is APoser.Tampon -> {
                    drawRect(a.couleur, tl, sz, style = androidx.compose.ui.graphics.drawscope.Stroke(2f * s))
                    val peint = android.graphics.Paint(android.graphics.Paint.ANTI_ALIAS_FLAG).apply {
                        color = android.graphics.Color.argb(255, (a.couleur.red * 255).toInt(), (a.couleur.green * 255).toInt(), (a.couleur.blue * 255).toInt())
                        textSize = a.taille * s
                        isFakeBoldText = true
                        textAlign = android.graphics.Paint.Align.CENTER
                    }
                    val lignes = a.texte.split("\n")
                    val pas = a.taille * 1.25f * s
                    val haut = y0 + (sz.height - lignes.size * pas) / 2
                    lignes.forEachIndexed { i, l ->
                        drawContext.canvas.nativeCanvas.drawText(l, x0 + sz.width / 2, haut + (i + 0.8f) * pas, peint)
                    }
                }
            }
            // cadre pointille : c'est un apercu, pas encore pose
            drawRect(Color(0xFF1A73E8), tl, sz, style = androidx.compose.ui.graphics.drawscope.Stroke(3f,
                pathEffect = androidx.compose.ui.graphics.PathEffect.dashPathEffect(floatArrayOf(14f, 10f))))
        }
        val hautBoutons = with(dens) { 48.dp.toPx() }
        val enDessous = y0 + lh * s + hautBoutons + 8 < with(dens) { maxHeight.toPx() }
        val yb = if (enDessous) y0 + lh * s + 8 else (y0 - hautBoutons - 8).coerceAtLeast(0f)
        FlowRow(Modifier.fillMaxWidth().offset { androidx.compose.ui.unit.IntOffset(0, yb.toInt()) },
            horizontalArrangement = Arrangement.spacedBy(6.dp, Alignment.CenterHorizontally)) {
            // taille : plus petit / plus grand, avant de poser
            FilledTonalButton(onClick = { etat.aPoser = a.agrandi(1f / 1.2f) }, contentPadding = PaddingValues(horizontal = 14.dp)) { Text("−", fontSize = 20.sp) }
            FilledTonalButton(onClick = { etat.aPoser = a.agrandi(1.2f) }, contentPadding = PaddingValues(horizontal = 14.dp)) { Text("+", fontSize = 20.sp) }
            Button(onClick = {
                val f = etat.fantome ?: return@Button
                etat.fantome = null
                etat.aPoser = null
                etat.annot.outil = Outil.MAIN
                val pt = com.artifex.mupdf.fitz.Point(f.second.x, f.second.y)
                val d = etat.doc
                val n = f.first
                // pas la portee de l'apercu : il quitte l'ecran tout de suite, ce qui annulerait la pose a mi-chemin
                // (la page ne se redessinait qu'a l'action suivante)
                (etat.portee ?: portee).launch {
                    when (a) {
                        is APoser.Traits -> d.poserTraits(n, pt, a.largeur, a.t.ratio, a.t.traits, ENCRE.versPdf(),
                            if (a.t.genre == "paraphe") 1.6f else 2f)
                        is APoser.Tampon -> d.tampon(n, pt, a.texte, a.couleur.versPdf(), a.taille)
                        is APoser.Image -> d.image(n, pt, a.largeur, a.ratio, a.png.readBytes())
                    }
                }
            }, colors = ButtonDefaults.buttonColors(containerColor = ROUGE)) { Text(stringResource(R.string.poser_ici)) }
            OutlinedButton(onClick = { etat.fantome = null; etat.aPoser = null; etat.annot.outil = Outil.MAIN },
                colors = ButtonDefaults.outlinedButtonColors(containerColor = Color.White)) { Text(stringResource(R.string.annuler)) }
        }
    }
}

/** Cadre de la signature ou du tampon que l'on deplace, avec « Ici » et « Annuler ». */
@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun Deplacement(etat: EtatLecteur, info: InfoAnnot, w: Float) {
    BoxWithConstraints(Modifier.fillMaxSize()) {
        val dens = LocalDensity.current
        val s = with(dens) { maxWidth.toPx() } / w
        val d = etat.decalageDepl
        val x0 = (info.rect[0] + d.x) * s
        val y0 = (info.rect[1] + d.y) * s
        val lw = (info.rect[2] - info.rect[0]) * s
        val lh = (info.rect[3] - info.rect[1]) * s
        Canvas(Modifier.fillMaxSize()) {
            drawRect(Color(0x331A73E8), Offset(x0, y0), Size(lw, lh))
            drawRect(Color(0xFF1A73E8), Offset(x0, y0), Size(lw, lh), style = androidx.compose.ui.graphics.drawscope.Stroke(3f,
                pathEffect = androidx.compose.ui.graphics.PathEffect.dashPathEffect(floatArrayOf(14f, 10f))))
        }
        val hb = with(dens) { 48.dp.toPx() }
        val yb = if (y0 + lh + hb + 8 < with(dens) { maxHeight.toPx() }) y0 + lh + 8 else (y0 - hb - 8).coerceAtLeast(0f)
        FlowRow(Modifier.fillMaxWidth().offset { androidx.compose.ui.unit.IntOffset(0, yb.toInt()) },
            horizontalArrangement = Arrangement.spacedBy(6.dp, Alignment.CenterHorizontally)) {
            Button(onClick = {
                val dd = etat.decalageDepl
                etat.deplacement = null
                etat.decalageDepl = Offset.Zero
                etat.portee?.launch { etat.doc.transformer(info, dd.x, dd.y, 1f) }
            }, colors = ButtonDefaults.buttonColors(containerColor = ROUGE)) { Text(stringResource(R.string.ici)) }
            OutlinedButton(onClick = { etat.deplacement = null; etat.decalageDepl = Offset.Zero },
                colors = ButtonDefaults.outlinedButtonColors(containerColor = Color.White)) { Text(stringResource(R.string.annuler)) }
        }
        Text(stringResource(R.string.aide_deplacer), Modifier.align(Alignment.TopCenter).padding(8.dp)
            .background(Color(0xCC333333), RoundedCornerShape(12.dp)).padding(horizontal = 10.dp, vertical = 4.dp),
            color = Color.White, fontSize = 12.sp)
    }
}

@Composable
private fun IndicateurPage(etat: EtatLecteur, total: Int, modifier: Modifier) {
    Text(stringResource(R.string.page_sur, etat.page + 1, total),
        modifier.padding(12.dp).background(Color(0xAA000000), RoundedCornerShape(12.dp)).padding(horizontal = 10.dp, vertical = 4.dp),
        color = Color.White, fontSize = 13.sp)
}

@Composable
private fun AllerALaPage(total: Int, fermer: () -> Unit, aller: (Int) -> Unit) {
    var t by remember { mutableStateOf("") }
    AlertDialog(onDismissRequest = fermer,
        title = { Text(stringResource(R.string.aller_page)) },
        text = {
            OutlinedTextField(t, { t = it.filter(Char::isDigit) }, singleLine = true,
                label = { Text("1 – $total") }, keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number))
        },
        confirmButton = {
            TextButton(onClick = { t.toIntOrNull()?.let { aller((it - 1).coerceIn(0, total - 1)) }; fermer() }) {
                Text(stringResource(R.string.ok))
            }
        },
        dismissButton = { TextButton(onClick = fermer) { Text(stringResource(R.string.annuler)) } })
}

@Composable
private fun DemandeMotDePasse(doc: DocumentPdf, ok: () -> Unit, annuler: () -> Unit) {
    var mdp by remember { mutableStateOf("") }
    var faux by remember { mutableStateOf(false) }
    AlertDialog(onDismissRequest = annuler,
        title = { Text(stringResource(R.string.mot_de_passe)) },
        text = {
            Column {
                Text(stringResource(R.string.protege, doc.nom))
                Spacer(Modifier.height(8.dp))
                ChampSecret(mdp, { mdp = it; faux = false }, stringResource(R.string.mot_de_passe), erreur = faux,
                    aide = if (faux) { { Text(stringResource(R.string.mdp_faux)) } } else null)
            }
        },
        confirmButton = { TextButton(onClick = { if (doc.motDePasse(mdp)) ok() else faux = true }) { Text(stringResource(R.string.ok)) } },
        dismissButton = { TextButton(onClick = annuler) { Text(stringResource(R.string.annuler)) } })
}

/** Page ou l'on s'etait arrete, par document (reprise a la reouverture). */
object PagesLues {
    private fun prefs(ctx: Context) = ctx.getSharedPreferences("pages_lues", Context.MODE_PRIVATE)
    fun lire(ctx: Context, uri: String): Int = prefs(ctx).getInt(empreinte(uri), 0)
    fun ecrire(ctx: Context, uri: String, page: Int) { prefs(ctx).edit().putInt(empreinte(uri), page).apply() }
}

/** Partager : l'application e-mail d'Android, un Drive, une messagerie... (choix d'Android). */
suspend fun partager(ctx: Context, doc: DocumentPdf) {
    val f = doc.copieAJour(ctx)                     // avec les annotations, meme pas encore enregistrees
    val u = FileProvider.getUriForFile(ctx, ctx.packageName + ".fichiers", f)
    val i = Intent(Intent.ACTION_SEND).setType("application/pdf").putExtra(Intent.EXTRA_STREAM, u)
        .putExtra(Intent.EXTRA_SUBJECT, doc.nom).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
    ctx.startActivity(Intent.createChooser(i, ctx.getString(R.string.partager)))
}

/** Imprimer : service d'impression d'Android (imprimantes du reseau, « Enregistrer au format PDF »...). */
suspend fun imprimer(ctx: Context, doc: DocumentPdf) {
    val f = doc.copieAJour(ctx)
    val pm = ctx.getSystemService(Context.PRINT_SERVICE) as PrintManager
    pm.print(doc.nom, object : PrintDocumentAdapter() {
        override fun onLayout(ancien: PrintAttributes?, nouveau: PrintAttributes?, annul: CancellationSignal?,
                              rappel: LayoutResultCallback, extras: Bundle?) {
            if (annul?.isCanceled == true) { rappel.onLayoutCancelled(); return }
            rappel.onLayoutFinished(PrintDocumentInfo.Builder(doc.nom)
                .setContentType(PrintDocumentInfo.CONTENT_TYPE_DOCUMENT).setPageCount(doc.nbPages()).build(), true)
        }

        override fun onWrite(pages: Array<out PageRange>?, destination: ParcelFileDescriptor, annul: CancellationSignal?,
                             rappel: WriteResultCallback) {
            try {
                f.inputStream().use { e ->
                    ParcelFileDescriptor.AutoCloseOutputStream(destination).use { s -> e.copyTo(s) }
                }
                rappel.onWriteFinished(arrayOf(PageRange.ALL_PAGES))
            } catch (e: Exception) {
                rappel.onWriteFailed(e.message)
            }
        }
    }, null)
}


/** Libelle sur une ligne qui rapetisse au lieu d'etre coupe (« Commenter » et non « Comment »),
 *  meme quand le telephone est regle en grands caracteres. */
@Composable
fun TexteAjuste(texte: String, taille: androidx.compose.ui.unit.TextUnit, minimum: Float = 7f) {
    var t by remember(texte, taille) { mutableStateOf(taille) }
    var pret by remember(texte, taille) { mutableStateOf(false) }
    Text(texte, fontSize = t, maxLines = 1, softWrap = false,
        modifier = Modifier.drawWithContent { if (pret) drawContent() },
        onTextLayout = { r ->
            if (r.hasVisualOverflow && t.value > minimum) t = (t.value * 0.9f).sp else pret = true
        })
}

/** Reconnaissance du texte (OCR) d'une page scannee ou de tout le document : le texte est pose invisible sous l'image
 *  (recherche, copie, « Modifier le texte »). Tout se fait sur le telephone ; les langues autres que le francais sont
 *  telechargees une fois, a la demande (plusieurs langues possibles pour un document mixte). */
@OptIn(ExperimentalLayoutApi::class, ExperimentalMaterial3Api::class)
@Composable
private fun DialogueOcr(etat: EtatLecteur, page: Int, fermer: () -> Unit) {
    val ctx = LocalContext.current
    val portee = rememberCoroutineScope()
    var occupe by remember { mutableStateOf(false) }
    var fait by remember { mutableStateOf(0) }
    var total by remember { mutableStateOf(0) }
    var telecharge by remember { mutableStateOf<String?>(null) }
    var erreur by remember { mutableStateOf<String?>(null) }
    var langues by remember { mutableStateOf(Ocr.choisies(ctx)) }
    var travail by remember { mutableStateOf<kotlinx.coroutines.Job?>(null) }
    val aTelecharger = Ocr.LANGUES.filter { it.code in langues && !Ocr.disponible(ctx, it.code) }
    fun lancer(pages: List<Int>?) {
        occupe = true; erreur = null
        travail = portee.launch {
            try {
                for (l in aTelecharger) {
                    telecharge = l.nom
                    try { withContext(Dispatchers.IO) { Ocr.telecharger(ctx, l.code) } }
                    catch (x: Exception) { throw IllegalStateException(ctx.getString(R.string.ocr_telechargement_impossible, l.nom, x.message ?: x.toString())) }
                }
                telecharge = null
                Ocr.retenir(ctx, langues)
                val k = etat.doc.reconnaitre(ctx, pages, langues.joinToString("+")) { a, b -> fait = a; total = b }
                etat.message = if (k > 0) ctx.getString(R.string.ocr_fini, k) else ctx.getString(R.string.ocr_rien)
                fermer()
            } catch (x: kotlinx.coroutines.CancellationException) { throw x
            } catch (x: Throwable) {
                Journal.ecrire("ocr", "reconnaissance impossible : $x")
                erreur = x.message ?: x.toString(); occupe = false; telecharge = null
            }
        }
    }
    AlertDialog(onDismissRequest = { if (!occupe) fermer() }, title = { Text(stringResource(R.string.ocr_titre)) },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState())) {
                Text(stringResource(R.string.ocr_aide), fontSize = 14.sp)
                Spacer(Modifier.height(8.dp))
                Text(stringResource(R.string.ocr_langues), fontWeight = FontWeight.SemiBold, fontSize = 13.sp)
                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    Ocr.LANGUES.forEach { l ->
                        val oui = l.code in langues
                        FilterChip(oui, enabled = !occupe, onClick = {
                            langues = if (oui) (langues - l.code).ifEmpty { listOf("fra") } else langues + l.code
                        }, label = { Text(l.nom + if (!Ocr.disponible(ctx, l.code)) " ↓" else "", fontSize = 12.sp) })
                    }
                }
                Text(stringResource(R.string.ocr_langues_aide), fontSize = 11.sp, color = Color.Gray)
                if (aTelecharger.isNotEmpty() && !occupe) Text(stringResource(R.string.ocr_a_telecharger,
                    aTelecharger.joinToString(", ") { it.nom }, "%.1f".format(aTelecharger.sumOf { it.mo.toDouble() })),
                    fontSize = 12.sp, color = Color(0xFF0F6CBD))
                if (occupe) {
                    Spacer(Modifier.height(10.dp))
                    if (telecharge == null && total > 1) LinearProgressIndicator({ fait.toFloat() / total }, Modifier.fillMaxWidth())
                    else LinearProgressIndicator(Modifier.fillMaxWidth())
                    Text(telecharge?.let { stringResource(R.string.ocr_telechargement, it) }
                        ?: stringResource(R.string.ocr_en_cours, (fait + 1).coerceAtMost(total.coerceAtLeast(1)), total.coerceAtLeast(1)),
                        fontSize = 12.sp, color = Color.Gray)
                }
                erreur?.let { Text(it, color = Color(0xFFC62828), fontSize = 13.sp, modifier = Modifier.padding(top = 6.dp)) }
            }
        },
        confirmButton = {
            if (!occupe) Row {
                TextButton(onClick = { lancer(listOf(page)) }) { Text(stringResource(R.string.ocr_cette_page, page + 1)) }
                TextButton(onClick = { lancer(null) }) { Text(stringResource(R.string.ocr_tout)) }
            }
        },
        dismissButton = { TextButton(onClick = { travail?.cancel(); fermer() }) { Text(stringResource(R.string.annuler)) } })
}
