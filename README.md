# Sailing — Cascais J/70 Worlds 2026

Race analysis for the **Swedish team** at the J/70 World Championship, Cascais,
September 2026. Two halves:

- **`src/sailing_agents/`** — the analysis pipeline. Parses Vakaros VKX telemetry
  and turns it into per-leg performance data.
- **`index.html`** — the brief the team reads. Static, self-updating, deployed on
  Vercel from this branch.

New competitor logs arrive daily through the shared Google Drive folder `Sailing`
(id `1IYNZ3gopcq7Wjr7lT9Ob6ajs0DiaBuQn`). The regatta runs to Friday 11 September.

---

## The brief (`index.html`)

Open it directly — no server needed. Wind is loaded at runtime, newest source first:

1. `data/wind.json` — refreshed every three hours by GitHub Actions
2. Open-Meteo direct — live, when the host allows the call
3. the snapshot embedded in the file — always works, may be stale

The page names its source under the day tabs, so you can always see how fresh it is.

### Deploy on Vercel

vercel.com → *Add New* → *Project* → *Import Git Repository* → `sailing`.
Connect it to **`main`**. There is no build step:

| Setting | Value |
|---|---|
| Framework Preset | **Other** |
| Build Command | *leave empty* |
| Output Directory | `.` |
| Install Command | *leave empty* |

`vercel.json` sets the cache and robots headers. Vercel redeploys on every push,
including the three-hourly wind commits, so the site refreshes itself.

**Protect it.** This is client race data. *Project → Settings → Deployment
Protection* → **Vercel Authentication**, or **Password Protection** on Pro. Note
that every push also mints its own preview URL, public unless protection is on.
`robots.txt` and the `X-Robots-Tag` header keep the site out of search engines,
but neither is access control.

### The three-hourly refresh

`.github/workflows/wind-refresh.yml` runs `tools/fetch_wind.py`, writes
`data/wind.json`, and commits only when the forecast has actually moved. It runs on
GitHub's servers, so nothing needs to be open locally. Trigger it by hand from
**Actions → Wind refresh → Run workflow**. If its push is rejected, enable
**Settings → Actions → General → Workflow permissions → Read and write**.

---

## The analysis pipeline

- `src/sailing_agents/vkx_parser.py` — the canonical VKX reader, written against the
  [published format spec](https://github.com/vakaros/vkx): GPS fixes, race timer
  events, line position, shift angle, wind, speed-through-water, depth, temperature,
  load.
- `src/sailing_agents/race_legs.py` — finds the **real** race start and segments the
  first upwind and downwind legs from the GPS track alone.
- `src/sailing_agents/race_multi_leg.py` — full multi-leg segmentation by track
  reversal; per-leg duration, distance, average and max SOG, and a VMG *proxy*.
- `src/sailing_agents/start_line.py`, `start_line_report.py` — start-line geometry
  from the VKX line-position rows: line length, bearing, distance to line at the gun,
  position along the line.
- `src/sailing_agents/wind_grib.py` — GRIB decoding for ICON-EU and ECMWF.
- `src/sailing_agents/fleet_report.py`, `digest.py`, `regatta_data.py` — fleet
  aggregation and the data the dashboard reads.
- `tools/fetch_wind.py` — builds `data/wind.json`. Standalone; imports nothing above.

Reports live in `reports/`. `docs/Cascais-Debrief-8-Sep.pdf` is the shareable debrief.

### Finding the race start

Vakaros logs a `RACE_START` **every time a start sequence reaches zero**, including
general recalls. `find_final_race_start` therefore takes the *last* one. This matters:
on 8 September the loggers recorded a sequence expiring at 13:05 local while the race
actually got away at 13:34:52 — roughly half an hour apart. Anchor on the wrong event
and every "at the gun" figure is measured at the wrong instant.

### The wind bias correction

The GRIB sits **+18.6° to the right** of the wind this fleet actually races in,
measured against the event's own race reports (+19.1° in race 1, +18.0° in race 2 on
8 September). The Nortada bends left into Cascais Bay and a 7 km grid cell cannot
resolve it.

**Only valid in a 10–14 kn gradient Nortada.** Both `tools/fetch_wind.py` and the page
withhold a corrected bearing below 8 kn or above 30° of inter-model spread, because a
thermally driven light day bends differently. Friday 11 September is exactly that case —
2–8 kn with up to 111° of model disagreement — so the page shows a dash rather than a
false bearing. Recalibrate as more races are sailed; see `docs/ANALYSIS-BRIEF.md`.

---

## Known limitations

State these before drawing conclusions.

- **No boat logs a wind instrument.** Every measured bearing comes from GPS geometry or
  the event's own analysis, and no measured wind *speed* exists at all. TUR 442 and TYRA
  already feed NMEA speed-through-water, depth and temperature into the Atlas — a
  masthead feed on that bus would retire the correction entirely.
- **True wind-referenced VMG is not computed yet.** `vmg_proxy_kn` is straight-line
  progress per unit time, not VMG. The team ranks this the most important metric.
- **Mark positions are inferred** from track reversals, not recorded, so extra-distance
  figures carry unknown error.
- **No official finishing positions.** Order shown is at the last rounding. The final
  leg is excluded because the loggers' RACE_END is synced fleet-wide and so is not a
  finish signal.
- **20 of the 34 boats have no telemetry.** Every fleet-relative figure is a 14-boat
  sample. `MidlifeCrisis` (the `MLC USA 26 primary` file) logs at ~10 Hz — the best in
  the fleet — and is in no analysis yet.
- **Heel and pitch** are derivable from the orientation quaternion, and never computed.
- **No boat identity inside a `.vkx` file** — no name, sail number or serial. Identity
  comes only from the filename. Team Sweden is `data/raw/team/team_*.vkx`, confirmed by
  byte-size match and cross-checked on max boat speed.
