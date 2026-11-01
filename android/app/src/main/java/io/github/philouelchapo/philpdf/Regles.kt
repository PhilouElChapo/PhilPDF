package io.github.philouelchapo.philpdf

import com.artifex.mupdf.fitz.PDFAnnotation
import com.artifex.mupdf.fitz.PDFDocument
import com.artifex.mupdf.fitz.PDFObject
import com.artifex.mupdf.fitz.PDFPage
import com.artifex.mupdf.fitz.PDFWidget
import org.json.JSONArray
import org.json.JSONObject
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Date
import java.util.Locale

/**
 * Regles des champs de formulaire, exactement comme PhilPDF Windows (moteur/champs.py) : format (nombre, montant,
 * pourcentage, date, heure, masque), valeur automatique, calcul, plage, listes dependantes, afficher / masquer,
 * majuscules, controles francais (e-mail, NIR, IBAN, SIRET, RPPS), aide.
 *
 * Elles sont gardees dans le champ (cle /PhilPDF_Regles, en JSON, meme format que Windows) et traduites en
 * JavaScript standard d'Acrobat (AFNumber_Format, AFDate_FormatEx, AFSimple_Calculate...) : le formulaire marche pareil
 * dans Acrobat, Acrobat Reader, PhilPDF Windows et PhilPDF Android.
 */
object Regles {
    const val CLE = "PhilPDF_Regles"
    private const val DEBUT = "/* PhilPDF */"
    private const val FIN = "/* fin PhilPDF */"
    val SEPARATEURS = mapOf(0 to Triple("1,234.56", ",", "."), 1 to Triple("1234.56", "", "."), 2 to Triple("1.234,56", ".", ","),
        3 to Triple("1234,56", "", ","), 4 to Triple("1'234.56", "'", "."))
    val DATES = listOf("dd/mm/yyyy", "dd/mm/yy", "d/m/yyyy", "dd.mm.yyyy", "yyyy-mm-dd", "dd mmmm yyyy", "mm/dd/yyyy", "dd/mm/yyyy HH:MM")
    val HEURES = listOf("HH:MM", "HH:MM:ss", "h:MM tt")
    val MASQUES = linkedMapOf("telephone" to "99 99 99 99 99", "code_postal" to "99999", "siret" to "999 999 999 99999",
        "nir" to "9 99 99 XX 999 999 99")
    val CALCULS = linkedMapOf("somme" to "SUM", "produit" to "PRD", "moyenne" to "AVG", "min" to "MIN", "max" to "MAX")
    val CONTROLES = listOf("email", "nir", "iban", "siret", "rpps")
    private val MOIS = listOf("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
        "novembre", "décembre")

    fun vide(): JSONObject = JSONObject().put("format", JSONObject().put("genre", "aucun")).put("auto", JSONObject.NULL)
        .put("calcul", JSONObject.NULL).put("plage", JSONObject.NULL).put("depend", JSONObject.NULL).put("affiche", JSONObject.NULL)
        .put("majuscules", false).put("controle", JSONObject.NULL).put("aide", JSONObject.NULL).put("action", JSONObject.NULL)
        .put("js_seul", JSONArray())

    private fun JSONObject.obj(k: String): JSONObject? = optJSONObject(k)
    private fun JSONObject.txt(k: String): String? = if (isNull(k)) null else optString(k).ifEmpty { null }
    fun format(r: JSONObject?): JSONObject = r?.obj("format") ?: JSONObject().put("genre", "aucun")

    // ------------------------------------------------------------ type devine d'apres le libelle
    private val TYPES: List<Triple<Regex, String, JSONObject?>> = listOf(
        Triple(Regex("signature|sign[ée] par|visa\\b"), "signature", null),
        Triple(Regex("\\bdate\\b|n[ée]\\(?e?\\)?\\s*le|\\bfait le\\b|\\ble\\s*:?$|d[ée]livr[ée] le|\\bdu\\b\\s*:?$|\\bau\\b\\s*:?$"), "texte",
            JSONObject().put("format", JSONObject().put("genre", "date").put("date", "dd/mm/yyyy"))),
        Triple(Regex("montant|prix|total|tarif|somme|co[uû]t|\\b(ht|ttc)\\b|€|euros?"), "texte",
            JSONObject().put("format", JSONObject().put("genre", "nombre").put("decimales", 2).put("separateur", 2).put("negatif", 0)
                .put("symbole", "€").put("symbole_avant", false))),
        Triple(Regex("quantit[ée]|\\bqt[ée]\\b|nombre de|\\bnb\\b"), "texte",
            JSONObject().put("format", JSONObject().put("genre", "nombre").put("decimales", 0).put("separateur", 2).put("negatif", 0)
                .put("symbole", "").put("symbole_avant", false))),
        Triple(Regex("t[ée]l[ée]?phone|\\bt[ée]l\\b|portable|mobile|\\bfax\\b|\\bgsm\\b"), "texte",
            JSONObject().put("format", JSONObject().put("genre", "masque").put("masque", "99 99 99 99 99"))),
        Triple(Regex("code\\s*postal|\\bc\\.?p\\.?\\b"), "texte", JSONObject().put("format", JSONObject().put("genre", "masque").put("masque", "99999"))),
        Triple(Regex("e-?mail|courriel|m[ée]l\\b|adresse [ée]lectronique"), "texte", JSONObject().put("controle", "email")),
        Triple(Regex("s[ée]curit[ée] sociale|\\bn\\.?i\\.?r\\.?\\b|n°\\s*ss\\b|immatriculation"), "texte", JSONObject().put("controle", "nir")),
        Triple(Regex("\\biban\\b"), "texte", JSONObject().put("controle", "iban").put("majuscules", true)),
        Triple(Regex("\\bsiret\\b"), "texte", JSONObject().put("controle", "siret")),
        Triple(Regex("\\brpps\\b"), "texte", JSONObject().put("controle", "rpps")),
        Triple(Regex("^nom\\b|nom de famille|nom d'usage|\\bville\\b|commune"), "texte", JSONObject().put("majuscules", true)),
    )

