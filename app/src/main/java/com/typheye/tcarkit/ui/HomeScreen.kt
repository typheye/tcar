package com.typheye.tcarkit.ui

import android.graphics.Paint
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Rect
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.clipPath
import androidx.compose.ui.graphics.drawscope.rotate
import androidx.compose.ui.graphics.nativeCanvas
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.typheye.tcarkit.TelemetryState
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.roundToInt
import kotlin.math.sin

@Composable
internal fun HomeScreen(data: TelemetryState) {
    PageBackground {
        Row(
            Modifier.fillMaxSize().padding(28.dp),
            horizontalArrangement = Arrangement.spacedBy(18.dp),
        ) {
            Surface(
                Modifier.weight(7f).fillMaxHeight(),
                color = Color(0xFF12151A),
                shape = RoundedCornerShape(6.dp),
            ) {
                AircraftAttitudeIndicator(data, Modifier.fillMaxSize())
            }
            Column(
                Modifier.weight(3f).fillMaxHeight(),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                DataCard("Battery", "${data.batteryPercent.roundToInt()}%", Modifier.weight(1f))
                DataCard("Obstacle", formatDistance(data.distanceMm), Modifier.weight(1f))
                InfraredCard(data.infraredMask, Modifier.weight(1f))
            }
        }
    }
}

@Composable
private fun InfraredCard(mask: Int, modifier: Modifier = Modifier) {
    Surface(modifier.fillMaxWidth(), color = Color(0xFF171B20), shape = RoundedCornerShape(6.dp)) {
        Column(Modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.SpaceBetween) {
            Text("Infrared", color = Color(0xFF9FA6AF), style = MaterialTheme.typography.labelMedium)
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(10.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                repeat(4) { index ->
                    val active = mask and (1 shl (3 - index)) != 0
                    Box(
                        Modifier.weight(1f).fillMaxHeight(.45f)
                            .background(
                                if (active) Color(0xFFFF6A00) else Color(0xFF3B4149),
                                RoundedCornerShape(3.dp),
                            ),
                    )
                }
            }
        }
    }
}

@Composable
private fun AircraftAttitudeIndicator(data: TelemetryState, modifier: Modifier) {
    Canvas(modifier.padding(20.dp)) {
        val radius = size.minDimension * .43f
        val horizonPath = Path().apply {
            addOval(Rect(center.x - radius, center.y - radius, center.x + radius, center.y + radius))
        }
        val pitchScale = radius / 48f
        val pitchOffset = data.pitch.coerceIn(-45f, 45f) * pitchScale
        val textPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = Color.White.toArgb()
            textAlign = Paint.Align.CENTER
            textSize = 12.sp.toPx()
            isFakeBoldText = true
            setShadowLayer(2f, 1f, 1f, Color(0x88000000).toArgb())
        }

        drawCircle(Color(0xFF090B0E), radius + 13.dp.toPx(), center)
        drawCircle(Color(0xFF626870), radius + 8.dp.toPx(), center)

        clipPath(horizonPath) {
            rotate(-data.roll, center) {
                drawRect(
                    Color(0xFF4B9DCE),
                    topLeft = Offset(center.x - radius * 2f, center.y - radius * 2f),
                    size = androidx.compose.ui.geometry.Size(radius * 4f, radius * 4f),
                )
                val horizonY = center.y + pitchOffset
                drawRect(
                    Color(0xFF8D683E),
                    topLeft = Offset(center.x - radius * 2f, horizonY),
                    size = androidx.compose.ui.geometry.Size(radius * 4f, radius * 3f),
                )
                for (mark in -30..30 step 10) {
                    if (mark == 0) continue
                    val y = horizonY - mark * pitchScale
                    val halfWidth = radius * if (mark % 20 == 0) .28f else .19f
                    drawLine(
                        Color.White,
                        Offset(center.x - halfWidth, y),
                        Offset(center.x + halfWidth, y),
                        2.dp.toPx(),
                    )
                    val baseline = y + textPaint.textSize * .34f
                    drawContext.canvas.nativeCanvas.drawText(
                        kotlin.math.abs(mark).toString(),
                        center.x - halfWidth - 22.dp.toPx(),
                        baseline,
                        textPaint,
                    )
                    drawContext.canvas.nativeCanvas.drawText(
                        kotlin.math.abs(mark).toString(),
                        center.x + halfWidth + 22.dp.toPx(),
                        baseline,
                        textPaint,
                    )
                }
            }
        }

        val tickColor = Color(0xFFF4F6F8)
        val tickAngles = intArrayOf(
            -90, -80, -70, -60, -50, -45, -40, -30, -20, -10,
            0, 10, 20, 30, 40, 45, 50, 60, 70, 80, 90,
        )
        tickAngles.forEach { roll ->
            val radians = (-90f + roll) * PI.toFloat() / 180f
            val outer = radius - 7.dp.toPx()
            val inner = outer - if (roll % 30 == 0) 15.dp.toPx() else 9.dp.toPx()
            drawLine(
                tickColor,
                Offset(center.x + cos(radians) * inner, center.y + sin(radians) * inner),
                Offset(center.x + cos(radians) * outer, center.y + sin(radians) * outer),
                if (roll == 0) 4.dp.toPx() else 3.dp.toPx(),
            )
        }

        val markerY = center.y - radius + 29.dp.toPx()
        val rollMarker = Path().apply {
            moveTo(center.x, markerY - 10.dp.toPx())
            lineTo(center.x - 9.dp.toPx(), markerY + 7.dp.toPx())
            lineTo(center.x + 9.dp.toPx(), markerY + 7.dp.toPx())
            close()
        }
        rotate(-data.roll.coerceIn(-90f, 90f), center) {
            drawPath(rollMarker, Color(0xFFFF6B62))
        }

        val aircraft = Color(0xFFFFD600)
        val wingY = center.y
        drawLine(
            aircraft,
            Offset(center.x - radius * .32f, wingY),
            Offset(center.x - radius * .08f, wingY),
            6.dp.toPx(),
        )
        drawLine(
            aircraft,
            Offset(center.x + radius * .08f, wingY),
            Offset(center.x + radius * .32f, wingY),
            6.dp.toPx(),
        )
        drawCircle(aircraft, 7.dp.toPx(), center)

        drawCircle(Color(0xFFB7BCC2), radius + 1.dp.toPx(), center, style = Stroke(5.dp.toPx()))
        drawCircle(Color(0xFF2B2F35), radius + 10.dp.toPx(), center, style = Stroke(6.dp.toPx()))
    }
}
