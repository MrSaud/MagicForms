package com.magicforms.mobile.ui.home

import com.magicforms.mobile.data.models.InboxItem
import com.magicforms.mobile.data.models.PublishedFormItem

object FormsListFilter {
    fun apply(
        forms: List<PublishedFormItem>,
        searchText: String,
        entitySlug: String?,
        categorySlug: String?,
    ): List<PublishedFormItem> {
        val query = searchText.trim().lowercase()
        return forms.filter { form ->
            if (entitySlug != null && form.entity.slug != entitySlug) return@filter false
            if (categorySlug != null) {
                val cat = form.category ?: return@filter false
                if (cat.slug != categorySlug) return@filter false
            }
            if (query.isEmpty()) return@filter true
            form.title.lowercase().contains(query) ||
                form.slug.lowercase().contains(query) ||
                form.entity.name.lowercase().contains(query) ||
                form.description.lowercase().contains(query) ||
                (form.category?.name?.lowercase()?.contains(query) == true)
        }
    }

    fun entityOptions(forms: List<PublishedFormItem>): List<Pair<String, String>> {
        return forms
            .map { it.entity.slug to it.entity.name }
            .distinctBy { it.first }
            .sortedBy { it.second.lowercase() }
    }

    fun categoryOptions(forms: List<PublishedFormItem>): List<Pair<String, String>> {
        return forms.mapNotNull { it.category?.let { c -> c.slug to c.name } }
            .distinctBy { it.first }
            .sortedBy { it.second.lowercase() }
    }
}

object InboxListFilter {
    fun apply(
        items: List<InboxItem>,
        searchText: String,
        entitySlug: String?,
        formId: Int?,
        actionNeededOnly: Boolean,
        unreadOnly: Boolean,
    ): List<InboxItem> {
        val query = searchText.trim().lowercase()
        return items.filter { item ->
            if (entitySlug != null && item.form.entitySlug != entitySlug) return@filter false
            if (formId != null && item.form.id != formId) return@filter false
            if (actionNeededOnly && !item.canAct) return@filter false
            if (unreadOnly && !item.hasUnreadThread) return@filter false
            if (query.isEmpty()) return@filter true
            item.form.title.lowercase().contains(query) ||
                item.form.entityName.lowercase().contains(query) ||
                item.submitter.lowercase().contains(query) ||
                item.referenceToken.lowercase().contains(query) ||
                item.currentStepLabel.lowercase().contains(query)
        }
    }

    fun entityOptions(items: List<InboxItem>): List<Pair<String, String>> {
        return items
            .map { it.form.entitySlug to it.form.entityName }
            .distinctBy { it.first }
            .sortedBy { it.second.lowercase() }
    }

    fun formOptions(items: List<InboxItem>): List<Pair<Int, String>> {
        return items
            .map { it.form.id to it.form.title }
            .distinctBy { it.first }
            .sortedBy { it.second.lowercase() }
    }
}
