#!/usr/bin/env python3
"""Assemble index.html from the four editable sources in site/.

index.html is a BUILD OUTPUT. Edit the files in this folder, never index.html —
anything written directly into index.html is lost the next time this runs.

    head.html      <title>, fonts, the whole stylesheet
    body.html      page structure and copy
    app.js.html    behaviour, with __PAYLOAD__ where the data goes
    payload.json   every number the page displays

The three HTML parts are concatenated with no separator, because each already
carries its own leading and trailing whitespace.
"""
import json, os, pathlib, sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent

def build() -> str:
    head = (HERE / 'head.html').read_text(encoding='utf-8')
    body = (HERE / 'body.html').read_text(encoding='utf-8')
    js   = (HERE / 'app.js.html').read_text(encoding='utf-8')
    payload = (HERE / 'payload.json').read_text(encoding='utf-8')

    # The page embeds a copy of the wind for hosts that cannot fetch. Re-sync it
    # from data/wind.json on every build: keeping a hand-maintained copy meant the
    # header could advertise one bias while the bearings were computed with another.
    data = json.loads(payload)
    wind_path = ROOT / 'data' / 'wind.json'
    if wind_path.exists():
        wind = json.loads(wind_path.read_text(encoding='utf-8'))
        if data.get('wind') != wind:
            data['wind'] = wind
            payload = json.dumps(data, ensure_ascii=False)
            (HERE / 'payload.json').write_text(payload, encoding='utf-8')
            print('  re-synced the embedded wind from data/wind.json')
        bias = data.get('meta', {}).get('bias')
        if bias is not None and abs(wind.get('bias_deg', bias) - bias) > 0.05:
            sys.exit(f"build refused: meta.bias {bias} but wind.json was built "
                     f"with {wind.get('bias_deg')} — rerun tools/fetch_wind.py")
    if '__PAYLOAD__' not in js:
        sys.exit('app.js.html has no __PAYLOAD__ placeholder')
    out = head + body + js.replace('__PAYLOAD__', payload)

    # guards for regressions this page has actually suffered
    checks = {
        'the line-square fix (brg - 90, not + 90)': 'norm(brg - 90)' in out,
        'a light-only palette':      'prefers-color-scheme:dark' not in out,
        'no stale Vercel reference': 'Vercel' not in out,
        'the official results panel': 'drawOfficial' in out,
        'nothing below 12px':        '11.5px/1.5' not in out,
    }
    bad = [k for k, ok in checks.items() if not ok]
    if bad:
        sys.exit('build refused, lost: ' + '; '.join(bad))
    return out

if __name__ == '__main__':
    html = build()
    assert html.lstrip().startswith('<meta charset="utf-8">'), \
        'the brief must declare a charset: nothing else does when it is served raw'
    (ROOT / 'index.html').write_text(html, encoding='utf-8')
    print(f'wrote index.html — {len(html)} bytes')
