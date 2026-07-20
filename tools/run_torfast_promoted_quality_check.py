#!/usr/bin/env python3
"""Verify the promoted torfast profile keeps Tor-quality invariants while faster."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import time
from urllib.parse import urlparse


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from check_c_tor_circuits import run_check as run_c_tor_circuit_check
from check_c_tor_circuits import short_summary as c_tor_circuit_short_summary
from run_browser_compare import (
    collect_no_marionette_fingerprint_snapshot,
    stable_fingerprint_reference_failures,
    validate_browser_fingerprint_snapshot,
    validate_browser_quality_prefs,
)
from torfast.browser_startup_seed import DEFAULT_BROWSER_STARTUP_SEED_ROOT
from torfast.control import user_stream_snapshot_observed


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
DEFAULT_TARGETS = ["https://check.torproject.org/"]
BROADER_TARGETS = [
    "https://check.torproject.org/",
    "https://www.torproject.org/",
    "https://www.torproject.org/download/",
]
TARGET_PACKS = {
    "focused": DEFAULT_TARGETS,
    "broader": BROADER_TARGETS,
}
PROFILE_SPECS = (
    {
        "name": "auto",
        "managed_open_adaptive_general_circuit_wait_timeout_seconds": 0.0,
    },
    {
        "name": "auto_managedadaptivegencirc_0p126s",
        "managed_open_adaptive_general_circuit_wait_timeout_seconds": 0.126,
    },
)
TARGET_STREAM_PROOF_ENABLED_ENV = "TORFAST_ENABLE_TARGET_STREAM_PROOF"
BROWSER_RUNTIME_QUALITY_PROOF_ENABLED_ENV = (
    "TORFAST_ENABLE_BROWSER_RUNTIME_QUALITY_PROOF"
)
# Keys that track the window environment (which display backs the headless
# window, live window geometry, page cookie state) rather than the browser
# configuration. Saved runs show these jitter between otherwise identical
# launches, e.g. devicePixelRatio flipping 1 -> 2 with screen/avail following
# the window size, so they stay out of the pairwise equality proof.
PAIRWISE_IGNORED_FINGERPRINT_KEYS = frozenset(
    {
        "innerWidth",
        "innerHeight",
        "outerWidth",
        "outerHeight",
        "screenWidth",
        "screenHeight",
        "availWidth",
        "availHeight",
        "devicePixelRatio",
        "cookieEnabled",
    }
)
# Product-path RFP liveness signature: with TZ=UTC alone the browser reports
# Atlantic/Reykjavik, so an exact "UTC" can only come from the
# resistFingerprinting timezone spoof being active for content.
RFP_SPOOFED_TIMEZONE = "UTC"
# Speed gate: the candidate must beat baseline on the launch-controlled
# metric (median open browser elapsed) on every target, and must not regress
# the end-to-end combined wall beyond a noise-scaled guard on any target.
# Combined wall includes delivering the requested page over a random Tor
# circuit; measured same-config per-run stdev is ~4-7s, so the guard scales
# with the baseline's own spread instead of gating on a fixed sub-noise
# threshold.
COMBINED_WALL_REGRESSION_GUARD_FLOOR_SECONDS = 1.0
COMBINED_WALL_REGRESSION_GUARD_NOISE_FACTOR = 0.75


def combined_wall_regression_guard_seconds(
    baseline_summary: dict[str, object] | None,
) -> float:
    guard = COMBINED_WALL_REGRESSION_GUARD_FLOOR_SECONDS
    if isinstance(baseline_summary, dict):
        stdev = baseline_summary.get("stdev_combined_wall_seconds")
        if isinstance(stdev, (int, float)):
            guard = max(
                guard,
                COMBINED_WALL_REGRESSION_GUARD_NOISE_FACTOR * float(stdev),
            )
    return round(guard, 3)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--browser-bin", default=str(DEFAULT_BROWSER_BIN))
    parser.add_argument("--tor-bin", default=str(DEFAULT_TOR_BIN))
    parser.add_argument(
        "--browser-startup-seed-root",
        default=str(DEFAULT_BROWSER_STARTUP_SEED_ROOT),
    )
    parser.add_argument("--cycles", type=int, default=1)
    parser.add_argument("--browser-timeout", type=float, default=3.0)
    parser.add_argument("--stream-isolation-probe-timeout", type=float, default=3.0)
    parser.add_argument("--window-size", default="1000,1000")
    parser.add_argument(
        "--target-pack",
        choices=sorted(TARGET_PACKS),
        default="focused",
    )
    parser.add_argument("--targets", nargs="*", default=None)
    parser.add_argument("--port-base", type=int, default=20760)
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument(
        "--skip-c-tor-circuit-check",
        action="store_true",
        help="skip the separate C Tor circuit-quality support check",
    )
    parser.add_argument(
        "--c-tor-circuit-check-all-targets",
        action="store_true",
        help="run the separate C Tor circuit-quality support check for every target",
    )
    parser.add_argument(
        "--c-tor-circuit-check-socks-port",
        type=int,
        default=20860,
    )
    parser.add_argument(
        "--c-tor-circuit-check-control-port",
        type=int,
        default=20861,
    )
    return parser


def resolve_targets(target_pack: str, explicit_targets: list[str] | None) -> list[str]:
    if explicit_targets is not None:
        return [target for target in explicit_targets if target]
    return list(TARGET_PACKS[target_pack])


def target_slug(target: str) -> str:
    parsed = urlparse(target)
    if parsed.scheme == "about":
        return parsed.path.replace(":", "_") or "about"
    host = parsed.netloc or parsed.path or "target"
    path = parsed.path.strip("/").replace("/", "_")
    suffix = f"_{path}" if path else ""
    return f"{host}{suffix}".replace(":", "_")


def copy_json_file(source: Path, destination: Path) -> dict[str, object] | None:
    if not source.exists():
        return None
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return json.loads(destination.read_text())


def output_tail(text: str, *, limit: int = 80) -> list[str]:
    return [line.rstrip() for line in text.splitlines()[-limit:]]


def parse_stdout_json(stdout_text: str) -> dict[str, object] | None:
    start = stdout_text.find("{")
    if start < 0:
        return None
    try:
        payload = json.loads(stdout_text[start:])
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def run_command(
    *,
    command: list[str],
    env: dict[str, str],
    stdout_path: Path,
) -> dict[str, object]:
    started = time.monotonic()
    proc = subprocess.run(
        command,
        cwd=str(REPO_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    wall_seconds = round(time.monotonic() - started, 3)
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stdout_path.write_text(proc.stdout)
    return {
        "command": command,
        "exit_code": proc.returncode,
        "ok": proc.returncode == 0,
        "wall_seconds": wall_seconds,
        "stdout_path": str(stdout_path),
        "stdout_tail": output_tail(proc.stdout),
        "stdout_json": parse_stdout_json(proc.stdout),
    }


def managed_open_wait_args(timeout_seconds: float) -> list[str]:
    # Always pass the value explicitly so the baseline row stays a true 0.0
    # even when the product default promotes a non-zero wait.
    return [
        "--managed-open-adaptive-general-circuit-wait-timeout",
        str(timeout_seconds),
    ]


def target_stream_snapshot_from_open_launch(
    open_launch: dict[str, object] | None,
) -> dict[str, object] | None:
    if not isinstance(open_launch, dict):
        return None
    browser = open_launch.get("browser")
    if isinstance(browser, dict):
        snapshot = browser.get("target_stream_snapshot")
        if isinstance(snapshot, dict):
            return snapshot
    adaptive_wait = open_launch.get("managed_open_adaptive_general_circuit_wait")
    if isinstance(adaptive_wait, dict):
        browser_launch_gate_wait = adaptive_wait.get("browser_launch_gate_wait")
        if isinstance(browser_launch_gate_wait, dict):
            snapshot = browser_launch_gate_wait.get("target_stream_snapshot")
            if isinstance(snapshot, dict):
                return snapshot
        snapshot = adaptive_wait.get("target_stream_snapshot")
        if isinstance(snapshot, dict):
            return snapshot
    return None


def path_lengths_are_three_hop(snapshot: dict[str, object] | None) -> bool:
    if not isinstance(snapshot, dict):
        return False
    counts = snapshot.get("matched_circuit_path_length_counts")
    if not isinstance(counts, dict) or not counts:
        return False
    saw_positive = False
    for raw_length, raw_count in counts.items():
        try:
            length = int(raw_length)
        except (TypeError, ValueError):
            return False
        if length != 3:
            return False
        if isinstance(raw_count, int) and raw_count > 0:
            saw_positive = True
    return saw_positive


def path_lengths_do_not_contradict_three_hop(
    snapshot: dict[str, object] | None,
) -> bool:
    if not isinstance(snapshot, dict):
        return True
    counts = snapshot.get("matched_circuit_path_length_counts")
    if not isinstance(counts, dict) or not counts:
        return True
    for raw_length in counts:
        try:
            if int(raw_length) != 3:
                return False
        except (TypeError, ValueError):
            return False
    return True


def validate_open_launch_quality(
    open_launch: dict[str, object] | None,
    *,
    allow_webdriver_artifact: bool,
    reference_fingerprint_snapshot: dict[str, object] | None = None,
) -> dict[str, object]:
    if not isinstance(open_launch, dict):
        return {
            "ok": False,
            "failures": ["open launch payload missing"],
        }
    target_stream_snapshot = target_stream_snapshot_from_open_launch(open_launch)
    browser_default_pref_check = open_launch.get("browser_default_pref_check")
    browser_runtime_reset = open_launch.get("browser_runtime_reset")
    torrc_quality = open_launch.get("torrc_quality")
    browser_stream_isolation_probe = open_launch.get(
        "browser_stream_isolation_probe"
    )
    browser_runtime_quality_proof = open_launch.get(
        "browser_runtime_quality_proof"
    )
    effective_proxy_prefs = open_launch.get("effective_proxy_prefs")
    browser_quality_prefs = open_launch.get("browser_quality_prefs")
    browser_fingerprint_snapshot = open_launch.get("browser_fingerprint_snapshot")
    browser_quality_pref_check = validate_browser_quality_prefs(
        browser_quality_prefs if isinstance(browser_quality_prefs, dict) else {}
    )
    browser_fingerprint_validation = validate_browser_fingerprint_snapshot(
        browser_fingerprint_snapshot
        if isinstance(browser_fingerprint_snapshot, dict)
        else {},
        allow_webdriver_artifact=allow_webdriver_artifact,
        require_rfp_behaviors=True,
    )
    fingerprint_values = (
        browser_fingerprint_snapshot.get("snapshot")
        if isinstance(browser_fingerprint_snapshot, dict)
        else None
    )
    stable_reference_failures = (
        stable_fingerprint_reference_failures(
            fingerprint_values if isinstance(fingerprint_values, dict) else None,
            reference_fingerprint_snapshot,
        )
        if reference_fingerprint_snapshot is not None
        else []
    )
    checks = {
        "browser_default_pref_check_ok": (
            isinstance(browser_default_pref_check, dict)
            and browser_default_pref_check.get("ok") is True
        ),
        "browser_runtime_reset_ok": (
            isinstance(browser_runtime_reset, dict)
            and browser_runtime_reset.get("ok") is True
        ),
        "torrc_isolate_socks_auth": (
            isinstance(torrc_quality, dict)
            and torrc_quality.get("isolate_socks_auth") is True
        ),
        "browser_runtime_quality_proof_enabled": (
            isinstance(browser_runtime_quality_proof, dict)
            and browser_runtime_quality_proof.get("enabled") is True
        ),
        "effective_proxy_prefs_ok": (
            isinstance(effective_proxy_prefs, dict)
            and effective_proxy_prefs.get("network.proxy.socks") == "127.0.0.1"
            and effective_proxy_prefs.get("network.proxy.socks_port")
            == open_launch.get("port")
            and effective_proxy_prefs.get("network.proxy.socks_remote_dns") is True
            and effective_proxy_prefs.get("network.proxy.type") == 1
        ),
        "browser_stream_isolation_probe_ok": (
            isinstance(browser_stream_isolation_probe, dict)
            and browser_stream_isolation_probe.get("ok") is True
            and isinstance(
                browser_stream_isolation_probe.get("observed_stream_count"),
                int,
            )
            and browser_stream_isolation_probe["observed_stream_count"] >= 1
        ),
        "target_navigation_proven": user_stream_snapshot_observed(
            target_stream_snapshot
        ),
        "target_stream_three_hop_proven": path_lengths_are_three_hop(
            target_stream_snapshot
        ),
        "target_stream_three_hop_if_known_ok": (
            path_lengths_do_not_contradict_three_hop(target_stream_snapshot)
        ),
        "browser_quality_pref_check_ok": (
            browser_quality_pref_check.get("ok") is True
        ),
        "browser_fingerprint_validation_ok": (
            browser_fingerprint_validation.get("ok") is True
        ),
        "browser_rfp_timezone_spoof_ok": (
            isinstance(fingerprint_values, dict)
            and fingerprint_values.get("timezone") == RFP_SPOOFED_TIMEZONE
        ),
        "browser_fingerprint_page_is_target_ok": (
            isinstance(fingerprint_values, dict)
            and isinstance(open_launch.get("url"), str)
            and fingerprint_values.get("pageUrl") == open_launch.get("url")
        ),
        "stable_fingerprint_matches_reference_ok": (
            reference_fingerprint_snapshot is None
            or not stable_reference_failures
        ),
    }
    failures: list[str] = []
    blocking_keys = {
        "browser_default_pref_check_ok",
        "browser_runtime_reset_ok",
        "torrc_isolate_socks_auth",
        "browser_runtime_quality_proof_enabled",
        "effective_proxy_prefs_ok",
        "browser_stream_isolation_probe_ok",
        "target_navigation_proven",
        "target_stream_three_hop_if_known_ok",
        "browser_quality_pref_check_ok",
        "browser_fingerprint_validation_ok",
        "browser_rfp_timezone_spoof_ok",
        "browser_fingerprint_page_is_target_ok",
        "stable_fingerprint_matches_reference_ok",
    }
    for key, passed in checks.items():
        if key not in blocking_keys:
            continue
        if passed:
            continue
        failures.append(key)
    return {
        **checks,
        "browser_quality_pref_check": browser_quality_pref_check,
        "browser_fingerprint_validation": browser_fingerprint_validation,
        "stable_fingerprint_reference_failures": stable_reference_failures,
        "target_stream_snapshot": target_stream_snapshot,
        "browser_stream_isolation_probe": browser_stream_isolation_probe,
        "ok": not failures,
        "failures": failures,
    }


def pairwise_quality_failures(
    baseline_open_launch: dict[str, object] | None,
    candidate_open_launch: dict[str, object] | None,
) -> list[str]:
    failures: list[str] = []
    if not isinstance(baseline_open_launch, dict) or not isinstance(
        candidate_open_launch, dict
    ):
        return ["missing open launch for pairwise comparison"]
    baseline_quality_prefs = (
        (baseline_open_launch.get("browser_quality_prefs") or {}).get("prefs")
    )
    candidate_quality_prefs = (
        (candidate_open_launch.get("browser_quality_prefs") or {}).get("prefs")
    )
    if baseline_quality_prefs != candidate_quality_prefs:
        failures.append("browser_quality_prefs_mismatch")
    baseline_fingerprint = (
        (baseline_open_launch.get("browser_fingerprint_snapshot") or {}).get(
            "snapshot"
        )
    )
    candidate_fingerprint = (
        (candidate_open_launch.get("browser_fingerprint_snapshot") or {}).get(
            "snapshot"
        )
    )
    if isinstance(baseline_fingerprint, dict) and isinstance(candidate_fingerprint, dict):
        baseline_fingerprint = {
            key: value
            for key, value in baseline_fingerprint.items()
            if key not in PAIRWISE_IGNORED_FINGERPRINT_KEYS
        }
        candidate_fingerprint = {
            key: value
            for key, value in candidate_fingerprint.items()
            if key not in PAIRWISE_IGNORED_FINGERPRINT_KEYS
        }
    if baseline_fingerprint != candidate_fingerprint:
        failures.append("browser_fingerprint_snapshot_mismatch")
    baseline_probe = baseline_open_launch.get("browser_stream_isolation_probe") or {}
    candidate_probe = candidate_open_launch.get("browser_stream_isolation_probe") or {}
    if baseline_probe.get("iso_fields") != candidate_probe.get("iso_fields"):
        failures.append("browser_stream_isolation_iso_fields_mismatch")
    baseline_target_stream = target_stream_snapshot_from_open_launch(
        baseline_open_launch
    ) or {}
    candidate_target_stream = target_stream_snapshot_from_open_launch(
        candidate_open_launch
    ) or {}
    if baseline_target_stream.get("iso_fields") != candidate_target_stream.get(
        "iso_fields"
    ):
        failures.append("target_stream_iso_fields_mismatch")
    return failures


def numeric_values(values: list[object]) -> list[float]:
    return [float(value) for value in values if isinstance(value, (int, float))]


def median_value(values: list[object]) -> float | None:
    numeric = numeric_values(values)
    if not numeric:
        return None
    return round(statistics.median(numeric), 3)


def stdev_value(values: list[object]) -> float | None:
    numeric = numeric_values(values)
    if len(numeric) < 2:
        return None
    return round(statistics.stdev(numeric), 3)


def summarize_profile_target_runs(
    rows: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "runs": len(rows),
        "quality_ok_runs": sum(
            1
            for row in rows
            if isinstance((quality := row.get("quality")), dict)
            and quality.get("ok") is True
        ),
        "target_navigation_proven_runs": sum(
            1
            for row in rows
            if isinstance((quality := row.get("quality")), dict)
            and quality.get("target_navigation_proven") is True
        ),
        "browser_quality_pref_check_ok_runs": sum(
            1
            for row in rows
            if isinstance((quality := row.get("quality")), dict)
            and quality.get("browser_quality_pref_check_ok") is True
        ),
        "browser_fingerprint_validation_ok_runs": sum(
            1
            for row in rows
            if isinstance((quality := row.get("quality")), dict)
            and quality.get("browser_fingerprint_validation_ok") is True
        ),
        "browser_stream_isolation_probe_ok_runs": sum(
            1
            for row in rows
            if isinstance((quality := row.get("quality")), dict)
            and quality.get("browser_stream_isolation_probe_ok") is True
        ),
        "torrc_isolate_socks_auth_ok_runs": sum(
            1
            for row in rows
            if isinstance((quality := row.get("quality")), dict)
            and quality.get("torrc_isolate_socks_auth") is True
        ),
        "median_combined_wall_seconds": median_value(
            [row.get("combined_wall_seconds") for row in rows]
        ),
        "stdev_combined_wall_seconds": stdev_value(
            [row.get("combined_wall_seconds") for row in rows]
        ),
        "median_open_browser_elapsed_seconds": median_value(
            [
                (
                    ((row.get("open_launch") or {}).get("browser") or {}).get(
                        "elapsed_seconds"
                    )
                )
                for row in rows
            ]
        ),
    }


def summarize_results(
    results: list[dict[str, object]],
    *,
    targets: list[str],
) -> dict[str, object]:
    profiles: dict[str, object] = {}
    for target in targets:
        profiles[target] = {}
        for spec in PROFILE_SPECS:
            profile_name = str(spec["name"])
            rows = [
                row
                for row in results
                if row.get("target") == target and row.get("profile_name") == profile_name
            ]
            profiles[target][profile_name] = summarize_profile_target_runs(rows)
    return profiles


def delta_vs_baseline(
    profiles: dict[str, object],
    *,
    targets: list[str],
    baseline_profile: str,
    candidate_profile: str,
) -> dict[str, object]:
    deltas: dict[str, object] = {}
    for target in targets:
        target_profiles = profiles.get(target)
        if not isinstance(target_profiles, dict):
            continue
        baseline = target_profiles.get(baseline_profile)
        candidate = target_profiles.get(candidate_profile)
        if not isinstance(baseline, dict) or not isinstance(candidate, dict):
            continue
        baseline_combined = baseline.get("median_combined_wall_seconds")
        candidate_combined = candidate.get("median_combined_wall_seconds")
        baseline_elapsed = baseline.get("median_open_browser_elapsed_seconds")
        candidate_elapsed = candidate.get("median_open_browser_elapsed_seconds")
        deltas[target] = {
            "combined_wall_seconds": (
                round(float(candidate_combined) - float(baseline_combined), 3)
                if isinstance(candidate_combined, (int, float))
                and isinstance(baseline_combined, (int, float))
                else None
            ),
            "open_browser_elapsed_seconds": (
                round(float(candidate_elapsed) - float(baseline_elapsed), 3)
                if isinstance(candidate_elapsed, (int, float))
                and isinstance(baseline_elapsed, (int, float))
                else None
            ),
        }
    return deltas


def run_profile_target_cycle(
    *,
    browser_bin: Path,
    tor_bin: Path,
    browser_startup_seed_root: Path,
    output_dir: Path,
    target: str,
    cycle: int,
    profile_spec: dict[str, object],
    port: int,
    browser_timeout: float,
    stream_isolation_probe_timeout: float,
    reference_fingerprint_snapshot: dict[str, object] | None = None,
) -> dict[str, object]:
    profile_name = str(profile_spec["name"])
    run_dir = output_dir / target_slug(target) / profile_name / f"run-{cycle}"
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    state_root = run_dir / "state"
    env = os.environ.copy()
    env[TARGET_STREAM_PROOF_ENABLED_ENV] = "1"
    env[BROWSER_RUNTIME_QUALITY_PROOF_ENABLED_ENV] = "1"
    common_args = [
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
        "--no-browser-startup-seed",
        "--managed-open-browser-overlap",
        "--no-managed-open-settle",
        "--stream-isolation-probe",
        "--stream-isolation-probe-timeout",
        str(stream_isolation_probe_timeout),
        *managed_open_wait_args(
            float(
                profile_spec.get(
                    "managed_open_adaptive_general_circuit_wait_timeout_seconds",
                    0.0,
                )
            )
        ),
    ]
    warm = run_command(
        command=[sys.executable, "-m", "torfast", "warm", *common_args],
        env=env,
        stdout_path=run_dir / "warm.stdout.txt",
    )
    warm_launch = copy_json_file(
        state_root / "launch.json",
        run_dir / "warm-launch.json",
    )
    open_run = run_command(
        command=[
            sys.executable,
            "-m",
            "torfast",
            "open",
            *common_args,
            "--browser-timeout",
            str(browser_timeout),
            "--headless",
        ],
        env=env,
        stdout_path=run_dir / "open.stdout.txt",
    )
    open_launch = copy_json_file(
        state_root / "launch.json",
        run_dir / "open-launch.json",
    )
    stop = run_command(
        command=[
            sys.executable,
            "-m",
            "torfast",
            "stop",
            "--browser-bin",
            str(browser_bin),
            "--tor-bin",
            str(tor_bin),
            "--port",
            str(port),
            "--state-root",
            str(state_root),
        ],
        env=env,
        stdout_path=run_dir / "stop.stdout.txt",
    )
    quality = validate_open_launch_quality(
        open_launch,
        allow_webdriver_artifact=True,
        reference_fingerprint_snapshot=reference_fingerprint_snapshot,
    )
    combined_wall_seconds = None
    if isinstance(warm.get("wall_seconds"), (int, float)) and isinstance(
        open_run.get("wall_seconds"), (int, float)
    ):
        combined_wall_seconds = round(
            float(warm["wall_seconds"]) + float(open_run["wall_seconds"]),
            3,
        )
    result = {
        "target": target,
        "profile_name": profile_name,
        "cycle": cycle,
        "port": port,
        "run_dir": str(run_dir),
        "state_root": str(state_root),
        "warm": warm,
        "warm_launch": warm_launch,
        "open": open_run,
        "open_launch": open_launch,
        "stop": stop,
        "combined_wall_seconds": combined_wall_seconds,
        "quality": quality,
    }
    (run_dir / "run-summary.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )
    return result


def result_quality_ok(result: dict[str, object]) -> bool:
    quality = result.get("quality")
    warm = result.get("warm")
    open_run = result.get("open")
    stop = result.get("stop")
    return (
        isinstance(quality, dict)
        and quality.get("ok") is True
        and isinstance(warm, dict)
        and warm.get("ok") is True
        and isinstance(open_run, dict)
        and open_run.get("ok") is True
        and isinstance(stop, dict)
        and stop.get("ok") is True
    )


def payload_ok(payload: dict[str, object]) -> bool:
    if (
        not isinstance(
            (proof := payload.get("no_marionette_fingerprint_proof")),
            dict,
        )
        or proof.get("ok") is not True
        or not isinstance((validation := proof.get("validation")), dict)
        or validation.get("ok") is not True
    ):
        return False
    circuit_checks = payload.get("c_tor_circuit_checks")
    if isinstance(circuit_checks, dict):
        for target, circuit_check in circuit_checks.items():
            if not isinstance(target, str) or not isinstance(circuit_check, dict):
                return False
            if circuit_check.get("skipped") is True:
                continue
            if circuit_check.get("ok") is not True:
                return False
    else:
        circuit_check = payload.get("c_tor_circuit_check")
        if isinstance(circuit_check, dict) and circuit_check.get("skipped") is not True:
            if circuit_check.get("ok") is not True:
                return False
    for row in payload.get("results", []):
        if not isinstance(row, dict) or not result_quality_ok(row):
            return False
    for row in payload.get("pairwise_consistency", []):
        if not isinstance(row, dict) or row.get("ok") is not True:
            return False
    deltas = payload.get("delta_vs_baseline")
    if not isinstance(deltas, dict):
        return False
    profiles = payload.get("profiles")
    profiles = profiles if isinstance(profiles, dict) else {}
    profile_names = payload.get("profile_names")
    baseline_profile_name = (
        profile_names[0]
        if isinstance(profile_names, list) and profile_names
        else None
    )
    for target in payload.get("targets", []):
        target_delta = deltas.get(target)
        if not isinstance(target_delta, dict):
            return False
        target_profiles = profiles.get(target)
        baseline_summary = (
            target_profiles.get(baseline_profile_name)
            if isinstance(target_profiles, dict)
            and isinstance(baseline_profile_name, str)
            else None
        )
        guard = combined_wall_regression_guard_seconds(
            baseline_summary if isinstance(baseline_summary, dict) else None
        )
        combined_delta = target_delta.get("combined_wall_seconds")
        if not isinstance(combined_delta, (int, float)) or combined_delta > guard:
            return False
        open_elapsed_delta = target_delta.get("open_browser_elapsed_seconds")
        if (
            not isinstance(open_elapsed_delta, (int, float))
            or open_elapsed_delta >= 0
        ):
            return False
    return True


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if args.cycles < 1:
        raise SystemExit("--cycles must be at least 1")
    browser_bin = Path(args.browser_bin).resolve()
    tor_bin = Path(args.tor_bin).resolve()
    browser_startup_seed_root = Path(args.browser_startup_seed_root).resolve()
    if not browser_bin.exists():
        raise SystemExit(f"browser binary not found: {browser_bin}")
    if not tor_bin.exists():
        raise SystemExit(f"tor binary not found: {tor_bin}")
    targets = resolve_targets(args.target_pack, args.targets)
    run_id = time.strftime("%Y%m%dT%H%M%S")
    output_dir = Path(args.output_root).resolve() / (
        f"torfast-promoted-quality-check-{run_id}"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    no_marionette_fingerprint = collect_no_marionette_fingerprint_snapshot(
        browser_bin=browser_bin,
        output_dir=output_dir,
        window_size=args.window_size,
        compact_output=False,
    )
    no_marionette_validation = validate_browser_fingerprint_snapshot(
        no_marionette_fingerprint,
        require_rfp_behaviors=True,
    )
    no_marionette_fingerprint["validation"] = no_marionette_validation
    reference_fingerprint_snapshot = (
        no_marionette_fingerprint.get("snapshot")
        if (
            no_marionette_fingerprint.get("ok") is True
            and no_marionette_validation.get("ok") is True
            and isinstance(no_marionette_fingerprint.get("snapshot"), dict)
        )
        else None
    )

    c_tor_circuit_checks: dict[str, dict[str, object]] = {}
    if args.skip_c_tor_circuit_check:
        for target in targets:
            c_tor_circuit_checks[target] = {
                "ok": True,
                "skipped": True,
            }
    else:
        targets_to_check = (
            list(targets) if args.c_tor_circuit_check_all_targets else [targets[0]]
        )
        for index, target in enumerate(targets_to_check):
            c_tor_circuit_check_output_dir = (
                output_dir / "c-tor-circuit-check" / target_slug(target)
            )
            c_tor_circuit_check_output_dir.mkdir(parents=True, exist_ok=True)
            circuit_check = run_c_tor_circuit_check(
                tor_bin=tor_bin,
                target=target,
                socks_port=args.c_tor_circuit_check_socks_port + (index * 2),
                control_port=args.c_tor_circuit_check_control_port + (index * 2),
                output_dir=c_tor_circuit_check_output_dir,
            )
            circuit_check["summary"] = c_tor_circuit_short_summary(circuit_check)
            (
                c_tor_circuit_check_output_dir / "c-tor-circuits.json"
            ).write_text(json.dumps(circuit_check, indent=2, sort_keys=True) + "\n")
            c_tor_circuit_checks[target] = circuit_check
        for target in targets:
            c_tor_circuit_checks.setdefault(
                target,
                {
                    "ok": True,
                    "skipped": True,
                },
            )

    results: list[dict[str, object]] = []
    ports_used = 0
    for cycle in range(1, args.cycles + 1):
        for target in targets:
            for profile_spec in PROFILE_SPECS:
                result = run_profile_target_cycle(
                    browser_bin=browser_bin,
                    tor_bin=tor_bin,
                    browser_startup_seed_root=browser_startup_seed_root,
                    output_dir=output_dir,
                    target=target,
                    cycle=cycle,
                    profile_spec=profile_spec,
                    port=args.port_base + ports_used,
                    browser_timeout=args.browser_timeout,
                    stream_isolation_probe_timeout=args.stream_isolation_probe_timeout,
                    reference_fingerprint_snapshot=reference_fingerprint_snapshot,
                )
                quality = validate_open_launch_quality(
                    result.get("open_launch"),
                    allow_webdriver_artifact=(
                        no_marionette_fingerprint.get("ok") is True
                        and no_marionette_validation.get("ok") is True
                    ),
                    reference_fingerprint_snapshot=reference_fingerprint_snapshot,
                )
                result["quality"] = quality
                results.append(result)
                ports_used += 1

    profiles = summarize_results(results, targets=targets)
    pairwise_consistency: list[dict[str, object]] = []
    for cycle in range(1, args.cycles + 1):
        for target in targets:
            baseline = next(
                (
                    row
                    for row in results
                    if row.get("target") == target
                    and row.get("cycle") == cycle
                    and row.get("profile_name") == PROFILE_SPECS[0]["name"]
                ),
                None,
            )
            candidate = next(
                (
                    row
                    for row in results
                    if row.get("target") == target
                    and row.get("cycle") == cycle
                    and row.get("profile_name") == PROFILE_SPECS[1]["name"]
                ),
                None,
            )
            failures = pairwise_quality_failures(
                baseline.get("open_launch") if isinstance(baseline, dict) else None,
                candidate.get("open_launch") if isinstance(candidate, dict) else None,
            )
            pairwise_consistency.append(
                {
                    "target": target,
                    "cycle": cycle,
                    "baseline_profile": PROFILE_SPECS[0]["name"],
                    "candidate_profile": PROFILE_SPECS[1]["name"],
                    "ok": not failures,
                    "failures": failures,
                }
            )

    deltas = delta_vs_baseline(
        profiles,
        targets=targets,
        baseline_profile=str(PROFILE_SPECS[0]["name"]),
        candidate_profile=str(PROFILE_SPECS[1]["name"]),
    )
    payload = {
        "created_at_utc": datetime.now(timezone.utc).isoformat().replace(
            "+00:00", "Z"
        ),
        "repo_root": str(REPO_ROOT),
        "output_dir": str(output_dir),
        "targets": targets,
        "cycles": args.cycles,
        "profile_names": [str(spec["name"]) for spec in PROFILE_SPECS],
        "no_marionette_fingerprint_proof": no_marionette_fingerprint,
        "c_tor_circuit_check": c_tor_circuit_checks.get(targets[0], {}),
        "c_tor_circuit_checks": c_tor_circuit_checks,
        "profiles": profiles,
        "delta_vs_baseline": deltas,
        "pairwise_consistency": pairwise_consistency,
        "results": results,
    }
    payload["ok"] = payload_ok(payload)
    summary_path = output_dir / "summary.json"
    summary_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"wrote {summary_path}")
    print(
        json.dumps(
            {
                "ok": payload["ok"],
                "output_dir": str(output_dir),
                "delta_vs_baseline": deltas,
                "pairwise_consistency": pairwise_consistency,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
