package com.magicforms.mobile.ui.home

import androidx.compose.foundation.background
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
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Message
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.SwipeToDismissBox
import androidx.compose.material3.SwipeToDismissBoxValue
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberSwipeToDismissBoxState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.magicforms.mobile.R
import com.magicforms.mobile.data.models.InboxItem
import com.magicforms.mobile.ui.AuthUiState
import com.magicforms.mobile.ui.AuthViewModel

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun InboxScreen(
    state: AuthUiState,
    authViewModel: AuthViewModel,
    onOpenDetail: (Int) -> Unit,
    modifier: Modifier = Modifier,
) {
    val rejectComments = remember { mutableStateMapOf<Int, String>() }
    var searchQuery by remember { mutableStateOf("") }
    var selectedEntitySlug by remember { mutableStateOf<String?>(null) }
    var selectedFormId by remember { mutableStateOf<Int?>(null) }
    var actionNeededOnly by remember { mutableStateOf(false) }
    var unreadOnly by remember { mutableStateOf(false) }
    var swipeApproveItem by remember { mutableStateOf<InboxItem?>(null) }
    var swipeRejectItem by remember { mutableStateOf<InboxItem?>(null) }
    var swipeRejectComment by remember { mutableStateOf("") }

    val entityOptions = remember(state.inboxItems) { InboxListFilter.entityOptions(state.inboxItems) }
    val formOptions = remember(state.inboxItems) { InboxListFilter.formOptions(state.inboxItems) }
    val filteredItems = remember(
        state.inboxItems,
        searchQuery,
        selectedEntitySlug,
        selectedFormId,
        actionNeededOnly,
        unreadOnly,
    ) {
        InboxListFilter.apply(
            state.inboxItems,
            searchQuery,
            selectedEntitySlug,
            selectedFormId,
            actionNeededOnly,
            unreadOnly,
        )
    }
    val hasActiveFilters = searchQuery.isNotBlank() ||
        selectedEntitySlug != null ||
        selectedFormId != null ||
        actionNeededOnly ||
        unreadOnly

    val filterChips = buildList {
        if (entityOptions.size > 1) {
            add(
                FilterChipSpec(
                    id = "entity-all",
                    label = stringResource(R.string.all_orgs),
                    selected = selectedEntitySlug == null,
                    onClick = { selectedEntitySlug = null },
                ),
            )
            entityOptions.forEach { (slug, name) ->
                add(
                    FilterChipSpec(
                        id = "entity-$slug",
                        label = name,
                        selected = selectedEntitySlug == slug,
                        onClick = { selectedEntitySlug = slug },
                    ),
                )
            }
        }
        if (formOptions.size > 1) {
            add(
                FilterChipSpec(
                    id = "form-all",
                    label = stringResource(R.string.all_forms),
                    selected = selectedFormId == null,
                    onClick = { selectedFormId = null },
                ),
            )
            formOptions.forEach { (id, title) ->
                add(
                    FilterChipSpec(
                        id = "form-$id",
                        label = title,
                        selected = selectedFormId == id,
                        onClick = { selectedFormId = id },
                    ),
                )
            }
        }
        add(
            FilterChipSpec(
                id = "action-needed",
                label = stringResource(R.string.action_needed),
                selected = actionNeededOnly,
                onClick = { actionNeededOnly = !actionNeededOnly },
            ),
        )
        add(
            FilterChipSpec(
                id = "unread",
                label = stringResource(R.string.unread),
                selected = unreadOnly,
                onClick = { unreadOnly = !unreadOnly },
            ),
        )
    }

    swipeApproveItem?.let { item ->
        AlertDialog(
            onDismissRequest = { swipeApproveItem = null },
            title = { Text(stringResource(R.string.confirm_approve_title)) },
            text = { Text(stringResource(R.string.confirm_approve_message)) },
            confirmButton = {
                TextButton(onClick = {
                    swipeApproveItem = null
                    authViewModel.performInboxWorkflow(
                        submissionId = item.id,
                        decision = "approve",
                        comment = null,
                        workflowActionAnchor = item.currentStepId,
                    )
                }) { Text(stringResource(R.string.approve)) }
            },
            dismissButton = {
                TextButton(onClick = { swipeApproveItem = null }) {
                    Text(stringResource(R.string.cancel))
                }
            },
        )
    }

    swipeRejectItem?.let { item ->
        AlertDialog(
            onDismissRequest = {
                swipeRejectItem = null
                swipeRejectComment = ""
            },
            title = { Text(stringResource(R.string.confirm_reject_title)) },
            text = {
                OutlinedTextField(
                    value = swipeRejectComment,
                    onValueChange = { swipeRejectComment = it },
                    label = { Text(stringResource(R.string.rejection_reason)) },
                    minLines = 2,
                )
            },
            confirmButton = {
                TextButton(
                    onClick = {
                        val comment = swipeRejectComment.trim()
                        rejectComments[item.id] = comment
                        swipeRejectItem = null
                        swipeRejectComment = ""
                        authViewModel.performInboxWorkflow(
                            submissionId = item.id,
                            decision = "reject",
                            comment = comment,
                            workflowActionAnchor = item.currentStepId,
                        )
                    },
                    enabled = swipeRejectComment.isNotBlank(),
                ) { Text(stringResource(R.string.reject)) }
            },
            dismissButton = {
                TextButton(onClick = {
                    swipeRejectItem = null
                    swipeRejectComment = ""
                }) { Text(stringResource(R.string.cancel)) }
            },
        )
    }

    Box(modifier = modifier.fillMaxSize()) {
        if (state.inboxItems.isEmpty() && !state.isLoadingHome) {
            Column(
                modifier = Modifier
                    .align(Alignment.Center)
                    .padding(24.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Text(stringResource(R.string.inbox_empty), style = MaterialTheme.typography.titleMedium)
                Text(
                    stringResource(R.string.inbox_empty_desc),
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        } else {
            LazyColumn(
                modifier = Modifier.fillMaxSize(),
                contentPadding = androidx.compose.foundation.layout.PaddingValues(16.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                item {
                    ListSearchFilterBar(
                        searchQuery = searchQuery,
                        onSearchChange = { searchQuery = it },
                        searchPlaceholder = stringResource(R.string.search_inbox),
                        chips = filterChips,
                        hasActiveFilters = hasActiveFilters,
                        onClearFilters = {
                            searchQuery = ""
                            selectedEntitySlug = null
                            selectedFormId = null
                            actionNeededOnly = false
                            unreadOnly = false
                        },
                    )
                }
                if (filteredItems.isEmpty()) {
                    item {
                        Column(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(vertical = 32.dp),
                            horizontalAlignment = Alignment.CenterHorizontally,
                            verticalArrangement = Arrangement.spacedBy(8.dp),
                        ) {
                            Text(stringResource(R.string.no_matches), style = MaterialTheme.typography.titleMedium)
                            Text(
                                stringResource(R.string.no_matches_desc),
                                style = MaterialTheme.typography.bodyMedium,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                    }
                } else {
                    items(filteredItems, key = { it.id }) { item ->
                        InboxSwipeableRow(
                            item = item,
                            isActing = state.inboxActingIds.contains(item.id),
                            errorMessage = state.inboxItemErrors[item.id],
                            onOpen = { onOpenDetail(item.id) },
                            onSwipeApprove = { swipeApproveItem = item },
                            onSwipeReject = {
                                swipeRejectItem = item
                                swipeRejectComment = rejectComments[item.id].orEmpty()
                            },
                        )
                    }
                }
            }
        }

        if (state.isLoadingHome && state.inboxItems.isEmpty()) {
            CircularProgressIndicator(modifier = Modifier.align(Alignment.Center))
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun InboxSwipeableRow(
    item: InboxItem,
    isActing: Boolean,
    errorMessage: String?,
    onOpen: () -> Unit,
    onSwipeApprove: () -> Unit,
    onSwipeReject: () -> Unit,
) {
    val dismissState = rememberSwipeToDismissBoxState(
        confirmValueChange = { value ->
            when (value) {
                SwipeToDismissBoxValue.StartToEnd -> {
                    if (item.canAct) onSwipeApprove()
                    false
                }
                SwipeToDismissBoxValue.EndToStart -> {
                    if (item.canAct) onSwipeReject()
                    false
                }
                else -> false
            }
        },
    )

    SwipeToDismissBox(
        state = dismissState,
        enableDismissFromStartToEnd = item.canAct,
        enableDismissFromEndToStart = item.canAct,
        backgroundContent = {
            val direction = dismissState.dismissDirection
            val color = when (direction) {
                SwipeToDismissBoxValue.StartToEnd -> MaterialTheme.colorScheme.primaryContainer
                SwipeToDismissBoxValue.EndToStart -> MaterialTheme.colorScheme.errorContainer
                else -> MaterialTheme.colorScheme.surfaceVariant
            }
            val alignment = when (direction) {
                SwipeToDismissBoxValue.StartToEnd -> Alignment.CenterStart
                SwipeToDismissBoxValue.EndToStart -> Alignment.CenterEnd
                else -> Alignment.Center
            }
            val icon = when (direction) {
                SwipeToDismissBoxValue.StartToEnd -> Icons.Default.Check
                SwipeToDismissBoxValue.EndToStart -> Icons.Default.Close
                else -> null
            }
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .background(color)
                    .padding(horizontal = 20.dp),
                contentAlignment = alignment,
            ) {
                icon?.let {
                    Icon(it, contentDescription = null)
                }
            }
        },
    ) {
        InboxRow(
            item = item,
            isActing = isActing,
            errorMessage = errorMessage,
            onOpen = onOpen,
        )
    }
}

@Composable
private fun InboxRow(
    item: InboxItem,
    isActing: Boolean,
    errorMessage: String?,
    onOpen: () -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .background(MaterialTheme.colorScheme.surface),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .clickable(onClick = onOpen)
                .padding(vertical = 4.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            Row(horizontalArrangement = Arrangement.SpaceBetween, modifier = Modifier.fillMaxWidth()) {
                Text(item.form.title, style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
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
                    )
                }
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
        }

        errorMessage?.let { msg ->
            Text(msg, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.error)
        }

        if (isActing) {
            CircularProgressIndicator(modifier = Modifier.align(Alignment.CenterHorizontally))
        }
    }
}
