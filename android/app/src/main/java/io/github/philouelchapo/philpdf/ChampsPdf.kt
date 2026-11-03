package io.github.philouelchapo.philpdf

import com.artifex.mupdf.fitz.PDFDocument
import com.artifex.mupdf.fitz.PDFObject
import com.artifex.mupdf.fitz.PDFPage
import com.artifex.mupdf.fitz.PDFWidget
import java.util.Locale

/**
 * Reglages d'un champ ecrits directement dans le PDF, exactement comme PhilPDF Windows (moteur/formulaire.py,
 * app/formulaire_doc.py) : info-bulle, obligatoire, lecture seule, affichage, texte (plusieurs lignes, longueur,
 * alignement, valeur par defaut), police / taille / couleur, liste (tri, choix par defaut, saisie libre), case a cocher
 * (signe, couleur, valeur, cochee par defaut), bouton (texte, action), ordre de tabulation, JavaScript.
 */
object ChampsPdf {
    // drapeaux du champ (/Ff) et de l'annotation (/F), norme PDF
    const val FF_LECTURE = 1
    const val FF_OBLIGATOIRE = 2
    const val FF_MULTILIGNE = 1 shl 12
    const val FF_POUSSOIR = 1 shl 16
    const val FF_COMBO = 1 shl 17
    const val FF_LIBRE = 1 shl 18
    const val FF_PLUSIEURS = 1 shl 21                 // liste ouverte : plusieurs choix possibles
    const val FF_TRI = 1 shl 19
    private const val F_MASQUE = 2
    private const val F_IMPRIME = 4
    private const val F_INVISIBLE = 32

    /** Polices standard du formulaire (nom de ressource -> police), comme Windows (moteur/apparence.py). */
    val POLICES = linkedMapOf("Helv" to "Helvetica", "HeBo" to "Helvetica-Bold", "HeOb" to "Helvetica-Oblique",
        "TiRo" to "Times-Roman", "TiBo" to "Times-Bold", "TiIt" to "Times-Italic", "Cour" to "Courier", "CoBo" to "Courier-Bold")

    /** Signes d'une case : caractere ZapfDingbats d'Acrobat (/MK/CA) et symbole montre (comme Windows). */
    val STYLES_COCHE = linkedMapOf("coche" to ("4" to "✓"), "croix" to ("8" to "✗"), "rond" to ("l" to "●"),
        "carre" to ("n" to "■"), "losange" to ("u" to "◆"), "etoile" to ("H" to "★"))

    /** Couleurs proposees (texte et signe), comme Windows. */
    val COULEURS = listOf(Triple(0f, 0f, 0f), Triple(0.08f, 0.38f, 0.76f), Triple(0f, 0f, 0.55f), Triple(0.79f, 0.15f, 0.18f),
        Triple(0.13f, 0.52f, 0.24f), Triple(0.4f, 0.4f, 0.4f))

    /** Actions d'un bouton (comme Windows). */
    val ACTIONS = listOf("reinitialiser", "imprimer", "email", "page")

    data class Proprietes(
        var info: String = "", var obligatoire: Boolean = false, var lecture: Boolean = false, var affichage: Int = 0,
        // texte
        var multi: Boolean = false, var maxlen: Int = 0, var alignement: Int = 0, var defaut: String = "",
        var police: String = "Helv", var taille: Float = 0f, var couleur: Triple<Float, Float, Float> = Triple(0f, 0f, 0f),
        // liste
        var trier: Boolean = false, var libre: Boolean = false, var plusieurs: Boolean = false,
        // case a cocher
        var style: String = "coche", var couleurSigne: Triple<Float, Float, Float> = Triple(0f, 0f, 0f),
        var valeurCochee: String = "Oui", var cocheeDefaut: Boolean = false,
        // bouton
        var legende: String = "")

    private fun f(v: Float) = String.format(Locale.US, "%.2f", v)
    private fun g(v: Float) = String.format(Locale.US, "%.3f", v).trimEnd('0').trimEnd('.').ifEmpty { "0" }

    /** Valeur heritee d'une cle (widget, puis champ parent). */
    private fun herite(w: PDFObject, cle: String): PDFObject {
        var o: PDFObject? = w
        var k = 0
        while (o != null && !o.isNull && k++ < 10) {
            val v = o.get(cle)
            if (!v.isNull) return v
            o = o.get("Parent").takeIf { !it.isNull }
        }
        return PDFObject.Null
    }

