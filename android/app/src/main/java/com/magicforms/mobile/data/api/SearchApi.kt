package com.magicforms.mobile.data.api

import com.magicforms.mobile.data.models.SubmissionSearchResponse
import kotlinx.serialization.json.Json

class SearchApi {
    private val json = Json { ignoreUnknownKeys = true; isLenient = true }
    private val authApi = AuthApi()

    fun fetchSubmissions(
        token: String,
        query: String = "",
        relation: String = "any",
        workflowState: String? = null,
        formId: Int? = null,
        limit: Int = 50,
        offset: Int = 0,
    ): SubmissionSearchResponse {
        val params = buildList {
            add("limit=$limit")
            add("offset=$offset")
            add("relation=$relation")
            if (query.isNotBlank()) add("q=${java.net.URLEncoder.encode(query.trim(), Charsets.UTF_8.name())}")
            if (!workflowState.isNullOrBlank()) add("workflow_state=$workflowState")
            if (formId != null) add("form=$formId")
        }
        val url = ApiConfig.url("/api/v1/submissions/search/?${params.joinToString("&")}")
        val data = authApi.get(url, token)
        return json.decodeFromString(data)
    }
}
