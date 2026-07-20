#!/usr/bin/env python3
"""Analyze torfast warm/open benchmark compare results."""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime
import json
from pathlib import Path
import re
import statistics
import sys
from urllib.parse import urlsplit


ACTIVE_LIMIT_RE = re.compile(r"AtActiveConnectionLimit")
PENDING_QUEUE_RE = re.compile(r"adding transaction to pending queue")
PROCESS_PENDING_RE = re.compile(r"ProcessPendingQForEntry")
SHOULD_THROTTLE_RE = re.compile(r"ShouldThrottle")
PRIORITY_HEADER_RE = re.compile(r"(?im)^Priority:\s*(.+)$")
CONNECTION_INFO_HASH_FIELDS = (
    "subject_connectionInfoHashKey",
    "extra_args_connectionInfoHashKey",
    "subject_connInfoKey",
    "extra_args_connInfoKey",
)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "path",
        nargs="?",
        help="warm-open benchmark summary.json or result directory",
    )
    parser.add_argument(
        "--results-dir",
        default="results",
        help="directory to search when PATH is omitted",
    )
    parser.add_argument(
        "--target",
        action="append",
        default=[],
        help="restrict analysis to this target; repeat for more",
    )
    parser.add_argument(
        "--baseline-profile",
        help="baseline profile for delta tables; defaults to summary baseline",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=8,
        help="worst runs or top resources to print",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    summary_path = resolve_summary_path(args.path, Path(args.results_dir))
    if summary_path is None:
        print("No torfast warm/open benchmark result found.", file=sys.stderr)
        return 1
    payload = load_json(summary_path)
    run_payloads = load_run_payloads(summary_path.parent)
    target_filter = set(args.target)
    baseline_profile = (
        args.baseline_profile
        if args.baseline_profile is not None
        else payload.get("baseline_profile")
    )

    print(
        "# Torfast Warm/Open Benchmark Analysis\n\n"
        f"source: `{summary_path}`\n"
    )

    print("## Summary Profiles\n")
    print(
        "| profile | target | ok runs | median combined s | median elapsed ms | median load ms | median open gate wait s |"
    )
    print("|---|---|---:|---:|---:|---:|---:|")
    for row in summary_profile_rows(payload, target_filter=target_filter):
        print(
            "| {profile} | {target} | {ok_runs} | {combined} | {elapsed} | {load} | {open_gate_wait} |".format(
                profile=row["profile"],
                target=row["target"],
                ok_runs=fmt(row.get("ok_runs")),
                combined=fmt(row.get("median_combined_wall_seconds")),
                elapsed=fmt(row.get("median_elapsed_ms")),
                load=fmt(row.get("median_load_ms")),
                open_gate_wait=fmt(row.get("median_open_gate_wait_seconds")),
            )
        )

    if baseline_profile:
        delta_rows = summary_profile_delta_rows(
            payload,
            baseline_profile=str(baseline_profile),
            target_filter=target_filter,
        )
        if delta_rows:
            print("\n## Summary Deltas vs Baseline\n")
            print(
                "| profile | target | combined delta s | elapsed delta ms | load delta ms | open gate wait delta s |"
            )
            print("|---|---|---:|---:|---:|---:|")
            for row in delta_rows:
                print(
                    "| {profile} | {target} | {combined} | {elapsed} | {load} | {open_gate_wait} |".format(
                        profile=row["profile"],
                        target=row["target"],
                        combined=fmt(row.get("combined_wall_seconds")),
                        elapsed=fmt(row.get("elapsed_ms")),
                        load=fmt(row.get("load_ms")),
                        open_gate_wait=fmt(row.get("open_gate_wait_seconds")),
                    )
                )

    phase_rows = phase_summary_rows(run_payloads, target_filter=target_filter)
    if phase_rows:
        print("\n## Navigation And Gate Summary\n")
        print(
            "| profile | target | runs | median combined s | median response start ms | median response->dom ms | median dom->load ms | median before boot | median before gc count | median before general | median before conflux | before gc ready runs |"
        )
        print("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
        for row in phase_rows:
            print(
                "| {profile} | {target} | {runs} | {combined} | {response_start} | {response_to_dom} | {dom_to_load} | {before_boot} | {before_gc_count} | {before_general} | {before_conflux} | {before_gc_ready_runs} |".format(
                    profile=row["profile"],
                    target=row["target"],
                    runs=fmt(row.get("runs")),
                    combined=fmt(row.get("median_combined_wall_seconds")),
                    response_start=fmt(row.get("median_nav_response_start_ms")),
                    response_to_dom=fmt(row.get("median_nav_response_to_dom_ms")),
                    dom_to_load=fmt(row.get("median_nav_dom_to_load_ms")),
                    before_boot=fmt(row.get("median_before_bootstrap_progress")),
                    before_gc_count=fmt(row.get("median_before_gc_count")),
                    before_general=fmt(row.get("median_before_general_count")),
                    before_conflux=fmt(row.get("median_before_conflux_count")),
                    before_gc_ready_runs=fmt(row.get("before_gc_ready_runs")),
                )
            )

    timeline_rows = timeline_summary_rows(run_payloads, target_filter=target_filter)
    if timeline_rows:
        print("\n## Circuit Timeline Summary\n")
        print(
            "| profile | target | runs | median first conflux s | median max general | median max conflux | median samples | median duration s |"
        )
        print("|---|---|---:|---:|---:|---:|---:|---:|")
        for row in timeline_rows:
            print(
                "| {profile} | {target} | {runs} | {first_conflux} | {max_general} | {max_conflux} | {samples} | {duration} |".format(
                    profile=row["profile"],
                    target=row["target"],
                    runs=fmt(row.get("runs")),
                    first_conflux=fmt(row.get("median_first_conflux_seconds")),
                    max_general=fmt(row.get("median_max_general_count")),
                    max_conflux=fmt(row.get("median_max_conflux_count")),
                    samples=fmt(row.get("median_sample_count")),
                    duration=fmt(row.get("median_timeline_duration_seconds")),
                )
            )

    stream_timeline_rows = stream_timeline_summary_rows(
        run_payloads, target_filter=target_filter
    )
    if stream_timeline_rows:
        print("\n## Stream Timeline Summary\n")
        print(
            "| profile | target | runs | median peak user streams | median peak-sample circuits | median peak-sample streams/circuit | median peak-sample single-circuit share % | median active samples | median samples |"
        )
        print("|---|---|---:|---:|---:|---:|---:|---:|---:|")
        for row in stream_timeline_rows:
            print(
                "| {profile} | {target} | {runs} | {user_streams} | {circuits} | {streams_per_circuit} | {share_pct} | {active_samples} | {samples} |".format(
                    profile=row["profile"],
                    target=row["target"],
                    runs=fmt(row.get("runs")),
                    user_streams=fmt(row.get("median_peak_user_stream_count")),
                    circuits=fmt(row.get("median_peak_unique_circuit_count")),
                    streams_per_circuit=fmt(
                        row.get("median_peak_streams_per_circuit")
                    ),
                    share_pct=fmt(
                        row.get("median_peak_single_circuit_share_pct")
                    ),
                    active_samples=fmt(row.get("median_active_sample_count")),
                    samples=fmt(row.get("median_sample_count")),
                )
            )

    saturation_rows = saturation_summary_rows(
        run_payloads,
        target_filter=target_filter,
    )
    if saturation_rows:
        print("\n## Queue Saturation And Tail Summary\n")
        print(
            "| profile | target | runs | median queued >1s | median slot-depth>=6 queued >1s | median max slot depth | median tail-after-dom >1s | max tail-after-dom ms | top tail resources |"
        )
        print("|---|---|---:|---:|---:|---:|---:|---:|---|")
        for row in saturation_rows:
            print(
                "| {profile} | {target} | {runs} | {queued_1000} | {slot_depth_6_queued_1000} | {max_slot_depth} | {tail_after_dom_1000} | {max_tail_after_dom} | {tail_resources} |".format(
                    profile=row["profile"],
                    target=row["target"],
                    runs=fmt(row.get("runs")),
                    queued_1000=fmt(row.get("median_queued_gt_1000ms")),
                    slot_depth_6_queued_1000=fmt(
                        row.get("median_slot_depth_6_queued_gt_1000ms")
                    ),
                    max_slot_depth=fmt(row.get("median_max_slot_depth_at_request")),
                    tail_after_dom_1000=fmt(
                        row.get("median_tail_after_dom_gt_1000ms")
                    ),
                    max_tail_after_dom=fmt(row.get("max_tail_after_dom_ms")),
                    tail_resources=row.get("top_tail_resources", ""),
                )
            )

    queue_cause_rows = queue_cause_summary_rows(
        run_payloads,
        target_filter=target_filter,
    )
    if queue_cause_rows:
        print("\n## Queue Cause Summary\n")
        print(
            "| profile | target | runs | median queued >1s | median blocked ms | median unexplained ms | mostly blocked rows | mostly after-prev rows | top unexplained resources |"
        )
        print("|---|---|---:|---:|---:|---:|---:|---:|---|")
        for row in queue_cause_rows:
            print(
                "| {profile} | {target} | {runs} | {queued_1000} | {blocked_ms} | {unexplained_ms} | {blocked_rows} | {after_prev_rows} | {resources} |".format(
                    profile=row["profile"],
                    target=row["target"],
                    runs=fmt(row.get("runs")),
                    queued_1000=fmt(row.get("median_queued_gt_1000ms")),
                    blocked_ms=fmt(row.get("median_total_blocked_ms")),
                    unexplained_ms=fmt(row.get("median_total_unexplained_ms")),
                    blocked_rows=fmt(row.get("median_mostly_blocked_rows")),
                    after_prev_rows=fmt(row.get("median_mostly_after_previous_rows")),
                    resources=row.get("top_unexplained_resources", ""),
                )
            )

    blocker_rows = blocker_chain_summary_rows(
        run_payloads,
        target_filter=target_filter,
    )
    if blocker_rows:
        print("\n## Queue Blocker Chain Summary\n")
        print(
            "| profile | target | runs | max blocked ms | top blocked chains | top blocker resources |"
        )
        print("|---|---|---:|---:|---|---|")
        for row in blocker_rows:
            print(
                "| {profile} | {target} | {runs} | {max_blocked_ms} | {chains} | {resources} |".format(
                    profile=row["profile"],
                    target=row["target"],
                    runs=fmt(row.get("runs")),
                    max_blocked_ms=fmt(row.get("max_blocked_ms")),
                    chains=row.get("top_blocked_chains", ""),
                    resources=row.get("top_blocker_resources", ""),
                )
            )

    blocker_release_rows = blocker_release_summary_rows(
        run_payloads,
        target_filter=target_filter,
    )
    if blocker_release_rows:
        print("\n## Queue Blocker Release Summary\n")
        print(
            "| profile | target | runs | median queued >1s | rows with active blockers | receive-dominant rows | wait-dominant rows | blockers left <=500ms | median max blocker left ms | median queue-minus-left ms | median max wait left ms | median max receive left ms | top queued resources |"
        )
        print("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|")
        for row in blocker_release_rows:
            print(
                "| {profile} | {target} | {runs} | {queued_1000} | {active_rows} | {receive_rows} | {wait_rows} | {left_500} | {remaining} | {queue_minus_left} | {wait_left} | {receive_left} | {resources} |".format(
                    profile=row["profile"],
                    target=row["target"],
                    runs=fmt(row.get("runs")),
                    queued_1000=fmt(row.get("median_queued_gt_1000ms")),
                    active_rows=fmt(row.get("median_rows_with_active_blockers")),
                    receive_rows=fmt(row.get("median_receive_dominant_rows")),
                    wait_rows=fmt(row.get("median_wait_dominant_rows")),
                    left_500=fmt(row.get("median_blockers_left_500ms")),
                    remaining=fmt(row.get("median_max_blocker_remaining_ms")),
                    queue_minus_left=fmt(
                        row.get("median_queue_minus_max_blocker_left_ms")
                    ),
                    wait_left=fmt(row.get("median_max_blocker_wait_left_ms")),
                    receive_left=fmt(row.get("median_max_blocker_receive_left_ms")),
                    resources=row.get("top_queued_resources", ""),
                )
            )

    request_order_rows = request_order_probe_summary_rows(
        run_payloads,
        target_filter=target_filter,
    )
    if request_order_rows:
        print("\n## Browser Activity Request-Order Summary\n")
        print(
            "| profile | target | runs | median queued >1s | rows with probe | request-order-dominant rows | late-discovered >1s rows | median fetch->probe ms | median probe->request ms | top request-order resources | top late-discovery resources |"
        )
        print("|---|---|---:|---:|---:|---:|---:|---:|---:|---|---|")
        for row in request_order_rows:
            print(
                "| {profile} | {target} | {runs} | {queued_1000} | {with_probe} | {request_order_rows} | {late_discovered_rows} | {fetch_to_probe} | {probe_to_request} | {request_order_resources} | {late_discovery_resources} |".format(
                    profile=row["profile"],
                    target=row["target"],
                    runs=fmt(row.get("runs")),
                    queued_1000=fmt(row.get("median_queued_gt_1000ms")),
                    with_probe=fmt(row.get("median_rows_with_probe")),
                    request_order_rows=fmt(
                        row.get("median_request_order_dominant_rows")
                    ),
                    late_discovered_rows=fmt(
                        row.get("median_late_discovered_gt_1000ms_rows")
                    ),
                    fetch_to_probe=fmt(row.get("median_fetch_to_probe_ms")),
                    probe_to_request=fmt(row.get("median_probe_to_request_ms")),
                    request_order_resources=row.get("top_request_order_resources", ""),
                    late_discovery_resources=row.get(
                        "top_late_discovery_resources", ""
                    ),
                )
            )

    priority_group_rows = request_priority_group_summary_rows(
        run_payloads,
        target_filter=target_filter,
    )
    if priority_group_rows:
        print("\n## Browser Activity Priority Group Summary\n")
        print(
            "| profile | target | priority | initiator | runs | median queued >1s rows | request-order-dominant rows | late-discovered >1s rows | median queue ms | median fetch->probe ms | median probe->request ms | top resources |"
        )
        print("|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|")
        for row in priority_group_rows:
            print(
                "| {profile} | {target} | {priority} | {initiator} | {runs} | {queued_rows} | {request_order_rows} | {late_rows} | {queue_ms} | {fetch_to_probe} | {probe_to_request} | {resources} |".format(
                    profile=row["profile"],
                    target=row["target"],
                    priority=row.get("priority_header", ""),
                    initiator=row.get("initiator_type", ""),
                    runs=fmt(row.get("runs")),
                    queued_rows=fmt(row.get("median_queued_gt_1000ms")),
                    request_order_rows=fmt(
                        row.get("median_request_order_dominant_rows")
                    ),
                    late_rows=fmt(row.get("median_late_discovered_gt_1000ms_rows")),
                    queue_ms=fmt(row.get("median_queue_ms")),
                    fetch_to_probe=fmt(row.get("median_fetch_to_probe_ms")),
                    probe_to_request=fmt(row.get("median_probe_to_request_ms")),
                    resources=row.get("top_resources", ""),
                )
            )

    should_throttle_group_rows = should_throttle_priority_group_summary_rows(
        run_payloads,
        target_filter=target_filter,
    )
    if should_throttle_group_rows:
        print("\n## ShouldThrottle Priority Group Summary\n")
        print(
            "| profile | target | priority | initiator | runs | median throttled resources | median ShouldThrottle events | request-order-dominant resources | median queue ms | top throttled resources |"
        )
        print("|---|---|---|---|---:|---:|---:|---:|---:|---|")
        for row in should_throttle_group_rows:
            print(
                "| {profile} | {target} | {priority} | {initiator} | {runs} | {resources} | {events} | {request_order_resources} | {queue_ms} | {top_resources} |".format(
                    profile=row["profile"],
                    target=row["target"],
                    priority=row.get("priority_header", ""),
                    initiator=row.get("initiator_type", ""),
                    runs=fmt(row.get("runs")),
                    resources=fmt(row.get("median_resources")),
                    events=fmt(row.get("median_should_throttle_events")),
                    request_order_resources=fmt(
                        row.get("median_request_order_dominant_resources")
                    ),
                    queue_ms=fmt(row.get("median_queue_ms")),
                    top_resources=row.get("top_resources", ""),
                )
            )

    should_throttle_timing_rows = should_throttle_timing_summary_rows(
        run_payloads,
        target_filter=target_filter,
    )
    if should_throttle_timing_rows:
        print("\n## ShouldThrottle Timing Summary\n")
        print(
            "| profile | target | priority | initiator | runs | median first throttle ms | median fetch-after-throttle ms | median request-after-throttle ms | median ShouldThrottle events | top early-throttled resources |"
        )
        print("|---|---|---|---|---:|---:|---:|---:|---:|---|")
        for row in should_throttle_timing_rows:
            print(
                "| {profile} | {target} | {priority} | {initiator} | {runs} | {first_throttle_ms} | {fetch_after_throttle_ms} | {request_after_throttle_ms} | {events} | {top_resources} |".format(
                    profile=row["profile"],
                    target=row["target"],
                    priority=row.get("priority_header", ""),
                    initiator=row.get("initiator_type", ""),
                    runs=fmt(row.get("runs")),
                    first_throttle_ms=fmt(
                        row.get("median_first_should_throttle_ms")
                    ),
                    fetch_after_throttle_ms=fmt(
                        row.get("median_fetch_after_first_should_throttle_ms")
                    ),
                    request_after_throttle_ms=fmt(
                        row.get("median_request_after_first_should_throttle_ms")
                    ),
                    events=fmt(row.get("median_should_throttle_events")),
                    top_resources=row.get("top_resources", ""),
                )
            )

    should_throttle_wave_rows = should_throttle_wave_summary_rows(
        run_payloads,
        target_filter=target_filter,
    )
    if should_throttle_wave_rows:
        print("\n## ShouldThrottle Wave Summary\n")
        print(
            "| profile | target | priority | initiator | runs | median earliest wave offset ms | median wave offset ms | median request-after-throttle ms | median ShouldThrottle events | top earliest-wave resources |"
        )
        print("|---|---|---|---|---:|---:|---:|---:|---:|---|")
        for row in should_throttle_wave_rows:
            print(
                "| {profile} | {target} | {priority} | {initiator} | {runs} | {earliest_wave_offset_ms} | {wave_offset_ms} | {request_after_throttle_ms} | {events} | {top_resources} |".format(
                    profile=row["profile"],
                    target=row["target"],
                    priority=row.get("priority_header", ""),
                    initiator=row.get("initiator_type", ""),
                    runs=fmt(row.get("runs")),
                    earliest_wave_offset_ms=fmt(
                        row.get("median_earliest_wave_offset_ms")
                    ),
                    wave_offset_ms=fmt(row.get("median_wave_offset_ms")),
                    request_after_throttle_ms=fmt(
                        row.get("median_request_after_first_should_throttle_ms")
                    ),
                    events=fmt(row.get("median_should_throttle_events")),
                    top_resources=row.get("top_resources", ""),
                )
            )

    should_throttle_pre_request_blocker_rows = (
        should_throttle_pre_request_blocker_summary_rows(
            run_payloads,
            target_filter=target_filter,
        )
    )
    if should_throttle_pre_request_blocker_rows:
        print("\n## ShouldThrottle Pre-Request Blocker Summary\n")
        print(
            "| profile | target | priority | initiator | runs | median pre-request resources | median fetch-after-throttle ms | median request-after-throttle ms | median active blockers | median same-group blockers | top blocker groups | top blocked resources |"
        )
        print("|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|")
        for row in should_throttle_pre_request_blocker_rows:
            print(
                "| {profile} | {target} | {priority} | {initiator} | {runs} | {resources} | {fetch_after} | {request_after} | {active_blockers} | {same_group_blockers} | {blocker_groups} | {top_resources} |".format(
                    profile=row["profile"],
                    target=row["target"],
                    priority=row.get("priority_header", ""),
                    initiator=row.get("initiator_type", ""),
                    runs=fmt(row.get("runs")),
                    resources=fmt(row.get("median_resources")),
                    fetch_after=fmt(
                        row.get("median_fetch_after_first_should_throttle_ms")
                    ),
                    request_after=fmt(
                        row.get("median_request_after_first_should_throttle_ms")
                    ),
                    active_blockers=fmt(row.get("median_active_blockers")),
                    same_group_blockers=fmt(row.get("median_same_group_blockers")),
                    blocker_groups=row.get("top_blocker_groups", ""),
                    top_resources=row.get("top_resources", ""),
                )
            )

    should_throttle_pre_request_remaining_rows = (
        should_throttle_pre_request_remaining_summary_rows(
            run_payloads,
            target_filter=target_filter,
        )
    )
    if should_throttle_pre_request_remaining_rows:
        print("\n## ShouldThrottle Pre-Request Blocker Remaining Summary\n")
        print(
            "| profile | target | priority | initiator | runs | median request-after-throttle ms | wait-dominant resources | median max wait left ms | median max receive left ms | median sum wait left ms | median sum receive left ms | top resources |"
        )
        print("|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|")
        for row in should_throttle_pre_request_remaining_rows:
            print(
                "| {profile} | {target} | {priority} | {initiator} | {runs} | {request_after} | {wait_dominant} | {max_wait} | {max_receive} | {sum_wait} | {sum_receive} | {top_resources} |".format(
                    profile=row["profile"],
                    target=row["target"],
                    priority=row.get("priority_header", ""),
                    initiator=row.get("initiator_type", ""),
                    runs=fmt(row.get("runs")),
                    request_after=fmt(
                        row.get("median_request_after_first_should_throttle_ms")
                    ),
                    wait_dominant=fmt(row.get("median_wait_dominant_resources")),
                    max_wait=fmt(row.get("median_max_wait_remaining_ms")),
                    max_receive=fmt(row.get("median_max_receive_remaining_ms")),
                    sum_wait=fmt(row.get("median_sum_wait_remaining_ms")),
                    sum_receive=fmt(row.get("median_sum_receive_remaining_ms")),
                    top_resources=row.get("top_resources", ""),
                )
            )

    should_throttle_pre_request_phase_rows = (
        should_throttle_pre_request_phase_summary_rows(
            run_payloads,
            target_filter=target_filter,
        )
    )
    if should_throttle_pre_request_phase_rows:
        print("\n## ShouldThrottle Pre-Request Phase Summary\n")
        print(
            "| profile | target | priority | initiator | runs | median request-after-throttle ms | response-start-dominant resources | median request->responseStart ms | median responseStart->responseEnd ms | median throttle->responseStart ms | median throttle->responseEnd ms | top TTFB resources |"
        )
        print("|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|")
        for row in should_throttle_pre_request_phase_rows:
            print(
                "| {profile} | {target} | {priority} | {initiator} | {runs} | {request_after} | {response_start_dominant} | {request_to_response_start} | {response_start_to_end} | {throttle_to_response_start} | {throttle_to_response_end} | {top_resources} |".format(
                    profile=row["profile"],
                    target=row["target"],
                    priority=row.get("priority_header", ""),
                    initiator=row.get("initiator_type", ""),
                    runs=fmt(row.get("runs")),
                    request_after=fmt(
                        row.get("median_request_after_first_should_throttle_ms")
                    ),
                    response_start_dominant=fmt(
                        row.get("median_response_start_dominant_resources")
                    ),
                    request_to_response_start=fmt(
                        row.get("median_request_to_response_start_ms")
                    ),
                    response_start_to_end=fmt(
                        row.get("median_response_start_to_response_end_ms")
                    ),
                    throttle_to_response_start=fmt(
                        row.get("median_throttle_to_response_start_ms")
                    ),
                    throttle_to_response_end=fmt(
                        row.get("median_throttle_to_response_end_ms")
                    ),
                    top_resources=row.get("top_resources", ""),
                )
            )

    should_throttle_pre_request_phase_pair_rows = (
        should_throttle_pre_request_phase_pair_summary_rows(
            run_payloads,
            target_filter=target_filter,
        )
    )
    if should_throttle_pre_request_phase_pair_rows:
        print("\n## ShouldThrottle Pre-Request Phase Pair Summary\n")
        print(
            "| profile | target | priority | initiator | runs | median response-start-dominant resources | median request->responseStart ms | median max pair-covered ms | top blocker pairs | top blocker resources | top TTFB resources |"
        )
        print("|---|---|---|---|---:|---:|---:|---:|---|---|---|")
        for row in should_throttle_pre_request_phase_pair_rows:
            print(
                "| {profile} | {target} | {priority} | {initiator} | {runs} | {response_start_dominant} | {request_to_response_start} | {pair_covered} | {top_pairs} | {top_blockers} | {top_resources} |".format(
                    profile=row["profile"],
                    target=row["target"],
                    priority=row.get("priority_header", ""),
                    initiator=row.get("initiator_type", ""),
                    runs=fmt(row.get("runs")),
                    response_start_dominant=fmt(
                        row.get("median_response_start_dominant_resources")
                    ),
                    request_to_response_start=fmt(
                        row.get("median_request_to_response_start_ms")
                    ),
                    pair_covered=fmt(row.get("median_max_pair_covered_ms")),
                    top_pairs=row.get("top_blocker_pairs", ""),
                    top_blockers=row.get("top_blocker_resources", ""),
                    top_resources=row.get("top_resources", ""),
                )
            )

    should_throttle_connection_rows = should_throttle_connection_group_summary_rows(
        run_payloads,
        target_filter=target_filter,
    )
    if should_throttle_connection_rows:
        print("\n## ShouldThrottle Connection Group Summary\n")
        print(
            "| profile | target | priority | initiator | runs | median shared-connection resources | median shared-connection blocker pairs | median request->responseStart ms | median max shared pair-covered ms | top shared-connection pairs | top shared-connection blockers |"
        )
        print("|---|---|---|---|---:|---:|---:|---:|---:|---|---|")
        for row in should_throttle_connection_rows:
            print(
                "| {profile} | {target} | {priority} | {initiator} | {runs} | {resources} | {pairs} | {request_to_response_start} | {pair_covered} | {top_pairs} | {top_blockers} |".format(
                    profile=row["profile"],
                    target=row["target"],
                    priority=row.get("priority_header", ""),
                    initiator=row.get("initiator_type", ""),
                    runs=fmt(row.get("runs")),
                    resources=fmt(row.get("median_shared_connection_resources")),
                    pairs=fmt(row.get("median_shared_connection_pairs")),
                    request_to_response_start=fmt(
                        row.get("median_request_to_response_start_ms")
                    ),
                    pair_covered=fmt(row.get("median_max_shared_pair_covered_ms")),
                    top_pairs=row.get("top_shared_connection_pairs", ""),
                    top_blockers=row.get("top_shared_connection_resources", ""),
                )
            )

    queue_rows = queue_summary_rows(run_payloads, target_filter=target_filter)
    if queue_rows:
        print("\n## Same-Origin Queue Summary\n")
        print(
            "| profile | target | runs | median max queue ms | max queue ms | median queued >2s | median queued >5s | median queued >10s | median active-limit | median pending-queue | median should-throttle | top queued resources |"
        )
        print("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|")
        for row in queue_rows:
            print(
                "| {profile} | {target} | {runs} | {median_max_queue} | {max_max_queue} | {queued_2s} | {queued_5s} | {queued_10s} | {active_limit} | {pending_queue} | {should_throttle} | {resources} |".format(
                    profile=row["profile"],
                    target=row["target"],
                    runs=fmt(row.get("runs")),
                    median_max_queue=fmt(row.get("median_max_queue_ms")),
                    max_max_queue=fmt(row.get("max_max_queue_ms")),
                    queued_2s=fmt(row.get("median_queued_gt_2000ms")),
                    queued_5s=fmt(row.get("median_queued_gt_5000ms")),
                    queued_10s=fmt(row.get("median_queued_gt_10000ms")),
                    active_limit=fmt(row.get("median_active_limit_events")),
                    pending_queue=fmt(row.get("median_pending_queue_events")),
                    should_throttle=fmt(row.get("median_should_throttle_events")),
                    resources=row.get("top_queued_resources", ""),
                )
            )

    worst_rows = worst_run_rows(
        run_payloads, target_filter=target_filter, limit=max(1, args.top)
    )
    if worst_rows:
        print("\n## Worst Runs\n")
        print(
            "| profile | target | cycle | combined s | elapsed ms | load ms | max queue ms | queued >5s | queued >10s | active-limit | pending-queue | should-throttle | top queued resources |"
        )
        print("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|")
        for row in worst_rows:
            print(
                "| {profile} | {target} | {cycle} | {combined} | {elapsed} | {load} | {max_queue} | {queued_5s} | {queued_10s} | {active_limit} | {pending_queue} | {should_throttle} | {resources} |".format(
                    profile=row["profile"],
                    target=row["target"],
                    cycle=fmt(row.get("cycle")),
                    combined=fmt(row.get("combined_wall_seconds")),
                    elapsed=fmt(row.get("elapsed_ms")),
                    load=fmt(row.get("load_ms")),
                    max_queue=fmt(row.get("max_queue_ms")),
                    queued_5s=fmt(row.get("queued_gt_5000ms")),
                    queued_10s=fmt(row.get("queued_gt_10000ms")),
                    active_limit=fmt(row.get("active_limit_events")),
                    pending_queue=fmt(row.get("pending_queue_events")),
                    should_throttle=fmt(row.get("should_throttle_events")),
                    resources=row.get("top_queued_resources", ""),
                )
            )

    return 0


def resolve_summary_path(path_arg: str | None, results_dir: Path) -> Path | None:
    if path_arg:
        path = Path(path_arg)
        if path.is_dir():
            candidate = path / "summary.json"
            return candidate if candidate.exists() else None
        return path if path.exists() else None
    candidates = sorted(
        results_dir.glob("torfast-warm-open-benchmark-compare-*/summary.json")
    )
    return candidates[-1] if candidates else None


def load_json(path: Path) -> dict[str, object]:
    with path.open() as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise SystemExit(f"expected JSON object in {path}")
    return payload


def load_run_payloads(result_dir: Path) -> list[dict[str, object]]:
    payloads: list[dict[str, object]] = []
    for path in sorted(result_dir.glob("*.json")):
        if path.name == "summary.json":
            continue
        payload = load_json(path)
        payload["_path"] = str(path)
        payloads.append(payload)
    return payloads


def summary_profile_rows(
    payload: dict[str, object], *, target_filter: set[str]
) -> list[dict[str, object]]:
    summary_profiles = payload.get("summary_profiles")
    if not isinstance(summary_profiles, dict):
        return []
    rows: list[dict[str, object]] = []
    for target, target_profiles in summary_profiles.items():
        if not isinstance(target, str):
            continue
        if target_filter and target not in target_filter:
            continue
        if not isinstance(target_profiles, dict):
            continue
        for profile, profile_summary in target_profiles.items():
            if not isinstance(profile, str) or not isinstance(profile_summary, dict):
                continue
            rows.append(
                {
                    "target": target,
                    "profile": profile,
                    **profile_summary,
                }
            )
    rows.sort(key=lambda row: (str(row["target"]), str(row["profile"])))
    return rows


def summary_profile_delta_rows(
    payload: dict[str, object],
    *,
    baseline_profile: str,
    target_filter: set[str],
) -> list[dict[str, object]]:
    delta_vs_baseline = payload.get("delta_vs_baseline")
    if not isinstance(delta_vs_baseline, dict):
        return []
    rows: list[dict[str, object]] = []
    for target, target_profiles in delta_vs_baseline.items():
        if not isinstance(target, str):
            continue
        if target_filter and target not in target_filter:
            continue
        if not isinstance(target_profiles, dict):
            continue
        for profile, delta in target_profiles.items():
            if (
                not isinstance(profile, str)
                or profile == baseline_profile
                or not isinstance(delta, dict)
            ):
                continue
            rows.append({"target": target, "profile": profile, **delta})
    rows.sort(key=lambda row: (str(row["target"]), str(row["profile"])))
    return rows


def queue_summary_rows(
    run_payloads: list[dict[str, object]], *, target_filter: set[str]
) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for payload in run_payloads:
        row = queue_row(payload)
        if row is None:
            continue
        target = str(row["target"])
        if target_filter and target not in target_filter:
            continue
        grouped[(target, str(row["profile"]))].append(row)

    rows: list[dict[str, object]] = []
    for (target, profile), group_rows in sorted(grouped.items()):
        top_resources = top_names_by_score(
            group_rows,
            value_key="max_queue_ms",
            names_key="top_queued_resource_names",
            limit=4,
        )
        rows.append(
            {
                "target": target,
                "profile": profile,
                "runs": len(group_rows),
                "median_max_queue_ms": median(
                    row.get("max_queue_ms") for row in group_rows
                ),
                "max_max_queue_ms": max_numeric(
                    row.get("max_queue_ms") for row in group_rows
                ),
                "median_queued_gt_2000ms": median(
                    row.get("queued_gt_2000ms") for row in group_rows
                ),
                "median_queued_gt_5000ms": median(
                    row.get("queued_gt_5000ms") for row in group_rows
                ),
                "median_queued_gt_10000ms": median(
                    row.get("queued_gt_10000ms") for row in group_rows
                ),
                "median_active_limit_events": median(
                    row.get("active_limit_events") for row in group_rows
                ),
                "median_pending_queue_events": median(
                    row.get("pending_queue_events") for row in group_rows
                ),
                "median_should_throttle_events": median(
                    row.get("should_throttle_events") for row in group_rows
                ),
                "top_queued_resources": ", ".join(top_resources),
            }
        )
    return rows


def phase_summary_rows(
    run_payloads: list[dict[str, object]], *, target_filter: set[str]
) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for payload in run_payloads:
        row = phase_row(payload)
        if row is None:
            continue
        target = str(row["target"])
        if target_filter and target not in target_filter:
            continue
        grouped[(target, str(row["profile"]))].append(row)

    rows: list[dict[str, object]] = []
    for (target, profile), group_rows in sorted(grouped.items()):
        rows.append(
            {
                "target": target,
                "profile": profile,
                "runs": len(group_rows),
                "median_combined_wall_seconds": median(
                    row.get("combined_wall_seconds") for row in group_rows
                ),
                "median_nav_response_start_ms": median(
                    row.get("nav_response_start_ms") for row in group_rows
                ),
                "median_nav_response_to_dom_ms": median(
                    row.get("nav_response_to_dom_ms") for row in group_rows
                ),
                "median_nav_dom_to_load_ms": median(
                    row.get("nav_dom_to_load_ms") for row in group_rows
                ),
                "median_before_bootstrap_progress": median(
                    row.get("before_bootstrap_progress") for row in group_rows
                ),
                "median_before_gc_count": median(
                    row.get("before_gc_count") for row in group_rows
                ),
                "median_before_general_count": median(
                    row.get("before_general_count") for row in group_rows
                ),
                "median_before_conflux_count": median(
                    row.get("before_conflux_count") for row in group_rows
                ),
                "before_gc_ready_runs": sum(
                    1 for row in group_rows if row.get("before_has_built_gc") is True
                ),
            }
        )
    return rows


def timeline_summary_rows(
    run_payloads: list[dict[str, object]], *, target_filter: set[str]
) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for payload in run_payloads:
        row = timeline_row(payload)
        if row is None:
            continue
        target = str(row["target"])
        if target_filter and target not in target_filter:
            continue
        grouped[(target, str(row["profile"]))].append(row)

    rows: list[dict[str, object]] = []
    for (target, profile), group_rows in sorted(grouped.items()):
        rows.append(
            {
                "target": target,
                "profile": profile,
                "runs": len(group_rows),
                "median_first_conflux_seconds": median(
                    row.get("first_conflux_seconds") for row in group_rows
                ),
                "median_max_general_count": median(
                    row.get("max_general_count") for row in group_rows
                ),
                "median_max_conflux_count": median(
                    row.get("max_conflux_count") for row in group_rows
                ),
                "median_sample_count": median(
                    row.get("sample_count") for row in group_rows
                ),
                "median_timeline_duration_seconds": median(
                    row.get("timeline_duration_seconds") for row in group_rows
                ),
            }
        )
    return rows


def stream_timeline_summary_rows(
    run_payloads: list[dict[str, object]], *, target_filter: set[str]
) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for payload in run_payloads:
        row = stream_timeline_row(payload)
        if row is None:
            continue
        target = str(row["target"])
        if target_filter and target not in target_filter:
            continue
        grouped[(target, str(row["profile"]))].append(row)

    rows: list[dict[str, object]] = []
    for (target, profile), group_rows in sorted(grouped.items()):
        rows.append(
            {
                "target": target,
                "profile": profile,
                "runs": len(group_rows),
                "median_peak_user_stream_count": median(
                    row.get("peak_user_stream_count") for row in group_rows
                ),
                "median_peak_unique_circuit_count": median(
                    row.get("peak_unique_circuit_count") for row in group_rows
                ),
                "median_peak_streams_per_circuit": median(
                    row.get("peak_streams_per_circuit") for row in group_rows
                ),
                "median_peak_single_circuit_share_pct": median(
                    row.get("peak_single_circuit_share_pct") for row in group_rows
                ),
                "median_active_sample_count": median(
                    row.get("active_sample_count") for row in group_rows
                ),
                "median_sample_count": median(
                    row.get("sample_count") for row in group_rows
                ),
            }
        )
    rows.sort(
        key=lambda row: (
            -(numeric(row.get("median_peak_single_circuit_share_pct")) or 0.0),
            -(numeric(row.get("median_peak_user_stream_count")) or 0.0),
            -(numeric(row.get("median_peak_unique_circuit_count")) or 0.0),
            str(row.get("profile", "")),
        )
    )
    return rows


def saturation_summary_rows(
    run_payloads: list[dict[str, object]], *, target_filter: set[str]
) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for payload in run_payloads:
        row = saturation_row(payload)
        if row is None:
            continue
        target = str(row["target"])
        if target_filter and target not in target_filter:
            continue
        grouped[(target, str(row["profile"]))].append(row)

    rows: list[dict[str, object]] = []
    for (target, profile), group_rows in sorted(grouped.items()):
        rows.append(
            {
                "target": target,
                "profile": profile,
                "runs": len(group_rows),
                "median_queued_gt_1000ms": median(
                    row.get("queued_gt_1000ms") for row in group_rows
                ),
                "median_slot_depth_6_queued_gt_1000ms": median(
                    row.get("slot_depth_6_queued_gt_1000ms") for row in group_rows
                ),
                "median_max_slot_depth_at_request": median(
                    row.get("max_slot_depth_at_request") for row in group_rows
                ),
                "median_tail_after_dom_gt_1000ms": median(
                    row.get("tail_after_dom_gt_1000ms") for row in group_rows
                ),
                "max_tail_after_dom_ms": max_numeric(
                    row.get("max_tail_after_dom_ms") for row in group_rows
                ),
                "top_tail_resources": ", ".join(
                    top_names_by_score(
                        group_rows,
                        value_key="max_tail_after_dom_ms",
                        names_key="top_tail_resource_names",
                        limit=4,
                    )
                ),
            }
        )
    return rows


def queue_cause_summary_rows(
    run_payloads: list[dict[str, object]], *, target_filter: set[str]
) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for payload in run_payloads:
        row = queue_cause_row(payload)
        if row is None:
            continue
        target = str(row["target"])
        if target_filter and target not in target_filter:
            continue
        grouped[(target, str(row["profile"]))].append(row)

    rows: list[dict[str, object]] = []
    for (target, profile), group_rows in sorted(grouped.items()):
        rows.append(
            {
                "target": target,
                "profile": profile,
                "runs": len(group_rows),
                "median_queued_gt_1000ms": median(
                    row.get("queued_gt_1000ms") for row in group_rows
                ),
                "median_total_blocked_ms": median(
                    row.get("total_blocked_ms") for row in group_rows
                ),
                "median_total_unexplained_ms": median(
                    row.get("total_unexplained_ms") for row in group_rows
                ),
                "median_mostly_blocked_rows": median(
                    row.get("mostly_blocked_rows") for row in group_rows
                ),
                "median_mostly_after_previous_rows": median(
                    row.get("mostly_after_previous_rows") for row in group_rows
                ),
                "top_unexplained_resources": ", ".join(
                    top_names_by_score_map(
                        group_rows,
                        score_map_key="unexplained_resource_scores",
                        limit=4,
                    )
                ),
            }
        )
    return rows


def blocker_chain_summary_rows(
    run_payloads: list[dict[str, object]], *, target_filter: set[str]
) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for payload in run_payloads:
        row = queue_cause_row(payload)
        if row is None:
            continue
        target = str(row["target"])
        if target_filter and target not in target_filter:
            continue
        grouped[(target, str(row["profile"]))].append(row)

    rows: list[dict[str, object]] = []
    for (target, profile), group_rows in sorted(grouped.items()):
        rows.append(
            {
                "target": target,
                "profile": profile,
                "runs": len(group_rows),
                "max_blocked_ms": max_numeric(
                    row.get("max_blocked_ms") for row in group_rows
                ),
                "top_blocked_chains": ", ".join(
                    top_names_by_score_map(
                        group_rows,
                        score_map_key="blocked_chain_scores",
                        limit=4,
                    )
                ),
                "top_blocker_resources": ", ".join(
                    top_names_by_score_map(
                        group_rows,
                        score_map_key="blocker_resource_scores",
                        limit=4,
                    )
                ),
            }
        )
    return rows


def blocker_release_summary_rows(
    run_payloads: list[dict[str, object]], *, target_filter: set[str]
) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for payload in run_payloads:
        row = blocker_release_row(payload)
        if row is None:
            continue
        target = str(row["target"])
        if target_filter and target not in target_filter:
            continue
        grouped[(target, str(row["profile"]))].append(row)

    rows: list[dict[str, object]] = []
    for (target, profile), group_rows in sorted(grouped.items()):
        rows.append(
            {
                "target": target,
                "profile": profile,
                "runs": len(group_rows),
                "median_queued_gt_1000ms": median(
                    row.get("queued_gt_1000ms") for row in group_rows
                ),
                "median_rows_with_active_blockers": median(
                    row.get("rows_with_active_blockers") for row in group_rows
                ),
                "median_receive_dominant_rows": median(
                    row.get("receive_dominant_rows") for row in group_rows
                ),
                "median_wait_dominant_rows": median(
                    row.get("wait_dominant_rows") for row in group_rows
                ),
                "median_blockers_left_500ms": median(
                    row.get("blockers_left_500ms") for row in group_rows
                ),
                "median_max_blocker_remaining_ms": median(
                    row.get("median_max_blocker_remaining_ms") for row in group_rows
                ),
                "median_queue_minus_max_blocker_left_ms": median(
                    row.get("median_queue_minus_max_blocker_left_ms")
                    for row in group_rows
                ),
                "median_max_blocker_wait_left_ms": median(
                    row.get("median_max_blocker_wait_left_ms") for row in group_rows
                ),
                "median_max_blocker_receive_left_ms": median(
                    row.get("median_max_blocker_receive_left_ms") for row in group_rows
                ),
                "top_queued_resources": ", ".join(
                    top_names_by_score(
                        group_rows,
                        value_key="max_queue_ms",
                        names_key="top_queued_resource_names",
                        limit=4,
                    )
                ),
            }
        )
    return rows


def request_order_probe_summary_rows(
    run_payloads: list[dict[str, object]], *, target_filter: set[str]
) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for payload in run_payloads:
        row = request_order_probe_row(payload)
        if row is None:
            continue
        target = str(row["target"])
        if target_filter and target not in target_filter:
            continue
        grouped[(target, str(row["profile"]))].append(row)

    rows: list[dict[str, object]] = []
    for (target, profile), group_rows in sorted(grouped.items()):
        rows.append(
            {
                "target": target,
                "profile": profile,
                "runs": len(group_rows),
                "median_queued_gt_1000ms": median(
                    row.get("queued_gt_1000ms") for row in group_rows
                ),
                "median_rows_with_probe": median(
                    row.get("rows_with_probe") for row in group_rows
                ),
                "median_request_order_dominant_rows": median(
                    row.get("request_order_dominant_rows") for row in group_rows
                ),
                "median_late_discovered_gt_1000ms_rows": median(
                    row.get("late_discovered_gt_1000ms_rows") for row in group_rows
                ),
                "median_fetch_to_probe_ms": median(
                    row.get("median_fetch_to_probe_ms") for row in group_rows
                ),
                "median_probe_to_request_ms": median(
                    row.get("median_probe_to_request_ms") for row in group_rows
                ),
                "top_request_order_resources": ", ".join(
                    top_names_by_score_map(
                        group_rows,
                        score_map_key="request_order_resource_scores",
                        limit=4,
                    )
                ),
                "top_late_discovery_resources": ", ".join(
                    top_names_by_score_map(
                        group_rows,
                        score_map_key="late_discovery_resource_scores",
                        limit=4,
                    )
                ),
            }
        )
    return rows


def request_priority_group_summary_rows(
    run_payloads: list[dict[str, object]], *, target_filter: set[str]
) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str, str, str], list[dict[str, object]]] = defaultdict(list)
    for payload in run_payloads:
        for row in request_priority_group_rows_for_payload(payload):
            target = str(row["target"])
            if target_filter and target not in target_filter:
                continue
            grouped[
                (
                    target,
                    str(row["profile"]),
                    str(row["priority_header"]),
                    str(row["initiator_type"]),
                )
            ].append(row)

    rows: list[dict[str, object]] = []
    for (target, profile, priority_header, initiator_type), group_rows in sorted(
        grouped.items()
    ):
        rows.append(
            {
                "target": target,
                "profile": profile,
                "priority_header": priority_header,
                "initiator_type": initiator_type,
                "runs": len(group_rows),
                "median_queued_gt_1000ms": median(
                    row.get("queued_gt_1000ms") for row in group_rows
                ),
                "median_request_order_dominant_rows": median(
                    row.get("request_order_dominant_rows") for row in group_rows
                ),
                "median_late_discovered_gt_1000ms_rows": median(
                    row.get("late_discovered_gt_1000ms_rows") for row in group_rows
                ),
                "median_queue_ms": median(
                    row.get("median_queue_ms") for row in group_rows
                ),
                "median_fetch_to_probe_ms": median(
                    row.get("median_fetch_to_probe_ms") for row in group_rows
                ),
                "median_probe_to_request_ms": median(
                    row.get("median_probe_to_request_ms") for row in group_rows
                ),
                "top_resources": ", ".join(
                    top_names_by_score(
                        group_rows,
                        value_key="max_queue_ms",
                        names_key="top_resource_names",
                        limit=4,
                    )
                ),
            }
        )
    rows.sort(
        key=lambda row: (
            numeric(row.get("median_queued_gt_1000ms")) or 0.0,
            numeric(row.get("median_probe_to_request_ms")) or 0.0,
            numeric(row.get("median_queue_ms")) or 0.0,
            str(row.get("priority_header", "")),
            str(row.get("initiator_type", "")),
        ),
        reverse=True,
    )
    return rows