    private fun da(pdf: PDFDocument, w: PDFObject): String {
        val v = herite(w, "DA")
        if (!v.isNull) return v.asString()
        return try { pdf.getTrailer().get("Root").get("AcroForm").get("DA").asString() } catch (_: Exception) { "" }
    }

    fun lire(pdf: PDFDocument, widget: PDFWidget): Proprietes {
        val w = widget.getObject()
        val ch = Regles.champDe(w)
        val ff = herite(w, "Ff").let { if (it.isNull) 0 else it.asInteger() }
        val fa = w.get("F").let { if (it.isNull) 0 else it.asInteger() }
        val p = Proprietes()
        p.info = ch.get("TU").let { if (it.isNull) "" else it.asString() }
        p.obligatoire = ff and FF_OBLIGATOIRE != 0
        p.lecture = ff and FF_LECTURE != 0
        p.affichage = when {
            fa and F_INVISIBLE != 0 && fa and F_IMPRIME != 0 -> 3
            fa and F_MASQUE != 0 -> 1
            fa and F_IMPRIME == 0 -> 2
            else -> 0
        }
        p.multi = ff and FF_MULTILIGNE != 0
        p.maxlen = herite(w, "MaxLen").let { if (it.isNull) 0 else it.asInteger() }
        p.alignement = herite(w, "Q").let { if (it.isNull) 0 else it.asInteger() }
        val dv = herite(w, "DV")
        p.defaut = if (dv.isString) dv.asString() else ""
        val d = da(pdf, w)
        Regex("/([^\\s/]+)\\s+([\\d.]+)\\s+Tf").find(d)?.let { m -> p.police = m.groupValues[1]; p.taille = m.groupValues[2].toFloatOrNull() ?: 0f }
        Regex("([\\d.]+)\\s+([\\d.]+)\\s+([\\d.]+)\\s+rg").find(d)?.let { m ->
            Triple(m.groupValues[1].toFloat(), m.groupValues[2].toFloat(), m.groupValues[3].toFloat()).let { p.couleur = it; p.couleurSigne = it }
        } ?: Regex("([\\d.]+)\\s+g\\b").find(d)?.let { m -> val x = m.groupValues[1].toFloat(); p.couleur = Triple(x, x, x); p.couleurSigne = p.couleur }
        p.trier = ff and FF_TRI != 0
        p.libre = ff and FF_LIBRE != 0
        p.plusieurs = ff and FF_PLUSIEURS != 0
        val ca = w.get("MK").get("CA")
        if (ca.isString) {
            val c = ca.asString()
            if (widget.fieldType == PDFWidget.TYPE_BUTTON) p.legende = c
            else STYLES_COCHE.entries.firstOrNull { it.value.first == c }?.let { p.style = it.key }
        }
        if (widget.fieldType == PDFWidget.TYPE_CHECKBOX || widget.fieldType == PDFWidget.TYPE_RADIOBUTTON) {
            p.valeurCochee = etatCoche(w) ?: "Oui"
            p.cocheeDefaut = dv.isName && dv.asName() != "Off"
            if (widget.fieldType == PDFWidget.TYPE_RADIOBUTTON && !ca.isString) p.style = "rond"
        }
        return p
    }

    /** Nom de l'etat « coche » d'une case (cle de /AP/N autre que Off). */
    private fun etatCoche(w: PDFObject): String? {
        val n = w.get("AP").get("N")
        if (!n.isDictionary) return null
        for (k in n) { val nom = k.asName(); if (nom != "Off") return nom }
        return null
    }

    /** Police standard dans les ressources du formulaire (comme Windows assurer_police). */
    fun assurerPolice(pdf: PDFDocument, nom: String) {
        val base = POLICES[nom] ?: return
        val racine = pdf.getTrailer().get("Root")
        var af = racine.get("AcroForm")
        if (af.isNull) { af = objetIndirect(pdf, pdf.newDictionary()); racine.put("AcroForm", af) }
        var dr = af.get("DR")
        if (dr.isNull) { dr = pdf.newDictionary(); af.put("DR", dr) }
        var fonts = dr.get("Font")
        if (fonts.isNull) { fonts = pdf.newDictionary(); dr.put("Font", fonts) }
        if (!fonts.get(nom).isNull) return
        val p = pdf.newDictionary()
        p.put("Type", pdf.newName("Font")); p.put("Subtype", pdf.newName("Type1")); p.put("BaseFont", pdf.newName(base))
        p.put("Encoding", pdf.newName("WinAnsiEncoding"))
        fonts.put(nom, objetIndirect(pdf, p))
    }

