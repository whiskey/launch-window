import Foundation

// Every user-facing string in the app and the widget, in one place, with an
// explicit key for each.
//
// Explicit keys rather than the English text as its own key: the catalogue then
// has a stable contract that `tools/check-strings.py` can verify against this
// file, and rewording the English cannot silently orphan the German.
//
// The beacon's own sentences — the verdict reasons and the veto labels — arrive
// as English generated on the device. `Reasons` matches them against the closed
// set of templates in `firmware/lib/verdict.py` and re-renders them in the
// reader's language, with numbers formatted for their locale. Anything that
// does not match is shown exactly as the beacon said it, which is how a firmware
// that learns a new sentence degrades: untranslated, never dropped.

enum Strings {

    // MARK: - Verdict

    static func verdictTitle(_ state: VerdictState) -> String {
        switch state {
        case .go:
            return String(localized: "verdict.go.title", defaultValue: "GO",
                          comment: "The verdict when the night is worth setting up for")
        case .marginal:
            return String(localized: "verdict.marginal.title", defaultValue: "MARGINAL",
                          comment: "The verdict when there is a window, but a short one")
        case .noGo:
            return String(localized: "verdict.nogo.title", defaultValue: "NO-GO",
                          comment: "The verdict when the sky is not worth it")
        case .unknown:
            return String(localized: "verdict.unknown.title", defaultValue: "UNKNOWN",
                          comment: "Not a judgement about the sky: the beacon has no forecast")
        }
    }

    static func verdictMeaning(_ state: VerdictState) -> String {
        switch state {
        case .go:
            return String(localized: "verdict.go.meaning", defaultValue: "Worth setting up")
        case .marginal:
            return String(localized: "verdict.marginal.meaning", defaultValue: "Worth a look")
        case .noGo:
            return String(localized: "verdict.nogo.meaning", defaultValue: "Not tonight")
        case .unknown:
            return String(localized: "verdict.unknown.meaning", defaultValue: "No forecast")
        }
    }

    // MARK: - Sky vocabulary

    static func darkness(_ darkness: Darkness) -> String {
        switch darkness {
        case .astronomical:
            return String(localized: "darkness.astronomical", defaultValue: "astronomical")
        case .nautical:
            return String(localized: "darkness.nautical", defaultValue: "nautical")
        case .none:
            return String(localized: "darkness.none", defaultValue: "none")
        }
    }

    /// The eight named phases. An unrecognised phase is returned untranslated
    /// rather than forced into the nearest one.
    static func moonPhase(_ phase: String) -> String {
        switch phase {
        case "new":
            return String(localized: "moon.new", defaultValue: "new")
        case "waxing crescent":
            return String(localized: "moon.waxingCrescent", defaultValue: "waxing crescent")
        case "first quarter":
            return String(localized: "moon.firstQuarter", defaultValue: "first quarter")
        case "waxing gibbous":
            return String(localized: "moon.waxingGibbous", defaultValue: "waxing gibbous")
        case "full":
            return String(localized: "moon.full", defaultValue: "full")
        case "waning gibbous":
            return String(localized: "moon.waningGibbous", defaultValue: "waning gibbous")
        case "last quarter":
            return String(localized: "moon.lastQuarter", defaultValue: "last quarter")
        case "waning crescent":
            return String(localized: "moon.waningCrescent", defaultValue: "waning crescent")
        default:
            return phase
        }
    }

    // MARK: - Labels

    static var appName: String {
        String(localized: "app.name", defaultValue: "Launch Window")
    }

    static var tonight: String {
        String(localized: "label.tonight", defaultValue: "Tonight")
    }

    static var noWindow: String {
        String(localized: "label.noWindow", defaultValue: "No window")
    }

    static var darkSky: String {
        String(localized: "label.darkSky", defaultValue: "Dark sky")
    }

    static var moon: String {
        String(localized: "label.moon", defaultValue: "Moon")
    }

    static var moonInterferes: String {
        String(localized: "label.moonInterferes", defaultValue: "in the way")
    }

    static var sunset: String {
        String(localized: "label.sunset", defaultValue: "Sunset")
    }

    static var dusk: String {
        String(localized: "label.dusk", defaultValue: "Dusk")
    }

    static var dawn: String {
        String(localized: "label.dawn", defaultValue: "Dawn")
    }

    static var sunrise: String {
        String(localized: "label.sunrise", defaultValue: "Sunrise")
    }

    static var cloud: String {
        String(localized: "label.cloud", defaultValue: "Cloud")
    }

    static var gusts: String {
        String(localized: "label.gusts", defaultValue: "Gusts")
    }

    /// A column header over values in kelvin, so it has to be short. The delta
    /// is what distinguishes it from the dew point itself.
    static var dewSpread: String {
        String(localized: "label.dewSpread", defaultValue: "Dew Δ")
    }

