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
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeoutOrNull
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.io.IOException
import java.lang.ref.WeakReference
import java.net.HttpURLConnection
import java.net.InetSocketAddress
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

/** Fournisseur de stockage (memes applications declarees que PhilPDF Windows). */
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
    // pCloud : code + secret de l'application (pas de PKCE), jeton sans fin, serveur du compte (Europe ou Etats-Unis)
    Fournisseur("pcloud", "pCloud", "https://my.pcloud.com/oauth2/authorize", "https://%s/oauth2_token", "",
        emptyMap(), "http://localhost:%d/", PORTS_FIXES, BuildConfig.PCLOUD_ID, BuildConfig.PCLOUD_SECRET),
)

/** Tous les Drives relies « en direct » (meme liste que sous Windows). */
val CLES_NUAGES = setOf("gdrive", "onedrive", "dropbox", "box", "pcloud")

/** Element d'un dossier distant : id = identifiant du fournisseur (chemin pour Dropbox). */
data class Entree(val id: String, val nom: String, val dossier: Boolean, val taille: Long, val date: String)

/** Fichier ouvert depuis un compte : « Meme fichier » le renvoie a sa place. */
data class Origine(val compte: String, val id: String, val nom: String)

private const val GOOGLE = "https://www.googleapis.com/drive/v3"
private const val GOOGLE_ENVOI = "https://www.googleapis.com/upload/drive/v3"
private const val GRAPH = "https://graph.microsoft.com/v1.0"
private const val DBX = "https://api.dropboxapi.com/2"
private const val DBX_CONTENU = "https://content.dropboxapi.com/2"
private const val BOX = "https://api.box.com/2.0"
private const val BOX_ENVOI = "https://upload.box.com/api/2.0"

/**
 * Un compte relie : Google Drive (compte du telephone ou navigateur), OneDrive, Dropbox, Box.
 * Plusieurs comptes possibles ; l'un d'eux (au choix) est celui ou PhilPDF Windows synchronise son dossier PhilPDF.
 * Autorisation comme sous Windows (OAuth avec PKCE, aucun mot de passe donne a PhilPDF) ; jeton durable chiffre.
 */
class Nuage private constructor(val id: String) {
    private var acces: String? = null
    private var expire = 0L
    private val ids = HashMap<String, String>()          // chemin relatif dans PhilPDF -> identifiant (Google, Box)

    private fun prefs(ctx: Context) = ctx.getSharedPreferences("compte_$id", Context.MODE_PRIVATE)
    fun fournisseur(ctx: Context): Fournisseur =
        FOURNISSEURS.firstOrNull { it.cle == prefs(ctx).getString("fournisseur", "gdrive") } ?: FOURNISSEURS[0]
    fun email(ctx: Context): String? = prefs(ctx).getString("email", null)?.takeIf { it.isNotEmpty() }
    fun nom(ctx: Context): String? = prefs(ctx).getString("nom", null)?.takeIf { it.isNotEmpty() }
    fun mode(ctx: Context): String? = prefs(ctx).getString("mode", null)
    fun photo(ctx: Context): File = File(ctx.filesDir, "comptes/$id.png")
    fun connecte(ctx: Context) = mode(ctx) != null
    fun libelle(ctx: Context) = email(ctx) ?: nom(ctx) ?: fournisseur(ctx).nom

    private fun oublierJetons(ctx: Context) {
        val a = acces
        if (mode(ctx) == "telephone" && a != null) {
            try { AccountManager.get(ctx).invalidateAuthToken("com.google", a) } catch (_: Exception) {}
        }
        acces = null; expire = 0; ids.clear()
        prefs(ctx).edit().clear().apply()
        photo(ctx).delete()
    }

    // ------------------------------------------------------------ Google : compte du telephone
    /** Essaie le compte Google d'Android ; false si Google refuse (on proposera alors le navigateur). */
    suspend fun connecterTelephone(ctx: Context, email: String): Boolean = withContext(Dispatchers.IO) {
        try {
            val j = jetonTelephone(ctx, email)
            prefs(ctx).edit().clear().putString("fournisseur", "gdrive").putString("email", email).putString("mode", "telephone").apply()
            acces = j; expire = System.currentTimeMillis() + 50 * 60_000; ids.clear()
            enregistrer(ctx, this@Nuage)
            Journal.ecrire("compte", "Google Drive : relié par le compte du téléphone")
            true
        } catch (e: android.accounts.OperationCanceledException) {
            Journal.ecrire("compte", "Google Drive (compte du téléphone) : annulé")
            throw ErreurCompte(Textes.t(R.string.err_connexion_annulee))
        } catch (e: Exception) {
            Journal.ecrire("compte", "Google Drive (compte du téléphone) : refusé par Google ($e)")
            false
        }
    }

    private fun jetonTelephone(ctx: Context, email: String): String {
        val f = AccountManager.get(ctx).getAuthToken(Account(email, "com.google"), "oauth2:" + FOURNISSEURS[0].portee,
            null, activite?.get(), null, null)
        return f.result.getString(AccountManager.KEY_AUTHTOKEN)      // bloquant : jamais sur le fil de l'interface
            ?: throw ErreurCompte(Textes.t(R.string.err_google_reconnecter))
    }

