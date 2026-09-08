"""Read 10-m wind out of GRIB2 at a point, and compare it with what the boats sailed.

The GRIBs in `data/wind/` are gradient-scale forecasts: ICON-EU at ~7 km and
ECMWF IFS at 0.25° (~25 km). Cascais Bay is smaller than either grid cell is
good at, so the forecast is not automatically the wind the fleet raced in — and
on 8 Sept it wasn't. This module produces both numbers side by side so the
offset is visible rather than assumed away:

  forecast_deg   what the model says at the nearest grid point
  observed_deg   what the committee squared the line to, and the bearing the
                 fleet actually sailed up the first beat

The models supply the one thing GPS geometry cannot: wind SPEED.
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import os
import sys

MS_TO_KN = 1.9438444924


def _point_value(path: str, lat: float, lon: float):
    """Value of the single field in `path` at the grid point nearest lat/lon."""
    from eccodes import (codes_get, codes_get_values, codes_grib_new_from_file,
                         codes_release)

    with open(path, "rb") as f:
        gid = codes_grib_new_from_file(f)
        if gid is None:
            raise ValueError(f"no GRIB message in {path}")
        short_name = codes_get(gid, "shortName")
        step = codes_get(gid, "step")
        lat0 = codes_get(gid, "latitudeOfFirstGridPointInDegrees")
        lon0 = codes_get(gid, "longitudeOfFirstGridPointInDegrees")
        di = codes_get(gid, "iDirectionIncrementInDegrees")
        dj = codes_get(gid, "jDirectionIncrementInDegrees")
        ni = codes_get(gid, "Ni")
        values = codes_get_values(gid)
        codes_release(gid)

    # Grids here start at a positive longitude and run east; negative longitudes
    # therefore have to be wrapped before indexing.
    lon_q = lon % 360 if lon0 >= 0 else lon
    i = round((lon_q - lon0) / di)
    j = round((lat0 - lat) / dj) if lat0 > lat else round((lat - lat0) / dj)
    return short_name, step, float(values[j * ni + i])


def wind_from_uv(u: float, v: float) -> tuple[float, float]:
    """(direction the wind blows FROM in degrees true, speed in knots)."""
    return math.degrees(math.atan2(-u, -v)) % 360.0, math.hypot(u, v) * MS_TO_KN


def icon_series(directory: str, lat: float, lon: float) -> list[dict]:
    """One row per forecast hour from a directory of ICON-EU single-level files."""
    steps: dict[str, dict] = {}
    for path in sorted(glob.glob(os.path.join(directory, "*.grib2"))):
        base = os.path.basename(path)
        parts = base.replace(".grib2", "").split("_")
        step_txt = next((p for p in parts if p.isdigit() and len(p) == 3), None)
        if step_txt is None:
            continue
        var = "VMAX" if "VMAX" in base else ("U" if "_U_" in base else ("V" if "_V_" in base else None))
        if var is None:
            continue
        _, _, value = _point_value(path, lat, lon)
        steps.setdefault(step_txt, {})[var] = value

    rows = []
    for step_txt in sorted(steps):
        s = steps[step_txt]
        if "U" not in s or "V" not in s:
            continue
        direction, speed = wind_from_uv(s["U"], s["V"])
        # ICON-EU run is the 06 UTC cycle: forecast hour + 6 = valid UTC hour.
        rows.append({
            "forecast_hour": int(step_txt),
            "valid_utc_hour": int(step_txt) + 6,
            "direction_deg": round(direction, 1),
            "speed_kn": round(speed, 2),
            "gust_kn": round(s["VMAX"] * MS_TO_KN, 2) if "VMAX" in s else None,
        })
    return rows


def compare(forecast_rows: list[dict], observed: list[dict]) -> dict:
    """Offset between the forecast and what the fleet sailed."""
    out = {"races": []}
    offsets = []
    for obs in observed:
        near = min(forecast_rows, key=lambda r: abs(r["valid_utc_hour"] - obs["mid_utc_hour"]))
        off = (near["direction_deg"] - obs["observed_deg"] + 180) % 360 - 180
        offsets.append(off)
        out["races"].append({
            "race_number": obs["race_number"],
            "mid_utc_hour": obs["mid_utc_hour"],
            "forecast_direction_deg": near["direction_deg"],
            "forecast_speed_kn": near["speed_kn"],
            "forecast_gust_kn": near["gust_kn"],
            "observed_direction_deg": obs["observed_deg"],
            "observed_basis": obs.get("basis", ""),
            "forecast_minus_observed_deg": round(off, 1),
        })
    if offsets:
        out["mean_forecast_minus_observed_deg"] = round(sum(offsets) / len(offsets), 1)
        out["interpretation"] = (
            "A positive mean means the forecast sits to the RIGHT of the wind the fleet "
            "actually sailed, i.e. on the water the breeze was further left than the model. "
            "Both the committee's line and the fleet's beat bearing are independent of the "
            "model, so a consistent offset is a real local bend, not measurement error."
        )
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--icon-dir", required=True)
    ap.add_argument("--lat", type=float, default=38.68)
    ap.add_argument("--lon", type=float, default=-9.42)
    ap.add_argument("--observed", help="JSON list of {race_number, mid_utc_hour, observed_deg, basis}")
    ap.add_argument("-o", "--out", required=True)
    args = ap.parse_args(argv)

    rows = icon_series(args.icon_dir, args.lat, args.lon)
    result = {
        "point": {"lat": args.lat, "lon": args.lon},
        "model": "DWD ICON-EU 06z, ~7 km, 10 m wind",
        "forecast": rows,
    }
    if args.observed:
        result["model_vs_observed"] = compare(rows, json.loads(args.observed))

    with open(args.out, "w") as f:
        json.dump(result, f, indent=1)
    print(f"wrote {args.out} ({len(rows)} forecast hours)")
    for r in rows:
        print(f"  {r['valid_utc_hour']:02d}Z  {r['direction_deg']:5.1f} deg  "
              f"{r['speed_kn']:5.2f} kn  gust {r['gust_kn']}")
    if "model_vs_observed" in result:
        mv = result["model_vs_observed"]
        print(f"\n  mean forecast-minus-observed: {mv.get('mean_forecast_minus_observed_deg')} deg")
        for r in mv["races"]:
            print(f"    race {r['race_number']}: forecast {r['forecast_direction_deg']} vs "
                  f"observed {r['observed_direction_deg']} -> {r['forecast_minus_observed_deg']:+.1f} deg")
    return 0


if __name__ == "__main__":
    sys.exit(main())
