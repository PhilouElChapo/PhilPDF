package io.github.philouelchapo.philpdf

import android.content.Context
import android.net.Uri
import android.os.Build
import android.provider.Settings
import org.json.JSONArray
import org.json.JSONObject
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * Ce telephone (ou cette tablette) vu de vos PC : son nom, et la liste de ses fichiers recents ouverts depuis un Drive,
 * ecrite dans PhilPDF/appareils/<id>.json du Drive de synchronisation (jamais dans session.json, que les PC fusionnent).
 * Les PC les montrent dans « Sur vos autres postes » et les rouvrent directement sur le Drive (decision du 23/11/2026).
 * Les fichiers qui n'existent que sur le telephone (piece jointe, Telechargements) ne sont pas publies : un PC ne
 * pourrait pas les ouvrir.
 */
object Appareil {
    private fun prefs(ctx: Context) = ctx.getSharedPreferences("appareil", Context.MODE_PRIVATE)

    /** Nom de l'appareil (celui d'Android : Reglages › A propos), modifiable dans PhilPDF. */
    fun nom(ctx: Context): String = prefs(ctx).getString("nom", null)?.takeIf { it.isNotBlank() } ?: nomSysteme(ctx)

    fun nomSysteme(ctx: Context): String = try {
        Settings.Global.getString(ctx.contentResolver, Settings.Global.DEVICE_NAME)
    } catch (_: Exception) { null }?.takeIf { it.isNotBlank() } ?: Build.MODEL ?: "Android"

    fun changerNom(ctx: Context, nom: String) {
        prefs(ctx).edit().putString("nom", nom.trim()).remove("publie").apply()
        Journal.ecrire("appareil", "nom de l'appareil : « ${nom(ctx)} »")
    }

    private fun id(ctx: Context): String = prefs(ctx).getString("id", null) ?: java.util.UUID.randomUUID().toString().take(12)
        .also { prefs(ctx).edit().putString("id", it).apply() }

    /** Publie la liste si elle a change (au plus toutes les 10 minutes) ; rien sans Drive de synchronisation. */
    suspend fun publier(ctx: Context, forcer: Boolean = false) {
        val sync = Nuage.synchro(ctx) ?: return
        val p = prefs(ctx)
        if (!forcer && System.currentTimeMillis() - p.getLong("essai", 0) < 10 * 60_000) return
        p.edit().putLong("essai", System.currentTimeMillis()).apply()
        val fmt = SimpleDateFormat("yyyy-MM-dd'T'HH:mm", Locale.ROOT)
        val chemins = HashMap<String, String?>()
        try { JSONObject(p.getString("chemins", "{}")!!).let { o -> o.keys().forEach { chemins[it] = o.optString(it).ifEmpty { null } } } } catch (_: Exception) {}
        val recents = JSONArray()
        for (r in Recents.liste(ctx)) {
            val (_, o) = Distants.origine(ctx, Uri.parse(r.uri)) ?: continue      // seulement ce qui vient d'un Drive
            val n = Nuage.liste(ctx).firstOrNull { it.id == o.compte } ?: continue
            val cle = "${n.id}|${o.id}"
            val chemin = if (chemins.containsKey(cle)) chemins[cle] else n.cheminDe(ctx, o.id).also { chemins[cle] = it }
            if (chemin.isNullOrEmpty()) continue
            val f = n.fournisseur(ctx)
            recents.put(JSONObject().put("nom", o.nom.ifEmpty { r.nom }).put("date", fmt.format(Date(r.date)))
                .put("chemin", chemin)
                .put("distant", JSONObject().put("cle", "${f.cle}||").put("chemin", chemin)
                    .put("lieu", f.nom + (n.email(ctx)?.let { " · $it" } ?: ""))))
        }
        p.edit().putString("chemins", JSONObject(chemins.filterValues { it != null } as Map<*, *>).toString()).apply()
        val contenu = JSONObject().put(nom(ctx), JSONObject().put("systeme", "android").put("fichiers", JSONArray())
            .put("recents", recents)).toString()
        if (!forcer && contenu == p.getString("publie", null)) return
        val tout = JSONObject(contenu).apply { getJSONObject(nom(ctx)).put("maj", fmt.format(Date())) }
        try {
            if (sync.ecrireSynchro(ctx, "appareils", id(ctx) + ".json", tout.toString(1).toByteArray())) {
                p.edit().putString("publie", contenu).apply()
                Journal.ecrire("appareil", "« ${nom(ctx)} » : ${recents.length()} fichier(s) d'un Drive visibles sur vos PC")
            }
        } catch (e: Exception) {
            Journal.ecrire("appareil", "liste non publiée ($e)")
        }
    }
}
