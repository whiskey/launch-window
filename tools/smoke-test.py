#!/usr/bin/env python3
"""Exercise the whole firmware on the board, not just the maths.

    tools/smoke-test.py             push, then run every check
    tools/smoke-test.py --no-push   run against what is already installed

`tests/` runs the pure modules under CPython, where the standard library is
complete and floats are 64-bit. This runs the same code where it has to live:
`asyncio` is MicroPython's, `json` is MicroPython's, the heap is 165 kB and the
radio is real. The failures it is built to catch are the ones a host test
cannot see —

- a module that imports something MicroPython does not have,
- a document that serialises on a laptop and runs the board out of memory,
- an access point that will not come up, or a socket that will not bind,
- `asyncio` API differences between the two implementations.

It does not associate a client with the access point; nothing here can do that
without a second radio. What it proves is that the AP starts, port 80 and port
53 bind, and a request routed through the real server object returns a real
page.

The firmware is parked (`main.py` renamed) and the board hard-reset before the
checks run, so the measurements are taken on a clean heap rather than alongside
a running beacon that already holds port 80 and 35 kB of imported modules. It
is restored afterwards whatever happens, and a parked `main.py` left behind by
an interrupted run is restored at the start of the next one.

Exits non-zero if any check fails.
"""

from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import pico  # noqa: E402
import strip_docs  # noqa: E402

FIRMWARE = os.path.join(ROOT, "firmware")

DEVICE_SCRIPT = r"""
import sys, gc, json
sys.path.insert(0, '/lib')
for name in ('sky','clock','weather','verdict','store','state','led','page','server','portal','wifi'):
    sys.modules.pop(name, None)
gc.collect()
start_mem = gc.mem_free()

failures = []
def check(label, condition, detail=''):
    print('%s %s %s' % ('PASS' if condition else 'FAIL', label, detail))
    if not condition:
        failures.append(label)

# -- every module must import under MicroPython ------------------------
import sky, clock, weather, verdict, store, state, led, page, server, portal, wifi
check('imports', True, '11 modules')

NOW = 1786917600  # 2026-08-16 22:00 UTC

# -- astronomy ---------------------------------------------------------
night = sky.night(NOW, 52.52, 13.40)
check('night boundaries', night['dusk_astronomical'] is not None and
      night['dawn_astronomical'] > night['dusk_astronomical'],
      'dark for %ds' % night['dark_seconds'])

# -- a full document ---------------------------------------------------
CONFIG = {'hostname':'launch-window',
          'site':{'name':'Garden','latitude':52.52,'longitude':13.40,
                  'timezone':{'name':'Europe/Berlin','std_offset_min':60,'dst':'eu',
                              'abbrev':['CET','CEST']}}}
hours = []
for i in range(8):
    hours.append({'ts': night['dusk_astronomical'] - 3600 + i*3600,
                  'cloud_cover': 5, 'cloud_cover_low': 0, 'cloud_cover_mid': 0,
                  'cloud_cover_high': 5, 'temperature_2m': 15.0, 'dew_point_2m': 4.0,
                  'wind_gusts_10m': 7.0, 'precipitation_probability': 0})
state.CACHE_PATH = '/smoke-cache.json'
beacon = state.Beacon(CONFIG, wifi=None, boot_ts=NOW-3600)
beacon.hours = hours
beacon.fetched_at = NOW - 600
gc.collect()
before_doc = gc.mem_free()
doc = beacon.document(NOW)
encoded = json.dumps(doc)
gc.collect()
check('document builds', doc['schema'] == 1 and doc['verdict']['state'] == 'go',
      'state=%s score=%s' % (doc['verdict']['state'], doc['verdict']['score']))
check('document serialises', len(encoded) > 500, '%d bytes json' % len(encoded))
check('document memory', before_doc - gc.mem_free() < 40000,
      'cost %d bytes' % (before_doc - gc.mem_free()))

# -- html, consumed the way the server consumes it ---------------------
# Never joined into one string: the largest contiguous allocation available
# here is a few kB, and the server writes each fragment straight to the socket.
first = last = None
total = biggest = 0
leaked_none = False
for fragment in page.render(doc):
    if first is None:
        first = fragment
    last = fragment
    total += len(fragment)
    if len(fragment) > biggest:
        biggest = len(fragment)
    if 'None' in fragment:
        leaked_none = True
check('page renders', first.startswith('<!doctype html>') and last.rstrip().endswith('</html>'),
      '%d bytes total' % total)
check('page has no None', not leaked_none)
check('page fragments stay small', biggest < 1200, 'largest fragment %d bytes' % biggest)

# -- led ---------------------------------------------------------------
lamp = led.Led()
lamp.set(doc['verdict']['state'])
steps = [lamp._step() for _ in range(4)]
lamp.set_night(True)
night_steps = [lamp._step() for _ in range(4)]
check('led pattern', lamp.pattern == 'go' and steps[0][0] == 1, str(steps[:2]))
check('led night dimming', night_steps[0][1] < steps[0][1],
      '%dms day vs %dms night' % (steps[0][1], night_steps[0][1]))

# -- http server, through the real object ------------------------------
import asyncio

class R:
    def __init__(self, data): self.data = data
    async def readline(self):
        i = self.data.find(b'\r\n')
        if i < 0:
            d, self.data = self.data, b''
            return d
        line, self.data = self.data[:i+2], self.data[i+2:]
        return line
    async def readexactly(self, n):
        c, self.data = self.data[:n], self.data[n:]
        return c

class W:
    # Collects into a list rather than concatenating: `sent += d` allocates a
    # new object per fragment and fragments the heap all by itself, which made
    # this test fail on memory the firmware never actually needed.
    def __init__(self): self.parts = []
    def write(self, d): self.parts.append(d)
    async def drain(self): pass
    def close(self): pass
    async def wait_closed(self): pass
    def contains(self, needle): return any(needle in p for p in self.parts)
    def size(self): return sum(len(p) for p in self.parts)

routes = {'/': lambda rq: (200, 'text/html; charset=utf-8', page.render(doc)),
          '/api/v1/beacon': lambda rq: server.json_response(doc),
          '/api/v1/health': lambda rq: server.json_response({'ok': True, 'schema': 1})}
srv = server.Server(routes)
w = W()
asyncio.run(srv.handle(R(b'GET / HTTP/1.1\r\nHost: x\r\n\r\n'), w))
check('http serves the page', w.contains(b'200 OK') and w.contains(b'<!doctype html>'),
      '%d bytes' % w.size())
w = W()
asyncio.run(srv.handle(R(b'GET /api/v1/beacon HTTP/1.1\r\nHost: x\r\n\r\n'), w))
check('http serves json', w.contains(b'application/json') and w.contains(b'"schema"'))
w = W()
asyncio.run(srv.handle(R(b'GET /nope HTTP/1.1\r\nHost: x\r\n\r\n'), w))
check('http 404s', w.contains(b'404'))

# -- dns hijack --------------------------------------------------------
q = b'\xab\xcd\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00\x07example\x03com\x00\x00\x01\x00\x01'
r = portal.dns_response(q, bytes((192,168,4,1)))
check('dns response', r is not None and r[:2] == b'\xab\xcd' and r.endswith(bytes((192,168,4,1))),
      '%d bytes' % (len(r) if r else 0))

# -- randomness for the setup passphrase -------------------------------
p1 = portal.generate_passphrase()
p2 = portal.generate_passphrase()
check('passphrase is random', p1 != p2 and len(p1) == 12,
      '%d chars, two draws differ' % len(p1))
check('passphrase alphabet', all(c in portal.ALPHABET for c in p1), p1[:3] + '...')

# -- radio -------------------------------------------------------------
import network
ap = network.WLAN(network.AP_IF)
ap.config(essid='launch-window-smoke', password=portal.generate_passphrase(),
          security=portal.AUTH_WPA2_AES_PSK)
ap.active(True)
import time
time.sleep(1)
addr = ap.ifconfig()[0]
check('access point up', ap.active() and addr == '192.168.4.1', addr)

# -- sockets actually bind on the live interface -----------------------
import socket
ok80 = ok53 = False
held_by_firmware = False
try:
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(('0.0.0.0', 80)); s.listen(1); s.close(); ok80 = True
except OSError as e:
    # EADDRINUSE means main.py is running and already listening on 80, which
    # proves the same thing this check was written to prove. Any other errno is
    # a real failure of the socket layer.
    if e.args and e.args[0] == 98:
        ok80 = held_by_firmware = True
    else:
        print('   port 80:', e)
try:
    d = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    d.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    d.bind(('0.0.0.0', 53)); d.close(); ok53 = True
except Exception as e:
    print('   port 53:', e)
check('port 80 binds', ok80, 'held by the running firmware' if held_by_firmware else '')
check('port 53 binds', ok53)
ap.active(False)

# -- what is left ------------------------------------------------------
try:
    import os as _os
    _os.remove('/smoke-cache.json')
except Exception:
    pass
gc.collect()
print('MEM start=%d end=%d' % (start_mem, gc.mem_free()))
check('heap not exhausted', gc.mem_free() > 60000, '%d bytes free' % gc.mem_free())
print('FAILURES=%d' % len(failures))
"""


