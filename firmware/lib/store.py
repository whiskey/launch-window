"""Reading and writing the beacon's two JSON files.

`config.json` holds the site and the thresholds and belongs in version control.
`wifi.json` holds the network credentials, is written only by the setup portal,
and must never be committed — which is why it is a separate file rather than a
section of the config. There is no way to accidentally publish a secret that
lives in a file the repository does not track.

Writes go through a temporary file and a rename because the power supply here
is a USB socket that a person unplugs without warning. littlefs will not let a
rename clobber an existing name, so the old file is removed first; the window
that opens is a few milliseconds wide and the failure mode is a missing file
rather than a half-written one that parses as valid JSON.
"""

import json

try:
    import os
except ImportError:  # pragma: no cover
    os = None


def load(path, default=None):
    """Parse a JSON file, returning `default` if it is missing or corrupt."""
    try:
        with open(path) as handle:
            return json.load(handle)
    except Exception:
        return default


def save(path, data):
    """Write JSON, replacing any existing file. Returns True on success."""
    temp = path + ".tmp"
    try:
        with open(temp, "w") as handle:
            json.dump(data, handle)
        try:
            os.remove(path)
        except Exception:
            pass  # first write, or nothing there to replace
        os.rename(temp, path)
        return True
    except Exception:
        try:
            os.remove(temp)
        except Exception:
            pass
        return False


def merged(defaults, override):
    """Defaults overlaid with a loaded file, one level deep into dicts.

    One level is enough for this config's shape and keeps the behaviour
    obvious: a user who sets a single threshold keeps the defaults for the
    others, and a user who sets `site` must give the whole site.
    """
    result = dict(defaults)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            merged_value = dict(result[key])
            merged_value.update(value)
            result[key] = merged_value
        else:
            result[key] = value
    return result