    // ------------------------------------------------------------ navigateur (tous les fournisseurs)
    /**
     * Ouvre la page du fournisseur dans le navigateur et recoit sa reponse sur l'adresse locale (PKCE).
     * Le code n'est echange qu'une fois PhilPDF revenu au premier plan : Android coupe souvent le reseau
     * des applications en arriere-plan (« Unable to resolve host »).
     */
    suspend fun connecterNavigateur(ctx: Context, f: Fournisseur, indice: String?, attente: (String) -> Unit): Unit =
        withContext(Dispatchers.IO) {
            if (!disponible(f)) throw ErreurCompte(Textes.t(R.string.err_identifiant, f.nom))
            val b64 = Base64.URL_SAFE or Base64.NO_PADDING or Base64.NO_WRAP
            val verif = Base64.encodeToString(ByteArray(48).also { SecureRandom().nextBytes(it) }, b64)
            val defi = Base64.encodeToString(MessageDigest.getInstance("SHA-256").digest(verif.toByteArray()), b64)
            val etatAleatoire = java.util.UUID.randomUUID().toString()
            // toutes les adresses locales (127.0.0.1 ET ::1 : « localhost » vise l'une ou l'autre selon le navigateur) ;
            // toute connexion venant d'ailleurs que le telephone lui-meme est refusee
            val srv = f.ports.firstNotNullOfOrNull { p ->
                try { ServerSocket().apply { reuseAddress = true; bind(InetSocketAddress(p), 8) } } catch (_: Exception) { null }
            } ?: throw ErreurCompte(Textes.t(R.string.err_ports, f.ports.joinToString()))
            var code: String? = null
            var hotePcloud = "api.pcloud.com"
            var retour = ""
            try { srv.use { s0 ->
                s0.soTimeout = 5 * 60_000
                retour = f.retour.format(s0.localPort)
                val params = (linkedMapOf("client_id" to f.id, "redirect_uri" to retour, "response_type" to "code",
                    "state" to etatAleatoire) + f.extra).toMutableMap()
                if (f.cle != "pcloud") { params["code_challenge"] = defi; params["code_challenge_method"] = "S256" }
                if (f.portee.isNotEmpty()) params["scope"] = f.portee
                if (!indice.isNullOrEmpty() && f.cle == "gdrive") params["login_hint"] = indice
                val url = f.auth + "?" + formulaire(params)
                Journal.ecrire("compte", "${f.nom} : page d'autorisation ouverte dans le navigateur (retour sur $retour)")
                withContext(Dispatchers.Main) {
                    AttenteConnexion.demarrer(ctx, ctx.getString(R.string.attente_navigateur))
                    ctx.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
                }
                while (code == null) {
                    val so = try { s0.accept() } catch (e: java.net.SocketTimeoutException) {
                        throw ErreurCompte(Textes.t(R.string.err_pas_de_reponse))
                    }
                    so.use {
                        if (!it.inetAddress.isLoopbackAddress) return@use
                        val ligne = it.getInputStream().bufferedReader().readLine() ?: ""
                        val chemin = ligne.split(" ").getOrNull(1) ?: ""
                        val q = chemin.substringAfter('?', "").split('&').filter { x -> '=' in x }
                            .associate { x -> URLDecoder.decode(x.substringBefore('='), "UTF-8") to URLDecoder.decode(x.substringAfter('='), "UTF-8") }
                        val ok = q["code"] != null && q["state"] == etatAleatoire
                        val page = pageRetour(f, ok, q["error"], q.isEmpty())
                        it.getOutputStream().write(("HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\n" +
                            "Content-Length: ${page.toByteArray().size}\r\nConnection: close\r\n\r\n$page").toByteArray())
                        it.getOutputStream().flush()
                        Journal.ecrire("compte", "${f.nom} : réponse du navigateur — " + when {
                            ok -> "accord reçu"; q["error"] != null -> "refus (${q["error"]})"; else -> "autre demande (${chemin.take(40)})" })
                        if (q["error"] != null) throw ErreurCompte(Textes.t(R.string.err_a_refuse, f.nom, q["error_description"] ?: q["error"]))
                        if (ok) { code = q["code"]; hotePcloud = q["hostname"] ?: if (q["locationid"] == "2") "eapi.pcloud.com" else "api.pcloud.com" }
                    }
                }
            } } catch (e: Exception) { AttenteConnexion.arreter(ctx); Journal.ecrire("compte", "${f.nom} : échec ($e)"); throw e }
            // attendre le retour dans PhilPDF (bouton « Revenir a PhilPDF » de la page, ou l'utilisateur revient lui-meme)
            if (!premierPlan.value) {
                attente(ctx.getString(R.string.attente_retour))
                withTimeoutOrNull(10 * 60_000L) { premierPlan.first { it } }
                    ?: run { AttenteConnexion.arreter(ctx); throw ErreurCompte(Textes.t(R.string.err_pas_rouvert)) }
            }
            AttenteConnexion.arreter(ctx)
            Journal.ecrire("compte", "${f.nom} : PhilPDF revenu au premier plan, échange du code...")
            attente(ctx.getString(R.string.connexion_en_cours))
            if (f.cle == "pcloud") {
                // jeton sans fin, demande au serveur du compte ; garde chiffre avec ce serveur (« hote|jeton »)
                if (!Regex("[a-z0-9.-]+\\.pcloud\\.com").matches(hotePcloud)) throw ErreurCompte(Textes.t(R.string.err_pas_durable, f.nom))
                val r = try { JSONObject(String(post(f.jeton.format(hotePcloud), mapOf("client_id" to f.id, "client_secret" to f.secret,
                    "code" to code!!)))) } catch (e: Exception) { Journal.ecrire("compte", "pCloud : échange du code refusé (${e.message})"); throw e }
                val jt = r.optString("access_token")
                if (r.optInt("result", 0) != 0 || jt.isEmpty()) throw ErreurCompte(Textes.t(R.string.err_pas_durable, f.nom))
                acces = jt; expire = Long.MAX_VALUE; ids.clear()
                prefs(ctx).edit().clear().putString("fournisseur", f.cle).putString("email", indice ?: "")
                    .putString("mode", "navigateur").putString("jeton", Coffre.chiffrer("$hotePcloud|$jt")).apply()
                enregistrer(ctx, this@Nuage)
                Journal.ecrire("compte", "pCloud : relié ($hotePcloud)")
                return@withContext
            }
            val champs = mutableMapOf("code" to code!!, "client_id" to f.id, "redirect_uri" to retour,
                "grant_type" to "authorization_code", "code_verifier" to verif)
            if (f.secret.isNotEmpty()) champs["client_secret"] = f.secret
            val r = try { JSONObject(String(post(f.jeton, champs))) } catch (e: Exception) {
                Journal.ecrire("compte", "${f.nom} : échange du code refusé (${e.message})"); throw e
            }
            val durable = r.optString("refresh_token")
            if (durable.isEmpty()) throw ErreurCompte(Textes.t(R.string.err_pas_durable, f.nom))
            acces = r.getString("access_token"); expire = System.currentTimeMillis() + (r.optLong("expires_in", 3600) - 120) * 1000
            ids.clear()
            prefs(ctx).edit().clear().putString("fournisseur", f.cle).putString("email", indice ?: "")
                .putString("mode", "navigateur").putString("jeton", Coffre.chiffrer(durable)).apply()
            enregistrer(ctx, this@Nuage)
            Journal.ecrire("compte", "${f.nom} : relié")
        }

    private fun pageRetour(f: Fournisseur, ok: Boolean, erreur: String?, vide: Boolean): String {
        // pas de redirection automatique : certains navigateurs la bloquent (« null est inaccessible ») ; un vrai bouton marche partout
        val lien = "intent://connecte#Intent;scheme=philpdf;package=${BuildConfig.APPLICATION_ID};end"
        val msg = when {
            ok -> Textes.t(R.string.retour_relie, f.nom)
            vide -> Textes.t(R.string.retour_attente, f.nom)
            else -> Textes.t(R.string.retour_refuse, erreur?.let { " ($it)" } ?: "")
        }
        return """<!doctype html><html lang="${java.util.Locale.getDefault().language}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>PhilPDF</title><style>body{font-family:sans-serif;text-align:center;padding:40px 16px;background:#f3f3f3;color:#222}
a{display:inline-block;margin-top:24px;padding:16px 32px;background:#C9252D;color:#fff;border-radius:28px;text-decoration:none;font-size:20px}</style></head>
<body><h2>$msg</h2><a href="$lien">${Textes.t(R.string.retour_revenir)}</a></body></html>"""
    }

    // ------------------------------------------------------------ jeton d'acces et appels
    private suspend fun jeton(ctx: Context): String = withContext(Dispatchers.IO) {
        val a = acces
        if (a != null && System.currentTimeMillis() < expire) return@withContext a
        val j = when (mode(ctx)) {
            "telephone" -> jetonTelephone(ctx, email(ctx) ?: throw ErreurCompte(Textes.t(R.string.err_aucun_compte)))
                .also { expire = System.currentTimeMillis() + 50 * 60_000 }
            "navigateur" -> {
                val f = fournisseur(ctx)
                val r = prefs(ctx).getString("jeton", null)?.let { Coffre.dechiffrer(it) }
                    ?: throw ErreurCompte(Textes.t(R.string.err_autorisation_perdue, f.nom))
                if (f.cle == "pcloud") { expire = Long.MAX_VALUE; acces = r.substringAfter('|'); return@withContext r.substringAfter('|') }
                val champs = mutableMapOf("client_id" to f.id, "refresh_token" to r, "grant_type" to "refresh_token")
                if (f.secret.isNotEmpty()) champs["client_secret"] = f.secret
                val o = try { JSONObject(String(post(f.jeton, champs))) } catch (e: Exception) {
                    Journal.ecrire("compte", "${f.nom} : renouvellement de l'autorisation refusé (${e.message})"); throw e
                }
                // Microsoft et Box donnent un nouveau jeton durable a chaque fois (l'ancien ne sert plus)
                o.optString("refresh_token").takeIf { it.isNotEmpty() && it != r }?.let {
                    prefs(ctx).edit().putString("jeton", Coffre.chiffrer(it)).apply()
                }
                expire = System.currentTimeMillis() + (o.optLong("expires_in", 3600) - 120) * 1000
                o.getString("access_token")
            }
            else -> throw ErreurCompte(Textes.t(R.string.err_aucun_compte))
        }
        acces = j
        j
    }

    /** Appel authentifie ; renvoie (code, contenu, adresse de redirection). Jeton perime : renouvele une fois. */
    private suspend fun appel(ctx: Context, methode: String, url: String, corps: ByteArray? = null,
                              entetes: Map<String, String> = emptyMap()): Triple<Int, ByteArray, String?> = withContext(Dispatchers.IO) {
        for (essai in 0..1) {
            val j = jeton(ctx)
            val (c, code) = reessayer {
                val c = URL(url).openConnection() as HttpURLConnection
                // HttpURLConnection ne connait pas PATCH : POST + en-tete de remplacement (accepte par Google)
                if (methode == "PATCH") { c.requestMethod = "POST"; c.setRequestProperty("X-HTTP-Method-Override", "PATCH") }
                else c.requestMethod = methode
                c.instanceFollowRedirects = false             // telechargements : adresse signee, a suivre sans le jeton
                c.connectTimeout = 15_000; c.readTimeout = 60_000
                c.setRequestProperty("Authorization", "Bearer $j")
                entetes.forEach { (k, v) -> c.setRequestProperty(k, v) }
                if (corps != null) { c.doOutput = true; c.setFixedLengthStreamingMode(corps.size); c.outputStream.use { it.write(corps) } }
                c to c.responseCode
            }
            if (code == 401 && essai == 0) {
                if (mode(ctx) == "telephone") try { AccountManager.get(ctx).invalidateAuthToken("com.google", j) } catch (_: Exception) {}
                acces = null; expire = 0
                continue
            }
            if (code in 300..399) return@withContext Triple(code, ByteArray(0), c.getHeaderField("Location"))
            val b = (if (code in 200..299) c.inputStream else c.errorStream)?.use { it.readBytes() } ?: ByteArray(0)
            return@withContext Triple(code, b, null)
        }
        throw ErreurCompte(Textes.t(R.string.err_autorisation_refusee, fournisseur(ctx).nom))
    }

