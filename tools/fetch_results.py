#!/usr/bin/env python3
"""Official standings -> data/event/results.json.

The results page renders its table from an AJAX endpoint, so this fetches that
directly rather than scraping the rendered page: one request, no browser, and it
can be re-run when another race is scored.

A discarded race is printed in brackets and a scoring code (DNC, DNF, DSQ, PRP)
sits in front of its points. Both are kept — a boat's worst race being a DNC
rather than a bad race is the difference between bad luck and bad sailing.
"""
import json, os, re, subprocess, sys, html as htmlmod

URL = ('https://cascaisj70worlds2026.cncascais.com/en/default/races/resultsajax'
       '?id=10841&idsc2r=32340&allResults=1&handicap=')
UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0 Safari/537.36'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'data/event/results.json')


# The endpoint emits <tr> with no closing tag, and hides a sort key in a display:none
# span inside every cell ("punt_ _0000004" in front of the 4). Both have to be handled
# or the table parses as nothing, or as its own sort keys.
HIDDEN = re.compile(r'<span[^>]*display\s*:\s*none[^>]*>.*?</span>', re.S | re.I)


def cell_text(td):
    t = HIDDEN.sub(' ', td)
    t = re.sub(r'<[^>]+>', ' ', t)
    return re.sub(r'\s+', ' ', htmlmod.unescape(t)).strip()


def split_rows(raw):
    """Rows are <tr>-separated, not <tr></tr>-wrapped."""
    for chunk in re.split(r'<tr\b[^>]*>', raw)[1:]:
        cells = [cell_text(c) for c in re.split(r'<t[dh]\b[^>]*>', chunk)[1:]]
        if cells:
            yield cells


def parse_race(s):
    """'DNC (101)' -> (101.0, 'DNC', True); '(25)' -> (25.0, None, True); '4' -> (4.0, None, False)"""
    disc = '(' in s
    code = (re.match(r'\s*\(?\s*([A-Z]{2,4})\b', s) or [None, None])[1]
    num = re.search(r'(\d+(?:\.\d+)?)', s.replace('(', ' ').replace(')', ' '))
    return (float(num.group(1)) if num else None), code, disc


def main():
    raw = subprocess.run(['curl', '-s', '-m', '60', '-A', UA,
                          '-H', 'X-Requested-With: XMLHttpRequest', URL],
                         capture_output=True, text=True).stdout
    rows = []
    for tds in split_rows(raw):
        if len(tds) < 9 or not tds[0].isdigit():
            continue
        races = [parse_race(x) for x in tds[8:] if x]
        rows.append({'pos': int(tds[0]), 'sail': tds[1], 'boat': tds[2], 'cat': tds[5],
                     'net': float(tds[6]), 'total': float(tds[7]),
                     'races': [r[0] for r in races],
                     'codes': [r[1] for r in races],
                     'discard': next((i + 1 for i, r in enumerate(races) if r[2]), None)})
    if not rows:
        sys.exit('no rows parsed — the endpoint or its markup has changed')
    n_races = max(len(r['races']) for r in rows)
    rows = [r for r in rows if len(r['races']) == n_races]
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump({'source': URL, 'fleet': len(rows), 'races_scored': n_races,
               'discard_applied': any(r['discard'] for r in rows), 'rows': rows},
              open(OUT, 'w'), ensure_ascii=False, indent=1)
    g = next((r for r in rows if r['boat'].upper() == 'GARM'), None)
    print(f'{len(rows)} boats, {n_races} races scored, '
          f'discard {"applied" if any(r["discard"] for r in rows) else "not applied"}')
    if g:
        print(f'  Garm: {g["pos"]}th, net {g["net"]:g} of {g["total"]:g}, '
              f'races {g["races"]}, discarding race {g["discard"]}')
    print('  top 5:', ', '.join(f'{r["pos"]} {r["boat"]} {r["net"]:g}' for r in rows[:5]))


if __name__ == '__main__':
    main()
