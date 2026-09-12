import Foundation

// PROOF OF CONCEPT — a Swift port of `firmware/lib/verdict.py`.
//
// Like `SkyMath`, this exists only because the beacon grades tonight and
// nothing else. It is a faithful port rather than a reinterpretation: the same
// weights, the same vetoes, the same run-finding, and the same English reason
// sentences — which means `Reasons.localized` translates the output of this
// engine exactly as it translates the beacon's, with no second vocabulary.
//
// Every weight here has a justification in the original file. They are not
// repeated; the short version is that cloud dominates, high cloud is penalised
// beyond its share because thin cirrus fools both people and forecasts, gusts
// rather than mean wind move a tripod, dew is graded from the spread because
// that is what predicts it, and moonlight scales with illuminated fraction to
// the power 1.5 because a half-lit Moon is far less than half as bright.

enum VerdictEngine {

    struct Thresholds: Sendable, Hashable {
        var usableScore: Double = 55
        var goHours: Double = 2.0
        var goScore: Double = 70
        var marginalHours: Double = 1.0
        var gustVetoKMH: Double = 40.0
        var gustFreeKMH: Double = 15.0
        var precipVetoPercent: Double = 40.0
        var cloudVetoPercent: Double = 90.0

        /// The defaults in `firmware/lib/verdict.py`. `config.json` on the
        /// board may override any of them, and the document does not publish
        /// what it used — so a beacon with edited thresholds will disagree with
        /// this engine, and `OutlookEngine.selfCheck` is what would notice.
        static let `default` = Thresholds()
    }

    /// One forecast hour as Open-Meteo gives it.
    struct Row: Sendable, Hashable {
        var timestamp: Int
        var cloudCover: Double?
        var cloudCoverHigh: Double?
        var windGusts: Double?
        var temperature: Double?
        var dewPoint: Double?
        var precipitationProbability: Double?
    }

    // MARK: - One hour

    /// Score one hour from 0 to 100, or nil if it cannot be judged.
    static func grade(_ row: Row,
                      moonAltitude: Double?,
                      moonIllumination: Double,
                      thresholds t: Thresholds = .default) -> ForecastHour {
        let cloud = row.cloudCover
        let high = row.cloudCoverHigh
        let gusts = row.windGusts
        let precip = row.precipitationProbability
        let temp = row.temperature
        let dew = row.dewPoint

        // An hour whose cloud cover never arrived is excluded from the night,
        // not counted as a clear one.
        guard let cloud else {
            return ForecastHour(timestamp: Double(row.timestamp),
                                time: Date(timeIntervalSince1970: Double(row.timestamp)),
                                local: nil, score: nil, penalties: [:], veto: "no data",
                                moonAltitudeDegrees: moonAltitude, cloudCover: nil,
                                cloudCoverHigh: high, windGusts: gusts, temperature: temp,
                                dewPoint: dew, precipitationProbability: precip)
        }

        var veto: String?
        if let precip, precip >= t.precipVetoPercent {
            veto = "rain likely (\(Int(precip)) %)"
        } else if let gusts, gusts >= t.gustVetoKMH {
            veto = "gusts to \(Int(gusts)) km/h"
        } else if cloud >= t.cloudVetoPercent {
            veto = "overcast (\(Int(cloud)) %)"
        }

        var penalties: [String: Double] = [:]
        penalties["cloud"] = min(85.0, 0.80 * cloud + 0.20 * (high ?? 0.0))

        if let gusts, gusts > t.gustFreeKMH {
            penalties["wind"] = min(40.0, (gusts - t.gustFreeKMH) * 1.2)
        }
        if let temp, let dew {
            let spread = temp - dew
            if spread < 1.0 {
                penalties["dew"] = 20.0
            } else if spread < 2.0 {
                penalties["dew"] = 12.0
            } else if spread < 3.0 {
                penalties["dew"] = 6.0
            }
        }
        if let precip, precip > 0 {
            penalties["precipitation"] = precip * 0.3
        }
        if let moonAltitude, moonAltitude > 0, moonIllumination != 0 {
            let altitudeFactor = 0.35 + 0.65 * sin(moonAltitude * .pi / 180)
            penalties["moon"] = pow(moonIllumination, 1.5) * altitudeFactor * 45.0
        }

        let score = veto != nil ? 0.0 : max(0.0, 100.0 - penalties.values.reduce(0, +))
        return ForecastHour(timestamp: Double(row.timestamp),
                            time: Date(timeIntervalSince1970: Double(row.timestamp)),
                            local: nil,
                            score: score.rounded(to: 1),
                            penalties: penalties.mapValues { $0.rounded(to: 1) },
                            veto: veto,
                            moonAltitudeDegrees: moonAltitude.map { $0.rounded(to: 1) },
                            cloudCover: cloud, cloudCoverHigh: high, windGusts: gusts,
                            temperature: temp, dewPoint: dew,
                            precipitationProbability: precip)
    }

