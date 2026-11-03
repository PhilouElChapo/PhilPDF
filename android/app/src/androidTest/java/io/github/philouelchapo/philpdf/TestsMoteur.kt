package io.github.philouelchapo.philpdf

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Typeface
import android.net.Uri
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.artifex.mupdf.fitz.Buffer
import com.artifex.mupdf.fitz.Document
import com.artifex.mupdf.fitz.Font
import com.artifex.mupdf.fitz.Image
import com.artifex.mupdf.fitz.PDFDocument
import com.artifex.mupdf.fitz.PDFPage
import com.artifex.mupdf.fitz.Point
import com.artifex.mupdf.fitz.Rect
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.ByteArrayOutputStream
import java.io.File

/**
 * Essais sur un telephone (simule par GitHub a chaque fabrication) : ce que PhilPDF ecrit dans un PDF est relu apres
 * enregistrement. Ils attrapent les defauts de la bibliotheque MuPDF Java (objet libere deux fois, champ en double,
 * fonction absente) avant qu'ils n'arrivent sur un vrai telephone. Un essai qui echoue bloque la publication.
 */
@RunWith(AndroidJUnit4::class)
class TestsMoteur {
    private val ctx: Context = InstrumentationRegistry.getInstrumentation().targetContext
    private val dossier = File(ctx.cacheDir, "essais").apply { mkdirs() }

    /** Ramasse-miettes : les objets Java liberes trop tot se voient alors (debris, plantage). */
    private fun nettoyer() { repeat(3) { System.gc(); System.runFinalization(); Thread.sleep(50) } }

    private fun police(pdf: PDFDocument, base: String) = pdf.addSimpleFont(Font(base), Font.SIMPLE_ENCODING_LATIN)

    /** PDF d'essai : une page A4 avec du texte (Helvetica gras et normal sur la meme ligne). */
    private fun pdfTexte(nom: String): File {
        val pdf = PDFDocument()
        val res = pdf.newDictionary()
        val fonts = pdf.newDictionary()
        fonts.put("F1", police(pdf, "Helvetica-Bold"))
        fonts.put("F2", police(pdf, "Helvetica"))
        res.put("Font", fonts)
        val contenu = "BT /F1 12 Tf 72 720 Td (Mode de paiement : ) Tj /F2 12 Tf (Virement bancaire) Tj ET\n" +
            "BT /F2 12 Tf 72 690 Td (73 boulevard de la Republique) Tj ET"
        val page = pdf.addPage(Rect(0f, 0f, 595f, 842f), 0, res, contenu)
        pdf.insertPage(-1, page)
        val f = File(dossier, nom)
        pdf.save(f.absolutePath, "")
        pdf.destroy()
        return f
    }

    /** PDF d'essai « scanne » : le texte n'est qu'une image. */
    private fun pdfImage(nom: String, texte: String, aLEnvers: Boolean = false): File {
        val bm = Bitmap.createBitmap(1654, 400, Bitmap.Config.ARGB_8888)
        val c = Canvas(bm)
        c.drawColor(android.graphics.Color.WHITE)
        if (aLEnvers) c.rotate(180f, bm.width / 2f, bm.height / 2f)
        c.drawText(texte, 80f, 240f, Paint().apply { textSize = 110f; isAntiAlias = true; typeface = Typeface.DEFAULT_BOLD })
        val png = ByteArrayOutputStream().also { bm.compress(Bitmap.CompressFormat.PNG, 100, it) }.toByteArray()
        val pdf = PDFDocument()
        val res = pdf.newDictionary()
        val xo = pdf.newDictionary()
        xo.put("Im0", pdf.addImage(Image(png)))
        res.put("XObject", xo)
        val page = pdf.addPage(Rect(0f, 0f, 595f, 842f), 0, res, "q 523 0 0 126 36 600 cm /Im0 Do Q")
        pdf.insertPage(-1, page)
        val f = File(dossier, nom)
        pdf.save(f.absolutePath, "")
        pdf.destroy()
        return f
    }

    private fun ouvrir(f: File) = runBlocking { DocumentPdf.ouvrir(ctx, Uri.fromFile(f)) }

