package io.github.philouelchapo.philpdf

import com.artifex.mupdf.fitz.Buffer
import com.artifex.mupdf.fitz.PDFDocument
import com.artifex.mupdf.fitz.PDFObject
import com.artifex.mupdf.fitz.PDFPage

/**
 * Images de la page (photos, logos, scans) comme objets, comme sous Windows : les trouver sous le doigt, les deplacer,
 * les agrandir, les tourner, les retourner (miroir), les remplacer, les enregistrer, les supprimer.
 *
 * Une image est placee dans le contenu de la page par « a b c d e f cm /Im1 Do » : la matrice dit ou va son carre
 * unite. On lit le contenu de la page (et des sous-objets qu'elle appelle) pour retrouver chaque image, sa matrice
 * complete et l'endroit exact du texte qui la place ; modifier l'image, c'est reecrire cette matrice. L'image
 * elle-meme n'est ni recopiee ni recompressee.
 */
object ImagesPdf {
    /** Matrice 2D (convention PDF : un point est un vecteur ligne, p' = p x M). */
    data class M(val a: Float, val b: Float, val c: Float, val d: Float, val e: Float, val f: Float) {
        operator fun times(o: M) = M(a * o.a + b * o.c, a * o.b + b * o.d, c * o.a + d * o.c, c * o.b + d * o.d,
            e * o.a + f * o.c + o.e, e * o.b + f * o.d + o.f)
        fun inverse(): M {
            val det = a * d - b * c
            if (kotlin.math.abs(det) < 1e-9f) return this
            return M(d / det, -b / det, -c / det, a / det, (c * f - d * e) / det, (b * e - a * f) / det)
        }
        fun point(x: Float, y: Float) = Pair(x * a + y * c + e, x * b + y * d + f)
        companion object {
            val I = M(1f, 0f, 0f, 1f, 0f, 0f)
            fun de(m: com.artifex.mupdf.fitz.Matrix) = M(m.a, m.b, m.c, m.d, m.e, m.f)
            fun translation(x: Float, y: Float) = M(1f, 0f, 0f, 1f, x, y)
            fun echelle(k: Float) = M(k, 0f, 0f, k, 0f, 0f)
            /** Rotation a l'ecran (y vers le bas), sens inverse des aiguilles d'une montre. */
            fun rotationEcran(degres: Float): M {
                val r = Math.toRadians(degres.toDouble())
                val co = kotlin.math.cos(r).toFloat(); val si = kotlin.math.sin(r).toFloat()
                return M(co, -si, si, co, 0f, 0f)
            }
        }
    }

    /** Une image placee sur la page. flux = -1 : le contenu de la page (ses flux mis bout a bout) ; sinon le numero
     *  de l'objet du sous-objet (formulaire XObject) qui la dessine. [debut, fin[ : texte de « /Nom Do ». */
    data class Placee(val page: Int, val nom: String, val objet: Int, val flux: Int, val debut: Int, val fin: Int,
                      val ctm: M, val partage: Boolean) {
        /** Coins de l'image dans le repere de la page affichee (y vers le bas), dans l'ordre du carre unite. */
        fun coins(t: M): List<Pair<Float, Float>> {
            val p = ctm * t
            return listOf(p.point(0f, 0f), p.point(1f, 0f), p.point(1f, 1f), p.point(0f, 1f))
        }
        fun cadre(t: M): FloatArray {
            val c = coins(t)
            return floatArrayOf(c.minOf { it.first }, c.minOf { it.second }, c.maxOf { it.first }, c.maxOf { it.second })
        }
        fun contient(t: M, x: Float, y: Float): Boolean {
            val (u, v) = (ctm * t).inverse().point(x, y)        // point de la page -> carre unite de l'image
            return u in -0.02f..1.02f && v in -0.02f..1.02f
        }
    }

    // ------------------------------------------------------------------ lecture du contenu
    private fun octets(o: PDFObject): String = String(o.readStream(), Charsets.ISO_8859_1)

    private fun contenuPage(po: PDFObject): String {
        val c = po.get("Contents")
        return when {
            c.isArray -> (0 until c.size()).joinToString("\n") { k -> c.get(k).let { x -> if (x.isStream) octets(x) else "" } }
            c.isStream -> octets(c)
            else -> ""
        }
    }

    private fun estDelim(ch: Char) = ch in "()<>[]{}/%" || ch.isWhitespace()

