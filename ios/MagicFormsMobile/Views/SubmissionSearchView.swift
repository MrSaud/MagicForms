import SwiftUI

struct SubmissionSearchView: View {
    @ObservedObject var auth: AuthViewModel
    @EnvironmentObject private var language: LanguageManager

    @State private var searchText = ""
    @State private var relation = "any"
    @State private var workflowState = ""
    @State private var selectedFormId: Int?
    @State private var items: [InboxItem] = []
    @State private var formOptions: [SearchFormOption] = []
    @State private var total = 0
    @State private var isLoading = false
    @State private var errorMessage: String?

    var body: some View {
        Group {
            if items.isEmpty && !isLoading && errorMessage == nil {
                ContentUnavailableView(
                    language.t(.searchEmpty),
                    systemImage: "magnifyingglass",
                    description: Text(language.t(.searchEmptyDesc))
                )
            } else if items.isEmpty && !isLoading {
                ContentUnavailableView(
                    language.t(.noMatches),
                    systemImage: "line.3.horizontal.decrease.circle",
                    description: Text(errorMessage ?? language.t(.noMatchesDesc))
                )
            } else {
                List(items) { item in
                    NavigationLink(value: item.id) {
                        SearchResultRow(item: item, language: language)
                    }
                }
                .listStyle(.plain)
            }
        }
        .searchable(text: $searchText, prompt: language.t(.searchRequests))
        .onSubmit(of: .search) { Task { await runSearch() } }
        .onChange(of: searchText) { _, _ in
            Task { await runSearchDebounced() }
        }
        .safeAreaInset(edge: .top, spacing: 0) {
            searchFilterBar
        }
        .navigationDestination(for: Int.self) { submissionId in
            InboxDetailView(auth: auth, submissionId: submissionId)
        }
        .overlay {
            if isLoading && items.isEmpty {
                ProgressView()
            }
        }
        .task {
            await runSearch()
        }
        .refreshable {
            await runSearch()
        }
    }

    private var searchFilterBar: some View {
        VStack(spacing: 0) {
            ListFilterChipRow(chips: searchFilterChips)
            if total > 0 {
                Text(language.t(.resultsCount, total))
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.horizontal, 16)
                    .padding(.bottom, 6)
            }
        }
        .padding(.vertical, 8)
        .background(.bar)
    }

    private var searchFilterChips: [(id: String, title: String, isSelected: Bool, action: () -> Void)] {
        var chips: [(id: String, title: String, isSelected: Bool, action: () -> Void)] = [
            ("rel-any", language.t(.allRoles), relation == "any", { applyRelation("any") }),
            ("rel-applicant", language.t(.roleApplicant), relation == "applicant", { applyRelation("applicant") }),
            ("rel-workflow", language.t(.roleWorkflow), relation == "workflow", { applyRelation("workflow") }),
            ("wf-all", language.t(.allStatus), workflowState.isEmpty, { applyWorkflowState("") }),
            ("wf-progress", language.t(.statusInProgress), workflowState == "in_progress", { applyWorkflowState("in_progress") }),
            ("wf-completed", language.t(.statusCompleted), workflowState == "completed", { applyWorkflowState("completed") }),
            ("wf-rejected", language.t(.statusRejected), workflowState == "rejected", { applyWorkflowState("rejected") }),
        ]
        if formOptions.count > 1 {
            chips.append(("form-all", language.t(.allForms), selectedFormId == nil, { applyForm(nil) }))
            for form in formOptions {
                chips.append((
                    "form-\(form.id)",
                    form.title,
                    selectedFormId == form.id,
                    { applyForm(form.id) }
                ))
            }
        }
        return chips
    }

    private func applyRelation(_ value: String) {
        relation = value
        Task { await runSearch() }
    }

    private func applyWorkflowState(_ value: String) {
        workflowState = value
        Task { await runSearch() }
    }

    private func applyForm(_ id: Int?) {
        selectedFormId = id
        Task { await runSearch() }
    }

    @State private var searchTask: Task<Void, Never>?

    private func runSearchDebounced() async {
        searchTask?.cancel()
        searchTask = Task {
            try? await Task.sleep(nanoseconds: 400_000_000)
            guard !Task.isCancelled else { return }
            await runSearch()
        }
    }

    private func runSearch() async {
        guard let token = auth.token else { return }
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            let response = try await SearchAPI.fetchSubmissions(
                token: token,
                query: searchText,
                relation: relation,
                workflowState: workflowState.isEmpty ? nil : workflowState,
                formId: selectedFormId
            )
            items = response.items
            formOptions = response.formOptions
            total = response.total
        } catch let apiError as APIError {
            errorMessage = apiError.message
            items = []
        } catch {
            errorMessage = error.localizedDescription
            items = []
        }
    }
}

private struct SearchResultRow: View {
    let item: InboxItem
    let language: LanguageManager

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(item.form.title)
                    .font(.body.weight(.semibold))
                Spacer()
                Text(item.workflowStateLabel)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            if !item.roleLabels.isEmpty {
                Text(item.roleLabels.joined(separator: " · "))
                    .font(.caption)
                    .foregroundStyle(.tertiary)
            }
            Text(item.form.entityName)
                .font(.caption)
                .foregroundStyle(.secondary)
            if !item.submitter.isEmpty {
                Text(item.submitter)
                    .font(.caption)
            }
            if !item.currentStepLabel.isEmpty {
                Text(item.currentStepLabel)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            if !item.referenceToken.isEmpty {
                Text(item.referenceToken)
                    .font(.caption2.monospaced())
                    .foregroundStyle(.tertiary)
            }
            if item.canAct {
                Text(language.t(.actionNeeded))
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(.orange)
            }
            if item.hasUnreadThread {
                Image(systemName: "message.badge.fill")
                    .font(.caption)
                    .foregroundStyle(.blue)
                    .accessibilityLabel(language.t(.unreadMessages))
            }
        }
        .padding(.vertical, 4)
    }
}
