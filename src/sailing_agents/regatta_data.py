"""Generate the dashboard's chart data resource (`regattaData`) for one race day.

The Claude Design dashboard does not read the JSON reports. Its KPI cards, the
speed-vs-time chart, the start track map and the per-start metric table all come
from a single ES module bundled as the `regattaData` external resource:

    export const DATA = {session, boats, starts}

That resource shipped with the 7 September session baked in. This module
regenerates it, in exactly the same schema, from the VKX files of any day, so
the page can be pointed at a different day's racing without touching the
template's rendering code.

Three decisions worth knowing about, because they are not recoverable from
looking at the output:

1. **Everything is measured over the racing window**, first RACE_START to last
   RACE_END, not over the whole logged file. The files run about five hours and
   include the tow out and the sail home; a "max speed" taken over that is a
   motoring number, not a racing one.

2. **Wind direction is per race, not per day.** No boat logged a wind
   instrument, so the true wind angle used to split upwind from downwind is the
   fleet's own first-beat bearing for that race, which is the most direct
   observation of where the wind actually was. On 8 September the two races
   differ by 6.4 degrees, enough to move samples across the upwind/downwind
   boundary, so using one figure for the day would misclassify the second race.

3. **Manoeuvres are detected from speed dips**, with the same detector the leg
   segmenter uses, and are then labelled tack or gybe by the point of sail at
   the time. Upwind tack counts are reliable. Downwind gybe counts over-count,
   because a surfing boat's speed oscillates through the same threshold; the
   dashboard shows them, so this caveat travels with them.

Usage:
    PYTHONPATH=src python3 -m sailing_agents.regatta_data \
        --team data/raw/team/team_2026-09-08.vkx \
        --competitors 'data/raw/competitors_2026-09-08/*.vkx' \
        --fleet-report reports/2026-09-08_fleet_report.json \
        --out dashboard/regatta_data.js
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import math
import os
import sys

from .race_legs import KNOTS_PER_MS, haversine_m
from .race_multi_leg import race_windows
from .vkx_parser import VkxLog, parse_file

VENUE = "Cascais, Portugal"
TEAM_NAME = "Team Sweden (Roman)"
TEAM_KEY = "roman"

# Track sampling for the start charts. The template's x-axis is fixed at
# -180..+120 s around the gun, and it draws a marker every 15th point, so the
# step also sets the marker spacing.
TRACK_FROM_S = -180
TRACK_TO_S = 120
TRACK_STEP_S = 2

# Upwind if the angle between COG and the wind is under this, downwind if over.
# 70/110 leaves a reaching band that belongs to neither, which is what a J/70
# beating at ~42 and running at ~150 actually does.
UPWIND_MAX_TWA = 70.0
DOWNWIND_MIN_TWA = 110.0


def _ang_diff(a: float, b: float) -> float:
    """Smallest absolute angle between two bearings, 0..180."""
    return abs((a - b + 180.0) % 360.0 - 180.0)


def _key_for(name: str) -> str:
    """Stable CSS/JS-safe key from a boat name.

    Digits are dropped because several crews append a sail number to the same
    boat name across days ("To Nessa 1527"), and the key has to stay the same
    so the template's colour map keeps working. The team keeps the key the
    template has always used for it.
    """
    if name == TEAM_NAME:
        return TEAM_KEY
    return "".join(c for c in name.lower() if c.isalpha()) or "boat"


def _short_for(name: str) -> str:
    """Three-character badge used on the KPI cards."""
    if name == TEAM_NAME:
        return "SWE"
    return (_key_for(name)[:3] or "BOA").upper()


def _sample_rate_hz(track) -> float:
    if len(track) < 3:
        return 1.0
    span_s = (track[-1][0] - track[0][0]) / 1000.0
    return (len(track) - 1) / span_s if span_s > 0 else 1.0


def racing_window(log: VkxLog) -> tuple[int, int] | None:
    """First RACE_START to last RACE_END, or None if the boat logged no race."""
    windows = race_windows(log)
    if not windows:
        return None
    return windows[0][0], windows[-1][1]


def _manoeuvres(track, hz: float, wind_by_ts):
    """Speed-dip manoeuvres, each labelled tack or gybe with its speed loss.

    A local speed minimum below half the average, at least 15 s clear of the
    previous one — the leg segmenter's detector, with one change that matters
    over a whole session rather than a single leg. The threshold is taken from
    the average for the boat's OWN point of sail, not from the session average.
    A J/70 here beats at 5.6 kn and runs at 11.8 kn, so one session-wide
    threshold of half of 7.4 kn sits below every downwind speed and finds
    essentially no gybes at all; per point of sail, a gybe has to dip below
    half of 11.8 kn to count, which is what a gybe actually does.

    The loss is the drop from the boat's speed 10 s before the dip to the dip
    itself, which is what a crew feels. Measuring from the leg average would
    understate a manoeuvre entered fast and overstate one entered slow.

    Upwind tack counts are reliable. Gybe counts are indicative: a surfing boat
    oscillates through the downwind threshold without gybing, so the run legs
    over-count. The same caveat is on the leg-level counts in the fleet report.
    """
    sogs = [p[3] * KNOTS_PER_MS for p in track]
    if not sogs:
        return [], []
    twas = [_ang_diff(math.degrees(p[4]) % 360.0, wind_by_ts(p[0])) for p in track]

    up = [s for s, a in zip(sogs, twas) if a < 90.0]
    down = [s for s, a in zip(sogs, twas) if a >= 90.0]
    thresholds = (
        max(2.0, 0.5 * (sum(up) / len(up))) if up else 2.0,
        max(2.0, 0.5 * (sum(down) / len(down))) if down else 2.0,
    )
    lead = max(1, int(round(10 * hz)))
    gap = max(1, int(round(15 * hz)))

    tacks, gybes, last = [], [], -10 ** 9
    for k in range(1, len(sogs) - 1):
        upwind = twas[k] < 90.0
        if sogs[k] >= thresholds[0 if upwind else 1]:
            continue
        if not (sogs[k] <= sogs[k - 1] and sogs[k] <= sogs[k + 1]):
            continue
        if k - last <= gap:
            continue
        last = k
        loss = max(0.0, sogs[max(0, k - lead)] - sogs[k])
        (tacks if upwind else gybes).append(loss)
    return tacks, gybes


def _point_of_sail(track, wind_by_ts) -> dict:
    """Upwind and downwind aggregates, split by true wind angle."""
    out = {}
    for label, lo, hi in (("upwind", 0.0, UPWIND_MAX_TWA), ("downwind", DOWNWIND_MIN_TWA, 180.0)):
        sogs, vmgs, dist_m, samples = [], [], 0.0, 0
        for k, p in enumerate(track):
            twa = _ang_diff(math.degrees(p[4]) % 360.0, wind_by_ts(p[0]))
            if not (lo <= twa <= hi):
                continue
            sog_kn = p[3] * KNOTS_PER_MS
            sogs.append(sog_kn)
            vmgs.append(sog_kn * math.cos(math.radians(twa)))
            samples += 1
            if k + 1 < len(track):
                dist_m += haversine_m(p[1], p[2], track[k + 1][1], track[k + 1][2])
        n = len(sogs) or 1
        out[label] = {
            "avgSpeedKn": round(sum(sogs) / n, 2),
            "maxSpeedKn": round(max(sogs), 1) if sogs else 0.0,
            "avgVmgKn": round(abs(sum(vmgs) / n), 2),
            "distanceNm": round(dist_m / 1852.0, 2),
            "pctTime": round(100.0 * samples / max(1, len(track)), 1),
        }
    return out


def boat_summary(name: str, log: VkxLog, wind_by_ts, twd_label: float) -> dict | None:
    win = racing_window(log)
    if win is None:
        return None
    t0, t1 = win
    track = [p for p in log.positions if t0 <= p[0] <= t1]
    if len(track) < 30:
        return None

    hz = _sample_rate_hz(track)
    sogs = [p[3] * KNOTS_PER_MS for p in track]
    dist_m = sum(haversine_m(track[k][1], track[k][2], track[k + 1][1], track[k + 1][2])
                 for k in range(len(track) - 1))
    tacks, gybes = _manoeuvres(track, hz, wind_by_ts)
    all_losses = tacks + gybes

    return {
        "key": _key_for(name),
        "name": name,
        "short": _short_for(name),
        "maxSpeedKn": round(max(sogs), 1),
        "avgSpeedKn": round(sum(sogs) / len(sogs), 1),
        "totalDistanceNm": round(dist_m / 1852.0, 1),
        "sessionStart": t0,
        "sessionEnd": t1,
        "tackCount": len(all_losses),
        "avgSpeedLossKn": round(sum(all_losses) / len(all_losses), 2) if all_losses else 0.0,
        "pointOfSail": dict(twd=round(twd_label), tacks={"count": len(tacks),
                            "avgLossKn": round(sum(tacks) / len(tacks), 2) if tacks else 0.0},
                            gybes={"count": len(gybes),
                                   "avgLossKn": round(sum(gybes) / len(gybes), 2) if gybes else 0.0},
                            **_point_of_sail(track, wind_by_ts)),
    }


def _interp_fix(track, ts_ms: int):
    """Position and motion at an arbitrary instant, linearly interpolated.

    The chart's x-axis is a fixed grid of whole seconds off the gun, but the
    logger samples at its own 2 Hz phase, so asking for the nearest sample
    would jitter the grid by up to half a sample. COG is interpolated as a unit
    vector so it does not swing the wrong way around north.
    """
    if not track or ts_ms < track[0][0] or ts_ms > track[-1][0]:
        return None
    lo, hi = 0, len(track) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if track[mid][0] <= ts_ms:
            lo = mid
        else:
            hi = mid
    a, b = track[lo], track[hi]
    span = b[0] - a[0]
    f = 0.0 if span <= 0 else (ts_ms - a[0]) / span
    lat = a[1] + (b[1] - a[1]) * f
    lon = a[2] + (b[2] - a[2]) * f
    sog = a[3] + (b[3] - a[3]) * f
    sin_c = math.sin(a[4]) + (math.sin(b[4]) - math.sin(a[4])) * f
    cos_c = math.cos(a[4]) + (math.cos(b[4]) - math.cos(a[4])) * f
    cog = math.degrees(math.atan2(sin_c, cos_c)) % 360.0
    return lat, lon, sog, cog


def start_entry(idx: int, gun_ts_ms: int, boats: list[tuple[str, VkxLog]],
                dist_to_line: dict[str, float]) -> dict:
    """One start: the fixed -180..+120 s tracks plus the approach metrics."""
    grid = list(range(TRACK_FROM_S, TRACK_TO_S + 1, TRACK_STEP_S))
    out = []
    for name, log in boats:
        track = [p for p in log.positions
                 if gun_ts_ms - 400_000 <= p[0] <= gun_ts_ms + 300_000]
        if len(track) < 30:
            continue
        rows, sog_at_gun = [], None
        for t in grid:
            fix = _interp_fix(track, gun_ts_ms + t * 1000)
            if fix is None:
                continue
            lat, lon, sog_ms, cog = fix
            sog_kn = sog_ms * KNOTS_PER_MS
            rows.append([t, round(lat, 6), round(lon, 6), round(sog_kn, 1), round(cog)])
            if t == 0:
                sog_at_gun = sog_kn
        if len(rows) < len(grid) // 2 or sog_at_gun is None:
            continue

        first60 = [r[3] for r in rows if 0 <= r[0] <= 60]
        approach = [r[3] for r in rows if -180 <= r[0] <= 0]
        window = [r for r in rows if -180 <= r[0] <= 120]
        window_m = sum(haversine_m(window[k][1], window[k][2], window[k + 1][1], window[k + 1][2])
                       for k in range(len(window) - 1))
        out.append({
            "key": _key_for(name),
            "gunTime": gun_ts_ms,
            "speedAtGunKn": round(sog_at_gun, 1),
            "maxSpeedFirst60sKn": round(max(first60), 1) if first60 else 0.0,
            "avgSpeedApproachKn": round(sum(approach) / len(approach), 1) if approach else 0.0,
            "distanceInWindowNm": round(window_m / 1852.0, 2),
            "track": rows,
            "distToLineAtGunM": dist_to_line.get(name),
        })
    return {"idx": idx, "gunTimeUtc": gun_ts_ms, "boats": out}


def load_logs(team_path: str, competitor_glob: str) -> dict[str, VkxLog]:
    """Boat name -> log. Competitor names come from their filenames, which is
    how the crews labelled their own exports; the fleet report uses the same
    derivation, so the two artefacts agree on names without a lookup table."""
    logs: dict[str, VkxLog] = {}
    for path in sorted(glob.glob(team_path)):
        logs[TEAM_NAME] = parse_file(path)
    for path in sorted(glob.glob(competitor_glob)):
        stem = os.path.basename(path).replace(".vkx", "")
        name = stem.rsplit("_", 1)[0].replace("_", " ")
        logs[name] = parse_file(path)
    return logs


def build(logs: dict[str, VkxLog], fleet_report: dict, display: list[str]) -> dict:
    races = fleet_report["races"]
    # Wind per race, from the fleet's own first-beat bearing.
    race_wind = [(r["gun_local"], r["wind"]["first_beat_bearing_deg"]) for r in races]

    team = logs.get(TEAM_NAME)
    if team is None:
        raise SystemExit(f"team log not found (expected {TEAM_NAME!r}); got {list(logs)}")
    guns = [s for s, _ in race_windows(team)]
    if len(guns) != len(races):
        raise SystemExit(f"{len(guns)} RACE_START rows in the team log but "
                         f"{len(races)} races in the fleet report")

    def wind_by_ts(ts_ms: int) -> float:
        """The nearer race's beat bearing. Between races the boundary is the
        midpoint of the two guns, so each sample is attributed to the race it
        belongs to rather than to whichever ran first."""
        best, best_gap = race_wind[0][1], abs(ts_ms - guns[0])
        for gun, (_, deg) in zip(guns, race_wind):
            gap = abs(ts_ms - gun)
            if gap < best_gap:
                best, best_gap = deg, gap
        return best

    twd_label = sum(d for _, d in race_wind) / len(race_wind)

    boats = []
    for name in display:
        if name not in logs:
            raise SystemExit(f"boat {name!r} asked for on the dashboard but not in the logs")
        summary = boat_summary(name, logs[name], wind_by_ts, twd_label)
        if summary is None:
            raise SystemExit(f"boat {name!r} logged no race window")
        boats.append(summary)

    display_logs = [(n, logs[n]) for n in display]
    starts = []
    for i, (gun, race) in enumerate(zip(guns, races)):
        dist = {row["boat"]: row["start"]["distance_to_line_m"] for row in race["rows"]}
        starts.append(start_entry(i + 1, gun, display_logs, dist))

    date = dt.datetime.fromtimestamp(guns[0] / 1000, dt.timezone.utc).date().isoformat()
    return {
        "session": {"date": date, "venue": VENUE, "estimatedTWD": round(twd_label)},
        "boats": boats,
        "starts": starts,
    }


def render(data: dict) -> str:
    return "export const DATA = " + json.dumps(data, separators=(",", ":")) + ";\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--team", default="data/raw/team/team_2026-09-08.vkx")
    ap.add_argument("--competitors", default="data/raw/competitors_2026-09-08/*.vkx")
    ap.add_argument("--fleet-report", default="reports/2026-09-08_fleet_report.json")
    ap.add_argument("--display", default=None,
                    help="comma-separated boat names for the four chart series "
                         "(default: the team plus the three best across the day)")
    ap.add_argument("--out", default="dashboard/regatta_data.js")
    args = ap.parse_args(argv)

    with open(args.fleet_report) as f:
        fleet = json.load(f)

    if args.display:
        display = [s.strip() for s in args.display.split(",")]
    else:
        # Rank by summed finishing position at the last tracked mark across the
        # races a boat actually sailed, so a boat that skipped a race cannot
        # win the ranking by absence.
        score: dict[str, list[int]] = {}
        for race in fleet["races"]:
            for pos, boat in enumerate(race["order_at_last_mark"], 1):
                score.setdefault(boat, []).append(pos)
        n_races = len(fleet["races"])
        ranked = sorted((b for b, ps in score.items() if len(ps) == n_races and b != TEAM_NAME),
                        key=lambda b: sum(score[b]))
        display = [TEAM_NAME] + ranked[:3]

    logs = load_logs(args.team, args.competitors)
    data = build(logs, fleet, display)

    with open(args.out, "w") as f:
        f.write(render(data))
    print(f"wrote {args.out}: {data['session']['date']}, "
          f"{len(data['boats'])} boats, {len(data['starts'])} starts")
    for b in data["boats"]:
        print(f"  {b['key']:<10} {b['name']:<22} max {b['maxSpeedKn']:>4} kn  "
              f"avg {b['avgSpeedKn']:>4} kn  {b['totalDistanceNm']:>5} nm  "
              f"{b['tackCount']:>3} manoeuvres")
    for s in data["starts"]:
        print(f"  start {s['idx']}: {len(s['boats'])} boats, "
              f"{len(s['boats'][0]['track'])} track points each")
    return 0


if __name__ == "__main__":
    sys.exit(main())
