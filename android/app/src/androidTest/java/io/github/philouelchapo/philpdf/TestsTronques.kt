package io.github.philouelchapo.philpdf

import android.content.Context
import android.content.res.Configuration
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Paint
import android.net.Uri
import android.util.Log
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.asPaddingValues
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.ui.unit.dp
import androidx.compose.foundation.lazy.LazyListState
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Rect
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.semantics.SemanticsNode
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.semantics.getOrNull
import androidx.compose.ui.test.SemanticsMatcher
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.compose.ui.test.performClick
import androidx.compose.ui.text.TextLayoutResult
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.artifex.mupdf.fitz.Font
import com.artifex.mupdf.fitz.PDFDocument
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.util.Locale

/**
 * Rien de coupe sur un petit telephone ni a l'horizontale, comme tests/test_tronques.py sous Windows : chaque ecran est
 * affiche sur un ecran de 320 x 600 dp (police agrandie de 30 %, comme sur bien des telephones) puis de 650 x 320 dp (paysage), dans les 5 langues ;
 * dans le lecteur, chaque bouton et chaque entree des menus est touche (deux niveaux). Est signale : un texte qui deborde
 * de sa place, un mot coupe en deux d'une ligne a l'autre, des points de suspension, un bouton hors de l'ecran sans
 * defilement pour l'atteindre. Un essai qui echoue bloque la publication (le detail est dans le journal : PhilTronque).
 */
@RunWith(AndroidJUnit4::class)
class TestsTronques {
    @get:Rule val regle = createEmptyComposeRule()

    private val instr = InstrumentationRegistry.getInstrumentation()
    private val ctx: Context = instr.targetContext
    private val problemes = linkedMapOf<String, MutableList<String>>()
    private var echantillon = 12                         // quelques mesures au journal, pour juger l'essai lui-meme

    private class Cadre(val nom: String, val px: String, val police: String)
    private val petit = Cadre("petit téléphone 320×600 dp, police +30 %", "640x1200", "1.3")
    private val paysage = Cadre("paysage 650×320 dp", "1300x640", "1.0")
    private val langues = listOf("fr", "en", "de", "es", "it")

    // ce qui est affiche, change sans relancer l'activite
    private var ecran by mutableStateOf<(@Composable () -> Unit)?>(null)
    private var langue by mutableStateOf("fr")
    private var version by mutableIntStateOf(0)
    private var activite: android.app.Activity? = null

    private fun shell(cmd: String) {
        instr.uiAutomation.executeShellCommand(cmd).use { java.io.FileInputStream(it.fileDescriptor).readBytes() }
    }

    @After fun remettre() {
        instr.runOnMainSync { ctx.getSystemService(android.app.LocaleManager::class.java).applicationLocales = android.os.LocaleList.getEmptyLocaleList() }
        shell("wm size reset"); shell("wm density reset"); shell("settings put system font_scale 1.0")
    }

    private fun texte(id: Int) = ctx.getString(id)

    /** PDF d'essai : deux pages A4 avec du texte. */
    private fun pdf(): File {
        val d = PDFDocument()
        val res = d.newDictionary(); val f = d.newDictionary()
        f.put("F1", d.addSimpleFont(Font("Helvetica"), Font.SIMPLE_ENCODING_LATIN)); res.put("Font", f)
        repeat(2) { k ->
            val p = d.addPage(com.artifex.mupdf.fitz.Rect(0f, 0f, 595f, 842f), 0, res,
                "BT /F1 14 Tf 72 760 Td (Page ${k + 1} : texte pour les essais) Tj ET")
            d.insertPage(-1, p)
        }
        val fichier = File(File(ctx.cacheDir, "essais").apply { mkdirs() }, "tronques.pdf")
        d.save(fichier.absolutePath, ""); d.destroy()
        return fichier
    }

    private fun image(): Bitmap {
        val b = Bitmap.createBitmap(700, 990, Bitmap.Config.ARGB_8888)
        val c = Canvas(b); c.drawColor(android.graphics.Color.WHITE)
        val p = Paint().apply { color = android.graphics.Color.BLACK; textSize = 26f }
        for (i in 0 until 20) c.drawText("Ligne de texte numéro $i pour les essais", 60f, 80f + i * 42f, p)
        return b
    }

    // ------------------------------------------------------------------ verification
    private fun racine(n: SemanticsNode): SemanticsNode { var r = n; while (r.parent != null) r = r.parent!!; return r }

