import Foundation

enum FormSubmitAPI {
    private static let decoder = JSONDecoder()

    static func fetchSchema(token: String, formId: Int) async throws -> FormSchemaResponse {
        let url = APIConfig.url(path: "/api/v1/forms/\(formId)/schema/")
        let data = try await AuthAPI.getData(url: url, token: token)
        let response = try decoder.decode(FormSchemaResponse.self, from: data)
        if response.ok { return response }
        throw try AuthAPI.decodeError(from: data)
    }

    static func submit(
        token: String,
        formId: Int,
        textFields: [String: String],
        checkboxFields: [String: Bool],
        checklistFields: [String: [String]],
        files: [String: (data: Data, fileName: String, mimeType: String)]
    ) async throws -> FormSubmitResponse {
        let url = APIConfig.url(path: "/api/v1/forms/\(formId)/submit/")
        let data = try await AuthAPI.postMultipartForm(
            url: url,
            token: token,
            textFields: textFields,
            checkboxFields: checkboxFields,
            checklistFields: checklistFields,
            files: files
        )
        let response = try decoder.decode(FormSubmitResponse.self, from: data)
        if response.ok { return response }
        if let fieldErrors = response.fieldErrors, !fieldErrors.isEmpty {
            throw FormSubmitValidationError(
                message: response.message ?? "Please fix the highlighted fields.",
                fieldErrors: fieldErrors
            )
        }
        throw try AuthAPI.decodeError(from: data)
    }

    static func fetchRelatedSchema(token: String, accessToken: String) async throws -> FormSchemaResponse {
        let url = APIConfig.url(path: "/api/v1/related/\(accessToken)/schema/")
        let data = try await AuthAPI.getData(url: url, token: token)
        let response = try decoder.decode(FormSchemaResponse.self, from: data)
        if response.ok { return response }
        throw try AuthAPI.decodeError(from: data)
    }

    static func submitRelated(
        token: String,
        accessToken: String,
        textFields: [String: String],
        checkboxFields: [String: Bool],
        checklistFields: [String: [String]],
        files: [String: (data: Data, fileName: String, mimeType: String)]
    ) async throws -> FormSubmitResponse {
        let url = APIConfig.url(path: "/api/v1/related/\(accessToken)/submit/")
        let data = try await AuthAPI.postMultipartForm(
            url: url,
            token: token,
            textFields: textFields,
            checkboxFields: checkboxFields,
            checklistFields: checklistFields,
            files: files
        )
        let response = try decoder.decode(FormSubmitResponse.self, from: data)
        if response.ok { return response }
        if let fieldErrors = response.fieldErrors, !fieldErrors.isEmpty {
            throw FormSubmitValidationError(
                message: response.message ?? "Please fix the highlighted fields.",
                fieldErrors: fieldErrors
            )
        }
        throw try AuthAPI.decodeError(from: data)
    }
}

struct FormSubmitValidationError: LocalizedError {
    let message: String
    let fieldErrors: [String: [String]]
    var errorDescription: String? { message }
}
