#!/usr/bin/env python3
"""Publish the whole analysis as a flat, documented dataset -> data/v1/.

site/payload.json is shaped for one page's renderers. This splits it into
per-subject files a website, a notebook or a BI tool can consume without
knowing anything about the page, and writes a CSV alongside every table.
Nothing is recomputed here: this is a projection, so the site and the dataset
can never disagree.
"""
import json, os, csv, io, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'data/v1')
BASE = 'https://github.com/fiorellataraborelli-ops/sailing/tree/main/data/v1'

KN = 'knots'
DEG = 'degrees true'

FIELDS = {
  'fleet': {
    'file': 'Log file, named for the boat', 'day': 'Date of the session (UTC)',
    't0': 'First fix, UTC', 't1': 'Last fix, UTC', 'fixes': 'Number of position fixes',
    'nm': 'Distance sailed, nautical miles', 'mx': f'Peak SOG, {KN}',
    'avg': f'Mean SOG over the whole session, {KN}',
    'upAvg': f'Mean SOG below 8 kn (treated as upwind), {KN}',
    'dnAvg': f'Mean SOG at or above 8 kn (treated as downwind), {KN}'},
  'legs': {
    'race': 'Race number', 'boat': 'Boat', 'n': 'Leg number, 1-4',
    'kind': 'beat (upwind) or run (downwind)', 'wind': f'Wind on this leg as measured by the event, {DEG}',
    'min': 'Leg duration, minutes', 'sog': f'Mean speed over ground, {KN}',
    'vmg': f'Mean wind-referenced VMG, {KN} — the component of boat speed along the wind axis',
    'twa': 'Mean true wind angle, degrees off the wind',
    'eff': 'VMG divided by SOG (definitional, not an independent measure)',
    'extra': 'Distance sailed beyond the straight line, metres',
    'tacks': 'Settled tacks', 'gybes': 'Settled gybes',
    'tloss': f'Mean speed lost per tack, {KN}', 'gloss': f'Mean speed lost per gybe, {KN}'},
  'segments': {
    'boat': 'Boat', 's0': f'Instantaneous peak speed, {KN}',
    's5': f'Best speed held 5 s, {KN}', 's10': f'Best speed held 10 s, {KN}',
    's20': f'Best speed held 20 s, {KN}', 's30': f'Best speed held 30 s, {KN}',
    's60': f'Best speed held 60 s, {KN}',
    'hold': 'The 60 s figure divided by the peak — how much of the headline number survives a minute',
    'rank0': 'Rank on peak', 'rank60': 'Rank on the 60 s figure', 'rankhold': 'Rank on hold'},
  'kpi': {
    'boat': 'Boat', 'pos': 'Overall position', 'pts': 'Total points — no discard has been applied at four races', 'team': 'True for the client boat',
    'gain': 'Places won between the first windward mark and the finish, summed over races',
    'peak': f'Instantaneous peak speed on 9 Sep, {KN}', 's60': f'Best speed held 60 s on 9 Sep, {KN}',
    'hold': 'Hold ratio', 'vmg': f'Mean upwind VMG from this boat\'s own log, {KN}',
    'twa': 'Mean upwind true wind angle, degrees'},
  'races': {
    'race': 'Race number', 'boat': 'Boat', 'm0': 'Cumulative minutes at mark 1',
    'm1': 'Cumulative minutes at mark 2', 'm2': 'Cumulative minutes at mark 3',
    'up': f'Mean upwind SOG, {KN}', 'dn': f'Mean downwind SOG, {KN}',
    'ex': 'Extra distance sailed over the race, metres', 'tk': 'Tacks',
    'dl': 'Distance to the start line at the gun, metres (negative = over)',
    'al': 'Position along the line, 0 = pin, 1 = committee boat'},
  'wind': {
    'date': 'Forecast date', 'hr': 'Hour, UTC', 'raw': f'Model consensus wind direction, {DEG}',
    'cor': f'Direction after the +16.1 deg fleet-measured bias, {DEG}; null when not trusted',
    'sp': 'Spread between the three models, degrees',
    'kn': f'Wind speed, {KN}', 'gust': f'Gust, {KN}', 'mslp': 'Pressure, hPa',
    'trust': 'False below 8 kn or above 30 deg of spread — the bias is not applied there'},
  'bias': {
    'race': 'Race number', 'forecast': f'GRIB direction at the first beat, {DEG}',
    'measured': f'Direction measured on the water, {DEG}', 'bias': 'Forecast minus measured, degrees',
    'old_observed': 'An earlier, superseded observation, kept for audit',
    'old_bias': 'The error that earlier observation produced'},
  'startline': {
    'race': 'Race number', 'setting': f'Direction the committee set the line to, {DEG}',
    'line_m': 'Line length, metres', 'bias_deg': 'Line bias, degrees off square',
    'bias_m': 'Advantage to the favoured end, metres, as the event published it',
    'calc_m': 'The same advantage from our own geometry: line_m x sin(bias_deg)',
    'favoured': 'Favoured end'},
  'official': {
    'pos': 'Overall position', 'sail': 'Sail number', 'boat': 'Boat', 'pts': 'Total points — no discard has been applied at four races',
    'r': 'Finishing position in each race', 'gain': 'Places won after the first windward mark'},
}


