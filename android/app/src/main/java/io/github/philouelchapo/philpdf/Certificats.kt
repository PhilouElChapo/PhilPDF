package io.github.philouelchapo.philpdf

import android.content.Context
import android.util.Base64
import com.artifex.mupdf.fitz.Document
import com.artifex.mupdf.fitz.FitzInputStream
import com.artifex.mupdf.fitz.PDFDocument
import com.artifex.mupdf.fitz.PDFObject
import com.artifex.mupdf.fitz.PKCS7DistinguishedName
import com.artifex.mupdf.fitz.PKCS7Signer
import com.artifex.mupdf.fitz.PKCS7Verifier
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.bouncycastle.asn1.ASN1ObjectIdentifier
import org.bouncycastle.asn1.DERSet
import org.bouncycastle.asn1.cms.Attribute
import org.bouncycastle.asn1.cms.AttributeTable
import org.bouncycastle.asn1.pkcs.PKCSObjectIdentifiers
import org.bouncycastle.asn1.x500.style.BCStyle
import org.bouncycastle.cert.X509CertificateHolder
import org.bouncycastle.cert.jcajce.JcaCertStore
import org.bouncycastle.cert.jcajce.JcaX509CertificateHolder
import org.bouncycastle.cms.CMSProcessableByteArray
import org.bouncycastle.cms.CMSSignedData
import org.bouncycastle.cms.CMSSignedDataGenerator
import org.bouncycastle.cms.SignerInformation
import org.bouncycastle.cms.SignerInformationStore
import org.bouncycastle.cms.jcajce.JcaSignerInfoGeneratorBuilder
import org.bouncycastle.cms.jcajce.JcaSimpleSignerInfoVerifierBuilder
import org.bouncycastle.jce.provider.BouncyCastleProvider
import org.bouncycastle.operator.jcajce.JcaContentSignerBuilder
import org.bouncycastle.operator.jcajce.JcaDigestCalculatorProviderBuilder
import org.bouncycastle.tsp.TimeStampRequestGenerator
import org.bouncycastle.tsp.TimeStampResponse
import org.json.JSONArray
import org.json.JSONObject
import java.io.ByteArrayInputStream
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.security.KeyStore
import java.security.MessageDigest
import java.security.PrivateKey
import java.security.cert.CertificateFactory
import java.security.cert.X509Certificate

/** Une identite numerique (certificat + clef, fichier .pfx), comme dans PhilPDF Windows. */
data class Identite(val id: String, val nom: String, val email: String, val organisation: String, val emetteur: String,
                    val fin: String, val empreinte: String, val autosigne: Boolean)

/** Ce qu'on dit d'une signature trouvee dans le PDF. */
data class InfoSignature(val page: Int, val nom: String, val intacte: Boolean, val approuvee: Boolean, val autosignee: Boolean,
                         val modifieApres: Boolean, val message: String)

class ErreurCertificat(message: String) : Exception(message)

/**
 * Identites (.pfx) gardees sur le telephone, chiffrees par la clef du telephone (Keystore) ; le mot de passe du .pfx
 * est demande a chaque signature, jamais garde. Recuperables depuis PhilPDF Windows (fichier secrets.philpdf du
 * compte de synchronisation, ouvert avec votre phrase secrete) ou importees d'un fichier .pfx / .p12.
 */
object Identites {
    private val BC = BouncyCastleProvider()
    private fun dossier(ctx: Context) = File(ctx.filesDir, "identites").apply { mkdirs() }
    private fun index(ctx: Context) = File(dossier(ctx), "index.json")
    private fun approuves(ctx: Context) = File(dossier(ctx), "approuves.json")

    fun liste(ctx: Context): List<Identite> = try {
        val a = JSONArray(index(ctx).readText())
        (0 until a.length()).map { a.getJSONObject(it) }.map { o ->
            Identite(o.optString("id"), o.optString("nom"), o.optString("email"), o.optString("organisation"),
                o.optString("emetteur"), o.optString("fin"), o.optString("empreinte"), o.optBoolean("autosigne"))
        }
    } catch (_: Exception) { emptyList() }

