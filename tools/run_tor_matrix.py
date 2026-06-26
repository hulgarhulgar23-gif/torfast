#!/usr/bin/env python3
"""Run C Tor speed profiles through the same benchmark.

This does not weaken Tor. It only changes official client options that affect
how supported Conflux UX is requested.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import threading
import time

from bench_http import fetch, summarize


URLS = [
    "https://check.torproject.org/",
    "https://www.torproject.org/",
]

PROFILES = [
    {"name": "stock_auto", "port": 19050, "conflux_ux": None},
    {"name": "latency_auto", "port": 19051, "conflux_ux": "latency"},
    {"name": "throughput_auto", "port": 19052, "conflux_ux": "throughput"},
    {"name": "throughput_lowmem_auto", "port": 19053, "conflux_ux": "throughput_lowmem"},
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--tor-bin",
        default=None,
        help="Tor binary to run. Defaults to PATH tor, then upstream/tor/src/app/tor.",
    )
    parser.add_argument("--runs", type=int, default=3)
    args = parser.parse_args()

    tor_bin = find_tor(args.tor_bin)
    if not tor_bin:
        print("tor not found. Build C Tor or pass --tor-bin.", file=sys.stderr)
        return 2

    run_id = time.strftime("%Y%m%dT%H%M%S")
    output_dir = Path("results") / f"tor-matrix-{run_id}"
    output_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "run_id": run_id,
        "tor_bin": tor_bin,
        "profiles": {},
    }

    for profile in PROFILES:
        payload["profiles"][profile["name"]] = run_profile(
            tor_bin=tor_bin,
            profile=profile,
            output_dir=output_dir,
            runs=args.runs,
        )

    output_path = output_dir / "matrix.json"
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"wrote {output_path}")
    print(json.dumps(short_summary(payload), indent=2, sort_keys=True))
    return 0


def find_tor(value: str | None) -> str | None:
    if value:
        path = Path(value).resolve()
        return str(path) if path.exists() else None
    path_tor = shutil.which("tor")
    if path_tor:
        return path_tor
    local_tor = Path("upstream/tor/src/app/tor").resolve()
    if local_tor.exists():
        return str(local_tor)
    return None


def run_profile(
    *, tor_bin: str, profile: dict[str, object], output_dir: Path, runs: int
) -> dict[str, object]:
    name = str(profile["name"])
    port = int(profile["port"])
    data_dir = output_dir / name / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    torrc = output_dir / name / "torrc"
    torrc.write_text(render_torrc(profile, data_dir=data_dir) + "\n")

    proc = subprocess.Popen(
        [tor_bin, "-f", str(torrc)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    lines: queue.Queue[str] = queue.Queue()
    reader = threading.Thread(target=read_lines, args=(proc, lines), daemon=True)
    reader.start()

    try:
        boot = wait_for_bootstrap(proc, lines, timeout=180.0)
        result: dict[str, object] = {"boot": boot, "benchmarks": {}}
        if boot["ok"]:
            socks = ("127.0.0.1", port)
            for url in URLS:
                fetch_runs = [
                    fetch(url, socks=socks, timeout=60.0, max_bytes=2_000_000)
                    for _ in range(runs)
                ]
                result["benchmarks"][url] = {
                    "runs": [asdict(run) for run in fetch_runs],
                    "summary": summarize(fetch_runs),
                }
        return result
    finally:
        stop_process(proc)


def render_torrc(profile: dict[str, object], *, data_dir: Path) -> str:
    lines = [
        f"SocksPort 127.0.0.1:{profile['port']}",
        f"DataDirectory {data_dir}",
        "ClientOnly 1",
        "AvoidDiskWrites 1",
        "SafeLogging 1",
        "Log notice stdout",
        "ConfluxEnabled auto",
    ]
    if profile["conflux_ux"]:
        lines.append(f"ConfluxClientUX {profile['conflux_ux']}")
    return "\n".join(lines)


def read_lines(proc: subprocess.Popen[str], lines: queue.Queue[str]) -> None:
    assert proc.stdout is not None
    for line in proc.stdout:
        lines.put(line.rstrip())


def wait_for_bootstrap(
    proc: subprocess.Popen[str], lines: queue.Queue[str], *, timeout: float
) -> dict[str, object]:
    started = time.monotonic()
    seen: list[str] = []
    while time.monotonic() - started < timeout:
        if proc.poll() is not None:
            return {
                "ok": False,
                "error": f"tor exited with code {proc.returncode}",
                "lines": seen[-50:],
            }
        try:
            line = lines.get(timeout=0.25)
        except queue.Empty:
            continue
        seen.append(line)
        if "Bootstrapped 100%" in line:
            return {"ok": True, "seconds": round(time.monotonic() - started, 3), "lines": seen[-50:]}
    return {"ok": False, "error": "bootstrap timeout", "lines": seen[-50:]}


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
    out: dict[str, object] = {}
    profiles = payload["profiles"]
    assert isinstance(profiles, dict)
    for name, result in profiles.items():
        boot = result["boot"]
        out[name] = {
            "boot_ok": boot["ok"],
            "benchmarks": {
                url: data["summary"]
                for url, data in result.get("benchmarks", {}).items()
            },
        }
    return out


if __name__ == "__main__":
    raise SystemExit(main())
