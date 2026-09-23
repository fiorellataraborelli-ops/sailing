#!/usr/bin/env python3
"""Garm's position at each mark, derived from the fleet's logs -> data/event/progress_derived.json.

The event's race-progress report gives position at the first windward mark and the
places won after it, for the whole hundred-boat fleet. It stopped at race 8. Races 9
and 10 were sailed, scored, and logged by fifteen and fourteen boats, and the model
carried nothing for them: the first-mark section simply ended on Friday while every
other part of the page ran to Saturday.

The logs can answer the same question. We know, for each logged boat, when it rounded
each mark, and we know where it actually finished in the hundred-boat fleet. So rank
the logged boats by time at a mark, then read the fleet position off the finishing
positions those same boats went on to take: the boat lying k-th of n at the mark is
estimated to lie where the k-th best of that sample finished. It assumes the sample is
spread through the fleet in much the same way at the mark as at the finish, which is
the sort of assumption that has to be checked rather than asserted -- so it is.

CHECKED, every run, two ways:

  * against the event's own published first-mark positions, on the five races where
    both exist and enough boats logged. Mean error must stay at or under MAX_MEAN_ERR
    places or this exits non-zero. It currently runs at 3.4, and the shape of that
    matters more than the mean: races 5, 7 and 8 are within one place, while the two
    Tuesday races come out 7-8 places optimistic. Four estimator variants were tried
    (order statistic vs quantile, sailed-only vs all-logged at the mark) and all four
    land on the same numbers, so it is structural, not a formula to tune. Saturday's
    two races have Thursday-and-Friday-shaped samples -- the boats still logging -- so
    the one-place figure is the relevant one for them, and the page says so.
  * against the results themselves: ranking the logged boats by elapsed time has to
    reproduce their actual finishing order. Kendall tau must clear MIN_TAU on every
    race used. It currently runs +1.00 on races 5 and 9, +0.97 to +0.99 elsewhere.

A race with fewer than MIN_BOATS logged is not derived at all. Races 3 and 4 have four
logs between them, which is a sample that can say almost nothing about a hundred boats.
"""
import sys, os, glob, json, math, datetime, itertools, unicodedata as ud, statistics as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.sailing_agents.vkx_parser import parse_file
from src.sailing_agents import race_multi_leg as rml
from tools.build_legs import (name, SRC, RACE_GUN, race_of, WIND,
                              finish_by_line, finish_ts)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'data/event/progress_derived.json')
RESULTS = os.path.join(ROOT, 'data/event/results.json')
PUBLISHED = os.path.join(ROOT, 'data/event/progress.json')

TEAM = 'Team Sweden'
MIN_BOATS = 10          # logged boats matched to the scoreboard before a race is used
MAX_MEAN_ERR = 4.0      # places, against the published first-mark positions (see above)
MIN_TAU = 0.90          # elapsed order vs actual finishing order

fold = lambda s: ud.normalize('NFKD', s).encode('ascii', 'ignore').decode().lower().strip()
# telemetry name -> scoreboard name, where the two genuinely differ
ALIAS = {'team sweden': 'garm', 'ba ba': 'baba', 'midlifecrisis': 'midlife crisis',
         'ro': 'relative obscurity', 'diva-neu': 'diva', 'gtg new': 'good to go'}


def scoreboard():
    """{race -> {folded boat name -> finishing position}}, sailed finishes only.

    A coded score is not a position anyone crossed the line in. A DSQ and a DNC are
    both scored 101 here, an RDG is an average — none of them say where the boat was
    on the water, so all of them would corrupt a mapping built on "the k-th boat at
    this mark finished where the k-th boat of the sample finished". Race 2 carries
    three DSQ, three DNF, two DNS and two RDG, and leaving them in dropped its
    elapsed-vs-finish agreement to +0.88 and put it below the gate.
    """
    out = {}
    for r in json.load(open(RESULTS))['rows']:
        for i, (sc, code) in enumerate(zip(r['races'], r['codes']), 1):
            if code or sc is None:
                continue
            out.setdefault(str(i), {})[fold(r['boat'])] = sc
    return out


def finished(table, rn, boat):
    """Where this boat finished that race, or None if the name does not match."""
    f = ALIAS.get(fold(boat), fold(boat))
    T = table.get(rn, {})
    if f in T:
        return T[f]
    for k, v in T.items():
        if k.startswith(f) or f.startswith(k) or f in k or k in f:
            return v
    return None


