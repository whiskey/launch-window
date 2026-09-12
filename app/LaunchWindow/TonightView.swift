import SwiftUI

/// The whole answer, at the one size where there is room for all of it.
///
/// The widgets are summaries of this screen; this screen is where the verdict
/// can be checked against the numbers it was derived from.
struct TonightView: View {
    @Bindable var model: BeaconModel
    @State private var isShowingSettings = false
    @Environment(\.scenePhase) private var scenePhase

    private var palette: Palette { model.palette }

    var body: some View {
        NavigationStack {
            content
            .navigationTitle(model.snapshot.site ?? Strings.appName)
            #if os(iOS)
            .navigationBarTitleDisplayMode(.inline)
            #endif
            .toolbar {
                ToolbarItem(placement: .primaryAction) {
                    Button {
                        Task { await model.load() }
                    } label: {
                        Label(Strings.refresh, systemImage: "arrow.clockwise")
                    }
                    .disabled(model.isLoading)
                }
                ToolbarItem(placement: .primaryAction) {
                    Button {
                        isShowingSettings = true
                    } label: {
                        Label(Strings.settings, systemImage: "gearshape")
                    }
                }
            }
            .refreshable { await model.load() }
            .sheet(isPresented: $isShowingSettings) {
                SettingsView(model: model)
            }
        }
        .tint(palette.verdict(model.snapshot.state))
        .task { await model.load() }
        .onChange(of: scenePhase) { _, phase in
            // A reading that is minutes old is not worth showing when the app
            // comes back to the front; the sky moves.
            if phase == .active { Task { await model.load() } }
        }
    }

    // MARK: - Sections

    /// Everything the screen says, without the navigation stack around it.
    var content: some View {
        ScrollView { panels }
            .background(palette.background)
            .scrollContentBackground(.hidden)
    }

