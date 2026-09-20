import Foundation

struct FormDraft: Codable {
    var textValues: [String: String] = [:]
    var boolValues: [String: Bool] = [:]
    var checklistValues: [String: [String]] = [:]
    var savedAt: Date = Date()
}

enum FormDraftStore {
    private static let prefix = "form_draft_"

    static func key(formId: Int?) -> String? {
        guard let formId else { return nil }
        return "\(prefix)form_\(formId)"
    }

    static func key(relatedAccessToken: String?) -> String? {
        guard let relatedAccessToken, !relatedAccessToken.isEmpty else { return nil }
        return "\(prefix)related_\(relatedAccessToken)"
    }

    static func load(storageKey: String?) -> FormDraft? {
        guard let storageKey,
              let data = UserDefaults.standard.data(forKey: storageKey) else { return nil }
        return try? JSONDecoder().decode(FormDraft.self, from: data)
    }

    static func save(
        storageKey: String?,
        textValues: [String: String],
        boolValues: [String: Bool],
        checklistValues: [String: Set<String>]
    ) {
        guard let storageKey else { return }
        let draft = FormDraft(
            textValues: textValues,
            boolValues: boolValues,
            checklistValues: checklistValues.mapValues { Array($0).sorted() }
        )
        guard let data = try? JSONEncoder().encode(draft) else { return }
        UserDefaults.standard.set(data, forKey: storageKey)
    }

    static func clear(storageKey: String?) {
        guard let storageKey else { return }
        UserDefaults.standard.removeObject(forKey: storageKey)
    }
}
