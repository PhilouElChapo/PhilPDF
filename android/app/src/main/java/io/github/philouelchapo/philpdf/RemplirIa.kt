package io.github.philouelchapo.philpdf

import android.content.Context
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
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
import com.artifex.mupdf.fitz.PDFWidget
import kotlinx.coroutines.launch
import org.json.JSONArray
import org.json.JSONObject

/** Consigne de « Remplir avec l'IA » (la meme sous Windows, app/dialogues_ia.py). */
private const val CONSIGNES_REMPLIR = """Tu aides à remplir un formulaire PDF. On te donne le texte du document, la liste de ses champs
(nom technique, libellé visible, type, choix possibles, valeur actuelle) et ce que la personne t'indique sur elle ou sur
la démarche. Réponds en JSON : {"valeurs": {"<nom technique du champ>": "<valeur>"}, "manque": ["<information
qu'il faudrait pour remplir un champ resté vide>"]}.
Règles : ne remplis un champ que si l'information est donnée par la personne ou évidente d'après le document ; n'invente
rien (ni numéro, ni date, ni adresse). Case à cocher : "oui" ou "non". Liste ou bouton radio : une des valeurs
possibles, recopiée exactement. Dates au format du document (sinon JJ/MM/AAAA). Champ de signature : jamais."""

private class Propose(val champ: ChampIa, valeur: String, coche: Boolean) {
    var valeur by mutableStateOf(valeur)
    var coche by mutableStateOf(coche)
}

private fun prefs(ctx: Context) = ctx.getSharedPreferences("ia", Context.MODE_PRIVATE)

