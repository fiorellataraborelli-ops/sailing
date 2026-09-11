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
* A leg average over every fix is not boat speed — it is boat speed diluted by
  however many times the boat turned. A crew that tacks nineteen times against a
  fleet median of thirteen is charged for it twice: once in the manoeuvre cost,
  and again in a leg average that is quietly measuring manoeuvre count. So the
  averages are computed both ways, and the manoeuvre windows are sized from the
  fleet's own recovery curve rather than assumed. See STEADY_WINDOW_S.
* What a manoeuvre costs is metres and seconds, not knots. A speed dip of 3.5 kn
  says nothing on its own — a boat that loses 3.5 kn for four seconds and one that
  loses it for twenty have paid completely different prices, and neither figure is
  something a crew can weigh against a shift. The cost here is the ground the boat
  failed to make good: what it would have gained in the window at its own settled
  VMG for that leg, minus what it actually gained. See manoeuvre_cost().
"""
from __future__ import annotations
import math

KNOTS_PER_MS = 1.943844

# How long a manoeuvre actually holds the boat down, measured across 30 boats and
# ~1,700 samples per second-offset on 8 September. Speed at the crossing falls to
# 70.6% of the approach for a tack and 64.4% for a gybe, and is back on the
# post-manoeuvre plateau by +10 s and +15 s respectively; the approach starts
# giving way about 10 s out in both cases. These are those windows, rounded out
# by a few seconds. Steady-state figures drop every fix inside them.
STEADY_WINDOW_S = {'tack': (-10, 15), 'gybe': (-10, 20)}


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


def _steady_mask(track, mans) -> list[bool]:
    """True for every fix that is not inside a manoeuvre window."""
    keep = [True] * len(track)
    for m in mans:
        lo, hi = STEADY_WINDOW_S[m['kind']]
        a, b = m['at_ms'] + lo * 1000, m['at_ms'] + hi * 1000
        for i, p in enumerate(track):
            if a <= p[0] <= b:
                keep[i] = False
    return keep


def _dmg(track, wind_deg, upwind, i0, i1):
    """Metres made good along the wind axis between two fixes, integrated."""
    total = 0.0
    for j in range(max(1, i0), min(i1, len(track))):
        dt = (track[j][0] - track[j - 1][0]) / 1000.0
        if dt <= 0 or dt > 5:
            continue
        v = track[j][3] * math.cos(math.radians(_rel(math.degrees(track[j][4]) % 360, wind_deg)))
        total += (v if upwind else -v) * dt
    return total


def manoeuvre_cost(track, mans, wind_deg: float, upwind: bool, ref_vmg_kn: float):
    """Ground lost to each manoeuvre, in metres and in seconds.

    The reference is the boat's own settled VMG for the leg — the speed it was
    making good when it was not turning. Over a manoeuvre's window it would have
    gained ref x window; it actually gained the integral of its VMG. The shortfall
    is the cost, in metres of ground, and dividing by the same reference turns it
    into the seconds of sailing needed to win that ground back.

    Using the leg's own settled VMG rather than a fixed number means a manoeuvre in
    light air is judged against light-air progress, and it makes the parts sum to
    the whole: the manoeuvre losses on a leg add up to the difference between the
    all-fix average and the settled one, which is checked in the tests.
    """
    if not mans or not ref_vmg_kn or ref_vmg_kn <= 0:
        return mans
    ref_ms = ref_vmg_kn / KNOTS_PER_MS
    ts = [p[0] for p in track]
    for m in mans:
        lo, hi = STEADY_WINDOW_S[m['kind']]
        a, b = m['at_ms'] + lo * 1000, m['at_ms'] + hi * 1000
        i0 = next((i for i, t in enumerate(ts) if t >= a), 0)
        i1 = next((i for i, t in enumerate(ts) if t > b), len(ts))
        if i1 <= i0 + 1:
            continue
        window_s = (ts[min(i1, len(ts)) - 1] - ts[i0]) / 1000.0
        got = _dmg(track, wind_deg, upwind, i0, i1)
        lost = ref_ms * window_s - got
        m['window_s'] = round(window_s, 1)
        m['loss_m'] = round(lost, 1)
        m['loss_s'] = round(lost / ref_ms, 1) if ref_ms else None
    return mans


def leg_vmg(track, wind_deg: float, upwind: bool, mans=None) -> dict:
    """VMG statistics for one leg. `track` is race_multi_leg's tuple layout.

    Returns each average twice: `avg_*` over every fix, which is the rate the boat
    actually got round the course, and `steady_*` over the fixes outside a
    manoeuvre, which is boat speed with turning taken out. Neither is the right
    number on its own — the gap between them is the cost of the manoeuvre count.

    Pass `mans` to reuse a manoeuvre list already computed for this leg.
    """
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

    out = {
        'wind_deg': wind_deg,
        'avg_vmg_kn': round(sum(vmg) / len(vmg), 2),
        'avg_sog_kn': round(sum(sog) / len(sog), 2),
        'avg_twa_deg': round(sum(twa) / len(twa), 1),
        'vmg_efficiency': round((sum(vmg) / len(vmg)) / (sum(sog) / len(sog)), 3),
        'best_60s': best,
        'worst_60s': worst,
    }

    # the same three averages over the fixes that are not inside a manoeuvre
    keep = _steady_mask(track, mans if mans is not None else manoeuvres(track, wind_deg))
    n = sum(keep)
    if n >= 10:
        out.update({
            'steady_vmg_kn': round(sum(v for v, k in zip(vmg, keep) if k) / n, 2),
            'steady_sog_kn': round(sum(v for v, k in zip(sog, keep) if k) / n, 2),
            'steady_twa_deg': round(sum(v for v, k in zip(twa, keep) if k) / n, 1),
            'steady_share': round(n / len(track), 3),
        })
        # cost every manoeuvre against that settled VMG, in metres and seconds
        manoeuvre_cost(track, mans if mans is not None else [], wind_deg, upwind,
                       out['steady_vmg_kn'])
    return out


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
                        # the speed dip, kept as a diagnostic. It is not the cost:
                        # see manoeuvre_cost for metres and seconds.
                        'dip_kn': round(entry - low, 2),
                        'recovered': exit_ >= entry - 0.3})
        side = s
    return out
