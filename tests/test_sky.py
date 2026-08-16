"""Sun and moon geometry, checked against an independent ephemeris.

The reference is pyephem, which implements VSOP87 and ELP2000 in full. It is
not a dependency of anything that ships — it is installed into a throwaway
virtualenv to run these tests, and the suite skips them cleanly when it is
absent so `python3 tests/run.py` still works on a bare machine.

Testing against a second implementation rather than against stored expected
values is deliberate: hardcoded values would only prove the code still does
what it did the day the values were captured, including whatever was wrong
with it that day.

The invariant tests below need no reference at all, and they are the ones that
catch the errors an ephemeris comparison would miss — a night that ends before
it begins, a phase name that disagrees with the illuminated fraction.
"""

import math
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "firmware", "lib"))

import sky  # noqa: E402

try:
    import datetime

    import ephem
except ImportError:  # pragma: no cover
    ephem = None

BERLIN = (52.52, 13.40)
WESTHAVELLAND = (52.735, 12.246)
TENERIFE = (28.30, -16.51)
REYKJAVIK = (64.15, -21.94)
SITES = (BERLIN, WESTHAVELLAND, TENERIFE, REYKJAVIK)

YEAR_START = 1767225600  # 2026-01-01 00:00 UTC


def observer(lat, lon, ts):
    obs = ephem.Observer()
    obs.lat, obs.lon = str(lat), str(lon)
    obs.elevation = 0
    obs.pressure = 0  # sky.py applies no refraction either
    obs.date = ephem.Date(
        datetime.datetime(1970, 1, 1) + datetime.timedelta(seconds=ts)
    )
    return obs


def to_unix(ephem_date):
    return (ephem_date.datetime() - datetime.datetime(1970, 1, 1)).total_seconds()


@unittest.skipIf(ephem is None, "pyephem not installed")
class TestAgainstEphemeris(unittest.TestCase):
    """Worst-case deviations over a year at four latitudes."""

    def test_sun_altitude_within_0_02_deg(self):
        worst = 0.0
        for lat, lon in SITES:
            for day in range(0, 365, 7):
                for hour in (0, 5, 11, 17, 21):
                    ts = YEAR_START + day * 86400 + hour * 3600
                    computed = sky.sun_altaz(ts, lat, lon)[0]
                    reference = math.degrees(ephem.Sun(observer(lat, lon, ts)).alt)
                    worst = max(worst, abs(computed - reference))
        self.assertLess(worst, 0.02, "worst sun altitude deviation %.4f deg" % worst)

    def test_moon_altitude_within_0_6_deg(self):
        worst = 0.0
        for lat, lon in SITES:
            for day in range(0, 365, 7):
                for hour in (0, 5, 11, 17, 21):
                    ts = YEAR_START + day * 86400 + hour * 3600
                    computed = sky.moon_altaz(ts, lat, lon)[0]
                    reference = math.degrees(ephem.Moon(observer(lat, lon, ts)).alt)
                    worst = max(worst, abs(computed - reference))
        self.assertLess(worst, 0.6, "worst moon altitude deviation %.4f deg" % worst)

    def test_illumination_within_half_a_percent(self):
        worst = 0.0
        for day in range(0, 365, 3):
            ts = YEAR_START + day * 86400
            computed = sky.moon_illumination(ts)
            reference = ephem.Moon(observer(*BERLIN, ts)).phase / 100.0
            worst = max(worst, abs(computed - reference))
        self.assertLess(worst, 0.005, "worst illumination deviation %.4f" % worst)

    def test_sunset_within_10_seconds(self):
        worst = 0.0
        for lat, lon in (BERLIN, WESTHAVELLAND):
            for day in (0, 60, 120, 240, 300):
                ts = YEAR_START + day * 86400 + 12 * 3600
                obs = observer(lat, lon, ts)
                obs.horizon = "-0:50"  # matches sky.SUNRISE_ALT
                reference = to_unix(obs.next_setting(ephem.Sun(), use_center=True))
                computed = sky.night(ts, lat, lon)["sunset"]
                worst = max(worst, abs(computed - reference))
        self.assertLess(worst, 10, "worst sunset deviation %.1f s" % worst)

    def test_astronomical_dusk_within_10_seconds(self):
        worst = 0.0
        for lat, lon in (BERLIN, WESTHAVELLAND):
            for day in (0, 60, 120, 240, 300):
                ts = YEAR_START + day * 86400 + 12 * 3600
                obs = observer(lat, lon, ts)
                obs.horizon = "-18"
                reference = to_unix(obs.next_setting(ephem.Sun(), use_center=True))
                computed = sky.night(ts, lat, lon)["dusk_astronomical"]
                worst = max(worst, abs(computed - reference))
        self.assertLess(worst, 10, "worst dusk deviation %.1f s" % worst)

    def test_moonrise_within_5_minutes(self):
        worst = 0.0
        for day in (3, 10, 17, 24, 31):
            ts = YEAR_START + day * 86400 + 12 * 3600
            obs = observer(*BERLIN, ts)
            obs.horizon = "0"
            reference = to_unix(obs.next_rising(ephem.Moon(), use_center=True))
            computed = sky.moon_events(ts, ts + 86400, *BERLIN)["rise"]
            worst = max(worst, abs(computed - reference))
        self.assertLess(worst, 300, "worst moonrise deviation %.1f s" % worst)


