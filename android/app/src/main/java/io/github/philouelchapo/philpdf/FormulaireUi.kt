package io.github.philouelchapo.philpdf

import androidx.compose.foundation.layout.*
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
    AlertDialog(onDismissRequest = fermer,
        title = { Text(stringResource(R.string.champ_formulaire)) },
        text = {
            Column {
                OutlinedTextField(nom, { nom = it }, label = { Text(stringResource(R.string.nom_champ)) }, singleLine = true)
                Spacer(Modifier.height(8.dp))
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
