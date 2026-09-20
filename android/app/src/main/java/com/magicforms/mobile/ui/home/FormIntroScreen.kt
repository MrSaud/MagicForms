package com.magicforms.mobile.ui.home

import android.content.Intent
import android.net.Uri
import android.webkit.WebView
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.CalendarMonth
import androidx.compose.material.icons.outlined.Description
import androidx.compose.material.icons.outlined.Info
import androidx.compose.material.icons.outlined.LocationOn
import androidx.compose.material.icons.outlined.Person
import androidx.compose.material.icons.outlined.PhotoLibrary
import androidx.compose.material.icons.outlined.PlayCircleOutline
import androidx.compose.material.icons.outlined.Sparkles
import androidx.compose.material.icons.outlined.Textsms
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import coil.compose.AsyncImage
import com.magicforms.mobile.R
import com.magicforms.mobile.data.api.HomeApi
import com.magicforms.mobile.data.models.ApiException
import com.magicforms.mobile.data.models.FormIntroPayload
import com.magicforms.mobile.ui.AuthViewModel
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

@OptIn(ExperimentalFoundationApi::class)
@Composable
fun FormIntroScreen(
    formId: Int,
    formTitle: String,
    authViewModel: AuthViewModel,
    onApply: () -> Unit,
    onBack: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val context = LocalContext.current
    val token = authViewModel.state.value.token
    var intro by remember { mutableStateOf<FormIntroPayload?>(null) }
    var isLoading by remember { mutableStateOf(true) }
    var errorMessage by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(token, formId) {
        val t = token ?: return@LaunchedEffect
        isLoading = true
        errorMessage = null
        try {
            val response = withContext(Dispatchers.IO) { HomeApi().fetchFormIntro(t, formId) }
            intro = response.intro
        } catch (e: ApiException) {
            errorMessage = e.message
        } catch (e: Exception) {
            errorMessage = e.message
        } finally {
            isLoading = false
        }
    }

    Column(modifier = modifier.fillMaxSize()) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 8.dp, vertical = 4.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            TextButton(onClick = onBack) {
                Text(stringResource(R.string.back_to_forms))
            }
            Text(
                formTitle,
                style = MaterialTheme.typography.titleMedium,
                modifier = Modifier.weight(1f),
            )
        }

        when {
            isLoading -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                CircularProgressIndicator()
            }
            errorMessage != null -> Box(Modifier.fillMaxSize().padding(24.dp), contentAlignment = Alignment.Center) {
                Text(errorMessage ?: "")
            }
            intro != null -> {
                val data = intro!!
                Column(
                    modifier = Modifier
                        .weight(1f)
                        .verticalScroll(rememberScrollState())
                        .padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(16.dp),
                ) {
                    Text(data.headline, style = MaterialTheme.typography.headlineSmall)
                    if (data.tagline.isNotBlank()) {
                        Text(data.tagline, style = MaterialTheme.typography.bodyLarge, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                    if (data.gallery.isNotEmpty()) {
                        introSection(stringResource(R.string.gallery), Icons.Outlined.PhotoLibrary) {
                        val pagerState = rememberPagerState(pageCount = { data.gallery.size })
                        HorizontalPager(state = pagerState, modifier = Modifier.fillMaxWidth().height(220.dp)) { page ->
                            val item = data.gallery[page]
                            Box {
                                AsyncImage(
                                    model = item.imageUrl,
                                    contentDescription = item.alt,
                                    modifier = Modifier.fillMaxSize(),
                                    contentScale = ContentScale.Crop,
                                )
                                if (item.caption.isNotBlank()) {
                                    Text(
                                        item.caption,
                                        modifier = Modifier
                                            .align(Alignment.BottomCenter)
                                            .fillMaxWidth()
                                            .padding(8.dp),
                                        style = MaterialTheme.typography.bodySmall,
                                        color = MaterialTheme.colorScheme.onPrimary,
                                    )
                                }
                            }
                        }
                        }
                    }
                    if (data.messageHtml.isNotBlank()) {
                        introSection(stringResource(R.string.about), Icons.Outlined.Textsms) {
                        AndroidView(
                            factory = { WebView(it).apply { settings.javaScriptEnabled = false } },
                            update = { web ->
                                web.loadDataWithBaseURL(
                                    null,
                                    """<html><body style="font-family:sans-serif;font-size:14px;">${data.messageHtml}</body></html>""",
                                    "text/html",
                                    "UTF-8",
                                    null,
                                )
                            },
                            modifier = Modifier.fillMaxWidth().height(120.dp),
                        )
                        }
                    }
                    if (
                        data.registerBy.label.isNotBlank() ||
                        data.registration.fee.isNotBlank() ||
                        data.registration.showCapacity && data.registration.capacity != null
                    ) {
                        introSection(stringResource(R.string.registration_info), Icons.Outlined.Description) {
                            if (data.registerBy.label.isNotBlank()) introRow(stringResource(R.string.register_by), data.registerBy.label)
                            if (data.registration.fee.isNotBlank()) introRow(stringResource(R.string.fee), data.registration.fee)
                            if (data.registration.showCapacity) data.registration.capacity?.let { cap ->
                                val seats = data.registration.seatsRemaining?.let { "$it / $cap" } ?: cap.toString()
                                introRow(stringResource(R.string.capacity), seats)
                            }
                        }
                    }
                    if (data.schedule.startsLabel.isNotBlank() || data.schedule.endsLabel.isNotBlank()) {
                        introSection(stringResource(R.string.schedule), Icons.Outlined.CalendarMonth) {
                            if (data.schedule.startsLabel.isNotBlank()) introRow(stringResource(R.string.starts), data.schedule.startsLabel)
                            if (data.schedule.endsLabel.isNotBlank()) introRow(stringResource(R.string.ends), data.schedule.endsLabel)
                        }
                    }
                    val w = data.where
                    if (w.formatLabel.isNotBlank() || w.location.isNotBlank() || w.mapUrl.isNotBlank()) {
                        introSection(stringResource(R.string.where_section), Icons.Outlined.LocationOn) {
                            if (w.formatLabel.isNotBlank()) introRow(stringResource(R.string.format), w.formatLabel)
                            if (w.location.isNotBlank()) introRow(stringResource(R.string.location), w.location)
                            if (w.mapUrl.isNotBlank()) {
                                TextButton(onClick = {
                                    context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(w.mapUrl)))
                                }) { Text(stringResource(R.string.view_on_map)) }
                            }
                        }
                    }
                    val c = data.contact
                    if (c.name.isNotBlank() || c.email.isNotBlank() || c.phone.isNotBlank()) {
                        introSection(stringResource(R.string.get_in_touch), Icons.Outlined.Person) {
                            if (c.name.isNotBlank()) introRow(stringResource(R.string.contact), c.name)
                            if (c.email.isNotBlank()) {
                                TextButton(onClick = {
                                    context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("mailto:${c.email}")))
                                }) { Text(c.email) }
                            }
                            if (c.phone.isNotBlank()) {
                                TextButton(onClick = {
                                    context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("tel:${c.phone}")))
                                }) { Text(c.phone) }
                            }
                        }
                    }
                    if (data.highlights.isNotEmpty()) {
                        introSection(stringResource(R.string.highlights), Icons.Outlined.Sparkles) {
                            introListItems(data.highlights, data.highlightsListStyle)
                        }
                    }
                    data.brochureUrl?.takeIf { it.isNotBlank() }?.let { url ->
                        TextButton(onClick = {
                            context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
                        }) { Text(stringResource(R.string.download_brochure)) }
                    }
                    if (data.guidelines.isNotEmpty()) {
                        introSection(stringResource(R.string.guidelines), Icons.Outlined.Info) {
                            introListItems(data.guidelines, data.guidelinesListStyle)
                        }
                    }
                    data.video?.watchUrl?.takeIf { it.isNotBlank() }?.let { url ->
                        introSection(stringResource(R.string.featured_video), Icons.Outlined.PlayCircleOutline) {
                            TextButton(onClick = {
                                context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
                            }) { Text(stringResource(R.string.open_video)) }
                        }
                    }
                    if (data.closed) {
                        Text(
                            stringResource(R.string.registration_closed),
                            color = MaterialTheme.colorScheme.error,
                            style = MaterialTheme.typography.bodyMedium,
                        )
                    } else if (data.canApply) {
                        Button(onClick = onApply, modifier = Modifier.fillMaxWidth()) {
                            Text(data.applyLabel.ifBlank { stringResource(R.string.apply_now) })
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun introSection(
    title: String,
    icon: ImageVector? = null,
    content: @Composable () -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Row(
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            if (icon != null) {
                Icon(
                    icon,
                    contentDescription = null,
                    tint = MaterialTheme.colorScheme.primary,
                    modifier = Modifier.height(22.dp),
                )
            }
            Text(title, style = MaterialTheme.typography.titleMedium)
        }
        content()
    }
}

@Composable
private fun introListItems(items: List<String>, listStyle: String) {
    val ordered = listStyle == "ordered"
    items.forEachIndexed { index, text ->
        val prefix = if (ordered) "${index + 1}. " else "• "
        Text(prefix + text, style = MaterialTheme.typography.bodyMedium)
    }
}

@Composable
private fun introRow(label: String, value: String) {
    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(label, style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.weight(0.35f))
        Text(value, style = MaterialTheme.typography.bodyMedium, modifier = Modifier.weight(0.65f))
    }
}
