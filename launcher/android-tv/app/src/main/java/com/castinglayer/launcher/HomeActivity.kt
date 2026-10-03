package com.castinglayer.launcher

import android.app.Activity
import android.content.ActivityNotFoundException
import android.content.Intent
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.text.format.DateFormat
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import java.util.Date

/**
 * The TV's home screen: four tiles (Jellyfin, Casts, Settings, Inputs).
 *
 * Registered for the HOME category, so once the stock launcher is disabled
 * (see ../tv.sh set-home) the Home button lands here.
 */
class HomeActivity : Activity() {

    private val handler = Handler(Looper.getMainLooper())
    private lateinit var clock: TextView
    private val tick = object : Runnable {
        override fun run() {
            clock.text = DateFormat.getTimeFormat(this@HomeActivity).format(Date())
            handler.postDelayed(this, 15_000)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_home)
        clock = findViewById(R.id.clock)

        val tiles = findViewById<LinearLayout>(R.id.tiles)
        val entries = listOf(
            Tile(R.drawable.ic_jellyfin, R.string.tile_jellyfin) { openJellyfin() },
            Tile(R.drawable.ic_casts, R.string.tile_casts) { startActivity(Intent(this, CastsActivity::class.java)) },
            Tile(R.drawable.ic_settings, R.string.tile_settings) { openSettings() },
            Tile(R.drawable.ic_inputs, R.string.tile_inputs) { startActivity(Intent(this, InputsActivity::class.java)) },
        )
        for ((icon, label, action) in entries) {
            val view = tile(icon, getString(label), action)
            tiles.addView(view, LinearLayout.LayoutParams(0, dp(260), 1f).apply {
                marginStart = dp(16)
                marginEnd = dp(16)
            })
        }
        tiles.getChildAt(0).requestFocus()
    }

    override fun onResume() {
        super.onResume()
        findViewById<TextView>(R.id.subtitle).text = Net.deviceName(this) ?: ""
        handler.post(tick)
    }

    override fun onPause() {
        super.onPause()
        handler.removeCallbacks(tick)
    }

    // We are the home screen: Back has nowhere to go.
    @Deprecated("Deprecated in Java")
    override fun onBackPressed() {}

    private fun openJellyfin() {
        val launch = packageManager.getLeanbackLaunchIntentForPackage(JELLYFIN)
            ?: packageManager.getLaunchIntentForPackage(JELLYFIN)
        if (launch != null) {
            startActivity(launch)
            return
        }
        Toast.makeText(this, R.string.jellyfin_missing, Toast.LENGTH_LONG).show()
    }

    private fun openSettings() {
        tryStart(Intent(Settings.ACTION_SETTINGS))
    }

    private fun tryStart(intent: Intent) {
        try {
            startActivity(intent)
        } catch (e: ActivityNotFoundException) {
            Toast.makeText(this, R.string.open_failed, Toast.LENGTH_SHORT).show()
        }
    }

    private data class Tile(val icon: Int, val label: Int, val action: () -> Unit)

    companion object {
        const val JELLYFIN = "org.jellyfin.androidtv"
    }
}
