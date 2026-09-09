#!/usr/bin/env python3
"""Wind-referenced leg analysis for the whole fleet -> site/payload.json['legs'].

Race windows come from the loggers' own RACE_START/RACE_END timer events. That
choice is validated, not assumed: segmenting Patakin 3's race 1 from the 12:05
timer start reproduces the independently-derived leg durations 31.97 / 16.87 /
25.94 min exactly, and yields clean beat/run/beat/run at TWA 10 and 171. The
alternative start published in the event report puts the boat mid-race.
"""
import sys, glob, os, json, re, datetime, math, statistics as st
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.sailing_agents.vkx_parser import parse_file
from src.sailing_agents import race_multi_leg as rml
from src.sailing_agents.leg_vmg import leg_vmg, manoeuvres

SRC = os.path.expanduser('~/Downloads/Sailing Files')
WIND = {1: [317, 323, 313, 317], 2: [314, 321, 313, 313], 3: [313, 316, 307, 316]}
MAP = {'vakaros': 'Team Sweden', 'MLC USA 26 primary': 'MidlifeCrisis', 'Bábá': 'Ba ba',
       'Aretê 1872': 'Areté', 'SASSY too': 'Sassy', 'Moore DRV - vakaros 2': 'Moore DRV',
       'TYRA VAKAROS': 'TYRA', 'To Nessa 1527': 'To Nessa', 'Patakin_3': 'Patakin 3',
       'JCurve2026': 'JCurve', 'Nautique J70': 'Nautique', 'Mike’s Vakaros': "Mike's Vakaros"}
name = lambda n: MAP.get(re.sub(r'\s+\d+$', '', re.sub(r'\.vkx.*$', '', n)).strip(),
                         re.sub(r'\s+\d+$', '', re.sub(r'\.vkx.*$', '', n)).strip())

def pearson(x, y):
    mx, my = st.mean(x), st.mean(y)
    sx = math.sqrt(sum((a - mx) ** 2 for a in x)); sy = math.sqrt(sum((b - my) ** 2 for b in y))
    return round(sum((a - mx) * (b - my) for a, b in zip(x, y)) / (sx * sy), 2) if sx and sy else 0.0

def main():
    races, seen = {}, set()
    for p in sorted(glob.glob(SRC + '/*')):
        if not os.path.isfile(p): continue
        try: log = parse_file(p)
        except Exception: continue
        if not log.positions: continue
        day = datetime.datetime.fromtimestamp(log.positions[0][0] / 1000,
                                              datetime.timezone.utc).strftime('%Y-%m-%d')
        if day != '2026-09-08': continue
        b = name(os.path.basename(p))
        if b in seen: continue
        seen.add(b)
        for rn, (s, e) in enumerate(rml.race_windows(log), 1):
            if rn > 3: continue
            w = WIND.get(rn, WIND[1])
            race = rml.segment_race(log, s, e, rn, wind_deg=w[0])
            if len(race.legs) < 3: continue
            tr = [q for q in log.positions if s <= q[0] <= e]
            legs = []
            for i, l in enumerate(race.legs[:4]):
                sub = [q for q in tr if l.start_ts_ms <= q[0] <= l.end_ts_ms]
                wd = w[i] if i < len(w) else w[-1]
                v = leg_vmg(sub, wd, l.kind == 'beat')
                m = manoeuvres(sub, wd)
                tk = [x for x in m if x['kind'] == 'tack']
                gy = [x for x in m if x['kind'] == 'gybe']
                legs.append({'n': i + 1, 'kind': l.kind, 'wind': wd,
                             'min': round(l.duration_min, 1), 'sog': v.get('avg_sog_kn'),
                             'vmg': v.get('avg_vmg_kn'), 'twa': v.get('avg_twa_deg'),
                             'eff': v.get('vmg_efficiency'),
                             'extra': round(l.path_m - l.straight_line_m),
                             'tacks': len(tk), 'gybes': len(gy),
                             'tloss': round(st.mean([x['loss_kn'] for x in tk]), 2) if tk else None,
                             'gloss': round(st.mean([x['loss_kn'] for x in gy]), 2) if gy else None})
            races.setdefault(str(rn), {})[b] = legs

    out = {'source': 'race_multi_leg segmentation + leg_vmg, per-leg winds from the event reports',
           'races': races, 'drivers': {}}
    for rn, R in races.items():
        L = [l[0] for l in R.values() if l and l[0]['kind'] == 'beat']
        if len(L) < 8: continue
        vm = [x['vmg'] for x in L]
        out['drivers'][rn] = {'n': len(L),
            'median_vmg': round(st.median(vm), 2),
            'r_tacks': pearson([x['tacks'] for x in L], vm),
            'r_extra': pearson([x['extra'] for x in L], vm),
            'r_twa':   pearson([x['twa'] for x in L], vm),
            'r_eff':   pearson([x['eff'] for x in L], vm)}
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    d = json.load(open(root + '/site/payload.json'))
    d['legs'] = out
    json.dump(d, open(root + '/site/payload.json', 'w'), ensure_ascii=False)
    print(f"legs written: races {sorted(races)}, boats "
          f"{ {k: len(v) for k, v in races.items()} }")

if __name__ == '__main__':
    main()
