package io.github.philouelchapo.philpdf

import android.accounts.Account
import android.accounts.AccountManager
import android.app.Activity
import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.net.Uri
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import com.artifex.mupdf.fitz.Cookie
import com.artifex.mupdf.fitz.Document
import com.artifex.mupdf.fitz.Matrix
import com.artifex.mupdf.fitz.android.AndroidDrawDevice
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.lang.ref.WeakReference
import java.net.HttpURLConnection
import java.net.InetAddress
import java.net.ServerSocket
import java.net.URL
import java.net.URLDecoder
import java.net.URLEncoder
import java.security.KeyStore
import java.security.MessageDigest
import java.security.SecureRandom
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/** Erreur a montrer telle quelle (en francais). */
class ErreurCompte(message: String) : Exception(message)

/** Fournisseur de stockage ou PhilPDF Windows synchronise son dossier « PhilPDF » (memes identifiants que Windows). */
data class Fournisseur(val cle: String, val nom: String, val auth: String, val jeton: String, val portee: String,
                       val extra: Map<String, String>, val retour: String, val ports: List<Int>, val id: String, val secret: String)

private val PORTS_FIXES = listOf(53682, 53683, 53684)   // declares chez Dropbox et Box (port exact exige)

val FOURNISSEURS = listOf(
    Fournisseur("gdrive", "Google Drive", "https://accounts.google.com/o/oauth2/v2/auth", "https://oauth2.googleapis.com/token",
        "https://www.googleapis.com/auth/drive.file", mapOf("access_type" to "offline", "prompt" to "consent"),
        "http://127.0.0.1:%d", listOf(0), BuildConfig.GOOGLE_ID, BuildConfig.GOOGLE_SECRET),
    Fournisseur("onedrive", "OneDrive", "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        "https://login.microsoftonline.com/common/oauth2/v2.0/token", "Files.ReadWrite offline_access User.Read",
        mapOf("prompt" to "select_account"), "http://localhost:%d", listOf(0),
        BuildConfig.ONEDRIVE_ID.ifEmpty { "e6479a20-b120-476d-ba0a-e4f37aa9841c" }, ""),
    Fournisseur("dropbox", "Dropbox", "https://www.dropbox.com/oauth2/authorize", "https://api.dropboxapi.com/oauth2/token", "",
        mapOf("token_access_type" to "offline"), "http://localhost:%d/", PORTS_FIXES, BuildConfig.DROPBOX_ID, BuildConfig.DROPBOX_SECRET),
    Fournisseur("box", "Box", "https://account.box.com/api/oauth2/authorize", "https://api.box.com/oauth2/token", "",
        emptyMap(), "http://localhost:%d/", PORTS_FIXES, BuildConfig.BOX_ID, BuildConfig.BOX_SECRET),
)

/**
 * Compte relie (un seul a la fois) : celui ou PhilPDF Windows synchronise son dossier PhilPDF.
 *
 * Google Drive : le compte Google deja present dans Android (aucun mot de passe, un seul « Autoriser ») ;
 * si Google refuse (PhilPDF Android pas encore declare chez Google), ou pour OneDrive, Dropbox, Box :
 * la page du fournisseur s'ouvre dans le navigateur, puis on revient a PhilPDF (comme sous Windows).
 * Meme autorisation limitee que sous Windows : PhilPDF ne lit que son dossier.
 */
object Nuage {
    /** Activite au premier plan : Android y affiche lui-meme l'ecran « Autoriser » quand il le faut. */
    var activite: WeakReference<Activity>? = null

    private var acces: String? = null
    private var expire = 0L
    private val ids = HashMap<String, String>()          // chemin relatif -> identifiant (Google, Box)

    private fun prefs(ctx: Context) = ctx.getSharedPreferences("compte", Context.MODE_PRIVATE)
    fun fournisseur(ctx: Context): Fournisseur =
        FOURNISSEURS.firstOrNull { it.cle == prefs(ctx).getString("fournisseur", "gdrive") } ?: FOURNISSEURS[0]
    fun email(ctx: Context): String? = prefs(ctx).getString("email", null)?.takeIf { it.isNotEmpty() }
    fun nom(ctx: Context): String? = prefs(ctx).getString("nom", null)
    fun mode(ctx: Context): String? = prefs(ctx).getString("mode", null)
    fun photo(ctx: Context): File = File(ctx.filesDir, "compte/photo.png")
    fun connecte(ctx: Context) = mode(ctx) != null
    fun disponible(f: Fournisseur) = f.id.isNotEmpty()

