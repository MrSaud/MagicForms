import SwiftUI

/// Divided organization login: editable ``entity-slug`` + ``-`` + ``username`` in one control.
struct OrganizationLoginField<Field: Hashable>: View {
    @Binding var entitySlug: String
    @Binding var username: String
    let directoryEntities: [APIEntity]
    var focusedField: FocusState<Field?>.Binding
    let entityField: Field
    let usernameField: Field

    private var showEntitySegment: Bool {
        !directoryEntities.isEmpty
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Organization username")
                .font(.subheadline.weight(.medium))

            HStack(spacing: 0) {
                if showEntitySegment {
                    entitySegment
                        .frame(maxWidth: .infinity, alignment: .leading)

                    Text("–")
                        .font(.body.weight(.medium))
                        .foregroundStyle(.secondary)
                        .padding(.horizontal, 10)
                        .accessibilityHidden(true)
                }

                TextField("username", text: $username)
                    .textContentType(.username)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .focused(focusedField, equals: usernameField)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 12)
            .background(Color(.secondarySystemBackground))
            .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))

            if showEntitySegment {
                Text(hintText)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
    }

    private var hintText: String {
        if directoryEntities.count > 1 {
            return "Type your organization slug or tap the list to choose one, then enter your username."
        }
        if let only = directoryEntities.first {
            return "Organization slug (e.g. \(only.slug)), then your username — same as the web sign-in."
        }
        return "Organization slug and username, separated by a hyphen."
    }

    private var entitySegment: some View {
        HStack(spacing: 6) {
            TextField("org-slug", text: $entitySlug)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
                .focused(focusedField, equals: entityField)
                .font(.body.monospaced())
                .accessibilityLabel("Organization slug")

            if directoryEntities.count > 1 {
                Menu {
                    ForEach(directoryEntities, id: \.slug) { entity in
                        Button {
                            entitySlug = entity.slug
                        } label: {
                            Text("\(entity.name) (\(entity.slug))")
                        }
                    }
                } label: {
                    Image(systemName: "list.bullet")
                        .font(.body.weight(.medium))
                        .foregroundStyle(.secondary)
                        .padding(6)
                        .background(Color(.tertiarySystemFill))
                        .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
                }
                .accessibilityLabel("Choose organization")
            }
        }
    }
}

#Preview {
    struct PreviewWrapper: View {
        @State private var slug = ""
        @State private var user = "jdoe"
        @FocusState private var focused: Int?

        var body: some View {
            OrganizationLoginField(
                entitySlug: $slug,
                username: $user,
                directoryEntities: [
                    APIEntity(id: 1, slug: "mosa-kuwait", name: "MOSA Kuwait"),
                    APIEntity(id: 2, slug: "default", name: "Default"),
                ],
                focusedField: $focused,
                entityField: 0,
                usernameField: 1
            )
            .padding()
        }
    }
    return PreviewWrapper()
}