def wcsv(name, rows, cols):
    if not rows:
        return None
    with open(os.path.join(OUT, name + '.csv'), 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction='ignore')
        w.writeheader()
        for r in rows:
            w.writerow({k: ('true' if v is True else 'false' if v is False else
                            json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v)
                        for k, v in r.items()})
    return name + '.csv'


def wjson(name, obj):
    with open(os.path.join(OUT, name + '.json'), 'w') as f:
        json.dump(obj, f, indent=1, ensure_ascii=False)
    return name + '.json'


def main():
    os.makedirs(OUT, exist_ok=True)
    D = json.load(open(os.path.join(ROOT, 'site/payload.json')))
    files = []

    def add(name, obj, rows=None, cols=None, about='', fields=None):
        j = wjson(name, obj)
        c = wcsv(name, rows, cols) if rows else None
        files.append({'name': name, 'json': j, 'csv': c, 'rows': len(rows) if rows else None,
                      'about': about, 'fields': fields or FIELDS.get(name)})

    # --- provenance -------------------------------------------------------
    add('meta', {**D['meta'], 'event': D['official']['event'],
                 'generated_utc': datetime.datetime.now(datetime.timezone.utc)
                                  .strftime('%Y-%m-%dT%H:%M:%SZ'),
                 'telemetry': D['official']['telemetry']},
        about='Venue, calibrated model bias, tacking angle, event dates and telemetry coverage.')

    # --- fleet log summaries ---------------------------------------------
    add('fleet', D['fleet'], D['fleet'], list(FIELDS['fleet']),
        about='One row per decoded .vkx log: session extent, fix count, distance and speed splits.')

    # --- per-leg VMG ------------------------------------------------------
    legrows = [{'race': int(rn), 'boat': b, **l}
               for rn, R in D['legs']['races'].items() for b, L in R.items() for l in L]
    add('legs', {'source': D['legs']['source'], 'drivers': D['legs']['drivers'],
                 'rows': legrows}, legrows, list(FIELDS['legs']),
        about='Wind-referenced VMG per boat per leg, plus the correlations between each '
              'variable and first-beat VMG across the tracked fleet.')

    # --- per-race boat rows ----------------------------------------------
    racerows = [{'race': r['n'], **b} for r in D['races'] for b in r['boats']]
    add('races', {'races': [{k: v for k, v in r.items() if k != 'boats'} for r in D['races']],
                  'rows': racerows}, racerows, list(FIELDS['races']),
        about='Mark timings, speed splits and start-line position per boat per race, with the '
              'race header (gun, line length and bearing, measured wind) alongside.')

    # --- Wednesday speed segments ----------------------------------------
    segrows = [{'boat': r['boat'], **{'s' + str(w): r['s'][str(w)] for w in D['segments']['windows']},
                'hold': r['hold'], 'rank0': r['rank0'], 'rank60': r['rank60'],
                'rankhold': r['rankhold']} for r in D['segments']['rows']]
    add('segments', {**{k: v for k, v in D['segments'].items() if k != 'rows'}, 'rows': segrows},
        segrows, list(FIELDS['segments']),
        about='Maximum speed held over rolling windows, 9 Sep. Transcribed from the event\'s '
              'published table; the hold ratio and ranks are derived here.')

    # --- joined KPI table -------------------------------------------------
    add('kpi', D['kpi'], D['kpi']['rows'], list(FIELDS['kpi']),
        about='Top five and the client boat joined across scored results, the segment table '
              'and VMG from the logs. Nulls mean no data, never zero.')

    # --- official standings ----------------------------------------------
    add('official', D['official'], D['official']['top'] + [
        {'pos': D['official']['team']['pos'], 'sail': D['official']['team']['sail'],
         'boat': D['official']['team']['boat'], 'pts': D['official']['team']['pts'],
         'r': [D['official']['team'][k] for k in ('r1', 'r2', 'r3', 'r4')],
         'gain': D['official']['team']['gain_total']}], list(FIELDS['official']),
        about='Scored standings, not derived from telemetry.')

    # --- wind forecast ----------------------------------------------------
    wrows = [{'date': d['date'], **r} for d in D['wind']['days'] for r in d['rows']]
    add('wind', D['wind'], wrows, list(FIELDS['wind']),
        about='Three-model consensus at the race area, hourly 11:00-18:00 UTC, refreshed '
              'every three hours. Raw and bias-corrected direction side by side.')

    # --- model bias calibration ------------------------------------------
    add('bias', {'note': D['ib']['bias_note'], 'trend': D['ib']['bias_trend'],
                 'rows': D['ib']['bias_rows']}, D['ib']['bias_rows'], list(FIELDS['bias']),
        about='GRIB forecast against wind measured on the water, per race. This is where the '
              '+16.1 deg correction comes from, and it is not a constant.')

    # --- start line -------------------------------------------------------
    slrows = [{'race': r['n'], 'setting': r['setting'], 'line_m': r['line_m'],
               'bias_deg': r['bias_deg'], 'bias_m': r['bias_m'], 'calc_m': r['calc_m'],
               'favoured': r['favoured']} for r in D['ib']['races']]
    add('startline', {'source': D['ib']['source'], 'rows': slrows}, slrows,
        list(FIELDS['startline']),
        about='Line geometry per race, with the event\'s published advantage beside the one '
              'our own formula produces from the geometry alone.')

    # --- measured wind by leg --------------------------------------------
    lgrows = [{'race': r['n'], **r['legs']} for r in D['ib']['races']]
    add('wind_by_leg', {'rows': lgrows}, lgrows, ['race', 'uw1', 'dw1', 'uw2', 'dw2'],
        about='Wind bearing measured on each leg of each race by the event.',
        fields={'race': 'Race number', 'uw1': f'First upwind, {DEG}', 'dw1': f'First downwind, {DEG}',
                'uw2': f'Second upwind, {DEG}', 'dw2': f'Second downwind, {DEG}'})

    # --- day comparison ---------------------------------------------------
    add('daycompare', D['daycompare'], D['daycompare']['rows'],
        list(D['daycompare']['rows'][0]) if D['daycompare']['rows'] else None,
        about='Boats with a log on both 8 and 9 Sep — same hulls, same crews, different breeze.')

    # --- narrative, kept as data -----------------------------------------
    add('coach', D['coach'], about='Coaching notes, transcribed. Not measured, and labelled as such.')
    add('brief', D['brief'], about='The analysis requirements, with what is validated and what is open.')

    # --- manifest ---------------------------------------------------------
    tracks = os.path.join(OUT, 'tracks/index.json')
    manifest = {
      'dataset': 'J/70 World Championship 2026, Cascais — race analysis from Vakaros Atlas telemetry',
      'version': 'v1',
      'generated_utc': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
      'base_url': BASE,
      'licence_note': 'Telemetry belongs to the boats that recorded it. Scored results and race '
                      'analysis are the event organisers\'. Published here for the teams involved.',
      'conventions': {
        'time': 'UTC throughout, ISO 8601 with a trailing Z',
        'speed': 'knots unless a field says otherwise',
        'bearings': 'degrees true, 0-360',
        'wind_direction': 'the direction the wind is coming FROM',
        'null': 'means no data. It never means zero, and no file substitutes one for the other',
        'boat_names': 'as written on the log file, with a small alias map applied; the same '
                      'string is used as the join key across every file',
      },
      'files': files,
    }
    if os.path.exists(tracks):
        ti = json.load(open(tracks))
        manifest['files'].append({
          'name': 'tracks', 'json': 'tracks/index.json', 'csv': None, 'rows': ti['n_files'],
          'about': f'Position, SOG, COG and leg index at {ti["step_s"]} s for every boat in '
                   f'races 1 and 2, one columnar file per boat per race, plus estimated mark '
                   f'positions. This is what a course plan view or a polar scatter is drawn from.',
          'fields': {'t': 'seconds since start_utc', 'lat': 'degrees', 'lon': 'degrees',
                     'sog': KN, 'cog': DEG, 'leg': '1-4, 0 outside a leg'}})
    wjson('index', manifest)
    readme(manifest)

    print(f'{len(manifest["files"])} datasets -> {OUT}')
    for f in manifest['files']:
        print(f'  {f["name"]:14} {str(f["rows"] or ""):>6} rows  {f["json"]}'
              + (f' + {f["csv"]}' if f['csv'] else ''))


