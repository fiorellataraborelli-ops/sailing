#!/usr/bin/env python3
"""Compact plan-view tracks -> site/payload.json['tracks'].

data/v1/tracks holds 2 s fixes and runs to 6 MB, which is fine for a download and
hopeless for a phone. This resamples to 20 s, converts to integer metres from a
per-race origin, and stores each track as a first point plus steps — a boat covers
60-80 m in 20 s, so the deltas are two digits where the absolutes are four. The
whole fleet for both races lands near 100 KB, and at 20 s a point is about 10 px
on a 600 px render of a 4 km course.
"""
import json, glob, math, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STEP_S = 20
M = 111320.0


def main():
    idx = json.load(open(os.path.join(ROOT, 'data/v1/tracks/index.json')))
    out = {}
    for race in ('1', '2'):
        files = sorted(glob.glob(os.path.join(ROOT, f'data/v1/tracks/*-r{race}.json')))
        if not files:
            continue
        ts = [json.load(open(f)) for f in files]
        lat0 = min(min(t['lat']) for t in ts)
        lon0 = min(min(t['lon']) for t in ts)
        cs = math.cos(math.radians(lat0))
        boats, allx, ally = {}, [], []
        for t in ts:
            step = max(1, round(STEP_S / t['step_s']))
            xs, ys, bounds, seen = [], [], [], set()
            for n, i in enumerate(range(0, t['n'], step)):
                xs.append(round((t['lon'][i] - lon0) * M * cs))
                ys.append(round((t['lat'][i] - lat0) * M))
                lg = t['leg'][i]
                if lg not in seen:
                    seen.add(lg)
                    bounds.append([lg, n])
            allx += xs
            ally += ys
            boats[t['boat']] = {
                'x': [xs[0]] + [xs[i] - xs[i-1] for i in range(1, len(xs))],
                'y': [ys[0]] + [ys[i] - ys[i-1] for i in range(1, len(ys))],
                'b': bounds,
            }
        # the clock cannot be counted off the point index: fixes are nominally 0.5 s but
        # drift, so 2 s resampling loses about 11 minutes over a 97 minute race. Carry the
        # real elapsed time instead, median across the fleet.
        import datetime as _dt
        secs = sorted(
            (_dt.datetime.strptime(t['end_utc'], '%Y-%m-%dT%H:%M:%SZ') -
             _dt.datetime.strptime(t['start_utc'], '%Y-%m-%dT%H:%M:%SZ')).total_seconds()
            for t in ts)
        out[race] = {
            'dur_s': int(secs[len(secs) // 2]),
            'boats': boats,
            'marks': [[round((m['lon'] - lon0) * M * cs), round((m['lat'] - lat0) * M),
                       m['after_leg'], m['spread_m']] for m in idx['marks_estimated'][race]],
            'x0': min(allx), 'y0': min(ally),
            'w': max(allx) - min(allx), 'h': max(ally) - min(ally),
            'step_s': STEP_S,
        }

    pj = os.path.join(ROOT, 'site/payload.json')
    D = json.load(open(pj))
    D['tracks'] = out
    json.dump(D, open(pj, 'w'), ensure_ascii=False)
    kb = len(json.dumps(out, separators=(',', ':'))) / 1024
    print(f'wrote payload["tracks"]: ' +
          ', '.join(f'race {k} {len(v["boats"])} boats' for k, v in out.items()) +
          f' — {kb:.0f} KB')


if __name__ == '__main__':
    main()