    /** Contenu d'une adresse (en suivant une redirection signee, sans envoyer le jeton). */
    private suspend fun telecharger(ctx: Context, methode: String, url: String, corps: ByteArray? = null,
                                    entetes: Map<String, String> = emptyMap()): ByteArray? {
        val (code, b, ailleurs) = appel(ctx, methode, url, corps, entetes)
        if (ailleurs != null) return withContext(Dispatchers.IO) { URL(ailleurs).openStream().use { it.readBytes() } }
        if (code == 404 || code == 409) return null
        if (code !in 200..299) throw ErreurCompte(Textes.t(R.string.err_code, fournisseur(ctx).nom, code, String(b).take(200)))
        return b
    }

    private suspend fun json(ctx: Context, methode: String, url: String, corps: JSONObject? = null): JSONObject? {
        // POST sans argument (Dropbox) : corps JSON « null »
        val envoi = corps?.toString()?.toByteArray() ?: if (methode == "POST") "null".toByteArray() else null
        val (code, b, _) = appel(ctx, methode, url, envoi,
            if (envoi != null) mapOf("Content-Type" to "application/json") else emptyMap())
        if (code == 404 || code == 409) return null
        if (code !in 200..299) throw ErreurCompte(Textes.t(R.string.err_code, fournisseur(ctx).nom, code, String(b).take(200)))
        return JSONObject(String(b))
    }

    // ------------------------------------------------------------ pCloud (API par chemins, reponse {"result": 0, ...})
    private fun hote(ctx: Context): String =
        prefs(ctx).getString("jeton", null)?.let { Coffre.dechiffrer(it) }?.substringBefore('|', "api.pcloud.com") ?: "api.pcloud.com"

    /** Appel pCloud ; null si le fichier ou dossier n'existe pas. */
    private suspend fun pc(ctx: Context, methode: String, params: Map<String, String> = emptyMap(), corps: ByteArray? = null,
                           entetes: Map<String, String> = emptyMap()): JSONObject? {
        val j = jeton(ctx)
        val url = "https://${hote(ctx)}/$methode?" + formulaire(params + ("access_token" to j))
        val (code, b, _) = appel(ctx, if (corps != null) "POST" else "GET", url, corps, entetes)
        if (code !in 200..299) throw ErreurCompte(Textes.t(R.string.err_code, "pCloud", code, String(b).take(200)))
        val o = JSONObject(String(b))
        return when (val r = o.optInt("result", 0)) {
            0 -> o
            2002, 2005, 2009 -> null
            else -> { Journal.ecrire("compte", "pCloud : $methode refusé ($r ${o.optString("error")})")
                throw ErreurCompte(Textes.t(R.string.err_code, "pCloud", r, o.optString("error").take(200))) }
        }
    }

