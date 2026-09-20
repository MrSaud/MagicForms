package com.magicforms.mobile.ui.home

import android.content.Intent
import android.graphics.Bitmap
import android.graphics.pdf.PdfRenderer
import android.net.Uri
import android.os.ParcelFileDescriptor
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.core.content.FileProvider
import com.magicforms.mobile.R
import com.magicforms.mobile.data.LanguagePreferences
import com.magicforms.mobile.data.api.ApiConfig
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.File

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DocumentPreviewScreen(
    title: String,
    url: String,
    bearerToken: String,
    filename: String,
    onBack: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val context = LocalContext.current
    var isLoading by remember { mutableStateOf(true) }
    var errorMessage by remember { mutableStateOf<String?>(null) }
    var pdfPages by remember { mutableStateOf<List<Bitmap>>(emptyList()) }
    var shareFile by remember { mutableStateOf<File?>(null) }

    LaunchedEffect(url, bearerToken) {
        isLoading = true
        errorMessage = null
        pdfPages = emptyList()
        shareFile = null
        try {
            val client = OkHttpClient()
            val request = Request.Builder()
                .url(url)
                .header("Authorization", "Bearer $bearerToken")
                .header("Accept-Language", LanguagePreferences.acceptLanguageHeader())
                .build()
            val response = client.newCall(request).execute()
            if (!response.isSuccessful) {
                errorMessage = "Download failed (${response.code})."
                return@LaunchedEffect
            }
            val bytes = response.body?.bytes() ?: ByteArray(0)
            val safeName = filename.ifBlank { "document.bin" }
            val temp = File(context.cacheDir, safeName)
            temp.writeBytes(bytes)
            val lower = safeName.lowercase()
            val isPdf = lower.endsWith(".pdf") || url.contains("/pdf")
            if (isPdf) {
                val fd = ParcelFileDescriptor.open(temp, ParcelFileDescriptor.MODE_READ_ONLY)
                val renderer = PdfRenderer(fd)
                val pages = mutableListOf<Bitmap>()
                for (i in 0 until renderer.pageCount) {
                    renderer.openPage(i).use { page ->
                        val bitmap = Bitmap.createBitmap(
                            page.width * 2,
                            page.height * 2,
                            Bitmap.Config.ARGB_8888,
                        )
                        page.render(bitmap, null, null, PdfRenderer.Page.RENDER_MODE_FOR_DISPLAY)
                        pages.add(bitmap)
                    }
                }
                renderer.close()
                fd.close()
                pdfPages = pages
            } else {
                shareFile = temp
            }
        } catch (e: Exception) {
            errorMessage = e.message ?: "Could not open document."
        } finally {
            isLoading = false
        }
    }

    DisposableEffect(Unit) {
        onDispose {
            pdfPages.forEach { if (!it.isRecycled) it.recycle() }
        }
    }

    Scaffold(
        modifier = modifier.fillMaxSize(),
        topBar = {
            TopAppBar(
                title = { Text(title) },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = stringResource(R.string.back))
                    }
                },
            )
        },
    ) { padding ->
        Box(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding),
        ) {
            when {
                isLoading -> CircularProgressIndicator(modifier = Modifier.align(Alignment.Center))
                errorMessage != null -> Text(
                    errorMessage!!,
                    modifier = Modifier.align(Alignment.Center).padding(24.dp),
                    color = MaterialTheme.colorScheme.error,
                )
                pdfPages.isNotEmpty() -> LazyColumn(
                    modifier = Modifier.fillMaxSize(),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                    contentPadding = androidx.compose.foundation.layout.PaddingValues(12.dp),
                ) {
                    itemsIndexed(pdfPages) { _, bitmap ->
                        Image(
                            bitmap = bitmap.asImageBitmap(),
                            contentDescription = null,
                            modifier = Modifier.fillMaxWidth(),
                        )
                    }
                }
                shareFile != null -> {
                    val file = shareFile!!
                    Column(
                        modifier = Modifier
                            .align(Alignment.Center)
                            .padding(24.dp),
                        verticalArrangement = Arrangement.spacedBy(16.dp),
                        horizontalAlignment = Alignment.CenterHorizontally,
                    ) {
                        Text(
                            stringResource(R.string.open_document_externally),
                            style = MaterialTheme.typography.bodyMedium,
                        )
                        Button(onClick = {
                            val uri: Uri = FileProvider.getUriForFile(
                                context,
                                "${context.packageName}.fileprovider",
                                file,
                            )
                            val intent = Intent(Intent.ACTION_VIEW).apply {
                                setDataAndType(uri, mimeForFilename(file.name))
                                addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                            }
                            context.startActivity(Intent.createChooser(intent, title))
                        }) {
                            Text(stringResource(R.string.open_attachment))
                        }
                    }
                }
                else -> Text(
                    stringResource(R.string.could_not_open_document),
                    modifier = Modifier.align(Alignment.Center).padding(24.dp),
                )
            }
        }
    }
}

private fun mimeForFilename(name: String): String {
    val lower = name.lowercase()
    return when {
        lower.endsWith(".pdf") -> "application/pdf"
        lower.endsWith(".docx") ->
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        lower.endsWith(".odt") -> "application/vnd.oasis.opendocument.text"
        else -> "*/*"
    }
}

data class DocumentPreviewRequest(
    val title: String,
    val url: String,
    val filename: String,
)

fun documentPreviewFromMerged(
    merged: com.magicforms.mobile.data.models.MergedDocumentRef,
    viewPdfLabel: String,
    viewDocxLabel: String,
    viewOdtLabel: String,
): List<Pair<String, DocumentPreviewRequest>> {
    val items = mutableListOf<Pair<String, DocumentPreviewRequest>>()
    if (merged.canViewPdfInline || merged.showPdfDownload) {
        items.add(
            viewPdfLabel to DocumentPreviewRequest(
                title = viewPdfLabel,
                url = ApiConfig.documentUrl(merged.pdfApiPath, inline = true),
                filename = "merged.pdf",
            ),
        )
    }
    if (merged.showDocxDownload) {
        items.add(
            viewDocxLabel to DocumentPreviewRequest(
                title = viewDocxLabel,
                url = ApiConfig.documentUrl(merged.docxApiPath),
                filename = "merged.docx",
            ),
        )
    }
    if (merged.showOdtDownload) {
        items.add(
            viewOdtLabel to DocumentPreviewRequest(
                title = viewOdtLabel,
                url = ApiConfig.documentUrl(merged.odtApiPath),
                filename = "merged.odt",
            ),
        )
    }
    return items
}

fun documentPreviewFromAttachment(
    doc: com.magicforms.mobile.data.models.SubmissionDocumentAttachment,
): DocumentPreviewRequest {
    val path = if (doc.canPreviewPdf && !doc.isPdf) doc.pdfApiPath else doc.downloadApiPath
    val inline = doc.canPreviewPdf && !doc.isPdf
    return DocumentPreviewRequest(
        title = doc.title.ifBlank { doc.filename },
        url = ApiConfig.documentUrl(path, inline = inline),
        filename = doc.filename,
    )
}
