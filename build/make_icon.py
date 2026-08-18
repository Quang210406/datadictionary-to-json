"""Generates build/icon.icns.

Written by hand rather than pulled from a drawing library so the build has
no extra dependency: a PNG is a zlib stream of raw scanlines, and that is
little enough code to keep here. Draws the same rounded gradient square the
window uses as its logo, supersampled 4x for smooth edges, then lets sips and
iconutil produce the sizes macOS wants.
"""

import math
import struct
import subprocess
import sys
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent

SIZE = 1024
SS = 4                      # supersampling factor
INSET = 0.10                # macOS icons sit inside a margin
RADIUS = 0.235              # fraction of the square's side

# Flat teal, matching --accent in the window. The previous icon faded blue
# into violet; that gradient is the single most recognisable AI-design
# signature, and an icon that disagrees with the window it opens is worse
# than either choice alone. A very slight vertical shift is kept so the
# rounded square reads as a solid object rather than a flat sticker.
TOP = (0x11, 0x7C, 0x70)
BOTTOM = (0x0B, 0x5F, 0x56)


def rounded_box_coverage(x, y, side, radius, origin):
    """Signed-distance test for a rounded square, used per subsample."""
    cx = x - (origin + side / 2)
    cy = y - (origin + side / 2)
    half = side / 2 - radius
    dx = max(abs(cx) - half, 0.0)
    dy = max(abs(cy) - half, 0.0)
    return math.hypot(dx, dy) <= radius


def render(size):
    side = size * (1 - 2 * INSET)
    origin = size * INSET
    radius = side * RADIUS
    step = 1.0 / SS
    weight = 1.0 / (SS * SS)

    rows = []
    for py in range(size):
        row = bytearray()
        for px in range(size):
            cover = 0.0
            for sy in range(SS):
                for sx in range(SS):
                    x = px + (sx + 0.5) * step
                    y = py + (sy + 0.5) * step
                    if rounded_box_coverage(x, y, side, radius, origin):
                        cover += weight
            if cover <= 0:
                row += b"\0\0\0\0"
                continue
            # Vertical gradient, positioned within the box rather than the
            # canvas so the inset does not flatten the ends.
            t = min(max((py - origin) / side, 0.0), 1.0)
            r = round(TOP[0] + (BOTTOM[0] - TOP[0]) * t)
            g = round(TOP[1] + (BOTTOM[1] - TOP[1]) * t)
            b = round(TOP[2] + (BOTTOM[2] - TOP[2]) * t)
            row += bytes((r, g, b, round(255 * cover)))
        rows.append(bytes(row))
    return rows


def write_png(path, rows, size):
    def chunk(tag, payload):
        body = tag + payload
        return (struct.pack(">I", len(payload)) + body
                + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF))

    raw = b"".join(b"\0" + row for row in rows)      # filter byte 0 per line
    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw, 9))
           + chunk(b"IEND", b""))
    path.write_bytes(png)


def main():
    iconset = HERE / "icon.iconset"
    iconset.mkdir(exist_ok=True)

    master = HERE / "_icon_1024.png"
    write_png(master, render(SIZE), SIZE)

    # The exact set iconutil expects.
    for base in (16, 32, 128, 256, 512):
        for scale, suffix in ((1, ""), (2, "@2x")):
            pixels = base * scale
            target = iconset / f"icon_{base}x{base}{suffix}.png"
            subprocess.run(["sips", "-z", str(pixels), str(pixels),
                            str(master), "--out", str(target)],
                           check=True, capture_output=True)

    subprocess.run(["iconutil", "-c", "icns", str(iconset),
                    "-o", str(HERE / "icon.icns")], check=True)
    master.unlink()
    print(f"icon.icns written ({(HERE / 'icon.icns').stat().st_size} bytes)")


if __name__ == "__main__":
    sys.exit(main())