    private fun ecrireListe(ctx: Context, l: List<Identite>) {
        val a = JSONArray()
        l.forEach { e -> a.put(JSONObject().put("id", e.id).put("nom", e.nom).put("email", e.email).put("organisation", e.organisation)
            .put("emetteur", e.emetteur).put("fin", e.fin).put("empreinte", e.empreinte).put("autosigne", e.autosigne)) }
        index(ctx).writeText(a.toString())
    }

    private fun fichier(ctx: Context, id: String) = File(dossier(ctx), "$id.pfx.chiffre")

    /** Clef et chaine de certificats du .pfx ; mot de passe faux : ErreurCertificat. */
    fun ouvrir(octets: ByteArray, mdp: String): Pair<PrivateKey, List<X509Certificate>> {
        val ks = KeyStore.getInstance("PKCS12", BC)
        try { ks.load(ByteArrayInputStream(octets), mdp.toCharArray()) }
        catch (e: Exception) { throw ErreurCertificat(Textes.t(R.string.err_cert_mdp)) }
        for (alias in ks.aliases()) {
            if (!ks.isKeyEntry(alias)) continue
            val clef = ks.getKey(alias, mdp.toCharArray()) as? PrivateKey ?: continue
            val chaine = ks.getCertificateChain(alias)?.map { it as X509Certificate } ?: continue
            if (chaine.isNotEmpty()) return clef to chaine
        }
        throw ErreurCertificat(Textes.t(R.string.err_cert_clef))
    }

    fun empreinte(c: X509Certificate): String = MessageDigest.getInstance("SHA-256").digest(c.encoded).joinToString("") { "%02X".format(it) }

    private fun champ(c: X509Certificate, oid: ASN1ObjectIdentifier, sujet: Boolean = true): String = try {
        val h = JcaX509CertificateHolder(c)
        val n = if (sujet) h.subject else h.issuer
        n.getRDNs(oid).firstOrNull()?.first?.value?.toString() ?: ""
    } catch (_: Exception) { "" }

    fun infos(id: String, c: X509Certificate) = Identite(id, champ(c, BCStyle.CN), champ(c, BCStyle.EmailAddress),
        champ(c, BCStyle.O), champ(c, BCStyle.CN, false).ifEmpty { champ(c, BCStyle.O, false) },
        java.text.SimpleDateFormat("yyyy-MM-dd", java.util.Locale.FRANCE).format(c.notAfter), empreinte(c),
        c.subjectX500Principal == c.issuerX500Principal)

    /** Ajoute un .pfx (mot de passe verifie). Deja present (meme certificat) : remplace. */
    fun ajouter(ctx: Context, octets: ByteArray, mdp: String, id: String? = null): Identite {
        val (_, chaine) = ouvrir(octets, mdp)
        val l = liste(ctx).toMutableList()
        val emp = empreinte(chaine[0])
        val ident = id ?: l.firstOrNull { it.empreinte == emp }?.id ?: java.util.UUID.randomUUID().toString().take(12)
        val e = infos(ident, chaine[0])
        fichier(ctx, ident).writeText(Coffre.chiffrer(Base64.encodeToString(octets, Base64.NO_WRAP)))
        val place = l.indexOfFirst { it.id == ident || it.empreinte == emp }   // deja la : garde sa place dans la liste
        l.removeAll { it.id == ident || it.empreinte == emp }
        if (place in 0..l.size) l.add(place, e) else l += e
        ecrireListe(ctx, l)
        oublierRetrait(ctx, ident)
        ajouterApprouve(ctx, chaine[0].encoded)                 // vos propres signatures sont approuvees
        Journal.ecrire("certificat", "identité ajoutée : ${e.nom} (jusqu'au ${e.fin})")
        return e
    }

