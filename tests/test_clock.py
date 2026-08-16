"""Calendar arithmetic and the EU daylight-saving rule.

Checked against `zoneinfo` and `datetime` rather than against handwritten
expected values, for the same reason the sky maths is checked against pyephem:
an independent implementation catches the cases nobody thought to write down.
The firmware cannot use either — MicroPython has no `datetime` and no timezone
database — which is exactly why the reimplementation needs verifying.
"""

import datetime
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "firmware", "lib"))

import clock  # noqa: E402

try:
    from zoneinfo import ZoneInfo

    BERLIN_TZ = ZoneInfo("Europe/Berlin")
except Exception:  # pragma: no cover
    BERLIN_TZ = None

BERLIN = {"std_offset_min": 60, "dst": "eu", "abbrev": ["CET", "CEST"], "name": "Europe/Berlin"}
UTC = {"std_offset_min": 0, "dst": None, "abbrev": ["UTC", "UTC"]}
INDIA = {"std_offset_min": 330, "dst": None, "abbrev": ["IST", "IST"]}


class TestCivilDates(unittest.TestCase):
    def test_round_trip_over_two_centuries(self):
        for year in range(1970, 2100, 7):
            for month in (1, 2, 3, 6, 9, 12):
                for day in (1, 15, 28):
                    days = clock.days_from_civil(year, month, day)
                    self.assertEqual(clock.civil_from_days(days), (year, month, day))

    def test_parts_matches_datetime(self):
        for ts in (0, 946728000, 1767225600, 1786906800, 2145916800):
            reference = datetime.datetime(1970, 1, 1) + datetime.timedelta(seconds=ts)
            year, month, day, hour, minute, second, weekday = clock.parts(ts)
            self.assertEqual(
                (year, month, day, hour, minute, second),
                (
                    reference.year,
                    reference.month,
                    reference.day,
                    reference.hour,
                    reference.minute,
                    reference.second,
                ),
            )
            self.assertEqual(weekday, reference.weekday())

    def test_leap_day_exists(self):
        days = clock.days_from_civil(2028, 2, 29)
        self.assertEqual(clock.civil_from_days(days), (2028, 2, 29))


@unittest.skipIf(BERLIN_TZ is None, "no tz database")
class TestDaylightSaving(unittest.TestCase):
    def reference_offset(self, ts):
        moment = datetime.datetime.fromtimestamp(ts, datetime.timezone.utc)
        return int(moment.astimezone(BERLIN_TZ).utcoffset().total_seconds())

    def test_matches_tzdata_every_hour_for_a_year(self):
        start = 1767225600  # 2026-01-01
        for hour in range(0, 366 * 24):
            ts = start + hour * 3600
            self.assertEqual(
                clock.utc_offset(ts, BERLIN),
                self.reference_offset(ts),
                "offset differs at %s" % clock.iso_utc(ts),
            )

    def test_matches_tzdata_across_several_years(self):
        for year_start in (1735689600, 1798761600, 1830297600, 1861920000):
            for day in range(0, 365, 5):
                ts = year_start + day * 86400 + 12 * 3600
                self.assertEqual(clock.utc_offset(ts, BERLIN), self.reference_offset(ts))

    def test_transition_instants_are_exact(self):
        """The switch happens at 01:00 UTC, not at some point during that day."""
        spring = clock._last_sunday_utc(2026, 3)
        self.assertEqual(clock.utc_offset(spring - 1, BERLIN), 3600)
        self.assertEqual(clock.utc_offset(spring, BERLIN), 7200)
        autumn = clock._last_sunday_utc(2026, 10)
        self.assertEqual(clock.utc_offset(autumn - 1, BERLIN), 7200)
        self.assertEqual(clock.utc_offset(autumn, BERLIN), 3600)

    def test_transitions_land_on_a_sunday(self):
        for year in range(2026, 2036):
            for month in (3, 10):
                ts = clock._last_sunday_utc(year, month)
                self.assertEqual(clock.parts(ts)[6], 6, "not a Sunday in %d/%d" % (year, month))
                self.assertEqual(clock.parts(ts)[3], 1, "not at 01:00 UTC")
                # And it really is the last one: a week later is a different month.
                self.assertNotEqual(clock.parts(ts + 7 * 86400)[1], month)

    def test_abbreviation_follows_the_offset(self):
        summer = 1786906800  # August
        winter = 1767225600  # January
        self.assertEqual(clock.tz_abbrev(summer, BERLIN), "CEST")
        self.assertEqual(clock.tz_abbrev(winter, BERLIN), "CET")


class TestFixedOffsets(unittest.TestCase):
    def test_no_dst_rule_means_constant_offset(self):
        for ts in (1767225600, 1786906800):
            self.assertEqual(clock.utc_offset(ts, UTC), 0)
            self.assertEqual(clock.utc_offset(ts, INDIA), 330 * 60)

    def test_half_hour_offset_formats_correctly(self):
        self.assertTrue(clock.iso_local(1786906800, INDIA).endswith("+05:30"))


class TestFormatting(unittest.TestCase):
    def test_iso_utc(self):
        self.assertEqual(clock.iso_utc(1786906800), "2026-08-16T19:00:00Z")

    def test_iso_local_carries_the_summer_offset(self):
        self.assertEqual(clock.iso_local(1786906800, BERLIN), "2026-08-16T21:00:00+02:00")

    def test_hhmm_is_local(self):
        self.assertEqual(clock.hhmm(1786906800, BERLIN), "21:00")
        self.assertEqual(clock.hhmm(1786906800, UTC), "19:00")

    def test_none_passes_through(self):
        """A missing boundary must stay missing, not become 1970."""
        self.assertIsNone(clock.iso_utc(None))
        self.assertIsNone(clock.hhmm(None, BERLIN))
        self.assertIsNone(clock.iso_local(None, BERLIN))
        self.assertIsNone(clock.duration(None))

    def test_duration_reads_like_a_person_wrote_it(self):
        self.assertEqual(clock.duration(30), "30 s")
        self.assertEqual(clock.duration(90), "1 min")
        self.assertEqual(clock.duration(3600), "1 h 00 min")
        self.assertEqual(clock.duration(15960), "4 h 26 min")

    def test_plausible_rejects_the_boot_clock(self):
        """The board boots believing it is 2021; nothing may trust that."""
        self.assertFalse(clock.plausible(1609459200))  # 2021-01-01
        self.assertTrue(clock.plausible(1786906800))


if __name__ == "__main__":
    unittest.main()
