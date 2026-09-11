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
PAYLOAD = os.path.join(ROOT, 'site/payload.json')


def rank(rows, key, value):
    vals = sorted((r[key] for r in rows if r[key] is not None), reverse=True)
    return vals.index(value) + 1, len(vals)


def main():
    P = json.load(open(SRC))
    D = json.load(open(PAYLOAD))
    rows = P['fleet_rows']
    g = next(r for r in rows if r['boat'].startswith('GARM'))

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
        'by_race': P['team_by_race'],
        'team': {'gain': g['gain'], 'up': g['up'], 'dn': g['dn']},
        'ranks': {'gain': rank(rows, 'gain', g['gain']),
                  'up': rank(rows, 'up', g['up']),
                  'dn': rank(rows, 'dn', g['dn']),
                  'gain_top20': rank(top20, 'gain', g['gain'])},
        'best_up': max((r for r in rows if r['up'] is not None), key=lambda r: r['up']),
        'top': [{'pos': r['pos'], 'boat': r['boat'].rsplit(' ', 2)[0].title(),
                 'gain': r['gain'], 'up': r['up'], 'dn': r['dn']} for r in top20[:5]],
    }
    json.dump(D, open(PAYLOAD, 'w'), ensure_ascii=False)
    r = D['progress']['ranks']
    print(f"gains over {P['races_covered']} races: total {g['gain']:+d} (rank {r['gain'][0]}/{r['gain'][1]}, "
          f"{r['gain_top20'][0]}/{r['gain_top20'][1]} among the top 20), "
          f"upwind {g['up']:+d} (rank {r['up'][0]}/{r['up'][1]}), "
          f"downwind {g['dn']:+d} (rank {r['dn'][0]}/{r['dn'][1]})")


if __name__ == '__main__':
    main()
