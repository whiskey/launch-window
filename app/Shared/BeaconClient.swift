import Foundation

/// What went wrong reaching the beacon, in terms a person standing in a garden
/// can act on. Every case says which half failed — the network, the device, or
/// the contract — because the remedies are completely different.
enum BeaconError: Error, Hashable, Sendable {
    /// The host string could not be turned into a URL at all.
    case badHost(String)
    /// The request never completed: no route, no DNS, refused, timed out.
    case unreachable(String)
    /// The beacon answered, but not with success. Carries the status and
    /// whatever short body it sent — the firmware puts its reason there, and
    /// "memory allocation failed" is a very different problem from a 404.
    case httpStatus(code: Int, body: String?)
    /// The bytes arrived but are not the document we were promised.
    case malformed(String)
    /// A major version this client does not implement.
    case unsupportedSchema(Int)

    /// Already localised. Render with `Text(_:)`, which does not translate an
    /// ordinary `String` a second time.
    var message: String {
        switch self {
        case .badHost(let host):
            return String(localized: "error.badHost",
                          defaultValue: "‘\(host)’ is not a usable address.")
        case .unreachable(let reason):
            return String(localized: "error.unreachable",
                          defaultValue: "Could not reach the beacon: \(reason)")
        case .httpStatus(let code, let body):
            let status = code.formatted(.number.grouping(.never))
            if let body, !body.isEmpty {
                return String(localized: "error.httpStatusWithBody",
                              defaultValue: "The beacon answered \(status): \(body)")
            }
            return String(localized: "error.httpStatus",
                          defaultValue: "The beacon answered \(status).")
        case .malformed(let detail):
            return String(localized: "error.malformed",
                          defaultValue: "The beacon's answer could not be read: \(detail)")
        case .unsupportedSchema(let schema):
            let version = schema.formatted(.number.grouping(.never))
            return String(localized: "error.unsupportedSchema",
                          defaultValue: "This beacon speaks protocol \(version); this app speaks 1.")
        }
    }

    /// True when the beacon itself answered: it is on the network, and the
    /// fault is in what it sent rather than in getting there. Calling that
    /// "unreachable" sends its owner off to debug the WiFi instead of the board.
    var beaconAnswered: Bool {
        switch self {
        case .httpStatus, .malformed, .unsupportedSchema: return true
        case .badHost, .unreachable: return false
        }
    }

    /// True when retrying later might plausibly work, which is what decides
    /// whether the widget schedules a short or a long retry.
    var isTransient: Bool {
        switch self {
        case .unreachable, .httpStatus: return true
        case .badHost, .malformed, .unsupportedSchema: return false
        }
    }
}

/// Talks to one beacon over plain HTTP on the local network.
///
/// There is no TLS here and there will not be: the other end is a Pico W with
/// 264 kB of RAM that cannot terminate it, on a network you control. See the
/// app's `Info.plist` for the matching transport-security exception.
struct BeaconClient: Sendable {
    /// The protocol major version this client implements.
    static let supportedSchema = 1

    /// Whatever the user typed: a hostname, a hostname with a port, or a full
    /// URL. Normalisation happens in `url(path:)`.
    var host: String
    var timeout: TimeInterval

    init(host: String, timeout: TimeInterval = 10) {
        self.host = host
        self.timeout = timeout
    }

    private var session: URLSession {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.timeoutIntervalForRequest = timeout
        configuration.timeoutIntervalForResource = timeout
        // Never let a cached copy masquerade as a fresh reading. The beacon
        // sends no-store, but this client should not depend on that.
        configuration.requestCachePolicy = .reloadIgnoringLocalAndRemoteCacheData
        configuration.urlCache = nil
        configuration.waitsForConnectivity = false
        // No proxy, for a device that is three metres away on the same wire.
        //
        // iCloud Private Relay proxies exactly two kinds of traffic: Safari, and
        // plain HTTP from any app — which is all this client speaks. It is meant
        // to leave local destinations alone, but it decides that from the name,
        // and `launch-window.home` is a fully-qualified name in an ordinary TLD.
        // Before the system has resolved it to a private address, the relay can
        // take the request, fail to find the host on the public internet, and
        // answer 502 — which reaches us as "Could not connect to the server"
        // for a beacon that is switched on and answering.
        configuration.connectionProxyDictionary = [:]
        return URLSession(configuration: configuration)
    }

