import Foundation
import UIKit

enum DeviceAPI {
    private struct RegisterBody: Encodable {
        let platform: String
        let token: String
        let deviceId: String

        enum CodingKeys: String, CodingKey {
            case platform
            case token
            case deviceId = "device_id"
        }
    }

    private struct UnregisterBody: Encodable {
        let token: String?
    }

    @MainActor
    static func registerPushToken(bearerToken: String, pushToken: String) async {
        let url = APIConfig.url(path: "/api/v1/devices/register/")
        let body = RegisterBody(
            platform: "ios",
            token: pushToken,
            deviceId: UIDevice.current.identifierForVendor?.uuidString ?? ""
        )
        guard let payload = try? JSONEncoder().encode(body) else { return }
        _ = try? await AuthAPI.postData(url: url, body: payload, token: bearerToken)
    }

    @MainActor
    static func unregisterPushToken(bearerToken: String, pushToken: String?) async {
        let url = APIConfig.url(path: "/api/v1/devices/unregister/")
        let body = UnregisterBody(token: pushToken)
        guard let payload = try? JSONEncoder().encode(body) else { return }
        _ = try? await AuthAPI.postData(url: url, body: payload, token: bearerToken)
    }
}
