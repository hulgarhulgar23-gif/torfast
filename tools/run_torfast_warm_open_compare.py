#!/usr/bin/env python3
"""Compare repeated warm/open launch gates without changing Tor quality defaults."""

from __future__ import annotations

import argparse
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

from torfast.browser_startup_seed import DEFAULT_BROWSER_STARTUP_SEED_ROOT


DEFAULT_BROWSER_BIN = (
    REPO_ROOT
    / "tmp"
    / "browser"
    / "Tor Browser.app"
    / "Contents"
    / "MacOS"
    / "firefox"
)
DEFAULT_TOR_BIN = (
    REPO_ROOT
    / "tmp"
    / "browser"
    / "Tor Browser.app"
    / "Contents"
    / "MacOS"
    / "Tor"
    / "tor"
)
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "results"
DEFAULT_TARGETS = [
    "about:tor",
    "https://check.torproject.org/",
]
DEFAULT_PROFILES = [
    "auto",
    "tor_boot_100",
    "tor_boot_95",
    "tor_boot_90",
    "socks_ready",
]
PROFILE_CHOICES = tuple(DEFAULT_PROFILES)
LAUNCH_FIELDS = (
    "browser",
    "browser_launch_gate",
    "browser_launch_gate_requested",
    "browser_runtime_reset",
    "browser_startup_seed_apply",
    "browser_startup_seed_update",
    "dir_cache_seed_apply",
    "dir_cache_seed_update",
    "leave_tor_running",
    "port",
    "reused_tor_service",
    "tor_managed_ready",
    "tor_browser_launch_gate",
    "tor_boot",
    "torrc_quality",
    "url",
)


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.baseline_profile not in args.profiles:
        raise SystemExit("--baseline-profile must be included in --profiles")

    browser_bin = Path(args.browser_bin).resolve()
    tor_bin = Path(args.tor_bin).resolve()
    browser_startup_seed_root = Path(args.browser_startup_seed_root).resolve()
    output_root = Path(args.output_root).resolve()
    run_id = time.strftime("%Y%m%dT%H%M%S")
    output_dir = output_root / f"torfast-warm-open-compare-{run_id}"
    output_dir.mkdir(parents=True, exist_ok=True)

    if not browser_bin.exists():
        raise SystemExit(f"browser binary not found: {browser_bin}")
    if not tor_bin.exists():
        raise SystemExit(f"tor binary not found: {tor_bin}")

    results: list[dict[str, object]] = []
    port = args.port_base
    for target in args.targets:
        for cycle in range(1, args.cycles + 1):
            for profile_name in cycle_profile_order(cycle, args.profiles):
                result = run_target_profile_once(
                    target=target,
                    profile_name=profile_name,
                    cycle=cycle,
                    port=port,
                    browser_bin=browser_bin,
                    tor_bin=tor_bin,
                    browser_timeout=args.browser_timeout,
                    browser_startup_seed_root=browser_startup_seed_root,
                    browser_startup_seed_enabled=args.browser_startup_seed,
                    headed=args.headed,
                    keep_run_dir=args.keep_run_dirs,
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
        "profile_names": args.profiles,
        "baseline_profile": args.baseline_profile,
        "browser_timeout_seconds": args.browser_timeout,
        "browser_startup_seed_enabled": args.browser_startup_seed,
        "profiles": summarize_results(
            results,
            targets=args.targets,
            profile_names=args.profiles,
        ),
        "results": compact_results(results, targets=args.targets),
    }
    payload["delta_vs_baseline"] = delta_vs_baseline(
        payload["profiles"],
        targets=args.targets,
        profile_names=args.profiles,
        baseline_profile=args.baseline_profile,
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
        help="targets to measure with the warm/open workflow",
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
    parser.add_argument(
        "--browser-timeout",
        type=float,
        default=3.0,
        help="seconds to keep the headless browser open for each open run",
    )
    parser.add_argument(
        "--browser-startup-seed-root",
        default=str(DEFAULT_BROWSER_STARTUP_SEED_ROOT),
    )
    parser.add_argument(
        "--browser-startup-seed",
        action="store_true",
        help="opt in to the shared browser startup seed during open runs",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="show browser windows instead of using headless browser runs",
    )
    parser.add_argument("--port-base", type=int, default=20450)
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument(
        "--keep-run-dirs",
        action="store_true",
        help="keep per-run temp state directories under tmp/",
    )
    return parser


def cycle_profile_order(cycle: int, profiles: list[str]) -> list[str]:
    if not profiles:
        return []
    offset = (cycle - 1) % len(profiles)
    return profiles[offset:] + profiles[:offset]


def target_slug(target: str) -> str:
    return (
        target.replace("https://", "")
        .replace("http://", "")
        .replace("/", "_")
        .replace(":", "_")
    )


def run_target_profile_once(
    *,
    target: str,
    profile_name: str,
    cycle: int,
    port: int,
    browser_bin: Path,
    tor_bin: Path,
    browser_timeout: float,
    browser_startup_seed_root: Path,
    browser_startup_seed_enabled: bool,
    headed: bool,
    keep_run_dir: bool,
    output_dir: Path,
    run_id: str,
) -> dict[str, object]:
    run_dir = (
        REPO_ROOT
        / "tmp"
        / f"torfast-warm-open-{run_id}-{target_slug(target)}-{profile_name}-cycle{cycle}"
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
        profile_name=profile_name,
        browser_timeout=browser_timeout,
        browser_startup_seed_root=browser_startup_seed_root,
        browser_startup_seed_enabled=browser_startup_seed_enabled,
        headed=headed,
    )
    warm_run = run_command(warm_command)
    warm_launch = read_json_file(state_root / "launch.json")
    result["warm"] = warm_run
    result["warm_launch"] = compact_launch(warm_launch)

    open_launch: dict[str, object] | None = None
    if warm_run.get("ok"):
        open_command = build_torfast_command(
            action="open",
            state_root=state_root,
            browser_bin=browser_bin,
            tor_bin=tor_bin,
            target=target,
            port=port,
            profile_name=profile_name,
            browser_timeout=browser_timeout,
            browser_startup_seed_root=browser_startup_seed_root,
            browser_startup_seed_enabled=browser_startup_seed_enabled,
            headed=headed,
        )
        open_run = run_command(open_command)
        open_launch = read_json_file(state_root / "launch.json")
    else:
        open_run = {
            "ok": False,
            "skipped": True,
            "exit_code": None,
            "wall_seconds": None,
            "stdout_tail": [],
            "stderr_tail": [],
        }
    result["open"] = open_run
    result["open_launch"] = compact_launch(open_launch)

    stop_command = build_stop_command(state_root)
    stop_run = run_command(stop_command)
    stop_payload = parse_json_text(
        "\n".join(str(line) for line in stop_run.get("stdout_tail", []))
    )
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


def build_torfast_command(
    *,
    action: str,
    state_root: Path,
    browser_bin: Path,
    tor_bin: Path,
    target: str,
    port: int,
    profile_name: str,
    browser_timeout: float,
    browser_startup_seed_root: Path,
    browser_startup_seed_enabled: bool,
    headed: bool,
) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "torfast",
        action,
        "--browser-bin",
        str(browser_bin),
        "--tor-bin",
        str(tor_bin),
        "--url",
        target,
        "--port",
        str(port),
        "--state-root",
        str(state_root),
        "--browser-startup-seed-root",
        str(browser_startup_seed_root),
    ]
    if profile_name != "auto":
        command.extend(["--browser-launch-gate", profile_name])
    if browser_startup_seed_enabled:
        command.append("--browser-startup-seed")
    else:
        command.append("--no-browser-startup-seed")
    if action == "open":
        command.extend(["--browser-timeout", str(browser_timeout)])
        if not headed:
            command.append("--headless")
    return command