def readme(m):
    """The data dictionary is generated from the manifest, so it cannot drift."""
    L = ['# Cascais 2026 — race analysis dataset (v1)\n', m['dataset'] + '\n',
         f"Generated {m['generated_utc']}. Every file here is a projection of the same analysis "
         "the live page renders, so the two cannot disagree. Rebuild with "
         "`python3 tools/export_data.py` and `python3 tools/export_tracks.py`.\n",
         '## Conventions\n']
    L += [f'- **{k}** — {v}' for k, v in m['conventions'].items()]
    L += ['', '## Files\n', '| Dataset | Rows | JSON | CSV | What it is |', '|---|---:|---|---|---|']
    L += [f"| `{f['name']}` | {f['rows'] or ''} | `{f['json']}` | "
          f"{('`' + f['csv'] + '`') if f['csv'] else '—'} | {f['about']} |" for f in m['files']]
    L += ['', '## Field dictionary\n']
    for f in m['files']:
        if not f.get('fields'):
            continue
        L += [f"### `{f['name']}`\n", '| Field | Meaning |', '|---|---|']
        L += [f'| `{k}` | {v} |' for k, v in f['fields'].items()]
        L += ['']
    L += ['## Joining\n',
          '`boat` is the join key everywhere. `race` is 1-3 for 8 September; race 4 '
          '(9 September) is scored but has no published wind or bias analysis, so it appears in '
          '`official` and not in `legs`, `races`, `bias` or `startline`.\n',
          '## What is measured and what is inferred\n',
          '- **Measured by the instrument** — position, SOG, COG, and the committee/pin line '
          'positions the Atlas recorded.',
          '- **Derived here** — VMG, TWA, leg segmentation, manoeuvre counts and costs, extra '
          'distance, hold ratios, and the model bias.',
          '- **Taken from the event** — scored results, measured leg winds, published line bias, '
          'and the 9 September speed segment table.',
          '- **Not available at all** — true wind from any boat (no instrument logged one) and '
          'recorded mark roundings. Mark positions in `tracks/index.json` are the median leg '
          'boundary across the fleet, with the spread quoted, and are estimates.\n']
    open(os.path.join(OUT, 'README.md'), 'w').write('\n'.join(L))


if __name__ == '__main__':
    main()
