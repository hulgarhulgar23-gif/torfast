"""Generate the Torfast app icon with the standard library only.

Renders a rounded-square deep-ink gradient tile with the torfast bolt as
an RGBA PNG (no Pillow), then macOS `sips` + `iconutil` turn the master
render into an .icns. Everything is deterministic so the icon can be
regenerated and tested.
"""

from __future__ import annotations

import math
import shutil
import struct
import subprocess
import zlib
from pathlib import Path

MASTER_SIZE = 2048
ICONSET_SIZES = (16, 32, 128, 256, 512)

# Palette matches the zen ui theme in torfast/theme.py.
TILE_TOP = (36, 29, 51)
TILE_BOTTOM = (18, 15, 27)
BOLT_COLOR = (196, 178, 248)

# Classic bolt, unit coordinates from the top-left of the tile.
BOLT_POINTS = (
    (0.62, 0.08),
    (0.33, 0.52),
    (0.47, 0.52),
    (0.40, 0.92),
    (0.70, 0.44),
    (0.55, 0.44),
)


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
    )


def write_png(path: Path, size: int, rows: list[bytearray]) -> None:
    raw = b"".join(b"\x00" + bytes(row) for row in rows)
    payload = (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
        + _png_chunk(b"IDAT", zlib.compress(raw, 9))
        + _png_chunk(b"IEND", b"")
    )
    path.write_bytes(payload)


def _rounded_rect_span(y: float, x0: float, x1: float, y0: float, y1: float, radius: float) -> tuple[float, float] | None:
    if y < y0 or y > y1:
        return None
    if y < y0 + radius:
        dy = (y0 + radius) - y
    elif y > y1 - radius:
        dy = y - (y1 - radius)
    else:
        return (x0, x1)
    dx = radius - math.sqrt(max(radius * radius - dy * dy, 0.0))
    return (x0 + dx, x1 - dx)


def _polygon_row_spans(y: float, points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    crossings: list[float] = []
    count = len(points)
    for index in range(count):
        (px, py) = points[index]
        (qx, qy) = points[(index + 1) % count]
        if (py <= y < qy) or (qy <= y < py):
            crossings.append(px + (y - py) * (qx - px) / (qy - py))
    crossings.sort()
    return [
        (crossings[i], crossings[i + 1])
        for i in range(0, len(crossings) - 1, 2)
    ]


def render_master_png(path: Path, size: int = MASTER_SIZE) -> None:
    margin = 0.055 * size
    rect0 = margin
    rect1 = size - margin
    radius = 0.225 * (rect1 - rect0)
    bolt = [(x * size, y * size) for (x, y) in BOLT_POINTS]

    rows: list[bytearray] = []
    for y in range(size):
        row = bytearray(size * 4)
        span = _rounded_rect_span(y + 0.5, rect0, rect1, rect0, rect1, radius)
        if span is not None:
            t = (y - rect0) / max(rect1 - rect0, 1.0)
            t = min(max(t, 0.0), 1.0)
            tile = tuple(
                round(TILE_TOP[i] + (TILE_BOTTOM[i] - TILE_TOP[i]) * t)
                for i in range(3)
            )
            x_start = max(int(math.ceil(span[0] - 0.5)), 0)
            x_end = min(int(math.floor(span[1] - 0.5)), size - 1)
            tile_pixel = bytes((tile[0], tile[1], tile[2], 255))
            row[x_start * 4 : (x_end + 1) * 4] = tile_pixel * (x_end - x_start + 1)
            bolt_pixel = bytes((*BOLT_COLOR, 255))
            for (bolt_x0, bolt_x1) in _polygon_row_spans(y + 0.5, bolt):
                b_start = max(int(math.ceil(bolt_x0 - 0.5)), x_start)
                b_end = min(int(math.floor(bolt_x1 - 0.5)), x_end)
                if b_end >= b_start:
                    row[b_start * 4 : (b_end + 1) * 4] = bolt_pixel * (
                        b_end - b_start + 1
                    )
        rows.append(row)
    write_png(path, size, rows)


def build_icns(icns_path: Path, work_dir: Path) -> dict[str, object]:
    """Render the master PNG and convert it to an .icns via sips/iconutil.

    Returns a report; when the macOS tools are unavailable the report says
    so and the app simply keeps the generic icon.
    """
    report: dict[str, object] = {"ok": True, "icns_path": str(icns_path)}
    sips = shutil.which("sips")
    iconutil = shutil.which("iconutil")
    if sips is None or iconutil is None:
        report.update(
            {"ok": False, "skipped": True, "reason": "sips/iconutil not available"}
        )
        return report

    master = work_dir / "torfast-master.png"
    render_master_png(master)
    iconset = work_dir / "torfast.iconset"
    iconset.mkdir(parents=True, exist_ok=True)
    try:
        for base in ICONSET_SIZES:
            for scale in (1, 2):
                pixels = base * scale
                suffix = "" if scale == 1 else "@2x"
                target = iconset / f"icon_{base}x{base}{suffix}.png"
                subprocess.run(
                    [sips, "-z", str(pixels), str(pixels), str(master), "--out", str(target)],
                    check=True,
                    capture_output=True,
                )
        subprocess.run(
            [iconutil, "-c", "icns", str(iconset), "-o", str(icns_path)],
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as exc:
        report.update(
            {
                "ok": False,
                "reason": "icon tool failed",
                "detail": (exc.stderr or b"").decode("utf-8", "replace")[-400:],
            }
        )
        return report
    return report
