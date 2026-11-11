package io.github.philouelchapo.philpdf

import android.content.Context
import android.util.Base64
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.math.BigInteger
import java.net.HttpURLConnection
import java.net.URL

/**
 * Assistant IA, comme sous Windows : Claude (Anthropic) ou Gemini (Google), avec VOTRE clef API (le cout est
 * celui de votre compte chez le fournisseur). Rien ne part sans un geste : avant chaque envoi, les donnees sensibles
 * reperees dans le texte (IBAN, carte bancaire, securite sociale, numero fiscal, mot de passe) sont signalees.
 * Les clefs sont gardees chiffrees sur le telephone (clef du telephone, AndroidKeyStore).
 */
object Ia {
    private const val CLAUDE_API = "https://api.anthropic.com/v1"
    private const val GEMINI_API = "https://generativelanguage.googleapis.com/v1beta"
    private const val MODELE_CLAUDE = "claude-sonnet-5-5"
    private const val MODELE_GEMINI = "gemini-2.5-flash"
    private val PASSAGERS = setOf(429, 500, 502, 503, 504)

    class ErreurIa(message: String, val code: Int = 0, val passager: Boolean = false) : Exception(message)

    /** Qui a vraiment repondu a la derniere demande : moteur ("claude" ou "gemini") et modele. */
    @Volatile var dernier: Pair<String, String>? = null
    private val trouves = HashMap<String, String>()          // modele qui marche, par moteur
    private val bearer = HashSet<String>()                    // clefs Claude presentees en « Authorization: Bearer »

    private fun prefs(ctx: Context) = ctx.getSharedPreferences("ia", Context.MODE_PRIVATE)

    fun nettoyerClef(c: String?): String = (c ?: "").replace(Regex("[\\s\"'«»]+"), "")

    fun clef(ctx: Context, moteur: String): String =
        prefs(ctx).getString("clef_$moteur", null)?.let { Coffre.dechiffrer(it) }?.let { nettoyerClef(it) } ?: ""

    fun poserClef(ctx: Context, moteur: String, valeur: String) {
        val v = nettoyerClef(valeur)
        prefs(ctx).edit().apply { if (v.isEmpty()) remove("clef_$moteur") else putString("clef_$moteur", Coffre.chiffrer(v)) }.apply()
    }

    /** IA choisie : "claude" ou "gemini". */
    fun moteurPrefere(ctx: Context): String = prefs(ctx).getString("moteur", "claude") ?: "claude"
    fun poserMoteur(ctx: Context, m: String) = prefs(ctx).edit().putString("moteur", m).apply()

    /** Moteurs qui ont une clef, dans l'ordre de preference (force : celui choisi pour cette demande). */
    fun moteurs(ctx: Context, force: String? = null): List<Pair<String, String>> {
        val choix = force ?: moteurPrefere(ctx)
        val ordre = if (choix == "gemini") listOf("gemini", "claude") else listOf("claude", "gemini")
        return ordre.map { it to clef(ctx, it) }.filter { it.second.isNotEmpty() }
    }

    fun disponible(ctx: Context): Boolean = moteurs(ctx).isNotEmpty()
    fun nom(m: String?): String = when (m) { "claude" -> "Claude"; "gemini" -> "Gemini"; else -> "?" }

    /** Consignes perso deja utilisees (gardees seulement sur demande), par sujet : resume, texte... */
    fun consignes(ctx: Context, sujet: String): List<String> = try {
        val a = JSONArray(prefs(ctx).getString("consignes_$sujet", "[]")); (0 until a.length()).map { a.getString(it) }
    } catch (_: Exception) { emptyList() }
    fun garderConsigne(ctx: Context, sujet: String, c: String) {
        val l = (listOf(c) + consignes(ctx, sujet).filter { it != c }).take(10)
        prefs(ctx).edit().putString("consignes_$sujet", JSONArray(l).toString()).apply()
    }
    fun oublierConsigne(ctx: Context, sujet: String, c: String) {
        prefs(ctx).edit().putString("consignes_$sujet", JSONArray(consignes(ctx, sujet).filter { it != c }).toString()).apply()
    }

