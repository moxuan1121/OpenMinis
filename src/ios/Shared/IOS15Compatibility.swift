import SwiftUI
import PhotosUI
import UniformTypeIdentifiers

/// Keeps the existing navigation implementation on iOS 16 and later.
struct MinisNavigationStack<Content: View>: View {
    private let content: Content
    init(@ViewBuilder content: () -> Content) { self.content = content() }

    @ViewBuilder var body: some View {
        if #available(iOS 16.0, *) {
            NavigationStack { content }
        } else {
            NavigationView { content }.navigationViewStyle(.stack)
        }
    }
}

struct MinisPathNavigationStack<Value: Hashable, Root: View, Destination: View>: View {
    @Binding var path: [Value]
    let root: Root
    let destination: (Value) -> Destination

    init(path: Binding<[Value]>, @ViewBuilder content: () -> Root,
         @ViewBuilder destination: @escaping (Value) -> Destination) {
        _path = path
        root = content()
        self.destination = destination
    }

    @ViewBuilder var body: some View {
        if #available(iOS 16.0, *) {
            NavigationStack(path: $path) {
                root.navigationDestination(for: Value.self, destination: destination)
            }
        } else {
            NavigationView {
                LegacyPathNode(path: $path, depth: 0, content: AnyView(root),
                               destination: { AnyView(destination($0)) })
            }
            .navigationViewStyle(.stack)
        }
    }
}

private struct LegacyPathNode<Value: Hashable>: View {
    @Binding var path: [Value]
    let depth: Int
    let content: AnyView
    let destination: (Value) -> AnyView

    private var active: Binding<Bool> {
        Binding(get: { path.count > depth }, set: { pushed in
            if !pushed, path.count > depth { path.removeSubrange(depth...) }
        })
    }

    private var next: AnyView {
        guard path.indices.contains(depth) else { return AnyView(EmptyView()) }
        let value = path[depth]
        return AnyView(LegacyPathNode(path: $path, depth: depth + 1,
            content: AnyView(destination(value).id(value)), destination: destination))
    }

    var body: some View {
        content.background(NavigationLink(destination: next, isActive: active) { EmptyView() }
            .hidden().accessibilityHidden(true))
    }
}

struct MinisLabeledContent<Content: View, Label: View>: View {
    let content: Content
    let label: Label
    init(@ViewBuilder content: () -> Content, @ViewBuilder label: () -> Label) {
        self.content = content()
        self.label = label()
    }
    @ViewBuilder var body: some View {
        if #available(iOS 16.0, *) {
            LabeledContent { content } label: { label }
        } else {
            HStack { label; Spacer(); content.foregroundStyle(.secondary) }
                .accessibilityElement(children: .combine)
        }
    }
}

extension MinisLabeledContent where Label == Text {
    init(_ title: LocalizedStringKey, @ViewBuilder content: () -> Content) {
        self.content = content(); label = Text(title)
    }
    init<S: StringProtocol>(_ title: S, @ViewBuilder content: () -> Content) {
        self.content = content(); label = Text(title)
    }
}

extension MinisLabeledContent where Label == Text, Content == Text {
    init(_ title: LocalizedStringKey, value: String) {
        content = Text(value); label = Text(title)
    }
    init<S: StringProtocol>(_ title: S, value: String) {
        content = Text(value); label = Text(title)
    }
}

struct MinisMultilineTextField: View {
    let title: Text
    @Binding var text: String
    init(_ title: LocalizedStringKey, text: Binding<String>) {
        self.title = Text(title); _text = text
    }
    init<S: StringProtocol>(_ title: S, text: Binding<String>) {
        self.title = Text(title); _text = text
    }
    @ViewBuilder var body: some View {
        if #available(iOS 16.0, *) {
            TextField(text: $text, axis: .vertical) { title }
        } else {
            TextEditor(text: $text).accessibilityLabel(title).frame(minHeight: 44)
        }
    }
}

enum MinisPresentationDetent: Hashable {
    case medium, large, fraction(CGFloat), height(CGFloat)
    @available(iOS 16.0, *) var native: PresentationDetent {
        switch self {
        case .medium: return .medium
        case .large: return .large
        case .fraction(let value): return .fraction(value)
        case .height(let value): return .height(value)
        }
    }
    var legacy: UISheetPresentationController.Detent {
        // ponytail: iOS 15 only has medium/large detents; custom heights use
        // the nearest system size until a custom presentation is required.
        switch self {
        case .medium: return .medium()
        case .large: return .large()
        case .fraction(let value): return value <= 0.5 ? .medium() : .large()
        case .height(let value): return value <= UIScreen.main.bounds.height / 2 ? .medium() : .large()
        }
    }
}

private struct LegacySheetConfiguration: UIViewControllerRepresentable {
    var detents: Set<MinisPresentationDetent>?
    var grabber: Bool?

