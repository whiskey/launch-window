import Foundation

/// One reading, and an honest account of where it came from.
///
/// The beacon's first design rule is that a stale value must never be presented
/// as a current one. That rule has two levels here, and both are carried on
/// this type rather than inferred at the last moment by a view:
///
///   * the *forecast* inside the document can be stale — `data.stale`, which the
///     beacon itself judges;
///   * the *document* can be stale — this client failed to reach the beacon and
///     is showing the last one it managed to read.
///
/// A view that has a snapshot has everything it needs to say which.
struct BeaconSnapshot: Sendable {
    enum Origin: Sendable, Equatable {
        /// Read from the beacon just now.
        case live
        /// The last document that decoded, replayed because the beacon did not answer.
        case cache
        /// Bundled data, for previews and for the widget gallery.
        case sample
    }

    var document: BeaconDocument?
    /// When *this client* obtained the document — distinct from
    /// `document.generatedAt`, which is when the beacon composed it.
    var retrievedAt: Date?
    var host: String
    /// The failure from the most recent attempt, whether or not a cached
    /// document is being shown alongside it.
    var failure: BeaconError?
    var origin: Origin

    init(document: BeaconDocument? = nil,
         retrievedAt: Date? = nil,
         host: String = SharedStore.defaultHost,
         failure: BeaconError? = nil,
         origin: Origin = .live) {
        self.document = document
        self.retrievedAt = retrievedAt
        self.host = host
        self.failure = failure
        self.origin = origin
    }

    /// The verdict, defaulting to `unknown` when there is no document at all —
    /// which is the correct statement in that case, not a pessimistic one.
    var state: VerdictState { document?.verdict.state ?? .unknown }

    /// True when the document on screen is not from this attempt.
    var isReplayed: Bool { origin == .cache }

    /// True when the beacon's own forecast half is out of date.
    var hasStaleForecast: Bool { document?.data.stale ?? false }

    var site: String? { document?.site.name }

    /// How old this client's copy is, right now.
    func age(at now: Date = Date()) -> TimeInterval? {
        retrievedAt.map { now.timeIntervalSince($0) }
    }
}

/// Fetches a reading and keeps the last good one, for both the app and the
/// widget. The fallback is deliberate and one level deep: a failed read shows
/// the previous document, labelled, and never an older one dressed as new.
enum BeaconLoader {
    /// - Parameter timeout: widgets get a shorter leash than the app; a timeline
    ///   provider that blocks is a timeline that does not refresh.
    static func load(host: String, timeout: TimeInterval = 10) async -> BeaconSnapshot {
        let client = BeaconClient(host: host, timeout: timeout)
        do {
            let (document, raw) = try await client.fetch()
            let now = Date()
            SharedStore.store(raw: raw, host: host, at: now)
            return BeaconSnapshot(document: document, retrievedAt: now, host: host, origin: .live)
        } catch {
            let failure = (error as? BeaconError) ?? .unreachable(error.localizedDescription)
            if let cached = SharedStore.loadCached(),
               let document = try? BeaconDocument.decode(from: cached.raw) {
                return BeaconSnapshot(document: document,
                                      retrievedAt: cached.retrievedAt,
                                      host: host,
                                      failure: failure,
                                      origin: .cache)
            }
            return BeaconSnapshot(document: nil, retrievedAt: nil, host: host,
                                  failure: failure, origin: .cache)
        }
    }
}

/// Compact, localised durations: `29 s`, `10 min`, `2 h 33 min`.
///
/// The beacon ships its own rendering of these in `data.age`, but that string is
/// English and formatted on a microcontroller. The seconds behind it are the
/// part worth trusting, so this formats them for the reader's locale instead.
enum Age {
    static func compact(_ seconds: TimeInterval) -> String {
        let total = max(0, Int(seconds.rounded()))
        let duration = Duration.seconds(total)
        if total < 60 {
            return duration.formatted(.units(allowed: [.seconds], width: .abbreviated))
        }
        if total < 3600 {
            return duration.formatted(.units(allowed: [.minutes], width: .abbreviated))
        }
        if total < 86_400 {
            return duration.formatted(.units(allowed: [.hours, .minutes],
                                             width: .abbreviated,
                                             maximumUnitCount: 2))
        }
        return duration.formatted(.units(allowed: [.days, .hours],
                                         width: .abbreviated,
                                         maximumUnitCount: 2))
    }

    /// Clock time in the reader's own zone, for "read 22:14".
    static func clock(_ date: Date) -> String {
        date.formatted(date: .omitted, time: .shortened)
    }
}
