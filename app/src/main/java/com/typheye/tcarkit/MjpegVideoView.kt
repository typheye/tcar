package com.typheye.tcarkit

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Rect
import android.graphics.RectF
import android.util.AttributeSet
import android.view.View
import java.io.BufferedInputStream
import java.io.ByteArrayOutputStream
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.atomic.AtomicInteger
import kotlin.concurrent.thread

class MjpegVideoView @JvmOverloads constructor(
    context: Context,
    attributes: AttributeSet? = null,
) : View(context, attributes) {
    @Volatile private var streamUrl: String? = null
    @Volatile private var running = false
    @Volatile private var activeConnection: HttpURLConnection? = null
    private val generation = AtomicInteger()
    private val frameLock = Any()
    private var latestFrame: Bitmap? = null
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG or Paint.FILTER_BITMAP_FLAG)

    var onFpsChanged: ((Float) -> Unit)? = null
    var onFrameDelayChanged: ((Float) -> Unit)? = null
    var onConnectionChanged: ((Boolean) -> Unit)? = null

    init {
        setBackgroundColor(Color.BLACK)
    }

    fun connect(url: String) {
        if (streamUrl == url && running) return
        streamUrl = url
        restart()
    }

    fun disconnect() {
        running = false
        generation.incrementAndGet()
        activeConnection?.disconnect()
        activeConnection = null
        synchronized(frameLock) {
            latestFrame?.recycle()
            latestFrame = null
        }
    }

    override fun onAttachedToWindow() {
        super.onAttachedToWindow()
        if (!running) restart()
    }

    override fun onDetachedFromWindow() {
        disconnect()
        super.onDetachedFromWindow()
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        canvas.drawColor(Color.BLACK)
        synchronized(frameLock) {
            val bitmap = latestFrame ?: return
            if (bitmap.isRecycled || bitmap.width <= 0 || bitmap.height <= 0) return
            val scale = maxOf(width.toFloat() / bitmap.width, height.toFloat() / bitmap.height)
            val frameWidth = bitmap.width * scale
            val frameHeight = bitmap.height * scale
            canvas.drawBitmap(
                bitmap,
                Rect(0, 0, bitmap.width, bitmap.height),
                RectF(
                    (width - frameWidth) / 2f,
                    (height - frameHeight) / 2f,
                    (width + frameWidth) / 2f,
                    (height + frameHeight) / 2f,
                ),
                paint,
            )
        }
    }

    private fun restart() {
        val address = streamUrl ?: return
        if (!isAttachedToWindow) return
        running = false
        activeConnection?.disconnect()
        val token = generation.incrementAndGet()
        running = true
        thread(name = "mjpeg-latest-frame", isDaemon = true) { readLoop(address, token) }
    }

    private fun readLoop(address: String, token: Int) {
        var retryDelay = 250L
        while (isCurrent(token)) {
            var connection: HttpURLConnection? = null
            try {
                connection = URL(address).openConnection() as HttpURLConnection
                activeConnection = connection
                connection.connectTimeout = 2_500
                connection.readTimeout = 5_000
                connection.useCaches = false
                connection.connect()
                if (connection.responseCode !in 200..299) {
                    error("MJPEG HTTP ${connection.responseCode}")
                }
                notifyConnection(true, token)
                retryDelay = 250L
                BufferedInputStream(connection.inputStream, 64 * 1024).use { readFrames(it, token) }
            } catch (_: Exception) {
                notifyConnection(false, token)
                if (isCurrent(token)) Thread.sleep(retryDelay)
                retryDelay = (retryDelay * 2).coerceAtMost(2_000L)
            } finally {
                connection?.disconnect()
                if (activeConnection === connection) activeConnection = null
            }
        }
    }

    private fun readFrames(input: BufferedInputStream, token: Int) {
        var previous = -1
        var frame: ByteArrayOutputStream? = null
        var frames = 0
        var fpsStarted = System.nanoTime()
        var frameStarted = 0L
        while (isCurrent(token)) {
            val value = input.read()
            if (value < 0) return
            if (frame == null) {
                if (previous == 0xFF && value == 0xD8) {
                    frame = ByteArrayOutputStream(128 * 1024).apply {
                        write(0xFF)
                        write(0xD8)
                    }
                    frameStarted = System.nanoTime()
                }
            } else {
                frame.write(value)
                if (frame.size() > 2_500_000) {
                    frame = null
                } else if (previous == 0xFF && value == 0xD9) {
                    val bytes = frame.toByteArray()
                    frame = null
                    val bitmap = BitmapFactory.decodeByteArray(bytes, 0, bytes.size)
                    if (bitmap != null && submitFrame(bitmap, token)) {
                        frames++
                        val frameDelay = (System.nanoTime() - frameStarted) / 1_000_000f
                        postIfCurrent(token) { onFrameDelayChanged?.invoke(frameDelay) }
                        val elapsed = System.nanoTime() - fpsStarted
                        if (elapsed >= 1_000_000_000L) {
                            val fps = frames * 1_000_000_000f / elapsed
                            postIfCurrent(token) { onFpsChanged?.invoke(fps) }
                            frames = 0
                            fpsStarted = System.nanoTime()
                        }
                    }
                }
            }
            previous = value
        }
    }

    private fun submitFrame(bitmap: Bitmap, token: Int): Boolean {
        if (!isCurrent(token)) {
            bitmap.recycle()
            return false
        }
        synchronized(frameLock) {
            if (!isCurrent(token)) {
                bitmap.recycle()
                return false
            }
            latestFrame?.recycle()
            latestFrame = bitmap
        }
        postInvalidateOnAnimation()
        return true
    }

    private fun notifyConnection(connected: Boolean, token: Int) {
        postIfCurrent(token) { onConnectionChanged?.invoke(connected) }
    }

    private fun postIfCurrent(token: Int, action: () -> Unit) {
        post { if (isCurrent(token)) action() }
    }

    private fun isCurrent(token: Int): Boolean = running && generation.get() == token
}
