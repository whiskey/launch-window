import SwiftUI

/// Two settings, and an honest statement about whether the widget can see them.
struct SettingsView: View {
    @Bindable var model: BeaconModel
    @Environment(\.dismiss) private var dismiss
    @State private var draftHost: String = ""

    private var palette: Palette { model.palette }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField(Strings.beaconAddress, text: $draftHost, prompt: Text(SharedStore.defaultHost))
                        .textFieldStyle(.plain)
                        .font(.system(size: 15, design: .monospaced))
                        #if os(iOS)
                        .textInputAutocapitalization(.never)
                        .keyboardType(.URL)
                        .submitLabel(.done)
                        #endif
                        .autocorrectionDisabled()
                        .onSubmit(commit)
                } header: {
                    Text(Strings.beaconAddress)
                } footer: {
                    VStack(alignment: .leading, spacing: 6) {
                        Text(Strings.beaconAddressFootnote)
                        // The widget runs in its own process. Whether it can
                        // read this field depends on an App Group entitlement,
                        // and guessing wrong leaves someone wondering why the
                        // widget disagrees with the app.
                        Text(SharedStore.isSharing ? Strings.sharedWithWidget
                                                   : Strings.notSharedWithWidget)
                            .foregroundStyle(SharedStore.isSharing ? palette.secondary
                                                                   : palette.verdict(.marginal))
                    }
                }

                Section {
                    Toggle(Strings.nightVision, isOn: $model.nightVision)
                } footer: {
                    VStack(alignment: .leading, spacing: 6) {
                        Text(Strings.nightVisionFootnote)
                        // Dark adaptation belongs to the observer, not to one
                        // app, so this setting lives in the shared astro group.
                        // Only say so when the group actually resolved.
                        if SharedStore.isSharing {
                            Text(Strings.nightVisionShared)
                                .foregroundStyle(palette.secondary)
                        }
                    }
                }

                Section {
                    LabeledContent(Strings.beacon) {
                        Text(model.snapshot.document?.beacon.host ?? "—")
                            .monospaced()
                    }
                    LabeledContent(Strings.firmware) {
                        Text(model.snapshot.document?.beacon.firmwareVersion ?? "—")
                            .monospaced()
                    }
                    LabeledContent(Strings.ipAddress) {
                        Text(model.snapshot.document?.beacon.address ?? "—")
                            .monospaced()
                    }
                }
            }
            .formStyle(.grouped)
            .navigationTitle(Strings.settings)
            #if os(iOS)
            .navigationBarTitleDisplayMode(.inline)
            #endif
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button(Strings.done) {
                        commit()
                        dismiss()
                    }
                }
            }
        }
        .onAppear { draftHost = model.host }
        #if os(macOS)
        .frame(minWidth: 420, minHeight: 380)
        #endif
    }

    private func commit() {
        let trimmed = draftHost.trimmingCharacters(in: .whitespacesAndNewlines)
        model.host = trimmed.isEmpty ? SharedStore.defaultHost : trimmed
        draftHost = model.host
        Task { await model.load() }
    }
}

#if DEBUG
#Preview {
    SettingsView(model: BeaconModel(showing: SampleBeacon.snapshot(SampleBeacon.go)))
        .preferredColorScheme(.dark)
}
#endif