    fun ajouterConsigne(consignes: String, perso: String?): String = if (perso.isNullOrBlank()) consignes else
        consignes + "\n\nConsigne supplémentaire de l'utilisateur (à suivre en priorité, en gardant le format de réponse demandé) :\n" + perso.trim()

    // ------------------------------------------------------------ donnees sensibles (comme sous Windows)
    private fun luhn(ch: String): Boolean {
        var s = 0; var double = false
        for (c in ch.reversed()) { var n = (c - '0') * if (double) 2 else 1; if (n > 9) n -= 9; s += n; double = !double }
        return s % 10 == 0
    }

    private fun ibanValide(iban: String): Boolean = try {
        val r = iban.substring(4) + iban.substring(0, 4)
        BigInteger(r.map { c -> Character.getNumericValue(c).toString() }.joinToString("")).mod(BigInteger.valueOf(97)).toInt() == 1
    } catch (_: Exception) { false }

    private fun nirValide(nir: String): Boolean = try {
        val corps = nir.substring(0, 13).uppercase().replace("2A", "19").replace("2B", "18")
        97 - BigInteger(corps).mod(BigInteger.valueOf(97)).toInt() == nir.substring(13).toInt()
    } catch (_: Exception) { false }

    /** (genre, extrait masque) des donnees sensibles reperees. */
    fun sensibles(texte: String): List<Pair<String, String>> {
        val out = LinkedHashSet<Pair<String, String>>()
        Regex("\\b[A-Z]{2}\\d{2}(?: ?[A-Z0-9]){11,30}\\b").findAll(texte).forEach { m ->
            val b = m.value.replace(" ", "")
            if (b.length in 15..34 && ibanValide(b)) out += Textes.t(R.string.ia_s_iban) to b.take(4) + " ... " + b.takeLast(4)
        }
        Regex("\\b(?:\\d[ -]?){13,19}\\b").findAll(texte).forEach { m ->
            val ch = m.value.filter { it.isDigit() }
            if (ch.length in 13..19 && ch[0] in "3456" && luhn(ch)) out += Textes.t(R.string.ia_s_carte) to "**** " + ch.takeLast(4)
        }
        Regex("\\b([12]) ?(\\d{2}) ?(\\d{2}) ?(\\d{2}|2A|2B) ?(\\d{3}) ?(\\d{3}) ?(\\d{2})\\b").findAll(texte).forEach { m ->
            val nir = m.groupValues.drop(1).joinToString("")
            if (nirValide(nir)) out += Textes.t(R.string.ia_s_secu) to nir.take(1) + " ** ** ** *** *** " + nir.takeLast(2)
        }
        Regex("(?i)(?:num[ée]ro fiscal|n° fiscal|SPI)\\D{0,12}([0-3]\\d(?: ?\\d){11})\\b").findAll(texte).forEach { m ->
            out += Textes.t(R.string.ia_s_fiscal) to m.groupValues[1].take(2) + " ... "
        }
        Regex("(?i)\\b(mot de passe|password|code confidentiel|code secret)\\b\\s*[:=]\\s*\\S+").findAll(texte).forEach { m ->
            out += Textes.t(R.string.ia_s_mdp) to m.groupValues[1] + " : ****"
        }
        return out.toList()
    }

