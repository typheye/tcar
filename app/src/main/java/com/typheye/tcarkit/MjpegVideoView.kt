package com.typheye.tcarkit

import android.content.Context
import android.graphics.*
import android.util.AttributeSet
import android.view.TextureView
import java.io.BufferedInputStream
import java.io.ByteArrayOutputStream
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.atomic.AtomicInteger
import kotlin.concurrent.thread

class MjpegVideoView @JvmOverloads constructor(
    context: Context, attributes: AttributeSet? = null,
) : TextureView(context, attributes), TextureView.SurfaceTextureListener {
    @Volatile private var streamUrl: String? = null
    @Volatile private var running = false
    private val generation = AtomicInteger()
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG or Paint.FILTER_BITMAP_FLAG)
    var onFpsChanged: ((Float) -> Unit)? = null
    var onFrameDelayChanged: ((Float) -> Unit)? = null
    var onConnectionChanged: ((Boolean) -> Unit)? = null

    init { surfaceTextureListener = this; isOpaque = true }

    fun connect(url: String) {
        if (streamUrl == url && running) return
        streamUrl = url
        restart()
    }

    fun disconnect() { running = false; generation.incrementAndGet() }

    override fun onSurfaceTextureAvailable(texture: SurfaceTexture, width: Int, height: Int) = restart()
    override fun onSurfaceTextureSizeChanged(texture: SurfaceTexture, width: Int, height: Int) = Unit
    override fun onSurfaceTextureUpdated(texture: SurfaceTexture) = Unit
    override fun onSurfaceTextureDestroyed(texture: SurfaceTexture): Boolean { disconnect(); return true }

    private fun restart() {
        val address = streamUrl ?: return
        if (!isAvailable) return
        val token = generation.incrementAndGet()
        running = true
        thread(name = "mjpeg-latest-frame", isDaemon = true) { readLoop(address, token) }
    }

    private fun readLoop(address: String, token: Int) {
        var retryDelay = 250L
        while (running && generation.get() == token) {
            var connection: HttpURLConnection? = null
            try {
                connection = URL(address).openConnection() as HttpURLConnection
                connection.connectTimeout = 2_500
                connection.readTimeout = 5_000
                connection.useCaches = false
                connection.connect()
                if (connection.responseCode !in 200..299) error("MJPEG HTTP ${connection.responseCode}")
                post { onConnectionChanged?.invoke(true) }
                retryDelay = 250L
                BufferedInputStream(connection.inputStream, 64 * 1024).use { readFrames(it, token) }
            } catch (_: Exception) {
                post { onConnectionChanged?.invoke(false) }
                if (running && generation.get() == token) Thread.sleep(retryDelay)
                retryDelay = (retryDelay * 2).coerceAtMost(2_000L)
            } finally { connection?.disconnect() }
        }
    }

    private fun readFrames(input: BufferedInputStream, token: Int) {
        var previous = -1
        var frame: ByteArrayOutputStream? = null
        var frames = 0
        var fpsStarted = System.nanoTime()
        var frameStarted = 0L
        while (running && generation.get() == token) {
            val value = input.read()
            if (value < 0) return
            if (frame == null) {
                if (previous == 0xFF && value == 0xD8) {
                    frame = ByteArrayOutputStream(128 * 1024).apply { write(0xFF); write(0xD8) }
                    frameStarted = System.nanoTime()
                }
            } else {
                frame.write(value)
                if (frame.size() > 2_500_000) frame = null
                else if (previous == 0xFF && value == 0xD9) {
                    val bytes = frame.toByteArray(); frame = null
                    BitmapFactory.decodeByteArray(bytes, 0, bytes.size)?.let { bitmap ->
                        drawFrame(bitmap); bitmap.recycle(); frames++
                        val frameDelay = (System.nanoTime() - frameStarted) / 1_000_000f
                        post { onFrameDelayChanged?.invoke(frameDelay) }
                        val elapsed = System.nanoTime() - fpsStarted
                        if (elapsed >= 1_000_000_000L) {
                            val fps = frames * 1_000_000_000f / elapsed
                            post { onFpsChanged?.invoke(fps) }
                            frames = 0; fpsStarted = System.nanoTime()
                        }
                    }
                }
            }
            previous = value
        }
    }

    private fun drawFrame(bitmap: Bitmap) {
        val canvas = lockCanvas() ?: return
        try {
            canvas.drawColor(Color.BLACK)
            val scale = maxOf(canvas.width.toFloat() / bitmap.width, canvas.height.toFloat() / bitmap.height)
            val width = bitmap.width * scale; val height = bitmap.height * scale
            canvas.drawBitmap(bitmap, Rect(0, 0, bitmap.width, bitmap.height),
                RectF((canvas.width - width) / 2f, (canvas.height - height) / 2f,
                    (canvas.width + width) / 2f, (canvas.height + height) / 2f), paint)
        } finally { unlockCanvasAndPost(canvas) }
    }
}