    /** Identite de Windows dont on n'a pas encore verifie le mot de passe : gardee telle quelle, infos du Drive. */
    private fun ajouterBrut(ctx: Context, id: String, octets: ByteArray, info: JSONObject?) {
        fichier(ctx, id).writeText(Coffre.chiffrer(Base64.encodeToString(octets, Base64.NO_WRAP)))
        val l = liste(ctx).toMutableList()
        val place = l.indexOfFirst { it.id == id }
        l.removeAll { it.id == id }
        val nouvelle = Identite(id, info?.optString("nom").orEmpty().ifEmpty { "Certificat" }, info?.optString("email").orEmpty(),
            info?.optString("organisation").orEmpty(), info?.optString("emetteur").orEmpty(),
            info?.optString("fin").orEmpty().take(10), info?.optString("empreinte").orEmpty(), info?.optBoolean("autosigne") ?: false)
        if (place >= 0) l.add(place, nouvelle) else l += nouvelle
        ecrireListe(ctx, l)
        oublierRetrait(ctx, id)
    }

    fun octets(ctx: Context, id: String): ByteArray? {
        val f = fichier(ctx, id).takeIf { it.exists() } ?: return null
        return Coffre.dechiffrer(f.readText())?.let { Base64.decode(it, Base64.NO_WRAP) }
    }

    /** Retiree de ce telephone : la synchronisation ne la remet pas (tant qu'on ne la reprend pas soi-meme). */
    fun retirer(ctx: Context, id: String) {
        fichier(ctx, id).delete()
        ecrireListe(ctx, liste(ctx).filter { it.id != id })
        val p = ctx.getSharedPreferences("identites", Context.MODE_PRIVATE)
        p.edit().putStringSet("retirees", (p.getStringSet("retirees", emptySet()) ?: emptySet()) + id).apply()
    }
    fun retirees(ctx: Context): Set<String> =
        ctx.getSharedPreferences("identites", Context.MODE_PRIVATE).getStringSet("retirees", emptySet()) ?: emptySet()
    private fun oublierRetrait(ctx: Context, id: String) {
        val p = ctx.getSharedPreferences("identites", Context.MODE_PRIVATE)
        val r = retirees(ctx); if (id in r) p.edit().putStringSet("retirees", r - id).apply()
    }

    /** Change la place d'une identite dans la liste (sens -1 : monter, +1 : descendre). */
    fun deplacer(ctx: Context, id: String, sens: Int) {
        val l = liste(ctx).toMutableList()
        val i = l.indexOfFirst { it.id == id }; val j = i + sens
        if (i < 0 || j !in l.indices) return
        java.util.Collections.swap(l, i, j)
        ecrireListe(ctx, l)
    }

