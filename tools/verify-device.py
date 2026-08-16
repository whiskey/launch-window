#!/usr/bin/env python3
"""Re-run the astronomy on real hardware and compare it to the host.

This exists because of one property of the target: MicroPython on the RP2040
uses 32-bit floats, and the host runs 64-bit ones. Every test in `tests/` runs
on the host, so every test in `tests/` is blind to the failure mode that
actually threatens this firmware — a formula that is correct in double
precision and quietly loses the time of day in single precision. A Julian Day
number rounds to the nearest six hours up there.

So: push `sky.py` to the board, evaluate the same vectors in both places, and
compare. A regression that only shows on hardware shows up here.

    tools/verify-device.py            push, run, compare
    tools/verify-device.py --no-push  use whatever is already on the board

Exits non-zero if any deviation exceeds the tolerances below, which are set to
the observed float32 noise floor and not to the accuracy of the underlying
model — that is what `tests/test_sky.py` measures against pyephem.
"""

from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "firmware", "lib"))

import pico  # noqa: E402
import sky  # noqa: E402

TOLERANCE = {
    "sun_alt": 0.02,  # degrees
    "moon_alt": 0.05,
    "illumination": 0.002,
    "event": 5.0,  # seconds
}

SITES = (
    ("berlin", 52.52, 13.40),
    ("westhavelland", 52.735, 12.246),
)

# Spread across a year so the day-count term is exercised at both ends, plus a
# midsummer date where astronomical night does not exist at this latitude.
VECTORS = (
    1767225600,  # 2026-01-01 00:00 UTC
    1772668800,  # 2026-03-05 00:00 UTC
    1782518400,  # 2026-06-27 00:00 UTC, near solstice
    1786906800,  # 2026-08-16 19:00 UTC
    1798761600,  # 2027-01-01 00:00 UTC
    1830297600,  # 2028-01-01 00:00 UTC, past a leap day
)

DEVICE_SCRIPT = """
import sys, gc
# Drop any cached copy first. MicroPython keeps sys.modules across raw-REPL
# calls, so a freshly pushed module is invisible until the old one is evicted
# — which silently compares the host against code that is no longer on disk.
sys.modules.pop('sky', None)
gc.collect()
import sky
SITES = %r
VECTORS = %r
for name, lat, lon in SITES:
    for ts in VECTORS:
        alt, az = sky.sun_altaz(ts, lat, lon)
        print("sun %%s %%d %%.6f %%.6f" %% (name, ts, alt, az))
        alt, az = sky.moon_altaz(ts, lat, lon)
        print("moon %%s %%d %%.6f %%.6f" %% (name, ts, alt, az))
        print("illum %%s %%d %%.6f" %% (name, ts, sky.moon_illumination(ts)))
for name, lat, lon in SITES:
    for ts in VECTORS:
        n = sky.night(ts, lat, lon)
        for key in ("sunset", "sunrise", "dusk_astronomical", "dawn_astronomical"):
            print("night %%s %%d %%s %%s" %% (name, ts, key, n[key]))
        ev = sky.moon_events(ts, ts + 86400, lat, lon)
        print("moonev %%s %%d rise %%s" %% (name, ts, ev["rise"]))
        print("moonev %%s %%d set %%s" %% (name, ts, ev["set"]))
print("DONE")
"""


def host_values():
    values = {}
    for name, lat, lon in SITES:
        for ts in VECTORS:
            alt, az = sky.sun_altaz(ts, lat, lon)
            values[("sun", name, ts)] = (alt, az)
            alt, az = sky.moon_altaz(ts, lat, lon)
            values[("moon", name, ts)] = (alt, az)
            values[("illum", name, ts)] = sky.moon_illumination(ts)
    for name, lat, lon in SITES:
        for ts in VECTORS:
            night = sky.night(ts, lat, lon)
            for key in ("sunset", "sunrise", "dusk_astronomical", "dawn_astronomical"):
                values[("night", name, ts, key)] = night[key]
            events = sky.moon_events(ts, ts + 86400, lat, lon)
            values[("moonev", name, ts, "rise")] = events["rise"]
            values[("moonev", name, ts, "set")] = events["set"]
    return values


