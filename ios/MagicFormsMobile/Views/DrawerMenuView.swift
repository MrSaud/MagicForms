import SwiftUI

struct DrawerMenuView: View {
    @ObservedObject var auth: AuthViewModel
    @EnvironmentObject private var language: LanguageManager
    var onOpenInbox: () -> Void = {}
    var onOpenSignatures: () -> Void = {}
    var onOpenSearch: () -> Void = {}
    var onOpenPending: () -> Void = {}
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            List {
                if let user = auth.user {
                    Section {
                        Text(user.displayName)
                            .font(.headline)
                        Text(user.username)
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                    }
                }

                Section {
                    LanguagePickerView {
                        Task { await auth.loadHomeData() }
                    }
                    if BiometricLockManager.canUseBiometrics {
                        Toggle(isOn: Binding(
                            get: { BiometricPreferences.isEnabled },
                            set: { BiometricPreferences.isEnabled = $0 }
                        )) {
                            Label(language.t(.biometricUnlock), systemImage: "faceid")
                        }
                    }
                }

                if let summary = auth.homeSummary {
                    Section(language.t(.studio)) {
                        if summary.applicantPendingCount > 0 {
                            Button {
                                dismiss()
                                onOpenPending()
                            } label: {
                                Label(
                                    "\(language.t(.formsToComplete)) (\(summary.applicantPendingCount))",
                                    systemImage: "star.fill"
                                )
                            }
                        }
                        Button {
                            dismiss()
                            onOpenSearch()
                        } label: {
                            Label(language.t(.search), systemImage: "magnifyingglass")
                        }
                        Button {
                            dismiss()
                            onOpenSignatures()
                        } label: {
                            Label(language.t(.mySignatures), systemImage: "signature")
                        }
                        if auth.homeSummary?.isStaff == true || auth.homeSummary?.isSuperuser == true,
                           let helpUrl = auth.homeSummary?.menuLinks.help,
                           let dest = URL(string: helpUrl) {
                            Link(destination: dest) {
                                Label(language.t(.help), systemImage: "questionmark.circle")
                            }
                        }
                    }
                }

                Section {
                    Button {
                        dismiss()
                        Task { await auth.loadHomeData() }
                    } label: {
                        Label(language.t(.refresh), systemImage: "arrow.clockwise")
                    }
                    Button(role: .destructive) {
                        dismiss()
                        Task { await auth.logout() }
                    } label: {
                        Label(language.t(.signOut), systemImage: "rectangle.portrait.and.arrow.right")
                    }
                }
            }
            .navigationTitle(language.t(.menu))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button(language.t(.done)) { dismiss() }
                }
            }
        }
        .environment(\.layoutDirection, language.language.layoutDirection)
    }
}
