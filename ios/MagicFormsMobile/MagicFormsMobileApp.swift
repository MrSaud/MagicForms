import SwiftUI

@main
struct MagicFormsMobileApp: App {
    @UIApplicationDelegateAdaptor(MobileAppDelegate.self) private var appDelegate
    @StateObject private var language = LanguageManager.shared
    @StateObject private var network = NetworkMonitor.shared
    @StateObject private var offlineQueue = OfflineSubmitQueue.shared

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(language)
                .environmentObject(network)
                .environmentObject(offlineQueue)
                .environment(\.layoutDirection, language.language.layoutDirection)
        }
    }
}
