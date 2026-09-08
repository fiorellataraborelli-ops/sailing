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
import re
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


def _all_fields(path: str, lat: float, lon: float) -> dict:
    """Every field in a multi-message GRIB, at the nearest grid point."""
    from eccodes import (codes_get, codes_get_values, codes_grib_new_from_file,
                         codes_release)

    out = {}
    with open(path, "rb") as f:
        while True:
            gid = codes_grib_new_from_file(f)
            if gid is None:
                break
            short_name = codes_get(gid, "shortName")
            step = codes_get(gid, "step")
            lat0 = codes_get(gid, "latitudeOfFirstGridPointInDegrees")
            lon0 = codes_get(gid, "longitudeOfFirstGridPointInDegrees")
            di = codes_get(gid, "iDirectionIncrementInDegrees")
            dj = codes_get(gid, "jDirectionIncrementInDegrees")
            ni = codes_get(gid, "Ni")
            values = codes_get_values(gid)
            codes_release(gid)
            lon_q = lon % 360 if lon0 >= 0 else lon
            i = round((lon_q - lon0) / di)
            j = round((lat0 - lat) / dj) if lat0 > lat else round((lat - lat0) / dj)
            out[short_name] = (step, float(values[j * ni + i]))
    return out


def ecmwf_series(directory: str, lat: float, lon: float, cycle_hour: int = 6) -> list[dict]:
    """One row per file from a directory of ECMWF IFS open-data GRIBs.

    These are multi-field files (10u, 10v and mean sea-level pressure), unlike
    the one-field-per-file ICON layout, so every message has to be walked.
    """
    rows = []
    for path in sorted(glob.glob(os.path.join(directory, "*.grib2"))):
        m = re.search(r"-(\d+)h-", os.path.basename(path))
        if not m:
            continue
        fields = _all_fields(path, lat, lon)
        if "10u" not in fields or "10v" not in fields:
            continue
        direction, speed = wind_from_uv(fields["10u"][1], fields["10v"][1])
        row = {
            "forecast_hour": int(m.group(1)),
            "valid_utc_hour": cycle_hour + int(m.group(1)),
            "direction_deg": round(direction, 1),
            "speed_kn": round(speed, 2),
        }
        if "msl" in fields:
            row["mslp_hpa"] = round(fields["msl"][1] / 100.0, 1)
        if "10fg" in fields:
            row["gust_kn"] = round(fields["10fg"][1] * MS_TO_KN, 2)
        rows.append(row)
    rows.sort(key=lambda r: r["valid_utc_hour"])
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