    // ------------------------------------------------------------ appels
    private fun http(url: String, corps: JSONObject?, entetes: Map<String, String>, delaiS: Int = 180): JSONObject {
        val c = URL(url).openConnection() as HttpURLConnection
        try {
            c.connectTimeout = 20_000; c.readTimeout = delaiS * 1000
            c.requestMethod = if (corps != null) "POST" else "GET"
            c.setRequestProperty("Content-Type", "application/json")
            entetes.forEach { (k, v) -> c.setRequestProperty(k, v) }
            if (corps != null) { c.doOutput = true; c.outputStream.use { it.write(corps.toString().toByteArray()) } }
            val code = c.responseCode
            val brut = (if (code in 200..299) c.inputStream else c.errorStream)?.use { it.readBytes() } ?: ByteArray(0)
            val txt = String(brut, Charsets.UTF_8)
            if (code !in 200..299) {
                val msg = try { JSONObject(txt).optJSONObject("error")?.optString("message") } catch (_: Exception) { null } ?: txt.take(300)
                throw ErreurIa("$code : ${expliquer(code, msg).ifEmpty { msg }}", code, code in PASSAGERS)
            }
            return JSONObject(txt)
        } catch (e: ErreurIa) { throw e
        } catch (e: java.net.SocketTimeoutException) { throw ErreurIa(Textes.t(R.string.ia_e_delai), 0, true)
        } catch (e: java.io.IOException) { throw ErreurIa(Textes.t(R.string.ia_e_injoignable, e.message ?: e.toString()), 0, true)
        } finally { c.disconnect() }
    }

    private fun expliquer(code: Int, msg: String): String = when {
        code == 429 && "limit: 0" in msg -> Textes.t(R.string.ia_e_quota0)
        code == 429 && ("per day" in msg || "PerDay" in msg) -> Textes.t(R.string.ia_e_quota_jour)
        code == 429 -> Textes.t(R.string.ia_e_quota_minute)
        code in 500..504 -> Textes.t(R.string.ia_e_surcharge, code)
        else -> ""
    }

    private fun typeImage(o: ByteArray) = if (o.size > 3 && o[0] == 0xFF.toByte() && o[1] == 0xD8.toByte()) "image/jpeg" else "image/png"

    private fun entetesClaude(clef: String, autre: Boolean): Map<String, String> {
        val b = (clef in bearer) != autre
        return mapOf("anthropic-version" to "2023-06-01") + if (b) mapOf("Authorization" to "Bearer $clef") else mapOf("x-api-key" to clef)
    }

    private fun modeleClaudeRecent(clef: String): String {
        val d = http("$CLAUDE_API/models?limit=100", null, entetesClaude(clef, false), 30).optJSONArray("data") ?: JSONArray()
        val ids = (0 until d.length()).map { d.getJSONObject(it).optString("id") }
        for (f in listOf("sonnet", "opus", "haiku")) ids.firstOrNull { f in it }?.let { trouves["claude"] = it; return it }
        throw ErreurIa(Textes.t(R.string.ia_e_aucun_modele, "Claude"))
    }

    private fun claude(clef: String, consignes: String, texte: String, images: List<ByteArray>, maxJetons: Int): String {
        val contenu = JSONArray()
        images.forEach { i -> contenu.put(JSONObject().put("type", "image").put("source", JSONObject().put("type", "base64")
            .put("media_type", typeImage(i)).put("data", Base64.encodeToString(i, Base64.NO_WRAP)))) }
        contenu.put(JSONObject().put("type", "text").put("text", texte))
        var modele = trouves["claude"] ?: MODELE_CLAUDE
        var autre = false; var recent = false
        repeat(3) {
            try {
                val corps = JSONObject().put("model", modele).put("max_tokens", maxJetons).put("system", consignes)
                    .put("messages", JSONArray().put(JSONObject().put("role", "user").put("content", contenu)))
                val d = http("$CLAUDE_API/messages", corps, entetesClaude(clef, autre))
                if (autre) { if (clef in bearer) bearer -= clef else bearer += clef }
                trouves["claude"] = modele; dernier = "claude" to modele
                val c = d.optJSONArray("content") ?: JSONArray()
                return (0 until c.length()).map { c.getJSONObject(it) }.filter { it.optString("type") == "text" }.joinToString("") { it.optString("text") }
            } catch (e: ErreurIa) {
                when {
                    e.code == 404 && !recent -> { recent = true; modele = modeleClaudeRecent(clef) }   // modele retire
                    e.code in setOf(401, 403) && !autre -> autre = true                               // autre facon de presenter la clef
                    e.code in setOf(401, 403) -> throw ErreurIa(Textes.t(R.string.ia_e_clef_claude, e.message ?: ""), e.code)
                    else -> throw e
                }
            }
        }
        throw ErreurIa(Textes.t(R.string.ia_e_aucun_modele, "Claude"))
    }