    /// Accepts `launch-window.home`, `launch-window.home:8080`,
    /// `http://10.1.10.84`, or any of those with a trailing slash.
    func url(path: String) throws -> URL {
        let trimmed = host.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { throw BeaconError.badHost(host) }

        let base = trimmed.contains("://") ? trimmed : "http://\(trimmed)"
        guard var components = URLComponents(string: base), let scheme = components.scheme,
              let hostname = components.host, !hostname.isEmpty,
              scheme == "http" || scheme == "https"
        else { throw BeaconError.badHost(host) }

        // Discard whatever path the user's entry carried; we own the API path.
        components.path = path
        components.query = nil
        components.fragment = nil
        guard let url = components.url else { throw BeaconError.badHost(host) }
        return url
    }

    /// `GET /api/v1/beacon` — the full document, and the raw bytes behind it.
    ///
    /// The bytes are returned alongside the decoded value so the cache can
    /// store exactly what the beacon sent, fields this client does not model
    /// included.
    func fetch() async throws -> (document: BeaconDocument, raw: Data) {
        let data = try await get(path: "/api/v1/beacon")
        let document: BeaconDocument
        do {
            document = try BeaconDocument.decode(from: data)
        } catch {
            throw BeaconError.malformed(Self.describe(decoding: error))
        }
        guard document.schema == Self.supportedSchema else {
            throw BeaconError.unsupportedSchema(document.schema)
        }
        return (document, data)
    }

    /// `GET /api/v1/health` — the cheap liveness check that computes nothing.
    /// Useful when `/beacon` itself is failing, to tell a dead board apart from
    /// a board that cannot allocate the document.
    func health() async throws -> Bool {
        let data = try await get(path: "/api/v1/health")
        let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        return (object?["ok"] as? Bool) ?? false
    }

    /// `POST /api/v1/refresh` — fetch the forecast now instead of waiting for
    /// the next interval.
    ///
    /// Returns as soon as the fetch is *scheduled*, not when it completes; the
    /// caller polls `data.fetched_at` to see it land. `GET` is deliberately a
    /// 405 on the device, because refreshing costs an upstream API call.
    func requestRefresh() async throws {
        var request = URLRequest(url: try url(path: "/api/v1/refresh"))
        request.httpMethod = "POST"
        request.setValue("0", forHTTPHeaderField: "Content-Length")
        _ = try await perform(request)
    }

    // MARK: - Plumbing

    private func get(path: String) async throws -> Data {
        var request = URLRequest(url: try url(path: path))
        request.httpMethod = "GET"
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        return try await perform(request)
    }

    private func perform(_ request: URLRequest) async throws -> Data {
        do {
            return try await send(request)
        } catch let error as BeaconError {
            // One retry, against the address rather than the name.
            //
            // Disabling proxies above should be enough, but it is a request to
            // the networking stack rather than a guarantee, and the failure it
            // guards against is intermittent and invisible: the widget refreshes
            // while nobody is watching and quietly shows UNKNOWN. A literal
            // RFC 1918 address cannot be mistaken for a public destination by
            // anything, so resolving the name ourselves — through the system
            // resolver, which is the one that knows about this network — closes
            // the hole rather than narrowing it.
            guard case .unreachable = error,
                  let address = await Self.privateAddress(for: request.url),
                  let retry = Self.rewrite(request, to: address)
            else { throw error }
            return try await send(retry)
        }
    }

