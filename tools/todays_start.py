#!/usr/bin/env python3
"""What were today's starts? — run it the moment the logs land.

    python3 tools/todays_start.py              # today
    python3 tools/todays_start.py 2026-09-10   # any day

The event's live race-management page is not being populated, and the published
gun in the race reports is unreliable — race 1's report gives 13:34:52, which puts
every tracked boat mid-race. The loggers are the authority: each Atlas records a
RACE_START timer event at the gun, and across the fleet they agree to the second.
The committee's line ends come from the same file, so the line and its bias fall
out of the same source with no second opinion needed.

Nothing here writes to the payload; it is the look-first step before a rebuild.
"""
import sys, os, glob, math, datetime, statistics as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.sailing_agents.vkx_parser import parse_file
from src.sailing_agents import race_multi_leg as rml
from src.sailing_agents import start_line as sl
from src.sailing_agents.wind_from_track import leg_wind, seed_from_leg
from tools.build_legs import name, SRC

TEAM = 'Team Sweden'
hm = lambda ms: datetime.datetime.fromtimestamp(
    ms / 1000, datetime.timezone.utc).strftime('%H:%M:%S')


def main(day=None):
    day = day or datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d')
    found, seen = {}, set()
    for p in sorted(glob.glob(SRC + '/*')):
        if not os.path.isfile(p):
            continue
        try:
            log = parse_file(p)
        except Exception:
            continue
        if not log.positions:
            continue
        d = datetime.datetime.fromtimestamp(log.positions[0][0] / 1000,
                                            datetime.timezone.utc).strftime('%Y-%m-%d')
        b = name(os.path.basename(p))
        if d != day or b in seen:
            continue
        seen.add(b)
        for s, e in rml.race_windows(log):
            # grouped by the gun, not by position in the file — one boat starting its
            # timer twice would otherwise shunt every later window into the wrong race
            found.setdefault(hm(s)[:5], []).append((b, s, e, log))

    if not found:
        print(f'{day}: no logs in {SRC} yet.')
        print('Drop the day\'s .vkx files in, then run this again.')
        return

    print(f'{day}: {len(seen)} boats logged, {len(found)} distinct gun(s).\n')
    for gun, rows in sorted(found.items()):
        seen_b = {b for b, *_ in rows}
        b0, s0, e0, log0 = rows[0]
        print(f'  Gun {gun}Z   ends {hm(e0)}Z   {len(seen_b)} boats'
              + ('' if len(seen_b) > 2 else '   <- too few to be a fleet start'))

        lens, brgs = [], []
        for _, s, _, log in rows:
            ends = sl.line_at(log, s)
            if not ends:
                continue
            pin, cb = ends
            lens.append(math.hypot((cb[0] - pin[0]) * sl.M_PER_DEG_LAT,
                                   (cb[1] - pin[1]) * sl.M_PER_DEG_LAT *
                                   math.cos(math.radians(pin[0]))))
            north = (cb[0] - pin[0]) * sl.M_PER_DEG_LAT
            east = (cb[1] - pin[1]) * sl.M_PER_DEG_LAT * math.cos(math.radians(pin[0]))
            brgs.append(math.degrees(math.atan2(east, north)) % 360)

        winds = []
        for _, s, e, log in rows:
            tr = [q for q in log.positions if s <= q[0] <= e]
            race = rml.segment_race(log, s, e, 1, wind_deg=seed_from_leg(tr[:2400]))
            if race.legs:
                l = race.legs[0]
                w = leg_wind([q for q in tr if l.start_ts_ms <= q[0] <= l.end_ts_ms],
                             l.kind == 'beat')
                if w:
                    winds.append(w)
        if lens and winds:
            L, brg, wind = round(st.median(lens)), st.median(brgs), round(st.median(winds))
            sq = min(((brg + 90) % 360, (brg - 90) % 360),
                     key=lambda x: abs(((x - wind + 180) % 360) - 180))
            off = ((wind - sq + 180) % 360) - 180
            print(f'      line {L} m bearing {brg:.0f}, square to {sq:.0f}, '
                  f'wind {wind} -> {abs(off):.0f} deg, '
                  f'{"pin" if off < 0 else "boat"} favoured by '
                  f'{round(L * abs(math.sin(math.radians(off))))} m')

        for b, s, _, log in rows:
            if b != TEAM:
                continue
            a = sl.start_analysis(log, s)
            if a:
                print(f'      Garm: {a["distance_to_line_m"]:.1f} m from the line at the gun, '
                      f'{a["sog_at_gun_kn"]:.2f} kn, {a["started_on"]}')
        print()
    print('Then: build_start.py, build_legs.py, build_racemeta.py, build_analysis.py')


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else None)
