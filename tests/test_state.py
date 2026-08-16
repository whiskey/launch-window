"""The assembled document, checked against the schema it promises to satisfy.

`protocol/beacon-v1.schema.json` is the contract. These tests validate real
documents against that file rather than against a copy of its expectations, so
a field renamed in one place and not the other fails here instead of at a
client six months later.

The scenarios are the ones where a status document is most tempted to lie: no
forecast at all, a forecast from before a power cut, and a clock that has never
been set.
"""

import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "firmware", "lib"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import schema_check  # noqa: E402
import state as state_mod  # noqa: E402
import store  # noqa: E402
import verdict  # noqa: E402

with open(os.path.join(ROOT, "protocol", "beacon-v1.schema.json")) as handle:
    SCHEMA = json.load(handle)

NOW = 1786917600  # 2026-08-16 22:00 UTC, inside the night
UNSET_CLOCK = 1609459200  # what the board believes at power-up

CONFIG = {
    "hostname": "launch-window",
    "site": {
        "name": "Garden",
        "latitude": 52.52,
        "longitude": 13.40,
        "timezone": {
            "name": "Europe/Berlin",
            "std_offset_min": 60,
            "dst": "eu",
            "abbrev": ["CET", "CEST"],
        },
    },
}


class FakeWifi:
    def __init__(self, connected=True):
        self._connected = connected

    def connected(self):
        return self._connected

    def rssi(self):
        return -47

    def address(self):
        return "10.1.10.84"


def clear_night(start_ts, count=8, **overrides):
    rows = []
    for index in range(count):
        row = {
            "ts": start_ts + index * 3600,
            "cloud_cover": 0,
            "cloud_cover_low": 0,
            "cloud_cover_mid": 0,
            "cloud_cover_high": 0,
            "temperature_2m": 15.0,
            "dew_point_2m": 4.0,
            "wind_gusts_10m": 7.0,
            "precipitation_probability": 0,
        }
        row.update(overrides)
        rows.append(row)
    return rows


class BeaconTestCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.original_cache = state_mod.CACHE_PATH
        state_mod.CACHE_PATH = os.path.join(self.temp.name, "cache.json")
        self.addCleanup(setattr, state_mod, "CACHE_PATH", self.original_cache)

    def beacon(self, hours=None, fetched_at=None, wifi=None, boot_ts=None):
        instance = state_mod.Beacon(
            CONFIG, wifi=wifi or FakeWifi(), boot_ts=NOW - 3600 if boot_ts is None else boot_ts
        )
        if hours is not None:
            instance.hours = hours
            instance.fetched_at = fetched_at if fetched_at is not None else NOW - 600
        return instance

    def assertValid(self, document):
        errors = schema_check.validate(document, SCHEMA)
        self.assertEqual(errors, [], "schema violations:\n  " + "\n  ".join(errors))


class TestDocumentShape(BeaconTestCase):
    def test_clear_night_validates_and_is_a_go(self):
        beacon = self.beacon(clear_night(NOW - 3600))
        document = beacon.document(NOW)
        self.assertValid(document)
        self.assertEqual(document["verdict"]["state"], "go")
        self.assertIsNotNone(document["verdict"]["window"])

    def test_overcast_night_validates_and_is_a_no_go(self):
        beacon = self.beacon(clear_night(NOW - 3600, cloud_cover=100))
        document = beacon.document(NOW)
        self.assertValid(document)
        self.assertEqual(document["verdict"]["state"], "no-go")
        self.assertIsNone(document["verdict"]["window"])

    def test_no_forecast_validates_and_is_unknown(self):
        document = self.beacon().document(NOW)
        self.assertValid(document)
        self.assertEqual(document["verdict"]["state"], "unknown")
        self.assertTrue(document["data"]["stale"])
        self.assertIsNone(document["data"]["fetched_at"])

    def test_document_is_json_serialisable(self):
        """It is serialised on a board with no room to discover this at runtime."""
        document = self.beacon(clear_night(NOW - 3600)).document(NOW)
        self.assertIsInstance(json.dumps(document), str)

    def test_local_times_accompany_every_utc_time(self):
        document = self.beacon(clear_night(NOW - 3600)).document(NOW)
        night = document["night"]
        self.assertTrue(night["sunset"].endswith("Z"))
        self.assertRegex(night["sunset_local"], r"^\d\d:\d\d$")
        for hour in document["verdict"]["hours"]:
            self.assertRegex(hour["local"], r"^\d\d:\d\d$")


