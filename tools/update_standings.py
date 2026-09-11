#!/usr/bin/env python3
"""data/event/results.json -> payload['official'].

Six races are now scored and a discard is being applied, which changes what the
page is allowed to say. Through four races every boat's points equalled the sum of
its finishes, so the page called them total points and said so; from five races on,
net and total differ and both belong on the page — a boat whose discard is a DNC
is in a different position from one throwing out a bad race.

The gain figures (places won after the first windward mark) come from the event's
mark-progress tables, which only cover races 1-4, so they are carried forward
unchanged and labelled with the races they cover rather than being silently
restated as if they covered six.
"""
import json, os, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(ROOT, 'data/event/results.json')
# Where the team stood at each race count. "Moved up 14 places" has to be measured
# against the standing after five races, not against whatever the payload happens to
# hold — deriving it from the payload meant a second run with no new race compared
# the position against itself and quietly reported no movement at all.
HISTORY = os.path.join(ROOT, 'data/event/standing_history.json')
PAYLOAD = os.path.join(ROOT, 'site/payload.json')
TEAM = 'GARM'
DISPLAY = {'OCEANPACT - VIKING': 'Oceanpact - Viking', 'EMPEIRIA': 'Empeiria',
           'MARNATURA': 'Marnatura', 'MIDLIFE CRISIS': 'MidlifeCrisis',
           'GOOD TO GO': 'Good to Go', 'ARETê': 'Areté', 'GARM': 'Garm'}
nice = lambda b: DISPLAY.get(b, b.title())


def fmt(r):
    """Race scores with the discard bracketed and any scoring code kept."""
    return [(f'{c} ' if c else '') + f'{p:g}' + ('*' if i + 1 == r['discard'] else '')
            for i, (p, c) in enumerate(zip(r['races'], r['codes']))]


def main():
    R = json.load(open(RESULTS))
    D = json.load(open(PAYLOAD))
    rows = R['rows']
    team = next(r for r in rows if r['boat'].upper() == TEAM)
    o = D['official']
    hist = json.load(open(HISTORY)) if os.path.exists(HISTORY) else {}
    hist.setdefault(str(o['races_scored']), o['team']['pos'])      # before this update
    hist[str(R['races_scored'])] = team['pos']
    earlier = [int(k) for k in hist if int(k) < R['races_scored']]
    prev_races = max(earlier) if earlier else R['races_scored']
    prev_pos = hist[str(prev_races)]

    o['races_scored'] = R['races_scored']
    o['fleet_scored'] = R['fleet']
    o['discard_applied'] = R['discard_applied']
    o['updated'] = datetime.datetime.now(datetime.timezone.utc).strftime('%d/%m/%Y %H:%M UTC')
    o['source'] = ('cncascais.com scored results (fetched, not transcribed) + ib-sailing '
                   'mark-progress standings for races 1-4')
    o['top'] = [{'pos': r['pos'], 'sail': r['sail'], 'boat': nice(r['boat']),
                 'pts': r['net'], 'total': r['total'], 'r': r['races'],
                 'codes': r['codes'], 'discard': r['discard'], 'scores': fmt(r)}
                for r in rows[:5]]
    o['team'] = {**o['team'], 'pos': team['pos'], 'sail': team['sail'], 'boat': 'Garm',
                 'pts': team['net'], 'total': team['total'], 'r': team['races'],
                 'codes': team['codes'], 'discard': team['discard'], 'scores': fmt(team),
                 'best': min(team['races']), 'moved': prev_pos - team['pos']}
    for i, p in enumerate(team['races'], 1):          # r1..r6, kept for older renderers
        o['team']['r%d' % i] = p
    o['gain_races'] = 4
    o['gain_def'] = ('Places won between the first windward mark and the finish — the '
                     'estimated Windward 1 position minus the official finish, summed over '
                     'races 1-4. The event has not published mark progress for races 5-6.')
    o['race4_note'] = (
        f"Six races scored, one discard. Garm is {team['pos']}th on {team['net']:g} net from "
        f"{team['total']:g} total, discarding race {team['discard']} "
        f"({team['races'][team['discard']-1]:g}). Race 5 is a {min(team['races']):g}"
        f"{'nd' if min(team['races']) == 2 else 'th'} — the best of the regatta — and the team "
        f"has moved from {prev_pos}th after {prev_races} races to {team['pos']}th after "
        f"{R['races_scored']}.")
    json.dump(hist, open(HISTORY, 'w'), indent=1, sort_keys=True)
    json.dump(D, open(PAYLOAD, 'w'), ensure_ascii=False)
    print(f"Garm {prev_pos}th after {prev_races} -> {team['pos']}th of {R['fleet']}, "
          f"net {team['net']:g} / total {team['total']:g}, scores {' '.join(fmt(team))}")
    print('top 5:', ', '.join(f"{r['pos']} {nice(r['boat'])} {r['net']:g}" for r in rows[:5]))


if __name__ == '__main__':
    main()
