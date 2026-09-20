package com.magicforms.mobile.ui

import androidx.biometric.BiometricManager
import androidx.biometric.BiometricPrompt
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.fragment.app.FragmentActivity
import com.magicforms.mobile.R

@Composable
fun BiometricLockScreen(onUnlocked: () -> Unit) {
    val context = LocalContext.current
    var errorMessage by remember { mutableStateOf<String?>(null) }

    Column(
        modifier = Modifier.fillMaxSize().padding(24.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(stringResource(R.string.unlock_app), style = MaterialTheme.typography.titleLarge)
        Text(
            stringResource(R.string.unlock_app_desc),
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(vertical = 12.dp),
        )
        errorMessage?.let {
            Text(it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)
        }
        Button(onClick = {
            val activity = context as? FragmentActivity
            if (activity == null) {
                errorMessage = context.getString(R.string.biometric_failed)
                return@Button
            }
            val authenticators = BiometricManager.Authenticators.BIOMETRIC_STRONG
            val can = BiometricManager.from(context).canAuthenticate(authenticators)
            if (can != BiometricManager.BIOMETRIC_SUCCESS) {
                errorMessage = context.getString(R.string.biometric_failed)
                return@Button
            }
            val executor = ContextCompat.getMainExecutor(context)
            val prompt = BiometricPrompt(
                activity,
                executor,
                object : BiometricPrompt.AuthenticationCallback() {
                    override fun onAuthenticationSucceeded(result: BiometricPrompt.AuthenticationResult) {
                        onUnlocked()
                    }

                    override fun onAuthenticationError(errorCode: Int, errString: CharSequence) {
                        errorMessage = errString.toString()
                    }

                    override fun onAuthenticationFailed() {
                        errorMessage = context.getString(R.string.biometric_failed)
                    }
                },
            )
            prompt.authenticate(
                BiometricPrompt.PromptInfo.Builder()
                    .setTitle(context.getString(R.string.unlock_app))
                    .setSubtitle(context.getString(R.string.unlock_app_desc))
                    .setNegativeButtonText(context.getString(R.string.cancel))
                    .setAllowedAuthenticators(authenticators)
                    .build(),
            )
        }) {
            Text(stringResource(R.string.unlock_with_biometrics))
        }
    }
}