    // MARK: - One night

    /// Which definition of darkness applies, so that a night with no forecast
    /// still reports the same darkness as one with a forecast.
    static func darkness(of night: SkyMath.Night) -> Darkness {
        if night.duskAstronomical != nil && night.dawnAstronomical != nil { return .astronomical }
        if night.duskNautical != nil && night.dawnNautical != nil { return .nautical }
        return .none
    }

    struct Assessment: Sendable {
        var verdict: Verdict
        var darkness: Darkness
        var darkStart: Int?
        var darkEnd: Int?
    }

    static func assess(hours: [Row],
                       night: SkyMath.Night,
                       moonAt: (Int) -> (altitude: Double?, illumination: Double),
                       thresholds t: Thresholds = .default,
                       hourSeconds: Int = 3600) -> Assessment {
        let darkness = darkness(of: night)
        let darkStart: Int?
        let darkEnd: Int?
        if darkness == .astronomical {
            darkStart = night.duskAstronomical
            darkEnd = night.dawnAstronomical
        } else {
            // Around midsummer the Sun never reaches -18°. Nautical twilight is
            // the honest fallback — it is what people actually image in during
            // those weeks — and the result says which it used.
            darkStart = night.duskNautical
            darkEnd = night.dawnNautical
        }

        guard let darkStart, let darkEnd else {
            return Assessment(verdict: Verdict(state: .unknown, score: nil,
                                               reasons: ["no astronomical or nautical night at this date"],
                                               window: nil, hours: []),
                              darkness: .none, darkStart: nil, darkEnd: nil)
        }

        var graded: [ForecastHour] = []
        for row in hours {
            let ts = row.timestamp
            if ts + hourSeconds <= darkStart || ts >= darkEnd { continue }
            let (altitude, illumination) = moonAt(ts)
            graded.append(grade(row, moonAltitude: altitude, moonIllumination: illumination,
                                thresholds: t))
        }

        guard !graded.isEmpty else {
            return Assessment(verdict: Verdict(state: .unknown, score: nil,
                                               reasons: ["no forecast covering tonight's dark hours"],
                                               window: nil, hours: []),
                              darkness: darkness, darkStart: darkStart, darkEnd: darkEnd)
        }

        let (startIndex, runLength) = longestRun(graded, usableScore: t.usableScore)
        let scored = graded.compactMap(\.score)
        let nightMean = scored.isEmpty ? nil : scored.reduce(0, +) / Double(scored.count)

        var best: ObservingWindow?
        var runMean: Double?
        if runLength > 0 {
            let run = Array(graded[startIndex ..< startIndex + runLength])
            let mean = run.compactMap(\.score).reduce(0, +) / Double(runLength)
            runMean = mean
            // Clip to the dark period: the first and last hours of a run may
            // extend past dusk or dawn, and promising imaging time that is not
            // dark is exactly the kind of lie this project is trying not to tell.
            let start = max(Int(run[0].timestamp), darkStart)
            let end = min(Int(run[run.count - 1].timestamp) + hourSeconds, darkEnd)
            best = ObservingWindow(start: Date(timeIntervalSince1970: Double(start)),
                                   end: Date(timeIntervalSince1970: Double(end)),
                                   startLocal: nil, endLocal: nil,
                                   hours: (Double(end - start) / 3600.0).rounded(to: 1),
                                   meanScore: mean.rounded(to: 1))
        }

        let state: VerdictState
        if let best, let runMean, best.hours >= t.goHours, runMean >= t.goScore {
            state = .go
        } else if let best, best.hours >= t.marginalHours {
            state = .marginal
        } else {
            state = .noGo
        }

        let verdict = Verdict(state: state,
                              score: nightMean?.rounded(to: 1),
                              reasons: reasons(state: state, graded: graded, best: best, t: t),
                              // A window is an invitation to go outside, so it
                              // exists only when going outside is the advice.
                              window: state == .noGo ? nil : best,
                              hours: graded)
        return Assessment(verdict: verdict, darkness: darkness,
                          darkStart: darkStart, darkEnd: darkEnd)
    }

    // MARK: -

    /// Longest contiguous run of usable hours, as (startIndex, length).
    private static func longestRun(_ graded: [ForecastHour],
                                   usableScore: Double) -> (start: Int, length: Int) {
        var bestStart = -1, bestLength = 0
        var runStart = -1, runLength = 0
        for (index, hour) in graded.enumerated() {
            if let score = hour.score, score >= usableScore {
                if runLength == 0 { runStart = index }
                runLength += 1
                if runLength > bestLength {
                    bestStart = runStart
                    bestLength = runLength
                }
            } else {
                runLength = 0
            }
        }
        return (bestStart, bestLength)
    }

