package com.typheye.tcarkit.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Logout
import androidx.compose.material.icons.filled.WarningAmber
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp

@Composable
internal fun SettingsScreen(host: String, onDisconnect: () -> Unit) {
    var confirmDisconnect by remember { mutableStateOf(false) }
    PageBackground {
        Column(Modifier.fillMaxSize().padding(30.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
            Text("Settings", style = MaterialTheme.typography.headlineMedium, color = Color.White)
            DataCard("Core host", host)
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
