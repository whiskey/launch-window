"""Sun and moon geometry, computed on the beacon itself.

Why compute this on a microcontroller instead of asking a server: darkness and
moonlight are the two inputs that are perfectly predictable, and they are the
two the beacon must never be wrong about. Weather needs an internet round trip
and can go stale; the sky cannot. A beacon that has lost its network still
knows when astronomical night starts tonight, and says so.

Single-precision arithmetic, and what it forces
-----------------------------------------------

MicroPython on the RP2040 has no FPU and builds with 32-bit floats. A float32
carries 24 bits of significand, so a Julian Day number — about 2.46 million —
quantises to 0.25 days. On the board, `2460904.5` evaluates to `2460905.0`:
the time of day disappears entirely. Textbook formulations of this maths are
written in double precision and fail silently here, producing plausible
numbers that are hours wrong.

So no large quantity is ever allowed to carry the time fraction:

- Time is a Unix integer throughout, split into whole days since J2000 (an
  exact `int`) and a fraction of a day (a float below 1.0, where float32 has
  eight significant digits to spare).
- Angles of the form `const + rate * days` are reduced with `_angle`, which
  takes the integer part of the rate through exact integer arithmetic mod 360
  and lets only the small remainder touch a float. Without this, the Moon's
  mean longitude — 13.18 deg/day over 9700 days — lands at 127825 deg, where
  float32 steps in units of 0.016 deg.
- Rise and set searches bisect over integer seconds, so they converge to one
  second rather than to whatever the float spacing happens to be.

`tools/verify-device.py` re-runs the host's test vectors on real hardware and
compares, rather than assuming any of this works. It currently reports the
board agreeing with the host to 0.002 deg in altitude and 1 second on rise and
set times. Before the constants were pre-split it reported 0.67 deg and 339
seconds, with every host test still passing.

Accuracy, measured against pyephem over a year at four sites from 28 to 64
degrees north (`tests/test_sky.py`):

- Sun altitude within 0.012 deg; sunset and twilight boundaries within 4 s.
- Moon altitude within 0.55 deg, rise and set within 3 minutes, illuminated
  fraction within 0.002.
- Azimuth degrades near the zenith where it is ill-conditioned by definition,
  worst case 3.8 deg at 85 deg altitude. Nothing here decides on azimuth.

Positions come from the low-precision solar series in the Astronomical Almanac
and the truncated ELP series in Meeus chapter 47, keeping terms above roughly
0.1 deg. The lunar terms drop the T-squared and T-cubed corrections, worth
0.0006 deg at this epoch and growing slowly; they would matter for a century,
not for a decade. The Moon also gets the horizontal-parallax correction that
turns a geocentric altitude into a topocentric one — up to a degree, and the
difference between "already set" and "still washing out the target".

Pure stdlib maths: this module imports nothing but `math`, so it runs
unchanged on MicroPython and on CPython under test.
"""

import math

# J2000.0 (2000-01-01 12:00 UTC) as a Unix timestamp. MicroPython on rp2 uses
# the Unix epoch, verified on the board.
J2000_UNIX = 946728000

_EARTH_RADIUS_KM = 6378.14

# Mean motions in degrees per day, from Meeus' per-century coefficients divided
# by 36525, and written pre-split into (whole_degrees, remainder).
#
# The split is in the source, not computed at run time, because the constant
# itself does not survive float32. Writing 360.98564736629 and taking its
# fractional part on the board yields 0.985778809: the literal is stored with
# an error of 1.3e-4, which over the 9724 days since J2000 accumulates to 1.28
# degrees of sidereal time — five minutes, and every rise and set time wrong by
# that much. Stored as 0.98564736629 alone, a float32 holds it to 6e-8, and the
# same 9724 days accumulate 0.0006 degrees.
#
# This is the single most important detail in the file, and the reason
# tools/verify-device.py exists.
_SUN_MEAN_LON_RATE = (0, 0.9856474)
_SUN_MEAN_ANOM_RATE = (0, 0.9856003)
_GMST_RATE = (360, 0.98564736629)
_MOON_MEAN_LON_RATE = (13, 0.176396475)
_MOON_ANOM_RATE = (13, 0.064992950)
_ELONGATION_RATE = (12, 0.190749114)
_ARG_LAT_RATE = (13, 0.229350240)
_MOON_SUN_ANOM_RATE = (0, 0.985600282)