    /** (genre, regles) proposes pour un champ d'apres son libelle (« Date de naissance » -> date...) ; null sinon. */
    fun deviner(libelle: String): Pair<String, JSONObject?>? {
        val t = libelle.trim().lowercase(Locale.FRANCE)
        for ((m, g, r) in TYPES) if (m.containsMatchIn(t)) return g to r?.let { JSONObject(it.toString()) }
        return null
    }

    // ------------------------------------------------------------ controles francais
    private fun luhn(ch: String): Boolean {
        var t = 0
        ch.reversed().forEachIndexed { i, c -> var d = c.digitToInt(); if (i % 2 == 1) { d *= 2; if (d > 9) d -= 9 }; t += d }
        return t % 10 == 0
    }

    fun controleOk(genre: String?, texte: String): Boolean {
        val t = texte.trim()
        if (t.isEmpty() || genre == null) return true
        val c = t.replace(Regex("[\\s.\\-]"), "").uppercase()
        return when (genre) {
            "email" -> Regex("[^@\\s]+@[^@\\s]+\\.[^@\\s]{2,}").matches(t)
            "nir" -> {
                if (!Regex("[12378]\\d{4}(\\d{2}|2A|2B)\\d{6}\\d{2}").matches(c)) false
                else { val corps = c.take(13).replace("2A", "19").replace("2B", "18"); 97 - (corps.toBigInteger() % 97.toBigInteger()).toInt() == c.drop(13).toInt() }
            }
            "iban" -> {
                if (!Regex("[A-Z]{2}\\d{2}[A-Z0-9]{11,30}").matches(c)) false
                else { val r = c.drop(4) + c.take(4); (r.map { it.digitToInt(36).toString() }.joinToString("").toBigInteger() % 97.toBigInteger()).toInt() == 1 }
            }
            "siret" -> Regex("\\d{14}").matches(c) && (luhn(c) || (c.startsWith("356000000") && c.sumOf { it.digitToInt() } % 5 == 0))
            "rpps" -> Regex("\\d{11}").matches(c) && luhn(c)
            else -> true
        }
    }

    private val JS_CONTROLES = mapOf(
        "email" to "function(v){return /^[^@\\s]+@[^@\\s]+\\.[^@\\s]{2,}\$/.test(v);}",
        "nir" to ("function(v){v=v.replace(/[\\s.\\-]/g,\"\").toUpperCase();" +
            "if(!/^[12378]\\d{4}(\\d{2}|2A|2B)\\d{8}\$/.test(v))return false;" +
            "var c=v.substr(0,13).replace(\"2A\",\"19\").replace(\"2B\",\"18\");var r=0;" +
            "for(var i=0;i<c.length;i++)r=(r*10+parseInt(c.charAt(i),10))%97;return 97-r==parseInt(v.substr(13),10);}"),
        "iban" to ("function(v){v=v.replace(/\\s/g,\"\").toUpperCase();if(!/^[A-Z]{2}\\d{2}[A-Z0-9]{11,30}\$/.test(v))return false;" +
            "v=v.substr(4)+v.substr(0,4);var r=0;for(var i=0;i<v.length;i++){var n=parseInt(v.charAt(i),36).toString();" +
            "for(var j=0;j<n.length;j++)r=(r*10+parseInt(n.charAt(j),10))%97;}return r==1;}"),
        "siret" to ("function(v){v=v.replace(/[\\s.\\-]/g,\"\");if(!/^\\d{14}\$/.test(v))return false;var s=0;" +
            "for(var i=0;i<14;i++){var d=parseInt(v.charAt(13-i),10);if(i%2){d*=2;if(d>9)d-=9;}s+=d;}" +
            "if(s%10==0)return true;if(v.substr(0,9)==\"356000000\"){s=0;for(i=0;i<14;i++)s+=parseInt(v.charAt(i),10);return s%5==0;}return false;}"),
        "rpps" to ("function(v){v=v.replace(/\\s/g,\"\");if(!/^\\d{11}\$/.test(v))return false;var s=0;" +
            "for(var i=0;i<11;i++){var d=parseInt(v.charAt(10-i),10);if(i%2){d*=2;if(d>9)d-=9;}s+=d;}return s%10==0;}"))
    val MESSAGES_CONTROLE = mapOf("email" to "Adresse e-mail incorrecte.", "nir" to "Numéro de Sécurité sociale incorrect (vérifiez la clef).",
        "iban" to "IBAN incorrect.", "siret" to "Numéro SIRET incorrect.", "rpps" to "Numéro RPPS incorrect.")

    private fun jsControle(genre: String): String {
        val f = JS_CONTROLES[genre] ?: return ""
        return "if (event.value != \"\" && !($f)(event.value)) { app.alert(${jsstr(MESSAGES_CONTROLE[genre] ?: "")}); event.rc = false; }"
    }

