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
        if let spec = ProcessInfo.processInfo.environment["LW_SKY"] {
            dumpSky(spec)
        }
        if let host = ProcessInfo.processInfo.environment["LW_SELFCHECK"] {
            selfCheck(host: host)
        }
        if let json = ProcessInfo.processInfo.environment["LW_VERDICT"] {
            dumpVerdict(json)
        }
        if let spec = ProcessInfo.processInfo.environment["LW_OUTLOOK"] {
            dumpOutlook(spec)
        }
        #if os(macOS)
        if ProcessInfo.processInfo.environment["LW_GALLERY"] != nil {
            renderGallery()
        }
        #endif
    }

    // MARK: - Outlook

    /// The whole proof of concept, end to end: read the beacon for the site and
    /// for tonight, fetch several days of forecast, grade every night, and
    /// report both the outlook and whether the engine still agrees with the
    /// device about the one night they both know.
    ///
    /// `LW_OUTLOOK=<host>:<nights>`
    private static func dumpOutlook(_ spec: String) {
        let parts = spec.split(separator: ":").map(String.init)
        let host = parts.first ?? SharedStore.defaultHost
        let nights = parts.count > 1 ? (Int(parts[1]) ?? 5) : 5

        let semaphore = DispatchSemaphore(value: 0)
        nonisolated(unsafe) var lines: [String] = ["OUTLOOK no result"]
        Task.detached {
            let snapshot = await BeaconLoader.load(host: host, timeout: 15)
            guard let document = snapshot.document else {
                lines = ["OUTLOOK unreachable: \(snapshot.failure?.message ?? "unknown")"]
                semaphore.signal()
                return
            }
            let check = OutlookEngine.selfCheck(document: document)
            var out = ["OUTLOOK site=\(document.site.name ?? "?") "
                       + "\(document.site.latitude),\(document.site.longitude) "
                       + "selfcheck=\(check.agrees ? "AGREE" : "DISAGREE")"]
            for difference in check.differences { out.append("  DIFF \(difference)") }

            do {
                let client = OpenMeteo(latitude: document.site.latitude,
                                       longitude: document.site.longitude)
                let rows = try await client.hourly(days: nights + 1)
                out.append("  fetched \(rows.count) hourly rows")
                let outlook = OutlookEngine.outlook(rows: rows,
                                                    latitude: document.site.latitude,
                                                    longitude: document.site.longitude,
                                                    nights: nights)
                let formatter = DateFormatter()
                formatter.dateFormat = "EEE dd MMM"
                formatter.timeZone = document.site.timeZone ?? .current
                let clock = DateFormatter()
                clock.dateFormat = "HH:mm"
                clock.timeZone = document.site.timeZone ?? .current

                for night in outlook {
                    let window = night.verdict.window.map {
                        "\(clock.string(from: $0.start ?? .distantPast))–\(clock.string(from: $0.end ?? .distantPast))"
                            + " \(String(format: "%.1f", $0.hours)) h"
                    } ?? "—"
                    let dark = night.darkStart.map { clock.string(from: $0) } ?? "—"
                    // Built by hand rather than with a format string: `%s`
                    // wants a C string and a Swift String is not one, which is
                    // a crash rather than a wrong column.
                    func pad(_ text: String, _ width: Int) -> String {
                        text.count >= width ? text
                            : text + String(repeating: " ", count: width - text.count)
                    }
                    let score = night.verdict.score.map { String(format: "%.1f", $0) } ?? "—"
                    let illumination = String(format: "%.0f", night.moonIllumination * 100)
                    out.append("  " + pad(formatter.string(from: night.evening), 12)
                               + pad(night.verdict.state.rawValue.uppercased(), 9)
                               + pad("score=" + score, 12)
                               + pad("window=" + window, 26)
                               + pad("dark " + dark, 11)
                               + "moon " + illumination + "% " + night.moonPhase)
                }
            } catch {
                out.append("  forecast failed: \((error as? OpenMeteo.Failure)?.message ?? "\(error)")")
            }
            lines = out
            semaphore.signal()
        }
        semaphore.wait()
        report(lines)
        exit(0)
    }

    // MARK: - Verdict

    /// Grades one night described by a JSON document and prints the result as JSON,
    /// so `app/tools/compare-verdict.py` can put this engine and
    /// `firmware/lib/verdict.py` side by side over cases the real sky is not
    /// currently offering — a moonlit night, a gusty one, a night that clears
    /// at three.
    /// The case arrives in the environment rather than as a file path: this
    /// app is sandboxed, so it cannot read one the harness wrote elsewhere.
    private static func dumpVerdict(_ json: String) {
        let data = Data(json.utf8)
        let parsed = try? JSONSerialization.jsonObject(with: data)
        guard let input = parsed as? [String: Any] else {
            print("VERDICT not a JSON object")
            exit(2)
        }
        // JSON numbers arrive as NSNumber whatever they looked like in the
        // file, so `0` and `0.0` must both read as a Double. Casting straight
        // to Double silently drops every whole number.
        func number(_ any: Any?) -> Double? { (any as? NSNumber)?.doubleValue }
        guard let latitude = number(input["lat"]),
              let longitude = number(input["lon"]),
              let reference = number(input["reference"]).map({ Int($0) }),
              let rawHours = input["hours"] as? [[String: Any]]
        else {
            print("VERDICT missing fields: keys=\(Array(input.keys).sorted())")
            exit(2)
        }

        let rows = rawHours.map { raw in
            VerdictEngine.Row(timestamp: number(raw["ts"]).map { Int($0) } ?? 0,
                              cloudCover: number(raw["cloud_cover"]),
                              cloudCoverHigh: number(raw["cloud_cover_high"]),
                              windGusts: number(raw["wind_gusts_10m"]),
                              temperature: number(raw["temperature_2m"]),
                              dewPoint: number(raw["dew_point_2m"]),
                              precipitationProbability: number(raw["precipitation_probability"]))
        }
        let outlook = OutlookEngine.grade(reference: reference, leadDays: 0, rows: rows,
                                          latitude: latitude, longitude: longitude)
        let verdict = outlook.verdict

        var window: Any = NSNull()
        if let w = verdict.window {
            window = ["hours": w.hours,
                      "mean_score": w.meanScore ?? 0,
                      "start": Int(w.start?.timeIntervalSince1970 ?? 0),
                      "end": Int(w.end?.timeIntervalSince1970 ?? 0)] as [String: Any]
        }
        let hours: [[String: Any]] = verdict.hours.map { hour in
            ["ts": Int(hour.timestamp),
             "score": hour.score ?? NSNull(),
             "veto": hour.veto ?? NSNull(),
             "moon_alt_deg": hour.moonAltitudeDegrees ?? NSNull(),
             "penalties": hour.penalties] as [String: Any]
        }
        let payload: [String: Any] = [
            "state": verdict.state.rawValue,
            "score": verdict.score ?? NSNull(),
            "darkness": String(describing: outlook.darkness),
            "reasons": verdict.reasons,
            "window": window,
            "hours": hours,
        ]
        let encoded = try? JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys])
        print("VERDICT " + (encoded.flatMap { String(data: $0, encoding: .utf8) } ?? "{}"))
        exit(0)
    }

    // MARK: - Self-check

    /// Regrades the beacon's own night with this client's engine and reports
    /// every disagreement. The one test that matters for the outlook: if the
    /// ports cannot reproduce a verdict the device already published, they have
    /// no business projecting the nights after it.
    private static func selfCheck(host: String) {
        let semaphore = DispatchSemaphore(value: 0)
        nonisolated(unsafe) var lines: [String] = ["SELFCHECK no result"]
        Task.detached {
            let snapshot = await BeaconLoader.load(host: host, timeout: 15)
            guard let document = snapshot.document else {
                lines = ["SELFCHECK unreachable: \(snapshot.failure?.message ?? "unknown")"]
                semaphore.signal()
                return
            }
            let check = OutlookEngine.selfCheck(document: document)
            var out = ["SELFCHECK \(check.agrees ? "AGREE" : "DISAGREE") "
                       + "host=\(host) hours=\(document.verdict.hours.count)"]
            if let computed = check.computed {
                out.append("  beacon   state=\(check.reported.state.rawValue) "
                           + "score=\(check.reported.score.map { String(format: "%.1f", $0) } ?? "nil")")
                out.append("  engine   state=\(computed.state.rawValue) "
                           + "score=\(computed.score.map { String(format: "%.1f", $0) } ?? "nil")")
                out.append("  beacon   reasons: \(check.reported.reasons.joined(separator: " | "))")
                out.append("  engine   reasons: \(computed.reasons.joined(separator: " | "))")
            }
            for difference in check.differences {
                out.append("  DIFF \(difference)")
            }
            lines = out
            semaphore.signal()
        }
        semaphore.wait()
        report(lines)
        exit(0)
    }

    // MARK: - Sky

    /// Prints this client's astronomy for N nights, in a form
    /// `app/tools/compare-sky.py` can diff against `firmware/lib/sky.py`.
    ///
    /// `LW_SKY=<unix base>:<nights>:<lat>:<lon>`. The port exists to compute
    /// nights the beacon does not, which means nothing on the device can check
    /// it; the original implementation is the only oracle there is, so it is
    /// used as one.
    private static func dumpSky(_ spec: String) {
        let parts = spec.split(separator: ":").map(String.init)
        guard parts.count == 4, let base = Int(parts[0]), let nights = Int(parts[1]),
              let latitude = Double(parts[2]), let longitude = Double(parts[3])
        else {
            print("SKY bad spec, want <unix>:<nights>:<lat>:<lon>")
            exit(2)
        }
        for index in 0 ..< nights {
            let timestamp = base + index * 86400
            let night = SkyMath.night(at: timestamp, latitude: latitude, longitude: longitude)
            let moon = SkyMath.moonEvents(from: timestamp - 12 * 3600, to: timestamp + 24 * 3600,
                                          latitude: latitude, longitude: longitude)
            let reference = night.duskAstronomical ?? timestamp
            let illumination = SkyMath.moonIllumination(at: reference)
            let altitude = SkyMath.moonAltitude(at: reference,
                                                latitude: latitude,
                                                longitude: longitude)
            var fields: [String] = [String(timestamp)]
            fields.append(night.sunset.map(String.init) ?? "-")
            fields.append(night.duskAstronomical.map(String.init) ?? "-")
            fields.append(night.dawnAstronomical.map(String.init) ?? "-")
            fields.append(night.sunrise.map(String.init) ?? "-")
            fields.append(String(night.darkSeconds))
            fields.append(String(format: "%.6f", illumination))
            fields.append(SkyMath.moonPhaseName(at: reference))
            fields.append(String(format: "%.4f", altitude))
            fields.append(moon.rise.map(String.init) ?? "-")
            fields.append(moon.set.map(String.init) ?? "-")
            // Pipe-separated: a phase name contains a space.
            print("SKY " + fields.joined(separator: "|"))
        }
        exit(0)
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
            let model = BeaconModel(showing: snapshot,
                                    outlook: sampleOutlook(for: snapshot),
                                    selfCheck: snapshot.document.map { OutlookEngine.selfCheck(document: $0) })
            let screen = ZStack(alignment: .top) {
                palette.background
                TonightView(model: model).panels
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

    /// A week of nights graded from a made-up but deterministic sky, so the
    /// gallery can draw the outlook without a network.
    ///
    /// The weather is invented; the grading is not. These rows go through the
    /// same `OutlookEngine` the app uses, so a layout that survives this is a
    /// layout that has met real output.
    private static func sampleOutlook(for snapshot: BeaconSnapshot) -> [NightOutlook] {
        guard let document = snapshot.document, let start = document.night.darkStart
        else { return [] }
        // Aligned to the hour, because Open-Meteo's rows are and a window that
        // ends at 22:29 is an artefact of the generator, not of the sky.
        let base = ((Int(start.timeIntervalSince1970) - 6 * 3600) / 3600) * 3600
        var rows: [VerdictEngine.Row] = []
        for hour in 0 ..< (24 * 8) {
            let timestamp = base + hour * 3600
            // A slow sweep through clear, broken and overcast, so the seven
            // rows differ from each other the way a real week does.
            let cloud = Double((hour * 7 + (hour / 24) * 31) % 101)
            rows.append(VerdictEngine.Row(timestamp: timestamp,
                                          cloudCover: cloud,
                                          cloudCoverHigh: cloud * 0.4,
                                          windGusts: 8 + Double((hour * 3) % 25),
                                          temperature: 14,
                                          dewPoint: 14 - Double(2 + (hour % 7)),
                                          precipitationProbability: cloud > 85 ? 45 : 0))
        }
        return OutlookEngine.followingNights(rows: rows,
                                             latitude: document.site.latitude,
                                             longitude: document.site.longitude,
                                             count: 7,
                                             from: Date(timeIntervalSince1970: Double(base)))
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
