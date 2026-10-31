package io.github.philouelchapo.philpdf

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder

/**
 * Pendant que vous acceptez dans le navigateur, PhilPDF reste eveille (sinon Android le met en sommeil :
 * la page du navigateur ne trouve plus PhilPDF et le reseau lui est coupe). Une notification le signale ;
 * la toucher ramene a PhilPDF.
 */
class AttenteConnexion : Service() {
    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val nm = getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(NotificationChannel(CANAL, getString(R.string.canal_connexion), NotificationManager.IMPORTANCE_LOW))
        val retour = PendingIntent.getActivity(this, 0,
            Intent(this, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_REORDER_TO_FRONT or Intent.FLAG_ACTIVITY_SINGLE_TOP),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        val n = Notification.Builder(this, CANAL)
            .setSmallIcon(R.drawable.logo)
            .setContentTitle(getString(R.string.app_name))
            .setContentText(intent?.getStringExtra("texte") ?: getString(R.string.attente_navigateur))
            .setContentIntent(retour)
            .setOngoing(true)
            .build()
        if (Build.VERSION.SDK_INT >= 29) startForeground(1, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC) else startForeground(1, n)
        return START_NOT_STICKY
    }

    companion object {
        private const val CANAL = "connexion"

        fun demarrer(ctx: Context, texte: String) {
            try { ctx.startForegroundService(Intent(ctx, AttenteConnexion::class.java).putExtra("texte", texte)) } catch (_: Exception) { }
        }

        fun arreter(ctx: Context) {
            try { ctx.stopService(Intent(ctx, AttenteConnexion::class.java)) } catch (_: Exception) { }
        }
    }
}
