"""The single green LED, and the language it speaks.

A Pico W's onboard LED hangs off the wireless chip rather than an RP2040 pin,
so it cannot be dimmed: `machine.PWM` does not reach it. Everything the beacon
says across the room it says in on and off times, which is why the patterns are
built to be told apart at a glance rather than to be pretty.

The vocabulary, chosen so that the states a person cares about are the calm
ones and the states that need a human are the busy ones:

    GO          one long 1.5 s pulse every 3 s      unmistakable from a doorway
    MARGINAL    two short blinks every 3 s          "there is a window, read it"
    NO-GO       one 60 ms blip every 5 s            alive, and almost invisible
    UNKNOWN     three short blinks every 3 s        forecast missing or stale
    CONNECTING  4 Hz blink                          transient, seconds only
    SETUP       1 Hz half-on blink                  the AP is up, come and configure
    FAULT       rapid triple every 1.5 s            something needs a human

Night courtesy: after sunset the on-times shrink to a third. A green LED at
full duty in a dark room costs an observer their dark adaptation, and this
device exists to serve people who care about exactly that. The off-times are
untouched, so the rhythm — which is what carries the meaning — stays the same.
"""

try:
    import machine
except ImportError:  # pragma: no cover - host-side tests
    machine = None

# Durations in milliseconds, alternating on, off, on, off, ...
PATTERNS = {
    "go": (1500, 1500),
    "marginal": (120, 220, 120, 2540),
    "no-go": (60, 4940),
    "unknown": (110, 190, 110, 190, 110, 2290),
    "connecting": (125, 125),
    "setup": (500, 500),
    "fault": (70, 90, 70, 90, 70, 1110),
    "boot": (60, 60, 60, 60, 60, 60),
    "off": (0, 1000),
}

NIGHT_DUTY = 0.33


class Led:
    """Plays a named pattern until told otherwise.

    The player is the beacon's most reliable heartbeat — it ticks every few
    hundred milliseconds no matter what the network is doing — so it is also
    where the watchdog gets fed. If this loop stops, the board deserves to be
    reset.
    """

    def __init__(self, pin="LED", watchdog=None):
        self.pin = machine.Pin(pin, machine.Pin.OUT) if machine else None
        self.watchdog = watchdog
        self.pattern = "boot"
        self.night = False
        self._sequence = PATTERNS["boot"]
        self._index = 0

    def set(self, pattern):
        """Switch pattern, restarting the sequence so the change is visible."""
        if pattern not in PATTERNS:
            pattern = "fault"
        if pattern != self.pattern:
            self.pattern = pattern
            self._sequence = PATTERNS[pattern]
            self._index = 0

    def set_night(self, is_night):
        self.night = bool(is_night)

    def _step(self):
        """Next (level, duration_ms) in the sequence."""
        duration = self._sequence[self._index]
        level = 1 - (self._index % 2)  # even index = on
        self._index = (self._index + 1) % len(self._sequence)
        if level and self.night:
            duration = max(20, int(duration * NIGHT_DUTY))
        return level, duration

    def apply(self, level):
        if self.pin is not None:
            self.pin.value(level)

    async def run(self):
        import asyncio

        while True:
            level, duration = self._step()
            self.apply(level if duration else 0)
            if self.watchdog is not None:
                self.watchdog.feed()
            # Sleep in slices so the watchdog keeps getting fed through a 5 s
            # off-phase, and so a state change interrupts that phase instead of
            # waiting it out — the beacon should react when the answer changes.
            playing = self.pattern
            remaining = duration
            while remaining > 0 and self.pattern == playing:
                slice_ms = min(250, remaining)
                await asyncio.sleep_ms(slice_ms)
                remaining -= slice_ms
                if self.watchdog is not None:
                    self.watchdog.feed()
