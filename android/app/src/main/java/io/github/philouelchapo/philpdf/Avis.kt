package io.github.philouelchapo.philpdf

import android.app.Activity
import android.content.Context
import android.content.ContextWrapper

/**
 * Demande de note Google Play, la fenetre officielle de Google (« Noter PhilPDF », etoiles, sans quitter l'appli).
 * Version Google Play seulement, une seule fois : apres 5 enregistrements reussis et au moins 3 jours d'utilisation,
 * jamais au milieu d'un travail. Google decide lui-meme de l'afficher ou non (il limite le nombre de demandes) ;
 * rien n'est envoye par PhilPDF. Sinon : Aide > Noter PhilPDF, a tout moment.
 */
object Avis {
    private const val SEUIL = 5
    private const val JOURS = 3L

    fun apresEnregistrement(ctx: Context) {
        if (!BuildConfig.PLAY_STORE) return
        val p = ctx.getSharedPreferences("avis", Context.MODE_PRIVATE)
        if (p.getBoolean("demande", false)) return
        val n = p.getInt("enregistrements", 0) + 1
        p.edit().putInt("enregistrements", n).apply()
        if (n < SEUIL) return
        val installe = try { ctx.packageManager.getPackageInfo(ctx.packageName, 0).firstInstallTime } catch (_: Exception) { 0L }
        if (System.currentTimeMillis() - installe < JOURS * 24 * 3600 * 1000) return
        val activite = activite(ctx) ?: return
        p.edit().putBoolean("demande", true).apply()
        try {
            val gestion = com.google.android.play.core.review.ReviewManagerFactory.create(activite)
            gestion.requestReviewFlow().addOnCompleteListener { t ->
                if (t.isSuccessful) {
                    Journal.ecrire("avis", "demande de note Google Play proposée (après $n enregistrements)")
                    gestion.launchReviewFlow(activite, t.result)
                } else Journal.ecrire("avis", "demande de note indisponible : ${t.exception?.message}")
            }
        } catch (e: Exception) {
            Journal.ecrire("avis", "demande de note impossible : $e")
        }
    }

    private fun activite(c: Context): Activity? {
        var x: Context? = c
        while (x != null) {
            if (x is Activity) return x
            x = (x as? ContextWrapper)?.baseContext
        }
        return null
    }
}
