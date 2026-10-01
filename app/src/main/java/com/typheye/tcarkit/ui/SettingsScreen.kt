package com.typheye.tcarkit.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Logout
import androidx.compose.material.icons.filled.WarningAmber
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp

@Composable
internal fun SettingsScreen(
    host: String,
    showDebugConsole: Boolean,
    onShowDebugConsoleChange: (Boolean) -> Unit,
    onDisconnect: () -> Unit,
) {
    var confirmDisconnect by remember { mutableStateOf(false) }
    PageBackground {
        Column(Modifier.fillMaxSize().padding(30.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
            Text("Settings", style = MaterialTheme.typography.headlineMedium, color = Color.White)
            DataCard("Core host", host)
            SettingToggle(
                title = "Show Debug Console",
                description = "Overlay FPS and frame delay on the Drive view.",
                checked = showDebugConsole,
                onCheckedChange = onShowDebugConsoleChange,
            )
            OutlinedButton(onClick = { confirmDisconnect = true }) {
                Icon(Icons.Default.Logout, null)
                Spacer(Modifier.width(8.dp))
                Text("Disconnect")
            }
        }
        if (confirmDisconnect) {
            AlertDialog(
                onDismissRequest = { confirmDisconnect = false },
                icon = {
                    Icon(
                        Icons.Default.WarningAmber,
                        null,
                        tint = MaterialTheme.colorScheme.primary,
                    )
                },
                title = { Text("Disconnect from vehicle?") },
                text = { Text("The current control and telemetry session will be closed.") },
                confirmButton = {
                    TextButton(onClick = {
                        confirmDisconnect = false
                        onDisconnect()
                    }) {
                        Text("Disconnect", color = MaterialTheme.colorScheme.primary)
                    }
                },
                dismissButton = {
                    TextButton(onClick = { confirmDisconnect = false }) {
                        Text("Cancel")
                    }
                },
                containerColor = Color(0xFF171A1F),
                tonalElevation = 8.dp,
            )
        }
    }
}

@Composable
private fun SettingToggle(
    title: String,
    description: String,
    checked: Boolean,
    onCheckedChange: (Boolean) -> Unit,
) {
    Surface(Modifier.fillMaxWidth(), color = Color(0xFF171B20), shape = RoundedCornerShape(6.dp)) {
        Row(
            Modifier.fillMaxWidth().padding(16.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(Modifier.weight(1f)) {
                Text(title, color = Color.White, style = MaterialTheme.typography.titleMedium)
                Spacer(Modifier.height(4.dp))
                Text(description, color = Color(0xFF9FA6AF), style = MaterialTheme.typography.labelMedium)
            }
            Spacer(Modifier.width(16.dp))
            Switch(checked = checked, onCheckedChange = onCheckedChange)
        }
    }
}
