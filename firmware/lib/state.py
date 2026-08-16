"""The beacon's state: what it knows, how old it is, and what it decides.

This module owns the refresh cycle and assembles the document defined in
`protocol/beacon-v1.md`. It follows the three rules the rig's own status API
set, because a household that already has one status document should not have
to learn a second set of conventions:

**Never present a stale value as current.** The sky half of the document is
recomputed every cycle and is exact. The weather half comes from a network
request that can fail for hours. `data.age_s` dates it, `data.stale` judges it,
and the web page says so in words above the verdict rather than in a subtitle
under it.

**Nulls are honest.** A forecast that has never arrived leaves the verdict
`unknown`, not `no-go`. Those are different statements: one says the sky is
bad, the other says the beacon does not know, and a beacon that resolves its
own ignorance into a confident negative is worse than useless to someone
deciding whether to carry a mount outside.

**Additive changes only within a schema version.**

The last good forecast is cached to flash. After a power cut at 22:00 the
beacon comes back knowing what it knew at 21:30, labelled half an hour old,
instead of knowing nothing — and since the sky half is recomputed from the
clock, a cached night still produces a usable verdict.
"""

import gc

import clock
import sky
import store
import verdict as verdict_mod
import weather

FIRMWARE_VERSION = "1.0.0"
SCHEMA = 1
CACHE_PATH = "cache.json"

# A forecast older than this is called stale on the page and in the document.
# Two hours is chosen against the thing being forecast: hourly cloud fields do
# not meaningfully change faster than that, and a beacon that cried stale after
# twenty minutes of a flaky link would be noise.
STALE_AFTER = 2 * 3600


