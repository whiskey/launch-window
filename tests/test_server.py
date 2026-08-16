"""The HTTP server, driven both through fake streams and over real sockets.

The fake reader and writer implement just enough of asyncio's stream interface
for `Server.handle`, which lets every route, every malformed request and every
timeout be exercised cheaply. `TestOverRealSockets` then runs the same object
behind a real listening socket, so the accept path is covered too.

What no host test can show is the radio: `tools/smoke-test.py` binds port 80 on
the board's live access point, and associating an actual client needs a second
device.
"""

import asyncio
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "firmware", "lib"))

import server as server_mod  # noqa: E402


class FakeReader:
    def __init__(self, data=b"", stall=False):
        self.data = data
        self.stall = stall

    async def readline(self):
        if self.stall:
            await asyncio.sleep(30)
        index = self.data.find(b"\r\n")
        if index < 0:
            line, self.data = self.data, b""
            return line
        line, self.data = self.data[: index + 2], self.data[index + 2 :]
        return line

    async def readexactly(self, count):
        chunk, self.data = self.data[:count], self.data[count:]
        return chunk


class FakeWriter:
    def __init__(self):
        self.sent = b""
        self.closed = False

    def write(self, data):
        self.sent += data

    async def drain(self):
        pass

    def close(self):
        self.closed = True

    async def wait_closed(self):
        pass


def request_bytes(method="GET", target="/", body=b"", headers=None):
    lines = ["%s %s HTTP/1.1" % (method, target), "Host: beacon"]
    for name, value in (headers or {}).items():
        lines.append("%s: %s" % (name, value))
    if body:
        lines.append("Content-Length: %d" % len(body))
    return ("\r\n".join(lines) + "\r\n\r\n").encode() + body


def serve(routes, raw, fallback=None):
    reader, writer = FakeReader(raw), FakeWriter()
    asyncio.run(server_mod.Server(routes, fallback).handle(reader, writer))
    return writer.sent


def split(response):
    head, _, body = response.partition(b"\r\n\r\n")
    return head.decode(), body


class TestParsing(unittest.TestCase):
    def test_unquote_plus(self):
        self.assertEqual(server_mod.unquote_plus("a+b"), "a b")
        self.assertEqual(server_mod.unquote_plus("plain"), "plain")
        self.assertEqual(server_mod.unquote_plus("100%%"), "100%%")

    def test_multibyte_characters_survive_decoding(self):
        """A password with an umlaut must arrive as the password, not as mojibake."""
        self.assertEqual(server_mod.unquote_plus("Caf%C3%A9"), "Café")
        self.assertEqual(server_mod.unquote_plus("Stra%C3%9Fe123"), "Straße123")
        self.assertEqual(server_mod.unquote_plus("W%C3%BCrfel"), "Würfel")

    def test_parse_qs(self):
        self.assertEqual(
            server_mod.parse_qs("theme=day&x=1"), {"theme": "day", "x": "1"}
        )
        self.assertEqual(server_mod.parse_qs(""), {})
        self.assertEqual(server_mod.parse_qs("flag"), {"flag": ""})

    def test_password_with_reserved_characters_round_trips(self):
        """WiFi passwords contain & and = more often than anyone would like."""
        form = server_mod.parse_qs("ssid=Home&password=a%26b%3Dc+d")
        self.assertEqual(form["password"], "a&b=c d")


class TestRouting(unittest.TestCase):
    def test_serves_a_route(self):
        routes = {"/": lambda r: (200, "text/plain", "hello")}
        head, body = split(serve(routes, request_bytes()))
        self.assertIn("200 OK", head)
        self.assertEqual(body, b"hello")

    def test_json_helper_sets_content_type(self):
        routes = {"/x": lambda r: server_mod.json_response({"ok": True})}
        head, body = split(serve(routes, request_bytes(target="/x")))
        self.assertIn("application/json", head)
        self.assertEqual(json.loads(body), {"ok": True})

    def test_unknown_path_is_404(self):
        head, _ = split(serve({}, request_bytes(target="/nope")))
        self.assertIn("404", head)

    def test_fallback_catches_everything(self):
        """Captive-portal probes ask for paths nobody registered."""
        sent = serve(
            {}, request_bytes(target="/generate_204"),
            fallback=lambda r: (200, "text/html", "setup"),
        )
        head, body = split(sent)
        self.assertIn("200 OK", head)
        self.assertEqual(body, b"setup")

    def test_query_string_reaches_the_handler(self):
        seen = {}

        def handler(request):
            seen.update(request.query)
            return 200, "text/plain", "ok"

        serve({"/": handler}, request_bytes(target="/?theme=day"))
        self.assertEqual(seen, {"theme": "day"})

    def test_iterable_body_is_streamed(self):
        routes = {"/": lambda r: (200, "text/html", (c for c in ["a", "b", "c"]))}
        _, body = split(serve(routes, request_bytes()))
        self.assertEqual(body, b"abc")

    def test_extra_headers_are_sent(self):
        routes = {"/": lambda r: server_mod.redirect("/elsewhere")}
        head, _ = split(serve(routes, request_bytes()))
        self.assertIn("303", head)
        self.assertIn("Location: /elsewhere", head)

    def test_post_body_reaches_the_handler(self):
        seen = {}

        def handler(request):
            seen.update(request.form())
            return 200, "text/plain", "ok"

        serve(
            {"/save": handler},
            request_bytes("POST", "/save", b"ssid=ExampleNet&password=secret"),
        )
        self.assertEqual(seen, {"ssid": "ExampleNet", "password": "secret"})


