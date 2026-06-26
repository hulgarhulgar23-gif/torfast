#!/usr/bin/env python3
"""Compare bundled, local-cold, and seeded Tor Browser first-use page loads."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import queue
import shutil
import statistics
import subprocess
import sys
import threading
import time


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from torfast.browser_defaults import read_browser_default_prefs, validate_default_prefs
from torfast.browser_startup_seed import DEFAULT_BROWSER_STARTUP_SEED_ROOT
from torfast.cli import discover_browser_bin, discover_tor_bin
from torfast.control import wait_for_general_circuits
from torfast.dir_cache_seed import (
    apply_seed_to_data_dir,
    describe_seed,
    update_seed_from_data_dir,
)
from run_browser_compare import (
    C_TOR_SOCKS_FLAGS,
    binary_info,
    cleanup_named_paths,
    collect_no_marionette_fingerprint_snapshot,
    normalize_browser_block_url_substrings,
    read_torrc_quality,
    record_proxy_output_tail,
    run_browser_benchmarks,
    start_c_tor,
    stop_process,
    summarize_browser,
    wait_after_boot,
    wait_for_line,
)


DEFAULT_TARGETS = [
    "https://check.torproject.org/",
    "https://www.torproject.org/",
]
BROADER_TARGETS = [
    "https://check.torproject.org/",
    "https://www.torproject.org/",
    "https://www.torproject.org/download/",
]
TARGET_PACKS = {
    "focused": DEFAULT_TARGETS,
    "broader": BROADER_TARGETS,
}

BUNDLED_PROFILE = "bundled_c_tor_browser"
BUNDLED_SEEDED_PROFILE = "bundled_c_tor_browser_seeded"
COLD_PROFILE = "local_c_tor_browser_cold"
SEEDED_PROFILE = "local_c_tor_browser_seeded"
SEEDED_CIRCUIT_READY_PROFILE = "local_c_tor_browser_seeded_general_circuit"
PROXY_LOG_TAIL_LINES = 200


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--browser-bin")
    parser.add_argument("--tor-bin")
    parser.add_argument("--bundled-tor-bin")
    parser.add_argument("--skip-bundled-tor", action="store_true")
    parser.add_argument(
        "--extra-bundled-seeded",
        action="store_true",
        help=(
            "add a bundled Tor seeded profile that primes and reapplies cache-only "
            "directory files using the Tor Browser app's bundled Tor binary"
        ),
    )
    parser.add_argument(
        "--extra-bundled-seeded-min-general-circuits",
        action="append",
        default=[],
        metavar="COUNT",
        help=(
            "add a bundled-seeded profile that waits for at least this many built "
            "GENERAL/CONFLUX_LINKED circuits before launching the browser"
        ),
    )
    parser.add_argument(
        "--extra-bundled-seeded-conflux-ux",
        action="append",
        default=[],
        choices=("latency", "throughput", "throughput_lowmem"),
        help=(
            "add a bundled-seeded same-window profile that keeps the bundled Tor "
            "binary and cache-only seed path, but sets the official "
            "ConfluxClientUX option to this value"
        ),
    )
    parser.add_argument(
        "--extra-seeded-general-circuit-ready",
        action="store_true",
        help=(
            "add a same-window seeded profile that waits for a built GENERAL or "
            "CONFLUX_LINKED circuit on the control port before launching the browser"
        ),
    )
    parser.add_argument(
        "--extra-seeded-post-boot-wait-seconds",
        action="append",
        default=[],
        metavar="SECONDS",
        help=(
            "add a same-window seeded profile that waits this many seconds after "
            "Tor boot before launching the browser; repeat to compare more values"
        ),
    )
    parser.add_argument("--runs", type=int, default=2)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--window-size", default="1000,1000")
    parser.add_argument(
        "--target-pack",
        choices=sorted(TARGET_PACKS),
        default="focused",
        help="named target set to use when --targets is omitted",
    )
    parser.add_argument("--targets", nargs="*", default=None)
    parser.add_argument("--port-base", type=int, default=19600)
    parser.add_argument("--post-boot-wait", type=float, default=0.0)
    parser.add_argument("--output-root", default="results")
    parser.add_argument("--compact-output", action="store_true")
    parser.add_argument(
        "--browser-startup-seed-root",
        default=str(DEFAULT_BROWSER_STARTUP_SEED_ROOT),
        help=(
            "shared startup-only Tor Browser seed to apply to fresh benchmark "
            "profiles before launch"
        ),
    )
    browser_startup_seed_group = parser.add_mutually_exclusive_group()
    browser_startup_seed_group.add_argument(
        "--browser-startup-seed",
        dest="no_browser_startup_seed",
        action="store_false",
        help=(
            "enable applying the shared startup-only browser seed in "
            "benchmarks; default is off because it is not yet a proven speed win"
        ),
    )
    browser_startup_seed_group.add_argument(
        "--no-browser-startup-seed",
        dest="no_browser_startup_seed",
        action="store_true",
        help="disable applying the shared startup-only browser seed in benchmarks",
    )
    parser.set_defaults(no_browser_startup_seed=True)
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
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    if args.runs < 1:
        print("--runs must be at least 1", file=sys.stderr)
        return 2
    if args.timeout <= 0:
        print("--timeout must be positive", file=sys.stderr)
        return 2
    if args.post_boot_wait < 0:
        print("--post-boot-wait must be non-negative", file=sys.stderr)
        return 2
    if (
        args.browser_max_persistent_connections_per_server is not None
        and not (1 <= args.browser_max_persistent_connections_per_server <= 32)
    ):
        print(
            "--browser-max-persistent-connections-per-server must be between 1 and 32",
            file=sys.stderr,
        )
        return 2
    if (
        args.browser_serial_http_connections
        and args.browser_max_persistent_connections_per_server is not None
    ):
        print(
            "--browser-serial-http-connections cannot be combined with "
            "--browser-max-persistent-connections-per-server",
            file=sys.stderr,
        )
        return 2
    try:
        browser_block_url_substrings = normalize_browser_block_url_substrings(
            args.browser_block_url_substrings
        )
    except ValueError as exc:
        print(f"--browser-block-url-substring {exc}", file=sys.stderr)
        return 2
    extra_seeded_post_boot_wait_seconds = parse_extra_wait_values(
        args.extra_seeded_post_boot_wait_seconds
    )
    extra_bundled_seeded_conflux_ux = parse_extra_conflux_ux_values(
        args.extra_bundled_seeded_conflux_ux
    )
    extra_bundled_seeded_min_general_circuits = parse_min_general_circuit_counts(
        args.extra_bundled_seeded_min_general_circuits
    )
    targets = resolve_targets(args.target_pack, args.targets)
    if not targets:
        print("at least one target is required", file=sys.stderr)
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
    output_dir = Path(args.output_root).resolve() / f"torfast-browser-compare-{run_id}"
    output_dir.mkdir(parents=True, exist_ok=True)

    browser_bin = Path(str(browser["path"])).resolve()
    tor_bin = Path(str(tor["path"])).resolve()
    bundled_tor = discover_bundled_tor_bin(browser_bin, args.bundled_tor_bin)
    bundled_tor_bin = Path(str(bundled_tor["path"])).resolve()
    include_bundled_tor = (
        not args.skip_bundled_tor and bundled_tor.get("exists") is True
    )
    profile_order_base = [COLD_PROFILE, SEEDED_PROFILE]
    if include_bundled_tor:
        profile_order_base = [BUNDLED_PROFILE, *profile_order_base]
    if include_bundled_tor and args.extra_bundled_seeded:
        profile_order_base.append(BUNDLED_SEEDED_PROFILE)
    bundled_seeded_conflux_profiles = [
        bundled_seeded_conflux_ux_profile_name(ux)
        for ux in extra_bundled_seeded_conflux_ux
    ]
    if include_bundled_tor:
        profile_order_base.extend(bundled_seeded_conflux_profiles)
    bundled_seeded_general_circuit_profiles = [
        bundled_seeded_general_circuits_profile_name(count)
        for count in extra_bundled_seeded_min_general_circuits
    ]
    if include_bundled_tor:
        profile_order_base.extend(bundled_seeded_general_circuit_profiles)
    if args.extra_seeded_general_circuit_ready:
        profile_order_base.append(SEEDED_CIRCUIT_READY_PROFILE)
    seeded_wait_profiles = [
        seeded_wait_profile_name(seconds)
        for seconds in extra_seeded_post_boot_wait_seconds
    ]
    profile_order_base.extend(seeded_wait_profiles)

    default_prefs = read_browser_default_prefs(browser_bin)
    payload: dict[str, object] = {
        "run_id": run_id,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "repo_root": str(REPO_ROOT),
        "output_dir": str(output_dir),
        "runs": args.runs,
        "target_pack": args.target_pack,
        "targets": targets,
        "timeout_seconds": args.timeout,
        "window_size": args.window_size,
        "post_boot_wait_seconds": args.post_boot_wait,
        "compact_output": args.compact_output,
        "browser_lab": {
            "serial_http_connections": args.browser_serial_http_connections,
            "max_persistent_connections_per_server": (
                args.browser_max_persistent_connections_per_server
            ),
        },
        "browser_request_blocker": {
            "enabled": bool(browser_block_url_substrings),
            "url_substrings": browser_block_url_substrings,
        },
        "browser_net_log": {
            "enabled": args.browser_net_log,
        },
        "browser_startup_seed": {
            "enabled": not args.no_browser_startup_seed,
            "seed_root": str(Path(args.browser_startup_seed_root).resolve()),
        },
        "cycle_order_strategy": "cyclic rotation over base profile order",
        "profile_order_base": profile_order_base,
        "skip_bundled_tor": args.skip_bundled_tor,
        "extra_bundled_seeded": args.extra_bundled_seeded,
        "extra_bundled_seeded_conflux_ux": extra_bundled_seeded_conflux_ux,
        "extra_bundled_seeded_min_general_circuits": (
            extra_bundled_seeded_min_general_circuits
        ),
        "extra_seeded_general_circuit_ready": args.extra_seeded_general_circuit_ready,
        "extra_seeded_post_boot_wait_seconds": extra_seeded_post_boot_wait_seconds,
        "system": {
            "platform": platform.platform(),
            "python": platform.python_version(),
        },
        "binaries": {
            "browser": {
                "path": str(browser_bin),
                "version": binary_info(browser_bin).get("version"),
            },
            "bundled_tor": {
                **bundled_tor,
                "path": str(bundled_tor_bin),
            },
            "local_c_tor": binary_info(tor_bin),
        },
        "browser_default_prefs": default_prefs,
        "browser_quality": {
            "default_prefs": validate_default_prefs(default_prefs),
            "no_marionette_fingerprint": collect_no_marionette_fingerprint_snapshot(
                browser_bin=browser_bin,
                output_dir=output_dir,
                window_size=args.window_size,
                compact_output=args.compact_output,
            ),
        },
        "profiles": {
            COLD_PROFILE: {"runs": []},
            SEEDED_PROFILE: {"runs": []},
            BUNDLED_SEEDED_PROFILE: (
                {"runs": []}
                if include_bundled_tor and args.extra_bundled_seeded
                else {
                    "skipped": True,
                    "reason": (
                        "disabled by default"
                        if include_bundled_tor
                        else f"bundled tor not found: {bundled_tor_bin}"
                    ),
                }
            ),
            SEEDED_CIRCUIT_READY_PROFILE: (
                {"runs": []}
                if args.extra_seeded_general_circuit_ready
                else {"skipped": True, "reason": "disabled by default"}
            ),
            BUNDLED_PROFILE: (
                {"runs": []}
                if include_bundled_tor
                else {
                    "skipped": True,
                    "reason": (
                        "disabled by --skip-bundled-tor"
                        if args.skip_bundled_tor
                        else f"bundled tor not found: {bundled_tor_bin}"
                    ),
                }
            ),
        },
    }
    for count, profile_name in zip(
        extra_bundled_seeded_min_general_circuits,
        bundled_seeded_general_circuit_profiles,
        strict=True,
    ):
        profiles_payload = payload["profiles"]
        assert isinstance(profiles_payload, dict)
        profiles_payload[profile_name] = {
            "runs": [],
            "min_general_circuit_count": count,
        }
    for ux, profile_name in zip(
        extra_bundled_seeded_conflux_ux,
        bundled_seeded_conflux_profiles,
        strict=True,
    ):
        profiles_payload = payload["profiles"]
        assert isinstance(profiles_payload, dict)
        profiles_payload[profile_name] = {
            "runs": [],
            "conflux_client_ux": ux,
        }
    for seconds, profile_name in zip(
        extra_seeded_post_boot_wait_seconds,
        seeded_wait_profiles,
        strict=True,
    ):
        profiles_payload = payload["profiles"]
        assert isinstance(profiles_payload, dict)
        profiles_payload[profile_name] = {
            "runs": [],
            "extra_post_boot_wait_seconds": seconds,
        }

    profiles = payload["profiles"]
    assert isinstance(profiles, dict)
    cold_runs = profiles[COLD_PROFILE]["runs"]
    seeded_runs = profiles[SEEDED_PROFILE]["runs"]
    bundled_seeded_profile = profiles[BUNDLED_SEEDED_PROFILE]
    assert isinstance(bundled_seeded_profile, dict)
    bundled_seeded_runs = bundled_seeded_profile.get("runs", [])
    bundled_seeded_conflux_runs_by_profile: dict[str, list[dict[str, object]]] = {}
    bundled_seeded_general_runs_by_profile: dict[str, list[dict[str, object]]] = {}
    seeded_circuit_ready_profile = profiles[SEEDED_CIRCUIT_READY_PROFILE]
    assert isinstance(seeded_circuit_ready_profile, dict)
    seeded_circuit_ready_runs = seeded_circuit_ready_profile.get("runs", [])
    seeded_wait_runs_by_profile: dict[str, list[dict[str, object]]] = {}
    assert isinstance(cold_runs, list)
    assert isinstance(seeded_runs, list)
    assert isinstance(bundled_seeded_runs, list)
    assert isinstance(seeded_circuit_ready_runs, list)
    for profile_name in bundled_seeded_conflux_profiles:
        bundled_seeded_conflux_profile = profiles[profile_name]
        assert isinstance(bundled_seeded_conflux_profile, dict)
        runs_payload = bundled_seeded_conflux_profile.get("runs", [])
        assert isinstance(runs_payload, list)
        bundled_seeded_conflux_runs_by_profile[profile_name] = runs_payload
    for profile_name in seeded_wait_profiles:
        seeded_wait_profile = profiles[profile_name]
        assert isinstance(seeded_wait_profile, dict)
        runs_payload = seeded_wait_profile.get("runs", [])
        assert isinstance(runs_payload, list)
        seeded_wait_runs_by_profile[profile_name] = runs_payload
    for profile_name in bundled_seeded_general_circuit_profiles:
        bundled_seeded_general_profile = profiles[profile_name]
        assert isinstance(bundled_seeded_general_profile, dict)
        runs_payload = bundled_seeded_general_profile.get("runs", [])
        assert isinstance(runs_payload, list)
        bundled_seeded_general_runs_by_profile[profile_name] = runs_payload
    bundled_profile = profiles[BUNDLED_PROFILE]
    assert isinstance(bundled_profile, dict)
    bundled_runs = bundled_profile.get("runs", [])
    assert isinstance(bundled_runs, list)

    for run_index in range(1, args.runs + 1):
        run_port_base = args.port_base + (run_index - 1) * len(profile_order_base)
        ports = {
            name: run_port_base + index
            for index, name in enumerate(profile_order_base)
        }
        for profile_name in cycle_order(run_index, profile_order_base):
            if profile_name == BUNDLED_PROFILE:
                bundled_runs.append(
                    run_unseeded_profile(
                        profile_name=BUNDLED_PROFILE,
                        run_index=run_index,
                        output_dir=output_dir,
                        browser_bin=browser_bin,
                        tor_bin=bundled_tor_bin,
                        port=ports[BUNDLED_PROFILE],
                        targets=targets,
                        timeout=args.timeout,
                        window_size=args.window_size,
                        post_boot_wait=args.post_boot_wait,
                        compact_output=args.compact_output,
                        browser_net_log=args.browser_net_log,
                        browser_serial_http_connections=(
                            args.browser_serial_http_connections
                        ),
                        browser_max_persistent_connections_per_server=(
                            args.browser_max_persistent_connections_per_server
                        ),
                        browser_block_url_substrings=browser_block_url_substrings,
                        browser_startup_seed_root=Path(
                            args.browser_startup_seed_root
                        ).resolve(),
                        no_browser_startup_seed=args.no_browser_startup_seed,
                    )
                )
            elif profile_name == BUNDLED_SEEDED_PROFILE:
                bundled_seeded_runs.append(
                    run_seeded_profile(
                        profile_name=BUNDLED_SEEDED_PROFILE,
                        run_index=run_index,
                        output_dir=output_dir,
                        browser_bin=browser_bin,
                        tor_bin=bundled_tor_bin,
                        port=ports[BUNDLED_SEEDED_PROFILE],
                        targets=targets,
                        timeout=args.timeout,
                        window_size=args.window_size,
                        post_boot_wait=args.post_boot_wait,
                        compact_output=args.compact_output,
                        browser_net_log=args.browser_net_log,
                        browser_serial_http_connections=(
                            args.browser_serial_http_connections
                        ),
                        browser_max_persistent_connections_per_server=(
                            args.browser_max_persistent_connections_per_server
                        ),
                        browser_block_url_substrings=browser_block_url_substrings,
                        browser_startup_seed_root=Path(
                            args.browser_startup_seed_root
                        ).resolve(),
                        no_browser_startup_seed=args.no_browser_startup_seed,
                    )
                )
            elif profile_name in bundled_seeded_conflux_runs_by_profile:
                bundled_seeded_conflux_runs_by_profile[profile_name].append(
                    run_seeded_profile(
                        profile_name=profile_name,
                        run_index=run_index,
                        output_dir=output_dir,
                        browser_bin=browser_bin,
                        tor_bin=bundled_tor_bin,
                        port=ports[profile_name],
                        targets=targets,
                        timeout=args.timeout,
                        window_size=args.window_size,
                        post_boot_wait=args.post_boot_wait,
                        compact_output=args.compact_output,
                        browser_net_log=args.browser_net_log,
                        browser_serial_http_connections=(
                            args.browser_serial_http_connections
                        ),
                        browser_max_persistent_connections_per_server=(
                            args.browser_max_persistent_connections_per_server
                        ),
                        browser_block_url_substrings=browser_block_url_substrings,
                        browser_startup_seed_root=Path(
                            args.browser_startup_seed_root
                        ).resolve(),
                        no_browser_startup_seed=args.no_browser_startup_seed,
                        conflux_client_ux=profile_bundled_seeded_conflux_ux(
                            profile_name
                        ),
                    )
                )
            elif profile_name in bundled_seeded_general_runs_by_profile:
                bundled_seeded_general_runs_by_profile[profile_name].append(
                    run_seeded_profile(
                        profile_name=profile_name,
                        run_index=run_index,
                        output_dir=output_dir,
                        browser_bin=browser_bin,
                        tor_bin=bundled_tor_bin,
                        port=ports[profile_name],
                        targets=targets,
                        timeout=args.timeout,
                        window_size=args.window_size,
                        post_boot_wait=args.post_boot_wait,
                        compact_output=args.compact_output,
                        browser_net_log=args.browser_net_log,
                        browser_serial_http_connections=(
                            args.browser_serial_http_connections
                        ),
                        browser_max_persistent_connections_per_server=(
                            args.browser_max_persistent_connections_per_server
                        ),
                        browser_block_url_substrings=browser_block_url_substrings,
                        browser_startup_seed_root=Path(
                            args.browser_startup_seed_root
                        ).resolve(),
                        no_browser_startup_seed=args.no_browser_startup_seed,
                        min_general_circuit_count=profile_min_general_circuit_count(
                            profile_name
                        ),
                    )
                )
            elif profile_name == SEEDED_CIRCUIT_READY_PROFILE:
                seeded_circuit_ready_runs.append(
                    run_seeded_profile(
                        profile_name=SEEDED_CIRCUIT_READY_PROFILE,
                        run_index=run_index,
                        output_dir=output_dir,
                        browser_bin=browser_bin,
                        tor_bin=tor_bin,
                        port=ports[SEEDED_CIRCUIT_READY_PROFILE],
                        targets=targets,
                        timeout=args.timeout,
                        window_size=args.window_size,
                        post_boot_wait=args.post_boot_wait,
                        compact_output=args.compact_output,
                        browser_net_log=args.browser_net_log,
                        browser_serial_http_connections=(
                            args.browser_serial_http_connections
                        ),
                        browser_max_persistent_connections_per_server=(
                            args.browser_max_persistent_connections_per_server
                        ),
                        browser_block_url_substrings=browser_block_url_substrings,
                        browser_startup_seed_root=Path(
                            args.browser_startup_seed_root
                        ).resolve(),
                        no_browser_startup_seed=args.no_browser_startup_seed,
                        wait_for_general_circuit_ready=True,
                    )
                )
            elif profile_name in seeded_wait_runs_by_profile:
                seeded_wait_runs_by_profile[profile_name].append(
                    run_seeded_profile(
                        profile_name=profile_name,
                        run_index=run_index,
                        output_dir=output_dir,
                        browser_bin=browser_bin,
                        tor_bin=tor_bin,
                        port=ports[profile_name],
                        targets=targets,
                        timeout=args.timeout,
                        window_size=args.window_size,
                        post_boot_wait=profile_extra_post_boot_wait_seconds(profile_name),
                        compact_output=args.compact_output,
                        browser_net_log=args.browser_net_log,
                        browser_serial_http_connections=(
                            args.browser_serial_http_connections
                        ),
                        browser_max_persistent_connections_per_server=(
                            args.browser_max_persistent_connections_per_server
                        ),
                        browser_block_url_substrings=browser_block_url_substrings,
                        browser_startup_seed_root=Path(
                            args.browser_startup_seed_root
                        ).resolve(),
                        no_browser_startup_seed=args.no_browser_startup_seed,
                    )
                )
            elif profile_name == COLD_PROFILE:
                cold_runs.append(
                    run_unseeded_profile(
                        profile_name=COLD_PROFILE,
                        run_index=run_index,
                        output_dir=output_dir,
                        browser_bin=browser_bin,
                        tor_bin=tor_bin,
                        port=ports[COLD_PROFILE],
                        targets=targets,
                        timeout=args.timeout,
                        window_size=args.window_size,
                        post_boot_wait=args.post_boot_wait,
                        compact_output=args.compact_output,
                        browser_net_log=args.browser_net_log,
                        browser_serial_http_connections=(
                            args.browser_serial_http_connections
                        ),
                        browser_max_persistent_connections_per_server=(
                            args.browser_max_persistent_connections_per_server
                        ),
                        browser_block_url_substrings=browser_block_url_substrings,
                        browser_startup_seed_root=Path(
                            args.browser_startup_seed_root
                        ).resolve(),
                        no_browser_startup_seed=args.no_browser_startup_seed,
                    )
                )
            else:
                seeded_runs.append(
                    run_seeded_profile(
                        run_index=run_index,
                        output_dir=output_dir,
                        browser_bin=browser_bin,
                        tor_bin=tor_bin,
                        port=ports[SEEDED_PROFILE],
                        targets=targets,
                        timeout=args.timeout,
                        window_size=args.window_size,
                        post_boot_wait=args.post_boot_wait,
                        compact_output=args.compact_output,
                        browser_net_log=args.browser_net_log,
                        browser_serial_http_connections=(
                            args.browser_serial_http_connections
                        ),
                        browser_max_persistent_connections_per_server=(
                            args.browser_max_persistent_connections_per_server
                        ),
                        browser_block_url_substrings=browser_block_url_substrings,
                        browser_startup_seed_root=Path(
                            args.browser_startup_seed_root
                        ).resolve(),
                        no_browser_startup_seed=args.no_browser_startup_seed,
                    )
                )

    add_profile_summary(bundled_profile, targets)
    add_profile_summary(profiles[BUNDLED_SEEDED_PROFILE], targets)
    for profile_name in bundled_seeded_conflux_profiles:
        add_profile_summary(profiles[profile_name], targets)
    for profile_name in bundled_seeded_general_circuit_profiles:
        add_profile_summary(profiles[profile_name], targets)
    add_profile_summary(profiles[COLD_PROFILE], targets)
    add_profile_summary(profiles[SEEDED_PROFILE], targets)
    add_profile_summary(profiles[SEEDED_CIRCUIT_READY_PROFILE], targets)
    for profile_name in seeded_wait_profiles:
        add_profile_summary(profiles[profile_name], targets)
    payload["summary"] = short_summary(payload)

    output_path = output_dir / "torfast-browser-compare.json"
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"wrote {output_path}")
    print(json.dumps(payload["summary"], indent=2, sort_keys=True))
    return 0 if payload_ok(payload) else 1


def discover_bundled_tor_bin(
    browser_bin: Path, explicit: str | None
) -> dict[str, object]:
    path = (
        Path(explicit).resolve()
        if explicit is not None
        else (browser_bin.parent / "Tor" / "tor").resolve()
    )
    info = binary_info(path)
    info["source"] = "explicit" if explicit is not None else "browser bundle"
    return info


def resolve_targets(target_pack: str, explicit_targets: list[str] | None) -> list[str]:
    if explicit_targets is not None:
        return [target for target in explicit_targets if target]
    return list(TARGET_PACKS[target_pack])


def parse_extra_wait_values(values: list[str]) -> list[float]:
    parsed: list[float] = []
    seen: set[float] = set()
    for raw in values:
        try:
            seconds = float(raw)
        except ValueError:
            raise SystemExit(
                f"--extra-seeded-post-boot-wait-seconds must be numeric, got: {raw}"
            ) from None
        if seconds < 0:
            raise SystemExit(
                "--extra-seeded-post-boot-wait-seconds must be non-negative"
            )
        rounded = round(seconds, 3)
        if rounded in seen:
            continue
        seen.add(rounded)
        parsed.append(rounded)
    return parsed


def parse_extra_conflux_ux_values(values: list[str]) -> list[str]:
    parsed: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        parsed.append(value)
    return parsed


def seeded_wait_profile_name(seconds: float) -> str:
    ms = round(seconds * 1000)
    return f"{SEEDED_PROFILE}_wait_{ms}ms"


def profile_extra_post_boot_wait_seconds(profile_name: str) -> float:
    if not profile_name.startswith(f"{SEEDED_PROFILE}_wait_") or not profile_name.endswith("ms"):
        return 0.0
    raw_ms = profile_name.removeprefix(f"{SEEDED_PROFILE}_wait_").removesuffix("ms")
    try:
        return round(int(raw_ms) / 1000.0, 3)
    except ValueError:
        return 0.0


def parse_min_general_circuit_counts(values: list[str]) -> list[int]:
    parsed: list[int] = []
    seen: set[int] = set()
    for raw in values:
        try:
            count = int(raw)
        except ValueError:
            raise SystemExit(
                f"--extra-bundled-seeded-min-general-circuits must be an integer, got: {raw}"
            ) from None
        if count < 1:
            raise SystemExit(
                "--extra-bundled-seeded-min-general-circuits must be at least 1"
            )
        if count in seen:
            continue
        seen.add(count)
        parsed.append(count)
    return parsed


def bundled_seeded_general_circuits_profile_name(count: int) -> str:
    return f"{BUNDLED_SEEDED_PROFILE}_general_circuits_{count}"


def bundled_seeded_conflux_ux_profile_name(conflux_client_ux: str) -> str:
    return f"{BUNDLED_SEEDED_PROFILE}_confluxux_{conflux_client_ux}"


def profile_bundled_seeded_conflux_ux(profile_name: str) -> str | None:
    prefix = f"{BUNDLED_SEEDED_PROFILE}_confluxux_"
    if not profile_name.startswith(prefix):
        return None
    raw = profile_name.removeprefix(prefix)
    return raw or None


def profile_min_general_circuit_count(profile_name: str) -> int | None:
    prefix = f"{BUNDLED_SEEDED_PROFILE}_general_circuits_"
    if not profile_name.startswith(prefix):
        return None
    raw = profile_name.removeprefix(prefix)
    try:
        return int(raw)
    except ValueError:
        return None


def is_seeded_profile_name(profile_name: str) -> bool:
    return "_seeded" in profile_name


def cycle_order(run_index: int, profile_names: list[str]) -> list[str]:
    if not profile_names:
        return []
    offset = (run_index - 1) % len(profile_names)
    return profile_names[offset:] + profile_names[:offset]


def cleanup_path(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)


def run_unseeded_profile(
    *,
    profile_name: str,
    run_index: int,
    output_dir: Path,
    browser_bin: Path,
    tor_bin: Path,
    port: int,
    targets: list[str],
    timeout: float,
    window_size: str,
    post_boot_wait: float,
    compact_output: bool,
    browser_net_log: bool = False,
    browser_serial_http_connections: bool = False,
    browser_max_persistent_connections_per_server: int | None = None,
    browser_block_url_substrings: list[str] | None = None,
    browser_startup_seed_root: Path = DEFAULT_BROWSER_STARTUP_SEED_ROOT,
    no_browser_startup_seed: bool = False,
) -> dict[str, object]:
    run_dir = output_dir / profile_name / f"run-{run_index}"
    cleanup_path(run_dir)
    return run_measured_c_tor_browser(
        profile_name=profile_name,
        run_index=run_index,
        run_dir=run_dir,
        browser_bin=browser_bin,
        tor_bin=tor_bin,
        port=port,
        targets=targets,
        timeout=timeout,
        window_size=window_size,
        post_boot_wait=post_boot_wait,
        compact_output=compact_output,
        browser_net_log=browser_net_log,
        browser_serial_http_connections=browser_serial_http_connections,
        browser_max_persistent_connections_per_server=(
            browser_max_persistent_connections_per_server
        ),
        browser_block_url_substrings=browser_block_url_substrings,
        browser_startup_seed_root=browser_startup_seed_root,
        no_browser_startup_seed=no_browser_startup_seed,
    )


def run_seeded_profile(
    *,
    profile_name: str = SEEDED_PROFILE,
    run_index: int,
    output_dir: Path,
    browser_bin: Path,
    tor_bin: Path,
    port: int,
    targets: list[str],
    timeout: float,
    window_size: str,
    post_boot_wait: float,
    compact_output: bool,
    browser_net_log: bool = False,
    browser_serial_http_connections: bool = False,
    browser_max_persistent_connections_per_server: int | None = None,
    browser_block_url_substrings: list[str] | None = None,
    browser_startup_seed_root: Path = DEFAULT_BROWSER_STARTUP_SEED_ROOT,
    no_browser_startup_seed: bool = False,
    wait_for_general_circuit_ready: bool = False,
    min_general_circuit_count: int | None = None,
    conflux_client_ux: str | None = None,
) -> dict[str, object]:
    run_dir = output_dir / profile_name / f"run-{run_index}"
    cleanup_path(run_dir)
    seed_root = run_dir / "dir-cache-seed"
    prime_result = prime_seed_cache(
        run_index=run_index,
        run_dir=run_dir / "seed-refresh",
        tor_bin=tor_bin,
        port=port,
        seed_root=seed_root,
        compact_output=compact_output,
        conflux_client_ux=conflux_client_ux,
    )
    result: dict[str, object] = {
        "profile": profile_name,
        "run_index": run_index,
        "port": port,
        "seed_root": str(seed_root),
        "seed_prime": prime_result,
        "wait_for_general_circuit_ready": wait_for_general_circuit_ready,
        "min_general_circuit_count": min_general_circuit_count,
        "conflux_client_ux": conflux_client_ux,
    }
    seed_update = prime_result.get("seed_update")
    if (
        not isinstance(seed_update, dict)
        or not seed_update.get("ok")
        or not seed_update.get("updated")
    ):
        result["skipped"] = True
        result["skip_reason"] = "seed prime failed"
        result["seed_description"] = describe_seed(seed_root)
        return result

    measured_dir = run_dir / "measured"
    data_dir = measured_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    seed_apply = apply_seed_to_data_dir(data_dir, seed_root)
    result["seed_apply"] = seed_apply
    result["seed_description"] = describe_seed(seed_root)
    if not seed_apply.get("ok") or not seed_apply.get("applied"):
        result["skipped"] = True
        result["skip_reason"] = "seed apply failed"
        if compact_output:
            result["proxy_artifacts"] = cleanup_named_paths({"data_dir": data_dir})
        return result

    measured = run_measured_c_tor_browser(
        profile_name=profile_name,
        run_index=run_index,
        run_dir=measured_dir,
        browser_bin=browser_bin,
        tor_bin=tor_bin,
        port=port,
        targets=targets,
        timeout=timeout,
        window_size=window_size,
        post_boot_wait=post_boot_wait,
        compact_output=compact_output,
        browser_net_log=browser_net_log,
        browser_serial_http_connections=browser_serial_http_connections,
        browser_max_persistent_connections_per_server=(
            browser_max_persistent_connections_per_server
        ),
        browser_block_url_substrings=browser_block_url_substrings,
        browser_startup_seed_root=browser_startup_seed_root,
        no_browser_startup_seed=no_browser_startup_seed,
        data_dir=data_dir,
        seed_apply=seed_apply,
        seed_root=seed_root,
        reset_run_dir=False,
        wait_for_general_circuit_ready=wait_for_general_circuit_ready,
        min_general_circuit_count=min_general_circuit_count,
        conflux_client_ux=conflux_client_ux,
    )
    result.update(measured)
    result["seed_description"] = describe_seed(seed_root)
    return result


def prime_seed_cache(
    *,
    run_index: int,
    run_dir: Path,
    tor_bin: Path,
    port: int,
    seed_root: Path,
    compact_output: bool,
    conflux_client_ux: str | None,
) -> dict[str, object]:
    cleanup_path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    data_dir = run_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    torrc = run_dir / "torrc"
    proc, lines = start_c_tor(
        tor_bin=tor_bin,
        port=port,
        data_dir=data_dir,
        torrc=torrc,
        conflux_client_ux=conflux_client_ux,
    )
    result: dict[str, object] = {
        "profile": "seed_refresh",
        "run_index": run_index,
        "port": port,
        "state_root": str(run_dir),
        "data_dir": str(data_dir),
        "conflux_client_ux": conflux_client_ux,
    }
    try:
        boot = wait_for_line(
            proc,
            lines,
            timeout=180.0,
            ready_text="Bootstrapped 100%",
            process_name="seed refresh tor",
        )
        result["boot"] = boot
        result["torrc"] = read_torrc_quality(torrc)
    finally:
        stop_process(proc)
        record_proxy_output_tail(result, lines, limit=PROXY_LOG_TAIL_LINES)

    if isinstance(result.get("boot"), dict) and result["boot"].get("ok"):
        result["seed_update"] = update_seed_from_data_dir(data_dir, seed_root)
    else:
        result["seed_update"] = {
            "ok": False,
            "updated": False,
            "reason": "seed refresh bootstrap failed",
            "seed_root": str(seed_root),
        }
    result["seed_description"] = describe_seed(seed_root)
    if compact_output:
        result["proxy_artifacts"] = cleanup_named_paths({"data_dir": data_dir})
    return result


def run_measured_c_tor_browser(
    *,
    profile_name: str,
    run_index: int,
    run_dir: Path,
    browser_bin: Path,
    tor_bin: Path,
    port: int,
    targets: list[str],
    timeout: float,
    window_size: str,
    post_boot_wait: float,
    compact_output: bool,
    browser_net_log: bool = False,
    browser_serial_http_connections: bool = False,
    browser_max_persistent_connections_per_server: int | None = None,
    browser_block_url_substrings: list[str] | None = None,
    browser_startup_seed_root: Path = DEFAULT_BROWSER_STARTUP_SEED_ROOT,
    no_browser_startup_seed: bool = False,
    data_dir: Path | None = None,
    seed_apply: dict[str, object] | None = None,
    seed_root: Path | None = None,
    reset_run_dir: bool = True,
    wait_for_general_circuit_ready: bool = False,
    min_general_circuit_count: int | None = None,
    conflux_client_ux: str | None = None,
) -> dict[str, object]:
    if reset_run_dir:
        cleanup_path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    if data_dir is None:
        data_dir = run_dir / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
    torrc = run_dir / "torrc"
    result: dict[str, object] = {
        "profile": profile_name,
        "run_index": run_index,
        "port": port,
        "state_root": str(run_dir),
        "data_dir": str(data_dir),
        "cache_mode": "seeded" if is_seeded_profile_name(profile_name) else "cold",
        "post_boot_wait_seconds": post_boot_wait,
        "seed_apply": seed_apply,
        "seed_root": str(seed_root) if seed_root is not None else None,
        "wait_for_general_circuit_ready": wait_for_general_circuit_ready,
        "min_general_circuit_count": min_general_circuit_count,
        "conflux_client_ux": conflux_client_ux,
    }
    requested_general_circuit_count = (
        min_general_circuit_count
        if min_general_circuit_count is not None
        else (1 if wait_for_general_circuit_ready else None)
    )
    control_port = port + 10_000 if requested_general_circuit_count is not None else None
    control_cookie_path = (
        run_dir / "control_auth_cookie"
        if requested_general_circuit_count is not None
        else None
    )
    proc, lines = start_c_tor_profile(
        tor_bin=tor_bin,
        port=port,
        data_dir=data_dir,
        torrc=torrc,
        control_port=control_port,
        control_cookie_path=control_cookie_path,
        conflux_client_ux=conflux_client_ux,
    )
    try:
        boot = wait_for_line(
            proc,
            lines,
            timeout=180.0,
            ready_text="Bootstrapped 100%",
            process_name=profile_name,
        )
        result["boot"] = boot
        result["torrc"] = read_torrc_quality(torrc)
        result["benchmarks"] = {}
        if boot["ok"]:
            if requested_general_circuit_count is not None:
                assert control_port is not None
                assert control_cookie_path is not None
                general_circuit_ready = wait_for_general_circuits(
                    host="127.0.0.1",
                    port=control_port,
                    cookie_path=control_cookie_path,
                    timeout=min(60.0, timeout),
                    min_count=requested_general_circuit_count,
                )
                annotate_general_circuit_ready(boot, general_circuit_ready)
                result["general_circuit_ready"] = general_circuit_ready
                if not general_circuit_ready.get("ok"):
                    return result
            wait_after_boot(post_boot_wait)
            result["benchmarks"] = run_browser_benchmarks(
                browser_bin=browser_bin,
                port=port,
                output_dir=run_dir,
                targets=targets,
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
                no_browser_startup_seed=no_browser_startup_seed,
            )
    finally:
        stop_process(proc)
        record_proxy_output_tail(result, lines, limit=PROXY_LOG_TAIL_LINES)
        if compact_output:
            result["proxy_artifacts"] = cleanup_named_paths({"data_dir": data_dir})
    return result


def start_c_tor_profile(
    *,
    tor_bin: Path,
    port: int,
    data_dir: Path,
    torrc: Path,
    control_port: int | None = None,
    control_cookie_path: Path | None = None,
    conflux_client_ux: str | None = None,
) -> tuple[subprocess.Popen[str], queue.Queue[str]]:
    torrc_lines = [
        f"SocksPort 127.0.0.1:{port} {' '.join(C_TOR_SOCKS_FLAGS)}",
        f"DataDirectory {data_dir.resolve()}",
        "ClientOnly 1",
        "AvoidDiskWrites 1",
        "SafeLogging 1",
        "Log notice stdout",
        "ConfluxEnabled auto",
    ]
    if conflux_client_ux:
        torrc_lines.append(f"ConfluxClientUX {conflux_client_ux}")
    if control_port is not None and control_cookie_path is not None:
        torrc_lines.extend(
            [
                f"ControlPort 127.0.0.1:{control_port}",
                "CookieAuthentication 1",
                f"CookieAuthFile {control_cookie_path.resolve()}",
            ]
        )
    torrc.write_text("\n".join(torrc_lines) + "\n")
    proc = subprocess.Popen(
        [str(tor_bin), "-f", str(torrc)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    lines: queue.Queue[str] = queue.Queue()
    threading.Thread(target=read_lines, args=(proc, lines), daemon=True).start()
    return proc, lines


def read_lines(proc: subprocess.Popen[str], lines: queue.Queue[str]) -> None:
    assert proc.stdout is not None
    for line in proc.stdout:
        lines.put(line.rstrip())


def all_benchmarks_ok(benchmarks: object) -> bool:
    if not isinstance(benchmarks, dict) or not benchmarks:
        return False
    for bench in benchmarks.values():
        if not isinstance(bench, dict):
            return False
        summary = bench.get("summary")
        if not isinstance(summary, dict) or not summary.get("ok"):
            return False
    return True


def profile_run_ok(run: dict[str, object]) -> bool:
    if run.get("skipped"):
        return False
    boot = run.get("boot")
    if not isinstance(boot, dict) or not boot.get("ok"):
        return False
    if not all_benchmarks_ok(run.get("benchmarks")):
        return False
    general_circuit_ready = run.get("general_circuit_ready")
    if isinstance(general_circuit_ready, dict) and not general_circuit_ready.get("ok"):
        return False
    profile_name = str(run.get("profile", ""))
    if not is_seeded_profile_name(profile_name):
        return True
    seed_prime = run.get("seed_prime")
    if not isinstance(seed_prime, dict):
        return False
    seed_prime_boot = seed_prime.get("boot")
    seed_update = seed_prime.get("seed_update")
    seed_apply = run.get("seed_apply")
    return (
        isinstance(seed_prime_boot, dict)
        and seed_prime_boot.get("ok")
        and isinstance(seed_update, dict)
        and seed_update.get("ok")
        and seed_update.get("updated")
        and isinstance(seed_apply, dict)
        and seed_apply.get("ok")
        and seed_apply.get("applied")
        and (
            profile_name != SEEDED_CIRCUIT_READY_PROFILE
            or (
                isinstance(general_circuit_ready, dict)
                and general_circuit_ready.get("ok")
            )
        )
    )


def annotate_general_circuit_ready(
    boot: dict[str, object],
    general_circuit_ready: dict[str, object],
) -> None:
    if not general_circuit_ready.get("ok"):
        return
    ready_seconds = general_circuit_ready.get("seconds")
    boot_seconds = boot.get("seconds")
    if not isinstance(ready_seconds, (int, float)):
        return
    general_circuit_ready["after_boot_seconds"] = float(ready_seconds)
    if isinstance(boot_seconds, (int, float)):
        general_circuit_ready["total_ready_seconds"] = round(
            float(boot_seconds) + float(ready_seconds),
            3,
        )


def launch_ready_seconds_for_run(run: dict[str, object]) -> float | None:
    general_circuit_ready = run.get("general_circuit_ready")
    if isinstance(general_circuit_ready, dict) and isinstance(
        general_circuit_ready.get("total_ready_seconds"),
        (int, float),
    ):
        return float(general_circuit_ready["total_ready_seconds"])
    boot = run.get("boot")
    if isinstance(boot, dict) and isinstance(boot.get("seconds"), (int, float)):
        total = float(boot["seconds"])
        post_boot_wait_seconds = run.get("post_boot_wait_seconds")
        if isinstance(post_boot_wait_seconds, (int, float)):
            total += float(post_boot_wait_seconds)
        return total
    return None


def browser_run_for_target(run: dict[str, object], url: str) -> dict[str, object] | None:
    benchmarks = run.get("benchmarks")
    if not isinstance(benchmarks, dict):
        return None
    bench = benchmarks.get(url)
    if not isinstance(bench, dict):
        return None
    rows = bench.get("runs")
    if not isinstance(rows, list) or not rows:
        return None
    result = rows[0]
    return result if isinstance(result, dict) else None


def summarize_target_runs(
    runs: list[dict[str, object]], url: str
) -> dict[str, object]:
    browser_results = []
    launch_elapsed_values = []
    launch_load_values = []
    cycle_successes = 0
    for run in runs:
        browser_result = browser_run_for_target(run, url)
        if browser_result is None:
            continue
        browser_results.append(browser_result)
        if browser_result.get("ok"):
            cycle_successes += 1
            boot_seconds = launch_ready_seconds_for_run(run)
            elapsed_ms = browser_result.get("elapsed_ms")
            load_ms = browser_result.get("load_ms")
            if isinstance(boot_seconds, (int, float)) and isinstance(
                elapsed_ms, (int, float)
            ):
                launch_elapsed_values.append(boot_seconds * 1000 + elapsed_ms)
            if isinstance(boot_seconds, (int, float)) and isinstance(
                load_ms, (int, float)
            ):
                launch_load_values.append(boot_seconds * 1000 + load_ms)
    if browser_results:
        summary = summarize_browser(browser_results)
    else:
        summary = {"ok": False, "successes": 0, "failures": len(runs)}
    summary["cycle_runs"] = len(runs)
    summary["cycle_successes"] = cycle_successes
    summary["cycle_failures"] = len(runs) - cycle_successes
    summary["ok"] = cycle_successes == len(runs) and len(runs) > 0
    summary["median_launch_elapsed_ms"] = (
        median(launch_elapsed_values) if launch_elapsed_values else None
    )
    summary["median_launch_load_ms"] = (
        median(launch_load_values) if launch_load_values else None
    )
    return summary


def summarize_profile_runs(
    runs: list[dict[str, object]], targets: list[str]
) -> dict[str, object]:
    boot_values = [
        boot.get("seconds")
        for run in runs
        if isinstance((boot := run.get("boot")), dict)
        and isinstance(boot.get("seconds"), (int, float))
    ]
    ok_runs = [run for run in runs if profile_run_ok(run)]
    summary: dict[str, object] = {
        "ok": len(ok_runs) == len(runs) and len(runs) > 0,
        "runs": len(runs),
        "ok_runs": len(ok_runs),
        "median_boot_seconds": median(boot_values) if boot_values else None,
        "targets": {
            url: summarize_target_runs(runs, url)
            for url in targets
        },
    }
    launch_ready_values = [
        launch_ready_seconds
        for run in runs
        if isinstance((launch_ready_seconds := launch_ready_seconds_for_run(run)), (int, float))
    ]
    if launch_ready_values:
        summary["median_launch_ready_seconds"] = median(launch_ready_values)
    seed_prime_boot_values = [
        seed_prime_boot.get("seconds")
        for run in runs
        if isinstance((seed_prime := run.get("seed_prime")), dict)
        and isinstance((seed_prime_boot := seed_prime.get("boot")), dict)
        and isinstance(seed_prime_boot.get("seconds"), (int, float))
    ]
    if seed_prime_boot_values:
        summary["median_seed_prime_boot_seconds"] = median(seed_prime_boot_values)
        summary["seed_apply_successes"] = sum(
            1
            for run in runs
            if isinstance((seed_apply := run.get("seed_apply")), dict)
            and seed_apply.get("ok")
            and seed_apply.get("applied")
        )
    general_circuit_ready_values = [
        general_circuit_ready.get("total_ready_seconds")
        for run in runs
        if isinstance((general_circuit_ready := run.get("general_circuit_ready")), dict)
        and isinstance(general_circuit_ready.get("total_ready_seconds"), (int, float))
    ]
    if general_circuit_ready_values:
        summary["median_general_circuit_ready_seconds"] = median(
            general_circuit_ready_values
        )
        general_circuit_post_boot_wait_values = [
            general_circuit_ready.get("after_boot_seconds")
            for run in runs
            if isinstance((general_circuit_ready := run.get("general_circuit_ready")), dict)
            and isinstance(general_circuit_ready.get("after_boot_seconds"), (int, float))
        ]
        if general_circuit_post_boot_wait_values:
            summary["median_general_circuit_post_boot_wait_seconds"] = median(
                general_circuit_post_boot_wait_values
            )
    return summary


def add_profile_summary(profile: dict[str, object], targets: list[str]) -> None:
    if profile.get("skipped"):
        return
    runs = profile.get("runs", [])
    assert isinstance(runs, list)
    profile["summary"] = summarize_profile_runs(runs, targets)


def summary_delta(candidate_value: object, baseline_value: object) -> float | None:
    if not isinstance(candidate_value, (int, float)):
        return None
    if not isinstance(baseline_value, (int, float)):
        return None
    return round(candidate_value - baseline_value, 3)


def target_delta_summary(
    candidate_summary: dict[str, object], baseline_summary: dict[str, object]
) -> dict[str, object]:
    candidate_targets = candidate_summary.get("targets", {})
    baseline_targets = baseline_summary.get("targets", {})
    if not isinstance(candidate_targets, dict) or not isinstance(baseline_targets, dict):
        return {}
    return {
        url: {
            "boot_seconds": summary_delta(
                candidate_summary.get("median_boot_seconds"),
                baseline_summary.get("median_boot_seconds"),
            ),
            "launch_elapsed_ms": summary_delta(
                candidate_target.get("median_launch_elapsed_ms"),
                baseline_target.get("median_launch_elapsed_ms"),
            ),
            "launch_load_ms": summary_delta(
                candidate_target.get("median_launch_load_ms"),
                baseline_target.get("median_launch_load_ms"),
            ),
            "elapsed_ms": summary_delta(
                candidate_target.get("median_elapsed_ms"),
                baseline_target.get("median_elapsed_ms"),
            ),
            "load_ms": summary_delta(
                candidate_target.get("median_load_ms"),
                baseline_target.get("median_load_ms"),
            ),
        }
        for url, baseline_target in baseline_targets.items()
        if isinstance(baseline_target, dict)
        and isinstance((candidate_target := candidate_targets.get(url)), dict)
    }


def short_summary(payload: dict[str, object]) -> dict[str, object]:
    profiles = payload.get("profiles", {})
    assert isinstance(profiles, dict)
    summary: dict[str, object] = {
        "ok": payload_ok(payload),
        "runs": payload.get("runs"),
        "targets": payload.get("targets"),
        "profiles": {},
    }
    profiles_summary = summary["profiles"]
    assert isinstance(profiles_summary, dict)
    for name, profile in profiles.items():
        if not isinstance(profile, dict):
            continue
        if profile.get("skipped"):
            profiles_summary[name] = {
                "skipped": True,
                "reason": profile.get("reason") or profile.get("skip_reason"),
            }
            continue
        profile_summary = profile.get("summary", {})
        if not isinstance(profile_summary, dict):
            continue
        targets_summary = profile_summary.get("targets", {})
        profiles_summary[name] = {
            "ok": profile_summary.get("ok"),
            "runs": profile_summary.get("runs"),
            "ok_runs": profile_summary.get("ok_runs"),
            "median_boot_seconds": profile_summary.get("median_boot_seconds"),
            "median_seed_prime_boot_seconds": profile_summary.get(
                "median_seed_prime_boot_seconds"
            ),
            "median_general_circuit_ready_seconds": profile_summary.get(
                "median_general_circuit_ready_seconds"
            ),
            "median_general_circuit_post_boot_wait_seconds": profile_summary.get(
                "median_general_circuit_post_boot_wait_seconds"
            ),
            "median_launch_ready_seconds": profile_summary.get(
                "median_launch_ready_seconds"
            ),
            "targets": {
                url: {
                    "ok": target_summary.get("ok"),
                    "median_elapsed_ms": target_summary.get("median_elapsed_ms"),
                    "median_load_ms": target_summary.get("median_load_ms"),
                    "median_launch_elapsed_ms": target_summary.get(
                        "median_launch_elapsed_ms"
                    ),
                    "median_launch_load_ms": target_summary.get(
                        "median_launch_load_ms"
                    ),
                }
                for url, target_summary in targets_summary.items()
                if isinstance(target_summary, dict)
            },
        }

    cold = profiles.get(COLD_PROFILE, {})
    seeded = profiles.get(SEEDED_PROFILE, {})
    if isinstance(cold, dict) and isinstance(seeded, dict):
        cold_summary = cold.get("summary")
        seeded_summary = seeded.get("summary")
        if isinstance(cold_summary, dict) and isinstance(seeded_summary, dict):
            delta_vs_cold = target_delta_summary(seeded_summary, cold_summary)
            summary["delta_vs_cold"] = delta_vs_cold
            summary["delta_vs_local_cold"] = delta_vs_cold

    bundled = profiles.get(BUNDLED_PROFILE, {})
    bundled_seeded = profiles.get(BUNDLED_SEEDED_PROFILE, {})
    if isinstance(bundled, dict) and isinstance(seeded, dict):
        bundled_summary = bundled.get("summary")
        seeded_summary = seeded.get("summary")
        if isinstance(bundled_summary, dict) and isinstance(seeded_summary, dict):
            summary["delta_vs_bundled"] = target_delta_summary(
                seeded_summary,
                bundled_summary,
            )
    if isinstance(bundled, dict) and isinstance(bundled_seeded, dict):
        bundled_summary = bundled.get("summary")
        bundled_seeded_summary = bundled_seeded.get("summary")
        if isinstance(bundled_summary, dict) and isinstance(bundled_seeded_summary, dict):
            summary["delta_bundled_seeded_vs_bundled"] = target_delta_summary(
                bundled_seeded_summary,
                bundled_summary,
            )
    if isinstance(bundled_seeded, dict) and isinstance(seeded, dict):
        bundled_seeded_summary = bundled_seeded.get("summary")
        seeded_summary = seeded.get("summary")
        if isinstance(bundled_seeded_summary, dict) and isinstance(seeded_summary, dict):
            summary["delta_bundled_seeded_vs_local_seeded"] = target_delta_summary(
                bundled_seeded_summary,
                seeded_summary,
            )
    bundled_seeded_variant_deltas: dict[str, object] = {}
    if isinstance(bundled_seeded, dict):
        bundled_seeded_summary = bundled_seeded.get("summary")
        if isinstance(bundled_seeded_summary, dict):
            for profile_name, profile in profiles.items():
                if (
                    profile_name == BUNDLED_SEEDED_PROFILE
                    or not isinstance(profile, dict)
                    or not profile_name.startswith(f"{BUNDLED_SEEDED_PROFILE}_")
                ):
                    continue
                variant_summary = profile.get("summary")
                if not isinstance(variant_summary, dict):
                    continue
                bundled_seeded_variant_deltas[profile_name] = target_delta_summary(
                    variant_summary,
                    bundled_seeded_summary,
                )
    if bundled_seeded_variant_deltas:
        summary["delta_bundled_seeded_variants_vs_bundled_seeded"] = (
            bundled_seeded_variant_deltas
        )
    seeded_circuit_ready = profiles.get(SEEDED_CIRCUIT_READY_PROFILE, {})
    if isinstance(seeded_circuit_ready, dict) and isinstance(seeded, dict):
        seeded_ready_summary = seeded_circuit_ready.get("summary")
        seeded_summary = seeded.get("summary")
        if isinstance(seeded_ready_summary, dict) and isinstance(seeded_summary, dict):
            summary["delta_seeded_circuit_ready_vs_seeded"] = target_delta_summary(
                seeded_ready_summary,
                seeded_summary,
            )
    seeded_variant_deltas: dict[str, object] = {}
    if isinstance(seeded, dict):
        seeded_summary = seeded.get("summary")
        if isinstance(seeded_summary, dict):
            for profile_name, profile in profiles.items():
                if (
                    profile_name in {SEEDED_PROFILE, SEEDED_CIRCUIT_READY_PROFILE}
                    or not isinstance(profile, dict)
                    or not profile_name.startswith(f"{SEEDED_PROFILE}_")
                ):
                    continue
                variant_summary = profile.get("summary")
                if not isinstance(variant_summary, dict):
                    continue
                seeded_variant_deltas[profile_name] = target_delta_summary(
                    variant_summary,
                    seeded_summary,
                )
    if seeded_variant_deltas:
        summary["delta_seeded_variants_vs_seeded"] = seeded_variant_deltas
    return summary


def payload_ok(payload: dict[str, object]) -> bool:
    quality = payload.get("browser_quality", {})
    if not isinstance(quality, dict):
        return False
    default_prefs = quality.get("default_prefs")
    no_marionette = quality.get("no_marionette_fingerprint")
    if not isinstance(default_prefs, dict) or not default_prefs.get("ok"):
        return False
    if not isinstance(no_marionette, dict) or not no_marionette.get("ok"):
        return False
    profiles = payload.get("profiles", {})
    if not isinstance(profiles, dict):
        return False
    for profile in profiles.values():
        if not isinstance(profile, dict):
            return False
        if profile.get("skipped"):
            continue
        summary = profile.get("summary")
        if not isinstance(summary, dict) or not summary.get("ok"):
            return False
    return True


def median(values: object) -> float:
    return float(statistics.median(values))


if __name__ == "__main__":
    raise SystemExit(main())
