package com.magicforms.mobile.data.models

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class ApiUser(
    val id: Int,
    val username: String,
    val email: String = "",
    @SerialName("first_name") val firstName: String = "",
    @SerialName("last_name") val lastName: String = "",
    @SerialName("full_name") val fullName: String = "",
    @SerialName("is_staff") val isStaff: Boolean = false,
    @SerialName("is_superuser") val isSuperuser: Boolean = false,
) {
    val displayName: String
        get() = when {
            fullName.isNotBlank() -> fullName
            firstName.isNotBlank() || lastName.isNotBlank() ->
                listOf(firstName, lastName).filter { it.isNotBlank() }.joinToString(" ")
            else -> username
        }
}

@Serializable
data class ApiEntity(
    val id: Int? = null,
    val slug: String,
    val name: String,
    @SerialName("logo_url") val logoUrl: String? = null,
)

@Serializable
data class LoginRequest(
    val username: String,
    val password: String,
    @SerialName("entity_slug") val entitySlug: String? = null,
)

@Serializable
data class LoginResponse(
    val ok: Boolean,
    val token: String? = null,
    @SerialName("expires_at") val expiresAt: String? = null,
    @SerialName("token_type") val tokenType: String? = null,
    @SerialName("login_via") val loginVia: String? = null,
    val user: ApiUser? = null,
    val entities: List<ApiEntity>? = null,
)

@Serializable
data class MeResponse(
    val ok: Boolean,
    val user: ApiUser? = null,
    val entities: List<ApiEntity>? = null,
)

@Serializable
data class DirectoryEntitiesResponse(
    val ok: Boolean,
    val entities: List<ApiEntity>? = null,
)

@Serializable
data class ApiErrorBody(
    val ok: Boolean? = null,
    val error: String? = null,
    val message: String? = null,
    val entities: List<ApiEntity>? = null,
)

class ApiException(
    val code: String,
    override val message: String,
    val entities: List<ApiEntity>? = null,
) : Exception(message)
