import Foundation
import UserNotifications
import UIKit

@MainActor
final class PushRegistration: ObservableObject {
    static let shared = PushRegistration()

    @Published private(set) var deviceToken: String?

    private var bearerToken: String?

    private init() {}

    func bindAuthToken(_ token: String?) {
        bearerToken = token
        if token != nil, let deviceToken {
            Task { await uploadToken(deviceToken) }
        }
    }

    func requestPermissionAndRegister() async {
        let center = UNUserNotificationCenter.current()
        do {
            let granted = try await center.requestAuthorization(options: [.alert, .badge, .sound])
            guard granted else { return }
            await MainActor.run {
                UIApplication.shared.registerForRemoteNotifications()
            }
        } catch {
            return
        }
    }

    func handleDeviceToken(_ tokenData: Data) async {
        let token = tokenData.map { String(format: "%02.2hhx", $0) }.joined()
        deviceToken = token
        await uploadToken(token)
    }

    private func uploadToken(_ pushToken: String) async {
        guard let bearerToken, !pushToken.isEmpty else { return }
        await DeviceAPI.registerPushToken(bearerToken: bearerToken, pushToken: pushToken)
    }

    func unregister() async {
        guard let bearerToken else { return }
        await DeviceAPI.unregisterPushToken(bearerToken: bearerToken, pushToken: deviceToken)
        deviceToken = nil
    }
}

final class MobileAppDelegate: NSObject, UIApplicationDelegate {
    func application(
        _ application: UIApplication,
        didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data
    ) {
        Task { @MainActor in
            await PushRegistration.shared.handleDeviceToken(deviceToken)
        }
    }

    func application(
        _ application: UIApplication,
        didFailToRegisterForRemoteNotificationsWithError error: Error
    ) {
        #if DEBUG
        print("APNs registration failed:", error.localizedDescription)
        #endif
    }
}
