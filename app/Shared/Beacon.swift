import Foundation

// The document served at `GET /api/v1/beacon`, protocol version 1.
//
// Mapped field by field against `protocol/beacon-v1.md` — the coding keys are
// written out rather than derived, so this file can be read side by side with
// the spec. Three rules from that document shape everything below:
//
//   * **Ignore unknown fields.** New ones may appear within version 1, so
//     decoding must never fail because the beacon knows something we do not.
//   * **Nulls are honest.** Every nullable field is an Optional and stays one.
//     A missing score is not a zero, and `unknown` is not `no-go`.
//   * **Additive only.** A field that disappears or changes type means the
//     beacon has moved to `/api/v2`, and this type would be replaced wholesale.
//
// These are decode-only. The cache stores the bytes the beacon actually sent,
// so fields this client does not model survive a round trip untouched.

// MARK: - Verdict state

/// The four answers the beacon is willing to give.
///
/// `unknown` is not a bad night — it means the beacon has no forecast and is
/// saying so. Anything unrecognised decodes to `unknown` for the same reason:
/// a client that resolves its own ignorance into a confident verdict is worse
/// than one that admits it.
enum VerdictState: String, Decodable, Hashable, Sendable, CaseIterable {
    case go
    case marginal
    case noGo = "no-go"
    case unknown

    init(from decoder: Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        self = VerdictState(rawValue: raw) ?? .unknown
    }
}

/// Which definition of darkness the verdict was graded against.
enum Darkness: String, Decodable, Hashable, Sendable {
    case astronomical
    case nautical
    case none

    init(from decoder: Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        self = Darkness(rawValue: raw) ?? .none
    }
}

// MARK: - Document

struct BeaconDocument: Decodable, Hashable, Sendable {
    let schema: Int
    let generatedAt: Date?
    let generatedLocal: String?
    let beacon: BeaconInfo
    let clock: ClockInfo
    let site: Site
    let night: Night
    let moon: Moon
    let verdict: Verdict
    let data: DataInfo

    enum CodingKeys: String, CodingKey {
        case schema
        case generatedAt = "generated_at"
        case generatedLocal = "generated_local"
        case beacon, clock, site, night, moon, verdict, data
    }
}

struct BeaconInfo: Decodable, Hashable, Sendable {
    let host: String
    let firmwareVersion: String
    let uptimeSeconds: Double?
    let uptime: String?
    let coreTemperatureC: Double?
    let signalDBM: Double?
    let address: String?

    enum CodingKeys: String, CodingKey {
        case host
        case firmwareVersion = "firmware_version"
        case uptimeSeconds = "uptime_s"
        case uptime
        case coreTemperatureC = "core_temp_c"
        case signalDBM = "signal_dbm"
        case address
    }
}

struct ClockInfo: Decodable, Hashable, Sendable {
    /// False means every timestamp in the document is unreliable: the RP2040
    /// has no battery-backed clock and boots believing it is 2021.
    let synced: Bool
    let lastSync: Date?

    enum CodingKeys: String, CodingKey {
        case synced
        case lastSync = "last_sync"
    }
}

struct Site: Decodable, Hashable, Sendable {
    let name: String?
    let latitude: Double
    let longitude: Double
    let timezone: String?

    /// The site's own zone, for the few places this client formats a date
    /// itself. Display otherwise uses the beacon's `*_local` strings, which are
    /// already rendered in this zone.
    var timeZone: TimeZone? {
        timezone.flatMap(TimeZone.init(identifier:))
    }
}

struct Night: Decodable, Hashable, Sendable {
    let darkness: Darkness?
    let sunset: Date?
    let sunsetLocal: String?
    let duskAstronomical: Date?
    let duskAstronomicalLocal: String?
    let dawnAstronomical: Date?
    let dawnAstronomicalLocal: String?
    let sunrise: Date?
    let sunriseLocal: String?
    let darkSeconds: Double
    let darkDuration: String?
    let darkStart: Date?
    let darkEnd: Date?

