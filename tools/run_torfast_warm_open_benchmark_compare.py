#!/usr/bin/env python3
"""Benchmark real page loads after torfast warm without changing Tor quality defaults."""

from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path
import queue
import random
import re
import shutil
import sys
import threading
import time


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_ROOT = REPO_ROOT / "tools"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from launch_torfast_browser import (
    browser_launch_gate_ready_text,
    connect_existing_marionette_session,
    managed_service_ready_for_gate,
    managed_service_ready_result,
    read_bootstrap_phase_snapshot,
    resolve_managed_browser_launch_gate,
    wait_for_existing_service_ready_in_log,
)
from run_browser_compare import (
    collect_browser_activity_probe,
    collect_browser_connection_prefs,
    collect_browser_fingerprint_snapshot,
    collect_browser_quality_prefs,
    collect_browser_request_blocker,
    collect_page_resource_discovery,
    collect_performance_timing,
    configure_browser_lab_prefs,
    install_browser_activity_probe,
    install_browser_request_blocker,
    normalize_browser_block_url_substrings,
    optional_command,
    png_info,
    read_torrc_quality,
    read_runtime_prefs,
    record_proxy_run_signals,
    run_browser_benchmarks,
    summarize_browser,
    write_browser_screenshot,
)
from torfast.control import (
    read_general_circuit_snapshot,
    read_user_stream_snapshot,
    wait_for_general_circuits,
)
from run_torfast_warm_open_compare import (
    CONFLUX_CLIENT_UX_CHOICES,
    DEFAULT_BROWSER_BIN,
    DEFAULT_OUTPUT_ROOT,
    DEFAULT_PROFILES,
    DEFAULT_TOR_BIN,
    PROFILE_CHOICES,
    build_profile_specs as build_compare_profile_specs,
    build_stop_command,
    build_torfast_command,
    compact_launch,
    median_value,
    parse_json_text,
    read_json_file,
    run_command,
    subtract_metric,
    target_slug,
    torfast_command_env,
    warm_ready_gate,
    warm_ready_seconds,
)
DEFAULT_TARGETS = ["https://check.torproject.org/"]

BENCHMARK_GENERAL_CIRCUIT_TIMELINE_POLL_INTERVAL_SECONDS = 0.25
BENCHMARK_GENERAL_CIRCUIT_TIMELINE_SAMPLE_LIMIT = 400
BENCHMARK_STREAM_TIMELINE_POLL_INTERVAL_SECONDS = 0.1
BENCHMARK_STREAM_TIMELINE_SAMPLE_LIMIT = 400
BENCHMARK_PROXY_RUN_TAIL_LINES = 80


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


def benchmark_profile_name(raw_name: str) -> str:
    def replace(match: re.Match[str]) -> str:
        seconds = float(match.group(1).replace("p", "."))
        return f"_wait_{round(seconds * 1000)}ms"

    return re.sub(r"_wait_([0-9]+(?:p[0-9]+)?)s(?=_|$)", replace, raw_name)


def slugify_profile_token(raw: str, *, fallback: str = "value") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", raw.lower()).strip("-")
    return slug[:48] or fallback


def browser_block_profile_name(base_profile_name: str, url_substring: str) -> str:
    return f"{base_profile_name}_block_{slugify_profile_token(url_substring)}"


def browser_maxconn_profile_name(base_profile_name: str, count: int) -> str:
    return f"{base_profile_name}_maxconn_{count}"


def browser_serial_http_profile_name(base_profile_name: str) -> str:
    return f"{base_profile_name}_serialhttp"


def managed_general_circuit_profile_name(
    base_profile_name: str,
    count: int,
) -> str:
    return f"{base_profile_name}_gencirc_{count}"


def parse_extra_browser_block_url_substrings(values: list[str]) -> list[str]:
    return normalize_browser_block_url_substrings(values)


def parse_extra_browser_connection_cap_values(values: list[str]) -> list[int]:
    parsed: list[int] = []
    seen: set[int] = set()
    for raw in values:
        try:
            count = int(raw)
        except ValueError:
            raise SystemExit(
                "--extra-browser-max-persistent-connections-per-server "
                f"must be an integer, got: {raw}"
            ) from None
        if not (1 <= count <= 32):
            raise SystemExit(
                "--extra-browser-max-persistent-connections-per-server "
                "must be between 1 and 32"
            )
        if count in seen:
            continue
        seen.add(count)
        parsed.append(count)
    return parsed


