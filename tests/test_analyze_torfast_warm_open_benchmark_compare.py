import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from analyze_torfast_warm_open_benchmark_compare import (
    blocker_chain_summary_rows,
    blocker_release_summary_rows,
    load_run_payloads,
    phase_summary_rows,
    parent_mozlog_counts,
    payload_combined_wall_seconds,
    queue_cause_summary_rows,
    queue_summary_rows,
    request_priority_group_summary_rows,
    request_order_probe_summary_rows,
    resolve_summary_path,
    saturation_summary_rows,
    stream_timeline_summary_rows,
    same_origin_request_priority_group_rows,
    same_origin_request_order_probe_metrics,
    same_origin_should_throttle_pre_request_blocker_group_rows,
    same_origin_should_throttle_connection_group_group_rows,
    same_origin_should_throttle_pre_request_phase_pair_group_rows,
    same_origin_should_throttle_pre_request_phase_group_rows,
    same_origin_should_throttle_pre_request_remaining_group_rows,
    same_origin_should_throttle_priority_group_rows,
    same_origin_should_throttle_timing_group_rows,
    same_origin_should_throttle_wave_group_rows,
    same_origin_queue_cause_metrics,
    same_origin_queue_cause_rows,
    same_origin_queue_metrics,
    should_throttle_pre_request_blocker_summary_rows,
    should_throttle_connection_group_summary_rows,
    should_throttle_pre_request_phase_pair_summary_rows,
    should_throttle_pre_request_phase_summary_rows,
    should_throttle_pre_request_remaining_summary_rows,
    should_throttle_priority_group_summary_rows,
    should_throttle_timing_summary_rows,
    should_throttle_wave_summary_rows,
    summary_profile_delta_rows,
    timeline_summary_rows,
    worst_run_rows,
)


TARGET = "https://www.torproject.org/download/"


def browser_run(*, files: list[str]) -> dict[str, object]:
    return {
        "elapsed_ms": 12345.0,
        "load_ms": 11111.0,
        "browser_net_log": {"files": files},
        "browser_activity_probe": {"enabled": False, "rows": []},
        "performance_timing": {
            "navigation": {
                "responseStart": 1500.0,
                "domContentLoadedEventEnd": 5000.0,
                "loadEventEnd": 9000.0,
            },
            "time_origin_ms": 1000.0,
            "resources": [
                {
                    "name": "https://www.torproject.org/static/images/favicon/favicon.ico",
                    "fetchStart": 100.0,
                    "requestStart": 6200.0,
                    "responseEnd": 7600.0,
                    "nextHopProtocol": "http/1.1",
                },
                {
                    "name": "https://www.torproject.org/static/fonts/fontawesome/png/white/brands/github.png",
                    "fetchStart": 120.0,
                    "requestStart": 3400.0,
                    "responseEnd": 4100.0,
                    "nextHopProtocol": "http/1.1",
                },
                {
                    "name": "https://cdn.example.com/third-party.js",
                    "fetchStart": 50.0,
                    "requestStart": 6050.0,
                    "responseEnd": 6900.0,
                    "nextHopProtocol": "http/1.1",
                },
            ]
        },
    }


def browser_run_with_resources(
    *, files: list[str], resources: list[dict[str, object]]
) -> dict[str, object]:
    run = browser_run(files=files)
    run["performance_timing"]["resources"] = resources
    return run


def enable_probe(
    run: dict[str, object], *, rows: list[dict[str, object]]
) -> dict[str, object]:
    run["browser_activity_probe"] = {"enabled": True, "rows": rows}
    return run


def probe_row(
    *,
    uri: str,
    observed_epoch_ms: float,
    priority_header: str = "",
    connection_hash: str | None = None,
) -> dict[str, object]:
    header_lines = [
        "GET / HTTP/1.1",
        "Host: www.torproject.org",
    ]
    if priority_header:
        header_lines.append(f"Priority: {priority_header}")
    row = {
        "source": "http_activity",
        "uri": uri,
        "observed_epoch_ms": observed_epoch_ms,
        "extra_string_data": "\r\n".join(header_lines) + "\r\n\r\n",
    }
    if connection_hash is not None:
        row["subject_connectionInfoHashKey"] = connection_hash
    return row


def run_payload(*, profile_name: str, cycle: int, log_path: str) -> dict[str, object]:
    return {
        "target": TARGET,
        "profile_name": profile_name,
        "cycle": cycle,
        "warm": {"wall_seconds": 0.25},
        "benchmark_wall_seconds": 15.25 + cycle,
        "open_gate_wait": {"seconds": 1.0},
        "general_circuit_wait": {"seconds": 0.5},
        "benchmark_service_state_before_browser": {
            "control_bootstrap_phase": {"progress": 100},
            "general_circuit_snapshot": {
                "matched_circuit_count": 2,
                "matched_circuit_count_by_purpose": {
                    "CONFLUX_LINKED": 1,
                    "GENERAL": 1,
                },
                "has_built_general_circuit": True,
            },
        },
        "benchmarks": {
            TARGET: {
                "runs": [browser_run(files=[log_path])],
                "summary": {
                    "ok": True,
                    "median_elapsed_ms": 12345.0,
                    "median_load_ms": 11111.0,
                },
            }
        },
        "benchmark_general_circuit_timeline": {
            "enabled": True,
            "ok": True,
            "samples": [
                {
                    "elapsed_seconds": 0.1,
                    "matched_circuit_count_by_purpose": {"GENERAL": 1},
                },
                {
                    "elapsed_seconds": 0.4,
                    "matched_circuit_count_by_purpose": {
                        "GENERAL": 1,
                        "CONFLUX_LINKED": 2,
                    },
                },
            ],
        },
    }


