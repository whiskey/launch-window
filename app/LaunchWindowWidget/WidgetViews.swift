import SwiftUI
import WidgetKit

/// Binds a timeline entry to the layout for whichever family WidgetKit is
/// asking about.
///
/// The four system layouts are in `Shared/WidgetLayouts.swift` and know nothing
/// about WidgetKit. What stays here is the part that genuinely does: the family
/// switch, the container background, and the Lock Screen sizes, which are drawn
/// in a single system tint and so are written to carry their meaning without
/// colour.
struct BeaconWidgetView: View {
    var entry: BeaconEntry
    @Environment(\.widgetFamily) private var family

    var body: some View {
        switch family {
        case .systemSmall:
            SmallVerdict(snapshot: entry.snapshot, palette: entry.palette).widgetSurface(entry.palette)
        case .systemMedium:
            MediumVerdict(snapshot: entry.snapshot, palette: entry.palette).widgetSurface(entry.palette)
        case .systemLarge:
            LargeVerdict(snapshot: entry.snapshot, palette: entry.palette).widgetSurface(entry.palette)
        case .systemExtraLarge:
            ExtraLargeVerdict(snapshot: entry.snapshot, palette: entry.palette).widgetSurface(entry.palette)
        #if !os(macOS)
        case .accessoryCircular:
            CircularVerdict(entry: entry)
        case .accessoryRectangular:
            RectangularVerdict(entry: entry)
        case .accessoryInline:
            InlineVerdict(entry: entry)
        #endif
        default:
            SmallVerdict(snapshot: entry.snapshot, palette: entry.palette).widgetSurface(entry.palette)
        }
    }
}

private extension View {
    /// Every system-family widget paints its own ground; without it the panel
    /// borrows the home screen's, and a night-vision widget stops being dark.
    func widgetSurface(_ palette: Palette) -> some View {
        containerBackground(for: .widget) { palette.background }
    }
}

// MARK: - Lock Screen

#if !os(macOS)

/// A capacity gauge of the night's mean score, with the verdict in the middle.
/// Accessory widgets are rendered in a single tint, so nothing here may depend
/// on colour — the symbol carries the state.
struct CircularVerdict: View {
    var entry: BeaconEntry

    var body: some View {
        let verdict = entry.snapshot.document?.verdict
        ZStack {
            AccessoryWidgetBackground()
            if let score = verdict?.score {
                Gauge(value: min(max(score, 0), 100), in: 0 ... 100) {
                    Image(systemName: VerdictSymbol.name(for: entry.snapshot.state))
                } currentValueLabel: {
                    Text(score.formatted(.number.precision(.fractionLength(0))))
                        .font(.system(size: 15, weight: .semibold, design: .rounded))
                        .minimumScaleFactor(0.7)
                }
                .gaugeStyle(.accessoryCircular)
            } else {
                VStack(spacing: 1) {
                    Image(systemName: VerdictSymbol.name(for: entry.snapshot.state))
                        .font(.system(size: 17, weight: .semibold))
                    Text(Strings.verdictTitle(entry.snapshot.state))
                        .font(.system(size: 9, weight: .bold, design: .rounded))
                        .lineLimit(1)
                        .minimumScaleFactor(0.6)
                }
            }
        }
        .containerBackground(for: .widget) { Color.clear }
    }
}

struct RectangularVerdict: View {
    var entry: BeaconEntry

    var body: some View {
        VStack(alignment: .leading, spacing: 1) {
            HStack(spacing: 3) {
                Image(systemName: VerdictSymbol.name(for: entry.snapshot.state))
                    .font(.system(size: 12, weight: .semibold))
                Text(Strings.verdictTitle(entry.snapshot.state))
                    .font(.system(size: 15, weight: .heavy, design: .rounded))
                if entry.snapshot.hasStaleForecast || entry.snapshot.isReplayed {
                    Text(Strings.stale)
                        .font(.system(size: 8, weight: .bold))
                }
            }
            .widgetAccentable()

            if let verdict = entry.snapshot.document?.verdict {
                if let window = verdict.window, let start = window.startLocal, let end = window.endLocal {
                    Text(Strings.timeRange(start, end))
                        .font(.system(size: 13, weight: .semibold, design: .rounded))
                        .monospacedDigit()
                } else {
                    Text(Strings.noWindow)
                        .font(.system(size: 12, weight: .medium))
                }
                if let reason = verdict.reasons.first {
                    Text(Reasons.localized(reason))
                        .font(.system(size: 10))
                        .lineLimit(1)
                        .minimumScaleFactor(0.8)
                }
            } else {
                Text(Strings.couldNotReach(host: entry.snapshot.host))
                    .font(.system(size: 10))
                    .lineLimit(2)
                    .minimumScaleFactor(0.8)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .leading)
        .containerBackground(for: .widget) { Color.clear }
    }
}

struct InlineVerdict: View {
    var entry: BeaconEntry

    var body: some View {
        // One line, one image, no layout of its own: the system owns both.
        Label {
            Text(text)
        } icon: {
            Image(systemName: VerdictSymbol.name(for: entry.snapshot.state))
        }
        .containerBackground(for: .widget) { Color.clear }
    }

    private var text: String {
        let title = Strings.verdictTitle(entry.snapshot.state)
        guard let window = entry.snapshot.document?.verdict.window,
              let start = window.startLocal, let end = window.endLocal
        else { return title }
        return "\(title) \(Strings.timeRange(start, end))"
    }
}

#endif

// MARK: - Previews

#Preview("Small — GO", as: .systemSmall) {
    TonightWidget()
} timeline: {
    BeaconEntry(date: .now, snapshot: SampleBeacon.snapshot(SampleBeacon.go), palette: .day)
}

#Preview("Medium — NO-GO", as: .systemMedium) {
    TonightWidget()
} timeline: {
    BeaconEntry(date: .now, snapshot: SampleBeacon.snapshot(SampleBeacon.noGo), palette: .day)
}

#Preview("Large — GO", as: .systemLarge) {
    TonightWidget()
} timeline: {
    BeaconEntry(date: .now, snapshot: SampleBeacon.snapshot(SampleBeacon.go), palette: .day)
}

#Preview("Large — night vision", as: .systemLarge) {
    TonightWidget()
} timeline: {
    BeaconEntry(date: .now, snapshot: SampleBeacon.snapshot(SampleBeacon.noGo), palette: .night)
}

#Preview("Large — unknown", as: .systemLarge) {
    TonightWidget()
} timeline: {
    BeaconEntry(date: .now, snapshot: SampleBeacon.snapshot(SampleBeacon.unknown), palette: .day)
}
