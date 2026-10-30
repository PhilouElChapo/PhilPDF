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

/**
 * Compte Google du telephone, relie au meme Drive que PhilPDF Windows.
 *
 * Meme autorisation que sous Windows (drive.file : PhilPDF ne voit QUE les fichiers qu'il a crees lui-meme,
 * jamais le reste du Drive). Deux facons de l'obtenir :
 *  - « telephone » : le compte Google deja present dans Android (aucun mot de passe, un seul « Autoriser ») ;
 *  - « navigateur » : si Google refuse la premiere (PhilPDF Android pas encore declare chez Google),
 *    la page Google s'ouvre dans le navigateur, le compte deja choisi, puis on revient a PhilPDF.
 */
object Google {
    const val PORTEE = "https://www.googleapis.com/auth/drive.file"
    private const val AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
    private const val JETON = "https://oauth2.googleapis.com/token"
    const val API = "https://www.googleapis.com/drive/v3"

    /** Activite au premier plan : Android y affiche lui-meme l'ecran « Autoriser » quand il le faut. */
    var activite: WeakReference<Activity>? = null

    private var acces: String? = null
    private var expire = 0L

    private fun prefs(ctx: Context) = ctx.getSharedPreferences("compte", Context.MODE_PRIVATE)
    fun email(ctx: Context): String? = prefs(ctx).getString("email", null)
    fun nom(ctx: Context): String? = prefs(ctx).getString("nom", null)
    fun mode(ctx: Context): String? = prefs(ctx).getString("mode", null)
    fun photo(ctx: Context): File = File(ctx.filesDir, "compte/photo.png")
    fun connecte(ctx: Context) = email(ctx) != null && mode(ctx) != null

    /** Liste des comptes Google du telephone (ecran d'Android, aucune autorisation a demander). */
    fun intentChoisir(): Intent =
        AccountManager.newChooseAccountIntent(null, null, arrayOf("com.google"), null, null, null, null)

    fun deconnecter(ctx: Context) {
        val e = email(ctx)
        val a = acces
        if (mode(ctx) == "telephone" && a != null) {
            try { AccountManager.get(ctx).invalidateAuthToken("com.google", a) } catch (_: Exception) {}
        }
        acces = null; expire = 0
        prefs(ctx).edit().clear().apply()
        photo(ctx).delete()
        Bibliotheque.oublier(ctx)
        android.util.Log.i("PhilPDF", "compte $e deconnecte")
    }

    // ------------------------------------------------------------ connexion par le compte du telephone
    /** Essaie le compte Android ; renvoie false si Google refuse (on proposera alors le navigateur). */
    suspend fun connecterTelephone(ctx: Context, email: String): Boolean = withContext(Dispatchers.IO) {
        try {
            val j = jetonTelephone(ctx, email)
            prefs(ctx).edit().putString("email", email).putString("mode", "telephone").apply()
            acces = j; expire = System.currentTimeMillis() + 50 * 60_000
            true
        } catch (e: android.accounts.OperationCanceledException) {
            throw ErreurCompte("Connexion annulée.")
        } catch (e: Exception) {
            android.util.Log.w("PhilPDF", "compte telephone refuse : $e")
            false
        }
    }

    private fun jetonTelephone(ctx: Context, email: String): String {
        val am = AccountManager.get(ctx)
        val f = am.getAuthToken(Account(email, "com.google"), "oauth2:$PORTEE", null, activite?.get(), null, null)
        val b = f.result                                     // bloquant : jamais sur le fil de l'interface
        return b.getString(AccountManager.KEY_AUTHTOKEN)
            ?: throw ErreurCompte("Google demande de vous reconnecter (Accueil, en haut à droite).")
    }

