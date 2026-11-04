package io.github.philouelchapo.philpdf

import android.content.Context
import android.graphics.Bitmap
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.Hyphens
import androidx.compose.ui.text.style.LineBreak
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.artifex.mupdf.fitz.Font
import com.artifex.mupdf.fitz.Matrix
import com.artifex.mupdf.fitz.Point
import com.artifex.mupdf.fitz.Quad
import com.artifex.mupdf.fitz.Rect
import com.artifex.mupdf.fitz.StructuredTextWalker

/**
 * Lecture fluide (comme le « Mode liquide » d'Acrobat) : le texte de chaque page est remis en colonne a la largeur
 * du telephone, avec les titres, le gras et l'italique, les images a leur place. Le PDF n'est pas modifie.
 */
object Fluide {
    class Morceau(val texte: String, val gras: Boolean, val italique: Boolean)

    sealed class Bloc {
        class Titre(val texte: String, val niveau: Int) : Bloc()
        class Para(val morceaux: List<Morceau>, val puce: Boolean) : Bloc()
        class Img(val image: Bitmap) : Bloc()
    }

    /** Une page : ses blocs, ou scannee (aucun texte : on montre l'image de la page). */
    class PageFluide(val blocs: List<Bloc>, val scannee: Boolean)

    private class Car(val c: Int, val taille: Float, val gras: Boolean, val italique: Boolean)
    private class Ligne(val r: Rect) { val cars = ArrayList<Car>() }
    private class BlocTexte(val r: Rect) { val lignes = ArrayList<Ligne>() }

    private val PUCES = setOf('•', '▪', '◦', '·', '‣', '–', '—', '-', '*', '■', '□', '➢', '►', '✓')
    private val NUMERO = Regex("^(\\d{1,3}|[a-zA-Z]|[ivxIVX]{1,4})[.)]\\s")

    private val GRAS = Regex("(?i)bold|black|heavy|semibold|demi")
    private val ITALIQUE = Regex("(?i)italic|oblique")
    private fun gras(f: Font?): Boolean = f != null &&
        (runCatching { f.isBold }.getOrDefault(false) || GRAS.containsMatchIn(runCatching { f.name }.getOrNull() ?: ""))
    private fun italique(f: Font?): Boolean = f != null &&
        (runCatching { f.isItalic }.getOrDefault(false) || ITALIQUE.containsMatchIn(runCatching { f.name }.getOrNull() ?: ""))

    /**
     * Lit la page dans l'ordre de lecture du moteur. image(zone) rend une zone de la page (null : on la laisse).
     */
    fun lire(page: com.artifex.mupdf.fitz.Page, image: (Rect) -> Bitmap?): PageFluide {
        val bord = page.bounds
        val elements = ArrayList<Any>()                      // BlocTexte ou Rect (image)
        var bloc: BlocTexte? = null
        var ligne: Ligne? = null
        val st = page.toStructuredText("preserve-images")
        try {
            st.walk(object : StructuredTextWalker {
                override fun onImageBlock(bbox: Rect?, transform: Matrix?, image: com.artifex.mupdf.fitz.Image?) { bbox?.let { elements += Rect(it) } }
                override fun beginTextBlock(bbox: Rect?, flags: Int) { bloc = BlocTexte(Rect(bbox ?: Rect())).also { elements += it } }
                override fun endTextBlock() { bloc = null }
                override fun beginLine(bbox: Rect?, wmode: Int, dir: Point?) { ligne = Ligne(Rect(bbox ?: Rect())).also { bloc?.lignes?.add(it) } }
                override fun endLine() { ligne = null }
                override fun onChar(c: Int, origin: Point?, font: Font?, size: Float, q: Quad?, argb: Int, flags: Int, bidi: Int) {
                    if (c >= 32 || c == 9) ligne?.cars?.add(Car(if (c == 9) 32 else c, size, gras(font), italique(font)))
                }
                override fun beginStruct(standard: String?, raw: String?, index: Int) {}
                override fun endStruct() {}
                override fun onVector(bbox: Rect?, info: StructuredTextWalker.VectorInfo?, argb: Int) {}
            })
        } finally { st.destroy() }

        val tousCars = elements.filterIsInstance<BlocTexte>().flatMap { b -> b.lignes.flatMap { it.cars } }
            .filter { it.c != 32 }
        if (tousCars.isEmpty()) return PageFluide(emptyList(), true)
        // taille du texte courant : la plus frequente (en nombre de lettres)
        val corps = tousCars.groupingBy { Math.round(it.taille * 2) / 2f }.eachCount().maxByOrNull { it.value }!!.key
        val haut = bord.y1 - bord.y0
        val blocs = ArrayList<Bloc>()
        for (e in elements) {
            if (e is Rect) {
                val w = e.x1 - e.x0; val h = e.y1 - e.y0
                // ni les petits ornements, ni le fond qui couvre toute la page
                if (w < 40 || h < 30 || (w > 0.9f * (bord.x1 - bord.x0) && h > 0.9f * haut)) continue
                image(e)?.let { blocs += Bloc.Img(it) }
                continue
            }
            val b = e as BlocTexte
            val texte = b.lignes.joinToString(" ") { l -> l.cars.joinToString("") { String(Character.toChars(it.c)) } }.trim()
            if (texte.isEmpty()) continue
            // en-tetes et pieds de page courts (numero de page, titre courant) : la lecture fluide les laisse
            val marge = 0.06f * haut
            if ((b.r.y1 < bord.y0 + marge || b.r.y0 > bord.y1 - marge) && texte.length <= 80) continue
            blocs += paragraphes(b, corps)
        }
        return PageFluide(blocs, false)
    }

