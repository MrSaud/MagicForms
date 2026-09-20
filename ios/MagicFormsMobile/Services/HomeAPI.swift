import Foundation

enum HomeAPI {
    private static let decoder = JSONDecoder()

    static func fetchSummary(token: String) async throws -> HomeSummary {
        let url = APIConfig.url(path: "/api/v1/home/summary/")
        let data = try await AuthAPI.getData(url: url, token: token)
        let response = try decoder.decode(HomeSummaryResponse.self, from: data)
        return response.summary
    }

    static func fetchPublishedForms(token: String) async throws -> [PublishedFormItem] {
        let url = APIConfig.url(path: "/api/v1/forms/published/")
        let data = try await AuthAPI.getData(url: url, token: token)
        let response = try decoder.decode(PublishedFormsResponse.self, from: data)
        return response.forms
    }

    static func fetchFormIntro(token: String, formId: Int) async throws -> FormIntroPayload {
        let url = APIConfig.url(path: "/api/v1/forms/\(formId)/intro/")
        let data = try await AuthAPI.getData(url: url, token: token)
        let response = try decoder.decode(FormIntroResponse.self, from: data)
        if response.ok { return response.intro }
        throw try AuthAPI.decodeError(from: data)
    }

    static func fetchInbox(token: String, limit: Int = 50, offset: Int = 0) async throws -> InboxListResponse {
        var components = URLComponents(url: APIConfig.url(path: "/api/v1/inbox/"), resolvingAgainstBaseURL: false)!
        components.queryItems = [
            URLQueryItem(name: "limit", value: String(limit)),
            URLQueryItem(name: "offset", value: String(offset)),
        ]
        let data = try await AuthAPI.getData(url: components.url!, token: token)
        return try decoder.decode(InboxListResponse.self, from: data)
    }

    static func fetchInboxDetail(token: String, submissionId: Int) async throws -> InboxDetailResponse {
        let url = APIConfig.url(path: "/api/v1/inbox/\(submissionId)/")
        let data = try await AuthAPI.getData(url: url, token: token)
        let response = try decoder.decode(InboxDetailResponse.self, from: data)
        if response.ok { return response }
        throw try AuthAPI.decodeError(from: data)
    }

    static func fetchPendingRelated(token: String) async throws -> PendingRelatedResponse {
        let url = APIConfig.url(path: "/api/v1/related/pending/")
        let data = try await AuthAPI.getData(url: url, token: token)
        let response = try decoder.decode(PendingRelatedResponse.self, from: data)
        if response.ok { return response }
        throw try AuthAPI.decodeError(from: data)
    }

    static func postThreadMessage(token: String, submissionId: Int, body: String) async throws -> InboxDetailResponse {
        let url = APIConfig.url(path: "/api/v1/inbox/\(submissionId)/thread/post/")
        let payload = try JSONEncoder().encode(ThreadPostRequest(body: body))
        let data = try await AuthAPI.postData(url: url, body: payload, token: token)
        let response = try decoder.decode(InboxDetailResponse.self, from: data)
        if response.ok { return response }
        throw try AuthAPI.decodeError(from: data)
    }

    static func documentURL(apiPath: String, inline: Bool = false) -> URL {
        var url = APIConfig.url(path: apiPath)
        if inline {
            var components = URLComponents(url: url, resolvingAgainstBaseURL: false)!
            components.queryItems = [URLQueryItem(name: "inline", value: "1")]
            url = components.url ?? url
        }
        return url
    }

    static func performWorkflow(
        token: String,
        submissionId: Int,
        decision: String,
        comment: String?,
        workflowActionAnchor: Int?
    ) async throws -> InboxDetailResponse {
        let url = APIConfig.url(path: "/api/v1/inbox/\(submissionId)/workflow/")
        let body = WorkflowActionRequest(
            decision: decision,
            comment: comment,
            workflowActionAnchor: workflowActionAnchor
        )
        let data = try JSONEncoder().encode(body)
        let responseData = try await AuthAPI.postData(url: url, body: data, token: token)
        let response = try decoder.decode(InboxDetailResponse.self, from: responseData)
        if response.ok { return response }
        throw try AuthAPI.decodeError(from: responseData)
    }
}
