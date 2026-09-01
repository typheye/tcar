package com.typheye.tcarkit

import android.os.SystemClock
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.*
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.Inet4Address
import java.net.URL

sealed interface ConnectionState {
    data object Disconnected : ConnectionState
    data object Discovering : ConnectionState
    data class Connected(val coreHost: String) : ConnectionState
    data class Failed(val message: String) : ConnectionState
}

data class TelemetryState(
    val available: Boolean = false,
    val pitch: Float = 0f,
    val roll: Float = 0f,
    val yaw: Float = 0f,
    val heading: Float = 0f,
    val magneticHeading: Float? = null,
    val cameraPan: Float = 0f,
    val distanceMm: Float = 0f,
    val batteryVoltage: Float = 0f,
    val batteryPercent: Float = 0f,
    val infraredMask: Int = 0,
    val sampleRateHz: Float = 0f,
    val lastUpdatedElapsed: Long = 0L,
)

class ConnectionViewModel : ViewModel() {
    var state: ConnectionState by mutableStateOf(ConnectionState.Disconnected)
        private set
    var telemetry: TelemetryState by mutableStateOf(TelemetryState())
        private set
    private var telemetryJob: Job? = null

    fun connect(username: String, password: String) {
        if (state is ConnectionState.Discovering) return
        state = ConnectionState.Discovering
        viewModelScope.launch {
            runCatching {
                val host = withContext(Dispatchers.IO) { discoverCoreHost() }
                withContext(Dispatchers.IO) { login(host, username, password) }
                host
            }.onSuccess { host ->
                state = ConnectionState.Connected(host)
                startTelemetry(host)
            }.onFailure { error ->
                state = ConnectionState.Failed(error.message ?: "Connection failed")
            }
        }
    }

    fun disconnect() {
        telemetryJob?.cancel()
        telemetryJob = null
        telemetry = TelemetryState()
        state = ConnectionState.Disconnected
    }

    private fun startTelemetry(host: String) {
        telemetryJob?.cancel()
        telemetryJob = viewModelScope.launch {
            var previousSample = 0L
            while (isActive && (state as? ConnectionState.Connected)?.coreHost == host) {
                val started = SystemClock.elapsedRealtime()
                val sample = withContext(Dispatchers.IO) {
                    runCatching { request("GET", "http://$host:8080/api/v1/telemetry") }.getOrNull()
                }
                if (sample != null) {
                    val now = SystemClock.elapsedRealtime()
                    val rate = if (previousSample > 0L) 1000f / (now - previousSample).coerceAtLeast(1L) else 0f
                    previousSample = now
                    telemetry = parseTelemetry(sample, rate, now)
                } else if (SystemClock.elapsedRealtime() - telemetry.lastUpdatedElapsed > 2_000L) {
                    telemetry = telemetry.copy(available = false)
                }
                delay((200L - (SystemClock.elapsedRealtime() - started)).coerceAtLeast(40L))
            }
        }
    }

    private fun parseTelemetry(json: JSONObject, rate: Float, now: Long) = TelemetryState(
        available = true,
        pitch = json.optDouble("pitch").toFloat(),
        roll = json.optDouble("roll").toFloat(),
        yaw = json.optDouble("yaw").toFloat(),
        heading = json.optDouble("heading").toFloat(),
        magneticHeading = json.opt("mag_heading")?.takeUnless { it == JSONObject.NULL }?.let {
            (it as? Number)?.toFloat()
        },
        cameraPan = json.optDouble("camera_pan").toFloat(),
        distanceMm = json.optDouble("distance_mm").toFloat(),
        batteryVoltage = json.optDouble("battery_voltage").toFloat(),
        batteryPercent = json.optDouble("battery_percent").toFloat().coerceIn(0f, 100f),
        infraredMask = json.optInt("infrared_mask"),
        sampleRateHz = rate,
        lastUpdatedElapsed = now,
    )

    private fun discoverCoreHost(): String {
        val json = request("GET", "http://192.168.66.1/test")
        val devices = json.getJSONArray("devices")
        for (index in 0 until devices.length()) {
            val device = devices.getJSONObject(index)
            if (device.optString("name") != "Core host" || !device.optBoolean("status")) continue
            val address = device.optString("ip")
            val parsed = runCatching { Inet4Address.getByName(address) }.getOrNull()
            if (parsed != null && !parsed.isAnyLocalAddress && !parsed.isLoopbackAddress) return address
        }
        error("Core host is offline")
    }

    private fun login(host: String, username: String, password: String) {
        val body = JSONObject().put("username", username).put("password", password).toString()
        if (request("POST", "http://$host:8080/api/login", body).optInt("status") != 1) {
            error("Invalid username or password")
        }
    }

    private fun request(method: String, address: String, body: String? = null): JSONObject {
        val connection = URL(address).openConnection() as HttpURLConnection
        return try {
            connection.requestMethod = method
            connection.connectTimeout = 2_500
            connection.readTimeout = 3_500
            connection.useCaches = false
            connection.setRequestProperty("Accept", "application/json")
            if (body != null) {
                connection.doOutput = true
                connection.setRequestProperty("Content-Type", "application/json; charset=utf-8")
                connection.outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }
            }
            val status = connection.responseCode
            val stream = if (status in 200..299) connection.inputStream else connection.errorStream
            val content = stream?.bufferedReader()?.use { it.readText() }.orEmpty()
            if (status !in 200..299) {
                val reason = runCatching { JSONObject(content).optString("error") }.getOrNull()
                error(reason?.takeIf { it.isNotBlank() } ?: "Connection failed ($status)")
            }
            JSONObject(content)
        } finally {
            connection.disconnect()
        }
    }
}