    // ------------------------------------------------------------ connexion par le navigateur
    /** Ouvre la page Google dans le navigateur (compte pre-choisi) et attend le retour sur 127.0.0.1. */
    suspend fun connecterNavigateur(ctx: Context, email: String): Unit = withContext(Dispatchers.IO) {
        if (BuildConfig.GOOGLE_ID.isEmpty()) throw ErreurCompte("Cette version n'a pas l'identifiant Google de PhilPDF.")
        val verif = Base64.encodeToString(ByteArray(48).also { SecureRandom().nextBytes(it) },
            Base64.URL_SAFE or Base64.NO_PADDING or Base64.NO_WRAP)
        val defi = Base64.encodeToString(MessageDigest.getInstance("SHA-256").digest(verif.toByteArray()),
            Base64.URL_SAFE or Base64.NO_PADDING or Base64.NO_WRAP)
        val etatAleatoire = java.util.UUID.randomUUID().toString()
        ServerSocket(0, 4, InetAddress.getByName("127.0.0.1")).use { srv ->
            srv.soTimeout = 5 * 60_000
            val retour = "http://127.0.0.1:${srv.localPort}"
            val url = AUTH + "?" + formulaire(mapOf(
                "client_id" to BuildConfig.GOOGLE_ID, "redirect_uri" to retour, "response_type" to "code",
                "scope" to PORTEE, "code_challenge" to defi, "code_challenge_method" to "S256",
                "access_type" to "offline", "prompt" to "consent", "login_hint" to email, "state" to etatAleatoire))
            withContext(Dispatchers.Main) {
                ctx.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
            }
            var code: String? = null
            while (code == null) {
                val s = try { srv.accept() } catch (e: java.net.SocketTimeoutException) {
                    throw ErreurCompte("Pas de réponse de Google dans les 5 minutes : recommencez.")
                }
                s.use { so ->
                    val ligne = so.getInputStream().bufferedReader().readLine() ?: ""
                    val chemin = ligne.split(" ").getOrNull(1) ?: ""
                    val p = chemin.substringAfter('?', "").split('&').filter { '=' in it }
                        .associate { URLDecoder.decode(it.substringBefore('='), "UTF-8") to URLDecoder.decode(it.substringAfter('='), "UTF-8") }
                    val ok = p["code"] != null && p["state"] == etatAleatoire
                    val page = pageRetour(ok, p["error"])
                    so.getOutputStream().write(("HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\n" +
                        "Content-Length: ${page.toByteArray().size}\r\nConnection: close\r\n\r\n$page").toByteArray())
                    so.getOutputStream().flush()
                    if (p["error"] != null) throw ErreurCompte("Google a refusé : ${p["error"]}")
                    if (ok) code = p["code"]
                }
            }
            val r = JSONObject(String(post(JETON, mapOf(
                "code" to code!!, "client_id" to BuildConfig.GOOGLE_ID, "client_secret" to BuildConfig.GOOGLE_SECRET,
                "redirect_uri" to retour, "grant_type" to "authorization_code", "code_verifier" to verif))))
            val rafraichir = r.optString("refresh_token")
            if (rafraichir.isEmpty()) throw ErreurCompte("Google n'a pas donné d'autorisation durable : recommencez.")
            acces = r.getString("access_token"); expire = System.currentTimeMillis() + (r.optLong("expires_in", 3600) - 120) * 1000
            prefs(ctx).edit().putString("email", email).putString("mode", "navigateur")
                .putString("jeton", Coffre.chiffrer(rafraichir)).apply()
        }
    }

    private fun pageRetour(ok: Boolean, erreur: String?): String {
        val lien = "intent://connecte#Intent;scheme=philpdf;package=${BuildConfig.APPLICATION_ID};end"
        val msg = if (ok) "PhilPDF est relié à votre Google Drive." else "Connexion refusée${erreur?.let { " ($it)" } ?: ""}."
        return """<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>PhilPDF</title><style>body{font-family:sans-serif;text-align:center;padding:40px 16px;background:#f3f3f3}
a{display:inline-block;margin-top:24px;padding:14px 28px;background:#C9252D;color:#fff;border-radius:24px;text-decoration:none;font-size:18px}</style></head>
<body><h2>$msg</h2><a href="$lien">Revenir à PhilPDF</a><script>setTimeout(function(){location.href="$lien"},400)</script></body></html>"""
    }

