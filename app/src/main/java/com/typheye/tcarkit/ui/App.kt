package com.typheye.tcarkit.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import com.typheye.tcarkit.ConnectionState
import com.typheye.tcarkit.ConnectionViewModel

val TCarDark = darkColorScheme(
    background = Color(0xFF0B0D10),
    surface = Color(0xFF15181D),
    surfaceVariant = Color(0xFF20242B),
    primary = Color(0xFFFF6A00),
    secondary = Color(0xFFF0B429),
)

@Composable
fun TCarKitApp(connection: ConnectionViewModel) {
    var showSplash by rememberSaveable { mutableStateOf(true) }
    Box(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background)) {
        if (showSplash) {
            BrandSplashScreen { showSplash = false }
        } else {
            when (val state = connection.state) {
                is ConnectionState.Connected -> MainShell(
                    state.coreHost,
                    connection.telemetry,
                    connection::disconnect,
                )
                else -> ConnectionScreen(state, connection::connect)
            }
        }
    }
}
