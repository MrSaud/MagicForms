import SwiftUI

struct LanguagePickerView: View {
    @EnvironmentObject private var language: LanguageManager
    var onChanged: (() -> Void)? = nil

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(language.t(.language))
                .font(.subheadline.weight(.medium))
                .foregroundStyle(.secondary)
            HStack(spacing: 8) {
                ForEach(AppLanguage.allCases) { lang in
                    Button {
                        language.setLanguage(lang)
                        onChanged?()
                    } label: {
                        Text(lang.displayName)
                            .font(.subheadline.weight(language.language == lang ? .semibold : .regular))
                            .padding(.horizontal, 12)
                            .padding(.vertical, 8)
                            .background(
                                language.language == lang
                                    ? Color.accentColor.opacity(0.2)
                                    : Color(.secondarySystemBackground)
                            )
                            .clipShape(Capsule())
                    }
                    .buttonStyle(.plain)
                }
            }
        }
    }
}