    /// The panels alone. Split out from `content` because a scroll view lays
    /// its children out against a viewport, and the development gallery has no
    /// viewport to give it — this is the form that can be drawn to a file.
    var panels: some View {
        VStack(alignment: .leading, spacing: 16) {
            if let document = model.snapshot.document {
                verdict(document)
                banner
                night(document)
                reasons(document)
                OutlookSection(model: model, palette: palette)
                sky(document)
                beacon(document)
            } else {
                UnreachableView(snapshot: model.snapshot, palette: palette)
                    .padding(.top, 40)
                Button(Strings.openSettings) { isShowingSettings = true }
                    .buttonStyle(.bordered)
            }
            footer
        }
        .padding(18)
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func verdict(_ document: BeaconDocument) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .top) {
                VerdictHeadline(state: document.verdict.state, palette: palette, size: 42)
                Spacer(minLength: 8)
                ScoreBadge(verdict: document.verdict, palette: palette)
            }
            WindowLine(verdict: document.verdict, palette: palette, size: 26)
        }
    }

    @ViewBuilder
    private var banner: some View {
        StatusBanner(snapshot: model.snapshot, palette: palette, size: 12)
    }

    @ViewBuilder
    private func night(_ document: BeaconDocument) -> some View {
        if document.verdict.hours.isEmpty {
            Panel(title: Strings.tonight, palette: palette) {
                Text(document.night.hasDarkness ? Strings.noGradedHours : Strings.noDarkness)
                    .font(.system(size: 13))
                    .foregroundStyle(palette.secondary)
            }
        } else {
            Panel(title: Strings.tonight, palette: palette) {
                VStack(alignment: .leading, spacing: 14) {
                    HourStrip(hours: document.verdict.hours,
                              window: document.verdict.window,
                              palette: palette,
                              height: 110, barWidth: 28, spacing: 5, labelSize: 10,
                              labelEvery: document.verdict.hours.count > 12 ? 2 : 1)
                    .frame(maxWidth: .infinity, alignment: .leading)

                    HourTable(hours: document.verdict.hours,
                              palette: palette,
                              limit: document.verdict.hours.count)
                }
            }
        }
    }

    @ViewBuilder
    private func reasons(_ document: BeaconDocument) -> some View {
        if !document.verdict.reasons.isEmpty {
            Panel(title: Strings.reasons, palette: palette) {
                ReasonList(reasons: document.verdict.reasons, palette: palette,
                           size: 13, limit: document.verdict.reasons.count)
            }
        }
    }

    private func sky(_ document: BeaconDocument) -> some View {
        Panel(title: Strings.darkSky, palette: palette) {
            VStack(alignment: .leading, spacing: 12) {
                HStack(alignment: .top, spacing: 10) {
                    Fact(label: Strings.sunset, value: document.night.sunsetLocal ?? "—",
                         palette: palette, size: 13)
                    Fact(label: Strings.dusk, value: document.night.duskAstronomicalLocal ?? "—",
                         palette: palette, size: 13)
                    Fact(label: Strings.dawn, value: document.night.dawnAstronomicalLocal ?? "—",
                         palette: palette, size: 13)
                    Fact(label: Strings.sunrise, value: document.night.sunriseLocal ?? "—",
                         palette: palette, size: 13)
                }
                HStack(alignment: .top, spacing: 10) {
                    Fact(label: Strings.hours,
                         value: document.night.darkDuration.map(darkDuration) ?? Strings.noDarkness,
                         palette: palette, size: 13)
                    Fact(label: Strings.darkSky,
                         value: document.night.darkness.map(Strings.darkness) ?? Strings.darkness(.none),
                         palette: palette, size: 13)
                    Fact(label: Strings.moon, value: moon(document.moon), palette: palette,
                         tint: document.moon.interferes ? palette.verdict(.marginal) : nil,
                         size: 13)
                }
            }
        }
    }

    private func beacon(_ document: BeaconDocument) -> some View {
        Panel(title: Strings.beacon, palette: palette) {
            HStack(alignment: .top, spacing: 10) {
                Fact(label: Strings.forecast,
                     value: document.data.ageSeconds.map(Age.compact) ?? Strings.neverRead,
                     palette: palette,
                     tint: document.data.stale ? palette.verdict(.marginal) : nil,
                     size: 13)
                Fact(label: Strings.uptime, value: document.beacon.uptime ?? "—",
                     palette: palette, size: 13)
                Fact(label: Strings.signal,
                     value: document.beacon.signalDBM.map(Strings.decibelMilliwatts) ?? "—",
                     palette: palette, size: 13)
                Fact(label: Strings.temperature,
                     value: document.beacon.coreTemperatureC.map(Strings.degreesCelsius) ?? "—",
                     palette: palette, size: 13)
            }
        }
    }

    private var footer: some View {
        VStack(alignment: .leading, spacing: 8) {
            FreshnessLine(snapshot: model.snapshot, palette: palette, size: 11, showsSite: false)

            Button {
                Task { await model.forceForecast() }
            } label: {
                HStack(spacing: 6) {
                    if model.isForcingForecast {
                        ProgressView().controlSize(.small)
                    } else {
                        Image(systemName: "arrow.down.circle")
                    }
                    Text(Strings.fetchForecastNow)
                }
                .font(.system(size: 12, weight: .medium))
            }
            // .plain rather than .borderless: the borderless style is drawn
            // differently on each platform, and this row is a quiet link, not a
            // control that should announce itself.
            .buttonStyle(.plain)
            .foregroundStyle(model.isForcingForecast ? palette.faint : palette.secondary)
            .disabled(model.isForcingForecast || model.snapshot.document == nil)

            Text(Strings.attribution)
                .font(.system(size: 10))
                .foregroundStyle(palette.faint)
        }
        .padding(.top, 4)
    }

    // MARK: -

    /// The beacon renders this one itself (`7 h 06 min`); it is passed through
    /// rather than re-derived, because `dark_seconds` and that string are the
    /// same fact and only one of them is the device's own wording.
    private func darkDuration(_ value: String) -> String { value }

    private func moon(_ moon: Moon) -> String {
        let percent = Strings.percent(moon.illumination * 100)
        return "\(percent) · \(Strings.moonPhase(moon.phase))"
    }
}

/// A titled block. The app is a stack of these; the widgets are not, because at
/// widget sizes a title costs more than it explains.
struct Panel<Content: View>: View {
    var title: String
    var palette: Palette
    @ViewBuilder var content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(title.uppercased())
                .font(.system(size: 10, weight: .semibold))
                .tracking(0.8)
                .foregroundStyle(palette.faint)
            content
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .fill(palette.surface)
        )
    }
}

// Previews are DEBUG-only: they use the seeded initialiser, which is too.
#if DEBUG
#Preview("GO") {
    TonightView(model: BeaconModel(showing: SampleBeacon.snapshot(SampleBeacon.go)))
        .preferredColorScheme(.dark)
}

#Preview("NO-GO") {
    TonightView(model: BeaconModel(showing: SampleBeacon.snapshot(SampleBeacon.noGo)))
        .preferredColorScheme(.dark)
}

#Preview("Unreachable") {
    TonightView(model: BeaconModel(showing: BeaconSnapshot(
        host: "launch-window.home",
        failure: .httpStatus(code: 500,
                             body: "handler failed: memory allocation failed, allocating 4088 bytes"),
        origin: .cache)))
        .preferredColorScheme(.dark)
}
#endif