    // ------------------------------------------------------------ lecture / ecriture dans le PDF
    /** Le champ (porteur du nom /T) d'un widget : lui-meme, ou son parent. */
    fun champDe(w: PDFObject): PDFObject {
        val o = w.resolve()
        if (o.get("T").isNull) { val p = o.get("Parent"); if (!p.isNull) return p.resolve() }
        return o
    }

    private fun js(x: PDFObject, cle: String): String {
        val a = if (cle == "A") x.get("A") else x.get("AA").let { if (it.isNull) it else it.get(cle) }
        if (a.isNull) return ""
        val j = a.resolve().get("JS")
        if (j.isNull) return ""
        val r = j.resolve()
        return if (r.isStream) String(r.readStream(), Charsets.ISO_8859_1) else try { r.asString() } catch (_: Exception) { "" }
    }

    private fun scripts(champ: PDFObject, widget: PDFObject): Map<String, String> {
        val out = HashMap<String, String>()
        for (x in listOf(champ, widget)) for (k in listOf("K", "F", "V", "C", "Fo", "Bl", "U", "A")) {
            val s = js(x, k)
            if (s.isNotEmpty() && out[k]?.contains(s) != true) out[k] = ((out[k] ?: "") + "\n" + s).trim()
        }
        return out
    }

    /** Regles d'un champ : celles de PhilPDF, sinon reconnues dans le JavaScript d'Acrobat. */
    fun lire(widget: PDFObject): JSONObject {
        val champ = champDe(widget)
        val v = champ.get(CLE)
        if (!v.isNull) try {
            val r = vide()
            val j = JSONObject(v.asString())
            for (k in j.keys()) r.put(k, j.get(k))
            r.put("_philpdf", true)
            val c = r.obj("calcul")
            if (c != null && ((c.optString("genre") in CALCULS && (c.optJSONArray("champs")?.length() ?: 0) == 0) ||
                    (c.optString("genre") == "formule" && c.optString("formule").isBlank()))) r.put("calcul", JSONObject.NULL)
            return r
        } catch (_: Exception) {}
        return depuisJs(scripts(champ, widget.resolve()))
    }

    private fun args(s: String): List<String> = s.split(Regex(",(?=(?:[^\"]*\"[^\"]*\")*[^\"]*$)")).map { it.trim().trim('"', '\'') }

    /** Reconnait les fonctions standard d'Acrobat dans les scripts d'un champ. */
    fun depuisJs(sc: Map<String, String>): JSONObject {
        val r = vide()
        val f = (sc["F"] ?: "") + "\n" + (sc["K"] ?: "")
        Regex("AFNumber_Format\\s*\\(([^)]*)\\)").find(f)?.let { m ->
            val a = args(m.groupValues[1]) + List(6) { "" }
            try {
                r.put("format", JSONObject().put("genre", "nombre").put("decimales", (a[0].ifEmpty { "0" }).toDouble().toInt())
                    .put("separateur", (a[1].ifEmpty { "0" }).toDouble().toInt()).put("negatif", (a[2].ifEmpty { "0" }).toDouble().toInt())
                    .put("symbole", a[4]).put("symbole_avant", a[5].lowercase() == "true"))
            } catch (_: Exception) {}
        }
        Regex("AFPercent_Format\\s*\\(([^)]*)\\)").find(f)?.let { m ->
            val a = args(m.groupValues[1]) + listOf("0", "0")
            r.put("format", JSONObject().put("genre", "pourcentage").put("decimales", a[0].toDoubleOrNull()?.toInt() ?: 0)
                .put("separateur", a[1].toDoubleOrNull()?.toInt() ?: 0))
        }
        Regex("AFDate_(?:Format|Keystroke)Ex\\s*\\(\\s*[\"']([^\"']+)").find(f)?.let { r.put("format", JSONObject().put("genre", "date").put("date", it.groupValues[1])) }
        Regex("AFTime_(?:Format|Keystroke)Ex\\s*\\(\\s*[\"']([^\"']+)").find(f)?.let { r.put("format", JSONObject().put("genre", "heure").put("heure", it.groupValues[1])) }
        Regex("AFSpecial_KeystrokeEx\\s*\\(\\s*[\"']([^\"']+)").find(f)?.let { r.put("format", JSONObject().put("genre", "masque").put("masque", it.groupValues[1])) }
        if (Regex("event\\.change\\s*=\\s*event\\.change\\.toUpperCase").containsMatchIn(sc["K"] ?: "")) r.put("majuscules", "tout")
        val c = sc["C"] ?: ""
        val mc = Regex("AFSimple_Calculate\\s*\\(\\s*[\"'](\\w+)[\"']\\s*,\\s*new\\s+Array\\s*\\(([^)]*)\\)").find(c)
        if (mc != null) {
            val inv = CALCULS.entries.associate { it.value to it.key }
            r.put("calcul", JSONObject().put("genre", inv[mc.groupValues[1].uppercase()] ?: "somme")
                .put("champs", JSONArray(args(mc.groupValues[2]).filter { it.isNotEmpty() })))
        } else Regex("/\\*\\*\\s*BVCALC\\s*(.*?)\\s*EVCALC\\s*\\*\\*/", RegexOption.DOT_MATCHES_ALL).find(c)?.let {
            r.put("calcul", JSONObject().put("genre", "formule").put("formule", sfnVersCrochets(it.groupValues[1])))
        }
        Regex("AFRange_Validate\\s*\\(([^)]*)\\)").find(sc["V"] ?: "")?.let { m ->
            val a = args(m.groupValues[1]) + List(4) { "" }
            r.put("plage", JSONObject().put("min", if (a[0].lowercase() == "true") a[1].toDoubleOrNull() ?: JSONObject.NULL else JSONObject.NULL)
                .put("max", if (a[2].lowercase() == "true") a[3].toDoubleOrNull() ?: JSONObject.NULL else JSONObject.NULL))
        }
        return r
    }