    static var score: String {
        String(localized: "label.score", defaultValue: "Score")
    }

    static var meanScore: String {
        String(localized: "label.meanScore", defaultValue: "Mean score")
    }

    static var hours: String {
        String(localized: "label.hours", defaultValue: "Hours")
    }

    static var reasons: String {
        String(localized: "label.reasons", defaultValue: "Reasons")
    }

    static var forecast: String {
        String(localized: "label.forecast", defaultValue: "Forecast")
    }

    static var beacon: String {
        String(localized: "label.beacon", defaultValue: "Beacon")
    }

    static var firmware: String {
        String(localized: "label.firmware", defaultValue: "Firmware")
    }

    static var ipAddress: String {
        String(localized: "label.ipAddress", defaultValue: "IP address")
    }

    static var uptime: String {
        String(localized: "label.uptime", defaultValue: "Uptime")
    }

    static var signal: String {
        String(localized: "label.signal", defaultValue: "Signal")
    }

    static var temperature: String {
        String(localized: "label.temperature", defaultValue: "Core temp")
    }

    static var fetchForecastNow: String {
        String(localized: "action.fetchForecastNow", defaultValue: "Fetch the forecast now",
               comment: "Triggers POST /api/v1/refresh, which costs the beacon an upstream API call")
    }

    static var attribution: String {
        String(localized: "label.attribution",
               defaultValue: "Forecast by Open-Meteo, CC-BY 4.0. Darkness and Moon computed on the beacon.")
    }

    static var settings: String {
        String(localized: "label.settings", defaultValue: "Settings")
    }

    static var refresh: String {
        String(localized: "label.refresh", defaultValue: "Refresh")
    }

    static var done: String {
        String(localized: "label.done", defaultValue: "Done")
    }

    static var nightVision: String {
        String(localized: "label.nightVision", defaultValue: "Night vision")
    }

    /// Shown under the night-vision toggle only when the App Group resolved, so
    /// the claim is never made by a build that cannot keep it.
    static var nightVisionShared: String {
        String(localized: "label.nightVision.shared",
               defaultValue: "Applies to the other astro tools in this group.")
    }

    static var nightVisionFootnote: String {
        String(localized: "label.nightVision.footnote",
               defaultValue: "Red on black, so reading the widget at one in the morning does not cost you your dark adaptation.")
    }

    static var beaconAddress: String {
        String(localized: "label.beaconAddress", defaultValue: "Beacon address")
    }

    static var beaconAddressFootnote: String {
        String(localized: "label.beaconAddress.footnote",
               defaultValue: "A hostname or an address on your network. A port may be appended, as in launch-window.home:8080.")
    }

    static var sharedWithWidget: String {
        String(localized: "label.sharedWithWidget",
               defaultValue: "The widget uses this address.")
    }

    static var notSharedWithWidget: String {
        String(localized: "label.notSharedWithWidget",
               defaultValue: "This build cannot share settings with the widget. Set the address on the widget itself: long-press it and choose Edit Widget.")
    }

    // MARK: - Freshness

    static var stale: String {
        String(localized: "label.stale", defaultValue: "STALE")
    }

    static func staleBanner(age: String) -> String {
        String(localized: "banner.stale",
               defaultValue: "The forecast is \(age) old. The sky half of this answer is out of date; the darkness and the Moon are not.",
               comment: "Shown above the verdict when data.stale is true")
    }

    static var noForecastBanner: String {
        String(localized: "banner.noForecast",
               defaultValue: "No forecast has arrived. This is not a judgement about the sky.")
    }

    static func flashCacheBanner(age: String) -> String {
        String(localized: "banner.flashCache",
               defaultValue: "Restored from the beacon's flash after a reboot, \(age) old.")
    }

    static var clockUnsyncedBanner: String {
        String(localized: "banner.clockUnsynced",
               defaultValue: "The beacon's clock has never synchronised, so every time below is unreliable.")
    }

    static func lastKnown(age: String) -> String {
        String(localized: "banner.lastKnown",
               defaultValue: "Beacon unreachable. Showing the last reading, from \(age) ago.",
               comment: "The app or widget could not reach the beacon and is showing its cache")
    }

    static func readAt(time: String) -> String {
        String(localized: "label.readAt", defaultValue: "read \(time)",
               comment: "When this client last got an answer, e.g. 'read 22:14'")
    }

    static var neverRead: String {
        String(localized: "label.neverRead", defaultValue: "never read")
    }

    // MARK: - Empty and error states

    static var noDarkness: String {
        String(localized: "state.noDarkness",
               defaultValue: "No astronomical night at this date.")
    }

    static var noGradedHours: String {
        String(localized: "state.noGradedHours", defaultValue: "No graded hours.")
    }

