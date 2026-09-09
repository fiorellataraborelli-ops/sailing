#!/usr/bin/env python3
"""Fetch the Cascais race-area wind and write data/wind.json.

Three-model consensus (ICON-EU, ECMWF IFS, GFS) at the race area, reduced to
the racing window and corrected by the bias the fleet itself measured.

Run locally, or every three hours by .github/workflows/wind-refresh.yml.
"""
import json, math, os, statistics as st, subprocess, urllib.request, datetime

LAT, LON = 38.68, -9.42
MODELS = ['icon_eu', 'ecmwf_ifs025', 'gfs_seamless']
BIAS = 16.1          # deg; mean of three measured races (+19.1, +18.0, +11.2).
                     # Not a constant: it shrank through 8 Sep as the model backed
                     # further than the water did. Re-derive it as races are added.
TACK = 80.5          # deg; the fleet's own measured tacking angle
MIN_KN_FOR_BIAS = 8  # below this the correction is not valid (see README)
HOURS = range(11, 19)
LAST_DAY = '2026-09-11'   # regatta ends Friday

URL = (f"https://api.open-meteo.com/v1/forecast?latitude={LAT}&longitude={LON}"
       "&hourly=wind_speed_10m,wind_direction_10m,wind_gusts_10m,pressure_msl"
       "&wind_speed_unit=kn&timezone=Europe%2FLisbon&forecast_days=5"
       f"&models={','.join(MODELS)}")

def get(url):
    """Some Python installs (notably python.org builds on macOS) ship without
    root certificates, so fall back to curl, which uses the system trust store."""
    try:
        with urllib.request.urlopen(url, timeout=45) as r:
            return r.read().decode()
    except Exception:
        return subprocess.run(['curl', '-sS', '--max-time', '45', url],
                              capture_output=True, text=True, check=True).stdout

def circ_mean(a):
    x = sum(math.cos(v * math.pi / 180) for v in a)
    y = sum(math.sin(v * math.pi / 180) for v in a)
    return math.degrees(math.atan2(y, x)) % 360

def spread(a):
    m = circ_mean(a)
    return max(abs((v - m + 180) % 360 - 180) for v in a)

def main():
    h = json.loads(get(URL))['hourly']

    days = {}
    for i, stamp in enumerate(h['time']):
        date, hh = stamp.split('T')
        hr = int(hh[:2])
        if hr not in HOURS or date > LAST_DAY:
            continue
        def col(p):
            return [h[f'{p}_{m}'][i] for m in MODELS if h[f'{p}_{m}'][i] is not None]
        dirs, sp, gu, pr = (col('wind_direction_10m'), col('wind_speed_10m'),
                            col('wind_gusts_10m'), col('pressure_msl'))
        if not dirs:
            continue
        raw, sprd, kn = circ_mean(dirs), spread(dirs), st.mean(sp)
        # The correction was calibrated on a 10-14 kn gradient Nortada. In light
        # air, or when the models simply disagree, do not pretend to a bearing.
        trust = kn >= MIN_KN_FOR_BIAS and sprd <= 30
        days.setdefault(date, []).append({
            'hr': hr, 'raw': round(raw, 1),
            'cor': round((raw - BIAS) % 360, 1) if trust else None,
            'sp': round(sprd, 1), 'kn': round(kn, 1),
            'gust': round(max(gu), 1), 'mslp': round(st.mean(pr), 1),
            'trust': trust,
        })

    out = {
        'generated': datetime.datetime.now(datetime.timezone.utc)
                     .strftime('%Y-%m-%dT%H:%M:%SZ'),
        'source': 'Open-Meteo consensus: ICON-EU, ECMWF IFS 0.25, GFS',
        'position': {'lat': LAT, 'lon': LON},
        'bias_deg': BIAS, 'tack_deg': TACK, 'min_kn_for_bias': MIN_KN_FOR_BIAS,
        'days': [{'date': d, 'rows': days[d]} for d in sorted(days)],
    }
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        'data', 'wind.json')
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        json.dump(out, f, indent=1)
    print(f"wrote {path}")
    for d in out['days']:
        r = d['rows']
        cors = [x['cor'] for x in r if x['cor'] is not None]
        band = f"{cors[0]:.0f}->{cors[-1]:.0f} deg" if cors else "direction not meaningful"
        print(f"  {d['date']}  {r[0]['kn']:.0f}-{max(x['kn'] for x in r):.0f} kn, "
              f"gust {max(x['gust'] for x in r):.0f}, {band}")

if __name__ == '__main__':
    main()