    private fun modelesGemini(clef: String): List<String> = try {
        val d = http("$GEMINI_API/models?pageSize=200", null, mapOf("x-goog-api-key" to clef), 30).optJSONArray("models") ?: JSONArray()
        (0 until d.length()).map { d.getJSONObject(it) }.filter { m ->
            val s = m.optJSONArray("supportedGenerationMethods"); s != null && (0 until s.length()).any { s.optString(it) == "generateContent" }
        }.map { it.optString("name").substringAfterLast('/') }
    } catch (_: ErreurIa) { emptyList() }

    private fun version(i: String) = Regex("gemini-(\\d+(?:\\.\\d+)?)").find(i)?.groupValues?.get(1)?.toFloatOrNull() ?: 0f

    private fun gemini(clef: String, consignes: String, texte: String, images: List<ByteArray>, maxJetons: Int, json: Boolean): String {
        val parts = JSONArray()
        images.forEach { i -> parts.put(JSONObject().put("inline_data", JSONObject().put("mime_type", typeImage(i)).put("data", Base64.encodeToString(i, Base64.NO_WRAP)))) }
        parts.put(JSONObject().put("text", texte))
        val conf = JSONObject().put("maxOutputTokens", maxJetons)
        if (json) conf.put("responseMimeType", "application/json")
        val corps = JSONObject().put("system_instruction", JSONObject().put("parts", JSONArray().put(JSONObject().put("text", consignes))))
            .put("contents", JSONArray().put(JSONObject().put("role", "user").put("parts", parts))).put("generationConfig", conf)
        val essais = ArrayDeque(listOf(trouves["gemini"] ?: MODELE_GEMINI))
        var liste = false
        while (essais.isNotEmpty()) {
            val modele = essais.removeFirst()
            try {
                val d = http("$GEMINI_API/models/$modele:generateContent", corps, mapOf("x-goog-api-key" to clef))
                val cands = d.optJSONArray("candidates")
                if (cands == null || cands.length() == 0)
                    throw ErreurIa(Textes.t(R.string.ia_e_gemini_rien, d.optJSONObject("promptFeedback")?.optString("blockReason") ?: "?"))
                trouves["gemini"] = modele; dernier = "gemini" to modele
                val p = cands.getJSONObject(0).optJSONObject("content")?.optJSONArray("parts") ?: JSONArray()
                return (0 until p.length()).joinToString("") { p.getJSONObject(it).optString("text") }
            } catch (e: ErreurIa) {
                if (e.code in setOf(400, 403) && "API key" in (e.message ?: "")) throw ErreurIa(Textes.t(R.string.ia_e_clef_gemini), e.code)
                if (e.code == 404 || e.passager) {
                    Journal.ecrire("IA gemini", "modèle $modele : ${e.message} → essai d'un autre modèle")
                    if (!liste) {
                        liste = true
                        val ids = modelesGemini(clef).filter { it.startsWith("gemini") && "exp" !in it && "preview" !in it &&
                            listOf("embedding", "tts", "image", "audio", "live").none { x -> x in it } }
                        val flash = ids.filter { "flash" in it && "lite" !in it }.sortedByDescending { version(it) }
                        val lite = ids.filter { "flash-lite" in it }.sortedByDescending { version(it) }
                        essais.addAll((flash + lite).filter { it != modele }.take(3))
                    }
                    if (essais.isNotEmpty()) continue
                }
                throw e
            }
        }
        throw ErreurIa(Textes.t(R.string.ia_e_aucun_modele, "Gemini"))
    }

