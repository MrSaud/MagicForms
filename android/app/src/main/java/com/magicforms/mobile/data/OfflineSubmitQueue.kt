package com.magicforms.mobile.data

import android.content.Context
import com.magicforms.mobile.data.api.FormSubmitApi
import kotlinx.serialization.Serializable
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import java.util.UUID

@Serializable
data class PendingFormSubmit(
    val id: String,
    val kind: String,
    val formId: Int? = null,
    val relatedAccessToken: String? = null,
    val textFields: Map<String, String> = emptyMap(),
    val checkboxFields: Map<String, Boolean> = emptyMap(),
    val checklistFields: Map<String, List<String>> = emptyMap(),
)

class OfflineSubmitQueue(context: Context) {
    private val prefs = context.getSharedPreferences("offline_submit_queue", Context.MODE_PRIVATE)
    private val json = Json { ignoreUnknownKeys = true }
    private val api = FormSubmitApi()

    fun pendingCount(): Int = load().size

    fun enqueue(item: PendingFormSubmit) {
        val items = load().toMutableList()
        items.add(item)
        save(items)
    }

    fun flush(token: String): Int {
        val items = load().toMutableList()
        if (items.isEmpty()) return 0
        var synced = 0
        val remaining = mutableListOf<PendingFormSubmit>()
        for (item in items) {
            try {
                when {
                    item.kind == "related" && item.relatedAccessToken != null -> {
                        api.submitRelated(
                            token,
                            item.relatedAccessToken,
                            item.textFields,
                            item.checkboxFields,
                            item.checklistFields,
                            emptyMap(),
                        )
                    }
                    item.formId != null -> {
                        api.submit(
                            token,
                            item.formId,
                            item.textFields,
                            item.checkboxFields,
                            item.checklistFields,
                            emptyMap(),
                        )
                    }
                    else -> {
                        remaining.add(item)
                        continue
                    }
                }
                synced++
            } catch (_: Exception) {
                remaining.add(item)
            }
        }
        save(remaining)
        return synced
    }

    fun newItem(
        kind: String,
        formId: Int?,
        relatedAccessToken: String?,
        textFields: Map<String, String>,
        checkboxFields: Map<String, Boolean>,
        checklistFields: Map<String, List<String>>,
    ) = PendingFormSubmit(
        id = UUID.randomUUID().toString(),
        kind = kind,
        formId = formId,
        relatedAccessToken = relatedAccessToken,
        textFields = textFields,
        checkboxFields = checkboxFields,
        checklistFields = checklistFields,
    )

    private fun load(): List<PendingFormSubmit> {
        val raw = prefs.getString("items", null) ?: return emptyList()
        return runCatching { json.decodeFromString<List<PendingFormSubmit>>(raw) }.getOrElse { emptyList() }
    }

    private fun save(items: List<PendingFormSubmit>) {
        prefs.edit().putString("items", json.encodeToString(items)).apply()
    }
}
