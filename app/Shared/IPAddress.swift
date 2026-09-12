import Foundation

/// Just enough address handling to answer two questions: is this text already an
/// address, and does this name live on our own network?
///
/// Both exist for one reason. Everything this app talks to is a small device on
/// the LAN, reached over plain HTTP because it cannot do anything else, and
/// plain HTTP is precisely the traffic iCloud Private Relay takes an interest
/// in. A literal address in one of the private ranges is the one destination
/// nothing will try to proxy, so being able to recognise and resolve to one is
/// what keeps the client reachable when the name path goes astray.
struct IPAddress: Sendable, Hashable {
    enum Family: Sendable, Hashable { case v4, v6 }

    var text: String
    var family: Family

    /// `true` for the ranges that are, by definition, not on the public
    /// internet: RFC 1918, RFC 3927 link-local, loopback, and their v6
    /// equivalents — unique-local `fc00::/7` and link-local `fe80::/10`.
    var isPrivate: Bool {
        switch family {
        case .v4:
            let parts = text.split(separator: ".").compactMap { UInt8($0) }
            guard parts.count == 4 else { return false }
            switch (parts[0], parts[1]) {
            case (10, _): return true
            case (127, _): return true
            case (192, 168): return true
            case (172, 16 ... 31): return true
            case (169, 254): return true
            default: return false
            }
        case .v6:
            let lowered = text.lowercased()
            if lowered == "::1" { return true }
            guard let first = lowered.split(separator: ":").first,
                  let leading = UInt16(first, radix: 16) else { return false }
            // fc00::/7 unique-local, fe80::/10 link-local.
            return (leading & 0xFE00) == 0xFC00 || (leading & 0xFFC0) == 0xFE80
        }
    }

    /// Parses text that is already an address, returning nil for anything that
    /// is a name. Brackets around an IPv6 literal are tolerated.
    static func parse(_ text: String) -> IPAddress? {
        let bare = text.hasPrefix("[") && text.hasSuffix("]")
            ? String(text.dropFirst().dropLast())
            : text
        var v4 = in_addr()
        if bare.withCString({ inet_pton(AF_INET, $0, &v4) }) == 1 {
            return IPAddress(text: bare, family: .v4)
        }
        var v6 = in6_addr()
        // A scope suffix (fe80::1%en0) is part of the literal, not of the address.
        let withoutScope = bare.split(separator: "%", maxSplits: 1).first.map(String.init) ?? bare
        if withoutScope.withCString({ inet_pton(AF_INET6, $0, &v6) }) == 1 {
            return IPAddress(text: bare, family: .v6)
        }
        return nil
    }

    /// Resolves a name through the system resolver.
    ///
    /// Deliberately `getaddrinfo` and not a URL request: this is the resolver
    /// that knows about the router handing out `.home`, and it is the one path
    /// that is not itself subject to the proxying this is meant to detour
    /// around. It blocks, so callers must not run it on a cooperative thread.
    static func resolve(_ name: String) -> [IPAddress] {
        var hints = addrinfo(ai_flags: 0,
                             ai_family: AF_UNSPEC,
                             ai_socktype: SOCK_STREAM,
                             ai_protocol: IPPROTO_TCP,
                             ai_addrlen: 0,
                             ai_canonname: nil,
                             ai_addr: nil,
                             ai_next: nil)
        var head: UnsafeMutablePointer<addrinfo>?
        guard getaddrinfo(name, nil, &hints, &head) == 0, let first = head else { return [] }
        defer { freeaddrinfo(head) }

        var found: [IPAddress] = []
        var buffer = [CChar](repeating: 0, count: Int(NI_MAXHOST))
        for info in sequence(first: first, next: { $0.pointee.ai_next }) {
            guard let sockaddr = info.pointee.ai_addr else { continue }
            let status = getnameinfo(sockaddr, info.pointee.ai_addrlen,
                                     &buffer, socklen_t(buffer.count),
                                     nil, 0, NI_NUMERICHOST)
            guard status == 0 else { continue }
            let text = String(cString: buffer)
            // Round-trip through `parse` so the family comes from the address
            // itself rather than from what the resolver said it would be.
            if let address = parse(text), !found.contains(address) {
                found.append(address)
            }
        }
        return found
    }
}