    /** Cree un certificat personnel (auto-signe, RSA 3072, SHA-256) comme PhilPDF Windows, l'ajoute et le depose
     *  dans PhilPDF/identites du compte synchronise : vos postes Windows le reprennent. */
    suspend fun creer(ctx: Context, nom: String, mdp: String, organisation: String, service: String, email: String,
                      pays: String, annees: Int): Identite = withContext(Dispatchers.Default) {
        val gen = java.security.KeyPairGenerator.getInstance("RSA").apply { initialize(3072) }
        val kp = gen.generateKeyPair()
        val b = org.bouncycastle.asn1.x500.X500NameBuilder(BCStyle.INSTANCE)
        b.addRDN(BCStyle.CN, nom.trim())
        if (organisation.isNotBlank()) b.addRDN(BCStyle.O, organisation.trim())
        if (service.isNotBlank()) b.addRDN(BCStyle.OU, service.trim())
        if (email.isNotBlank()) b.addRDN(BCStyle.EmailAddress, email.trim())
        if (pays.trim().length == 2) b.addRDN(BCStyle.C, pays.trim().uppercase())
        val x500 = b.build()
        val debut = java.util.Date(System.currentTimeMillis() - 60_000)
        val fin = java.util.Calendar.getInstance().apply { add(java.util.Calendar.YEAR, annees.coerceIn(1, 30)) }.time
        val cb = org.bouncycastle.cert.jcajce.JcaX509v3CertificateBuilder(x500, java.math.BigInteger(64, java.security.SecureRandom()).abs(),
            debut, fin, x500, kp.public)
        cb.addExtension(org.bouncycastle.asn1.x509.Extension.basicConstraints, true, org.bouncycastle.asn1.x509.BasicConstraints(false))
        cb.addExtension(org.bouncycastle.asn1.x509.Extension.keyUsage, true,
            org.bouncycastle.asn1.x509.KeyUsage(org.bouncycastle.asn1.x509.KeyUsage.digitalSignature or org.bouncycastle.asn1.x509.KeyUsage.nonRepudiation))
        cb.addExtension(org.bouncycastle.asn1.x509.Extension.extendedKeyUsage, false, org.bouncycastle.asn1.x509.ExtendedKeyUsage(arrayOf(
            org.bouncycastle.asn1.x509.KeyPurposeId.id_kp_emailProtection,
            org.bouncycastle.asn1.x509.KeyPurposeId.getInstance(ASN1ObjectIdentifier("1.2.840.113583.1.1.5")),    // Adobe : signature de PDF
            org.bouncycastle.asn1.x509.KeyPurposeId.getInstance(ASN1ObjectIdentifier("1.3.6.1.4.1.311.10.3.12")))))  // signature de documents
        if (email.isNotBlank()) cb.addExtension(org.bouncycastle.asn1.x509.Extension.subjectAlternativeName, false,
            org.bouncycastle.asn1.x509.GeneralNames(org.bouncycastle.asn1.x509.GeneralName(org.bouncycastle.asn1.x509.GeneralName.rfc822Name, email.trim())))
        val signeur = JcaContentSignerBuilder("SHA256withRSA").setProvider(BC).build(kp.private)
        val cert = org.bouncycastle.cert.jcajce.JcaX509CertificateConverter().setProvider(BC).getCertificate(cb.build(signeur))
        val ks = KeyStore.getInstance("PKCS12", BC)
        ks.load(null, null)
        ks.setKeyEntry(nom.trim().ifEmpty { "PhilPDF" }, kp.private, mdp.toCharArray(), arrayOf(cert))
        val o = java.io.ByteArrayOutputStream().also { ks.store(it, mdp.toCharArray()) }.toByteArray()
        val e = ajouter(ctx, o, mdp)
        Journal.ecrire("certificat", "certificat créé sur ce téléphone : ${e.nom} (jusqu'au ${e.fin})")
        try { publier(ctx, e, o) } catch (x: Exception) { Journal.ecrire("certificat", "dépôt dans PhilPDF/identites impossible : $x") }
        e
    }

    /** Depose le .pfx (protege par son mot de passe) et sa fiche dans PhilPDF/identites : vos postes le reprennent. */
    suspend fun publier(ctx: Context, e: Identite, octets: ByteArray) {
        val n = Nuage.synchro(ctx) ?: return
        val fiche = JSONObject().put("id", e.id).put("nom", e.nom).put("email", e.email).put("organisation", e.organisation)
            .put("emetteur", e.emetteur).put("fin", e.fin).put("empreinte", e.empreinte).put("autosigne", e.autosigne).put("origine", "android")
        n.deposer(ctx, "identites", "${e.id}.pfx", octets)
        n.deposer(ctx, "identites", "${e.id}.json", fiche.toString(1).toByteArray())
        Journal.ecrire("certificat", "${e.nom} déposé dans PhilPDF/identites (vos postes le reprendront)")
    }

    // ------------------------------------------------------------ certificats approuves (comme Acrobat)
    fun approuvesDer(ctx: Context): List<ByteArray> = try {
        val a = JSONArray(approuves(ctx).readText())
        (0 until a.length()).mapNotNull { try { Base64.decode(a.getString(it), Base64.NO_WRAP) } catch (_: Exception) { null } }
    } catch (_: Exception) { emptyList() }

    fun ajouterApprouve(ctx: Context, der: ByteArray) {
        val l = approuvesDer(ctx)
        if (l.any { it.contentEquals(der) }) return
        val a = JSONArray(); (l + listOf(der)).forEach { a.put(Base64.encodeToString(it, Base64.NO_WRAP)) }
        approuves(ctx).writeText(a.toString())
    }

    // ------------------------------------------------------------ depuis PhilPDF Windows
    /** Indice de la phrase secrete (s'il a ete note sous Windows). */
    suspend fun indice(ctx: Context): String? = try {
        Nuage.synchro(ctx)?.lire(ctx, "indice_phrase.json")?.let { JSONObject(String(it)).optString("indice") }?.ifEmpty { null }
    } catch (_: Exception) { null }