def should_throttle_priority_group_summary_rows(
    run_payloads: list[dict[str, object]], *, target_filter: set[str]
) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str, str, str], list[dict[str, object]]] = defaultdict(list)
    for payload in run_payloads:
        for row in should_throttle_priority_group_rows_for_payload(payload):
            target = str(row["target"])
            if target_filter and target not in target_filter:
                continue
            grouped[
                (
                    target,
                    str(row["profile"]),
                    str(row["priority_header"]),
                    str(row["initiator_type"]),
                )
            ].append(row)

    rows: list[dict[str, object]] = []
    for (target, profile, priority_header, initiator_type), group_rows in sorted(
        grouped.items()
    ):
        rows.append(
            {
                "target": target,
                "profile": profile,
                "priority_header": priority_header,
                "initiator_type": initiator_type,
                "runs": len(group_rows),
                "median_resources": median(
                    row.get("resources") for row in group_rows
                ),
                "median_should_throttle_events": median(
                    row.get("should_throttle_events") for row in group_rows
                ),
                "median_request_order_dominant_resources": median(
                    row.get("request_order_dominant_resources") for row in group_rows
                ),
                "median_queue_ms": median(
                    row.get("median_queue_ms") for row in group_rows
                ),
                "top_resources": ", ".join(
                    top_names_by_score(
                        group_rows,
                        value_key="max_should_throttle_events",
                        names_key="top_resource_names",
                        limit=4,
                    )
                ),
            }
        )
    rows.sort(
        key=lambda row: (
            numeric(row.get("median_should_throttle_events")) or 0.0,
            numeric(row.get("median_resources")) or 0.0,
            numeric(row.get("median_queue_ms")) or 0.0,
            str(row.get("priority_header", "")),
            str(row.get("initiator_type", "")),
        ),
        reverse=True,
    )
    return rows