    /** Liste des comptes Google du telephone (ecran d'Android, aucune autorisation a demander). */
    fun intentChoisirGoogle(): Intent =
        AccountManager.newChooseAccountIntent(null, null, arrayOf("com.google"), null, null, null, null)

    fun deconnecter(ctx: Context) {
        val a = acces
        if (mode(ctx) == "telephone" && a != null) {
            try { AccountManager.get(ctx).invalidateAuthToken("com.google", a) } catch (_: Exception) {}
        }
        acces = null; expire = 0; ids.clear()
        prefs(ctx).edit().clear().apply()
        photo(ctx).delete()
        Bibliotheque.oublier(ctx)
    }

    // ------------------------------------------------------------ Google : compte du telephone
    /** Essaie le compte Google d'Android ; false si Google refuse (on proposera alors le navigateur). */
    suspend fun connecterTelephone(ctx: Context, email: String): Boolean = withContext(Dispatchers.IO) {
        try {
            val j = jetonTelephone(ctx, email)
            prefs(ctx).edit().clear().putString("fournisseur", "gdrive").putString("email", email).putString("mode", "telephone").apply()
            acces = j; expire = System.currentTimeMillis() + 50 * 60_000; ids.clear()
            true
        } catch (e: android.accounts.OperationCanceledException) {
            throw ErreurCompte("Connexion annulée.")
        } catch (e: Exception) {
            android.util.Log.w("PhilPDF", "compte telephone refuse : $e")
            false
        }
    }

    private fun jetonTelephone(ctx: Context, email: String): String {
        val f = AccountManager.get(ctx).getAuthToken(Account(email, "com.google"), "oauth2:" + FOURNISSEURS[0].portee,
            null, activite?.get(), null, null)
        return f.result.getString(AccountManager.KEY_AUTHTOKEN)      // bloquant : jamais sur le fil de l'interface
            ?: throw ErreurCompte("Google demande de vous reconnecter (Accueil, en haut à droite).")
    }

