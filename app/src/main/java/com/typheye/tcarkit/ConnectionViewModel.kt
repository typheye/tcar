package com.typheye.tcarkit

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
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

class ConnectionViewModel : ViewModel() {
    var state: ConnectionState by mutableStateOf(ConnectionState.Disconnected)
        private set

    fun connect(username: String, password: String) {
        if (state is ConnectionState.Discovering) return
        state = ConnectionState.Discovering
        viewModelScope.launch {
            state = runCatching {
                val host = withContext(Dispatchers.IO) { discoverCoreHost() }
                withContext(Dispatchers.IO) { login(host, username, password) }
                ConnectionState.Connected(host)
            }.getOrElse { ConnectionState.Failed(it.message ?: "Connection failed") }
        }
    }

    fun disconnect() { state = ConnectionState.Disconnected }

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
        val response = request("POST", "http://$host:8080/api/login", body)
        if (response.optInt("status") != 1) error("Invalid username or password")
    }

    private fun request(method: String, address: String, body: String? = null): JSONObject {
        val connection = URL(address).openConnection() as HttpURLConnection
        return try {
            connection.requestMethod = method
            connection.connectTimeout = 2_500
            connection.readTimeout = 3_500
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
