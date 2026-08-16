"""launch-window — is tonight worth setting up the rig?

Boot order, and why it is this order:

1. The LED starts first, before the network exists, so a board that fails
   later still says something rather than sitting dark.
2. Credentials decide the mode. No `wifi.json`, or a join that fails three
   times, means the setup portal. A router that is merely rebooting should not
   strand the beacon in setup mode forever, so the portal gives up after five
   minutes and the board restarts into a fresh attempt.
3. The watchdog is armed only after the first full pass through the main loop.
   An RP2040 watchdog cannot be switched off once started; arming it before the
   code is known to work would turn any boot-time exception into a board that
   reboots every eight seconds and is very hard to talk to. Arming it after the
   first success means it only ever guards a system that has already run.

The refresh loop backs off on failure to a quarter of an hour. The forecast it
is fetching updates hourly, so hammering a free API through an outage would
gain nothing and cost the beacon its welcome.
"""

import gc
import sys

import asyncio
import machine

sys.path.insert(0, "/lib")

import clock  # noqa: E402
import led as led_mod  # noqa: E402
import page  # noqa: E402
import portal as portal_mod  # noqa: E402
import server as server_mod  # noqa: E402
import state as state_mod  # noqa: E402
import store  # noqa: E402
import wifi as wifi_mod  # noqa: E402

CONFIG_PATH = "config.json"
WIFI_PATH = "wifi.json"

DEFAULT_CONFIG = {
    "hostname": "launch-window",
    "refresh_minutes": 30,
    "watchdog": True,
    "ntp_host": "pool.ntp.org",
    "site": {
        "name": "Garden",
        "latitude": 52.52,
        "longitude": 13.40,
        "timezone": {
            "name": "Europe/Berlin",
            "std_offset_min": 60,
            "dst": "eu",
            "abbrev": ["CET", "CEST"],
        },
    },
    # No passphrase here: portal.default_password() derives one from this
    # board's unique ID, so no shared credential ships in the repository.
    "setup_ap": {"ssid": "launch-window-setup", "password": None},
    "country": "DE",
}

WATCHDOG_TIMEOUT_MS = 8000
PORTAL_TIMEOUT_S = 300
JOIN_ATTEMPTS = 3


def load_config():
    return store.merged(DEFAULT_CONFIG, store.load(CONFIG_PATH))


async def run_portal(config, led):
    """Serve the setup page until credentials are saved, then restart."""
    led.set("setup")
    saved = {}

    def on_save(ssid, password):
        saved["ssid"] = ssid
        store.save(WIFI_PATH, {"ssid": ssid, "password": password})

    ap_config = config.get("setup_ap") or {}
    portal = portal_mod.Portal(
        ssid=ap_config.get("ssid", "launch-window-setup"),
        password=ap_config.get("password"),  # None derives it from the board ID
        on_save=on_save,
    )
    portal.start()
    await portal.server().serve(port=80)
    dns = asyncio.create_task(portal.run_dns())

    waited = 0
    while "ssid" not in saved and waited < PORTAL_TIMEOUT_S:
        await asyncio.sleep(1)
        waited += 1

    # Either credentials arrived or the window closed; both end in a restart,
    # which is the only way to cleanly leave AP mode on this chip.
    await asyncio.sleep(2)
    dns.cancel()
    portal.stop()
    machine.reset()


async def refresh_loop(beacon, config, led):
    """Fetch the forecast, then again every refresh interval."""
    backoff = 60
    interval = int(config.get("refresh_minutes", 30)) * 60
    while True:
        ok = await beacon.refresh()
        gc.collect()
        led.set(beacon.led_pattern())
        if ok:
            backoff = 60
            await asyncio.sleep(interval)
        else:
            await asyncio.sleep(backoff)
            backoff = min(900, backoff * 2)


async def signal_loop(beacon, led):
    """Keep the LED and the night dimming in step with the current verdict."""
    while True:
        led.set(beacon.led_pattern())
        led.set_night(beacon.is_night())
        await asyncio.sleep(20)


async def clock_loop(beacon, config):
    """Re-synchronise the clock at boot and daily; the RP2040 has no RTC."""
    host = config.get("ntp_host", "pool.ntp.org")
    while True:
        if clock.sync_ntp(host):
            beacon.last_sync = clock.now()
            await asyncio.sleep(86400)
        else:
            await asyncio.sleep(60)


def routes_for(beacon):
    def status_page(request):
        theme = request.query.get("theme", "night")
        return 200, "text/html; charset=utf-8", page.render(beacon.document(), theme)

    def beacon_json(request):
        return server_mod.json_response(beacon.document())

    def health(request):
        return server_mod.json_response({"ok": True, "schema": state_mod.SCHEMA})

    def refresh_now(request):
        if request.method != "POST":
            return 405, "text/plain; charset=utf-8", "POST only"
        asyncio.create_task(beacon.refresh())
        return server_mod.json_response({"ok": True, "action": "refresh"})

    return {
        "/": status_page,
        "/api/v1/beacon": beacon_json,
        "/api/v1/health": health,
        "/api/v1/refresh": refresh_now,
    }


async def main():
    config = load_config()
    led = led_mod.Led()
    led_task = asyncio.create_task(led.run())

    credentials = store.load(WIFI_PATH)  # gitleaks:allow - reads the file, is not one
    if not credentials or not credentials.get("ssid"):
        await run_portal(config, led)
        return

    led.set("connecting")
    link = wifi_mod.Wifi(
        credentials["ssid"],
        credentials.get("password", ""),
        country=config.get("country", "DE"),
        hostname=config.get("hostname", "launch-window"),
    )
    link.start()
    joined = False
    for _ in range(JOIN_ATTEMPTS):
        joined = link.connect()
        if joined:
            break
    if not joined:
        # The saved credentials are kept. If they are simply stale the portal
        # replaces them; if the router was down, the restart after the portal's
        # timeout tries them again.
        await run_portal(config, led)
        return

    clock.sync_ntp(config.get("ntp_host", "pool.ntp.org"))
    boot_ts = clock.now() if clock.plausible(clock.now()) else None
    beacon = state_mod.Beacon(config, wifi=link, boot_ts=boot_ts)
    beacon.last_sync = boot_ts

    await server_mod.Server(routes_for(beacon)).serve(port=80)

    tasks = [
        asyncio.create_task(refresh_loop(beacon, config, led)),
        asyncio.create_task(signal_loop(beacon, led)),
        asyncio.create_task(clock_loop(beacon, config)),
        asyncio.create_task(link.maintain()),
    ]

    if config.get("watchdog", True):
        # Everything above has now run once without raising; from here on a
        # hang is a fault worth resetting for.
        led.watchdog = machine.WDT(timeout=WATCHDOG_TIMEOUT_MS)

    await asyncio.gather(led_task, *tasks)


try:
    asyncio.run(main())
except KeyboardInterrupt:
    # Ctrl-C at the REPL should leave a usable prompt, not a reset loop.
    machine.Pin("LED", machine.Pin.OUT).off()
    raise
