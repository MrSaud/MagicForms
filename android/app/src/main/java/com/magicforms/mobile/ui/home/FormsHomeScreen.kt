package com.magicforms.mobile.ui.home

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.material3.TextButton
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.magicforms.mobile.R
import com.magicforms.mobile.data.models.PublishedFormItem
import com.magicforms.mobile.ui.AuthUiState

@Composable
fun FormsHomeScreen(
    state: AuthUiState,
    onOpenForm: (PublishedFormItem) -> Unit,
    onReadIntro: (PublishedFormItem) -> Unit,
    modifier: Modifier = Modifier,
) {
    var searchQuery by remember { mutableStateOf("") }
    var selectedEntitySlug by remember { mutableStateOf<String?>(null) }
    var selectedCategorySlug by remember { mutableStateOf<String?>(null) }

    val entityOptions = remember(state.publishedForms) {
        FormsListFilter.entityOptions(state.publishedForms)
    }
    val categoryOptions = remember(state.publishedForms) {
        FormsListFilter.categoryOptions(state.publishedForms)
    }
    val filteredForms = remember(
        state.publishedForms,
        searchQuery,
        selectedEntitySlug,
        selectedCategorySlug,
    ) {
        FormsListFilter.apply(
            state.publishedForms,
            searchQuery,
            selectedEntitySlug,
            selectedCategorySlug,
        )
    }
    val hasActiveFilters = searchQuery.isNotBlank() ||
        selectedEntitySlug != null ||
        selectedCategorySlug != null

    val filterChips = buildList {
        if (entityOptions.size > 1) {
            add(
                FilterChipSpec(
                    id = "entity-all",
                    label = "All orgs",
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
        if (categoryOptions.isNotEmpty()) {
            add(
                FilterChipSpec(
                    id = "cat-all",
                    label = "All categories",
                    selected = selectedCategorySlug == null,
                    onClick = { selectedCategorySlug = null },
                ),
            )
            categoryOptions.forEach { (slug, name) ->
                add(
                    FilterChipSpec(
                        id = "cat-$slug",
                        label = name,
                        selected = selectedCategorySlug == slug,
                        onClick = { selectedCategorySlug = slug },
                    ),
                )
            }
        }
    }

    Box(modifier = modifier.fillMaxSize()) {
        if (state.publishedForms.isEmpty() && !state.isLoadingHome) {
            Column(
                modifier = Modifier
                    .align(Alignment.Center)
                    .padding(24.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Text(stringResource(R.string.no_open_forms), style = MaterialTheme.typography.titleMedium)
                Text(
                    stringResource(R.string.no_open_forms_desc),
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        } else {
            LazyColumn(
                modifier = Modifier.fillMaxSize(),
                contentPadding = androidx.compose.foundation.layout.PaddingValues(16.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                item {
                    ListSearchFilterBar(
                        searchQuery = searchQuery,
                        onSearchChange = { searchQuery = it },
                        searchPlaceholder = stringResource(R.string.search_forms),
                        chips = filterChips,
                        hasActiveFilters = hasActiveFilters,
                        onClearFilters = {
                            searchQuery = ""
                            selectedEntitySlug = null
                            selectedCategorySlug = null
                        },
                    )
                }
                if (filteredForms.isEmpty()) {
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
                    items(filteredForms, key = { it.id }) { form ->
                        FormRow(
                            form = form,
                            onOpen = { onOpenForm(form) },
                            onReadIntro = {
                                if (form.introPageEnabled && form.introPageUrl.isNotBlank()) {
                                    onReadIntro(form)
                                }
                            },
                        )
                    }
                }
            }
        }

        if (state.isLoadingHome && state.publishedForms.isEmpty()) {
            CircularProgressIndicator(modifier = Modifier.align(Alignment.Center))
        }
    }
}

@Composable
private fun FormRow(
    form: PublishedFormItem,
    onOpen: () -> Unit,
    onReadIntro: () -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 8.dp),
        verticalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .clickable(onClick = onOpen),
            verticalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            Text(form.title, style = MaterialTheme.typography.titleMedium)
            Text(form.entity.name, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            form.category?.name?.takeIf { it.isNotBlank() }?.let {
                Text(it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            if (form.submissionDeadlineLabel.isNotBlank()) {
                Text(stringResource(R.string.due, form.submissionDeadlineLabel), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            if (form.description.isNotBlank()) {
                Text(form.description, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 2)
            }
        }
        if (form.introPageEnabled && form.introPageUrl.isNotBlank()) {
            TextButton(onClick = onReadIntro) {
                Text(stringResource(R.string.read_more_about_form))
            }
        }
    }
}
