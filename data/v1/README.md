# Cascais 2026 — race analysis dataset (v1)

J/70 World Championship 2026, Cascais — race analysis from Vakaros Atlas telemetry

Generated 2026-09-11T08:59:01Z. Every file here is a projection of the same analysis the live page renders, so the two cannot disagree. Rebuild with `python3 tools/export_data.py` and `python3 tools/export_tracks.py`.

## Conventions

- **time** — UTC throughout, ISO 8601 with a trailing Z
- **speed** — knots unless a field says otherwise
- **bearings** — degrees true, 0-360
- **wind_direction** — the direction the wind is coming FROM
- **null** — means no data. It never means zero, and no file substitutes one for the other
- **boat_names** — as written on the log file, with a small alias map applied; the same string is used as the join key across every file

## Files

| Dataset | Rows | JSON | CSV | What it is |
|---|---:|---|---|---|
| `meta` |  | `meta.json` | — | Venue, calibrated model bias, tacking angle, event dates and telemetry coverage. |
| `fleet` | 61 | `fleet.json` | `fleet.csv` | One row per decoded .vkx log: session extent, fix count, distance and speed splits. |
| `legs` | 424 | `legs.json` | `legs.csv` | Wind-referenced VMG per boat per leg, plus the correlations between each variable and first-beat VMG across the tracked fleet. |
| `races` | 25 | `races.json` | `races.csv` | Mark timings, speed splits and start-line position per boat per race, with the race header (gun, line length and bearing, measured wind) alongside. |
| `segments` | 30 | `segments.json` | `segments.csv` | Maximum speed held over rolling windows, 9 Sep. Transcribed from the event's published table; the hold ratio and ranks are derived here. |
| `kpi` | 6 | `kpi.json` | `kpi.csv` | Top five and the client boat joined across scored results, the segment table and VMG from the logs. Nulls mean no data, never zero. |
| `official` | 6 | `official.json` | `official.csv` | Scored standings, not derived from telemetry. |
| `wind` | 16 | `wind.json` | `wind.csv` | Three-model consensus at the race area, hourly 11:00-18:00 UTC, refreshed every three hours. Raw and bias-corrected direction side by side. |
| `bias` | 6 | `bias.json` | `bias.csv` | GRIB forecast against wind measured on the water, per race. This is where the +16.1 deg correction comes from, and it is not a constant. |
| `startline` | 6 | `startline.json` | `startline.csv` | Line geometry per race, with the event's published advantage beside the one our own formula produces from the geometry alone. |
| `wind_by_leg` | 6 | `wind_by_leg.json` | `wind_by_leg.csv` | Wind bearing measured on each leg of each race by the event. |
| `daycompare` | 4 | `daycompare.json` | `daycompare.csv` | Boats with a log on both 8 and 9 Sep — same hulls, same crews, different breeze. |
| `coach` |  | `coach.json` | — | Coaching notes, transcribed. Not measured, and labelled as such. |
| `brief` |  | `brief.json` | — | The analysis requirements, with what is validated and what is open. |
| `tracks` | 106 | `tracks/index.json` | — | Position, SOG, COG and leg index at 2 s for every boat in races 1 and 2, one columnar file per boat per race, plus estimated mark positions. This is what a course plan view or a polar scatter is drawn from. |

## Field dictionary

### `fleet`

| Field | Meaning |
|---|---|
| `file` | Log file, named for the boat |
| `day` | Date of the session (UTC) |
| `t0` | First fix, UTC |
| `t1` | Last fix, UTC |
| `fixes` | Number of position fixes |
| `nm` | Distance sailed, nautical miles |
| `mx` | Peak SOG, knots |
| `avg` | Mean SOG over the whole session, knots |
| `upAvg` | Mean SOG below 8 kn (treated as upwind), knots |
| `dnAvg` | Mean SOG at or above 8 kn (treated as downwind), knots |

### `legs`

| Field | Meaning |
|---|---|
| `race` | Race number |
| `boat` | Boat |
| `n` | Leg number, 1-4 |
| `kind` | beat (upwind) or run (downwind) |
| `wind` | Wind on this leg as measured by the event, degrees true |
| `min` | Leg duration, minutes |
| `sog` | Mean speed over ground, knots |
| `vmg` | Mean wind-referenced VMG, knots — the component of boat speed along the wind axis |
| `twa` | Mean true wind angle, degrees off the wind |
| `eff` | VMG divided by SOG (definitional, not an independent measure) |
| `svmg` | Mean VMG over the fixes outside a manoeuvre, knots — boat speed with turning removed, so a boat that manoeuvres more is not measured as slower for it |
| `ssog` | Mean SOG over the same fixes, knots |
| `stwa` | Mean true wind angle over the same fixes, degrees |
| `keep` | Share of the leg's fixes left after removing the manoeuvre windows (-10 s to +15 s around a tack, -10 s to +20 s around a gybe) |
| `extra` | Distance sailed beyond the straight line, metres |
| `tacks` | Settled tacks |
| `gybes` | Settled gybes |
| `tloss` | Mean speed lost per tack, knots |
| `gloss` | Mean speed lost per gybe, knots |

