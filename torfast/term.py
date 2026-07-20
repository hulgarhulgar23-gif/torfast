"""Terminal presentation helpers for the torfast CLI.

Human output is a TTY-only layer: every command keeps its JSON output
byte-identical when stdout is not a terminal (or when `--json` is passed),
so scripts and benchmark harnesses never see styled text. Stdlib only.
"""

from __future__ import annotations

import io
import itertools
import os
import sys
import threading
import time


RESET = "\x1b[0m"
CODES = {
    "bold": "\x1b[1m",
    "dim": "\x1b[2m",
    "red": "\x1b[31m",
    "green": "\x1b[32m",
    "yellow": "\x1b[33m",
    "magenta": "\x1b[35m",
    "cyan": "\x1b[36m",
}

SYMBOL_OK = "✓"
SYMBOL_FAIL = "✗"
SYMBOL_ON = "●"
SYMBOL_OFF = "○"
SYMBOL_STEP = "▸"
SPINNER_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

WORDMARK = "\n".join(
    [
        "▀█▀ █▀█ █▀█ █▀▀ ▄▀█ █▀ ▀█▀",
        " █  █▄█ █▀▄ █▀  █▀█ ▄█  █ ",
    ]
)


def color_enabled(stream=None) -> bool:
    if os.environ.get("NO_COLOR") is not None:
        return False
    if os.environ.get("TERM") == "dumb":
        return False
    stream = stream if stream is not None else sys.stdout
    isatty = getattr(stream, "isatty", None)
    return bool(isatty and isatty())


def human_output_enabled(args=None, stream=None) -> bool:
    """Human rendering is opt-out via --json and only ever on a TTY."""
    if args is not None and getattr(args, "json", False):
        return False
    stream = stream if stream is not None else sys.stdout
    isatty = getattr(stream, "isatty", None)
    return bool(isatty and isatty())


def style(text: str, *names: str, enabled: bool = True) -> str:
    if not enabled or not names:
        return text
    prefix = "".join(CODES[name] for name in names)
    return f"{prefix}{text}{RESET}"


def status_symbol(ok: object, *, enabled: bool = True) -> str:
    if ok is True:
        return style(SYMBOL_OK, "green", enabled=enabled)
    return style(SYMBOL_FAIL, "red", enabled=enabled)


def presence_symbol(on: object, *, enabled: bool = True) -> str:
    if on is True:
        return style(SYMBOL_ON, "green", enabled=enabled)
    return style(SYMBOL_OFF, "dim", enabled=enabled)


def format_seconds(value: object) -> str:
    if not isinstance(value, (int, float)):
        return "-"
    return f"{value:.1f}s"


def render_panel(
    title: str,
    rows: list[tuple[str, str]],
    *,
    enabled: bool = True,
) -> str:
    lines = [style(title, "bold", enabled=enabled)]
    width = max((len(label) for label, _ in rows), default=0)
    for label, value in rows:
        padded = label.ljust(width)
        lines.append(f"  {style(padded, 'dim', enabled=enabled)}  {value}")
    return "\n".join(lines)


def render_check_line(
    ok: object,
    label: str,
    detail: str = "",
    *,
    enabled: bool = True,
) -> str:
    line = f"  {status_symbol(ok, enabled=enabled)} {label}"
    if detail:
        line += f"  {style(detail, 'dim', enabled=enabled)}"
    return line


def render_wordmark(*, enabled: bool = True) -> str:
    return style(WORDMARK, "magenta", "bold", enabled=enabled)


class Spinner:
    """Single-line progress spinner on stderr; silent when stderr is not a TTY.

    The spinner is presentation only: it never touches stdout, so captured
    command output stays clean.
    """

    def __init__(self, label: str, *, stream=None, interval: float = 0.1):
        self.label = label
        self.stream = stream if stream is not None else sys.stderr
        self.interval = interval
        self._stop = threading.Event()
        self._worker: threading.Thread | None = None
        self._started_at = 0.0

    @property
    def enabled(self) -> bool:
        isatty = getattr(self.stream, "isatty", None)
        return bool(isatty and isatty()) and os.environ.get("TERM") != "dumb"

    def __enter__(self) -> "Spinner":
        self._started_at = time.monotonic()
        if self.enabled:
            self._worker = threading.Thread(target=self._spin, daemon=True)
            self._worker.start()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self._stop.set()
        if self._worker is not None:
            self._worker.join(timeout=2.0)
        if self.enabled:
            self.stream.write("\r\x1b[2K")
            self.stream.flush()

    @property
    def elapsed_seconds(self) -> float:
        return time.monotonic() - self._started_at

    def _spin(self) -> None:
        colored = color_enabled(self.stream)
        for frame in itertools.cycle(SPINNER_FRAMES):
            if self._stop.wait(self.interval):
                return
            elapsed = format_seconds(self.elapsed_seconds)
            line = (
                f"\r\x1b[2K{style(frame, 'cyan', enabled=colored)} "
                f"{self.label} {style(elapsed, 'dim', enabled=colored)}"
            )
            self.stream.write(line)
            self.stream.flush()


class CapturedStdout:
    """Redirect sys.stdout to a buffer without contextlib dependency games."""

    def __init__(self):
        self.buffer = io.StringIO()
        self._saved = None

    def __enter__(self) -> io.StringIO:
        self._saved = sys.stdout
        sys.stdout = self.buffer
        return self.buffer

    def __exit__(self, *exc_info: object) -> None:
        sys.stdout = self._saved
