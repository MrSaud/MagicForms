import Foundation

struct SignaturesListResponse: Decodable {
    let ok: Bool
    let limit: Int
    let count: Int
    let signatures: [UserSignatureItem]
}

struct UserSignatureItem: Decodable, Identifiable, Hashable {
    let id: Int
    let label: String
    let imageUrl: String
    let isPrimary: Bool
    let sortOrder: Int
    let createdAt: String
    let createdAtLabel: String

    enum CodingKeys: String, CodingKey {
        case id, label
        case imageUrl = "image_url"
        case isPrimary = "is_primary"
        case sortOrder = "sort_order"
        case createdAt = "created_at"
        case createdAtLabel = "created_at_label"
    }
}

struct SignatureMutationResponse: Decodable {
    let ok: Bool
    let message: String?
    let signature: UserSignatureItem?
}
