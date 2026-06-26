#!/usr/bin/env python3
"""Start the built Arti proxy, benchmark it, then stop it."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time

from bench_http import fetch, summarize


URLS = [
    "https://check.torproject.org/",
    "https://www.torproject.org/",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--arti-bin", default="upstream/arti/target/debug/arti")
    parser.add_argument("--port", type=int, default=19060)
    parser.add_argument("--runs", type=int, default=3)
    args = parser.parse_args()

    arti_bin = Path(args.arti_bin).resolve()
    if not arti_bin.exists():
        print(f"arti binary not found: {arti_bin}", file=sys.stderr)
        return 2

    run_id = time.strftime("%Y%m%dT%H%M%S")
    output_dir = Path("results") / f"arti-baseline-{run_id}"
    output_dir.mkdir(parents=True, exist_ok=True)

    proc = start_arti(arti_bin=arti_bin, port=args.port, output_dir=output_dir)
    lines: queue.Queue[str] = queue.Queue()
    reader = threading.Thread(target=read_lines, args=(proc, lines), daemon=True)
    reader.start()

    try:
        boot = wait_for_ready(proc, lines, timeout=180.0)
        payload = {
            "run_id": run_id,
            "arti_bin": str(arti_bin),
            "port": args.port,
            "boot": boot,
            "benchmarks": {},
        }

        if boot["ok"]:
            socks = ("127.0.0.1", args.port)
            for url in URLS:
                runs = [
                    fetch(url, socks=socks, timeout=60.0, max_bytes=2_000_000)
                    for _ in range(args.runs)
                ]
                payload["benchmarks"][url] = {
                    "runs": [asdict(run) for run in runs],
                    "summary": summarize(runs),
                }

        output_path = output_dir / "arti-baseline.json"
        output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        print(f"wrote {output_path}")
        print(json.dumps(short_summary(payload), indent=2, sort_keys=True))
        return 0 if boot["ok"] else 1
    finally:
        stop_process(proc)


def start_arti(*, arti_bin: Path, port: int, output_dir: Path) -> subprocess.Popen[str]:
    cache_dir = (output_dir / "cache").resolve()
    state_dir = (output_dir / "state").resolve()
    cache_dir.mkdir(parents=True, exist_ok=True)
    state_dir.mkdir(parents=True, exist_ok=True)

    return subprocess.Popen(
        [
            str(arti_bin),
            "proxy",
            "--disable-fs-permission-checks",
            "-l",
            "info",
            "-p",
            str(port),
            "-o",
            f'storage.cache_dir="{cache_dir}"',
            "-o",
            f'storage.state_dir="{state_dir}"',
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )


def read_lines(proc: subprocess.Popen[str], lines: queue.Queue[str]) -> None:
    assert proc.stdout is not None
    for line in proc.stdout:
        lines.put(line.rstrip())


def wait_for_ready(
    proc: subprocess.Popen[str], lines: queue.Queue[str], *, timeout: float
) -> dict[str, object]:
    started = time.monotonic()
    seen: list[str] = []
    while time.monotonic() - started < timeout:
        if proc.poll() is not None:
            return {
                "ok": False,
                "error": f"arti exited with code {proc.returncode}",
                "lines": seen[-80:],
            }
        try:
            line = lines.get(timeout=0.25)
        except queue.Empty:
            continue
        seen.append(line)
        if "proxy now functional" in line:
            return {"ok": True, "seconds": round(time.monotonic() - started, 3), "lines": seen[-80:]}
    return {"ok": False, "error": "bootstrap timeout", "lines": seen[-80:]}


def stop_process(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=10.0)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=10.0)


def short_summary(payload: dict[str, object]) -> dict[str, object]:
    return {
        "boot": payload["boot"],
        "benchmarks": {
            url: data["summary"] for url, data in payload["benchmarks"].items()
        },
    }


if __name__ == "__main__":
    raise SystemExit(main())