    private suspend fun pcEnvoyer(ctx: Context, dossier: String, nom: String, octets: ByteArray): Triple<Int, ByteArray, String?> {
        if (dossier.isNotEmpty() && dossier != "/") pc(ctx, "createfolderifnotexists", mapOf("path" to dossier))
        val bord = "PhilPDF" + java.util.UUID.randomUUID().toString().replace("-", "")
        val corps = ("--$bord\r\nContent-Disposition: form-data; name=\"file\"; filename=\"${nom.replace("\"", "")}\"\r\n" +
            "Content-Type: application/octet-stream\r\n\r\n").toByteArray() + octets + "\r\n--$bord--\r\n".toByteArray()
        pc(ctx, "uploadfile", mapOf("path" to dossier.ifEmpty { "/" }, "filename" to nom, "nopartial" to "1"), corps,
            mapOf("Content-Type" to "multipart/form-data; boundary=$bord"))
        return Triple(200, ByteArray(0), null)
    }

    private suspend fun pcContenu(ctx: Context, chemin: String): ByteArray? {
        val l = pc(ctx, "getfilelink", mapOf("path" to chemin)) ?: return null
        val url = "https://" + l.getJSONArray("hosts").getString(0) + l.getString("path")
        return withContext(Dispatchers.IO) { reessayer { URL(url).openStream().use { it.readBytes() } } }
    }

    private suspend fun pcExiste(ctx: Context, chemin: String): Boolean = pc(ctx, "stat", mapOf("path" to chemin)) != null

    // ------------------------------------------------------------ profil (pastille en haut a droite)
    suspend fun profil(ctx: Context) = withContext(Dispatchers.IO) {
        var nom: String? = null; var mail: String? = null; var image: ByteArray? = null
        fun publique(l: String?) = l?.takeIf { it.isNotEmpty() }?.let { u -> try { URL(u).openStream().use { it.readBytes() } } catch (_: Exception) { null } }
        when (fournisseur(ctx).cle) {
            "gdrive" -> json(ctx, "GET", "$GOOGLE/about?fields=user(emailAddress,displayName,photoLink)")?.optJSONObject("user")?.let { u ->
                nom = u.optString("displayName"); mail = u.optString("emailAddress"); image = publique(u.optString("photoLink"))
            }
            "onedrive" -> {
                json(ctx, "GET", "$GRAPH/me?\$select=displayName,mail,userPrincipalName")?.let { u ->
                    nom = u.optString("displayName"); mail = u.optString("mail").ifEmpty { u.optString("userPrincipalName") }
                }
                image = try { appel(ctx, "GET", "$GRAPH/me/photo/\$value").let { (c, b, _) -> if (c in 200..299) b else null } } catch (_: Exception) { null }
            }
            "dropbox" -> json(ctx, "POST", "$DBX/users/get_current_account")?.let { u ->
                nom = u.optJSONObject("name")?.optString("display_name"); mail = u.optString("email"); image = publique(u.optString("profile_photo_url"))
            }
            "box" -> json(ctx, "GET", "$BOX/users/me?fields=name,login")?.let { u -> nom = u.optString("name"); mail = u.optString("login") }
            "pcloud" -> pc(ctx, "userinfo")?.let { u -> mail = u.optString("email") }
        }
        prefs(ctx).edit().apply {
            nom?.takeIf { it.isNotEmpty() }?.let { putString("nom", it) }
            mail?.takeIf { it.isNotEmpty() }?.let { putString("email", it) }
        }.apply()
        image?.let { photo(ctx).parentFile?.mkdirs(); photo(ctx).writeBytes(it) }
        // meme compte deja relie (reconnexion) : on garde le plus recent
        val f = fournisseur(ctx).cle
        val e = email(ctx)
        if (e != null) liste(ctx).filter { it.id != id && it.fournisseur(ctx).cle == f && it.email(ctx) == e }.forEach { autre ->
            if (synchro(ctx)?.id == autre.id) registre(ctx).edit().putString("synchro", id).apply()
            retirer(ctx, autre, garderBibliotheque = true)
        }
    }

    // ------------------------------------------------------------ parcourir, ouvrir, renvoyer
    /** Google Drive : l'autorisation limitee (drive.file) ne montre que les fichiers de PhilPDF ; le reste passe par Android. */
    fun parcourable(ctx: Context) = fournisseur(ctx).cle != "gdrive"

    fun racineParcours(ctx: Context): String = when (fournisseur(ctx).cle) { "dropbox", "pcloud" -> ""; "box" -> "0"; else -> "root" }

    /** Dossiers et PDF d'un dossier (les autres fichiers ne sont pas montres). */
    suspend fun lister(ctx: Context, dossier: String): List<Entree> {
        val out = ArrayList<Entree>()
        when (fournisseur(ctx).cle) {
            "onedrive" -> {
                var url: String? = "$GRAPH/me/drive/items/$dossier/children?\$top=500&\$select=id,name,size,folder,file,lastModifiedDateTime"
                while (url != null) {
                    val o = json(ctx, "GET", url) ?: break
                    val a = o.optJSONArray("value") ?: JSONArray()
                    for (i in 0 until a.length()) a.getJSONObject(i).let { x ->
                        out += Entree(x.optString("id"), x.optString("name"), x.has("folder"), x.optLong("size"), x.optString("lastModifiedDateTime"))
                    }
                    url = o.optString("@odata.nextLink").takeIf { it.isNotEmpty() }
                }
            }
            "dropbox" -> {
                var o = json(ctx, "POST", "$DBX/files/list_folder", JSONObject().put("path", dossier).put("limit", 1000))
                while (o != null) {
                    val a = o.optJSONArray("entries") ?: JSONArray()
                    for (i in 0 until a.length()) a.getJSONObject(i).let { x ->
                        out += Entree(x.optString("path_display"), x.optString("name"), x.optString(".tag") == "folder",
                            x.optLong("size"), x.optString("server_modified"))
                    }
                    o = if (o.optBoolean("has_more")) json(ctx, "POST", "$DBX/files/list_folder/continue", JSONObject().put("cursor", o.optString("cursor"))) else null
                }
            }
            "box" -> {
                var debut = 0
                while (true) {
                    val o = json(ctx, "GET", "$BOX/folders/$dossier/items?fields=id,name,type,size,modified_at&limit=1000&offset=$debut") ?: break
                    val a = o.optJSONArray("entries") ?: break
                    for (i in 0 until a.length()) a.getJSONObject(i).let { x ->
                        out += Entree(x.optString("id"), x.optString("name"), x.optString("type") == "folder", x.optLong("size"), x.optString("modified_at"))
                    }
                    debut += a.length()
                    if (a.length() == 0 || debut >= o.optInt("total_count", 0)) break
                }
            }
        }
        if (fournisseur(ctx).cle == "pcloud") {
            val a = pc(ctx, "listfolder", mapOf("path" to dossier.ifEmpty { "/" }))?.optJSONObject("metadata")?.optJSONArray("contents") ?: JSONArray()
            for (i in 0 until a.length()) a.getJSONObject(i).let { x ->
                out += Entree(dossier.trimEnd('/') + "/" + x.optString("name"), x.optString("name"), x.optBoolean("isfolder"),
                    x.optLong("size"), x.optString("modified"))
            }
        }
        return out.filter { it.dossier || it.nom.lowercase().endsWith(".pdf") }
            .sortedWith(compareBy<Entree>({ !it.dossier }, { it.nom.lowercase() }))
    }

    /** Copie le fichier sur le telephone et retient d'ou il vient (pour « Meme fichier »). */
    suspend fun ouvrirFichier(ctx: Context, e: Entree): Uri {
        val b = contenuFichier(ctx, e.id) ?: throw ErreurCompte(Textes.t(R.string.err_fichier_introuvable, fournisseur(ctx).nom))
        val f = File(ctx.filesDir, "comptes/fichiers/$id/${empreinte(e.id)}/${e.nom.replace('/', '_')}")
        withContext(Dispatchers.IO) { f.parentFile?.mkdirs(); f.writeBytes(b) }
        Distants.retenir(ctx, f, Origine(id, e.id, e.nom))
        return Uri.fromFile(f)
    }

    /** Fichier designe par son chemin depuis la racine du compte (« /Factures/facture.pdf »), comme sous Windows ;
     *  copie sur le telephone, ouverte ensuite comme un fichier du compte (« Meme fichier » l'y renvoie). */
    suspend fun ouvrirChemin(ctx: Context, chemin: String): Uri {
        val parts = chemin.split("/").filter { it.isNotEmpty() }
        val nom = parts.lastOrNull() ?: throw ErreurCompte(Textes.t(R.string.err_fichier_introuvable, fournisseur(ctx).nom))
        val fid: String? = when (fournisseur(ctx).cle) {
            "gdrive" -> { var x: String? = "root"; for (n in parts) x = x?.let { gEnfant(ctx, it, n)?.getString("id") }; x }
            "onedrive" -> json(ctx, "GET", "$GRAPH/me/drive/root:/" + parts.joinToString("/") { enc(it) } + "?\$select=id")
                ?.optString("id")?.takeIf { it.isNotEmpty() }
            "dropbox", "pcloud" -> "/" + parts.joinToString("/")
            "box" -> { var x: String? = "0"; for (n in parts) x = x?.let { bEnfant(ctx, it, n) }; x }
            else -> null
        }
        if (fid == null) throw ErreurCompte(Textes.t(R.string.err_fichier_introuvable, fournisseur(ctx).nom))
        return ouvrirFichier(ctx, Entree(fid, nom, false, 0, ""))
    }

    suspend fun contenuFichier(ctx: Context, fid: String): ByteArray? = when (fournisseur(ctx).cle) {
        "gdrive" -> telecharger(ctx, "GET", "$GOOGLE/files/$fid?alt=media")
        "onedrive" -> telecharger(ctx, "GET", "$GRAPH/me/drive/items/$fid/content")
        "dropbox" -> telecharger(ctx, "POST", "$DBX_CONTENU/files/download", ByteArray(0),
            mapOf("Dropbox-API-Arg" to ascii(JSONObject().put("path", fid).toString()), "Content-Type" to "text/plain; charset=dropbox-cors-hack"))
        "box" -> telecharger(ctx, "GET", "$BOX/files/$fid/content")
        "pcloud" -> pcContenu(ctx, fid)
        else -> null
    }

    /** Remplace le fichier distant par cette version (« Meme fichier »). */
    suspend fun renvoyer(ctx: Context, fid: String, nom: String, octets: ByteArray) {
        val (code, b, _) = when (fournisseur(ctx).cle) {
            "gdrive" -> appel(ctx, "PATCH", "$GOOGLE_ENVOI/files/$fid?uploadType=media", octets, mapOf("Content-Type" to "application/pdf"))
            "onedrive" -> appel(ctx, "PUT", "$GRAPH/me/drive/items/$fid/content", octets, mapOf("Content-Type" to "application/pdf"))
            "dropbox" -> appel(ctx, "POST", "$DBX_CONTENU/files/upload", octets, mapOf("Content-Type" to "application/octet-stream",
                "Dropbox-API-Arg" to ascii(JSONObject().put("path", fid).put("mode", "overwrite").put("mute", true).toString())))
            "box" -> {
                val bord = "PhilPDF" + java.util.UUID.randomUUID().toString().replace("-", "")
                val corps = ("--$bord\r\nContent-Disposition: form-data; name=\"attributes\"\r\n\r\n{}\r\n" +
                    "--$bord\r\nContent-Disposition: form-data; name=\"file\"; filename=\"${nom.replace("\"", "")}\"\r\n" +
                    "Content-Type: application/pdf\r\n\r\n").toByteArray() + octets + "\r\n--$bord--\r\n".toByteArray()
                appel(ctx, "POST", "$BOX_ENVOI/files/$fid/content", corps, mapOf("Content-Type" to "multipart/form-data; boundary=$bord"))
            }
            "pcloud" -> pcEnvoyer(ctx, fid.substringBeforeLast('/', ""), fid.substringAfterLast('/'), octets)
            else -> Triple(0, ByteArray(0), null)
        }
        if (code !in 200..299) {
            Journal.ecrire("compte", "${fournisseur(ctx).nom} : renvoi de $nom refusé ($code)")
            throw ErreurCompte(Textes.t(R.string.err_envoi_refuse, fournisseur(ctx).nom, code, String(b).take(160)))
        }
        Journal.ecrire("compte", "${fournisseur(ctx).nom} : $nom renvoyé à sa place")
    }

    // ------------------------------------------------------------ partage par lien
    /** Depose le PDF dans PhilPDF/Partages du compte et renvoie un lien public (lecture seule), a mettre dans un e-mail. */
    suspend fun partagerParLien(ctx: Context, nom: String, octets: ByteArray): String {
        val f = fournisseur(ctx)
        if (ids[""] == null && !trouverRacine(ctx)) throw ErreurCompte(Textes.t(R.string.err_dossier_philpdf_windows, f.nom))
        val racine = ids[""]!!
        fun erreur(etape: String, code: Int, b: ByteArray): Nothing {
            Journal.ecrire("partage", "${f.nom} : $etape refusé ($code) ${String(b).take(200)}")
            throw ErreurCompte(Textes.t(R.string.err_etape_refusee, f.nom, etape, code, String(b).take(160)))
        }
        val lien: String = when (f.cle) {
            "gdrive" -> {
                val dossier = gEnfant(ctx, racine, "Partages")?.getString("id")
                    ?: json(ctx, "POST", "$GOOGLE/files?fields=id", JSONObject().put("name", "Partages")
                        .put("mimeType", "application/vnd.google-apps.folder").put("parents", JSONArray().put(racine)))?.getString("id")
                    ?: throw ErreurCompte(Textes.t(R.string.err_dossier_creer, f.nom, "Partages"))
                val bord = "PhilPDF" + java.util.UUID.randomUUID().toString().replace("-", "")
                val meta = JSONObject().put("name", nom).put("parents", JSONArray().put(dossier)).toString()
                val corps = ("--$bord\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n$meta\r\n" +
                    "--$bord\r\nContent-Type: application/pdf\r\n\r\n").toByteArray() + octets + "\r\n--$bord--\r\n".toByteArray()
                val (c1, b1, _) = appel(ctx, "POST", "$GOOGLE_ENVOI/files?uploadType=multipart&fields=id", corps,
                    mapOf("Content-Type" to "multipart/related; boundary=$bord"))
                if (c1 !in 200..299) erreur("dépôt", c1, b1)
                val fid = JSONObject(String(b1)).getString("id")
                val (c2, b2, _) = appel(ctx, "POST", "$GOOGLE/files/$fid/permissions",
                    JSONObject().put("role", "reader").put("type", "anyone").toString().toByteArray(), mapOf("Content-Type" to "application/json"))
                if (c2 !in 200..299) erreur("lien", c2, b2)
                "https://drive.google.com/file/d/$fid/view?usp=sharing"
            }
            "onedrive" -> {
                val (c1, b1, _) = appel(ctx, "PUT", "$GRAPH/me/drive/items/$racine:/Partages/${enc(nom)}:/content?@microsoft.graph.conflictBehavior=rename",
                    octets, mapOf("Content-Type" to "application/pdf"))
                if (c1 !in 200..299) erreur("dépôt", c1, b1)
                val fid = JSONObject(String(b1)).getString("id")
                var r: Triple<Int, ByteArray, String?> = Triple(0, ByteArray(0), null)
                for (portee in listOf("anonymous", "organization")) {      // comptes d'entreprise : lien interne si l'anonyme est interdit
                    r = appel(ctx, "POST", "$GRAPH/me/drive/items/$fid/createLink",
                        JSONObject().put("type", "view").put("scope", portee).toString().toByteArray(), mapOf("Content-Type" to "application/json"))
                    if (r.first in 200..299) break
                }
                if (r.first !in 200..299) erreur("lien", r.first, r.second)
                JSONObject(String(r.second)).getJSONObject("link").getString("webUrl")
            }
            "dropbox" -> {
                val (c1, b1, _) = appel(ctx, "POST", "$DBX_CONTENU/files/upload", octets, mapOf("Content-Type" to "application/octet-stream",
                    "Dropbox-API-Arg" to ascii(JSONObject().put("path", "$racine/Partages/$nom").put("mode", "add").put("autorename", true).put("mute", true).toString())))
                if (c1 !in 200..299) erreur("dépôt", c1, b1)
                val chemin = JSONObject(String(b1)).getString("path_lower")
                val (c2, b2, _) = appel(ctx, "POST", "$DBX/sharing/create_shared_link_with_settings",
                    JSONObject().put("path", chemin).toString().toByteArray(), mapOf("Content-Type" to "application/json"))
                when {
                    c2 in 200..299 -> JSONObject(String(b2)).getString("url")
                    String(b2).contains("shared_link_already_exists") -> JSONObject(String(b2)).optJSONObject("error")
                        ?.optJSONObject("shared_link_already_exists")?.optJSONObject("metadata")?.optString("url")
                        ?.takeIf { it.isNotEmpty() } ?: erreur("lien", c2, b2)
                    String(b2).contains("missing_scope") -> throw ErreurCompte(Textes.t(R.string.err_dropbox_liens))
                    else -> erreur("lien", c2, b2)
                }
            }
            "box" -> {
                val dossier = bEnfant(ctx, racine, "Partages")
                    ?: json(ctx, "POST", "$BOX/folders", JSONObject().put("name", "Partages").put("parent", JSONObject().put("id", racine)))?.optString("id")
                    ?: throw ErreurCompte(Textes.t(R.string.err_dossier_creer, "Box", "Partages"))
                val bord = "PhilPDF" + java.util.UUID.randomUUID().toString().replace("-", "")
                val attr = JSONObject().put("name", nom).put("parent", JSONObject().put("id", dossier)).toString()
                val corps = ("--$bord\r\nContent-Disposition: form-data; name=\"attributes\"\r\n\r\n$attr\r\n" +
                    "--$bord\r\nContent-Disposition: form-data; name=\"file\"; filename=\"${nom.replace("\"", "")}\"\r\n" +
                    "Content-Type: application/pdf\r\n\r\n").toByteArray() + octets + "\r\n--$bord--\r\n".toByteArray()
                val (c1, b1, _) = appel(ctx, "POST", "$BOX_ENVOI/files/content", corps, mapOf("Content-Type" to "multipart/form-data; boundary=$bord"))
                if (c1 !in 200..299) erreur("dépôt", c1, b1)
                val fid = JSONObject(String(b1)).getJSONArray("entries").getJSONObject(0).getString("id")
                val (c2, b2, _) = appel(ctx, "PUT", "$BOX/files/$fid?fields=shared_link",
                    JSONObject().put("shared_link", JSONObject().put("access", "open")).toString().toByteArray(), mapOf("Content-Type" to "application/json"))
                if (c2 !in 200..299) erreur("lien", c2, b2)
                JSONObject(String(b2)).getJSONObject("shared_link").getString("url")
            }
            "pcloud" -> {
                var n = nom; var i = 2
                while (pcExiste(ctx, "$racine/Partages/$n")) { n = nom.substringBeforeLast('.') + " ($i)." + nom.substringAfterLast('.', "pdf"); i++ }
                pcEnvoyer(ctx, "$racine/Partages", n, octets)
                pc(ctx, "getfilepublink", mapOf("path" to "$racine/Partages/$n"))?.optString("link")?.takeIf { it.isNotEmpty() }
                    ?: throw ErreurCompte(Textes.t(R.string.err_pas_de_lien, f.nom))
            }
            else -> throw ErreurCompte(Textes.t(R.string.err_pas_de_lien, f.nom))
        }
        Journal.ecrire("partage", "${f.nom} : $nom déposé dans PhilPDF/Partages, lien créé")
        return lien
    }

    /** Ecrit (ou remplace) PhilPDF/<dossier>/<nom> dans le compte synchronise. */
    suspend fun deposer(ctx: Context, dossier: String, nom: String, octets: ByteArray) {
        val f = fournisseur(ctx)
        if (ids[""] == null && !trouverRacine(ctx)) throw ErreurCompte(Textes.t(R.string.err_dossier_philpdf, f.nom))
        val racine = ids[""]!!
        val type = mapOf("Content-Type" to "application/octet-stream")
        val (code, b, _) = when (f.cle) {
            "gdrive" -> {
                val d = gEnfant(ctx, racine, dossier)?.getString("id")
                    ?: json(ctx, "POST", "$GOOGLE/files?fields=id", JSONObject().put("name", dossier)
                        .put("mimeType", "application/vnd.google-apps.folder").put("parents", JSONArray().put(racine)))?.getString("id")
                    ?: throw ErreurCompte(Textes.t(R.string.err_dossier_creer, f.nom, dossier))
                val existant = gEnfant(ctx, d, nom)?.getString("id")
                if (existant != null) appel(ctx, "PATCH", "$GOOGLE_ENVOI/files/$existant?uploadType=media", octets, type)
                else {
                    val bord = "PhilPDF" + java.util.UUID.randomUUID().toString().replace("-", "")
                    val meta = JSONObject().put("name", nom).put("parents", JSONArray().put(d)).toString()
                    val corps = ("--$bord\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n$meta\r\n" +
                        "--$bord\r\nContent-Type: application/octet-stream\r\n\r\n").toByteArray() + octets + "\r\n--$bord--\r\n".toByteArray()
                    appel(ctx, "POST", "$GOOGLE_ENVOI/files?uploadType=multipart&fields=id", corps, mapOf("Content-Type" to "multipart/related; boundary=$bord"))
                }
            }
            "onedrive" -> appel(ctx, "PUT", "$GRAPH/me/drive/items/$racine:/${enc(dossier)}/${enc(nom)}:/content?@microsoft.graph.conflictBehavior=replace", octets, type)
            "dropbox" -> appel(ctx, "POST", "$DBX_CONTENU/files/upload", octets, mapOf("Content-Type" to "application/octet-stream",
                "Dropbox-API-Arg" to ascii(JSONObject().put("path", "$racine/$dossier/$nom").put("mode", "overwrite").put("mute", true).toString())))
            "box" -> {
                val d = bEnfant(ctx, racine, dossier)
                    ?: json(ctx, "POST", "$BOX/folders", JSONObject().put("name", dossier).put("parent", JSONObject().put("id", racine)))?.optString("id")
                    ?: throw ErreurCompte(Textes.t(R.string.err_dossier_creer, "Box", dossier))
                val existant = bEnfant(ctx, d, nom)
                val bord = "PhilPDF" + java.util.UUID.randomUUID().toString().replace("-", "")
                val attr = if (existant != null) "{}" else JSONObject().put("name", nom).put("parent", JSONObject().put("id", d)).toString()
                val corps = ("--$bord\r\nContent-Disposition: form-data; name=\"attributes\"\r\n\r\n$attr\r\n" +
                    "--$bord\r\nContent-Disposition: form-data; name=\"file\"; filename=\"${nom.replace("\"", "")}\"\r\n" +
                    "Content-Type: application/octet-stream\r\n\r\n").toByteArray() + octets + "\r\n--$bord--\r\n".toByteArray()
                appel(ctx, "POST", if (existant != null) "$BOX_ENVOI/files/$existant/content" else "$BOX_ENVOI/files/content", corps,
                    mapOf("Content-Type" to "multipart/form-data; boundary=$bord"))
            }
            "pcloud" -> pcEnvoyer(ctx, "$racine/$dossier", nom, octets)
            else -> Triple(0, ByteArray(0), null)
        }
        if (code !in 200..299) throw ErreurCompte(Textes.t(R.string.err_depot_refuse, f.nom, nom, code, String(b).take(160)))
    }

    /** Envoie un fichier dans un dossier du compte designe par son chemin (« /Factures/EDF »), dossiers crees s'il le
     *  faut. Un fichier du meme nom n'est jamais remplace : le nouveau prend « (2) ». Renvoie le chemin final. */
    suspend fun envoyerChemin(ctx: Context, dossier: String, nom0: String, octets: ByteArray): String {
        val f = fournisseur(ctx)
        val parts = dossier.split("/").filter { it.isNotEmpty() }
        suspend fun libre(existe: suspend (String) -> Boolean): String {
            if (!existe(nom0)) return nom0
            val base = nom0.substringBeforeLast('.'); val ext = nom0.substringAfterLast('.', "pdf")
            var i = 2
            while (existe("$base ($i).$ext")) i++
            return "$base ($i).$ext"
        }
        var nom = nom0
        val (code, b, _) = when (f.cle) {
            "gdrive" -> {
                var d = "root"
                for (n in parts) d = gEnfant(ctx, d, n)?.getString("id")
                    ?: json(ctx, "POST", "$GOOGLE/files?fields=id", JSONObject().put("name", n)
                        .put("mimeType", "application/vnd.google-apps.folder").put("parents", JSONArray().put(d)))?.getString("id")
                    ?: throw ErreurCompte(Textes.t(R.string.err_dossier_creer, f.nom, n))
                nom = libre { gEnfant(ctx, d, it) != null }
                val bord = "PhilPDF" + java.util.UUID.randomUUID().toString().replace("-", "")
                val meta = JSONObject().put("name", nom).put("parents", JSONArray().put(d)).toString()
                val corps = ("--$bord\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n$meta\r\n" +
                    "--$bord\r\nContent-Type: application/pdf\r\n\r\n").toByteArray() + octets + "\r\n--$bord--\r\n".toByteArray()
                appel(ctx, "POST", "$GOOGLE_ENVOI/files?uploadType=multipart&fields=id", corps, mapOf("Content-Type" to "multipart/related; boundary=$bord"))
            }
            "onedrive" -> {
                val ch = (parts + nom0).joinToString("/") { enc(it) }
                appel(ctx, "PUT", "$GRAPH/me/drive/root:/$ch:/content?@microsoft.graph.conflictBehavior=rename", octets,
                    mapOf("Content-Type" to "application/pdf"))
            }
            "dropbox" -> appel(ctx, "POST", "$DBX_CONTENU/files/upload", octets, mapOf("Content-Type" to "application/octet-stream",
                "Dropbox-API-Arg" to ascii(JSONObject().put("path", "/" + (parts + nom0).joinToString("/")).put("mode", "add")
                    .put("autorename", true).put("mute", true).toString())))
            "box" -> {
                var d = "0"
                for (n in parts) d = bEnfant(ctx, d, n)
                    ?: json(ctx, "POST", "$BOX/folders", JSONObject().put("name", n).put("parent", JSONObject().put("id", d)))?.optString("id")
                    ?: throw ErreurCompte(Textes.t(R.string.err_dossier_creer, "Box", n))
                nom = libre { bEnfant(ctx, d, it) != null }
                val bord = "PhilPDF" + java.util.UUID.randomUUID().toString().replace("-", "")
                val attr = JSONObject().put("name", nom).put("parent", JSONObject().put("id", d)).toString()
                val corps = ("--$bord\r\nContent-Disposition: form-data; name=\"attributes\"\r\n\r\n$attr\r\n" +
                    "--$bord\r\nContent-Disposition: form-data; name=\"file\"; filename=\"${nom.replace("\"", "")}\"\r\n" +
                    "Content-Type: application/octet-stream\r\n\r\n").toByteArray() + octets + "\r\n--$bord--\r\n".toByteArray()
                appel(ctx, "POST", "$BOX_ENVOI/files/content", corps, mapOf("Content-Type" to "multipart/form-data; boundary=$bord"))
            }
            "pcloud" -> {
                val d = "/" + parts.joinToString("/")
                nom = libre { pcExiste(ctx, d.trimEnd('/') + "/" + it) }
                pcEnvoyer(ctx, d, nom, octets)
            }
            else -> Triple(0, ByteArray(0), null)
        }
        if (code !in 200..299) throw ErreurCompte(Textes.t(R.string.err_depot_refuse, f.nom, nom, code, String(b).take(160)))
        val final = "/" + (parts + nom).joinToString("/")
        Journal.ecrire("classer", "${f.nom} : $final")
        return final
    }

    // ------------------------------------------------------------ dossier PhilPDF (synchronisation) et lecture de ses fichiers
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
            "pcloud" -> if (pcExiste(ctx, "/PhilPDF")) "/PhilPDF" else null
            "box" -> bEnfant(ctx, "0", "PhilPDF")
                ?: json(ctx, "GET", "$BOX/search?query=PhilPDF&type=folder&content_types=name&fields=id,name")?.optJSONArray("entries")?.let { a ->
                    (0 until a.length()).map { a.getJSONObject(it) }.firstOrNull { it.optString("name") == "PhilPDF" }?.optString("id")
                }
            else -> null
        }
        if (r.isNullOrEmpty()) { Journal.ecrire("synchro", "${fournisseur(ctx).nom} : aucun dossier PhilPDF"); return false }
        ids[""] = r
        return true
    }

    /** Contenu d'un fichier du dossier PhilPDF (chemin relatif : « sauvegarde/index.json »), ou null s'il n'existe pas. */
    suspend fun lire(ctx: Context, rel: String): ByteArray? {
        if (ids[""] == null && !trouverRacine(ctx)) return null
        val racine = ids[""]!!
        return when (fournisseur(ctx).cle) {
            "gdrive" -> contenuFichier(ctx, idParChemin(rel) { p, n -> gEnfant(ctx, p, n)?.getString("id") } ?: return null)
            "onedrive" -> telecharger(ctx, "GET", "$GRAPH/me/drive/items/$racine:/" + rel.split("/").joinToString("/") { enc(it) } + ":/content")
            "dropbox", "pcloud" -> contenuFichier(ctx, "$racine/$rel")
            "box" -> contenuFichier(ctx, idParChemin(rel) { p, n -> bEnfant(ctx, p, n) } ?: return null)
            else -> null
        }
    }

    private suspend fun idParChemin(rel: String, enfant: suspend (String, String) -> String?): String? {
        var chemin = ""
        var x = ids[""] ?: return null
        for (n in rel.split("/").filter { it.isNotEmpty() }) {
            chemin = if (chemin.isEmpty()) n else "$chemin/$n"
            x = ids[chemin] ?: (enfant(x, n) ?: return null).also { ids[chemin] = it }
        }
        return x
    }

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

    companion object {
        /** Activite au premier plan : Android y affiche lui-meme l'ecran « Autoriser » quand il le faut. */
        var activite: WeakReference<Activity>? = null
        /** PhilPDF au premier plan (le reseau est alors autorise par Android). */
        val premierPlan = MutableStateFlow(false)

        private val instances = HashMap<String, Nuage>()
        fun de(id: String): Nuage = synchronized(instances) { instances.getOrPut(id) { Nuage(id) } }
        private fun registre(ctx: Context) = ctx.getSharedPreferences("comptes", Context.MODE_PRIVATE)

        /** Comptes relies, dans l'ordre d'ajout. */
        fun liste(ctx: Context): List<Nuage> {
            migrer(ctx)
            val a = try { JSONArray(registre(ctx).getString("liste", "[]")) } catch (_: Exception) { JSONArray() }
            return (0 until a.length()).map { de(a.getString(it)) }.filter { it.connecte(ctx) }
        }

        /** Compte ou se trouve le dossier PhilPDF de vos postes. */
        fun synchro(ctx: Context): Nuage? = liste(ctx).let { l -> l.firstOrNull { it.id == registre(ctx).getString("synchro", null) } }

        /** Compte prefere pour envoyer, partager par lien et classer (sinon celui de la synchronisation). */
        fun prefere(ctx: Context): Nuage? = liste(ctx).let { l ->
            l.firstOrNull { it.id == registre(ctx).getString("prefere", null) } ?: synchro(ctx) ?: l.firstOrNull() }

        fun estPrefere(ctx: Context, n: Nuage) = registre(ctx).getString("prefere", null) == n.id

        fun choisirPrefere(ctx: Context, n: Nuage?) = registre(ctx).edit().putString("prefere", n?.id).apply()

        fun choisirSynchro(ctx: Context, n: Nuage?) {
            if (synchro(ctx)?.id != n?.id) Bibliotheque.oublier(ctx)
            registre(ctx).edit().putString("synchro", n?.id).apply()
        }

        /** Nouveau compte (enregistre seulement une fois l'autorisation obtenue). */
        fun nouveau(): Nuage = de(java.util.UUID.randomUUID().toString().take(8))

        private fun enregistrer(ctx: Context, n: Nuage) {
            val a = try { JSONArray(registre(ctx).getString("liste", "[]")) } catch (_: Exception) { JSONArray() }
            val l = (0 until a.length()).map { a.getString(it) }
            if (n.id !in l) registre(ctx).edit().putString("liste", JSONArray(l + n.id).toString()).apply()
            if (synchro(ctx) == null) registre(ctx).edit().putString("synchro", n.id).apply()
        }

        fun retirer(ctx: Context, n: Nuage, garderBibliotheque: Boolean = false) {
            if (synchro(ctx)?.id == n.id) {
                registre(ctx).edit().remove("synchro").apply()
                if (!garderBibliotheque) Bibliotheque.oublier(ctx)
            }
            n.oublierJetons(ctx)
            val a = try { JSONArray(registre(ctx).getString("liste", "[]")) } catch (_: Exception) { JSONArray() }
            registre(ctx).edit().putString("liste", JSONArray((0 until a.length()).map { a.getString(it) }.filter { it != n.id }).toString()).apply()
            File(ctx.filesDir, "comptes/fichiers/${n.id}").deleteRecursively()
        }

        /** Version 0.9.41 : un seul compte, dans « compte ». */
        private fun migrer(ctx: Context) {
            val ancien = ctx.getSharedPreferences("compte", Context.MODE_PRIVATE)
            if (ancien.getString("mode", null) == null) return
            val n = de("c1")
            val e = n.prefs(ctx).edit()
            ancien.all.forEach { (k, v) -> if (v is String) e.putString(k, v) }
            e.apply()
            val ph = File(ctx.filesDir, "compte/photo.png")
            if (ph.exists()) { n.photo(ctx).parentFile?.mkdirs(); ph.renameTo(n.photo(ctx)) }
            ancien.edit().clear().apply()
            registre(ctx).edit().putString("liste", JSONArray(listOf("c1")).toString()).putString("synchro", "c1").apply()
        }

        fun disponible(f: Fournisseur) = f.id.isNotEmpty()

        /** Liste des comptes Google du telephone (ecran d'Android, aucune autorisation a demander). */
        fun intentChoisirGoogle(): Intent =
            AccountManager.newChooseAccountIntent(null, null, arrayOf("com.google"), null, null, null, null)

        private fun formulaire(m: Map<String, String>) = m.entries.joinToString("&") { enc(it.key) + "=" + enc(it.value) }
        private fun enc(t: String) = URLEncoder.encode(t, "UTF-8").replace("+", "%20")
        private fun ascii(t: String) = buildString { t.forEach { c -> if (c.code < 128) append(c) else append("\\u%04x".format(c.code)) } }

        /** Reseau capricieux (sortie de veille, changement Wi-Fi / 4G) : trois essais espaces. */
        private fun <T> reessayer(f: () -> T): T {
            var derniere: IOException? = null
            repeat(3) { i ->
                try { return f() } catch (e: java.net.UnknownHostException) { derniere = e } catch (e: java.net.ConnectException) { derniere = e }
                Thread.sleep(1500L * (i + 1))
            }
            throw ErreurCompte(Textes.t(R.string.err_reseau, derniere?.message))
        }

        private fun post(url: String, champs: Map<String, String>): ByteArray = reessayer {
            val c = URL(url).openConnection() as HttpURLConnection
            c.requestMethod = "POST"; c.doOutput = true; c.connectTimeout = 15_000; c.readTimeout = 30_000
            c.setRequestProperty("Content-Type", "application/x-www-form-urlencoded")
            c.outputStream.use { it.write(formulaire(champs).toByteArray()) }
            if (c.responseCode !in 200..299) {
                val msg = c.errorStream?.readBytes()?.let { String(it) }?.take(200) ?: ""
                throw ErreurCompte(Textes.t(R.string.err_autorisation_code, c.responseCode, msg))
            }
            c.inputStream.use { it.readBytes() }
        }
    }
}

