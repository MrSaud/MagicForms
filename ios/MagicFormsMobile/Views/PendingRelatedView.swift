import SwiftUI

struct PendingRelatedView: View {
    @ObservedObject var auth: AuthViewModel
    @EnvironmentObject private var language: LanguageManager

    @State private var items: [PendingRelatedItem] = []
    @State private var isLoading = true
    @State private var errorMessage: String?

    var body: some View {
        Group {
            if isLoading && items.isEmpty {
                ProgressView()
            } else if let errorMessage, items.isEmpty {
                ContentUnavailableView(language.t(.couldNotLoadForm), systemImage: "exclamationmark.triangle", description: Text(errorMessage))
            } else if items.isEmpty {
                ContentUnavailableView(
                    language.t(.noPendingRelated),
                    systemImage: "doc.text",
                    description: Text(language.t(.formsToCompleteDesc))
                )
            } else {
                List(items) { item in
                    NavigationLink {
                        FormSubmitView(
                            auth: auth,
                            relatedAccessToken: item.accessToken,
                            formTitle: item.childForm.title
                        )
                    } label: {
                        VStack(alignment: .leading, spacing: 4) {
                            Text(item.childForm.title)
                                .font(.body.weight(.semibold))
                            Text("\(language.t(.mainForm)): \(item.parentSubmission.formTitle)")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            Text(item.childForm.entityName)
                                .font(.caption2)
                                .foregroundStyle(.tertiary)
                        }
                        .padding(.vertical, 4)
                    }
                }
                .listStyle(.plain)
                .refreshable { await load() }
            }
        }
        .navigationTitle(language.t(.formsToComplete))
        .navigationBarTitleDisplayMode(.inline)
        .task { await load() }
    }

    private func load() async {
        guard let token = auth.token else { return }
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            let response = try await HomeAPI.fetchPendingRelated(token: token)
            items = response.items
        } catch let err as APIError {
            errorMessage = err.message
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
