import Foundation

enum SearchAPI {
    private static let decoder = JSONDecoder()

    static func fetchSubmissions(
        token: String,
        query: String = "",
        relation: String = "any",
        workflowState: String? = nil,
        formId: Int? = nil,
        limit: Int = 50,
        offset: Int = 0
    ) async throws -> SubmissionSearchResponse {
        var components = URLComponents(url: APIConfig.url(path: "/api/v1/submissions/search/"), resolvingAgainstBaseURL: false)!
        var queryItems = [
            URLQueryItem(name: "limit", value: String(limit)),
            URLQueryItem(name: "offset", value: String(offset)),
            URLQueryItem(name: "relation", value: relation),
        ]
        let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)
        if !trimmed.isEmpty {
            queryItems.append(URLQueryItem(name: "q", value: trimmed))
        }
        if let workflowState, !workflowState.isEmpty {
            queryItems.append(URLQueryItem(name: "workflow_state", value: workflowState))
        }
        if let formId {
            queryItems.append(URLQueryItem(name: "form", value: String(formId)))
        }
        components.queryItems = queryItems

        let data = try await AuthAPI.getData(url: components.url!, token: token)
        let response = try decoder.decode(SubmissionSearchResponse.self, from: data)
        if response.ok { return response }
        throw try AuthAPI.decodeError(from: data)
    }
}