def should_throttle_timing_summary_rows(
    run_payloads: list[dict[str, object]], *, target_filter: set[str]
) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str, str, str], list[dict[str, object]]] = defaultdict(list)
    for payload in run_payloads:
        for row in should_throttle_timing_group_rows_for_payload(payload):
            target = str(row["target"])
            if target_filter and target not in target_filter:
                continue
            grouped[
                (
                    target,
                    str(row["profile"]),
                    str(row["priority_header"]),
                    str(row["initiator_type"]),
                )
            ].append(row)

    rows: list[dict[str, object]] = []
    for (target, profile, priority_header, initiator_type), group_rows in sorted(
        grouped.items()
    ):
        rows.append(
            {
                "target": target,
                "profile": profile,
                "priority_header": priority_header,
                "initiator_type": initiator_type,
                "runs": len(group_rows),
                "median_first_should_throttle_ms": median(
                    row.get("median_first_should_throttle_ms") for row in group_rows
                ),
                "median_fetch_after_first_should_throttle_ms": median(
                    row.get("median_fetch_after_first_should_throttle_ms")
                    for row in group_rows
                ),
                "median_request_after_first_should_throttle_ms": median(
                    row.get("median_request_after_first_should_throttle_ms")
                    for row in group_rows
                ),
                "median_should_throttle_events": median(
                    row.get("should_throttle_events") for row in group_rows
                ),
                "top_resources": ", ".join(
                    top_names_by_score(
                        group_rows,
                        value_key="max_request_after_first_should_throttle_ms",
                        names_key="top_resource_names",
                        limit=4,
                    )
                ),
            }
        )
    rows.sort(
        key=lambda row: (
            -(numeric(row.get("median_request_after_first_should_throttle_ms")) or 0.0),
            -(numeric(row.get("median_should_throttle_events")) or 0.0),
            numeric(row.get("median_first_should_throttle_ms"))
            if numeric(row.get("median_first_should_throttle_ms")) is not None
            else float("inf"),
            str(row.get("priority_header", "")),
            str(row.get("initiator_type", "")),
        )
    )
    return rows


def should_throttle_wave_summary_rows(
    run_payloads: list[dict[str, object]], *, target_filter: set[str]
) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str, str, str], list[dict[str, object]]] = defaultdict(list)
    for payload in run_payloads:
        for row in should_throttle_wave_group_rows_for_payload(payload):
            target = str(row["target"])
            if target_filter and target not in target_filter:
                continue
            grouped[
                (
                    target,
                    str(row["profile"]),
                    str(row["priority_header"]),
                    str(row["initiator_type"]),
                )
            ].append(row)

    rows: list[dict[str, object]] = []
    for (target, profile, priority_header, initiator_type), group_rows in sorted(
        grouped.items()
    ):
        rows.append(
            {
                "target": target,
                "profile": profile,
                "priority_header": priority_header,
                "initiator_type": initiator_type,
                "runs": len(group_rows),
                "median_earliest_wave_offset_ms": median(
                    row.get("earliest_wave_offset_ms") for row in group_rows
                ),
                "median_wave_offset_ms": median(
                    row.get("median_wave_offset_ms") for row in group_rows
                ),
                "median_request_after_first_should_throttle_ms": median(
                    row.get("median_request_after_first_should_throttle_ms")
                    for row in group_rows
                ),
                "median_should_throttle_events": median(
                    row.get("should_throttle_events") for row in group_rows
                ),
                "top_resources": ", ".join(
                    top_names_by_score(
                        group_rows,
                        value_key="negative_earliest_wave_offset_ms",
                        names_key="top_resource_names",
                        limit=4,
                    )
                ),
            }
        )
    rows.sort(
        key=lambda row: (
            numeric(row.get("median_earliest_wave_offset_ms"))
            if numeric(row.get("median_earliest_wave_offset_ms")) is not None
            else float("inf"),
            numeric(row.get("median_wave_offset_ms"))
            if numeric(row.get("median_wave_offset_ms")) is not None
            else float("inf"),
            -(numeric(row.get("median_should_throttle_events")) or 0.0),
            str(row.get("priority_header", "")),
            str(row.get("initiator_type", "")),
        )
    )
    return rows


def should_throttle_pre_request_blocker_summary_rows(
    run_payloads: list[dict[str, object]], *, target_filter: set[str]
) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str, str, str], list[dict[str, object]]] = defaultdict(list)
    for payload in run_payloads:
        for row in should_throttle_pre_request_blocker_group_rows_for_payload(payload):
            target = str(row["target"])
            if target_filter and target not in target_filter:
                continue
            grouped[
                (
                    target,
                    str(row["profile"]),
                    str(row["priority_header"]),
                    str(row["initiator_type"]),
                )
            ].append(row)

    rows: list[dict[str, object]] = []
    for (target, profile, priority_header, initiator_type), group_rows in sorted(
        grouped.items()
    ):
        rows.append(
            {
                "target": target,
                "profile": profile,
                "priority_header": priority_header,
                "initiator_type": initiator_type,
                "runs": len(group_rows),
                "median_resources": median(
                    row.get("resources") for row in group_rows
                ),
                "median_fetch_after_first_should_throttle_ms": median(
                    row.get("median_fetch_after_first_should_throttle_ms")
                    for row in group_rows
                ),
                "median_request_after_first_should_throttle_ms": median(
                    row.get("median_request_after_first_should_throttle_ms")
                    for row in group_rows
                ),
                "median_active_blockers": median(
                    row.get("median_active_blockers") for row in group_rows
                ),
                "median_same_group_blockers": median(
                    row.get("median_same_group_blockers") for row in group_rows
                ),
                "top_blocker_groups": ", ".join(
                    top_names_from_score_map(
                        summed_score_maps(
                            group_rows,
                            score_map_key="blocker_group_scores",
                        ),
                        limit=4,
                    )
                ),
                "top_resources": ", ".join(
                    top_names_by_score_map(
                        group_rows,
                        score_map_key="resource_scores",
                        limit=4,
                    )
                ),
            }
        )
    rows.sort(
        key=lambda row: (
            -(numeric(row.get("median_request_after_first_should_throttle_ms")) or 0.0),
            -(numeric(row.get("median_resources")) or 0.0),
            -(numeric(row.get("median_active_blockers")) or 0.0),
            str(row.get("priority_header", "")),
            str(row.get("initiator_type", "")),
        )
    )
    return rows


