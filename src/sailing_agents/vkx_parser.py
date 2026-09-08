"""Parser for the Vakaros VKX telemetry log format (spec v1.4).

Format reference: https://github.com/vakaros/vkx (row-based binary log,
each row has a U1 key followed by a fixed-size payload for that key).
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field


# Fixed payload sizes (bytes) for rows that are either internal/undocumented
# or trivial framing rows. Real telemetry rows are parsed explicitly below.
_INTERNAL_PAYLOAD_SIZES = {0x01: 32, 0x07: 12, 0x0E: 16, 0x20: 13, 0x21: 52}


@dataclass
class VkxLog:
    """All rows extracted from one VKX file, grouped by message type."""

    positions: list = field(default_factory=list)   # 0x02 (ts_ms, lat, lon, sog_ms, cog_rad, alt_m, qw,qx,qy,qz)
    declinations: list = field(default_factory=list)  # 0x03 (ts_ms, decl_rad, lat, lon)
    timer_events: list = field(default_factory=list)  # 0x04 (ts_ms, event_id, timer_value_s)
    line_positions: list = field(default_factory=list)  # 0x05 (ts_ms, end_type, lat, lon)
    shift_angles: list = field(default_factory=list)  # 0x06 (ts_ms, tack_id, manual, heading_deg, sog_kn)
    device_config: list = field(default_factory=list)  # 0x08 (unused_u8, bitfield, rate_hz)
    wind: list = field(default_factory=list)  # 0x0A (ts_ms, wind_dir_deg, wind_speed_ms) -- apparent
    speed_through_water: list = field(default_factory=list)  # 0x0B (ts_ms, fwd_ms, horiz_ms)
    depth: list = field(default_factory=list)  # 0x0C (ts_ms, depth_m)
    temperature: list = field(default_factory=list)  # 0x10 (ts_ms, temp_c)
    load: list = field(default_factory=list)  # 0x0F (ts_ms, name_bytes, load)
    page_header_versions: list = field(default_factory=list)  # 0xFF version bytes seen
    bytes_total: int = 0
    bytes_consumed: int = 0
    unknown_rows: list = field(default_factory=list)  # (offset, key) where parsing had to stop

    # -- convenience --
    RACE_TIMER_EVENTS = {0: "RESET", 1: "START", 2: "SYNC", 3: "RACE_START", 4: "RACE_END"}

    def race_starts(self) -> list[int]:
        """All RACE_START (event id 3) timestamps in ms, chronological."""
        return [ts for (ts, ev, _val) in self.timer_events if ev == 3]


def parse_bytes(data: bytes) -> VkxLog:
    log = VkxLog(bytes_total=len(data))
    i = 0
    n = len(data)

    while i < n:
        key = data[i]
        i += 1
        try:
            if key == 0xFF:
                log.page_header_versions.append(data[i])
                i += 7
            elif key == 0xFE:
                i += 2
            elif key in _INTERNAL_PAYLOAD_SIZES:
                i += _INTERNAL_PAYLOAD_SIZES[key]
            elif key == 0x02:
                ts = struct.unpack_from("<Q", data, i)[0]
                lat = struct.unpack_from("<i", data, i + 8)[0] * 1e-7
                lon = struct.unpack_from("<i", data, i + 12)[0] * 1e-7
                sog = struct.unpack_from("<f", data, i + 16)[0]
                cog = struct.unpack_from("<f", data, i + 20)[0]
                alt = struct.unpack_from("<f", data, i + 24)[0]
                qw, qx, qy, qz = struct.unpack_from("<ffff", data, i + 28)
                log.positions.append((ts, lat, lon, sog, cog, alt, qw, qx, qy, qz))
                i += 44
            elif key == 0x03:
                ts = struct.unpack_from("<Q", data, i)[0]
                decl = struct.unpack_from("<f", data, i + 8)[0]
                lat = struct.unpack_from("<i", data, i + 12)[0] * 1e-7
                lon = struct.unpack_from("<i", data, i + 16)[0] * 1e-7
                log.declinations.append((ts, decl, lat, lon))
                i += 20
            elif key == 0x04:
                ts = struct.unpack_from("<Q", data, i)[0]
                ev = data[i + 8]
                val = struct.unpack_from("<i", data, i + 9)[0]
                log.timer_events.append((ts, ev, val))
                i += 13
            elif key == 0x05:
                ts = struct.unpack_from("<Q", data, i)[0]
                end_type = data[i + 8]
                lat = struct.unpack_from("<f", data, i + 9)[0]
                lon = struct.unpack_from("<f", data, i + 13)[0]
                log.line_positions.append((ts, end_type, lat, lon))
                i += 17
            elif key == 0x06:
                ts = struct.unpack_from("<Q", data, i)[0]
                tack_id = data[i + 8]
                manual = data[i + 9]
                heading = struct.unpack_from("<f", data, i + 10)[0]
                sog_kn = struct.unpack_from("<f", data, i + 14)[0]
                log.shift_angles.append((ts, tack_id, manual, heading, sog_kn))
                i += 18
            elif key == 0x08:
                unused = struct.unpack_from("<Q", data, i)[0]
                bitfield = struct.unpack_from("<I", data, i + 8)[0]
                rate = data[i + 12]
                log.device_config.append((unused, bitfield, rate))
                i += 13
            elif key == 0x0A:
                ts = struct.unpack_from("<Q", data, i)[0]
                wdir = struct.unpack_from("<f", data, i + 8)[0]
                wspd = struct.unpack_from("<f", data, i + 12)[0]
                log.wind.append((ts, wdir, wspd))
                i += 16
            elif key == 0x0B:
                ts = struct.unpack_from("<Q", data, i)[0]
                fwd = struct.unpack_from("<f", data, i + 8)[0]
                horiz = struct.unpack_from("<f", data, i + 12)[0]
                log.speed_through_water.append((ts, fwd, horiz))
                i += 16
            elif key == 0x0C:
                ts = struct.unpack_from("<Q", data, i)[0]
                d = struct.unpack_from("<f", data, i + 8)[0]
                log.depth.append((ts, d))
                i += 12
            elif key == 0x10:
                ts = struct.unpack_from("<Q", data, i)[0]
                t = struct.unpack_from("<f", data, i + 8)[0]
                log.temperature.append((ts, t))
                i += 12
            elif key == 0x0F:
                ts = struct.unpack_from("<Q", data, i)[0]
                name = data[i + 8:i + 12]
                amt = struct.unpack_from("<f", data, i + 12)[0]
                log.load.append((ts, name, amt))
                i += 16
            else:
                log.unknown_rows.append((i - 1, key))
                break
        except struct.error:
            log.unknown_rows.append((i - 1, key))
            break

    log.bytes_consumed = i
    return log


def parse_file(path: str) -> VkxLog:
    with open(path, "rb") as f:
        return parse_bytes(f.read())