    /** Ecrit les reglages (memes cles que Windows), puis redessine le champ. */
    fun ecrire(pdf: PDFDocument, widget: PDFWidget, p: Proprietes) {
        val w = widget.getObject()
        val ch = Regles.champDe(w)
        val genre = widget.fieldType
        if (p.info.isNotBlank()) ch.put("TU", pdf.newString(p.info.trim())) else ch.delete("TU")
        var ff = herite(w, "Ff").let { if (it.isNull) 0 else it.asInteger() }
        fun bit(b: Int, oui: Boolean) { ff = if (oui) ff or b else ff and b.inv() }
        bit(FF_OBLIGATOIRE, p.obligatoire); bit(FF_LECTURE, p.lecture)
        if (genre == PDFWidget.TYPE_TEXT) bit(FF_MULTILIGNE, p.multi)
        if (genre == PDFWidget.TYPE_COMBOBOX || genre == PDFWidget.TYPE_LISTBOX) {
            bit(FF_TRI, p.trier)
            // plusieurs choix : liste ouverte (comme Acrobat, une liste deroulante n'en permet qu'un)
            val etait = ff and FF_PLUSIEURS != 0
            bit(FF_PLUSIEURS, p.plusieurs)
            if (p.plusieurs) bit(FF_COMBO, false) else if (etait) bit(FF_COMBO, true)
            bit(FF_LIBRE, p.libre && !p.plusieurs)
        }
        ch.put("Ff", ff)
        var fa = w.get("F").let { if (it.isNull) 0 else it.asInteger() }
        fa = fa and (F_MASQUE or F_IMPRIME or F_INVISIBLE).inv()
        fa = fa or when (p.affichage) { 1 -> F_MASQUE; 2 -> 0; 3 -> F_INVISIBLE or F_IMPRIME; else -> F_IMPRIME }
        w.put("F", fa)
        when (genre) {
            PDFWidget.TYPE_TEXT, PDFWidget.TYPE_COMBOBOX, PDFWidget.TYPE_LISTBOX -> {
                if (genre == PDFWidget.TYPE_TEXT) {
                    if (p.maxlen > 0) ch.put("MaxLen", p.maxlen) else ch.delete("MaxLen")
                    if (p.alignement > 0) { ch.put("Q", p.alignement); if (ch !== w) w.put("Q", p.alignement) }
                    else { ch.delete("Q"); w.delete("Q") }
                }
                // valeur par defaut (/DV) ; mise tout de suite si le champ est vide
                if (p.defaut.isNotEmpty()) {
                    ch.put("DV", pdf.newString(p.defaut))
                    val v = herite(w, "V")
                    if (v.isNull || (v.isString && v.asString().isEmpty())) try { widget.setTextValue(p.defaut) } catch (_: Exception) {
                        try { widget.setChoiceValue(p.defaut) } catch (_: Exception) {} }
                } else ch.delete("DV")
                assurerPolice(pdf, p.police)
                val da = "/${p.police} ${g(p.taille)} Tf ${g(p.couleur.first)} ${g(p.couleur.second)} ${g(p.couleur.third)} rg"
                w.put("DA", pdf.newString(da)); if (ch !== w) ch.put("DA", pdf.newString(da))
                if (genre != PDFWidget.TYPE_TEXT && p.trier) trierChoix(pdf, ch)
            }
            PDFWidget.TYPE_CHECKBOX, PDFWidget.TYPE_RADIOBUTTON -> {
                val etat = dessinerCase(pdf, w, p.style, p.couleurSigne, if (genre == PDFWidget.TYPE_CHECKBOX) p.valeurCochee else null)
                if (genre == PDFWidget.TYPE_CHECKBOX) {
                    if (p.cocheeDefaut) {
                        ch.put("DV", pdf.newName(etat))
                        val v = herite(w, "V")
                        if (v.isNull || (v.isName && v.asName() == "Off")) { ch.put("V", pdf.newName(etat)); w.put("AS", pdf.newName(etat)) }
                    } else ch.delete("DV")
                }
            }
            PDFWidget.TYPE_BUTTON -> if (p.legende.isNotBlank()) dessinerBouton(pdf, w, p.legende.trim())
        }
        if (genre != PDFWidget.TYPE_CHECKBOX && genre != PDFWidget.TYPE_RADIOBUTTON && genre != PDFWidget.TYPE_BUTTON)
            try { widget.update() } catch (_: Exception) {}
    }

