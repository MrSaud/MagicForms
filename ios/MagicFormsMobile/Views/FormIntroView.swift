import SwiftUI
import WebKit

struct FormIntroView: View {
    @ObservedObject var auth: AuthViewModel
    @EnvironmentObject private var language: LanguageManager
    let formId: Int
    let formTitle: String

    @State private var intro: FormIntroPayload?
    @State private var loadError: String?
    @State private var isLoading = true
    @State private var galleryIndex = 0

    var body: some View {
        Group {
            if isLoading {
                ProgressView()
            } else if let loadError {
                ContentUnavailableView(
                    language.t(.couldNotLoadForm),
                    systemImage: "exclamationmark.triangle",
                    description: Text(loadError)
                )
            } else if let intro {
                ScrollView {
                    VStack(alignment: .leading, spacing: 20) {
                        VStack(alignment: .leading, spacing: 6) {
                            Text(intro.headline)
                                .font(.title2.bold())
                            if !intro.tagline.isEmpty {
                                Text(intro.tagline)
                                    .font(.subheadline)
                                    .foregroundStyle(.secondary)
                            }
                        }
                        .frame(maxWidth: .infinity)

                        if !intro.gallery.isEmpty {
                            introSectionHeading(language.t(.gallery), systemImage: "photo.on.rectangle.angled")
                            introGallery(intro.gallery)
                        }

                        if let video = intro.video, !video.watchUrl.isEmpty {
                            introVideoSection(video)
                        }

                        if !intro.messageHtml.isEmpty {
                            introSectionHeading(language.t(.about), systemImage: "text.bubble")
                            IntroHTMLBlock(html: intro.messageHtml)
                                .frame(minHeight: 40)
                        }

                        introRegistrationSection(intro)
                        introScheduleSection(intro)
                        introWhereSection(intro)
                        introContactSection(intro)
                        introHighlightsSection(intro)
                        introBrochureSection(intro)
                        introGuidelinesSection(intro)

                        if intro.closed {
                            Text(language.t(.registrationClosed))
                                .font(.subheadline)
                                .foregroundStyle(.orange)
                                .frame(maxWidth: .infinity)
                        } else if intro.canApply {
                            NavigationLink {
                                FormSubmitView(auth: auth, formId: formId, formTitle: formTitle)
                            } label: {
                                Text(intro.applyLabel.isEmpty ? language.t(.applyNow) : intro.applyLabel)
                                    .frame(maxWidth: .infinity)
                            }
                            .buttonStyle(.borderedProminent)
                        }
                    }
                    .padding()
                }
            }
        }
        .navigationTitle(formTitle)
        .navigationBarTitleDisplayMode(.inline)
        .task { await load() }
    }

    @ViewBuilder
    private func introGallery(_ items: [FormIntroGalleryItem]) -> some View {
        VStack(spacing: 8) {
            TabView(selection: $galleryIndex) {
                ForEach(Array(items.enumerated()), id: \.offset) { index, item in
                    AsyncImage(url: URL(string: item.imageUrl)) { phase in
                        switch phase {
                        case .success(let image):
                            image.resizable().scaledToFill()
                        default:
                            Color.gray.opacity(0.2)
                        }
                    }
                    .frame(height: 220)
                    .clipped()
                    .overlay(alignment: .bottom) {
                        if !item.caption.isEmpty {
                            Text(item.caption)
                                .font(.caption)
                                .foregroundStyle(.white)
                                .padding(8)
                                .frame(maxWidth: .infinity)
                                .background(.black.opacity(0.55))
                        }
                    }
                    .tag(index)
                }
            }
            .frame(height: 220)
            .tabViewStyle(.page(indexDisplayMode: items.count > 1 ? .automatic : .never))
        }
    }

    @ViewBuilder
    private func introSectionHeading(_ title: String, systemImage: String) -> some View {
        Label(title, systemImage: systemImage)
            .font(.headline)
    }