def should_throttle_pre_request_remaining_summary_rows(
    run_payloads: list[dict[str, object]], *, target_filter: set[str]
) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str, str, str], list[dict[str, object]]] = defaultdict(list)
    for payload in run_payloads:
        for row in should_throttle_pre_request_remaining_group_rows_for_payload(payload):
            target = str(row["target"])
            if target_filter and target not in target_filter:
                continue
            grouped[
                (
                    target,
                    str(row["profile"]),
                    str(row["priority_header"]),
                    str(row["initiator_type"]),
                )
            ].append(row)

    rows: list[dict[str, object]] = []
    for (target, profile, priority_header, initiator_type), group_rows in sorted(
        grouped.items()
    ):
        rows.append(
            {
                "target": target,
                "profile": profile,
                "priority_header": priority_header,
                "initiator_type": initiator_type,
                "runs": len(group_rows),
                "median_request_after_first_should_throttle_ms": median(
                    row.get("median_request_after_first_should_throttle_ms")
                    for row in group_rows
                ),
                "median_wait_dominant_resources": median(
                    row.get("wait_dominant_resources") for row in group_rows
                ),
                "median_max_wait_remaining_ms": median(
                    row.get("median_max_wait_remaining_ms") for row in group_rows
                ),
                "median_max_receive_remaining_ms": median(
                    row.get("median_max_receive_remaining_ms")
                    for row in group_rows
                ),
                "median_sum_wait_remaining_ms": median(
                    row.get("median_sum_wait_remaining_ms") for row in group_rows
                ),
                "median_sum_receive_remaining_ms": median(
                    row.get("median_sum_receive_remaining_ms")
                    for row in group_rows
                ),
                "top_resources": ", ".join(
                    top_names_by_score_map(
                        group_rows,
                        score_map_key="resource_scores",
                        limit=4,
                    )
                ),
            }
        )
    rows.sort(
        key=lambda row: (
            -(numeric(row.get("median_request_after_first_should_throttle_ms")) or 0.0),
            -(numeric(row.get("median_wait_dominant_resources")) or 0.0),
            -(numeric(row.get("median_sum_wait_remaining_ms")) or 0.0),
            str(row.get("priority_header", "")),
            str(row.get("initiator_type", "")),
        )
    )
    return rows


def should_throttle_pre_request_phase_summary_rows(
    run_payloads: list[dict[str, object]], *, target_filter: set[str]
) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str, str, str], list[dict[str, object]]] = defaultdict(list)
    for payload in run_payloads:
        for row in should_throttle_pre_request_phase_group_rows_for_payload(payload):
            target = str(row["target"])
            if target_filter and target not in target_filter:
                continue
            grouped[
                (
                    target,
                    str(row["profile"]),
                    str(row["priority_header"]),
                    str(row["initiator_type"]),
                )
            ].append(row)

    rows: list[dict[str, object]] = []
    for (target, profile, priority_header, initiator_type), group_rows in sorted(
        grouped.items()
    ):
        rows.append(
            {
                "target": target,
                "profile": profile,
                "priority_header": priority_header,
                "initiator_type": initiator_type,
                "runs": len(group_rows),
                "median_request_after_first_should_throttle_ms": median(
                    row.get("median_request_after_first_should_throttle_ms")
                    for row in group_rows
                ),
                "median_response_start_dominant_resources": median(
                    row.get("response_start_dominant_resources") for row in group_rows
                ),
                "median_request_to_response_start_ms": median(
                    row.get("median_request_to_response_start_ms")
                    for row in group_rows
                ),
                "median_response_start_to_response_end_ms": median(
                    row.get("median_response_start_to_response_end_ms")
                    for row in group_rows
                ),
                "median_throttle_to_response_start_ms": median(
                    row.get("median_throttle_to_response_start_ms")
                    for row in group_rows
                ),
                "median_throttle_to_response_end_ms": median(
                    row.get("median_throttle_to_response_end_ms")
                    for row in group_rows
                ),
                "top_resources": ", ".join(
                    top_names_by_score_map(
                        group_rows,
                        score_map_key="resource_scores",
                        limit=4,
                    )
                ),
            }
        )
    rows.sort(
        key=lambda row: (
            -(numeric(row.get("median_request_after_first_should_throttle_ms")) or 0.0),
            -(numeric(row.get("median_request_to_response_start_ms")) or 0.0),
            -(numeric(row.get("median_response_start_dominant_resources")) or 0.0),
            str(row.get("priority_header", "")),
            str(row.get("initiator_type", "")),
        )
    )
    return rows


def should_throttle_pre_request_phase_pair_summary_rows(
    run_payloads: list[dict[str, object]], *, target_filter: set[str]
) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str, str, str], list[dict[str, object]]] = defaultdict(list)
    for payload in run_payloads:
        for row in should_throttle_pre_request_phase_pair_group_rows_for_payload(payload):
            target = str(row["target"])
            if target_filter and target not in target_filter:
                continue
            grouped[
                (
                    target,
                    str(row["profile"]),
                    str(row["priority_header"]),
                    str(row["initiator_type"]),
                )
            ].append(row)

    rows: list[dict[str, object]] = []
    for (target, profile, priority_header, initiator_type), group_rows in sorted(
        grouped.items()
    ):
        rows.append(
            {
                "target": target,
                "profile": profile,
                "priority_header": priority_header,
                "initiator_type": initiator_type,
                "runs": len(group_rows),
                "median_response_start_dominant_resources": median(
                    row.get("response_start_dominant_resources") for row in group_rows
                ),
                "median_request_to_response_start_ms": median(
                    row.get("median_request_to_response_start_ms")
                    for row in group_rows
                ),
                "median_max_pair_covered_ms": median(
                    row.get("median_max_pair_covered_ms") for row in group_rows
                ),
                "top_blocker_pairs": ", ".join(
                    top_names_from_score_map(
                        summed_score_maps(
                            group_rows,
                            score_map_key="blocker_pair_scores",
                        ),
                        limit=4,
                    )
                ),
                "top_blocker_resources": ", ".join(
                    top_names_from_score_map(
                        summed_score_maps(
                            group_rows,
                            score_map_key="blocker_resource_scores",
                        ),
                        limit=4,
                    )
                ),
                "top_resources": ", ".join(
                    top_names_by_score_map(
                        group_rows,
                        score_map_key="resource_scores",
                        limit=4,
                    )
                ),
            }
        )
    rows.sort(
        key=lambda row: (
            -(numeric(row.get("median_request_to_response_start_ms")) or 0.0),
            -(numeric(row.get("median_max_pair_covered_ms")) or 0.0),
            -(numeric(row.get("median_response_start_dominant_resources")) or 0.0),
            str(row.get("priority_header", "")),
            str(row.get("initiator_type", "")),
        )
    )
    return rows


def should_throttle_connection_group_summary_rows(
    run_payloads: list[dict[str, object]], *, target_filter: set[str]
) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str, str, str], list[dict[str, object]]] = defaultdict(list)
    for payload in run_payloads:
        for row in should_throttle_connection_group_group_rows_for_payload(payload):
            target = str(row["target"])
            if target_filter and target not in target_filter:
                continue
            grouped[
                (
                    target,
                    str(row["profile"]),
                    str(row["priority_header"]),
                    str(row["initiator_type"]),
                )
            ].append(row)

    rows: list[dict[str, object]] = []
    for (target, profile, priority_header, initiator_type), group_rows in sorted(
        grouped.items()
    ):
        rows.append(
            {
                "target": target,
                "profile": profile,
                "priority_header": priority_header,
                "initiator_type": initiator_type,
                "runs": len(group_rows),
                "median_shared_connection_resources": median(
                    row.get("shared_connection_resources") for row in group_rows
                ),
                "median_shared_connection_pairs": median(
                    row.get("median_shared_connection_pairs") for row in group_rows
                ),
                "median_request_to_response_start_ms": median(
                    row.get("median_request_to_response_start_ms")
                    for row in group_rows
                ),
                "median_max_shared_pair_covered_ms": median(
                    row.get("median_max_shared_pair_covered_ms")
                    for row in group_rows
                ),
                "top_shared_connection_pairs": ", ".join(
                    top_names_from_score_map(
                        summed_score_maps(
                            group_rows,
                            score_map_key="shared_connection_pair_scores",
                        ),
                        limit=4,
                    )
                ),
                "top_shared_connection_resources": ", ".join(
                    top_names_from_score_map(
                        summed_score_maps(
                            group_rows,
                            score_map_key="shared_connection_resource_scores",
                        ),
                        limit=4,
                    )
                ),
            }
        )
    rows.sort(
        key=lambda row: (
            -(numeric(row.get("median_max_shared_pair_covered_ms")) or 0.0),
            -(numeric(row.get("median_shared_connection_resources")) or 0.0),
            -(numeric(row.get("median_shared_connection_pairs")) or 0.0),
            str(row.get("priority_header", "")),
            str(row.get("initiator_type", "")),
        )
    )
    return rows


def worst_run_rows(
    run_payloads: list[dict[str, object]], *, target_filter: set[str], limit: int
) -> list[dict[str, object]]:
    rows = []
    for payload in run_payloads:
        row = queue_row(payload)
        if row is None:
            continue
        if target_filter and str(row["target"]) not in target_filter:
            continue
        rows.append(row)
    rows.sort(
        key=lambda row: (
            numeric(row.get("max_queue_ms")) or -1.0,
            numeric(row.get("combined_wall_seconds")) or -1.0,
            numeric(row.get("elapsed_ms")) or -1.0,
        ),
        reverse=True,
    )
    return rows[:limit]


def queue_row(payload: dict[str, object]) -> dict[str, object] | None:
    target = payload.get("target")
    profile = payload.get("profile_name")
    cycle = payload.get("cycle")
    browser_run = first_browser_run(payload)
    if not isinstance(target, str) or not isinstance(profile, str):
        return None
    if not isinstance(browser_run, dict):
        return None
    queue_metrics = same_origin_queue_metrics(browser_run, target)
    mozlog_metrics = parent_mozlog_counts(browser_run)
    phase_metrics = navigation_phase_metrics(browser_run)
    return {
        "target": target,
        "profile": profile,
        "cycle": cycle,
        "combined_wall_seconds": payload_combined_wall_seconds(payload),
        "elapsed_ms": browser_run.get("elapsed_ms"),
        "load_ms": browser_run.get("load_ms"),
        **queue_metrics,
        **mozlog_metrics,
        **phase_metrics,
        "top_queued_resources": ", ".join(
            name
            for name in queue_metrics.get("top_queued_resource_names", [])
            if isinstance(name, str)
        ),
        "source_path": payload.get("_path"),
    }


def phase_row(payload: dict[str, object]) -> dict[str, object] | None:
    target = payload.get("target")
    profile = payload.get("profile_name")
    browser_run = first_browser_run(payload)
    if not isinstance(target, str) or not isinstance(profile, str):
        return None
    if not isinstance(browser_run, dict):
        return None
    before = payload.get("benchmark_service_state_before_browser")
    before_bootstrap = service_bootstrap_progress(before)
    before_gc_count = service_general_circuit_count(before)
    return {
        "target": target,
        "profile": profile,
        "combined_wall_seconds": payload_combined_wall_seconds(payload),
        **navigation_phase_metrics(browser_run),
        "before_bootstrap_progress": before_bootstrap,
        "before_gc_count": before_gc_count,
        "before_general_count": service_general_circuit_purpose_count(before, "GENERAL"),
        "before_conflux_count": service_general_circuit_purpose_count(
            before,
            "CONFLUX_LINKED",
        ),
        "before_has_built_gc": service_has_built_general_circuit(before),
    }


def timeline_row(payload: dict[str, object]) -> dict[str, object] | None:
    target = payload.get("target")
    profile = payload.get("profile_name")
    timeline = payload.get("benchmark_general_circuit_timeline")
    if not isinstance(target, str) or not isinstance(profile, str):
        return None
    if not isinstance(timeline, dict):
        return None
    samples = timeline.get("samples")
    if not isinstance(samples, list) or not samples:
        return None
    return {
        "target": target,
        "profile": profile,
        "first_conflux_seconds": first_purpose_count_seconds(
            samples,
            purpose="CONFLUX_LINKED",
        ),
        "max_general_count": max_purpose_count(samples, purpose="GENERAL"),
        "max_conflux_count": max_purpose_count(samples, purpose="CONFLUX_LINKED"),
        "sample_count": len(samples),
        "timeline_duration_seconds": max_numeric(
            sample.get("elapsed_seconds")
            for sample in samples
            if isinstance(sample, dict)
        ),
    }


def stream_timeline_row(payload: dict[str, object]) -> dict[str, object] | None:
    target = payload.get("target")
    profile = payload.get("profile_name")
    timeline = payload.get("benchmark_stream_isolation_timeline")
    if not isinstance(target, str) or not isinstance(profile, str):
        return None
    if not isinstance(timeline, dict):
        return None
    samples = timeline.get("samples")
    if not isinstance(samples, list) or not samples:
        return None
    typed_samples = [sample for sample in samples if isinstance(sample, dict)]
    peak_sample = max(
        typed_samples,
        key=lambda sample: (
            numeric(sample.get("user_stream_count")) or 0.0,
            numeric(sample.get("max_streams_per_circuit")) or 0.0,
            numeric(sample.get("single_circuit_share_pct")) or 0.0,
            -(numeric(sample.get("unique_circuit_count")) or 0.0),
        ),
    )
    return {
        "target": target,
        "profile": profile,
        "sample_count": len(typed_samples),
        "active_sample_count": sum(
            1
            for sample in typed_samples
            if (numeric(sample.get("user_stream_count")) or 0.0) > 0.0
        ),
        "max_user_stream_count": max(
            [(numeric(sample.get("user_stream_count")) or 0.0) for sample in typed_samples],
            default=0.0,
        ),
        "max_unique_circuit_count": max(
            [
                (numeric(sample.get("unique_circuit_count")) or 0.0)
                for sample in typed_samples
            ],
            default=0.0,
        ),
        "max_streams_per_circuit": max(
            [
                (numeric(sample.get("max_streams_per_circuit")) or 0.0)
                for sample in typed_samples
            ],
            default=0.0,
        ),
        "max_single_circuit_share_pct": max(
            [
                (numeric(sample.get("single_circuit_share_pct")) or 0.0)
                for sample in typed_samples
            ],
            default=0.0,
        ),
        "peak_user_stream_count": numeric(peak_sample.get("user_stream_count")) or 0.0,
        "peak_unique_circuit_count": (
            numeric(peak_sample.get("unique_circuit_count")) or 0.0
        ),
        "peak_streams_per_circuit": (
            numeric(peak_sample.get("max_streams_per_circuit")) or 0.0
        ),
        "peak_single_circuit_share_pct": (
            numeric(peak_sample.get("single_circuit_share_pct")) or 0.0
        ),
    }


def saturation_row(payload: dict[str, object]) -> dict[str, object] | None:
    target = payload.get("target")
    profile = payload.get("profile_name")
    browser_run = first_browser_run(payload)
    if not isinstance(target, str) or not isinstance(profile, str):
        return None
    if not isinstance(browser_run, dict):
        return None
    return {
        "target": target,
        "profile": profile,
        **same_origin_queue_saturation_metrics(browser_run, target),
    }


def queue_cause_row(payload: dict[str, object]) -> dict[str, object] | None:
    target = payload.get("target")
    profile = payload.get("profile_name")
    browser_run = first_browser_run(payload)
    if not isinstance(target, str) or not isinstance(profile, str):
        return None
    if not isinstance(browser_run, dict):
        return None
    return {
        "target": target,
        "profile": profile,
        **same_origin_queue_cause_metrics(browser_run, target),
    }


def blocker_release_row(payload: dict[str, object]) -> dict[str, object] | None:
    target = payload.get("target")
    profile = payload.get("profile_name")
    browser_run = first_browser_run(payload)
    if not isinstance(target, str) or not isinstance(profile, str):
        return None
    if not isinstance(browser_run, dict):
        return None
    return {
        "target": target,
        "profile": profile,
        **same_origin_queue_blocker_release_metrics(browser_run, target),
    }


def request_order_probe_row(payload: dict[str, object]) -> dict[str, object] | None:
    target = payload.get("target")
    profile = payload.get("profile_name")
    browser_run = first_browser_run(payload)
    if not isinstance(target, str) or not isinstance(profile, str):
        return None
    if not isinstance(browser_run, dict):
        return None
    if not browser_activity_probe_rows(browser_run):
        return None
    return {
        "target": target,
        "profile": profile,
        **same_origin_request_order_probe_metrics(browser_run, target),
    }


def request_priority_group_rows_for_payload(
    payload: dict[str, object]
) -> list[dict[str, object]]:
    target = payload.get("target")
    profile = payload.get("profile_name")
    browser_run = first_browser_run(payload)
    if not isinstance(target, str) or not isinstance(profile, str):
        return []
    if not isinstance(browser_run, dict):
        return []
    rows = same_origin_request_priority_group_rows(browser_run, target)
    return [
        {
            "target": target,
            "profile": profile,
            **row,
        }
        for row in rows
    ]


def should_throttle_priority_group_rows_for_payload(
    payload: dict[str, object]
) -> list[dict[str, object]]:
    target = payload.get("target")
    profile = payload.get("profile_name")
    browser_run = first_browser_run(payload)
    if not isinstance(target, str) or not isinstance(profile, str):
        return []
    if not isinstance(browser_run, dict):
        return []
    rows = same_origin_should_throttle_priority_group_rows(browser_run, target)
    return [
        {
            "target": target,
            "profile": profile,
            **row,
        }
        for row in rows
    ]


def should_throttle_timing_group_rows_for_payload(
    payload: dict[str, object]
) -> list[dict[str, object]]:
    target = payload.get("target")
    profile = payload.get("profile_name")
    browser_run = first_browser_run(payload)
    if not isinstance(target, str) or not isinstance(profile, str):
        return []
    if not isinstance(browser_run, dict):
        return []
    rows = same_origin_should_throttle_timing_group_rows(browser_run, target)
    return [
        {
            "target": target,
            "profile": profile,
            **row,
        }
        for row in rows
    ]


def should_throttle_wave_group_rows_for_payload(
    payload: dict[str, object]
) -> list[dict[str, object]]:
    target = payload.get("target")
    profile = payload.get("profile_name")
    browser_run = first_browser_run(payload)
    if not isinstance(target, str) or not isinstance(profile, str):
        return []
    if not isinstance(browser_run, dict):
        return []
    rows = same_origin_should_throttle_wave_group_rows(browser_run, target)
    return [
        {
            "target": target,
            "profile": profile,
            **row,
        }
        for row in rows
    ]


