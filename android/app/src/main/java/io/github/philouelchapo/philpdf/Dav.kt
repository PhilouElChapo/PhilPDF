package io.github.philouelchapo.philpdf

import android.util.Xml
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.Credentials
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.xmlpull.v1.XmlPullParser
import java.net.URLDecoder
import java.net.URLEncoder
import java.util.concurrent.TimeUnit

/** WebDAV (pCloud par adresse e-mail et mot de passe, comme sous Windows). Android ne connait pas PROPFIND ni MKCOL
 *  avec HttpURLConnection : OkHttp les envoie. Les chemins partent de la racine du compte (« /PhilPDF/a.pdf »). */
object Dav {
    const val PCLOUD_EUROPE = "https://ewebdav.pcloud.com"
    const val PCLOUD_USA = "https://webdav.pcloud.com"

    private val client by lazy {
        OkHttpClient.Builder().connectTimeout(20, TimeUnit.SECONDS).readTimeout(90, TimeUnit.SECONDS)
            .writeTimeout(90, TimeUnit.SECONDS).build()
    }

    class Acces(val base: String, val utilisateur: String, val mdp: String)

    private fun url(a: Acces, chemin: String) = a.base.trimEnd('/') + chemin.split("/").joinToString("/") {
        URLEncoder.encode(it, "UTF-8").replace("+", "%20") }

    private suspend fun requete(a: Acces, methode: String, chemin: String, corps: ByteArray? = null,
                                entetes: Map<String, String> = emptyMap()): Pair<Int, ByteArray> = withContext(Dispatchers.IO) {
        val b = Request.Builder().url(url(a, chemin)).header("Authorization", Credentials.basic(a.utilisateur, a.mdp))
        entetes.forEach { (k, v) -> b.header(k, v) }
        b.method(methode, corps?.toRequestBody() ?: if (methode == "PUT" || methode == "PROPFIND" || methode == "MKCOL")
            ByteArray(0).toRequestBody() else null)
        client.newCall(b.build()).execute().use { r -> r.code to (r.body?.bytes() ?: ByteArray(0)) }
    }

    private val PROPFIND = ("<?xml version=\"1.0\"?><d:propfind xmlns:d=\"DAV:\"><d:prop><d:resourcetype/>" +
        "<d:getcontentlength/><d:getlastmodified/></d:prop></d:propfind>").toByteArray()

    /** Serveur pCloud du compte (Europe d'abord) ; null si l'adresse ou le mot de passe est refuse. */
    suspend fun trouverPcloud(utilisateur: String, mdp: String): String? {
        for (base in listOf(PCLOUD_EUROPE, PCLOUD_USA)) {
            val (code, _) = try { requete(Acces(base, utilisateur, mdp), "PROPFIND", "/", PROPFIND, mapOf("Depth" to "0")) }
                catch (e: Exception) { Journal.ecrire("compte", "pCloud ($base) : ${e.message}"); continue }
            Journal.ecrire("compte", "pCloud ($base) : réponse $code")
            if (code in 200..299) return base
        }
        return null
    }

    /** Contenu d'un dossier : (chemin, nom, dossier ?, taille, date) ; null s'il n'existe pas. */
    suspend fun lister(a: Acces, dossier: String): List<Entree>? {
        val d = dossier.ifEmpty { "/" }.let { if (it.endsWith("/")) it else "$it/" }
        val (code, b) = requete(a, "PROPFIND", d, PROPFIND, mapOf("Depth" to "1", "Content-Type" to "application/xml"))
        if (code == 404) return null
        if (code !in 200..299) throw ErreurCompte(Textes.t(R.string.err_code, "pCloud", code, String(b).take(200)))
        val out = ArrayList<Entree>()
        val p = Xml.newPullParser().apply { setFeature(XmlPullParser.FEATURE_PROCESS_NAMESPACES, true); setInput(b.inputStream(), "UTF-8") }
        var href = ""; var dos = false; var taille = 0L; var date = ""; var champ = ""
        while (p.next() != XmlPullParser.END_DOCUMENT) {
            when (p.eventType) {
                XmlPullParser.START_TAG -> when (p.name) {
                    "response" -> { href = ""; dos = false; taille = 0; date = "" }
                    "collection" -> dos = true
                    else -> champ = p.name
                }
                XmlPullParser.TEXT -> when (champ) {
                    "href" -> href += p.text.trim()
                    "getcontentlength" -> taille = p.text.trim().toLongOrNull() ?: 0
                    "getlastmodified" -> date += p.text.trim()
                }
                XmlPullParser.END_TAG -> {
                    if (p.name == "response") {
                        val chemin = URLDecoder.decode(java.net.URI(href).rawPath ?: href, "UTF-8").trimEnd('/')
                        if (chemin.isNotEmpty() && chemin != d.trimEnd('/'))
                            out += Entree(chemin, chemin.substringAfterLast('/'), dos, taille, date)
                    }
                    champ = ""
                }
            }
        }
        return out
    }

    suspend fun lire(a: Acces, chemin: String): ByteArray? {
        val (code, b) = requete(a, "GET", chemin)
        if (code == 404) return null
        if (code !in 200..299) throw ErreurCompte(Textes.t(R.string.err_code, "pCloud", code, String(b).take(200)))
        return b
    }

    suspend fun existe(a: Acces, chemin: String): Boolean =
        requete(a, "PROPFIND", chemin, PROPFIND, mapOf("Depth" to "0")).first in 200..299

    /** Ecrit (ou remplace) le fichier ; les dossiers manquants sont crees. */
    suspend fun ecrire(a: Acces, chemin: String, octets: ByteArray): Pair<Int, ByteArray> {
        val parties = chemin.split("/").filter { it.isNotEmpty() }.dropLast(1)
        for (i in 1..parties.size) {
            val d = "/" + parties.take(i).joinToString("/") + "/"
            if (!existe(a, d)) requete(a, "MKCOL", d)
        }
        return requete(a, "PUT", chemin, octets, mapOf("Content-Type" to "application/octet-stream"))
    }
}