    static func couldNotReach(host: String) -> String {
        String(localized: "state.couldNotReach", defaultValue: "Could not reach \(host).")
    }

    static var openSettings: String {
        String(localized: "action.openSettings", defaultValue: "Change address")
    }

    // MARK: - Units and small formats

    static func percent(_ value: Double) -> String {
        let formatted = value.formatted(.number.precision(.fractionLength(0)))
        return String(localized: "unit.percent", defaultValue: "\(formatted) %")
    }

    static func hoursCount(_ value: Double) -> String {
        let formatted = value.formatted(.number.precision(.fractionLength(1)))
        return String(localized: "unit.hours", defaultValue: "\(formatted) h")
    }

    static func kilometresPerHour(_ value: Double) -> String {
        let formatted = value.formatted(.number.precision(.fractionLength(0)))
        return String(localized: "unit.kmh", defaultValue: "\(formatted) km/h")
    }

    static func decibelMilliwatts(_ value: Double) -> String {
        let formatted = value.formatted(.number.precision(.fractionLength(0)))
        return String(localized: "unit.dbm", defaultValue: "\(formatted) dBm")
    }

    static func kelvin(_ value: Double) -> String {
        let formatted = value.formatted(.number.precision(.fractionLength(1)))
        return String(localized: "unit.kelvin", defaultValue: "\(formatted) K")
    }

    static func degreesCelsius(_ value: Double) -> String {
        let formatted = value.formatted(.number.precision(.fractionLength(0)))
        return String(localized: "unit.celsius", defaultValue: "\(formatted) °C")
    }

    /// The line under the window: how long it is and how good it is.
    ///
    /// A whole phrase rather than a label joined to a number, because German
    /// capitalises its nouns and lower-casing `Mean score` to fit an English
    /// sentence produced `mittlere wertung`.
    static func windowDetail(hours: String, meanScore: String) -> String {
        String(localized: "format.windowDetail",
               defaultValue: "\(hours) · mean score \(meanScore)")
    }

    /// `21:47 – 04:22`, with the spacing this project's page uses.
    static func timeRange(_ start: String, _ end: String) -> String {
        String(localized: "format.timeRange", defaultValue: "\(start) – \(end)")
    }

    // MARK: - Widget

    static var widgetDisplayName: String {
        String(localized: "widget.displayName", defaultValue: "Tonight's verdict")
    }

    static var widgetDescription: String {
        String(localized: "widget.description",
               defaultValue: "Whether tonight is worth setting up the rig, from your launch-window beacon.")
    }
}

// MARK: - The beacon's own sentences

/// Re-renders the English sentences the firmware generates into the reader's
/// language.
///
/// The templates are the closed set in `firmware/lib/verdict.py`. Matching is on
/// the fixed words and the numbers are pulled out and reformatted, so a German
/// reader gets `0,4 h` rather than `0.4 h`. A sentence that matches nothing is
/// passed through untouched — the honest failure for a firmware that has learned
/// to say something new.
enum Reasons {

    static func localized(_ reason: String) -> String {
        let text = reason.trimmingCharacters(in: .whitespaces)
        let numbers = decimals(in: text)

        // Whole sentences, in the order verdict.py can emit them.
        if text == "no astronomical or nautical night at this date" {
            return String(localized: "reason.noNight",
                          defaultValue: "no astronomical or nautical night at this date")
        }
        if text == "no forecast covering tonight's dark hours" {
            return String(localized: "reason.noForecast",
                          defaultValue: "no forecast covering tonight's dark hours")
        }
        if text == "no usable stretch of dark sky tonight" {
            return String(localized: "reason.noUsableStretch",
                          defaultValue: "no usable stretch of dark sky tonight")
        }
        if text == "air close to the dew point — heaters on" {
            return String(localized: "reason.dew",
                          defaultValue: "air close to the dew point — heaters on")
        }
        if text == "some chance of precipitation" {
            return String(localized: "reason.precipitation",
                          defaultValue: "some chance of precipitation")
        }

        // Sentences carrying numbers.
        if text.contains("of usable dark sky, mean score"), numbers.count >= 2 {
            let hours = fraction(numbers[0], 1)
            let score = fraction(numbers[1], 0)
            return String(localized: "reason.usableWithScore",
                          defaultValue: "\(hours) h of usable dark sky, mean score \(score)")
        }
        if text.hasPrefix("only "), text.contains("h of usable dark sky"), let first = numbers.first {
            let hours = fraction(first, 1)
            return String(localized: "reason.onlyHours",
                          defaultValue: "only \(hours) h of usable dark sky")
        }
        if text.hasPrefix("best stretch is"), numbers.count >= 2 {
            let best = fraction(numbers[0], 1)
            let threshold = fraction(numbers[1], 1)
            return String(localized: "reason.bestStretchBelow",
                          defaultValue: "best stretch is \(best) h, below the \(threshold) h worth setting up for")
        }
        if text.hasPrefix("cloud cover averaging"), let first = numbers.first {
            let percent = fraction(first, 0)
            return String(localized: "reason.cloudAverage",
                          defaultValue: "cloud cover averaging \(percent) %")
        }
        if text.hasPrefix("moon up for"), numbers.count >= 2 {
            let lit = fraction(numbers[0], 0)
            let total = fraction(numbers[1], 0)
            return String(localized: "reason.moonUp",
                          defaultValue: "moon up for \(lit) of \(total) dark hours")
        }
        if text.hasPrefix("gusty (costing"), let first = numbers.first {
            let points = fraction(first, 0)
            return String(localized: "reason.gusty",
                          defaultValue: "gusty (costing \(points) points an hour)")
        }
        // "<veto kind> for N of M dark hours"
        if let range = text.range(of: " for "), text.hasSuffix("dark hours"), numbers.count >= 2 {
            let kind = String(text[text.startIndex ..< range.lowerBound])
            let count = fraction(numbers[0], 0)
            let total = fraction(numbers[1], 0)
            return String(localized: "reason.vetoedHours",
                          defaultValue: "\(vetoKind(kind)) for \(count) of \(total) dark hours")
        }

        return reason
    }