    private fun enregistrer(d: DocumentPdf, nom: String): File = runBlocking { d.ecrire(File(dossier, nom)) }

    private fun texte(f: File): String {
        val d = Document.openDocument(f.absolutePath)
        try {
            return (0 until d.countPages()).joinToString("\n") { n ->
                val p = d.loadPage(n); try { val st = p.toStructuredText(); try { st.asText() } finally { st.destroy() } } finally { p.destroy() }
            }
        } finally { d.destroy() }
    }

    /** Aucun debris (texte a la place d'un objet) dans les tableaux de la page et du formulaire. */
    private fun sansDebris(f: File) {
        val d = Document.openDocument(f.absolutePath) as PDFDocument
        try {
            for (n in 0 until d.countPages()) {
                val po = d.findPage(n)
                for (cle in listOf("Annots", "Contents")) {
                    val a = po.get(cle)
                    if (a.isArray) for (i in 0 until a.size()) assertTrue("page ${n + 1}, $cle[$i] : debris ${a.get(i)}",
                        a.get(i).isIndirect || a.get(i).isDictionary)
                }
            }
            val champs = d.getTrailer().get("Root").get("AcroForm").get("Fields")
            if (champs.isArray) for (i in 0 until champs.size()) assertTrue("Fields[$i] : ${champs.get(i)}", champs.get(i).isIndirect)
        } finally { d.destroy() }
    }

    /** Le dessin d'origine de la page est toujours la (images, texte) : rien n'est perdu a l'enregistrement. */
    private fun contenuGarde(f: File, attendu: String) {
        val d = Document.openDocument(f.absolutePath) as PDFDocument
        try {
            val c = d.findPage(0).get("Contents")
            val flux = if (c.isArray) (0 until c.size()).map { c.get(it) } else listOf(c)
            val tout = flux.joinToString("\n") { x -> try { String(x.readStream(), Charsets.ISO_8859_1) } catch (_: Exception) { "" } }
            assertTrue("contenu d'origine perdu (« $attendu » absent)", tout.contains(attendu))
        } finally { d.destroy() }
    }

    // ------------------------------------------------------------------ bibliotheque MuPDF Java
    @Test fun ajoutAUnTableauSansDebris() {
        val pdf = PDFDocument()
        val tableau = pdf.newArray()
        repeat(20) { tableau.ajouter(pdf.addStream("q Q % flux $it\n")) }
        val racine = pdf.getTrailer().get("Root")
        racine.put("EssaiPhilPDF", objetIndirect(pdf, tableau))
        nettoyer()
        val f = File(dossier, "tableau.pdf")
        pdf.addPage(Rect(0f, 0f, 100f, 100f), 0, pdf.newDictionary(), "").let { pdf.insertPage(-1, it) }
        pdf.save(f.absolutePath, "")
        pdf.destroy()
        val d = Document.openDocument(f.absolutePath) as PDFDocument
        try {
            val t = d.getTrailer().get("Root").get("EssaiPhilPDF")
            assertEquals(20, t.size())
            for (i in 0 until 20) {
                assertTrue("element $i : ${t.get(i)}", t.get(i).isIndirect)
                assertTrue(String(t.get(i).readStream()).contains("flux $i"))
            }
        } finally { d.destroy() }
    }

    @Test fun objetIndirectEstUneReference() {
        val pdf = PDFDocument()
        val ref = objetIndirect(pdf, pdf.newDictionary().also { it.put("Essai", 1) })
        assertTrue(ref.isIndirect)
        assertEquals(1, ref.get("Essai").asInteger())
        pdf.destroy()
    }

