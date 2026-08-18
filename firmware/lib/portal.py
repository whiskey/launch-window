"""First-run setup: the beacon serves its own network to be told about yours.

The credentials for a home WiFi cannot be committed to a repository and should
not be typed into a source file that then has to be kept out of one. So the
beacon that has no `wifi.json` becomes an access point, answers every DNS query
with its own address, and serves a page listing the networks it can see. The
phone that joins it pops the page up by itself — that is what the DNS hijack is
for — and the password is typed once, on the device, over a link that exists
for ninety seconds.

The setup AP is WPA2 rather than open. An open AP would mean the home WiFi
password crosses the air in the clear to a device anyone in range can also
join.

Its passphrase is random, generated on the board at first use and kept in
`setup.json`, which is never committed. Two weaker designs were tried and
rejected:

- A fixed default in `config.json` is a shared credential published in a
  README. Every beacon built from this source would have the same one, which
  is the property that makes such defaults worthless.
- Deriving it from the RP2040's unique ID looks better and is not. The format
  would be public, so the search space is only the ID's varying bytes — around
  24 bits, which an attacker who captures the WPA2 handshake cracks offline in
  seconds. That matters here more than it looks: the whole reason this network
  is encrypted is that the owner's *home* WiFi password crosses it, and anyone
  who recovers the passphrase can decrypt exactly that exchange.

Twelve characters from a 31-symbol alphabet is about 59 bits, which is not
crackable, and the characters that get misread on a phone screen — `0`/`O`,
`1`/`l`/`i` — are left out.

There is deliberately no fallback if the board cannot produce randomness. A
predictable passphrase would be worse than no access point at all, so the
failure is loud instead.

Nothing is validated beyond "the fields are not empty". A typo'd password
cannot be distinguished from a router that is temporarily down without trying
it, and the beacon does try it: after saving it reboots, attempts the join, and
comes back to setup mode if the join fails. Retry is the validation.
"""

import server as server_mod
import store

AP_ADDRESS = "192.168.4.1"

_PAGE_CSS = """*{box-sizing:border-box;margin:0;padding:0}
body{background:#0b0b0d;color:#e6e6e6;font:15px/1.55 -apple-system,BlinkMacSystemFont,
"Segoe UI",Roboto,sans-serif;padding:28px 20px 56px;max-width:30rem;margin:0 auto}
h1{font-size:1.35rem;font-weight:600;letter-spacing:-.01em}
p.sub{color:#8b8b93;margin:.35rem 0 1.6rem;font-size:.92rem}
label{display:block;margin:1rem 0 .3rem;color:#b9b9c2;font-size:.82rem;
text-transform:uppercase;letter-spacing:.09em}
select,input{width:100%;padding:.72rem .8rem;background:#17171b;color:#f2f2f2;
border:1px solid #33333c;border-radius:9px;font-size:1rem}
select:focus,input:focus{outline:2px solid #5a7fd6;border-color:transparent}
button{width:100%;margin-top:1.7rem;padding:.85rem;background:#3b6fd4;color:#fff;
border:0;border-radius:9px;font-size:1rem;font-weight:600}
.note{margin-top:1.5rem;color:#75757e;font-size:.82rem}
.rssi{color:#75757e;font-variant-numeric:tabular-nums}
"""


PASSPHRASE_PATH = "setup.json"
PASSPHRASE_LENGTH = 12

# CYW43 authentication mode. `WLAN.config(security=...)` passes this value
# straight to the driver on this port — it is a raw auth constant, not a small
# enum index, and the interface accepts any integer without complaint.
#
# It has to be WPA2/AES specifically. A mixed or unrecognised mode negotiates a
# TKIP *group* cipher, and while a client still associates over the CCMP
# pairwise key, every broadcast frame is then undecodable: DHCP DISCOVER never
# lands, the client falls back to a 169.254 address, and a phone sits on the
# join spinner until it gives up. Setup mode looks broken in a way that reads
# as a wrong passphrase.
AUTH_WPA2_AES_PSK = 0x00400004

# No 0/O, 1/l/i — the characters people mistype off a screen at night.
ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"

# 8 * 31 = 248. Bytes at or above this are discarded rather than folded, which
# would make the first eight letters of the alphabet slightly likelier.
_UNBIASED_LIMIT = 248


def generate_passphrase(length=PASSPHRASE_LENGTH, source=None):
    """A random passphrase. Raises if the platform has no randomness."""
    if source is None:
        import os

        source = os.urandom
    characters = []
    while len(characters) < length:
        for byte in source(length):
            if byte < _UNBIASED_LIMIT:
                characters.append(ALPHABET[byte % len(ALPHABET)])
                if len(characters) == length:
                    break
    return "".join(characters)


def ensure_passphrase(configured=None, path=PASSPHRASE_PATH):
    """The setup network's passphrase: configured, remembered, or new.

    Remembering it matters as much as generating it. If the board invented a
    new passphrase on every boot, a power blip during setup would silently
    change the network the owner is standing in front of with a phone.
    """
    if configured:
        return configured
    stored = store.load(path)
    if stored and stored.get("passphrase"):
        return stored["passphrase"]
    passphrase = generate_passphrase()
    store.save(path, {"passphrase": passphrase})
    return passphrase


def scan_networks(station):
    """Visible SSIDs, strongest first, deduplicated across access points."""
    seen = {}
    try:
        for entry in station.scan():
            name = entry[0].decode("utf-8", "replace").strip()
            if not name:
                continue  # hidden network: nothing to show, nothing to pick
            rssi = entry[3]
            if name not in seen or rssi > seen[name]:
                seen[name] = rssi
    except Exception:
        pass
    return sorted(seen.items(), key=lambda item: -item[1])


