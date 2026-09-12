import Foundation

// PROOF OF CONCEPT — nights the beacon does not compute.
//
// The beacon answers one question about one night. This assembles the same
// answer for the nights after it, from `SkyMath` and `VerdictEngine` — the two
// ports — plus a weather forecast this client fetches itself.
//
// The honest risk in all of it is that the ports drift from the originals and
// start quietly disagreeing with the device in the hallway. `selfCheck` is the
// mitigation, and it is the reason this approach is defensible at all: the same
// engine also regrades *tonight*, where the beacon has published its own answer,
// so the two can be compared on every refresh. A client that cannot reproduce
// the verdict it was given has no business projecting three more.

/// One night, graded.
struct NightOutlook: Sendable, Identifiable {
    /// Days ahead: 0 is the night the beacon is talking about.
    var leadDays: Int
    var night: SkyMath.Night
    var darkness: Darkness
    var verdict: Verdict
    var moonIllumination: Double
    var moonPhase: String

    var id: Int { leadDays }

    var darkStart: Date? { night.duskAstronomical.map { Date(timeIntervalSince1970: Double($0)) } }
    var darkEnd: Date? { night.dawnAstronomical.map { Date(timeIntervalSince1970: Double($0)) } }

    /// The evening this night belongs to, for labelling. A night that starts at
    /// 21:29 and ends at 04:36 is "tonight", not two days.
    var evening: Date {
        Date(timeIntervalSince1970: Double(night.sunset ?? night.duskAstronomical ?? 0))
    }

    /// How much a forecast this far out is worth.
    ///
    /// Not a decoration: hourly cloud beyond about three days is a hint, and
    /// presenting day six with the same confidence as tonight would be the
    /// same lie this project refuses to tell about stale data.
    var confidence: Confidence {
        switch leadDays {
        case 0, 1: return .firm
        case 2, 3: return .fair
        default: return .vague
        }
    }

    enum Confidence: Sendable { case firm, fair, vague }
}

enum OutlookEngine {

    /// Grades `nights` consecutive nights, starting with the one in progress or
    /// about to begin.
    static func outlook(rows: [VerdictEngine.Row],
                        latitude: Double,
                        longitude: Double,
                        nights: Int,
                        from now: Date = Date(),
                        thresholds: VerdictEngine.Thresholds = .default) -> [NightOutlook] {
        let base = Int(now.timeIntervalSince1970)
        return (0 ..< nights).map { lead in
            grade(reference: base + lead * 86400, leadDays: lead, rows: rows,
                  latitude: latitude, longitude: longitude, thresholds: thresholds)
        }
    }

    /// The nights *after* the one in progress — which is what any caller
    /// showing a list next to the beacon's verdict actually wants.
    ///
    /// Tonight is deliberately excluded rather than merely skipped by the view.
    /// The beacon has already answered for tonight, from its own forecast, and
    /// a second opinion computed here could differ slightly and be read as a
    /// fault. That comparison is worth making, but exactly once and on purpose:
    /// it is `selfCheck`.
    static func followingNights(rows: [VerdictEngine.Row],
                                latitude: Double,
                                longitude: Double,
                                count: Int,
                                from now: Date = Date(),
                                thresholds: VerdictEngine.Thresholds = .default) -> [NightOutlook] {
        Array(outlook(rows: rows, latitude: latitude, longitude: longitude,
                      nights: count + 1, from: now, thresholds: thresholds).dropFirst())
    }

    static func grade(reference: Int,
                      leadDays: Int,
                      rows: [VerdictEngine.Row],
                      latitude: Double,
                      longitude: Double,
                      thresholds: VerdictEngine.Thresholds = .default) -> NightOutlook {
        let night = SkyMath.night(at: reference, latitude: latitude, longitude: longitude)
        let assessment = VerdictEngine.assess(
            hours: rows,
            night: night,
            moonAt: { timestamp in
                (SkyMath.moonAltitude(at: timestamp, latitude: latitude, longitude: longitude),
                 SkyMath.moonIllumination(at: timestamp))
            },
            thresholds: thresholds)

        // Describe the Moon at the middle of the dark window rather than at the
        // reference instant: "42 %" is about the night, not about teatime.
        let middle = midpoint(of: night) ?? reference
        return NightOutlook(leadDays: leadDays,
                            night: night,
                            darkness: assessment.darkness,
                            verdict: assessment.verdict,
                            moonIllumination: SkyMath.moonIllumination(at: middle),
                            moonPhase: SkyMath.moonPhaseName(at: middle))
    }