    // ------------------------------------------------------------------ formulaires
    @Test fun champsCreesUneSeuleFois() {
        val d = ouvrir(pdfTexte("champs.pdf"))
        runBlocking {
            assertTrue(d.creerChamps(listOf(
                ChampDetecte(0, "texte", Rect(300f, 100f, 500f, 120f), "Nom"),
                ChampDetecte(0, "case", Rect(300f, 140f, 314f, 154f), "Accord"),
                ChampDetecte(0, "liste", Rect(300f, 170f, 450f, 190f), "Ville", choix = listOf("Nice", "Cannes", "Antibes")),
                ChampDetecte(0, "signature", Rect(300f, 220f, 480f, 270f), "Signature"))))
        }
        nettoyer()
        val f = enregistrer(d, "champs-ecrits.pdf")
        sansDebris(f)
        val p = Document.openDocument(f.absolutePath) as PDFDocument
        try {
            val annots = p.findPage(0).get("Annots")
            val champs = p.getTrailer().get("Root").get("AcroForm").get("Fields")
            assertEquals(4, annots.size())
            assertEquals(4, champs.size())
            for (i in 0 until 4) assertEquals("champ $i : meme objet dans la page et dans le formulaire",
                annots.get(i).asIndirect(), champs.get(i).asIndirect())
            val pg = p.loadPage(0) as PDFPage
            try { assertEquals(listOf("Nom", "Accord", "Ville", "Signature"), pg.widgets.map { it.name }) } finally { pg.destroy() }
        } finally { p.destroy() }
    }

    @Test fun proprietesBoutonEtOrdre() {
        val d = ouvrir(pdfTexte("proprietes.pdf"))
        runBlocking {
            d.creerChamps(listOf(ChampDetecte(0, "texte", Rect(300f, 100f, 500f, 120f), "Nom"),
                ChampDetecte(0, "liste", Rect(300f, 170f, 450f, 190f), "Ville", choix = listOf("Nice", "Cannes", "Antibes")),
                ChampDetecte(0, "case", Rect(300f, 140f, 314f, 154f), "Accord")))
            val nom = d.champA(0, Point(400f, 110f))!!
            val (p0, _) = d.proprietesChamp(nom)!!
            p0.obligatoire = true; p0.info = "Votre nom"; p0.maxlen = 20; p0.alignement = 1; p0.police = "TiRo"; p0.taille = 11f
            assertTrue(d.ecrireReglesChamp(nom, Regles.vide(), null, p0))
            val ville = d.champA(0, Point(400f, 180f))!!
            val (p1, _) = d.proprietesChamp(ville)!!
            p1.trier = true; p1.defaut = "Cannes"; p1.libre = true
            assertTrue(d.ecrireReglesChamp(ville, Regles.vide(), listOf("Nice", "Cannes", "Antibes"), p1))
            assertTrue("saisie libre vue au remplissage", d.champA(0, Point(400f, 180f))!!.libre)
            assertTrue(d.remplir(d.champA(0, Point(400f, 180f))!!, "Grasse") == null)
            val accord = d.champA(0, Point(307f, 147f))!!
            val (p2, _) = d.proprietesChamp(accord)!!
            p2.style = "etoile"; p2.valeurCochee = "OK"; p2.cocheeDefaut = true
            assertTrue(d.ecrireReglesChamp(accord, Regles.vide(), null, p2))
            assertTrue(d.creerBouton(0, Rect(300f, 300f, 420f, 324f), "Imprimer", org.json.JSONObject().put("genre", "imprimer")))
            // proprietes du bouton changees ensuite : il doit rester bleu (le moteur le redessinait en blanc)
            val bouton = d.champA(0, Point(360f, 312f))!!
            val (pb, _) = d.proprietesChamp(bouton)!!
            pb.info = "Imprimer le formulaire"
            assertTrue(d.ecrireReglesChamp(bouton, Regles.vide().put("action", org.json.JSONObject().put("genre", "imprimer")), null, pb))
            assertTrue(d.poserOrdre(0, listOf(3, 2, 1, 0)))
        }
        nettoyer()
        val f = enregistrer(d, "proprietes-ecrites.pdf")
        sansDebris(f)
        val p = Document.openDocument(f.absolutePath) as PDFDocument
        try {
            val pg = p.loadPage(0) as PDFPage
            try {
                val w = pg.widgets.associateBy { it.name }
                val nom = ChampsPdf.lire(p, w.getValue("Nom"))
                assertTrue(nom.obligatoire); assertEquals("Votre nom", nom.info); assertEquals(20, nom.maxlen)
                assertEquals(1, nom.alignement); assertEquals("TiRo", nom.police)
                val ville = w.getValue("Ville")
                assertEquals(listOf("Antibes", "Cannes", "Nice"), ville.options.toList())
                assertEquals("Cannes", ChampsPdf.lire(p, ville).defaut)
                assertEquals("valeur tapee librement", "Grasse", ville.value)
                val accord = ChampsPdf.lire(p, w.getValue("Accord"))
                assertEquals("etoile", accord.style); assertEquals("OK", accord.valeurCochee); assertTrue(accord.cocheeDefaut)
                val bouton = pg.widgets.first { it.fieldType == com.artifex.mupdf.fitz.PDFWidget.TYPE_BUTTON }
                assertTrue(Regles.lire(bouton.getObject()).optJSONObject("action")?.optString("genre") == "imprimer")
                val ap = String(bouton.getObject().get("AP").get("N").readStream(), Charsets.ISO_8859_1)
                assertTrue("bouton bleu : $ap", ap.contains("0.165 0.42 0.69 rg"))
                assertEquals("ordre de tabulation", "Bouton1", pg.widgets.first().name)
            } finally { pg.destroy() }
        } finally { p.destroy() }
    }