def setup_page(networks, message=None):
    yield (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>launch-window setup</title><style>%s</style></head><body>" % _PAGE_CSS
    )
    yield "<h1>launch-window</h1>"
    yield (
        '<p class="sub">Tell the beacon which network to join. It will restart, '
        "connect, and start reporting on tonight's sky.</p>"
    )
    if message:
        yield '<p class="sub">%s</p>' % message
    yield '<form method="POST" action="/save"><label for="ssid">Network</label>'
    if networks:
        yield '<select id="ssid" name="ssid">'
        for name, rssi in networks:
            yield '<option value="%s">%s &nbsp;(%d dBm)</option>' % (
                _escape(name),
                _escape(name),
                rssi,
            )
        yield "</select>"
    else:
        yield '<input id="ssid" name="ssid" placeholder="network name" autocapitalize="off">'
    yield (
        '<label for="password">Password</label>'
        '<input id="password" name="password" type="password" '
        'autocomplete="current-password">'
        "<button type=submit>Save and restart</button></form>"
    )
    yield (
        '<p class="note">Stored on the board in <code>wifi.json</code>, which is '
        "never committed. To change it later, delete that file and power-cycle.</p>"
    )
    yield "</body></html>"


def saved_page(ssid):
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>saved</title><style>%s</style></head><body>"
        "<h1>Saved</h1>"
        '<p class="sub">Restarting and joining <b>%s</b>. This network is about to '
        "disappear — rejoin your own, then look for the beacon by its hostname or "
        "on your router's client list.</p>"
        '<p class="note">If the LED returns to a slow half-second blink, the join '
        "failed and setup is running again.</p></body></html>"
        % (_PAGE_CSS, _escape(ssid))
    )


class Portal:
    """Runs the AP, the DNS hijack and the setup form until credentials arrive."""

    def __init__(self, ssid="launch-window-setup", password=None, on_save=None):
        self.ssid = ssid
        # Resolved in start(): generating a passphrase is a side effect that
        # writes to flash, and constructing a Portal should not do that.
        self.password = password
        self.on_save = on_save
        self.access_point = None
        self.networks = []

    def start(self):
        import network

        self.password = ensure_passphrase(self.password)
        # Printed for anyone on the serial console; it is not shown on the
        # setup page itself, where it would be visible to whoever already
        # joined the network.
        print("setup network %s, passphrase %s" % (self.ssid, self.password))

        # Scan from station mode first: a CYW43 in AP mode cannot survey the
        # band, and the list of networks is the whole point of the page.
        station = network.WLAN(network.STA_IF)
        station.active(True)
        self.networks = scan_networks(station)
        station.active(False)

        self.access_point = network.WLAN(network.AP_IF)
        self.access_point.config(
            essid=self.ssid, password=self.password, security=AUTH_WPA2_AES_PSK
        )
        self.access_point.active(True)
        return self.access_point

    def routes(self):
        def index(request):
            return 200, "text/html; charset=utf-8", setup_page(self.networks)

        def save(request):
            if request.method != "POST":
                return 405, "text/plain", "POST only"
            form = request.form()
            ssid = (form.get("ssid") or "").strip()
            password = form.get("password") or ""
            if not ssid:
                return (
                    400,
                    "text/html; charset=utf-8",
                    setup_page(self.networks, "Pick a network first."),
                )
            if self.on_save:
                self.on_save(ssid, password)
            return 200, "text/html; charset=utf-8", saved_page(ssid)

        return {"/": index, "/save": save}

    def server(self):
        routes = self.routes()
        # Captive-portal probes ask for paths nobody registered — Android wants
        # /generate_204, Apple wants /hotspot-detect.html. Serving the setup
        # page for anything unknown is what makes the sheet appear by itself.
        return server_mod.Server(routes, fallback=routes["/"])

    async def run_dns(self):
        """Answer every A query with the beacon's own address."""
        import asyncio
        import socket

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setblocking(False)
        sock.bind(("0.0.0.0", 53))
        octets = bytes(int(part) for part in AP_ADDRESS.split("."))
        while True:
            try:
                query, source = sock.recvfrom(256)
            except Exception:
                await asyncio.sleep_ms(60)
                continue
            response = dns_response(query, octets)
            if response:
                try:
                    sock.sendto(response, source)
                except Exception:
                    pass

    def stop(self):
        if self.access_point is not None:
            try:
                self.access_point.active(False)
            except Exception:
                pass


def dns_response(query, address_octets):
    """Build an A-record answer pointing at us, for any single-question query.

    Only the shape a captive-portal probe sends is handled: one question, class
    IN. Anything else is ignored rather than answered wrongly.
    """
    if len(query) < 12:
        return None
    if query[2] & 0x80:  # already a response
        return None
    if query[4:6] != b"\x00\x01":  # not exactly one question
        return None

    # Walk the QNAME labels to find where the question ends.
    offset = 12
    while offset < len(query):
        length = query[offset]
        if length == 0:
            offset += 1
            break
        offset += length + 1
    if offset + 4 > len(query):
        return None
    question_end = offset + 4

    header = (
        query[0:2]  # same transaction id
        + b"\x81\x80"  # response, recursion available, no error
        + b"\x00\x01"  # one question, echoed back
        + b"\x00\x01"  # one answer
        + b"\x00\x00\x00\x00"  # no authority or additional records
    )
    answer = (
        b"\xc0\x0c"  # pointer to the question's name at offset 12
        + b"\x00\x01\x00\x01"  # type A, class IN
        + b"\x00\x00\x00\x3c"  # TTL 60 s
        + b"\x00\x04"
        + address_octets
    )
    return header + query[12:question_end] + answer


def _escape(text):
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