    // ------------------------------------------------------------ navigateur (tous les fournisseurs)
    /** Ouvre la page du fournisseur dans le navigateur et attend son retour sur l'adresse locale (PKCE). */
    suspend fun connecterNavigateur(ctx: Context, f: Fournisseur, indice: String?): Unit = withContext(Dispatchers.IO) {
        if (!disponible(f)) throw ErreurCompte("Cette version n'a pas l'identifiant ${f.nom} de PhilPDF.")
        val b64 = Base64.URL_SAFE or Base64.NO_PADDING or Base64.NO_WRAP
        val verif = Base64.encodeToString(ByteArray(48).also { SecureRandom().nextBytes(it) }, b64)
        val defi = Base64.encodeToString(MessageDigest.getInstance("SHA-256").digest(verif.toByteArray()), b64)
        val etatAleatoire = java.util.UUID.randomUUID().toString()
        val srv = f.ports.firstNotNullOfOrNull { p ->
            try { ServerSocket(p, 4, InetAddress.getByName("127.0.0.1")) } catch (_: Exception) { null }
        } ?: throw ErreurCompte("Les ports ${f.ports.joinToString()} sont occupés sur ce téléphone.")
        srv.use { s0 ->
            s0.soTimeout = 5 * 60_000
            val retour = f.retour.format(s0.localPort)
            val p = linkedMapOf("client_id" to f.id, "redirect_uri" to retour, "response_type" to "code",
                "code_challenge" to defi, "code_challenge_method" to "S256", "state" to etatAleatoire) + f.extra
            val params = p.toMutableMap()
            if (f.portee.isNotEmpty()) params["scope"] = f.portee
            if (!indice.isNullOrEmpty() && f.cle == "gdrive") params["login_hint"] = indice
            val url = f.auth + "?" + formulaire(params)
            withContext(Dispatchers.Main) {
                ctx.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
            }
            var code: String? = null
            while (code == null) {
                val so = try { s0.accept() } catch (e: java.net.SocketTimeoutException) {
                    throw ErreurCompte("Pas de réponse dans les 5 minutes : recommencez.")
                }
                so.use {
                    val ligne = it.getInputStream().bufferedReader().readLine() ?: ""
                    val chemin = ligne.split(" ").getOrNull(1) ?: ""
                    val q = chemin.substringAfter('?', "").split('&').filter { x -> '=' in x }
                        .associate { x -> URLDecoder.decode(x.substringBefore('='), "UTF-8") to URLDecoder.decode(x.substringAfter('='), "UTF-8") }
                    val ok = q["code"] != null && q["state"] == etatAleatoire
                    val page = pageRetour(f, ok, q["error"])
                    it.getOutputStream().write(("HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\n" +
                        "Content-Length: ${page.toByteArray().size}\r\nConnection: close\r\n\r\n$page").toByteArray())
                    it.getOutputStream().flush()
                    if (q["error"] != null) throw ErreurCompte("${f.nom} a refusé : ${q["error"]}")
                    if (ok) code = q["code"]
                }
            }
            val champs = mutableMapOf("code" to code!!, "client_id" to f.id, "redirect_uri" to retour,
                "grant_type" to "authorization_code", "code_verifier" to verif)
            if (f.secret.isNotEmpty()) champs["client_secret"] = f.secret
            val r = JSONObject(String(post(f.jeton, champs)))
            val durable = r.optString("refresh_token")
            if (durable.isEmpty()) throw ErreurCompte("${f.nom} n'a pas donné d'autorisation durable : recommencez.")
            acces = r.getString("access_token"); expire = System.currentTimeMillis() + (r.optLong("expires_in", 3600) - 120) * 1000
            ids.clear()
            prefs(ctx).edit().clear().putString("fournisseur", f.cle).putString("email", indice ?: "")
                .putString("mode", "navigateur").putString("jeton", Coffre.chiffrer(durable)).apply()
        }
    }

    private fun pageRetour(f: Fournisseur, ok: Boolean, erreur: String?): String {
        val lien = "intent://connecte#Intent;scheme=philpdf;package=${BuildConfig.APPLICATION_ID};end"
        val msg = if (ok) "PhilPDF est relié à votre ${f.nom}." else "Connexion refusée${erreur?.let { " ($it)" } ?: ""}."
        return """<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>PhilPDF</title><style>body{font-family:sans-serif;text-align:center;padding:40px 16px;background:#f3f3f3}
a{display:inline-block;margin-top:24px;padding:14px 28px;background:#C9252D;color:#fff;border-radius:24px;text-decoration:none;font-size:18px}</style></head>
<body><h2>$msg</h2><a href="$lien">Revenir à PhilPDF</a><script>setTimeout(function(){location.href="$lien"},400)</script></body></html>"""
    }

    // ------------------------------------------------------------ jeton d'acces et appels
    private suspend fun jeton(ctx: Context): String = withContext(Dispatchers.IO) {
        val a = acces
        if (a != null && System.currentTimeMillis() < expire) return@withContext a
        val j = when (mode(ctx)) {
            "telephone" -> jetonTelephone(ctx, email(ctx) ?: throw ErreurCompte("Aucun compte relié."))
                .also { expire = System.currentTimeMillis() + 50 * 60_000 }
            "navigateur" -> {
                val f = fournisseur(ctx)
                val r = prefs(ctx).getString("jeton", null)?.let { Coffre.dechiffrer(it) }
                    ?: throw ErreurCompte("Autorisation perdue : reconnectez le compte (Accueil, en haut à droite).")
                val champs = mutableMapOf("client_id" to f.id, "refresh_token" to r, "grant_type" to "refresh_token")
                if (f.secret.isNotEmpty()) champs["client_secret"] = f.secret
                val o = JSONObject(String(post(f.jeton, champs)))
                // Microsoft et Box donnent un nouveau jeton durable a chaque fois (l'ancien ne sert plus)
                o.optString("refresh_token").takeIf { it.isNotEmpty() && it != r }?.let {
                    prefs(ctx).edit().putString("jeton", Coffre.chiffrer(it)).apply()
                }
                expire = System.currentTimeMillis() + (o.optLong("expires_in", 3600) - 120) * 1000
                o.getString("access_token")
            }
            else -> throw ErreurCompte("Aucun compte relié.")
        }
        acces = j
        j
    }