/** Fichiers ouverts depuis un compte : copie sur le telephone -> origine (renvoi apres « Meme fichier »). */
object Distants {
    private fun prefs(ctx: Context) = ctx.getSharedPreferences("distants", Context.MODE_PRIVATE)

    fun retenir(ctx: Context, f: File, o: Origine) {
        prefs(ctx).edit().putString(f.absolutePath, JSONObject().put("compte", o.compte).put("id", o.id).put("nom", o.nom).toString()).apply()
    }

    fun origine(ctx: Context, uri: Uri): Pair<File, Origine>? {
        if (uri.scheme != "file") return null
        val p = uri.path ?: return null
        val o = prefs(ctx).getString(p, null)?.let { JSONObject(it) } ?: return null
        return File(p) to Origine(o.optString("compte"), o.optString("id"), o.optString("nom"))
    }

    /** Avant de rouvrir (Recents) : derniere version du compte, si le reseau le permet. */
    suspend fun rafraichir(ctx: Context, uri: Uri) {
        val (f, o) = origine(ctx, uri) ?: return
        val n = Nuage.liste(ctx).firstOrNull { it.id == o.compte } ?: return
        try {
            n.contenuFichier(ctx, o.id)?.let { b -> withContext(Dispatchers.IO) { f.parentFile?.mkdirs(); f.writeBytes(b) } }
        } catch (_: Exception) { }
    }