### `races`

| Field | Meaning |
|---|---|
| `race` | Race number |
| `boat` | Boat |
| `m0` | Cumulative minutes at mark 1 |
| `m1` | Cumulative minutes at mark 2 |
| `m2` | Cumulative minutes at mark 3 |
| `up` | Mean upwind SOG, knots |
| `dn` | Mean downwind SOG, knots |
| `ex` | Extra distance sailed over the race, metres |
| `tk` | Tacks |
| `dl` | Distance to the start line at the gun, metres (negative = over) |
| `al` | Position along the line, 0 = pin, 1 = committee boat |

### `segments`

| Field | Meaning |
|---|---|
| `boat` | Boat |
| `s0` | Instantaneous peak speed, knots |
| `s5` | Best speed held 5 s, knots |
| `s10` | Best speed held 10 s, knots |
| `s20` | Best speed held 20 s, knots |
| `s30` | Best speed held 30 s, knots |
| `s60` | Best speed held 60 s, knots |
| `hold` | The 60 s figure divided by the peak — how much of the headline number survives a minute |
| `rank0` | Rank on peak |
| `rank60` | Rank on the 60 s figure |
| `rankhold` | Rank on hold |

### `kpi`

| Field | Meaning |
|---|---|
| `boat` | Boat |
| `pos` | Overall position |
| `pts` | Total points — no discard has been applied at four races |
| `team` | True for the client boat |
| `gain` | Places won between the first windward mark and the finish, summed over races |
| `peak` | Instantaneous peak speed on 9 Sep, knots |
| `s60` | Best speed held 60 s on 9 Sep, knots |
| `hold` | Hold ratio |
| `vmg` | Mean upwind VMG from this boat's own log, knots |
| `twa` | Mean upwind true wind angle, degrees |
| `svmg` | The same VMG with every tack cut out of the average, knots |

### `official`

| Field | Meaning |
|---|---|
| `pos` | Overall position |
| `sail` | Sail number |
| `boat` | Boat |
| `pts` | Net points — the total with the worst race discarded |
| `total` | Total points before the discard |
| `discard` | Which race is discarded, 1-based |
| `r` | Finishing position in each race |
| `codes` | Scoring code per race where one applies (DNC, DNF, DSQ, PRP), else null |
| `gain` | Places won after the first windward mark, races 1-4 only |

### `wind`

| Field | Meaning |
|---|---|
| `date` | Forecast date |
| `hr` | Hour, UTC |
| `raw` | Model consensus wind direction, degrees true |
| `cor` | Direction after the +16.1 deg fleet-measured bias, degrees true; null when not trusted |
| `sp` | Spread between the three models, degrees |
| `kn` | Wind speed, knots |
| `gust` | Gust, knots |
| `mslp` | Pressure, hPa |
| `trust` | False below 8 kn or above 30 deg of spread — the bias is not applied there |

### `bias`

| Field | Meaning |
|---|---|
| `race` | Race number |
| `forecast` | GRIB direction at the first beat, degrees true |
| `measured` | Direction measured on the water, degrees true |
| `bias` | Forecast minus measured, degrees |
| `old_observed` | An earlier, superseded observation, kept for audit |
| `old_bias` | The error that earlier observation produced |

### `startline`

| Field | Meaning |
|---|---|
| `race` | Race number |
| `setting` | Direction the committee set the line to, degrees true |
| `line_m` | Line length, metres |
| `bias_deg` | Line bias, degrees off square |
| `bias_m` | Advantage to the favoured end, metres, as the event published it |
| `calc_m` | The same advantage from our own geometry: line_m x sin(bias_deg) |
| `favoured` | Favoured end |

### `wind_by_leg`

| Field | Meaning |
|---|---|
| `race` | Race number |
| `uw1` | First upwind, degrees true |
| `dw1` | First downwind, degrees true |
| `uw2` | Second upwind, degrees true |
| `dw2` | Second downwind, degrees true |

### `tracks`

| Field | Meaning |
|---|---|
| `t` | seconds since start_utc |
| `lat` | degrees |
| `lon` | degrees |
| `sog` | knots |
| `cog` | degrees true |
| `leg` | 1-4, 0 outside a leg |

## Joining

`boat` is the join key everywhere. `race` is 1-3 for 8 September; race 4 (9 September) is scored but has no published wind or bias analysis, so it appears in `official` and not in `legs`, `races`, `bias` or `startline`.

## What is measured and what is inferred

- **Measured by the instrument** — position, SOG, COG, and the committee/pin line positions the Atlas recorded.
- **Derived here** — VMG, TWA, leg segmentation, manoeuvre counts and costs, extra distance, hold ratios, and the model bias.
- **Taken from the event** — scored results, measured leg winds, published line bias, and the 9 September speed segment table.
- **Not available at all** — true wind from any boat (no instrument logged one) and recorded mark roundings. Mark positions in `tracks/index.json` are the median leg boundary across the fleet, with the spread quoted, and are estimates.
