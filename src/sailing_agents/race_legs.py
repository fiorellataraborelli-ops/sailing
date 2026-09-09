"""Race-start detection and first-upwind / first-downwind leg segmentation.

Method (no wind-sensor data required):
  1. The actual race start is the LAST "RACE_START" (timer event id 3) row in
     the file. Vakaros logs a RACE_START every time a start sequence reaches
     zero, including general recalls/postponed starts that are later reset;
     the final one before racing that is never followed by RACE_END/RESET is
     treated as the real start.
  2. From that instant on, take the boat's course made good and find the
     dominant axis of travel (first principal component of the track's local
     x/y positions). On a windward/leeward course this axis is the
     upwind-downwind axis: tacking/gybing adds only small variance
     perpendicular to it.
  3. Project every fix onto that axis. Beating (upwind) moves monotonically
     one way along the axis at low SOG; after the windward mark the
     projection reverses and SOG jumps up (running/reaching). The first
     sustained reversal is leg 1's end (leg 2's start); the next sustained
     reversal is leg 2's end.
  4. If the device logged real wind (0x0A) or shift-angle (0x06) rows, those
     are reported alongside as corroborating/ additional evidence, but are
     not required for the segmentation itself.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .vkx_parser import VkxLog

EARTH_RADIUS_M = 6371000.0
KNOTS_PER_MS = 1.9438444924


@dataclass
class LegStats:
    name: str
    start_ts_ms: int
    end_ts_ms: int
    n_fixes: int
    path_distance_m: float
    straight_line_distance_m: float
    avg_sog_kn: float
    max_sog_kn: float
    min_sog_kn: float
    num_tacks_or_gybes: int

    @property
    def duration_s(self) -> float:
        return (self.end_ts_ms - self.start_ts_ms) / 1000.0

    @property
    def avg_vmg_kn(self) -> float:
        """Straight-line progress along the leg per unit time, in knots.
        This is a VMG *proxy* along the boat's own track axis, not true
        wind-referenced VMG (no wind direction is available in this file).
        """
        if self.duration_s <= 0:
            return 0.0
        m_per_s = self.straight_line_distance_m / self.duration_s
        return m_per_s * KNOTS_PER_MS


def haversine_m(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def find_final_race_start(log: VkxLog) -> int | None:
    starts = log.race_starts()
    return starts[-1] if starts else None


def _to_local_xy(lat, lon, lat0, lon0):
    x = math.radians(lon - lon0) * EARTH_RADIUS_M * math.cos(math.radians(lat0))
    y = math.radians(lat - lat0) * EARTH_RADIUS_M
    return x, y


def _smooth(values: list[float], window: int) -> list[float]:
    """Centered moving average, O(n) via prefix sums."""
    n = len(values)
    half = max(1, window // 2)
    prefix = [0.0] * (n + 1)
    for i, v in enumerate(values):
        prefix[i + 1] = prefix[i] + v
    out = [0.0] * n
    for i in range(n):
        lo = max(0, i - half)
        hi = min(n, i + half + 1)
        out[i] = (prefix[hi] - prefix[lo]) / (hi - lo)
    return out


def _estimate_sample_rate_hz(ts_list: list[int]) -> float:
    if len(ts_list) < 2:
        return 2.0
    span_s = (ts_list[-1] - ts_list[0]) / 1000.0
    if span_s <= 0:
        return 2.0
    return (len(ts_list) - 1) / span_s


def segment_first_two_legs(
    log: VkxLog,
    race_start_ts_ms: int | None = None,
    smooth_window_s: float = 30.0,
    reversal_threshold_m: float = 300.0,
    skip_boundary_s: float = 10.0,
    min_leg_duration_s: float = 180.0,
    trend_window_s: float = 1200.0,
):
    """Return (leg1_upwind, leg2_downwind, track_after_start) or (None, None, [])."""
    if race_start_ts_ms is None:
        race_start_ts_ms = find_final_race_start(log)
    if race_start_ts_ms is None:
        return None, None, []

    track = [p for p in log.positions if p[0] >= race_start_ts_ms]
    if len(track) < 10:
        return None, None, track

    ts = [p[0] for p in track]
    lat0, lon0 = track[0][1], track[0][2]
    xy = [_to_local_xy(p[1], p[2], lat0, lon0) for p in track]

    n = len(xy)
    mx = sum(p[0] for p in xy) / n
    my = sum(p[1] for p in xy) / n
    sxx = sum((p[0] - mx) ** 2 for p in xy) / n
    syy = sum((p[1] - my) ** 2 for p in xy) / n
    sxy = sum((p[0] - mx) * (p[1] - my) for p in xy) / n
    theta = 0.5 * math.atan2(2 * sxy, sxx - syy)
    ax, ay = math.cos(theta), math.sin(theta)

    proj = [(p[0] - mx) * ax + (p[1] - my) * ay for p in xy]

    hz = _estimate_sample_rate_hz(ts)
    win = max(3, int(round(smooth_window_s * hz)))
    sm = _smooth(proj, win)

    skip_n = max(1, int(round(skip_boundary_s * hz)))
    skip_n = min(skip_n, n - 3)

    # Determine the dominant trend direction with a least-squares slope over
    # a long initial window (default 20 min, or the whole track if shorter).
    # A two-point probe is fooled by post-start settling-in (bearing away,
    # luffing for a lane) that can run the "wrong" way for several minutes;
    # the regression slope is dominated by the much longer real leg trend.
    trend_window_n = min(n, max(skip_n + 3, int(round(trend_window_s * hz))))
    xs_bar = (trend_window_n - 1) / 2.0
    ys_bar = sum(sm[:trend_window_n]) / trend_window_n
    num = sum((i - xs_bar) * (sm[i] - ys_bar) for i in range(trend_window_n))
    den = sum((i - xs_bar) ** 2 for i in range(trend_window_n))
    slope = num / den if den else 0.0
    trend_sign = 1 if slope >= 0 else -1

    def track_extremum(start_i, sign, min_gap_samples):
        """From start_i, follow `sign` direction until a >threshold retracement,
        never returning before min_gap_samples have elapsed since start_i (to
        reject small pre-start/rounding wobble); return index of the turning
        point (the running extremum at the moment the retracement is confirmed)."""
        best_i = start_i
        best_v = sm[start_i]
        for i in range(start_i + 1, n):
            v = sm[i]
            past_min_gap = (i - start_i) >= min_gap_samples
            if sign > 0:
                if v > best_v:
                    best_v, best_i = v, i
                elif best_v - v > reversal_threshold_m and past_min_gap:
                    return best_i
            else:
                if v < best_v:
                    best_v, best_i = v, i
                elif v - best_v > reversal_threshold_m and past_min_gap:
                    return best_i
        return None

    min_gap_samples = int(round(min_leg_duration_s * hz))
    idx_mark1 = track_extremum(skip_n, trend_sign, min_gap_samples)
    if idx_mark1 is None:
        return None, None, track
    idx_mark2 = track_extremum(idx_mark1, -trend_sign, min_gap_samples)
    if idx_mark2 is None:
        idx_mark2 = n - 1

    def build_leg(name, i0, i1):
        seg = track[i0:i1 + 1]
        path_d = sum(
            haversine_m(seg[k][1], seg[k][2], seg[k + 1][1], seg[k + 1][2])
            for k in range(len(seg) - 1)
        )
        straight_d = haversine_m(seg[0][1], seg[0][2], seg[-1][1], seg[-1][2])
        sogs_kn = [p[3] * KNOTS_PER_MS for p in seg]
        # crude tack/gybe counter: local minima in SOG under a slow-speed
        # threshold, spaced at least ~15s apart (maneuvers cause a speed dip).
        tacks = 0
        last_tack_i = -10 ** 9
        slow_kn = max(2.0, 0.5 * (sum(sogs_kn) / len(sogs_kn)))
        for k in range(1, len(sogs_kn) - 1):
            if sogs_kn[k] < slow_kn and sogs_kn[k] <= sogs_kn[k - 1] and sogs_kn[k] <= sogs_kn[k + 1]:
                if k - last_tack_i > 15 * hz:
                    tacks += 1
                    last_tack_i = k
        return LegStats(
            name=name,
            start_ts_ms=seg[0][0],
            end_ts_ms=seg[-1][0],
            n_fixes=len(seg),
            path_distance_m=path_d,
            straight_line_distance_m=straight_d,
            avg_sog_kn=sum(sogs_kn) / len(sogs_kn),
            max_sog_kn=max(sogs_kn),
            min_sog_kn=min(sogs_kn),
            num_tacks_or_gybes=tacks,
        )

    leg1 = build_leg("first_upwind", 0, idx_mark1)
    leg2 = build_leg("first_downwind", idx_mark1, idx_mark2)
    return leg1, leg2, track