class TestHonesty(BeaconTestCase):
    def test_missing_forecast_is_unknown_not_no_go(self):
        """The difference between 'the sky is bad' and 'I do not know'."""
        document = self.beacon().document(NOW)
        self.assertEqual(document["verdict"]["state"], verdict.STATE_UNKNOWN)
        self.assertNotEqual(document["verdict"]["state"], verdict.STATE_NO_GO)

    def test_old_forecast_is_marked_stale(self):
        beacon = self.beacon(clear_night(NOW - 3600), fetched_at=NOW - 3 * 3600)
        document = beacon.document(NOW)
        self.assertTrue(document["data"]["stale"])
        self.assertEqual(document["data"]["age_s"], 3 * 3600)
        self.assertEqual(document["data"]["age"], "3 h 00 min")

    def test_fresh_forecast_is_not_stale(self):
        document = self.beacon(clear_night(NOW - 3600), fetched_at=NOW - 300).document(NOW)
        self.assertFalse(document["data"]["stale"])

    def test_unsynced_clock_refuses_to_date_the_document(self):
        beacon = self.beacon(clear_night(NOW - 3600))
        document = beacon.document(UNSET_CLOCK)
        # NTP moving the clock must not publish a negative uptime.
        self.assertIsNone(document["beacon"]["uptime_s"])
        self.assertFalse(document["clock"]["synced"])
        self.assertIsNone(document["generated_at"])
        self.assertValid(document)

    def test_fetch_error_is_reported_not_swallowed(self):
        beacon = self.beacon()
        beacon.last_error = "request failed: -2"
        document = beacon.document(NOW)
        self.assertEqual(document["data"]["error"], "request failed: -2")
        self.assertIn("request failed", " ".join(document["verdict"]["reasons"]))

    def test_darkness_agrees_whether_or_not_a_forecast_exists(self):
        """Two code paths compute this; they disagreed once, visibly."""
        winter = 1798761600 + 22 * 3600  # 2027-01-01 22:00 UTC
        with_forecast = self.beacon(clear_night(winter), boot_ts=winter - 3600)
        without = self.beacon(boot_ts=winter - 3600)
        self.assertEqual(
            with_forecast.document(winter)["night"]["darkness"],
            without.document(winter)["night"]["darkness"],
        )
        self.assertEqual(without.document(winter)["night"]["darkness"], "astronomical")
        self.assertGreater(without.document(winter)["night"]["dark_seconds"], 0)

    def test_midsummer_reports_no_astronomical_night(self):
        """The beacon must not invent a darkness that does not exist."""
        midsummer = 1782518400 + 12 * 3600  # 2026-06-27 12:00 UTC
        beacon = self.beacon(clear_night(midsummer + 4 * 3600), boot_ts=midsummer - 3600)
        document = beacon.document(midsummer)
        self.assertValid(document)
        self.assertIsNone(document["night"]["dusk_astronomical"])
        self.assertEqual(document["night"]["dark_seconds"], 0)
        self.assertEqual(document["night"]["darkness"], "nautical")


class TestFlashCache(BeaconTestCase):
    def test_forecast_survives_a_reboot_and_says_where_it_came_from(self):
        store.save(state_mod.CACHE_PATH, {"hours": clear_night(NOW - 3600), "fetched_at": NOW - 1800})
        beacon = state_mod.Beacon(CONFIG, wifi=FakeWifi(), boot_ts=NOW)
        document = beacon.document(NOW)
        self.assertEqual(document["verdict"]["state"], "go")
        self.assertTrue(document["data"]["from_flash_cache"])
        self.assertEqual(document["data"]["age_s"], 1800)

    def test_absent_cache_is_not_an_error(self):
        beacon = state_mod.Beacon(CONFIG, wifi=FakeWifi(), boot_ts=NOW)
        self.assertIsNone(beacon.hours)

    def test_corrupt_cache_is_ignored(self):
        with open(state_mod.CACHE_PATH, "w") as handle:
            handle.write("{ this is not json")
        beacon = state_mod.Beacon(CONFIG, wifi=FakeWifi(), boot_ts=NOW)
        self.assertIsNone(beacon.hours)


class TestSignalling(BeaconTestCase):
    def test_led_follows_the_verdict(self):
        self.assertEqual(self.beacon(clear_night(NOW - 3600)).led_pattern(NOW), "go")
        self.assertEqual(
            self.beacon(clear_night(NOW - 3600, cloud_cover=100)).led_pattern(NOW), "no-go"
        )

    def test_disconnected_beacon_signals_connecting(self):
        beacon = self.beacon(clear_night(NOW - 3600), wifi=FakeWifi(connected=False))
        self.assertEqual(beacon.led_pattern(NOW), "connecting")

    def test_unsynced_clock_signals_unknown(self):
        beacon = self.beacon(clear_night(NOW - 3600))
        self.assertEqual(beacon.led_pattern(UNSET_CLOCK), "unknown")

    def test_every_pattern_the_state_can_ask_for_exists(self):
        import led as led_mod

        for pattern in ("go", "marginal", "no-go", "unknown", "connecting", "setup", "fault"):
            self.assertIn(pattern, led_mod.PATTERNS)

    def test_night_dimming_follows_the_sun(self):
        beacon = self.beacon()
        self.assertTrue(beacon.is_night(NOW))  # 22:00 UTC in August
        self.assertFalse(beacon.is_night(NOW - 10 * 3600))  # noon
        self.assertFalse(beacon.is_night(UNSET_CLOCK))  # unknown clock: no guess


if __name__ == "__main__":
    unittest.main()