    private fun paragraphes(b: BlocTexte, corps: Float): List<Bloc> {
        val out = ArrayList<Bloc>()
        val largeur = (b.r.x1 - b.r.x0).coerceAtLeast(1f)
        var courant = ArrayList<Ligne>()
        fun finir() {
            if (courant.isEmpty()) return
            out += para(courant, corps)
            courant = ArrayList()
        }
        var avant: Ligne? = null
        for (l in b.lignes) {
            val t = l.cars.joinToString("") { String(Character.toChars(it.c)) }.trim()
            if (t.isEmpty()) continue
            val p = avant
            if (p != null) {
                val hauteur = (p.r.y1 - p.r.y0).coerceAtLeast(1f)
                val ecart = l.r.y0 - p.r.y1
                val tp = p.cars.joinToString("") { String(Character.toChars(it.c)) }.trim()
                val courte = (p.r.x1 - p.r.x0) < 0.7f * largeur && tp.isNotEmpty() && tp.last() in setOf('.', ':', '!', '?', ';')
                val puce = t.first() in PUCES || NUMERO.containsMatchIn(t)
                val autreTaille = kotlin.math.abs(moyenne(l) - moyenne(p)) > 0.2f * corps
                if (ecart > 0.8f * hauteur || courte || puce || autreTaille) finir()
            }
            courant += l
            avant = l
        }
        finir()
        return out
    }

    private fun moyenne(l: Ligne): Float = l.cars.filter { it.c != 32 }.map { it.taille }.average().toFloat().takeIf { !it.isNaN() } ?: 0f

    private fun para(lignes: List<Ligne>, corps: Float): Bloc {
        // lignes recousues : un tiret de fin de ligne suivi d'une minuscule disparait (mot coupe)
        val cars = ArrayList<Car>()
        for ((k, l) in lignes.withIndex()) {
            val c = l.cars.dropWhile { it.c == 32 }.dropLastWhile { it.c == 32 }
            if (k > 0 && cars.isNotEmpty()) {
                val dernier = cars.last()
                val suivant = c.firstOrNull()
                if (dernier.c == '-'.code && suivant != null && Character.isLowerCase(suivant.c) && cars.size > 1 &&
                    Character.isLetter(cars[cars.size - 2].c)) cars.removeAt(cars.size - 1)
                else cars += Car(32, dernier.taille, dernier.gras, dernier.italique)
            }
            cars += c
        }
        val texte = cars.joinToString("") { String(Character.toChars(it.c)) }.replace(Regex(" {2,}"), " ").trim()
        val lettres = cars.filter { it.c != 32 }
        val taille = lettres.map { it.taille }.average().toFloat()
        val toutGras = lettres.isNotEmpty() && lettres.count { it.gras } > 0.8f * lettres.size
        when {
            taille >= 1.7f * corps && texte.length <= 160 -> return Bloc.Titre(texte, 1)
            taille >= 1.25f * corps && texte.length <= 200 -> return Bloc.Titre(texte, 2)
            toutGras && lignes.size == 1 && texte.length <= 90 && taille >= 0.95f * corps &&
                texte.last() !in setOf('.', ',', ';') -> return Bloc.Titre(texte, 3)
        }
        // morceaux de meme style
        val morceaux = ArrayList<Morceau>()
        val sb = StringBuilder()
        var g = false; var i = false
        for (c in cars) {
            val cg = if (c.c == 32) g else c.gras
            val ci = if (c.c == 32) i else c.italique
            if (sb.isNotEmpty() && (cg != g || ci != i)) { morceaux += Morceau(sb.toString(), g, i); sb.clear() }
            g = cg; i = ci
            sb.appendCodePoint(c.c)
        }
        if (sb.isNotEmpty()) morceaux += Morceau(sb.toString(), g, i)
        val puce = (texte.isNotEmpty() && texte.first() in PUCES) || NUMERO.containsMatchIn(texte)
        return Bloc.Para(morceaux, puce)
    }
}

