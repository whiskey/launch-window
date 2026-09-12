import SwiftUI

// The pieces the app and every widget size are assembled from. They live here
// rather than in either target so that a phone widget, a Mac widget and the
// app's own screen cannot drift into saying the same thing three ways.

// MARK: - Verdict headline

/// The answer, at whatever size the container can afford.
struct VerdictHeadline: View {
    var state: VerdictState
    var palette: Palette
    var size: CGFloat
    var showsMeaning: Bool = true

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: size * 0.22) {
            Image(systemName: VerdictSymbol.name(for: state))
                .font(.system(size: size * 0.78, weight: .semibold))
                .foregroundStyle(palette.verdict(state))
                .alignmentGuide(.firstTextBaseline) { $0[.bottom] * 0.82 }

            VStack(alignment: .leading, spacing: 0) {
                Text(Strings.verdictTitle(state))
                    .font(.system(size: size, weight: .heavy, design: .rounded))
                    .foregroundStyle(palette.verdict(state))
                    .lineLimit(1)
                    .minimumScaleFactor(0.6)

                if showsMeaning {
                    Text(Strings.verdictMeaning(state))
                        .font(.system(size: size * 0.34, weight: .medium))
                        .foregroundStyle(palette.secondary)
                        .lineLimit(1)
                        .minimumScaleFactor(0.7)
                }
            }
        }
    }
}

// MARK: - The window

/// The imaging window, which is the one line that tells you what to do. When
/// there is none, the absence is stated rather than left blank — a rejected
/// night is described in the reasons, not by an empty row.
struct WindowLine: View {
    var verdict: Verdict
    var palette: Palette
    var size: CGFloat
    var showsDetail: Bool = true

    var body: some View {
        if let window = verdict.window,
           let start = window.startLocal, let end = window.endLocal {
            VStack(alignment: .leading, spacing: 1) {
                Text(Strings.timeRange(start, end))
                    .font(.system(size: size, weight: .semibold, design: .rounded))
                    .monospacedDigit()
                    .foregroundStyle(palette.text)
                    .lineLimit(1)
                    .minimumScaleFactor(0.6)

                if showsDetail {
                    Text(detail(for: window))
                        .font(.system(size: size * 0.62, weight: .regular))
                        .foregroundStyle(palette.secondary)
                        .lineLimit(1)
                        .minimumScaleFactor(0.7)
                }
            }
        } else {
            Text(Strings.noWindow)
                .font(.system(size: size * 0.78, weight: .semibold, design: .rounded))
                .foregroundStyle(palette.faint)
                .lineLimit(1)
                .minimumScaleFactor(0.7)
        }
    }

    private func detail(for window: ObservingWindow) -> String {
        let hours = Strings.hoursCount(window.hours)
        guard let mean = window.meanScore else { return hours }
        let score = mean.formatted(.number.precision(.fractionLength(0)))
        return Strings.windowDetail(hours: hours, meanScore: score)
    }
}

// MARK: - The night, hour by hour

/// Every forecast hour overlapping the dark window, graded.
///
/// Three things are drawn that a bare bar chart would lose:
///
///   * the **usable line** at score 55, the firmware's own `usable_score`, so
///     it is visible which hours clear the bar rather than merely which are
///     taller than their neighbours;
///   * **vetoed** hours, marked, because a veto is absolute and not just a low
///     score;
///   * **ungraded** hours, drawn hollow. An hour whose cloud cover came back
///     null is excluded from the night, and it must not look like a zero.
struct HourStrip: View {
    var hours: [ForecastHour]
    var window: ObservingWindow?
    var palette: Palette
    var height: CGFloat
    /// A cap, not a fixed width. Columns share the space they are given, so the
    /// strip fills the panel it is in instead of huddling in the middle of it;
    /// the cap only stops four hours from becoming four slabs.
    var barWidth: CGFloat = 22
    var spacing: CGFloat = 3
    /// Set independently of the bar width, which is now driven by the available
    /// space rather than by anything to do with type.
    var labelSize: CGFloat = 9
    var showsLabels: Bool = true
    var showsUsableLine: Bool = true
    var labelEvery: Int = 1

