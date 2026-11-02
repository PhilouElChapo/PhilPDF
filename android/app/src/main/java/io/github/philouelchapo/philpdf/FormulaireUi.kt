package io.github.philouelchapo.philpdf

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.launch

/** « Detecter les champs » : PhilPDF propose, vous choisissez (cocher, renommer), puis « Creer ». */
@Composable
fun DetectionChamps(etat: EtatLecteur, fermer: () -> Unit) {
    val portee = rememberCoroutineScope()
    val d = etat.doc
    var liste by remember { mutableStateOf<List<ChampDetecte>?>(null) }
    var version by remember { mutableIntStateOf(0) }       // redessine apres une case cochee ou un nom change
    var occupe by remember { mutableStateOf(false) }
    LaunchedEffect(Unit) { liste = try { d.detecterChamps() } catch (_: Exception) { emptyList() } }
    Fenetre({ if (!occupe) fermer() }) {
        Surface(Modifier.fillMaxWidth(0.96f).widthIn(max = 620.dp).fillMaxHeight(0.92f), shape = RoundedCornerShape(16.dp)) {
            Column(Modifier.padding(16.dp)) {
                Text(stringResource(R.string.detecter_champs), fontWeight = FontWeight.SemiBold, fontSize = 19.sp)
                Spacer(Modifier.height(6.dp))
                val l = liste
                when {
                    l == null -> Row(verticalAlignment = Alignment.CenterVertically) {
                        CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp)
                        Spacer(Modifier.width(10.dp)); Text(stringResource(R.string.detection_en_cours))
                    }
                    l.isEmpty() -> Text(stringResource(R.string.detection_rien), color = Color.Gray, fontSize = 14.sp)
                    else -> {
                        Text(stringResource(R.string.detection_aide), fontSize = 13.sp, color = Color.Gray)
                        Spacer(Modifier.height(6.dp))
                        key(version) {
                            LazyColumn(Modifier.weight(1f, fill = false)) {
                                itemsIndexed(l) { i, c ->
                                    Row(verticalAlignment = Alignment.CenterVertically) {
                                        Checkbox(c.garder, { c.garder = it; version++ })
                                        Column(Modifier.weight(1f)) {
                                            var nom by remember(i) { mutableStateOf(c.nom) }
                                            OutlinedTextField(nom, { nom = it; c.nom = it }, singleLine = true, modifier = Modifier.fillMaxWidth(),
                                                textStyle = LocalTextStyle.current.copy(fontSize = 14.sp))
                                            Text(stringResource(if (c.genre == "case") R.string.champ_case else
                                                if (c.lignes) R.string.champ_texte_lignes else R.string.champ_texte) + " · " +
                                                stringResource(R.string.page_n, c.page + 1), fontSize = 11.sp, color = Color.Gray)
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
                Spacer(Modifier.height(10.dp))
                val n = liste?.count { it.garder } ?: 0
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                    TextButton(onClick = fermer, enabled = !occupe) { Text(stringResource(R.string.annuler)) }
                    Button(onClick = {
                        occupe = true
                        portee.launch {
                            val choisis = liste.orEmpty().filter { it.garder }
                            if (d.creerChamps(choisis)) Journal.ecrire("formulaire", "${d.nom} : ${choisis.size} champ(s) créé(s)")
                            occupe = false
                            fermer()
                        }
                    }, enabled = !occupe && n > 0, colors = ButtonDefaults.buttonColors(containerColor = ROUGE)) {
                        Text(stringResource(R.string.creer_champs, n))
                    }
                }
            }
        }
    }
}

/** Appui long sur un champ : son nom, le renommer, le supprimer. */
@Composable
fun OptionsChamp(etat: EtatLecteur, c: InfoChamp, fermer: () -> Unit) {
    val portee = rememberCoroutineScope()
    var nom by remember { mutableStateOf(c.nom) }
    var confirmer by remember { mutableStateOf(false) }
    var proprietes by remember { mutableStateOf(false) }
    if (proprietes) { DialogueProprietes(etat, c, fermer); return }
    AlertDialog(onDismissRequest = fermer,
        title = { Text(stringResource(R.string.champ_formulaire)) },
        text = {
            Column {
                OutlinedTextField(nom, { nom = it }, label = { Text(stringResource(R.string.nom_champ)) }, singleLine = true)
                Spacer(Modifier.height(8.dp))
                TextButton(onClick = { proprietes = true }) { Text(stringResource(R.string.proprietes)) }
                if (!confirmer) TextButton(onClick = { confirmer = true }) { Text(stringResource(R.string.supprimer_champ), color = ROUGE) }
                else TextButton(onClick = { portee.launch { etat.doc.supprimerChamp(c); fermer() } }) {
                    Text(stringResource(R.string.supprimer_champ_ok), color = ROUGE, fontWeight = FontWeight.SemiBold)
                }
            }
        },
        confirmButton = {
            TextButton(onClick = { portee.launch { if (nom.isNotBlank() && nom != c.nom) etat.doc.renommerChamp(c, nom.trim()); fermer() } }) {
                Text(stringResource(R.string.appliquer))
            }
        },
        dismissButton = { TextButton(onClick = fermer) { Text(stringResource(R.string.annuler)) } })
}

/** Proprietes d'un champ, comme sous Windows : format, controle, majuscules, valeur automatique, plage, calcul,
 *  liste dependante, afficher / masquer, aide. Gardees dans le champ et traduites en JavaScript d'Acrobat. */
@OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class)
@Composable
fun DialogueProprietes(etat: EtatLecteur, c: InfoChamp, fermer: () -> Unit) {
    val portee = rememberCoroutineScope()
    var charge by remember { mutableStateOf<Pair<org.json.JSONObject, List<String>>?>(null) }
    var reglages by remember { mutableStateOf<Pair<ChampsPdf.Proprietes, Map<String, Pair<String, String>>>?>(null) }
    var nbPages by remember { mutableIntStateOf(1) }
    LaunchedEffect(c) {
        reglages = etat.doc.proprietesChamp(c) ?: (ChampsPdf.Proprietes() to emptyMap())
        nbPages = etat.doc.nombrePages()
        charge = etat.doc.reglesChamp(c)
    }
    val (prop, js) = reglages ?: (ChampsPdf.Proprietes() to emptyMap())
    val perso = remember(js) { js.mapValues { it.value.second }.toMutableMap() }
    val (r0, noms) = charge ?: run {
        Fenetre(fermer) { Surface(shape = RoundedCornerShape(16.dp)) { CircularProgressIndicator(Modifier.padding(24.dp)) } }
        return
    }
    val r = remember(r0) { org.json.JSONObject(r0.toString()) }
    var v by remember { mutableIntStateOf(0) }                // redessine apres un changement
    fun maj(f: () -> Unit) { f(); v++ }
    val estTexte = c.genre == com.artifex.mupdf.fitz.PDFWidget.TYPE_TEXT
    val estListe = c.options.isNotEmpty() || c.genre == com.artifex.mupdf.fitz.PDFWidget.TYPE_COMBOBOX ||
        c.genre == com.artifex.mupdf.fitz.PDFWidget.TYPE_LISTBOX
    var choix by remember { mutableStateOf(c.options.joinToString("\n")) }
    Fenetre(fermer) {
        Surface(Modifier.fillMaxWidth(0.96f).widthIn(max = 640.dp).fillMaxHeight(0.94f), shape = RoundedCornerShape(16.dp)) {
            Column(Modifier.padding(16.dp)) {
                Text(stringResource(R.string.proprietes_champ, c.nom), fontWeight = FontWeight.SemiBold, fontSize = 18.sp)
                key(v) { Column(Modifier.weight(1f).verticalScroll(rememberScrollState())) {
                    fun noeud(k: String): org.json.JSONObject = r.optJSONObject(k) ?: org.json.JSONObject().also { r.put(k, it) }
                    SectionsReglages(c, prop, r, choix, nbPages) { f -> maj(f) }
                    if (estTexte) {
                        // ---- format
                        Titre(R.string.prop_format)
                        val f = noeud("format")
                        val g = f.optString("genre", "aucun")
                        val cle = when { g == "nombre" && f.optString("symbole").contains("€") -> "montant"
                            g == "masque" && f.optString("masque") == Regles.MASQUES["telephone"] -> "telephone"
                            g == "masque" && f.optString("masque") == Regles.MASQUES["code_postal"] -> "code_postal"; else -> g }
                        Puces(listOf("aucun" to stringResource(R.string.f_aucun), "date" to stringResource(R.string.f_date),
                            "heure" to stringResource(R.string.f_heure), "nombre" to stringResource(R.string.f_nombre),
                            "montant" to stringResource(R.string.f_montant), "pourcentage" to stringResource(R.string.f_pourcentage),
                            "telephone" to stringResource(R.string.f_telephone), "code_postal" to stringResource(R.string.f_code_postal),
                            "masque" to stringResource(R.string.f_masque)), cle) { k -> maj {
                            r.put("format", when (k) {
                                "date" -> org.json.JSONObject().put("genre", "date").put("date", "dd/mm/yyyy")
                                "heure" -> org.json.JSONObject().put("genre", "heure").put("heure", "HH:MM")
                                "nombre" -> org.json.JSONObject().put("genre", "nombre").put("decimales", 0).put("separateur", 2).put("negatif", 0).put("symbole", "").put("symbole_avant", false)
                                "montant" -> org.json.JSONObject().put("genre", "nombre").put("decimales", 2).put("separateur", 2).put("negatif", 0).put("symbole", "€").put("symbole_avant", false)
                                "pourcentage" -> org.json.JSONObject().put("genre", "pourcentage").put("decimales", 0).put("separateur", 2)
                                "telephone" -> org.json.JSONObject().put("genre", "masque").put("masque", Regles.MASQUES["telephone"])
                                "code_postal" -> org.json.JSONObject().put("genre", "masque").put("masque", Regles.MASQUES["code_postal"])
                                "masque" -> org.json.JSONObject().put("genre", "masque").put("masque", "")
                                else -> org.json.JSONObject().put("genre", "aucun")
                            }) } }
                        when (g) {
                            "date" -> Puces(Regles.DATES.map { it to it.replace("yyyy", "aaaa").replace("dd", "jj") }, f.optString("date")) { d -> maj { f.put("date", d) } }
                            "heure" -> Puces(Regles.HEURES.map { it to it }, f.optString("heure")) { d -> maj { f.put("heure", d) } }
                            "nombre", "pourcentage" -> {
                                Puces((0..4).map { "$it" to stringResource(R.string.f_decimales, it) }, f.optInt("decimales").toString()) { d -> maj { f.put("decimales", d.toInt()) } }
                                Puces(Regles.SEPARATEURS.map { (k, t) -> "$k" to t.first }, f.optInt("separateur", 2).toString()) { d -> maj { f.put("separateur", d.toInt()) } }
                                if (g == "nombre") Champ(f.optString("symbole"), stringResource(R.string.f_symbole)) { f.put("symbole", it) }
                            }
                            "masque" -> if (cle == "masque") Champ(f.optString("masque"), stringResource(R.string.f_masque_aide)) { f.put("masque", it) }
                        }
                        // ---- majuscules, controle, valeur automatique
                        Titre(R.string.prop_majuscules)
                        val m = r.opt("majuscules").let { if (it == true) "tout" else if (it is String) it else "non" }
                        Puces(listOf("non" to stringResource(R.string.maj_non), "tout" to "MAJUSCULES", "premiere" to stringResource(R.string.maj_premiere),
                            "mots" to stringResource(R.string.maj_mots)), m) { k -> maj { r.put("majuscules", if (k == "non") false else k) } }
                        Titre(R.string.prop_controle)
                        Puces(listOf("" to stringResource(R.string.f_aucun), "email" to "E-mail", "nir" to stringResource(R.string.ctrl_nir),
                            "iban" to "IBAN", "siret" to "SIRET", "rpps" to "RPPS"), if (r.isNull("controle")) "" else r.optString("controle")) { k ->
                            maj { r.put("controle", if (k.isEmpty()) org.json.JSONObject.NULL else k) } }
                        Titre(R.string.prop_auto)
                        Puces(listOf("" to stringResource(R.string.f_aucun), "date_clic" to stringResource(R.string.auto_date),
                            "heure_clic" to stringResource(R.string.auto_heure), "date_heure_clic" to stringResource(R.string.auto_date_heure)),
                            if (r.isNull("auto")) "" else r.optString("auto")) { k -> maj { r.put("auto", if (k.isEmpty()) org.json.JSONObject.NULL else k) } }
                        // ---- plage
                        Titre(R.string.prop_plage)
                        val pl = r.optJSONObject("plage")
                        Row {
                            Box(Modifier.weight(1f)) { Champ(pl?.takeIf { !it.isNull("min") }?.optDouble("min")?.let { Regles.valeurBrute(it) } ?: "", "min") {
                                noeud("plage").put("min", Regles.nombre(it) ?: org.json.JSONObject.NULL) } }
                            Spacer(Modifier.width(8.dp))
                            Box(Modifier.weight(1f)) { Champ(pl?.takeIf { !it.isNull("max") }?.optDouble("max")?.let { Regles.valeurBrute(it) } ?: "", "max") {
                                noeud("plage").put("max", Regles.nombre(it) ?: org.json.JSONObject.NULL) } }
                        }
                        // ---- calcul
                        Titre(R.string.prop_calcul)
                        val ca = r.optJSONObject("calcul")
                        val gc = ca?.optString("genre") ?: ""
                        Puces(listOf("" to stringResource(R.string.f_aucun), "somme" to stringResource(R.string.c_somme), "produit" to stringResource(R.string.c_produit),
                            "moyenne" to stringResource(R.string.c_moyenne), "min" to "Min", "max" to "Max", "formule" to stringResource(R.string.c_formule),
                            "copie" to stringResource(R.string.c_copie), "age" to stringResource(R.string.c_age), "ecart_jours" to stringResource(R.string.c_ecart),
                            "date_plus" to stringResource(R.string.c_date_plus)), gc) { k -> maj {
                            r.put("calcul", if (k.isEmpty()) org.json.JSONObject.NULL else org.json.JSONObject().put("genre", k).put("champs", org.json.JSONArray())) } }
                        if (ca != null) when (gc) {
                            "formule" -> Champ(ca.optString("formule"), stringResource(R.string.c_formule_aide)) { ca.put("formule", it) }
                            "copie", "age", "date_plus" -> {
                                Text(stringResource(R.string.c_source), fontSize = 12.sp, color = Color.Gray)
                                Puces(noms.map { it to it }, ca.optString("source")) { k -> maj { ca.put("source", k) } }
                                if (gc == "date_plus") Champ(ca.optInt("jours").toString(), stringResource(R.string.c_jours)) { ca.put("jours", it.toIntOrNull() ?: 0) }
                            }
                            "ecart_jours" -> {
                                Text(stringResource(R.string.c_debut), fontSize = 12.sp, color = Color.Gray)
                                Puces(noms.map { it to it }, ca.optString("debut")) { k -> maj { ca.put("debut", k) } }
                                Text(stringResource(R.string.c_fin), fontSize = 12.sp, color = Color.Gray)
                                Puces(noms.map { it to it }, ca.optString("fin")) { k -> maj { ca.put("fin", k) } }
                            }
                            else -> {
                                Text(stringResource(R.string.c_champs), fontSize = 12.sp, color = Color.Gray)
                                val sel = (0 until (ca.optJSONArray("champs")?.length() ?: 0)).map { ca.getJSONArray("champs").getString(it) }.toSet()
                                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                                    noms.forEach { n -> FilterChip(n in sel, { maj { ca.put("champs", org.json.JSONArray(if (n in sel) sel - n else sel + n)) } },
                                        label = { Text(n, fontSize = 12.sp) }) }
                                }
                            }
                        }
                    }
                    if (estListe) {
                        // ---- choix de la liste, et liste dependante d'un autre champ
                        Titre(R.string.liste_choix)
                        OutlinedTextField(choix, { choix = it }, minLines = 3, maxLines = 8, modifier = Modifier.fillMaxWidth())
                        Titre(R.string.prop_depend)
                        val de = r.optJSONObject("depend")
                        Puces(listOf("" to stringResource(R.string.f_aucun)) + noms.map { it to it }, de?.optString("parent") ?: "") { k -> maj {
                            r.put("depend", if (k.isEmpty()) org.json.JSONObject.NULL else org.json.JSONObject().put("parent", k).put("listes", de?.optJSONObject("listes") ?: org.json.JSONObject())) } }
                        if (de != null) {
                            val l = de.optJSONObject("listes") ?: org.json.JSONObject()
                            val texte = l.keys().asSequence().joinToString("\n") { k -> "$k : " + (0 until l.getJSONArray(k).length()).joinToString("; ") { l.getJSONArray(k).getString(it) } }
                            Text(stringResource(R.string.depend_aide), fontSize = 12.sp, color = Color.Gray)
                            var t by remember { mutableStateOf(texte) }
                            OutlinedTextField(t, { t = it
                                val o = org.json.JSONObject()
                                it.lines().forEach { ln -> val i = ln.indexOf(':'); if (i > 0) o.put(ln.take(i).trim(),
                                    org.json.JSONArray(ln.drop(i + 1).split(';').map { x -> x.trim() }.filter { x -> x.isNotEmpty() })) }
                                de.put("listes", o) }, minLines = 3, maxLines = 8, modifier = Modifier.fillMaxWidth())
                        }
                    }
                    // ---- afficher / masquer d'autres champs selon celui-ci
                    Titre(R.string.prop_affiche)
                    val af = r.optJSONObject("affiche")
                    Puces(listOf("" to stringResource(R.string.f_aucun), "coche" to stringResource(R.string.aff_coche), "valeur" to stringResource(R.string.aff_valeur)),
                        af?.optString("quand") ?: "") { k -> maj {
                        r.put("affiche", if (k.isEmpty()) org.json.JSONObject.NULL else org.json.JSONObject().put("quand", k).put("valeur", af?.optString("valeur") ?: "")
                            .put("cibles", af?.optJSONArray("cibles") ?: org.json.JSONArray())) } }
                    if (af != null) {
                        if (af.optString("quand") == "valeur") Champ(af.optString("valeur"), stringResource(R.string.aff_valeur_aide)) { af.put("valeur", it) }
                        Text(stringResource(R.string.aff_cibles), fontSize = 12.sp, color = Color.Gray)
                        val sel = (0 until (af.optJSONArray("cibles")?.length() ?: 0)).map { af.getJSONArray("cibles").getString(it) }.toSet()
                        FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            noms.forEach { n -> FilterChip(n in sel, { maj { af.put("cibles", org.json.JSONArray(if (n in sel) sel - n else sel + n)) } },
                                label = { Text(n, fontSize = 12.sp) }) }
                        }
                    }
                    // ---- aide
                    Titre(R.string.prop_aide)
                    Champ(r.optJSONObject("aide")?.optString("entree") ?: "", stringResource(R.string.aide_entree)) { noeud("aide").put("entree", it) }
                    Champ(r.optJSONObject("aide")?.optString("vide") ?: "", stringResource(R.string.aide_vide)) { noeud("aide").put("vide", it) }
                    SectionJavaScript(js, perso, r) { f -> maj(f) }
                } }
                Spacer(Modifier.height(10.dp))
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                    TextButton(onClick = fermer) { Text(stringResource(R.string.annuler)) }
                    Button(onClick = {
                        r.remove("_philpdf")
                        portee.launch {
                            val avant = js.mapValues { it.value.second }
                            etat.doc.ecrireReglesChamp(c, r, if (estListe) choix.lines().map { it.trim() }.filter { it.isNotEmpty() } else null,
                                prop, perso.filter { (k, v) -> v != (avant[k] ?: "") })
                            fermer()
                        }
                    }, colors = ButtonDefaults.buttonColors(containerColor = ROUGE)) { Text(stringResource(R.string.appliquer)) }
                }
            }
        }
    }
}

@Composable
internal fun Titre(t: Int) { Spacer(Modifier.height(12.dp)); Text(stringResource(t), fontWeight = FontWeight.SemiBold, fontSize = 14.sp) }

@OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class)
@Composable
internal fun Puces(options: List<Pair<String, String>>, actuel: String, choisir: (String) -> Unit) {
    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        options.forEach { (k, t) -> FilterChip(actuel == k, { choisir(k) }, label = { Text(t, fontSize = 12.sp) }) }
    }
}

@Composable
internal fun Champ(valeur: String, libelle: String, changer: (String) -> Unit) {
    var t by remember { mutableStateOf(valeur) }
    OutlinedTextField(t, { t = it; changer(it) }, label = { Text(libelle) }, singleLine = true, modifier = Modifier.fillMaxWidth())
}
