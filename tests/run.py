#!/usr/bin/env python3
"""Run the whole host-side suite.

    python3 tests/run.py            (exit 0 = all passed)
    python3 tests/run.py -v         individual test names

Needs nothing installed. The pyephem comparisons in `test_sky.py` skip
themselves when it is absent, and the report says how many skipped so a clean
run on a bare machine cannot be mistaken for a complete one.

What this suite cannot do is run the firmware on 32-bit floats. That gap is
covered by `tools/verify-device.py`, which needs the board plugged in.
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "firmware", "lib"))
sys.path.insert(0, HERE)


def main() -> int:
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for name in sorted(os.listdir(HERE)):
        if name.startswith("test_") and name.endswith(".py"):
            module = __import__(name[:-3])
            suite.addTests(loader.loadTestsFromModule(module))

    verbosity = 2 if "-v" in sys.argv else 1
    result = unittest.TextTestRunner(verbosity=verbosity).run(suite)

    if result.skipped:
        print("\n%d skipped:" % len(result.skipped))
        for test, reason in result.skipped:
            print("  %s — %s" % (test, reason))
        print(
            "\nInstall pyephem in a throwaway virtualenv to run the ephemeris\n"
            "comparisons:  python3 -m venv /tmp/ephem && /tmp/ephem/bin/pip install ephem\n"
            "              /tmp/ephem/bin/python tests/run.py"
        )
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
