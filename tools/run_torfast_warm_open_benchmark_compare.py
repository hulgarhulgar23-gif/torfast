#!/usr/bin/env python3
"""Benchmark real page loads after torfast warm without changing Tor quality defaults."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import random
import shutil
import sys
import time


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_ROOT = REPO_ROOT / "tools"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from launch_torfast_browser import wait_for_existing_service_ready_in_log
from run_browser_compare import read_torrc_quality, run_browser_benchmarks
from run_torfast_warm_open_compare import (
    DEFAULT_BROWSER_BIN,
    DEFAULT_OUTPUT_ROOT,
    DEFAULT_PROFILES,
    DEFAULT_TOR_BIN,
    PROFILE_CHOICES,
    build_stop_command,
    build_torfast_command,
    compact_launch,
    cycle_profile_order,
    median_value,
    parse_json_text,
    read_json_file,
    run_command,
    subtract_metric,
    target_slug,
    warm_ready_gate,
    warm_ready_seconds,
)


DEFAULT_TARGETS = [
    "https://check.torproject.org/",
]


def parse_extra_wait_values(values: list[str]) -> list[float]:
    parsed: list[float] = []
    seen: set[float] = set()
    for raw in values:
        try:
            seconds = float(raw)
        except ValueError:
            raise SystemExit(
                f"--extra-post-warm-wait-seconds must be numeric, got: {raw}"
            ) from None
        if seconds < 0:
            raise SystemExit("--extra-post-warm-wait-seconds must be non-negative")
        rounded = round(seconds, 3)
        if rounded in seen:
            continue
        seen.add(rounded)
        parsed.append(rounded)
    return parsed


def waited_profile_name(base_profile_name: str, seconds: float) -> str:
    ms = round(seconds * 1000)
    return f"{base_profile_name}_wait_{ms}ms"


def percentile_value(values: list[object], percentile: float) -> float | None:
    numeric = sorted(float(value) for value in values if isinstance(value, (int, float)))
    if not numeric:
        return None
    index = max(
        0,
        min(
            len(numeric) - 1,
            int(round((percentile / 100.0) * (len(numeric) - 1))),
        ),
    )
    return round(numeric[index], 3)


def max_value(values: list[object]) -> float | None:
    numeric = [float(value) for value in values if isinstance(value, (int, float))]
    if not numeric:
        return None
    return round(max(numeric), 3)


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    extra_post_warm_wait_seconds = parse_extra_wait_values(
        args.extra_post_warm_wait_seconds
    )
    profile_specs = build_profile_specs(
        profile_names=args.profiles,
        extra_post_warm_wait_seconds=extra_post_warm_wait_seconds,
    )
    profile_names = [str(spec["name"]) for spec in profile_specs]
    if args.baseline_profile not in profile_names:
        raise SystemExit("--baseline-profile must be included in the expanded profile set")

    browser_bin = Path(args.browser_bin).resolve()
    tor_bin = Path(args.tor_bin).resolve()
    browser_startup_seed_root = Path(args.browser_startup_seed_root).resolve()
    output_root = Path(args.output_root).resolve()
    run_id = time.strftime("%Y%m%dT%H%M%S")
    output_dir = output_root / f"torfast-warm-open-benchmark-compare-{run_id}"
    output_dir.mkdir(parents=True, exist_ok=True)

    if not browser_bin.exists():
        raise SystemExit(f"browser binary not found: {browser_bin}")
    if not tor_bin.exists():
        raise SystemExit(f"tor binary not found: {tor_bin}")

    results: list[dict[str, object]] = []
    cycle_profile_orders: list[dict[str, object]] = []
    port = args.port_base
    for target in args.targets:
        for cycle in range(1, args.cycles + 1):
            ordered_profile_specs = cycle_profile_order(
                cycle,
                profile_specs,
                profile_order=args.profile_order,
                random_seed=args.random_seed,
            )
            cycle_profile_orders.append(
                {
                    "target": target,
                    "cycle": cycle,
                    "profile_names": [
                        str(profile_spec["name"]) for profile_spec in ordered_profile_specs
                    ],
                }
            )
            for profile_spec in ordered_profile_specs:
                result = run_target_profile_once(
                    target=target,
                    profile_name=str(profile_spec["name"]),
                    base_profile_name=str(profile_spec["base_profile_name"]),
                    extra_post_warm_wait_seconds=float(
                        profile_spec["extra_post_warm_wait_seconds"]
                    ),
                    cycle=cycle,
                    port=port,
                    browser_bin=browser_bin,
                    tor_bin=tor_bin,
                    timeout=args.timeout,
                    window_size=args.window_size,
                    compact_output=not args.keep_run_dirs,
                    keep_run_dir=args.keep_run_dirs,
                    browser_startup_seed_root=browser_startup_seed_root,
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
        "profiles": profile_names,
        "profile_specs": profile_specs,
        "profile_order": args.profile_order,
        "profile_order_seed": (
            args.random_seed if args.profile_order == "randomized" else None
        ),
        "cycle_profile_orders": cycle_profile_orders,
        "baseline_profile": args.baseline_profile,
        "browser_timeout_seconds": args.timeout,
        "browser_startup_seed_enabled": args.browser_startup_seed,
        "summary_profiles": summarize_results(
            results,
            targets=args.targets,
            profile_names=profile_names,
        ),
        "results": compact_results(results, targets=args.targets),
    }
    payload["delta_vs_baseline"] = delta_vs_baseline(
        payload["summary_profiles"],
        targets=args.targets,
        profile_names=profile_names,
        baseline_profile=args.baseline_profile,
    )

    output_path = output_dir / "summary.json"
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"wrote {output_path}")
    print(
        json.dumps(
            {
                "output_dir": str(output_dir),
                "summary_profiles": payload["summary_profiles"],
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
        help="targets to benchmark after torfast warm returns",
    )
    parser.add_argument(
        "--profiles",
        nargs="+",
        default=list(DEFAULT_PROFILES),
        choices=PROFILE_CHOICES,
        help="warm/open launch-gate profiles to compare",
    )
    parser.add_argument(
        "--baseline-profile",
        default="auto",
        choices=PROFILE_CHOICES,
        help="baseline profile used for delta tables",
    )
    parser.add_argument("--cycles", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--window-size", default="1280,800")
    parser.add_argument(
        "--profile-order",
        choices=("rotate", "randomized"),
        default="rotate",
        help="how to order profile variants inside each cycle",
    )
    parser.add_argument(
        "--random-seed",
        type=int,
        default=0,
        help="seed used when --profile-order randomized is selected",
    )
    parser.add_argument(
        "--extra-post-warm-wait-seconds",
        action="append",
        default=[],
        metavar="SECONDS",
        help=(
            "add a same-profile benchmark variant that waits this many seconds "
            "after torfast warm returns before the browser benchmark starts"
        ),
    )
    parser.add_argument(
        "--browser-startup-seed-root",
        default=str(
            REPO_ROOT / "tmp" / "torfast-browser-startup-seed"
        ),
    )
    parser.add_argument(
        "--browser-startup-seed",
        action="store_true",
        help="opt in to the shared browser startup seed during page benchmarks",
    )
    parser.add_argument("--port-base", type=int, default=20550)
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument(
        "--keep-run-dirs",
        action="store_true",
        help="keep per-run temp state directories under tmp/",
    )
    return parser


def build_profile_specs(
    *,
    profile_names: list[str],
    extra_post_warm_wait_seconds: list[float],
) -> list[dict[str, object]]:
    specs: list[dict[str, object]] = []
    seen: set[str] = set()
    for profile_name in profile_names:
        if profile_name not in seen:
            specs.append(
                {
                    "name": profile_name,
                    "base_profile_name": profile_name,
                    "extra_post_warm_wait_seconds": 0.0,
                }
            )
            seen.add(profile_name)
        for seconds in extra_post_warm_wait_seconds:
            waited_name = waited_profile_name(profile_name, seconds)
            if waited_name in seen:
                continue
            specs.append(
                {
                    "name": waited_name,
                    "base_profile_name": profile_name,
                    "extra_post_warm_wait_seconds": seconds,
                }
            )
            seen.add(waited_name)
    return specs


def cycle_profile_order(
    cycle: int,
    profile_specs: list[dict[str, object]],
    *,
    profile_order: str = "rotate",
    random_seed: int = 0,
) -> list[dict[str, object]]:
    if not profile_specs:
        return []
    if profile_order == "randomized":
        ordered = list(profile_specs)
        random.Random(f"{random_seed}:{cycle}").shuffle(ordered)
        return ordered
    offset = (cycle - 1) % len(profile_specs)
    return profile_specs[offset:] + profile_specs[:offset]


def run_target_profile_once(
    *,
    target: str,
    profile_name: str,
    base_profile_name: str,
    extra_post_warm_wait_seconds: float,
    cycle: int,
    port: int,
    browser_bin: Path,
    tor_bin: Path,
    timeout: float,
    window_size: str,
    compact_output: bool,
    keep_run_dir: bool,
    browser_startup_seed_root: Path,
    browser_startup_seed_enabled: bool,
    output_dir: Path,
    run_id: str,
) -> dict[str, object]:
    run_dir = (
        REPO_ROOT
        / "tmp"
        / f"torfast-warm-open-benchmark-{run_id}-{target_slug(target)}-{profile_name}-cycle{cycle}"
    )
    shutil.rmtree(run_dir, ignore_errors=True)
    run_dir.mkdir(parents=True, exist_ok=True)
    state_root = run_dir / "state"

    result: dict[str, object] = {
        "target": target,
        "profile_name": profile_name,
        "cycle": cycle,
        "port": port,
        "run_dir": str(run_dir),
        "state_root": str(state_root),
    }

    warm_command = build_torfast_command(
        action="warm",
        state_root=state_root,
        browser_bin=browser_bin,
        tor_bin=tor_bin,
        target=target,
        port=port,
        profile_name=base_profile_name,
        browser_timeout=timeout,
        browser_startup_seed_root=browser_startup_seed_root,
        browser_startup_seed_enabled=browser_startup_seed_enabled,
        headed=True,
    )
    warm_run = run_command(warm_command)
    warm_launch = read_json_file(state_root / "launch.json")
    result["warm"] = warm_run
    result["warm_launch"] = compact_launch(warm_launch)
    result["post_warm_wait_seconds"] = extra_post_warm_wait_seconds

    benchmarks: dict[str, object] = {}
    benchmark_wall_seconds = None
    boot_after_benchmark: dict[str, object] | None = None
    if warm_run.get("ok"):
        if extra_post_warm_wait_seconds > 0:
            time.sleep(extra_post_warm_wait_seconds)
        benchmark_started = time.monotonic()
        benchmarks = run_browser_benchmarks(
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
        benchmark_wall_seconds = round(time.monotonic() - benchmark_started, 3)
        service = warm_service(result)
        if isinstance(service, dict):
            pid = service.get("pid")
            tor_log = service.get("tor_log")
            if isinstance(pid, int) and isinstance(tor_log, str):
                boot_after_benchmark = wait_for_existing_service_ready_in_log(
                    pid=pid,
                    log_path=Path(tor_log),
                    timeout=60.0,
                    ready_text="Bootstrapped 100%",
                    process_name="tor",
                )
    result["benchmarks"] = benchmarks
    result["benchmark_wall_seconds"] = benchmark_wall_seconds
    result["boot_after_benchmark"] = boot_after_benchmark
    result["torrc"] = read_torrc_quality(state_root / "torrc")

    stop_run = run_command(build_stop_command(state_root))
    stop_payload = parse_json_text("\n".join(stop_run.get("stdout_tail", [])))
    result["stop"] = {
        **stop_run,
        "response": stop_payload,
    }

    copy_path = (
        output_dir
        / f"{target_slug(target)}-{profile_name}-cycle{cycle}.json"
    )
    copy_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")

    if not keep_run_dir:
        shutil.rmtree(run_dir, ignore_errors=True)

    return result


def warm_service(result: dict[str, object]) -> dict[str, object] | None:
    warm_launch = result.get("warm_launch")
    if not isinstance(warm_launch, dict):
        return None
    service = warm_launch.get("reused_tor_service")
    return service if isinstance(service, dict) else None


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


def result_ok(result: dict[str, object]) -> bool:
    warm = result.get("warm")
    warm_launch = result.get("warm_launch")
    stop = result.get("stop")
    target = result.get("target")
    if not isinstance(target, str):
        return False
    if not isinstance(warm, dict) or warm.get("ok") is not True:
        return False
    if (
        not isinstance(warm_launch, dict)
        or not isinstance(warm_launch.get("tor_managed_ready"), dict)
        or warm_launch["tor_managed_ready"].get("ok") is not True
    ):
        return False
    if benchmark_summary_for_result(result, target).get("ok") is not True:
        return False
    torrc = result.get("torrc")
    if not isinstance(torrc, dict) or torrc.get("isolate_socks_auth") is not True:
        return False
    boot_after_benchmark = result.get("boot_after_benchmark")
    if (
        not isinstance(boot_after_benchmark, dict)
        or boot_after_benchmark.get("ok") is not True
    ):
        return False
    if not isinstance(stop, dict) or stop.get("ok") is not True:
        return False
    return True


def benchmark_elapsed_ms(result: dict[str, object]) -> float | None:
    target = result.get("target")
    if not isinstance(target, str):
        return None
    summary = benchmark_summary_for_result(result, target)
    value = summary.get("median_elapsed_ms")
    if not isinstance(value, (int, float)):
        return None
    return round(float(value), 3)


def benchmark_load_ms(result: dict[str, object]) -> float | None:
    target = result.get("target")
    if not isinstance(target, str):
        return None
    summary = benchmark_summary_for_result(result, target)
    value = summary.get("median_load_ms")
    if not isinstance(value, (int, float)):
        return None
    return round(float(value), 3)


def combined_wall_seconds(result: dict[str, object]) -> float | None:
    warm = result.get("warm")
    benchmark_wall_seconds = result.get("benchmark_wall_seconds")
    if not isinstance(warm, dict):
        return None
    warm_seconds = warm.get("wall_seconds")
    if not isinstance(warm_seconds, (int, float)) or not isinstance(
        benchmark_wall_seconds, (int, float)
    ):
        return None
    return round(float(warm_seconds) + float(benchmark_wall_seconds), 3)


def summarize_results(
    results: list[dict[str, object]],
    *,
    targets: list[str],
    profile_names: list[str],
) -> dict[str, object]:
    profiles: dict[str, object] = {}
    for target in targets:
        target_profiles: dict[str, object] = {}
        for profile_name in profile_names:
            rows = [
                result
                for result in results
                if result.get("target") == target
                and result.get("profile_name") == profile_name
            ]
            ok_rows = [result for result in rows if result_ok(result)]
            warm_wall_values = [(result.get("warm") or {}).get("wall_seconds") for result in ok_rows]
            warm_ready_values = [warm_ready_seconds(result) for result in ok_rows]
            post_warm_wait_values = [
                result.get("post_warm_wait_seconds") for result in ok_rows
            ]
            benchmark_wall_values = [
                result.get("benchmark_wall_seconds") for result in ok_rows
            ]
            elapsed_values = [benchmark_elapsed_ms(result) for result in ok_rows]
            load_values = [benchmark_load_ms(result) for result in ok_rows]
            combined_wall_values = [combined_wall_seconds(result) for result in ok_rows]
            target_profiles[profile_name] = {
                "runs": len(rows),
                "ok_runs": len(ok_rows),
                "median_warm_wall_seconds": median_value(warm_wall_values),
                "median_warm_ready_seconds": median_value(warm_ready_values),
                "median_post_warm_wait_seconds": median_value(post_warm_wait_values),
                "median_benchmark_wall_seconds": median_value(benchmark_wall_values),
                "median_elapsed_ms": median_value(elapsed_values),
                "p90_elapsed_ms": percentile_value(elapsed_values, 90),
                "max_elapsed_ms": max_value(elapsed_values),
                "median_load_ms": median_value(load_values),
                "p90_load_ms": percentile_value(load_values, 90),
                "max_load_ms": max_value(load_values),
                "median_combined_wall_seconds": median_value(combined_wall_values),
                "p90_combined_wall_seconds": percentile_value(
                    combined_wall_values, 90
                ),
                "max_combined_wall_seconds": max_value(combined_wall_values),
                "warm_ready_ok_runs": sum(
                    1
                    for result in rows
                    if isinstance(
                        (ready := (result.get("warm_launch") or {}).get("tor_managed_ready")),
                        dict,
                    )
                    and ready.get("ok") is True
                ),
                "torrc_isolate_socks_auth_ok_runs": sum(
                    1
                    for result in rows
                    if isinstance((torrc := result.get("torrc")), dict)
                    and torrc.get("isolate_socks_auth") is True
                ),
                "boot_after_benchmark_ok_runs": sum(
                    1
                    for result in rows
                    if isinstance((boot := result.get("boot_after_benchmark")), dict)
                    and boot.get("ok") is True
                ),
                "stop_ok_runs": sum(
                    1
                    for result in rows
                    if isinstance((stop := result.get("stop")), dict)
                    and stop.get("ok") is True
                ),
            }
        profiles[target] = target_profiles
    return profiles


def delta_vs_baseline(
    profiles: dict[str, object],
    *,
    targets: list[str],
    profile_names: list[str],
    baseline_profile: str,
) -> dict[str, object]:
    deltas: dict[str, object] = {}
    for target in targets:
        target_profiles = profiles.get(target)
        if not isinstance(target_profiles, dict):
            continue
        baseline = target_profiles.get(baseline_profile)
        if not isinstance(baseline, dict):
            continue
        target_deltas: dict[str, object] = {}
        for profile_name in profile_names:
            candidate = target_profiles.get(profile_name)
            if not isinstance(candidate, dict):
                continue
            target_deltas[profile_name] = {
                "warm_wall_seconds": subtract_metric(
                    candidate.get("median_warm_wall_seconds"),
                    baseline.get("median_warm_wall_seconds"),
                ),
                "warm_ready_seconds": subtract_metric(
                    candidate.get("median_warm_ready_seconds"),
                    baseline.get("median_warm_ready_seconds"),
                ),
                "post_warm_wait_seconds": subtract_metric(
                    candidate.get("median_post_warm_wait_seconds"),
                    baseline.get("median_post_warm_wait_seconds"),
                ),
                "benchmark_wall_seconds": subtract_metric(
                    candidate.get("median_benchmark_wall_seconds"),
                    baseline.get("median_benchmark_wall_seconds"),
                ),
                "elapsed_ms": subtract_metric(
                    candidate.get("median_elapsed_ms"),
                    baseline.get("median_elapsed_ms"),
                ),
                "p90_elapsed_ms": subtract_metric(
                    candidate.get("p90_elapsed_ms"),
                    baseline.get("p90_elapsed_ms"),
                ),
                "max_elapsed_ms": subtract_metric(
                    candidate.get("max_elapsed_ms"),
                    baseline.get("max_elapsed_ms"),
                ),
                "load_ms": subtract_metric(
                    candidate.get("median_load_ms"),
                    baseline.get("median_load_ms"),
                ),
                "p90_load_ms": subtract_metric(
                    candidate.get("p90_load_ms"),
                    baseline.get("p90_load_ms"),
                ),
                "max_load_ms": subtract_metric(
                    candidate.get("max_load_ms"),
                    baseline.get("max_load_ms"),
                ),
                "combined_wall_seconds": subtract_metric(
                    candidate.get("median_combined_wall_seconds"),
                    baseline.get("median_combined_wall_seconds"),
                ),
                "p90_combined_wall_seconds": subtract_metric(
                    candidate.get("p90_combined_wall_seconds"),
                    baseline.get("p90_combined_wall_seconds"),
                ),
                "max_combined_wall_seconds": subtract_metric(
                    candidate.get("max_combined_wall_seconds"),
                    baseline.get("max_combined_wall_seconds"),
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
        target = result.get("target")
        if target not in targets:
            continue
        compact.append(
            {
                "target": target,
                "profile_name": result.get("profile_name"),
                "cycle": result.get("cycle"),
                "port": result.get("port"),
                "warm_ready_gate": warm_ready_gate(result),
                "warm_ready_seconds": warm_ready_seconds(result),
                "warm_wall_seconds": (result.get("warm") or {}).get("wall_seconds"),
                "post_warm_wait_seconds": result.get("post_warm_wait_seconds"),
                "benchmark_wall_seconds": result.get("benchmark_wall_seconds"),
                "elapsed_ms": benchmark_elapsed_ms(result),
                "load_ms": benchmark_load_ms(result),
                "combined_wall_seconds": combined_wall_seconds(result),
                "torrc_isolate_socks_auth": (
                    (result.get("torrc") or {}).get("isolate_socks_auth")
                ),
                "boot_after_benchmark_ok": (
                    (result.get("boot_after_benchmark") or {}).get("ok")
                ),
                "stop_ok": ((result.get("stop") or {}).get("ok")),
                "ok": result_ok(result),
            }
        )
    return compact


def payload_ok(results: list[dict[str, object]], *, targets: list[str]) -> bool:
    for result in results:
        if result.get("target") not in targets:
            return False
        if not result_ok(result):
            return False
    return True


if __name__ == "__main__":
    raise SystemExit(main())
