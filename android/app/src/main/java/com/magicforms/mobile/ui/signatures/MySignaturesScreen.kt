package com.magicforms.mobile.ui.signatures

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.unit.dp
import com.magicforms.mobile.data.api.SignatureApi
import com.magicforms.mobile.data.models.ApiException
import com.magicforms.mobile.data.models.UserSignatureItem
import com.magicforms.mobile.ui.AuthViewModel
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

@Composable
fun MySignaturesScreen(
    authViewModel: AuthViewModel,
    modifier: Modifier = Modifier,
) {
    val scope = rememberCoroutineScope()
    val signatureApi = remember { SignatureApi() }
    val padState = rememberSignaturePadState()
    val config = LocalConfiguration.current
    val exportWidthPx = (config.screenWidthDp * config.densityDpi / 160f).toInt().coerceAtLeast(400)

    var signatures by remember { mutableStateOf<List<UserSignatureItem>>(emptyList()) }
    var limit by remember { mutableIntStateOf(200) }
    var label by remember { mutableStateOf("") }
    var editingId by remember { mutableStateOf<Int?>(null) }
    var isLoading by remember { mutableStateOf(true) }
    var isSaving by remember { mutableStateOf(false) }
    var errorMessage by remember { mutableStateOf<String?>(null) }
    var successMessage by remember { mutableStateOf<String?>(null) }

    fun loadSignatures() {
        val token = authViewModel.state.value.token ?: return
        scope.launch {
            isLoading = true
            errorMessage = null
            try {
                val response = withContext(Dispatchers.IO) {
                    signatureApi.fetchSignatures(token)
                }
                signatures = response.signatures
                limit = response.limit
            } catch (e: ApiException) {
                errorMessage = e.message
            } catch (e: Exception) {
                errorMessage = e.message ?: "Failed to load signatures."
            } finally {
                isLoading = false
            }
        }
    }

    LaunchedEffect(Unit) { loadSignatures() }

    Box(modifier = modifier.fillMaxSize()) {
        LazyColumn(
            modifier = Modifier.fillMaxSize(),
            contentPadding = androidx.compose.foundation.layout.PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            successMessage?.let { msg ->
                item { Text(msg, color = MaterialTheme.colorScheme.primary) }
            }
            errorMessage?.let { msg ->
                item { Text(msg, color = MaterialTheme.colorScheme.error) }
            }

            item {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(
                        if (editingId == null) "Draw a new signature" else "Redraw selected signature",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    SignaturePad(state = padState)
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        OutlinedButton(
                            onClick = { padState.undo() },
                            enabled = padState.canUndo && !isSaving,
                        ) { Text("Undo") }
                        OutlinedButton(
                            onClick = { padState.clear() },
                            enabled = !padState.isEmpty && !isSaving,
                        ) { Text("Clear") }
                        Button(
                            onClick = {
                                val token = authViewModel.state.value.token ?: return@Button
                                if (editingId == null && signatures.size >= limit) {
                                    errorMessage = "You reached the maximum number of signatures ($limit)."
                                    return@Button
                                }
                                isSaving = true
                                errorMessage = null
                                successMessage = null
                                scope.launch {
                                    try {
                                        val heightPx = (exportWidthPx / 2.2f).toInt().coerceAtLeast(120)
                                        val png = padState.exportPng(exportWidthPx, heightPx)
                                        withContext(Dispatchers.IO) {
                                            signatureApi.uploadSignature(
                                                token = token,
                                                pngBytes = png,
                                                label = label.trim(),
                                                replaceSignatureId = editingId,
                                            )
                                        }
                                        successMessage = if (editingId == null) "Signature added." else "Signature updated."
                                        editingId = null
                                        label = ""
                                        padState.clear()
                                        loadSignatures()
                                    } catch (e: ApiException) {
                                        errorMessage = e.message
                                    } catch (e: Exception) {
                                        errorMessage = e.message ?: "Failed to save signature."
                                    } finally {
                                        isSaving = false
                                    }
                                }
                            },
                            enabled = !padState.isEmpty && !isSaving,
                            modifier = Modifier.weight(1f),
                        ) {
                            Text(if (editingId == null) "Add new" else "Save")
                        }
                    }
                    OutlinedTextField(
                        value = label,
                        onValueChange = { label = it },
                        label = { Text("Label (optional)") },
                        modifier = Modifier.fillMaxWidth(),
                        enabled = !isSaving,
                    )
                    if (editingId != null) {
                        TextButton(onClick = {
                            editingId = null
                            label = ""
                            padState.clear()
                        }) { Text("Cancel edit") }
                    }
                }
            }

            item {
                Text("Your signatures", style = MaterialTheme.typography.titleMedium)
            }

            if (signatures.isEmpty() && !isLoading) {
                item {
                    Text(
                        "No signatures yet. Draw one above and tap Add new.",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }

            items(signatures, key = { it.id }) { sig ->
                SignatureListRow(
                    sig = sig,
                    isSaving = isSaving,
                    onEdit = {
                        editingId = sig.id
                        label = sig.label
                        padState.clear()
                    },
                    onSetPrimary = {
                        val token = authViewModel.state.value.token ?: return@SignatureListRow
                        isSaving = true
                        scope.launch {
                            try {
                                withContext(Dispatchers.IO) {
                                    signatureApi.setPrimary(token, sig.id)
                                }
                                successMessage = "Primary signature updated."
                                loadSignatures()
                            } catch (e: ApiException) {
                                errorMessage = e.message
                            } catch (e: Exception) {
                                errorMessage = e.message ?: "Failed to update primary."
                            } finally {
                                isSaving = false
                            }
                        }
                    },
                    onRemove = {
                        val token = authViewModel.state.value.token ?: return@SignatureListRow
                        isSaving = true
                        scope.launch {
                            try {
                                withContext(Dispatchers.IO) {
                                    signatureApi.deleteSignature(token, sig.id)
                                }
                                if (editingId == sig.id) {
                                    editingId = null
                                    label = ""
                                    padState.clear()
                                }
                                successMessage = "Signature removed."
                                loadSignatures()
                            } catch (e: ApiException) {
                                errorMessage = e.message
                            } catch (e: Exception) {
                                errorMessage = e.message ?: "Failed to remove signature."
                            } finally {
                                isSaving = false
                            }
                        }
                    },
                )
            }
        }

        if (isLoading) {
            CircularProgressIndicator(modifier = Modifier.align(Alignment.Center))
        }
    }
}

@Composable
private fun SignatureListRow(
    sig: UserSignatureItem,
    isSaving: Boolean,
    onEdit: () -> Unit,
    onSetPrimary: () -> Unit,
    onRemove: () -> Unit,
) {
    Column(
        modifier = Modifier.fillMaxWidth(),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Column(modifier = Modifier.weight(1f)) {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(
                        if (sig.label.isNotBlank()) sig.label else "(no label)",
                        style = MaterialTheme.typography.titleSmall,
                    )
                    if (sig.isPrimary) {
                        Text(
                            "Primary",
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.primary,
                        )
                    }
                }
                Text(sig.createdAtLabel, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            TextButton(onClick = onEdit, enabled = !isSaving) { Text("Edit") }
            if (!sig.isPrimary) {
                TextButton(onClick = onSetPrimary, enabled = !isSaving) { Text("Set primary") }
            }
            TextButton(onClick = onRemove, enabled = !isSaving) { Text("Remove") }
        }
    }
}
