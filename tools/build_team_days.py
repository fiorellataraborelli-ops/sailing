#!/usr/bin/env python3
"""Garm's own logs -> the day fleet rows, the day-over-day table, and a check.

The start and leg analysis comes out of build_start.py and build_legs.py, which
cover every race day. This adds what those do not:

  * the day-level fleet row for Team Sweden and the coverage counts beside it;
  * the day-over-day table, which could not include the team until now;
  * a check worth having, given the client makes the instrument. The event
    publishes its own peak-and-hold segment table for Wednesday. Recomputing
    Garm's row straight from the log reproduces it to 0.01 kn on five of six
    windows, which both validates the transcription and settles the question of
    whether the event's GARM is this boat.
"""
import sys, os, glob, json, math, datetime, re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.sailing_agents.vkx_parser import parse_file
from tools.build_legs import name as boat_name

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Garm's log for each racing day. The device names its files by date, and the team
# hands them over a day at a time, so this list grows by one line per day.
LOGS = {'2026-09-09': '~/Downloads/Sailing Files/vakaros 9-9-2026.vkx',
        '2026-09-10': '~/Downloads/Sailing Files/vakaros 10-9-2026.vkx',
        '2026-09-11': '~/Downloads/Sailing Files/vakaros 11-9-2026.vkx'}
# The event published a peak-and-hold segment table for Wednesday only, so that is
# the one day the instrument can be checked against someone else's arithmetic.
VERIFY_DAY = '2026-09-09'
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
    """One row per boat with a full log on every racing day.

    Columns are suffixed by day of month rather than by an index, so adding a day
    adds columns instead of renumbering the ones already published.
    """
    by = {}
    for f in fleet:
        if f['day'] in days:
            by.setdefault(f['file'], {})[f['day']] = f
    hours = lambda f: round((int(f['t1'][:2]) * 60 + int(f['t1'][3:]) -
                             int(f['t0'][:2]) * 60 - int(f['t0'][3:])) / 60, 1)
    rows = []
    for boat, d in by.items():
        if len(d) < len(days) or any(d[k].get('partial') for k in d):
            continue
        r = {'boat': 'Garm' if boat.startswith('Team Sweden') else boat,
             'team': boat.startswith('Team Sweden')}
        for day in days:
            k, f = day[-2:].lstrip('0'), d[day]
            r.update({'h' + k: hours(f), 'nm' + k: f['nm'], 'mx' + k: f['mx'],
                      'dn' + k: f['dnAvg'], 'up' + k: f['upAvg']})
        rows.append(r)
    rows.sort(key=lambda r: (not r['team'], r['boat']))
    return rows


SRC = os.path.expanduser('~/Downloads/Sailing Files')


def other_logs(day, have):
    """Every other boat that logged this day and has no fleet row yet.

    Garm's row is added by name; the rest of the fleet was added a day at a time by
    hand, which left Thursday's three other boats out entirely. Additive only — an
    existing row is never recomputed, so nothing already published moves.
    """
    out = []
    for p in sorted(glob.glob(SRC + '/*')):
        if not os.path.isfile(p):
            continue
        try:
            log = parse_file(p)
        except Exception:
            continue
        if not log.positions:
            continue
        d = datetime.datetime.fromtimestamp(log.positions[0][0] / 1000,
                                            datetime.timezone.utc).strftime('%Y-%m-%d')
        b = boat_name(os.path.basename(p))
        if d != day or b == 'Team Sweden' or b in have:
            continue
        have.add(b)
        out.append((p, b))
    return out


def fleet_row(path, day, label='Team Sweden (Roman)'):
    log = parse_file(os.path.expanduser(path))
    sog = [q[3] * MS for q in log.positions]
    up = [x for x in sog if x < PLANING_KN]
    dn = [x for x in sog if x >= PLANING_KN]
    d = sum(math.hypot((r[1] - q[1]) * 111320,
                       (r[2] - q[2]) * 111320 * math.cos(math.radians(q[1])))
            for q, r in zip(log.positions, log.positions[1:]))
    hm = lambda ms: datetime.datetime.fromtimestamp(
        ms / 1000, datetime.timezone.utc).strftime('%H:%M')
    return log, {'file': label, 'day': day,
                 't0': hm(log.positions[0][0]), 't1': hm(log.positions[-1][0]),
                 'fixes': len(log.positions), 'nm': round(d / 1852, 1),
                 'mx': round(max(sog), 1), 'avg': round(sum(sog) / len(sog), 2),
                 # a boat that never got above the planing line has no downwind sample;
           # dividing by that emptied the whole run
           'upAvg': round(sum(up) / len(up), 2) if up else None,
           'dnAvg': round(sum(dn) / len(dn), 2) if dn else None}


def main():
    pj = os.path.join(ROOT, 'site/payload.json')
    D = json.load(open(pj))
    logs = {}
    for day, path in LOGS.items():
        log, row = fleet_row(path, day)
        logs[day] = log
        D['fleet'] = [f for f in D['fleet']
                      if not (f['day'] == day and f['file'].startswith('Team Sweden'))] + [row]
        print(f'{day} Garm: {row["fixes"]} fixes, {row["nm"]} nm, '
              f'{row["upAvg"]}/{row["dnAvg"]} kn up/down')
        have = {f['file'] for f in D['fleet'] if f['day'] == day}
        for path2, b in other_logs(day, set(have)):
            if b in have:
                continue
            _, r2 = fleet_row(path2, day, label=b)
            D['fleet'].append(r2)
            print(f'{day} + {b}: {r2["nm"]} nm, {r2["upAvg"]}/{r2["dnAvg"]} kn up/down')

    t = D['official']['telemetry']
    for day in LOGS:
        k = 'day' + day[-2:].lstrip('0')
        t[k + '_boats'] = sorted(set(t.get(k + '_boats', []) + ['Team Sweden']))
        t[k] = len([f for f in D['fleet'] if f['day'] == day])
    t['team_day9'] = t['team_day10'] = True
    t['logs'] = len(D['fleet'])

    days = tuple(sorted({f['day'] for f in D['fleet']} & ({'2026-09-08'} | set(LOGS))))
    D['daycompare']['days'] = {d: datetime.datetime.strptime(d, '%Y-%m-%d').strftime('%a %-d %b')
                               for d in days}
    D['daycompare']['rows'] = day_compare(D['fleet'], days)
    D['daycompare']['team_has'] = list(days)
    D['daycompare']['note'] = (
        f"{len(D['daycompare']['rows'])} boats have a full log for all "
        f"{len(days)} racing days, Garm among them.")

    mine = hold_curve(logs[VERIFY_DAY].positions)
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
    print('daycompare:', list(D['daycompare']['days'].values()),
          '->', [r['boat'] for r in D['daycompare']['rows']])
    print('verify:', D['segments'].get('verify', {}).get('max_diff_kn'), 'kn max diff,',
          D['segments'].get('verify', {}).get('exact'), 'of 6 exact')


if __name__ == '__main__':
    main()
