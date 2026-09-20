package com.magicforms.mobile.data

import android.content.Context
import java.util.Locale

object LanguagePreferences {
    private const val PREFS = "magicforms_prefs"
    private const val KEY = "app_language"

    private lateinit var appContext: Context

    fun init(context: Context) {
        appContext = context.applicationContext
    }

    fun getTag(): String {
        if (!::appContext.isInitialized) return "en"
        return appContext.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .getString(KEY, "en")
            ?.takeIf { it == "en" || it == "ar" }
            ?: "en"
    }

    fun setTag(tag: String) {
        val normalized = if (tag == "ar") "ar" else "en"
        appContext.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit()
            .putString(KEY, normalized)
            .apply()
        val locale = Locale.forLanguageTag(normalized)
        Locale.setDefault(locale)
    }

    fun acceptLanguageHeader(): String = getTag()

    fun isRtl(): Boolean = getTag() == "ar"
}
