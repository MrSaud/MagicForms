import Foundation

@MainActor
final class AuthViewModel: ObservableObject {
    @Published var entitySlug = ""
    @Published var username = ""
    @Published var password = ""
    @Published private(set) var directoryEntities: [APIEntity] = []
    @Published var user: APIUser?
    @Published var entities: [APIEntity] = []
    @Published var isLoading = false
    @Published var errorMessage: String?

    @Published private(set) var homeSummary: HomeSummary?
    @Published private(set) var publishedForms: [PublishedFormItem] = []
    @Published private(set) var inboxItems: [InboxItem] = []
    @Published private(set) var inboxTotal = 0
    @Published private(set) var isLoadingHome = false
    @Published private(set) var inboxActingIds: Set<Int> = []
    @Published var inboxItemErrors: [Int: String] = [:]
    /// False until keychain token (if any) has been validated — avoids flashing the login screen.
    @Published private(set) var isSessionReady = false
    @Published var sessionExpiredMessage: String?

    private(set) var token: String?
    private var sessionObserver: NSObjectProtocol?

    /// Studio nav badge; fall back to loaded inbox list if summary is not ready yet.
    var inboxBadgeCount: Int {
        let fromSummary = homeSummary?.inboxCount ?? 0
        return max(fromSummary, inboxTotal)
    }

    /// Organization line for the app bar (same as studio header).
    var bannerEntityLabel: String {
        let fromSummary = homeSummary?.bannerEntityName.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        if !fromSummary.isEmpty { return fromSummary }
        return entities.map(\.name).filter { !$0.isEmpty }.joined(separator: " · ")
    }

    var bannerLogoURL: URL? {
        if let url = homeSummary?.bannerLogoUrl.trimmingCharacters(in: .whitespacesAndNewlines),
           !url.isEmpty,
           let parsed = URL(string: url) {
            return parsed
        }
        if entities.count == 1,
           let url = entities[0].logoUrl?.trimmingCharacters(in: .whitespacesAndNewlines),
           !url.isEmpty,
           let parsed = URL(string: url) {
            return parsed
        }
        return nil
    }

    var isLoggedIn: Bool { token != nil && user != nil }

    /// Directory sign-in needs an organization slug whenever any directory org is configured.
    var requiresEntitySlug: Bool {
        !directoryEntities.isEmpty
    }

    var canSubmitLogin: Bool {
        let userOk = !username.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        let entityOk = !requiresEntitySlug
            || !entitySlug.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        return userOk && entityOk && !password.isEmpty
    }

    init() {
        sessionObserver = NotificationCenter.default.addObserver(
            forName: .mobileSessionExpired,
            object: nil,
            queue: .main
        ) { [weak self] _ in
            Task { @MainActor in
                self?.handleSessionExpired()
            }
        }
    }

    deinit {
        if let sessionObserver {
            NotificationCenter.default.removeObserver(sessionObserver)
        }
    }

    func bootstrap() async {
        if let saved = KeychainTokenStore.load() {
            token = saved
            await validateStoredSession()
        }
        await loadDirectoryEntities()
        isSessionReady = true
    }

    func loadDirectoryEntities() async {
        do {
            directoryEntities = try await AuthAPI.fetchDirectoryEntities()
        } catch {
            directoryEntities = []
        }
    }