def build_stop_command(state_root: Path) -> list[str]:
    return [
        sys.executable,
        "-m",
        "torfast",
        "stop",
        "--state-root",
        str(state_root),
    ]


def run_command(command: list[str]) -> dict[str, object]:
    started = time.monotonic()
    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    return {
        "command": command,
        "ok": completed.returncode == 0,
        "exit_code": completed.returncode,
        "wall_seconds": round(time.monotonic() - started, 3),
        "stdout_tail": completed.stdout.splitlines()[-80:],
        "stderr_tail": completed.stderr.splitlines()[-80:],
    }


def read_json_file(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def parse_json_text(text: str) -> dict[str, object] | None:
    if not text.strip():
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def compact_launch(launch: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(launch, dict):
        return None
    return {
        key: launch.get(key)
        for key in LAUNCH_FIELDS
        if key in launch
    }


def result_ok(result: dict[str, object]) -> bool:
    warm = result.get("warm")
    warm_launch = result.get("warm_launch")
    open_run = result.get("open")
    open_launch = result.get("open_launch")
    stop = result.get("stop")

    if not isinstance(warm, dict) or warm.get("ok") is not True:
        return False
    if (
        not isinstance(warm_launch, dict)
        or not isinstance(warm_launch.get("tor_managed_ready"), dict)
        or warm_launch["tor_managed_ready"].get("ok") is not True
    ):
        return False
    if not isinstance(open_run, dict) or open_run.get("ok") is not True:
        return False
    if not isinstance(open_launch, dict):
        return False
    browser = open_launch.get("browser")
    tor_boot = open_launch.get("tor_boot")
    torrc = open_launch.get("torrc_quality")
    reused = open_launch.get("reused_tor_service")
    if not isinstance(browser, dict) or browser.get("ok") is not True:
        return False
    if not isinstance(tor_boot, dict) or tor_boot.get("ok") is not True:
        return False
    if not isinstance(torrc, dict) or torrc.get("isolate_socks_auth") is not True:
        return False
    if not isinstance(reused, dict):
        return False
    if not isinstance(stop, dict) or stop.get("ok") is not True:
        return False
    return True


def warm_ready_gate(result: dict[str, object]) -> str | None:
    warm_launch = result.get("warm_launch")
    if not isinstance(warm_launch, dict):
        return None
    ready = warm_launch.get("tor_managed_ready")
    if not isinstance(ready, dict):
        return None
    gate = ready.get("gate")
    return str(gate) if isinstance(gate, str) else None


def warm_ready_seconds(result: dict[str, object]) -> float | None:
    warm_launch = result.get("warm_launch")
    if not isinstance(warm_launch, dict):
        return None
    ready = warm_launch.get("tor_managed_ready")
    if not isinstance(ready, dict):
        return None
    seconds = ready.get("seconds")
    if not isinstance(seconds, (int, float)):
        return None
    return round(float(seconds), 3)


def open_launch_gate_name(result: dict[str, object]) -> str | None:
    open_launch = result.get("open_launch")
    if not isinstance(open_launch, dict):
        return None
    gate = open_launch.get("browser_launch_gate")
    return str(gate) if isinstance(gate, str) else None


def open_launch_gate_seconds(result: dict[str, object]) -> float | None:
    open_launch = result.get("open_launch")
    if not isinstance(open_launch, dict):
        return None
    launch_gate = open_launch.get("tor_browser_launch_gate")
    if isinstance(launch_gate, dict) and isinstance(
        launch_gate.get("seconds"), (int, float)
    ):
        return round(float(launch_gate["seconds"]), 3)
    tor_boot = open_launch.get("tor_boot")
    if isinstance(tor_boot, dict) and isinstance(tor_boot.get("seconds"), (int, float)):
        return round(float(tor_boot["seconds"]), 3)
    return None


def open_full_boot_seconds(result: dict[str, object]) -> float | None:
    open_launch = result.get("open_launch")
    if not isinstance(open_launch, dict):
        return None
    tor_boot = open_launch.get("tor_boot")
    if not isinstance(tor_boot, dict):
        return None
    seconds = tor_boot.get("seconds")
    if not isinstance(seconds, (int, float)):
        return None
    return round(float(seconds), 3)


def open_browser_elapsed_seconds(result: dict[str, object]) -> float | None:
    open_launch = result.get("open_launch")
    if not isinstance(open_launch, dict):
        return None
    browser = open_launch.get("browser")
    if not isinstance(browser, dict):
        return None
    seconds = browser.get("elapsed_seconds")
    if not isinstance(seconds, (int, float)):
        return None
    return round(float(seconds), 3)


def combined_wall_seconds(result: dict[str, object]) -> float | None:
    warm = result.get("warm")
    open_run = result.get("open")
    if not isinstance(warm, dict) or not isinstance(open_run, dict):
        return None
    warm_seconds = warm.get("wall_seconds")
    open_seconds = open_run.get("wall_seconds")
    if not isinstance(warm_seconds, (int, float)) or not isinstance(
        open_seconds, (int, float)
    ):
        return None
    return round(float(warm_seconds) + float(open_seconds), 3)


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
            target_profiles[profile_name] = {
                "runs": len(rows),
                "ok_runs": len(ok_rows),
                "median_warm_wall_seconds": median_value(
                    [
                        (result.get("warm") or {}).get("wall_seconds")
                        for result in ok_rows
                    ]
                ),
                "median_warm_ready_seconds": median_value(
                    [warm_ready_seconds(result) for result in ok_rows]
                ),
                "median_open_wall_seconds": median_value(
                    [
                        (result.get("open") or {}).get("wall_seconds")
                        for result in ok_rows
                    ]
                ),
                "median_open_browser_elapsed_seconds": median_value(
                    [open_browser_elapsed_seconds(result) for result in ok_rows]
                ),
                "median_open_launch_gate_seconds": median_value(
                    [open_launch_gate_seconds(result) for result in ok_rows]
                ),
                "median_open_full_boot_seconds": median_value(
                    [open_full_boot_seconds(result) for result in ok_rows]
                ),
                "median_combined_wall_seconds": median_value(
                    [combined_wall_seconds(result) for result in ok_rows]
                ),
                "warm_ready_ok_runs": sum(
                    1
                    for result in rows
                    if isinstance(
                        (ready := (result.get("warm_launch") or {}).get("tor_managed_ready")),
                        dict,
                    )
                    and ready.get("ok") is True
                ),
                "open_browser_ok_runs": sum(
                    1
                    for result in rows
                    if isinstance(
                        (browser := (result.get("open_launch") or {}).get("browser")),
                        dict,
                    )
                    and browser.get("ok") is True
                ),
                "open_tor_boot_ok_runs": sum(
                    1
                    for result in rows
                    if isinstance(
                        (tor_boot := (result.get("open_launch") or {}).get("tor_boot")),
                        dict,
                    )
                    and tor_boot.get("ok") is True
                ),
                "torrc_isolate_socks_auth_ok_runs": sum(
                    1
                    for result in rows
                    if isinstance(
                        (torrc := (result.get("open_launch") or {}).get("torrc_quality")),
                        dict,
                    )
                    and torrc.get("isolate_socks_auth") is True
                ),
                "reused_service_ok_runs": sum(
                    1
                    for result in rows
                    if isinstance(
                        (reused := (result.get("open_launch") or {}).get("reused_tor_service")),
                        dict,
                    )
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
                "open_wall_seconds": subtract_metric(
                    candidate.get("median_open_wall_seconds"),
                    baseline.get("median_open_wall_seconds"),
                ),
                "open_browser_elapsed_seconds": subtract_metric(
                    candidate.get("median_open_browser_elapsed_seconds"),
                    baseline.get("median_open_browser_elapsed_seconds"),
                ),
                "open_launch_gate_seconds": subtract_metric(
                    candidate.get("median_open_launch_gate_seconds"),
                    baseline.get("median_open_launch_gate_seconds"),
                ),
                "open_full_boot_seconds": subtract_metric(
                    candidate.get("median_open_full_boot_seconds"),
                    baseline.get("median_open_full_boot_seconds"),
                ),
                "combined_wall_seconds": subtract_metric(
                    candidate.get("median_combined_wall_seconds"),
                    baseline.get("median_combined_wall_seconds"),
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
                "warm_wall_seconds": (result.get("warm") or {}).get("wall_seconds"),
                "warm_ready_gate": warm_ready_gate(result),
                "warm_ready_seconds": warm_ready_seconds(result),
                "open_wall_seconds": (result.get("open") or {}).get("wall_seconds"),
                "open_launch_gate": open_launch_gate_name(result),
                "open_launch_gate_seconds": open_launch_gate_seconds(result),
                "open_full_boot_seconds": open_full_boot_seconds(result),
                "open_browser_elapsed_seconds": open_browser_elapsed_seconds(result),
                "combined_wall_seconds": combined_wall_seconds(result),
                "torrc_isolate_socks_auth": (
                    ((result.get("open_launch") or {}).get("torrc_quality") or {}).get(
                        "isolate_socks_auth"
                    )
                ),
                "open_tor_boot_ok": (
                    ((result.get("open_launch") or {}).get("tor_boot") or {}).get("ok")
                ),
                "stop_ok": ((result.get("stop") or {}).get("ok")),
                "ok": result_ok(result),
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
        if result.get("target") not in targets:
            return False
        if not result_ok(result):
            return False
    return True


if __name__ == "__main__":
    raise SystemExit(main())
