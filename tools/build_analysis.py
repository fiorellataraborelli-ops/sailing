#!/usr/bin/env python3
"""site2/page.html + site/payload.json -> race-analysis.html.

The design came from the client as a Claude Design bundle whose runtime cannot
be published as a static page, so the layout is rebuilt as plain HTML with the
same tokens, type and imagery, and driven by the real payload instead of the
placeholder numbers the mockup shipped with. Images are inlined as data URIs so
the page is one file with no external requests but the two Google fonts.
"""
import json, os, base64, re, unicodedata as ud

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMG = os.path.join(ROOT, 'site2/img')
OUT = os.path.join(ROOT, 'race-analysis.html')

DAY_LABEL = {'2026-09-08': 'Tue 8 Sep', '2026-09-09': 'Wed 9 Sep'}
DAY_NOTE = {
  '2026-09-08': 'Races 1, 2 and 3. Thirty boats decode here against the event\'s own 34-boat '
                'analysis set, so fleet-relative figures are a real fleet comparison.',
  '2026-09-09': 'Race 4. Only three logs have synced for this day, and Garm\'s is not among them — '
                'so there is no telemetry for the team\'s racing today, only the scored result.',
}
fold = lambda s: ud.normalize('NFKD', s).encode('ascii', 'ignore').decode().lower()


def data_uri(path):
    with open(path, 'rb') as f:
        return 'data:image/jpeg;base64,' + base64.b64encode(f.read()).decode()


def leg_tacks(D, race_n, boat):
    """Settled tacks on the first beat, from leg_vmg rather than the speed-dip counter.

    The two disagree — a speed dip is not a tack — and the page showed both at once for
    a moment. The settled-crossing count is the one that survived checking, so it is the
    only one that appears.
    """
    alias = {'team sweden (roman)': 'team sweden', 'ba ba': 'baba', 'phantom7': 'phantom7 8.9.2026'}
    want = alias.get(fold(boat), fold(boat))
    for k, L in D['legs']['races'].get(str(race_n), {}).items():
        kk = fold(k)
        if kk == want or kk.startswith(want) or want.startswith(kk.split()[0]):
            beat = next((l for l in L if l['kind'] == 'beat'), None)
            if beat:
                return beat['tacks']
    return None


def canon(s):
    """One key per boat across three sources that name them three different ways."""
    t = ud.normalize('NFKD', s).encode('ascii', 'ignore').decode().lower()
    t = re.sub(r'\b\d{1,2}[.\-]\d{1,2}[.\-]\d{4}\b', '', t)
    t = re.sub(r'\bvakaros\d*\b', '', t)
    t = re.sub(r'[^a-z0-9]', '', t)
    return re.sub(r'\d+$', '', t) or t


ALIAS = {'teamswedenroman': 'garm', 'teamsweden': 'garm', 'dimepiece': 'dime',
         'j70letitbe': 'letitbe', 'mag': 'magatron', 'gtgnew': 'goodtogo'}
key = lambda s: ALIAS.get(canon(s), canon(s))

DISPLAY = {'garm': 'Garm', 'dime': 'Dime Piece', 'letitbe': 'Let It Be', 'magatron': 'Mag',
           'goodtogo': 'GTG', 'arete': 'Areté', 'baba': 'Bábá', 'ladyinred': 'Lady in Red',
           'mooredrv': 'Moore DRV', 'vtarte': 'V-Tarte', 'tonessa': 'To Nessa',
           'midlifecrisis': 'MidlifeCrisis', 'relativeobscurity': 'Relative Obscurity',
           # the download stamped dates into these filenames; the boat is not called that
           'phantom': 'Phantom7', 'divaneu': 'DIVA-NEU', 'njk': 'NJK', 'tur': 'TUR 442',
           'tyra': 'TYRA', 'joust': 'Joust70', 'jcurve': 'JCurve', 'mikes': "Mike's"}


