#!/usr/bin/env python3
"""Compare torfast cold launches, seeded launches, primed launches, and warm reuse."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import time


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from torfast.cli import discover_browser_bin, discover_tor_bin
from torfast.browser_startup_seed import DEFAULT_BROWSER_STARTUP_SEED_ROOT
from torfast.dir_cache_seed import DEFAULT_C_TOR_DIR_CACHE_SEED_ROOT


DEFAULT_URL = "about:tor"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--browser-bin")
    parser.add_argument("--tor-bin")
    parser.add_argument("--runs", type=int, default=2)
    parser.add_argument("--browser-timeout", type=float, default=6.0)
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--port-base", type=int, default=19500)
    parser.add_argument("--output-root", default="results")
    parser.add_argument("--state-root-base")
    parser.add_argument("--dir-cache-seed-root")
    parser.add_argument(
        "--browser-startup-seed-root",
        default=str(DEFAULT_BROWSER_STARTUP_SEED_ROOT),
    )
    parser.add_argument("--keep-state-roots", action="store_true")
    args = parser.parse_args()

    if args.runs < 1:
        print("--runs must be at least 1", file=sys.stderr)
        return 2
    if args.browser_timeout <= 0:
        print("--browser-timeout must be positive", file=sys.stderr)
        return 2

    browser = discover_browser_bin(args.browser_bin)
    if not browser["found"] or not isinstance(browser.get("path"), str):
        print(
            "Tor Browser binary not found; pass --browser-bin or run "
            "`python3 -m torfast install-browser` first.",
            file=sys.stderr,
        )
        return 2
    tor = discover_tor_bin(args.tor_bin)
    if not tor["found"] or not isinstance(tor.get("path"), str):
        print(
            "C Tor binary not found; pass --tor-bin, run "
            "`python3 -m torfast install-browser`, or build/install it first.",
            file=sys.stderr,
        )
        return 2

    run_id = time.strftime("%Y%m%dT%H%M%S")
    output_dir = Path(args.output_root).resolve() / f"torfast-runtime-compare-{run_id}"
    output_dir.mkdir(parents=True, exist_ok=True)
    if args.state_root_base:
        state_root_base = Path(args.state_root_base).resolve()
    else:
        state_root_base = (REPO_ROOT / "tmp" / f"torfast-runtime-compare-{run_id}").resolve()
    state_root_base.mkdir(parents=True, exist_ok=True)
    if args.dir_cache_seed_root:
        dir_cache_seed_root = Path(args.dir_cache_seed_root).resolve()
    else:
        dir_cache_seed_root = (
            REPO_ROOT / "tmp" / f"torfast-runtime-compare-seed-{run_id}"
        ).resolve()
    cleanup_path(dir_cache_seed_root)

    payload: dict[str, object] = {
        "run_id": run_id,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "repo_root": str(REPO_ROOT),
        "browser_bin": str(Path(str(browser["path"])).resolve()),
        "tor_bin": str(Path(str(tor["path"])).resolve()),
        "url": args.url,
        "runs": args.runs,
        "browser_timeout_seconds": args.browser_timeout,
        "output_dir": str(output_dir),
        "state_root_base": str(state_root_base),
        "dir_cache_seed_root": str(dir_cache_seed_root),
        "seeded_launch_order_mode": "rotate_by_run_index",
        "browser_startup_seed_root": str(
            Path(args.browser_startup_seed_root).resolve()
        ),
        "profiles": {
            "cold_launch": {"runs": []},
            "seeded_launch": {"runs": []},
            "seeded_launch_no_browser_startup_seed": {"runs": []},
            "primed_launch": {"runs": []},
            "warm_seed": {"runs": []},
            "warm_reuse": {"runs": []},
        },
    }

    cold_profile = payload["profiles"]["cold_launch"]
    seeded_profile = payload["profiles"]["seeded_launch"]
    seeded_no_browser_startup_seed_profile = payload["profiles"][
        "seeded_launch_no_browser_startup_seed"
    ]
    primed_profile = payload["profiles"]["primed_launch"]
    warm_seed_profile = payload["profiles"]["warm_seed"]
    warm_reuse_profile = payload["profiles"]["warm_reuse"]
    assert isinstance(cold_profile, dict)
    assert isinstance(seeded_profile, dict)
    assert isinstance(seeded_no_browser_startup_seed_profile, dict)
    assert isinstance(primed_profile, dict)
    assert isinstance(warm_seed_profile, dict)
    assert isinstance(warm_reuse_profile, dict)
    cold_runs = cold_profile["runs"]
    seeded_runs = seeded_profile["runs"]
    seeded_no_browser_startup_seed_runs = (
        seeded_no_browser_startup_seed_profile["runs"]
    )
    primed_runs = primed_profile["runs"]
    warm_seed_runs = warm_seed_profile["runs"]
    warm_reuse_runs = warm_reuse_profile["runs"]
    assert isinstance(cold_runs, list)
    assert isinstance(seeded_runs, list)
    assert isinstance(seeded_no_browser_startup_seed_runs, list)
    assert isinstance(primed_runs, list)
    assert isinstance(warm_seed_runs, list)
    assert isinstance(warm_reuse_runs, list)

    for run_index in range(1, args.runs + 1):
        cold_state_root = state_root_base / f"cold-{run_index}"
        seeded_seed_root = dir_cache_seed_root / f"seeded-{run_index}"
        seeded_prime_state_root = state_root_base / f"seeded-prime-{run_index}"
        seeded_launch_state_root = state_root_base / f"seeded-launch-{run_index}"
        seeded_no_browser_startup_seed_state_root = (
            state_root_base / f"seeded-launch-no-browser-startup-seed-{run_index}"
        )
        primed_state_root = state_root_base / f"primed-{run_index}"
        warm_state_root = state_root_base / f"warm-{run_index}"
        cold_port = args.port_base + (run_index - 1) * 5
        seeded_port = cold_port + 1
        primed_port = cold_port + 2
        warm_port = cold_port + 3
        cold_out = output_dir / "cold_launch" / f"run-{run_index}-launch.json"
        seeded_prime_out = output_dir / "seeded_launch" / f"run-{run_index}-prime.json"
        seeded_launch_out = output_dir / "seeded_launch" / f"run-{run_index}-launch.json"
        seeded_no_browser_startup_seed_out = (
            output_dir
            / "seeded_launch_no_browser_startup_seed"
            / f"run-{run_index}-launch.json"
        )
        primed_prime_out = output_dir / "primed_launch" / f"run-{run_index}-prime.json"
        primed_launch_out = output_dir / "primed_launch" / f"run-{run_index}-launch.json"
        warm_seed_out = output_dir / "warm_seed" / f"run-{run_index}-launch.json"
        warm_reuse_out = output_dir / "warm_reuse" / f"run-{run_index}-launch.json"

        cleanup_state_root(cold_state_root)
        cleanup_state_root(seeded_prime_state_root)
        cleanup_state_root(seeded_launch_state_root)
        cleanup_state_root(seeded_no_browser_startup_seed_state_root)
        cleanup_path(seeded_seed_root)
        cleanup_state_root(primed_state_root)
        cleanup_state_root(warm_state_root)

        cold_runs.append(
            run_profile(
                profile_name="cold_launch",
                run_index=run_index,
                browser_bin=Path(str(browser["path"])),
                tor_bin=Path(str(tor["path"])),
                state_root=cold_state_root,
                port=cold_port,
                url=args.url,
                browser_timeout=args.browser_timeout,
                command_name="launch",
                copied_launch_path=cold_out,
                dir_cache_seed_root=seeded_seed_root,
                no_dir_cache_seed=True,
            )
        )

        seeded_prime_result = run_profile(
            profile_name="seeded_prime",
            run_index=run_index,
            browser_bin=Path(str(browser["path"])),
            tor_bin=Path(str(tor["path"])),
            state_root=seeded_prime_state_root,
            port=seeded_port,
            url=args.url,
            browser_timeout=args.browser_timeout,
            command_name="prime",
            copied_launch_path=seeded_prime_out,
            dir_cache_seed_root=seeded_seed_root,
            no_dir_cache_seed=False,
        )
        seeded_launch_specs = [
            {
                "profile_name": "seeded_launch",
                "state_root": seeded_launch_state_root,
                "copied_launch_path": seeded_launch_out,
                "browser_startup_seed_enabled": True,
            },
            {
                "profile_name": "seeded_launch_no_browser_startup_seed",
                "state_root": seeded_no_browser_startup_seed_state_root,
                "copied_launch_path": seeded_no_browser_startup_seed_out,
                "browser_startup_seed_enabled": False,
            },
        ]
        if seeded_launch_order_for_run(run_index)[0] != "seeded_launch":
            seeded_launch_specs.reverse()
        seeded_launch_results: dict[str, dict[str, object]] = {}
        if profile_run_ok(seeded_prime_result):
            seed_launch = seeded_prime_result.get("launch")
            seed_launch_dict = seed_launch if isinstance(seed_launch, dict) else {}
            seed_tor_boot = (
                seed_launch_dict.get("tor_boot")
                if isinstance(seed_launch_dict.get("tor_boot"), dict)
                else {}
            )
            for spec in seeded_launch_specs:
                result = run_profile(
                    profile_name=str(spec["profile_name"]),
                    run_index=run_index,
                    browser_bin=Path(str(browser["path"])),
                    tor_bin=Path(str(tor["path"])),
                    state_root=Path(str(spec["state_root"])),
                    port=seeded_port,
                    url=args.url,
                    browser_timeout=args.browser_timeout,
                    command_name="launch",
                    copied_launch_path=Path(str(spec["copied_launch_path"])),
                    dir_cache_seed_root=seeded_seed_root,
                    no_dir_cache_seed=False,
                    browser_startup_seed_root=Path(
                        args.browser_startup_seed_root
                    ).resolve(),
                    browser_startup_seed_enabled=bool(
                        spec["browser_startup_seed_enabled"]
                    ),
                )
                metrics = result.get("metrics")
                if isinstance(metrics, dict):
                    metrics["seed_prime_ok"] = True
                    metrics["seed_prime_wall_seconds"] = numeric_value(
                        seeded_prime_result.get("wall_seconds")
                    )
                    metrics["seed_prime_tor_boot_seconds"] = numeric_value(
                        seed_tor_boot.get("seconds")
                    )
                result["seed_prime_cache"] = seeded_prime_result
                seeded_launch_results[str(spec["profile_name"])] = result
        else:
            for spec in seeded_launch_specs:
                result = skipped_profile_result(
                    profile_name=str(spec["profile_name"]),
                    run_index=run_index,
                    state_root=Path(str(spec["state_root"])),
                    port=seeded_port,
                    reason="seed-prime run failed",
                )
                result["seed_prime_cache"] = seeded_prime_result
                seeded_launch_results[str(spec["profile_name"])] = result
        seeded_runs.append(seeded_launch_results["seeded_launch"])
        seeded_no_browser_startup_seed_runs.append(
            seeded_launch_results["seeded_launch_no_browser_startup_seed"]
        )

        prime_result = run_profile(
            profile_name="prime_seed",
            run_index=run_index,
            browser_bin=Path(str(browser["path"])),
            tor_bin=Path(str(tor["path"])),
            state_root=primed_state_root,
            port=primed_port,
            url=args.url,
            browser_timeout=args.browser_timeout,
            command_name="prime",
            copied_launch_path=primed_prime_out,
            dir_cache_seed_root=dir_cache_seed_root,
            no_dir_cache_seed=True,
        )
        if profile_run_ok(prime_result):
            primed_result = run_profile(
                profile_name="primed_launch",
                run_index=run_index,
                browser_bin=Path(str(browser["path"])),
                tor_bin=Path(str(tor["path"])),
                state_root=primed_state_root,
                port=primed_port,
                url=args.url,
                browser_timeout=args.browser_timeout,
                command_name="launch",
                copied_launch_path=primed_launch_out,
                dir_cache_seed_root=dir_cache_seed_root,
                no_dir_cache_seed=True,
            )
            metrics = primed_result.get("metrics")
            if isinstance(metrics, dict):
                metrics["prime_ok"] = True
                prime_launch = prime_result.get("launch")
                prime_launch_dict = prime_launch if isinstance(prime_launch, dict) else {}
                prime_tor_boot = (
                    prime_launch_dict.get("tor_boot")
                    if isinstance(prime_launch_dict.get("tor_boot"), dict)
                    else {}
                )
                metrics["prime_wall_seconds"] = numeric_value(prime_result.get("wall_seconds"))
                metrics["prime_tor_boot_seconds"] = numeric_value(
                    prime_tor_boot.get("seconds")
                )
            primed_result["prime_cache"] = prime_result
        else:
            primed_result = skipped_profile_result(
                profile_name="primed_launch",
                run_index=run_index,
                state_root=primed_state_root,
                port=primed_port,
                reason="prime run failed",
            )
            primed_result["prime_cache"] = prime_result
        primed_runs.append(primed_result)

        seed_result = run_profile(
            profile_name="warm_seed",
            run_index=run_index,
            browser_bin=Path(str(browser["path"])),
            tor_bin=Path(str(tor["path"])),
            state_root=warm_state_root,
            port=warm_port,
            url=args.url,
            browser_timeout=args.browser_timeout,
            command_name="start",
            copied_launch_path=warm_seed_out,
            dir_cache_seed_root=dir_cache_seed_root,
            no_dir_cache_seed=True,
        )
        warm_seed_runs.append(seed_result)

        if profile_run_ok(seed_result):
            reuse_result = run_profile(
                profile_name="warm_reuse",
                run_index=run_index,
                browser_bin=Path(str(browser["path"])),
                tor_bin=Path(str(tor["path"])),
                state_root=warm_state_root,
                port=warm_port,
                url=args.url,
                browser_timeout=args.browser_timeout,
                command_name="open",
                copied_launch_path=warm_reuse_out,
                dir_cache_seed_root=dir_cache_seed_root,
                no_dir_cache_seed=True,
            )
        else:
            reuse_result = skipped_profile_result(
                profile_name="warm_reuse",
                run_index=run_index,
                state_root=warm_state_root,
                port=warm_port,
                reason="warm seed run failed",
            )
        warm_reuse_runs.append(reuse_result)

        stop_result = stop_managed_tor_service(warm_state_root)
        seed_result["stop_managed_tor"] = stop_result
        reuse_result["stop_managed_tor"] = stop_result

        if not args.keep_state_roots:
            cleanup_state_root(cold_state_root)
            cleanup_state_root(seeded_prime_state_root)
            cleanup_state_root(seeded_launch_state_root)
            cleanup_state_root(seeded_no_browser_startup_seed_state_root)
            cleanup_state_root(primed_state_root)
            cleanup_state_root(warm_state_root)
            cleanup_path(seeded_seed_root)

    add_profile_summary(cold_profile)
    add_profile_summary(seeded_profile)
    add_profile_summary(seeded_no_browser_startup_seed_profile)
    add_profile_summary(primed_profile)
    add_profile_summary(warm_seed_profile)
    add_profile_summary(warm_reuse_profile)
    payload["summary"] = short_summary(payload)

    output_path = output_dir / "torfast-runtime-compare.json"
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"wrote {output_path}")
    print(json.dumps(payload["summary"], indent=2, sort_keys=True))
    summary = payload["summary"]
    assert isinstance(summary, dict)
    return 0 if bool(summary.get("ok")) else 1


def cleanup_state_root(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)


def cleanup_path(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)


def seeded_launch_order_for_run(run_index: int) -> list[str]:
    order = [
        "seeded_launch",
        "seeded_launch_no_browser_startup_seed",
    ]
    if run_index % 2 == 0:
        order.reverse()
    return order


def run_profile(
    *,
    profile_name: str,
    run_index: int,
    browser_bin: Path,
    tor_bin: Path,
    state_root: Path,
    port: int,
    url: str,
    browser_timeout: float,
    command_name: str,
    copied_launch_path: Path,
    dir_cache_seed_root: Path,
    no_dir_cache_seed: bool,
    browser_startup_seed_root: Path = DEFAULT_BROWSER_STARTUP_SEED_ROOT,
    browser_startup_seed_enabled: bool | None = None,
) -> dict[str, object]:
    command = [
        sys.executable,
        "-m",
        "torfast",
        command_name,
        "--browser-bin",
        str(browser_bin.resolve()),
        "--tor-bin",
        str(tor_bin.resolve()),
        "--headless",
        "--browser-timeout",
        str(browser_timeout),
        "--url",
        url,
        "--state-root",
        str(state_root.resolve()),
        "--port",
        str(port),
        "--dir-cache-seed-root",
        str(dir_cache_seed_root.resolve()),
        "--browser-startup-seed-root",
        str(browser_startup_seed_root.resolve()),
    ]
    if no_dir_cache_seed:
        command.append("--no-dir-cache-seed")
    if browser_startup_seed_enabled is True:
        command.append("--browser-startup-seed")
    elif browser_startup_seed_enabled is False:
        command.append("--no-browser-startup-seed")
    started = time.monotonic()
    completed = subprocess.run(command, cwd=REPO_ROOT, capture_output=True, text=True)
    wall_seconds = round(time.monotonic() - started, 3)
    launch_json_path = state_root / "launch.json"
    launch = load_json(launch_json_path)
    copied_path = copy_launch_json(launch_json_path, copied_launch_path)
    result: dict[str, object] = {
        "profile": profile_name,
        "run_index": run_index,
        "command": command,
        "exit_code": completed.returncode,
        "wall_seconds": wall_seconds,
        "state_root": str(state_root.resolve()),
        "port": port,
        "launch_path": str(copied_path) if copied_path is not None else None,
        "stdout_tail": tail_lines(completed.stdout),
        "stderr_tail": tail_lines(completed.stderr),
        "launch": launch,
    }
    result["metrics"] = derive_run_metrics(result, browser_timeout_seconds=browser_timeout)
    return result


def skipped_profile_result(
    *,
    profile_name: str,
    run_index: int,
    state_root: Path,
    port: int,
    reason: str,
) -> dict[str, object]:
    return {
        "profile": profile_name,
        "run_index": run_index,
        "command": None,
        "exit_code": None,
        "wall_seconds": None,
        "state_root": str(state_root.resolve()),
        "port": port,
        "launch_path": None,
        "stdout_tail": [],
        "stderr_tail": [],
        "launch": None,
        "metrics": {
            "ok": False,
            "reason": reason,
            "browser_ok": False,
            "tor_ok": False,
            "timed_out": False,
            "reused_tor_service": False,
        },
    }


def stop_managed_tor_service(state_root: Path) -> dict[str, object]:
    command = [
        sys.executable,
        "-m",
        "torfast",
        "stop",
        "--state-root",
        str(state_root.resolve()),
    ]
    completed = subprocess.run(command, cwd=REPO_ROOT, capture_output=True, text=True)
    payload = parse_first_json_object(completed.stdout)
    return {
        "exit_code": completed.returncode,
        "stdout_tail": tail_lines(completed.stdout),
        "stderr_tail": tail_lines(completed.stderr),
        "result": payload,
    }


def parse_first_json_object(text: str) -> dict[str, object] | None:
    stripped = text.strip()
    if not stripped:
        return None
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def load_json(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def copy_launch_json(source_path: Path, destination_path: Path) -> Path | None:
    if not source_path.exists():
        return None
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, destination_path)
    return destination_path


def tail_lines(text: str, *, limit: int = 40) -> list[str]:
    lines = [line for line in text.splitlines() if line]
    return lines[-limit:]


def derive_run_metrics(
    run: dict[str, object],
    *,
    browser_timeout_seconds: float,
) -> dict[str, object]:
    launch = run.get("launch")
    launch_dict = launch if isinstance(launch, dict) else {}
    browser = launch_dict.get("browser") if isinstance(launch_dict.get("browser"), dict) else {}
    tor_boot = launch_dict.get("tor_boot") if isinstance(launch_dict.get("tor_boot"), dict) else {}
    browser_startup_seed_apply = (
        launch_dict.get("browser_startup_seed_apply")
        if isinstance(launch_dict.get("browser_startup_seed_apply"), dict)
        else {}
    )
    browser_skipped = browser.get("skipped") is True
    reused_tor_service = tor_boot.get("reused_service") is True
    tor_boot_seconds = numeric_value(tor_boot.get("seconds"))
    if reused_tor_service and tor_boot_seconds is None:
        tor_boot_seconds = 0.0
    wall_seconds = numeric_value(run.get("wall_seconds"))
    browser_elapsed_seconds = numeric_value(browser.get("elapsed_seconds"))
    launch_overhead_seconds = None
    if wall_seconds is not None:
        if browser_skipped:
            launch_overhead_seconds = round(wall_seconds, 3)
        else:
            launch_overhead_seconds = round(
                max(0.0, wall_seconds - browser_timeout_seconds),
                3,
            )
    post_boot_browser_overhead_seconds = None
    if launch_overhead_seconds is not None and tor_boot_seconds is not None:
        post_boot_browser_overhead_seconds = round(
            max(0.0, launch_overhead_seconds - tor_boot_seconds),
            3,
        )
    browser_ok = browser.get("ok") is True
    tor_ok = tor_boot.get("ok") is True if tor_boot else False
    return {
        "ok": bool(run.get("exit_code") == 0 and browser_ok and tor_ok),
        "browser_ok": browser_ok,
        "tor_ok": tor_ok,
        "timed_out": browser.get("timed_out") is True,
        "reused_tor_service": reused_tor_service,
        "wall_seconds": wall_seconds,
        "browser_elapsed_seconds": browser_elapsed_seconds,
        "browser_startup_seed_applied": (
            browser_startup_seed_apply.get("applied") is True
        ),
        "tor_boot_seconds": tor_boot_seconds,
        "launch_overhead_seconds": launch_overhead_seconds,
        "post_boot_browser_overhead_seconds": post_boot_browser_overhead_seconds,
    }


def numeric_value(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


def profile_run_ok(run: dict[str, object]) -> bool:
    metrics = run.get("metrics")
    return isinstance(metrics, dict) and metrics.get("ok") is True


def add_profile_summary(profile: dict[str, object]) -> None:
    runs = profile.get("runs")
    assert isinstance(runs, list)
    profile["summary"] = summarize_profile_runs(runs)


def summarize_profile_runs(runs: list[dict[str, object]]) -> dict[str, object]:
    metrics = [
        run.get("metrics")
        for run in runs
        if isinstance(run.get("metrics"), dict)
    ]
    metric_dicts = [metric for metric in metrics if isinstance(metric, dict)]
    ok_runs = sum(1 for metric in metric_dicts if metric.get("ok") is True)
    summary = {
        "ok": bool(metric_dicts) and ok_runs == len(metric_dicts),
        "runs": len(runs),
        "ok_runs": ok_runs,
        "reused_runs": sum(
            1 for metric in metric_dicts if metric.get("reused_tor_service") is True
        ),
        "browser_startup_seed_applied_runs": sum(
            1
            for metric in metric_dicts
            if metric.get("browser_startup_seed_applied") is True
        ),
        "timed_timeout_stop_runs": sum(
            1 for metric in metric_dicts if metric.get("timed_out") is True
        ),
        "median_elapsed_ms": median_ms(metric_dicts, "wall_seconds"),
        "median_tor_boot_seconds": median_seconds(metric_dicts, "tor_boot_seconds"),
        "median_browser_elapsed_seconds": median_seconds(
            metric_dicts, "browser_elapsed_seconds"
        ),
        "median_launch_overhead_seconds": median_seconds(
            metric_dicts, "launch_overhead_seconds"
        ),
        "median_prime_wall_seconds": median_seconds(metric_dicts, "prime_wall_seconds"),
        "median_prime_tor_boot_seconds": median_seconds(
            metric_dicts, "prime_tor_boot_seconds"
        ),
        "median_seed_prime_wall_seconds": median_seconds(
            metric_dicts, "seed_prime_wall_seconds"
        ),
        "median_seed_prime_tor_boot_seconds": median_seconds(
            metric_dicts, "seed_prime_tor_boot_seconds"
        ),
        "median_post_boot_browser_overhead_seconds": median_seconds(
            metric_dicts, "post_boot_browser_overhead_seconds"
        ),
        "min_elapsed_ms": min_ms(metric_dicts, "wall_seconds"),
        "max_elapsed_ms": max_ms(metric_dicts, "wall_seconds"),
    }
    return summary


def numeric_metric_values(
    metrics: list[dict[str, object]],
    key: str,
) -> list[float]:
    values: list[float] = []
    for metric in metrics:
        value = metric.get(key)
        if isinstance(value, (int, float)):
            values.append(float(value))
    return values


def median_seconds(metrics: list[dict[str, object]], key: str) -> float | None:
    values = numeric_metric_values(metrics, key)
    if not values:
        return None
    return round(float(statistics.median(values)), 3)


def median_ms(metrics: list[dict[str, object]], key: str) -> float | None:
    value = median_seconds(metrics, key)
    return None if value is None else round(value * 1000, 3)


def min_ms(metrics: list[dict[str, object]], key: str) -> float | None:
    values = numeric_metric_values(metrics, key)
    if not values:
        return None
    return round(min(values) * 1000, 3)


def max_ms(metrics: list[dict[str, object]], key: str) -> float | None:
    values = numeric_metric_values(metrics, key)
    if not values:
        return None
    return round(max(values) * 1000, 3)


def short_summary(payload: dict[str, object]) -> dict[str, object]:
    profiles = payload.get("profiles")
    assert isinstance(profiles, dict)
    profile_summaries = {
        name: profile.get("summary")
        for name, profile in profiles.items()
        if isinstance(profile, dict)
    }
    summaries = [
        summary
        for summary in profile_summaries.values()
        if isinstance(summary, dict)
    ]
    summary = {
        "ok": bool(summaries) and all(summary.get("ok") for summary in summaries),
        "url": payload.get("url"),
        "browser_timeout_seconds": payload.get("browser_timeout_seconds"),
        "profiles": profile_summaries,
    }
    seeded = profile_summaries.get("seeded_launch")
    seeded_no_browser_startup_seed = profile_summaries.get(
        "seeded_launch_no_browser_startup_seed"
    )
    if isinstance(seeded, dict) and isinstance(seeded_no_browser_startup_seed, dict):
        summary["delta_seeded_launch_vs_no_browser_startup_seed"] = summary_delta(
            seeded,
            seeded_no_browser_startup_seed,
        )
    return summary


def summary_delta(
    current: dict[str, object], baseline: dict[str, object]
) -> dict[str, object]:
    return {
        "elapsed_ms": subtract_metric(
            current.get("median_elapsed_ms"), baseline.get("median_elapsed_ms")
        ),
        "tor_boot_seconds": subtract_metric(
            current.get("median_tor_boot_seconds"),
            baseline.get("median_tor_boot_seconds"),
        ),
        "launch_overhead_seconds": subtract_metric(
            current.get("median_launch_overhead_seconds"),
            baseline.get("median_launch_overhead_seconds"),
        ),
        "post_boot_browser_overhead_seconds": subtract_metric(
            current.get("median_post_boot_browser_overhead_seconds"),
            baseline.get("median_post_boot_browser_overhead_seconds"),
        ),
    }


def subtract_metric(current: object, baseline: object) -> float | None:
    current_num = numeric_value(current)
    baseline_num = numeric_value(baseline)
    if current_num is None or baseline_num is None:
        return None
    return round(current_num - baseline_num, 3)


if __name__ == "__main__":
    raise SystemExit(main())
