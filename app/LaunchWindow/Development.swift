#if DEBUG
import Foundation
import SwiftUI
#if os(macOS)
import AppKit
import ImageIO
import UniformTypeIdentifiers
#endif

/// Two command-line development aids, both DEBUG-only. The probe runs
/// anywhere; the gallery needs AppKit and so is macOS-only.
///
/// They exist because the two things most easily got wrong here are the hardest
/// to look at from a terminal: a widget cannot be run on its own, and the
/// network path is guarded by transport-security and local-network policy that
/// only bite on a real device.
///
///     LW_PROBE=launch-window.home open -a LaunchWindow     # read once, print, exit
///     LW_GALLERY=1 ./LaunchWindow                          # render every size to PNG
///
/// Both print a line and call `exit`, so neither can be triggered by accident
/// from the UI.
@MainActor
enum Development {
    static func runIfRequested() {
        if let host = ProcessInfo.processInfo.environment["LW_PROBE"] {
            probe(host: host)
        }
        #if os(macOS)
        if ProcessInfo.processInfo.environment["LW_GALLERY"] != nil {
            renderGallery()
        }
        #endif
    }

    // MARK: - Probe

    /// Reads the beacon once and prints what came back, or why nothing did.
    private static func probe(host: String) {
        let semaphore = DispatchSemaphore(value: 0)
        nonisolated(unsafe) var lines: [String] = ["PROBE no result"]
        Task.detached {
            let snapshot = await BeaconLoader.load(host: host, timeout: 15)
            let group = SharedStore.appGroup ?? "none"
            let container = SharedStore.appGroup.flatMap {
                FileManager.default.containerURL(forSecurityApplicationGroupIdentifier: $0)?.path
            } ?? "-"
            let bare = host.replacingOccurrences(of: "http://", with: "")
                .split(separator: "/").first.map(String.init) ?? host
            let name = bare.split(separator: ":").first.map(String.init) ?? bare
            let addresses = IPAddress.resolve(name)
            let described = addresses.isEmpty ? "(none)" : addresses
                .map { "\($0.text)\($0.isPrivate ? " private" : " public")" }
                .joined(separator: ", ")
            let chosen = SharedStore.nightVision.map(String.init(describing:)) ?? "unset"
            lines = [
                "PROBE resolves \(name) → \(described)",
                "PROBE group=\(group)",
                "      container=\(container)",
                "      sharing=\(SharedStore.isSharing)",
                "      astro.nightVision=\(chosen) → this app draws "
                    + (SharedStore.prefersNightVision ? "red on black" : "in colour"),
            ]
            if let document = snapshot.document, snapshot.origin == .live {
                let window = document.verdict.window.map {
                    " window=\($0.startLocal ?? "?")–\($0.endLocal ?? "?")"
                } ?? ""
                lines.append("PROBE ok host=\(host) verdict=\(document.verdict.state.rawValue)"
                    + " score=\(document.verdict.score.map { String(format: "%.1f", $0) } ?? "nil")"
                    + " hours=\(document.verdict.hours.count) stale=\(document.data.stale)"
                    + window)
            } else {
                lines.append("PROBE failed host=\(host): \(snapshot.failure?.message ?? "unknown")")
            }
            semaphore.signal()
        }
        semaphore.wait()
        report(lines)
        exit(0)
    }

    /// Printed, and also written to a file.
    ///
    /// On iOS the process is gone before anything has attached to its stdout —
    /// the probe runs from `App.init` and exits — so `simctl launch --console`
    /// captures nothing. The file survives, and
    /// `simctl get_app_container booted <id> data` says where to find it.
    private static func report(_ lines: [String]) {
        let text = lines.joined(separator: "\n")
        print(text)
        let directory = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first
            ?? URL(fileURLWithPath: NSTemporaryDirectory())
        let file = directory.appendingPathComponent("probe.txt")
        try? (text + "\n").write(to: file, atomically: true, encoding: .utf8)
        print("PROBE written to \(file.path)")
    }

    #if os(macOS)

    // MARK: - Gallery

