"""The status page: that it renders, escapes, and never shows a raw None.

`None` leaking into HTML is the characteristic failure of a page built from a
document full of honest nulls. It reads as a bug to anyone who sees it and it
hides the thing the null was trying to say, so it gets its own test.
"""

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "firmware", "lib"))

import page  # noqa: E402


def document(**overrides):
    base = {
        "generated_at": "2026-08-16T20:11:04Z",
        "generated_local": "22:11",
        "beacon": {"host": "launch-window", "uptime": "12 h 33 min"},
        "clock": {"synced": True},
        "site": {"name": "Garden"},
        "night": {
            "sunset_local": "20:29",
            "dusk_astronomical_local": "22:57",
            "dawn_astronomical_local": "03:24",
            "sunrise_local": "05:52",
            "dark_duration": "4 h 25 min",
        },
        "moon": {
            "illumination": 0.196,
            "phase": "waxing crescent",
            "rise_local": "12:02",
            "set_local": "21:34",
            "interferes": False,
        },
        "verdict": {
            "state": "go",
            "score": 88.0,
            "reasons": ["4.4 h of usable dark sky, mean score 88"],
            "window": {
                "start_local": "22:57",
                "end_local": "03:24",
                "hours": 4.4,
                "mean_score": 88.0,
            },
            "hours": [
                {
                    "local": "23:00",
                    "score": 88.0,
                    "veto": None,
                    "cloud_cover": 10,
                    "wind_gusts_10m": 8,
                    "temperature_2m": 15.0,
                    "dew_point_2m": 4.0,
                    "moon_alt_deg": -14.6,
                }
            ],
        },
        "data": {"age": "10 min", "stale": False},
    }
    base.update(overrides)
    return base


def render(doc, theme="night"):
    return "".join(page.render(doc, theme))


class TestRendering(unittest.TestCase):
    def test_headline_carries_the_verdict(self):
        html = render(document())
        self.assertIn("GO", html)
        self.assertIn("4.4 h of usable dark sky", html)

    def test_window_is_shown_when_there_is_one(self):
        html = render(document())
        self.assertIn("22:57", html)
        self.assertIn("03:24", html)

    def test_no_go_renders_without_a_window(self):
        doc = document()
        doc["verdict"] = dict(doc["verdict"], state="no-go", window=None,
                              reasons=["cloud cover averaging 88 %"])
        html = render(doc)
        self.assertIn("NO-GO", html)
        self.assertIn("cloud cover averaging 88 %", html)

    def test_never_prints_a_bare_none(self):
        """Honest nulls must reach the page as em dashes, not as 'None'."""
        doc = document()
        doc["night"] = {key: None for key in doc["night"]}
        doc["moon"] = dict(doc["moon"], rise_local=None, set_local=None)
        doc["verdict"] = dict(
            doc["verdict"],
            state="unknown",
            score=None,
            window=None,
            hours=[{"local": "23:00", "score": None, "veto": "no data",
                    "cloud_cover": None, "wind_gusts_10m": None,
                    "temperature_2m": None, "dew_point_2m": None,
                    "moon_alt_deg": None}],
        )
        doc["data"] = {"age": None, "stale": True}
        html = render(doc)
        self.assertNotIn("None", html)
        self.assertIn("—", html)

    def test_stale_data_is_called_out_above_the_verdict(self):
        doc = document()
        doc["data"] = {"age": "5 h 00 min", "stale": True}
        html = render(doc)
        self.assertIn("stale", html)
        self.assertIn("5 h 00 min old", html)
        # Above the verdict element itself, not merely above its CSS rule.
        self.assertLess(html.index("still exact"), html.index('<div class="verdict"'))

    def test_unsynced_clock_is_called_out(self):
        doc = document()
        doc["clock"] = {"synced": False}
        self.assertIn("never synchronised", render(doc))

    def test_reasons_are_escaped(self):
        doc = document()
        doc["verdict"] = dict(doc["verdict"], reasons=["<script>alert(1)</script>"])
        html = render(doc)
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_hour_table_shows_the_drivers(self):
        html = render(document())
        self.assertIn("Cloud", html)
        self.assertIn("Gust", html)
        self.assertIn("Spread", html)
        self.assertIn("11.0 K", html)  # 15.0 - 4.0

    def test_vetoed_hours_are_marked(self):
        doc = document()
        doc["verdict"]["hours"][0] = dict(doc["verdict"]["hours"][0], veto="overcast (100 %)", score=0.0)
        self.assertIn('class="veto"', render(doc))

    def test_page_is_self_contained(self):
        """A strict offline device cannot fetch a stylesheet from anywhere."""
        html = render(document())
        self.assertNotIn("http://", html.replace('http-equiv', ''))
        self.assertNotIn("https://", html)
        self.assertNotIn("<script", html)

    def test_themes_differ_and_both_render(self):
        night = render(document(), "night")
        day = render(document(), "day")
        self.assertIn('class="night"', night)
        self.assertIn('class="day"', day)
        self.assertIn("?theme=day", night)
        self.assertIn("?theme=night", day)

    def test_html_is_balanced_enough_to_close(self):
        html = render(document())
        self.assertTrue(html.startswith("<!doctype html>"))
        self.assertTrue(html.rstrip().endswith("</html>"))
        self.assertEqual(html.count("<table>"), html.count("</table>"))


if __name__ == "__main__":
    unittest.main()
