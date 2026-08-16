# launch-window

A Raspberry Pi Pico W that answers one question, from across the room, before you ask it:

> **Is tonight worth setting up the rig?**

It computes tonight's darkness and moonlight on the board, fetches the hourly cloud, wind and
dew-point forecast for your site, grades every dark hour, and signals the verdict on its single
onboard LED. Plug it into any USB socket where you will walk past it.

```
                    ┌──────────────────────────────────────┐
   Open-Meteo ─────►│  Pico W                              │
   (hourly cloud,   │                                      │
    gusts, dew      │   sky.py     darkness + moon, local  │
    point, rain)    │   verdict.py grade each dark hour    │──► onboard LED
                    │   state.py   the document            │    GO / MARGINAL / NO-GO
                    │   server.py  :80                     │
                    └──────────────┬───────────────────────┘
                                   │ WiFi
                        phone ─────┴──── /  and  /api/v1/beacon
```

The astronomy is computed locally and the weather is fetched. That split is deliberate:
darkness and moonrise are perfectly predictable and must never be wrong, so they do not depend
on a network. When the link drops, the beacon still knows exactly when astronomical night
starts — and it says plainly that the weather half of its answer has gone stale.

## The LED language

One green LED that cannot be dimmed, so everything is said in on and off times.

| Pattern | Meaning |
|---|---|
| One long 1.5 s pulse every 3 s | **GO** — at least 2 h of usable dark sky |
| Two short blinks every 3 s | **MARGINAL** — there is a window; go read it |
| One 60 ms blip every 5 s | **NO-GO** — alive, and almost invisible in a dark room |
| Three short blinks every 3 s | **UNKNOWN** — no forecast, or the clock never synced |
| 4 Hz blink | connecting to WiFi — seconds only |
| Steady 1 Hz half-on blink | **setup mode**: its own WiFi is up, come and configure it |

After sunset every on-time shrinks to a third. A green LED at full duty costs a dark-adapted
observer their night vision, and this device exists to serve people who care about that.

## Setting it up

The beacon has never seen your WiFi password and this repository must never contain it, so it
asks for it once, over a network of its own.

1. **Plug it in.** With no credentials stored it starts an access point called
   **`launch-window-setup`** and the LED blinks steadily at 1 Hz.

   Its passphrase is random — twelve characters, about 59 bits — generated once and kept in
   `setup.json` on the board, which is never committed. **`tools/deploy.py` prints it**, and
   `tools/pico.py get setup.json` recovers it later. Setting `setup_ap.password` in
   `firmware/config.json` overrides it.

   It has to be unguessable rather than merely unique, because the owner's home WiFi password
   crosses this network: anyone who recovers the passphrase from a captured handshake can
   decrypt exactly that exchange. A passphrase derived from the board's chip ID would look
   fine and offer about 24 bits, which is seconds of offline work.
2. **Join that network with a phone.** The setup page opens by itself — the beacon answers every
   DNS query with its own address, which is what makes the captive-portal sheet appear. If it
   does not, open `http://192.168.4.1`.
3. **Pick your network, type the password, submit.** The beacon restarts and joins. Credentials
   land in `wifi.json` on the board, which `.gitignore` excludes and `deploy.py` never touches.
4. **Find it** at `http://launch-window/` or by its address on your router's client list. If the
   join fails, it returns to setup mode — retry is the validation.

To change the network later, delete `wifi.json` (`tools/deploy.py --wipe-wifi`) and power-cycle.

## The site

Edit `firmware/config.json`. It ships pointed at Berlin, which is a placeholder for a garden:

```json
"site": {
  "name": "Garden",
  "latitude": 52.52,
  "longitude": 13.4,
  "timezone": { "name": "Europe/Berlin", "std_offset_min": 60, "dst": "eu",
                "abbrev": ["CET", "CEST"] }
}
```

Coordinates to a hundredth of a degree are ample — that is a kilometre, and the weather model's
grid is coarser than that. `dst: "eu"` implements the EU daylight-saving rule; `null` gives a
fixed offset anywhere else.

The `thresholds` block in the same file is where the judgement lives — what counts as a usable
hour, how long a run has to be before it is worth carrying a mount outside. The defaults, and
the reasoning behind every weight, are documented at the top of
[`firmware/lib/verdict.py`](firmware/lib/verdict.py).

## How the verdict is reached

Every forecast hour that overlaps astronomical night is scored from 0 to 100. The verdict comes
from the **longest run of usable hours**, never from the night's average: four clear hours after
a cloudy evening is a session, and a night that sits flat at 60 all the way through is a wasted
setup.

- **Cloud cover dominates**, and high cloud is penalised beyond its share — thin cirrus looks
  like a clear sky to a person and to most forecasts, and it is the usual reason a night that
  looked fine produced nothing.