    /** Identites de vos postes (reglages communs de PhilPDF Windows), meme celles qui ne sont pas encore ici. */
    suspend fun distantes(ctx: Context): List<JSONObject> = try {
        val n = Nuage.synchro(ctx)
        val c = n?.lire(ctx, "preferences.json")?.let { JSONObject(String(it)).optJSONObject("communs") }
        val a = c?.optJSONArray("identites")
        val supprimees = c?.optJSONArray("identites_supprimees")?.let { x -> (0 until x.length()).map { x.optString(it) }.toSet() } ?: emptySet()
        (0 until (a?.length() ?: 0)).mapNotNull { a!!.optJSONObject(it) }.filter { it.optString("id") !in supprimees && !it.optBoolean("orpheline") }
    } catch (_: Exception) { emptyList() }

    /** Retire de ce telephone les identites reprises de vos postes et jamais ouvertes (sans empreinte) que vos postes
     *  ne listent plus (retirees, ou doublon d'une autre) : on ne pourrait pas signer avec. distantes vide : rien. */
    fun nettoyer(ctx: Context, distantes: List<JSONObject>): Boolean {
        if (distantes.isEmpty()) return false
        val connus = HashSet<String>()
        distantes.forEach { e -> connus += e.optString("id"); e.optJSONArray("alias")?.let { a -> for (i in 0 until a.length()) connus += a.optString(i) } }
        val l = liste(ctx)
        val garder = l.filter { it.empreinte.isNotEmpty() || (it.id in connus && it.nom != "Certificat") }
        if (garder.size == l.size) return false
        (l - garder.toSet()).forEach { fichier(ctx, it.id).delete(); Journal.ecrire("certificat", "identité inutilisable retirée (${it.nom}, ${it.id})") }
        ecrireListe(ctx, garder)
        return true
    }

    /** Phrase secrete retenue sur ce telephone (chiffree par sa clef) : les certificats suivent tout seuls. */
    fun phraseRetenue(ctx: Context): String? =
        ctx.getSharedPreferences("identites", Context.MODE_PRIVATE).getString("phrase", null)?.let { Coffre.dechiffrer(it) }
    fun retenirPhrase(ctx: Context, phrase: String?) = ctx.getSharedPreferences("identites", Context.MODE_PRIVATE).edit()
        .apply { if (phrase == null) remove("phrase") else putString("phrase", Coffre.chiffrer(phrase)) }.apply()

    /** Synchronisation : avec la phrase retenue, les certificats ajoutes sur vos postes arrivent ici sans rien demander. */
    suspend fun synchroAuto(ctx: Context): Int {
        val ici = liste(ctx).map { it.id }.toSet()
        val r = retirees(ctx)
        val manquantes = distantes(ctx).filter { it.optString("id") !in ici && it.optString("id") !in r }
        if (manquantes.isEmpty()) return 0
        // 1. les .pfx que vos postes deposent dans PhilPDF/identites (proteges par leur propre mot de passe)
        var k = 0
        val n = Nuage.synchro(ctx)
        for (d in manquantes) {
            val id = d.optString("id").filter { it.isLetterOrDigit() }
            if (id.isEmpty()) continue
            val o = try { n?.lire(ctx, "identites/$id.pfx") } catch (_: Exception) { null } ?: continue
            ajouterBrut(ctx, id, o, d); k++
        }
        if (k > 0) Journal.ecrire("certificat", "$k identité(s) reprise(s) du dossier PhilPDF de vos postes")
        // 2. sinon, avec la phrase retenue : le fichier chiffre des mots de passe partages
        val phrase = phraseRetenue(ctx)
        if (phrase != null && liste(ctx).size < ici.size + manquantes.size)
            k += try { recupererWindows(ctx, phrase) } catch (e: Exception) { Journal.ecrire("certificat", "synchronisation : $e"); 0 }
        return k
    }

