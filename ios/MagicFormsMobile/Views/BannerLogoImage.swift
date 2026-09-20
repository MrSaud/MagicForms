import SwiftUI

/// Organization logo with natural aspect ratio inside max bounds (no toolbar clipping).
struct BannerLogoImage: View {
    let url: URL
    var accessibilityLabel: String = "Organization logo"
    var maxWidth: CGFloat = 200
    var maxHeight: CGFloat = 40

    var body: some View {
        AsyncImage(url: url) { phase in
            switch phase {
            case .success(let image):
                image
                    .resizable()
                    .scaledToFit()
                    .frame(maxWidth: maxWidth, maxHeight: maxHeight)
            case .failure:
                EmptyView()
            default:
                ProgressView()
                    .controlSize(.small)
                    .frame(width: 28, height: 28)
            }
        }
        .accessibilityLabel(accessibilityLabel)
    }
}

/// Full-width strip at the top of the screen (below status bar / Dynamic Island).
struct OrganizationLogoBanner: View {
    let url: URL
    var accessibilityLabel: String = "Organization logo"

    var body: some View {
        BannerLogoImage(
            url: url,
            accessibilityLabel: accessibilityLabel,
            maxWidth: 220,
            maxHeight: 40
        )
        .frame(maxWidth: .infinity)
        .padding(.horizontal, 16)
        .padding(.bottom, 8)
    }
}
