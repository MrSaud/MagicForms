import SwiftUI

struct MySignaturesView: View {
    @ObservedObject var auth: AuthViewModel

    @StateObject private var padModel = SignaturePadModel()
    @State private var signatures: [UserSignatureItem] = []
    @State private var limit = 200
    @State private var label = ""
    @State private var editingId: Int?
    @State private var padSize: CGSize = CGSize(width: 400, height: 180)
    @State private var isLoading = true
    @State private var isSaving = false
    @State private var errorMessage: String?
    @State private var successMessage: String?

    var body: some View {
        List {
            if let successMessage {
                Section {
                    Text(successMessage)
                        .foregroundStyle(.green)
                }
            }
            if let errorMessage {
                Section {
                    Text(errorMessage)
                        .foregroundStyle(.red)
                }
            }

            Section {
                Text(editingId == nil ? "Draw a new signature" : "Redraw selected signature")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                SignaturePadView(model: padModel)
                    .onPadSizeChange { padSize = $0 }

                HStack {
                    Button("Undo") {
                        padModel.undo()
                    }
                    .disabled(!padModel.canUndo || isSaving)

                    Button("Clear") {
                        padModel.clear()
                    }
                    .disabled(padModel.isEmpty || isSaving)

                    Spacer()

                    Button(editingId == nil ? "Add new" : "Save") {
                        Task { await saveSignature() }
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(padModel.isEmpty || isSaving)
                }

                TextField("Label (optional)", text: $label)
                    .textFieldStyle(.roundedBorder)

                if editingId != nil {
                    Button("Cancel edit") {
                        editingId = nil
                        label = ""
                        padModel.clear()
                    }
                    .foregroundStyle(.secondary)
                }
            }

            Section("Your signatures") {
                if signatures.isEmpty && !isLoading {
                    Text("No signatures yet. Draw one above and tap Add new.")
                        .foregroundStyle(.secondary)
                }
                ForEach(signatures) { sig in
                    signatureRow(sig)
                }
            }
        }
        .listStyle(.insetGrouped)
        .navigationTitle("My signatures")
        .overlay {
            if isLoading {
                ProgressView()
            }
        }
        .task {
            await loadSignatures()
        }
        .refreshable {
            await loadSignatures()
        }
    }

    @ViewBuilder
    private func signatureRow(_ sig: UserSignatureItem) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .top, spacing: 12) {
                if let url = URL(string: sig.imageUrl) {
                    AsyncImage(url: url) { phase in
                        switch phase {
                        case .success(let image):
                            image
                                .resizable()
                                .scaledToFit()
                        default:
                            Rectangle()
                                .fill(Color.secondary.opacity(0.15))
                        }
                    }
                    .frame(width: 100, height: 56)
                    .clipShape(RoundedRectangle(cornerRadius: 6))
                }
                VStack(alignment: .leading, spacing: 4) {
                    HStack {
                        Text(sig.label.isEmpty ? "(no label)" : sig.label)
                            .font(.subheadline.weight(.medium))
                        if sig.isPrimary {
                            Text("Primary")
                                .font(.caption2.weight(.semibold))
                                .padding(.horizontal, 6)
                                .padding(.vertical, 2)
                                .background(Color.accentColor.opacity(0.15))
                                .clipShape(Capsule())
                        }
                    }
                    Text(sig.createdAtLabel)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }

            HStack(spacing: 8) {
                Button("Edit") {
                    editingId = sig.id
                    label = sig.label
                    padModel.clear()
                }
                .disabled(isSaving)

                if !sig.isPrimary {
                    Button("Set primary") {
                        Task { await setPrimary(sig.id) }
                    }
                    .disabled(isSaving)
                }

                Button("Remove", role: .destructive) {
                    Task { await removeSignature(sig.id) }
                }
                .disabled(isSaving)
            }
            .font(.caption)
        }
        .padding(.vertical, 4)
    }

    private func loadSignatures() async {
        guard let token = auth.token else { return }
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            let response = try await SignatureAPI.fetchSignatures(token: token)
            signatures = response.signatures
            limit = response.limit
        } catch let apiError as APIError {
            errorMessage = apiError.message
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func saveSignature() async {
        guard let token = auth.token else { return }
        let exportSize = padSize == .zero ? CGSize(width: 400, height: 180) : padSize
        guard let png = padModel.exportPNG(size: exportSize) else {
            errorMessage = "Could not export drawing."
            return
        }
        if editingId == nil && signatures.count >= limit {
            errorMessage = "You reached the maximum number of signatures (\(limit))."
            return
        }

        isSaving = true
        errorMessage = nil
        successMessage = nil
        defer { isSaving = false }

        do {
            _ = try await SignatureAPI.uploadSignature(
                token: token,
                pngData: png,
                label: label.trimmingCharacters(in: .whitespacesAndNewlines),
                replaceSignatureId: editingId
            )
            successMessage = editingId == nil ? "Signature added." : "Signature updated."
            editingId = nil
            label = ""
            padModel.clear()
            await loadSignatures()
        } catch let apiError as APIError {
            errorMessage = apiError.message
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func setPrimary(_ id: Int) async {
        guard let token = auth.token else { return }
        isSaving = true
        defer { isSaving = false }
        do {
            try await SignatureAPI.setPrimary(token: token, signatureId: id)
            successMessage = "Primary signature updated."
            await loadSignatures()
        } catch let apiError as APIError {
            errorMessage = apiError.message
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func removeSignature(_ id: Int) async {
        guard let token = auth.token else { return }
        isSaving = true
        defer { isSaving = false }
        do {
            try await SignatureAPI.deleteSignature(token: token, signatureId: id)
            if editingId == id {
                editingId = nil
                label = ""
                padModel.clear()
            }
            successMessage = "Signature removed."
            await loadSignatures()
        } catch let apiError as APIError {
            errorMessage = apiError.message
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
