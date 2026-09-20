package com.magicforms.mobile.ui.home

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyListScope
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.magicforms.mobile.R
import com.magicforms.mobile.data.api.ApiConfig
import com.magicforms.mobile.data.api.HomeApi
import com.magicforms.mobile.data.models.ApiException
import com.magicforms.mobile.data.models.InboxDetailResponse
import com.magicforms.mobile.data.models.SubmissionDocumentAttachment
import com.magicforms.mobile.data.models.SubmissionDocumentsBlock
import com.magicforms.mobile.data.models.SubmissionFieldValue
import com.magicforms.mobile.data.models.SubmissionThreadBlock
import com.magicforms.mobile.data.models.SubmissionTimelineEvent
import com.magicforms.mobile.data.models.ThreadMessage
import com.magicforms.mobile.ui.AuthViewModel
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

@Composable
fun InboxDetailScreen(
    submissionId: Int,
    authViewModel: AuthViewModel,
    onDone: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val scope = rememberCoroutineScope()
    val homeApi = remember { HomeApi() }
    var detail by remember { mutableStateOf<InboxDetailResponse?>(null) }
    var isLoading by remember { mutableStateOf(true) }
    var isPostingThread by remember { mutableStateOf(false) }
    var errorMessage by remember { mutableStateOf<String?>(null) }
    var threadDraft by remember { mutableStateOf("") }
    var documentPreview by remember { mutableStateOf<DocumentPreviewRequest?>(null) }

    fun loadDetail() {
        val token = authViewModel.state.value.token ?: return
        scope.launch {
            isLoading = true
            errorMessage = null
            try {
                detail = withContext(Dispatchers.IO) {
                    homeApi.fetchInboxDetail(token, submissionId)
                }
            } catch (e: ApiException) {
                errorMessage = e.message
            } catch (e: Exception) {
                errorMessage = e.message ?: "Failed to load."
            } finally {
                isLoading = false
            }
        }
    }

    LaunchedEffect(submissionId) { loadDetail() }

    val token = authViewModel.state.value.token
    val preview = documentPreview
    if (preview != null && token != null) {
        DocumentPreviewScreen(
            title = preview.title,
            url = preview.url,
            bearerToken = token,
            filename = preview.filename,
            onBack = { documentPreview = null },
            modifier = modifier,
        )
        return
    }

    Box(modifier = modifier.fillMaxSize()) {
        when {
            isLoading && detail == null -> {
                CircularProgressIndicator(modifier = Modifier.align(Alignment.Center))
            }
            detail != null -> {
                DetailContent(
                    detail = detail!!,
                    onOpenDocument = { documentPreview = it },
                    threadDraft = threadDraft,
                    onThreadDraftChange = { threadDraft = it },
                    errorMessage = errorMessage,
                    isPostingThread = isPostingThread,
                    onPostThread = {
                        val token = authViewModel.state.value.token ?: return@DetailContent
                        val body = threadDraft.trim()
                        if (body.isEmpty()) return@DetailContent
                        scope.launch {
                            isPostingThread = true
                            errorMessage = null
                            try {
                                val response = withContext(Dispatchers.IO) {
                                    homeApi.postThreadMessage(token, submissionId, body)
                                }
                                detail = response
                                threadDraft = ""
                                authViewModel.refreshInbox()
                            } catch (e: ApiException) {
                                errorMessage = e.message
                            } catch (e: Exception) {
                                errorMessage = e.message ?: "Failed to post."
                            } finally {
                                isPostingThread = false
                            }
                        }
                    },
                )
            }
            else -> {
                Text(
                    errorMessage ?: stringResource(R.string.could_not_load),
                    modifier = Modifier.align(Alignment.Center).padding(24.dp),
                    color = MaterialTheme.colorScheme.error,
                )
            }
        }
        if (isPostingThread) {
            CircularProgressIndicator(modifier = Modifier.align(Alignment.Center))
        }
    }
}