    func login() async {
        errorMessage = nil
        isLoading = true
        defer { isLoading = false }

        let trimmedUser = username.trimmingCharacters(in: .whitespacesAndNewlines)
        let trimmedSlug = entitySlug.trimmingCharacters(in: .whitespacesAndNewlines)

        if trimmedUser.isEmpty {
            errorMessage = "Enter your username."
            return
        }

        if requiresEntitySlug, trimmedSlug.isEmpty {
            errorMessage = "Enter your organization slug (e.g. mosa-kuwait)."
            return
        }

        let slugForAPI = trimmedSlug.isEmpty ? nil : trimmedSlug

        do {
            let response = try await AuthAPI.login(
                username: trimmedUser,
                password: password,
                entitySlug: slugForAPI
            )
            guard let tokenValue = response.token else {
                errorMessage = "No token returned."
                return
            }
            try KeychainTokenStore.save(token: tokenValue)
            token = tokenValue
            user = response.user
            entities = response.entities ?? []
            password = ""
            PushRegistration.shared.bindAuthToken(tokenValue)
            await PushRegistration.shared.requestPermissionAndRegister()
            await loadHomeData()
            _ = await OfflineSubmitQueue.shared.flush(authToken: tokenValue)
        } catch let apiError as APIError {
            if apiError.code == "organization_required" {
                if let list = apiError.entities, !list.isEmpty {
                    directoryEntities = list
                }
                errorMessage = "Enter your organization slug, then your username."
            } else {
                errorMessage = apiError.message
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func refreshSession() async {
        guard token != nil else { return }
        isLoading = true
        defer { isLoading = false }
        let ok = await validateStoredSession()
        if !ok {
            errorMessage = "Session expired. Please sign in again."
        }
    }

    @discardableResult
    private func validateStoredSession() async -> Bool {
        guard let token else { return false }
        do {
            let response = try await AuthAPI.me(token: token)
            user = response.user
            entities = response.entities ?? []
            errorMessage = nil
            PushRegistration.shared.bindAuthToken(token)
            await PushRegistration.shared.requestPermissionAndRegister()
            await loadHomeData()
            _ = await OfflineSubmitQueue.shared.flush(authToken: token)
            return true
        } catch let apiError as APIError where apiError.code == "authentication_required" {
            handleSessionExpired()
            return false
        } catch {
            signOutLocal()
            return false
        }
    }

    func handleSessionExpired() {
        guard token != nil else { return }
        sessionExpiredMessage = "Your session expired. Please sign in again."
        signOutLocal()
    }

    func clearSessionExpiredMessage() {
        sessionExpiredMessage = nil
    }

    func loadHomeData() async {
        guard let token else { return }
        isLoadingHome = true
        defer { isLoadingHome = false }

        do {
            homeSummary = try await HomeAPI.fetchSummary(token: token)
        } catch {
            errorMessage = error.localizedDescription
        }

        do {
            publishedForms = try await HomeAPI.fetchPublishedForms(token: token)
        } catch {
            if errorMessage == nil {
                errorMessage = error.localizedDescription
            }
        }

        do {
            let inbox = try await HomeAPI.fetchInbox(token: token)
            inboxItems = inbox.items
            inboxTotal = inbox.total
        } catch {
            if errorMessage == nil {
                errorMessage = error.localizedDescription
            }
        }
    }

    func refreshInbox() async {
        guard let token else { return }
        isLoadingHome = true
        defer { isLoadingHome = false }
        do {
            async let summary = HomeAPI.fetchSummary(token: token)
            async let inbox = HomeAPI.fetchInbox(token: token)
            let (s, i) = try await (summary, inbox)
            homeSummary = s
            inboxItems = i.items
            inboxTotal = i.total
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func isInboxActing(_ submissionId: Int) -> Bool {
        inboxActingIds.contains(submissionId)
    }

    func performInboxWorkflow(
        submissionId: Int,
        decision: String,
        comment: String?,
        workflowActionAnchor: Int?
    ) async {
        guard let token else { return }
        inboxActingIds.insert(submissionId)
        inboxItemErrors.removeValue(forKey: submissionId)
        defer { inboxActingIds.remove(submissionId) }

        do {
            _ = try await HomeAPI.performWorkflow(
                token: token,
                submissionId: submissionId,
                decision: decision,
                comment: comment,
                workflowActionAnchor: workflowActionAnchor
            )
            await refreshInbox()
        } catch let apiError as APIError {
            inboxItemErrors[submissionId] = apiError.message
        } catch {
            inboxItemErrors[submissionId] = error.localizedDescription
        }
    }

    func logout() async {
        if let token {
            isLoading = true
            await PushRegistration.shared.unregister()
            _ = try? await AuthAPI.logout(token: token)
            isLoading = false
        }
        signOutLocal()
    }

    func signOutLocal() {
        PushRegistration.shared.bindAuthToken(nil)
        KeychainTokenStore.delete()
        token = nil
        user = nil
        entities = []
        password = ""
        homeSummary = nil
        publishedForms = []
        inboxItems = []
        inboxTotal = 0
        inboxActingIds = []
        inboxItemErrors = [:]
    }
}