def parse_extra_managed_general_circuit_min_count_values(
    values: list[str],
) -> list[int]:
    parsed: list[int] = []
    seen: set[int] = set()
    for raw in values:
        try:
            count = int(raw)
        except ValueError:
            raise SystemExit(
                "--extra-managed-general-circuit-min-count must be an integer, "
                f"got: {raw}"
            ) from None
        if count < 1:
            raise SystemExit(
                "--extra-managed-general-circuit-min-count must be at least 1"
            )
        if count in seen:
            continue
        seen.add(count)
        parsed.append(count)
    return parsed


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


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if (
        args.browser_max_persistent_connections_per_server is not None
        and not (1 <= args.browser_max_persistent_connections_per_server <= 32)
    ):
        raise SystemExit(
            "--browser-max-persistent-connections-per-server must be between 1 and 32"
        )
    if (
        args.browser_serial_http_connections
        and args.browser_max_persistent_connections_per_server is not None
    ):
        raise SystemExit(
            "--browser-serial-http-connections and "
            "--browser-max-persistent-connections-per-server cannot be combined"
        )
    try:
        browser_block_url_substrings = normalize_browser_block_url_substrings(
            args.browser_block_url_substrings
        )
    except ValueError as exc:
        raise SystemExit(f"--browser-block-url-substring {exc}") from None
    extra_browser_block_url_substrings = parse_extra_browser_block_url_substrings(
        args.extra_browser_block_url_substring
    )
    extra_browser_max_persistent_connections_per_server = (
        parse_extra_browser_connection_cap_values(
            args.extra_browser_max_persistent_connections_per_server
        )
    )
    if (
        args.browser_serial_http_connections
        and extra_browser_max_persistent_connections_per_server
    ):
        raise SystemExit(
            "--extra-browser-max-persistent-connections-per-server cannot be "
            "combined with --browser-serial-http-connections"
        )
    if (
        args.browser_max_persistent_connections_per_server is not None
        and args.extra_browser_serial_http_connections
    ):
        raise SystemExit(
            "--extra-browser-serial-http-connections cannot be combined with "
            "--browser-max-persistent-connections-per-server"
        )
    if args.managed_general_circuit_min_count < 1:
        raise SystemExit("--managed-general-circuit-min-count must be at least 1")
    if (
        args.managed_general_circuit_min_count != 1
        and not args.use_managed_general_circuit_gate
    ):
        raise SystemExit(
            "--managed-general-circuit-min-count requires "
            "--use-managed-general-circuit-gate"
        )
    extra_managed_general_circuit_min_count = (
        parse_extra_managed_general_circuit_min_count_values(
            args.extra_managed_general_circuit_min_count
        )
    )
    extra_post_warm_wait_seconds = parse_extra_wait_values(
        args.extra_post_warm_wait_seconds
    )
    profile_specs = build_profile_specs(
        profile_names=args.profiles,
        extra_post_warm_wait_seconds=extra_post_warm_wait_seconds,
        base_conflux_client_ux=args.conflux_client_ux,
        extra_conflux_client_ux=args.extra_conflux_client_ux,
        base_browser_startup_seed_enabled=args.browser_startup_seed,
        base_persistent_control_wait_enabled=args.persistent_control_wait,
        base_control_bootstrap_probe_enabled=True,
        base_async_browser_reset_enabled=True,
        base_managed_service_metadata_wait_enabled=True,
        base_managed_open_settle_enabled=args.managed_open_settle,
        base_managed_open_browser_overlap_enabled=(
            args.managed_open_browser_overlap
        ),
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
        extra_browser_block_url_substrings=extra_browser_block_url_substrings,
        extra_browser_max_persistent_connections_per_server=(
            extra_browser_max_persistent_connections_per_server
        ),
        extra_browser_serial_http_connections=args.extra_browser_serial_http_connections,
        extra_managed_general_circuit_min_count=(
            extra_managed_general_circuit_min_count
        ),
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
                    conflux_client_ux=(
                        str(profile_spec["conflux_client_ux"])
                        if profile_spec.get("conflux_client_ux") is not None
                        else args.conflux_client_ux
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
                    browser_net_log=args.browser_net_log,
                    browser_serial_http_connections=(
                        bool(profile_spec["browser_serial_http_connections"])
                        or args.browser_serial_http_connections
                    ),
                    browser_max_persistent_connections_per_server=(
                        profile_spec["browser_max_persistent_connections_per_server"]
                        if profile_spec["browser_max_persistent_connections_per_server"]
                        is not None
                        else args.browser_max_persistent_connections_per_server
                    ),
                    browser_block_url_substrings=normalize_browser_block_url_substrings(
                        [
                            *browser_block_url_substrings,
                            *profile_spec["extra_browser_block_url_substrings"],
                        ]
                    ),
                    use_managed_open_gate=args.use_managed_open_gate,
                    use_managed_general_circuit_gate=(
                        bool(
                            profile_spec.get(
                                "use_managed_general_circuit_gate",
                                args.use_managed_general_circuit_gate,
                            )
                        )
                    ),
                    managed_general_circuit_min_count=(
                        int(
                            profile_spec.get(
                                "managed_general_circuit_min_count",
                                args.managed_general_circuit_min_count,
                            )
                        )
                    ),
                    benchmark_general_circuit_timeline=(
                        args.benchmark_general_circuit_timeline
                    ),
                    benchmark_stream_isolation_timeline=(
                        args.benchmark_stream_isolation_timeline
                    ),
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
        "conflux_client_ux": args.conflux_client_ux,
        "browser_startup_seed_enabled": args.browser_startup_seed,
        "extra_browser_startup_seed": args.extra_browser_startup_seed,
        "extra_no_browser_startup_seed": args.extra_no_browser_startup_seed,
        "persistent_control_wait_enabled": args.persistent_control_wait,
        "control_bootstrap_probe_enabled": True,
        "async_browser_reset_enabled": True,
        "managed_service_metadata_wait_enabled": True,
        "managed_open_settle_enabled": args.managed_open_settle,
        "managed_open_browser_overlap_enabled": (
            args.managed_open_browser_overlap
        ),
        "warm_helper_prestart_enabled": args.warm_helper_prestart,
        "warm_browser_prestart_enabled": args.warm_browser_prestart,
        "browser_net_log": args.browser_net_log,
        "browser_serial_http_connections": args.browser_serial_http_connections,
        "browser_max_persistent_connections_per_server": (
            args.browser_max_persistent_connections_per_server
        ),
        "browser_block_url_substrings": list(browser_block_url_substrings),
        "extra_browser_block_url_substrings": extra_browser_block_url_substrings,
        "extra_browser_max_persistent_connections_per_server": (
            extra_browser_max_persistent_connections_per_server
        ),
        "extra_browser_serial_http_connections": (
            args.extra_browser_serial_http_connections
        ),
        "extra_conflux_client_ux": args.extra_conflux_client_ux,
        "extra_no_persistent_control_wait": args.extra_no_persistent_control_wait,
        "extra_no_control_bootstrap_probe": args.extra_no_control_bootstrap_probe,
        "extra_no_async_browser_reset": args.extra_no_async_browser_reset,
        "extra_no_managed_service_metadata_wait": (
            args.extra_no_managed_service_metadata_wait
        ),
        "extra_no_managed_open_settle": args.extra_no_managed_open_settle,
        "extra_no_managed_open_browser_overlap": (
            args.extra_no_managed_open_browser_overlap
        ),
        "extra_no_warm_helper_prestart": args.extra_no_warm_helper_prestart,
        "extra_no_warm_browser_prestart": args.extra_no_warm_browser_prestart,
        "managed_general_circuit_min_count": args.managed_general_circuit_min_count,
        "extra_managed_general_circuit_min_count": (
            extra_managed_general_circuit_min_count
        ),
        "benchmark_general_circuit_timeline": args.benchmark_general_circuit_timeline,
        "benchmark_stream_isolation_timeline": (
            args.benchmark_stream_isolation_timeline
        ),
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
            "add same-window benchmark profile variants with this official Tor "
            "`ConfluxClientUX` override"
        ),
    )
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
            "opt in to the persistent Tor control connection during warm-phase "
            "readiness waits for the base profiles"
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
            "enable the managed-open browser-overlap path for the base profiles"
        ),
    )
    managed_open_browser_overlap_group.add_argument(
        "--no-managed-open-browser-overlap",
        dest="managed_open_browser_overlap",
        action="store_false",
        help=(
            "disable the managed-open browser-overlap path for the base profiles"
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
            "when the base profiles use managed-open settle, also add "
            "same-window variants with settle disabled"
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
        "--browser-net-log",
        action="store_true",
        help=(
            "lab-only: capture Firefox/Tor Browser network MOZ_LOG files for "
            "resource-to-SOCKS mapping evidence"
        ),
    )
    parser.add_argument(
        "--browser-serial-http-connections",
        action="store_true",
        help=(
            "lab-only proof mode: limit browser HTTP connection concurrency so "
            "resource-to-SOCKS stream joins are unambiguous"
        ),
    )
    parser.add_argument(
        "--browser-max-persistent-connections-per-server",
        type=int,
        help=(
            "lab-only proof mode: override Tor Browser's "
            "network.http.max-persistent-connections-per-server value"
        ),
    )
    parser.add_argument(
        "--browser-block-url-substring",
        action="append",
        dest="browser_block_url_substrings",
        default=[],
        metavar="SUBSTRING",
        help=(
            "lab-only proof mode: cancel browser HTTP(S) requests whose URL "
            "contains this substring; repeat to block multiple requests"
        ),
    )
    parser.add_argument(
        "--extra-browser-block-url-substring",
        action="append",
        default=[],
        metavar="SUBSTRING",
        help=(
            "add a same-window lab-only profile variant that blocks browser "
            "HTTP(S) requests whose URL contains this substring"
        ),
    )
    parser.add_argument(
        "--extra-browser-max-persistent-connections-per-server",
        action="append",
        default=[],
        metavar="COUNT",
        help=(
            "add a same-window lab-only profile variant that overrides "
            "network.http.max-persistent-connections-per-server to this value"
        ),
    )
    parser.add_argument(
        "--extra-browser-serial-http-connections",
        action="store_true",
        help=(
            "add a same-window lab-only profile variant that forces serial "
            "browser HTTP connection concurrency"
        ),
    )
    parser.add_argument(
        "--use-managed-open-gate",
        action="store_true",
        help=(
            "wait for the same browser launch gate that `torfast open` would use "
            "on the warmed managed service before running the page benchmark"
        ),
    )
    parser.add_argument(
        "--use-managed-general-circuit-gate",
        action="store_true",
        help=(
            "proof mode: wait until the warmed managed service exposes at least "
            "one built 3-hop general circuit before running the page benchmark"
        ),
    )
    parser.add_argument(
        "--managed-general-circuit-min-count",
        type=int,
        default=1,
        help=(
            "proof mode: when --use-managed-general-circuit-gate is enabled, "
            "require at least this many built 3-hop general circuits before "
            "running the page benchmark"
        ),
    )
    parser.add_argument(
        "--extra-managed-general-circuit-min-count",
        action="append",
        default=[],
        metavar="COUNT",
        help=(
            "add a same-window profile variant that waits for at least this "
            "many built 3-hop general circuits before the page benchmark"
        ),
    )
    parser.add_argument(
        "--benchmark-general-circuit-timeline",
        action="store_true",
        help=(
            "proof mode: poll the warmed managed service control port during the "
            "page benchmark and save built general-circuit purpose counts over time"
        ),
    )
    parser.add_argument(
        "--benchmark-stream-isolation-timeline",
        action="store_true",
        help=(
            "proof mode: poll the warmed managed service control port during the "
            "page benchmark and save active user SOCKS stream concentration over time"
        ),
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
    base_conflux_client_ux: str | None = None,
    extra_conflux_client_ux: list[str] | None = None,
    base_browser_startup_seed_enabled: bool = False,
    base_persistent_control_wait_enabled: bool = False,
    base_control_bootstrap_probe_enabled: bool = True,
    base_async_browser_reset_enabled: bool = True,
    base_managed_service_metadata_wait_enabled: bool = True,
    base_managed_open_settle_enabled: bool = False,
    base_managed_open_browser_overlap_enabled: bool = True,
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
    extra_browser_block_url_substrings: list[str],
    extra_browser_max_persistent_connections_per_server: list[int],
    extra_browser_serial_http_connections: bool,
    extra_managed_general_circuit_min_count: list[int],
) -> list[dict[str, object]]:
    specs: list[dict[str, object]] = []
    seen: set[str] = set()

    def add_spec(
        base_spec: dict[str, object],
        *,
        name: str,
        browser_serial_http_connections: bool | None = None,
        browser_max_persistent_connections_per_server: int | None = None,
        extra_browser_block_url_substrings: list[str] | None = None,
        use_managed_general_circuit_gate: bool | None = None,
        managed_general_circuit_min_count: int | None = None,
    ) -> None:
        normalized_name = benchmark_profile_name(name)
        if normalized_name in seen:
            return
        spec = dict(base_spec)
        spec["name"] = normalized_name
        spec["browser_serial_http_connections"] = (
            bool(browser_serial_http_connections)
            if browser_serial_http_connections is not None
            else bool(spec.get("browser_serial_http_connections"))
        )
        spec["browser_max_persistent_connections_per_server"] = (
            browser_max_persistent_connections_per_server
            if browser_max_persistent_connections_per_server is not None
            else spec.get("browser_max_persistent_connections_per_server")
        )
        spec["extra_browser_block_url_substrings"] = list(
            extra_browser_block_url_substrings
            if extra_browser_block_url_substrings is not None
            else spec.get("extra_browser_block_url_substrings", [])
        )
        if spec.get("conflux_client_ux") is None:
            spec.pop("conflux_client_ux", None)
        if use_managed_general_circuit_gate or managed_general_circuit_min_count not in (
            None,
            1,
        ):
            spec["use_managed_general_circuit_gate"] = bool(
                use_managed_general_circuit_gate
            )
            spec["managed_general_circuit_min_count"] = (
                1
                if managed_general_circuit_min_count is None
                else managed_general_circuit_min_count
            )
        else:
            spec.pop("use_managed_general_circuit_gate", None)
            spec.pop("managed_general_circuit_min_count", None)
        specs.append(spec)
        seen.add(normalized_name)

    compare_specs = build_compare_profile_specs(
        profile_names=profile_names,
        extra_post_warm_wait_seconds=extra_post_warm_wait_seconds,
        base_conflux_client_ux=base_conflux_client_ux,
        extra_conflux_client_ux=extra_conflux_client_ux,
        base_browser_startup_seed_enabled=base_browser_startup_seed_enabled,
        base_persistent_control_wait_enabled=base_persistent_control_wait_enabled,
        base_control_bootstrap_probe_enabled=base_control_bootstrap_probe_enabled,
        base_async_browser_reset_enabled=base_async_browser_reset_enabled,
        base_managed_service_metadata_wait_enabled=(
            base_managed_service_metadata_wait_enabled
        ),
        base_managed_open_settle_enabled=base_managed_open_settle_enabled,
        base_managed_open_browser_overlap_enabled=(
            base_managed_open_browser_overlap_enabled
        ),
        base_warm_helper_prestart_enabled=base_warm_helper_prestart_enabled,
        base_warm_browser_prestart_enabled=base_warm_browser_prestart_enabled,
        extra_browser_startup_seed=extra_browser_startup_seed,
        extra_no_persistent_control_wait=extra_no_persistent_control_wait,
        extra_no_control_bootstrap_probe=extra_no_control_bootstrap_probe,
        extra_no_async_browser_reset=extra_no_async_browser_reset,
        extra_no_managed_service_metadata_wait=(
            extra_no_managed_service_metadata_wait
        ),
        extra_no_browser_startup_seed=extra_no_browser_startup_seed,
        extra_no_managed_open_settle=extra_no_managed_open_settle,
        extra_no_managed_open_browser_overlap=(
            extra_no_managed_open_browser_overlap
        ),
        extra_no_warm_helper_prestart=extra_no_warm_helper_prestart,
        extra_no_warm_browser_prestart=extra_no_warm_browser_prestart,
    )
    for compare_spec in compare_specs:
        add_spec(dict(compare_spec), name=str(compare_spec["name"]))

    existing_specs = list(specs)
    for spec in existing_specs:
        profile_name = str(spec["name"])
        for substring in extra_browser_block_url_substrings:
            add_spec(
                spec,
                name=browser_block_profile_name(profile_name, substring),
                browser_serial_http_connections=bool(
                    spec.get("browser_serial_http_connections")
                ),
                browser_max_persistent_connections_per_server=(
                    spec.get("browser_max_persistent_connections_per_server")
                    if isinstance(
                        spec.get("browser_max_persistent_connections_per_server"),
                        int,
                    )
                    else None
                ),
                extra_browser_block_url_substrings=[substring],
            )
        for count in extra_browser_max_persistent_connections_per_server:
            add_spec(
                spec,
                name=browser_maxconn_profile_name(profile_name, count),
                browser_serial_http_connections=bool(
                    spec.get("browser_serial_http_connections")
                ),
                browser_max_persistent_connections_per_server=count,
                extra_browser_block_url_substrings=list(
                    spec.get("extra_browser_block_url_substrings", [])
                ),
            )
        if extra_browser_serial_http_connections:
            add_spec(
                spec,
                name=browser_serial_http_profile_name(profile_name),
                browser_serial_http_connections=True,
                browser_max_persistent_connections_per_server=(
                    spec.get("browser_max_persistent_connections_per_server")
                    if isinstance(
                        spec.get("browser_max_persistent_connections_per_server"),
                        int,
                    )
                    else None
                ),
                extra_browser_block_url_substrings=list(
                    spec.get("extra_browser_block_url_substrings", [])
                ),
            )
    if extra_managed_general_circuit_min_count:
        existing_specs = list(specs)
        for spec in existing_specs:
            for count in extra_managed_general_circuit_min_count:
                add_spec(
                    spec,
                    name=managed_general_circuit_profile_name(str(spec["name"]), count),
                    browser_serial_http_connections=bool(
                        spec["browser_serial_http_connections"]
                    ),
                    browser_max_persistent_connections_per_server=(
                        spec["browser_max_persistent_connections_per_server"]
                        if isinstance(
                            spec["browser_max_persistent_connections_per_server"],
                            int,
                        )
                        else None
                    ),
                    extra_browser_block_url_substrings=list(
                        spec["extra_browser_block_url_substrings"]
                    ),
                    use_managed_general_circuit_gate=True,
                    managed_general_circuit_min_count=count,
                )
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
    conflux_client_ux: str | None = None,
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
    persistent_control_wait_enabled: bool = False,
    control_bootstrap_probe_enabled: bool = True,
    async_browser_reset_enabled: bool = True,
    managed_service_metadata_wait_enabled: bool = True,
    managed_open_settle_enabled: bool = False,
    managed_open_browser_overlap_enabled: bool = True,
    warm_helper_prestart_enabled: bool = False,
    warm_browser_prestart_enabled: bool = False,
    browser_net_log: bool,
    browser_serial_http_connections: bool,
    browser_max_persistent_connections_per_server: int | None,
    browser_block_url_substrings: list[str],
    use_managed_open_gate: bool,
    use_managed_general_circuit_gate: bool,
    managed_general_circuit_min_count: int,
    benchmark_general_circuit_timeline: bool,
    benchmark_stream_isolation_timeline: bool,
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
        "base_profile_name": base_profile_name,
        "cycle": cycle,
        "port": port,
        "run_dir": str(run_dir),
        "state_root": str(state_root),
        "conflux_client_ux": conflux_client_ux,
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
        "use_managed_open_gate": use_managed_open_gate,
        "use_managed_general_circuit_gate": use_managed_general_circuit_gate,
        "managed_general_circuit_min_count": managed_general_circuit_min_count,
        "benchmark_general_circuit_timeline_enabled": (
            benchmark_general_circuit_timeline
        ),
        "benchmark_stream_isolation_timeline_enabled": (
            benchmark_stream_isolation_timeline
        ),
        "browser_net_log": browser_net_log,
        "browser_serial_http_connections": browser_serial_http_connections,
        "browser_max_persistent_connections_per_server": (
            browser_max_persistent_connections_per_server
        ),
        "browser_block_url_substrings": list(browser_block_url_substrings),
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
        browser_timeout=timeout,
        browser_startup_seed_root=browser_startup_seed_root,
        browser_startup_seed_enabled=browser_startup_seed_enabled,
        managed_open_settle_enabled=managed_open_settle_enabled,
        managed_open_browser_overlap_enabled=(
            managed_open_browser_overlap_enabled
        ),
        warm_browser_prestart_enabled=warm_browser_prestart_enabled,
        headed=True,
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
    result["post_warm_wait_seconds"] = extra_post_warm_wait_seconds

    benchmarks: dict[str, object] = {}
    benchmark_wall_seconds = None
    boot_after_benchmark: dict[str, object] | None = None
    benchmark_service_state_before_browser: dict[str, object] | None = None
    benchmark_service_state_after_browser: dict[str, object] | None = None
    benchmark_proxy_signal_capture: dict[str, object] | None = None
    open_gate_wait: dict[str, object] | None = None
    general_circuit_wait: dict[str, object] | None = None
    benchmark_general_circuit_timeline_payload: dict[str, object] | None = None
    benchmark_stream_isolation_timeline_payload: dict[str, object] | None = None
    if warm_run.get("ok"):
        if extra_post_warm_wait_seconds > 0:
            time.sleep(extra_post_warm_wait_seconds)
        if use_managed_open_gate:
            open_gate_wait = wait_for_managed_open_gate(
                result,
                requested_gate=base_profile_name,
                target=target,
            )
        gates_ready = not use_managed_open_gate or (
            isinstance(open_gate_wait, dict) and open_gate_wait.get("ok") is True
        )
        if gates_ready and use_managed_general_circuit_gate:
            general_circuit_wait = wait_for_managed_general_circuit(
                result,
                min_count=managed_general_circuit_min_count,
            )
            gates_ready = (
                isinstance(general_circuit_wait, dict)
                and general_circuit_wait.get("ok") is True
            )
        if gates_ready:
            service = warm_service(result)
            prestarted_browser = warm_prestarted_browser(result)
            benchmark_service_state_before_browser = (
                capture_managed_service_state_snapshot(service)
            )
            benchmark_started = time.monotonic()
            timeline_collector = None
            stream_timeline_collector = None
            if benchmark_general_circuit_timeline:
                timeline_collector = start_benchmark_general_circuit_timeline_collector(
                    service,
                    benchmark_started_monotonic=benchmark_started,
                )
                benchmark_general_circuit_timeline_payload = timeline_collector.get(
                    "payload"
                )
            if benchmark_stream_isolation_timeline:
                stream_timeline_collector = (
                    start_benchmark_stream_isolation_timeline_collector(
                        service,
                        benchmark_started_monotonic=benchmark_started,
                        target=target,
                    )
                )
                benchmark_stream_isolation_timeline_payload = (
                    stream_timeline_collector.get("payload")
                )
            try:
                if (
                    warm_browser_prestart_enabled
                    and isinstance(prestarted_browser, dict)
                    and prestarted_browser.get("applied") is True
                ):
                    benchmarks = run_prestarted_browser_benchmarks(
                        state_root=state_root,
                        prestarted_browser=prestarted_browser,
                        port=port,
                        output_dir=run_dir,
                        targets=[target],
                        runs=1,
                        timeout=timeout,
                        browser_net_log=browser_net_log,
                        browser_serial_http_connections=(
                            browser_serial_http_connections
                        ),
                        browser_max_persistent_connections_per_server=(
                            browser_max_persistent_connections_per_server
                        ),
                        browser_block_url_substrings=browser_block_url_substrings,
                        browser_startup_seed_apply=(
                            warm_launch.get("browser_startup_seed_apply")
                            if isinstance(warm_launch, dict)
                            else None
                        ),
                    )
                else:
                    benchmarks = run_browser_benchmarks(
                        browser_bin=browser_bin,
                        port=port,
                        output_dir=run_dir,
                        targets=[target],
                        runs=1,
                        timeout=timeout,
                        window_size=window_size,
                        compact_output=compact_output,
                        browser_net_log=browser_net_log,
                        browser_serial_http_connections=browser_serial_http_connections,
                        browser_max_persistent_connections_per_server=(
                            browser_max_persistent_connections_per_server
                        ),
                        browser_block_url_substrings=browser_block_url_substrings,
                        browser_startup_seed_root=browser_startup_seed_root,
                        no_browser_startup_seed=not browser_startup_seed_enabled,
                    )
            finally:
                if timeline_collector is not None:
                    stop_benchmark_general_circuit_timeline_collector(
                        timeline_collector
                    )
                if stream_timeline_collector is not None:
                    stop_benchmark_stream_isolation_timeline_collector(
                        stream_timeline_collector
                    )
            benchmark_wall_seconds = round(time.monotonic() - benchmark_started, 3)
            benchmark_service_state_after_browser = (
                capture_managed_service_state_snapshot(service)
            )
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
    result["benchmark_service_state_before_browser"] = (
        benchmark_service_state_before_browser
    )
    result["benchmark_service_state_after_browser"] = (
        benchmark_service_state_after_browser
    )
    result["benchmark_general_circuit_timeline"] = (
        benchmark_general_circuit_timeline_payload
    )
    result["benchmark_stream_isolation_timeline"] = (
        benchmark_stream_isolation_timeline_payload
    )
    result["open_gate_wait"] = open_gate_wait
    result["general_circuit_wait"] = general_circuit_wait
    result["boot_after_benchmark"] = boot_after_benchmark
    result["torrc"] = read_torrc_quality(state_root / "torrc")
    service = warm_service(result)
    if isinstance(service, dict):
        tor_log = service.get("tor_log")
        if isinstance(tor_log, str):
            benchmark_proxy_signal_capture = preserve_benchmark_proxy_run_signals(
                benchmarks,
                proxy_log_path=Path(tor_log),
            )

    stop_run = run_command(build_stop_command(state_root))
    stop_payload = parse_json_text("\n".join(stop_run.get("stdout_tail", [])))
    result["stop"] = {
        **stop_run,
        "response": stop_payload,
    }
    result["benchmark_proxy_signal_capture"] = benchmark_proxy_signal_capture

    copy_path = (
        output_dir
        / f"{target_slug(target)}-{profile_name}-cycle{cycle}.json"
    )
    browser_net_log_archive = preserve_benchmark_browser_net_logs(
        benchmarks,
        archive_root=output_dir / "browser_net_logs",
        target=target,
        profile_name=profile_name,
        cycle=cycle,
    )
    result["browser_net_log_archive"] = browser_net_log_archive
    copy_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")

    if not keep_run_dir:
        shutil.rmtree(run_dir, ignore_errors=True)

    return result


def preserve_benchmark_browser_net_logs(
    benchmarks: dict[str, object],
    *,
    archive_root: Path,
    target: str,
    profile_name: str,
    cycle: int,
) -> dict[str, object]:
    archive = {
        "enabled": True,
        "copied_files": [],
        "missing_files": [],
        "errors": [],
    }
    if not isinstance(benchmarks, dict):
        return archive
    archive_root.mkdir(parents=True, exist_ok=True)
    run_slug = f"{target_slug(target)}-{profile_name}-cycle{cycle}"
    for benchmark_target, benchmark_payload in benchmarks.items():
        if not isinstance(benchmark_payload, dict):
            continue
        runs = benchmark_payload.get("runs")
        if not isinstance(runs, list):
            continue
        for run_index, run in enumerate(runs, start=1):
            if not isinstance(run, dict):
                continue
            browser_net_log = run.get("browser_net_log")
            if not isinstance(browser_net_log, dict):
                continue
            files = browser_net_log.get("files")
            if not isinstance(files, list):
                continue
            preserved_files: list[str] = []
            for raw_path in files:
                if not isinstance(raw_path, str):
                    continue
                source_path = Path(raw_path)
                if not source_path.exists() or not source_path.is_file():
                    archive["missing_files"].append(raw_path)
                    continue
                destination_path = (
                    archive_root
                    / f"{run_slug}-run{run_index}-{source_path.name}"
                )
                try:
                    shutil.copy2(source_path, destination_path)
                except OSError as exc:
                    archive["errors"].append(
                        f"{source_path} -> {destination_path}: {exc}"
                    )
                    continue
                preserved_files.append(str(destination_path))
                archive["copied_files"].append(
                    {
                        "target": benchmark_target,
                        "run_index": run_index,
                        "source": raw_path,
                        "destination": str(destination_path),
                    }
                )
            if preserved_files:
                browser_net_log["files"] = preserved_files
    return archive


def benchmark_run_entries(
    benchmarks: dict[str, object],
) -> list[tuple[dict[str, object], dict[str, object]]]:
    entries: list[tuple[dict[str, object], dict[str, object]]] = []
    if not isinstance(benchmarks, dict):
        return entries
    for benchmark_payload in benchmarks.values():
        if not isinstance(benchmark_payload, dict):
            continue
        runs = benchmark_payload.get("runs")
        if not isinstance(runs, list):
            continue
        for run in runs:
            if isinstance(run, dict):
                entries.append((benchmark_payload, run))
    return entries


def preserve_benchmark_proxy_run_signals(
    benchmarks: dict[str, object],
    *,
    proxy_log_path: Path,
    keep_success_tail_limit: int = BENCHMARK_PROXY_RUN_TAIL_LINES,
) -> dict[str, object]:
    entries = benchmark_run_entries(benchmarks)
    capture: dict[str, object] = {
        "enabled": bool(entries),
        "proxy_log_path": str(proxy_log_path),
        "run_count": len(entries),
        "captured_run_count": 0,
        "line_count": 0,
    }
    if not entries:
        capture["reason"] = "no benchmark runs"
        return capture
    if not proxy_log_path.exists():
        capture["ok"] = False
        capture["error"] = f"not found: {proxy_log_path}"
        return capture
    try:
        log_lines = proxy_log_path.read_text(
            encoding="utf-8",
            errors="replace",
        ).splitlines()
    except OSError as exc:
        capture["ok"] = False
        capture["error"] = f"{type(exc).__name__}: {exc}"
        return capture

    capture["line_count"] = len(log_lines)
    for benchmark_payload, run in entries:
        lines: queue.Queue[str] = queue.Queue()
        for line in log_lines:
            lines.put(line)
        record_proxy_run_signals(
            benchmark_payload,
            run,
            lines,
            keep_success_tail_limit=keep_success_tail_limit,
        )
        if any(
            run.get(key)
            for key in (
                "proxy_signal_lines",
                "proxy_relay_context_lines",
                "proxy_output_tail",
            )
        ):
            capture["captured_run_count"] = (
                int(capture.get("captured_run_count", 0)) + 1
            )
    capture["ok"] = True
    return capture


def warm_service(result: dict[str, object]) -> dict[str, object] | None:
    warm_launch = result.get("warm_launch")
    if not isinstance(warm_launch, dict):
        return None
    service = warm_launch.get("reused_tor_service")
    return service if isinstance(service, dict) else None


def warm_prestarted_browser(result: dict[str, object]) -> dict[str, object] | None:
    warm_launch = result.get("warm_launch")
    if not isinstance(warm_launch, dict):
        return None
    prestarted_browser = warm_launch.get("warm_browser_prestart")
    return prestarted_browser if isinstance(prestarted_browser, dict) else None


def run_prestarted_browser_benchmarks(
    *,
    state_root: Path,
    prestarted_browser: dict[str, object],
    port: int,
    output_dir: Path,
    targets: list[str],
    runs: int,
    timeout: float,
    browser_net_log: bool,
    browser_serial_http_connections: bool,
    browser_max_persistent_connections_per_server: int | None,
    browser_block_url_substrings: list[str],
    browser_startup_seed_apply: dict[str, object] | None = None,
) -> dict[str, object]:
    benchmarks: dict[str, object] = {}
    for url in targets:
        url_slug = target_slug(url)
        results = [
            run_prestarted_browser_once(
                state_root=state_root,
                prestarted_browser=prestarted_browser,
                port=port,
                output_dir=output_dir,
                url=url,
                url_slug=url_slug,
                run_index=run_index,
                timeout=timeout,
                browser_net_log=browser_net_log,
                browser_serial_http_connections=browser_serial_http_connections,
                browser_max_persistent_connections_per_server=(
                    browser_max_persistent_connections_per_server
                ),
                browser_block_url_substrings=browser_block_url_substrings,
                browser_startup_seed_apply=browser_startup_seed_apply,
            )
            for run_index in range(1, runs + 1)
        ]
        benchmarks[url] = {
            "runs": results,
            "summary": summarize_browser(results),
        }
    return benchmarks


def run_prestarted_browser_once(
    *,
    state_root: Path,
    prestarted_browser: dict[str, object],
    port: int,
    output_dir: Path,
    url: str,
    url_slug: str,
    run_index: int,
    timeout: float,
    browser_net_log: bool,
    browser_serial_http_connections: bool,
    browser_max_persistent_connections_per_server: int | None,
    browser_block_url_substrings: list[str],
    browser_startup_seed_apply: dict[str, object] | None = None,
) -> dict[str, object]:
    profile_dir = state_root / "browser-profile"
    home_dir = state_root / "browser-home"
    screenshot_path = output_dir / "screenshots" / f"{url_slug}-{run_index}.png"
    screenshot_path.parent.mkdir(parents=True, exist_ok=True)

    started = time.perf_counter()
    started_epoch_ms = time.time() * 1000
    timed_out = False
    error = None
    exit_code = None
    output_lines: list[str] = []
    capabilities: dict[str, object] = {}
    current_url = None
    title = None
    load_ms = None
    nav_started_epoch_ms = None
    nav_finished_epoch_ms = None
    browser_connection_prefs: dict[str, object] = {}
    browser_lab_prefs: dict[str, object] = {
        "serial_http_connections": {"enabled": browser_serial_http_connections},
        "max_persistent_connections_per_server": {
            "enabled": browser_max_persistent_connections_per_server is not None,
            "requested_value": browser_max_persistent_connections_per_server,
        },
    }
    browser_activity_probe: dict[str, object] = {
        "enabled": browser_net_log,
        "note": "prestarted browser reuse path",
    }
    browser_request_blocker: dict[str, object] = {
        "enabled": bool(browser_block_url_substrings),
        "url_substrings": list(browser_block_url_substrings or []),
    }
    browser_quality_prefs: dict[str, object] = {}
    browser_fingerprint_snapshot: dict[str, object] = {}
    performance_timing: dict[str, object] = {}

    pid = prestarted_browser.get("pid")
    marionette_port = prestarted_browser.get("marionette_port")
    client = None
    try:
        if not isinstance(pid, int) or not isinstance(marionette_port, int):
            raise RuntimeError(
                "prestarted browser metadata missing pid or marionette_port"
            )
        client = connect_existing_marionette_session(
            pid=pid,
            marionette_port=marionette_port,
            timeout=min(30.0, timeout),
        )
        try:
            client.sock.settimeout(timeout + 10.0)
        except Exception:
            pass
        client.command(
            "WebDriver:SetTimeouts",
            {
                "implicit": 0,
                "pageLoad": int(timeout * 1000),
                "script": 30_000,
            },
        )
        browser_lab_prefs = configure_browser_lab_prefs(
            client,
            serial_http_connections=browser_serial_http_connections,
            max_persistent_connections_per_server=(
                browser_max_persistent_connections_per_server
            ),
        )
        browser_request_blocker = install_browser_request_blocker(
            client, url_substrings=browser_block_url_substrings
        )
        browser_activity_probe = install_browser_activity_probe(
            client, enabled=browser_net_log
        )
        nav_started_epoch_ms = time.time() * 1000
        nav_started = time.perf_counter()
        client.command("WebDriver:Navigate", {"url": url})
        load_ms = (time.perf_counter() - nav_started) * 1000
        nav_finished_epoch_ms = time.time() * 1000

        screenshot = client.command("WebDriver:TakeScreenshot", {})
        raw_png = base64.b64decode(screenshot["value"])
        write_browser_screenshot(screenshot_path, raw_png)

        current_url = optional_command(client, "WebDriver:GetCurrentURL")
        title = optional_command(client, "WebDriver:GetTitle")
        performance_timing = collect_performance_timing(client)
        if isinstance(performance_timing, dict):
            performance_timing["page_resource_discovery"] = (
                collect_page_resource_discovery(client)
            )
        browser_connection_prefs = collect_browser_connection_prefs(client)
        browser_quality_prefs = collect_browser_quality_prefs(client)
        browser_fingerprint_snapshot = collect_browser_fingerprint_snapshot(client)
    except TimeoutError as exc:
        timed_out = True
        error = str(exc)
    except Exception as exc:  # noqa: BLE001
        error = f"{type(exc).__name__}: {exc}"
    finally:
        if client:
            browser_request_blocker = collect_browser_request_blocker(
                client, browser_request_blocker
            )
            browser_activity_probe = collect_browser_activity_probe(
                client, browser_activity_probe
            )
            client.close()

    elapsed_ms = (time.perf_counter() - started) * 1000
    finished_epoch_ms = time.time() * 1000
    image = png_info(screenshot_path)
    runtime_prefs = read_runtime_prefs(profile_dir)
    effective_proxy = {
        "network.proxy.socks": runtime_prefs.get("network.proxy.socks", "127.0.0.1"),
        "network.proxy.socks_port": runtime_prefs.get("network.proxy.socks_port", 9150),
        "network.proxy.socks_remote_dns": runtime_prefs.get(
            "network.proxy.socks_remote_dns", True
        ),
        "network.proxy.type": runtime_prefs.get("network.proxy.type", 1),
    }
    ok = (
        not timed_out
        and error is None
        and image["exists"]
        and image["bytes"] > 0
        and effective_proxy["network.proxy.socks"] == "127.0.0.1"
        and effective_proxy["network.proxy.socks_port"] == port
        and effective_proxy["network.proxy.socks_remote_dns"] is True
        and effective_proxy["network.proxy.type"] == 1
    )
    artifacts = {
        "compact_output": False,
        "profile_dir_retained": profile_dir.exists(),
        "home_dir_retained": home_dir.exists(),
        "removed": [],
        "errors": [],
        "retain_reason": "prestarted_browser_reuse",
    }

    if not isinstance(browser_startup_seed_apply, dict):
        browser_startup_seed_apply = {
            "ok": True,
            "applied": None,
            "reason": "reused prestarted browser",
        }

    return {
        "url": url,
        "run_index": run_index,
        "ok": ok,
        "expected_socks_port": port,
        "started_epoch_ms": round(started_epoch_ms, 3),
        "finished_epoch_ms": round(finished_epoch_ms, 3),
        "nav_started_epoch_ms": (
            round(nav_started_epoch_ms, 3)
            if nav_started_epoch_ms is not None
            else None
        ),
        "nav_finished_epoch_ms": (
            round(nav_finished_epoch_ms, 3)
            if nav_finished_epoch_ms is not None
            else None
        ),
        "elapsed_ms": round(elapsed_ms, 3),
        "load_ms": round(load_ms, 3) if load_ms is not None else None,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "error": error,
        "current_url": current_url,
        "title": title,
        "capabilities": capabilities,
        "performance_timing": performance_timing,
        "browser_connection_prefs": browser_connection_prefs,
        "browser_lab_prefs": browser_lab_prefs,
        "browser_request_blocker": browser_request_blocker,
        "browser_activity_probe": browser_activity_probe,
        "browser_quality_prefs": browser_quality_prefs,
        "browser_fingerprint_snapshot": browser_fingerprint_snapshot,
        "screenshot": image,
        "profile_dir": str(profile_dir),
        "home_dir": str(home_dir),
        "artifacts": artifacts,
        "runtime_prefs": runtime_prefs,
        "effective_proxy_prefs": effective_proxy,
        "browser_net_log": {
            "enabled": browser_net_log,
            "ok": not browser_net_log,
            "reason": (
                "unsupported when reusing a prestarted browser"
                if browser_net_log
                else "not requested"
            ),
            "files": [],
        },
        "browser_startup_seed_apply": browser_startup_seed_apply,
        "output_tail": output_lines[-40:],
    }


def capture_managed_service_state_snapshot(
    service: dict[str, object] | None,
) -> dict[str, object] | None:
    if not isinstance(service, dict):
        return None
    now_epoch_ms = round(time.time() * 1000, 3)
    started_epoch_ms = service.get("started_epoch_ms")
    ready_epoch_ms = service.get("ready_epoch_ms")
    service_uptime_seconds = None
    if isinstance(started_epoch_ms, (int, float)):
        service_uptime_seconds = round(
            (now_epoch_ms - float(started_epoch_ms)) / 1000.0,
            3,
        )
    service_ready_age_seconds = None
    if isinstance(ready_epoch_ms, (int, float)):
        service_ready_age_seconds = round(
            (now_epoch_ms - float(ready_epoch_ms)) / 1000.0,
            3,
        )
    control_port = service.get("control_port")
    control_cookie_path = service.get("control_cookie_path")
    general_circuit_snapshot: dict[str, object]
    if isinstance(control_port, int) and isinstance(control_cookie_path, str):
        general_circuit_snapshot = read_general_circuit_snapshot(
            host="127.0.0.1",
            port=control_port,
            cookie_path=Path(control_cookie_path),
        )
    else:
        general_circuit_snapshot = {
            "ok": False,
            "error": "control-port general-circuit probe unavailable",
        }
    return {
        "service_metadata_ready_gate": service.get("ready_gate"),
        "service_uptime_seconds": service_uptime_seconds,
        "service_ready_age_seconds": service_ready_age_seconds,
        "control_bootstrap_phase": read_bootstrap_phase_snapshot(
            control_port=control_port,
            control_cookie_path=control_cookie_path,
        ),
        "general_circuit_snapshot": general_circuit_snapshot,
    }


def wait_for_managed_open_gate(
    result: dict[str, object],
    *,
    requested_gate: str,
    target: str,
) -> dict[str, object] | None:
    service = warm_service(result)
    if not isinstance(service, dict):
        return None
    gate = resolve_managed_browser_launch_gate(
        requested_gate=requested_gate,
        url=target,
        start_managed_tor_only=False,
        reused_tor_service=service,
    )
    if managed_service_ready_for_gate(service, gate):
        return {
            "gate": gate,
            **managed_service_ready_result(service, gate=gate),
        }
    pid = service.get("pid")
    tor_log = service.get("tor_log")
    if not isinstance(pid, int) or not isinstance(tor_log, str):
        return {
            "gate": gate,
            "ok": False,
            "error": "managed warm service metadata missing pid or tor_log",
        }
    return {
        "gate": gate,
        **wait_for_existing_service_ready_in_log(
            pid=pid,
            log_path=Path(tor_log),
            timeout=60.0,
            ready_text=browser_launch_gate_ready_text(gate),
            process_name="tor",
        ),
    }


def wait_for_managed_general_circuit(
    result: dict[str, object],
    *,
    min_count: int = 1,
) -> dict[str, object] | None:
    if min_count < 1:
        raise ValueError("min_count must be at least 1")
    service = warm_service(result)
    if not isinstance(service, dict):
        return None
    control_port = service.get("control_port")
    control_cookie_path = service.get("control_cookie_path")
    if not isinstance(control_port, int) or not isinstance(control_cookie_path, str):
        return {
            "gate": "general_circuit",
            "ok": False,
            "error": "managed warm service metadata missing control-port support",
        }
    snapshot = read_general_circuit_snapshot(
        host="127.0.0.1",
        port=control_port,
        cookie_path=Path(control_cookie_path),
    )
    if (
        snapshot.get("ok") is True
        and isinstance(snapshot.get("matched_circuit_count"), int)
        and snapshot["matched_circuit_count"] >= min_count
    ):
        return {
            "gate": "general_circuit",
            "ok": True,
            "seconds": 0.0,
            "min_count": min_count,
            "reused_service": True,
            **snapshot,
        }
    return {
        "gate": "general_circuit",
        **wait_for_general_circuits(
            host="127.0.0.1",
            port=control_port,
            cookie_path=Path(control_cookie_path),
            timeout=60.0,
            poll_interval=0.05,
            min_count=min_count,
        ),
    }


def start_benchmark_general_circuit_timeline_collector(
    service: dict[str, object] | None,
    *,
    benchmark_started_monotonic: float,
    poll_interval_seconds: float = (
        BENCHMARK_GENERAL_CIRCUIT_TIMELINE_POLL_INTERVAL_SECONDS
    ),
    sample_limit: int = BENCHMARK_GENERAL_CIRCUIT_TIMELINE_SAMPLE_LIMIT,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "enabled": True,
        "ok": True,
        "poll_interval_seconds": poll_interval_seconds,
        "sample_limit": sample_limit,
        "samples": [],
        "sample_count": 0,
        "truncated": False,
    }
    if not isinstance(service, dict):
        payload["ok"] = False
        payload["error"] = "managed warm service metadata missing"
        return {"payload": payload}
    control_port = service.get("control_port")
    control_cookie_path = service.get("control_cookie_path")
    if not isinstance(control_port, int) or not isinstance(control_cookie_path, str):
        payload["ok"] = False
        payload["error"] = "managed warm service metadata missing control-port support"
        return {"payload": payload}

    stop_event = threading.Event()
    samples = payload["samples"]

    def worker() -> None:
        try:
            while not stop_event.is_set():
                if not isinstance(samples, list):
                    break
                if len(samples) >= sample_limit:
                    payload["truncated"] = True
                    break
                snapshot = read_general_circuit_snapshot(
                    host="127.0.0.1",
                    port=control_port,
                    cookie_path=Path(control_cookie_path),
                )
                samples.append(
                    compact_general_circuit_timeline_sample(
                        snapshot,
                        benchmark_started_monotonic=benchmark_started_monotonic,
                    )
                )
                if stop_event.wait(poll_interval_seconds):
                    break
        except Exception as exc:
            payload["ok"] = False
            payload["error"] = f"{type(exc).__name__}: {exc}"

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    return {
        "payload": payload,
        "stop_event": stop_event,
        "thread": thread,
    }


def stop_benchmark_general_circuit_timeline_collector(
    collector: dict[str, object],
) -> None:
    payload = collector.get("payload")
    stop_event = collector.get("stop_event")
    thread = collector.get("thread")
    if isinstance(stop_event, threading.Event):
        stop_event.set()
    if isinstance(thread, threading.Thread):
        thread.join(timeout=2.0)
        if isinstance(payload, dict):
            payload["thread_joined"] = not thread.is_alive()
    if isinstance(payload, dict):
        samples = payload.get("samples")
        payload["sample_count"] = len(samples) if isinstance(samples, list) else 0


def compact_general_circuit_timeline_sample(
    snapshot: dict[str, object],
    *,
    benchmark_started_monotonic: float,
) -> dict[str, object]:
    sample: dict[str, object] = {
        "elapsed_seconds": round(time.monotonic() - benchmark_started_monotonic, 3),
        "ok": snapshot.get("ok") is True,
    }
    for key in (
        "matched_circuit_count",
        "matched_circuit_count_by_purpose",
        "first_purpose",
        "has_built_general_circuit",
        "total_circuit_count",
        "seconds",
    ):
        if key in snapshot:
            sample[key] = snapshot.get(key)
    if snapshot.get("ok") is not True and isinstance(snapshot.get("error"), str):
        sample["error"] = snapshot.get("error")
    return sample


def start_benchmark_stream_isolation_timeline_collector(
    service: dict[str, object] | None,
    *,
    benchmark_started_monotonic: float,
    target: str,
    poll_interval_seconds: float = BENCHMARK_STREAM_TIMELINE_POLL_INTERVAL_SECONDS,
    sample_limit: int = BENCHMARK_STREAM_TIMELINE_SAMPLE_LIMIT,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "enabled": True,
        "ok": True,
        "poll_interval_seconds": poll_interval_seconds,
        "sample_limit": sample_limit,
        "target_substrings": stream_timeline_target_substrings(target),
        "samples": [],
        "sample_count": 0,
        "truncated": False,
    }
    if not isinstance(service, dict):
        payload["ok"] = False
        payload["error"] = "managed warm service metadata missing"
        return {"payload": payload}
    control_port = service.get("control_port")
    control_cookie_path = service.get("control_cookie_path")
    if not isinstance(control_port, int) or not isinstance(control_cookie_path, str):
        payload["ok"] = False
        payload["error"] = "managed warm service metadata missing control-port support"
        return {"payload": payload}

    stop_event = threading.Event()
    samples = payload["samples"]
    target_substrings = list(payload["target_substrings"])
    known_stream_ids: set[str] = set()

    def worker() -> None:
        try:
            while not stop_event.is_set():
                if not isinstance(samples, list):
                    break
                if len(samples) >= sample_limit:
                    payload["truncated"] = True
                    break
                snapshot = read_user_stream_snapshot(
                    host="127.0.0.1",
                    port=control_port,
                    cookie_path=Path(control_cookie_path),
                    target_substrings=target_substrings,
                    known_stream_ids=known_stream_ids,
                )
                samples.append(
                    compact_benchmark_stream_timeline_sample(
                        snapshot,
                        benchmark_started_monotonic=benchmark_started_monotonic,
                    )
                )
                if stop_event.wait(poll_interval_seconds):
                    break
        except Exception as exc:
            payload["ok"] = False
            payload["error"] = f"{type(exc).__name__}: {exc}"

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    return {
        "payload": payload,
        "stop_event": stop_event,
        "thread": thread,
    }


def stop_benchmark_stream_isolation_timeline_collector(
    collector: dict[str, object],
) -> None:
    payload = collector.get("payload")
    stop_event = collector.get("stop_event")
    thread = collector.get("thread")
    if isinstance(stop_event, threading.Event):
        stop_event.set()
    if isinstance(thread, threading.Thread):
        thread.join(timeout=2.0)
        if isinstance(payload, dict):
            payload["thread_joined"] = not thread.is_alive()
    if isinstance(payload, dict):
        samples = payload.get("samples")
        payload["sample_count"] = len(samples) if isinstance(samples, list) else 0


def stream_timeline_target_substrings(target: str) -> list[str]:
    match = re.match(r"^[a-z]+://([^/:?#]+)", target)
    if match is None:
        return []
    host = match.group(1).strip().lower()
    return [host] if host else []


def compact_benchmark_stream_timeline_sample(
    snapshot: dict[str, object],
    *,
    benchmark_started_monotonic: float,
) -> dict[str, object]:
    sample: dict[str, object] = {
        "elapsed_seconds": round(time.monotonic() - benchmark_started_monotonic, 3),
        "ok": snapshot.get("ok") is True,
    }
    for key in (
        "seconds",
        "user_stream_count",
        "total_stream_count",
        "unique_circuit_count",
        "max_streams_per_circuit",
        "single_circuit_share_pct",
        "status_counts",
        "circuit_purpose_counts",
        "matched_circuit_path_length_counts",
    ):
        if key in snapshot:
            sample[key] = snapshot.get(key)
    if snapshot.get("ok") is not True and isinstance(snapshot.get("error"), str):
        sample["error"] = snapshot.get("error")
    return sample


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
    if result.get("use_managed_open_gate"):
        open_gate_wait = result.get("open_gate_wait")
        if (
            not isinstance(open_gate_wait, dict)
            or open_gate_wait.get("ok") is not True
        ):
            return False
    if result.get("use_managed_general_circuit_gate"):
        general_circuit_wait = result.get("general_circuit_wait")
        if (
            not isinstance(general_circuit_wait, dict)
            or general_circuit_wait.get("ok") is not True
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
    open_gate_wait = result.get("open_gate_wait")
    open_gate_wait_seconds = 0.0
    if isinstance(open_gate_wait, dict) and isinstance(
        open_gate_wait.get("seconds"), (int, float)
    ):
        open_gate_wait_seconds = float(open_gate_wait["seconds"])
    general_circuit_wait = result.get("general_circuit_wait")
    general_circuit_wait_seconds = 0.0
    if isinstance(general_circuit_wait, dict) and isinstance(
        general_circuit_wait.get("seconds"), (int, float)
    ):
        general_circuit_wait_seconds = float(general_circuit_wait["seconds"])
    return round(
        float(warm_seconds)
        + open_gate_wait_seconds
        + general_circuit_wait_seconds
        + float(benchmark_wall_seconds),
        3,
    )


def open_gate_name(result: dict[str, object]) -> str | None:
    open_gate_wait = result.get("open_gate_wait")
    if not isinstance(open_gate_wait, dict):
        return None
    gate = open_gate_wait.get("gate")
    return str(gate) if isinstance(gate, str) else None


def open_gate_wait_seconds(result: dict[str, object]) -> float | None:
    open_gate_wait = result.get("open_gate_wait")
    if not isinstance(open_gate_wait, dict):
        return None
    seconds = open_gate_wait.get("seconds")
    if not isinstance(seconds, (int, float)):
        return None
    return round(float(seconds), 3)


def general_circuit_wait_seconds(result: dict[str, object]) -> float | None:
    general_circuit_wait = result.get("general_circuit_wait")
    if not isinstance(general_circuit_wait, dict):
        return None
    seconds = general_circuit_wait.get("seconds")
    if not isinstance(seconds, (int, float)):
        return None
    return round(float(seconds), 3)


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
            open_gate_wait_values = [open_gate_wait_seconds(result) for result in ok_rows]
            general_circuit_wait_values = [
                general_circuit_wait_seconds(result) for result in ok_rows
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
                "median_open_gate_wait_seconds": median_value(open_gate_wait_values),
                "median_general_circuit_wait_seconds": median_value(
                    general_circuit_wait_values
                ),
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
                "open_gate_wait_seconds": subtract_metric(
                    candidate.get("median_open_gate_wait_seconds"),
                    baseline.get("median_open_gate_wait_seconds"),
                ),
                "general_circuit_wait_seconds": subtract_metric(
                    candidate.get("median_general_circuit_wait_seconds"),
                    baseline.get("median_general_circuit_wait_seconds"),
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
                "open_gate": open_gate_name(result),
                "open_gate_wait_seconds": open_gate_wait_seconds(result),
                "general_circuit_wait_seconds": general_circuit_wait_seconds(result),
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
