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
)

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
            ?: throw ErreurCompte("Google demande de vous reconnecter.")
    }

    // ------------------------------------------------------------ navigateur (tous les fournisseurs)
    /**
     * Ouvre la page du fournisseur dans le navigateur et recoit sa reponse sur l'adresse locale (PKCE).
     * Le code n'est echange qu'une fois PhilPDF revenu au premier plan : Android coupe souvent le reseau
     * des applications en arriere-plan (« Unable to resolve host »).
     */
    suspend fun connecterNavigateur(ctx: Context, f: Fournisseur, indice: String?, attente: (String) -> Unit): Unit =
        withContext(Dispatchers.IO) {
            if (!disponible(f)) throw ErreurCompte("Cette version n'a pas l'identifiant ${f.nom} de PhilPDF.")
            val b64 = Base64.URL_SAFE or Base64.NO_PADDING or Base64.NO_WRAP
            val verif = Base64.encodeToString(ByteArray(48).also { SecureRandom().nextBytes(it) }, b64)
            val defi = Base64.encodeToString(MessageDigest.getInstance("SHA-256").digest(verif.toByteArray()), b64)
            val etatAleatoire = java.util.UUID.randomUUID().toString()
            // toutes les adresses locales (127.0.0.1 ET ::1 : « localhost » vise l'une ou l'autre selon le navigateur) ;
            // toute connexion venant d'ailleurs que le telephone lui-meme est refusee
            val srv = f.ports.firstNotNullOfOrNull { p ->
                try { ServerSocket().apply { reuseAddress = true; bind(InetSocketAddress(p), 8) } } catch (_: Exception) { null }
            } ?: throw ErreurCompte("Les ports ${f.ports.joinToString()} sont occupés sur ce téléphone.")
            var code: String? = null
            var retour = ""
            try { srv.use { s0 ->
                s0.soTimeout = 5 * 60_000
                retour = f.retour.format(s0.localPort)
                val params = (linkedMapOf("client_id" to f.id, "redirect_uri" to retour, "response_type" to "code",
                    "code_challenge" to defi, "code_challenge_method" to "S256", "state" to etatAleatoire) + f.extra).toMutableMap()
                if (f.portee.isNotEmpty()) params["scope"] = f.portee
                if (!indice.isNullOrEmpty() && f.cle == "gdrive") params["login_hint"] = indice
                val url = f.auth + "?" + formulaire(params)
                withContext(Dispatchers.Main) {
                    AttenteConnexion.demarrer(ctx, ctx.getString(R.string.attente_navigateur))
                    ctx.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
                }
                while (code == null) {
                    val so = try { s0.accept() } catch (e: java.net.SocketTimeoutException) {
                        throw ErreurCompte("Pas de réponse dans les 5 minutes : recommencez.")
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
                        if (q["error"] != null) throw ErreurCompte("${f.nom} a refusé : ${q["error_description"] ?: q["error"]}")
                        if (ok) code = q["code"]
                    }
                }
            } } catch (e: Exception) { AttenteConnexion.arreter(ctx); throw e }
            // attendre le retour dans PhilPDF (bouton « Revenir a PhilPDF » de la page, ou l'utilisateur revient lui-meme)
            if (!premierPlan.value) {
                attente(ctx.getString(R.string.attente_retour))
                withTimeoutOrNull(10 * 60_000L) { premierPlan.first { it } }
                    ?: run { AttenteConnexion.arreter(ctx); throw ErreurCompte("PhilPDF n'a pas été rouvert : recommencez.") }
            }
            AttenteConnexion.arreter(ctx)
            attente(ctx.getString(R.string.connexion_en_cours))
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
            enregistrer(ctx, this@Nuage)
        }

    private fun pageRetour(f: Fournisseur, ok: Boolean, erreur: String?, vide: Boolean): String {
        // pas de redirection automatique : certains navigateurs la bloquent (« null est inaccessible ») ; un vrai bouton marche partout
        val lien = "intent://connecte#Intent;scheme=philpdf;package=${BuildConfig.APPLICATION_ID};end"
        val msg = when {
            ok -> "C'est fait : PhilPDF est relié à votre ${f.nom}."
            vide -> "PhilPDF attend la réponse de ${f.nom}."
            else -> "Connexion refusée${erreur?.let { " ($it)" } ?: ""}."
        }
        return """<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>PhilPDF</title><style>body{font-family:sans-serif;text-align:center;padding:40px 16px;background:#f3f3f3;color:#222}
a{display:inline-block;margin-top:24px;padding:16px 32px;background:#C9252D;color:#fff;border-radius:28px;text-decoration:none;font-size:20px}</style></head>
<body><h2>$msg</h2><a href="$lien">Revenir à PhilPDF</a></body></html>"""
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
                    ?: throw ErreurCompte("Autorisation perdue : reconnectez le compte ${f.nom}.")
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
        throw ErreurCompte("${fournisseur(ctx).nom} : autorisation refusée.")
    }

    /** Contenu d'une adresse (en suivant une redirection signee, sans envoyer le jeton). */
    private suspend fun telecharger(ctx: Context, methode: String, url: String, corps: ByteArray? = null,
                                    entetes: Map<String, String> = emptyMap()): ByteArray? {
        val (code, b, ailleurs) = appel(ctx, methode, url, corps, entetes)
        if (ailleurs != null) return withContext(Dispatchers.IO) { URL(ailleurs).openStream().use { it.readBytes() } }
        if (code == 404 || code == 409) return null
        if (code !in 200..299) throw ErreurCompte("${fournisseur(ctx).nom} : erreur $code ${String(b).take(200)}")
        return b
    }

    private suspend fun json(ctx: Context, methode: String, url: String, corps: JSONObject? = null): JSONObject? {
        // POST sans argument (Dropbox) : corps JSON « null »
        val envoi = corps?.toString()?.toByteArray() ?: if (methode == "POST") "null".toByteArray() else null
        val (code, b, _) = appel(ctx, methode, url, envoi,
            if (envoi != null) mapOf("Content-Type" to "application/json") else emptyMap())
        if (code == 404 || code == 409) return null
        if (code !in 200..299) throw ErreurCompte("${fournisseur(ctx).nom} : erreur $code ${String(b).take(200)}")
        return JSONObject(String(b))
    }

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

    fun racineParcours(ctx: Context): String = when (fournisseur(ctx).cle) { "dropbox" -> ""; "box" -> "0"; else -> "root" }

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
        return out.filter { it.dossier || it.nom.lowercase().endsWith(".pdf") }
            .sortedWith(compareBy<Entree>({ !it.dossier }, { it.nom.lowercase() }))
    }

    /** Copie le fichier sur le telephone et retient d'ou il vient (pour « Meme fichier »). */
    suspend fun ouvrirFichier(ctx: Context, e: Entree): Uri {
        val b = contenuFichier(ctx, e.id) ?: throw ErreurCompte("Fichier introuvable sur ${fournisseur(ctx).nom}.")
        val f = File(ctx.filesDir, "comptes/fichiers/$id/${empreinte(e.id)}/${e.nom.replace('/', '_')}")
        withContext(Dispatchers.IO) { f.parentFile?.mkdirs(); f.writeBytes(b) }
        Distants.retenir(ctx, f, Origine(id, e.id, e.nom))
        return Uri.fromFile(f)
    }

    suspend fun contenuFichier(ctx: Context, fid: String): ByteArray? = when (fournisseur(ctx).cle) {
        "gdrive" -> telecharger(ctx, "GET", "$GOOGLE/files/$fid?alt=media")
        "onedrive" -> telecharger(ctx, "GET", "$GRAPH/me/drive/items/$fid/content")
        "dropbox" -> telecharger(ctx, "POST", "$DBX_CONTENU/files/download", ByteArray(0),
            mapOf("Dropbox-API-Arg" to ascii(JSONObject().put("path", fid).toString()), "Content-Type" to "text/plain; charset=dropbox-cors-hack"))
        "box" -> telecharger(ctx, "GET", "$BOX/files/$fid/content")
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
            else -> Triple(0, ByteArray(0), null)
        }
        if (code !in 200..299) throw ErreurCompte("${fournisseur(ctx).nom} : envoi refusé ($code) ${String(b).take(160)}")
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
        return when (fournisseur(ctx).cle) {
            "gdrive" -> contenuFichier(ctx, idParChemin(rel) { p, n -> gEnfant(ctx, p, n)?.getString("id") } ?: return null)
            "onedrive" -> telecharger(ctx, "GET", "$GRAPH/me/drive/items/$racine:/" + rel.split("/").joinToString("/") { enc(it) } + ":/content")
            "dropbox" -> contenuFichier(ctx, "$racine/$rel")
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
            throw ErreurCompte("Pas de réseau pour PhilPDF (${derniere?.message}). Vérifiez la connexion, et que l'économiseur de données ne bloque pas PhilPDF.")
        }

        private fun post(url: String, champs: Map<String, String>): ByteArray = reessayer {
            val c = URL(url).openConnection() as HttpURLConnection
            c.requestMethod = "POST"; c.doOutput = true; c.connectTimeout = 15_000; c.readTimeout = 30_000
            c.setRequestProperty("Content-Type", "application/x-www-form-urlencoded")
            c.outputStream.use { it.write(formulaire(champs).toByteArray()) }
            if (c.responseCode !in 200..299) {
                val msg = c.errorStream?.readBytes()?.let { String(it) }?.take(200) ?: ""
                throw ErreurCompte("Autorisation : erreur ${c.responseCode} $msg")
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
        val n = Nuage.liste(ctx).firstOrNull { it.id == o.compte } ?: throw ErreurCompte("Le compte d'origine n'est plus relié : choisissez « Autre nom ».")
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

    private fun sync(ctx: Context): Nuage = Nuage.synchro(ctx) ?: throw ErreurCompte("Aucun compte de synchronisation relié.")

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
                val octets = sync(ctx).lire(ctx, "sauvegarde/${e.genre}/${e.id}${e.ext}") ?: return@forEachIndexed
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
