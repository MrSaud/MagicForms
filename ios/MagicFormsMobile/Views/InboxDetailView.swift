import SwiftUI

struct InboxDetailView: View {
    @ObservedObject var auth: AuthViewModel
    @EnvironmentObject private var language: LanguageManager
    let submissionId: Int

    @State private var detail: InboxDetailResponse?
    @State private var threadDraft = ""
    @State private var isLoading = true
    @State private var isPostingThread = false
    @State private var errorMessage: String?
    var body: some View {
        Group {
            if isLoading && detail == nil {
                ProgressView()
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if let detail {
                detailContent(detail)
            } else {
                ContentUnavailableView(
                    language.t(.couldNotLoad),
                    systemImage: "exclamationmark.triangle",
                    description: Text(errorMessage ?? language.t(.tryAgain))
                )
            }
        }
        .navigationTitle(detail?.submission.form.title ?? language.t(.request))
        .navigationBarTitleDisplayMode(.inline)
        .task { await loadDetail() }
        .refreshable { await loadDetail() }
    }

    @ViewBuilder
    private func detailContent(_ detail: InboxDetailResponse) -> some View {
        let sub = detail.submission
        List {
            if let errorMessage {
                Section { Text(errorMessage).foregroundStyle(.red) }
            }

            Section(language.t(.requestSection)) {
                LabeledContent(language.t(.reference), value: sub.referenceToken)
                LabeledContent(language.t(.status), value: sub.workflowStateLabel)
                LabeledContent(language.t(.submittedLabel), value: sub.submittedAtLabel)
                if !sub.submitter.isEmpty {
                    LabeledContent(language.t(.from), value: sub.submitter)
                }
                if !sub.submitterEmail.isEmpty {
                    LabeledContent(language.t(.email), value: sub.submitterEmail)
                }
                if !sub.currentStepLabel.isEmpty {
                    LabeledContent(language.t(.currentStep), value: sub.currentStepLabel)
                }
                LabeledContent(language.t(.organization), value: sub.form.entityName)
                if sub.canAct && sub.actingAsDelegate {
                    Text(language.t(.delegateNotice))
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
            }

            if let thread = detail.thread {
                Section(language.t(.thread)) {
                    if thread.messages.isEmpty {
                        Text(language.t(.threadMessages))
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    ForEach(thread.messages) { msg in
                        VStack(alignment: .leading, spacing: 4) {
                            HStack {
                                Text(msg.authorDisplay)
                                    .font(.subheadline.weight(.semibold))
                                Spacer()
                                Text(msg.createdAtLabel)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                            Text(msg.body)
                                .font(.body)
                        }
                        .padding(.vertical, 2)
                    }
                    if thread.canPost {
                        TextField(language.t(.addMessage), text: $threadDraft, axis: .vertical)
                            .lineLimit(2...5)
                        Button {
                            Task { await postThread() }
                        } label: {
                            if isPostingThread {
                                ProgressView()
                            } else {
                                Text(language.t(.post)).frame(maxWidth: .infinity)
                            }
                        }
                        .disabled(isPostingThread || threadDraft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                    }
                }
            }

            if let documents = detail.documents {
                documentsSection(documents)
            }

            if !detail.values.isEmpty {
                Section(language.t(.responses)) {
                    ForEach(detail.values) { field in
                        VStack(alignment: .leading, spacing: 4) {
                            Text(field.fieldLabel)
                                .font(.subheadline.weight(.medium))
                            if field.fieldType == "file", let att = field.attachment,
                               let token = auth.token {
                                NavigationLink {
                                    DocumentPreviewView(
                                        title: att.filename,
                                        url: HomeAPI.documentURL(apiPath: att.apiPath),
                                        bearerToken: token,
                                        filename: att.filename
                                    )
                                } label: {
                                    Text(att.filename)
                                        .font(.body)
                                }
                            } else {
                                Text(field.displayValue.isEmpty ? "—" : field.displayValue)
                                    .font(.body)
                                    .foregroundStyle(field.displayValue.isEmpty ? .secondary : .primary)
                            }
                        }
                        .padding(.vertical, 2)
                    }
                }
            }

            if !detail.events.isEmpty {
                Section(language.t(.timeline)) {
                    ForEach(detail.events) { event in
                        VStack(alignment: .leading, spacing: 4) {
                            HStack {
                                Text(event.kindLabel)
                                    .font(.subheadline.weight(.semibold))
                                Spacer()
                                Text(event.createdAtLabel)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                            if !event.stepLabel.isEmpty {
                                Text(event.stepLabel)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                            if !event.author.isEmpty {
                                Text(event.author).font(.caption)
                            }
                            if !event.message.isEmpty {
                                Text(event.message).font(.footnote)
                            }
                        }
                        .padding(.vertical, 2)
                    }
                }
            }
        }
        .overlay {
            if isPostingThread {
                ProgressView()
                    .padding()
                    .background(.ultraThinMaterial)
                    .clipShape(RoundedRectangle(cornerRadius: 12))
            }
        }
    }

    @ViewBuilder
    private func documentsSection(_ documents: SubmissionDocumentsBlock) -> some View {
        if let merged = documents.merged, merged.hasMergeOutput, let token = auth.token {
            Section(language.t(.mergedDocument)) {
                if merged.canViewPdfInline || merged.showPdfDownload {
                    NavigationLink {
                        DocumentPreviewView(
                            title: language.t(.mergedDocument),
                            url: HomeAPI.documentURL(apiPath: merged.pdfApiPath, inline: true),
                            bearerToken: token,
                            filename: "merged.pdf"
                        )
                    } label: {
                        Label(language.t(.viewPdf), systemImage: "doc.richtext")
                    }
                }
                if merged.showDocxDownload {
                    NavigationLink {
                        DocumentPreviewView(
                            title: language.t(.mergedDocument),
                            url: HomeAPI.documentURL(apiPath: merged.docxApiPath),
                            bearerToken: token,
                            filename: "merged.docx"
                        )
                    } label: {
                        Label(language.t(.viewDocx), systemImage: "doc")
                    }
                }
                if merged.showOdtDownload {
                    NavigationLink {
                        DocumentPreviewView(
                            title: language.t(.mergedDocument),
                            url: HomeAPI.documentURL(apiPath: merged.odtApiPath),
                            bearerToken: token,
                            filename: "merged.odt"
                        )
                    } label: {
                        Label(language.t(.viewOdt), systemImage: "doc")
                    }
                }
            }
        }
        if !documents.attachments.isEmpty, let token = auth.token {
            Section(language.t(.attachedDocuments)) {
                ForEach(documents.attachments) { doc in
                    let path = doc.canPreviewPdf && !doc.isPdf ? doc.pdfApiPath : doc.downloadApiPath
                    let inline = doc.canPreviewPdf
                    NavigationLink {
                        DocumentPreviewView(
                            title: doc.title.isEmpty ? doc.filename : doc.title,
                            url: HomeAPI.documentURL(apiPath: path, inline: inline && !doc.isPdf),
                            bearerToken: token,
                            filename: doc.filename
                        )
                    } label: {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(doc.title.isEmpty ? doc.filename : doc.title)
                            if !doc.title.isEmpty {
                                Text(doc.filename)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        }
                    }
                }
            }
        }
    }

    private func loadDetail() async {
        guard let token = auth.token else { return }
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            detail = try await HomeAPI.fetchInboxDetail(token: token, submissionId: submissionId)
        } catch let apiError as APIError {
            errorMessage = apiError.message
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func postThread() async {
        guard let token = auth.token else { return }
        let body = threadDraft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !body.isEmpty else { return }
        isPostingThread = true
        errorMessage = nil
        defer { isPostingThread = false }
        do {
            detail = try await HomeAPI.postThreadMessage(token: token, submissionId: submissionId, body: body)
            threadDraft = ""
            await auth.refreshInbox()
        } catch let apiError as APIError {
            errorMessage = apiError.message
        } catch {
            errorMessage = error.localizedDescription
        }
    }

}
