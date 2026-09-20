package com.magicforms.mobile.ui.search

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Message
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
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
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.magicforms.mobile.R
import com.magicforms.mobile.data.api.SearchApi
import com.magicforms.mobile.data.models.ApiException
import com.magicforms.mobile.data.models.InboxItem
import com.magicforms.mobile.data.models.SearchFormOption
import com.magicforms.mobile.ui.AuthViewModel
import com.magicforms.mobile.ui.home.FilterChipSpec
import com.magicforms.mobile.ui.home.ListSearchFilterBar
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

@Composable
fun SubmissionSearchScreen(
    authViewModel: AuthViewModel,
    onOpenDetail: (Int) -> Unit,
    modifier: Modifier = Modifier,
) {
    val scope = rememberCoroutineScope()
    val searchApi = remember { SearchApi() }

    var searchQuery by remember { mutableStateOf("") }
    var relation by remember { mutableStateOf("any") }
    var workflowState by remember { mutableStateOf("") }
    var selectedFormId by remember { mutableStateOf<Int?>(null) }
    var items by remember { mutableStateOf<List<InboxItem>>(emptyList()) }
    var formOptions by remember { mutableStateOf<List<SearchFormOption>>(emptyList()) }
    var total by remember { mutableIntStateOf(0) }
    var isLoading by remember { mutableStateOf(false) }
    var errorMessage by remember { mutableStateOf<String?>(null) }

    fun runSearch() {
        val token = authViewModel.state.value.token ?: return
        scope.launch {
            isLoading = true
            errorMessage = null
            try {
                val response = withContext(Dispatchers.IO) {
                    searchApi.fetchSubmissions(
                        token = token,
                        query = searchQuery,
                        relation = relation,
                        workflowState = workflowState.takeIf { it.isNotBlank() },
                        formId = selectedFormId,
                    )
                }
                items = response.items
                formOptions = response.formOptions
                total = response.total
            } catch (e: ApiException) {
                errorMessage = e.message
                items = emptyList()
            } catch (e: Exception) {
                errorMessage = e.message ?: "Search failed."
                items = emptyList()
            } finally {
                isLoading = false
            }
        }
    }

    LaunchedEffect(relation, workflowState, selectedFormId) { runSearch() }
    LaunchedEffect(searchQuery) {
        delay(400)
        runSearch()
    }

    val filterChips = buildList {
        add(FilterChipSpec("rel-any", stringResource(R.string.all_roles), relation == "any") { relation = "any"; runSearch() })
        add(FilterChipSpec("rel-applicant", stringResource(R.string.role_applicant), relation == "applicant") { relation = "applicant"; runSearch() })
        add(FilterChipSpec("rel-workflow", stringResource(R.string.role_workflow), relation == "workflow") { relation = "workflow"; runSearch() })
        add(FilterChipSpec("wf-all", stringResource(R.string.all_status), workflowState.isEmpty()) { workflowState = ""; runSearch() })
        add(FilterChipSpec("wf-progress", stringResource(R.string.status_in_progress), workflowState == "in_progress") { workflowState = "in_progress"; runSearch() })
        add(FilterChipSpec("wf-completed", stringResource(R.string.status_completed), workflowState == "completed") { workflowState = "completed"; runSearch() })
        add(FilterChipSpec("wf-rejected", stringResource(R.string.status_rejected), workflowState == "rejected") { workflowState = "rejected"; runSearch() })
        if (formOptions.size > 1) {
            add(FilterChipSpec("form-all", stringResource(R.string.all_forms), selectedFormId == null) { selectedFormId = null; runSearch() })
            formOptions.forEach { form ->
                add(
                    FilterChipSpec(
                        id = "form-${form.id}",
                        label = form.title,
                        selected = selectedFormId == form.id,
                        onClick = { selectedFormId = form.id; runSearch() },
                    ),
                )
            }
        }
    }

    Box(modifier = modifier.fillMaxSize()) {
        LazyColumn(
            modifier = Modifier.fillMaxSize(),
            contentPadding = androidx.compose.foundation.layout.PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            item {
                ListSearchFilterBar(
                    searchQuery = searchQuery,
                    onSearchChange = { searchQuery = it },
                    searchPlaceholder = stringResource(R.string.search_requests),
                    chips = filterChips,
                    hasActiveFilters = searchQuery.isNotBlank() ||
                        relation != "any" ||
                        workflowState.isNotBlank() ||
                        selectedFormId != null,
                    onClearFilters = {
                        searchQuery = ""
                        relation = "any"
                        workflowState = ""
                        selectedFormId = null
                        runSearch()
                    },
                )
                if (total > 0) {
                    Text(
                        stringResource(R.string.results_count, total),
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.padding(bottom = 8.dp),
                    )
                }
            }
            if (items.isEmpty() && !isLoading) {
                item {
                    Column(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(vertical = 32.dp),
                        horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        Text(
                            stringResource(if (errorMessage != null) R.string.no_matches else R.string.search_empty),
                            style = MaterialTheme.typography.titleMedium,
                        )
                        Text(
                            errorMessage ?: stringResource(R.string.search_empty_desc),
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
            } else {
                items(items, key = { it.id }) { item ->
                    SearchResultRow(item = item, onOpen = { onOpenDetail(item.id) })
                }
            }
        }
        if (isLoading && items.isEmpty()) {
            CircularProgressIndicator(modifier = Modifier.align(Alignment.Center))
        }
    }
}

@Composable
private fun SearchResultRow(item: InboxItem, onOpen: () -> Unit) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onOpen)
            .padding(vertical = 8.dp),
        verticalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Text(item.form.title, style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
            Text(item.workflowStateLabel, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        if (item.roleLabels.isNotEmpty()) {
            Text(item.roleLabels.joinToString(" · "), style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.tertiary)
        }
        Text(item.form.entityName, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        if (item.submitter.isNotBlank()) {
            Text(item.submitter, style = MaterialTheme.typography.bodySmall)
        }
        if (item.currentStepLabel.isNotBlank()) {
            Text(item.currentStepLabel, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        if (item.referenceToken.isNotBlank()) {
            Text(item.referenceToken, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        if (item.canAct) {
            Text(
                stringResource(R.string.action_needed),
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.tertiary,
            )
        }
        if (item.hasUnreadThread) {
            Icon(
                Icons.Default.Message,
                contentDescription = stringResource(R.string.unread_messages),
                tint = MaterialTheme.colorScheme.primary,
                modifier = Modifier.padding(top = 4.dp),
            )
        }
    }
}