    // ------------------------------------------------------------------ modifier le texte
    @Test fun texteMixteGardeGrasEtNormal() {
        val d = ouvrir(pdfTexte("mixte.pdf"))
        val r = runBlocking {
            val par = d.paragrapheA(0, Point(100f, 842f - 722f))
            assertNotNull("paragraphe touche", par)
            d.reecrireTexte(par!!, listOf("Mode de paiement : Prelevement"), par.lignes[0].taille, 0, par.lignes[0].gras,
                par.lignes[0].italique, false)
        }
        assertTrue(r.message, r.ok)
        nettoyer()
        val f = enregistrer(d, "mixte-ecrit.pdf")
        sansDebris(f)
        val doc = Document.openDocument(f.absolutePath)
        try {
            val pg = doc.loadPage(0)
            val polices = HashMap<String, String>()
            val st = pg.toStructuredText()
            st.walk(object : com.artifex.mupdf.fitz.StructuredTextWalker {
                val l = StringBuilder()
                override fun onImageBlock(bbox: Rect?, transform: com.artifex.mupdf.fitz.Matrix?, image: Image?) {}
                override fun beginTextBlock(bbox: Rect?, flags: Int) {}
                override fun endTextBlock() {}
                override fun beginLine(bbox: Rect?, wmode: Int, dir: Point?) {}
                override fun endLine() {}
                override fun onChar(c: Int, origin: Point?, font: Font?, size: Float, q: com.artifex.mupdf.fitz.Quad?, argb: Int, flags: Int, bidi: Int) {
                    l.appendCodePoint(c); if (c == 'M'.code || c == 'P'.code) polices[String(Character.toChars(c))] = font?.name ?: ""
                }
                override fun beginStruct(standard: String?, raw: String?, index: Int) {}
                override fun endStruct() {}
                override fun onVector(bbox: Rect?, info: com.artifex.mupdf.fitz.StructuredTextWalker.VectorInfo?, argb: Int) {}
            })
            st.destroy(); pg.destroy()
            assertTrue("« Mode » en gras : ${polices["M"]}", polices["M"]!!.contains("Bold"))
            assertFalse("« Prelevement » normal : ${polices["P"]}", polices["P"]!!.contains("Bold"))
        } finally { doc.destroy() }
        assertTrue(texte(f).contains("Prelevement"))
        assertTrue("l'autre ligne est toujours la", texte(f).contains("73 boulevard"))
    }

