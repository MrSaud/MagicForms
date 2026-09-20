import Foundation

enum BiometricPreferences {
    private static let enabledKey = "biometric_unlock_enabled"

    static var isEnabled: Bool {
        get { UserDefaults.standard.bool(forKey: enabledKey) }
        set { UserDefaults.standard.set(newValue, forKey: enabledKey) }
    }
}