class TestInvariants(unittest.TestCase):
    """Properties that must hold with or without a reference ephemeris."""

    def test_night_is_ordered(self):
        for day in range(0, 365, 11):
            ts = YEAR_START + day * 86400 + 12 * 3600
            night = sky.night(ts, *BERLIN)
            self.assertIsNotNone(night["sunset"])
            self.assertIsNotNone(night["sunrise"])
            self.assertLess(night["sunset"], night["sunrise"])
            if night["dusk_astronomical"] and night["dawn_astronomical"]:
                self.assertLess(night["sunset"], night["dusk_astronomical"])
                self.assertLess(night["dusk_astronomical"], night["dawn_astronomical"])
                self.assertLess(night["dawn_astronomical"], night["sunrise"])

    def test_no_astronomical_night_at_midsummer_in_berlin(self):
        """The one case a beacon must not invent a number for."""
        midsummer = YEAR_START + 172 * 86400 + 12 * 3600  # 2026-06-22
        night = sky.night(midsummer, *BERLIN)
        self.assertIsNone(night["dusk_astronomical"])
        self.assertIsNone(night["dawn_astronomical"])
        self.assertEqual(night["dark_seconds"], 0)
        # Nautical twilight still exists, which is what the verdict falls back to.
        self.assertIsNotNone(night["dusk_nautical"])

    def test_dark_seconds_matches_the_boundaries(self):
        ts = YEAR_START + 300 * 86400 + 12 * 3600
        night = sky.night(ts, *BERLIN)
        self.assertEqual(
            night["dark_seconds"],
            night["dawn_astronomical"] - night["dusk_astronomical"],
        )

    def test_illumination_stays_in_range(self):
        for day in range(0, 60):
            value = sky.moon_illumination(YEAR_START + day * 86400)
            self.assertGreaterEqual(value, 0.0)
            self.assertLessEqual(value, 1.0)

    def test_phase_name_agrees_with_illumination(self):
        """A 'new' moon that is 90 % lit means the age and the geometry disagree."""
        for day in range(0, 120):
            ts = YEAR_START + day * 86400
            name = sky.moon_phase_name(ts)
            lit = sky.moon_illumination(ts)
            if name == "new":
                self.assertLess(lit, 0.10, "'new' at %.2f lit" % lit)
            elif name == "full":
                self.assertGreater(lit, 0.90, "'full' at %.2f lit" % lit)
            elif name in ("first quarter", "last quarter"):
                # The eight names are bins 3.69 days wide, so a quarter spans
                # 1.85 days either side of the exact instant — which is 22.6
                # degrees of phase angle, or 0.28 to 0.72 illuminated. Anything
                # outside that means the age and the geometry have drifted
                # apart, which is the actual failure worth catching.
                self.assertTrue(0.27 < lit < 0.73, "'%s' at %.2f lit" % (name, lit))

    def test_synodic_cycle_returns_to_new(self):
        start = YEAR_START
        later = start + int(sky.SYNODIC_MONTH * 86400)
        self.assertAlmostEqual(
            sky.moon_age_days(start), sky.moon_age_days(later), places=2
        )

    def test_crossings_finds_nothing_when_never_crossed(self):
        """Polar day: the Sun never reaches -18 deg, so there is no dusk."""
        ts = YEAR_START + 172 * 86400
        events = sky.crossings(
            lambda t: sky.sun_altaz(t, 78.2, 15.6)[0],  # Svalbard
            ts,
            ts + 86400,
            sky.ASTRONOMICAL_ALT,
        )
        self.assertEqual(events, [])

    def test_epoch_split_is_exact(self):
        """The split must lose nothing; it is what makes float32 survivable."""
        for ts in (946728000, 1767225600, 1786906800, 2000000000):
            days, fraction = sky.epoch_split(ts)
            self.assertEqual(days * 86400 + round(fraction * 86400), ts - sky.J2000_UNIX)
            self.assertGreaterEqual(fraction, 0.0)
            self.assertLess(fraction, 1.0)

    def test_angle_reduction_matches_naive_double_precision(self):
        """`_angle` must agree with the obvious formula where doubles suffice."""
        days, fraction = sky.epoch_split(1786906800)
        for constant, rate in (
            (280.46061837, sky._GMST_RATE),
            (218.3164477, sky._MOON_MEAN_LON_RATE),
            (357.528, sky._SUN_MEAN_ANOM_RATE),
        ):
            whole, remainder = rate
            naive = (constant + (whole + remainder) * (days + fraction)) % 360.0
            self.assertAlmostEqual(sky._angle(constant, rate, days, fraction), naive, places=4)


if __name__ == "__main__":
    unittest.main()
