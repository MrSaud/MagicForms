package com.magicforms.mobile.ui.home

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DatePicker
import androidx.compose.material3.DatePickerDialog
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberDatePickerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
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
import com.magicforms.mobile.data.FormDraftStore
import com.magicforms.mobile.data.SessionExpiredException
import com.magicforms.mobile.data.api.FormSubmitApi
import com.magicforms.mobile.data.api.FormSubmitValidationException
import com.magicforms.mobile.data.models.ApiException
import java.io.IOException
import com.magicforms.mobile.data.models.FormFieldSchema
import com.magicforms.mobile.data.models.FormSchemaResponse
import com.magicforms.mobile.ui.AuthViewModel
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun FormSubmitScreen(
    formTitle: String,
    authViewModel: AuthViewModel,
    onDone: () -> Unit,
    onViewSubmission: (Int) -> Unit = {},
    formId: Int? = null,
    relatedAccessToken: String? = null,
    modifier: Modifier = Modifier,
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val token = authViewModel.state.value.token

    var schema by remember { mutableStateOf<FormSchemaResponse?>(null) }
    var loadError by remember { mutableStateOf<String?>(null) }
    var isLoading by remember { mutableStateOf(true) }
    var isSubmitting by remember { mutableStateOf(false) }
    var submitError by remember { mutableStateOf<String?>(null) }
    var successSubmissionId by remember { mutableStateOf<Int?>(null) }
    val fieldErrors = remember { mutableStateMapOf<String, List<String>>() }

    val textValues = remember { mutableStateMapOf<String, String>() }
    val boolValues = remember { mutableStateMapOf<String, Boolean>() }
    val checklistValues = remember { mutableStateMapOf<String, MutableSet<String>>() }
    val fileSelections = remember { mutableStateMapOf<String, Pair<ByteArray, String>>() }

    var filePickKey by remember { mutableStateOf<String?>(null) }
    val draftKey = remember(formId, relatedAccessToken) {
        FormDraftStore.storageKey(formId) ?: FormDraftStore.storageKey(relatedAccessToken)
    }
    val filePicker = rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { uri: Uri? ->
        val key = filePickKey ?: return@rememberLauncherForActivityResult
        if (uri == null) return@rememberLauncherForActivityResult
        runCatching {
            context.contentResolver.openInputStream(uri)?.use { stream ->
                val bytes = stream.readBytes()
                val name = uri.lastPathSegment?.substringAfterLast('/') ?: "upload"
                fileSelections[key] = bytes to name
            }
        }
        filePickKey = null
    }

    LaunchedEffect(textValues.size, boolValues.size, checklistValues.size) {
        kotlinx.coroutines.delay(1500)
        FormDraftStore.save(context, draftKey, textValues, boolValues, checklistValues)
    }

    LaunchedEffect(formId, relatedAccessToken, token) {
        val t = token ?: return@LaunchedEffect
        isLoading = true
        loadError = null
        try {
            val loaded = withContext(Dispatchers.IO) {
                val api = FormSubmitApi()
                when {
                    relatedAccessToken != null -> api.fetchRelatedSchema(t, relatedAccessToken)
                    formId != null -> api.fetchSchema(t, formId)
                    else -> error("Invalid form")
                }
            }
            schema = loaded
            applyInitial(loaded, textValues, boolValues, checklistValues)
            FormDraftStore.load(context, draftKey)?.let { draft ->
                draft.textValues.forEach { (k, v) ->
                    if (textValues[k].isNullOrBlank()) textValues[k] = v
                }
                draft.boolValues.forEach { (k, v) -> boolValues[k] = v }
                draft.checklistValues.forEach { (k, v) -> checklistValues[k] = v.toMutableSet() }
            }
        } catch (e: ApiException) {
            loadError = e.message
        } catch (e: Exception) {
            loadError = e.message ?: "Could not load form."
        } finally {
            isLoading = false
        }
    }

    Column(modifier = modifier.fillMaxSize()) {
        when {
            isLoading -> {
                Column(
                    modifier = Modifier.fillMaxSize(),
                    verticalArrangement = Arrangement.Center,
                    horizontalAlignment = Alignment.CenterHorizontally,
                ) {
                    CircularProgressIndicator()
                    Text("Loading form…", modifier = Modifier.padding(top = 12.dp))
                }
            }
            loadError != null -> {
                Column(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(24.dp),
                    verticalArrangement = Arrangement.Center,
                    horizontalAlignment = Alignment.CenterHorizontally,
                ) {
                    Text("Could not load form", style = MaterialTheme.typography.titleMedium)
                    Text(loadError.orEmpty(), color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
            schema != null && schema!!.status != "open" -> {
                Column(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(24.dp),
                    verticalArrangement = Arrangement.Center,
                    horizontalAlignment = Alignment.CenterHorizontally,
                ) {
                    Text("Not available", style = MaterialTheme.typography.titleMedium)
                    Text(
                        schema!!.statusMessage.ifBlank { "This form cannot be submitted." },
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
            successSubmissionId != null -> {
                val submissionId = successSubmissionId!!
                Column(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(24.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp, Alignment.CenterVertically),
                    horizontalAlignment = Alignment.CenterHorizontally,
                ) {
                    Text(stringResource(R.string.submitted), style = MaterialTheme.typography.titleLarge)
                    Text(
                        stringResource(R.string.submitted_desc),
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    Button(onClick = { onViewSubmission(submissionId) }) {
                        Text(stringResource(R.string.view_submission))
                    }
                    TextButton(onClick = onDone) { Text(stringResource(R.string.done)) }
                }
            }
            schema != null -> {
                val s = schema!!
                Column(
                    modifier = Modifier
                        .fillMaxSize()
                        .verticalScroll(rememberScrollState())
                        .padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(16.dp),
                ) {
                    Text(formTitle, style = MaterialTheme.typography.titleLarge)
                    submitError?.let {
                        Text(it, color = MaterialTheme.colorScheme.error)
                    }
                    s.sections.sortedBy { it.order }.forEach { section ->
                        val sectionFields = s.fields.filter {
                            it.sectionId == section.id && isVisible(it, s, textValues, boolValues, checklistValues)
                        }
                        if (sectionFields.isNotEmpty()) {
                            Text(section.title, style = MaterialTheme.typography.titleMedium)
                            if (section.description.isNotBlank()) {
                                Text(section.description, style = MaterialTheme.typography.bodySmall)
                            }
                            sectionFields.forEach { field ->
                                FieldEditor(
                                    field = field,
                                    textValues = textValues,
                                    boolValues = boolValues,
                                    checklistValues = checklistValues,
                                    fileSelections = fileSelections,
                                    fieldErrors = fieldErrors,
                                    onPickFile = {
                                        filePickKey = field.key
                                        filePicker.launch("*/*")
                                    },
                                )
                            }
                        }
                    }
                    s.fields.filter { it.sectionId == null && isVisible(it, s, textValues, boolValues, checklistValues) }
                        .forEach { field ->
                            FieldEditor(
                                field = field,
                                textValues = textValues,
                                boolValues = boolValues,
                                checklistValues = checklistValues,
                                fileSelections = fileSelections,
                                fieldErrors = fieldErrors,
                                onPickFile = {
                                    filePickKey = field.key
                                    filePicker.launch("*/*")
                                },
                            )
                        }
                }
                Button(
                    onClick = {
                        val t = token ?: return@Button
                        scope.launch {
                            isSubmitting = true
                            submitError = null
                            fieldErrors.clear()
                            try {
                                val textPayload = mutableMapOf<String, String>()
                                val checkboxPayload = mutableMapOf<String, Boolean>()
                                val checklistPayload = mutableMapOf<String, List<String>>()
                                val files = mutableMapOf<String, Pair<ByteArray, String>>()
                                s.fields.filter { isVisible(it, s, textValues, boolValues, checklistValues) }
                                    .forEach { field ->
                                        when (field.fieldType) {
                                            "checkbox" -> checkboxPayload[field.key] = boolValues[field.key] == true
                                            "checklist" -> checklistPayload[field.key] =
                                                (checklistValues[field.key] ?: emptySet()).sorted()
                                            "file" -> fileSelections[field.key]?.let { files[field.key] = it }
                                            else -> textPayload[field.key] = textValues[field.key].orEmpty()
                                        }
                                    }
                                val result = withContext(Dispatchers.IO) {
                                    val api = FormSubmitApi()
                                    when {
                                        relatedAccessToken != null -> api.submitRelated(
                                            t,
                                            relatedAccessToken,
                                            textPayload,
                                            checkboxPayload,
                                            checklistPayload,
                                            files,
                                        )
                                        formId != null -> api.submit(
                                            t,
                                            formId,
                                            textPayload,
                                            checkboxPayload,
                                            checklistPayload,
                                            files,
                                        )
                                        else -> error("Invalid form")
                                    }
                                }
                                FormDraftStore.clear(context, draftKey)
                                successSubmissionId = result.submission?.id
                                authViewModel.loadHomeData()
                            } catch (e: FormSubmitValidationException) {
                                submitError = e.message
                                fieldErrors.putAll(e.fieldErrors)
                            } catch (e: SessionExpiredException) {
                                authViewModel.handleSessionExpired()
                            } catch (e: ApiException) {
                                submitError = e.message
                            } catch (e: IOException) {
                                if (files.isNotEmpty()) {
                                    submitError = context.getString(R.string.offline_files_not_queued)
                                } else {
                                    authViewModel.offlineQueue().enqueue(
                                        authViewModel.offlineQueue().newItem(
                                            kind = if (relatedAccessToken != null) "related" else "form",
                                            formId = formId,
                                            relatedAccessToken = relatedAccessToken,
                                            textFields = textPayload,
                                            checkboxFields = checkboxPayload,
                                            checklistFields = checklistPayload,
                                        ),
                                    )
                                    FormDraftStore.clear(context, draftKey)
                                    authViewModel.refreshPendingSyncCount()
                                    submitError = context.getString(R.string.queued_offline)
                                }
                            } catch (e: Exception) {
                                submitError = e.message ?: "Submit failed."
                            } finally {
                                isSubmitting = false
                            }
                        }
                    },
                    enabled = !isSubmitting,
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(16.dp),
                ) {
                    if (isSubmitting) {
                        CircularProgressIndicator(modifier = Modifier.padding(4.dp))
                    } else {
                        Text("Submit")
                    }
                }
            }
        }
    }
}

@Composable
private fun FieldEditor(
    field: FormFieldSchema,
    textValues: MutableMap<String, String>,
    boolValues: MutableMap<String, Boolean>,
    checklistValues: MutableMap<String, MutableSet<String>>,
    fileSelections: MutableMap<String, Pair<ByteArray, String>>,
    fieldErrors: MutableMap<String, List<String>>,
    onPickFile: () -> Unit,
) {
    val errors = fieldErrors[field.key].orEmpty()
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        when (field.fieldType) {
            "textarea" -> OutlinedTextField(
                value = textValues[field.key].orEmpty(),
                onValueChange = { textValues[field.key] = it },
                label = { Text(field.label) },
                modifier = Modifier.fillMaxWidth(),
                minLines = 3,
            )
            "email", "text", "number" -> OutlinedTextField(
                value = textValues[field.key].orEmpty(),
                onValueChange = { textValues[field.key] = it },
                label = { Text(if (field.placeholder.isNotBlank()) field.placeholder else field.label) },
                modifier = Modifier.fillMaxWidth(),
                singleLine = field.fieldType != "textarea",
            )
            "date" -> DateFieldEditor(field, textValues)
            "select" -> {
                Text(field.label, style = MaterialTheme.typography.labelLarge)
                field.choices.forEach { choice ->
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        modifier = Modifier
                            .fillMaxWidth()
                            .clickable { textValues[field.key] = choice },
                    ) {
                        RadioButton(
                            selected = textValues[field.key] == choice,
                            onClick = { textValues[field.key] = choice },
                        )
                        Text(choice)
                    }
                }
            }
            "radio" -> {
                Text(field.label, style = MaterialTheme.typography.labelLarge)
                field.choices.forEach { choice ->
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        modifier = Modifier
                            .fillMaxWidth()
                            .clickable { textValues[field.key] = choice },
                    ) {
                        RadioButton(
                            selected = textValues[field.key] == choice,
                            onClick = { textValues[field.key] = choice },
                        )
                        Text(choice)
                    }
                }
            }
            "checkbox" -> Row(verticalAlignment = Alignment.CenterVertically) {
                Checkbox(
                    checked = boolValues[field.key] == true,
                    onCheckedChange = { boolValues[field.key] = it },
                )
                Text(field.label)
            }
            "checklist" -> {
                Text(field.label, style = MaterialTheme.typography.labelLarge)
                field.choices.forEach { choice ->
                    val set = checklistValues.getOrPut(field.key) { mutableSetOf() }
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Checkbox(
                            checked = set.contains(choice),
                            onCheckedChange = { checked ->
                                if (checked) set.add(choice) else set.remove(choice)
                            },
                        )
                        Text(choice)
                    }
                }
            }
            "file" -> {
                Text(field.label, style = MaterialTheme.typography.labelLarge)
                fileSelections[field.key]?.let { (_, name) ->
                    Text(name, style = MaterialTheme.typography.bodySmall)
                    TextButton(onClick = { fileSelections.remove(field.key) }) { Text("Remove file") }
                }
                TextButton(onClick = onPickFile) { Text("Choose file") }
            }
            else -> OutlinedTextField(
                value = textValues[field.key].orEmpty(),
                onValueChange = { textValues[field.key] = it },
                label = { Text(field.label) },
                modifier = Modifier.fillMaxWidth(),
            )
        }
        if (field.helpText.isNotBlank()) {
            Text(field.helpText, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        errors.forEach { err ->
            Text(err, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.error)
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun DateFieldEditor(field: FormFieldSchema, textValues: MutableMap<String, String>) {
    var showPicker by remember { mutableStateOf(false) }
    val formatter = remember { DateTimeFormatter.ISO_LOCAL_DATE }
    Text(field.label, style = MaterialTheme.typography.labelLarge)
    OutlinedTextField(
        value = textValues[field.key].orEmpty(),
        onValueChange = {},
        readOnly = true,
        modifier = Modifier
            .fillMaxWidth()
            .clickable { showPicker = true },
        label = { Text("Date") },
    )
    if (showPicker) {
        val state = rememberDatePickerState()
        DatePickerDialog(
            onDismissRequest = { showPicker = false },
            confirmButton = {
                TextButton(onClick = {
                    state.selectedDateMillis?.let { ms ->
                        val date = Instant.ofEpochMilli(ms).atZone(ZoneId.systemDefault()).toLocalDate()
                        textValues[field.key] = date.format(formatter)
                    }
                    showPicker = false
                }) { Text("OK") }
            },
            dismissButton = {
                TextButton(onClick = { showPicker = false }) { Text("Cancel") }
            },
        ) {
            DatePicker(state = state)
        }
    }
}

private fun isVisible(
    field: FormFieldSchema,
    schema: FormSchemaResponse,
    textValues: Map<String, String>,
    boolValues: Map<String, Boolean>,
    checklistValues: Map<String, Set<String>>,
): Boolean {
    val controlId = field.visibilityControlFieldId ?: return true
    val controlKey = "f_$controlId"
    val control = schema.fields.find { it.id == controlId } ?: return false
    val allowed = field.visibilityValues.toSet()
    if (allowed.isEmpty()) return false
    if (control.fieldType == "checklist") {
        val selected = checklistValues[controlKey].orEmpty()
        if (selected.isEmpty()) return "" in allowed
        if (selected.any { it in allowed }) return true
        return selected.sorted().joinToString("\n") in allowed
    }
    if (control.fieldType == "checkbox") {
        val current = if (boolValues[controlKey] == true) "yes" else ""
        return current in allowed
    }
    return textValues[controlKey].orEmpty().trim() in allowed
}

private fun applyInitial(
    schema: FormSchemaResponse,
    textValues: MutableMap<String, String>,
    boolValues: MutableMap<String, Boolean>,
    checklistValues: MutableMap<String, MutableSet<String>>,
) {
    schema.initial.forEach { (key, element) ->
        when {
            element is JsonArray -> {
                checklistValues[key] = element.mapNotNull {
                    (it as? JsonPrimitive)?.contentOrNull
                }.toMutableSet()
            }
            element is JsonPrimitive && element.booleanOrNull != null -> {
                boolValues[key] = element.boolean
            }
            element is JsonPrimitive -> {
                element.contentOrNull?.let { textValues[key] = it }
            }
        }
    }
}
