package io.github.philouelchapo.philpdf

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
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

    suspend fun chercher(actuelle: String): NouvelleVersion? = withContext(Dispatchers.IO) {
        try {
            val c = URL("https://api.github.com/repos/$DEPOT/releases/latest").openConnection() as HttpURLConnection
            c.connectTimeout = 8000
            c.readTimeout = 8000
            c.setRequestProperty("Accept", "application/vnd.github+json")
            val j = JSONObject(c.inputStream.bufferedReader().use { it.readText() })
            val v = j.getString("tag_name").trimStart('v')
            if (!plusRecente(v, actuelle)) return@withContext null
            val assets = j.getJSONArray("assets")
            var lien = "https://github.com/$DEPOT/releases/latest"
            for (i in 0 until assets.length()) {
                val a = assets.getJSONObject(i)
                if (a.getString("name").endsWith(".apk")) lien = a.getString("browser_download_url")
            }
            NouvelleVersion(v, lien)
        } catch (_: Exception) {
            null
        }
    }
}
