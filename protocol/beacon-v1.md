# Beacon API — version 1

What the beacon serves, and the rules it holds itself to. Machine-readable schema:
[`beacon-v1.schema.json`](beacon-v1.schema.json).

- Base path: `/api/v1`
- Content type: `application/json; charset=utf-8`

The conventions are lifted deliberately from the rig's own `status-v1`. A household with two
status documents should not have to learn two sets of rules, and these three are the ones worth
copying.

## Design rules

**Never present a stale value as current.** The document has two halves with very different
lifetimes. The sky half — darkness, moonrise, illumination — is recomputed from the clock on
every request and is exact. The weather half comes from a network request that can fail for
hours. `data.age_s` dates it, `data.stale` judges it, and the web page says so in a banner above
the verdict rather than in small print below it.

**Nulls are honest.** A forecast that never arrived leaves `verdict.state` at `unknown`, not at
`no-go`. Those are different statements: one says the sky is bad, the other says the beacon does
not know. A beacon that resolves its own ignorance into a confident negative is worse than
useless to someone deciding whether to carry a mount outside in the cold.

The same applies to darkness. At 52 degrees north there is no astronomical night for several
weeks around midsummer, so `night.dusk_astronomical` is `null` then and `night.darkness` says
`nautical` to report which definition the grading actually used.

**Additive changes only within a version.** New fields may appear at any time; clients must
ignore unknown ones. Removing or retyping a field requires `/api/v2`.

## Endpoints

### `GET /api/v1/beacon`

The full document. See the schema; an example follows.

### `GET /api/v1/health`

Cheap liveness check that computes nothing. `{"ok": true, "schema": 1}`.

### `POST /api/v1/refresh`

Fetches the forecast immediately instead of waiting for the next interval. Returns
`{"ok": true, "action": "refresh"}` as soon as the fetch is scheduled, not when it completes —
poll `data.fetched_at` to see it land. `GET` is a 405: refreshing costs an upstream API call, so
it must not be something a link preview or a crawler can trigger.

### `GET /`

The human page. Red on black, because its readers are dark-adapted; `?theme=day` for the
conventional version.

## How the verdict is reached

Every forecast hour overlapping the dark window is graded from 0 to 100. The verdict then comes
from the **longest run of usable hours**, not from the average over the night — four clear hours
after a cloudy evening is a session, and a night that sits flat at 60 all the way through is a
wasted setup.

| State | Meaning |
|---|---|
| `go` | A run of at least 2 h at or above the usable score, averaging 70 or better |
| `marginal` | A run of at least 1 h — worth a look, not worth a drive |
| `no-go` | Nothing that long, or vetoed outright |
| `unknown` | No forecast, or no night at this date. Not a judgement about the sky |

Vetoes are absolute regardless of everything else: rain probability at or above 40 %, gusts at
or above 40 km/h, cloud cover at or above 90 %. The weights behind the rest, and the reasoning
for each, are documented in `firmware/lib/verdict.py`.

## Example

```json
{
  "schema": 1,
  "generated_at": "2026-08-16T20:11:04Z",
  "generated_local": "22:11",
  "beacon": {
    "host": "launch-window",
    "firmware_version": "1.0.0",
    "uptime_s": 45231,
    "uptime": "12 h 33 min",
    "core_temp_c": 28.4,
    "signal_dbm": -47,
    "address": "10.1.10.84"
  },
  "clock": { "synced": true, "last_sync": "2026-08-16T08:00:12Z" },
  "site": {
    "name": "Garden",
    "latitude": 52.52,
    "longitude": 13.4,
    "timezone": "Europe/Berlin"
  },
  "night": {
    "darkness": "astronomical",
    "sunset": "2026-08-16T18:29:52Z",
    "sunset_local": "20:29",
    "dusk_astronomical": "2026-08-16T20:57:25Z",
    "dusk_astronomical_local": "22:57",
    "dawn_astronomical": "2026-08-17T01:24:24Z",
    "dawn_astronomical_local": "03:24",
    "sunrise": "2026-08-17T03:52:02Z",
    "sunrise_local": "05:52",
    "dark_seconds": 15959,
    "dark_duration": "4 h 25 min",
    "dark_start": "2026-08-16T20:57:25Z",
    "dark_end": "2026-08-17T01:24:24Z"
  },
  "moon": {
    "illumination": 0.196,
    "phase": "waxing crescent",
    "altitude_deg": -12.4,
    "rise": "2026-08-16T10:02:11Z",
    "rise_local": "12:02",
    "set": "2026-08-16T19:34:48Z",
    "set_local": "21:34",
    "interferes": false
  },
  "verdict": {
    "state": "no-go",
    "score": 12.6,
    "reasons": [
      "best stretch is 0.4 h, below the 1.0 h worth setting up for",
      "overcast for 5 of 6 dark hours",
      "cloud cover averaging 88 %"
    ],
    "window": null,
    "hours": [
      {
        "ts": 1786914000,
        "time": "2026-08-16T21:00:00Z",
        "local": "23:00",
        "score": 0.0,
        "penalties": { "cloud": 85.0 },
        "veto": "overcast (100 %)",
        "moon_alt_deg": -14.6,
        "cloud_cover": 100,
        "cloud_cover_high": 100,
        "wind_gusts_10m": 5.4,
        "temperature_2m": 21.7,
        "dew_point_2m": 12.5,
        "precipitation_probability": 0
      }
    ]
  },
  "data": {
    "source": "open-meteo",
    "fetched_at": "2026-08-16T20:00:31Z",
    "age_s": 633,
    "age": "10 min",
    "stale": false,
    "from_flash_cache": false,
    "error": null
  }
}
```
