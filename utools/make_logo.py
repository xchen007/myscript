#!/usr/bin/env python3
"""
Generate utools/logo.png — 64×64 blue circle with letter 'M'.
Uses only Python stdlib (no Pillow required).

Run: python utools/make_logo.py
Or:  make utools-logo
"""
from __future__ import annotations
import math, os, struct, zlib

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logo.png')

W = H = 64
CX = CY = 32.0
CIRCLE_R = 29.0
BLUE = (37, 99, 235)   # #2563EB

# Pixel-art letter M defined as filled rectangles: (x0, y0, x1, y1) inclusive
_M_BARS: list[tuple[int, int, int, int]] = [
    (18, 16, 22, 47),   # left vertical bar
    (42, 16, 46, 47),   # right vertical bar
]
# Left diagonal: from (22,16)→(32,26); right diagonal: (42,16)→(32,26)
def _in_m(x: int, y: int) -> bool:
    for x0, y0, x1, y1 in _M_BARS:
        if x0 <= x <= x1 and y0 <= y <= y1:
            return True
    # Left diagonal strokes (thickness=3)
    if 16 <= y <= 32:
        t = (y - 16) / 16.0            # 0..1 top to middle
        cx_l = 22 + t * (32 - 22)      # sweeps x: 22→32
        cx_r = 42 - t * (42 - 32)      # sweeps x: 42→32
        if abs(x - cx_l) < 2.5 or abs(x - cx_r) < 2.5:
            return True
    return False

def get_pixel(x: int, y: int) -> tuple[int, int, int, int]:
    dist = math.hypot(x - CX + 0.5, y - CY + 0.5)
    if dist > CIRCLE_R:
        return (0, 0, 0, 0)                   # transparent outside circle
    if _in_m(x, y):
        return (255, 255, 255, 255)            # white M
    return (*BLUE, 255)                        # blue fill

def _chunk(tag: bytes, data: bytes) -> bytes:
    c = tag + data
    return struct.pack('>I', len(data)) + c + struct.pack('>I', zlib.crc32(c) & 0xFFFFFFFF)

def write_png(path: str) -> None:
    ihdr = _chunk(b'IHDR', struct.pack('>IIBBBBB', W, H, 8, 6, 0, 0, 0))  # RGBA
    raw = bytearray()
    for y in range(H):
        raw.append(0)   # filter type: None
        for x in range(W):
            raw.extend(get_pixel(x, y))
    idat = _chunk(b'IDAT', zlib.compress(bytes(raw), 9))
    iend = _chunk(b'IEND', b'')
    with open(path, 'wb') as f:
        f.write(b'\x89PNG\r\n\x1a\n' + ihdr + idat + iend)
    print(f'✅  logo.png written → {path}')

if __name__ == '__main__':
    write_png(OUT)