def mark_times():
    """{race -> {boat -> [minutes from the gun to each of the four mark roundings]}}."""
    out = {}
    for p in sorted(glob.glob(SRC + '/*')):
        if not os.path.isfile(p):
            continue
        try:
            log = parse_file(p)
        except Exception:
            continue
        if not log.positions:
            continue
        day = datetime.datetime.fromtimestamp(
            log.positions[0][0] / 1000, datetime.timezone.utc).strftime('%Y-%m-%d')
        if day not in RACE_GUN:
            continue
        b, done = name(os.path.basename(p)), set()
        for s, e in rml.race_windows(log):
            rn = race_of(day, s)
            if rn is None or rn in done:
                continue
            done.add(rn)
            try:
                race = rml.segment_race(log, s, e, int(rn), wind_deg=WIND[rn][0])
            except Exception:
                continue
            if len(race.legs) < 4:
                continue
            tr = [q for q in log.positions if s <= q[0] <= e]
            ts = []
            for i, l in enumerate(race.legs[:4]):
                end = l.end_ts_ms
                if i == 3 and l.kind == 'run':
                    seg = [q for q in tr if l.start_ts_ms <= q[0] <= end]
                    ft = finish_by_line(log, s, seg) or finish_ts(seg)
                    if ft and end - ft > 45_000:
                        end = ft
                ts.append((end - s) / 60000.0)
            out.setdefault(rn, {})[b] = ts
    return out


def tau(order):
    """Kendall tau between the given order and its own finishing positions."""
    pairs = list(itertools.combinations(order, 2))
    if not pairs:
        return 1.0
    conc = sum(1 for a, b in pairs if a < b)
    disc = sum(1 for a, b in pairs if a > b)
    return (conc - disc) / (conc + disc) if conc + disc else 1.0


def main():
    table, marks = scoreboard(), mark_times()
    pub = {r['race']: r for r in json.load(open(PUBLISHED))['team_by_race']}

    rows, errs, taus, skipped = [], [], [], []
    for rn in sorted(marks, key=int):
        d = {b: t for b, t in marks[rn].items() if finished(table, rn, b) is not None}
        if TEAM not in d or len(d) < MIN_BOATS:
            skipped.append((rn, len(d)))
            continue

        by_elapsed = sorted(d, key=lambda b: d[b][3])      # time to the finish
        t = tau([finished(table, rn, b) for b in by_elapsed])
        taus.append((rn, t))
        if t < MIN_TAU:
            skipped.append((rn, f'tau {t:+.2f}'))
            continue

        # fleet positions the sample went on to take, in order
        fins = sorted(finished(table, rn, b) for b in d)
        at = []
        for i in range(4):
            order = sorted(d, key=lambda b: d[b][i])
            at.append(int(fins[order.index(TEAM)]))
        real = int(finished(table, rn, TEAM))
        p = pub.get(int(rn), {}).get('w1')
        if p is not None:
            errs.append(abs(at[0] - p))
        rows.append({'race': int(rn), 'boats': len(d), 'result': real,
                     'w1': at[0], 'leeward': at[1], 'w2': at[2],
                     'gain': at[0] - real,
                     # a run, then a beat, then the run to the finish
                     'dn': (at[0] - at[1]) + (at[2] - real), 'up': at[1] - at[2],
                     'published_w1': p,
                     'err': None if p is None else at[0] - p,
                     'source': 'derived'})

    if errs and st.mean(errs) > MAX_MEAN_ERR:
        raise SystemExit(f'derivation refused: mean error {st.mean(errs):.1f} places '
                         f'against the published first-mark positions, over {len(errs)} '
                         f'races — limit is {MAX_MEAN_ERR}')

    out = {
        'source': 'derived from the fleet\'s own logs, validated against the event report',
        'note': ('Position at each mark, estimated by ranking the logged boats at that '
                 'mark and reading the fleet position off where those same boats '
                 'finished. Only races with at least '
                 f'{MIN_BOATS} logged boats matched to the scoreboard.'),
        'method_error_places': round(st.mean(errs), 1) if errs else None,
        'method_checked_on': len(errs),
        'method_error_by_race': {r['race']: r['err'] for r in rows if r['err'] is not None},
        'tau_by_race': {int(rn): round(t, 2) for rn, t in taus},
        'min_boats': MIN_BOATS,
        'by_race': rows,
    }
    json.dump(out, open(OUT, 'w'), ensure_ascii=False, indent=1)

    print(f'derived first-mark positions for races {[r["race"] for r in rows]}')
    for r in rows:
        p = '' if r['published_w1'] is None else f"   published {r['published_w1']}"
        print(f"  race {r['race']:>2}: {r['boats']:>2} boats, mark 1 ~{r['w1']:>3}"
              f" -> finished {r['result']:>3}, {r['gain']:+3d} places{p}")
    print(f'  checked against {len(errs)} published values: mean error '
          f'{st.mean(errs):.1f} places, worst {max(errs)}')
    print(f'  elapsed-vs-finish tau: ' +
          ', '.join(f'r{rn} {t:+.2f}' for rn, t in taus))
    if skipped:
        print(f'  not derived: ' + ', '.join(f'r{rn} ({why})' for rn, why in skipped))


if __name__ == '__main__':
    main()
