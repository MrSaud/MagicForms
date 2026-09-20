import SwiftUI

struct AppLogoView: View {
    var height: CGFloat = 26

    var body: some View {
        Image("AppLogo")
            .resizable()
            .scaledToFit()
            .frame(height: height)
            .accessibilityLabel("SForms")
    }
}
