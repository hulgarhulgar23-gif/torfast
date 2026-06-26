#!/usr/bin/env python3
"""Compare repeated cold proxy bootstrap times."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import queue
import re
import statistics
import subprocess
import threading

from run_browser_compare import (
    binary_info,
    cleanup_named_paths,
    parse_dir_bad_health_gate_combos,
    read_torrc_quality,
    start_arti,
    start_c_tor,
    stop_process,
    wait_for_line,
)


@dataclass(frozen=True)
class BootSpec:
    name: str
    kind: str
    bin_path: Path
    port: int
    hs_desc_shared_cache: bool = False
    dir_select_spread: bool = False
    dir_incremental_microdescs: bool = False
    dir_microdesc_early_usable_notify: bool = False
    dir_microdesc_early_retry_on_partial: bool = False
    dir_microdesc_partial_retry_chunking: bool = False
    dir_microdesc_bad_health_replacement_suppress_gap_ms: int | None = None
    dir_microdesc_bad_health_replacement_suppress_min_assigned_streams: int | None = (
        None
    )
    dir_microdesc_bad_health_replacement_suppress_min_active_streams: int | None = (
        None
    )
    dir_microdesc_source_spread: bool = False
    dir_microdesc_pending_spread: bool = False
    dir_microdesc_ids_per_request: int | None = None
    dir_microdesc_retry_ids_per_request: int | None = None
    dir_microdesc_retry_delay_max_ms: int | None = None
    dir_microdesc_parallelism: int | None = None
    dir_microdesc_hedge_ms: int | None = None
    dirclient_read_timeout_ms: int | None = None
    dirclient_progress_read_timeout_ms: int | None = None
    dirclient_microdesc_body_max_ms: int | None = None
    dirclient_microdesc_min_rate_bps: int | None = None
    dirclient_timing_log: bool = False


@dataclass
class RunningBoot:
    spec: BootSpec
    proc: subprocess.Popen[str]
    lines: queue.Queue[str]
    storage_paths: dict[str, Path]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--arti-bin", default="upstream/arti/target/release/arti")
    parser.add_argument("--local-tor-bin", default="upstream/tor/src/app/tor")
    parser.add_argument("--arti-port", type=int, default=19182)
    parser.add_argument("--local-tor-port", type=int, default=19181)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--arti-log-level", default="info")
    parser.add_argument("--arti-dir-select-spread", action="store_true")
    parser.add_argument("--extra-arti-hs-desc-shared-cache", action="store_true")
    parser.add_argument("--extra-arti-dir-select-spread", action="store_true")
    parser.add_argument("--extra-arti-dir-select-spread-port", type=int, default=19183)
    parser.add_argument("--extra-arti-dir-incremental-microdescs", action="store_true")
    parser.add_argument(
        "--extra-arti-dir-incremental-microdescs-port", type=int, default=19184
    )
    parser.add_argument(
        "--extra-arti-dir-microdesc-early-usable-notify", action="store_true"
    )
    parser.add_argument(
        "--extra-arti-dir-microdesc-early-retry-on-partial", action="store_true"
    )
    parser.add_argument(
        "--extra-arti-dir-microdesc-partial-retry-chunking", action="store_true"
    )
    parser.add_argument(
        "--extra-arti-dir-microdesc-source-spread", action="store_true"
    )
    parser.add_argument(
        "--extra-arti-dir-microdesc-source-spread-early-usable",
        action="store_true",
    )
    parser.add_argument(
        "--extra-arti-dir-microdesc-source-spread-pending-spread",
        action="store_true",
    )
    parser.add_argument(
        "--extra-arti-dir-microdesc-source-spread-pending-spread-early-usable",
        action="store_true",
    )
    parser.add_argument(
        "--extra-arti-dir-microdesc-source-spread-pending-spread-early-usable-bad-health-replacement-suppress-gap-ms",
        type=int,
        action="append",
        default=[],
    )
    parser.add_argument(
        "--extra-arti-dir-microdesc-source-spread-pending-spread-early-usable-bad-health-replacement-gate",
        action="append",
        default=[],
        metavar="GAP_MS:MIN_ASSIGNED:MIN_ACTIVE",
    )
    parser.add_argument(
        "--extra-arti-dir-microdesc-source-spread-pending-spread-early-usable-partial-retry-chunking",
        action="store_true",
    )
    parser.add_argument(
        "--extra-arti-dirclient-read-timeout-ms",
        type=int,
        action="append",
        default=[],
    )
    parser.add_argument(
        "--extra-arti-dirclient-progress-read-timeout-ms",
        type=int,
        action="append",
        default=[],
    )
    parser.add_argument(
        "--extra-arti-dirclient-microdesc-body-max-ms",
        type=int,
        action="append",
        default=[],
    )
    parser.add_argument(
        "--extra-arti-dirclient-microdesc-min-rate-bps",
        type=int,
        action="append",
        default=[],
    )
    parser.add_argument(
        "--extra-arti-dir-microdesc-ids-per-request",
        type=int,
        action="append",
        default=[],
    )
    parser.add_argument(
        "--extra-arti-dir-microdesc-retry-ids-per-request",
        type=int,
        action="append",
        default=[],
    )
    parser.add_argument(
        "--extra-arti-dir-microdesc-retry-delay-max-ms",
        type=int,
        action="append",
        default=[],
    )
    parser.add_argument(
        "--extra-arti-dir-microdesc-parallelism",
        type=int,
        action="append",
        default=[],
    )
    parser.add_argument(
        "--extra-arti-dir-microdesc-hedge-ms",
        type=int,
        action="append",
        default=[],
    )
    parser.add_argument("--arti-dirclient-timing-log", action="store_true")
    parser.add_argument("--skip-local-c-tor", action="store_true")
    parser.add_argument("--compact-output", action="store_true")
    args = parser.parse_args()

    if args.runs < 1:
        print("--runs must be at least 1")
        return 2

    arti_bin = Path(args.arti_bin).resolve()
    local_tor_bin = Path(args.local_tor_bin).resolve()
    if not arti_bin.exists():
        print(f"arti binary not found: {arti_bin}")
        return 2
    if not args.skip_local_c_tor and not local_tor_bin.exists():
        print(f"local C Tor binary not found: {local_tor_bin}")
        return 2
    if args.arti_dir_select_spread and args.extra_arti_dir_select_spread:
        print("--extra-arti-dir-select-spread needs the primary Arti profile to stay default")
        return 2
    invalid_read_timeouts = [
        value
        for value in args.extra_arti_dirclient_read_timeout_ms
        if not 2_000 <= value <= 10_000
    ]
    if invalid_read_timeouts:
        print("--extra-arti-dirclient-read-timeout-ms must be between 2000 and 10000")
        return 2
    invalid_progress_read_timeouts = [
        value
        for value in args.extra_arti_dirclient_progress_read_timeout_ms
        if not 2_000 <= value <= 10_000
    ]
    if invalid_progress_read_timeouts:
        print(
            "--extra-arti-dirclient-progress-read-timeout-ms must be between 2000 and 10000"
        )
        return 2
    invalid_microdesc_body_maxes = [
        value
        for value in args.extra_arti_dirclient_microdesc_body_max_ms
        if not 2_000 <= value <= 10_000
    ]
    if invalid_microdesc_body_maxes:
        print(
            "--extra-arti-dirclient-microdesc-body-max-ms must be between 2000 and 10000"
        )
        return 2
    invalid_microdesc_min_rates = [
        value
        for value in args.extra_arti_dirclient_microdesc_min_rate_bps
        if not 32 * 1024 <= value <= 256 * 1024
    ]
    if invalid_microdesc_min_rates:
        print(
            "--extra-arti-dirclient-microdesc-min-rate-bps must be between 32768 and 262144"
        )
        return 2
    invalid_microdesc_chunks = [
        value
        for value in args.extra_arti_dir_microdesc_ids_per_request
        if not 64 <= value <= 500
    ]
    if invalid_microdesc_chunks:
        print("--extra-arti-dir-microdesc-ids-per-request must be between 64 and 500")
        return 2
    invalid_microdesc_retry_chunks = [
        value
        for value in args.extra_arti_dir_microdesc_retry_ids_per_request
        if not 64 <= value <= 500
    ]
    if invalid_microdesc_retry_chunks:
        print(
            "--extra-arti-dir-microdesc-retry-ids-per-request must be between 64 and 500"
        )
        return 2
    invalid_microdesc_retry_delays = [
        value
        for value in args.extra_arti_dir_microdesc_retry_delay_max_ms
        if not 250 <= value <= 2_000
    ]
    if invalid_microdesc_retry_delays:
        print(
            "--extra-arti-dir-microdesc-retry-delay-max-ms must be between 250 and 2000"
        )
        return 2
    invalid_microdesc_parallelism = [
        value
        for value in args.extra_arti_dir_microdesc_parallelism
        if not 1 <= value <= 12
    ]
    if invalid_microdesc_parallelism:
        print("--extra-arti-dir-microdesc-parallelism must be between 1 and 12")
        return 2
    invalid_microdesc_bad_health_gap_suppression = [
        value
        for value in args.extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_bad_health_replacement_suppress_gap_ms
        if not 1_000 <= value <= 60_000
    ]
    if invalid_microdesc_bad_health_gap_suppression:
        print(
            "--extra-arti-dir-microdesc-source-spread-pending-spread-early-usable-bad-health-replacement-suppress-gap-ms must be between 1000 and 60000"
        )
        return 2
    try:
        extra_dir_bad_health_gate_combos = parse_dir_bad_health_gate_combos(
            args.extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_bad_health_replacement_gate,
            option=(
                "--extra-arti-dir-microdesc-source-spread-pending-spread-"
                "early-usable-bad-health-replacement-gate"
            ),
        )
    except ValueError as exc:
        print(str(exc))
        return 2
    invalid_microdesc_hedges = [
        value
        for value in args.extra_arti_dir_microdesc_hedge_ms
        if not 2_000 <= value <= 10_000
    ]
    if invalid_microdesc_hedges:
        print("--extra-arti-dir-microdesc-hedge-ms must be between 2000 and 10000")
        return 2

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    output_dir = Path("results") / f"boot-compare-{run_id}"
    output_dir.mkdir(parents=True, exist_ok=True)

    specs = [
        BootSpec(
            "arti_release_boot",
            "arti",
            arti_bin,
            args.arti_port,
            dir_select_spread=args.arti_dir_select_spread,
            dirclient_timing_log=args.arti_dirclient_timing_log,
        ),
    ]
    if args.extra_arti_hs_desc_shared_cache:
        specs.append(
            BootSpec(
                "arti_release_boot_hsdescshare",
                "arti",
                arti_bin,
                next_free_port(
                    [spec.port for spec in specs] + [args.local_tor_port],
                    start=args.extra_arti_dir_select_spread_port,
                ),
                hs_desc_shared_cache=True,
                dirclient_timing_log=args.arti_dirclient_timing_log,
            )
        )
    
    if args.extra_arti_dir_select_spread:
        specs.append(
            BootSpec(
                "arti_release_boot_dirspread",
                "arti",
                arti_bin,
                args.extra_arti_dir_select_spread_port,
                dir_select_spread=True,
                dirclient_timing_log=args.arti_dirclient_timing_log,
            )
        )
    for hedge_ms in args.extra_arti_dir_microdesc_hedge_ms:
        specs.append(
            BootSpec(
                f"arti_release_boot_mdhedge{hedge_ms}ms",
                "arti",
                arti_bin,
                next_free_port(
                    [spec.port for spec in specs] + [args.local_tor_port],
                    start=args.extra_arti_dir_incremental_microdescs_port + 1,
                ),
                dir_microdesc_hedge_ms=hedge_ms,
                dirclient_timing_log=args.arti_dirclient_timing_log,
            )
        )
    for parallelism in args.extra_arti_dir_microdesc_parallelism:
        specs.append(
            BootSpec(
                f"arti_release_boot_mdpar{parallelism}",
                "arti",
                arti_bin,
                next_free_port(
                    [spec.port for spec in specs] + [args.local_tor_port],
                    start=args.extra_arti_dir_incremental_microdescs_port + 1,
                ),
                dir_microdesc_parallelism=parallelism,
                dirclient_timing_log=args.arti_dirclient_timing_log,
            )
        )
    if args.extra_arti_dir_incremental_microdescs:
        specs.append(
            BootSpec(
                "arti_release_boot_incrmd",
                "arti",
                arti_bin,
                args.extra_arti_dir_incremental_microdescs_port,
                dir_incremental_microdescs=True,
                dirclient_timing_log=args.arti_dirclient_timing_log,
            )
        )
    if args.extra_arti_dir_microdesc_early_usable_notify:
        specs.append(
            BootSpec(
                "arti_release_boot_mdearlyusable",
                "arti",
                arti_bin,
                next_free_port(
                    [spec.port for spec in specs] + [args.local_tor_port],
                    start=args.extra_arti_dir_incremental_microdescs_port + 1,
                ),
                dir_microdesc_early_usable_notify=True,
                dirclient_timing_log=args.arti_dirclient_timing_log,
            )
        )
    if args.extra_arti_dir_microdesc_early_retry_on_partial:
        specs.append(
            BootSpec(
                "arti_release_boot_mdearlyretrypartial",
                "arti",
                arti_bin,
                next_free_port(
                    [spec.port for spec in specs] + [args.local_tor_port],
                    start=args.extra_arti_dir_incremental_microdescs_port + 1,
                ),
                dir_microdesc_early_retry_on_partial=True,
                dirclient_timing_log=args.arti_dirclient_timing_log,
            )
        )
    if args.extra_arti_dir_microdesc_partial_retry_chunking:
        specs.append(
            BootSpec(
                "arti_release_boot_mdpartialretrychunking",
                "arti",
                arti_bin,
                next_free_port(
                    [spec.port for spec in specs] + [args.local_tor_port],
                    start=args.extra_arti_dir_incremental_microdescs_port + 1,
                ),
                dir_microdesc_partial_retry_chunking=True,
                dirclient_timing_log=args.arti_dirclient_timing_log,
            )
        )
    if args.extra_arti_dir_microdesc_source_spread:
        specs.append(
            BootSpec(
                "arti_release_boot_mdsrcspread",
                "arti",
                arti_bin,
                next_free_port(
                    [spec.port for spec in specs] + [args.local_tor_port],
                    start=args.extra_arti_dir_incremental_microdescs_port + 1,
                ),
                dir_microdesc_source_spread=True,
                dirclient_timing_log=args.arti_dirclient_timing_log,
            )
        )
    if (
        args.extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_partial_retry_chunking
    ):
        specs.append(
            BootSpec(
                "arti_release_boot_mdsrcspreadpendingearlyusablepartialretrychunking",
                "arti",
                arti_bin,
                next_free_port(
                    [spec.port for spec in specs] + [args.local_tor_port],
                    start=args.extra_arti_dir_incremental_microdescs_port + 1,
                ),
                dir_microdesc_early_usable_notify=True,
                dir_microdesc_partial_retry_chunking=True,
                dir_microdesc_source_spread=True,
                dir_microdesc_pending_spread=True,
                dir_microdesc_retry_ids_per_request=250,
                dir_microdesc_retry_delay_max_ms=500,
                dirclient_timing_log=args.arti_dirclient_timing_log,
            )
        )
    if args.extra_arti_dir_microdesc_source_spread_early_usable:
        specs.append(
            BootSpec(
                "arti_release_boot_mdsrcspreadearlyusable",
                "arti",
                arti_bin,
                next_free_port(
                    [spec.port for spec in specs] + [args.local_tor_port],
                    start=args.extra_arti_dir_incremental_microdescs_port + 1,
                ),
                dir_microdesc_early_usable_notify=True,
                dir_microdesc_source_spread=True,
                dirclient_timing_log=args.arti_dirclient_timing_log,
            )
        )
    if args.extra_arti_dir_microdesc_source_spread_pending_spread:
        specs.append(
            BootSpec(
                "arti_release_boot_mdsrcspreadpending",
                "arti",
                arti_bin,
                next_free_port(
                    [spec.port for spec in specs] + [args.local_tor_port],
                    start=args.extra_arti_dir_incremental_microdescs_port + 1,
                ),
                dir_microdesc_source_spread=True,
                dir_microdesc_pending_spread=True,
                dirclient_timing_log=args.arti_dirclient_timing_log,
            )
        )
    if args.extra_arti_dir_microdesc_source_spread_pending_spread_early_usable:
        specs.append(
            BootSpec(
                "arti_release_boot_mdsrcspreadpendingearlyusable",
                "arti",
                arti_bin,
                next_free_port(
                    [spec.port for spec in specs] + [args.local_tor_port],
                    start=args.extra_arti_dir_incremental_microdescs_port + 1,
                ),
                dir_microdesc_early_usable_notify=True,
                dir_microdesc_source_spread=True,
                dir_microdesc_pending_spread=True,
                dirclient_timing_log=args.arti_dirclient_timing_log,
            )
        )
    for gap_ms in (
        args.extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_bad_health_replacement_suppress_gap_ms
    ):
        specs.append(
            BootSpec(
                f"arti_release_boot_mdsrcspreadpendingearlyusable_badhealthgap{gap_ms}ms",
                "arti",
                arti_bin,
                next_free_port(
                    [spec.port for spec in specs] + [args.local_tor_port],
                    start=args.extra_arti_dir_incremental_microdescs_port + 1,
                ),
                dir_microdesc_early_usable_notify=True,
                dir_microdesc_bad_health_replacement_suppress_gap_ms=gap_ms,
                dir_microdesc_source_spread=True,
                dir_microdesc_pending_spread=True,
                dirclient_timing_log=args.arti_dirclient_timing_log,
            )
        )
    for gap_ms, min_assigned_streams, min_active_streams in (
        extra_dir_bad_health_gate_combos
    ):
        specs.append(
            BootSpec(
                "arti_release_boot_"
                f"mdsrcspreadpendingearlyusable_badhealthgate{gap_ms}ms_"
                f"assigned{min_assigned_streams}_active{min_active_streams}",
                "arti",
                arti_bin,
                next_free_port(
                    [spec.port for spec in specs] + [args.local_tor_port],
                    start=args.extra_arti_dir_incremental_microdescs_port + 1,
                ),
                dir_microdesc_early_usable_notify=True,
                dir_microdesc_bad_health_replacement_suppress_gap_ms=gap_ms,
                dir_microdesc_bad_health_replacement_suppress_min_assigned_streams=(
                    min_assigned_streams
                ),
                dir_microdesc_bad_health_replacement_suppress_min_active_streams=(
                    min_active_streams
                ),
                dir_microdesc_source_spread=True,
                dir_microdesc_pending_spread=True,
                dirclient_timing_log=args.arti_dirclient_timing_log,
            )
        )
    for timeout_ms in args.extra_arti_dirclient_read_timeout_ms:
        specs.append(
            BootSpec(
                f"arti_release_boot_dirread{timeout_ms}ms",
                "arti",
                arti_bin,
                next_free_port(
                    [
                        spec.port
                        for spec in specs
                    ]
                    + [args.local_tor_port],
                    start=args.extra_arti_dir_incremental_microdescs_port + 1,
                ),
                dirclient_read_timeout_ms=timeout_ms,
                dirclient_timing_log=args.arti_dirclient_timing_log,
            )
        )
    for timeout_ms in args.extra_arti_dirclient_progress_read_timeout_ms:
        specs.append(
            BootSpec(
                f"arti_release_boot_dirprogress{timeout_ms}ms",
                "arti",
                arti_bin,
                next_free_port(
                    [spec.port for spec in specs] + [args.local_tor_port],
                    start=args.extra_arti_dir_incremental_microdescs_port + 1,
                ),
                dirclient_progress_read_timeout_ms=timeout_ms,
                dirclient_timing_log=args.arti_dirclient_timing_log,
            )
        )
    for timeout_ms in args.extra_arti_dirclient_microdesc_body_max_ms:
        specs.append(
            BootSpec(
                f"arti_release_boot_mdbodymax{timeout_ms}ms",
                "arti",
                arti_bin,
                next_free_port(
                    [spec.port for spec in specs] + [args.local_tor_port],
                    start=args.extra_arti_dir_incremental_microdescs_port + 1,
                ),
                dirclient_microdesc_body_max_ms=timeout_ms,
                dirclient_timing_log=args.arti_dirclient_timing_log,
            )
        )
    for min_rate_bps in args.extra_arti_dirclient_microdesc_min_rate_bps:
        specs.append(
            BootSpec(
                f"arti_release_boot_mdminrate{min_rate_bps}bps",
                "arti",
                arti_bin,
                next_free_port(
                    [spec.port for spec in specs] + [args.local_tor_port],
                    start=args.extra_arti_dir_incremental_microdescs_port + 1,
                ),
                dirclient_microdesc_min_rate_bps=min_rate_bps,
                dirclient_timing_log=args.arti_dirclient_timing_log,
            )
        )
    for ids_per_request in args.extra_arti_dir_microdesc_ids_per_request:
        specs.append(
            BootSpec(
                f"arti_release_boot_mdchunk{ids_per_request}",
                "arti",
                arti_bin,
                next_free_port(
                    [spec.port for spec in specs] + [args.local_tor_port],
                    start=args.extra_arti_dir_incremental_microdescs_port + 1,
                ),
                dir_microdesc_ids_per_request=ids_per_request,
                dirclient_timing_log=args.arti_dirclient_timing_log,
            )
        )
    for ids_per_request in args.extra_arti_dir_microdesc_retry_ids_per_request:
        specs.append(
            BootSpec(
                f"arti_release_boot_mdretrychunk{ids_per_request}",
                "arti",
                arti_bin,
                next_free_port(
                    [spec.port for spec in specs] + [args.local_tor_port],
                    start=args.extra_arti_dir_incremental_microdescs_port + 1,
                ),
                dir_microdesc_retry_ids_per_request=ids_per_request,
                dirclient_timing_log=args.arti_dirclient_timing_log,
            )
        )
    for retry_delay_ms in args.extra_arti_dir_microdesc_retry_delay_max_ms:
        specs.append(
            BootSpec(
                f"arti_release_boot_mdretrydelay{retry_delay_ms}ms",
                "arti",
                arti_bin,
                next_free_port(
                    [spec.port for spec in specs] + [args.local_tor_port],
                    start=args.extra_arti_dir_incremental_microdescs_port + 1,
                ),
                dir_microdesc_retry_delay_max_ms=retry_delay_ms,
                dirclient_timing_log=args.arti_dirclient_timing_log,
            )
        )
    if not args.skip_local_c_tor:
        specs.append(
            BootSpec("local_c_tor_boot", "c_tor", local_tor_bin, args.local_tor_port)
        )

    payload: dict[str, object] = {
        "run_id": run_id,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "runs": args.runs,
        "timeout_seconds": args.timeout,
        "arti_dir_select_spread": args.arti_dir_select_spread,
        "profiles": {
            spec.name: {
                "kind": spec.kind,
                "port": spec.port,
                "arti_hs_desc_shared_cache": spec.hs_desc_shared_cache,
                "arti_dir_select_spread": spec.dir_select_spread,
                "arti_dir_incremental_microdescs": spec.dir_incremental_microdescs,
                "arti_dir_microdesc_early_usable_notify": (
                    spec.dir_microdesc_early_usable_notify
                ),
                "arti_dir_microdesc_early_retry_on_partial": (
                    spec.dir_microdesc_early_retry_on_partial
                ),
                "arti_dir_microdesc_partial_retry_chunking": (
                    spec.dir_microdesc_partial_retry_chunking
                ),
                "arti_dir_microdesc_bad_health_replacement_suppress_gap_ms": (
                    spec.dir_microdesc_bad_health_replacement_suppress_gap_ms
                ),
                "arti_dir_microdesc_bad_health_replacement_suppress_min_assigned_streams": (
                    spec.dir_microdesc_bad_health_replacement_suppress_min_assigned_streams
                ),
                "arti_dir_microdesc_bad_health_replacement_suppress_min_active_streams": (
                    spec.dir_microdesc_bad_health_replacement_suppress_min_active_streams
                ),
                "arti_dir_microdesc_source_spread": (
                    spec.dir_microdesc_source_spread
                ),
                "arti_dir_microdesc_pending_spread": (
                    spec.dir_microdesc_pending_spread
                ),
                "arti_dir_microdesc_ids_per_request": (
                    spec.dir_microdesc_ids_per_request
                ),
                "arti_dir_microdesc_retry_ids_per_request": (
                    spec.dir_microdesc_retry_ids_per_request
                ),
                "arti_dir_microdesc_retry_delay_max_ms": (
                    spec.dir_microdesc_retry_delay_max_ms
                ),
                "arti_dir_microdesc_parallelism": spec.dir_microdesc_parallelism,
                "arti_dir_microdesc_hedge_ms": spec.dir_microdesc_hedge_ms,
                "arti_dirclient_read_timeout_ms": spec.dirclient_read_timeout_ms,
                "arti_dirclient_progress_read_timeout_ms": (
                    spec.dirclient_progress_read_timeout_ms
                ),
                "arti_dirclient_microdesc_body_max_ms": (
                    spec.dirclient_microdesc_body_max_ms
                ),
                "arti_dirclient_microdesc_min_rate_bps": (
                    spec.dirclient_microdesc_min_rate_bps
                ),
                "arti_dirclient_timing_log": spec.dirclient_timing_log,
                "binary": binary_info(spec.bin_path),
                "boot_runs": [],
            }
            for spec in specs
        },
    }

    for run_index in range(1, args.runs + 1):
        run_dir = output_dir / f"run-{run_index:02d}"
        run_dir.mkdir(parents=True, exist_ok=True)
        results = run_once(
            specs=specs,
            run_dir=run_dir,
            run_index=run_index,
            timeout=args.timeout,
            arti_log_level=args.arti_log_level,
            compact_output=args.compact_output,
        )
        profiles = payload["profiles"]
        assert isinstance(profiles, dict)
        for spec in specs:
            profile = profiles[spec.name]
            assert isinstance(profile, dict)
            boot_runs = profile["boot_runs"]
            assert isinstance(boot_runs, list)
            boot_runs.append(results[spec.name])

    profiles = payload["profiles"]
    assert isinstance(profiles, dict)
    for profile in profiles.values():
        assert isinstance(profile, dict)
        boot_runs = profile.get("boot_runs", [])
        assert isinstance(boot_runs, list)
        profile["summary"] = summarize_boot_runs(boot_runs)

    payload["comparison"] = compare_profiles(profiles)

    result_path = output_dir / "boot-compare.json"
    result_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"wrote {result_path}")
    print(json.dumps(compact_stdout_summary(payload), indent=2, sort_keys=True))
    return 0 if all_profiles_booted(payload) else 1


def run_once(
    *,
    specs: list[BootSpec],
    run_dir: Path,
    run_index: int,
    timeout: float,
    arti_log_level: str,
    compact_output: bool,
) -> dict[str, dict[str, object]]:
    running: list[RunningBoot] = []
    results: dict[str, dict[str, object]] = {}
    try:
        for spec in specs:
            profile_dir = run_dir / spec.name
            profile_dir.mkdir(parents=True, exist_ok=True)
            proc, lines, storage_paths = start_boot_proxy(
                spec=spec,
                profile_dir=profile_dir,
                arti_log_level=arti_log_level,
            )
            running.append(
                RunningBoot(
                    spec=spec,
                    proc=proc,
                    lines=lines,
                    storage_paths=storage_paths,
                )
            )

        boot_results = wait_for_boots(running, timeout)
        for proxy in running:
            result = {
                "run_index": run_index,
                "boot": boot_results.get(
                    proxy.spec.name,
                    {"ok": False, "error": "boot wait did not complete"},
                ),
            }
            result["signals"] = boot_signal_counts(result["boot"])
            result["timeline"] = boot_timeline(result["boot"])
            if proxy.spec.kind == "c_tor":
                result["torrc"] = read_torrc_quality(
                    run_dir / proxy.spec.name / "torrc"
                )
            results[proxy.spec.name] = result
    finally:
        for proxy in running:
            stop_process(proxy.proc)
        if compact_output:
            for proxy in running:
                existing_paths = {
                    name: path
                    for name, path in proxy.storage_paths.items()
                    if path.exists()
                }
                if existing_paths:
                    results.setdefault(
                        proxy.spec.name,
                        {"run_index": run_index, "boot": {"ok": False}},
                    )
                    results[proxy.spec.name]["proxy_artifacts"] = cleanup_named_paths(
                        existing_paths
                    )
    return results


def start_boot_proxy(
    *,
    spec: BootSpec,
    profile_dir: Path,
    arti_log_level: str,
) -> tuple[subprocess.Popen[str], queue.Queue[str], dict[str, Path]]:
    if spec.kind == "arti":
        cache_dir = profile_dir / "cache"
        state_dir = profile_dir / "state"
        proc, lines = start_arti(
            arti_bin=spec.bin_path,
            port=spec.port,
            cache_dir=cache_dir,
            state_dir=state_dir,
            log_level=arti_log_level,
            hs_desc_shared_cache=spec.hs_desc_shared_cache,
            dir_select_spread=spec.dir_select_spread,
            dir_incremental_microdescs=spec.dir_incremental_microdescs,
            dir_microdesc_early_usable_notify=(
                spec.dir_microdesc_early_usable_notify
            ),
            dir_microdesc_early_retry_on_partial=(
                spec.dir_microdesc_early_retry_on_partial
            ),
            dir_microdesc_partial_retry_chunking=(
                spec.dir_microdesc_partial_retry_chunking
            ),
            dir_microdesc_bad_health_replacement_suppress_gap_ms=(
                spec.dir_microdesc_bad_health_replacement_suppress_gap_ms
            ),
            dir_microdesc_bad_health_replacement_suppress_min_assigned_streams=(
                spec.dir_microdesc_bad_health_replacement_suppress_min_assigned_streams
            ),
            dir_microdesc_bad_health_replacement_suppress_min_active_streams=(
                spec.dir_microdesc_bad_health_replacement_suppress_min_active_streams
            ),
            dir_microdesc_source_spread=spec.dir_microdesc_source_spread,
            dir_microdesc_pending_spread=spec.dir_microdesc_pending_spread,
            dir_microdesc_ids_per_request=spec.dir_microdesc_ids_per_request,
            dir_microdesc_retry_ids_per_request=(
                spec.dir_microdesc_retry_ids_per_request
            ),
            dir_microdesc_retry_delay_max_ms=spec.dir_microdesc_retry_delay_max_ms,
            dir_microdesc_parallelism=spec.dir_microdesc_parallelism,
            dir_microdesc_hedge_ms=spec.dir_microdesc_hedge_ms,
            dirclient_read_timeout_ms=spec.dirclient_read_timeout_ms,
            dirclient_progress_read_timeout_ms=(
                spec.dirclient_progress_read_timeout_ms
            ),
            dirclient_microdesc_body_max_ms=spec.dirclient_microdesc_body_max_ms,
            dirclient_microdesc_min_rate_bps=(
                spec.dirclient_microdesc_min_rate_bps
            ),
            dirclient_timing_log=spec.dirclient_timing_log,
        )
        return proc, lines, {"cache_dir": cache_dir, "state_dir": state_dir}
    if spec.kind == "c_tor":
        data_dir = profile_dir / "data"
        torrc = profile_dir / "torrc"
        proc, lines = start_c_tor(
            tor_bin=spec.bin_path,
            port=spec.port,
            data_dir=data_dir,
            torrc=torrc,
        )
        return proc, lines, {"data_dir": data_dir}
    raise ValueError(f"unknown proxy kind: {spec.kind}")


def wait_for_boots(
    running: list[RunningBoot], timeout: float
) -> dict[str, dict[str, object]]:
    results: dict[str, dict[str, object]] = {}
    lock = threading.Lock()

    def wait_one(proxy: RunningBoot) -> None:
        boot = wait_for_line(
            proxy.proc,
            proxy.lines,
            timeout=timeout,
            ready_text=ready_text(proxy.spec.kind),
            process_name=proxy.spec.kind,
        )
        with lock:
            results[proxy.spec.name] = boot

    threads = [
        threading.Thread(target=wait_one, args=(proxy,), daemon=True)
        for proxy in running
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return results


def ready_text(kind: str) -> str:
    if kind == "c_tor":
        return "Bootstrapped 100%"
    return "proxy now functional"


def boot_signal_counts(boot: object) -> dict[str, object]:
    lines = []
    if isinstance(boot, dict):
        raw_lines = boot.get("lines", [])
        if isinstance(raw_lines, list):
            lines = [str(line) for line in raw_lines]
    counts = {
        "directory_failures": 0,
        "directory_timeouts": 0,
        "notdirectory": 0,
        "partial_response": 0,
        "partial_retry_chunking_signals": 0,
        "terminal_summaries": 0,
        "warnings": 0,
        "has_directory_signal": False,
        "last_signal": "",
    }
    last_signal = ""
    for line in lines:
        lower = line.lower()
        failure_signal = False
        if "directory failure" in lower:
            counts["directory_failures"] += 1
            failure_signal = True
        if "directory timed out" in lower:
            counts["directory_timeouts"] += 1
            failure_signal = True
        if "notdirectory" in lower:
            counts["notdirectory"] += 1
            failure_signal = True
        if "partial response" in lower:
            counts["partial_response"] += 1
            failure_signal = True
        if "partial retry chunking signal" in lower:
            counts["partial_retry_chunking_signals"] += 1
        if "terminal summary" in lower:
            counts["terminal_summaries"] += 1
        if "warn" in lower:
            counts["warnings"] += 1
        if failure_signal:
            last_signal = line
    has_directory_signal = bool(
        (isinstance(boot, dict) and boot.get("ok") is not True)
        or counts["directory_failures"]
        or counts["directory_timeouts"]
        or counts["notdirectory"]
        or counts["partial_response"]
    )
    counts["has_directory_signal"] = has_directory_signal
    counts["last_signal"] = last_signal if has_directory_signal else ""
    return counts


def boot_timeline(boot: object) -> dict[str, object]:
    lines: list[str] = []
    if isinstance(boot, dict):
        raw_lines = boot.get("signal_lines")
        if not isinstance(raw_lines, list):
            raw_lines = boot.get("lines", [])
        if isinstance(raw_lines, list):
            lines = [str(line) for line in raw_lines]

    parsed = [(parse_iso_line_timestamp(line), line) for line in lines]
    timestamps = [stamp for stamp, _line in parsed if stamp is not None]
    if not timestamps:
        return {}
    start = timestamps[0]

    timeline: dict[str, object] = {
        "line_span_seconds": round((timestamps[-1] - start).total_seconds(), 3),
        "consensus_attempts": 0,
        "partial_retry_chunking_signals": 0,
        "terminal_summaries": 0,
        "terminal_summary_total_relay_bytes": 0,
        "terminal_summary_max_transfer_ms": None,
        "terminal_summary_max_data_gap_ms": None,
        "terminal_summary_max_queued_after_bytes": None,
        "terminal_summary_not_connected": 0,
        "dirclient_timing_rows": 0,
        "dirclient_timing_error_rows": 0,
        "dirclient_timing_timeout_rows": 0,
        "dirclient_timing_max_elapsed_ms": None,
        "dirclient_timing_max_body_bytes": None,
        "dirclient_timing_max_elapsed_kind": "",
        "dirclient_timing_max_body_read_calls": None,
        "dirclient_timing_max_body_first_byte_ms": None,
        "dirclient_timing_max_body_last_byte_ms": None,
        "dirclient_timing_max_body_read_gap_ms": None,
        "dirclient_timing_max_body_timeout_after_last_byte_ms": None,
        "dirclient_timing_body_eof_rows": 0,
        "dirclient_timing_max_source_circ": "",
        "dirclient_timing_max_source_circ_rows": 0,
        "dirclient_timing_max_timeout_source_circ": "",
        "dirclient_timing_max_source_circ_timeout_rows": 0,
        "dirclient_timing_max_partial_source_circ": "",
        "dirclient_timing_max_source_circ_partial_rows": 0,
        "channel_open_timing_rows": 0,
        "channel_open_timing_errors": 0,
        "channel_open_dir_rows": 0,
        "channel_open_newly_created_rows": 0,
        "channel_open_preexisting_rows": 0,
        "channel_open_max_elapsed_ms": None,
        "channel_open_max_elapsed_usage_kind": "",
        "channel_open_max_elapsed_outcome": "",
        "circuit_build_failures": 0,
        "circuit_build_channel_failures": 0,
        "circuit_build_dir_failures": 0,
        "circuit_build_exit_failures": 0,
        "circuit_build_preemptive_failures": 0,
        "circuit_build_other_usage_failures": 0,
        "max_circuit_build_pending_age_ms": None,
    }

    def set_first(key: str, stamp: datetime | None) -> None:
        if stamp is None or key in timeline:
            return
        timeline[key] = round((stamp - start).total_seconds(), 3)

    max_transfer_ms: int | None = None
    max_data_gap_ms: int | None = None
    max_queued_after_bytes: int | None = None
    max_dirclient_elapsed_ms: int | None = None
    max_dirclient_body_bytes: int | None = None
    max_dirclient_body_read_calls: int | None = None
    max_dirclient_body_first_byte_ms: int | None = None
    max_dirclient_body_last_byte_ms: int | None = None
    max_dirclient_body_read_gap_ms: int | None = None
    max_dirclient_body_timeout_after_last_byte_ms: int | None = None
    max_channel_open_elapsed_ms: int | None = None
    max_circuit_build_pending_age_ms: int | None = None
    total_relay_bytes = 0
    source_circ_rows: dict[str, int] = {}
    source_circ_timeout_rows: dict[str, int] = {}
    source_circ_partial_rows: dict[str, int] = {}
    for stamp, line in parsed:
        lower = line.lower()
        if "looking for a consensus" in lower:
            timeline["consensus_attempts"] = int(timeline["consensus_attempts"]) + 1
            set_first("first_consensus_seconds", stamp)
        if "downloading certificates for consensus" in lower:
            set_first("first_certificates_seconds", stamp)
        if "downloading microdescriptors" in lower:
            set_first("first_microdescriptors_seconds", stamp)
        if "marked consensus usable" in lower:
            set_first("consensus_usable_seconds", stamp)
        if "directory is complete" in lower:
            set_first("directory_complete_seconds", stamp)
        if "we have enough information to build circuits" in lower:
            set_first("enough_dirinfo_seconds", stamp)
        if "proxy now functional" in lower or "bootstrapped 100%" in lower:
            set_first("proxy_functional_seconds", stamp)
        if "directory failure" in lower:
            set_first("first_directory_failure_seconds", stamp)
        if "directory timed out" in lower:
            set_first("first_directory_timeout_seconds", stamp)
        if "partial retry chunking signal" in lower:
            timeline["partial_retry_chunking_signals"] = (
                int(timeline["partial_retry_chunking_signals"]) + 1
            )
            set_first("first_partial_retry_chunking_signal_seconds", stamp)
        if "torfast channel open timing" in lower:
            timeline["channel_open_timing_rows"] = (
                int(timeline["channel_open_timing_rows"]) + 1
            )
            set_first("first_channel_open_seconds", stamp)
            outcome = extract_text_field(line, "outcome")
            if outcome not in (None, "ok"):
                timeline["channel_open_timing_errors"] = (
                    int(timeline["channel_open_timing_errors"]) + 1
                )
            usage_kind = extract_text_field(line, "usage_kind")
            if usage_kind == "dir":
                timeline["channel_open_dir_rows"] = (
                    int(timeline["channel_open_dir_rows"]) + 1
                )
            provenance = extract_text_field(line, "provenance")
            if provenance == "newly_created":
                timeline["channel_open_newly_created_rows"] = (
                    int(timeline["channel_open_newly_created_rows"]) + 1
                )
            elif provenance == "preexisting":
                timeline["channel_open_preexisting_rows"] = (
                    int(timeline["channel_open_preexisting_rows"]) + 1
                )
            elapsed_ms = extract_int_field(line, "elapsed_ms")
            if elapsed_ms is not None and (
                max_channel_open_elapsed_ms is None
                or elapsed_ms > max_channel_open_elapsed_ms
            ):
                max_channel_open_elapsed_ms = elapsed_ms
                timeline["channel_open_max_elapsed_usage_kind"] = usage_kind or ""
                timeline["channel_open_max_elapsed_outcome"] = outcome or ""
        if "torfast circuit selection build failed" in lower:
            timeline["circuit_build_failures"] = (
                int(timeline["circuit_build_failures"]) + 1
            )
            set_first("first_circuit_build_failure_seconds", stamp)
            if "problem opening a channel" in lower:
                timeline["circuit_build_channel_failures"] = (
                    int(timeline["circuit_build_channel_failures"]) + 1
                )
            usage_kind = extract_text_field(line, "usage_kind")
            if usage_kind == "dir":
                timeline["circuit_build_dir_failures"] = (
                    int(timeline["circuit_build_dir_failures"]) + 1
                )
            elif usage_kind == "exit":
                timeline["circuit_build_exit_failures"] = (
                    int(timeline["circuit_build_exit_failures"]) + 1
                )
            elif usage_kind == "preemptive":
                timeline["circuit_build_preemptive_failures"] = (
                    int(timeline["circuit_build_preemptive_failures"]) + 1
                )
            elif usage_kind is not None:
                timeline["circuit_build_other_usage_failures"] = (
                    int(timeline["circuit_build_other_usage_failures"]) + 1
                )
            pending_age_ms = extract_int_field(line, "pending_age_ms")
            if pending_age_ms is not None:
                max_circuit_build_pending_age_ms = (
                    pending_age_ms
                    if max_circuit_build_pending_age_ms is None
                    else max(max_circuit_build_pending_age_ms, pending_age_ms)
                )
        if "terminal summary" in lower:
            timeline["terminal_summaries"] = int(timeline["terminal_summaries"]) + 1
            transfer_ms = extract_int_field(line, "transfer_ms")
            if transfer_ms is not None:
                max_transfer_ms = (
                    transfer_ms
                    if max_transfer_ms is None
                    else max(max_transfer_ms, transfer_ms)
                )
            data_gap_ms = extract_int_field(line, "max_data_gap_ms")
            if data_gap_ms is not None:
                max_data_gap_ms = (
                    data_gap_ms
                    if max_data_gap_ms is None
                    else max(max_data_gap_ms, data_gap_ms)
                )
            queued_after_bytes = extract_int_field(line, "max_queued_after_bytes")
            if queued_after_bytes is not None:
                max_queued_after_bytes = (
                    queued_after_bytes
                    if max_queued_after_bytes is None
                    else max(max_queued_after_bytes, queued_after_bytes)
                )
            relay_bytes = extract_int_field(line, "relay_data_bytes")
            if relay_bytes is not None:
                total_relay_bytes += relay_bytes
            if "error_kind=not_connected" in lower:
                timeline["terminal_summary_not_connected"] = (
                    int(timeline["terminal_summary_not_connected"]) + 1
                )
        if "torfast dirclient timing" in lower:
            timeline["dirclient_timing_rows"] = (
                int(timeline["dirclient_timing_rows"]) + 1
            )
            outcome = extract_text_field(line, "outcome")
            source_circ = extract_text_field(line, "source_circ")
            if source_circ and source_circ != "none":
                source_circ_rows[source_circ] = source_circ_rows.get(source_circ, 0) + 1
                if outcome == "partial":
                    source_circ_partial_rows[source_circ] = (
                        source_circ_partial_rows.get(source_circ, 0) + 1
                    )
            if outcome not in (None, "ok", "partial", "status"):
                timeline["dirclient_timing_error_rows"] = (
                    int(timeline["dirclient_timing_error_rows"]) + 1
                )
            if "tornetworktimeout" in lower or "dirtimeout" in lower:
                timeline["dirclient_timing_timeout_rows"] = (
                    int(timeline["dirclient_timing_timeout_rows"]) + 1
                )
                if source_circ and source_circ != "none":
                    source_circ_timeout_rows[source_circ] = (
                        source_circ_timeout_rows.get(source_circ, 0) + 1
                    )
            elapsed_ms = extract_int_field(line, "elapsed_ms")
            if elapsed_ms is not None and (
                max_dirclient_elapsed_ms is None or elapsed_ms > max_dirclient_elapsed_ms
            ):
                max_dirclient_elapsed_ms = elapsed_ms
                timeline["dirclient_timing_max_elapsed_kind"] = (
                    extract_text_field(line, "request_kind") or ""
                )
            body_bytes = extract_int_field(line, "body_bytes")
            if body_bytes is not None:
                max_dirclient_body_bytes = (
                    body_bytes
                    if max_dirclient_body_bytes is None
                    else max(max_dirclient_body_bytes, body_bytes)
                )
            body_read_calls = extract_int_field(line, "body_read_calls")
            if body_read_calls is not None:
                max_dirclient_body_read_calls = (
                    body_read_calls
                    if max_dirclient_body_read_calls is None
                    else max(max_dirclient_body_read_calls, body_read_calls)
                )
            body_first_byte_ms = extract_int_field(line, "body_first_byte_ms")
            if body_first_byte_ms is not None:
                max_dirclient_body_first_byte_ms = (
                    body_first_byte_ms
                    if max_dirclient_body_first_byte_ms is None
                    else max(max_dirclient_body_first_byte_ms, body_first_byte_ms)
                )
            body_last_byte_ms = extract_int_field(line, "body_last_byte_ms")
            if body_last_byte_ms is not None:
                max_dirclient_body_last_byte_ms = (
                    body_last_byte_ms
                    if max_dirclient_body_last_byte_ms is None
                    else max(max_dirclient_body_last_byte_ms, body_last_byte_ms)
                )
            body_max_read_gap_ms = extract_int_field(line, "body_max_read_gap_ms")
            if body_max_read_gap_ms is not None:
                max_dirclient_body_read_gap_ms = (
                    body_max_read_gap_ms
                    if max_dirclient_body_read_gap_ms is None
                    else max(max_dirclient_body_read_gap_ms, body_max_read_gap_ms)
                )
            body_timeout_after_last_byte_ms = extract_int_field(
                line, "body_timeout_after_last_byte_ms"
            )
            if body_timeout_after_last_byte_ms is not None:
                max_dirclient_body_timeout_after_last_byte_ms = (
                    body_timeout_after_last_byte_ms
                    if max_dirclient_body_timeout_after_last_byte_ms is None
                    else max(
                        max_dirclient_body_timeout_after_last_byte_ms,
                        body_timeout_after_last_byte_ms,
                    )
                )
            if "body_eof=true" in lower:
                timeline["dirclient_timing_body_eof_rows"] = (
                    int(timeline["dirclient_timing_body_eof_rows"]) + 1
                )

    timeline["terminal_summary_total_relay_bytes"] = total_relay_bytes
    timeline["terminal_summary_max_transfer_ms"] = max_transfer_ms
    timeline["terminal_summary_max_data_gap_ms"] = max_data_gap_ms
    timeline["terminal_summary_max_queued_after_bytes"] = max_queued_after_bytes
    timeline["dirclient_timing_max_elapsed_ms"] = max_dirclient_elapsed_ms
    timeline["dirclient_timing_max_body_bytes"] = max_dirclient_body_bytes
    timeline["dirclient_timing_max_body_read_calls"] = max_dirclient_body_read_calls
    timeline["dirclient_timing_max_body_first_byte_ms"] = max_dirclient_body_first_byte_ms
    timeline["dirclient_timing_max_body_last_byte_ms"] = max_dirclient_body_last_byte_ms
    timeline["dirclient_timing_max_body_read_gap_ms"] = max_dirclient_body_read_gap_ms
    timeline["dirclient_timing_max_body_timeout_after_last_byte_ms"] = (
        max_dirclient_body_timeout_after_last_byte_ms
    )
    top_source_circ = max(
        source_circ_rows.items(), key=lambda item: (item[1], item[0]), default=("", 0)
    )
    timeline["dirclient_timing_max_source_circ"] = top_source_circ[0]
    timeline["dirclient_timing_max_source_circ_rows"] = top_source_circ[1]
    top_timeout_source_circ = max(
        source_circ_timeout_rows.items(),
        key=lambda item: (item[1], item[0]),
        default=("", 0),
    )
    timeline["dirclient_timing_max_timeout_source_circ"] = top_timeout_source_circ[0]
    timeline["dirclient_timing_max_source_circ_timeout_rows"] = (
        top_timeout_source_circ[1]
    )
    top_partial_source_circ = max(
        source_circ_partial_rows.items(),
        key=lambda item: (item[1], item[0]),
        default=("", 0),
    )
    timeline["dirclient_timing_max_partial_source_circ"] = top_partial_source_circ[0]
    timeline["dirclient_timing_max_source_circ_partial_rows"] = (
        top_partial_source_circ[1]
    )
    timeline["channel_open_max_elapsed_ms"] = max_channel_open_elapsed_ms
    timeline["max_circuit_build_pending_age_ms"] = max_circuit_build_pending_age_ms
    return timeline


def parse_iso_line_timestamp(line: str) -> datetime | None:
    match = re.match(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})Z\b", line)
    if not match:
        return None
    return datetime.fromisoformat(match.group(1)).replace(tzinfo=timezone.utc)


def extract_int_field(line: str, name: str) -> int | None:
    match = re.search(rf"\b{re.escape(name)}=(\d+)\b", line)
    if not match:
        return None
    return int(match.group(1))


def extract_text_field(line: str, name: str) -> str | None:
    match = re.search(rf'\b{re.escape(name)}="?([^"\s]+)"?', line)
    if not match:
        return None
    return match.group(1)


def summarize_boot_runs(boot_runs: list[object]) -> dict[str, object]:
    seconds = []
    summary = {
        "runs": len(boot_runs),
        "successes": 0,
        "failures": 0,
        "directory_signal_runs": 0,
        "median_boot_seconds": None,
        "min_boot_seconds": None,
        "max_boot_seconds": None,
        "slowest_run_index": None,
        "slowest_last_signal": "",
        "directory_failures": 0,
        "directory_timeouts": 0,
        "notdirectory": 0,
        "partial_response": 0,
        "partial_retry_chunking_signals": 0,
        "terminal_summaries": 0,
        "warnings": 0,
        "median_consensus_usable_seconds": None,
        "median_microdescriptors_seconds": None,
        "median_enough_dirinfo_seconds": None,
        "median_proxy_functional_seconds": None,
        "max_terminal_summary_transfer_ms": None,
        "max_terminal_summary_data_gap_ms": None,
        "total_terminal_summary_relay_bytes": 0,
        "dirclient_timing_rows": 0,
        "dirclient_timing_error_rows": 0,
        "dirclient_timing_timeout_rows": 0,
        "max_dirclient_timing_elapsed_ms": None,
        "max_dirclient_timing_body_bytes": None,
        "max_dirclient_timing_body_read_calls": None,
        "max_dirclient_timing_body_first_byte_ms": None,
        "max_dirclient_timing_body_last_byte_ms": None,
        "max_dirclient_timing_body_read_gap_ms": None,
        "max_dirclient_timing_body_timeout_after_last_byte_ms": None,
        "dirclient_timing_body_eof_rows": 0,
        "max_dirclient_timing_source_circ_rows": 0,
        "max_dirclient_timing_source_circ_timeout_rows": 0,
        "max_dirclient_timing_source_circ_partial_rows": 0,
        "channel_open_timing_rows": 0,
        "channel_open_timing_errors": 0,
        "channel_open_dir_rows": 0,
        "channel_open_newly_created_rows": 0,
        "channel_open_preexisting_rows": 0,
        "max_channel_open_elapsed_ms": None,
        "circuit_build_failures": 0,
        "circuit_build_channel_failures": 0,
        "circuit_build_dir_failures": 0,
        "circuit_build_exit_failures": 0,
        "circuit_build_preemptive_failures": 0,
        "circuit_build_other_usage_failures": 0,
        "median_first_circuit_build_failure_seconds": None,
        "max_circuit_build_pending_age_ms": None,
    }
    slowest: tuple[float, int, str] | None = None
    timelines: list[dict[str, object]] = []
    for item in boot_runs:
        if not isinstance(item, dict):
            summary["failures"] += 1
            continue
        boot = item.get("boot", {})
        signals = boot_signal_counts(boot)
        timeline = item.get("timeline")
        if not isinstance(timeline, dict):
            timeline = boot_timeline(boot)
        if timeline:
            timelines.append(timeline)
        if isinstance(boot, dict) and boot.get("ok") is True:
            summary["successes"] += 1
            value = boot.get("seconds")
            if isinstance(value, (int, float)):
                seconds.append(float(value))
                candidate = (
                    float(value),
                    int(item.get("run_index", 0)),
                    str(signals.get("last_signal", "")),
                )
                if slowest is None or candidate[0] > slowest[0]:
                    slowest = candidate
        else:
            summary["failures"] += 1
        if signals.get("has_directory_signal"):
            summary["directory_signal_runs"] += 1
        for key in (
            "directory_failures",
            "directory_timeouts",
            "notdirectory",
            "partial_response",
            "partial_retry_chunking_signals",
            "terminal_summaries",
            "warnings",
        ):
            value = signals.get(key)
            if isinstance(value, int):
                summary[key] += value
    if seconds:
        summary["median_boot_seconds"] = round(float(statistics.median(seconds)), 3)
        summary["min_boot_seconds"] = round(min(seconds), 3)
        summary["max_boot_seconds"] = round(max(seconds), 3)
    if slowest is not None:
        summary["slowest_run_index"] = slowest[1]
        summary["slowest_last_signal"] = slowest[2]
    add_timeline_summary(summary, timelines)
    return summary


def add_timeline_summary(
    summary: dict[str, object], timelines: list[dict[str, object]]
) -> None:
    median_keys = {
        "median_consensus_usable_seconds": "consensus_usable_seconds",
        "median_microdescriptors_seconds": "first_microdescriptors_seconds",
        "median_enough_dirinfo_seconds": "enough_dirinfo_seconds",
        "median_proxy_functional_seconds": "proxy_functional_seconds",
        "median_first_partial_retry_chunking_signal_seconds": (
            "first_partial_retry_chunking_signal_seconds"
        ),
    }
    for summary_key, timeline_key in median_keys.items():
        values = [
            float(timeline[timeline_key])
            for timeline in timelines
            if isinstance(timeline.get(timeline_key), (int, float))
        ]
        if values:
            summary[summary_key] = round(float(statistics.median(values)), 3)

    transfer_values = [
        int(timeline["terminal_summary_max_transfer_ms"])
        for timeline in timelines
        if isinstance(timeline.get("terminal_summary_max_transfer_ms"), int)
    ]
    if transfer_values:
        summary["max_terminal_summary_transfer_ms"] = max(transfer_values)

    gap_values = [
        int(timeline["terminal_summary_max_data_gap_ms"])
        for timeline in timelines
        if isinstance(timeline.get("terminal_summary_max_data_gap_ms"), int)
    ]
    if gap_values:
        summary["max_terminal_summary_data_gap_ms"] = max(gap_values)

    summary["total_terminal_summary_relay_bytes"] = sum(
        int(timeline.get("terminal_summary_total_relay_bytes", 0))
        for timeline in timelines
        if isinstance(timeline.get("terminal_summary_total_relay_bytes", 0), int)
    )

    for key in (
        "dirclient_timing_rows",
        "dirclient_timing_error_rows",
        "dirclient_timing_timeout_rows",
        "dirclient_timing_body_eof_rows",
        "channel_open_timing_rows",
        "channel_open_timing_errors",
        "channel_open_dir_rows",
        "channel_open_newly_created_rows",
        "channel_open_preexisting_rows",
        "circuit_build_failures",
        "circuit_build_channel_failures",
        "circuit_build_dir_failures",
        "circuit_build_exit_failures",
        "circuit_build_preemptive_failures",
        "circuit_build_other_usage_failures",
    ):
        summary[key] = sum(
            int(timeline.get(key, 0))
            for timeline in timelines
            if isinstance(timeline.get(key, 0), int)
        )

    elapsed_values = [
        int(timeline["dirclient_timing_max_elapsed_ms"])
        for timeline in timelines
        if isinstance(timeline.get("dirclient_timing_max_elapsed_ms"), int)
    ]
    if elapsed_values:
        summary["max_dirclient_timing_elapsed_ms"] = max(elapsed_values)

    body_values = [
        int(timeline["dirclient_timing_max_body_bytes"])
        for timeline in timelines
        if isinstance(timeline.get("dirclient_timing_max_body_bytes"), int)
    ]
    if body_values:
        summary["max_dirclient_timing_body_bytes"] = max(body_values)

    for summary_key, timeline_key in {
        "max_dirclient_timing_body_read_calls": "dirclient_timing_max_body_read_calls",
        "max_dirclient_timing_body_first_byte_ms": "dirclient_timing_max_body_first_byte_ms",
        "max_dirclient_timing_body_last_byte_ms": "dirclient_timing_max_body_last_byte_ms",
        "max_dirclient_timing_body_read_gap_ms": "dirclient_timing_max_body_read_gap_ms",
        "max_dirclient_timing_body_timeout_after_last_byte_ms": (
            "dirclient_timing_max_body_timeout_after_last_byte_ms"
        ),
        "max_dirclient_timing_source_circ_rows": "dirclient_timing_max_source_circ_rows",
        "max_dirclient_timing_source_circ_timeout_rows": (
            "dirclient_timing_max_source_circ_timeout_rows"
        ),
        "max_dirclient_timing_source_circ_partial_rows": (
            "dirclient_timing_max_source_circ_partial_rows"
        ),
    }.items():
        values = [
            int(timeline[timeline_key])
            for timeline in timelines
            if isinstance(timeline.get(timeline_key), int)
        ]
        if values:
            summary[summary_key] = max(values)

    channel_open_elapsed_values = [
        int(timeline["channel_open_max_elapsed_ms"])
        for timeline in timelines
        if isinstance(timeline.get("channel_open_max_elapsed_ms"), int)
    ]
    if channel_open_elapsed_values:
        summary["max_channel_open_elapsed_ms"] = max(channel_open_elapsed_values)

    first_build_failure_values = [
        float(timeline["first_circuit_build_failure_seconds"])
        for timeline in timelines
        if isinstance(timeline.get("first_circuit_build_failure_seconds"), (int, float))
    ]
    if first_build_failure_values:
        summary["median_first_circuit_build_failure_seconds"] = round(
            float(statistics.median(first_build_failure_values)), 3
        )

    pending_age_values = [
        int(timeline["max_circuit_build_pending_age_ms"])
        for timeline in timelines
        if isinstance(timeline.get("max_circuit_build_pending_age_ms"), int)
    ]
    if pending_age_values:
        summary["max_circuit_build_pending_age_ms"] = max(pending_age_values)


def compare_profiles(profiles: dict[object, object]) -> dict[str, object]:
    comparison: dict[str, object] = {}
    arti = profile_summary(profiles, "arti_release_boot")
    local = profile_summary(profiles, "local_c_tor_boot")
    if arti and local:
        arti_median = arti.get("median_boot_seconds")
        local_median = local.get("median_boot_seconds")
        if isinstance(arti_median, (int, float)) and isinstance(
            local_median, (int, float)
        ):
            delta = round(float(arti_median) - float(local_median), 3)
            comparison["arti_minus_local_median_boot_seconds"] = delta
            comparison["faster_median_boot_profile"] = (
                "arti_release_boot" if delta < 0 else "local_c_tor_boot"
            )
    spread = profile_summary(profiles, "arti_release_boot_dirspread")
    if arti and spread:
        arti_median = arti.get("median_boot_seconds")
        spread_median = spread.get("median_boot_seconds")
        if isinstance(arti_median, (int, float)) and isinstance(
            spread_median, (int, float)
        ):
            delta = round(float(spread_median) - float(arti_median), 3)
            comparison["dirspread_minus_default_median_boot_seconds"] = delta
            comparison["faster_arti_median_boot_profile"] = (
                "arti_release_boot_dirspread" if delta < 0 else "arti_release_boot"
            )
    incrmd = profile_summary(profiles, "arti_release_boot_incrmd")
    if arti and incrmd:
        arti_median = arti.get("median_boot_seconds")
        incrmd_median = incrmd.get("median_boot_seconds")
        if isinstance(arti_median, (int, float)) and isinstance(
            incrmd_median, (int, float)
        ):
            delta = round(float(incrmd_median) - float(arti_median), 3)
            comparison["incrmd_minus_default_median_boot_seconds"] = delta
            comparison["faster_arti_incrmd_median_boot_profile"] = (
                "arti_release_boot_incrmd" if delta < 0 else "arti_release_boot"
            )
    mdearlyusable = profile_summary(profiles, "arti_release_boot_mdearlyusable")
    if arti and mdearlyusable:
        arti_median = arti.get("median_boot_seconds")
        mdearlyusable_median = mdearlyusable.get("median_boot_seconds")
        if isinstance(arti_median, (int, float)) and isinstance(
            mdearlyusable_median, (int, float)
        ):
            delta = round(float(mdearlyusable_median) - float(arti_median), 3)
            comparison[
                "mdearlyusable_minus_default_median_boot_seconds"
            ] = delta
            comparison["faster_arti_mdearlyusable_median_boot_profile"] = (
                "arti_release_boot_mdearlyusable"
                if delta < 0
                else "arti_release_boot"
            )
    if arti:
        arti_median = arti.get("median_boot_seconds")
        for name in sorted(str(key) for key in profiles):
            if not name.startswith(
                (
                    "arti_release_boot_dirread",
                    "arti_release_boot_dirprogress",
                    "arti_release_boot_mdbodymax",
                    "arti_release_boot_mdminrate",
                )
            ):
                continue
            read_timeout = profile_summary(profiles, name)
            if not read_timeout:
                continue
            read_timeout_median = read_timeout.get("median_boot_seconds")
            if isinstance(arti_median, (int, float)) and isinstance(
                read_timeout_median, (int, float)
            ):
                delta = round(float(read_timeout_median) - float(arti_median), 3)
                comparison[f"{name}_minus_default_median_boot_seconds"] = delta
                comparison[f"faster_{name}_median_boot_profile"] = (
                    name if delta < 0 else "arti_release_boot"
                )
        for name in sorted(str(key) for key in profiles):
            if not name.startswith(
                (
                    "arti_release_boot_mdchunk",
                    "arti_release_boot_mdpartialretrychunking",
                    "arti_release_boot_mdretrychunk",
                    "arti_release_boot_mdretrydelay",
                    "arti_release_boot_mdearlyretrypartial",
                    "arti_release_boot_mdsrcspread",
                )
            ):
                continue
            chunk = profile_summary(profiles, name)
            if not chunk:
                continue
            chunk_median = chunk.get("median_boot_seconds")
            if isinstance(arti_median, (int, float)) and isinstance(
                chunk_median, (int, float)
            ):
                delta = round(float(chunk_median) - float(arti_median), 3)
                comparison[f"{name}_minus_default_median_boot_seconds"] = delta
                comparison[f"faster_{name}_median_boot_profile"] = (
                    name if delta < 0 else "arti_release_boot"
                )
        for name in sorted(str(key) for key in profiles):
            if not name.startswith("arti_release_boot_mdpar"):
                continue
            parallelism = profile_summary(profiles, name)
            if not parallelism:
                continue
            parallelism_median = parallelism.get("median_boot_seconds")
            if isinstance(arti_median, (int, float)) and isinstance(
                parallelism_median, (int, float)
            ):
                delta = round(float(parallelism_median) - float(arti_median), 3)
                comparison[f"{name}_minus_default_median_boot_seconds"] = delta
                comparison[f"faster_{name}_median_boot_profile"] = (
                    name if delta < 0 else "arti_release_boot"
                )
        for name in sorted(str(key) for key in profiles):
            if not name.startswith("arti_release_boot_mdhedge"):
                continue
            hedge = profile_summary(profiles, name)
            if not hedge:
                continue
            hedge_median = hedge.get("median_boot_seconds")
            if isinstance(arti_median, (int, float)) and isinstance(
                hedge_median, (int, float)
            ):
                delta = round(float(hedge_median) - float(arti_median), 3)
                comparison[f"{name}_minus_default_median_boot_seconds"] = delta
                comparison[f"faster_{name}_median_boot_profile"] = (
                    name if delta < 0 else "arti_release_boot"
                )
    return comparison


def next_free_port(used_ports: list[int], *, start: int) -> int:
    used = set(used_ports)
    port = start
    while port in used:
        port += 1
    return port


def profile_summary(
    profiles: dict[object, object], profile_name: str
) -> dict[str, object] | None:
    profile = profiles.get(profile_name)
    if not isinstance(profile, dict):
        return None
    summary = profile.get("summary")
    if not isinstance(summary, dict):
        return None
    return summary


def compact_stdout_summary(payload: dict[str, object]) -> dict[str, object]:
    profiles = payload.get("profiles", {})
    if not isinstance(profiles, dict):
        profiles = {}
    return {
        "run_id": payload.get("run_id"),
        "profiles": {
            name: profile.get("summary")
            for name, profile in profiles.items()
            if isinstance(profile, dict)
        },
        "comparison": payload.get("comparison", {}),
    }


def all_profiles_booted(payload: dict[str, object]) -> bool:
    profiles = payload.get("profiles", {})
    if not isinstance(profiles, dict):
        return False
    for profile in profiles.values():
        if not isinstance(profile, dict):
            return False
        summary = profile.get("summary")
        if not isinstance(summary, dict):
            return False
        if summary.get("failures") != 0:
            return False
    return True


if __name__ == "__main__":
    raise SystemExit(main())
