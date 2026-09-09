#!/usr/bin/env python3
"""Downsampled race tracks -> data/v1/tracks/.

The full logs are 0.5 s and 34 files deep; nothing on a web page needs that.
This writes one columnar JSON per boat per race at 2 s, tagged with the leg the
fix belongs to, plus an estimated mark position per race taken as the median of
every boat's leg boundary. Marks are inferred from track reversals, not
recorded by the instrument, so they carry unknown error and are labelled as
estimates everywhere they appear.
"""
import sys, glob, os, json, re, datetime, math, statistics as st
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.sailing_agents.vkx_parser import parse_file
from src.sailing_agents import race_multi_leg as rml

SRC = os.path.expanduser('~/Downloads/Sailing Files')
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data/v1/tracks')
STEP_S = 2
WIND = {1: [317, 323, 313, 317], 2: [314, 321, 313, 313], 3: [313, 316, 307, 316]}
MAP = {'vakaros': 'Team Sweden', 'MLC USA 26 primary': 'MidlifeCrisis', 'Bábá': 'Ba ba',
       'Aretê 1872': 'Areté', 'SASSY too': 'Sassy', 'Moore DRV - vakaros 2': 'Moore DRV',
       'TYRA VAKAROS': 'TYRA', 'To Nessa 1527': 'To Nessa', 'Patakin_3': 'Patakin 3',
       'JCurve2026': 'JCurve', 'Nautique J70': 'Nautique', 'Mike’s Vakaros': "Mike's Vakaros"}
name = lambda n: MAP.get(re.sub(r'\s+\d+$', '', re.sub(r'\.vkx.*$', '', n)).strip(),
                         re.sub(r'\s+\d+$', '', re.sub(r'\.vkx.*$', '', n)).strip())
slug = lambda s: re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')
iso = lambda ms: datetime.datetime.fromtimestamp(ms / 1000, datetime.timezone.utc)\
                                  .strftime('%Y-%m-%dT%H:%M:%SZ')


def main():
    os.makedirs(OUT, exist_ok=True)
    index, boundaries, seen = [], {}, set()

    for p in sorted(glob.glob(SRC + '/*')):
        if not os.path.isfile(p):
            continue
        try:
            log = parse_file(p)
        except Exception:
            continue
        if not log.positions:
            continue
        day = datetime.datetime.fromtimestamp(log.positions[0][0] / 1000,
                                              datetime.timezone.utc).strftime('%Y-%m-%d')
        if day != '2026-09-08':
            continue
        boat = name(os.path.basename(p))
        if boat in seen:
            continue
        seen.add(boat)

        for rn, (s, e) in enumerate(rml.race_windows(log), 1):
            if rn > 3:
                continue
            race = rml.segment_race(log, s, e, rn, wind_deg=WIND.get(rn, WIND[1])[0])
            if len(race.legs) < 3:
                continue
            legs = race.legs[:4]
            tr = [q for q in log.positions if s <= q[0] <= e]
            if not tr:
                continue

            # leg index per fix: 1..4 inside a leg, 0 before the first / after the last
            def leg_of(ts):
                for i, l in enumerate(legs, 1):
                    if l.start_ts_ms <= ts <= l.end_ts_ms:
                        return i
                return 0

            t0 = tr[0][0]
            step_ms, nxt = STEP_S * 1000, t0
            lat, lon, sog, cog, lg, tsec = [], [], [], [], [], []
            for q in tr:
                if q[0] < nxt:
                    continue
                nxt = q[0] + step_ms
                lat.append(round(q[1], 6))
                lon.append(round(q[2], 6))
                sog.append(round(q[3] * 1.9438444924406, 2))       # m/s -> knots
                cog.append(round(math.degrees(q[4]) % 360, 1))
                lg.append(leg_of(q[0]))
                tsec.append(round((q[0] - t0) / 1000, 1))

            rec = {
                'boat': boat, 'race': rn, 'date': day,
                'start_utc': iso(t0), 'end_utc': iso(tr[-1][0]),
                'step_s': STEP_S, 'n': len(lat),
                'units': {'lat': 'deg', 'lon': 'deg', 't': 's since start_utc',
                          'sog': 'kn', 'cog': 'deg true', 'leg': '1-4, 0 = outside a leg'},
                'legs': [{'n': i, 'kind': l.kind,
                          'wind_deg': WIND.get(rn, WIND[1])[min(i - 1, 3)],
                          'start_utc': iso(l.start_ts_ms), 'end_utc': iso(l.end_ts_ms)}
                         for i, l in enumerate(legs, 1)],
                't': tsec, 'lat': lat, 'lon': lon, 'sog': sog, 'cog': cog, 'leg': lg,
            }
            fn = f'{slug(boat)}-r{rn}.json'
            with open(os.path.join(OUT, fn), 'w') as f:
                json.dump(rec, f, separators=(',', ':'), ensure_ascii=False)
            index.append({'boat': boat, 'race': rn, 'file': 'tracks/' + fn,
                          'n': len(lat), 'bytes': os.path.getsize(os.path.join(OUT, fn))})

            # leg boundaries -> estimated mark positions
            for i, l in enumerate(legs, 1):
                at = min(tr, key=lambda q: abs(q[0] - l.end_ts_ms))
                boundaries.setdefault((rn, i), []).append((at[1], at[2]))
            print(f'  {boat:22} race {rn}  {len(lat):5} pts')

    marks = {}
    for (rn, i), pts in sorted(boundaries.items()):
        if len(pts) < 3:
            continue
        marks.setdefault(str(rn), []).append({
            'after_leg': i,
            'lat': round(st.median(p[0] for p in pts), 6),
            'lon': round(st.median(p[1] for p in pts), 6),
            'n_boats': len(pts),
            'spread_m': round(st.median(
                [math.hypot((p[0] - st.median(q[0] for q in pts)) * 111320,
                            (p[1] - st.median(q[1] for q in pts)) * 111320 *
                            math.cos(math.radians(p[0]))) for p in pts]), 1),
        })

    with open(os.path.join(OUT, 'index.json'), 'w') as f:
        json.dump({
            'note': 'One file per boat per race, columnar arrays of equal length.',
            'step_s': STEP_S, 'date': '2026-09-08', 'n_files': len(index),
            'marks_estimated': marks,
            'marks_note': 'Median leg-boundary position across boats. The Atlas does not '
                          'record mark roundings, so these are inferred from track reversals; '
                          'spread_m is the median distance of individual boats from that median.',
            'files': index,
        }, f, indent=1, ensure_ascii=False)
    print(f'\n{len(index)} track files, {sum(i["bytes"] for i in index) / 1e6:.1f} MB')


if __name__ == '__main__':
    main()
