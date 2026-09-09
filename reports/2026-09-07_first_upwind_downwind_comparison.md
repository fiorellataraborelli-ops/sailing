# Race Data Report — First Upwind / First Downwind Leg Analysis

**Date of racing analyzed:** 2026-09-07 (yesterday)
**Scope, per user instruction:** "No one finished the race on purpose" — analysis is restricted to the **first upwind leg** and **first downwind leg** only. Later legs are excluded from this report.

---

## 1. Data sources (source of truth)

| Boat | File | Size | Fully parsed |
|---|---|---|---|
| **Team (our boat)** | `data/raw/team/team_2026-09-07.vkx` (user-uploaded) | 1,549,440 bytes | Yes, 100% |
| TYRA | `data/raw/competitors/TYRA_VAKAROS2_2026-09-07.vkx` (Google Drive) | 5,049,110 bytes | Yes, 100% |
| TUR 442 | `data/raw/competitors/TUR442_07.09.2026.vkx` (Google Drive) | 4,254,478 bytes | Yes, 100% |
| GSpot | `data/raw/competitors/GSpot_7-9-2026.vkx` (Google Drive) | 1,541,402 bytes | Yes, 100% |
| DIVA-NEU | `data/raw/competitors/DIVA-NEU_7.9.2026.vkx` (Google Drive) | 1,421,574 bytes | Yes, 100% |
| noticia | `data/raw/competitors/noticia_9-7-2026.vkx` (Google Drive) | 1,510,107 bytes | Yes, 100% |

All files are Vakaros VKX v1.4 telemetry logs, parsed against the official format spec ([github.com/vakaros/vkx](https://github.com/vakaros/vkx)) with `src/sailing_agents/vkx_parser.py`. Every file parsed to end-of-file with zero unrecognized rows (see `reports/2026-09-07_race_comparison_raw.json`, field `fully_parsed: true` per boat).

Full per-boat detail: `reports/2026-09-07_race_comparison_raw.json`.

## 2. Race start — cross-boat validation

All 6 devices logged an **identical sequence of four RACE_START timer events**, within ~20 ms of each other across boats — strong confirmation this is one shared start sequence for the fleet:

| # | UTC time | Outcome |
|---|---|---|
| 1 | 13:55:00 | General recall — RESET ~2 min later |
| 2 | 14:10:00 | General recall — RESET ~2 min later |
| 3 | 14:35:00 | General recall — RESET ~2 min later |
| 4 | **14:50:00** | **Final valid start — no further RESET logged. Used as t0 for all leg analysis below.** |

Source: `timer_events` (row `0x04`) in each file, event id 3 = RACE_START. Local time (Cascais/Lisbon, WEST, UTC+1) would be 15:50:00.

## 3. Method (documented for repeatability, no wind-sensor input required)

None of the 6 files contain wind-sensor (`0x0A`) or shift-angle (`0x06`) rows — **Data not provided**, so true wind direction, true wind angle, and true-wind-referenced VMG cannot be computed for this session on any boat. All speed/VMG figures below are SOG (speed over ground, GPS-derived) and a **VMG proxy** (straight-line progress along the boat's own leg axis, per unit time) — not true-wind VMG.

Leg boundaries were found from GPS track alone: after t0, the dominant axis of travel is found (principal component of the track), the track is projected onto it, and the first two sustained reversals of that projection (>300 m, confirmed after a 20-minute trend-direction check to reject post-start settling noise) mark the windward-mark rounding (end of leg 1) and the next mark rounding (end of leg 2). Implementation: `src/sailing_agents/race_legs.py`.

## 4. First upwind leg (the beat) — ranked by avg SOG

| Boat | Duration | Avg SOG | Max SOG | Straight-line dist. | VMG proxy | Tacks detected |
|---|---|---|---|---|---|---|
| TYRA | 31.83 min | 5.53 kn | 8.5 kn | 3,770 m | 3.84 kn | 2 |
| DIVA-NEU | 30.16 min | 5.53 kn | 7.7 kn | 3,653 m | 3.92 kn | 3 |
| GSpot | 29.16 min | 5.49 kn | 8.2 kn | 3,654 m | 4.06 kn | 2 |
| noticia | 31.78 min | 5.45 kn | 7.9 kn | 3,764 m | 3.84 kn | 2 |
| TUR 442 | 32.05 min | 5.43 kn | 7.8 kn | 3,722 m | 3.76 kn | 1 |
| **Team (our boat)** | **29.49 min** | **5.23 kn** | **7.5 kn** | **3,645 m** | **4.00 kn** | **6** |

- Team had the **lowest average SOG** of the 6 boats on the beat, but the **2nd-best VMG proxy** (4.00 kn, behind only GSpot's 4.06 kn) — i.e. speed lost tacking was largely offset by sailing a more direct track.
- Team logged **6 tacks**, roughly double-to-sextuple every other tracked boat (1–3 tacks). Each tack costs boatspeed; with 6 tacks Team still matched the fleet's VMG, meaning boat-for-boat pointing/speed in a straight groove was competitive, but the extra maneuvers are the first lever to check (fewer, better-timed tacks would likely lift avg SOG toward the ~5.5 kn the fleet showed).

## 5. First downwind leg (the run) — ranked by avg SOG

| Boat | Duration | Avg SOG | Max SOG | Straight-line dist. | VMG proxy | Gybes detected |
|---|---|---|---|---|---|---|
| TUR 442 | 11.14 min | 11.16 kn | 16.3 kn | 2,548 m | 7.41 kn | 1 |
| TYRA | 12.31 min | 10.80 kn | 16.0 kn | 2,804 m | 7.38 kn | 3 |
| **Team (our boat)** | **14.55 min** | **10.34 kn** | **15.8 kn** | **3,270 m** | **7.28 kn** | **4** |
| GSpot | 14.63 min | 10.12 kn | 16.7 kn | 3,279 m | 7.26 kn | 2 |
| DIVA-NEU | 15.04 min | 9.93 kn | 16.6 kn | 3,258 m | 7.02 kn | 3 |
| noticia | 16.57 min | 9.38 kn | 15.6 kn | 3,258 m | 6.37 kn | 8 |

- Team was mid-pack on the run: 3rd of 6 on both avg SOG and VMG proxy.
- TUR 442 and TYRA's shorter straight-line distance (2,548 m / 2,804 m vs. ~3,260–3,280 m for the rest) suggests they rounded the leeward mark at a different point than the others — worth a course-marks cross-check before reading too much into their faster time (**Data not provided**: no line/mark-position row in any file pins down the actual leeward mark, so this is inferred from where each boat's own track reverses).

## 6. What this data cannot tell you (explicitly)

- **True wind speed/direction, TWA, true VMG** — Data not provided (no `0x0A`/`0x06` rows in any file).
- **Actual race result / fleet placement (the "3/103")** — that figure was provided by the user, not derived from telemetry; it is not cross-checked against these files.
- **Confirmed course/mark identity** — no `0x05` (line/mark position) rows with plausible race-mark coordinates were found tying all 6 boats to the same charted marks; the leg boundaries above are inferred purely from each boat's own track reversal, not from an authoritative mark position.
- **Boat names/sail numbers for competitor files** are taken as given from the Google Drive filenames; not independently verified against a fleet entry list (not provided).

---
*Generated from `src/sailing_agents/` (vkx_parser.py, race_legs.py, report.py) — reusable for today's racing.*