def should_throttle_pre_request_blocker_group_rows_for_payload(
    payload: dict[str, object]
) -> list[dict[str, object]]:
    target = payload.get("target")
    profile = payload.get("profile_name")
    browser_run = first_browser_run(payload)
    if not isinstance(target, str) or not isinstance(profile, str):
        return []
    if not isinstance(browser_run, dict):
        return []
    rows = same_origin_should_throttle_pre_request_blocker_group_rows(browser_run, target)
    return [
        {
            "target": target,
            "profile": profile,
            **row,
        }
        for row in rows
    ]


def should_throttle_pre_request_remaining_group_rows_for_payload(
    payload: dict[str, object]
) -> list[dict[str, object]]:
    target = payload.get("target")
    profile = payload.get("profile_name")
    browser_run = first_browser_run(payload)
    if not isinstance(target, str) or not isinstance(profile, str):
        return []
    if not isinstance(browser_run, dict):
        return []
    rows = same_origin_should_throttle_pre_request_remaining_group_rows(
        browser_run, target
    )
    return [
        {
            "target": target,
            "profile": profile,
            **row,
        }
        for row in rows
    ]


def should_throttle_pre_request_phase_group_rows_for_payload(
    payload: dict[str, object]
) -> list[dict[str, object]]:
    target = payload.get("target")
    profile = payload.get("profile_name")
    browser_run = first_browser_run(payload)
    if not isinstance(target, str) or not isinstance(profile, str):
        return []
    if not isinstance(browser_run, dict):
        return []
    rows = same_origin_should_throttle_pre_request_phase_group_rows(
        browser_run, target
    )
    return [
        {
            "target": target,
            "profile": profile,
            **row,
        }
        for row in rows
    ]


def should_throttle_pre_request_phase_pair_group_rows_for_payload(
    payload: dict[str, object]
) -> list[dict[str, object]]:
    target = payload.get("target")
    profile = payload.get("profile_name")
    browser_run = first_browser_run(payload)
    if not isinstance(target, str) or not isinstance(profile, str):
        return []
    if not isinstance(browser_run, dict):
        return []
    rows = same_origin_should_throttle_pre_request_phase_pair_group_rows(
        browser_run, target
    )
    return [
        {
            "target": target,
            "profile": profile,
            **row,
        }
        for row in rows
    ]


def should_throttle_connection_group_group_rows_for_payload(
    payload: dict[str, object]
) -> list[dict[str, object]]:
    target = payload.get("target")
    profile = payload.get("profile_name")
    browser_run = first_browser_run(payload)
    if not isinstance(target, str) or not isinstance(profile, str):
        return []
    if not isinstance(browser_run, dict):
        return []
    rows = same_origin_should_throttle_connection_group_group_rows(
        browser_run, target
    )
    return [
        {
            "target": target,
            "profile": profile,
            **row,
        }
        for row in rows
    ]


def first_browser_run(payload: dict[str, object]) -> dict[str, object] | None:
    benchmarks = payload.get("benchmarks")
    if not isinstance(benchmarks, dict):
        return None
    target = payload.get("target")
    target_payload = benchmarks.get(target) if isinstance(target, str) else None
    if not isinstance(target_payload, dict):
        return None
    runs = target_payload.get("runs")
    if not isinstance(runs, list) or not runs:
        return None
    run = runs[0]
    return run if isinstance(run, dict) else None


def same_origin_queue_metrics(
    browser_run: dict[str, object], target_url: str
) -> dict[str, object]:
    target_host = urlsplit(target_url).hostname
    resources = performance_resources(browser_run)
    rows: list[tuple[float, str]] = []
    for resource in resources:
        name = resource.get("name")
        if not isinstance(name, str):
            continue
        if urlsplit(name).hostname != target_host:
            continue
        fetch_start = numeric(resource.get("fetchStart"))
        request_start = numeric(resource.get("requestStart"))
        if fetch_start is None or request_start is None:
            continue
        rows.append((max(0.0, request_start - fetch_start), name))

    queue_values = [queue_ms for queue_ms, _ in rows]
    sorted_rows = sorted(rows, reverse=True)
    return {
        "same_origin_resources": len(rows),
        "max_queue_ms": round(max(queue_values), 3) if queue_values else None,
        "queued_gt_2000ms": sum(1 for value in queue_values if value > 2000.0),
        "queued_gt_5000ms": sum(1 for value in queue_values if value > 5000.0),
        "queued_gt_10000ms": sum(1 for value in queue_values if value > 10000.0),
        "top_queued_resource_names": [
            resource_name_label(name) for _, name in sorted_rows[:4]
        ],
    }


def same_origin_queue_saturation_metrics(
    browser_run: dict[str, object], target_url: str
) -> dict[str, object]:
    target_host = urlsplit(target_url).hostname
    resources = performance_resources(browser_run)
    dom_loaded = navigation_value(browser_run, "domContentLoadedEventEnd")
    rows: list[dict[str, object]] = []
    tail_rows: list[tuple[float, str]] = []
    for resource in resources:
        name = resource.get("name")
        if not isinstance(name, str):
            continue
        if urlsplit(name).hostname != target_host:
            continue
        fetch_to_request = subtract_fields(resource, "fetchStart", "requestStart")
        slot_depth = same_origin_protocol_slot_depth_at_request(resource, resources)
        if fetch_to_request is not None:
            rows.append(
                {
                    "name": name,
                    "fetch_to_request_ms": fetch_to_request,
                    "slot_depth_at_request": slot_depth,
                }
            )
        response_end = numeric(resource.get("responseEnd"))
        if dom_loaded is not None and response_end is not None and response_end > dom_loaded:
            tail_rows.append((response_end - dom_loaded, name))

    slot_depths = [
        value
        for value in (
            numeric(row.get("slot_depth_at_request")) for row in rows
        )
        if value is not None
    ]
    tail_values = [value for value, _name in tail_rows]
    sorted_tail_rows = sorted(tail_rows, reverse=True)
    return {
        "queued_gt_1000ms": sum(
            1
            for row in rows
            if (numeric(row.get("fetch_to_request_ms")) or 0.0) > 1000.0
        ),
        "slot_depth_6_queued_gt_1000ms": sum(
            1
            for row in rows
            if (numeric(row.get("fetch_to_request_ms")) or 0.0) > 1000.0
            and (numeric(row.get("slot_depth_at_request")) or 0.0) >= 6.0
        ),
        "max_slot_depth_at_request": round(max(slot_depths), 3)
        if slot_depths
        else None,
        "tail_after_dom_gt_1000ms": sum(1 for value in tail_values if value > 1000.0),
        "max_tail_after_dom_ms": round(max(tail_values), 3) if tail_values else None,
        "top_tail_resource_names": [
            resource_name_label(name) for _value, name in sorted_tail_rows[:4]
        ],
    }


def same_origin_queue_cause_metrics(
    browser_run: dict[str, object], target_url: str
) -> dict[str, object]:
    rows = same_origin_queue_cause_rows(browser_run, target_url)
    filtered_rows = [
        row
        for row in rows
        if (numeric(row.get("fetch_to_request_ms")) or 0.0) > 1000.0
    ]
    blocked_chain_scores: dict[str, float] = {}
    blocker_resource_scores: dict[str, float] = {}
    unexplained_resource_scores: dict[str, float] = {}
    for row in filtered_rows:
        resource = row.get("resource")
        if not isinstance(resource, str):
            continue
        label = resource_name_label(resource)
        previous_resource = row.get("previous_resource")
        blocked_ms = numeric(row.get("queue_blocked_by_previous_response_ms")) or 0.0
        if isinstance(previous_resource, str) and blocked_ms > 0.0:
            previous_label = resource_name_label(previous_resource)
            chain_label = f"{previous_label} -> {label}"
            blocked_chain_scores[chain_label] = max(
                blocked_chain_scores.get(chain_label, 0.0),
                blocked_ms,
            )
            blocker_resource_scores[previous_label] = max(
                blocker_resource_scores.get(previous_label, 0.0),
                blocked_ms,
            )
        unexplained_ms = numeric(row.get("queue_unexplained_after_previous_ms")) or 0.0
        unexplained_resource_scores[label] = max(
            unexplained_resource_scores.get(label, 0.0),
            unexplained_ms,
        )
    return {
        "queued_gt_1000ms": len(filtered_rows),
        "total_blocked_ms": round(
            sum(numeric(row.get("queue_blocked_by_previous_response_ms")) or 0.0 for row in filtered_rows),
            3,
        ),
        "total_unexplained_ms": round(
            sum(numeric(row.get("queue_unexplained_after_previous_ms")) or 0.0 for row in filtered_rows),
            3,
        ),
        "mostly_blocked_rows": sum(
            1 for row in filtered_rows if row.get("queue_cause_hint") == "queued behind previous response"
        ),
        "mostly_after_previous_rows": sum(
            1 for row in filtered_rows if row.get("queue_cause_hint") == "queue mostly after previous response"
        ),
        "max_blocked_ms": max_numeric(
            row.get("queue_blocked_by_previous_response_ms") for row in filtered_rows
        ),
        "blocked_chain_scores": blocked_chain_scores,
        "blocker_resource_scores": blocker_resource_scores,
        "max_unexplained_ms": max_numeric(
            row.get("queue_unexplained_after_previous_ms") for row in filtered_rows
        ),
        "unexplained_resource_scores": unexplained_resource_scores,
        "top_unexplained_resource_names": [
            name
            for name, _value in sorted(
                unexplained_resource_scores.items(),
                key=lambda item: (-item[1], item[0]),
            )[:4]
        ],
    }


def same_origin_queue_blocker_release_metrics(
    browser_run: dict[str, object], target_url: str
) -> dict[str, object]:
    target_host = urlsplit(target_url).hostname
    resources = performance_resources(browser_run)
    rows: list[dict[str, object]] = []
    for resource in resources:
        name = resource.get("name")
        if not isinstance(name, str):
            continue
        if urlsplit(name).hostname != target_host:
            continue
        queue_ms = subtract_fields(resource, "fetchStart", "requestStart")
        if queue_ms is None or queue_ms <= 1000.0:
            continue
        request_start = numeric(resource.get("requestStart"))
        if request_start is None:
            continue
        blockers = same_origin_protocol_active_resources_at_request(resource, resources)
        blocker_rows = [
            {
                "resource": blocker.get("name"),
                "remaining_ms": subtract_numeric(
                    blocker.get("responseEnd"),
                    request_start,
                ),
                "wait_remaining_ms": blocker_wait_remaining_at_request(
                    blocker, request_start
                ),
                "receive_remaining_ms": blocker_receive_remaining_at_request(
                    blocker,
                    request_start,
                ),
            }
            for blocker in blockers
        ]
        max_remaining = max_numeric(
            blocker_row.get("remaining_ms") for blocker_row in blocker_rows
        )
        max_wait = max_numeric(
            blocker_row.get("wait_remaining_ms") for blocker_row in blocker_rows
        )
        max_receive = max_numeric(
            blocker_row.get("receive_remaining_ms") for blocker_row in blocker_rows
        )
        rows.append(
            {
                "queued_resource": name,
                "fetch_to_request_ms": queue_ms,
                "slot_depth_at_request": same_origin_protocol_slot_depth_at_request(
                    resource, resources
                ),
                "active_blockers": len(blocker_rows),
                "max_blocker_remaining_ms": max_remaining,
                "max_blocker_wait_remaining_ms": max_wait,
                "max_blocker_receive_remaining_ms": max_receive,
                "queue_minus_max_blocker_left_ms": subtract_numeric(
                    queue_ms, max_remaining
                ),
            }
        )

    sorted_rows = sorted(
        rows,
        key=lambda row: numeric(row.get("fetch_to_request_ms")) or 0.0,
        reverse=True,
    )
    return {
        "queued_gt_1000ms": len(rows),
        "rows_with_active_blockers": sum(
            1 for row in rows if (numeric(row.get("active_blockers")) or 0.0) > 0.0
        ),
        "receive_dominant_rows": sum(
            1
            for row in rows
            if (numeric(row.get("max_blocker_receive_remaining_ms")) or 0.0)
            >= (numeric(row.get("max_blocker_wait_remaining_ms")) or 0.0)
            and (numeric(row.get("max_blocker_receive_remaining_ms")) or 0.0) > 0.0
        ),
        "wait_dominant_rows": sum(
            1
            for row in rows
            if (numeric(row.get("max_blocker_wait_remaining_ms")) or 0.0)
            > (numeric(row.get("max_blocker_receive_remaining_ms")) or 0.0)
        ),
        "blockers_left_500ms": sum(
            1
            for row in rows
            if (value := numeric(row.get("max_blocker_remaining_ms"))) is not None
            and value <= 500.0
        ),
        "median_max_blocker_remaining_ms": median(
            row.get("max_blocker_remaining_ms") for row in rows
        ),
        "median_queue_minus_max_blocker_left_ms": median(
            row.get("queue_minus_max_blocker_left_ms") for row in rows
        ),
        "median_max_blocker_wait_left_ms": median(
            row.get("max_blocker_wait_remaining_ms") for row in rows
        ),
        "median_max_blocker_receive_left_ms": median(
            row.get("max_blocker_receive_remaining_ms") for row in rows
        ),
        "max_queue_ms": max_numeric(row.get("fetch_to_request_ms") for row in rows),
        "top_queued_resource_names": [
            resource_name_label(str(row.get("queued_resource", "")))
            for row in sorted_rows[:4]
            if row.get("queued_resource")
        ],
    }


def same_origin_request_order_probe_metrics(
    browser_run: dict[str, object], target_url: str
) -> dict[str, object]:
    target_host = urlsplit(target_url).hostname
    first_activity_by_uri = first_activity_relative_ms_by_uri(browser_run)
    rows: list[dict[str, object]] = []
    queued_gt_1000ms = 0
    for resource in performance_resources(browser_run):
        name = resource.get("name")
        if not isinstance(name, str):
            continue
        if urlsplit(name).hostname != target_host:
            continue
        fetch_start = numeric(resource.get("fetchStart"))
        request_start = numeric(resource.get("requestStart"))
        if fetch_start is None or request_start is None:
            continue
        queue_ms = round(max(0.0, request_start - fetch_start), 3)
        if queue_ms <= 1000.0:
            continue
        queued_gt_1000ms += 1
        first_activity_ms = first_activity_by_uri.get(name)
        if first_activity_ms is None:
            continue
        fetch_to_probe_ms = round(max(0.0, first_activity_ms - fetch_start), 3)
        probe_to_request_ms = round(max(0.0, request_start - first_activity_ms), 3)
        rows.append(
            {
                "resource": name,
                "queue_ms": queue_ms,
                "fetch_to_probe_ms": fetch_to_probe_ms,
                "probe_to_request_ms": probe_to_request_ms,
            }
        )

    request_order_resource_scores: dict[str, float] = {}
    late_discovery_resource_scores: dict[str, float] = {}
    for row in rows:
        resource_label = resource_name_label(str(row.get("resource", "")))
        request_order_resource_scores[resource_label] = max(
            request_order_resource_scores.get(resource_label, 0.0),
            numeric(row.get("probe_to_request_ms")) or 0.0,
        )
        late_discovery_resource_scores[resource_label] = max(
            late_discovery_resource_scores.get(resource_label, 0.0),
            numeric(row.get("fetch_to_probe_ms")) or 0.0,
        )

    return {
        "queued_gt_1000ms": queued_gt_1000ms,
        "rows_with_probe": len(rows),
        "request_order_dominant_rows": sum(
            1
            for row in rows
            if (numeric(row.get("probe_to_request_ms")) or 0.0)
            >= (numeric(row.get("queue_ms")) or 0.0) * 0.75
        ),
        "late_discovered_gt_1000ms_rows": sum(
            1
            for row in rows
            if (numeric(row.get("fetch_to_probe_ms")) or 0.0) > 1000.0
        ),
        "median_fetch_to_probe_ms": median(
            row.get("fetch_to_probe_ms") for row in rows
        ),
        "median_probe_to_request_ms": median(
            row.get("probe_to_request_ms") for row in rows
        ),
        "request_order_resource_scores": request_order_resource_scores,
        "late_discovery_resource_scores": late_discovery_resource_scores,
    }


def same_origin_request_priority_group_rows(
    browser_run: dict[str, object], target_url: str
) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in same_origin_request_priority_rows(browser_run, target_url):
        grouped[
            (
                str(row.get("priority_header", "")),
                str(row.get("initiator_type", "")),
            )
        ].append(row)

    rows: list[dict[str, object]] = []
    for (priority_header, initiator_type), group_rows in grouped.items():
        sorted_rows = sorted(
            group_rows,
            key=lambda row: (
                numeric(row.get("queue_ms")) or 0.0,
                str(row.get("resource", "")),
            ),
            reverse=True,
        )
        rows.append(
            {
                "priority_header": priority_header,
                "initiator_type": initiator_type,
                "queued_gt_1000ms": len(group_rows),
                "request_order_dominant_rows": sum(
                    1
                    for row in group_rows
                    if row.get("request_order_dominant") is True
                ),
                "late_discovered_gt_1000ms_rows": sum(
                    1
                    for row in group_rows
                    if row.get("late_discovered_gt_1000ms") is True
                ),
                "median_queue_ms": median(row.get("queue_ms") for row in group_rows),
                "median_fetch_to_probe_ms": median(
                    row.get("fetch_to_probe_ms") for row in group_rows
                ),
                "median_probe_to_request_ms": median(
                    row.get("probe_to_request_ms") for row in group_rows
                ),
                "max_queue_ms": max_numeric(row.get("queue_ms") for row in group_rows),
                "top_resource_names": [
                    resource_name_label(str(row.get("resource", "")))
                    for row in sorted_rows[:4]
                    if row.get("resource")
                ],
            }
        )
    rows.sort(
        key=lambda row: (
            numeric(row.get("queued_gt_1000ms")) or 0.0,
            numeric(row.get("median_probe_to_request_ms")) or 0.0,
            numeric(row.get("median_queue_ms")) or 0.0,
            str(row.get("priority_header", "")),
            str(row.get("initiator_type", "")),
        ),
        reverse=True,
    )
    return rows


