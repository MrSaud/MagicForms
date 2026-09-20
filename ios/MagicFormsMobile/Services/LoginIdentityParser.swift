import Foundation

/// Parses ``entity-slug-username`` (e.g. ``mosa-kuwait-jdoe``) into API fields.
enum LoginIdentityParser {
    struct Parsed {
        let entitySlug: String?
        let username: String
    }

    /// Longest matching directory slug prefix wins: ``{slug}-{username}``.
    static func parse(_ raw: String, knownEntitySlugs: [String]) -> Parsed {
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else {
            return Parsed(entitySlug: nil, username: "")
        }

        let slugs = knownEntitySlugs
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
            .sorted { $0.count > $1.count }

        let lower = trimmed.lowercased()
        for slug in slugs {
            let prefix = "\(slug)-"
            if lower.hasPrefix(prefix.lowercased()) {
                let username = String(trimmed.dropFirst(prefix.count))
                    .trimmingCharacters(in: .whitespacesAndNewlines)
                if !username.isEmpty {
                    return Parsed(entitySlug: slug, username: username)
                }
            }
        }

        return Parsed(entitySlug: nil, username: trimmed)
    }
}