    /// The order `grade_hour` assigns penalties, which is the order they end up
    /// in its dict.
    ///
    /// It matters because Python dicts keep insertion order and Python's sort is
    /// stable, so two penalties with equal totals come out in the order they
    /// were first added. A Swift `Dictionary` has no order at all, so the
    /// original's has to be written down or the tie-break silently differs —
    /// which is precisely what `compare-verdict.py` caught.
    static let penaltyOrder = ["cloud", "wind", "dew", "precipitation", "moon"]

    /// Which penalties actually shaped this night, largest total first, ties
    /// broken the way the original breaks them.
    private static func dominantLimits(_ graded: [ForecastHour]) -> [(String, Double)] {
        var totals: [String: Double] = [:]
        for hour in graded {
            for (name, value) in hour.penalties {
                totals[name, default: 0] += value
            }
        }
        func rank(_ name: String) -> Int {
            penaltyOrder.firstIndex(of: name) ?? penaltyOrder.count
        }
        return totals
            .map { ($0.key, $0.value) }
            .sorted { left, right in
                left.1 == right.1 ? rank(left.0) < rank(right.0) : left.1 > right.1
            }
    }

    /// The same sentences `verdict.py` produces, so that one translator serves
    /// both. Numbers are formatted the way Python's `%` operator formats them.
    private static func reasons(state: VerdictState,
                                graded: [ForecastHour],
                                best: ObservingWindow?,
                                t: Thresholds) -> [String] {
        var reasons: [String] = []
        let vetoed = graded.filter { $0.veto != nil }
        let limits = dominantLimits(graded)
        let count = graded.count

        if state == .go, let best, let mean = best.meanScore {
            reasons.append("\(fixed(best.hours, 1)) h of usable dark sky, mean score \(fixed(mean, 0))")
        } else if state == .marginal, let best {
            reasons.append("only \(fixed(best.hours, 1)) h of usable dark sky")
        } else if let best {
            reasons.append("best stretch is \(fixed(best.hours, 1)) h, below the "
                           + "\(fixed(t.marginalHours, 1)) h worth setting up for")
        } else {
            reasons.append("no usable stretch of dark sky tonight")
        }

        if !vetoed.isEmpty {
            // Report the veto that occurs most: one wet hour and eight wet
            // hours are different nights.
            // Counted in the order the kinds first appear, because `max` in the
            // original returns the first of several equal counts and that order
            // is the dict's insertion order — chronological, here.
            var order: [String] = []
            var kinds: [String: Int] = [:]
            for hour in vetoed {
                guard let veto = hour.veto else { continue }
                let kind = veto.components(separatedBy: " (")[0].components(separatedBy: " to ")[0]
                if kinds[kind] == nil { order.append(kind) }
                kinds[kind, default: 0] += 1
            }
            if let worst = order.max(by: { (kinds[$0] ?? 0) < (kinds[$1] ?? 0) }) {
                reasons.append("\(worst) for \(kinds[worst] ?? 0) of \(count) dark hours")
            }
        }

        for (name, total) in limits.prefix(2) {
            let mean = total / Double(count)
            if mean < 5 { continue }
            switch name {
            case "cloud":
                let covers = graded.compactMap(\.cloudCover)
                if !covers.isEmpty {
                    let average = covers.reduce(0, +) / Double(covers.count)
                    reasons.append("cloud cover averaging \(fixed(average, 0)) %")
                }
            case "moon":
                let lit = graded.filter { $0.penalties["moon"] != nil }.count
                reasons.append("moon up for \(lit) of \(count) dark hours")
            case "wind":
                reasons.append("gusty (costing \(fixed(mean, 0)) points an hour)")
            case "dew":
                reasons.append("air close to the dew point — heaters on")
            case "precipitation":
                reasons.append("some chance of precipitation")
            default:
                break
            }
        }
        return reasons
    }

    /// `%.Nf`, which is what the original uses and what `Reasons` parses back.
    private static func fixed(_ value: Double, _ places: Int) -> String {
        String(format: "%.\(places)f", value)
    }
}

extension Double {
    /// Rounded to a number of decimal places, half away from zero.
    ///
    /// Python's `round` is half-to-even, so the two can differ on an exact
    /// midpoint. `tools/compare-verdict.py` allows for that rather than
    /// pretending the difference is not there — it is worth 0.1 of a score that
    /// is then compared against thresholds 15 points apart.
    func rounded(to places: Int) -> Double {
        let factor = pow(10.0, Double(places))
        return (self * factor).rounded() / factor
    }
}
