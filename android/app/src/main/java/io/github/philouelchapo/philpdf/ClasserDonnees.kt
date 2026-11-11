package io.github.philouelchapo.philpdf

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
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
import kotlinx.coroutines.launch
import org.json.JSONObject
import java.text.Normalizer

// ================================================================ renommer et classer (comme sous Windows)
/** Ce que vos postes ont appris (PhilPDF/apprentissage/classement.json du Drive de synchronisation) : pour chaque
 *  expediteur, le dossier ou ranger ses courriers. Le telephone ne garde que les dossiers d'un Drive qu'il connait. */
object Classement {
    data class DossierDrive(val compte: Nuage, val chemin: String) {
        fun forme(ctx: Context) = "distant:${compte.fournisseur(ctx).cle}||:$chemin"
        fun libelle(ctx: Context) = compte.libelle(ctx) + " › " + chemin.ifEmpty { "/" }
    }

    fun cle(nom: String): String = Normalizer.normalize(nom, Normalizer.Form.NFKD).replace(Regex("[^\\p{ASCII}]"), "")
        .lowercase().replace(Regex("[^a-z0-9]+"), " ").trim()

    private suspend fun lireJson(ctx: Context): JSONObject =
        try { Nuage.synchro(ctx)?.lire(ctx, "apprentissage/classement.json")?.let { JSONObject(String(it)) } } catch (_: Exception) { null } ?: JSONObject()

    /** forme « distant:<genre>|...:/chemin » -> dossier d'un compte de ce telephone, ou null. */
    private fun versDrive(ctx: Context, forme: String): DossierDrive? {
        if (!forme.startsWith("distant:")) return null
        val reste = forme.removePrefix("distant:")
        val genre = reste.substringBefore("|")
        val chemin = reste.substringAfter(":", "")
        if (genre !in CLES_NUAGES) return null
        val c = Nuage.liste(ctx).filter { it.fournisseur(ctx).cle == genre }.let { l -> l.firstOrNull { it == Nuage.synchro(ctx) } ?: l.firstOrNull() } ?: return null
        return DossierDrive(c, chemin)
    }

    /** (dossiers connus, les plus utilises d'abord ; dossier appris pour cet expediteur ou null). */
    suspend fun dossiers(ctx: Context, expediteur: String): Pair<List<DossierDrive>, DossierDrive?> {
        val ex = lireJson(ctx).optJSONObject("expediteurs") ?: JSONObject()
        val compte = HashMap<String, Pair<DossierDrive, Int>>()
        for (k in ex.keys()) {
            val e = ex.optJSONObject(k) ?: continue
            val d = versDrive(ctx, e.optString("dossier")) ?: continue
            val id = d.compte.id + d.chemin
            compte[id] = d to ((compte[id]?.second ?: 0) + e.optInt("n", 1))
        }
        val appris = ex.optJSONObject(cle(expediteur))?.let { versDrive(ctx, it.optString("dossier")) }
        return compte.values.sortedByDescending { it.second }.map { it.first } to appris
    }

    /** Retient le choix (sur le Drive : tous vos postes l'apprennent). */
    suspend fun retenir(ctx: Context, expediteur: String, d: DossierDrive) {
        val k = cle(expediteur)
        if (k.isEmpty()) return
        val n = Nuage.synchro(ctx) ?: return
        try {
            val j = lireJson(ctx)
            val ex = j.optJSONObject("expediteurs") ?: JSONObject().also { j.put("expediteurs", it) }
            val ancien = ex.optJSONObject(k)
            val forme = d.forme(ctx)
            ex.put(k, JSONObject().put("nom", expediteur).put("dossier", forme)
                .put("n", if (ancien?.optString("dossier") == forme) ancien.optInt("n", 1) + 1 else 1)
                .put("maj", java.time.LocalDateTime.now().withNano(0).toString()))
            n.deposer(ctx, "apprentissage", "classement.json", j.toString(1).toByteArray())
        } catch (e: Exception) { Journal.ecrire("classer", "classement non retenu ($e)") }
    }
}

