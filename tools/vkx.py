"""Minimal Vakaros .vkx reader.

Layout: the file is a sequence of ~2 KB pages. Each page opens with an 8-byte
header (ff 05 01 00 + uint32 block number) and closes with a 3-byte terminator
(fe + uint16 page length). Records never straddle a page boundary, so page
length varies with how much fitted.
"""
import struct, datetime

RECORD_LEN = {0x02: 45, 0x03: 21, 0x04: 14, 0x05: 18, 0x07: 13, 0x08: 14,
               0x0b: 17, 0x0c: 13, 0x0e: 17, 0x10: 13, 0x21: 53}

def records(path):
    d = open(path, 'rb').read()
    n, i = len(d), 0
    while i < n:
        t = d[i]
        if t == 0xff:                      # page header
            i += 8; continue
        if t == 0xfe:                      # page terminator
            i += 3; continue
        L = RECORD_LEN.get(t)
        if L is None or i + L > n:
            raise ValueError(f'unknown record 0x{t:02x} at {i}')
        yield t, d[i:i + L]
        i += L

def track(path):
    """Yield the 0x02 position/velocity/orientation fixes."""
    for t, r in records(path):
        if t != 0x02:
            continue
        ts, lat, lon, sog, cog, _r, qy, qx, qz, qw = struct.unpack_from('<QiiffI4f', r, 1)
        yield dict(
            t=datetime.datetime.fromtimestamp(ts / 1000, datetime.timezone.utc),
            lat=lat * 1e-7, lon=lon * 1e-7,
            sog_kn=sog * 1.943844,           # m/s -> knots
            cog_deg=cog * 180 / 3.141592653589793 % 360,
            q=(qw, qx, qy, qz),
        )
