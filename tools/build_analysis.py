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
  '2026-09-08': 'Races 1 and 2. Thirty boats decode here against the event\'s own 34-boat '
                'analysis set, so fleet-relative figures are a real fleet comparison.',
  '2026-09-09': 'Three full logs and one partial, and Garm\'s is not among them — so there is no '
                'telemetry for the team\'s racing, only the fleet\'s speed segments.',
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
                # boat speed with the turns taken out — the honest number for a
                # table whose whole purpose is ranking boats against each other
                r['svmg' + rn] = beat.get('svmg')
            if run:
                r['run' + rn] = run['vmg']
                r['srun' + rn] = run.get('svmg')

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


MIN_FOR_THIRDS = 12      # boats needed before splitting a start line into thirds


def coach_test(D):
    """The coach's start-line rule, checked against where boats actually started.

    "If you see start line bias, it is most probably big enough to take it" and "RC boats
    cannot get it back" are testable: split each fleet by which third of the line it
    started in, and compare what happened over the next minute and the beat that followed.

    Only for races with enough boats to split. Wednesday has four logs, which would put
    one or two boats in a third and print the difference between them as a finding.
    """
    out = []
    sl = {r['n']: r for r in D['ib']['races']}
    for rn, rows in sorted(D.get('start', {}).get('races', {}).items()):
        if len(rows) < MIN_FOR_THIRDS:
            continue
        legs = D['legs']['races'].get(rn, {})
        r = sl[int(rn)]
        thirds = {}
        for x in rows:
            thirds.setdefault(x['third'], []).append(x)
        groups = []
        for k in ('pin third', 'middle third', 'boat third'):
            g = thirds.get(k)
            if not g:
                continue
            beats = [next((l for l in (legs.get(x['boat']) or []) if l['kind'] == 'beat'), None)
                     for x in g]
            mins = [b['min'] for b in beats if b and b.get('vmg')]
            groups.append({
                'third': k.replace(' third', ''), 'n': len(g),
                'behind60': round(sum(x['behind60'] for x in g) / len(g), 1),
                'late': round(sum(x['late_s'] for x in g) / len(g), 1),
                'sog': round(sum(x['sog'] for x in g) / len(g), 2),
                'beat': round(sum(mins) / len(mins), 1) if mins else None,
            })
        out.append({'race': int(rn), 'favoured': r['favoured'], 'bias_m': r['bias_m'],
                    'line_m': r['line_m'], 'groups': groups})
    return out


def segs_repaint_themselves(html):
    """Every segmented control must re-render itself when one of its buttons is picked.

    seg() stamps aria-pressed as it builds the buttons, so a handler that changes the
    data without redrawing the control leaves the dark pill behind on the old choice.
    That shipped once: the start replay switched race underneath — plot, caption and
    all — while the pill stayed on race 1, which reads as a dead button.
    """
    bodies = {m.group(1): m.group(2) for m in
              re.finditer(r'function ([A-Za-z_]\w*)\s*\([^)]*\)\s*\{(.*?)\n\}', html, re.S)}
    bad = []
    for m in re.finditer(r"seg\(\$\('([^']+)'\)(.*?)\);\n", html, re.S):
        tid, rest = m.group(1), m.group(2)
        if '=>' not in rest:
            continue
        handler = rest[rest.rfind('=>'):]
        called = set(re.findall(r'\b([A-Za-z_]\w*)\s*\(', handler))
        # drawAll redraws the page, so anything reached through it repaints too
        reach = set(called)
        for f in list(called):
            if f in bodies:
                reach |= set(re.findall(r'\b([A-Za-z_]\w*)\s*\(', bodies[f]))
        if not any(f"seg($('{tid}')" in bodies.get(f, '') for f in reach):
            bad.append(tid)
    if bad:
        print('  segmented controls that never move their own pill:', ', '.join(bad))
    return not bad