    /** Choix de la liste par ordre alphabetique (comme Windows : sorted(key=str.lower)). */
    private fun trierChoix(pdf: PDFDocument, ch: PDFObject) {
        val opt = ch.get("Opt")
        if (!opt.isArray) return
        val l = (0 until opt.size()).map { opt.get(it) }
        fun cle(o: PDFObject) = (if (o.isArray) o.get(1) else o).let { if (it.isString) it.asString() else "" }.lowercase(Locale.FRENCH)
        val tri = pdf.newArray()
        l.sortedBy { cle(it) }.forEach { tri.ajouter(it) }
        ch.put("Opt", tri)
    }

    // ---------------------------------------------------------------- case a cocher : dessin du signe (comme Windows)
    private fun trace(style: String, lw: Float, lh: Float, c: Triple<Float, Float, Float>): String {
        val cm = minOf(lw, lh); val cx = lw / 2; val cy = lh / 2
        val plein = "${g(c.first)} ${g(c.second)} ${g(c.third)} rg "
        val trait = "${g(c.first)} ${g(c.second)} ${g(c.third)} RG ${f(maxOf(1f, cm * 0.12f))} w 1 J 1 j "
        return when (style) {
            "coche" -> trait + "${f(cx - cm * 0.30f)} ${f(cy + cm * 0.02f)} m ${f(cx - cm * 0.08f)} ${f(cy - cm * 0.22f)} l " +
                "${f(cx + cm * 0.32f)} ${f(cy + cm * 0.28f)} l S"
            "croix" -> trait + "${f(cx - cm * 0.28f)} ${f(cy - cm * 0.28f)} m ${f(cx + cm * 0.28f)} ${f(cy + cm * 0.28f)} l " +
                "${f(cx - cm * 0.28f)} ${f(cy + cm * 0.28f)} m ${f(cx + cm * 0.28f)} ${f(cy - cm * 0.28f)} l S"
            "rond" -> {
                val r = cm * 0.26f; val k = 0.5523f * r
                plein + "${f(cx + r)} ${f(cy)} m ${f(cx + r)} ${f(cy + k)} ${f(cx + k)} ${f(cy + r)} ${f(cx)} ${f(cy + r)} c " +
                    "${f(cx - k)} ${f(cy + r)} ${f(cx - r)} ${f(cy + k)} ${f(cx - r)} ${f(cy)} c " +
                    "${f(cx - r)} ${f(cy - k)} ${f(cx - k)} ${f(cy - r)} ${f(cx)} ${f(cy - r)} c " +
                    "${f(cx + k)} ${f(cy - r)} ${f(cx + r)} ${f(cy - k)} ${f(cx + r)} ${f(cy)} c f"
            }
            "carre" -> { val a = cm * 0.25f; plein + "${f(cx - a)} ${f(cy - a)} ${f(2 * a)} ${f(2 * a)} re f" }
            "losange" -> { val a = cm * 0.32f; plein + "${f(cx)} ${f(cy + a)} m ${f(cx + a)} ${f(cy)} l ${f(cx)} ${f(cy - a)} l ${f(cx - a)} ${f(cy)} l h f" }
            else -> {
                val pts = (0 until 10).map { i ->
                    val r = cm * (if (i % 2 == 0) 0.34f else 0.14f); val ang = Math.PI / 2 + i * Math.PI / 5
                    (cx + r * Math.cos(ang)).toFloat() to (cy + r * Math.sin(ang)).toFloat()
                }
                plein + "${f(pts[0].first)} ${f(pts[0].second)} m " + pts.drop(1).joinToString(" ") { "${f(it.first)} ${f(it.second)} l" } + " h f"
            }
        }
    }