# Standard altitude of the Sun's upper limb at sunrise and sunset: refraction
# at the horizon plus the solar semi-diameter. Twilight is defined
# geometrically and takes no refraction.
SUNRISE_ALT = -0.833
CIVIL_ALT = -6.0
NAUTICAL_ALT = -12.0
ASTRONOMICAL_ALT = -18.0


def epoch_split(ts):
    """Time since J2000 as (whole_days: int, day_fraction: float).

    Keeping these apart is the whole trick. `days` stays an exact integer and
    `fraction` stays below 1.0, so neither ever needs more precision than a
    float32 has.
    """
    seconds = int(ts) - J2000_UNIX
    days, remainder = divmod(seconds, 86400)
    return days, remainder / 86400.0


def _angle(constant, rate, days, fraction):
    """`constant + rate * (days + fraction)` in degrees, reduced mod 360.

    `rate` is the pre-split (whole, remainder) pair. The whole degrees per day
    are multiplied by the integer day count in exact integer arithmetic and
    reduced mod 360 before they can overflow a float32's significand; only the
    sub-1.0 remainder is ever multiplied by the day count in floating point,
    where its relative precision is 6e-8 rather than 4e-7.

    The day fraction is below 1.0, so multiplying it by the full rate costs at
    most the rate's own storage error — a ten-thousandth of a degree, not the
    degree and a quarter that the same error buys when multiplied by 9724 days.
    """
    whole, remainder = rate
    return (
        constant
        + (whole * days) % 360
        + (remainder * days) % 360.0
        + whole * fraction
        + remainder * fraction
    ) % 360.0


def gmst_deg(days, fraction):
    """Greenwich mean sidereal time in degrees (IAU 1982 expression)."""
    return _angle(280.46061837, _GMST_RATE, days, fraction)


def _obliquity(days):
    return math.radians(23.439 - 0.0000004 * days)


def sun_equatorial(days, fraction):
    """Geocentric right ascension and declination of the Sun, in radians."""
    mean_lon = _angle(280.460, _SUN_MEAN_LON_RATE, days, fraction)
    mean_anom = math.radians(_angle(357.528, _SUN_MEAN_ANOM_RATE, days, fraction))
    ecliptic_lon = math.radians(
        mean_lon + 1.915 * math.sin(mean_anom) + 0.020 * math.sin(2 * mean_anom)
    )
    obliquity = _obliquity(days)
    ra = math.atan2(
        math.cos(obliquity) * math.sin(ecliptic_lon), math.cos(ecliptic_lon)
    )
    dec = math.asin(math.sin(obliquity) * math.sin(ecliptic_lon))
    return ra, dec


def moon_ecliptic(days, fraction):
    """Geocentric ecliptic longitude, latitude (radians) and distance (km)."""
    mean_lon = _angle(218.3164477, _MOON_MEAN_LON_RATE, days, fraction)
    sun_anom = math.radians(_angle(357.5291092, _MOON_SUN_ANOM_RATE, days, fraction))
    moon_anom = math.radians(_angle(134.9633964, _MOON_ANOM_RATE, days, fraction))
    elongation = math.radians(_angle(297.8501921, _ELONGATION_RATE, days, fraction))
    arg_lat = math.radians(_angle(93.2720950, _ARG_LAT_RATE, days, fraction))

    lon = mean_lon + (
        6.289 * math.sin(moon_anom)
        + 1.274 * math.sin(2 * elongation - moon_anom)
        + 0.658 * math.sin(2 * elongation)
        + 0.214 * math.sin(2 * moon_anom)
        - 0.186 * math.sin(sun_anom)
        - 0.114 * math.sin(2 * arg_lat)
    )
    lat = (
        5.128 * math.sin(arg_lat)
        + 0.281 * math.sin(moon_anom + arg_lat)
        - 0.278 * math.sin(arg_lat - moon_anom)
        - 0.173 * math.sin(2 * elongation - arg_lat)
    )
    dist = (
        385001.0
        - 20905.0 * math.cos(moon_anom)
        - 3699.0 * math.cos(2 * elongation - moon_anom)
        - 2956.0 * math.cos(2 * elongation)
        - 570.0 * math.cos(2 * moon_anom)
    )
    return math.radians(lon % 360.0), math.radians(lat), dist


