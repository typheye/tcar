package com.typheye.tcarkit.ui

import android.graphics.Paint
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.withFrameNanos
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.nativeCanvas
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import com.typheye.tcarkit.MjpegVideoView
import com.typheye.tcarkit.TelemetryState
import kotlin.math.PI
import kotlin.math.abs
import kotlin.math.cos
import kotlin.math.floor
import kotlin.math.roundToInt
import kotlin.math.sin

@Composable
internal fun VisionScreen(
    coreHost: String,
    telemetry: TelemetryState,
    onFps: (Float) -> Unit,
    onFrameDelay: (Float) -> Unit,
) {
    var videoConnected by remember { mutableStateOf(false) }
    var videoFps by remember { mutableFloatStateOf(0f) }
    var frameDelayMs by remember { mutableFloatStateOf(0f) }
    Box(Modifier.fillMaxSize().background(Color.Black)) {
        AndroidView(
            factory = { context ->
                MjpegVideoView(context).also {
                    it.onFpsChanged = { fps -> videoFps = fps; onFps(fps) }
                    it.onFrameDelayChanged = { delay -> frameDelayMs = delay; onFrameDelay(delay) }
                    it.onConnectionChanged = { connected -> videoConnected = connected }
                }
            },
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
                BatteryBar(
                    telemetry.batteryPercent,
                    Modifier.align(Alignment.BottomCenter).padding(bottom = 22.dp)
                        .width((maxWidth * .26f).coerceAtMost(500.dp)),
                )
            }
            if (!videoConnected) {
                StatusLabel("Camera offline", Modifier.align(Alignment.Center))
            } else if (!telemetry.available) {
                StatusLabel("Synchronizing vehicle data", Modifier.align(Alignment.Center))
            }
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
            val startY = 18.dp.toPx()
            val endY = (if (major) 29 else 23).dp.toPx()
            drawLine(
                Color(0x73000000),
                Offset(x + 1.dp.toPx(), startY),
                Offset(x + 1.dp.toPx(), endY),
                3.dp.toPx(),
            )
            drawLine(Color(0xAFCDD0D2), Offset(x, startY), Offset(x, endY), 1.dp.toPx())
            if (major && abs(offset) >= 7f) {
                val label = if (data.magneticHeading != null) {
                    cardinalAt(normalized.toFloat()) ?: normalized.toString()
                } else {
                    normalized.toString()
                }
                textPaint.color = Color(0xAFCDD0D2).toArgb()
                textPaint.textSize = 10.sp.toPx()
                textPaint.isFakeBoldText = true
                textPaint.setShadowLayer(2f, 1f, 1f, Color(0x73000000).toArgb())
                drawContext.canvas.nativeCanvas.drawText(label, x, 47.dp.toPx(), textPaint)
            }
            bearing += 5f
        }
        val focus = normalize(heading).roundToInt() % 360
        drawLine(
            Color(0x7D000000),
            Offset(center + 1.dp.toPx(), 18.dp.toPx()),
            Offset(center + 1.dp.toPx(), 30.dp.toPx()),
            3.dp.toPx(),
        )
        drawLine(Color.White, Offset(center, 17.dp.toPx()), Offset(center, 30.dp.toPx()), 2.2.dp.toPx())
        textPaint.color = Color.White.toArgb()
        textPaint.textSize = 11.sp.toPx()
        textPaint.isFakeBoldText = true
        textPaint.setShadowLayer(2f, 1f, 1f, Color(0x7D000000).toArgb())
        drawContext.canvas.nativeCanvas.drawText(focus.toString(), center, 48.dp.toPx(), textPaint)
        val triangle = Path().apply {
            moveTo(center - 7.dp.toPx(), 1.dp.toPx())
            lineTo(center + 7.dp.toPx(), 1.dp.toPx())
            lineTo(center, 13.dp.toPx())
            close()
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
            if (abs(delta) <= .08f) {
                value = target
                break
            }
            value = normalize(value + delta * .08f)
            withFrameNanos { }
        }
    }
    return value
}

@Composable
private fun DebugPanel(fps: Float, frameDelayMs: Float, modifier: Modifier = Modifier) {
    Surface(
        modifier.widthIn(min = 240.dp, max = 330.dp).fillMaxWidth(.25f),
        color = Color(0x9B000000),
        shape = RoundedCornerShape(topEnd = 5.dp, bottomEnd = 5.dp),
    ) {
        Column(Modifier.padding(start = 18.dp, end = 18.dp, top = 14.dp, bottom = 16.dp)) {
            DebugRow("FPS", "${"%.1f".format(fps)}")
            DebugRow("Frame Delay", "${"%.1f".format(frameDelayMs)} ms")
        }
    }
}

@Composable
private fun DebugRow(label: String, value: String) {
    Row(Modifier.fillMaxWidth().height(25.dp), verticalAlignment = Alignment.CenterVertically) {
        Text(label, Modifier.weight(.56f), color = Color(0xFFF5F5F5), style = MaterialTheme.typography.labelLarge)
        Text(
            value,
            Modifier.weight(.44f),
            color = Color(0xFFF5F5F5),
            style = MaterialTheme.typography.labelLarge,
            textAlign = TextAlign.End,
        )
    }
}

@Composable
private fun MiniMap(data: TelemetryState, mapSize: Dp, modifier: Modifier = Modifier) {
    val heading = smoothAngle(normalize(data.heading + data.cameraPan))
    Canvas(modifier.size(mapSize)) {
        drawRect(Color(0xB95C6065))
        drawRect(Color(0xB9EBEBEB), style = Stroke(2.dp.toPx()))
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
            moveTo(center.x, center.y)
            lineTo(left.x, left.y)
            quadraticBezierTo(control.x, control.y, right.x, right.y)
            close()
        }
        val end = Offset(center.x + cos(angle) * length, center.y + sin(angle) * length)
        val colors = if (data.magneticHeading != null) {
            listOf(Color(0xD7BEFFD2), Color(0x10A0F5BE))
        } else {
            listOf(Color(0xCDFFFFFF), Color(0x12FFFFFF))
        }
        drawPath(cone, Brush.linearGradient(colors, center, end))
        val dotRadius = maxOf(8.dp.toPx(), size.width * .045f)
        drawCircle(Color(0xFFE0E0E0), dotRadius, center)
        drawCircle(Color(0xE1FFFFFF), dotRadius, center, style = Stroke(2.dp.toPx()))
    }
}

@Composable
private fun BatteryBar(percent: Float, modifier: Modifier = Modifier) {
    Box(modifier.height(16.dp).background(Color(0x91000000))) {
        Box(
            Modifier.fillMaxHeight().fillMaxWidth(percent.coerceIn(0f, 100f) / 100f)
                .background(Color(0xF5F8F8F8)),
        )
    }
}