private const val CONSIGNES_CLASSER = """Tu aides à ranger des courriers et documents PDF. Lis le document et réponds en JSON :
{"date": "AAAA-MM-JJ (date du document)", "expediteur": "<organisme ou personne qui l'envoie, nom court usuel,
ex. CPAM, URSSAF, DGFiP, EDF, Maître Dupont>", "objet": "<objet en 2 à 6 mots>",
"type": "<facture, courrier, contrat, relevé, avis, attestation...>",
"dossier": "<un des dossiers proposés qui convient le mieux, recopié exactement, ou chaîne vide>"}"""

/** Plus > Renommer et classer : nom propose par l'IA, dossier du Drive appris par vos postes (ou un autre), puis
 *  envoi sur le Drive ; ou « Sur le telephone... » avec ce nom. Le document ouvert ne change pas. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun ClasserIa(etat: EtatLecteur, fermer: () -> Unit) {
    val ctx = LocalContext.current
    val portee = rememberCoroutineScope()
    val texte by produceState<String?>(null, etat.doc) { value = try { etat.doc.texteDocument(40_000) } catch (_: Exception) { "" } }
    val connus by produceState<List<Classement.DossierDrive>?>(null) { value = try { Classement.dossiers(ctx, "").first } catch (_: Exception) { emptyList() } }
    var r by remember { mutableStateOf<JSONObject?>(null) }
    var nom by remember { mutableStateOf("") }
    var choisi by remember { mutableStateOf<Classement.DossierDrive?>(null) }
    var autreCompte by remember { mutableStateOf<Nuage?>(Nuage.prefere(ctx)) }
    var autreChemin by remember { mutableStateOf("") }
    var occupe by remember { mutableStateOf(false) }
    val t = texte; val cs = connus
    when {
        t == null || cs == null -> {}
        t.isBlank() -> AlertDialog(onDismissRequest = fermer, title = { Text(stringResource(R.string.cls_titre)) },
            text = { Text(stringResource(R.string.ia_sans_texte)) },
            confirmButton = { if (etat.doc.modifiable) TextButton(onClick = { fermer(); etat.ocr = 0 }) { Text(stringResource(R.string.ocr_titre_menu)) } },
            dismissButton = { TextButton(onClick = fermer) { Text(stringResource(R.string.fermer)) } })
        r == null -> EnvoiIa(t, stringResource(R.string.ia_lit_document), {
            val jour = java.text.SimpleDateFormat("yyyy-MM-dd", java.util.Locale.US).format(java.util.Date())
            val liste = cs.take(60).joinToString("\n") { it.chemin }.ifEmpty { "(aucun pour l'instant)" }
            Ia.lireJson(Ia.demander(ctx, "$CONSIGNES_CLASSER\nDate du jour : $jour.\nDossiers proposés :\n$liste", t, json = true))
        }, { j ->
            portee.launch {
                val (_, appris) = Classement.dossiers(ctx, j.optString("expediteur"))
                choisi = appris ?: cs.firstOrNull { it.chemin == j.optString("dossier") }
                nom = nomPropose(j)
                r = j
            }
        }, fermer)
        else -> Fenetre({ if (!occupe) fermer() }) {
            val j = r!!
            Column(Modifier.fillMaxSize().background(Color.White)) {
                Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(16.dp)) {
                    Text(stringResource(R.string.cls_titre), fontSize = 20.sp, fontWeight = FontWeight.SemiBold)
                    Text(listOf(j.optString("expediteur"), j.optString("type"), j.optString("objet")).filter { it.isNotBlank() }.joinToString(" · "),
                        fontSize = 13.sp, color = Color.Gray)
                    Spacer(Modifier.height(8.dp))
                    OutlinedTextField(nom, { nom = it }, Modifier.fillMaxWidth(), label = { Text(stringResource(R.string.cls_nom)) })
                    Spacer(Modifier.height(10.dp))
                    Text(stringResource(R.string.cls_dossier), fontWeight = FontWeight.SemiBold)
                    if (cs.isEmpty()) Text(stringResource(R.string.cls_aucun_appris), fontSize = 12.sp, color = Color.Gray)
                    cs.take(12).forEach { d ->
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            RadioButton(choisi == d, { choisi = d })
                            Text(d.libelle(ctx), fontSize = 14.sp)
                        }
                    }
                    // autre dossier d'un compte relie (cree s'il n'existe pas)
                    val comptes = Nuage.liste(ctx).filter { it.connecte(ctx) }
                    if (comptes.isNotEmpty()) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            RadioButton(choisi?.let { c -> cs.none { it == c } } == true, { autreCompte?.let { choisi = Classement.DossierDrive(it, autreChemin.trim()) } })
                            Text(stringResource(R.string.cls_autre), fontSize = 14.sp)
                        }
                        FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            comptes.forEach { c -> FilterChip(autreCompte == c, { autreCompte = c; choisi = Classement.DossierDrive(c, autreChemin.trim()) },
                                { Text(c.libelle(ctx), fontSize = 12.sp) }) }
                        }
                        OutlinedTextField(autreChemin, { autreChemin = it; autreCompte?.let { c -> choisi = Classement.DossierDrive(c, it.trim()) } },
                            Modifier.fillMaxWidth(), singleLine = true, placeholder = { Text("/Factures/EDF") })
                    }
                    Spacer(Modifier.height(8.dp))
                    Text(stringResource(R.string.cls_aide), fontSize = 12.sp, color = Color.Gray)
                    BoutonSignalerIa("Renommer et classer") { j.toString(2) }
                }
                FlowRow(Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 8.dp),
                    horizontalArrangement = Arrangement.spacedBy(4.dp, Alignment.End)) {
                    TextButton(onClick = fermer, enabled = !occupe) { Text(stringResource(R.string.annuler)) }
                    TextButton(onClick = { fermer(); etat.enregistrerSous = nom.trim().let { if (it.lowercase().endsWith(".pdf")) it else "$it.pdf" } },
                        enabled = !occupe && nom.isNotBlank()) { Text(stringResource(R.string.cls_telephone)) }
                    Button(onClick = {
                        val d = choisi ?: return@Button
                        occupe = true
                        portee.launch {
                            val n = nom.trim().let { if (it.lowercase().endsWith(".pdf")) it else "$it.pdf" }
                            try {
                                val octets = etat.doc.octetsActuels(ctx)
                                val final = d.compte.envoyerChemin(ctx, d.chemin, n, octets)
                                Classement.retenir(ctx, j.optString("expediteur"), d)
                                etat.message = ctx.getString(R.string.cls_fait, d.compte.libelle(ctx) + " › " + final)
                                fermer()
                            } catch (e: Exception) {
                                Journal.ecrire("classer", e.toString())
                                etat.message = (e as? ErreurCompte)?.message ?: ctx.getString(R.string.cls_echec, e.message ?: e.javaClass.simpleName)
                                occupe = false
                            }
                        }
                    }, enabled = !occupe && nom.isNotBlank() && choisi != null,
                        colors = ButtonDefaults.buttonColors(containerColor = ROUGE)) { Text(stringResource(R.string.cls_classer)) }
                }
            }
        }
    }
}

// ================================================================ extraire les donnees (comme sous Windows)
private val MODELES_DONNEES = listOf(
    Triple("facture", R.string.don_facture, "fournisseur, numéro de facture, date, date d'échéance, client, montant HT, TVA (taux et montant), montant TTC, " +
        "moyen de paiement, IBAN du fournisseur ; et les lignes (désignation, quantité, prix unitaire, total)"),
    Triple("releve", R.string.don_releve, "banque, titulaire, numéro de compte (4 derniers chiffres seulement), période, solde initial, solde final ; et " +
        "les opérations (date, libellé, débit, crédit)"),
    Triple("courrier", R.string.don_courrier, "expéditeur, destinataire, date, référence ou numéro de dossier, objet, montants mentionnés, échéances et ce " +
        "qu'il faut faire"),
    Triple("perso", R.string.don_perso, ""))

private const val CONSIGNE_DONNEES = """Tu extrais les données d'un document. Champs voulus : CHAMPS.
Réponds en JSON : {"champs": [{"nom": "<nom du champ>", "valeur": "<valeur telle qu'écrite>"}],
"tableau": {"colonnes": ["..."], "lignes": [["...", "..."]]}}.
Mets "tableau" à null s'il n'y a pas de lignes répétées (articles, opérations...). Recopie les valeurs exactement
(nombres avec la virgule décimale, dates en JJ/MM/AAAA). Un champ absent du document : valeur vide, ne devine pas."""

private class ValeurDonnee(val nom: String, valeur: String) { var valeur by mutableStateOf(valeur) }

/** Plus > Extraire les donnees : facture, releve, courrier ou vos champs ; valeurs a verifier, puis copier ou
 *  partager en texte (colonnes separees par des tabulations : se colle dans un tableur). */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun ExtraireIa(etat: EtatLecteur, fermer: () -> Unit) {
    val ctx = LocalContext.current
    val prefs = remember { ctx.getSharedPreferences("ia", Context.MODE_PRIVATE) }
    val texte by produceState<String?>(null, etat.doc) { value = try { etat.doc.texteDocument(60_000) } catch (_: Exception) { "" } }
    var modele by remember { mutableStateOf(prefs.getString("donnees_modele", "facture") ?: "facture") }
    var perso by remember { mutableStateOf(prefs.getString("donnees_champs", "") ?: "") }
    var lancer by remember { mutableStateOf(false) }
    var valeurs by remember { mutableStateOf<List<ValeurDonnee>?>(null) }
    var tableau by remember { mutableStateOf<List<List<String>>>(emptyList()) }
    val t = texte
    fun enTexte(): String = valeurs.orEmpty().joinToString("\n") { "${it.nom}\t${it.valeur}" } +
        if (tableau.isNotEmpty()) "\n\n" + tableau.joinToString("\n") { it.joinToString("\t") } else ""
    when {
        t == null -> {}
        t.isBlank() -> AlertDialog(onDismissRequest = fermer, title = { Text(stringResource(R.string.don_titre)) },
            text = { Text(stringResource(R.string.ia_sans_texte)) },
            confirmButton = { if (etat.doc.modifiable) TextButton(onClick = { fermer(); etat.ocr = 0 }) { Text(stringResource(R.string.ocr_titre_menu)) } },
            dismissButton = { TextButton(onClick = fermer) { Text(stringResource(R.string.fermer)) } })
        valeurs != null -> Fenetre(fermer) {
            Column(Modifier.fillMaxSize().background(Color.White)) {
                Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(16.dp)) {
                    Text(stringResource(R.string.don_resultat), fontSize = 20.sp, fontWeight = FontWeight.SemiBold)
                    Text(stringResource(R.string.don_verifier), fontSize = 13.sp, color = Color.Gray)
                    valeurs!!.forEach { v -> OutlinedTextField(v.valeur, { v.valeur = it }, Modifier.fillMaxWidth(), label = { Text(v.nom) }) }
                    if (tableau.isNotEmpty()) {
                        Spacer(Modifier.height(10.dp))
                        Surface(shape = RoundedCornerShape(8.dp), color = Color.White) {
                            Column(Modifier.fillMaxWidth().padding(8.dp)) {
                                tableau.forEachIndexed { i, l ->
                                    Text(l.joinToString("  ·  "), fontSize = 12.sp, fontWeight = if (i == 0) FontWeight.SemiBold else FontWeight.Normal)
                                }
                            }
                        }
                    }
                    BoutonSignalerIa("Extraire les données") { enTexte() }
                }
                FlowRow(Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 8.dp),
                    horizontalArrangement = Arrangement.spacedBy(4.dp, Alignment.End)) {
                    TextButton(onClick = fermer) { Text(stringResource(R.string.fermer)) }
                    TextButton(onClick = {
                        (ctx.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager).setPrimaryClip(ClipData.newPlainText("PhilPDF", enTexte()))
                        etat.message = ctx.getString(R.string.don_copie)
                    }) { Text(stringResource(R.string.don_copier)) }
                    Button(onClick = {
                        ctx.startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).setType("text/plain")
                            .putExtra(Intent.EXTRA_SUBJECT, etat.doc.nom).putExtra(Intent.EXTRA_TEXT, enTexte()), null))
                    }, colors = ButtonDefaults.buttonColors(containerColor = ROUGE)) { Text(stringResource(R.string.don_partager)) }
                }
            }
        }
        lancer -> {
            val liste = if (modele == "perso") perso.trim() else MODELES_DONNEES.first { it.first == modele }.third
            EnvoiIa(t, stringResource(R.string.ia_lit_document), {
                Ia.lireJson(Ia.demander(ctx, CONSIGNE_DONNEES.replace("CHAMPS", liste), t, json = true, maxJetons = 6000))
            }, { j ->
                val a = j.optJSONArray("champs")
                valeurs = (0 until (a?.length() ?: 0)).mapNotNull { a!!.optJSONObject(it) }.map { ValeurDonnee(it.optString("nom"), it.optString("valeur")) }
                tableau = j.optJSONObject("tableau")?.let { tb ->
                    val col = tb.optJSONArray("colonnes")?.let { c -> (0 until c.length()).map { c.optString(it) } } ?: emptyList()
                    val lig = tb.optJSONArray("lignes")?.let { l -> (0 until l.length()).mapNotNull { l.optJSONArray(it) }.map { r -> (0 until r.length()).map { r.optString(it) } } } ?: emptyList()
                    if (lig.isEmpty()) emptyList() else listOf(col) + lig
                } ?: emptyList()
            }, fermer)
        }
        else -> Fenetre(fermer) {
            Column(Modifier.fillMaxSize().background(Color.White)) {
                Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(16.dp)) {
                    Text(stringResource(R.string.don_titre), fontSize = 20.sp, fontWeight = FontWeight.SemiBold)
                    Text(stringResource(R.string.don_aide), fontSize = 13.sp, color = Color.Gray)
                    Spacer(Modifier.height(8.dp))
                    MODELES_DONNEES.forEach { (k, lib, _) ->
                        Row(verticalAlignment = Alignment.CenterVertically) { RadioButton(modele == k, { modele = k }); Text(stringResource(lib)) }
                    }
                    if (modele == "perso") OutlinedTextField(perso, { perso = it }, Modifier.fillMaxWidth(),
                        placeholder = { Text(stringResource(R.string.don_perso_exemple), fontSize = 13.sp) })
                }
                FlowRow(Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 8.dp),
                    horizontalArrangement = Arrangement.spacedBy(4.dp, Alignment.End)) {
                    TextButton(onClick = fermer) { Text(stringResource(R.string.annuler)) }
                    Button(onClick = {
                        prefs.edit().putString("donnees_modele", modele).apply { if (modele == "perso") putString("donnees_champs", perso.trim()) }.apply()
                        lancer = true
                    }, enabled = modele != "perso" || perso.isNotBlank(),
                        colors = ButtonDefaults.buttonColors(containerColor = ROUGE)) { Text(stringResource(R.string.don_extraire)) }
                }
            }
        }
    }
}