    enum CodingKeys: String, CodingKey {
        case darkness, sunset, sunrise
        case sunsetLocal = "sunset_local"
        case duskAstronomical = "dusk_astronomical"
        case duskAstronomicalLocal = "dusk_astronomical_local"
        case dawnAstronomical = "dawn_astronomical"
        case dawnAstronomicalLocal = "dawn_astronomical_local"
        case sunriseLocal = "sunrise_local"
        case darkSeconds = "dark_seconds"
        case darkDuration = "dark_duration"
        case darkStart = "dark_start"
        case darkEnd = "dark_end"
    }

    /// True when the Sun never reached the grading depth — at 52 degrees north
    /// there is genuinely no astronomical night for several weeks in midsummer.
    var hasDarkness: Bool { darkSeconds > 0 }
}

struct Moon: Decodable, Hashable, Sendable {
    /// Illuminated fraction, 0...1.
    let illumination: Double
    /// One of eight named phases. Kept as the raw string so an unrecognised
    /// value renders as itself instead of being silently reshaped.
    let phase: String
    let altitudeDegrees: Double?
    let rise: Date?
    let riseLocal: String?
    let set: Date?
    let setLocal: String?
    /// True when the Moon is above the horizon during the dark window and
    /// bright enough to matter.
    let interferes: Bool

    enum CodingKeys: String, CodingKey {
        case illumination, phase, rise, set, interferes
        case altitudeDegrees = "altitude_deg"
        case riseLocal = "rise_local"
        case setLocal = "set_local"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        illumination = try c.decode(Double.self, forKey: .illumination)
        phase = try c.decode(String.self, forKey: .phase)
        altitudeDegrees = try c.decodeIfPresent(Double.self, forKey: .altitudeDegrees)
        rise = try c.decodeIfPresent(Date.self, forKey: .rise)
        riseLocal = try c.decodeIfPresent(String.self, forKey: .riseLocal)
        set = try c.decodeIfPresent(Date.self, forKey: .set)
        setLocal = try c.decodeIfPresent(String.self, forKey: .setLocal)
        // Not in the schema's required list, so treat absence as "does not".
        interferes = try c.decodeIfPresent(Bool.self, forKey: .interferes) ?? false
    }
}

struct Verdict: Decodable, Hashable, Sendable {
    let state: VerdictState
    /// Mean score across the dark hours. The verdict is decided by the best
    /// run, not by this — see `window`.
    let score: Double?
    let reasons: [String]
    /// Null unless the recommendation is to go outside. A rejected stretch is
    /// described in `reasons` instead.
    let window: ObservingWindow?
    let hours: [ForecastHour]
}

struct ObservingWindow: Decodable, Hashable, Sendable {
    let start: Date?
    let end: Date?
    let startLocal: String?
    let endLocal: String?
    let hours: Double
    let meanScore: Double?

    enum CodingKeys: String, CodingKey {
        case start, end, hours
        case startLocal = "start_local"
        case endLocal = "end_local"
        case meanScore = "mean_score"
    }
}

/// One forecast hour overlapping the dark window, carrying both the grade and
/// the values behind it.
struct ForecastHour: Decodable, Hashable, Sendable, Identifiable {
    let timestamp: Double
    let time: Date?
    let local: String?
    /// Null when the hour could not be graded. Never a zero standing in for
    /// missing data — an ungraded hour is excluded from the night, not counted
    /// as a clear one.
    let score: Double?
    let penalties: [String: Double]
    let veto: String?
    let moonAltitudeDegrees: Double?
    let cloudCover: Double?
    let cloudCoverHigh: Double?
    let windGusts: Double?
    let temperature: Double?
    let dewPoint: Double?
    let precipitationProbability: Double?

    var id: Double { timestamp }

    /// Temperature/dew-point spread in kelvin, which is what actually predicts
    /// dew. Nil unless both halves arrived.
    var dewSpread: Double? {
        guard let temperature, let dewPoint else { return nil }
        return temperature - dewPoint
    }

