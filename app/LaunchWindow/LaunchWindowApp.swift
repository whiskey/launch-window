import SwiftUI

@main
struct LaunchWindowApp: App {
    @State private var model = BeaconModel()

    init() {
        #if DEBUG && os(macOS)
        Development.runIfRequested()
        #endif
    }

    var body: some Scene {
        WindowGroup {
            TonightView(model: model)
                // The app is dark by construction, not by preference: its
                // readers are dark-adapted, and a light scheme would be a bug.
                .preferredColorScheme(.dark)
        }
        #if os(macOS)
        .defaultSize(width: 480, height: 820)
        #endif
    }
}
