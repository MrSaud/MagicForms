import Foundation

struct PendingFormSubmit: Codable, Identifiable {
    let id: String
    let kind: String
    let formId: Int?
    let relatedAccessToken: String?
    let textFields: [String: String]
    let checkboxFields: [String: Bool]
    let checklistFields: [String: [String]]
    let createdAt: Date
}

@MainActor
final class OfflineSubmitQueue: ObservableObject {
    static let shared = OfflineSubmitQueue()

    @Published private(set) var pendingCount = 0

    private let storageKey = "offline_form_submit_queue"

    private init() {
        pendingCount = load().count
    }

    func enqueue(_ item: PendingFormSubmit) {
        var items = load()
        items.append(item)
        save(items)
        pendingCount = items.count
    }

    func flush(authToken: String) async -> Int {
        let items = load()
        guard !items.isEmpty else { return 0 }
        var synced = 0
        var remaining: [PendingFormSubmit] = []

        for item in items {
            do {
                let files: [String: (data: Data, fileName: String, mimeType: String)] = [:]
                if item.kind == "related", let token = item.relatedAccessToken {
                    _ = try await FormSubmitAPI.submitRelated(
                        token: authToken,
                        accessToken: token,
                        textFields: item.textFields,
                        checkboxFields: item.checkboxFields,
                        checklistFields: item.checklistFields,
                        files: files
                    )
                } else if let formId = item.formId {
                    _ = try await FormSubmitAPI.submit(
                        token: authToken,
                        formId: formId,
                        textFields: item.textFields,
                        checkboxFields: item.checkboxFields,
                        checklistFields: item.checklistFields,
                        files: files
                    )
                } else {
                    remaining.append(item)
                    continue
                }
                synced += 1
            } catch {
                remaining.append(item)
            }
        }
        save(remaining)
        pendingCount = remaining.count
        return synced
    }

    private func load() -> [PendingFormSubmit] {
        guard let data = UserDefaults.standard.data(forKey: storageKey) else { return [] }
        return (try? JSONDecoder().decode([PendingFormSubmit].self, from: data)) ?? []
    }

    private func save(_ items: [PendingFormSubmit]) {
        guard let data = try? JSONEncoder().encode(items) else { return }
        UserDefaults.standard.set(data, forKey: storageKey)
    }
}
