import SwiftUI

// PROOF OF CONCEPT — the nights after tonight, one row each.
//
// Deliberately a summary and not a second copy of the main screen: at this size
// the useful questions are "is any of the coming week worth planning for" and
// "when", and every extra number makes those harder to answer at a glance.

struct OutlookSection: View {
    var model: BeaconModel
    var palette: Palette

    var body: some View {
        Panel(title: Strings.outlook, palette: palette) {
            VStack(alignment: .leading, spacing: 10) {
                if let check = model.selfCheck, !check.agrees {
                    // Loud, because everything below is computed by the engine
                    // that just failed to reproduce a verdict it can check.
                    Label(Strings.outlookDisagrees(check.differences.joined(separator: "; ")),
                          systemImage: "exclamationmark.triangle.fill")
                        .font(.system(size: 11, weight: .medium))
                        .foregroundStyle(palette.verdict(.marginal))
                }

                if model.isLoadingOutlook && model.outlook.isEmpty {
                    HStack(spacing: 6) {
                        ProgressView().controlSize(.small)
                        Text(Strings.outlookLoading)
                            .font(.system(size: 12))
                            .foregroundStyle(palette.secondary)
                    }
                } else if let failure = model.outlookFailure {
                    Text(failure)
                        .font(.system(size: 12))
                        .foregroundStyle(palette.verdict(.marginal))
                } else {
                    VStack(spacing: 0) {
                        ForEach(model.outlook) { night in
                            OutlookRow(night: night, palette: palette,
                                       timeZone: model.snapshot.document?.site.timeZone)
                            if night.id != model.outlook.last?.id {
                                Rectangle().fill(palette.grid.opacity(0.5)).frame(height: 1)
                            }
                        }
                    }
                }

                Text(Strings.outlookConfidence)
                    .font(.system(size: 10))
                    .foregroundStyle(palette.faint)
                    .fixedSize(horizontal: false, vertical: true)

                if let check = model.selfCheck, check.agrees {
                    Text(Strings.outlookAgrees)
                        .font(.system(size: 10))
                        .foregroundStyle(palette.faint)
                }
            }
        }
    }
}

struct OutlookRow: View {
    var night: NightOutlook
    var palette: Palette
    var timeZone: TimeZone?

    var body: some View {
        HStack(spacing: 10) {
            VStack(alignment: .leading, spacing: 1) {
                Text(dayLabel)
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(palette.text)
                    .lineLimit(1)
                    .minimumScaleFactor(0.8)
                HStack(spacing: 3) {
                    Image(systemName: MoonSymbol.name(for: night.moonPhase))
                        .font(.system(size: 9))
                    Text(Strings.percent(night.moonIllumination * 100))
                        .font(.system(size: 9))
                        .monospacedDigit()
                }
                .foregroundStyle(night.moonIllumination > 0.5
                                 ? palette.verdict(.marginal) : palette.faint)
            }
            .frame(width: 86, alignment: .leading)

            Image(systemName: VerdictSymbol.name(for: night.verdict.state))
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(palette.verdict(night.verdict.state))

            VStack(alignment: .leading, spacing: 0) {
                Text(windowLabel)
                    .font(.system(size: 12, weight: .semibold, design: .rounded))
                    .monospacedDigit()
                    .foregroundStyle(night.verdict.window == nil ? palette.faint : palette.text)
                    .lineLimit(1)
                    .minimumScaleFactor(0.7)
                Text(Strings.verdictTitle(night.verdict.state))
                    .font(.system(size: 9, weight: .semibold))
                    .foregroundStyle(palette.verdict(night.verdict.state))
            }
            .frame(width: 104, alignment: .leading)

            if night.verdict.hours.isEmpty {
                Spacer(minLength: 0)
            } else {
                HourStrip(hours: night.verdict.hours,
                          window: night.verdict.window,
                          palette: palette,
                          height: 26, barWidth: 9, spacing: 2,
                          showsLabels: false)
                    // Confidence shown as presence, not as a badge: a night
                    // five days out is drawn faintly because that is how much
                    // of it is knowable.
                    .opacity(opacity)
            }
        }
        .padding(.vertical, 7)
    }

    private var opacity: Double {
        switch night.confidence {
        case .firm: return 1.0
        case .fair: return 0.78
        case .vague: return 0.5
        }
    }

    private var dayLabel: String {
        if night.leadDays == 0 { return Strings.tonightLabel }
        var formatter = Date.FormatStyle().weekday(.abbreviated).day().month(.abbreviated)
        // `.timeZone(_:)` on a FormatStyle chooses how to *print* a zone; the
        // zone to format in is the property.
        if let timeZone { formatter.timeZone = timeZone }
        return night.evening.formatted(formatter)
    }

    private var windowLabel: String {
        guard let window = night.verdict.window,
              let start = window.start, let end = window.end else { return Strings.noWindow }
        var clock = Date.FormatStyle(date: .omitted, time: .shortened)
        if let timeZone { clock.timeZone = timeZone }
        return Strings.timeRange(start.formatted(clock), end.formatted(clock))
    }
}