def same_origin_should_throttle_priority_group_rows(
    browser_run: dict[str, object], target_url: str
) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in same_origin_should_throttle_rows(browser_run, target_url):
        grouped[
            (
                str(row.get("priority_header", "")),
                str(row.get("initiator_type", "")),
            )
        ].append(row)

    rows: list[dict[str, object]] = []
    for (priority_header, initiator_type), group_rows in grouped.items():
        sorted_rows = sorted(
            group_rows,
            key=lambda row: (
                numeric(row.get("should_throttle_events")) or 0.0,
                numeric(row.get("queue_ms")) or 0.0,
                str(row.get("resource", "")),
            ),
            reverse=True,
        )
        rows.append(
            {
                "priority_header": priority_header,
                "initiator_type": initiator_type,
                "resources": len(group_rows),
                "should_throttle_events": round(
                    sum(
                        numeric(row.get("should_throttle_events")) or 0.0
                        for row in group_rows
                    ),
                    3,
                ),
                "request_order_dominant_resources": sum(
                    1
                    for row in group_rows
                    if row.get("request_order_dominant") is True
                ),
                "median_queue_ms": median(row.get("queue_ms") for row in group_rows),
                "max_should_throttle_events": max_numeric(
                    row.get("should_throttle_events") for row in group_rows
                ),
                "top_resource_names": [
                    resource_name_label(str(row.get("resource", "")))
                    for row in sorted_rows[:4]
                    if row.get("resource")
                ],
            }
        )
    rows.sort(
        key=lambda row: (
            numeric(row.get("should_throttle_events")) or 0.0,
            numeric(row.get("resources")) or 0.0,
            numeric(row.get("median_queue_ms")) or 0.0,
            str(row.get("priority_header", "")),
            str(row.get("initiator_type", "")),
        ),
        reverse=True,
    )
    return rows


def same_origin_should_throttle_timing_group_rows(
    browser_run: dict[str, object], target_url: str
) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in same_origin_should_throttle_timing_rows(browser_run, target_url):
        grouped[
            (
                str(row.get("priority_header", "")),
                str(row.get("initiator_type", "")),
            )
        ].append(row)

    rows: list[dict[str, object]] = []
    for (priority_header, initiator_type), group_rows in grouped.items():
        sorted_rows = sorted(
            group_rows,
            key=lambda row: (
                numeric(row.get("request_after_first_should_throttle_ms")) or 0.0,
                numeric(row.get("should_throttle_events")) or 0.0,
                str(row.get("resource", "")),
            ),
            reverse=True,
        )
        rows.append(
            {
                "priority_header": priority_header,
                "initiator_type": initiator_type,
                "resources": len(group_rows),
                "should_throttle_events": round(
                    sum(
                        numeric(row.get("should_throttle_events")) or 0.0
                        for row in group_rows
                    ),
                    3,
                ),
                "median_first_should_throttle_ms": median(
                    row.get("first_should_throttle_ms") for row in group_rows
                ),
                "median_fetch_after_first_should_throttle_ms": median(
                    row.get("fetch_after_first_should_throttle_ms")
                    for row in group_rows
                ),
                "median_request_after_first_should_throttle_ms": median(
                    row.get("request_after_first_should_throttle_ms")
                    for row in group_rows
                ),
                "max_request_after_first_should_throttle_ms": max_numeric(
                    row.get("request_after_first_should_throttle_ms")
                    for row in group_rows
                ),
                "top_resource_names": [
                    resource_name_label(str(row.get("resource", "")))
                    for row in sorted_rows[:4]
                    if row.get("resource")
                ],
            }
        )
    rows.sort(
        key=lambda row: (
            -(numeric(row.get("median_request_after_first_should_throttle_ms")) or 0.0),
            -(numeric(row.get("should_throttle_events")) or 0.0),
            numeric(row.get("median_first_should_throttle_ms"))
            if numeric(row.get("median_first_should_throttle_ms")) is not None
            else float("inf"),
            str(row.get("priority_header", "")),
            str(row.get("initiator_type", "")),
        )
    )
    return rows


def same_origin_should_throttle_wave_group_rows(
    browser_run: dict[str, object], target_url: str
) -> list[dict[str, object]]:
    timing_rows = same_origin_should_throttle_timing_rows(browser_run, target_url)
    first_wave_ms = min_numeric(
        row.get("first_should_throttle_ms") for row in timing_rows
    )
    if first_wave_ms is None:
        return []

    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in timing_rows:
        grouped[
            (
                str(row.get("priority_header", "")),
                str(row.get("initiator_type", "")),
            )
        ].append(
            {
                **row,
                "wave_offset_ms": subtract_numeric(
                    row.get("first_should_throttle_ms"),
                    first_wave_ms,
                ),
            }
        )

    rows: list[dict[str, object]] = []
    for (priority_header, initiator_type), group_rows in grouped.items():
        sorted_rows = sorted(
            group_rows,
            key=lambda row: (
                numeric(row.get("wave_offset_ms"))
                if numeric(row.get("wave_offset_ms")) is not None
                else float("inf"),
                -(numeric(row.get("should_throttle_events")) or 0.0),
                str(row.get("resource", "")),
            ),
        )
        earliest_wave_offset_ms = min_numeric(
            row.get("wave_offset_ms") for row in group_rows
        )
        rows.append(
            {
                "priority_header": priority_header,
                "initiator_type": initiator_type,
                "resources": len(group_rows),
                "should_throttle_events": round(
                    sum(
                        numeric(row.get("should_throttle_events")) or 0.0
                        for row in group_rows
                    ),
                    3,
                ),
                "earliest_wave_offset_ms": earliest_wave_offset_ms,
                "median_wave_offset_ms": median(
                    row.get("wave_offset_ms") for row in group_rows
                ),
                "median_request_after_first_should_throttle_ms": median(
                    row.get("request_after_first_should_throttle_ms")
                    for row in group_rows
                ),
                "negative_earliest_wave_offset_ms": (
                    -earliest_wave_offset_ms
                    if earliest_wave_offset_ms is not None
                    else None
                ),
                "top_resource_names": [
                    resource_name_label(str(row.get("resource", "")))
                    for row in sorted_rows[:4]
                    if row.get("resource")
                ],
            }
        )
    rows.sort(
        key=lambda row: (
            numeric(row.get("earliest_wave_offset_ms"))
            if numeric(row.get("earliest_wave_offset_ms")) is not None
            else float("inf"),
            numeric(row.get("median_wave_offset_ms"))
            if numeric(row.get("median_wave_offset_ms")) is not None
            else float("inf"),
            -(numeric(row.get("should_throttle_events")) or 0.0),
            str(row.get("priority_header", "")),
            str(row.get("initiator_type", "")),
        )
    )
    return rows


def same_origin_should_throttle_pre_request_blocker_group_rows(
    browser_run: dict[str, object], target_url: str
) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in same_origin_should_throttle_pre_request_blocker_rows(
        browser_run, target_url
    ):
        grouped[
            (
                str(row.get("priority_header", "")),
                str(row.get("initiator_type", "")),
            )
        ].append(row)

    rows: list[dict[str, object]] = []
    for (priority_header, initiator_type), group_rows in grouped.items():
        sorted_rows = sorted(
            group_rows,
            key=lambda row: (
                numeric(row.get("request_after_first_should_throttle_ms")) or 0.0,
                numeric(row.get("active_blockers")) or 0.0,
                str(row.get("resource", "")),
            ),
            reverse=True,
        )
        rows.append(
            {
                "priority_header": priority_header,
                "initiator_type": initiator_type,
                "resources": len(group_rows),
                "median_fetch_after_first_should_throttle_ms": median(
                    row.get("fetch_after_first_should_throttle_ms")
                    for row in group_rows
                ),
                "median_request_after_first_should_throttle_ms": median(
                    row.get("request_after_first_should_throttle_ms")
                    for row in group_rows
                ),
                "median_active_blockers": median(
                    row.get("active_blockers") for row in group_rows
                ),
                "median_same_group_blockers": median(
                    row.get("same_group_blockers") for row in group_rows
                ),
                "max_request_after_first_should_throttle_ms": max_numeric(
                    row.get("request_after_first_should_throttle_ms")
                    for row in group_rows
                ),
                "blocker_group_scores": summed_score_maps(
                    group_rows,
                    score_map_key="blocker_group_scores",
                ),
                "resource_scores": {
                    resource_name_label(str(row.get("resource", ""))): (
                        numeric(row.get("request_after_first_should_throttle_ms"))
                        or 0.0
                    )
                    for row in group_rows
                    if row.get("resource")
                },
                "top_resource_names": [
                    resource_name_label(str(row.get("resource", "")))
                    for row in sorted_rows[:4]
                    if row.get("resource")
                ],
            }
        )
    rows.sort(
        key=lambda row: (
            -(numeric(row.get("median_request_after_first_should_throttle_ms")) or 0.0),
            -(numeric(row.get("resources")) or 0.0),
            -(numeric(row.get("median_active_blockers")) or 0.0),
            str(row.get("priority_header", "")),
            str(row.get("initiator_type", "")),
        )
    )
    return rows


def same_origin_should_throttle_pre_request_remaining_group_rows(
    browser_run: dict[str, object], target_url: str
) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in same_origin_should_throttle_pre_request_remaining_rows(
        browser_run, target_url
    ):
        grouped[
            (
                str(row.get("priority_header", "")),
                str(row.get("initiator_type", "")),
            )
        ].append(row)

    rows: list[dict[str, object]] = []
    for (priority_header, initiator_type), group_rows in grouped.items():
        rows.append(
            {
                "priority_header": priority_header,
                "initiator_type": initiator_type,
                "resources": len(group_rows),
                "median_request_after_first_should_throttle_ms": median(
                    row.get("request_after_first_should_throttle_ms")
                    for row in group_rows
                ),
                "wait_dominant_resources": sum(
                    1 for row in group_rows if row.get("wait_dominant") is True
                ),
                "median_max_wait_remaining_ms": median(
                    row.get("max_wait_remaining_ms") for row in group_rows
                ),
                "median_max_receive_remaining_ms": median(
                    row.get("max_receive_remaining_ms") for row in group_rows
                ),
                "median_sum_wait_remaining_ms": median(
                    row.get("sum_wait_remaining_ms") for row in group_rows
                ),
                "median_sum_receive_remaining_ms": median(
                    row.get("sum_receive_remaining_ms") for row in group_rows
                ),
                "resource_scores": {
                    resource_name_label(str(row.get("resource", ""))): (
                        numeric(row.get("request_after_first_should_throttle_ms"))
                        or 0.0
                    )
                    for row in group_rows
                    if row.get("resource")
                },
            }
        )
    rows.sort(
        key=lambda row: (
            -(numeric(row.get("median_request_after_first_should_throttle_ms")) or 0.0),
            -(numeric(row.get("wait_dominant_resources")) or 0.0),
            -(numeric(row.get("median_sum_wait_remaining_ms")) or 0.0),
            str(row.get("priority_header", "")),
            str(row.get("initiator_type", "")),
        )
    )
    return rows


def same_origin_should_throttle_pre_request_phase_group_rows(
    browser_run: dict[str, object], target_url: str
) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in same_origin_should_throttle_pre_request_phase_rows(
        browser_run, target_url
    ):
        grouped[
            (
                str(row.get("priority_header", "")),
                str(row.get("initiator_type", "")),
            )
        ].append(row)

    rows: list[dict[str, object]] = []
    for (priority_header, initiator_type), group_rows in grouped.items():
        rows.append(
            {
                "priority_header": priority_header,
                "initiator_type": initiator_type,
                "resources": len(group_rows),
                "median_request_after_first_should_throttle_ms": median(
                    row.get("request_after_first_should_throttle_ms")
                    for row in group_rows
                ),
                "response_start_dominant_resources": sum(
                    1
                    for row in group_rows
                    if row.get("response_start_dominant") is True
                ),
                "median_request_to_response_start_ms": median(
                    row.get("request_to_response_start_ms") for row in group_rows
                ),
                "median_response_start_to_response_end_ms": median(
                    row.get("response_start_to_response_end_ms")
                    for row in group_rows
                ),
                "median_throttle_to_response_start_ms": median(
                    row.get("throttle_to_response_start_ms") for row in group_rows
                ),
                "median_throttle_to_response_end_ms": median(
                    row.get("throttle_to_response_end_ms") for row in group_rows
                ),
                "resource_scores": {
                    resource_name_label(str(row.get("resource", ""))): (
                        numeric(row.get("request_to_response_start_ms")) or 0.0
                    )
                    for row in group_rows
                    if row.get("resource")
                },
            }
        )
    rows.sort(
        key=lambda row: (
            -(numeric(row.get("median_request_after_first_should_throttle_ms")) or 0.0),
            -(numeric(row.get("median_request_to_response_start_ms")) or 0.0),
            -(numeric(row.get("response_start_dominant_resources")) or 0.0),
            str(row.get("priority_header", "")),
            str(row.get("initiator_type", "")),
        )
    )
    return rows


def same_origin_should_throttle_pre_request_phase_pair_group_rows(
    browser_run: dict[str, object], target_url: str
) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in same_origin_should_throttle_pre_request_phase_pair_rows(
        browser_run, target_url
    ):
        grouped[
            (
                str(row.get("priority_header", "")),
                str(row.get("initiator_type", "")),
            )
        ].append(row)

    rows: list[dict[str, object]] = []
    for (priority_header, initiator_type), group_rows in grouped.items():
        rows.append(
            {
                "priority_header": priority_header,
                "initiator_type": initiator_type,
                "resources": len(group_rows),
                "response_start_dominant_resources": sum(
                    1
                    for row in group_rows
                    if row.get("response_start_dominant") is True
                ),
                "median_request_to_response_start_ms": median(
                    row.get("request_to_response_start_ms") for row in group_rows
                ),
                "median_max_pair_covered_ms": median(
                    row.get("max_pair_covered_ms") for row in group_rows
                ),
                "blocker_pair_scores": summed_score_maps(
                    group_rows,
                    score_map_key="blocker_pair_scores",
                ),
                "blocker_resource_scores": summed_score_maps(
                    group_rows,
                    score_map_key="blocker_resource_scores",
                ),
                "resource_scores": {
                    resource_name_label(str(row.get("resource", ""))): (
                        numeric(row.get("request_to_response_start_ms")) or 0.0
                    )
                    for row in group_rows
                    if row.get("resource")
                },
            }
        )
    rows.sort(
        key=lambda row: (
            -(numeric(row.get("median_request_to_response_start_ms")) or 0.0),
            -(numeric(row.get("median_max_pair_covered_ms")) or 0.0),
            -(numeric(row.get("response_start_dominant_resources")) or 0.0),
            str(row.get("priority_header", "")),
            str(row.get("initiator_type", "")),
        )
    )
    return rows


def same_origin_should_throttle_connection_group_group_rows(
    browser_run: dict[str, object], target_url: str
) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in same_origin_should_throttle_pre_request_phase_pair_rows(
        browser_run, target_url
    ):
        if not row.get("shared_connection_pair_scores"):
            continue
        grouped[
            (
                str(row.get("priority_header", "")),
                str(row.get("initiator_type", "")),
            )
        ].append(row)

    rows: list[dict[str, object]] = []
    for (priority_header, initiator_type), group_rows in grouped.items():
        rows.append(
            {
                "priority_header": priority_header,
                "initiator_type": initiator_type,
                "shared_connection_resources": len(group_rows),
                "median_shared_connection_pairs": median(
                    row.get("shared_connection_pairs") for row in group_rows
                ),
                "median_request_to_response_start_ms": median(
                    row.get("request_to_response_start_ms") for row in group_rows
                ),
                "median_max_shared_pair_covered_ms": median(
                    row.get("max_shared_pair_covered_ms") for row in group_rows
                ),
                "shared_connection_pair_scores": summed_score_maps(
                    group_rows,
                    score_map_key="shared_connection_pair_scores",
                ),
                "shared_connection_resource_scores": summed_score_maps(
                    group_rows,
                    score_map_key="shared_connection_resource_scores",
                ),
            }
        )
    rows.sort(
        key=lambda row: (
            -(numeric(row.get("median_max_shared_pair_covered_ms")) or 0.0),
            -(numeric(row.get("shared_connection_resources")) or 0.0),
            -(numeric(row.get("median_shared_connection_pairs")) or 0.0),
            str(row.get("priority_header", "")),
            str(row.get("initiator_type", "")),
        )
    )
    return rows


def same_origin_request_priority_rows(
    browser_run: dict[str, object], target_url: str
) -> list[dict[str, object]]:
    target_host = urlsplit(target_url).hostname
    first_activity_rows = first_http_activity_row_by_uri(browser_run)
    rows: list[dict[str, object]] = []
    for resource in performance_resources(browser_run):
        name = resource.get("name")
        if not isinstance(name, str):
            continue
        if urlsplit(name).hostname != target_host:
            continue
        fetch_start = numeric(resource.get("fetchStart"))
        request_start = numeric(resource.get("requestStart"))
        if fetch_start is None or request_start is None:
            continue
        queue_ms = round(max(0.0, request_start - fetch_start), 3)
        if queue_ms <= 1000.0:
            continue
        probe_row = first_activity_rows.get(name)
        if probe_row is None:
            continue
        first_activity_ms = activity_observed_relative_ms(browser_run, probe_row)
        if first_activity_ms is None:
            continue
        fetch_to_probe_ms = round(max(0.0, first_activity_ms - fetch_start), 3)
        probe_to_request_ms = round(max(0.0, request_start - first_activity_ms), 3)
        rows.append(
            {
                "resource": name,
                "priority_header": priority_header_label(
                    browser_activity_priority_header(probe_row)
                ),
                "initiator_type": initiator_type_label(resource.get("initiatorType")),
                "queue_ms": queue_ms,
                "fetch_to_probe_ms": fetch_to_probe_ms,
                "probe_to_request_ms": probe_to_request_ms,
                "request_order_dominant": probe_to_request_ms >= queue_ms * 0.75,
                "late_discovered_gt_1000ms": fetch_to_probe_ms > 1000.0,
            }
        )
    return rows


