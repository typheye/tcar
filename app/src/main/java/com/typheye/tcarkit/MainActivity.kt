package com.typheye.tcarkit

import android.graphics.Paint
import android.os.Bundle
import android.text.Editable
import android.text.InputType
import android.text.TextWatcher
import android.view.inputmethod.EditorInfo
import android.view.inputmethod.InputMethodManager
import android.widget.EditText
import android.view.WindowManager
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.interaction.FocusInteraction
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.nativeCanvas
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.graphics.drawscope.rotate
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import androidx.lifecycle.viewmodel.compose.viewModel
import kotlinx.coroutines.launch
import kotlin.math.roundToInt
import kotlin.math.abs
import kotlin.math.floor
import kotlin.math.cos
import kotlin.math.sin
import kotlin.math.PI

private val TCarDark = darkColorScheme(
    background = Color(0xFF0B0D10), surface = Color(0xFF15181D),
    surfaceVariant = Color(0xFF20242B), primary = Color(0xFFFF6A00),
    secondary = Color(0xFFF0B429),
)

private enum class Page { Drive, Home, Performance, Settings }

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        WindowCompat.setDecorFitsSystemWindows(window, false)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        WindowInsetsControllerCompat(window, window.decorView).apply {
            hide(WindowInsetsCompat.Type.systemBars())
            systemBarsBehavior = WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
        }
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
    Box(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background)) {
        when (val state = connection.state) {
            is ConnectionState.Connected -> MainShell(
                state.coreHost, connection.telemetry, connection::disconnect,
            )
            else -> ConnectionScreen(state, connection::connect)
        }
    }
}

@Composable
private fun ConnectionScreen(state: ConnectionState, onConnect: (String, String) -> Unit) {
    var username by rememberSaveable { mutableStateOf("tcar") }
    var password by rememberSaveable { mutableStateOf("admin123") }
    var dismissedFailure by rememberSaveable { mutableStateOf<String?>(null) }
    val busy = state is ConnectionState.Discovering
    val context = LocalContext.current
    val rootView = LocalView.current
    var passwordField by remember { mutableStateOf<EditText?>(null) }
    val submit = { if (!busy && username.isNotBlank() && password.isNotEmpty()) {
        rootView.findFocus()?.clearFocus()
        context.getSystemService(InputMethodManager::class.java)?.hideSoftInputFromWindow(rootView.windowToken, 0)
        dismissedFailure = null
        onConnect(username.trim(), password)
    } }
    Box(Modifier.fillMaxSize().background(Color(0xFF0B0D10)), contentAlignment = Alignment.Center) {
        Column(Modifier.windowInsetsPadding(WindowInsets.safeDrawing).widthIn(max = 380.dp)
            .padding(horizontal = 24.dp, vertical = 16.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Image(painterResource(R.drawable.icon_logo), "tCarKit", contentScale = ContentScale.Fit,
                modifier = Modifier.size(64.dp).clip(RoundedCornerShape(16.dp)))
            Text("tCarKit", style = MaterialTheme.typography.headlineSmall, color = Color.White)
            NativeLoginField(
                value = username,
                onValueChange = { username = it },
                hint = "Username",
                imeAction = EditorInfo.IME_ACTION_NEXT,
                enabled = !busy,
                onEditorAction = {
                    passwordField?.requestFocus()
                    passwordField?.let {
                        context.getSystemService(InputMethodManager::class.java)?.showSoftInput(it, InputMethodManager.SHOW_IMPLICIT)
                    }
                },
            )
            NativeLoginField(
                value = password,
                onValueChange = { password = it },
                hint = "Password",
                password = true,
                imeAction = EditorInfo.IME_ACTION_DONE,
                enabled = !busy,
                onViewCreated = { passwordField = it },
                onEditorAction = submit,
            )
            Button(onClick = submit, enabled = !busy && username.isNotBlank() && password.isNotEmpty(),
                modifier = Modifier.fillMaxWidth().height(48.dp)) {
                if (busy) CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp, color = Color.White)
                else Text("Connect")
            }
        }
        val failure = state as? ConnectionState.Failed
        if (failure != null && failure.message != dismissedFailure) {
            ConnectionErrorDialog(
                message = failure.message,
                onDismiss = { dismissedFailure = failure.message },
            )
        }
    }
}

