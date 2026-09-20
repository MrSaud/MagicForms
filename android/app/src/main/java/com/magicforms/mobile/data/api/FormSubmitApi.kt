package com.magicforms.mobile.data.api

import com.magicforms.mobile.data.models.ApiException
import com.magicforms.mobile.data.models.FormSchemaResponse
import com.magicforms.mobile.data.models.FormSubmitResponse
import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.toRequestBody

class FormSubmitApi {
    private val json = Json { ignoreUnknownKeys = true; isLenient = true }
    private val authApi = AuthApi()

    fun fetchSchema(token: String, formId: Int): FormSchemaResponse {
        val data = authApi.get(ApiConfig.url("/api/v1/forms/$formId/schema/"), token)
        val response = json.decodeFromString<FormSchemaResponse>(data)
        if (response.ok) return response
        throw ApiException(message = "Could not load form.")
    }

    fun submit(
        token: String,
        formId: Int,
        textFields: Map<String, String>,
        checkboxFields: Map<String, Boolean>,
        checklistFields: Map<String, List<String>>,
        files: Map<String, Pair<ByteArray, String>>,
    ): FormSubmitResponse {
        val builder = MultipartBody.Builder().setType(MultipartBody.FORM)
        textFields.forEach { (key, value) ->
            builder.addFormDataPart(key, value)
        }
        checkboxFields.filter { it.value }.forEach { (key, _) ->
            builder.addFormDataPart(key, "on")
        }
        checklistFields.forEach { (key, values) ->
            values.forEach { value -> builder.addFormDataPart(key, value) }
        }
        val octet = "application/octet-stream".toMediaType()
        files.forEach { (key, pair) ->
            val (bytes, fileName) = pair
            builder.addFormDataPart(
                key,
                fileName,
                bytes.toRequestBody(octet),
            )
        }
        val data = authApi.postMultipart(
            ApiConfig.url("/api/v1/forms/$formId/submit/"),
            builder.build(),
            token,
        )
        val response = json.decodeFromString<FormSubmitResponse>(data)
        if (response.ok) return response
        if (!response.fieldErrors.isNullOrEmpty()) {
            throw FormSubmitValidationException(
                message = response.message ?: "Please fix the highlighted fields.",
                fieldErrors = response.fieldErrors,
            )
        }
        throw ApiException(message = response.message ?: "Submit failed.")
    }

    fun fetchRelatedSchema(token: String, accessToken: String): FormSchemaResponse {
        val data = authApi.get(ApiConfig.url("/api/v1/related/$accessToken/schema/"), token)
        val response = json.decodeFromString<FormSchemaResponse>(data)
        if (response.ok) return response
        throw ApiException(message = "Could not load form.")
    }

    fun submitRelated(
        token: String,
        accessToken: String,
        textFields: Map<String, String>,
        checkboxFields: Map<String, Boolean>,
        checklistFields: Map<String, List<String>>,
        files: Map<String, Pair<ByteArray, String>>,
    ): FormSubmitResponse {
        val builder = MultipartBody.Builder().setType(MultipartBody.FORM)
        textFields.forEach { (key, value) -> builder.addFormDataPart(key, value) }
        checkboxFields.filter { it.value }.forEach { (key, _) -> builder.addFormDataPart(key, "on") }
        checklistFields.forEach { (key, values) ->
            values.forEach { value -> builder.addFormDataPart(key, value) }
        }
        val octet = "application/octet-stream".toMediaType()
        files.forEach { (key, pair) ->
            val (bytes, fileName) = pair
            builder.addFormDataPart(key, fileName, bytes.toRequestBody(octet))
        }
        val data = authApi.postMultipart(
            ApiConfig.url("/api/v1/related/$accessToken/submit/"),
            builder.build(),
            token,
        )
        val response = json.decodeFromString<FormSubmitResponse>(data)
        if (response.ok) return response
        if (!response.fieldErrors.isNullOrEmpty()) {
            throw FormSubmitValidationException(
                message = response.message ?: "Please fix the highlighted fields.",
                fieldErrors = response.fieldErrors,
            )
        }
        throw ApiException(message = response.message ?: "Submit failed.")
    }
}

class FormSubmitValidationException(
    override val message: String,
    val fieldErrors: Map<String, List<String>>,
) : Exception(message)
