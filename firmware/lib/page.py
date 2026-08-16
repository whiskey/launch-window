"""The human-readable status page.

Red on black, and not as a style choice. The audience for this page is someone
standing at a telescope at one in the morning deciding whether to keep going;
a white phone screen costs them twenty minutes of dark adaptation. So the
palette is a single red hue at varying intensity, the verdict is carried by
size and by a glyph rather than by colour, and there is no white anywhere.
`?theme=day` gives the conventional traffic-light version for reading indoors.

Rendered as a generator of fragments, and the fragments are deliberately small.
This is not premature caution: the board reports 80 kB free after boot but
cannot allocate 4 kB contiguously, because importing eleven modules leaves the
heap fragmented. A single 2.6 kB stylesheet string was enough to raise
MemoryError while serving a request. So the CSS is split into three constants
that are yielded in sequence, no fragment exceeds about a kilobyte, and
`tools/smoke-test.py` asserts that on the hardware.
"""

GLYPHS = {"go": "●", "marginal": "◐", "no-go": "○", "unknown": "?"}

HEADLINES = {
    "go": "GO",
    "marginal": "MARGINAL",
    "no-go": "NO-GO",
    "unknown": "UNKNOWN",
}

# Split into three so no single yield needs a large contiguous allocation.
_CSS_BASE = """*{box-sizing:border-box;margin:0;padding:0}
body{background:#000;color:#c22;font:14px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;
padding:20px 16px 48px;max-width:44rem;margin:0 auto;-webkit-text-size-adjust:100%}
h1{font-size:11px;letter-spacing:.22em;text-transform:uppercase;color:#822;font-weight:400}
.verdict{display:flex;align-items:baseline;gap:.5rem;margin:.6rem 0 .2rem}
.verdict b{font-size:clamp(2.6rem,13vw,4rem);line-height:1;letter-spacing:-.02em;font-weight:600}
.glyph{font-size:clamp(2rem,9vw,2.8rem);line-height:1}
.reasons{color:#a11;margin:.5rem 0 1.4rem}
.reasons li{list-style:none;padding-left:1rem;text-indent:-1rem}
.reasons li::before{content:"\\2014 ";color:#711}
.window{border:1px solid #611;padding:.7rem .9rem;margin-bottom:1.4rem}
.window b{font-size:1.5rem;font-weight:600}
"""

_CSS_TABLE = """h2{font-size:10px;letter-spacing:.2em;text-transform:uppercase;color:#711;
font-weight:400;margin:1.5rem 0 .5rem;border-bottom:1px solid #400;padding-bottom:.3rem}
table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}
td,th{padding:.22rem .4rem;text-align:right;white-space:nowrap}
th{color:#711;font-weight:400;font-size:11px;text-transform:uppercase;letter-spacing:.08em}
td:first-child,th:first-child{text-align:left}
.bar{position:relative;width:100%;min-width:74px;height:.72rem;background:#200;display:block}
.bar i{position:absolute;inset:0 auto 0 0;background:#c22;display:block}
tr.veto .bar i{background:#500}
tr.veto td{color:#711}
.kv{display:grid;grid-template-columns:auto 1fr;gap:.15rem 1rem}
.kv dt{color:#811}
.kv dd{text-align:right;font-variant-numeric:tabular-nums}
footer{margin-top:2rem;color:#611;font-size:12px;border-top:1px solid #400;padding-top:.6rem}
footer a{color:#811}
.stale{color:#e33;border:1px solid #a11;padding:.5rem .7rem;margin-bottom:1rem}
"""

_CSS_DAY = """body.day{color:#e8e8e8}
body.day h1,body.day h2,body.day th,body.day .kv dt{color:#8a8a8a}
body.day h2{border-color:#333}
body.day .reasons{color:#bbb}
body.day .reasons li::before{color:#666}
body.day .window{border-color:#444}
body.day .bar{background:#222}
body.day .bar i{background:#5fb85f}
body.day tr.veto .bar i{background:#8a3a3a}
body.day tr.veto td{color:#777}
body.day .go{color:#5fb85f}body.day .marginal{color:#d8a33a}body.day .no-go{color:#c05050}
body.day footer{color:#777;border-color:#333}body.day footer a{color:#999}
"""


def _pct(value):
    return "—" if value is None else "%d%%" % round(value)


def _num(value, unit="", digits=0):
    if value is None:
        return "—"
    return ("%." + str(digits) + "f%s") % (value, unit)