    /** Appel authentifie ; renvoie (code, contenu). Un jeton perime est renouvele une fois. */
    private suspend fun appel(ctx: Context, methode: String, url: String, corps: ByteArray? = null,
                              entetes: Map<String, String> = emptyMap()): Pair<Int, ByteArray> = withContext(Dispatchers.IO) {
        for (essai in 0..1) {
            val j = jeton(ctx)
            val c = URL(url).openConnection() as HttpURLConnection
            c.requestMethod = methode
            c.connectTimeout = 15_000; c.readTimeout = 30_000
            c.setRequestProperty("Authorization", "Bearer $j")
            entetes.forEach { (k, v) -> c.setRequestProperty(k, v) }
            if (corps != null) { c.doOutput = true; c.outputStream.use { it.write(corps) } }
            else if (methode == "POST") { c.doOutput = true; c.setFixedLengthStreamingMode(0); c.outputStream.close() }
            val code = c.responseCode
            if (code == 401 && essai == 0) {
                if (mode(ctx) == "telephone") try { AccountManager.get(ctx).invalidateAuthToken("com.google", j) } catch (_: Exception) {}
                acces = null; expire = 0
                continue
            }
            val b = (if (code in 200..299) c.inputStream else c.errorStream)?.use { it.readBytes() } ?: ByteArray(0)
            return@withContext code to b
        }
        throw ErreurCompte("${fournisseur(ctx).nom} : autorisation refusée.")
    }

    private suspend fun json(ctx: Context, methode: String, url: String, corps: JSONObject? = null): JSONObject? {
        // POST sans argument (Dropbox) : corps JSON « null »
        val envoi = corps?.toString()?.toByteArray() ?: if (methode == "POST") "null".toByteArray() else null
        val (code, b) = appel(ctx, methode, url, envoi,
            if (envoi != null) mapOf("Content-Type" to "application/json") else emptyMap())
        if (code == 404 || code == 409) return null
        if (code !in 200..299) throw ErreurCompte("${fournisseur(ctx).nom} : erreur $code ${String(b).take(200)}")
        return JSONObject(String(b))
    }

    private fun post(url: String, champs: Map<String, String>): ByteArray {
        val c = URL(url).openConnection() as HttpURLConnection
        c.requestMethod = "POST"; c.doOutput = true; c.connectTimeout = 15_000; c.readTimeout = 30_000
        c.setRequestProperty("Content-Type", "application/x-www-form-urlencoded")
        c.outputStream.use { it.write(formulaire(champs).toByteArray()) }
        if (c.responseCode !in 200..299) {
            val msg = c.errorStream?.readBytes()?.let { String(it) }?.take(200) ?: ""
            throw ErreurCompte("Autorisation : erreur ${c.responseCode} $msg")
        }
        return c.inputStream.use { it.readBytes() }
    }

    private fun formulaire(m: Map<String, String>) =
        m.entries.joinToString("&") { enc(it.key) + "=" + enc(it.value) }

    private fun enc(t: String) = URLEncoder.encode(t, "UTF-8").replace("+", "%20")

    private const val GOOGLE = "https://www.googleapis.com/drive/v3"
    private const val GRAPH = "https://graph.microsoft.com/v1.0"
    private const val DBX = "https://api.dropboxapi.com/2"
    private const val DBX_CONTENU = "https://content.dropboxapi.com/2"
    private const val BOX = "https://api.box.com/2.0"

