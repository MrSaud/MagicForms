package com.magicforms.mobile.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.magicforms.mobile.R

@Composable
fun LanguagePicker(
    currentTag: String,
    onLanguageChange: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(modifier = modifier.fillMaxWidth()) {
        Text(
            text = stringResource(R.string.language),
            style = MaterialTheme.typography.labelLarge,
            modifier = Modifier.padding(bottom = 8.dp),
        )
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            FilterChip(
                selected = currentTag == "en",
                onClick = { onLanguageChange("en") },
                label = { Text(stringResource(R.string.english)) },
            )
            FilterChip(
                selected = currentTag == "ar",
                onClick = { onLanguageChange("ar") },
                label = { Text(stringResource(R.string.arabic)) },
            )
        }
    }
}
