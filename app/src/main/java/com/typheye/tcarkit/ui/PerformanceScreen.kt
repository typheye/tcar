package com.typheye.tcarkit.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import com.typheye.tcarkit.TelemetryState
import kotlin.math.roundToInt

@Composable
internal fun PerformanceScreen(host: String, data: TelemetryState, videoFps: Float) {
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
