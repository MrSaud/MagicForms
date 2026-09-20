package com.magicforms.mobile.ui.signatures

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.unit.dp
import android.graphics.Bitmap
import android.graphics.Canvas as AndroidCanvas
import android.graphics.Paint
import androidx.compose.ui.platform.LocalDensity

class SignaturePadState {
    private val strokes = mutableStateListOf<List<Offset>>()
    private val currentStroke = mutableStateListOf<Offset>()
    var revision by mutableStateOf(0)
        private set

    private fun bump() {
        revision++
    }

    val canUndo: Boolean get() = strokes.isNotEmpty()
    val isEmpty: Boolean get() = strokes.isEmpty() && currentStroke.isEmpty()

    fun beginStroke(point: Offset) {
        currentStroke.clear()
        currentStroke.add(point)
        bump()
    }

    fun appendPoint(point: Offset) {
        if (currentStroke.isEmpty()) {
            beginStroke(point)
        } else {
            currentStroke.add(point)
            bump()
        }
    }

    fun endStroke() {
        if (currentStroke.size >= 2) {
            strokes.add(currentStroke.toList())
        }
        currentStroke.clear()
        bump()
    }

    fun undo() {
        if (strokes.isNotEmpty()) {
            strokes.removeAt(strokes.lastIndex)
            bump()
        }
    }

    fun clear() {
        strokes.clear()
        currentStroke.clear()
        bump()
    }

    fun allStrokes(): List<List<Offset>> {
        val all = strokes.toList()
        return if (currentStroke.size >= 2) all + listOf(currentStroke.toList()) else all
    }

    fun exportPng(widthPx: Int, heightPx: Int): ByteArray {
        val bitmap = Bitmap.createBitmap(widthPx, heightPx, Bitmap.Config.ARGB_8888)
        val canvas = AndroidCanvas(bitmap)
        canvas.drawColor(android.graphics.Color.WHITE)
        val paint = Paint().apply {
            color = android.graphics.Color.BLACK
            strokeWidth = 6f
            style = Paint.Style.STROKE
            strokeCap = Paint.Cap.ROUND
            strokeJoin = Paint.Join.ROUND
            isAntiAlias = true
        }
        val scaleX = widthPx.toFloat()
        val scaleY = heightPx.toFloat()
        for (stroke in allStrokes()) {
            if (stroke.size < 2) continue
            val path = android.graphics.Path()
            val first = stroke.first()
            path.moveTo(first.x * scaleX, first.y * scaleY)
            stroke.drop(1).forEach { p ->
                path.lineTo(p.x * scaleX, p.y * scaleY)
            }
            canvas.drawPath(path, paint)
        }
        val stream = java.io.ByteArrayOutputStream()
        bitmap.compress(Bitmap.CompressFormat.PNG, 100, stream)
        bitmap.recycle()
        return stream.toByteArray()
    }
}

@Composable
fun rememberSignaturePadState(): SignaturePadState = remember { SignaturePadState() }

@Composable
fun SignaturePad(
    state: SignaturePadState,
    modifier: Modifier = Modifier,
) {
    val strokeWidth = 3.dp
    val density = LocalDensity.current
    @Suppress("UNUSED_VARIABLE")
    val revision = state.revision

    Canvas(
        modifier = modifier
            .fillMaxWidth()
            .aspectRatio(2.2f)
            .background(MaterialTheme.colorScheme.surface, RoundedCornerShape(12.dp))
            .border(1.dp, MaterialTheme.colorScheme.outline.copy(alpha = 0.35f), RoundedCornerShape(12.dp))
            .pointerInput(Unit) {
                detectDragGestures(
                    onDragStart = { offset ->
                        val normalized = Offset(
                            x = (offset.x / size.width).coerceIn(0f, 1f),
                            y = (offset.y / size.height).coerceIn(0f, 1f),
                        )
                        state.beginStroke(normalized)
                    },
                    onDrag = { change, _ ->
                        val normalized = Offset(
                            x = (change.position.x / size.width).coerceIn(0f, 1f),
                            y = (change.position.y / size.height).coerceIn(0f, 1f),
                        )
                        state.appendPoint(normalized)
                    },
                    onDragEnd = { state.endStroke() },
                    onDragCancel = { state.endStroke() },
                )
            },
    ) {
        val strokeStyle = Stroke(
            width = with(density) { strokeWidth.toPx() },
            cap = StrokeCap.Round,
            join = StrokeJoin.Round,
        )
        for (stroke in state.allStrokes()) {
            if (stroke.size < 2) continue
            val path = Path()
            path.moveTo(stroke.first().x * size.width, stroke.first().y * size.height)
            stroke.drop(1).forEach { p ->
                path.lineTo(p.x * size.width, p.y * size.height)
            }
            drawPath(path, Color.Black, style = strokeStyle)
        }
    }
}