def parse_device(text):
    values = {}
    for line in text.splitlines():
        parts = line.split()
        if not parts:
            continue
        kind = parts[0]
        if kind in ("sun", "moon") and len(parts) == 5:
            values[(kind, parts[1], int(parts[2]))] = (float(parts[3]), float(parts[4]))
        elif kind == "illum" and len(parts) == 4:
            values[(kind, parts[1], int(parts[2]))] = float(parts[3])
        elif kind in ("night", "moonev") and len(parts) == 5:
            raw = parts[4]
            values[(kind, parts[1], int(parts[2]), parts[3])] = (
                None if raw == "None" else int(raw)
            )
    return values


def main() -> int:
    push = "--no-push" not in sys.argv
    board = pico.Pico()
    print("board: %s" % board.device)
    try:
        board.enter_raw()
        if push:
            for module in ("sky.py",):
                path = os.path.join(ROOT, "firmware", "lib", module)
                with open(path, "rb") as handle:
                    board.put(handle.read(), "/lib/" + module)
                print("pushed %s" % module)
        board.check("import sys\nsys.path.insert(0, '/lib')")
        output = board.check(DEVICE_SCRIPT % (SITES, VECTORS), timeout=180)
    finally:
        board.exit_raw()
        board.close()

    if "DONE" not in output:
        print("device did not finish:\n%s" % output)
        return 1

    device = parse_device(output)
    host = host_values()

    worst = {"sun_alt": 0.0, "moon_alt": 0.0, "illumination": 0.0, "event": 0.0}
    failures = []
    for key, host_value in host.items():
        if key not in device:
            failures.append("missing on device: %s" % (key,))
            continue
        device_value = device[key]
        kind = key[0]
        if kind in ("sun", "moon"):
            metric = "sun_alt" if kind == "sun" else "moon_alt"
            deviation = abs(device_value[0] - host_value[0])
            worst[metric] = max(worst[metric], deviation)
            if deviation > TOLERANCE[metric]:
                failures.append("%s altitude off by %.4f deg" % (key, deviation))
        elif kind == "illum":
            deviation = abs(device_value - host_value)
            worst["illumination"] = max(worst["illumination"], deviation)
            if deviation > TOLERANCE["illumination"]:
                failures.append("%s illumination off by %.5f" % (key, deviation))
        else:
            if (host_value is None) != (device_value is None):
                failures.append(
                    "%s disagrees on existence: host %r device %r"
                    % (key, host_value, device_value)
                )
                continue
            if host_value is None:
                continue
            deviation = abs(device_value - host_value)
            worst["event"] = max(worst["event"], deviation)
            if deviation > TOLERANCE["event"]:
                failures.append("%s off by %.1f s" % (key, deviation))

    print("\nworst device-vs-host deviation")
    print("  sun altitude    %.4f deg   (tolerance %.2f)" % (worst["sun_alt"], TOLERANCE["sun_alt"]))
    print("  moon altitude   %.4f deg   (tolerance %.2f)" % (worst["moon_alt"], TOLERANCE["moon_alt"]))
    print("  illumination    %.5f       (tolerance %.3f)" % (worst["illumination"], TOLERANCE["illumination"]))
    print("  event times     %.1f s       (tolerance %.0f)" % (worst["event"], TOLERANCE["event"]))
    print("  vectors compared: %d" % len(host))

    if failures:
        print("\nFAILED")
        for failure in failures[:20]:
            print("  " + failure)
        return 1
    print("\nOK — single precision on the board agrees with the host")
    return 0


if __name__ == "__main__":
    sys.exit(main())
