"""CLI: parse a VKX file and report first-upwind / first-downwind leg stats."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys

from .race_legs import find_final_race_start, segment_first_two_legs
from .vkx_parser import parse_file


def iso_utc(ts_ms: int) -> str:
    return dt.datetime.utcfromtimestamp(ts_ms / 1000).replace(tzinfo=dt.timezone.utc).isoformat()


def leg_to_dict(leg) -> dict:
    return {
        "leg": leg.name,
        "start_utc": iso_utc(leg.start_ts_ms),
        "end_utc": iso_utc(leg.end_ts_ms),
        "duration_min": round(leg.duration_s / 60.0, 2),
        "path_distance_m": round(leg.path_distance_m, 1),
        "straight_line_distance_m": round(leg.straight_line_distance_m, 1),
        "avg_sog_kn": round(leg.avg_sog_kn, 2),
        "max_sog_kn": round(leg.max_sog_kn, 2),
        "min_sog_kn": round(leg.min_sog_kn, 2),
        "avg_vmg_proxy_kn": round(leg.avg_vmg_kn, 2),
        "num_tacks_or_gybes_detected": leg.num_tacks_or_gybes,
        "n_gps_fixes": leg.n_fixes,
    }


def analyze(path: str) -> dict:
    log = parse_file(path)
    race_start = find_final_race_start(log)
    result = {
        "source_file": path,
        "bytes_total": log.bytes_total,
        "bytes_parsed": log.bytes_consumed,
        "fully_parsed": log.bytes_consumed == log.bytes_total,
        "n_position_fixes": len(log.positions),
        "n_race_start_events": len(log.race_starts()),
        "all_race_start_events_utc": [iso_utc(t) for t in log.race_starts()],
        "has_wind_sensor_data": len(log.wind) > 0,
        "has_shift_angle_data": len(log.shift_angles) > 0,
    }
    if race_start is None:
        result["error"] = "No RACE_START (timer event id 3) row found in this file. Data not provided."
        return result
    result["race_start_used_utc"] = iso_utc(race_start)
    leg1, leg2, track = segment_first_two_legs(log, race_start)
    if leg1 is None:
        result["error"] = "Could not segment legs: insufficient/ambiguous track data after race start."
        return result
    result["first_upwind_leg"] = leg_to_dict(leg1)
    result["first_downwind_leg"] = leg_to_dict(leg2)
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("vkx_path")
    ap.add_argument("--json", action="store_true", help="print raw JSON only")
    args = ap.parse_args(argv)

    result = analyze(args.vkx_path)
    if args.json:
        print(json.dumps(result, indent=2))
        return 0

    print(f"File: {result['source_file']}")
    print(f"  Parsed cleanly: {result['fully_parsed']} ({result['bytes_parsed']}/{result['bytes_total']} bytes)")
    print(f"  GPS fixes: {result['n_position_fixes']}")
    print(f"  RACE_START events logged: {result['n_race_start_events']} -> {result['all_race_start_events_utc']}")
    print(f"  Wind sensor data present: {result['has_wind_sensor_data']}")
    print(f"  Shift-angle (tack) data present: {result['has_shift_angle_data']}")
    if "error" in result:
        print(f"  ERROR: {result['error']}")
        return 1
    print(f"  Race start used (final RACE_START): {result['race_start_used_utc']}")
    for key in ("first_upwind_leg", "first_downwind_leg"):
        leg = result[key]
        print(f"  -- {leg['leg']} --")
        for k, v in leg.items():
            if k == "leg":
                continue
            print(f"      {k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
