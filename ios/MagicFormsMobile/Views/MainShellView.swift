import SwiftUI

struct MainShellView: View {
    @ObservedObject var auth: AuthViewModel
    @EnvironmentObject private var language: LanguageManager
    @EnvironmentObject private var offlineQueue: OfflineSubmitQueue
    @State private var showMenu = false
    @State private var showInbox = false
    @State private var showSignatures = false
    @State private var showSearch = false
    @State private var showPending = false

    private var onFormsHome: Bool {
        !showInbox && !showSignatures && !showSearch && !showPending
    }

    private var screenTitle: String {
        if showPending { return language.t(.formsToComplete) }
        if showSearch { return language.t(.search) }
        if showSignatures { return language.t(.signatures) }
        if showInbox { return language.t(.inbox) }
        return language.t(.forms)
    }

    /// Org name under the nav title only when there is no logo strip or multiple orgs.
    private var bannerTitleEntityLabel: String {
        let label = auth.bannerEntityLabel
        if auth.bannerLogoURL != nil, !label.contains("·") { return "" }
        return label
    }

    var body: some View {
        VStack(spacing: 0) {
            if let logoURL = auth.bannerLogoURL {
                OrganizationLogoBanner(
                    url: logoURL,
                    accessibilityLabel: auth.bannerEntityLabel.isEmpty
                        ? "Organization logo"
                        : auth.bannerEntityLabel
                )
                .background(Color(.systemBackground))
                Divider()
            }

            NavigationStack {
            Group {
                if showPending {
                    PendingRelatedView(auth: auth)
                } else if showSearch {
                    SubmissionSearchView(auth: auth)
                } else if showSignatures {
                    MySignaturesView(auth: auth)
                } else if showInbox {
                    InboxView(auth: auth)
                } else {
                    FormsHomeView(auth: auth)
                }
            }
            .navigationBarTitleDisplayMode(.inline)
            .safeAreaInset(edge: .top, spacing: 0) {
                if offlineQueue.pendingCount > 0 {
                    Text(language.t(.pendingSync, offlineQueue.pendingCount))
                        .font(.caption)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 6)
                        .background(Color.orange.opacity(0.15))
                }
            }
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    leadingToolbarContent
                }
                ToolbarItem(placement: .principal) {
                    AppBannerTitle(
                        entityLabel: bannerTitleEntityLabel,
                        screenTitle: screenTitle,
                        username: auth.user?.username ?? ""
                    )
                }
                if onFormsHome {
                    ToolbarItem(placement: .topBarTrailing) {
                        Button {
                            showInbox = true
                        } label: {
                            inboxTrayIcon
                                .padding(.trailing, 4)
                        }
                        .accessibilityLabel(inboxAccessibilityLabel)
                    }
                }
            }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .sheet(isPresented: $showMenu) {
            DrawerMenuView(auth: auth, onOpenInbox: {
                showMenu = false
                showInbox = true
                showSearch = false
                showSignatures = false
            }, onOpenSignatures: {
                showMenu = false
                showSignatures = true
                showSearch = false
                showInbox = false
            }, onOpenSearch: {
                showMenu = false
                showSearch = true
                showSignatures = false
                showInbox = false
                showPending = false
            }, onOpenPending: {
                showMenu = false
                showPending = true
                showSearch = false
                showSignatures = false
                showInbox = false
            })
        }
        .task {
            await auth.loadHomeData()
        }
        .onChange(of: showInbox) { _, isShowing in
            if isShowing {
                Task { await auth.refreshInbox() }
            }
        }
    }

    @ViewBuilder
    private var leadingToolbarContent: some View {
        if showInbox || showSignatures || showSearch || showPending {
            Button {
                if showPending {
                    showPending = false
                } else if showSearch {
                    showSearch = false
                } else if showSignatures {
                    showSignatures = false
                } else {
                    showInbox = false
                }
            } label: {
                Image(systemName: "chevron.left")
                    .fontWeight(.semibold)
            }
            .accessibilityLabel(language.t(.backToForms))
        } else {
            Button {
                showMenu = true
            } label: {
                Image(systemName: "line.3.horizontal")
            }
            .accessibilityLabel(language.t(.menu))
        }
    }

    private var inboxTrayIcon: some View {
        ZStack(alignment: .topTrailing) {
            Image(systemName: "tray.fill")
                .font(.body.weight(.medium))
                .padding(.top, 6)
                .padding(.trailing, 8)

            if auth.inboxBadgeCount > 0 {
                Text(badgeText(auth.inboxBadgeCount))
                    .font(.system(size: 11, weight: .bold))
                    .monospacedDigit()
                    .foregroundStyle(.white)
                    .padding(.horizontal, 5)
                    .padding(.vertical, 2)
                    .background(Capsule().fill(Color.red))
                    .fixedSize()
                    .lineLimit(1)
            }
        }
        .frame(minWidth: 36, minHeight: 28)
    }

    private var inboxAccessibilityLabel: String {
        let n = auth.inboxBadgeCount
        if n == 0 { return language.t(.inbox) }
        return language.t(.inboxOpen, n)
    }

    private func badgeText(_ count: Int) -> String {
        count > 99 ? "99+" : "\(count)"
    }
}

#Preview {
    MainShellView(auth: AuthViewModel())
}
