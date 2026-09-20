package com.magicforms.mobile.ui

import android.content.Context
import android.content.res.Configuration
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.remember
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.unit.LayoutDirection
import com.magicforms.mobile.data.LanguagePreferences
import java.util.Locale

fun Context.withAppLocale(): Context {
    val tag = LanguagePreferences.getTag()
    val locale = Locale.forLanguageTag(tag)
    val config = Configuration(resources.configuration)
    config.setLocale(locale)
    config.setLayoutDirection(locale)
    return createConfigurationContext(config)
}

@Composable
fun AppLocaleProvider(
    languageTag: String,
    content: @Composable () -> Unit,
) {
    val base = LocalContext.current
    val localized = remember(languageTag) { base.withAppLocale() }
    val layoutDirection = if (languageTag == "ar") {
        LayoutDirection.Rtl
    } else {
        LayoutDirection.Ltr
    }
    CompositionLocalProvider(
        LocalContext provides localized,
        LocalLayoutDirection provides layoutDirection,
    ) {
        content()
    }
}
