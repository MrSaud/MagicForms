package com.magicforms.mobile.data

import android.content.Context
import kotlinx.serialization.Serializable
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json

@Serializable
data class FormDraft(
    val textValues: Map<String, String> = emptyMap(),
    val boolValues: Map<String, Boolean> = emptyMap(),
    val checklistValues: Map<String, List<String>> = emptyMap(),
)

object FormDraftStore {
    private val json = Json { ignoreUnknownKeys = true }
    private const val PREFS = "form_drafts"

    fun storageKey(formId: Int?): String? = formId?.let { "form_$it" }

    fun storageKey(relatedAccessToken: String?): String? =
        relatedAccessToken?.takeIf { it.isNotBlank() }?.let { "related_$it" }

    fun load(context: Context, key: String?): FormDraft? {
        if (key.isNullOrBlank()) return null
        val raw = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getString(key, null)
            ?: return null
        return runCatching { json.decodeFromString<FormDraft>(raw) }.getOrNull()
    }

    fun save(
        context: Context,
        key: String?,
        textValues: Map<String, String>,
        boolValues: Map<String, Boolean>,
        checklistValues: Map<String, Set<String>>,
    ) {
        if (key.isNullOrBlank()) return
        val draft = FormDraft(
            textValues = textValues,
            boolValues = boolValues,
            checklistValues = checklistValues.mapValues { (_, v) -> v.sorted() },
        )
        val encoded = json.encodeToString(draft)
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit()
            .putString(key, encoded)
            .apply()
    }

    fun clear(context: Context, key: String?) {
        if (key.isNullOrBlank()) return
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().remove(key).apply()
    }
}
