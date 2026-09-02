package com.typheye.tcarkit.ui

import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.typheye.tcarkit.R

@Composable
internal fun BrandSplashScreen(onFinished: () -> Unit) {
    val timeline = remember { Animatable(0f) }
    LaunchedEffect(Unit) {
        timeline.animateTo(1f, tween(durationMillis = 2450, easing = LinearEasing))
        onFinished()
    }
    val progress = timeline.value
    val reveal = ((progress - 0.08f) / 0.22f).coerceIn(0f, 1f)
    val settle = 1f - (1f - reveal) * (1f - reveal)
    val exitAlpha = ((1f - progress) / 0.10f).coerceIn(0f, 1f)

    Box(
        Modifier.fillMaxSize().background(Color(0xFF080A0D))
            .graphicsLayer { alpha = exitAlpha },
    ) {
        Canvas(Modifier.fillMaxSize()) {
            val grid = Color(0xFF20242A)
            val step = 52.dp.toPx()
            var x = 0f
            while (x <= size.width) {
                drawLine(grid, Offset(x, 0f), Offset(x, size.height), 1f)
                x += step
            }
            var y = 0f
            while (y <= size.height) {
                drawLine(grid, Offset(0f, y), Offset(size.width, y), 1f)
                y += step
            }

            val centerY = size.height * 0.5f
            val orange = Color(0xFFFF6A00)
            val trackLength = size.width * (0.12f + 0.30f * settle)
            val trackGap = size.width * (0.17f - 0.08f * settle)
            val leftEnd = size.width * 0.5f - trackGap
            val rightStart = size.width * 0.5f + trackGap
            val offsets = floatArrayOf(-78f, -46f, 46f, 78f)
            offsets.forEachIndexed { index, offset ->
                val lineAlpha = (0.18f + index % 2 * 0.17f) * reveal
                val stroke = if (index % 2 == 0) 2.dp.toPx() else 1.dp.toPx()
                drawLine(
                    orange.copy(alpha = lineAlpha),
                    Offset((leftEnd - trackLength).coerceAtLeast(0f), centerY + offset),
                    Offset(leftEnd, centerY + offset),
                    stroke,
                )
                drawLine(
                    orange.copy(alpha = lineAlpha),
                    Offset(rightStart, centerY + offset),
                    Offset((rightStart + trackLength).coerceAtMost(size.width), centerY + offset),
                    stroke,
                )
            }

            val scanX = size.width * ((progress * 1.35f) % 1f)
            drawLine(
                orange.copy(alpha = 0.55f * (1f - settle * 0.35f)),
                Offset(scanX, size.height * 0.18f),
                Offset(scanX, size.height * 0.82f),
                2.dp.toPx(),
            )
        }

        Column(
            modifier = Modifier.align(Alignment.Center)
                .windowInsetsPadding(WindowInsets.safeDrawing)
                .graphicsLayer {
                    alpha = settle
                    scaleX = 0.88f + settle * 0.12f
                    scaleY = 0.88f + settle * 0.12f
                    translationY = (1f - settle) * 42.dp.toPx()
                },
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center,
        ) {
            Image(
                painterResource(R.drawable.icon_logo),
                contentDescription = "Typheye Car",
                contentScale = ContentScale.Fit,
                modifier = Modifier.size(88.dp).clip(RoundedCornerShape(20.dp)),
            )
            Spacer(Modifier.height(18.dp))
            Text("Typheye Car", color = Color.White, fontSize = 42.sp, fontWeight = FontWeight.SemiBold)
            Spacer(Modifier.height(12.dp))
            Box(
                Modifier.width(188.dp).height(3.dp)
                    .background(Color(0xFF343940), RoundedCornerShape(2.dp)),
            ) {
                Box(
                    Modifier.fillMaxHeight().fillMaxWidth(settle)
                        .background(Color(0xFFFF6A00), RoundedCornerShape(2.dp)),
                )
            }
            Spacer(Modifier.height(10.dp))
            Text(
                "VEHICLE CONTROL SYSTEM",
                color = Color(0xFFAEB4BC),
                fontSize = 11.sp,
                fontWeight = FontWeight.Medium,
            )
        }
    }
}