    final class Controller: UIViewController {
        var configure: ((UISheetPresentationController) -> Void)?
        override func viewWillAppear(_ animated: Bool) {
            super.viewWillAppear(animated)
            apply()
        }
        func apply() {
            var controller: UIViewController? = self
            while let current = controller {
                if let sheet = current.sheetPresentationController, current.presentingViewController != nil {
                    configure?(sheet)
                    return
                }
                controller = current.parent
            }
        }
    }
    func makeUIViewController(context: Context) -> Controller { Controller() }
    func updateUIViewController(_ controller: Controller, context: Context) {
        controller.configure = { sheet in
            if let detents {
                let mapped = detents.map(\.legacy)
                let medium = mapped.contains { $0.identifier == .medium }
                let large = mapped.contains { $0.identifier == .large }
                sheet.detents = (medium ? [.medium()] : []) + (large ? [.large()] : [])
            }
            if let grabber { sheet.prefersGrabberVisible = grabber }
        }
        controller.apply()
    }
}

enum MinisToolbarPlacement { case navigationBar }
enum MinisKeyboardDismissMode { case interactively }

extension View {
    @ViewBuilder func minisPresentationDetents(_ detents: Set<MinisPresentationDetent>) -> some View {
        if #available(iOS 16.0, *) {
            presentationDetents(Set(detents.map(\.native)))
        } else {
            background(LegacySheetConfiguration(detents: detents))
        }
    }
    @ViewBuilder func minisPresentationDetents(_ detents: Set<MinisPresentationDetent>,
                                               selection: Binding<MinisPresentationDetent>) -> some View {
        if #available(iOS 16.0, *) {
            presentationDetents(Set(detents.map(\.native)), selection: Binding(
                get: { selection.wrappedValue.native },
                set: { value in
                    if let found = detents.first(where: { $0.native == value }) { selection.wrappedValue = found }
                }))
        } else {
            minisPresentationDetents(detents)
        }
    }
    @ViewBuilder func minisPresentationDragIndicator(_ visibility: Visibility) -> some View {
        if #available(iOS 16.0, *) { presentationDragIndicator(visibility) }
        else { background(LegacySheetConfiguration(grabber: visibility == .visible)) }
    }
    @ViewBuilder func minisScrollContentBackground(_ visibility: Visibility) -> some View {
        if #available(iOS 16.0, *) { scrollContentBackground(visibility) }
        else { self }
    }
    @ViewBuilder func minisScrollDismissesKeyboard(_ mode: MinisKeyboardDismissMode) -> some View {
        if #available(iOS 16.0, *) { scrollDismissesKeyboard(.interactively) }
        else { self }
    }
    @ViewBuilder func minisToolbarBackground<S: ShapeStyle>(_ style: S, for placement: MinisToolbarPlacement) -> some View {
        if #available(iOS 16.0, *) { toolbarBackground(style, for: .navigationBar) }
        else { self }
    }
    @ViewBuilder func minisToolbarBackground(_ visibility: Visibility, for placement: MinisToolbarPlacement) -> some View {
        if #available(iOS 16.0, *) { toolbarBackground(visibility, for: .navigationBar) }
        else { self }
    }
    @ViewBuilder func minisLineLimit(_ range: ClosedRange<Int>) -> some View {
        if #available(iOS 16.0, *) { lineLimit(range) }
        else { frame(minHeight: CGFloat(range.lowerBound) * 20, maxHeight: CGFloat(range.upperBound) * 24) }
    }
    @ViewBuilder func minisDraggable(_ value: String) -> some View {
        if #available(iOS 16.0, *) { draggable(value) }
        else { onDrag { NSItemProvider(object: value as NSString) } }
    }
}

struct MinisShareLink: View {
    let item: URL
    @State private var presented = false
    var body: some View {
        Button { presented = true } label: { Label("Share", systemImage: "square.and.arrow.up") }
            .sheet(isPresented: $presented) { ActivityShareSheet(items: [item]) }
    }
}

private struct ActivityShareSheet: UIViewControllerRepresentable {
    let items: [Any]
    func makeUIViewController(context: Context) -> UIActivityViewController {
        UIActivityViewController(activityItems: items, applicationActivities: nil)
    }
    func updateUIViewController(_ controller: UIActivityViewController, context: Context) {}
}

