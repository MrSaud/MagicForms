import PDFKit
import QuickLook
import SwiftUI

struct DocumentPreviewView: View {
    let title: String
    let url: URL
    let bearerToken: String
    let filename: String

    @State private var pdfDocument: PDFDocument?
    @State private var loadError: String?
    @State private var isLoading = true
    @State private var previewURL: URL?

    var body: some View {
        Group {
            if isLoading {
                ProgressView()
            } else if let pdfDocument {
                PDFKitRepresentedView(document: pdfDocument)
            } else if let previewURL {
                QuickLookPreview(url: previewURL)
            } else {
                ContentUnavailableView(
                    "Could not open document",
                    systemImage: "doc",
                    description: Text(loadError ?? "Unsupported format on this device.")
                )
            }
        }
        .navigationTitle(title)
        .navigationBarTitleDisplayMode(.inline)
        .task { await load() }
    }

    private func load() async {
        isLoading = true
        loadError = nil
        defer { isLoading = false }
        var request = URLRequest(url: url)
        request.setValue("Bearer \(bearerToken)", forHTTPHeaderField: "Authorization")
        request.setValue(AppLanguage.currentAcceptLanguage, forHTTPHeaderField: "Accept-Language")
        do {
            let (data, response) = try await URLSession.shared.data(for: request)
            guard let http = response as? HTTPURLResponse, (200 ..< 300).contains(http.statusCode) else {
                loadError = "Download failed."
                return
            }
            let lower = filename.lowercased()
            if lower.hasSuffix(".pdf") || url.absoluteString.contains("/pdf") {
                if let doc = PDFDocument(data: data) {
                    pdfDocument = doc
                    return
                }
            }
            let temp = FileManager.default.temporaryDirectory
                .appendingPathComponent(filename.isEmpty ? "document.bin" : filename)
            try data.write(to: temp)
            previewURL = temp
        } catch {
            loadError = error.localizedDescription
        }
    }
}

private struct PDFKitRepresentedView: UIViewRepresentable {
    let document: PDFDocument

    func makeUIView(context: Context) -> PDFView {
        let view = PDFView()
        view.autoScales = true
        view.displayMode = .singlePageContinuous
        view.displayDirection = .vertical
        view.document = document
        return view
    }

    func updateUIView(_ uiView: PDFView, context: Context) {
        uiView.document = document
    }
}

private struct QuickLookPreview: UIViewControllerRepresentable {
    let url: URL

    func makeUIViewController(context: Context) -> QLPreviewController {
        let controller = QLPreviewController()
        controller.dataSource = context.coordinator
        return controller
    }

    func updateUIViewController(_ uiViewController: QLPreviewController, context: Context) {}

    func makeCoordinator() -> Coordinator {
        Coordinator(url: url)
    }

    final class Coordinator: NSObject, QLPreviewControllerDataSource {
        let url: URL
        init(url: URL) { self.url = url }
        func numberOfPreviewItems(in controller: QLPreviewController) -> Int { 1 }
        func previewController(_ controller: QLPreviewController, previewItemAt index: Int) -> QLPreviewItem {
            url as NSURL
        }
    }
}