    /** Recupere les identites (.pfx) et certificats approuves de vos postes. Renvoie le nombre d'identites. */
    suspend fun recupererWindows(ctx: Context, phrase: String): Int = withContext(Dispatchers.IO) {
        val n = Nuage.synchro(ctx) ?: throw ErreurCertificat(Textes.t(R.string.err_aucune_synchro))
        val chiffre = n.lire(ctx, "secrets.philpdf")
            ?: throw ErreurCertificat(Textes.t(R.string.err_cert_partage))
        val doc = Document.openDocument(chiffre, "application/pdf") as PDFDocument
        val json = try {
            // la phrase telle que tapee, sans espace autour, et sous ses deux formes Unicode (accents)
            val essais = listOf(phrase, phrase.trim(), java.text.Normalizer.normalize(phrase.trim(), java.text.Normalizer.Form.NFC),
                java.text.Normalizer.normalize(phrase.trim(), java.text.Normalizer.Form.NFD)).distinct()
            if (doc.needsPassword() && essais.none { doc.authenticatePassword(it) }) {
                Journal.ecrire("certificat", "secrets.philpdf : ${chiffre.size} octets, phrase refusée (${phrase.length} caractères)")
                throw ErreurCertificat(Textes.t(R.string.err_cert_phrase))
            }
            fichierJoint(doc, "preferences.json") ?: throw ErreurCertificat(Textes.t(R.string.err_cert_fichier))
        } finally { doc.destroy() }
        val secrets = JSONObject(String(json, Charsets.UTF_8)).optJSONObject("secrets") ?: JSONObject()
        // noms, dates et certificats approuves : reglages communs de vos postes
        val communs = try { n.lire(ctx, "preferences.json")?.let { JSONObject(String(it)).optJSONObject("communs") } } catch (_: Exception) { null }
        val infos = HashMap<String, JSONObject>()
        communs?.optJSONArray("identites")?.let { a -> for (i in 0 until a.length()) a.optJSONObject(i)?.let { infos[it.optString("id")] = it } }
        var k = 0
        // seulement les identites que vos postes listent (ni retirees, ni orphelines) ; un ancien numero (alias) d'une
        // identite deja reprise n'est pas repris une seconde fois : sinon des « Certificat » sans nom, inutilisables
        val supprimees = communs?.optJSONArray("identites_supprimees")?.let { x -> (0 until x.length()).map { x.optString(it) }.toSet() } ?: emptySet()
        val alias = HashMap<String, String>()
        infos.values.forEach { e -> e.optJSONArray("alias")?.let { a -> for (i in 0 until a.length()) alias[a.optString(i)] = e.optString("id") } }
        val faits = HashSet<String>()
        for (cle in secrets.keys()) {
            if (!cle.startsWith("identite:")) continue
            val brut = cle.removePrefix("identite:").filter { it.isLetterOrDigit() }
            val id = alias[brut] ?: brut
            if (id.isEmpty() || id in supprimees || id in faits) continue
            val info = infos[id]
            if (info == null || info.optBoolean("orpheline") || info.optString("nom").isEmpty()) continue
            faits += id
            ajouterBrut(ctx, id, Base64.decode(secrets.getString(cle), Base64.DEFAULT), infos[id])
            k++
        }
        communs?.optJSONArray("certificats_approuves")?.let { a ->
            for (i in 0 until a.length()) a.optJSONObject(i)?.optString("der")?.takeIf { it.isNotEmpty() }?.let {
                try { ajouterApprouve(ctx, Base64.decode(it, Base64.DEFAULT)) } catch (_: Exception) {}
            }
        }
        Journal.ecrire("certificat", "$k identité(s) récupérée(s) de vos postes")
        k
    }

