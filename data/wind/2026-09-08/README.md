# Wind data — Cascais, 2026-09-08 (J/70 Worlds)

Two independent GRIB sources for today's race window (approximately
11:00–17:00 UTC / 12:00–18:00 local WEST).

## `icon-eu-06z/` — DWD ICON-EU, 06 UTC cycle

- Regional NWP, ~7 km resolution, hourly steps.
- Free/open GRIB2 from https://opendata.dwd.de/weather/nwp/icon-eu/grib/06/
- Variables: `U_10M`, `V_10M`, `VMAX_10M` (10-m u-wind, v-wind, gust).
- Forecast hours pulled: `005..011` (11Z → 17Z, i.e. the racing window).
- Filename pattern:
  `icon-eu_europe_regular-lat-lon_single-level_2026090806_<HHH>_<VAR>.grib2`

## `ecmwf-ifs-06z/` — ECMWF IFS open data, 06 UTC cycle

- Global NWP, 0.25° resolution, 3-hourly steps.
- Free/open GRIB2 from https://data.ecmwf.int/forecasts/20260908/06z/ifs/0p25/oper/
- Kept fields: 10-m U, 10-m V, 10-m wind gust, mean sea-level pressure.
- Files: `+6h` (12Z), `+9h` (15Z), `+12h` (18Z), subset to those four fields
  (still global grid; ~2 MB each) so the whole bundle stays small enough
  to commit.

## Decoded summary at Cascais Bay (38.68 N, 9.42 W)

ICON-EU 06z at the nearest grid point:

| Local | UTC | Wind dir | Speed | Gust |
|-------|-----|----------|-------|------|
| 12:00 | 11Z | 341°     | 11.7 kn | 22.4 kn |
| 13:00 | 12Z | 338°     | 11.5 kn | 22.5 kn |
| 14:00 | 13Z | 334°     | 11.4 kn | 22.1 kn |
| 15:00 | 14Z | 332°     | 11.3 kn | 22.0 kn |
| 16:00 | 15Z | 328°     | 11.0 kn | 21.6 kn |
| 17:00 | 16Z | 327°     | 12.0 kn | 22.4 kn |
| 18:00 | 17Z | 326°     | 11.1 kn | 22.4 kn |

ECMWF IFS 06z at the nearest grid point (no gust in retained fields):

| UTC | Wind dir | Speed | MSLP |
|-----|----------|-------|------|
| 12Z | 345°     | 12.2 kn | 1022.8 hPa |
| 15Z | 343°     | 11.9 kn | 1021.2 hPa |
| 18Z | 342°     | 11.3 kn | 1020.5 hPa |

Two models agree: classic Cascais **Nortada** — NNW gradient wind, 11–12 kn
mean with gusts to ~22 kn, veering a couple of degrees left through the
afternoon as MSLP drops slightly.

## Decoding

```python
import pygrib, math
LAT, LON = 38.68, -9.42
with pygrib.open("data/wind/2026-09-08/icon-eu-06z/"
                 "icon-eu_europe_regular-lat-lon_single-level_"
                 "2026090806_008_U_10M.grib2") as gr:
    m = gr[1]
    lats, lons = m.latlons()
    j, i = divmod(((lats-LAT)**2 + (lons-LON)**2).argmin(), lats.shape[1])
    u = m.values[j, i]
# repeat for V_10M, VMAX_10M; speed = hypot(u,v)*1.9438 kn; dir = atan2(-u,-v).
```
