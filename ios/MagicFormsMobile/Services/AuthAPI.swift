import Foundation

extension Notification.Name {
    static let mobileSessionExpired = Notification.Name("MobileSessionExpired")
}

enum AuthAPI {
    private static let decoder: JSONDecoder = {
        let d = JSONDecoder()
        return d
    }()

    private static let encoder: JSONEncoder = {
        let e = JSONEncoder()
        return e
    }()

    static func getData(url: URL, token: String?) async throws -> Data {
        try await get(url: url, token: token)
    }

    static func postData(url: URL, body: Data, token: String?) async throws -> Data {
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        applyCommonHeaders(&request, token: token)
        request.httpBody = body
        return try await perform(request)
    }

    static func deleteData(url: URL, token: String?) async throws -> Data {
        var request = URLRequest(url: url)
        request.httpMethod = "DELETE"
        applyCommonHeaders(&request, token: token)
        return try await perform(request)
    }

    static func postMultipartForm(
        url: URL,
        token: String?,
        textFields: [String: String],
        checkboxFields: [String: Bool] = [:],
        checklistFields: [String: [String]] = [:],
        files: [String: (data: Data, fileName: String, mimeType: String)] = [:]
    ) async throws -> Data {
        let boundary = "Boundary-\(UUID().uuidString)"
        var body = Data()

        func appendField(name: String, value: String) {
            body.append("--\(boundary)\r\n".data(using: .utf8)!)
            body.append("Content-Disposition: form-data; name=\"\(name)\"\r\n\r\n".data(using: .utf8)!)
            body.append("\(value)\r\n".data(using: .utf8)!)
        }

        for (key, value) in textFields {
            appendField(name: key, value: value)
        }
        for (key, checked) in checkboxFields where checked {
            appendField(name: key, value: "on")
        }
        for (key, values) in checklistFields {
            for value in values {
                appendField(name: key, value: value)
            }
        }
        for (fieldName, file) in files {
            body.append("--\(boundary)\r\n".data(using: .utf8)!)
            body.append(
                "Content-Disposition: form-data; name=\"\(fieldName)\"; filename=\"\(file.fileName)\"\r\n"
                    .data(using: .utf8)!
            )
            body.append("Content-Type: \(file.mimeType)\r\n\r\n".data(using: .utf8)!)
            body.append(file.data)
            body.append("\r\n".data(using: .utf8)!)
        }
        body.append("--\(boundary)--\r\n".data(using: .utf8)!)

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        applyCommonHeaders(&request, token: token)
        request.httpBody = body
        return try await perform(request)
    }

    static func uploadMultipart(
        url: URL,
        token: String?,
        fields: [String: String],
        fileField: String,
        fileData: Data,
        fileName: String,
        mimeType: String
    ) async throws -> Data {
        let boundary = "Boundary-\(UUID().uuidString)"
        var body = Data()
        for (key, value) in fields {
            body.append("--\(boundary)\r\n".data(using: .utf8)!)
            body.append("Content-Disposition: form-data; name=\"\(key)\"\r\n\r\n".data(using: .utf8)!)
            body.append("\(value)\r\n".data(using: .utf8)!)
        }
        body.append("--\(boundary)\r\n".data(using: .utf8)!)
        body.append(
            "Content-Disposition: form-data; name=\"\(fileField)\"; filename=\"\(fileName)\"\r\n"
                .data(using: .utf8)!
        )
        body.append("Content-Type: \(mimeType)\r\n\r\n".data(using: .utf8)!)
        body.append(fileData)
        body.append("\r\n".data(using: .utf8)!)
        body.append("--\(boundary)--\r\n".data(using: .utf8)!)

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        applyCommonHeaders(&request, token: token)
        request.httpBody = body
        return try await perform(request)
    }

    static func fetchDirectoryEntities() async throws -> [APIEntity] {
        let url = APIConfig.url(path: "/api/v1/auth/directory-entities/")
        let data = try await get(url: url, token: nil)
        let response = try decoder.decode(DirectoryEntitiesResponse.self, from: data)
        return response.entities ?? []
    }

    static func login(username: String, password: String, entitySlug: String?) async throws -> LoginResponse {
        let url = APIConfig.url(path: "/api/v1/auth/login/")
        let body = LoginRequest(
            username: username,
            password: password,
            entitySlug: entitySlug?.isEmpty == true ? nil : entitySlug
        )
        let data = try await post(url: url, body: body, token: nil)
        let response = try decoder.decode(LoginResponse.self, from: data)
        if response.ok, response.token != nil {
            return response
        }
        throw try parseError(data: data)
    }

    static func me(token: String) async throws -> MeResponse {
        let url = APIConfig.url(path: "/api/v1/auth/me/")
        let data = try await get(url: url, token: token)
        let response = try decoder.decode(MeResponse.self, from: data)
        if response.ok { return response }
        throw try parseError(data: data)
    }

    static func logout(token: String) async throws {
        let url = APIConfig.url(path: "/api/v1/auth/logout/")
        _ = try await post(url: url, body: EmptyBody(), token: token)
    }

    // MARK: - HTTP

    private struct EmptyBody: Encodable {}

    private static func get(url: URL, token: String?) async throws -> Data {
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        applyCommonHeaders(&request, token: token)
        return try await perform(request)
    }

    private static func post<T: Encodable>(url: URL, body: T, token: String?) async throws -> Data {
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        applyCommonHeaders(&request, token: token)
        request.httpBody = try encoder.encode(body)
        return try await perform(request)
    }

    private static func applyCommonHeaders(_ request: inout URLRequest, token: String?) {
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue(AppLanguage.currentAcceptLanguage, forHTTPHeaderField: "Accept-Language")
        if let token { request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization") }
    }

    private static func perform(_ request: URLRequest) async throws -> Data {
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse else {
            throw APIError(code: "network", message: "Invalid response.", entities: nil)
        }
        if (200 ..< 300).contains(http.statusCode) {
            return data
        }
        if http.statusCode == 401 {
            NotificationCenter.default.post(name: .mobileSessionExpired, object: nil)
        }
        throw try parseError(data: data, status: http.statusCode)
    }

    static func decodeError(from data: Data, status: Int? = nil) throws -> APIError {
        try parseError(data: data, status: status)
    }

    private static func parseError(data: Data, status: Int? = nil) throws -> APIError {
        if let body = try? decoder.decode(APIErrorBody.self, from: data) {
            let code = body.error ?? "error"
            let message = body.message ?? "Request failed."
            return APIError(code: code, message: message, entities: body.entities)
        }
        if let status {
            return APIError(code: "http_\(status)", message: "HTTP \(status)", entities: nil)
        }
        return APIError(code: "error", message: "Request failed.", entities: nil)
    }
}