def same_origin_should_throttle_rows(
    browser_run: dict[str, object], target_url: str
) -> list[dict[str, object]]:
    target_host = urlsplit(target_url).hostname
    resource_by_url = {
        str(resource.get("name")): resource
        for resource in performance_resources(browser_run)
        if isinstance(resource.get("name"), str)
    }
    first_activity_rows = first_http_activity_row_by_uri(browser_run)
    grouped: dict[str, dict[str, object]] = {}
    for row in browser_net_log_transaction_rows(browser_run):
        uri = row.get("uri")
        if not isinstance(uri, str) or not uri:
            continue
        if urlsplit(uri).hostname != target_host:
            continue
        should_throttle_events = int(numeric(row.get("should_throttle_events")) or 0.0)
        if should_throttle_events <= 0:
            continue
        summary_row = grouped.setdefault(
            uri,
            {
                "resource": uri,
                "should_throttle_events": 0,
            },
        )
        summary_row["should_throttle_events"] = int(
            summary_row.get("should_throttle_events", 0)
        ) + should_throttle_events

    rows: list[dict[str, object]] = []
    for uri, summary_row in grouped.items():
        resource = resource_by_url.get(uri)
        queue_ms = subtract_fields(resource, "fetchStart", "requestStart") if isinstance(resource, dict) else None
        probe_row = first_activity_rows.get(uri)
        request_start = (
            numeric(resource.get("requestStart")) if isinstance(resource, dict) else None
        )
        probe_to_request_ms = (
            round(
                max(
                    0.0,
                    request_start - (activity_observed_relative_ms(browser_run, probe_row) or 0.0),
                ),
                3,
            )
            if request_start is not None and isinstance(probe_row, dict)
            else None
        )
        priority_header = priority_header_label(
            browser_activity_priority_header(probe_row) if probe_row is not None else ""
        )
        initiator_type = initiator_type_label(
            resource.get("initiatorType") if isinstance(resource, dict) else None
        )
        rows.append(
            {
                "resource": uri,
                "priority_header": priority_header,
                "initiator_type": initiator_type,
                "queue_ms": queue_ms,
                "should_throttle_events": summary_row["should_throttle_events"],
                "request_order_dominant": (
                    probe_to_request_ms is not None
                    and (numeric(queue_ms) or 0.0) > 0.0
                    and probe_to_request_ms >= (numeric(queue_ms) or 0.0) * 0.75
                ),
            }
        )
    return rows


def same_origin_should_throttle_timing_rows(
    browser_run: dict[str, object], target_url: str
) -> list[dict[str, object]]:
    target_host = urlsplit(target_url).hostname
    time_origin_ms = browser_time_origin_ms(browser_run)
    if time_origin_ms is None:
        return []
    resource_by_url = {
        str(resource.get("name")): resource
        for resource in performance_resources(browser_run)
        if isinstance(resource.get("name"), str)
    }
    first_activity_rows = first_http_activity_row_by_uri(browser_run)
    grouped: dict[str, dict[str, object]] = {}
    for row in browser_net_log_transaction_rows(browser_run):
        uri = row.get("uri")
        if not isinstance(uri, str) or not uri:
            continue
        if urlsplit(uri).hostname != target_host:
            continue
        should_throttle_events = int(numeric(row.get("should_throttle_events")) or 0.0)
        if should_throttle_events <= 0:
            continue
        first_should_throttle_epoch_ms = numeric(
            row.get("first_should_throttle_epoch_ms")
        )
        if first_should_throttle_epoch_ms is None:
            continue
        summary_row = grouped.setdefault(
            uri,
            {
                "resource": uri,
                "should_throttle_events": 0,
                "first_should_throttle_epoch_ms": first_should_throttle_epoch_ms,
            },
        )
        summary_row["should_throttle_events"] = int(
            summary_row.get("should_throttle_events", 0)
        ) + should_throttle_events
        existing_first = numeric(summary_row.get("first_should_throttle_epoch_ms"))
        if existing_first is None or first_should_throttle_epoch_ms < existing_first:
            summary_row["first_should_throttle_epoch_ms"] = first_should_throttle_epoch_ms

    rows: list[dict[str, object]] = []
    for uri, summary_row in grouped.items():
        resource = resource_by_url.get(uri)
        if not isinstance(resource, dict):
            continue
        first_should_throttle_ms = subtract_numeric(
            summary_row.get("first_should_throttle_epoch_ms"),
            time_origin_ms,
        )
        if first_should_throttle_ms is None:
            continue
        probe_row = first_activity_rows.get(uri)
        priority_header = priority_header_label(
            browser_activity_priority_header(probe_row) if probe_row is not None else ""
        )
        initiator_type = initiator_type_label(resource.get("initiatorType"))
        rows.append(
            {
                "resource": uri,
                "priority_header": priority_header,
                "initiator_type": initiator_type,
                "first_should_throttle_ms": first_should_throttle_ms,
                "fetch_after_first_should_throttle_ms": subtract_numeric(
                    resource.get("fetchStart"),
                    first_should_throttle_ms,
                ),
                "request_after_first_should_throttle_ms": subtract_numeric(
                    resource.get("requestStart"),
                    first_should_throttle_ms,
                ),
                "should_throttle_events": summary_row["should_throttle_events"],
            }
        )
    return rows


def same_origin_should_throttle_pre_request_blocker_rows(
    browser_run: dict[str, object], target_url: str
) -> list[dict[str, object]]:
    resources = performance_resources(browser_run)
    resource_by_url = {
        str(resource.get("name")): resource
        for resource in resources
        if isinstance(resource.get("name"), str)
    }
    first_activity_rows = first_http_activity_row_by_uri(browser_run)
    rows: list[dict[str, object]] = []
    for row in same_origin_should_throttle_timing_rows(browser_run, target_url):
        request_after_first_should_throttle_ms = numeric(
            row.get("request_after_first_should_throttle_ms")
        )
        if request_after_first_should_throttle_ms is None:
            continue
        if request_after_first_should_throttle_ms <= 0.0:
            continue
        uri = row.get("resource")
        resource = resource_by_url.get(uri) if isinstance(uri, str) else None
        if not isinstance(resource, dict):
            continue
        request_start = numeric(resource.get("requestStart"))
        if request_start is None:
            continue
        blockers = same_origin_protocol_active_resources_at_request(resource, resources)
        blocker_group_scores: dict[str, float] = {}
        same_group_blockers = 0
        resource_group = blocker_group_label(
            str(row.get("priority_header", "")),
            str(row.get("initiator_type", "")),
        )
        for blocker in blockers:
            blocker_name = blocker.get("name")
            blocker_probe_row = (
                first_activity_rows.get(blocker_name)
                if isinstance(blocker_name, str)
                else None
            )
            blocker_group = blocker_group_label(
                priority_header_label(
                    browser_activity_priority_header(blocker_probe_row)
                    if blocker_probe_row is not None
                    else ""
                ),
                initiator_type_label(blocker.get("initiatorType")),
            )
            blocker_group_scores[blocker_group] = (
                blocker_group_scores.get(blocker_group, 0.0) + 1.0
            )
            if blocker_group == resource_group:
                same_group_blockers += 1
        rows.append(
            {
                **row,
                "active_blockers": len(blockers),
                "same_group_blockers": same_group_blockers,
                "blocker_group_scores": blocker_group_scores,
            }
        )
    return rows


def same_origin_should_throttle_pre_request_remaining_rows(
    browser_run: dict[str, object], target_url: str
) -> list[dict[str, object]]:
    resources = performance_resources(browser_run)
    resource_by_url = {
        str(resource.get("name")): resource
        for resource in resources
        if isinstance(resource.get("name"), str)
    }
    rows: list[dict[str, object]] = []
    for row in same_origin_should_throttle_pre_request_blocker_rows(
        browser_run, target_url
    ):
        uri = row.get("resource")
        resource = resource_by_url.get(uri) if isinstance(uri, str) else None
        if not isinstance(resource, dict):
            continue
        request_start = numeric(resource.get("requestStart"))
        if request_start is None:
            continue
        blockers = same_origin_protocol_active_resources_at_request(resource, resources)
        wait_values = [
            blocker_wait_remaining_at_request(blocker, request_start) or 0.0
            for blocker in blockers
        ]
        receive_values = [
            blocker_receive_remaining_at_request(blocker, request_start) or 0.0
            for blocker in blockers
        ]
        sum_wait_remaining_ms = round(sum(wait_values), 3)
        sum_receive_remaining_ms = round(sum(receive_values), 3)
        rows.append(
            {
                **row,
                "max_wait_remaining_ms": max(wait_values) if wait_values else 0.0,
                "max_receive_remaining_ms": (
                    max(receive_values) if receive_values else 0.0
                ),
                "sum_wait_remaining_ms": sum_wait_remaining_ms,
                "sum_receive_remaining_ms": sum_receive_remaining_ms,
                "wait_dominant": sum_wait_remaining_ms >= sum_receive_remaining_ms,
            }
        )
    return rows


def same_origin_should_throttle_pre_request_phase_rows(
    browser_run: dict[str, object], target_url: str
) -> list[dict[str, object]]:
    resources = performance_resources(browser_run)
    resource_by_url = {
        str(resource.get("name")): resource
        for resource in resources
        if isinstance(resource.get("name"), str)
    }
    rows: list[dict[str, object]] = []
    for row in same_origin_should_throttle_pre_request_remaining_rows(
        browser_run, target_url
    ):
        uri = row.get("resource")
        resource = resource_by_url.get(uri) if isinstance(uri, str) else None
        if not isinstance(resource, dict):
            continue
        request_to_response_start_ms = subtract_fields(
            resource, "requestStart", "responseStart"
        )
        response_start_to_response_end_ms = subtract_fields(
            resource, "responseStart", "responseEnd"
        )
        throttle_to_response_start_ms = subtract_numeric(
            resource.get("responseStart"), row.get("first_should_throttle_ms")
        )
        throttle_to_response_end_ms = subtract_numeric(
            resource.get("responseEnd"), row.get("first_should_throttle_ms")
        )
        rows.append(
            {
                **row,
                "request_to_response_start_ms": request_to_response_start_ms,
                "response_start_to_response_end_ms": (
                    response_start_to_response_end_ms
                ),
                "throttle_to_response_start_ms": throttle_to_response_start_ms,
                "throttle_to_response_end_ms": throttle_to_response_end_ms,
                "response_start_dominant": (
                    (numeric(request_to_response_start_ms) or 0.0)
                    >= (numeric(response_start_to_response_end_ms) or 0.0)
                ),
            }
        )
    return rows


def same_origin_should_throttle_pre_request_phase_pair_rows(
    browser_run: dict[str, object], target_url: str
) -> list[dict[str, object]]:
    resources = performance_resources(browser_run)
    resource_by_url = {
        str(resource.get("name")): resource
        for resource in resources
        if isinstance(resource.get("name"), str)
    }
    connection_keys_by_uri = browser_activity_connection_group_keys_by_uri(browser_run)
    rows: list[dict[str, object]] = []
    for row in same_origin_should_throttle_pre_request_phase_rows(
        browser_run, target_url
    ):
        request_to_response_start_ms = numeric(row.get("request_to_response_start_ms"))
        if request_to_response_start_ms is None or request_to_response_start_ms <= 0.0:
            continue
        uri = row.get("resource")
        resource = resource_by_url.get(uri) if isinstance(uri, str) else None
        if not isinstance(resource, dict):
            continue
        request_start = numeric(resource.get("requestStart"))
        if request_start is None:
            continue
        target_connection_keys = set(connection_keys_by_uri.get(str(uri), ()))
        blockers = same_origin_protocol_active_resources_at_request(resource, resources)
        blocker_pair_scores: dict[str, float] = {}
        blocker_resource_scores: dict[str, float] = {}
        shared_connection_pair_scores: dict[str, float] = {}
        shared_connection_resource_scores: dict[str, float] = {}
        shared_connection_pairs = 0
        for blocker in blockers:
            blocker_name = blocker.get("name")
            if not isinstance(blocker_name, str):
                continue
            wait_remaining_ms = (
                blocker_wait_remaining_at_request(blocker, request_start) or 0.0
            )
            receive_remaining_ms = (
                blocker_receive_remaining_at_request(blocker, request_start) or 0.0
            )
            pair_covered_ms = min(
                request_to_response_start_ms,
                wait_remaining_ms + receive_remaining_ms,
            )
            blocker_label = resource_name_label(blocker_name)
            target_label = resource_name_label(str(uri))
            blocker_pair_scores[f"{blocker_label} -> {target_label}"] = max(
                blocker_pair_scores.get(f"{blocker_label} -> {target_label}", 0.0),
                pair_covered_ms,
            )
            blocker_resource_scores[blocker_label] = max(
                blocker_resource_scores.get(blocker_label, 0.0),
                pair_covered_ms,
            )
            blocker_connection_keys = set(connection_keys_by_uri.get(blocker_name, ()))
            if target_connection_keys & blocker_connection_keys:
                shared_connection_pairs += 1
                shared_connection_pair_scores[
                    f"{blocker_label} -> {target_label}"
                ] = max(
                    shared_connection_pair_scores.get(
                        f"{blocker_label} -> {target_label}",
                        0.0,
                    ),
                    pair_covered_ms,
                )
                shared_connection_resource_scores[blocker_label] = max(
                    shared_connection_resource_scores.get(blocker_label, 0.0),
                    pair_covered_ms,
                )
        rows.append(
            {
                **row,
                "blocker_pair_scores": blocker_pair_scores,
                "blocker_resource_scores": blocker_resource_scores,
                "max_pair_covered_ms": max_numeric(blocker_pair_scores.values()),
                "shared_connection_pair_scores": shared_connection_pair_scores,
                "shared_connection_resource_scores": (
                    shared_connection_resource_scores
                ),
                "shared_connection_pairs": shared_connection_pairs,
                "max_shared_pair_covered_ms": max_numeric(
                    shared_connection_pair_scores.values()
                ),
            }
        )
    return rows


def same_origin_queue_cause_rows(
    browser_run: dict[str, object], target_url: str
) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    target_host = urlsplit(target_url).hostname
    for resource in performance_resources(browser_run):
        name = resource.get("name")
        if not isinstance(name, str):
            continue
        if urlsplit(name).hostname != target_host:
            continue
        request_start = numeric(resource.get("requestStart"))
        fetch_start = numeric(resource.get("fetchStart"))
        response_start = numeric(resource.get("responseStart"))
        response_end = numeric(resource.get("responseEnd"))
        if (
            request_start is None
            or fetch_start is None
            or response_start is None
            or response_end is None
        ):
            continue
        key = (
            origin_label(name),
            protocol_label(resource.get("nextHopProtocol")),
        )
        grouped[key].append(
            {
                "resource": name,
                "fetch_start_ms": fetch_start,
                "request_start_ms": request_start,
                "response_start_ms": response_start,
                "response_end_ms": response_end,
                "fetch_to_request_ms": subtract_fields(
                    resource,
                    "fetchStart",
                    "requestStart",
                ),
            }
        )

    rows: list[dict[str, object]] = []
    for group_rows in grouped.values():
        sorted_rows = sorted(
            group_rows,
            key=lambda row: (
                numeric(row.get("request_start_ms"))
                if numeric(row.get("request_start_ms")) is not None
                else float("inf"),
                numeric(row.get("fetch_start_ms"))
                if numeric(row.get("fetch_start_ms")) is not None
                else float("inf"),
                str(row.get("resource", "")),
            ),
        )
        previous_resource: dict[str, object] | None = None
        for row in sorted_rows:
            if previous_resource is None:
                previous_resource = row
                continue
            queue_ms = numeric(row.get("fetch_to_request_ms"))
            fetch_start = numeric(row.get("fetch_start_ms"))
            request_start = numeric(row.get("request_start_ms"))
            previous_response_end = numeric(previous_resource.get("response_end_ms"))
            if (
                queue_ms is None
                or queue_ms <= 0.0
                or fetch_start is None
                or request_start is None
                or previous_response_end is None
            ):
                previous_resource = row
                continue
            blocked_ms = max(
                0.0,
                min(request_start, previous_response_end) - fetch_start,
            )
            blocked_ms = min(blocked_ms, queue_ms)
            output_row = dict(row)
            output_row["previous_resource"] = previous_resource.get("resource", "")
            output_row["previous_response_end_ms"] = previous_response_end
            output_row["queue_blocked_by_previous_response_ms"] = round(blocked_ms, 3)
            output_row["queue_unexplained_after_previous_ms"] = round(
                max(0.0, queue_ms - blocked_ms),
                3,
            )
            output_row["queue_cause_hint"] = queue_cause_hint(output_row)
            rows.append(output_row)
            previous_resource = row
    return rows


def queue_cause_hint(row: dict[str, object]) -> str:
    queue_ms = numeric(row.get("fetch_to_request_ms")) or 0.0
    blocked_ms = numeric(row.get("queue_blocked_by_previous_response_ms")) or 0.0
    unexplained_ms = numeric(row.get("queue_unexplained_after_previous_ms")) or 0.0
    if queue_ms <= 0.0:
        return "no browser queue"
    if blocked_ms >= queue_ms * 0.9:
        return "queued behind previous response"
    if unexplained_ms > blocked_ms:
        return "queue mostly after previous response"
    return "mixed previous response and browser delay"


def performance_resources(browser_run: dict[str, object]) -> list[dict[str, object]]:
    performance_timing = browser_run.get("performance_timing")
    if not isinstance(performance_timing, dict):
        return []
    resources = performance_timing.get("resources")
    if not isinstance(resources, list):
        return []
    return [resource for resource in resources if isinstance(resource, dict)]


def navigation_value(browser_run: dict[str, object], field: str) -> float | None:
    performance_timing = browser_run.get("performance_timing")
    if not isinstance(performance_timing, dict):
        return None
    navigation = performance_timing.get("navigation")
    if not isinstance(navigation, dict):
        return None
    return numeric(navigation.get(field))


def browser_time_origin_ms(browser_run: dict[str, object]) -> float | None:
    performance_timing = browser_run.get("performance_timing")
    if not isinstance(performance_timing, dict):
        return None
    return numeric(performance_timing.get("time_origin_ms"))


def browser_activity_probe_rows(browser_run: dict[str, object]) -> list[dict[str, object]]:
    probe = browser_run.get("browser_activity_probe")
    if not isinstance(probe, dict) or probe.get("enabled") is not True:
        return []
    rows = probe.get("rows")
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def browser_activity_connection_group_key(row: dict[str, object]) -> str | None:
    for field in CONNECTION_INFO_HASH_FIELDS:
        value = row.get(field)
        if value in (None, ""):
            continue
        return str(value)
    return None


def browser_activity_connection_group_keys_by_uri(
    browser_run: dict[str, object],
) -> dict[str, tuple[str, ...]]:
    grouped: dict[str, set[str]] = defaultdict(set)
    for row in browser_activity_probe_rows(browser_run):
        uri = row.get("uri")
        if not isinstance(uri, str) or not uri:
            continue
        connection_key = browser_activity_connection_group_key(row)
        if connection_key is None:
            continue
        grouped[uri].add(connection_key)
    return {
        uri: tuple(sorted(connection_keys))
        for uri, connection_keys in grouped.items()
    }


