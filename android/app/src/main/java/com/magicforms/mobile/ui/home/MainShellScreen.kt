package com.magicforms.mobile.ui.home

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Inbox
import androidx.compose.material.icons.filled.Menu
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.Badge
import androidx.compose.material3.BadgedBox
import androidx.compose.material3.DrawerValue
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Switch
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalNavigationDrawer
import androidx.compose.material3.NavigationDrawerItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.rememberDrawerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.res.stringResource
import com.magicforms.mobile.R
import com.magicforms.mobile.data.BiometricPreferences
import com.magicforms.mobile.ui.AuthUiState
import com.magicforms.mobile.ui.AuthViewModel
import com.magicforms.mobile.ui.LanguagePicker
import com.magicforms.mobile.ui.search.SubmissionSearchScreen
import com.magicforms.mobile.ui.signatures.MySignaturesScreen
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MainShellScreen(
    state: AuthUiState,
    authViewModel: AuthViewModel,
    languageTag: String,
    onLanguageChange: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    val drawerState = rememberDrawerState(DrawerValue.Closed)
    val scope = rememberCoroutineScope()
    var showInbox by remember { mutableStateOf(false) }
    var showSignatures by remember { mutableStateOf(false) }
    var showSearch by remember { mutableStateOf(false) }
    var showPending by remember { mutableStateOf(false) }
    var inboxDetailId by remember { mutableStateOf<Int?>(null) }
    var searchDetailId by remember { mutableStateOf<Int?>(null) }
    var formIntroId by remember { mutableStateOf<Int?>(null) }
    var formSubmitId by remember { mutableStateOf<Int?>(null) }
    var relatedAccessToken by remember { mutableStateOf<String?>(null) }
    var formSubmitTitle by remember { mutableStateOf("") }
    var postSubmitDetailId by remember { mutableStateOf<Int?>(null) }
    val context = LocalContext.current

    val inboxDetailTitle = inboxDetailId?.let { id ->
        state.inboxItems.find { it.id == id }?.form?.title
    }

    LaunchedEffect(state.token) {
        if (state.token != null) {
            authViewModel.loadHomeData()
        }
    }

    LaunchedEffect(showInbox) {
        if (showInbox && state.token != null) {
            authViewModel.refreshInbox()
        }
    }

    ModalNavigationDrawer(
        drawerState = drawerState,
        drawerContent = {
            DrawerMenuContent(
                state = state,
                languageTag = languageTag,
                onLanguageChange = onLanguageChange,
                onClose = { scope.launch { drawerState.close() } },
                onRefresh = {
                    scope.launch { drawerState.close() }
                    authViewModel.loadHomeData()
                },
                onSignOut = {
                    scope.launch { drawerState.close() }
                    authViewModel.logout()
                },
                onOpenUrl = { url ->
                    scope.launch { drawerState.close() }
                    runCatching {
                        context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
                    }
                },
                onOpenSignatures = {
                    scope.launch { drawerState.close() }
                    showSignatures = true
                    showInbox = false
                    showSearch = false
                    showPending = false
                    inboxDetailId = null
                    searchDetailId = null
                },
                onOpenSearch = {
                    scope.launch { drawerState.close() }
                    showSearch = true
                    showSignatures = false
                    showInbox = false
                    showPending = false
                    inboxDetailId = null
                    searchDetailId = null
                },
                onOpenInbox = {
                    scope.launch { drawerState.close() }
                    showInbox = true
                    showSearch = false
                    showSignatures = false
                    showPending = false
                    inboxDetailId = null
                    searchDetailId = null
                },
                onOpenPending = {
                    scope.launch { drawerState.close() }
                    showPending = true
                    showInbox = false
                    showSearch = false
                    showSignatures = false
                    inboxDetailId = null
                    searchDetailId = null
                    formSubmitId = null
                    relatedAccessToken = null
                },
                applicantPendingCount = state.homeSummary?.applicantPendingCount ?: 0,
            )
        },
        modifier = modifier,
    ) {
        Scaffold(
            topBar = {
                TopAppBar(
                    title = {
                        AppBannerTitle(
                            entityLabel = bannerTitleEntityLabel(state),
                            screenTitle = when {
                                postSubmitDetailId != null -> stringResource(R.string.request)
                                formSubmitId != null || relatedAccessToken != null ->
                                    formSubmitTitle.ifBlank { stringResource(R.string.forms) }
                                showSearch && searchDetailId != null -> stringResource(R.string.request)
                                showSearch -> stringResource(R.string.search)
                                showSignatures -> stringResource(R.string.signatures)
                                showPending -> stringResource(R.string.forms_to_complete)
                                inboxDetailId != null -> inboxDetailTitle ?: stringResource(R.string.request)
                                showInbox -> stringResource(R.string.inbox)
                                else -> stringResource(R.string.forms)
                            },
                            username = state.user?.username.orEmpty(),
                        )
                    },
                    navigationIcon = {
                        if (showInbox || showSignatures || showSearch || showPending ||
                            formSubmitId != null || relatedAccessToken != null || postSubmitDetailId != null
                        ) {
                            IconButton(onClick = {
                                when {
                                    postSubmitDetailId != null -> postSubmitDetailId = null
                                    formSubmitId != null || relatedAccessToken != null -> {
                                        formSubmitId = null
                                        relatedAccessToken = null
                                    }
                                    searchDetailId != null -> searchDetailId = null
                                    inboxDetailId != null -> inboxDetailId = null
                                    showSearch -> showSearch = false
                                    showSignatures -> showSignatures = false
                                    showPending -> showPending = false
                                    else -> showInbox = false
                                }
                            }) {
                                Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = stringResource(R.string.back))
                            }
                        } else {
                            IconButton(onClick = { scope.launch { drawerState.open() } }) {
                                Icon(Icons.Default.Menu, contentDescription = stringResource(R.string.menu))
                            }
                        }
                    },
                    actions = {
                        if (!showInbox && !showSignatures && !showSearch && !showPending &&
                            formSubmitId == null && relatedAccessToken == null
                        ) {
                            val count = state.inboxBadgeCount
                            val inboxLabel = if (count > 0) {
                                stringResource(R.string.inbox_open, count)
                            } else {
                                stringResource(R.string.inbox)
                            }
                            if (count > 0) {
                                BadgedBox(
                                    modifier = Modifier.padding(end = 6.dp),
                                    badge = {
                                        Badge(
                                            containerColor = MaterialTheme.colorScheme.error,
                                        ) {
                                            Text(
                                                text = if (count > 99) "99+" else count.toString(),
                                                style = MaterialTheme.typography.labelSmall,
                                            )
                                        }
                                    },
                                ) {
                                    IconButton(onClick = {
                                        showInbox = true
                                        inboxDetailId = null
                                    }) {
                                        Icon(Icons.Default.Inbox, contentDescription = inboxLabel)
                                    }
                                }
                            } else {
                                IconButton(onClick = {
                                    showInbox = true
                                    inboxDetailId = null
                                }) {
                                    Icon(Icons.Default.Inbox, contentDescription = inboxLabel)
                                }
                            }
                        }
                    },
                )
            },
        ) { padding ->
            Column(modifier = Modifier.padding(padding).fillMaxSize()) {
                state.bannerLogoUrl?.takeIf { it.isNotBlank() }?.let { logoUrl ->
                    OrganizationLogoBanner(
                        logoUrl = logoUrl,
                        contentDescription = state.bannerEntityLabel.ifBlank {
                            "Organization logo"
                        },
                    )
                    HorizontalDivider()
                }
                if (state.pendingSyncCount > 0) {
                    Text(
                        stringResource(R.string.pending_sync, state.pendingSyncCount),
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.tertiary,
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(horizontal = 16.dp, vertical = 6.dp),
                    )
                }
                Box(modifier = Modifier.weight(1f).fillMaxWidth()) {
                when {
                    postSubmitDetailId != null -> InboxDetailScreen(
                        submissionId = postSubmitDetailId!!,
                        authViewModel = authViewModel,
                        onDone = {
                            postSubmitDetailId = null
                            authViewModel.loadHomeData()
                        },
                        modifier = Modifier.fillMaxSize(),
                    )
                    formIntroId != null -> FormIntroScreen(
                        formId = formIntroId!!,
                        formTitle = formSubmitTitle,
                        authViewModel = authViewModel,
                        onApply = {
                            formSubmitId = formIntroId
                            formIntroId = null
                        },
                        onBack = { formIntroId = null },
                        modifier = Modifier.fillMaxSize(),
                    )
                    formSubmitId != null || relatedAccessToken != null -> FormSubmitScreen(
                        formId = formSubmitId,
                        relatedAccessToken = relatedAccessToken,
                        formTitle = formSubmitTitle,
                        authViewModel = authViewModel,
                        onViewSubmission = { id ->
                            formSubmitId = null
                            relatedAccessToken = null
                            postSubmitDetailId = id
                        },
                        onDone = {
                            formSubmitId = null
                            relatedAccessToken = null
                            authViewModel.loadHomeData()
                        },
                        modifier = Modifier.fillMaxSize(),
                    )
                    showPending -> PendingRelatedScreen(
                        authViewModel = authViewModel,
                        onOpenForm = { item ->
                            relatedAccessToken = item.accessToken
                            formSubmitId = null
                            formSubmitTitle = item.childForm.title
                        },
                        modifier = Modifier.fillMaxSize(),
                    )
                    showSearch -> when (val detailId = searchDetailId) {
                        null -> SubmissionSearchScreen(
                            authViewModel = authViewModel,
                            onOpenDetail = { searchDetailId = it },
                            modifier = Modifier.fillMaxSize(),
                        )
                        else -> com.magicforms.mobile.ui.home.InboxDetailScreen(
                            submissionId = detailId,
                            authViewModel = authViewModel,
                            onDone = { searchDetailId = null },
                            modifier = Modifier.fillMaxSize(),
                        )
                    }
                    showSignatures -> MySignaturesScreen(
                        authViewModel = authViewModel,
                        modifier = Modifier.fillMaxSize(),
                    )
                    showInbox -> when (val detailId = inboxDetailId) {
                        null -> InboxScreen(
                            state = state,
                            authViewModel = authViewModel,
                            onOpenDetail = { inboxDetailId = it },
                            modifier = Modifier.fillMaxSize(),
                        )
                        else -> InboxDetailScreen(
                            submissionId = detailId,
                            authViewModel = authViewModel,
                            onDone = { inboxDetailId = null },
                            modifier = Modifier.fillMaxSize(),
                        )
                    }
                    else -> FormsHomeScreen(
                        state = state,
                        onOpenForm = { form ->
                            formSubmitId = form.id
                            formSubmitTitle = form.title
                        },
                        onReadIntro = { form ->
                            formIntroId = form.id
                            formSubmitTitle = form.title
                            formSubmitId = null
                            relatedAccessToken = null
                        },
                        modifier = Modifier.fillMaxSize(),
                    )
                }
                }
            }
        }
    }
}

