import Foundation

// PROOF OF CONCEPT — the forecast for the nights the beacon does not fetch.
//
// The beacon asks Open-Meteo for the hours of one night and nothing else, which
// is the right trade on a board with 165 kB of heap. A phone has no such
// problem, so this asks for several days at once and grades them locally.
//
// Same provider as the beacon, deliberately. A different one would be easier to
// reach — WeatherKit is already on the device and needs no client at all — but
// then tonight would come from Open-Meteo via the beacon and tomorrow from
// somewhere else, and the two would disagree in ways no reader could account
// for. One source, one set of weights, one comparable column of nights.
//
// Data by Open-Meteo under CC-BY 4.0. The attribution travels with anything
// published from it, which is why the app carries it at the foot of its screen.
struct OpenMeteo: Sendable {
    /// The variables `verdict.py` grades on. Same names, same provider, so a
    /// row from here and a row from the beacon mean the same thing.
    static let variables = [
        "cloud_cover",
        "cloud_cover_high",
        "temperature_2m",
        "dew_point_2m",
        "wind_gusts_10m",
        "precipitation_probability",
    ]

    var latitude: Double
    var longitude: Double
    var timeout: TimeInterval = 15

    enum Failure: Error, Sendable {
        case badURL
        case unreachable(String)
        case httpStatus(Int)
        case malformed(String)

        var message: String {
            switch self {
            case .badURL:
                return String(localized: "outlook.error.badURL",
                              defaultValue: "The forecast address could not be built.")
            case .unreachable(let reason):
                return String(localized: "outlook.error.unreachable",
                              defaultValue: "Could not reach the forecast: \(reason)")
            case .httpStatus(let code):
                let status = code.formatted(.number.grouping(.never))
                return String(localized: "outlook.error.httpStatus",
                              defaultValue: "The forecast service answered \(status).")
            case .malformed(let detail):
                return String(localized: "outlook.error.malformed",
                              defaultValue: "The forecast could not be read: \(detail)")
            }
        }
    }

    /// Hourly rows for `days` days, in ascending time order.
    ///
    /// `timeformat=unixtime` because every timestamp in this app is a Unix
    /// integer already, and parsing a local-time string back into one is a
    /// timezone bug waiting for a border.
    func hourly(days: Int) async throws -> [VerdictEngine.Row] {
        var components = URLComponents(string: "https://api.open-meteo.com/v1/forecast")
        components?.queryItems = [
            URLQueryItem(name: "latitude", value: String(latitude)),
            URLQueryItem(name: "longitude", value: String(longitude)),
            URLQueryItem(name: "hourly", value: Self.variables.joined(separator: ",")),
            URLQueryItem(name: "timeformat", value: "unixtime"),
            URLQueryItem(name: "timezone", value: "UTC"),
            URLQueryItem(name: "forecast_days", value: String(max(1, min(16, days)))),
        ]
        guard let url = components?.url else { throw Failure.badURL }

        let configuration = URLSessionConfiguration.ephemeral
        configuration.timeoutIntervalForRequest = timeout
        configuration.timeoutIntervalForResource = timeout
        configuration.requestCachePolicy = .reloadIgnoringLocalAndRemoteCacheData
        configuration.urlCache = nil
        let session = URLSession(configuration: configuration)

        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(from: url)
        } catch let error as URLError {
            throw Failure.unreachable(error.localizedDescription)
        }
        if let http = response as? HTTPURLResponse, !(200 ..< 300).contains(http.statusCode) {
            throw Failure.httpStatus(http.statusCode)
        }
        return try Self.rows(from: data)
    }

    static func rows(from data: Data) throws -> [VerdictEngine.Row] {
        guard let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw Failure.malformed("not an object")
        }
        guard let hourly = object["hourly"] as? [String: Any] else {
            throw Failure.malformed("no hourly block")
        }
        guard let times = (hourly["time"] as? [Any])?.compactMap({ ($0 as? NSNumber)?.intValue }) else {
            throw Failure.malformed("no hourly times")
        }

        /// Open-Meteo writes a missing value as JSON null, which must stay nil.
        /// A hole in the cloud series is an hour that cannot be graded, and
        /// turning it into a zero would invent a clear sky.
        func series(_ name: String) -> [Double?] {
            let raw = hourly[name] as? [Any] ?? []
            return raw.map { ($0 as? NSNumber)?.doubleValue }
        }
        let cloud = series("cloud_cover")
        let high = series("cloud_cover_high")
        let temperature = series("temperature_2m")
        let dew = series("dew_point_2m")
        let gusts = series("wind_gusts_10m")
        let precipitation = series("precipitation_probability")

        func value(_ column: [Double?], _ index: Int) -> Double? {
            index < column.count ? column[index] : nil
        }
        return times.enumerated().map { index, timestamp in
            VerdictEngine.Row(timestamp: timestamp,
                              cloudCover: value(cloud, index),
                              cloudCoverHigh: value(high, index),
                              windGusts: value(gusts, index),
                              temperature: value(temperature, index),
                              dewPoint: value(dew, index),
                              precipitationProbability: value(precipitation, index))
        }
    }
}
