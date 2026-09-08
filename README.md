# Sailing Race Data Agents

Tools that parse Vakaros VKX GPS/telemetry logs and turn them into race-leg
performance data — built to analyze yesterday's practice/first race and to
keep running as today's live racing produces new files.

## What's here

- `src/sailing_agents/vkx_parser.py` — full parser for the Vakaros VKX v1.4
  binary log format ([spec](https://github.com/vakaros/vkx)): GPS fixes,
  race timer events (start/reset/race start), line position, tack/shift
  angle, wind, speed-through-water, depth, temperature, load.
- `src/sailing_agents/race_legs.py` — finds the real race start (last
  `RACE_START` event — rejects general recalls/postponements) and segments
  the **first upwind** and **first downwind** legs from the GPS track alone
  (no wind sensor required). See the module docstring for the method.
- `src/sailing_agents/report.py` — CLI: `python3 -m src.sailing_agents.report <file.vkx> [--json]`
  prints/exports leg duration, distance, avg/max SOG, a VMG proxy, and a
  crude tack/gybe count for a single file.

## Data

- `data/raw/team/` — the team's own boat, from the uploaded VKX file.
- `data/raw/competitors/` — 5 competitor boats' tracks for the same race
  (TYRA, TUR 442, GSpot, DIVA-NEU, noticia), pulled from the shared Google
  Drive folder for cross-boat comparison.

## Reports

- `reports/2026-09-07_first_upwind_downwind_comparison.md` — yesterday's
  first-upwind/first-downwind comparison across all 6 boats (per user
  instruction: no one finished that race on purpose, so only the first two
  legs are analyzed).
- `reports/2026-09-07_race_comparison_raw.json` — the underlying per-boat
  JSON output of `report.py` for all 6 boats.

## Known limitations (be explicit about these before drawing conclusions)

- No boat in this dataset logged wind-sensor (`0x0A`) or shift-angle
  (`0x06`) rows, so true wind speed/direction/TWA/true-VMG cannot be
  computed — only GPS speed-over-ground and a track-relative VMG proxy.
- Leg boundaries are inferred purely from each boat's own GPS track
  (a principal-axis projection + reversal detection), not from an
  authoritative mark position, since no reliable mark-position rows were
  present.

## Running it on today's files

```
python3 -m src.sailing_agents.report path/to/new_track.vkx
```

Drop new competitor files into `data/raw/competitors/` (or team files into
`data/raw/team/`) and re-run per file; there's no cross-file state, so any
number of boats/races can be processed independently and compared the same
way as the report above.
