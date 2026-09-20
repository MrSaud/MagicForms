import SwiftUI

struct RootView: View {
    @StateObject private var auth = AuthViewModel()
    @EnvironmentObject private var language: LanguageManager
    @EnvironmentObject private var network: NetworkMonitor
    @EnvironmentObject private var offlineQueue: OfflineSubmitQueue

    @Environment(\.scenePhase) private var scenePhase
    @State private var isAppUnlocked = true

    var body: some View {
        ZStack {
            Group {
                if !auth.isSessionReady {
                    SessionCheckingView()
                } else if auth.isLoggedIn {
                    if needsBiometricLock {
                        AppLockView {
                            isAppUnlocked = true
                        }
                    } else {
                        MainShellView(auth: auth)
                    }
                } else {
                    LoginView(auth: auth)
                }
            }
            .task(id: auth.token) {
                PushRegistration.shared.bindAuthToken(auth.token)
                if let token = auth.token {
                    _ = await offlineQueue.flush(authToken: token)
                }
            }
            .onChange(of: network.isOnline) { _, online in
                guard online, let token = auth.token else { return }
                Task { _ = await offlineQueue.flush(authToken: token) }
            }
            .onChange(of: scenePhase) { _, phase in
                if phase == .background, auth.isLoggedIn, BiometricPreferences.isEnabled {
                    isAppUnlocked = false
                }
            }
        }
        .task { await auth.bootstrap() }
        .animation(.easeInOut(duration: 0.2), value: auth.isSessionReady)
        .animation(.easeInOut(duration: 0.2), value: auth.isLoggedIn)
        .environment(\.layoutDirection, language.language.layoutDirection)
        .alert(
            language.t(.sessionExpiredTitle),
            isPresented: Binding(
                get: { auth.sessionExpiredMessage != nil },
                set: { if !$0 { auth.clearSessionExpiredMessage() } }
            )
        ) {
            Button(language.t(.ok)) { auth.clearSessionExpiredMessage() }
        } message: {
            Text(auth.sessionExpiredMessage ?? language.t(.sessionExpiredMessage))
        }
    }

    private var needsBiometricLock: Bool {
        auth.isLoggedIn && BiometricPreferences.isEnabled && BiometricLockManager.canUseBiometrics && !isAppUnlocked
    }
}

private struct SessionCheckingView: View {
    var body: some View {
        ZStack {
            Color(.systemBackground)
                .ignoresSafeArea()
            ProgressView()
        }
    }
}

#Preview {
    RootView()
        .environmentObject(LanguageManager.shared)
        .environmentObject(NetworkMonitor.shared)
        .environmentObject(OfflineSubmitQueue.shared)
}
