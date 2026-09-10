"""Wind direction measured from the boats' own tracks.

Tuesday and Wednesday take their per-leg wind from the event's published analysis.
Thursday has no published analysis yet, so it has to come from the tracks — and a
leg's wind is not optional here: VMG, TWA and every manoeuvre count depend on it.

The method is the one a sailor would use by eye. On a beat a boat sails roughly
equal angles either side of the wind, so the two tack headings straddle it and
their bisector IS the wind. Downwind the same bisector points away from it, so add
180. Fixes inside a manoeuvre are excluded: a boat swinging through the eye of the
wind sits between the two modes and drags them together.

Calibrated against the event's own figures for the sixteen legs of races 1-4:
median error 0 deg, mean absolute error 0.9 deg, worst 3 deg. Beats are the tight
ones — every beat came within 2 deg. Runs are looser, and a run where the fleet
disagrees by tens of degrees should be reported with that spread rather than as a
single number.
"""
from __future__ import annotations
import math

from .leg_vmg import manoeuvres, _steady_mask, KNOTS_PER_MS

MIN_SOG_KN = 2.0        # a drifting boat's heading says nothing about the wind
MIN_FIXES = 30          # per tack, before a mode is worth trusting


def circular_mean(degs) -> float:
    x = sum(math.cos(math.radians(d)) for d in degs)
    y = sum(math.sin(math.radians(d)) for d in degs)
    return math.degrees(math.atan2(y, x)) % 360


def seed_from_leg(track) -> float:
    """A starting guess: the bearing of the leg's net displacement.

    A beat travels toward the wind, so this lands within a few tens of degrees —
    close enough to split the fixes into two tacks, which is all the seed is for.
    """
    a, b = track[0], track[-1]
    north = (b[1] - a[1]) * 111320
    east = (b[2] - a[2]) * 111320 * math.cos(math.radians(a[1]))
    return math.degrees(math.atan2(east, north)) % 360


def leg_wind(track, upwind: bool, seed: float | None = None, passes: int = 6):
    """Wind direction for one leg, or None if the two tacks are not both present."""
    w = seed if seed is not None else seed_from_leg(track)
    if not upwind and seed is None:
        w = (w + 180) % 360
    for _ in range(passes):
        keep = _steady_mask(track, manoeuvres(track, w))
        port, stbd = [], []
        for q, k in zip(track, keep):
            if not k or q[3] * KNOTS_PER_MS < MIN_SOG_KN:
                continue
            cog = math.degrees(q[4]) % 360
            rel = ((cog - w + 180) % 360) - 180
            if upwind:
                if abs(rel) > 80:            # reaching or running: not this leg's beat
                    continue
            else:
                if abs(rel) <= 90:           # sailing upwind on a run leg: a recovery
                    continue
                rel = rel - 180 if rel > 0 else rel + 180
            (port if rel < 0 else stbd).append(cog)
        if len(port) < MIN_FIXES or len(stbd) < MIN_FIXES:
            return None
        bisector = circular_mean([circular_mean(port), circular_mean(stbd)])
        new = bisector if upwind else (bisector + 180) % 360
        if abs(((new - w + 180) % 360) - 180) < 0.3:
            return round(new) % 360
        w = new
    return round(w) % 360