    private fun defile(n: SemanticsNode): Boolean {
        var p: SemanticsNode? = n
        while (p != null) {
            val c = p.config
            if (c.getOrNull(SemanticsProperties.VerticalScrollAxisRange) != null || c.getOrNull(SemanticsProperties.HorizontalScrollAxisRange) != null
                || c.getOrNull(SemanticsProperties.CollectionInfo) != null) return true
            p = p.parent
        }
        return false
    }

    private fun verifier(nom: String) {
        val lieu = "$nom [${langue}]"
        val out = mutableListOf<String>()
        val textes = regle.onAllNodes(SemanticsMatcher.keyIsDefined(SemanticsActions.GetTextLayoutResult), useUnmergedTree = true)
            .fetchSemanticsNodes(atLeastOneRootRequired = false)
        if (textes.isEmpty()) out += "rien d'affiché : l'écran a été perdu (autre application ouverte ?)"
        for (n in textes) {
            if (n.config.getOrNull(SemanticsProperties.EditableText) != null) continue      // champ de saisie : il defile
            val l = mutableListOf<TextLayoutResult>()
            try { n.config[SemanticsActions.GetTextLayoutResult].action?.invoke(l) } catch (_: Exception) { continue }
            val r = l.firstOrNull() ?: continue
            val t = r.layoutInput.text.text
            if (t.isBlank()) continue
            val court = t.replace('\n', ' ').take(60)
            // la place reelle du texte (taille du noeud) contre ses lignes : plus large = coupe a droite, plus haut = coupe en bas
            val w = n.size.width; val h = n.size.height
            if (w == 0 || h == 0) continue                    // pas encore affiche (fenetre qui s'ouvre, sous le volet)
            var large = 0f
            for (i in 0 until r.lineCount) large = maxOf(large, r.getLineRight(i) - r.getLineLeft(i))
            val bas = if (r.lineCount > 0) r.getLineBottom(r.lineCount - 1) else 0f
            if (large > w + 2) out += "« $court » coupé à droite : ${large.toInt()} px pour ${w} px"
            if (bas > h + 2 && !defile(n)) out += "« $court » coupé en bas : ${bas.toInt()} px pour ${h} px (${r.lineCount} ligne(s))"
            if (echantillon-- > 0) Log.i("PhilTronque", "mesure « $court » : noeud ${w}×${h}, lignes ${r.lineCount}, plus large ${large.toInt()}, bas ${bas.toInt()}")
            for (i in 0 until r.lineCount - 1) {
                val e = r.getLineEnd(i)
                if (e in 1 until t.length && t[e - 1].isLetterOrDigit() && t[e].isLetterOrDigit()) {
                    val a = t.lastIndexOf(' ', e - 1) + 1; val b = t.indexOf(' ', e).let { if (it < 0) t.length else it }
                    out += "mot coupé en deux : « ${t.substring(a, b)} » dans « $court »"; break
                }
            }
            if (r.lineCount > 0 && r.isLineEllipsized(r.lineCount - 1)) out += "« $court » se termine par des points de suspension"
        }
        // bas utile de l'ecran : au-dessus de la barre d'Android (retour, accueil, geste) ; un bouton dessous se touche mal.
        // Le clavier n'est pas compte : il couvre l'ecran de fond, et Android remonte (ou agrandit) le champ en cours.
        var basUtile = Float.MAX_VALUE
        instr.runOnMainSync {
            val v = activite?.window?.decorView
            val ins = v?.rootWindowInsets?.getInsets(android.view.WindowInsets.Type.navigationBars())
            if (v != null && ins != null && v.height > 0) basUtile = (v.height - ins.bottom).toFloat()
        }
        // boutons hors de l'ecran, sans defilement pour les atteindre
        for (n in regle.onAllNodes(SemanticsMatcher.keyIsDefined(SemanticsActions.OnClick)).fetchSemanticsNodes(atLeastOneRootRequired = false)) {
            val fen: Rect = racine(n).boundsInWindow
            val b = n.boundsInWindow
            if (b.width <= 0f || fen.width <= 0f) continue
            if ((b.bottom > fen.bottom + 2 || b.right > fen.right + 2 || b.top < fen.top - 2 || b.left < fen.left - 2) && !defile(n))
                out += "bouton « ${etiquette(n).take(50)} » hors de l'écran sans défilement"
            else if (b.bottom > basUtile + 2 && !defile(n))
                out += "bouton « ${etiquette(n).take(50)} » sous la barre d'Android (retour, accueil) : se touche mal"
        }
        if (out.isNotEmpty()) {
            val liste = problemes.getOrPut(lieu) { mutableListOf() }
            out.distinct().forEach { if (it !in liste) { liste += it; Log.e("PhilTronque", "$lieu : $it") } }
        }
    }

