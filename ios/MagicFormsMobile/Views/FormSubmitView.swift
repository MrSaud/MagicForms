import SwiftUI
import UniformTypeIdentifiers

struct FormSubmitView: View {
    @ObservedObject var auth: AuthViewModel
    @EnvironmentObject private var language: LanguageManager
    @EnvironmentObject private var network: NetworkMonitor
    @EnvironmentObject private var offlineQueue: OfflineSubmitQueue
    var formId: Int?
    var relatedAccessToken: String?
    let formTitle: String

    @Environment(\.dismiss) private var dismiss

    @State private var schema: FormSchemaResponse?
    @State private var loadError: String?
    @State private var isLoading = true
    @State private var isSubmitting = false
    @State private var submitError: String?
    @State private var fieldErrors: [String: [String]] = [:]
    @State private var successSubmissionId: Int?

    @State private var textValues: [String: String] = [:]
    @State private var boolValues: [String: Bool] = [:]
    @State private var checklistValues: [String: Set<String>] = [:]
    @State private var fileSelections: [String: (data: Data, name: String)] = [:]
    @State private var draftSaveTask: Task<Void, Never>?

    private var draftStorageKey: String? {
        FormDraftStore.key(formId: formId) ?? FormDraftStore.key(relatedAccessToken: relatedAccessToken)
    }

    var body: some View {
        Group {
            if isLoading {
                ProgressView(language.t(.loadingForm))
            } else if let loadError {
                ContentUnavailableView(language.t(.couldNotLoadForm), systemImage: "exclamationmark.triangle", description: Text(loadError))
            } else if let schema {
                if schema.status != "open" {
                    ContentUnavailableView(
                        language.t(.notAvailable),
                        systemImage: "doc.text",
                        description: Text(schema.statusMessage.isEmpty ? language.t(.notAvailableDesc) : schema.statusMessage)
                    )
                } else if successSubmissionId != nil {
                    submitSuccessView(submissionId: successSubmissionId!)
                } else {
                    formContent(schema: schema)
                }
            }
        }
        .navigationTitle(formTitle)
        .navigationBarTitleDisplayMode(.inline)
        .task { await loadSchema() }
        .onChange(of: textValues) { _, _ in scheduleDraftSave() }
        .onChange(of: boolValues) { _, _ in scheduleDraftSave() }
        .onChange(of: checklistValues) { _, _ in scheduleDraftSave() }
        .onDisappear { draftSaveTask?.cancel() }
    }