    private fun cadre(w: PDFObject, lw: Float, lh: Float): String {
        var out = ""
        val bg = w.get("MK").get("BG")
        if (bg.isArray) when (bg.size()) {
            1 -> out += "${g(bg.get(0).asFloat())} g 0 0 ${f(lw)} ${f(lh)} re f "
            3 -> out += "${g(bg.get(0).asFloat())} ${g(bg.get(1).asFloat())} ${g(bg.get(2).asFloat())} rg 0 0 ${f(lw)} ${f(lh)} re f "
        }
        val bc = w.get("MK").get("BC")
        if (bc.isArray && bc.size() > 0) {
            val larg = w.get("BS").get("W").let { if (it.isNull) 1f else it.asFloat() }
            val coul = if (bc.size() == 1) "${g(bc.get(0).asFloat())} G" else if (bc.size() == 3)
                "${g(bc.get(0).asFloat())} ${g(bc.get(1).asFloat())} ${g(bc.get(2).asFloat())} RG" else "0 G"
            val h = larg / 2
            out += "$coul ${f(larg)} w ${f(h)} ${f(h)} ${f(lw - larg)} ${f(lh - larg)} re S "
        }
        return out
    }

    private fun taille(w: PDFObject): Pair<Float, Float> {
        val r = w.get("Rect")
        return kotlin.math.abs(r.get(2).asFloat() - r.get(0).asFloat()) to kotlin.math.abs(r.get(3).asFloat() - r.get(1).asFloat())
    }

    /** Apparences cochee / Off dans le style choisi ; /MK/CA garde le caractere ZapfDingbats pour Acrobat.
     *  valeur : nom de l'etat coche (valeur exportee). Renvoie ce nom. */
    fun dessinerCase(pdf: PDFDocument, w: PDFObject, style: String, couleur: Triple<Float, Float, Float>, valeur: String?): String {
        val (lw, lh) = taille(w)
        val ancien = etatCoche(w)
        val brut = (valeur?.takeIf { it.isNotBlank() } ?: ancien ?: "Oui").trim()
        val nom = brut.filter { it.isLetterOrDigit() || it in "-_." }.ifEmpty { "Oui" }
        val cad = cadre(w, lw, lh)
        val ap = pdf.newDictionary()
        for (mode in listOf("N", "D")) {
            val d = pdf.newDictionary()
            for ((etat, contenu) in listOf(nom to (cad + trace(style, lw, lh, couleur)), "Off" to cad)) {
                val x = pdf.newDictionary()
                x.put("Type", pdf.newName("XObject")); x.put("Subtype", pdf.newName("Form"))
                val bb = pdf.newArray(); bb.push(0f); bb.push(0f); bb.push(lw); bb.push(lh); x.put("BBox", bb)
                x.put("Resources", pdf.newDictionary())
                d.put(etat, pdf.addStream(contenu, x))
            }
            ap.put(mode, d)
        }
        w.put("AP", ap)
        var mk = w.get("MK")
        if (mk.isNull) { mk = pdf.newDictionary(); w.put("MK", mk) }
        mk.put("CA", pdf.newString(STYLES_COCHE[style]?.first ?: "4"))
        w.put("DA", pdf.newString("/ZaDb 0 Tf ${g(couleur.first)} ${g(couleur.second)} ${g(couleur.third)} rg"))
        val coche = w.get("AS").let { !it.isNull && it.asName() != "Off" }
        w.put("AS", pdf.newName(if (coche) nom else "Off"))
        val ch = Regles.champDe(w)
        val v = herite(w, "V")
        if (!v.isNull || coche) {
            val estRadio = herite(w, "Ff").let { !it.isNull && it.asInteger() and (1 shl 15) != 0 }
            if (!estRadio) ch.put("V", pdf.newName(if (coche) nom else "Off"))
            else if (coche) ch.put("V", pdf.newName(nom))
        }
        if (ancien != null && ancien != nom) {
            val dv = ch.get("DV"); if (dv.isName && dv.asName() == ancien) ch.put("DV", pdf.newName(nom))
        }
        return nom
    }