    private fun etiquette(n: SemanticsNode): String {
        val t = n.config.getOrNull(SemanticsProperties.Text)?.joinToString(" ") { it.text }
        val d = n.config.getOrNull(SemanticsProperties.ContentDescription)?.joinToString(" ")
        return (t?.takeIf { it.isNotBlank() } ?: d ?: "").trim()
    }

    /** Laisse le temps aux effets (lecture du PDF sur un autre fil, animations des fenetres). */
    private fun attendre(tours: Int = 4) {
        repeat(tours) { Thread.sleep(150); regle.mainClock.advanceTimeBy(400); regle.waitForIdle() }
    }

    private fun montrer(nom: String, contenu: @Composable () -> Unit) {
        try {
            ecran = contenu; version++
            attendre()
            verifier(nom)
        } catch (e: Throwable) {
            problemes.getOrPut("$nom [$langue]") { mutableListOf() } += "essai impossible : $e"
            Log.e("PhilTronque", "$nom [$langue] : essai impossible", e)
        }
    }

    // ------------------------------------------------------------------ lecteur : boutons et menus, deux niveaux
    private val eviter by lazy {
        setOf(texte(R.string.imprimer), texte(R.string.partage_lien), texte(R.string.autre_nom), texte(R.string.ne_pas_enregistrer))
    }

    private fun cliquables(): List<String> =
        regle.onAllNodes(SemanticsMatcher.keyIsDefined(SemanticsActions.OnClick)).fetchSemanticsNodes(atLeastOneRootRequired = false)
            .filter { it.config.getOrNull(SemanticsProperties.Disabled) == null }
            .map { etiquette(it) }.filter { it.isNotBlank() && it !in eviter }.distinct()

    private fun toucher(etiq: String): Boolean {
        val n = regle.onAllNodes(SemanticsMatcher("« $etiq »") { etiquette(it) == etiq } and SemanticsMatcher.keyIsDefined(SemanticsActions.OnClick))
        if (n.fetchSemanticsNodes(atLeastOneRootRequired = false).isEmpty()) return false
        n[0].performClick(); attendre(); return true
    }

    private fun lecteurCharge() {
        val ouverture = ctxLangue().getString(R.string.ouverture)
        repeat(30) {
            attendre(1)
            if (regle.onAllNodes(SemanticsMatcher("ouverture") { etiquette(it) == ouverture }).fetchSemanticsNodes(atLeastOneRootRequired = false).isEmpty()) return
        }
    }

    private fun ctxLangue(): Context {
        val c = Configuration(ctx.resources.configuration).apply { setLocale(Locale.forLanguageTag(langue)) }
        return ctx.createConfigurationContext(c)
    }

    private fun appliquerLangue(lg: String) {
        langue = lg
        instr.runOnMainSync {
            ctx.getSystemService(android.app.LocaleManager::class.java).applicationLocales = android.os.LocaleList.forLanguageTags(lg)
        }
        Thread.sleep(1200)
    }

    private fun explorerLecteur(doc: DocumentPdf, nom: String) {
        val lecteur: @Composable () -> Unit = { Lecteur(doc) {} }
        montrer(nom, lecteur); lecteurCharge(); verifier(nom)
        val niveau1 = cliquables()
        for (a in niveau1) {
            ecran = lecteur; version++; attendre(); lecteurCharge()
            if (!toucher(a)) continue
            verifier("$nom › $a")
            val niveau2 = cliquables().filter { it !in niveau1 }.take(30)
            for (b in niveau2) {
                ecran = lecteur; version++; attendre(); lecteurCharge()
                if (!toucher(a)) continue
                if (!toucher(b)) continue
                verifier("$nom › $a › $b")
            }
        }
    }

    // ------------------------------------------------------------------ ecrans
    @Composable
    private fun AvecEtat(doc: DocumentPdf, contenu: @Composable (EtatLecteur) -> Unit) {
        val etat = remember { EtatLecteur(doc, LazyListState()) }
        etat.portee = rememberCoroutineScope()
        Surface(Modifier.fillMaxSize()) { contenu(etat) }
    }

    private fun e(nom: String, c: @Composable () -> Unit): Pair<String, @Composable () -> Unit> = nom to c