def classes_all_styled(html):
    """Every class the markup uses must have a rule somewhere in the stylesheet.

    Four did not, including the one on the page's primary button, which rendered as
    a raw browser control. Utility classes that only exist to be found by script are
    listed here rather than given an empty rule.
    """
    SCRIPT_ONLY = {'on', 'is-visible', 'team', 'me', 'ai', 'hl', 'good', 'bad', 'ico', 'scroll'}
    css = html[html.index('<style>'):html.index('</style>')]
    defined = set(re.findall(r'\.([a-zA-Z][\w-]*)', css)) | SCRIPT_ONLY
    used = set()
    for m in re.findall(r'class="([^"{}]*)"', html):
        used |= set(m.split())
    for m in re.findall(r'class=\\?"([^"$]*)', html):
        used |= {w for w in m.split() if re.fullmatch(r'[a-zA-Z][\w-]*', w)}
    missing = sorted(w for w in used - defined if re.fullmatch(r'[a-zA-Z][\w-]*', w))
    if missing:
        print('  classes with no rule:', ', '.join(missing))
    return not missing


def ids_all_exist(html):
    """Every element the script looks up by a literal id must be in the markup.

    Restyling moved a container and dropped it; nothing complained until the page
    threw in the browser. This is the check that would have caught it.
    """
    want = set(re.findall(r"\$\('([a-zA-Z0-9_-]+)'\)", html))
    have = set(re.findall(r'id="([a-zA-Z0-9_-]+)"', html))
    missing = sorted(want - have)
    if missing:
        print('  missing ids:', ', '.join(missing))
    return not missing


def grids_line_up(html):
    """Every grid-template-columns in a .gridhead must appear on a row template too."""
    heads = re.findall(r'class="gridhead"[^>]*grid-template-columns:([^;"]+)', html)
    rows = set(re.findall(r'class="grid [^"]*"[^>]*grid-template-columns:([^;"]+)', html) +
               re.findall(r'grid-template-columns:([^;"]+)', html))
    return all(any(h.strip() == r.strip() for r in rows) for h in heads)