    // ---------------------------------------------------------------- bouton (comme Windows dessiner_bouton)
    fun dessinerBouton(pdf: PDFDocument, w: PDFObject, texte: String) {
        val (larg, haut) = taille(w)
        val rayon = minOf(haut / 2.2f, 7f)
        val helv = com.artifex.mupdf.fitz.Font("Helvetica")
        fun longueur(t: Float) = texte.sumOf { c -> helv.advanceGlyph(helv.encodeCharacter(c.code), false).toDouble() }.toFloat() * t
        var t = maxOf(6f, minOf(haut * 0.5f, 13f))
        while (t > 6 && longueur(t) > larg - 10) t -= 0.5f
        val x = (larg - longueur(t)) / 2; val y = (haut - t * 0.72f) / 2
        fun chemin(x0: Float, y0: Float, x1: Float, y1: Float, rr: Float): String {
            val kk = 0.5523f * rr
            return "${f(x0 + rr)} ${f(y0)} m ${f(x1 - rr)} ${f(y0)} l ${f(x1 - rr + kk)} ${f(y0)} ${f(x1)} ${f(y0 + rr - kk)} ${f(x1)} ${f(y0 + rr)} c " +
                "${f(x1)} ${f(y1 - rr)} l ${f(x1)} ${f(y1 - rr + kk)} ${f(x1 - rr + kk)} ${f(y1)} ${f(x1 - rr)} ${f(y1)} c " +
                "${f(x0 + rr)} ${f(y1)} l ${f(x0 + rr - kk)} ${f(y1)} ${f(x0)} ${f(y1 - rr + kk)} ${f(x0)} ${f(y1 - rr)} c " +
                "${f(x0)} ${f(y0 + rr)} l ${f(x0)} ${f(y0 + rr - kk)} ${f(x0 + rr - kk)} ${f(y0)} ${f(x0 + rr)} ${f(y0)} c h"
        }
        val cp = java.nio.charset.Charset.forName("windows-1252")
        val hex = texte.toByteArray(cp).joinToString("") { "%02X".format(it.toInt() and 255) }
        val contenu = "q 0.55 0.65 0.78 rg ${chemin(0.6f, 0f, larg - 0.6f, haut - 1.2f, rayon)} f Q " +
            "q 0.165 0.42 0.69 rg ${chemin(0.6f, 1f, larg - 0.6f, haut - 0.4f, rayon)} f Q " +
            "BT 1 1 1 rg /Helv ${f(t)} Tf ${f(x)} ${f(y)} Td <$hex> Tj ET"
        val police = pdf.newDictionary()
        police.put("Type", pdf.newName("Font")); police.put("Subtype", pdf.newName("Type1"))
        police.put("BaseFont", pdf.newName("Helvetica")); police.put("Encoding", pdf.newName("WinAnsiEncoding"))
        val res = pdf.newDictionary(); val fonts = pdf.newDictionary(); fonts.put("Helv", objetIndirect(pdf, police)); res.put("Font", fonts)
        val xo = pdf.newDictionary()
        xo.put("Type", pdf.newName("XObject")); xo.put("Subtype", pdf.newName("Form"))
        val bb = pdf.newArray(); bb.push(0f); bb.push(0f); bb.push(larg); bb.push(haut); xo.put("BBox", bb)
        xo.put("Resources", res)
        val ap = pdf.newDictionary(); ap.put("N", pdf.addStream(contenu, xo)); w.put("AP", ap)
        val mk = pdf.newDictionary()
        val bg = pdf.newArray(); bg.push(0.165f); bg.push(0.42f); bg.push(0.69f); mk.put("BG", bg)
        mk.put("CA", pdf.newString(texte)); w.put("MK", mk)
        w.put("DA", pdf.newString("/Helv 0 Tf 1 g"))
    }

    /** Pose un bouton (bouton-poussoir) : texte, action gardee dans ses regles (JavaScript pour Acrobat). */
    fun creerBouton(pdf: PDFDocument, page: PDFPage, rect: com.artifex.mupdf.fitz.Rect, nom: String, legende: String, action: org.json.JSONObject) {
        val o = Formulaire.creer(pdf, page, ChampDetecte(page = 0, genre = "bouton", rect = rect, nom = nom)).resolve()
        dessinerBouton(pdf, o, legende)
        val r = Regles.lire(o).put("action", action)
        r.remove("_philpdf")
        Regles.ecrire(pdf, o, r)
    }