    // ------------------------------------------------------------ jeton d'acces et appels
    private suspend fun jeton(ctx: Context): String = withContext(Dispatchers.IO) {
        val a = acces
        if (a != null && System.currentTimeMillis() < expire) return@withContext a
        val e = email(ctx) ?: throw ErreurCompte("Aucun compte Google relié.")
        val j = when (mode(ctx)) {
            "telephone" -> jetonTelephone(ctx, e).also { expire = System.currentTimeMillis() + 50 * 60_000 }
            "navigateur" -> {
                val r = prefs(ctx).getString("jeton", null)?.let { Coffre.dechiffrer(it) }
                    ?: throw ErreurCompte("Autorisation perdue : reconnectez le compte (Accueil, en haut à droite).")
                val o = JSONObject(String(post(JETON, mapOf("client_id" to BuildConfig.GOOGLE_ID,
                    "client_secret" to BuildConfig.GOOGLE_SECRET, "refresh_token" to r, "grant_type" to "refresh_token"))))
                expire = System.currentTimeMillis() + (o.optLong("expires_in", 3600) - 120) * 1000
                o.getString("access_token")
            }
            else -> throw ErreurCompte("Aucun compte Google relié.")
        }
        acces = j
        j
    }

    /** GET authentifie ; un jeton perime est renouvele une fois. */
    suspend fun lire(ctx: Context, url: String): ByteArray = withContext(Dispatchers.IO) {
        for (essai in 0..1) {
            val j = jeton(ctx)
            val c = URL(url).openConnection() as HttpURLConnection
            c.connectTimeout = 15_000; c.readTimeout = 30_000
            c.setRequestProperty("Authorization", "Bearer $j")
            val code = c.responseCode
            if (code == 401 && essai == 0) {
                if (mode(ctx) == "telephone") try { AccountManager.get(ctx).invalidateAuthToken("com.google", j) } catch (_: Exception) {}
                acces = null; expire = 0
                continue
            }
            if (code !in 200..299) {
                val msg = c.errorStream?.readBytes()?.let { String(it) }?.take(200) ?: ""
                throw ErreurCompte("Google Drive : erreur $code $msg")
            }
            return@withContext c.inputStream.use { it.readBytes() }
        }
        throw ErreurCompte("Google Drive : autorisation refusée.")
    }

    private fun post(url: String, champs: Map<String, String>): ByteArray {
        val c = URL(url).openConnection() as HttpURLConnection
        c.requestMethod = "POST"; c.doOutput = true; c.connectTimeout = 15_000; c.readTimeout = 30_000
        c.setRequestProperty("Content-Type", "application/x-www-form-urlencoded")
        c.outputStream.use { it.write(formulaire(champs).toByteArray()) }
        if (c.responseCode !in 200..299) {
            val msg = c.errorStream?.readBytes()?.let { String(it) }?.take(200) ?: ""
            throw ErreurCompte("Google : erreur ${c.responseCode} $msg")
        }
        return c.inputStream.use { it.readBytes() }
    }

    private fun formulaire(m: Map<String, String>) =
        m.entries.joinToString("&") { URLEncoder.encode(it.key, "UTF-8") + "=" + URLEncoder.encode(it.value, "UTF-8") }

    /** Nom, adresse et photo du compte (affiches en haut a droite de l'Accueil). */
    suspend fun profil(ctx: Context) = withContext(Dispatchers.IO) {
        val u = JSONObject(String(lire(ctx, "$API/about?fields=user(emailAddress,displayName,photoLink)"))).optJSONObject("user")
            ?: return@withContext
        prefs(ctx).edit().putString("nom", u.optString("displayName")).apply()
        u.optString("photoLink").takeIf { it.isNotEmpty() }?.let { lien ->
            try {
                val b = URL(lien).openStream().use { it.readBytes() }
                photo(ctx).parentFile?.mkdirs()
                photo(ctx).writeBytes(b)
            } catch (_: Exception) {}
        }
    }

    // ------------------------------------------------------------ fichiers du Drive
    private fun q(q: String) = "$API/files?" + formulaire(mapOf("q" to q, "spaces" to "drive", "pageSize" to "1000",
        "fields" to "files(id,name,mimeType,size,modifiedTime,parents)"))

