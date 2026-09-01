package com.typheye.tcarkit

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.core.view.WindowCompat
import androidx.lifecycle.viewmodel.compose.viewModel

private val TCarDark = darkColorScheme(
    background = Color(0xFF0B0D10), surface = Color(0xFF15181D),
    surfaceVariant = Color(0xFF20242B), primary = Color(0xFFFF6A00),
    secondary = Color(0xFFF0B429),
)

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        WindowCompat.setDecorFitsSystemWindows(window, false)
        setContent {
            MaterialTheme(colorScheme = TCarDark) {
                val connection: ConnectionViewModel = viewModel()
                TCarKitApp(connection)
            }
        }
    }
}

@Composable
private fun TCarKitApp(connection: ConnectionViewModel) {
    val state = connection.state
    Box(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background)) {
        when (state) {
            is ConnectionState.Connected -> MainShell(state.coreHost, connection::disconnect)
            else -> ConnectionScreen(state, connection::connect)
        }
    }
}

@Composable
private fun ConnectionScreen(state: ConnectionState, onConnect: (String, String) -> Unit) {
    var username by rememberSaveable { mutableStateOf("tcar") }
    var password by rememberSaveable { mutableStateOf("admin123") }
    val busy = state is ConnectionState.Discovering
    Box(
        Modifier.fillMaxSize().background(Color(0xFF0B0D10)),
        contentAlignment = Alignment.Center,
    ) {
        Column(
            Modifier.windowInsetsPadding(WindowInsets.safeDrawing)
                .widthIn(max = 380.dp).padding(horizontal = 24.dp, vertical = 16.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            Image(
                painterResource(R.drawable.icon_logo), contentDescription = "tCarKit",
                contentScale = ContentScale.Fit,
                modifier = Modifier.size(72.dp).clip(RoundedCornerShape(18.dp)),
            )
            Text("tCarKit", style = MaterialTheme.typography.headlineSmall, color = Color.White)
            OutlinedTextField(
                username, { username = it }, label = { Text("Username") },
                singleLine = true, enabled = !busy, modifier = Modifier.fillMaxWidth(),
            )
            OutlinedTextField(
                password, { password = it }, label = { Text("Password") },
                singleLine = true, visualTransformation = PasswordVisualTransformation(),
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
                enabled = !busy, modifier = Modifier.fillMaxWidth(),
            )
            if (state is ConnectionState.Failed) {
                Text(state.message, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)
            }
            Button(
                onClick = { onConnect(username.trim(), password) },
                enabled = !busy && username.isNotBlank() && password.isNotEmpty(),
                modifier = Modifier.fillMaxWidth().height(48.dp),
            ) {
                if (busy) CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp, color = Color.White)
                else Text("Connect")
            }
        }
    }
}

@Composable
private fun MainShell(coreHost: String, onDisconnect: () -> Unit) {
    var page by rememberSaveable { mutableStateOf("Drive") }
    Box(Modifier.fillMaxSize()) {
        when (page) {
            "Drive" -> DriveSurface(coreHost)
            "Home" -> PlaceholderSurface("HOME", coreHost)
            "Performance" -> PlaceholderSurface("PERFORMANCE", coreHost)
            else -> PlaceholderSurface("SETTINGS", coreHost)
        }
        Row(
            Modifier.fillMaxSize().windowInsetsPadding(WindowInsets.safeDrawing),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            NavigationRail(containerColor = Color(0xB815181D)) {
                Spacer(Modifier.weight(1f))
                listOf("Drive", "Home", "Performance", "Settings").forEach { item ->
                    NavigationRailItem(
                        selected = page == item, onClick = { page = item },
                        icon = { Text(item.take(1)) }, label = { Text(item) },
                    )
                }
                Spacer(Modifier.weight(1f))
                TextButton(onClick = onDisconnect) { Text("Exit") }
            }
        }
    }
}

@Composable
private fun DriveSurface(coreHost: String) {
    Box(Modifier.fillMaxSize().background(Color.Black), contentAlignment = Alignment.Center) {
        Text("VIDEO  |  $coreHost", color = Color.White.copy(alpha = .72f), style = MaterialTheme.typography.titleMedium)
    }
}

@Composable
private fun PlaceholderSurface(title: String, coreHost: String) {
    Box(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background), contentAlignment = Alignment.Center) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Text(title, color = Color.White, style = MaterialTheme.typography.headlineMedium)
            Text(coreHost, color = Color.White.copy(alpha = .55f))
        }
    }
}
