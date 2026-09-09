"""Per-start line analysis across the fleet, plus wind direction estimates.

Produces two artefacts from the VKX files:
  reports/start_line_analysis.json   - the data (also fed into the analyser digest)
  dashboard/start_line_section.html  - a static section for the dashboard

Wind direction is estimated three ways, none of which needs a wind instrument
(no boat logged one). They are reported side by side precisely so that
agreement or disagreement between them is visible:

  line_square      The committee sets the start line square to the wind, so the
                   line's perpendicular is the committee's own read of it.
  beat_axis        Bearing from the gun position to the windward mark. Where the
                   course was actually set.
  tack_bisector    The two upwind COG modes bisected. Where the boat actually
                   found the wind. This one is sensitive to spending unequal
                   time on each tack and to current.
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import math
import os
import sys

from .race_legs import find_final_race_start, segment_first_two_legs
from .start_line import line_geometry, start_analysis
from .vkx_parser import VkxLog, parse_file

BOAT_LABELS = {
    "team_2026-09-07": "Team Sweden (Roman)",
    "TYRA_VAKAROS2_2026-09-07": "TYRA",
    "TUR442_07.09.2026": "TUR 442",
    "GSpot_7-9-2026": "G-Spot",
    "DIVA-NEU_7.9.2026": "Diva-Neu",
    "noticia_9-7-2026": "Noticia",
}
TEAM = "Team Sweden (Roman)"
VENUE_UTC_OFFSET_H = 1


def _hhmm(ts_ms: int, offset_h: int = 0) -> str:
    return (dt.datetime.utcfromtimestamp(ts_ms / 1000) + dt.timedelta(hours=offset_h)).strftime("%H:%M:%S")


def _bearing(a, b) -> float:
    lat1, lon1 = a
    lat2, lon2 = b
    y = math.radians(lon2 - lon1) * math.cos(math.radians((lat1 + lat2) / 2))
    x = math.radians(lat2 - lat1)
    return math.degrees(math.atan2(y, x)) % 360.0


def _circ_mean(degs) -> float:
    s = sum(math.sin(math.radians(d)) for d in degs)
    c = sum(math.cos(math.radians(d)) for d in degs)
    return math.degrees(math.atan2(s, c)) % 360.0


def _circ_diff(a: float, b: float) -> float:
    return abs((a - b + 180) % 360 - 180)


def estimate_wind_from_tacks(track, end_index, min_sog_kn=3.0, seeds=(280.0, 20.0)):
    """Bisect the two upwind COG modes. Returns (wind_deg, tack_a, tack_b, angle)."""
    cogs = [math.degrees(p[4]) % 360.0 for p in track[:end_index] if p[3] * 1.9438444924 >= min_sog_kn]
    if len(cogs) < 50:
        return None
    a, b = seeds
    for _ in range(60):
        ga = [x for x in cogs if _circ_diff(x, a) <= _circ_diff(x, b)]
        gb = [x for x in cogs if _circ_diff(x, a) > _circ_diff(x, b)]
        if not ga or not gb:
            return None
        a, b = _circ_mean(ga), _circ_mean(gb)
    return _circ_mean([a, b]), a, b, _circ_diff(a, b)


def _pick_square_side(square_pair, reference_deg):
    """Of the line's two perpendiculars, the one nearer the beat direction."""
    return min(square_pair, key=lambda d: _circ_diff(d, reference_deg))


