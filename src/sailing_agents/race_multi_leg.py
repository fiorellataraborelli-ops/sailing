"""Segment a COMPLETED race into all of its legs.

`race_legs.segment_first_two_legs` exists because the 7 Sept race was abandoned
and only the first beat and run were meaningful. A race sailed to a finish has
more legs than that — the 8 Sept races were four-leg windward-leewards — so this
module walks the whole race instead of stopping after two turning points.

The method is the same projection trick: project the track onto its dominant
axis (which on a windward-leeward course is the wind axis) and find every
sustained reversal. Each reversal is a mark rounding; the stretch between two of
them is a leg.

Legs are then labelled beat or run. Speed alone would be a fragile test — it
happens to separate cleanly in this fleet, but it would not in light air — so
the label comes from the direction the leg actually travels relative to the
estimated wind, with speed reported alongside so a wrong call is visible.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .race_legs import (
    EARTH_RADIUS_M,
    KNOTS_PER_MS,
    _estimate_sample_rate_hz,
    _smooth,
    _to_local_xy,
    haversine_m,
)
from .vkx_parser import VkxLog


@dataclass
class Leg:
    number: int
    kind: str                  # "beat" | "run"
    start_ts_ms: int
    end_ts_ms: int
    duration_min: float
    path_m: float
    straight_line_m: float
    avg_sog_kn: float
    max_sog_kn: float
    vmg_proxy_kn: float
    manoeuvres: int
    bearing_deg: float
    twa_deg: float | None = None


@dataclass
class Race:
    number: int
    start_ts_ms: int
    end_ts_ms: int
    legs: list = field(default_factory=list)
    wind_deg: float | None = None
    note: str = ""


def race_windows(log: VkxLog) -> list[tuple[int, int]]:
    """(start, end) for each race: a RACE_START paired with the next RACE_END.

    A RACE_END with no RACE_START before it is leftover device state from an
    earlier session and is ignored.
    """
    starts = [ts for ts, ev, _ in log.timer_events if ev == 3]
    ends = [ts for ts, ev, _ in log.timer_events if ev == 4]
    out = []
    for s in starts:
        e = next((x for x in ends if x > s), None)
        if e is not None:
            out.append((s, e))
    return out


def _bearing(a, b) -> float:
    lat1, lon1 = a
    lat2, lon2 = b
    y = math.radians(lon2 - lon1) * math.cos(math.radians((lat1 + lat2) / 2))
    x = math.radians(lat2 - lat1)
    return math.degrees(math.atan2(y, x)) % 360.0


def _ang_diff(a: float, b: float) -> float:
    return abs((a - b + 180) % 360 - 180)


def find_reversals(track, smooth_window_s=150.0, reversal_threshold_m=300.0,
                   min_leg_s=180.0, trend_window_s=1200.0):
    """Indices of every sustained reversal of the along-axis projection."""
    if len(track) < 30:
        return [], []

    ts = [p[0] for p in track]
    lat0, lon0 = track[0][1], track[0][2]
    xy = [_to_local_xy(p[1], p[2], lat0, lon0) for p in track]
    n = len(xy)

    mx = sum(a[0] for a in xy) / n
    my = sum(a[1] for a in xy) / n
    sxx = sum((a[0] - mx) ** 2 for a in xy) / n
    syy = sum((a[1] - my) ** 2 for a in xy) / n
    sxy = sum((a[0] - mx) * (a[1] - my) for a in xy) / n
    theta = 0.5 * math.atan2(2 * sxy, sxx - syy)
    ax, ay = math.cos(theta), math.sin(theta)
    proj = [(a[0] - mx) * ax + (a[1] - my) * ay for a in xy]

    hz = _estimate_sample_rate_hz(ts)
    sm = _smooth(proj, max(3, int(round(smooth_window_s * hz))))

    # Initial direction from a least-squares slope, for the same reason as in
    # race_legs: a two-point probe is fooled by post-start settling.
    w = min(n, max(3, int(round(trend_window_s * hz))))
    xbar = (w - 1) / 2.0
    ybar = sum(sm[:w]) / w
    num = sum((i - xbar) * (sm[i] - ybar) for i in range(w))
    den = sum((i - xbar) ** 2 for i in range(w))
    sign = 1 if (num / den if den else 0.0) >= 0 else -1

    min_gap = int(round(min_leg_s * hz))
    reversals = []
    i = 0
    best_i, best_v = 0, sm[0]
    while i < n - 1:
        i += 1
        v = sm[i]
        if sign > 0:
            if v > best_v:
                best_v, best_i = v, i
            elif best_v - v > reversal_threshold_m and (i - best_i) >= 0 and (best_i - (reversals[-1] if reversals else 0)) >= min_gap:
                reversals.append(best_i)
                sign = -1
                best_i, best_v = i, v
        else:
            if v < best_v:
                best_v, best_i = v, i
            elif v - best_v > reversal_threshold_m and (best_i - (reversals[-1] if reversals else 0)) >= min_gap:
                reversals.append(best_i)
                sign = 1
                best_i, best_v = i, v
    return reversals, sm


def _leg_stats(track, i0, i1, number, hz) -> dict:
    seg = track[i0:i1 + 1]
    path = sum(haversine_m(seg[k][1], seg[k][2], seg[k + 1][1], seg[k + 1][2])
               for k in range(len(seg) - 1))
    straight = haversine_m(seg[0][1], seg[0][2], seg[-1][1], seg[-1][2])
    sogs = [p[3] * KNOTS_PER_MS for p in seg]
    dur_s = (seg[-1][0] - seg[0][0]) / 1000.0

    # Manoeuvres: speed dips below half the leg average, spaced >15 s apart.
    slow = max(2.0, 0.5 * (sum(sogs) / len(sogs)))
    man, last = 0, -10 ** 9
    for k in range(1, len(sogs) - 1):
        if sogs[k] < slow and sogs[k] <= sogs[k - 1] and sogs[k] <= sogs[k + 1] and k - last > 15 * hz:
            man += 1
            last = k

    return {
        "number": number,
        "start_ts_ms": seg[0][0],
        "end_ts_ms": seg[-1][0],
        "duration_min": round(dur_s / 60.0, 2),
        "path_m": round(path, 1),
        "straight_line_m": round(straight, 1),
        "avg_sog_kn": round(sum(sogs) / len(sogs), 2),
        "max_sog_kn": round(max(sogs), 2),
        "vmg_proxy_kn": round((straight / dur_s) * KNOTS_PER_MS, 2) if dur_s > 0 else 0.0,
        "manoeuvres": man,
        "bearing_deg": round(_bearing((seg[0][1], seg[0][2]), (seg[-1][1], seg[-1][2])), 1),
    }


def segment_race(log: VkxLog, start_ts: int, end_ts: int, number: int,
                 wind_deg: float | None = None, **kw) -> Race:
    track = [p for p in log.positions if start_ts <= p[0] <= end_ts]
    race = Race(number=number, start_ts_ms=start_ts, end_ts_ms=end_ts, wind_deg=wind_deg)
    if len(track) < 30:
        race.note = "too few fixes in the race window"
        return race

    hz = _estimate_sample_rate_hz([p[0] for p in track])
    reversals, _ = find_reversals(track, **kw)
    bounds = [0] + reversals + [len(track) - 1]

    for k in range(len(bounds) - 1):
        st = _leg_stats(track, bounds[k], bounds[k + 1], k + 1, hz)
        twa = None
        if wind_deg is not None:
            twa = round(_ang_diff(st["bearing_deg"], wind_deg), 1)
            kind = "beat" if twa < 90 else "run"
        else:
            # Without a wind reference, fall back to the speed split. Reported
            # so the caller can see which basis was used.
            kind = "beat" if st["avg_sog_kn"] < 8.0 else "run"
        race.legs.append(Leg(kind=kind, twa_deg=twa, **st))
    return race


def analyse(log: VkxLog, wind_deg: float | None = None, **kw) -> list[Race]:
    return [segment_race(log, s, e, i + 1, wind_deg=wind_deg, **kw)
            for i, (s, e) in enumerate(race_windows(log))]
