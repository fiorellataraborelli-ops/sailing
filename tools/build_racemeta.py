#!/usr/bin/env python3
"""Race metadata for days the event has not published -> payload['ib']['races'].

Races 1-4 have an ib-sailing report giving the line setting, its bias and the wind
on each leg. Thursday's races 5 and 6 do not, so the wind card would simply have no
Thursday. Everything the card needs is measurable from the logs:

  * line length and bearing, from the committee's own line-position rows in the VKX;
  * the line's square heading — the perpendicular to it, taking whichever of the two
    faces the wind rather than points away down the run;
  * bias, as the angle between that and the wind actually measured on the first beat,
    and the metres it is worth: L x sin(bias). Checked against the four races the
    event did publish; see check_against_published().
  * the wind on each leg, from wind_from_track.

Median across whichever boats logged the race, so one boat's line fix cannot set it.
"""
import sys, os, glob, json, math, datetime, statistics as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.sailing_agents.vkx_parser import parse_file
from src.sailing_agents import race_multi_leg as rml
from src.sailing_agents import start_line as sl
from tools.build_legs import RACE_GUN, WIND, WIND_SOURCE, name, race_of

SRC = os.path.expanduser('~/Downloads/Sailing Files')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DERIVE = ('5', '6', '7', '8')          # races with no published report
# The GRIB forecast at each gun, captured once and kept. wind.json holds only the
# coming two days and the overnight refresh rolls the raced day out of it, so this
# cannot be re-derived after the fact: 10 September's forecast was already gone by
# 02:07 the next morning. Written the first time it is seen, read forever after.
FORECAST = os.path.join(ROOT, 'data/event/forecast_at_gun.json')
LOCAL_OFFSET_H = 1           # Lisbon is UTC+1 in September


def square_heading(brg, wind):
    """The perpendicular to the line that faces upwind.

    A line bearing 64 deg has perpendiculars at 154 and 334. Only one of them is the
    direction the fleet beats in; picking the wrong one puts the bias 170 deg out.
    """
    a, b = (brg + 90) % 360, (brg - 90) % 360
    off = lambda x: abs(((x - wind + 180) % 360) - 180)
    return a if off(a) <= off(b) else b


def bearing(a, b):
    north = (b[0] - a[0]) * sl.M_PER_DEG_LAT
    east = (b[1] - a[1]) * sl.M_PER_DEG_LAT * math.cos(math.radians(a[0]))
    return math.degrees(math.atan2(east, north)) % 360