@Composable
private fun DetailContent(
    detail: InboxDetailResponse,
    threadDraft: String,
    onThreadDraftChange: (String) -> Unit,
    errorMessage: String?,
    isPostingThread: Boolean,
    onPostThread: () -> Unit,
    onOpenDocument: (DocumentPreviewRequest) -> Unit,
) {
    val sub = detail.submission
    val context = LocalContext.current
    val viewPdf = stringResource(R.string.view_pdf)
    val viewDocx = stringResource(R.string.view_docx)
    val viewOdt = stringResource(R.string.view_odt)
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = androidx.compose.foundation.layout.PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        errorMessage?.let { item { Text(it, color = MaterialTheme.colorScheme.error) } }

        item {
            SectionTitle(stringResource(R.string.request_section))
            DetailLine(stringResource(R.string.reference), sub.referenceToken)
            DetailLine(stringResource(R.string.status), sub.workflowStateLabel)
            DetailLine(stringResource(R.string.submitted_label), sub.submittedAtLabel)
            if (sub.submitter.isNotBlank()) DetailLine(stringResource(R.string.from), sub.submitter)
            if (sub.submitterEmail.isNotBlank()) DetailLine(stringResource(R.string.email), sub.submitterEmail)
            if (sub.currentStepLabel.isNotBlank()) DetailLine(stringResource(R.string.current_step), sub.currentStepLabel)
            DetailLine(stringResource(R.string.organization), sub.form.entityName)
            if (sub.canAct && sub.actingAsDelegate) {
                Text(
                    stringResource(R.string.delegate_notice),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(top = 8.dp),
                )
            }
        }

        detail.thread?.let { thread ->
            item { ThreadSection(thread, threadDraft, onThreadDraftChange, isPostingThread, onPostThread) }
        }

        detail.documents?.let { documents ->
            documentsSectionItems(
                documents = documents,
                mergedTitle = stringResource(R.string.merged_document),
                attachedTitle = stringResource(R.string.attached_documents),
                viewPdf = viewPdf,
                viewDocx = viewDocx,
                viewOdt = viewOdt,
                onOpenDocument = onOpenDocument,
            )
        }

        if (detail.values.isNotEmpty()) {
            item { SectionTitle(stringResource(R.string.responses)) }
            items(detail.values, key = { it.valueId.takeIf { id -> id > 0 } ?: it.fieldName.hashCode() }) { field ->
                FieldRow(
                    field = field,
                    onOpenUrl = { url ->
                        runCatching {
                            context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
                        }
                    },
                    onOpenDocument = onOpenDocument,
                )
            }
        }

        if (detail.events.isNotEmpty()) {
            item { SectionTitle(stringResource(R.string.timeline)) }
            items(detail.events, key = { it.id }) { event ->
                EventRow(event)
            }
        }
    }
}