    private fun sfnVersCrochets(sfn: String): String =
        Regex("(?:\\\\.|[^\\s+\\-*/()])+|[+\\-*/()]").findAll(sfn).map { it.value }.joinToString(" ") { j ->
            when {
                j in listOf("+", "-", "*", "/", "(", ")") -> j
                Regex("\\d+(?:[.,]\\d+)?").matches(j) -> j
                else -> "[" + j.replace(Regex("\\\\(.)"), "$1") + "]"
            }
        }

    /** Garde les regles dans le champ (le JavaScript est refait pour tout le formulaire par genererJs). */
    fun ecrire(pdf: PDFDocument, widget: PDFObject, regles: JSONObject) {
        val champ = champDe(widget)
        val propre = JSONObject()
        for (k in regles.keys()) if (!k.startsWith("_")) propre.put(k, regles.get(k))
        if (propre.toString() == vide().toString()) champ.delete(CLE) else champ.put(CLE, pdf.newString(propre.toString()))
    }

    // ------------------------------------------------------------ JavaScript pour Acrobat
    fun jsstr(t: String) = "\"" + t.replace("\\", "\\\\").replace("\"", "\\\"") + "\""

    private fun jsFormat(fmt: JSONObject): Pair<String, String> = when (fmt.optString("genre", "aucun")) {
        "nombre" -> {
            var sym = fmt.optString("symbole", ""); val avant = fmt.optBoolean("symbole_avant")
            if (sym.isNotEmpty() && !avant && !sym.startsWith(" ")) sym = " $sym"
            if (sym.isNotEmpty() && avant && !sym.endsWith(" ")) sym = "$sym "
            val a = "${fmt.optInt("decimales", 2)}, ${fmt.optInt("separateur", 2)}, ${fmt.optInt("negatif", 0)}, 0, ${jsstr(sym)}, ${if (avant) "true" else "false"}"
            "AFNumber_Format($a);" to "AFNumber_Keystroke($a);"
        }
        "pourcentage" -> { val a = "${fmt.optInt("decimales", 0)}, ${fmt.optInt("separateur", 2)}"; "AFPercent_Format($a);" to "AFPercent_Keystroke($a);" }
        "date" -> { val d = jsstr(fmt.optString("date").ifEmpty { "dd/mm/yyyy" }); "AFDate_FormatEx($d);" to "AFDate_KeystrokeEx($d);" }
        "heure" -> { val h = jsstr(fmt.optString("heure").ifEmpty { "HH:MM" }); "AFTime_FormatEx($h);" to "AFTime_KeystrokeEx($h);" }
        "masque" -> { val m = jsstr(fmt.optString("masque")); "AFSpecial_KeystrokeEx($m);" to "AFSpecial_KeystrokeEx($m);" }
        else -> "" to ""
    }

    /** « [Quantite] * [Prix] + 2 » -> jetons (champ, op, nombre). */
    fun jetons(formule: String): List<Pair<String, String>> {
        val out = ArrayList<Pair<String, String>>(); var i = 0
        while (i < formule.length) {
            val c = formule[i]
            when {
                c.isWhitespace() -> i++
                c == '[' -> { val j = formule.indexOf(']', i); if (j < 0) throw IllegalArgumentException("crochet"); out += "champ" to formule.substring(i + 1, j); i = j + 1 }
                c in "+-*/()" -> { out += "op" to c.toString(); i++ }
                else -> {
                    val m = Regex("\\d+(?:[.,]\\d+)?").find(formule, i)?.takeIf { it.range.first == i } ?: throw IllegalArgumentException(formule.drop(i).take(10))
                    out += "nombre" to m.value.replace(",", "."); i += m.value.length
                }
            }
        }
        return out
    }

    private fun jsCalcul(c: JSONObject?, formats: Map<String, JSONObject>, fmtSoi: JSONObject): String {
        if (c == null) return ""
        fun dfmt(nom: String) = formats[nom]?.let { if (it.optString("genre") == "date") it.optString("date").ifEmpty { null } else null } ?: "dd/mm/yyyy"
        return when (val g = c.optString("genre")) {
            "copie" -> "event.value = this.getField(${jsstr(c.optString("source"))}).value;"
            "age" -> { val s = c.optString("source")
                "var d = util.scand(${jsstr(dfmt(s))}, this.getField(${jsstr(s)}).valueAsString); " +
                    "if (d) { var n = new Date(); var a = n.getFullYear() - d.getFullYear(); " +
                    "if (n.getMonth() < d.getMonth() || (n.getMonth() == d.getMonth() && n.getDate() < d.getDate())) a--; " +
                    "event.value = a; } else event.value = \"\";" }
            "ecart_jours" -> { val a = c.optString("debut"); val b = c.optString("fin")
                "var a = util.scand(${jsstr(dfmt(a))}, this.getField(${jsstr(a)}).valueAsString); " +
                    "var b = util.scand(${jsstr(dfmt(b))}, this.getField(${jsstr(b)}).valueAsString); " +
                    "event.value = (a && b) ? Math.round((b.getTime() - a.getTime()) / 86400000) : \"\";" }
            "date_plus" -> { val s = c.optString("source")
                val soi = if (fmtSoi.optString("genre") == "date") fmtSoi.optString("date").ifEmpty { "dd/mm/yyyy" } else "dd/mm/yyyy"
                "var d = util.scand(${jsstr(dfmt(s))}, this.getField(${jsstr(s)}).valueAsString); " +
                    "if (d) { d.setDate(d.getDate() + ${c.optInt("jours", 0)}); event.value = util.printd(${jsstr(soi)}, d); } else event.value = \"\";" }
            "formule" -> {
                val j = try { jetons(c.optString("formule")) } catch (_: Exception) { emptyList() }
                val js = j.joinToString(" ") { (t, v) -> if (t == "champ") "AFMakeNumber(getField(${jsstr(v)}).value)" else v }
                val sfn = j.joinToString(" ") { (t, v) -> if (t == "champ") v.replace(Regex("([\\s+\\-*/()\\\\])"), "\\\\$1") else v }
                "/** BVCALC $sfn EVCALC **/ event.value = ${js.ifEmpty { "0" }};"
            }
            else -> {
                val champs = (0 until (c.optJSONArray("champs")?.length() ?: 0)).joinToString(", ") { jsstr(c.getJSONArray("champs").getString(it)) }
                "AFSimple_Calculate(\"${CALCULS[g] ?: "SUM"}\", new Array ($champs));"
            }
        }
    }

