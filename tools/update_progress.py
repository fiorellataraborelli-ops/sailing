#!/usr/bin/env python3
"""data/event/progress.json -> payload['official'] gains and payload['progress'].

Places won between the first windward mark and the finish used to come from the
per-race reports, which cover races 1-4 and are now behind a password. The event's
race-progress report is public, covers all six, and gives the same measure for the
whole 100-boat fleet — which turns a bare number into a ranked one.
"""
import json, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'data/event/mark_progress.json')      # the event's ten-race report
DERIVED = os.path.join(ROOT, 'data/event/progress_derived.json')   # tools/derive_progress.py, cross-check only
PAYLOAD = os.path.join(ROOT, 'site/payload.json')


def merged_by_race(published, derived, scored):
    """One row per scored race, from the best source there is for it.

    The event's report stops at race 8 and left race 6 without a first-mark position.
    The logs cover every race with enough boats, so: the published row where it has a
    first-mark position, the derived row where it does not, and an honest blank where
    neither can say (races 3 and 4: four logs). Every row names its source, and the
    page draws the derived ones differently -- a figure estimated from a sample of
    the fleet must not sit in the same type as one the event measured on every boat.
    """
    pub = {r['race']: r for r in published}
    der = {r['race']: r for r in (derived or {}).get('by_race', [])}
    rows = []
    for rn in range(1, scored + 1):
        p, d = pub.get(rn), der.get(rn)
        if p:
            row = {**p, 'source': 'event report'}
            if p.get('w1') is None:
                row['why'] = 'the event could not resolve the first mark for this race'
            # the logs' own estimate rides alongside as a cross-check, never as the figure
            if d:
                row['derived_w1'] = d['w1']
            rows.append(row)
        elif d:
            rows.append({'race': rn, 'result': d['result'], 'w1': d['w1'], 'gain': d['gain'],
                         'up': d['up'], 'dn': d['dn'], 'legs': f"logs, {d['boats']} boats",
                         'source': 'derived', 'boats': d['boats']})
        else:
            rows.append({'race': rn, 'w1': None, 'gain': None,
                         'source': 'none', 'why': 'no report and too few boats logged to estimate'})
    return rows


def rank(rows, key, value, high_is_good=True):
    """Competition rank: boats on the same figure share a place."""
    vals = [r[key] for r in rows if r.get(key) is not None]
    better = sum(1 for v in vals if (v > value if high_is_good else v < value))
    return better + 1, len(vals)