private fun bannerTitleEntityLabel(state: AuthUiState): String {
    val label = state.bannerEntityLabel
    val hasLogo = !state.bannerLogoUrl.isNullOrBlank()
    return if (hasLogo && !label.contains("·")) "" else label
}

@Composable
private fun DrawerMenuContent(
    state: AuthUiState,
    languageTag: String,
    onLanguageChange: (String) -> Unit,
    onClose: () -> Unit,
    onRefresh: () -> Unit,
    onSignOut: () -> Unit,
    onOpenUrl: (String) -> Unit,
    onOpenSignatures: () -> Unit,
    onOpenSearch: () -> Unit,
    onOpenInbox: () -> Unit,
    onOpenPending: () -> Unit,
    applicantPendingCount: Int,
) {
    Column(modifier = Modifier.padding(horizontal = 12.dp, vertical = 24.dp)) {
        state.user?.let { user ->
            Text(user.displayName, style = androidx.compose.material3.MaterialTheme.typography.titleMedium)
            Text(user.username, style = androidx.compose.material3.MaterialTheme.typography.bodySmall)
        }
        Spacer(modifier = Modifier.size(16.dp))

        LanguagePicker(
            currentTag = languageTag,
            onLanguageChange = onLanguageChange,
            modifier = Modifier.padding(bottom = 16.dp),
        )

        val context = LocalContext.current
        var biometricEnabled by remember {
            mutableStateOf(BiometricPreferences.isEnabled(context))
        }
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(bottom = 12.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(stringResource(R.string.biometric_unlock), style = MaterialTheme.typography.bodyMedium)
            Switch(
                checked = biometricEnabled,
                onCheckedChange = {
                    biometricEnabled = it
                    BiometricPreferences.setEnabled(context, it)
                },
            )
        }

        val links = state.homeSummary?.menuLinks
        val summary = state.homeSummary
        if (links != null && summary != null) {
            Text(stringResource(R.string.studio), style = androidx.compose.material3.MaterialTheme.typography.labelLarge, modifier = Modifier.padding(vertical = 8.dp))
            val inboxLabel = if (state.inboxBadgeCount > 0) {
                stringResource(R.string.inbox_count, state.inboxBadgeCount)
            } else {
                stringResource(R.string.inbox)
            }
            NavigationDrawerItem(label = { Text(inboxLabel) }, selected = false, onClick = onOpenInbox)
            if (applicantPendingCount > 0) {
                NavigationDrawerItem(
                    label = {
                        Text(stringResource(R.string.forms_to_complete_count, applicantPendingCount))
                    },
                    selected = false,
                    onClick = onOpenPending,
                )
            }
            NavigationDrawerItem(
                icon = { Icon(Icons.Default.Search, contentDescription = null) },
                label = { Text(stringResource(R.string.search)) },
                selected = false,
                onClick = onOpenSearch,
            )
            NavigationDrawerItem(label = { Text(stringResource(R.string.my_signatures)) }, selected = false, onClick = onOpenSignatures)
            if (summary.isStaff || summary.isSuperuser) {
                NavigationDrawerItem(label = { Text(stringResource(R.string.help)) }, selected = false, onClick = { onOpenUrl(links.help) })
            }
        }

        Spacer(modifier = Modifier.size(8.dp))
        NavigationDrawerItem(label = { Text(stringResource(R.string.refresh)) }, selected = false, onClick = onRefresh)
        NavigationDrawerItem(label = { Text(stringResource(R.string.sign_out)) }, selected = false, onClick = onSignOut)
    }
}
