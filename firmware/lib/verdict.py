"""Turning a forecast into the only answer that matters: set up, or don't.

The beacon grades each hour of astronomical night from 0 to 100 and then looks
for the longest run of usable hours. A run is what decides the verdict, not an
average over the night: four clear hours after midnight is a session, and so is
nothing else. A night that averages 60 because it is half brilliant and half
overcast is a session; a night that sits flat at 60 all the way through is a
waste of a setup.

Where the weights come from
---------------------------

**Cloud cover dominates**, because nothing else can be worked around. High
cloud carries an extra penalty beyond its share of the total: thin cirrus looks
like a clear sky to a person and to most forecasts, but it scatters, flattens
contrast, and dims the guide star intermittently, which shows up as guiding
that mysteriously falls apart. It is the most common cause of a night that
looked fine and produced nothing.

**Gusts, not mean wind**, because the mount is the limit rather than the
optics. Steady air moves a tripod not at all; a gust arrives during a 240 s sub
and elongates every star in it. Below 15 km/h the effect is not visible, and by
40 km/h nothing usable comes out, so that is a veto rather than a penalty.

**Dew is graded from the spread between air temperature and dew point**, which
is the quantity that actually predicts it. `docs/field-operation.md` in the
astro repository records the local reality: damp nights near the dew point are
the normal case in northern Germany, not the exception, and surfaces that
radiate to a clear sky settle *below* air temperature — so a spread of 1 K
means the corrector plate is already dewing. It is a penalty and never a veto,
because a dew heater is the answer and the observer owns one.

**Moonlight scales with illuminated fraction and altitude.** A full Moon near
the zenith raises the sky background enough to swamp broadband subs; the same
Moon at 5 degrees is dimmed by air mass and usually behind something. The
fraction is raised to the power 1.5 because a half-lit Moon is far less than
half as bright as a full one — the illuminated crescent is foreshortened and
the lunar surface backscatters most strongly at opposition.

**Precipitation probability above 40 % is a veto** regardless of everything
else. Wet equipment ends a night and can end a camera.

Grading refuses to guess. An hour whose cloud cover came back null scores None
and is excluded from every run, rather than being treated as clear.
"""

import math

# Defaults; `config.json` may override any of them.
THRESHOLDS = {
    "usable_score": 55,  # an hour at or above this can be imaged
    "go_hours": 2.0,  # a run this long, at go_score, is a GO
    "go_score": 70,  # mean score of the run required for GO
    "marginal_hours": 1.0,  # anything shorter than this is a NO-GO
    "gust_veto_kmh": 40.0,
    "gust_free_kmh": 15.0,
    "precip_veto_pct": 40.0,
    "cloud_veto_pct": 90.0,
}

STATE_GO = "go"
STATE_MARGINAL = "marginal"
STATE_NO_GO = "no-go"
STATE_UNKNOWN = "unknown"


