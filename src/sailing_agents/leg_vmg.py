"""Wind-referenced VMG, and manoeuvre cost, per leg.

`race_multi_leg` segments a race and reports `vmg_proxy_kn` — straight-line
distance over elapsed time. That is a course-made-good rate, not VMG: it cannot
tell a boat that sailed a longer fast route from one that sailed a shorter slow
one, and it knows nothing about the wind.

Given a wind direction this computes the real thing — the component of boat
speed along the wind axis, averaged over the leg — plus what each tack and gybe
actually cost.

Two things that are easy to get wrong, and are handled here:

* A tack and a gybe are told apart by the point of sail **either side** of the
  crossing, never by the heading at the crossing itself. At the moment a boat
  passes through the wind axis its heading is by definition near the wind, so
  an instantaneous test calls every gybe a tack.
* The heading oscillates constantly, especially surfing downwind, so the
  off-wind angle is smoothed and a crossing only counts once the boat has
  settled past a margin on the new side.
"""
from __future__ import annotations
import math

KNOTS_PER_MS = 1.943844


def _smooth(v, k):
    if k < 3 or k >= len(v):
        return list(v)
    h, out = k // 2, []
    for i in range(len(v)):
        a, b = max(0, i - h), min(len(v), i + h + 1)
        out.append(sum(v[a:b]) / (b - a))
    return out


def _rel(cog_deg: float, wind_deg: float) -> float:
    """Heading relative to the wind, -180..180. 0 = sailing straight upwind."""
    return ((cog_deg - wind_deg + 180) % 360) - 180


def leg_vmg(track, wind_deg: float, upwind: bool) -> dict:
    """VMG statistics for one leg. `track` is race_multi_leg's tuple layout."""
    if len(track) < 10:
        return {}
    sog = [p[3] * KNOTS_PER_MS for p in track]
    cog = [math.degrees(p[4]) % 360 for p in track]
    rel = [_rel(c, wind_deg) for c in cog]
    # component along the wind axis; positive means making good progress in the
    # direction this leg is trying to go
    comp = [s * math.cos(math.radians(r)) for s, r in zip(sog, rel)]
    vmg = [c if upwind else -c for c in comp]
    twa = [abs(r) for r in rel]

    hz = max(1e-6, (len(track) - 1) * 1000.0 / max(1, track[-1][0] - track[0][0]))
    win = max(5, int(round(60 * hz)))          # a 60-second window
    best = worst = None
    if len(vmg) > win:
        step = max(1, win // 6)
        means = [(sum(vmg[i:i + win]) / win, i) for i in range(0, len(vmg) - win, step)]
        bv, bi = max(means); wv, wi = min(means)
        best  = {'vmg': round(bv, 2), 'at_ms': track[bi + win // 2][0]}
        worst = {'vmg': round(wv, 2), 'at_ms': track[wi + win // 2][0]}

    return {
        'wind_deg': wind_deg,
        'avg_vmg_kn': round(sum(vmg) / len(vmg), 2),
        'avg_sog_kn': round(sum(sog) / len(sog), 2),
        'avg_twa_deg': round(sum(twa) / len(twa), 1),
        'vmg_efficiency': round((sum(vmg) / len(vmg)) / (sum(sog) / len(sog)), 3),
        'best_60s': best,
        'worst_60s': worst,
    }


def manoeuvres(track, wind_deg: float, settle_deg: float = 20.0) -> list[dict]:
    """Every settled crossing of the wind axis, typed and costed."""
    if len(track) < 30:
        return []
    hz = max(1e-6, (len(track) - 1) * 1000.0 / max(1, track[-1][0] - track[0][0]))
    sog = [p[3] * KNOTS_PER_MS for p in track]
    rel = _smooth([_rel(math.degrees(p[4]) % 360, wind_deg) for p in track],
                  max(3, int(round(15 * hz))))

    out, side = [], (1 if rel[0] > 0 else -1)
    span = max(5, int(round(20 * hz)))         # +/- 20 s around the crossing
    for i in range(1, len(rel)):
        s = 1 if rel[i] > 0 else -1
        if s == side or abs(rel[i]) < settle_deg:
            continue
        a, b = max(0, i - span), min(len(track), i + span)
        # point of sail on either side decides tack vs gybe, not the crossing
        pos = sum(abs(r) for r in rel[a:b]) / (b - a)
        entry = max(sog[a:i]) if i > a else 0.0
        low = min(sog[a:b])
        exit_ = max(sog[i:b]) if b > i else 0.0
        if entry > 2.5:
            out.append({'kind': 'tack' if pos < 90 else 'gybe',
                        'at_ms': track[i][0],
                        'entry_kn': round(entry, 2),
                        'min_kn': round(low, 2),
                        'exit_kn': round(exit_, 2),
                        'loss_kn': round(entry - low, 2),
                        'recovered': exit_ >= entry - 0.3})
        side = s
    return out
