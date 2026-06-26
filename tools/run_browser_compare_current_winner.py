#!/usr/bin/env python3
"""Run the current fastest clean browser-compare recipe."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys


DEFAULT_TARGETS = [
    "https://check.torproject.org/",
    "https://www.torproject.org/",
    "https://www.torproject.org/download/",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--window-size", default="1000,1000")
    args = parser.parse_args()

    runner = Path(__file__).with_name("run_browser_compare.py")
    cmd = [
        sys.executable,
        str(runner),
        "--skip-bundled-tor",
        "--schedule",
        "interleaved",
        "--targets",
        *DEFAULT_TARGETS,
        "--runs",
        str(args.runs),
        "--window-size",
        args.window_size,
        "--arti-exit-same-isolation-target",
        "2",
        "--arti-exit-same-isolation-prewarm-first-stream",
        "--arti-exit-select-health-aware",
        "--arti-exit-select-prefer-cold-same-isolation",
    ]
    return subprocess.run(cmd, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