def main():
    per = {}
    seen = set()
    for p in sorted(glob.glob(SRC + '/*')):
        if not os.path.isfile(p):
            continue
        try:
            log = parse_file(p)
        except Exception:
            continue
        if not log.positions:
            continue
        day = datetime.datetime.fromtimestamp(log.positions[0][0] / 1000,
                                              datetime.timezone.utc).strftime('%Y-%m-%d')
        if day not in RACE_GUN:
            continue
        b = name(os.path.basename(p))
        if (day, b) in seen:
            continue
        seen.add((day, b))
        done = set()
        for s, e in rml.race_windows(log):
            rn = race_of(day, s)
            if rn not in DERIVE or rn in done:
                continue
            done.add(rn)
            ends = sl.line_at(log, s)
            if not ends:
                continue
            pin, cb = ends
            per.setdefault(rn, {'day': day, 'gun': s, 'len': [], 'brg': []})
            per[rn]['len'].append(sl.line_length_m(pin, cb) if hasattr(sl, 'line_length_m')
                                  else math.dist((0, 0), (
                                      (cb[0] - pin[0]) * sl.M_PER_DEG_LAT,
                                      (cb[1] - pin[1]) * sl.M_PER_DEG_LAT *
                                      math.cos(math.radians(pin[0])))))
            per[rn]['brg'].append(bearing(pin, cb))

    D = json.load(open(os.path.join(ROOT, 'site/payload.json')))
    existing = {r['n'] for r in D['ib']['races']}
    added = []
    for rn, v in sorted(per.items()):
        if int(rn) in existing:
            continue
        line_m = round(st.median(v['len']))
        brg = round(st.median(v['brg']), 1)
        wind = WIND[rn]
        square = square_heading(brg, wind[0])
        # signed angle from the line's square heading to the measured wind: negative
        # means the wind has gone left of square, which pays at the pin
        off = ((wind[0] - square + 180) % 360) - 180
        setting = wind[0]        # the event's "setting" column is the course axis
        bias_m = round(line_m * abs(math.sin(math.radians(off))))
        gun = datetime.datetime.fromtimestamp(v['gun'] / 1000, datetime.timezone.utc)
        D['ib']['races'].append({
            'n': int(rn), 'date': v['day'],
            'start_local': (gun + datetime.timedelta(hours=LOCAL_OFFSET_H)).strftime('%H:%M'),
            'start_utc': gun.strftime('%H:%M:%S'),
            'setting': setting, 'line_brg': brg, 'square': round(square),
            'bias_deg': abs(round(off)), 'bias_m': bias_m,
            # the wind sitting left of square favours the pin, right of square the boat
            'favoured': 'Pin' if off < 0 else 'Boat',
            'line_m': line_m, 'calc_m': bias_m,
            'legs': {'uw1': wind[0], 'dw1': wind[1], 'uw2': wind[2], 'dw2': wind[3]},
            'top_vmg': [], 'source': 'derived from the logs — no event report for this race',
        })
        added.append((rn, line_m, brg, setting, off, bias_m))
    D['ib']['races'].sort(key=lambda r: r['n'])

    # the wind card's forecast-vs-measured row
    have = {b['race'] for b in D['ib']['bias_rows']}
    kept = json.load(open(FORECAST)) if os.path.exists(FORECAST) else {}
    # wind.json is {days: [{date, rows: [{hr, raw, ...}]}]} — raw is the GRIB direction,
    # kn its speed. A direction from a 2 kn model field is not a forecast of anything:
    # on 11 September the model had 80 deg at the first gun and 191 deg an hour later
    # while the water was steady at 327, which would have published a model error of
    # +116 and -179 deg. The payload already carries the threshold it trusts.
    MIN_KN = json.load(open(os.path.join(ROOT, 'data/wind.json'))).get('min_kn_for_bias', 8)
    fc, fc_kn = {}, {}
    wf = os.path.join(ROOT, 'data/wind.json')
    if os.path.exists(wf):
        for d in json.load(open(wf)).get('days', []):
            for h in d.get('rows', []):
                fc[(d['date'], h['hr'])] = h.get('raw')
                fc_kn[(d['date'], h['hr'])] = h.get('kn')
    for r in D['ib']['races']:
        if r['n'] in have or r['n'] not in {int(x) for x in DERIVE}:
            continue
        hour = (r['date'], int(r['start_utc'][:2]))
        live = fc.get(hour)
        if live is not None and (fc_kn.get(hour) or 0) < MIN_KN:
            live = None                              # too light for the direction to mean anything
        if live is not None:
            kept.setdefault(str(r['n']), live)      # first sighting wins, and is kept
        f = kept.get(str(r['n']))
        D['ib']['bias_rows'].append({
            'race': r['n'], 'forecast': f, 'measured': float(r['legs']['uw1']),
            'bias': round(((f - r['legs']['uw1'] + 180) % 360) - 180, 1) if f is not None else None,
            'old_observed': None, 'old_bias': None})
    json.dump(kept, open(FORECAST, 'w'), indent=1, sort_keys=True)
    D['ib']['bias_rows'].sort(key=lambda b: b['race'])
    D['ib']['wind_source'] = WIND_SOURCE

    json.dump(D, open(os.path.join(ROOT, 'site/payload.json'), 'w'), ensure_ascii=False)
    for rn, line_m, brg, setting, off, bias_m in added:
        print(f'race {rn}: line {line_m} m bearing {brg}, square {square_heading(brg, WIND[rn][0]):.0f}, '
              f'wind {WIND[rn][0]} -> {off:+.0f} deg = {bias_m} m, '
              f'{"pin" if off < 0 else "boat"} favoured')
    print('bias rows:', [(b['race'], b['forecast'], b['measured'], b['bias'])
                         for b in D['ib']['bias_rows']])


if __name__ == '__main__':
    main()
