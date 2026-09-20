package com.magicforms.mobile.data.models

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class SignaturesListResponse(
    val ok: Boolean,
    val limit: Int = 200,
    val count: Int = 0,
    val signatures: List<UserSignatureItem> = emptyList(),
)

@Serializable
data class UserSignatureItem(
    val id: Int,
    val label: String = "",
    @SerialName("image_url") val imageUrl: String = "",
    @SerialName("is_primary") val isPrimary: Boolean = false,
    @SerialName("sort_order") val sortOrder: Int = 0,
    @SerialName("created_at") val createdAt: String = "",
    @SerialName("created_at_label") val createdAtLabel: String = "",
)

@Serializable
data class SignatureMutationResponse(
    val ok: Boolean,
    val message: String? = null,
    val signature: UserSignatureItem? = null,
)
