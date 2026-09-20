package com.magicforms.mobile.ui

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.magicforms.mobile.data.OfflineSubmitQueue
import com.magicforms.mobile.data.PushTokenStore
import com.magicforms.mobile.data.SessionExpiredException
import com.magicforms.mobile.data.TokenStore
import com.magicforms.mobile.data.api.AuthApi
import com.magicforms.mobile.data.api.DeviceApi
import com.magicforms.mobile.data.api.HomeApi
import android.provider.Settings
import com.magicforms.mobile.data.models.ApiEntity
import com.magicforms.mobile.data.models.ApiException
import com.magicforms.mobile.data.models.ApiUser
import com.magicforms.mobile.data.models.HomeSummaryResponse
import com.magicforms.mobile.data.models.InboxItem
import com.magicforms.mobile.data.models.PublishedFormItem
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

data class AuthUiState(
    val entitySlug: String = "",
    val username: String = "",
    val password: String = "",
    val directoryEntities: List<ApiEntity> = emptyList(),
    val user: ApiUser? = null,
    val entities: List<ApiEntity> = emptyList(),
    val isLoading: Boolean = false,
    val errorMessage: String? = null,
    val token: String? = null,
    val homeSummary: HomeSummaryResponse? = null,
    val publishedForms: List<PublishedFormItem> = emptyList(),
    val inboxItems: List<InboxItem> = emptyList(),
    val inboxTotal: Int = 0,
    val isLoadingHome: Boolean = false,
    val inboxActingIds: Set<Int> = emptySet(),
    val inboxItemErrors: Map<Int, String> = emptyMap(),
    /** False until a saved token (if any) has been validated — avoids flashing the login screen. */
    val isSessionReady: Boolean = false,
    val sessionExpiredMessage: String? = null,
    val pendingSyncCount: Int = 0,
) {
    val isLoggedIn: Boolean get() = token != null && user != null

    val requiresEntitySlug: Boolean get() = directoryEntities.isNotEmpty()

    val inboxBadgeCount: Int
        get() = maxOf(homeSummary?.inboxCount ?: 0, inboxTotal)

    val bannerEntityLabel: String
        get() {
            val fromSummary = homeSummary?.bannerEntityName?.trim().orEmpty()
            if (fromSummary.isNotBlank()) return fromSummary
            return entities.map { it.name }.filter { it.isNotBlank() }.joinToString(" · ")
        }

    val bannerLogoUrl: String?
        get() {
            homeSummary?.bannerLogoUrl?.trim()?.takeIf { it.isNotBlank() }?.let { return it }
            if (entities.size == 1) {
                return entities[0].logoUrl?.trim()?.takeIf { it.isNotBlank() }
            }
            return null
        }

    val canSubmitLogin: Boolean
        get() {
            val userOk = username.trim().isNotEmpty()
            val entityOk = !requiresEntitySlug || entitySlug.trim().isNotEmpty()
            return userOk && entityOk && password.isNotEmpty() && !isLoading
        }
}

class AuthViewModel(application: Application) : AndroidViewModel(application) {
    private val authApi = AuthApi()
    private val homeApi = HomeApi()
    private val deviceApi = DeviceApi()
    private val tokenStore = TokenStore(application)
    private val offlineQueue = OfflineSubmitQueue(application)

    private val _state = MutableStateFlow(AuthUiState())
    val state: StateFlow<AuthUiState> = _state.asStateFlow()

    init {
        bootstrap()
    }

    fun onEntitySlugChange(value: String) = _state.update { it.copy(entitySlug = value) }
    fun onUsernameChange(value: String) = _state.update { it.copy(username = value) }
    fun onPasswordChange(value: String) = _state.update { it.copy(password = value) }

    private fun bootstrap() {
        viewModelScope.launch {
            try {
                tokenStore.load()?.let { saved ->
                    _state.update { it.copy(token = saved) }
                    validateStoredSession()
                }
                loadDirectoryEntities()
            } finally {
                _state.update { it.copy(isSessionReady = true) }
            }
        }
    }

    private suspend fun validateStoredSession(): Boolean {
        val token = _state.value.token ?: return false
        return try {
            val response = withContext(Dispatchers.IO) { authApi.me(token) }
            _state.update {
                it.copy(
                    user = response.user,
                    entities = response.entities.orEmpty(),
                    errorMessage = null,
                )
            }
            loadHomeDataAwait()
            registerPushTokenIfAvailable()
            flushOfflineQueue()
            true
        } catch (_: SessionExpiredException) {
            handleSessionExpired()
            false
        } catch (_: Exception) {
            signOutLocal()
            false
        }
    }

