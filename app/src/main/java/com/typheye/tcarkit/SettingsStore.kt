package com.typheye.tcarkit

import android.content.Context
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue

/** Persistent, app-wide user preferences. */
class SettingsStore(context: Context) {
    private val preferences =
        context.applicationContext.getSharedPreferences(PREFERENCES_NAME, Context.MODE_PRIVATE)

    var showDebugConsole by mutableStateOf(preferences.getBoolean(KEY_SHOW_DEBUG_CONSOLE, false))
        private set

    fun updateShowDebugConsole(enabled: Boolean) {
        showDebugConsole = enabled
        preferences.edit().putBoolean(KEY_SHOW_DEBUG_CONSOLE, enabled).apply()
    }

    private companion object {
        const val PREFERENCES_NAME = "tcar_settings"
        const val KEY_SHOW_DEBUG_CONSOLE = "show_debug_console"
    }
}
