package io.github.philouelchapo.philpdf

import android.content.Context

/** Messages du moteur dans la langue du telephone (le moteur n'a pas de Context sous la main). */
object Textes {
    @Volatile private var app: Context? = null

    fun demarrer(ctx: Context) { app = ctx.applicationContext }

    fun t(id: Int, vararg args: Any?): String =
        app?.getString(id, *args) ?: ("#$id " + args.joinToString(" "))
}