    /// The full veto label on a single hour, e.g. `overcast (100 %)`.
    static func veto(_ veto: String) -> String {
        let numbers = decimals(in: veto)
        if veto == "no data" {
            return String(localized: "veto.noData", defaultValue: "no data")
        }
        if veto.hasPrefix("rain likely"), let first = numbers.first {
            let percent = fraction(first, 0)
            return String(localized: "veto.rainLikely", defaultValue: "rain likely (\(percent) %)")
        }
        if veto.hasPrefix("gusts to"), let first = numbers.first {
            let speed = fraction(first, 0)
            return String(localized: "veto.gustsTo", defaultValue: "gusts to \(speed) km/h")
        }
        if veto.hasPrefix("overcast"), let first = numbers.first {
            let percent = fraction(first, 0)
            return String(localized: "veto.overcast", defaultValue: "overcast (\(percent) %)")
        }
        return veto
    }

    /// The kind of a full veto label, localised. `verdict.py` reduces
    /// "overcast (100 %)" to "overcast" by cutting at " (" and " to "; this cuts
    /// it the same way, so the two always name the same set of kinds.
    ///
    /// - Parameter short: the table column is about fifty points wide, and
    ///   "Regen wahrscheinlich" is not. The long form is for sentences, where
    ///   there is room for it and where the extra word carries meaning.
    static func kind(ofVeto veto: String, short: Bool = false) -> String {
        let head = veto.components(separatedBy: " (")[0].components(separatedBy: " to ")[0]
        return short ? shortVetoKind(head) : vetoKind(head)
    }

    private static func shortVetoKind(_ kind: String) -> String {
        switch kind {
        case "no data":
            return String(localized: "vetoKindShort.noData", defaultValue: "no data")
        case "rain likely":
            return String(localized: "vetoKindShort.rainLikely", defaultValue: "rain")
        case "gusts":
            return String(localized: "vetoKindShort.gusts", defaultValue: "gusts")
        case "overcast":
            return String(localized: "vetoKindShort.overcast", defaultValue: "overcast")
        default:
            return kind
        }
    }

    /// The bare kind, as `verdict.py` derives it by cutting at " (" and " to ".
    static func vetoKind(_ kind: String) -> String {
        switch kind {
        case "no data":
            return String(localized: "vetoKind.noData", defaultValue: "no data")
        case "rain likely":
            return String(localized: "vetoKind.rainLikely", defaultValue: "rain likely")
        case "gusts":
            return String(localized: "vetoKind.gusts", defaultValue: "gusts")
        case "overcast":
            return String(localized: "vetoKind.overcast", defaultValue: "overcast")
        default:
            return kind
        }
    }

    // MARK: -

    /// Every decimal number in the sentence, in order. The firmware writes them
    /// with a dot, always, so parsing is locale-independent on the way in;
    /// `fraction` puts them back in the reader's locale on the way out.
    private static func decimals(in text: String) -> [Double] {
        var found: [Double] = []
        var current = ""
        for character in text {
            if character.isNumber || (character == "." && !current.isEmpty) {
                current.append(character)
            } else {
                if let value = Double(current) { found.append(value) }
                current = ""
            }
        }
        if let value = Double(current) { found.append(value) }
        return found
    }

    private static func fraction(_ value: Double, _ places: Int) -> String {
        value.formatted(.number.precision(.fractionLength(places)))
    }
}
