package com.castinglayer.launcher

import android.content.Context
import android.net.ConnectivityManager
import android.os.Build
import android.provider.Settings
import java.net.Inet4Address

internal object Net {
    /** The name Cast senders show for this TV, e.g. "Living Room TV". */
    fun deviceName(context: Context): String? =
        Settings.Global.getString(context.contentResolver, "device_name")
            ?: Build.MODEL

    /** The TV's IPv4 address on the active network, or null when offline. */
    fun ipAddress(context: Context): String? {
        val cm = context.getSystemService(ConnectivityManager::class.java) ?: return null
        val props = cm.getLinkProperties(cm.activeNetwork) ?: return null
        return props.linkAddresses
            .map { it.address }
            .firstOrNull { it is Inet4Address && !it.isLoopbackAddress }
            ?.hostAddress
    }
}