    // ------------------------------------------------------------ profil (pastille en haut a droite)
    suspend fun profil(ctx: Context) = withContext(Dispatchers.IO) {
        var nom: String? = null; var mail: String? = null; var image: ByteArray? = null
        when (fournisseur(ctx).cle) {
            "gdrive" -> json(ctx, "GET", "$GOOGLE/about?fields=user(emailAddress,displayName,photoLink)")?.optJSONObject("user")?.let { u ->
                nom = u.optString("displayName"); mail = u.optString("emailAddress")
                image = u.optString("photoLink").takeIf { it.isNotEmpty() }?.let { l -> try { URL(l).openStream().use { it.readBytes() } } catch (_: Exception) { null } }
            }
            "onedrive" -> {
                json(ctx, "GET", "$GRAPH/me?\$select=displayName,mail,userPrincipalName")?.let { u ->
                    nom = u.optString("displayName"); mail = u.optString("mail").ifEmpty { u.optString("userPrincipalName") }
                }
                image = try { appel(ctx, "GET", "$GRAPH/me/photo/\$value").let { (c, b) -> if (c in 200..299) b else null } } catch (_: Exception) { null }
            }
            "dropbox" -> json(ctx, "POST", "$DBX/users/get_current_account")?.let { u ->
                nom = u.optJSONObject("name")?.optString("display_name"); mail = u.optString("email")
                image = u.optString("profile_photo_url").takeIf { it.isNotEmpty() }?.let { l -> try { URL(l).openStream().use { it.readBytes() } } catch (_: Exception) { null } }
            }
            "box" -> json(ctx, "GET", "$BOX/users/me?fields=name,login")?.let { u -> nom = u.optString("name"); mail = u.optString("login") }
        }
        prefs(ctx).edit().apply {
            nom?.takeIf { it.isNotEmpty() }?.let { putString("nom", it) }
            mail?.takeIf { it.isNotEmpty() }?.let { putString("email", it) }
        }.apply()
        image?.let { photo(ctx).parentFile?.mkdirs(); photo(ctx).writeBytes(it) }
    }

    // ------------------------------------------------------------ dossier PhilPDF et lecture de ses fichiers
    /** Trouve le dossier PhilPDF (a la racine d'abord, sinon ailleurs) ; renvoie false s'il n'existe pas. */
    suspend fun trouverRacine(ctx: Context): Boolean {
        ids.clear()
        val r: String? = when (fournisseur(ctx).cle) {
            "gdrive" -> {
                val d = "mimeType = 'application/vnd.google-apps.folder' and name = 'PhilPDF' and trashed = false"
                gChercher(ctx, "$d and 'root' in parents").firstOrNull()?.getString("id")
                    ?: gChercher(ctx, d).firstOrNull { gEnfant(ctx, it.getString("id"), "preferences.json") != null }?.getString("id")
            }
            "onedrive" -> json(ctx, "GET", "$GRAPH/me/drive/root:/PhilPDF?\$select=id,folder")?.optString("id")
                ?: json(ctx, "GET", "$GRAPH/me/drive/root/search(q='PhilPDF')?\$select=id,name,folder")?.optJSONArray("value")?.let { a ->
                    (0 until a.length()).map { a.getJSONObject(it) }.firstOrNull { it.optString("name") == "PhilPDF" && it.has("folder") }?.optString("id")
                }
            "dropbox" -> (if (json(ctx, "POST", "$DBX/files/get_metadata", JSONObject().put("path", "/PhilPDF")) != null) "/PhilPDF" else null)
                ?: json(ctx, "POST", "$DBX/files/search_v2", JSONObject().put("query", "PhilPDF")
                    .put("options", JSONObject().put("filename_only", true)))?.optJSONArray("matches")?.let { a ->
                    (0 until a.length()).mapNotNull { a.getJSONObject(it).optJSONObject("metadata")?.optJSONObject("metadata") }
                        .firstOrNull { it.optString(".tag") == "folder" && it.optString("name") == "PhilPDF" }?.optString("path_lower")
                }
            "box" -> bEnfant(ctx, "0", "PhilPDF")
                ?: json(ctx, "GET", "$BOX/search?query=PhilPDF&type=folder&content_types=name&fields=id,name")?.optJSONArray("entries")?.let { a ->
                    (0 until a.length()).map { a.getJSONObject(it) }.firstOrNull { it.optString("name") == "PhilPDF" }?.optString("id")
                }
            else -> null
        }
        if (r.isNullOrEmpty()) return false
        ids[""] = r
        return true
    }