    @ViewBuilder
    private func submitSuccessView(submissionId: Int) -> some View {
        VStack(spacing: 16) {
            Image(systemName: "checkmark.circle.fill")
                .font(.system(size: 48))
                .foregroundStyle(.green)
            Text(language.t(.submitted))
                .font(.title2.weight(.semibold))
            Text(language.t(.submittedDesc))
                .foregroundStyle(.secondary)
            NavigationLink {
                InboxDetailView(auth: auth, submissionId: submissionId)
            } label: {
                Text(language.t(.viewSubmission))
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
            Button(language.t(.done)) { dismiss() }
                .buttonStyle(.bordered)
        }
        .padding()
    }

    @ViewBuilder
    private func formContent(schema: FormSchemaResponse) -> some View {
        Form {
            if let submitError {
                Section {
                    Text(submitError)
                        .foregroundStyle(.red)
                }
            }

            ForEach(schema.sections.sorted(by: { $0.order < $1.order })) { section in
                let sectionFields = schema.fields.filter { $0.sectionId == section.id && isVisible($0, schema: schema) }
                if !sectionFields.isEmpty {
                    Section {
                        if !section.description.isEmpty {
                            Text(section.description)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        ForEach(sectionFields) { field in
                            fieldView(field, schema: schema)
                        }
                    } header: {
                        Text(section.title)
                    }
                }
            }

            let unsectioned = schema.fields.filter { $0.sectionId == nil && isVisible($0, schema: schema) }
            if !unsectioned.isEmpty {
                Section {
                    ForEach(unsectioned) { field in
                        fieldView(field, schema: schema)
                    }
                }
            }
        }
        .safeAreaInset(edge: .bottom) {
            Button {
                Task { await submit(schema: schema) }
            } label: {
                if isSubmitting {
                    ProgressView()
                        .frame(maxWidth: .infinity)
                } else {
                    Text("Submit")
                        .frame(maxWidth: .infinity)
                }
            }
            .buttonStyle(.borderedProminent)
            .disabled(isSubmitting)
            .padding()
            .background(.bar)
        }
    }

    @ViewBuilder
    private func fieldView(_ field: FormFieldSchema, schema: FormSchemaResponse) -> some View {
        let errors = fieldErrors[field.key] ?? []
        VStack(alignment: .leading, spacing: 6) {
            switch field.fieldType {
            case "textarea":
                TextField(field.label, text: bindingText(field.key), axis: .vertical)
                    .lineLimit(3 ... 8)
            case "email", "text":
                TextField(field.placeholder.isEmpty ? field.label : field.placeholder, text: bindingText(field.key))
                    .textInputAutocapitalization(field.fieldType == "email" ? .never : .sentences)
                    .keyboardType(field.fieldType == "email" ? .emailAddress : .default)
            case "number":
                TextField(field.label, text: bindingText(field.key))
                    .keyboardType(.decimalPad)
            case "date":
                DatePicker(
                    field.label,
                    selection: bindingDate(field.key),
                    displayedComponents: .date
                )
            case "select":
                Picker(field.label, selection: bindingText(field.key)) {
                    Text("—").tag("")
                    ForEach(field.choices, id: \.self) { choice in
                        Text(choice).tag(choice)
                    }
                }
            case "radio":
                VStack(alignment: .leading, spacing: 8) {
                    Text(field.label)
                        .font(.subheadline.weight(.medium))
                    ForEach(field.choices, id: \.self) { choice in
                        Button {
                            textValues[field.key] = choice
                        } label: {
                            HStack {
                                Image(systemName: textValues[field.key] == choice ? "largecircle.fill.circle" : "circle")
                                Text(choice)
                                Spacer()
                            }
                        }
                        .buttonStyle(.plain)
                    }
                }
            case "checkbox":
                Toggle(isOn: bindingBool(field.key)) {
                    Text(field.label)
                }
            case "checklist":
                VStack(alignment: .leading, spacing: 8) {
                    Text(field.label)
                        .font(.subheadline.weight(.medium))
                    ForEach(field.choices, id: \.self) { choice in
                        Toggle(choice, isOn: bindingChecklist(field.key, choice: choice))
                    }
                }
            case "file":
                VStack(alignment: .leading, spacing: 8) {
                    Text(field.label)
                        .font(.subheadline.weight(.medium))
                    if let file = fileSelections[field.key] {
                        Text(file.name)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Button("Remove file") { fileSelections.removeValue(forKey: field.key) }
                    }
                    FileImportButton { url in
                        importFile(url: url, fieldKey: field.key)
                    }
                }
            default:
                TextField(field.label, text: bindingText(field.key))
            }

            if !field.helpText.isEmpty {
                Text(field.helpText)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            ForEach(errors, id: \.self) { err in
                Text(err)
                    .font(.caption)
                    .foregroundStyle(.red)
            }
        }
    }

    private func bindingText(_ key: String) -> Binding<String> {
        Binding(
            get: { textValues[key] ?? "" },
            set: { textValues[key] = $0 }
        )
    }

    private func bindingBool(_ key: String) -> Binding<Bool> {
        Binding(
            get: { boolValues[key] ?? false },
            set: { boolValues[key] = $0 }
        )
    }

    private func bindingChecklist(_ key: String, choice: String) -> Binding<Bool> {
        Binding(
            get: { checklistValues[key]?.contains(choice) ?? false },
            set: { checked in
                var set = checklistValues[key] ?? []
                if checked { set.insert(choice) } else { set.remove(choice) }
                checklistValues[key] = set
            }
        )
    }

    private func bindingDate(_ key: String) -> Binding<Date> {
        Binding(
            get: {
                let fmt = ISO8601DateFormatter()
                fmt.formatOptions = [.withFullDate]
                if let s = textValues[key], let d = fmt.date(from: s) { return d }
                return Date()
            },
            set: {
                let fmt = ISO8601DateFormatter()
                fmt.formatOptions = [.withFullDate]
                textValues[key] = fmt.string(from: $0).prefix(10).description
            }
        )
    }

    private func isVisible(_ field: FormFieldSchema, schema: FormSchemaResponse) -> Bool {
        guard let controlId = field.visibilityControlFieldId else { return true }
        let controlKey = "f_\(controlId)"
        guard let control = schema.fields.first(where: { $0.id == controlId }) else { return false }
        let allowed = Set(field.visibilityValues)
        if allowed.isEmpty { return false }

        if control.fieldType == "checklist" {
            let selected = checklistValues[controlKey] ?? []
            if selected.isEmpty { return allowed.contains("") }
            if !selected.isDisjoint(with: allowed) { return true }
            let joined = selected.sorted().joined(separator: "\n")
            return allowed.contains(joined)
        }
        if control.fieldType == "checkbox" {
            let current = (boolValues[controlKey] ?? false) ? "yes" : ""
            return allowed.contains(current)
        }
        let current = (textValues[controlKey] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        return allowed.contains(current)
    }

    private func applyInitial(_ schema: FormSchemaResponse) {
        for field in schema.fields {
            guard let raw = schema.initial[field.key] else { continue }
            switch raw {
            case .bool(let b):
                boolValues[field.key] = b
            case .strings(let arr):
                checklistValues[field.key] = Set(arr)
            case .string(let s):
                textValues[field.key] = s
            }
        }
    }

    private func loadSchema() async {
        guard let token = auth.token else { return }
        isLoading = true
        loadError = nil
        defer { isLoading = false }
        do {
            let loaded: FormSchemaResponse
            if let relatedAccessToken {
                loaded = try await FormSubmitAPI.fetchRelatedSchema(token: token, accessToken: relatedAccessToken)
            } else if let formId {
                loaded = try await FormSubmitAPI.fetchSchema(token: token, formId: formId)
            } else {
                loadError = "Invalid form."
                return
            }
            schema = loaded
            applyInitial(loaded)
            applyDraft()
        } catch let err as APIError {
            loadError = err.message
        } catch {
            loadError = error.localizedDescription
        }
    }

    private func submit(schema: FormSchemaResponse) async {
        guard let token = auth.token else { return }
        isSubmitting = true
        submitError = nil
        fieldErrors = [:]
        defer { isSubmitting = false }

        var textPayload: [String: String] = [:]
        var checkboxPayload: [String: Bool] = [:]
        var checklistPayload: [String: [String]] = [:]
        var files: [String: (data: Data, fileName: String, mimeType: String)] = [:]

        for field in schema.fields where isVisible(field, schema: schema) {
            switch field.fieldType {
            case "checkbox":
                checkboxPayload[field.key] = boolValues[field.key] ?? false
            case "checklist":
                checklistPayload[field.key] = Array(checklistValues[field.key] ?? []).sorted()
            case "file":
                if let file = fileSelections[field.key] {
                    files[field.key] = (file.data, file.name, "application/octet-stream")
                }
            default:
                textPayload[field.key] = textValues[field.key] ?? ""
            }
        }

        do {
            let result: FormSubmitResponse
            if let relatedAccessToken {
                result = try await FormSubmitAPI.submitRelated(
                    token: token,
                    accessToken: relatedAccessToken,
                    textFields: textPayload,
                    checkboxFields: checkboxPayload,
                    checklistFields: checklistPayload,
                    files: files
                )
            } else if let formId {
                result = try await FormSubmitAPI.submit(
                    token: token,
                    formId: formId,
                    textFields: textPayload,
                    checkboxFields: checkboxPayload,
                    checklistFields: checklistPayload,
                    files: files
                )
            } else {
                return
            }
            FormDraftStore.clear(storageKey: draftStorageKey)
            successSubmissionId = result.submission?.id
            await auth.loadHomeData()
        } catch let err as FormSubmitValidationError {
            submitError = err.message
            fieldErrors = err.fieldErrors
        } catch let err as APIError {
            submitError = err.message
        } catch let urlError as URLError where isOfflineError(urlError) {
            handleOfflineSubmit(
                textPayload: textPayload,
                checkboxPayload: checkboxPayload,
                checklistPayload: checklistPayload,
                hasFiles: !files.isEmpty
            )
        } catch {
            if !network.isOnline {
                handleOfflineSubmit(
                    textPayload: textPayload,
                    checkboxPayload: checkboxPayload,
                    checklistPayload: checklistPayload,
                    hasFiles: !files.isEmpty
                )
            } else {
                submitError = error.localizedDescription
            }
        }
    }

    private func applyDraft() {
        guard let draft = FormDraftStore.load(storageKey: draftStorageKey) else { return }
        for (key, value) in draft.textValues where textValues[key]?.isEmpty != false {
            textValues[key] = value
        }
        for (key, value) in draft.boolValues {
            boolValues[key] = value
        }
        for (key, values) in draft.checklistValues {
            checklistValues[key] = Set(values)
        }
    }

    private func scheduleDraftSave() {
        draftSaveTask?.cancel()
        draftSaveTask = Task {
            try? await Task.sleep(nanoseconds: 1_500_000_000)
            guard !Task.isCancelled else { return }
            FormDraftStore.save(
                storageKey: draftStorageKey,
                textValues: textValues,
                boolValues: boolValues,
                checklistValues: checklistValues
            )
        }
    }

    private func isOfflineError(_ error: URLError) -> Bool {
        error.code == .notConnectedToInternet || error.code == .networkConnectionLost
    }

    private func handleOfflineSubmit(
        textPayload: [String: String],
        checkboxPayload: [String: Bool],
        checklistPayload: [String: [String]],
        hasFiles: Bool
    ) {
        if hasFiles {
            submitError = language.t(.offlineFilesNotQueued)
            return
        }
        let item = PendingFormSubmit(
            id: UUID().uuidString,
            kind: relatedAccessToken != nil ? "related" : "form",
            formId: formId,
            relatedAccessToken: relatedAccessToken,
            textFields: textPayload,
            checkboxFields: checkboxPayload,
            checklistFields: checklistPayload,
            createdAt: Date()
        )
        offlineQueue.enqueue(item)
        FormDraftStore.clear(storageKey: draftStorageKey)
        submitError = language.t(.queuedOffline)
    }

    private func importFile(url: URL, fieldKey: String) {
        guard url.startAccessingSecurityScopedResource() else { return }
        defer { url.stopAccessingSecurityScopedResource() }
        guard let data = try? Data(contentsOf: url) else { return }
        fileSelections[fieldKey] = (data, url.lastPathComponent)
    }
}

private struct FileImportButton: View {
    let onPick: (URL) -> Void
    @State private var showPicker = false

    var body: some View {
        Button("Choose file") { showPicker = true }
            .fileImporter(
                isPresented: $showPicker,
                allowedContentTypes: [.item],
                allowsMultipleSelection: false
            ) { result in
                if case .success(let urls) = result, let url = urls.first {
                    onPick(url)
                }
            }
    }
}
