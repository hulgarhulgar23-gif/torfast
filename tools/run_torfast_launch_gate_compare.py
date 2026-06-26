#!/usr/bin/env python3
"""Compare one-shot browser launch gates without changing Tor quality defaults."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import statistics
import sys
import time

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "tools"))

from run_browser_compare import (
    read_torrc_quality,
    record_proxy_output_tail,
    run_browser_benchmarks,
    start_c_tor,
    stop_process,
    wait_for_line,
)
from torfast.browser_startup_seed import DEFAULT_BROWSER_STARTUP_SEED_ROOT
from torfast.dir_cache_seed import (
    DEFAULT_C_TOR_DIR_CACHE_SEED_ROOT,
    apply_seed_to_data_dir,
)


DEFAULT_BROWSER_BIN = REPO_ROOT / "tmp" / "browser" / "Tor Browser.app" / "Contents" / "MacOS" / "firefox"
DEFAULT_TOR_BIN = REPO_ROOT / "tmp" / "browser" / "Tor Browser.app" / "Contents" / "MacOS" / "Tor" / "tor"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "results"
DEFAULT_TARGETS = [
    "https://check.torproject.org/",
    "https://www.torproject.org/",
]
DEFAULT_GATES = ["tor_boot_100", "tor_boot_95", "tor_boot_90", "tor_boot_75", "socks_ready"]
LAUNCH_GATE_PROFILES = {
    "socks_ready": {
        "ready_text": "Opened Socks listener connection (ready)",
        "extra_wait_seconds": 0.0,
    },
    "tor_boot_90": {
        "ready_text": "Bootstrapped 90% (ap_handshake_done): Handshake finished with a relay to build circuits",
        "extra_wait_seconds": 0.0,
    },
    "tor_boot_90_plus_200ms": {
        "ready_text": "Bootstrapped 90% (ap_handshake_done): Handshake finished with a relay to build circuits",
        "extra_wait_seconds": 0.2,
    },
    "tor_boot_90_plus_400ms": {
        "ready_text": "Bootstrapped 90% (ap_handshake_done): Handshake finished with a relay to build circuits",
        "extra_wait_seconds": 0.4,
    },
    "tor_boot_95": {
        "ready_text": "Bootstrapped 95% (circuit_create): Establishing a Tor circuit",
        "extra_wait_seconds": 0.0,
    },
    "tor_boot_75": {
        "ready_text": "Bootstrapped 75% (enough_dirinfo): Loaded enough directory info to build circuits",
        "extra_wait_seconds": 0.0,
    },
    "tor_boot_100": {
        "ready_text": "Bootstrapped 100%",
        "extra_wait_seconds": 0.0,
    },
}


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.baseline_gate not in args.gates:
        raise SystemExit("--baseline-gate must be included in --gates")

    browser_bin = Path(args.browser_bin).resolve()
    tor_bin = Path(args.tor_bin).resolve()
    seed_root = Path(args.dir_cache_seed_root).resolve()
    browser_startup_seed_root = Path(args.browser_startup_seed_root).resolve()
    output_root = Path(args.output_root).resolve()
    run_id = time.strftime("%Y%m%dT%H%M%S")
    output_dir = output_root / f"torfast-launch-gate-compare-{run_id}"
    output_dir.mkdir(parents=True, exist_ok=True)

    if not browser_bin.exists():
        raise SystemExit(f"browser binary not found: {browser_bin}")
    if not tor_bin.exists():
        raise SystemExit(f"tor binary not found: {tor_bin}")

    results: list[dict[str, object]] = []
    port = args.port_base
    for target in args.targets:
        for cycle in range(1, args.cycles + 1):
            for gate_name in cycle_profile_order(cycle, args.gates):
                result = run_target_gate_once(
                    target=target,
                    gate_name=gate_name,
                    cycle=cycle,
                    port=port,
                    browser_bin=browser_bin,
                    tor_bin=tor_bin,
                    seed_root=seed_root,
                    browser_startup_seed_root=browser_startup_seed_root,
                    timeout=args.timeout,
                    window_size=args.window_size,
                    compact_output=not args.keep_run_dirs,
                    keep_run_dir=args.keep_run_dirs,
                    browser_startup_seed_enabled=args.browser_startup_seed,
                    output_dir=output_dir,
                    run_id=run_id,
                )
                results.append(result)
                port += 1

    payload = {
        "run_id": run_id,
        "created_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "repo_root": str(REPO_ROOT),
        "output_dir": str(output_dir),
        "targets": args.targets,
        "cycles": args.cycles,
        "gates": args.gates,
        "baseline_gate": args.baseline_gate,
        "profiles": summarize_results(
            results,
            targets=args.targets,
            gates=args.gates,
            baseline_gate=args.baseline_gate,
        ),
        "results": compact_results(results, targets=args.targets),
    }
    payload["delta_vs_baseline"] = delta_vs_baseline(
        payload["profiles"],
        targets=args.targets,
        gates=args.gates,
        baseline_gate=args.baseline_gate,
    )

    output_path = output_dir / "summary.json"
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"wrote {output_path}")
    print(
        json.dumps(
            {
                "output_dir": str(output_dir),
                "profiles": payload["profiles"],
                "delta_vs_baseline": payload["delta_vs_baseline"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if payload_ok(results, targets=args.targets) else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--browser-bin", default=str(DEFAULT_BROWSER_BIN))
    parser.add_argument("--tor-bin", default=str(DEFAULT_TOR_BIN))
    parser.add_argument(
        "--targets",
        nargs="+",
        default=list(DEFAULT_TARGETS),
        help="browser targets to measure",
    )
    parser.add_argument(
        "--gates",
        nargs="+",
        default=list(DEFAULT_GATES),
        choices=tuple(LAUNCH_GATE_PROFILES),
        help="launch gates to compare",
    )
    parser.add_argument(
        "--baseline-gate",
        default="tor_boot_100",
        choices=tuple(LAUNCH_GATE_PROFILES),
        help="baseline gate used for delta tables",
    )
    parser.add_argument("--cycles", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--window-size", default="1280,800")
    parser.add_argument("--port-base", type=int, default=20300)
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument(
        "--dir-cache-seed-root",
        default=str(DEFAULT_C_TOR_DIR_CACHE_SEED_ROOT),
    )
    parser.add_argument(
        "--browser-startup-seed-root",
        default=str(DEFAULT_BROWSER_STARTUP_SEED_ROOT),
    )
    parser.add_argument(
        "--browser-startup-seed",
        action="store_true",
        help="opt in to the shared browser startup seed during browser runs",
    )
    parser.add_argument(
        "--keep-run-dirs",
        action="store_true",
        help="keep per-run temp state directories under tmp/",
    )
    return parser


def launch_gate_ready_text(gate_name: str) -> str:
    try:
        profile = LAUNCH_GATE_PROFILES[gate_name]
    except KeyError as exc:
        raise ValueError(f"unsupported launch gate: {gate_name}") from exc
    return str(profile["ready_text"])


def launch_gate_extra_wait_seconds(gate_name: str) -> float:
    try:
        profile = LAUNCH_GATE_PROFILES[gate_name]
    except KeyError as exc:
        raise ValueError(f"unsupported launch gate: {gate_name}") from exc
    return float(profile["extra_wait_seconds"])


def cycle_profile_order(cycle: int, gates: list[str]) -> list[str]:
    if not gates:
        return []
    offset = (cycle - 1) % len(gates)
    return gates[offset:] + gates[:offset]


def target_slug(target: str) -> str:
    return (
        target.replace("https://", "")
        .replace("http://", "")
        .replace("/", "_")
        .replace(":", "_")
    )


def run_target_gate_once(
    *,
    target: str,
    gate_name: str,
    cycle: int,
    port: int,
    browser_bin: Path,
    tor_bin: Path,
    seed_root: Path,
    browser_startup_seed_root: Path,
    timeout: float,
    window_size: str,
    compact_output: bool,
    keep_run_dir: bool,
    browser_startup_seed_enabled: bool,
    output_dir: Path,
    run_id: str,
) -> dict[str, object]:
    run_dir = (
        REPO_ROOT
        / "tmp"
        / f"torfast-launch-gate-{run_id}-{target_slug(target)}-{gate_name}-cycle{cycle}"
    )
    shutil.rmtree(run_dir, ignore_errors=True)
    run_dir.mkdir(parents=True, exist_ok=True)
    data_dir = run_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    torrc = run_dir / "torrc"
    seed_apply = apply_seed_to_data_dir(data_dir, seed_root)

    proc, lines = start_c_tor(
        tor_bin=tor_bin,
        port=port,
        data_dir=data_dir,
        torrc=torrc,
        conflux_client_ux=None,
    )
    started = time.monotonic()
    result: dict[str, object] = {
        "target": target,
        "gate_name": gate_name,
        "cycle": cycle,
        "port": port,
        "run_dir": str(run_dir),
        "seed_apply": seed_apply,
    }
    try:
        gate = wait_for_line(
            proc,
            lines,
            timeout=180.0,
            ready_text=launch_gate_ready_text(gate_name),
            process_name=f"{gate_name} tor",
        )
        extra_wait_seconds = launch_gate_extra_wait_seconds(gate_name)
        if gate.get("ok") and extra_wait_seconds > 0:
            time.sleep(extra_wait_seconds)
            gate = {
                **gate,
                "extra_wait_seconds": extra_wait_seconds,
                "signal_seconds": gate.get("seconds"),
                "seconds": round(float(gate.get("seconds") or 0.0) + extra_wait_seconds, 3),
            }
        result["browser_launch_gate"] = {
            "name": gate_name,
            "ready_text": launch_gate_ready_text(gate_name),
            "extra_wait_seconds": extra_wait_seconds,
            **gate,
        }
        result["benchmarks"] = {}
        if gate.get("ok"):
            result["benchmarks"] = run_browser_benchmarks(
                browser_bin=browser_bin,
                port=port,
                output_dir=run_dir,
                targets=[target],
                runs=1,
                timeout=timeout,
                window_size=window_size,
                compact_output=compact_output,
                browser_startup_seed_root=browser_startup_seed_root,
                no_browser_startup_seed=not browser_startup_seed_enabled,
            )
        result["wall_seconds_to_benchmark_end"] = round(time.monotonic() - started, 3)
        if gate_name == "tor_boot_100":
            result["boot_after_benchmark"] = gate
        else:
            result["boot_after_benchmark"] = wait_for_line(
                proc,
                lines,
                timeout=60.0,
                ready_text=launch_gate_ready_text("tor_boot_100"),
                process_name=f"{gate_name} tor",
            )
        result["torrc"] = read_torrc_quality(torrc)
    finally:
        stop_process(proc)
        record_proxy_output_tail(result, lines, limit=120)
        if not keep_run_dir:
            shutil.rmtree(run_dir, ignore_errors=True)

    copy_path = output_dir / f"{target_slug(target)}-{gate_name}-cycle{cycle}.json"
    copy_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def benchmark_summary_for_result(
    result: dict[str, object], target: str
) -> dict[str, object]:
    benchmarks = result.get("benchmarks")
    if not isinstance(benchmarks, dict):
        return {}
    target_payload = benchmarks.get(target)
    if not isinstance(target_payload, dict):
        return {}
    summary = target_payload.get("summary")
    return summary if isinstance(summary, dict) else {}


def summarize_results(
    results: list[dict[str, object]],
    *,
    targets: list[str],
    gates: list[str],
    baseline_gate: str,
) -> dict[str, object]:
    profiles: dict[str, object] = {}
    for target in targets:
        target_profiles: dict[str, object] = {}
        for gate_name in gates:
            rows = [
                result
                for result in results
                if result.get("target") == target and result.get("gate_name") == gate_name
            ]
            ok_rows = [
                result
                for result in rows
                if benchmark_summary_for_result(result, target).get("ok")
            ]
            target_profiles[gate_name] = {
                "runs": len(rows),
                "ok_runs": len(ok_rows),
                "median_wall_seconds_to_benchmark_end": median_value(
                    [result.get("wall_seconds_to_benchmark_end") for result in ok_rows]
                ),
                "median_elapsed_ms": median_value(
                    [
                        benchmark_summary_for_result(result, target).get("median_elapsed_ms")
                        for result in ok_rows
                    ]
                ),
                "median_load_ms": median_value(
                    [
                        benchmark_summary_for_result(result, target).get("median_load_ms")
                        for result in ok_rows
                    ]
                ),
                "median_browser_launch_gate_seconds": median_value(
                    [
                        (result.get("browser_launch_gate") or {}).get("seconds")
                        for result in rows
                    ]
                ),
                "torrc_isolate_socks_auth_ok_runs": sum(
                    1
                    for result in ok_rows
                    if isinstance((torrc := result.get("torrc")), dict)
                    and torrc.get("isolate_socks_auth") is True
                ),
                "boot_after_benchmark_ok_runs": sum(
                    1
                    for result in ok_rows
                    if isinstance((boot := result.get("boot_after_benchmark")), dict)
                    and boot.get("ok") is True
                ),
            }
        profiles[target] = target_profiles
    return profiles


def delta_vs_baseline(
    profiles: dict[str, object],
    *,
    targets: list[str],
    gates: list[str],
    baseline_gate: str,
) -> dict[str, object]:
    deltas: dict[str, object] = {}
    for target in targets:
        target_profiles = profiles.get(target)
        if not isinstance(target_profiles, dict):
            continue
        baseline = target_profiles.get(baseline_gate)
        if not isinstance(baseline, dict):
            continue
        target_deltas: dict[str, object] = {}
        for gate_name in gates:
            candidate = target_profiles.get(gate_name)
            if not isinstance(candidate, dict):
                continue
            target_deltas[gate_name] = {
                "wall_seconds_to_benchmark_end": subtract_metric(
                    candidate.get("median_wall_seconds_to_benchmark_end"),
                    baseline.get("median_wall_seconds_to_benchmark_end"),
                ),
                "elapsed_ms": subtract_metric(
                    candidate.get("median_elapsed_ms"),
                    baseline.get("median_elapsed_ms"),
                ),
                "load_ms": subtract_metric(
                    candidate.get("median_load_ms"),
                    baseline.get("median_load_ms"),
                ),
            }
        deltas[target] = target_deltas
    return deltas


def compact_results(
    results: list[dict[str, object]],
    *,
    targets: list[str],
) -> list[dict[str, object]]:
    compact: list[dict[str, object]] = []
    for result in results:
        target = str(result.get("target"))
        if target not in targets:
            continue
        bench = benchmark_summary_for_result(result, target)
        compact.append(
            {
                "target": target,
                "gate_name": result.get("gate_name"),
                "cycle": result.get("cycle"),
                "port": result.get("port"),
                "wall_seconds_to_benchmark_end": result.get(
                    "wall_seconds_to_benchmark_end"
                ),
                "browser_launch_gate_seconds": (
                    (result.get("browser_launch_gate") or {}).get("seconds")
                ),
                "boot_after_benchmark_ok": (
                    (result.get("boot_after_benchmark") or {}).get("ok")
                ),
                "elapsed_ms": bench.get("median_elapsed_ms"),
                "load_ms": bench.get("median_load_ms"),
                "ok": bench.get("ok"),
            }
        )
    return compact


def median_value(values: list[object]) -> float | None:
    numeric = [float(value) for value in values if isinstance(value, (int, float))]
    if not numeric:
        return None
    return round(statistics.median(numeric), 3)


def subtract_metric(candidate: object, baseline: object) -> float | None:
    if not isinstance(candidate, (int, float)) or not isinstance(baseline, (int, float)):
        return None
    return round(float(candidate) - float(baseline), 3)


def payload_ok(results: list[dict[str, object]], *, targets: list[str]) -> bool:
    for result in results:
        target = result.get("target")
        if target not in targets:
            return False
        if not benchmark_summary_for_result(result, str(target)).get("ok"):
            return False
        torrc = result.get("torrc")
        if not isinstance(torrc, dict) or torrc.get("isolate_socks_auth") is not True:
            return False
        boot = result.get("boot_after_benchmark")
        if not isinstance(boot, dict) or boot.get("ok") is not True:
            return False
    return True


if __name__ == "__main__":
    raise SystemExit(main())
