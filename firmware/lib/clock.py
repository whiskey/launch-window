"""Time: NTP synchronisation, EU daylight saving, and formatting.

An RP2040 has no battery-backed clock. On power-up it believes it is 2021-01-01
and it drifts while running, so every timestamp this beacon prints or reasons
about depends on NTP having succeeded at least once. That makes clock state
part of the contract: `synced` is published in the status document, and a
beacon that has never synced says so rather than dating its verdict to 2021.

Civil dates are converted with Howard Hinnant's `days_from_civil` algorithm
rather than the platform's `mktime`. MicroPython's `mktime` ignores the weekday
field and the ports disagree about the epoch; a dozen lines of exact integer
arithmetic behave identically on the board and under test, which matters
because the daylight-saving rule is expressed in civil dates.

Daylight saving is implemented for the EU rule only — forward on the last
Sunday in March at 01:00 UTC, back on the last Sunday in October at 01:00 UTC.
The rule is defined in UTC across the whole union, so it needs no local time to
evaluate and no zone database. `dst: null` in the site config gives a fixed
offset for anywhere else.
"""

try:
    import time
except ImportError:  # pragma: no cover
    time = None

DAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def days_from_civil(year, month, day):
    """Days since 1970-01-01 for a civil date (proleptic Gregorian)."""
    year -= month <= 2
    era = (year if year >= 0 else year - 399) // 400
    yoe = year - era * 400
    doy = (153 * (month + (-3 if month > 2 else 9)) + 2) // 5 + day - 1
    doe = yoe * 365 + yoe // 4 - yoe // 100 + doy
    return era * 146097 + doe - 719468


def civil_from_days(z):
    """Inverse of `days_from_civil`: returns (year, month, day)."""
    z += 719468
    era = (z if z >= 0 else z - 146096) // 146097
    doe = z - era * 146097
    yoe = (doe - doe // 1460 + doe // 36524 - doe // 146096) // 365
    y = yoe + era * 400
    doy = doe - (365 * yoe + yoe // 4 - yoe // 100)
    mp = (5 * doy + 2) // 153
    d = doy - (153 * mp + 2) // 5 + 1
    m = mp + (3 if mp < 10 else -9)
    return y + (m <= 2), m, d


def parts(ts):
    """Break a Unix timestamp into (year, month, day, hour, minute, second, weekday).

    Weekday is 0 = Monday, matching both `time.gmtime` implementations.
    """
    ts = int(ts)
    days, rem = divmod(ts, 86400)
    year, month, day = civil_from_days(days)
    hour, rem = divmod(rem, 3600)
    minute, second = divmod(rem, 60)
    return year, month, day, hour, minute, second, (days + 3) % 7


def _last_sunday_utc(year, month, hour_utc=1):
    """Unix timestamp of the last Sunday of a month at a given UTC hour."""
    # Day 0 of the following month is the last day of this one.
    next_month_start = days_from_civil(
        year + (month == 12), 1 if month == 12 else month + 1, 1
    )
    last_day = next_month_start - 1
    weekday = (last_day + 3) % 7  # 0 = Monday, so Sunday is 6
    last_sunday = last_day - ((weekday + 1) % 7)
    return last_sunday * 86400 + hour_utc * 3600


def utc_offset(ts, tz):
    """Offset from UTC in seconds for a timestamp, honouring the EU DST rule."""
    base = int(tz.get("std_offset_min", 0)) * 60
    if tz.get("dst") != "eu":
        return base
    year = parts(ts)[0]
    start = _last_sunday_utc(year, 3)
    end = _last_sunday_utc(year, 10)
    return base + 3600 if start <= ts < end else base


def tz_abbrev(ts, tz):
    names = tz.get("abbrev") or ("UTC", "UTC")
    is_dst = utc_offset(ts, tz) != int(tz.get("std_offset_min", 0)) * 60
    return names[1] if is_dst else names[0]


def iso_utc(ts):
    """RFC 3339 timestamp in UTC, the form the status documents use."""
    if ts is None:
        return None
    y, mo, d, h, mi, s, _ = parts(ts)
    return "%04d-%02d-%02dT%02d:%02d:%02dZ" % (y, mo, d, h, mi, s)


def iso_local(ts, tz):
    """RFC 3339 timestamp with the site's numeric offset."""
    if ts is None:
        return None
    offset = utc_offset(ts, tz)
    y, mo, d, h, mi, s, _ = parts(ts + offset)
    sign = "+" if offset >= 0 else "-"
    return "%04d-%02d-%02dT%02d:%02d:%02d%s%02d:%02d" % (
        y, mo, d, h, mi, s, sign, abs(offset) // 3600, (abs(offset) % 3600) // 60
    )


def hhmm(ts, tz):
    """Local wall-clock time as HH:MM — what a human reads off the page."""
    if ts is None:
        return None
    y, mo, d, h, mi, s, _ = parts(ts + utc_offset(ts, tz))
    return "%02d:%02d" % (h, mi)


def duration(seconds):
    """Human duration such as '4 h 20 min', for spans measured in hours."""
    if seconds is None:
        return None
    seconds = int(seconds)
    if seconds < 60:
        return "%d s" % seconds
    if seconds < 3600:
        return "%d min" % (seconds // 60)
    return "%d h %02d min" % (seconds // 3600, (seconds % 3600) // 60)


def now():
    """Current Unix timestamp in UTC."""
    return time.time()


def sync_ntp(host="pool.ntp.org", timeout=4):
    """Set the RTC from NTP. Returns True on success.

    Failure is not an error worth stopping for: the beacon keeps running on its
    drifting clock and publishes `clock.synced = false` so a client can see
    that every timestamp in the document is suspect.
    """
    try:
        import ntptime

        ntptime.host = host
        ntptime.timeout = timeout
        ntptime.settime()
        return True
    except Exception:
        return False


def plausible(ts):
    """Whether a timestamp can be a real current time.

    The board boots believing it is 2021-01-01. Anything before 2025 means NTP
    has not landed yet, whatever else the code thinks.
    """
    return ts > 1735689600  # 2025-01-01T00:00:00Z