def render(doc, theme="night"):
    """Yield the status page for a beacon document."""
    verdict = doc.get("verdict") or {}
    state = verdict.get("state", "unknown")
    site = doc.get("site") or {}
    night = doc.get("night") or {}
    moon = doc.get("moon") or {}
    data = doc.get("data") or {}
    beacon = doc.get("beacon") or {}
    body_class = "day" if theme == "day" else "night"

    yield (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="refresh" content="180">'
        "<title>%s — launch window</title><style>" % _escape(site.get("name", "beacon"))
    )
    yield _CSS_BASE
    yield _CSS_TABLE
    yield _CSS_DAY
    yield '</style></head><body class="%s">' % body_class

    yield "<h1>%s &middot; tonight</h1>" % _escape(site.get("name", "site"))

    if data.get("stale"):
        yield (
            '<p class="stale">Forecast is %s old — the sky half of this page is '
            "still exact, the weather half is not.</p>" % _escape(data.get("age", "?"))
        )
    if not (doc.get("clock") or {}).get("synced", True):
        yield (
            '<p class="stale">Clock has never synchronised. Every time on this '
            "page is meaningless until NTP succeeds.</p>"
        )

    yield '<div class="verdict"><span class="glyph">%s</span><b class="%s">%s</b></div>' % (
        GLYPHS.get(state, "?"),
        state,
        HEADLINES.get(state, "UNKNOWN"),
    )

    yield '<ul class="reasons">'
    for reason in verdict.get("reasons") or []:
        yield "<li>%s</li>" % _escape(reason)
    yield "</ul>"

    window = verdict.get("window")
    if window:
        yield (
            '<div class="window">imaging window<br><b>%s – %s</b> &nbsp;%s '
            "&middot; mean score %s</div>"
            % (
                window.get("start_local", "?"),
                window.get("end_local", "?"),
                _num(window.get("hours"), " h", 1),
                _num(window.get("mean_score"), "", 0),
            )
        )

    yield "<h2>Night</h2><dl class='kv'>"
    for label, key in (
        ("Sunset", "sunset_local"),
        ("Astronomical dusk", "dusk_astronomical_local"),
        ("Astronomical dawn", "dawn_astronomical_local"),
        ("Sunrise", "sunrise_local"),
        ("Dark for", "dark_duration"),
    ):
        yield "<dt>%s</dt><dd>%s</dd>" % (label, night.get(key) or "—")
    yield "</dl>"

    yield "<h2>Moon</h2><dl class='kv'>"
    yield "<dt>Phase</dt><dd>%s</dd>" % _escape(moon.get("phase", "—"))
    yield "<dt>Illuminated</dt><dd>%s</dd>" % _pct(
        (moon.get("illumination") or 0) * 100 if moon.get("illumination") is not None else None
    )
    yield "<dt>Rise / set</dt><dd>%s / %s</dd>" % (
        moon.get("rise_local") or "—",
        moon.get("set_local") or "—",
    )
    yield "<dt>Interferes tonight</dt><dd>%s</dd>" % (
        "yes" if moon.get("interferes") else "no"
    )
    yield "</dl>"

    hours = verdict.get("hours") or []
    if hours:
        yield (
            "<h2>Dark hours</h2><table><tr><th>Time</th><th>Score</th>"
            "<th>Cloud</th><th>Gust</th><th>Spread</th><th>Moon</th></tr>"
        )
        for hour in hours:
            score = hour.get("score")
            spread = None
            if hour.get("temperature_2m") is not None and hour.get("dew_point_2m") is not None:
                spread = hour["temperature_2m"] - hour["dew_point_2m"]
            yield (
                '<tr class="%s"><td>%s</td>'
                '<td style="width:34%%"><span class="bar"><i style="width:%d%%"></i></span></td>'
                "<td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>"
                % (
                    "veto" if hour.get("veto") else "",
                    hour.get("local", "—"),
                    int(score or 0),
                    _pct(hour.get("cloud_cover")),
                    _num(hour.get("wind_gusts_10m"), "", 0),
                    _num(spread, " K", 1),
                    _num(hour.get("moon_alt_deg"), "°", 0)
                    if (hour.get("moon_alt_deg") or -1) > 0
                    else "—",
                )
            )
        yield "</table>"

    other = "day" if theme != "day" else "night"
    yield (
        "<footer>%s &middot; up %s &middot; %s &middot; forecast %s old"
        ' &middot; <a href="?theme=%s">%s theme</a>'
        ' &middot; <a href="/api/v1/beacon">json</a></footer>'
        % (
            _escape(beacon.get("host", "launch-window")),
            _escape(beacon.get("uptime", "?")),
            _escape(doc.get("generated_local") or doc.get("generated_at") or ""),
            _escape(data.get("age", "?")),
            other,
            other,
        )
    )
    yield "</body></html>"


def _escape(text):
    if text is None:
        return ""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
