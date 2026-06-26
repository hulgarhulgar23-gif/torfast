#!/usr/bin/env python3
"""Compare cold and warm directory-cache behavior for C Tor and Arti."""

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
    parser.add_argument("--runs", type=int, default=2)
    parser.add_argument("--tor-port", type=int, default=19120)
    parser.add_argument("--arti-port", type=int, default=19121)
    parser.add_argument("--targets", nargs="*", default=URLS)
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
    output_dir = Path("results") / f"cache-diagnostic-{run_id}"
    output_dir.mkdir(parents=True, exist_ok=True)

    payload: dict[str, object] = {
        "run_id": run_id,
        "runs_per_target": args.runs,
        "targets": args.targets,
        "profiles": {},
    }

    payload["profiles"]["c_tor"] = run_cold_warm_c_tor(
        tor_bin=tor_bin,
        port=args.tor_port,
        output_dir=output_dir / "c_tor",
        targets=args.targets,
        runs=args.runs,
    )
    payload["profiles"]["arti_release"] = run_cold_warm_arti(
        arti_bin=arti_bin,
        port=args.arti_port,
        output_dir=output_dir / "arti_release",
        targets=args.targets,
        runs=args.runs,
    )

    output_path = output_dir / "cache-diagnostic.json"
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"wrote {output_path}")
    print(json.dumps(short_summary(payload), indent=2, sort_keys=True))
    return 0 if payload_ok(payload) else 1


def run_cold_warm_c_tor(
    *, tor_bin: Path, port: int, output_dir: Path, targets: list[str], runs: int
) -> dict[str, object]:
    data_dir = output_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return {
        "cold": run_c_tor_once(
            tor_bin=tor_bin,
            port=port,
            data_dir=data_dir,
            output_dir=output_dir / "cold",
            targets=targets,
            runs=runs,
        ),
        "warm": run_c_tor_once(
            tor_bin=tor_bin,
            port=port,
            data_dir=data_dir,
            output_dir=output_dir / "warm",
            targets=targets,
            runs=runs,
        ),
    }


def run_cold_warm_arti(
    *, arti_bin: Path, port: int, output_dir: Path, targets: list[str], runs: int
) -> dict[str, object]:
    cache_dir = (output_dir / "cache").resolve()
    state_dir = (output_dir / "state").resolve()
    cache_dir.mkdir(parents=True, exist_ok=True)
    state_dir.mkdir(parents=True, exist_ok=True)
    return {
        "cold": run_arti_once(
            arti_bin=arti_bin,
            port=port,
            cache_dir=cache_dir,
            state_dir=state_dir,
            output_dir=output_dir / "cold",
            targets=targets,
            runs=runs,
        ),
        "warm": run_arti_once(
            arti_bin=arti_bin,
            port=port,
            cache_dir=cache_dir,
            state_dir=state_dir,
            output_dir=output_dir / "warm",
            targets=targets,
            runs=runs,
        ),
    }


def run_c_tor_once(
    *,
    tor_bin: Path,
    port: int,
    data_dir: Path,
    output_dir: Path,
    targets: list[str],
    runs: int,
) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
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
    threading.Thread(target=read_lines, args=(proc, lines), daemon=True).start()
    try:
        boot = wait_for_line(
            proc,
            lines,
            timeout=180.0,
            ready_text="Bootstrapped 100%",
            process_name="tor",
        )
        return result_after_boot(boot, ("127.0.0.1", port), targets, runs)
    finally:
        stop_process(proc)


def run_arti_once(
    *,
    arti_bin: Path,
    port: int,
    cache_dir: Path,
    state_dir: Path,
    output_dir: Path,
    targets: list[str],
    runs: int,
) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
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
    threading.Thread(target=read_lines, args=(proc, lines), daemon=True).start()
    try:
        boot = wait_for_line(
            proc,
            lines,
            timeout=180.0,
            ready_text="proxy now functional",
            process_name="arti",
        )
        return result_after_boot(boot, ("127.0.0.1", port), targets, runs)
    finally:
        stop_process(proc)


def result_after_boot(
    boot: dict[str, object],
    socks: tuple[str, int],
    targets: list[str],
    runs: int,
) -> dict[str, object]:
    result: dict[str, object] = {
        "boot": with_log_counts(boot),
        "benchmarks": {},
    }
    if boot["ok"]:
        result["benchmarks"] = run_benchmarks(socks=socks, targets=targets, runs=runs)
    return result


def run_benchmarks(
    *, socks: tuple[str, int], targets: list[str], runs: int
) -> dict[str, object]:
    benchmarks: dict[str, object] = {}
    for url in targets:
        fetch_runs = [
            fetch(url, socks=socks, timeout=60.0, max_bytes=2_000_000)
            for _ in range(runs)
        ]
        benchmarks[url] = {
            "runs": [asdict(run) for run in fetch_runs],
            "summary": summarize(fetch_runs),
        }
    return benchmarks


def with_log_counts(boot: dict[str, object]) -> dict[str, object]:
    lines = boot.get("lines", [])
    if not isinstance(lines, list):
        return boot
    text = "\n".join(str(line) for line in lines).lower()
    enriched = dict(boot)
    enriched["directory_failure_lines"] = sum(
        1
        for line in lines
        if "directory failure" in str(line).lower()
        or "directory timed out" in str(line).lower()
        or "notdirectory" in str(line).lower()
    )
    enriched["timeout_mentions"] = text.count("timeout")
    return enriched


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
            return {
                "ok": True,
                "seconds": round(time.monotonic() - started, 3),
                "lines": seen[-80:],
            }
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
        profile: {
            phase: {
                "boot": data.get("boot", {}),
                "benchmarks": {
                    url: bench.get("summary", {})
                    for url, bench in data.get("benchmarks", {}).items()
                },
            }
            for phase, data in phases.items()
        }
        for profile, phases in payload.get("profiles", {}).items()
    }


def payload_ok(payload: dict[str, object]) -> bool:
    for phases in payload.get("profiles", {}).values():
        for data in phases.values():
            if not data.get("boot", {}).get("ok"):
                return False
            for bench in data.get("benchmarks", {}).values():
                if not bench.get("summary", {}).get("ok"):
                    return False
    return True


if __name__ == "__main__":
    raise SystemExit(main())