    /** Contenu d'un fichier du dossier PhilPDF (chemin relatif : « sauvegarde/index.json »), ou null s'il n'existe pas. */
    suspend fun lire(ctx: Context, rel: String): ByteArray? {
        if (ids[""] == null && !trouverRacine(ctx)) return null
        val racine = ids[""]!!
        val f = fournisseur(ctx)
        val (code, b) = when (f.cle) {
            "gdrive" -> {
                val id = idParChemin(ctx, rel) { p, n -> gEnfant(ctx, p, n)?.getString("id") } ?: return null
                appel(ctx, "GET", "$GOOGLE/files/$id?alt=media")
            }
            "onedrive" -> appel(ctx, "GET", "$GRAPH/me/drive/items/$racine:/" + rel.split("/").joinToString("/") { enc(it) } + ":/content")
            "dropbox" -> appel(ctx, "POST", "$DBX_CONTENU/files/download", ByteArray(0),
                mapOf("Dropbox-API-Arg" to ascii(JSONObject().put("path", "$racine/$rel").toString()), "Content-Type" to "text/plain; charset=dropbox-cors-hack"))
            "box" -> {
                val id = idParChemin(ctx, rel) { p, n -> bEnfant(ctx, p, n) } ?: return null
                appel(ctx, "GET", "$BOX/files/$id/content")
            }
            else -> return null
        }
        if (code == 404 || code == 409) return null
        if (code !in 200..299) throw ErreurCompte("${f.nom} : erreur $code ${String(b).take(200)}")
        return b
    }

    private suspend fun idParChemin(ctx: Context, rel: String, enfant: suspend (String, String) -> String?): String? {
        var chemin = ""
        var id = ids[""] ?: return null
        for (n in rel.split("/").filter { it.isNotEmpty() }) {
            chemin = if (chemin.isEmpty()) n else "$chemin/$n"
            id = ids[chemin] ?: (enfant(id, n) ?: return null).also { ids[chemin] = it }
        }
        return id
    }

    private fun ascii(t: String) = buildString { t.forEach { c -> if (c.code < 128) append(c) else append("\\u%04x".format(c.code)) } }

    private suspend fun gChercher(ctx: Context, q: String): List<JSONObject> {
        val url = "$GOOGLE/files?" + formulaire(mapOf("q" to q, "spaces" to "drive", "pageSize" to "1000", "fields" to "files(id,name,mimeType)"))
        val a = json(ctx, "GET", url)?.optJSONArray("files") ?: JSONArray()
        return (0 until a.length()).map { a.getJSONObject(it) }
    }

    private suspend fun gEnfant(ctx: Context, parent: String, nom: String): JSONObject? =
        gChercher(ctx, "name = '${nom.replace("\\", "\\\\").replace("'", "\\'")}' and '$parent' in parents and trashed = false").firstOrNull()

    private suspend fun bEnfant(ctx: Context, dossier: String, nom: String): String? {
        var debut = 0
        while (true) {
            val o = json(ctx, "GET", "$BOX/folders/$dossier/items?fields=id,name&limit=1000&offset=$debut") ?: return null
            val a = o.optJSONArray("entries") ?: return null
            (0 until a.length()).map { a.getJSONObject(it) }.firstOrNull { it.optString("name") == nom }?.let { return it.optString("id") }
            debut += a.length()
            if (a.length() == 0 || debut >= o.optInt("total_count", 0)) return null
        }
    }
}

