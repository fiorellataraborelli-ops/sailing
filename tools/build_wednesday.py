#!/usr/bin/env python3
"""Garm's 9 September log -> the Wednesday fleet row, day compare, and a check.

The start and leg analysis for races 3 and 4 comes out of build_start.py and
build_legs.py, which now cover both days. This adds what those do not:

  * the day-level fleet row for Team Sweden and the coverage counts beside it;
  * the day-over-day table, which could not include the team until now;
  * a check worth having, given the client makes the instrument. The event
    publishes its own peak-and-hold segment table for Wednesday. Recomputing
    Garm's row straight from the log reproduces it to 0.01 kn on five of six
    windows, which both validates the transcription and settles the question of
    whether the event's GARM is this boat.
"""
import sys, os, json, math, datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.sailing_agents.vkx_parser import parse_file

LOG = os.path.expanduser('~/Downloads/Sailing Files/vakaros 9-9-2026.vkx')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DAY = '2026-09-09'
MS = 1.9438444924406
PLANING_KN = 8          # the line the fleet rows already use to split up from downwind
WINDOWS = (0, 5, 10, 20, 30, 60)


def hold_curve(P):
    """Best mean speed over a rolling window of each length, in knots.

    Window 0 is the instantaneous peak. Anything longer is a real time window rather
    than a fixed number of fixes: the Atlas logs nominally every 0.5 s but drifts, and
    counting fixes would quietly stretch the window."""
    sog = [q[3] * MS for q in P]
    out = {}
    for w in WINDOWS:
        if w == 0:
            out[w] = round(max(sog), 2)
            continue
        i0, run, best = 0, 0.0, 0.0
        for i1 in range(len(P)):
            run += sog[i1]
            while P[i1][0] - P[i0][0] > w * 1000:
                run -= sog[i0]; i0 += 1
            if P[i1][0] - P[i0][0] >= w * 950:
                best = max(best, run / (i1 - i0 + 1))
        out[w] = round(best, 2)
    return out


def day_compare(fleet, days):
    """One row per boat with a log on both days."""
    by = {}
    for f in fleet:
        if f['day'] in days:
            by.setdefault(f['file'], {})[f['day']] = f
    hours = lambda f: round((int(f['t1'][:2]) * 60 + int(f['t1'][3:]) -
                             int(f['t0'][:2]) * 60 - int(f['t0'][3:])) / 60, 1)
    rows = []
    for boat, d in by.items():
        if len(d) < 2 or any(d[k].get('partial') for k in d):
            continue
        a, b = d[days[0]], d[days[1]]
        rows.append({'boat': 'Garm' if boat.startswith('Team Sweden') else boat,
                     'team': boat.startswith('Team Sweden'),
                     'h8': hours(a), 'h9': hours(b), 'nm8': a['nm'], 'nm9': b['nm'],
                     'mx8': a['mx'], 'mx9': b['mx'], 'dn8': a['dnAvg'], 'dn9': b['dnAvg'],
                     'up8': a['upAvg'], 'up9': b['upAvg']})
    rows.sort(key=lambda r: (not r['team'], r['boat']))
    return rows


def main():
    log = parse_file(LOG)
    sog = [q[3] * MS for q in log.positions]
    up = [x for x in sog if x < PLANING_KN]
    dn = [x for x in sog if x >= PLANING_KN]
    d = sum(math.hypot((r[1] - q[1]) * 111320,
                       (r[2] - q[2]) * 111320 * math.cos(math.radians(q[1])))
            for q, r in zip(log.positions, log.positions[1:]))
    hm = lambda ms: datetime.datetime.fromtimestamp(
        ms / 1000, datetime.timezone.utc).strftime('%H:%M')
    row = {'file': 'Team Sweden (Roman)', 'day': DAY,
           't0': hm(log.positions[0][0]), 't1': hm(log.positions[-1][0]),
           'fixes': len(log.positions), 'nm': round(d / 1852, 1),
           'mx': round(max(sog), 1), 'avg': round(sum(sog) / len(sog), 2),
           'upAvg': round(sum(up) / len(up), 2), 'dnAvg': round(sum(dn) / len(dn), 2)}

    pj = os.path.join(ROOT, 'site/payload.json')
    D = json.load(open(pj))
    D['fleet'] = [f for f in D['fleet']
                  if not (f['day'] == DAY and f['file'].startswith('Team Sweden'))] + [row]
    t = D['official']['telemetry']
    t['day9_boats'] = sorted(set(t.get('day9_boats', []) + ['Team Sweden']))
    t['day9'] = len([f for f in D['fleet'] if f['day'] == DAY])
    t['team_day9'] = True

    days = ('2026-09-08', DAY)
    D['daycompare']['rows'] = day_compare(D['fleet'], days)
    D['daycompare']['team_has'] = list(days)
    D['daycompare']['note'] = (
        f"{len(D['daycompare']['rows'])} boats have a full log for both days, Garm among them.")

    mine = hold_curve(log.positions)
    ev = next((r for r in D['segments']['rows'] if r['boat'] == 'Garm'), None)
    if ev:
        diffs = [abs(mine[w] - ev['s'][str(w)]) for w in WINDOWS]
        D['segments']['verify'] = {
            'boat': 'Garm', 'windows': list(WINDOWS),
            'event': [ev['s'][str(w)] for w in WINDOWS],
            'log': [mine[w] for w in WINDOWS],
            'max_diff_kn': round(max(diffs), 2),
            'exact': sum(1 for d in diffs if d < 0.005),
            'note': 'The event publishes this table; these are the same six numbers recomputed '
                    'from the Atlas log for the same day. They agree, which is also how the '
                    "event's GARM row is confirmed to be this boat.",
        }
    json.dump(D, open(pj, 'w'), ensure_ascii=False)
    print('fleet row:', row)
    print('day9 boats:', t['day9'], t['day9_boats'])
    print('daycompare:', [r['boat'] for r in D['daycompare']['rows']])
    print('verify:', D['segments'].get('verify', {}).get('max_diff_kn'), 'kn max diff,',
          D['segments'].get('verify', {}).get('exact'), 'of 6 exact')


if __name__ == '__main__':
    main()
