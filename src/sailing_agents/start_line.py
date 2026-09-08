"""Start-line geometry: distance to the line at the gun, and where on it you started.

The VKX `0x05` Line Position rows carry the pin (end type 0) and committee-boat
(end type 1) coordinates, logged near-continuously through the session. All six
boats in this regatta recorded byte-identical coordinate ranges, so these are
the real race-committee line ends rather than one crew's guess, and the same
line can be used for every boat.

The line is re-laid between start attempts, so the operative line for a given
gun is the last pin and last boat position logged BEFORE that gun.

Two numbers come out of this, and the second is the tactically interesting one:

  distance_to_line_m  - perpendicular distance from the boat to the line at the
                        gun. Positive = still behind the line (late); negative =
                        already across (over early).
  along_line_from_pin - 0.0 at the pin end, 1.0 at the committee boat end. This
                        is which part of the line the boat actually started on.

A third falls out of the geometry for free: the committee sets the line square
to the wind, so the line's perpendicular is an independent estimate of the wind
direction — the only wind reference this dataset contains, since no boat logged
a wind instrument.
"""
from __future__ import annotations

import math

from .race_legs import EARTH_RADIUS_M
from .vkx_parser import VkxLog

M_PER_DEG_LAT = 111_320.0


def _enu(lat, lon, lat0, lon0):
    """Local east/north metres relative to (lat0, lon0)."""
    east = math.radians(lon - lon0) * EARTH_RADIUS_M * math.cos(math.radians(lat0))
    north = math.radians(lat - lat0) * EARTH_RADIUS_M
    return east, north


def line_at(log: VkxLog, ts_ms: int):
    """The (pin, boat) line ends in effect at `ts_ms`, as (lat, lon) pairs.

    Returns (None, None) if either end was never logged before that time.
    """
    pin = boat = None
    for ts, end_type, lat, lon in log.line_positions:
        if ts > ts_ms:
            break
        if end_type == 0:
            pin = (lat, lon)
        elif end_type == 1:
            boat = (lat, lon)
    return pin, boat


def line_geometry(pin, boat):
    """Length, bearing and the two perpendicular bearings of the line.

    `bearing_deg` runs pin -> committee boat. `square_wind_deg` are the two
    directions perpendicular to the line; the committee aims the line square to
    the wind, so the wind lies along one of them (which one is resolved by
    seeing which side of the line the fleet sails to after the gun).
    """
    lat0, lon0 = pin
    east, north = _enu(boat[0], boat[1], lat0, lon0)
    length_m = math.hypot(east, north)
    bearing = math.degrees(math.atan2(east, north)) % 360.0
    return {
        "length_m": length_m,
        "length_nm": length_m / 1852.0,
        "bearing_deg": bearing,
        "square_wind_deg": ((bearing + 90) % 360.0, (bearing - 90) % 360.0),
    }


def position_vs_line(pos, pin, boat, course_side_sign: float = 1.0):
    """Where `pos` sits relative to the line.

    `course_side_sign` flips the sign of the perpendicular distance so that
    positive always means "behind the line" — see `resolve_course_side`.
    """
    lat0, lon0 = pin
    lx, ly = _enu(boat[0], boat[1], lat0, lon0)      # pin -> boat
    px, py = _enu(pos[0], pos[1], lat0, lon0)        # pin -> position
    line_len = math.hypot(lx, ly)
    if line_len == 0:
        return None

    # Signed perpendicular offset via the 2D cross product, and the projection
    # along the line normalised to 0 (pin) .. 1 (committee boat).
    cross = (lx * py - ly * px) / line_len
    along = (lx * px + ly * py) / (line_len * line_len)
    return {
        "distance_to_line_m": cross * course_side_sign,
        "along_line_from_pin": along,
        "line_length_m": line_len,
    }


def resolve_course_side(log: VkxLog, gun_ts_ms: int, pin, boat, settle_s: float = 120.0):
    """Work out which side of the line is the course side.

    After the gun the fleet sails away from the line onto the first beat, so the
    side the boat is on a couple of minutes later is the course side. Returns a
    sign to multiply the raw perpendicular offset by, so that positive means
    "behind the line".
    """
    target = gun_ts_ms + int(settle_s * 1000)
    later = None
    for p in log.positions:
        if p[0] >= target:
            later = p
            break
    if later is None:
        return 1.0
    raw = position_vs_line((later[1], later[2]), pin, boat)
    if raw is None or raw["distance_to_line_m"] == 0:
        return 1.0
    # That later position is on the COURSE side, so its raw offset must end up
    # negative: the sign we want is the opposite of the one it has.
    return -1.0 if raw["distance_to_line_m"] > 0 else 1.0


def position_at(log: VkxLog, ts_ms: int, max_gap_s: float = 5.0):
    """The GPS fix nearest `ts_ms`, or None if the track has no fix close to it."""
    best = None
    best_dt = None
    for p in log.positions:
        d = abs(p[0] - ts_ms)
        if best_dt is None or d < best_dt:
            best, best_dt = p, d
        elif p[0] > ts_ms and d > best_dt:
            break
    if best is None or best_dt > max_gap_s * 1000:
        return None
    return best


def start_analysis(log: VkxLog, gun_ts_ms: int) -> dict | None:
    """Distance to the line and along-line position at one gun, for one boat."""
    pin, boat = line_at(log, gun_ts_ms)
    if pin is None or boat is None:
        return None
    fix = position_at(log, gun_ts_ms)
    if fix is None:
        return None

    sign = resolve_course_side(log, gun_ts_ms, pin, boat)
    rel = position_vs_line((fix[1], fix[2]), pin, boat, sign)
    if rel is None:
        return None

    geom = line_geometry(pin, boat)
    along = rel["along_line_from_pin"]
    if along < 0.33:
        third = "pin third"
    elif along > 0.67:
        third = "boat third"
    else:
        third = "middle third"

    return {
        "gun_ts_ms": gun_ts_ms,
        "pin": {"lat": pin[0], "lon": pin[1]},
        "committee_boat": {"lat": boat[0], "lon": boat[1]},
        "line_length_m": round(geom["length_m"], 1),
        "line_bearing_deg": round(geom["bearing_deg"], 1),
        "line_square_wind_deg": [round(x, 1) for x in geom["square_wind_deg"]],
        "distance_to_line_m": round(rel["distance_to_line_m"], 1),
        "along_line_from_pin": round(along, 3),
        "started_on": third,
        "sog_at_gun_kn": round(fix[3] * 1.9438444924, 2),
    }
