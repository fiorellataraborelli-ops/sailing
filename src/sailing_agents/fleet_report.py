"""Fleet debrief for a day of completed races: who was where at each mark, and why.

Two measurement decisions matter here, and both were forced by what the data
actually turned out to be:

1. RACE_END is useless as a finish time. Every boat's RACE_END lands within a
   second of every other boat's, so it is a synced signal from the committee's
   sequence, not the moment each crew crossed the line. Ranking on it ranks
   sampling noise. Positions here are therefore taken at MARK ROUNDINGS, which
   are detected per boat from its own track and do spread out realistically.
   The last leg is excluded for the same reason: its end is the synced signal,
   not a rounding.

2. Where a boat lost time is separated into speed and distance. `avg_sog_kn`
   answers "were we slow", `path_m / straight_line_m` answers "did we sail
   further than we had to". A boat can be at fleet-average speed and still lose
   two minutes by sailing 150 m extra, which is exactly what happened in the
   second race on 8 Sept.
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import math
import os
import sys

from .race_multi_leg import analyse
from .start_line import line_at, line_geometry, start_analysis
from .vkx_parser import parse_file

VENUE_UTC_OFFSET_H = 1
TEAM = "Team Sweden (Roman)"
DATE_SUFFIXES = ["_9-8-2026", "_8-9-2026", "_08-09-2026", "_8.9.2026",
                 "_9-7-2026", "_7-9-2026", "_07.09.2026", "_7.9.2026"]


def _local(ts_ms: int, fmt="%H:%M") -> str:
    return (dt.datetime.utcfromtimestamp(ts_ms / 1000)
            + dt.timedelta(hours=VENUE_UTC_OFFSET_H)).strftime(fmt)


def _pearson(xs, ys) -> float:
    n = len(xs)
    if n < 3:
        return 0.0
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    dx = math.sqrt(sum((a - mx) ** 2 for a in xs))
    dy = math.sqrt(sum((b - my) ** 2 for b in ys))
    return num / (dx * dy) if dx and dy else 0.0


def boat_name(path: str) -> str:
    name = os.path.basename(path).replace(".vkx", "")
    for suf in DATE_SUFFIXES:
        name = name.replace(suf, "")
    return name.replace("_", " ").strip()


def load_fleet(team_path: str, competitor_glob: str, wind_deg: float | None):
    fleet = {TEAM: parse_file(team_path)}
    for p in sorted(glob.glob(competitor_glob)):
        fleet[boat_name(p)] = parse_file(p)
    return {n: (log, analyse(log, wind_deg=wind_deg)) for n, log in fleet.items()}


def estimate_wind(fleet, race_number: int) -> dict:
    """Wind direction for a race, from the committee's own line plus the beat."""
    log, races = fleet[TEAM]
    race = next((r for r in races if r.number == race_number), None)
    if race is None:
        return {}
    pin, boat = line_at(log, race.start_ts_ms)
    out = {}
    if pin and boat:
        geom = line_geometry(pin, boat)
        beat = race.legs[0].bearing_deg if race.legs else None
        square = geom["square_wind_deg"]
        if beat is not None:
            square = min(square, key=lambda d: abs((d - beat + 180) % 360 - 180))
        else:
            square = square[0]
        out.update(line_length_m=round(geom["length_m"], 1),
                   line_bearing_deg=round(geom["bearing_deg"], 1),
                   line_square_deg=round(square, 1))
    if race.legs:
        out["first_beat_bearing_deg"] = race.legs[0].bearing_deg
    return out