/// Either the SwiftUI picker item or its iOS 15 PHPicker equivalent.
struct MinisPhotoItem: Equatable, @unchecked Sendable {
    let id = UUID()
    let itemIdentifier: String?
    let supportedContentTypes: [UTType]
    private let provider: NSItemProvider?
    private let native: Any?
    static func == (lhs: Self, rhs: Self) -> Bool { lhs.id == rhs.id }
    init(_ result: PHPickerResult) {
        itemIdentifier = result.assetIdentifier
        provider = result.itemProvider
        supportedContentTypes = result.itemProvider.registeredTypeIdentifiers.compactMap(UTType.init)
        native = nil
    }
    @available(iOS 16.0, *) init(_ item: PhotosPickerItem) {
        itemIdentifier = item.itemIdentifier
        supportedContentTypes = item.supportedContentTypes
        native = item
        provider = nil
    }
    func loadData() async throws -> Data {
        if #available(iOS 16.0, *), let item = native as? PhotosPickerItem,
           let data = try await item.loadTransferable(type: Data.self) { return data }
        guard let provider, let type = supportedContentTypes.first(where: { $0.conforms(to: .image) }) else {
            throw CocoaError(.fileReadCorruptFile)
        }
        return try await withCheckedThrowingContinuation { continuation in
            provider.loadDataRepresentation(forTypeIdentifier: type.identifier) { data, error in
                if let data { continuation.resume(returning: data) }
                else { continuation.resume(throwing: error ?? CocoaError(.fileReadCorruptFile)) }
            }
        }
    }
    func loadVideo() async throws -> MinisPickedVideo {
        if #available(iOS 16.0, *), let item = native as? PhotosPickerItem,
           let video = try await item.loadTransferable(type: VideoFileTransferable.self) {
            return MinisPickedVideo(url: video.url)
        }
        guard let provider else { throw CocoaError(.fileReadCorruptFile) }
        return try await withCheckedThrowingContinuation { continuation in
            provider.loadFileRepresentation(forTypeIdentifier: UTType.movie.identifier) { url, error in
                guard let url else {
                    continuation.resume(throwing: error ?? CocoaError(.fileReadCorruptFile)); return
                }
                do {
                    let copy = FileManager.default.temporaryDirectory
                        .appendingPathComponent(UUID().uuidString + "_" + url.lastPathComponent)
                    try FileManager.default.copyItem(at: url, to: copy)
                    continuation.resume(returning: MinisPickedVideo(url: copy))
                } catch { continuation.resume(throwing: error) }
            }
        }
    }
}

struct MinisPickedVideo: Sendable { let url: URL }

private struct LegacyPhotosPicker: UIViewControllerRepresentable {
    let limit: Int
    let filter: PHPickerFilter
    let selection: Binding<[MinisPhotoItem]>
    let presented: Binding<Bool>
    func makeUIViewController(context: Context) -> PHPickerViewController {
        var configuration = PHPickerConfiguration(photoLibrary: .shared())
        configuration.selectionLimit = limit
        configuration.filter = filter
        configuration.preferredAssetRepresentationMode = .current
        configuration.selection = .ordered
        let picker = PHPickerViewController(configuration: configuration)
        picker.delegate = context.coordinator
        return picker
    }
    func updateUIViewController(_ controller: PHPickerViewController, context: Context) {}
    func makeCoordinator() -> Coordinator { Coordinator(self) }
    final class Coordinator: NSObject, PHPickerViewControllerDelegate {
        let parent: LegacyPhotosPicker
        init(_ parent: LegacyPhotosPicker) { self.parent = parent }
        func picker(_ picker: PHPickerViewController, didFinishPicking results: [PHPickerResult]) {
            parent.presented.wrappedValue = false
            parent.selection.wrappedValue = results.map(MinisPhotoItem.init)
        }
    }
}

@available(iOS 16.0, *)
private struct ModernPhotosPickerModifier: ViewModifier {
    @Binding var presented: Bool
    @Binding var selection: [MinisPhotoItem]
    let limit: Int
    let filter: PHPickerFilter
    @State private var items: [PhotosPickerItem] = []
    func body(content: Content) -> some View {
        content.photosPicker(isPresented: $presented, selection: $items,
            maxSelectionCount: limit, matching: filter, photoLibrary: .shared())
            .onChange(of: items) { value in
                guard !value.isEmpty else { return }
                selection = value.map(MinisPhotoItem.init)
                items = []
            }
    }
}

extension View {
    @ViewBuilder func minisPhotosPicker(isPresented: Binding<Bool>, selection: Binding<[MinisPhotoItem]>,
                                        maxSelectionCount: Int, matching: PHPickerFilter) -> some View {
        if #available(iOS 16.0, *) {
            modifier(ModernPhotosPickerModifier(presented: isPresented, selection: selection,
                limit: maxSelectionCount, filter: matching))
        } else {
            sheet(isPresented: isPresented) {
                LegacyPhotosPicker(limit: maxSelectionCount, filter: matching,
                    selection: selection, presented: isPresented)
            }
        }
    }
    func minisPhotosPicker(isPresented: Binding<Bool>, selection: Binding<MinisPhotoItem?>,
                            matching: PHPickerFilter, photoLibrary: PHPhotoLibrary) -> some View {
        minisPhotosPicker(isPresented: isPresented, selection: Binding(
            get: { selection.wrappedValue.map { [$0] } ?? [] },
            set: { selection.wrappedValue = $0.first }), maxSelectionCount: 1, matching: matching)
    }
}
