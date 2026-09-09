# What the race analysis must cover

Requirements as set by the team, 9 September 2026. The regatta runs to Friday
11 September and new competitor logs arrive daily through the shared Google Drive
folder `Sailing` (id `1IYNZ3gopcq7Wjr7lT9Ob6ajs0DiaBuQn`).

**Client: the Swedish team.** Their boat is `Team Sweden (Roman)`, the `vakaros *.vkx` logs.

## 1. Start analysis
- Distance to gun
- Time to gun
- Speed at gun
- Angle at gun

## 2. Leg analysis — four legs and two offsets per race
- Boat speed
- **Boat VMG — most important**
- Tacks / gybes
- Tack loss per tack
- Gybe loss per gybe
- Best moments
- Worst moments
- Places gained / lost per leg

## 3. Race analysis
- Overall strategy: boat position against wind shifts
- Choice of downwind mark, left or right — the coach reports the right-hand gate came out
  considerably further upwind with the left shift at the bottom; see `COACH-NOTES.md`
- Whatever else a full J/70 Worlds race analysis should carry
- Official start list and results
- **Course and course markers, GPS position of the roundings**

## Status

Done and validated:
- VKX decoder; all 25 logs parse byte-exact to EOF
- Start-line geometry — line length agrees with the event reports to within 3 m
- Start-line bias — 6°/107 m and 12°/206 m, pin favoured both races; our formula
  reproduces both within 2%
- Model bias recalibrated to +18.6° against measured wind, with a light-air guard
- Wind outlook to Friday, three-model consensus, refreshed three-hourly

**Not done — and one active defect:**

> A separate leg-splitting script was written and **failed** — it returned identical
> first-leg durations (42.13 min) for all 13 boats, which is a search-band boundary
> being hit, not the boats agreeing. It has been deleted rather than left in the tree,
> because `src/sailing_agents/race_multi_leg.py` already does this properly, by track
> reversal, and produced the reports in `reports/`. Two lessons from the failure are
> worth keeping:
>
> - Anchor on the **last** `RACE_START` event, not the first. `race_legs.py`
>   already does this; the ad-hoc script did not, and every leg was offset by the
>   ~30 minutes between the recalled sequence and the actual gun.
> - Classify a tack against a gybe by the **point of sail either side of the
>   crossing**, not by the instantaneous heading at the crossing, which is always
>   near the wind axis and so always reads as a tack.
>
> What remains genuinely missing is **wind-referenced VMG**: `_leg_stats` reports
> `vmg_proxy_kn`, a straight-line rate. `race_multi_leg.analyse()` already accepts a
> `wind_deg` argument, and the measured per-leg winds are now known (race 1:
> 317/323/313/317; race 2: 314/321/313/313), so this is a matter of feeding them
> through and computing the true along-wind speed component.

Also outstanding:
- Per-leg VMG, best/worst moments, places gained per leg (blocked on the above)
- The two offsets are not separated out
- Official start list and finishing positions — not yet pulled. Positions shown are
  order at the last rounding, which is not finishing order; the final leg is excluded
  because the loggers' RACE_END is synced fleet-wide and so is not a finish signal
- Course and mark GPS — marks are inferred from track reversals, so extra-distance
  figures carry unknown error
- Heel and pitch — the quaternion is present and clean, never converted
- 20 of the 34 boats have no telemetry. `MidlifeCrisis` (the `MLC USA 26 primary`
  file) logs at ~10 Hz, the best in the fleet, and is in no analysis yet. `ToNessa`
  is in this repo but never reached the Drive folder
- A ~30 minute discrepancy between the loggers' race timers and the event's stated
  start time. The mark *durations* reconcile; the gun *label* did not. Race 1 ran
  12:34:52 → 13:50:41 UTC

## How the model improves

The +18.6° correction rests on two races on one day. A headland bend is unlikely to be
a constant offset — it should vary with gradient direction and strength. Each new race
day, recompute it: raw GRIB direction at the midpoint of the first beat, minus the mean
of the event report's "Wind setting" and its 1st-upwind direction. Enough days turns a
single number into a calibration curve, which is the single largest available gain in
accuracy short of putting a wind instrument on the boat.

The boats already carry the plumbing: TUR 442 and TYRA feed NMEA speed-through-water,
depth and water temperature into the Atlas. A masthead wind feed on that same bus would
give true TWD and TWS at 1 Hz and retire the correction entirely.
