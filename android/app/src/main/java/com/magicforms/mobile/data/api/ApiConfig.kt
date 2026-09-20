package com.magicforms.mobile.data.api

import com.magicforms.mobile.BuildConfig

/** Main-site API base URL (no entity slug in paths). Set via [BuildConfig.API_BASE_URL]. */
object ApiConfig {
    val baseUrl: String
        get() = BuildConfig.API_BASE_URL.trimEnd('/')

    fun url(path: String): String {
        val suffix = if (path.startsWith("/")) path else "/$path"
        return baseUrl + suffix
    }

    fun documentUrl(apiPath: String, inline: Boolean = false): String {
        val base = url(apiPath)
        return if (inline) "$base?inline=1" else base
    }
}
