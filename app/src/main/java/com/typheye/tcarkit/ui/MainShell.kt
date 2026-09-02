package com.typheye.tcarkit.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Menu
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.Speed
import androidx.compose.material.icons.filled.Videocam
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.FilledTonalIconButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.unit.dp
import com.typheye.tcarkit.TelemetryState

private enum class Page { Drive, Home, Performance, Settings }

@Composable
internal fun MainShell(coreHost: String, telemetry: TelemetryState, onDisconnect: () -> Unit) {
    var page by rememberSaveable { mutableStateOf(Page.Drive) }
    var menuOpen by remember { mutableStateOf(false) }
    var videoFps by remember { mutableFloatStateOf(0f) }
    var frameDelayMs by remember { mutableFloatStateOf(0f) }

    Box(Modifier.fillMaxSize()) {
        when (page) {
            Page.Drive -> VisionScreen(coreHost, telemetry, { videoFps = it }, { frameDelayMs = it })
            Page.Home -> HomeScreen(telemetry)
            Page.Performance -> PerformanceScreen(coreHost, telemetry, videoFps)
            Page.Settings -> SettingsScreen(coreHost, onDisconnect)
        }
        Box(Modifier.fillMaxSize().windowInsetsPadding(WindowInsets.safeDrawing)) {
            FilledTonalIconButton(
                onClick = { menuOpen = true },
                modifier = Modifier.align(Alignment.BottomStart).padding(12.dp),
                colors = IconButtonDefaults.filledTonalIconButtonColors(
                    containerColor = Color(0xB8FFFFFF),
                    contentColor = Color(0xFF15181D),
                ),
            ) {
                Icon(Icons.Default.Menu, "Menu")
            }
            DropdownMenu(
                expanded = menuOpen,
                onDismissRequest = { menuOpen = false },
                modifier = Modifier.background(Color(0xF215181D)),
            ) {
                NavigationItem(Page.Drive, page, Icons.Default.Videocam) { page = it; menuOpen = false }
                NavigationItem(Page.Home, page, Icons.Default.Home) { page = it; menuOpen = false }
                NavigationItem(Page.Performance, page, Icons.Default.Speed) { page = it; menuOpen = false }
                NavigationItem(Page.Settings, page, Icons.Default.Settings) { page = it; menuOpen = false }
            }
        }
        if (telemetry.available && telemetry.batteryPercent < 10f) LowBatteryOverlay()
    }
}

@Composable
private fun NavigationItem(page: Page, selected: Page, icon: ImageVector, onClick: (Page) -> Unit) {
    DropdownMenuItem(
        text = { Text(page.name) },
        onClick = { onClick(page) },
        leadingIcon = {
            Icon(
                icon,
                null,
                tint = if (page == selected) MaterialTheme.colorScheme.primary else Color.White,
            )
        },
    )
}
