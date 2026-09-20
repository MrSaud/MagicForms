import Foundation

enum SignatureAPI {
    private static let decoder = JSONDecoder()

    static func fetchSignatures(token: String) async throws -> SignaturesListResponse {
        let url = APIConfig.url(path: "/api/v1/signatures/")
        let data = try await AuthAPI.getData(url: url, token: token)
        let response = try decoder.decode(SignaturesListResponse.self, from: data)
        if response.ok { return response }
        throw try AuthAPI.decodeError(from: data)
    }

    static func uploadSignature(
        token: String,
        pngData: Data,
        label: String,
        replaceSignatureId: Int?
    ) async throws -> SignatureMutationResponse {
        let path: String
        if let replaceSignatureId {
            path = "/api/v1/signatures/\(replaceSignatureId)/image/"
        } else {
            path = "/api/v1/signatures/"
        }
        let url = APIConfig.url(path: path)
        let data = try await AuthAPI.uploadMultipart(
            url: url,
            token: token,
            fields: label.isEmpty ? [:] : ["label": label],
            fileField: "image",
            fileData: pngData,
            fileName: "signature.png",
            mimeType: "image/png"
        )
        let response = try decoder.decode(SignatureMutationResponse.self, from: data)
        if response.ok { return response }
        throw try AuthAPI.decodeError(from: data)
    }

    static func setPrimary(token: String, signatureId: Int) async throws {
        let url = APIConfig.url(path: "/api/v1/signatures/\(signatureId)/primary/")
        let data = try await AuthAPI.postData(url: url, body: Data("{}".utf8), token: token)
        if let body = try? decoder.decode(SignatureMutationResponse.self, from: data), body.ok {
            return
        }
        throw try AuthAPI.decodeError(from: data)
    }

    static func deleteSignature(token: String, signatureId: Int) async throws {
        let url = APIConfig.url(path: "/api/v1/signatures/\(signatureId)/")
        let data = try await AuthAPI.deleteData(url: url, token: token)
        if let body = try? decoder.decode(SignatureMutationResponse.self, from: data), body.ok {
            return
        }
        throw try AuthAPI.decodeError(from: data)
    }
}
