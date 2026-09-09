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

    json.loads(payload)                      # fail loudly on malformed data
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
    (ROOT / 'index.html').write_text(html, encoding='utf-8')
    print(f'wrote index.html — {len(html)} bytes')