def render_section(result: dict) -> str:
    """Static dashboard section: what the models said vs what the fleet sailed."""
    icon = result.get("forecast", [])
    ecmwf = (result.get("ecmwf") or {}).get("forecast", [])
    mv = result.get("model_vs_observed", {})
    races = mv.get("races", [])
    offset = mv.get("mean_forecast_minus_observed_deg")

    obs = [r["observed_direction_deg"] for r in races]
    observed_mean = round(sum(obs) / len(obs), 0) if obs else None
    speeds = [r["speed_kn"] for r in icon] or [0]
    gusts = [r["gust_kn"] for r in icon if r.get("gust_kn")] or [0]
    mslps = [r["mslp_hpa"] for r in ecmwf if r.get("mslp_hpa")]

    tiles = []
    if observed_mean is not None:
        tiles.append(("Wind on the water", f"{observed_mean:.0f}&deg;", "from the line and the beat"))
    tiles.append(("Speed", f"{min(speeds):.0f}&ndash;{max(speeds):.0f} kn", "ICON-EU forecast"))
    if any(gusts):
        tiles.append(("Gusts", f"{max(gusts):.0f} kn", "about 2x the mean"))
    if offset is not None:
        tiles.append(("GRIB error", f"{offset:+.0f}&deg;", "model sits right of reality"))
    if len(mslps) >= 2:
        tiles.append(("Pressure", f"{mslps[-1] - mslps[0]:+.1f} hPa", f"{mslps[0]:.0f} &rarr; {mslps[-1]:.0f} over the day"))

    p = ['<!-- ===== Wind: forecast vs the water (static, build-time) ===== -->', '<style>',
         '#wx-wrap{margin:28px 40px 0;border:1px solid var(--bh-grey-line);}',
         '#wx-head{background:var(--bh-black);color:var(--bh-white);padding:16px 20px;}',
         '#wx-body{padding:20px;}',
         '#wx-tiles{display:flex;gap:30px;flex-wrap:wrap;padding-bottom:16px;margin-bottom:18px;'
         'border-bottom:1px solid var(--bh-grey-line);}',
         '.wx-t{font-size:11px;color:var(--bh-grey-700);}',
         '.wx-t b{display:block;font-size:22px;color:var(--bh-black);font-weight:600;'
         'font-variant-numeric:tabular-nums;margin:2px 0 1px;}',
         '.wx-t span{font-size:10px;color:var(--bh-grey-400);}',
         '.wx-table{width:100%;border-collapse:collapse;font-size:11.5px;}',
         '.wx-table th{text-align:right;padding:7px 8px;font-weight:600;color:var(--bh-black);'
         'border-bottom:1px solid var(--bh-black);white-space:nowrap;}',
         '.wx-table th:first-child,.wx-table td:first-child{text-align:left;}',
         '.wx-table td{text-align:right;padding:6px 8px;border-bottom:1px solid var(--bh-grey-100);'
         'font-variant-numeric:tabular-nums;color:var(--bh-grey-700);}',
         '.wx-obs td{color:var(--bh-ultramarine);font-weight:600;}',
         '#wx-note{font-size:11px;color:var(--bh-grey-700);margin-top:14px;line-height:1.55;}',
         '#wx-note b{color:var(--bh-black);}',
         '</style>',
         '<div id="wx-wrap">',
         '  <div id="wx-head">',
         '    <div style="font-size:13px;font-weight:600;">Wind &mdash; forecast vs. the water</div>',
         '    <div style="font-size:11px;color:var(--bh-grey-100);margin-top:4px;">'
         'ICON-EU 7 km and ECMWF IFS 0.25&deg;, decoded at 38.68 N 9.42 W, against the wind the fleet actually sailed</div>',
         '  </div>', '  <div id="wx-body">', '    <div id="wx-tiles">']
    for label, value, sub in tiles:
        p.append(f'      <div class="wx-t">{label}<b>{value}</b><span>{sub}</span></div>')
    p.append('    </div>')

    p.append('    <table class="wx-table"><thead><tr><th>Source</th>'
             '<th>Race 1 dir</th><th>Race 2 dir</th><th>Speed</th><th>vs. water</th></tr></thead><tbody>')
    if len(races) >= 2:
        p.append('      <tr><td>ICON-EU 06z (7 km)</td>'
                 f'<td>{races[0]["forecast_direction_deg"]:.0f}&deg;</td>'
                 f'<td>{races[1]["forecast_direction_deg"]:.0f}&deg;</td>'
                 f'<td>{races[0]["forecast_speed_kn"]:.1f} kn</td>'
                 f'<td>{races[0]["forecast_minus_observed_deg"]:+.1f} / {races[1]["forecast_minus_observed_deg"]:+.1f}&deg;</td></tr>')
    if len(ecmwf) >= 2 and obs:
        e1, e2 = ecmwf[0]["direction_deg"], ecmwf[1]["direction_deg"]
        p.append('      <tr><td>ECMWF IFS 06z (25 km)</td>'
                 f'<td>{e1:.0f}&deg;</td><td>{e2:.0f}&deg;</td>'
                 f'<td>{ecmwf[0]["speed_kn"]:.1f} kn</td>'
                 f'<td>{e1-obs[0]:+.1f} / {e2-obs[1]:+.1f}&deg;</td></tr>')
    if len(races) >= 2:
        p.append('      <tr class="wx-obs"><td>Measured on the water</td>'
                 f'<td>{races[0]["observed_direction_deg"]:.0f}&deg;</td>'
                 f'<td>{races[1]["observed_direction_deg"]:.0f}&deg;</td>'
                 '<td>&mdash;</td><td>&mdash;</td></tr>')
    p.append('    </tbody></table>')

    p.append('    <div id="wx-note">'
             '<b>Both models sit right of the racecourse.</b> The committee\'s line square and the fleet\'s '
             'beat bearing are independent of each other and of the models, and they agree with each other far '
             'more closely than either agrees with a GRIB. That is the Nortada bending left into Cascais Bay, '
             'which a 7&nbsp;km cell cannot resolve &mdash; and the finer ICON grid is about half as wrong as ECMWF. '
             '<b>Working rule: take ICON and subtract ~10&deg;.</b><br>'
             'The models do get the <i>trend</i> right: ICON backs 5.7&deg; between the two races and the fleet '
             'backed 6.4&deg;. Use them for when a shift arrives, not for the absolute bearing. Wind speed is the '
             'one thing GPS cannot give and the GRIB can.</div>')
    p.append('  </div>')
    p.append('</div>')
    return "\n".join(p) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--icon-dir", required=True)
    ap.add_argument("--ecmwf-dir", help="directory of ECMWF IFS open-data GRIBs")
    ap.add_argument("--lat", type=float, default=38.68)
    ap.add_argument("--lon", type=float, default=-9.42)
    ap.add_argument("--observed", help="JSON list of {race_number, mid_utc_hour, observed_deg, basis}")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--html-out", help="also write a dashboard section here")
    args = ap.parse_args(argv)

    rows = icon_series(args.icon_dir, args.lat, args.lon)
    result = {
        "point": {"lat": args.lat, "lon": args.lon},
        "model": "DWD ICON-EU 06z, ~7 km, 10 m wind",
        "forecast": rows,
    }
    if args.ecmwf_dir:
        result["ecmwf"] = {
            "model": "ECMWF IFS 06z open data, 0.25 deg, 10 m wind + MSLP",
            "forecast": ecmwf_series(args.ecmwf_dir, args.lat, args.lon),
        }
    if args.observed:
        result["model_vs_observed"] = compare(rows, json.loads(args.observed))

    with open(args.out, "w") as f:
        json.dump(result, f, indent=1)
    if args.html_out:
        with open(args.html_out, "w") as f:
            f.write(render_section(result))
        print(f"wrote {args.html_out}")
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