    /** Apres « Meme fichier » sur une copie venue d'un compte : on la renvoie a sa place. */
    suspend fun renvoyer(ctx: Context, uri: Uri) {
        val (f, o) = origine(ctx, uri) ?: return
        val n = Nuage.liste(ctx).firstOrNull { it.id == o.compte } ?: throw ErreurCompte(Textes.t(R.string.err_compte_origine))
        n.renvoyer(ctx, o.id, o.nom, withContext(Dispatchers.IO) { f.readBytes() })
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
                         val maj: String, val categorie: String, val ratio: Float, val rendu: Int = 1,
                         val favori: Boolean = false, val ordre: Int = 10000)

/** Version de la fabrication des apercus : 2 = fond blanc rendu transparent. Plus ancien : refait a la recuperation. */
private const val RENDU = 2

/** Ce que l'on lit dans le dossier PhilPDF du compte relie. */
data class EtatDrive(val trouve: Boolean, val postes: List<Poste>, val distants: List<ElementBiblio>, val nouveaux: Int)

/** Signatures, tampons, filigranes de PhilPDF Windows (PhilPDF/sauvegarde), recopies sur le telephone. */
object Bibliotheque {
    private fun dossier(ctx: Context) = File(ctx.filesDir, "bibliotheque")
    private fun index(ctx: Context) = File(dossier(ctx), "index.json")
    fun fichier(ctx: Context, e: ElementBiblio) = File(dossier(ctx), "${e.genre}/${e.id}${e.ext}")
    fun apercu(ctx: Context, e: ElementBiblio) = File(dossier(ctx), "apercus/${e.id}.png")

