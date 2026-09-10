#!/usr/bin/env python3
"""Wind-referenced leg analysis for the whole fleet -> site/payload.json['legs'].

Race windows come from the loggers' own RACE_START/RACE_END timer events. That
choice is validated, not assumed: segmenting Patakin 3's race 1 from the 12:05
timer start reproduces the independently-derived leg durations 31.97 / 16.87 /
25.94 min exactly, and yields clean beat/run/beat/run at TWA 10 and 171. The
alternative start published in the event report puts the boat mid-race.

The window runs to the logger's RACE_END, which is later than the finish — the
crew stops the timer when they get round to it, and the boat sails home in the
meantime. Left alone that inflates the fourth leg by minutes and drags its
average speed down with sail-home data: Garm's Tuesday race 1 read 21.2 min at
9.3 kn against a 16.9 min second run at 11.7 kn. finish_ts() cuts it at the
finish instead; see there for how, and for what it is calibrated against.
"""
import sys, glob, os, json, re, datetime, math, statistics as st
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.sailing_agents.vkx_parser import parse_file
from src.sailing_agents import race_multi_leg as rml
from src.sailing_agents.leg_vmg import leg_vmg, manoeuvres, STEADY_WINDOW_S

SRC = os.path.expanduser('~/Downloads/Sailing Files')
MS = 1.9438444924406

# Which race each day's race windows belong to, in order. Explicit rather than
# "window n = race n": Wednesday's first window is race 3, and one Tuesday boat
# leaves a spare window behind that would otherwise be scored as a race.
RACE_OF_WINDOW = {'2026-09-08': {1: '1', 2: '2'}, '2026-09-09': {1: '3', 2: '4'}}
WIND = {'1': [317, 323, 313, 317], '2': [314, 321, 313, 313],
        '3': [324, 327, 326, 332], '4': [335, 341, 342, 349]}
MAP = {'vakaros': 'Team Sweden', 'MLC USA 26 primary': 'MidlifeCrisis', 'Bábá': 'Ba ba',
       'Aretê 1872': 'Areté', 'SASSY too': 'Sassy', 'Moore DRV - vakaros 2': 'Moore DRV',
       'TYRA VAKAROS': 'TYRA', 'To Nessa 1527': 'To Nessa', 'Patakin_3': 'Patakin 3',
       'JCurve2026': 'JCurve', 'Nautique J70': 'Nautique', 'Mike’s Vakaros': "Mike's Vakaros"}


def name(fn):
    """Boat from filename: drop the extension, then a trailing date, then a copy number."""
    s = re.sub(r'\.vkx.*$', '', fn).strip()
    s = re.sub(r'\s+\d{1,2}-\d{1,2}-\d{4}$', '', s).strip()   # "vakaros 9-9-2026"
    s = re.sub(r'\s+\d+$', '', s).strip()                      # "vakaros 10"
    return MAP.get(s, s)


def rolling_kn(tr, win_s=30):
    """Centred rolling mean speed, one value per fix."""
    out, n, j0, j1 = [], len(tr), 0, 0
    for q in tr:
        while tr[j0][0] < q[0] - win_s * 500: j0 += 1
        while j1 < n and tr[j1][0] <= q[0] + win_s * 500: j1 += 1
        seg = tr[j0:j1]
        out.append(sum(x[3] for x in seg) / len(seg) * MS)
    return out


def finish_ts(sub):
    """When the boat finished, from the speed trace alone.

    At the leeward finish the kite comes down and the boat falls off the plane and
    never gets back on it; everything after is sailing home. So: last moment the
    30 s mean speed is still at 60% of what the boat was doing on the leg. The
    threshold is relative rather than a fixed knots figure so a light-air leg is
    not cut at its start.

    Calibrated against the event's own published leg times for Garm on Wednesday:
    race 3 gives 11.1 min against 10:28 published, race 4 12.1 against 11:28. Both
    run about 40 s long, which is the smear of the rolling window — the cut errs
    late, never early.
    """
    if len(sub) < 60:
        return None
    v = rolling_kn(sub)
    thr = 0.6 * st.median(v[:int(len(v) * 0.66)])
    for i in range(len(v) - 1, -1, -1):
        if v[i] >= thr:
            return sub[i][0]
    return None


def pearson(x, y):
    mx, my = st.mean(x), st.mean(y)
    sx = math.sqrt(sum((a - mx) ** 2 for a in x)); sy = math.sqrt(sum((b - my) ** 2 for b in y))
    return round(sum((a - mx) * (b - my) for a, b in zip(x, y)) / (sx * sy), 2) if sx and sy else 0.0