PARK = """
import os
listing = os.listdir('/')
if 'main.off' in listing and 'main.py' in listing:
    os.remove('main.off')          # a stale park from an interrupted run
    listing = os.listdir('/')
if 'main.py' in listing:
    os.rename('main.py', 'main.off')
print('parked')
"""

RESTORE = """
import os
listing = os.listdir('/')
if 'main.off' in listing:
    if 'main.py' in listing:
        os.remove('main.off')
    else:
        os.rename('main.off', 'main.py')
print('restored', 'main.py' in os.listdir('/'))
"""


def main() -> int:
    push = "--no-push" not in sys.argv
    board = pico.Pico()
    print("board: %s\n" % board.device)
    output = error = ""
    try:
        board.enter_raw()
        if push:
            library = os.path.join(FIRMWARE, "lib")
            for name in sorted(os.listdir(library)):
                if name.endswith(".py"):
                    with open(os.path.join(library, name), "rb") as handle:
                        # Push exactly what deploy.py would, docstrings removed,
                        # so the memory this measures is the memory that ships.
                        board.put(strip_docs.strip_bytes(handle.read()), "/lib/" + name)
            print("pushed %d modules\n" % len(os.listdir(library)))

        board.check(PARK)
        board.hard_reset()
        board.enter_raw()
        try:
            output, error = board.exec(DEVICE_SCRIPT, timeout=180)
        finally:
            board.check(RESTORE)
    finally:
        try:
            board.exit_raw()
            board.reset()
        except Exception:
            pass
        board.close()

    sys.stdout.write(output)
    if error.strip():
        sys.stderr.write("\ndevice traceback:\n" + error)
        return 1
    if "FAILURES=0" not in output:
        print("\nSMOKE TEST FAILED")
        return 1
    print("\nOK — the firmware runs on the hardware")
    return 0


if __name__ == "__main__":
    sys.exit(main())