    private fun jsAuto(auto: String?, fmt: JSONObject): String {
        if (auto.isNullOrEmpty()) return ""
        val f = when (auto) {
            "date_clic" -> if (fmt.optString("genre") == "date") fmt.optString("date") else "dd/mm/yyyy"
            "heure_clic" -> if (fmt.optString("genre") == "heure") fmt.optString("heure") else "HH:MM"
            else -> if (fmt.optString("genre") == "date" && fmt.optString("date").contains("H")) fmt.optString("date") else "dd/mm/yyyy HH:MM"
        }
        return "if (event.target.value == \"\") event.target.value = util.printd(${jsstr(f)}, new Date());"
    }

    private fun remplacerBloc(ancien: String, bloc: String): String {
        val a = ancien.replace(Regex(Regex.escape(DEBUT) + ".*?" + Regex.escape(FIN), RegexOption.DOT_MATCHES_ALL), "").trim()
        if (bloc.isEmpty()) return a
        return (if (a.isNotEmpty()) "$a\n" else "") + "$DEBUT\n$bloc\n$FIN"
    }

    private fun poserJs(pdf: PDFDocument, x: PDFObject, cle: String, texte: String) {
        if (texte.isEmpty()) {
            if (cle == "A") x.delete("A")
            else { val aa = x.get("AA"); if (!aa.isNull) { aa.delete(cle); if (aa.size() == 0) x.delete("AA") } }
            return
        }
        val action = pdf.newDictionary()
        action.put("S", pdf.newName("JavaScript")); action.put("JS", pdf.newString(texte))
        if (cle == "A") { x.put("A", action); return }
        var aa = x.get("AA")
        if (aa.isNull) { aa = pdf.newDictionary(); x.put("AA", aa) }
        aa.put(cle, action)
    }

    /** Tous les champs du document : (page, objet du widget, nom, genre). */
    data class Ch(val page: Int, val obj: PDFObject, val nom: String, val genre: Int)

    fun tous(pdf: PDFDocument): List<Ch> {
        val out = ArrayList<Ch>()
        for (n in 0 until pdf.countPages()) {
            val p = pdf.loadPage(n) as PDFPage
            try { p.widgets?.forEach { w -> out += Ch(n, w.getObject(), w.name ?: "", w.fieldType) } } finally { p.destroy() }
        }
        return out
    }

