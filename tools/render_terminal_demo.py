#!/usr/bin/env python3
"""Generate the animated terminal demo SVG embedded in the README.

The demo is a scripted replay of a real `torfast open` + `torfast status`
session. All numbers shown come from the verified artifact
`results/torfast-promoted-quality-check-20260707T002336` (candidate median
open-browser elapsed 4.4s vs baseline 11.2-12.3s); only the timeline is
compressed. The output is deterministic so the committed asset can be
regenerated and diffed; never hand-edit the SVG.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from xml.sax.saxutils import escape

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPO_ROOT / "docs" / "assets" / "torfast-demo.svg"

WIDTH = 760
LINE_HEIGHT = 19
HEADER_HEIGHT = 36
PADDING_X = 18
PADDING_BOTTOM = 18
FONT_SIZE = 13
LOOP_SECONDS = 16.0

COLORS = {
    "bg": "#0d1117",
    "frame": "#30363d",
    "text": "#e6edf3",
    "dim": "#8b949e",
    "green": "#3fb950",
    "cyan": "#56d4dd",
    "purple": "#bc8cff",
    "red": "#f85149",
    "yellow": "#d29922",
}


@dataclass
class Line:
    """One terminal line: (color-name, text) segments and its reveal time."""

    segments: list[tuple[str, str]]
    at: float
    row: int
    until: float | None = None


@dataclass
class Script:
    lines: list[Line] = field(default_factory=list)

    def add(
        self,
        at: float,
        *segments: tuple[str, str],
        until: float | None = None,
        row: int | None = None,
    ) -> None:
        # A transient line (spinner) can hand its row to a later line so the
        # replay does not leave a blank gap when it disappears.
        next_row = (
            row
            if row is not None
            else (max((line.row for line in self.lines), default=-1) + 1)
        )
        self.lines.append(Line(list(segments), at, next_row, until))

    @property
    def row_count(self) -> int:
        return max((line.row for line in self.lines), default=-1) + 1


def demo_script() -> Script:
    script = Script()
    dim, text, green, cyan, purple = "dim", "text", "green", "cyan", "purple"

    script.add(
        0.4,
        (dim, "$ "),
        (text, "torfast open --url https://check.torproject.org/"),
    )
    script.add(
        0.9,
        (cyan, "⠹ "),
        (text, "opening Tor Browser over Tor …"),
        until=4.6,
    )
    script.add(
        4.6,
        (green, "  ✓ "),
        (text, "open done  "),
        (dim, "wall 12.5s"),
        row=1,
    )
    script.add(
        5.0,
        (dim, "    page             "),
        (text, "https://check.torproject.org/"),
    )
    script.add(
        5.3,
        (dim, "    browser session  "),
        (text, "4.4s "),
        (green, "✓"),
        (dim, "  (stock profile: 11.2s)"),
    )
    script.add(5.6, (dim, "    launch gate      "), (text, "tor_boot_95"))
    script.add(
        5.9,
        (dim, "    quality prefs    "),
        (green, "✓"),
        (dim, "  exact Tor Browser rules"),
    )
    script.add(
        6.2,
        (dim, "    full report      "),
        (text, "tmp/torfast-browser/launch.json"),
    )
    script.add(7.6, (dim, "$ "), (text, "torfast status"))
    script.add(8.2, (purple, "torfast status"))
    script.add(
        8.5,
        (dim, "  managed tor  "),
        (green, "● warm"),
    )
    script.add(8.8, (dim, "  socks port   "), (text, "19450"))
    script.add(
        9.1,
        (dim, "  last launch  "),
        (text, "https://check.torproject.org/"),
    )
    script.add(
        10.6,
        (dim, "  proof: results/torfast-promoted-quality-check-20260707T002336"),
    )
    script.add(
        11.0,
        (dim, "         30/30 quality gates · 15/15 pairwise · conflux live"),
    )
    return script


def render_svg(script: Script) -> str:
    height = HEADER_HEIGHT + script.row_count * LINE_HEIGHT + PADDING_BOTTOM
    css = [
        "text { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas,"
        f" 'Liberation Mono', monospace; font-size: {FONT_SIZE}px; }}".replace(
            "}}", "}"
        ),
        "@media (prefers-reduced-motion: reduce) {"
        " text { animation: none !important; }"
        " text.transient { opacity: 0 !important; } }",
    ]
    body: list[str] = []
    for index, line in enumerate(script.lines):
        name = f"l{index}"
        start_pct = round(line.at / LOOP_SECONDS * 100, 3)
        frames = [
            "0% { opacity: 0; }",
            f"{start_pct}% {{ opacity: 1; }}",
        ]
        if line.until is not None:
            end_pct = round(line.until / LOOP_SECONDS * 100, 3)
            frames.append(f"{end_pct}% {{ opacity: 0; }}")
            frames.append("100% { opacity: 0; }")
        else:
            frames.append("100% { opacity: 1; }")
        # Base opacity keeps the full final screen visible in renderers
        # without CSS animation support; transient lines stay hidden there
        # so they cannot overlap the line that replaces them.
        base_opacity = 0 if line.until is not None else 1
        css.append(
            f".{name} {{ opacity: {base_opacity}; animation: k{name}"
            f" {LOOP_SECONDS}s steps(1, end) infinite; }}"
        )
        css.append(f"@keyframes k{name} {{ {' '.join(frames)} }}")

        y = HEADER_HEIGHT + (line.row + 1) * LINE_HEIGHT
        tspans = "".join(
            f'<tspan fill="{COLORS[color]}">{escape(part)}</tspan>'
            for color, part in line.segments
        )
        classes = name if line.until is None else f"{name} transient"
        body.append(
            f'<text class="{classes}" x="{PADDING_X}" y="{y}" xml:space="preserve">'
            f"{tspans}</text>"
        )

    dots = "".join(
        f'<circle cx="{cx}" cy="18" r="5.5" fill="{COLORS[color]}"/>'
        for cx, color in ((22, "red"), (42, "yellow"), (62, "green"))
    )
    return "\n".join(
        [
            (
                f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" '
                f'height="{height}" viewBox="0 0 {WIDTH} {height}" '
                'role="img" aria-label="torfast terminal demo">'
            ),
            f"<style>{' '.join(css)}</style>",
            (
                f'<rect width="{WIDTH}" height="{height}" rx="10" '
                f'fill="{COLORS["bg"]}" stroke="{COLORS["frame"]}"/>'
            ),
            dots,
            (
                f'<text x="{WIDTH / 2:.0f}" y="22" text-anchor="middle" '
                f'fill="{COLORS["dim"]}">torfast — proven fast, exact Tor '
                "Browser quality</text>"
            ),
            *body,
            "</svg>",
        ]
    )


def main() -> int:
    DEFAULT_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_OUTPUT.write_text(render_svg(demo_script()) + "\n")
    print(f"wrote {DEFAULT_OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
