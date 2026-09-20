import SwiftUI

struct LoginView: View {
    @ObservedObject var auth: AuthViewModel
    @EnvironmentObject private var language: LanguageManager
    @FocusState private var focusedField: Field?

    private enum Field: Hashable {
        case entitySlug, username, password
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                LanguagePickerView()

                AppLogoView(height: 28)
                Text(language.t(.signInSubtitle))
                    .font(.subheadline)
                    .foregroundStyle(.secondary)

                OrganizationLoginField(
                    entitySlug: $auth.entitySlug,
                    username: $auth.username,
                    directoryEntities: auth.directoryEntities,
                    focusedField: $focusedField,
                    entityField: .entitySlug,
                    usernameField: .username
                )

                VStack(alignment: .leading, spacing: 6) {
                    Text(language.t(.password))
                        .font(.subheadline.weight(.medium))
                    SecureField(language.t(.password), text: $auth.password)
                        .textContentType(.password)
                        .focused($focusedField, equals: .password)
                        .padding(12)
                        .background(Color(.secondarySystemBackground))
                        .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                }

                if let error = auth.errorMessage {
                    Text(error)
                        .font(.footnote)
                        .foregroundStyle(.red)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }

                Button {
                    focusedField = nil
                    Task { await auth.login() }
                } label: {
                    Group {
                        if auth.isLoading {
                            ProgressView()
                                .tint(.white)
                        } else {
                            Text(language.t(.signIn))
                                .fontWeight(.semibold)
                        }
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 14)
                }
                .buttonStyle(.borderedProminent)
                .disabled(auth.isLoading || !auth.canSubmitLogin)
            }
            .padding(24)
        }
        .scrollDismissesKeyboard(.interactively)
        .task { await auth.loadDirectoryEntities() }
    }
}

#Preview {
    LoginView(auth: AuthViewModel())
}
