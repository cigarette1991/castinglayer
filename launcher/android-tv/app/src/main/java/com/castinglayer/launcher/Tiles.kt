package com.castinglayer.launcher

import android.content.Context
import android.util.TypedValue
import android.view.Gravity
import android.view.View
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.TextView

internal fun Context.dp(value: Int): Int =
    TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, value.toFloat(), resources.displayMetrics).toInt()

/** A big D-pad-focusable tile: icon above a label, scales up a little when focused. */
internal fun Context.tile(iconRes: Int, label: CharSequence, onClick: () -> Unit): View {
    val tile = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        gravity = Gravity.CENTER
        isFocusable = true
        isClickable = true
        setBackgroundResource(R.drawable.tile_bg)
        setPadding(dp(16), dp(16), dp(16), dp(16))
        setOnClickListener { onClick() }
        setOnFocusChangeListener { v, hasFocus ->
            val s = if (hasFocus) 1.08f else 1f
            v.animate().scaleX(s).scaleY(s).setDuration(120).start()
        }
    }
    tile.addView(ImageView(this).apply { setImageResource(iconRes) }, LinearLayout.LayoutParams(dp(96), dp(96)))
    tile.addView(TextView(this).apply {
        text = label
        textSize = 26f
        setTextColor(getColor(R.color.text))
        gravity = Gravity.CENTER
        setPadding(0, dp(16), 0, 0)
    })
    return tile
}

/** A full-width focusable list row used by the Casts and Inputs screens. */
internal fun Context.row(title: CharSequence, detail: CharSequence?, onClick: (() -> Unit)?): View {
    val row = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        isFocusable = true
        isClickable = onClick != null
        setBackgroundResource(R.drawable.row_bg)
        setPadding(dp(24), dp(16), dp(24), dp(16))
        if (onClick != null) setOnClickListener { onClick() }
    }
    row.addView(TextView(this).apply {
        text = title
        textSize = 22f
        setTextColor(getColor(R.color.text))
    })
    if (!detail.isNullOrEmpty()) {
        row.addView(TextView(this).apply {
            text = detail
            textSize = 16f
            setTextColor(getColor(R.color.text_dim))
        })
    }
    row.layoutParams = LinearLayout.LayoutParams(
        LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT
    ).apply { bottomMargin = dp(12) }
    return row
}
