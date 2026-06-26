#!/usr/bin/env python3
"""Compare direct, C Tor, and Arti release in one time window."""

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
    parser.add_argument("--tor-bin", default="upstream/tor/src/app/tor")
    parser.add_argument("--arti-bin", default="upstream/arti/target/release/arti")
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--tor-port", type=int, default=19070)
    parser.add_argument("--arti-port", type=int, default=19071)
    args = parser.parse_args()

    tor_bin = Path(args.tor_bin).resolve()
    arti_bin = Path(args.arti_bin).resolve()
    if not tor_bin.exists():
        print(f"tor binary not found: {tor_bin}", file=sys.stderr)
        return 2
    if not arti_bin.exists():
        print(f"arti binary not found: {arti_bin}", file=sys.stderr)
        return 2

    run_id = time.strftime("%Y%m%dT%H%M%S")
    output_dir = Path("results") / f"proxy-compare-{run_id}"
    output_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "run_id": run_id,
        "runs_per_target": args.runs,
        "tor_bin": str(tor_bin),
        "arti_bin": str(arti_bin),
        "targets": URLS,
        "profiles": {},
    }

    payload["profiles"]["direct_start"] = run_direct(runs=args.runs)
    payload["profiles"]["c_tor_stock"] = run_c_tor(
        tor_bin=tor_bin,
        port=args.tor_port,
        output_dir=output_dir / "c_tor_stock",
        runs=args.runs,
    )
    payload["profiles"]["arti_release"] = run_arti(
        arti_bin=arti_bin,
        port=args.arti_port,
        output_dir=output_dir / "arti_release",
        runs=args.runs,
    )
    payload["profiles"]["direct_end"] = run_direct(runs=args.runs)

    output_path = output_dir / "compare.json"
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"wrote {output_path}")
    print(json.dumps(short_summary(payload), indent=2, sort_keys=True))
    return 0


def run_direct(*, runs: int) -> dict[str, object]:
    return {"benchmarks": run_benchmarks(socks=None, runs=runs)}


def run_c_tor(
    *, tor_bin: Path, port: int, output_dir: Path, runs: int
) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    data_dir = output_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    torrc = output_dir / "torrc"
    torrc.write_text(
        "\n".join(
            [
                f"SocksPort 127.0.0.1:{port}",
                f"DataDirectory {data_dir.resolve()}",
                "ClientOnly 1",
                "AvoidDiskWrites 1",
                "SafeLogging 1",
                "Log notice stdout",
                "ConfluxEnabled auto",
            ]
        )
        + "\n"
    )
    proc = subprocess.Popen(
        [str(tor_bin), "-f", str(torrc)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    lines: queue.Queue[str] = queue.Queue()
    reader = threading.Thread(target=read_lines, args=(proc, lines), daemon=True)
    reader.start()
    try:
        boot = wait_for_line(
            proc,
            lines,
            timeout=180.0,
            ready_text="Bootstrapped 100%",
            process_name="tor",
        )
        result: dict[str, object] = {"boot": boot, "benchmarks": {}}
        if boot["ok"]:
            result["benchmarks"] = run_benchmarks(socks=("127.0.0.1", port), runs=runs)
        return result
    finally:
        stop_process(proc)


def run_arti(
    *, arti_bin: Path, port: int, output_dir: Path, runs: int
) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = (output_dir / "cache").resolve()
    state_dir = (output_dir / "state").resolve()
    cache_dir.mkdir(parents=True, exist_ok=True)
    state_dir.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(
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
    lines: queue.Queue[str] = queue.Queue()
    reader = threading.Thread(target=read_lines, args=(proc, lines), daemon=True)
    reader.start()
    try:
        boot = wait_for_line(
            proc,
            lines,
            timeout=180.0,
            ready_text="proxy now functional",
            process_name="arti",
        )
        result: dict[str, object] = {"boot": boot, "benchmarks": {}}
        if boot["ok"]:
            result["benchmarks"] = run_benchmarks(socks=("127.0.0.1", port), runs=runs)
        return result
    finally:
        stop_process(proc)


def run_benchmarks(*, socks: tuple[str, int] | None, runs: int) -> dict[str, object]:
    benchmarks: dict[str, object] = {}
    for url in URLS:
        fetch_runs = [
            fetch(url, socks=socks, timeout=60.0, max_bytes=2_000_000)
            for _ in range(runs)
        ]
        benchmarks[url] = {
            "runs": [asdict(run) for run in fetch_runs],
            "summary": summarize(fetch_runs),
        }
    return benchmarks


def read_lines(proc: subprocess.Popen[str], lines: queue.Queue[str]) -> None:
    assert proc.stdout is not None
    for line in proc.stdout:
        lines.put(line.rstrip())


def wait_for_line(
    proc: subprocess.Popen[str],
    lines: queue.Queue[str],
    *,
    timeout: float,
    ready_text: str,
    process_name: str,
) -> dict[str, object]:
    started = time.monotonic()
    seen: list[str] = []
    while time.monotonic() - started < timeout:
        if proc.poll() is not None:
            return {
                "ok": False,
                "error": f"{process_name} exited with code {proc.returncode}",
                "lines": seen[-80:],
            }
        try:
            line = lines.get(timeout=0.25)
        except queue.Empty:
            continue
        seen.append(line)
        if ready_text in line:
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
    profiles = payload["profiles"]
    assert isinstance(profiles, dict)
    return {
        name: {
            "boot": data.get("boot", {}),
            "benchmarks": {
                url: bench["summary"]
                for url, bench in data.get("benchmarks", {}).items()
            },
        }
        for name, data in profiles.items()
    }


if __name__ == "__main__":
    raise SystemExit(main())
