"""A small async HTTP server, sized for one phone at a time.

Written against `asyncio.start_server` rather than pulled in as a framework:
the beacon serves three routes, and a dependency would cost more flash than the
eighty lines it replaces. Everything here is deliberate about the failure modes
that actually occur on a microcontroller:

- **Every read has a timeout.** A phone that opens a socket, sends nothing and
  walks out of range would otherwise hold a task forever. Two of those and the
  beacon is deaf.
- **Bodies are chunk-limited.** A request body is read up to a cap and no
  further, so a malformed `Content-Length` cannot make the board allocate until
  it dies.
- **Handlers may return an iterable.** The status page is assembled from
  fragments and streamed, so rendering it never needs the whole document in
  heap at once.
- **A handler that raises returns 500 and keeps the server alive.** A status
  beacon that stops answering because one request went wrong has failed at its
  only job.
"""

import json

READ_TIMEOUT = 8
MAX_BODY = 2048
MAX_LINE = 512

STATUS_TEXT = {
    200: "OK",
    303: "See Other",
    400: "Bad Request",
    404: "Not Found",
    405: "Method Not Allowed",
    500: "Internal Server Error",
}


class Request:
    def __init__(self, method, path, query, headers, body):
        self.method = method
        self.path = path
        self.query = query
        self.headers = headers
        self.body = body

    def form(self):
        """Parse an `application/x-www-form-urlencoded` body."""
        return parse_qs(self.body.decode("utf-8", "replace") if self.body else "")


def unquote_plus(text):
    """Percent-decoding with `+` for space. MicroPython has no `urllib`.

    Decoding assembles bytes and then decodes UTF-8 once, rather than turning
    each `%XX` straight into a character. The shortcut works for ASCII and
    quietly corrupts everything else: a password containing "ß" arrives as
    `%C3%9F`, and per-character decoding yields "Ã\x9f" — a password that looks
    almost right, saves without complaint, and then simply fails to join the
    network with no explanation offered anywhere.
    """
    text = text.replace("+", " ")
    if "%" not in text:
        return text
    out = bytearray()
    index = 0
    while index < len(text):
        character = text[index]
        if character == "%" and index + 3 <= len(text):
            try:
                out.append(int(text[index + 1 : index + 3], 16))
                index += 3
                continue
            except ValueError:
                pass
        out.extend(character.encode("utf-8"))
        index += 1
    return bytes(out).decode("utf-8", "replace")


def parse_qs(query):
    """Query or form string to a dict. Later keys win; no multi-value support."""
    result = {}
    for pair in query.split("&"):
        if not pair:
            continue
        name, _, value = pair.partition("=")
        result[unquote_plus(name)] = unquote_plus(value)
    return result


def json_response(data, status=200):
    return status, "application/json; charset=utf-8", json.dumps(data)


def html_response(body, status=200):
    return status, "text/html; charset=utf-8", body


def redirect(location):
    return 303, "text/plain; charset=utf-8", ("see %s" % location), {"Location": location}


class Server:
    """Routes requests to handlers keyed by path.

    A handler takes a `Request` and returns `(status, content_type, body)` or
    `(status, content_type, body, extra_headers)`, where body is a string,
    bytes, or an iterable of either.
    """

    def __init__(self, routes, fallback=None, name="launch-window"):
        self.routes = routes
        self.fallback = fallback
        self.name = name

    async def _read_line(self, reader):
        line = await reader.readline()
        if len(line) > MAX_LINE:
            raise ValueError("request line too long")
        return line

    async def handle(self, reader, writer):
        import asyncio

        try:
            try:
                request_line = await asyncio.wait_for(
                    self._read_line(reader), READ_TIMEOUT
                )
            except Exception:
                return
            if not request_line:
                return

            try:
                method, target, _ = request_line.decode().split(" ", 2)
            except ValueError:
                await self._send(writer, 400, "text/plain", "bad request line")
                return

            path, _, query = target.partition("?")
            headers = {}
            while True:
                line = await asyncio.wait_for(self._read_line(reader), READ_TIMEOUT)
                if not line or line == b"\r\n":
                    break
                name, _, value = line.decode("utf-8", "replace").partition(":")
                headers[name.strip().lower()] = value.strip()

            body = b""
            length = int(headers.get("content-length") or 0)
            if length > 0:
                body = await asyncio.wait_for(
                    reader.readexactly(min(length, MAX_BODY)), READ_TIMEOUT
                )

            request = Request(method, path, parse_qs(query), headers, body)
            handler = self.routes.get(path) or self.fallback
            if handler is None:
                await self._send(writer, 404, "text/plain", "not found")
                return

            try:
                result = handler(request)
                if hasattr(result, "__await__"):
                    result = await result
            except Exception as exc:
                await self._send(
                    writer, 500, "text/plain", "handler failed: %s" % (exc,)
                )
                return

            status, content_type, payload = result[0], result[1], result[2]
            extra = result[3] if len(result) > 3 else None
            await self._send(writer, status, content_type, payload, extra)
        finally:
            try:
                await writer.drain()
            except Exception:
                pass
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    async def _send(self, writer, status, content_type, payload, extra=None):
        head = "HTTP/1.1 %d %s\r\nContent-Type: %s\r\n" % (
            status,
            STATUS_TEXT.get(status, "OK"),
            content_type,
        )
        # No Content-Length: the body may be a generator whose length is not
        # known before it is rendered. Closing the connection delimits it,
        # which HTTP/1.1 permits and every client handles.
        head += "Connection: close\r\nCache-Control: no-store\r\n"
        for name, value in (extra or {}).items():
            head += "%s: %s\r\n" % (name, value)
        writer.write(head.encode() + b"\r\n")

        if isinstance(payload, (bytes, str)):
            payload = (payload,)
        for piece in payload:
            writer.write(piece.encode() if isinstance(piece, str) else piece)
            await writer.drain()

    async def serve(self, host="0.0.0.0", port=80):
        import asyncio

        return await asyncio.start_server(self.handle, host, port)
