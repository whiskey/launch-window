#!/usr/bin/env python3
"""Diff the Swift astronomy port against `firmware/lib/sky.py`.

    app/tools/compare-sky.py <path-to-LaunchWindow-binary> [--nights 60] [--start ISO]

`app/Shared/SkyMath.swift` is a second implementation of the one thing this
project says must never be wrong. The beacon can check the client for tonight —
it publishes its own answer — but not for the nights after it, which is the
whole point of the port. The original is therefore the only oracle available,
and this is what holds the two to each other.

Tolerances are tight on purpose. Both sides run the same series in double
precision, so agreement should be to the second and to a rounding error; a
difference means a transcription mistake, not a numerical one.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "firmware" / "lib"))

import sky  # noqa: E402

# Seconds of disagreement tolerated on an event time, and absolute tolerance on
# the two floating-point quantities.
EVENT_TOLERANCE_S = 1
ILLUMINATION_TOLERANCE = 1e-6
ALTITUDE_TOLERANCE_DEG = 1e-4


def python_row(ts, latitude, longitude):
    night = sky.night(ts, latitude, longitude)
    moon = sky.moon_events(ts - 12 * 3600, ts + 24 * 3600, latitude, longitude)
    reference = night["dusk_astronomical"] or ts
    return {
        "ts": ts,
        "sunset": night["sunset"],
        "dusk": night["dusk_astronomical"],
        "dawn": night["dawn_astronomical"],
        "sunrise": night["sunrise"],
        "dark_seconds": night["dark_seconds"],
        "illumination": sky.moon_illumination(reference),
        "phase": sky.moon_phase_name(reference),
        "moon_alt": sky.moon_altaz(reference, latitude, longitude)[0],
        "moonrise": moon["rise"],
        "moonset": moon["set"],
    }


def swift_rows(binary, base, nights, latitude, longitude):
    environment = dict(os.environ)
    environment["LW_SKY"] = "%d:%d:%s:%s" % (base, nights, latitude, longitude)
    completed = subprocess.run([binary], capture_output=True, text=True,
                               env=environment, timeout=600)
    rows = []
    for line in completed.stdout.splitlines():
        if not line.startswith("SKY "):
            continue
        f = line[4:].split("|")
        if len(f) != 11:
            sys.exit("unexpected SKY line: %s" % line)
        maybe = lambda v: None if v == "-" else int(v)  # noqa: E731
        rows.append({
            "ts": int(f[0]), "sunset": maybe(f[1]), "dusk": maybe(f[2]),
            "dawn": maybe(f[3]), "sunrise": maybe(f[4]), "dark_seconds": int(f[5]),
            "illumination": float(f[6]), "phase": f[7], "moon_alt": float(f[8]),
            "moonrise": maybe(f[9]), "moonset": maybe(f[10]),
        })
    if not rows:
        sys.exit("the binary printed no SKY lines:\n%s" % completed.stderr[-2000:])
    return rows


def compare(expected, actual):
    problems = []
    for key in ("sunset", "dusk", "dawn", "sunrise", "moonrise", "moonset"):
        want, got = expected[key], actual[key]
        if (want is None) != (got is None):
            problems.append("%s: python=%s swift=%s" % (key, want, got))
        elif want is not None and abs(want - got) > EVENT_TOLERANCE_S:
            problems.append("%s: %+d s" % (key, got - want))
    if abs(expected["dark_seconds"] - actual["dark_seconds"]) > EVENT_TOLERANCE_S:
        problems.append("dark_seconds: %+d s"
                        % (actual["dark_seconds"] - expected["dark_seconds"]))
    if abs(expected["illumination"] - actual["illumination"]) > ILLUMINATION_TOLERANCE:
        problems.append("illumination: %+.8f"
                        % (actual["illumination"] - expected["illumination"]))
    if abs(expected["moon_alt"] - actual["moon_alt"]) > ALTITUDE_TOLERANCE_DEG:
        problems.append("moon_alt: %+.6f deg" % (actual["moon_alt"] - expected["moon_alt"]))
    if expected["phase"] != actual["phase"]:
        problems.append("phase: python=%s swift=%s" % (expected["phase"], actual["phase"]))
    return problems


SITES = [
    ("Garden (Berlin)", 52.52, 13.4),
    ("Tenerife", 28.3, -16.5),
    ("Tromsø", 69.65, 18.96),     # no astronomical night for months
    ("Cape Town", -33.93, 18.42),  # southern hemisphere
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary")
    parser.add_argument("--nights", type=int, default=60)
    parser.add_argument("--start", type=int, default=None,
                        help="unix timestamp of the first night (default: now)")
    arguments = parser.parse_args()

    base = arguments.start if arguments.start is not None else int(time.time())
    failures = 0
    checked = 0

    for name, latitude, longitude in SITES:
        rows = swift_rows(arguments.binary, base, arguments.nights, latitude, longitude)
        for row in rows:
            expected = python_row(row["ts"], latitude, longitude)
            problems = compare(expected, row)
            checked += 1
            if problems:
                failures += 1
                print("%s  %s" % (name, time.strftime("%Y-%m-%d", time.gmtime(row["ts"]))))
                for problem in problems:
                    print("    %s" % problem)

    print("\n%d nights checked across %d sites, %d disagreeing"
          % (checked, len(SITES), failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