/** Plus > Remplir avec l'IA : vous dites ce que l'IA doit savoir, elle propose une valeur par champ, vous cochez et
 *  corrigez, puis c'est ecrit (une seule etape d'annulation). Rien n'est invente ; jamais la signature. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun RemplirIa(etat: EtatLecteur, fermer: () -> Unit) {
    val ctx = LocalContext.current
    val portee = rememberCoroutineScope()
    val champs by produceState<List<ChampIa>?>(null, etat.doc) { value = try { etat.doc.champsARemplir() } catch (_: Exception) { emptyList() } }
    val texte by produceState<String?>(null, etat.doc) { value = try { etat.doc.texteDocument(40_000) } catch (_: Exception) { "" } }
    var infos by remember { mutableStateOf(prefs(ctx).getString("infos_formulaire", "") ?: "") }
    var garder by remember { mutableStateOf((prefs(ctx).getString("infos_formulaire", "") ?: "").isNotEmpty()) }
    var envoyer by remember { mutableStateOf(false) }
    var proposes by remember { mutableStateOf<List<Propose>?>(null) }
    var manque by remember { mutableStateOf<List<String>>(emptyList()) }
    var occupe by remember { mutableStateOf(false) }
    val cs = champs; val t = texte
    when {
        cs == null || t == null -> {}
        cs.isEmpty() -> AlertDialog(onDismissRequest = fermer, title = { Text(stringResource(R.string.rempl_titre)) },
            text = { Text(stringResource(R.string.rempl_aucun_champ)) },
            confirmButton = { TextButton(onClick = fermer) { Text(stringResource(R.string.ok)) } })
        proposes != null -> Fenetre(fermer) {
            val l = proposes!!
            Column(Modifier.fillMaxSize()) {
                Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(16.dp)) {
                    Text(stringResource(R.string.rempl_titre), fontSize = 20.sp, fontWeight = FontWeight.SemiBold)
                    Text(stringResource(R.string.rempl_verifier), fontSize = 13.sp, color = Color.Gray)
                    Spacer(Modifier.height(8.dp))
                    if (l.isEmpty()) Text(stringResource(R.string.rempl_rien))
                    l.forEach { p ->
                        Surface(Modifier.fillMaxWidth().padding(vertical = 4.dp), shape = RoundedCornerShape(10.dp), color = Color.White) {
                            Column(Modifier.padding(8.dp)) {
                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    Checkbox(p.coche, { p.coche = it })
                                    Column(Modifier.weight(1f)) {
                                        Text((p.champ.libelle.ifEmpty { p.champ.nom }), fontWeight = FontWeight.SemiBold, fontSize = 14.sp)
                                        Text(stringResource(R.string.rempl_page_actuel, p.champ.page + 1, p.champ.valeur.ifEmpty { "—" }),
                                            fontSize = 12.sp, color = Color.Gray)
                                    }
                                }
                                if (p.champ.genre == PDFWidget.TYPE_CHECKBOX || p.champ.choix.isNotEmpty()) {
                                    val choix = if (p.champ.genre == PDFWidget.TYPE_CHECKBOX) listOf("oui", "non") else p.champ.choix
                                    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                                        choix.forEach { c -> FilterChip(p.valeur == c, { p.valeur = c; p.coche = true }, { Text(c) }) }
                                    }
                                } else OutlinedTextField(p.valeur, { p.valeur = it; p.coche = true }, Modifier.fillMaxWidth(), singleLine = false)
                            }
                        }
                    }
                    if (manque.isNotEmpty()) {
                        Spacer(Modifier.height(8.dp))
                        Text(stringResource(R.string.rempl_manque) + "\n• " + manque.take(8).joinToString("\n• "), fontSize = 13.sp, color = Color(0xFF8A5A00))
                    }
                }
                FlowRow(Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 8.dp),
                    horizontalArrangement = Arrangement.spacedBy(4.dp, Alignment.End)) {
                    TextButton(onClick = fermer, enabled = !occupe) { Text(stringResource(R.string.annuler)) }
                    Button(onClick = {
                        occupe = true
                        portee.launch {
                            val (n, refus) = etat.doc.remplirIa(l.filter { it.coche }.map { it.champ to it.valeur })
                            etat.message = ctx.getString(R.string.rempl_fait, n) + if (refus.isNotEmpty()) "\n" + refus.joinToString("\n") else ""
                            occupe = false
                            fermer()
                        }
                    }, enabled = !occupe && l.any { it.coche }, colors = ButtonDefaults.buttonColors(containerColor = ROUGE)) {
                        Text(stringResource(R.string.rempl_remplir)) }
                }
            }
        }
        envoyer -> {
            val description = JSONArray(cs.map { c ->
                JSONObject().put("nom", c.nom).put("libelle", c.libelle).put("type", when (c.genre) {
                    PDFWidget.TYPE_CHECKBOX -> "case"; PDFWidget.TYPE_TEXT -> "texte"; else -> "liste" })
                    .put("choix", JSONArray(c.choix)).put("valeur", c.valeur)
            })
            val envoi = JSONObject().put("champs", description).toString() + "\n\nCe que la personne indique :\n" +
                infos.ifBlank { "(rien)" } + "\n\nTexte du document :\n" + t
            EnvoiIa(infos + "\n" + t, stringResource(R.string.rempl_attente), {
                Ia.lireJson(Ia.demander(ctx, CONSIGNES_REMPLIR, envoi, json = true, maxJetons = 6000))
            }, { r ->
                val v = r.optJSONObject("valeurs") ?: JSONObject()
                proposes = cs.filter { v.has(it.nom) && v.optString(it.nom).isNotBlank() }.map { c ->
                    Propose(c, v.optString(c.nom), c.valeur.isEmpty() || c.valeur == "non")
                }
                manque = r.optJSONArray("manque")?.let { a -> (0 until a.length()).map { a.optString(it) }.filter { it.isNotBlank() } } ?: emptyList()
            }, fermer)
        }
        else -> Fenetre(fermer) {
            Column(Modifier.fillMaxSize()) {
                Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(16.dp)) {
                    Text(stringResource(R.string.rempl_titre), fontSize = 20.sp, fontWeight = FontWeight.SemiBold)
                    Text(stringResource(R.string.rempl_aide, cs.size), fontSize = 13.sp, color = Color.Gray)
                    Spacer(Modifier.height(8.dp))
                    OutlinedTextField(infos, { infos = it }, Modifier.fillMaxWidth().heightIn(min = 140.dp),
                        placeholder = { Text(stringResource(R.string.rempl_exemple), fontSize = 13.sp) })
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Checkbox(garder, { garder = it })
                        Text(stringResource(R.string.rempl_garder), fontSize = 13.sp)
                    }
                }
                FlowRow(Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 8.dp),
                    horizontalArrangement = Arrangement.spacedBy(4.dp, Alignment.End)) {
                    TextButton(onClick = fermer) { Text(stringResource(R.string.annuler)) }
                    Button(onClick = {
                        prefs(ctx).edit().putString("infos_formulaire", if (garder) infos.trim() else "").apply()
                        envoyer = true
                    }, colors = ButtonDefaults.buttonColors(containerColor = ROUGE)) { Text(stringResource(R.string.rempl_proposer)) }
                }
            }
        }
    }
}