    /** Lecture des operateurs du contenu : appelle op(nom, operandes, debut du premier operande, fin de l'operateur). */
    private fun parcourir(s: String, op: (String, List<String>, Int, Int) -> Unit) {
        var i = 0
        val n = s.length
        val pile = ArrayList<String>()
        var debutOperandes = -1
        while (i < n) {
            val ch = s[i]
            when {
                ch.isWhitespace() -> { i++; continue }
                ch == '%' -> { while (i < n && s[i] != '\n' && s[i] != '\r') i++; continue }
            }
            val debut = i
            val jeton: String
            when {
                ch == '(' -> {                              // chaine, parentheses imbriquees et echappements
                    var prof = 0
                    while (i < n) {
                        val c = s[i]
                        if (c == '\\') { i += 2; continue }
                        if (c == '(') prof++
                        if (c == ')') { prof--; if (prof == 0) { i++; break } }
                        i++
                    }
                    jeton = s.substring(debut, minOf(i, n))
                }
                ch == '<' && i + 1 < n && s[i + 1] == '<' -> { i += 2; jeton = "<<" }
                ch == '>' && i + 1 < n && s[i + 1] == '>' -> { i += 2; jeton = ">>" }
                ch == '<' -> { while (i < n && s[i] != '>') i++; i++; jeton = s.substring(debut, minOf(i, n)) }
                ch == '[' || ch == ']' || ch == '{' || ch == '}' -> { i++; jeton = ch.toString() }
                ch == '/' -> { i++; while (i < n && !estDelim(s[i])) i++; jeton = s.substring(debut, i) }
                else -> { while (i < n && !estDelim(s[i])) i++; if (i == debut) i++; jeton = s.substring(debut, i) }
            }
            val premier = jeton[0]
            val operande = premier == '/' || premier == '(' || premier == '<' || premier == '[' || premier == ']' ||
                premier == '>' || premier.isDigit() || premier == '-' || premier == '+' || premier == '.' ||
                jeton == "true" || jeton == "false" || jeton == "null"
            if (operande) {
                if (pile.isEmpty()) debutOperandes = debut
                pile += jeton
                continue
            }
            if (jeton == "BI") {                             // image en ligne : sautee jusqu'a « EI »
                val id = s.indexOf("ID", i)
                var k = if (id < 0) n else id + 2
                while (k < n) {
                    val e = s.indexOf("EI", k)
                    if (e < 0) { k = n; break }
                    if ((e == 0 || s[e - 1].isWhitespace()) && (e + 2 >= n || estDelim(s[e + 2]))) { k = e + 2; break }
                    k = e + 2
                }
                i = k
                pile.clear(); debutOperandes = -1
                continue
            }
            op(jeton, pile.toList(), if (pile.isEmpty()) debut else debutOperandes, i)
            pile.clear(); debutOperandes = -1
        }
    }

    private fun matrice(o: PDFObject): M {
        if (!o.isArray || o.size() < 6) return M.I
        return M(o.get(0).asFloat(), o.get(1).asFloat(), o.get(2).asFloat(), o.get(3).asFloat(), o.get(4).asFloat(), o.get(5).asFloat())
    }

    /** Images placees sur la page n (dans la page et dans ses sous-objets). */
    fun lister(pdf: PDFDocument, page: PDFPage, n: Int): List<Placee> {
        val po = page.getObject()
        val out = ArrayList<Placee>()
        val appels = HashMap<Int, Int>()                     // sous-objet -> nombre d'appels (pour savoir s'il est partage)
        fun visiter(texte: String, res: PDFObject, ctm0: M, flux: Int, profondeur: Int) {
            val pileCtm = ArrayList<M>()
            var ctm = ctm0
            parcourir(texte) { nom, ops, debut, fin ->
                when (nom) {
                    "q" -> pileCtm += ctm
                    "Q" -> if (pileCtm.isNotEmpty()) ctm = pileCtm.removeAt(pileCtm.size - 1)
                    "cm" -> {
                        val v = ops.mapNotNull { it.toFloatOrNull() }
                        if (v.size == 6) ctm = M(v[0], v[1], v[2], v[3], v[4], v[5]) * ctm
                    }
                    "Do" -> {
                        val nomX = ops.lastOrNull()?.removePrefix("/")
                        val xo = if (nomX != null) res.get("XObject").get(nomX) else null
                        if (xo != null && !xo.isNull) {
                            val sous = xo.get("Subtype").asName()
                            val num = if (xo.isIndirect) xo.asIndirect() else -1
                            if (sous == "Image" && num > 0) {
                                out += Placee(n, nomX!!, num, flux, debut, fin, ctm, false)
                            } else if (sous == "Form" && profondeur < 3 && num > 0) {
                                appels[num] = (appels[num] ?: 0) + 1
                                val r = xo.get("Resources").let { if (it.isNull) res else it }
                                visiter(octets(xo), r, matrice(xo.get("Matrix")) * ctm, num, profondeur + 1)
                            }
                        }
                    }
                }
            }
        }
        val res = po.getInheritable("Resources")
        visiter(contenuPage(po), res, M.I, -1, 0)
        // un sous-objet appele plusieurs fois (logo repete) : le modifier changerait toutes ses copies
        return out.map { if (it.flux > 0 && (appels[it.flux] ?: 0) > 1) it.copy(partage = true) else it }
    }

    // ------------------------------------------------------------------ ecriture
    private fun f(v: Float) = String.format(java.util.Locale.US, "%.5f", v).trimEnd('0').trimEnd('.').let { if (it == "-0") "0" else it }

    private fun texteFlux(pdf: PDFDocument, page: PDFPage, i: Placee): String =
        if (i.flux < 0) contenuPage(page.getObject()) else octets(pdf.newIndirect(i.flux, 0))

