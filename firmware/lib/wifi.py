"""Station-mode WiFi, with the two settings a Pico W server actually needs.

**Power management off.** The CYW43 defaults to an aggressive sleep mode that
parks the radio between beacons. It saves milliamps that a mains-powered beacon
does not care about, and it costs whole seconds of latency on the first packet
of a connection — which shows up as a status page that takes four seconds to
start loading, or does not load at all before the phone gives up. `pm=0xa11140`
is the documented "performance" value and is the single most important line in
this file.

**Country code set.** It determines the legal channel set; leaving it at the
worldwide default can make the radio ignore the channels an access point is
actually on.

Reconnection is handled by polling rather than by the driver's own retry, so
an outage is visible in the status document instead of being hidden inside the
network stack.
"""

import time

try:
    import network
except ImportError:  # pragma: no cover
    network = None

PERFORMANCE_PM = 0xA11140

# CYW43 link states that mean "stopped trying"; anything else is in progress.
FAILED_STATES = (-1, -2, -3)


class Wifi:
    def __init__(self, ssid, password, country="DE", hostname="launch-window"):
        self.ssid = ssid
        self.password = password
        self.country = country
        self.hostname = hostname
        self.station = None

    def start(self):
        if network is None:
            return
        try:
            network.country(self.country)
        except Exception:
            pass
        try:
            network.hostname(self.hostname)
        except Exception:
            pass
        self.station = network.WLAN(network.STA_IF)
        self.station.active(True)
        try:
            self.station.config(pm=PERFORMANCE_PM)
        except Exception:
            pass

    def connect(self, timeout=25):
        """Associate and wait for an address. Returns True once usable."""
        if self.station is None:
            self.start()
        if self.station is None:
            return False
        if self.connected():
            return True
        self.station.connect(self.ssid, self.password)
        deadline = time.time() + timeout
        while time.time() < deadline:
            status = self.station.status()
            if self.connected():
                return True
            if status in FAILED_STATES:
                return False
            time.sleep(0.5)
        return False

    def connected(self):
        if self.station is None:
            return False
        try:
            return bool(self.station.isconnected()) and self.address() not in (
                None,
                "0.0.0.0",
            )
        except Exception:
            return False

    def address(self):
        try:
            return self.station.ifconfig()[0]
        except Exception:
            return None

    def rssi(self):
        try:
            return self.station.status("rssi")
        except Exception:
            return None

    async def maintain(self, interval=30):
        """Background task: notice a dropped link and re-associate."""
        import asyncio

        while True:
            await asyncio.sleep(interval)
            if not self.connected():
                try:
                    self.station.disconnect()
                except Exception:
                    pass
                self.connect(timeout=20)