    private fun ecrans(doc: DocumentPdf, tailles: List<Pair<Float, Float>>, img: Bitmap, f: File): List<Pair<String, @Composable () -> Unit>> = listOf(
        e("Démarrage") { Demarrage(false) {} },
        e("Accueil") { Accueil({}, {}) },
        e("Aide") { EcranAide {} },
        e("Comptes") { EcranComptes({}, {}) },
        e("Réglages IA") { ReglagesIa {} },
        e("Numériser") { EcranNumerisation({}, dOffice = false) {} },
        e("Combiner") { EcranCombiner({}, dOffice = false) {} },
        e("Redresser") { RedresserImage(img, ctxLangue().getString(R.string.redresser_page_n, 1), {}, toutes = false) { _, _, _ -> } },
        e("Signer à la main") { PadSignature("signature", {}) {} },
        e("Nommer le scan") { NommerScan(f, img) {} },
        // comme dans le tiroir du lecteur : largeur pleine, 200 a 560 dp de haut
        e("Annoter") { AvecEtat(doc) { et -> Box(Modifier.fillMaxWidth().heightIn(min = 200.dp, max = 560.dp)) { PanneauAnnoter(et) } } },
        e("Signer") { AvecEtat(doc) { et -> Box(Modifier.fillMaxWidth().heightIn(min = 200.dp, max = 560.dp)) { PanneauSigner(et, tailles) } } },
        e("Organiser les pages") { AvecEtat(doc) { et -> OrganiserPages(et, tailles) {} } },
        e("Partager") { AvecEtat(doc) { et -> ChoixPartage(et) {} } },
        e("Résumer avec l'IA") { AvecEtat(doc) { et -> ResumeIa(et) {} } },
        e("Lecture fluide") { AvecEtat(doc) { et -> LectureFluide(et, tailles.size) {} } },
        e("Redresser la page") { AvecEtat(doc) { et -> RedresserPage(et, 0) {} } },
        e("Créer un formulaire") { AvecEtat(doc) { et -> DetectionChamps(et) {} } },
        e("Vérifier les signatures") { AvecEtat(doc) { et -> DialogueVerifier(et) {} } },
        e("Historique") { AvecEtat(doc) { et -> Box { MenuHistorique(et) {} } } },
    )

    private fun lancer(cadre: Cadre, lg: String, bloc: () -> Unit) {
        appliquerLangue(lg)
        ActivityScenario.launch(ComponentActivity::class.java).use { sc ->
            var vue = ""
            sc.onActivity { a ->
                activite = a
                vue = a.resources.configuration.locales[0].language
                // comme MainActivity : marges des barres d'Android transmises aux fenetres, contenu au-dessus des barres
                a.setContent {
                    val marges = androidx.compose.foundation.layout.WindowInsets.safeDrawing.asPaddingValues()
                    androidx.compose.runtime.CompositionLocalProvider(LocalMarges provides marges) {
                        Box(Modifier.safeDrawingPadding()) { key(version) { ecran?.invoke() } }
                    }
                }
            }
            if (vue != lg) problemes.getOrPut("${cadre.nom} [$lg]") { mutableListOf() } += "langue non appliquée ($vue au lieu de $lg)"
            regle.mainClock.autoAdvance = false
            bloc()
            ecran = null; version++; attendre(1); activite = null
        }
    }

    @Test fun rienDeCoupe() {
        Textes.demarrer(ctx)
        val f = pdf()
        val doc = runBlocking { DocumentPdf.ouvrir(ctx, Uri.fromFile(f)) }
        val tailles = runBlocking { doc.tailles() }
        val img = image()
        for (cadre in listOf(petit, paysage)) {
            shell("wm size ${cadre.px}"); shell("wm density 320"); shell("settings put system font_scale ${cadre.police}")
            Thread.sleep(1500)
            for (lg in langues) lancer(cadre, lg) {
                for ((nom, c) in ecrans(doc, tailles, img, f)) montrer("${cadre.nom} · $nom", c)
                // le lecteur, tout ce qu'on peut y toucher : allemand (le plus long) partout, francais sur petit ecran
                if (lg == "de" || (lg == "fr" && cadre === petit)) explorerLecteur(doc, "${cadre.nom} · Lecteur")
            }
        }
        val bilan = problemes.entries.joinToString("\n") { (k, v) -> "✕ $k\n" + v.take(10).joinToString("\n") { "     $it" } }
        Log.i("PhilTronque", if (problemes.isEmpty()) "RESULTAT : OK" else "RESULTAT : ${problemes.size} écran(s) avec un texte coupé\n$bilan")
        assertTrue("Textes coupés sur Android :\n$bilan", problemes.isEmpty())
    }
}