    private fun ecrireFlux(pdf: PDFDocument, page: PDFPage, i: Placee, texte: String) {
        val buf = Buffer()
        buf.writeBytes(texte.toByteArray(Charsets.ISO_8859_1))
        if (i.flux < 0) page.getObject().put("Contents", pdf.addStream(buf))   // la page n'a plus qu'un flux
        else pdf.newIndirect(i.flux, 0).writeStream(buf)
    }

    // « q a b c d e f cm /Im Do Q » ecrit par PhilPDF autour de l'image : on le reecrit au lieu d'en ajouter un autre
    private val ENTOURE = Regex("""q\s+([-+.\d]+)\s+([-+.\d]+)\s+([-+.\d]+)\s+([-+.\d]+)\s+([-+.\d]+)\s+([-+.\d]+)\s+cm\s+$""")

    /** Remplace le placement de l'image par la matrice complete voulue (carre unite -> repere PDF). Le texte qui la
     *  place n'est pas touche : « /Im Do » devient « q N cm /Im Do Q » (le reste de la page ne bouge pas). */
    fun placer(pdf: PDFDocument, page: PDFPage, i: Placee, voulue: M, autreNom: String? = null): Boolean {
        if (i.partage) throw IllegalStateException("partage")
        val texte = texteFlux(pdf, page, i)
        if (i.fin > texte.length || !texte.substring(i.debut, i.fin).trimEnd().endsWith("Do")) return false
        val m = fun(x: M) = "${f(x.a)} ${f(x.b)} ${f(x.c)} ${f(x.d)} ${f(x.e)} ${f(x.f)} cm"
        var debut = i.debut; var fin = i.fin
        var sans = i.ctm                                  // matrice de l'image sans notre « cm » d'une modification precedente
        val avant = ENTOURE.find(texte.substring(maxOf(0, i.debut - 120), i.debut))
        val apres = Regex("""^\s*Q""").find(texte.substring(i.fin, minOf(texte.length, i.fin + 8)))
        if (avant != null && apres != null) {
            val v = avant.groupValues.drop(1).map { it.toFloat() }
            sans = M(v[0], v[1], v[2], v[3], v[4], v[5]).inverse() * i.ctm
            debut = maxOf(0, i.debut - 120) + avant.range.first
            fin = i.fin + apres.range.last + 1
        }
        val nouveau = "q ${m(voulue * sans.inverse())} /${autreNom ?: i.nom} Do Q"
        ecrireFlux(pdf, page, i, texte.substring(0, debut) + nouveau + texte.substring(fin))
        return true
    }

    /** Met une autre image a la place (meme largeur, meme centre ; la hauteur suit les proportions de la nouvelle). */
    fun remplacer(pdf: PDFDocument, page: PDFPage, i: Placee, image: com.artifex.mupdf.fitz.Image): Boolean {
        if (i.partage) throw IllegalStateException("partage")
        val res = if (i.flux < 0) page.getObject().getInheritable("Resources") else pdf.newIndirect(i.flux, 0).get("Resources")
        if (res.isNull) return false
        var xo = res.get("XObject")
        if (xo.isNull) { xo = pdf.newDictionary(); res.put("XObject", xo) }
        var k = 1
        while (!xo.get("PhilIm$k").isNull) k++
        xo.put("PhilIm$k", pdf.addImage(image))
        val (t, _) = transformations(page)
        val p = i.ctm * t
        val larg = kotlin.math.hypot(p.a, p.b); val haut = kotlin.math.hypot(p.c, p.d)
        val voulu = larg * image.height / image.width.coerceAtLeast(1)
        val e = if (haut > 0.01f) voulu / haut else 1f
        val s = M(1f, 0f, 0f, e, 0f, (1 - e) / 2)              // carre unite : hauteur changee autour du centre
        return placer(pdf, page, i, s * i.ctm, "PhilIm$k")
    }

    /** Retire l'image de la page (seulement « /Im Do » : le reste du contenu ne change pas). */
    fun supprimer(pdf: PDFDocument, page: PDFPage, i: Placee): Boolean {
        if (i.partage) throw IllegalStateException("partage")
        val texte = texteFlux(pdf, page, i)
        if (i.fin > texte.length) return false
        ecrireFlux(pdf, page, i, texte.substring(0, i.debut) + texte.substring(i.fin))
        return true
    }

    /** Repere de la page affichee (y vers le bas) -> repere PDF, et inverse. */
    fun transformations(page: PDFPage): Pair<M, M> {
        val t = M.de(page.getTransform())
        return t to t.inverse()
    }

    /** Matrice complete apres une transformation g exprimee dans le repere de la page affichee. */
    fun apres(page: PDFPage, i: Placee, g: M): M {
        val (t, inv) = transformations(page)
        return i.ctm * t * g * inv
    }

    fun centre(page: PDFPage, i: Placee): Pair<Float, Float> {
        val c = i.cadre(transformations(page).first)
        return Pair((c[0] + c[2]) / 2, (c[1] + c[3]) / 2)
    }

    /** Autour d'un point fixe (x, y) de la page affichee. */
    fun autour(x: Float, y: Float, g: M) = M.translation(-x, -y) * g * M.translation(x, y)
}