    var body: some View {
        HStack(alignment: .bottom, spacing: spacing) {
            ForEach(Array(hours.enumerated()), id: \.element.id) { index, hour in
                column(for: hour, index: index)
                    .accessibilityLabel(accessibilityLabel(for: hour, index: index))
            }
        }
        // The overlay goes on before the strip is stretched, so the threshold
        // line ends where the bars end rather than running off into the margin.
        .overlay(alignment: .top) {
            if showsUsableLine {
                Rectangle()
                    .fill(palette.grid)
                    .frame(height: 1)
                    .padding(.top, height * (1 - CGFloat(Grading.usableScore / 100)))
                    .allowsHitTesting(false)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    /// One hour: the bar, the window marker under it, and its label. Keeping
    /// them in a single column is what makes the label sit under its own bar at
    /// every width, without measuring anything.
    private func column(for hour: ForecastHour, index: Int) -> some View {
        VStack(spacing: 0) {
            // The column takes an equal share of the strip; the bar inside it
            // is capped. Eight hours therefore spread across the whole panel at
            // a sane bar width, rather than bunching at the left of it.
            bar(for: hour)
                .frame(height: height)
                .frame(maxWidth: barWidth)

            // The recommended window, marked under the hours it covers. Drawn
            // only when there is one — an empty rail under a no-go night would
            // read as a window of zero length rather than as no window.
            if window != nil {
                RoundedRectangle(cornerRadius: 1, style: .continuous)
                    .fill(isInWindow(hour) ? palette.verdict(.go) : .clear)
                    .frame(height: 3)
                    .frame(maxWidth: barWidth)
                    .padding(.top, 3)
            }

            if showsLabels {
                Text(index % labelEvery == 0 ? shortHour(hour) : " ")
                    .font(.system(size: labelSize, weight: .medium))
                    .monospacedDigit()
                    .foregroundStyle(palette.faint)
                    .lineLimit(1)
                    .minimumScaleFactor(0.6)
                    .padding(.top, 3)
            }
        }
        .frame(maxWidth: .infinity)
    }

    @ViewBuilder
    private func bar(for hour: ForecastHour) -> some View {
        // Capped: a bar that is wide because the panel is wide should not also
        // become a lozenge.
        let radius = min(barWidth / 2.6, 4.5)
        ZStack(alignment: .bottom) {
            RoundedRectangle(cornerRadius: radius, style: .continuous)
                .fill(palette.grid.opacity(0.35))

            if let score = hour.score {
                RoundedRectangle(cornerRadius: radius, style: .continuous)
                    .fill(palette.score(score))
                    .frame(height: max(barWidth * 0.55, height * CGFloat(score / 100)))
                    .overlay(alignment: .top) {
                        if hour.isVetoed {
                            // A veto is not a low score; it is a refusal, and it
                            // is marked as one so a tall-but-vetoed hour cannot
                            // be misread as usable.
                            Rectangle()
                                .fill(palette.background.opacity(0.85))
                                .frame(height: 1.5)
                        }
                    }
            } else {
                // Ungraded: an outline where a bar would be. An hour whose cloud
                // cover came back null is excluded from the night, and it must
                // not be drawn as a zero.
                RoundedRectangle(cornerRadius: radius, style: .continuous)
                    .strokeBorder(palette.faint, style: StrokeStyle(lineWidth: 1, dash: [2, 2]))
            }
        }
    }

    /// `21:00` is four characters the strip usually cannot spare; the hour alone
    /// carries it, and the full time is in the app.
    private func shortHour(_ hour: ForecastHour) -> String {
        guard let local = hour.local else { return "—" }
        return local.split(separator: ":").first.map(String.init) ?? local
    }

    private func isInWindow(_ hour: ForecastHour) -> Bool {
        guard let window, let start = window.start, let end = window.end,
              let hourStart = hour.time else { return false }
        let hourEnd = hourStart.addingTimeInterval(3600)
        return hourStart < end && hourEnd > start
    }

    /// Built with `verbatim:` throughout: every part is already localised, and
    /// an interpolated `Text` literal would become a catalogue key of its own.
    private func accessibilityLabel(for hour: ForecastHour, index: Int) -> Text {
        let time = hour.local ?? String(index)
        guard let score = hour.score else {
            return Text(verbatim: "\(time): \(Strings.noGradedHours)")
        }
        let value = score.formatted(.number.precision(.fractionLength(0)))
        if let veto = hour.veto {
            return Text(verbatim: "\(time): \(value), \(Reasons.veto(veto))")
        }
        return Text(verbatim: "\(time): \(value)")
    }
}

// MARK: - Score and evidence

/// The mean score over the dark hours. Deliberately set apart from the verdict,
/// because it did not decide it — the best run did.
struct ScoreBadge: View {
    var verdict: Verdict
    var palette: Palette

    var body: some View {
        if let score = verdict.score {
            VStack(alignment: .trailing, spacing: -2) {
                Text(score.formatted(.number.precision(.fractionLength(0))))
                    .font(.system(size: 30, weight: .bold, design: .rounded))
                    .monospacedDigit()
                    .foregroundStyle(palette.score(score))
                Text(Strings.meanScore.uppercased())
                    .font(.system(size: 8, weight: .semibold))
                    .tracking(0.4)
                    .foregroundStyle(palette.faint)
            }
        }
    }
}

/// The values each hour was graded from. The verdict is an opinion; this is the
/// evidence, and on a panel this wide there is room to show it.
struct HourTable: View {
    var hours: [ForecastHour]
    var palette: Palette
    var limit: Int = 8
    var columnWidth: CGFloat = 54
    var spacing: CGFloat = 4

    var body: some View {
        VStack(spacing: 2) {
            header
            Rectangle().fill(palette.grid).frame(height: 1)
            ForEach(hours.prefix(limit)) { hour in
                HStack(spacing: spacing) {
                    cell(hour.local ?? "—", weight: .semibold, tint: palette.text)
                    cell(hour.score.map { $0.formatted(.number.precision(.fractionLength(0))) } ?? "—",
                         tint: palette.score(hour.score))
                    cell(hour.cloudCover.map(Strings.percent) ?? "—")
                    cell(hour.windGusts.map(Strings.kilometresPerHour) ?? "—")
                    cell(hour.dewSpread.map(Strings.kelvin) ?? "—")
                    // The kind only. "overcast (100 %)" would repeat the cloud
                    // column back at the reader in half the width available.
                    cell(hour.veto.map { Reasons.kind(ofVeto: $0, short: true) } ?? "",
                         tint: palette.verdict(.noGo), wide: true)
                }
            }
        }
    }

    private var header: some View {
        HStack(spacing: spacing) {
            headerCell("")
            headerCell(Strings.score)
            headerCell(Strings.cloud)
            headerCell(Strings.gusts)
            headerCell(Strings.dewSpread)
            headerCell("", wide: true)
        }
    }

    private func headerCell(_ text: String, wide: Bool = false) -> some View {
        Text(text.uppercased())
            .font(.system(size: 8, weight: .semibold))
            .tracking(0.3)
            .foregroundStyle(palette.faint)
            .lineLimit(1)
            .minimumScaleFactor(0.6)
            .frame(maxWidth: wide ? .infinity : columnWidth, alignment: wide ? .leading : .trailing)
    }

    private func cell(_ text: String, weight: Font.Weight = .regular,
                      tint: Color? = nil, wide: Bool = false) -> some View {
        Text(text)
            .font(.system(size: 10, weight: weight, design: .rounded))
            .monospacedDigit()
            .foregroundStyle(tint ?? palette.secondary)
            .lineLimit(1)
            .minimumScaleFactor(0.7)
            .frame(maxWidth: wide ? .infinity : columnWidth, alignment: wide ? .leading : .trailing)
            .padding(.leading, wide ? 6 : 0)
    }
}

// MARK: - Banners

/// What the reader must be told before they read the verdict.
///
/// The beacon's rule is that a stale value is never presented as a current one,
/// and that the saying-so goes *above* the verdict rather than in small print
/// below it. This is that banner, and its order is by severity: a document we
/// could not refresh outranks a forecast the beacon itself calls stale, which
/// outranks a clock that never synced.
struct StatusBanner: View {
    var snapshot: BeaconSnapshot
    var palette: Palette
    var size: CGFloat = 11

    var body: some View {
        if let notice {
            HStack(spacing: 4) {
                Image(systemName: notice.symbol)
                    .font(.system(size: size * 0.95, weight: .semibold))
                Text(notice.text)
                    .font(.system(size: size, weight: .medium))
                    .lineLimit(2)
                    .minimumScaleFactor(0.75)
                    .multilineTextAlignment(.leading)
                Spacer(minLength: 0)
            }
            .foregroundStyle(notice.tint)
            .padding(.horizontal, 6)
            .padding(.vertical, 4)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(
                RoundedRectangle(cornerRadius: 6, style: .continuous)
                    .fill(notice.tint.opacity(palette.nightVision ? 0.12 : 0.16))
            )
        }
    }

    private struct Notice {
        var symbol: String
        var text: String
        var tint: Color
    }

    private var notice: Notice? {
        guard let document = snapshot.document else { return nil }

        if snapshot.isReplayed {
            let age = snapshot.age().map(Age.compact) ?? Strings.neverRead
            return Notice(symbol: "antenna.radiowaves.left.and.right.slash",
                          text: Strings.lastKnown(age: age),
                          tint: palette.verdict(.unknown))
        }
        if document.data.stale {
            if let seconds = document.data.ageSeconds {
                return Notice(symbol: "clock.badge.exclamationmark",
                              text: Strings.staleBanner(age: Age.compact(seconds)),
                              tint: palette.verdict(.marginal))
            }
            return Notice(symbol: "clock.badge.exclamationmark",
                          text: Strings.noForecastBanner,
                          tint: palette.verdict(.marginal))
        }
        if !document.clock.synced {
            return Notice(symbol: "clock.badge.questionmark",
                          text: Strings.clockUnsyncedBanner,
                          tint: palette.verdict(.marginal))
        }
        if document.data.fromFlashCache, let seconds = document.data.ageSeconds {
            return Notice(symbol: "internaldrive",
                          text: Strings.flashCacheBanner(age: Age.compact(seconds)),
                          tint: palette.secondary)
        }
        return nil
    }
}

// MARK: - Footer

/// Site, and when this copy was read. Small, but it is the difference between a
/// number and a dated number.
struct FreshnessLine: View {
    var snapshot: BeaconSnapshot
    var palette: Palette
    var size: CGFloat = 9
    var showsSite: Bool = true

    var body: some View {
        HStack(spacing: 4) {
            // The smallest sizes have no room for a banner, so the two things
            // that would go in one are carried here instead: a document we
            // could not refresh, and a forecast the beacon calls stale.
            if snapshot.isReplayed {
                Image(systemName: "antenna.radiowaves.left.and.right.slash")
                    .foregroundStyle(palette.verdict(.unknown))
            }
            if showsSite, let site = snapshot.site, !site.isEmpty {
                Text(site)
                    .lineLimit(1)
                    .minimumScaleFactor(0.7)
                Text(verbatim: "·")
            }
            if snapshot.hasStaleForecast {
                Text(Strings.stale)
                    .fontWeight(.heavy)
                    .foregroundStyle(palette.verdict(.marginal))
            }
            Text(readAt)
                .monospacedDigit()
                .lineLimit(1)
            Spacer(minLength: 0)
        }
        .font(.system(size: size, weight: .medium))
        .foregroundStyle(palette.faint)
    }

    private var readAt: String {
        guard let retrievedAt = snapshot.retrievedAt else { return Strings.neverRead }
        return Strings.readAt(time: Age.clock(retrievedAt))
    }
}

// MARK: - Reasons

/// The beacon's own sentences, translated where they match a known template.
struct ReasonList: View {
    var reasons: [String]
    var palette: Palette
    var size: CGFloat = 11
    var limit: Int = 3

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            ForEach(Array(reasons.prefix(limit).enumerated()), id: \.offset) { _, reason in
                HStack(alignment: .firstTextBaseline, spacing: 4) {
                    Text(verbatim: "—")
                        .foregroundStyle(palette.faint)
                    Text(Reasons.localized(reason))
                        .foregroundStyle(palette.secondary)
                        .lineLimit(2)
                        .minimumScaleFactor(0.8)
                        .multilineTextAlignment(.leading)
                    Spacer(minLength: 0)
                }
                .font(.system(size: size))
            }
        }
    }
}

// MARK: - Sky facts

/// A labelled value, the unit of the fact grids in the larger sizes.
struct Fact: View {
    var label: String
    var value: String
    var palette: Palette
    var tint: Color?
    var size: CGFloat = 11

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text(label.uppercased())
                .font(.system(size: size * 0.72, weight: .semibold))
                .tracking(0.4)
                .foregroundStyle(palette.faint)
                .lineLimit(1)
                .minimumScaleFactor(0.7)
            Text(value)
                .font(.system(size: size, weight: .semibold, design: .rounded))
                .monospacedDigit()
                .foregroundStyle(tint ?? palette.text)
                .lineLimit(1)
                .minimumScaleFactor(0.6)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

/// Darkness, the Moon, and the age of the forecast — the three things that
/// qualify the verdict.
struct SkyFacts: View {
    var document: BeaconDocument
    var palette: Palette
    var size: CGFloat = 11

    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            Fact(label: Strings.darkSky, value: darkness, palette: palette, size: size)
            Fact(label: Strings.moon, value: moon, palette: palette,
                 tint: document.moon.interferes ? palette.verdict(.marginal) : nil, size: size)
            Fact(label: Strings.forecast, value: forecast, palette: palette,
                 tint: document.data.stale ? palette.verdict(.marginal) : nil, size: size)
        }
    }