def build(logs: dict[str, VkxLog]) -> dict:
    team = logs[TEAM]
    guns = team.race_starts()

    # Beat axis and tack bisector come from the valid (final) start's first beat.
    valid_gun = find_final_race_start(team)
    leg1, _leg2, track = segment_first_two_legs(team, valid_gun)
    wind = {}
    if leg1 is not None and track:
        mark_i = next((i for i, p in enumerate(track) if p[0] >= leg1.end_ts_ms), len(track) - 1)
        beat_axis = _bearing((track[0][1], track[0][2]), (track[mark_i][1], track[mark_i][2]))
        wind["beat_axis_deg"] = round(beat_axis, 1)
        tacks = estimate_wind_from_tacks(track, mark_i)
        if tacks:
            w, ta, tb, ang = tacks
            wind["tack_bisector_deg"] = round(w, 1)
            wind["upwind_cog_modes_deg"] = [round(ta, 1), round(tb, 1)]
            wind["tacking_angle_deg"] = round(ang, 1)

    starts = []
    for idx, gun in enumerate(guns, 1):
        rows = []
        line = None
        for name, log in logs.items():
            r = start_analysis(log, gun)
            if not r:
                continue
            if line is None:
                square = r["line_square_wind_deg"]
                ref = wind.get("beat_axis_deg")
                line = {
                    "length_m": r["line_length_m"],
                    "length_nm": round(r["line_length_m"] / 1852.0, 3),
                    "bearing_deg": r["line_bearing_deg"],
                    "square_wind_deg": round(_pick_square_side(square, ref), 1) if ref is not None else None,
                    "square_wind_both_deg": square,
                    "pin": r["pin"],
                    "committee_boat": r["committee_boat"],
                }
            rows.append({
                "boat": name,
                "distance_to_line_m": r["distance_to_line_m"],
                "along_line_from_pin": r["along_line_from_pin"],
                "started_on": r["started_on"],
                "sog_at_gun_kn": r["sog_at_gun_kn"],
            })
        rows.sort(key=lambda x: x["distance_to_line_m"])
        starts.append({
            "start_number": idx,
            "gun_utc": _hhmm(gun),
            "gun_local": _hhmm(gun, VENUE_UTC_OFFSET_H),
            "was_valid_start": gun == valid_gun,
            "line": line,
            "boats": rows,
        })

    if starts and starts[-1]["line"] and starts[-1]["line"]["square_wind_deg"] is not None:
        wind["line_square_deg_valid_start"] = starts[-1]["line"]["square_wind_deg"]

    bearings = [s["line"]["bearing_deg"] for s in starts if s["line"]]
    return {
        "conventions": {
            "distance_to_line_m": "Perpendicular distance from the boat to the start line AT THE GUN. "
                                  "Positive = still behind the line. Negative = over the line early.",
            "along_line_from_pin": "0.0 = pin (left) end, 1.0 = committee boat (right) end. "
                                   "Values slightly outside 0-1 mean just beyond that end.",
            "source": "VKX 0x05 Line Position rows (pin = end type 0, committee boat = end type 1), "
                      "taking the last position logged for each end before the gun. All six boats "
                      "logged identical line coordinates, so this is the committee's line.",
        },
        "wind_direction_estimates_deg_from": wind,
        "wind_estimate_caveats": [
            "No boat logged a wind instrument; every figure here is inferred from GPS geometry.",
            "These are leg-average directions, not live shifts, and none of them gives wind SPEED.",
            "The line bearing rotated from {} to {} deg across the four starts, which implies the "
            "committee was re-squaring to a shifting wind.".format(
                round(bearings[0]) if bearings else "n/a", round(bearings[-1]) if bearings else "n/a"),
        ],
        "starts": starts,
    }


