import SwiftUI

// The four system widget sizes.
//
// They live here, beside the pieces they are built from, and they take a
// snapshot and a palette rather than a WidgetKit timeline entry. Two things
// follow from that: they can be rendered and looked at without a widget host,
// and the app and the widget cannot drift into describing the same night
// differently, because there is only one description.
//
// They are not one view scaled four ways. Each size answers a different
// question:
//
//   * **Small** — the verdict and the window. Nothing that cannot be read while
//     walking past it.
//   * **Medium** — adds the night hour by hour, which is what turns "no" into
//     "no, because it only clears after three".
//   * **Large** — adds the reasons, and the sky they are about.
//   * **Extra large** — adds the numbers each hour was graded from, so the
//     verdict can be argued with.

// MARK: - Small

struct SmallVerdict: View {
    var snapshot: BeaconSnapshot
    var palette: Palette

    var body: some View {
        if let document = snapshot.document {
            VStack(alignment: .leading, spacing: 4) {
                VerdictHeadline(state: document.verdict.state, palette: palette,
                                size: 25, showsMeaning: false)

                WindowLine(verdict: document.verdict, palette: palette, size: 15)

                Spacer(minLength: 2)

                if document.verdict.hours.isEmpty {
                    Text(Reasons.localized(document.verdict.reasons.first ?? Strings.noGradedHours))
                        .font(.system(size: 9))
                        .foregroundStyle(palette.secondary)
                        .lineLimit(2)
                        .minimumScaleFactor(0.8)
                } else {
                    HourStrip(hours: document.verdict.hours,
                              window: document.verdict.window,
                              palette: palette,
                              height: 26, barWidth: 10, spacing: 2,
                              showsLabels: false)
                }

                FreshnessLine(snapshot: snapshot, palette: palette, size: 8)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        } else {
            UnreachableView(snapshot: snapshot, palette: palette, compact: true)
        }
    }
}

// MARK: - Medium

struct MediumVerdict: View {
    var snapshot: BeaconSnapshot
    var palette: Palette

    var body: some View {
        if let document = snapshot.document {
            HStack(alignment: .top, spacing: 12) {
                VStack(alignment: .leading, spacing: 4) {
                    VerdictHeadline(state: document.verdict.state, palette: palette, size: 26)
                    WindowLine(verdict: document.verdict, palette: palette, size: 16)
                    Spacer(minLength: 0)
                    FreshnessLine(snapshot: snapshot, palette: palette, size: 9)
                }
                .frame(width: 122, alignment: .leading)

                VStack(alignment: .leading, spacing: 5) {
                    StatusBanner(snapshot: snapshot, palette: palette, size: 9)

                    if document.verdict.hours.isEmpty {
                        Spacer(minLength: 0)
                    } else {
                        HourStrip(hours: document.verdict.hours,
                                  window: document.verdict.window,
                                  palette: palette,
                                  height: 54, barWidth: 16, spacing: 3, labelSize: 8,
                                  labelEvery: document.verdict.hours.count > 10 ? 2 : 1)
                    }

                    ReasonList(reasons: document.verdict.reasons, palette: palette,
                               size: 9.5, limit: 2)
                    Spacer(minLength: 0)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        } else {
            UnreachableView(snapshot: snapshot, palette: palette)
        }
    }
}

// MARK: - Large

struct LargeVerdict: View {
    var snapshot: BeaconSnapshot
    var palette: Palette

    var body: some View {
        if let document = snapshot.document {
            VStack(alignment: .leading, spacing: 9) {
                HStack(alignment: .top) {
                    VerdictHeadline(state: document.verdict.state, palette: palette, size: 34)
                    Spacer(minLength: 6)
                    ScoreBadge(verdict: document.verdict, palette: palette)
                }

                WindowLine(verdict: document.verdict, palette: palette, size: 21)

                StatusBanner(snapshot: snapshot, palette: palette, size: 10)

                if document.verdict.hours.isEmpty {
                    Text(Strings.noGradedHours)
                        .font(.system(size: 11))
                        .foregroundStyle(palette.faint)
                        .frame(maxWidth: .infinity, alignment: .leading)
                } else {
                    HourStrip(hours: document.verdict.hours,
                              window: document.verdict.window,
                              palette: palette,
                              height: 86, barWidth: 22, spacing: 4, labelSize: 9,
                              labelEvery: document.verdict.hours.count > 12 ? 2 : 1)
                }

                ReasonList(reasons: document.verdict.reasons, palette: palette, size: 11, limit: 3)

                Spacer(minLength: 0)

                Rectangle().fill(palette.grid).frame(height: 1)

                SkyFacts(document: document, palette: palette, size: 12)

                FreshnessLine(snapshot: snapshot, palette: palette, size: 9.5)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        } else {
            UnreachableView(snapshot: snapshot, palette: palette)
        }
    }
}

// MARK: - Extra large

struct ExtraLargeVerdict: View {
    var snapshot: BeaconSnapshot
    var palette: Palette

    var body: some View {
        if let document = snapshot.document {
            HStack(alignment: .top, spacing: 18) {
                VStack(alignment: .leading, spacing: 10) {
                    HStack(alignment: .top) {
                        VerdictHeadline(state: document.verdict.state, palette: palette, size: 40)
                        Spacer(minLength: 6)
                        ScoreBadge(verdict: document.verdict, palette: palette)
                    }
                    WindowLine(verdict: document.verdict, palette: palette, size: 24)
                    StatusBanner(snapshot: snapshot, palette: palette, size: 11)
                    ReasonList(reasons: document.verdict.reasons, palette: palette, size: 12, limit: 4)
                    Spacer(minLength: 0)
                    Rectangle().fill(palette.grid).frame(height: 1)
                    SkyFacts(document: document, palette: palette, size: 13)
                    FreshnessLine(snapshot: snapshot, palette: palette, size: 10)
                }
                .frame(maxWidth: .infinity, alignment: .leading)

                VStack(alignment: .leading, spacing: 8) {
                    if document.verdict.hours.isEmpty {
                        Text(Strings.noGradedHours)
                            .font(.system(size: 12))
                            .foregroundStyle(palette.faint)
                    } else {
                        HourStrip(hours: document.verdict.hours,
                                  window: document.verdict.window,
                                  palette: palette,
                                  height: 96, barWidth: 26, spacing: 5, labelSize: 10)
                        HourTable(hours: document.verdict.hours, palette: palette)
                    }
                    Spacer(minLength: 0)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        } else {
            UnreachableView(snapshot: snapshot, palette: palette)
        }
    }
}