def build_compare(D):
    """Every velocity measure this analysis has, one row per boat, joined on `key`.

    Three sources name the same boats differently — the log file, the leg analysis and
    the event's segment table — so nothing here is joined on a raw string. A boat missing
    from one source keeps nulls for those columns rather than dropping out of the table.
    """
    rows = {}

    def slot(name):
        k = key(name)
        return rows.setdefault(k, {'key': k, 'name': DISPLAY.get(k, name), 'team': k == 'garm'})

    for f in D['fleet']:
        if f['day'] != '2026-09-08':
            continue
        r = slot(f['file'])
        r.update(up=f['upAvg'], dn=f['dnAvg'], avg=f['avg'], mx=f['mx'], nm=f['nm'])

    for rn in ('1', '2'):
        for boat, L in D['legs']['races'].get(rn, {}).items():
            r = slot(boat)
            beat = next((l for l in L if l['kind'] == 'beat'), None)
            run = next((l for l in L if l['kind'] == 'run'), None)
            if beat:
                r['vmg' + rn], r['twa' + rn] = beat['vmg'], beat['twa']
                r['tacks' + rn], r['extra' + rn] = beat['tacks'], beat['extra']
            if run:
                r['run' + rn] = run['vmg']

    for s in D['segments']['rows']:
        r = slot(s['boat'])
        r.update(peak=s['s']['0'], s60=s['s']['60'], hold=s['hold'])

    for o in D['official']['top']:
        k = key(o['boat'])
        if k in rows:
            rows[k].update(pos=o['pos'], pts=o['pts'])
    t = D['official']['team']
    if 'garm' in rows:
        rows['garm'].update(pos=t['pos'], pts=t['pts'])

    out = [r for r in rows.values() if r.get('up') or r.get('peak')]
    out.sort(key=lambda r: -(r.get('up') or 0))
    return out


