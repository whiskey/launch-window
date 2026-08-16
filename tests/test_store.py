"""Config and credential files: defaults, merging, and surviving a power cut."""

import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "firmware", "lib"))

import store  # noqa: E402

DEFAULTS = {
    "hostname": "launch-window",
    "refresh_minutes": 30,
    "site": {"name": "Garden", "latitude": 52.52, "longitude": 13.40},
    "thresholds": {"usable_score": 55, "go_hours": 2.0},
}


class TestLoadSave(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = os.path.join(self.temp.name, "config.json")

    def test_round_trip(self):
        self.assertTrue(store.save(self.path, {"a": 1, "b": [1, 2]}))
        self.assertEqual(store.load(self.path), {"a": 1, "b": [1, 2]})

    def test_missing_file_returns_the_default(self):
        self.assertIsNone(store.load(os.path.join(self.temp.name, "absent.json")))
        self.assertEqual(store.load("/nowhere/at/all.json", {"x": 1}), {"x": 1})

    def test_corrupt_file_returns_the_default_rather_than_raising(self):
        """A half-written file must not stop the beacon from booting."""
        with open(self.path, "w") as handle:
            handle.write('{"truncated": ')
        self.assertEqual(store.load(self.path, {"fallback": True}), {"fallback": True})

    def test_overwriting_replaces_completely(self):
        store.save(self.path, {"old": "value", "extra": 1})
        store.save(self.path, {"new": "value"})
        self.assertEqual(store.load(self.path), {"new": "value"})

    def test_no_temporary_file_is_left_behind(self):
        store.save(self.path, {"a": 1})
        self.assertFalse(os.path.exists(self.path + ".tmp"))

    def test_unwritable_path_reports_failure_instead_of_raising(self):
        self.assertFalse(store.save("/proc/nowhere/config.json", {"a": 1}))

    def test_saved_file_is_valid_json_on_disk(self):
        store.save(self.path, {"site": {"latitude": 52.52}})
        with open(self.path) as handle:
            self.assertEqual(json.load(handle), {"site": {"latitude": 52.52}})


class TestMerge(unittest.TestCase):
    def test_none_yields_the_defaults(self):
        self.assertEqual(store.merged(DEFAULTS, None), DEFAULTS)

    def test_top_level_override(self):
        merged = store.merged(DEFAULTS, {"refresh_minutes": 10})
        self.assertEqual(merged["refresh_minutes"], 10)
        self.assertEqual(merged["hostname"], "launch-window")

    def test_partial_nested_override_keeps_the_other_keys(self):
        """Setting one threshold must not silently drop the rest."""
        merged = store.merged(DEFAULTS, {"thresholds": {"usable_score": 70}})
        self.assertEqual(merged["thresholds"], {"usable_score": 70, "go_hours": 2.0})

    def test_defaults_are_not_mutated(self):
        store.merged(DEFAULTS, {"thresholds": {"usable_score": 99}, "hostname": "other"})
        self.assertEqual(DEFAULTS["thresholds"]["usable_score"], 55)
        self.assertEqual(DEFAULTS["hostname"], "launch-window")

    def test_unknown_keys_are_kept(self):
        """A newer config on an older firmware should not lose its settings."""
        merged = store.merged(DEFAULTS, {"future_option": True})
        self.assertTrue(merged["future_option"])

    def test_a_non_dict_override_replaces_a_dict(self):
        merged = store.merged(DEFAULTS, {"site": None})
        self.assertIsNone(merged["site"])


if __name__ == "__main__":
    unittest.main()