    /** Refait tout le JavaScript PhilPDF du formulaire a partir des regles, et l'ordre de calcul (comme Windows). */
    fun genererJs(pdf: PDFDocument) {
        val champs = tous(pdf)
        val parNom = LinkedHashMap<String, MutableList<Ch>>()
        champs.forEach { parNom.getOrPut(it.nom) { ArrayList() } += it }
        val regles = parNom.mapValues { lire(it.value[0].obj) }
        val surSource = HashMap<String, MutableList<String>>()
        for ((nom, r) in regles) {
            if (!r.optBoolean("_philpdf")) continue
            val dep = r.obj("depend")
            val parent = dep?.txt("parent")
            if (dep != null && parent != null) {
                val m = dep.obj("listes") ?: JSONObject()
                surSource.getOrPut(parent) { ArrayList() } += "var m = $m; var f = this.getField(${jsstr(nom)}); " +
                    "if (f) { var l = m[event.value]; if (l) f.setItems(l); else f.clearItems(); }"
            }
        }
        for ((nom, r) in regles) {
            val a = if (r.optBoolean("_philpdf")) r.obj("affiche") else null
            val cibles = a?.optJSONArray("cibles")
            if (a == null || cibles == null || cibles.length() == 0) continue
            val cond = if (a.optString("quand") == "coche") "event.target.value != \"Off\"" else "event.value == ${jsstr(a.optString("valeur"))}"
            surSource.getOrPut("affiche:$nom") { ArrayList() } += (0 until cibles.length()).map {
                "this.getField(${jsstr(cibles.getString(it))}).display = ($cond) ? display.visible : display.hidden;" }
        }
        val formats = regles.mapValues { format(it.value) }
        val calcules = ArrayList<String>()
        for ((nom, l) in parNom) {
            val r = regles[nom]!!
            val phil = r.optBoolean("_philpdf")
            val source = nom in surSource || "affiche:$nom" in surSource
            if (!phil && !source) continue                    // formulaire d'Acrobat sans regle PhilPDF : on n'y touche pas
            val w = l[0]
            val fx = champDe(w.obj)
            val fmt = if (phil) format(r) else JSONObject().put("genre", "aucun")
            var (jf, jk) = jsFormat(fmt)
            val cal = if (phil) jsCalcul(r.obj("calcul"), formats, fmt) else ""
            val maj = if (phil) r.opt("majuscules") else null
            if (maj == true || maj == "tout") jk = ("if (!event.willCommit) event.change = event.change.toUpperCase();\n$jk").trim()
            if (r.obj("calcul") != null) calcules += nom
            val plage = if (phil) r.obj("plage") else null
            var jv = ""
            if (plage != null && (!plage.isNull("min") || !plage.isNull("max"))) {
                fun n(k: String) = if (plage.isNull(k)) 0.0 else plage.optDouble(k, 0.0)
                jv = "AFRange_Validate(${!plage.isNull("min")}, ${valeurBrute(n("min"))}, ${!plage.isNull("max")}, ${valeurBrute(n("max"))});"
            }
            if (maj == "premiere") jv = ("if (event.value) event.value = event.value.charAt(0).toUpperCase() + event.value.slice(1);\n$jv").trim()
            else if (maj == "mots") jv = ("if (event.value) event.value = event.value.toLowerCase().replace(/(^|[\\s\\-'’])(\\S)/g, " +
                "function (m, a, b) { return a + b.toUpperCase(); });\n$jv").trim()
            if (phil) r.txt("controle")?.let { jv = (jv + "\n" + jsControle(it)).trim() }
            val caseOuRadio = w.genre == PDFWidget.TYPE_CHECKBOX || w.genre == PDFWidget.TYPE_RADIOBUTTON
            jv = (listOf(jv) + (surSource[nom] ?: emptyList()) + (if (caseOuRadio) emptyList() else surSource["affiche:$nom"] ?: emptyList()))
                .filter { it.isNotEmpty() }.joinToString("\n")
            var ja = if (caseOuRadio) (surSource["affiche:$nom"] ?: emptyList()).joinToString("\n") else ""
            val seul = if (phil) (0 until (r.optJSONArray("js_seul")?.length() ?: 0)).map { r.getJSONArray("js_seul").getString(it) }.toSet() else emptySet()
            for ((cle, texte) in listOf("F" to jf, "K" to jk, "C" to cal, "V" to jv))
                poserJs(pdf, fx, cle, remplacerBloc(js(fx, cle), if (cle in seul) "" else texte))
            val aide = if (phil) r.obj("aide") else null
            var jfo = jsAuto(if (phil) r.txt("auto") else null, fmt)
            aide?.txt("entree")?.let { jfo = (jfo + "\n" + "app.alert({cMsg: ${jsstr(it)}, nIcon: 3, cTitle: \"Aide\"});").trim() }
            val jbl = aide?.txt("vide")?.let { "if (event.target.value == \"\" || event.target.value == \"Off\") app.alert({cMsg: ${jsstr(it)}, nIcon: 1});" } ?: ""
            for (ww in l) for ((cle, texte) in listOf("Fo" to jfo, "Bl" to jbl, "U" to ja))
                poserJs(pdf, ww.obj.resolve(), cle, remplacerBloc(js(ww.obj.resolve(), cle), if (cle in seul) "" else texte))
        }
        ordreCalcul(pdf, parNom, regles, calcules)
    }

    private fun ordreCalcul(pdf: PDFDocument, parNom: Map<String, List<Ch>>, regles: Map<String, JSONObject>, calcules: List<String>) {
        val af = pdf.getTrailer().get("Root").get("AcroForm")
        if (af.isNull) return
        val deps = calcules.associateWith { sources(regles[it]!!.obj("calcul")).toSet() }
        val ordre = ArrayList<String>(); val vus = HashSet<String>()
        fun visiter(n: String, pile: Set<String>) {
            if (n in vus || n in pile) return
            deps[n]?.forEach { d -> if (d in deps) visiter(d, pile + n) }
            vus += n; ordre += n
        }
        calcules.forEach { visiter(it, emptySet()) }
        if (ordre.isEmpty()) { af.delete("CO"); return }
        val co = pdf.newArray()
        ordre.forEach { n -> parNom[n]?.firstOrNull()?.let { co.push(champDe(it.obj).let { c -> if (c.isIndirect) c else it.obj }) } }
        af.put("CO", co)
    }

    fun sources(c: JSONObject?): List<String> {
        if (c == null) return emptyList()
        return when (c.optString("genre")) {
            "copie", "age", "date_plus" -> listOf(c.optString("source"))
            "ecart_jours" -> listOf(c.optString("debut"), c.optString("fin"))
            "formule" -> try { jetons(c.optString("formule")).filter { it.first == "champ" }.map { it.second } } catch (_: Exception) { emptyList() }
            else -> (0 until (c.optJSONArray("champs")?.length() ?: 0)).map { c.getJSONArray("champs").getString(it) }
        }
    }

