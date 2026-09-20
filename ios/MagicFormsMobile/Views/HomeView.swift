import SwiftUI

struct HomeView: View {
    @ObservedObject var auth: AuthViewModel

    var body: some View {
        NavigationStack {
            List {
                if let user = auth.user {
                    Section("Signed in") {
                        LabeledContent("Name", value: user.displayName)
                        LabeledContent("Username", value: user.username)
                        if !user.email.isEmpty {
                            LabeledContent("Email", value: user.email)
                        }
                        if user.isStaff {
                            Text("Staff")
                                .font(.caption)
                                .padding(.horizontal, 8)
                                .padding(.vertical, 4)
                                .background(Color.blue.opacity(0.15))
                                .clipShape(Capsule())
                        }
                    }
                }

                Section("Organizations") {
                    if auth.entities.isEmpty {
                        Text("No organizations linked.")
                            .foregroundStyle(.secondary)
                    } else {
                        ForEach(auth.entities, id: \.slug) { entity in
                            VStack(alignment: .leading, spacing: 2) {
                                Text(entity.name)
                                    .font(.body.weight(.medium))
                                Text(entity.slug)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        }
                    }
                }

                Section {
                    Button("Refresh profile") {
                        Task { await auth.refreshSession() }
                    }
                    .disabled(auth.isLoading)

                    Button("Sign out", role: .destructive) {
                        Task { await auth.logout() }
                    }
                    .disabled(auth.isLoading)
                }
            }
            .navigationTitle("Home")
            .overlay {
                if auth.isLoading {
                    ProgressView()
                        .padding()
                        .background(.ultraThinMaterial)
                        .clipShape(RoundedRectangle(cornerRadius: 12))
                }
            }
        }
    }
}

#Preview {
    HomeView(auth: AuthViewModel())
}