    private var darkness: String {
        let night = document.night
        guard night.hasDarkness,
              let dusk = night.duskAstronomicalLocal ?? night.sunsetLocal,
              let dawn = night.dawnAstronomicalLocal ?? night.sunriseLocal
        else { return Strings.noDarkness }
        return Strings.timeRange(dusk, dawn)
    }

    private var moon: String {
        let percent = Strings.percent(document.moon.illumination * 100)
        let phase = Strings.moonPhase(document.moon.phase)
        return document.moon.interferes
            ? "\(percent) · \(Strings.moonInterferes)"
            : "\(percent) · \(phase)"
    }

    private var forecast: String {
        guard let seconds = document.data.ageSeconds else { return Strings.neverRead }
        return Age.compact(seconds)
    }
}

// MARK: - Empty state

/// What is shown when there is no document at all — which is a different screen
/// from a bad verdict, and must never be mistaken for one.
struct UnreachableView: View {
    var snapshot: BeaconSnapshot
    var palette: Palette
    var compact: Bool = false

    var body: some View {
        VStack(alignment: .leading, spacing: compact ? 3 : 8) {
            HStack(spacing: 6) {
                Image(systemName: "antenna.radiowaves.left.and.right.slash")
                    .font(.system(size: compact ? 14 : 20, weight: .semibold))
                Text(Strings.verdictTitle(.unknown))
                    .font(.system(size: compact ? 17 : 26, weight: .heavy, design: .rounded))
            }
            .foregroundStyle(palette.verdict(.unknown))

            Text(Strings.couldNotReach(host: snapshot.host))
                .font(.system(size: compact ? 10 : 13, weight: .medium))
                .foregroundStyle(palette.text)
                .lineLimit(2)
                .minimumScaleFactor(0.8)

            if let failure = snapshot.failure {
                Text(failure.message)
                    .font(.system(size: compact ? 9 : 11))
                    .foregroundStyle(palette.secondary)
                    .lineLimit(compact ? 2 : 4)
                    .minimumScaleFactor(0.8)
                    .multilineTextAlignment(.leading)
            }
            Spacer(minLength: 0)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}