/** Reglages de la lecture fluide, gardes sur le telephone. */
private class ReglagesFluide(ctx: Context) {
    private val p = ctx.getSharedPreferences("lecture_fluide", Context.MODE_PRIVATE)
    var taille by mutableIntStateOf(p.getInt("taille", 18))
    var theme by mutableIntStateOf(p.getInt("theme", 0))            // 0 clair, 1 sepia, 2 sombre
    var justifie by mutableStateOf(p.getBoolean("justifie", true))
    var serif by mutableStateOf(p.getBoolean("serif", false))
    fun garder() { p.edit().putInt("taille", taille).putInt("theme", theme).putBoolean("justifie", justifie).putBoolean("serif", serif).apply() }
}

private val FONDS = listOf(Color(0xFFFFFFFF), Color(0xFFF6EEDC), Color(0xFF1E1E1E))
private val ENCRES = listOf(Color(0xFF222222), Color(0xFF433422), Color(0xFFDDDDDD))

/** Ecran de lecture fluide. fermer(page) : page a montrer en revenant (null : la page en cours). */
@OptIn(ExperimentalLayoutApi::class, ExperimentalMaterial3Api::class)
@Composable
fun LectureFluide(etat: EtatLecteur, nb: Int, fermer: (Int?) -> Unit) {
    val ctx = LocalContext.current
    val r = remember { ReglagesFluide(ctx) }
    val cache = remember(etat.doc, etat.doc.version) { mutableStateMapOf<Int, Fluide.PageFluide>() }
    val liste = rememberLazyListState(initialFirstVisibleItemIndex = etat.page.coerceIn(0, (nb - 1).coerceAtLeast(0)))
    val fond = FONDS[r.theme]; val encre = ENCRES[r.theme]
    val pageVue = liste.firstVisibleItemIndex
    Fenetre({ fermer(pageVue) }) {
        Surface(Modifier.fillMaxSize(), color = fond) {
            Column(Modifier.fillMaxSize()) {
                // barre du haut : retour et titre ; reglages en dessous, qui passent a la ligne (jamais tronques)
                Column(Modifier.fillMaxWidth().background(Color.White)) {
                    Row(Modifier.fillMaxWidth().padding(horizontal = 4.dp, vertical = 2.dp), verticalAlignment = Alignment.CenterVertically) {
                        IconButton(onClick = { fermer(pageVue) }) { Icon(Icons.AutoMirrored.Filled.ArrowBack, stringResource(R.string.retour)) }
                        Column(Modifier.weight(1f)) {
                            TexteAjuste(stringResource(R.string.lecture_fluide), 17.sp)
                            Text(etat.doc.nom, fontSize = 12.sp, color = Color.Gray, maxLines = 1,
                                overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis)
                        }
                    }
                    FlowRow(Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 2.dp),
                        horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                        OutlinedButton(onClick = { r.taille = (r.taille - 2).coerceAtLeast(12); r.garder() },
                            contentPadding = PaddingValues(horizontal = 12.dp)) { Text("A−", fontSize = 14.sp) }
                        OutlinedButton(onClick = { r.taille = (r.taille + 2).coerceAtMost(34); r.garder() },
                            contentPadding = PaddingValues(horizontal = 12.dp)) { Text("A+", fontSize = 18.sp) }
                        listOf(R.string.fluide_clair, R.string.fluide_sepia, R.string.fluide_sombre).forEachIndexed { k, t ->
                            FilterChip(selected = r.theme == k, onClick = { r.theme = k; r.garder() }, label = { Text(stringResource(t)) },
                                leadingIcon = { Box(Modifier.size(14.dp).background(FONDS[k], RoundedCornerShape(7.dp))
                                    .border(1.dp, Color.Gray, RoundedCornerShape(7.dp))) })
                        }
                        FilterChip(selected = r.justifie, onClick = { r.justifie = !r.justifie; r.garder() },
                            label = { Text(stringResource(R.string.fluide_justifier)) })
                        FilterChip(selected = r.serif, onClick = { r.serif = !r.serif; r.garder() },
                            label = { Text(stringResource(R.string.fluide_serif)) })
                    }
                    HorizontalDivider(color = Color(0xFFE2E2E2))
                }
                LazyColumn(Modifier.weight(1f).fillMaxWidth(), state = liste,
                    contentPadding = PaddingValues(horizontal = 18.dp, vertical = 12.dp)) {
                    items(nb, key = { it }) { n ->
                        PageLue(etat, n, r, encre, cache) { fermer(n) }
                    }
                }
            }
        }
    }
}

