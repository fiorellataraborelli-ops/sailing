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
    # gain_races and gain_def belong to update_progress, which knows how many races
    # the progress report actually covers. Setting them here overwrote that with 4.
    # Every figure in this sentence is read from the result, never typed: the count
    # of races, the discard, which race was the best and what it scored. The first
    # words used to be the literal "Six races scored", and stayed that way through
    # ten. A sentence that is nearly all right is the one nobody re-reads.
    ordn = lambda n: f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"
    words = {6: 'Six', 7: 'Seven', 8: 'Eight', 9: 'Nine', 10: 'Ten', 11: 'Eleven', 12: 'Twelve'}
    n_scored = R['races_scored']
    best = min(team['races'])
    best_race = team['races'].index(best) + 1
    o['race4_note'] = (
        f"{words.get(n_scored, n_scored)} races scored"
        + (", one discard" if R.get('discard_applied') else ", no discard yet")
        + f". Garm is {ordn(team['pos'])} on {team['net']:g} net from {team['total']:g} total"
        + (f", discarding race {team['discard']} ({team['races'][team['discard']-1]:g})"
           if team.get('discard') else '')
        + f". Race {best_race} is a {ordn(int(best))} — the best of the regatta — and the team "
        f"has moved from {ordn(prev_pos)} after {prev_races} races to {ordn(team['pos'])} after "
        f"{n_scored}.")
    # the whole arc of the regatta, for the page to draw: standing after each scoring
    # cut, oldest first — 29th after four races, 9th after ten
    o['history'] = {str(k): v for k, v in sorted(((int(k), v) for k, v in hist.items()))}
    json.dump(hist, open(HISTORY, 'w'), indent=1, sort_keys=True)
    json.dump(D, open(PAYLOAD, 'w'), ensure_ascii=False)
    print(f"Garm {prev_pos}th after {prev_races} -> {team['pos']}th of {R['fleet']}, "
          f"net {team['net']:g} / total {team['total']:g}, scores {' '.join(fmt(team))}")
    print('top 5:', ', '.join(f"{r['pos']} {nice(r['boat'])} {r['net']:g}" for r in rows[:5]))


if __name__ == '__main__':
    main()
