import SwiftUI

struct SignatureStroke: Equatable {
    var points: [CGPoint]
}

@MainActor
final class SignaturePadModel: ObservableObject {
    @Published private(set) var strokes: [SignatureStroke] = []
    private var undone: [SignatureStroke] = []

    var canUndo: Bool { !strokes.isEmpty }
    var isEmpty: Bool { strokes.allSatisfy { $0.points.count < 2 } }

    func beginStroke(at point: CGPoint) {
        strokes.append(SignatureStroke(points: [point]))
        undone.removeAll()
    }

    func appendPoint(_ point: CGPoint) {
        guard !strokes.isEmpty else {
            beginStroke(at: point)
            return
        }
        strokes[strokes.count - 1].points.append(point)
    }

    func endStroke() {
        if let last = strokes.last, last.points.count < 2 {
            strokes.removeLast()
        }
    }

    func undo() {
        guard let last = strokes.popLast() else { return }
        undone.append(last)
    }

    func clear() {
        strokes.removeAll()
        undone.removeAll()
    }

    func exportPNG(size: CGSize) -> Data? {
        let renderer = UIGraphicsImageRenderer(size: size)
        let image = renderer.image { ctx in
            UIColor.white.setFill()
            ctx.fill(CGRect(origin: .zero, size: size))
            ctx.cgContext.setStrokeColor(UIColor.black.cgColor)
            ctx.cgContext.setLineWidth(3)
            ctx.cgContext.setLineCap(.round)
            ctx.cgContext.setLineJoin(.round)
            for stroke in strokes where stroke.points.count > 1 {
                ctx.cgContext.beginPath()
                ctx.cgContext.move(to: stroke.points[0])
                for point in stroke.points.dropFirst() {
                    ctx.cgContext.addLine(to: point)
                }
                ctx.cgContext.strokePath()
            }
        }
        return image.pngData()
    }
}

struct SignaturePadView: View {
    @ObservedObject var model: SignaturePadModel
    @State private var isDrawing = false

    var body: some View {
        GeometryReader { geo in
            Canvas { context, _ in
                var path = Path()
                for stroke in model.strokes where stroke.points.count > 1 {
                    path.move(to: stroke.points[0])
                    for point in stroke.points.dropFirst() {
                        path.addLine(to: point)
                    }
                }
                context.stroke(
                    path,
                    with: .color(.primary),
                    style: StrokeStyle(lineWidth: 3, lineCap: .round, lineJoin: .round)
                )
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(Color(.systemBackground))
            .overlay(
                RoundedRectangle(cornerRadius: 12)
                    .strokeBorder(Color.secondary.opacity(0.35), lineWidth: 1)
            )
            .clipShape(RoundedRectangle(cornerRadius: 12))
            .contentShape(Rectangle())
            .gesture(
                DragGesture(minimumDistance: 0)
                    .onChanged { value in
                        let point = value.location
                        if !isDrawing {
                            isDrawing = true
                            model.beginStroke(at: point)
                        } else {
                            model.appendPoint(point)
                        }
                    }
                    .onEnded { _ in
                        isDrawing = false
                        model.endStroke()
                    }
            )
            .background(
                GeometryReader { proxy in
                    Color.clear.preference(key: SignaturePadSizeKey.self, value: proxy.size)
                }
            )
        }
        .aspectRatio(2.2, contentMode: .fit)
    }
}

private struct SignaturePadSizeKey: PreferenceKey {
    static var defaultValue: CGSize = .zero
    static func reduce(value: inout CGSize, nextValue: () -> CGSize) {
        value = nextValue()
    }
}

extension SignaturePadView {
    func onPadSizeChange(_ action: @escaping (CGSize) -> Void) -> some View {
        onPreferenceChange(SignaturePadSizeKey.self, perform: action)
    }
}