    /** Fichier joint (EmbeddedFiles) d'un PDF, par son nom. */
    private fun fichierJoint(doc: PDFDocument, nom: String): ByteArray? {
        fun chercher(noeud: PDFObject?): ByteArray? {
            if (noeud == null || noeud.isNull) return null
            val noms = noeud.get("Names")
            if (noms.isArray) {
                var i = 0
                while (i + 1 < noms.size()) {
                    val fs = noms.get(i + 1).resolve()
                    val n = try { noms.get(i).asString() } catch (_: Exception) { "" }
                    if (n == nom || fs.get("F").let { !it.isNull && it.asString() == nom } || fs.get("UF").let { !it.isNull && it.asString() == nom }) {
                        val ef = fs.get("EF")
                        val s = ef.get("F").takeIf { !it.isNull } ?: ef.get("UF")
                        if (!s.isNull) return s.readStream()
                    }
                    i += 2
                }
            }
            val kids = noeud.get("Kids")
            if (kids.isArray) for (j in 0 until kids.size()) chercher(kids.get(j).resolve())?.let { return it }
            return null
        }
        return chercher(doc.getTrailer().get("Root").get("Names").get("EmbeddedFiles").resolve())
    }
}

/** Signe avec la clef du certificat (CMS detache, SHA-256), horodatage gratuit si Internet (comme sous Windows). */
/** Lit tout un flux MuPDF : sa fin est signalee par 0 (et non -1), d'ou une boucle sans fin avec readBytes(). */
internal fun lireFlux(stm: FitzInputStream): ByteArray {
    val out = java.io.ByteArrayOutputStream()
    val buf = ByteArray(65536)
    while (true) { val n = stm.read(buf, 0, buf.size); if (n <= 0) break; out.write(buf, 0, n) }
    return out.toByteArray()
}

class Signataire(private val clef: PrivateKey, private val chaine: List<X509Certificate>) : PKCS7Signer() {
    var horodatee = false
        private set

    override fun name(): PKCS7DistinguishedName {
        val c = chaine[0]
        val d = PKCS7DistinguishedName()
        val h = JcaX509CertificateHolder(c).subject
        fun v(oid: ASN1ObjectIdentifier) = h.getRDNs(oid).firstOrNull()?.first?.value?.toString()
        d.cn = v(BCStyle.CN); d.o = v(BCStyle.O); d.ou = v(BCStyle.OU); d.email = v(BCStyle.EmailAddress); d.c = v(BCStyle.C)
        return d
    }

    override fun maxDigest(): Int = 12000 + chaine.sumOf { it.encoded.size } * 2

    override fun sign(stm: FitzInputStream): ByteArray {
        val donnees = lireFlux(stm)
        val algo = when (clef.algorithm) { "EC", "ECDSA" -> "SHA256withECDSA"; else -> "SHA256withRSA" }
        val bc = BouncyCastleProvider()
        val gen = CMSSignedDataGenerator()
        val signeur = JcaContentSignerBuilder(algo).setProvider(bc).build(clef)
        gen.addSignerInfoGenerator(JcaSignerInfoGeneratorBuilder(JcaDigestCalculatorProviderBuilder().setProvider(bc).build())
            .build(signeur, chaine[0]))
        gen.addCertificates(JcaCertStore(chaine))
        var cms = gen.generate(CMSProcessableByteArray(donnees), false)
        cms = try { horodater(cms) } catch (e: Exception) { Journal.ecrire("certificat", "horodatage impossible ($e)"); cms }
        return cms.encoded
    }

    /** Jeton d'horodatage (RFC 3161) ajoute a la signature : la date ne depend plus de l'horloge du telephone. */
    private fun horodater(cms: CMSSignedData): CMSSignedData {
        val si = cms.signerInfos.signers.first()
        val empreinte = MessageDigest.getInstance("SHA-256").digest(si.signature)
        val req = TimeStampRequestGenerator().apply { setCertReq(true) }
            .generate(org.bouncycastle.tsp.TSPAlgorithms.SHA256, empreinte, java.math.BigInteger.valueOf(System.nanoTime()))
        for (url in listOf("http://timestamp.digicert.com", "http://timestamp.sectigo.com", "https://freetsa.org/tsr")) {
            try {
                val c = URL(url).openConnection() as HttpURLConnection
                c.connectTimeout = 5000; c.readTimeout = 7000; c.doOutput = true; c.requestMethod = "POST"
                c.setRequestProperty("Content-Type", "application/timestamp-query")
                c.outputStream.use { it.write(req.encoded) }
                if (c.responseCode != 200) continue
                val rep = TimeStampResponse(c.inputStream.use { it.readBytes() })
                rep.validate(req)
                val jeton = rep.timeStampToken ?: continue
                val attr = Attribute(PKCSObjectIdentifiers.id_aa_signatureTimeStampToken, DERSet(jeton.toCMSSignedData().toASN1Structure()))
                val v = si.unsignedAttributes?.toASN1EncodableVector() ?: org.bouncycastle.asn1.ASN1EncodableVector()
                v.add(attr)
                val nouveau = SignerInformation.replaceUnsignedAttributes(si, AttributeTable(v))
                horodatee = true
                Journal.ecrire("certificat", "signature horodatée ($url)")
                return CMSSignedData.replaceSigners(cms, SignerInformationStore(nouveau))
            } catch (_: Exception) { }
        }
        return cms
    }
}

