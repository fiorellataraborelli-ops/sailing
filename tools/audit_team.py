#!/usr/bin/env python3
"""Check the client boat's data against every independent source available.

Garm's numbers are the ones that matter, so they are the ones that get checked
rather than trusted. Nothing here recomputes from the payload alone — each test
compares a published figure against a source that was produced separately:

  * the event's own four-leg analysis of races 3 and 4;
  * the event's scored results and its race-progress report;
  * the Atlas log itself, re-read from disk;
  * and the page as built, so the payload and the deliverable cannot drift apart.

Exit status is non-zero if anything fails, so it can gate a deploy.
"""
import json, os, re, sys, math, datetime, glob

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
TEAM, EVENT_NAME = 'Team Sweden', 'GARM'
ok, bad, warn = [], [], []


def check(name, cond, detail=''):
    (ok if cond else bad).append(f'{name}: {detail}' if detail else name)


def note(name, detail):
    warn.append(f'{name}: {detail}')


def close(a, b, tol):
    return a is not None and b is not None and abs(a - b) <= tol


def main():
    D = json.load(open(os.path.join(ROOT, 'site/payload.json')))
    R = D['legs']['races']
    races = sorted(R, key=int)

    # ---- 1. the team is present everywhere it should be -----------------------
    check('team in every race, legs', all(TEAM in R[r] for r in races), ', '.join(races))
    check('team in every race, starts',
          all(any(x['boat'] == TEAM for x in D['start']['races'][r]) for r in races))
    check('team in every race, tracks',
          all(TEAM in D['tracks'][r]['boats'] for r in races if r in D['tracks']))
    check('four legs in every race', all(len(R[r][TEAM]) == 4 for r in races),
          str({r: len(R[r][TEAM]) for r in races}))

    # ---- 2. against the event's own four-leg analysis (races 3 and 4) ---------
    E = json.load(open(os.path.join(ROOT, 'data/event/races34.json')))
    keys = ['1U', '1D', '2U', '2D']
    for rn in ('3', '4'):
        for i, lk in enumerate(keys):
            row = next((x for x in E['races'][rn]['legs'][lk]['rows'] if x[0] == EVENT_NAME), None)
            if not row:
                continue
            mine = R[rn][TEAM][i]
            ev_sog, ev_vmg, ev_twa, ev_man = row[7], row[8], row[9], row[6]
            # tight on purpose. A loose run tolerance hid a real 2 deg bias in the
            # angle and 0.2 kn in the speed, caused by averaging the mark roundings
            # into the leg; these are the errors that remain once they are trimmed.
            check(f'r{rn} {lk} SOG vs event', close(mine['sog'], ev_sog, 0.35),
                  f"{mine['sog']} vs {ev_sog}")
            check(f'r{rn} {lk} VMG vs event', close(mine['vmg'], ev_vmg, 0.35),
                  f"{mine['vmg']} vs {ev_vmg}")
            check(f'r{rn} {lk} TWA vs event', close(mine['twa'], ev_twa, 2.0),
                  f"{mine['twa']} vs {ev_twa}")
            man = mine['tacks'] + mine['gybes']
            if abs(man - ev_man) > 2:
                note(f'r{rn} {lk} manoeuvre count', f'{man} against the event\'s {ev_man}')

    # ---- 3. against the scored results ---------------------------------------
    RES = json.load(open(os.path.join(ROOT, 'data/event/results.json')))
    g = next(r for r in RES['rows'] if r['boat'].upper() == EVENT_NAME)
    t = D['official']['team']
    check('position matches the results', t['pos'] == g['pos'], f"{t['pos']} vs {g['pos']}")
    check('net points match', close(t['pts'], g['net'], 0.01), f"{t['pts']} vs {g['net']}")
    check('total points match', close(t['total'], g['total'], 0.01))
    check('race scores match', list(t['r']) == list(g['races']))
    check('net = total - discard',
          close(g['net'], g['total'] - g['races'][g['discard'] - 1], 0.01),
          f"{g['net']} vs {g['total']} - {g['races'][g['discard']-1]}")
    # telemetry always lags scoring: a race is scored the evening it is sailed and the
    # logs arrive whenever the fleet hands them over. Legs must be a subset, not equal.
    check('every race with legs is a scored race', len(races) <= RES['races_scored'],
          f"{len(races)} raced with telemetry, {RES['races_scored']} scored")
    if len(races) < RES['races_scored']:
        note('telemetry behind the scoreboard',
             f"legs for {len(races)} of {RES['races_scored']} scored races")

    # ---- 4. against the race-progress report ---------------------------------
    PR = json.load(open(os.path.join(ROOT, 'data/event/progress.json')))
    pg = next(r for r in PR['fleet_rows'] if r['boat'].startswith(EVENT_NAME))
    check('gain total matches progress', t['gain_total'] == pg['gain'])
    check('gain split matches progress', (t['gain_up'], t['gain_down']) == (pg['up'], pg['dn']))
    # the progress report and the scoreboard are published separately and the scoreboard
    # is corrected more often, so a race can legitimately differ until the report catches
    # up. Report it; do not fail on it.
    for row in PR['team_by_race']:
        if row['race'] > len(g['races']):
            continue
        scored = g['races'][row['race'] - 1]
        if not close(float(row['result']), scored, 0.01):
            note(f"r{row['race']} differs between event sources",
                 f"progress report {row['result']}, scoreboard {scored:g} — "
                 f"the scoreboard is the later of the two")
    if PR.get('races_covered', 0) < RES['races_scored']:
        note('progress report behind the scoreboard',
             f"{PR.get('races_covered')} races against {RES['races_scored']} scored")

    # ---- 5. against the log itself, re-read ----------------------------------
    from src.sailing_agents.vkx_parser import parse_file
    from src.sailing_agents import race_multi_leg as rml
    from src.sailing_agents import start_line as sl
    from tools.build_legs import RACE_GUN, race_of, name as boat_name, SRC
    logs = {}
    for p in sorted(glob.glob(SRC + '/*')):
        if not os.path.isfile(p):
            continue
        try:
            log = parse_file(p)
        except Exception:
            continue
        if not log.positions or boat_name(os.path.basename(p)) != TEAM:
            continue
        day = datetime.datetime.fromtimestamp(log.positions[0][0] / 1000,
                                              datetime.timezone.utc).strftime('%Y-%m-%d')
        if day in RACE_GUN:
            logs[day] = log
    seen = {}
    for day, log in logs.items():
        for s, e in rml.race_windows(log):
            rn = race_of(day, s)
            if rn and rn not in seen:
                seen[rn] = (log, s, e)
    check('a log window for every race', sorted(seen) == races, str(sorted(seen)))
    for rn, (log, s, e) in sorted(seen.items()):
        a = sl.start_analysis(log, s)
        row = next(x for x in D['start']['races'][rn] if x['boat'] == TEAM)
        check(f'r{rn} distance to line from the log', close(row['dist_m'], a['distance_to_line_m'], 0.05),
              f"{row['dist_m']} vs {a['distance_to_line_m']}")
        check(f'r{rn} speed at gun from the log', close(row['sog'], a['sog_at_gun_kn'], 0.05))
        legs_min = sum(l['min'] for l in R[rn][TEAM])
        window_min = (e - s) / 60000
        check(f'r{rn} legs fit inside the race window', legs_min <= window_min + 1,
              f'{legs_min:.1f} min of legs in a {window_min:.1f} min window')

    # ---- 6. internal coherence ------------------------------------------------
    for rn in races:
        for l in R[rn][TEAM]:
            check(f'r{rn} leg {l["n"]} carries both averages',
                  l.get('svmg') is not None and l.get('keep') is not None)
            check(f'r{rn} leg {l["n"]} cost is in metres',
                  'loss_m' in l and 'tloss' not in l)
            if l['kind'] == 'beat' and l['twa'] > 55:
                bad.append(f'r{rn} leg {l["n"]}: beat TWA {l["twa"]} is not a beat')
            if l['kind'] == 'run' and l['twa'] < 110:
                bad.append(f'r{rn} leg {l["n"]}: run TWA {l["twa"]} is not a run')

    # ---- 7. the built page says the same thing --------------------------------
    html = open(os.path.join(ROOT, 'race-analysis.html'), encoding='utf-8').read()
    i = html.index('const D = {')
    P = json.loads(html[i + 10:html.index('\n', html.index(';\n', i))].rstrip().rstrip(';'))
    check('page position matches payload', P['official']['team']['pos'] == t['pos'])
    check('page points match payload', close(P['official']['team']['pts'], t['pts'], 0.01))
    check('page gain matches payload', P['official']['team']['gain'] == t['gain_total'])
    check('page has every race', sorted(P['legs']['races']) == races)
    check('page leg data matches payload',
          P['legs']['races'] == R, 'legs block is carried through unchanged')

    print(f'{len(ok)} checks passed')
    for w in warn:
        print('  note   ', w)
    for b in bad:
        print('  FAILED ', b)
    if bad:
        sys.exit(1)


if __name__ == '__main__':
    main()
