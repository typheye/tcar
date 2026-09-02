package com.typheye.tcarkit.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxScope
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.unit.dp
import kotlin.math.roundToInt

@Composable
internal fun PageBackground(content: @Composable BoxScope.() -> Unit) = Box(
    Modifier.fillMaxSize().background(Color(0xFF0B0D10))
        .windowInsetsPadding(WindowInsets.safeDrawing),
    content = content,
)

@Composable
internal fun DataCard(label: String, value: String, modifier: Modifier = Modifier) {
    Surface(modifier.fillMaxWidth(), color = Color(0xFF171B20), shape = RoundedCornerShape(6.dp)) {
        Column(Modifier.padding(16.dp)) {
            Text(label, color = Color(0xFF9FA6AF), style = MaterialTheme.typography.labelMedium)
            Spacer(Modifier.height(4.dp))
            Text(value, color = Color.White, style = MaterialTheme.typography.titleMedium)
        }
    }
}

@Composable
internal fun StatusLabel(text: String, modifier: Modifier) = Surface(
    modifier,
    color = Color(0xB0000000),
    shape = RoundedCornerShape(4.dp),
) {
    Text(text, color = Color.White, modifier = Modifier.padding(horizontal = 16.dp, vertical = 10.dp))
}

@Composable
internal fun LowBatteryOverlay() {
    Box(Modifier.fillMaxSize().background(Color.Black), contentAlignment = Alignment.Center) {
        Canvas(Modifier.width(68.dp).height(126.dp)) {
            drawRoundRect(
                Color.White,
                style = Stroke(5.dp.toPx()),
                cornerRadius = CornerRadius(9.dp.toPx()),
            )
            drawRoundRect(
                Color.White,
                topLeft = Offset(size.width * .34f, -8.dp.toPx()),
                size = Size(size.width * .32f, 10.dp.toPx()),
                cornerRadius = CornerRadius(3.dp.toPx()),
            )
            drawRoundRect(
                Color(0xFFFF704D),
                topLeft = Offset(7.dp.toPx(), size.height - 16.dp.toPx()),
                size = Size(size.width - 14.dp.toPx(), 9.dp.toPx()),
                cornerRadius = CornerRadius(3.dp.toPx()),
            )
        }
    }
}

internal fun normalize(value: Float): Float = ((value % 360f) + 360f) % 360f

internal fun cardinalAt(value: Float): String? = when (normalize(value).roundToInt()) {
    0 -> "N"
    45 -> "NE"
    90 -> "E"
    135 -> "SE"
    180 -> "S"
    225 -> "SW"
    270 -> "W"
    315 -> "NW"
    else -> null
}

internal fun formatDistance(mm: Float): String = when {
    mm >= 1000f -> "${"%.2f".format(mm / 1000f)} m"
    mm >= 100f -> "${"%.1f".format(mm / 10f)} cm"
    else -> "${mm.roundToInt()} mm"
}
