"""The grading rules, and the decisions they add up to.

These are the tests that encode the domain judgement, so they are written as
statements about nights rather than about functions: a clear moonless night is
a GO, an overcast one is a NO-GO, and four clear hours after a cloudy evening
beat eight mediocre ones. If a weight is ever retuned, the ones that should
break are the borderline cases at the bottom.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "firmware", "lib"))

import verdict  # noqa: E402

DUSK = 1786910400  # 2026-08-16 20:00 UTC
DAWN = DUSK + 8 * 3600

NIGHT = {
    "dusk_astronomical": DUSK,
    "dawn_astronomical": DAWN,
    "dusk_nautical": DUSK - 3600,
    "dawn_nautical": DAWN + 3600,
    "dark_seconds": 8 * 3600,
}

NO_MOON = lambda ts: (-30.0, 0.0)  # noqa: E731
FULL_MOON_HIGH = lambda ts: (55.0, 1.0)  # noqa: E731


def hour(index, **overrides):
    """One forecast hour, clear and calm unless told otherwise."""
    row = {
        "ts": DUSK + index * 3600,
        "cloud_cover": 0,
        "cloud_cover_low": 0,
        "cloud_cover_mid": 0,
        "cloud_cover_high": 0,
        "temperature_2m": 15.0,
        "dew_point_2m": 5.0,
        "wind_gusts_10m": 8.0,
        "precipitation_probability": 0,
    }
    row.update(overrides)
    return row


def night_of(*rows):
    return list(rows)


class TestHourGrading(unittest.TestCase):
    def test_perfect_hour_scores_full_marks(self):
        graded = verdict.grade_hour(hour(0), -30.0, 0.0)
        self.assertEqual(graded["score"], 100.0)
        self.assertIsNone(graded["veto"])

    def test_cloud_cover_dominates(self):
        clear = verdict.grade_hour(hour(0, cloud_cover=0), -30.0, 0.0)["score"]
        half = verdict.grade_hour(hour(0, cloud_cover=50), -30.0, 0.0)["score"]
        self.assertLess(half, clear)
        self.assertAlmostEqual(half, 60.0, places=1)

    def test_high_cloud_costs_more_than_its_share(self):
        """Cirrus looks like a clear sky and ruins the guiding anyway."""
        low = verdict.grade_hour(
            hour(0, cloud_cover=40, cloud_cover_low=40), -30.0, 0.0
        )["score"]
        high = verdict.grade_hour(
            hour(0, cloud_cover=40, cloud_cover_high=40), -30.0, 0.0
        )["score"]
        self.assertLess(high, low)

    def test_overcast_is_a_veto(self):
        graded = verdict.grade_hour(hour(0, cloud_cover=95), -30.0, 0.0)
        self.assertEqual(graded["score"], 0.0)
        self.assertIn("overcast", graded["veto"])

    def test_rain_is_a_veto_even_under_a_clear_sky(self):
        graded = verdict.grade_hour(
            hour(0, cloud_cover=10, precipitation_probability=60), -30.0, 0.0
        )
        self.assertEqual(graded["score"], 0.0)
        self.assertIn("rain", graded["veto"])

    def test_gusts_are_a_veto_at_40_kmh(self):
        below = verdict.grade_hour(hour(0, wind_gusts_10m=39), -30.0, 0.0)
        at = verdict.grade_hour(hour(0, wind_gusts_10m=40), -30.0, 0.0)
        self.assertIsNone(below["veto"])
        self.assertIsNotNone(at["veto"])
        self.assertEqual(at["score"], 0.0)

    def test_light_wind_costs_nothing(self):
        self.assertNotIn("wind", verdict.grade_hour(hour(0, wind_gusts_10m=15), -30.0, 0.0)["penalties"])

    def test_dew_point_spread_is_penalised_but_never_vetoes(self):
        """Dew is answered with a heater, not by staying indoors."""
        damp = verdict.grade_hour(
            hour(0, temperature_2m=10.0, dew_point_2m=9.5), -30.0, 0.0
        )
        self.assertIn("dew", damp["penalties"])
        self.assertIsNone(damp["veto"])
        self.assertGreater(damp["score"], 0)

    def test_dry_air_gets_no_dew_penalty(self):
        dry = verdict.grade_hour(
            hour(0, temperature_2m=15.0, dew_point_2m=2.0), -30.0, 0.0
        )
        self.assertNotIn("dew", dry["penalties"])

    def test_moon_below_the_horizon_costs_nothing(self):
        down = verdict.grade_hour(hour(0), -5.0, 1.0)
        self.assertNotIn("moon", down["penalties"])
        self.assertEqual(down["score"], 100.0)

    def test_moon_penalty_scales_with_brightness_and_altitude(self):
        crescent = verdict.grade_hour(hour(0), 40.0, 0.15)["score"]
        gibbous = verdict.grade_hour(hour(0), 40.0, 0.85)["score"]
        low_full = verdict.grade_hour(hour(0), 5.0, 1.0)["score"]
        high_full = verdict.grade_hour(hour(0), 70.0, 1.0)["score"]
        self.assertGreater(crescent, gibbous)
        self.assertGreater(low_full, high_full)

    def test_missing_cloud_data_is_not_a_clear_sky(self):
        graded = verdict.grade_hour(hour(0, cloud_cover=None), -30.0, 0.0)
        self.assertIsNone(graded["score"])
        self.assertEqual(graded["veto"], "no data")

    def test_raw_values_travel_with_the_grade(self):
        graded = verdict.grade_hour(hour(0, cloud_cover=42, wind_gusts_10m=17), -30.0, 0.0)
        self.assertEqual(graded["cloud_cover"], 42)
        self.assertEqual(graded["wind_gusts_10m"], 17)


class TestNightAssessment(unittest.TestCase):
    def assess(self, rows, moon=NO_MOON):
        return verdict.assess(rows, NIGHT, moon)

    def test_clear_moonless_night_is_a_go(self):
        result = self.assess([hour(i) for i in range(8)])
        self.assertEqual(result["state"], verdict.STATE_GO)
        self.assertEqual(result["window"]["hours"], 8.0)
        self.assertEqual(result["darkness"], "astronomical")

    def test_overcast_night_is_a_no_go(self):
        result = self.assess([hour(i, cloud_cover=100) for i in range(8)])
        self.assertEqual(result["state"], verdict.STATE_NO_GO)
        self.assertIsNone(result["window"])

    def test_a_clear_run_beats_a_mediocre_average(self):
        """Four clear hours after a cloudy evening is a session."""
        rows = [hour(i, cloud_cover=100) for i in range(4)] + [hour(i) for i in range(4, 8)]
        result = self.assess(rows)
        self.assertEqual(result["state"], verdict.STATE_GO)
        self.assertEqual(result["window"]["hours"], 4.0)
        self.assertEqual(result["window"]["start"], DUSK + 4 * 3600)

    def test_flat_mediocre_night_is_not_a_go(self):
        rows = [hour(i, cloud_cover=55) for i in range(8)]
        result = self.assess(rows)
        self.assertNotEqual(result["state"], verdict.STATE_GO)

    def test_single_usable_hour_is_marginal(self):
        rows = [hour(i, cloud_cover=100) for i in range(8)]
        rows[3] = hour(3)
        result = self.assess(rows)
        self.assertEqual(result["state"], verdict.STATE_MARGINAL)
        self.assertEqual(result["window"]["hours"], 1.0)

    def test_full_moon_all_night_spoils_a_cloudless_sky(self):
        result = self.assess([hour(i) for i in range(8)], moon=FULL_MOON_HIGH)
        self.assertNotEqual(result["state"], verdict.STATE_GO)
        self.assertTrue(any("moon" in reason for reason in result["reasons"]))

    def test_hours_outside_darkness_are_ignored(self):
        """A brilliant hour at sunset is not observing time."""
        rows = [hour(-3), hour(-2), hour(-1)] + [
            hour(i, cloud_cover=100) for i in range(8)
        ]
        result = self.assess(rows)
        self.assertEqual(result["state"], verdict.STATE_NO_GO)
        self.assertEqual(len(result["hours"]), 8)

    def test_window_is_clipped_to_darkness(self):
        """A run that starts before dusk may not promise pre-dusk imaging."""
        rows = [hour(-1)] + [hour(i) for i in range(8)]
        result = self.assess(rows)
        self.assertEqual(result["window"]["start"], DUSK)
        self.assertLessEqual(result["window"]["end"], DAWN)

    def test_no_forecast_is_unknown_not_no_go(self):
        result = self.assess([])
        self.assertEqual(result["state"], verdict.STATE_UNKNOWN)

    def test_all_hours_missing_data_is_unknown_shaped(self):
        rows = [hour(i, cloud_cover=None) for i in range(8)]
        result = self.assess(rows)
        self.assertEqual(result["state"], verdict.STATE_NO_GO)
        self.assertIsNone(result["window"])
        self.assertIsNone(result["score"])

    def test_falls_back_to_nautical_night_at_midsummer(self):
        summer_night = dict(NIGHT)
        summer_night["dusk_astronomical"] = None
        summer_night["dawn_astronomical"] = None
        result = verdict.assess([hour(i) for i in range(8)], summer_night, NO_MOON)
        self.assertEqual(result["darkness"], "nautical")
        self.assertEqual(result["state"], verdict.STATE_GO)

    def test_no_night_at_all_is_unknown(self):
        polar = {"dusk_astronomical": None, "dawn_astronomical": None,
                 "dusk_nautical": None, "dawn_nautical": None}
        result = verdict.assess([hour(i) for i in range(8)], polar, NO_MOON)
        self.assertEqual(result["state"], verdict.STATE_UNKNOWN)


class TestReasons(unittest.TestCase):
    def test_reasons_name_the_limiting_factor(self):
        rows = [hour(i, cloud_cover=100) for i in range(8)]
        reasons = verdict.assess(rows, NIGHT, NO_MOON)["reasons"]
        joined = " ".join(reasons)
        self.assertIn("overcast", joined)
        self.assertIn("cloud cover averaging 100", joined)

    def test_cloud_average_is_the_forecast_not_the_penalty(self):
        rows = [hour(i, cloud_cover=60, cloud_cover_high=60) for i in range(8)]
        reasons = verdict.assess(rows, NIGHT, NO_MOON)["reasons"]
        self.assertIn("cloud cover averaging 60 %", " ".join(reasons))

    def test_rejected_stretch_is_explained(self):
        rows = [hour(i, cloud_cover=100) for i in range(8)]
        rows[3] = hour(3)
        thresholds = {"marginal_hours": 2.0}
        result = verdict.assess(rows, NIGHT, NO_MOON, thresholds)
        self.assertEqual(result["state"], verdict.STATE_NO_GO)
        self.assertIn("best stretch is 1.0 h", " ".join(result["reasons"]))

    def test_go_reason_quotes_the_window(self):
        result = verdict.assess([hour(i) for i in range(8)], NIGHT, NO_MOON)
        self.assertIn("8.0 h of usable dark sky", " ".join(result["reasons"]))


class TestThresholds(unittest.TestCase):
    def test_usable_score_decides_which_hours_count(self):
        rows = [hour(i, cloud_cover=50) for i in range(8)]  # every hour scores 60
        strict = verdict.assess(rows, NIGHT, NO_MOON, {"usable_score": 80})
        lenient = verdict.assess(rows, NIGHT, NO_MOON, {"usable_score": 40})
        self.assertEqual(strict["state"], verdict.STATE_NO_GO)
        # Usable, but a whole night at 60 still is not worth calling a GO —
        # that takes clearing `go_score` as well, which is the point of having
        # both thresholds.
        self.assertEqual(lenient["state"], verdict.STATE_MARGINAL)

    def test_go_score_is_the_second_gate(self):
        rows = [hour(i, cloud_cover=50) for i in range(8)]
        result = verdict.assess(
            rows, NIGHT, NO_MOON, {"usable_score": 40, "go_score": 55}
        )
        self.assertEqual(result["state"], verdict.STATE_GO)

    def test_defaults_are_not_mutated_by_an_override(self):
        verdict.assess([hour(0)], NIGHT, NO_MOON, {"usable_score": 99})
        self.assertEqual(verdict.THRESHOLDS["usable_score"], 55)


if __name__ == "__main__":
    unittest.main()