class Beacon:
    def __init__(self, config, wifi=None, boot_ts=None):
        self.config = config
        self.wifi = wifi
        self.hours = None
        self.fetched_at = None
        self.last_error = None
        self.last_sync = None
        self.boot_ts = boot_ts
        self._cached_from_flash = False
        self._restore()

    # -- site helpers -----------------------------------------------------

    @property
    def site(self):
        return self.config["site"]

    @property
    def tz(self):
        return self.site["timezone"]

    def _local(self, ts):
        return clock.hhmm(ts, self.tz)

    def moon_at(self, ts):
        return (
            sky.moon_altaz(ts, self.site["latitude"], self.site["longitude"])[0],
            sky.moon_illumination(ts),
        )

    # -- forecast ---------------------------------------------------------

    def _restore(self):
        """Reload the last forecast from flash, if one survived the reboot."""
        cached = store.load(CACHE_PATH)
        if cached and cached.get("hours") and cached.get("fetched_at"):
            self.hours = cached["hours"]
            self.fetched_at = cached["fetched_at"]
            self._cached_from_flash = True

    async def refresh(self, now=None):
        """Fetch tonight's forecast. Returns True if new data arrived."""
        now = now or clock.now()
        if not clock.plausible(now):
            self.last_error = "clock not synchronised"
            return False

        night = sky.night(now, self.site["latitude"], self.site["longitude"])
        start = night.get("dusk_nautical") or night.get("sunset") or now
        end = night.get("dawn_nautical") or night.get("sunrise") or (now + 10 * 3600)
        try:
            hours = await weather.fetch(
                self.site["latitude"], self.site["longitude"], start - 3600, end + 3600
            )
        except Exception as exc:
            self.last_error = str(exc)
            return False

        self.hours = hours
        self.fetched_at = now
        self.last_error = None
        self._cached_from_flash = False
        store.save(CACHE_PATH, {"hours": hours, "fetched_at": now})
        gc.collect()
        return True

    # -- document ---------------------------------------------------------

    def assess(self, now=None):
        """Grade the coming night from whatever is currently known."""
        now = now or clock.now()
        night = sky.night(now, self.site["latitude"], self.site["longitude"])
        if not self.hours:
            return night, {
                "state": verdict_mod.STATE_UNKNOWN,
                "score": None,
                "reasons": [self.last_error or "no forecast retrieved yet"],
                "window": None,
                "hours": [],
                # Darkness is computed from the clock, so it is known even with
                # no forecast at all, and must agree with the graded path.
                "darkness": verdict_mod.darkness_of(night),
            }
        return night, verdict_mod.assess(
            self.hours, night, self.moon_at, self.config.get("thresholds")
        )

    def document(self, now=None):
        """The full beacon document — see protocol/beacon-v1.md."""
        now = now or clock.now()
        night, decision = self.assess(now)
        synced = clock.plausible(now)

        age = None if self.fetched_at is None else max(0, int(now - self.fetched_at))
        dark_start = decision.get("dark_start") or night.get("dusk_astronomical")
        dark_end = decision.get("dark_end") or night.get("dawn_astronomical")

        moon_rise_set = sky.moon_events(
            now - 6 * 3600, now + 24 * 3600, self.site["latitude"], self.site["longitude"]
        )
        illumination = sky.moon_illumination(now)
        interferes = any(
            (hour.get("moon_alt_deg") or -90) > 0 for hour in decision.get("hours") or []
        ) and illumination > 0.15

        window = decision.get("window")
        if window:
            window = dict(window)
            window["start_local"] = self._local(window["start"])
            window["end_local"] = self._local(window["end"])
            window["start"] = clock.iso_utc(window["start"])
            window["end"] = clock.iso_utc(window["end"])

        hours_out = []
        for hour in decision.get("hours") or []:
            entry = dict(hour)
            entry["local"] = self._local(hour["ts"])
            entry["time"] = clock.iso_utc(hour["ts"])
            hours_out.append(entry)

        # Uptime is measured against the wall clock, which NTP can move. A step
        # backwards would otherwise publish a negative age; "not measurable" is
        # the truthful answer, and the same one given before the clock is set.
        uptime = None
        if self.boot_ts is not None and now >= self.boot_ts:
            uptime = int(now - self.boot_ts)

        return {
            "schema": SCHEMA,
            "generated_at": clock.iso_utc(now) if synced else None,
            "generated_local": self._local(now) if synced else None,
            "beacon": {
                "host": self.config.get("hostname", "launch-window"),
                "firmware_version": FIRMWARE_VERSION,
                "uptime_s": uptime,
                "uptime": clock.duration(uptime) if uptime is not None else None,
                "core_temp_c": core_temperature(),
                "signal_dbm": self.wifi.rssi() if self.wifi else None,
                "address": self.wifi.address() if self.wifi else None,
            },
            "clock": {
                "synced": synced,
                "last_sync": clock.iso_utc(self.last_sync) if self.last_sync else None,
            },
            "site": {
                "name": self.site.get("name"),
                "latitude": self.site["latitude"],
                "longitude": self.site["longitude"],
                "timezone": self.tz.get("name", "UTC"),
            },
            "night": {
                "darkness": decision.get("darkness"),
                "sunset": clock.iso_utc(night.get("sunset")),
                "sunset_local": self._local(night.get("sunset")),
                "dusk_astronomical": clock.iso_utc(night.get("dusk_astronomical")),
                "dusk_astronomical_local": self._local(night.get("dusk_astronomical")),
                "dawn_astronomical": clock.iso_utc(night.get("dawn_astronomical")),
                "dawn_astronomical_local": self._local(night.get("dawn_astronomical")),
                "sunrise": clock.iso_utc(night.get("sunrise")),
                "sunrise_local": self._local(night.get("sunrise")),
                "dark_seconds": night.get("dark_seconds") or 0,
                "dark_duration": clock.duration(night.get("dark_seconds") or 0),
                "dark_start": clock.iso_utc(dark_start),
                "dark_end": clock.iso_utc(dark_end),
            },
            "moon": {
                "illumination": round(illumination, 3),
                "phase": sky.moon_phase_name(now),
                "altitude_deg": round(
                    sky.moon_altaz(
                        now, self.site["latitude"], self.site["longitude"]
                    )[0],
                    1,
                ),
                "rise": clock.iso_utc(moon_rise_set.get("rise")),
                "rise_local": self._local(moon_rise_set.get("rise")),
                "set": clock.iso_utc(moon_rise_set.get("set")),
                "set_local": self._local(moon_rise_set.get("set")),
                "interferes": interferes,
            },
            "verdict": {
                "state": decision.get("state"),
                "score": decision.get("score"),
                "reasons": decision.get("reasons") or [],
                "window": window,
                "hours": hours_out,
            },
            "data": {
                "source": "open-meteo",
                "fetched_at": clock.iso_utc(self.fetched_at),
                "age_s": age,
                "age": clock.duration(age) if age is not None else None,
                "stale": age is None or age > STALE_AFTER,
                "from_flash_cache": self._cached_from_flash,
                "error": self.last_error,
            },
        }

    # -- signalling -------------------------------------------------------

    def led_pattern(self, now=None):
        """Which LED pattern the current state calls for."""
        now = now or clock.now()
        if self.wifi is not None and not self.wifi.connected():
            return "connecting"
        if not clock.plausible(now):
            return "unknown"
        _, decision = self.assess(now)
        return decision.get("state") or "unknown"

    def is_night(self, now=None):
        """True once the Sun is down — the LED shortens its on-times then."""
        now = now or clock.now()
        if not clock.plausible(now):
            return False
        altitude, _ = sky.sun_altaz(
            now, self.site["latitude"], self.site["longitude"]
        )
        return altitude < 0


def core_temperature():
    """RP2040 die temperature in Celsius, or None where there is no ADC.

    This is the chip, not the air: it reads several degrees above ambient and
    is published as a health signal, not as weather. The document keeps it
    under `beacon`, never under `night`, so it cannot be mistaken for one.
    """
    try:
        import machine

        raw = machine.ADC(4).read_u16() * 3.3 / 65535
        return round(27 - (raw - 0.706) / 0.001721, 1)
    except Exception:
        return None