def activity_observed_relative_ms(
    browser_run: dict[str, object], row: dict[str, object]
) -> float | None:
    time_origin_ms = browser_time_origin_ms(browser_run)
    observed_epoch_ms = numeric(row.get("observed_epoch_ms"))
    if time_origin_ms is None or observed_epoch_ms is None:
        return None
    return round(observed_epoch_ms - time_origin_ms, 3)


def first_http_activity_info_by_uri(
    browser_run: dict[str, object],
) -> dict[str, tuple[float, dict[str, object]]]:
    first_activity_by_uri: dict[str, tuple[float, dict[str, object]]] = {}
    for row in browser_activity_probe_rows(browser_run):
        if row.get("source") != "http_activity":
            continue
        uri = row.get("uri")
        if not isinstance(uri, str) or not uri:
            continue
        relative_ms = activity_observed_relative_ms(browser_run, row)
        if relative_ms is None:
            continue
        previous = first_activity_by_uri.get(uri)
        if previous is None or relative_ms < previous[0]:
            first_activity_by_uri[uri] = (relative_ms, row)
    return first_activity_by_uri


def first_http_activity_row_by_uri(
    browser_run: dict[str, object],
) -> dict[str, dict[str, object]]:
    return {
        uri: row for uri, (_relative_ms, row) in first_http_activity_info_by_uri(browser_run).items()
    }


def first_activity_relative_ms_by_uri(
    browser_run: dict[str, object],
) -> dict[str, float]:
    return {
        uri: relative_ms
        for uri, (relative_ms, _row) in first_http_activity_info_by_uri(browser_run).items()
    }


def browser_activity_priority_header(row: dict[str, object]) -> str:
    extra_string_data = row.get("extra_string_data")
    if not isinstance(extra_string_data, str):
        return ""
    match = PRIORITY_HEADER_RE.search(extra_string_data)
    if match is None:
        return ""
    return match.group(1).strip()


def priority_header_label(value: str) -> str:
    return value if value else "(none)"


def initiator_type_label(value: object) -> str:
    if isinstance(value, str) and value:
        return value
    return "unknown"


def browser_net_log_transaction_rows(
    browser_run: dict[str, object],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    rows_by_channel: dict[tuple[str, str], dict[str, object]] = {}
    rows_by_transaction: dict[tuple[str, str], dict[str, object]] = {}
    pending_uri_by_file: dict[str, str] = {}
    pending_dispatch_channel_by_file: dict[str, str] = {}

    def row_for_channel(file_key: str, channel: str) -> dict[str, object]:
        key = (file_key, channel)
        row = rows_by_channel.get(key)
        if row is None:
            row = {
                "file": file_key,
                "http_channel": channel,
            }
            rows_by_channel[key] = row
            rows.append(row)
        return row

    def row_for_transaction(file_key: str, transaction: str) -> dict[str, object]:
        key = (file_key, transaction)
        row = rows_by_transaction.get(key)
        if row is None:
            row = {
                "file": file_key,
                "transaction": transaction,
            }
            rows_by_transaction[key] = row
            rows.append(row)
        return row

    for path in parent_browser_net_log_paths(browser_run):
        file_key = path.name
        try:
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    timestamp_ms = parse_browser_net_log_timestamp_ms(line)
                    uri_match = re.search(
                        r"HttpChannelParent RecvAsyncOpen \[this=([0-9a-fA-F]+) uri=([^,\]]+), gid=([0-9]+)",
                        line,
                    )
                    if uri_match:
                        pending_uri_by_file[file_key] = uri_match.group(2)
                        continue

                    create_channel_match = re.search(
                        r"Creating nsHttpChannel \[this=([0-9a-fA-F]+),",
                        line,
                    )
                    if create_channel_match:
                        channel = create_channel_match.group(1)
                        row = row_for_channel(file_key, channel)
                        pending_uri = pending_uri_by_file.pop(file_key, None)
                        if pending_uri:
                            row["uri"] = pending_uri
                        continue

                    dispatch_match = re.search(
                        r"nsHttpChannel::DispatchTransaction \[this=([0-9a-fA-F]+),",
                        line,
                    )
                    if dispatch_match:
                        pending_dispatch_channel_by_file[file_key] = (
                            dispatch_match.group(1)
                        )
                        continue

                    transaction_match = re.search(
                        r"Creating nsHttpTransaction @([0-9a-fA-F]+)", line
                    )
                    if transaction_match:
                        transaction = transaction_match.group(1)
                        channel = pending_dispatch_channel_by_file.pop(file_key, None)
                        if channel:
                            row = row_for_channel(file_key, channel)
                        else:
                            row = row_for_transaction(file_key, transaction)
                        row["transaction"] = transaction
                        rows_by_transaction[(file_key, transaction)] = row
                        continue

                    should_throttle_match = re.search(
                        r"nsHttpConnectionMgr::ShouldThrottle trans=([0-9a-fA-F]+)",
                        line,
                    )
                    if should_throttle_match:
                        transaction = should_throttle_match.group(1)
                        row = row_for_transaction(file_key, transaction)
                        row["should_throttle_events"] = int(
                            row.get("should_throttle_events", 0)
                        ) + 1
                        if timestamp_ms is not None and row.get("first_should_throttle_epoch_ms") is None:
                            row["first_should_throttle_epoch_ms"] = timestamp_ms
                        if timestamp_ms is not None:
                            row["last_should_throttle_epoch_ms"] = timestamp_ms
                        continue
        except OSError:
            continue
    return rows


def parent_browser_net_log_paths(browser_run: dict[str, object]) -> list[Path]:
    browser_net_log = browser_run.get("browser_net_log")
    if not isinstance(browser_net_log, dict):
        return []
    files = browser_net_log.get("files")
    if not isinstance(files, list):
        return []
    paths: list[Path] = []
    for raw_path in files:
        if not isinstance(raw_path, str):
            continue
        path = Path(raw_path)
        if not path.exists() or not path.is_file() or not path.name.endswith(".mozlog.moz_log"):
            continue
        paths.append(path)
    return paths


def parse_browser_net_log_timestamp_ms(line: str | None) -> int | None:
    if not line:
        return None
    match = re.match(
        r"(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2})(?:\.(\d+))? UTC\b",
        line,
    )
    if not match:
        return None
    fraction = (match.group(3) or "0")[:6].ljust(6, "0")
    dt = datetime.fromisoformat(
        f"{match.group(1)}T{match.group(2)}.{fraction}+00:00"
    )
    return int(dt.timestamp() * 1000)


def subtract_fields(resource: dict[str, object], start: str, end: str) -> float | None:
    start_value = numeric(resource.get(start))
    end_value = numeric(resource.get(end))
    if start_value is None or end_value is None:
        return None
    return round(max(0.0, end_value - start_value), 3)


def subtract_numeric(candidate: object, baseline: object) -> float | None:
    candidate_value = numeric(candidate)
    baseline_value = numeric(baseline)
    if candidate_value is None or baseline_value is None:
        return None
    return round(candidate_value - baseline_value, 3)


def same_origin_protocol_slot_depth_at_request(
    resource: dict[str, object], resources: list[dict[str, object]]
) -> float | None:
    request_start = numeric(resource.get("requestStart"))
    name = resource.get("name")
    if request_start is None or not isinstance(name, str):
        return None
    origin = origin_label(name)
    protocol = protocol_label(resource.get("nextHopProtocol"))
    active = 1
    for other in resources:
        if other is resource:
            continue
        other_name = other.get("name")
        if not isinstance(other_name, str):
            continue
        if origin_label(other_name) != origin:
            continue
        if protocol_label(other.get("nextHopProtocol")) != protocol:
            continue
        other_request_start = numeric(other.get("requestStart"))
        other_response_end = numeric(other.get("responseEnd"))
        if other_request_start is None or other_response_end is None:
            continue
        if other_request_start <= request_start < other_response_end:
            active += 1
    return float(active)


def same_origin_protocol_active_resources_at_request(
    resource: dict[str, object], resources: list[dict[str, object]]
) -> list[dict[str, object]]:
    request_start = numeric(resource.get("requestStart"))
    name = resource.get("name")
    if request_start is None or not isinstance(name, str):
        return []
    origin = origin_label(name)
    protocol = protocol_label(resource.get("nextHopProtocol"))
    active: list[dict[str, object]] = []
    for other in resources:
        if other is resource:
            continue
        other_name = other.get("name")
        if not isinstance(other_name, str):
            continue
        if origin_label(other_name) != origin:
            continue
        if protocol_label(other.get("nextHopProtocol")) != protocol:
            continue
        other_request_start = numeric(other.get("requestStart"))
        other_response_end = numeric(other.get("responseEnd"))
        if other_request_start is None or other_response_end is None:
            continue
        if other_request_start <= request_start < other_response_end:
            active.append(other)
    return sorted(
        active,
        key=lambda row: subtract_numeric(row.get("responseEnd"), request_start) or 0.0,
        reverse=True,
    )


def blocker_wait_remaining_at_request(
    resource: dict[str, object], request_start: object
) -> float | None:
    queue_start = numeric(request_start)
    response_start = numeric(resource.get("responseStart"))
    response_end = numeric(resource.get("responseEnd"))
    if queue_start is None or response_start is None or response_end is None:
        return None
    if queue_start >= response_end:
        return 0.0
    return round(max(0.0, response_start - queue_start), 3)


def blocker_receive_remaining_at_request(
    resource: dict[str, object], request_start: object
) -> float | None:
    queue_start = numeric(request_start)
    response_start = numeric(resource.get("responseStart"))
    response_end = numeric(resource.get("responseEnd"))
    if queue_start is None or response_start is None or response_end is None:
        return None
    if queue_start >= response_end:
        return 0.0
    return round(max(0.0, response_end - max(queue_start, response_start)), 3)


def origin_label(value: object) -> str:
    if not isinstance(value, str) or not value:
        return ""
    parts = urlsplit(value)
    if parts.scheme and parts.netloc:
        return f"{parts.scheme}://{parts.netloc}"
    return parts.netloc or value


def protocol_label(value: object) -> str:
    if isinstance(value, str) and value:
        return value
    return "unknown"


def blocker_group_label(priority_header: str, initiator_type: str) -> str:
    return f"{priority_header_label(priority_header)}/{initiator_type_label(initiator_type)}"


def navigation_phase_metrics(browser_run: dict[str, object]) -> dict[str, object]:
    performance_timing = browser_run.get("performance_timing")
    if not isinstance(performance_timing, dict):
        return {
            "nav_response_start_ms": None,
            "nav_response_to_dom_ms": None,
            "nav_dom_to_load_ms": None,
        }
    navigation = performance_timing.get("navigation")
    if not isinstance(navigation, dict):
        return {
            "nav_response_start_ms": None,
            "nav_response_to_dom_ms": None,
            "nav_dom_to_load_ms": None,
        }
    response_start = numeric(navigation.get("responseStart"))
    dom_content_loaded = numeric(navigation.get("domContentLoadedEventEnd"))
    load_event_end = numeric(navigation.get("loadEventEnd"))
    return {
        "nav_response_start_ms": rounded_metric(response_start),
        "nav_response_to_dom_ms": delta_metric(dom_content_loaded, response_start),
        "nav_dom_to_load_ms": delta_metric(load_event_end, dom_content_loaded),
    }


def payload_combined_wall_seconds(payload: dict[str, object]) -> float | None:
    warm = payload.get("warm")
    benchmark_wall_seconds = payload.get("benchmark_wall_seconds")
    if not isinstance(warm, dict):
        return None
    warm_seconds = numeric(warm.get("wall_seconds"))
    benchmark_seconds = numeric(benchmark_wall_seconds)
    if warm_seconds is None or benchmark_seconds is None:
        return None
    open_gate_seconds = nested_seconds(payload.get("open_gate_wait"))
    general_circuit_seconds = nested_seconds(payload.get("general_circuit_wait"))
    return round(
        warm_seconds + open_gate_seconds + general_circuit_seconds + benchmark_seconds,
        3,
    )


def nested_seconds(payload: object) -> float:
    if not isinstance(payload, dict):
        return 0.0
    seconds = numeric(payload.get("seconds"))
    return 0.0 if seconds is None else seconds


def service_bootstrap_progress(snapshot: object) -> float | None:
    if not isinstance(snapshot, dict):
        return None
    phase = snapshot.get("control_bootstrap_phase")
    if not isinstance(phase, dict):
        return None
    return rounded_metric(numeric(phase.get("progress")))


def service_general_circuit_count(snapshot: object) -> float | None:
    if not isinstance(snapshot, dict):
        return None
    general_circuit_snapshot = snapshot.get("general_circuit_snapshot")
    if not isinstance(general_circuit_snapshot, dict):
        return None
    return rounded_metric(numeric(general_circuit_snapshot.get("matched_circuit_count")))


def service_general_circuit_purpose_count(
    snapshot: object, purpose: str
) -> float | None:
    if not isinstance(snapshot, dict):
        return None
    general_circuit_snapshot = snapshot.get("general_circuit_snapshot")
    if not isinstance(general_circuit_snapshot, dict):
        return None
    purpose_counts = general_circuit_snapshot.get("matched_circuit_count_by_purpose")
    if not isinstance(purpose_counts, dict):
        return None
    return rounded_metric(numeric(purpose_counts.get(purpose)))


def service_has_built_general_circuit(snapshot: object) -> bool:
    if not isinstance(snapshot, dict):
        return False
    general_circuit_snapshot = snapshot.get("general_circuit_snapshot")
    if not isinstance(general_circuit_snapshot, dict):
        return False
    return general_circuit_snapshot.get("has_built_general_circuit") is True


def first_purpose_count_seconds(
    samples: list[object], *, purpose: str
) -> float | None:
    for sample in samples:
        if not isinstance(sample, dict):
            continue
        if (purpose_count(sample, purpose=purpose) or 0.0) > 0.0:
            return rounded_metric(numeric(sample.get("elapsed_seconds")))
    return None


def max_purpose_count(samples: list[object], *, purpose: str) -> float | None:
    return max_numeric(
        purpose_count(sample, purpose=purpose)
        for sample in samples
        if isinstance(sample, dict)
    )


def purpose_count(sample: dict[str, object], *, purpose: str) -> float | None:
    purpose_counts = sample.get("matched_circuit_count_by_purpose")
    if not isinstance(purpose_counts, dict):
        return None
    return numeric(purpose_counts.get(purpose))


def parent_mozlog_counts(browser_run: dict[str, object]) -> dict[str, object]:
    browser_net_log = browser_run.get("browser_net_log")
    if not isinstance(browser_net_log, dict):
        return zero_parent_mozlog_counts()
    files = browser_net_log.get("files")
    if not isinstance(files, list):
        return zero_parent_mozlog_counts()
    parent_log = None
    for entry in files:
        if isinstance(entry, str) and entry.endswith(".mozlog.moz_log"):
            parent_log = Path(entry)
            break
    if parent_log is None or not parent_log.exists():
        return zero_parent_mozlog_counts()
    text = parent_log.read_text(errors="ignore")
    return {
        "active_limit_events": len(ACTIVE_LIMIT_RE.findall(text)),
        "pending_queue_events": len(PENDING_QUEUE_RE.findall(text)),
        "process_pending_events": len(PROCESS_PENDING_RE.findall(text)),
        "should_throttle_events": len(SHOULD_THROTTLE_RE.findall(text)),
    }


def zero_parent_mozlog_counts() -> dict[str, int]:
    return {
        "active_limit_events": 0,
        "pending_queue_events": 0,
        "process_pending_events": 0,
        "should_throttle_events": 0,
    }


def top_names_by_score(
    rows: list[dict[str, object]],
    *,
    value_key: str,
    names_key: str,
    limit: int,
) -> list[str]:
    scores: dict[str, float] = {}
    for row in rows:
        value = numeric(row.get(value_key)) or 0.0
        names = row.get(names_key)
        if not isinstance(names, list):
            continue
        for name in names:
            if not isinstance(name, str):
                continue
            scores[name] = max(scores.get(name, 0.0), value)
    ordered = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    return [name for name, _ in ordered[:limit]]


def top_names_by_score_map(
    rows: list[dict[str, object]],
    *,
    score_map_key: str,
    limit: int,
) -> list[str]:
    scores: dict[str, float] = {}
    for row in rows:
        score_map = row.get(score_map_key)
        if not isinstance(score_map, dict):
            continue
        for name, value in score_map.items():
            if not isinstance(name, str):
                continue
            numeric_value = numeric(value) or 0.0
            scores[name] = max(scores.get(name, 0.0), numeric_value)
    ordered = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    return [name for name, _ in ordered[:limit]]


def summed_score_maps(
    rows: list[dict[str, object]], *, score_map_key: str
) -> dict[str, float]:
    scores: dict[str, float] = {}
    for row in rows:
        score_map = row.get(score_map_key)
        if not isinstance(score_map, dict):
            continue
        for name, value in score_map.items():
            if not isinstance(name, str):
                continue
            numeric_value = numeric(value)
            if numeric_value is None:
                continue
            scores[name] = round(scores.get(name, 0.0) + numeric_value, 3)
    return scores


def top_names_from_score_map(score_map: dict[str, float], *, limit: int) -> list[str]:
    ordered = sorted(score_map.items(), key=lambda item: (-item[1], item[0]))
    return [name for name, _ in ordered[:limit]]


def resource_name_label(name: str) -> str:
    path = urlsplit(name).path
    if not path:
        return name
    return path.rsplit("/", 1)[-1] or name


def median(values: object) -> float | None:
    numeric_values = [float(value) for value in values if isinstance(value, (int, float))]
    if not numeric_values:
        return None
    return round(statistics.median(numeric_values), 3)


def min_numeric(values: object) -> float | None:
    numeric_values = [float(value) for value in values if isinstance(value, (int, float))]
    if not numeric_values:
        return None
    return round(min(numeric_values), 3)


def max_numeric(values: object) -> float | None:
    numeric_values = [float(value) for value in values if isinstance(value, (int, float))]
    if not numeric_values:
        return None
    return round(max(numeric_values), 3)


def numeric(value: object) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def rounded_metric(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 3)


def delta_metric(later: float | None, earlier: float | None) -> float | None:
    if later is None or earlier is None:
        return None
    return round(later - earlier, 3)


def fmt(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return f"{value:.3f}".rstrip("0").rstrip(".")
    return str(value)


if __name__ == "__main__":
    raise SystemExit(main())