    fun handleSessionExpired() {
        if (_state.value.token == null) return
        _state.update {
            it.copy(sessionExpiredMessage = "Your session expired. Please sign in again.")
        }
        signOutLocal()
    }

    fun clearSessionExpiredMessage() {
        _state.update { it.copy(sessionExpiredMessage = null) }
    }

    fun flushOfflineQueue() {
        val token = _state.value.token ?: return
        viewModelScope.launch {
            val synced = withContext(Dispatchers.IO) { offlineQueue.flush(token) }
            _state.update { it.copy(pendingSyncCount = offlineQueue.pendingCount()) }
            if (synced > 0) loadHomeData()
        }
    }

    fun refreshPendingSyncCount() {
        _state.update { it.copy(pendingSyncCount = offlineQueue.pendingCount()) }
    }

    fun offlineQueue(): OfflineSubmitQueue = offlineQueue

    private suspend fun registerPushTokenIfAvailable() {
        val bearer = _state.value.token ?: return
        val push = PushTokenStore.load(getApplication()) ?: return
        val deviceId = Settings.Secure.getString(
            getApplication().contentResolver,
            Settings.Secure.ANDROID_ID,
        ).orEmpty()
        runCatching {
            withContext(Dispatchers.IO) {
                deviceApi.registerPushToken(bearer, push, deviceId)
            }
        }
    }

    fun loadDirectoryEntities() {
        viewModelScope.launch {
            runCatching {
                withContext(Dispatchers.IO) { authApi.fetchDirectoryEntities() }
            }.onSuccess { list ->
                _state.update { it.copy(directoryEntities = list) }
            }
        }
    }

    fun login() {
        val current = _state.value
        val trimmedUser = current.username.trim()
        val trimmedSlug = current.entitySlug.trim()

        if (trimmedUser.isEmpty()) {
            _state.update { it.copy(errorMessage = "Enter your username.") }
            return
        }
        if (current.requiresEntitySlug && trimmedSlug.isEmpty()) {
            _state.update { it.copy(errorMessage = "Enter your organization slug (e.g. mosa-kuwait).") }
            return
        }

        val slugForApi = trimmedSlug.ifBlank { null }
        _state.update { it.copy(isLoading = true, errorMessage = null) }

        viewModelScope.launch {
            try {
                val response = withContext(Dispatchers.IO) {
                    authApi.login(trimmedUser, current.password, slugForApi)
                }
                val tokenValue = response.token
                    ?: run {
                        _state.update { it.copy(isLoading = false, errorMessage = "No token returned.") }
                        return@launch
                    }
                tokenStore.save(tokenValue)
                _state.update {
                    it.copy(
                        isLoading = false,
                        token = tokenValue,
                        user = response.user,
                        entities = response.entities.orEmpty(),
                        password = "",
                        errorMessage = null,
                    )
                }
                registerPushTokenIfAvailable()
                flushOfflineQueue()
                loadHomeData()
            } catch (e: ApiException) {
                val msg = if (e.code == "organization_required") {
                    e.entities?.takeIf { it.isNotEmpty() }?.let { list ->
                        _state.update { s -> s.copy(directoryEntities = list) }
                    }
                    "Enter your organization slug, then your username."
                } else {
                    e.message
                }
                _state.update { it.copy(isLoading = false, errorMessage = msg) }
            } catch (e: Exception) {
                _state.update {
                    it.copy(isLoading = false, errorMessage = e.message ?: "Sign-in failed.")
                }
            }
        }
    }

    fun refreshSession() {
        val token = _state.value.token ?: return
        _state.update { it.copy(isLoading = true) }
        viewModelScope.launch {
            val ok = validateStoredSession()
            _state.update {
                it.copy(
                    isLoading = false,
                    errorMessage = if (ok) null else "Session expired. Please sign in again.",
                )
            }
        }
    }

    fun loadHomeData() {
        val token = _state.value.token ?: return
        _state.update { it.copy(isLoadingHome = true) }
        viewModelScope.launch {
            try {
                loadHomeDataAwait()
            } catch (_: SessionExpiredException) {
                handleSessionExpired()
            }
        }
    }

