package com.typheye.tcarkit.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import com.typheye.tcarkit.PerformanceState

@Composable
internal fun PerformanceScreen(data: PerformanceState) {
    val unavailable = "--"
    PageBackground {
        Column(Modifier.fillMaxSize().padding(30.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text("Performance", style = MaterialTheme.typography.headlineMedium, color = Color.White)
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                DataCard("Uptime", if (data.available) formatUptime(data.uptimeSeconds) else unavailable, Modifier.weight(1f))
                DataCard("CPU", if (data.available) "${"%.1f".format(data.cpuPercent)}%" else unavailable, Modifier.weight(1f))
                DataCard("Memory", if (data.available) "${"%.1f".format(data.memoryPercent)}%" else unavailable, Modifier.weight(1f))
            }
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                DataCard("Latency", if (data.available) "${"%.1f".format(data.latencyMs)} ms" else unavailable, Modifier.weight(1f))
                DataCard("Network", if (data.available) "${"%.2f".format(data.networkMbPerSecond)} MB/s" else unavailable, Modifier.weight(1f))
                Spacer(Modifier.weight(1f))
            }
        }
    }
}

private fun formatUptime(seconds: Float): String {
    val total = seconds.toLong().coerceAtLeast(0L)
    val days = total / 86_400
    val hours = total % 86_400 / 3_600
    val minutes = total % 3_600 / 60
    return if (days > 0) "${days}d ${hours}h" else "${hours}h ${minutes}m"
}
