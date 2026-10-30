package io.github.philouelchapo.philpdf

import android.content.Context
import android.content.Intent
import android.net.Uri
import org.json.JSONArray
import org.json.JSONObject

data class Recent(val uri: String, val nom: String, val date: Long, val pages: Int)

/** Fichiers recents de cet appareil : 30 fichiers au plus, 30 derniers jours (comme sous Windows). */
object Recents {
    private const val MAX = 30
    private const val JOURS = 30L

    private fun prefs(ctx: Context) = ctx.getSharedPreferences("philpdf", Context.MODE_PRIVATE)

    fun liste(ctx: Context): List<Recent> {
        val limite = System.currentTimeMillis() - JOURS * 24 * 3600 * 1000
        return try {
            val a = JSONArray(prefs(ctx).getString("recents", "[]"))
            (0 until a.length()).map { a.getJSONObject(it) }
                .map { Recent(it.getString("uri"), it.optString("nom"), it.optLong("date"), it.optInt("pages")) }
                .filter { it.date >= limite }
        } catch (_: Exception) {
            emptyList()
        }
    }

    private fun ecrire(ctx: Context, l: List<Recent>) {
        val a = JSONArray()
        l.take(MAX).forEach {
            a.put(JSONObject().put("uri", it.uri).put("nom", it.nom).put("date", it.date).put("pages", it.pages))
        }
        prefs(ctx).edit().putString("recents", a.toString()).apply()
    }

    fun ajouter(ctx: Context, uri: Uri, nom: String, pages: Int) {
        // garder le droit de rouvrir le fichier plus tard (seulement possible pour ce qui vient du selecteur)
        try {
            ctx.contentResolver.takePersistableUriPermission(uri, Intent.FLAG_GRANT_READ_URI_PERMISSION)
        } catch (_: Exception) {
        }
        val l = liste(ctx).filter { it.uri != uri.toString() }
        ecrire(ctx, listOf(Recent(uri.toString(), nom, System.currentTimeMillis(), pages)) + l)
    }

    fun retirer(ctx: Context, uri: String) {
        ecrire(ctx, liste(ctx).filter { it.uri != uri })
        Miniatures.fichier(ctx, uri).delete()
    }
}
