package com.magicforms.mobile.data.api

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json

class DeviceApi {
    private val json = Json { ignoreUnknownKeys = true }
    private val authApi = AuthApi()

    fun registerPushToken(bearerToken: String, pushToken: String, deviceId: String) {
        val body = RegisterBody(platform = "android", token = pushToken, deviceId = deviceId)
        authApi.post(ApiConfig.url("/api/v1/devices/register/"), json.encodeToString(body), bearerToken)
    }

    fun unregisterPushToken(bearerToken: String, pushToken: String?) {
        val body = UnregisterBody(token = pushToken)
        authApi.post(ApiConfig.url("/api/v1/devices/unregister/"), json.encodeToString(body), bearerToken)
    }

    @Serializable
    private data class RegisterBody(
        val platform: String,
        val token: String,
        @SerialName("device_id") val deviceId: String = "",
    )

    @Serializable
    private data class UnregisterBody(val token: String? = null)
}