    fun oublier(ctx: Context) { dossier(ctx).deleteRecursively() }

    private fun sync(ctx: Context): Nuage = Nuage.synchro(ctx) ?: throw ErreurCompte(Textes.t(R.string.err_aucune_synchro))

    private fun versElement(o: JSONObject) = ElementBiblio(o.optString("id"), o.optString("genre"), o.optString("nom"),
        o.optString("ext", ".pdf").ifEmpty { ".pdf" }, o.optString("hash"), o.optString("maj"), o.optString("categorie"),
        o.optDouble("ratio", 3.0).toFloat(), o.optInt("rendu", 1), o.optBoolean("favori"), o.optInt("ordre", 10000))

    /** Elements deja recuperes sur ce telephone (utilisables sans reseau). */
    fun locaux(ctx: Context): List<ElementBiblio> = try {
        val a = JSONObject(index(ctx).readText()).getJSONArray("elements")
        (0 until a.length()).map { versElement(a.getJSONObject(it)) }.filter { apercu(ctx, it).exists() }
    } catch (_: Exception) { emptyList() }

    fun derniereRecuperation(ctx: Context): Long = index(ctx).takeIf { it.exists() }?.lastModified() ?: 0

    private suspend fun json(ctx: Context, rel: String): JSONObject? = try {
        sync(ctx).lire(ctx, rel)?.let { JSONObject(String(it)) }
    } catch (e: ErreurCompte) { throw e } catch (_: Exception) { null }

