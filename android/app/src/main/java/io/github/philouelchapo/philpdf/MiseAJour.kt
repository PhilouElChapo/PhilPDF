package io.github.philouelchapo.philpdf

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

data class NouvelleVersion(val version: String, val lien: String)

/** Verifie sur GitHub s'il existe une version plus recente (meme depot que Windows et Linux). Rien n'est
 *  telecharge sans votre accord : l'Accueil propose, vous choisissez. */
object MiseAJour {
    private const val DEPOT = "PhilouElChapo/PhilPDF"

    private fun numeros(v: String): List<Int> = v.trimStart('v').split(".").map { p -> p.filter { it.isDigit() }.toIntOrNull() ?: 0 }

    fun plusRecente(a: String, b: String): Boolean {
        val x = numeros(a)
        val y = numeros(b)
        for (i in 0 until maxOf(x.size, y.size)) {
            val d = x.getOrElse(i) { 0 } - y.getOrElse(i) { 0 }
            if (d != 0) return d > 0
        }
        return false
    }

    /** Derniere publication Android (« android-v1.2.3 »), distincte de celles de Windows et Linux (« v0.9.x »). */
    suspend fun chercher(actuelle: String): NouvelleVersion? = withContext(Dispatchers.IO) {
        try {
            val c = URL("https://api.github.com/repos/$DEPOT/releases?per_page=40").openConnection() as HttpURLConnection
            c.connectTimeout = 8000
            c.readTimeout = 8000
            c.setRequestProperty("Accept", "application/vnd.github+json")
            val l = JSONArray(c.inputStream.bufferedReader().use { it.readText() })
            val j = (0 until l.length()).map { l.getJSONObject(it) }
                .filter { !it.optBoolean("draft") && it.optString("tag_name").startsWith("android-v") }
                .maxWithOrNull { a, b -> if (plusRecente(a.optString("tag_name").removePrefix("android-v"), b.optString("tag_name").removePrefix("android-v"))) 1 else -1 }
                ?: run { Journal.ecrire("mise à jour", "aucune publication Android trouvée"); return@withContext null }
            val v = j.getString("tag_name").removePrefix("android-v")
            if (!plusRecente(v, actuelle)) {
                Journal.ecrire("mise à jour", "vérification : $actuelle est à jour (dernière publiée : $v)")
                return@withContext null
            }
            val assets = j.getJSONArray("assets")
            var lien = j.optString("html_url", "https://github.com/$DEPOT/releases")
            for (i in 0 until assets.length()) {
                val a = assets.getJSONObject(i)
                if (a.getString("name") == "PhilPDF.apk") lien = a.getString("browser_download_url")   // universel
            }
            Journal.ecrire("mise à jour", "PhilPDF Android $v disponible (installée : $actuelle)")
            NouvelleVersion(v, lien)
        } catch (e: Exception) {
            Journal.ecrire("mise à jour", "vérification impossible ($e)")
            null
        }
    }
}
