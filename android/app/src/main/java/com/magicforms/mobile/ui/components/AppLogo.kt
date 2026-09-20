package com.magicforms.mobile.ui.components

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.TextUnit
import androidx.compose.ui.unit.sp

/** Wordmark matching Django `sforms-logo.svg` (blue S, dark Forms). */
@Composable
fun AppLogo(
    modifier: Modifier = Modifier,
    fontSize: TextUnit = 22.sp,
) {
    val text = buildAnnotatedString {
        withStyle(SpanStyle(color = Color(0xFF0071E3), fontWeight = FontWeight.Bold)) {
            append("S")
        }
        withStyle(SpanStyle(color = Color(0xFF1D1D1F), fontWeight = FontWeight.Bold)) {
            append("Forms")
        }
    }
    Text(
        text = text,
        modifier = modifier,
        style = MaterialTheme.typography.headlineMedium.copy(
            fontSize = fontSize,
            letterSpacing = (-0.04).sp,
        ),
    )
}