@Composable
private fun PageLue(etat: EtatLecteur, n: Int, r: ReglagesFluide, encre: Color,
                    cache: MutableMap<Int, Fluide.PageFluide>, allerPage: () -> Unit) {
    val dens = LocalDensity.current
    val page by produceState(cache[n], n, etat.doc.version) {
        if (value == null) value = try { etat.doc.texteFluide(n) } catch (e: Exception) {
            Journal.ecrire("lecture fluide", "page ${n + 1} : $e"); Fluide.PageFluide(emptyList(), true)
        }.also { cache[n] = it }
    }
    Column(Modifier.fillMaxWidth()) {
        // separateur : numero de la page ; le toucher ramene a cette page dans l'affichage normal
        Row(Modifier.fillMaxWidth().clickable { allerPage() }.padding(vertical = 10.dp), verticalAlignment = Alignment.CenterVertically) {
            HorizontalDivider(Modifier.weight(1f), color = encre.copy(alpha = 0.2f))
            Text("  " + stringResource(R.string.fluide_page, n + 1) + "  ", fontSize = 12.sp, color = encre.copy(alpha = 0.55f))
            HorizontalDivider(Modifier.weight(1f), color = encre.copy(alpha = 0.2f))
        }
        val p = page
        if (p == null) {
            Box(Modifier.fillMaxWidth().height(160.dp), contentAlignment = Alignment.Center) { CircularProgressIndicator(Modifier.size(28.dp)) }
            return@Column
        }
        if (p.scannee) { PageScannee(etat, n, encre, dens.density); return@Column }
        val famille = if (r.serif) FontFamily.Serif else FontFamily.Default
        val style = TextStyle(color = encre, fontSize = r.taille.sp, lineHeight = (r.taille * 1.5f).sp, fontFamily = famille,
            textAlign = if (r.justifie) TextAlign.Justify else TextAlign.Start, hyphens = Hyphens.Auto,
            lineBreak = LineBreak.Paragraph)
        for (b in p.blocs) when (b) {
            is Fluide.Bloc.Titre -> Text(b.texte, Modifier.padding(top = 14.dp, bottom = 6.dp), style = style.copy(
                fontSize = (r.taille * when (b.niveau) { 1 -> 1.45f; 2 -> 1.2f; else -> 1.05f }).sp,
                lineHeight = (r.taille * when (b.niveau) { 1 -> 1.8f; 2 -> 1.55f; else -> 1.4f }).sp,
                fontWeight = FontWeight.Bold, textAlign = TextAlign.Start, hyphens = Hyphens.None))
            is Fluide.Bloc.Para -> Text(texteStyle(b), Modifier.padding(bottom = 10.dp, start = if (b.puce) 8.dp else 0.dp),
                style = if (b.puce) style.copy(textAlign = TextAlign.Start) else style)
            is Fluide.Bloc.Img -> {
                val img = remember(b) { b.image.asImageBitmap() }
                Image(img, null, Modifier.fillMaxWidth().padding(vertical = 8.dp)
                    .widthIn(max = with(dens) { (b.image.width * 1.5f).toDp() }), contentScale = ContentScale.FillWidth)
            }
        }
    }
}

private fun texteStyle(b: Fluide.Bloc.Para): AnnotatedString = buildAnnotatedString {
    for (m in b.morceaux) {
        if (!m.gras && !m.italique) append(m.texte)
        else withStyle(SpanStyle(fontWeight = if (m.gras) FontWeight.Bold else null,
            fontStyle = if (m.italique) FontStyle.Italic else null)) { append(m.texte) }
    }
}

/** Page sans texte (scan) : son image, et la reconnaissance du texte proposee. */
@Composable
private fun PageScannee(etat: EtatLecteur, n: Int, encre: Color, densite: Float) {
    BoxWithConstraints(Modifier.fillMaxWidth()) {
        val largeur = (maxWidth.value * densite).toInt().coerceIn(200, 1600)
        val bm by produceState<Bitmap?>(null, n, etat.doc.version) { value = try { etat.doc.rendre(n, largeur) } catch (_: Exception) { null } }
        Column(Modifier.fillMaxWidth()) {
            Text(stringResource(R.string.fluide_scannee), fontSize = 13.sp, color = encre.copy(alpha = 0.7f))
            if (etat.doc.modifiable) TextButton(onClick = { etat.lectureFluide = false; etat.ocr = n }) {
                Text(stringResource(R.string.ocr_titre_menu))
            }
            bm?.let { Image(it.asImageBitmap(), null, Modifier.fillMaxWidth().padding(vertical = 6.dp), contentScale = ContentScale.FillWidth) }
        }
    }
}