    // ------------------------------------------------------------ dans PhilPDF : saisir, formater, calculer
    /** « 1 234,50 € » ou « 1,234.50 » -> 1234.5 ; null si ce n'est pas un nombre. */
    fun nombre(texte: String?): Double? {
        if (texte == null) return null
        var t = texte.trim().replace(" ", "").replace(" ", "").replace(" ", "").replace("'", "")
        t = t.replace(Regex("[^\\d,.\\-+()%]"), "")
        if (t.isEmpty() || t == "-" || t == "+") return null
        val neg = t.startsWith("(") && t.endsWith(")")
        t = t.trim('(', ')', '%')
        if ("," in t && "." in t) t = if (t.lastIndexOf(',') > t.lastIndexOf('.')) t.replace(".", "").replace(",", ".") else t.replace(",", "")
        else if ("," in t) t = if (t.count { it == ',' } == 1) t.replace(",", ".") else t.replace(",", "")
        else if (t.count { it == '.' } > 1) t = t.replace(".", "")
        val v = t.toDoubleOrNull() ?: return null
        return if (neg) -v else v
    }

    private fun nombreTxt(v: Double, dec: Int, sep: Int): String {
        val (_, mil, decim) = SEPARATEURS[sep] ?: SEPARATEURS[2]!!
        val s = String.format(Locale.US, "%,.${dec}f", kotlin.math.abs(v))
        val ent = s.substringBefore('.').replace(",", mil)
        val fr = if ('.' in s) s.substringAfter('.') else ""
        return (if (v < 0) "-" else "") + ent + (if (fr.isNotEmpty()) decim + fr else "")
    }

    /** Texte affiche dans le champ (comme Acrobat l'affiche hors saisie). */
    fun formater(regles: JSONObject?, valeur: String): String {
        val fmt = format(regles)
        if (valeur.isEmpty()) return ""
        return when (fmt.optString("genre")) {
            "nombre" -> {
                val v = nombre(valeur) ?: return valeur
                var t = nombreTxt(v, fmt.optInt("decimales", 2), fmt.optInt("separateur", 2))
                if (v < 0 && fmt.optInt("negatif", 0) in listOf(2, 3)) t = "(" + t.trimStart('-') + ")"
                val sym = fmt.optString("symbole", "").trim()
                if (sym.isNotEmpty()) t = if (fmt.optBoolean("symbole_avant")) "$sym $t" else "$t $sym"
                t
            }
            "pourcentage" -> nombre(valeur)?.let { nombreTxt(it * 100, fmt.optInt("decimales", 0), fmt.optInt("separateur", 2)) + " %" } ?: valeur
            else -> valeur
        }
    }

    /** Format Acrobat (dd/mm/yyyy HH:MM) -> format Java. */
    private fun javaDate(fmt: String): String {
        val rep = listOf("yyyy" to "yyyy", "yy" to "yy", "mmmm" to "MMMM", "mmm" to "MMM", "mm" to "MM", "dd" to "dd", "HH" to "HH",
            "MM" to "mm", "ss" to "ss", "tt" to "a")
        val out = StringBuilder(); var i = 0
        while (i < fmt.length) {
            val r = rep.firstOrNull { fmt.startsWith(it.first, i) }
            if (r != null) { out.append(r.second); i += r.first.length; continue }
            val c = fmt[i]
            out.append(when (c) { 'd' -> "d"; 'm' -> "M"; 'H' -> "H"; 'h' -> "h"; else -> if (c.isLetter()) "'$c'" else c.toString() })
            i++
        }
        return out.toString()
    }

    fun ecrireDate(fmt: String, quand: Date = Date()): String = SimpleDateFormat(javaDate(fmt), Locale.FRANCE).format(quand)

    fun lireDate(fmt: String, texte: String): Date? {
        val t = texte.trim()
        if (t.isEmpty()) return null
        for (f in listOf(javaDate(fmt), "dd/MM/yyyy", "dd/MM/yy", "dd-MM-yyyy", "dd.MM.yyyy", "yyyy-MM-dd", "dd/MM/yyyy HH:mm", "HH:mm", "HH:mm:ss", "d MMMM yyyy")) {
            try { val p = SimpleDateFormat(f, Locale.FRANCE).apply { isLenient = false }; val pos = java.text.ParsePosition(0)
                val d = p.parse(t, pos); if (d != null && pos.index == t.length) return d } catch (_: Exception) {}
        }
        return null
    }

    private fun masqueOk(m: String, t: String): Boolean = t.length == m.length && m.zip(t).all { (a, c) ->
        when (a) { '9' -> c.isDigit(); 'A' -> c.isLetter(); 'O' -> c.isLetterOrDigit(); 'X' -> true; else -> a == c } }

    /** Remet les espaces et separateurs du masque : « 0612345678 » -> « 06 12 34 56 78 ». */
    fun appliquerMasque(m: String, texte: String): String? {
        val brut = texte.filter { it.isLetterOrDigit() }.toMutableList()
        val out = StringBuilder()
        for (c in m) if (c in "9AOX") { if (brut.isEmpty()) return null; out.append(brut.removeAt(0).uppercaseChar()) } else out.append(c)
        return if (brut.isEmpty()) out.toString() else null
    }

    fun casse(texte: String, genre: Any?): String = when (genre) {
        true, "tout" -> texte.uppercase(Locale.FRANCE)
        "premiere" -> texte.take(1).uppercase(Locale.FRANCE) + texte.drop(1)
        "mots" -> texte.lowercase(Locale.FRANCE).replace(Regex("(^|[\\s\\-'’])(\\S)")) { it.groupValues[1] + it.groupValues[2].uppercase(Locale.FRANCE) }
        else -> texte
    }

