import Foundation

/// API base URL for the MagicForms backend (main domain only — no entity slug in paths).
///
/// Set once at build time via the `API_BASE_URL` key in Info.plist (see Xcode target build settings).
/// End users never choose or enter a server URL.
enum APIConfig {
    static var baseURL: URL {
        if let raw = Bundle.main.object(forInfoDictionaryKey: "API_BASE_URL") as? String,
           !raw.isEmpty,
           let url = URL(string: raw) {
            return url
        }
        #if DEBUG
        #if targetEnvironment(simulator)
        return URL(string: "http://127.0.0.1:8000")!
        #else
        // Physical device in Debug: set API_BASE_URL in the target’s build settings (e.g. your Mac’s LAN IP).
        return URL(string: "http://127.0.0.1:8000")!
        #endif
        #else
        fatalError("Set API_BASE_URL in the MagicFormsMobile target build settings for Release builds.")
        #endif
    }

    static func url(path: String) -> URL {
        var base = baseURL.absoluteString
        if base.hasSuffix("/") { base.removeLast() }
        let suffix = path.hasPrefix("/") ? path : "/\(path)"
        guard let url = URL(string: base + suffix) else {
            fatalError("Invalid API URL: \(base)\(suffix)")
        }
        return url
    }
}