/** Petit coffre : l'autorisation durable est chiffree par une clef qui ne quitte jamais le telephone. */
object Coffre {
    private const val NOM = "philpdf_compte"
    private fun clef(): SecretKey {
        val ks = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (ks.getKey(NOM, null) as? SecretKey)?.let { return it }
        val g = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        g.init(KeyGenParameterSpec.Builder(NOM, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
            .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build())
        return g.generateKey()
    }

    fun chiffrer(t: String): String {
        val c = Cipher.getInstance("AES/GCM/NoPadding").apply { init(Cipher.ENCRYPT_MODE, clef()) }
        return Base64.encodeToString(c.iv + c.doFinal(t.toByteArray()), Base64.NO_WRAP)
    }

    fun dechiffrer(t: String): String? = try {
        val b = Base64.decode(t, Base64.NO_WRAP)
        val c = Cipher.getInstance("AES/GCM/NoPadding").apply { init(Cipher.DECRYPT_MODE, clef(), GCMParameterSpec(128, b, 0, 12)) }
        String(c.doFinal(b, 12, b.size - 12))
    } catch (_: Exception) { null }
}

// ================================================================ postes et bibliotheque
data class Poste(val nom: String, val activite: String, val fichiers: Int, val reglagesPar: Boolean)

data class ElementBiblio(val id: String, val genre: String, val nom: String, val ext: String, val hash: String,
                         val maj: String, val categorie: String, val ratio: Float)

/** Ce que l'on lit dans le dossier PhilPDF du compte relie. */
data class EtatDrive(val trouve: Boolean, val postes: List<Poste>, val distants: List<ElementBiblio>, val nouveaux: Int)

/** Signatures, tampons, filigranes de PhilPDF Windows (PhilPDF/sauvegarde), recopies sur le telephone. */
object Bibliotheque {
    private fun dossier(ctx: Context) = File(ctx.filesDir, "bibliotheque")
    private fun index(ctx: Context) = File(dossier(ctx), "index.json")
    fun fichier(ctx: Context, e: ElementBiblio) = File(dossier(ctx), "${e.genre}/${e.id}${e.ext}")
    fun apercu(ctx: Context, e: ElementBiblio) = File(dossier(ctx), "apercus/${e.id}.png")

    fun oublier(ctx: Context) { dossier(ctx).deleteRecursively() }

    private fun versElement(o: JSONObject) = ElementBiblio(o.optString("id"), o.optString("genre"), o.optString("nom"),
        o.optString("ext", ".pdf").ifEmpty { ".pdf" }, o.optString("hash"), o.optString("maj"), o.optString("categorie"),
        o.optDouble("ratio", 3.0).toFloat())

    /** Elements deja recuperes sur ce telephone (utilisables sans reseau). */
    fun locaux(ctx: Context): List<ElementBiblio> = try {
        val a = JSONObject(index(ctx).readText()).getJSONArray("elements")
        (0 until a.length()).map { versElement(a.getJSONObject(it)) }.filter { apercu(ctx, it).exists() }
    } catch (_: Exception) { emptyList() }

    fun derniereRecuperation(ctx: Context): Long = index(ctx).takeIf { it.exists() }?.lastModified() ?: 0

    private suspend fun json(ctx: Context, rel: String): JSONObject? = try {
        Nuage.lire(ctx, rel)?.let { JSONObject(String(it)) }
    } catch (e: ErreurCompte) { throw e } catch (_: Exception) { null }

    /** Lit le dossier PhilPDF : postes (preferences.json, session.json) et bibliotheque (sauvegarde/index.json). */
    suspend fun lireDrive(ctx: Context): EtatDrive {
        if (!Nuage.trouverRacine(ctx)) return EtatDrive(false, emptyList(), emptyList(), 0)
        val pref = json(ctx, "preferences.json") ?: JSONObject()
        val sess = json(ctx, "session.json") ?: JSONObject()
        val par = pref.optJSONObject("communs")?.optString("par") ?: ""
        val noms = LinkedHashSet<String>()
        pref.optJSONObject("postes")?.keys()?.forEach { noms += it }
        sess.keys().forEach { if (sess.optJSONObject(it) != null) noms += it }
        val postes = noms.map { m ->
            val p = pref.optJSONObject("postes")?.optJSONObject(m)
            val s = sess.optJSONObject(m)
            Poste(m, maxOf(p?.optString("maj") ?: "", s?.optString("maj") ?: ""), s?.optJSONArray("fichiers")?.length() ?: 0, m == par)
        }.sortedByDescending { it.activite }
        val distants = json(ctx, "sauvegarde/index.json")?.let { ix ->
            val supprimes = ix.optJSONArray("supprimes")?.let { s -> (0 until s.length()).map { s.optString(it) }.toSet() } ?: emptySet()
            val a = ix.optJSONArray("elements") ?: JSONArray()
            (0 until a.length()).map { versElement(a.getJSONObject(it)) }.filter { it.id.isNotEmpty() && it.id !in supprimes }
        } ?: emptyList()
        val ici = locaux(ctx).associateBy { it.id }
        val nouveaux = distants.count { ici[it.id]?.hash != it.hash }
        return EtatDrive(true, postes, distants, nouveaux)
    }