    private static func midpoint(of night: SkyMath.Night) -> Int? {
        guard let start = night.duskAstronomical ?? night.duskNautical,
              let end = night.dawnAstronomical ?? night.dawnNautical else { return nil }
        return (start + end) / 2
    }

    // MARK: - Self-check

    /// What happened when this client regraded the night the beacon had already
    /// graded.
    struct SelfCheck: Sendable {
        var agrees: Bool { differences.isEmpty }
        var differences: [String]
        var computed: Verdict?
        var reported: Verdict

        var summary: String {
            agrees
                ? "engine agrees with the beacon"
                : "engine disagrees with the beacon: " + differences.joined(separator: "; ")
        }
    }

    /// Regrades the beacon's own night from the raw values in its own document
    /// and compares.
    ///
    /// The document carries each hour's measured cloud, gusts, temperature, dew
    /// point and precipitation alongside the grade, precisely so a client can
    /// show why rather than just what. That makes it a complete input for the
    /// engine, and a complete test of it: same hours, same site, same
    /// thresholds, so any difference is this client's fault.
    static func selfCheck(document: BeaconDocument,
                          thresholds: VerdictEngine.Thresholds = .default) -> SelfCheck {
        let reported = document.verdict
        guard !reported.hours.isEmpty, let generated = document.generatedAt else {
            return SelfCheck(differences: [], computed: nil, reported: reported)
        }

        let rows = reported.hours.map { hour in
            VerdictEngine.Row(timestamp: Int(hour.timestamp),
                              cloudCover: hour.cloudCover,
                              cloudCoverHigh: hour.cloudCoverHigh,
                              windGusts: hour.windGusts,
                              temperature: hour.temperature,
                              dewPoint: hour.dewPoint,
                              precipitationProbability: hour.precipitationProbability)
        }
        let outlook = grade(reference: Int(generated.timeIntervalSince1970),
                            leadDays: 0,
                            rows: rows,
                            latitude: document.site.latitude,
                            longitude: document.site.longitude,
                            thresholds: thresholds)
        return SelfCheck(differences: differences(between: outlook.verdict, and: reported),
                         computed: outlook.verdict,
                         reported: reported)
    }

    /// Scores are compared loosely by one tenth, which is the rounding the
    /// document already applies; states, vetoes and hour counts are compared
    /// exactly, because a difference there is not rounding.
    private static func differences(between computed: Verdict, and reported: Verdict) -> [String] {
        var found: [String] = []
        if computed.state != reported.state {
            found.append("state \(computed.state.rawValue) vs \(reported.state.rawValue)")
        }
        if computed.hours.count != reported.hours.count {
            found.append("\(computed.hours.count) hours vs \(reported.hours.count)")
            return found
        }
        if !close(computed.score, reported.score) {
            found.append("score \(describe(computed.score)) vs \(describe(reported.score))")
        }
        for (mine, theirs) in zip(computed.hours, reported.hours) {
            if Int(mine.timestamp) != Int(theirs.timestamp) {
                found.append("hour timestamps differ")
                break
            }
            if !close(mine.score, theirs.score) {
                found.append("\(Int(mine.timestamp)) score \(describe(mine.score)) vs \(describe(theirs.score))")
            }
            if mine.veto != theirs.veto {
                found.append("\(Int(mine.timestamp)) veto \(mine.veto ?? "none") vs \(theirs.veto ?? "none")")
            }
        }
        switch (computed.window, reported.window) {
        case (nil, nil):
            break
        case let (mine?, theirs?):
            if !close(mine.hours, theirs.hours) {
                found.append("window \(mine.hours) h vs \(theirs.hours) h")
            }
            if !close(mine.meanScore, theirs.meanScore) {
                found.append("window mean \(describe(mine.meanScore)) vs \(describe(theirs.meanScore))")
            }
        default:
            found.append("window presence differs")
        }
        return found
    }

    private static func close(_ a: Double?, _ b: Double?, tolerance: Double = 0.1001) -> Bool {
        switch (a, b) {
        case (nil, nil): return true
        case let (x?, y?): return abs(x - y) <= tolerance
        default: return false
        }
    }

    private static func describe(_ value: Double?) -> String {
        value.map { String(format: "%.1f", $0) } ?? "nil"
    }
}
