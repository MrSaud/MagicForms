package com.magicforms.mobile

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.viewmodel.compose.viewModel
import com.magicforms.mobile.data.BiometricPreferences
import com.magicforms.mobile.data.LanguagePreferences
import com.magicforms.mobile.ui.AppLocaleProvider
import com.magicforms.mobile.ui.AuthViewModel
import com.magicforms.mobile.ui.BiometricLockScreen
import com.magicforms.mobile.ui.home.MainShellScreen
import com.magicforms.mobile.ui.login.LoginScreen
import com.magicforms.mobile.ui.theme.MagicFormsTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        LanguagePreferences.init(applicationContext)
        LanguagePreferences.setTag(LanguagePreferences.getTag())
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            var languageTag by remember { mutableStateOf(LanguagePreferences.getTag()) }
            val context = LocalContext.current
            var isUnlocked by remember { mutableStateOf(true) }
            val lifecycleOwner = LocalLifecycleOwner.current
            val authViewModel: AuthViewModel = viewModel()
            val state by authViewModel.state.collectAsState()

            DisposableEffect(lifecycleOwner, state.isLoggedIn) {
                val observer = LifecycleEventObserver { _, event ->
                    if (event == Lifecycle.Event.ON_STOP &&
                        state.isLoggedIn &&
                        BiometricPreferences.isEnabled(context)
                    ) {
                        isUnlocked = false
                    }
                }
                lifecycleOwner.lifecycle.addObserver(observer)
                onDispose { lifecycleOwner.lifecycle.removeObserver(observer) }
            }

            AppLocaleProvider(languageTag = languageTag) {
                MagicFormsTheme {
                    if (state.sessionExpiredMessage != null) {
                        AlertDialog(
                            onDismissRequest = { authViewModel.clearSessionExpiredMessage() },
                            title = { Text(stringResource(R.string.session_expired_title)) },
                            text = { Text(state.sessionExpiredMessage ?: stringResource(R.string.session_expired_message)) },
                            confirmButton = {
                                TextButton(onClick = { authViewModel.clearSessionExpiredMessage() }) {
                                    Text(stringResource(R.string.ok))
                                }
                            },
                        )
                    }

                    when {
                        !state.isSessionReady -> {
                            Box(
                                modifier = Modifier.fillMaxSize(),
                                contentAlignment = Alignment.Center,
                            ) {
                                CircularProgressIndicator()
                            }
                        }
                        state.isLoggedIn && BiometricPreferences.isEnabled(context) && !isUnlocked -> {
                            BiometricLockScreen(onUnlocked = { isUnlocked = true })
                        }
                        state.isLoggedIn -> {
                            MainShellScreen(
                                state = state,
                                authViewModel = authViewModel,
                                languageTag = languageTag,
                                onLanguageChange = { tag ->
                                    LanguagePreferences.setTag(tag)
                                    languageTag = tag
                                    authViewModel.loadHomeData()
                                },
                            )
                        }
                        else -> {
                            LoginScreen(
                                state = state,
                                languageTag = languageTag,
                                onLanguageChange = { tag ->
                                    LanguagePreferences.setTag(tag)
                                    languageTag = tag
                                },
                                onEntitySlugChange = authViewModel::onEntitySlugChange,
                                onUsernameChange = authViewModel::onUsernameChange,
                                onPasswordChange = authViewModel::onPasswordChange,
                                onSignIn = authViewModel::login,
                            )
                        }
                    }
                }
            }
        }
    }
}