    private fun echapper(n: String) = n.replace("\\", "\\\\").replace("'", "\\'")

    suspend fun chercher(ctx: Context, requete: String): List<JSONObject> {
        val a = JSONObject(String(lire(ctx, q(requete)))).optJSONArray("files") ?: JSONArray()
        return (0 until a.length()).map { a.getJSONObject(it) }
    }

    suspend fun enfant(ctx: Context, parent: String, nom: String): JSONObject? =
        chercher(ctx, "name = '${echapper(nom)}' and '$parent' in parents and trashed = false").firstOrNull()

    suspend fun contenu(ctx: Context, id: String): ByteArray = lire(ctx, "$API/files/$id?alt=media")

    /** Dossier PhilPDF cree par PhilPDF Windows : a la racine du Drive d'abord, sinon ailleurs. */
    suspend fun dossierPhilpdf(ctx: Context): String? {
        val dossier = "mimeType = 'application/vnd.google-apps.folder' and name = 'PhilPDF' and trashed = false"
        chercher(ctx, "$dossier and 'root' in parents").firstOrNull()?.let { return it.getString("id") }
        return chercher(ctx, dossier).firstOrNull { enfant(ctx, it.getString("id"), "preferences.json") != null }?.getString("id")
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

/** Ce que l'on lit dans le dossier PhilPDF du Drive. */
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

    /** Lit le dossier PhilPDF : postes (preferences.json, session.json) et bibliotheque (sauvegarde/index.json). */
    suspend fun lireDrive(ctx: Context): EtatDrive {
        val racine = Google.dossierPhilpdf(ctx) ?: return EtatDrive(false, emptyList(), emptyList(), 0)
        suspend fun json(parent: String, nom: String): JSONObject? = try {
            Google.enfant(ctx, parent, nom)?.let { JSONObject(String(Google.contenu(ctx, it.getString("id")))) }
        } catch (_: Exception) { null }
        val pref = json(racine, "preferences.json") ?: JSONObject()
        val sess = json(racine, "session.json") ?: JSONObject()
        val par = pref.optJSONObject("communs")?.optString("par") ?: ""
        val noms = LinkedHashSet<String>()
        pref.optJSONObject("postes")?.keys()?.forEach { noms += it }
        sess.keys().forEach { if (sess.optJSONObject(it) != null) noms += it }
        val postes = noms.map { m ->
            val p = pref.optJSONObject("postes")?.optJSONObject(m)
            val s = sess.optJSONObject(m)
            Poste(m, maxOf(p?.optString("maj") ?: "", s?.optString("maj") ?: ""), s?.optJSONArray("fichiers")?.length() ?: 0, m == par)
        }.sortedByDescending { it.activite }
        val sauv = Google.enfant(ctx, racine, "sauvegarde")
        val distants = sauv?.let { json(it.getString("id"), "index.json") }?.let { ix ->
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
        val racine = Google.dossierPhilpdf(ctx) ?: throw ErreurCompte("Dossier PhilPDF introuvable sur ce Drive.")
        val sauv = Google.enfant(ctx, racine, "sauvegarde")?.getString("id") ?: throw ErreurCompte("Aucune bibliothèque sur ce Drive.")
        val ici = locaux(ctx).associateBy { it.id }
        val dossiersGenre = HashMap<String, String?>()
        val gardes = ArrayList<ElementBiblio>()
        var n = 0
        distants.forEachIndexed { i, e ->
            avance(i, distants.size)
            val deja = ici[e.id]
            if (deja != null && deja.hash == e.hash && fichier(ctx, deja).exists()) { gardes += deja; return@forEachIndexed }
            try {
                val dg = dossiersGenre.getOrPut(e.genre) { Google.enfant(ctx, sauv, e.genre)?.getString("id") } ?: return@forEachIndexed
                val f = Google.enfant(ctx, dg, e.id + e.ext) ?: return@forEachIndexed
                val octets = Google.contenu(ctx, f.getString("id"))
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