def build(fleet, min_legs: int = 3) -> dict:
    race_numbers = sorted({r.number for _, races in fleet.values() for r in races})
    report = {
        "date": "unknown",
        "team": TEAM,
        "method_notes": [
            "Positions are taken at mark roundings detected from each boat's own track.",
            "RACE_END is synced across the fleet (all boats within ~1 s), so it is not a "
            "finish time and is never used for ranking. The final leg is excluded.",
            "No boat logged a wind instrument; wind direction is estimated from the "
            "committee's line bearing and the beat, and no wind speed is available.",
            "Manoeuvre counts come from speed dips and over-count on downwind legs, where "
            "surfing makes speed oscillate. Treat upwind tack counts as reliable and "
            "downwind gybe counts as indicative only.",
        ],
        "races": [],
    }

    any_ts = next(iter(fleet.values()))[1]
    if any_ts:
        report["date"] = _local(any_ts[0].start_ts_ms, "%Y-%m-%d")

    for rn in race_numbers:
        guns = [r.start_ts_ms for _, races in fleet.values() for r in races if r.number == rn]
        if not guns:
            continue
        gun = min(guns)

        rows = []
        for name, (log, races) in fleet.items():
            race = next((r for r in races if r.number == rn), None)
            if race is None or len(race.legs) < min_legs:
                continue
            legs = race.legs[:min_legs]
            sa = start_analysis(log, race.start_ts_ms)
            first = legs[0]
            rows.append({
                "boat": name,
                "marks_min": [round((L.end_ts_ms - gun) / 60000.0, 2) for L in legs],
                "leg_min": [L.duration_min for L in legs],
                "leg_avg_sog_kn": [L.avg_sog_kn for L in legs],
                "leg_kind": [L.kind for L in legs],
                "beat1": {
                    "duration_min": first.duration_min,
                    "avg_sog_kn": first.avg_sog_kn,
                    "path_m": first.path_m,
                    "straight_line_m": first.straight_line_m,
                    "extra_distance_m": round(first.path_m - first.straight_line_m, 1),
                    "path_ratio": round(first.path_m / first.straight_line_m, 3)
                    if first.straight_line_m else None,
                    "tacks": first.manoeuvres,
                },
                "start": {
                    "distance_to_line_m": sa["distance_to_line_m"] if sa else None,
                    "along_line_from_pin": sa["along_line_from_pin"] if sa else None,
                } if sa else None,
            })

        if not rows:
            continue
        rows.sort(key=lambda x: x["marks_min"][-1])

        entry = {
            "race_number": rn,
            "gun_local": _local(gun),
            "boats_tracked": len(rows),
            "wind": estimate_wind(fleet, rn),
            "order_at_last_mark": [x["boat"] for x in rows],
            "rows": rows,
        }

        starters = [x for x in rows if x["start"] and x["start"]["along_line_from_pin"] is not None]
        if len(starters) >= 3:
            entry["along_line_vs_beat1_time_correlation"] = round(_pearson(
                [x["start"]["along_line_from_pin"] for x in starters],
                [x["beat1"]["duration_min"] for x in starters]), 2)
            entry["correlation_meaning"] = (
                "Positive means boats starting nearer the committee-boat end took longer "
                "to the first windward mark.")

        team = next((x for x in rows if x["boat"] == TEAM), None)
        if team:
            others = [x for x in rows if x["boat"] != TEAM]
            entry["team_summary"] = {
                "position_at_each_mark": [
                    sorted(rows, key=lambda z: z["marks_min"][i]).index(team) + 1
                    for i in range(min_legs)
                ],
                "gap_to_leader_min": [
                    round(team["marks_min"][i] - min(x["marks_min"][i] for x in rows), 2)
                    for i in range(min_legs)
                ],
                "beat1_avg_sog_vs_fleet_kn": round(
                    team["beat1"]["avg_sog_kn"]
                    - sum(x["beat1"]["avg_sog_kn"] for x in others) / len(others), 2),
                "beat1_extra_distance_vs_fleet_m": round(
                    team["beat1"]["extra_distance_m"]
                    - sum(x["beat1"]["extra_distance_m"] for x in others) / len(others), 1),
                "beat1_tacks_vs_fleet_median": team["beat1"]["tacks"] - sorted(
                    x["beat1"]["tacks"] for x in others)[len(others) // 2],
            }
        report["races"].append(entry)

    return report


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--team", required=True)
    ap.add_argument("--competitors", required=True, help="glob of competitor .vkx files")
    ap.add_argument("--wind-deg", type=float, default=None,
                    help="estimated wind direction, used to label legs beat/run")
    ap.add_argument("-o", "--out", required=True)
    args = ap.parse_args(argv)

    fleet = load_fleet(args.team, args.competitors, args.wind_deg)
    report = build(fleet)
    with open(args.out, "w") as f:
        json.dump(report, f, indent=1)
    print(f"wrote {args.out}: {len(report['races'])} races, "
          f"{report['races'][0]['boats_tracked'] if report['races'] else 0} boats")
    for r in report["races"]:
        ts = r.get("team_summary")
        if ts:
            print(f"  race {r['race_number']} ({r['gun_local']}): team at marks "
                  f"{ts['position_at_each_mark']} of {r['boats_tracked']}, "
                  f"gap to leader {ts['gap_to_leader_min']} min")
    return 0


if __name__ == "__main__":
    sys.exit(main())