def grade_hour(row, moon_alt_deg, moon_illumination, thresholds=None):
    """Score one forecast hour from 0 to 100, or None if it cannot be judged.

    Returns a dict with the score, the penalty breakdown (so the web page can
    show *why*, not just a number), and any veto that fired.
    """
    t = dict(THRESHOLDS)
    if thresholds:
        t.update(thresholds)

    cloud = row.get("cloud_cover")
    high = row.get("cloud_cover_high")
    gusts = row.get("wind_gusts_10m")
    precip = row.get("precipitation_probability")
    temp = row.get("temperature_2m")
    dew = row.get("dew_point_2m")

    # The raw drivers travel with the grade: a client showing "score 41" and
    # nothing else is unreadable, and re-deriving cloud cover from a capped
    # penalty gives a different number than the forecast actually said.
    measured = {
        "cloud_cover": cloud,
        "cloud_cover_high": high,
        "wind_gusts_10m": gusts,
        "temperature_2m": temp,
        "dew_point_2m": dew,
        "precipitation_probability": precip,
    }

    if cloud is None:
        entry = {"ts": row.get("ts"), "score": None, "penalties": {}, "veto": "no data"}
        entry.update(measured)
        return entry

    veto = None
    if precip is not None and precip >= t["precip_veto_pct"]:
        veto = "rain likely (%d %%)" % precip
    elif gusts is not None and gusts >= t["gust_veto_kmh"]:
        veto = "gusts to %d km/h" % gusts
    elif cloud >= t["cloud_veto_pct"]:
        veto = "overcast (%d %%)" % cloud

    penalties = {}
    penalties["cloud"] = min(85.0, 0.80 * cloud + 0.20 * (high or 0.0))

    if gusts is not None and gusts > t["gust_free_kmh"]:
        penalties["wind"] = min(40.0, (gusts - t["gust_free_kmh"]) * 1.2)

    if temp is not None and dew is not None:
        spread = temp - dew
        if spread < 1.0:
            penalties["dew"] = 20.0
        elif spread < 2.0:
            penalties["dew"] = 12.0
        elif spread < 3.0:
            penalties["dew"] = 6.0

    if precip is not None and precip > 0:
        penalties["precipitation"] = precip * 0.3

    if moon_alt_deg is not None and moon_alt_deg > 0 and moon_illumination:
        altitude_factor = 0.35 + 0.65 * math.sin(math.radians(moon_alt_deg))
        penalties["moon"] = (moon_illumination ** 1.5) * altitude_factor * 45.0

    score = 0.0 if veto else max(0.0, 100.0 - sum(penalties.values()))
    entry = {
        "ts": row.get("ts"),
        "score": round(score, 1),
        "penalties": {k: round(v, 1) for k, v in penalties.items()},
        "veto": veto,
    }
    entry.update(measured)
    return entry


def darkness_of(night_info):
    """Which definition of darkness applies tonight.

    Shared so that a beacon with no forecast still reports the same darkness as
    one with a forecast. They are computed from different code paths, and the
    two disagreeing produced a status page that claimed twelve hours of a
    darkness it simultaneously called "none".
    """
    if night_info.get("dusk_astronomical") and night_info.get("dawn_astronomical"):
        return "astronomical"
    if night_info.get("dusk_nautical") and night_info.get("dawn_nautical"):
        return "nautical"
    return "none"


def _longest_run(graded, usable_score):
    """Longest contiguous run of usable hours; returns (start_index, length)."""
    best_start, best_len = -1, 0
    run_start, run_len = -1, 0
    for index, hour in enumerate(graded):
        usable = hour["score"] is not None and hour["score"] >= usable_score
        if usable:
            if run_len == 0:
                run_start = index
            run_len += 1
            if run_len > best_len:
                best_start, best_len = run_start, run_len
        else:
            run_len = 0
    return best_start, best_len


def _dominant_limits(graded):
    """Which penalties actually shaped this night, largest total first."""
    totals = {}
    for hour in graded:
        for name, value in hour["penalties"].items():
            totals[name] = totals.get(name, 0.0) + value
    return sorted(totals.items(), key=lambda kv: -kv[1])