    private func send(_ request: URLRequest) async throws -> Data {
        #if DEBUG
        // Fault injection for the retry above, which otherwise only runs during
        // a failure that cannot be produced on demand — the worst kind of code
        // to leave unexercised. With LW_FAIL_BY_NAME set, every request made by
        // name fails, so the address fallback is what has to carry the read.
        if ProcessInfo.processInfo.environment["LW_FAIL_BY_NAME"] != nil,
           let host = request.url?.host, IPAddress.parse(host) == nil {
            throw BeaconError.unreachable("forced failure by name (LW_FAIL_BY_NAME)")
        }
        #endif

        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: request)
        } catch let error as URLError {
            throw BeaconError.unreachable(Self.describe(url: error))
        } catch {
            throw BeaconError.unreachable(error.localizedDescription)
        }

        guard let http = response as? HTTPURLResponse else { return data }
        guard (200 ..< 300).contains(http.statusCode) else {
            throw BeaconError.httpStatus(code: http.statusCode, body: Self.snippet(data))
        }
        return data
    }

    /// The same request aimed at a literal address, with the name preserved in
    /// `Host` so a server that cares still sees what it was asked for.
    private static func rewrite(_ request: URLRequest, to address: String) -> URLRequest? {
        guard let url = request.url,
              var components = URLComponents(url: url, resolvingAgainstBaseURL: false),
              let name = components.host
        else { return nil }
        // IPv6 literals need brackets in a URL; IPv4 must not have them.
        components.host = address.contains(":") ? "[\(address)]" : address
        guard let rewritten = components.url else { return nil }

        var retry = request
        retry.url = rewritten
        retry.setValue(components.port.map { "\(name):\($0)" } ?? name,
                       forHTTPHeaderField: "Host")
        return retry
    }

    /// Resolves a host through the system resolver and returns it only if it
    /// lands somewhere private.
    ///
    /// The check matters: if the name resolves to a public address then the
    /// proxy was not in the way and something else is wrong, and retrying around
    /// it would be this client deciding it knows better than the network.
    private static func privateAddress(for url: URL?) async -> String? {
        guard let name = url?.host, IPAddress.parse(name) == nil else { return nil }
        let resolved = await withCheckedContinuation { continuation in
            // getaddrinfo blocks; it does not belong on a cooperative thread.
            DispatchQueue.global(qos: .userInitiated).async {
                continuation.resume(returning: IPAddress.resolve(name))
            }
        }
        return resolved.first(where: \.isPrivate)?.text
    }

    /// The firmware answers failures in `text/plain`, one short line. Keep it,
    /// trimmed, because it names the actual fault.
    private static func snippet(_ data: Data, limit: Int = 160) -> String? {
        guard let text = String(data: data, encoding: .utf8)?
            .trimmingCharacters(in: .whitespacesAndNewlines), !text.isEmpty
        else { return nil }
        return text.count <= limit ? text : String(text.prefix(limit)) + "…"
    }

    private static func describe(url error: URLError) -> String {
        switch error.code {
        case .cannotFindHost, .dnsLookupFailed:
            return String(localized: "error.dns", defaultValue: "the name does not resolve")
        case .cannotConnectToHost:
            return String(localized: "error.refused", defaultValue: "nothing is listening")
        case .timedOut:
            return String(localized: "error.timeout", defaultValue: "it did not answer in time")
        case .notConnectedToInternet, .networkConnectionLost:
            return String(localized: "error.offline", defaultValue: "this device is off the network")
        case .appTransportSecurityRequiresSecureConnection:
            return String(localized: "error.ats", defaultValue: "the app refused a plain-HTTP connection")
        default:
            return error.localizedDescription
        }
    }

    private static func describe(decoding error: Error) -> String {
        guard let error = error as? DecodingError else { return error.localizedDescription }
        switch error {
        case .keyNotFound(let key, _):
            let name = key.stringValue
            return String(localized: "error.missingField",
                          defaultValue: "a required field is missing: \(name)")
        case .typeMismatch(_, let context), .valueNotFound(_, let context):
            let path = context.codingPath.map(\.stringValue).joined(separator: ".")
            return path.isEmpty ? context.debugDescription
                : String(localized: "error.unexpectedValue",
                         defaultValue: "unexpected value at \(path)")
        case .dataCorrupted(let context):
            return context.debugDescription
        @unknown default:
            return error.localizedDescription
        }
    }
}
