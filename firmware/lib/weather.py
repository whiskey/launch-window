"""Open-Meteo client: the hourly forecast for one night, and nothing else.

Open-Meteo is used because it needs no API key. A key would have to live in the
beacon's flash, be excluded from the repository, and be re-entered on every
reflash — for a public weather forecast. The free tier's terms cover this
usage: one request per refresh interval, roughly a hundred a day.

The request is narrowed hard on purpose. Asking for two full days of eleven
variables returns 3.8 kB; asking for the eight variables that feed a verdict,
only over the hours of the coming night, and with `timeformat=unixtime`,
returns about 1 kB. On a board with 165 kB of heap that difference is not
critical, but the parsed form is what gets held between refreshes, cached to
flash, and serialised into every status response.

Plain HTTP rather than HTTPS, deliberately:

- TLS on an RP2040 costs 30-40 kB of heap for the handshake, and mbedtls in
  this firmware cannot verify a certificate chain anyway without a CA bundle
  that would have to be shipped and maintained. Encrypting to an unverified
  peer buys confidentiality against passive observers only.
- Nothing secret is sent. The request carries a latitude and a longitude, both
  of which the beacon publishes on its own status page, and no credential.
- The honest residual risk: someone able to modify traffic on the path could
  feed the beacon a false forecast. The cost of that attack succeeding is a
  wasted evening setting up under clouds, or a missed clear night. That is
  worth 35 kB of heap and the removal of an unverifiable trust chain.

Responses arrive `Transfer-Encoding: chunked` with no `Content-Length`, so the
reader dechunks rather than trusting a header that is never sent.
"""

import json

HOST = "api.open-meteo.com"
PORT = 80

# The variables that feed `verdict.py`, in the order the API returns them.
VARIABLES = (
    "cloud_cover",
    "cloud_cover_low",
    "cloud_cover_mid",
    "cloud_cover_high",
    "temperature_2m",
    "dew_point_2m",
    "wind_gusts_10m",
    "precipitation_probability",
)


class WeatherError(Exception):
    """The forecast could not be retrieved or made sense of."""


def _hour_stamp(ts):
    """Format a timestamp as the API's `start_hour`/`end_hour` argument."""
    from clock import parts

    y, mo, d, h, _, _, _ = parts(ts)
    return "%04d-%02d-%02dT%02d:00" % (y, mo, d, h)


def build_path(latitude, longitude, start_ts, end_ts):
    """The request path for one night's forecast. Pure, so tests can read it."""
    return (
        "/v1/forecast?latitude=%.4f&longitude=%.4f&hourly=%s"
        "&timeformat=unixtime&timezone=GMT&start_hour=%s&end_hour=%s"
        % (
            latitude,
            longitude,
            ",".join(VARIABLES),
            _hour_stamp(start_ts),
            _hour_stamp(end_ts),
        )
    )


def dechunk(body):
    """Decode a chunked transfer body. Returns the assembled bytes."""
    out = b""
    while True:
        line_end = body.find(b"\r\n")
        if line_end < 0:
            break
        size_field = body[:line_end].split(b";")[0].strip()
        if not size_field:
            break
        try:
            size = int(size_field, 16)
        except ValueError:
            raise WeatherError("malformed chunk size %r" % size_field)
        if size == 0:
            break
        start = line_end + 2
        out += body[start : start + size]
        body = body[start + size + 2 :]
    return out


def parse_http(raw):
    """Split a raw HTTP response into (status_code, body_bytes)."""
    head, _, body = raw.partition(b"\r\n\r\n")
    if not head:
        raise WeatherError("empty response")
    lines = head.split(b"\r\n")
    try:
        status = int(lines[0].split()[1])
    except (IndexError, ValueError):
        raise WeatherError("unparseable status line %r" % lines[0][:60])
    for line in lines[1:]:
        name, _, value = line.partition(b":")
        if name.strip().lower() == b"transfer-encoding" and b"chunked" in value.lower():
            body = dechunk(body)
            break
    return status, body


def to_hours(document):
    """Turn an Open-Meteo document into a list of per-hour dicts.

    Missing values stay None. Open-Meteo returns null for variables it has no
    model data for, and a null cloud cover must not silently become a clear
    sky — `verdict.py` refuses to grade an hour it cannot see.
    """
    hourly = document.get("hourly") or {}
    times = hourly.get("time") or []
    if not times:
        raise WeatherError("forecast contained no hours")

    def column(name):
        values = hourly.get(name) or []
        return values + [None] * (len(times) - len(values))

    columns = {name: column(name) for name in VARIABLES}
    hours = []
    for index, ts in enumerate(times):
        row = {"ts": int(ts)}
        for name in VARIABLES:
            row[name] = columns[name][index]
        hours.append(row)
    return hours


async def fetch(latitude, longitude, start_ts, end_ts, timeout=20):
    """Retrieve and parse one night's forecast. Raises WeatherError."""
    import asyncio

    path = build_path(latitude, longitude, start_ts, end_ts)
    request = (
        "GET %s HTTP/1.1\r\nHost: %s\r\n"
        "User-Agent: launch-window/1.0 (Pico W beacon)\r\n"
        "Accept: application/json\r\nConnection: close\r\n\r\n" % (path, HOST)
    )

    async def _request():
        reader, writer = await asyncio.open_connection(HOST, PORT)
        try:
            writer.write(request.encode())
            await writer.drain()
            chunks = []
            while True:
                chunk = await reader.read(512)
                if not chunk:
                    break
                chunks.append(chunk)
            return b"".join(chunks)
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    try:
        raw = await asyncio.wait_for(_request(), timeout)
    except WeatherError:
        raise
    except Exception as exc:
        raise WeatherError("request failed: %s" % (exc,))

    status, body = parse_http(raw)
    if status != 200:
        raise WeatherError("HTTP %d" % status)
    try:
        document = json.loads(body)
    except Exception:
        raise WeatherError("response was not JSON")
    if "error" in document:
        raise WeatherError(str(document.get("reason", "API error")))
    return to_hours(document)
