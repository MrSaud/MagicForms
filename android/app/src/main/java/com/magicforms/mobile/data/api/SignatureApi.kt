package com.magicforms.mobile.data.api

import com.magicforms.mobile.data.models.SignatureMutationResponse
import com.magicforms.mobile.data.models.SignaturesListResponse
import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody

class SignatureApi {
    private val json = Json { ignoreUnknownKeys = true; isLenient = true }
    private val authApi = AuthApi()
    private val pngMedia = "image/png".toMediaType()

    fun fetchSignatures(token: String): SignaturesListResponse {
        val data = authApi.get(ApiConfig.url("/api/v1/signatures/"), token)
        return json.decodeFromString(data)
    }

    fun uploadSignature(
        token: String,
        pngBytes: ByteArray,
        label: String,
        replaceSignatureId: Int?,
    ): SignatureMutationResponse {
        val url = if (replaceSignatureId != null) {
            ApiConfig.url("/api/v1/signatures/$replaceSignatureId/image/")
        } else {
            ApiConfig.url("/api/v1/signatures/")
        }
        val body = MultipartBody.Builder()
            .setType(MultipartBody.FORM)
            .apply {
                if (label.isNotBlank()) {
                    addFormDataPart("label", label)
                }
                addFormDataPart(
                    "image",
                    "signature.png",
                    pngBytes.toRequestBody(pngMedia),
                )
            }
            .build()
        val data = authApi.postMultipart(url, body, token)
        return json.decodeFromString(data)
    }

    fun setPrimary(token: String, signatureId: Int) {
        authApi.post(ApiConfig.url("/api/v1/signatures/$signatureId/primary/"), "{}", token)
    }

    fun deleteSignature(token: String, signatureId: Int) {
        authApi.delete(ApiConfig.url("/api/v1/signatures/$signatureId/"), token)
    }
}