class AnalyzeTorfastWarmOpenBenchmarkCompareTests(unittest.TestCase):
    def test_payload_combined_wall_seconds_adds_waits(self) -> None:
        payload = run_payload(
            profile_name="auto",
            cycle=1,
            log_path="/tmp/run.mozlog.moz_log",
        )

        self.assertEqual(payload_combined_wall_seconds(payload), 18.0)

    def test_same_origin_queue_metrics_ignores_cross_origin_rows(self) -> None:
        metrics = same_origin_queue_metrics(browser_run(files=[]), TARGET)

        self.assertEqual(metrics["same_origin_resources"], 2)
        self.assertEqual(metrics["queued_gt_2000ms"], 2)
        self.assertEqual(metrics["queued_gt_5000ms"], 1)
        self.assertEqual(metrics["queued_gt_10000ms"], 0)
        self.assertEqual(metrics["max_queue_ms"], 6100.0)
        self.assertEqual(
            metrics["top_queued_resource_names"][:2],
            ["favicon.ico", "github.png"],
        )

    def test_parent_mozlog_counts_reads_parent_log_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            parent_log = Path(temp_dir) / "run.mozlog.moz_log"
            parent_log.write_text(
                "\n".join(
                    [
                        "nsHttpConnectionMgr::AtActiveConnectionLimit",
                        "adding transaction to pending queue",
                        "ProcessPendingQForEntry",
                        "ShouldThrottle",
                        "ShouldThrottle",
                    ]
                )
            )

            counts = parent_mozlog_counts(browser_run(files=[str(parent_log)]))

        self.assertEqual(counts["active_limit_events"], 1)
        self.assertEqual(counts["pending_queue_events"], 1)
        self.assertEqual(counts["process_pending_events"], 1)
        self.assertEqual(counts["should_throttle_events"], 2)

    def test_queue_summary_rows_and_worst_runs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            parent_log = Path(temp_dir) / "run.mozlog.moz_log"
            parent_log.write_text(
                "\n".join(
                    [
                        "nsHttpConnectionMgr::AtActiveConnectionLimit",
                        "adding transaction to pending queue",
                        "ShouldThrottle",
                    ]
                )
            )
            rows = queue_summary_rows(
                [
                    run_payload(
                        profile_name="auto",
                        cycle=1,
                        log_path=str(parent_log),
                    ),
                    run_payload(
                        profile_name="auto",
                        cycle=2,
                        log_path=str(parent_log),
                    ),
                ],
                target_filter=set(),
            )
            worst = worst_run_rows(
                [
                    run_payload(
                        profile_name="auto",
                        cycle=1,
                        log_path=str(parent_log),
                    ),
                    run_payload(
                        profile_name="auto",
                        cycle=2,
                        log_path=str(parent_log),
                    ),
                ],
                target_filter=set(),
                limit=1,
            )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["profile"], "auto")
        self.assertEqual(rows[0]["median_active_limit_events"], 1.0)
        self.assertEqual(rows[0]["median_pending_queue_events"], 1.0)
        self.assertEqual(rows[0]["median_should_throttle_events"], 1.0)
        self.assertEqual(len(worst), 1)
        self.assertEqual(worst[0]["profile"], "auto")
        self.assertEqual(worst[0]["combined_wall_seconds"], 19.0)
        self.assertEqual(worst[0]["top_queued_resources"], "favicon.ico, github.png")

    def test_phase_summary_rows_capture_nav_and_gate_state(self) -> None:
        rows = phase_summary_rows(
            [
                run_payload(
                    profile_name="auto",
                    cycle=1,
                    log_path="/tmp/run1.mozlog.moz_log",
                ),
                run_payload(
                    profile_name="auto",
                    cycle=2,
                    log_path="/tmp/run2.mozlog.moz_log",
                ),
            ],
            target_filter=set(),
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["profile"], "auto")
        self.assertEqual(rows[0]["median_combined_wall_seconds"], 18.5)
        self.assertEqual(rows[0]["median_nav_response_start_ms"], 1500.0)
        self.assertEqual(rows[0]["median_nav_response_to_dom_ms"], 3500.0)
        self.assertEqual(rows[0]["median_nav_dom_to_load_ms"], 4000.0)
        self.assertEqual(rows[0]["median_before_bootstrap_progress"], 100.0)
        self.assertEqual(rows[0]["median_before_gc_count"], 2.0)
        self.assertEqual(rows[0]["median_before_general_count"], 1.0)
        self.assertEqual(rows[0]["median_before_conflux_count"], 1.0)
        self.assertEqual(rows[0]["before_gc_ready_runs"], 2)

    def test_stream_timeline_summary_rows_capture_single_circuit_concentration(
        self,
    ) -> None:
        payload = run_payload(
            profile_name="auto",
            cycle=1,
            log_path="/tmp/run1.mozlog.moz_log",
        )
        payload["benchmark_stream_isolation_timeline"] = {
            "enabled": True,
            "ok": True,
            "samples": [
                {
                    "elapsed_seconds": 0.1,
                    "user_stream_count": 0,
                    "unique_circuit_count": 0,
                    "max_streams_per_circuit": 0,
                    "single_circuit_share_pct": 0.0,
                },
                {
                    "elapsed_seconds": 0.2,
                    "user_stream_count": 2,
                    "unique_circuit_count": 1,
                    "max_streams_per_circuit": 2,
                    "single_circuit_share_pct": 100.0,
                },
            ],
        }

        rows = stream_timeline_summary_rows([payload], target_filter=set())

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["profile"], "auto")
        self.assertEqual(rows[0]["median_peak_user_stream_count"], 2.0)
        self.assertEqual(rows[0]["median_peak_unique_circuit_count"], 1.0)
        self.assertEqual(rows[0]["median_peak_streams_per_circuit"], 2.0)
        self.assertEqual(rows[0]["median_peak_single_circuit_share_pct"], 100.0)
        self.assertEqual(rows[0]["median_active_sample_count"], 1.0)
        self.assertEqual(rows[0]["median_sample_count"], 2.0)

    def test_timeline_summary_rows_capture_first_conflux_and_max_counts(self) -> None:
        rows = timeline_summary_rows(
            [
                run_payload(
                    profile_name="auto",
                    cycle=1,
                    log_path="/tmp/run1.mozlog.moz_log",
                ),
                run_payload(
                    profile_name="auto",
                    cycle=2,
                    log_path="/tmp/run2.mozlog.moz_log",
                ),
            ],
            target_filter=set(),
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["profile"], "auto")
        self.assertEqual(rows[0]["median_first_conflux_seconds"], 0.4)
        self.assertEqual(rows[0]["median_max_general_count"], 1.0)
        self.assertEqual(rows[0]["median_max_conflux_count"], 2.0)
        self.assertEqual(rows[0]["median_sample_count"], 2.0)
        self.assertEqual(rows[0]["median_timeline_duration_seconds"], 0.4)

    def test_saturation_summary_rows_capture_slot_pressure_and_tail(self) -> None:
        saturated_run = {
            "elapsed_ms": 20000.0,
            "load_ms": 18000.0,
            "browser_net_log": {"files": []},
            "performance_timing": {
                "navigation": {
                    "responseStart": 1500.0,
                    "domContentLoadedEventEnd": 5000.0,
                    "loadEventEnd": 10000.0,
                },
                "resources": [
                    {
                        "name": f"https://www.torproject.org/static/a{i}.png",
                        "fetchStart": float(i * 10),
                        "requestStart": float(i * 10),
                        "responseEnd": 7000.0 + i,
                        "nextHopProtocol": "http/1.1",
                    }
                    for i in range(6)
                ]
                + [
                    {
                        "name": "https://www.torproject.org/static/queued.png",
                        "fetchStart": 100.0,
                        "requestStart": 6200.0,
                        "responseEnd": 9500.0,
                        "nextHopProtocol": "http/1.1",
                    }
                ],
            },
        }
        payload = run_payload(
            profile_name="auto",
            cycle=1,
            log_path="/tmp/run.mozlog.moz_log",
        )
        payload["benchmarks"][TARGET]["runs"] = [saturated_run]

        rows = saturation_summary_rows([payload], target_filter=set())

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["profile"], "auto")
        self.assertEqual(rows[0]["median_queued_gt_1000ms"], 1.0)
        self.assertEqual(rows[0]["median_slot_depth_6_queued_gt_1000ms"], 1.0)
        self.assertEqual(rows[0]["median_max_slot_depth_at_request"], 7.0)
        self.assertEqual(rows[0]["median_tail_after_dom_gt_1000ms"], 7.0)
        self.assertEqual(rows[0]["max_tail_after_dom_ms"], 4500.0)
        self.assertIn("queued.png", rows[0]["top_tail_resources"])

    def test_same_origin_queue_cause_rows_split_blocked_vs_unexplained(self) -> None:
        run = browser_run_with_resources(
            files=[],
            resources=[
                {
                    "name": "https://www.torproject.org/static/first.css",
                    "fetchStart": 0.0,
                    "requestStart": 0.0,
                    "responseStart": 100.0,
                    "responseEnd": 2500.0,
                    "nextHopProtocol": "http/1.1",
                },
                {
                    "name": "https://www.torproject.org/static/blocked.svg",
                    "fetchStart": 1000.0,
                    "requestStart": 2600.0,
                    "responseStart": 2700.0,
                    "responseEnd": 3200.0,
                    "nextHopProtocol": "http/1.1",
                },
                {
                    "name": "https://www.torproject.org/static/mostly-after.png",
                    "fetchStart": 1000.0,
                    "requestStart": 3000.0,
                    "responseStart": 3100.0,
                    "responseEnd": 3600.0,
                    "nextHopProtocol": "h2",
                },
                {
                    "name": "https://www.torproject.org/static/after-base.png",
                    "fetchStart": 0.0,
                    "requestStart": 0.0,
                    "responseStart": 100.0,
                    "responseEnd": 1200.0,
                    "nextHopProtocol": "h2",
                },
                {
                    "name": "https://cdn.example.com/third-party.js",
                    "fetchStart": 1000.0,
                    "requestStart": 5000.0,
                    "responseStart": 5100.0,
                    "responseEnd": 5600.0,
                    "nextHopProtocol": "http/1.1",
                },
            ],
        )

        rows = same_origin_queue_cause_rows(run, TARGET)

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["resource"], "https://www.torproject.org/static/blocked.svg")
        self.assertEqual(rows[0]["previous_resource"], "https://www.torproject.org/static/first.css")
        self.assertEqual(rows[0]["queue_blocked_by_previous_response_ms"], 1500.0)
        self.assertEqual(rows[0]["queue_unexplained_after_previous_ms"], 100.0)
        self.assertEqual(rows[0]["queue_cause_hint"], "queued behind previous response")
        self.assertEqual(rows[1]["resource"], "https://www.torproject.org/static/mostly-after.png")
        self.assertEqual(rows[1]["previous_resource"], "https://www.torproject.org/static/after-base.png")
        self.assertEqual(rows[1]["queue_blocked_by_previous_response_ms"], 200.0)
        self.assertEqual(rows[1]["queue_unexplained_after_previous_ms"], 1800.0)
        self.assertEqual(rows[1]["queue_cause_hint"], "queue mostly after previous response")

    def test_queue_cause_summary_rows_capture_blocked_and_unexplained_totals(self) -> None:
        run = browser_run_with_resources(
            files=[],
            resources=[
                {
                    "name": "https://www.torproject.org/static/first.css",
                    "fetchStart": 0.0,
                    "requestStart": 0.0,
                    "responseStart": 100.0,
                    "responseEnd": 2500.0,
                    "nextHopProtocol": "http/1.1",
                },
                {
                    "name": "https://www.torproject.org/static/blocked.svg",
                    "fetchStart": 1000.0,
                    "requestStart": 2600.0,
                    "responseStart": 2700.0,
                    "responseEnd": 3200.0,
                    "nextHopProtocol": "http/1.1",
                },
                {
                    "name": "https://www.torproject.org/static/after-base.png",
                    "fetchStart": 0.0,
                    "requestStart": 0.0,
                    "responseStart": 100.0,
                    "responseEnd": 1200.0,
                    "nextHopProtocol": "h2",
                },
                {
                    "name": "https://www.torproject.org/static/mostly-after.png",
                    "fetchStart": 1000.0,
                    "requestStart": 3000.0,
                    "responseStart": 3100.0,
                    "responseEnd": 3600.0,
                    "nextHopProtocol": "h2",
                },
            ],
        )
        payload = run_payload(
            profile_name="auto",
            cycle=1,
            log_path="/tmp/run.mozlog.moz_log",
        )
        payload["benchmarks"][TARGET]["runs"] = [run]

        metrics = same_origin_queue_cause_metrics(run, TARGET)
        rows = queue_cause_summary_rows([payload], target_filter=set())

        self.assertEqual(metrics["queued_gt_1000ms"], 2)
        self.assertEqual(metrics["total_blocked_ms"], 1700.0)
        self.assertEqual(metrics["total_unexplained_ms"], 1900.0)
        self.assertEqual(metrics["mostly_blocked_rows"], 1)
        self.assertEqual(metrics["mostly_after_previous_rows"], 1)
        self.assertEqual(metrics["max_unexplained_ms"], 1800.0)
        self.assertEqual(
            metrics["top_unexplained_resource_names"][:2],
            ["mostly-after.png", "blocked.svg"],
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["profile"], "auto")
        self.assertEqual(rows[0]["median_queued_gt_1000ms"], 2.0)
        self.assertEqual(rows[0]["median_total_blocked_ms"], 1700.0)
        self.assertEqual(rows[0]["median_total_unexplained_ms"], 1900.0)
        self.assertEqual(rows[0]["median_mostly_blocked_rows"], 1.0)
        self.assertEqual(rows[0]["median_mostly_after_previous_rows"], 1.0)
        self.assertEqual(rows[0]["top_unexplained_resources"], "mostly-after.png, blocked.svg")

    def test_blocker_chain_summary_rows_capture_top_chains_and_blockers(self) -> None:
        run = browser_run_with_resources(
            files=[],
            resources=[
                {
                    "name": "https://www.torproject.org/static/first.css",
                    "fetchStart": 0.0,
                    "requestStart": 0.0,
                    "responseStart": 100.0,
                    "responseEnd": 2500.0,
                    "nextHopProtocol": "http/1.1",
                },
                {
                    "name": "https://www.torproject.org/static/blocked.svg",
                    "fetchStart": 1000.0,
                    "requestStart": 2600.0,
                    "responseStart": 2700.0,
                    "responseEnd": 3200.0,
                    "nextHopProtocol": "http/1.1",
                },
                {
                    "name": "https://www.torproject.org/static/after-base.png",
                    "fetchStart": 0.0,
                    "requestStart": 0.0,
                    "responseStart": 100.0,
                    "responseEnd": 1200.0,
                    "nextHopProtocol": "h2",
                },
                {
                    "name": "https://www.torproject.org/static/mostly-after.png",
                    "fetchStart": 1000.0,
                    "requestStart": 3000.0,
                    "responseStart": 3100.0,
                    "responseEnd": 3600.0,
                    "nextHopProtocol": "h2",
                },
            ],
        )
        payload = run_payload(
            profile_name="auto",
            cycle=1,
            log_path="/tmp/run.mozlog.moz_log",
        )
        payload["benchmarks"][TARGET]["runs"] = [run]

        rows = blocker_chain_summary_rows([payload], target_filter=set())

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["profile"], "auto")
        self.assertEqual(rows[0]["max_blocked_ms"], 1500.0)
        self.assertEqual(
            rows[0]["top_blocked_chains"],
            "first.css -> blocked.svg, after-base.png -> mostly-after.png",
        )
        self.assertEqual(
            rows[0]["top_blocker_resources"],
            "first.css, after-base.png",
        )

    def test_blocker_release_summary_rows_capture_wait_vs_receive_dominance(self) -> None:
        run = browser_run_with_resources(
            files=[],
            resources=[
                {
                    "name": "https://www.torproject.org/static/recv-blocker.css",
                    "fetchStart": 0.0,
                    "requestStart": 0.0,
                    "responseStart": 500.0,
                    "responseEnd": 5000.0,
                    "nextHopProtocol": "http/1.1",
                },
                {
                    "name": "https://www.torproject.org/static/wait-blocker.css",
                    "fetchStart": 0.0,
                    "requestStart": 0.0,
                    "responseStart": 4000.0,
                    "responseEnd": 4500.0,
                    "nextHopProtocol": "http/1.1",
                },
                {
                    "name": "https://www.torproject.org/static/queued-recv.png",
                    "fetchStart": 1000.0,
                    "requestStart": 2500.0,
                    "responseStart": 5100.0,
                    "responseEnd": 5600.0,
                    "nextHopProtocol": "http/1.1",
                },
                {
                    "name": "https://www.torproject.org/static/wait-only.css",
                    "fetchStart": 0.0,
                    "requestStart": 0.0,
                    "responseStart": 5000.0,
                    "responseEnd": 5200.0,
                    "nextHopProtocol": "h2",
                },
                {
                    "name": "https://www.torproject.org/static/queued-wait.png",
                    "fetchStart": 0.0,
                    "requestStart": 1500.0,
                    "responseStart": 5300.0,
                    "responseEnd": 5800.0,
                    "nextHopProtocol": "h2",
                },
            ],
        )
        payload = run_payload(
            profile_name="auto",
            cycle=1,
            log_path="/tmp/run.mozlog.moz_log",
        )
        payload["benchmarks"][TARGET]["runs"] = [run]

        rows = blocker_release_summary_rows([payload], target_filter=set())

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["profile"], "auto")
        self.assertEqual(rows[0]["median_queued_gt_1000ms"], 2.0)
        self.assertEqual(rows[0]["median_rows_with_active_blockers"], 2.0)
        self.assertEqual(rows[0]["median_receive_dominant_rows"], 1.0)
        self.assertEqual(rows[0]["median_wait_dominant_rows"], 1.0)
        self.assertEqual(rows[0]["median_blockers_left_500ms"], 0.0)
        self.assertEqual(rows[0]["median_max_blocker_remaining_ms"], 3100.0)
        self.assertEqual(rows[0]["median_queue_minus_max_blocker_left_ms"], -1600.0)
        self.assertEqual(rows[0]["median_max_blocker_wait_left_ms"], 2500.0)
        self.assertEqual(rows[0]["median_max_blocker_receive_left_ms"], 1350.0)
        self.assertEqual(
            rows[0]["top_queued_resources"],
            "queued-recv.png, queued-wait.png",
        )

    def test_same_origin_request_order_probe_metrics_split_request_order_vs_discovery(self) -> None:
        run = enable_probe(
            browser_run_with_resources(
                files=[],
                resources=[
                    {
                        "name": "https://www.torproject.org/static/request-order.svg",
                        "fetchStart": 100.0,
                        "requestStart": 3100.0,
                        "responseStart": 3200.0,
                        "responseEnd": 3600.0,
                        "nextHopProtocol": "http/1.1",
                    },
                    {
                        "name": "https://www.torproject.org/static/late-discovery.png",
                        "fetchStart": 200.0,
                        "requestStart": 2200.0,
                        "responseStart": 2250.0,
                        "responseEnd": 2600.0,
                        "nextHopProtocol": "http/1.1",
                    },
                    {
                        "name": "https://www.torproject.org/static/missing-probe.css",
                        "fetchStart": 300.0,
                        "requestStart": 1800.0,
                        "responseStart": 1850.0,
                        "responseEnd": 2100.0,
                        "nextHopProtocol": "http/1.1",
                    },
                    {
                        "name": "https://www.torproject.org/static/fast.css",
                        "fetchStart": 400.0,
                        "requestStart": 700.0,
                        "responseStart": 720.0,
                        "responseEnd": 900.0,
                        "nextHopProtocol": "http/1.1",
                    },
                ],
            ),
            rows=[
                {
                    "source": "http_activity",
                    "uri": "https://www.torproject.org/static/request-order.svg",
                    "observed_epoch_ms": 1150.0,
                },
                {
                    "source": "http_activity",
                    "uri": "https://www.torproject.org/static/request-order.svg",
                    "observed_epoch_ms": 1400.0,
                },
                {
                    "source": "http_activity",
                    "uri": "https://www.torproject.org/static/late-discovery.png",
                    "observed_epoch_ms": 2800.0,
                },
            ],
        )

        metrics = same_origin_request_order_probe_metrics(run, TARGET)

        self.assertEqual(metrics["queued_gt_1000ms"], 3)
        self.assertEqual(metrics["rows_with_probe"], 2)
        self.assertEqual(metrics["request_order_dominant_rows"], 1)
        self.assertEqual(metrics["late_discovered_gt_1000ms_rows"], 1)
        self.assertEqual(metrics["median_fetch_to_probe_ms"], 825.0)
        self.assertEqual(metrics["median_probe_to_request_ms"], 1675.0)
        self.assertEqual(
            metrics["request_order_resource_scores"],
            {
                "request-order.svg": 2950.0,
                "late-discovery.png": 400.0,
            },
        )
        self.assertEqual(
            metrics["late_discovery_resource_scores"],
            {
                "request-order.svg": 50.0,
                "late-discovery.png": 1600.0,
            },
        )

    def test_request_order_probe_summary_rows_capture_request_order_resources(self) -> None:
        run = enable_probe(
            browser_run_with_resources(
                files=[],
                resources=[
                    {
                        "name": "https://www.torproject.org/static/request-order.svg",
                        "fetchStart": 100.0,
                        "requestStart": 3100.0,
                        "responseStart": 3200.0,
                        "responseEnd": 3600.0,
                        "nextHopProtocol": "http/1.1",
                    },
                    {
                        "name": "https://www.torproject.org/static/late-discovery.png",
                        "fetchStart": 200.0,
                        "requestStart": 2200.0,
                        "responseStart": 2250.0,
                        "responseEnd": 2600.0,
                        "nextHopProtocol": "http/1.1",
                    },
                ],
            ),
            rows=[
                {
                    "source": "http_activity",
                    "uri": "https://www.torproject.org/static/request-order.svg",
                    "observed_epoch_ms": 1150.0,
                },
                {
                    "source": "http_activity",
                    "uri": "https://www.torproject.org/static/late-discovery.png",
                    "observed_epoch_ms": 2800.0,
                },
            ],
        )
        payload = run_payload(
            profile_name="auto",
            cycle=1,
            log_path="/tmp/run.mozlog.moz_log",
        )
        payload["benchmarks"][TARGET]["runs"] = [run]

        rows = request_order_probe_summary_rows([payload], target_filter=set())

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["profile"], "auto")
        self.assertEqual(rows[0]["median_queued_gt_1000ms"], 2.0)
        self.assertEqual(rows[0]["median_rows_with_probe"], 2.0)
        self.assertEqual(rows[0]["median_request_order_dominant_rows"], 1.0)
        self.assertEqual(rows[0]["median_late_discovered_gt_1000ms_rows"], 1.0)
        self.assertEqual(rows[0]["median_fetch_to_probe_ms"], 825.0)
        self.assertEqual(rows[0]["median_probe_to_request_ms"], 1675.0)
        self.assertEqual(
            rows[0]["top_request_order_resources"],
            "request-order.svg, late-discovery.png",
        )
        self.assertEqual(
            rows[0]["top_late_discovery_resources"],
            "late-discovery.png, request-order.svg",
        )

    def test_same_origin_request_priority_group_rows_capture_priority_clusters(self) -> None:
        run = enable_probe(
            browser_run_with_resources(
                files=[],
                resources=[
                    {
                        "name": "https://www.torproject.org/static/request-order.svg",
                        "fetchStart": 100.0,
                        "requestStart": 3100.0,
                        "responseStart": 3200.0,
                        "responseEnd": 3600.0,
                        "nextHopProtocol": "http/1.1",
                        "initiatorType": "img",
                    },
                    {
                        "name": "https://www.torproject.org/static/late-discovery.png",
                        "fetchStart": 200.0,
                        "requestStart": 2200.0,
                        "responseStart": 2250.0,
                        "responseEnd": 2600.0,
                        "nextHopProtocol": "http/1.1",
                        "initiatorType": "css",
                    },
                    {
                        "name": "https://www.torproject.org/static/no-priority.js",
                        "fetchStart": 500.0,
                        "requestStart": 2100.0,
                        "responseStart": 2120.0,
                        "responseEnd": 2400.0,
                        "nextHopProtocol": "http/1.1",
                        "initiatorType": "script",
                    },
                ],
            ),
            rows=[
                probe_row(
                    uri="https://www.torproject.org/static/request-order.svg",
                    observed_epoch_ms=1150.0,
                    priority_header="u=5, i",
                ),
                probe_row(
                    uri="https://www.torproject.org/static/late-discovery.png",
                    observed_epoch_ms=2800.0,
                    priority_header="u=4, i",
                ),
                probe_row(
                    uri="https://www.torproject.org/static/no-priority.js",
                    observed_epoch_ms=1600.0,
                ),
            ],
        )

        rows = same_origin_request_priority_group_rows(run, TARGET)
        by_key = {
            (row["priority_header"], row["initiator_type"]): row for row in rows
        }

        self.assertEqual(len(rows), 3)
        self.assertEqual(
            by_key[("u=5, i", "img")]["median_probe_to_request_ms"],
            2950.0,
        )
        self.assertEqual(
            by_key[("u=5, i", "img")]["median_fetch_to_probe_ms"],
            50.0,
        )
        self.assertEqual(
            by_key[("u=5, i", "img")]["request_order_dominant_rows"],
            1,
        )
        self.assertEqual(
            by_key[("u=4, i", "css")]["late_discovered_gt_1000ms_rows"],
            1,
        )
        self.assertEqual(
            by_key[("(none)", "script")]["median_probe_to_request_ms"],
            1500.0,
        )
        self.assertEqual(
            by_key[("(none)", "script")]["top_resource_names"],
            ["no-priority.js"],
        )

    def test_request_priority_group_summary_rows_capture_priority_and_resources(self) -> None:
        run = enable_probe(
            browser_run_with_resources(
                files=[],
                resources=[
                    {
                        "name": "https://www.torproject.org/static/request-order.svg",
                        "fetchStart": 100.0,
                        "requestStart": 3100.0,
                        "responseStart": 3200.0,
                        "responseEnd": 3600.0,
                        "nextHopProtocol": "http/1.1",
                        "initiatorType": "img",
                    },
                    {
                        "name": "https://www.torproject.org/static/late-discovery.png",
                        "fetchStart": 200.0,
                        "requestStart": 2200.0,
                        "responseStart": 2250.0,
                        "responseEnd": 2600.0,
                        "nextHopProtocol": "http/1.1",
                        "initiatorType": "css",
                    },
                    {
                        "name": "https://www.torproject.org/static/no-priority.js",
                        "fetchStart": 500.0,
                        "requestStart": 2100.0,
                        "responseStart": 2120.0,
                        "responseEnd": 2400.0,
                        "nextHopProtocol": "http/1.1",
                        "initiatorType": "script",
                    },
                ],
            ),
            rows=[
                probe_row(
                    uri="https://www.torproject.org/static/request-order.svg",
                    observed_epoch_ms=1150.0,
                    priority_header="u=5, i",
                ),
                probe_row(
                    uri="https://www.torproject.org/static/late-discovery.png",
                    observed_epoch_ms=2800.0,
                    priority_header="u=4, i",
                ),
                probe_row(
                    uri="https://www.torproject.org/static/no-priority.js",
                    observed_epoch_ms=1600.0,
                ),
            ],
        )
        payload = run_payload(
            profile_name="auto",
            cycle=1,
            log_path="/tmp/run.mozlog.moz_log",
        )
        payload["benchmarks"][TARGET]["runs"] = [run]

        rows = request_priority_group_summary_rows([payload], target_filter=set())
        by_key = {
            (row["priority_header"], row["initiator_type"]): row for row in rows
        }

        self.assertEqual(len(rows), 3)
        self.assertEqual(by_key[("u=5, i", "img")]["median_queued_gt_1000ms"], 1.0)
        self.assertEqual(
            by_key[("u=5, i", "img")]["median_request_order_dominant_rows"],
            1.0,
        )
        self.assertEqual(
            by_key[("u=5, i", "img")]["top_resources"],
            "request-order.svg",
        )
        self.assertEqual(
            by_key[("u=4, i", "css")]["median_late_discovered_gt_1000ms_rows"],
            1.0,
        )
        self.assertEqual(
            by_key[("(none)", "script")]["median_probe_to_request_ms"],
            1500.0,
        )
        self.assertEqual(
            by_key[("(none)", "script")]["top_resources"],
            "no-priority.js",
        )

    def test_same_origin_should_throttle_priority_group_rows_join_parent_log_to_resources(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "run.mozlog.moz_log"
            request_order_uri = "https://www.torproject.org/static/request-order.svg"
            script_uri = "https://www.torproject.org/static/no-priority.js"
            log_path.write_text(
                "\n".join(
                    [
                        f"2026-07-05 00:00:00.100000 UTC - [Parent]: D/nsHttp HttpChannelParent RecvAsyncOpen [this=a1 uri={request_order_uri}, gid=42 browserid=5]",
                        "2026-07-05 00:00:00.100010 UTC - [Parent]: D/nsHttp Creating nsHttpChannel [this=abc123, nsIChannel=abc124]",
                        "2026-07-05 00:00:00.100020 UTC - [Parent]: D/nsHttp nsHttpChannel::DispatchTransaction [this=abc123, aTransWithStickyConn=0]",
                        "2026-07-05 00:00:00.100030 UTC - [Parent]: V/nsHttp Creating nsHttpTransaction @deadbeef",
                        "2026-07-05 00:00:00.100040 UTC - [Parent]: V/nsHttp nsHttpConnectionMgr::ShouldThrottle trans=deadbeef",
                        "2026-07-05 00:00:00.100050 UTC - [Parent]: V/nsHttp nsHttpConnectionMgr::ShouldThrottle trans=deadbeef",
                        f"2026-07-05 00:00:00.100060 UTC - [Parent]: D/nsHttp HttpChannelParent RecvAsyncOpen [this=b2 uri={script_uri}, gid=43 browserid=5]",
                        "2026-07-05 00:00:00.100070 UTC - [Parent]: D/nsHttp Creating nsHttpChannel [this=abc456, nsIChannel=abc457]",
                        "2026-07-05 00:00:00.100080 UTC - [Parent]: D/nsHttp nsHttpChannel::DispatchTransaction [this=abc456, aTransWithStickyConn=0]",
                        "2026-07-05 00:00:00.100090 UTC - [Parent]: V/nsHttp Creating nsHttpTransaction @feedface",
                        "2026-07-05 00:00:00.100100 UTC - [Parent]: V/nsHttp nsHttpConnectionMgr::ShouldThrottle trans=feedface",
                    ]
                ),
                encoding="utf-8",
            )
            run = enable_probe(
                browser_run_with_resources(
                    files=[str(log_path)],
                    resources=[
                        {
                            "name": request_order_uri,
                            "fetchStart": 100.0,
                            "requestStart": 3100.0,
                            "responseStart": 3200.0,
                            "responseEnd": 3600.0,
                            "nextHopProtocol": "http/1.1",
                            "initiatorType": "img",
                        },
                        {
                            "name": script_uri,
                            "fetchStart": 500.0,
                            "requestStart": 2100.0,
                            "responseStart": 2120.0,
                            "responseEnd": 2400.0,
                            "nextHopProtocol": "http/1.1",
                            "initiatorType": "script",
                        },
                    ],
                ),
                rows=[
                    probe_row(
                        uri=request_order_uri,
                        observed_epoch_ms=1150.0,
                        priority_header="u=5, i",
                    ),
                    probe_row(
                        uri=script_uri,
                        observed_epoch_ms=1600.0,
                    ),
                ],
            )

            rows = same_origin_should_throttle_priority_group_rows(run, TARGET)

        by_key = {
            (row["priority_header"], row["initiator_type"]): row for row in rows
        }
        self.assertEqual(len(rows), 2)
        self.assertEqual(by_key[("u=5, i", "img")]["resources"], 1)
        self.assertEqual(by_key[("u=5, i", "img")]["should_throttle_events"], 2.0)
        self.assertEqual(
            by_key[("u=5, i", "img")]["request_order_dominant_resources"], 1
        )
        self.assertEqual(
            by_key[("u=5, i", "img")]["top_resource_names"],
            ["request-order.svg"],
        )
        self.assertEqual(by_key[("(none)", "script")]["should_throttle_events"], 1.0)
        self.assertEqual(
            by_key[("(none)", "script")]["top_resource_names"],
            ["no-priority.js"],
        )

    def test_should_throttle_priority_group_summary_rows_capture_priority_clusters(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "run.mozlog.moz_log"
            request_order_uri = "https://www.torproject.org/static/request-order.svg"
            script_uri = "https://www.torproject.org/static/no-priority.js"
            log_path.write_text(
                "\n".join(
                    [
                        f"2026-07-05 00:00:00.100000 UTC - [Parent]: D/nsHttp HttpChannelParent RecvAsyncOpen [this=a1 uri={request_order_uri}, gid=42 browserid=5]",
                        "2026-07-05 00:00:00.100010 UTC - [Parent]: D/nsHttp Creating nsHttpChannel [this=abc123, nsIChannel=abc124]",
                        "2026-07-05 00:00:00.100020 UTC - [Parent]: D/nsHttp nsHttpChannel::DispatchTransaction [this=abc123, aTransWithStickyConn=0]",
                        "2026-07-05 00:00:00.100030 UTC - [Parent]: V/nsHttp Creating nsHttpTransaction @deadbeef",
                        "2026-07-05 00:00:00.100040 UTC - [Parent]: V/nsHttp nsHttpConnectionMgr::ShouldThrottle trans=deadbeef",
                        "2026-07-05 00:00:00.100050 UTC - [Parent]: V/nsHttp nsHttpConnectionMgr::ShouldThrottle trans=deadbeef",
                        f"2026-07-05 00:00:00.100060 UTC - [Parent]: D/nsHttp HttpChannelParent RecvAsyncOpen [this=b2 uri={script_uri}, gid=43 browserid=5]",
                        "2026-07-05 00:00:00.100070 UTC - [Parent]: D/nsHttp Creating nsHttpChannel [this=abc456, nsIChannel=abc457]",
                        "2026-07-05 00:00:00.100080 UTC - [Parent]: D/nsHttp nsHttpChannel::DispatchTransaction [this=abc456, aTransWithStickyConn=0]",
                        "2026-07-05 00:00:00.100090 UTC - [Parent]: V/nsHttp Creating nsHttpTransaction @feedface",
                        "2026-07-05 00:00:00.100100 UTC - [Parent]: V/nsHttp nsHttpConnectionMgr::ShouldThrottle trans=feedface",
                    ]
                ),
                encoding="utf-8",
            )
            run = enable_probe(
                browser_run_with_resources(
                    files=[str(log_path)],
                    resources=[
                        {
                            "name": request_order_uri,
                            "fetchStart": 100.0,
                            "requestStart": 3100.0,
                            "responseStart": 3200.0,
                            "responseEnd": 3600.0,
                            "nextHopProtocol": "http/1.1",
                            "initiatorType": "img",
                        },
                        {
                            "name": script_uri,
                            "fetchStart": 500.0,
                            "requestStart": 2100.0,
                            "responseStart": 2120.0,
                            "responseEnd": 2400.0,
                            "nextHopProtocol": "http/1.1",
                            "initiatorType": "script",
                        },
                    ],
                ),
                rows=[
                    probe_row(
                        uri=request_order_uri,
                        observed_epoch_ms=1150.0,
                        priority_header="u=5, i",
                    ),
                    probe_row(
                        uri=script_uri,
                        observed_epoch_ms=1600.0,
                    ),
                ],
            )
            payload = run_payload(
                profile_name="auto",
                cycle=1,
                log_path=str(log_path),
            )
            payload["benchmarks"][TARGET]["runs"] = [run]

            rows = should_throttle_priority_group_summary_rows(
                [payload], target_filter=set()
            )

        by_key = {
            (row["priority_header"], row["initiator_type"]): row for row in rows
        }
        self.assertEqual(len(rows), 2)
        self.assertEqual(by_key[("u=5, i", "img")]["median_resources"], 1.0)
        self.assertEqual(
            by_key[("u=5, i", "img")]["median_should_throttle_events"], 2.0
        )
        self.assertEqual(
            by_key[("u=5, i", "img")]["median_request_order_dominant_resources"],
            1.0,
        )
        self.assertEqual(
            by_key[("u=5, i", "img")]["top_resources"],
            "request-order.svg",
        )
        self.assertEqual(
            by_key[("(none)", "script")]["median_should_throttle_events"], 1.0
        )
        self.assertEqual(
            by_key[("(none)", "script")]["top_resources"],
            "no-priority.js",
        )

    def test_same_origin_should_throttle_timing_group_rows_capture_scheduler_lead_times(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "run.mozlog.moz_log"
            request_order_uri = "https://www.torproject.org/static/request-order.svg"
            script_uri = "https://www.torproject.org/static/no-priority.js"
            log_path.write_text(
                "\n".join(
                    [
                        f"1970-01-01 00:00:01.100000 UTC - [Parent]: D/nsHttp HttpChannelParent RecvAsyncOpen [this=a1 uri={request_order_uri}, gid=42 browserid=5]",
                        "1970-01-01 00:00:01.110000 UTC - [Parent]: D/nsHttp Creating nsHttpChannel [this=abc123, nsIChannel=abc124]",
                        "1970-01-01 00:00:01.120000 UTC - [Parent]: D/nsHttp nsHttpChannel::DispatchTransaction [this=abc123, aTransWithStickyConn=0]",
                        "1970-01-01 00:00:01.130000 UTC - [Parent]: V/nsHttp Creating nsHttpTransaction @deadbeef",
                        "1970-01-01 00:00:01.140000 UTC - [Parent]: V/nsHttp nsHttpConnectionMgr::ShouldThrottle trans=deadbeef",
                        "1970-01-01 00:00:01.150000 UTC - [Parent]: V/nsHttp nsHttpConnectionMgr::ShouldThrottle trans=deadbeef",
                        f"1970-01-01 00:00:01.700000 UTC - [Parent]: D/nsHttp HttpChannelParent RecvAsyncOpen [this=b2 uri={script_uri}, gid=43 browserid=5]",
                        "1970-01-01 00:00:01.710000 UTC - [Parent]: D/nsHttp Creating nsHttpChannel [this=abc456, nsIChannel=abc457]",
                        "1970-01-01 00:00:01.720000 UTC - [Parent]: D/nsHttp nsHttpChannel::DispatchTransaction [this=abc456, aTransWithStickyConn=0]",
                        "1970-01-01 00:00:01.730000 UTC - [Parent]: V/nsHttp Creating nsHttpTransaction @feedface",
                        "1970-01-01 00:00:01.900000 UTC - [Parent]: V/nsHttp nsHttpConnectionMgr::ShouldThrottle trans=feedface",
                    ]
                ),
                encoding="utf-8",
            )
            run = enable_probe(
                browser_run_with_resources(
                    files=[str(log_path)],
                    resources=[
                        {
                            "name": request_order_uri,
                            "fetchStart": 200.0,
                            "requestStart": 3100.0,
                            "responseStart": 3200.0,
                            "responseEnd": 3600.0,
                            "nextHopProtocol": "http/1.1",
                            "initiatorType": "img",
                        },
                        {
                            "name": script_uri,
                            "fetchStart": 500.0,
                            "requestStart": 2100.0,
                            "responseStart": 2120.0,
                            "responseEnd": 2400.0,
                            "nextHopProtocol": "http/1.1",
                            "initiatorType": "script",
                        },
                    ],
                ),
                rows=[
                    probe_row(
                        uri=request_order_uri,
                        observed_epoch_ms=1150.0,
                        priority_header="u=5, i",
                    ),
                    probe_row(
                        uri=script_uri,
                        observed_epoch_ms=1600.0,
                    ),
                ],
            )

            rows = same_origin_should_throttle_timing_group_rows(run, TARGET)

        by_key = {
            (row["priority_header"], row["initiator_type"]): row for row in rows
        }
        self.assertEqual(len(rows), 2)
        self.assertEqual(
            by_key[("u=5, i", "img")]["median_first_should_throttle_ms"], 140.0
        )
        self.assertEqual(
            by_key[("u=5, i", "img")][
                "median_fetch_after_first_should_throttle_ms"
            ],
            60.0,
        )
        self.assertEqual(
            by_key[("u=5, i", "img")][
                "median_request_after_first_should_throttle_ms"
            ],
            2960.0,
        )
        self.assertEqual(
            by_key[("u=5, i", "img")]["top_resource_names"],
            ["request-order.svg"],
        )
        self.assertEqual(
            by_key[("(none)", "script")][
                "median_request_after_first_should_throttle_ms"
            ],
            1200.0,
        )

    def test_should_throttle_timing_summary_rows_capture_lead_times(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "run.mozlog.moz_log"
            request_order_uri = "https://www.torproject.org/static/request-order.svg"
            script_uri = "https://www.torproject.org/static/no-priority.js"
            log_path.write_text(
                "\n".join(
                    [
                        f"1970-01-01 00:00:01.100000 UTC - [Parent]: D/nsHttp HttpChannelParent RecvAsyncOpen [this=a1 uri={request_order_uri}, gid=42 browserid=5]",
                        "1970-01-01 00:00:01.110000 UTC - [Parent]: D/nsHttp Creating nsHttpChannel [this=abc123, nsIChannel=abc124]",
                        "1970-01-01 00:00:01.120000 UTC - [Parent]: D/nsHttp nsHttpChannel::DispatchTransaction [this=abc123, aTransWithStickyConn=0]",
                        "1970-01-01 00:00:01.130000 UTC - [Parent]: V/nsHttp Creating nsHttpTransaction @deadbeef",
                        "1970-01-01 00:00:01.140000 UTC - [Parent]: V/nsHttp nsHttpConnectionMgr::ShouldThrottle trans=deadbeef",
                        "1970-01-01 00:00:01.150000 UTC - [Parent]: V/nsHttp nsHttpConnectionMgr::ShouldThrottle trans=deadbeef",
                        f"1970-01-01 00:00:01.700000 UTC - [Parent]: D/nsHttp HttpChannelParent RecvAsyncOpen [this=b2 uri={script_uri}, gid=43 browserid=5]",
                        "1970-01-01 00:00:01.710000 UTC - [Parent]: D/nsHttp Creating nsHttpChannel [this=abc456, nsIChannel=abc457]",
                        "1970-01-01 00:00:01.720000 UTC - [Parent]: D/nsHttp nsHttpChannel::DispatchTransaction [this=abc456, aTransWithStickyConn=0]",
                        "1970-01-01 00:00:01.730000 UTC - [Parent]: V/nsHttp Creating nsHttpTransaction @feedface",
                        "1970-01-01 00:00:01.900000 UTC - [Parent]: V/nsHttp nsHttpConnectionMgr::ShouldThrottle trans=feedface",
                    ]
                ),
                encoding="utf-8",
            )
            run = enable_probe(
                browser_run_with_resources(
                    files=[str(log_path)],
                    resources=[
                        {
                            "name": request_order_uri,
                            "fetchStart": 200.0,
                            "requestStart": 3100.0,
                            "responseStart": 3200.0,
                            "responseEnd": 3600.0,
                            "nextHopProtocol": "http/1.1",
                            "initiatorType": "img",
                        },
                        {
                            "name": script_uri,
                            "fetchStart": 500.0,
                            "requestStart": 2100.0,
                            "responseStart": 2120.0,
                            "responseEnd": 2400.0,
                            "nextHopProtocol": "http/1.1",
                            "initiatorType": "script",
                        },
                    ],
                ),
                rows=[
                    probe_row(
                        uri=request_order_uri,
                        observed_epoch_ms=1150.0,
                        priority_header="u=5, i",
                    ),
                    probe_row(
                        uri=script_uri,
                        observed_epoch_ms=1600.0,
                    ),
                ],
            )
            payload = run_payload(
                profile_name="auto",
                cycle=1,
                log_path=str(log_path),
            )
            payload["benchmarks"][TARGET]["runs"] = [run]

            rows = should_throttle_timing_summary_rows([payload], target_filter=set())

        by_key = {
            (row["priority_header"], row["initiator_type"]): row for row in rows
        }
        self.assertEqual(len(rows), 2)
        self.assertEqual(
            by_key[("u=5, i", "img")]["median_first_should_throttle_ms"], 140.0
        )
        self.assertEqual(
            by_key[("u=5, i", "img")][
                "median_request_after_first_should_throttle_ms"
            ],
            2960.0,
        )
        self.assertEqual(
            by_key[("u=5, i", "img")]["median_should_throttle_events"], 2.0
        )
        self.assertEqual(
            by_key[("u=5, i", "img")]["top_resources"],
            "request-order.svg",
        )
        self.assertEqual(
            by_key[("(none)", "script")][
                "median_fetch_after_first_should_throttle_ms"
            ],
            -400.0,
        )

    def test_same_origin_should_throttle_wave_group_rows_capture_wave_offsets(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "run.mozlog.moz_log"
            request_order_uri = "https://www.torproject.org/static/request-order.svg"
            script_uri = "https://www.torproject.org/static/no-priority.js"
            log_path.write_text(
                "\n".join(
                    [
                        f"1970-01-01 00:00:01.100000 UTC - [Parent]: D/nsHttp HttpChannelParent RecvAsyncOpen [this=a1 uri={request_order_uri}, gid=42 browserid=5]",
                        "1970-01-01 00:00:01.110000 UTC - [Parent]: D/nsHttp Creating nsHttpChannel [this=abc123, nsIChannel=abc124]",
                        "1970-01-01 00:00:01.120000 UTC - [Parent]: D/nsHttp nsHttpChannel::DispatchTransaction [this=abc123, aTransWithStickyConn=0]",
                        "1970-01-01 00:00:01.130000 UTC - [Parent]: V/nsHttp Creating nsHttpTransaction @deadbeef",
                        "1970-01-01 00:00:01.140000 UTC - [Parent]: V/nsHttp nsHttpConnectionMgr::ShouldThrottle trans=deadbeef",
                        f"1970-01-01 00:00:01.700000 UTC - [Parent]: D/nsHttp HttpChannelParent RecvAsyncOpen [this=b2 uri={script_uri}, gid=43 browserid=5]",
                        "1970-01-01 00:00:01.710000 UTC - [Parent]: D/nsHttp Creating nsHttpChannel [this=abc456, nsIChannel=abc457]",
                        "1970-01-01 00:00:01.720000 UTC - [Parent]: D/nsHttp nsHttpChannel::DispatchTransaction [this=abc456, aTransWithStickyConn=0]",
                        "1970-01-01 00:00:01.730000 UTC - [Parent]: V/nsHttp Creating nsHttpTransaction @feedface",
                        "1970-01-01 00:00:01.900000 UTC - [Parent]: V/nsHttp nsHttpConnectionMgr::ShouldThrottle trans=feedface",
                    ]
                ),
                encoding="utf-8",
            )
            run = enable_probe(
                browser_run_with_resources(
                    files=[str(log_path)],
                    resources=[
                        {
                            "name": request_order_uri,
                            "fetchStart": 200.0,
                            "requestStart": 3100.0,
                            "responseStart": 3200.0,
                            "responseEnd": 3600.0,
                            "nextHopProtocol": "http/1.1",
                            "initiatorType": "img",
                        },
                        {
                            "name": script_uri,
                            "fetchStart": 500.0,
                            "requestStart": 2100.0,
                            "responseStart": 2120.0,
                            "responseEnd": 2400.0,
                            "nextHopProtocol": "http/1.1",
                            "initiatorType": "script",
                        },
                    ],
                ),
                rows=[
                    probe_row(
                        uri=request_order_uri,
                        observed_epoch_ms=1150.0,
                        priority_header="u=5, i",
                    ),
                    probe_row(
                        uri=script_uri,
                        observed_epoch_ms=1600.0,
                    ),
                ],
            )

            rows = same_origin_should_throttle_wave_group_rows(run, TARGET)

        by_key = {
            (row["priority_header"], row["initiator_type"]): row for row in rows
        }
        self.assertEqual(len(rows), 2)
        self.assertEqual(by_key[("u=5, i", "img")]["earliest_wave_offset_ms"], 0.0)
        self.assertEqual(by_key[("u=5, i", "img")]["median_wave_offset_ms"], 0.0)
        self.assertEqual(
            by_key[("u=5, i", "img")]["top_resource_names"],
            ["request-order.svg"],
        )
        self.assertEqual(
            by_key[("(none)", "script")]["earliest_wave_offset_ms"],
            760.0,
        )

    def test_should_throttle_wave_summary_rows_capture_wave_offsets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "run.mozlog.moz_log"
            request_order_uri = "https://www.torproject.org/static/request-order.svg"
            script_uri = "https://www.torproject.org/static/no-priority.js"
            log_path.write_text(
                "\n".join(
                    [
                        f"1970-01-01 00:00:01.100000 UTC - [Parent]: D/nsHttp HttpChannelParent RecvAsyncOpen [this=a1 uri={request_order_uri}, gid=42 browserid=5]",
                        "1970-01-01 00:00:01.110000 UTC - [Parent]: D/nsHttp Creating nsHttpChannel [this=abc123, nsIChannel=abc124]",
                        "1970-01-01 00:00:01.120000 UTC - [Parent]: D/nsHttp nsHttpChannel::DispatchTransaction [this=abc123, aTransWithStickyConn=0]",
                        "1970-01-01 00:00:01.130000 UTC - [Parent]: V/nsHttp Creating nsHttpTransaction @deadbeef",
                        "1970-01-01 00:00:01.140000 UTC - [Parent]: V/nsHttp nsHttpConnectionMgr::ShouldThrottle trans=deadbeef",
                        f"1970-01-01 00:00:01.700000 UTC - [Parent]: D/nsHttp HttpChannelParent RecvAsyncOpen [this=b2 uri={script_uri}, gid=43 browserid=5]",
                        "1970-01-01 00:00:01.710000 UTC - [Parent]: D/nsHttp Creating nsHttpChannel [this=abc456, nsIChannel=abc457]",
                        "1970-01-01 00:00:01.720000 UTC - [Parent]: D/nsHttp nsHttpChannel::DispatchTransaction [this=abc456, aTransWithStickyConn=0]",
                        "1970-01-01 00:00:01.730000 UTC - [Parent]: V/nsHttp Creating nsHttpTransaction @feedface",
                        "1970-01-01 00:00:01.900000 UTC - [Parent]: V/nsHttp nsHttpConnectionMgr::ShouldThrottle trans=feedface",
                    ]
                ),
                encoding="utf-8",
            )
            run = enable_probe(
                browser_run_with_resources(
                    files=[str(log_path)],
                    resources=[
                        {
                            "name": request_order_uri,
                            "fetchStart": 200.0,
                            "requestStart": 3100.0,
                            "responseStart": 3200.0,
                            "responseEnd": 3600.0,
                            "nextHopProtocol": "http/1.1",
                            "initiatorType": "img",
                        },
                        {
                            "name": script_uri,
                            "fetchStart": 500.0,
                            "requestStart": 2100.0,
                            "responseStart": 2120.0,
                            "responseEnd": 2400.0,
                            "nextHopProtocol": "http/1.1",
                            "initiatorType": "script",
                        },
                    ],
                ),
                rows=[
                    probe_row(
                        uri=request_order_uri,
                        observed_epoch_ms=1150.0,
                        priority_header="u=5, i",
                    ),
                    probe_row(
                        uri=script_uri,
                        observed_epoch_ms=1600.0,
                    ),
                ],
            )
            payload = run_payload(
                profile_name="auto",
                cycle=1,
                log_path=str(log_path),
            )
            payload["benchmarks"][TARGET]["runs"] = [run]

            rows = should_throttle_wave_summary_rows([payload], target_filter=set())

        by_key = {
            (row["priority_header"], row["initiator_type"]): row for row in rows
        }
        self.assertEqual(len(rows), 2)
        self.assertEqual(
            by_key[("u=5, i", "img")]["median_earliest_wave_offset_ms"],
            0.0,
        )
        self.assertEqual(
            by_key[("u=5, i", "img")]["median_wave_offset_ms"],
            0.0,
        )
        self.assertEqual(
            by_key[("u=5, i", "img")]["top_resources"],
            "request-order.svg",
        )
        self.assertEqual(
            by_key[("(none)", "script")]["median_earliest_wave_offset_ms"],
            760.0,
        )

    def test_same_origin_should_throttle_pre_request_blocker_group_rows_capture_blocker_mix(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "run.mozlog.moz_log"
            first_uri = "https://www.torproject.org/static/request-order.svg"
            second_uri = "https://www.torproject.org/static/second-wave.svg"
            blocker_img_uri = "https://www.torproject.org/static/shared-blocker.svg"
            blocker_css_uri = "https://www.torproject.org/static/icon.png"
            log_path.write_text(
                "\n".join(
                    [
                        f"1970-01-01 00:00:01.100000 UTC - [Parent]: D/nsHttp HttpChannelParent RecvAsyncOpen [this=a1 uri={first_uri}, gid=42 browserid=5]",
                        "1970-01-01 00:00:01.110000 UTC - [Parent]: D/nsHttp Creating nsHttpChannel [this=abc123, nsIChannel=abc124]",
                        "1970-01-01 00:00:01.120000 UTC - [Parent]: D/nsHttp nsHttpChannel::DispatchTransaction [this=abc123, aTransWithStickyConn=0]",
                        "1970-01-01 00:00:01.130000 UTC - [Parent]: V/nsHttp Creating nsHttpTransaction @deadbeef",
                        "1970-01-01 00:00:01.140000 UTC - [Parent]: V/nsHttp nsHttpConnectionMgr::ShouldThrottle trans=deadbeef",
                        f"1970-01-01 00:00:01.200000 UTC - [Parent]: D/nsHttp HttpChannelParent RecvAsyncOpen [this=b2 uri={second_uri}, gid=43 browserid=5]",
                        "1970-01-01 00:00:01.210000 UTC - [Parent]: D/nsHttp Creating nsHttpChannel [this=abc456, nsIChannel=abc457]",
                        "1970-01-01 00:00:01.220000 UTC - [Parent]: D/nsHttp nsHttpChannel::DispatchTransaction [this=abc456, aTransWithStickyConn=0]",
                        "1970-01-01 00:00:01.230000 UTC - [Parent]: V/nsHttp Creating nsHttpTransaction @feedface",
                        "1970-01-01 00:00:01.240000 UTC - [Parent]: V/nsHttp nsHttpConnectionMgr::ShouldThrottle trans=feedface",
                    ]
                ),
                encoding="utf-8",
            )
            run = enable_probe(
                browser_run_with_resources(
                    files=[str(log_path)],
                    resources=[
                        {
                            "name": first_uri,
                            "fetchStart": 200.0,
                            "requestStart": 3100.0,
                            "responseStart": 3500.0,
                            "responseEnd": 3600.0,
                            "nextHopProtocol": "http/1.1",
                            "initiatorType": "img",
                        },
                        {
                            "name": second_uri,
                            "fetchStart": 220.0,
                            "requestStart": 3300.0,
                            "responseStart": 3700.0,
                            "responseEnd": 3800.0,
                            "nextHopProtocol": "http/1.1",
                            "initiatorType": "img",
                        },
                        {
                            "name": blocker_img_uri,
                            "fetchStart": 180.0,
                            "requestStart": 2800.0,
                            "responseStart": 3450.0,
                            "responseEnd": 3500.0,
                            "nextHopProtocol": "http/1.1",
                            "initiatorType": "img",
                        },
                        {
                            "name": blocker_css_uri,
                            "fetchStart": 150.0,
                            "requestStart": 2600.0,
                            "responseStart": 3380.0,
                            "responseEnd": 3400.0,
                            "nextHopProtocol": "http/1.1",
                            "initiatorType": "css",
                        },
                    ],
                ),
                rows=[
                    probe_row(
                        uri=first_uri,
                        observed_epoch_ms=1150.0,
                        priority_header="u=5, i",
                    ),
                    probe_row(
                        uri=second_uri,
                        observed_epoch_ms=1160.0,
                        priority_header="u=5, i",
                    ),
                    probe_row(
                        uri=blocker_img_uri,
                        observed_epoch_ms=1140.0,
                        priority_header="u=5, i",
                    ),
                    probe_row(
                        uri=blocker_css_uri,
                        observed_epoch_ms=1130.0,
                        priority_header="u=4, i",
                    ),
                ],
            )

            rows = same_origin_should_throttle_pre_request_blocker_group_rows(
                run, TARGET
            )

        by_key = {
            (row["priority_header"], row["initiator_type"]): row for row in rows
        }
        self.assertEqual(len(rows), 1)
        self.assertEqual(by_key[("u=5, i", "img")]["resources"], 2)
        self.assertEqual(
            by_key[("u=5, i", "img")]["median_active_blockers"],
            2.5,
        )
        self.assertEqual(
            by_key[("u=5, i", "img")]["median_same_group_blockers"],
            1.5,
        )
        self.assertEqual(
            by_key[("u=5, i", "img")]["blocker_group_scores"],
            {
                "u=5, i/img": 3.0,
                "u=4, i/css": 2.0,
            },
        )
        self.assertEqual(
            by_key[("u=5, i", "img")]["top_resource_names"],
            ["second-wave.svg", "request-order.svg"],
        )

    def test_should_throttle_pre_request_blocker_summary_rows_capture_blocker_mix(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "run.mozlog.moz_log"
            first_uri = "https://www.torproject.org/static/request-order.svg"
            second_uri = "https://www.torproject.org/static/second-wave.svg"
            blocker_img_uri = "https://www.torproject.org/static/shared-blocker.svg"
            blocker_css_uri = "https://www.torproject.org/static/icon.png"
            log_path.write_text(
                "\n".join(
                    [
                        f"1970-01-01 00:00:01.100000 UTC - [Parent]: D/nsHttp HttpChannelParent RecvAsyncOpen [this=a1 uri={first_uri}, gid=42 browserid=5]",
                        "1970-01-01 00:00:01.110000 UTC - [Parent]: D/nsHttp Creating nsHttpChannel [this=abc123, nsIChannel=abc124]",
                        "1970-01-01 00:00:01.120000 UTC - [Parent]: D/nsHttp nsHttpChannel::DispatchTransaction [this=abc123, aTransWithStickyConn=0]",
                        "1970-01-01 00:00:01.130000 UTC - [Parent]: V/nsHttp Creating nsHttpTransaction @deadbeef",
                        "1970-01-01 00:00:01.140000 UTC - [Parent]: V/nsHttp nsHttpConnectionMgr::ShouldThrottle trans=deadbeef",
                        f"1970-01-01 00:00:01.200000 UTC - [Parent]: D/nsHttp HttpChannelParent RecvAsyncOpen [this=b2 uri={second_uri}, gid=43 browserid=5]",
                        "1970-01-01 00:00:01.210000 UTC - [Parent]: D/nsHttp Creating nsHttpChannel [this=abc456, nsIChannel=abc457]",
                        "1970-01-01 00:00:01.220000 UTC - [Parent]: D/nsHttp nsHttpChannel::DispatchTransaction [this=abc456, aTransWithStickyConn=0]",
                        "1970-01-01 00:00:01.230000 UTC - [Parent]: V/nsHttp Creating nsHttpTransaction @feedface",
                        "1970-01-01 00:00:01.240000 UTC - [Parent]: V/nsHttp nsHttpConnectionMgr::ShouldThrottle trans=feedface",
                    ]
                ),
                encoding="utf-8",
            )
            run = enable_probe(
                browser_run_with_resources(
                    files=[str(log_path)],
                    resources=[
                        {
                            "name": first_uri,
                            "fetchStart": 200.0,
                            "requestStart": 3100.0,
                            "responseStart": 3500.0,
                            "responseEnd": 3600.0,
                            "nextHopProtocol": "http/1.1",
                            "initiatorType": "img",
                        },
                        {
                            "name": second_uri,
                            "fetchStart": 220.0,
                            "requestStart": 3300.0,
                            "responseStart": 3700.0,
                            "responseEnd": 3800.0,
                            "nextHopProtocol": "http/1.1",
                            "initiatorType": "img",
                        },
                        {
                            "name": blocker_img_uri,
                            "fetchStart": 180.0,
                            "requestStart": 2800.0,
                            "responseStart": 3450.0,
                            "responseEnd": 3500.0,
                            "nextHopProtocol": "http/1.1",
                            "initiatorType": "img",
                        },
                        {
                            "name": blocker_css_uri,
                            "fetchStart": 150.0,
                            "requestStart": 2600.0,
                            "responseStart": 3380.0,
                            "responseEnd": 3400.0,
                            "nextHopProtocol": "http/1.1",
                            "initiatorType": "css",
                        },
                    ],
                ),
                rows=[
                    probe_row(
                        uri=first_uri,
                        observed_epoch_ms=1150.0,
                        priority_header="u=5, i",
                    ),
                    probe_row(
                        uri=second_uri,
                        observed_epoch_ms=1160.0,
                        priority_header="u=5, i",
                    ),
                    probe_row(
                        uri=blocker_img_uri,
                        observed_epoch_ms=1140.0,
                        priority_header="u=5, i",
                    ),
                    probe_row(
                        uri=blocker_css_uri,
                        observed_epoch_ms=1130.0,
                        priority_header="u=4, i",
                    ),
                ],
            )
            payload = run_payload(
                profile_name="auto",
                cycle=1,
                log_path=str(log_path),
            )
            payload["benchmarks"][TARGET]["runs"] = [run]

            rows = should_throttle_pre_request_blocker_summary_rows(
                [payload], target_filter=set()
            )

        by_key = {
            (row["priority_header"], row["initiator_type"]): row for row in rows
        }
        self.assertEqual(len(rows), 1)
        self.assertEqual(by_key[("u=5, i", "img")]["median_resources"], 2.0)
        self.assertEqual(
            by_key[("u=5, i", "img")]["median_active_blockers"],
            2.5,
        )
        self.assertEqual(
            by_key[("u=5, i", "img")]["median_same_group_blockers"],
            1.5,
        )
        self.assertEqual(
            by_key[("u=5, i", "img")]["top_blocker_groups"],
            "u=5, i/img, u=4, i/css",
        )
        self.assertEqual(
            by_key[("u=5, i", "img")]["top_resources"],
            "second-wave.svg, request-order.svg",
        )

    def test_same_origin_should_throttle_pre_request_remaining_group_rows_capture_wait_dominance(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "run.mozlog.moz_log"
            first_uri = "https://www.torproject.org/static/request-order.svg"
            second_uri = "https://www.torproject.org/static/second-wave.svg"
            blocker_img_uri = "https://www.torproject.org/static/shared-blocker.svg"
            blocker_css_uri = "https://www.torproject.org/static/icon.png"
            log_path.write_text(
                "\n".join(
                    [
                        f"1970-01-01 00:00:01.100000 UTC - [Parent]: D/nsHttp HttpChannelParent RecvAsyncOpen [this=a1 uri={first_uri}, gid=42 browserid=5]",
                        "1970-01-01 00:00:01.110000 UTC - [Parent]: D/nsHttp Creating nsHttpChannel [this=abc123, nsIChannel=abc124]",
                        "1970-01-01 00:00:01.120000 UTC - [Parent]: D/nsHttp nsHttpChannel::DispatchTransaction [this=abc123, aTransWithStickyConn=0]",
                        "1970-01-01 00:00:01.130000 UTC - [Parent]: V/nsHttp Creating nsHttpTransaction @deadbeef",
                        "1970-01-01 00:00:01.140000 UTC - [Parent]: V/nsHttp nsHttpConnectionMgr::ShouldThrottle trans=deadbeef",
                        f"1970-01-01 00:00:01.200000 UTC - [Parent]: D/nsHttp HttpChannelParent RecvAsyncOpen [this=b2 uri={second_uri}, gid=43 browserid=5]",
                        "1970-01-01 00:00:01.210000 UTC - [Parent]: D/nsHttp Creating nsHttpChannel [this=abc456, nsIChannel=abc457]",
                        "1970-01-01 00:00:01.220000 UTC - [Parent]: D/nsHttp nsHttpChannel::DispatchTransaction [this=abc456, aTransWithStickyConn=0]",
                        "1970-01-01 00:00:01.230000 UTC - [Parent]: V/nsHttp Creating nsHttpTransaction @feedface",
                        "1970-01-01 00:00:01.240000 UTC - [Parent]: V/nsHttp nsHttpConnectionMgr::ShouldThrottle trans=feedface",
                    ]
                ),
                encoding="utf-8",
            )
            run = enable_probe(
                browser_run_with_resources(
                    files=[str(log_path)],
                    resources=[
                        {
                            "name": first_uri,
                            "fetchStart": 200.0,
                            "requestStart": 3100.0,
                            "responseStart": 3500.0,
                            "responseEnd": 3600.0,
                            "nextHopProtocol": "http/1.1",
                            "initiatorType": "img",
                        },
                        {
                            "name": second_uri,
                            "fetchStart": 220.0,
                            "requestStart": 3300.0,
                            "responseStart": 3700.0,
                            "responseEnd": 3800.0,
                            "nextHopProtocol": "http/1.1",
                            "initiatorType": "img",
                        },
                        {
                            "name": blocker_img_uri,
                            "fetchStart": 180.0,
                            "requestStart": 2800.0,
                            "responseStart": 3450.0,
                            "responseEnd": 3500.0,
                            "nextHopProtocol": "http/1.1",
                            "initiatorType": "img",
                        },
                        {
                            "name": blocker_css_uri,
                            "fetchStart": 150.0,
                            "requestStart": 2600.0,
                            "responseStart": 3380.0,
                            "responseEnd": 3400.0,
                            "nextHopProtocol": "http/1.1",
                            "initiatorType": "css",
                        },
                    ],
                ),
                rows=[
                    probe_row(
                        uri=first_uri,
                        observed_epoch_ms=1150.0,
                        priority_header="u=5, i",
                    ),
                    probe_row(
                        uri=second_uri,
                        observed_epoch_ms=1160.0,
                        priority_header="u=5, i",
                    ),
                    probe_row(
                        uri=blocker_img_uri,
                        observed_epoch_ms=1140.0,
                        priority_header="u=5, i",
                    ),
                    probe_row(
                        uri=blocker_css_uri,
                        observed_epoch_ms=1130.0,
                        priority_header="u=4, i",
                    ),
                ],
            )

            rows = same_origin_should_throttle_pre_request_remaining_group_rows(
                run, TARGET
            )

        by_key = {
            (row["priority_header"], row["initiator_type"]): row for row in rows
        }
        self.assertEqual(len(rows), 1)
        self.assertEqual(
            by_key[("u=5, i", "img")]["wait_dominant_resources"],
            2,
        )
        self.assertEqual(
            by_key[("u=5, i", "img")]["median_max_wait_remaining_ms"],
            275.0,
        )
        self.assertEqual(
            by_key[("u=5, i", "img")]["median_max_receive_remaining_ms"],
            75.0,
        )
        self.assertEqual(
            by_key[("u=5, i", "img")]["median_sum_wait_remaining_ms"],
            530.0,
        )
        self.assertEqual(
            by_key[("u=5, i", "img")]["median_sum_receive_remaining_ms"],
            120.0,
        )

    def test_should_throttle_pre_request_remaining_summary_rows_capture_wait_dominance(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "run.mozlog.moz_log"
            first_uri = "https://www.torproject.org/static/request-order.svg"
            second_uri = "https://www.torproject.org/static/second-wave.svg"
            blocker_img_uri = "https://www.torproject.org/static/shared-blocker.svg"
            blocker_css_uri = "https://www.torproject.org/static/icon.png"
            log_path.write_text(
                "\n".join(
                    [
                        f"1970-01-01 00:00:01.100000 UTC - [Parent]: D/nsHttp HttpChannelParent RecvAsyncOpen [this=a1 uri={first_uri}, gid=42 browserid=5]",
                        "1970-01-01 00:00:01.110000 UTC - [Parent]: D/nsHttp Creating nsHttpChannel [this=abc123, nsIChannel=abc124]",
                        "1970-01-01 00:00:01.120000 UTC - [Parent]: D/nsHttp nsHttpChannel::DispatchTransaction [this=abc123, aTransWithStickyConn=0]",
                        "1970-01-01 00:00:01.130000 UTC - [Parent]: V/nsHttp Creating nsHttpTransaction @deadbeef",
                        "1970-01-01 00:00:01.140000 UTC - [Parent]: V/nsHttp nsHttpConnectionMgr::ShouldThrottle trans=deadbeef",
                        f"1970-01-01 00:00:01.200000 UTC - [Parent]: D/nsHttp HttpChannelParent RecvAsyncOpen [this=b2 uri={second_uri}, gid=43 browserid=5]",
                        "1970-01-01 00:00:01.210000 UTC - [Parent]: D/nsHttp Creating nsHttpChannel [this=abc456, nsIChannel=abc457]",
                        "1970-01-01 00:00:01.220000 UTC - [Parent]: D/nsHttp nsHttpChannel::DispatchTransaction [this=abc456, aTransWithStickyConn=0]",
                        "1970-01-01 00:00:01.230000 UTC - [Parent]: V/nsHttp Creating nsHttpTransaction @feedface",
                        "1970-01-01 00:00:01.240000 UTC - [Parent]: V/nsHttp nsHttpConnectionMgr::ShouldThrottle trans=feedface",
                    ]
                ),
                encoding="utf-8",
            )
            run = enable_probe(
                browser_run_with_resources(
                    files=[str(log_path)],
                    resources=[
                        {
                            "name": first_uri,
                            "fetchStart": 200.0,
                            "requestStart": 3100.0,
                            "responseStart": 3500.0,
                            "responseEnd": 3600.0,
                            "nextHopProtocol": "http/1.1",
                            "initiatorType": "img",
                        },
                        {
                            "name": second_uri,
                            "fetchStart": 220.0,
                            "requestStart": 3300.0,
                            "responseStart": 3700.0,
                            "responseEnd": 3800.0,
                            "nextHopProtocol": "http/1.1",
                            "initiatorType": "img",
                        },
                        {
                            "name": blocker_img_uri,
                            "fetchStart": 180.0,
                            "requestStart": 2800.0,
                            "responseStart": 3450.0,
                            "responseEnd": 3500.0,
                            "nextHopProtocol": "http/1.1",
                            "initiatorType": "img",
                        },
                        {
                            "name": blocker_css_uri,
                            "fetchStart": 150.0,
                            "requestStart": 2600.0,
                            "responseStart": 3380.0,
                            "responseEnd": 3400.0,
                            "nextHopProtocol": "http/1.1",
                            "initiatorType": "css",
                        },
                    ],
                ),
                rows=[
                    probe_row(
                        uri=first_uri,
                        observed_epoch_ms=1150.0,
                        priority_header="u=5, i",
                    ),
                    probe_row(
                        uri=second_uri,
                        observed_epoch_ms=1160.0,
                        priority_header="u=5, i",
                    ),
                    probe_row(
                        uri=blocker_img_uri,
                        observed_epoch_ms=1140.0,
                        priority_header="u=5, i",
                    ),
                    probe_row(
                        uri=blocker_css_uri,
                        observed_epoch_ms=1130.0,
                        priority_header="u=4, i",
                    ),
                ],
            )
            payload = run_payload(
                profile_name="auto",
                cycle=1,
                log_path=str(log_path),
            )
            payload["benchmarks"][TARGET]["runs"] = [run]

            rows = should_throttle_pre_request_remaining_summary_rows(
                [payload], target_filter=set()
            )

        by_key = {
            (row["priority_header"], row["initiator_type"]): row for row in rows
        }
        self.assertEqual(len(rows), 1)
        self.assertEqual(
            by_key[("u=5, i", "img")]["median_wait_dominant_resources"],
            2.0,
        )
        self.assertEqual(
            by_key[("u=5, i", "img")]["median_max_wait_remaining_ms"],
            275.0,
        )
        self.assertEqual(
            by_key[("u=5, i", "img")]["median_sum_wait_remaining_ms"],
            530.0,
        )
        self.assertEqual(
            by_key[("u=5, i", "img")]["top_resources"],
            "second-wave.svg, request-order.svg",
        )

    def test_same_origin_should_throttle_pre_request_phase_group_rows_capture_ttfb_mix(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "run.mozlog.moz_log"
            first_uri = "https://www.torproject.org/static/request-order.svg"
            second_uri = "https://www.torproject.org/static/second-wave.svg"
            blocker_img_uri = "https://www.torproject.org/static/shared-blocker.svg"
            blocker_css_uri = "https://www.torproject.org/static/icon.png"
            log_path.write_text(
                "\n".join(
                    [
                        f"1970-01-01 00:00:01.100000 UTC - [Parent]: D/nsHttp HttpChannelParent RecvAsyncOpen [this=a1 uri={first_uri}, gid=42 browserid=5]",
                        "1970-01-01 00:00:01.110000 UTC - [Parent]: D/nsHttp Creating nsHttpChannel [this=abc123, nsIChannel=abc124]",
                        "1970-01-01 00:00:01.120000 UTC - [Parent]: D/nsHttp nsHttpChannel::DispatchTransaction [this=abc123, aTransWithStickyConn=0]",
                        "1970-01-01 00:00:01.130000 UTC - [Parent]: V/nsHttp Creating nsHttpTransaction @deadbeef",
                        "1970-01-01 00:00:01.140000 UTC - [Parent]: V/nsHttp nsHttpConnectionMgr::ShouldThrottle trans=deadbeef",
                        f"1970-01-01 00:00:01.200000 UTC - [Parent]: D/nsHttp HttpChannelParent RecvAsyncOpen [this=b2 uri={second_uri}, gid=43 browserid=5]",
                        "1970-01-01 00:00:01.210000 UTC - [Parent]: D/nsHttp Creating nsHttpChannel [this=abc456, nsIChannel=abc457]",
                        "1970-01-01 00:00:01.220000 UTC - [Parent]: D/nsHttp nsHttpChannel::DispatchTransaction [this=abc456, aTransWithStickyConn=0]",
                        "1970-01-01 00:00:01.230000 UTC - [Parent]: V/nsHttp Creating nsHttpTransaction @feedface",
                        "1970-01-01 00:00:01.240000 UTC - [Parent]: V/nsHttp nsHttpConnectionMgr::ShouldThrottle trans=feedface",
                    ]
                ),
                encoding="utf-8",
            )
            run = enable_probe(
                browser_run_with_resources(
                    files=[str(log_path)],
                    resources=[
                        {
                            "name": first_uri,
                            "fetchStart": 200.0,
                            "requestStart": 3100.0,
                            "responseStart": 3500.0,
                            "responseEnd": 3600.0,
                            "nextHopProtocol": "http/1.1",
                            "initiatorType": "img",
                        },
                        {
                            "name": second_uri,
                            "fetchStart": 220.0,
                            "requestStart": 3300.0,
                            "responseStart": 3700.0,
                            "responseEnd": 3800.0,
                            "nextHopProtocol": "http/1.1",
                            "initiatorType": "img",
                        },
                        {
                            "name": blocker_img_uri,
                            "fetchStart": 180.0,
                            "requestStart": 2800.0,
                            "responseStart": 3450.0,
                            "responseEnd": 3500.0,
                            "nextHopProtocol": "http/1.1",
                            "initiatorType": "img",
                        },
                        {
                            "name": blocker_css_uri,
                            "fetchStart": 150.0,
                            "requestStart": 2600.0,
                            "responseStart": 3380.0,
                            "responseEnd": 3400.0,
                            "nextHopProtocol": "http/1.1",
                            "initiatorType": "css",
                        },
                    ],
                ),
                rows=[
                    probe_row(
                        uri=first_uri,
                        observed_epoch_ms=1150.0,
                        priority_header="u=5, i",
                    ),
                    probe_row(
                        uri=second_uri,
                        observed_epoch_ms=1160.0,
                        priority_header="u=5, i",
                    ),
                    probe_row(
                        uri=blocker_img_uri,
                        observed_epoch_ms=1140.0,
                        priority_header="u=5, i",
                    ),
                    probe_row(
                        uri=blocker_css_uri,
                        observed_epoch_ms=1130.0,
                        priority_header="u=4, i",
                    ),
                ],
            )

            rows = same_origin_should_throttle_pre_request_phase_group_rows(
                run, TARGET
            )

        by_key = {
            (row["priority_header"], row["initiator_type"]): row for row in rows
        }
        self.assertEqual(len(rows), 1)
        self.assertEqual(
            by_key[("u=5, i", "img")]["response_start_dominant_resources"],
            2,
        )
        self.assertEqual(
            by_key[("u=5, i", "img")]["median_request_to_response_start_ms"],
            400.0,
        )
        self.assertEqual(
            by_key[("u=5, i", "img")]["median_response_start_to_response_end_ms"],
            100.0,
        )
        self.assertEqual(
            by_key[("u=5, i", "img")]["median_throttle_to_response_start_ms"],
            3410.0,
        )
        self.assertEqual(
            by_key[("u=5, i", "img")]["median_throttle_to_response_end_ms"],
            3510.0,
        )

    def test_should_throttle_pre_request_phase_summary_rows_capture_ttfb_mix(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "run.mozlog.moz_log"
            first_uri = "https://www.torproject.org/static/request-order.svg"
            second_uri = "https://www.torproject.org/static/second-wave.svg"
            blocker_img_uri = "https://www.torproject.org/static/shared-blocker.svg"
            blocker_css_uri = "https://www.torproject.org/static/icon.png"
            log_path.write_text(
                "\n".join(
                    [
                        f"1970-01-01 00:00:01.100000 UTC - [Parent]: D/nsHttp HttpChannelParent RecvAsyncOpen [this=a1 uri={first_uri}, gid=42 browserid=5]",
                        "1970-01-01 00:00:01.110000 UTC - [Parent]: D/nsHttp Creating nsHttpChannel [this=abc123, nsIChannel=abc124]",
                        "1970-01-01 00:00:01.120000 UTC - [Parent]: D/nsHttp nsHttpChannel::DispatchTransaction [this=abc123, aTransWithStickyConn=0]",
                        "1970-01-01 00:00:01.130000 UTC - [Parent]: V/nsHttp Creating nsHttpTransaction @deadbeef",
                        "1970-01-01 00:00:01.140000 UTC - [Parent]: V/nsHttp nsHttpConnectionMgr::ShouldThrottle trans=deadbeef",
                        f"1970-01-01 00:00:01.200000 UTC - [Parent]: D/nsHttp HttpChannelParent RecvAsyncOpen [this=b2 uri={second_uri}, gid=43 browserid=5]",
                        "1970-01-01 00:00:01.210000 UTC - [Parent]: D/nsHttp Creating nsHttpChannel [this=abc456, nsIChannel=abc457]",
                        "1970-01-01 00:00:01.220000 UTC - [Parent]: D/nsHttp nsHttpChannel::DispatchTransaction [this=abc456, aTransWithStickyConn=0]",
                        "1970-01-01 00:00:01.230000 UTC - [Parent]: V/nsHttp Creating nsHttpTransaction @feedface",
                        "1970-01-01 00:00:01.240000 UTC - [Parent]: V/nsHttp nsHttpConnectionMgr::ShouldThrottle trans=feedface",
                    ]
                ),
                encoding="utf-8",
            )
            run = enable_probe(
                browser_run_with_resources(
                    files=[str(log_path)],
                    resources=[
                        {
                            "name": first_uri,
                            "fetchStart": 200.0,
                            "requestStart": 3100.0,
                            "responseStart": 3500.0,
                            "responseEnd": 3600.0,
                            "nextHopProtocol": "http/1.1",
                            "initiatorType": "img",
                        },
                        {
                            "name": second_uri,
                            "fetchStart": 220.0,
                            "requestStart": 3300.0,
                            "responseStart": 3700.0,
                            "responseEnd": 3800.0,
                            "nextHopProtocol": "http/1.1",
                            "initiatorType": "img",
                        },
                        {
                            "name": blocker_img_uri,
                            "fetchStart": 180.0,
                            "requestStart": 2800.0,
                            "responseStart": 3450.0,
                            "responseEnd": 3500.0,
                            "nextHopProtocol": "http/1.1",
                            "initiatorType": "img",
                        },
                        {
                            "name": blocker_css_uri,
                            "fetchStart": 150.0,
                            "requestStart": 2600.0,
                            "responseStart": 3380.0,
                            "responseEnd": 3400.0,
                            "nextHopProtocol": "http/1.1",
                            "initiatorType": "css",
                        },
                    ],
                ),
                rows=[
                    probe_row(
                        uri=first_uri,
                        observed_epoch_ms=1150.0,
                        priority_header="u=5, i",
                    ),
                    probe_row(
                        uri=second_uri,
                        observed_epoch_ms=1160.0,
                        priority_header="u=5, i",
                    ),
                    probe_row(
                        uri=blocker_img_uri,
                        observed_epoch_ms=1140.0,
                        priority_header="u=5, i",
                    ),
                    probe_row(
                        uri=blocker_css_uri,
                        observed_epoch_ms=1130.0,
                        priority_header="u=4, i",
                    ),
                ],
            )
            payload = run_payload(
                profile_name="auto",
                cycle=1,
                log_path=str(log_path),
            )
            payload["benchmarks"][TARGET]["runs"] = [run]

            rows = should_throttle_pre_request_phase_summary_rows(
                [payload], target_filter=set()
            )

        by_key = {
            (row["priority_header"], row["initiator_type"]): row for row in rows
        }
        self.assertEqual(len(rows), 1)
        self.assertEqual(
            by_key[("u=5, i", "img")][
                "median_request_after_first_should_throttle_ms"
            ],
            3010.0,
        )
        self.assertEqual(
            by_key[("u=5, i", "img")][
                "median_response_start_dominant_resources"
            ],
            2.0,
        )
        self.assertEqual(
            by_key[("u=5, i", "img")]["median_request_to_response_start_ms"],
            400.0,
        )
        self.assertEqual(
            by_key[("u=5, i", "img")][
                "median_response_start_to_response_end_ms"
            ],
            100.0,
        )
        self.assertEqual(
            by_key[("u=5, i", "img")]["median_throttle_to_response_start_ms"],
            3410.0,
        )
        self.assertEqual(
            by_key[("u=5, i", "img")]["top_resources"],
            "request-order.svg, second-wave.svg",
        )

    def test_same_origin_should_throttle_pre_request_phase_pair_group_rows_capture_top_pairs(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "run.mozlog.moz_log"
            first_uri = "https://www.torproject.org/static/request-order.svg"
            second_uri = "https://www.torproject.org/static/second-wave.svg"
            blocker_img_uri = "https://www.torproject.org/static/shared-blocker.svg"
            blocker_css_uri = "https://www.torproject.org/static/icon.png"
            log_path.write_text(
                "\n".join(
                    [
                        f"1970-01-01 00:00:01.100000 UTC - [Parent]: D/nsHttp HttpChannelParent RecvAsyncOpen [this=a1 uri={first_uri}, gid=42 browserid=5]",
                        "1970-01-01 00:00:01.110000 UTC - [Parent]: D/nsHttp Creating nsHttpChannel [this=abc123, nsIChannel=abc124]",
                        "1970-01-01 00:00:01.120000 UTC - [Parent]: D/nsHttp nsHttpChannel::DispatchTransaction [this=abc123, aTransWithStickyConn=0]",
                        "1970-01-01 00:00:01.130000 UTC - [Parent]: V/nsHttp Creating nsHttpTransaction @deadbeef",
                        "1970-01-01 00:00:01.140000 UTC - [Parent]: V/nsHttp nsHttpConnectionMgr::ShouldThrottle trans=deadbeef",
                        f"1970-01-01 00:00:01.200000 UTC - [Parent]: D/nsHttp HttpChannelParent RecvAsyncOpen [this=b2 uri={second_uri}, gid=43 browserid=5]",
                        "1970-01-01 00:00:01.210000 UTC - [Parent]: D/nsHttp Creating nsHttpChannel [this=abc456, nsIChannel=abc457]",
                        "1970-01-01 00:00:01.220000 UTC - [Parent]: D/nsHttp nsHttpChannel::DispatchTransaction [this=abc456, aTransWithStickyConn=0]",
                        "1970-01-01 00:00:01.230000 UTC - [Parent]: V/nsHttp Creating nsHttpTransaction @feedface",
                        "1970-01-01 00:00:01.240000 UTC - [Parent]: V/nsHttp nsHttpConnectionMgr::ShouldThrottle trans=feedface",
                    ]
                ),
                encoding="utf-8",
            )
            run = enable_probe(
                browser_run_with_resources(
                    files=[str(log_path)],
                    resources=[
                        {
                            "name": first_uri,
                            "fetchStart": 200.0,
                            "requestStart": 3100.0,
                            "responseStart": 3500.0,
                            "responseEnd": 3600.0,
                            "nextHopProtocol": "http/1.1",
                            "initiatorType": "img",
                        },
                        {
                            "name": second_uri,
                            "fetchStart": 220.0,
                            "requestStart": 3300.0,
                            "responseStart": 3700.0,
                            "responseEnd": 3800.0,
                            "nextHopProtocol": "http/1.1",
                            "initiatorType": "img",
                        },
                        {
                            "name": blocker_img_uri,
                            "fetchStart": 180.0,
                            "requestStart": 2800.0,
                            "responseStart": 3450.0,
                            "responseEnd": 3500.0,
                            "nextHopProtocol": "http/1.1",
                            "initiatorType": "img",
                        },
                        {
                            "name": blocker_css_uri,
                            "fetchStart": 150.0,
                            "requestStart": 2600.0,
                            "responseStart": 3380.0,
                            "responseEnd": 3400.0,
                            "nextHopProtocol": "http/1.1",
                            "initiatorType": "css",
                        },
                    ],
                ),
                rows=[
                    probe_row(
                        uri=first_uri,
                        observed_epoch_ms=1150.0,
                        priority_header="u=5, i",
                    ),
                    probe_row(
                        uri=second_uri,
                        observed_epoch_ms=1160.0,
                        priority_header="u=5, i",
                    ),
                    probe_row(
                        uri=blocker_img_uri,
                        observed_epoch_ms=1140.0,
                        priority_header="u=5, i",
                    ),
                    probe_row(
                        uri=blocker_css_uri,
                        observed_epoch_ms=1130.0,
                        priority_header="u=4, i",
                    ),
                ],
            )

            rows = same_origin_should_throttle_pre_request_phase_pair_group_rows(
                run, TARGET
            )

        by_key = {
            (row["priority_header"], row["initiator_type"]): row for row in rows
        }
        self.assertEqual(len(rows), 1)
        self.assertEqual(
            by_key[("u=5, i", "img")]["response_start_dominant_resources"],
            2,
        )
        self.assertEqual(
            by_key[("u=5, i", "img")]["median_request_to_response_start_ms"],
            400.0,
        )
        self.assertEqual(
            by_key[("u=5, i", "img")]["median_max_pair_covered_ms"],
            350.0,
        )
        self.assertEqual(
            by_key[("u=5, i", "img")]["blocker_pair_scores"],
            {
                "shared-blocker.svg -> request-order.svg": 400.0,
                "icon.png -> request-order.svg": 300.0,
                "request-order.svg -> second-wave.svg": 300.0,
                "shared-blocker.svg -> second-wave.svg": 200.0,
                "icon.png -> second-wave.svg": 100.0,
            },
        )
        self.assertEqual(
            by_key[("u=5, i", "img")]["blocker_resource_scores"],
            {
                "shared-blocker.svg": 600.0,
                "icon.png": 400.0,
                "request-order.svg": 300.0,
            },
        )

    def test_should_throttle_pre_request_phase_pair_summary_rows_capture_top_pairs(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "run.mozlog.moz_log"
            first_uri = "https://www.torproject.org/static/request-order.svg"
            second_uri = "https://www.torproject.org/static/second-wave.svg"
            blocker_img_uri = "https://www.torproject.org/static/shared-blocker.svg"
            blocker_css_uri = "https://www.torproject.org/static/icon.png"
            log_path.write_text(
                "\n".join(
                    [
                        f"1970-01-01 00:00:01.100000 UTC - [Parent]: D/nsHttp HttpChannelParent RecvAsyncOpen [this=a1 uri={first_uri}, gid=42 browserid=5]",
                        "1970-01-01 00:00:01.110000 UTC - [Parent]: D/nsHttp Creating nsHttpChannel [this=abc123, nsIChannel=abc124]",
                        "1970-01-01 00:00:01.120000 UTC - [Parent]: D/nsHttp nsHttpChannel::DispatchTransaction [this=abc123, aTransWithStickyConn=0]",
                        "1970-01-01 00:00:01.130000 UTC - [Parent]: V/nsHttp Creating nsHttpTransaction @deadbeef",
                        "1970-01-01 00:00:01.140000 UTC - [Parent]: V/nsHttp nsHttpConnectionMgr::ShouldThrottle trans=deadbeef",
                        f"1970-01-01 00:00:01.200000 UTC - [Parent]: D/nsHttp HttpChannelParent RecvAsyncOpen [this=b2 uri={second_uri}, gid=43 browserid=5]",
                        "1970-01-01 00:00:01.210000 UTC - [Parent]: D/nsHttp Creating nsHttpChannel [this=abc456, nsIChannel=abc457]",
                        "1970-01-01 00:00:01.220000 UTC - [Parent]: D/nsHttp nsHttpChannel::DispatchTransaction [this=abc456, aTransWithStickyConn=0]",
                        "1970-01-01 00:00:01.230000 UTC - [Parent]: V/nsHttp Creating nsHttpTransaction @feedface",
                        "1970-01-01 00:00:01.240000 UTC - [Parent]: V/nsHttp nsHttpConnectionMgr::ShouldThrottle trans=feedface",
                    ]
                ),
                encoding="utf-8",
            )
            run = enable_probe(
                browser_run_with_resources(
                    files=[str(log_path)],
                    resources=[
                        {
                            "name": first_uri,
                            "fetchStart": 200.0,
                            "requestStart": 3100.0,
                            "responseStart": 3500.0,
                            "responseEnd": 3600.0,
                            "nextHopProtocol": "http/1.1",
                            "initiatorType": "img",
                        },
                        {
                            "name": second_uri,
                            "fetchStart": 220.0,
                            "requestStart": 3300.0,
                            "responseStart": 3700.0,
                            "responseEnd": 3800.0,
                            "nextHopProtocol": "http/1.1",
                            "initiatorType": "img",
                        },
                        {
                            "name": blocker_img_uri,
                            "fetchStart": 180.0,
                            "requestStart": 2800.0,
                            "responseStart": 3450.0,
                            "responseEnd": 3500.0,
                            "nextHopProtocol": "http/1.1",
                            "initiatorType": "img",
                        },
                        {
                            "name": blocker_css_uri,
                            "fetchStart": 150.0,
                            "requestStart": 2600.0,
                            "responseStart": 3380.0,
                            "responseEnd": 3400.0,
                            "nextHopProtocol": "http/1.1",
                            "initiatorType": "css",
                        },
                    ],
                ),
                rows=[
                    probe_row(
                        uri=first_uri,
                        observed_epoch_ms=1150.0,
                        priority_header="u=5, i",
                    ),
                    probe_row(
                        uri=second_uri,
                        observed_epoch_ms=1160.0,
                        priority_header="u=5, i",
                    ),
                    probe_row(
                        uri=blocker_img_uri,
                        observed_epoch_ms=1140.0,
                        priority_header="u=5, i",
                    ),
                    probe_row(
                        uri=blocker_css_uri,
                        observed_epoch_ms=1130.0,
                        priority_header="u=4, i",
                    ),
                ],
            )
            payload = run_payload(
                profile_name="auto",
                cycle=1,
                log_path=str(log_path),
            )
            payload["benchmarks"][TARGET]["runs"] = [run]

            rows = should_throttle_pre_request_phase_pair_summary_rows(
                [payload], target_filter=set()
            )

        by_key = {
            (row["priority_header"], row["initiator_type"]): row for row in rows
        }
        self.assertEqual(len(rows), 1)
        self.assertEqual(
            by_key[("u=5, i", "img")]["median_response_start_dominant_resources"],
            2.0,
        )
        self.assertEqual(
            by_key[("u=5, i", "img")]["median_request_to_response_start_ms"],
            400.0,
        )
        self.assertEqual(
            by_key[("u=5, i", "img")]["median_max_pair_covered_ms"],
            350.0,
        )
        self.assertEqual(
            by_key[("u=5, i", "img")]["top_blocker_pairs"],
            "shared-blocker.svg -> request-order.svg, icon.png -> request-order.svg, request-order.svg -> second-wave.svg, shared-blocker.svg -> second-wave.svg",
        )
        self.assertEqual(
            by_key[("u=5, i", "img")]["top_blocker_resources"],
            "shared-blocker.svg, icon.png, request-order.svg",
        )
        self.assertEqual(
            by_key[("u=5, i", "img")]["top_resources"],
            "request-order.svg, second-wave.svg",
        )

    def test_same_origin_should_throttle_connection_group_group_rows_capture_shared_pairs(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "run.mozlog.moz_log"
            first_uri = "https://www.torproject.org/static/request-order.svg"
            second_uri = "https://www.torproject.org/static/second-wave.svg"
            blocker_img_uri = "https://www.torproject.org/static/shared-blocker.svg"
            blocker_css_uri = "https://www.torproject.org/static/icon.png"
            log_path.write_text(
                "\n".join(
                    [
                        f"1970-01-01 00:00:01.100000 UTC - [Parent]: D/nsHttp HttpChannelParent RecvAsyncOpen [this=a1 uri={first_uri}, gid=42 browserid=5]",
                        "1970-01-01 00:00:01.110000 UTC - [Parent]: D/nsHttp Creating nsHttpChannel [this=abc123, nsIChannel=abc124]",
                        "1970-01-01 00:00:01.120000 UTC - [Parent]: D/nsHttp nsHttpChannel::DispatchTransaction [this=abc123, aTransWithStickyConn=0]",
                        "1970-01-01 00:00:01.130000 UTC - [Parent]: V/nsHttp Creating nsHttpTransaction @deadbeef",
                        "1970-01-01 00:00:01.140000 UTC - [Parent]: V/nsHttp nsHttpConnectionMgr::ShouldThrottle trans=deadbeef",
                        f"1970-01-01 00:00:01.200000 UTC - [Parent]: D/nsHttp HttpChannelParent RecvAsyncOpen [this=b2 uri={second_uri}, gid=43 browserid=5]",
                        "1970-01-01 00:00:01.210000 UTC - [Parent]: D/nsHttp Creating nsHttpChannel [this=abc456, nsIChannel=abc457]",
                        "1970-01-01 00:00:01.220000 UTC - [Parent]: D/nsHttp nsHttpChannel::DispatchTransaction [this=abc456, aTransWithStickyConn=0]",
                        "1970-01-01 00:00:01.230000 UTC - [Parent]: V/nsHttp Creating nsHttpTransaction @feedface",
                        "1970-01-01 00:00:01.240000 UTC - [Parent]: V/nsHttp nsHttpConnectionMgr::ShouldThrottle trans=feedface",
                    ]
                ),
                encoding="utf-8",
            )
            run = enable_probe(
                browser_run_with_resources(
                    files=[str(log_path)],
                    resources=[
                        {
                            "name": first_uri,
                            "fetchStart": 200.0,
                            "requestStart": 3100.0,
                            "responseStart": 3500.0,
                            "responseEnd": 3600.0,
                            "nextHopProtocol": "http/1.1",
                            "initiatorType": "img",
                        },
                        {
                            "name": second_uri,
                            "fetchStart": 220.0,
                            "requestStart": 3300.0,
                            "responseStart": 3700.0,
                            "responseEnd": 3800.0,
                            "nextHopProtocol": "http/1.1",
                            "initiatorType": "img",
                        },
                        {
                            "name": blocker_img_uri,
                            "fetchStart": 180.0,
                            "requestStart": 2800.0,
                            "responseStart": 3450.0,
                            "responseEnd": 3500.0,
                            "nextHopProtocol": "http/1.1",
                            "initiatorType": "img",
                        },
                        {
                            "name": blocker_css_uri,
                            "fetchStart": 150.0,
                            "requestStart": 2600.0,
                            "responseStart": 3380.0,
                            "responseEnd": 3400.0,
                            "nextHopProtocol": "http/1.1",
                            "initiatorType": "css",
                        },
                    ],
                ),
                rows=[
                    probe_row(
                        uri=first_uri,
                        observed_epoch_ms=1150.0,
                        priority_header="u=5, i",
                        connection_hash="group-a",
                    ),
                    probe_row(
                        uri=second_uri,
                        observed_epoch_ms=1160.0,
                        priority_header="u=5, i",
                        connection_hash="group-a",
                    ),
                    probe_row(
                        uri=blocker_img_uri,
                        observed_epoch_ms=1140.0,
                        priority_header="u=5, i",
                        connection_hash="group-a",
                    ),
                    probe_row(
                        uri=blocker_css_uri,
                        observed_epoch_ms=1130.0,
                        priority_header="u=4, i",
                        connection_hash="group-b",
                    ),
                ],
            )

            rows = same_origin_should_throttle_connection_group_group_rows(run, TARGET)

        by_key = {
            (row["priority_header"], row["initiator_type"]): row for row in rows
        }
        self.assertEqual(len(rows), 1)
        self.assertEqual(
            by_key[("u=5, i", "img")]["shared_connection_resources"],
            2,
        )
        self.assertEqual(
            by_key[("u=5, i", "img")]["median_shared_connection_pairs"],
            1.5,
        )
        self.assertEqual(
            by_key[("u=5, i", "img")]["median_request_to_response_start_ms"],
            400.0,
        )
        self.assertEqual(
            by_key[("u=5, i", "img")]["median_max_shared_pair_covered_ms"],
            350.0,
        )
        self.assertEqual(
            by_key[("u=5, i", "img")]["shared_connection_pair_scores"],
            {
                "shared-blocker.svg -> request-order.svg": 400.0,
                "request-order.svg -> second-wave.svg": 300.0,
                "shared-blocker.svg -> second-wave.svg": 200.0,
            },
        )
        self.assertEqual(
            by_key[("u=5, i", "img")]["shared_connection_resource_scores"],
            {
                "shared-blocker.svg": 600.0,
                "request-order.svg": 300.0,
            },
        )

    def test_should_throttle_connection_group_summary_rows_capture_shared_pairs(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "run.mozlog.moz_log"
            first_uri = "https://www.torproject.org/static/request-order.svg"
            second_uri = "https://www.torproject.org/static/second-wave.svg"
            blocker_img_uri = "https://www.torproject.org/static/shared-blocker.svg"
            blocker_css_uri = "https://www.torproject.org/static/icon.png"
            log_path.write_text(
                "\n".join(
                    [
                        f"1970-01-01 00:00:01.100000 UTC - [Parent]: D/nsHttp HttpChannelParent RecvAsyncOpen [this=a1 uri={first_uri}, gid=42 browserid=5]",
                        "1970-01-01 00:00:01.110000 UTC - [Parent]: D/nsHttp Creating nsHttpChannel [this=abc123, nsIChannel=abc124]",
                        "1970-01-01 00:00:01.120000 UTC - [Parent]: D/nsHttp nsHttpChannel::DispatchTransaction [this=abc123, aTransWithStickyConn=0]",
                        "1970-01-01 00:00:01.130000 UTC - [Parent]: V/nsHttp Creating nsHttpTransaction @deadbeef",
                        "1970-01-01 00:00:01.140000 UTC - [Parent]: V/nsHttp nsHttpConnectionMgr::ShouldThrottle trans=deadbeef",
                        f"1970-01-01 00:00:01.200000 UTC - [Parent]: D/nsHttp HttpChannelParent RecvAsyncOpen [this=b2 uri={second_uri}, gid=43 browserid=5]",
                        "1970-01-01 00:00:01.210000 UTC - [Parent]: D/nsHttp Creating nsHttpChannel [this=abc456, nsIChannel=abc457]",
                        "1970-01-01 00:00:01.220000 UTC - [Parent]: D/nsHttp nsHttpChannel::DispatchTransaction [this=abc456, aTransWithStickyConn=0]",
                        "1970-01-01 00:00:01.230000 UTC - [Parent]: V/nsHttp Creating nsHttpTransaction @feedface",
                        "1970-01-01 00:00:01.240000 UTC - [Parent]: V/nsHttp nsHttpConnectionMgr::ShouldThrottle trans=feedface",
                    ]
                ),
                encoding="utf-8",
            )
            run = enable_probe(
                browser_run_with_resources(
                    files=[str(log_path)],
                    resources=[
                        {
                            "name": first_uri,
                            "fetchStart": 200.0,
                            "requestStart": 3100.0,
                            "responseStart": 3500.0,
                            "responseEnd": 3600.0,
                            "nextHopProtocol": "http/1.1",
                            "initiatorType": "img",
                        },
                        {
                            "name": second_uri,
                            "fetchStart": 220.0,
                            "requestStart": 3300.0,
                            "responseStart": 3700.0,
                            "responseEnd": 3800.0,
                            "nextHopProtocol": "http/1.1",
                            "initiatorType": "img",
                        },
                        {
                            "name": blocker_img_uri,
                            "fetchStart": 180.0,
                            "requestStart": 2800.0,
                            "responseStart": 3450.0,
                            "responseEnd": 3500.0,
                            "nextHopProtocol": "http/1.1",
                            "initiatorType": "img",
                        },
                        {
                            "name": blocker_css_uri,
                            "fetchStart": 150.0,
                            "requestStart": 2600.0,
                            "responseStart": 3380.0,
                            "responseEnd": 3400.0,
                            "nextHopProtocol": "http/1.1",
                            "initiatorType": "css",
                        },
                    ],
                ),
                rows=[
                    probe_row(
                        uri=first_uri,
                        observed_epoch_ms=1150.0,
                        priority_header="u=5, i",
                        connection_hash="group-a",
                    ),
                    probe_row(
                        uri=second_uri,
                        observed_epoch_ms=1160.0,
                        priority_header="u=5, i",
                        connection_hash="group-a",
                    ),
                    probe_row(
                        uri=blocker_img_uri,
                        observed_epoch_ms=1140.0,
                        priority_header="u=5, i",
                        connection_hash="group-a",
                    ),
                    probe_row(
                        uri=blocker_css_uri,
                        observed_epoch_ms=1130.0,
                        priority_header="u=4, i",
                        connection_hash="group-b",
                    ),
                ],
            )
            payload = run_payload(
                profile_name="auto",
                cycle=1,
                log_path=str(log_path),
            )
            payload["benchmarks"][TARGET]["runs"] = [run]

            rows = should_throttle_connection_group_summary_rows(
                [payload], target_filter=set()
            )

        by_key = {
            (row["priority_header"], row["initiator_type"]): row for row in rows
        }
        self.assertEqual(len(rows), 1)
        self.assertEqual(
            by_key[("u=5, i", "img")]["median_shared_connection_resources"],
            2.0,
        )
        self.assertEqual(
            by_key[("u=5, i", "img")]["median_shared_connection_pairs"],
            1.5,
        )
        self.assertEqual(
            by_key[("u=5, i", "img")]["median_request_to_response_start_ms"],
            400.0,
        )
        self.assertEqual(
            by_key[("u=5, i", "img")]["median_max_shared_pair_covered_ms"],
            350.0,
        )
        self.assertEqual(
            by_key[("u=5, i", "img")]["top_shared_connection_pairs"],
            "shared-blocker.svg -> request-order.svg, request-order.svg -> second-wave.svg, shared-blocker.svg -> second-wave.svg",
        )
        self.assertEqual(
            by_key[("u=5, i", "img")]["top_shared_connection_resources"],
            "shared-blocker.svg, request-order.svg",
        )

    def test_summary_profile_delta_rows_skips_baseline(self) -> None:
        payload = {
            "delta_vs_baseline": {
                TARGET: {
                    "auto": {
                        "combined_wall_seconds": 0.0,
                        "elapsed_ms": 0.0,
                        "load_ms": 0.0,
                        "open_gate_wait_seconds": 0.0,
                    },
                    "tor_boot_95": {
                        "combined_wall_seconds": -1.0,
                        "elapsed_ms": -1000.0,
                        "load_ms": -900.0,
                        "open_gate_wait_seconds": -3.0,
                    },
                }
            }
        }

        rows = summary_profile_delta_rows(
            payload,
            baseline_profile="auto",
            target_filter=set(),
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["profile"], "tor_boot_95")

    def test_resolve_summary_path_and_load_run_payloads(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result_dir = Path(temp_dir) / "torfast-warm-open-benchmark-compare-1"
            result_dir.mkdir()
            summary_path = result_dir / "summary.json"
            summary_path.write_text("{}\n")
            run_path = result_dir / "run.json"
            run_path.write_text("{}\n")

            resolved = resolve_summary_path(str(result_dir), Path(temp_dir))
            run_payloads = load_run_payloads(result_dir)

        self.assertEqual(resolved, summary_path)
        self.assertEqual(len(run_payloads), 1)


if __name__ == "__main__":
    unittest.main()
