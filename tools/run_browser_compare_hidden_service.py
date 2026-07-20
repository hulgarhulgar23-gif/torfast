#!/usr/bin/env python3
"""Run the current hidden-service browser-compare matrix."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys


DEFAULT_TARGETS = [
    "https://securedrop.org/",
    # Current Tor Project onion download page from Onion-Location proof.
    "http://2gzyxa5ihm7nsggfxnu52rck2vv4rvmdlkiu3zzui5du4xyclen53wid.onion/download/index.html",
]
DEFAULT_HS_DESC_SHARED_CACHE_STREAM_READY_DATA_COALESCE_MIN_HOP_COMBOS = [
    "4096:4"
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=4)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--post-boot-wait", type=float, default=0.0)
    parser.add_argument("--window-size", default="1000,1000")
    parser.add_argument("--arti-log-level")
    parser.add_argument("--compact-output", action="store_true")
    parser.add_argument("--proxy-log-tail-lines", type=int)
    parser.add_argument("--proxy-run-tail-lines", type=int)
    parser.add_argument("--warm-cache", action="store_true")
    parser.add_argument("--share-arti-warm-cache-seed", action="store_true")
    parser.add_argument("--browser-startup-seed", action="store_true")
    parser.add_argument("--browser-net-log", action="store_true")
    parser.add_argument("--byte-tap", action="store_true")
    parser.add_argument("--byte-tap-socks-reply-bind-port-tag", action="store_true")
    parser.add_argument("--arti-socks-relay-byte-timing", action="store_true")
    parser.add_argument("--arti-hspool-launch-parallelism", type=int)
    parser.add_argument("--arti-hspool-background-start-delay-ms", type=int)
    parser.add_argument("--arti-hspool-guarded-stem-target", type=int)
    parser.add_argument(
        "--arti-hspool-guarded-stem-target-defer-post-bootstrap",
        action="store_true",
    )
    parser.add_argument("--arti-hspool-on-demand-grace-ms", type=int)
    parser.add_argument("--arti-hspool-on-demand-race-ms", type=int)
    parser.add_argument("--skip-plain-arti", action="store_true")
    parser.add_argument("--skip-local-c-tor", action="store_true")
    parser.add_argument(
        "--extra-arti-hs-desc-shared-cache-stream-scheduler-burst",
        action="append",
        type=int,
        default=[],
    )
    parser.add_argument(
        "--extra-arti-hs-desc-shared-cache-socks-tor-to-client-coalesce-bytes",
        action="append",
        type=int,
        default=[],
    )
    parser.add_argument(
        "--extra-arti-hs-desc-shared-cache-stream-ready-data-coalesce-bytes",
        action="append",
        type=int,
        default=[],
    )
    parser.add_argument(
        "--extra-arti-hs-desc-shared-cache-reuse-max-active-streams",
        action="append",
        type=int,
        default=[],
    )
    parser.add_argument(
        "--extra-arti-hs-desc-shared-cache-stream-ready-data-coalesce-min-hop-combo",
        action="append",
        default=[],
    )
    parser.add_argument(
        "--extra-arti-hs-desc-shared-cache-stream-ready-data-coalesce-min-hop-start-backlog-combo",
        action="append",
        default=[],
    )
    parser.add_argument(
        "--extra-arti-hs-desc-shared-cache-stream-ready-data-coalesce-min-hop-busy-max-combo",
        action="append",
        default=[],
    )
    parser.add_argument(
        "--extra-arti-hs-desc-shared-cache-rendezvous-establish-timeout-floor-ms",
        action="append",
        type=int,
        default=[],
    )
    parser.add_argument(
        "--extra-arti-hs-desc-shared-cache-stream-ready-data-coalesce-min-hop-rendezvous-establish-timeout-floor-combo",
        action="append",
        default=[],
    )
    parser.add_argument(
        "--extra-arti-hs-rend-prebuild-before-desc-shared-cache",
        action="store_true",
    )
    parser.add_argument(
        "--extra-arti-hs-rend-prebuild-before-desc-shared-cache-shared-hit-only",
        action="store_true",
    )
    parser.add_argument(
        "--extra-arti-hs-rend-prebuild-before-desc-shared-cache-shared-hit-only-stream-ready-data-coalesce-bytes",
        action="append",
        type=int,
        default=[],
    )
    parser.add_argument(
        "--extra-arti-hs-rend-prebuild-before-desc-shared-cache-shared-hit-only-cold-late-ms",
        action="append",
        type=int,
        default=[],
    )
    parser.add_argument(
        "--extra-arti-hs-rend-prebuild-before-desc-shared-cache-shared-hit-only-reuse-max-active-streams",
        action="append",
        type=int,
        default=[],
    )
    parser.add_argument(
        "--extra-arti-hs-rend-prebuild-before-desc-shared-cache-shared-hit-only-reuse-max-active-streams-startup-only-hsdir-extend-timeout-cap-combo",
        action="append",
        default=[],
    )
    parser.add_argument(
        "--extra-arti-hs-rend-prebuild-before-desc-shared-cache-shared-hit-only-reuse-max-active-streams-cold-late-combo",
        action="append",
        default=[],
    )
    parser.add_argument(
        "--extra-arti-hs-intro-rend-overlap",
        action="store_true",
    )
    parser.add_argument(
        "--extra-arti-hs-desc-shared-cache-intro-circuit-hedge-ms",
        action="append",
        type=int,
        default=[],
    )
    parser.add_argument(
        "--extra-arti-hs-desc-shared-cache-hsdir-extend-timeout-cap-ms",
        action="append",
        type=int,
        default=[],
    )
    parser.add_argument(
        "--extra-arti-hs-desc-shared-cache-hsdir-extend-timeout-cap-startup-only-ms",
        action="append",
        type=int,
        default=[],
    )
    parser.add_argument(
        "--extra-arti-hs-desc-shared-cache-hsdir-extend-timeout-cap-post-boot-only-ms",
        action="append",
        type=int,
        default=[],
    )
    parser.add_argument(
        "--extra-arti-hs-desc-shared-cache-hspool-on-demand-race-ms",
        action="append",
        type=int,
        default=[],
    )
    parser.add_argument(
        "--extra-arti-hs-desc-shared-cache-hspool-background-start-on-demand",
        action="store_true",
    )
    parser.add_argument(
        "--extra-arti-hs-desc-shared-cache-hspool-race-background-start-on-demand-ms",
        action="append",
        type=int,
        default=[],
    )
    parser.add_argument(
        "--extra-arti-hs-desc-shared-cache-hspool-race-background-start-on-demand-background-build-timeout-cap-combo",
        action="append",
        default=[],
    )
    parser.add_argument(
        "--extra-arti-hs-desc-shared-cache-hspool-race-background-start-on-demand-hsdir-extend-timeout-cap-combo",
        action="append",
        default=[],
    )
    parser.add_argument(
        "--extra-arti-hs-desc-shared-cache-hspool-race-background-start-on-demand-hsdir-extend-timeout-cap-guarded-stem-target-defer-post-bootstrap-combo",
        action="append",
        default=[],
    )
    parser.add_argument(
        "--extra-arti-hs-desc-shared-cache-hspool-race-background-start-on-demand-intro-circuit-hedge-combo",
        action="append",
        default=[],
    )
    parser.add_argument(
        "--extra-arti-hs-desc-shared-cache-hspool-race-background-start-delay-combo",
        action="append",
        default=[],
    )
    parser.add_argument(
        "--extra-arti-hs-desc-shared-cache-hspool-race-background-start-delay-launch-parallelism-combo",
        action="append",
        default=[],
    )
    parser.add_argument(
        "--extra-arti-hs-desc-shared-cache-hspool-race-background-start-delay-guarded-stem-target-defer-post-bootstrap-combo",
        action="append",
        default=[],
    )
    parser.add_argument(
        "--interleaved-target-order",
        choices=("fixed", "rotating"),
        default="rotating",
    )
    parser.add_argument("--targets", nargs="*", default=list(DEFAULT_TARGETS))
    args = parser.parse_args()

    startup_only_timeout_cap_ms_values: list[int] = []
    for timeout_cap_ms in (
        args.extra_arti_hs_desc_shared_cache_hsdir_extend_timeout_cap_startup_only_ms
    ):
        if timeout_cap_ms not in startup_only_timeout_cap_ms_values:
            startup_only_timeout_cap_ms_values.append(timeout_cap_ms)

    post_boot_only_timeout_cap_ms_values: list[int] = []
    for timeout_cap_ms in (
        args.extra_arti_hs_desc_shared_cache_hsdir_extend_timeout_cap_post_boot_only_ms
    ):
        if timeout_cap_ms not in post_boot_only_timeout_cap_ms_values:
            post_boot_only_timeout_cap_ms_values.append(timeout_cap_ms)

    demand_start_race_ms_values: list[int] = []
    for race_ms in (
        args.extra_arti_hs_desc_shared_cache_hspool_race_background_start_on_demand_ms
    ):
        if race_ms not in demand_start_race_ms_values:
            demand_start_race_ms_values.append(race_ms)

    min_hop_combos = list(
        DEFAULT_HS_DESC_SHARED_CACHE_STREAM_READY_DATA_COALESCE_MIN_HOP_COMBOS
    )
    for combo in args.extra_arti_hs_desc_shared_cache_stream_ready_data_coalesce_min_hop_combo:
        if combo not in min_hop_combos:
            min_hop_combos.append(combo)

    runner = Path(__file__).with_name("run_browser_compare.py")
    cmd = [
        sys.executable,
        str(runner),
        "--skip-bundled-tor",
        "--schedule",
        "interleaved",
        "--interleaved-target-order",
        args.interleaved_target_order,
        "--targets",
        *args.targets,
        "--runs",
        str(args.runs),
        "--timeout",
        str(args.timeout),
        "--post-boot-wait",
        str(args.post_boot_wait),
        "--window-size",
        args.window_size,
        "--arti-exit-same-isolation-target",
        "2",
        "--arti-exit-select-health-aware",
        "--arti-exit-select-prefer-cold-same-isolation",
        "--extra-arti-hs-desc-shared-cache",
    ]
    if args.arti_log_level:
        cmd.extend(["--arti-log-level", args.arti_log_level])
    if args.compact_output:
        cmd.append("--compact-output")
    if args.proxy_log_tail_lines is not None:
        cmd.extend(["--proxy-log-tail-lines", str(args.proxy_log_tail_lines)])
    if args.proxy_run_tail_lines is not None:
        cmd.extend(["--proxy-run-tail-lines", str(args.proxy_run_tail_lines)])
    if args.warm_cache:
        cmd.append("--warm-cache")
    if args.share_arti_warm_cache_seed:
        cmd.append("--share-arti-warm-cache-seed")
    if args.browser_startup_seed:
        cmd.append("--browser-startup-seed")
    if args.browser_net_log:
        cmd.append("--browser-net-log")
    if args.byte_tap:
        cmd.append("--byte-tap")
    if args.byte_tap_socks_reply_bind_port_tag:
        cmd.append("--byte-tap-socks-reply-bind-port-tag")
    if args.arti_socks_relay_byte_timing:
        cmd.append("--arti-socks-relay-byte-timing")
    if args.arti_hspool_launch_parallelism is not None:
        cmd.extend(
            [
                "--arti-hspool-launch-parallelism",
                str(args.arti_hspool_launch_parallelism),
            ]
        )
    if args.arti_hspool_background_start_delay_ms is not None:
        cmd.extend(
            [
                "--arti-hspool-background-start-delay-ms",
                str(args.arti_hspool_background_start_delay_ms),
            ]
        )
    if args.arti_hspool_guarded_stem_target is not None:
        cmd.extend(
            [
                "--arti-hspool-guarded-stem-target",
                str(args.arti_hspool_guarded_stem_target),
            ]
        )
    if args.arti_hspool_guarded_stem_target_defer_post_bootstrap:
        cmd.append("--arti-hspool-guarded-stem-target-defer-post-bootstrap")
    if args.arti_hspool_on_demand_grace_ms is not None:
        cmd.extend(
            [
                "--arti-hspool-on-demand-grace-ms",
                str(args.arti_hspool_on_demand_grace_ms),
            ]
        )
    if args.arti_hspool_on_demand_race_ms is not None:
        cmd.extend(
            [
                "--arti-hspool-on-demand-race-ms",
                str(args.arti_hspool_on_demand_race_ms),
            ]
        )
    if args.skip_local_c_tor:
        cmd.append("--skip-local-c-tor")
    if args.skip_plain_arti:
        cmd.append("--skip-plain-arti")
    for burst in args.extra_arti_hs_desc_shared_cache_stream_scheduler_burst:
        cmd.extend(
            [
                "--extra-arti-hs-desc-shared-cache-stream-scheduler-burst",
                str(burst),
            ]
        )
    for coalesce_bytes in (
        args.extra_arti_hs_desc_shared_cache_socks_tor_to_client_coalesce_bytes
    ):
        cmd.extend(
            [
                "--extra-arti-hs-desc-shared-cache-socks-tor-to-client-coalesce-bytes",
                str(coalesce_bytes),
            ]
        )
    for coalesce_bytes in (
        args.extra_arti_hs_desc_shared_cache_stream_ready_data_coalesce_bytes
    ):
        cmd.extend(
            [
                "--extra-arti-hs-desc-shared-cache-stream-ready-data-coalesce-bytes",
                str(coalesce_bytes),
            ]
        )
    for max_active_streams in (
        args.extra_arti_hs_desc_shared_cache_reuse_max_active_streams
    ):
        cmd.extend(
            [
                "--extra-arti-hs-desc-shared-cache-reuse-max-active-streams",
                str(max_active_streams),
            ]
        )
    for combo in min_hop_combos:
        cmd.extend(
            [
                "--extra-arti-hs-desc-shared-cache-stream-ready-data-coalesce-min-hop-combo",
                combo,
            ]
        )
    for timeout_floor_ms in (
        args.extra_arti_hs_desc_shared_cache_rendezvous_establish_timeout_floor_ms
    ):
        cmd.extend(
            [
                "--extra-arti-hs-desc-shared-cache-rendezvous-establish-timeout-floor-ms",
                str(timeout_floor_ms),
            ]
        )
    for combo in (
        args.extra_arti_hs_desc_shared_cache_stream_ready_data_coalesce_min_hop_rendezvous_establish_timeout_floor_combo
    ):
        cmd.extend(
            [
                "--extra-arti-hs-desc-shared-cache-stream-ready-data-coalesce-min-hop-rendezvous-establish-timeout-floor-combo",
                combo,
            ]
        )
    for combo in (
        args.extra_arti_hs_desc_shared_cache_stream_ready_data_coalesce_min_hop_start_backlog_combo
    ):
        cmd.extend(
            [
                "--extra-arti-hs-desc-shared-cache-stream-ready-data-coalesce-min-hop-start-backlog-combo",
                combo,
            ]
        )
    for combo in (
        args.extra_arti_hs_desc_shared_cache_stream_ready_data_coalesce_min_hop_busy_max_combo
    ):
        cmd.extend(
            [
                "--extra-arti-hs-desc-shared-cache-stream-ready-data-coalesce-min-hop-busy-max-combo",
                combo,
            ]
        )
    if args.extra_arti_hs_intro_rend_overlap:
        cmd.append("--extra-arti-hs-intro-rend-overlap")
    for hedge_ms in args.extra_arti_hs_desc_shared_cache_intro_circuit_hedge_ms:
        cmd.extend(
            [
                "--extra-arti-hs-desc-shared-cache-intro-circuit-hedge-ms",
                str(hedge_ms),
            ]
        )
    for timeout_cap_ms in (
        args.extra_arti_hs_desc_shared_cache_hsdir_extend_timeout_cap_ms
    ):
        cmd.extend(
            [
                "--extra-arti-hs-desc-shared-cache-hsdir-extend-timeout-cap-ms",
                str(timeout_cap_ms),
            ]
        )
    for timeout_cap_ms in startup_only_timeout_cap_ms_values:
        cmd.extend(
            [
                "--extra-arti-hs-desc-shared-cache-hsdir-extend-timeout-cap-startup-only-ms",
                str(timeout_cap_ms),
            ]
        )
    for timeout_cap_ms in post_boot_only_timeout_cap_ms_values:
        cmd.extend(
            [
                "--extra-arti-hs-desc-shared-cache-hsdir-extend-timeout-cap-post-boot-only-ms",
                str(timeout_cap_ms),
            ]
        )
    for race_ms in args.extra_arti_hs_desc_shared_cache_hspool_on_demand_race_ms:
        cmd.extend(
            [
                "--extra-arti-hs-desc-shared-cache-hspool-on-demand-race-ms",
                str(race_ms),
            ]
        )
    if args.extra_arti_hs_desc_shared_cache_hspool_background_start_on_demand:
        cmd.append(
            "--extra-arti-hs-desc-shared-cache-hspool-background-start-on-demand"
        )
    for race_ms in demand_start_race_ms_values:
        cmd.extend(
            [
                "--extra-arti-hs-desc-shared-cache-hspool-race-background-start-on-demand-ms",
                str(race_ms),
            ]
        )
    for combo in (
        args.extra_arti_hs_desc_shared_cache_hspool_race_background_start_on_demand_background_build_timeout_cap_combo
    ):
        cmd.extend(
            [
                "--extra-arti-hs-desc-shared-cache-hspool-race-background-start-on-demand-background-build-timeout-cap-combo",
                combo,
            ]
        )
    for combo in (
        args.extra_arti_hs_desc_shared_cache_hspool_race_background_start_on_demand_hsdir_extend_timeout_cap_combo
    ):
        cmd.extend(
            [
                "--extra-arti-hs-desc-shared-cache-hspool-race-background-start-on-demand-hsdir-extend-timeout-cap-combo",
                combo,
            ]
        )
    for combo in (
        args.extra_arti_hs_desc_shared_cache_hspool_race_background_start_on_demand_hsdir_extend_timeout_cap_guarded_stem_target_defer_post_bootstrap_combo
    ):
        cmd.extend(
            [
                "--extra-arti-hs-desc-shared-cache-hspool-race-background-start-on-demand-hsdir-extend-timeout-cap-guarded-stem-target-defer-post-bootstrap-combo",
                combo,
            ]
        )
    for combo in (
        args.extra_arti_hs_desc_shared_cache_hspool_race_background_start_on_demand_intro_circuit_hedge_combo
    ):
        cmd.extend(
            [
                "--extra-arti-hs-desc-shared-cache-hspool-race-background-start-on-demand-intro-circuit-hedge-combo",
                combo,
            ]
        )
    for combo in (
        args.extra_arti_hs_desc_shared_cache_hspool_race_background_start_delay_combo
    ):
        cmd.extend(
            [
                "--extra-arti-hs-desc-shared-cache-hspool-race-background-start-delay-combo",
                combo,
            ]
        )
    for combo in (
        args.extra_arti_hs_desc_shared_cache_hspool_race_background_start_delay_launch_parallelism_combo
    ):
        cmd.extend(
            [
                "--extra-arti-hs-desc-shared-cache-hspool-race-background-start-delay-launch-parallelism-combo",
                combo,
            ]
        )
    for combo in (
        args.extra_arti_hs_desc_shared_cache_hspool_race_background_start_delay_guarded_stem_target_defer_post_bootstrap_combo
    ):
        cmd.extend(
            [
                "--extra-arti-hs-desc-shared-cache-hspool-race-background-start-delay-guarded-stem-target-defer-post-bootstrap-combo",
                combo,
            ]
        )
    if args.extra_arti_hs_rend_prebuild_before_desc_shared_cache:
        cmd.append("--extra-arti-hs-rend-prebuild-before-desc-shared-cache")
    if args.extra_arti_hs_rend_prebuild_before_desc_shared_cache_shared_hit_only:
        cmd.append(
            "--extra-arti-hs-rend-prebuild-before-desc-shared-cache-shared-hit-only"
        )
    for coalesce_bytes in (
        args.extra_arti_hs_rend_prebuild_before_desc_shared_cache_shared_hit_only_stream_ready_data_coalesce_bytes
    ):
        cmd.extend(
            [
                "--extra-arti-hs-rend-prebuild-before-desc-shared-cache-shared-hit-only-stream-ready-data-coalesce-bytes",
                str(coalesce_bytes),
            ]
        )
    for timeout_ms in (
        args.extra_arti_hs_rend_prebuild_before_desc_shared_cache_shared_hit_only_cold_late_ms
    ):
        cmd.extend(
            [
                "--extra-arti-hs-rend-prebuild-before-desc-shared-cache-shared-hit-only-cold-late-ms",
                str(timeout_ms),
            ]
        )
    for max_active_streams in (
        args.extra_arti_hs_rend_prebuild_before_desc_shared_cache_shared_hit_only_reuse_max_active_streams
    ):
        cmd.extend(
            [
                "--extra-arti-hs-rend-prebuild-before-desc-shared-cache-shared-hit-only-reuse-max-active-streams",
                str(max_active_streams),
            ]
        )
    for combo in (
        args.extra_arti_hs_rend_prebuild_before_desc_shared_cache_shared_hit_only_reuse_max_active_streams_startup_only_hsdir_extend_timeout_cap_combo
    ):
        cmd.extend(
            [
                "--extra-arti-hs-rend-prebuild-before-desc-shared-cache-shared-hit-only-reuse-max-active-streams-startup-only-hsdir-extend-timeout-cap-combo",
                combo,
            ]
        )
    for combo in (
        args.extra_arti_hs_rend_prebuild_before_desc_shared_cache_shared_hit_only_reuse_max_active_streams_cold_late_combo
    ):
        cmd.extend(
            [
                "--extra-arti-hs-rend-prebuild-before-desc-shared-cache-shared-hit-only-reuse-max-active-streams-cold-late-combo",
                combo,
            ]
        )
    return subprocess.run(cmd, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
