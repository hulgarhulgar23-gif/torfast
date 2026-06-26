#!/usr/bin/env python3
"""Analyze torfast browser compare results."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re
import statistics
import sys
from urllib.parse import urlsplit


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", help="torfast browser compare JSON path")
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
        "--top",
        type=int,
        default=8,
        help="top resources to print per profile/target section",
    )
    parser.add_argument(
        "--baseline-profile",
        help="baseline profile for the delta table",
    )
    parser.add_argument(
        "--compare-profile",
        help="comparison profile for the delta table",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    path = resolve_result_path(args.path, Path(args.results_dir))
    if path is None:
        print("No torfast browser compare result found.", file=sys.stderr)
        return 1

    payload = load_json(path)
    target_filter = set(args.target)
    phase_rows = phase_summary_rows(payload, target_filter=target_filter)
    tail_rows = resource_tail_summary_rows(payload, target_filter=target_filter)
    pressure_rows = same_origin_pressure_summary_rows(
        payload, target_filter=target_filter
    )
    blocker_summary_rows = same_origin_blocker_summary_rows(
        payload, target_filter=target_filter
    )
    blocker_detail_rows = same_origin_blocker_rows(
        payload, target_filter=target_filter
    )
    blocker_owner_summary = limit_blocker_owner_summary_rows(
        same_origin_blocker_owner_summary_rows(
            payload,
            target_filter=target_filter,
        ),
        limit=max(1, args.top),
    )
    blocker_family_rows = limit_blocker_family_summary_rows(
        same_origin_blocker_family_summary_rows(
            payload,
            target_filter=target_filter,
        ),
        limit=max(1, args.top),
    )
    blocker_owner_deltas = same_origin_blocker_owner_delta_rows(
        payload,
        target_filter=target_filter,
        baseline_profile=args.baseline_profile,
        compare_profile=args.compare_profile,
        limit=max(1, args.top),
    )
    browser_net_log_cache_rows = browser_net_log_cache_summary_rows(
        payload,
        target_filter=target_filter,
    )
    resource_discovery_rows = limit_resource_discovery_summary_rows(
        resource_discovery_summary_rows(
            payload,
            target_filter=target_filter,
        ),
        limit=max(1, args.top),
    )
    pre_network_cancel_rows = limit_pre_network_cancel_summary_rows(
        pre_network_cancel_summary_rows(
            payload,
            target_filter=target_filter,
        ),
        limit=max(1, args.top),
    )
    variant_swap_rows = limit_resource_variant_swap_rows(
        resource_variant_swap_rows(
            payload,
            target_filter=target_filter,
        ),
        limit=max(1, args.top),
    )
    css_discovery_gate_rows = limit_css_discovery_gate_rows(
        css_discovery_gate_summary_rows(
            payload,
            target_filter=target_filter,
        ),
        limit=max(1, args.top),
    )
    blocker_cache_rows = limit_blocker_cache_signal_rows(
        same_origin_blocker_cache_signal_rows(
            payload,
            target_filter=target_filter,
        ),
        limit=max(1, args.top),
    )
    family_rows = limit_resource_family_summary_rows(
        resource_family_summary_rows(
            payload,
            target_filter=target_filter,
        ),
        limit=max(1, args.top),
    )
    family_delta_rows = resource_family_delta_rows(
        payload,
        target_filter=target_filter,
        baseline_profile=args.baseline_profile,
        compare_profile=args.compare_profile,
        limit=max(1, args.top),
    )
    resource_rows = top_resource_rows(
        payload,
        target_filter=target_filter,
        limit=max(1, args.top),
    )
    delta_rows = resource_delta_rows(
        payload,
        target_filter=target_filter,
        baseline_profile=args.baseline_profile,
        compare_profile=args.compare_profile,
        limit=max(1, args.top),
    )

    print(f"# Torfast Browser Compare Analysis\n\nsource: `{path}`\n")
    if not phase_rows:
        print("No successful browser runs found.")
        return 1

    print("## Navigation Phases\n")
    print(
        "| profile | target | ok runs | load ms | launch+load ms | nav response ms | response->DOM ms | DOM->load ms | slowest resource ms |"
    )
    print("|---|---|---:|---:|---:|---:|---:|---:|---:|")
    for row in phase_rows:
        print(
            "| {profile} | {target} | {runs} | {load} | {launch_load} | {response} | {response_to_dom} | {dom_to_load} | {slowest} |".format(
                profile=row["profile"],
                target=row["target"],
                runs=fmt(row.get("ok_runs")),
                load=fmt(row.get("median_load_ms")),
                launch_load=fmt(row.get("median_launch_load_ms")),
                response=fmt(row.get("median_nav_response_start_ms")),
                response_to_dom=fmt(row.get("median_nav_response_to_dom_ms")),
                dom_to_load=fmt(row.get("median_nav_dom_to_load_ms")),
                slowest=fmt(row.get("median_slowest_resource_ms")),
            )
        )

    print("\n## Resource Tail Summary\n")
    print(
        "| profile | target | resources | queued >=1000ms | slow >=2s | ending final 1s | median fetch->request ms | max fetch->request ms | median duration ms | median wait ms | median receive ms | max response end ms | max tail after DOM ms | median end before load ms |"
    )
    print("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for row in tail_rows:
        print(
            "| {profile} | {target} | {resources} | {queued} | {slow} | {final} | {queue} | {max_queue} | {duration} | {wait} | {receive} | {response_end} | {tail_dom} | {end_before_load} |".format(
                profile=row["profile"],
                target=row["target"],
                resources=fmt(row.get("resources")),
                queued=fmt(row.get("queued_1000ms")),
                slow=fmt(row.get("slow_resources_2s")),
                final=fmt(row.get("resources_ending_final_1s")),
                queue=fmt(row.get("median_fetch_to_request_ms")),
                max_queue=fmt(row.get("max_fetch_to_request_ms")),
                duration=fmt(row.get("median_duration_ms")),
                wait=fmt(row.get("median_wait_ms")),
                receive=fmt(row.get("median_receive_ms")),
                response_end=fmt(row.get("max_response_end_ms")),
                tail_dom=fmt(row.get("max_tail_after_dom_ms")),
                end_before_load=fmt(row.get("median_end_before_load_ms")),
            )
        )

    print("\n## Same-Origin Slot Pressure\n")
    print(
        "| profile | target | queued >=1000ms | slot-pressure rows | median active at request | median max active in queue | max active in queue | top slot-pressure resources |"
    )
    print("|---|---|---:|---:|---:|---:|---:|---|")
    for row in pressure_rows:
        print(
            "| {profile} | {target} | {queued} | {slot_rows} | {active_request} | {active_queue} | {max_active_queue} | {top_resources} |".format(
                profile=row["profile"],
                target=row["target"],
                queued=fmt(row.get("queued_1000ms")),
                slot_rows=fmt(row.get("slot_pressure_rows")),
                active_request=fmt(row.get("median_active_same_origin_at_request")),
                active_queue=fmt(row.get("median_max_same_origin_active_in_queue")),
                max_active_queue=fmt(row.get("max_same_origin_active_in_queue")),
                top_resources=row.get("top_slot_pressure_resources", ""),
            )
        )

    print("\n## Slot Blocker Summary\n")
    print(
        "| profile | target | slot-pressure rows | median blockers before request | max blockers before request | top blockers |"
    )
    print("|---|---|---:|---:|---:|---|")
    for row in blocker_summary_rows:
        print(
            "| {profile} | {target} | {slot_rows} | {median_blockers} | {max_blockers} | {top_blockers} |".format(
                profile=row["profile"],
                target=row["target"],
                slot_rows=fmt(row.get("slot_pressure_rows")),
                median_blockers=fmt(row.get("median_blockers_before_request")),
                max_blockers=fmt(row.get("max_blockers_before_request")),
                top_blockers=row.get("top_blockers", ""),
            )
        )

    print("\n## Slot Blocker Chains\n")
    print(
        "| profile | target | run | queued resource | queue ms | blockers before request | top blockers |"
    )
    print("|---|---|---:|---|---:|---:|---|")
    for row in blocker_detail_rows[: max(1, args.top)]:
        print(
            "| {profile} | {target} | {run} | {resource} | {queue} | {blockers} | {top_blockers} |".format(
                profile=row["profile"],
                target=row["target"],
                run=fmt(row.get("run_index")),
                resource=row.get("resource", ""),
                queue=fmt(row.get("fetch_to_request_ms")),
                blockers=fmt(row.get("blockers_before_request")),
                top_blockers=row.get("top_blockers", ""),
            )
        )

    print("\n## Blocker Owners\n")
    print(
        "| profile | target | blocker | type | proto | occurrences | runs | queued resources | median active ms | median remaining at queued request ms | median overlap in queue ms | median blocker age at queued request ms | top queued resources |"
    )
    print("|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|")
    for row in blocker_owner_summary:
        print(
            "| {profile} | {target} | {blocker} | {rtype} | {proto} | {occurrences} | {runs} | {queued_resources} | {active} | {remaining} | {overlap} | {age} | {queued} |".format(
                profile=row["profile"],
                target=row["target"],
                blocker=row["blocker"],
                rtype=row.get("blocker_type", ""),
                proto=row.get("protocol", ""),
                occurrences=fmt(row.get("blocker_occurrences")),
                runs=fmt(row.get("runs")),
                queued_resources=fmt(row.get("queued_resource_count")),
                active=fmt(row.get("median_blocker_duration_ms")),
                remaining=fmt(
                    row.get("median_blocker_remaining_at_request_ms")
                ),
                overlap=fmt(row.get("median_blocker_overlap_in_queue_ms")),
                age=fmt(row.get("median_blocker_age_at_request_ms")),
                queued=row.get("top_queued_resources", ""),
            )
        )

    if blocker_family_rows:
        print("\n## Blocker Family Cascades\n")
        print(
            "| profile | target | queued family | blocker family | occurrences | runs | queued resources | blocker resources | median remaining at queued request ms | median overlap in queue ms | top blockers |"
        )
        print(
            "|---|---|---|---|---:|---:|---:|---:|---:|---:|---|"
        )
        for row in blocker_family_rows:
            print(
                "| {profile} | {target} | {queued_family} | {blocker_family} | {occurrences} | {runs} | {queued_resources} | {blocker_resources} | {remaining} | {overlap} | {top_blockers} |".format(
                    profile=row["profile"],
                    target=row["target"],
                    queued_family=row["queued_family"],
                    blocker_family=row["blocker_family"],
                    occurrences=fmt(row.get("blocker_occurrences")),
                    runs=fmt(row.get("runs")),
                    queued_resources=fmt(row.get("queued_resource_count")),
                    blocker_resources=fmt(row.get("blocker_resource_count")),
                    remaining=fmt(
                        row.get("median_blocker_remaining_at_request_ms")
                    ),
                    overlap=fmt(row.get("median_blocker_overlap_in_queue_ms")),
                    top_blockers=row.get("top_blocker_resources", ""),
                )
            )

    if blocker_owner_deltas:
        compare_profile = str(blocker_owner_deltas[0]["compare_profile"])
        baseline_profile = str(blocker_owner_deltas[0]["baseline_profile"])
        print(
            f"\n## Blocker Owner Delta `{compare_profile}` vs `{baseline_profile}`\n"
        )
        print(
            "| target | blocker | type | compare occurrences | baseline occurrences | delta occurrences | compare active ms | baseline active ms | delta active ms | compare remaining at queued request ms | baseline remaining at queued request ms | delta remaining at queued request ms | compare overlap in queue ms | baseline overlap in queue ms | delta overlap in queue ms |"
        )
        print(
            "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"
        )
        for row in blocker_owner_deltas:
            print(
                "| {target} | {blocker} | {rtype} | {compare_occurrences} | {baseline_occurrences} | {delta_occurrences} | {compare_active} | {baseline_active} | {delta_active} | {compare_remaining} | {baseline_remaining} | {delta_remaining} | {compare_overlap} | {baseline_overlap} | {delta_overlap} |".format(
                    target=row["target"],
                    blocker=row["blocker"],
                    rtype=row.get("blocker_type", ""),
                    compare_occurrences=fmt(row.get("compare_blocker_occurrences")),
                    baseline_occurrences=fmt(
                        row.get("baseline_blocker_occurrences")
                    ),
                    delta_occurrences=fmt(row.get("delta_blocker_occurrences")),
                    compare_active=fmt(
                        row.get("compare_median_blocker_duration_ms")
                    ),
                    baseline_active=fmt(
                        row.get("baseline_median_blocker_duration_ms")
                    ),
                    delta_active=fmt(row.get("delta_median_blocker_duration_ms")),
                    compare_remaining=fmt(
                        row.get("compare_median_blocker_remaining_at_request_ms")
                    ),
                    baseline_remaining=fmt(
                        row.get("baseline_median_blocker_remaining_at_request_ms")
                    ),
                    delta_remaining=fmt(
                        row.get("delta_median_blocker_remaining_at_request_ms")
                    ),
                    compare_overlap=fmt(
                        row.get("compare_median_blocker_overlap_in_queue_ms")
                    ),
                    baseline_overlap=fmt(
                        row.get("baseline_median_blocker_overlap_in_queue_ms")
                    ),
                    delta_overlap=fmt(
                        row.get("delta_median_blocker_overlap_in_queue_ms")
                    ),
                )
            )

    if browser_net_log_cache_rows:
        print("\n## Net-Log Cache Signals\n")
        print(
            "| profile | target | net-log rows | unique URIs | same-origin rows | http/1.1 rows | 200 rows | 304 rows | cache new | cache reused | must-validate yes | must-validate no | ETag rows | Last-Modified rows | Cache-Control max-age rows |"
        )
        print(
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"
        )
        for row in browser_net_log_cache_rows:
            print(
                "| {profile} | {target} | {rows} | {uris} | {same_origin} | {http11} | {ok200} | {not_modified} | {cache_new} | {cache_reused} | {must_validate_yes} | {must_validate_no} | {etag} | {last_modified} | {max_age} |".format(
                    profile=row["profile"],
                    target=row["target"],
                    rows=fmt(row.get("rows")),
                    uris=fmt(row.get("unique_uris")),
                    same_origin=fmt(row.get("same_origin_rows")),
                    http11=fmt(row.get("http11_rows")),
                    ok200=fmt(row.get("status_200_rows")),
                    not_modified=fmt(row.get("status_304_rows")),
                    cache_new=fmt(row.get("cache_entry_new_rows")),
                    cache_reused=fmt(row.get("cache_entry_reused_rows")),
                    must_validate_yes=fmt(row.get("must_validate_yes_rows")),
                    must_validate_no=fmt(row.get("must_validate_no_rows")),
                    etag=fmt(row.get("etag_rows")),
                    last_modified=fmt(row.get("last_modified_rows")),
                    max_age=fmt(row.get("cache_control_max_age_rows")),
                )
            )

    if resource_discovery_rows:
        print("\n## Resource Discovery\n")
        print(
            "| profile | target | family | resources | unique resources | median request start ms | dom-only | css-only | dom+css | img-dom | css background | css font-face | top stylesheets | top selectors |"
        )
        print(
            "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|"
        )
        for row in resource_discovery_rows:
            print(
                "| {profile} | {target} | {family} | {resources} | {unique_resources} | {request_start} | {dom_only} | {css_only} | {dom_and_css} | {img_dom} | {css_background} | {css_font_face} | {stylesheets} | {selectors} |".format(
                    profile=row["profile"],
                    target=row["target"],
                    family=row["family"],
                    resources=fmt(row.get("resources")),
                    unique_resources=fmt(row.get("unique_resources")),
                    request_start=fmt(row.get("median_request_start_ms")),
                    dom_only=fmt(row.get("dom_only_resources")),
                    css_only=fmt(row.get("css_only_resources")),
                    dom_and_css=fmt(row.get("dom_and_css_resources")),
                    img_dom=fmt(row.get("img_dom_resources")),
                    css_background=fmt(row.get("css_background_resources")),
                    css_font_face=fmt(row.get("css_font_face_resources")),
                    stylesheets=row.get("top_css_stylesheets", ""),
                    selectors=row.get("top_css_selectors", ""),
                )
            )

    if pre_network_cancel_rows:
        print("\n## Pre-Network Cancels\n")
        print(
            "| profile | target | loaded family | current family | request-blocked | resources | unique resources | median request start ms | stop-request rows | channels | top loaded resources | current discovered resources |"
        )
        print("|---|---|---|---|---|---:|---:|---:|---:|---:|---|---|")
        for row in pre_network_cancel_rows:
            print(
                "| {profile} | {target} | {loaded_family} | {current_family} | {request_blocked} | {resources} | {unique_resources} | {request_start} | {stop_rows} | {channels} | {loaded_resources} | {current_resources} |".format(
                    profile=row["profile"],
                    target=row["target"],
                    loaded_family=row["loaded_family"],
                    current_family=row["current_family"],
                    request_blocked="yes" if row.get("request_blocked") else "no",
                    resources=fmt(row.get("resources")),
                    unique_resources=fmt(row.get("unique_resources")),
                    request_start=fmt(row.get("median_request_start_ms")),
                    stop_rows=fmt(row.get("stop_request_rows")),
                    channels=fmt(row.get("channel_count")),
                    loaded_resources=row.get("top_loaded_resources", ""),
                    current_resources=row.get("top_current_resources", ""),
                )
            )

    if variant_swap_rows:
        print("\n## Variant Swaps\n")
        print(
            "| profile | target | loaded family | current family | resources | median request start ms | top loaded resources | current discovered resources |"
        )
        print("|---|---|---|---|---:|---:|---|---|")
        for row in variant_swap_rows:
            print(
                "| {profile} | {target} | {loaded_family} | {current_family} | {resources} | {request_start} | {loaded_resources} | {current_resources} |".format(
                    profile=row["profile"],
                    target=row["target"],
                    loaded_family=row["loaded_family"],
                    current_family=row["current_family"],
                    resources=fmt(row.get("resources")),
                    request_start=fmt(row.get("median_request_start_ms")),
                    loaded_resources=row.get("top_loaded_resources", ""),
                    current_resources=row.get("top_current_resources", ""),
                )
            )

    if css_discovery_gate_rows:
        print("\n## CSS Discovery Gates\n")
        print(
            "| profile | target | family | stylesheet | resources | median fetch start after stylesheet end ms | median request start after stylesheet end ms | median stylesheet end ms | top selectors |"
        )
        print(
            "|---|---|---|---|---:|---:|---:|---:|---|"
        )
        for row in css_discovery_gate_rows:
            print(
                "| {profile} | {target} | {family} | {stylesheet} | {resources} | {fetch_after} | {request_after} | {stylesheet_end} | {selectors} |".format(
                    profile=row["profile"],
                    target=row["target"],
                    family=row["family"],
                    stylesheet=row["stylesheet"],
                    resources=fmt(row.get("resources")),
                    fetch_after=fmt(
                        row.get("median_fetch_start_after_stylesheet_end_ms")
                    ),
                    request_after=fmt(
                        row.get("median_request_start_after_stylesheet_end_ms")
                    ),
                    stylesheet_end=fmt(row.get("median_stylesheet_response_end_ms")),
                    selectors=row.get("top_css_selectors", ""),
                )
            )

    if blocker_cache_rows:
        print("\n## Blocker Cache Signals\n")
        print(
            "| profile | target | blocker | type | proto | blocker occurrences | net-log matches | status codes | cache entry | must validate | cache-control | ETag | Last-Modified | content-type |"
        )
        print("|---|---|---|---|---|---:|---:|---|---|---|---|---|---|---|")
        for row in blocker_cache_rows:
            print(
                "| {profile} | {target} | {blocker} | {rtype} | {proto} | {occurrences} | {matches} | {status_codes} | {cache_entry} | {must_validate} | {cache_control} | {etag} | {last_modified} | {content_type} |".format(
                    profile=row["profile"],
                    target=row["target"],
                    blocker=row["blocker"],
                    rtype=row.get("blocker_type", ""),
                    proto=row.get("protocol", ""),
                    occurrences=fmt(row.get("blocker_occurrences")),
                    matches=fmt(row.get("net_log_matches")),
                    status_codes=row.get("status_codes", ""),
                    cache_entry=row.get("cache_entry_summary", ""),
                    must_validate=row.get("must_validate_summary", ""),
                    cache_control=row.get("cache_control_summary", ""),
                    etag=row.get("etag_summary", ""),
                    last_modified=row.get("last_modified_summary", ""),
                    content_type=row.get("content_type_summary", ""),
                )
            )

    if family_rows:
        print("\n## Resource Families\n")
        print(
            "| profile | target | family | resources | unique resources | median request start ms | median fetch->request ms | median wait ms | median receive ms | median duration ms | median encoded KiB | median transfer KiB | top resources |"
        )
        print(
            "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|"
        )
        for row in family_rows:
            print(
                "| {profile} | {target} | {family} | {resources} | {unique_resources} | {request_start} | {queue} | {wait} | {receive} | {duration} | {encoded_kib} | {transfer_kib} | {top_resources} |".format(
                    profile=row["profile"],
                    target=row["target"],
                    family=row["family"],
                    resources=fmt(row.get("resources")),
                    unique_resources=fmt(row.get("unique_resources")),
                    request_start=fmt(row.get("median_request_start_ms")),
                    queue=fmt(row.get("median_fetch_to_request_ms")),
                    wait=fmt(row.get("median_wait_ms")),
                    receive=fmt(row.get("median_receive_ms")),
                    duration=fmt(row.get("median_duration_ms")),
                    encoded_kib=fmt(row.get("median_encoded_body_kib")),
                    transfer_kib=fmt(row.get("median_transfer_size_kib")),
                    top_resources=row.get("top_resources", ""),
                )
            )

    if family_delta_rows:
        compare_profile = str(family_delta_rows[0]["compare_profile"])
        baseline_profile = str(family_delta_rows[0]["baseline_profile"])
        print(f"\n## Family Delta `{compare_profile}` vs `{baseline_profile}`\n")
        print(
            "| target | family | phase hint | compare request start ms | baseline request start ms | delta request start ms | delta fetch->request ms | delta wait ms | delta receive ms | delta duration ms | delta encoded KiB |"
        )
        print(
            "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|"
        )
        for row in family_delta_rows:
            print(
                "| {target} | {family} | {phase_hint} | {compare_request_start} | {baseline_request_start} | {delta_request_start} | {delta_queue} | {delta_wait} | {delta_receive} | {delta_duration} | {delta_encoded_kib} |".format(
                    target=row["target"],
                    family=row["family"],
                    phase_hint=row.get("phase_hint", ""),
                    compare_request_start=fmt(
                        row.get("compare_request_start_ms")
                    ),
                    baseline_request_start=fmt(
                        row.get("baseline_request_start_ms")
                    ),
                    delta_request_start=fmt(row.get("delta_request_start_ms")),
                    delta_queue=fmt(row.get("delta_fetch_to_request_ms")),
                    delta_wait=fmt(row.get("delta_wait_ms")),
                    delta_receive=fmt(row.get("delta_receive_ms")),
                    delta_duration=fmt(row.get("delta_duration_ms")),
                    delta_encoded_kib=fmt(row.get("delta_encoded_body_kib")),
                )
            )

    print("\n## Top Load-Tail Resources\n")
    print(
        "| profile | target | resource | type | proto | runs | median fetch->request ms | median active in queue | slot-pressure runs | median duration ms | median wait ms | median receive ms | median tail after DOM ms | median end before load ms |"
    )
    print("|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for row in resource_rows:
        print(
            "| {profile} | {target} | {resource} | {rtype} | {proto} | {runs} | {queue} | {active_queue} | {slot_runs} | {duration} | {wait} | {receive} | {tail_dom} | {end_before_load} |".format(
                profile=row["profile"],
                target=row["target"],
                resource=row["resource"],
                rtype=row["resource_type"],
                proto=row.get("protocol", ""),
                runs=fmt(row.get("runs")),
                queue=fmt(row.get("median_fetch_to_request_ms")),
                active_queue=fmt(row.get("median_max_same_origin_active_in_queue")),
                slot_runs=fmt(row.get("slot_pressure_runs")),
                duration=fmt(row.get("median_duration_ms")),
                wait=fmt(row.get("median_wait_ms")),
                receive=fmt(row.get("median_receive_ms")),
                tail_dom=fmt(row.get("median_tail_after_dom_ms")),
                end_before_load=fmt(row.get("median_end_before_load_ms")),
            )
        )

    if delta_rows:
        compare_profile = str(delta_rows[0]["compare_profile"])
        baseline_profile = str(delta_rows[0]["baseline_profile"])
        print(f"\n## Resource Delta `{compare_profile}` vs `{baseline_profile}`\n")
        print(
            "| target | resource | type | phase hint | compare active in queue | baseline active in queue | delta active in queue | compare fetch->request ms | baseline fetch->request ms | delta fetch->request ms | delta wait ms | delta receive ms | delta duration ms | delta tail after DOM ms |"
        )
        print("|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
        for row in delta_rows:
            print(
                "| {target} | {resource} | {rtype} | {phase_hint} | {compare_active_queue} | {baseline_active_queue} | {delta_active_queue} | {compare_queue} | {baseline_queue} | {delta_queue} | {delta_wait} | {delta_receive} | {delta_duration} | {delta_tail} |".format(
                    target=row["target"],
                    resource=row["resource"],
                    rtype=row["resource_type"],
                    phase_hint=row.get("phase_hint", ""),
                    compare_active_queue=fmt(
                        row.get("compare_max_same_origin_active_in_queue")
                    ),
                    baseline_active_queue=fmt(
                        row.get("baseline_max_same_origin_active_in_queue")
                    ),
                    delta_active_queue=fmt(
                        row.get("delta_max_same_origin_active_in_queue")
                    ),
                    compare_queue=fmt(row.get("compare_fetch_to_request_ms")),
                    baseline_queue=fmt(row.get("baseline_fetch_to_request_ms")),
                    delta_queue=fmt(row.get("delta_fetch_to_request_ms")),
                    delta_wait=fmt(row.get("delta_wait_ms")),
                    delta_receive=fmt(row.get("delta_receive_ms")),
                    delta_duration=fmt(row.get("delta_duration_ms")),
                    delta_tail=fmt(row.get("delta_tail_after_dom_ms")),
                )
            )

    return 0


def resolve_result_path(raw_path: str | None, results_dir: Path) -> Path | None:
    if raw_path:
        return Path(raw_path).resolve()
    paths = sorted(
        results_dir.glob("torfast-browser-compare-*/torfast-browser-compare.json")
    )
    return paths[-1].resolve() if paths else None


def load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text())


def numeric(value: object) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def median(values: list[float]) -> float | None:
    return float(statistics.median(values)) if values else None


def fmt(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def iter_browser_runs(
    payload: dict[str, object],
    *,
    target_filter: set[str] | None = None,
):
    profiles = payload.get("profiles", {})
    if not isinstance(profiles, dict):
        return
    for profile_name, profile in sorted(profiles.items()):
        if not isinstance(profile, dict) or profile.get("skipped"):
            continue
        runs = profile.get("runs", [])
        if not isinstance(runs, list):
            continue
        for profile_run in runs:
            if not isinstance(profile_run, dict):
                continue
            run_index = profile_run.get("run_index")
            benchmarks = profile_run.get("benchmarks", {})
            if not isinstance(benchmarks, dict):
                continue
            for target, bench in sorted(benchmarks.items()):
                if target_filter and target not in target_filter:
                    continue
                if not isinstance(bench, dict):
                    continue
                browser_runs = bench.get("runs", [])
                if not isinstance(browser_runs, list):
                    continue
                for browser_run in browser_runs:
                    if not isinstance(browser_run, dict) or not browser_run.get("ok"):
                        continue
                    yield profile_name, str(target), run_index, profile_run, browser_run


def browser_timing_resource_names(
    browser_run: dict[str, object], *, target: str
) -> set[str]:
    names = {
        str(resource.get("name") or "")
        for resource in browser_resources(browser_run)
        if str(resource.get("name") or "")
    }
    names.add(target)
    current_url = browser_run.get("current_url")
    if isinstance(current_url, str) and current_url:
        names.add(current_url)
    browser_url = browser_run.get("url")
    if isinstance(browser_url, str) and browser_url:
        names.add(browser_url)
    return names


def browser_page_resource_discovery(
    browser_run: dict[str, object],
) -> list[dict[str, object]]:
    timing = browser_run.get("performance_timing", {})
    if not isinstance(timing, dict):
        return []
    discovery = timing.get("page_resource_discovery")
    if not isinstance(discovery, dict) or discovery.get("ok") is False:
        return []
    rows = discovery.get("rows")
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def browser_activity_probe_rows(
    browser_run: dict[str, object],
) -> list[dict[str, object]]:
    probe = browser_run.get("browser_activity_probe")
    if not isinstance(probe, dict) or probe.get("ok") is False:
        return []
    rows = probe.get("rows")
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def browser_request_blocked_uri_counter(
    browser_run: dict[str, object],
) -> Counter[str]:
    blocker = browser_run.get("browser_request_blocker")
    if not isinstance(blocker, dict) or blocker.get("ok") is False:
        return Counter()
    rows = blocker.get("rows")
    if not isinstance(rows, list):
        return Counter()
    counter: Counter[str] = Counter()
    for row in rows:
        if not isinstance(row, dict):
            continue
        uri = str(row.get("uri", ""))
        if uri:
            counter[uri] += 1
    return counter


def browser_activity_summary_by_uri(
    browser_run: dict[str, object],
) -> dict[str, dict[str, object]]:
    summary: dict[str, dict[str, object]] = {}
    for row in browser_activity_probe_rows(browser_run):
        uri = str(row.get("uri", ""))
        if not uri:
            continue
        state = summary.setdefault(
            uri,
            {
                "stop_request_rows": 0,
                "examine_response_rows": 0,
                "activity_rows": 0,
                "any_socket_ports": False,
                "channel_ids": set(),
            },
        )
        topic = str(row.get("topic", ""))
        if topic == "http-on-stop-request":
            state["stop_request_rows"] = int(state["stop_request_rows"]) + 1
        elif topic == "http-on-examine-response":
            state["examine_response_rows"] = int(state["examine_response_rows"]) + 1
        if row.get("source") == "http_activity":
            state["activity_rows"] = int(state["activity_rows"]) + 1
        if (
            row.get("localPort") is not None
            or row.get("remotePort") is not None
            or row.get("subject_localPort") is not None
            or row.get("subject_remotePort") is not None
        ):
            state["any_socket_ports"] = True
        channel_id = row.get("channel_id")
        if channel_id is not None:
            channel_ids = state["channel_ids"]
            assert isinstance(channel_ids, set)
            channel_ids.add(channel_id)
    return summary


def resource_url_match_keys(url: str) -> set[str]:
    keys = set()
    if not url:
        return keys
    keys.add(url)
    parsed = urlsplit(url)
    if parsed.scheme and parsed.netloc:
        path = parsed.path or ""
        base = f"{parsed.scheme}://{parsed.netloc}{path}"
        if parsed.query:
            keys.add(base)
        if path.startswith("/static/"):
            without_static_path = path[len("/static") :]
            normalized = f"{parsed.scheme}://{parsed.netloc}{without_static_path}"
            if parsed.query:
                keys.add(f"{normalized}?{parsed.query}")
            keys.add(normalized)
    return keys


def resource_variant_key(url: str) -> str:
    if not url:
        return ""
    parsed = urlsplit(url)
    if not parsed.scheme or not parsed.netloc:
        return url
    path = parsed.path or ""
    if path.startswith("/static/"):
        path = path[len("/static") :]
    segments = [segment for segment in path.split("/") if segment]
    normalized_segments: list[str] = []
    for segment in segments[:-1]:
        if segment.lower() in {"png", "svg", "jpg", "jpeg", "webp", "gif"}:
            continue
        normalized_segments.append(segment.lower())
    filename = segments[-1] if segments else ""
    stem = Path(filename).stem.lower()
    stem = re.sub(r"@\dx$", "", stem)
    normalized_segments.append(stem)
    return f"{parsed.scheme}://{parsed.netloc}/" + "/".join(normalized_segments)


def browser_nav(browser_run: dict[str, object]) -> dict[str, object]:
    timing = browser_run.get("performance_timing", {})
    if not isinstance(timing, dict):
        return {}
    navigation = timing.get("navigation")
    return navigation if isinstance(navigation, dict) else {}


def browser_resources(browser_run: dict[str, object]) -> list[dict[str, object]]:
    timing = browser_run.get("performance_timing", {})
    if not isinstance(timing, dict):
        return []
    resources = timing.get("resources")
    if not isinstance(resources, list):
        resources = timing.get("slowest_resources", [])
    if not isinstance(resources, list):
        return []
    return [resource for resource in resources if isinstance(resource, dict)]


def nav_phase(nav: dict[str, object], start_field: str, end_field: str) -> float | None:
    start = numeric(nav.get(start_field))
    end = numeric(nav.get(end_field))
    if start is None or end is None:
        return None
    return end - start


def run_slowest_resource_ms(browser_run: dict[str, object]) -> float | None:
    durations = [
        duration
        for resource in browser_resources(browser_run)
        if (duration := numeric(resource.get("duration"))) is not None
    ]
    return max(durations) if durations else None


def origin_label(url: object) -> str:
    raw = str(url or "")
    if not raw:
        return ""
    parsed = urlsplit(raw)
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}"


def protocol_label(protocol: object) -> str:
    return str(protocol or "")


def resource_active_interval(resource: dict[str, object]) -> tuple[float | None, float | None]:
    return numeric(resource.get("requestStart")), numeric(resource.get("responseEnd"))


def resource_queued_interval(resource: dict[str, object]) -> tuple[float | None, float | None]:
    start = numeric(resource.get("fetchStart"))
    if start is None:
        start = numeric(resource.get("startTime"))
    return start, numeric(resource.get("requestStart"))


def resource_active_at_ms(resource: dict[str, object], point_ms: object) -> bool:
    point = numeric(point_ms)
    start, end = resource_active_interval(resource)
    if point is None or start is None or end is None:
        return False
    return start <= point < end


def resource_active_overlap_ms(
    resource: dict[str, object], gap_start: object, gap_end: object
) -> float | None:
    start, end = resource_active_interval(resource)
    left = max(
        numeric(gap_start) if numeric(gap_start) is not None else float("-inf"),
        start if start is not None else float("-inf"),
    )
    right = min(
        numeric(gap_end) if numeric(gap_end) is not None else float("inf"),
        end if end is not None else float("inf"),
    )
    if left == float("-inf") or right == float("inf") or right <= left:
        return 0.0
    return right - left


def same_origin_protocol_resources(
    resource: dict[str, object], resources: list[dict[str, object]]
) -> list[dict[str, object]]:
    origin = origin_label(resource.get("name"))
    protocol = protocol_label(resource.get("nextHopProtocol"))
    return [
        candidate
        for candidate in resources
        if origin_label(candidate.get("name")) == origin
        and protocol_label(candidate.get("nextHopProtocol")) == protocol
    ]


def active_count_at_ms(resources: list[dict[str, object]], point_ms: object) -> int:
    return sum(1 for resource in resources if resource_active_at_ms(resource, point_ms))


def blockers_before_request(
    resource: dict[str, object], peers: list[dict[str, object]]
) -> list[dict[str, object]]:
    request_start = numeric(resource.get("requestStart"))
    if request_start is None:
        return []
    point = request_start - 0.001
    blockers = [
        peer
        for peer in peers
        if peer is not resource and resource_active_at_ms(peer, point)
    ]
    blockers.sort(
        key=lambda peer: (
            numeric(peer.get("responseEnd")) or 0.0,
            numeric(peer.get("requestStart")) or 0.0,
        ),
        reverse=True,
    )
    return blockers


def browser_net_log_parent_resource_rows_for_run(
    browser_run: dict[str, object],
) -> list[dict[str, object]]:
    log_summary = browser_run.get("browser_net_log", {})
    if not isinstance(log_summary, dict) or log_summary.get("enabled") is not True:
        return []
    files = log_summary.get("files")
    if not isinstance(files, list):
        return []

    rows: list[dict[str, object]] = []
    rows_by_channel: dict[tuple[str, str], dict[str, object]] = {}
    rows_by_transaction: dict[tuple[str, str], dict[str, object]] = {}
    pending_uri_by_file: dict[str, str] = {}
    pending_dispatch_channel_by_file: dict[str, str] = {}
    last_process_transaction_by_file: dict[str, str] = {}
    active_header_transaction_by_file: dict[str, str] = {}
    last_cache_channel_by_file: dict[str, str] = {}
    pending_validate_channel_by_file: dict[str, str] = {}

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

    def set_selected_header(row: dict[str, object], name: str, value: str) -> None:
        header_name = name.strip().lower()
        cleaned = value.strip()
        if header_name == "cache-control":
            row["cache_control"] = cleaned
        elif header_name == "etag":
            row["etag"] = cleaned
        elif header_name == "last-modified":
            row["last_modified"] = cleaned
        elif header_name == "content-type":
            row["content_type"] = cleaned

    for raw_path in files:
        if not isinstance(raw_path, str):
            continue
        path = Path(raw_path)
        if not path.exists() or not path.is_file():
            continue
        file_key = path.name
        try:
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    uri_match = re.search(
                        r"HttpChannelParent RecvAsyncOpen \[this=([0-9a-fA-F]+) uri=([^,\]]+), gid=([0-9]+)",
                        line,
                    )
                    if uri_match:
                        pending_uri_by_file[file_key] = uri_match.group(2)
                        continue

                    create_channel_match = re.search(
                        r"Creating nsHttpChannel \[this=([0-9a-fA-F]+),", line
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

                    open_cache_match = re.search(
                        r"nsHttpChannel::OpenCacheEntry \[this=([0-9a-fA-F]+)\]",
                        line,
                    )
                    if open_cache_match:
                        channel = open_cache_match.group(1)
                        row_for_channel(file_key, channel)
                        last_cache_channel_by_file[file_key] = channel
                        continue

                    cache_available_match = re.search(
                        r"nsHttpChannel::OnCacheEntryAvailable \[this=([0-9a-fA-F]+) entry=([0-9a-fA-F]+) new=([01]) status=([^\]]+)\] for (https?://\S+)",
                        line,
                    )
                    if cache_available_match:
                        channel = cache_available_match.group(1)
                        row = row_for_channel(file_key, channel)
                        row["cache_entry"] = cache_available_match.group(2)
                        row["cache_entry_new"] = cache_available_match.group(3) == "1"
                        row["cache_entry_status"] = cache_available_match.group(4)
                        row["uri"] = cache_available_match.group(5)
                        last_cache_channel_by_file[file_key] = channel
                        continue

                    process_data_match = re.search(
                        r"nsHttpTransaction::ProcessData \[this=([0-9a-fA-F]+) count=",
                        line,
                    )
                    if process_data_match:
                        last_process_transaction_by_file[file_key] = (
                            process_data_match.group(1)
                        )
                        continue

                    status_match = re.search(
                        r"nsHttpTransaction::ParseLine \[(HTTP/1\.[01]) ([0-9]{3})",
                        line,
                    )
                    if status_match:
                        transaction = last_process_transaction_by_file.get(file_key)
                        if transaction:
                            row = row_for_transaction(file_key, transaction)
                            row["http_version"] = status_match.group(1)
                            row["status_code"] = int(status_match.group(2))
                            active_header_transaction_by_file[file_key] = transaction
                        continue

                    header_match = re.search(
                        r"nsHttpTransaction::ParseLine \[([^:\]]+): (.*)\]",
                        line,
                    )
                    if header_match:
                        transaction = active_header_transaction_by_file.get(file_key)
                        if transaction:
                            row = row_for_transaction(file_key, transaction)
                            set_selected_header(
                                row,
                                header_match.group(1),
                                header_match.group(2),
                            )
                        continue

                    headers_available_match = re.search(
                        r"nsHttpConnection::OnHeadersAvailable \[this=([0-9a-fA-F]+) trans=([0-9a-fA-F]+) response-head=([0-9a-fA-F]+)\]",
                        line,
                    )
                    if headers_available_match:
                        transaction = headers_available_match.group(2)
                        row = row_for_transaction(file_key, transaction)
                        row["response_head"] = headers_available_match.group(3)
                        if active_header_transaction_by_file.get(file_key) == transaction:
                            active_header_transaction_by_file.pop(file_key, None)
                        continue

                    init_cache_match = re.search(
                        r"nsHttpChannel::InitCacheEntry \[this=([0-9a-fA-F]+) entry=([0-9a-fA-F]+)\]",
                        line,
                    )
                    if init_cache_match:
                        channel = init_cache_match.group(1)
                        row = row_for_channel(file_key, channel)
                        row["cache_entry"] = init_cache_match.group(2)
                        last_cache_channel_by_file[file_key] = channel
                        continue

                    if "nsHttpResponseHead::MustValidate ??" in line:
                        channel = last_cache_channel_by_file.get(file_key)
                        if channel:
                            pending_validate_channel_by_file[file_key] = channel
                        continue

                    if file_key in pending_validate_channel_by_file:
                        if "V/nsHttp " not in line:
                            continue
                        note = line.split("V/nsHttp ", 1)[-1].strip()
                        if note == "nsHttpResponseHead::MustValidate ??":
                            continue
                        channel = pending_validate_channel_by_file.pop(file_key)
                        row = row_for_channel(file_key, channel)
                        row["must_validate_note"] = note
                        row["must_validate"] = (
                            note.lower() != "no mandatory validation requirement"
                        )
                        continue
        except OSError:
            continue

    filtered_rows = []
    for row in rows:
        uri = row.get("uri")
        if not isinstance(uri, str) or not uri:
            continue
        filtered_rows.append(row)
    return filtered_rows


def browser_net_log_page_resource_rows(
    payload: dict[str, object],
    *,
    target_filter: set[str] | None = None,
) -> list[dict[str, object]]:
    rows = []
    for profile_name, target, run_index, _profile_run, browser_run in iter_browser_runs(
        payload, target_filter=target_filter
    ):
        page_resource_names = browser_timing_resource_names(browser_run, target=target)
        for row in browser_net_log_parent_resource_rows_for_run(browser_run):
            uri = row.get("uri")
            if not isinstance(uri, str) or uri not in page_resource_names:
                continue
            merged = dict(row)
            merged.update(
                {
                    "profile": profile_name,
                    "target": target,
                    "run_index": run_index,
                    "same_origin": origin_label(uri) == origin_label(target),
                }
            )
            rows.append(merged)
    return rows


def browser_net_log_cache_summary_rows(
    payload: dict[str, object],
    *,
    target_filter: set[str] | None = None,
) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in browser_net_log_page_resource_rows(payload, target_filter=target_filter):
        grouped[(str(row.get("profile", "")), str(row.get("target", "")))].append(row)

    output = []
    for (profile_name, target), rows in sorted(grouped.items()):
        output.append(
            {
                "profile": profile_name,
                "target": target,
                "rows": len(rows),
                "unique_uris": len(
                    {
                        str(row.get("uri", ""))
                        for row in rows
                        if str(row.get("uri", ""))
                    }
                ),
                "same_origin_rows": sum(
                    1 for row in rows if row.get("same_origin") is True
                ),
                "http11_rows": sum(
                    1
                    for row in rows
                    if str(row.get("http_version", "")).startswith("HTTP/1.1")
                ),
                "status_200_rows": sum(1 for row in rows if row.get("status_code") == 200),
                "status_304_rows": sum(1 for row in rows if row.get("status_code") == 304),
                "cache_entry_new_rows": sum(
                    1 for row in rows if row.get("cache_entry_new") is True
                ),
                "cache_entry_reused_rows": sum(
                    1 for row in rows if row.get("cache_entry_new") is False
                ),
                "must_validate_yes_rows": sum(
                    1 for row in rows if row.get("must_validate") is True
                ),
                "must_validate_no_rows": sum(
                    1 for row in rows if row.get("must_validate") is False
                ),
                "etag_rows": sum(1 for row in rows if row.get("etag")),
                "last_modified_rows": sum(
                    1 for row in rows if row.get("last_modified")
                ),
                "cache_control_max_age_rows": sum(
                    1
                    for row in rows
                    if "max-age=" in str(row.get("cache_control", "")).lower()
                ),
            }
        )
    return output


def resource_discovery_summary_rows(
    payload: dict[str, object],
    *,
    target_filter: set[str] | None = None,
) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str, str], list[dict[str, object]]] = defaultdict(list)
    for profile_name, target, _run_index, _profile_run, browser_run in iter_browser_runs(
        payload, target_filter=target_filter
    ):
        nav = browser_nav(browser_run)
        resources = browser_resources(browser_run)
        metric_by_resource: dict[str, dict[str, object]] = {}
        for resource in resources:
            row = resource_metric_row(resource, nav, resources)
            if row is None:
                continue
            metric_by_resource[str(row.get("resource", ""))] = row
        discovery_rows = browser_page_resource_discovery(browser_run)
        discovery_by_key: dict[str, list[dict[str, object]]] = defaultdict(list)
        for row in discovery_rows:
            url = str(row.get("url", ""))
            for key in resource_url_match_keys(url):
                discovery_by_key[key].append(row)
        for resource_url, metric in metric_by_resource.items():
            matched_rows = []
            seen_urls: set[str] = set()
            for key in resource_url_match_keys(resource_url):
                for row in discovery_by_key.get(key, []):
                    url = str(row.get("url", ""))
                    if url in seen_urls:
                        continue
                    matched_rows.append(row)
                    seen_urls.add(url)
            if not matched_rows:
                continue
            for row in matched_rows:
                merged = dict(row)
                merged.update(
                    {
                        "resource": resource_url,
                        "family": str(metric.get("family", "")),
                        "request_start_ms": metric.get("request_start_ms"),
                    }
                )
                grouped[
                    (
                        profile_name,
                        target,
                        str(metric.get("family", "")),
                    )
                ].append(merged)

    output = []
    for (profile_name, target, family), rows in sorted(grouped.items()):
        output.append(
            summarize_resource_discovery_group(
                profile_name=profile_name,
                target=target,
                family=family,
                rows=rows,
            )
        )
    return output


def pre_network_cancel_summary_rows(
    payload: dict[str, object],
    *,
    target_filter: set[str] | None = None,
) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str, str, str, bool], list[dict[str, object]]] = defaultdict(list)
    for profile_name, target, _run_index, _profile_run, browser_run in iter_browser_runs(
        payload, target_filter=target_filter
    ):
        nav = browser_nav(browser_run)
        resources = browser_resources(browser_run)
        activity_by_uri = browser_activity_summary_by_uri(browser_run)
        blocked_uri_counts = browser_request_blocked_uri_counter(browser_run)
        discovery_by_variant: dict[str, list[dict[str, object]]] = defaultdict(list)
        discovery_by_match_key: dict[str, list[dict[str, object]]] = defaultdict(list)
        for row in browser_page_resource_discovery(browser_run):
            url = str(row.get("url", ""))
            if not url:
                continue
            for key in resource_url_match_keys(url):
                discovery_by_match_key[key].append(row)
            variant = resource_variant_key(url)
            if variant:
                discovery_by_variant[variant].append(row)

        for resource in resources:
            metric = resource_metric_row(resource, nav, resources)
            if metric is None:
                continue
            resource_url = str(metric.get("resource", ""))
            if not resource_url:
                continue
            activity = activity_by_uri.get(resource_url)
            if not activity:
                continue
            duration_ms = numeric(metric.get("duration_ms")) or 0.0
            transfer_size_bytes = numeric(metric.get("transfer_size_bytes")) or 0.0
            encoded_body_size_bytes = (
                numeric(metric.get("encoded_body_size_bytes")) or 0.0
            )
            if (
                duration_ms != 0.0
                or transfer_size_bytes != 0.0
                or encoded_body_size_bytes != 0.0
            ):
                continue
            stop_request_rows = int(activity.get("stop_request_rows") or 0)
            examine_response_rows = int(activity.get("examine_response_rows") or 0)
            if stop_request_rows <= 0:
                continue
            if examine_response_rows > 0 or activity.get("any_socket_ports") is True:
                continue
            request_blocked = blocked_uri_counts[resource_url] > 0
            current_matches: list[dict[str, object]] = []
            if not any(
                discovery_by_match_key.get(key)
                for key in resource_url_match_keys(resource_url)
            ):
                variant = resource_variant_key(resource_url)
                if variant:
                    current_matches = [
                        row
                        for row in discovery_by_variant.get(variant, [])
                        if str(row.get("url", "")) and str(row.get("url", "")) != resource_url
                    ]
            current_families = sorted(
                {
                    resource_family(str(match.get("url", "")), "")
                    for match in current_matches
                    if str(match.get("url", ""))
                }
            )
            current_family = (
                current_families[0]
                if len(current_families) == 1
                else (
                    ", ".join(current_families[:3])
                    if current_families
                    else str(metric.get("family", ""))
                )
            )
            grouped[
                (
                    profile_name,
                    target,
                    str(metric.get("family", "")),
                    current_family,
                    request_blocked,
                )
            ].append(
                {
                    "resource": resource_url,
                    "request_start_ms": metric.get("request_start_ms"),
                    "stop_request_rows": stop_request_rows,
                    "channel_count": len(activity.get("channel_ids", set())),
                    "current_urls": [
                        str(match.get("url", ""))
                        for match in current_matches
                        if str(match.get("url", ""))
                    ],
                }
            )

    output = []
    for (profile_name, target, loaded_family, current_family, request_blocked), rows in sorted(
        grouped.items()
    ):
        request_starts = [
            value
            for row in rows
            if (value := numeric(row.get("request_start_ms"))) is not None
        ]
        loaded_freq: dict[str, int] = defaultdict(int)
        current_freq: dict[str, int] = defaultdict(int)
        stop_request_rows = 0
        channel_count = 0
        for row in rows:
            resource = str(row.get("resource", ""))
            if resource:
                loaded_freq[resource] += 1
            stop_request_rows += int(row.get("stop_request_rows") or 0)
            channel_count += int(row.get("channel_count") or 0)
            for current_url in row.get("current_urls", []):
                text = str(current_url or "")
                if text:
                    current_freq[text] += 1
        top_loaded = sorted(
            loaded_freq.items(),
            key=lambda item: (item[1], item[0]),
            reverse=True,
        )
        top_current = sorted(
            current_freq.items(),
            key=lambda item: (item[1], item[0]),
            reverse=True,
        )
        output.append(
            {
                "profile": profile_name,
                "target": target,
                "loaded_family": loaded_family,
                "current_family": current_family,
                "request_blocked": request_blocked,
                "resources": len(rows),
                "unique_resources": len(loaded_freq),
                "median_request_start_ms": median(request_starts),
                "stop_request_rows": stop_request_rows,
                "channel_count": channel_count,
                "top_loaded_resources": ", ".join(
                    compact_resource(name, 32) for name, _count in top_loaded[:3]
                ),
                "top_current_resources": ", ".join(
                    compact_resource(name, 32) for name, _count in top_current[:3]
                ),
            }
        )
    output.sort(
        key=lambda row: (
            1 if row.get("request_blocked") else 0,
            numeric(row.get("resources")) or 0.0,
            numeric(row.get("median_request_start_ms")) or 0.0,
        ),
        reverse=True,
    )
    return output


def summarize_resource_discovery_group(
    *,
    profile_name: str,
    target: str,
    family: str,
    rows: list[dict[str, object]],
) -> dict[str, object]:
    request_starts = [
        value
        for row in rows
        if (value := numeric(row.get("request_start_ms"))) is not None
    ]
    resource_urls = {
        str(row.get("resource", "")) for row in rows if str(row.get("resource", ""))
    }
    dom_only = 0
    css_only = 0
    dom_and_css = 0
    img_dom = 0
    css_background = 0
    css_font_face = 0
    css_stylesheet_freq: dict[str, int] = defaultdict(int)
    css_selector_freq: dict[str, int] = defaultdict(int)
    for row in rows:
        direct_ref_count = int(numeric(row.get("direct_ref_count")) or 0)
        css_ref_count = int(numeric(row.get("css_ref_count")) or 0)
        if direct_ref_count > 0 and css_ref_count <= 0:
            dom_only += 1
        elif css_ref_count > 0 and direct_ref_count <= 0:
            css_only += 1
        elif direct_ref_count > 0 and css_ref_count > 0:
            dom_and_css += 1
        dom_tags = row.get("dom_tags")
        if isinstance(dom_tags, list) and "img" in dom_tags:
            img_dom += 1
        css_properties = row.get("css_properties")
        if isinstance(css_properties, list) and any(
            "background" in str(value) for value in css_properties
        ):
            css_background += 1
        css_rule_kinds = row.get("css_rule_kinds")
        if isinstance(css_rule_kinds, list) and "@font-face" in css_rule_kinds:
            css_font_face += 1
        css_stylesheets = row.get("css_stylesheets")
        if isinstance(css_stylesheets, list):
            for value in css_stylesheets:
                text = str(value or "")
                if text:
                    css_stylesheet_freq[text] += 1
        css_selectors = row.get("css_selectors")
        if isinstance(css_selectors, list):
            for value in css_selectors:
                text = str(value or "")
                if text:
                    css_selector_freq[text] += 1
    top_stylesheets = sorted(
        css_stylesheet_freq.items(),
        key=lambda item: (item[1], item[0]),
        reverse=True,
    )
    top_selectors = sorted(
        css_selector_freq.items(),
        key=lambda item: (item[1], item[0]),
        reverse=True,
    )
    return {
        "profile": profile_name,
        "target": target,
        "family": family,
        "resources": len(rows),
        "unique_resources": len(resource_urls),
        "median_request_start_ms": median(request_starts),
        "dom_only_resources": dom_only,
        "css_only_resources": css_only,
        "dom_and_css_resources": dom_and_css,
        "img_dom_resources": img_dom,
        "css_background_resources": css_background,
        "css_font_face_resources": css_font_face,
        "top_css_stylesheets": ", ".join(
            compact_resource(name, 32) for name, _count in top_stylesheets[:3]
        ),
        "top_css_selectors": ", ".join(
            text for text, _count in top_selectors[:3]
        ),
    }


def resource_variant_swap_rows(
    payload: dict[str, object],
    *,
    target_filter: set[str] | None = None,
) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str, str, str], list[dict[str, object]]] = defaultdict(list)
    for profile_name, target, _run_index, _profile_run, browser_run in iter_browser_runs(
        payload, target_filter=target_filter
    ):
        nav = browser_nav(browser_run)
        resources = browser_resources(browser_run)
        metric_by_resource: dict[str, dict[str, object]] = {}
        discovery_by_variant: dict[str, list[dict[str, object]]] = defaultdict(list)
        discovery_by_match_key: dict[str, list[dict[str, object]]] = defaultdict(list)
        for resource in resources:
            row = resource_metric_row(resource, nav, resources)
            if row is None:
                continue
            metric_by_resource[str(row.get("resource", ""))] = row
        for row in browser_page_resource_discovery(browser_run):
            url = str(row.get("url", ""))
            if not url:
                continue
            for key in resource_url_match_keys(url):
                discovery_by_match_key[key].append(row)
            variant = resource_variant_key(url)
            if variant:
                discovery_by_variant[variant].append(row)
        for resource_url, metric in metric_by_resource.items():
            if any(
                discovery_by_match_key.get(key)
                for key in resource_url_match_keys(resource_url)
            ):
                continue
            variant = resource_variant_key(resource_url)
            if not variant:
                continue
            matches = discovery_by_variant.get(variant, [])
            if not matches:
                continue
            loaded_family = str(metric.get("family", ""))
            current_families = sorted(
                {
                    resource_family(str(match.get("url", "")), "")
                    for match in matches
                    if str(match.get("url", ""))
                }
            )
            current_family = current_families[0] if len(current_families) == 1 else ", ".join(current_families[:3])
            grouped[(profile_name, target, loaded_family, current_family)].append(
                {
                    "resource": resource_url,
                    "request_start_ms": metric.get("request_start_ms"),
                    "current_urls": [
                        str(match.get("url", ""))
                        for match in matches
                        if str(match.get("url", ""))
                    ],
                }
            )

    output = []
    for (profile_name, target, loaded_family, current_family), rows in sorted(
        grouped.items()
    ):
        request_starts = [
            value
            for row in rows
            if (value := numeric(row.get("request_start_ms"))) is not None
        ]
        loaded_freq: dict[str, int] = defaultdict(int)
        current_freq: dict[str, int] = defaultdict(int)
        for row in rows:
            resource = str(row.get("resource", ""))
            if resource:
                loaded_freq[resource] += 1
            for current_url in row.get("current_urls", []):
                current_freq[str(current_url)] += 1
        top_loaded = sorted(
            loaded_freq.items(),
            key=lambda item: (item[1], item[0]),
            reverse=True,
        )
        top_current = sorted(
            current_freq.items(),
            key=lambda item: (item[1], item[0]),
            reverse=True,
        )
        output.append(
            {
                "profile": profile_name,
                "target": target,
                "loaded_family": loaded_family,
                "current_family": current_family,
                "resources": len(rows),
                "median_request_start_ms": median(request_starts),
                "top_loaded_resources": ", ".join(
                    compact_resource(name, 32) for name, _count in top_loaded[:3]
                ),
                "top_current_resources": ", ".join(
                    compact_resource(name, 32) for name, _count in top_current[:3]
                ),
            }
        )
    output.sort(
        key=lambda row: (
            numeric(row.get("resources")) or 0.0,
            numeric(row.get("median_request_start_ms")) or 0.0,
        ),
        reverse=True,
    )
    return output


def limit_resource_variant_swap_rows(
    rows: list[dict[str, object]], *, limit: int
) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row.get("profile", "")), str(row.get("target", "")))].append(row)

    output = []
    for key in sorted(grouped):
        output.extend(grouped[key][:limit])
    return output


def limit_pre_network_cancel_summary_rows(
    rows: list[dict[str, object]], *, limit: int
) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row.get("profile", "")), str(row.get("target", "")))].append(row)

    output = []
    for key in sorted(grouped):
        output.extend(grouped[key][:limit])
    return output


def css_discovery_gate_summary_rows(
    payload: dict[str, object],
    *,
    target_filter: set[str] | None = None,
) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str, str, str], list[dict[str, object]]] = defaultdict(list)
    for profile_name, target, _run_index, _profile_run, browser_run in iter_browser_runs(
        payload, target_filter=target_filter
    ):
        nav = browser_nav(browser_run)
        resources = browser_resources(browser_run)
        metric_by_key: dict[str, dict[str, object]] = {}
        for resource in resources:
            row = resource_metric_row(resource, nav, resources)
            if row is None:
                continue
            resource_name = str(row.get("resource", ""))
            for key in resource_url_match_keys(resource_name):
                metric_by_key[key] = row
        for discovery_row in browser_page_resource_discovery(browser_run):
            css_stylesheets = discovery_row.get("css_stylesheets")
            if not isinstance(css_stylesheets, list) or not css_stylesheets:
                continue
            direct_ref_count = int(numeric(discovery_row.get("direct_ref_count")) or 0)
            css_ref_count = int(numeric(discovery_row.get("css_ref_count")) or 0)
            if css_ref_count <= 0:
                continue
            resource_url = str(discovery_row.get("url", ""))
            resource_metric = None
            for key in resource_url_match_keys(resource_url):
                resource_metric = metric_by_key.get(key)
                if resource_metric is not None:
                    break
            if resource_metric is None:
                continue
            for stylesheet_url in css_stylesheets:
                stylesheet_metric = None
                for key in resource_url_match_keys(str(stylesheet_url)):
                    stylesheet_metric = metric_by_key.get(key)
                    if stylesheet_metric is not None:
                        break
                if stylesheet_metric is None:
                    continue
                request_start = numeric(resource_metric.get("request_start_ms"))
                fetch_start = numeric(
                    resource_metric.get("fetch_to_request_ms")
                )
                actual_fetch_start = None
                if request_start is not None and fetch_start is not None:
                    actual_fetch_start = request_start - fetch_start
                stylesheet_end = numeric(stylesheet_metric.get("response_end_ms"))
                grouped[
                    (
                        profile_name,
                        target,
                        str(resource_metric.get("family", "")),
                        str(stylesheet_url),
                    )
                ].append(
                    {
                        "resource": resource_url,
                        "selectors": discovery_row.get("css_selectors"),
                        "request_start_after_stylesheet_end_ms": subtract(
                            request_start, stylesheet_end
                        ),
                        "fetch_start_after_stylesheet_end_ms": subtract(
                            actual_fetch_start, stylesheet_end
                        ),
                        "stylesheet_response_end_ms": stylesheet_end,
                        "direct_ref_count": direct_ref_count,
                    }
                )

    output = []
    for (profile_name, target, family, stylesheet), rows in sorted(grouped.items()):
        request_after = [
            value
            for row in rows
            if (
                value := numeric(
                    row.get("request_start_after_stylesheet_end_ms")
                )
            )
            is not None
        ]
        fetch_after = [
            value
            for row in rows
            if (
                value := numeric(
                    row.get("fetch_start_after_stylesheet_end_ms")
                )
            )
            is not None
        ]
        stylesheet_end = [
            value
            for row in rows
            if (
                value := numeric(row.get("stylesheet_response_end_ms"))
            )
            is not None
        ]
        selector_freq: dict[str, int] = defaultdict(int)
        unique_resources = {
            str(row.get("resource", "")) for row in rows if str(row.get("resource", ""))
        }
        for row in rows:
            selectors = row.get("selectors")
            if not isinstance(selectors, list):
                continue
            for selector in selectors:
                text = str(selector or "")
                if text:
                    selector_freq[text] += 1
        top_selectors = sorted(
            selector_freq.items(),
            key=lambda item: (item[1], item[0]),
            reverse=True,
        )
        output.append(
            {
                "profile": profile_name,
                "target": target,
                "family": family,
                "stylesheet": compact_resource(stylesheet, 32),
                "resources": len(unique_resources),
                "median_fetch_start_after_stylesheet_end_ms": median(fetch_after),
                "median_request_start_after_stylesheet_end_ms": median(request_after),
                "median_stylesheet_response_end_ms": median(stylesheet_end),
                "top_css_selectors": ", ".join(
                    selector for selector, _count in top_selectors[:3]
                ),
            }
        )
    output.sort(
        key=lambda row: (
            numeric(row.get("median_request_start_after_stylesheet_end_ms")) or -1.0,
            numeric(row.get("resources")) or -1.0,
        ),
        reverse=True,
    )
    return output


def limit_css_discovery_gate_rows(
    rows: list[dict[str, object]], *, limit: int
) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row.get("profile", "")), str(row.get("target", "")))].append(row)

    output = []
    for key in sorted(grouped):
        output.extend(grouped[key][:limit])
    return output


def limit_resource_discovery_summary_rows(
    rows: list[dict[str, object]], *, limit: int
) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row.get("profile", "")), str(row.get("target", "")))].append(row)

    output = []
    for key in sorted(grouped):
        rows_for_key = sorted(
            grouped[key],
            key=lambda row: (
                numeric(row.get("median_request_start_ms")) or -1.0,
                numeric(row.get("css_only_resources")) or -1.0,
                numeric(row.get("resources")) or -1.0,
            ),
            reverse=True,
        )
        output.extend(rows_for_key[:limit])
    return output


def counter_summary(values: list[str], *, limit: int = 3) -> str:
    counter = Counter(value for value in values if value)
    if not counter:
        return ""
    return ", ".join(
        f"{value}x{count}" if count > 1 else value
        for value, count in counter.most_common(limit)
    )


def bool_state_summary(
    values: list[object], *, true_label: str, false_label: str
) -> str:
    observed = [value for value in values if isinstance(value, bool)]
    if not observed:
        return ""
    true_count = sum(1 for value in observed if value is True)
    false_count = sum(1 for value in observed if value is False)
    total = len(observed)
    parts = []
    if true_count:
        parts.append(f"{true_label} {true_count}/{total}")
    if false_count:
        parts.append(f"{false_label} {false_count}/{total}")
    return ", ".join(parts)


def same_origin_blocker_cache_signal_rows(
    payload: dict[str, object],
    *,
    target_filter: set[str] | None = None,
) -> list[dict[str, object]]:
    cache_rows = browser_net_log_page_resource_rows(payload, target_filter=target_filter)
    cache_by_run_uri: dict[tuple[str, str, object, str], list[dict[str, object]]] = defaultdict(list)
    for row in cache_rows:
        cache_by_run_uri[
            (
                str(row.get("profile", "")),
                str(row.get("target", "")),
                row.get("run_index"),
                str(row.get("uri", "")),
            )
        ].append(row)

    grouped: dict[tuple[str, str, str, str, str], list[dict[str, object]]] = defaultdict(list)
    for row in same_origin_blocker_owner_rows(payload, target_filter=target_filter):
        grouped[
            (
                str(row.get("profile", "")),
                str(row.get("target", "")),
                str(row.get("blocker_resource", "")),
                str(row.get("blocker_type", "")),
                str(row.get("protocol", "")),
            )
        ].append(row)

    output = []
    for (profile_name, target, blocker_resource, blocker_type, protocol), rows in sorted(
        grouped.items()
    ):
        matches = []
        for blocker_row in rows:
            matches.extend(
                cache_by_run_uri.get(
                    (
                        profile_name,
                        target,
                        blocker_row.get("run_index"),
                        blocker_resource,
                    ),
                    [],
                )
            )
        if not matches:
            continue
        output.append(
            {
                "profile": profile_name,
                "target": target,
                "blocker": compact_resource(blocker_resource, 54),
                "blocker_resource": blocker_resource,
                "blocker_type": blocker_type,
                "protocol": protocol,
                "blocker_occurrences": len(rows),
                "net_log_matches": len(matches),
                "status_codes": counter_summary(
                    [str(match.get("status_code", "")) for match in matches]
                ),
                "cache_entry_summary": bool_state_summary(
                    [match.get("cache_entry_new") for match in matches],
                    true_label="new",
                    false_label="reused",
                ),
                "must_validate_summary": bool_state_summary(
                    [match.get("must_validate") for match in matches],
                    true_label="yes",
                    false_label="no",
                ),
                "cache_control_summary": counter_summary(
                    [str(match.get("cache_control", "")) for match in matches],
                    limit=2,
                ),
                "etag_summary": bool_state_summary(
                    [bool(match.get("etag")) for match in matches if "etag" in match],
                    true_label="present",
                    false_label="missing",
                ),
                "last_modified_summary": bool_state_summary(
                    [
                        bool(match.get("last_modified"))
                        for match in matches
                        if "last_modified" in match
                    ],
                    true_label="present",
                    false_label="missing",
                ),
                "content_type_summary": counter_summary(
                    [str(match.get("content_type", "")) for match in matches],
                    limit=2,
                ),
            }
        )
    output.sort(
        key=lambda row: (
            numeric(row.get("blocker_occurrences")) or 0.0,
            numeric(row.get("net_log_matches")) or 0.0,
            str(row.get("blocker", "")),
        ),
        reverse=True,
    )
    return output


def limit_blocker_cache_signal_rows(
    rows: list[dict[str, object]], *, limit: int
) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row.get("profile", "")), str(row.get("target", "")))].append(row)

    output = []
    for key in sorted(grouped):
        output.extend(grouped[key][:limit])
    return output


def max_active_count_in_interval(
    resources: list[dict[str, object]], start_ms: object, end_ms: object
) -> int:
    start = numeric(start_ms)
    end = numeric(end_ms)
    if start is None or end is None or end <= start:
        return 0
    points = {start, start + ((end - start) / 2.0)}
    end_probe = end - 0.001
    if end_probe >= start:
        points.add(end_probe)
    for resource in resources:
        for field in ("requestStart", "responseStart", "responseEnd"):
            value = numeric(resource.get(field))
            if value is not None and start <= value < end:
                points.add(value)
    return max((active_count_at_ms(resources, point) for point in points), default=0)


def phase_summary_rows(
    payload: dict[str, object],
    *,
    target_filter: set[str] | None = None,
) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], list[tuple[dict[str, object], dict[str, object]]]] = defaultdict(list)
    for profile_name, target, _run_index, profile_run, browser_run in iter_browser_runs(
        payload, target_filter=target_filter
    ):
        grouped[(profile_name, target)].append((profile_run, browser_run))

    rows = []
    for (profile_name, target), entries in sorted(grouped.items()):
        load_ms = [value for _profile_run, browser_run in entries if (value := numeric(browser_run.get("load_ms"))) is not None]
        launch_load_ms = []
        nav_response_ms = []
        response_to_dom_ms = []
        dom_to_load_ms = []
        slowest_ms = []
        for profile_run, browser_run in entries:
            nav = browser_nav(browser_run)
            if (boot := launch_ready_seconds_for_run(profile_run)) is not None and (
                load := numeric(browser_run.get("load_ms"))
            ) is not None:
                launch_load_ms.append(boot * 1000 + load)
            if (value := numeric(nav.get("responseStart"))) is not None:
                nav_response_ms.append(value)
            if (value := nav_phase(nav, "responseStart", "domContentLoadedEventEnd")) is not None:
                response_to_dom_ms.append(value)
            if (value := nav_phase(nav, "domContentLoadedEventEnd", "loadEventEnd")) is not None:
                dom_to_load_ms.append(value)
            if (value := run_slowest_resource_ms(browser_run)) is not None:
                slowest_ms.append(value)
        rows.append(
            {
                "profile": profile_name,
                "target": target,
                "ok_runs": len(entries),
                "median_load_ms": median(load_ms),
                "median_launch_load_ms": median(launch_load_ms),
                "median_nav_response_start_ms": median(nav_response_ms),
                "median_nav_response_to_dom_ms": median(response_to_dom_ms),
                "median_nav_dom_to_load_ms": median(dom_to_load_ms),
                "median_slowest_resource_ms": median(slowest_ms),
            }
        )
    return rows


def resource_metric_row(
    resource: dict[str, object], nav: dict[str, object], resources: list[dict[str, object]]
) -> dict[str, object] | None:
    duration_ms = numeric(resource.get("duration"))
    if duration_ms is None:
        return None
    fetch_to_request_ms = phase_ms(
        resource.get("fetchStart")
        if numeric(resource.get("fetchStart")) is not None
        else resource.get("startTime"),
        resource.get("requestStart"),
    )
    wait_ms = phase_ms(resource.get("requestStart"), resource.get("responseStart"))
    receive_ms = phase_ms(resource.get("responseStart"), resource.get("responseEnd"))
    response_end_ms = numeric(resource.get("responseEnd"))
    load_end_ms = numeric(nav.get("loadEventEnd"))
    dom_end_ms = numeric(nav.get("domContentLoadedEventEnd"))
    end_before_load_ms = None
    if response_end_ms is not None and load_end_ms is not None:
        end_before_load_ms = load_end_ms - response_end_ms
    tail_after_dom_ms = None
    if response_end_ms is not None and dom_end_ms is not None:
        tail_after_dom_ms = max(0.0, response_end_ms - dom_end_ms)
    peer_resources = same_origin_protocol_resources(resource, resources)
    active_same_origin_at_request = active_count_at_ms(
        peer_resources, resource.get("requestStart")
    )
    queue_start = (
        resource.get("fetchStart")
        if numeric(resource.get("fetchStart")) is not None
        else resource.get("startTime")
    )
    max_same_origin_active_in_queue = max_active_count_in_interval(
        peer_resources, queue_start, resource.get("requestStart")
    )
    blockers = blockers_before_request(resource, peer_resources)
    slot_pressure_likely = (
        protocol_label(resource.get("nextHopProtocol")) == "http/1.1"
        and (fetch_to_request_ms or 0.0) >= 1000.0
        and max_same_origin_active_in_queue >= 6
    )
    return {
        "resource": str(resource.get("name") or ""),
        "resource_type": str(resource.get("initiatorType") or "unknown"),
        "family": resource_family(
            str(resource.get("name") or ""),
            str(resource.get("initiatorType") or "unknown"),
        ),
        "protocol": protocol_label(resource.get("nextHopProtocol")),
        "request_start_ms": numeric(resource.get("requestStart")),
        "response_start_ms": numeric(resource.get("responseStart")),
        "duration_ms": duration_ms,
        "fetch_to_request_ms": fetch_to_request_ms,
        "wait_ms": wait_ms,
        "receive_ms": receive_ms,
        "response_end_ms": response_end_ms,
        "transfer_size_bytes": numeric(resource.get("transferSize")),
        "encoded_body_size_bytes": numeric(resource.get("encodedBodySize")),
        "decoded_body_size_bytes": numeric(resource.get("decodedBodySize")),
        "end_before_load_ms": end_before_load_ms,
        "tail_after_dom_ms": tail_after_dom_ms,
        "active_same_origin_at_request": active_same_origin_at_request,
        "max_same_origin_active_in_queue": max_same_origin_active_in_queue,
        "blockers_before_request": len(blockers),
        "top_blockers": ", ".join(
            compact_resource(str(blocker.get("name", ""))) for blocker in blockers[:6]
        ),
        "slot_pressure_likely": slot_pressure_likely,
        "slow_2s": duration_ms >= 2000.0,
        "queued_1000ms": (fetch_to_request_ms or 0.0) >= 1000.0,
        "ending_final_1s": (
            end_before_load_ms is not None and 0.0 <= end_before_load_ms <= 1000.0
        ),
    }


def subtract(left: object, right: object) -> float | None:
    left_num = numeric(left)
    right_num = numeric(right)
    if left_num is None or right_num is None:
        return None
    return left_num - right_num


def phase_ms(start: object, end: object) -> float | None:
    delta = subtract(end, start)
    if delta is None:
        return None
    return max(0.0, delta)


def resource_tail_summary_rows(
    payload: dict[str, object],
    *,
    target_filter: set[str] | None = None,
) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for profile_name, target, _run_index, _profile_run, browser_run in iter_browser_runs(
        payload, target_filter=target_filter
    ):
        nav = browser_nav(browser_run)
        resources = browser_resources(browser_run)
        for resource in resources:
            row = resource_metric_row(resource, nav, resources)
            if row is not None:
                grouped[(profile_name, target)].append(row)

    rows = []
    for (profile_name, target), metrics in sorted(grouped.items()):
        rows.append(summarize_resource_metric_group(profile_name, target, metrics))
    return rows


def summarize_resource_metric_group(
    profile_name: str,
    target: str,
    metrics: list[dict[str, object]],
) -> dict[str, object]:
    fetch_to_request = [
        value
        for row in metrics
        if (value := numeric(row.get("fetch_to_request_ms"))) is not None
    ]
    active_at_request = [
        value
        for row in metrics
        if (value := numeric(row.get("active_same_origin_at_request"))) is not None
    ]
    active_in_queue = [
        value
        for row in metrics
        if (value := numeric(row.get("max_same_origin_active_in_queue"))) is not None
    ]
    durations = [value for row in metrics if (value := numeric(row.get("duration_ms"))) is not None]
    waits = [value for row in metrics if (value := numeric(row.get("wait_ms"))) is not None]
    receives = [value for row in metrics if (value := numeric(row.get("receive_ms"))) is not None]
    response_ends = [value for row in metrics if (value := numeric(row.get("response_end_ms"))) is not None]
    tails = [value for row in metrics if (value := numeric(row.get("tail_after_dom_ms"))) is not None]
    end_before_loads = [value for row in metrics if (value := numeric(row.get("end_before_load_ms"))) is not None]
    return {
        "profile": profile_name,
        "target": target,
        "resources": len(metrics),
        "queued_1000ms": sum(1 for row in metrics if row.get("queued_1000ms")),
        "slot_pressure_rows": sum(
            1 for row in metrics if row.get("slot_pressure_likely")
        ),
        "slow_resources_2s": sum(1 for row in metrics if row.get("slow_2s")),
        "resources_ending_final_1s": sum(
            1 for row in metrics if row.get("ending_final_1s")
        ),
        "median_fetch_to_request_ms": median(fetch_to_request),
        "max_fetch_to_request_ms": max(fetch_to_request) if fetch_to_request else None,
        "median_active_same_origin_at_request": median(active_at_request),
        "median_max_same_origin_active_in_queue": median(active_in_queue),
        "max_same_origin_active_in_queue": max(active_in_queue) if active_in_queue else None,
        "median_duration_ms": median(durations),
        "median_wait_ms": median(waits),
        "median_receive_ms": median(receives),
        "max_response_end_ms": max(response_ends) if response_ends else None,
        "max_tail_after_dom_ms": max(tails) if tails else None,
        "median_end_before_load_ms": median(end_before_loads),
    }


def top_resource_rows(
    payload: dict[str, object],
    *,
    target_filter: set[str] | None = None,
    limit: int = 8,
) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str, str, str], list[dict[str, object]]] = defaultdict(list)
    for profile_name, target, _run_index, _profile_run, browser_run in iter_browser_runs(
        payload, target_filter=target_filter
    ):
        nav = browser_nav(browser_run)
        resources = browser_resources(browser_run)
        for resource in resources:
            row = resource_metric_row(resource, nav, resources)
            if row is None or not row["resource"]:
                continue
            grouped[(profile_name, target, row["resource"], row["resource_type"])].append(
                row
            )

    grouped_by_profile_target: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for (profile_name, target, resource_name, resource_type), rows in grouped.items():
        grouped_by_profile_target[(profile_name, target)].append(
            summarize_named_resource_group(
                profile_name=profile_name,
                target=target,
                resource_name=resource_name,
                resource_type=resource_type,
                metrics=rows,
            )
        )

    output = []
    for key in sorted(grouped_by_profile_target):
        rows = sorted(
            grouped_by_profile_target[key],
            key=lambda row: (
                numeric(row.get("median_tail_after_dom_ms")) or -1.0,
                numeric(row.get("median_duration_ms")) or -1.0,
                numeric(row.get("runs")) or -1.0,
            ),
            reverse=True,
        )
        output.extend(rows[:limit])
    return output


def summarize_named_resource_group(
    *,
    profile_name: str,
    target: str,
    resource_name: str,
    resource_type: str,
    metrics: list[dict[str, object]],
) -> dict[str, object]:
    fetch_to_request = [
        value
        for row in metrics
        if (value := numeric(row.get("fetch_to_request_ms"))) is not None
    ]
    active_in_queue = [
        value
        for row in metrics
        if (value := numeric(row.get("max_same_origin_active_in_queue"))) is not None
    ]
    durations = [value for row in metrics if (value := numeric(row.get("duration_ms"))) is not None]
    waits = [value for row in metrics if (value := numeric(row.get("wait_ms"))) is not None]
    receives = [value for row in metrics if (value := numeric(row.get("receive_ms"))) is not None]
    tails = [value for row in metrics if (value := numeric(row.get("tail_after_dom_ms"))) is not None]
    end_before_loads = [value for row in metrics if (value := numeric(row.get("end_before_load_ms"))) is not None]
    return {
        "profile": profile_name,
        "target": target,
        "resource": resource_name,
        "resource_type": resource_type,
        "protocol": str(metrics[0].get("protocol", "")) if metrics else "",
        "runs": len(metrics),
        "median_fetch_to_request_ms": median(fetch_to_request),
        "median_max_same_origin_active_in_queue": median(active_in_queue),
        "slot_pressure_runs": sum(
            1 for row in metrics if row.get("slot_pressure_likely")
        ),
        "median_duration_ms": median(durations),
        "median_wait_ms": median(waits),
        "median_receive_ms": median(receives),
        "median_tail_after_dom_ms": median(tails),
        "median_end_before_load_ms": median(end_before_loads),
    }


def resource_delta_rows(
    payload: dict[str, object],
    *,
    target_filter: set[str] | None = None,
    baseline_profile: str | None = None,
    compare_profile: str | None = None,
    limit: int = 8,
) -> list[dict[str, object]]:
    grouped = top_resource_rows(payload, target_filter=target_filter, limit=100000)
    if not grouped:
        return []
    available_profiles = sorted({str(row["profile"]) for row in grouped})
    if baseline_profile is None:
        baseline_profile = default_baseline_profile(available_profiles)
    if compare_profile is None:
        compare_profile = default_compare_profile(available_profiles, baseline_profile)
    if not baseline_profile or not compare_profile:
        return []

    baseline_map = {
        (str(row["target"]), str(row["resource"]), str(row["resource_type"])): row
        for row in grouped
        if row["profile"] == baseline_profile
    }
    compare_rows = [
        row for row in grouped if row["profile"] == compare_profile
    ]
    joined = []
    for row in compare_rows:
        key = (str(row["target"]), str(row["resource"]), str(row["resource_type"]))
        baseline = baseline_map.get(key)
        if baseline is None:
            continue
        joined.append(
            {
                "target": key[0],
                "resource": key[1],
                "resource_type": key[2],
                "compare_profile": compare_profile,
                "baseline_profile": baseline_profile,
                "compare_fetch_to_request_ms": row.get("median_fetch_to_request_ms"),
                "baseline_fetch_to_request_ms": baseline.get(
                    "median_fetch_to_request_ms"
                ),
                "compare_max_same_origin_active_in_queue": row.get(
                    "median_max_same_origin_active_in_queue"
                ),
                "baseline_max_same_origin_active_in_queue": baseline.get(
                    "median_max_same_origin_active_in_queue"
                ),
                "delta_max_same_origin_active_in_queue": subtract(
                    row.get("median_max_same_origin_active_in_queue"),
                    baseline.get("median_max_same_origin_active_in_queue"),
                ),
                "delta_fetch_to_request_ms": subtract(
                    row.get("median_fetch_to_request_ms"),
                    baseline.get("median_fetch_to_request_ms"),
                ),
                "compare_wait_ms": row.get("median_wait_ms"),
                "baseline_wait_ms": baseline.get("median_wait_ms"),
                "delta_wait_ms": subtract(
                    row.get("median_wait_ms"),
                    baseline.get("median_wait_ms"),
                ),
                "compare_receive_ms": row.get("median_receive_ms"),
                "baseline_receive_ms": baseline.get("median_receive_ms"),
                "delta_receive_ms": subtract(
                    row.get("median_receive_ms"),
                    baseline.get("median_receive_ms"),
                ),
                "compare_duration_ms": row.get("median_duration_ms"),
                "baseline_duration_ms": baseline.get("median_duration_ms"),
                "delta_duration_ms": subtract(
                    row.get("median_duration_ms"),
                    baseline.get("median_duration_ms"),
                ),
                "compare_tail_after_dom_ms": row.get("median_tail_after_dom_ms"),
                "baseline_tail_after_dom_ms": baseline.get("median_tail_after_dom_ms"),
                "delta_tail_after_dom_ms": subtract(
                    row.get("median_tail_after_dom_ms"),
                    baseline.get("median_tail_after_dom_ms"),
                ),
            }
        )
        joined[-1]["phase_hint"] = resource_delta_phase_hint(joined[-1])
    joined.sort(
        key=lambda row: (
            abs(numeric(row.get("delta_fetch_to_request_ms")) or 0.0),
            abs(numeric(row.get("delta_tail_after_dom_ms")) or 0.0),
            abs(numeric(row.get("delta_duration_ms")) or 0.0),
        ),
        reverse=True,
    )
    return joined[:limit]


def resource_family_summary_rows(
    payload: dict[str, object],
    *,
    target_filter: set[str] | None = None,
) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str, str], list[dict[str, object]]] = defaultdict(list)
    for profile_name, target, _run_index, _profile_run, browser_run in iter_browser_runs(
        payload, target_filter=target_filter
    ):
        nav = browser_nav(browser_run)
        resources = browser_resources(browser_run)
        for resource in resources:
            row = resource_metric_row(resource, nav, resources)
            if row is None:
                continue
            family = str(row.get("family") or "")
            if not family:
                continue
            grouped[(profile_name, target, family)].append(row)

    rows = []
    for (profile_name, target, family), metrics in sorted(grouped.items()):
        rows.append(
            summarize_resource_family_group(
                profile_name=profile_name,
                target=target,
                family=family,
                metrics=metrics,
            )
        )
    return rows


def summarize_resource_family_group(
    *,
    profile_name: str,
    target: str,
    family: str,
    metrics: list[dict[str, object]],
) -> dict[str, object]:
    request_starts = [
        value
        for row in metrics
        if (value := numeric(row.get("request_start_ms"))) is not None
    ]
    fetch_to_request = [
        value
        for row in metrics
        if (value := numeric(row.get("fetch_to_request_ms"))) is not None
    ]
    waits = [value for row in metrics if (value := numeric(row.get("wait_ms"))) is not None]
    receives = [
        value for row in metrics if (value := numeric(row.get("receive_ms"))) is not None
    ]
    durations = [
        value
        for row in metrics
        if (value := numeric(row.get("duration_ms"))) is not None
    ]
    transfer_sizes = [
        bytes_to_kib(value)
        for row in metrics
        if (value := numeric(row.get("transfer_size_bytes"))) is not None
    ]
    encoded_sizes = [
        bytes_to_kib(value)
        for row in metrics
        if (value := numeric(row.get("encoded_body_size_bytes"))) is not None
    ]
    resource_freq: dict[str, int] = defaultdict(int)
    for row in metrics:
        resource = str(row.get("resource", ""))
        if resource:
            resource_freq[resource] += 1
    top_resources = sorted(
        resource_freq.items(),
        key=lambda item: (item[1], item[0]),
        reverse=True,
    )
    return {
        "profile": profile_name,
        "target": target,
        "family": family,
        "resources": len(metrics),
        "unique_resources": len(resource_freq),
        "median_request_start_ms": median(request_starts),
        "median_fetch_to_request_ms": median(fetch_to_request),
        "median_wait_ms": median(waits),
        "median_receive_ms": median(receives),
        "median_duration_ms": median(durations),
        "median_transfer_size_kib": median(transfer_sizes),
        "median_encoded_body_kib": median(encoded_sizes),
        "top_resources": ", ".join(
            compact_resource(resource, 36)
            for resource, _count in top_resources[:3]
        ),
    }


def limit_resource_family_summary_rows(
    rows: list[dict[str, object]], *, limit: int
) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row.get("profile", "")), str(row.get("target", "")))].append(row)

    output = []
    for key in sorted(grouped):
        rows_for_key = sorted(
            grouped[key],
            key=lambda row: (
                numeric(row.get("median_request_start_ms")) or -1.0,
                numeric(row.get("median_duration_ms")) or -1.0,
                numeric(row.get("resources")) or -1.0,
            ),
            reverse=True,
        )
        output.extend(rows_for_key[:limit])
    return output


def resource_family_delta_rows(
    payload: dict[str, object],
    *,
    target_filter: set[str] | None = None,
    baseline_profile: str | None = None,
    compare_profile: str | None = None,
    limit: int = 8,
) -> list[dict[str, object]]:
    grouped = resource_family_summary_rows(payload, target_filter=target_filter)
    if not grouped:
        return []
    available_profiles = sorted({str(row["profile"]) for row in grouped})
    if baseline_profile is None:
        baseline_profile = default_baseline_profile(available_profiles)
    if compare_profile is None:
        compare_profile = default_compare_profile(available_profiles, baseline_profile)
    if not baseline_profile or not compare_profile:
        return []

    baseline_map = {
        (str(row["target"]), str(row["family"])): row
        for row in grouped
        if row["profile"] == baseline_profile
    }
    compare_rows = [row for row in grouped if row["profile"] == compare_profile]
    joined = []
    for row in compare_rows:
        key = (str(row["target"]), str(row["family"]))
        baseline = baseline_map.get(key)
        if baseline is None:
            continue
        joined.append(
            {
                "target": key[0],
                "family": key[1],
                "compare_profile": compare_profile,
                "baseline_profile": baseline_profile,
                "compare_request_start_ms": row.get("median_request_start_ms"),
                "baseline_request_start_ms": baseline.get("median_request_start_ms"),
                "delta_request_start_ms": subtract(
                    row.get("median_request_start_ms"),
                    baseline.get("median_request_start_ms"),
                ),
                "delta_fetch_to_request_ms": subtract(
                    row.get("median_fetch_to_request_ms"),
                    baseline.get("median_fetch_to_request_ms"),
                ),
                "delta_wait_ms": subtract(
                    row.get("median_wait_ms"),
                    baseline.get("median_wait_ms"),
                ),
                "delta_receive_ms": subtract(
                    row.get("median_receive_ms"),
                    baseline.get("median_receive_ms"),
                ),
                "delta_duration_ms": subtract(
                    row.get("median_duration_ms"),
                    baseline.get("median_duration_ms"),
                ),
                "delta_encoded_body_kib": subtract(
                    row.get("median_encoded_body_kib"),
                    baseline.get("median_encoded_body_kib"),
                ),
            }
        )
        joined[-1]["phase_hint"] = resource_family_delta_phase_hint(joined[-1])
    joined.sort(
        key=lambda row: (
            abs(numeric(row.get("delta_duration_ms")) or 0.0),
            abs(numeric(row.get("delta_request_start_ms")) or 0.0),
            abs(numeric(row.get("delta_fetch_to_request_ms")) or 0.0),
        ),
        reverse=True,
    )
    return joined[:limit]


def default_baseline_profile(profiles: list[str]) -> str | None:
    for candidate in (
        "bundled_c_tor_browser",
        "local_c_tor_browser_cold",
    ):
        if candidate in profiles:
            return candidate
    return profiles[0] if profiles else None


def default_compare_profile(
    profiles: list[str], baseline_profile: str | None
) -> str | None:
    for candidate in (
        "bundled_c_tor_browser_seeded",
        "local_c_tor_browser_seeded",
    ):
        if candidate in profiles and candidate != baseline_profile:
            return candidate
    for profile in profiles:
        if profile != baseline_profile:
            return profile
    return None


def same_origin_pressure_summary_rows(
    payload: dict[str, object],
    *,
    target_filter: set[str] | None = None,
) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for profile_name, target, _run_index, _profile_run, browser_run in iter_browser_runs(
        payload, target_filter=target_filter
    ):
        nav = browser_nav(browser_run)
        resources = browser_resources(browser_run)
        for resource in resources:
            row = resource_metric_row(resource, nav, resources)
            if row is not None:
                grouped[(profile_name, target)].append(row)

    output = []
    for (profile_name, target), metrics in sorted(grouped.items()):
        summary = summarize_resource_metric_group(profile_name, target, metrics)
        named_groups: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
        for row in metrics:
            named_groups[(str(row.get("resource", "")), str(row.get("resource_type", "")))].append(
                row
            )
        slot_named = []
        for (resource_name, _resource_type), rows in named_groups.items():
            slot_runs = sum(1 for row in rows if row.get("slot_pressure_likely"))
            if slot_runs <= 0:
                continue
            slot_named.append(
                (
                    slot_runs,
                    median(
                        [
                            value
                            for row in rows
                            if (value := numeric(row.get("fetch_to_request_ms"))) is not None
                        ]
                    )
                    or 0.0,
                    compact_resource(resource_name),
                )
            )
        slot_named.sort(reverse=True)
        summary["top_slot_pressure_resources"] = ", ".join(
            name for _runs, _queue, name in slot_named[:5]
        )
        output.append(summary)
    return output


def iter_slot_pressure_resources(
    payload: dict[str, object],
    *,
    target_filter: set[str] | None = None,
):
    for profile_name, target, run_index, _profile_run, browser_run in iter_browser_runs(
        payload, target_filter=target_filter
    ):
        nav = browser_nav(browser_run)
        resources = browser_resources(browser_run)
        for resource in resources:
            row = resource_metric_row(resource, nav, resources)
            if row is None or not row.get("slot_pressure_likely"):
                continue
            yield profile_name, target, run_index, resource, resources, row


def same_origin_blocker_rows(
    payload: dict[str, object],
    *,
    target_filter: set[str] | None = None,
) -> list[dict[str, object]]:
    rows = []
    for profile_name, target, run_index, _resource, _resources, row in iter_slot_pressure_resources(
        payload,
        target_filter=target_filter,
    ):
        rows.append(
            {
                "profile": profile_name,
                "target": target,
                "run_index": run_index,
                "resource": compact_resource(str(row.get("resource", "")), 54),
                "resource_type": row.get("resource_type"),
                "fetch_to_request_ms": row.get("fetch_to_request_ms"),
                "blockers_before_request": row.get("blockers_before_request"),
                "top_blockers": row.get("top_blockers", ""),
            }
        )
    rows.sort(
        key=lambda row: (
            numeric(row.get("fetch_to_request_ms")) or 0.0,
            numeric(row.get("blockers_before_request")) or 0.0,
        ),
        reverse=True,
    )
    return rows


def same_origin_blocker_summary_rows(
    payload: dict[str, object],
    *,
    target_filter: set[str] | None = None,
) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in same_origin_blocker_rows(payload, target_filter=target_filter):
        grouped[(str(row.get("profile", "")), str(row.get("target", "")))].append(row)

    output = []
    for (profile_name, target), rows in sorted(grouped.items()):
        blocker_counts = [
            value
            for row in rows
            if (value := numeric(row.get("blockers_before_request"))) is not None
        ]
        blocker_freq: dict[str, int] = defaultdict(int)
        for row in rows:
            for blocker in str(row.get("top_blockers", "")).split(", "):
                if blocker:
                    blocker_freq[blocker] += 1
        top_blockers = sorted(
            blocker_freq.items(), key=lambda item: (item[1], item[0]), reverse=True
        )
        output.append(
            {
                "profile": profile_name,
                "target": target,
                "slot_pressure_rows": len(rows),
                "median_blockers_before_request": median(blocker_counts),
                "max_blockers_before_request": max(blocker_counts)
                if blocker_counts
                else None,
                "top_blockers": ", ".join(
                    blocker for blocker, _count in top_blockers[:5]
                ),
            }
        )
    return output


def same_origin_blocker_owner_rows(
    payload: dict[str, object],
    *,
    target_filter: set[str] | None = None,
) -> list[dict[str, object]]:
    rows = []
    for profile_name, target, run_index, resource, resources, row in iter_slot_pressure_resources(
        payload,
        target_filter=target_filter,
    ):
        peer_resources = same_origin_protocol_resources(resource, resources)
        queue_start = (
            resource.get("fetchStart")
            if numeric(resource.get("fetchStart")) is not None
            else resource.get("startTime")
        )
        request_start = resource.get("requestStart")
        queued_resource = str(row.get("resource", ""))
        queued_resource_display = compact_resource(queued_resource, 54)
        for blocker in blockers_before_request(resource, peer_resources):
            blocker_resource = str(blocker.get("name") or "")
            rows.append(
                {
                    "profile": profile_name,
                    "target": target,
                    "run_index": run_index,
                    "queued_resource": queued_resource,
                    "queued_resource_display": queued_resource_display,
                    "queued_fetch_to_request_ms": row.get("fetch_to_request_ms"),
                    "blocker_resource": blocker_resource,
                    "blocker": compact_resource(blocker_resource, 54),
                    "blocker_type": str(blocker.get("initiatorType") or "unknown"),
                    "protocol": protocol_label(blocker.get("nextHopProtocol")),
                    "blocker_duration_ms": phase_ms(
                        blocker.get("requestStart"), blocker.get("responseEnd")
                    ),
                    "blocker_wait_ms": phase_ms(
                        blocker.get("requestStart"), blocker.get("responseStart")
                    ),
                    "blocker_receive_ms": phase_ms(
                        blocker.get("responseStart"), blocker.get("responseEnd")
                    ),
                    "blocker_remaining_at_request_ms": phase_ms(
                        request_start, blocker.get("responseEnd")
                    ),
                    "blocker_age_at_request_ms": phase_ms(
                        blocker.get("requestStart"), request_start
                    ),
                    "blocker_overlap_in_queue_ms": resource_active_overlap_ms(
                        blocker, queue_start, request_start
                    ),
                }
            )
    rows.sort(
        key=lambda row: (
            numeric(row.get("blocker_remaining_at_request_ms")) or 0.0,
            numeric(row.get("blocker_duration_ms")) or 0.0,
            numeric(row.get("queued_fetch_to_request_ms")) or 0.0,
        ),
        reverse=True,
    )
    return rows


def same_origin_blocker_owner_summary_rows(
    payload: dict[str, object],
    *,
    target_filter: set[str] | None = None,
) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str, str, str, str], list[dict[str, object]]] = defaultdict(list)
    for row in same_origin_blocker_owner_rows(payload, target_filter=target_filter):
        grouped[
            (
                str(row.get("profile", "")),
                str(row.get("target", "")),
                str(row.get("blocker_resource", "")),
                str(row.get("blocker_type", "")),
                str(row.get("protocol", "")),
            )
        ].append(row)

    output = []
    for (profile_name, target, blocker_resource, blocker_type, protocol), rows in sorted(
        grouped.items()
    ):
        blocker_durations = [
            value
            for row in rows
            if (value := numeric(row.get("blocker_duration_ms"))) is not None
        ]
        blocker_waits = [
            value
            for row in rows
            if (value := numeric(row.get("blocker_wait_ms"))) is not None
        ]
        blocker_receives = [
            value
            for row in rows
            if (value := numeric(row.get("blocker_receive_ms"))) is not None
        ]
        blocker_remaining = [
            value
            for row in rows
            if (value := numeric(row.get("blocker_remaining_at_request_ms")))
            is not None
        ]
        blocker_ages = [
            value
            for row in rows
            if (value := numeric(row.get("blocker_age_at_request_ms"))) is not None
        ]
        blocker_overlap = [
            value
            for row in rows
            if (value := numeric(row.get("blocker_overlap_in_queue_ms"))) is not None
        ]
        queued_resource_freq: dict[str, int] = defaultdict(int)
        for row in rows:
            queued_resource = str(row.get("queued_resource", ""))
            if queued_resource:
                queued_resource_freq[queued_resource] += 1
        top_queued = sorted(
            queued_resource_freq.items(),
            key=lambda item: (item[1], item[0]),
            reverse=True,
        )
        output.append(
            {
                "profile": profile_name,
                "target": target,
                "blocker": compact_resource(blocker_resource, 54),
                "blocker_resource": blocker_resource,
                "blocker_type": blocker_type,
                "protocol": protocol,
                "blocker_occurrences": len(rows),
                "runs": len({row.get("run_index") for row in rows}),
                "queued_resource_count": len(queued_resource_freq),
                "median_blocker_duration_ms": median(blocker_durations),
                "median_blocker_wait_ms": median(blocker_waits),
                "median_blocker_receive_ms": median(blocker_receives),
                "median_blocker_remaining_at_request_ms": median(
                    blocker_remaining
                ),
                "median_blocker_age_at_request_ms": median(blocker_ages),
                "median_blocker_overlap_in_queue_ms": median(blocker_overlap),
                "top_queued_resources": ", ".join(
                    compact_resource(name, 42) for name, _count in top_queued[:3]
                ),
            }
        )
    output.sort(
        key=lambda row: (
            numeric(row.get("blocker_occurrences")) or 0.0,
            numeric(row.get("median_blocker_remaining_at_request_ms")) or 0.0,
            numeric(row.get("median_blocker_duration_ms")) or 0.0,
            str(row.get("blocker", "")),
        ),
        reverse=True,
    )
    return output


def same_origin_blocker_family_summary_rows(
    payload: dict[str, object],
    *,
    target_filter: set[str] | None = None,
) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str, str, str], list[dict[str, object]]] = defaultdict(list)
    for row in same_origin_blocker_owner_rows(payload, target_filter=target_filter):
        queued_family = resource_family(str(row.get("queued_resource", "")), "")
        blocker_family = resource_family(str(row.get("blocker_resource", "")), "")
        grouped[
            (
                str(row.get("profile", "")),
                str(row.get("target", "")),
                queued_family,
                blocker_family,
            )
        ].append(row)

    output = []
    for (profile_name, target, queued_family, blocker_family), rows in sorted(
        grouped.items()
    ):
        remaining = [
            value
            for row in rows
            if (value := numeric(row.get("blocker_remaining_at_request_ms")))
            is not None
        ]
        overlap = [
            value
            for row in rows
            if (value := numeric(row.get("blocker_overlap_in_queue_ms"))) is not None
        ]
        blocker_resource_freq: dict[str, int] = defaultdict(int)
        queued_resource_freq: dict[str, int] = defaultdict(int)
        for row in rows:
            blocker_resource = str(row.get("blocker_resource", ""))
            if blocker_resource:
                blocker_resource_freq[blocker_resource] += 1
            queued_resource = str(row.get("queued_resource", ""))
            if queued_resource:
                queued_resource_freq[queued_resource] += 1
        top_blockers = sorted(
            blocker_resource_freq.items(),
            key=lambda item: (item[1], item[0]),
            reverse=True,
        )
        output.append(
            {
                "profile": profile_name,
                "target": target,
                "queued_family": queued_family,
                "blocker_family": blocker_family,
                "blocker_occurrences": len(rows),
                "runs": len({row.get("run_index") for row in rows}),
                "queued_resource_count": len(queued_resource_freq),
                "blocker_resource_count": len(blocker_resource_freq),
                "median_blocker_remaining_at_request_ms": median(remaining),
                "median_blocker_overlap_in_queue_ms": median(overlap),
                "top_blocker_resources": ", ".join(
                    compact_resource(name, 36) for name, _count in top_blockers[:3]
                ),
            }
        )
    output.sort(
        key=lambda row: (
            numeric(row.get("blocker_occurrences")) or 0.0,
            numeric(row.get("median_blocker_remaining_at_request_ms")) or 0.0,
            numeric(row.get("median_blocker_overlap_in_queue_ms")) or 0.0,
        ),
        reverse=True,
    )
    return output


def limit_blocker_owner_summary_rows(
    rows: list[dict[str, object]], *, limit: int
) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row.get("profile", "")), str(row.get("target", "")))].append(row)

    output = []
    for key in sorted(grouped):
        output.extend(grouped[key][:limit])
    return output


def limit_blocker_family_summary_rows(
    rows: list[dict[str, object]], *, limit: int
) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row.get("profile", "")), str(row.get("target", "")))].append(row)

    output = []
    for key in sorted(grouped):
        output.extend(grouped[key][:limit])
    return output


def same_origin_blocker_owner_delta_rows(
    payload: dict[str, object],
    *,
    target_filter: set[str] | None = None,
    baseline_profile: str | None = None,
    compare_profile: str | None = None,
    limit: int = 8,
) -> list[dict[str, object]]:
    grouped = same_origin_blocker_owner_summary_rows(
        payload,
        target_filter=target_filter,
    )
    if not grouped:
        return []
    available_profiles = sorted({str(row["profile"]) for row in grouped})
    if baseline_profile is None:
        baseline_profile = default_baseline_profile(available_profiles)
    if compare_profile is None:
        compare_profile = default_compare_profile(available_profiles, baseline_profile)
    if not baseline_profile or not compare_profile:
        return []

    baseline_map = {
        (
            str(row["target"]),
            str(row["blocker_resource"]),
            str(row["blocker_type"]),
            str(row["protocol"]),
        ): row
        for row in grouped
        if row["profile"] == baseline_profile
    }
    compare_rows = [row for row in grouped if row["profile"] == compare_profile]
    joined = []
    for row in compare_rows:
        key = (
            str(row["target"]),
            str(row["blocker_resource"]),
            str(row["blocker_type"]),
            str(row["protocol"]),
        )
        baseline = baseline_map.get(key)
        if baseline is None:
            continue
        joined.append(
            {
                "target": key[0],
                "blocker": row["blocker"],
                "blocker_resource": key[1],
                "blocker_type": key[2],
                "protocol": key[3],
                "compare_profile": compare_profile,
                "baseline_profile": baseline_profile,
                "compare_blocker_occurrences": row.get("blocker_occurrences"),
                "baseline_blocker_occurrences": baseline.get("blocker_occurrences"),
                "delta_blocker_occurrences": subtract(
                    row.get("blocker_occurrences"),
                    baseline.get("blocker_occurrences"),
                ),
                "compare_median_blocker_duration_ms": row.get(
                    "median_blocker_duration_ms"
                ),
                "baseline_median_blocker_duration_ms": baseline.get(
                    "median_blocker_duration_ms"
                ),
                "delta_median_blocker_duration_ms": subtract(
                    row.get("median_blocker_duration_ms"),
                    baseline.get("median_blocker_duration_ms"),
                ),
                "compare_median_blocker_remaining_at_request_ms": row.get(
                    "median_blocker_remaining_at_request_ms"
                ),
                "baseline_median_blocker_remaining_at_request_ms": baseline.get(
                    "median_blocker_remaining_at_request_ms"
                ),
                "delta_median_blocker_remaining_at_request_ms": subtract(
                    row.get("median_blocker_remaining_at_request_ms"),
                    baseline.get("median_blocker_remaining_at_request_ms"),
                ),
                "compare_median_blocker_overlap_in_queue_ms": row.get(
                    "median_blocker_overlap_in_queue_ms"
                ),
                "baseline_median_blocker_overlap_in_queue_ms": baseline.get(
                    "median_blocker_overlap_in_queue_ms"
                ),
                "delta_median_blocker_overlap_in_queue_ms": subtract(
                    row.get("median_blocker_overlap_in_queue_ms"),
                    baseline.get("median_blocker_overlap_in_queue_ms"),
                ),
                "compare_median_blocker_age_at_request_ms": row.get(
                    "median_blocker_age_at_request_ms"
                ),
                "baseline_median_blocker_age_at_request_ms": baseline.get(
                    "median_blocker_age_at_request_ms"
                ),
                "delta_median_blocker_age_at_request_ms": subtract(
                    row.get("median_blocker_age_at_request_ms"),
                    baseline.get("median_blocker_age_at_request_ms"),
                ),
            }
        )
    joined.sort(
        key=lambda row: (
            abs(
                numeric(row.get("delta_median_blocker_remaining_at_request_ms"))
                or 0.0
            ),
            abs(numeric(row.get("delta_blocker_occurrences")) or 0.0),
            abs(numeric(row.get("delta_median_blocker_duration_ms")) or 0.0),
        ),
        reverse=True,
    )
    return joined[:limit]


def compact_resource(value: str, max_length: int = 42) -> str:
    if len(value) <= max_length:
        return value
    parsed = urlsplit(value)
    if parsed.scheme and parsed.netloc:
        parts = [part for part in parsed.path.split("/") if part]
        query = f"?{parsed.query}" if parsed.query else ""
        candidates = []
        if parts:
            for keep in (3, 2, 1):
                tail = "/".join(parts[-keep:])
                candidates.append(tail + query)
        candidates.append(parsed.netloc + "/" + (parts[-1] if parts else "") + query)
        for candidate in candidates:
            if len(candidate) <= max_length:
                return candidate
        if candidates:
            candidate = candidates[0]
            return "…" + candidate[-(max_length - 1) :]
    return "…" + value[-(max_length - 1) :]


def resource_delta_phase_hint(row: dict[str, object]) -> str:
    deltas = {
        "start/queue": numeric(row.get("delta_fetch_to_request_ms")) or 0.0,
        "response wait": numeric(row.get("delta_wait_ms")) or 0.0,
        "response receive": numeric(row.get("delta_receive_ms")) or 0.0,
    }
    delta_duration = numeric(row.get("delta_duration_ms")) or 0.0
    positive = {name: value for name, value in deltas.items() if value > 0}
    if not positive:
        return "faster"
    ordered = sorted(positive.items(), key=lambda item: item[1], reverse=True)
    top_name, top_value = ordered[0]
    second_value = ordered[1][1] if len(ordered) > 1 else 0.0
    if top_value < 100.0:
        if delta_duration <= -100.0:
            return "faster"
        return "flat"
    if second_value >= max(100.0, top_value * 0.75):
        return "mixed"
    return top_name


def resource_family_delta_phase_hint(row: dict[str, object]) -> str:
    deltas = {
        "request discovery": numeric(row.get("delta_request_start_ms")) or 0.0,
        "start/queue": numeric(row.get("delta_fetch_to_request_ms")) or 0.0,
        "response wait": numeric(row.get("delta_wait_ms")) or 0.0,
        "response receive": numeric(row.get("delta_receive_ms")) or 0.0,
    }
    delta_duration = numeric(row.get("delta_duration_ms")) or 0.0
    positive = {name: value for name, value in deltas.items() if value > 0}
    if not positive:
        if delta_duration <= -100.0:
            return "faster"
        return "flat"
    ordered = sorted(positive.items(), key=lambda item: item[1], reverse=True)
    top_name, top_value = ordered[0]
    second_value = ordered[1][1] if len(ordered) > 1 else 0.0
    if top_value < 100.0:
        if delta_duration <= -100.0:
            return "faster"
        return "flat"
    if second_value >= max(100.0, top_value * 0.75):
        return "mixed"
    return top_name


def bytes_to_kib(value: float) -> float:
    return value / 1024.0


def resource_family(resource_name: str, resource_type: str) -> str:
    parsed = urlsplit(resource_name)
    path = parsed.path.lower()
    if "/static/fonts/fontawesome/png/" in path:
        return "fontawesome png"
    if "/static/fonts/fontawesome/webfonts/" in path:
        return "fontawesome webfont"
    if "/static/fonts/fontawesome/css/" in path:
        return "fontawesome css"
    if "/static/fonts/sourcesanspro/" in path:
        return "source sans font"
    if "/static/fonts/sourcecodepro/" in path:
        return "source code font"
    if "/static/images/download/png/" in path:
        return "download png"
    if "/static/images/download/svg/" in path:
        return "download svg"
    if "/static/images/tor-browser-mobile-window/png/" in path:
        return "product window png"
    if "/static/images/tb85/" in path:
        return "tb85 image"
    if "/static/images/favicon/" in path:
        return "favicon"
    if "/static/images/" in path:
        return "site image"
    if "/static/css/" in path:
        return "site css"
    if "/static/js/" in path:
        return "site js"
    suffix = Path(path).suffix.lower()
    if suffix == ".css":
        return "css"
    if suffix == ".js":
        return "js"
    if suffix in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}:
        return "image"
    return resource_type or "other"


def launch_ready_seconds_for_run(profile_run: dict[str, object]) -> float | None:
    general_circuit_ready = profile_run.get("general_circuit_ready")
    if isinstance(general_circuit_ready, dict):
        total_ready_seconds = numeric(general_circuit_ready.get("total_ready_seconds"))
        if total_ready_seconds is not None:
            return total_ready_seconds
    boot = profile_run.get("boot")
    if not isinstance(boot, dict):
        return None
    boot_seconds = numeric(boot.get("seconds"))
    if boot_seconds is None:
        return None
    post_boot_wait_seconds = numeric(profile_run.get("post_boot_wait_seconds")) or 0.0
    return boot_seconds + post_boot_wait_seconds


if __name__ == "__main__":
    raise SystemExit(main())