def main():
    P = json.load(open(SRC))
    D = json.load(open(PAYLOAD))
    DV = json.load(open(DERIVED)) if os.path.exists(DERIVED) else None
    rows = P['fleet_rows']
    g = next(r for r in rows if r['boat'].startswith('GARM'))
    T = P['team']
    scored = D['official']['races_scored']
    by_race = merged_by_race(P['team_by_race'], DV, scored)
    derived_races = [r['race'] for r in by_race if r['source'] == 'derived']
    with_gain = [r for r in by_race if r.get('gain') is not None]
    # the published total is fleet-ranked and stays as it is; this one runs to the end
    # of the regatta by adding the derived races, and is never ranked against the fleet
    # because the fleet's own figures stop where the report does
    gain_all = sum(r['gain'] for r in with_gain)

    t = D['official']['team']
    t.update(gain_total=g['gain'], gain_up=g['up'], gain_down=g['dn'])
    D['official']['gain_races'] = T['gain_races']          # 9: the event could not measure race 6
    D['official']['gain_missing'] = T['gain_missing']
    D['official']['gain_def'] = (
        'Places won between the first windward mark and the finish, summed over the '
        f"{T['gain_races']} of {P['races_covered']} races the event could measure — its own "
        f"mark-progress report, covering the full {P['fleet']}-boat fleet.")

    top20 = [r for r in rows if r['pos'] <= 20]
    D['progress'] = {
        'source': P['source'], 'note': P['note'],
        'races': P['races_covered'], 'fleet': P['fleet'],
        'by_race': by_race,
        'team': {'gain': g['gain'], 'up': g['up'], 'dn': g['dn']},
        # the whole regatta, published where the event measured it and derived from the
        # logs where it did not; says which races are which and how good the method is
        'all': {'races': scored, 'covered': [r['race'] for r in with_gain],
                'gain': gain_all,
                'up': sum(r['up'] for r in with_gain if r.get('up') is not None),
                'dn': sum(r['dn'] for r in with_gain if r.get('dn') is not None),
                'derived': derived_races,
                'method_error_places': DV.get('method_error_places') if DV else None,
                'method_checked_on': DV.get('method_checked_on') if DV else None,
                'method_error_by_race': DV.get('method_error_by_race') if DV else None},
        # position at the first windward mark: the sharpest measure of how deep the
        # boat is coming off the line, and lower is better
        'w1': ({'avg': T['w1_avg'], 'rank': T['w1_rank'], 'n': P['fleet'],
                'races': T['w1_races']} if T.get('w1_avg') else None),
        # the event's own ranks where it publishes them. It does not rank Garm on total
        # gain — nine races measured against other boats' ten is not a fair table — so
        # neither do we; the top-20 comparison that used to sit on the card is gone with it
        'ranks': {'gain': None,
                  'up': (T['up_rank'], P['fleet']),
                  'dn': (T['dn_rank'], P['fleet']),
                  'gain_top20': None},
        # the race as it unfolded: Garm's estimated position at each course checkpoint
        # and the whole fleet's, compact enough to animate on a phone. Order per boat is
        # [Windward 1, leeward gate, Windward 2, finish]; null where the event could not
        # resolve that boat at that mark. Sails carry no space so they key cleanly.
        'marks': {
            'checkpoints': ['Windward 1', 'Leeward gate', 'Windward 2', 'Finish'],
            'team': {rn: [m[k]['pos'] for k in ('w1', 'gate', 'w2', 'fin')]
                     for rn, m in P.get('team_marks', {}).items()},
            'team_times': {rn: [m[k]['time'] for k in ('w1', 'gate', 'w2', 'fin')]
                           for rn, m in P.get('team_marks', {}).items()},
            'team_range': {rn: [[m[k]['lo'], m[k]['hi']] if m[k]['lo'] else None
                                for k in ('w1', 'gate', 'w2', 'fin')]
                           for rn, m in P.get('team_marks', {}).items()},
            'fleet': {rn: [[sail] + [next((r['pos'] for r in (F.get(k) or []) if r['sail'] == sail), None)
                                    for k in ('w1', 'gate', 'w2', 'fin')]
                           for sail in sorted({r['sail'] for k in ('w1', 'gate', 'w2', 'fin')
                                               for r in (F.get(k) or []) if r['sail']})]
                      for rn, F in P.get('fleet_marks', {}).items()},
            'names': {r['sail']: r['name'] for r in rows},
        },
        'event': {k: T[k] for k in ('gain', 'gain_races', 'gain_missing', 'up', 'up_rank',
                                    'dn', 'dn_rank', 'lap', 'leg_total', 'w1_avg', 'w1_rank',
                                    'w1_races')},
        'best_up': max((r for r in rows if r['up'] is not None), key=lambda r: r['up']),
        'top': [{'pos': r['pos'], 'boat': r['boat'].rsplit(' ', 2)[0].title(),
                 'gain': r['gain'], 'up': r['up'], 'dn': r['dn']} for r in top20[:5]],
    }
    D['official']['gain_all'] = gain_all
    D['official']['gain_all_races'] = len(with_gain)
    json.dump(D, open(PAYLOAD, 'w'), ensure_ascii=False)
    r = D['progress']['ranks']
    print(f"event: gain {T['gain']:+d} over {T['gain_races']} of {P['races_covered']} races (missing {T['gain_missing']}), "
          f"up {T['up']:+d} rank {T['up_rank']}/{P['fleet']}, dn {T['dn']:+d} rank {T['dn_rank']}/{P['fleet']}, "
          f"mean first mark {T['w1_avg']} rank {T['w1_rank']}/{P['fleet']}")
    print(f"first-mark rows: {len(by_race)} races, "
          f"{sum(1 for x in by_race if x['source']=='event report')} published, "
          f"{len(derived_races)} derived {derived_races}, "
          f"{sum(1 for x in by_race if x['source']=='none')} blank; "
          f"gain over {len(with_gain)} races {gain_all:+d}")



if __name__ == '__main__':
    main()
