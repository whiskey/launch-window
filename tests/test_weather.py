"""The Open-Meteo client, including the parts that only bite on real responses.

The fixture is a genuine captured response, headers and all, because the two
things that actually broke here were both invisible in a hand-written one:
Open-Meteo replies with `Transfer-Encoding: chunked` and sends no
`Content-Length`, so a reader that trusts the header reads zero bytes forever.

`test_fetch_over_a_real_socket` runs the actual async client against a local
server replaying that fixture, so the socket handling is exercised rather than
mocked away.
"""

import asyncio
import json
import os
import socket
import sys
import threading
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "firmware", "lib"))

import weather  # noqa: E402

FIXTURE = os.path.join(ROOT, "tests", "fixtures", "open-meteo-berlin-night.http")

with open(FIXTURE, "rb") as handle:
    RAW_RESPONSE = handle.read()


class TestRequestBuilding(unittest.TestCase):
    def test_path_asks_only_for_the_night(self):
        path = weather.build_path(52.52, 13.40, 1786906800, 1786932000)
        self.assertIn("latitude=52.5200", path)
        self.assertIn("longitude=13.4000", path)
        self.assertIn("start_hour=2026-08-16T19:00", path)
        self.assertIn("end_hour=2026-08-17T02:00", path)
        self.assertIn("timeformat=unixtime", path)
        self.assertIn("timezone=GMT", path)

    def test_path_requests_every_variable_the_grader_uses(self):
        path = weather.build_path(52.52, 13.40, 1786906800, 1786932000)
        for variable in weather.VARIABLES:
            self.assertIn(variable, path)

    def test_negative_longitude_survives_formatting(self):
        path = weather.build_path(64.15, -21.94, 1786906800, 1786932000)
        self.assertIn("longitude=-21.9400", path)


class TestResponseParsing(unittest.TestCase):
    def test_parses_the_real_captured_response(self):
        status, body = weather.parse_http(RAW_RESPONSE)
        self.assertEqual(status, 200)
        document = json.loads(body)
        self.assertIn("hourly", document)

    def test_dechunking_actually_happened(self):
        """The chunk-size lines must not survive into the JSON."""
        _, body = weather.parse_http(RAW_RESPONSE)
        self.assertTrue(body.strip().startswith(b"{"))
        self.assertTrue(body.strip().endswith(b"}"))

    def test_non_200_is_reported(self):
        raw = b"HTTP/1.1 429 Too Many Requests\r\nContent-Length: 0\r\n\r\n"
        status, _ = weather.parse_http(raw)
        self.assertEqual(status, 429)

    def test_garbage_raises_rather_than_returning_nonsense(self):
        with self.assertRaises(weather.WeatherError):
            weather.parse_http(b"")
        with self.assertRaises(weather.WeatherError):
            weather.parse_http(b"not http at all\r\n\r\nbody")

    def test_unchunked_body_passes_through(self):
        raw = b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n{}'
        status, body = weather.parse_http(raw)
        self.assertEqual((status, body), (200, b"{}"))


class TestHourExtraction(unittest.TestCase):
    def document(self):
        _, body = weather.parse_http(RAW_RESPONSE)
        return json.loads(body)

    def test_hours_carry_every_variable(self):
        hours = weather.to_hours(self.document())
        self.assertGreater(len(hours), 0)
        for row in hours:
            self.assertIsInstance(row["ts"], int)
            for variable in weather.VARIABLES:
                self.assertIn(variable, row)

    def test_timestamps_are_hourly_and_ascending(self):
        hours = weather.to_hours(self.document())
        for earlier, later in zip(hours, hours[1:]):
            self.assertEqual(later["ts"] - earlier["ts"], 3600)

    def test_nulls_are_preserved_not_zeroed(self):
        """A null cloud cover must never arrive as a clear sky."""
        document = {
            "hourly": {
                "time": [1786906800, 1786910400],
                "cloud_cover": [None, 40],
            }
        }
        hours = weather.to_hours(document)
        self.assertIsNone(hours[0]["cloud_cover"])
        self.assertEqual(hours[1]["cloud_cover"], 40)

    def test_short_column_is_padded_with_none(self):
        document = {"hourly": {"time": [1, 2, 3], "cloud_cover": [10]}}
        hours = weather.to_hours(document)
        self.assertEqual([row["cloud_cover"] for row in hours], [10, None, None])

    def test_empty_forecast_is_an_error(self):
        with self.assertRaises(weather.WeatherError):
            weather.to_hours({"hourly": {"time": []}})


class ReplayServer:
    """Serves fixed bytes to one client, so the async path can be exercised."""

    def __init__(self, payload):
        self.payload = payload
        self.socket = socket.socket()
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind(("127.0.0.1", 0))
        self.socket.listen(1)
        self.port = self.socket.getsockname()[1]
        self.request = b""
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self):
        try:
            connection, _ = self.socket.accept()
            with connection:
                connection.settimeout(5)
                self.request = connection.recv(4096)
                connection.sendall(self.payload)
        except Exception:
            pass
        finally:
            self.socket.close()


class TestFetch(unittest.TestCase):
    def fetch_against(self, payload):
        server = ReplayServer(payload)
        original = (weather.HOST, weather.PORT)
        weather.HOST, weather.PORT = "127.0.0.1", server.port
        try:
            return asyncio.run(
                weather.fetch(52.52, 13.40, 1786906800, 1786932000, timeout=10)
            ), server
        finally:
            weather.HOST, weather.PORT = original

    def test_fetch_over_a_real_socket(self):
        hours, server = self.fetch_against(RAW_RESPONSE)
        self.assertGreater(len(hours), 0)
        self.assertIn(b"GET /v1/forecast", server.request)
        self.assertIn(b"Connection: close", server.request)
        self.assertIn(b"Host: 127.0.0.1", server.request)

    def test_http_error_becomes_weather_error(self):
        with self.assertRaises(weather.WeatherError):
            self.fetch_against(b"HTTP/1.1 500 Server Error\r\nContent-Length: 0\r\n\r\n")

    def test_api_error_document_becomes_weather_error(self):
        body = b'{"error":true,"reason":"latitude must be in range"}'
        payload = (
            b"HTTP/1.1 200 OK\r\nContent-Length: %d\r\n\r\n" % len(body)
        ) + body
        with self.assertRaises(weather.WeatherError):
            self.fetch_against(payload)

    def test_connection_refused_becomes_weather_error(self):
        original = (weather.HOST, weather.PORT)
        weather.HOST, weather.PORT = "127.0.0.1", 1  # nothing listens on port 1
        try:
            with self.assertRaises(weather.WeatherError):
                asyncio.run(
                    weather.fetch(52.52, 13.40, 1786906800, 1786932000, timeout=5)
                )
        finally:
            weather.HOST, weather.PORT = original


if __name__ == "__main__":
    unittest.main()
