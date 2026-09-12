import Foundation

/// Settings and the last-known-good document, shared between the app and the
/// widget extension — and, by design, with the other tools of this observing
/// season.
///
/// The container is `group.de.staticline.astro` rather than one named after
/// this app, because an App Group is per development team and the useful unit
/// here is the toolset, not the tool. Dark adaptation is the reason: it is a
/// property of the observer, not of an application, and three astro apps of
/// which only one goes red at one in the morning cost their owner the half hour
/// they spent becoming dark-adapted. `astro.nightVision` therefore belongs to
/// the family, and any tool in it may read or write that key.
///
/// The rest is namespaced. A shared container is a shared key space, so
/// everything private to this app sits under `launchWindow.` and nothing here
/// writes an unprefixed key that another tool might also think is its own. The
/// two prefixes are the whole convention:
///
///   * `astro.*` — shared on purpose, for every tool in the group;
///   * `launchWindow.*` — this app and its widget, and no one else's business.
///
/// If the entitlement is not available — an unsigned build, a provisioning
/// profile without the group — everything falls back to each process's own
/// defaults and keeps working, with the widget's own configuration supplying
/// the host instead. Nothing here is allowed to be the reason a build does not
/// run.
enum SharedStore {
    /// Where the beacon answers unless told otherwise.
    static let defaultHost = "launch-window.home"

    /// The bare identifier, which is what iOS declares and what macOS needs a
    /// team in front of. Written once, here, and nowhere else.
    private static let bareGroup = "group.de.staticline.astro"

    /// The group this build was actually entitled to, as `LWAppGroup` in
    /// `Info.plist`.
    ///
    /// It is set from `$(LW_APP_GROUP)` in `Config/Signing.xcconfig`, which
    /// spells it bare for iOS and team-prefixed for macOS. Reading it beats
    /// hardcoding both spellings: the team identifier stays out of the source
    /// entirely, and the code cannot disagree with the entitlement it was
    /// actually signed with, because they are generated from one definition.
    private static var declaredGroup: String? {
        let value = Bundle.main.object(forInfoDictionaryKey: "LWAppGroup") as? String
        guard let value, !value.isEmpty, !value.hasPrefix("$(") else { return nil }
        return value
    }

    /// What is entitled first, then the bare name as a fallback for a build
    /// whose Info.plist did not carry one.
    private static var groupCandidates: [String] {
        var candidates: [String] = []
        if let declared = declaredGroup { candidates.append(declared) }
        if !candidates.contains(bareGroup) { candidates.append(bareGroup) }
        return candidates
    }

    /// The group this process can really use, if any.
    ///
    /// Neither obvious test is trustworthy. `UserDefaults(suiteName:)` returns
    /// an object for suites you were never granted, and on macOS
    /// `containerURL(forSecurityApplicationGroupIdentifier:)` returns a path for
    /// identifiers the entitlement never mentioned — it will happily hand back
    /// `~/Library/Group Containers/group.de.staticline.astro` for a build
    /// entitled only to the team-prefixed one. Writing a file is the only answer
    /// that cannot be wrong, and it costs one create and one unlink, once.
    static let appGroup: String? = groupCandidates.first(where: isUsable)

    private static func isUsable(_ group: String) -> Bool {
        let manager = FileManager.default
        guard let container = manager.containerURL(forSecurityApplicationGroupIdentifier: group)
        else { return false }
        let probe = container.appendingPathComponent(".launch-window-write-probe")
        guard manager.createFile(atPath: probe.path, contents: Data()) else { return false }
        try? manager.removeItem(at: probe)
        return true
    }

    static let defaults: UserDefaults = {
        if let appGroup, let shared = UserDefaults(suiteName: appGroup) { return shared }
        return .standard
    }()

    /// True when app and widget are genuinely reading the same settings. The
    /// settings screen says so, rather than letting the user wonder why the
    /// widget disagrees with the app.
    static var isSharing: Bool { appGroup != nil }

    private enum Key {
        /// Shared with every other tool in the group. See the note on this type
        /// for why this one, and only this one, is not app-private.
        static let nightVision = "astro.nightVision"

        static let host = "launchWindow.beaconHost"
        static let cachedDocument = "launchWindow.cache.document"
        static let cachedAt = "launchWindow.cache.retrievedAt"
        static let cachedHost = "launchWindow.cache.host"
    }

    // MARK: - Settings

    /// The beacon's address. Empty entries fall back rather than being stored,
    /// so there is no way to end up with an app that points at nothing.
    static var host: String {
        get {
            let stored = defaults.string(forKey: Key.host)?
                .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            return stored.isEmpty ? defaultHost : stored
        }
        set {
            let trimmed = newValue.trimmingCharacters(in: .whitespacesAndNewlines)
            if trimmed.isEmpty {
                defaults.removeObject(forKey: Key.host)
            } else {
                defaults.set(trimmed, forKey: Key.host)
            }
        }
    }

    /// Red on black, for a reader who is dark-adapted — shared across the whole
    /// astro group, because dark adaptation is a property of the observer and a
    /// half-dark toolset is no darker than a bright one.
    ///
    /// **`nil` means nobody has chosen yet, and that is not the same as `false`.**
    /// The tools in this group do not agree on what to do in the absence of a
    /// choice, and both are right: `ground-control` is red on black by default,
    /// because it is read at the eyepiece and white light there costs twenty
    /// minutes of adaptation; Launch Window starts bright, because a widget is
    /// mostly read in daylight and the LED's own colour language — green, amber,
    /// red — says more at a glance than a monochrome panel can.
    ///
    /// So the shared key carries only an explicit choice. Each tool applies its
    /// own default until the observer makes one, and from then on every tool
    /// obeys it. Writing a default into this key on first launch would let
    /// whichever app happened to start first impose its taste on the others.
    static var nightVision: Bool? {
        get { defaults.object(forKey: Key.nightVision) as? Bool }
        set {
            if let newValue {
                defaults.set(newValue, forKey: Key.nightVision)
            } else {
                defaults.removeObject(forKey: Key.nightVision)
            }
        }
    }

    /// What *this* app draws with, which is the shared choice when there is one
    /// and Launch Window's own default when there is not.
    static var prefersNightVision: Bool { nightVision ?? false }

    // MARK: - Last known good

    /// The raw bytes of the last document that decoded, kept so a beacon that
    /// has gone quiet still leaves something on screen — clearly dated, never
    /// dressed up as current.
    struct Cached: Sendable {
        var raw: Data
        var retrievedAt: Date
        var host: String
    }

    static func loadCached() -> Cached? {
        guard let raw = defaults.data(forKey: Key.cachedDocument),
              let retrievedAt = defaults.object(forKey: Key.cachedAt) as? Date
        else { return nil }
        return Cached(raw: raw,
                      retrievedAt: retrievedAt,
                      host: defaults.string(forKey: Key.cachedHost) ?? defaultHost)
    }

    static func store(raw: Data, host: String, at date: Date = Date()) {
        defaults.set(raw, forKey: Key.cachedDocument)
        defaults.set(date, forKey: Key.cachedAt)
        defaults.set(host, forKey: Key.cachedHost)
    }

    static func clearCache() {
        defaults.removeObject(forKey: Key.cachedDocument)
        defaults.removeObject(forKey: Key.cachedAt)
        defaults.removeObject(forKey: Key.cachedHost)
    }
}
