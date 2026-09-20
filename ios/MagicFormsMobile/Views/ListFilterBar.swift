import SwiftUI

struct FilterChipButton: View {
    let title: String
    let isSelected: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Text(title)
                .font(.caption.weight(.medium))
                .padding(.horizontal, 12)
                .padding(.vertical, 6)
                .background(isSelected ? Color.accentColor.opacity(0.2) : Color.secondary.opacity(0.12))
                .foregroundStyle(isSelected ? Color.accentColor : Color.primary)
                .clipShape(Capsule())
        }
        .buttonStyle(.plain)
    }
}

struct ListFilterChipRow: View {
    let chips: [(id: String, title: String, isSelected: Bool, action: () -> Void)]

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(chips, id: \.id) { chip in
                    FilterChipButton(title: chip.title, isSelected: chip.isSelected, action: chip.action)
                }
            }
            .padding(.horizontal, 16)
        }
    }
}

enum FormsListFilter {
    static func apply(
        to forms: [PublishedFormItem],
        searchText: String,
        entitySlug: String?,
        categorySlug: String?
    ) -> [PublishedFormItem] {
        let query = searchText.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        return forms.filter { form in
            if let entitySlug, form.entity.slug != entitySlug { return false }
            if let categorySlug {
                guard let category = form.category, category.slug == categorySlug else { return false }
            }
            guard !query.isEmpty else { return true }
            if form.title.lowercased().contains(query) { return true }
            if form.slug.lowercased().contains(query) { return true }
            if form.entity.name.lowercased().contains(query) { return true }
            if form.description.lowercased().contains(query) { return true }
            if let category = form.category, category.name.lowercased().contains(query) { return true }
            return false
        }
    }

    static func entityOptions(from forms: [PublishedFormItem]) -> [(slug: String, name: String)] {
        var seen = Set<String>()
        var result: [(slug: String, name: String)] = []
        for form in forms {
            if seen.insert(form.entity.slug).inserted {
                result.append((form.entity.slug, form.entity.name))
            }
        }
        return result.sorted { $0.name.localizedCaseInsensitiveCompare($1.name) == .orderedAscending }
    }

    static func categoryOptions(from forms: [PublishedFormItem]) -> [(slug: String, name: String)] {
        var seen = Set<String>()
        var result: [(slug: String, name: String)] = []
        for form in forms {
            guard let category = form.category else { continue }
            if seen.insert(category.slug).inserted {
                result.append((category.slug, category.name))
            }
        }
        return result.sorted { $0.name.localizedCaseInsensitiveCompare($1.name) == .orderedAscending }
    }
}

enum InboxListFilter {
    static func apply(
        to items: [InboxItem],
        searchText: String,
        entitySlug: String?,
        formId: Int?,
        actionNeededOnly: Bool,
        unreadOnly: Bool
    ) -> [InboxItem] {
        let query = searchText.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        return items.filter { item in
            if let entitySlug, item.form.entitySlug != entitySlug { return false }
            if let formId, item.form.id != formId { return false }
            if actionNeededOnly, !item.canAct { return false }
            if unreadOnly, !item.hasUnreadThread { return false }
            guard !query.isEmpty else { return true }
            if item.form.title.lowercased().contains(query) { return true }
            if item.form.entityName.lowercased().contains(query) { return true }
            if item.submitter.lowercased().contains(query) { return true }
            if item.referenceToken.lowercased().contains(query) { return true }
            if item.currentStepLabel.lowercased().contains(query) { return true }
            return false
        }
    }

    static func entityOptions(from items: [InboxItem]) -> [(slug: String, name: String)] {
        var seen = Set<String>()
        var result: [(slug: String, name: String)] = []
        for item in items {
            if seen.insert(item.form.entitySlug).inserted {
                result.append((item.form.entitySlug, item.form.entityName))
            }
        }
        return result.sorted { $0.name.localizedCaseInsensitiveCompare($1.name) == .orderedAscending }
    }

    static func formOptions(from items: [InboxItem]) -> [(id: Int, title: String)] {
        var seen = Set<Int>()
        var result: [(id: Int, title: String)] = []
        for item in items {
            if seen.insert(item.form.id).inserted {
                result.append((item.form.id, item.form.title))
            }
        }
        return result.sorted { $0.title.localizedCaseInsensitiveCompare($1.title) == .orderedAscending }
    }
}
