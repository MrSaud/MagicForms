import SwiftUI

struct InboxView: View {
    @ObservedObject var auth: AuthViewModel
    @EnvironmentObject private var language: LanguageManager
    @State private var rejectComments: [Int: String] = [:]
    @State private var searchText = ""
    @State private var selectedEntitySlug: String?
    @State private var selectedFormId: Int?
    @State private var actionNeededOnly = false
    @State private var unreadOnly = false
    @State private var swipeApproveItem: InboxItem?
    @State private var swipeRejectItem: InboxItem?
    @State private var swipeRejectComment = ""

    private var filteredItems: [InboxItem] {
        InboxListFilter.apply(
            to: auth.inboxItems,
            searchText: searchText,
            entitySlug: selectedEntitySlug,
            formId: selectedFormId,
            actionNeededOnly: actionNeededOnly,
            unreadOnly: unreadOnly
        )
    }

    private var hasActiveFilters: Bool {
        !searchText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            || selectedEntitySlug != nil
            || selectedFormId != nil
            || actionNeededOnly
            || unreadOnly
    }

    private var entityOptions: [(slug: String, name: String)] {
        InboxListFilter.entityOptions(from: auth.inboxItems)
    }

    private var formOptions: [(id: Int, title: String)] {
        InboxListFilter.formOptions(from: auth.inboxItems)
    }

    var body: some View {
        Group {
            if auth.inboxItems.isEmpty && !auth.isLoadingHome {
                ContentUnavailableView(
                    language.t(.inboxEmpty),
                    systemImage: "tray",
                    description: Text(language.t(.inboxEmptyDesc))
                )
            } else if filteredItems.isEmpty {
                ContentUnavailableView(
                    language.t(.noMatches),
                    systemImage: "line.3.horizontal.decrease.circle",
                    description: Text(language.t(.noMatchesDesc))
                )
            } else {
                List(filteredItems) { item in
                    VStack(alignment: .leading, spacing: 8) {
                        NavigationLink(value: item.id) {
                            InboxRowContent(item: item, language: language)
                        }

                        if let err = auth.inboxItemErrors[item.id] {
                            Text(err)
                                .font(.caption)
                                .foregroundStyle(.red)
                        }
                    }
                    .padding(.vertical, 4)
                    .swipeActions(edge: .trailing, allowsFullSwipe: false) {
                        if item.canAct {
                            Button {
                                swipeApproveItem = item
                            } label: {
                                Label(language.t(.approve), systemImage: "checkmark")
                            }
                            .tint(.green)
                        }
                    }
                    .swipeActions(edge: .leading, allowsFullSwipe: false) {
                        if item.canAct {
                            Button {
                                swipeRejectItem = item
                                swipeRejectComment = rejectComments[item.id, default: ""]
                            } label: {
                                Label(language.t(.reject), systemImage: "xmark")
                            }
                            .tint(.red)
                        }
                    }
                }
                .listStyle(.plain)
                .refreshable { await auth.refreshInbox() }
            }
        }
        .searchable(text: $searchText, prompt: language.t(.searchInbox))
        .safeAreaInset(edge: .top, spacing: 0) {
            if !auth.inboxItems.isEmpty {
                inboxFilterBar
            }
        }
        .toolbar {
            if hasActiveFilters {
                ToolbarItem(placement: .topBarTrailing) {
                    Button(language.t(.clear)) {
                        searchText = ""
                        selectedEntitySlug = nil
                        selectedFormId = nil
                        actionNeededOnly = false
                        unreadOnly = false
                    }
                }
            }
        }
        .navigationDestination(for: Int.self) { submissionId in
            InboxDetailView(auth: auth, submissionId: submissionId)
        }
        .overlay {
            if auth.isLoadingHome && auth.inboxItems.isEmpty {
                ProgressView()
            }
        }
        .confirmationDialog(
            language.t(.confirmApproveTitle),
            isPresented: Binding(
                get: { swipeApproveItem != nil },
                set: { if !$0 { swipeApproveItem = nil } }
            ),
            titleVisibility: .visible
        ) {
            Button(language.t(.approve), role: .none) {
                guard let item = swipeApproveItem else { return }
                swipeApproveItem = nil
                Task {
                    await auth.performInboxWorkflow(
                        submissionId: item.id,
                        decision: "approve",
                        comment: nil,
                        workflowActionAnchor: item.currentStepId
                    )
                }
            }
            Button(language.t(.cancel), role: .cancel) {
                swipeApproveItem = nil
            }
        } message: {
            Text(language.t(.confirmApproveMessage))
        }
        .alert(language.t(.confirmRejectTitle), isPresented: Binding(
            get: { swipeRejectItem != nil },
            set: { if !$0 { swipeRejectItem = nil; swipeRejectComment = "" } }
        )) {
            TextField(language.t(.rejectionReason), text: $swipeRejectComment)
            Button(language.t(.reject), role: .destructive) {
                guard let item = swipeRejectItem else { return }
                let comment = swipeRejectComment.trimmingCharacters(in: .whitespacesAndNewlines)
                swipeRejectItem = nil
                rejectComments[item.id] = comment
                Task {
                    await auth.performInboxWorkflow(
                        submissionId: item.id,
                        decision: "reject",
                        comment: comment,
                        workflowActionAnchor: item.currentStepId
                    )
                }
            }
            .disabled(swipeRejectComment.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            Button(language.t(.cancel), role: .cancel) {
                swipeRejectItem = nil
                swipeRejectComment = ""
            }
        }
    }

    private var inboxFilterBar: some View {
        ListFilterChipRow(chips: inboxFilterChips)
            .padding(.vertical, 8)
            .background(.bar)
    }

    private var inboxFilterChips: [(id: String, title: String, isSelected: Bool, action: () -> Void)] {
        var chips: [(id: String, title: String, isSelected: Bool, action: () -> Void)] = []
        if entityOptions.count > 1 {
            chips.append(("entity-all", language.t(.allOrgs), selectedEntitySlug == nil, { selectedEntitySlug = nil }))
            for entity in entityOptions {
                chips.append((
                    "entity-\(entity.slug)",
                    entity.name,
                    selectedEntitySlug == entity.slug,
                    { selectedEntitySlug = entity.slug }
                ))
            }
        }
        if formOptions.count > 1 {
            chips.append(("form-all", language.t(.allForms), selectedFormId == nil, { selectedFormId = nil }))
            for form in formOptions {
                chips.append((
                    "form-\(form.id)",
                    form.title,
                    selectedFormId == form.id,
                    { selectedFormId = form.id }
                ))
            }
        }
        chips.append((
            "action-needed",
            language.t(.actionNeeded),
            actionNeededOnly,
            { actionNeededOnly.toggle() }
        ))
        chips.append((
            "unread",
            language.t(.unread),
            unreadOnly,
            { unreadOnly.toggle() }
        ))
        return chips
    }
}

private struct InboxRowContent: View {
    let item: InboxItem
    let language: LanguageManager

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(item.form.title)
                    .font(.body.weight(.semibold))
                Spacer()
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
        }
    }
}

