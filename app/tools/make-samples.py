#!/usr/bin/env python3
"""Regenerate Shared/SampleBeacon.swift from a real beacon document.

    app/tools/make-samples.py                        read launch-window.home
    app/tools/make-samples.py --host localhost:8099  read tools/simulate.py --serve
    app/tools/make-samples.py --from night.json      use a document already saved

The previews and the widget gallery render three nights: the one the beacon
served when this was run, that night cleared up, and that night with no forecast
at all. Deriving the last two from a real document rather than writing them by
hand keeps every field present and every type right — the samples go through the
same decoder as a live reading, so a model change that breaks decoding breaks
the previews too, which is the point of them.
"""

from __future__ import annotations

import argparse
import copy
import json
import pathlib
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "Shared" / "SampleBeacon.swift"

# A clear night over the same dark window: cloud, high cloud, gusts, temperature,
# dew point, precipitation probability, score. Every hour is at or above the
# firmware's usable_score of 55, which is what makes one unbroken window the
# correct reading of these numbers rather than a contradiction of them.
CLEAR_HOURS = [
    (4, 0, 11.5, 17.8, 9.1, 0, 94.0),
    (0, 0, 10.1, 17.0, 8.9, 0, 97.0),
    (8, 4, 9.4, 16.2, 8.6, 0, 90.0),
    (12, 8, 8.6, 15.5, 8.4, 0, 86.0),
    (6, 2, 7.9, 14.9, 8.2, 0, 92.0),
    (18, 12, 7.2, 14.4, 8.1, 0, 79.0),
    (34, 24, 6.8, 14.0, 8.0, 0, 62.0),
    (40, 26, 6.1, 13.6, 7.9, 0, 58.0),
]
USABLE_SCORE = 55


def fetch(host: str) -> dict:
    url = host if "://" in host else "http://%s" % host
    with urllib.request.urlopen("%s/api/v1/beacon" % url.rstrip("/"), timeout=20) as response:
        return json.load(response)


def make_nogo(live: dict) -> dict:
    """The document as served, with the fields a laptop cannot produce filled in
    so the sample looks like hardware rather than like the simulator."""
    doc = copy.deepcopy(live)
    doc["beacon"].update({"uptime_s": 45231, "uptime": "12 h 33 min",
                          "core_temp_c": 28.4, "signal_dbm": -47,
                          "address": "10.1.10.84"})
    doc["data"].update({"age_s": 633, "age": "10 min"})
    return doc


def make_go(nogo: dict) -> dict:
    doc = copy.deepcopy(nogo)
    hours = doc["verdict"]["hours"]
    if not hours:
        sys.exit("the source document has no graded hours; point at a night, not a noon")
    for hour, values in zip(hours, CLEAR_HOURS):
        cloud, high, gust, temp, dew, precip, score = values
        hour.update({"cloud_cover": cloud, "cloud_cover_high": high,
                     "wind_gusts_10m": gust, "temperature_2m": temp,
                     "dew_point_2m": dew, "precipitation_probability": precip,
                     "score": score, "veto": None,
                     "penalties": {"cloud": round(cloud * 0.85, 1)}})
    scored = [h["score"] for h in hours if h["score"] is not None]
    mean = round(sum(scored) / len(scored), 1)
    assert min(scored) >= USABLE_SCORE, "every hour in the window must clear usable_score"

    start = hours[0].get("time") or doc["night"]["dark_start"]
    doc["verdict"].update({
        "state": "go", "score": mean,
        "reasons": ["%.1f h of usable dark sky, mean score %.0f" % (len(scored) * 0.8, mean),
                    "cloud cover averaging %.0f %%"
                    % (sum(v[0] for v in CLEAR_HOURS[:len(scored)]) / len(scored))],
        "window": {
            "start": doc["night"]["dark_start"] or start,
            "end": doc["night"]["dark_end"],
            "start_local": doc["night"]["dusk_astronomical_local"]
            or doc["night"]["sunset_local"],
            "end_local": doc["night"]["dawn_astronomical_local"]
            or doc["night"]["sunrise_local"],
            "hours": round(len(scored) * 0.8, 1), "mean_score": mean,
        },
    })
    return doc


def make_unknown(nogo: dict) -> dict:
    """Up, but with no forecast. `unknown` is not `no-go`, and this is the state
    the views are most easily written to blur."""
    doc = copy.deepcopy(nogo)
    doc["verdict"].update({"state": "unknown", "score": None,
                           "reasons": ["no forecast covering tonight's dark hours"],
                           "window": None, "hours": []})
    doc["data"].update({"fetched_at": None, "age_s": None, "age": None,
                        "stale": True, "error": "wifi: no route to host"})
    return doc


def wrap(doc: dict, width: int = 100, indent: str = "    ") -> str:
    """Compact JSON, wrapped only immediately after a comma outside a string.

    Any other break point risks landing inside a token — mid-number, or
    mid-string, where a newline is a control character and not whitespace."""
    text = json.dumps(doc, separators=(",", ":"), ensure_ascii=False)
    lines: list[str] = []
    current: list[str] = []
    in_string = escaped = False
    for character in text:
        current.append(character)
        if escaped:
            escaped = False
        elif in_string:
            if character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
        elif character == '"':
            in_string = True
        elif character == "," and len(current) >= width:
            lines.append("".join(current))
            current = []
    if current:
        lines.append("".join(current))
    return "\n".join(indent + line for line in lines)


HEADER = '''import Foundation

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
'''

FOOTER = '''
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
'''


def literal(name: str, doc: dict, note: str) -> str:
    return '    /// %s\n    static let %s = #"""\n%s\n    """#\n' % (note, name, wrap(doc))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="launch-window.home")
    parser.add_argument("--from", dest="path", help="a saved beacon document")
    arguments = parser.parse_args()

    if arguments.path:
        live = json.loads(pathlib.Path(arguments.path).read_text())
    else:
        live = fetch(arguments.host)

    if live.get("schema") != 1:
        sys.exit("this generator writes protocol 1; the document says %r" % live.get("schema"))

    nogo = make_nogo(live)
    go = make_go(nogo)
    unknown = make_unknown(nogo)

    for name, doc in (("go", go), ("no-go", nogo), ("unknown", unknown)):
        assert json.loads(wrap(doc)) == doc, name
        assert '"""' not in wrap(doc), name

    OUT.write_text(HEADER + "\n".join([
        literal("goNight", go, "A clear night: an unbroken window from dusk, at a mean score of %.0f."
                % go["verdict"]["score"]),
        literal("noGoNight", nogo,
                "What the beacon actually served when this file was generated."),
        literal("unknownNight", unknown,
                "Up, but with no forecast. `unknown` is not `no-go`, and the views must not blur the two."),
    ]) + FOOTER)
    print("wrote %s" % OUT.relative_to(ROOT.parent))
    return 0


if __name__ == "__main__":
    sys.exit(main())
