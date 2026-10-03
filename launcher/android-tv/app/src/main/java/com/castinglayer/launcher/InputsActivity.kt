package com.castinglayer.launcher

import android.app.Activity
import android.content.ActivityNotFoundException
import android.content.Intent
import android.media.tv.TvContract
import android.media.tv.TvInputInfo
import android.media.tv.TvInputManager
import android.os.Bundle
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast

/**
 * Lists the TV's physical inputs (HDMI, composite, …) and switches to one.
 *
 * Switching works by asking the system TV app to view the input's passthrough
 * channel URI, which is the documented way for third-party apps to tune an input.
 */
class InputsActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_list)
        findViewById<TextView>(R.id.title).setText(R.string.inputs_title)
    }

    override fun onResume() {
        super.onResume()
        val rows = findViewById<LinearLayout>(R.id.rows)
        rows.removeAllViews()

        val tvm = getSystemService(TvInputManager::class.java)
        val inputs = tvm?.tvInputList.orEmpty()
            .filter { it.isPassthroughInput && !it.isHidden(this) }
            .sortedWith(compareBy({ typeOrder(it.type) }, { it.loadLabel(this).toString() }))

        if (inputs.isEmpty()) {
            findViewById<TextView>(R.id.body).setText(R.string.inputs_none)
            rows.addView(row("Open TV input settings", null) { openInputSettings() })
        } else {
            findViewById<TextView>(R.id.body).text = ""
            for (info in inputs) {
                val label = info.loadCustomLabel(this)?.toString()?.takeIf { it.isNotBlank() }
                    ?: info.loadLabel(this).toString()
                rows.addView(row(label, typeName(info.type)) { switchTo(info) })
            }
        }
        rows.getChildAt(0)?.requestFocus()
    }

    private fun switchTo(info: TvInputInfo) {
        val uri = TvContract.buildChannelUriForPassthroughInput(info.id)
        try {
            startActivity(Intent(Intent.ACTION_VIEW, uri).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        } catch (e: ActivityNotFoundException) {
            Toast.makeText(this, R.string.open_failed, Toast.LENGTH_SHORT).show()
        }
    }

    private fun openInputSettings() {
        // Not every TV has a dedicated inputs screen; fall back to the main settings.
        for (action in listOf("android.settings.TV_INPUT_SETTINGS", android.provider.Settings.ACTION_SETTINGS)) {
            try {
                startActivity(Intent(action))
                return
            } catch (_: ActivityNotFoundException) {
            }
        }
    }

    private fun typeOrder(type: Int) = if (type == TvInputInfo.TYPE_HDMI) 0 else 1

    private fun typeName(type: Int) = when (type) {
        TvInputInfo.TYPE_HDMI -> "HDMI"
        TvInputInfo.TYPE_COMPONENT -> "Component"
        TvInputInfo.TYPE_COMPOSITE -> "Composite"
        TvInputInfo.TYPE_SVIDEO -> "S-Video"
        TvInputInfo.TYPE_SCART -> "SCART"
        TvInputInfo.TYPE_VGA -> "VGA"
        TvInputInfo.TYPE_DVI -> "DVI"
        TvInputInfo.TYPE_DISPLAY_PORT -> "DisplayPort"
        TvInputInfo.TYPE_TUNER -> "Antenna / cable"
        else -> "Input"
    }
}
