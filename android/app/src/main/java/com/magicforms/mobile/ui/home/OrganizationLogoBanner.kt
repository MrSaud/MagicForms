package com.magicforms.mobile.ui.home

import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.layout.wrapContentSize
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.unit.dp
import coil.compose.AsyncImage

@Composable
fun OrganizationLogoBanner(
    logoUrl: String,
    contentDescription: String,
    modifier: Modifier = Modifier,
) {
    AsyncImage(
        model = logoUrl,
        contentDescription = contentDescription,
        modifier = modifier
            .fillMaxWidth()
            .wrapContentSize(Alignment.Center)
            .widthIn(max = 220.dp)
            .heightIn(max = 40.dp)
            .padding(horizontal = 16.dp, vertical = 8.dp),
        contentScale = ContentScale.Fit,
    )
}
