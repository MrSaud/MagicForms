import SwiftUI

struct AppLockView: View {
    @EnvironmentObject private var language: LanguageManager
    let onUnlocked: () -> Void

    @State private var errorMessage: String?

    var body: some View {
        VStack(spacing: 20) {
            Image(systemName: "lock.fill")
                .font(.system(size: 44))
                .foregroundStyle(.secondary)
            Text(language.t(.unlockApp))
                .font(.title2.weight(.semibold))
            Text(language.t(.unlockAppDesc))
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal)
            if let errorMessage {
                Text(errorMessage)
                    .font(.caption)
                    .foregroundStyle(.red)
            }
            Button(language.t(.unlockWithBiometrics)) {
                Task { await unlock() }
            }
            .buttonStyle(.borderedProminent)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color(.systemBackground))
    }

    private func unlock() async {
        errorMessage = nil
        let ok = await BiometricLockManager.authenticate(reason: language.t(.unlockApp))
        if ok {
            onUnlocked()
        } else {
            errorMessage = language.t(.biometricFailed)
        }
    }
}