    private func introVideoSection(_ video: FormIntroVideo) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            introSectionHeading(language.t(.featuredVideo), systemImage: "play.rectangle.fill")
            if !video.embedUrl.isEmpty, let url = URL(string: video.embedUrl) {
                Link(destination: url) {
                    Label(language.t(.openVideo), systemImage: "play.rectangle")
                }
            } else if let url = URL(string: video.watchUrl) {
                Link(destination: url) {
                    Label(language.t(.openVideo), systemImage: "play.rectangle")
                }
            }
        }
    }

    @ViewBuilder
    private func introRegistrationSection(_ intro: FormIntroPayload) -> some View {
        let hasReg = !intro.registerBy.label.isEmpty || !intro.registration.fee.isEmpty
            || (intro.registration.showCapacity && intro.registration.capacity != nil)
        if hasReg {
            VStack(alignment: .leading, spacing: 8) {
                introSectionHeading(language.t(.registrationInfo), systemImage: "doc.text.fill")
                if !intro.registerBy.label.isEmpty {
                    introRow(language.t(.registerBy), intro.registerBy.label)
                }
                if !intro.registration.fee.isEmpty {
                    introRow(language.t(.fee), intro.registration.fee)
                }
                if intro.registration.showCapacity, let cap = intro.registration.capacity {
                    let seats = intro.registration.seatsRemaining.map { "\($0) / \(cap)" } ?? "\(cap)"
                    introRow(language.t(.capacity), seats)
                }
            }
        }
    }

    @ViewBuilder
    private func introScheduleSection(_ intro: FormIntroPayload) -> some View {
        if !intro.schedule.startsLabel.isEmpty || !intro.schedule.endsLabel.isEmpty {
            VStack(alignment: .leading, spacing: 8) {
                introSectionHeading(language.t(.schedule), systemImage: "calendar")
                if !intro.schedule.startsLabel.isEmpty {
                    introRow(language.t(.starts), intro.schedule.startsLabel)
                }
                if !intro.schedule.endsLabel.isEmpty {
                    introRow(language.t(.ends), intro.schedule.endsLabel)
                }
            }
        }
    }

    @ViewBuilder
    private func introWhereSection(_ intro: FormIntroPayload) -> some View {
        let w = intro.whereInfo
        if !w.formatLabel.isEmpty || !w.location.isEmpty || !w.mapUrl.isEmpty {
            VStack(alignment: .leading, spacing: 8) {
                introSectionHeading(language.t(.whereSection), systemImage: "mappin.and.ellipse")
                if !w.formatLabel.isEmpty { introRow(language.t(.format), w.formatLabel) }
                if !w.location.isEmpty { introRow(language.t(.location), w.location) }
                if let url = URL(string: w.mapUrl), !w.mapUrl.isEmpty {
                    Link(language.t(.viewOnMap), destination: url)
                }
            }
        }
    }

    @ViewBuilder
    private func introContactSection(_ intro: FormIntroPayload) -> some View {
        let c = intro.contact
        if !c.name.isEmpty || !c.email.isEmpty || !c.phone.isEmpty {
            VStack(alignment: .leading, spacing: 8) {
                introSectionHeading(language.t(.getInTouch), systemImage: "person.crop.circle")
                if !c.name.isEmpty { introRow(language.t(.contact), c.name) }
                if !c.email.isEmpty {
                    Link(c.email, destination: URL(string: "mailto:\(c.email)")!)
                }
                if !c.phone.isEmpty {
                    Link(c.phone, destination: URL(string: "tel:\(c.phone.filter { !$0.isWhitespace })")!)
                }
            }
        }
    }

    @ViewBuilder
    private func introHighlightsSection(_ intro: FormIntroPayload) -> some View {
        if !intro.highlights.isEmpty {
            VStack(alignment: .leading, spacing: 8) {
                introSectionHeading(language.t(.highlights), systemImage: "sparkles")
                ForEach(Array(intro.highlights.enumerated()), id: \.offset) { index, item in
                    if intro.highlightsListStyle == "ordered" {
                        Text("\(index + 1). \(item)")
                            .font(.subheadline)
                    } else {
                        Label(item, systemImage: "circle.fill")
                            .font(.caption)
                            .labelStyle(.titleAndIcon)
                    }
                }
            }
        }
    }

    @ViewBuilder
    private func introBrochureSection(_ intro: FormIntroPayload) -> some View {
        if let urlString = intro.brochureUrl, let url = URL(string: urlString) {
            Link(destination: url) {
                Label(language.t(.downloadBrochure), systemImage: "doc.fill")
            }
        }
    }

    @ViewBuilder
    private func introGuidelinesSection(_ intro: FormIntroPayload) -> some View {
        if !intro.guidelines.isEmpty {
            VStack(alignment: .leading, spacing: 8) {
                introSectionHeading(language.t(.guidelines), systemImage: "info.circle")
                ForEach(Array(intro.guidelines.enumerated()), id: \.offset) { index, rule in
                    if intro.guidelinesListStyle == "ordered" {
                        Text("\(index + 1). \(rule)")
                            .font(.subheadline)
                    } else {
                        Text("• \(rule)")
                            .font(.subheadline)
                    }
                }
            }
        }
    }

    private func introRow(_ label: String, _ value: String) -> some View {
        HStack(alignment: .top) {
            Text(label)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(.secondary)
                .frame(width: 100, alignment: .leading)
            Text(value)
                .font(.subheadline)
        }
    }

    private func load() async {
        guard let token = auth.token else { return }
        isLoading = true
        loadError = nil
        defer { isLoading = false }
        do {
            intro = try await HomeAPI.fetchFormIntro(token: token, formId: formId)
        } catch let err as APIError {
            loadError = err.message
        } catch {
            loadError = error.localizedDescription
        }
    }
}

private struct IntroHTMLBlock: UIViewRepresentable {
    let html: String

    func makeUIView(context: Context) -> WKWebView {
        let web = WKWebView()
        web.isOpaque = false
        web.backgroundColor = .clear
        web.scrollView.isScrollEnabled = false
        return web
    }

    func updateUIView(_ webView: WKWebView, context: Context) {
        let wrapped = """
        <html><head><meta name="viewport" content="width=device-width"><style>
        body{font-family:-apple-system,sans-serif;font-size:15px;line-height:1.45;margin:0;color:#222;}
        a{color:#0a5;}
        </style></head><body>\(html)</body></html>
        """
        webView.loadHTMLString(wrapped, baseURL: nil)
    }
}
