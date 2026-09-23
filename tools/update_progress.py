#!/usr/bin/env python3
"""data/event/progress.json -> payload['official'] gains and payload['progress'].

Places won between the first windward mark and the finish used to come from the
per-race reports, which cover races 1-4 and are now behind a password. The event's
race-progress report is public, covers all six, and gives the same measure for the
whole 100-boat fleet — which turns a bare number into a ranked one.
"""
import json, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'data/event/progress.json')
DERIVED = os.path.join(ROOT, 'data/event/progress_derived.json')   # tools/derive_progress.py
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
        if p and p.get('w1') is not None:
            rows.append({**p, 'source': 'event report'})
        elif d:
            rows.append({'race': rn, 'result': d['result'], 'w1': d['w1'], 'gain': d['gain'],
                         'up': d['up'], 'dn': d['dn'], 'legs': f"logs, {d['boats']} boats",
                         'source': 'derived', 'boats': d['boats']})
        else:
            rows.append({**(p or {'race': rn}), 'w1': None, 'gain': None,
                         'source': 'none', 'why': 'too few boats logged to estimate'})
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
    D['official']['gain_races'] = P['races_covered']
    D['official']['gain_def'] = (
        'Places won between the first windward mark and the finish, summed over all '
        f"{P['races_covered']} races — the event's own race-progress report, which covers "
        f"the full {P['fleet']}-boat fleet.")

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
        'w1': ({'avg': g['w1'],
                'rank': rank(rows, 'w1', g['w1'], False)[0],
                'n': rank(rows, 'w1', g['w1'], False)[1]} if g.get('w1') else None),
        'ranks': {'gain': rank(rows, 'gain', g['gain']),
                  'up': rank(rows, 'up', g['up']),
                  'dn': rank(rows, 'dn', g['dn']),
                  'gain_top20': rank(top20, 'gain', g['gain'])},
        'best_up': max((r for r in rows if r['up'] is not None), key=lambda r: r['up']),
        'top': [{'pos': r['pos'], 'boat': r['boat'].rsplit(' ', 2)[0].title(),
                 'gain': r['gain'], 'up': r['up'], 'dn': r['dn']} for r in top20[:5]],
    }
    D['official']['gain_all'] = gain_all
    D['official']['gain_all_races'] = len(with_gain)
    json.dump(D, open(PAYLOAD, 'w'), ensure_ascii=False)
    r = D['progress']['ranks']
    print(f"first-mark rows: {len(by_race)} races, "
          f"{sum(1 for x in by_race if x['source']=='event report')} published, "
          f"{len(derived_races)} derived {derived_races}, "
          f"{sum(1 for x in by_race if x['source']=='none')} blank; "
          f"gain over {len(with_gain)} races {gain_all:+d}")
    print(f"gains over {P['races_covered']} races: total {g['gain']:+d} (rank {r['gain'][0]}/{r['gain'][1]}, "
          f"{r['gain_top20'][0]}/{r['gain_top20'][1]} among the top 20), "
          f"upwind {g['up']:+d} (rank {r['up'][0]}/{r['up'][1]}), "
          f"downwind {g['dn']:+d} (rank {r['dn'][0]}/{r['dn'][1]})")


if __name__ == '__main__':
    main()
