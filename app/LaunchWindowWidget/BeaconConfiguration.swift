import AppIntents
import WidgetKit

/// How dark the widget draws itself.
///
/// Three states rather than two, because the useful answer is usually "whatever
/// the app is set to" — but not always. A widget on a desk at work and one on a
/// phone that lives in an observing bag want different answers, and the widget
/// is the only place that distinction can be made.
enum NightVisionSetting: String, AppEnum {
    case automatic
    case on
    case off

    static var typeDisplayRepresentation: TypeDisplayRepresentation { "Night vision" }

    static var caseDisplayRepresentations: [NightVisionSetting: DisplayRepresentation] {
        [
            .automatic: DisplayRepresentation(title: "Follow the app"),
            .on: DisplayRepresentation(title: "On"),
            .off: DisplayRepresentation(title: "Off"),
        ]
    }
}

/// What one instance of the widget is pointed at.
///
/// The address is configurable per widget, and empty means "use the app's".
/// That covers both the ordinary case — set it once in the app — and the case
/// this project invites, which is a second beacon at a second site.
struct BeaconConfiguration: WidgetConfigurationIntent {
    static var title: LocalizedStringResource { "Beacon" }

    static var description: IntentDescription {
        IntentDescription("Which beacon this widget reads, and how brightly it draws the answer.")
    }

    @Parameter(title: "Beacon address", default: "")
    var host: String

    @Parameter(title: "Night vision", default: NightVisionSetting.automatic)
    var nightVision: NightVisionSetting

    init() {}

    init(host: String, nightVision: NightVisionSetting = .automatic) {
        self.host = host
        self.nightVision = nightVision
    }

    /// The widget's own address if one was typed, the app's if not, and the
    /// built-in default if neither — so a freshly dropped widget works with no
    /// configuration at all.
    var resolvedHost: String {
        let trimmed = host.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? SharedStore.host : trimmed
    }

    var palette: Palette {
        switch nightVision {
        case .automatic: return .current
        case .on: return .night
        case .off: return .day
        }
    }
}