    /** Lit le dossier PhilPDF : postes (preferences.json, session.json) et bibliotheque (sauvegarde/index.json). */
    suspend fun lireDrive(ctx: Context): EtatDrive {
        if (!sync(ctx).trouverRacine(ctx)) return EtatDrive(false, emptyList(), emptyList(), 0)
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
        val nouveaux = distants.count { d -> ici[d.id]?.let { it.hash != d.hash || it.rendu < RENDU } ?: true }
        Journal.ecrire("synchro", "${postes.size} poste(s), ${distants.size} élément(s) de bibliothèque, $nouveaux à récupérer")
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
            if (deja != null && deja.hash == e.hash && deja.rendu >= RENDU && fichier(ctx, deja).exists()) { gardes += deja; return@forEachIndexed }
            try {
                val octets = sync(ctx).lire(ctx, "sauvegarde/${e.genre}/${e.id}${e.ext}") ?: return@forEachIndexed
                val dest = fichier(ctx, e)
                val ratio = withContext(Dispatchers.IO) {
                    dest.parentFile?.mkdirs()
                    dest.writeBytes(octets)
                    rendreApercu(dest, apercu(ctx, e))
                }
                gardes += e.copy(ratio = ratio, rendu = RENDU)
                n++
            } catch (ex: Exception) {
                Journal.ecrire("synchro", "bibliothèque : ${e.nom} non récupéré ($ex)")
                deja?.let { gardes += it }
            }
        }
        avance(distants.size, distants.size)
        // retires sur les postes : effaces ici aussi
        ici.values.filter { l -> gardes.none { it.id == l.id } }.forEach { fichier(ctx, it).delete(); apercu(ctx, it).delete() }
        val a = JSONArray()
        gardes.forEach { e ->
            a.put(JSONObject().put("id", e.id).put("genre", e.genre).put("nom", e.nom).put("ext", e.ext).put("hash", e.hash)
                .put("maj", e.maj).put("categorie", e.categorie).put("ratio", e.ratio.toDouble()).put("rendu", e.rendu)
                .put("favori", e.favori).put("ordre", e.ordre))
        }
        index(ctx).parentFile?.mkdirs()
        index(ctx).writeText(JSONObject().put("elements", a).toString())
        Journal.ecrire("synchro", "bibliothèque : $n élément(s) récupéré(s), ${gardes.size} sur le téléphone")
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
                blancTransparent(bm)
                dest.parentFile?.mkdirs()
                dest.outputStream().use { bm.compress(Bitmap.CompressFormat.PNG, 100, it) }
                return w / h
            } finally { p.destroy() }
        } finally { d.destroy() }
    }

    /** Fond blanc (scan, signature photographiee) rendu transparent, bords adoucis : le texte de la page reste
     *  visible sous la signature ou le tampon. Meme regle que PhilPDF Windows (clair au-dessus de 225 : transparent). */
    private fun blancTransparent(bm: Bitmap) {
        val w = bm.width
        val px = IntArray(w * bm.height)
        bm.getPixels(px, 0, w, 0, 0, w, bm.height)
        for (i in px.indices) {
            val c = px[i]
            val a = c ushr 24
            if (a == 0) continue
            val lum = (((c shr 16) and 255) + ((c shr 8) and 255) + (c and 255)) / 3f
            val k = ((225f - lum) / 45f).coerceIn(0f, 1f)
            px[i] = ((a * k).toInt() shl 24) or (c and 0xFFFFFF)
        }
        bm.setPixels(px, 0, w, 0, 0, w, bm.height)
    }

    fun image(ctx: Context, e: ElementBiblio): Bitmap? = BitmapFactory.decodeFile(apercu(ctx, e).absolutePath)

    fun nomGenre(g: String) = when (g) {
        "signatures" -> "Signatures"; "tampons" -> "Tampons"; "filigranes" -> "Filigranes"; "paraphes" -> "Paraphes"
        else -> g.replaceFirstChar { it.uppercase() }
    }
}


// ================================================================ fichiers de vos autres postes (sur un Drive)
/** Fichier ouvert recemment sur un autre poste depuis un Drive relie dans PhilPDF (session.json du dossier PhilPDF). */
data class FichierPoste(val nom: String, val poste: String, val date: String, val ouvert: Boolean, val chemin: String,
                        val lieu: String, val compte: Nuage)

object AutresPostes {
    @Volatile private var cache: Pair<Long, List<FichierPoste>>? = null

    /** Lus une fois par quart d'heure au plus (rien de lent a l'ouverture de l'Accueil) ; seulement les fichiers d'un
     *  Drive que ce telephone connait aussi (meme genre de compte ; le meme e-mail s'il y en a plusieurs). */
    suspend fun lire(ctx: Context, forcer: Boolean = false): List<FichierPoste> {
        cache?.let { (t, l) -> if (!forcer && System.currentTimeMillis() - t < 15 * 60_000) return l }
        val sync = Nuage.synchro(ctx) ?: return emptyList()
        val sess = try { sync.lire(ctx, "session.json")?.let { JSONObject(String(it)) } } catch (e: Exception) {
            Journal.ecrire("autres postes", "session illisible ($e)"); null } ?: return emptyList()
        val comptes = Nuage.liste(ctx)
        val vus = HashSet<String>()
        val out = ArrayList<FichierPoste>()
        for (m in sess.keys()) {
            val v = sess.optJSONObject(m) ?: continue
            val maj = v.optString("maj")
            fun lister(a: JSONArray?, ouvert: Boolean) {
                if (a == null) return
                for (i in 0 until a.length()) {
                    val e = a.optJSONObject(i) ?: continue
                    val d = e.optJSONObject("distant") ?: continue
                    val genre = d.optString("cle").substringBefore("|")
                    val chemin = d.optString("chemin")
                    if (genre !in CLES_NUAGES || chemin.isEmpty()) continue
                    val lieu = d.optString("lieu")
                    val memes = comptes.filter { it.fournisseur(ctx).cle == genre }
                    val c = memes.firstOrNull { n -> n.email(ctx)?.let { lieu.contains(it, true) } == true } ?: memes.singleOrNull() ?: continue
                    if (!vus.add("$genre|${chemin.lowercase()}")) continue
                    out += FichierPoste(e.optString("nom").ifEmpty { chemin.substringAfterLast('/') }, m,
                        if (ouvert) maj else e.optString("date").ifEmpty { maj }, ouvert, chemin, lieu, c)
                }
            }
            lister(v.optJSONArray("fichiers"), true)
            lister(v.optJSONArray("recents"), false)
        }
        val l = out.sortedByDescending { it.date }.take(30)
        Journal.ecrire("autres postes", "${l.size} fichier(s) de vos autres postes sur un Drive")
        cache = System.currentTimeMillis() to l
        return l
    }
}