- **Gusts, not mean wind.** Steady air does not move a tripod; a gust during a 240 s sub
  elongates every star in it. 40 km/h is a veto.
- **Dew is graded from the temperature/dew-point spread**, which is what actually predicts it.
  It is a penalty and never a veto, because the answer is a heater.
- **Moonlight scales with illuminated fraction and altitude**, to the power 1.5 — a half-lit
  Moon is far less than half as bright as a full one.
- **Rain probability at or above 40 % is a veto.** Wet equipment ends a night and can end a
  camera.

An hour whose cloud cover came back null scores `null` and is excluded, rather than counted as
clear. A beacon with no forecast at all reports `unknown`, not `no-go` — those are different
statements, and only one of them is a claim about the sky.

## The API

`GET /api/v1/beacon` returns the document defined in
[`protocol/beacon-v1.md`](protocol/beacon-v1.md), which follows the same three rules as the
rig's own status API: never present a stale value as current, nulls are honest, additive changes
only within a version. `GET /api/v1/health` is a cheap liveness check.
`POST /api/v1/refresh` fetches immediately.

`GET /` is the human page: red on black, because whoever reads it at one in the morning is
dark-adapted. `?theme=day` for the ordinary version.

## Working on it

```
tests/run.py                  the host suite — 166 tests, nothing to install
tools/simulate.py             run the firmware on your laptop against tonight's real forecast
tools/simulate.py --serve     ... and serve the actual status page at localhost:8080
tools/deploy.py               push changed files to the board and restart it
tools/smoke-test.py           run the whole firmware on the hardware
tools/verify-device.py        prove the board's arithmetic matches the host's
tools/pico.py                 a small serial REPL driver: run, get, put, ls, reset
```

Nothing here needs anything installed. The one optional dependency is `pyephem`, which
`tests/test_sky.py` compares the astronomy against and skips cleanly without:

```sh
python3 -m venv /tmp/ephem && /tmp/ephem/bin/pip install ephem
/tmp/ephem/bin/python tests/run.py
```

### Two things about this hardware that shaped the code

**MicroPython on the RP2040 uses 32-bit floats.** A Julian Day number is about 2.46 million,
which quantises to 0.25 days in a float32 — on the board, `2460904.5` evaluates to `2460905.0`
and the time of day disappears. Every textbook formulation of this astronomy is written in
double precision and fails silently here. `sky.py` therefore keeps time as an integer split into
whole days and a fraction, and reduces the fast angle terms through exact integer arithmetic.

The failure was not hypothetical: writing `360.98564736629` and taking its fractional part on
the board yields `0.985778809`, an error that accumulates to **1.28 degrees of sidereal time**
over the days since J2000 — five minutes on every rise and set time — while every host test
still passed. `tools/verify-device.py` exists to catch exactly this, and now reports the board
agreeing with the host to 0.002 degrees and one second.

**The heap fragments.** After importing eleven modules the board reports 80 kB free but cannot
allocate 4 kB contiguously. So the status page is streamed as fragments of at most a kilobyte,
and `deploy.py` strips docstrings on the way to flash — MicroPython keeps them in RAM for as
long as a module is imported, and this project's documentation costs more heap than the board
can spare. The documentation stays here, where it is read.

## What has been verified, and what has not

Verified on the hardware: all eleven modules import; the document builds and serialises;
the page renders and is served by the real server object; the access point comes up at
192.168.4.1; ports 80 and 53 bind; the astronomy matches the host to 0.002 degrees; the heap
survives it with 107 kB free.

**Not yet verified: a client actually associating with the beacon over the air.** A Pico W
cannot open a TCP connection to its own access point, and testing it needs a second radio. The
accept path is covered on the host in `tests/test_server.py` and the socket binds on the board
— but the first phone to join the setup network will be the first real client this code has
ever had. That is a thirty-second test, and it is step 2 above.

## Layout

| Path | What it holds |
|---|---|
| `firmware/main.py` | Boot order, the task set, and why the watchdog is armed late |
| `firmware/lib/sky.py` | Sun and moon geometry, and the float32 problem |
| `firmware/lib/verdict.py` | The grading rules and where every weight comes from |
| `firmware/lib/state.py` | The refresh cycle and the published document |
| `firmware/lib/page.py` | The night-vision status page |
| `firmware/lib/portal.py` | Setup access point, captive DNS, credential form |
| `firmware/lib/server.py`, `weather.py`, `clock.py`, `led.py`, `wifi.py`, `store.py` | The rest |
| `protocol/` | The versioned JSON contract and its schema |
| `tools/` | Deploy, simulate, smoke-test, verify, serial driver |
| `tests/` | The host suite |