    /** Recopie sur le telephone les elements nouveaux ou modifies ; retire ceux supprimes sur vos postes. */
    suspend fun recuperer(ctx: Context, distants: List<ElementBiblio>, avance: (Int, Int) -> Unit): Int {
        val ici = locaux(ctx).associateBy { it.id }
        val gardes = ArrayList<ElementBiblio>()
        var n = 0
        distants.forEachIndexed { i, e ->
            avance(i, distants.size)
            val deja = ici[e.id]
            if (deja != null && deja.hash == e.hash && fichier(ctx, deja).exists()) { gardes += deja; return@forEachIndexed }
            try {
                val octets = Nuage.lire(ctx, "sauvegarde/${e.genre}/${e.id}${e.ext}") ?: return@forEachIndexed
                val dest = fichier(ctx, e)
                val ratio = withContext(Dispatchers.IO) {
                    dest.parentFile?.mkdirs()
                    dest.writeBytes(octets)
                    rendreApercu(dest, apercu(ctx, e))
                }
                gardes += e.copy(ratio = ratio)
                n++
            } catch (ex: Exception) {
                android.util.Log.w("PhilPDF", "bibliotheque ${e.nom} : $ex")
                deja?.let { gardes += it }
            }
        }
        avance(distants.size, distants.size)
        // retires sur les postes : effaces ici aussi
        ici.values.filter { l -> gardes.none { it.id == l.id } }.forEach { fichier(ctx, it).delete(); apercu(ctx, it).delete() }
        val a = JSONArray()
        gardes.forEach { e ->
            a.put(JSONObject().put("id", e.id).put("genre", e.genre).put("nom", e.nom).put("ext", e.ext).put("hash", e.hash)
                .put("maj", e.maj).put("categorie", e.categorie).put("ratio", e.ratio.toDouble()))
        }
        index(ctx).parentFile?.mkdirs()
        index(ctx).writeText(JSONObject().put("elements", a).toString())
        return n
    }

    /** Image PNG transparente de l'element (premiere page), pour l'apercu et pour la poser. Renvoie largeur / hauteur. */
    private fun rendreApercu(source: File, dest: File): Float {
        val d = Document.openDocument(source.absolutePath)
        try {
            val p = d.loadPage(0)
            try {
                val b = p.bounds
                val w = (b.x1 - b.x0).coerceAtLeast(1f)
                val h = (b.y1 - b.y0).coerceAtLeast(1f)
                val z = (900f / w).coerceAtMost(900f / h).coerceAtMost(6f)
                val bm = Bitmap.createBitmap((w * z).toInt().coerceAtLeast(1), (h * z).toInt().coerceAtLeast(1), Bitmap.Config.ARGB_8888)
                bm.eraseColor(android.graphics.Color.TRANSPARENT)
                val dev = AndroidDrawDevice(bm, 0, 0)
                try { p.run(dev, Matrix(z, z), null as Cookie?); dev.close() } finally { dev.destroy() }
                dest.parentFile?.mkdirs()
                dest.outputStream().use { bm.compress(Bitmap.CompressFormat.PNG, 100, it) }
                return w / h
            } finally { p.destroy() }
        } finally { d.destroy() }
    }

    fun image(ctx: Context, e: ElementBiblio): Bitmap? = BitmapFactory.decodeFile(apercu(ctx, e).absolutePath)

    fun nomGenre(g: String) = when (g) {
        "signatures" -> "Signatures"; "tampons" -> "Tampons"; "filigranes" -> "Filigranes"; "paraphes" -> "Paraphes"
        else -> g.replaceFirstChar { it.uppercase() }
    }
}
