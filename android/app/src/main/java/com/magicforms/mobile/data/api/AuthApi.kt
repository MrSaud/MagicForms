package com.magicforms.mobile.data.api

import com.magicforms.mobile.data.models.ApiEntity
import com.magicforms.mobile.data.models.ApiErrorBody
import com.magicforms.mobile.data.models.ApiException
import com.magicforms.mobile.data.models.DirectoryEntitiesResponse
import com.magicforms.mobile.data.models.LoginRequest
import com.magicforms.mobile.data.models.LoginResponse
import com.magicforms.mobile.data.LanguagePreferences
import com.magicforms.mobile.data.SessionExpiredException
import com.magicforms.mobile.data.models.MeResponse
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.MultipartBody
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody

class AuthApi {
    private val json = Json {
        ignoreUnknownKeys = true
        isLenient = true
    }

    private val client = OkHttpClient.Builder().build()
    private val jsonMedia = "application/json; charset=utf-8".toMediaType()

    suspend fun fetchDirectoryEntities(): List<ApiEntity> {
        val data = get(ApiConfig.url("/api/v1/auth/directory-entities/"), token = null)
        val response = json.decodeFromString<DirectoryEntitiesResponse>(data)
        return response.entities.orEmpty()
    }

    suspend fun login(username: String, password: String, entitySlug: String?): LoginResponse {
        val body = LoginRequest(
            username = username,
            password = password,
            entitySlug = entitySlug?.takeIf { it.isNotBlank() },
        )
        val data = postRequest(ApiConfig.url("/api/v1/auth/login/"), json.encodeToString(body), token = null)
        val response = json.decodeFromString<LoginResponse>(data)
        if (response.ok && !response.token.isNullOrBlank()) {
            return response
        }
        throw parseError(data)
    }

    suspend fun me(token: String): MeResponse {
        val data = get(ApiConfig.url("/api/v1/auth/me/"), token = token)
        val response = json.decodeFromString<MeResponse>(data)
        if (response.ok) return response
        throw parseError(data)
    }

    suspend fun logout(token: String) {
        postRequest(ApiConfig.url("/api/v1/auth/logout/"), "{}", token = token)
    }

    fun get(url: String, token: String?): String = getRequest(url, token)

    fun post(url: String, body: String, token: String?): String = postRequest(url, body, token)

    fun postMultipart(url: String, body: MultipartBody, token: String?): String {
        val request = Request.Builder()
            .url(url)
            .post(body)
            .header("Accept", "application/json")
            .apply { token?.let { header("Authorization", "Bearer $it") } }
            .build()
        return execute(request)
    }

    fun delete(url: String, token: String?): String {
        val request = applyLanguage(
            Request.Builder()
                .url(url)
                .delete()
                .header("Accept", "application/json")
                .apply { token?.let { header("Authorization", "Bearer $it") } },
        ).build()
        return execute(request)
    }

    private fun getRequest(url: String, token: String?): String {
        val request = applyLanguage(
            Request.Builder()
                .url(url)
                .get()
                .header("Accept", "application/json")
                .apply { token?.let { header("Authorization", "Bearer $it") } },
        ).build()
        return execute(request)
    }

    private fun postRequest(url: String, body: String, token: String?): String {
        val request = applyLanguage(
            Request.Builder()
                .url(url)
                .post(body.toRequestBody(jsonMedia))
                .header("Content-Type", "application/json")
                .header("Accept", "application/json")
                .apply { token?.let { header("Authorization", "Bearer $it") } },
        ).build()
        return execute(request)
    }

    private fun applyLanguage(request: Request.Builder): Request.Builder {
        return request.header("Accept-Language", LanguagePreferences.acceptLanguageHeader())
    }

    private fun execute(request: Request): String {
        client.newCall(request).execute().use { response ->
            val body = response.body?.string().orEmpty()
            if (response.isSuccessful) return body
            if (response.code == 401) {
                throw SessionExpiredException()
            }
            throw parseError(body, response.code)
        }
    }

    private fun parseError(data: String, status: Int? = null): ApiException {
        return try {
            val body = json.decodeFromString<ApiErrorBody>(data)
            ApiException(
                code = body.error ?: "error",
                message = body.message ?: "Request failed.",
                entities = body.entities,
            )
        } catch (_: Exception) {
            ApiException(
                code = status?.let { "http_$it" } ?: "error",
                message = status?.let { "HTTP $it" } ?: "Request failed.",
            )
        }
    }
}
