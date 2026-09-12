#!/usr/bin/env python3
"""Diff the Swift grading port against `firmware/lib/verdict.py`.

    app/tools/compare-verdict.py <path-to-LaunchWindow-binary> [--cases 400]

`selfCheck` compares the two on whatever the sky is doing tonight, which is one
case and usually a dull one. This constructs nights the weather is not currently
offering — moonlit, gusty, dewy, clearing at three, overcast for half the night,
an hour with no cloud reading at all — and holds the two implementations to each
other across all of them.

Cases are generated from a fixed seed, so a failure is reproducible.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import random
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "firmware" / "lib"))

import sky  # noqa: E402
import verdict as verdict_mod  # noqa: E402

SCORE_TOLERANCE = 0.1001

# Sites and seasons that exercise different shapes of night: a long winter one,
# a short summer one, one with no astronomical night at all.
SITES = [
    ("Berlin", 52.52, 13.4),
    ("Tromsø", 69.65, 18.96),
    ("Tenerife", 28.3, -16.5),
]
# Unix timestamps at 20:00 UTC, spread through a year from 2026-01-15.
BASES = [1768507200 + n * 37 * 86400 for n in range(10)]


def make_hours(rng, reference):
    """A night's worth of hourly rows, deliberately varied and sometimes ugly."""
    start = reference - 6 * 3600
    style = rng.choice(["clear", "overcast", "clearing", "windy", "dewy", "patchy", "gappy"])
    rows = []
    for index in range(20):
        ts = start + index * 3600
        if style == "clear":
            cloud = rng.uniform(0, 20)
        elif style == "overcast":
            cloud = rng.uniform(85, 100)
        elif style == "clearing":
            cloud = max(0.0, 100 - index * 9 + rng.uniform(-6, 6))
        elif style == "patchy":
            cloud = rng.choice([5, 40, 95, 60, 15])
        else:
            cloud = rng.uniform(0, 100)
        temp = rng.uniform(-5, 25)
        spread = rng.uniform(0, 6) if style == "dewy" else rng.uniform(0, 12)
        row = {
            "ts": ts,
            "cloud_cover": round(cloud, 1),
            "cloud_cover_high": round(min(100.0, cloud * rng.uniform(0, 1.2)), 1),
            "wind_gusts_10m": round(rng.uniform(20, 55) if style == "windy"
                                    else rng.uniform(0, 35), 1),
            "temperature_2m": round(temp, 1),
            "dew_point_2m": round(temp - spread, 1),
            "precipitation_probability": round(rng.choice([0, 0, 5, 20, 45, 70]), 1),
        }
        # An hour whose cloud cover never arrived: scores None, and must be
        # excluded from every run rather than treated as clear.
        if style == "gappy" and index in (3, 4):
            row["cloud_cover"] = None
        rows.append(row)
    return rows


def python_verdict(rows, reference, latitude, longitude):
    night = sky.night(reference, latitude, longitude)

    def moon_at(ts):
        return (sky.moon_altaz(ts, latitude, longitude)[0], sky.moon_illumination(ts))

    decision = verdict_mod.assess(rows, night, moon_at)
    window = decision["window"]
    return {
        "state": decision["state"],
        "score": decision["score"],
        "reasons": decision["reasons"],
        "window": None if not window else {
            "hours": window["hours"], "mean_score": window["mean_score"],
            "start": window["start"], "end": window["end"],
        },
        "hours": [{"ts": h["ts"], "score": h["score"], "veto": h["veto"],
                   "moon_alt_deg": h["moon_alt_deg"], "penalties": h["penalties"]}
                  for h in decision["hours"]],
    }


def swift_verdict(binary, rows, reference, latitude, longitude):
    payload = {"lat": latitude, "lon": longitude, "reference": reference, "hours": rows}
    # Inline rather than a file: the app is sandboxed and cannot read a path
    # outside its own container.
    environment = dict(os.environ)
    environment["LW_VERDICT"] = json.dumps(payload)
    completed = subprocess.run([binary], capture_output=True, text=True,
                               env=environment, timeout=120)
    for line in completed.stdout.splitlines():
        if line.startswith("VERDICT "):
            return json.loads(line[len("VERDICT "):])
    sys.exit("no VERDICT line:\n%s\n%s" % (completed.stdout[-1500:], completed.stderr[-1500:]))


def near(a, b, tolerance=SCORE_TOLERANCE):
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return abs(a - b) <= tolerance


def compare(expected, actual):
    problems = []
    if expected["state"] != actual["state"]:
        problems.append("state python=%s swift=%s" % (expected["state"], actual["state"]))
    if not near(expected["score"], actual["score"]):
        problems.append("score python=%s swift=%s" % (expected["score"], actual["score"]))
    if expected["reasons"] != actual["reasons"]:
        problems.append("reasons\n      python=%s\n      swift =%s"
                        % (expected["reasons"], actual["reasons"]))

    ew, aw = expected["window"], actual["window"]
    if (ew is None) != (aw is None):
        problems.append("window python=%s swift=%s" % (ew, aw))
    elif ew is not None:
        for key in ("hours", "mean_score", "start", "end"):
            if not near(ew[key], aw[key], 1.0 if key in ("start", "end") else SCORE_TOLERANCE):
                problems.append("window.%s python=%s swift=%s" % (key, ew[key], aw[key]))

    if len(expected["hours"]) != len(actual["hours"]):
        problems.append("hour count python=%d swift=%d"
                        % (len(expected["hours"]), len(actual["hours"])))
        return problems
    for mine, theirs in zip(expected["hours"], actual["hours"]):
        if mine["ts"] != theirs["ts"]:
            problems.append("hour ts python=%s swift=%s" % (mine["ts"], theirs["ts"]))
            continue
        if not near(mine["score"], theirs["score"]):
            problems.append("%s score python=%s swift=%s"
                            % (mine["ts"], mine["score"], theirs["score"]))
        if mine["veto"] != theirs["veto"]:
            problems.append("%s veto python=%s swift=%s"
                            % (mine["ts"], mine["veto"], theirs["veto"]))
        if not near(mine["moon_alt_deg"], theirs["moon_alt_deg"], 0.1001):
            problems.append("%s moon_alt python=%s swift=%s"
                            % (mine["ts"], mine["moon_alt_deg"], theirs["moon_alt_deg"]))
        for name in set(mine["penalties"]) | set(theirs["penalties"]):
            if not near(mine["penalties"].get(name), theirs["penalties"].get(name)):
                problems.append("%s penalty %s python=%s swift=%s"
                                % (mine["ts"], name, mine["penalties"].get(name),
                                   theirs["penalties"].get(name)))
    return problems


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary")
    parser.add_argument("--cases", type=int, default=120)
    parser.add_argument("--seed", type=int, default=20260912)
    arguments = parser.parse_args()

    rng = random.Random(arguments.seed)
    failures = 0
    states = {}

    for case in range(arguments.cases):
        name, latitude, longitude = SITES[case % len(SITES)]
        reference = BASES[(case // len(SITES)) % len(BASES)]
        rows = make_hours(rng, reference)
        expected = python_verdict(rows, reference, latitude, longitude)
        actual = swift_verdict(arguments.binary, rows, reference, latitude, longitude)
        states[expected["state"]] = states.get(expected["state"], 0) + 1
        problems = compare(expected, actual)
        if problems:
            failures += 1
            print("case %d  %s  reference=%d" % (case, name, reference))
            for problem in problems:
                print("    %s" % problem)

    print("\n%d cases, %d disagreeing" % (arguments.cases, failures))
    print("states exercised: %s" % ", ".join("%s=%d" % kv for kv in sorted(states.items())))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
