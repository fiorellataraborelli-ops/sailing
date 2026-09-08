"""Build the compact race digest the in-dashboard strategy analyser reasons over.

The analyser sends this digest to Claude as text on every question, so it has a
hard size budget (the `sample` capability caps input at 64 KiB total, and the
conversation has to fit alongside it). Raw tracks are ~32k GPS fixes per boat
and never belong here: only per-leg and per-start aggregates go in, plus an
explicit statement of what the telemetry does NOT contain, so the analyser
can say "not in this data" instead of inventing it.
"""
from __future__ import annotations

import argparse
import json
import sys

# Local time at the venue relative to UTC. Portugal is on WEST (UTC+1) from
# late March to late October, which covers the September regatta dates.
VENUE_UTC_OFFSET_H = 1


def _utc_hhmm(ts_ms: int) -> str:
    import datetime as dt

    return dt.datetime.utcfromtimestamp(ts_ms / 1000).strftime("%H:%M:%S")


def _local_hhmm(ts_ms: int) -> str:
    import datetime as dt

    t = dt.datetime.utcfromtimestamp(ts_ms / 1000) + dt.timedelta(hours=VENUE_UTC_OFFSET_H)
    return t.strftime("%H:%M:%S")


# The leg pipeline names boats after their source files while the start metrics
# use the crews' own boat names. They must agree, or the analyser reads one boat
# as two.
BOAT_NAME_CANONICAL = {
    "Team (uploaded, our boat)": "Team Sweden (Roman)",
    "GSpot": "G-Spot",
    "DIVA-NEU": "Diva-Neu",
    "noticia": "Noticia",
}


def canonical_boat_name(label: str) -> str:
    return BOAT_NAME_CANONICAL.get(label, label)


def build_digest(leg_report: dict, start_metrics: dict | None = None) -> dict:
    """leg_report: reports/<date>_race_comparison_raw.json (our own pipeline).
    start_metrics: the regattaData-shaped dict of per-start numbers, if present.
    """
    boats = []
    for label, obj in leg_report.items():
        if "first_upwind_leg" not in obj:
            continue
        up = obj["first_upwind_leg"]
        dn = obj["first_downwind_leg"]
        boats.append({
            "boat": canonical_boat_name(label),
            "first_upwind": {
                "duration_min": up["duration_min"],
                "avg_sog_kn": up["avg_sog_kn"],
                "max_sog_kn": up["max_sog_kn"],
                "straight_line_m": up["straight_line_distance_m"],
                "path_m": up["path_distance_m"],
                "vmg_proxy_kn": up["avg_vmg_proxy_kn"],
                "tacks_detected": up["num_tacks_or_gybes_detected"],
            },
            "first_downwind": {
                "duration_min": dn["duration_min"],
                "avg_sog_kn": dn["avg_sog_kn"],
                "max_sog_kn": dn["max_sog_kn"],
                "straight_line_m": dn["straight_line_distance_m"],
                "path_m": dn["path_distance_m"],
                "vmg_proxy_kn": dn["avg_vmg_proxy_kn"],
                "gybes_detected": dn["num_tacks_or_gybes_detected"],
            },
        })

    digest = {
        "session": {
            "date": "2026-09-07",
            "venue": "Cascais, Portugal (approx 38.68N, 9.42W from GPS fixes)",
            "local_time_offset_from_utc_h": VENUE_UTC_OFFSET_H,
            "fleet_size_reported_by_user": 103,
            "team_result_reported_by_user": "3rd of 103 (user-provided, NOT derived from telemetry)",
            "scope_note": (
                "The race was not sailed to a finish (per the team). Only the FIRST "
                "UPWIND and FIRST DOWNWIND leg are analysed; later legs are excluded."
            ),
        },
        "start_sequence": {
            "race_start_events_utc": ["13:55:00", "14:10:00", "14:35:00", "14:50:00"],
            "observed": (
                "All 6 devices logged the same four RACE_START timer events within ~20ms "
                "of each other. Each of the first three was followed ~2 min later by a "
                "RACE_END+RESET pair; the 14:50 start had no RESET after it."
            ),
            "interpretation_inference": (
                "Consistent with three general recalls/abandoned starts and a valid final "
                "start at 14:50:00 UTC (15:50 local). This is an INFERENCE from timer "
                "events, not a recorded race-committee signal."
            ),
        },
        "legs": boats,
        "not_in_this_data": [
            "True wind speed and direction: no wind-instrument rows (VKX 0x0A) in any file.",
            "True wind angle and true VMG: cannot be computed without wind direction. "
            "The 'vmg_proxy_kn' figures are straight-line progress along each boat's own "
            "track axis per unit time - NOT wind-referenced VMG.",
            "Device-detected tack/gybe events: no shift-angle rows (VKX 0x06) in any file. "
            "Tack counts here are inferred from speed dips in the GPS track.",
            "Heel and pitch: the VKX 0x02 rows DO carry an orientation quaternion, but it "
            "has not been converted to heel/pitch yet, so no heel figures exist here.",
            "Finishing positions, elapsed times, points, and penalties: not in telemetry.",
            "Mark positions: no reliable mark/line rows; leg boundaries are inferred from "
            "each boat's own track reversal.",
            "Current/tide, waves, and wind shifts during the legs.",
        ],
        "metric_definitions": {
            "avg_sog_kn": "Mean GPS speed over ground across the leg, knots. Includes time lost in manoeuvres.",
            "vmg_proxy_kn": "Straight-line start-to-end distance of the leg divided by leg time, in knots. A course-made-good rate, not wind-referenced VMG.",
            "path_m": "Total distance sailed through the water track, metres.",
            "straight_line_m": "Direct distance from leg start to leg end, metres. path_m minus straight_line_m is the extra distance sailed (tacking/gybing and any wandering).",
            "speedAtGunKn": "GPS speed at the start gun, knots.",
            "avgSpeedApproachKn": "Mean speed over the 3 minutes before the gun, knots.",
            "distanceInWindowNm": "Distance sailed from 3 min before to 2 min after the gun, nautical miles.",
        },
    }

    if start_metrics:
        starts = []
        for s in start_metrics.get("starts", []):
            names = {b["key"]: b["name"] for b in start_metrics.get("boats", [])}
            starts.append({
                "start_number": s["idx"],
                "gun_utc": _utc_hhmm(s["gunTimeUtc"]),
                "gun_local": _local_hhmm(s["gunTimeUtc"]),
                "boats": [
                    {
                        "boat": canonical_boat_name(names.get(b["key"], b["key"])),
                        "speed_at_gun_kn": b["speedAtGunKn"],
                        "max_speed_first_60s_kn": b["maxSpeedFirst60sKn"],
                        "avg_speed_approach_kn": b["avgSpeedApproachKn"],
                        "distance_in_window_nm": b["distanceInWindowNm"],
                    }
                    for b in s["boats"]
                ],
            })
        digest["starts"] = starts

    return digest


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("leg_report", help="reports/<date>_race_comparison_raw.json")
    ap.add_argument("--start-metrics", help="JSON file of regattaData-shaped start metrics")
    ap.add_argument("-o", "--out", help="write digest here instead of stdout")
    args = ap.parse_args(argv)

    leg_report = json.load(open(args.leg_report))
    start_metrics = json.load(open(args.start_metrics)) if args.start_metrics else None
    digest = build_digest(leg_report, start_metrics)
    text = json.dumps(digest, indent=1)

    if args.out:
        with open(args.out, "w") as f:
            f.write(text)
        print(f"wrote {args.out} ({len(text.encode())} bytes)")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