def assess(hours, night_info, moon_at, thresholds=None, hour_seconds=3600):
    """Grade a night and return the verdict document's decision half.

    `hours` are forecast rows from `weather.to_hours`. `night_info` comes from
    `sky.night`. `moon_at(ts)` must return (altitude_deg, illuminated_fraction);
    it is injected rather than imported so the grading can be tested against
    fixed moon conditions.

    Each row is taken to represent the hour beginning at its timestamp, which
    is how Open-Meteo labels hourly data.
    """
    t = dict(THRESHOLDS)
    if thresholds:
        t.update(thresholds)

    darkness = darkness_of(night_info)
    if darkness == "astronomical":
        dark_start = night_info.get("dusk_astronomical")
        dark_end = night_info.get("dawn_astronomical")
    else:
        # Around midsummer at these latitudes the Sun never reaches -18 deg.
        # Nautical twilight is the honest fallback: it is what people actually
        # image in during those weeks, and the document says which it used.
        dark_start = night_info.get("dusk_nautical")
        dark_end = night_info.get("dawn_nautical")

    if dark_start is None or dark_end is None:
        return {
            "state": STATE_UNKNOWN,
            "score": None,
            "darkness": "none",
            "reasons": ["no astronomical or nautical night at this date"],
            "window": None,
            "hours": [],
        }

    graded = []
    for row in hours:
        ts = row.get("ts")
        if ts is None or ts + hour_seconds <= dark_start or ts >= dark_end:
            continue
        moon_alt, moon_illum = moon_at(ts)
        entry = grade_hour(row, moon_alt, moon_illum, t)
        entry["moon_alt_deg"] = round(moon_alt, 1) if moon_alt is not None else None
        graded.append(entry)

    if not graded:
        return {
            "state": STATE_UNKNOWN,
            "score": None,
            "darkness": darkness,
            "reasons": ["no forecast covering tonight's dark hours"],
            "window": None,
            "hours": [],
        }

    start_index, run_length = _longest_run(graded, t["usable_score"])
    scored = [h["score"] for h in graded if h["score"] is not None]
    night_mean = sum(scored) / len(scored) if scored else None

    best = None
    run_mean = None
    if run_length:
        run = graded[start_index : start_index + run_length]
        run_mean = sum(h["score"] for h in run) / run_length
        # Clip the stretch to the dark period: the first and last hours of a run
        # may extend past dusk or dawn, and promising imaging time that is not
        # dark is exactly the kind of lie this project is trying not to tell.
        best = {
            "start": max(run[0]["ts"], dark_start),
            "end": min(run[-1]["ts"] + hour_seconds, dark_end),
            "mean_score": round(run_mean, 1),
        }
        best["hours"] = round((best["end"] - best["start"]) / 3600.0, 1)

    if best and best["hours"] >= t["go_hours"] and run_mean >= t["go_score"]:
        state = STATE_GO
    elif best and best["hours"] >= t["marginal_hours"]:
        state = STATE_MARGINAL
    else:
        state = STATE_NO_GO

    return {
        "state": state,
        "score": round(night_mean, 1) if night_mean is not None else None,
        "darkness": darkness,
        "dark_start": dark_start,
        "dark_end": dark_end,
        "reasons": _reasons(state, graded, best, t),
        # `window` is an invitation to go outside, so it exists only when going
        # outside is the recommendation. The stretch that fell short is still
        # described in `reasons`, which is where a rejected night belongs.
        "window": best if state != STATE_NO_GO else None,
        "hours": graded,
    }


def _reasons(state, graded, best, thresholds):
    """Short human explanations, most important first.

    These are the sentences a person reads at 21:00 while deciding whether to
    carry a mount outside, so they name the limiting factor and its size rather
    than restating the score.
    """
    reasons = []
    vetoed = [h for h in graded if h["veto"]]
    limits = _dominant_limits(graded)
    count = len(graded)

    if state == STATE_GO and best:
        reasons.append(
            "%.1f h of usable dark sky, mean score %.0f" % (best["hours"], best["mean_score"])
        )
    elif state == STATE_MARGINAL and best:
        reasons.append("only %.1f h of usable dark sky" % best["hours"])
    elif best:
        reasons.append(
            "best stretch is %.1f h, below the %.1f h worth setting up for"
            % (best["hours"], thresholds["marginal_hours"])
        )
    else:
        reasons.append("no usable stretch of dark sky tonight")

    if vetoed:
        # Report the veto that occurs most, since one wet hour and eight wet
        # hours are different nights.
        kinds = {}
        for hour in vetoed:
            kind = hour["veto"].split(" (")[0].split(" to ")[0]
            kinds[kind] = kinds.get(kind, 0) + 1
        worst = max(kinds.items(), key=lambda kv: kv[1])
        reasons.append("%s for %d of %d dark hours" % (worst[0], worst[1], count))

    for name, total in limits[:2]:
        mean = total / count
        if mean < 5:
            continue
        if name == "cloud":
            covers = [h["cloud_cover"] for h in graded if h["cloud_cover"] is not None]
            if covers:
                reasons.append(
                    "cloud cover averaging %.0f %%" % (sum(covers) / len(covers))
                )
        elif name == "moon":
            lit = [h for h in graded if h["penalties"].get("moon")]
            reasons.append(
                "moon up for %d of %d dark hours" % (len(lit), count)
            )
        elif name == "wind":
            reasons.append("gusty (costing %.0f points an hour)" % mean)
        elif name == "dew":
            reasons.append("air close to the dew point — heaters on")
        elif name == "precipitation":
            reasons.append("some chance of precipitation")
    return reasons