    /** Valeur tapee -> (valeur a garder, code d'erreur ou null). */
    fun saisie(regles: JSONObject?, texte0: String): Pair<String?, String?> {
        val fmt = format(regles)
        val g = fmt.optString("genre", "aucun")
        var texte = if (g != "aucun") texte0.trim() else texte0
        if (texte.isBlank()) return "" to null
        regles?.opt("majuscules")?.takeIf { it != false && it != JSONObject.NULL }?.let { texte = casse(texte, it) }
        if (!controleOk(regles?.txt("controle"), texte)) return null to "controle"
        var v: String = texte
        when (g) {
            "nombre", "pourcentage" -> {
                var n = nombre(texte) ?: return null to "nombre"
                if (g == "pourcentage" && "%" in texte) n /= 100
                v = valeurBrute(n)
            }
            "date" -> { val f = fmt.optString("date").ifEmpty { "dd/mm/yyyy" }; v = ecrireDate(f, lireDate(f, texte) ?: return null to "date") }
            "heure" -> { val f = fmt.optString("heure").ifEmpty { "HH:MM" }; v = ecrireDate(f, lireDate(f, texte) ?: return null to "heure") }
            "masque" -> { val m = fmt.optString("masque"); v = if (masqueOk(m, texte)) texte else appliquerMasque(m, texte) ?: return null to "masque" }
        }
        val plage = regles?.obj("plage")
        if (plage != null && g in listOf("nombre", "pourcentage", "aucun")) {
            val n = nombre(v)
            if (n != null && ((!plage.isNull("min") && n < plage.optDouble("min")) || (!plage.isNull("max") && n > plage.optDouble("max"))))
                return null to "plage"
        }
        return v to null
    }

    /** Valeur d'un champ calcule a partir des valeurs des autres. */
    fun calculer(regles: JSONObject, valeurs: Map<String, String>, formats: Map<String, String?>): String? {
        val c = regles.obj("calcul") ?: return null
        val g = c.optString("genre")
        if (g == "copie") return valeurs[c.optString("source")] ?: ""
        if (g in listOf("age", "ecart_jours", "date_plus")) {
            fun d(nom: String) = lireDate(formats[nom] ?: "dd/mm/yyyy", valeurs[nom] ?: "")
            return when (g) {
                "age" -> d(c.optString("source"))?.let { n ->
                    val a = Calendar.getInstance(); val b = Calendar.getInstance().apply { time = n }
                    var x = a.get(Calendar.YEAR) - b.get(Calendar.YEAR)
                    if (a.get(Calendar.DAY_OF_YEAR) < b.get(Calendar.DAY_OF_YEAR)) x--
                    x.toString()
                } ?: ""
                "ecart_jours" -> { val a = d(c.optString("debut")); val b = d(c.optString("fin"))
                    if (a != null && b != null) Math.round((b.time - a.time) / 86400000.0).toString() else "" }
                else -> d(c.optString("source"))?.let { n ->
                    val soi = format(regles).let { if (it.optString("genre") == "date") it.optString("date").ifEmpty { "dd/mm/yyyy" } else "dd/mm/yyyy" }
                    ecrireDate(soi, Date(n.time + c.optInt("jours", 0) * 86400000L))
                } ?: ""
            }
        }
        if (g == "formule") {
            val j = try { jetons(c.optString("formule")) } catch (_: Exception) { return null }
            return try { valeurBrute(Expression(j.map { (t, v) -> if (t == "champ") "nombre" to (nombre(valeurs[v]) ?: 0.0).toString() else t to v }).evaluer()) }
            catch (_: Exception) { "0" }
        }
        val nums = (0 until (c.optJSONArray("champs")?.length() ?: 0)).map { nombre(valeurs[c.getJSONArray("champs").getString(it)]) ?: 0.0 }
        if (nums.isEmpty()) return "0"
        return valeurBrute(when (g) { "produit" -> nums.fold(1.0) { a, b -> a * b }; "moyenne" -> nums.average(); "min" -> nums.min(); "max" -> nums.max(); else -> nums.sum() })
    }

    /** Nombre -> texte comme Acrobat le garde (point decimal, sans zeros inutiles). */
    fun valeurBrute(v: Double): String =
        if (kotlin.math.abs(v - Math.rint(v)) < 1e-9) Math.rint(v).toLong().toString()
        else String.format(Locale.US, "%.6f", v).trimEnd('0').trimEnd('.')

    /** Petit calculateur (+ - * / parentheses) pour les formules, sans rien executer d'autre. */
    private class Expression(val j: List<Pair<String, String>>) {
        var i = 0
        fun evaluer(): Double { val v = somme(); return v }
        private fun somme(): Double { var v = produit(); while (i < j.size && j[i].second in listOf("+", "-")) { val o = j[i++].second; val w = produit(); v = if (o == "+") v + w else v - w }; return v }
        private fun produit(): Double { var v = facteur(); while (i < j.size && j[i].second in listOf("*", "/")) { val o = j[i++].second; val w = facteur(); v = if (o == "*") v * w else if (w == 0.0) 0.0 else v / w }; return v }
        private fun facteur(): Double {
            val (t, v) = j[i++]
            return when {
                t == "nombre" -> v.toDouble()
                v == "(" -> { val x = somme(); i++; x }
                v == "-" -> -facteur()
                else -> 0.0
            }
        }
    }

    /** Masquer / montrer un widget (drapeau « cache » de l'annotation). */
    fun afficher(annot: PDFAnnotation, visible: Boolean) {
        val f = annot.flags
        annot.flags = if (visible) f and 2.inv() else f or 2
    }

    val MOIS_FR get() = MOIS
}
