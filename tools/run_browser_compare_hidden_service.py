#!/usr/bin/env python3
"""Run the current hidden-service browser-compare matrix."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys


DEFAULT_TARGETS = [
    "https://securedrop.org/",
    # Current Tor Project onion download page from Onion-Location proof.
    "http://2gzyxa5ihm7nsggfxnu52rck2vv4rvmdlkiu3zzui5du4xyclen53wid.onion/download/index.html",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--post-boot-wait", type=float, default=0.0)
    parser.add_argument("--window-size", default="1000,1000")
    parser.add_argument("--warm-cache", action="store_true")
    parser.add_argument("--share-arti-warm-cache-seed", action="store_true")
    parser.add_argument("--browser-startup-seed", action="store_true")
    parser.add_argument(
        "--interleaved-target-order",
        choices=("fixed", "rotating"),
        default="fixed",
    )
    parser.add_argument("--targets", nargs="*", default=list(DEFAULT_TARGETS))
    args = parser.parse_args()

    runner = Path(__file__).with_name("run_browser_compare.py")
    cmd = [
        sys.executable,
        str(runner),
        "--skip-bundled-tor",
        "--schedule",
        "interleaved",
        "--interleaved-target-order",
        args.interleaved_target_order,
        "--targets",
        *args.targets,
        "--runs",
        str(args.runs),
        "--timeout",
        str(args.timeout),
        "--post-boot-wait",
        str(args.post_boot_wait),
        "--window-size",
        args.window_size,
        "--arti-exit-same-isolation-target",
        "2",
        "--arti-exit-same-isolation-prewarm-first-stream",
        "--arti-exit-select-health-aware",
        "--arti-exit-select-prefer-cold-same-isolation",
        "--extra-arti-hs-rend-prebuild-before-desc",
    ]
    if args.warm_cache:
        cmd.append("--warm-cache")
    if args.share_arti_warm_cache_seed:
        cmd.append("--share-arti-warm-cache-seed")
    if args.browser_startup_seed:
        cmd.append("--browser-startup-seed")
    return subprocess.run(cmd, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