    /// Point sizes as the two hosts actually lay them out, with the content
    /// margin each applies.
    private static let sizes: [(String, CGSize, CGFloat)] = [
        ("ios-small", CGSize(width: 170, height: 170), 16),
        ("ios-medium", CGSize(width: 364, height: 170), 16),
        ("ios-large", CGSize(width: 364, height: 382), 16),
        ("ios-extralarge", CGSize(width: 748, height: 382), 16),
        ("mac-small", CGSize(width: 155, height: 155), 12),
        ("mac-medium", CGSize(width: 329, height: 155), 12),
        ("mac-large", CGSize(width: 329, height: 345), 12),
    ]

    private static func renderGallery() {
        let directory = URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent("gallery")
        try? FileManager.default.removeItem(at: directory)
        try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)

        for (state, snapshot, palette) in cases {
            for (name, size, margin) in sizes {
                let view = ZStack {
                    palette.background
                    layout(named: name, snapshot: snapshot, palette: palette)
                        .padding(margin)
                }
                .frame(width: size.width, height: size.height)
                write(view, to: directory.appendingPathComponent("\(state)-\(name).png"), size: size)
            }
            // The app screen too: it is the same vocabulary at a fourth size,
            // and the place a layout regression is easiest to see.
            // `panels` rather than the whole screen: ImageRenderer can host
            // neither a NavigationStack nor a ScrollView, and neither is what
            // regresses. The panels are.
            let screen = ZStack(alignment: .top) {
                palette.background
                TonightView(model: BeaconModel(showing: snapshot)).panels
            }
            .frame(width: 460, height: 1120)
            write(screen, to: directory.appendingPathComponent("\(state)-app.png"),
                  size: CGSize(width: 460, height: 1120))
        }
        print("GALLERY \(directory.path)")
        exit(0)
    }

    private static var cases: [(String, BeaconSnapshot, Palette)] {
        [
            ("go", SampleBeacon.snapshot(SampleBeacon.go), .day),
            ("nogo", SampleBeacon.snapshot(SampleBeacon.noGo), .day),
            ("unknown", SampleBeacon.snapshot(SampleBeacon.unknown), .day),
            ("night", SampleBeacon.snapshot(SampleBeacon.noGo), .night),
            ("replayed", replayed, .day),
            ("unreachable", unreachable, .day),
        ]
    }

    @ViewBuilder
    private static func layout(named name: String,
                               snapshot: BeaconSnapshot,
                               palette: Palette) -> some View {
        if name.hasSuffix("extralarge") {
            ExtraLargeVerdict(snapshot: snapshot, palette: palette)
        } else if name.hasSuffix("large") {
            LargeVerdict(snapshot: snapshot, palette: palette)
        } else if name.hasSuffix("medium") {
            MediumVerdict(snapshot: snapshot, palette: palette)
        } else {
            SmallVerdict(snapshot: snapshot, palette: palette)
        }
    }

    /// A good night, shown after the beacon stopped answering.
    private static var replayed: BeaconSnapshot {
        BeaconSnapshot(document: SampleBeacon.go,
                       retrievedAt: Date().addingTimeInterval(-9000),
                       host: SharedStore.defaultHost,
                       failure: .unreachable(String(localized: "error.dns",
                                                    defaultValue: "the name does not resolve")),
                       origin: .cache)
    }

    /// No document at all, failing the way the hardware actually failed on the
    /// afternoon this was written: alive, answering /health, out of contiguous
    /// heap for the document itself.
    private static var unreachable: BeaconSnapshot {
        BeaconSnapshot(document: nil, retrievedAt: nil, host: "launch-window.home",
                       failure: .httpStatus(code: 500,
                                            body: "handler failed: memory allocation failed, allocating 4088 bytes"),
                       origin: .cache)
    }

    private static func write(_ view: some View, to url: URL, size: CGSize) {
        let renderer = ImageRenderer(content: view.environment(\.colorScheme, .dark))
        renderer.scale = 2
        renderer.proposedSize = ProposedViewSize(size)
        guard let image = renderer.cgImage,
              let destination = CGImageDestinationCreateWithURL(
                url as CFURL, UTType.png.identifier as CFString, 1, nil)
        else { return }
        CGImageDestinationAddImage(destination, image, nil)
        CGImageDestinationFinalize(destination)
    }
    #endif
}

#endif