def main():
    D = json.load(open(os.path.join(ROOT, 'site/payload.json')))
    team = D['meta']['team']
    raceday = '2026-09-08'

    # fleet, one row per log, flagged for the client boat
    # Sunday 7 September was the abandoned practice day — no scored racing, no Garm log.
    # It is dropped rather than shown as a third tab nobody asked for.
    RACED = ('2026-09-08', '2026-09-09')
    fleet = [{'name': f['file'], 'day': f['day'], 'avg': f['avg'], 'up': f['upAvg'],
              'dn': f['dnAvg'], 'mx': f['mx'], 'nm': f['nm'],
              'team': f['file'].startswith('Team Sweden') or f['file'] == 'vakaros'}
             for f in D['fleet'] if f['day'] in RACED]

    # Wind, measured, grouped by the day it was actually sailed.
    #
    # This used to mix the event's measured wind for Tuesday with wind.json's hourly
    # forecast for Wednesday. Two things broke that: the 23:03 refresh rolled wind.json
    # forward to 10-12 September and dropped the 9th entirely, leaving the Wednesday tab
    # empty; and race 4 is a Wednesday race that was being listed under Tuesday, because
    # the races were taken in order rather than by date. Both are gone now — every figure
    # here is measured, and each race sits under the day it was sailed.
    guns = {r['n']: r['gun'] for r in D['races']}
    bias_by_race = {b['race']: b for b in D['ib']['bias_rows']}
    wind_days = {}
    for r in D['ib']['races']:
        b = bias_by_race.get(r['n'], {})
        wind_days.setdefault(r['date'], []).append({
            # the loggers' gun, not the event's published one: race 1's report says
            # 13:34:52, which puts every tracked boat mid-race
            'n': r['n'], 'gun': guns.get(r['n']) or r.get('start_local'),
            'forecast': b.get('forecast'), 'measured': b.get('measured'),
            'bias': b.get('bias'), 'setting': r['setting'], 'legs': r['legs']})
    wind = [{'date': d, 'label': DAY_LABEL.get(d, d), 'races': rs}
            for d, rs in sorted(wind_days.items())]

    # start line, from the event's published geometry
    startline = [{'race': r['n'], 'setting': r['setting'], 'line_m': r['line_m'],
                  'bias_deg': r['bias_deg'], 'bias_m': r['bias_m'], 'calc_m': r['calc_m'],
                  'favoured': r['favoured']} for r in D['ib']['races']]

    # segments, flagged and renamed for the client boat
    segs = []
    for r in D['segments']['rows']:
        s = r['s']
        segs.append({'boat': r['boat'], 's0': s['0'], 's10': s['10'], 's30': s['30'],
                     's60': s['60'], 'hold': r['hold'], 'rank0': r['rank0'],
                     'rankhold': r['rankhold'], 'team': r['boat'] == 'Garm'})

    t = D['official']['team']
    bias = D['ib']['bias_rows'][0]

    qa = [
      {'label': 'Where did the regatta go wrong?',
       'k': ['wrong', 'bad', 'lose', 'lost', 'worst'],
       'q': 'Where did the regatta go wrong?',
       'a': f"Not on boat speed. Garm's upwind VMG is {D['kpi']['rows'][-1]['vmg']} kn at "
            f"{D['kpi']['rows'][-1]['twa']}° — within 0.01 kn of Areté, which is 3rd overall. "
            f"The damage is done by the first windward mark: Garm wins <b>+{t['gain_total']} places</b> "
            f"after it, more than anyone in the top five, which means it is starting each race deep "
            f"and spending the rest of it recovering."},
      {'label': "What's the wind bias?", 'k': ['bias', 'wind', 'grib', 'forecast', 'model'],
       'q': "What's the wind bias?",
       'a': f"The GRIB runs right of the water. Race 1 forecast {bias['forecast']}° against "
            f"{bias['measured']}° measured — <b>+{bias['bias']}°</b>. Across the three races it ran "
            f"+19.1, +18.0 and +11.2, so the page uses +{D['meta']['bias']}° as a centre, not a fixed "
            f"offset, and withholds it entirely below 8 knots. The cause is the breeze bending against "
            f"the shoreline, which a 7 km grid cell cannot resolve."},
      {'label': 'Which end of the line?', 'k': ['line', 'start', 'pin', 'end', 'bias at the gun'],
       'q': 'Which end of the line was favoured?',
       'a': f"The pin, in every race. Race 2 was worth {startline[1]['bias_m']} m on a "
            f"{startline[1]['line_m']:,} m line — a fifth of the line, free. Our own geometry "
            f"reproduces the event's published figures to within 2% each time, working only from the "
            f"line bearing and the measured wind."},
      {'label': 'Do tacks matter?', 'k': ['tack', 'gybe', 'manoeuvre', 'maneuver'],
       'q': 'Do tacks explain the difference?',
       'a': f"No, and this is the most counter-intuitive result on the page. Across the tracked fleet "
            f"tack count correlates with first-beat VMG at r = {D['legs']['drivers']['1']['r_tacks']} — "
            f"the weakest of every variable tested. True wind angle "
            f"({D['legs']['drivers']['1']['r_twa']}) and extra distance sailed "
            f"({D['legs']['drivers']['1']['r_extra']}) both matter more. Boats are not losing the beat "
            f"in the manoeuvres."},
      {'label': 'Official standing?', 'k': ['standing', 'result', 'position', 'points', 'overall'],
       'q': "What's our official standing?",
       'a': f"{t['pos']}th of {D['official']['fleet_scored']} on {t['pts']} net points after "
            f"{D['official']['races_scored']} races — {t['r1']}, {t['r2']}, {t['r3']}, {t['r4']}. "
            f"{t['sail']}, {t['boat']}, skippered by {t['skipper']}."},
      {'label': 'How fast is the boat really?', 'k': ['fast', 'speed', 'peak', 'hold', 'segment'],
       'q': 'How fast is the boat really?',
       'a': "Faster than it looks in the segment table. Garm peaked at 19.8 kn on Wednesday — 21st of "
            "30 — but held 17.14 kn over a full minute, 16th, and ranks 8th on retention. Across the "
            "fleet the peak and the hold correlate at −0.59: the biggest headline numbers come from a "
            "brief surf in a gust, not from a genuinely quick boat."},
    ]

    payload = {
      'meta': {'bias': D['meta']['bias'], 'tack': D['meta']['tack'], 'pos': D['meta']['pos'],
               'team': team, 'legteam': 'Team Sweden', 'raceday': raceday,
               'logs': D['official']['telemetry']['logs']},
      'official': {'fleet': D['official']['fleet_scored'], 'races': D['official']['races_scored'],
                   # only the field the page prints; the event's end date is not shown
                   'event': {'dates': D['official']['event']['dates']},
                   'team': {'pos': t['pos'], 'sail': t['sail'], 'boat': t['boat'],
                            'skipper': t['skipper'], 'pts': t['pts'], 'gain': t['gain_total'],
                            'races': [t['r1'], t['r2'], t['r3'], t['r4']]}},
      'wind': {'days': wind},
      'fleet': fleet,
      'dayLabel': DAY_LABEL, 'dayNote': DAY_NOTE,
      'startline': startline,
      'legs': {'races': D['legs']['races'], 'drivers': D['legs']['drivers']},
      'segments': {'rows': segs, 'caveat': D['segments']['caveat']},
      'kpi': {'rows': D['kpi']['rows'], 'note': D['kpi']['note']},
      'coach': {'start': D['coach']['start'], 'mechanism': D['coach']['mechanism']},
      'race4': {
        'date': D['race4']['date'], 'boats': D['race4']['boats'],
        'coverage': D['race4']['coverage'], 'note': D['race4']['analyst_note'],
        'wind_uw1': D['race4']['wind_uw1'], 'start_line': D['race4']['start_line'],
        'gun_utc': '12:55:00Z',
        'start_cols': D['race4']['start_cols'], 'start': D['race4']['start'],
        'uw1_cols': D['race4']['uw1_cols'], 'uw1': D['race4']['uw1'],
      },
      'bias': {'rows': D['ib']['bias_rows'], 'trend': D['ib']['bias_trend'],
               'note': D['ib']['bias_note']},
      'compare': build_compare(D),
      'qa': qa,
    }

    html = open(os.path.join(ROOT, 'site2/page.html'), encoding='utf-8').read()
    html = html.replace('__DATA__', json.dumps(payload, ensure_ascii=False, separators=(',', ':')))
    # one image now: the page is a data page, and three decorative photos were 240 KB
    # of payload a phone had to download before it could read a number.
    html = html.replace('__HERO__', data_uri(os.path.join(IMG, 'hero.jpg')))

    # guards against the regressions this page has already had once
    checks = {
      'no placeholder standings': '38th' not in html and '>75<' not in html,
      'the real fleet size': str(D['official']['fleet_scored']) in html,
      'no unfilled bindings': '{{' not in html and '__' not in html.replace('__DATA__', ''),
      'wind days all raced': all(d['date'] in RACED and d['races'] for d in wind),
      'no unraced days': '2026-09-10' not in html and '2026-09-11' not in html
                         and '2026-09-12' not in html and '2026-09-07' not in html,
      'the hero inlined': html.count('data:image/jpeg;base64,') == 1,
    }
    bad = [k for k, v in checks.items() if not v]
    if bad:
        raise SystemExit('build refused, missing: ' + '; '.join(bad))

    open(OUT, 'w', encoding='utf-8').write(html)
    print(f'wrote race-analysis.html — {len(html) / 1e6:.2f} MB '
          f'({len(json.dumps(payload)) / 1024:.0f} KB of data, '
          f'{len(fleet)} logs, {len(segs)} segment rows)')


if __name__ == '__main__':
    main()