    @Test fun texteALEnversModifiable() {
        val pdf = PDFDocument()
        val res = pdf.newDictionary(); val fonts = pdf.newDictionary()
        fonts.put("F1", police(pdf, "Helvetica")); res.put("Font", fonts)
        val page = pdf.addPage(Rect(0f, 0f, 595f, 842f), 0, res,
            "BT /F1 14 Tf -1 0 0 -1 400 600 Tm (ENVERS) Tj ET\nBT /F1 12 Tf 72 100 Td (Bas de page) Tj ET")
        pdf.insertPage(-1, page)
        val src = File(dossier, "envers-texte.pdf"); pdf.save(src.absolutePath, ""); pdf.destroy()
        val d = ouvrir(src)
        val r = runBlocking {
            // « ENVERS » ecrit a l'envers : il s'etend vers la gauche du point (400, 600) du PDF, soit y = 242 sur la page
            val par = d.paragrapheA(0, Point(370f, 842f - 600f + 5f))
            assertNotNull("texte a l'envers trouve sous le doigt", par)
            d.reecrireTexte(par!!, listOf("ENDROIT"), par.lignes[0].taille, 0, par.lignes[0].gras, par.lignes[0].italique, false)
        }
        assertTrue(r.message, r.ok)
        val f = enregistrer(d, "envers-texte-ecrit.pdf")
        sansDebris(f)
        assertTrue(texte(f).contains("ENDROIT"))
        assertTrue(texte(f).contains("Bas de page"))
    }

    // ------------------------------------------------------------------ reconnaissance du texte
    @Test fun ocrPoseEtRelu() {
        val d = ouvrir(pdfImage("scan.pdf", "PHILPDF ESSAI"))
        val r = runBlocking { d.reconnaitre(ctx, null, "fra", false) { _, _ -> } }
        assertTrue("mots reconnus : ${r.mots}", r.mots > 0)
        nettoyer()
        val f = enregistrer(d, "scan-ocr.pdf")
        sansDebris(f)
        assertTrue("texte relu : ${texte(f)}", texte(f).uppercase().contains("PHILPDF"))
        contenuGarde(f, "/Im0 Do")
    }

    @Test fun ocrTexteALEnvers() {
        val d = ouvrir(pdfImage("envers.pdf", "PASSPORT MISSION", aLEnvers = true))
        val r = runBlocking { d.reconnaitre(ctx, null, "fra", true) { _, _ -> } }
        assertTrue("mots reconnus : ${r.mots}", r.mots > 0)
        val f = enregistrer(d, "envers-ocr.pdf")
        sansDebris(f)
        assertTrue("texte relu : ${texte(f)}", texte(f).uppercase().contains("PASSPORT"))
        assertFalse("charabia du texte lu a l'endroit : ${texte(f)}", texte(f).uppercase().contains("NOISSIN"))
        contenuGarde(f, "/Im0 Do")
    }

    @Test fun listeAPlusieursChoix() {
        val d = ouvrir(pdfTexte("plusieurs.pdf"))
        runBlocking {
            d.creerChamps(listOf(ChampDetecte(0, "liste", Rect(300f, 170f, 450f, 230f), "Villes", choix = listOf("Nice", "Cannes", "Antibes"))))
            val c = d.champA(0, Point(400f, 200f))!!
            val (p0, _) = d.proprietesChamp(c)!!
            p0.plusieurs = true
            assertTrue(d.ecrireReglesChamp(c, Regles.vide(), listOf("Nice", "Cannes", "Antibes"), p0))
            val c2 = d.champA(0, Point(400f, 200f))!!
            assertTrue("liste ouverte a plusieurs choix", c2.plusieurs)
            assertTrue(d.remplirPlusieurs(c2, listOf("Antibes", "Nice")))
        }
        nettoyer()
        val f = enregistrer(d, "plusieurs-choix.pdf")
        sansDebris(f)
        val relu = ouvrir(f)
        val c3 = runBlocking { relu.champA(0, Point(400f, 200f)) }!!
        assertEquals("choix gardes, dans l'ordre de la liste", listOf("Nice", "Antibes"), c3.choisis)
    }

