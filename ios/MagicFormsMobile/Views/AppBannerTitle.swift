import SwiftUI

/// Navigation bar title (organization logo is shown in ``OrganizationLogoBanner`` below the bar).
struct AppBannerTitle: View {
    let entityLabel: String
    let screenTitle: String
    var username: String = ""

    var body: some View {
        VStack(spacing: 4) {
            if !entityLabel.isEmpty {
                Text(entityLabel)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
                    .multilineTextAlignment(.center)
                    .minimumScaleFactor(0.8)
            }
            Text(screenTitle)
                .font(.headline)
            if !username.isEmpty {
                Text(username)
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
                    .lineLimit(1)
            }
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel(accessibilityText)
    }

    private var accessibilityText: String {
        var parts: [String] = []
        if !entityLabel.isEmpty { parts.append(entityLabel) }
        parts.append(screenTitle)
        if !username.isEmpty { parts.append(username) }
        return parts.joined(separator: ", ")
    }
}
