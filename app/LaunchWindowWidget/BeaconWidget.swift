import SwiftUI
import WidgetKit

struct BeaconEntry: TimelineEntry {
    var date: Date
    var snapshot: BeaconSnapshot
    var palette: Palette
}

/// Reads the beacon on the widget's behalf, and decides when to ask again.
struct BeaconTimelineProvider: AppIntentTimelineProvider {

    func placeholder(in context: Context) -> BeaconEntry {
        BeaconEntry(date: Date(),
                    snapshot: SampleBeacon.snapshot(SampleBeacon.go),
                    palette: .day)
    }

    /// The gallery, and the moment before a real reading exists. WidgetKit
    /// renders this before the widget is allowed to fetch anything, so it gets
    /// a bundled night rather than an empty frame.
    func snapshot(for configuration: BeaconConfiguration, in context: Context) async -> BeaconEntry {
        if context.isPreview {
            return BeaconEntry(date: Date(),
                               snapshot: SampleBeacon.snapshot(SampleBeacon.go),
                               palette: configuration.palette)
        }
        let snapshot = await BeaconLoader.load(host: configuration.resolvedHost, timeout: 8)
        return BeaconEntry(date: Date(), snapshot: snapshot, palette: configuration.palette)
    }

    func timeline(for configuration: BeaconConfiguration, in context: Context) async -> Timeline<BeaconEntry> {
        let now = Date()
        let snapshot = await BeaconLoader.load(host: configuration.resolvedHost, timeout: 12)
        let entry = BeaconEntry(date: now, snapshot: snapshot, palette: configuration.palette)
        return Timeline(entries: [entry], policy: .after(Self.nextReading(after: now, given: snapshot)))
    }

    /// When to look again.
    ///
    /// WidgetKit grants a widget a few dozen refreshes a day, so they are spent
    /// where they change a decision. The question this answers — *do I set up
    /// tonight?* — is live from late afternoon until the sky closes, and dead at
    /// four in the morning once the answer has been acted on. The beacon itself
    /// only re-fetches every 30 minutes, so asking faster than that buys nothing.
    static func nextReading(after now: Date, given snapshot: BeaconSnapshot) -> Date {
        if let failure = snapshot.failure {
            // A beacon that is out of heap or off the network will likely still
            // be so in a minute; back off, but not so far that a reboot goes
            // unnoticed for the rest of the evening.
            return now.addingTimeInterval(failure.isTransient ? 15 * 60 : 60 * 60)
        }

        guard let night = snapshot.document?.night, let darkStart = night.darkStart else {
            return now.addingTimeInterval(60 * 60)
        }

        // The run-up to dusk is when the answer is worth money: it is when a
        // mount either goes outside or does not.
        let decisionOpens = darkStart.addingTimeInterval(-6 * 3600)
        let decisionCloses = night.darkEnd ?? darkStart.addingTimeInterval(8 * 3600)
        let inDecisionWindow = now >= decisionOpens && now <= decisionCloses
        return now.addingTimeInterval(inDecisionWindow ? 30 * 60 : 2 * 3600)
    }
}

struct TonightWidget: Widget {
    static let kind = "de.staticline.LaunchWindow.Tonight"

    var body: some WidgetConfiguration {
        AppIntentConfiguration(kind: Self.kind,
                               intent: BeaconConfiguration.self,
                               provider: BeaconTimelineProvider()) { entry in
            BeaconWidgetView(entry: entry)
        }
        .configurationDisplayName(Text(Strings.widgetDisplayName))
        .description(Text(Strings.widgetDescription))
        .supportedFamilies(Self.supportedFamilies)
    }

    static var supportedFamilies: [WidgetFamily] {
        #if os(macOS)
        [.systemSmall, .systemMedium, .systemLarge, .systemExtraLarge]
        #else
        [.systemSmall, .systemMedium, .systemLarge, .systemExtraLarge,
         .accessoryCircular, .accessoryRectangular, .accessoryInline]
        #endif
    }
}

@main
struct LaunchWindowWidgets: WidgetBundle {
    var body: some Widget {
        TonightWidget()
    }
}