/** Verifie les signatures du PDF : empreinte (le document n'a pas change) et certificat (approuve ou non). */
class Verifieur(private val approuves: List<ByteArray>) : PKCS7Verifier() {
    private val bc = BouncyCastleProvider()
    /** Nom du signataire, lu dans le certificat lors de checkCertificate. */
    var signataire: String? = null

    override fun checkDigest(stream: FitzInputStream, signature: ByteArray): Int = try {
        val cms = CMSSignedData(CMSProcessableByteArray(lireFlux(stream)), signature)
        val si = cms.signerInfos.signers.first()
        @Suppress("UNCHECKED_CAST")
        val cert = (cms.certificates.getMatches(si.sid as org.bouncycastle.util.Selector<X509CertificateHolder>) as Collection<X509CertificateHolder>).first()
        if (si.verify(JcaSimpleSignerInfoVerifierBuilder().setProvider(bc).build(cert))) PKCS7Verifier.PKCS7VerifierOK else PKCS7Verifier.PKCS7VerifierDigestFailure
    } catch (_: Exception) { PKCS7Verifier.PKCS7VerifierDigestFailure }

    override fun checkCertificate(signature: ByteArray): Int = try {
        val cms = CMSSignedData(signature)
        val si = cms.signerInfos.signers.first()
        @Suppress("UNCHECKED_CAST")
        val cert = (cms.certificates.getMatches(si.sid as org.bouncycastle.util.Selector<X509CertificateHolder>) as Collection<X509CertificateHolder>).first()
        signataire = try {
            fun v(oid: ASN1ObjectIdentifier) = cert.subject.getRDNs(oid).firstOrNull()?.first?.value?.toString()?.takeIf { it.isNotBlank() }
            v(BCStyle.CN) ?: v(BCStyle.EmailAddress) ?: v(BCStyle.O)
        } catch (_: Exception) { null }
        when {
            approuves.any { it.contentEquals(cert.encoded) } -> PKCS7Verifier.PKCS7VerifierOK
            cert.subject == cert.issuer -> PKCS7Verifier.PKCS7VerifierSelfSigned
            else -> {
                // certificat d'une autorite reconnue par Android (carte, token professionnel...)
                val x = CertificateFactory.getInstance("X.509").generateCertificate(ByteArrayInputStream(cert.encoded)) as X509Certificate
                val tm = javax.net.ssl.TrustManagerFactory.getInstance(javax.net.ssl.TrustManagerFactory.getDefaultAlgorithm())
                    .apply { init(null as KeyStore?) }.trustManagers.filterIsInstance<javax.net.ssl.X509TrustManager>().first()
                @Suppress("UNCHECKED_CAST")
                val tous = (cms.certificates.getMatches(null) as Collection<X509CertificateHolder>).map {
                    CertificateFactory.getInstance("X.509").generateCertificate(ByteArrayInputStream(it.encoded)) as X509Certificate }
                try { tm.checkClientTrusted(arrayOf(x) + tous.filter { it != x }.toTypedArray(), "RSA"); PKCS7Verifier.PKCS7VerifierOK }
                catch (_: Exception) { PKCS7Verifier.PKCS7VerifierNotTrusted }
            }
        }
    } catch (_: Exception) { PKCS7Verifier.PKCS7VerifierUnknown }
}
