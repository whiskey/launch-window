import SwiftUI

/// The colour vocabulary, in two modes.
///
/// **Ordinary** uses the LED's own language — green, amber, red, and a grey for
/// "no answer" — because that is what the device in the hallway already says and
/// a second vocabulary for the same three states would be one too many.
///
/// **Night vision** throws hue away and says everything in deep red on black,
/// the way the beacon's own status page does. Someone reading this at one in the
/// morning has spent half an hour becoming dark-adapted, and a green tile at
/// full brightness costs them that. The verdict is then carried by the symbol
/// and by intensity, never by colour alone — which is also why the symbols
/// differ from each other in shape and not just in fill.
struct Palette: Sendable, Equatable {
    var nightVision: Bool

    static var current: Palette { Palette(nightVision: SharedStore.prefersNightVision) }
    static let day = Palette(nightVision: false)
    static let night = Palette(nightVision: true)

    // MARK: - Surfaces

    var background: Color {
        nightVision ? .black : Color(red: 0.039, green: 0.047, blue: 0.063)
    }

    var surface: Color {
        nightVision ? Color(red: 0.09, green: 0.012, blue: 0.008)
                    : Color(red: 0.082, green: 0.098, blue: 0.129)
    }

    /// Hairlines and axis rules.
    var grid: Color {
        nightVision ? deepRed.opacity(0.22) : Color(red: 0.23, green: 0.26, blue: 0.32)
    }

    // MARK: - Ink

    private var deepRed: Color { Color(red: 0.91, green: 0.16, blue: 0.11) }

    var text: Color {
        nightVision ? deepRed : Color(red: 0.949, green: 0.961, blue: 0.980)
    }

    var secondary: Color {
        nightVision ? deepRed.opacity(0.72) : Color(red: 0.612, green: 0.651, blue: 0.714)
    }

    var faint: Color {
        nightVision ? deepRed.opacity(0.42) : Color(red: 0.361, green: 0.400, blue: 0.463)
    }

    // MARK: - Verdict

    func verdict(_ state: VerdictState) -> Color {
        guard !nightVision else {
            switch state {
            case .go: return deepRed
            case .marginal: return deepRed.opacity(0.78)
            case .noGo: return deepRed.opacity(0.55)
            case .unknown: return deepRed.opacity(0.38)
            }
        }
        switch state {
        case .go: return Color(red: 0.239, green: 0.808, blue: 0.388)
        case .marginal: return Color(red: 1.000, green: 0.714, blue: 0.180)
        case .noGo: return Color(red: 0.953, green: 0.286, blue: 0.235)
        case .unknown: return Color(red: 0.557, green: 0.596, blue: 0.667)
        }
    }

    /// One graded hour, coloured against the firmware's own thresholds:
    /// `go_score` 70 and `usable_score` 55 from `firmware/config.json`.
    ///
    /// A `nil` score is not a zero. It is an hour that could not be graded, and
    /// it is drawn as absent rather than as bad.
    func score(_ value: Double?) -> Color {
        guard let value else { return faint.opacity(0.5) }
        guard !nightVision else {
            return deepRed.opacity(0.28 + 0.72 * min(1, max(0, value / 100)))
        }
        switch value {
        case Grading.goScore...: return verdict(.go)
        case Grading.usableScore...: return verdict(.marginal)
        default: return verdict(.noGo)
        }
    }
}

/// The thresholds the firmware grades against, mirrored here so the widget's
/// colours mean the same thing the verdict does. They live in
/// `firmware/config.json`; if they are changed there, change them here.
enum Grading {
    /// An hour at or above this can be imaged.
    static let usableScore: Double = 55
    /// A run at this mean score, long enough, is a GO.
    static let goScore: Double = 70
}

/// SF Symbols for the four states. Chosen to differ in outline, not only in
/// fill, so night-vision mode and a colour-blind reader both still get it.
enum VerdictSymbol {
    static func name(for state: VerdictState) -> String {
        switch state {
        case .go: return "checkmark.circle.fill"
        case .marginal: return "circle.lefthalf.filled"
        case .noGo: return "xmark.circle.fill"
        case .unknown: return "questionmark.circle"
        }
    }
}