    @Test fun imagesDeLaPage() {
        // image placee par « q 523 0 0 126 36 600 cm /Im0 Do Q » : 523 x 126 pt, en bas a gauche a (36, 600) en PDF
        val d = ouvrir(pdfImage("images.pdf", "PHILPDF"))
        val (l, t) = runBlocking { d.images(0) }
        assertEquals("une image sur la page", 1, l.size)
        val i = l[0]
        val c = i.cadre(t)
        assertEquals("largeur", 523f, c[2] - c[0], 1f)
        assertEquals("haut de l'image (page affichee)", 842f - 726f, c[1], 1f)
        assertNotNull("trouvee sous le doigt", runBlocking { d.imageA(0, Point(300f, 180f)) })
        // deplacer de 10 pt vers la droite, tourner d'un quart de tour, miroir, puis verifier apres enregistrement
        assertTrue(runBlocking { d.transformerImage(i, ImagesPdf.M.translation(10f, 0f)) })
        val i2 = runBlocking { d.images(0) }.first.single()
        assertEquals("deplacee", c[0] + 10f, i2.cadre(t)[0], 1f)
        val cc = i2.cadre(t)
        assertTrue(runBlocking { d.transformerImage(i2, ImagesPdf.autour((cc[0] + cc[2]) / 2, (cc[1] + cc[3]) / 2, ImagesPdf.M.rotationEcran(90f))) })
        val i3 = runBlocking { d.images(0) }.first.single()
        val c3 = i3.cadre(t)
        assertEquals("tournee : largeur et hauteur echangees", 126f, c3[2] - c3[0], 1.5f)
        assertTrue(runBlocking { d.miroirImage(i3, true) })
        nettoyer()
        val f = enregistrer(d, "images-modifiees.pdf")
        sansDebris(f)
        val relu = ouvrir(f)
        val l4 = runBlocking { relu.images(0) }.first
        assertEquals("toujours une seule image", 1, l4.size)
        assertEquals("tournee apres enregistrement", 126f, l4[0].cadre(t).let { it[2] - it[0] }, 1.5f)
        // enregistrer l'image en PNG, la remplacer, la supprimer
        val png = runBlocking { relu.exporterImage(l4[0], File(dossier, "image.png")) }
        assertTrue("PNG enregistre", png != null && png.length() > 100)
        assertTrue(runBlocking { relu.remplacerImage(l4[0], png!!.readBytes()) })
        assertEquals(1, runBlocking { relu.images(0) }.first.size)
        assertTrue(runBlocking { relu.supprimerImage(runBlocking { relu.images(0) }.first.single()) })
        assertEquals("image retiree", 0, runBlocking { relu.images(0) }.first.size)
    }

    @Test fun debrisRepares() {
        // fichier abime par une version precedente : des chaines au milieu de la liste des contenus de la page
        val src = pdfImage("abime-source.pdf", "PHILPDF")
        val f = File(dossier, "abime.pdf")
        val doc = Document.openDocument(src.absolutePath) as PDFDocument
        val po = doc.findPage(0)
        val t = doc.newArray()
        t.push("debris"); t.ajouter(po.get("Contents")); t.push("debris")
        po.put("Contents", t)
        doc.save(f.absolutePath, ""); doc.destroy()
        val d = ouvrir(f)
        assertEquals(listOf(1), runBlocking { d.reparerDebris() })
        val r = enregistrer(d, "abime-repare.pdf")
        sansDebris(r)
        contenuGarde(r, "/Im0 Do")
        assertEquals(emptyList<Int>(), runBlocking { ouvrir(r).reparerDebris() })
    }

    // ------------------------------------------------------------------ signature numerique
    @Test fun certificatSignatureEtVerification() {
        val ident = runBlocking { Identites.creer(ctx, "Essai PhilPDF", "motdepasse", "", "", "", "FR", 1) }
        val (clef, chaine) = Identites.ouvrir(Identites.octets(ctx, ident.id)!!, "motdepasse")
        val d = ouvrir(pdfTexte("a-signer.pdf"))
        runBlocking { d.creerChamps(listOf(ChampDetecte(0, "signature", Rect(300f, 600f, 480f, 650f), "Signature"))) }
        val signe = runBlocking { d.signerNumerique(ctx, 0, Rect(300f, 600f, 480f, 650f), Signataire(clef, chaine), "Essai", "", null, "Signature") }
        nettoyer()
        val relu = ouvrir(signe)
        val l = runBlocking { relu.signatures(ctx) }
        assertEquals(1, l.size)
        assertTrue("empreinte intacte", l[0].intacte)
        assertEquals("Essai PhilPDF", l[0].nom)
        assertFalse("pas modifie depuis", l[0].modifieApres)
        Identites.retirer(ctx, ident.id)
    }
}
