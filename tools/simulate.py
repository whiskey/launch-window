#!/usr/bin/env python3
"""Run the beacon's firmware on this machine, against the live forecast.

    tools/simulate.py                    print tonight's verdict and exit
    tools/simulate.py --serve [--port N] serve the real page at localhost:8080
    tools/simulate.py --date 2026-12-24  pretend it is a different night
    tools/simulate.py --site 52.7,12.2   somewhere other than the config's site

This imports the same modules the board runs — `sky`, `weather`, `verdict`,
`state`, `server`, `page` — with no substitutes. The device-specific parts
degrade honestly on a laptop: there is no `machine`, so the core temperature is
null, and no WiFi object, so the signal strength is null. Everything that makes
a decision is the code under test.

It is the fastest way to see what a change to the weights does to a real night,
and it works with no board plugged in.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "firmware", "lib"))

import clock  # noqa: E402
import page  # noqa: E402
import server as server_mod  # noqa: E402
import state as state_mod  # noqa: E402
import store  # noqa: E402

BARS = " ▁▂▃▄▅▆▇█"


def argument(flag, fallback=None):
    if flag in sys.argv:
        index = sys.argv.index(flag)
        if index + 1 < len(sys.argv):
            return sys.argv[index + 1]
    return fallback


def load_config():
    config = store.load(os.path.join(ROOT, "firmware", "config.json")) or {}
    site = argument("--site")
    if site:
        latitude, longitude = (float(part) for part in site.split(","))
        config["site"] = dict(config["site"], latitude=latitude, longitude=longitude,
                              name="%.3f, %.3f" % (latitude, longitude))
    return config


def chosen_time():
    date = argument("--date")
    if not date:
        return int(time.time())
    year, month, day = (int(part) for part in date.split("-"))
    # 22:00 UTC on that date: inside the night everywhere this is aimed at.
    return clock.days_from_civil(year, month, day) * 86400 + 22 * 3600


def bar(score, width=24):
    if score is None:
        return "?" * width
    filled = int(round(score / 100.0 * width))
    return "█" * filled + "·" * (width - filled)


def report(beacon, now):
    document = beacon.document(now)
    verdict = document["verdict"]
    night = document["night"]
    moon = document["moon"]
    tz = beacon.tz

    print("\n%s — %s local" % (document["site"]["name"], clock.hhmm(now, tz)))
    print("=" * 58)
    print("  %s" % verdict["state"].upper())
    for reason in verdict["reasons"]:
        print("    — %s" % reason)
    if verdict["window"]:
        window = verdict["window"]
        print(
            "  window: %s – %s  (%.1f h, mean score %.0f)"
            % (window["start_local"], window["end_local"], window["hours"], window["mean_score"])
        )

    print("\n  sunset %s   dusk %s   dawn %s   sunrise %s" % (
        night["sunset_local"] or "—",
        night["dusk_astronomical_local"] or "—",
        night["dawn_astronomical_local"] or "—",
        night["sunrise_local"] or "—",
    ))
    print("  darkness: %s (%s)   moon: %.0f %% %s, %s–%s%s" % (
        night["dark_duration"] or "none",
        night["darkness"] or "none",
        moon["illumination"] * 100,
        moon["phase"],
        moon["rise_local"] or "—",
        moon["set_local"] or "—",
        "  ← interferes" if moon["interferes"] else "",
    ))

    if verdict["hours"]:
        print("\n  hour   score                      cloud  gust  spread  moon")
        for hour in verdict["hours"]:
            spread = None
            if hour["temperature_2m"] is not None and hour["dew_point_2m"] is not None:
                spread = hour["temperature_2m"] - hour["dew_point_2m"]
            print(
                "  %s  %s %5s  %4s%%  %4s  %5s  %5s %s"
                % (
                    hour["local"],
                    bar(hour["score"]),
                    "—" if hour["score"] is None else "%.0f" % hour["score"],
                    "—" if hour["cloud_cover"] is None else hour["cloud_cover"],
                    "—" if hour["wind_gusts_10m"] is None else "%.0f" % hour["wind_gusts_10m"],
                    "—" if spread is None else "%.1fK" % spread,
                    "—" if (hour["moon_alt_deg"] or -1) <= 0 else "%.0f°" % hour["moon_alt_deg"],
                    "  VETO: " + hour["veto"] if hour["veto"] else "",
                )
            )

    data = document["data"]
    print("\n  forecast: %s, %s%s" % (
        data["source"],
        "%s old" % data["age"] if data["age"] is not None else "never fetched",
        "  ← STALE" if data["stale"] else "",
    ))
    if data["error"]:
        print("  error: %s" % data["error"])
    print("  led pattern: %s" % beacon.led_pattern(now))
    return document


async def run():
    config = load_config()
    now = chosen_time()
    beacon = state_mod.Beacon(config, wifi=None, boot_ts=now)
    # The simulator keeps its cache out of the repository; the board writes its
    # own next to the firmware.
    state_mod.CACHE_PATH = os.path.join(
        os.environ.get("TMPDIR", "/tmp"), "launch-window-cache.json"
    )

    print("fetching forecast for %s ..." % clock.iso_utc(now))
    if not await beacon.refresh(now):
        print("  fetch failed: %s" % beacon.last_error)
    document = report(beacon, now)

    if "--json" in sys.argv:
        print("\n" + json.dumps(document, indent=2))

    if "--serve" in sys.argv:
        port = int(argument("--port", "8080"))

        def status_page(request):
            return (
                200,
                "text/html; charset=utf-8",
                page.render(beacon.document(chosen_time() if argument("--date") else None), request.query.get("theme", "night")),
            )

        routes = {
            "/": status_page,
            "/api/v1/beacon": lambda r: server_mod.json_response(beacon.document()),
            "/api/v1/health": lambda r: server_mod.json_response({"ok": True, "schema": state_mod.SCHEMA}),
        }
        await server_mod.Server(routes).serve("127.0.0.1", port)
        print("\n  serving the real page at http://127.0.0.1:%d/  (ctrl-c to stop)" % port)
        while True:
            await asyncio.sleep(3600)


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print()