def main():
    races, seen, trims = {}, set(), []
    for p in sorted(glob.glob(SRC + '/*')):
        if not os.path.isfile(p): continue
        try: log = parse_file(p)
        except Exception: continue
        if not log.positions: continue
        day = datetime.datetime.fromtimestamp(log.positions[0][0] / 1000,
                                              datetime.timezone.utc).strftime('%Y-%m-%d')
        if day not in RACE_OF_WINDOW: continue
        b = name(os.path.basename(p))
        if (day, b) in seen: continue
        seen.add((day, b))

        for wi, (s, e) in enumerate(rml.race_windows(log), 1):
            rn = RACE_OF_WINDOW[day].get(wi)
            if rn is None: continue
            w = WIND[rn]
            race = rml.segment_race(log, s, e, int(rn), wind_deg=w[0])
            if len(race.legs) < 4: continue
            tr = [q for q in log.positions if s <= q[0] <= e]
            legs = []
            for i, l in enumerate(race.legs[:4]):
                end = l.end_ts_ms
                if i == 3 and l.kind == 'run':           # the last scored leg ends at the finish
                    ft = finish_ts([q for q in tr if l.start_ts_ms <= q[0] <= end])
                    if ft and end - ft > 45_000:
                        trims.append((rn, b, round((end - ft) / 60000, 1)))
                        end = ft
                sub = [q for q in tr if l.start_ts_ms <= q[0] <= end]
                wd = w[i] if i < len(w) else w[-1]
                m = manoeuvres(sub, wd)
                v = leg_vmg(sub, wd, l.kind == 'beat', mans=m)
                tk = [x for x in m if x['kind'] == 'tack']
                gy = [x for x in m if x['kind'] == 'gybe']
                path = sum(math.hypot((r[1] - q[1]) * 111320,
                                      (r[2] - q[2]) * 111320 * math.cos(math.radians(q[1])))
                           for q, r in zip(sub, sub[1:]))
                straight = math.hypot((sub[-1][1] - sub[0][1]) * 111320,
                                      (sub[-1][2] - sub[0][2]) * 111320 *
                                      math.cos(math.radians(sub[0][1])))
                legs.append({'n': i + 1, 'kind': l.kind, 'wind': wd,
                             'min': round((end - l.start_ts_ms) / 60000, 1),
                             'sog': v.get('avg_sog_kn'),
                             'vmg': v.get('avg_vmg_kn'), 'twa': v.get('avg_twa_deg'),
                             'eff': v.get('vmg_efficiency'),
                             # the same leg with the turns taken out: boat speed rather
                             # than boat speed diluted by manoeuvre count
                             'svmg': v.get('steady_vmg_kn'), 'ssog': v.get('steady_sog_kn'),
                             'stwa': v.get('steady_twa_deg'), 'keep': v.get('steady_share'),
                             'extra': round(path - straight),
                             'tacks': len(tk), 'gybes': len(gy),
                             'tloss': round(st.mean([x['loss_kn'] for x in tk]), 2) if tk else None,
                             'gloss': round(st.mean([x['loss_kn'] for x in gy]), 2) if gy else None})
            races.setdefault(rn, {})[b] = legs

    out = {'source': 'race_multi_leg segmentation + leg_vmg, per-leg winds from the event reports',
           'races': races, 'drivers': {}, 'steady_window_s': STEADY_WINDOW_S,
           'note': 'The fourth leg is cut at the finish, detected as the boat coming off the '
                   'plane, not at the logger\'s RACE_END — that runs on into the sail home. '
                   'Checked against the event\'s published leg times for races 3 and 4: about '
                   '40 s long, never short.'}
    for rn, R in races.items():
        L = [l[0] for l in R.values() if l and l[0]['kind'] == 'beat']
        if len(L) < 8: continue
        vm = [x['vmg'] for x in L]
        sv = [x['svmg'] for x in L]
        out['drivers'][rn] = {'n': len(L),
            'median_vmg': round(st.median(vm), 2),
            'median_svmg': round(st.median(sv), 2),
            'r_tacks': pearson([x['tacks'] for x in L], vm),
            'r_extra': pearson([x['extra'] for x in L], vm),
            'r_twa':   pearson([x['twa'] for x in L], vm),
            'r_eff':   pearson([x['eff'] for x in L], vm),
            # the same correlation once turning is out of the average. If tack count
            # only ever predicted VMG because the average included the tacks, this is
            # where it disappears.
            'r_tacks_steady': pearson([x['tacks'] for x in L], sv),
            'r_twa_steady':   pearson([x['stwa'] for x in L], sv)}
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    d = json.load(open(root + '/site/payload.json'))
    d['legs'] = out
    json.dump(d, open(root + '/site/payload.json', 'w'), ensure_ascii=False)
    print(f"legs: { {k: len(v) for k, v in sorted(races.items())} }")
    print(f"finish trim applied to {len(trims)} final runs, "
          f"median {st.median([t[2] for t in trims]):.1f} min" if trims else "no trims")
    for t in sorted(trims, key=lambda x: -x[2])[:6]:
        print(f'   r{t[0]} {t[1]:22} -{t[2]} min')


if __name__ == '__main__':
    main()