    /**
     * Texte renvoye par le premier moteur qui repond (l'autre, s'il a une clef, prend le relais d'une panne passagere).
     * json : la reponse doit etre un objet JSON (lire avec lireJson). force : moteur choisi pour cette demande.
     */
    suspend fun demander(ctx: Context, consignes: String, texte: String, images: List<ByteArray> = emptyList(),
                         json: Boolean = false, maxJetons: Int = 4000, force: String? = null): String = withContext(Dispatchers.IO) {
        val ms = moteurs(ctx, force)
        if (ms.isEmpty()) throw ErreurIa(Textes.t(R.string.ia_e_aucune_clef))
        val c = if (json) consignes + "\n\nRéponds uniquement par un objet JSON valide, sans texte autour ni balises de code." else consignes
        var derniere: ErreurIa? = null
        for ((m, clef) in ms) {
            val t0 = System.currentTimeMillis()
            try {
                val r = if (m == "claude") claude(clef, c, texte, images, maxJetons) else gemini(clef, c, texte, images, maxJetons, json)
                Journal.ecrire("IA $m", "réponse en ${(System.currentTimeMillis() - t0) / 1000} s, modèle ${trouves[m]}, ${texte.length} car. envoyés" +
                    if (images.isNotEmpty()) ", ${images.size} image(s)" else "")
                Signalement.derniere = r.trim()
                return@withContext r.trim()
            } catch (e: ErreurIa) {
                Journal.ecrire("IA $m", "✕ après ${(System.currentTimeMillis() - t0) / 1000} s : ${e.message}")
                derniere = e
                if (!e.passager) break
            }
        }
        throw derniere ?: ErreurIa(Textes.t(R.string.ia_e_aucune_clef))
    }

    fun lireJson(texte: String): JSONObject {
        val t = texte.trim().replace(Regex("^```(?:json)?\\s*|\\s*```$"), "")
        try { return JSONObject(t) } catch (_: Exception) {}
        Regex("\\{.*\\}", RegexOption.DOT_MATCHES_ALL).find(t)?.let { try { return JSONObject(it.value) } catch (_: Exception) {} }
        throw ErreurIa(Textes.t(R.string.ia_e_illisible))
    }