    var isVetoed: Bool { veto != nil }

    enum CodingKeys: String, CodingKey {
        case ts, time, local, score, penalties, veto
        case moonAltitudeDegrees = "moon_alt_deg"
        case cloudCover = "cloud_cover"
        case cloudCoverHigh = "cloud_cover_high"
        case windGusts = "wind_gusts_10m"
        case temperature = "temperature_2m"
        case dewPoint = "dew_point_2m"
        case precipitationProbability = "precipitation_probability"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        timestamp = try c.decode(Double.self, forKey: .ts)
        time = try c.decodeIfPresent(Date.self, forKey: .time)
        local = try c.decodeIfPresent(String.self, forKey: .local)
        score = try c.decodeIfPresent(Double.self, forKey: .score)
        // The schema constrains `penalties` to an object but not its values.
        // A shape we cannot read costs us a tooltip, never the whole document.
        penalties = (try? c.decodeIfPresent([String: Double].self, forKey: .penalties)) ?? [:]
        veto = try c.decodeIfPresent(String.self, forKey: .veto)
        moonAltitudeDegrees = try c.decodeIfPresent(Double.self, forKey: .moonAltitudeDegrees)
        cloudCover = try c.decodeIfPresent(Double.self, forKey: .cloudCover)
        cloudCoverHigh = try c.decodeIfPresent(Double.self, forKey: .cloudCoverHigh)
        windGusts = try c.decodeIfPresent(Double.self, forKey: .windGusts)
        temperature = try c.decodeIfPresent(Double.self, forKey: .temperature)
        dewPoint = try c.decodeIfPresent(Double.self, forKey: .dewPoint)
        precipitationProbability = try c.decodeIfPresent(Double.self, forKey: .precipitationProbability)
    }
}

struct DataInfo: Decodable, Hashable, Sendable {
    let source: String
    let fetchedAt: Date?
    let ageSeconds: Double?
    let age: String?
    /// True when the forecast is older than two hours or never arrived.
    /// Clients must distinguish stale from current visibly.
    let stale: Bool
    /// True when the forecast was restored from flash after a reboot rather
    /// than fetched in this session.
    let fromFlashCache: Bool
    let error: String?

    enum CodingKeys: String, CodingKey {
        case source, age, stale, error
        case fetchedAt = "fetched_at"
        case ageSeconds = "age_s"
        case fromFlashCache = "from_flash_cache"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        source = try c.decode(String.self, forKey: .source)
        fetchedAt = try c.decodeIfPresent(Date.self, forKey: .fetchedAt)
        ageSeconds = try c.decodeIfPresent(Double.self, forKey: .ageSeconds)
        age = try c.decodeIfPresent(String.self, forKey: .age)
        stale = try c.decode(Bool.self, forKey: .stale)
        fromFlashCache = try c.decodeIfPresent(Bool.self, forKey: .fromFlashCache) ?? false
        error = try c.decodeIfPresent(String.self, forKey: .error)
    }
}

// MARK: - Decoding

extension BeaconDocument {
    /// The decoder this protocol needs: ISO-8601 timestamps, with or without
    /// fractional seconds, and unknown keys ignored (which `Decodable` does by
    /// construction).
    static func decoder() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .custom { decoder in
            let raw = try decoder.singleValueContainer().decode(String.self)
            guard let date = ISO8601.date(from: raw) else {
                throw DecodingError.dataCorrupted(
                    .init(codingPath: decoder.codingPath,
                          debugDescription: "not an ISO-8601 timestamp: \(raw)")
                )
            }
            return date
        }
        return decoder
    }

    static func decode(from data: Data) throws -> BeaconDocument {
        try decoder().decode(BeaconDocument.self, from: data)
    }
}

private enum ISO8601 {
    nonisolated(unsafe) private static let withFraction: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter
    }()

    nonisolated(unsafe) private static let plain: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        return formatter
    }()

    static func date(from raw: String) -> Date? {
        plain.date(from: raw) ?? withFraction.date(from: raw)
    }
}
