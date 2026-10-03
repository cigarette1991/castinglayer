package com.castinglayer.launcher

import android.app.Activity
import android.os.Bundle
import android.widget.LinearLayout
import android.widget.TextView

/**
 * Cast is built into the TV's system, so there is nothing to launch.
 * This screen just confirms the TV is ready and shows what to look for on the sender.
 */
class CastsActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_list)
        findViewById<TextView>(R.id.title).setText(R.string.casts_title)
        findViewById<TextView>(R.id.body).text = getText(R.string.casts_body)
    }

    override fun onResume() {
        super.onResume()
        val rows = findViewById<LinearLayout>(R.id.rows)
        rows.removeAllViews()
        rows.addView(row("Cast name", Net.deviceName(this) ?: "unknown", null))
        rows.addView(row("IP address", Net.ipAddress(this) ?: "not connected", null))
        rows.getChildAt(0).requestFocus()
    }
}
