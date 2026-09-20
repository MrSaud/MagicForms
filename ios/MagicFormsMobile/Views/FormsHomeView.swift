import SwiftUI

struct FormsHomeView: View {
    @ObservedObject var auth: AuthViewModel
    @EnvironmentObject private var language: LanguageManager

    @State private var searchText = ""
    @State private var selectedEntitySlug: String?
    @State private var selectedCategorySlug: String?

    private var filteredForms: [PublishedFormItem] {
        FormsListFilter.apply(
            to: auth.publishedForms,
            searchText: searchText,
            entitySlug: selectedEntitySlug,
            categorySlug: selectedCategorySlug
        )
    }

    private var hasActiveFilters: Bool {
        !searchText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            || selectedEntitySlug != nil
            || selectedCategorySlug != nil
    }

    private var entityOptions: [(slug: String, name: String)] {
        FormsListFilter.entityOptions(from: auth.publishedForms)
    }

    private var categoryOptions: [(slug: String, name: String)] {
        FormsListFilter.categoryOptions(from: auth.publishedForms)
    }

    var body: some View {
        Group {
            if auth.publishedForms.isEmpty && !auth.isLoadingHome {
                ContentUnavailableView(
                    language.t(.noOpenForms),
                    systemImage: "doc.text",
                    description: Text(language.t(.noOpenFormsDesc))
                )
            } else if filteredForms.isEmpty {
                ContentUnavailableView(
                    language.t(.noMatches),
                    systemImage: "line.3.horizontal.decrease.circle",
                    description: Text(language.t(.noMatchesDesc))
                )
            } else {
                List(filteredForms) { form in
                    VStack(alignment: .leading, spacing: 6) {
                        NavigationLink {
                            FormSubmitView(auth: auth, formId: form.id, formTitle: form.title)
                        } label: {
                            FormRow(form: form)
                        }
                        if form.introPageEnabled {
                            NavigationLink {
                                FormIntroView(auth: auth, formId: form.id, formTitle: form.title)
                            } label: {
                                Label(language.t(.readMoreAboutForm), systemImage: "doc.text.magnifyingglass")
                                    .font(.subheadline)
                            }
                            .padding(.leading, 4)
                        }
                    }
                }
                .listStyle(.plain)
                .refreshable { await auth.loadHomeData() }
            }
        }
        .searchable(text: $searchText, prompt: language.t(.searchForms))
        .safeAreaInset(edge: .top, spacing: 0) {
            if entityOptions.count > 1 || !categoryOptions.isEmpty {
                formsFilterBar
            }
        }
        .toolbar {
            if hasActiveFilters {
                ToolbarItem(placement: .topBarTrailing) {
                    Button(language.t(.clear)) {
                        searchText = ""
                        selectedEntitySlug = nil
                        selectedCategorySlug = nil
                    }
                }
            }
        }
        .overlay {
            if auth.isLoadingHome && auth.publishedForms.isEmpty {
                ProgressView()
            }
        }
    }

    private var formsFilterBar: some View {
        ListFilterChipRow(
            chips: formsFilterChips
        )
        .padding(.vertical, 8)
        .background(.bar)
    }

    private var formsFilterChips: [(id: String, title: String, isSelected: Bool, action: () -> Void)] {
        var chips: [(id: String, title: String, isSelected: Bool, action: () -> Void)] = []
        if entityOptions.count > 1 {
            chips.append((
                "entity-all",
                language.t(.allOrgs),
                selectedEntitySlug == nil,
                { selectedEntitySlug = nil }
            ))
            for entity in entityOptions {
                chips.append((
                    "entity-\(entity.slug)",
                    entity.name,
                    selectedEntitySlug == entity.slug,
                    { selectedEntitySlug = entity.slug }
                ))
            }
        }
        if !categoryOptions.isEmpty {
            chips.append((
                "cat-all",
                language.t(.allCategories),
                selectedCategorySlug == nil,
                { selectedCategorySlug = nil }
            ))
            for category in categoryOptions {
                chips.append((
                    "cat-\(category.slug)",
                    category.name,
                    selectedCategorySlug == category.slug,
                    { selectedCategorySlug = category.slug }
                ))
            }
        }
        return chips
    }
}

private struct FormRow: View {
    @EnvironmentObject private var language: LanguageManager
    let form: PublishedFormItem

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(form.title)
                .font(.body.weight(.semibold))
            Text(form.entity.name)
                .font(.caption)
                .foregroundStyle(.secondary)
            if let category = form.category, !category.name.isEmpty {
                Text(category.name)
                    .font(.caption)
                    .foregroundStyle(.tertiary)
            }
            if !form.submissionDeadlineLabel.isEmpty {
                Text(language.t(.due, form.submissionDeadlineLabel))
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            if !form.description.isEmpty {
                Text(form.description)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
            }
        }
        .padding(.vertical, 4)
    }
}