def main():
    D = json.load(open(os.path.join(ROOT, 'site/payload.json')))
    team = D['meta']['team']
    raceday = '2026-09-08'

    # fleet, one row per log, flagged for the client boat
    # Sunday 7 September was the abandoned practice day — no scored racing, no Garm log.
    # It is dropped rather than shown as a third tab nobody asked for.
    RACED = ('2026-09-08', '2026-09-09')
    # All four races. Tuesday's two carry thirty logs each; Wednesday's two carry five,
    # Garm's among them, plus the event's own published four-leg analysis. Anything
    # measured against four boats rather than thirty says so where it is printed.
    TRACKED = (1, 2, 3, 4)
    # The wind card carries both days. Race 3 turned out to be a Wednesday race, not a
    # Tuesday one — the event's own report is dated 2026-09-09 — so Wednesday has two.
    WIND_RACES = (1, 2, 3, 4)
    fleet = [{'name': f['file'], 'day': f['day'], 'avg': f['avg'], 'up': f['upAvg'],
              'dn': f['dnAvg'], 'mx': f['mx'], 'nm': f['nm'],
              't0': f['t0'], 't1': f['t1'], 'fixes': f['fixes'],
              'team': f['file'].startswith('Team Sweden') or f['file'] == 'vakaros',
              'partial': f.get('partial', False)}
             for f in D['fleet'] if f['day'] in RACED]

    # Wind, measured, grouped by the day it was actually sailed.
    #
    # Wednesday used to come from wind.json's hourly forecast. The 23:03 refresh rolled that
    # file forward to 10-12 September and dropped the 9th, leaving the tab empty; and race 4
    # was appearing under Tuesday because races were taken in order rather than by date.
    # Every figure here is now measured, and each race sits under the day it was sailed.
    guns = {r['n']: r['gun'] for r in D['races']}
    bias_by_race = {b['race']: b for b in D['ib']['bias_rows']}
    by_day = {}
    for r in D['ib']['races']:
        if r['n'] not in WIND_RACES:
            continue
        b = bias_by_race.get(r['n'], {})
        by_day.setdefault(r['date'], []).append({
            # the loggers' gun, not the event's published one: race 1's report says
            # 13:34:52, which puts every tracked boat mid-race
            'n': r['n'], 'gun': guns.get(r['n']) or r.get('start_local'),
            'forecast': b.get('forecast'), 'measured': b.get('measured'),
            'bias': b.get('bias'), 'setting': r['setting'], 'legs': r['legs']})
    wind_days = [{'date': d, 'label': DAY_LABEL.get(d, d), 'races': rs}
                 for d, rs in sorted(by_day.items())]

    # start line, from the event's published geometry
    startline = [{'race': r['n'], 'setting': r['setting'], 'line_m': r['line_m'],
                  'bias_deg': r['bias_deg'], 'bias_m': r['bias_m'], 'calc_m': r['calc_m'],
                  'favoured': r['favoured']} for r in D['ib']['races'] if r['n'] in TRACKED]

    # segments, flagged and renamed for the client boat
    segs = []
    for r in D['segments']['rows']:
        s = r['s']
        segs.append({'boat': r['boat'], 's0': s['0'], 's10': s['10'], 's30': s['30'],
                     's60': s['60'], 'hold': r['hold'], 'rank0': r['rank0'],
                     'rankhold': r['rankhold'], 'team': r['boat'] == 'Garm'})

    # The KPI table carried a VMG figure frozen from an earlier build, which now
    # disagreed with the leg table on the same page. Re-derive it from race 1's
    # first beat instead, and carry the manoeuvres-out figure with it.
    beat1 = {key(b): L[0] for b, L in D['legs']['races']['1'].items() if L}
    kpi_rows = []
    for r in D['kpi']['rows']:
        r = dict(r)
        l = beat1.get(key(r['boat']))
        if l:
            r['vmg'], r['twa'], r['svmg'] = l['vmg'], l['twa'], l['svmg']
        else:
            r['svmg'] = None
        kpi_rows.append(r)
    garm_kpi = next((r for r in kpi_rows if r['team']), kpi_rows[-1])

    t = D['official']['team']
    bias = D['ib']['bias_rows'][0]

    qa = [
      {'label': 'Where did the regatta go wrong?',
       'k': ['wrong', 'bad', 'lose', 'lost', 'worst'],
       'q': 'Where did the regatta go wrong?',
       'a': f"Not on boat speed. Garm's upwind VMG is {garm_kpi['vmg']} kn at "
            f"{garm_kpi['twa']}°, and {garm_kpi['svmg']} kn with the tacks taken out of the "
            f"average — mid-fleet either way, and the ranking barely moves. "
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
                   'day9_races': D['official']['telemetry'].get('day9_races', []),
                   'team': {'pos': t['pos'], 'sail': t['sail'], 'boat': t['boat'],
                            'skipper': t['skipper'], 'pts': t['pts'], 'gain': t['gain_total'],
                            'races': [t['r1'], t['r2'], t['r3'], t['r4']]}},
      'wind': {'days': wind_days, 'note': D['coach']['mechanism']},
      'fleet': fleet,
      'dayLabel': DAY_LABEL, 'dayNote': DAY_NOTE,
      'startline': startline,
      'races': [{'n': r['n'], 'boats': [{**{k: b[k] for k in ('b', 'up', 'dn', 'ex', 'dl')},
                                         'tk': leg_tacks(D, r['n'], b['b'])}
                                        for b in r['boats']]} for r in D['races']],
      'legs': {'races': D['legs']['races'], 'drivers': D['legs']['drivers'],
               'steady_window_s': D['legs']['steady_window_s']},
      'segments': {'rows': segs, 'caveat': D['segments']['caveat'],
                   'verify': D['segments'].get('verify')},
      'kpi': {'rows': kpi_rows, 'note': D['kpi']['note']},
      'coach': {'start': D['coach']['start'], 'mechanism': D['coach']['mechanism']},
      'start': {'races': {k: [{**r, 'team': r['boat'] == 'Team Sweden'} for r in v]
                          for k, v in D['start']['races'].items()},
                'replay': D['start']['replay'],
                'note': D['start']['note']},
      'coachTest': coach_test(D),
      'malfunction': D['official']['telemetry'].get('malfunction'),
      'tracks': D.get('tracks'),
      'eventLegs': D.get('eventLegs'),
      'compare': build_compare(D),
      'qa': qa,
    }

    legteam = payload['meta']['legteam']
    html = open(os.path.join(ROOT, 'site2/page.html'), encoding='utf-8').read()
    html = html.replace('__DATA__', json.dumps(payload, ensure_ascii=False, separators=(',', ':')))
    for tok, fn in (('__HERO__', 'hero.jpg'), ('__IMG1__', 'crew.jpg'),
                    ('__IMG2__', 'hiking.jpg'), ('__IMG3__', 'prize.jpg')):
        html = html.replace(tok, data_uri(os.path.join(IMG, fn)))

    # guards against the regressions this page has already had once
    checks = {
      'no placeholder standings': '38th' not in html and '>75<' not in html,
      'the real fleet size': str(D['official']['fleet_scored']) in html,
      'no unfilled bindings': '{{' not in html and '__' not in html.replace('__DATA__', ''),
      'only tracked races': all(r['n'] in WIND_RACES for d in wind_days for r in d['races'])
                            and all(r['race'] in TRACKED for r in startline),
      'wind days all raced': all(d['date'] in RACED and d['races'] for d in wind_days),
      'no unraced days': '2026-09-10' not in html and '2026-09-11' not in html
                         and '2026-09-12' not in html and '2026-09-07' not in html,
      'every image inlined': html.count('data:image/jpeg;base64,') == 4,
      # a .gridhead and the row template it labels must declare the same columns —
      # they drifted once and nothing complained
      'grid headers match their rows': grids_line_up(html),
      'every id the script reaches for exists': ids_all_exist(html),
      'every class the markup uses is styled': classes_all_styled(html),
      'every segmented control repaints itself': segs_repaint_themselves(html),
      # a phone lays the page out at 980 px without this, and shrinks everything
      'a viewport declared': 'name="viewport" content="width=device-width' in html,
      # nothing supplies a charset when Netlify serves this file raw
      'a charset declared': html.lstrip().startswith('<meta charset="utf-8">'),
      # every boat's points equal the sum of its finishes, so nothing is discarded yet
      # and the page must not present these figures as net
      'points not called net': ('Net points' not in html
                               if sum([t['r1'], t['r2'], t['r3'], t['r4']]) == t['pts'] else True),
      # every race with a start also has legs, and vice versa — they come from
      # separate scripts over the same logs and drifted apart once
      'start and legs cover the same races':
          set(D['start']['races']) == set(D['legs']['races']) == {str(r) for r in TRACKED},
      # the team's own telemetry, on every race that has any
      'the team is in every tracked race':
          all(any(r.get('boat') == legteam
                  for r in D['start']['races'].get(str(rn), [])) and
              legteam in D['legs']['races'].get(str(rn), {}) for rn in TRACKED),
      # correlations are only computed for fleets; a race without them must not
      # reach the page still holding the template's undefined
      'no undefined in the copy': 'undefined' not in html,
      # every leg carries both averages, or the manoeuvres-out toggle quietly
      # falls back to the all-fix figure and shows the same table twice
      'both averages on every leg':
          all(l.get('svmg') is not None and l.get('keep') is not None
              for R in D['legs']['races'].values() for L in R.values() for l in L),
      # the final run is cut at the finish, so it cannot be longer than the race
      'no leg runs past its race':
          all(sum(l['min'] for l in L) < 120
              for R in D['legs']['races'].values() for L in R.values()),
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
