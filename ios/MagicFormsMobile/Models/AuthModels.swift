import Foundation

struct APIUser: Codable, Identifiable, Equatable {
    let id: Int
    let username: String
    let email: String
    let firstName: String
    let lastName: String
    let fullName: String
    let isStaff: Bool
    let isSuperuser: Bool

    enum CodingKeys: String, CodingKey {
        case id, username, email
        case firstName = "first_name"
        case lastName = "last_name"
        case fullName = "full_name"
        case isStaff = "is_staff"
        case isSuperuser = "is_superuser"
    }

    var displayName: String {
        if !fullName.isEmpty { return fullName }
        if !firstName.isEmpty || !lastName.isEmpty {
            return [firstName, lastName].filter { !$0.isEmpty }.joined(separator: " ")
        }
        return username
    }
}

struct APIEntity: Codable, Identifiable, Equatable, Hashable {
    let id: Int?
    let slug: String
    let name: String
    let logoUrl: String? = nil

    enum CodingKeys: String, CodingKey {
        case id, slug, name
        case logoUrl = "logo_url"
    }
}

struct LoginRequest: Encodable {
    let username: String
    let password: String
    let entitySlug: String?

    enum CodingKeys: String, CodingKey {
        case username, password
        case entitySlug = "entity_slug"
    }
}

struct LoginResponse: Decodable {
    let ok: Bool
    let token: String?
    let expiresAt: String?
    let tokenType: String?
    let loginVia: String?
    let user: APIUser?
    let entities: [APIEntity]?

    enum CodingKeys: String, CodingKey {
        case ok, token, user, entities
        case expiresAt = "expires_at"
        case tokenType = "token_type"
        case loginVia = "login_via"
    }
}

struct MeResponse: Decodable {
    let ok: Bool
    let user: APIUser?
    let entities: [APIEntity]?
}

struct DirectoryEntitiesResponse: Decodable {
    let ok: Bool
    let entities: [APIEntity]?
}

struct APIErrorBody: Decodable {
    let ok: Bool?
    let error: String?
    let message: String?
    let entities: [APIEntity]?
}

struct APIError: LocalizedError {
    let code: String
    let message: String
    let entities: [APIEntity]?

    var errorDescription: String? { message }
}