@Composable
private fun ThreadSection(
    thread: SubmissionThreadBlock,
    threadDraft: String,
    onThreadDraftChange: (String) -> Unit,
    isPostingThread: Boolean,
    onPostThread: () -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        SectionTitle(stringResource(R.string.thread))
        if (thread.messages.isEmpty()) {
            Text(
                stringResource(R.string.thread_messages),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        thread.messages.forEach { msg -> ThreadMessageRow(msg) }
        if (thread.canPost) {
            OutlinedTextField(
                value = threadDraft,
                onValueChange = onThreadDraftChange,
                label = { Text(stringResource(R.string.add_message)) },
                modifier = Modifier.fillMaxWidth(),
                minLines = 2,
            )
            Button(
                onClick = onPostThread,
                enabled = !isPostingThread && threadDraft.isNotBlank(),
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text(stringResource(R.string.post))
            }
        }
    }
}

@Composable
private fun ThreadMessageRow(msg: ThreadMessage) {
    Column(modifier = Modifier.padding(vertical = 4.dp)) {
        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Text(msg.authorDisplay.ifBlank { msg.authorUsername }, style = MaterialTheme.typography.titleSmall)
            Text(msg.createdAtLabel, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        Text(msg.body, style = MaterialTheme.typography.bodyMedium)
    }
}

@Composable
private fun SectionTitle(title: String) {
    Text(title, style = MaterialTheme.typography.titleSmall, color = MaterialTheme.colorScheme.primary)
}

@Composable
private fun DetailLine(label: String, value: String) {
    Row(
        modifier = Modifier.fillMaxWidth().padding(vertical = 2.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        Text(label, color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.bodySmall)
        Text(value, style = MaterialTheme.typography.bodyMedium)
    }
}

private fun LazyListScope.documentsSectionItems(
    documents: SubmissionDocumentsBlock,
    mergedTitle: String,
    attachedTitle: String,
    viewPdf: String,
    viewDocx: String,
    viewOdt: String,
    onOpenDocument: (DocumentPreviewRequest) -> Unit,
) {
    val merged = documents.merged
    if (merged != null && merged.hasMergeOutput) {
        item { SectionTitle(mergedTitle) }
        documentPreviewFromMerged(merged, viewPdf, viewDocx, viewOdt).forEach { (label, request) ->
            item {
                Text(
                    label,
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.primary,
                    modifier = Modifier
                        .fillMaxWidth()
                        .clickable { onOpenDocument(request) }
                        .padding(vertical = 6.dp),
                )
            }
        }
    }
    if (documents.attachments.isNotEmpty()) {
        item { SectionTitle(attachedTitle) }
        items(documents.attachments, key = { it.id }) { doc ->
            DocumentAttachmentRow(doc, onOpenDocument)
        }
    }
}

@Composable
private fun DocumentAttachmentRow(
    doc: SubmissionDocumentAttachment,
    onOpenDocument: (DocumentPreviewRequest) -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .clickable { onOpenDocument(documentPreviewFromAttachment(doc)) }
            .padding(vertical = 6.dp),
    ) {
        Text(
            doc.title.ifBlank { doc.filename },
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.primary,
        )
        if (doc.title.isNotBlank()) {
            Text(
                doc.filename,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

@Composable
private fun FieldRow(
    field: SubmissionFieldValue,
    onOpenUrl: (String) -> Unit,
    onOpenDocument: (DocumentPreviewRequest) -> Unit,
) {
    Column(modifier = Modifier.padding(vertical = 4.dp)) {
        Text(field.fieldLabel, style = MaterialTheme.typography.titleSmall)
        val attachment = field.attachment
        if (field.fieldType == "file" && attachment != null) {
            val label = attachment.filename.ifBlank { stringResource(R.string.open_attachment) }
            if (attachment.apiPath.isNotBlank()) {
                Text(
                    label,
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.primary,
                    modifier = Modifier.clickable {
                        onOpenDocument(
                            DocumentPreviewRequest(
                                title = label,
                                url = ApiConfig.documentUrl(attachment.apiPath),
                                filename = attachment.filename.ifBlank { "attachment" },
                            ),
                        )
                    },
                )
            } else if (attachment.downloadUrl.isNotBlank()) {
                Text(
                    label,
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.primary,
                    modifier = Modifier.clickable { onOpenUrl(attachment.downloadUrl) },
                )
            }
        } else {
            Text(
                field.displayValue.ifBlank { "—" },
                style = MaterialTheme.typography.bodyMedium,
                color = if (field.displayValue.isBlank()) MaterialTheme.colorScheme.onSurfaceVariant else MaterialTheme.colorScheme.onSurface,
            )
        }
    }
}

@Composable
private fun EventRow(event: SubmissionTimelineEvent) {
    Column(modifier = Modifier.padding(vertical = 6.dp)) {
        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Text(event.kindLabel, style = MaterialTheme.typography.titleSmall)
            Text(event.createdAtLabel, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        if (event.stepLabel.isNotBlank()) {
            Text(event.stepLabel, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        if (event.author.isNotBlank()) {
            Text(event.author, style = MaterialTheme.typography.bodySmall)
        }
        if (event.message.isNotBlank()) {
            Text(event.message, style = MaterialTheme.typography.bodySmall)
        }
    }
}