    /**
     * Image modifiee par Gemini (Claude ne sait pas rendre d'image) : octets PNG ou JPEG.
     * Les modeles d'image proposes par la clef sont essayes du plus recent au plus ancien.
     */
    suspend fun image(ctx: Context, octets: ByteArray, consigne: String): ByteArray = withContext(Dispatchers.IO) {
        val clef = clef(ctx, "gemini")
        if (clef.isEmpty()) throw ErreurIa(Textes.t(R.string.ia_e_image_gemini))
        val corps = JSONObject().put("contents", JSONArray().put(JSONObject().put("role", "user").put("parts", JSONArray()
            .put(JSONObject().put("inline_data", JSONObject().put("mime_type", typeImage(octets)).put("data", Base64.encodeToString(octets, Base64.NO_WRAP))))
            .put(JSONObject().put("text", consigne)))))
            .put("generationConfig", JSONObject().put("responseModalities", JSONArray().put("TEXT").put("IMAGE")))
        val liste = trouves["gemini_image"]?.let { listOf(it) } ?: modelesGemini(clef)
            .filter { it.startsWith("gemini") && "image" in it && "imagen" !in it }
            .sortedWith(compareByDescending<String> { "preview" !in it && "exp" !in it }.thenByDescending { version(it) }.thenBy { "pro" in it })
            .ifEmpty { listOf("gemini-2.5-flash-image", "gemini-2.5-flash-image-preview") }.take(4)
        var derniere: ErreurIa? = null
        for (modele in liste) {
            try {
                val t0 = System.currentTimeMillis()
                val d = http("$GEMINI_API/models/$modele:generateContent", corps, mapOf("x-goog-api-key" to clef), 240)
                val cands = d.optJSONArray("candidates") ?: JSONArray()
                var raison = ""
                for (i in 0 until cands.length()) {
                    val p = cands.getJSONObject(i).optJSONObject("content")?.optJSONArray("parts") ?: continue
                    for (j in 0 until p.length()) {
                        val o = p.getJSONObject(j)
                        val data = o.optJSONObject("inline_data") ?: o.optJSONObject("inlineData")
                        if (data != null && data.optString("data").isNotEmpty()) {
                            trouves["gemini_image"] = modele; dernier = "gemini" to modele
                            Journal.ecrire("IA gemini", "image rendue en ${(System.currentTimeMillis() - t0) / 1000} s, modèle $modele")
                            return@withContext Base64.decode(data.getString("data"), Base64.DEFAULT)
                        }
                        raison += o.optString("text")
                    }
                }
                throw ErreurIa(Textes.t(R.string.ia_e_pas_image, d.optJSONObject("promptFeedback")?.optString("blockReason")?.ifEmpty { null } ?: raison.take(200).ifEmpty { "?" }))
            } catch (e: ErreurIa) {
                if (e.code in setOf(400, 403) && "API key" in (e.message ?: "")) throw ErreurIa(Textes.t(R.string.ia_e_clef_gemini), e.code)
                Journal.ecrire("IA gemini", "image, modèle $modele : ${e.message}")
                derniere = e
                if (e.code == 404 || e.passager) continue
                throw e
            }
        }
        throw derniere ?: ErreurIa(Textes.t(R.string.ia_e_aucun_modele, "Gemini"))
    }

    /** Petit essai d'une clef : renvoie le modele qui a repondu. */
    suspend fun tester(ctx: Context, moteur: String): String {
        demander(ctx, "Réponds seulement : OK", "Test de connexion de PhilPDF.", maxJetons = 20, force = moteur)
        val d = dernier
        if (d == null || d.first != moteur) throw ErreurIa(Textes.t(R.string.ia_e_aucune_clef))
        return d.second
    }

    /** Clefs Claude / Gemini de vos postes Windows (fichier chiffre de PhilPDF sur votre compte). Renvoie les moteurs repris. */
    suspend fun reprendreDePostes(ctx: Context, phrase: String): List<String> {
        val s = Identites.secretsWindows(ctx, phrase)
        val repris = ArrayList<String>()
        for (m in listOf("claude", "gemini")) {
            val v = nettoyerClef(s.optString("clef_$m"))
            if (v.isNotEmpty()) { poserClef(ctx, m, v); repris += m }
        }
        // l'IA choisie sur vos postes (reglages communs, sans secret)
        try {
            Nuage.synchro(ctx)?.lire(ctx, "preferences.json")?.let { JSONObject(String(it)).optJSONObject("communs")?.optString("ia_moteur") }
                ?.takeIf { it == "claude" || it == "gemini" }?.let { poserMoteur(ctx, it) }
        } catch (_: Exception) {}
        Journal.ecrire("IA", "clefs reprises de vos postes : ${repris.joinToString().ifEmpty { "aucune" }}")
        return repris
    }

    /** Texte du document recoupe en lignes d'environ la meme longueur que l'original (une ligne tapee = une ligne). */
    fun recouper(texte: String, original: String): String {
        val cible = original.split("\n").maxOfOrNull { it.length }?.coerceAtLeast(12) ?: return texte
        return texte.split("\n").joinToString("\n") { para ->
            val out = ArrayList<String>(); val l = StringBuilder()
            for (mot in para.split(Regex(" +")).filter { it.isNotEmpty() }) {
                if (l.isNotEmpty() && l.length + 1 + mot.length > cible) { out += l.toString(); l.clear() }
                if (l.isNotEmpty()) l.append(' ')
                l.append(mot)
            }
            out += l.toString()
            out.joinToString("\n")
        }
    }
}