@Composable
private fun ConnectionErrorDialog(message: String, onDismiss: () -> Unit) {
    Dialog(
        onDismissRequest = onDismiss,
        properties = DialogProperties(dismissOnBackPress = true, dismissOnClickOutside = true),
    ) {
        Surface(
            color = Color(0xFF171A1F),
            contentColor = Color.White,
            shape = RoundedCornerShape(8.dp),
            tonalElevation = 8.dp,
            shadowElevation = 16.dp,
            modifier = Modifier.widthIn(min = 320.dp, max = 420.dp),
        ) {
            Column {
                Row(
                    modifier = Modifier.padding(start = 24.dp, top = 22.dp, end = 24.dp, bottom = 16.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(14.dp),
                ) {
                    Box(
                        Modifier.size(42.dp).background(Color(0x26FF6A00), CircleShape),
                        contentAlignment = Alignment.Center,
                    ) {
                        Icon(Icons.Default.ErrorOutline, null, tint = MaterialTheme.colorScheme.primary)
                    }
                    Text("Connection failed", style = MaterialTheme.typography.titleLarge)
                }
                Text(
                    message,
                    color = Color(0xFFCED1D6),
                    style = MaterialTheme.typography.bodyLarge,
                    modifier = Modifier.padding(horizontal = 24.dp, vertical = 4.dp),
                )
                HorizontalDivider(
                    modifier = Modifier.padding(top = 22.dp),
                    color = Color(0xFF30343B),
                )
                Row(
                    modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 10.dp),
                    horizontalArrangement = Arrangement.End,
                ) {
                    TextButton(onClick = onDismiss) {
                        Text("OK", color = MaterialTheme.colorScheme.primary)
                    }
                }
            }
        }
    }
}

@Composable
private fun NativeLoginField(
    value: String,
    onValueChange: (String) -> Unit,
    hint: String,
    imeAction: Int,
    enabled: Boolean,
    password: Boolean = false,
    onViewCreated: (EditText) -> Unit = {},
    onEditorAction: () -> Unit,
) {
    val currentOnValueChange by rememberUpdatedState(onValueChange)
    val currentOnEditorAction by rememberUpdatedState(onEditorAction)
    val interactionSource = remember { MutableInteractionSource() }
    val coroutineScope = rememberCoroutineScope()
    var focusInteraction by remember { mutableStateOf<FocusInteraction.Focus?>(null) }
    Box(Modifier.fillMaxWidth()) {
        OutlinedTextField(
            value = value,
            onValueChange = {},
            label = { Text(hint) },
            enabled = enabled,
            readOnly = true,
            singleLine = true,
            visualTransformation = if (password) PasswordVisualTransformation() else VisualTransformation.None,
            interactionSource = interactionSource,
            modifier = Modifier.fillMaxWidth(),
        )
        AndroidView(
            factory = { context ->
                EditText(context).apply {
                    background = null
                    alpha = 0f
                    isCursorVisible = false
                    setSingleLine(true)
                    inputType = InputType.TYPE_CLASS_TEXT or if (password) {
                        InputType.TYPE_TEXT_VARIATION_PASSWORD
                    } else {
                        InputType.TYPE_TEXT_VARIATION_NORMAL
                    }
                    this.imeOptions = imeAction and EditorInfo.IME_FLAG_NO_EXTRACT_UI.inv()
                    setText(value)
                    setSelection(value.length)
                    addTextChangedListener(object : TextWatcher {
                        override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) = Unit
                        override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {
                            currentOnValueChange(s?.toString().orEmpty())
                        }
                        override fun afterTextChanged(s: Editable?) = Unit
                    })
                    setOnFocusChangeListener { _, hasFocus ->
                        if (hasFocus) {
                            FocusInteraction.Focus().also { focus ->
                                focusInteraction = focus
                                coroutineScope.launch { interactionSource.emit(focus) }
                            }
                        } else {
                            focusInteraction?.let { focus ->
                                coroutineScope.launch { interactionSource.emit(FocusInteraction.Unfocus(focus)) }
                            }
                            focusInteraction = null
                        }
                    }
                    setOnEditorActionListener { _, actionId, _ ->
                        if (actionId == imeAction || actionId == EditorInfo.IME_ACTION_UNSPECIFIED) {
                            currentOnEditorAction()
                            true
                        } else false
                    }
                    onViewCreated(this)
                }
            },
            update = { field ->
                field.isEnabled = enabled
                if (field.text.toString() != value) {
                    field.setText(value)
                    field.setSelection(value.length)
                }
            },
            modifier = Modifier.matchParentSize(),
        )
    }
}

