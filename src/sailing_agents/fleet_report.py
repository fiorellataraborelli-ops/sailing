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


TEAM_NAME = "Team Sweden (Roman)"


def _esc(text: str) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def render_start_line_section(report: dict) -> str:
    """The dashboard's start-line panel, one card per completed race.

    Rendered from this report rather than recomputed, so the page and the JSON
    can never disagree: every number below is read straight out of the dict
    that was just written to disk.

    The panel it replaces described 7 September, whose four starts were all
    general recalls. The interesting column there was "were we over early". Here
    both starts were valid and sailed to a finish, so the interesting column is
    where along the line each boat started against how long its first beat then
    took - which is the day's one clear finding.
    """
    races = report.get("races") or []
    cards = []
    for race in races:
        wind = race["wind"]
        rows = sorted(race["rows"], key=lambda r: r["start"]["distance_to_line_m"])
        beat1_by_boat = {r["boat"]: r["beat1"]["duration_min"] for r in race["rows"]}
        lines = []
        for row in rows:
            st = row["start"]
            is_team = row["boat"] == TEAM_NAME
            dist = st["distance_to_line_m"]
            cls = "sl-row sl-team" if is_team else "sl-row"
            val_cls = "sl-v sl-over" if dist < 0 else "sl-v"
            sign = "+" if dist >= 0 else "\u2212"
            beat = beat1_by_boat.get(row["boat"])
            lines.append(
                f'        <div class="{cls}"><span class="sl-b">{_esc(row["boat"])}</span>'
                f'<span class="{val_cls}">{sign}{abs(dist):.1f} m &middot; {st["along_line_from_pin"]:.2f}'
                f' &middot; {beat:.1f} min</span></div>'
            )
        corr = race["along_line_vs_beat1_time_correlation"]
        cards.append(
            '      <div class="sl-card">\n'
            f'        <div class="sl-t">Race {race["race_number"]} &mdash; gun {race["gun_local"]} local'
            f' &middot; {race["boats_tracked"]} boats tracked</div>\n'
            f'        <div class="sl-m">Line {wind["line_length_m"]:.0f} m, bearing '
            f'{wind["line_bearing_deg"]:.0f}&deg;, square to {wind["line_square_deg"]:.0f}&deg;. '
            f'Correlation between start position along the line and time to the first windward '
            f'mark: <b>{corr:+.2f}</b> &mdash; positive means the committee-boat end was slower.</div>\n'
            + "\n".join(lines) + "\n      </div>"
        )

    return """<!-- ===== Start line: distance at the gun (static, build-time) ===== -->
<style>
#sl-wrap{margin:28px 40px 0;border:1px solid var(--bh-grey-line);}
#sl-head{background:var(--bh-black);color:var(--bh-white);padding:16px 20px;}
#sl-body{padding:20px;}
.sl-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:20px;}
.sl-card{border:1px solid var(--bh-grey-line);padding:14px 16px;}
.sl-t{font-size:12px;font-weight:600;color:var(--bh-black);margin-bottom:2px;}
.sl-m{font-size:10.5px;color:var(--bh-grey-700);margin-bottom:10px;line-height:1.45;}
.sl-row{display:flex;justify-content:space-between;gap:10px;font-size:11.5px;padding:3px 0;border-top:1px solid var(--bh-grey-100);}
.sl-b{color:var(--bh-grey-700);}
.sl-v{font-variant-numeric:tabular-nums;color:var(--bh-black);font-weight:600;white-space:nowrap;}
.sl-team .sl-b,.sl-team .sl-v{color:var(--bh-ultramarine);}
.sl-over{color:var(--bh-traffic-red);}
#sl-foot{font-size:10.5px;color:var(--bh-grey-400);margin-top:14px;line-height:1.5;}
</style>
<div id="sl-wrap">
  <div id="sl-head">
    <div style="font-size:13px;font-weight:600;">Start line &mdash; position at the gun, and what it cost</div>
    <div style="font-size:11px;color:var(--bh-grey-100);margin-top:4px;">Distance to line (positive = behind, negative = over early) &middot; position along the line (pin 0.00 &rarr; committee boat 1.00) &middot; first beat elapsed. Sorted by distance to the line.</div>
  </div>
  <div id="sl-body">
    <div class="sl-grid">
%s
    </div>
    <div id="sl-foot">%s</div>
  </div>
</div>
""" % ("\n".join(cards), _esc(
        "Line ends from the boats' own VKX line-position rows (last logged before each gun); "
        "every boat recorded identical coordinates, so this is the committee's line. Positions and "
        "beat times are measured from each boat's own track. No boat logged a wind instrument, so "
        "the square-to figures are geometry, not measurement — see the forecast panel for wind speed."
    ))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--team", required=True)
    ap.add_argument("--competitors", required=True, help="glob of competitor .vkx files")
    ap.add_argument("--wind-deg", type=float, default=None,
                    help="estimated wind direction, used to label legs beat/run")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--html-out", default=None,
                    help="also render the dashboard's start-line section from this report")
    args = ap.parse_args(argv)

    fleet = load_fleet(args.team, args.competitors, args.wind_deg)
    report = build(fleet)
    with open(args.out, "w") as f:
        json.dump(report, f, indent=1)
    print(f"wrote {args.out}: {len(report['races'])} races, "
          f"{report['races'][0]['boats_tracked'] if report['races'] else 0} boats")
    if args.html_out:
        with open(args.html_out, "w") as f:
            f.write(render_start_line_section(report))
        print(f"wrote {args.html_out}")
    for r in report["races"]:
        ts = r.get("team_summary")
        if ts:
            print(f"  race {r['race_number']} ({r['gun_local']}): team at marks "
                  f"{ts['position_at_each_mark']} of {r['boats_tracked']}, "
                  f"gap to leader {ts['gap_to_leader_min']} min")
    return 0


if __name__ == "__main__":
    sys.exit(main())
