package io.github.philouelchapo.philpdf

import android.content.Context
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * Journal de PhilPDF sur le telephone (comme Aide > Journal sous Windows) : connexions aux comptes,
 * synchronisation, mises a jour, erreurs. Jetons, codes et mots de passe masques. Taille limitee.
 */
object Journal {
    private const val TAILLE_MAX = 512 * 1024
    private var dossier: File? = null

    fun demarrer(ctx: Context) {
        dossier = ctx.applicationContext.filesDir
        ecrire("démarrage", "PhilPDF Android ${BuildConfig.VERSION_NAME} (Android ${android.os.Build.VERSION.RELEASE}, " +
            "${android.os.Build.MANUFACTURER} ${android.os.Build.MODEL})")
        // version changee depuis le dernier lancement : la mise a jour s'est bien faite
        val f = File(ctx.filesDir, "derniere_version.txt")
        val avant = if (f.exists()) f.readText().trim() else ""
        if (avant.isNotEmpty() && avant != BuildConfig.VERSION_NAME) ecrire("mise à jour", "$avant -> ${BuildConfig.VERSION_NAME} : installée")
        try { f.writeText(BuildConfig.VERSION_NAME) } catch (_: Exception) { }
    }

    fun fichier(ctx: Context) = File(ctx.filesDir, "journal.txt")

    /** Masque ce qui ressemble a un secret (jeton, code d'autorisation, mot de passe). */
    private fun masquer(t: String) = t
        .replace(Regex("(?i)(access_token|refresh_token|code|password|mot_de_passe|client_secret|Bearer)([\"=:\\s]+)[A-Za-z0-9._~+/\\-]{8,}"), "$1$2•••")

    @Synchronized
    fun ecrire(source: String, texte: String) {
        val d = dossier ?: return
        try {
            val f = File(d, "journal.txt")
            if (f.exists() && f.length() > TAILLE_MAX) {
                val garde = f.readText().takeLast(TAILLE_MAX / 2)
                f.writeText(garde.substringAfter('\n'))
            }
            val h = SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.FRANCE).format(Date())
            f.appendText("$h  [$source]  ${masquer(texte)}\n")
        } catch (_: Exception) { }                 // le journal ne doit jamais faire echouer une operation
    }

    fun lire(ctx: Context): String = try { fichier(ctx).takeIf { it.exists() }?.readText() ?: "" } catch (_: Exception) { "" }

    fun effacer(ctx: Context) { fichier(ctx).delete() }
}