    private suspend fun loadHomeDataAwait() {
        val token = _state.value.token ?: return
        _state.update { it.copy(isLoadingHome = true) }
        var summary: HomeSummaryResponse? = null
        var forms: List<PublishedFormItem>? = null
        var inboxItems: List<InboxItem> = emptyList()
        var inboxTotal = 0
        var error: String? = null

        withContext(Dispatchers.IO) {
            runCatching { homeApi.fetchSummary(token) }
                .onSuccess { summary = it }
                .onFailure { e ->
                    if (e is SessionExpiredException) throw e
                    error = e.message ?: "Failed to load summary."
                }

            runCatching { homeApi.fetchPublishedForms(token).forms }
                .onSuccess { forms = it }
                .onFailure {
                    if (error == null) error = it.message ?: "Failed to load forms."
                }

            runCatching { homeApi.fetchInbox(token) }
                .onSuccess {
                    inboxItems = it.items
                    inboxTotal = it.total
                }
                .onFailure {
                    if (error == null) error = it.message ?: "Failed to load inbox."
                }
        }

        _state.update {
            it.copy(
                isLoadingHome = false,
                homeSummary = summary ?: it.homeSummary,
                publishedForms = forms ?: it.publishedForms,
                inboxItems = inboxItems,
                inboxTotal = inboxTotal,
                errorMessage = error,
                pendingSyncCount = offlineQueue.pendingCount(),
            )
        }
    }

    fun refreshInbox() {
        val token = _state.value.token ?: return
        _state.update { it.copy(isLoadingHome = true) }
        viewModelScope.launch {
            try {
                val result = withContext(Dispatchers.IO) {
                    coroutineScope {
                        val summary = async { homeApi.fetchSummary(token) }
                        val inbox = async { homeApi.fetchInbox(token) }
                        Pair(summary.await(), inbox.await())
                    }
                }
                _state.update {
                    it.copy(
                        isLoadingHome = false,
                        homeSummary = result.first,
                        inboxItems = result.second.items,
                        inboxTotal = result.second.total,
                    )
                }
            } catch (e: Exception) {
                _state.update {
                    it.copy(isLoadingHome = false, errorMessage = e.message ?: "Failed to refresh inbox.")
                }
            }
        }
    }

    fun performInboxWorkflow(
        submissionId: Int,
        decision: String,
        comment: String?,
        workflowActionAnchor: Int?,
        onSuccess: () -> Unit = {},
    ) {
        val token = _state.value.token ?: return
        _state.update {
            it.copy(
                inboxActingIds = it.inboxActingIds + submissionId,
                inboxItemErrors = it.inboxItemErrors - submissionId,
            )
        }
        viewModelScope.launch {
            try {
                withContext(Dispatchers.IO) {
                    homeApi.performWorkflow(token, submissionId, decision, comment, workflowActionAnchor)
                    val summary = homeApi.fetchSummary(token)
                    val inbox = homeApi.fetchInbox(token)
                    summary to inbox
                }.let { (summary, inbox) ->
                    _state.update {
                        it.copy(
                            homeSummary = summary,
                            inboxItems = inbox.items,
                            inboxTotal = inbox.total,
                        )
                    }
                }
                onSuccess()
            } catch (e: ApiException) {
                _state.update {
                    it.copy(inboxItemErrors = it.inboxItemErrors + (submissionId to (e.message ?: "Workflow failed.")))
                }
            } catch (e: Exception) {
                _state.update {
                    it.copy(inboxItemErrors = it.inboxItemErrors + (submissionId to (e.message ?: "Workflow failed.")))
                }
            } finally {
                _state.update { it.copy(inboxActingIds = it.inboxActingIds - submissionId) }
            }
        }
    }

    fun logout() {
        val token = _state.value.token
        val push = PushTokenStore.load(getApplication())
        _state.update { it.copy(isLoading = true) }
        viewModelScope.launch {
            if (token != null) {
                runCatching {
                    withContext(Dispatchers.IO) {
                        if (push != null) deviceApi.unregisterPushToken(token, push)
                        authApi.logout(token)
                    }
                }
            }
            signOutLocal()
            _state.update { it.copy(isLoading = false) }
        }
    }

    private fun signOutLocal() {
        tokenStore.delete()
        _state.update {
            it.copy(
                token = null,
                user = null,
                entities = emptyList(),
                password = "",
                homeSummary = null,
                publishedForms = emptyList(),
                inboxItems = emptyList(),
                inboxTotal = 0,
                inboxActingIds = emptySet(),
                inboxItemErrors = emptyMap(),
                pendingSyncCount = offlineQueue.pendingCount(),
            )
        }
    }
}
