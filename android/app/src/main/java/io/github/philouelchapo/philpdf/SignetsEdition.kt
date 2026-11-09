package io.github.philouelchapo.philpdf

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.launch

/** Signet a sa place dans l'arbre : sa liste (parent) et sa profondeur. */
private class Place(val n: NoeudSignet, val liste: MutableList<NoeudSignet>, val prof: Int)

private fun aplatir(l: MutableList<NoeudSignet>, prof: Int = 0, out: MutableList<Place> = ArrayList()): List<Place> {
    for (n in l) { out += Place(n, l, prof); aplatir(n.enfants, prof + 1, out) }
    return out
}

/** Modifier les signets (Organiser les pages > Signets, ou le volet Signets), comme sous Windows : ajouter (sur la
 *  page voulue), sous-signet, renommer, changer de page, monter / descendre, supprimer. Chaque changement est une
 *  etape d'annulation ; rien n'est enregistre dans le fichier avant la disquette. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun EditeurSignets(etat: EtatLecteur, nbPages: Int, pageDefaut: Int, fermer: () -> Unit) {
    val d = etat.doc
    val portee = rememberCoroutineScope()
    var arbre by remember { mutableStateOf<MutableList<NoeudSignet>?>(null) }
    var version by remember { mutableIntStateOf(0) }
    LaunchedEffect(version) { arbre = d.arbreSignets().toMutableList() }
    var edition by remember { mutableStateOf<Pair<Place?, Boolean>?>(null) }     // (signet modifie ou null = nouveau, sous-signet ?)
    var menu by remember { mutableStateOf<Place?>(null) }
    var supprimer by remember { mutableStateOf<Place?>(null) }

    fun ecrire(libelle: String) {
        val a = arbre ?: return
        portee.launch { d.ecrireSignets(a, libelle); version++ }
    }

    Fenetre(fermer) {
        Surface(Modifier.fillMaxSize(), color = Color.White) {
            Column(Modifier.fillMaxSize()) {
                Row(Modifier.fillMaxWidth().padding(horizontal = 4.dp, vertical = 2.dp), verticalAlignment = Alignment.CenterVertically) {
                    IconButton(onClick = fermer) { Icon(Icons.AutoMirrored.Filled.ArrowBack, stringResource(R.string.retour)) }
                    Column(Modifier.weight(1f)) {
                        TexteAjuste(stringResource(R.string.sgn_titre), 17.sp)
                        Text(stringResource(R.string.sgn_aide), fontSize = 12.sp, color = Color.Gray, maxLines = 3)
                    }
                    BoutonsEdition(etat)
                }
                HorizontalDivider(color = Color(0xFFE2E2E2))
                val a = arbre
                val places = remember(a, version) { a?.let { aplatir(it) } ?: emptyList() }
                Box(Modifier.weight(1f).fillMaxWidth()) {
                    when {
                        a == null -> CircularProgressIndicator(Modifier.align(Alignment.Center))
                        places.isEmpty() -> Text(stringResource(R.string.aucun_signet), Modifier.padding(16.dp), color = Color.Gray)
                        else -> LazyColumn(Modifier.fillMaxSize()) {
                            items(places) { pl ->
                                Row(Modifier.fillMaxWidth().clickable { menu = pl }
                                    .padding(start = (12 + 16 * pl.prof).dp, end = 8.dp, top = 10.dp, bottom = 10.dp),
                                    verticalAlignment = Alignment.CenterVertically) {
                                    Text(pl.n.titre.ifBlank { "—" }, Modifier.weight(1f), fontSize = 15.sp, maxLines = 3, overflow = TextOverflow.Ellipsis)
                                    Text(if (pl.n.page >= 0) "p. ${pl.n.page + 1}" else "—", fontSize = 12.sp, color = Color.Gray)
                                    Icon(Icones.get("suivante", Color(0xFF666666)), null, Modifier.padding(start = 6.dp), tint = Color.Unspecified)
                                }
                                HorizontalDivider(color = Color(0xFFEEEEEE))
                            }
                        }
                    }
                }
                HorizontalDivider(color = Color(0xFFE2E2E2))
                FlowRow(Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 8.dp),
                    horizontalArrangement = Arrangement.spacedBy(4.dp, Alignment.End)) {
                    TextButton(onClick = fermer) { Text(stringResource(R.string.termine)) }
                    Button(onClick = { edition = Pair(null, false) }, enabled = a != null,
                        colors = ButtonDefaults.buttonColors(containerColor = ROUGE)) { Text(stringResource(R.string.sgn_ajouter)) }
                }
            }
        }
    }

    // actions sur un signet
    menu?.let { pl ->
        val i = pl.liste.indexOf(pl.n)
        AlertDialog(onDismissRequest = { menu = null }, title = { Text(pl.n.titre.ifBlank { "—" }, maxLines = 2, overflow = TextOverflow.Ellipsis) },
            text = {
                Column {
                    @Composable fun ligne(t: Int, actif: Boolean = true, f: () -> Unit) =
                        Text(stringResource(t), Modifier.fillMaxWidth().clickable(enabled = actif) { menu = null; f() }.padding(vertical = 12.dp),
                            color = if (actif) Color.Unspecified else Color.LightGray)
                    if (pl.n.page >= 0) ligne(R.string.sgn_aller) { fermer(); portee.launch { etat.liste.scrollToItem(pl.n.page) } }
                    ligne(R.string.sgn_modifier) { edition = Pair(pl, false) }
                    ligne(R.string.sgn_sous) { edition = Pair(pl, true) }
                    ligne(R.string.sgn_monter, i > 0) { pl.liste.removeAt(i); pl.liste.add(i - 1, pl.n); ecrire("Signet monté") }
                    ligne(R.string.sgn_descendre, i < pl.liste.size - 1) { pl.liste.removeAt(i); pl.liste.add(i + 1, pl.n); ecrire("Signet descendu") }
                    Text(stringResource(R.string.sgn_supprimer), Modifier.fillMaxWidth().clickable { menu = null; supprimer = pl }.padding(vertical = 12.dp), color = ROUGE)
                }
            },
            confirmButton = { TextButton(onClick = { menu = null }) { Text(stringResource(R.string.fermer)) } })
    }

    supprimer?.let { pl ->
        AlertDialog(onDismissRequest = { supprimer = null }, title = { Text(stringResource(R.string.sgn_supprimer)) },
            text = { Text(stringResource(if (pl.n.enfants.isEmpty()) R.string.sgn_supprimer_q else R.string.sgn_supprimer_q_sous, pl.n.titre, pl.n.enfants.size)) },
            confirmButton = { TextButton(onClick = { supprimer = null; pl.liste.remove(pl.n); ecrire("Signet supprimé") }) { Text(stringResource(R.string.supprimer), color = ROUGE) } },
            dismissButton = { TextButton(onClick = { supprimer = null }) { Text(stringResource(R.string.annuler)) } })
    }

    // ajouter / modifier : titre et page
    edition?.let { (pl, sous) ->
        val modif = pl != null && !sous
        var titre by remember(pl, sous) { mutableStateOf(if (modif) pl!!.n.titre else "") }
        var page by remember(pl, sous) { mutableStateOf(((if (modif) pl!!.n.page else pageDefaut).coerceAtLeast(0) + 1).toString()) }
        val p = page.toIntOrNull()
        val ok = titre.isNotBlank() && p != null && p in 1..nbPages
        AlertDialog(onDismissRequest = { edition = null },
            title = { Text(stringResource(when { modif -> R.string.sgn_modifier; sous -> R.string.sgn_sous; else -> R.string.sgn_ajouter })) },
            text = {
                Column {
                    OutlinedTextField(titre, { titre = it }, Modifier.fillMaxWidth(), label = { Text(stringResource(R.string.sgn_nom)) })
                    Spacer(Modifier.height(8.dp))
                    OutlinedTextField(page, { page = it.filter { c -> c.isDigit() }.take(5) }, Modifier.fillMaxWidth(), singleLine = true,
                        label = { Text(stringResource(R.string.sgn_page, nbPages)) }, isError = p == null || p !in 1..nbPages,
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number))
                }
            },
            confirmButton = { TextButton(onClick = {
                val a = arbre ?: return@TextButton
                val n = p!! - 1
                when {
                    modif -> { pl!!.n.titre = titre.trim(); pl.n.page = n; ecrire("Signet modifié") }
                    sous -> { pl!!.n.enfants += NoeudSignet(titre.trim(), "", n, ArrayList()); ecrire("Sous-signet ajouté") }
                    else -> {
                        // a sa place dans l'ordre des pages, au premier niveau
                        val i = a.indexOfFirst { it.page > n }.let { if (it < 0) a.size else it }
                        a.add(i, NoeudSignet(titre.trim(), "", n, ArrayList())); ecrire("Signet ajouté")
                    }
                }
                edition = null
            }, enabled = ok) { Text(stringResource(R.string.ok)) } },
            dismissButton = { TextButton(onClick = { edition = null }) { Text(stringResource(R.string.annuler)) } })
    }
}