def _ecliptic_to_equatorial(lon, lat, days):
    obliquity = _obliquity(days)
    sin_lat, cos_lat = math.sin(lat), math.cos(lat)
    sin_lon, cos_lon = math.sin(lon), math.cos(lon)
    sin_obl, cos_obl = math.sin(obliquity), math.cos(obliquity)
    ra = math.atan2(sin_lon * cos_obl - (sin_lat / cos_lat) * sin_obl, cos_lon)
    dec = math.asin(sin_lat * cos_obl + cos_lat * sin_obl * sin_lon)
    return ra, dec


def _to_horizontal(ra, dec, days, fraction, lat_deg, lon_deg):
    """Convert to altitude/azimuth. Azimuth is measured from north, eastwards."""
    lst = math.radians((gmst_deg(days, fraction) + lon_deg) % 360.0)
    hour_angle = lst - ra
    lat = math.radians(lat_deg)
    sin_alt = math.sin(lat) * math.sin(dec) + math.cos(lat) * math.cos(dec) * math.cos(
        hour_angle
    )
    alt = math.asin(max(-1.0, min(1.0, sin_alt)))
    az = math.atan2(
        -math.cos(dec) * math.sin(hour_angle),
        math.cos(lat) * math.sin(dec)
        - math.sin(lat) * math.cos(dec) * math.cos(hour_angle),
    )
    return math.degrees(alt), math.degrees(az) % 360.0


def sun_altaz(ts, lat_deg, lon_deg):
    """Altitude and azimuth of the Sun in degrees at a Unix timestamp."""
    days, fraction = epoch_split(ts)
    ra, dec = sun_equatorial(days, fraction)
    return _to_horizontal(ra, dec, days, fraction, lat_deg, lon_deg)


def moon_altaz(ts, lat_deg, lon_deg):
    """Topocentric altitude and azimuth of the Moon in degrees."""
    days, fraction = epoch_split(ts)
    lon, lat, dist = moon_ecliptic(days, fraction)
    ra, dec = _ecliptic_to_equatorial(lon, lat, days)
    alt, az = _to_horizontal(ra, dec, days, fraction, lat_deg, lon_deg)
    parallax = math.degrees(math.asin(_EARTH_RADIUS_KM / dist))
    return alt - parallax * math.cos(math.radians(alt)), az


def moon_illumination(ts):
    """Illuminated fraction of the Moon's disc, 0.0 (new) to 1.0 (full)."""
    days, fraction = epoch_split(ts)
    moon_lon, moon_lat, _ = moon_ecliptic(days, fraction)
    sun_ra, sun_dec = sun_equatorial(days, fraction)
    moon_ra, moon_dec = _ecliptic_to_equatorial(moon_lon, moon_lat, days)
    cos_elongation = math.sin(sun_dec) * math.sin(moon_dec) + math.cos(
        sun_dec
    ) * math.cos(moon_dec) * math.cos(sun_ra - moon_ra)
    elongation = math.acos(max(-1.0, min(1.0, cos_elongation)))
    # The Sun's distance dwarfs the Moon's, so the phase angle is the
    # supplement of the elongation to well within this module's accuracy.
    return (1.0 + math.cos(math.pi - elongation)) / 2.0


SYNODIC_MONTH = 29.530588853
# Reference new moon, 2000-01-06 18:14 UTC, as days since J2000.
_NEW_MOON_EPOCH_DAYS = 5.2597


def moon_age_days(ts):
    """Days since the last new moon, from the mean synodic cycle."""
    days, fraction = epoch_split(ts)
    return (days + fraction - _NEW_MOON_EPOCH_DAYS) % SYNODIC_MONTH