def render_section(data: dict) -> str:
    """Static dashboard section: distance to line at the gun, all starts."""
    w = data["wind_direction_estimates_deg_from"]
    est = []
    if "line_square_deg_valid_start" in w:
        est.append(("Line square (committee)", f"{w['line_square_deg_valid_start']:.0f}&deg;"))
    if "beat_axis_deg" in w:
        est.append(("Beat axis to mark", f"{w['beat_axis_deg']:.0f}&deg;"))
    if "tack_bisector_deg" in w:
        est.append(("Tack bisector", f"{w['tack_bisector_deg']:.0f}&deg;"))

    parts = [
        '<!-- ===== Start line: distance at the gun (static, build-time) ===== -->',
        '<style>',
        '#sl-wrap{margin:28px 40px 0;border:1px solid var(--bh-grey-line);}',
        '#sl-head{background:var(--bh-black);color:var(--bh-white);padding:16px 20px;}',
        '#sl-body{padding:20px;}',
        '.sl-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:20px;}',
        '.sl-card{border:1px solid var(--bh-grey-line);padding:14px 16px;}',
        '.sl-card.valid{border-color:var(--bh-ultramarine);border-width:2px;}',
        '.sl-t{font-size:12px;font-weight:600;color:var(--bh-black);margin-bottom:2px;}',
        '.sl-m{font-size:10.5px;color:var(--bh-grey-700);margin-bottom:10px;line-height:1.45;}',
        '.sl-row{display:flex;justify-content:space-between;gap:10px;font-size:11.5px;padding:3px 0;'
        'border-top:1px solid var(--bh-grey-100);}',
        '.sl-b{color:var(--bh-grey-700);}',
        '.sl-v{font-variant-numeric:tabular-nums;color:var(--bh-black);font-weight:600;white-space:nowrap;}',
        '.sl-team .sl-b,.sl-team .sl-v{color:var(--bh-ultramarine);}',
        '.sl-over{color:var(--bh-traffic-red);}',
        '#sl-wind{display:flex;gap:26px;flex-wrap:wrap;margin-bottom:18px;padding-bottom:16px;'
        'border-bottom:1px solid var(--bh-grey-line);}',
        '.sl-w{font-size:11px;color:var(--bh-grey-700);}',
        '.sl-w b{display:block;font-size:19px;color:var(--bh-black);font-weight:600;'
        'font-variant-numeric:tabular-nums;margin-top:2px;}',
        '#sl-foot{font-size:10.5px;color:var(--bh-grey-400);margin-top:14px;line-height:1.5;}',
        '</style>',
        '<div id="sl-wrap">',
        '  <div id="sl-head">',
        '    <div style="font-size:13px;font-weight:600;">Start line &mdash; distance at the gun</div>',
        '    <div style="font-size:11px;color:var(--bh-grey-100);margin-top:4px;">'
        'Positive = behind the line; negative = over early. Pin end 0.00 &rarr; committee boat 1.00</div>',
        '  </div>',
        '  <div id="sl-body">',
    ]

    if est:
        parts.append('    <div id="sl-wind">')
        for label, val in est:
            parts.append(f'      <div class="sl-w">{label}<b>{val}</b></div>')
        parts.append('      <div class="sl-w">Wind speed<b>n/a</b></div>')
        parts.append('    </div>')

    parts.append('    <div class="sl-grid">')
    for s in data["starts"]:
        line = s["line"] or {}
        cls = "sl-card valid" if s["was_valid_start"] else "sl-card"
        tag = " &middot; VALID START" if s["was_valid_start"] else " &middot; recalled"
        parts.append(f'      <div class="{cls}">')
        parts.append(f'        <div class="sl-t">Start {s["start_number"]} &mdash; gun {s["gun_local"]} local{tag}</div>')
        if line:
            parts.append(
                '        <div class="sl-m">Line {:.0f} m ({:.2f} nm), bearing {:.0f}&deg;{}</div>'.format(
                    line["length_m"], line["length_nm"], line["bearing_deg"],
                    ", square to {:.0f}&deg;".format(line["square_wind_deg"]) if line.get("square_wind_deg") is not None else ""))
        for b in s["boats"]:
            team_cls = " sl-team" if b["boat"] == TEAM else ""
            d = b["distance_to_line_m"]
            over = ' class="sl-v sl-over"' if d < 0 else ' class="sl-v"'
            parts.append(
                '        <div class="sl-row{}"><span class="sl-b">{}</span>'
                '<span{}>{:+.1f} m &middot; {:.2f}</span></div>'.format(
                    team_cls, b["boat"], over, d, b["along_line_from_pin"]))
        parts.append('      </div>')
    parts.append('    </div>')

    parts.append(
        '    <div id="sl-foot">Line ends from the boats\' own VKX line-position rows (last logged before each gun); '
        'all six boats recorded identical coordinates. No boat logged a wind instrument, so the wind directions above '
        'are inferred from geometry and no wind speed is available.</div>')
    parts.append('  </div>')
    parts.append('</div>')
    return "\n".join(parts) + "\n"


def load_logs(team_glob: str, competitor_glob: str) -> dict[str, VkxLog]:
    logs = {}
    for path in sorted(glob.glob(team_glob)) + sorted(glob.glob(competitor_glob)):
        key = os.path.basename(path).replace(".vkx", "")
        logs[BOAT_LABELS.get(key, key)] = parse_file(path)
    if TEAM not in logs:
        raise SystemExit(f"team log not found (expected label {TEAM!r}); got {list(logs)}")
    return logs


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--team", default="data/raw/team/*.vkx")
    ap.add_argument("--competitors", default="data/raw/competitors/*.vkx")
    ap.add_argument("--json-out", default="reports/start_line_analysis.json")
    ap.add_argument("--html-out", default="dashboard/start_line_section.html")
    args = ap.parse_args(argv)

    data = build(load_logs(args.team, args.competitors))

    with open(args.json_out, "w") as f:
        json.dump(data, f, indent=1)
    print(f"wrote {args.json_out}")
    with open(args.html_out, "w") as f:
        f.write(render_section(data))
    print(f"wrote {args.html_out}")

    w = data["wind_direction_estimates_deg_from"]
    print("\nwind direction estimates (deg from):")
    for k, v in w.items():
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
