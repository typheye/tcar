package com.typheye.tcarkit.ui

import android.app.Activity
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.WarningAmber
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
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
    var confirmExit by rememberSaveable { mutableStateOf(false) }
    val activity = LocalContext.current as? Activity
    val lowBatteryLocked = connection.state is ConnectionState.Connected &&
        connection.telemetry.available && connection.telemetry.batteryPercent < 10f

    BackHandler {
        if (!lowBatteryLocked && !showSplash) confirmExit = true
    }
    Box(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background)) {
        if (showSplash) {
            BrandSplashScreen { showSplash = false }
        } else {
            when (val state = connection.state) {
                is ConnectionState.Connected -> MainShell(
                    state.coreHost,
                    connection.telemetry,
                    connection.performance,
                    connection::disconnect,
                )
                else -> ConnectionScreen(state, connection::connect)
            }
        }
        if (confirmExit) {
            AlertDialog(
                onDismissRequest = { confirmExit = false },
                icon = {
                    Icon(Icons.Default.WarningAmber, null, tint = MaterialTheme.colorScheme.primary)
                },
                title = { Text("Exit tCarKit?") },
                text = { Text("Vehicle monitoring will stop when the application closes.") },
                confirmButton = {
                    TextButton(onClick = {
                        confirmExit = false
                        activity?.finishAndRemoveTask()
                    }) {
                        Text("Exit", color = MaterialTheme.colorScheme.primary)
                    }
                },
                dismissButton = {
                    TextButton(onClick = { confirmExit = false }) { Text("Cancel") }
                },
                containerColor = Color(0xFF171A1F),
                tonalElevation = 8.dp,
            )
        }
    }
}