PHASE_NAMES = (
    "new",
    "waxing crescent",
    "first quarter",
    "waxing gibbous",
    "full",
    "waning gibbous",
    "last quarter",
    "waning crescent",
)


def moon_phase_name(ts):
    """Conventional name of the current phase.

    Named from the age in the synodic cycle rather than from the illuminated
    fraction, because illumination alone cannot tell waxing from waning.
    """
    index = int((moon_age_days(ts) / SYNODIC_MONTH) * 8 + 0.5) % 8
    return PHASE_NAMES[index]


def crossings(altitude_fn, start_ts, end_ts, target_alt, step=300):
    """Times in [start, end) where altitude crosses `target_alt`.

    Returns a list of (timestamp, rising) pairs, `rising` being True when the
    body is ascending through the target. Coarse sampling at `step` seconds,
    then integer bisection to one second.

    Sampling rather than solving in closed form: closed forms need special
    cases for bodies that never rise or never set, and sampling degrades into
    "no crossing found" without any of them. The cost is about 300 evaluations
    of a trigonometric series, a few milliseconds here.
    """
    start_ts, end_ts = int(start_ts), int(end_ts)
    found = []
    previous_ts = start_ts
    previous = altitude_fn(start_ts) - target_alt
    ts = start_ts + step
    while ts <= end_ts:
        current = altitude_fn(ts) - target_alt
        if (previous < 0.0) != (current < 0.0):
            low, high = previous_ts, ts
            low_value = previous
            while high - low > 1:
                middle = (low + high) // 2
                middle_value = altitude_fn(middle) - target_alt
                if (low_value < 0.0) != (middle_value < 0.0):
                    high = middle
                else:
                    low, low_value = middle, middle_value
            found.append((high, current > 0.0))
        previous_ts, previous = ts, current
        ts += step
    return found


def _first(events, rising):
    for ts, is_rising in events:
        if is_rising == rising:
            return ts
    return None


def night(ts, lat_deg, lon_deg):
    """The coming night's boundaries, as Unix timestamps.

    "The coming night" is measured over a window that starts 12 hours back, so
    calling this in the afternoon describes tonight and calling it at 03:00
    still describes the night in progress rather than skipping to the next one.

    Any boundary the Sun does not reach is None rather than a guess. At these
    latitudes astronomical night genuinely does not exist for weeks around the
    summer solstice, and a beacon that invented one would be lying about the
    only thing it can compute exactly.
    """

    def sun_alt(t):
        return sun_altaz(t, lat_deg, lon_deg)[0]

    start = int(ts) - 12 * 3600
    end = int(ts) + 24 * 3600

    sun_events = crossings(sun_alt, start, end, SUNRISE_ALT)
    dark_events = crossings(sun_alt, start, end, ASTRONOMICAL_ALT)
    nautical_events = crossings(sun_alt, start, end, NAUTICAL_ALT)

    result = {
        "sunset": _first(sun_events, False),
        "sunrise": None,
        "dusk_astronomical": _first(dark_events, False),
        "dawn_astronomical": None,
        "dusk_nautical": _first(nautical_events, False),
        "dawn_nautical": None,
        "dark_seconds": 0,
    }
    if result["sunset"] is not None:
        result["sunrise"] = _first(
            [e for e in sun_events if e[0] > result["sunset"]], True
        )
    dusk = result["dusk_astronomical"]
    if dusk is not None:
        result["dawn_astronomical"] = _first(
            [e for e in dark_events if e[0] > dusk], True
        )
        if result["dawn_astronomical"] is not None:
            result["dark_seconds"] = result["dawn_astronomical"] - dusk
    nautical_dusk = result["dusk_nautical"]
    if nautical_dusk is not None:
        result["dawn_nautical"] = _first(
            [e for e in nautical_events if e[0] > nautical_dusk], True
        )
    return result


def moon_events(start_ts, end_ts, lat_deg, lon_deg):
    """Moonrise and moonset within a window, either of which may be None."""

    def moon_alt(t):
        return moon_altaz(t, lat_deg, lon_deg)[0]

    events = crossings(moon_alt, start_ts, end_ts, 0.0)
    return {"rise": _first(events, True), "set": _first(events, False)}
