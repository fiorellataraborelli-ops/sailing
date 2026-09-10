#!/usr/bin/env python3
"""Start analysis for races 1 and 2 -> site/payload.json['start'].

The coaching brief asks for four numbers at the gun — distance, time, speed,
angle — and this is the one section never built, because the payload only ever
carried distance and along-line position. All four come out of the logs.

Distance and along-line position come from start_line.py, which reads the
committee's own line ends out of the VKX 0x05 rows. Time is measured, not
divided: walk the track forward from the gun until the boat's signed distance
to the line crosses zero, and that is when it actually started. Angle is COG at
the gun against the measured first-beat wind, so it reads as a true wind angle
rather than a compass bearing nobody can act on.

One figure needs the whole fleet rather than one boat: gap to the leader a
minute after the gun, taken as windward progress along the wind axis relative
to the best boat in the tracked fleet.
"""
import sys, glob, os, json, re, math, datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.sailing_agents.vkx_parser import parse_file
from src.sailing_agents import race_multi_leg as rml
from src.sailing_agents import start_line as sl

SRC = os.path.expanduser('~/Downloads/Sailing Files')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DAY = '2026-09-08'
WIND = {1: 317, 2: 314}          # measured first upwind, from the event reports
MS = 1.9438444924406            # m/s -> knots
MAP = {'vakaros': 'Team Sweden', 'MLC USA 26 primary': 'MidlifeCrisis', 'Bábá': 'Ba ba',
       'Aretê 1872': 'Areté', 'SASSY too': 'Sassy', 'Moore DRV - vakaros 2': 'Moore DRV',
       'TYRA VAKAROS': 'TYRA', 'To Nessa 1527': 'To Nessa', 'Patakin_3': 'Patakin 3',
       'JCurve2026': 'JCurve', 'Nautique J70': 'Nautique', 'Mike’s Vakaros': "Mike's Vakaros"}
name = lambda n: MAP.get(re.sub(r'\s+\d+$', '', re.sub(r'\.vkx.*$', '', n)).strip(),
                         re.sub(r'\s+\d+$', '', re.sub(r'\.vkx.*$', '', n)).strip())


def cross_time_s(log, gun_ms, pin, boat, sign, window_s=180):
    """Seconds after the gun that the boat's signed distance to the line reaches zero.

    Negative means it was already across when the gun went — over early. None means
    it had not crossed within the window, which no boat here does.
    """
    prev = None
    for q in log.positions:
        dt = (q[0] - gun_ms) / 1000
        if dt < -60 or dt > window_s:
            continue
        rel = sl.position_vs_line((q[1], q[2]), pin, boat, sign)
        if rel is None:
            continue
        d = rel['distance_to_line_m']
        if prev is not None and prev[1] > 0 >= d:
            # linear interpolation between the fix behind and the fix across
            f = prev[1] / (prev[1] - d) if prev[1] != d else 0
            return round(prev[0] + (dt - prev[0]) * f, 1)
        prev = (dt, d)
    return None


def progress_m(log, gun_ms, at_s, wind_deg):
    """Distance made good along the wind axis between the gun and gun + at_s."""
    a = sl.position_at(log, gun_ms)
    b = sl.position_at(log, gun_ms + int(at_s * 1000))
    if a is None or b is None:
        return None
    north = (b[1] - a[1]) * sl.M_PER_DEG_LAT
    east = (b[2] - a[2]) * sl.M_PER_DEG_LAT * math.cos(math.radians(a[1]))
    # wind_deg is the direction the wind comes FROM, which is also the bearing of the
    # windward mark — sailing upwind means sailing into it. Adding 180 here pointed the
    # axis downwind and made every boat lose ground off the start line.
    up = math.radians(wind_deg)
    return round(north * math.cos(up) + east * math.sin(up), 1)


def main():
    out = {}
    seen = set()
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
        if day != DAY:
            continue
        b = name(os.path.basename(p))
        if b in seen:
            continue
        seen.add(b)

        for rn, (s, e) in enumerate(rml.race_windows(log), 1):
            if rn not in WIND:
                continue
            a = sl.start_analysis(log, s)
            if not a:
                continue
            pin, cb = sl.line_at(log, s)
            sign = sl.resolve_course_side(log, s, pin, cb)
            fix = sl.position_at(log, s)
            cog = math.degrees(fix[4]) % 360
            twa = abs(((cog - WIND[rn] + 180) % 360) - 180)
            out.setdefault(str(rn), []).append({
                'boat': b,
                'dist_m': a['distance_to_line_m'],
                'late_s': cross_time_s(log, s, pin, cb, sign),
                'sog': a['sog_at_gun_kn'],
                'cog': round(cog, 1),
                'twa': round(twa, 1),
                'along': a['along_line_from_pin'],
                'third': a['started_on'],
                'gain60': progress_m(log, s, 60, WIND[rn]),
                'line_m': a['line_length_m'],
            })
            print(f'  r{rn} {b:22} {a["distance_to_line_m"]:6.1f} m  '
                  f'{str(out[str(rn)][-1]["late_s"]):>6} s  {a["sog_at_gun_kn"]:5.2f} kn  '
                  f'twa {twa:5.1f}  +60s {out[str(rn)][-1]["gain60"]}')

    # gap to the best boat a minute after the gun
    for rn, rows in out.items():
        best = max((r['gain60'] for r in rows if r['gain60'] is not None), default=None)
        for r in rows:
            r['behind60'] = None if r['gain60'] is None or best is None else round(r['gain60'] - best)
        rows.sort(key=lambda r: (r['behind60'] is None, -(r['behind60'] or 0)))

    pj = os.path.join(ROOT, 'site/payload.json')
    D = json.load(open(pj))
    D['start'] = {
        'source': 'VKX line-position rows and 0.5 s tracks; wind from the event reports',
        'races': out,
        'note': 'Distance is perpendicular to the committee line at the gun, positive behind it. '
                'Time is measured by walking the track forward to the crossing, not distance '
                'divided by speed. Angle is COG at the gun against the measured first-beat wind. '
                'Behind at +60 s is windward progress along the wind axis against the best boat '
                'in the tracked fleet.',
    }
    json.dump(D, open(pj, 'w'), ensure_ascii=False)
    print('\nwrote payload["start"]:', {k: len(v) for k, v in out.items()})


if __name__ == '__main__':
    main()
