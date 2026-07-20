#!/usr/bin/env python3
"""Compare repeated warm/open launch gates without changing Tor quality defaults."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import statistics
import subprocess
import sys
import time
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from torfast.browser_startup_seed import DEFAULT_BROWSER_STARTUP_SEED_ROOT
from torfast.control import (
    read_general_circuit_snapshot,
    user_stream_snapshot_observed,
    wait_for_general_circuits,
)
from torfast.fast_runtime import WARM_RUNTIME_HELPER_PRESTART_ENABLED_ENV


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
CONFLUX_CLIENT_UX_CHOICES = (
    "latency",
    "throughput",
    "throughput_lowmem",
)
LAUNCH_FIELDS = (
    "browser",
    "browser_default_pref_check",
    "browser_default_prefs",
    "browser_launch_gate",
    "browser_launch_gate_requested",
    "browser_runtime_reset",
    "browser_startup_seed_apply",
    "browser_startup_seed_update",
    "dir_cache_seed_apply",
    "dir_cache_seed_update",
    "managed_open_browser_overlap",
    "managed_open_browser_overlap_enabled",
    "managed_open_adaptive_general_circuit_wait",
    "managed_open_adaptive_general_circuit_wait_timeout_seconds",
    "warm_browser_prestart",
    "warm_browser_prestart_enabled",
    "leave_tor_running",
    "managed_open_settle",
    "managed_open_settle_enabled",
    "port",
    "reused_tor_service",
    "runtime_helper_gate_promoter",
    "tor_managed_ready",
    "tor_browser_launch_gate",
    "tor_boot",
    "torrc_quality",
    "url",
)
WAIT_READY_GATE_CHOICES = (
    "auto",
    "socks_ready",
    "tor_boot_90",
    "tor_boot_95",
    "tor_boot_100",
)
PERSISTENT_CONTROL_WAIT_DISABLED_ENV = "TORFAST_DISABLE_PERSISTENT_CONTROL_WAIT"
PERSISTENT_CONTROL_WAIT_ENABLED_ENV = "TORFAST_ENABLE_PERSISTENT_CONTROL_WAIT"
CONTROL_BOOTSTRAP_PROBE_DISABLED_ENV = "TORFAST_DISABLE_CONTROL_BOOTSTRAP_PROBE"
ASYNC_BROWSER_RESET_DISABLED_ENV = "TORFAST_DISABLE_ASYNC_BROWSER_RESET"
MANAGED_SERVICE_METADATA_WAIT_DISABLED_ENV = (
    "TORFAST_DISABLE_MANAGED_SERVICE_METADATA_WAIT"
)
TARGET_STREAM_PROOF_ENABLED_ENV = "TORFAST_ENABLE_TARGET_STREAM_PROOF"
ADAPTIVE_GENERAL_CIRCUIT_WAIT_POLL_INTERVAL_SECONDS = 0.05
VARIANT_TIMEOUT_LABEL_DECIMALS = 6


def parse_extra_wait_values(values: list[str]) -> list[float]:
    waits: list[float] = []
    for raw in values:
        try:
            seconds = float(raw)
        except ValueError as exc:
            raise SystemExit(
                f"invalid --extra-post-warm-wait-seconds value: {raw!r}"
            ) from exc
        if seconds <= 0:
            raise SystemExit("--extra-post-warm-wait-seconds values must be positive")
        rounded = round(seconds, 3)
        if rounded not in waits:
            waits.append(rounded)
    return waits


def parse_extra_adaptive_general_circuit_wait_timeout_values(
    values: list[str],
) -> list[float]:
    timeouts: list[float] = []
    seen_labels: set[str] = set()
    for raw in values:
        try:
            seconds = float(raw)
        except ValueError as exc:
            raise SystemExit(
                "invalid --extra-adaptive-general-circuit-wait-timeout value: "
                f"{raw!r}"
            ) from exc
        if seconds <= 0:
            raise SystemExit(
                "--extra-adaptive-general-circuit-wait-timeout values must be positive"
            )
        normalized = normalized_variant_timeout_seconds(seconds)
        label = variant_timeout_seconds_label(normalized)
        if label not in seen_labels:
            timeouts.append(normalized)
            seen_labels.add(label)
    return timeouts


def waited_profile_name(base_profile_name: str, seconds: float) -> str:
    seconds_label = format(seconds, "g").replace(".", "p")
    return f"{base_profile_name}_wait_{seconds_label}s"


def normalized_variant_timeout_seconds(seconds: float) -> float:
    return float(f"{seconds:.{VARIANT_TIMEOUT_LABEL_DECIMALS}f}")


def variant_timeout_seconds_label(seconds: float) -> str:
    normalized = normalized_variant_timeout_seconds(seconds)
    seconds_label = (
        f"{normalized:.{VARIANT_TIMEOUT_LABEL_DECIMALS}f}"
        .rstrip("0")
        .rstrip(".")
    )
    return seconds_label.replace(".", "p")


def adaptive_general_circuit_wait_variant_profile_name(
    base_profile_name: str,
    timeout_seconds: float,
) -> str:
    seconds_label = variant_timeout_seconds_label(timeout_seconds)
    return f"{base_profile_name}_adaptivegencirc_{seconds_label}s"


def managed_open_adaptive_general_circuit_wait_variant_profile_name(
    base_profile_name: str,
    timeout_seconds: float,
) -> str:
    seconds_label = variant_timeout_seconds_label(timeout_seconds)
    return f"{base_profile_name}_managedadaptivegencirc_{seconds_label}s"


def conflux_variant_profile_name(
    profile_name: str,
    conflux_client_ux: str | None,
) -> str:
    if not conflux_client_ux:
        return profile_name
    return f"{profile_name}_confluxux_{conflux_client_ux}"


def managed_open_settle_variant_profile_name(
    profile_name: str,
    *,
    managed_open_settle_enabled: bool,
) -> str:
    if managed_open_settle_enabled:
        return profile_name
    return f"{profile_name}_nosettle"


def warm_helper_prestart_variant_profile_name(
    profile_name: str,
    *,
    warm_helper_prestart_enabled: bool,
) -> str:
    if warm_helper_prestart_enabled:
        return profile_name
    return f"{profile_name}_noprestart"


def warm_browser_prestart_variant_profile_name(
    profile_name: str,
    *,
    warm_browser_prestart_enabled: bool,
) -> str:
    if warm_browser_prestart_enabled:
        return profile_name
    return f"{profile_name}_nobrowserprestart"


def managed_open_browser_overlap_variant_profile_name(
    profile_name: str,
    *,
    managed_open_browser_overlap_enabled: bool,
) -> str:
    if managed_open_browser_overlap_enabled:
        return profile_name
    return f"{profile_name}_nooverlap"


def browser_startup_seed_variant_profile_name(
    profile_name: str,
    *,
    browser_startup_seed_enabled: bool,
) -> str:
    suffix = (
        "browserstartupseed"
        if browser_startup_seed_enabled
        else "nobrowserstartupseed"
    )
    return f"{profile_name}_{suffix}"


def persistent_control_wait_variant_profile_name(
    profile_name: str,
    *,
    persistent_control_wait_enabled: bool,
) -> str:
    if persistent_control_wait_enabled:
        return profile_name
    return f"{profile_name}_nopersistctrl"


def control_bootstrap_probe_variant_profile_name(
    profile_name: str,
    *,
    control_bootstrap_probe_enabled: bool,
) -> str:
    if control_bootstrap_probe_enabled:
        return profile_name
    return f"{profile_name}_nocontrolprobe"


def async_browser_reset_variant_profile_name(
    profile_name: str,
    *,
    async_browser_reset_enabled: bool,
) -> str:
    if async_browser_reset_enabled:
        return profile_name
    return f"{profile_name}_noasyncreset"


def managed_service_metadata_wait_variant_profile_name(
    profile_name: str,
    *,
    managed_service_metadata_wait_enabled: bool,
) -> str:
    if managed_service_metadata_wait_enabled:
        return profile_name
    return f"{profile_name}_nometadatawait"


def port_is_available(port: int) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", port))
    except OSError:
        return False
    return True


def next_available_port(
    start_port: int,
    *,
    reserved_ports: set[int] | None = None,
) -> int:
    reserved = reserved_ports or set()
    for port in range(start_port, 65_536):
        if port in reserved:
            continue
        if port_is_available(port):
            return port
    raise SystemExit(f"no available port found at or above {start_port}")


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.baseline_profile not in args.profiles:
        raise SystemExit("--baseline-profile must be included in --profiles")

    browser_bin = Path(args.browser_bin).resolve()
    tor_bin = Path(args.tor_bin).resolve()
    browser_startup_seed_root = Path(args.browser_startup_seed_root).resolve()
    output_root = Path(args.output_root).resolve()
    extra_post_warm_wait_seconds = parse_extra_wait_values(
        args.extra_post_warm_wait_seconds
    )
    extra_adaptive_general_circuit_wait_timeout_seconds = (
        parse_extra_adaptive_general_circuit_wait_timeout_values(
            args.extra_adaptive_general_circuit_wait_timeout
        )
    )
    extra_managed_open_adaptive_general_circuit_wait_timeout_seconds = (
        parse_extra_adaptive_general_circuit_wait_timeout_values(
            args.extra_managed_open_adaptive_general_circuit_wait_timeout
        )
    )
    profile_specs = build_profile_specs(
        profile_names=args.profiles,
        extra_post_warm_wait_seconds=extra_post_warm_wait_seconds,
        extra_adaptive_general_circuit_wait_timeout_seconds=(
            extra_adaptive_general_circuit_wait_timeout_seconds
        ),
        extra_managed_open_adaptive_general_circuit_wait_timeout_seconds=(
            extra_managed_open_adaptive_general_circuit_wait_timeout_seconds
        ),
        base_conflux_client_ux=args.conflux_client_ux,
        extra_conflux_client_ux=args.extra_conflux_client_ux,
        base_browser_startup_seed_enabled=args.browser_startup_seed,
        base_persistent_control_wait_enabled=args.persistent_control_wait,
        base_control_bootstrap_probe_enabled=True,
        base_async_browser_reset_enabled=True,
        base_managed_service_metadata_wait_enabled=True,
        base_managed_open_settle_enabled=args.managed_open_settle,
        base_managed_open_browser_overlap_enabled=args.managed_open_browser_overlap,
        base_warm_helper_prestart_enabled=args.warm_helper_prestart,
        base_warm_browser_prestart_enabled=args.warm_browser_prestart,
        extra_browser_startup_seed=args.extra_browser_startup_seed,
        extra_no_persistent_control_wait=args.extra_no_persistent_control_wait,
        extra_no_control_bootstrap_probe=args.extra_no_control_bootstrap_probe,
        extra_no_async_browser_reset=args.extra_no_async_browser_reset,
        extra_no_managed_service_metadata_wait=(
            args.extra_no_managed_service_metadata_wait
        ),
        extra_no_browser_startup_seed=args.extra_no_browser_startup_seed,
        extra_no_managed_open_settle=args.extra_no_managed_open_settle,
        extra_no_managed_open_browser_overlap=(
            args.extra_no_managed_open_browser_overlap
        ),
        extra_no_warm_helper_prestart=args.extra_no_warm_helper_prestart,
        extra_no_warm_browser_prestart=args.extra_no_warm_browser_prestart,
    )
    profile_names = [str(spec["name"]) for spec in profile_specs]
    run_id = time.strftime("%Y%m%dT%H%M%S")
    output_dir = output_root / f"torfast-warm-open-compare-{run_id}"
    output_dir.mkdir(parents=True, exist_ok=True)

    if not browser_bin.exists():
        raise SystemExit(f"browser binary not found: {browser_bin}")
    if not tor_bin.exists():
        raise SystemExit(f"tor binary not found: {tor_bin}")

    results: list[dict[str, object]] = []
    port = args.port_base
    reserved_ports: set[int] = set()
    for target in args.targets:
        for cycle in range(1, args.cycles + 1):
            for profile_spec in cycle_profile_order(cycle, profile_specs):
                requested_port = port
                port = next_available_port(port, reserved_ports=reserved_ports)
                reserved_ports.add(port)
                result = run_target_profile_once(
                    target=target,
                    profile_name=str(profile_spec["name"]),
                    base_profile_name=str(profile_spec["base_profile_name"]),
                    extra_post_warm_wait_seconds=float(
                        profile_spec["extra_post_warm_wait_seconds"]
                    ),
                    conflux_client_ux=(
                        str(profile_spec["conflux_client_ux"])
                        if profile_spec.get("conflux_client_ux") is not None
                        else None
                    ),
                    managed_open_settle_enabled=bool(
                        profile_spec.get(
                            "managed_open_settle_enabled",
                            args.managed_open_settle,
                        )
                    ),
                    managed_open_browser_overlap_enabled=bool(
                        profile_spec.get(
                            "managed_open_browser_overlap_enabled",
                            args.managed_open_browser_overlap,
                        )
                    ),
                    cycle=cycle,
                    port=port,
                    requested_port=requested_port,
                    browser_bin=browser_bin,
                    tor_bin=tor_bin,
                    browser_timeout=args.browser_timeout,
                    browser_startup_seed_root=browser_startup_seed_root,
                    browser_startup_seed_enabled=bool(
                        profile_spec.get(
                            "browser_startup_seed_enabled",
                            args.browser_startup_seed,
                        )
                    ),
                    persistent_control_wait_enabled=bool(
                        profile_spec.get(
                            "persistent_control_wait_enabled",
                            args.persistent_control_wait,
                        )
                    ),
                    control_bootstrap_probe_enabled=bool(
                        profile_spec.get(
                            "control_bootstrap_probe_enabled",
                            True,
                        )
                    ),
                    async_browser_reset_enabled=bool(
                        profile_spec.get(
                            "async_browser_reset_enabled",
                            True,
                        )
                    ),
                    managed_service_metadata_wait_enabled=bool(
                        profile_spec.get(
                            "managed_service_metadata_wait_enabled",
                            True,
                        )
                    ),
                    warm_helper_prestart_enabled=bool(
                        profile_spec.get(
                            "warm_helper_prestart_enabled",
                            args.warm_helper_prestart,
                        )
                    ),
                    warm_browser_prestart_enabled=bool(
                        profile_spec.get(
                            "warm_browser_prestart_enabled",
                            args.warm_browser_prestart,
                        )
                    ),
                    managed_open_adaptive_general_circuit_wait_timeout_seconds=float(
                        profile_spec.get(
                            (
                                "managed_open_adaptive_general_circuit_wait_"
                                "timeout_seconds"
                            ),
                            0.0,
                        )
                    ),
                    adaptive_general_circuit_wait_timeout_seconds=float(
                        profile_spec.get(
                            "adaptive_general_circuit_wait_timeout_seconds",
                            0.0,
                        )
                    ),
                    headed=args.headed,
                    wait_ready_after_post_warm_wait=(
                        args.wait_ready_after_post_warm_wait
                    ),
                    wait_ready_gate=args.wait_ready_gate,
                    wait_ready_timeout=args.wait_ready_timeout,
                    gate_diagnostics=args.gate_diagnostics,
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
        "profile_names": profile_names,
        "baseline_profile": args.baseline_profile,
        "conflux_client_ux": args.conflux_client_ux,
        "browser_timeout_seconds": args.browser_timeout,
        "browser_startup_seed_enabled": args.browser_startup_seed,
        "persistent_control_wait_enabled": args.persistent_control_wait,
        "control_bootstrap_probe_enabled": True,
        "managed_service_metadata_wait_enabled": True,
        "managed_open_settle_enabled": args.managed_open_settle,
        "managed_open_browser_overlap_enabled": (
            args.managed_open_browser_overlap
        ),
        "warm_helper_prestart_enabled": args.warm_helper_prestart,
        "warm_browser_prestart_enabled": args.warm_browser_prestart,
        "wait_ready_after_post_warm_wait_enabled": args.wait_ready_after_post_warm_wait,
        "wait_ready_gate": args.wait_ready_gate,
        "wait_ready_timeout_seconds": args.wait_ready_timeout,
        "extra_browser_startup_seed": args.extra_browser_startup_seed,
        "extra_no_persistent_control_wait": args.extra_no_persistent_control_wait,
        "extra_no_control_bootstrap_probe": args.extra_no_control_bootstrap_probe,
        "extra_no_async_browser_reset": args.extra_no_async_browser_reset,
        "extra_adaptive_general_circuit_wait_timeout_seconds": (
            extra_adaptive_general_circuit_wait_timeout_seconds
        ),
        "extra_managed_open_adaptive_general_circuit_wait_timeout_seconds": (
            extra_managed_open_adaptive_general_circuit_wait_timeout_seconds
        ),
        "extra_no_managed_service_metadata_wait": (
            args.extra_no_managed_service_metadata_wait
        ),
        "extra_no_browser_startup_seed": args.extra_no_browser_startup_seed,
        "extra_no_managed_open_settle": args.extra_no_managed_open_settle,
        "extra_no_managed_open_browser_overlap": (
            args.extra_no_managed_open_browser_overlap
        ),
        "extra_no_warm_helper_prestart": args.extra_no_warm_helper_prestart,
        "extra_no_warm_browser_prestart": args.extra_no_warm_browser_prestart,
        "profiles": summarize_results(
            results,
            targets=args.targets,
            profile_names=profile_names,
        ),
        "results": compact_results(results, targets=args.targets),
    }
    payload["delta_vs_baseline"] = delta_vs_baseline(
        payload["profiles"],
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
        "--conflux-client-ux",
        choices=CONFLUX_CLIENT_UX_CHOICES,
        help="optional official Tor `ConfluxClientUX` override to benchmark",
    )
    parser.add_argument(
        "--extra-conflux-client-ux",
        action="append",
        default=[],
        choices=CONFLUX_CLIENT_UX_CHOICES,
        help=(
            "add same-window variant profiles with this official Tor "
            "`ConfluxClientUX` override"
        ),
    )
    parser.add_argument(
        "--extra-post-warm-wait-seconds",
        action="append",
        default=[],
        metavar="SECONDS",
        help=(
            "add a same-profile repeated-open variant that waits this many "
            "seconds after warm returns before open starts; this hidden "
            "background wait is tracked separately and not charged to the "
            "combined warm+open metric"
        ),
    )
    parser.add_argument(
        "--extra-adaptive-general-circuit-wait-timeout",
        action="append",
        default=[],
        metavar="SECONDS",
        help=(
            "add same-window variants that, before `open`, wait up to this "
            "many seconds for a built 3-hop general circuit only when the "
            "reused Tor service does not already have one; this capped wait "
            "is charged to the combined warm+open metric"
        ),
    )
    parser.add_argument(
        "--extra-managed-open-adaptive-general-circuit-wait-timeout",
        action="append",
        default=[],
        metavar="SECONDS",
        help=(
            "add same-window variants that pass the real launcher/runtime "
            "managed-open adaptive general-circuit wait timeout through to "
            "`torfast open`; this charges any wait inside the real open wall "
            "time rather than using the harness-side pause"
        ),
    )
    parser.add_argument(
        "--wait-ready-after-post-warm-wait",
        action="store_true",
        help=(
            "after any explicit post-warm idle gap, run `torfast wait-ready` "
            "before `open` so the hidden-readiness workflow is measured through "
            "the real user-facing command"
        ),
    )
    parser.add_argument(
        "--wait-ready-gate",
        default="auto",
        choices=WAIT_READY_GATE_CHOICES,
        help="gate passed to `torfast wait-ready` when that command is enabled",
    )
    parser.add_argument(
        "--wait-ready-timeout",
        type=float,
        default=180.0,
        help="seconds to wait inside `torfast wait-ready` when it is enabled",
    )
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
        "--extra-browser-startup-seed",
        action="store_true",
        help=(
            "when the base profiles keep browser startup seed off, also add "
            "same-window variants with it enabled"
        ),
    )
    parser.add_argument(
        "--extra-no-browser-startup-seed",
        action="store_true",
        help=(
            "when the base profiles use browser startup seed, also add "
            "same-window variants with it disabled"
        ),
    )
    parser.add_argument(
        "--persistent-control-wait",
        action="store_true",
        help=(
            "opt in to the persistent Tor control connection during readiness "
            "waits for the base profiles"
        ),
    )
    parser.add_argument(
        "--extra-no-persistent-control-wait",
        action="store_true",
        help=(
            "when the base profiles use persistent Tor control waits, also add "
            "same-window variants with that behavior disabled"
        ),
    )
    parser.add_argument(
        "--extra-no-control-bootstrap-probe",
        action="store_true",
        help=(
            "add same-window variants that disable launcher control bootstrap "
            "probes and wait only on log-based reused-service readiness"
        ),
    )
    parser.add_argument(
        "--extra-no-async-browser-reset",
        action="store_true",
        help=(
            "add same-window variants that disable async browser runtime reset "
            "cleanup for A/B comparison"
        ),
    )
    parser.add_argument(
        "--extra-no-managed-service-metadata-wait",
        action="store_true",
        help=(
            "add same-window variants that disable the reused-service "
            "tor-service.json readiness shortcut for A/B comparison"
        ),
    )
    parser.add_argument(
        "--managed-open-settle",
        action="store_true",
        help="opt in to the managed-open settle candidate for the base profiles",
    )
    managed_open_browser_overlap_group = parser.add_mutually_exclusive_group()
    managed_open_browser_overlap_group.add_argument(
        "--managed-open-browser-overlap",
        dest="managed_open_browser_overlap",
        action="store_true",
        help=(
            "enable the managed-open browser-overlap path for the base "
            "profiles"
        ),
    )
    managed_open_browser_overlap_group.add_argument(
        "--no-managed-open-browser-overlap",
        dest="managed_open_browser_overlap",
        action="store_false",
        help=(
            "disable the managed-open browser-overlap path for the base "
            "profiles"
        ),
    )
    parser.set_defaults(managed_open_browser_overlap=True)
    parser.add_argument(
        "--warm-helper-prestart",
        action="store_true",
        help=(
            "opt in to the warm-time runtime-helper prestart overlap candidate "
            "for the base profiles"
        ),
    )
    parser.add_argument(
        "--warm-browser-prestart",
        action="store_true",
        help=(
            "opt in to the warm-gap background browser prestart candidate for "
            "the base profiles"
        ),
    )
    parser.add_argument(
        "--extra-no-managed-open-settle",
        action="store_true",
        help=(
            "when the base profiles use managed-open settle, also add same-window "
            "variants with settle disabled"
        ),
    )
    parser.add_argument(
        "--extra-no-managed-open-browser-overlap",
        action="store_true",
        help=(
            "when the base profiles use managed-open browser overlap, also add "
            "same-window variants with overlap disabled"
        ),
    )
    parser.add_argument(
        "--extra-no-warm-helper-prestart",
        action="store_true",
        help=(
            "add same-window variants that disable the warm-time runtime-helper "
            "prestart overlap for A/B comparison"
        ),
    )
    parser.add_argument(
        "--extra-no-warm-browser-prestart",
        action="store_true",
        help=(
            "add same-window variants that disable the warm-gap background "
            "browser prestart candidate for A/B comparison"
        ),
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="show browser windows instead of using headless browser runs",
    )
    parser.add_argument(
        "--gate-diagnostics",
        action="store_true",
        help="record proof-only reused-service gate-wait diagnostics in saved launch JSON",
    )
    parser.add_argument("--port-base", type=int, default=20450)
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
    extra_adaptive_general_circuit_wait_timeout_seconds: list[float] | None = None,
    extra_managed_open_adaptive_general_circuit_wait_timeout_seconds: (
        list[float] | None
    ) = None,
    base_conflux_client_ux: str | None = None,
    extra_conflux_client_ux: list[str] | None = None,
    base_browser_startup_seed_enabled: bool = False,
    base_persistent_control_wait_enabled: bool = False,
    base_control_bootstrap_probe_enabled: bool = True,
    base_async_browser_reset_enabled: bool = True,
    base_managed_service_metadata_wait_enabled: bool = True,
    base_managed_open_settle_enabled: bool = False,
    base_managed_open_browser_overlap_enabled: bool = False,
    base_warm_helper_prestart_enabled: bool = False,
    base_warm_browser_prestart_enabled: bool = False,
    extra_browser_startup_seed: bool = False,
    extra_no_persistent_control_wait: bool = False,
    extra_no_control_bootstrap_probe: bool = False,
    extra_no_async_browser_reset: bool = False,
    extra_no_managed_service_metadata_wait: bool = False,
    extra_no_browser_startup_seed: bool = False,
    extra_no_managed_open_settle: bool = False,
    extra_no_managed_open_browser_overlap: bool = False,
    extra_no_warm_helper_prestart: bool = False,
    extra_no_warm_browser_prestart: bool = False,
) -> list[dict[str, object]]:
    specs: list[dict[str, object]] = []
    seen: set[str] = set()
    conflux_variants: list[str | None] = [base_conflux_client_ux]
    for value in extra_conflux_client_ux or []:
        if value not in conflux_variants:
            conflux_variants.append(value)

    def add_spec(
        *,
        name: str,
        base_profile_name: str,
        extra_post_warm_wait_seconds: float,
        conflux_client_ux: str | None,
        browser_startup_seed_enabled: bool,
        record_browser_startup_seed_field: bool = False,
        persistent_control_wait_enabled: bool,
        record_persistent_control_wait_field: bool = False,
        control_bootstrap_probe_enabled: bool = True,
        record_control_bootstrap_probe_field: bool = False,
        async_browser_reset_enabled: bool,
        record_async_browser_reset_field: bool = False,
        managed_service_metadata_wait_enabled: bool = True,
        record_managed_service_metadata_wait_field: bool = False,
        managed_open_settle_enabled: bool,
        record_managed_open_settle_field: bool = False,
        managed_open_browser_overlap_enabled: bool = False,
        record_managed_open_browser_overlap_field: bool = False,
        warm_helper_prestart_enabled: bool = True,
        record_warm_helper_prestart_field: bool = False,
        warm_browser_prestart_enabled: bool = False,
        record_warm_browser_prestart_field: bool = False,
        managed_open_adaptive_general_circuit_wait_timeout_seconds: float = 0.0,
        record_managed_open_adaptive_general_circuit_wait_timeout_field: bool = False,
        adaptive_general_circuit_wait_timeout_seconds: float = 0.0,
        record_adaptive_general_circuit_wait_timeout_field: bool = False,
    ) -> None:
        if name in seen:
            return
        spec: dict[str, object] = {
            "name": name,
            "base_profile_name": base_profile_name,
            "extra_post_warm_wait_seconds": extra_post_warm_wait_seconds,
            "conflux_client_ux": conflux_client_ux,
        }
        if record_browser_startup_seed_field:
            spec["browser_startup_seed_enabled"] = browser_startup_seed_enabled
        if record_persistent_control_wait_field:
            spec["persistent_control_wait_enabled"] = (
                persistent_control_wait_enabled
            )
        if record_control_bootstrap_probe_field:
            spec["control_bootstrap_probe_enabled"] = (
                control_bootstrap_probe_enabled
            )
        if record_async_browser_reset_field:
            spec["async_browser_reset_enabled"] = async_browser_reset_enabled
        if record_managed_service_metadata_wait_field:
            spec["managed_service_metadata_wait_enabled"] = (
                managed_service_metadata_wait_enabled
            )
        if record_managed_open_settle_field:
            spec["managed_open_settle_enabled"] = managed_open_settle_enabled
        if record_managed_open_browser_overlap_field:
            spec["managed_open_browser_overlap_enabled"] = (
                managed_open_browser_overlap_enabled
            )
        if record_warm_helper_prestart_field:
            spec["warm_helper_prestart_enabled"] = warm_helper_prestart_enabled
        if record_warm_browser_prestart_field:
            spec["warm_browser_prestart_enabled"] = warm_browser_prestart_enabled
        if record_managed_open_adaptive_general_circuit_wait_timeout_field:
            spec["managed_open_adaptive_general_circuit_wait_timeout_seconds"] = (
                managed_open_adaptive_general_circuit_wait_timeout_seconds
            )
        if record_adaptive_general_circuit_wait_timeout_field:
            spec["adaptive_general_circuit_wait_timeout_seconds"] = (
                adaptive_general_circuit_wait_timeout_seconds
            )
        specs.append(spec)
        seen.add(name)

    for profile_name in profile_names:
        for conflux_client_ux in conflux_variants:
            base_name = conflux_variant_profile_name(profile_name, conflux_client_ux)
            add_spec(
                name=base_name,
                base_profile_name=profile_name,
                extra_post_warm_wait_seconds=0.0,
                conflux_client_ux=conflux_client_ux,
                browser_startup_seed_enabled=base_browser_startup_seed_enabled,
                persistent_control_wait_enabled=(
                    base_persistent_control_wait_enabled
                ),
                async_browser_reset_enabled=base_async_browser_reset_enabled,
                managed_open_settle_enabled=base_managed_open_settle_enabled,
                managed_open_browser_overlap_enabled=(
                    base_managed_open_browser_overlap_enabled
                ),
                warm_browser_prestart_enabled=base_warm_browser_prestart_enabled,
            )
            for seconds in extra_post_warm_wait_seconds:
                add_spec(
                    name=conflux_variant_profile_name(
                        waited_profile_name(profile_name, seconds),
                        conflux_client_ux,
                    ),
                    base_profile_name=profile_name,
                    extra_post_warm_wait_seconds=seconds,
                    conflux_client_ux=conflux_client_ux,
                    browser_startup_seed_enabled=base_browser_startup_seed_enabled,
                    persistent_control_wait_enabled=(
                        base_persistent_control_wait_enabled
                    ),
                    async_browser_reset_enabled=base_async_browser_reset_enabled,
                    managed_open_settle_enabled=base_managed_open_settle_enabled,
                    managed_open_browser_overlap_enabled=(
                        base_managed_open_browser_overlap_enabled
                    ),
                    warm_browser_prestart_enabled=(
                        base_warm_browser_prestart_enabled
                    ),
                )
            if not (extra_no_managed_open_settle and base_managed_open_settle_enabled):
                if not (
                    extra_no_managed_open_browser_overlap
                    and base_managed_open_browser_overlap_enabled
                ):
                    continue
            if extra_no_managed_open_settle and base_managed_open_settle_enabled:
                add_spec(
                    name=managed_open_settle_variant_profile_name(
                        base_name,
                        managed_open_settle_enabled=False,
                    ),
                    base_profile_name=profile_name,
                    extra_post_warm_wait_seconds=0.0,
                    conflux_client_ux=conflux_client_ux,
                    browser_startup_seed_enabled=base_browser_startup_seed_enabled,
                    persistent_control_wait_enabled=(
                        base_persistent_control_wait_enabled
                    ),
                    async_browser_reset_enabled=base_async_browser_reset_enabled,
                    managed_open_settle_enabled=False,
                    record_managed_open_settle_field=True,
                    managed_open_browser_overlap_enabled=(
                        base_managed_open_browser_overlap_enabled
                    ),
                    warm_browser_prestart_enabled=(
                        base_warm_browser_prestart_enabled
                    ),
                )
                for seconds in extra_post_warm_wait_seconds:
                    add_spec(
                        name=managed_open_settle_variant_profile_name(
                            conflux_variant_profile_name(
                                waited_profile_name(profile_name, seconds),
                                conflux_client_ux,
                            ),
                            managed_open_settle_enabled=False,
                        ),
                        base_profile_name=profile_name,
                        extra_post_warm_wait_seconds=seconds,
                        conflux_client_ux=conflux_client_ux,
                        browser_startup_seed_enabled=(
                            base_browser_startup_seed_enabled
                        ),
                        persistent_control_wait_enabled=(
                            base_persistent_control_wait_enabled
                        ),
                        async_browser_reset_enabled=base_async_browser_reset_enabled,
                        managed_open_settle_enabled=False,
                        record_managed_open_settle_field=True,
                        managed_open_browser_overlap_enabled=(
                            base_managed_open_browser_overlap_enabled
                        ),
                        warm_browser_prestart_enabled=(
                            base_warm_browser_prestart_enabled
                        ),
                    )
            if not (
                extra_no_managed_open_browser_overlap
                and base_managed_open_browser_overlap_enabled
            ):
                continue
            add_spec(
                name=managed_open_browser_overlap_variant_profile_name(
                    base_name,
                    managed_open_browser_overlap_enabled=False,
                ),
                base_profile_name=profile_name,
                extra_post_warm_wait_seconds=0.0,
                conflux_client_ux=conflux_client_ux,
                browser_startup_seed_enabled=base_browser_startup_seed_enabled,
                persistent_control_wait_enabled=(
                    base_persistent_control_wait_enabled
                ),
                async_browser_reset_enabled=base_async_browser_reset_enabled,
                managed_open_settle_enabled=base_managed_open_settle_enabled,
                managed_open_browser_overlap_enabled=False,
                record_managed_open_browser_overlap_field=True,
                warm_browser_prestart_enabled=base_warm_browser_prestart_enabled,
            )
            for seconds in extra_post_warm_wait_seconds:
                add_spec(
                    name=managed_open_browser_overlap_variant_profile_name(
                        conflux_variant_profile_name(
                            waited_profile_name(profile_name, seconds),
                            conflux_client_ux,
                        ),
                        managed_open_browser_overlap_enabled=False,
                    ),
                    base_profile_name=profile_name,
                    extra_post_warm_wait_seconds=seconds,
                    conflux_client_ux=conflux_client_ux,
                    browser_startup_seed_enabled=base_browser_startup_seed_enabled,
                    persistent_control_wait_enabled=(
                        base_persistent_control_wait_enabled
                    ),
                    async_browser_reset_enabled=base_async_browser_reset_enabled,
                    managed_open_settle_enabled=base_managed_open_settle_enabled,
                    managed_open_browser_overlap_enabled=False,
                    record_managed_open_browser_overlap_field=True,
                    warm_browser_prestart_enabled=(
                        base_warm_browser_prestart_enabled
                    ),
                )
    if extra_no_warm_helper_prestart and base_warm_helper_prestart_enabled:
        existing_specs = list(specs)
        for spec in existing_specs:
            add_spec(
                name=warm_helper_prestart_variant_profile_name(
                    str(spec["name"]),
                    warm_helper_prestart_enabled=False,
                ),
                base_profile_name=str(spec["base_profile_name"]),
                extra_post_warm_wait_seconds=float(spec["extra_post_warm_wait_seconds"]),
                conflux_client_ux=(
                    str(spec["conflux_client_ux"])
                    if spec.get("conflux_client_ux") is not None
                    else None
                ),
                browser_startup_seed_enabled=bool(
                    spec.get(
                        "browser_startup_seed_enabled",
                        base_browser_startup_seed_enabled,
                    )
                ),
                record_browser_startup_seed_field=(
                    "browser_startup_seed_enabled" in spec
                ),
                persistent_control_wait_enabled=bool(
                    spec.get(
                        "persistent_control_wait_enabled",
                        base_persistent_control_wait_enabled,
                    )
                ),
                record_persistent_control_wait_field=(
                    "persistent_control_wait_enabled" in spec
                ),
                async_browser_reset_enabled=bool(
                    spec.get(
                        "async_browser_reset_enabled",
                        base_async_browser_reset_enabled,
                    )
                ),
                record_async_browser_reset_field=(
                    "async_browser_reset_enabled" in spec
                ),
                managed_open_settle_enabled=bool(
                    spec.get(
                        "managed_open_settle_enabled",
                        base_managed_open_settle_enabled,
                    )
                ),
                record_managed_open_settle_field=(
                    "managed_open_settle_enabled" in spec
                ),
                managed_open_browser_overlap_enabled=bool(
                    spec.get(
                        "managed_open_browser_overlap_enabled",
                        base_managed_open_browser_overlap_enabled,
                    )
                ),
                record_managed_open_browser_overlap_field=(
                    "managed_open_browser_overlap_enabled" in spec
                ),
                warm_helper_prestart_enabled=False,
                record_warm_helper_prestart_field=True,
                warm_browser_prestart_enabled=bool(
                    spec.get(
                        "warm_browser_prestart_enabled",
                        base_warm_browser_prestart_enabled,
                    )
                ),
                record_warm_browser_prestart_field=(
                    "warm_browser_prestart_enabled" in spec
                ),
            )

    if extra_no_warm_browser_prestart and base_warm_browser_prestart_enabled:
        existing_specs = list(specs)
        for spec in existing_specs:
            add_spec(
                name=warm_browser_prestart_variant_profile_name(
                    str(spec["name"]),
                    warm_browser_prestart_enabled=False,
                ),
                base_profile_name=str(spec["base_profile_name"]),
                extra_post_warm_wait_seconds=float(spec["extra_post_warm_wait_seconds"]),
                conflux_client_ux=(
                    str(spec["conflux_client_ux"])
                    if spec.get("conflux_client_ux") is not None
                    else None
                ),
                browser_startup_seed_enabled=bool(
                    spec.get(
                        "browser_startup_seed_enabled",
                        base_browser_startup_seed_enabled,
                    )
                ),
                record_browser_startup_seed_field=(
                    "browser_startup_seed_enabled" in spec
                ),
                persistent_control_wait_enabled=bool(
                    spec.get(
                        "persistent_control_wait_enabled",
                        base_persistent_control_wait_enabled,
                    )
                ),
                record_persistent_control_wait_field=(
                    "persistent_control_wait_enabled" in spec
                ),
                async_browser_reset_enabled=bool(
                    spec.get(
                        "async_browser_reset_enabled",
                        base_async_browser_reset_enabled,
                    )
                ),
                record_async_browser_reset_field=(
                    "async_browser_reset_enabled" in spec
                ),
                managed_open_settle_enabled=bool(
                    spec.get(
                        "managed_open_settle_enabled",
                        base_managed_open_settle_enabled,
                    )
                ),
                record_managed_open_settle_field=(
                    "managed_open_settle_enabled" in spec
                ),
                managed_open_browser_overlap_enabled=bool(
                    spec.get(
                        "managed_open_browser_overlap_enabled",
                        base_managed_open_browser_overlap_enabled,
                    )
                ),
                record_managed_open_browser_overlap_field=(
                    "managed_open_browser_overlap_enabled" in spec
                ),
                warm_helper_prestart_enabled=bool(
                    spec.get(
                        "warm_helper_prestart_enabled",
                        base_warm_helper_prestart_enabled,
                    )
                ),
                record_warm_helper_prestart_field=(
                    "warm_helper_prestart_enabled" in spec
                ),
                warm_browser_prestart_enabled=False,
                record_warm_browser_prestart_field=True,
            )

    browser_startup_seed_variant_enabled: bool | None = None
    if base_browser_startup_seed_enabled and extra_no_browser_startup_seed:
        browser_startup_seed_variant_enabled = False
    elif (
        not base_browser_startup_seed_enabled
        and extra_browser_startup_seed
    ):
        browser_startup_seed_variant_enabled = True

    if browser_startup_seed_variant_enabled is not None:
        existing_specs = list(specs)
        for spec in existing_specs:
            current_browser_startup_seed_enabled = bool(
                spec.get(
                    "browser_startup_seed_enabled",
                    base_browser_startup_seed_enabled,
                )
            )
            if (
                current_browser_startup_seed_enabled
                == browser_startup_seed_variant_enabled
            ):
                continue
            add_spec(
                name=browser_startup_seed_variant_profile_name(
                    str(spec["name"]),
                    browser_startup_seed_enabled=browser_startup_seed_variant_enabled,
                ),
                base_profile_name=str(spec["base_profile_name"]),
                extra_post_warm_wait_seconds=float(spec["extra_post_warm_wait_seconds"]),
                conflux_client_ux=(
                    str(spec["conflux_client_ux"])
                    if spec.get("conflux_client_ux") is not None
                    else None
                ),
                browser_startup_seed_enabled=browser_startup_seed_variant_enabled,
                record_browser_startup_seed_field=True,
                persistent_control_wait_enabled=bool(
                    spec.get(
                        "persistent_control_wait_enabled",
                        base_persistent_control_wait_enabled,
                    )
                ),
                record_persistent_control_wait_field=(
                    "persistent_control_wait_enabled" in spec
                ),
                async_browser_reset_enabled=bool(
                    spec.get(
                        "async_browser_reset_enabled",
                        base_async_browser_reset_enabled,
                    )
                ),
                record_async_browser_reset_field=(
                    "async_browser_reset_enabled" in spec
                ),
                managed_open_settle_enabled=bool(
                    spec.get(
                        "managed_open_settle_enabled",
                        base_managed_open_settle_enabled,
                    )
                ),
                record_managed_open_settle_field=("managed_open_settle_enabled" in spec),
                managed_open_browser_overlap_enabled=bool(
                    spec.get(
                        "managed_open_browser_overlap_enabled",
                        base_managed_open_browser_overlap_enabled,
                    )
                ),
                record_managed_open_browser_overlap_field=(
                    "managed_open_browser_overlap_enabled" in spec
                ),
                warm_helper_prestart_enabled=bool(
                    spec.get(
                        "warm_helper_prestart_enabled",
                        base_warm_helper_prestart_enabled,
                    )
                ),
                record_warm_helper_prestart_field=(
                    "warm_helper_prestart_enabled" in spec
                ),
                warm_browser_prestart_enabled=bool(
                    spec.get(
                        "warm_browser_prestart_enabled",
                        base_warm_browser_prestart_enabled,
                    )
                ),
                record_warm_browser_prestart_field=(
                    "warm_browser_prestart_enabled" in spec
                ),
            )
    if extra_no_async_browser_reset and base_async_browser_reset_enabled:
        existing_specs = list(specs)
        for spec in existing_specs:
            current_async_browser_reset_enabled = bool(
                spec.get(
                    "async_browser_reset_enabled",
                    base_async_browser_reset_enabled,
                )
            )
            if not current_async_browser_reset_enabled:
                continue
            add_spec(
                name=async_browser_reset_variant_profile_name(
                    str(spec["name"]),
                    async_browser_reset_enabled=False,
                ),
                base_profile_name=str(spec["base_profile_name"]),
                extra_post_warm_wait_seconds=float(spec["extra_post_warm_wait_seconds"]),
                conflux_client_ux=(
                    str(spec["conflux_client_ux"])
                    if spec.get("conflux_client_ux") is not None
                    else None
                ),
                browser_startup_seed_enabled=bool(
                    spec.get(
                        "browser_startup_seed_enabled",
                        base_browser_startup_seed_enabled,
                    )
                ),
                record_browser_startup_seed_field=(
                    "browser_startup_seed_enabled" in spec
                ),
                persistent_control_wait_enabled=bool(
                    spec.get(
                        "persistent_control_wait_enabled",
                        base_persistent_control_wait_enabled,
                    )
                ),
                record_persistent_control_wait_field=(
                    "persistent_control_wait_enabled" in spec
                ),
                async_browser_reset_enabled=False,
                record_async_browser_reset_field=True,
                managed_open_settle_enabled=bool(
                    spec.get(
                        "managed_open_settle_enabled",
                        base_managed_open_settle_enabled,
                    )
                ),
                record_managed_open_settle_field=(
                    "managed_open_settle_enabled" in spec
                ),
                managed_open_browser_overlap_enabled=bool(
                    spec.get(
                        "managed_open_browser_overlap_enabled",
                        base_managed_open_browser_overlap_enabled,
                    )
                ),
                record_managed_open_browser_overlap_field=(
                    "managed_open_browser_overlap_enabled" in spec
                ),
                warm_helper_prestart_enabled=bool(
                    spec.get(
                        "warm_helper_prestart_enabled",
                        base_warm_helper_prestart_enabled,
                    )
                ),
                record_warm_helper_prestart_field=(
                    "warm_helper_prestart_enabled" in spec
                ),
                warm_browser_prestart_enabled=bool(
                    spec.get(
                        "warm_browser_prestart_enabled",
                        base_warm_browser_prestart_enabled,
                    )
                ),
                record_warm_browser_prestart_field=(
                    "warm_browser_prestart_enabled" in spec
                ),
            )
    if extra_no_persistent_control_wait:
        existing_specs = list(specs)
        for spec in existing_specs:
            current_persistent_control_wait_enabled = bool(
                spec.get(
                    "persistent_control_wait_enabled",
                    base_persistent_control_wait_enabled,
                )
            )
            if not current_persistent_control_wait_enabled:
                continue
            add_spec(
                name=persistent_control_wait_variant_profile_name(
                    str(spec["name"]),
                    persistent_control_wait_enabled=False,
                ),
                base_profile_name=str(spec["base_profile_name"]),
                extra_post_warm_wait_seconds=float(spec["extra_post_warm_wait_seconds"]),
                conflux_client_ux=(
                    str(spec["conflux_client_ux"])
                    if spec.get("conflux_client_ux") is not None
                    else None
                ),
                browser_startup_seed_enabled=bool(
                    spec.get(
                        "browser_startup_seed_enabled",
                        base_browser_startup_seed_enabled,
                    )
                ),
                record_browser_startup_seed_field=(
                    "browser_startup_seed_enabled" in spec
                ),
                persistent_control_wait_enabled=False,
                record_persistent_control_wait_field=True,
                control_bootstrap_probe_enabled=bool(
                    spec.get(
                        "control_bootstrap_probe_enabled",
                        base_control_bootstrap_probe_enabled,
                    )
                ),
                record_control_bootstrap_probe_field=(
                    "control_bootstrap_probe_enabled" in spec
                ),
                async_browser_reset_enabled=bool(
                    spec.get(
                        "async_browser_reset_enabled",
                        base_async_browser_reset_enabled,
                    )
                ),
                record_async_browser_reset_field=(
                    "async_browser_reset_enabled" in spec
                ),
                managed_open_settle_enabled=bool(
                    spec.get(
                        "managed_open_settle_enabled",
                        base_managed_open_settle_enabled,
                    )
                ),
                record_managed_open_settle_field=("managed_open_settle_enabled" in spec),
                managed_open_browser_overlap_enabled=bool(
                    spec.get(
                        "managed_open_browser_overlap_enabled",
                        base_managed_open_browser_overlap_enabled,
                    )
                ),
                record_managed_open_browser_overlap_field=(
                    "managed_open_browser_overlap_enabled" in spec
                ),
                warm_helper_prestart_enabled=bool(
                    spec.get(
                        "warm_helper_prestart_enabled",
                        base_warm_helper_prestart_enabled,
                    )
                ),
                record_warm_helper_prestart_field=(
                    "warm_helper_prestart_enabled" in spec
                ),
                warm_browser_prestart_enabled=bool(
                    spec.get(
                        "warm_browser_prestart_enabled",
                        base_warm_browser_prestart_enabled,
                    )
                ),
                record_warm_browser_prestart_field=(
                    "warm_browser_prestart_enabled" in spec
                ),
            )
    if extra_no_control_bootstrap_probe:
        existing_specs = list(specs)
        for spec in existing_specs:
            current_control_bootstrap_probe_enabled = bool(
                spec.get(
                    "control_bootstrap_probe_enabled",
                    base_control_bootstrap_probe_enabled,
                )
            )
            if not current_control_bootstrap_probe_enabled:
                continue
            add_spec(
                name=control_bootstrap_probe_variant_profile_name(
                    str(spec["name"]),
                    control_bootstrap_probe_enabled=False,
                ),
                base_profile_name=str(spec["base_profile_name"]),
                extra_post_warm_wait_seconds=float(spec["extra_post_warm_wait_seconds"]),
                conflux_client_ux=(
                    str(spec["conflux_client_ux"])
                    if spec.get("conflux_client_ux") is not None
                    else None
                ),
                browser_startup_seed_enabled=bool(
                    spec.get(
                        "browser_startup_seed_enabled",
                        base_browser_startup_seed_enabled,
                    )
                ),
                record_browser_startup_seed_field=(
                    "browser_startup_seed_enabled" in spec
                ),
                persistent_control_wait_enabled=bool(
                    spec.get(
                        "persistent_control_wait_enabled",
                        base_persistent_control_wait_enabled,
                    )
                ),
                record_persistent_control_wait_field=(
                    "persistent_control_wait_enabled" in spec
                ),
                control_bootstrap_probe_enabled=False,
                record_control_bootstrap_probe_field=True,
                async_browser_reset_enabled=bool(
                    spec.get(
                        "async_browser_reset_enabled",
                        base_async_browser_reset_enabled,
                    )
                ),
                record_async_browser_reset_field=(
                    "async_browser_reset_enabled" in spec
                ),
                managed_open_settle_enabled=bool(
                    spec.get(
                        "managed_open_settle_enabled",
                        base_managed_open_settle_enabled,
                    )
                ),
                record_managed_open_settle_field=("managed_open_settle_enabled" in spec),
                managed_open_browser_overlap_enabled=bool(
                    spec.get(
                        "managed_open_browser_overlap_enabled",
                        base_managed_open_browser_overlap_enabled,
                    )
                ),
                record_managed_open_browser_overlap_field=(
                    "managed_open_browser_overlap_enabled" in spec
                ),
                warm_helper_prestart_enabled=bool(
                    spec.get(
                        "warm_helper_prestart_enabled",
                        base_warm_helper_prestart_enabled,
                    )
                ),
                record_warm_helper_prestart_field=(
                    "warm_helper_prestart_enabled" in spec
                ),
                warm_browser_prestart_enabled=bool(
                    spec.get(
                        "warm_browser_prestart_enabled",
                        base_warm_browser_prestart_enabled,
                    )
                ),
                record_warm_browser_prestart_field=(
                    "warm_browser_prestart_enabled" in spec
                ),
            )
    if extra_no_managed_service_metadata_wait:
        existing_specs = list(specs)
        for spec in existing_specs:
            current_managed_service_metadata_wait_enabled = bool(
                spec.get(
                    "managed_service_metadata_wait_enabled",
                    base_managed_service_metadata_wait_enabled,
                )
            )
            if not current_managed_service_metadata_wait_enabled:
                continue
            add_spec(
                name=managed_service_metadata_wait_variant_profile_name(
                    str(spec["name"]),
                    managed_service_metadata_wait_enabled=False,
                ),
                base_profile_name=str(spec["base_profile_name"]),
                extra_post_warm_wait_seconds=float(spec["extra_post_warm_wait_seconds"]),
                conflux_client_ux=(
                    str(spec["conflux_client_ux"])
                    if spec.get("conflux_client_ux") is not None
                    else None
                ),
                browser_startup_seed_enabled=bool(
                    spec.get(
                        "browser_startup_seed_enabled",
                        base_browser_startup_seed_enabled,
                    )
                ),
                record_browser_startup_seed_field=(
                    "browser_startup_seed_enabled" in spec
                ),
                persistent_control_wait_enabled=bool(
                    spec.get(
                        "persistent_control_wait_enabled",
                        base_persistent_control_wait_enabled,
                    )
                ),
                record_persistent_control_wait_field=(
                    "persistent_control_wait_enabled" in spec
                ),
                control_bootstrap_probe_enabled=bool(
                    spec.get(
                        "control_bootstrap_probe_enabled",
                        base_control_bootstrap_probe_enabled,
                    )
                ),
                record_control_bootstrap_probe_field=(
                    "control_bootstrap_probe_enabled" in spec
                ),
                async_browser_reset_enabled=bool(
                    spec.get(
                        "async_browser_reset_enabled",
                        base_async_browser_reset_enabled,
                    )
                ),
                record_async_browser_reset_field=(
                    "async_browser_reset_enabled" in spec
                ),
                managed_service_metadata_wait_enabled=False,
                record_managed_service_metadata_wait_field=True,
                managed_open_settle_enabled=bool(
                    spec.get(
                        "managed_open_settle_enabled",
                        base_managed_open_settle_enabled,
                    )
                ),
                record_managed_open_settle_field=(
                    "managed_open_settle_enabled" in spec
                ),
                managed_open_browser_overlap_enabled=bool(
                    spec.get(
                        "managed_open_browser_overlap_enabled",
                        base_managed_open_browser_overlap_enabled,
                    )
                ),
                record_managed_open_browser_overlap_field=(
                    "managed_open_browser_overlap_enabled" in spec
                ),
                warm_helper_prestart_enabled=bool(
                    spec.get(
                        "warm_helper_prestart_enabled",
                        base_warm_helper_prestart_enabled,
                    )
                ),
                record_warm_helper_prestart_field=(
                    "warm_helper_prestart_enabled" in spec
                ),
                warm_browser_prestart_enabled=bool(
                    spec.get(
                        "warm_browser_prestart_enabled",
                        base_warm_browser_prestart_enabled,
                    )
                ),
                record_warm_browser_prestart_field=(
                    "warm_browser_prestart_enabled" in spec
                ),
            )
    if extra_adaptive_general_circuit_wait_timeout_seconds:
        existing_specs = list(specs)
        for spec in existing_specs:
            current_timeout = float(
                spec.get("adaptive_general_circuit_wait_timeout_seconds", 0.0)
            )
            for timeout_seconds in (
                extra_adaptive_general_circuit_wait_timeout_seconds
            ):
                if current_timeout == timeout_seconds:
                    continue
                add_spec(
                    name=adaptive_general_circuit_wait_variant_profile_name(
                        str(spec["name"]),
                        timeout_seconds,
                    ),
                    base_profile_name=str(spec["base_profile_name"]),
                    extra_post_warm_wait_seconds=float(
                        spec["extra_post_warm_wait_seconds"]
                    ),
                    conflux_client_ux=(
                        str(spec["conflux_client_ux"])
                        if spec.get("conflux_client_ux") is not None
                        else None
                    ),
                    browser_startup_seed_enabled=bool(
                        spec.get(
                            "browser_startup_seed_enabled",
                            base_browser_startup_seed_enabled,
                        )
                    ),
                    record_browser_startup_seed_field=(
                        "browser_startup_seed_enabled" in spec
                    ),
                    persistent_control_wait_enabled=bool(
                        spec.get(
                            "persistent_control_wait_enabled",
                            base_persistent_control_wait_enabled,
                        )
                    ),
                    record_persistent_control_wait_field=(
                        "persistent_control_wait_enabled" in spec
                    ),
                    control_bootstrap_probe_enabled=bool(
                        spec.get(
                            "control_bootstrap_probe_enabled",
                            base_control_bootstrap_probe_enabled,
                        )
                    ),
                    record_control_bootstrap_probe_field=(
                        "control_bootstrap_probe_enabled" in spec
                    ),
                    async_browser_reset_enabled=bool(
                        spec.get(
                            "async_browser_reset_enabled",
                            base_async_browser_reset_enabled,
                        )
                    ),
                    record_async_browser_reset_field=(
                        "async_browser_reset_enabled" in spec
                    ),
                    managed_service_metadata_wait_enabled=bool(
                        spec.get(
                            "managed_service_metadata_wait_enabled",
                            base_managed_service_metadata_wait_enabled,
                        )
                    ),
                    record_managed_service_metadata_wait_field=(
                        "managed_service_metadata_wait_enabled" in spec
                    ),
                    managed_open_settle_enabled=bool(
                        spec.get(
                            "managed_open_settle_enabled",
                            base_managed_open_settle_enabled,
                        )
                    ),
                    record_managed_open_settle_field=(
                        "managed_open_settle_enabled" in spec
                    ),
                    managed_open_browser_overlap_enabled=bool(
                        spec.get(
                            "managed_open_browser_overlap_enabled",
                            base_managed_open_browser_overlap_enabled,
                        )
                    ),
                    record_managed_open_browser_overlap_field=(
                        "managed_open_browser_overlap_enabled" in spec
                    ),
                    warm_helper_prestart_enabled=bool(
                        spec.get(
                            "warm_helper_prestart_enabled",
                            base_warm_helper_prestart_enabled,
                        )
                    ),
                    record_warm_helper_prestart_field=(
                        "warm_helper_prestart_enabled" in spec
                    ),
                    warm_browser_prestart_enabled=bool(
                        spec.get(
                            "warm_browser_prestart_enabled",
                            base_warm_browser_prestart_enabled,
                        )
                    ),
                    record_warm_browser_prestart_field=(
                        "warm_browser_prestart_enabled" in spec
                    ),
                    adaptive_general_circuit_wait_timeout_seconds=timeout_seconds,
                    record_adaptive_general_circuit_wait_timeout_field=True,
                )
    if extra_managed_open_adaptive_general_circuit_wait_timeout_seconds:
        existing_specs = list(specs)
        for spec in existing_specs:
            current_timeout = float(
                spec.get(
                    "managed_open_adaptive_general_circuit_wait_timeout_seconds",
                    0.0,
                )
            )
            for timeout_seconds in (
                extra_managed_open_adaptive_general_circuit_wait_timeout_seconds
            ):
                if current_timeout == timeout_seconds:
                    continue
                add_spec(
                    name=managed_open_adaptive_general_circuit_wait_variant_profile_name(
                        str(spec["name"]),
                        timeout_seconds,
                    ),
                    base_profile_name=str(spec["base_profile_name"]),
                    extra_post_warm_wait_seconds=float(
                        spec["extra_post_warm_wait_seconds"]
                    ),
                    conflux_client_ux=(
                        str(spec["conflux_client_ux"])
                        if spec.get("conflux_client_ux") is not None
                        else None
                    ),
                    browser_startup_seed_enabled=bool(
                        spec.get(
                            "browser_startup_seed_enabled",
                            base_browser_startup_seed_enabled,
                        )
                    ),
                    record_browser_startup_seed_field=(
                        "browser_startup_seed_enabled" in spec
                    ),
                    persistent_control_wait_enabled=bool(
                        spec.get(
                            "persistent_control_wait_enabled",
                            base_persistent_control_wait_enabled,
                        )
                    ),
                    record_persistent_control_wait_field=(
                        "persistent_control_wait_enabled" in spec
                    ),
                    control_bootstrap_probe_enabled=bool(
                        spec.get(
                            "control_bootstrap_probe_enabled",
                            base_control_bootstrap_probe_enabled,
                        )
                    ),
                    record_control_bootstrap_probe_field=(
                        "control_bootstrap_probe_enabled" in spec
                    ),
                    async_browser_reset_enabled=bool(
                        spec.get(
                            "async_browser_reset_enabled",
                            base_async_browser_reset_enabled,
                        )
                    ),
                    record_async_browser_reset_field=(
                        "async_browser_reset_enabled" in spec
                    ),
                    managed_service_metadata_wait_enabled=bool(
                        spec.get(
                            "managed_service_metadata_wait_enabled",
                            base_managed_service_metadata_wait_enabled,
                        )
                    ),
                    record_managed_service_metadata_wait_field=(
                        "managed_service_metadata_wait_enabled" in spec
                    ),
                    managed_open_settle_enabled=bool(
                        spec.get(
                            "managed_open_settle_enabled",
                            base_managed_open_settle_enabled,
                        )
                    ),
                    record_managed_open_settle_field=(
                        "managed_open_settle_enabled" in spec
                    ),
                    managed_open_browser_overlap_enabled=bool(
                        spec.get(
                            "managed_open_browser_overlap_enabled",
                            base_managed_open_browser_overlap_enabled,
                        )
                    ),
                    record_managed_open_browser_overlap_field=(
                        "managed_open_browser_overlap_enabled" in spec
                    ),
                    warm_helper_prestart_enabled=bool(
                        spec.get(
                            "warm_helper_prestart_enabled",
                            base_warm_helper_prestart_enabled,
                        )
                    ),
                    record_warm_helper_prestart_field=(
                        "warm_helper_prestart_enabled" in spec
                    ),
                    warm_browser_prestart_enabled=bool(
                        spec.get(
                            "warm_browser_prestart_enabled",
                            base_warm_browser_prestart_enabled,
                        )
                    ),
                    record_warm_browser_prestart_field=(
                        "warm_browser_prestart_enabled" in spec
                    ),
                    managed_open_adaptive_general_circuit_wait_timeout_seconds=(
                        timeout_seconds
                    ),
                    record_managed_open_adaptive_general_circuit_wait_timeout_field=True,
                    adaptive_general_circuit_wait_timeout_seconds=float(
                        spec.get("adaptive_general_circuit_wait_timeout_seconds", 0.0)
                    ),
                    record_adaptive_general_circuit_wait_timeout_field=(
                        "adaptive_general_circuit_wait_timeout_seconds" in spec
                    ),
                )
    return specs


def cycle_profile_order(cycle: int, profile_specs: list[dict[str, object]]) -> list[dict[str, object]]:
    if not profile_specs:
        return []
    offset = (cycle - 1) % len(profile_specs)
    return profile_specs[offset:] + profile_specs[:offset]


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
    base_profile_name: str,
    extra_post_warm_wait_seconds: float,
    managed_open_settle_enabled: bool,
    managed_open_browser_overlap_enabled: bool,
    cycle: int,
    port: int,
    requested_port: int,
    browser_bin: Path,
    tor_bin: Path,
    conflux_client_ux: str | None,
    browser_timeout: float,
    browser_startup_seed_root: Path,
    browser_startup_seed_enabled: bool,
    persistent_control_wait_enabled: bool,
    control_bootstrap_probe_enabled: bool,
    async_browser_reset_enabled: bool,
    managed_service_metadata_wait_enabled: bool,
    warm_helper_prestart_enabled: bool,
    warm_browser_prestart_enabled: bool,
    managed_open_adaptive_general_circuit_wait_timeout_seconds: float,
    adaptive_general_circuit_wait_timeout_seconds: float,
    headed: bool,
    wait_ready_after_post_warm_wait: bool,
    wait_ready_gate: str,
    wait_ready_timeout: float,
    gate_diagnostics: bool = False,
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
        "base_profile_name": base_profile_name,
        "cycle": cycle,
        "port": port,
        "requested_port": requested_port,
        "run_dir": str(run_dir),
        "state_root": str(state_root),
        "post_warm_wait_seconds": extra_post_warm_wait_seconds,
        "browser_startup_seed_enabled": browser_startup_seed_enabled,
        "persistent_control_wait_enabled": persistent_control_wait_enabled,
        "control_bootstrap_probe_enabled": control_bootstrap_probe_enabled,
        "async_browser_reset_enabled": async_browser_reset_enabled,
        "managed_service_metadata_wait_enabled": (
            managed_service_metadata_wait_enabled
        ),
        "managed_open_settle_enabled": managed_open_settle_enabled,
        "managed_open_browser_overlap_enabled": (
            managed_open_browser_overlap_enabled
        ),
        "warm_helper_prestart_enabled": warm_helper_prestart_enabled,
        "warm_browser_prestart_enabled": warm_browser_prestart_enabled,
        "managed_open_adaptive_general_circuit_wait_timeout_seconds": (
            managed_open_adaptive_general_circuit_wait_timeout_seconds
        ),
        "adaptive_general_circuit_wait_enabled": (
            adaptive_general_circuit_wait_timeout_seconds > 0
        ),
        "adaptive_general_circuit_wait_timeout_seconds": (
            adaptive_general_circuit_wait_timeout_seconds
        ),
        "wait_ready_enabled": (
            wait_ready_after_post_warm_wait and extra_post_warm_wait_seconds > 0
        ),
        "wait_ready_gate": wait_ready_gate,
        "wait_ready_timeout_seconds": wait_ready_timeout,
    }

    warm_command = build_torfast_command(
        action="warm",
        state_root=state_root,
        browser_bin=browser_bin,
        tor_bin=tor_bin,
        target=target,
        port=port,
        profile_name=base_profile_name,
        conflux_client_ux=conflux_client_ux,
        browser_timeout=browser_timeout,
        browser_startup_seed_root=browser_startup_seed_root,
        browser_startup_seed_enabled=browser_startup_seed_enabled,
        managed_open_settle_enabled=managed_open_settle_enabled,
        managed_open_browser_overlap_enabled=managed_open_browser_overlap_enabled,
        managed_open_adaptive_general_circuit_wait_timeout_seconds=(
            managed_open_adaptive_general_circuit_wait_timeout_seconds
        ),
        warm_browser_prestart_enabled=warm_browser_prestart_enabled,
        headed=headed,
        gate_diagnostics=gate_diagnostics,
    )
    warm_run = run_command(
        warm_command,
        env_overrides=torfast_command_env(
            action="warm",
            persistent_control_wait_enabled=persistent_control_wait_enabled,
            control_bootstrap_probe_enabled=control_bootstrap_probe_enabled,
            async_browser_reset_enabled=async_browser_reset_enabled,
            managed_service_metadata_wait_enabled=(
                managed_service_metadata_wait_enabled
            ),
            warm_helper_prestart_enabled=warm_helper_prestart_enabled,
        ),
    )
    warm_launch = read_json_file(state_root / "launch.json")
    result["warm"] = warm_run
    result["warm_launch"] = compact_launch(warm_launch)

    open_launch: dict[str, object] | None = None
    wait_ready_run: dict[str, object] | None = None
    wait_ready_response: dict[str, object] | None = None
    adaptive_general_circuit_wait: dict[str, object] | None = None
    if warm_run.get("ok"):
        if extra_post_warm_wait_seconds > 0:
            time.sleep(extra_post_warm_wait_seconds)
        if wait_ready_after_post_warm_wait and extra_post_warm_wait_seconds > 0:
            wait_ready_command = build_wait_ready_command(
                state_root=state_root,
                gate=wait_ready_gate,
                timeout=wait_ready_timeout,
            )
            wait_ready_run = run_command(
                wait_ready_command,
                env_overrides=torfast_command_env(
                    action="wait-ready",
                    persistent_control_wait_enabled=(
                        persistent_control_wait_enabled
                    ),
                    control_bootstrap_probe_enabled=(
                        control_bootstrap_probe_enabled
                    ),
                    async_browser_reset_enabled=async_browser_reset_enabled,
                    managed_service_metadata_wait_enabled=(
                        managed_service_metadata_wait_enabled
                    ),
                    warm_helper_prestart_enabled=warm_helper_prestart_enabled,
                ),
            )
            wait_ready_response = wait_ready_run.get("stdout_json")
            if not isinstance(wait_ready_response, dict):
                wait_ready_response = None
        if wait_ready_run is None or wait_ready_run.get("ok"):
            if adaptive_general_circuit_wait_timeout_seconds > 0:
                adaptive_general_circuit_wait = (
                    maybe_wait_for_managed_general_circuit(
                        result,
                        timeout_seconds=(
                            adaptive_general_circuit_wait_timeout_seconds
                        ),
                    )
                )
            open_command = build_torfast_command(
                action="open",
                state_root=state_root,
                browser_bin=browser_bin,
                tor_bin=tor_bin,
                target=target,
                port=port,
                profile_name=base_profile_name,
                conflux_client_ux=conflux_client_ux,
                browser_timeout=browser_timeout,
                browser_startup_seed_root=browser_startup_seed_root,
                browser_startup_seed_enabled=browser_startup_seed_enabled,
                managed_open_settle_enabled=managed_open_settle_enabled,
                managed_open_browser_overlap_enabled=(
                    managed_open_browser_overlap_enabled
                ),
                managed_open_adaptive_general_circuit_wait_timeout_seconds=(
                    managed_open_adaptive_general_circuit_wait_timeout_seconds
                ),
                warm_browser_prestart_enabled=warm_browser_prestart_enabled,
                headed=headed,
                gate_diagnostics=gate_diagnostics,
            )
            open_run = run_command(
                open_command,
                env_overrides=torfast_command_env(
                    action="open",
                    persistent_control_wait_enabled=(
                        persistent_control_wait_enabled
                    ),
                    control_bootstrap_probe_enabled=(
                        control_bootstrap_probe_enabled
                    ),
                    async_browser_reset_enabled=async_browser_reset_enabled,
                    managed_service_metadata_wait_enabled=(
                        managed_service_metadata_wait_enabled
                    ),
                    warm_helper_prestart_enabled=warm_helper_prestart_enabled,
                ),
            )
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
    else:
        open_run = {
            "ok": False,
            "skipped": True,
            "exit_code": None,
            "wall_seconds": None,
            "stdout_tail": [],
            "stderr_tail": [],
        }
    result["wait_ready"] = wait_ready_run
    result["wait_ready_response"] = wait_ready_response
    result["adaptive_general_circuit_wait"] = adaptive_general_circuit_wait
    result["open"] = open_run
    result["open_launch"] = compact_launch(open_launch)

    stop_command = build_stop_command(state_root)
    stop_run = run_command(stop_command)
    stop_payload = stop_run.get("stdout_json")
    if not isinstance(stop_payload, dict):
        stop_payload = None
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
    conflux_client_ux: str | None,
    browser_timeout: float,
    browser_startup_seed_root: Path,
    browser_startup_seed_enabled: bool,
    managed_open_settle_enabled: bool = False,
    managed_open_browser_overlap_enabled: bool = False,
    managed_open_adaptive_general_circuit_wait_timeout_seconds: float = 0.0,
    warm_browser_prestart_enabled: bool = False,
    headed: bool,
    gate_diagnostics: bool = False,
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
    if conflux_client_ux:
        command.extend(["--conflux-client-ux", conflux_client_ux])
    if profile_name != "auto":
        command.extend(["--browser-launch-gate", profile_name])
    if browser_startup_seed_enabled:
        command.append("--browser-startup-seed")
    else:
        command.append("--no-browser-startup-seed")
    if managed_open_settle_enabled:
        command.append("--managed-open-settle")
    if managed_open_browser_overlap_enabled:
        command.append("--managed-open-browser-overlap")
    else:
        command.append("--no-managed-open-browser-overlap")
    # Always pass the value explicitly so a 0.0 baseline row stays disabled
    # even when the product default promotes a non-zero wait.
    command.extend(
        [
            "--managed-open-adaptive-general-circuit-wait-timeout",
            str(managed_open_adaptive_general_circuit_wait_timeout_seconds),
        ]
    )
    if warm_browser_prestart_enabled:
        command.append("--warm-browser-prestart")
    if action == "open":
        command.extend(["--browser-timeout", str(browser_timeout)])
        if not headed:
            command.append("--headless")
    if gate_diagnostics:
        command.append("--gate-diagnostics")
    return command


def torfast_command_env(
    *,
    action: str,
    persistent_control_wait_enabled: bool,
    control_bootstrap_probe_enabled: bool,
    async_browser_reset_enabled: bool,
    managed_service_metadata_wait_enabled: bool,
    warm_helper_prestart_enabled: bool,
) -> dict[str, str] | None:
    env: dict[str, str] = {}
    if action == "warm" and warm_helper_prestart_enabled:
        env[WARM_RUNTIME_HELPER_PRESTART_ENABLED_ENV] = "1"
    if persistent_control_wait_enabled:
        env[PERSISTENT_CONTROL_WAIT_ENABLED_ENV] = "1"
        env[PERSISTENT_CONTROL_WAIT_DISABLED_ENV] = "0"
    else:
        env[PERSISTENT_CONTROL_WAIT_ENABLED_ENV] = "0"
        env[PERSISTENT_CONTROL_WAIT_DISABLED_ENV] = "1"
    env[CONTROL_BOOTSTRAP_PROBE_DISABLED_ENV] = (
        "0" if control_bootstrap_probe_enabled else "1"
    )
    env[ASYNC_BROWSER_RESET_DISABLED_ENV] = (
        "" if async_browser_reset_enabled else "1"
    )
    env[MANAGED_SERVICE_METADATA_WAIT_DISABLED_ENV] = (
        "0" if managed_service_metadata_wait_enabled else "1"
    )
    env[TARGET_STREAM_PROOF_ENABLED_ENV] = "1" if action == "open" else "0"
    return env or None


def build_wait_ready_command(
    *,
    state_root: Path,
    gate: str,
    timeout: float,
) -> list[str]:
    return [
        sys.executable,
        "-m",
        "torfast",
        "wait-ready",
        "--state-root",
        str(state_root),
        "--gate",
        gate,
        "--timeout",
        str(timeout),
    ]


def build_stop_command(state_root: Path) -> list[str]:
    return [
        sys.executable,
        "-m",
        "torfast",
        "stop",
        "--state-root",
        str(state_root),
    ]


def run_command(
    command: list[str],
    *,
    env_overrides: dict[str, str] | None = None,
) -> dict[str, object]:
    started = time.monotonic()
    env = None
    if env_overrides:
        env = os.environ.copy()
        env.update(env_overrides)
    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        capture_output=True,
        env=env,
        text=True,
    )
    stdout_text = completed.stdout or ""
    return {
        "command": command,
        "ok": completed.returncode == 0,
        "exit_code": completed.returncode,
        "wall_seconds": round(time.monotonic() - started, 3),
        "stdout_json": parse_json_text(stdout_text),
        "stdout_tail": stdout_text.splitlines()[-80:],
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


def warm_service(result: dict[str, object]) -> dict[str, object] | None:
    warm_launch = result.get("warm_launch")
    if not isinstance(warm_launch, dict):
        return None
    service = warm_launch.get("reused_tor_service")
    return service if isinstance(service, dict) else None


def maybe_wait_for_managed_general_circuit(
    result: dict[str, object],
    *,
    timeout_seconds: float,
    poll_interval: float = ADAPTIVE_GENERAL_CIRCUIT_WAIT_POLL_INTERVAL_SECONDS,
) -> dict[str, object]:
    timeout_seconds = round(float(timeout_seconds), 3)
    payload: dict[str, object] = {
        "gate": "general_circuit",
        "enabled": timeout_seconds > 0,
        "timeout_seconds": timeout_seconds,
        "poll_interval_seconds": poll_interval,
    }
    if timeout_seconds <= 0:
        return {
            **payload,
            "ok": True,
            "skipped": True,
            "matched": False,
            "timed_out": False,
            "seconds": 0.0,
            "reason": "disabled",
        }

    service = warm_service(result)
    if not isinstance(service, dict):
        return {
            **payload,
            "ok": False,
            "skipped": True,
            "matched": False,
            "timed_out": False,
            "seconds": 0.0,
            "error": "warm launch missing reused_tor_service metadata",
        }
    control_port = service.get("control_port")
    control_cookie_path = service.get("control_cookie_path")
    if not isinstance(control_port, int) or not isinstance(control_cookie_path, str):
        return {
            **payload,
            "ok": False,
            "skipped": True,
            "matched": False,
            "timed_out": False,
            "seconds": 0.0,
            "error": "managed warm service metadata missing control-port support",
        }

    initial_snapshot = read_general_circuit_snapshot(
        host="127.0.0.1",
        port=control_port,
        cookie_path=Path(control_cookie_path),
    )
    payload["initial_snapshot"] = initial_snapshot
    if (
        initial_snapshot.get("ok") is True
        and isinstance(initial_snapshot.get("matched_circuit_count"), int)
        and initial_snapshot["matched_circuit_count"] >= 1
    ):
        return {
            **payload,
            "ok": True,
            "skipped": False,
            "matched": True,
            "timed_out": False,
            "seconds": 0.0,
            "reason": "already_ready",
            "matched_circuit_count": initial_snapshot.get("matched_circuit_count"),
        }

    started = time.monotonic()
    wait = wait_for_general_circuits(
        host="127.0.0.1",
        port=control_port,
        cookie_path=Path(control_cookie_path),
        timeout=timeout_seconds,
        poll_interval=poll_interval,
        min_count=1,
    )
    spent_seconds = wait.get("seconds")
    if not isinstance(spent_seconds, (int, float)):
        spent_seconds = round(time.monotonic() - started, 3)
    timed_out = wait.get("error") == "general circuit wait timeout"
    return {
        **payload,
        "ok": bool(wait.get("ok")) or timed_out,
        "skipped": False,
        "matched": bool(wait.get("ok")),
        "timed_out": timed_out,
        "seconds": round(float(spent_seconds), 3),
        "reason": "waited" if wait.get("ok") is True else "timeout_proceed",
        "matched_circuit_count": wait.get("matched_circuit_count"),
        "wait": wait,
    }


def result_ok(result: dict[str, object]) -> bool:
    warm = result.get("warm")
    warm_launch = result.get("warm_launch")
    open_run = result.get("open")
    open_launch = result.get("open_launch")
    stop = result.get("stop")
    wait_ready_enabled = bool(result.get("wait_ready_enabled"))

    if not isinstance(warm, dict) or warm.get("ok") is not True:
        return False
    if (
        not isinstance(warm_launch, dict)
        or not isinstance(warm_launch.get("tor_managed_ready"), dict)
        or warm_launch["tor_managed_ready"].get("ok") is not True
    ):
        return False
    if wait_ready_enabled:
        wait_ready = result.get("wait_ready")
        wait_ready_response = result.get("wait_ready_response")
        if not isinstance(wait_ready, dict) or wait_ready.get("ok") is not True:
            return False
        if (
            not isinstance(wait_ready_response, dict)
            or wait_ready_response.get("ok") is not True
        ):
            return False
    if not isinstance(open_run, dict) or open_run.get("ok") is not True:
        return False
    if not isinstance(open_launch, dict):
        return False
    browser = open_launch.get("browser")
    browser_default_pref_check = open_launch.get("browser_default_pref_check")
    browser_runtime_reset = open_launch.get("browser_runtime_reset")
    tor_boot = open_launch.get("tor_boot")
    torrc = open_launch.get("torrc_quality")
    reused = open_launch.get("reused_tor_service")
    if not isinstance(browser, dict) or browser.get("ok") is not True:
        return False
    if (
        target_requires_stream_proof(result.get("target"))
        and not target_navigation_proven(result)
    ):
        return False
    if (
        not isinstance(browser_default_pref_check, dict)
        or browser_default_pref_check.get("ok") is not True
    ):
        return False
    if (
        not isinstance(browser_runtime_reset, dict)
        or browser_runtime_reset.get("ok") is not True
    ):
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


def target_requires_stream_proof(target: object) -> bool:
    return isinstance(target, str) and urlparse(target).scheme.lower() in {
        "http",
        "https",
    }


def open_target_stream_snapshot(result: dict[str, object]) -> dict[str, object] | None:
    open_launch = result.get("open_launch")
    if not isinstance(open_launch, dict):
        return None
    browser = open_launch.get("browser")
    if isinstance(browser, dict):
        snapshot = browser.get("target_stream_snapshot")
        if isinstance(snapshot, dict):
            return snapshot
    adaptive_wait = open_launch.get("managed_open_adaptive_general_circuit_wait")
    if isinstance(adaptive_wait, dict):
        snapshot = adaptive_wait.get("target_stream_snapshot")
        if isinstance(snapshot, dict):
            return snapshot
    return None


def target_navigation_proven(result: dict[str, object]) -> bool:
    if not target_requires_stream_proof(result.get("target")):
        return True
    return user_stream_snapshot_observed(open_target_stream_snapshot(result))


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


def wait_ready_wall_seconds(result: dict[str, object]) -> float | None:
    wait_ready = result.get("wait_ready")
    if not isinstance(wait_ready, dict):
        return 0.0 if not bool(result.get("wait_ready_enabled")) else None
    seconds = wait_ready.get("wall_seconds")
    if isinstance(seconds, (int, float)):
        return round(float(seconds), 3)
    if wait_ready.get("skipped") is True:
        return 0.0
    return None


def adaptive_general_circuit_wait_seconds(result: dict[str, object]) -> float | None:
    adaptive_wait = result.get("adaptive_general_circuit_wait")
    if not isinstance(adaptive_wait, dict):
        return (
            0.0
            if not bool(result.get("adaptive_general_circuit_wait_enabled"))
            else None
        )
    seconds = adaptive_wait.get("seconds")
    if isinstance(seconds, (int, float)):
        return round(float(seconds), 3)
    if adaptive_wait.get("skipped") is True:
        return 0.0
    return None


def managed_open_adaptive_general_circuit_wait_seconds(
    result: dict[str, object],
) -> float | None:
    open_launch = result.get("open_launch")
    if not isinstance(open_launch, dict):
        return (
            0.0
            if not float(
                result.get(
                    "managed_open_adaptive_general_circuit_wait_timeout_seconds",
                    0.0,
                )
            )
            else None
        )
    adaptive_wait = open_launch.get("managed_open_adaptive_general_circuit_wait")
    if not isinstance(adaptive_wait, dict):
        return (
            0.0
            if not float(
                result.get(
                    "managed_open_adaptive_general_circuit_wait_timeout_seconds",
                    0.0,
                )
            )
            else None
        )
    seconds = adaptive_wait.get("seconds")
    if isinstance(seconds, (int, float)):
        return round(float(seconds), 3)
    if adaptive_wait.get("skipped") is True:
        return 0.0
    return None


def combined_wall_seconds(result: dict[str, object]) -> float | None:
    warm = result.get("warm")
    open_run = result.get("open")
    if not isinstance(warm, dict) or not isinstance(open_run, dict):
        return None
    warm_seconds = warm.get("wall_seconds")
    wait_ready_seconds_value = wait_ready_wall_seconds(result)
    open_seconds = open_run.get("wall_seconds")
    if not isinstance(warm_seconds, (int, float)) or not isinstance(
        open_seconds, (int, float)
    ):
        return None
    wait_ready_seconds = (
        0.0
        if not isinstance(wait_ready_seconds_value, (int, float))
        else float(wait_ready_seconds_value)
    )
    adaptive_general_circuit_seconds_value = adaptive_general_circuit_wait_seconds(
        result
    )
    adaptive_general_circuit_seconds = (
        0.0
        if not isinstance(adaptive_general_circuit_seconds_value, (int, float))
        else float(adaptive_general_circuit_seconds_value)
    )
    return round(
        float(warm_seconds)
        + wait_ready_seconds
        + adaptive_general_circuit_seconds
        + float(open_seconds),
        3,
    )


def total_wall_seconds(result: dict[str, object]) -> float | None:
    combined_seconds = combined_wall_seconds(result)
    if not isinstance(combined_seconds, (int, float)):
        return None
    post_warm_wait_seconds = result.get("post_warm_wait_seconds")
    hidden_wait_seconds = (
        0.0
        if not isinstance(post_warm_wait_seconds, (int, float))
        else float(post_warm_wait_seconds)
    )
    return round(float(combined_seconds) + hidden_wait_seconds, 3)


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
            open_launch_gate_values = [
                open_launch_gate_seconds(result) for result in ok_rows
            ]
            combined_wall_values = [
                combined_wall_seconds(result) for result in ok_rows
            ]
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
                "median_post_warm_wait_seconds": median_value(
                    [result.get("post_warm_wait_seconds") for result in ok_rows]
                ),
                "median_wait_ready_wall_seconds": median_value(
                    [wait_ready_wall_seconds(result) for result in ok_rows]
                ),
                "median_managed_open_adaptive_general_circuit_wait_seconds": (
                    median_value(
                        [
                            managed_open_adaptive_general_circuit_wait_seconds(
                                result
                            )
                            for result in ok_rows
                        ]
                    )
                ),
                "median_adaptive_general_circuit_wait_seconds": median_value(
                    [
                        adaptive_general_circuit_wait_seconds(result)
                        for result in ok_rows
                    ]
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
                    open_launch_gate_values
                ),
                "p90_open_launch_gate_seconds": percentile_value(
                    open_launch_gate_values,
                    90,
                ),
                "max_open_launch_gate_seconds": max_value(open_launch_gate_values),
                "median_open_full_boot_seconds": median_value(
                    [open_full_boot_seconds(result) for result in ok_rows]
                ),
                "median_combined_wall_seconds": median_value(
                    combined_wall_values
                ),
                "p90_combined_wall_seconds": percentile_value(
                    combined_wall_values,
                    90,
                ),
                "max_combined_wall_seconds": max_value(combined_wall_values),
                "median_total_wall_seconds": median_value(
                    [total_wall_seconds(result) for result in ok_rows]
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
                "browser_default_pref_check_ok_runs": sum(
                    1
                    for result in rows
                    if isinstance(
                        (
                            browser_default_pref_check := (
                                (result.get("open_launch") or {}).get(
                                    "browser_default_pref_check"
                                )
                            )
                        ),
                        dict,
                    )
                    and browser_default_pref_check.get("ok") is True
                ),
                "browser_runtime_reset_ok_runs": sum(
                    1
                    for result in rows
                    if isinstance(
                        (
                            browser_runtime_reset := (
                                (result.get("open_launch") or {}).get(
                                    "browser_runtime_reset"
                                )
                            )
                        ),
                        dict,
                    )
                    and browser_runtime_reset.get("ok") is True
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
                "wait_ready_ok_runs": sum(
                    1
                    for result in rows
                    if bool(result.get("wait_ready_enabled"))
                    and isinstance((wait_ready := result.get("wait_ready")), dict)
                    and wait_ready.get("ok") is True
                    and isinstance(
                        (wait_ready_response := result.get("wait_ready_response")),
                        dict,
                    )
                    and wait_ready_response.get("ok") is True
                ),
                "managed_open_adaptive_general_circuit_wait_ok_runs": sum(
                    1
                    for result in rows
                    if isinstance(
                        (
                            adaptive_wait := (
                                (result.get("open_launch") or {}).get(
                                    "managed_open_adaptive_general_circuit_wait"
                                )
                            )
                        ),
                        dict,
                    )
                    and adaptive_wait.get("ok") is True
                ),
                "managed_open_adaptive_general_circuit_wait_match_runs": sum(
                    1
                    for result in rows
                    if isinstance(
                        (
                            adaptive_wait := (
                                (result.get("open_launch") or {}).get(
                                    "managed_open_adaptive_general_circuit_wait"
                                )
                            )
                        ),
                        dict,
                    )
                    and adaptive_wait.get("matched") is True
                ),
                "managed_open_adaptive_general_circuit_wait_timeout_runs": sum(
                    1
                    for result in rows
                    if isinstance(
                        (
                            adaptive_wait := (
                                (result.get("open_launch") or {}).get(
                                    "managed_open_adaptive_general_circuit_wait"
                                )
                            )
                        ),
                        dict,
                    )
                    and adaptive_wait.get("timed_out") is True
                ),
                "adaptive_general_circuit_wait_ok_runs": sum(
                    1
                    for result in rows
                    if bool(result.get("adaptive_general_circuit_wait_enabled"))
                    and isinstance(
                        (
                            adaptive_wait := result.get(
                                "adaptive_general_circuit_wait"
                            )
                        ),
                        dict,
                    )
                    and adaptive_wait.get("ok") is True
                ),
                "adaptive_general_circuit_wait_match_runs": sum(
                    1
                    for result in rows
                    if isinstance(
                        (
                            adaptive_wait := result.get(
                                "adaptive_general_circuit_wait"
                            )
                        ),
                        dict,
                    )
                    and adaptive_wait.get("matched") is True
                ),
                "adaptive_general_circuit_wait_timeout_runs": sum(
                    1
                    for result in rows
                    if isinstance(
                        (
                            adaptive_wait := result.get(
                                "adaptive_general_circuit_wait"
                            )
                        ),
                        dict,
                    )
                    and adaptive_wait.get("timed_out") is True
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
                "wait_ready_wall_seconds": subtract_metric(
                    candidate.get("median_wait_ready_wall_seconds"),
                    baseline.get("median_wait_ready_wall_seconds"),
                ),
                "managed_open_adaptive_general_circuit_wait_seconds": subtract_metric(
                    candidate.get(
                        "median_managed_open_adaptive_general_circuit_wait_seconds"
                    ),
                    baseline.get(
                        "median_managed_open_adaptive_general_circuit_wait_seconds"
                    ),
                ),
                "adaptive_general_circuit_wait_seconds": subtract_metric(
                    candidate.get("median_adaptive_general_circuit_wait_seconds"),
                    baseline.get("median_adaptive_general_circuit_wait_seconds"),
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
                "p90_open_launch_gate_seconds": subtract_metric(
                    candidate.get("p90_open_launch_gate_seconds"),
                    baseline.get("p90_open_launch_gate_seconds"),
                ),
                "max_open_launch_gate_seconds": subtract_metric(
                    candidate.get("max_open_launch_gate_seconds"),
                    baseline.get("max_open_launch_gate_seconds"),
                ),
                "open_full_boot_seconds": subtract_metric(
                    candidate.get("median_open_full_boot_seconds"),
                    baseline.get("median_open_full_boot_seconds"),
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
                "total_wall_seconds": subtract_metric(
                    candidate.get("median_total_wall_seconds"),
                    baseline.get("median_total_wall_seconds"),
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
                "requested_port": result.get("requested_port"),
                "browser_startup_seed_enabled": result.get(
                    "browser_startup_seed_enabled"
                ),
                "persistent_control_wait_enabled": result.get(
                    "persistent_control_wait_enabled"
                ),
                "managed_service_metadata_wait_enabled": result.get(
                    "managed_service_metadata_wait_enabled"
                ),
                "async_browser_reset_enabled": result.get(
                    "async_browser_reset_enabled"
                ),
                "managed_open_settle_enabled": result.get(
                    "managed_open_settle_enabled"
                ),
                "managed_open_browser_overlap_enabled": result.get(
                    "managed_open_browser_overlap_enabled"
                ),
                "warm_helper_prestart_enabled": result.get(
                    "warm_helper_prestart_enabled"
                ),
                "warm_wall_seconds": (result.get("warm") or {}).get("wall_seconds"),
                "warm_ready_gate": warm_ready_gate(result),
                "warm_ready_seconds": warm_ready_seconds(result),
                "post_warm_wait_seconds": result.get("post_warm_wait_seconds"),
                "wait_ready_wall_seconds": (
                    wait_ready_wall_seconds(result)
                ),
                "managed_open_adaptive_general_circuit_wait_timeout_seconds": (
                    result.get(
                        "managed_open_adaptive_general_circuit_wait_timeout_seconds"
                    )
                ),
                "managed_open_adaptive_general_circuit_wait_seconds": (
                    managed_open_adaptive_general_circuit_wait_seconds(result)
                ),
                "managed_open_adaptive_general_circuit_wait_matched": (
                    (
                        ((result.get("open_launch") or {}).get(
                            "managed_open_adaptive_general_circuit_wait"
                        ) or {}).get("matched")
                    )
                ),
                "managed_open_adaptive_general_circuit_wait_timed_out": (
                    (
                        ((result.get("open_launch") or {}).get(
                            "managed_open_adaptive_general_circuit_wait"
                        ) or {}).get("timed_out")
                    )
                ),
                "adaptive_general_circuit_wait_timeout_seconds": result.get(
                    "adaptive_general_circuit_wait_timeout_seconds"
                ),
                "adaptive_general_circuit_wait_seconds": (
                    adaptive_general_circuit_wait_seconds(result)
                ),
                "adaptive_general_circuit_wait_matched": (
                    ((result.get("adaptive_general_circuit_wait") or {}).get("matched"))
                ),
                "adaptive_general_circuit_wait_timed_out": (
                    ((result.get("adaptive_general_circuit_wait") or {}).get("timed_out"))
                ),
                "open_wall_seconds": (result.get("open") or {}).get("wall_seconds"),
                "open_launch_gate": open_launch_gate_name(result),
                "open_launch_gate_seconds": open_launch_gate_seconds(result),
                "open_full_boot_seconds": open_full_boot_seconds(result),
                "open_browser_elapsed_seconds": open_browser_elapsed_seconds(result),
                "open_target_stream_observed": user_stream_snapshot_observed(
                    open_target_stream_snapshot(result)
                ),
                "open_target_navigation_proven": target_navigation_proven(result),
                "open_target_stream_targets": (
                    (open_target_stream_snapshot(result) or {}).get("targets")
                ),
                "browser_default_pref_check_ok": (
                    ((result.get("open_launch") or {}).get("browser_default_pref_check") or {}).get(
                        "ok"
                    )
                ),
                "browser_runtime_reset_ok": (
                    ((result.get("open_launch") or {}).get("browser_runtime_reset") or {}).get(
                        "ok"
                    )
                ),
                "combined_wall_seconds": combined_wall_seconds(result),
                "total_wall_seconds": total_wall_seconds(result),
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