class TestOverRealSockets(unittest.TestCase):
    """The same Server object, driven through an actual TCP connection.

    The fake streams above exercise every branch, but they cannot show that
    `asyncio.start_server` accepts a connection and that the response reaches a
    client that speaks HTTP. On the board that last step is only partly
    provable — `tools/smoke-test.py` shows port 80 binding on the live radio,
    but a Pico W cannot open a TCP connection to its own access point, so the
    accept path is verified here instead.
    """

    def round_trip(self, routes, request):
        import socket

        async def run():
            server = await server_mod.Server(routes).serve("127.0.0.1", 0)
            port = server.sockets[0].getsockname()[1] if hasattr(server, "sockets") else None
            loop = asyncio.get_event_loop()
            sock = socket.socket()
            sock.setblocking(False)
            await loop.sock_connect(sock, ("127.0.0.1", port))
            await loop.sock_sendall(sock, request)
            received = b""
            while True:
                chunk = await loop.sock_recv(sock, 4096)
                if not chunk:
                    break
                received += chunk
            sock.close()
            server.close()
            return received

        return asyncio.run(run())

    def test_a_real_client_gets_the_page(self):
        routes = {"/": lambda r: (200, "text/html", (part for part in ["<!doctype html>", "<body>hi</body>"]))}
        response = self.round_trip(routes, b"GET / HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n")
        self.assertIn(b"200 OK", response)
        self.assertIn(b"<!doctype html>", response)
        self.assertIn(b"hi", response)

    def test_a_real_client_gets_json(self):
        routes = {"/api/v1/health": lambda r: server_mod.json_response({"ok": True, "schema": 1})}
        response = self.round_trip(
            routes, b"GET /api/v1/health HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n"
        )
        head, _, body = response.partition(b"\r\n\r\n")
        self.assertIn(b"application/json", head)
        self.assertEqual(json.loads(body), {"ok": True, "schema": 1})

    def test_a_real_post_reaches_the_handler(self):
        seen = {}

        def save(request):
            seen.update(request.form())
            return 200, "text/plain", "saved"

        body = b"ssid=ExampleNet&password=Stra%C3%9Fe+42"
        response = self.round_trip(
            {"/save": save},
            b"POST /save HTTP/1.1\r\nHost: x\r\nContent-Length: %d\r\nConnection: close\r\n\r\n%s"
            % (len(body), body),
        )
        self.assertIn(b"200 OK", response)
        self.assertEqual(seen, {"ssid": "ExampleNet", "password": "Straße 42"})


class TestRobustness(unittest.TestCase):
    def test_handler_exception_becomes_500_and_the_server_lives(self):
        def broken(request):
            raise ValueError("boom")

        head, body = split(serve({"/": broken}, request_bytes()))
        self.assertIn("500", head)
        self.assertIn(b"boom", body)

    def test_malformed_request_line_is_400(self):
        reader, writer = FakeReader(b"garbage\r\n\r\n"), FakeWriter()
        asyncio.run(server_mod.Server({}).handle(reader, writer))
        self.assertIn(b"400", writer.sent)

    def test_empty_request_closes_quietly(self):
        reader, writer = FakeReader(b""), FakeWriter()
        asyncio.run(server_mod.Server({}).handle(reader, writer))
        self.assertEqual(writer.sent, b"")
        self.assertTrue(writer.closed)

    def test_a_silent_client_does_not_hold_the_task_forever(self):
        """A phone that opens a socket and walks out of range must time out."""
        original = server_mod.READ_TIMEOUT
        server_mod.READ_TIMEOUT = 0.05
        try:
            reader, writer = FakeReader(stall=True), FakeWriter()
            asyncio.run(server_mod.Server({}).handle(reader, writer))
        finally:
            server_mod.READ_TIMEOUT = original
        self.assertTrue(writer.closed)

    def test_oversized_body_is_capped(self):
        seen = {}

        def handler(request):
            seen["length"] = len(request.body)
            return 200, "text/plain", "ok"

        huge = b"x" * (server_mod.MAX_BODY * 3)
        serve({"/": handler}, request_bytes("POST", "/", huge))
        self.assertLessEqual(seen["length"], server_mod.MAX_BODY)

    def test_connection_is_always_closed(self):
        reader, writer = FakeReader(request_bytes()), FakeWriter()
        asyncio.run(server_mod.Server({"/": lambda r: (200, "text/plain", "x")}).handle(reader, writer))
        self.assertTrue(writer.closed)

    def test_responses_are_not_cached(self):
        """A status page served from a phone's cache is a lying status page."""
        head, _ = split(serve({"/": lambda r: (200, "text/plain", "x")}, request_bytes()))
        self.assertIn("Cache-Control: no-store", head)


if __name__ == "__main__":
    unittest.main()