@Composable
private fun MainShell(coreHost: String, telemetry: TelemetryState, onDisconnect: () -> Unit) {
    var page by rememberSaveable { mutableStateOf(Page.Drive) }
    var menuOpen by remember { mutableStateOf(false) }
    var videoFps by remember { mutableFloatStateOf(0f) }
    var frameDelayMs by remember { mutableFloatStateOf(0f) }
    Box(Modifier.fillMaxSize()) {
        when (page) {
            Page.Drive -> DriveScreen(coreHost, telemetry, { videoFps = it }, { frameDelayMs = it })
            Page.Home -> HomeScreen(telemetry)
            Page.Performance -> PerformanceScreen(coreHost, telemetry, videoFps)
            Page.Settings -> SettingsScreen(coreHost, onDisconnect)
        }
        Box(Modifier.fillMaxSize().windowInsetsPadding(WindowInsets.safeDrawing)) {
            FilledTonalIconButton(
                onClick = { menuOpen = true },
                modifier = Modifier.align(Alignment.TopStart).padding(12.dp),
                colors = IconButtonDefaults.filledTonalIconButtonColors(containerColor = Color(0x9915181D)),
            ) { Icon(Icons.Default.Menu, "Menu") }
            DropdownMenu(expanded = menuOpen, onDismissRequest = { menuOpen = false },
                modifier = Modifier.background(Color(0xF215181D))) {
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
private fun NavigationItem(page: Page, selected: Page, icon: androidx.compose.ui.graphics.vector.ImageVector,
                           onClick: (Page) -> Unit) {
    DropdownMenuItem(text = { Text(page.name) }, onClick = { onClick(page) },
        leadingIcon = { Icon(icon, null, tint = if (page == selected) MaterialTheme.colorScheme.primary else Color.White) })
}

@Composable
private fun DriveScreen(coreHost: String, telemetry: TelemetryState, onFps: (Float) -> Unit,
                        onFrameDelay: (Float) -> Unit) {
    var videoConnected by remember { mutableStateOf(false) }
    var videoFps by remember { mutableFloatStateOf(0f) }
    var frameDelayMs by remember { mutableFloatStateOf(0f) }
    Box(Modifier.fillMaxSize().background(Color.Black)) {
        AndroidView(
            factory = { context -> MjpegVideoView(context).also {
                it.onFpsChanged = { fps -> videoFps = fps; onFps(fps) }
                it.onFrameDelayChanged = { delay -> frameDelayMs = delay; onFrameDelay(delay) }
                it.onConnectionChanged = { connected -> videoConnected = connected }
            } },
            update = {
                it.onFpsChanged = { fps -> videoFps = fps; onFps(fps) }
                it.onFrameDelayChanged = { delay -> frameDelayMs = delay; onFrameDelay(delay) }
                it.onConnectionChanged = { connected -> videoConnected = connected }
                it.connect("http://$coreHost:8080/stream.mjpg")
            },
            modifier = Modifier.fillMaxSize(),
        )
        BoxWithConstraints(Modifier.fillMaxSize().windowInsetsPadding(WindowInsets.safeDrawing)) {
            if (telemetry.available) {
                CompassRibbon(telemetry, Modifier.align(Alignment.TopCenter))
                DebugPanel(videoFps, frameDelayMs, Modifier.align(Alignment.CenterStart))
                val mapSize = (maxWidth * .17f).coerceIn(150.dp, 230.dp)
                MiniMap(telemetry, mapSize, Modifier.align(Alignment.BottomEnd).padding(22.dp))
                BatteryBar(telemetry.batteryPercent,
                    Modifier.align(Alignment.BottomCenter).padding(bottom = 22.dp)
                        .width((maxWidth * .26f).coerceAtMost(500.dp)))
            }
            if (!videoConnected) StatusLabel("Camera offline", Modifier.align(Alignment.Center))
            else if (!telemetry.available) StatusLabel("Synchronizing vehicle data", Modifier.align(Alignment.Center))
        }
    }
}

@Composable
private fun CompassRibbon(data: TelemetryState, modifier: Modifier = Modifier) {
    val heading = smoothAngle(normalize(data.heading + data.cameraPan))
    val density = LocalDensity.current
    Canvas(modifier.fillMaxWidth().height(56.dp)) {
        val center = size.width / 2f
        val span = minOf(with(density) { 760.dp.toPx() }, size.width * .40f)
        val pxPerDegree = span / 180f
        val textPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply { textAlign = Paint.Align.CENTER }
        var bearing = floor((heading - 90f) / 5f) * 5f
        while (bearing <= heading + 90f) {
            val offset = bearing - heading
            val x = center + offset * pxPerDegree
            val normalized = normalize(bearing).roundToInt() % 360
            val major = normalized % 15 == 0
            val startY = 18.dp.toPx(); val endY = (if (major) 29 else 23).dp.toPx()
            drawLine(Color(0x73000000), Offset(x + 1.dp.toPx(), startY),
                Offset(x + 1.dp.toPx(), endY), 3.dp.toPx())
            drawLine(Color(0xAFCDD0D2), Offset(x, startY), Offset(x, endY), 1.dp.toPx())
            if (major && abs(offset) >= 7f) {
                val label = if (data.magneticHeading != null) cardinalAt(normalized.toFloat()) ?: normalized.toString()
                    else normalized.toString()
                textPaint.color = Color(0xAFCDD0D2).toArgb(); textPaint.textSize = 10.sp.toPx()
                textPaint.isFakeBoldText = true
                textPaint.setShadowLayer(2f, 1f, 1f, Color(0x73000000).toArgb())
                drawContext.canvas.nativeCanvas.drawText(label, x, 47.dp.toPx(), textPaint)
            }
            bearing += 5f
        }
        val focus = normalize(heading).roundToInt() % 360
        drawLine(Color(0x7D000000), Offset(center + 1.dp.toPx(), 18.dp.toPx()),
            Offset(center + 1.dp.toPx(), 30.dp.toPx()), 3.dp.toPx())
        drawLine(Color.White, Offset(center, 17.dp.toPx()), Offset(center, 30.dp.toPx()), 2.2.dp.toPx())
        textPaint.color = Color.White.toArgb(); textPaint.textSize = 11.sp.toPx(); textPaint.isFakeBoldText = true
        textPaint.setShadowLayer(2f, 1f, 1f, Color(0x7D000000).toArgb())
        drawContext.canvas.nativeCanvas.drawText(focus.toString(), center, 48.dp.toPx(), textPaint)
        val triangle = Path().apply {
            moveTo(center - 7.dp.toPx(), 1.dp.toPx()); lineTo(center + 7.dp.toPx(), 1.dp.toPx())
            lineTo(center, 13.dp.toPx()); close()
        }
        drawPath(triangle, Color(0xFFEECD48))
    }
}

@Composable
private fun smoothAngle(target: Float): Float {
    var value by remember { mutableFloatStateOf(target) }
    LaunchedEffect(target) {
        while (true) {
            val delta = (target - value + 540f) % 360f - 180f
            if (abs(delta) <= .08f) { value = target; break }
            value = normalize(value + delta * .08f)
            withFrameNanos { }
        }
    }
    return value
}

@Composable
private fun DebugPanel(fps: Float, frameDelayMs: Float, modifier: Modifier = Modifier) {
    Surface(modifier.widthIn(min = 240.dp, max = 330.dp).fillMaxWidth(.25f),
        color = Color(0x9B000000), shape = RoundedCornerShape(topEnd = 5.dp, bottomEnd = 5.dp)) {
        Column(Modifier.padding(start = 18.dp, end = 18.dp, top = 14.dp, bottom = 16.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp)) {
            DebugRow("FPS", "${"%.1f".format(fps)}")
            DebugRow("Frame Delay", "${"%.1f".format(frameDelayMs)} ms")
        }
    }
}

@Composable private fun DebugRow(label: String, value: String) {
    Row(Modifier.fillMaxWidth().height(25.dp), verticalAlignment = Alignment.CenterVertically) {
        Text(label, Modifier.weight(.56f), color = Color(0xFFF5F5F5), style = MaterialTheme.typography.labelLarge)
        Text(value, Modifier.weight(.44f), color = Color(0xFFF5F5F5),
            style = MaterialTheme.typography.labelLarge, textAlign = androidx.compose.ui.text.style.TextAlign.End)
    }
}

@Composable
private fun MiniMap(data: TelemetryState, mapSize: androidx.compose.ui.unit.Dp, modifier: Modifier = Modifier) {
    val heading = smoothAngle(normalize(data.heading + data.cameraPan))
    Canvas(modifier.size(mapSize)) {
        drawRect(Color(0xB95C6065))
        val border = androidx.compose.ui.graphics.drawscope.Stroke(2.dp.toPx())
        drawRect(Color(0xB9EBEBEB), style = border)
        for (index in 1..3) {
            val coordinate = size.width * index / 4f
            drawLine(Color(0x37D7D7D7), Offset(coordinate, 0f), Offset(coordinate, size.height), 1.dp.toPx())
            drawLine(Color(0x37D7D7D7), Offset(0f, coordinate), Offset(size.width, coordinate), 1.dp.toPx())
        }
        val angle = (heading - 90f) * PI.toFloat() / 180f
        val halfFov = 24f * PI.toFloat() / 180f
        val length = size.width * .28f
        val left = Offset(center.x + cos(angle - halfFov) * length, center.y + sin(angle - halfFov) * length)
        val right = Offset(center.x + cos(angle + halfFov) * length, center.y + sin(angle + halfFov) * length)
        val control = Offset(center.x + cos(angle) * length * 1.06f, center.y + sin(angle) * length * 1.06f)
        val cone = Path().apply {
            moveTo(center.x, center.y); lineTo(left.x, left.y)
            quadraticBezierTo(control.x, control.y, right.x, right.y); close()
        }
        val end = Offset(center.x + cos(angle) * length, center.y + sin(angle) * length)
        val colors = if (data.magneticHeading != null)
            listOf(Color(0xD7BEFFD2), Color(0x10A0F5BE))
        else listOf(Color(0xCDFFFFFF), Color(0x12FFFFFF))
        drawPath(cone, Brush.linearGradient(colors, center, end))
        val dotRadius = maxOf(8.dp.toPx(), size.width * .045f)
        drawCircle(Color(0xFFE0E0E0), dotRadius, center)
        drawCircle(Color(0xE1FFFFFF), dotRadius, center,
            style = androidx.compose.ui.graphics.drawscope.Stroke(2.dp.toPx()))
    }
}

@Composable
private fun BatteryBar(percent: Float, modifier: Modifier = Modifier) {
    Box(modifier.height(16.dp).background(Color(0x91000000))) {
        Box(Modifier.fillMaxHeight().fillMaxWidth(percent.coerceIn(0f, 100f) / 100f)
            .background(Color(0xF5F8F8F8)))
    }
}

@Composable
private fun HomeScreen(data: TelemetryState) {
    PageBackground {
        Row(Modifier.fillMaxSize().padding(28.dp), horizontalArrangement = Arrangement.spacedBy(18.dp)) {
            Surface(Modifier.weight(1.4f).fillMaxHeight(), color = Color(0xFF12151A), shape = RoundedCornerShape(6.dp)) {
                AttitudeView(data, Modifier.fillMaxSize())
            }
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                DataCard("Heading", "${normalize(data.heading).roundToInt()} deg")
                DataCard("Battery", "${data.batteryPercent.roundToInt()}%  |  ${"%.2f".format(data.batteryVoltage)} V")
                DataCard("Obstacle", formatDistance(data.distanceMm))
                DataCard("Infrared", data.infraredMask.toString(2).padStart(4, '0'))
            }
        }
    }
}

@Composable
private fun AttitudeView(data: TelemetryState, modifier: Modifier) {
    Canvas(modifier.padding(24.dp)) {
        drawCircle(Color(0xFF20262D), size.minDimension * .34f, center)
        rotate(data.roll, center) {
            val half = size.minDimension * .29f
            val pitchOffset = data.pitch.coerceIn(-45f, 45f) / 45f * half
            drawLine(Color(0xFFF0B429), Offset(center.x - half, center.y + pitchOffset),
                Offset(center.x + half, center.y + pitchOffset), 3.dp.toPx())
            drawLine(Color.White, Offset(center.x, center.y - half * .55f),
                Offset(center.x, center.y + half * .55f), 2.dp.toPx())
        }
        drawCircle(Color(0xFF9FA6AF), size.minDimension * .34f, center,
            style = androidx.compose.ui.graphics.drawscope.Stroke(2.dp.toPx()))
    }
}

@Composable
private fun PerformanceScreen(host: String, data: TelemetryState, videoFps: Float) {
    PageBackground {
        Column(Modifier.fillMaxSize().padding(30.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
            Text("Performance", style = MaterialTheme.typography.headlineMedium, color = Color.White)
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                DataCard("Video", "${"%.1f".format(videoFps)} FPS", Modifier.weight(1f))
                DataCard("Telemetry", "${"%.1f".format(data.sampleRateHz)} Hz", Modifier.weight(1f))
                DataCard("Core host", host, Modifier.weight(1f))
            }
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                DataCard("Battery", "${data.batteryPercent.roundToInt()}%", Modifier.weight(1f))
                DataCard("Camera pan", "${data.cameraPan.roundToInt()} deg", Modifier.weight(1f))
                DataCard("Link", if (data.available) "ONLINE" else "WAITING", Modifier.weight(1f))
            }
        }
    }
}

@Composable
private fun SettingsScreen(host: String, onDisconnect: () -> Unit) {
    PageBackground {
        Column(Modifier.fillMaxSize().padding(30.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
            Text("Settings", style = MaterialTheme.typography.headlineMedium, color = Color.White)
            DataCard("Core host", host)
            OutlinedButton(onClick = onDisconnect) { Icon(Icons.Default.Logout, null); Spacer(Modifier.width(8.dp)); Text("Disconnect") }
        }
    }
}

@Composable private fun PageBackground(content: @Composable BoxScope.() -> Unit) =
    Box(Modifier.fillMaxSize().background(Color(0xFF0B0D10)).windowInsetsPadding(WindowInsets.safeDrawing), content = content)

@Composable
private fun DataCard(label: String, value: String, modifier: Modifier = Modifier) {
    Surface(modifier.fillMaxWidth(), color = Color(0xFF171B20), shape = RoundedCornerShape(6.dp)) {
        Column(Modifier.padding(16.dp)) {
            Text(label, color = Color(0xFF9FA6AF), style = MaterialTheme.typography.labelMedium)
            Spacer(Modifier.height(4.dp)); Text(value, color = Color.White, style = MaterialTheme.typography.titleMedium)
        }
    }
}

@Composable private fun StatusLabel(text: String, modifier: Modifier) =
    Surface(modifier, color = Color(0xB0000000), shape = RoundedCornerShape(4.dp)) {
        Text(text, color = Color.White, modifier = Modifier.padding(horizontal = 16.dp, vertical = 10.dp))
    }

@Composable
private fun LowBatteryOverlay() {
    Box(Modifier.fillMaxSize().background(Color.Black), contentAlignment = Alignment.Center) {
        Canvas(Modifier.width(68.dp).height(126.dp)) {
            drawRoundRect(Color.White, style = androidx.compose.ui.graphics.drawscope.Stroke(5.dp.toPx()),
                cornerRadius = androidx.compose.ui.geometry.CornerRadius(9.dp.toPx()))
            drawRoundRect(Color.White, topLeft = Offset(size.width * .34f, -8.dp.toPx()),
                size = androidx.compose.ui.geometry.Size(size.width * .32f, 10.dp.toPx()),
                cornerRadius = androidx.compose.ui.geometry.CornerRadius(3.dp.toPx()))
            drawRoundRect(Color(0xFFFF704D), topLeft = Offset(7.dp.toPx(), size.height - 16.dp.toPx()),
                size = androidx.compose.ui.geometry.Size(size.width - 14.dp.toPx(), 9.dp.toPx()),
                cornerRadius = androidx.compose.ui.geometry.CornerRadius(3.dp.toPx()))
        }
    }
}

private fun normalize(value: Float): Float = ((value % 360f) + 360f) % 360f
private fun cardinalAt(value: Float): String? = when (normalize(value).roundToInt()) {
    0 -> "N"; 45 -> "NE"; 90 -> "E"; 135 -> "SE"; 180 -> "S"; 225 -> "SW"; 270 -> "W"; 315 -> "NW"; else -> null
}
private fun formatDistance(mm: Float): String = when {
    mm >= 1000f -> "${"%.2f".format(mm / 1000f)} m"
    mm >= 100f -> "${"%.1f".format(mm / 10f)} cm"
    else -> "${mm.roundToInt()} mm"
}
