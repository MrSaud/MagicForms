package com.magicforms.mobile.data.api

import com.magicforms.mobile.data.models.HomeSummaryResponse
import com.magicforms.mobile.data.models.InboxDetailResponse
import com.magicforms.mobile.data.models.InboxListResponse
import com.magicforms.mobile.data.models.FormIntroResponse
import com.magicforms.mobile.data.models.PublishedFormsResponse
import com.magicforms.mobile.data.models.PendingRelatedResponse
import com.magicforms.mobile.data.models.ThreadPostRequest
import com.magicforms.mobile.data.models.WorkflowActionRequest
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json

class HomeApi {
    private val json = Json { ignoreUnknownKeys = true; isLenient = true }
    private val authApi = AuthApi()

    fun fetchSummary(token: String): HomeSummaryResponse {
        val data = authApi.get(ApiConfig.url("/api/v1/home/summary/"), token)
        return json.decodeFromString(data)
    }

    fun fetchPublishedForms(token: String): PublishedFormsResponse {
        val data = authApi.get(ApiConfig.url("/api/v1/forms/published/"), token)
        return json.decodeFromString(data)
    }

    fun fetchFormIntro(token: String, formId: Int): FormIntroResponse {
        val data = authApi.get(ApiConfig.url("/api/v1/forms/$formId/intro/"), token)
        return json.decodeFromString(data)
    }

    fun fetchInbox(token: String, limit: Int = 50, offset: Int = 0): InboxListResponse {
        val data = authApi.get(
            ApiConfig.url("/api/v1/inbox/?limit=$limit&offset=$offset"),
            token,
        )
        return json.decodeFromString(data)
    }

    fun fetchInboxDetail(token: String, submissionId: Int): InboxDetailResponse {
        val data = authApi.get(ApiConfig.url("/api/v1/inbox/$submissionId/"), token)
        return json.decodeFromString(data)
    }

    fun fetchPendingRelated(token: String): PendingRelatedResponse {
        val data = authApi.get(ApiConfig.url("/api/v1/related/pending/"), token)
        return json.decodeFromString(data)
    }

    fun postThreadMessage(token: String, submissionId: Int, body: String): InboxDetailResponse {
        val payload = json.encodeToString(ThreadPostRequest(body))
        val data = authApi.post(
            ApiConfig.url("/api/v1/inbox/$submissionId/thread/post/"),
            payload,
            token,
        )
        return json.decodeFromString(data)
    }

    fun performWorkflow(
        token: String,
        submissionId: Int,
        decision: String,
        comment: String?,
        workflowActionAnchor: Int?,
    ): InboxDetailResponse {
        val body = WorkflowActionRequest(
            decision = decision,
            comment = comment,
            workflowActionAnchor = workflowActionAnchor,
        )
        val data = authApi.post(
            ApiConfig.url("/api/v1/inbox/$submissionId/workflow/"),
            json.encodeToString(body),
            token,
        )
        return json.decodeFromString(data)
    }
}