    // ---------------------------------------------------------------- ordre de tabulation (comme Windows)
    /** Champs de la page dans l'ordre de /Annots : (index du widget, nom, haut, gauche). */
    fun ordre(page: PDFPage): List<Triple<Int, String, com.artifex.mupdf.fitz.Rect>> =
        (page.widgets ?: emptyArray()).mapIndexed { i, w -> Triple(i, w.name ?: "?", w.bounds) }

    /** Range les widgets de la page dans cet ordre (indices de page.widgets) ; les autres annotations gardent leur place. */
    fun poserOrdre(pdf: PDFDocument, page: PDFPage, indices: List<Int>) {
        val widgets = page.widgets ?: return
        val objs = indices.mapNotNull { widgets.getOrNull(it)?.getObject() }
        val po = page.getObject()
        val an = po.get("Annots")
        if (!an.isArray) return
        val l = (0 until an.size()).map { an.get(it) }
        val places = l.indices.filter { i -> objs.any { it.equals(l[i]) } }
        if (places.size != objs.size) return
        val neuf = pdf.newArray()
        var k = 0
        for (i in l.indices) neuf.ajouter(if (i in places) objs[k++] else l[i])
        po.put("Annots", neuf)
        po.delete("Tabs")
    }

    // ---------------------------------------------------------------- JavaScript du champ, evenement par evenement
    val EVENEMENTS = listOf("K", "F", "V", "C", "Fo", "Bl", "U")
    private val SUR_WIDGET = setOf("Fo", "Bl", "U")
    private const val DEBUT = "/* PhilPDF */"
    private const val FIN = "/* fin PhilPDF */"

    private fun script(x: PDFObject, cle: String): String {
        val a = if (cle == "A") x.get("A") else x.get("AA").get(cle)
        if (a.isNull) return ""
        val js = a.get("JS")
        return when {
            js.isString -> js.asString()
            js.isStream -> String(js.readStream(), Charsets.ISO_8859_1)
            else -> ""
        }
    }

    /** Script -> (partie PhilPDF, votre code). */
    fun separer(texte: String): Pair<String, String> {
        val re = Regex(Regex.escape(DEBUT) + "\\s*(.*?)\\s*" + Regex.escape(FIN), RegexOption.DOT_MATCHES_ALL)
        val phil = re.find(texte)?.groupValues?.get(1) ?: ""
        val perso = texte.replace(Regex(Regex.escape(DEBUT) + ".*?" + Regex.escape(FIN), RegexOption.DOT_MATCHES_ALL), "").trim()
        return phil to perso
    }

    /** {evenement: (code PhilPDF, votre code)}. */
    fun js(widget: PDFWidget): Map<String, Pair<String, String>> {
        val w = widget.getObject().resolve()
        val fx = Regles.champDe(widget.getObject())
        return EVENEMENTS.associateWith { k -> separer(script(if (k in SUR_WIDGET) w else fx, k)) }
    }

    /** Ecrit « votre code » en gardant la partie PhilPDF (genererJs la refait ensuite). */
    fun poserJsPerso(pdf: PDFDocument, widgets: List<PDFWidget>, perso: Map<String, String>) {
        if (widgets.isEmpty()) return
        val fx = Regles.champDe(widgets[0].getObject())
        for ((k, code0) in perso) {
            val cibles = if (k in SUR_WIDGET) widgets.map { it.getObject().resolve() } else listOf(fx)
            for (x in cibles) {
                val (phil, _) = separer(script(x, k))
                val code = code0.trim()
                val texte = listOf(code, if (phil.isNotEmpty()) "$DEBUT\n$phil\n$FIN" else "").filter { it.isNotEmpty() }.joinToString("\n")
                if (texte.isEmpty()) {
                    val aa = x.get("AA"); if (!aa.isNull) { aa.delete(k); if (aa.size() == 0) x.delete("AA") }
                } else {
                    val act = pdf.newDictionary(); act.put("S", pdf.newName("JavaScript")); act.put("JS", pdf.newString(texte))
                    var aa = x.get("AA"); if (aa.isNull) { aa = pdf.newDictionary(); x.put("AA", aa) }
                    aa.put(k, act)
                }
            }
        }
    }
}
