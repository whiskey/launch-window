import Foundation
import Observation
import WidgetKit

/// The app's copy of the reading, and the two things it can ask the beacon to do.
@MainActor
@Observable
final class BeaconModel {
    private(set) var snapshot: BeaconSnapshot
    private(set) var isLoading = false
    /// Set while a `POST /api/v1/refresh` is in flight and we are waiting for
    /// the new forecast to land, which is a slower thing than a reload.
    private(set) var isForcingForecast = false

    var host: String {
        didSet {
            guard host != oldValue else { return }
            SharedStore.host = host
            reloadWidgets()
        }
    }

    /// The toggle's value. Writing it records an explicit choice for every tool
    /// in the astro group — see `SharedStore.nightVision`, where an unset key
    /// deliberately means "no choice yet" rather than "off".
    var nightVision: Bool {
        didSet {
            guard nightVision != oldValue else { return }
            SharedStore.nightVision = nightVision
            reloadWidgets()
        }
    }

    var palette: Palette { Palette(nightVision: nightVision) }

    init() {
        host = SharedStore.host
        nightVision = SharedStore.prefersNightVision
        // Start from the last good reading so the window is never empty while
        // the first request is in flight — labelled as replayed until it is not.
        if let cached = SharedStore.loadCached(),
           let document = try? BeaconDocument.decode(from: cached.raw) {
            snapshot = BeaconSnapshot(document: document,
                                      retrievedAt: cached.retrievedAt,
                                      host: cached.host,
                                      origin: .cache)
        } else {
            snapshot = BeaconSnapshot(host: SharedStore.host)
        }
    }

    #if DEBUG
    /// A model holding a fixed reading. For previews and for the development
    /// gallery, neither of which should depend on a beacon being switched on.
    init(showing snapshot: BeaconSnapshot) {
        host = snapshot.host
        nightVision = false
        self.snapshot = snapshot
    }
    #endif

    func load() async {
        guard !isLoading else { return }
        isLoading = true
        defer { isLoading = false }
        snapshot = await BeaconLoader.load(host: host)
        if snapshot.origin == .live { reloadWidgets() }
    }

    /// Ask the beacon to fetch the forecast now rather than at its next
    /// interval, then read it back.
    ///
    /// The endpoint answers as soon as the fetch is *scheduled*, not when it
    /// completes — so this waits, then reads, and reads once more if the
    /// forecast has not moved yet. It costs the beacon an upstream API call, so
    /// it is a deliberate action and not what pull-to-refresh does.
    func forceForecast() async {
        guard !isForcingForecast else { return }
        isForcingForecast = true
        defer { isForcingForecast = false }

        let before = snapshot.document?.data.fetchedAt
        do {
            try await BeaconClient(host: host).requestRefresh()
        } catch {
            await load()
            return
        }

        for delay in [3.0, 4.0] {
            try? await Task.sleep(for: .seconds(delay))
            await load()
            if let now = snapshot.document?.data.fetchedAt, now != before { return }
        }
    }

    private func reloadWidgets() {
        WidgetCenter.shared.reloadAllTimelines()
    }
}
