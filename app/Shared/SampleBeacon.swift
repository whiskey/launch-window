import Foundation

// Bundled readings, used for SwiftUI previews and for the widget gallery, where
// WidgetKit renders before it is allowed to fetch anything.
//
// These are real documents: `noGoNight` is what the beacon served when
// `tools/make-samples.py` was last run, and the other two are that same night
// edited into the states that are hardest to get right. They go through the
// same decoder as a live reading, so a change to the model that breaks decoding
// breaks the previews too.
//
// Raw string literals rather than bundle resources, so that a preview cannot
// fail on a missing file. The line breaks fall only after a comma outside a
// string, where JSON treats them as whitespace.

enum SampleBeacon {
    /// A clear night: an unbroken window from dusk, at a mean score of 82.
    static let goNight = #"""
    {"schema":1,"generated_at":"2026-09-12T12:00:57Z","generated_local":"14:00","beacon":{"host":"launch-window",
    "firmware_version":"1.0.0","uptime_s":45231,"uptime":"12 h 33 min","core_temp_c":28.4,"signal_dbm":-47,
    "address":"10.1.10.84"},"clock":{"synced":true,"last_sync":null},"site":{"name":"Garden","latitude":52.52,
    "longitude":13.4,"timezone":"Europe/Berlin"},"night":{"darkness":"astronomical","sunset":"2026-09-12T17:28:54Z",
    "sunset_local":"19:28","dusk_astronomical":"2026-09-12T19:29:44Z","dusk_astronomical_local":"21:29",
    "dawn_astronomical":"2026-09-13T02:36:03Z","dawn_astronomical_local":"04:36","sunrise":"2026-09-13T04:37:04Z",
    "sunrise_local":"06:37","dark_seconds":25579,"dark_duration":"7 h 06 min","dark_start":"2026-09-12T19:29:44Z",
    "dark_end":"2026-09-13T02:36:03Z"},"moon":{"illumination":0.023,"phase":"new","altitude_deg":31.0,"rise":"2026-09-12T06:17:47Z",
    "rise_local":"08:17","set":"2026-09-12T17:26:13Z","set_local":"19:26","interferes":false},"verdict":{"state":"go",
    "score":82.2,"reasons":["6.4 h of usable dark sky, mean score 82","cloud cover averaging 15 %"],"window":{"start":"2026-09-12T19:29:44Z",
    "end":"2026-09-13T02:36:03Z","start_local":"21:29","end_local":"04:36","hours":6.4,"mean_score":82.2},
    "hours":[{"ts":1789239600,"score":94.0,"penalties":{"cloud":3.4},"veto":null,"cloud_cover":4,"cloud_cover_high":0,
    "wind_gusts_10m":11.5,"temperature_2m":17.8,"dew_point_2m":9.1,"precipitation_probability":0,"moon_alt_deg":-14.0,
    "local":"21:00","time":"2026-09-12T19:00:00Z"},{"ts":1789243200,"score":97.0,"penalties":{"cloud":0.0},
    "veto":null,"cloud_cover":0,"cloud_cover_high":0,"wind_gusts_10m":10.1,"temperature_2m":17.0,"dew_point_2m":8.9,
    "precipitation_probability":0,"moon_alt_deg":-22.9,"local":"22:00","time":"2026-09-12T20:00:00Z"},{"ts":1789246800,
    "score":90.0,"penalties":{"cloud":6.8},"veto":null,"cloud_cover":8,"cloud_cover_high":4,"wind_gusts_10m":9.4,
    "temperature_2m":16.2,"dew_point_2m":8.6,"precipitation_probability":0,"moon_alt_deg":-31.1,"local":"23:00",
    "time":"2026-09-12T21:00:00Z"},{"ts":1789250400,"score":86.0,"penalties":{"cloud":10.2},"veto":null,
    "cloud_cover":12,"cloud_cover_high":8,"wind_gusts_10m":8.6,"temperature_2m":15.5,"dew_point_2m":8.4,
    "precipitation_probability":0,"moon_alt_deg":-38.3,"local":"00:00","time":"2026-09-12T22:00:00Z"},{"ts":1789254000,
    "score":92.0,"penalties":{"cloud":5.1},"veto":null,"cloud_cover":6,"cloud_cover_high":2,"wind_gusts_10m":7.9,
    "temperature_2m":14.9,"dew_point_2m":8.2,"precipitation_probability":0,"moon_alt_deg":-43.7,"local":"01:00",
    "time":"2026-09-12T23:00:00Z"},{"ts":1789257600,"score":79.0,"penalties":{"cloud":15.3},"veto":null,
    "cloud_cover":18,"cloud_cover_high":12,"wind_gusts_10m":7.2,"temperature_2m":14.4,"dew_point_2m":8.1,
    "precipitation_probability":0,"moon_alt_deg":-46.6,"local":"02:00","time":"2026-09-13T00:00:00Z"},{"ts":1789261200,
    "score":62.0,"penalties":{"cloud":28.9},"veto":null,"cloud_cover":34,"cloud_cover_high":24,"wind_gusts_10m":6.8,
    "temperature_2m":14.0,"dew_point_2m":8.0,"precipitation_probability":0,"moon_alt_deg":-46.4,"local":"03:00",
    "time":"2026-09-13T01:00:00Z"},{"ts":1789264800,"score":58.0,"penalties":{"cloud":34.0},"veto":null,
    "cloud_cover":40,"cloud_cover_high":26,"wind_gusts_10m":6.1,"temperature_2m":13.6,"dew_point_2m":7.9,
    "precipitation_probability":0,"moon_alt_deg":-43.3,"local":"04:00","time":"2026-09-13T02:00:00Z"}]},
    "data":{"source":"open-meteo","fetched_at":"2026-09-12T11:45:53Z","age_s":633,"age":"10 min","stale":false,
    "from_flash_cache":false,"error":null}}
    """#

    /// What the beacon actually served when this file was generated.
    static let noGoNight = #"""
    {"schema":1,"generated_at":"2026-09-12T12:00:57Z","generated_local":"14:00","beacon":{"host":"launch-window",
    "firmware_version":"1.0.0","uptime_s":45231,"uptime":"12 h 33 min","core_temp_c":28.4,"signal_dbm":-47,
    "address":"10.1.10.84"},"clock":{"synced":true,"last_sync":null},"site":{"name":"Garden","latitude":52.52,
    "longitude":13.4,"timezone":"Europe/Berlin"},"night":{"darkness":"astronomical","sunset":"2026-09-12T17:28:54Z",
    "sunset_local":"19:28","dusk_astronomical":"2026-09-12T19:29:44Z","dusk_astronomical_local":"21:29",
    "dawn_astronomical":"2026-09-13T02:36:03Z","dawn_astronomical_local":"04:36","sunrise":"2026-09-13T04:37:04Z",
    "sunrise_local":"06:37","dark_seconds":25579,"dark_duration":"7 h 06 min","dark_start":"2026-09-12T19:29:44Z",
    "dark_end":"2026-09-13T02:36:03Z"},"moon":{"illumination":0.023,"phase":"new","altitude_deg":31.0,"rise":"2026-09-12T06:17:47Z",
    "rise_local":"08:17","set":"2026-09-12T17:26:13Z","set_local":"19:26","interferes":false},"verdict":{"state":"no-go",
    "score":0.0,"reasons":["no usable stretch of dark sky tonight","overcast for 6 of 8 dark hours","cloud cover averaging 100 %",
    "some chance of precipitation"],"window":null,"hours":[{"ts":1789239600,"score":0.0,"penalties":{"cloud":85.0},
    "veto":"overcast (100 %)","cloud_cover":100,"cloud_cover_high":100,"wind_gusts_10m":14.4,"temperature_2m":19.2,
    "dew_point_2m":10.5,"precipitation_probability":0,"moon_alt_deg":-14.0,"local":"21:00","time":"2026-09-12T19:00:00Z"},
    {"ts":1789243200,"score":0.0,"penalties":{"cloud":85.0},"veto":"overcast (100 %)","cloud_cover":100,
    "cloud_cover_high":100,"wind_gusts_10m":11.9,"temperature_2m":18.5,"dew_point_2m":11.1,"precipitation_probability":0,
    "moon_alt_deg":-22.9,"local":"22:00","time":"2026-09-12T20:00:00Z"},{"ts":1789246800,"score":0.0,"penalties":{"cloud":85.0,
    "precipitation":0.9},"veto":"overcast (100 %)","cloud_cover":100,"cloud_cover_high":100,"wind_gusts_10m":10.1,
    "temperature_2m":17.9,"dew_point_2m":11.3,"precipitation_probability":3,"moon_alt_deg":-31.1,"local":"23:00",
    "time":"2026-09-12T21:00:00Z"},{"ts":1789250400,"score":0.0,"penalties":{"cloud":85.0,"precipitation":1.5},
    "veto":"overcast (100 %)","cloud_cover":100,"cloud_cover_high":100,"wind_gusts_10m":12.2,"temperature_2m":17.5,
    "dew_point_2m":11.5,"precipitation_probability":5,"moon_alt_deg":-38.3,"local":"00:00","time":"2026-09-12T22:00:00Z"},
    {"ts":1789254000,"score":0.0,"penalties":{"cloud":85.0,"precipitation":5.4},"veto":"overcast (100 %)",
    "cloud_cover":100,"cloud_cover_high":100,"wind_gusts_10m":13.3,"temperature_2m":17.2,"dew_point_2m":12.1,
    "precipitation_probability":18,"moon_alt_deg":-43.7,"local":"01:00","time":"2026-09-12T23:00:00Z"},{"ts":1789257600,
    "score":0.0,"penalties":{"cloud":85.0,"wind":0.6,"precipitation":6.0},"veto":"overcast (100 %)","cloud_cover":100,
    "cloud_cover_high":69,"wind_gusts_10m":15.5,"temperature_2m":16.9,"dew_point_2m":12.0,"precipitation_probability":20,
    "moon_alt_deg":-46.6,"local":"02:00","time":"2026-09-13T00:00:00Z"},{"ts":1789261200,"score":0.0,"penalties":{"cloud":85.0,
    "wind":0.1,"precipitation":15.9},"veto":"rain likely (53 %)","cloud_cover":100,"cloud_cover_high":95,
    "wind_gusts_10m":15.1,"temperature_2m":16.6,"dew_point_2m":12.0,"precipitation_probability":53,"moon_alt_deg":-46.4,
    "local":"03:00","time":"2026-09-13T01:00:00Z"},{"ts":1789264800,"score":0.0,"penalties":{"cloud":85.0,
    "wind":1.0,"precipitation":19.5},"veto":"rain likely (65 %)","cloud_cover":100,"cloud_cover_high":100,
    "wind_gusts_10m":15.8,"temperature_2m":16.1,"dew_point_2m":12.7,"precipitation_probability":65,"moon_alt_deg":-43.3,
    "local":"04:00","time":"2026-09-13T02:00:00Z"}]},"data":{"source":"open-meteo","fetched_at":"2026-09-12T11:45:53Z",
    "age_s":633,"age":"10 min","stale":false,"from_flash_cache":false,"error":null}}
    """#

    /// Up, but with no forecast. `unknown` is not `no-go`, and the views must not blur the two.
    static let unknownNight = #"""
    {"schema":1,"generated_at":"2026-09-12T12:00:57Z","generated_local":"14:00","beacon":{"host":"launch-window",
    "firmware_version":"1.0.0","uptime_s":45231,"uptime":"12 h 33 min","core_temp_c":28.4,"signal_dbm":-47,
    "address":"10.1.10.84"},"clock":{"synced":true,"last_sync":null},"site":{"name":"Garden","latitude":52.52,
    "longitude":13.4,"timezone":"Europe/Berlin"},"night":{"darkness":"astronomical","sunset":"2026-09-12T17:28:54Z",
    "sunset_local":"19:28","dusk_astronomical":"2026-09-12T19:29:44Z","dusk_astronomical_local":"21:29",
    "dawn_astronomical":"2026-09-13T02:36:03Z","dawn_astronomical_local":"04:36","sunrise":"2026-09-13T04:37:04Z",
    "sunrise_local":"06:37","dark_seconds":25579,"dark_duration":"7 h 06 min","dark_start":"2026-09-12T19:29:44Z",
    "dark_end":"2026-09-13T02:36:03Z"},"moon":{"illumination":0.023,"phase":"new","altitude_deg":31.0,"rise":"2026-09-12T06:17:47Z",
    "rise_local":"08:17","set":"2026-09-12T17:26:13Z","set_local":"19:26","interferes":false},"verdict":{"state":"unknown",
    "score":null,"reasons":["no forecast covering tonight's dark hours"],"window":null,"hours":[]},"data":{"source":"open-meteo",
    "fetched_at":null,"age_s":null,"age":null,"stale":true,"from_flash_cache":false,"error":"wifi: no route to host"}}
    """#

    /// Forced: these literals ship inside the binary, so a failure here is a
    /// programming error that the first preview catches, not a runtime
    /// condition worth handling.
    private static func document(_ json: String) -> BeaconDocument {
        // swiftlint:disable:next force_try
        try! BeaconDocument.decode(from: Data(json.utf8))
    }

    static var go: BeaconDocument { document(goNight) }
    static var noGo: BeaconDocument { document(noGoNight) }
    static var unknown: BeaconDocument { document(unknownNight) }

    static func snapshot(_ document: BeaconDocument,
                         origin: BeaconSnapshot.Origin = .sample) -> BeaconSnapshot {
        BeaconSnapshot(document: document,
                       retrievedAt: document.data.fetchedAt ?? document.generatedAt,
                       host: SharedStore.defaultHost,
                       origin: origin)
    }
}
