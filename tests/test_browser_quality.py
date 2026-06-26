import io
import hashlib
import json
import queue
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from run_browser_compare import (
    BROWSER_CONNECTION_PREF_KEYS,
    BROWSER_NET_MOZ_LOG,
    BROWSER_QUALITY_PREF_KEYS,
    C_TOR_SOCKS_FLAGS,
    REQUIRED_DEFAULT_PREFS,
    SocksClientToProxyParser,
    SocksProxyToClientParser,
    all_profiles_ok,
    boot_signal_lines,
    cleanup_browser_artifacts,
    cleanup_named_paths,
    collect_browser_connection_prefs,
    collect_browser_fingerprint_snapshot,
    collect_page_resource_discovery,
    collect_browser_quality_prefs,
    install_browser_request_blocker,
    configure_browser_lab_prefs,
    detect_source_tweaks,
    effective_arti_exit_selector_metadata,
    effective_arti_log_level,
    extra_arti_proxy_app_buffer_profile_name,
    parse_dir_bad_health_gate_combos,
    parse_extra_arti_bin_specs,
    parse_health_min_assigned_cap_combos,
    parse_same_iso_active_cap_combos,
    parse_same_iso_other_iso_assigned_cap_combos,
    parse_soft_timeout_combos,
    parse_soft_timeout_pending_hedge_combos,
    normalize_interleaved_boot_seconds_from_launch,
    proxy_relay_context_lines,
    proxy_signal_lines,
    record_proxy_run_signals,
    read_torrc_quality,
    run_arti,
    run_browser_benchmarks,
    run_interleaved_profiles,
    socks_reply_bind_port_tag_for_connection,
    start_arti,
    browser_net_log_env,
    summarize_browser_net_log,
    summarize_browser,
    validate_browser_fingerprint_snapshot,
    validate_browser_quality_prefs,
    validate_default_prefs,
    wait_for_line,
)
from analyze_browser_compare import (
    main as analyze_browser_compare_main,
    arti_exit_select_ab_rows,
    arti_profile_load_tail_resource_ab_rows,
    arti_profile_names,
    arti_profile_promotion_risk_detail_rows,
    arti_profile_promotion_risk_rows,
    arti_profile_promotion_risk_socks_context_rows,
    arti_profile_promotion_risk_stream_receiver_rows,
    arti_profile_selector_move_risk_rows,
    print_arti_profile_selector_move_risk_table,
    validate_browser_fingerprint_consistency,
    arti_profile_http_queue_shape_ab_rows,
    arti_profile_resource_http_phase_ab_rows,
    arti_profile_resource_type_ab_rows,
    arti_profile_queue_loss_mechanism_rows,
    arti_profile_queue_loss_reason_rows,
    arti_profile_queue_loss_cause_rows,
    arti_profile_queue_loss_choice_rows,
    arti_profile_queue_loss_capacity_rows,
    arti_selected_circuit_gap_predictability_rows,
    arti_selected_circuit_network_evidence_rows,
    arti_selected_stream_gap_resource_overlap_rows,
    arti_selected_stream_gap_slot_pressure_rows,
    arti_selected_stream_gap_cross_activity_rows,
    arti_one_eligible_open_circuit_burst_rows,
    arti_profile_queue_loss_selected_circuit_rows,
    arti_profile_same_isolation_topup_ab_rows,
    arti_profile_same_isolation_topup_nonuse_rows,
    arti_profile_same_isolation_topup_timing_rows,
    arti_profile_top_resource_ab_rows,
    arti_profile_top_resource_relay_ab_rows,
    arti_profile_late_queue_ab_rows,
    byte_tap_connection_rows,
    byte_tap_run_summary_rows,
    byte_tap_stream_data_epochs,
    count_event_at_least,
    count_pending_wait_events,
    count_proxy_log_signals,
    event_max,
    event_median,
    event_timestamp_gaps_ms,
    failed_run_cause_rows,
    failed_run_relay_tail_circuit_concentration_rows,
    failed_run_relay_tail_detail_rows,
    failed_run_rows,
    failed_run_stream_lifecycle_rows,
    failed_run_torfast_socks_rows,
    group_torfast_socks_timings,
    parse_torfast_candidate_assignment_summary,
    parse_torfast_candidate_health_summary,
    parse_torfast_channel_flush_timings,
    parse_torfast_circuit_assignments,
    parse_torfast_circuit_congestion_timings,
    parse_torfast_circuit_selection_timings,
    parse_torfast_open_support_summary,
    parse_torfast_exit_client_timings,
    parse_torfast_hs_client_timings,
    parse_torfast_hs_state_timings,
    parse_torfast_hs_timings,
    parse_torfast_hspool_timings,
    parse_torfast_relay_receive_timings,
    parse_torfast_socks_byte_events,
    parse_torfast_socks_timings,
    parse_torfast_stream_reactor_congestion_timings,
    parse_torfast_stream_scheduler_timings,
    parse_torfast_stream_lifecycle_timings,
    parse_torfast_stream_receiver_timings,
    parse_browser_net_log_timestamp_ms,
    parse_log_timestamp_ms,
    torfast_exit_client_slow_tunnel_rows,
    torfast_slow_connect_phase_rows,
    boot_directory_failure_rows,
    boot_directory_timeline_rows,
    load_tail_resource_delta_rows,
    load_tail_rows,
    load_aware_guardrail_kept_first,
    health_aware_changed_assignment,
    health_aware_guard_kept_assignment,
    notable_torfast_socks_stream_lifecycle_rows,
    paired_run_delta_rows,
    proxy_run_tail_rows,
    proxy_log_lines,
    promotion_blocker_summary_rows,
    promotion_resource_queue_regression_rows,
    promotion_slow_target_proof_rows,
    promotion_unresolved_slow_stream_rows,
    pre_network_cancel_summary_rows,
    resource_phase_ms,
    resource_connection_shape_rows,
    resource_queue_saturation_rows,
    resource_queue_lifecycle_evidence_rows,
    resource_queue_late_write_summary_rows,
    resource_queue_late_circuit_summary_rows,
    resource_queue_late_stream_detail_rows,
    resource_queue_slot_blocker_summary_rows,
    resource_queue_slot_blocker_rows,
    resource_queue_delta_rows,
    resource_rows_for_profile_target,
    resource_type_delta_rows,
    selected_stream_gap_slot_pressure_hint,
    row_count_at_least,
    row_max,
    resource_variant_swap_rows,
    variant_swap_window_rows,
    socks_first_byte_after_reply_median,
    socks_byte_event_rows,
    socks_rows_by_target_kind,
    subtract_numeric,
    successful_run_relay_tail_circuit_concentration_rows,
    top_resource_delta_rows,
    torfast_context_rows,
    torfast_hs_burst_run_rows,
    torfast_channel_flush_summary_rows,
    torfast_channel_flush_gap_rows,
    torfast_relay_receive_stream_rows,
    torfast_stream_lifecycle_response_gap_rows,
    torfast_relay_receive_circuit_gap_detail_rows,
    torfast_relay_receive_circuit_gap_summary_rows,
    torfast_relay_receive_gap_detail_rows,
    torfast_relay_receive_stream_gap_detail_rows,
    torfast_relay_receive_run_summary_rows,
    browser_navigation_socks_join_rows,
    browser_activity_probe_evidence_rows,
    browser_activity_tagged_connection_bridge_rows_for_run,
    browser_activity_tagged_connection_group_rows,
    browser_activity_tagged_connection_queue_cause_rows,
    browser_activity_tagged_connection_queue_cause_summary_rows,
    browser_activity_tagged_connection_resource_rows,
    browser_activity_tagged_connection_sequence_rows,
    browser_activity_tagged_stream_group_rows,
    browser_activity_tagged_stream_queue_cause_rows,
    browser_activity_tagged_stream_resource_rows,
    browser_activity_tagged_stream_sequence_rows,
    browser_net_log_channel_rows_for_run,
    browser_net_log_parent_bridge_rows_for_run,
    browser_net_log_resource_evidence_rows,
    browser_net_log_socks_stream_bridge_rows_for_run,
    browser_resource_byte_tap_group_rows,
    browser_resource_byte_tap_join_rows,
    browser_resource_byte_tap_relay_group_rows,
    browser_resource_stream_gap_byte_context_rows,
    browser_resource_stream_gap_context_rows,
    browser_resource_stream_gap_phase_summary_rows,
    browser_resource_queue_selection_context_rows,
    browser_resource_queue_choice_class_summary_rows,
    browser_resource_queue_socks_relay_cluster_rows,
    browser_resource_queue_socks_relay_tail_rows,
    browser_run_late_phase_queue_context_rows,
    browser_resource_socks_relay_join_rows,
    browser_resource_socks_relay_summary_rows,
    torfast_socks_close_shape_summary_rows,
    torfast_socks_no_tor_byte_timeout_rows,
    torfast_socks_no_tor_byte_resource_rows,
    torfast_socks_partial_idle_timeout_rows,
    torfast_socks_partial_idle_resource_rows,
    torfast_socks_relay_join_rows,
    torfast_socks_connect_retry_rows,
    torfast_socks_connect_hedge_rows,
    torfast_load_aware_selection_health_outcome_rows,
    torfast_bad_health_replacement_lifecycle_rows,
    torfast_same_isolation_topup_lifecycle_rows,
    bad_health_replacement_later_proof_label,
    bad_health_replacement_nonuse_reason,
    torfast_socks_relay_join_gap_detail_rows,
    torfast_socks_relay_circuit_quality_rows,
    torfast_socks_relay_circuit_quality_run_summary_rows,
    torfast_socks_relay_circuit_shape_rows,
    torfast_socks_relay_join_run_summary_rows,
    torfast_stream_receiver_gap_context_rows,
    torfast_stream_lifecycle_summary_rows,
    torfast_stream_receiver_not_connected_summary_rows,
    torfast_stream_receiver_terminal_summary_rows,
    torfast_stream_receiver_terminal_top_rows,
    torfast_stream_receiver_rows,
    torfast_stream_scheduler_late_circuit_fairness_rows,
    torfast_unfinished_socks_rows,
    torfast_slow_socks_rows,
)


def browser_compare_run(
    *,
    load_ms: float,
    response_start_ms: float,
    dom_content_loaded_ms: float,
    load_event_end_ms: float,
    resources: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "ok": True,
        "run_index": 1,
        "load_ms": load_ms,
        "elapsed_ms": load_ms + 200.0,
        "screenshot": {"bytes": 100},
        "performance_timing": {
            "navigation": {
                "responseStart": response_start_ms,
                "domContentLoadedEventEnd": dom_content_loaded_ms,
                "loadEventEnd": load_event_end_ms,
            },
            "resources": resources,
        },
    }


def browser_compare_variant_cancel_payload() -> dict[str, object]:
    target = "https://www.torproject.org/download/"
    png_url = (
        "https://www.torproject.org/static/images/download/png/get-connected@3x.png?h=5e2656db"
    )
    svg_url = (
        "https://www.torproject.org/static/images/download/svg/get-connected.svg?h=5e2656db"
    )
    fallback_url = (
        "https://www.torproject.org/static/js/fallback.js?h=8a716acd"
    )
    run = browser_compare_run(
        load_ms=2000.0,
        response_start_ms=100.0,
        dom_content_loaded_ms=600.0,
        load_event_end_ms=2000.0,
        resources=[
            {
                "name": png_url,
                "initiatorType": "img",
                "nextHopProtocol": "http/1.1",
                "duration": 0.0,
                "fetchStart": 900.0,
                "requestStart": 900.0,
                "responseStart": 900.0,
                "responseEnd": 900.0,
                "transferSize": 0.0,
                "encodedBodySize": 0.0,
            },
            {
                "name": fallback_url,
                "initiatorType": "script",
                "nextHopProtocol": "http/1.1",
                "duration": 0.0,
                "fetchStart": 950.0,
                "requestStart": 950.0,
                "responseStart": 950.0,
                "responseEnd": 950.0,
                "transferSize": 0.0,
                "encodedBodySize": 0.0,
            },
            {
                "name": svg_url,
                "initiatorType": "img",
                "nextHopProtocol": "http/1.1",
                "duration": 1200.0,
                "fetchStart": 1200.0,
                "requestStart": 1300.0,
                "responseStart": 1400.0,
                "responseEnd": 2000.0,
                "transferSize": 30272.0,
                "encodedBodySize": 29972.0,
            },
        ],
    )
    run["browser_activity_probe"] = {
        "enabled": True,
        "ok": True,
        "rows": [
            {
                "source": "observer_topic",
                "topic": "http-on-stop-request",
                "uri": png_url,
                "channel_id": 11,
            },
            {
                "source": "http_activity",
                "uri": png_url,
                "channel_id": 11,
            },
            {
                "source": "observer_topic",
                "topic": "http-on-stop-request",
                "uri": fallback_url,
                "channel_id": 12,
            },
            {
                "source": "observer_topic",
                "topic": "http-on-stop-request",
                "uri": fallback_url,
                "channel_id": 13,
            },
            {
                "source": "observer_topic",
                "topic": "http-on-examine-response",
                "uri": svg_url,
                "channel_id": 14,
                "localPort": 0,
                "remotePort": 443,
            },
            {
                "source": "observer_topic",
                "topic": "http-on-stop-request",
                "uri": svg_url,
                "channel_id": 14,
                "localPort": 0,
                "remotePort": 443,
            },
        ],
    }
    run["browser_request_blocker"] = {
        "enabled": True,
        "ok": True,
        "blocked_request_count": 2,
        "rows": [
            {"uri": fallback_url},
            {"uri": fallback_url},
        ],
    }
    run["performance_timing"]["page_resource_discovery"] = {
        "ok": True,
        "row_count": 1,
        "rows": [
            {
                "url": svg_url,
                "direct_ref_count": 1,
                "css_ref_count": 0,
                "dom_tags": ["img"],
                "dom_rels": [],
                "css_properties": [],
                "css_stylesheets": [],
                "css_selectors": [],
                "css_rule_kinds": [],
                "direct_refs": [],
                "css_refs": [],
            }
        ],
    }
    return {
        "targets": [target],
        "browser_default_prefs": {
            "ok": True,
            "prefs": dict(REQUIRED_DEFAULT_PREFS),
        },
        "profiles": {
            "arti_release_browser": {
                "benchmarks": {
                    target: {
                        "summary": {"ok": True},
                        "runs": [run],
                    }
                }
            }
        },
    }


def browser_compare_swap_window_payload() -> dict[str, object]:
    target = "https://www.torproject.org/download/"
    time_origin_ms = 1_000_000.0
    png_url = (
        "https://www.torproject.org/static/images/download/png/get-connected@3x.png?h=5e2656db"
    )
    svg_url = (
        "https://www.torproject.org/static/images/download/svg/get-connected.svg?h=5e2656db"
    )
    fallback_url = (
        "https://www.torproject.org/static/js/fallback.js?h=8a716acd"
    )
    bootstrap_url = (
        "https://www.torproject.org/static/css/bootstrap.css?h=0d5c9bf6"
    )
    run = browser_compare_run(
        load_ms=2000.0,
        response_start_ms=100.0,
        dom_content_loaded_ms=600.0,
        load_event_end_ms=2000.0,
        resources=[
            {
                "name": bootstrap_url,
                "initiatorType": "link",
                "nextHopProtocol": "http/1.1",
                "duration": 300.0,
                "fetchStart": 100.0,
                "requestStart": 100.0,
                "responseStart": 250.0,
                "responseEnd": 400.0,
                "transferSize": 29865.0,
                "encodedBodySize": 29565.0,
            },
            {
                "name": png_url,
                "initiatorType": "img",
                "nextHopProtocol": "http/1.1",
                "duration": 0.0,
                "fetchStart": 900.0,
                "requestStart": 900.0,
                "responseStart": 900.0,
                "responseEnd": 900.0,
                "transferSize": 0.0,
                "encodedBodySize": 0.0,
            },
            {
                "name": fallback_url,
                "initiatorType": "script",
                "nextHopProtocol": "http/1.1",
                "duration": 300.0,
                "fetchStart": 950.0,
                "requestStart": 950.0,
                "responseStart": 1100.0,
                "responseEnd": 1250.0,
                "transferSize": 1315.0,
                "encodedBodySize": 1015.0,
            },
            {
                "name": svg_url,
                "initiatorType": "img",
                "nextHopProtocol": "http/1.1",
                "duration": 500.0,
                "fetchStart": 1300.0,
                "requestStart": 1400.0,
                "responseStart": 1500.0,
                "responseEnd": 1800.0,
                "transferSize": 30272.0,
                "encodedBodySize": 29972.0,
            },
        ],
    )
    run["performance_timing"]["time_origin_ms"] = time_origin_ms
    run["browser_activity_probe"] = {
        "enabled": True,
        "ok": True,
        "rows": [
            {
                "source": "observer_topic",
                "topic": "http-on-stop-request",
                "uri": png_url,
                "channel_id": 11,
                "observed_epoch_ms": time_origin_ms + 1280.0,
            },
            {
                "source": "http_activity",
                "uri": png_url,
                "channel_id": 11,
                "observed_epoch_ms": time_origin_ms + 1280.0,
            },
            {
                "source": "observer_topic",
                "topic": "http-on-examine-response",
                "uri": fallback_url,
                "channel_id": 12,
                "observed_epoch_ms": time_origin_ms + 1100.0,
            },
            {
                "source": "observer_topic",
                "topic": "http-on-stop-request",
                "uri": fallback_url,
                "channel_id": 12,
                "observed_epoch_ms": time_origin_ms + 1250.0,
                "localPort": 0,
                "remotePort": 443,
            },
            {
                "source": "observer_topic",
                "topic": "http-on-examine-response",
                "uri": svg_url,
                "channel_id": 13,
                "observed_epoch_ms": time_origin_ms + 1500.0,
                "localPort": 0,
                "remotePort": 443,
            },
            {
                "source": "observer_topic",
                "topic": "http-on-stop-request",
                "uri": svg_url,
                "channel_id": 13,
                "observed_epoch_ms": time_origin_ms + 1800.0,
                "localPort": 0,
                "remotePort": 443,
            },
        ],
    }
    run["performance_timing"]["page_resource_discovery"] = {
        "ok": True,
        "row_count": 1,
        "rows": [
            {
                "url": svg_url,
                "direct_ref_count": 1,
                "css_ref_count": 0,
                "dom_tags": ["img"],
                "dom_rels": [],
                "css_properties": [],
                "css_stylesheets": [],
                "css_selectors": [],
                "css_rule_kinds": [],
                "direct_refs": [],
                "css_refs": [],
            }
        ],
    }
    return {
        "targets": [target],
        "browser_default_prefs": {
            "ok": True,
            "prefs": dict(REQUIRED_DEFAULT_PREFS),
        },
        "profiles": {
            "arti_release_browser": {
                "benchmarks": {
                    target: {
                        "summary": {"ok": True},
                        "runs": [run],
                    }
                }
            }
        },
    }


class BrowserQualityTests(unittest.TestCase):
    def test_accepts_required_default_prefs(self) -> None:
        result = validate_default_prefs(
            {"ok": True, "prefs": dict(REQUIRED_DEFAULT_PREFS)}
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["failures"], [])

    def test_rejects_changed_fingerprint_pref(self) -> None:
        prefs = dict(REQUIRED_DEFAULT_PREFS)
        prefs["privacy.resistFingerprinting"] = False

        result = validate_default_prefs({"ok": True, "prefs": prefs})

        self.assertFalse(result["ok"])
        self.assertIn(
            "privacy.resistFingerprinting: expected True, got False",
            result["failures"],
        )

    def test_summarizes_browser_performance_timing(self) -> None:
        result = summarize_browser(
            [
                {
                    "ok": True,
                    "elapsed_ms": 1000,
                    "load_ms": 800,
                    "screenshot": {"bytes": 100},
                    "performance_timing": {
                        "navigation": {
                            "responseStart": 100,
                            "domContentLoadedEventEnd": 700,
                            "loadEventEnd": 800,
                            "duration": 850,
                        },
                        "resource_count": 4,
                        "slowest_resources": [{"duration": 300}],
                    },
                }
            ]
        )

        self.assertEqual(result["median_nav_response_start_ms"], 100.0)
        self.assertEqual(result["median_nav_dom_content_loaded_ms"], 700.0)
        self.assertEqual(result["median_nav_load_event_ms"], 800.0)
        self.assertEqual(result["median_nav_response_to_dom_ms"], 600.0)
        self.assertEqual(result["median_nav_dom_to_load_ms"], 100.0)
        self.assertEqual(result["median_resource_count"], 4.0)

    def test_collects_browser_connection_pref_audit(self) -> None:
        class FakeClient:
            def __init__(self) -> None:
                self.commands = []

            def command(self, name, params):
                self.commands.append((name, params))
                if name == "WebDriver:ExecuteScript":
                    return {
                        "value": json.dumps(
                            {
                                "network.http.spdy.enabled.http2": {
                                    "type": "bool",
                                    "value": True,
                                },
                                "network.http.max-persistent-connections-per-server": {
                                    "type": "int",
                                    "value": 6,
                                },
                            }
                        )
                    }
                return {}

        client = FakeClient()

        result = collect_browser_connection_prefs(client)

        self.assertTrue(result["ok"])
        self.assertTrue(
            result["prefs"]["network.http.spdy.enabled.http2"]["value"]
        )
        self.assertEqual(
            result["prefs"]["network.http.max-persistent-connections-per-server"][
                "value"
            ],
            6,
        )
        self.assertEqual(
            client.commands[0], ("Marionette:SetContext", {"value": "chrome"})
        )
        self.assertEqual(
            client.commands[1][1]["args"][0], BROWSER_CONNECTION_PREF_KEYS
        )
        self.assertEqual(
            client.commands[-1], ("Marionette:SetContext", {"value": "content"})
        )

    def test_collects_page_resource_discovery(self) -> None:
        payload = {
            "ok": True,
            "row_count": 2,
            "rows": [
                {
                    "url": "https://www.torproject.org/fonts/fontawesome/png/white/brands/github.png",
                    "direct_ref_count": 0,
                    "css_ref_count": 1,
                    "dom_tags": [],
                    "css_properties": ["background-image"],
                    "css_stylesheets": [
                        "https://www.torproject.org/static/css/bootstrap.css?h=0d5c9bf6"
                    ],
                },
                {
                    "url": "https://www.torproject.org/static/images/tor-logo@2x.png?h=16ad42bc",
                    "direct_ref_count": 1,
                    "css_ref_count": 0,
                    "dom_tags": ["img"],
                    "css_properties": [],
                    "css_stylesheets": [],
                },
            ],
        }

        class FakeClient:
            def __init__(self) -> None:
                self.commands = []

            def command(self, name, params):
                self.commands.append((name, params))
                return {"value": json.dumps(payload)}

        discovery = collect_page_resource_discovery(FakeClient())

        self.assertTrue(discovery["ok"])
        self.assertEqual(discovery["row_count"], 2)
        self.assertEqual(discovery["rows"][0]["css_ref_count"], 1)
        self.assertEqual(discovery["rows"][1]["dom_tags"], ["img"])

    def test_configures_browser_serial_http_lab_prefs(self) -> None:
        class FakeClient:
            def __init__(self) -> None:
                self.commands = []

            def command(self, name, params):
                self.commands.append((name, params))
                if name == "WebDriver:ExecuteScript":
                    return {
                        "value": json.dumps(
                            {
                                "ok": True,
                                "prefs": {
                                    "network.http.max-connections": {
                                        "old_type": "int",
                                        "old_value": 900,
                                        "set_value": 1,
                                        "type": "int",
                                        "value": 1,
                                    },
                                },
                            }
                        )
                    }
                return {}

        client = FakeClient()

        result = configure_browser_lab_prefs(
            client, serial_http_connections=True
        )

        serial = result["serial_http_connections"]
        self.assertTrue(serial["enabled"])
        self.assertTrue(serial["ok"])
        self.assertEqual(
            serial["prefs"]["network.http.max-connections"]["value"], 1
        )
        self.assertEqual(
            client.commands[0], ("Marionette:SetContext", {"value": "chrome"})
        )
        self.assertEqual(
            client.commands[1][1]["args"][0]["network.http.max-connections"], 1
        )
        self.assertEqual(
            client.commands[-1], ("Marionette:SetContext", {"value": "content"})
        )

    def test_configures_browser_connection_cap_lab_pref(self) -> None:
        class FakeClient:
            def __init__(self) -> None:
                self.commands = []

            def command(self, name, params):
                self.commands.append((name, params))
                if name == "WebDriver:ExecuteScript":
                    return {
                        "value": json.dumps(
                            {
                                "ok": True,
                                "prefs": {
                                    "network.http.max-persistent-connections-per-server": {
                                        "old_type": "int",
                                        "old_value": 6,
                                        "set_value": 10,
                                        "type": "int",
                                        "value": 10,
                                    },
                                },
                            }
                        )
                    }
                return {}

        client = FakeClient()

        result = configure_browser_lab_prefs(
            client, max_persistent_connections_per_server=10
        )

        cap = result["max_persistent_connections_per_server"]
        self.assertTrue(cap["enabled"])
        self.assertEqual(cap["requested_value"], 10)
        self.assertTrue(cap["ok"])
        self.assertEqual(
            cap["prefs"]["network.http.max-persistent-connections-per-server"][
                "value"
            ],
            10,
        )
        self.assertEqual(
            client.commands[1][1]["args"][0][
                "network.http.max-persistent-connections-per-server"
            ],
            10,
        )

    def test_install_browser_request_blocker_normalizes_substrings(self) -> None:
        class FakeClient:
            def __init__(self) -> None:
                self.commands = []

            def command(self, name, params):
                self.commands.append((name, params))
                if name == "WebDriver:ExecuteScript":
                    return {
                        "value": json.dumps(
                            {
                                "enabled": True,
                                "ok": True,
                                "topic": "http-on-modify-request",
                                "url_substrings": ["/static/js/fallback.js"],
                            }
                        )
                    }
                return {}

        client = FakeClient()

        result = install_browser_request_blocker(
            client,
            url_substrings=[" /static/js/fallback.js ", "/static/js/fallback.js"],
        )

        self.assertTrue(result["enabled"])
        self.assertTrue(result["ok"])
        self.assertEqual(result["url_substrings"], ["/static/js/fallback.js"])
        self.assertEqual(
            client.commands[0], ("Marionette:SetContext", {"value": "chrome"})
        )
        self.assertEqual(
            client.commands[1][1]["args"][0], ["/static/js/fallback.js"]
        )
        self.assertEqual(
            client.commands[-1], ("Marionette:SetContext", {"value": "content"})
        )

    def test_collects_browser_quality_pref_audit(self) -> None:
        class FakeClient:
            def __init__(self) -> None:
                self.commands = []

            def command(self, name, params):
                self.commands.append((name, params))
                if name == "WebDriver:ExecuteScript":
                    return {
                        "value": json.dumps(
                            {
                                key: {
                                    "type": "bool" if isinstance(value, bool) else "string",
                                    "value": value,
                                }
                                for key, value in REQUIRED_DEFAULT_PREFS.items()
                            }
                        )
                    }
                return {}

        client = FakeClient()

        result = collect_browser_quality_prefs(client)

        self.assertTrue(result["ok"])
        self.assertTrue(result["prefs"]["privacy.firstparty.isolate"]["value"])
        self.assertTrue(result["prefs"]["privacy.resistFingerprinting"]["value"])
        self.assertEqual(
            client.commands[0], ("Marionette:SetContext", {"value": "chrome"})
        )
        self.assertEqual(client.commands[1][1]["args"][0], BROWSER_QUALITY_PREF_KEYS)
        self.assertEqual(
            client.commands[-1], ("Marionette:SetContext", {"value": "content"})
        )

    def test_validate_browser_quality_prefs_rejects_runtime_override(self) -> None:
        audit = {
            "ok": True,
            "prefs": {
                key: {
                    "type": "bool" if isinstance(value, bool) else "string",
                    "value": value,
                }
                for key, value in REQUIRED_DEFAULT_PREFS.items()
            },
        }
        audit["prefs"]["privacy.resistFingerprinting"]["value"] = False

        result = validate_browser_quality_prefs(audit)

        self.assertFalse(result["ok"])
        self.assertIn(
            "privacy.resistFingerprinting: expected True, got False",
            result["failures"],
        )

    def test_collects_browser_fingerprint_snapshot(self) -> None:
        class FakeClient:
            def __init__(self) -> None:
                self.commands = []

            def command(self, name, params):
                self.commands.append((name, params))
                return {
                    "value": json.dumps(
                        {
                            "userAgent": "Mozilla/5.0",
                            "platform": "Linux x86_64",
                            "oscpu": "Linux x86_64",
                            "language": "en-US",
                            "languages": ["en-US", "en"],
                            "hardwareConcurrency": 2,
                            "maxTouchPoints": 0,
                            "webdriver": False,
                            "doNotTrack": "1",
                            "cookieEnabled": True,
                            "timezone": "UTC",
                            "timezoneOffset": 0,
                            "innerWidth": 1000,
                            "innerHeight": 900,
                        }
                    )
                }

        result = collect_browser_fingerprint_snapshot(FakeClient())

        self.assertTrue(result["ok"])
        self.assertEqual(result["snapshot"]["timezone"], "UTC")
        self.assertEqual(result["snapshot"]["timezoneOffset"], 0)
        self.assertFalse(result["snapshot"]["webdriver"])

    def test_validate_browser_fingerprint_snapshot_rejects_non_utc_or_webdriver(self) -> None:
        audit = {
            "ok": True,
            "snapshot": {
                "webdriver": True,
                "timezone": "Asia/Ulaanbaatar",
                "timezoneOffset": -480,
            },
        }

        result = validate_browser_fingerprint_snapshot(audit)

        self.assertFalse(result["ok"])
        self.assertIn(
            "navigator.webdriver: expected False, got True",
            result["failures"],
        )
        self.assertIn(
            "timezone: expected a zero-offset Tor Browser zone, got 'Asia/Ulaanbaatar'",
            result["failures"],
        )
        self.assertIn(
            "timezoneOffset: expected 0, got -480",
            result["failures"],
        )

    def test_validate_browser_fingerprint_snapshot_accepts_zero_offset_tor_zone(self) -> None:
        audit = {
            "ok": True,
            "snapshot": {
                "webdriver": False,
                "timezone": "Atlantic/Reykjavik",
                "timezoneOffset": 0,
            },
        }

        result = validate_browser_fingerprint_snapshot(audit)

        self.assertTrue(result["ok"])

    def test_validate_browser_fingerprint_snapshot_can_allow_webdriver_artifact(self) -> None:
        audit = {
            "ok": True,
            "snapshot": {
                "webdriver": True,
                "timezone": "UTC",
                "timezoneOffset": 0,
            },
        }

        result = validate_browser_fingerprint_snapshot(
            audit,
            allow_webdriver_artifact=True,
        )

        self.assertTrue(result["ok"])

    def test_validate_browser_fingerprint_consistency_rejects_profile_mismatch(self) -> None:
        good_snapshot = {
            "ok": True,
            "snapshot": {
                "userAgent": "Mozilla/5.0",
                "platform": "Linux x86_64",
                "timezone": "UTC",
                "timezoneOffset": 0,
                "webdriver": False,
            },
        }
        bad_snapshot = {
            "ok": True,
            "snapshot": {
                "userAgent": "Different Agent",
                "platform": "Linux x86_64",
                "timezone": "UTC",
                "timezoneOffset": 0,
                "webdriver": False,
            },
        }
        payload = {
            "profiles": {
                "arti_release_browser": {
                    "benchmarks": {
                        "https://example.test/": {
                            "runs": [
                                {
                                    "run_index": 1,
                                    "browser_fingerprint_snapshot": good_snapshot,
                                }
                            ]
                        }
                    }
                },
                "local_c_tor_browser": {
                    "benchmarks": {
                        "https://example.test/": {
                            "runs": [
                                {
                                    "run_index": 1,
                                    "browser_fingerprint_snapshot": bad_snapshot,
                                }
                            ]
                        }
                    }
                },
            }
        }

        failures = validate_browser_fingerprint_consistency(payload)

        self.assertEqual(len(failures), 1)
        self.assertIn("fingerprint snapshot mismatch", failures[0])
        self.assertIn("userAgent", failures[0])

    def test_parse_soft_timeout_combos(self) -> None:
        self.assertEqual(parse_soft_timeout_combos(["5000:3"]), [(5000, 3)])

        with self.assertRaises(ValueError):
            parse_soft_timeout_combos(["5000"])

        with self.assertRaises(ValueError):
            parse_soft_timeout_combos(["fast:3"])

    def test_parse_soft_timeout_pending_hedge_combos(self) -> None:
        self.assertEqual(
            parse_soft_timeout_pending_hedge_combos(["5000:3:1500"]),
            [(5000, 3, 1500)],
        )

        with self.assertRaises(ValueError):
            parse_soft_timeout_pending_hedge_combos(["5000:3"])

        with self.assertRaises(ValueError):
            parse_soft_timeout_pending_hedge_combos(["5000:fast:1500"])

    def test_parse_dir_bad_health_gate_combos(self) -> None:
        self.assertEqual(
            parse_dir_bad_health_gate_combos(["5000:5:3"]),
            [(5000, 5, 3)],
        )
        self.assertEqual(
            parse_dir_bad_health_gate_combos(["5000:5:3", "6000:6:4"]),
            [(5000, 5, 3), (6000, 6, 4)],
        )

        for value in ["5000:5", "fast:5:3", "999:5:3", "5000:0:3", "5000:5:0"]:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    parse_dir_bad_health_gate_combos([value])

    def test_parse_same_iso_active_cap_combos(self) -> None:
        self.assertEqual(parse_same_iso_active_cap_combos(["2:1"]), [(2, 1)])
        self.assertEqual(
            parse_same_iso_active_cap_combos(["2:1", "3:2"]),
            [(2, 1), (3, 2)],
        )

        for value in ["2", "fast:1", "1:1", "2:0", "5:1", "2:33"]:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    parse_same_iso_active_cap_combos([value])

    def test_parse_health_min_assigned_cap_combos(self) -> None:
        self.assertEqual(
            parse_health_min_assigned_cap_combos(["16000:4"]),
            [(16000, 4)],
        )
        self.assertEqual(
            parse_health_min_assigned_cap_combos(["16000:4", "65536:8"]),
            [(16000, 4), (65536, 8)],
        )

        for value in ["16000", "fast:4", "16000:0", "16000:33", "1048577:4"]:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    parse_health_min_assigned_cap_combos([value])

    def test_parse_same_iso_other_iso_assigned_cap_combos(self) -> None:
        self.assertEqual(
            parse_same_iso_other_iso_assigned_cap_combos(["2:3:4"]),
            [(2, 3, 4)],
        )
        self.assertEqual(
            parse_same_iso_other_iso_assigned_cap_combos(["2:3:4", "3:4:8"]),
            [(2, 3, 4), (3, 4, 8)],
        )

        for value in [
            "2:3",
            "fast:3:4",
            "1:3:4",
            "2:0:4",
            "2:65:4",
            "2:3:0",
            "2:3:33",
        ]:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    parse_same_iso_other_iso_assigned_cap_combos([value])

    def test_parse_extra_arti_bin_specs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "arti-flowctl"
            self.assertEqual(
                parse_extra_arti_bin_specs([f"flowctl:{path}"]),
                [("arti_release_browser_flowctl", path.resolve())],
            )

        with self.assertRaises(ValueError):
            parse_extra_arti_bin_specs(["bad-label:/x"])
        with self.assertRaises(ValueError):
            parse_extra_arti_bin_specs(["missing"])

    def test_computes_resource_phase_fields(self) -> None:
        self.assertEqual(
            resource_phase_ms(
                {"requestStart": 100, "responseStart": 250, "responseEnd": 400},
                "requestWait",
            ),
            150.0,
        )
        self.assertEqual(
            resource_phase_ms(
                {"requestStart": 100, "responseStart": 250, "responseEnd": 400},
                "responseReceive",
            ),
            150.0,
        )
        self.assertEqual(
            resource_phase_ms({"requestWait": 12}, "requestWait"),
            12.0,
        )

    def test_resource_rows_prefers_full_resources(self) -> None:
        profile = {
            "benchmarks": {
                "https://example.com/": {
                    "runs": [
                        {
                            "ok": True,
                            "performance_timing": {
                                "resources": [{"name": "a"}, {"name": "b"}],
                                "slowest_resources": [{"name": "slow"}],
                            },
                        },
                        {
                            "ok": False,
                            "performance_timing": {
                                "resources": [{"name": "failed"}],
                            },
                        },
                    ]
                }
            }
        }

        rows = resource_rows_for_profile_target(profile, "https://example.com/")

        self.assertEqual([row["name"] for row in rows], ["a", "b"])

    def test_failed_run_rows_include_error_and_screenshot_state(self) -> None:
        payload = {
            "profiles": {
                "arti_release_browser_healthaware": {
                    "benchmarks": {
                        "https://www.torproject.org/download/": {
                            "summary": {"ok": False},
                            "runs": [
                                {
                                    "ok": False,
                                    "run_index": 3,
                                    "elapsed_ms": 61518.07,
                                    "load_ms": None,
                                    "timed_out": False,
                                    "error": "RuntimeError: about:neterror connectionFailure",
                                    "screenshot": {"exists": False, "bytes": 0},
                                },
                                {
                                    "ok": True,
                                    "run_index": 4,
                                    "elapsed_ms": 9559.269,
                                    "load_ms": 8088.618,
                                    "screenshot": {"exists": True, "bytes": 734099},
                                },
                            ],
                        }
                    }
                }
            }
        }

        rows = failed_run_rows(payload)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["profile"], "arti_release_browser_healthaware")
        self.assertEqual(rows[0]["run_index"], 3)
        self.assertEqual(rows[0]["elapsed_ms"], 61518.07)
        self.assertEqual(rows[0]["screenshot_exists"], False)
        self.assertIn("connectionFailure", rows[0]["error"])

    def test_failed_run_torfast_socks_rows_show_slow_failed_streams(self) -> None:
        payload = {
            "profiles": {
                "arti_release_browser": {
                    "benchmarks": {
                        "https://www.torproject.org/download/": {
                            "summary": {"ok": False},
                            "runs": [
                                {
                                    "ok": False,
                                    "run_index": 2,
                                    "elapsed_ms": 61265.92,
                                    "proxy_signal_lines": [
                                        "timing_id=11 command=CONNECT target_kind=hostname port=443 elapsed_ms=0 torfast socks timing request parsed",
                                    ],
                                    "proxy_output_tail": [
                                        "timing_id=11 port=443 connect_ms=0 elapsed_ms=0 torfast socks timing stream ready",
                                        "timing_id=11 target_kind=hostname port=443 relay_ms=60167 last_tor_to_client_ms=1100 elapsed_ms=60167 client_to_tor_bytes=2552 tor_to_client_bytes=7834 ok=false torfast socks timing relay finished",
                                    ],
                                }
                            ],
                        }
                    }
                }
            }
        }

        rows = failed_run_torfast_socks_rows(payload)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["profile"], "arti_release_browser")
        self.assertEqual(rows[0]["run_index"], 2)
        self.assertEqual(rows[0]["timing_id"], 11)
        self.assertEqual(rows[0]["reason"], "relay>=5s")
        self.assertEqual(rows[0]["relay_ms"], 60167)
        self.assertEqual(rows[0]["last_tor_to_client_ms"], 1100)
        self.assertEqual(rows[0]["tor_to_client_idle_after_last_ms"], 59067)
        self.assertEqual(rows[0]["ok"], False)

    def test_failed_run_stream_lifecycle_rows_explain_bad_stream_state(self) -> None:
        payload = {
            "profiles": {
                "arti_release_browser": {
                    "benchmarks": {
                        "https://www.torproject.org/": {
                            "summary": {"ok": False},
                            "runs": [
                                {
                                    "ok": False,
                                    "run_index": 2,
                                    "started_epoch_ms": 1000,
                                    "proxy_signal_lines": [
                                        "timing_id=30 target_kind=hostname port=443 circ_id=Circ 3.8 stream_id=56959 elapsed_ms=2 torfast socks timing stream linked",
                                        "timing_id=30 target_kind=hostname port=443 relay_ms=62857 elapsed_ms=62857 first_tor_to_client_ms=0 last_tor_to_client_ms=0 client_to_tor_bytes=1893 tor_to_client_bytes=0 ok=false torfast socks timing relay finished",
                                        "event_epoch_ms=1200 hop=Some(HopNum(2)) stream_id=56959 relay_cmd=RelayCmd(BEGIN) delivery=\"sent\" torfast stream lifecycle",
                                        "event_epoch_ms=1201 circ_id=Circ 3.8 hop=HopNum(2) stream_id=56959 relay_cmd=RelayCmd(BEGIN) channel_circ_id=2147483650 counts_toward_windows=false circuit_sender_queue_before_cells=0 circuit_sender_queue_after_cells=0 channel_queue_count_available=true channel_queue_before_cells=0 channel_queue_after_cells=1 delivery=\"channel_queued\" torfast stream lifecycle",
                                        "event_epoch_ms=63858 circ_id=Circ 3.8 hop=Some(HopNum(2)) stream_id=56959 connected=false pending_after_bytes=0 user_read_bytes=0 data_cells=0 error_kind=not_connected returned_eof=false first_data_after_start_ms=0 transfer_ms=0 idle_after_last_data_ms=0 max_data_gap_ms=0 relay_data_bytes=0 torfast stream receiver terminal",
                                        "timing_id=31 target_kind=onion port=443 connect_ms=3743 elapsed_ms=3743 torfast socks timing stream ready",
                                        "timing_id=31 target_kind=onion port=443 circ_id=Circ 3.9 stream_id=17574 elapsed_ms=3744 torfast socks timing stream linked",
                                        "timing_id=31 target_kind=onion port=443 relay_ms=58768 elapsed_ms=62511 first_tor_to_client_ms=4137 last_tor_to_client_ms=4617 client_to_tor_bytes=2076 tor_to_client_bytes=3514 ok=false torfast socks timing relay finished",
                                        "event_epoch_ms=4743 hop=Some(HopNum(3)) stream_id=17574 relay_cmd=RelayCmd(BEGIN) delivery=\"sent\" torfast stream lifecycle",
                                        "event_epoch_ms=5088 circ_id=Circ 3.9 (Tunnel 18) hop=Some(HopNum(3)) stream_id=17574 relay_cmd=RelayCmd(CONNECTED) data_len=0 queued_before_bytes=0 queued_after_bytes=0 closes_stream=false delivery=\"delivered\" torfast stream lifecycle",
                                        "event_epoch_ms=5482 circ_id=Circ 3.9 (Tunnel 18) hop=Some(HopNum(3)) stream_id=17574 relay_cmd=RelayCmd(DATA) data_len=498 queued_before_bytes=0 queued_after_bytes=498 closes_stream=false delivery=\"delivered\" torfast stream lifecycle",
                                        "event_epoch_ms=62856 circ_id=Circ 3.9 hop=Some(HopNum(3)) stream_id=17574 connected=true pending_after_bytes=0 user_read_bytes=3514 data_cells=9 error_kind=not_connected returned_eof=false first_data_after_start_ms=739 transfer_ms=479 idle_after_last_data_ms=57895 max_data_gap_ms=352 relay_data_bytes=3514 torfast stream receiver terminal",
                                    ],
                                }
                            ],
                        }
                    }
                }
            }
        }

        rows = {
            row["timing_id"]: row for row in failed_run_stream_lifecycle_rows(payload)
        }

        self.assertEqual(rows[30]["lifecycle_state"], "BEGIN queued to channel, no CONNECTED")
        self.assertEqual(rows[30]["begin_sent"], 1)
        self.assertEqual(rows[30]["channel_queued"], 1)
        self.assertEqual(rows[30]["max_channel_queue_after_cells"], 1)
        self.assertEqual(rows[30]["max_circuit_sender_queue_after_cells"], 0)
        self.assertEqual(rows[30]["channel_queue_unknown"], 0)
        self.assertEqual(rows[30]["connected_delivered"], 0)
        self.assertEqual(rows[30]["data_delivered"], 0)
        self.assertEqual(rows[30]["terminal_relay_bytes"], 0)
        self.assertEqual(rows[31]["lifecycle_state"], "DATA delivered, no EOF")
        self.assertEqual(rows[31]["begin_sent"], 1)
        self.assertEqual(rows[31]["connected_delivered"], 1)
        self.assertEqual(rows[31]["data_delivered"], 1)
        self.assertEqual(rows[31]["stream_gone"], 0)
        self.assertEqual(rows[31]["queue_full"], 0)
        self.assertEqual(rows[31]["terminal_idle_after_last_data_ms"], 57895)
        self.assertEqual(rows[31]["terminal_relay_bytes"], 3514)

    def test_notable_socks_stream_lifecycle_rows_include_successful_slow_streams(
        self,
    ) -> None:
        payload = {
            "profiles": {
                "arti_release_browser": {
                    "benchmarks": {
                        "https://www.torproject.org/": {
                            "summary": {"ok": True},
                            "runs": [
                                {
                                    "ok": True,
                                    "run_index": 1,
                                    "started_epoch_ms": 1000,
                                    "proxy_signal_lines": [
                                        "timing_id=11 target_kind=hostname port=443 circ_id=Circ 3.8 stream_id=56959 elapsed_ms=2 torfast socks timing stream linked",
                                        "timing_id=11 target_kind=hostname port=443 relay_ms=6100 elapsed_ms=6100 first_tor_to_client_ms=1200 last_tor_to_client_ms=6000 client_to_tor_bytes=1893 tor_to_client_bytes=7789 ok=false torfast socks timing relay finished",
                                        "event_epoch_ms=1100 circ_id=Circ 3.8 hop=HopNum(2) stream_id=56959 relay_cmd=RelayCmd(DATA) channel_circ_id=2147483650 circuit_sender_queue_after_cells=0 delivery=\"channel_queued\" torfast stream lifecycle",
                                        "event_epoch_ms=1200 circ_id=Circ 3.8 hop=Some(HopNum(2)) stream_id=56959 relay_cmd=RelayCmd(CONNECTED) data_len=0 queued_before_bytes=0 queued_after_bytes=0 closes_stream=false delivery=\"delivered\" torfast stream lifecycle",
                                        "event_epoch_ms=1300 circ_id=Circ 3.8 hop=Some(HopNum(2)) stream_id=56959 relay_cmd=RelayCmd(DATA) data_len=498 queued_before_bytes=0 queued_after_bytes=498 closes_stream=false delivery=\"delivered\" torfast stream lifecycle",
                                        "event_epoch_ms=6100 circ_id=Circ 3.8 hop=Some(HopNum(2)) stream_id=56959 connected=true pending_after_bytes=0 user_read_bytes=7789 data_cells=17 error_kind=not_connected returned_eof=false first_data_after_start_ms=200 transfer_ms=4800 idle_after_last_data_ms=100 max_data_gap_ms=50 relay_data_bytes=7789 torfast stream receiver terminal",
                                    ],
                                }
                            ],
                        }
                    }
                }
            }
        }

        rows = notable_torfast_socks_stream_lifecycle_rows(payload)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["timing_id"], 11)
        self.assertEqual(rows[0]["reason"], "relay>=5s")
        self.assertEqual(rows[0]["lifecycle_state"], "DATA delivered, no EOF")
        self.assertEqual(rows[0]["data_to_data_ms"], 200)
        self.assertEqual(rows[0]["max_circuit_sender_queue_after_cells"], 0)
        self.assertEqual(rows[0]["terminal_relay_bytes"], 7789)

    def test_proxy_run_tail_rows_include_last_proxy_line(self) -> None:
        payload = {
            "profiles": {
                "arti_release_browser_healthaware": {
                    "benchmarks": {
                        "https://www.torproject.org/download/": {
                            "summary": {"ok": True},
                            "runs": [
                                {
                                    "ok": True,
                                    "run_index": 1,
                                    "load_ms": 6026.292,
                                    "elapsed_ms": 7553.597,
                                    "proxy_output_tail": [
                                        "first proxy line",
                                        "last proxy line",
                                    ],
                                },
                                {
                                    "ok": True,
                                    "run_index": 2,
                                    "load_ms": 7206.535,
                                    "elapsed_ms": 8688.402,
                                },
                            ],
                        }
                    }
                }
            }
        }

        rows = proxy_run_tail_rows(payload)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["profile"], "arti_release_browser_healthaware")
        self.assertEqual(rows[0]["tail_lines"], 2)
        self.assertEqual(rows[0]["last_proxy_line"], "last proxy line")

    def test_resource_rows_falls_back_to_slowest_resources(self) -> None:
        profile = {
            "benchmarks": {
                "https://example.com/": {
                    "runs": [
                        {
                            "ok": True,
                            "performance_timing": {
                                "slowest_resources": [{"name": "slow"}],
                            },
                        }
                    ]
                }
            }
        }

        rows = resource_rows_for_profile_target(profile, "https://example.com/")

        self.assertEqual([row["name"] for row in rows], ["slow"])

    def test_resource_delta_rows_compare_arti_to_local_c_tor(self) -> None:
        payload = {
            "targets": ["https://example.com/"],
            "profiles": {
                "arti_release_browser": {
                    "benchmarks": {
                        "https://example.com/": {
                            "runs": [
                                {
                                    "ok": True,
                                    "performance_timing": {
                                        "navigation": {
                                            "domContentLoadedEventEnd": 200,
                                            "loadEventEnd": 600,
                                        },
                                        "resources": [
                                            {
                                                "name": "https://example.com/a.css",
                                                "initiatorType": "css",
                                                "duration": 300,
                                                "requestStart": 10,
                                                "responseStart": 110,
                                                "responseEnd": 310,
                                                "encodedBodySize": 1000,
                                            },
                                            {
                                                "name": "https://example.com/logo.png",
                                                "initiatorType": "img",
                                                "duration": 500,
                                                "requestStart": 20,
                                                "responseStart": 220,
                                                "responseEnd": 520,
                                                "encodedBodySize": 2000,
                                            },
                                        ]
                                    },
                                }
                            ]
                        }
                    }
                },
                "arti_release_browser_pending500ms": {
                    "benchmarks": {
                        "https://example.com/": {
                            "runs": [
                                {
                                    "run_index": 1,
                                    "ok": True,
                                    "load_ms": 650,
                                    "elapsed_ms": 750,
                                    "performance_timing": {
                                        "navigation": {
                                            "responseStart": 120,
                                            "domContentLoadedEventEnd": 210,
                                            "loadEventEnd": 650,
                                        },
                                        "resources": [
                                            {
                                                "name": "https://example.com/a.css",
                                                "initiatorType": "css",
                                                "duration": 350,
                                                "requestStart": 10,
                                                "responseStart": 130,
                                                "responseEnd": 360,
                                                "encodedBodySize": 1000,
                                            },
                                            {
                                                "name": "https://example.com/logo.png",
                                                "initiatorType": "img",
                                                "duration": 460,
                                                "requestStart": 20,
                                                "responseStart": 130,
                                                "responseEnd": 480,
                                                "encodedBodySize": 2000,
                                            },
                                        ],
                                    },
                                }
                            ]
                        }
                    }
                },
                "local_c_tor_browser": {
                    "benchmarks": {
                        "https://example.com/": {
                            "runs": [
                                {
                                    "ok": True,
                                    "performance_timing": {
                                        "navigation": {
                                            "domContentLoadedEventEnd": 180,
                                            "loadEventEnd": 500,
                                        },
                                        "resources": [
                                            {
                                                "name": "https://example.com/a.css",
                                                "initiatorType": "css",
                                                "duration": 200,
                                                "requestStart": 10,
                                                "responseStart": 60,
                                                "responseEnd": 210,
                                                "encodedBodySize": 1000,
                                            },
                                            {
                                                "name": "https://example.com/logo.png",
                                                "initiatorType": "img",
                                                "duration": 450,
                                                "requestStart": 20,
                                                "responseStart": 120,
                                                "responseEnd": 470,
                                                "encodedBodySize": 2000,
                                            },
                                        ]
                                    },
                                }
                            ]
                        }
                    }
                },
            },
        }

        type_rows = resource_type_delta_rows(
            payload,
            candidate_profile="arti_release_browser",
            baseline_profile="local_c_tor_browser",
        )
        top_rows = top_resource_delta_rows(
            payload,
            candidate_profile="arti_release_browser",
            baseline_profile="local_c_tor_browser",
        )

        css_row = next(row for row in type_rows if row["resource_type"] == "css")
        self.assertEqual(css_row["duration_delta_ms"], 100.0)
        self.assertEqual(css_row["wait_delta_ms"], 50.0)
        self.assertEqual(css_row["receive_delta_ms"], 50.0)
        self.assertEqual(top_rows[0]["resource"], "https://example.com/a.css")
        self.assertEqual(top_rows[0]["duration_delta_ms"], 100.0)

        tail_rows = load_tail_resource_delta_rows(
            payload,
            candidate_profile="arti_release_browser",
            baseline_profile="local_c_tor_browser",
        )
        self.assertEqual(tail_rows[0]["resource"], "https://example.com/a.css")
        self.assertEqual(tail_rows[0]["response_end_delta_ms"], 100.0)
        self.assertEqual(tail_rows[0]["tail_after_dom_delta_ms"], 80.0)
        self.assertEqual(tail_rows[0]["candidate_tail_after_dom_ms"], 110.0)
        self.assertEqual(tail_rows[0]["baseline_tail_after_dom_ms"], 30.0)

        type_ab_rows = arti_profile_resource_type_ab_rows(payload)
        css_ab_row = next(row for row in type_ab_rows if row["resource_type"] == "css")
        self.assertEqual(css_ab_row["candidate_profile"], "arti_release_browser_pending500ms")
        self.assertEqual(css_ab_row["baseline_profile"], "arti_release_browser")
        self.assertEqual(css_ab_row["duration_delta_ms"], 50.0)

        top_ab_rows = arti_profile_top_resource_ab_rows(payload)
        self.assertEqual(top_ab_rows[0]["resource"], "https://example.com/a.css")
        self.assertEqual(top_ab_rows[0]["duration_delta_ms"], 50.0)

        tail_ab_rows = arti_profile_load_tail_resource_ab_rows(payload)
        self.assertEqual(tail_ab_rows[0]["resource"], "https://example.com/a.css")
        self.assertEqual(tail_ab_rows[0]["response_end_delta_ms"], 50.0)
        self.assertEqual(tail_ab_rows[0]["tail_after_dom_delta_ms"], 40.0)

    def test_resource_connection_shape_rows_summarize_reuse_shape(self) -> None:
        payload = {
            "targets": ["https://example.com/"],
            "profiles": {
                "arti_release_browser": {
                    "benchmarks": {
                        "https://example.com/": {
                            "runs": [
                                {
                                    "ok": True,
                                    "performance_timing": {
                                        "resources": [
                                            {
                                                "name": "https://static.example/a.css",
                                                "nextHopProtocol": "h2",
                                                "fetchStart": 100,
                                                "requestStart": 150,
                                                "responseStart": 200,
                                            },
                                            {
                                                "name": "https://static.example/b.js",
                                                "nextHopProtocol": "h2",
                                                "fetchStart": 104,
                                                "requestStart": 250,
                                                "responseStart": 300,
                                            },
                                            {
                                                "name": "https://cdn.example/c.png",
                                                "fetchStart": 410,
                                                "requestStart": 420,
                                                "responseStart": 440,
                                            },
                                        ]
                                    },
                                }
                            ]
                        }
                    }
                }
            },
        }

        rows = resource_connection_shape_rows(payload)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["resource_count"], 3)
        self.assertEqual(rows[0]["origin_count"], 2)
        self.assertAlmostEqual(rows[0]["top_origin_share_pct"], 66.666, places=2)
        self.assertEqual(rows[0]["protocol_summary"], "h2:2, unknown:1")
        self.assertEqual(rows[0]["fetch_start_bucket_count"], 2)
        self.assertAlmostEqual(
            rows[0]["top_fetch_start_bucket_share_pct"], 66.666, places=2
        )
        self.assertEqual(rows[0]["request_start_span_ms"], 270.0)
        self.assertEqual(rows[0]["median_fetch_to_request_ms"], 50.0)
        self.assertEqual(rows[0]["max_fetch_to_request_ms"], 146.0)
        self.assertEqual(rows[0]["fetch_to_request_100ms"], 1)
        self.assertEqual(rows[0]["fetch_to_request_500ms"], 0)
        self.assertEqual(rows[0]["fetch_to_request_1000ms"], 0)
        self.assertEqual(rows[0]["median_request_wait_ms"], 50.0)

    def test_resource_queue_delta_rows_compare_arti_to_local_c_tor(self) -> None:
        payload = {
            "targets": ["https://example.com/"],
            "profiles": {
                "arti_release_browser": {
                    "benchmarks": {
                        "https://example.com/": {
                            "runs": [
                                {
                                    "ok": True,
                                    "performance_timing": {
                                        "resources": [
                                            {
                                                "name": "https://example.com/a.css",
                                                "nextHopProtocol": "http/1.1",
                                                "duration": 1500,
                                                "fetchStart": 0,
                                                "requestStart": 1000,
                                                "responseStart": 1200,
                                            },
                                            {
                                                "name": "https://example.com/b.css",
                                                "nextHopProtocol": "http/1.1",
                                                "duration": 600,
                                                "fetchStart": 0,
                                                "requestStart": 200,
                                                "responseStart": 350,
                                            },
                                        ]
                                    },
                                }
                            ]
                        }
                    }
                },
                "local_c_tor_browser": {
                    "benchmarks": {
                        "https://example.com/": {
                            "runs": [
                                {
                                    "ok": True,
                                    "performance_timing": {
                                        "resources": [
                                            {
                                                "name": "https://example.com/a.css",
                                                "nextHopProtocol": "http/1.1",
                                                "duration": 900,
                                                "fetchStart": 0,
                                                "requestStart": 600,
                                                "responseStart": 750,
                                            },
                                            {
                                                "name": "https://example.com/b.css",
                                                "nextHopProtocol": "http/1.1",
                                                "duration": 500,
                                                "fetchStart": 0,
                                                "requestStart": 50,
                                                "responseStart": 150,
                                            },
                                        ]
                                    },
                                }
                            ]
                        }
                    }
                },
            },
        }

        rows = resource_queue_delta_rows(
            payload,
            candidate_profile="arti_release_browser",
            baseline_profile="local_c_tor_browser",
        )

        all_row = next(row for row in rows if row["group"] == "all")
        self.assertEqual(all_row["candidate_count"], 2)
        self.assertEqual(all_row["baseline_count"], 2)
        self.assertEqual(all_row["fetch_to_request_100_delta"], 1)
        self.assertEqual(all_row["fetch_to_request_500_delta"], 0)
        self.assertEqual(all_row["fetch_to_request_1000_delta"], 1)
        self.assertEqual(all_row["median_fetch_to_request_delta_ms"], 275.0)
        self.assertEqual(all_row["max_fetch_to_request_delta_ms"], 400.0)
        self.assertEqual(all_row["median_request_wait_delta_ms"], 50.0)
        self.assertEqual(all_row["median_duration_delta_ms"], 350.0)

        protocol_row = next(row for row in rows if row["group"] == "protocol:http/1.1")
        self.assertEqual(protocol_row["fetch_to_request_1000_delta"], 1)

    def test_resource_queue_saturation_rows_count_same_origin_slots(self) -> None:
        payload = {
            "targets": ["https://example.com/"],
            "profiles": {
                "arti_release_browser": {
                    "benchmarks": {
                        "https://example.com/": {
                            "runs": [
                                {
                                    "ok": True,
                                    "performance_timing": {
                                        "resources": [
                                            {
                                                "name": "https://example.com/open-a.css",
                                                "nextHopProtocol": "http/1.1",
                                                "fetchStart": 0,
                                                "requestStart": 0,
                                                "responseEnd": 1000,
                                            },
                                            {
                                                "name": "https://example.com/open-b.css",
                                                "nextHopProtocol": "http/1.1",
                                                "fetchStart": 0,
                                                "requestStart": 0,
                                                "responseEnd": 1000,
                                            },
                                            {
                                                "name": "https://example.com/queued.css",
                                                "nextHopProtocol": "http/1.1",
                                                "fetchStart": 0,
                                                "requestStart": 500,
                                                "responseEnd": 900,
                                            },
                                            {
                                                "name": "https://static.example/other.css",
                                                "nextHopProtocol": "http/1.1",
                                                "fetchStart": 0,
                                                "requestStart": 600,
                                                "responseEnd": 900,
                                            },
                                        ]
                                    },
                                }
                            ]
                        }
                    }
                }
            },
        }

        rows = resource_queue_saturation_rows(payload)

        all_row = next(row for row in rows if row["group"] == "all")
        self.assertEqual(all_row["queued_500ms"], 2)
        self.assertEqual(all_row["queued_1000ms"], 0)
        self.assertEqual(all_row["slot_depth_6"], 0)
        self.assertEqual(all_row["median_slot_depth_at_request"], 2.0)
        self.assertEqual(all_row["max_slot_depth_at_request"], 3)
        self.assertEqual(all_row["median_fetch_to_request_ms"], 550.0)
        self.assertEqual(all_row["max_fetch_to_request_ms"], 600.0)
        self.assertIn("queued.css", all_row["top_resources"])

        protocol_row = next(row for row in rows if row["group"] == "protocol:http/1.1")
        self.assertEqual(protocol_row["queued_500ms"], 2)

    def test_resource_variant_swap_rows_detect_png_to_svg_swap(self) -> None:
        rows = resource_variant_swap_rows(browser_compare_variant_cancel_payload())

        row = next(row for row in rows if row["loaded_family"] == "download png")
        self.assertEqual(row["current_family"], "download svg")
        self.assertEqual(row["resources"], 1)
        self.assertEqual(row["median_request_start_ms"], 900.0)
        self.assertIn("get-connected@3x.png", row["top_loaded_resources"])
        self.assertIn("get-connected.svg", row["top_current_resources"])

    def test_pre_network_cancel_summary_rows_capture_placeholder_and_blocked_rows(
        self,
    ) -> None:
        rows = pre_network_cancel_summary_rows(
            browser_compare_variant_cancel_payload()
        )

        png_row = next(row for row in rows if row["loaded_family"] == "download png")
        fallback_row = next(row for row in rows if row["loaded_family"] == "site js")

        self.assertEqual(png_row["current_family"], "download svg")
        self.assertFalse(png_row["request_blocked"])
        self.assertEqual(png_row["resources"], 1)
        self.assertEqual(png_row["unique_resources"], 1)
        self.assertEqual(png_row["stop_request_rows"], 1)
        self.assertEqual(png_row["channel_count"], 1)
        self.assertEqual(png_row["median_request_start_ms"], 900.0)
        self.assertIn("get-connected@3x.png", png_row["top_loaded_resources"])
        self.assertIn("get-connected.svg", png_row["top_current_resources"])

        self.assertEqual(fallback_row["current_family"], "site js")
        self.assertTrue(fallback_row["request_blocked"])
        self.assertEqual(fallback_row["resources"], 1)
        self.assertEqual(fallback_row["stop_request_rows"], 2)
        self.assertEqual(fallback_row["channel_count"], 2)
        self.assertIn("fallback.js", fallback_row["top_loaded_resources"])
        self.assertEqual(fallback_row["top_current_resources"], "")

    def test_analyze_browser_compare_main_prints_cancel_and_variant_sections(
        self,
    ) -> None:
        payload = browser_compare_variant_cancel_payload()

        with tempfile.TemporaryDirectory() as tmp:
            result_path = Path(tmp) / "browser-compare.json"
            result_path.write_text(json.dumps(payload), encoding="utf-8")
            stdout = io.StringIO()
            with patch("sys.argv", ["analyze_browser_compare.py", str(result_path)]):
                with patch("sys.stdout", stdout):
                    exit_code = analyze_browser_compare_main()

        output = stdout.getvalue()
        self.assertEqual(exit_code, 1)
        self.assertIn("## Pre-Network Cancels", output)
        self.assertIn("## Variant Swaps", output)
        self.assertIn("download png", output)
        self.assertIn("download svg", output)

    def test_variant_swap_window_rows_capture_bootstrap_fallback_cancel_timing(
        self,
    ) -> None:
        rows = variant_swap_window_rows(browser_compare_swap_window_payload())

        row = next(row for row in rows if row["loaded_family"] == "download png")
        self.assertEqual(row["current_family"], "download svg")
        self.assertEqual(row["resources"], 1)
        self.assertEqual(row["bootstrap_css_response_end_ms"], 400.0)
        self.assertEqual(row["fallback_js_request_start_ms"], 950.0)
        self.assertEqual(row["fallback_js_response_end_ms"], 1250.0)
        self.assertEqual(row["loaded_first_request_start_ms"], 900.0)
        self.assertEqual(row["pre_network_cancel_resources"], 1)
        self.assertEqual(row["pre_network_cancel_first_stop_request_ms"], 1280.0)
        self.assertEqual(row["current_first_request_start_ms"], 1400.0)
        self.assertEqual(
            row["bootstrap_css_end_to_fallback_js_request_ms"], 550.0
        )
        self.assertEqual(
            row["fallback_js_end_to_cancel_stop_request_ms"], 30.0
        )
        self.assertEqual(
            row["fallback_js_end_to_current_request_ms"], 150.0
        )

    def test_analyze_browser_compare_main_prints_variant_swap_window_section(
        self,
    ) -> None:
        payload = browser_compare_swap_window_payload()

        with tempfile.TemporaryDirectory() as tmp:
            result_path = Path(tmp) / "browser-compare.json"
            result_path.write_text(json.dumps(payload), encoding="utf-8")
            stdout = io.StringIO()
            with patch("sys.argv", ["analyze_browser_compare.py", str(result_path)]):
                with patch("sys.stdout", stdout):
                    exit_code = analyze_browser_compare_main()

        output = stdout.getvalue()
        self.assertEqual(exit_code, 1)
        self.assertIn("## Variant Swap Windows", output)
        self.assertIn("bootstrap.css end ms", output)
        self.assertIn("fallback.js request ms", output)

    def test_resource_queue_slot_blocker_rows_include_joined_blocker(self) -> None:
        base = int(parse_log_timestamp_ms("2026-06-06T23:12:37Z x") or 0)
        payload = {
            "profiles": {
                "arti_release_browser": {
                    "proxy_output_tail": [
                        f"timing_id=7 target_kind=hostname port=443 conn_started_epoch_ms={base + 105} circ_id=Circ 0.4 hop=3 stream_id=11302 elapsed_ms=122 torfast socks timing stream linked",
                        f"timing_id=7 target_kind=hostname port=443 conn_started_epoch_ms={base + 105} relay_ms=1900 first_tor_to_client_ms=145 first_tor_to_client_epoch_ms={base + 250} first_tor_to_client_write_ms=185 first_tor_to_client_write_epoch_ms={base + 290} last_tor_to_client_ms=1895 last_tor_to_client_write_ms=1895 tor_to_client_idle_after_last_ms=27 tor_to_client_bytes=3400 tor_to_client_write_bytes=3400 elapsed_ms=1922 ok=true torfast socks timing relay finished",
                        f"event_epoch_ms={base + 300} circ_id=Circ 0.4 (Tunnel 15) hop=Some(HopNum(3)) stream_id=11302 relay_cmd=RelayCmd(DATA) data_len=498 queued_before_bytes=0 queued_after_bytes=498 closes_stream=false torfast relay receive delivered",
                        f"event_epoch_ms={base + 2000} circ_id=Circ 0.4 (Tunnel 15) hop=Some(HopNum(3)) stream_id=11302 relay_cmd=RelayCmd(DATA) data_len=300 queued_before_bytes=0 queued_after_bytes=300 closes_stream=false torfast relay receive delivered",
                        "2026-06-06T23:12:38Z DEBUG tor_proto::client::reactor::circuit::circhop: circ_id=Circ 0.4 (Tunnel 15) hop=#3 stream_id=11302 relay_cmd=DATA torfast stream scheduler picked",
                        "2026-06-06T23:12:39Z DEBUG tor_proto::client::reactor::circuit::circhop: circ_id=Circ 0.4 (Tunnel 15) hop=#3 stream_id=11302 relay_cmd=DATA torfast stream scheduler picked",
                        "2026-06-06T23:12:40Z DEBUG tor_proto::client::reactor::circuit::circhop: circ_id=Circ 0.4 (Tunnel 15) hop=#3 stream_id=11303 relay_cmd=DATA torfast stream scheduler picked",
                        "2026-06-06T23:12:41Z DEBUG tor_proto::client::reactor::circuit::circhop: circ_id=Circ 0.4 (Tunnel 15) hop=#3 stream_id=11302 relay_cmd=DATA torfast stream scheduler picked",
                        f"event_epoch_ms={base + 2000} stream_id=11302 hop=None relay_cmd=DATA data_len=300 queued_after_bytes=0 recv_window_before=500 recv_window_after=499 sendme_due=false torfast stream receiver read",
                        f"event_epoch_ms={base + 2000} circ_id=Circ 0.4 (Tunnel 15) hop=#3 stream_id=11302 connected=true first_data_after_start_ms=145 transfer_ms=1700 idle_after_last_data_ms=0 max_data_gap_ms=1700 relay_data_bytes=3400 pending_after_bytes=0 user_read_bytes=3400 data_cells=7 read_events=7 sendmes=1 sendme_ok=1 min_recv_window_after_take=450 max_queued_after_bytes=498 error_kind= end_reason= returned_eof=true torfast stream receiver terminal summary",
                    ],
                    "benchmarks": {
                        "https://example.com/": {
                            "runs": [
                                {
                                    "run_index": 1,
                                    "ok": True,
                                    "performance_timing": {
                                        "time_origin_ms": base,
                                        "resources": [
                                            {
                                                "name": "https://example.com/open-a.css",
                                                "initiatorType": "link",
                                                "nextHopProtocol": "http/1.1",
                                                "connectStart": 100,
                                                "fetchStart": 0,
                                                "requestStart": 100,
                                                "responseStart": 450,
                                                "responseEnd": 2000,
                                            },
                                            {
                                                "name": "https://static.example/other.css",
                                                "nextHopProtocol": "http/1.1",
                                                "fetchStart": 0,
                                                "requestStart": 100,
                                                "responseEnd": 2000,
                                            },
                                            {
                                                "name": "https://example.com/queued.css",
                                                "nextHopProtocol": "http/1.1",
                                                "fetchStart": 0,
                                                "requestStart": 1200,
                                                "responseStart": 1300,
                                                "responseEnd": 1500,
                                            },
                                        ],
                                    },
                                }
                            ]
                        }
                    },
                }
            }
        }

        rows = resource_queue_slot_blocker_rows(payload)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["queued_resource"], "https://example.com/queued.css")
        self.assertEqual(rows[0]["fetch_to_request_ms"], 1200.0)
        self.assertEqual(rows[0]["slot_depth_at_request"], 2)
        self.assertEqual(rows[0]["active_blockers"], 1)
        self.assertEqual(rows[0]["max_blocker_remaining_ms"], 800.0)
        self.assertEqual(rows[0]["blockers_waiting_for_first_byte"], 0)
        self.assertEqual(rows[0]["blockers_receiving_body"], 1)
        self.assertEqual(rows[0]["max_blocker_wait_remaining_ms"], 0.0)
        self.assertEqual(rows[0]["max_blocker_receive_remaining_ms"], 800.0)
        self.assertEqual(
            rows[0]["max_blocker_last_write_after_queued_request_ms"], 800.0
        )
        self.assertEqual(
            rows[0]["median_blocker_response_end_after_last_write_ms"], 0.0
        )
        self.assertEqual(
            rows[0]["high_conf_max_blocker_last_write_after_queued_request_ms"],
            800.0,
        )

        summary_rows = resource_queue_slot_blocker_summary_rows(payload)

        self.assertEqual(len(summary_rows), 1)
        self.assertEqual(summary_rows[0]["queued_resources"], 1)
        self.assertEqual(summary_rows[0]["slot_depth_6"], 0)
        self.assertEqual(summary_rows[0]["rows_with_active_blockers"], 1)
        self.assertEqual(summary_rows[0]["receive_dominant_rows"], 1)
        self.assertEqual(summary_rows[0]["wait_dominant_rows"], 0)
        self.assertEqual(summary_rows[0]["high_conf_write_after_queue_500ms"], 1)
        self.assertEqual(summary_rows[0]["high_conf_write_after_queue_1000ms"], 0)
        self.assertEqual(summary_rows[0]["blockers_left_500ms"], 0)
        self.assertEqual(summary_rows[0]["rows_with_joined_blockers"], 1)
        self.assertEqual(summary_rows[0]["rows_with_high_conf_blockers"], 1)
        self.assertEqual(summary_rows[0]["median_fetch_to_request_ms"], 1200.0)
        self.assertEqual(summary_rows[0]["max_fetch_to_request_ms"], 1200.0)
        self.assertEqual(summary_rows[0]["median_max_blocker_remaining_ms"], 800.0)
        self.assertEqual(summary_rows[0]["max_blocker_remaining_ms"], 800.0)
        self.assertEqual(
            summary_rows[0]["median_queue_minus_max_blocker_left_ms"], 400.0
        )
        self.assertEqual(summary_rows[0]["median_max_blocker_wait_left_ms"], 0.0)
        self.assertEqual(summary_rows[0]["median_max_blocker_receive_left_ms"], 800.0)
        self.assertEqual(
            summary_rows[0][
                "median_high_conf_max_blocker_last_write_after_queued_request_ms"
            ],
            800.0,
        )
        self.assertEqual(summary_rows[0]["max_blocker_relay_ms"], 1900.0)
        self.assertEqual(
            summary_rows[0]["top_queued_resource"], "example.com/queued.css"
        )
        self.assertEqual(summary_rows[0]["blocker_timing_ids"], "7")
        self.assertEqual(
            summary_rows[0]["blocker_circuits"], "Circ 0.4 (Tunnel 15)"
        )

        late_write_rows = resource_queue_late_write_summary_rows(payload)

        self.assertEqual(len(late_write_rows), 1)
        self.assertEqual(late_write_rows[0]["high_conf_queued_rows"], 1)
        self.assertEqual(late_write_rows[0]["high_conf_write_after_queue_500ms"], 1)
        self.assertEqual(late_write_rows[0]["high_conf_write_after_queue_1000ms"], 0)
        self.assertEqual(
            late_write_rows[0]["median_high_conf_write_after_queue_ms"], 800.0
        )
        self.assertEqual(
            late_write_rows[0]["max_high_conf_write_after_queue_ms"], 800.0
        )
        self.assertEqual(late_write_rows[0]["terminal_coverage_rows"], 1)
        self.assertEqual(
            late_write_rows[0]["terminal_last_data_after_queue_1000ms"], 0
        )
        self.assertEqual(
            late_write_rows[0]["median_terminal_last_data_after_queue_ms"], 800.0
        )
        self.assertEqual(
            late_write_rows[0]["max_terminal_last_data_after_queue_ms"], 800.0
        )
        self.assertEqual(
            late_write_rows[0]["median_write_after_terminal_last_data_ms"], 0.0
        )
        self.assertEqual(
            late_write_rows[0]["max_write_after_terminal_last_data_ms"], 0.0
        )
        self.assertEqual(late_write_rows[0]["max_terminal_data_gap_ms"], 1700.0)
        self.assertEqual(
            late_write_rows[0]["max_terminal_idle_after_last_data_ms"], 0.0
        )
        self.assertEqual(late_write_rows[0]["max_terminal_pending_after_bytes"], 0.0)
        self.assertEqual(late_write_rows[0]["terminal_sendmes"], 1.0)
        self.assertEqual(late_write_rows[0]["terminal_sendme_ok"], 1.0)
        self.assertEqual(
            late_write_rows[0]["min_terminal_recv_window_after_take"], 450.0
        )
        self.assertEqual(late_write_rows[0]["max_terminal_queued_after_bytes"], 498.0)
        self.assertEqual(late_write_rows[0]["browser_release_after_write_rows"], 0)
        self.assertEqual(late_write_rows[0]["browser_release_after_write_500ms"], 0)
        self.assertEqual(late_write_rows[0]["response_before_last_write_rows"], 0)
        self.assertIsNone(
            late_write_rows[0]["median_positive_browser_release_after_write_ms"]
        )
        self.assertEqual(
            late_write_rows[0]["top_late_queued_resource"], "example.com/queued.css"
        )
        self.assertEqual(late_write_rows[0]["blocker_timing_ids"], "7")
        self.assertEqual(
            late_write_rows[0]["blocker_circuits"], "Circ 0.4 (Tunnel 15)"
        )

        late_stream_rows = resource_queue_late_stream_detail_rows(payload)

        self.assertEqual(len(late_stream_rows), 1)
        self.assertEqual(
            late_stream_rows[0]["queued_resource"],
            "https://example.com/queued.css",
        )
        self.assertEqual(late_stream_rows[0]["fetch_to_request_ms"], 1200.0)
        self.assertEqual(late_stream_rows[0]["slot_depth_at_request"], 2)
        self.assertEqual(
            late_stream_rows[0][
                "high_conf_max_terminal_last_data_after_queued_request_ms"
            ],
            800.0,
        )
        self.assertEqual(
            late_stream_rows[0][
                "high_conf_max_blocker_last_write_after_queued_request_ms"
            ],
            800.0,
        )
        self.assertEqual(
            late_stream_rows[0][
                "high_conf_max_last_write_after_terminal_last_data_ms"
            ],
            0.0,
        )
        self.assertEqual(
            late_stream_rows[0]["high_conf_max_terminal_data_gap_ms"], 1700.0
        )
        self.assertEqual(
            late_stream_rows[0]["high_conf_max_terminal_idle_after_last_data_ms"],
            0.0,
        )
        self.assertEqual(
            late_stream_rows[0]["high_conf_max_terminal_pending_after_bytes"], 0.0
        )
        self.assertEqual(late_stream_rows[0]["high_conf_terminal_sendmes"], 1.0)
        self.assertEqual(
            late_stream_rows[0]["high_conf_min_terminal_recv_window_after_take"],
            450.0,
        )
        self.assertEqual(
            late_stream_rows[0]["high_conf_max_terminal_queued_after_bytes"],
            498.0,
        )

        late_circuit_rows = resource_queue_late_circuit_summary_rows(payload)

        self.assertEqual(len(late_circuit_rows), 1)
        self.assertEqual(late_circuit_rows[0]["circuit"], "Circ 0.4 (Tunnel 15)")
        self.assertEqual(late_circuit_rows[0]["late_resources"], 1)
        self.assertEqual(
            late_circuit_rows[0]["max_terminal_last_data_after_queue_ms"], 800.0
        )
        self.assertEqual(
            late_circuit_rows[0]["max_late_terminal_data_gap_ms"], 1700.0
        )
        self.assertEqual(
            late_circuit_rows[0]["top_late_resource"], "example.com/queued.css"
        )
        self.assertEqual(late_circuit_rows[0]["late_timing_ids"], "7")
        self.assertEqual(late_circuit_rows[0]["terminal_streams"], 1)
        self.assertEqual(late_circuit_rows[0]["terminal_timing_ids"], "7")
        self.assertEqual(late_circuit_rows[0]["terminal_stream_ids"], "11302")
        self.assertAlmostEqual(late_circuit_rows[0]["terminal_relay_kib"], 3400 / 1024)
        self.assertEqual(late_circuit_rows[0]["max_terminal_transfer_ms"], 1700.0)
        self.assertEqual(late_circuit_rows[0]["max_terminal_data_gap_ms"], 1700.0)
        self.assertEqual(
            late_circuit_rows[0]["max_terminal_idle_after_last_data_ms"], 0.0
        )
        self.assertEqual(late_circuit_rows[0]["terminal_data_cells"], 7.0)

        scheduler_rows = torfast_stream_scheduler_late_circuit_fairness_rows(payload)

        self.assertEqual(len(scheduler_rows), 1)
        self.assertEqual(scheduler_rows[0]["scheduler_picks"], 4)
        self.assertEqual(scheduler_rows[0]["data_picks"], 4)
        self.assertEqual(scheduler_rows[0]["picked_streams"], 2)
        self.assertEqual(scheduler_rows[0]["top_picked_stream_id"], 11302)
        self.assertEqual(scheduler_rows[0]["top_picked_stream_picks"], 3)
        self.assertEqual(scheduler_rows[0]["top_picked_stream_share_pct"], 75.0)
        self.assertEqual(
            scheduler_rows[0]["max_consecutive_same_stream_picks"], 2
        )
        self.assertEqual(
            scheduler_rows[0]["top_picked_streams"], "11302:3, 11303:1"
        )
        self.assertEqual(
            scheduler_rows[0]["proof_hint"], "no scheduler monopoly seen"
        )
        self.assertEqual(
            rows[0]["high_conf_median_blocker_response_end_after_last_write_ms"],
            0.0,
        )
        self.assertEqual(
            rows[0]["high_conf_min_first_relay_after_queued_request_ms"],
            800.0,
        )
        self.assertEqual(
            rows[0]["high_conf_max_last_relay_after_queued_request_ms"],
            800.0,
        )
        self.assertEqual(rows[0]["high_conf_relay_data_after_queued_request_bytes"], 300)
        self.assertIsNone(rows[0]["high_conf_max_relay_gap_after_queued_request_ms"])
        self.assertEqual(
            rows[0][
                "high_conf_max_blocker_last_write_after_last_relay_receive_ms"
            ],
            0.0,
        )
        self.assertEqual(
            rows[0][
                "high_conf_max_blocker_last_write_after_last_stream_receiver_read_ms"
            ],
            0.0,
        )
        self.assertEqual(rows[0]["high_conf_max_stream_receiver_queued_after_bytes"], 0)
        self.assertEqual(rows[0]["high_conf_min_stream_receiver_recv_window_after"], 499)
        self.assertEqual(rows[0]["high_conf_terminal_coverage"], 1)
        self.assertEqual(
            rows[0]["high_conf_max_terminal_last_data_after_queued_request_ms"],
            800.0,
        )
        self.assertEqual(
            rows[0]["high_conf_median_last_write_after_terminal_last_data_ms"],
            0.0,
        )
        self.assertEqual(
            rows[0]["high_conf_max_last_write_after_terminal_last_data_ms"], 0.0
        )
        self.assertEqual(rows[0]["high_conf_max_terminal_data_gap_ms"], 1700.0)
        self.assertEqual(rows[0]["high_conf_max_terminal_idle_after_last_data_ms"], 0.0)
        self.assertEqual(rows[0]["high_conf_max_terminal_pending_after_bytes"], 0.0)
        self.assertEqual(rows[0]["blocker_high_confidence"], 1)
        self.assertEqual(rows[0]["blocker_timing_ids"], "7")
        self.assertEqual(rows[0]["blocker_circuits"], "Circ 0.4 (Tunnel 15)")
        self.assertEqual(rows[0]["blocker_max_relay_ms"], 1900)
        self.assertEqual(rows[0]["blocker_max_last_tor_to_client_ms"], 1895)
        self.assertEqual(rows[0]["blocker_max_idle_after_last_ms"], 27)
        self.assertIn("open-a.css", rows[0]["top_blockers"])
        self.assertIn("800.000ms recv", rows[0]["top_blockers"])
        self.assertIn("800.000ms write-after-queue", rows[0]["top_blockers"])
        self.assertIn("0.000ms resp-after-write", rows[0]["top_blockers"])
        self.assertIn("0.000ms write-after-relay", rows[0]["top_blockers"])

    def test_load_tail_rows_show_max_tail(self) -> None:
        payload = {
            "targets": ["https://example.com/"],
            "profiles": {
                "arti_release_browser": {
                    "benchmarks": {
                        "https://example.com/": {
                            "summary": {"median_load_ms": 1000.0},
                            "runs": [
                                {"ok": True, "load_ms": 900, "elapsed_ms": 1200},
                                {"ok": True, "load_ms": 1000, "elapsed_ms": 1300},
                                {"ok": True, "load_ms": 9000, "elapsed_ms": 9500},
                            ],
                        }
                    }
                }
            },
        }

        rows = load_tail_rows(payload)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["runs"], 3)
        self.assertEqual(rows[0]["ok_runs"], 3)
        self.assertEqual(rows[0]["median_load_ms"], 1000.0)
        self.assertEqual(rows[0]["max_load_ms"], 9000.0)
        self.assertEqual(rows[0]["max_to_median_load"], 9.0)
        self.assertEqual(rows[0]["max_load_run"], 3)
        self.assertEqual(rows[0]["max_elapsed_ms"], 9500.0)

    def test_boot_directory_failure_rows_show_boot_log_shape(self) -> None:
        payload = {
            "targets": ["https://example.com/"],
            "browser_default_prefs": {"ok": True, "prefs": REQUIRED_DEFAULT_PREFS},
            "profiles": {
                "arti_release_browser": {
                    "boot": {
                        "ok": True,
                        "seconds": 30.436,
                        "lines": [
                            "2026-06-08T14:22:54Z  INFO tor_dirmgr::bootstrap: 1: Looking for a consensus. attempt=1",
                            "2026-06-08T14:23:03Z  WARN tor_dirclient: directory timed out",
                            "2026-06-08T14:23:04Z  INFO tor_proto: NOTDIRECTORY END cell",
                            "2026-06-08T14:23:04Z  INFO tor_dirclient: Circ 2.0: Retiring circuit because of directory failure: Partial response",
                            '2026-06-08T14:23:05Z  INFO tor_dirclient: torfast dirclient timing request_kind="consensus" anonymized=Direct outcome="error" status=None body_bytes=0 elapsed_ms=10003 read_timeout_ms=10000 body_read_calls=0 body_first_byte_ms=0 body_last_byte_ms=0 body_max_read_gap_ms=0 body_timeout_after_last_byte_ms=10003 body_eof=false error_kind=Some(TorNetworkTimeout)',
                            '2026-06-08T14:23:05Z  INFO tor_circmgr::build: torfast channel open timing elapsed_ms=10005 usage_kind="dir" provenance="newly_created" outcome="err" error_kind=TorAccessFailed',
                            "2026-06-08T14:23:05Z  INFO tor_circmgr::mgr: torfast circuit selection build failed pending_id=0x96501cb10 pending_age_ms=10005 usage_kind=dir err=Problem opening a channel to [scrubbed]",
                            "2026-06-08T14:23:12Z  INFO torfast stream receiver terminal summary stream_id=7 transfer_ms=7726 max_data_gap_ms=385 relay_data_bytes=746286 max_queued_after_bytes=35756",
                            "2026-06-08T14:23:13Z  INFO tor_dirmgr::bootstrap: 1: Downloading microdescriptors (we are missing 9773). attempt=1",
                            "2026-06-08T14:23:38Z  INFO tor_dirmgr: Marked consensus usable.",
                            "2026-06-08T14:23:38Z  INFO arti::subcommands::proxy: Sufficiently bootstrapped; proxy now functional.",
                        ],
                    },
                    "benchmarks": {
                        "https://example.com/": {
                            "summary": {"ok": True, "successes": 1},
                            "runs": [
                                {
                                    "ok": True,
                                    "expected_socks_port": 19050,
                                    "effective_proxy_prefs": {
                                        "network.proxy.socks": "127.0.0.1",
                                        "network.proxy.socks_port": 19050,
                                        "network.proxy.socks_remote_dns": True,
                                        "network.proxy.type": 1,
                                    },
                                    "screenshot": {
                                        "exists": True,
                                        "bytes": 100,
                                        "width": 800,
                                        "height": 600,
                                    },
                                }
                            ],
                        }
                    },
                }
            },
        }

        rows = boot_directory_failure_rows(payload)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["profile"], "arti_release_browser")
        self.assertEqual(rows[0]["boot_seconds"], 30.436)
        self.assertTrue(rows[0]["boot_ok"])
        self.assertEqual(rows[0]["boot_lines"], 11)
        self.assertEqual(rows[0]["directory_failures"], 1)
        self.assertEqual(rows[0]["directory_timeouts"], 1)
        self.assertEqual(rows[0]["notdirectory"], 1)
        self.assertEqual(rows[0]["partial_response"], 1)
        self.assertEqual(rows[0]["terminal_summaries"], 1)
        self.assertEqual(rows[0]["warnings"], 1)
        self.assertIn("Partial response", rows[0]["last_boot_signal"])

        timeline_rows = boot_directory_timeline_rows(payload)
        self.assertEqual(len(timeline_rows), 1)
        self.assertEqual(timeline_rows[0]["consensus_attempts"], 1)
        self.assertEqual(timeline_rows[0]["first_directory_timeout_seconds"], 9.0)
        self.assertEqual(timeline_rows[0]["first_circuit_build_failure_seconds"], 11.0)
        self.assertEqual(timeline_rows[0]["circuit_build_failures"], 1)
        self.assertEqual(timeline_rows[0]["circuit_build_channel_failures"], 1)
        self.assertEqual(timeline_rows[0]["circuit_build_dir_failures"], 1)
        self.assertEqual(timeline_rows[0]["max_circuit_build_pending_age_ms"], 10005)
        self.assertEqual(timeline_rows[0]["channel_open_timing_rows"], 1)
        self.assertEqual(timeline_rows[0]["channel_open_timing_errors"], 1)
        self.assertEqual(timeline_rows[0]["channel_open_dir_rows"], 1)
        self.assertEqual(timeline_rows[0]["channel_open_max_elapsed_ms"], 10005)
        self.assertEqual(timeline_rows[0]["first_microdescriptors_seconds"], 19.0)
        self.assertEqual(timeline_rows[0]["consensus_usable_seconds"], 44.0)
        self.assertEqual(timeline_rows[0]["dirclient_timing_rows"], 1)
        self.assertEqual(timeline_rows[0]["dirclient_timing_error_rows"], 1)
        self.assertEqual(timeline_rows[0]["dirclient_timing_max_elapsed_ms"], 10003)
        self.assertEqual(
            timeline_rows[0]["dirclient_timing_max_body_timeout_after_last_byte_ms"],
            10003,
        )
        self.assertEqual(
            timeline_rows[0]["dirclient_timing_max_elapsed_kind"], "consensus"
        )
        self.assertEqual(timeline_rows[0]["terminal_summary_max_transfer_ms"], 7726)
        self.assertEqual(timeline_rows[0]["terminal_summary_relay_mib"], 0.712)

        with tempfile.TemporaryDirectory() as tmp:
            result_path = Path(tmp) / "browser-compare.json"
            result_path.write_text(json.dumps(payload), encoding="utf-8")
            stdout = io.StringIO()
            with patch("sys.argv", ["analyze_browser_compare.py", str(result_path)]):
                with patch("sys.stdout", stdout):
                    exit_code = analyze_browser_compare_main()

        self.assertEqual(exit_code, 0)
        output = stdout.getvalue()
        self.assertIn("## Boot Directory Timeline", output)
        self.assertIn("## Boot Directory Failure Summary", output)
        self.assertIn("build fails", output)
        self.assertIn("channel fails", output)
        self.assertIn("dir build fails", output)
        self.assertIn("channel open rows", output)
        self.assertIn("max channel open ms", output)
        self.assertIn("max body timeout gap ms", output)
        self.assertIn("partial response", output.lower())

    def test_boot_directory_rows_prefer_filtered_boot_signal_lines(self) -> None:
        signal_lines = [
            "2026-06-08T14:22:54Z  INFO tor_dirmgr::bootstrap: 1: Looking for a consensus. attempt=1",
            "2026-06-08T14:23:03Z  WARN tor_dirclient: directory timed out",
            "2026-06-08T14:23:13Z  INFO tor_dirmgr::bootstrap: 1: Downloading microdescriptors (we are missing 9773). attempt=1",
            "2026-06-08T14:23:38Z  INFO tor_dirmgr: Marked consensus usable.",
            "2026-06-08T14:23:38Z  INFO arti::subcommands::proxy: Sufficiently bootstrapped; proxy now functional.",
        ]
        payload = {
            "profiles": {
                "arti_release_browser": {
                    "boot": {
                        "ok": True,
                        "seconds": 44.0,
                        "lines": [
                            "2026-06-08T14:23:38Z  INFO tor_proto::circuit::circhop: torfast stream lifecycle delivery=\"delivered\"",
                        ],
                        "signal_lines": signal_lines,
                    },
                    "benchmarks": {},
                }
            }
        }

        failure_rows = boot_directory_failure_rows(payload)
        timeline_rows = boot_directory_timeline_rows(payload)

        self.assertEqual(len(failure_rows), 1)
        self.assertEqual(failure_rows[0]["boot_lines"], len(signal_lines))
        self.assertEqual(failure_rows[0]["directory_timeouts"], 1)
        self.assertEqual(len(timeline_rows), 1)
        self.assertEqual(timeline_rows[0]["first_directory_timeout_seconds"], 9.0)
        self.assertEqual(timeline_rows[0]["first_microdescriptors_seconds"], 19.0)
        self.assertEqual(timeline_rows[0]["consensus_usable_seconds"], 44.0)

    def test_promotion_blocker_summary_rows_collects_current_blockers(self) -> None:
        active_resources = [
            {
                "name": f"https://example.test/static/{index}.png",
                "nextHopProtocol": "http/1.1",
                "fetchStart": 0,
                "requestStart": 0,
                "responseStart": 100,
                "responseEnd": 10000,
            }
            for index in range(7)
        ]
        queued_resource = {
            "name": "https://example.test/static/queued.png",
            "nextHopProtocol": "http/1.1",
            "fetchStart": 0,
            "requestStart": 2000,
            "responseStart": 2100,
            "responseEnd": 2200,
        }
        payload = {
            "targets": ["https://example.test/"],
            "profiles": {
                "arti_release_browser": {
                    "boot": {
                        "ok": True,
                        "seconds": 44.0,
                        "lines": [
                            "WARN directory timed out",
                            "INFO Partial response from directory failure",
                        ],
                    },
                    "benchmarks": {
                        "https://example.test/": {
                            "summary": {"ok": True},
                            "runs": [
                                {
                                    "run_index": 1,
                                    "ok": True,
                                    "elapsed_ms": 5200,
                                    "load_ms": 5000,
                                    "performance_timing": {
                                        "navigation": {
                                            "responseStart": 100,
                                            "domContentLoadedEventEnd": 1000,
                                            "loadEventEnd": 5000,
                                        },
                                        "resources": active_resources + [queued_resource],
                                    },
                                    "proxy_signal_lines": [
                                        'timing_id=1 target_kind="onion" command=CONNECT port=443 elapsed_ms=0 torfast socks timing request parsed',
                                        'timing_id=1 target_kind="onion" port=443 connect_ms=2200 elapsed_ms=2200 torfast socks timing stream ready',
                                        'timing_id=2 target_kind="hostname" command=CONNECT port=443 elapsed_ms=0 torfast socks timing request parsed',
                                        'timing_id=2 target_kind="hostname" port=443 relay_ms=8000 elapsed_ms=8001 first_tor_to_client_ms=100 last_tor_to_client_ms=7000 client_to_tor_eof_ms=8000 tor_to_client_error_ms=8001 tor_to_client_bytes=4096 copy_error_kind=not_connected ok=false torfast socks timing relay finished',
                                        'timing_id=3 target_kind="hostname" command=CONNECT port=443 elapsed_ms=0 torfast socks timing request parsed',
                                        'timing_id=3 target_kind="hostname" port=443 relay_ms=7000 elapsed_ms=7000 first_tor_to_client_ms=100 last_tor_to_client_ms=1200 tor_to_client_bytes=4096 ok=false torfast socks timing relay finished',
                                    ],
                                }
                            ],
                        }
                    },
                },
                "local_c_tor_browser": {
                    "boot": {"ok": True, "seconds": 15.0, "lines": []},
                    "benchmarks": {
                        "https://example.test/": {
                            "summary": {"ok": True},
                            "runs": [
                                {
                                    "run_index": 1,
                                    "ok": True,
                                    "elapsed_ms": 1200,
                                    "load_ms": 1000,
                                    "performance_timing": {
                                        "navigation": {
                                            "responseStart": 50,
                                            "domContentLoadedEventEnd": 500,
                                            "loadEventEnd": 1000,
                                        }
                                    },
                                }
                            ],
                        }
                    },
                },
            },
        }

        rows = promotion_blocker_summary_rows(payload)

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["profile"], "arti_release_browser")
        self.assertIn("boot slower", row["blockers"])
        self.assertIn("boot directory", row["blockers"])
        self.assertIn("slower than C Tor", row["blockers"])
        self.assertIn("resource queue", row["blockers"])
        self.assertIn("slow onion/data gap", row["blockers"])
        self.assertIn("slow hostname stream", row["blockers"])
        self.assertEqual(row["slow_targets"], 1)
        self.assertEqual(row["worst_load_delta_ms"], 4000.0)
        self.assertEqual(row["boot_seconds"], 44.0)
        self.assertEqual(row["boot_delta_ms"], 29000.0)
        self.assertEqual(row["directory_failure_signals"], 3)
        self.assertEqual(row["queued_runs"], 1)
        self.assertEqual(row["queue_regression_targets"], 1)
        self.assertEqual(row["max_fetch_to_request_ms"], 2000)
        self.assertIsNone(row["max_queue_delta_ms"])
        self.assertEqual(row["slow_onion_streams"], 1)
        self.assertEqual(row["slow_hostname_streams"], 2)
        self.assertEqual(row["slow_same_close_not_connected_streams"], 1)
        self.assertEqual(row["slow_client_reset_close_streams"], 0)
        self.assertEqual(row["slow_unresolved_streams"], 2)
        self.assertEqual(row["slow_unresolved_onion_streams"], 1)
        self.assertEqual(row["slow_unresolved_hostname_streams"], 1)
        self.assertEqual(row["max_slow_last_tor_byte_to_client_eof_ms"], 1000)
        self.assertEqual(row["max_relay_ms"], 8000)
        self.assertEqual(row["next_proof"], "stream gap proof")
        unresolved = promotion_unresolved_slow_stream_rows(payload)
        self.assertEqual([row["timing_id"] for row in unresolved], [3, 1])
        self.assertNotIn(2, [row["timing_id"] for row in unresolved])

    def test_promotion_blocker_summary_rows_counts_warmup_boot_failures(self) -> None:
        payload = {
            "targets": ["https://example.test/"],
            "profiles": {
                "arti_release_browser": {
                    "warmup_boot": {
                        "ok": True,
                        "lines": [
                            "WARN directory timed out",
                            "INFO Partial response from directory failure",
                        ],
                    },
                    "boot": {"ok": True, "seconds": 5.0, "lines": []},
                    "benchmarks": {
                        "https://example.test/": {
                            "summary": {"ok": True},
                            "runs": [
                                {
                                    "run_index": 1,
                                    "ok": True,
                                    "elapsed_ms": 5200,
                                    "load_ms": 5000,
                                    "performance_timing": {
                                        "navigation": {
                                            "responseStart": 100,
                                            "domContentLoadedEventEnd": 1000,
                                            "loadEventEnd": 5000,
                                        }
                                    },
                                }
                            ],
                        }
                    },
                },
                "local_c_tor_browser": {
                    "boot": {"ok": True, "seconds": 3.0, "lines": []},
                    "benchmarks": {
                        "https://example.test/": {
                            "summary": {"ok": True},
                            "runs": [
                                {
                                    "run_index": 1,
                                    "ok": True,
                                    "elapsed_ms": 1200,
                                    "load_ms": 1000,
                                    "performance_timing": {
                                        "navigation": {
                                            "responseStart": 50,
                                            "domContentLoadedEventEnd": 500,
                                            "loadEventEnd": 1000,
                                        }
                                    },
                                }
                            ],
                        }
                    },
                },
            },
        }

        rows = promotion_blocker_summary_rows(payload)

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["profile"], "arti_release_browser")
        self.assertIn("boot directory", row["blockers"])
        self.assertEqual(row["directory_failure_signals"], 3)

    def test_promotion_slow_target_proof_rows_join_browser_and_socks(self) -> None:
        base = 1_000_000
        payload = {
            "targets": ["https://example.test/"],
            "profiles": {
                "arti_release_browser": {
                    "benchmarks": {
                        "https://example.test/": {
                            "summary": {"ok": True},
                            "runs": [
                                {
                                    "run_index": 1,
                                    "ok": True,
                                    "load_ms": 5000,
                                    "started_epoch_ms": base,
                                    "performance_timing": {
                                        "time_origin_ms": base,
                                        "navigation": {
                                            "connectStart": 10,
                                            "requestStart": 200,
                                            "responseStart": 3200,
                                            "responseEnd": 3300,
                                            "domContentLoadedEventEnd": 3600,
                                            "loadEventEnd": 5000,
                                        },
                                        "resources": [
                                            {
                                                "name": "https://example.test/pixel.png",
                                                "initiatorType": "img",
                                                "duration": 700,
                                            }
                                        ],
                                    },
                                    "proxy_signal_lines": [
                                        f"timing_id=7 target_kind=hostname port=443 conn_started_epoch_ms={base + 10} elapsed_ms=0 torfast socks timing request parsed",
                                        f"timing_id=7 target_kind=hostname port=443 conn_started_epoch_ms={base + 10} circ_id=Circ 0.1 (Tunnel 2) stream_id=13 relay_ms=5200 first_tor_to_client_ms=250 first_tor_to_client_epoch_ms={base + 250} last_tor_to_client_ms=5100 tor_to_client_bytes=4096 elapsed_ms=5220 ok=false copy_error_kind=not_connected torfast socks timing relay finished",
                                        f"event_epoch_ms={base + 20} circ_id=Circ 0.1 (Tunnel 2) hop=3 stream_id=13 relay_cmd=RelayCmd(BEGIN) delivery=\"channel_queued\" torfast stream lifecycle",
                                        f"event_epoch_ms={base + 120} circ_id=Circ 0.1 (Tunnel 2) hop=3 stream_id=13 relay_cmd=RelayCmd(CONNECTED) delivery=\"delivered\" torfast stream lifecycle",
                                        f"event_epoch_ms={base + 250} circ_id=Circ 0.1 (Tunnel 2) hop=3 stream_id=13 relay_cmd=RelayCmd(DATA) delivery=\"delivered\" torfast stream lifecycle",
                                        f"event_epoch_ms={base + 5220} circ_id=Circ 0.1 (Tunnel 2) stream_id=13 connected=true first_data_after_start_ms=250 transfer_ms=5100 idle_after_last_data_ms=120 max_data_gap_ms=1800 relay_data_bytes=4096 pending_after_bytes=0 user_read_bytes=4096 data_cells=9 error_kind=not_connected returned_eof=false torfast stream receiver terminal summary",
                                    ],
                                }
                            ],
                        }
                    },
                },
                "local_c_tor_browser": {
                    "benchmarks": {
                        "https://example.test/": {
                            "summary": {"ok": True},
                            "runs": [
                                {
                                    "run_index": 1,
                                    "ok": True,
                                    "load_ms": 1000,
                                    "performance_timing": {
                                        "time_origin_ms": base + 20_000,
                                        "navigation": {
                                            "responseStart": 100,
                                            "domContentLoadedEventEnd": 300,
                                            "loadEventEnd": 1000,
                                        },
                                    },
                                }
                            ],
                        }
                    },
                },
            },
        }

        rows = promotion_slow_target_proof_rows(payload)

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["profile"], "arti_release_browser")
        self.assertEqual(row["target"], "https://example.test/")
        self.assertEqual(row["candidate_run"], 1)
        self.assertEqual(row["candidate_load_ms"], 5000)
        self.assertEqual(row["baseline_max_load_ms"], 1000)
        self.assertEqual(row["median_load_delta_ms"], 4000.0)
        self.assertEqual(row["nav_wait_ms"], 3000)
        self.assertEqual(row["nav_receive_ms"], 100)
        self.assertEqual(row["resource_count"], 1)
        self.assertEqual(row["nav_timing_id"], 7)
        self.assertEqual(row["nav_first_tor_byte_to_response_ms"], 2950)
        self.assertEqual(row["nav_relay_ms"], 5200)
        self.assertEqual(row["worst_timing_id"], 7)
        self.assertEqual(row["worst_lifecycle_state"], "DATA delivered, no EOF")
        self.assertEqual(row["worst_relay_ms"], 5200)
        self.assertEqual(row["worst_transfer_ms"], 5100)
        self.assertEqual(row["worst_data_gap_ms"], 1800)
        self.assertEqual(row["worst_idle_after_last_data_ms"], 120)
        self.assertEqual(row["worst_relay_kib"], 4.0)

    def test_promotion_blocker_summary_rows_treats_same_close_as_resolved(self) -> None:
        payload = {
            "targets": ["https://example.test/"],
            "profiles": {
                "arti_release_browser": {
                    "boot": {"ok": True, "seconds": 10.0, "lines": []},
                    "benchmarks": {
                        "https://example.test/": {
                            "summary": {"ok": True},
                            "runs": [
                                {
                                    "run_index": 1,
                                    "ok": True,
                                    "load_ms": 900,
                                    "performance_timing": {
                                        "navigation": {
                                            "responseStart": 100,
                                            "domContentLoadedEventEnd": 300,
                                            "loadEventEnd": 900,
                                        },
                                        "resources": [],
                                    },
                                    "proxy_signal_lines": [
                                        'timing_id=7 target_kind="hostname" port=443 relay_ms=6500 elapsed_ms=6501 first_tor_to_client_ms=100 last_tor_to_client_ms=5500 client_to_tor_eof_ms=6500 tor_to_client_error_ms=6501 tor_to_client_bytes=4096 copy_error_kind=not_connected ok=false torfast socks timing relay finished',
                                        'timing_id=8 target_kind="onion" port=443 conn_started_epoch_ms=1000 relay_ms=6500 elapsed_ms=6501 first_tor_to_client_ms=1800 last_tor_to_client_ms=6480 client_to_tor_error_ms=6500 tor_to_client_bytes=4096 copy_error_kind=connection_reset circ_id=Circ 0.4 (Tunnel 15) stream_id=11303 ok=false torfast socks timing relay finished',
                                        'event_epoch_ms=7500 circ_id=Circ 0.4 (Tunnel 15) hop=HopNum(3) stream_id=11303 relay_cmd=RelayCmd(END) delivery="channel_queued" torfast stream lifecycle',
                                        'timing_id=9 target_kind="hostname" port=443 conn_started_epoch_ms=2000 relay_ms=6500 elapsed_ms=6501 first_tor_to_client_ms=1800 last_tor_to_client_ms=6500 tor_to_client_eof_ms=6500 client_to_tor_eof_ms=6501 tor_to_client_bytes=4096 copy_error_kind=connection_reset circ_id=Circ 0.5 (Tunnel 16) stream_id=11304 ok=false torfast socks timing relay finished',
                                        'event_epoch_ms=8500 circ_id=Circ 0.5 (Tunnel 16) hop=Some(HopNum(3)) stream_id=11304 relay_cmd=RelayCmd(END) delivery="delivered" torfast stream lifecycle',
                                    ],
                                }
                            ],
                        }
                    },
                },
                "local_c_tor_browser": {
                    "boot": {"ok": True, "seconds": 12.0, "lines": []},
                    "benchmarks": {
                        "https://example.test/": {
                            "summary": {"ok": True},
                            "runs": [
                                {
                                    "run_index": 1,
                                    "ok": True,
                                    "load_ms": 1000,
                                    "performance_timing": {
                                        "navigation": {
                                            "responseStart": 100,
                                            "domContentLoadedEventEnd": 300,
                                            "loadEventEnd": 1000,
                                        },
                                        "resources": [],
                                    },
                                }
                            ],
                        }
                    },
                },
            },
        }

        rows = promotion_blocker_summary_rows(payload)

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["blockers"], "none seen")
        self.assertEqual(row["slow_hostname_streams"], 2)
        self.assertEqual(row["slow_same_close_not_connected_streams"], 1)
        self.assertEqual(row["slow_client_reset_close_streams"], 1)
        self.assertEqual(row["slow_remote_end_close_streams"], 1)
        self.assertEqual(row["slow_unresolved_streams"], 0)
        self.assertEqual(row["queue_regression_targets"], 0)
        self.assertEqual(row["next_proof"], "broader A/B")
        self.assertEqual(promotion_unresolved_slow_stream_rows(payload), [])

    def test_promotion_blocker_summary_rows_treats_stream_target_closed_as_resolved(
        self,
    ) -> None:
        base = 1_000_000
        payload = {
            "targets": ["https://example.test/"],
            "profiles": {
                "arti_release_browser": {
                    "boot": {"ok": True, "seconds": 10.0, "lines": []},
                    "benchmarks": {
                        "https://example.test/": {
                            "summary": {"ok": True},
                            "runs": [
                                {
                                    "run_index": 1,
                                    "ok": True,
                                    "load_ms": 900,
                                    "performance_timing": {
                                        "navigation": {
                                            "responseStart": 100,
                                            "domContentLoadedEventEnd": 300,
                                            "loadEventEnd": 900,
                                        },
                                        "resources": [],
                                    },
                                    "proxy_signal_lines": [
                                        f'timing_id=7 target_kind="hostname" port=443 conn_started_epoch_ms={base} relay_ms=6500 elapsed_ms=6501 first_tor_to_client_ms=100 last_tor_to_client_ms=5500 tor_to_client_bytes=4096 copy_error_kind=not_connected circ_id=Circ 0.6 (Tunnel 17) stream_id=11305 ok=false torfast socks timing relay finished',
                                        f"event_epoch_ms={base + 6501} circ_id=Circ 0.6 (Tunnel 17) stream_id=11305 connected=true first_data_after_start_ms=100 transfer_ms=5400 idle_after_last_data_ms=1001 max_data_gap_ms=600 relay_data_bytes=4096 pending_after_bytes=0 user_read_bytes=4096 data_cells=9 read_events=9 sendmes=0 sendme_ok=0 min_recv_window_after_take=450 max_queued_after_bytes=4096 error_kind=not_connected not_connected_source=receiver_err stream_close_cause=stream_target_closed returned_eof=false torfast stream receiver terminal summary",
                                    ],
                                }
                            ],
                        }
                    },
                },
                "local_c_tor_browser": {
                    "boot": {"ok": True, "seconds": 12.0, "lines": []},
                    "benchmarks": {
                        "https://example.test/": {
                            "summary": {"ok": True},
                            "runs": [
                                {
                                    "run_index": 1,
                                    "ok": True,
                                    "load_ms": 1000,
                                    "performance_timing": {
                                        "navigation": {
                                            "responseStart": 100,
                                            "domContentLoadedEventEnd": 300,
                                            "loadEventEnd": 1000,
                                        },
                                        "resources": [],
                                    },
                                }
                            ],
                        }
                    },
                },
            },
        }

        rows = promotion_blocker_summary_rows(payload)

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["blockers"], "none seen")
        self.assertEqual(row["slow_hostname_streams"], 1)
        self.assertEqual(row["slow_same_close_not_connected_streams"], 1)
        self.assertEqual(row["slow_unresolved_streams"], 0)
        self.assertEqual(promotion_unresolved_slow_stream_rows(payload), [])

    def test_promotion_resource_queue_regression_ignores_small_noise(self) -> None:
        def payload_with_candidate_fetch_to_request(values: list[float]) -> dict:
            def resource(index: int, fetch_to_request: float) -> dict:
                return {
                    "name": f"https://example.test/r{index}.png",
                    "initiatorType": "img",
                    "nextHopProtocol": "http/1.1",
                    "fetchStart": 0,
                    "requestStart": fetch_to_request,
                    "responseStart": fetch_to_request + 10,
                    "responseEnd": fetch_to_request + 20,
                    "duration": fetch_to_request + 20,
                }

            return {
                "targets": ["https://example.test/"],
                "profiles": {
                    "arti_release_browser": {
                        "benchmarks": {
                            "https://example.test/": {
                                "summary": {"ok": True},
                                "runs": [
                                    {
                                        "run_index": 1,
                                        "ok": True,
                                        "performance_timing": {
                                            "resources": [
                                                resource(index, value)
                                                for index, value in enumerate(values)
                                            ]
                                        },
                                    }
                                ],
                            }
                        }
                    },
                    "local_c_tor_browser": {
                        "benchmarks": {
                            "https://example.test/": {
                                "summary": {"ok": True},
                                "runs": [
                                    {
                                        "run_index": 1,
                                        "ok": True,
                                        "performance_timing": {
                                            "resources": [
                                                resource(1, 10),
                                                resource(2, 20),
                                            ]
                                        },
                                    }
                                ],
                            }
                        }
                    },
                },
            }

        noise_rows = promotion_resource_queue_regression_rows(
            payload_with_candidate_fetch_to_request([20, 30]),
            candidate_profile="arti_release_browser",
            baseline_profile="local_c_tor_browser",
        )
        real_rows = promotion_resource_queue_regression_rows(
            payload_with_candidate_fetch_to_request([20, 170]),
            candidate_profile="arti_release_browser",
            baseline_profile="local_c_tor_browser",
        )

        self.assertEqual(noise_rows, [])
        self.assertEqual(len(real_rows), 1)
        self.assertEqual(real_rows[0]["max_fetch_to_request_delta_ms"], 150.0)

    def test_promotion_blocker_summary_rows_block_failed_baseline(self) -> None:
        payload = {
            "targets": ["https://example.test/"],
            "profiles": {
                "arti_release_browser": {
                    "benchmarks": {
                        "https://example.test/": {
                            "summary": {"ok": True},
                            "runs": [
                                {
                                    "run_index": 1,
                                    "ok": True,
                                    "load_ms": 900,
                                    "elapsed_ms": 1100,
                                }
                            ],
                        }
                    }
                },
                "local_c_tor_browser": {
                    "benchmarks": {
                        "https://example.test/": {
                            "summary": {"ok": False},
                            "runs": [
                                {
                                    "run_index": 1,
                                    "ok": False,
                                    "load_ms": None,
                                    "elapsed_ms": 120000,
                                }
                            ],
                        }
                    }
                },
            },
        }

        rows = promotion_blocker_summary_rows(payload)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["baseline_failure_signals"], 2)
        self.assertIn("baseline failed", rows[0]["blockers"])
        self.assertEqual(rows[0]["next_proof"], "clean baseline proof")

    def test_boot_directory_failure_rows_skip_warning_only_boot(self) -> None:
        payload = {
            "profiles": {
                "local_c_tor_browser": {
                    "boot": {
                        "ok": True,
                        "seconds": 1.0,
                        "lines": ["Jun 08 21:30:14.404 [warn] Fixing permissions"],
                    },
                    "benchmarks": {},
                }
            }
        }

        self.assertEqual(boot_directory_failure_rows(payload), [])

    def test_paired_run_delta_rows_compares_same_run_index(self) -> None:
        payload = {
            "targets": ["https://example.com/"],
            "profiles": {
                "arti_release_browser": {
                    "boot": {"seconds": 0.5},
                    "benchmarks": {
                        "https://example.com/": {
                            "runs": [
                                {
                                    "run_index": 1,
                                    "ok": True,
                                    "load_ms": 900,
                                    "elapsed_ms": 1000,
                                    "performance_timing": {
                                        "navigation": {
                                            "responseStart": 100,
                                            "domContentLoadedEventEnd": 250,
                                            "loadEventEnd": 500,
                                        }
                                    },
                                },
                                {
                                    "run_index": 2,
                                    "ok": True,
                                    "load_ms": 1200,
                                    "elapsed_ms": 1300,
                                    "performance_timing": {
                                        "navigation": {
                                            "responseStart": 300,
                                            "domContentLoadedEventEnd": 450,
                                            "loadEventEnd": 800,
                                        }
                                    },
                                },
                            ]
                        }
                    },
                },
                "local_c_tor_browser": {
                    "boot": {"seconds": 2.0},
                    "benchmarks": {
                        "https://example.com/": {
                            "runs": [
                                {
                                    "run_index": 1,
                                    "ok": True,
                                    "load_ms": 1000,
                                    "elapsed_ms": 1100,
                                    "performance_timing": {
                                        "navigation": {
                                            "responseStart": 150,
                                            "domContentLoadedEventEnd": 250,
                                            "loadEventEnd": 650,
                                        }
                                    },
                                },
                                {
                                    "run_index": 2,
                                    "ok": True,
                                    "load_ms": 1100,
                                    "elapsed_ms": 1150,
                                    "performance_timing": {
                                        "navigation": {
                                            "responseStart": 200,
                                            "domContentLoadedEventEnd": 400,
                                            "loadEventEnd": 700,
                                        }
                                    },
                                },
                            ]
                        }
                    },
                },
            },
        }

        rows = paired_run_delta_rows(
            payload,
            candidate_profile="arti_release_browser",
            baseline_profile="local_c_tor_browser",
        )

        self.assertEqual(rows[0]["paired_runs"], 2)
        self.assertEqual(rows[0]["candidate_load_wins"], 1)
        self.assertEqual(rows[0]["median_load_delta_ms"], 0.0)
        self.assertEqual(rows[0]["median_response_start_delta_ms"], 25.0)
        self.assertEqual(rows[0]["median_response_to_dom_delta_ms"], 0.0)
        self.assertEqual(rows[0]["median_dom_to_load_delta_ms"], -50.0)
        self.assertEqual(rows[0]["median_boot_plus_load_delta_ms"], -1500.0)

    def test_paired_run_delta_rows_use_true_interleaved_boot_seconds(self) -> None:
        payload = {
            "targets": ["https://example.com/"],
            "profiles": {
                "arti_release_browser": {
                    "interleaved_launch": {"started_epoch_ms": 118000.0},
                    "boot": {
                        "seconds": 0.2,
                        "ready_epoch_ms": 120000.0,
                    },
                    "benchmarks": {
                        "https://example.com/": {
                            "runs": [
                                {"run_index": 1, "ok": True, "load_ms": 500.0}
                            ]
                        }
                    },
                },
                "local_c_tor_browser": {
                    "interleaved_launch": {"started_epoch_ms": 100000.0},
                    "boot": {
                        "seconds": 0.0,
                        "ready_epoch_ms": 110000.0,
                    },
                    "benchmarks": {
                        "https://example.com/": {
                            "runs": [
                                {"run_index": 1, "ok": True, "load_ms": 1000.0}
                            ]
                        }
                    },
                },
            },
        }

        rows = paired_run_delta_rows(
            payload,
            candidate_profile="arti_release_browser",
            baseline_profile="local_c_tor_browser",
        )

        self.assertEqual(rows[0]["median_load_delta_ms"], -500.0)
        self.assertEqual(rows[0]["median_boot_plus_load_delta_ms"], -8500.0)

    def test_arti_exit_select_ab_rows_compare_to_lowest_width(self) -> None:
        payload = {
            "targets": ["https://example.com/"],
            "profiles": {
                "arti_release_browser": {
                    "arti_exit_select_parallelism_override": 3,
                    "boot": {"seconds": 0.4},
                    "benchmarks": {
                        "https://example.com/": {
                            "runs": [
                                {
                                    "run_index": 1,
                                    "ok": True,
                                    "load_ms": 300,
                                    "elapsed_ms": 400,
                                },
                                {
                                    "run_index": 2,
                                    "ok": True,
                                    "load_ms": 350,
                                    "elapsed_ms": 450,
                                },
                            ]
                        }
                    },
                },
                "arti_release_browser_exit1": {
                    "arti_exit_select_parallelism_override": 1,
                    "boot": {"seconds": 0.5},
                    "benchmarks": {
                        "https://example.com/": {
                            "runs": [
                                {
                                    "run_index": 1,
                                    "ok": True,
                                    "load_ms": 700,
                                    "elapsed_ms": 800,
                                },
                                {
                                    "run_index": 2,
                                    "ok": True,
                                    "load_ms": 900,
                                    "elapsed_ms": 1000,
                                },
                            ]
                        }
                    },
                },
            },
        }

        rows = arti_exit_select_ab_rows(payload)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["candidate_profile"], "arti_release_browser")
        self.assertEqual(rows[0]["candidate_width"], 3)
        self.assertEqual(rows[0]["baseline_profile"], "arti_release_browser_exit1")
        self.assertEqual(rows[0]["baseline_width"], 1)
        self.assertEqual(rows[0]["candidate_load_wins"], 2)
        self.assertEqual(rows[0]["median_load_delta_ms"], -475.0)

    def test_arti_profile_names_include_extra_arti_profiles(self) -> None:
        payload = {
            "profiles": {
                "arti_release_browser": {},
                "arti_release_browser_exit1": {},
                "bundled_c_tor_browser": {},
                "local_c_tor_browser": {},
                "arti_skipped": {"skipped": True},
            }
        }

        self.assertEqual(
            arti_profile_names(payload),
            ["arti_release_browser", "arti_release_browser_exit1"],
        )

    def test_extra_arti_proxy_app_buffer_profile_name(self) -> None:
        self.assertEqual(
            extra_arti_proxy_app_buffer_profile_name(32768, 0),
            "arti_release_browser_appbuf32768",
        )
        self.assertEqual(
            extra_arti_proxy_app_buffer_profile_name(32768, 1),
            "arti_release_browser_appbuf32768_2",
        )

    def test_arti_profile_promotion_risk_rows_flag_slow_tail(self) -> None:
        payload = {
            "targets": ["https://example.test/"],
            "profiles": {
                "arti_release_browser": {
                    "boot": {"seconds": 1.0},
                    "benchmarks": {
                        "https://example.test/": {
                            "summary": {
                                "median_load_ms": 1000,
                                "median_elapsed_ms": 1200,
                            },
                            "runs": [
                                {
                                    "run_index": 1,
                                    "ok": True,
                                    "load_ms": 900,
                                    "elapsed_ms": 1100,
                                    "performance_timing": {
                                        "navigation": {
                                            "connectStart": 0,
                                            "connectEnd": 100,
                                            "responseStart": 200,
                                            "domContentLoadedEventEnd": 500,
                                            "loadEventEnd": 900,
                                        }
                                    },
                                },
                                {
                                    "run_index": 2,
                                    "ok": True,
                                    "load_ms": 1100,
                                    "elapsed_ms": 1300,
                                    "performance_timing": {
                                        "navigation": {
                                            "connectStart": 0,
                                            "connectEnd": 150,
                                            "responseStart": 250,
                                            "domContentLoadedEventEnd": 650,
                                            "loadEventEnd": 1100,
                                        }
                                    },
                                },
                            ],
                        }
                    },
                },
                "arti_release_browser_lab": {
                    "boot": {"seconds": 1.0},
                    "proxy_signal_lines": [
                        'timing_id=12 target_kind="hostname" command=CONNECT port=443 conn_started_epoch_ms=3005 elapsed_ms=0 torfast socks timing request parsed',
                        'timing_id=12 target_kind="hostname" port=443 conn_started_epoch_ms=3005 connect_ms=1800 elapsed_ms=1800 torfast socks timing stream ready',
                        'timing_id=12 target_kind="hostname" port=443 conn_started_epoch_ms=3005 circ_id=Circ 0.9 (Tunnel 21) hop=3 stream_id=77 elapsed_ms=1801 torfast socks timing stream linked',
                        'timing_id=12 target_kind="hostname" port=443 conn_started_epoch_ms=3005 elapsed_ms=1810 torfast socks timing socks reply sent',
                        'timing_id=12 target_kind="hostname" port=443 conn_started_epoch_ms=3005 relay_ms=2300 elapsed_ms=2600 first_tor_to_client_ms=1850 first_tor_to_client_epoch_ms=4855 tor_to_client_bytes=8192 ok=true torfast socks timing relay finished',
                    ],
                    "benchmarks": {
                        "https://example.test/": {
                            "summary": {
                                "median_load_ms": 1300,
                                "median_elapsed_ms": 1500,
                            },
                            "runs": [
                                {
                                    "run_index": 1,
                                    "ok": True,
                                    "load_ms": 800,
                                    "elapsed_ms": 1000,
                                    "performance_timing": {
                                        "time_origin_ms": 1000,
                                        "navigation": {
                                            "connectStart": 0,
                                            "connectEnd": 100,
                                            "responseStart": 200,
                                            "domContentLoadedEventEnd": 500,
                                            "loadEventEnd": 800,
                                        }
                                    },
                                },
                                {
                                    "run_index": 2,
                                    "ok": True,
                                    "load_ms": 2400,
                                    "elapsed_ms": 2600,
                                    "performance_timing": {
                                        "time_origin_ms": 3000,
                                        "navigation": {
                                            "connectStart": 0,
                                            "connectEnd": 1800,
                                            "responseStart": 1900,
                                            "domContentLoadedEventEnd": 2200,
                                            "loadEventEnd": 2400,
                                        },
                                        "resources": [
                                            {
                                                "name": "https://example.test/slow.png",
                                                "duration": 700,
                                            }
                                        ],
                                    },
                                    "proxy_relay_context_lines": [
                                        'timing_id=12 target_kind="hostname" port=443 circ_id=Circ 0.9 (Tunnel 21) hop=3 stream_id=77 elapsed_ms=1801 torfast socks timing stream linked',
                                        'timing_id=12 target_kind="hostname" port=443 relay_ms=2300 elapsed_ms=2600 ok=false copy_error_kind=not_connected torfast socks timing relay finished',
                                        "event_epoch_ms=5600 circ_id=Circ 0.9 (Tunnel 21) hop=3 stream_id=77 connected=true first_data_after_start_ms=120 transfer_ms=2300 idle_after_last_data_ms=1800 max_data_gap_ms=900 relay_data_bytes=4096 pending_after_bytes=0 user_read_bytes=4096 data_cells=9 error_kind=not_connected end_reason= returned_eof=false torfast stream receiver terminal summary",
                                    ],
                                },
                            ],
                        }
                    },
                },
            },
        }

        rows = arti_profile_promotion_risk_rows(payload)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["candidate_profile"], "arti_release_browser_lab")
        self.assertIn("paired median slower", rows[0]["risk"])
        self.assertIn("summary median slower", rows[0]["risk"])
        self.assertIn("max tail worse", rows[0]["risk"])
        self.assertEqual(rows[0]["paired_load_wins"], "1/2")
        detail_rows = arti_profile_promotion_risk_detail_rows(payload)
        self.assertEqual(len(detail_rows), 1)
        self.assertEqual(detail_rows[0]["candidate_max_run"], 2)
        self.assertEqual(detail_rows[0]["candidate_max_load_ms"], 2400)
        self.assertIn("nav connect/TLS", detail_rows[0]["phase_hint"])
        self.assertEqual(detail_rows[0]["slowest_resource"], "example.test/slow.png")
        context_rows = arti_profile_promotion_risk_socks_context_rows(payload)
        self.assertEqual(len(context_rows), 1)
        self.assertEqual(context_rows[0]["timing_id"], 12)
        self.assertEqual(context_rows[0]["match_confidence"], "high")
        self.assertEqual(context_rows[0]["connect_ms"], 1800)
        self.assertEqual(context_rows[0]["reply_elapsed_ms"], 1810)
        self.assertEqual(context_rows[0]["first_tor_to_client_ms"], 1850)
        self.assertEqual(context_rows[0]["response_after_reply_ms"], 85.0)
        self.assertEqual(context_rows[0]["circ_id"], "Circ 0.9 (Tunnel 21)")
        self.assertEqual(context_rows[0]["stream_id"], 77)
        self.assertEqual(context_rows[0]["relay_ms"], 2300)
        receiver_rows = arti_profile_promotion_risk_stream_receiver_rows(payload)
        self.assertEqual(len(receiver_rows), 1)
        self.assertEqual(receiver_rows[0]["timing_id"], 12)
        self.assertEqual(receiver_rows[0]["circ_id"], "Circ 0.9 (Tunnel 21)")
        self.assertEqual(receiver_rows[0]["stream_id"], 77)
        self.assertEqual(receiver_rows[0]["socks_relay_ms"], 2300)
        self.assertEqual(receiver_rows[0]["copy_error_kind"], "not_connected")
        self.assertFalse(receiver_rows[0]["returned_eof"])
        self.assertEqual(receiver_rows[0]["transfer_ms"], 2300)
        self.assertEqual(receiver_rows[0]["max_data_gap_ms"], 900)
        self.assertEqual(receiver_rows[0]["idle_after_last_data_ms"], 1800)
        self.assertEqual(receiver_rows[0]["first_data_after_start_ms"], 120)
        self.assertEqual(receiver_rows[0]["relay_kib"], 4.0)
        self.assertEqual(receiver_rows[0]["error_kind"], "not_connected")

    def test_arti_profile_selector_move_risk_rows_join_moves_and_connects(
        self,
    ) -> None:
        target = "https://example.test/"
        payload = {
            "targets": [target],
            "profiles": {
                "arti_release_browser": {
                    "benchmarks": {
                        target: {
                            "summary": {"median_load_ms": 1000},
                            "runs": [
                                {
                                    "run_index": 1,
                                    "ok": True,
                                    "load_ms": 1000,
                                    "performance_timing": {
                                        "navigation": {
                                            "connectStart": 0,
                                            "connectEnd": 50,
                                            "responseStart": 100,
                                            "domContentLoadedEventEnd": 600,
                                            "loadEventEnd": 1000,
                                        }
                                    },
                                }
                            ],
                        }
                    },
                },
                "arti_release_browser_loadaware_healthyovercold1": {
                    "benchmarks": {
                        target: {
                            "summary": {"median_load_ms": 2400},
                            "runs": [
                                {
                                    "run_index": 1,
                                    "ok": True,
                                    "load_ms": 2400,
                                    "proxy_signal_lines": [
                                        "open_candidates=2 select_load_aware=true select_health_aware=true selected_candidate_index=1 healthy_over_cold_candidate_index=1 healthy_over_cold_guard_only_candidate_index=-1 candidate_assignment_summary=0:Circ~0.1:4,1:Circ~0.2:0 candidate_health_summary=0:Circ~0.1:1:100:50:1000:100:1,1:Circ~0.2:9:9000:20:9000:10:1 selected_assigned_streams=0 usage_kind=\"exit\" tunnel_unique_id=Circ 0.2 torfast circuit selection open",
                                        'timing_id=12 target_kind="hostname" command=CONNECT port=443 elapsed_ms=0 torfast socks timing request parsed',
                                        'timing_id=12 target_kind="hostname" port=443 connect_ms=1800 elapsed_ms=1800 torfast socks timing stream ready',
                                    ],
                                    "performance_timing": {
                                        "navigation": {
                                            "connectStart": 0,
                                            "connectEnd": 1800,
                                            "responseStart": 1850,
                                            "domContentLoadedEventEnd": 2100,
                                            "loadEventEnd": 2400,
                                        }
                                    },
                                }
                            ],
                        }
                    },
                },
            },
        }

        rows = arti_profile_selector_move_risk_rows(payload)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["load_aware_picks"], 1)
        self.assertEqual(rows[0]["selected_nonfirst"], 1)
        self.assertEqual(rows[0]["healthy_over_cold_moves"], 1)
        self.assertEqual(rows[0]["guard_only_healthy_over_cold_moves"], 0)
        self.assertEqual(rows[0]["candidate_slow_connect_streams"], 1)
        self.assertEqual(rows[0]["candidate_max_connect_ms"], 1800)
        self.assertEqual(rows[0]["baseline_slow_connect_streams"], 0)
        self.assertEqual(
            rows[0]["selector_risk_hint"],
            "healthy-over-cold moved but target lost",
        )

        stdout = io.StringIO()
        with patch("sys.stdout", stdout):
            print_arti_profile_selector_move_risk_table(payload)
        output = stdout.getvalue()
        self.assertIn("## Arti Profile Selector Move Risk", output)
        self.assertIn("healthy-over-cold moved but target lost", output)

    def test_failed_run_cause_rows_bucket_connect_and_relay_tails(self) -> None:
        payload = {
            "profiles": {
                "arti_release_browser_lab": {
                    "benchmarks": {
                        "https://example.test/": {
                            "summary": {"ok": False},
                            "runs": [
                                {
                                    "run_index": 1,
                                    "ok": False,
                                    "elapsed_ms": 61000,
                                    "load_ms": None,
                                    "screenshot": {"exists": False, "bytes": 0},
                                    "error": "Reached error page",
                                    "proxy_signal_lines": [
                                        'timing_id=1 target_kind="hostname" command=CONNECT port=443 conn_started_epoch_ms=0 elapsed_ms=0 torfast socks timing request parsed',
                                        'timing_id=1 target_kind="hostname" port=443 soft_timeout_ms=1000 elapsed_ms=1000 torfast socks timing connect soft timeout',
                                        'timing_id=1 target_kind="hostname" port=443 elapsed_ms=1001 torfast socks timing connect retry',
                                        'timing_id=1 target_kind="hostname" port=443 connect_ms=1700 elapsed_ms=1700 torfast socks timing stream ready',
                                        'timing_id=1 target_kind="hostname" port=443 circ_id=Circ 0.4 (Tunnel 15) hop=3 stream_id=11302 elapsed_ms=1701 torfast socks timing stream linked',
                                        'timing_id=1 target_kind="hostname" port=443 elapsed_ms=1710 torfast socks timing socks reply sent',
                                        'timing_id=1 target_kind="hostname" port=443 relay_ms=9000 elapsed_ms=9000 first_tor_to_client_ms=2200 last_tor_to_client_ms=2500 tor_to_client_bytes=10 copy_error_kind=not_connected copy_error=stream_not_connected ok=false torfast socks timing relay finished',
                                        'event_epoch_ms=2200 circ_id=Circ 0.4 (Tunnel 15) hop=Some(HopNum(3)) stream_id=11302 relay_cmd=RelayCmd(DATA) data_len=4 queued_before_bytes=0 queued_after_bytes=4 closes_stream=false torfast relay receive delivered',
                                        'event_epoch_ms=2500 circ_id=Circ 0.4 (Tunnel 15) hop=Some(HopNum(3)) stream_id=11302 relay_cmd=RelayCmd(DATA) data_len=6 queued_before_bytes=4 queued_after_bytes=10 closes_stream=false torfast relay receive delivered',
                                        'event_epoch_ms=9050 circ_id=Circ 0.4 (Tunnel 15) hop=3 stream_id=11302 connected=true pending_after_bytes=0 user_read_bytes=10 data_cells=2 error_kind=not_connected end_reason= returned_eof=false torfast stream receiver terminal',
                                        'timing_id=2 target_kind="onion" command=CONNECT port=443 elapsed_ms=0 torfast socks timing request parsed',
                                        'timing_id=2 target_kind="onion" port=443 connect_ms=2200 elapsed_ms=2200 torfast socks timing stream ready',
                                        'timing_id=3 target_kind="hostname" command=CONNECT port=443 elapsed_ms=0 torfast socks timing request parsed',
                                        'timing_id=3 target_kind="hostname" port=443 elapsed_ms=0 torfast socks timing socks reply sent',
                                        'timing_id=3 target_kind="hostname" port=443 relay_ms=8000 elapsed_ms=8000 first_tor_to_client_ms=0 last_tor_to_client_ms=0 tor_to_client_bytes=0 ok=false torfast socks timing relay finished',
                                    ],
                                },
                                {
                                    "run_index": 2,
                                    "ok": False,
                                    "elapsed_ms": 100,
                                    "load_ms": None,
                                    "screenshot": {"exists": False, "bytes": 0},
                                    "error": "browser crashed",
                                },
                            ],
                        }
                    },
                }
            }
        }

        rows = failed_run_cause_rows(payload)

        self.assertEqual(len(rows), 2)
        self.assertEqual(
            rows[0]["cause"], "mixed connect wait + relay-after-reply tail"
        )
        self.assertEqual(rows[0]["slow_connect_streams"], 2)
        self.assertEqual(rows[0]["slow_connect_target_kinds"], "hostname:1, onion:1")
        self.assertEqual(rows[0]["relay_tail_streams"], 2)
        self.assertEqual(rows[0]["relay_tail_target_kinds"], "hostname:2")
        self.assertEqual(
            rows[0]["relay_tail_shape"],
            "no Tor bytes, partial Tor bytes then idle",
        )
        self.assertEqual(rows[0]["relay_tail_with_tor_bytes"], 1)
        self.assertEqual(rows[0]["relay_tail_no_tor_bytes"], 1)
        self.assertEqual(rows[0]["relay_tail_idle_after_tor_byte"], 1)
        self.assertEqual(rows[0]["soft_timeouts"], 1)
        self.assertEqual(rows[0]["connect_retries"], 1)
        self.assertEqual(rows[0]["max_connect_ms"], 2200)
        self.assertEqual(rows[0]["max_relay_ms"], 9000)
        self.assertEqual(rows[0]["max_idle_after_last_tor_byte_ms"], 6500)
        self.assertEqual(rows[0]["proof"], "load missing, screenshot missing, browser error")
        self.assertEqual(rows[1]["cause"], "browser proof failure")

        detail_rows = failed_run_relay_tail_detail_rows(payload)
        self.assertEqual(len(detail_rows), 2)
        self.assertEqual(detail_rows[0]["timing_id"], 1)
        self.assertEqual(detail_rows[0]["shape"], "partial Tor bytes then idle")
        self.assertEqual(detail_rows[0]["circ_ids"], "Circ 0.4 (Tunnel 15):1")
        self.assertEqual(detail_rows[0]["stream_ids"], "11302:1")
        self.assertTrue(detail_rows[0]["joined"])
        self.assertEqual(detail_rows[0]["relay_data_bytes"], 10)
        self.assertEqual(detail_rows[0]["relay_data_cells"], 2)
        self.assertEqual(detail_rows[0]["max_receive_gap_ms"], 300)
        self.assertEqual(detail_rows[0]["copy_error_kind"], "not_connected")
        self.assertEqual(detail_rows[0]["copy_error"], "stream_not_connected")
        self.assertEqual(detail_rows[0]["reader_terminal_kind"], "not_connected")
        self.assertFalse(detail_rows[0]["reader_terminal_returned_eof"])
        self.assertEqual(detail_rows[0]["reader_terminal_ms_after_conn"], 9050)
        self.assertEqual(detail_rows[0]["reader_idle_after_last_tor_byte_ms"], 6550)
        self.assertEqual(detail_rows[0]["reader_user_read_bytes"], 10)
        self.assertEqual(detail_rows[0]["reader_data_cells"], 2)
        self.assertEqual(detail_rows[0]["reader_pending_after_bytes"], 0)
        self.assertTrue(detail_rows[0]["reader_connected"])
        self.assertEqual(detail_rows[1]["timing_id"], 3)
        self.assertEqual(detail_rows[1]["shape"], "no Tor bytes")
        self.assertFalse(detail_rows[1]["joined"])

        concentration_rows = failed_run_relay_tail_circuit_concentration_rows(payload)
        self.assertEqual(len(concentration_rows), 2)
        self.assertEqual(concentration_rows[0]["circ_id"], "Circ 0.4 (Tunnel 15)")
        self.assertEqual(concentration_rows[0]["relay_tail_streams"], 1)
        self.assertEqual(concentration_rows[0]["target_kinds"], "hostname:1")
        self.assertEqual(
            concentration_rows[0]["shapes"],
            "partial Tor bytes then idle:1",
        )
        self.assertEqual(concentration_rows[0]["with_tor_bytes"], 1)
        self.assertEqual(concentration_rows[0]["no_tor_bytes"], 0)
        self.assertEqual(concentration_rows[0]["idle_after_tor_bytes"], 1)
        self.assertEqual(concentration_rows[0]["total_tor_to_client_bytes"], 10)
        self.assertEqual(concentration_rows[0]["max_relay_ms"], 9000)
        self.assertEqual(
            concentration_rows[0]["max_idle_after_last_tor_byte_ms"],
            6500,
        )
        self.assertEqual(concentration_rows[0]["reader_connected_streams"], 1)
        self.assertEqual(concentration_rows[0]["reader_not_connected_streams"], 0)
        self.assertEqual(concentration_rows[0]["max_reader_terminal_ms"], 9050)
        self.assertEqual(concentration_rows[0]["top_timing_ids"], "1")
        self.assertEqual(concentration_rows[0]["top_stream_ids"], "11302")
        self.assertEqual(concentration_rows[1]["circ_id"], "(unknown)")
        self.assertEqual(concentration_rows[1]["relay_tail_streams"], 1)
        self.assertEqual(concentration_rows[1]["shapes"], "no Tor bytes:1")

    def test_successful_run_relay_tail_concentration_groups_slow_ok_runs(self) -> None:
        payload = {
            "profiles": {
                "arti_release_browser_lab": {
                    "benchmarks": {
                        "https://example.test/download": {
                            "summary": {"ok": True},
                            "runs": [
                                {
                                    "run_index": 1,
                                    "ok": True,
                                    "load_ms": 7200,
                                    "proxy_signal_lines": [
                                        'timing_id=4 target_kind="hostname" command=CONNECT port=443 elapsed_ms=0 torfast socks timing request parsed',
                                        'timing_id=4 target_kind="hostname" port=443 connect_ms=300 elapsed_ms=300 torfast socks timing stream ready',
                                        'timing_id=4 target_kind="hostname" port=443 circ_id=Circ 2.9 (Tunnel 44) hop=3 stream_id=210 elapsed_ms=301 torfast socks timing stream linked',
                                        'timing_id=4 target_kind="hostname" port=443 elapsed_ms=305 torfast socks timing socks reply sent',
                                        'timing_id=4 target_kind="hostname" port=443 relay_ms=7000 elapsed_ms=7000 first_tor_to_client_ms=500 last_tor_to_client_ms=1200 tor_to_client_bytes=100 ok=true torfast socks timing relay finished',
                                        'timing_id=5 target_kind="hostname" command=CONNECT port=443 elapsed_ms=0 torfast socks timing request parsed',
                                        'timing_id=5 target_kind="hostname" port=443 connect_ms=250 elapsed_ms=250 torfast socks timing stream ready',
                                        'timing_id=5 target_kind="hostname" port=443 circ_id=Circ 2.9 (Tunnel 44) hop=3 stream_id=211 elapsed_ms=251 torfast socks timing stream linked',
                                        'timing_id=5 target_kind="hostname" port=443 elapsed_ms=255 torfast socks timing socks reply sent',
                                        'timing_id=5 target_kind="hostname" port=443 relay_ms=6200 elapsed_ms=6200 first_tor_to_client_ms=0 last_tor_to_client_ms=0 tor_to_client_bytes=0 ok=true torfast socks timing relay finished',
                                        'timing_id=6 target_kind="hostname" command=CONNECT port=443 elapsed_ms=0 torfast socks timing request parsed',
                                        'timing_id=6 target_kind="hostname" port=443 relay_ms=1200 elapsed_ms=1200 ok=true torfast socks timing relay finished',
                                    ],
                                },
                                {
                                    "run_index": 2,
                                    "ok": False,
                                    "load_ms": None,
                                    "proxy_signal_lines": [
                                        'timing_id=7 target_kind="hostname" command=CONNECT port=443 elapsed_ms=0 torfast socks timing request parsed',
                                        'timing_id=7 target_kind="hostname" port=443 circ_id=Circ 8.1 (Tunnel 90) hop=3 stream_id=310 elapsed_ms=1 torfast socks timing stream linked',
                                        'timing_id=7 target_kind="hostname" port=443 relay_ms=9000 elapsed_ms=9000 first_tor_to_client_ms=0 last_tor_to_client_ms=0 tor_to_client_bytes=0 ok=false torfast socks timing relay finished',
                                    ],
                                },
                            ],
                        }
                    },
                }
            }
        }

        rows = successful_run_relay_tail_circuit_concentration_rows(payload)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["circ_id"], "Circ 2.9 (Tunnel 44)")
        self.assertEqual(rows[0]["relay_tail_streams"], 2)
        self.assertEqual(rows[0]["target_kinds"], "hostname:2")
        self.assertEqual(
            rows[0]["shapes"],
            "no Tor bytes:1, partial Tor bytes then idle:1",
        )
        self.assertEqual(rows[0]["with_tor_bytes"], 1)
        self.assertEqual(rows[0]["no_tor_bytes"], 1)
        self.assertEqual(rows[0]["total_tor_to_client_bytes"], 100)
        self.assertEqual(rows[0]["max_relay_ms"], 7000)
        self.assertEqual(rows[0]["top_timing_ids"], "4, 5")
        self.assertEqual(rows[0]["top_stream_ids"], "210, 211")

    def test_subtract_numeric_rejects_bool(self) -> None:
        self.assertEqual(subtract_numeric(8, 5), 3.0)
        self.assertIsNone(subtract_numeric(True, 5))
        self.assertIsNone(subtract_numeric(8, False))

    def test_start_arti_accepts_proxy_buffer_size(self) -> None:
        started = {}

        class FakePopen:
            stdout = None

        def fake_popen(command, **kwargs):
            started["command"] = command
            started["env"] = kwargs.get("env", {})
            return FakePopen()

        with (
            tempfile.TemporaryDirectory() as tmp,
            patch("subprocess.Popen", side_effect=fake_popen),
            patch("threading.Thread"),
        ):
            root = Path(tmp)
            start_arti(
                arti_bin=root / "arti",
                port=19082,
                cache_dir=root / "cache",
                state_dir=root / "state",
                proxy_buffer_size="1 MB",
            )

        command = started["command"]
        self.assertIn('proxy.socket_send_buf_size="1 MB"', command)
        self.assertIn('proxy.socket_recv_buf_size="1 MB"', command)
        self.assertIn(
            f'storage.port_info_file="{root / "state" / "port_info.json"}"',
            command,
        )
        self.assertNotIn("TORFAST_SOCKS_RELAY_BYTE_TIMING", started["env"])
        self.assertNotIn(
            "TORFAST_SOCKS_TOR_TO_CLIENT_COALESCE_BYTES", started["env"]
        )
        self.assertNotIn(
            "TORFAST_STREAM_READY_DATA_COALESCE_BYTES", started["env"]
        )

    def test_byte_timing_log_level_keeps_hs_phase_rows(self) -> None:
        self.assertEqual(
            effective_arti_log_level("info", True),
            "info,tor_proto=debug,tor_hsclient=debug",
        )

    def test_start_arti_sets_lab_env_overrides(self) -> None:
        started = {}

        class FakePopen:
            stdout = None

        def fake_popen(command, **kwargs):
            started["command"] = command
            started["env"] = kwargs.get("env", {})
            return FakePopen()

        with (
            tempfile.TemporaryDirectory() as tmp,
            patch("subprocess.Popen", side_effect=fake_popen),
            patch("threading.Thread"),
        ):
            root = Path(tmp)
            start_arti(
                arti_bin=root / "arti",
                port=19082,
                cache_dir=root / "cache",
                state_dir=root / "state",
                exit_select_parallelism=1,
                exit_launch_parallelism=2,
                hspool_launch_parallelism=3,
                hspool_background_start_delay_ms=0,
                hspool_on_demand_grace_ms=50,
                hspool_on_demand_race_ms=75,
                socks_connect_soft_timeout_ms=5000,
                socks_connect_soft_timeout_attempts=3,
                socks_connect_hedge_ms=1500,
                socks_relay_byte_timing=True,
                socks_tor_to_client_coalesce_bytes=4096,
                stream_ready_data_coalesce_bytes=8192,
                stream_scheduler_burst=2,
                socks_partial_relay_idle_timeout_ms=4000,
                socks_no_tor_byte_relay_timeout_ms=5000,
                exit_pending_hedge_ms=1500,
                exit_select_load_aware=True,
                exit_select_health_aware=True,
                exit_select_health_aware_min_assigned=3,
                exit_select_avoid_bad_health=True,
                exit_select_avoid_bad_health_unknown_fallback=True,
                exit_select_bad_health_hedge_ms=750,
                exit_select_bad_health_stream_idle_ms=5000,
                exit_select_bad_health_active_no_data_ms=6000,
                exit_select_max_active_streams=2,
                exit_select_max_assigned_streams=4,
                exit_select_min_assignment_spread=2,
                exit_select_healthy_over_cold_min_assigned=4,
                exit_select_healthy_over_cold_guard_only_min_assigned=5,
                exit_same_isolation_target=2,
                exit_same_isolation_other_isolation_min=3,
                exit_same_isolation_require_bad_health=True,
                exit_same_isolation_min_assigned_streams=1,
                exit_same_isolation_pending_wait_ms=800,
                exit_same_isolation_prewarm_first_stream=True,
                exit_same_isolation_prefer_topup_on_tie=True,
                hs_intro_rend_overlap=True,
                hs_rend_prebuild_before_desc=True,
                hs_desc_shared_cache=True,
                hs_intro_circuit_hedge_ms=1500,
                dir_select_spread=True,
                dir_incremental_microdescs=True,
                dir_microdesc_early_usable_notify=True,
                dir_microdesc_early_retry_on_partial=True,
                dir_microdesc_disable_bad_health_replacement=True,
                dir_microdesc_bad_health_replacement_suppress_gap_ms=5000,
                dir_microdesc_bad_health_replacement_suppress_min_assigned_streams=5,
                dir_microdesc_bad_health_replacement_suppress_min_active_streams=3,
                dir_microdesc_source_spread=True,
                dir_microdesc_pending_spread=True,
                dir_microdesc_ids_per_request=250,
                dir_microdesc_retry_ids_per_request=375,
                dir_microdesc_retry_delay_max_ms=500,
                dir_microdesc_parallelism=6,
                dir_microdesc_hedge_ms=6000,
                dirclient_read_timeout_ms=5000,
                dirclient_progress_read_timeout_ms=3000,
                dirclient_microdesc_body_max_ms=7000,
                dirclient_microdesc_min_rate_bps=98304,
                dirclient_timing_log=True,
            )

        self.assertEqual(started["env"]["TORFAST_EXIT_SELECT_PARALLELISM"], "1")
        self.assertEqual(started["env"]["TORFAST_EXIT_LAUNCH_PARALLELISM"], "2")
        self.assertEqual(started["env"]["TORFAST_HSPOOL_LAUNCH_PARALLELISM"], "3")
        self.assertEqual(
            started["env"]["TORFAST_HSPOOL_BACKGROUND_START_DELAY_MS"], "0"
        )
        self.assertEqual(
            started["env"]["TORFAST_HSPOOL_ON_DEMAND_POOL_GRACE_MS"], "50"
        )
        self.assertEqual(
            started["env"]["TORFAST_HSPOOL_ON_DEMAND_POOL_RACE_MS"], "75"
        )
        self.assertEqual(
            started["env"]["TORFAST_SOCKS_CONNECT_SOFT_TIMEOUT_MS"], "5000"
        )
        self.assertEqual(
            started["env"]["TORFAST_SOCKS_CONNECT_SOFT_TIMEOUT_ATTEMPTS"], "3"
        )
        self.assertEqual(started["env"]["TORFAST_SOCKS_CONNECT_HEDGE_MS"], "1500")
        self.assertEqual(
            started["command"][started["command"].index("-l") + 1],
            "info,tor_proto=debug,tor_circmgr=debug,tor_hsclient=debug",
        )
        self.assertEqual(started["env"]["TORFAST_HS_INTRO_REND_OVERLAP"], "1")
        self.assertEqual(
            started["env"]["TORFAST_HS_REND_PREBUILD_BEFORE_DESC"], "1"
        )
        self.assertEqual(started["env"]["TORFAST_HS_DESC_SHARED_CACHE"], "1")
        self.assertEqual(
            started["env"]["TORFAST_HS_INTRO_CIRCUIT_HEDGE_MS"], "1500"
        )
        self.assertEqual(started["env"]["TORFAST_SOCKS_RELAY_BYTE_TIMING"], "1")
        self.assertEqual(
            started["env"]["TORFAST_SOCKS_TOR_TO_CLIENT_COALESCE_BYTES"],
            "4096",
        )
        self.assertEqual(
            started["env"]["TORFAST_STREAM_READY_DATA_COALESCE_BYTES"],
            "8192",
        )
        self.assertEqual(started["env"]["TORFAST_STREAM_SCHEDULER_BURST"], "2")
        self.assertEqual(started["env"]["TORFAST_CIRCUIT_CONGESTION_LOG"], "1")
        self.assertEqual(started["env"]["TORFAST_STREAM_SCHEDULER_LOG"], "1")
        self.assertEqual(started["env"]["TORFAST_STREAM_LIFECYCLE_LOG"], "1")
        self.assertEqual(
            started["env"]["TORFAST_EXIT_SELECT_LOW_LOG_CONTEXT"], "1"
        )
        self.assertEqual(
            started["env"]["TORFAST_SOCKS_PARTIAL_RELAY_IDLE_TIMEOUT_MS"],
            "4000",
        )
        self.assertEqual(
            started["env"]["TORFAST_SOCKS_NO_TOR_BYTE_RELAY_TIMEOUT_MS"],
            "5000",
        )
        self.assertEqual(started["env"]["TORFAST_EXIT_PENDING_HEDGE_MS"], "1500")
        self.assertEqual(started["env"]["TORFAST_EXIT_SELECT_LOAD_AWARE"], "1")
        self.assertEqual(started["env"]["TORFAST_EXIT_SELECT_HEALTH_AWARE"], "1")
        self.assertEqual(
            started["env"]["TORFAST_EXIT_SELECT_HEALTH_AWARE_MIN_ASSIGNED"], "3"
        )
        self.assertEqual(
            started["env"]["TORFAST_EXIT_SELECT_AVOID_BAD_HEALTH"], "1"
        )
        self.assertEqual(
            started["env"]["TORFAST_EXIT_SELECT_AVOID_BAD_HEALTH_UNKNOWN_FALLBACK"],
            "1",
        )
        self.assertEqual(
            started["env"]["TORFAST_EXIT_SELECT_BAD_HEALTH_HEDGE_MS"], "750"
        )
        self.assertEqual(
            started["env"]["TORFAST_EXIT_SELECT_BAD_HEALTH_STREAM_IDLE_MS"],
            "5000",
        )
        self.assertEqual(
            started["env"]["TORFAST_EXIT_SELECT_BAD_HEALTH_ACTIVE_NO_DATA_MS"],
            "6000",
        )
        self.assertEqual(
            started["env"]["TORFAST_EXIT_SELECT_MAX_ACTIVE_STREAMS"],
            "2",
        )
        self.assertEqual(
            started["env"]["TORFAST_EXIT_SELECT_MAX_ASSIGNED_STREAMS"],
            "4",
        )
        self.assertEqual(
            started["env"]["TORFAST_EXIT_SELECT_MIN_ASSIGNMENT_SPREAD"], "2"
        )
        self.assertEqual(
            started["env"]["TORFAST_EXIT_SELECT_HEALTHY_OVER_COLD_MIN_ASSIGNED"],
            "4",
        )
        self.assertEqual(
            started["env"][
                "TORFAST_EXIT_SELECT_HEALTHY_OVER_COLD_GUARD_ONLY_MIN_ASSIGNED"
            ],
            "5",
        )
        self.assertEqual(started["env"]["TORFAST_EXIT_SAME_ISOLATION_TARGET"], "2")
        self.assertEqual(
            started["env"]["TORFAST_EXIT_SAME_ISOLATION_OTHER_ISOLATION_MIN"],
            "3",
        )
        self.assertEqual(
            started["env"]["TORFAST_EXIT_SAME_ISOLATION_REQUIRE_BAD_HEALTH"], "1"
        )
        self.assertEqual(
            started["env"]["TORFAST_EXIT_SAME_ISOLATION_MIN_ASSIGNED_STREAMS"],
            "1",
        )
        self.assertEqual(
            started["env"]["TORFAST_EXIT_SAME_ISOLATION_PENDING_WAIT_MS"],
            "800",
        )
        self.assertEqual(
            started["env"]["TORFAST_EXIT_SAME_ISOLATION_PREWARM_FIRST_STREAM"],
            "1",
        )
        self.assertEqual(
            started["env"]["TORFAST_EXIT_SAME_ISOLATION_PREFER_TOPUP_ON_TIE"],
            "1",
        )
        self.assertEqual(started["env"]["TORFAST_DIR_SELECT_SPREAD"], "1")
        self.assertEqual(started["env"]["TORFAST_DIR_INCREMENTAL_MICRODESCS"], "1")
        self.assertEqual(
            started["env"]["TORFAST_DIR_MICRODESC_EARLY_USABLE_NOTIFY"], "1"
        )
        self.assertEqual(
            started["env"]["TORFAST_DIR_MICRODESC_EARLY_RETRY_ON_PARTIAL"], "1"
        )
        self.assertEqual(
            started["env"]["TORFAST_DIR_MICRODESC_DISABLE_BAD_HEALTH_REPLACEMENT"],
            "1",
        )
        self.assertEqual(
            started["env"][
                "TORFAST_DIR_MICRODESC_BAD_HEALTH_REPLACEMENT_SUPPRESS_GAP_MS"
            ],
            "5000",
        )
        self.assertEqual(
            started["env"][
                "TORFAST_DIR_MICRODESC_BAD_HEALTH_REPLACEMENT_SUPPRESS_MIN_ASSIGNED_STREAMS"
            ],
            "5",
        )
        self.assertEqual(
            started["env"][
                "TORFAST_DIR_MICRODESC_BAD_HEALTH_REPLACEMENT_SUPPRESS_MIN_ACTIVE_STREAMS"
            ],
            "3",
        )
        self.assertEqual(
            started["env"]["TORFAST_DIR_MICRODESC_SOURCE_SPREAD"], "1"
        )
        self.assertEqual(
            started["env"]["TORFAST_DIR_MICRODESC_PENDING_SPREAD"], "1"
        )
        self.assertEqual(
            started["env"]["TORFAST_DIR_MICRODESC_IDS_PER_REQUEST"], "250"
        )
        self.assertEqual(
            started["env"]["TORFAST_DIR_MICRODESC_RETRY_IDS_PER_REQUEST"],
            "375",
        )
        self.assertEqual(
            started["env"]["TORFAST_DIR_MICRODESC_RETRY_DELAY_MAX_MS"],
            "500",
        )
        self.assertIn(
            "download_schedule.retry_microdescs.parallelism=6",
            started["command"],
        )
        self.assertEqual(started["env"]["TORFAST_DIR_MICRODESC_HEDGE_MS"], "6000")
        self.assertEqual(started["env"]["TORFAST_DIRCLIENT_READ_TIMEOUT_MS"], "5000")
        self.assertEqual(
            started["env"]["TORFAST_DIRCLIENT_PROGRESS_READ_TIMEOUT_MS"],
            "3000",
        )
        self.assertEqual(
            started["env"]["TORFAST_DIRCLIENT_MICRODESC_BODY_MAX_MS"],
            "7000",
        )
        self.assertEqual(
            started["env"]["TORFAST_DIRCLIENT_MICRODESC_MIN_RATE_BPS"],
            "98304",
        )
        self.assertEqual(started["env"]["TORFAST_DIRCLIENT_TIMING_LOG"], "1")

    def test_start_arti_accepts_min_exit_circs_override(self) -> None:
        started = {}

        class FakePopen:
            stdout = None

        def fake_popen(command, **_kwargs):
            started["command"] = command
            return FakePopen()

        with (
            tempfile.TemporaryDirectory() as tmp,
            patch("subprocess.Popen", side_effect=fake_popen),
            patch("threading.Thread"),
        ):
            root = Path(tmp)
            start_arti(
                arti_bin=root / "arti",
                port=19082,
                cache_dir=root / "cache",
                state_dir=root / "state",
                min_exit_circs_for_port=3,
            )

        self.assertIn(
            "preemptive_circuits.min_exit_circs_for_port=3",
            started["command"],
        )

    def test_start_arti_avoid_bad_health_does_not_enable_load_aware(self) -> None:
        started = {}

        class FakePopen:
            stdout = None

        def fake_popen(command, **kwargs):
            started["env"] = kwargs.get("env", {})
            return FakePopen()

        with (
            tempfile.TemporaryDirectory() as tmp,
            patch("subprocess.Popen", side_effect=fake_popen),
            patch("threading.Thread"),
        ):
            root = Path(tmp)
            start_arti(
                arti_bin=root / "arti",
                port=19082,
                cache_dir=root / "cache",
                state_dir=root / "state",
                exit_select_avoid_bad_health=True,
            )

        self.assertEqual(
            started["env"]["TORFAST_EXIT_SELECT_AVOID_BAD_HEALTH"], "1"
        )
        self.assertNotIn("TORFAST_EXIT_SELECT_LOAD_AWARE", started["env"])

    def test_start_arti_same_isolation_does_not_enable_load_aware(self) -> None:
        started = {}

        class FakePopen:
            stdout = None

        def fake_popen(command, **kwargs):
            started["env"] = kwargs.get("env", {})
            return FakePopen()

        with (
            tempfile.TemporaryDirectory() as tmp,
            patch("subprocess.Popen", side_effect=fake_popen),
            patch("threading.Thread"),
        ):
            root = Path(tmp)
            start_arti(
                arti_bin=root / "arti",
                port=19082,
                cache_dir=root / "cache",
                state_dir=root / "state",
                exit_same_isolation_target=2,
            )

        self.assertEqual(started["env"]["TORFAST_EXIT_SAME_ISOLATION_TARGET"], "2")
        self.assertNotIn("TORFAST_EXIT_SELECT_LOAD_AWARE", started["env"])

    def test_start_arti_guard_only_healthy_over_cold_does_not_enable_load_aware(
        self,
    ) -> None:
        started = {}

        class FakePopen:
            stdout = None

        def fake_popen(command, **kwargs):
            started["env"] = kwargs.get("env", {})
            return FakePopen()

        with (
            tempfile.TemporaryDirectory() as tmp,
            patch("subprocess.Popen", side_effect=fake_popen),
            patch("threading.Thread"),
        ):
            root = Path(tmp)
            start_arti(
                arti_bin=root / "arti",
                port=19082,
                cache_dir=root / "cache",
                state_dir=root / "state",
                exit_select_healthy_over_cold_guard_only_min_assigned=4,
            )

        self.assertEqual(
            started["env"][
                "TORFAST_EXIT_SELECT_HEALTHY_OVER_COLD_GUARD_ONLY_MIN_ASSIGNED"
            ],
            "4",
        )
        self.assertNotIn("TORFAST_EXIT_SELECT_LOAD_AWARE", started["env"])

    def test_socks_proxy_parser_finds_stream_data_after_no_auth(self) -> None:
        parser = SocksProxyToClientParser()

        self.assertEqual(parser.feed(b"\x05\x00"), 0)
        self.assertEqual(parser.feed(b"\x05\x00\x00\x01\x00\x00\x00\x00\x00\x00"), 0)
        self.assertEqual(parser.feed(b"HTTP/1.1 200 OK\r\n"), 17)

    def test_socks_proxy_parser_handles_username_password_auth(self) -> None:
        parser = SocksProxyToClientParser()

        self.assertEqual(parser.feed(b"\x05\x02"), 0)
        self.assertEqual(parser.feed(b"\x01\x00"), 0)
        self.assertEqual(parser.feed(b"\x05\x00\x00\x01\x00\x00\x00\x00\x00\x00x"), 1)

    def test_socks_proxy_parser_can_tag_success_reply_bind_port(self) -> None:
        parser = SocksProxyToClientParser()
        tag_port = socks_reply_bind_port_tag_for_connection(7)

        stream_bytes, output, updates = parser.feed_with_reply_tag(
            b"\x05\x00", reply_tag_port=tag_port
        )
        self.assertEqual(stream_bytes, 0)
        self.assertEqual(output, b"\x05\x00")
        self.assertEqual(updates, {})

        stream_bytes, output, updates = parser.feed_with_reply_tag(
            b"\x05\x00\x00\x01\x7f\x00\x00\x01\x00\x00",
            reply_tag_port=tag_port,
        )
        self.assertEqual(stream_bytes, 0)
        self.assertEqual(output[-2:], tag_port.to_bytes(2, "big"))
        self.assertEqual(updates["socks_reply_original_bind_port"], 0)
        self.assertEqual(updates["socks_reply_tag_bind_port"], tag_port)

        stream_bytes, output, updates = parser.feed_with_reply_tag(
            b"HTTP/1.1 200 OK\r\n", reply_tag_port=tag_port
        )
        self.assertEqual(stream_bytes, 17)
        self.assertEqual(output, b"HTTP/1.1 200 OK\r\n")
        self.assertEqual(updates, {})

    def test_socks_client_parser_records_request_without_auth_secret(self) -> None:
        parser = SocksClientToProxyParser()

        updates = parser.feed(
            b"\x05\x02\x00\x02", elapsed_ms=1.25, event_epoch_ms=1000.5
        )
        self.assertEqual(updates["socks_client_version"], 5)
        self.assertEqual(updates["socks_client_methods"], [0, 2])
        self.assertEqual(updates["socks_greeting_elapsed_ms"], 1.25)

        updates = parser.feed(
            (
                b"\x01\x04user\x06secret"
                b"\x05\x01\x00\x03\x12www.torproject.org\x01\xbb"
            ),
            elapsed_ms=4.5,
            event_epoch_ms=1004.0,
        )

        self.assertTrue(updates["socks_auth_present"])
        self.assertEqual(updates["socks_auth_username_len"], 4)
        self.assertEqual(updates["socks_auth_password_len"], 6)
        self.assertNotIn("socks_auth_username_sha256_12", updates)
        self.assertNotIn("socks_auth_password_sha256_12", updates)
        self.assertEqual(updates["socks_command"], "connect")
        self.assertEqual(updates["socks_target_host"], "www.torproject.org")
        self.assertEqual(updates["socks_target_port"], 443)
        self.assertEqual(updates["socks_connect_request_elapsed_ms"], 4.5)
        serialized = json.dumps(updates)
        self.assertNotIn('"user"', serialized)
        self.assertNotIn("secret", serialized)

    def test_rejects_failed_proxy_warmup(self) -> None:
        self.assertFalse(
            all_profiles_ok(
                {
                    "arti_release_browser": {
                        "warmup_boot": {"ok": False},
                        "boot": {"ok": False},
                        "benchmarks": {},
                    }
                }
            )
        )

    def test_compact_output_removes_browser_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile = root / "profile"
            home = root / "home"
            profile.mkdir()
            home.mkdir()
            (profile / "prefs.js").write_text("", encoding="utf-8")

            artifacts = cleanup_browser_artifacts(
                profile_dir=profile,
                home_dir=home,
                compact_output=True,
            )

            self.assertFalse(profile.exists())
            self.assertFalse(home.exists())
            self.assertEqual(artifacts["removed"], ["profile_dir", "home_dir"])
            self.assertEqual(artifacts["errors"], [])

    def test_compact_output_retains_failed_browser_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile = root / "profile"
            home = root / "home"
            profile.mkdir()
            home.mkdir()

            artifacts = cleanup_browser_artifacts(
                profile_dir=profile,
                home_dir=home,
                compact_output=True,
                retain=True,
            )

            self.assertTrue(profile.exists())
            self.assertTrue(home.exists())
            self.assertEqual(artifacts["removed"], [])
            self.assertEqual(artifacts["errors"], [])
            self.assertEqual(artifacts["retain_reason"], "failed_run")

    def test_browser_net_log_env_sets_moz_log_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "browser.mozlog"

            env = browser_net_log_env(log_path)

            self.assertEqual(env["MOZ_LOG"], BROWSER_NET_MOZ_LOG)
            self.assertEqual(env["MOZ_LOG_FILE"], str(log_path.resolve()))
            self.assertIn("nsHttp", env["MOZ_LOG"])
            self.assertIn("nsSocketTransport", env["MOZ_LOG"])

    def test_run_browser_benchmarks_forwards_browser_startup_seed_options(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "out"
            seed_root = Path(tmp) / "browser-startup-seed"
            with patch(
                "run_browser_compare.run_browser_once",
                return_value={
                    "ok": True,
                    "elapsed_ms": 1000.0,
                    "load_ms": 800.0,
                    "screenshot": {"bytes": 100},
                    "performance_timing": {},
                },
            ) as run_once:
                benchmarks = run_browser_benchmarks(
                    browser_bin=Path("/tmp/firefox"),
                    port=9150,
                    output_dir=output_dir,
                    targets=["https://example.com/"],
                    runs=1,
                    timeout=1.0,
                    window_size="1000,1000",
                    browser_startup_seed_root=seed_root,
                    no_browser_startup_seed=True,
                )

            self.assertTrue(benchmarks["https://example.com/"]["summary"]["ok"])
            self.assertEqual(
                run_once.call_args.kwargs["browser_startup_seed_root"],
                seed_root,
            )
            self.assertTrue(run_once.call_args.kwargs["no_browser_startup_seed"])

    def test_run_browser_benchmarks_forwards_browser_request_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "out"
            with patch(
                "run_browser_compare.run_browser_once",
                return_value={
                    "ok": True,
                    "elapsed_ms": 1000.0,
                    "load_ms": 800.0,
                    "screenshot": {"bytes": 100},
                    "performance_timing": {},
                },
            ) as run_once:
                benchmarks = run_browser_benchmarks(
                    browser_bin=Path("/tmp/firefox"),
                    port=9150,
                    output_dir=output_dir,
                    targets=["https://example.com/"],
                    runs=1,
                    timeout=1.0,
                    window_size="1000,1000",
                    browser_block_url_substrings=[
                        " /static/js/fallback.js ",
                        "/static/js/fallback.js",
                    ],
                )

        self.assertTrue(benchmarks["https://example.com/"]["summary"]["ok"])
        self.assertEqual(
            run_once.call_args.kwargs["browser_block_url_substrings"],
            ["/static/js/fallback.js"],
        )

    def test_summarize_browser_net_log_keeps_tail_and_child_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "browser.mozlog"
            log_path.write_text("root one\nroot two\n", encoding="utf-8")
            child_path = Path(tmp) / "browser.mozlog.child-1"
            child_path.write_text("child one\nchild two\n", encoding="utf-8")

            summary = summarize_browser_net_log(log_path, enabled=True)

            self.assertTrue(summary["enabled"])
            self.assertTrue(summary["ok"])
            self.assertEqual(summary["moz_log"], BROWSER_NET_MOZ_LOG)
            self.assertEqual(summary["line_count"], 4)
            self.assertEqual(summary["tail"], ["root one", "root two", "child one", "child two"])
            self.assertEqual(summary["errors"], [])
            self.assertEqual(
                summary["files"],
                [str(log_path), str(child_path)],
            )

    def test_parse_browser_net_log_timestamp_ms(self) -> None:
        parsed = parse_browser_net_log_timestamp_ms(
            "2026-06-12 19:16:41.851697 UTC - [Child]: D/nsHttp test"
        )

        self.assertEqual(parsed, 1781291801851)

    def test_browser_net_log_resource_evidence_matches_channel_uri(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            resource_url = "https://www.torproject.org/static/css/app.css?h=1"
            child_log_path = Path(tmp) / "browser.child.mozlog"
            child_log_path.write_text(
                "\n".join(
                    [
                        "2026-06-12 19:16:41.851697 UTC - [Child]: D/nsHttp Creating HttpChannelChild @abc123",
                        f"2026-06-12 19:16:41.851702 UTC - [Child]: E/nsHttp uri={resource_url}",
                        f"2026-06-12 19:16:41.851738 UTC - [Child]: D/nsHttp HttpChannelChild::AsyncOpen [this=abc123 uri={resource_url}]",
                        "2026-06-12 19:16:41.851827 UTC - [Child]: D/nsHttp HttpBackgroundChannelChild::Init [this=b456 httpChannel=abc123 channelId=42]",
                        "2026-06-12 19:16:42.005130 UTC - [Child]: D/nsHttp HttpBackgroundChannelChild::RecvOnStartRequest [this=b456, status=0]",
                        "2026-06-12 19:16:42.005206 UTC - [Child]: D/nsHttp HttpChannelChild::DoOnDataAvailable [this=abc123, request=req1]",
                        "2026-06-12 19:16:42.063046 UTC - [Child]: D/nsHttp HttpChannelChild::OnStopRequest [this=abc123 status=0]",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            parent_log_path = Path(tmp) / "browser.parent.mozlog"
            ci_digest = bytes.fromhex(
                "0123456789abcdef0123456789abcdef"
                "0123456789abcdef0123456789abcdef"
            )
            parent_log_path.write_bytes(
                b"\n".join(
                    [
                        f"2026-06-12 19:16:41.854913 UTC - [Parent]: D/nsHttp HttpChannelParent RecvAsyncOpen [this=109b938c0 uri={resource_url}, gid=42 browserid=5]".encode(),
                        b"2026-06-12 19:16:41.854941 UTC - [Parent]: D/nsHttp Creating nsHttpChannel [this=149db3600, nsIChannel=149db3640]",
                        b"2026-06-12 19:16:41.867541 UTC - [Parent]: D/nsHttp nsHttpChannel::DispatchTransaction [this=149db3600, aTransWithStickyConn=0]",
                        b"2026-06-12 19:16:41.867542 UTC - [Parent]: V/nsHttp Creating nsHttpTransaction @14e337a00",
                        b"2026-06-12 19:16:41.869653 UTC - [Parent]: V/nsHttp Creating DnsAndConnectSocket [this=14e5a7380 trans=14e337a00 ent=www.torproject.org key=.S.P......www.torproject.org:443 (socks:127.0.0.1:19182)]",
                        b"2026-06-12 19:16:41.869669 UTC - [Parent]: E/nsSocketTransport nsSocketTransport::Init [this=14e7e8a00 host=www.torproject.org:443 origin=www.torproject.org:443 proxy=127.0.0.1:19182]",
                        b"2026-06-12 19:16:41.869700 UTC - [Parent]: E/nsHttp nsHttpConnection::Init this=14e90000 sockettransport=14e7e8a18 forWebSocket=0",
                        (
                            b"2026-06-12 19:16:41.869710 UTC - [Parent]: V/nsHttp nsHttpConnectionMgr::DispatchAbstractTransaction "
                            b"[ci=.S.P......[tlsflags0x00000000]www.torproject.org:443 (socks:127.0.0.1:19182)[torproject.org:0:"
                            + ci_digest
                            + b" trans=14e337a00 caps=5200001 conn=14e90000]"
                        ),
                        b"2026-06-12 19:16:41.869720 UTC - [Parent]: E/nsHttp nsHttpConnection::Activate [this=14e90000 trans=14e337a00 caps=5200001]",
                    ]
                )
                + b"\n"
            )
            run = {
                "ok": True,
                "run_index": 1,
                "browser_net_log": {
                    "enabled": True,
                    "files": [str(child_log_path), str(parent_log_path)],
                    "bytes": child_log_path.stat().st_size + parent_log_path.stat().st_size,
                },
                "browser_activity_probe": {
                    "enabled": True,
                    "ok": True,
                    "activity_distributor_ok": True,
                    "rows": [
                        {
                            "source": "http_activity",
                            "method": "observeActivity",
                            "channel_id": 42,
                            "uri": resource_url,
                            "localAddress": "0.0.0.0",
                            "localPort": 40007,
                            "remoteAddress": "0.0.0.0",
                            "remotePort": 443,
                            "subject_localPort": 40007,
                            "subject_connectionInfoHashKey": (
                                ".S.P......[tlsflags0x00000000]"
                                "www.torproject.org:443 "
                                "(socks:127.0.0.1:19182)[torproject.org:0:"
                                + ci_digest.decode("latin-1")
                                + "]{TPRH}^privateBrowsingId=1"
                            ),
                        }
                    ],
                },
                "performance_timing": {
                    "time_origin_ms": 1781291800000,
                    "resources": [
                        {
                            "name": resource_url,
                            "startTime": 1851.697,
                            "duration": 1000.0,
                        }
                    ],
                },
            }
            payload = {
                "profiles": {
                    "arti_release_browser": {
                        "boot": {"ok": True},
                        "byte_tap": {
                            "enabled": True,
                            "ok": True,
                            "listen_host": "127.0.0.1",
                            "listen_port": 19182,
                            "upstream_host": "127.0.0.1",
                            "upstream_port": 19082,
                            "connections": [
                                {
                                    "connection_id": 7,
                                    "started_epoch_ms": 1781291801870,
                                    "upstream_local_port": 60123,
                                    "upstream_peer_port": 19082,
                                    "browser_peer_port": 55222,
                                    "socks_auth_password_sha256_12": "0123456789ab",
                                    "socks_reply_tag_bind_port": 40007,
                                    "socks_target_host": "www.torproject.org",
                                }
                            ],
                            "events": [],
                        },
                        "proxy_output_tail": [
                            "2026-06-12T19:16:41Z  INFO arti::proxy::socks: timing_id=9 target_kind=hostname target_label=www.torproject.org port=443 client_peer_port=60123 conn_started_epoch_ms=1781291801871 circ_id=Circ 4.4 hop=3 stream_id=77 elapsed_ms=1 torfast socks timing stream linked"
                        ],
                        "benchmarks": {
                            "https://www.torproject.org/": {
                                "summary": {"ok": True},
                                "runs": [run],
                            }
                        },
                    }
                }
            }

            channel_rows = browser_net_log_channel_rows_for_run(run)
            parent_bridge_rows = browser_net_log_parent_bridge_rows_for_run(run)
            profile = payload["profiles"]["arti_release_browser"]
            stream_bridge_rows = browser_net_log_socks_stream_bridge_rows_for_run(
                profile, run, parent_bridge_rows
            )
            evidence_rows = browser_net_log_resource_evidence_rows(payload)
            activity_evidence_rows = browser_activity_probe_evidence_rows(payload)

        self.assertEqual(len(channel_rows), 1)
        self.assertEqual(channel_rows[0]["uri"], resource_url)
        self.assertEqual(channel_rows[0]["channel_id"], 42)
        self.assertEqual(channel_rows[0]["data_events"], 1)
        self.assertEqual(len(parent_bridge_rows), 1)
        self.assertEqual(parent_bridge_rows[0]["channel_id"], 42)
        self.assertEqual(parent_bridge_rows[0]["parent_channel"], "109b938c0")
        self.assertEqual(parent_bridge_rows[0]["ns_http_channel"], "149db3600")
        self.assertEqual(parent_bridge_rows[0]["transaction"], "14e337a00")
        self.assertEqual(parent_bridge_rows[0]["socket_transport"], "14e7e8a00")
        self.assertEqual(parent_bridge_rows[0]["proxy"], "127.0.0.1:19182")
        self.assertEqual(len(stream_bridge_rows), 1)
        self.assertEqual(stream_bridge_rows[0]["connection_id"], 7)
        self.assertEqual(stream_bridge_rows[0]["client_peer_port"], 60123)
        self.assertEqual(stream_bridge_rows[0]["timing_id"], 9)
        self.assertEqual(stream_bridge_rows[0]["stream_id"], 77)
        self.assertEqual(
            stream_bridge_rows[0]["ci_socks_password_sha256_12"], "0123456789ab"
        )
        self.assertEqual(len(evidence_rows), 1)
        self.assertEqual(evidence_rows[0]["matched_resources"], 1)
        self.assertEqual(evidence_rows[0]["parent_channels"], 1)
        self.assertEqual(evidence_rows[0]["proxy_socket_rows"], 1)
        self.assertEqual(evidence_rows[0]["ci_auth_rows"], 1)
        self.assertEqual(evidence_rows[0]["ci_auth_tap_matches"], 0)
        self.assertEqual(evidence_rows[0]["socks_stream_bridge_rows"], 1)
        self.assertEqual(evidence_rows[0]["bridged_resources"], 1)
        self.assertEqual(evidence_rows[0]["stream_bridged_resources"], 1)
        self.assertEqual(evidence_rows[0]["socks_stream_id_available"], "yes")
        self.assertEqual(len(activity_evidence_rows), 1)
        self.assertEqual(activity_evidence_rows[0]["http_activity_rows"], 1)
        self.assertEqual(activity_evidence_rows[0]["ci_auth_rows"], 1)
        self.assertEqual(activity_evidence_rows[0]["ci_auth_tap_matches"], 1)
        self.assertEqual(activity_evidence_rows[0]["ci_auth_buckets"], 1)
        self.assertEqual(activity_evidence_rows[0]["nonzero_local_port_rows"], 1)
        self.assertEqual(activity_evidence_rows[0]["exact_local_socks_rows"], 0)
        self.assertEqual(activity_evidence_rows[0]["socks_reply_tag_rows"], 1)
        self.assertEqual(
            activity_evidence_rows[0]["socks_reply_tag_connection_matches"], 1
        )
        self.assertIn(
            "40007=>conn7:www.torproject.org",
            activity_evidence_rows[0]["sample_socks_reply_tags"],
        )
        self.assertIn("channelId=42", evidence_rows[0]["sample_matches"])
        self.assertIn("proxy=127.0.0.1:19182", evidence_rows[0]["sample_matches"])
        self.assertIn("ciAuth=0123456789ab", evidence_rows[0]["sample_matches"])
        self.assertIn("timing_id=9", evidence_rows[0]["sample_matches"])
        self.assertIn("stream_id=77", evidence_rows[0]["sample_matches"])

    def test_browser_activity_probe_bridges_reused_resource_to_socks_stream(
        self,
    ) -> None:
        resource_url = "https://www.torproject.org/static/js/app.js?h=1"
        run = {
            "ok": True,
            "run_index": 1,
            "browser_activity_probe": {
                "enabled": True,
                "ok": True,
                "rows": [
                    {
                        "topic": "http-on-examine-response",
                        "channel_id": 42,
                        "uri": resource_url,
                        "localAddress": "127.0.0.1",
                        "localPort": 55222,
                        "remoteAddress": "127.0.0.1",
                        "remotePort": 19182,
                        "observed_epoch_ms": 1781291802000,
                    }
                ],
            },
            "performance_timing": {
                "time_origin_ms": 1781291801870,
                "resources": [
                    {
                        "name": resource_url,
                        "initiatorType": "script",
                        "fetchStart": 100.0,
                        "requestStart": 250.0,
                        "responseStart": 550.0,
                        "responseEnd": 650.0,
                        "duration": 550.0,
                    }
                ]
            },
        }
        profile = {
            "byte_tap": {
                "enabled": True,
                "ok": True,
                "listen_host": "127.0.0.1",
                "listen_port": 19182,
                "upstream_host": "127.0.0.1",
                "upstream_port": 19082,
                "connections": [
                    {
                        "connection_id": 7,
                        "started_epoch_ms": 1781291801870,
                        "browser_peer_port": 55222,
                        "upstream_local_port": 60123,
                    }
                ],
                "events": [],
            },
            "proxy_output_tail": [
                "2026-06-12T19:16:41Z  INFO arti::proxy::socks: timing_id=9 target_kind=hostname target_label=www.torproject.org port=443 client_peer_port=60123 conn_started_epoch_ms=1781291801871 circ_id=Circ 4.4 hop=3 stream_id=77 elapsed_ms=1 torfast socks timing stream linked"
            ],
        }
        parent_bridge_rows = [
            {
                "channel_id": 42,
                "uri": resource_url,
                "transaction": "14e337a00",
            }
        ]

        stream_bridge_rows = browser_net_log_socks_stream_bridge_rows_for_run(
            profile, run, parent_bridge_rows
        )
        payload = {
            "profiles": {
                "arti_release_browser": {
                    **profile,
                    "benchmarks": {
                        "https://www.torproject.org/": {
                            "summary": {"ok": True},
                            "runs": [run],
                        }
                    },
                }
            }
        }
        resource_rows = browser_activity_tagged_stream_resource_rows(payload)

        self.assertEqual(len(stream_bridge_rows), 1)
        self.assertEqual(stream_bridge_rows[0]["connection_id"], 7)
        self.assertEqual(stream_bridge_rows[0]["browser_peer_port"], 55222)
        self.assertEqual(stream_bridge_rows[0]["client_peer_port"], 60123)
        self.assertEqual(stream_bridge_rows[0]["timing_id"], 9)
        self.assertEqual(stream_bridge_rows[0]["stream_id"], 77)
        self.assertEqual(
            stream_bridge_rows[0]["stream_bridge_method"],
            "browser_activity_local_port",
        )

    def test_browser_activity_probe_tag_disambiguates_same_host_sockets(
        self,
    ) -> None:
        resource_url = "https://www.torproject.org/static/js/app.js?h=1"
        second_resource_url = "https://www.torproject.org/static/js/next.js?h=1"
        run = {
            "ok": True,
            "run_index": 1,
            "browser_activity_probe": {
                "enabled": True,
                "ok": True,
                "rows": [
                    {
                        "source": "http_activity",
                        "method": "observeActivity",
                        "channel_id": 42,
                        "uri": resource_url,
                        "localAddress": "0.0.0.0",
                        "localPort": 40007,
                        "remoteAddress": "0.0.0.0",
                        "remotePort": 443,
                        "observed_epoch_ms": 1781291802000,
                    },
                    {
                        "source": "http_activity",
                        "method": "observeActivity",
                        "channel_id": 43,
                        "uri": second_resource_url,
                        "localAddress": "0.0.0.0",
                        "localPort": 40007,
                        "remoteAddress": "0.0.0.0",
                        "remotePort": 443,
                        "observed_epoch_ms": 1781291802500,
                    }
                ],
            },
            "performance_timing": {
                "time_origin_ms": 1781291801870,
                "resources": [
                    {
                        "name": resource_url,
                        "initiatorType": "script",
                        "fetchStart": 100.0,
                        "requestStart": 250.0,
                        "responseStart": 550.0,
                        "responseEnd": 650.0,
                        "duration": 550.0,
                    },
                    {
                        "name": second_resource_url,
                        "initiatorType": "script",
                        "fetchStart": 200.0,
                        "requestStart": 700.0,
                        "responseStart": 820.0,
                        "responseEnd": 900.0,
                        "duration": 700.0,
                    }
                ]
            },
        }
        profile = {
            "byte_tap": {
                "enabled": True,
                "ok": True,
                "listen_host": "127.0.0.1",
                "listen_port": 19182,
                "upstream_host": "127.0.0.1",
                "upstream_port": 19082,
                "connections": [
                    {
                        "connection_id": 7,
                        "started_epoch_ms": 1781291801870,
                        "browser_peer_port": 55222,
                        "upstream_local_port": 60123,
                        "socks_reply_tag_bind_port": 40007,
                    },
                    {
                        "connection_id": 8,
                        "started_epoch_ms": 1781291801871,
                        "browser_peer_port": 55223,
                        "upstream_local_port": 60124,
                        "socks_reply_tag_bind_port": 40008,
                    },
                ],
                "events": [],
            },
            "proxy_output_tail": [
                "2026-06-12T19:16:41Z  INFO arti::proxy::socks: timing_id=9 target_kind=hostname target_label=www.torproject.org port=443 client_peer_port=60123 conn_started_epoch_ms=1781291801871 circ_id=Circ 4.4 hop=3 stream_id=77 elapsed_ms=1 torfast socks timing stream linked",
                "2026-06-12T19:16:41Z  INFO arti::proxy::socks: timing_id=9 target_kind=hostname direction=tor_to_client_write event_index=1 elapsed_ms=400 event_epoch_ms=1781291802271 write_bytes=4096 cumulative_bytes=4096 torfast socks byte event",
                "2026-06-12T19:16:41Z  INFO arti::proxy::socks: timing_id=9 target_kind=hostname target_label=www.torproject.org port=443 client_peer_port=60123 conn_started_epoch_ms=1781291801871 circ_id=Circ 4.4 hop=3 stream_id=77 relay_ms=900 first_tor_to_client_ms=150 last_tor_to_client_ms=370 tor_to_client_bytes=4096 elapsed_ms=901 ok=true torfast socks timing relay finished",
                "2026-06-12T19:16:41Z  INFO arti::proxy::socks: timing_id=10 target_kind=hostname target_label=www.torproject.org port=443 client_peer_port=60124 conn_started_epoch_ms=1781291801872 circ_id=Circ 4.5 hop=3 stream_id=88 elapsed_ms=1 torfast socks timing stream linked",
            ],
        }
        parent_bridge_rows = [
            {
                "channel_id": 42,
                "uri": resource_url,
                "proxy": "127.0.0.1:19182",
                "socket_epoch_ms": 1781291801870.5,
            }
        ]

        stream_bridge_rows = browser_net_log_socks_stream_bridge_rows_for_run(
            profile, run, parent_bridge_rows
        )
        payload = {
            "profiles": {
                "arti_release_browser": {
                    **profile,
                    "benchmarks": {
                        "https://www.torproject.org/": {
                            "summary": {"ok": True},
                            "runs": [run],
                        }
                    },
                }
            }
        }
        resource_rows = browser_activity_tagged_stream_resource_rows(payload)
        group_rows = browser_activity_tagged_stream_group_rows(payload)
        sequence_rows = browser_activity_tagged_stream_sequence_rows(payload)
        queue_cause_rows = browser_activity_tagged_stream_queue_cause_rows(payload)
        resource_rows_by_url = {row["resource"]: row for row in resource_rows}

        self.assertEqual(len(stream_bridge_rows), 1)
        self.assertEqual(stream_bridge_rows[0]["connection_id"], 7)
        self.assertEqual(stream_bridge_rows[0]["browser_activity_tag_port"], 40007)
        self.assertEqual(stream_bridge_rows[0]["client_peer_port"], 60123)
        self.assertEqual(stream_bridge_rows[0]["timing_id"], 9)
        self.assertEqual(stream_bridge_rows[0]["stream_id"], 77)
        self.assertEqual(
            stream_bridge_rows[0]["stream_bridge_method"],
            "browser_activity_socks_reply_tag",
        )
        self.assertEqual(len(resource_rows), 2)
        self.assertEqual(resource_rows_by_url[resource_url]["resource_type"], "script")
        self.assertEqual(resource_rows_by_url[resource_url]["connection_id"], 7)
        self.assertEqual(resource_rows[0]["browser_activity_tag_port"], 40007)
        self.assertEqual(resource_rows_by_url[resource_url]["stream_id"], 77)
        self.assertEqual(
            resource_rows_by_url[resource_url]["last_tor_to_client_write_ms"],
            400.0,
        )
        self.assertEqual(
            resource_rows_by_url[resource_url][
                "last_tor_write_after_last_tor_byte_ms"
            ],
            30.0,
        )
        self.assertEqual(
            resource_rows_by_url[resource_url][
                "response_end_after_last_tor_write_ms"
            ],
            249.0,
        )
        self.assertEqual(
            resource_rows_by_url[resource_url]["fetch_to_request_ms"],
            150.0,
        )
        self.assertEqual(len(group_rows), 1)
        self.assertEqual(group_rows[0]["resources"], 2)
        self.assertEqual(group_rows[0]["queued_1000ms"], 0)
        self.assertEqual(group_rows[0]["max_fetch_to_request_ms"], 500.0)
        self.assertEqual(
            group_rows[0]["max_last_tor_write_after_last_tor_byte_ms"],
            30.0,
        )
        self.assertEqual(
            group_rows[0]["median_response_end_after_last_tor_write_ms"],
            374.0,
        )
        self.assertIn("app.js", group_rows[0]["top_resources"])
        self.assertEqual(len(sequence_rows), 2)
        sequence_rows_by_index = {
            row["sequence_index"]: row for row in sequence_rows
        }
        self.assertEqual(
            sequence_rows_by_index[1]["request_after_previous_response_ms"],
            None,
        )
        self.assertEqual(sequence_rows_by_index[2]["previous_resource"], resource_url)
        self.assertEqual(
            sequence_rows_by_index[2]["request_after_previous_response_ms"],
            50.0,
        )
        self.assertEqual(len(queue_cause_rows), 1)
        self.assertEqual(queue_cause_rows[0]["resource"], second_resource_url)
        self.assertEqual(queue_cause_rows[0]["previous_resource"], resource_url)
        self.assertEqual(
            queue_cause_rows[0]["queue_blocked_by_previous_response_ms"],
            450.0,
        )
        self.assertEqual(
            queue_cause_rows[0]["queue_blocked_by_previous_pre_request_ms"],
            50.0,
        )
        self.assertEqual(
            queue_cause_rows[0]["queue_blocked_by_previous_wait_ms"],
            300.0,
        )
        self.assertEqual(
            queue_cause_rows[0]["queue_blocked_by_previous_receive_ms"],
            100.0,
        )
        self.assertEqual(
            queue_cause_rows[0]["queue_unexplained_after_previous_ms"],
            50.0,
        )
        self.assertEqual(
            queue_cause_rows[0]["queue_cause_hint"],
            "queued behind previous response",
        )

    def test_browser_activity_tagged_connection_rows_work_without_stream_logs(
        self,
    ) -> None:
        resource_url = "https://www.torproject.org/static/js/app.js?h=1"
        second_resource_url = "https://www.torproject.org/static/js/next.js?h=1"
        run = {
            "ok": True,
            "run_index": 1,
            "browser_activity_probe": {
                "enabled": True,
                "ok": True,
                "rows": [
                    {
                        "source": "http_activity",
                        "method": "observeActivity",
                        "channel_id": 42,
                        "uri": resource_url,
                        "localAddress": "0.0.0.0",
                        "localPort": 40007,
                        "remoteAddress": "0.0.0.0",
                        "remotePort": 443,
                        "observed_epoch_ms": 1781291802000,
                    },
                    {
                        "source": "http_activity",
                        "method": "observeActivity",
                        "channel_id": 43,
                        "uri": second_resource_url,
                        "localAddress": "0.0.0.0",
                        "localPort": 40007,
                        "remoteAddress": "0.0.0.0",
                        "remotePort": 443,
                        "observed_epoch_ms": 1781291802500,
                    },
                ],
            },
            "performance_timing": {
                "time_origin_ms": 1781291801870,
                "resources": [
                    {
                        "name": resource_url,
                        "initiatorType": "script",
                        "fetchStart": 100.0,
                        "requestStart": 250.0,
                        "responseStart": 550.0,
                        "responseEnd": 650.0,
                        "duration": 550.0,
                    },
                    {
                        "name": second_resource_url,
                        "initiatorType": "script",
                        "fetchStart": 200.0,
                        "requestStart": 700.0,
                        "responseStart": 820.0,
                        "responseEnd": 900.0,
                        "duration": 700.0,
                    },
                ]
            },
        }
        profile = {
            "byte_tap": {
                "enabled": True,
                "ok": True,
                "listen_host": "127.0.0.1",
                "listen_port": 19182,
                "upstream_host": "127.0.0.1",
                "upstream_port": 19082,
                "connections": [
                    {
                        "connection_id": 7,
                        "started_epoch_ms": 1781291801870,
                        "browser_peer_port": 55222,
                        "upstream_local_port": 60123,
                        "socks_reply_tag_bind_port": 40007,
                        "socks_target_host": "www.torproject.org",
                        "socks_target_port": 443,
                    },
                    {
                        "connection_id": 8,
                        "started_epoch_ms": 1781291801871,
                        "browser_peer_port": 55223,
                        "upstream_local_port": 60124,
                        "socks_reply_tag_bind_port": 40008,
                        "socks_target_host": "example.com",
                        "socks_target_port": 443,
                    },
                ],
                "events": [
                    {
                        "connection_id": 7,
                        "direction": "proxy_to_browser",
                        "elapsed_ms": 600.0,
                        "event_epoch_ms": 1781291802470.0,
                        "stream_data_bytes": 100,
                    }
                ],
            },
            "proxy_output_tail": [],
        }
        payload = {
            "profiles": {
                "local_c_tor_browser": {
                    **profile,
                    "benchmarks": {
                        "https://www.torproject.org/": {
                            "summary": {"ok": True},
                            "runs": [run],
                        }
                    },
                }
            }
        }

        bridge_rows = browser_activity_tagged_connection_bridge_rows_for_run(
            profile, run
        )
        resource_rows = browser_activity_tagged_connection_resource_rows(payload)
        group_rows = browser_activity_tagged_connection_group_rows(payload)
        sequence_rows = browser_activity_tagged_connection_sequence_rows(payload)
        queue_cause_rows = browser_activity_tagged_connection_queue_cause_rows(payload)
        queue_cause_summary_rows = (
            browser_activity_tagged_connection_queue_cause_summary_rows(payload)
        )
        resource_rows_by_url = {row["resource"]: row for row in resource_rows}

        self.assertEqual(len(bridge_rows), 2)
        self.assertEqual({row["connection_id"] for row in bridge_rows}, {7})
        self.assertEqual(len(resource_rows), 2)
        self.assertEqual(resource_rows_by_url[resource_url]["resource_type"], "script")
        self.assertEqual(resource_rows_by_url[resource_url]["connection_id"], 7)
        self.assertEqual(
            resource_rows_by_url[resource_url]["browser_activity_tag_port"],
            40007,
        )
        self.assertEqual(
            resource_rows_by_url[resource_url]["socks_target_host"],
            "www.torproject.org",
        )
        self.assertEqual(
            resource_rows_by_url[resource_url]["fetch_to_request_ms"],
            150.0,
        )
        self.assertEqual(len(group_rows), 1)
        self.assertEqual(group_rows[0]["resources"], 2)
        self.assertEqual(group_rows[0]["queued_1000ms"], 0)
        self.assertEqual(group_rows[0]["max_fetch_to_request_ms"], 500.0)
        self.assertIn("next.js", group_rows[0]["top_resources"])
        self.assertEqual(len(sequence_rows), 2)
        sequence_rows_by_index = {
            row["sequence_index"]: row for row in sequence_rows
        }
        self.assertEqual(
            sequence_rows_by_index[1]["request_after_previous_response_ms"],
            None,
        )
        self.assertEqual(sequence_rows_by_index[2]["previous_resource"], resource_url)
        self.assertEqual(
            sequence_rows_by_index[2]["request_after_previous_response_ms"],
            50.0,
        )
        self.assertEqual(len(queue_cause_rows), 1)
        self.assertEqual(queue_cause_rows[0]["resource"], second_resource_url)
        self.assertEqual(queue_cause_rows[0]["previous_resource"], resource_url)
        self.assertEqual(
            queue_cause_rows[0]["queue_blocked_by_previous_response_ms"],
            450.0,
        )
        self.assertEqual(
            queue_cause_rows[0]["previous_response_proxy_stream_data_events"],
            1,
        )
        self.assertEqual(
            queue_cause_rows[0]["previous_response_proxy_stream_data_bytes"],
            100.0,
        )
        self.assertEqual(
            queue_cause_rows[0]["previous_response_first_proxy_data_after_request_ms"],
            350.0,
        )
        self.assertEqual(
            queue_cause_rows[0]["previous_response_end_after_last_proxy_data_ms"],
            50.0,
        )
        self.assertEqual(
            queue_cause_rows[0]["previous_receive_proxy_stream_data_events"],
            1,
        )
        self.assertEqual(
            queue_cause_rows[0]["previous_receive_proxy_stream_data_bytes"],
            100.0,
        )
        self.assertEqual(
            queue_cause_rows[0][
                "previous_receive_first_proxy_data_after_start_ms"
            ],
            50.0,
        )
        self.assertEqual(
            queue_cause_rows[0][
                "previous_receive_browser_after_last_proxy_data_ms"
            ],
            50.0,
        )
        self.assertEqual(
            queue_cause_rows[0]["queue_unexplained_after_previous_ms"],
            50.0,
        )
        self.assertEqual(
            queue_cause_rows[0]["queue_cause_hint"],
            "queued behind previous response",
        )
        self.assertEqual(len(queue_cause_summary_rows), 1)
        self.assertEqual(queue_cause_summary_rows[0]["rows"], 1)
        self.assertEqual(queue_cause_summary_rows[0]["queued_1000ms"], 0)
        self.assertEqual(
            queue_cause_summary_rows[0]["total_fetch_to_request_ms"],
            500.0,
        )
        self.assertEqual(
            queue_cause_summary_rows[0][
                "total_queue_blocked_by_previous_response_ms"
            ],
            450.0,
        )
        self.assertEqual(
            queue_cause_summary_rows[0][
                "total_queue_blocked_by_previous_pre_request_ms"
            ],
            50.0,
        )
        self.assertEqual(
            queue_cause_summary_rows[0]["total_queue_blocked_by_previous_wait_ms"],
            300.0,
        )
        self.assertEqual(
            queue_cause_summary_rows[0]["total_queue_blocked_by_previous_receive_ms"],
            100.0,
        )
        self.assertEqual(
            queue_cause_summary_rows[0]["previous_response_rows_with_proxy_data"],
            1,
        )
        self.assertEqual(
            queue_cause_summary_rows[0][
                "total_previous_response_proxy_stream_data_bytes"
            ],
            100.0,
        )
        self.assertEqual(
            queue_cause_summary_rows[0][
                "median_previous_response_end_after_last_proxy_data_ms"
            ],
            50.0,
        )
        self.assertEqual(
            queue_cause_summary_rows[0]["previous_receive_rows_with_proxy_data"],
            1,
        )
        self.assertEqual(
            queue_cause_summary_rows[0][
                "total_previous_receive_proxy_stream_data_bytes"
            ],
            100.0,
        )
        self.assertEqual(
            queue_cause_summary_rows[0][
                "median_previous_receive_browser_after_last_proxy_data_ms"
            ],
            50.0,
        )
        self.assertEqual(
            queue_cause_summary_rows[0]["blocked_by_previous_response_share_pct"],
            90.0,
        )

    def test_run_arti_default_health_aware_min_assigned_is_defined(self) -> None:
        class FakeProc:
            returncode = 0

            def poll(self) -> int:
                return 0

        with tempfile.TemporaryDirectory() as tmp:
            with (
                patch("run_browser_compare.start_arti", return_value=(FakeProc(), queue.Queue())),
                patch(
                    "run_browser_compare.wait_for_line",
                    return_value={"ok": False, "error": "test boot failed"},
                ),
            ):
                result = run_arti(
                    arti_bin=Path("/tmp/fake-arti"),
                    port=19082,
                    output_dir=Path(tmp),
                    browser_bin=Path("/tmp/fake-browser"),
                    targets=[],
                    runs=0,
                    timeout=1.0,
                    window_size="1000,1000",
                )

        self.assertEqual(result["boot"], {"ok": False, "error": "test boot failed"})
        self.assertIsNone(result["arti_exit_select_health_aware_min_assigned"])

    def test_cleanup_named_paths_removes_directories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "data"
            path.mkdir()

            artifacts = cleanup_named_paths({"data_dir": path})

            self.assertFalse(path.exists())
            self.assertEqual(artifacts["removed"], ["data_dir"])
            self.assertEqual(artifacts["errors"], [])

    def test_detects_arti_preemptive_recheck_seconds(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "crates" / "tor-circmgr" / "src"
            source.mkdir(parents=True)
            (source / "lib.rs").write_text(
                "let base_delay = Duration::from_secs(1);",
                encoding="utf-8",
            )
            (source / "config.rs").write_text(
                """
fn default_preemptive_min_exit_circs_for_port() -> usize {
    3
}
""",
                encoding="utf-8",
            )
            proxy = root / "crates" / "arti" / "src" / "proxy"
            proxy.mkdir(parents=True)
            (proxy / "socks.rs").write_text(
                "prefs.optimistic(); TORFAST_SOCKS_CONNECT_SOFT_TIMEOUT_MS "
                "TORFAST_SOCKS_CONNECT_HEDGE_MS TORFAST_SOCKS_RELAY_BYTE_TIMING "
                "TORFAST_SOCKS_TOR_TO_CLIENT_COALESCE_BYTES",
                encoding="utf-8",
            )
            (root / "crates" / "arti" / "src" / "proxy.rs").write_text(
                'const TORFAST_APP_STREAM_BUF_LEN_ENV: &str = "TORFAST_APP_STREAM_BUF_LEN";',
                encoding="utf-8",
            )
            reactor = root / "crates" / "tor-proto" / "src" / "client" / "reactor"
            reactor.mkdir(parents=True)
            (reactor / "circuit.rs").write_text(
                "TORFAST_CIRCUIT_CONGESTION_LOG TORFAST_STREAM_SCHEDULER_LOG "
                'const TORFAST_STREAM_SCHEDULER_BURST_ENV: &str = "TORFAST_STREAM_SCHEDULER_BURST"; '
                "const TORFAST_STREAM_SCHEDULER_BURST_DEFAULT: usize = 1;",
                encoding="utf-8",
            )
            circuit = root / "crates" / "tor-proto" / "src" / "circuit"
            circuit.mkdir(parents=True)
            (circuit / "circhop.rs").write_text(
                "TORFAST_STREAM_LIFECYCLE_LOG",
                encoding="utf-8",
            )
            data_stream = (
                root / "crates" / "tor-proto" / "src" / "client" / "stream"
            )
            data_stream.mkdir(parents=True)
            (data_stream / "data.rs").write_text(
                "TORFAST_STREAM_READY_DATA_COALESCE_BYTES",
                encoding="utf-8",
            )
            impls = root / "crates" / "tor-circmgr" / "src" / "impls.rs"
            impls.write_text(
                """
	const TORFAST_DEFAULT_EXIT_SELECT_PARALLELISM: usize = 1;
	const TORFAST_DEFAULT_EXIT_LAUNCH_PARALLELISM: usize = 1;
	TargetTunnelUsage::Exit { .. } => torfast_exit_select_parallelism(),
	""",
                encoding="utf-8",
            )
            (source / "mgr.rs").write_text(
                "TORFAST_EXIT_PENDING_HEDGE_MS TORFAST_EXIT_SELECT_LOAD_AWARE "
                "TORFAST_EXIT_SELECT_HEALTH_AWARE "
                "TORFAST_EXIT_SELECT_AVOID_BAD_HEALTH "
                "TORFAST_EXIT_SELECT_AVOID_BAD_HEALTH_UNKNOWN_FALLBACK "
                "TORFAST_EXIT_SELECT_BAD_HEALTH_ACTIVE_NO_DATA_MS "
                "TORFAST_EXIT_SELECT_HEALTH_MIN_MOVE_SCORE_BPS "
                "TORFAST_EXIT_SELECT_MIN_ASSIGNMENT_SPREAD "
                "TORFAST_EXIT_SELECT_HEALTHY_OVER_COLD_MIN_ASSIGNED "
                "TORFAST_EXIT_SELECT_HEALTHY_OVER_COLD_GUARD_ONLY_MIN_ASSIGNED "
                "TORFAST_EXIT_SELECT_LOW_LOG_CONTEXT "
                "if low_log_selection_context { "
                "TORFAST_EXIT_SAME_ISOLATION_TARGET "
                "const TORFAST_EXIT_SAME_ISOLATION_TARGET_DEFAULT: usize = 2; "
                "TORFAST_EXIT_SAME_ISOLATION_OTHER_ISOLATION_MIN "
                "TORFAST_EXIT_SAME_ISOLATION_MIN_ASSIGNED_STREAMS "
                "TORFAST_EXIT_SAME_ISOLATION_PENDING_WAIT_MS "
                "TORFAST_EXIT_SAME_ISOLATION_PREWARM_FIRST_STREAM "
                "TORFAST_EXIT_SAME_ISOLATION_REQUIRE_BAD_HEALTH "
                "TORFAST_EXIT_SELECT_PREFER_COLD_SAME_ISOLATION "
                "const TORFAST_EXIT_SELECT_GUARDED_SAME_ISOLATION_ACTIVE_CAP_DEFAULT: u64 = 2; "
                "fn torfast_exit_select_load_aware() -> bool { torfast_env_flag(std::env::var(TORFAST_EXIT_SELECT_LOAD_AWARE_ENV).ok(), true) } "
                "fn torfast_exit_select_health_aware() -> bool { torfast_env_flag(std::env::var(TORFAST_EXIT_SELECT_HEALTH_AWARE_ENV).ok(), true) } "
                "fn torfast_exit_select_avoid_bad_health() -> bool { torfast_env_flag(std::env::var(TORFAST_EXIT_SELECT_AVOID_BAD_HEALTH_ENV).ok(), true) } "
                "fn torfast_exit_select_prefer_cold_same_isolation() -> bool { torfast_env_flag(std::env::var(TORFAST_EXIT_SELECT_PREFER_COLD_SAME_ISOLATION_ENV).ok(), true) } ",
                encoding="utf-8",
            )
            (source / "hspool.rs").write_text(
                'const TORFAST_HSPOOL_BACKGROUND_START_DELAY_MS_ENV: &str = "TORFAST_HSPOOL_BACKGROUND_START_DELAY_MS"; '
                "const TORFAST_HSPOOL_BACKGROUND_START_DELAY_DEFAULT_MS: u64 = 1_000; "
                'const TORFAST_HSPOOL_LAUNCH_PARALLELISM_ENV: &str = "TORFAST_HSPOOL_LAUNCH_PARALLELISM"; '
                "const TORFAST_HSPOOL_LAUNCH_PARALLELISM_DEFAULT: usize = 1; "
                'const TORFAST_HSPOOL_ON_DEMAND_POOL_GRACE_MS_ENV: &str = "TORFAST_HSPOOL_ON_DEMAND_POOL_GRACE_MS"; '
                "const TORFAST_HSPOOL_ON_DEMAND_POOL_GRACE_DEFAULT_MS: u64 = 0; "
                'const TORFAST_HSPOOL_ON_DEMAND_POOL_RACE_MS_ENV: &str = "TORFAST_HSPOOL_ON_DEMAND_POOL_RACE_MS"; '
                "const TORFAST_HSPOOL_ON_DEMAND_POOL_RACE_DEFAULT_MS: u64 = 0; ",
                encoding="utf-8",
            )
            hspool_mod = source / "hspool"
            hspool_mod.mkdir()
            (hspool_mod / "pool.rs").write_text(
                "const DEFAULT_GUARDED_STEM_TARGET: usize = 2; "
                'const TORFAST_HSPOOL_GUARDED_STEM_TARGET_ENV: &str = "TORFAST_HSPOOL_GUARDED_STEM_TARGET"; ',
                encoding="utf-8",
            )
            hsclient = root / "crates" / "tor-hsclient" / "src"
            hsclient.mkdir(parents=True)
            (hsclient / "connect.rs").write_text(
                'const TORFAST_HS_INTRO_REND_OVERLAP_ENV: &str = "TORFAST_HS_INTRO_REND_OVERLAP"; '
                'const TORFAST_HS_REND_PREBUILD_BEFORE_DESC_ENV: &str = "TORFAST_HS_REND_PREBUILD_BEFORE_DESC"; '
                'const TORFAST_HS_DESC_SHARED_CACHE_ENV: &str = "TORFAST_HS_DESC_SHARED_CACHE"; '
                'const TORFAST_HS_INTRO_CIRCUIT_HEDGE_MS_ENV: &str = "TORFAST_HS_INTRO_CIRCUIT_HEDGE_MS";',
                encoding="utf-8",
            )

            tweaks = detect_source_tweaks(root)

            self.assertEqual(tweaks["arti_preemptive_recheck_seconds"], 1)
            self.assertEqual(tweaks["arti_preemptive_min_exit_circs_for_port"], 3)
            self.assertTrue(tweaks["arti_socks_connect_optimistic"])
            self.assertEqual(tweaks["arti_exit_select_parallelism"], 1)
            self.assertEqual(tweaks["arti_exit_launch_parallelism"], 1)
            self.assertTrue(tweaks["arti_hspool_launch_parallelism_lab"])
            self.assertEqual(tweaks["arti_hspool_launch_parallelism_default"], 1)
            self.assertTrue(tweaks["arti_hspool_background_start_delay_lab"])
            self.assertEqual(tweaks["arti_hspool_background_start_delay_default_ms"], 1000)
            self.assertTrue(tweaks["arti_hspool_on_demand_grace_lab"])
            self.assertEqual(tweaks["arti_hspool_on_demand_grace_default_ms"], 0)
            self.assertTrue(tweaks["arti_hspool_on_demand_race_lab"])
            self.assertEqual(tweaks["arti_hspool_on_demand_race_default_ms"], 0)
            self.assertTrue(tweaks["arti_hspool_guarded_stem_target_lab"])
            self.assertEqual(tweaks["arti_hspool_guarded_stem_target_default"], 2)
            self.assertTrue(tweaks["arti_hs_intro_rend_overlap_lab"])
            self.assertTrue(tweaks["arti_hs_rend_prebuild_before_desc_lab"])
            self.assertTrue(tweaks["arti_hs_desc_shared_cache_lab"])
            self.assertTrue(tweaks["arti_hs_intro_circuit_hedge_lab"])
            self.assertTrue(tweaks["arti_socks_connect_soft_timeout_lab"])
            self.assertTrue(tweaks["arti_socks_connect_hedge_lab"])
            self.assertTrue(tweaks["arti_socks_relay_byte_timing_lab"])
            self.assertTrue(tweaks["arti_socks_tor_to_client_coalesce_lab"])
            self.assertTrue(tweaks["arti_stream_ready_data_coalesce_lab"])
            self.assertTrue(tweaks["arti_proxy_app_stream_buffer_lab"])
            self.assertTrue(tweaks["arti_circuit_congestion_log_lab"])
            self.assertTrue(tweaks["arti_stream_scheduler_log_lab"])
            self.assertTrue(tweaks["arti_stream_scheduler_burst_lab"])
            self.assertEqual(tweaks["arti_stream_scheduler_burst_default"], 1)
            self.assertTrue(tweaks["arti_stream_lifecycle_log_lab"])
            self.assertTrue(tweaks["arti_exit_pending_hedge_lab"])
            self.assertTrue(tweaks["arti_exit_select_load_aware_lab"])
            self.assertTrue(tweaks["arti_exit_select_load_aware_default"])
            self.assertTrue(tweaks["arti_exit_select_health_aware_lab"])
            self.assertTrue(tweaks["arti_exit_select_health_aware_default"])
            self.assertTrue(tweaks["arti_exit_select_avoid_bad_health_lab"])
            self.assertTrue(tweaks["arti_exit_select_avoid_bad_health_default"])
            self.assertTrue(
                tweaks["arti_exit_select_avoid_bad_health_unknown_fallback_lab"]
            )
            self.assertTrue(tweaks["arti_exit_select_bad_health_active_no_data_lab"])
            self.assertTrue(tweaks["arti_exit_select_health_min_move_score_lab"])
            self.assertTrue(tweaks["arti_exit_select_min_assignment_spread_lab"])
            self.assertTrue(tweaks["arti_exit_select_healthy_over_cold_lab"])
            self.assertTrue(
                tweaks["arti_exit_select_healthy_over_cold_guard_only_lab"]
            )
            self.assertTrue(tweaks["arti_exit_select_low_log_context_lab"])
            self.assertTrue(tweaks["arti_exit_select_low_log_info_unconditional"])
            self.assertTrue(tweaks["arti_exit_same_isolation_target_lab"])
            self.assertEqual(tweaks["arti_exit_same_isolation_target_default"], 2)
            self.assertTrue(
                tweaks["arti_exit_same_isolation_other_isolation_min_lab"]
            )
            self.assertTrue(tweaks["arti_exit_same_isolation_min_assigned_streams_lab"])
            self.assertTrue(
                tweaks["arti_exit_same_isolation_prewarm_first_stream_lab"]
            )
            self.assertTrue(tweaks["arti_exit_same_isolation_pending_wait_lab"])
            self.assertTrue(tweaks["arti_exit_same_isolation_require_bad_health_lab"])
            self.assertTrue(
                tweaks["arti_exit_select_prefer_cold_same_isolation_default"]
            )
            self.assertEqual(
                tweaks["arti_exit_select_guarded_same_isolation_active_cap_default"],
                2,
            )

    def test_effective_arti_exit_selector_metadata_uses_source_defaults(self) -> None:
        metadata = effective_arti_exit_selector_metadata(
            requested_load_aware=False,
            requested_health_aware=False,
            requested_avoid_bad_health=False,
            requested_avoid_bad_health_unknown_fallback=False,
            requested_same_isolation_target=None,
            requested_prefer_cold_same_isolation=False,
            requested_max_active_streams=None,
            source_tweaks={
                "arti_exit_select_load_aware_default": True,
                "arti_exit_select_health_aware_default": True,
                "arti_exit_select_avoid_bad_health_default": True,
                "arti_exit_same_isolation_target_default": 2,
                "arti_exit_select_prefer_cold_same_isolation_default": True,
                "arti_exit_select_guarded_same_isolation_active_cap_default": 2,
            },
        )

        self.assertTrue(metadata["arti_exit_select_load_aware_effective"])
        self.assertTrue(metadata["arti_exit_select_health_aware_effective"])
        self.assertTrue(metadata["arti_exit_select_avoid_bad_health_effective"])
        self.assertEqual(metadata["arti_exit_same_isolation_target_effective"], 2)
        self.assertTrue(
            metadata["arti_exit_select_prefer_cold_same_isolation_effective"]
        )
        self.assertEqual(metadata["arti_exit_select_max_active_streams_effective"], 2)

        explicit = effective_arti_exit_selector_metadata(
            requested_load_aware=True,
            requested_health_aware=True,
            requested_avoid_bad_health=True,
            requested_avoid_bad_health_unknown_fallback=True,
            requested_same_isolation_target=3,
            requested_prefer_cold_same_isolation=True,
            requested_max_active_streams=1,
            source_tweaks=None,
        )

        self.assertTrue(explicit["arti_exit_select_load_aware_effective"])
        self.assertTrue(explicit["arti_exit_select_health_aware_effective"])
        self.assertTrue(explicit["arti_exit_select_avoid_bad_health_effective"])
        self.assertTrue(
            explicit["arti_exit_select_avoid_bad_health_unknown_fallback_effective"]
        )
        self.assertEqual(explicit["arti_exit_same_isolation_target_effective"], 3)
        self.assertTrue(
            explicit["arti_exit_select_prefer_cold_same_isolation_effective"]
        )
        self.assertEqual(explicit["arti_exit_select_max_active_streams_effective"], 1)

    def test_effective_arti_exit_selector_metadata_health_aware_implies_load_aware(
        self,
    ) -> None:
        metadata = effective_arti_exit_selector_metadata(
            requested_load_aware=False,
            requested_health_aware=True,
            requested_avoid_bad_health=False,
            requested_avoid_bad_health_unknown_fallback=False,
            requested_same_isolation_target=2,
            requested_prefer_cold_same_isolation=True,
            requested_max_active_streams=None,
            source_tweaks=None,
        )

        self.assertTrue(metadata["arti_exit_select_load_aware_effective"])
        self.assertTrue(metadata["arti_exit_select_health_aware_effective"])
        self.assertTrue(
            metadata["arti_exit_select_prefer_cold_same_isolation_effective"]
        )

    def test_c_tor_torrc_quality_requires_socks_auth_isolation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            torrc = Path(tmp) / "torrc"
            torrc.write_text(
                f"SocksPort 127.0.0.1:19080 {' '.join(C_TOR_SOCKS_FLAGS)}\n",
                encoding="utf-8",
            )

            quality = read_torrc_quality(torrc)

            self.assertTrue(quality["isolate_socks_auth"])

    def test_interleaved_schedule_rotates_profiles(self) -> None:
        calls = []

        def fake_browser_once(**kwargs):
            calls.append((kwargs["port"], kwargs["run_index"]))
            return {
                "ok": True,
                "elapsed_ms": 1000 + len(calls),
                "load_ms": 800 + len(calls),
                "screenshot": {"bytes": 100},
                "performance_timing": {},
            }

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            browser = root / "firefox"
            bundled = root / "bundled-tor"
            local = root / "tor"
            arti = root / "arti"
            for path in (browser, bundled, local, arti):
                path.write_text("", encoding="utf-8")

            with (
                patch(
                    "run_browser_compare.warmup_proxy",
                    return_value={"ok": True, "seconds": 0.1},
                ),
                patch(
                    "run_browser_compare.start_proxy_for_spec",
                    return_value=(object(), queue.Queue()),
                ),
                patch(
                    "run_browser_compare.wait_for_line",
                    return_value={"ok": True, "seconds": 0.2},
                ),
                patch("run_browser_compare.stop_process"),
                patch("run_browser_compare.read_torrc_quality", return_value={}),
                patch("run_browser_compare.run_browser_once", side_effect=fake_browser_once),
            ):
                profiles = run_interleaved_profiles(
                    bundled_tor_bin=bundled,
                    tor_bin=local,
                    arti_bin=arti,
                    ports={
                        "bundled_c_tor_browser": 19080,
                        "local_c_tor_browser": 19081,
                        "arti_release_browser": 19082,
                    },
                    output_dir=root / "out",
                    browser_bin=browser,
                    targets=["https://check.torproject.org/"],
                    runs=2,
                    timeout=1.0,
                    window_size="1000,1000",
                    warm_cache=True,
                )

        self.assertEqual(
            calls,
            [
                (19080, 1),
                (19081, 1),
                (19082, 1),
                (19081, 2),
                (19082, 2),
                (19080, 2),
            ],
        )
        self.assertTrue(
            profiles["arti_release_browser"]["benchmarks"][
                "https://check.torproject.org/"
            ]["summary"]["ok"]
        )

    def test_interleaved_schedule_can_add_extra_arti_ab_profile(self) -> None:
        calls = []

        def fake_browser_once(**kwargs):
            calls.append((kwargs["port"], kwargs["run_index"]))
            return {
                "ok": True,
                "elapsed_ms": 1000 + len(calls),
                "load_ms": 800 + len(calls),
                "screenshot": {"bytes": 100},
                "performance_timing": {},
            }

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            browser = root / "firefox"
            bundled = root / "bundled-tor"
            local = root / "tor"
            arti = root / "arti"
            for path in (browser, bundled, local, arti):
                path.write_text("", encoding="utf-8")

            with (
                patch(
                    "run_browser_compare.warmup_proxy",
                    return_value={"ok": True, "seconds": 0.1},
                ),
                patch(
                    "run_browser_compare.start_proxy_for_spec",
                    return_value=(object(), queue.Queue()),
                ),
                patch(
                    "run_browser_compare.wait_for_line",
                    return_value={"ok": True, "seconds": 0.2},
                ),
                patch("run_browser_compare.stop_process"),
                patch("run_browser_compare.read_torrc_quality", return_value={}),
                patch("run_browser_compare.run_browser_once", side_effect=fake_browser_once),
            ):
                profiles = run_interleaved_profiles(
                    bundled_tor_bin=bundled,
                    tor_bin=local,
                    arti_bin=arti,
                    ports={
                        "bundled_c_tor_browser": 19080,
                        "local_c_tor_browser": 19081,
                        "arti_release_browser": 19082,
                    },
                    output_dir=root / "out",
                    browser_bin=browser,
                    targets=["https://check.torproject.org/"],
                    runs=1,
                    timeout=1.0,
                    window_size="1000,1000",
                    warm_cache=True,
                    arti_exit_select_parallelism=3,
                    arti_min_exit_circs_for_port=3,
                    arti_socks_connect_soft_timeout_ms=5000,
                    arti_socks_connect_soft_timeout_attempts=2,
                    arti_dirclient_read_timeout_ms=8000,
                    arti_exit_select_health_min_move_score_bps=32000,
                    arti_exit_select_bad_health_hedge_ms=750,
                    arti_exit_same_isolation_target=2,
                    arti_exit_same_isolation_require_bad_health=True,
                    arti_exit_same_isolation_min_assigned_streams=1,
                    arti_exit_same_isolation_pending_wait_ms=800,
                    arti_exit_same_isolation_prewarm_first_stream=True,
                    arti_hs_rend_prebuild_before_desc=True,
                    arti_exit_select_prefer_cold_same_isolation=True,
                    extra_arti_exit_select_parallelism=[1],
                    extra_arti_hspool_launch_parallelism=[2],
                    extra_arti_hspool_background_start_delay_ms=[0],
                    extra_arti_hspool_guarded_stem_target=[6],
                    extra_arti_hspool_guarded_stem_target_defer_post_boot=[4],
                    extra_arti_hspool_on_demand_grace_ms=[50],
                    extra_arti_hspool_on_demand_race_ms=[75],
                    extra_arti_hs_intro_rend_overlap=True,
                    extra_arti_hs_rend_prebuild_before_desc=True,
                    extra_arti_hs_desc_shared_cache=True,
                    extra_arti_hs_intro_circuit_hedge_ms=[1500],
                    extra_arti_proxy_buffer_size=["1 MB"],
                    extra_arti_socks_connect_soft_timeout_ms=[1500],
                    extra_arti_socks_connect_soft_timeout_attempts=[3],
                    extra_arti_socks_connect_soft_timeout_combos=[(5000, 3)],
                    extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_partial_retry_chunking_socks_connect_hedge_ms=[
                        500
                    ],
                    extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_partial_retry_chunking_hs_rend_prebuild_before_desc=True,
                    extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_partial_retry_chunking_socks_connect_soft_timeout_combos=[
                        (5000, 3)
                    ],
                    extra_arti_socks_connect_soft_timeout_pending_hedge_combos=[
                        (5000, 3, 1500)
                    ],
                    extra_arti_socks_no_tor_byte_relay_timeout_ms=[5000],
                    extra_arti_socks_partial_relay_idle_timeout_ms=[4000],
                    extra_arti_dirclient_read_timeout_ms=[8000],
                    extra_arti_dir_microdesc_early_usable_notify=True,
                    extra_arti_dir_microdesc_source_spread_pending_spread_early_usable=True,
                    extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware=(
                        True
                    ),
                    extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_no_dir_bad_health_replacement=(
                        True
                    ),
                    extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_bad_health_replacement_suppress_gap_ms=[
                        5000
                    ],
                    extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_bad_health_replacement_gate_combos=[
                        (5000, 5, 3)
                    ],
                    extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_early_retry_on_partial=(
                        True
                    ),
                    extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_partial_retry_chunking=(
                        True
                    ),
                    extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_partial_retry_chunking_bad_health_replacement_gate_combos=[
                        (5000, 5, 3)
                    ],
                    extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_partial_retry_chunking=(
                        True
                    ),
                    extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_partial_retry_chunking_max_active_streams=[
                        2
                    ],
                    extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_partial_retry_chunking_hs_rend_prebuild_before_desc=(
                        True
                    ),
                    extra_arti_dir_microdesc_source_spread_pending_spread=True,
                    extra_arti_dir_microdesc_retry_ids_per_request=[250],
                    extra_arti_exit_select_load_aware=True,
                    extra_arti_exit_select_health_aware=True,
                    extra_arti_exit_select_health_min_move_score_bps=[16000],
                    extra_arti_exit_select_avoid_bad_health=True,
                    extra_arti_exit_select_health_aware_avoid_bad_health=True,
                    extra_arti_exit_select_health_aware_avoid_bad_health_same_isolation_target=[
                        2
                    ],
                    extra_arti_exit_select_health_aware_same_isolation_prefer_cold_target=[
                        2
                    ],
                    extra_arti_exit_select_prefer_cold_same_isolation_target=[2],
                    extra_arti_exit_select_prefer_cold_same_isolation_active_cap=[
                        (2, 1)
                    ],
                    extra_arti_exit_select_prefer_cold_same_isolation_prewarm_target=[
                        2
                    ],
                    extra_arti_exit_select_health_aware_same_isolation_prefer_cold_prewarm_pending_wait=[
                        (2, 800)
                    ],
                    extra_arti_exit_select_avoid_bad_health_unknown_fallback_prefer_cold_same_isolation_target=[
                        2
                    ],
                    extra_arti_exit_select_min_assignment_spread=[2],
                    extra_arti_exit_same_isolation_target=[2],
                    extra_arti_exit_same_isolation_other_isolation_pressure=[
                        (2, 3)
                    ],
                    extra_arti_exit_select_prefer_cold_same_isolation_other_isolation_pressure=[
                        (2, 3)
                    ],
                    extra_arti_exit_load_aware_same_isolation_target=[2],
                    extra_arti_exit_same_isolation_prewarm_target=[2],
                    extra_arti_exit_load_aware_same_isolation_prewarm_target=[2],
                    extra_arti_exit_health_aware_same_isolation_prewarm_target=[
                        2
                    ],
                    extra_arti_exit_select_health_min_move_score_same_isolation_pending_wait=[
                        (2, 16000, 800)
                    ],
                    extra_arti_exit_select_bad_health_hedge_ms=[600],
                    extra_arti_port_start=19083,
                )

        self.assertEqual(
            calls,
            [(port, 1) for port in range(19080, 19141)],
        )
        self.assertEqual(
            profiles["arti_release_browser"]["arti_exit_select_parallelism_override"],
            3,
        )
        self.assertEqual(
            profiles["arti_release_browser"][
                "arti_min_exit_circs_for_port_override"
            ],
            3,
        )
        self.assertEqual(
            profiles["arti_release_browser"]["arti_socks_connect_soft_timeout_ms"],
            5000,
        )
        self.assertEqual(
            profiles["arti_release_browser"]["arti_dirclient_read_timeout_ms"],
            8000,
        )
        self.assertEqual(
            profiles["arti_release_browser"][
                "arti_socks_connect_soft_timeout_attempts"
            ],
            2,
        )
        self.assertEqual(
            profiles["arti_release_browser"]["arti_exit_select_bad_health_hedge_ms"],
            750,
        )
        self.assertFalse(
            profiles["arti_release_browser"]["arti_exit_select_avoid_bad_health"]
        )
        self.assertTrue(
            profiles["arti_release_browser"][
                "arti_exit_same_isolation_require_bad_health"
            ]
        )
        self.assertEqual(
            profiles["arti_release_browser"][
                "arti_exit_same_isolation_min_assigned_streams"
            ],
            1,
        )
        self.assertEqual(
            profiles["arti_release_browser"]["arti_exit_same_isolation_target"],
            2,
        )
        self.assertTrue(
            profiles["arti_release_browser"][
                "arti_exit_same_isolation_prewarm_first_stream"
            ]
        )
        self.assertTrue(
            profiles["arti_release_browser"][
                "arti_hs_rend_prebuild_before_desc"
            ]
        )
        self.assertTrue(
            profiles["arti_release_browser"][
                "arti_exit_select_prefer_cold_same_isolation"
            ]
        )
        for profile_name in (
            "arti_release_browser_mdsrcspreadpendingearlyusable",
            "arti_release_browser_mdsrcspreadpendingearlyusable_loadaware_partialretrychunk",
            "arti_release_browser_mdsrcspreadpendingearlyusable_loadaware_partialretrychunk_connecthedge500ms",
            "arti_release_browser_mdsrcspreadpendingearlyusable_partialretrychunk",
        ):
            with self.subTest(profile=profile_name):
                self.assertEqual(
                    profiles[profile_name]["arti_exit_same_isolation_target"], 2
                )
                self.assertTrue(
                    profiles[profile_name][
                        "arti_exit_same_isolation_require_bad_health"
                    ]
                )
                self.assertEqual(
                    profiles[profile_name][
                        "arti_exit_same_isolation_min_assigned_streams"
                    ],
                    1,
                )
                self.assertEqual(
                    profiles[profile_name][
                        "arti_exit_same_isolation_pending_wait_ms"
                    ],
                    800,
                )
                self.assertTrue(
                    profiles[profile_name][
                        "arti_exit_same_isolation_prewarm_first_stream"
                    ]
                )
                self.assertTrue(
                    profiles[profile_name][
                        "arti_exit_select_prefer_cold_same_isolation"
                    ]
                )
        self.assertEqual(
            profiles["arti_release_browser_exit1"][
                "arti_exit_select_parallelism_override"
            ],
            1,
        )
        self.assertEqual(
            profiles["arti_release_browser_exit1"][
                "arti_min_exit_circs_for_port_override"
            ],
            3,
        )
        self.assertEqual(
            profiles["arti_release_browser_hspoollaunch2"][
                "arti_hspool_launch_parallelism"
            ],
            2,
        )
        self.assertEqual(
            profiles["arti_release_browser_hspoolstart0ms"][
                "arti_hspool_background_start_delay_ms"
            ],
            0,
        )
        self.assertEqual(
            profiles["arti_release_browser_hspoolguarded6"][
                "arti_hspool_guarded_stem_target"
            ],
            6,
        )
        self.assertEqual(
            profiles["arti_release_browser_hspoolguarded4_deferpostboot"][
                "arti_hspool_guarded_stem_target"
            ],
            4,
        )
        self.assertTrue(
            profiles["arti_release_browser_hspoolguarded4_deferpostboot"][
                "arti_hspool_guarded_stem_target_defer_post_boot"
            ]
        )
        self.assertEqual(
            profiles["arti_release_browser_hspoolgrace50ms"][
                "arti_hspool_on_demand_grace_ms"
            ],
            50,
        )
        self.assertEqual(
            profiles["arti_release_browser_hspoolrace75ms"][
                "arti_hspool_on_demand_race_ms"
            ],
            75,
        )
        self.assertTrue(
            profiles["arti_release_browser_hsintrooverlap"][
                "arti_hs_intro_rend_overlap"
            ]
        )
        self.assertTrue(
            profiles["arti_release_browser_hsrendpredesc"][
                "arti_hs_rend_prebuild_before_desc"
            ]
        )
        self.assertTrue(
            profiles["arti_release_browser_hsdescshare"][
                "arti_hs_desc_shared_cache"
            ]
        )
        self.assertEqual(
            profiles["arti_release_browser_hsintrohedge1500ms"][
                "arti_hs_intro_circuit_hedge_ms"
            ],
            1500,
        )
        self.assertEqual(
            profiles["arti_release_browser_exit1"]["arti_socks_connect_soft_timeout_ms"],
            5000,
        )
        self.assertEqual(
            profiles["arti_release_browser_exit1"][
                "arti_socks_connect_soft_timeout_attempts"
            ],
            2,
        )
        self.assertEqual(
            profiles["arti_release_browser_exit1"]["arti_dirclient_read_timeout_ms"],
            8000,
        )
        self.assertTrue(
            profiles["arti_release_browser_mdearlyusable"][
                "arti_dir_microdesc_early_usable_notify"
            ]
        )
        self.assertTrue(
            profiles["arti_release_browser_mdsrcspreadpendingearlyusable"][
                "arti_dir_microdesc_early_usable_notify"
            ]
        )
        self.assertTrue(
            profiles["arti_release_browser_mdsrcspreadpendingearlyusable"][
                "arti_dir_microdesc_source_spread"
            ]
        )
        self.assertTrue(
            profiles["arti_release_browser_mdsrcspreadpendingearlyusable"][
                "arti_dir_microdesc_pending_spread"
            ]
        )
        load_aware_src_spread = profiles[
            "arti_release_browser_mdsrcspreadpendingearlyusable_loadaware"
        ]
        self.assertTrue(
            load_aware_src_spread["arti_dir_microdesc_early_usable_notify"]
        )
        self.assertTrue(load_aware_src_spread["arti_dir_microdesc_source_spread"])
        self.assertTrue(load_aware_src_spread["arti_dir_microdesc_pending_spread"])
        self.assertTrue(load_aware_src_spread["arti_exit_select_load_aware"])
        self.assertFalse(load_aware_src_spread["arti_exit_select_health_aware"])
        self.assertFalse(
            load_aware_src_spread[
                "arti_dir_microdesc_disable_bad_health_replacement"
            ]
        )
        load_aware_no_dir_bad_health_replacement = profiles[
            "arti_release_browser_"
            "mdsrcspreadpendingearlyusable_loadaware_"
            "nodirmicrodescbadhealthreplace"
        ]
        self.assertTrue(
            load_aware_no_dir_bad_health_replacement[
                "arti_dir_microdesc_early_usable_notify"
            ]
        )
        self.assertTrue(
            load_aware_no_dir_bad_health_replacement[
                "arti_dir_microdesc_disable_bad_health_replacement"
            ]
        )
        self.assertTrue(
            load_aware_no_dir_bad_health_replacement[
                "arti_dir_microdesc_source_spread"
            ]
        )
        self.assertTrue(
            load_aware_no_dir_bad_health_replacement[
                "arti_dir_microdesc_pending_spread"
            ]
        )
        self.assertTrue(
            load_aware_no_dir_bad_health_replacement["arti_exit_select_load_aware"]
        )
        self.assertFalse(
            load_aware_no_dir_bad_health_replacement[
                "arti_exit_select_health_aware"
            ]
        )
        load_aware_bad_health_gap = profiles[
            "arti_release_browser_"
            "mdsrcspreadpendingearlyusable_loadaware_badhealthgap5000ms"
        ]
        self.assertTrue(
            load_aware_bad_health_gap["arti_dir_microdesc_early_usable_notify"]
        )
        self.assertEqual(
            load_aware_bad_health_gap[
                "arti_dir_microdesc_bad_health_replacement_suppress_gap_ms"
            ],
            5000,
        )
        self.assertTrue(
            load_aware_bad_health_gap["arti_dir_microdesc_source_spread"]
        )
        self.assertTrue(
            load_aware_bad_health_gap["arti_dir_microdesc_pending_spread"]
        )
        self.assertTrue(load_aware_bad_health_gap["arti_exit_select_load_aware"])
        self.assertFalse(
            load_aware_bad_health_gap["arti_exit_select_health_aware"]
        )
        load_aware_bad_health_gate = profiles[
            "arti_release_browser_"
            "mdsrcspreadpendingearlyusable_loadaware_"
            "badhealthgate5000ms_assigned5_active3"
        ]
        self.assertTrue(
            load_aware_bad_health_gate["arti_dir_microdesc_early_usable_notify"]
        )
        self.assertEqual(
            load_aware_bad_health_gate[
                "arti_dir_microdesc_bad_health_replacement_suppress_gap_ms"
            ],
            5000,
        )
        self.assertEqual(
            load_aware_bad_health_gate[
                "arti_dir_microdesc_bad_health_replacement_suppress_min_assigned_streams"
            ],
            5,
        )
        self.assertEqual(
            load_aware_bad_health_gate[
                "arti_dir_microdesc_bad_health_replacement_suppress_min_active_streams"
            ],
            3,
        )
        self.assertTrue(
            load_aware_bad_health_gate["arti_dir_microdesc_source_spread"]
        )
        self.assertTrue(
            load_aware_bad_health_gate["arti_dir_microdesc_pending_spread"]
        )
        self.assertTrue(load_aware_bad_health_gate["arti_exit_select_load_aware"])
        self.assertFalse(
            load_aware_bad_health_gate["arti_exit_select_health_aware"]
        )
        load_aware_retry_partial = profiles[
            "arti_release_browser_"
            "mdsrcspreadpendingearlyusable_loadaware_earlyretrypartial"
        ]
        self.assertTrue(
            load_aware_retry_partial["arti_dir_microdesc_early_usable_notify"]
        )
        self.assertTrue(
            load_aware_retry_partial["arti_dir_microdesc_early_retry_on_partial"]
        )
        self.assertTrue(load_aware_retry_partial["arti_dir_microdesc_source_spread"])
        self.assertTrue(load_aware_retry_partial["arti_dir_microdesc_pending_spread"])
        self.assertTrue(load_aware_retry_partial["arti_exit_select_load_aware"])
        load_aware_partial_retry_chunk = profiles[
            "arti_release_browser_"
            "mdsrcspreadpendingearlyusable_loadaware_partialretrychunk"
        ]
        self.assertTrue(
            load_aware_partial_retry_chunk[
                "arti_dir_microdesc_early_usable_notify"
            ]
        )
        self.assertFalse(
            load_aware_partial_retry_chunk[
                "arti_dir_microdesc_early_retry_on_partial"
            ]
        )
        self.assertTrue(
            load_aware_partial_retry_chunk[
                "arti_dir_microdesc_partial_retry_chunking"
            ]
        )
        self.assertTrue(
            load_aware_partial_retry_chunk["arti_dir_microdesc_source_spread"]
        )
        self.assertTrue(
            load_aware_partial_retry_chunk["arti_dir_microdesc_pending_spread"]
        )
        self.assertEqual(
            load_aware_partial_retry_chunk[
                "arti_dir_microdesc_retry_ids_per_request"
            ],
            250,
        )
        self.assertEqual(
            load_aware_partial_retry_chunk["arti_dir_microdesc_retry_delay_max_ms"],
            500,
        )
        self.assertTrue(load_aware_partial_retry_chunk["arti_exit_select_load_aware"])
        load_aware_partial_retry_chunk_bad_health_gate = profiles[
            "arti_release_browser_"
            "mdsrcspreadpendingearlyusable_loadaware_partialretrychunk_"
            "badhealthgate5000ms_assigned5_active3"
        ]
        self.assertTrue(
            load_aware_partial_retry_chunk_bad_health_gate[
                "arti_dir_microdesc_early_usable_notify"
            ]
        )
        self.assertTrue(
            load_aware_partial_retry_chunk_bad_health_gate[
                "arti_dir_microdesc_partial_retry_chunking"
            ]
        )
        self.assertEqual(
            load_aware_partial_retry_chunk_bad_health_gate[
                "arti_dir_microdesc_bad_health_replacement_suppress_gap_ms"
            ],
            5000,
        )
        self.assertEqual(
            load_aware_partial_retry_chunk_bad_health_gate[
                "arti_dir_microdesc_bad_health_replacement_suppress_min_assigned_streams"
            ],
            5,
        )
        self.assertEqual(
            load_aware_partial_retry_chunk_bad_health_gate[
                "arti_dir_microdesc_bad_health_replacement_suppress_min_active_streams"
            ],
            3,
        )
        self.assertTrue(
            load_aware_partial_retry_chunk_bad_health_gate[
                "arti_dir_microdesc_source_spread"
            ]
        )
        self.assertTrue(
            load_aware_partial_retry_chunk_bad_health_gate[
                "arti_dir_microdesc_pending_spread"
            ]
        )
        self.assertEqual(
            load_aware_partial_retry_chunk_bad_health_gate[
                "arti_dir_microdesc_retry_ids_per_request"
            ],
            250,
        )
        self.assertEqual(
            load_aware_partial_retry_chunk_bad_health_gate[
                "arti_dir_microdesc_retry_delay_max_ms"
            ],
            500,
        )
        self.assertTrue(
            load_aware_partial_retry_chunk_bad_health_gate[
                "arti_exit_select_load_aware"
            ]
        )
        partial_retry_chunk = profiles[
            "arti_release_browser_"
            "mdsrcspreadpendingearlyusable_partialretrychunk"
        ]
        self.assertTrue(
            partial_retry_chunk["arti_dir_microdesc_early_usable_notify"]
        )
        self.assertTrue(
            partial_retry_chunk["arti_dir_microdesc_partial_retry_chunking"]
        )
        self.assertTrue(partial_retry_chunk["arti_dir_microdesc_source_spread"])
        self.assertTrue(partial_retry_chunk["arti_dir_microdesc_pending_spread"])
        self.assertEqual(
            partial_retry_chunk["arti_dir_microdesc_retry_ids_per_request"],
            250,
        )
        self.assertEqual(
            partial_retry_chunk["arti_dir_microdesc_retry_delay_max_ms"],
            500,
        )
        self.assertFalse(partial_retry_chunk["arti_exit_select_load_aware"])
        self.assertFalse(partial_retry_chunk["arti_exit_select_health_aware"])
        partial_retry_chunk_active_cap = profiles[
            "arti_release_browser_"
            "mdsrcspreadpendingearlyusable_partialretrychunk_"
            "activecap2"
        ]
        self.assertTrue(
            partial_retry_chunk_active_cap[
                "arti_dir_microdesc_early_usable_notify"
            ]
        )
        self.assertTrue(
            partial_retry_chunk_active_cap[
                "arti_dir_microdesc_partial_retry_chunking"
            ]
        )
        self.assertTrue(
            partial_retry_chunk_active_cap["arti_dir_microdesc_source_spread"]
        )
        self.assertTrue(
            partial_retry_chunk_active_cap["arti_dir_microdesc_pending_spread"]
        )
        self.assertEqual(
            partial_retry_chunk_active_cap[
                "arti_dir_microdesc_retry_ids_per_request"
            ],
            250,
        )
        self.assertEqual(
            partial_retry_chunk_active_cap["arti_dir_microdesc_retry_delay_max_ms"],
            500,
        )
        self.assertFalse(
            partial_retry_chunk_active_cap["arti_exit_select_load_aware"]
        )
        self.assertFalse(
            partial_retry_chunk_active_cap["arti_exit_select_health_aware"]
        )
        self.assertEqual(
            partial_retry_chunk_active_cap["arti_exit_select_max_active_streams"],
            2,
        )
        partial_retry_chunk_hs_rend_prebuild = profiles[
            "arti_release_browser_"
            "mdsrcspreadpendingearlyusable_partialretrychunk_"
            "hsrendpredesc"
        ]
        self.assertTrue(
            partial_retry_chunk_hs_rend_prebuild[
                "arti_dir_microdesc_early_usable_notify"
            ]
        )
        self.assertTrue(
            partial_retry_chunk_hs_rend_prebuild[
                "arti_dir_microdesc_partial_retry_chunking"
            ]
        )
        self.assertTrue(
            partial_retry_chunk_hs_rend_prebuild[
                "arti_dir_microdesc_source_spread"
            ]
        )
        self.assertTrue(
            partial_retry_chunk_hs_rend_prebuild[
                "arti_dir_microdesc_pending_spread"
            ]
        )
        self.assertTrue(
            partial_retry_chunk_hs_rend_prebuild[
                "arti_hs_rend_prebuild_before_desc"
            ]
        )
        self.assertFalse(
            partial_retry_chunk_hs_rend_prebuild["arti_exit_select_load_aware"]
        )
        load_aware_partial_retry_chunk_connect_hedge = profiles[
            "arti_release_browser_"
            "mdsrcspreadpendingearlyusable_loadaware_partialretrychunk_"
            "connecthedge500ms"
        ]
        self.assertTrue(
            load_aware_partial_retry_chunk_connect_hedge[
                "arti_dir_microdesc_early_usable_notify"
            ]
        )
        self.assertTrue(
            load_aware_partial_retry_chunk_connect_hedge[
                "arti_dir_microdesc_partial_retry_chunking"
            ]
        )
        self.assertTrue(
            load_aware_partial_retry_chunk_connect_hedge[
                "arti_dir_microdesc_source_spread"
            ]
        )
        self.assertTrue(
            load_aware_partial_retry_chunk_connect_hedge[
                "arti_dir_microdesc_pending_spread"
            ]
        )
        self.assertEqual(
            load_aware_partial_retry_chunk_connect_hedge[
                "arti_socks_connect_hedge_ms"
            ],
            500,
        )
        self.assertTrue(
            load_aware_partial_retry_chunk_connect_hedge[
                "arti_exit_select_load_aware"
            ]
        )
        load_aware_partial_retry_chunk_hs_rend_prebuild = profiles[
            "arti_release_browser_"
            "mdsrcspreadpendingearlyusable_loadaware_partialretrychunk_"
            "hsrendpredesc"
        ]
        self.assertTrue(
            load_aware_partial_retry_chunk_hs_rend_prebuild[
                "arti_dir_microdesc_early_usable_notify"
            ]
        )
        self.assertTrue(
            load_aware_partial_retry_chunk_hs_rend_prebuild[
                "arti_dir_microdesc_partial_retry_chunking"
            ]
        )
        self.assertTrue(
            load_aware_partial_retry_chunk_hs_rend_prebuild[
                "arti_dir_microdesc_source_spread"
            ]
        )
        self.assertTrue(
            load_aware_partial_retry_chunk_hs_rend_prebuild[
                "arti_dir_microdesc_pending_spread"
            ]
        )
        self.assertTrue(
            load_aware_partial_retry_chunk_hs_rend_prebuild[
                "arti_hs_rend_prebuild_before_desc"
            ]
        )
        self.assertTrue(
            load_aware_partial_retry_chunk_hs_rend_prebuild[
                "arti_exit_select_load_aware"
            ]
        )
        load_aware_partial_retry_chunk_soft_timeout = profiles[
            "arti_release_browser_"
            "mdsrcspreadpendingearlyusable_loadaware_partialretrychunk_"
            "soft5000ms_attempts3"
        ]
        self.assertTrue(
            load_aware_partial_retry_chunk_soft_timeout[
                "arti_dir_microdesc_early_usable_notify"
            ]
        )
        self.assertTrue(
            load_aware_partial_retry_chunk_soft_timeout[
                "arti_dir_microdesc_partial_retry_chunking"
            ]
        )
        self.assertTrue(
            load_aware_partial_retry_chunk_soft_timeout[
                "arti_dir_microdesc_source_spread"
            ]
        )
        self.assertTrue(
            load_aware_partial_retry_chunk_soft_timeout[
                "arti_dir_microdesc_pending_spread"
            ]
        )
        self.assertEqual(
            load_aware_partial_retry_chunk_soft_timeout[
                "arti_socks_connect_soft_timeout_ms"
            ],
            5000,
        )
        self.assertEqual(
            load_aware_partial_retry_chunk_soft_timeout[
                "arti_socks_connect_soft_timeout_attempts"
            ],
            3,
        )
        self.assertTrue(
            load_aware_partial_retry_chunk_soft_timeout[
                "arti_exit_select_load_aware"
            ]
        )
        self.assertFalse(
            profiles["arti_release_browser_mdsrcspreadpending"][
                "arti_dir_microdesc_early_usable_notify"
            ]
        )
        self.assertTrue(
            profiles["arti_release_browser_mdsrcspreadpending"][
                "arti_dir_microdesc_source_spread"
            ]
        )
        self.assertTrue(
            profiles["arti_release_browser_mdsrcspreadpending"][
                "arti_dir_microdesc_pending_spread"
            ]
        )
        self.assertEqual(
            profiles["arti_release_browser_mdretrychunk250"][
                "arti_dir_microdesc_retry_ids_per_request"
            ],
            250,
        )
        self.assertEqual(
            profiles["arti_release_browser_buf1mb"]["arti_proxy_buffer_size"],
            "1 MB",
        )
        self.assertEqual(
            profiles["arti_release_browser_buf1mb"][
                "arti_exit_select_parallelism_override"
            ],
            3,
        )
        self.assertEqual(
            profiles["arti_release_browser_exit1"][
                "arti_exit_select_bad_health_hedge_ms"
            ],
            750,
        )
        self.assertFalse(
            profiles["arti_release_browser_exit1"][
                "arti_exit_select_avoid_bad_health"
            ]
        )
        self.assertTrue(
            profiles["arti_release_browser_exit1"]["benchmarks"][
                "https://check.torproject.org/"
            ]["summary"]["ok"]
        )
        self.assertEqual(
            profiles["arti_release_browser_soft1500ms"][
                "arti_exit_select_parallelism_override"
            ],
            3,
        )
        self.assertEqual(
            profiles["arti_release_browser_soft1500ms"][
                "arti_min_exit_circs_for_port_override"
            ],
            3,
        )
        self.assertEqual(
            profiles["arti_release_browser_soft1500ms"][
                "arti_socks_connect_soft_timeout_ms"
            ],
            1500,
        )
        self.assertEqual(
            profiles["arti_release_browser_soft1500ms"][
                "arti_socks_connect_soft_timeout_attempts"
            ],
            2,
        )
        self.assertEqual(
            profiles["arti_release_browser_notorbyte5000ms"][
                "arti_socks_no_tor_byte_relay_timeout_ms"
            ],
            5000,
        )
        self.assertEqual(
            profiles["arti_release_browser_partialidle4000ms"][
                "arti_socks_partial_relay_idle_timeout_ms"
            ],
            4000,
        )
        self.assertEqual(
            profiles["arti_release_browser_partialidle4000ms"][
                "arti_exit_select_parallelism_override"
            ],
            3,
        )
        self.assertEqual(
            profiles["arti_release_browser_notorbyte5000ms"][
                "arti_exit_select_parallelism_override"
            ],
            3,
        )
        self.assertFalse(
            profiles["arti_release_browser_soft1500ms"][
                "arti_exit_select_avoid_bad_health"
            ]
        )
        self.assertTrue(
            profiles["arti_release_browser_soft1500ms"]["benchmarks"][
                "https://check.torproject.org/"
            ]["summary"]["ok"]
        )
        self.assertEqual(
            profiles["arti_release_browser_softattempts3"][
                "arti_socks_connect_soft_timeout_ms"
            ],
            5000,
        )
        self.assertEqual(
            profiles["arti_release_browser_softattempts3"][
                "arti_socks_connect_soft_timeout_attempts"
            ],
            3,
        )
        self.assertTrue(
            profiles["arti_release_browser_softattempts3"]["benchmarks"][
                "https://check.torproject.org/"
            ]["summary"]["ok"]
        )
        self.assertEqual(
            profiles["arti_release_browser_soft5000ms_attempts3"][
                "arti_socks_connect_soft_timeout_ms"
            ],
            5000,
        )
        self.assertEqual(
            profiles["arti_release_browser_soft5000ms_attempts3"][
                "arti_socks_connect_soft_timeout_attempts"
            ],
            3,
        )
        self.assertTrue(
            profiles["arti_release_browser_soft5000ms_attempts3"]["benchmarks"][
                "https://check.torproject.org/"
            ]["summary"]["ok"]
        )
        self.assertEqual(
            profiles["arti_release_browser_soft5000ms_attempts3_pending1500ms"][
                "arti_socks_connect_soft_timeout_ms"
            ],
            5000,
        )
        self.assertEqual(
            profiles["arti_release_browser_soft5000ms_attempts3_pending1500ms"][
                "arti_socks_connect_soft_timeout_attempts"
            ],
            3,
        )
        self.assertEqual(
            profiles["arti_release_browser_soft5000ms_attempts3_pending1500ms"][
                "arti_exit_pending_hedge_ms"
            ],
            1500,
        )
        self.assertTrue(
            profiles["arti_release_browser_soft5000ms_attempts3_pending1500ms"][
                "benchmarks"
            ]["https://check.torproject.org/"]["summary"]["ok"]
        )
        self.assertEqual(
            profiles["arti_release_browser_dirread8000ms"][
                "arti_dirclient_read_timeout_ms"
            ],
            8000,
        )
        self.assertTrue(
            profiles["arti_release_browser_dirread8000ms"]["benchmarks"][
                "https://check.torproject.org/"
            ]["summary"]["ok"]
        )
        self.assertTrue(
            profiles["arti_release_browser_loadaware"][
                "arti_exit_select_load_aware"
            ]
        )
        self.assertFalse(
            profiles["arti_release_browser_loadaware"][
                "arti_exit_select_avoid_bad_health"
            ]
        )
        self.assertTrue(
            profiles["arti_release_browser_loadaware"]["benchmarks"][
                "https://check.torproject.org/"
            ]["summary"]["ok"]
        )
        self.assertTrue(
            profiles["arti_release_browser_healthaware"][
                "arti_exit_select_load_aware"
            ]
        )
        self.assertTrue(
            profiles["arti_release_browser_healthaware"][
                "arti_exit_select_health_aware"
            ]
        )
        self.assertFalse(
            profiles["arti_release_browser_healthaware"][
                "arti_exit_select_avoid_bad_health"
            ]
        )
        self.assertTrue(
            profiles["arti_release_browser_healthaware"]["benchmarks"][
                "https://check.torproject.org/"
            ]["summary"]["ok"]
        )
        health_min = profiles["arti_release_browser_healthaware_min16000bps"]
        self.assertTrue(health_min["arti_exit_select_load_aware"])
        self.assertTrue(health_min["arti_exit_select_health_aware"])
        self.assertEqual(
            health_min["arti_exit_select_health_min_move_score_bps"], 16000
        )
        self.assertTrue(
            health_min["benchmarks"]["https://check.torproject.org/"]["summary"][
                "ok"
            ]
        )
        self.assertTrue(
            profiles["arti_release_browser_avoidbadhealth"][
                "arti_exit_select_load_aware"
            ]
        )
        self.assertFalse(
            profiles["arti_release_browser_avoidbadhealth"][
                "arti_exit_select_health_aware"
            ]
        )
        self.assertTrue(
            profiles["arti_release_browser_avoidbadhealth"][
                "arti_exit_select_avoid_bad_health"
            ]
        )
        self.assertTrue(
            profiles["arti_release_browser_avoidbadhealth"]["benchmarks"][
                "https://check.torproject.org/"
            ]["summary"]["ok"]
        )
        bad_health_hedge = profiles["arti_release_browser_loadaware_badhedge600ms"]
        self.assertTrue(bad_health_hedge["arti_exit_select_load_aware"])
        self.assertFalse(bad_health_hedge["arti_exit_select_health_aware"])
        self.assertTrue(bad_health_hedge["arti_exit_select_avoid_bad_health"])
        self.assertEqual(
            bad_health_hedge["arti_exit_select_bad_health_hedge_ms"], 600
        )
        self.assertTrue(
            bad_health_hedge["benchmarks"]["https://check.torproject.org/"][
                "summary"
            ]["ok"]
        )
        self.assertTrue(
            profiles["arti_release_browser_healthaware_avoidbadhealth"][
                "arti_exit_select_load_aware"
            ]
        )
        self.assertTrue(
            profiles["arti_release_browser_healthaware_avoidbadhealth"][
                "arti_exit_select_health_aware"
            ]
        )
        self.assertTrue(
            profiles["arti_release_browser_healthaware_avoidbadhealth"][
                "arti_exit_select_avoid_bad_health"
            ]
        )
        self.assertTrue(
            profiles["arti_release_browser_healthaware_avoidbadhealth"][
                "benchmarks"
            ]["https://check.torproject.org/"]["summary"]["ok"]
        )
        guarded_sameiso = profiles[
            "arti_release_browser_healthaware_avoidbadhealth_sameiso2"
        ]
        self.assertTrue(guarded_sameiso["arti_exit_select_load_aware"])
        self.assertTrue(guarded_sameiso["arti_exit_select_health_aware"])
        self.assertTrue(guarded_sameiso["arti_exit_select_avoid_bad_health"])
        self.assertEqual(guarded_sameiso["arti_exit_same_isolation_target"], 2)
        self.assertTrue(
            guarded_sameiso["benchmarks"]["https://check.torproject.org/"][
                "summary"
            ]["ok"]
        )
        prefer_cold_sameiso = profiles[
            "arti_release_browser_healthaware_sameiso2_prefercold"
        ]
        self.assertTrue(prefer_cold_sameiso["arti_exit_select_load_aware"])
        self.assertTrue(prefer_cold_sameiso["arti_exit_select_health_aware"])
        self.assertFalse(prefer_cold_sameiso["arti_exit_select_avoid_bad_health"])
        self.assertEqual(prefer_cold_sameiso["arti_exit_same_isolation_target"], 2)
        self.assertTrue(
            prefer_cold_sameiso["arti_exit_select_prefer_cold_same_isolation"]
        )
        self.assertTrue(
            prefer_cold_sameiso["benchmarks"]["https://check.torproject.org/"][
                "summary"
            ]["ok"]
        )
        guarded_prefer_cold_sameiso = profiles[
            "arti_release_browser_healthaware_avoidbadhealth_sameiso2_prefercold"
        ]
        self.assertTrue(guarded_prefer_cold_sameiso["arti_exit_select_load_aware"])
        self.assertTrue(guarded_prefer_cold_sameiso["arti_exit_select_health_aware"])
        self.assertTrue(
            guarded_prefer_cold_sameiso["arti_exit_select_avoid_bad_health"]
        )
        self.assertEqual(
            guarded_prefer_cold_sameiso["arti_exit_same_isolation_target"], 2
        )
        self.assertEqual(
            guarded_prefer_cold_sameiso[
                "arti_exit_same_isolation_min_assigned_streams"
            ],
            1,
        )
        self.assertTrue(
            guarded_prefer_cold_sameiso[
                "arti_exit_select_prefer_cold_same_isolation"
            ]
        )
        self.assertTrue(
            guarded_prefer_cold_sameiso["benchmarks"][
                "https://check.torproject.org/"
            ]["summary"]["ok"]
        )
        guarded_prefer_cold_sameiso_activecap = profiles[
            "arti_release_browser_healthaware_avoidbadhealth_sameiso2_prefercold_activecap1"
        ]
        self.assertTrue(
            guarded_prefer_cold_sameiso_activecap["arti_exit_select_load_aware"]
        )
        self.assertTrue(
            guarded_prefer_cold_sameiso_activecap["arti_exit_select_health_aware"]
        )
        self.assertTrue(
            guarded_prefer_cold_sameiso_activecap[
                "arti_exit_select_avoid_bad_health"
            ]
        )
        self.assertEqual(
            guarded_prefer_cold_sameiso_activecap[
                "arti_exit_same_isolation_target"
            ],
            2,
        )
        self.assertTrue(
            guarded_prefer_cold_sameiso_activecap[
                "arti_exit_select_prefer_cold_same_isolation"
            ]
        )
        self.assertEqual(
            guarded_prefer_cold_sameiso_activecap[
                "arti_exit_select_max_active_streams"
            ],
            1,
        )
        self.assertEqual(
            profiles["arti_release_browser"]["arti_exit_select_max_active_streams"],
            None,
        )
        self.assertTrue(
            guarded_prefer_cold_sameiso_activecap["benchmarks"][
                "https://check.torproject.org/"
            ]["summary"]["ok"]
        )
        guarded_prefer_cold_sameiso_prewarm = profiles[
            "arti_release_browser_healthaware_avoidbadhealth_sameiso2_prefercold_prewarmfirst"
        ]
        self.assertTrue(
            guarded_prefer_cold_sameiso_prewarm["arti_exit_select_load_aware"]
        )
        self.assertTrue(
            guarded_prefer_cold_sameiso_prewarm["arti_exit_select_health_aware"]
        )
        self.assertTrue(
            guarded_prefer_cold_sameiso_prewarm[
                "arti_exit_select_avoid_bad_health"
            ]
        )
        self.assertEqual(
            guarded_prefer_cold_sameiso_prewarm["arti_exit_same_isolation_target"],
            2,
        )
        self.assertEqual(
            guarded_prefer_cold_sameiso_prewarm[
                "arti_exit_same_isolation_pending_wait_ms"
            ],
            800,
        )
        self.assertTrue(
            guarded_prefer_cold_sameiso_prewarm[
                "arti_exit_same_isolation_prewarm_first_stream"
            ]
        )
        self.assertTrue(
            guarded_prefer_cold_sameiso_prewarm[
                "arti_exit_select_prefer_cold_same_isolation"
            ]
        )
        self.assertTrue(
            profiles["arti_release_browser"][
                "arti_exit_same_isolation_prewarm_first_stream"
            ]
        )
        self.assertTrue(
            guarded_prefer_cold_sameiso_prewarm["benchmarks"][
                "https://check.torproject.org/"
            ]["summary"]["ok"]
        )
        unknown_fallback_prefer_cold_sameiso = profiles[
            "arti_release_browser_healthaware_avoidbadhealth_unknownfallback_sameiso2_prefercold"
        ]
        self.assertTrue(
            unknown_fallback_prefer_cold_sameiso["arti_exit_select_load_aware"]
        )
        self.assertTrue(
            unknown_fallback_prefer_cold_sameiso["arti_exit_select_health_aware"]
        )
        self.assertTrue(
            unknown_fallback_prefer_cold_sameiso["arti_exit_select_avoid_bad_health"]
        )
        self.assertTrue(
            unknown_fallback_prefer_cold_sameiso[
                "arti_exit_select_avoid_bad_health_unknown_fallback"
            ]
        )
        self.assertEqual(
            unknown_fallback_prefer_cold_sameiso["arti_exit_same_isolation_target"], 2
        )
        self.assertTrue(
            unknown_fallback_prefer_cold_sameiso[
                "arti_exit_select_prefer_cold_same_isolation"
            ]
        )
        self.assertTrue(
            unknown_fallback_prefer_cold_sameiso["benchmarks"][
                "https://check.torproject.org/"
            ]["summary"]["ok"]
        )
        self.assertTrue(
            profiles["arti_release_browser_loadaware_spread2"][
                "arti_exit_select_load_aware"
            ]
        )
        self.assertEqual(
            profiles["arti_release_browser_loadaware_spread2"][
                "arti_exit_select_min_assignment_spread"
            ],
            2,
        )
        self.assertTrue(
            profiles["arti_release_browser_loadaware_spread2"]["benchmarks"][
                "https://check.torproject.org/"
            ]["summary"]["ok"]
        )
        self.assertFalse(
            profiles["arti_release_browser_sameiso2"]["arti_exit_select_load_aware"]
        )
        self.assertEqual(
            profiles["arti_release_browser_sameiso2"][
                "arti_exit_same_isolation_target"
            ],
            2,
        )
        self.assertTrue(
            profiles["arti_release_browser_sameiso2"][
                "arti_exit_same_isolation_require_bad_health"
            ]
        )
        self.assertTrue(
            profiles["arti_release_browser_sameiso2"]["benchmarks"][
                "https://check.torproject.org/"
            ]["summary"]["ok"]
        )
        sameiso_otheriso = profiles["arti_release_browser_sameiso2_otheriso3"]
        self.assertFalse(sameiso_otheriso["arti_exit_select_load_aware"])
        self.assertEqual(sameiso_otheriso["arti_exit_same_isolation_target"], 2)
        self.assertEqual(
            sameiso_otheriso["arti_exit_same_isolation_other_isolation_min"], 3
        )
        self.assertTrue(
            sameiso_otheriso["benchmarks"]["https://check.torproject.org/"][
                "summary"
            ]["ok"]
        )
        prefer_cold_sameiso_otheriso = profiles[
            "arti_release_browser_healthaware_avoidbadhealth_sameiso2_otheriso3_prefercold"
        ]
        self.assertTrue(prefer_cold_sameiso_otheriso["arti_exit_select_load_aware"])
        self.assertTrue(prefer_cold_sameiso_otheriso["arti_exit_select_health_aware"])
        self.assertTrue(
            prefer_cold_sameiso_otheriso["arti_exit_select_avoid_bad_health"]
        )
        self.assertEqual(
            prefer_cold_sameiso_otheriso["arti_exit_same_isolation_target"], 2
        )
        self.assertEqual(
            prefer_cold_sameiso_otheriso[
                "arti_exit_same_isolation_other_isolation_min"
            ],
            3,
        )
        self.assertTrue(
            prefer_cold_sameiso_otheriso[
                "arti_exit_select_prefer_cold_same_isolation"
            ]
        )
        loadaware_sameiso = profiles["arti_release_browser_loadaware_sameiso2"]
        self.assertTrue(loadaware_sameiso["arti_exit_select_load_aware"])
        self.assertFalse(loadaware_sameiso["arti_exit_select_health_aware"])
        self.assertFalse(loadaware_sameiso["arti_exit_select_avoid_bad_health"])
        self.assertEqual(loadaware_sameiso["arti_exit_same_isolation_target"], 2)
        self.assertEqual(
            loadaware_sameiso["arti_exit_same_isolation_min_assigned_streams"],
            1,
        )
        self.assertTrue(
            loadaware_sameiso["arti_exit_same_isolation_prewarm_first_stream"]
        )
        self.assertTrue(
            loadaware_sameiso["benchmarks"]["https://check.torproject.org/"][
                "summary"
            ]["ok"]
        )
        sameiso_prewarm = profiles["arti_release_browser_sameiso2_prewarmfirst"]
        self.assertFalse(sameiso_prewarm["arti_exit_select_load_aware"])
        self.assertFalse(sameiso_prewarm["arti_exit_select_health_aware"])
        self.assertFalse(sameiso_prewarm["arti_exit_select_avoid_bad_health"])
        self.assertEqual(sameiso_prewarm["arti_exit_same_isolation_target"], 2)
        self.assertEqual(
            sameiso_prewarm["arti_exit_same_isolation_pending_wait_ms"], 800
        )
        self.assertTrue(
            sameiso_prewarm["arti_exit_same_isolation_prewarm_first_stream"]
        )
        self.assertTrue(
            sameiso_prewarm["arti_exit_select_prefer_cold_same_isolation"]
        )
        self.assertTrue(
            sameiso_prewarm["arti_exit_same_isolation_require_bad_health"]
        )
        self.assertTrue(
            sameiso_prewarm["benchmarks"]["https://check.torproject.org/"][
                "summary"
            ]["ok"]
        )
        loadaware_sameiso_prewarm = profiles[
            "arti_release_browser_loadaware_sameiso2_prewarmfirst"
        ]
        self.assertTrue(loadaware_sameiso_prewarm["arti_exit_select_load_aware"])
        self.assertFalse(
            loadaware_sameiso_prewarm["arti_exit_select_health_aware"]
        )
        self.assertFalse(
            loadaware_sameiso_prewarm["arti_exit_select_avoid_bad_health"]
        )
        self.assertEqual(
            loadaware_sameiso_prewarm["arti_exit_same_isolation_target"], 2
        )
        self.assertEqual(
            loadaware_sameiso_prewarm["arti_exit_same_isolation_pending_wait_ms"],
            800,
        )
        self.assertTrue(
            loadaware_sameiso_prewarm[
                "arti_exit_same_isolation_prewarm_first_stream"
            ]
        )
        self.assertTrue(
            loadaware_sameiso_prewarm[
                "arti_exit_select_prefer_cold_same_isolation"
            ]
        )
        self.assertTrue(
            loadaware_sameiso_prewarm[
                "arti_exit_same_isolation_require_bad_health"
            ]
        )
        self.assertTrue(
            loadaware_sameiso_prewarm["benchmarks"][
                "https://check.torproject.org/"
            ]["summary"]["ok"]
        )
        healthaware_prefercold_sameiso_prewarm_wait = profiles[
            "arti_release_browser_healthaware_sameiso2_prewarmfirst_prefercold_wait800ms"
        ]
        self.assertTrue(
            healthaware_prefercold_sameiso_prewarm_wait[
                "arti_exit_select_load_aware"
            ]
        )
        self.assertTrue(
            healthaware_prefercold_sameiso_prewarm_wait[
                "arti_exit_select_health_aware"
            ]
        )
        self.assertEqual(
            healthaware_prefercold_sameiso_prewarm_wait[
                "arti_exit_select_health_min_move_score_bps"
            ],
            32000,
        )
        self.assertFalse(
            healthaware_prefercold_sameiso_prewarm_wait[
                "arti_exit_select_avoid_bad_health"
            ]
        )
        self.assertEqual(
            healthaware_prefercold_sameiso_prewarm_wait[
                "arti_exit_same_isolation_target"
            ],
            2,
        )
        self.assertEqual(
            healthaware_prefercold_sameiso_prewarm_wait[
                "arti_exit_same_isolation_pending_wait_ms"
            ],
            800,
        )
        self.assertTrue(
            healthaware_prefercold_sameiso_prewarm_wait[
                "arti_exit_same_isolation_prewarm_first_stream"
            ]
        )
        self.assertTrue(
            healthaware_prefercold_sameiso_prewarm_wait[
                "arti_exit_select_prefer_cold_same_isolation"
            ]
        )
        self.assertTrue(
            healthaware_prefercold_sameiso_prewarm_wait[
                "arti_exit_same_isolation_require_bad_health"
            ]
        )
        self.assertTrue(
            healthaware_prefercold_sameiso_prewarm_wait["benchmarks"][
                "https://check.torproject.org/"
            ]["summary"]["ok"]
        )
        healthaware_sameiso_prewarm = profiles[
            "arti_release_browser_healthaware_sameiso2_prewarmfirst"
        ]
        self.assertTrue(healthaware_sameiso_prewarm["arti_exit_select_load_aware"])
        self.assertTrue(
            healthaware_sameiso_prewarm["arti_exit_select_health_aware"]
        )
        self.assertEqual(
            healthaware_sameiso_prewarm[
                "arti_exit_select_health_min_move_score_bps"
            ],
            32000,
        )
        self.assertFalse(
            healthaware_sameiso_prewarm["arti_exit_select_avoid_bad_health"]
        )
        self.assertEqual(
            healthaware_sameiso_prewarm["arti_exit_same_isolation_target"], 2
        )
        self.assertTrue(
            healthaware_sameiso_prewarm[
                "arti_exit_same_isolation_prewarm_first_stream"
            ]
        )
        self.assertTrue(
            healthaware_sameiso_prewarm[
                "arti_exit_select_prefer_cold_same_isolation"
            ]
        )
        self.assertTrue(
            healthaware_sameiso_prewarm[
                "arti_exit_same_isolation_require_bad_health"
            ]
        )
        self.assertTrue(
            healthaware_sameiso_prewarm["benchmarks"][
                "https://check.torproject.org/"
            ]["summary"]["ok"]
        )
        health_min_sameiso_wait = profiles[
            "arti_release_browser_healthaware_min16000bps_sameiso2_wait800ms"
        ]
        self.assertTrue(health_min_sameiso_wait["arti_exit_select_load_aware"])
        self.assertTrue(health_min_sameiso_wait["arti_exit_select_health_aware"])
        self.assertEqual(
            health_min_sameiso_wait["arti_exit_select_health_min_move_score_bps"],
            16000,
        )
        self.assertFalse(
            health_min_sameiso_wait["arti_exit_select_avoid_bad_health"]
        )
        self.assertEqual(
            health_min_sameiso_wait["arti_exit_same_isolation_target"], 2
        )
        self.assertEqual(
            health_min_sameiso_wait["arti_exit_same_isolation_pending_wait_ms"],
            800,
        )
        self.assertTrue(
            health_min_sameiso_wait[
                "arti_exit_same_isolation_prewarm_first_stream"
            ]
        )
        self.assertTrue(
            health_min_sameiso_wait[
                "arti_exit_same_isolation_require_bad_health"
            ]
        )
        self.assertTrue(
            health_min_sameiso_wait["benchmarks"]["https://check.torproject.org/"][
                "summary"
            ]["ok"]
        )

    def test_interleaved_schedule_can_share_first_arti_warm_cache_with_extra_profiles(
        self,
    ) -> None:
        seeded_checks = []

        def fake_warmup(spec, storage):
            if spec.kind == "arti":
                marker = storage["cache_dir"] / "seed.txt"
                if spec.name == "arti_release_browser":
                    marker.write_text("seed", encoding="utf-8")
                elif spec.name == "arti_release_browser_sameiso2_prewarmfirst":
                    seeded_checks.append(marker.exists())
            return {"ok": True, "seconds": 0.1}

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            browser = root / "firefox"
            bundled = root / "bundled-tor"
            local = root / "tor"
            arti = root / "arti"
            for path in (browser, bundled, local, arti):
                path.write_text("", encoding="utf-8")

            with (
                patch("run_browser_compare.warmup_proxy", side_effect=fake_warmup),
                patch(
                    "run_browser_compare.start_proxy_for_spec",
                    return_value=(object(), queue.Queue()),
                ),
                patch(
                    "run_browser_compare.wait_for_line",
                    return_value={"ok": True, "seconds": 0.2},
                ),
                patch("run_browser_compare.stop_process"),
                patch("run_browser_compare.read_torrc_quality", return_value={}),
                patch(
                    "run_browser_compare.run_browser_once",
                    return_value={
                        "ok": True,
                        "elapsed_ms": 1001,
                        "load_ms": 801,
                        "screenshot": {"bytes": 100},
                        "performance_timing": {},
                    },
                ),
            ):
                profiles = run_interleaved_profiles(
                    bundled_tor_bin=bundled,
                    tor_bin=local,
                    arti_bin=arti,
                    ports={
                        "bundled_c_tor_browser": 19080,
                        "local_c_tor_browser": 19081,
                        "arti_release_browser": 19082,
                    },
                    output_dir=root / "out",
                    browser_bin=browser,
                    targets=["https://check.torproject.org/"],
                    runs=1,
                    timeout=1.0,
                    window_size="1000,1000",
                    warm_cache=True,
                    share_arti_warm_cache_seed=True,
                    extra_arti_exit_same_isolation_prewarm_target=[2],
                )

        self.assertEqual(seeded_checks, [True])
        self.assertEqual(
            profiles["arti_release_browser_sameiso2_prewarmfirst"][
                "arti_warm_cache_seeded_from"
            ],
            "arti_release_browser",
        )

    def test_interleaved_schedule_can_add_sameiso_min_assigned_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            browser = root / "firefox"
            bundled = root / "bundled-tor"
            local = root / "tor"
            arti = root / "arti"
            for path in (browser, bundled, local, arti):
                path.write_text("", encoding="utf-8")

            with (
                patch(
                    "run_browser_compare.warmup_proxy",
                    return_value={"ok": True, "seconds": 0.1},
                ),
                patch(
                    "run_browser_compare.start_proxy_for_spec",
                    return_value=(object(), queue.Queue()),
                ),
                patch(
                    "run_browser_compare.wait_for_line",
                    return_value={"ok": True, "seconds": 0.2},
                ),
                patch("run_browser_compare.stop_process"),
                patch("run_browser_compare.read_torrc_quality", return_value={}),
                patch(
                    "run_browser_compare.run_browser_once",
                    return_value={
                        "ok": True,
                        "elapsed_ms": 1001,
                        "load_ms": 801,
                        "screenshot": {"bytes": 100},
                        "performance_timing": {},
                    },
                ),
            ):
                profiles = run_interleaved_profiles(
                    bundled_tor_bin=bundled,
                    tor_bin=local,
                    arti_bin=arti,
                    ports={
                        "bundled_c_tor_browser": 19080,
                        "local_c_tor_browser": 19081,
                        "arti_release_browser": 19082,
                    },
                    output_dir=root / "out",
                    browser_bin=browser,
                    targets=["https://check.torproject.org/"],
                    runs=1,
                    timeout=1.0,
                    window_size="1000,1000",
                    warm_cache=True,
                    extra_arti_exit_same_isolation_min_assigned_streams=[(2, 1)],
                )

        profile = profiles["arti_release_browser_sameiso2_minassigned1_prewarmfirst"]
        self.assertEqual(profile["arti_exit_same_isolation_target"], 2)
        self.assertEqual(profile["arti_exit_same_isolation_min_assigned_streams"], 1)
        self.assertTrue(profile["arti_exit_same_isolation_prewarm_first_stream"])
        self.assertTrue(profile["benchmarks"]["https://check.torproject.org/"]["summary"]["ok"])

    def test_interleaved_schedule_can_add_sameiso_prefer_topup_on_tie_profile(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            browser = root / "firefox"
            bundled = root / "bundled-tor"
            local = root / "tor"
            arti = root / "arti"
            for path in (browser, bundled, local, arti):
                path.write_text("", encoding="utf-8")

            with (
                patch(
                    "run_browser_compare.warmup_proxy",
                    return_value={"ok": True, "seconds": 0.1},
                ),
                patch(
                    "run_browser_compare.start_proxy_for_spec",
                    return_value=(object(), queue.Queue()),
                ),
                patch(
                    "run_browser_compare.wait_for_line",
                    return_value={"ok": True, "seconds": 0.2},
                ),
                patch("run_browser_compare.stop_process"),
                patch("run_browser_compare.read_torrc_quality", return_value={}),
                patch(
                    "run_browser_compare.run_browser_once",
                    return_value={
                        "ok": True,
                        "elapsed_ms": 1001,
                        "load_ms": 801,
                        "screenshot": {"bytes": 100},
                        "performance_timing": {},
                    },
                ),
            ):
                profiles = run_interleaved_profiles(
                    bundled_tor_bin=bundled,
                    tor_bin=local,
                    arti_bin=arti,
                    ports={
                        "bundled_c_tor_browser": 19080,
                        "local_c_tor_browser": 19081,
                        "arti_release_browser": 19082,
                    },
                    output_dir=root / "out",
                    browser_bin=browser,
                    targets=["https://check.torproject.org/"],
                    runs=1,
                    timeout=1.0,
                    window_size="1000,1000",
                    warm_cache=True,
                    extra_arti_exit_same_isolation_prefer_topup_on_tie=[2],
                )

        profile = profiles["arti_release_browser_sameiso2_prewarmtie"]
        self.assertEqual(profile["arti_exit_same_isolation_target"], 2)
        self.assertTrue(profile["arti_exit_same_isolation_prewarm_first_stream"])
        self.assertTrue(profile["arti_exit_same_isolation_prefer_topup_on_tie"])
        self.assertTrue(profile["benchmarks"]["https://check.torproject.org/"]["summary"]["ok"])

    def test_interleaved_schedule_can_add_health_aware_spread_profile(self) -> None:
        calls = []

        def fake_browser_once(**kwargs):
            calls.append((kwargs["port"], kwargs["run_index"]))
            return {
                "ok": True,
                "elapsed_ms": 1000 + len(calls),
                "load_ms": 800 + len(calls),
                "screenshot": {"bytes": 100},
                "performance_timing": {},
            }

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            browser = root / "firefox"
            bundled = root / "bundled-tor"
            local = root / "tor"
            arti = root / "arti"
            for path in (browser, bundled, local, arti):
                path.write_text("", encoding="utf-8")

            with (
                patch(
                    "run_browser_compare.warmup_proxy",
                    return_value={"ok": True, "seconds": 0.1},
                ),
                patch(
                    "run_browser_compare.start_proxy_for_spec",
                    return_value=(object(), queue.Queue()),
                ),
                patch(
                    "run_browser_compare.wait_for_line",
                    return_value={"ok": True, "seconds": 0.2},
                ),
                patch("run_browser_compare.stop_process"),
                patch("run_browser_compare.read_torrc_quality", return_value={}),
                patch("run_browser_compare.run_browser_once", side_effect=fake_browser_once),
            ):
                profiles = run_interleaved_profiles(
                    bundled_tor_bin=bundled,
                    tor_bin=local,
                    arti_bin=arti,
                    ports={
                        "bundled_c_tor_browser": 19080,
                        "local_c_tor_browser": 19081,
                        "arti_release_browser": 19082,
                    },
                    output_dir=root / "out",
                    browser_bin=browser,
                    targets=["https://check.torproject.org/"],
                    runs=1,
                    timeout=1.0,
                    window_size="1000,1000",
                    warm_cache=True,
                    extra_arti_exit_select_health_aware_min_assignment_spread=[4],
                    extra_arti_exit_select_health_aware_min_assigned=[2],
                    extra_arti_exit_select_healthy_over_cold_min_assigned=[4],
                    extra_arti_exit_select_healthy_over_cold_guard_only_min_assigned=[
                        4
                    ],
                    extra_arti_port_start=19083,
                )

        self.assertEqual(
            calls,
            [
                (19080, 1),
                (19081, 1),
                (19082, 1),
                (19083, 1),
                (19084, 1),
                (19085, 1),
                (19086, 1),
            ],
        )
        self.assertFalse(profiles["arti_release_browser"]["arti_exit_select_load_aware"])
        self.assertFalse(
            profiles["arti_release_browser"]["arti_exit_select_health_aware"]
        )
        self.assertIsNone(
            profiles["arti_release_browser"]["arti_exit_select_min_assignment_spread"]
        )
        self.assertIsNone(
            profiles["arti_release_browser"][
                "arti_exit_select_healthy_over_cold_min_assigned"
            ]
        )
        self.assertIsNone(
            profiles["arti_release_browser"][
                "arti_exit_select_healthy_over_cold_guard_only_min_assigned"
            ]
        )
        self.assertIsNone(
            profiles["arti_release_browser"][
                "arti_exit_select_health_aware_min_assigned"
            ]
        )
        profile = profiles["arti_release_browser_healthaware_spread4"]
        self.assertTrue(profile["arti_exit_select_load_aware"])
        self.assertTrue(profile["arti_exit_select_health_aware"])
        self.assertFalse(profile["arti_exit_select_avoid_bad_health"])
        self.assertEqual(profile["arti_exit_select_min_assignment_spread"], 4)
        self.assertTrue(
            profile["benchmarks"]["https://check.torproject.org/"]["summary"]["ok"]
        )
        gated = profiles["arti_release_browser_healthaware_minassigned2"]
        self.assertTrue(gated["arti_exit_select_load_aware"])
        self.assertTrue(gated["arti_exit_select_health_aware"])
        self.assertEqual(gated["arti_exit_select_health_aware_min_assigned"], 2)
        self.assertTrue(
            gated["benchmarks"]["https://check.torproject.org/"]["summary"]["ok"]
        )
        guarded = profiles["arti_release_browser_loadaware_healthyovercold4"]
        self.assertTrue(guarded["arti_exit_select_load_aware"])
        self.assertFalse(guarded["arti_exit_select_health_aware"])
        self.assertEqual(
            guarded["arti_exit_select_healthy_over_cold_min_assigned"], 4
        )
        self.assertTrue(
            guarded["benchmarks"]["https://check.torproject.org/"]["summary"][
                "ok"
            ]
        )
        guard_only = profiles["arti_release_browser_guardonly_healthyovercold4"]
        self.assertFalse(guard_only["arti_exit_select_load_aware"])
        self.assertFalse(guard_only["arti_exit_select_health_aware"])
        self.assertEqual(
            guard_only[
                "arti_exit_select_healthy_over_cold_guard_only_min_assigned"
            ],
            4,
        )
        self.assertTrue(
            guard_only["benchmarks"]["https://check.torproject.org/"]["summary"][
                "ok"
            ]
        )

    def test_extra_socks_connect_hedge_inherits_healthy_over_cold_base(self) -> None:
        def fake_browser_once(**kwargs):
            return {
                "ok": True,
                "elapsed_ms": 1000 + kwargs["port"],
                "load_ms": 800 + kwargs["port"],
                "screenshot": {"bytes": 100},
                "performance_timing": {},
            }

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            browser = root / "firefox"
            bundled = root / "bundled-tor"
            local = root / "tor"
            arti = root / "arti"
            for path in (browser, bundled, local, arti):
                path.write_text("", encoding="utf-8")

            with (
                patch(
                    "run_browser_compare.warmup_proxy",
                    return_value={"ok": True, "seconds": 0.1},
                ),
                patch(
                    "run_browser_compare.start_proxy_for_spec",
                    return_value=(object(), queue.Queue()),
                ),
                patch(
                    "run_browser_compare.wait_for_line",
                    return_value={"ok": True, "seconds": 0.2},
                ),
                patch("run_browser_compare.stop_process"),
                patch("run_browser_compare.read_torrc_quality", return_value={}),
                patch("run_browser_compare.run_browser_once", side_effect=fake_browser_once),
            ):
                profiles = run_interleaved_profiles(
                    bundled_tor_bin=bundled,
                    tor_bin=local,
                    arti_bin=arti,
                    ports={
                        "bundled_c_tor_browser": 19080,
                        "local_c_tor_browser": 19081,
                        "arti_release_browser": 19082,
                    },
                    output_dir=root / "out",
                    browser_bin=browser,
                    targets=["https://check.torproject.org/"],
                    runs=1,
                    timeout=1.0,
                    window_size="1000,1000",
                    warm_cache=True,
                    arti_exit_select_healthy_over_cold_min_assigned=1,
                    extra_arti_socks_connect_hedge_ms=[500],
                    extra_arti_port_start=19083,
                    include_bundled_tor=False,
                )

        base = profiles["arti_release_browser"]
        hedged = profiles["arti_release_browser_connecthedge500ms"]
        self.assertEqual(
            base["arti_exit_select_healthy_over_cold_min_assigned"], 1
        )
        self.assertIsNone(base["arti_socks_connect_hedge_ms"])
        self.assertEqual(
            hedged["arti_exit_select_healthy_over_cold_min_assigned"], 1
        )
        self.assertTrue(hedged["arti_exit_select_load_aware"])
        self.assertEqual(hedged["arti_socks_connect_hedge_ms"], 500)
        self.assertTrue(
            hedged["benchmarks"]["https://check.torproject.org/"]["summary"]["ok"]
        )

    def test_interleaved_schedule_can_add_extra_arti_select_active_cap_profile(
        self,
    ) -> None:
        calls = []

        def fake_browser_once(**kwargs):
            calls.append((kwargs["port"], kwargs["run_index"]))
            return {
                "ok": True,
                "elapsed_ms": 1000 + len(calls),
                "load_ms": 800 + len(calls),
                "screenshot": {"bytes": 100},
                "performance_timing": {},
            }

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            browser = root / "firefox"
            bundled = root / "bundled-tor"
            local = root / "tor"
            arti = root / "arti"
            for path in (browser, bundled, local, arti):
                path.write_text("", encoding="utf-8")

            with (
                patch(
                    "run_browser_compare.warmup_proxy",
                    return_value={"ok": True, "seconds": 0.1},
                ),
                patch(
                    "run_browser_compare.start_proxy_for_spec",
                    return_value=(object(), queue.Queue()),
                ),
                patch(
                    "run_browser_compare.wait_for_line",
                    return_value={"ok": True, "seconds": 0.2},
                ),
                patch("run_browser_compare.stop_process"),
                patch("run_browser_compare.read_torrc_quality", return_value={}),
                patch("run_browser_compare.run_browser_once", side_effect=fake_browser_once),
            ):
                profiles = run_interleaved_profiles(
                    bundled_tor_bin=bundled,
                    tor_bin=local,
                    arti_bin=arti,
                    ports={
                        "bundled_c_tor_browser": 19080,
                        "local_c_tor_browser": 19081,
                        "arti_release_browser": 19082,
                    },
                    output_dir=root / "out",
                    browser_bin=browser,
                    targets=["https://check.torproject.org/"],
                    runs=1,
                    timeout=1.0,
                    window_size="1000,1000",
                    warm_cache=True,
                    extra_arti_exit_select_max_active_streams=[2],
                    extra_arti_port_start=19083,
                )

        self.assertEqual(
            calls,
            [(19080, 1), (19081, 1), (19082, 1), (19083, 1)],
        )
        self.assertFalse(profiles["arti_release_browser"]["arti_exit_select_load_aware"])
        self.assertIsNone(
            profiles["arti_release_browser"]["arti_exit_select_max_active_streams"]
        )
        profile = profiles["arti_release_browser_loadaware_activecap2"]
        self.assertTrue(profile["arti_exit_select_load_aware"])
        self.assertFalse(profile["arti_exit_select_health_aware"])
        self.assertFalse(profile["arti_exit_select_avoid_bad_health"])
        self.assertEqual(profile["arti_exit_select_max_active_streams"], 2)
        self.assertTrue(
            profile["benchmarks"]["https://check.torproject.org/"]["summary"]["ok"]
        )

    def test_interleaved_schedule_can_add_extra_partial_retry_chunk_active_cap_profile(
        self,
    ) -> None:
        calls = []

        def fake_browser_once(**kwargs):
            calls.append((kwargs["port"], kwargs["run_index"]))
            return {
                "ok": True,
                "elapsed_ms": 1000 + len(calls),
                "load_ms": 800 + len(calls),
                "screenshot": {"bytes": 100},
                "performance_timing": {},
            }

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            browser = root / "firefox"
            bundled = root / "bundled-tor"
            local = root / "tor"
            arti = root / "arti"
            for path in (browser, bundled, local, arti):
                path.write_text("", encoding="utf-8")

            with (
                patch(
                    "run_browser_compare.warmup_proxy",
                    return_value={"ok": True, "seconds": 0.1},
                ),
                patch(
                    "run_browser_compare.start_proxy_for_spec",
                    return_value=(object(), queue.Queue()),
                ),
                patch(
                    "run_browser_compare.wait_for_line",
                    return_value={"ok": True, "seconds": 0.2},
                ),
                patch("run_browser_compare.stop_process"),
                patch("run_browser_compare.read_torrc_quality", return_value={}),
                patch("run_browser_compare.run_browser_once", side_effect=fake_browser_once),
            ):
                profiles = run_interleaved_profiles(
                    bundled_tor_bin=bundled,
                    tor_bin=local,
                    arti_bin=arti,
                    ports={
                        "bundled_c_tor_browser": 19080,
                        "local_c_tor_browser": 19081,
                        "arti_release_browser": 19082,
                    },
                    output_dir=root / "out",
                    browser_bin=browser,
                    targets=["https://check.torproject.org/"],
                    runs=1,
                    timeout=1.0,
                    window_size="1000,1000",
                    warm_cache=True,
                    extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_partial_retry_chunking_max_active_streams=[
                        2
                    ],
                    extra_arti_port_start=19083,
                )

        self.assertEqual(
            calls,
            [(19080, 1), (19081, 1), (19082, 1), (19083, 1)],
        )
        self.assertFalse(profiles["arti_release_browser"]["arti_exit_select_load_aware"])
        self.assertFalse(
            profiles["arti_release_browser"]["arti_dir_microdesc_partial_retry_chunking"]
        )
        self.assertIsNone(
            profiles["arti_release_browser"]["arti_exit_select_max_active_streams"]
        )
        profile = profiles[
            "arti_release_browser_"
            "mdsrcspreadpendingearlyusable_partialretrychunk_"
            "activecap2"
        ]
        self.assertFalse(profile["arti_exit_select_load_aware"])
        self.assertFalse(profile["arti_exit_select_health_aware"])
        self.assertFalse(profile["arti_exit_select_avoid_bad_health"])
        self.assertTrue(profile["arti_dir_microdesc_early_usable_notify"])
        self.assertTrue(profile["arti_dir_microdesc_partial_retry_chunking"])
        self.assertTrue(profile["arti_dir_microdesc_source_spread"])
        self.assertTrue(profile["arti_dir_microdesc_pending_spread"])
        self.assertEqual(profile["arti_dir_microdesc_retry_ids_per_request"], 250)
        self.assertEqual(profile["arti_dir_microdesc_retry_delay_max_ms"], 500)
        self.assertEqual(profile["arti_exit_select_max_active_streams"], 2)
        self.assertTrue(
            profile["benchmarks"]["https://check.torproject.org/"]["summary"]["ok"]
        )

    def test_interleaved_schedule_can_add_extra_load_aware_partial_retry_chunk_active_cap_profile(
        self,
    ) -> None:
        calls = []

        def fake_browser_once(**kwargs):
            calls.append((kwargs["port"], kwargs["run_index"]))
            return {
                "ok": True,
                "elapsed_ms": 1000 + len(calls),
                "load_ms": 800 + len(calls),
                "screenshot": {"bytes": 100},
                "performance_timing": {},
            }

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            browser = root / "firefox"
            bundled = root / "bundled-tor"
            local = root / "tor"
            arti = root / "arti"
            for path in (browser, bundled, local, arti):
                path.write_text("", encoding="utf-8")

            with (
                patch(
                    "run_browser_compare.warmup_proxy",
                    return_value={"ok": True, "seconds": 0.1},
                ),
                patch(
                    "run_browser_compare.start_proxy_for_spec",
                    return_value=(object(), queue.Queue()),
                ),
                patch(
                    "run_browser_compare.wait_for_line",
                    return_value={"ok": True, "seconds": 0.2},
                ),
                patch("run_browser_compare.stop_process"),
                patch("run_browser_compare.read_torrc_quality", return_value={}),
                patch("run_browser_compare.run_browser_once", side_effect=fake_browser_once),
            ):
                profiles = run_interleaved_profiles(
                    bundled_tor_bin=bundled,
                    tor_bin=local,
                    arti_bin=arti,
                    ports={
                        "bundled_c_tor_browser": 19080,
                        "local_c_tor_browser": 19081,
                        "arti_release_browser": 19082,
                    },
                    output_dir=root / "out",
                    browser_bin=browser,
                    targets=["https://check.torproject.org/"],
                    runs=1,
                    timeout=1.0,
                    window_size="1000,1000",
                    warm_cache=True,
                    extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_partial_retry_chunking_max_active_streams=[
                        3
                    ],
                    extra_arti_port_start=19083,
                )

        self.assertEqual(
            calls,
            [(19080, 1), (19081, 1), (19082, 1), (19083, 1)],
        )
        self.assertFalse(profiles["arti_release_browser"]["arti_exit_select_load_aware"])
        self.assertFalse(
            profiles["arti_release_browser"]["arti_dir_microdesc_partial_retry_chunking"]
        )
        self.assertIsNone(
            profiles["arti_release_browser"]["arti_exit_select_max_active_streams"]
        )
        profile = profiles[
            "arti_release_browser_"
            "mdsrcspreadpendingearlyusable_loadaware_partialretrychunk_"
            "activecap3"
        ]
        self.assertTrue(profile["arti_dir_microdesc_early_usable_notify"])
        self.assertTrue(profile["arti_dir_microdesc_partial_retry_chunking"])
        self.assertTrue(profile["arti_dir_microdesc_source_spread"])
        self.assertTrue(profile["arti_dir_microdesc_pending_spread"])
        self.assertEqual(profile["arti_dir_microdesc_retry_ids_per_request"], 250)
        self.assertEqual(profile["arti_dir_microdesc_retry_delay_max_ms"], 500)
        self.assertTrue(profile["arti_exit_select_load_aware"])
        self.assertFalse(profile["arti_exit_select_health_aware"])
        self.assertFalse(profile["arti_exit_select_avoid_bad_health"])
        self.assertEqual(profile["arti_exit_select_max_active_streams"], 3)
        self.assertTrue(
            profile["benchmarks"]["https://check.torproject.org/"]["summary"]["ok"]
        )

    def test_interleaved_schedule_can_add_extra_assigned_cap_profile(self) -> None:
        calls = []

        def fake_browser_once(**kwargs):
            calls.append((kwargs["port"], kwargs["run_index"]))
            return {
                "ok": True,
                "elapsed_ms": 1000 + len(calls),
                "load_ms": 800 + len(calls),
                "screenshot": {"bytes": 100},
                "performance_timing": {},
            }

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            browser = root / "firefox"
            bundled = root / "bundled-tor"
            local = root / "tor"
            arti = root / "arti"
            for path in (browser, bundled, local, arti):
                path.write_text("", encoding="utf-8")

            with (
                patch(
                    "run_browser_compare.warmup_proxy",
                    return_value={"ok": True, "seconds": 0.1},
                ),
                patch(
                    "run_browser_compare.start_proxy_for_spec",
                    return_value=(object(), queue.Queue()),
                ),
                patch(
                    "run_browser_compare.wait_for_line",
                    return_value={"ok": True, "seconds": 0.2},
                ),
                patch("run_browser_compare.stop_process"),
                patch("run_browser_compare.read_torrc_quality", return_value={}),
                patch("run_browser_compare.run_browser_once", side_effect=fake_browser_once),
            ):
                profiles = run_interleaved_profiles(
                    bundled_tor_bin=bundled,
                    tor_bin=local,
                    arti_bin=arti,
                    ports={
                        "bundled_c_tor_browser": 19080,
                        "local_c_tor_browser": 19081,
                        "arti_release_browser": 19082,
                    },
                    output_dir=root / "out",
                    browser_bin=browser,
                    targets=["https://check.torproject.org/"],
                    runs=1,
                    timeout=1.0,
                    window_size="1000,1000",
                    warm_cache=True,
                    extra_arti_exit_select_max_assigned_streams=[4],
                    extra_arti_port_start=19083,
                )

        self.assertEqual(
            calls,
            [(19080, 1), (19081, 1), (19082, 1), (19083, 1)],
        )
        self.assertFalse(profiles["arti_release_browser"]["arti_exit_select_load_aware"])
        self.assertIsNone(
            profiles["arti_release_browser"]["arti_exit_select_max_assigned_streams"]
        )
        profile = profiles["arti_release_browser_loadaware_assignedcap4"]
        self.assertTrue(profile["arti_exit_select_load_aware"])
        self.assertFalse(profile["arti_exit_select_health_aware"])
        self.assertFalse(profile["arti_exit_select_avoid_bad_health"])
        self.assertEqual(profile["arti_exit_select_max_assigned_streams"], 4)
        self.assertTrue(
            profile["benchmarks"]["https://check.torproject.org/"]["summary"]["ok"]
        )

    def test_interleaved_schedule_can_add_extra_health_min_assigned_cap_profile(
        self,
    ) -> None:
        calls = []

        def fake_browser_once(**kwargs):
            calls.append((kwargs["port"], kwargs["run_index"]))
            return {
                "ok": True,
                "elapsed_ms": 1000 + len(calls),
                "load_ms": 800 + len(calls),
                "screenshot": {"bytes": 100},
                "performance_timing": {},
            }

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            browser = root / "firefox"
            bundled = root / "bundled-tor"
            local = root / "tor"
            arti = root / "arti"
            for path in (browser, bundled, local, arti):
                path.write_text("", encoding="utf-8")

            with (
                patch(
                    "run_browser_compare.warmup_proxy",
                    return_value={"ok": True, "seconds": 0.1},
                ),
                patch(
                    "run_browser_compare.start_proxy_for_spec",
                    return_value=(object(), queue.Queue()),
                ),
                patch(
                    "run_browser_compare.wait_for_line",
                    return_value={"ok": True, "seconds": 0.2},
                ),
                patch("run_browser_compare.stop_process"),
                patch("run_browser_compare.read_torrc_quality", return_value={}),
                patch("run_browser_compare.run_browser_once", side_effect=fake_browser_once),
            ):
                profiles = run_interleaved_profiles(
                    bundled_tor_bin=bundled,
                    tor_bin=local,
                    arti_bin=arti,
                    ports={
                        "bundled_c_tor_browser": 19080,
                        "local_c_tor_browser": 19081,
                        "arti_release_browser": 19082,
                    },
                    output_dir=root / "out",
                    browser_bin=browser,
                    targets=["https://check.torproject.org/"],
                    runs=1,
                    timeout=1.0,
                    window_size="1000,1000",
                    warm_cache=True,
                    extra_arti_exit_select_health_min_move_score_assigned_cap=[
                        (16000, 4)
                    ],
                    extra_arti_port_start=19083,
                )

        self.assertEqual(
            calls,
            [(19080, 1), (19081, 1), (19082, 1), (19083, 1)],
        )
        self.assertFalse(profiles["arti_release_browser"]["arti_exit_select_load_aware"])
        profile = profiles["arti_release_browser_healthaware_min16000bps_assignedcap4"]
        self.assertTrue(profile["arti_exit_select_load_aware"])
        self.assertTrue(profile["arti_exit_select_health_aware"])
        self.assertEqual(profile["arti_exit_select_health_min_move_score_bps"], 16000)
        self.assertEqual(profile["arti_exit_select_max_assigned_streams"], 4)
        self.assertTrue(
            profile["benchmarks"]["https://check.torproject.org/"]["summary"]["ok"]
        )

    def test_interleaved_schedule_can_add_extra_same_iso_other_iso_assigned_cap_profile(
        self,
    ) -> None:
        calls = []

        def fake_browser_once(**kwargs):
            calls.append((kwargs["port"], kwargs["run_index"]))
            return {
                "ok": True,
                "elapsed_ms": 1000 + len(calls),
                "load_ms": 800 + len(calls),
                "screenshot": {"bytes": 100},
                "performance_timing": {},
            }

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            browser = root / "firefox"
            bundled = root / "bundled-tor"
            local = root / "tor"
            arti = root / "arti"
            for path in (browser, bundled, local, arti):
                path.write_text("", encoding="utf-8")

            with (
                patch(
                    "run_browser_compare.warmup_proxy",
                    return_value={"ok": True, "seconds": 0.1},
                ),
                patch(
                    "run_browser_compare.start_proxy_for_spec",
                    return_value=(object(), queue.Queue()),
                ),
                patch(
                    "run_browser_compare.wait_for_line",
                    return_value={"ok": True, "seconds": 0.2},
                ),
                patch("run_browser_compare.stop_process"),
                patch("run_browser_compare.read_torrc_quality", return_value={}),
                patch("run_browser_compare.run_browser_once", side_effect=fake_browser_once),
            ):
                profiles = run_interleaved_profiles(
                    bundled_tor_bin=bundled,
                    tor_bin=local,
                    arti_bin=arti,
                    ports={
                        "bundled_c_tor_browser": 19080,
                        "local_c_tor_browser": 19081,
                        "arti_release_browser": 19082,
                    },
                    output_dir=root / "out",
                    browser_bin=browser,
                    targets=["https://check.torproject.org/"],
                    runs=1,
                    timeout=1.0,
                    window_size="1000,1000",
                    warm_cache=True,
                    extra_arti_exit_same_isolation_other_isolation_pressure_assigned_cap=[
                        (2, 3, 4)
                    ],
                    extra_arti_port_start=19083,
                )

        self.assertEqual(
            calls,
            [(19080, 1), (19081, 1), (19082, 1), (19083, 1)],
        )
        self.assertFalse(profiles["arti_release_browser"]["arti_exit_select_load_aware"])
        self.assertIsNone(
            profiles["arti_release_browser"]["arti_exit_select_max_assigned_streams"]
        )
        profile = profiles["arti_release_browser_sameiso2_otheriso3_assignedcap4"]
        self.assertFalse(profile["arti_exit_select_load_aware"])
        self.assertEqual(profile["arti_exit_same_isolation_target"], 2)
        self.assertEqual(
            profile["arti_exit_same_isolation_other_isolation_min"], 3
        )
        self.assertEqual(profile["arti_exit_select_max_assigned_streams"], 4)
        self.assertTrue(
            profile["benchmarks"]["https://check.torproject.org/"]["summary"]["ok"]
        )

    def test_interleaved_schedule_can_add_extra_same_iso_other_iso_assigned_cap_prewarm_profile(
        self,
    ) -> None:
        calls = []

        def fake_browser_once(**kwargs):
            calls.append((kwargs["port"], kwargs["run_index"]))
            return {
                "ok": True,
                "elapsed_ms": 1000 + len(calls),
                "load_ms": 800 + len(calls),
                "screenshot": {"bytes": 100},
                "performance_timing": {},
            }

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            browser = root / "firefox"
            bundled = root / "bundled-tor"
            local = root / "tor"
            arti = root / "arti"
            for path in (browser, bundled, local, arti):
                path.write_text("", encoding="utf-8")

            with (
                patch(
                    "run_browser_compare.warmup_proxy",
                    return_value={"ok": True, "seconds": 0.1},
                ),
                patch(
                    "run_browser_compare.start_proxy_for_spec",
                    return_value=(object(), queue.Queue()),
                ),
                patch(
                    "run_browser_compare.wait_for_line",
                    return_value={"ok": True, "seconds": 0.2},
                ),
                patch("run_browser_compare.stop_process"),
                patch("run_browser_compare.read_torrc_quality", return_value={}),
                patch("run_browser_compare.run_browser_once", side_effect=fake_browser_once),
            ):
                profiles = run_interleaved_profiles(
                    bundled_tor_bin=bundled,
                    tor_bin=local,
                    arti_bin=arti,
                    ports={
                        "bundled_c_tor_browser": 19080,
                        "local_c_tor_browser": 19081,
                        "arti_release_browser": 19082,
                    },
                    output_dir=root / "out",
                    browser_bin=browser,
                    targets=["https://check.torproject.org/"],
                    runs=1,
                    timeout=1.0,
                    window_size="1000,1000",
                    warm_cache=True,
                    extra_arti_exit_same_isolation_other_isolation_pressure_assigned_cap_prewarm=[
                        (2, 3, 4)
                    ],
                    extra_arti_port_start=19083,
                )

        self.assertEqual(
            calls,
            [(19080, 1), (19081, 1), (19082, 1), (19083, 1)],
        )
        self.assertFalse(profiles["arti_release_browser"]["arti_exit_select_load_aware"])
        self.assertFalse(
            profiles["arti_release_browser"]["arti_exit_same_isolation_prewarm_first_stream"]
        )
        profile = profiles[
            "arti_release_browser_sameiso2_otheriso3_assignedcap4_prewarmfirst"
        ]
        self.assertFalse(profile["arti_exit_select_load_aware"])
        self.assertEqual(profile["arti_exit_same_isolation_target"], 2)
        self.assertEqual(
            profile["arti_exit_same_isolation_other_isolation_min"], 3
        )
        self.assertEqual(profile["arti_exit_select_max_assigned_streams"], 4)
        self.assertTrue(profile["arti_exit_same_isolation_prewarm_first_stream"])
        self.assertTrue(
            profile["benchmarks"]["https://check.torproject.org/"]["summary"]["ok"]
        )

    def test_interleaved_schedule_can_add_extra_active_no_data_bad_health_profile(
        self,
    ) -> None:
        calls = []

        def fake_browser_once(**kwargs):
            calls.append((kwargs["port"], kwargs["run_index"]))
            return {
                "ok": True,
                "elapsed_ms": 1000 + len(calls),
                "load_ms": 800 + len(calls),
                "screenshot": {"bytes": 100},
                "performance_timing": {},
            }

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            browser = root / "firefox"
            bundled = root / "bundled-tor"
            local = root / "tor"
            arti = root / "arti"
            for path in (browser, bundled, local, arti):
                path.write_text("", encoding="utf-8")

            with (
                patch(
                    "run_browser_compare.warmup_proxy",
                    return_value={"ok": True, "seconds": 0.1},
                ),
                patch(
                    "run_browser_compare.start_proxy_for_spec",
                    return_value=(object(), queue.Queue()),
                ),
                patch(
                    "run_browser_compare.wait_for_line",
                    return_value={"ok": True, "seconds": 0.2},
                ),
                patch("run_browser_compare.stop_process"),
                patch("run_browser_compare.read_torrc_quality", return_value={}),
                patch("run_browser_compare.run_browser_once", side_effect=fake_browser_once),
            ):
                profiles = run_interleaved_profiles(
                    bundled_tor_bin=bundled,
                    tor_bin=local,
                    arti_bin=arti,
                    ports={
                        "bundled_c_tor_browser": 19080,
                        "local_c_tor_browser": 19081,
                        "arti_release_browser": 19082,
                    },
                    output_dir=root / "out",
                    browser_bin=browser,
                    targets=["https://check.torproject.org/"],
                    runs=1,
                    timeout=1.0,
                    window_size="1000,1000",
                    warm_cache=True,
                    extra_arti_exit_select_bad_health_active_no_data_ms=[5000],
                    extra_arti_port_start=19083,
                )

        self.assertEqual(
            calls,
            [(19080, 1), (19081, 1), (19082, 1), (19083, 1)],
        )
        self.assertFalse(profiles["arti_release_browser"]["arti_exit_select_load_aware"])
        self.assertIsNone(
            profiles["arti_release_browser"][
                "arti_exit_select_bad_health_active_no_data_ms"
            ]
        )
        profile = profiles["arti_release_browser_loadaware_activenodata5000ms"]
        self.assertTrue(profile["arti_exit_select_load_aware"])
        self.assertTrue(profile["arti_exit_select_avoid_bad_health"])
        self.assertEqual(
            profile["arti_exit_select_bad_health_active_no_data_ms"], 5000
        )
        self.assertTrue(
            profile["benchmarks"]["https://check.torproject.org/"]["summary"]["ok"]
        )

    def test_interleaved_schedule_can_skip_bundled_tor(self) -> None:
        calls = []

        def fake_browser_once(**kwargs):
            calls.append(kwargs["port"])
            return {
                "ok": True,
                "elapsed_ms": 1000 + len(calls),
                "load_ms": 800 + len(calls),
                "screenshot": {"bytes": 100},
                "performance_timing": {},
            }

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            browser = root / "firefox"
            bundled = root / "bundled-tor"
            local = root / "tor"
            arti = root / "arti"
            for path in (browser, bundled, local, arti):
                path.write_text("", encoding="utf-8")

            with (
                patch(
                    "run_browser_compare.warmup_proxy",
                    return_value={"ok": True, "seconds": 0.1},
                ),
                patch(
                    "run_browser_compare.start_proxy_for_spec",
                    return_value=(object(), queue.Queue()),
                ),
                patch(
                    "run_browser_compare.wait_for_line",
                    return_value={"ok": True, "seconds": 0.2},
                ),
                patch("run_browser_compare.stop_process"),
                patch("run_browser_compare.read_torrc_quality", return_value={}),
                patch("run_browser_compare.run_browser_once", side_effect=fake_browser_once),
            ):
                profiles = run_interleaved_profiles(
                    bundled_tor_bin=bundled,
                    tor_bin=local,
                    arti_bin=arti,
                    ports={
                        "bundled_c_tor_browser": 19080,
                        "local_c_tor_browser": 19081,
                        "arti_release_browser": 19082,
                    },
                    output_dir=root / "out",
                    browser_bin=browser,
                    targets=["https://check.torproject.org/"],
                    runs=1,
                    timeout=1.0,
                    window_size="1000,1000",
                    warm_cache=True,
                    include_bundled_tor=False,
                )

        self.assertEqual(calls, [19081, 19082])
        self.assertTrue(profiles["bundled_c_tor_browser"]["skipped"])
        self.assertEqual(
            profiles["bundled_c_tor_browser"]["reason"],
            "disabled by --skip-bundled-tor",
        )

    def test_interleaved_schedule_can_add_extra_arti_binary(self) -> None:
        calls = []

        def fake_browser_once(**kwargs):
            calls.append((kwargs["port"], kwargs["run_index"]))
            return {
                "ok": True,
                "elapsed_ms": 1000 + len(calls),
                "load_ms": 800 + len(calls),
                "screenshot": {"bytes": 100},
                "performance_timing": {},
            }

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            browser = root / "firefox"
            bundled = root / "bundled-tor"
            local = root / "tor"
            arti = root / "arti"
            flowctl = root / "arti-flowctl"
            for path in (browser, bundled, local, arti, flowctl):
                path.write_text("", encoding="utf-8")

            with (
                patch(
                    "run_browser_compare.warmup_proxy",
                    return_value={"ok": True, "seconds": 0.1},
                ),
                patch(
                    "run_browser_compare.start_proxy_for_spec",
                    return_value=(object(), queue.Queue()),
                ),
                patch(
                    "run_browser_compare.wait_for_line",
                    return_value={"ok": True, "seconds": 0.2},
                ),
                patch("run_browser_compare.stop_process"),
                patch("run_browser_compare.read_torrc_quality", return_value={}),
                patch(
                    "run_browser_compare.binary_info",
                    side_effect=lambda path: {"path": str(path), "exists": True},
                ),
                patch("run_browser_compare.run_browser_once", side_effect=fake_browser_once),
            ):
                profiles = run_interleaved_profiles(
                    bundled_tor_bin=bundled,
                    tor_bin=local,
                    arti_bin=arti,
                    ports={
                        "bundled_c_tor_browser": 19080,
                        "local_c_tor_browser": 19081,
                        "arti_release_browser": 19082,
                    },
                    output_dir=root / "out",
                    browser_bin=browser,
                    targets=["https://check.torproject.org/"],
                    runs=1,
                    timeout=1.0,
                    window_size="1000,1000",
                    warm_cache=True,
                    include_bundled_tor=False,
                    extra_arti_bins=[
                        ("arti_release_browser_flowctl", flowctl.resolve())
                    ],
                    extra_arti_port_start=19083,
                )

        self.assertEqual(calls, [(19081, 1), (19082, 1), (19083, 1)])
        self.assertEqual(
            profiles["arti_release_browser_flowctl"]["arti_bin"],
            str(flowctl.resolve()),
        )
        self.assertEqual(
            profiles["arti_release_browser_flowctl"]["binary"],
            {"path": str(flowctl.resolve()), "exists": True},
        )

    def test_interleaved_schedule_can_add_extra_arti_scheduler_burst_profile(
        self,
    ) -> None:
        calls = []

        def fake_browser_once(**kwargs):
            calls.append((kwargs["port"], kwargs["run_index"]))
            return {
                "ok": True,
                "elapsed_ms": 1000 + len(calls),
                "load_ms": 800 + len(calls),
                "screenshot": {"bytes": 100},
                "performance_timing": {},
            }

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            browser = root / "firefox"
            bundled = root / "bundled-tor"
            local = root / "tor"
            arti = root / "arti"
            for path in (browser, bundled, local, arti):
                path.write_text("", encoding="utf-8")

            with (
                patch(
                    "run_browser_compare.warmup_proxy",
                    return_value={"ok": True, "seconds": 0.1},
                ),
                patch(
                    "run_browser_compare.start_proxy_for_spec",
                    return_value=(object(), queue.Queue()),
                ),
                patch(
                    "run_browser_compare.wait_for_line",
                    return_value={"ok": True, "seconds": 0.2},
                ),
                patch("run_browser_compare.stop_process"),
                patch("run_browser_compare.read_torrc_quality", return_value={}),
                patch(
                    "run_browser_compare.run_browser_once",
                    side_effect=fake_browser_once,
                ),
            ):
                profiles = run_interleaved_profiles(
                    bundled_tor_bin=bundled,
                    tor_bin=local,
                    arti_bin=arti,
                    ports={
                        "bundled_c_tor_browser": 19080,
                        "local_c_tor_browser": 19081,
                        "arti_release_browser": 19082,
                    },
                    output_dir=root / "out",
                    browser_bin=browser,
                    targets=["https://check.torproject.org/"],
                    runs=1,
                    timeout=1.0,
                    window_size="1000,1000",
                    warm_cache=True,
                    include_bundled_tor=False,
                    extra_arti_stream_scheduler_burst=[2],
                    extra_arti_port_start=19083,
                )

        self.assertEqual(calls, [(19081, 1), (19082, 1), (19083, 1)])
        self.assertEqual(
            profiles["arti_release_browser_schedburst2"][
                "arti_stream_scheduler_burst"
            ],
            2,
        )

    def test_counts_proxy_log_signals(self) -> None:
        signals = count_proxy_log_signals(
            [
                "Got a socks request: CONNECT [scrubbed]:443",
                "Got a circuit for [scrubbed]:443 tunnel_id=Circ 1.0",
                "Got a stream for [scrubbed]:443",
                "Preemptive circuit was created for Preemptive {...}",
                "Spawning reactor...",
                "hs conn to [...]onion: obtaining intro circuit",
                "timing_id=1 elapsed_ms=3 torfast socks timing request parsed",
                "kind=GUARDED launch_ms=100 torfast hspool background circuit ready",
                "intro_index=IntroPtIndex(2) elapsed_ms=200 torfast hs timing rendezvous2 received",
                "elapsed_ms=20 torfast hs client timing tunnel ready",
                "elapsed_ms=2210 ok=true torfast hs state timing connect task finished",
                "elapsed_ms=20 torfast exit client timing tunnel ready",
                "stream_id=12 relay_cmd=DATA torfast relay receive delivered",
                "stream_id=12 relay_cmd=DATA torfast stream scheduler picked",
                "stream_id=12 transfer_ms=6000 torfast stream receiver terminal summary",
                "stream_id=12 relay_cmd=DATA torfast stream reactor congestion blocked",
                "stream_id=12 relay_cmd=DATA delivery=delivered torfast stream lifecycle",
                "channel_id=Chan 3 channel_cmd=ChanCmd(RELAY) delivery=channel_flushed torfast channel flush",
                "circ_id=Circ 1.0 hop=#3 algorithm=vegas can_send=true torfast circuit congestion sendme sent",
                "open_candidates=3 torfast circuit selection open",
                "timing_id=1 direction=tor_to_client torfast socks byte event",
            ]
        )

        self.assertEqual(signals["socks_connect"], 1)
        self.assertEqual(signals["circuit_assigned"], 1)
        self.assertEqual(signals["stream_ready"], 1)
        self.assertEqual(signals["preemptive_circuits"], 1)
        self.assertEqual(signals["spawned_reactors"], 1)
        self.assertEqual(signals["hs_connects"], 1)
        self.assertEqual(signals["torfast_socks_timings"], 1)
        self.assertEqual(signals["torfast_socks_byte_events"], 1)
        self.assertEqual(signals["torfast_relay_receive_timings"], 1)
        self.assertEqual(signals["torfast_stream_scheduler_timings"], 1)
        self.assertEqual(signals["torfast_stream_receiver_timings"], 1)
        self.assertEqual(signals["torfast_stream_reactor_congestion_timings"], 1)
        self.assertEqual(signals["torfast_stream_lifecycle_timings"], 1)
        self.assertEqual(signals["torfast_channel_flush_timings"], 1)
        self.assertEqual(signals["torfast_circuit_congestion_timings"], 1)
        self.assertEqual(signals["torfast_circuit_selection_timings"], 1)
        self.assertEqual(signals["torfast_hspool_timings"], 1)
        self.assertEqual(signals["torfast_hs_timings"], 1)
        self.assertEqual(signals["torfast_hs_client_timings"], 1)
        self.assertEqual(signals["torfast_hs_state_timings"], 1)
        self.assertEqual(signals["torfast_exit_client_timings"], 1)

    def test_proxy_signal_lines_keeps_key_lines_without_relay_delivered_flood(
        self,
    ) -> None:
        lines = proxy_signal_lines(
            [
                "torfast relay receive delivered stream_id=1",
                "torfast relay receive queue full stream_id=1",
                "torfast circuit selection open usage_kind=exit",
                "torfast circuit congestion sendme received circ_id=Circ 1.0",
                "torfast stream receiver already closed stream_id=1",
                "torfast stream receiver no-end close stream_id=1",
                "torfast stream reactor congestion blocked stream_id=1",
                "torfast stream lifecycle stream_id=1 delivery=stream_gone",
                "elapsed_ms=2210 ok=true torfast hs state timing connect task finished",
                "ordinary line",
            ]
        )

        self.assertEqual(
            lines,
            [
                "torfast relay receive queue full stream_id=1",
                "torfast circuit selection open usage_kind=exit",
                "torfast circuit congestion sendme received circ_id=Circ 1.0",
                "torfast stream receiver already closed stream_id=1",
                "torfast stream receiver no-end close stream_id=1",
                "torfast stream reactor congestion blocked stream_id=1",
                "torfast stream lifecycle stream_id=1 delivery=stream_gone",
                "elapsed_ms=2210 ok=true torfast hs state timing connect task finished",
            ],
        )

    def test_boot_signal_lines_keep_boot_markers_without_stream_flood(self) -> None:
        lines = [
            "2026-06-09T05:35:40Z  INFO tor_proto::circuit::circhop: torfast stream lifecycle delivery=\"delivered\"",
            "2026-06-09T05:35:41Z  INFO tor_dirmgr::bootstrap: 1: Looking for a consensus. attempt=1",
            "2026-06-09T05:35:42Z  INFO torfast stream receiver terminal summary stream_id=7 transfer_ms=100 relay_data_bytes=500",
            "2026-06-09T05:35:43Z  INFO tor_dirmgr: Marked consensus usable.",
            "2026-06-09T05:35:44Z  INFO arti::subcommands::proxy: Sufficiently bootstrapped; proxy now functional.",
        ]

        signals = boot_signal_lines(lines)

        self.assertEqual(
            signals,
            [
                lines[1],
                lines[2],
                lines[3],
                lines[4],
            ],
        )

    def test_wait_for_line_returns_filtered_boot_signal_lines(self) -> None:
        lines: queue.Queue[str] = queue.Queue()
        lines.put(
            "2026-06-09T05:35:40Z  INFO tor_proto::circuit::circhop: torfast stream lifecycle delivery=\"delivered\""
        )
        lines.put(
            "2026-06-09T05:35:41Z  INFO tor_dirmgr::bootstrap: 1: Looking for a consensus. attempt=1"
        )
        lines.put(
            "2026-06-09T05:35:42Z  INFO arti::subcommands::proxy: Sufficiently bootstrapped; proxy now functional."
        )

        class FakeProcess:
            returncode = None

            def poll(self):
                return None

        boot = wait_for_line(
            FakeProcess(),
            lines,
            timeout=1.0,
            ready_text="proxy now functional",
            process_name="arti",
        )

        self.assertTrue(boot["ok"])
        self.assertEqual(len(boot["lines"]), 3)
        self.assertEqual(len(boot["signal_lines"]), 2)
        self.assertIn("Looking for a consensus", boot["signal_lines"][0])
        self.assertIn("proxy now functional", boot["signal_lines"][1])

    def test_interleaved_boot_seconds_are_normalized_from_launch(self) -> None:
        boot = {
            "ok": True,
            "seconds": 0.0,
            "ready_monotonic_seconds": 112.345,
        }

        normalize_interleaved_boot_seconds_from_launch(boot, 110.0)

        self.assertEqual(boot["seconds"], 2.345)
        self.assertEqual(boot["seconds_from_launch"], 2.345)
        self.assertEqual(boot["wait_seconds_after_launch_plan"], 0.0)

    def test_record_proxy_run_signals_keeps_middle_run_lines(self) -> None:
        lines: queue.Queue[str] = queue.Queue()
        lines.put("ordinary line")
        lines.put("timing_id=21 torfast socks timing request parsed")
        lines.put("stream_id=44 relay_cmd=DATA torfast relay receive delivered")
        lines.put("stream_id=44 torfast stream receiver read")
        lines.put("stream_id=44 relay_cmd=DATA torfast relay receive queue full")
        profile: dict[str, object] = {}
        run: dict[str, object] = {}

        record_proxy_run_signals(profile, run, lines)

        self.assertEqual(
            run["proxy_signal_lines"],
            [
                "timing_id=21 torfast socks timing request parsed",
                "stream_id=44 relay_cmd=DATA torfast relay receive queue full",
            ],
        )
        self.assertEqual(run["proxy_signal_lines"], profile["proxy_signal_lines"])
        self.assertEqual(
            run["proxy_relay_context_lines"],
            [
                "timing_id=21 torfast socks timing request parsed",
                "stream_id=44 relay_cmd=DATA torfast relay receive queue full",
                "stream_id=44 relay_cmd=DATA torfast relay receive delivered",
                "stream_id=44 torfast stream receiver read",
            ],
        )
        self.assertTrue(lines.empty())

    def test_record_proxy_run_signals_keeps_stream_link_for_late_relay_finish(
        self,
    ) -> None:
        lines: queue.Queue[str] = queue.Queue()
        lines.put(
            "timing_id=48 target_kind=hostname circ_id=Circ 3.16 hop=#3 stream_id=38312 torfast socks timing stream linked"
        )
        for index in range(1100):
            lines.put(f"timing_id={index} torfast socks timing request parsed")
        lines.put(
            "timing_id=48 target_kind=hostname relay_ms=11135 torfast socks timing relay finished"
        )
        profile: dict[str, object] = {}
        run: dict[str, object] = {"ok": True}

        record_proxy_run_signals(profile, run, lines)

        self.assertIn(
            "timing_id=48 target_kind=hostname circ_id=Circ 3.16 hop=#3 stream_id=38312 torfast socks timing stream linked",
            run["proxy_signal_lines"],
        )
        self.assertIn(
            "timing_id=48 target_kind=hostname relay_ms=11135 torfast socks timing relay finished",
            run["proxy_signal_lines"],
        )
        self.assertLessEqual(len(run["proxy_signal_lines"]), 1000)

    def test_record_proxy_run_signals_keeps_hs_state_rows_under_cap(self) -> None:
        lines: queue.Queue[str] = queue.Queue()
        hs_state = (
            "port=443 elapsed_ms=2212 "
            "torfast hs state timing client wrapper finished"
        )
        lines.put(hs_state)
        for index in range(1100):
            lines.put(f"timing_id={index} torfast socks timing request parsed")
        profile: dict[str, object] = {}
        run: dict[str, object] = {"ok": True}

        record_proxy_run_signals(profile, run, lines)

        self.assertIn(hs_state, run["proxy_signal_lines"])
        self.assertLessEqual(len(run["proxy_signal_lines"]), 1000)

    def test_record_proxy_run_signals_keeps_stream_link_for_terminal_stream(
        self,
    ) -> None:
        lines: queue.Queue[str] = queue.Queue()
        linked = (
            "timing_id=48 target_kind=hostname circ_id=Circ 3.16 hop=#3 "
            "stream_id=38312 torfast socks timing stream linked"
        )
        terminal = (
            "event_epoch_ms=1200 circ_id=Circ 3.16 (Tunnel 9) hop=#3 "
            "stream_id=38312 connected=true idle_after_last_data_ms=50000 "
            "torfast stream receiver terminal"
        )
        lines.put(linked)
        for index in range(1100):
            lines.put(f"timing_id={index} torfast socks timing request parsed")
        lines.put(terminal)
        profile: dict[str, object] = {}
        run: dict[str, object] = {"ok": True}

        record_proxy_run_signals(profile, run, lines)

        self.assertIn(linked, run["proxy_signal_lines"])
        self.assertIn(terminal, run["proxy_signal_lines"])
        self.assertLessEqual(len(run["proxy_signal_lines"]), 1000)

    def test_record_proxy_run_signals_keeps_socks_timing_for_terminal_stream(
        self,
    ) -> None:
        lines: queue.Queue[str] = queue.Queue()
        ready = (
            "timing_id=48 target_kind=hostname connect_ms=122 "
            "torfast socks timing stream ready"
        )
        linked = (
            "timing_id=48 target_kind=hostname circ_id=Circ 3.16 hop=#3 "
            "stream_id=38312 torfast socks timing stream linked"
        )
        reply = (
            "timing_id=48 target_kind=hostname elapsed_ms=123 "
            "torfast socks timing socks reply sent"
        )
        relay = (
            "timing_id=48 target_kind=hostname relay_ms=900 "
            "torfast socks timing relay finished"
        )
        terminal = (
            "event_epoch_ms=1200 circ_id=Circ 3.16 (Tunnel 9) hop=#3 "
            "stream_id=38312 connected=true idle_after_last_data_ms=50000 "
            "torfast stream receiver terminal"
        )
        for line in (ready, linked, reply, relay):
            lines.put(line)
        for index in range(1100):
            lines.put(f"timing_id={index} torfast socks timing request parsed")
        lines.put(terminal)
        profile: dict[str, object] = {}
        run: dict[str, object] = {"ok": True}

        record_proxy_run_signals(profile, run, lines)

        for line in (ready, linked, reply, relay, terminal):
            self.assertIn(line, run["proxy_signal_lines"])
        self.assertLessEqual(len(run["proxy_signal_lines"]), 1000)

    def test_record_proxy_run_signals_keeps_byte_events_for_terminal_stream(
        self,
    ) -> None:
        lines: queue.Queue[str] = queue.Queue()
        linked = (
            "timing_id=48 target_kind=hostname circ_id=Circ 3.16 hop=#3 "
            "stream_id=38312 torfast socks timing stream linked"
        )
        byte_event = (
            "timing_id=48 target_kind=hostname direction=tor_to_client_write "
            "event_index=1 elapsed_ms=400 event_epoch_ms=1400 "
            "write_bytes=498 cumulative_bytes=498 torfast socks byte event"
        )
        terminal = (
            "event_epoch_ms=2200 circ_id=Circ 3.16 (Tunnel 9) hop=#3 "
            "stream_id=38312 connected=true idle_after_last_data_ms=50000 "
            "torfast stream receiver terminal"
        )
        lines.put(linked)
        lines.put(byte_event)
        for index in range(1100):
            lines.put(f"timing_id={index} torfast socks timing request parsed")
        lines.put(terminal)
        profile: dict[str, object] = {}
        run: dict[str, object] = {"ok": True}

        record_proxy_run_signals(profile, run, lines)

        self.assertIn(linked, run["proxy_signal_lines"])
        self.assertIn(byte_event, run["proxy_signal_lines"])
        self.assertIn(terminal, run["proxy_signal_lines"])
        self.assertLessEqual(len(run["proxy_signal_lines"]), 1000)

    def test_record_proxy_run_signals_keeps_phase_rows_for_slow_connect(
        self,
    ) -> None:
        lines: queue.Queue[str] = queue.Queue()
        exit_tunnel = (
            "1970-01-01T00:00:02.500Z INFO arti_client::client: "
            "port=443 tunnel_unique_id=Circ 4.11 elapsed_ms=1500 "
            "torfast exit client timing tunnel ready"
        )
        exit_begin = (
            "1970-01-01T00:00:02.501Z INFO arti_client::client: "
            "port=443 tunnel_unique_id=Circ 4.11 elapsed_ms=1501 "
            "tunnel_elapsed_ms=1500 begin_phase_ms=1 ok=true "
            "torfast exit client timing begin stream finished"
        )
        hs_begin = (
            "1970-01-01T00:00:04.420Z INFO arti_client::client: "
            "port=443 elapsed_ms=2420 tunnel_elapsed_ms=1900 "
            "begin_phase_ms=520 ok=true "
            "torfast hs client timing begin stream finished"
        )
        hostname_ready = (
            "timing_id=7 target_kind=hostname command=CONNECT port=443 "
            "conn_started_epoch_ms=1000 connect_ms=1501 elapsed_ms=1501 "
            "torfast socks timing stream ready"
        )
        hostname_linked = (
            "timing_id=7 target_kind=hostname port=443 "
            "conn_started_epoch_ms=1000 circ_id=Circ 4.11 hop=#3 "
            "stream_id=10 elapsed_ms=1501 torfast socks timing stream linked"
        )
        onion_ready = (
            "timing_id=8 target_kind=onion command=CONNECT port=443 "
            "conn_started_epoch_ms=2000 connect_ms=2420 elapsed_ms=2420 "
            "torfast socks timing stream ready"
        )
        hostname_relay = (
            "timing_id=7 target_kind=hostname port=443 relay_ms=300 "
            "elapsed_ms=1801 ok=true torfast socks timing relay finished"
        )
        onion_relay = (
            "timing_id=8 target_kind=onion port=443 relay_ms=300 "
            "elapsed_ms=2720 ok=true torfast socks timing relay finished"
        )
        for line in (
            exit_tunnel,
            exit_begin,
            hs_begin,
            hostname_ready,
            hostname_linked,
            onion_ready,
        ):
            lines.put(line)
        for index in range(1100):
            lines.put(f"timing_id={index} torfast socks timing request parsed")
        lines.put(hostname_relay)
        lines.put(onion_relay)
        profile: dict[str, object] = {}
        run: dict[str, object] = {"ok": True}

        record_proxy_run_signals(profile, run, lines)

        for line in (
            exit_tunnel,
            exit_begin,
            hs_begin,
            hostname_ready,
            hostname_linked,
            onion_ready,
            hostname_relay,
            onion_relay,
        ):
            self.assertIn(line, run["proxy_signal_lines"])
        self.assertLessEqual(len(run["proxy_signal_lines"]), 1000)

    def test_record_proxy_run_signals_keeps_circuit_selection_context(self) -> None:
        lines: queue.Queue[str] = queue.Queue()
        selection = (
            "torfast circuit selection open usage_kind=exit "
            "selected_candidate_index_before_active_cap=0 "
            "selected_candidate_index=1 active_stream_cap_moved=true"
        )
        lines.put(selection)
        for index in range(1100):
            lines.put(f"torfast stream lifecycle stream_id={index} delivery=delivered")
        profile: dict[str, object] = {}
        run: dict[str, object] = {"ok": True}

        record_proxy_run_signals(profile, run, lines)

        self.assertIn(selection, run["proxy_signal_lines"])
        self.assertLessEqual(len(run["proxy_signal_lines"]), 1000)

    def test_record_proxy_run_signals_filters_to_run_time_window(self) -> None:
        lines: queue.Queue[str] = queue.Queue()
        old_line = (
            "event_epoch_ms=500 torfast circuit selection open usage_kind=exit"
        )
        in_run_line = (
            "event_epoch_ms=1500 torfast circuit selection open usage_kind=exit"
        )
        late_line = (
            "event_epoch_ms=7000 torfast circuit selection build failed "
            "usage_kind=exit"
        )
        iso_old_line = (
            "1970-01-01T00:00:00Z  INFO tor_circmgr::mgr: "
            "torfast circuit selection open usage_kind=exit"
        )
        iso_in_run_line = (
            "1970-01-01T00:00:01Z  INFO tor_circmgr::mgr: "
            "torfast circuit selection open usage_kind=exit"
        )
        iso_late_line = (
            "1970-01-01T00:00:07Z  INFO tor_circmgr::mgr: "
            "torfast circuit selection build failed usage_kind=exit"
        )
        no_epoch_line = "ordinary proxy info"
        lines.put(old_line)
        lines.put(in_run_line)
        lines.put(late_line)
        lines.put(iso_old_line)
        lines.put(iso_in_run_line)
        lines.put(iso_late_line)
        lines.put(no_epoch_line)
        profile: dict[str, object] = {}
        run: dict[str, object] = {
            "ok": False,
            "started_epoch_ms": 1000,
            "elapsed_ms": 2000,
        }

        record_proxy_run_signals(profile, run, lines)

        self.assertIn(in_run_line, run["proxy_signal_lines"])
        self.assertIn(iso_in_run_line, run["proxy_signal_lines"])
        self.assertNotIn(old_line, run["proxy_signal_lines"])
        self.assertNotIn(late_line, run["proxy_signal_lines"])
        self.assertNotIn(iso_old_line, run["proxy_signal_lines"])
        self.assertNotIn(iso_late_line, run["proxy_signal_lines"])
        self.assertEqual(
            run["proxy_output_tail"],
            [in_run_line, iso_in_run_line, no_epoch_line],
        )

    def test_record_proxy_run_signals_keeps_pre_run_selection_for_seen_circuit(
        self,
    ) -> None:
        lines: queue.Queue[str] = queue.Queue()
        matching_old_selection = (
            "1970-01-01T00:00:00Z INFO tor_circmgr::mgr: "
            "candidate_assignment_summary=0:Circ~2.9:1 "
            "usage_kind=\"exit\" tunnel_unique_id=Circ 2.9 "
            "torfast circuit selection open"
        )
        matching_old_build = (
            "1970-01-01T00:00:00Z INFO tor_circmgr::mgr: "
            "pending_id=0x9 pending_age_ms=540 usage_kind=exit "
            "tunnel_unique_id=Circ 2.9 "
            "torfast circuit selection build complete"
        )
        unrelated_old_selection = (
            "1970-01-01T00:00:00Z INFO tor_circmgr::mgr: "
            "usage_kind=\"exit\" tunnel_unique_id=Circ 8.1 "
            "torfast circuit selection open"
        )
        matching_late_selection = (
            "1970-01-01T00:00:07Z INFO tor_circmgr::mgr: "
            "usage_kind=\"exit\" tunnel_unique_id=Circ 2.9 "
            "torfast circuit selection open"
        )
        in_run_terminal = (
            "1970-01-01T00:00:01Z INFO tor_proto::client::stream::data: "
            "circ_id=Circ 2.9 hop=#4 stream_id=64350 "
            "error_kind=not_connected torfast stream receiver terminal summary"
        )
        lines.put(matching_old_selection)
        lines.put(matching_old_build)
        lines.put(unrelated_old_selection)
        lines.put(in_run_terminal)
        lines.put(matching_late_selection)
        profile: dict[str, object] = {}
        run: dict[str, object] = {
            "ok": False,
            "started_epoch_ms": 1000,
            "elapsed_ms": 2000,
        }

        record_proxy_run_signals(profile, run, lines)

        self.assertIn(matching_old_selection, run["proxy_signal_lines"])
        self.assertIn(matching_old_build, run["proxy_signal_lines"])
        self.assertIn(in_run_terminal, run["proxy_relay_context_lines"])
        self.assertNotIn(unrelated_old_selection, run["proxy_signal_lines"])
        self.assertNotIn(matching_late_selection, run["proxy_signal_lines"])
        self.assertNotIn(matching_old_selection, run["proxy_output_tail"])
        self.assertNotIn(matching_old_build, run["proxy_output_tail"])

    def test_proxy_log_lines_reads_run_level_signal_lines(self) -> None:
        profile = {
            "proxy_signal_lines": ["profile level"],
            "benchmarks": {
                "https://example.com/": {
                    "runs": [
                        {"proxy_signal_lines": ["run 1 line"]},
                        {
                            "proxy_signal_lines": ["run 2 line", "profile level"],
                            "proxy_relay_context_lines": ["run 2 relay"],
                            "proxy_output_tail": [
                                "run 2 output",
                                "run 2 output",
                                "run 2 relay",
                            ],
                        },
                    ]
                }
            },
        }

        self.assertEqual(
            proxy_log_lines(profile),
            [
                "profile level",
                "run 1 line",
                "run 2 line",
                "run 2 relay",
                "run 2 output",
                "run 2 output",
            ],
        )

    def test_proxy_relay_context_lines_keeps_delivered_and_receiver_rows(self) -> None:
        lines = proxy_relay_context_lines(
            [
                "torfast relay receive delivered stream_id=1",
                "torfast stream receiver read stream_id=1",
                "torfast circuit selection open usage_kind=exit",
                "ordinary line",
            ]
        )

        self.assertEqual(
            lines,
            [
                "torfast circuit selection open usage_kind=exit",
                "torfast relay receive delivered stream_id=1",
                "torfast stream receiver read stream_id=1",
            ],
        )

    def test_record_proxy_run_signals_keeps_failed_run_proxy_tail(self) -> None:
        lines: queue.Queue[str] = queue.Queue()
        lines.put("ordinary proxy info 1")
        lines.put("ordinary proxy info 2")
        lines.put("ordinary proxy info 3")
        profile: dict[str, object] = {}
        run: dict[str, object] = {"ok": False}

        record_proxy_run_signals(profile, run, lines, tail_limit=2)

        self.assertEqual(
            run["proxy_output_tail"],
            ["ordinary proxy info 2", "ordinary proxy info 3"],
        )
        self.assertNotIn("proxy_signal_lines", run)
        self.assertNotIn("proxy_signal_lines", profile)

    def test_record_proxy_run_signals_does_not_keep_success_tail_by_default(self) -> None:
        lines: queue.Queue[str] = queue.Queue()
        lines.put("ordinary proxy info 1")
        lines.put("ordinary proxy info 2")
        profile: dict[str, object] = {}
        run: dict[str, object] = {"ok": True}

        record_proxy_run_signals(profile, run, lines)

        self.assertNotIn("proxy_output_tail", run)

    def test_record_proxy_run_signals_can_keep_success_proxy_tail(self) -> None:
        lines: queue.Queue[str] = queue.Queue()
        lines.put("ordinary proxy info 1")
        lines.put("ordinary proxy info 2")
        lines.put("ordinary proxy info 3")
        profile: dict[str, object] = {}
        run: dict[str, object] = {"ok": True}

        record_proxy_run_signals(profile, run, lines, keep_success_tail_limit=2)

        self.assertEqual(
            run["proxy_output_tail"],
            ["ordinary proxy info 2", "ordinary proxy info 3"],
        )

    def test_parses_torfast_relay_receive_timings(self) -> None:
        timings = parse_torfast_relay_receive_timings(
            [
                "2026-06-06T23:12:37Z DEBUG tor_proto::circuit::circhop: event_epoch_ms=1780787557123 circ_id=Circ 0.1 hop=Some(3) stream_id=12 relay_cmd=RelayCmd(DATA) data_len=498 queued_before_bytes=0 queued_after_bytes=498 closes_stream=false torfast relay receive delivered",
                "2026-06-06T23:12:38Z DEBUG tor_proto::circuit::circhop: event_epoch_ms=1780787558246 circ_id=Circ 0.1 hop=Some(3) stream_id=12 relay_cmd=SENDME queued_bytes=0 torfast relay receive control",
                "2026-06-06T23:12:39Z DEBUG tor_proto::circuit::circhop: circ_id=Circ 0.1 hop=Some(3) stream_id=12 relay_cmd=DATA data_len=498 queued_before_bytes=0 torfast relay receive stream gone",
                "2026-06-06T23:12:40Z DEBUG tor_proto::circuit::circhop: circ_id=Circ 0.1 hop=Some(3) stream_id=99 relay_cmd=DATA torfast relay receive unknown stream",
            ]
        )

        self.assertEqual(
            [timing["event"] for timing in timings],
            ["delivered", "control", "stream_gone", "unknown_stream"],
        )
        self.assertEqual(timings[0]["stream_id"], 12)
        self.assertEqual(timings[0]["relay_cmd"], "DATA")
        self.assertEqual(timings[0]["data_len"], 498)
        self.assertEqual(timings[0]["queued_after_bytes"], 498)
        self.assertEqual(timings[0]["circ_id"], "Circ 0.1")
        self.assertEqual(timings[0]["event_epoch_ms"], 1780787557123)
        self.assertEqual(timings[0]["timestamp_ms"], 1780787557123)
        self.assertEqual(event_timestamp_gaps_ms(timings[:2]), [1123.0])

    def test_summarizes_torfast_relay_receive_streams(self) -> None:
        timings = parse_torfast_relay_receive_timings(
            [
                "2026-06-06T23:12:37Z DEBUG tor_proto::circuit::circhop: circ_id=Circ 0.1 hop=Some(3) stream_id=12 relay_cmd=RelayCmd(DATA) data_len=498 queued_before_bytes=0 queued_after_bytes=498 closes_stream=false torfast relay receive delivered",
                "2026-06-06T23:12:38Z DEBUG tor_proto::circuit::circhop: circ_id=Circ 0.1 hop=Some(3) stream_id=12 relay_cmd=RelayCmd(DATA) data_len=300 queued_before_bytes=498 queued_after_bytes=798 closes_stream=false torfast relay receive delivered",
                "2026-06-06T23:12:41Z DEBUG tor_proto::circuit::circhop: circ_id=Circ 0.2 hop=Some(3) stream_id=14 relay_cmd=RelayCmd(DATA) data_len=50 queued_before_bytes=0 queued_after_bytes=50 closes_stream=false torfast relay receive delivered",
            ]
        )

        rows = torfast_relay_receive_stream_rows(timings)

        self.assertEqual(rows[0]["circ_id"], "Circ 0.1")
        self.assertEqual(rows[0]["stream_id"], 12)
        self.assertEqual(rows[0]["data_cells"], 2)
        self.assertEqual(rows[0]["data_bytes"], 798)
        self.assertEqual(rows[0]["span_ms"], 1000)
        self.assertEqual(rows[0]["max_gap_ms"], 1000.0)
        self.assertEqual(rows[0]["max_queued_after_bytes"], 798)

    def test_summarizes_torfast_relay_receive_by_browser_run(self) -> None:
        payload = {
            "profiles": {
                "arti_release_browser": {
                    "proxy_output_tail": [
                        "2026-06-06T23:12:37Z DEBUG tor_proto::circuit::circhop: circ_id=Circ 0.1 hop=Some(3) stream_id=12 relay_cmd=RelayCmd(DATA) data_len=498 queued_before_bytes=0 queued_after_bytes=498 closes_stream=false torfast relay receive delivered",
                        "2026-06-06T23:12:38Z DEBUG tor_proto::circuit::circhop: circ_id=Circ 0.1 hop=Some(3) stream_id=12 relay_cmd=RelayCmd(DATA) data_len=300 queued_before_bytes=498 queued_after_bytes=798 closes_stream=false torfast relay receive delivered",
                        "2026-06-06T23:12:41Z DEBUG tor_proto::circuit::circhop: circ_id=Circ 0.2 hop=Some(3) stream_id=14 relay_cmd=RelayCmd(DATA) data_len=50 queued_before_bytes=0 queued_after_bytes=50 closes_stream=false torfast relay receive delivered",
                    ],
                    "benchmarks": {
                        "https://example.com/": {
                            "runs": [
                                {
                                    "run_index": 1,
                                    "load_ms": 500,
                                    "performance_timing": {
                                        "time_origin_ms": parse_log_timestamp_ms(
                                            "2026-06-06T23:12:37Z x"
                                        ),
                                        "navigation": {
                                            "responseStart": 100,
                                            "loadEventEnd": 500,
                                        },
                                    },
                                },
                                {
                                    "run_index": 2,
                                    "load_ms": 600,
                                    "performance_timing": {
                                        "time_origin_ms": parse_log_timestamp_ms(
                                            "2026-06-06T23:12:41Z x"
                                        ),
                                        "navigation": {
                                            "responseStart": 100,
                                            "loadEventEnd": 600,
                                        },
                                    },
                                },
                            ]
                        }
                    },
                }
            }
        }

        rows = torfast_relay_receive_run_summary_rows(payload)

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["run_index"], 1)
        self.assertEqual(rows[0]["delivered"], 2)
        self.assertEqual(rows[0]["data_cells"], 2)
        self.assertEqual(rows[0]["data_bytes"], 798)
        self.assertEqual(rows[0]["unique_circuits"], 1)
        self.assertEqual(rows[0]["unique_streams"], 1)
        self.assertEqual(rows[0]["first_receive_after_start_ms"], 0.0)
        self.assertEqual(rows[0]["first_receive_minus_response_ms"], -100.0)
        self.assertEqual(rows[0]["receive_span_ms"], 1000)
        self.assertEqual(rows[0]["last_receive_before_load_ms"], -500.0)
        self.assertEqual(rows[0]["max_receive_gap_ms"], 1000.0)
        self.assertEqual(rows[0]["max_queued_after_bytes"], 798)
        self.assertEqual(rows[1]["run_index"], 2)
        self.assertEqual(rows[1]["data_bytes"], 50)
        self.assertEqual(rows[1]["unique_circuits"], 1)
        self.assertEqual(rows[1]["last_receive_before_load_ms"], 600.0)

    def test_relay_receive_gap_detail_rows_show_gap_edges(self) -> None:
        base = parse_log_timestamp_ms("2026-06-06T23:12:37Z x")
        assert base is not None
        payload = {
            "profiles": {
                "arti_release_browser": {
                    "proxy_output_tail": [
                        f"event_epoch_ms={base + 100} circ_id=Circ 0.1 (Tunnel 2) hop=Some(3) stream_id=12 relay_cmd=RelayCmd(DATA) data_len=498 queued_before_bytes=0 queued_after_bytes=498 closes_stream=false torfast relay receive delivered",
                        f"event_epoch_ms={base + 5100} circ_id=Circ 0.1 (Tunnel 2) hop=Some(3) stream_id=13 relay_cmd=RelayCmd(DATA) data_len=300 queued_before_bytes=0 queued_after_bytes=300 closes_stream=false torfast relay receive delivered",
                        f"event_epoch_ms={base + 5200} circ_id=Circ 0.2 (Tunnel 3) hop=Some(3) stream_id=14 relay_cmd=RelayCmd(DATA) data_len=50 queued_before_bytes=300 queued_after_bytes=350 closes_stream=false torfast relay receive delivered",
                    ],
                    "benchmarks": {
                        "https://example.com/": {
                            "runs": [
                                {
                                    "run_index": 1,
                                    "load_ms": 7000,
                                    "performance_timing": {
                                        "time_origin_ms": base,
                                        "navigation": {"loadEventEnd": 7000},
                                    },
                                }
                            ]
                        }
                    },
                }
            }
        }

        rows = torfast_relay_receive_gap_detail_rows(payload)

        self.assertEqual(rows[0]["gap_ms"], 5000)
        self.assertEqual(rows[0]["prev_circ_id"], "Circ 0.1 (Tunnel 2)")
        self.assertEqual(rows[0]["prev_stream_id"], 12)
        self.assertEqual(rows[0]["prev_queued_after_bytes"], 498)
        self.assertEqual(rows[0]["next_circ_id"], "Circ 0.1 (Tunnel 2)")
        self.assertEqual(rows[0]["next_stream_id"], 13)
        self.assertEqual(rows[0]["next_queued_before_bytes"], 0)
        self.assertEqual(rows[0]["next_queued_after_bytes"], 300)
        self.assertEqual(rows[0]["gap_end_before_load_ms"], 1900)

    def test_relay_receive_stream_gap_detail_rows_show_same_stream_gap(self) -> None:
        base = parse_log_timestamp_ms("2026-06-06T23:12:37Z x")
        assert base is not None
        payload = {
            "profiles": {
                "arti_release_browser": {
                    "proxy_output_tail": [
                        f"event_epoch_ms={base + 100} circ_id=Circ 0.1 (Tunnel 2) hop=Some(3) stream_id=12 relay_cmd=RelayCmd(DATA) data_len=498 queued_before_bytes=0 queued_after_bytes=498 closes_stream=false torfast relay receive delivered",
                        f"event_epoch_ms={base + 200} circ_id=Circ 0.2 (Tunnel 3) hop=Some(3) stream_id=99 relay_cmd=RelayCmd(DATA) data_len=498 queued_before_bytes=0 queued_after_bytes=498 closes_stream=false torfast relay receive delivered",
                        f"event_epoch_ms={base + 5100} circ_id=Circ 0.1 (Tunnel 2) hop=Some(3) stream_id=12 relay_cmd=RelayCmd(DATA) data_len=300 queued_before_bytes=0 queued_after_bytes=300 closes_stream=false torfast relay receive delivered",
                    ],
                    "benchmarks": {
                        "https://example.com/": {
                            "runs": [
                                {
                                    "run_index": 1,
                                    "load_ms": 7000,
                                    "performance_timing": {
                                        "time_origin_ms": base,
                                        "navigation": {"loadEventEnd": 7000},
                                    },
                                }
                            ]
                        }
                    },
                }
            }
        }

        rows = torfast_relay_receive_stream_gap_detail_rows(payload)

        self.assertEqual(rows[0]["gap_ms"], 5000)
        self.assertEqual(rows[0]["circ_id"], "Circ 0.1 (Tunnel 2)")
        self.assertEqual(rows[0]["stream_id"], 12)
        self.assertEqual(rows[0]["prev_queued_after_bytes"], 498)
        self.assertEqual(rows[0]["next_queued_before_bytes"], 0)
        self.assertEqual(rows[0]["next_queued_after_bytes"], 300)
        self.assertEqual(rows[0]["gap_end_before_load_ms"], 1900)

    def test_relay_receive_circuit_gap_detail_rows_show_circuit_gap(self) -> None:
        base = parse_log_timestamp_ms("2026-06-06T23:12:37Z x")
        assert base is not None
        payload = {
            "profiles": {
                "arti_release_browser": {
                    "proxy_output_tail": [
                        f"event_epoch_ms={base + 100} circ_id=Circ 0.1 (Tunnel 2) hop=Some(3) stream_id=12 relay_cmd=RelayCmd(DATA) data_len=498 queued_before_bytes=0 queued_after_bytes=498 closes_stream=false torfast relay receive delivered",
                        f"event_epoch_ms={base + 2000} circ_id=Circ 0.1 (Tunnel 2) hop=Some(3) stream_id=99 relay_cmd=RelayCmd(DATA) data_len=498 queued_before_bytes=0 queued_after_bytes=498 closes_stream=false torfast relay receive delivered",
                        f"event_epoch_ms={base + 5100} circ_id=Circ 0.1 (Tunnel 2) hop=Some(3) stream_id=12 relay_cmd=RelayCmd(DATA) data_len=300 queued_before_bytes=0 queued_after_bytes=300 closes_stream=false torfast relay receive delivered",
                    ],
                    "benchmarks": {
                        "https://example.com/": {
                            "runs": [
                                {
                                    "run_index": 1,
                                    "load_ms": 7000,
                                    "performance_timing": {
                                        "time_origin_ms": base,
                                        "navigation": {"loadEventEnd": 7000},
                                    },
                                }
                            ]
                        }
                    },
                }
            }
        }

        stream_rows = torfast_relay_receive_stream_gap_detail_rows(payload)
        circuit_rows = torfast_relay_receive_circuit_gap_detail_rows(payload)

        self.assertEqual(stream_rows[0]["gap_ms"], 5000)
        self.assertEqual(circuit_rows[0]["gap_ms"], 3100)
        self.assertEqual(circuit_rows[0]["circ_id"], "Circ 0.1 (Tunnel 2)")
        self.assertEqual(circuit_rows[0]["circuit_streams"], 2)
        self.assertEqual(circuit_rows[0]["prev_stream_id"], 99)
        self.assertEqual(circuit_rows[0]["next_stream_id"], 12)
        self.assertEqual(circuit_rows[0]["gap_end_before_load_ms"], 1900)

    def test_relay_receive_circuit_gap_summary_rows_show_gap_scope(self) -> None:
        base = parse_log_timestamp_ms("2026-06-06T23:12:37Z x")
        assert base is not None
        payload = {
            "profiles": {
                "arti_release_browser": {
                    "proxy_output_tail": [
                        f"event_epoch_ms={base + 100} circ_id=Circ 0.1 (Tunnel 2) hop=Some(3) stream_id=12 relay_cmd=RelayCmd(DATA) data_len=498 queued_before_bytes=0 queued_after_bytes=498 closes_stream=false torfast relay receive delivered",
                        f"event_epoch_ms={base + 2000} circ_id=Circ 0.1 (Tunnel 2) hop=Some(3) stream_id=99 relay_cmd=RelayCmd(DATA) data_len=498 queued_before_bytes=0 queued_after_bytes=498 closes_stream=false torfast relay receive delivered",
                        f"event_epoch_ms={base + 5100} circ_id=Circ 0.1 (Tunnel 2) hop=Some(3) stream_id=12 relay_cmd=RelayCmd(DATA) data_len=300 queued_before_bytes=0 queued_after_bytes=300 closes_stream=false torfast relay receive delivered",
                    ],
                    "benchmarks": {
                        "https://example.com/": {
                            "runs": [
                                {
                                    "run_index": 1,
                                    "load_ms": 7000,
                                    "performance_timing": {
                                        "time_origin_ms": base,
                                        "navigation": {"loadEventEnd": 7000},
                                    },
                                }
                            ]
                        }
                    },
                }
            }
        }

        rows = torfast_relay_receive_circuit_gap_summary_rows(payload)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["circuit"], "Circ 0.1 (Tunnel 2)")
        self.assertEqual(rows[0]["max_circuit_data_gap_ms"], 3100)
        self.assertEqual(rows[0]["median_circuit_data_gap_ms"], 2500.0)
        self.assertEqual(rows[0]["circuit_streams"], 2)
        self.assertEqual(rows[0]["cross_stream_gap_rows"], 2)
        self.assertEqual(rows[0]["same_stream_gap_rows"], 0)
        self.assertEqual(rows[0]["max_gap_prev_stream_id"], 99)
        self.assertEqual(rows[0]["max_gap_next_stream_id"], 12)
        self.assertFalse(rows[0]["max_gap_same_stream"])

    def test_socks_relay_join_gap_detail_rows_show_joined_stream_gap(self) -> None:
        base = parse_log_timestamp_ms("2026-06-06T23:12:37Z x")
        assert base is not None
        payload = {
            "profiles": {
                "arti_release_browser": {
                    "proxy_output_tail": [
                        f"timing_id=7 target_kind=hostname port=443 conn_started_epoch_ms={base} torfast socks timing request parsed",
                        f"timing_id=7 circ_id=Circ 0.1 (Tunnel 2) stream_id=12 torfast socks timing stream linked",
                        f"event_epoch_ms={base + 100} circ_id=Circ 0.1 (Tunnel 2) hop=Some(3) stream_id=12 relay_cmd=RelayCmd(DATA) data_len=498 queued_before_bytes=0 queued_after_bytes=498 closes_stream=false torfast relay receive delivered",
                        f"event_epoch_ms={base + 5100} circ_id=Circ 0.1 (Tunnel 2) hop=Some(3) stream_id=12 relay_cmd=RelayCmd(DATA) data_len=300 queued_before_bytes=0 queued_after_bytes=300 closes_stream=false torfast relay receive delivered",
                    ],
                    "benchmarks": {
                        "https://example.com/": {
                            "runs": [
                                {
                                    "run_index": 1,
                                    "load_ms": 7000,
                                    "performance_timing": {
                                        "time_origin_ms": base,
                                        "navigation": {"loadEventEnd": 7000},
                                    },
                                }
                            ]
                        }
                    },
                }
            }
        }

        rows = torfast_socks_relay_join_gap_detail_rows(payload)

        self.assertEqual(rows[0]["timing_id"], 7)
        self.assertEqual(rows[0]["target_kind"], "hostname")
        self.assertEqual(rows[0]["gap_ms"], 5000)
        self.assertEqual(rows[0]["circ_id"], "Circ 0.1 (Tunnel 2)")
        self.assertEqual(rows[0]["stream_id"], 12)
        self.assertEqual(rows[0]["prev_queued_after_bytes"], 498)
        self.assertEqual(rows[0]["next_queued_before_bytes"], 0)
        self.assertEqual(rows[0]["next_queued_after_bytes"], 300)
        self.assertEqual(rows[0]["gap_end_before_load_ms"], 1900)

    def test_parses_stream_receiver_timings(self) -> None:
        timings = parse_torfast_stream_receiver_timings(
            [
                "event_epoch_ms=1000 stream_id=12 hop=None relay_cmd=DATA data_len=498 queued_after_bytes=300 recv_window_before=500 recv_window_after=499 sendme_due=false torfast stream receiver read",
                "event_epoch_ms=2000 stream_id=12 hop=None relay_cmd=DATA data_len=498 queued_after_bytes=0 recv_window_before=451 recv_window_after_take=450 sendme_ok=true torfast stream receiver sendme",
                "event_epoch_ms=2000 stream_id=12 hop=None relay_cmd=DATA data_len=498 queued_after_bytes=0 recv_window_before=451 recv_window_after=500 sendme_due=true torfast stream receiver read",
                "event_epoch_ms=2990 circ_id=Circ 0.1 (Tunnel 2) hop=3 stream_id=12 not_connected_source=receiver_none stream_close_cause=stream_target_closed queued_after_bytes=0 read_events=2 sendmes=1 sendme_ok=1 min_recv_window_after_take=450 max_queued_after_bytes=300 torfast stream receiver no-end close",
                "event_epoch_ms=3000 circ_id=Circ 0.1 (Tunnel 2) hop=3 stream_id=12 connected=true first_data_after_start_ms=100 transfer_ms=2000 idle_after_last_data_ms=10 max_data_gap_ms=1000 relay_data_bytes=996 pending_after_bytes=0 user_read_bytes=996 data_cells=2 read_events=2 sendmes=1 sendme_ok=1 min_recv_window_after_take=450 max_queued_after_bytes=300 error_kind=end_done stream_close_cause= end_reason=DONE returned_eof=true torfast stream receiver terminal summary",
                "event_epoch_ms=3500 circ_id=Circ 0.2 (Tunnel 3) hop=3 stream_id=13 connected=false first_data_after_start_ms=0 transfer_ms=0 idle_after_last_data_ms=0 max_data_gap_ms=0 relay_data_bytes=0 pending_after_bytes=0 user_read_bytes=0 data_cells=0 read_events=0 sendmes=0 sendme_ok=0 min_recv_window_after_take=0 max_queued_after_bytes=0 error_kind=not_connected not_connected_source=receiver_err stream_close_cause=unknown end_reason= returned_eof=false torfast stream receiver terminal summary",
                "event_epoch_ms=3510 circ_id=Circ 0.2 (Tunnel 3) hop=3 stream_id=13 connected=false error_kind=not_connected returned_eof=false previous_not_connected_source=receiver_err previous_stream_close_cause=unknown not_connected_source=already_closed torfast stream receiver already closed",
            ]
        )

        self.assertEqual(len(timings), 7)
        self.assertEqual(timings[0]["event"], "read")
        self.assertEqual(timings[0]["stream_id"], 12)
        self.assertEqual(timings[0]["recv_window_after"], 499)
        self.assertFalse(timings[0]["sendme_due"])
        self.assertEqual(timings[1]["event"], "sendme")
        self.assertTrue(timings[1]["sendme_ok"])
        self.assertEqual(timings[3]["event"], "no_end_close")
        self.assertEqual(timings[3]["circ_id"], "Circ 0.1 (Tunnel 2)")
        self.assertEqual(timings[3]["not_connected_source"], "receiver_none")
        self.assertEqual(timings[3]["stream_close_cause"], "stream_target_closed")
        self.assertEqual(timings[3]["read_events"], 2)
        self.assertEqual(timings[4]["event"], "terminal")
        self.assertEqual(timings[4]["circ_id"], "Circ 0.1 (Tunnel 2)")
        self.assertEqual(timings[4]["error_kind"], "end_done")
        self.assertEqual(timings[4]["transfer_ms"], 2000)
        self.assertEqual(timings[4]["max_data_gap_ms"], 1000)
        self.assertEqual(timings[4]["relay_data_bytes"], 996)
        self.assertEqual(timings[4]["read_events"], 2)
        self.assertEqual(timings[4]["sendmes"], 1)
        self.assertEqual(timings[4]["sendme_ok"], 1)
        self.assertEqual(timings[4]["min_recv_window_after_take"], 450)
        self.assertEqual(timings[4]["max_queued_after_bytes"], 300)
        self.assertTrue(timings[4]["returned_eof"])
        self.assertEqual(timings[5]["event"], "terminal")
        self.assertEqual(timings[5]["not_connected_source"], "receiver_err")
        self.assertEqual(timings[5]["stream_close_cause"], "unknown")
        self.assertEqual(timings[6]["event"], "already_closed")
        self.assertEqual(timings[6]["not_connected_source"], "already_closed")
        self.assertEqual(timings[6]["previous_not_connected_source"], "receiver_err")
        self.assertEqual(timings[6]["previous_stream_close_cause"], "unknown")

        rows = torfast_stream_receiver_rows(timings)
        stream_12 = next(row for row in rows if row["stream_id"] == 12)

        self.assertEqual(stream_12["stream_id"], 12)
        self.assertEqual(stream_12["read_events"], 2)
        self.assertEqual(stream_12["sendmes"], 1)
        self.assertEqual(stream_12["sendme_ok"], 1)
        self.assertEqual(stream_12["data_bytes"], 996)
        self.assertEqual(stream_12["max_read_gap_ms"], 1000.0)
        self.assertEqual(stream_12["min_recv_window_after"], 499)

    def test_stream_receiver_terminal_summary_rows(self) -> None:
        payload = {
            "profiles": {
                "arti_release_browser": {
                    "benchmarks": {
                        "https://example.test/": {
                            "runs": [
                                {
                                    "run_index": 1,
                                    "load_ms": 7000,
                                    "proxy_relay_context_lines": [
                                        "timing_id=8 target_kind=hostname relay_ms=6500 circ_id=Circ 0.1 (Tunnel 2) stream_id=13 ok=false copy_error_kind=not_connected torfast socks timing relay finished",
                                        "timing_id=9 target_kind=onion relay_ms=3000 circ_id=Circ 0.2 (Tunnel 3) stream_id=14 ok=false copy_error_kind=not_connected torfast socks timing relay finished",
                                        "event_epoch_ms=3000 circ_id=Circ 0.0 (Tunnel 1) stream_id=12 connected=true first_data_after_start_ms=100 transfer_ms=2000 idle_after_last_data_ms=10 max_data_gap_ms=1000 relay_data_bytes=996 pending_after_bytes=0 user_read_bytes=900 data_cells=2 read_events=2 sendmes=1 sendme_ok=1 min_recv_window_after_take=450 max_queued_after_bytes=300 error_kind=end_done end_reason=DONE returned_eof=true torfast stream receiver terminal summary",
                                        'event_epoch_ms=3985 circ_id=Circ 0.1 (Tunnel 2) hop=3 stream_id=13 close_reason=StreamTargetClosed should_send_end=Send close_behavior=send_end delivery="close_decision" torfast stream lifecycle',
                                        "event_epoch_ms=3990 circ_id=Circ 0.1 (Tunnel 2) hop=3 stream_id=13 not_connected_source=receiver_none stream_close_cause=stream_target_closed queued_after_bytes=0 read_events=9 sendmes=0 sendme_ok=0 min_recv_window_after_take=491 max_queued_after_bytes=0 torfast stream receiver no-end close",
                                        "event_epoch_ms=4000 circ_id=Circ 0.1 (Tunnel 2) stream_id=13 connected=true first_data_after_start_ms=200 transfer_ms=6000 idle_after_last_data_ms=50 max_data_gap_ms=3000 relay_data_bytes=4096 pending_after_bytes=0 user_read_bytes=4096 data_cells=9 read_events=9 sendmes=0 sendme_ok=0 min_recv_window_after_take=491 max_queued_after_bytes=0 error_kind=not_connected not_connected_source=receiver_err stream_close_cause=stream_target_closed end_reason= returned_eof=false torfast stream receiver terminal summary",
                                        "event_epoch_ms=5000 circ_id=Circ 0.2 (Tunnel 3) stream_id=14 connected=true first_data_after_start_ms=300 transfer_ms=1000 idle_after_last_data_ms=250 max_data_gap_ms=500 relay_data_bytes=2048 pending_after_bytes=0 user_read_bytes=2048 data_cells=4 read_events=4 sendmes=1 sendme_ok=1 min_recv_window_after_take=450 max_queued_after_bytes=128 error_kind=not_connected not_connected_source=receiver_err stream_close_cause=unknown end_reason= returned_eof=false torfast stream receiver terminal summary",
                                    ],
                                }
                            ]
                        }
                    }
                }
            }
        }

        rows = torfast_stream_receiver_terminal_summary_rows(payload)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["streams"], 3)
        self.assertEqual(rows[0]["terminal_summaries"], 3)
        self.assertEqual(rows[0]["non_eof"], 2)
        self.assertAlmostEqual(rows[0]["relay_kib"], (996 + 4096 + 2048) / 1024)
        self.assertEqual(rows[0]["data_cells"], 15)
        self.assertEqual(rows[0]["median_transfer_ms"], 2000.0)
        self.assertEqual(rows[0]["max_transfer_ms"], 6000)
        self.assertEqual(rows[0]["max_data_gap_ms"], 3000)
        self.assertEqual(rows[0]["read_events"], 15)
        self.assertEqual(rows[0]["sendmes"], 2)
        self.assertEqual(rows[0]["sendme_ok"], 2)
        self.assertEqual(rows[0]["min_recv_window_after_take"], 450)
        self.assertEqual(rows[0]["max_queued_after_bytes"], 300)
        self.assertEqual(rows[0]["top_stream_id"], 13)

        top_rows = torfast_stream_receiver_terminal_top_rows(payload)

        self.assertEqual(len(top_rows), 3)
        self.assertEqual(top_rows[0]["profile"], "arti_release_browser")
        self.assertEqual(top_rows[0]["target"], "https://example.test/")
        self.assertEqual(top_rows[0]["run_index"], 1)
        self.assertEqual(top_rows[0]["stream_id"], 13)
        self.assertEqual(top_rows[0]["transfer_ms"], 6000)
        self.assertEqual(top_rows[0]["max_data_gap_ms"], 3000)
        self.assertEqual(top_rows[0]["idle_after_last_data_ms"], 50)
        self.assertEqual(top_rows[0]["relay_kib"], 4.0)
        self.assertEqual(top_rows[0]["read_events"], 9)
        self.assertEqual(top_rows[0]["sendmes"], 0)
        self.assertEqual(top_rows[0]["no_end_close_events"], 1)
        self.assertEqual(top_rows[0]["no_end_close_read_events"], 9)
        self.assertEqual(top_rows[0]["no_end_close_queued_after_bytes"], 0)
        self.assertEqual(top_rows[0]["close_decision_events"], 1)
        self.assertEqual(top_rows[0]["close_reasons"], "StreamTargetClosed:1")
        self.assertEqual(top_rows[0]["close_should_send_end"], "Send:1")
        self.assertEqual(top_rows[0]["close_behaviors"], "send_end:1")
        self.assertEqual(top_rows[0]["min_recv_window_after_take"], 491)
        self.assertEqual(top_rows[0]["max_queued_after_bytes"], 0)
        self.assertEqual(top_rows[0]["error_kind"], "not_connected")
        self.assertEqual(top_rows[0]["not_connected_source"], "receiver_err")
        self.assertEqual(top_rows[0]["stream_close_cause"], "stream_target_closed")
        self.assertEqual(top_rows[0]["timing_id"], 8)

        not_connected_rows = torfast_stream_receiver_not_connected_summary_rows(payload)

        self.assertEqual(len(not_connected_rows), 1)
        self.assertEqual(not_connected_rows[0]["profile"], "arti_release_browser")
        self.assertEqual(not_connected_rows[0]["target"], "https://example.test/")
        self.assertEqual(not_connected_rows[0]["run_index"], 1)
        self.assertEqual(not_connected_rows[0]["load_ms"], 7000)
        self.assertEqual(not_connected_rows[0]["not_connected_streams"], 2)
        self.assertEqual(not_connected_rows[0]["hostname_streams"], 1)
        self.assertEqual(not_connected_rows[0]["onion_streams"], 1)
        self.assertEqual(not_connected_rows[0]["max_socks_relay_ms"], 6500)
        self.assertEqual(not_connected_rows[0]["max_idle_after_last_data_ms"], 250)
        self.assertEqual(not_connected_rows[0]["max_transfer_ms"], 6000)
        self.assertEqual(not_connected_rows[0]["max_data_gap_ms"], 3000)
        self.assertEqual(not_connected_rows[0]["max_first_data_after_start_ms"], 300)
        self.assertEqual(
            not_connected_rows[0]["top_not_connected_sources"], "receiver_err:2"
        )
        self.assertEqual(
            not_connected_rows[0]["top_stream_close_causes"],
            "stream_target_closed:1, unknown:1",
        )
        self.assertIn("8", not_connected_rows[0]["top_timing_ids"])
        self.assertIn("Circ", not_connected_rows[0]["top_circuits"])
        self.assertIn("13", not_connected_rows[0]["top_stream_ids"])

    def test_stream_receiver_terminal_top_rows_include_run_context(self) -> None:
        payload = {
            "profiles": {
                "arti_release_browser": {
                    "benchmarks": {
                        "https://example.test/": {
                            "runs": [
                                {
                                    "run_index": 2,
                                    "load_ms": 9000,
                                    "proxy_relay_context_lines": [
                                        "timing_id=7 target_kind=hostname port=443 circ_id=Circ 0.4 (Tunnel 15) hop=3 stream_id=13 elapsed_ms=122 torfast socks timing stream linked",
                                        "timing_id=7 target_kind=hostname port=443 relay_ms=6500 elapsed_ms=6700 ok=false copy_error_kind=not_connected torfast socks timing relay finished",
                                        "event_epoch_ms=4000 stream_id=13 connected=true first_data_after_start_ms=200 transfer_ms=6000 idle_after_last_data_ms=50 max_data_gap_ms=3000 relay_data_bytes=4096 pending_after_bytes=0 user_read_bytes=4096 data_cells=9 error_kind=not_connected end_reason= returned_eof=false torfast stream receiver terminal summary",
                                    ],
                                }
                            ]
                        }
                    }
                }
            }
        }

        rows = torfast_stream_receiver_terminal_top_rows(payload)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["profile"], "arti_release_browser")
        self.assertEqual(rows[0]["target"], "https://example.test/")
        self.assertEqual(rows[0]["run_index"], 2)
        self.assertEqual(rows[0]["load_ms"], 9000)
        self.assertEqual(rows[0]["timing_id"], 7)
        self.assertEqual(rows[0]["target_kind"], "hostname")
        self.assertEqual(rows[0]["socks_relay_ms"], 6500)
        self.assertFalse(rows[0]["socks_ok"])
        self.assertEqual(rows[0]["copy_error_kind"], "not_connected")
        self.assertEqual(rows[0]["stream_id"], 13)

    def test_stream_receiver_terminal_top_rows_match_relay_finished_stream_key(
        self,
    ) -> None:
        payload = {
            "profiles": {
                "arti_release_browser": {
                    "benchmarks": {
                        "https://example.test/": {
                            "runs": [
                                {
                                    "run_index": 1,
                                    "load_ms": 8000,
                                    "proxy_relay_context_lines": [
                                        "timing_id=9 target_kind=hostname port=443 circ_id=Circ 0.4 (Tunnel 15) hop=3 stream_id=13 relay_ms=6500 elapsed_ms=6700 ok=false copy_error_kind=not_connected torfast socks timing relay finished",
                                        "event_epoch_ms=4000 circ_id=Circ 0.4 (Tunnel 15) hop=3 stream_id=13 connected=true first_data_after_start_ms=200 transfer_ms=6000 idle_after_last_data_ms=50 max_data_gap_ms=3000 relay_data_bytes=4096 pending_after_bytes=0 user_read_bytes=4096 data_cells=9 error_kind=not_connected end_reason= returned_eof=false torfast stream receiver terminal summary",
                                    ],
                                }
                            ]
                        }
                    }
                }
            }
        }

        rows = torfast_stream_receiver_terminal_top_rows(payload)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["timing_id"], 9)
        self.assertEqual(rows[0]["target_kind"], "hostname")
        self.assertEqual(rows[0]["socks_relay_ms"], 6500)
        self.assertFalse(rows[0]["socks_ok"])
        self.assertEqual(rows[0]["copy_error_kind"], "not_connected")
        self.assertEqual(rows[0]["stream_id"], 13)
        self.assertEqual(rows[0]["circ_id"], "Circ 0.4 (Tunnel 15)")

    def test_stream_receiver_gap_context_rows_overlay_reads(self) -> None:
        base = parse_log_timestamp_ms("2026-06-06T23:12:37Z x")
        assert base is not None
        payload = {
            "profiles": {
                "arti_release_browser": {
                    "proxy_output_tail": [
                        f"timing_id=7 target_kind=hostname port=443 conn_started_epoch_ms={base} torfast socks timing request parsed",
                        f"timing_id=7 circ_id=Circ 0.1 (Tunnel 2) stream_id=12 torfast socks timing stream linked",
                        f"event_epoch_ms={base + 100} circ_id=Circ 0.1 (Tunnel 2) hop=Some(3) stream_id=12 relay_cmd=RelayCmd(DATA) data_len=498 queued_before_bytes=0 queued_after_bytes=498 closes_stream=false torfast relay receive delivered",
                        f"event_epoch_ms={base + 120} stream_id=12 hop=None relay_cmd=DATA data_len=498 queued_after_bytes=0 recv_window_before=500 recv_window_after=499 sendme_due=false torfast stream receiver read",
                        f"event_epoch_ms={base + 5100} circ_id=Circ 0.1 (Tunnel 2) hop=Some(3) stream_id=12 relay_cmd=RelayCmd(DATA) data_len=300 queued_before_bytes=0 queued_after_bytes=300 closes_stream=false torfast relay receive delivered",
                    ],
                    "benchmarks": {
                        "https://example.com/": {
                            "runs": [
                                {
                                    "run_index": 1,
                                    "load_ms": 7000,
                                    "performance_timing": {
                                        "time_origin_ms": base,
                                        "navigation": {"loadEventEnd": 7000},
                                    },
                                }
                            ]
                        }
                    },
                }
            }
        }

        rows = torfast_stream_receiver_gap_context_rows(payload)

        self.assertEqual(rows[0]["timing_id"], 7)
        self.assertEqual(rows[0]["gap_ms"], 5000)
        self.assertEqual(rows[0]["receiver_reads_in_gap"], 1)
        self.assertEqual(rows[0]["receiver_sendmes_in_gap"], 0)
        self.assertEqual(rows[0]["first_receiver_read_after_gap_start_ms"], 20)
        self.assertEqual(rows[0]["last_receiver_read_before_gap_end_ms"], 4980)
        self.assertEqual(rows[0]["min_recv_window_after"], 499)

    def test_parses_torfast_stream_scheduler_timings(self) -> None:
        timings = parse_torfast_stream_scheduler_timings(
            [
                "2026-06-06T23:12:37Z DEBUG tor_proto::client::reactor::circuit::circhop: circ_id=Tunnel 1 (Circ 0.1) hop=3 stream_id=12 relay_cmd=DATA torfast stream scheduler picked",
                "2026-06-06T23:12:38Z DEBUG tor_proto::client::reactor::circuit::circhop: circ_id=Tunnel 1 (Circ 0.1) hop=3 stream_id=14 relay_cmd=DATA torfast stream scheduler picked",
                "2026-06-06T23:12:39Z DEBUG tor_proto::client::reactor::circuit::circhop: circ_id=Tunnel 1 (Circ 0.1) hop=3 stream_id=14 torfast stream scheduler stream closed",
                "2026-06-06T23:12:40Z DEBUG tor_proto::client::reactor::circuit::circhop: circ_id=Tunnel 1 (Circ 0.1) hop=3 torfast stream scheduler hop blocked",
            ]
        )

        self.assertEqual(
            [timing["event"] for timing in timings],
            ["picked", "picked", "stream_closed", "hop_blocked"],
        )
        self.assertEqual(timings[0]["stream_id"], 12)
        self.assertEqual(timings[0]["relay_cmd"], "DATA")
        self.assertEqual(timings[0]["circ_id"], "Tunnel 1 (Circ 0.1)")
        self.assertEqual(event_timestamp_gaps_ms(timings[:2]), [1000.0])

    def test_parses_torfast_stream_reactor_congestion_timings(self) -> None:
        timings = parse_torfast_stream_reactor_congestion_timings(
            [
                "2026-06-06T23:12:37Z DEBUG tor_proto::circuit::reactor::stream: circ_id=Tunnel 1 (Circ 0.1) hop=3 stream_id=12 relay_cmd=DATA torfast stream reactor congestion blocked",
                "2026-06-06T23:12:38Z DEBUG tor_proto::circuit::reactor::stream: circ_id=Tunnel 1 (Circ 0.1) hop=3 stream_id=14 relay_cmd=DATA torfast stream reactor congestion blocked",
            ]
        )

        self.assertEqual(
            [timing["event"] for timing in timings],
            ["congestion_blocked", "congestion_blocked"],
        )
        self.assertEqual(timings[0]["circ_id"], "Tunnel 1 (Circ 0.1)")
        self.assertEqual(timings[0]["stream_id"], 12)
        self.assertEqual(timings[0]["relay_cmd"], "DATA")
        self.assertEqual(event_timestamp_gaps_ms(timings), [1000.0])

    def test_parses_torfast_stream_lifecycle_timings(self) -> None:
        timings = parse_torfast_stream_lifecycle_timings(
            [
                "2026-06-06T23:12:37Z INFO tor_proto::circuit::circhop: event_epoch_ms=1780787557000 hop=Some(HopNum(3)) stream_id=12 relay_cmd=RelayCmd(BEGIN) delivery=\"sent\" torfast stream lifecycle",
                "2026-06-06T23:12:37Z INFO tor_proto::client::reactor::circuit: event_epoch_ms=1780787557001 circ_id=Circ 0.4 (Tunnel 15) hop=HopNum(3) stream_id=12 relay_cmd=RelayCmd(BEGIN) channel_circ_id=2147483650 circuit_sender_queue_after_cells=0 channel_queue_count_available=true channel_queue_after_cells=1 delivery=\"channel_queued\" torfast stream lifecycle",
                "2026-06-06T23:12:38Z INFO tor_proto::circuit::circhop: event_epoch_ms=1780787557500 circ_id=Circ 0.4 (Tunnel 15) hop=Some(HopNum(3)) stream_id=12 relay_cmd=RelayCmd(CONNECTED) data_len=0 queued_before_bytes=0 queued_after_bytes=0 closes_stream=false delivery=\"delivered\" torfast stream lifecycle",
                "2026-06-06T23:12:39Z INFO tor_proto::circuit::circhop: event_epoch_ms=1780787559000 circ_id=Circ 0.4 (Tunnel 15) hop=Some(HopNum(3)) stream_id=12 relay_cmd=RelayCmd(DATA) data_len=498 queued_before_bytes=0 queued_after_bytes=498 closes_stream=false delivery=\"stream_gone\" torfast stream lifecycle",
            ]
        )

        self.assertEqual([timing["event"] for timing in timings], ["sent", "channel_queued", "delivered", "stream_gone"])
        self.assertEqual(timings[1]["circ_id"], "Circ 0.4 (Tunnel 15)")
        self.assertEqual(timings[1]["relay_cmd"], "BEGIN")
        self.assertEqual(timings[1]["channel_circ_id"], 2147483650)
        self.assertEqual(timings[1]["channel_queue_after_cells"], 1)
        self.assertEqual(timings[2]["relay_cmd"], "CONNECTED")
        self.assertEqual(timings[3]["data_len"], 498)
        self.assertEqual(event_timestamp_gaps_ms(timings[:2]), [1])

    def test_stream_lifecycle_summary_rows_counts_delivery_and_commands(self) -> None:
        payload = {
            "profiles": {
                "arti_release_browser": {
                    "proxy_signal_lines": [
                        "event_epoch_ms=1000 hop=Some(HopNum(3)) stream_id=12 relay_cmd=RelayCmd(BEGIN) delivery=\"sent\" torfast stream lifecycle",
                        "event_epoch_ms=1001 circ_id=Circ 0.4 (Tunnel 15) hop=HopNum(3) stream_id=12 relay_cmd=RelayCmd(BEGIN) channel_circ_id=2147483650 channel_queue_after_cells=1 delivery=\"channel_queued\" torfast stream lifecycle",
                        "event_epoch_ms=1100 circ_id=Circ 0.4 (Tunnel 15) hop=Some(HopNum(3)) stream_id=12 relay_cmd=RelayCmd(CONNECTED) data_len=0 queued_before_bytes=0 queued_after_bytes=0 closes_stream=false delivery=\"delivered\" torfast stream lifecycle",
                        "event_epoch_ms=1200 circ_id=Circ 0.4 (Tunnel 15) hop=Some(HopNum(3)) stream_id=12 relay_cmd=RelayCmd(DATA) data_len=498 queued_before_bytes=0 queued_after_bytes=498 closes_stream=false delivery=\"stream_gone\" torfast stream lifecycle",
                    ]
                }
            }
        }

        rows = torfast_stream_lifecycle_summary_rows(payload)

        self.assertEqual(rows[0]["profile"], "arti_release_browser")
        self.assertEqual(rows[0]["sent"], 1)
        self.assertEqual(rows[0]["channel_queued"], 1)
        self.assertEqual(rows[0]["delivered"], 1)
        self.assertEqual(rows[0]["stream_gone"], 1)
        self.assertEqual(rows[0]["begin"], 2)
        self.assertEqual(rows[0]["connected"], 1)
        self.assertEqual(rows[0]["data"], 1)
        self.assertEqual(rows[0]["max_data_len"], 498)

    def test_stream_lifecycle_response_gap_rows(self) -> None:
        payload = {
            "profiles": {
                "arti_release_browser": {
                    "proxy_signal_lines": [
                        "event_epoch_ms=1000 circ_id=Circ 0.4 (Tunnel 15) hop=HopNum(3) stream_id=12 relay_cmd=RelayCmd(BEGIN) channel_circ_id=2147483650 delivery=\"channel_queued\" torfast stream lifecycle",
                        "event_epoch_ms=1150 circ_id=Circ 0.4 (Tunnel 15) hop=Some(HopNum(3)) stream_id=12 relay_cmd=RelayCmd(CONNECTED) data_len=0 delivery=\"delivered\" torfast stream lifecycle",
                        "event_epoch_ms=1200 circ_id=Circ 0.4 (Tunnel 15) hop=HopNum(3) stream_id=12 relay_cmd=RelayCmd(DATA) channel_circ_id=2147483650 delivery=\"channel_queued\" torfast stream lifecycle",
                        "event_epoch_ms=1500 circ_id=Circ 0.4 (Tunnel 15) hop=Some(HopNum(3)) stream_id=12 relay_cmd=RelayCmd(DATA) data_len=498 delivery=\"delivered\" torfast stream lifecycle",
                        "event_epoch_ms=2000 circ_id=Circ 0.4 (Tunnel 15) hop=HopNum(3) stream_id=13 relay_cmd=RelayCmd(BEGIN) channel_circ_id=2147483650 delivery=\"channel_queued\" torfast stream lifecycle",
                    ]
                }
            }
        }

        rows = torfast_stream_lifecycle_response_gap_rows(payload)

        self.assertEqual(rows[0]["streams"], 2)
        self.assertEqual(rows[0]["begin_queued"], 2)
        self.assertEqual(rows[0]["begin_connected"], 1)
        self.assertEqual(rows[0]["begin_without_connected"], 1)
        self.assertEqual(rows[0]["median_begin_to_connected_ms"], 150)
        self.assertEqual(rows[0]["max_begin_to_connected_ms"], 150)
        self.assertEqual(rows[0]["data_queued"], 1)
        self.assertEqual(rows[0]["data_response"], 1)
        self.assertEqual(rows[0]["data_without_response"], 0)
        self.assertEqual(rows[0]["median_data_to_data_ms"], 300)
        self.assertEqual(rows[0]["max_data_to_data_ms"], 300)

    def test_parses_torfast_channel_flush_timings(self) -> None:
        lines = [
            "2026-06-06T23:12:37Z INFO tor_proto::channel::reactor: event_epoch_ms=1780787557000 channel_id=Chan 3 channel_circ_id=2147483650 channel_circ_id_present=true channel_cmd=ChanCmd(RELAY) channel_reactor_queue_count_available=true channel_reactor_queue_after_cells=2 delivery=\"channel_flushed\" torfast channel flush",
            "2026-06-06T23:12:38Z INFO tor_proto::channel::reactor: event_epoch_ms=1780787558000 channel_id=Chan 3 channel_circ_id=0 channel_circ_id_present=false channel_cmd=ChanCmd(PADDING) channel_reactor_queue_count_available=false channel_reactor_queue_after_cells=0 delivery=\"channel_flushed\" torfast channel flush",
        ]

        timings = parse_torfast_channel_flush_timings(lines)

        self.assertEqual([timing["event"] for timing in timings], ["channel_flushed", "channel_flushed"])
        self.assertEqual(timings[0]["channel_id"], "Chan 3")
        self.assertEqual(timings[0]["channel_circ_id"], 2147483650)
        self.assertEqual(timings[0]["channel_reactor_queue_after_cells"], 2)
        self.assertEqual(timings[1]["channel_reactor_queue_count_available"], False)
        self.assertEqual(event_timestamp_gaps_ms(timings), [1000])

    def test_channel_flush_summary_rows_counts_queue_unknown(self) -> None:
        payload = {
            "profiles": {
                "arti_release_browser": {
                    "proxy_signal_lines": [
                        "event_epoch_ms=1000 channel_id=Chan 3 channel_circ_id=2147483650 channel_circ_id_present=true channel_cmd=ChanCmd(RELAY) channel_reactor_queue_count_available=true channel_reactor_queue_after_cells=2 delivery=\"channel_flushed\" torfast channel flush",
                        "event_epoch_ms=1001 channel_id=Chan 3 channel_circ_id=2147483650 channel_circ_id_present=true channel_cmd=ChanCmd(RELAY) channel_reactor_queue_count_available=true channel_reactor_queue_after_cells=1 delivery=\"channel_flushed\" torfast channel flush",
                        "event_epoch_ms=1002 channel_id=Chan 3 channel_circ_id=0 channel_circ_id_present=false channel_cmd=ChanCmd(PADDING) channel_reactor_queue_count_available=false channel_reactor_queue_after_cells=0 delivery=\"channel_flushed\" torfast channel flush",
                    ]
                }
            }
        }

        rows = torfast_channel_flush_summary_rows(payload)

        self.assertEqual(rows[0]["profile"], "arti_release_browser")
        self.assertEqual(rows[0]["flush_rows"], 3)
        self.assertEqual(rows[0]["relay"], 2)
        self.assertEqual(rows[0]["padding"], 1)
        self.assertEqual(rows[0]["unique_channel_circuits"], 1)
        self.assertEqual(rows[0]["max_channel_reactor_queue_after_cells"], 2)
        self.assertEqual(rows[0]["channel_reactor_queue_unknown"], 1)

    def test_channel_flush_gap_rows_match_queued_cells_to_flushes(self) -> None:
        payload = {
            "profiles": {
                "arti_release_browser": {
                    "proxy_signal_lines": [
                        "event_epoch_ms=1000 circ_id=Circ 0.4 (Tunnel 15) hop=HopNum(3) stream_id=12 relay_cmd=RelayCmd(DATA) channel_circ_id=2147483650 delivery=\"channel_queued\" torfast stream lifecycle",
                        "event_epoch_ms=1004 channel_id=Chan 3 channel_circ_id=2147483650 channel_circ_id_present=true channel_cmd=ChanCmd(RELAY) channel_reactor_queue_count_available=false channel_reactor_queue_after_cells=0 delivery=\"channel_flushed\" torfast channel flush",
                        "event_epoch_ms=1010 circ_id=Circ 0.4 (Tunnel 15) hop=HopNum(3) stream_id=13 relay_cmd=RelayCmd(DATA) channel_circ_id=2147483650 delivery=\"channel_queued\" torfast stream lifecycle",
                        "event_epoch_ms=1019 channel_id=Chan 3 channel_circ_id=2147483650 channel_circ_id_present=true channel_cmd=ChanCmd(RELAY) channel_reactor_queue_count_available=false channel_reactor_queue_after_cells=0 delivery=\"channel_flushed\" torfast channel flush",
                    ]
                }
            }
        }

        rows = torfast_channel_flush_gap_rows(payload)

        self.assertEqual(rows[0]["channel_queued_with_key"], 2)
        self.assertEqual(rows[0]["matched_flushes"], 2)
        self.assertEqual(rows[0]["unmatched_queued"], 0)
        self.assertEqual(rows[0]["median_queue_to_flush_ms"], 6.5)
        self.assertEqual(rows[0]["max_queue_to_flush_ms"], 9)

    def test_parses_torfast_circuit_congestion_timings(self) -> None:
        timings = parse_torfast_circuit_congestion_timings(
            [
                "2026-06-06T23:12:37Z INFO tor_proto::client::reactor::circuit: circ_id=Tunnel 1 (Circ 0.1) hop=3 algorithm=vegas can_send=true cwnd_present=true cwnd=500 cwnd_full_present=true cwnd_full=false inflight_present=true inflight=120 torfast circuit congestion sendme received",
                "2026-06-06T23:12:38Z INFO tor_proto::client::reactor::circuit: circ_id=Tunnel 1 (Circ 0.1) hop=3 algorithm=vegas can_send=true cwnd_present=true cwnd=520 cwnd_full_present=true cwnd_full=true inflight_present=true inflight=100 torfast circuit congestion sendme sent",
                "2026-06-06T23:12:39Z INFO tor_proto::client::reactor::circuit::circhop: circ_id=Tunnel 1 (Circ 0.1) hop=3 algorithm=vegas can_send=false cwnd_present=true cwnd=520 cwnd_full_present=true cwnd_full=true inflight_present=true inflight=520 torfast circuit congestion scheduler hop blocked",
            ]
        )

        self.assertEqual(
            [timing["event"] for timing in timings],
            ["sendme_received", "sendme_sent", "scheduler_hop_blocked"],
        )
        self.assertEqual(timings[0]["circ_id"], "Tunnel 1 (Circ 0.1)")
        self.assertEqual(timings[0]["algorithm"], "vegas")
        self.assertEqual(timings[0]["cwnd"], 500)
        self.assertEqual(timings[0]["inflight"], 120)
        self.assertIs(timings[2]["can_send"], False)
        self.assertEqual(event_timestamp_gaps_ms(timings), [1000.0, 1000.0])

    def test_parses_torfast_circuit_selection_timings(self) -> None:
        timings = parse_torfast_circuit_selection_timings(
            [
                "2026-06-06T23:12:37Z DEBUG tor_circmgr::mgr: open_candidates=3 select_parallelism=3 select_load_aware=true select_health_aware=true select_avoid_bad_health=true select_avoid_bad_health_unknown_fallback=true load_aware_assignment_spread=4 load_aware_min_assignment_spread=2 load_aware_assignment_candidate_index=1 health_aware_candidate_index=0 health_aware_assignment_score_bps=50000 health_aware_candidate_score_bps=120000 selected_candidate_index=0 open_support_summary=total:5,supported:3,unusable:0,usage_kind:1,isolation:1,stability:0,port:0,country:0,other:0,exit_unisolated:1,exit_compatible_isolated:2,exit_incompatible_isolated:1,exit_port_blocked:0,exit_stability_blocked:0,exit_country_blocked:0 candidate_assignment_summary=0:Circ~0.1:5,1:Circ~0.2:1,2:Circ~0.3:3 candidate_health_summary=0:Circ~0.1:4:12000:25,1:Circ~0.2:2:900:800,2:Circ~0.3:0:0:0 selected_assigned_streams=5 selected_health_score_bps=120000 selected_has_bad_health=false usage_kind=\"exit\" restrict_circ=true tunnel_unique_id=Circ 0.1 torfast circuit selection open",
                "2026-06-06T23:12:38Z DEBUG tor_circmgr::mgr: pending_candidates=2 selected_pending=1 usage_kind=preemptive restrict_circ=true torfast circuit selection pending",
                "2026-06-06T23:12:38Z DEBUG tor_circmgr::mgr: pending_candidates=1 max_pending=2 oldest_pending_ms=100 hedge_after_ms=1500 delay_ms=1400 usage_kind=exit restrict_circ=true torfast circuit selection pending hedge armed",
                "2026-06-06T23:12:38Z DEBUG tor_circmgr::mgr: delay_ms=1400 usage_kind=exit torfast circuit selection pending hedge timer fired",
                "2026-06-06T23:12:39Z DEBUG tor_circmgr::mgr: torfast circuit selection pending hedge pending_candidates=1 max_pending=2 oldest_pending_ms=1500 hedge_after_ms=1500 plans=1 usage_kind=exit restrict_circ=true",
                "2026-06-06T23:12:39Z DEBUG tor_circmgr::mgr: delay_ms=1500 usage_kind=exit torfast circuit selection build hedge timer fired",
                "2026-06-06T23:12:39Z DEBUG tor_circmgr::mgr: delay_ms=1500 plans=1 usage_kind=exit torfast circuit selection build hedge",
                "2026-06-06T23:12:40Z DEBUG tor_circmgr::mgr: launch_parallelism=1 plans=1 usage_kind=hs_circ_base restrict_circ=true torfast circuit selection build",
                "2026-06-06T23:12:41Z DEBUG tor_circmgr::mgr: open_candidates=1 pending_candidates=0 target=2 selected_assigned_streams=2 min_assigned_streams=2 selected_has_bad_health=true selected_active_streams=1 select_max_active_streams=1 selected_health_cells=4 selected_health_bytes=12000 selected_health_max_gap_ms=900 selected_health_score_bps=0 selected_health_span_ms=1200 selected_health_age_ms=50 require_bad_health=true active_stream_cap_saturated=true prewarm_first_stream=true exit_incompatible_isolated=4 other_isolation_min=3 other_isolation_pressure=true plans=1 usage_kind=exit torfast circuit selection same isolation topup",
                "2026-06-06T23:12:42Z DEBUG tor_circmgr::mgr: open_candidates=1 pending_candidates=0 target=2 selected_assigned_streams=2 min_assigned_streams=2 selected_has_bad_health=true selected_health_cells=5 selected_health_bytes=16000 selected_health_max_gap_ms=1000 selected_health_score_bps=0 selected_health_span_ms=1400 selected_health_age_ms=60 require_bad_health=true usage_kind=exit err=launch_failed torfast circuit selection same isolation topup failed",
                "2026-06-06T23:12:43Z INFO tor_circmgr::mgr: open_candidates=2 pending_candidates=1 selected_pending=1 target=2 selected_assigned_streams=1 active_stream_cap_saturated=false prewarm_first_stream=true delay_ms=800 fallback_tunnel_unique_id=Circ 3.4 usage_kind=\"exit\" torfast circuit selection same isolation pending wait",
                "2026-06-06T23:12:44Z INFO tor_circmgr::mgr: delay_ms=800 tunnel_unique_id=Circ 4.14 usage_kind=\"exit\" torfast circuit selection same isolation pending wait won",
                "2026-06-06T23:12:45Z INFO tor_circmgr::mgr: delay_ms=800 fallback_tunnel_unique_id=Circ 3.4 usage_kind=\"exit\" torfast circuit selection same isolation pending wait timer fired",
                "2026-06-06T23:12:46Z INFO tor_circmgr::mgr: open_candidates=2 pending_candidates=1 selected_pending=1 hedge_after_ms=600 selected_assigned_streams=1 selected_health_score_bps=0 fallback_tunnel_unique_id=Circ 3.5 usage_kind=\"exit\" torfast circuit selection bad health pending wait",
                "2026-06-06T23:12:47Z INFO tor_circmgr::mgr: delay_ms=600 tunnel_unique_id=Circ 4.15 usage_kind=\"exit\" torfast circuit selection bad health pending wait won",
                "2026-06-06T23:12:48Z INFO tor_circmgr::mgr: delay_ms=600 fallback_tunnel_unique_id=Circ 3.5 usage_kind=\"exit\" torfast circuit selection bad health pending wait timer fired",
                "2026-06-06T23:12:49Z INFO tor_circmgr::mgr: open_candidates=1 pending_candidates=1 hedge_after_ms=600 selected_assigned_streams=2 max_wait_assigned_streams=1 selected_health_score_bps=0 fallback_tunnel_unique_id=Circ 3.5 usage_kind=\"exit\" torfast circuit selection bad health pending wait skipped",
            ]
        )

        self.assertEqual(
            [timing["event"] for timing in timings],
            [
                "open",
                "pending",
                "pending_hedge_armed",
                "pending_hedge_timer",
                "pending_hedge",
                "build_hedge_timer",
                "build_hedge",
                "build",
                "same_isolation_topup",
                "same_isolation_topup_failed",
                "same_isolation_pending_wait",
                "same_isolation_pending_wait_won",
                "same_isolation_pending_wait_timer",
                "bad_health_pending_wait",
                "bad_health_pending_wait_won",
                "bad_health_pending_wait_timer",
                "bad_health_pending_wait_skipped",
            ],
        )
        self.assertEqual(count_pending_wait_events(timings), 3)
        self.assertEqual(timings[0]["open_candidates"], 3)
        self.assertEqual(timings[0]["select_parallelism"], 3)
        self.assertEqual(timings[0]["usage_kind"], "exit")
        self.assertEqual(timings[0]["selected_candidate_index"], 0)
        self.assertEqual(timings[0]["tunnel_unique_id"], "Circ 0.1")
        self.assertTrue(timings[0]["restrict_circ"])
        self.assertTrue(timings[0]["select_load_aware"])
        self.assertTrue(timings[0]["select_health_aware"])
        self.assertTrue(timings[0]["select_avoid_bad_health"])
        self.assertTrue(timings[0]["select_avoid_bad_health_unknown_fallback"])
        self.assertEqual(timings[10]["open_candidates"], 2)
        self.assertEqual(timings[10]["pending_candidates"], 1)
        self.assertEqual(timings[10]["selected_assigned_streams"], 1)
        self.assertEqual(timings[13]["hedge_after_ms"], 600)
        self.assertEqual(timings[13]["fallback_tunnel_unique_id_full"], "Circ 3.5")
        self.assertEqual(timings[14]["tunnel_unique_id"], "Circ 4.15")
        self.assertEqual(timings[16]["selected_assigned_streams"], 2)
        self.assertEqual(timings[16]["max_wait_assigned_streams"], 1)
        self.assertEqual(timings[10]["fallback_tunnel_unique_id"], "Circ")
        self.assertEqual(timings[11]["tunnel_unique_id"], "Circ 4.14")
        self.assertEqual(timings[0]["load_aware_assignment_spread"], 4)
        self.assertEqual(timings[0]["load_aware_min_assignment_spread"], 2)
        self.assertEqual(timings[0]["load_aware_assignment_candidate_index"], 1)
        self.assertEqual(timings[0]["health_aware_candidate_index"], 0)
        self.assertEqual(timings[0]["health_aware_assignment_score_bps"], 50000)
        self.assertEqual(timings[0]["health_aware_candidate_score_bps"], 120000)
        self.assertEqual(timings[0]["selected_assigned_streams"], 5)
        self.assertEqual(timings[0]["selected_health_score_bps"], 120000)
        self.assertFalse(timings[0]["selected_has_bad_health"])
        self.assertFalse(load_aware_guardrail_kept_first(timings[0]))

        self.assertTrue(health_aware_changed_assignment(timings[0]))
        self.assertFalse(health_aware_guard_kept_assignment(timings[0]))
        self.assertTrue(
            health_aware_guard_kept_assignment(
                {
                    "select_health_aware": True,
                    "selected_candidate_index": 1,
                    "load_aware_assignment_candidate_index": 1,
                    "health_aware_candidate_index": 0,
                }
            )
        )
        self.assertTrue(
            load_aware_guardrail_kept_first(
                {
                    "selected_candidate_index": 0,
                    "load_aware_assignment_spread": 1,
                    "load_aware_min_assignment_spread": 2,
                    "candidate_assignment_summary": "0:Circ~0.1:5,1:Circ~0.2:4",
                }
            )
        )
        self.assertEqual(
            parse_torfast_candidate_assignment_summary(
                timings[0]["candidate_assignment_summary"]
            ),
            [
                {
                    "index": 0,
                    "tunnel_unique_id": "Circ 0.1",
                    "assigned_streams": 5,
                },
                {
                    "index": 1,
                    "tunnel_unique_id": "Circ 0.2",
                    "assigned_streams": 1,
                },
                {
                    "index": 2,
                    "tunnel_unique_id": "Circ 0.3",
                    "assigned_streams": 3,
                },
            ],
        )
        self.assertEqual(
            parse_torfast_candidate_health_summary(
                timings[0]["candidate_health_summary"]
            ),
            [
                {
                    "index": 0,
                    "tunnel_unique_id": "Circ 0.1",
                    "relay_data_cells": 4,
                    "relay_data_bytes": 12000,
                    "max_relay_data_gap_ms": 25,
                },
                {
                    "index": 1,
                    "tunnel_unique_id": "Circ 0.2",
                    "relay_data_cells": 2,
                    "relay_data_bytes": 900,
                    "max_relay_data_gap_ms": 800,
                },
                {
                    "index": 2,
                    "tunnel_unique_id": "Circ 0.3",
                    "relay_data_cells": 0,
                    "relay_data_bytes": 0,
                    "max_relay_data_gap_ms": 0,
                },
            ],
        )
        self.assertEqual(
            parse_torfast_candidate_health_summary(
                "0:Circ~0.1:4:12000:25:120000:100:12"
            ),
            [
                {
                    "index": 0,
                    "tunnel_unique_id": "Circ 0.1",
                    "relay_data_cells": 4,
                    "relay_data_bytes": 12000,
                    "max_relay_data_gap_ms": 25,
                    "health_score_bps": 120000,
                    "health_span_ms": 100,
                    "health_age_ms": 12,
                },
            ],
        )
        self.assertEqual(
            parse_torfast_candidate_health_summary(
                "0:Circ~0.1:4:12000:25:120000:100:12:2:4"
            ),
            [
                {
                    "index": 0,
                    "tunnel_unique_id": "Circ 0.1",
                    "relay_data_cells": 4,
                    "relay_data_bytes": 12000,
                    "max_relay_data_gap_ms": 25,
                    "health_score_bps": 120000,
                    "health_span_ms": 100,
                    "health_age_ms": 12,
                    "active_streams": 2,
                    "max_active_streams": 4,
                },
            ],
        )
        self.assertEqual(
            parse_torfast_candidate_health_summary(
                "0:Circ~0.1:4:12000:25:120000:100:12:2:4:999"
            ),
            [
                {
                    "index": 0,
                    "tunnel_unique_id": "Circ 0.1",
                    "relay_data_cells": 4,
                    "relay_data_bytes": 12000,
                    "max_relay_data_gap_ms": 25,
                    "health_score_bps": 120000,
                    "health_span_ms": 100,
                    "health_age_ms": 12,
                    "active_streams": 2,
                    "max_active_streams": 4,
                    "active_stream_age_ms": 999,
                },
            ],
        )
        self.assertEqual(
            parse_torfast_open_support_summary(timings[0]["open_support_summary"]),
            {
                "total": 5,
                "supported": 3,
                "unusable": 0,
                "usage_kind": 1,
                "isolation": 1,
                "stability": 0,
                "port": 0,
                "country": 0,
                "other": 0,
                "exit_unisolated": 1,
                "exit_compatible_isolated": 2,
                "exit_incompatible_isolated": 1,
                "exit_port_blocked": 0,
                "exit_stability_blocked": 0,
                "exit_country_blocked": 0,
            },
        )
        self.assertEqual(timings[1]["usage_kind"], "preemptive")
        self.assertEqual(timings[1]["pending_candidates"], 2)
        self.assertEqual(timings[2]["usage_kind"], "exit")
        self.assertEqual(timings[2]["hedge_after_ms"], 1500)
        self.assertEqual(timings[4]["usage_kind"], "exit")
        self.assertEqual(timings[4]["plans"], 1)
        self.assertEqual(timings[5]["usage_kind"], "exit")
        self.assertEqual(timings[5]["delay_ms"], 1500)
        self.assertEqual(timings[6]["usage_kind"], "exit")
        self.assertEqual(timings[6]["plans"], 1)
        self.assertEqual(timings[7]["usage_kind"], "hs_circ_base")
        self.assertEqual(timings[7]["plans"], 1)
        self.assertEqual(timings[8]["usage_kind"], "exit")
        self.assertEqual(timings[8]["target"], 2)
        self.assertEqual(timings[8]["selected_assigned_streams"], 2)
        self.assertEqual(timings[8]["min_assigned_streams"], 2)
        self.assertTrue(timings[8]["active_stream_cap_saturated"])
        self.assertEqual(timings[8]["selected_active_streams"], 1)
        self.assertEqual(timings[8]["select_max_active_streams"], 1)
        self.assertTrue(timings[8]["prewarm_first_stream"])
        self.assertTrue(timings[8]["selected_has_bad_health"])
        self.assertEqual(timings[8]["selected_health_cells"], 4)
        self.assertEqual(timings[8]["selected_health_bytes"], 12000)
        self.assertEqual(timings[8]["selected_health_max_gap_ms"], 900)
        self.assertEqual(timings[8]["selected_health_score_bps"], 0)
        self.assertEqual(timings[8]["selected_health_span_ms"], 1200)
        self.assertEqual(timings[8]["selected_health_age_ms"], 50)
        self.assertTrue(timings[8]["require_bad_health"])
        self.assertEqual(timings[8]["exit_incompatible_isolated"], 4)
        self.assertEqual(timings[8]["other_isolation_min"], 3)
        self.assertTrue(timings[8]["other_isolation_pressure"])
        self.assertEqual(timings[8]["plans"], 1)
        self.assertEqual(timings[9]["event"], "same_isolation_topup_failed")
        self.assertEqual(timings[9]["err"], "launch_failed")
        self.assertEqual(event_timestamp_gaps_ms(timings[:2]), [1000.0])

    def test_parses_bad_health_replacement_later_selection_events(self) -> None:
        timings = parse_torfast_circuit_selection_timings(
            [
                "2026-06-06T23:12:41Z INFO tor_circmgr::mgr: pending_id=0x1 open_candidates=1 pending_candidates=0 selected_assigned_streams=1 selected_has_bad_health=true selected_health_max_gap_ms=900 selected_health_score_bps=12000 plans=1 usage_kind=exit fallback_tunnel_unique_id=Circ 1.5 torfast circuit selection bad health replacement",
                "2026-06-06T23:12:42Z INFO tor_circmgr::mgr: tunnel_unique_id=Circ 1.6 replacement_built_age_ms=800 replacement_open_index=1 replacement_candidate_index=1 candidate_context_count=2 selected_tunnel_unique_id=Circ~1.5 skip_reason=better_health selected_assigned_streams=1 selected_health_score_bps=50000 replacement_assigned_streams=1 replacement_health_score_bps=10000 usage_kind=exit torfast circuit selection bad health replacement later selection candidate skipped",
                "2026-06-06T23:12:43Z INFO tor_circmgr::mgr: tunnel_unique_id=Circ 1.7 replacement_built_age_ms=1200 support_reason=isolation exit_isolation_bucket=exit_incompatible_isolated replacement_assigned_streams=0 replacement_health_score_bps=0 usage_kind=exit torfast circuit selection bad health replacement later selection filtered",
                "2026-06-06T23:12:44Z INFO tor_circmgr::mgr: tunnel_unique_id=Circ 1.8 replacement_built_age_ms=500 replacement_open_index=0 replacement_candidate_index=0 candidate_context_count=1 selected_tunnel_unique_id=Circ~1.8 usage_kind=exit torfast circuit selection bad health replacement later selection selected",
                "2026-06-06T23:12:45Z INFO tor_circmgr::mgr: tunnel_unique_id=Circ 1.9 replacement_built_age_ms=700 replacement_open_index=3 candidate_context_count=2 selected_tunnel_unique_id=Circ~1.5 usage_kind=exit torfast circuit selection bad health replacement later selection supported outside candidate window",
                "2026-06-06T23:12:46Z INFO tor_circmgr::mgr: tunnel_unique_id=Circ 2.0 replacement_built_age_ms=900 replacement_assigned_streams=0 torfast circuit selection bad health replacement expired without later selection",
                "2026-06-06T23:12:47Z INFO tor_circmgr::mgr: tunnel_unique_id=Circ 2.1 replacement_built_age_ms=1000 replacement_assigned_streams=0 torfast circuit selection bad health replacement cleared without later selection",
            ]
        )

        self.assertEqual(
            [timing["event"] for timing in timings],
            [
                "bad_health_replacement",
                "bad_health_replacement_later_selection_candidate_skipped",
                "bad_health_replacement_later_selection_filtered",
                "bad_health_replacement_later_selection_selected",
                "bad_health_replacement_later_selection_supported_outside_candidate_window",
                "bad_health_replacement_expired_without_later_selection",
                "bad_health_replacement_cleared_without_later_selection",
            ],
        )
        self.assertEqual(timings[0]["fallback_tunnel_unique_id_full"], "Circ 1.5")
        self.assertEqual(timings[1]["tunnel_unique_id"], "Circ 1.6")
        self.assertEqual(timings[1]["selected_tunnel_unique_id"], "Circ 1.5")
        self.assertEqual(timings[1]["skip_reason"], "better_health")
        self.assertEqual(timings[2]["support_reason"], "isolation")

    def test_same_isolation_topup_ab_rows_compare_attempt_runs(self) -> None:
        payload = {
            "targets": ["https://example.com/"],
            "profiles": {
                "arti_release_browser": {
                    "benchmarks": {
                        "https://example.com/": {
                            "runs": [
                                {"run_index": 1, "ok": True, "load_ms": 1000},
                                {"run_index": 2, "ok": True, "load_ms": 2000},
                                {"run_index": 3, "ok": True, "load_ms": 1200},
                            ]
                        }
                    }
                },
                "arti_release_browser_sameiso2": {
                    "benchmarks": {
                        "https://example.com/": {
                            "runs": [
                                {"run_index": 1, "ok": True, "load_ms": 900},
                                {
                                    "run_index": 2,
                                    "ok": True,
                                    "load_ms": 2500,
                                    "proxy_signal_lines": [
                                        "2026-06-06T23:12:41Z DEBUG tor_circmgr::mgr: pending_id=0xabc open_candidates=1 pending_candidates=0 target=2 selected_assigned_streams=2 min_assigned_streams=2 selected_has_bad_health=true selected_health_max_gap_ms=900 selected_health_score_bps=0 selected_health_age_ms=50 require_bad_health=true plans=1 usage_kind=exit torfast circuit selection same isolation topup",
                                        "2026-06-06T23:12:41Z DEBUG tor_circmgr::mgr: pending_id=0xabc open_candidates=1 pending_candidates=0 target=2 selected_assigned_streams=2 min_assigned_streams=2 selected_has_bad_health=true selected_health_max_gap_ms=900 selected_health_score_bps=0 selected_health_age_ms=50 require_bad_health=true plans=1 usage_kind=exit torfast circuit selection same isolation topup",
                                    ],
                                },
                                {
                                    "run_index": 3,
                                    "ok": True,
                                    "load_ms": 1100,
                                    "proxy_signal_lines": [
                                        "2026-06-06T23:12:42Z DEBUG tor_circmgr::mgr: open_candidates=1 pending_candidates=0 target=2 selected_assigned_streams=3 min_assigned_streams=2 selected_has_bad_health=true selected_health_max_gap_ms=1000 selected_health_score_bps=0 selected_health_age_ms=60 require_bad_health=true usage_kind=exit err=launch_failed torfast circuit selection same isolation topup failed",
                                    ],
                                },
                            ]
                        }
                    }
                },
            },
        }

        rows = arti_profile_same_isolation_topup_ab_rows(payload)

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["target"], "https://example.com/")
        self.assertEqual(row["attempt_runs"], 2)
        self.assertEqual(row["no_attempt_runs"], 1)
        self.assertEqual(row["same_isolation_topups"], 1)
        self.assertEqual(row["same_isolation_topup_failures"], 1)
        self.assertEqual(row["topup_built_runs"], 0)
        self.assertEqual(row["topup_candidate_seen_runs"], 0)
        self.assertEqual(row["topup_used_runs"], 0)
        self.assertEqual(row["topup_missing_lifecycle_runs"], 1)
        self.assertEqual(row["attempt_load_wins"], 1)
        self.assertEqual(row["no_attempt_load_wins"], 1)
        self.assertEqual(row["attempt_median_load_delta_ms"], 200.0)
        self.assertEqual(row["no_attempt_median_load_delta_ms"], -100.0)
        self.assertEqual(row["attempt_candidate_median_load_ms"], 1800.0)
        self.assertEqual(row["attempt_baseline_median_load_ms"], 1600.0)
        self.assertEqual(row["attempt_candidate_max_load_ms"], 2500)
        self.assertEqual(row["no_attempt_candidate_max_load_ms"], 900)
        self.assertEqual(row["max_topup_assigned_streams"], 3)
        self.assertEqual(row["min_topup_floor"], 2)

    def test_same_isolation_topup_lifecycle_rows_match_build_and_use(self) -> None:
        base = int(parse_log_timestamp_ms("2026-06-06T23:12:40Z x") or 0)
        payload = {
            "profiles": {
                "arti_release_browser_sameiso2": {
                    "benchmarks": {
                        "https://example.com/": {
                            "runs": [
                                {
                                    "run_index": 1,
                                    "ok": True,
                                    "load_ms": 900,
                                    "performance_timing": {
                                        "time_origin_ms": base,
                                        "navigation": {"loadEventEnd": 6000},
                                    },
                                    "proxy_signal_lines": [
                                        "2026-06-06T23:12:41Z DEBUG tor_circmgr::mgr: pending_id=0x1 open_candidates=1 pending_candidates=0 target=2 selected_assigned_streams=2 min_assigned_streams=2 selected_has_bad_health=true selected_health_max_gap_ms=900 selected_health_score_bps=12000 selected_health_age_ms=50 require_bad_health=true plans=1 usage_kind=exit torfast circuit selection same isolation topup",
                                        "2026-06-06T23:12:41Z DEBUG tor_circmgr::mgr: pending_id=0x1 open_candidates=1 pending_candidates=0 target=2 selected_assigned_streams=2 min_assigned_streams=2 selected_has_bad_health=true selected_health_max_gap_ms=900 selected_health_score_bps=12000 selected_health_age_ms=50 require_bad_health=true plans=1 usage_kind=exit torfast circuit selection same isolation topup",
                                        "2026-06-06T23:12:42Z DEBUG tor_circmgr::mgr: torfast circuit selection build complete pending_id=0x1 pending_age_ms=540 tunnel_unique_id=Circ 1.6",
                                        "2026-06-06T23:12:43Z DEBUG tor_circmgr::mgr: open_candidates=2 select_load_aware=true select_health_aware=true selected_candidate_index=1 selected_assigned_streams=0 selected_health_score_bps=0 selected_has_bad_health=false candidate_assignment_summary=0:Circ~0.5:4,1:Circ~1.6:0 candidate_health_summary=0:Circ~0.5:3:2000:10:50000:100:1,1:Circ~1.6:0:0:0:0:0:0 usage_kind=\"exit\" tunnel_unique_id=Circ 1.6 torfast circuit selection open",
                                        "2026-06-06T23:12:43Z DEBUG arti_client::client: Got a circuit for [scrubbed]:443 tunnel_id=Circ 1.6",
                                        "2026-06-06T23:12:43Z DEBUG arti::proxy::socks: torfast socks timing stream linked timing_id=4 target_kind=hostname port=443 circ_id=Circ 1.6 hop=#3 stream_id=22 elapsed_ms=0",
                                        "2026-06-06T23:12:43Z DEBUG tor_proto::client::reactor::circuit::circhop: torfast stream scheduler picked circ_id=Circ 1.6 (Tunnel 25) hop=#3 stream_id=22 relay_cmd=DATA",
                                        "2026-06-06T23:12:44Z INFO tor_circmgr::mgr: pending_id=0x2 open_candidates=1 pending_candidates=0 target=2 selected_assigned_streams=2 min_assigned_streams=2 selected_has_bad_health=true selected_health_max_gap_ms=700 selected_health_score_bps=9000 require_bad_health=true plans=1 usage_kind=exit torfast circuit selection same isolation topup",
                                        "2026-06-06T23:12:44Z INFO tor_circmgr::mgr: pending_id=0x3 open_candidates=1 pending_candidates=0 target=2 selected_assigned_streams=2 min_assigned_streams=2 selected_has_bad_health=true selected_health_max_gap_ms=650 selected_health_score_bps=8500 require_bad_health=true plans=1 usage_kind=exit torfast circuit selection same isolation topup",
                                        "2026-06-06T23:12:45Z DEBUG tor_circmgr::mgr: torfast circuit selection build failed pending_id=0x2 pending_age_ms=60000 err=timeout",
                                        "2026-06-06T23:12:45Z INFO tor_circmgr::mgr: open_candidates=2 select_load_aware=true select_health_aware=true selected_candidate_index=1 selected_assigned_streams=0 selected_health_score_bps=0 selected_has_bad_health=false candidate_assignment_summary=0:Circ~1.6:4,1:Circ~1.7:0 candidate_health_summary=0:Circ~1.6:3:2000:10:50000:100:1,1:Circ~1.7:0:0:0:0:0:0 usage_kind=\"exit\" tunnel_unique_id=Circ 1.7 torfast circuit selection open",
                                        "2026-06-06T23:12:45Z DEBUG arti_client::client: Got a circuit for [scrubbed]:443 tunnel_id=Circ 1.7",
                                        "2026-06-06T23:12:45Z DEBUG arti::proxy::socks: torfast socks timing stream linked timing_id=5 target_kind=hostname port=443 circ_id=Circ 1.7 hop=#3 stream_id=23 elapsed_ms=0",
                                        "2026-06-06T23:12:46Z INFO tor_circmgr::mgr: open_candidates=1 pending_candidates=0 target=2 selected_assigned_streams=3 min_assigned_streams=2 selected_has_bad_health=true selected_health_max_gap_ms=1000 selected_health_score_bps=8000 require_bad_health=true usage_kind=exit err=launch_failed torfast circuit selection same isolation topup failed",
                                    ],
                                }
                            ]
                        }
                    }
                }
            }
        }

        rows = torfast_same_isolation_topup_lifecycle_rows(payload)

        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[0]["pending_id"], "0x1")
        self.assertEqual(rows[0]["outcome"], "built")
        self.assertEqual(rows[0]["build_pending_age_ms"], 540)
        self.assertEqual(rows[0]["built_tunnel_unique_id"], "Circ 1.6")
        self.assertEqual(rows[0]["page_load_after_build_ms"], 4000.0)
        self.assertEqual(rows[0]["open_count_after_build"], 2)
        self.assertEqual(rows[0]["exit_open_count_after_build"], 2)
        self.assertEqual(rows[0]["stream_link_count_after_build"], 2)
        self.assertEqual(rows[0]["first_stream_after_build_ms"], 1000.0)
        self.assertEqual(rows[0]["built_circuit_candidate_open_count_after_build"], 2)
        self.assertEqual(rows[0]["first_built_candidate_after_build_ms"], 1000.0)
        self.assertEqual(rows[0]["first_candidate_selected_tunnel_unique_id"], "Circ 1.6")
        self.assertEqual(rows[0]["first_candidate_selected_assigned_streams"], 0)
        self.assertEqual(rows[0]["first_candidate_selected_health_score_bps"], 0)
        self.assertEqual(rows[0]["first_candidate_built_assigned_streams"], 0)
        self.assertEqual(rows[0]["first_candidate_built_health_score_bps"], 0)
        self.assertTrue(rows[0]["used_by_streams"])
        self.assertEqual(rows[0]["selected_open_count_after_build"], 1)
        self.assertEqual(rows[0]["got_circuit_count_after_build"], 1)
        self.assertEqual(rows[0]["linked_stream_count_after_build"], 1)
        self.assertEqual(rows[0]["scheduler_pick_count_after_build"], 1)
        self.assertEqual(rows[0]["first_use_after_build_ms"], 1000.0)
        self.assertEqual(rows[0]["topup_selected_assigned_streams"], 2)
        self.assertEqual(rows[0]["topup_selected_health_score_bps"], 12000)
        self.assertEqual(rows[1]["pending_id"], "0x2")
        self.assertEqual(rows[1]["outcome"], "build_failed")
        self.assertEqual(rows[1]["build_pending_age_ms"], 60000)
        self.assertEqual(rows[1]["page_load_after_build_ms"], 1000.0)
        self.assertIsNone(rows[1]["open_count_after_build"])
        self.assertFalse(rows[1]["used_by_streams"])
        self.assertEqual(rows[2]["pending_id"], "0x3")
        self.assertEqual(rows[2]["outcome"], "candidate_seen_no_build_log")
        self.assertTrue(rows[2]["candidate_seen_without_build_log"])
        self.assertEqual(rows[2]["built_tunnel_unique_id"], "Circ 1.7")
        self.assertEqual(rows[2]["page_load_after_build_ms"], 1000.0)
        self.assertEqual(rows[2]["built_circuit_candidate_open_count_after_build"], 1)
        self.assertEqual(rows[2]["first_built_candidate_after_build_ms"], 0.0)
        self.assertEqual(rows[2]["first_candidate_built_assigned_streams"], 0)
        self.assertTrue(rows[2]["used_by_streams"])
        self.assertEqual(rows[3]["outcome"], "topup_failed")
        self.assertIsNone(rows[3]["page_load_after_build_ms"])
        self.assertIsNone(rows[3]["open_count_after_build"])
        self.assertEqual(rows[3]["topup_selected_assigned_streams"], 3)

    def test_same_isolation_topup_timing_rows_group_attempt_outcome(self) -> None:
        base = int(parse_log_timestamp_ms("2026-06-06T23:12:40Z x") or 0)
        payload = {
            "targets": ["https://example.com/"],
            "profiles": {
                "arti_release_browser": {
                    "benchmarks": {
                        "https://example.com/": {
                            "runs": [
                                {"run_index": 1, "ok": True, "load_ms": 1000},
                                {"run_index": 2, "ok": True, "load_ms": 1200},
                            ]
                        }
                    }
                },
                "arti_release_browser_sameiso2": {
                    "benchmarks": {
                        "https://example.com/": {
                            "runs": [
                                {"run_index": 1, "ok": True, "load_ms": 900},
                                {
                                    "run_index": 2,
                                    "ok": True,
                                    "load_ms": 1800,
                                    "performance_timing": {
                                        "time_origin_ms": base,
                                        "navigation": {"loadEventEnd": 5000},
                                    },
                                    "proxy_signal_lines": [
                                        "2026-06-06T23:12:41Z INFO tor_circmgr::mgr: pending_id=0x1 open_candidates=1 pending_candidates=0 target=2 selected_assigned_streams=2 min_assigned_streams=2 selected_has_bad_health=true selected_health_max_gap_ms=900 selected_health_score_bps=12000 selected_health_age_ms=50 require_bad_health=true plans=1 usage_kind=exit torfast circuit selection same isolation topup",
                                        "2026-06-06T23:12:42Z INFO tor_circmgr::mgr: torfast circuit selection build complete pending_id=0x1 pending_age_ms=540 tunnel_unique_id=Circ 1.6",
                                        "2026-06-06T23:12:43Z INFO tor_circmgr::mgr: open_candidates=2 selected_candidate_index=1 selected_assigned_streams=0 selected_health_score_bps=0 selected_has_bad_health=false candidate_assignment_summary=0:Circ~0.5:4,1:Circ~1.6:0 candidate_health_summary=0:Circ~0.5:3:2000:10:50000:100:1,1:Circ~1.6:0:0:0:0:0:0 usage_kind=\"exit\" tunnel_unique_id=Circ 1.6 torfast circuit selection open",
                                        "2026-06-06T23:12:43Z INFO arti_client::client: Got a circuit for [scrubbed]:443 tunnel_id=Circ 1.6",
                                    ],
                                },
                            ]
                        }
                    }
                },
            },
        }

        rows = arti_profile_same_isolation_topup_timing_rows(payload)

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["target"], "https://example.com/")
        self.assertEqual(row["topup_runs"], 1)
        self.assertEqual(row["topups"], 1)
        self.assertEqual(row["built_or_seen_topups"], 1)
        self.assertEqual(row["used_topups"], 1)
        self.assertEqual(row["first_selected_topups"], 1)
        self.assertEqual(row["median_build_age_ms"], 540)
        self.assertEqual(row["median_page_load_after_build_ms"], 3000.0)
        self.assertEqual(row["median_first_candidate_after_build_ms"], 1000.0)
        self.assertEqual(row["median_first_use_after_build_ms"], 1000.0)
        self.assertEqual(row["attempt_median_load_delta_ms"], 600.0)
        self.assertEqual(row["no_attempt_median_load_delta_ms"], -100.0)
        self.assertEqual(row["used_run_median_load_delta_ms"], 600.0)
        self.assertIsNone(row["unused_run_median_load_delta_ms"])
        self.assertEqual(
            row["diagnosis"],
            "top-up attempt runs were slower than no-attempt runs",
        )

    def test_same_isolation_topup_nonuse_rows_explain_first_candidate_choice(
        self,
    ) -> None:
        base = int(parse_log_timestamp_ms("2026-06-06T23:12:40Z x") or 0)
        payload = {
            "profiles": {
                "arti_release_browser_sameiso2": {
                    "benchmarks": {
                        "https://example.com/": {
                            "runs": [
                                {
                                    "run_index": 1,
                                    "ok": True,
                                    "load_ms": 2000,
                                    "performance_timing": {
                                        "time_origin_ms": base,
                                        "navigation": {"loadEventEnd": 6000},
                                    },
                                    "proxy_signal_lines": [
                                        "2026-06-06T23:12:41Z INFO tor_circmgr::mgr: pending_id=0x1 open_candidates=1 pending_candidates=0 target=2 selected_assigned_streams=2 min_assigned_streams=2 selected_has_bad_health=false selected_health_max_gap_ms=900 selected_health_score_bps=12000 require_bad_health=false plans=1 usage_kind=exit torfast circuit selection same isolation topup",
                                        "2026-06-06T23:12:42Z INFO tor_circmgr::mgr: torfast circuit selection build complete pending_id=0x1 pending_age_ms=540 tunnel_unique_id=Circ 1.6",
                                        "2026-06-06T23:12:43Z INFO tor_circmgr::mgr: open_candidates=2 selected_candidate_index=0 selected_assigned_streams=1 selected_health_score_bps=50000 selected_has_bad_health=false candidate_assignment_summary=0:Circ~0.5:1,1:Circ~1.6:3 candidate_health_summary=0:Circ~0.5:3:2000:10:50000:100:1,1:Circ~1.6:2:1000:20:10000:100:1 usage_kind=\"exit\" tunnel_unique_id=Circ 0.5 torfast circuit selection open",
                                    ],
                                }
                            ]
                        }
                    }
                }
            }
        }

        rows = arti_profile_same_isolation_topup_nonuse_rows(payload)

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["profile"], "arti_release_browser_sameiso2")
        self.assertEqual(row["target"], "https://example.com/")
        self.assertEqual(row["run_index"], 1)
        self.assertEqual(row["built_tunnel_unique_id"], "Circ 1.6")
        self.assertEqual(row["first_built_candidate_after_build_ms"], 1000.0)
        self.assertEqual(row["first_candidate_selected_tunnel_unique_id"], "Circ 0.5")
        self.assertEqual(row["first_candidate_selected_assigned_streams"], 1)
        self.assertEqual(row["first_candidate_built_assigned_streams"], 3)
        self.assertEqual(row["first_candidate_selected_health_score_bps"], 50000)
        self.assertEqual(row["first_candidate_built_health_score_bps"], 10000)
        self.assertFalse(row["used_by_streams"])
        self.assertEqual(row["nonuse_reason"], "lower-assignment circuit selected")

    def test_same_isolation_topup_nonuse_rows_explain_no_later_selection(
        self,
    ) -> None:
        base = int(parse_log_timestamp_ms("2026-06-06T23:12:40Z x") or 0)
        payload = {
            "profiles": {
                "arti_release_browser_sameiso2": {
                    "benchmarks": {
                        "https://example.com/": {
                            "runs": [
                                {
                                    "run_index": 1,
                                    "ok": True,
                                    "load_ms": 2000,
                                    "proxy_signal_lines": [
                                        "2026-06-06T23:12:41Z INFO tor_circmgr::mgr: pending_id=0x1 open_candidates=1 pending_candidates=0 target=2 selected_assigned_streams=0 min_assigned_streams=2 selected_has_bad_health=false selected_health_max_gap_ms=0 selected_health_score_bps=0 require_bad_health=false plans=1 usage_kind=exit torfast circuit selection same isolation topup",
                                        "2026-06-06T23:12:42Z INFO tor_circmgr::mgr: torfast circuit selection build complete pending_id=0x1 pending_age_ms=540 tunnel_unique_id=Circ 1.6",
                                        f"2026-06-06T23:12:43Z INFO arti::proxy::socks: timing_id=7 target_kind=hostname port=443 conn_started_epoch_ms={base + 500} circ_id=Circ 0.5 hop=3 stream_id=22 elapsed_ms=2500 torfast socks timing stream linked",
                                    ],
                                }
                            ]
                        }
                    }
                }
            }
        }

        rows = arti_profile_same_isolation_topup_nonuse_rows(payload)

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["built_tunnel_unique_id"], "Circ 1.6")
        self.assertEqual(row["open_count_after_build"], 0)
        self.assertEqual(row["stream_links_started_before_build"], 1)
        self.assertEqual(row["stream_links_started_after_build"], 0)
        self.assertEqual(row["first_stream_start_after_build_ms"], -1500.0)
        self.assertEqual(
            row["nonuse_reason"],
            "no later circuit selection; linked streams started before top-up was ready",
        )

    def test_same_isolation_topup_nonuse_rows_prefer_direct_filtered_proof(self) -> None:
        payload = {
            "profiles": {
                "arti_release_browser_sameiso2": {
                    "benchmarks": {
                        "https://example.com/": {
                            "runs": [
                                {
                                    "run_index": 1,
                                    "ok": True,
                                    "load_ms": 2000,
                                    "proxy_signal_lines": [
                                        "2026-06-06T23:12:41Z INFO tor_circmgr::mgr: pending_id=0x1 open_candidates=1 pending_candidates=0 target=2 selected_assigned_streams=0 min_assigned_streams=2 selected_has_bad_health=false selected_health_max_gap_ms=0 selected_health_score_bps=0 require_bad_health=false plans=1 usage_kind=exit torfast circuit selection same isolation topup",
                                        "2026-06-06T23:12:42Z INFO tor_circmgr::mgr: torfast circuit selection build complete pending_id=0x1 pending_age_ms=540 build_origin=same_isolation_topup pending_request_matches=1 tunnel_unique_id=Circ 1.6",
                                        "2026-06-06T23:12:43Z INFO tor_circmgr::mgr: tunnel_unique_id=Circ 1.6 topup_built_age_ms=800 support_reason=isolation exit_isolation_bucket=exit_incompatible_isolated selected_tunnel_unique_id=Circ~0.5 topup_assigned_streams=0 topup_health_score_bps=0 topup_health_max_gap_ms=0 topup_active_streams=0 usage_kind=exit torfast circuit selection same isolation topup later selection filtered",
                                    ],
                                }
                            ]
                        }
                    }
                }
            }
        }

        rows = arti_profile_same_isolation_topup_nonuse_rows(payload)

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["build_pending_request_matches"], 1)
        self.assertEqual(
            row["first_later_selection_event"],
            "same_isolation_topup_later_selection_filtered",
        )
        self.assertEqual(row["nonuse_reason"], "filtered by isolation")

    def test_same_isolation_topup_nonuse_rows_prefer_direct_expired_proof(self) -> None:
        payload = {
            "profiles": {
                "arti_release_browser_sameiso2": {
                    "benchmarks": {
                        "https://example.com/": {
                            "runs": [
                                {
                                    "run_index": 1,
                                    "ok": True,
                                    "load_ms": 2000,
                                    "proxy_signal_lines": [
                                        "2026-06-06T23:12:41Z INFO tor_circmgr::mgr: pending_id=0x1 open_candidates=1 pending_candidates=0 target=2 selected_assigned_streams=0 min_assigned_streams=2 selected_has_bad_health=false selected_health_max_gap_ms=0 selected_health_score_bps=0 require_bad_health=false plans=1 usage_kind=exit torfast circuit selection same isolation topup",
                                        "2026-06-06T23:12:42Z INFO tor_circmgr::mgr: torfast circuit selection build complete pending_id=0x1 pending_age_ms=540 build_origin=same_isolation_topup pending_request_matches=0 tunnel_unique_id=Circ 1.6",
                                        "2026-06-06T23:12:50Z INFO tor_circmgr::mgr: tunnel_unique_id=Circ 1.6 topup_built_age_ms=8000 topup_assigned_streams=0 torfast circuit selection same isolation topup expired without later selection",
                                    ],
                                }
                            ]
                        }
                    }
                }
            }
        }

        rows = arti_profile_same_isolation_topup_nonuse_rows(payload)

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["build_pending_request_matches"], 0)
        self.assertEqual(
            row["first_later_selection_event"],
            "same_isolation_topup_expired_without_later_selection",
        )
        self.assertEqual(row["nonuse_reason"], "expired without later selection")

    def test_same_isolation_topup_selected_open_counts_as_use(self) -> None:
        payload = {
            "profiles": {
                "arti_release_browser_sameiso2": {
                    "benchmarks": {
                        "https://example.com/": {
                            "runs": [
                                {
                                    "run_index": 1,
                                    "ok": True,
                                    "load_ms": 900,
                                    "proxy_signal_lines": [
                                        "2026-06-06T23:12:41Z INFO tor_circmgr::mgr: pending_id=0x1 open_candidates=1 pending_candidates=0 target=2 selected_assigned_streams=8 min_assigned_streams=8 selected_has_bad_health=false selected_health_max_gap_ms=200 selected_health_score_bps=12000 require_bad_health=false plans=1 usage_kind=exit torfast circuit selection same isolation topup",
                                        "2026-06-06T23:12:42Z INFO tor_circmgr::mgr: torfast circuit selection build complete pending_id=0x1 pending_age_ms=540 tunnel_unique_id=Circ 1.6",
                                        "2026-06-06T23:12:43Z INFO tor_circmgr::mgr: open_candidates=2 select_load_aware=true select_health_aware=true selected_candidate_index=1 selected_assigned_streams=0 selected_health_score_bps=0 selected_has_bad_health=false candidate_assignment_summary=0:Circ~0.5:4,1:Circ~1.6:0 candidate_health_summary=0:Circ~0.5:3:2000:10:50000:100:1,1:Circ~1.6:0:0:0:0:0:0 usage_kind=\"exit\" tunnel_unique_id=Circ 1.6 torfast circuit selection open",
                                    ],
                                }
                            ]
                        }
                    }
                }
            }
        }

        rows = torfast_same_isolation_topup_lifecycle_rows(payload)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["selected_open_count_after_build"], 1)
        self.assertTrue(rows[0]["used_by_streams"])

    def test_same_isolation_topup_terminal_or_relay_counts_as_use(self) -> None:
        base = int(parse_log_timestamp_ms("2026-06-06T23:12:40Z x") or 0)
        payload = {
            "profiles": {
                "arti_release_browser_sameiso2": {
                    "benchmarks": {
                        "https://example.com/": {
                            "runs": [
                                {
                                    "run_index": 1,
                                    "ok": True,
                                    "load_ms": 1200,
                                    "performance_timing": {
                                        "time_origin_ms": base,
                                        "navigation": {"loadEventEnd": 9000},
                                    },
                                    "proxy_signal_lines": [
                                        "2026-06-06T23:12:41Z INFO tor_circmgr::mgr: pending_id=0x1 open_candidates=1 pending_candidates=0 target=2 selected_assigned_streams=2 min_assigned_streams=2 selected_has_bad_health=false selected_health_max_gap_ms=500 selected_health_score_bps=12000 require_bad_health=false plans=1 usage_kind=exit torfast circuit selection same isolation topup",
                                        "2026-06-06T23:12:42Z INFO tor_circmgr::mgr: torfast circuit selection build complete pending_id=0x1 pending_age_ms=540 tunnel_unique_id=Circ 1.6",
                                        "2026-06-06T23:12:43Z INFO tor_circmgr::mgr: tunnel_unique_id=Circ 1.6 topup_built_age_ms=1000 topup_open_index=0 topup_candidate_index=0 candidate_context_count=2 selected_tunnel_unique_id=Circ~1.6 selected_assigned_streams=0 selected_health_score_bps=0 selected_health_max_gap_ms=0 topup_assigned_streams=0 topup_health_score_bps=0 topup_health_max_gap_ms=0 topup_active_streams=0 usage_kind=exit torfast circuit selection same isolation topup later selection selected",
                                        f"2026-06-06T23:12:46Z INFO arti::proxy::socks: timing_id=4 target_kind=hostname port=443 conn_started_epoch_ms={base + 2500} circ_id=Circ 1.6 hop=#3 stream_id=22 relay_ms=1800 elapsed_ms=1800 ok=false copy_error_kind=not_connected copy_error=Stream_not_connected torfast socks timing relay finished",
                                        f"2026-06-06T23:12:46Z INFO tor_proto::client::stream::data: event_epoch_ms={base + 6000} circ_id=Circ 1.6 hop=#3 stream_id=22 connected=true first_data_after_start_ms=400 transfer_ms=1800 idle_after_last_data_ms=200 max_data_gap_ms=300 relay_data_bytes=95905 pending_after_bytes=0 user_read_bytes=95905 data_cells=199 read_events=200 sendmes=3 sendme_ok=3 min_recv_window_after_take=450 max_queued_after_bytes=18482 error_kind=not_connected not_connected_source=receiver_err stream_close_cause=stream_target_closed end_reason= returned_eof=false torfast stream receiver terminal summary",
                                    ],
                                }
                            ]
                        }
                    }
                }
            }
        }

        rows = torfast_same_isolation_topup_lifecycle_rows(payload)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["built_tunnel_unique_id"], "Circ 1.6")
        self.assertEqual(rows[0]["selected_open_count_after_build"], 0)
        self.assertEqual(rows[0]["linked_stream_count_after_build"], 0)
        self.assertEqual(rows[0]["relay_finished_count_after_build"], 1)
        self.assertEqual(rows[0]["stream_receiver_terminal_count_after_build"], 1)
        self.assertTrue(rows[0]["used_by_streams"])
        self.assertEqual(rows[0]["first_use_after_build_ms"], 4000.0)

    def test_same_isolation_topup_lifecycle_uses_later_profile_build_failure(
        self,
    ) -> None:
        payload = {
            "profiles": {
                "arti_release_browser_sameiso2": {
                    "benchmarks": {
                        "https://example.com/": {
                            "runs": [
                                {
                                    "run_index": 1,
                                    "ok": True,
                                    "load_ms": 900,
                                    "proxy_signal_lines": [
                                        "2026-06-06T23:12:41Z INFO tor_circmgr::mgr: pending_id=0x1 open_candidates=1 pending_candidates=0 target=2 selected_assigned_streams=8 min_assigned_streams=8 selected_has_bad_health=true selected_health_max_gap_ms=900 selected_health_score_bps=0 require_bad_health=true plans=1 usage_kind=exit torfast circuit selection same isolation topup",
                                    ],
                                },
                                {
                                    "run_index": 2,
                                    "ok": True,
                                    "load_ms": 1000,
                                    "proxy_signal_lines": [
                                        "2026-06-06T23:12:45Z INFO tor_circmgr::mgr: torfast circuit selection build failed pending_id=0x1 pending_age_ms=4511 usage_kind=exit err=first_hop",
                                    ],
                                },
                            ]
                        }
                    }
                }
            }
        }

        rows = torfast_same_isolation_topup_lifecycle_rows(payload)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["pending_id"], "0x1")
        self.assertEqual(rows[0]["outcome"], "build_failed")
        self.assertEqual(rows[0]["build_pending_age_ms"], 4511)
        self.assertFalse(rows[0]["used_by_streams"])

    def test_bad_health_replacement_lifecycle_rows_match_build_use_and_nonuse(
        self,
    ) -> None:
        base = int(parse_log_timestamp_ms("2026-06-06T23:12:40Z x") or 0)
        payload = {
            "profiles": {
                "arti_release_browser_healthaware": {
                    "benchmarks": {
                        "https://example.com/": {
                            "runs": [
                                {
                                    "run_index": 1,
                                    "ok": True,
                                    "load_ms": 900,
                                    "performance_timing": {
                                        "time_origin_ms": base,
                                        "navigation": {"loadEventEnd": 6000},
                                    },
                                    "proxy_signal_lines": [
                                        "2026-06-06T23:12:41Z INFO tor_circmgr::mgr: pending_id=0x1 open_candidates=1 pending_candidates=0 selected_assigned_streams=1 selected_has_bad_health=true selected_active_streams=1 selected_health_max_gap_ms=900 selected_health_score_bps=12000 selected_active_stream_age_ms=1100 plans=1 usage_kind=exit fallback_tunnel_unique_id=Circ 1.5 torfast circuit selection bad health replacement",
                                        "2026-06-06T23:12:42Z INFO tor_circmgr::mgr: torfast circuit selection build complete pending_id=0x1 pending_age_ms=540 build_origin=bad_health_replacement pending_request_matches=1 tunnel_unique_id=Circ 1.6",
                                        "2026-06-06T23:12:43Z INFO tor_circmgr::mgr: open_candidates=2 selected_candidate_index=1 selected_assigned_streams=0 selected_health_score_bps=0 selected_has_bad_health=false candidate_assignment_summary=0:Circ~1.5:1,1:Circ~1.6:0 candidate_health_summary=0:Circ~1.5:3:2000:10:50000:100:1,1:Circ~1.6:0:0:0:0:0:0 usage_kind=\"exit\" tunnel_unique_id=Circ 1.6 torfast circuit selection open",
                                        "2026-06-06T23:12:43Z DEBUG arti_client::client: Got a circuit for [scrubbed]:443 tunnel_id=Circ 1.6",
                                        f"2026-06-06T23:12:43Z DEBUG arti::proxy::socks: timing_id=4 target_kind=hostname port=443 conn_started_epoch_ms={base + 2500} circ_id=Circ 1.6 hop=#3 stream_id=22 elapsed_ms=0 torfast socks timing stream linked",
                                    ],
                                },
                                {
                                    "run_index": 2,
                                    "ok": True,
                                    "load_ms": 1400,
                                    "performance_timing": {
                                        "time_origin_ms": base,
                                        "navigation": {"loadEventEnd": 7000},
                                    },
                                    "proxy_signal_lines": [
                                        "2026-06-06T23:12:44Z INFO tor_circmgr::mgr: pending_id=0x2 open_candidates=1 pending_candidates=0 selected_assigned_streams=1 selected_has_bad_health=true selected_active_streams=1 selected_health_max_gap_ms=800 selected_health_score_bps=8000 selected_active_stream_age_ms=1200 plans=1 usage_kind=exit fallback_tunnel_unique_id=Circ 2.5 torfast circuit selection bad health replacement",
                                        "2026-06-06T23:12:45Z INFO tor_circmgr::mgr: torfast circuit selection build complete pending_id=0x2 pending_age_ms=600 build_origin=bad_health_replacement pending_request_matches=1 tunnel_unique_id=Circ 2.6",
                                        "2026-06-06T23:12:46Z INFO tor_circmgr::mgr: open_candidates=2 selected_candidate_index=0 selected_assigned_streams=1 selected_health_score_bps=50000 selected_has_bad_health=false candidate_assignment_summary=0:Circ~2.5:1,1:Circ~2.6:1 candidate_health_summary=0:Circ~2.5:3:2000:10:50000:100:1,1:Circ~2.6:2:1000:20:10000:100:1 usage_kind=\"exit\" tunnel_unique_id=Circ 2.5 torfast circuit selection open",
                                        "2026-06-06T23:12:46Z INFO tor_circmgr::mgr: tunnel_unique_id=Circ 2.6 replacement_built_age_ms=1000 replacement_open_index=1 replacement_candidate_index=1 candidate_context_count=2 selected_tunnel_unique_id=Circ~2.5 skip_reason=better_health selected_assigned_streams=1 selected_health_score_bps=50000 selected_health_max_gap_ms=10 replacement_assigned_streams=1 replacement_health_score_bps=10000 replacement_health_max_gap_ms=20 replacement_active_streams=0 usage_kind=exit torfast circuit selection bad health replacement later selection candidate skipped",
                                        "2026-06-06T23:12:47Z INFO tor_circmgr::mgr: pending_id=0x3 open_candidates=1 pending_candidates=0 selected_assigned_streams=1 selected_has_bad_health=true selected_active_streams=1 selected_health_max_gap_ms=800 selected_health_score_bps=8000 selected_active_stream_age_ms=1200 usage_kind=exit err=launch_failed fallback_tunnel_unique_id=Circ 3.5 torfast circuit selection bad health replacement failed",
                                    ],
                                },
                            ]
                        }
                    }
                }
            }
        }

        rows = torfast_bad_health_replacement_lifecycle_rows(payload)

        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["pending_id"], "0x1")
        self.assertEqual(rows[0]["outcome"], "built")
        self.assertEqual(rows[0]["build_pending_age_ms"], 540)
        self.assertEqual(rows[0]["build_origin"], "bad_health_replacement")
        self.assertEqual(rows[0]["build_pending_request_matches"], 1)
        self.assertEqual(rows[0]["built_tunnel_unique_id"], "Circ 1.6")
        self.assertEqual(rows[0]["replacement_fallback_tunnel_unique_id"], "Circ 1.5")
        self.assertEqual(rows[0]["replacement_selected_active_stream_age_ms"], 1100)
        self.assertEqual(rows[0]["replacement_selected_health_score_bps"], 12000)
        self.assertEqual(rows[0]["replacement_selected_health_max_gap_ms"], 900)
        self.assertEqual(rows[0]["page_load_after_build_ms"], 4000.0)
        self.assertEqual(rows[0]["built_circuit_candidate_open_count_after_build"], 1)
        self.assertEqual(rows[0]["first_built_candidate_after_build_ms"], 1000.0)
        self.assertEqual(rows[0]["first_candidate_selected_tunnel_unique_id"], "Circ 1.6")
        self.assertTrue(rows[0]["used_by_streams"])
        self.assertEqual(rows[0]["selected_open_count_after_build"], 1)
        self.assertEqual(rows[0]["got_circuit_count_after_build"], 1)
        self.assertEqual(rows[0]["linked_stream_count_after_build"], 1)
        self.assertEqual(rows[0]["first_use_after_build_ms"], 1000.0)
        self.assertEqual(bad_health_replacement_nonuse_reason(rows[0]), "")

        self.assertEqual(rows[1]["pending_id"], "0x2")
        self.assertEqual(rows[1]["outcome"], "built")
        self.assertEqual(rows[1]["built_tunnel_unique_id"], "Circ 2.6")
        self.assertEqual(rows[1]["first_candidate_selected_tunnel_unique_id"], "Circ 2.5")
        self.assertEqual(rows[1]["first_candidate_selected_health_score_bps"], 50000)
        self.assertEqual(rows[1]["first_candidate_built_health_score_bps"], 10000)
        self.assertEqual(
            rows[1]["first_later_selection_event"],
            "bad_health_replacement_later_selection_candidate_skipped",
        )
        self.assertEqual(rows[1]["first_later_selection_skip_reason"], "better_health")
        self.assertEqual(
            bad_health_replacement_later_proof_label(rows[1]),
            "candidate-skipped:better_health",
        )
        self.assertEqual(rows[1]["first_later_selection_built_age_ms"], 1000)
        self.assertFalse(rows[1]["used_by_streams"])
        self.assertEqual(
            bad_health_replacement_nonuse_reason(rows[1]),
            "better-health circuit selected",
        )

        self.assertEqual(rows[2]["pending_id"], "0x3")
        self.assertEqual(rows[2]["outcome"], "replacement_failed")
        self.assertEqual(
            bad_health_replacement_nonuse_reason(rows[2]), "replacement launch failed"
        )

    def test_bad_health_replacement_lifecycle_uses_later_profile_disposition(
        self,
    ) -> None:
        payload = {
            "profiles": {
                "arti_release_browser": {
                    "benchmarks": {
                        "https://example.com/": {
                            "runs": [
                                {
                                    "run_index": 1,
                                    "ok": True,
                                    "load_ms": 1200,
                                    "proxy_signal_lines": [
                                        "2026-06-06T23:12:41Z INFO tor_circmgr::mgr: pending_id=0x1 open_candidates=1 pending_candidates=0 selected_assigned_streams=1 selected_has_bad_health=true selected_active_streams=1 selected_health_max_gap_ms=900 selected_health_score_bps=12000 plans=1 usage_kind=exit fallback_tunnel_unique_id=Circ 1.5 torfast circuit selection bad health replacement",
                                        "2026-06-06T23:12:42Z INFO tor_circmgr::mgr: torfast circuit selection build complete pending_id=0x1 pending_age_ms=540 build_origin=bad_health_replacement pending_request_matches=0 tunnel_unique_id=Circ 1.6",
                                    ],
                                },
                                {
                                    "run_index": 2,
                                    "ok": True,
                                    "load_ms": 1300,
                                    "proxy_signal_lines": [
                                        "2026-06-06T23:12:50Z INFO tor_circmgr::mgr: tunnel_unique_id=Circ 1.6 replacement_built_age_ms=8000 support_reason=isolation exit_isolation_bucket=exit_incompatible_isolated selected_tunnel_unique_id=Circ~1.5 replacement_assigned_streams=0 replacement_health_score_bps=0 replacement_health_max_gap_ms=0 replacement_active_streams=0 usage_kind=exit torfast circuit selection bad health replacement later selection filtered",
                                    ],
                                },
                            ]
                        }
                    }
                }
            }
        }

        rows = torfast_bad_health_replacement_lifecycle_rows(payload)

        self.assertEqual(len(rows), 1)
        self.assertEqual(
            rows[0]["first_later_selection_event"],
            "bad_health_replacement_later_selection_filtered",
        )
        self.assertEqual(rows[0]["first_later_selection_support_reason"], "isolation")
        self.assertEqual(
            rows[0]["first_later_selection_exit_isolation_bucket"],
            "exit_incompatible_isolated",
        )
        self.assertEqual(
            bad_health_replacement_later_proof_label(rows[0]), "filtered:isolation"
        )
        self.assertEqual(
            bad_health_replacement_nonuse_reason(rows[0]), "filtered by isolation"
        )

    def test_bad_health_replacement_nonuse_reason_names_late_no_new_streams(
        self,
    ) -> None:
        row = {
            "outcome": "built",
            "used_by_streams": False,
            "open_count_after_build": 7,
            "build_pending_request_matches": 0,
            "stream_links_started_before_build": 8,
            "stream_links_started_after_build": 0,
            "built_circuit_candidate_open_count_after_build": 0,
        }

        self.assertEqual(
            bad_health_replacement_nonuse_reason(row),
            "replacement missed active streams; no new stream starts after build",
        )

    def test_summarizes_load_aware_selection_health_outcome(self) -> None:
        base = int(parse_log_timestamp_ms("2026-06-06T23:12:37Z x") or 0)
        payload = {
            "profiles": {
                "arti_release_browser_loadaware": {
                    "proxy_output_tail": [
                        f"timing_id=1 target_kind=hostname port=443 conn_started_epoch_ms={base + 100} circ_id=Circ 0.1 hop=3 stream_id=10 elapsed_ms=20 torfast socks timing stream linked",
                        f"timing_id=1 target_kind=hostname port=443 conn_started_epoch_ms={base + 100} relay_ms=900 tor_to_client_bytes=100000 first_tor_to_client_ms=80 first_tor_to_client_epoch_ms={base + 180} elapsed_ms=920 ok=true torfast socks timing relay finished",
                        f"event_epoch_ms={base + 200} circ_id=Circ 0.1 (Tunnel 1) hop=Some(HopNum(3)) stream_id=10 relay_cmd=RelayCmd(DATA) data_len=50000 queued_before_bytes=0 queued_after_bytes=50000 closes_stream=false torfast relay receive delivered",
                        f"event_epoch_ms={base + 300} circ_id=Circ 0.1 (Tunnel 1) hop=Some(HopNum(3)) stream_id=10 relay_cmd=RelayCmd(DATA) data_len=50000 queued_before_bytes=50000 queued_after_bytes=100000 closes_stream=false torfast relay receive delivered",
                        f"timing_id=2 target_kind=hostname port=443 conn_started_epoch_ms={base + 110} circ_id=Circ 0.2 hop=3 stream_id=11 elapsed_ms=20 torfast socks timing stream linked",
                        f"timing_id=2 target_kind=hostname port=443 conn_started_epoch_ms={base + 110} relay_ms=5000 tor_to_client_bytes=1000 first_tor_to_client_ms=500 first_tor_to_client_epoch_ms={base + 610} elapsed_ms=5020 ok=true torfast socks timing relay finished",
                        f"event_epoch_ms={base + 200} circ_id=Circ 0.2 (Tunnel 2) hop=Some(HopNum(3)) stream_id=11 relay_cmd=RelayCmd(DATA) data_len=500 queued_before_bytes=0 queued_after_bytes=500 closes_stream=false torfast relay receive delivered",
                        f"event_epoch_ms={base + 2200} circ_id=Circ 0.2 (Tunnel 2) hop=Some(HopNum(3)) stream_id=11 relay_cmd=RelayCmd(DATA) data_len=500 queued_before_bytes=500 queued_after_bytes=1000 closes_stream=false torfast relay receive delivered",
                    ],
                    "benchmarks": {
                        "https://example.com/": {
                            "runs": [
                                {
                                    "run_index": 1,
                                    "load_ms": 3000,
                                    "proxy_signal_lines": [
                                        "2026-06-06T23:12:37Z DEBUG tor_circmgr::mgr: open_candidates=2 select_parallelism=1 select_load_aware=true load_aware_assignment_spread=4 load_aware_min_assignment_spread=0 selected_candidate_index=1 candidate_assignment_summary=0:Circ~0.1:4,1:Circ~0.2:0 candidate_health_summary=0:Circ~0.1:4:100000:100:200000:200:20:1:4:80,1:Circ~0.2:1:1000:2000:1000:2200:30:1:4:900 selected_assigned_streams=0 selected_active_stream_age_ms=900 usage_kind=\"exit\" restrict_circ=true tunnel_unique_id=Circ 0.2 torfast circuit selection open",
                                    ],
                                    "performance_timing": {
                                        "time_origin_ms": base,
                                        "navigation": {"loadEventEnd": 3000},
                                    },
                                }
                            ]
                        }
                    },
                }
            }
        }

        rows = torfast_load_aware_selection_health_outcome_rows(payload)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["load_aware_picks"], 1)
        self.assertEqual(rows[0]["selected_nonfirst"], 1)
        self.assertEqual(rows[0]["known_selected_health"], 1)
        self.assertEqual(rows[0]["known_first_health"], 1)
        self.assertEqual(rows[0]["selected_worse_than_first_rate"], 1)
        self.assertEqual(rows[0]["selected_better_than_first_rate"], 0)
        self.assertEqual(rows[0]["selected_low_rate"], 1)
        self.assertEqual(rows[0]["selected_slow_relay"], 1)
        self.assertEqual(rows[0]["max_selected_active_stream_age_ms"], 900)
        self.assertEqual(rows[0]["max_first_active_stream_age_ms"], 80)
        self.assertEqual(rows[0]["worst_selected_circ_id"], "Circ 0.2 (Tunnel 2)")

    def test_parses_torfast_socks_timings(self) -> None:
        timings = parse_torfast_socks_timings(
            [
                'DEBUG arti::proxy::socks: timing_id=7 target_kind="onion" command=CONNECT port=443 elapsed_ms=2 torfast socks timing request parsed',
                'DEBUG arti::proxy::socks: timing_id=7 target_kind="onion" target_label=cflareusni3s7vwh...qd.onion port=443 connect_ms=120 elapsed_ms=122 torfast socks timing stream ready',
                "DEBUG arti::proxy::socks: timing_id=7 target_kind=onion port=443 circ_id=Circ 0.4 hop=3 stream_id=11302 elapsed_ms=122 torfast socks timing stream linked",
                "DEBUG arti::proxy::socks: timing_id=8 port=443 connect_ms=1500 elapsed_ms=1500 torfast socks timing stream ready",
                "DEBUG arti::proxy::socks: timing_id=9 port=443 attempt=1 soft_timeout_ms=5000 attempt_ms=5001 elapsed_ms=5001 torfast socks timing connect soft timeout",
                "DEBUG arti::proxy::socks: timing_id=9 port=443 attempt=1 error_kind=TorNetworkTimeout attempt_ms=60000 elapsed_ms=60000 torfast socks timing connect retry",
                "DEBUG arti::proxy::socks: timing_id=9 port=443 attempt=2 attempt_ms=300 connect_ms=60300 elapsed_ms=60300 torfast socks timing connect retry succeeded",
                "DEBUG arti::proxy::socks: timing_id=7 port=443 elapsed_ms=123 torfast socks timing socks reply sent",
                "DEBUG arti::proxy::socks: timing_id=7 port=443 partial_relay_idle_timeout_ms=4000 idle_after_last_tor_byte_ms=4001 tor_to_client_bytes=3400 elapsed_ms=4701 torfast socks timing partial relay idle timeout",
                "DEBUG arti::proxy::socks: timing_id=8 port=443 no_tor_byte_relay_timeout_ms=5000 first_client_to_tor_ms=120 idle_after_first_client_to_tor_ms=5001 client_to_tor_eof_ms=0 client_to_tor_error_ms=0 tor_to_client_write_error_ms=0 tor_to_client_write_close_error_ms=0 client_to_tor_bytes=7900 tor_to_client_write_bytes=0 elapsed_ms=5121 torfast socks timing no tor byte relay timeout",
                "DEBUG arti::proxy::socks: timing_id=7 port=443 first_client_to_tor_ms=130 last_client_to_tor_ms=180 client_to_tor_eof_ms=810 first_client_to_tor_write_ms=131 client_to_tor_write_close_ms=812 first_tor_to_client_ms=220 last_tor_to_client_ms=700 tor_to_client_error_ms=814 first_tor_to_client_write_ms=245 first_tor_to_client_write_epoch_ms=1245 last_tor_to_client_write_ms=710 relay_ms=800 tor_to_client_write_bytes=3400 elapsed_ms=923 ok=true torfast socks timing relay finished",
            ]
        )

        self.assertEqual(len(timings), 11)
        self.assertEqual(timings[0]["event"], "request_parsed")
        self.assertEqual(timings[0]["target_kind"], "onion")
        self.assertEqual(timings[1]["target_label"], "cflareusni3s7vwh...qd.onion")
        self.assertEqual(timings[1]["connect_ms"], 120)
        self.assertEqual(timings[2]["event"], "stream_linked")
        self.assertEqual(timings[2]["circ_id"], "Circ 0.4")
        self.assertEqual(timings[2]["stream_id"], 11302)
        self.assertEqual(timings[4]["event"], "connect_soft_timeout")
        self.assertEqual(timings[4]["soft_timeout_ms"], 5000)
        self.assertEqual(timings[5]["event"], "connect_retry")
        self.assertEqual(timings[5]["error_kind"], "TorNetworkTimeout")
        self.assertEqual(timings[6]["event"], "connect_retry_succeeded")
        self.assertEqual(timings[8]["event"], "partial_relay_idle_timeout")
        self.assertEqual(timings[8]["partial_relay_idle_timeout_ms"], 4000)
        self.assertEqual(timings[9]["event"], "no_tor_byte_relay_timeout")
        self.assertEqual(timings[9]["no_tor_byte_relay_timeout_ms"], 5000)
        self.assertEqual(timings[9]["client_to_tor_eof_ms"], 0)
        self.assertEqual(timings[9]["tor_to_client_write_bytes"], 0)
        self.assertEqual(event_median(timings, "stream_ready", "connect_ms"), 810.0)
        self.assertEqual(event_max(timings, "stream_ready", "connect_ms"), 1500.0)
        self.assertEqual(
            count_event_at_least(timings, "stream_ready", "connect_ms", 1000), 1
        )
        self.assertEqual(event_median(timings, "relay_finished", "relay_ms"), 800.0)
        self.assertEqual(
            event_median(timings, "relay_finished", "first_tor_to_client_ms"),
            220.0,
        )
        self.assertEqual(
            event_median(timings, "relay_finished", "first_tor_to_client_write_ms"),
            245.0,
        )
        self.assertEqual(timings[-1]["last_tor_to_client_ms"], 700)
        self.assertEqual(timings[-1]["client_to_tor_eof_ms"], 810)
        self.assertEqual(timings[-1]["client_to_tor_write_close_ms"], 812)
        self.assertEqual(timings[-1]["tor_to_client_error_ms"], 814)
        self.assertEqual(timings[-1]["last_tor_to_client_write_ms"], 710)
        self.assertEqual(timings[-1]["tor_to_client_write_bytes"], 3400)
        self.assertEqual(socks_first_byte_after_reply_median(timings), 97.0)

    def test_groups_socks_timings_by_target_kind(self) -> None:
        timings = parse_torfast_socks_timings(
            [
                'timing_id=1 target_kind="hostname" elapsed_ms=0 torfast socks timing request parsed',
                'timing_id=1 target_kind="hostname" connect_ms=0 elapsed_ms=0 torfast socks timing stream ready',
                'timing_id=1 target_kind="hostname" elapsed_ms=1 torfast socks timing socks reply sent',
                'timing_id=1 target_kind="hostname" first_tor_to_client_ms=11 tor_to_client_bytes=100 elapsed_ms=20 torfast socks timing relay finished',
                'timing_id=2 target_kind="onion" elapsed_ms=0 torfast socks timing request parsed',
                'timing_id=2 target_kind="onion" connect_ms=2500 elapsed_ms=2500 torfast socks timing stream ready',
                'timing_id=2 target_kind="onion" elapsed_ms=2 torfast socks timing socks reply sent',
                'timing_id=2 target_kind="onion" first_tor_to_client_ms=22 tor_to_client_bytes=200 elapsed_ms=30 torfast socks timing relay finished',
            ]
        )

        grouped = socks_rows_by_target_kind(timings)

        self.assertEqual(len(grouped["hostname"]), 1)
        self.assertEqual(grouped["hostname"][0]["first_tor_to_client_ms"], 11)
        self.assertEqual(row_max(grouped["hostname"], "connect_ms"), 0)
        self.assertEqual(row_count_at_least(grouped["hostname"], "connect_ms", 1000), 0)
        self.assertEqual(len(grouped["onion"]), 1)
        self.assertEqual(row_max(grouped["onion"], "connect_ms"), 2500)
        self.assertEqual(row_count_at_least(grouped["onion"], "connect_ms", 1000), 1)

    def test_summarizes_socks_byte_events(self) -> None:
        events = parse_torfast_socks_byte_events(
            [
                "2026-06-06T23:12:37Z DEBUG arti::proxy::socks: timing_id=1 target_kind=hostname direction=tor_to_client event_index=1 elapsed_ms=100 read_bytes=50 cumulative_bytes=50 torfast socks byte event",
                "2026-06-06T23:12:38Z DEBUG arti::proxy::socks: timing_id=1 target_kind=hostname direction=tor_to_client event_index=2 elapsed_ms=350 read_bytes=100 cumulative_bytes=150 torfast socks byte event",
                "2026-06-06T23:12:39Z DEBUG arti::proxy::socks: timing_id=1 target_kind=hostname direction=client_to_tor event_index=1 elapsed_ms=20 read_bytes=200 cumulative_bytes=200 torfast socks byte event",
                "2026-06-06T23:12:40Z DEBUG arti::proxy::socks: timing_id=1 target_kind=hostname direction=tor_to_client_write event_index=1 elapsed_ms=120 write_bytes=50 cumulative_bytes=50 torfast socks byte event",
            ]
        )

        rows = socks_byte_event_rows(events)

        self.assertEqual(len(rows), 3)
        tor_row = next(row for row in rows if row["direction"] == "tor_to_client")
        self.assertEqual(tor_row["events_shown"], 2)
        self.assertEqual(tor_row["first_elapsed_ms"], 100.0)
        self.assertEqual(tor_row["second_elapsed_ms"], 350.0)
        self.assertEqual(tor_row["max_gap_ms"], 250.0)
        self.assertEqual(tor_row["last_cumulative_bytes"], 150.0)
        write_row = next(
            row for row in rows if row["direction"] == "tor_to_client_write"
        )
        self.assertEqual(write_row["first_elapsed_ms"], 120.0)
        self.assertEqual(write_row["last_cumulative_bytes"], 50.0)

    def test_summarizes_neutral_byte_tap_rows(self) -> None:
        profile = {
            "byte_tap": {
                "connections": [
                    {
                        "connection_id": 1,
                        "first_stream_data_to_browser_epoch_ms": 1000.0,
                        "first_stream_data_to_browser_ms": 50.0,
                        "first_browser_to_proxy_epoch_ms": 900.0,
                        "proxy_to_browser_stream_data_bytes": 150,
                    }
                ],
                "events": [
                    {
                        "connection_id": 1,
                        "direction": "proxy_to_browser",
                        "elapsed_ms": 50.0,
                        "event_epoch_ms": 1000.0,
                        "stream_data_bytes": 50,
                    },
                    {
                        "connection_id": 1,
                        "direction": "proxy_to_browser",
                        "elapsed_ms": 80.0,
                        "event_epoch_ms": 1030.0,
                        "stream_data_bytes": 100,
                    },
                ],
            }
        }

        rows = byte_tap_connection_rows(profile)

        self.assertEqual(rows[0]["shown_proxy_stream_data_events"], 2)
        self.assertEqual(rows[0]["max_proxy_stream_data_gap_ms"], 30.0)
        self.assertEqual(rows[0]["proxy_stream_data_event_span_ms"], 30.0)
        self.assertEqual(rows[0]["last_proxy_stream_data_event_epoch_ms"], 1030.0)
        self.assertEqual(byte_tap_stream_data_epochs(profile), [1000.0])

    def test_summarizes_byte_tap_connections_by_browser_run(self) -> None:
        payload = {
            "profiles": {
                "arti_release_browser": {
                    "byte_tap": {
                        "connections": [
                            {
                                "connection_id": 1,
                                "first_browser_to_proxy_epoch_ms": 900.0,
                                "first_stream_data_to_browser_epoch_ms": 980.0,
                                "proxy_to_browser_stream_data_bytes": 100,
                            },
                            {
                                "connection_id": 2,
                                "first_browser_to_proxy_epoch_ms": 2100.0,
                                "first_stream_data_to_browser_epoch_ms": 2200.0,
                                "proxy_to_browser_stream_data_bytes": 200,
                            },
                        ],
                        "events": [
                            {
                                "connection_id": 1,
                                "direction": "proxy_to_browser",
                                "elapsed_ms": 80.0,
                                "event_epoch_ms": 980.0,
                                "stream_data_bytes": 100,
                            },
                            {
                                "connection_id": 2,
                                "direction": "proxy_to_browser",
                                "elapsed_ms": 100.0,
                                "event_epoch_ms": 2200.0,
                                "stream_data_bytes": 100,
                            },
                            {
                                "connection_id": 2,
                                "direction": "proxy_to_browser",
                                "elapsed_ms": 250.0,
                                "event_epoch_ms": 2350.0,
                                "stream_data_bytes": 100,
                            },
                        ],
                    },
                    "benchmarks": {
                        "https://example.com/": {
                            "runs": [
                                {
                                    "run_index": 1,
                                    "load_ms": 500,
                                    "performance_timing": {
                                        "time_origin_ms": 1000.0,
                                        "navigation": {
                                            "responseStart": 100.0,
                                            "loadEventEnd": 500.0,
                                        },
                                    },
                                },
                                {
                                    "run_index": 2,
                                    "load_ms": 600,
                                    "performance_timing": {
                                        "time_origin_ms": 2000.0,
                                        "navigation": {
                                            "responseStart": 150.0,
                                            "loadEventEnd": 600.0,
                                        },
                                    },
                                },
                            ]
                        }
                    },
                }
            }
        }

        rows = byte_tap_run_summary_rows(payload)

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["run_index"], 1)
        self.assertEqual(rows[0]["connection_count"], 1)
        self.assertEqual(rows[0]["data_connection_count"], 1)
        self.assertEqual(rows[0]["first_stream_data_after_start_ms"], -20.0)
        self.assertEqual(rows[0]["first_stream_data_minus_response_ms"], -120.0)
        self.assertEqual(rows[0]["stream_data_bytes"], 100.0)
        self.assertEqual(rows[1]["run_index"], 2)
        self.assertEqual(rows[1]["connection_count"], 1)
        self.assertEqual(rows[1]["stream_data_span_ms"], 150.0)
        self.assertEqual(rows[1]["last_stream_data_before_load_ms"], 250.0)
        self.assertEqual(rows[1]["max_proxy_stream_data_gap_ms"], 150.0)

    def test_maps_browser_resource_to_nearest_byte_tap_connection(self) -> None:
        payload = {
            "profiles": {
                "arti_release_browser": {
                    "byte_tap": {
                        "connections": [
                            {
                                "connection_id": 1,
                                "first_browser_to_proxy_epoch_ms": 1120.0,
                                "first_stream_data_to_browser_epoch_ms": 1300.0,
                                "proxy_to_browser_stream_data_bytes": 4096,
                            }
                        ],
                        "events": [
                            {
                                "connection_id": 1,
                                "direction": "proxy_to_browser",
                                "elapsed_ms": 180.0,
                                "event_epoch_ms": 1300.0,
                                "stream_data_bytes": 2048,
                            },
                            {
                                "connection_id": 1,
                                "direction": "proxy_to_browser",
                                "elapsed_ms": 280.0,
                                "event_epoch_ms": 1400.0,
                                "stream_data_bytes": 2048,
                            },
                        ],
                    },
                    "benchmarks": {
                        "https://example.com/": {
                            "runs": [
                                {
                                    "run_index": 1,
                                    "ok": True,
                                    "performance_timing": {
                                        "time_origin_ms": 1000.0,
                                        "navigation": {
                                            "responseStart": 100.0,
                                            "loadEventEnd": 700.0,
                                        },
                                        "resources": [
                                            {
                                                "name": "https://example.com/app.css",
                                                "initiatorType": "link",
                                                "nextHopProtocol": "http/1.1",
                                                "connectStart": 100.0,
                                                "fetchStart": 100.0,
                                                "requestStart": 200.0,
                                                "responseStart": 300.0,
                                                "responseEnd": 500.0,
                                                "duration": 400.0,
                                            }
                                        ],
                                    },
                                }
                            ]
                        }
                    },
                }
            }
        }

        rows = browser_resource_byte_tap_join_rows(payload)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["resource"], "https://example.com/app.css")
        self.assertEqual(rows[0]["match_field"], "connectStart")
        self.assertEqual(rows[0]["match_delta_ms"], 20.0)
        self.assertEqual(rows[0]["match_confidence"], "high")
        self.assertEqual(rows[0]["connection_id"], 1)
        self.assertEqual(rows[0]["fetch_to_request_ms"], 100.0)
        self.assertEqual(rows[0]["wait_ms"], 100.0)
        self.assertEqual(rows[0]["receive_ms"], 200.0)
        self.assertEqual(rows[0]["first_data_minus_resource_ms"], 200.0)
        self.assertEqual(rows[0]["last_data_before_response_end_ms"], 100.0)
        self.assertEqual(rows[0]["stream_data_bytes"], 4096)
        self.assertEqual(rows[0]["max_proxy_stream_data_gap_ms"], 100.0)

    def test_groups_slow_browser_resources_by_byte_tap_connection(self) -> None:
        payload = {
            "profiles": {
                "arti_release_browser": {
                    "proxy_output_tail": [
                        "timing_id=7 target_kind=hostname port=443 conn_started_epoch_ms=1120 circ_id=Circ 0.4 hop=3 stream_id=11302 elapsed_ms=20 torfast socks timing stream linked",
                        "timing_id=7 target_kind=hostname port=443 conn_started_epoch_ms=1120 relay_ms=900 first_tor_to_client_ms=180 first_tor_to_client_epoch_ms=1300 first_tor_to_client_write_ms=260 first_tor_to_client_write_epoch_ms=1380 tor_to_client_bytes=4096 tor_to_client_write_bytes=4096 elapsed_ms=920 ok=true torfast socks timing relay finished",
                        "event_epoch_ms=1300 circ_id=Circ 0.4 (Tunnel 15) hop=Some(HopNum(3)) stream_id=11302 relay_cmd=RelayCmd(DATA) data_len=2048 queued_before_bytes=0 queued_after_bytes=2048 closes_stream=false torfast relay receive delivered",
                        "event_epoch_ms=1450 circ_id=Circ 0.4 (Tunnel 15) hop=Some(HopNum(3)) stream_id=11302 relay_cmd=RelayCmd(DATA) data_len=2048 queued_before_bytes=2048 queued_after_bytes=4096 closes_stream=false torfast relay receive delivered",
                    ],
                    "byte_tap": {
                        "connections": [
                            {
                                "connection_id": 1,
                                "first_browser_to_proxy_epoch_ms": 1120.0,
                                "first_stream_data_to_browser_epoch_ms": 1300.0,
                                "proxy_to_browser_stream_data_bytes": 4096,
                            },
                            {
                                "connection_id": 2,
                                "first_browser_to_proxy_epoch_ms": 1500.0,
                                "first_stream_data_to_browser_epoch_ms": 1600.0,
                                "proxy_to_browser_stream_data_bytes": 2048,
                            },
                        ],
                        "events": [
                            {
                                "connection_id": 1,
                                "direction": "proxy_to_browser",
                                "elapsed_ms": 180.0,
                                "event_epoch_ms": 1300.0,
                                "stream_data_bytes": 2048,
                            },
                            {
                                "connection_id": 1,
                                "direction": "proxy_to_browser",
                                "elapsed_ms": 330.0,
                                "event_epoch_ms": 1450.0,
                                "stream_data_bytes": 2048,
                            },
                            {
                                "connection_id": 2,
                                "direction": "proxy_to_browser",
                                "elapsed_ms": 100.0,
                                "event_epoch_ms": 1600.0,
                                "stream_data_bytes": 2048,
                            },
                        ],
                    },
                    "benchmarks": {
                        "https://example.com/": {
                            "runs": [
                                {
                                    "run_index": 1,
                                    "ok": True,
                                    "performance_timing": {
                                        "time_origin_ms": 1000.0,
                                        "navigation": {
                                            "responseStart": 100.0,
                                            "loadEventEnd": 5000.0,
                                        },
                                        "resources": [
                                            {
                                                "name": "https://example.com/app.css",
                                                "initiatorType": "link",
                                                "nextHopProtocol": "http/1.1",
                                                "connectStart": 120.0,
                                                "fetchStart": 120.0,
                                                "requestStart": 220.0,
                                                "responseStart": 420.0,
                                                "responseEnd": 3120.0,
                                                "duration": 3000.0,
                                            },
                                            {
                                                "name": "https://example.com/hero.png",
                                                "initiatorType": "img",
                                                "nextHopProtocol": "http/1.1",
                                                "connectStart": 130.0,
                                                "fetchStart": 130.0,
                                                "requestStart": 230.0,
                                                "responseStart": 430.0,
                                                "responseEnd": 2630.0,
                                                "duration": 2500.0,
                                            },
                                            {
                                                "name": "https://example.com/icon.png",
                                                "initiatorType": "img",
                                                "nextHopProtocol": "http/1.1",
                                                "connectStart": 125.0,
                                                "fetchStart": 125.0,
                                                "requestStart": 175.0,
                                                "responseStart": 275.0,
                                                "responseEnd": 625.0,
                                                "duration": 500.0,
                                            },
                                            {
                                                "name": "https://example.com/app.js",
                                                "initiatorType": "script",
                                                "nextHopProtocol": "http/1.1",
                                                "connectStart": 500.0,
                                                "fetchStart": 500.0,
                                                "requestStart": 550.0,
                                                "responseStart": 650.0,
                                                "responseEnd": 2850.0,
                                                "duration": 2350.0,
                                            },
                                        ],
                                    },
                                }
                            ]
                        }
                    },
                }
            }
        }

        rows = browser_resource_byte_tap_group_rows(payload)

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["connection_id"], 1)
        self.assertEqual(rows[0]["resources"], 3)
        self.assertEqual(rows[0]["high_confidence"], 3)
        self.assertEqual(rows[0]["slow_resources_2s"], 2)
        self.assertEqual(rows[0]["slow_high_confidence"], 2)
        self.assertEqual(rows[0]["median_slow_duration_ms"], 2750.0)
        self.assertEqual(rows[0]["median_slow_fetch_to_request_ms"], 100.0)
        self.assertEqual(rows[0]["median_slow_wait_ms"], 200.0)
        self.assertEqual(rows[0]["stream_data_bytes"], 4096)
        self.assertEqual(rows[0]["max_proxy_stream_data_gap_ms"], 150.0)
        self.assertIn("app.css", rows[0]["top_slow_resources"])
        self.assertEqual(rows[1]["connection_id"], 2)
        self.assertEqual(rows[1]["slow_resources_2s"], 1)

        relay_rows = browser_resource_byte_tap_relay_group_rows(payload)

        self.assertEqual(relay_rows[0]["connection_id"], 1)
        self.assertEqual(relay_rows[0]["slow_resources_2s"], 2)
        self.assertEqual(relay_rows[0]["relay_matched_resources"], 2)
        self.assertEqual(relay_rows[0]["median_write_lag_ms"], 80.0)
        self.assertEqual(relay_rows[0]["max_write_lag_ms"], 80.0)
        self.assertEqual(relay_rows[0]["max_tor_to_client_write_bytes"], 4096)

    def test_parses_log_timestamp_ms(self) -> None:
        self.assertEqual(
            parse_log_timestamp_ms("2026-06-06T23:12:37Z DEBUG message"),
            1780787557000,
        )
        self.assertIsNone(parse_log_timestamp_ms("DEBUG message"))

    def test_groups_torfast_socks_timings_by_timing_id(self) -> None:
        timings = parse_torfast_socks_timings(
            [
                "timing_id=7 command=CONNECT port=443 elapsed_ms=2 torfast socks timing request parsed",
                "timing_id=7 port=443 connect_ms=120 elapsed_ms=122 torfast socks timing stream ready",
                "timing_id=7 port=443 circ_id=Circ 0.4 hop=3 stream_id=11302 elapsed_ms=122 torfast socks timing stream linked",
                "timing_id=7 port=443 elapsed_ms=123 torfast socks timing socks reply sent",
                "timing_id=7 port=443 relay_ms=800 first_client_to_tor_ms=130 last_client_to_tor_ms=190 client_to_tor_eof_ms=810 client_to_tor_error_ms=0 first_client_to_tor_write_ms=131 first_client_to_tor_write_epoch_ms=1131 last_client_to_tor_write_ms=191 client_to_tor_write_error_ms=0 client_to_tor_write_close_ms=812 client_to_tor_write_close_error_ms=0 first_tor_to_client_ms=220 first_tor_to_client_epoch_ms=1220 last_tor_to_client_ms=700 tor_to_client_eof_ms=0 tor_to_client_error_ms=814 first_tor_to_client_write_ms=245 first_tor_to_client_write_epoch_ms=1245 last_tor_to_client_write_ms=710 tor_to_client_write_error_ms=0 tor_to_client_write_close_ms=0 tor_to_client_write_close_error_ms=0 client_to_tor_bytes=1200 client_to_tor_write_bytes=1200 tor_to_client_bytes=3400 tor_to_client_write_bytes=3400 elapsed_ms=923 ok=true torfast socks timing relay finished",
                "timing_id=8 command=CONNECT port=443 elapsed_ms=1 torfast socks timing request parsed",
                "timing_id=8 port=443 connect_ms=5000 elapsed_ms=5001 torfast socks timing stream ready",
                "timing_id=9 command=CONNECT port=443 elapsed_ms=1 torfast socks timing request parsed",
                "timing_id=9 port=443 attempt=1 soft_timeout_attempts=3 soft_timeout_ms=5000 attempt_ms=5001 elapsed_ms=5001 torfast socks timing connect soft timeout",
                "timing_id=9 port=443 attempt=1 soft_timeout_attempts=3 error_kind=TorNetworkTimeout attempt_ms=60000 elapsed_ms=60000 torfast socks timing connect retry",
                "timing_id=9 port=443 attempt=2 soft_timeout_attempts=3 attempt_ms=300 connect_ms=60300 elapsed_ms=60300 torfast socks timing connect retry succeeded",
            ]
        )

        grouped = group_torfast_socks_timings(timings)

        self.assertEqual(grouped[7]["command"], "CONNECT")
        self.assertEqual(grouped[7]["connect_ms"], 120)
        self.assertEqual(grouped[7]["relay_ms"], 800)
        self.assertEqual(grouped[7]["first_client_to_tor_ms"], 130)
        self.assertEqual(grouped[7]["last_client_to_tor_ms"], 190)
        self.assertEqual(grouped[7]["client_to_tor_eof_ms"], 810)
        self.assertEqual(grouped[7]["client_to_tor_error_ms"], 0)
        self.assertEqual(grouped[7]["first_client_to_tor_write_ms"], 131)
        self.assertEqual(grouped[7]["first_client_to_tor_write_epoch_ms"], 1131)
        self.assertEqual(grouped[7]["last_client_to_tor_write_ms"], 191)
        self.assertEqual(grouped[7]["client_to_tor_write_error_ms"], 0)
        self.assertEqual(grouped[7]["client_to_tor_write_close_ms"], 812)
        self.assertEqual(grouped[7]["client_to_tor_write_close_error_ms"], 0)
        self.assertEqual(grouped[7]["first_tor_to_client_ms"], 220)
        self.assertEqual(grouped[7]["first_tor_to_client_epoch_ms"], 1220)
        self.assertEqual(grouped[7]["last_tor_to_client_ms"], 700)
        self.assertEqual(grouped[7]["tor_to_client_eof_ms"], 0)
        self.assertEqual(grouped[7]["tor_to_client_error_ms"], 814)
        self.assertEqual(grouped[7]["client_eof_to_tor_error_ms"], 4)
        self.assertEqual(grouped[7]["client_eof_to_tor_writer_close_ms"], 2)
        self.assertEqual(grouped[7]["last_tor_byte_to_client_eof_ms"], 110)
        self.assertEqual(grouped[7]["last_tor_byte_to_tor_error_ms"], 114)
        self.assertEqual(grouped[7]["tor_to_client_idle_after_last_ms"], 223)
        self.assertEqual(grouped[7]["first_tor_to_client_write_ms"], 245)
        self.assertEqual(grouped[7]["first_tor_to_client_write_epoch_ms"], 1245)
        self.assertEqual(grouped[7]["last_tor_to_client_write_ms"], 710)
        self.assertEqual(grouped[7]["tor_to_client_write_error_ms"], 0)
        self.assertEqual(grouped[7]["tor_to_client_write_close_ms"], 0)
        self.assertEqual(grouped[7]["tor_to_client_write_close_error_ms"], 0)
        self.assertEqual(grouped[7]["client_to_tor_bytes"], 1200)
        self.assertEqual(grouped[7]["client_to_tor_write_bytes"], 1200)
        self.assertEqual(grouped[7]["tor_to_client_bytes"], 3400)
        self.assertEqual(grouped[7]["tor_to_client_write_bytes"], 3400)
        self.assertEqual(grouped[7]["circ_id"], "Circ 0.4")
        self.assertEqual(grouped[7]["hop"], 3)
        self.assertEqual(grouped[7]["stream_id"], 11302)
        self.assertEqual(grouped[7]["total_elapsed_ms"], 923)
        self.assertTrue(grouped[7]["ok"])
        self.assertEqual(grouped[8]["connect_ms"], 5000)
        self.assertEqual(grouped[9]["connect_soft_timeouts"], 1)
        self.assertEqual(grouped[9]["soft_timeout_attempts"], 3)
        self.assertEqual(grouped[9]["soft_timeout_ms"], 5000)
        self.assertEqual(
            grouped[9]["connect_attempt_trace"],
            [
                "1:soft_timeout:5001ms",
                "1:retry_TorNetworkTimeout:60000ms",
                "2:ok:300ms",
            ],
        )
        self.assertEqual(grouped[9]["last_soft_timeout_elapsed_ms"], 5001)
        self.assertEqual(grouped[9]["connect_retries"], 1)
        self.assertEqual(grouped[9]["error_kind"], "TorNetworkTimeout")
        self.assertEqual(grouped[9]["last_retry_elapsed_ms"], 60000)
        self.assertTrue(grouped[9]["connect_retry_succeeded"])
        self.assertEqual(grouped[9]["attempt"], 2)
        self.assertEqual(grouped[9]["attempt_ms"], 300)
        self.assertEqual(grouped[9]["connect_ms"], 60300)

        retry_rows = torfast_socks_connect_retry_rows(timings)
        self.assertEqual(len(retry_rows), 1)
        self.assertEqual(retry_rows[0]["timing_id"], 9)
        self.assertEqual(retry_rows[0]["connect_soft_timeouts"], 1)
        self.assertEqual(retry_rows[0]["soft_timeout_attempts"], 3)
        self.assertEqual(
            retry_rows[0]["connect_attempt_trace"],
            [
                "1:soft_timeout:5001ms",
                "1:retry_TorNetworkTimeout:60000ms",
                "2:ok:300ms",
            ],
        )
        self.assertEqual(retry_rows[0]["connect_retries"], 1)
        self.assertEqual(retry_rows[0]["error_kind"], "TorNetworkTimeout")
        self.assertTrue(retry_rows[0]["connect_retry_succeeded"])
        self.assertEqual(retry_rows[0]["connect_ms"], 60300)

    def test_groups_torfast_socks_connect_hedges(self) -> None:
        timings = parse_torfast_socks_timings(
            [
                "timing_id=11 target_kind=hostname port=443 attempt=2 backup_isolated=true hedge_after_ms=500 connect_ms=500 elapsed_ms=501 torfast socks timing connect hedge launched",
                "timing_id=11 target_kind=hostname port=443 winner_attempt=2 hedge_after_ms=500 hedge_wait_ms=220 connect_ms=721 elapsed_ms=722 torfast socks timing connect hedge succeeded",
                "timing_id=12 target_kind=hostname port=443 hedge_after_ms=500 connect_ms=500 elapsed_ms=501 torfast socks timing connect hedge skipped inflight",
                "timing_id=13 target_kind=hostname port=443 attempt=1 primary_error_kind=TorNetworkTimeout hedge_after_ms=500 attempt_ms=2 elapsed_ms=2 torfast socks timing connect hedge retry",
                "timing_id=13 target_kind=hostname port=443 attempt=2 hedge_after_ms=500 attempt_ms=80 connect_ms=82 elapsed_ms=82 torfast socks timing connect hedge retry succeeded",
            ]
        )

        rows = torfast_socks_connect_hedge_rows(timings)

        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["timing_id"], 11)
        self.assertEqual(rows[0]["connect_hedge_launched"], 1)
        self.assertEqual(rows[0]["connect_hedge_succeeded"], 1)
        self.assertEqual(rows[0]["winner_attempt"], 2)
        self.assertEqual(rows[0]["hedge_after_ms"], 500)
        self.assertEqual(rows[0]["hedge_wait_ms"], 220)
        self.assertEqual(rows[0]["connect_ms"], 721)
        self.assertEqual(rows[0]["total_elapsed_ms"], 722)
        self.assertEqual(rows[1]["connect_hedge_skipped_inflight"], 1)
        self.assertEqual(rows[2]["connect_hedge_retries"], 1)
        self.assertEqual(rows[2]["connect_hedge_retry_succeeded"], 1)
        self.assertEqual(rows[2]["primary_error_kind"], "TorNetworkTimeout")

    def test_summarizes_torfast_socks_close_shape(self) -> None:
        payload = {
            "profiles": {
                "arti_release_browser": {
                    "skipped": False,
                    "proxy_signal_lines": [
                        "timing_id=1 port=443 relay_ms=1001 last_tor_to_client_ms=900 client_to_tor_eof_ms=1000 client_to_tor_write_close_ms=1000 tor_to_client_error_ms=1001 copy_error_kind=not_connected torfast socks timing relay finished",
                        "timing_id=2 port=443 relay_ms=2000 last_tor_to_client_ms=1800 tor_to_client_eof_ms=2000 tor_to_client_write_close_ms=2000 copy_error_kind=connection_reset torfast socks timing relay finished",
                    ],
                }
            }
        }

        rows = torfast_socks_close_shape_summary_rows(payload)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["profile"], "arti_release_browser")
        self.assertEqual(rows[0]["streams"], 2)
        self.assertEqual(rows[0]["not_connected"], 1)
        self.assertEqual(rows[0]["client_eof_tor_error"], 1)
        self.assertEqual(rows[0]["same_close_not_connected"], 1)
        self.assertEqual(rows[0]["tor_eof"], 1)
        self.assertEqual(rows[0]["connection_reset"], 1)
        self.assertEqual(rows[0]["median_client_eof_to_tor_error_ms"], 1)
        self.assertEqual(rows[0]["median_last_tor_byte_to_client_eof_ms"], 100)
        self.assertEqual(rows[0]["max_last_tor_byte_to_client_eof_ms"], 100)

    def test_summarizes_torfast_socks_partial_idle_timeout_rows(self) -> None:
        payload = {
            "profiles": {
                "arti_release_browser_partialidle3000ms": {
                    "benchmarks": {
                        "https://www.torproject.org/download/": {
                            "runs": [
                                {
                                    "run_index": 2,
                                    "load_ms": 5023.955,
                                    "proxy_signal_lines": [
                                        "timing_id=11 target_kind=hostname port=443 partial_relay_idle_timeout_ms=3000 elapsed_ms=4289 last_tor_to_client_ms=1276 idle_after_last_tor_byte_ms=3013 client_to_tor_eof_ms=0 client_to_tor_error_ms=0 tor_to_client_write_error_ms=0 tor_to_client_write_close_ms=0 tor_to_client_write_close_error_ms=0 tor_to_client_bytes=7855 tor_to_client_write_bytes=7855 torfast socks timing partial relay idle timeout",
                                        "timing_id=11 target_kind=hostname port=443 relay_ms=4300 elapsed_ms=4301 client_to_tor_eof_ms=4300 tor_to_client_error_ms=4301 tor_to_client_bytes=7855 ok=false copy_error_kind=timed_out torfast socks timing relay finished",
                                    ],
                                }
                            ]
                        }
                    }
                }
            }
        }

        rows = torfast_socks_partial_idle_timeout_rows(payload)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["profile"], "arti_release_browser_partialidle3000ms")
        self.assertEqual(rows[0]["run_index"], 2)
        self.assertEqual(rows[0]["timing_id"], 11)
        self.assertEqual(rows[0]["partial_relay_idle_timeout_ms"], 3000)
        self.assertEqual(rows[0]["idle_after_last_tor_byte_ms"], 3013)
        self.assertFalse(rows[0]["client_abandon_at_timeout"])
        self.assertEqual(rows[0]["client_to_tor_eof_at_timeout_ms"], 0)
        self.assertEqual(rows[0]["tor_to_client_write_bytes_at_timeout"], 7855)
        self.assertEqual(rows[0]["relay_ms"], 4300)
        self.assertEqual(rows[0]["relay_after_timeout_ms"], 11)
        self.assertEqual(rows[0]["copy_error_kind"], "timed_out")

    def test_summarizes_torfast_socks_no_tor_byte_timeout_rows(self) -> None:
        payload = {
            "profiles": {
                "arti_release_browser_nobyte5000ms": {
                    "benchmarks": {
                        "https://www.torproject.org/download/": {
                            "runs": [
                                {
                                    "run_index": 2,
                                    "load_ms": 5023.955,
                                    "proxy_signal_lines": [
                                        "timing_id=12 target_kind=hostname port=443 no_tor_byte_relay_timeout_ms=5000 elapsed_ms=6121 first_client_to_tor_ms=120 idle_after_first_client_to_tor_ms=6001 client_to_tor_eof_ms=0 client_to_tor_error_ms=0 tor_to_client_write_error_ms=0 tor_to_client_write_close_error_ms=0 client_to_tor_bytes=7900 tor_to_client_write_bytes=0 torfast socks timing no tor byte relay timeout",
                                        "timing_id=12 target_kind=hostname port=443 relay_ms=6130 elapsed_ms=6131 client_to_tor_eof_ms=6130 tor_to_client_bytes=0 ok=false copy_error_kind=timed_out torfast socks timing relay finished",
                                    ],
                                }
                            ]
                        }
                    }
                }
            }
        }

        rows = torfast_socks_no_tor_byte_timeout_rows(payload)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["profile"], "arti_release_browser_nobyte5000ms")
        self.assertEqual(rows[0]["run_index"], 2)
        self.assertEqual(rows[0]["timing_id"], 12)
        self.assertEqual(rows[0]["no_tor_byte_relay_timeout_ms"], 5000)
        self.assertEqual(rows[0]["idle_after_first_client_to_tor_ms"], 6001)
        self.assertFalse(rows[0]["client_abandon_at_timeout"])
        self.assertEqual(rows[0]["client_to_tor_eof_at_timeout_ms"], 0)
        self.assertEqual(rows[0]["tor_to_client_write_bytes_at_timeout"], 0)
        self.assertEqual(rows[0]["relay_ms"], 6130)
        self.assertEqual(rows[0]["relay_after_timeout_ms"], 9)
        self.assertEqual(rows[0]["copy_error_kind"], "timed_out")

    def test_joins_partial_idle_timeout_to_nearest_resource_context(self) -> None:
        payload = {
            "profiles": {
                "arti_release_browser_partialidle3000ms": {
                    "benchmarks": {
                        "https://www.torproject.org/download/": {
                            "runs": [
                                {
                                    "ok": True,
                                    "run_index": 2,
                                    "load_ms": 5023.955,
                                    "performance_timing": {
                                        "time_origin_ms": 1000,
                                        "navigation": {"loadEventEnd": 5000},
                                        "resources": [
                                            {
                                                "name": "https://example.com/icon.png",
                                                "initiatorType": "img",
                                                "nextHopProtocol": "http/1.1",
                                                "fetchStart": 1200,
                                                "requestStart": 2000,
                                                "responseStart": 4200,
                                                "responseEnd": 4300,
                                                "duration": 3100,
                                                "encodedBodySize": 7539,
                                            }
                                        ],
                                    },
                                    "proxy_signal_lines": [
                                        "timing_id=11 target_kind=hostname port=443 conn_started_epoch_ms=1005 partial_relay_idle_timeout_ms=3000 elapsed_ms=4289 last_tor_to_client_ms=1276 idle_after_last_tor_byte_ms=3013 tor_to_client_bytes=7855 torfast socks timing partial relay idle timeout",
                                        "timing_id=11 target_kind=hostname port=443 conn_started_epoch_ms=1005 relay_ms=4288 elapsed_ms=4288 client_to_tor_eof_ms=0 tor_to_client_bytes=7855 ok=false copy_error_kind=timed_out torfast socks timing relay finished",
                                    ],
                                }
                            ]
                        }
                    }
                }
            }
        }

        rows = torfast_socks_partial_idle_resource_rows(payload)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["timing_id"], 11)
        self.assertEqual(rows[0]["timeout_after_start_ms"], 4294)
        self.assertEqual(rows[0]["load_after_timeout_ms"], 706)
        self.assertEqual(rows[0]["active_resources_at_timeout"], 1)
        self.assertEqual(rows[0]["receiving_resources_at_timeout"], 1)
        self.assertEqual(rows[0]["waiting_resources_at_timeout"], 0)
        self.assertEqual(rows[0]["max_active_end_after_timeout_ms"], 6)
        self.assertIn("icon.png", rows[0]["active_resource_samples"])
        self.assertIn("receiving", rows[0]["active_resource_samples"])
        self.assertEqual(rows[0]["exact_resource_matches"], 0)
        self.assertEqual(rows[0]["nearest_response_end_delta_ms"], 6)
        self.assertEqual(rows[0]["phase_at_timeout"], "receiving")
        self.assertEqual(rows[0]["nearest_resource_body_bytes"], 7539)

    def test_joins_no_tor_byte_timeout_to_nearest_resource_context(self) -> None:
        payload = {
            "profiles": {
                "arti_release_browser_nobyte5000ms": {
                    "benchmarks": {
                        "https://www.torproject.org/download/": {
                            "runs": [
                                {
                                    "ok": True,
                                    "run_index": 2,
                                    "load_ms": 5023.955,
                                    "performance_timing": {
                                        "time_origin_ms": 1000,
                                        "navigation": {"loadEventEnd": 5000},
                                        "resources": [
                                            {
                                                "name": "https://example.com/icon.png",
                                                "initiatorType": "img",
                                                "nextHopProtocol": "http/1.1",
                                                "fetchStart": 1200,
                                                "requestStart": 2000,
                                                "responseStart": 4200,
                                                "responseEnd": 4300,
                                                "duration": 3100,
                                                "encodedBodySize": 7539,
                                            }
                                        ],
                                    },
                                    "proxy_signal_lines": [
                                        "timing_id=12 target_kind=hostname port=443 conn_started_epoch_ms=1005 no_tor_byte_relay_timeout_ms=3000 elapsed_ms=3289 first_client_to_tor_ms=120 idle_after_first_client_to_tor_ms=3169 client_to_tor_bytes=7900 torfast socks timing no tor byte relay timeout",
                                        "timing_id=12 target_kind=hostname port=443 conn_started_epoch_ms=1005 relay_ms=3288 elapsed_ms=3288 client_to_tor_eof_ms=0 tor_to_client_bytes=0 ok=false copy_error_kind=timed_out torfast socks timing relay finished",
                                    ],
                                }
                            ]
                        }
                    }
                }
            }
        }

        rows = torfast_socks_no_tor_byte_resource_rows(payload)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["timing_id"], 12)
        self.assertEqual(rows[0]["timeout_after_start_ms"], 3294)
        self.assertEqual(rows[0]["load_after_timeout_ms"], 1706)
        self.assertEqual(rows[0]["active_resources_at_timeout"], 1)
        self.assertEqual(rows[0]["receiving_resources_at_timeout"], 0)
        self.assertEqual(rows[0]["waiting_resources_at_timeout"], 1)
        self.assertEqual(rows[0]["max_active_end_after_timeout_ms"], 1006)
        self.assertIn("icon.png", rows[0]["active_resource_samples"])
        self.assertIn("waiting", rows[0]["active_resource_samples"])
        self.assertEqual(rows[0]["exact_resource_matches"], 0)
        self.assertEqual(rows[0]["nearest_response_end_delta_ms"], 1006)
        self.assertEqual(rows[0]["phase_at_timeout"], "waiting")
        self.assertEqual(rows[0]["nearest_resource_body_bytes"], 7539)

    def test_partial_idle_active_resources_block_promotion(self) -> None:
        target = "https://www.torproject.org/download/"
        candidate_run = {
            "ok": True,
            "run_index": 1,
            "load_ms": 5000,
            "elapsed_ms": 5200,
            "performance_timing": {
                "time_origin_ms": 1000,
                "navigation": {"loadEventEnd": 5000},
                "resources": [
                    {
                        "name": "https://example.com/icon.png",
                        "initiatorType": "img",
                        "nextHopProtocol": "http/1.1",
                        "fetchStart": 1200,
                        "requestStart": 2000,
                        "responseStart": 4200,
                        "responseEnd": 4300,
                        "duration": 3100,
                        "encodedBodySize": 7539,
                    }
                ],
            },
            "proxy_signal_lines": [
                "timing_id=11 target_kind=hostname port=443 conn_started_epoch_ms=1005 partial_relay_idle_timeout_ms=3000 elapsed_ms=4289 last_tor_to_client_ms=1276 idle_after_last_tor_byte_ms=3013 client_to_tor_eof_ms=0 client_to_tor_error_ms=0 tor_to_client_write_error_ms=0 tor_to_client_write_close_error_ms=0 tor_to_client_bytes=7855 tor_to_client_write_bytes=7855 torfast socks timing partial relay idle timeout",
                "timing_id=11 target_kind=hostname port=443 conn_started_epoch_ms=1005 relay_ms=4288 elapsed_ms=4288 client_to_tor_eof_ms=0 tor_to_client_bytes=7855 ok=false copy_error_kind=timed_out torfast socks timing relay finished",
            ],
        }
        payload = {
            "targets": [target],
            "profiles": {
                "local_c_tor_browser": {
                    "benchmarks": {
                        target: {
                            "summary": {"ok": True, "median_load_ms": 5200},
                            "runs": [
                                {
                                    "ok": True,
                                    "run_index": 1,
                                    "load_ms": 5200,
                                    "elapsed_ms": 5400,
                                }
                            ],
                        }
                    }
                },
                "arti_release_browser": {
                    "benchmarks": {
                        target: {
                            "summary": {"ok": True, "median_load_ms": 6000},
                            "runs": [
                                {
                                    "ok": True,
                                    "run_index": 1,
                                    "load_ms": 6000,
                                    "elapsed_ms": 6200,
                                    "performance_timing": {
                                        "navigation": {"loadEventEnd": 6000}
                                    },
                                }
                            ],
                        }
                    }
                },
                "arti_release_browser_partialidle3000ms": {
                    "benchmarks": {
                        target: {
                            "summary": {"ok": True, "median_load_ms": 5000},
                            "runs": [candidate_run],
                        }
                    }
                },
            },
        }

        risk_rows = arti_profile_promotion_risk_rows(payload)

        self.assertEqual(len(risk_rows), 1)
        self.assertEqual(
            risk_rows[0]["candidate_profile"],
            "arti_release_browser_partialidle3000ms",
        )
        self.assertIn("partial idle active resources", risk_rows[0]["risk"])
        self.assertIn("partial idle no client abandon", risk_rows[0]["risk"])

        blocker_rows = promotion_blocker_summary_rows(payload)
        partial_row = next(
            row
            for row in blocker_rows
            if row["profile"] == "arti_release_browser_partialidle3000ms"
        )
        self.assertIn("partial idle active resources", partial_row["blockers"])
        self.assertIn("partial idle no client abandon", partial_row["blockers"])
        self.assertEqual(partial_row["partial_idle_active_closes"], 1)
        self.assertEqual(partial_row["partial_idle_no_client_abandon_closes"], 1)
        self.assertEqual(partial_row["max_partial_idle_active_resources"], 1)
        self.assertEqual(partial_row["next_proof"], "client-abandon proof")

    def test_no_tor_byte_active_resources_block_promotion(self) -> None:
        target = "https://www.torproject.org/download/"
        candidate_run = {
            "ok": True,
            "run_index": 1,
            "load_ms": 5000,
            "elapsed_ms": 5200,
            "performance_timing": {
                "time_origin_ms": 1000,
                "navigation": {"loadEventEnd": 5000},
                "resources": [
                    {
                        "name": "https://example.com/icon.png",
                        "initiatorType": "img",
                        "nextHopProtocol": "http/1.1",
                        "fetchStart": 1200,
                        "requestStart": 2000,
                        "responseStart": 4200,
                        "responseEnd": 4300,
                        "duration": 3100,
                        "encodedBodySize": 7539,
                    }
                ],
            },
            "proxy_signal_lines": [
                "timing_id=12 target_kind=hostname port=443 conn_started_epoch_ms=1005 no_tor_byte_relay_timeout_ms=3000 elapsed_ms=3289 first_client_to_tor_ms=120 idle_after_first_client_to_tor_ms=3169 client_to_tor_eof_ms=0 client_to_tor_error_ms=0 tor_to_client_write_error_ms=0 tor_to_client_write_close_error_ms=0 client_to_tor_bytes=7900 tor_to_client_write_bytes=0 torfast socks timing no tor byte relay timeout",
                "timing_id=12 target_kind=hostname port=443 conn_started_epoch_ms=1005 relay_ms=3288 elapsed_ms=3288 client_to_tor_eof_ms=0 tor_to_client_bytes=0 ok=false copy_error_kind=timed_out torfast socks timing relay finished",
            ],
        }
        payload = {
            "targets": [target],
            "profiles": {
                "local_c_tor_browser": {
                    "benchmarks": {
                        target: {
                            "summary": {"ok": True, "median_load_ms": 5200},
                            "runs": [
                                {
                                    "ok": True,
                                    "run_index": 1,
                                    "load_ms": 5200,
                                    "elapsed_ms": 5400,
                                }
                            ],
                        }
                    }
                },
                "arti_release_browser": {
                    "benchmarks": {
                        target: {
                            "summary": {"ok": True, "median_load_ms": 6000},
                            "runs": [
                                {
                                    "ok": True,
                                    "run_index": 1,
                                    "load_ms": 6000,
                                    "elapsed_ms": 6200,
                                    "performance_timing": {
                                        "navigation": {"loadEventEnd": 6000}
                                    },
                                }
                            ],
                        }
                    }
                },
                "arti_release_browser_nobyte3000ms": {
                    "benchmarks": {
                        target: {
                            "summary": {"ok": True, "median_load_ms": 5000},
                            "runs": [candidate_run],
                        }
                    }
                },
            },
        }

        risk_rows = arti_profile_promotion_risk_rows(payload)

        self.assertEqual(len(risk_rows), 1)
        self.assertEqual(
            risk_rows[0]["candidate_profile"],
            "arti_release_browser_nobyte3000ms",
        )
        self.assertIn("no-byte active resources", risk_rows[0]["risk"])
        self.assertIn("no-byte no client abandon", risk_rows[0]["risk"])

        blocker_rows = promotion_blocker_summary_rows(payload)
        no_byte_row = next(
            row
            for row in blocker_rows
            if row["profile"] == "arti_release_browser_nobyte3000ms"
        )
        self.assertIn("no-byte active resources", no_byte_row["blockers"])
        self.assertIn("no-byte no client abandon", no_byte_row["blockers"])
        self.assertEqual(no_byte_row["no_tor_byte_active_closes"], 1)
        self.assertEqual(no_byte_row["no_tor_byte_no_client_abandon_closes"], 1)
        self.assertEqual(no_byte_row["max_no_tor_byte_active_resources"], 1)
        self.assertEqual(no_byte_row["next_proof"], "client-abandon proof")

    def test_joins_torfast_socks_to_relay_receive_streams(self) -> None:
        rows = torfast_socks_relay_join_rows(
            [
                "timing_id=7 target_kind=hostname port=443 circ_id=Circ 0.4 hop=3 stream_id=11302 elapsed_ms=122 torfast socks timing stream linked",
                "timing_id=7 target_kind=hostname port=443 relay_ms=9000 first_tor_to_client_ms=200 first_tor_to_client_epoch_ms=1780787557000 first_tor_to_client_write_ms=260 first_tor_to_client_write_epoch_ms=1780787557060 tor_to_client_bytes=411460 tor_to_client_write_bytes=411460 elapsed_ms=9122 ok=true torfast socks timing relay finished",
                "2026-06-06T23:12:37Z DEBUG tor_proto::circuit::circhop: event_epoch_ms=1780787557000 circ_id=Circ 0.4 (Tunnel 15) hop=Some(HopNum(3)) stream_id=11302 relay_cmd=RelayCmd(DATA) data_len=498 queued_before_bytes=0 queued_after_bytes=498 closes_stream=false torfast relay receive delivered",
                "2026-06-06T23:12:38Z DEBUG tor_proto::circuit::circhop: event_epoch_ms=1780787557500 circ_id=Circ 0.4 (Tunnel 15) hop=Some(HopNum(3)) stream_id=11302 relay_cmd=RelayCmd(DATA) data_len=300 queued_before_bytes=498 queued_after_bytes=798 closes_stream=false torfast relay receive delivered",
            ]
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["timing_id"], 7)
        self.assertEqual(rows[0]["target_kind"], "hostname")
        self.assertEqual(rows[0]["circ_id"], "Circ 0.4 (Tunnel 15)")
        self.assertEqual(rows[0]["stream_id"], 11302)
        self.assertEqual(rows[0]["relay_ms"], 9000)
        self.assertEqual(rows[0]["first_tor_to_client_ms"], 200)
        self.assertEqual(rows[0]["first_tor_to_client_write_ms"], 260)
        self.assertEqual(rows[0]["tor_to_client_bytes"], 411460)
        self.assertEqual(rows[0]["tor_to_client_write_bytes"], 411460)
        self.assertEqual(rows[0]["data_cells"], 2)
        self.assertEqual(rows[0]["data_bytes"], 798)
        self.assertEqual(rows[0]["span_ms"], 500)
        self.assertEqual(rows[0]["max_gap_ms"], 500.0)
        self.assertEqual(rows[0]["max_queued_after_bytes"], 798)

    def test_summarizes_torfast_socks_relay_join_by_browser_run(self) -> None:
        base1 = int(parse_log_timestamp_ms("2026-06-06T23:12:37Z x") or 0)
        base2 = int(parse_log_timestamp_ms("2026-06-06T23:12:41Z x") or 0)
        payload = {
            "profiles": {
                "arti_release_browser": {
                    "proxy_output_tail": [
                        f"timing_id=7 target_kind=hostname port=443 conn_started_epoch_ms={base1 + 100} circ_id=Circ 0.4 hop=3 stream_id=11302 elapsed_ms=122 torfast socks timing stream linked",
                        f"timing_id=7 target_kind=hostname port=443 conn_started_epoch_ms={base1 + 100} relay_ms=900 tor_to_client_bytes=3400 first_tor_to_client_ms=150 first_tor_to_client_epoch_ms={base1 + 250} elapsed_ms=922 ok=true torfast socks timing relay finished",
                        f"event_epoch_ms={base1 + 300} circ_id=Circ 0.4 (Tunnel 15) hop=Some(HopNum(3)) stream_id=11302 relay_cmd=RelayCmd(DATA) data_len=498 queued_before_bytes=0 queued_after_bytes=498 closes_stream=false torfast relay receive delivered",
                        f"event_epoch_ms={base1 + 700} circ_id=Circ 0.4 (Tunnel 15) hop=Some(HopNum(3)) stream_id=11302 relay_cmd=RelayCmd(DATA) data_len=300 queued_before_bytes=498 queued_after_bytes=798 closes_stream=false torfast relay receive delivered",
                        f"timing_id=8 target_kind=hostname port=443 conn_started_epoch_ms={base2 + 100} circ_id=Circ 0.5 hop=3 stream_id=11303 elapsed_ms=122 torfast socks timing stream linked",
                        f"timing_id=8 target_kind=hostname port=443 conn_started_epoch_ms={base2 + 100} relay_ms=500 tor_to_client_bytes=200 first_tor_to_client_ms=80 first_tor_to_client_epoch_ms={base2 + 180} elapsed_ms=622 ok=true torfast socks timing relay finished",
                        f"event_epoch_ms={base2 + 200} circ_id=Circ 0.5 (Tunnel 16) hop=Some(HopNum(3)) stream_id=11303 relay_cmd=RelayCmd(DATA) data_len=50 queued_before_bytes=0 queued_after_bytes=50 closes_stream=false torfast relay receive delivered",
                    ],
                    "benchmarks": {
                        "https://example.com/": {
                            "runs": [
                                {
                                    "run_index": 1,
                                    "load_ms": 1000,
                                    "performance_timing": {
                                        "time_origin_ms": base1,
                                        "navigation": {
                                            "domContentLoadedEventEnd": 400,
                                            "loadEventEnd": 1000,
                                        },
                                    },
                                },
                                {
                                    "run_index": 2,
                                    "load_ms": 800,
                                    "performance_timing": {
                                        "time_origin_ms": base2,
                                        "navigation": {"loadEventEnd": 800},
                                    },
                                },
                            ]
                        }
                    },
                }
            }
        }

        rows = torfast_socks_relay_join_run_summary_rows(payload)

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["run_index"], 1)
        self.assertEqual(rows[0]["joined_streams"], 1)
        self.assertEqual(rows[0]["unique_circuits"], 1)
        self.assertEqual(rows[0]["data_cells"], 2)
        self.assertEqual(rows[0]["data_bytes"], 798)
        self.assertEqual(rows[0]["tor_to_client_bytes"], 3400)
        self.assertEqual(rows[0]["first_stream_after_start_ms"], 100.0)
        self.assertEqual(rows[0]["first_relay_receive_after_start_ms"], 300.0)
        self.assertEqual(rows[0]["last_relay_receive_before_load_ms"], 300.0)
        self.assertEqual(rows[0]["max_receive_gap_ms"], 400.0)
        self.assertEqual(rows[0]["max_receive_span_ms"], 400.0)
        self.assertEqual(rows[0]["max_queued_after_bytes"], 798)
        self.assertEqual(rows[0]["top_timing_id"], 7)
        self.assertEqual(rows[0]["top_circ_id"], "Circ 0.4 (Tunnel 15)")
        self.assertEqual(rows[0]["top_stream_id"], 11302)
        self.assertEqual(rows[1]["run_index"], 2)
        self.assertEqual(rows[1]["data_bytes"], 50)
        self.assertEqual(rows[1]["tor_to_client_bytes"], 200)

        shape_rows = torfast_socks_relay_circuit_shape_rows(payload)

        self.assertEqual(len(shape_rows), 2)
        self.assertEqual(shape_rows[0]["run_index"], 1)
        self.assertEqual(shape_rows[0]["circ_id"], "Circ 0.4 (Tunnel 15)")
        self.assertEqual(shape_rows[0]["streams"], 1)
        self.assertEqual(shape_rows[0]["data_bytes"], 798)
        self.assertEqual(shape_rows[0]["tor_to_client_bytes"], 3400)
        self.assertEqual(shape_rows[0]["max_receive_span_ms"], 400)
        self.assertEqual(shape_rows[0]["max_receive_gap_ms"], 400.0)
        self.assertEqual(shape_rows[0]["top_timing_id"], 7)
        self.assertEqual(shape_rows[1]["run_index"], 2)
        self.assertEqual(shape_rows[1]["circ_id"], "Circ 0.5 (Tunnel 16)")
        self.assertEqual(shape_rows[1]["data_bytes"], 50)

        quality_rows = torfast_socks_relay_circuit_quality_rows(payload)

        self.assertEqual(len(quality_rows), 2)
        self.assertEqual(quality_rows[0]["run_index"], 1)
        self.assertEqual(quality_rows[0]["circ_id"], "Circ 0.4 (Tunnel 15)")
        self.assertEqual(quality_rows[0]["relay_streams"], 1)
        self.assertEqual(quality_rows[0]["median_first_tor_to_client_ms"], 150.0)
        self.assertEqual(quality_rows[0]["median_relay_ms"], 900.0)
        self.assertEqual(quality_rows[0]["max_relay_ms"], 900.0)
        self.assertAlmostEqual(
            quality_rows[0]["rough_receive_kib_s"], 798 * 1000 / 400 / 1024
        )

        quality_summary_rows = torfast_socks_relay_circuit_quality_run_summary_rows(
            payload
        )

        self.assertEqual(len(quality_summary_rows), 2)
        self.assertEqual(quality_summary_rows[0]["run_index"], 1)
        self.assertEqual(quality_summary_rows[0]["circuits"], 1)
        self.assertEqual(quality_summary_rows[0]["relay_streams"], 1)
        self.assertEqual(quality_summary_rows[0]["data_bytes"], 798)
        self.assertEqual(quality_summary_rows[0]["low_rate_circuits"], 1)
        self.assertEqual(quality_summary_rows[0]["low_rate_streams"], 1)
        self.assertEqual(quality_summary_rows[0]["low_rate_data_bytes"], 798)
        self.assertEqual(quality_summary_rows[0]["slow_relay_circuits"], 0)
        self.assertEqual(
            quality_summary_rows[0]["worst_circ_id"], "Circ 0.4 (Tunnel 15)"
        )

    def test_socks_relay_circuit_quality_falls_back_to_terminal_rows(self) -> None:
        first_terminal = (
            "INFO tor_proto::client::stream::data: event_epoch_ms=2500 "
            "circ_id=Circ 0.4 (Tunnel 15) hop=#3 stream_id=11302 connected=true "
            "first_data_after_start_ms=100 transfer_ms=1000 idle_after_last_data_ms=10 "
            "max_data_gap_ms=200 relay_data_bytes=4096 pending_after_bytes=0 "
            "user_read_bytes=4096 data_cells=8 read_events=9 sendmes=1 sendme_ok=1 "
            "min_recv_window_after_take=450 max_queued_after_bytes=512 "
            "error_kind=not_connected end_reason= returned_eof=false "
            "torfast stream receiver terminal summary"
        )
        second_terminal = (
            "INFO tor_proto::client::stream::data: event_epoch_ms=2600 "
            "circ_id=Circ 0.4 (Tunnel 15) hop=#3 stream_id=11303 connected=true "
            "first_data_after_start_ms=150 transfer_ms=500 idle_after_last_data_ms=20 "
            "max_data_gap_ms=300 relay_data_bytes=2048 pending_after_bytes=0 "
            "user_read_bytes=2048 data_cells=4 read_events=5 sendmes=0 sendme_ok=0 "
            "min_recv_window_after_take=490 max_queued_after_bytes=128 "
            "error_kind=not_connected end_reason= returned_eof=false "
            "torfast stream receiver terminal summary"
        )
        payload = {
            "browser_default_prefs": {
                "ok": True,
                "prefs": dict(REQUIRED_DEFAULT_PREFS),
            },
            "profiles": {
                "arti_release_browser": {
                    "boot": {"ok": True},
                    "benchmarks": {
                        "https://example.com/": {
                            "summary": {"ok": True},
                            "runs": [
                                {
                                    "ok": True,
                                    "run_index": 1,
                                    "load_ms": 1800.0,
                                    "started_epoch_ms": 1000,
                                    "finished_epoch_ms": 3000,
                                    "expected_socks_port": 19082,
                                    "effective_proxy_prefs": {
                                        "network.proxy.socks": "127.0.0.1",
                                        "network.proxy.socks_port": 19082,
                                        "network.proxy.socks_remote_dns": True,
                                        "network.proxy.type": 1,
                                    },
                                    "screenshot": {
                                        "exists": True,
                                        "bytes": 100,
                                        "width": 10,
                                        "height": 10,
                                    },
                                    "performance_timing": {
                                        "time_origin_ms": 1000,
                                        "navigation": {"loadEventEnd": 1800},
                                    },
                                    "proxy_relay_context_lines": [first_terminal],
                                    "proxy_output_tail": [
                                        "INFO arti::proxy::socks: timing_id=7 target_kind=hostname port=443 circ_id=Circ 0.4 hop=#3 stream_id=11302 relay_ms=1200 first_tor_to_client_ms=120 tor_to_client_bytes=4096 ok=false torfast socks timing relay finished",
                                        first_terminal,
                                        "INFO arti::proxy::socks: timing_id=8 target_kind=hostname port=443 circ_id=Circ 0.4 hop=#3 stream_id=11303 relay_ms=800 first_tor_to_client_ms=160 tor_to_client_bytes=2048 ok=false torfast socks timing relay finished",
                                        second_terminal,
                                    ],
                                }
                            ],
                        }
                    },
                }
            }
        }

        quality_rows = torfast_socks_relay_circuit_quality_rows(payload)

        self.assertEqual(len(quality_rows), 1)
        self.assertEqual(quality_rows[0]["circ_id"], "Circ 0.4 (Tunnel 15)")
        self.assertEqual(quality_rows[0]["streams"], 2)
        self.assertEqual(quality_rows[0]["relay_streams"], 2)
        self.assertEqual(quality_rows[0]["data_bytes"], 6144)
        self.assertEqual(quality_rows[0]["tor_to_client_bytes"], 6144)
        self.assertEqual(quality_rows[0]["median_first_tor_to_client_ms"], 140.0)
        self.assertEqual(quality_rows[0]["median_relay_ms"], 1000.0)
        self.assertEqual(quality_rows[0]["max_relay_ms"], 1200.0)
        self.assertEqual(quality_rows[0]["max_receive_span_ms"], 1000.0)
        self.assertEqual(quality_rows[0]["max_receive_gap_ms"], 300.0)
        self.assertAlmostEqual(
            quality_rows[0]["rough_receive_kib_s"], 6144 * 1000 / 1000 / 1024
        )
        self.assertEqual(quality_rows[0]["top_timing_id"], 7)
        self.assertEqual(quality_rows[0]["top_stream_id"], 11302)

        quality_summary_rows = torfast_socks_relay_circuit_quality_run_summary_rows(
            payload
        )

        self.assertEqual(len(quality_summary_rows), 1)
        self.assertEqual(quality_summary_rows[0]["circuits"], 1)
        self.assertEqual(quality_summary_rows[0]["relay_streams"], 2)
        self.assertEqual(quality_summary_rows[0]["data_bytes"], 6144)
        self.assertEqual(quality_summary_rows[0]["slow_relay_circuits"], 0)

    def test_report_prints_terminal_only_circuit_quality(self) -> None:
        terminal = (
            "INFO tor_proto::client::stream::data: event_epoch_ms=2500 "
            "circ_id=Circ 0.4 (Tunnel 15) hop=#3 stream_id=11302 connected=true "
            "first_data_after_start_ms=100 transfer_ms=1000 idle_after_last_data_ms=10 "
            "max_data_gap_ms=200 relay_data_bytes=4096 pending_after_bytes=0 "
            "user_read_bytes=4096 data_cells=8 read_events=9 sendmes=1 sendme_ok=1 "
            "min_recv_window_after_take=450 max_queued_after_bytes=512 "
            "error_kind=not_connected end_reason= returned_eof=false "
            "torfast stream receiver terminal summary"
        )
        payload = {
            "browser_default_prefs": {
                "ok": True,
                "prefs": dict(REQUIRED_DEFAULT_PREFS),
            },
            "profiles": {
                "arti_release_browser": {
                    "boot": {"ok": True},
                    "benchmarks": {
                        "https://example.com/": {
                            "summary": {"ok": True},
                            "runs": [
                                {
                                    "ok": True,
                                    "run_index": 1,
                                    "load_ms": 1800.0,
                                    "started_epoch_ms": 1000,
                                    "finished_epoch_ms": 3000,
                                    "expected_socks_port": 19082,
                                    "effective_proxy_prefs": {
                                        "network.proxy.socks": "127.0.0.1",
                                        "network.proxy.socks_port": 19082,
                                        "network.proxy.socks_remote_dns": True,
                                        "network.proxy.type": 1,
                                    },
                                    "screenshot": {
                                        "exists": True,
                                        "bytes": 100,
                                        "width": 10,
                                        "height": 10,
                                    },
                                    "performance_timing": {
                                        "time_origin_ms": 1000,
                                        "navigation": {"loadEventEnd": 1800},
                                    },
                                    "proxy_output_tail": [
                                        "INFO arti::proxy::socks: timing_id=7 target_kind=hostname port=443 circ_id=Circ 0.4 hop=#3 stream_id=11302 relay_ms=1200 first_tor_to_client_ms=120 tor_to_client_bytes=4096 ok=false torfast socks timing relay finished",
                                        terminal,
                                    ],
                                }
                            ],
                        }
                    },
                }
            }
        }

        with tempfile.TemporaryDirectory() as tmp:
            result_path = Path(tmp) / "browser-compare.json"
            result_path.write_text(json.dumps(payload), encoding="utf-8")
            stdout = io.StringIO()
            with patch("sys.argv", ["analyze_browser_compare.py", str(result_path)]):
                with patch("sys.stdout", stdout):
                    exit_code = analyze_browser_compare_main()

        self.assertEqual(exit_code, 0)
        output = stdout.getvalue()
        self.assertIn("## Torfast SOCKS Relay Circuit Quality", output)
        self.assertIn("## Torfast SOCKS Relay Circuit Quality Run Summary", output)
        self.assertIn("Circ 0.4 (Tunnel 15)", output)
        self.assertIn("4096", output)

    def test_maps_browser_resource_to_nearest_socks_relay_join(self) -> None:
        base = int(parse_log_timestamp_ms("2026-06-06T23:12:37Z x") or 0)
        payload = {
            "profiles": {
                "arti_release_browser": {
                    "proxy_output_tail": [
                        f"timing_id=7 target_kind=hostname target_label=example.com port=443 conn_started_epoch_ms={base + 105} circ_id=Circ 0.4 hop=3 stream_id=11302 elapsed_ms=122 torfast socks timing stream linked",
                        f"timing_id=7 target_kind=hostname target_label=example.com port=443 conn_started_epoch_ms={base + 105} relay_ms=900 first_tor_to_client_ms=145 first_tor_to_client_epoch_ms={base + 250} first_tor_to_client_write_ms=185 first_tor_to_client_write_epoch_ms={base + 290} last_tor_to_client_ms=450 last_tor_to_client_write_ms=455 tor_to_client_bytes=3400 tor_to_client_write_bytes=3400 elapsed_ms=922 ok=true torfast socks timing relay finished",
                        f"event_epoch_ms={base + 300} circ_id=Circ 0.4 (Tunnel 15) hop=Some(HopNum(3)) stream_id=11302 relay_cmd=RelayCmd(DATA) data_len=498 queued_before_bytes=0 queued_after_bytes=498 closes_stream=false torfast relay receive delivered",
                    ],
                    "benchmarks": {
                        "https://example.com/": {
                            "runs": [
                                {
                                    "run_index": 1,
                                    "ok": True,
                                    "proxy_signal_lines": [
                                        "2026-06-06T23:12:37Z DEBUG tor_circmgr::mgr: open_candidates=2 select_parallelism=1 select_load_aware=false select_health_aware=false select_avoid_bad_health=false selected_candidate_index=-1 candidate_assignment_summary=0:Circ~0.4:2,1:Circ~0.5:0 candidate_health_summary=0:Circ~0.4:0:0:0:0:0:0,1:Circ~0.5:4:12000:25:120000:100:1 selected_assigned_streams=2 usage_kind=\"exit\" restrict_circ=true tunnel_unique_id=Circ 0.4 torfast circuit selection open",
                                    ],
                                    "performance_timing": {
                                        "time_origin_ms": base,
                                        "navigation": {
                                            "domContentLoadedEventEnd": 400,
                                            "loadEventEnd": 1000,
                                        },
                                        "resources": [
                                            {
                                                "name": "https://example.com/app.css",
                                                "initiatorType": "link",
                                                "connectStart": 100,
                                                "fetchStart": 10,
                                                "duration": 500,
                                                "requestStart": 120,
                                                "responseStart": 420,
                                                "responseEnd": 600,
                                                "encodedBodySize": 498,
                                            }
                                        ],
                                    },
                                }
                            ]
                        }
                    },
                }
            }
        }

        rows = browser_resource_socks_relay_join_rows(payload)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["resource"], "https://example.com/app.css")
        self.assertEqual(rows[0]["match_field"], "connectStart")
        self.assertEqual(rows[0]["match_delta_ms"], 5.0)
        self.assertEqual(rows[0]["match_confidence"], "high")
        self.assertEqual(rows[0]["target_label"], "example.com")
        self.assertEqual(rows[0]["stream_set_match_confidence"], "exact")
        self.assertEqual(rows[0]["host_lifetime_candidates"], 1)
        self.assertEqual(rows[0]["host_lifetime_candidate_stream_ids"], "11302")
        self.assertEqual(rows[0]["timing_id"], 7)
        self.assertEqual(rows[0]["circ_id"], "Circ 0.4 (Tunnel 15)")
        self.assertEqual(rows[0]["stream_id"], 11302)
        self.assertEqual(rows[0]["first_tor_to_client_ms"], 145)
        self.assertEqual(rows[0]["first_tor_to_client_write_ms"], 185)
        self.assertEqual(rows[0]["last_tor_to_client_ms"], 450)
        self.assertEqual(rows[0]["last_tor_to_client_write_ms"], 455)
        self.assertEqual(rows[0]["last_tor_to_client_epoch_ms"], base + 555)
        self.assertEqual(rows[0]["tor_to_client_idle_after_last_ms"], 472)
        self.assertEqual(rows[0]["response_end_after_last_tor_byte_ms"], 45)
        self.assertEqual(rows[0]["last_tor_byte_before_load_ms"], 445)
        self.assertEqual(rows[0]["tor_to_client_write_bytes"], 3400)
        self.assertEqual(rows[0]["wait_ms"], 300.0)
        self.assertEqual(rows[0]["receive_ms"], 180.0)
        self.assertEqual(rows[0]["response_end_ms"], 600)
        self.assertEqual(rows[0]["tail_after_dom_ms"], 200)
        self.assertEqual(rows[0]["response_end_before_load_ms"], 400)

        queue_rows = browser_resource_queue_socks_relay_tail_rows(payload)

        self.assertEqual(len(queue_rows), 1)
        self.assertEqual(queue_rows[0]["resource"], "https://example.com/app.css")
        self.assertEqual(queue_rows[0]["fetch_to_request_ms"], 110.0)
        self.assertEqual(queue_rows[0]["timing_id"], 7)
        self.assertEqual(queue_rows[0]["circ_id"], "Circ 0.4 (Tunnel 15)")

        cluster_rows = browser_resource_queue_socks_relay_cluster_rows(payload)

        self.assertEqual(len(cluster_rows), 1)
        self.assertEqual(cluster_rows[0]["timing_id"], 7)
        self.assertEqual(cluster_rows[0]["queued_resources"], 1)
        self.assertEqual(cluster_rows[0]["queued_500ms"], 0)
        self.assertEqual(cluster_rows[0]["queued_1000ms"], 0)
        self.assertEqual(cluster_rows[0]["median_fetch_to_request_ms"], 110.0)
        self.assertEqual(cluster_rows[0]["max_fetch_to_request_ms"], 110.0)
        self.assertIn("app.css", cluster_rows[0]["top_resources"])

        selection_context_rows = browser_resource_queue_selection_context_rows(payload)

        self.assertEqual(len(selection_context_rows), 1)
        self.assertEqual(selection_context_rows[0]["timing_id"], 7)
        self.assertEqual(selection_context_rows[0]["selected_open_rows"], 1)
        self.assertEqual(selection_context_rows[0]["multi_candidate_selected_rows"], 1)
        self.assertEqual(selection_context_rows[0]["lower_assignment_alt_rows"], 1)
        self.assertEqual(selection_context_rows[0]["better_health_alt_rows"], 1)
        self.assertEqual(selection_context_rows[0]["better_health_move_alt_rows"], 1)
        self.assertEqual(selection_context_rows[0]["below_floor_health_alt_rows"], 0)
        self.assertEqual(selection_context_rows[0]["cold_selected_alt_scored_rows"], 1)
        self.assertEqual(selection_context_rows[0]["health_min_move_score_bps"], 65536)
        self.assertEqual(selection_context_rows[0]["max_selected_assigned_streams"], 2.0)
        self.assertEqual(selection_context_rows[0]["max_alt_health_score_bps"], 120000.0)
        self.assertIn("*0:Circ 0.4", selection_context_rows[0]["first_candidate_context"])
        self.assertIn("1:Circ 0.5", selection_context_rows[0]["first_candidate_context"])

        summary_rows = browser_resource_socks_relay_summary_rows(payload)

        self.assertEqual(len(summary_rows), 1)
        self.assertEqual(summary_rows[0]["profile"], "arti_release_browser")
        self.assertEqual(summary_rows[0]["target"], "https://example.com/")
        self.assertEqual(summary_rows[0]["resources"], 1)
        self.assertEqual(summary_rows[0]["high_confidence"], 1)
        self.assertEqual(summary_rows[0]["slow_resources_2s"], 0)
        self.assertEqual(summary_rows[0]["resources_ending_final_1s"], 1)
        self.assertEqual(summary_rows[0]["median_duration_ms"], 500)
        self.assertEqual(summary_rows[0]["median_wait_ms"], 300)
        self.assertEqual(summary_rows[0]["median_receive_ms"], 180)
        self.assertEqual(summary_rows[0]["max_response_end_ms"], 600)
        self.assertEqual(summary_rows[0]["max_tail_after_dom_ms"], 200)
        self.assertEqual(summary_rows[0]["median_response_end_before_load_ms"], 400)
        self.assertEqual(summary_rows[0]["median_relay_ms"], 900)
        self.assertEqual(summary_rows[0]["median_last_tor_to_client_ms"], 450)
        self.assertEqual(
            summary_rows[0]["median_tor_to_client_idle_after_last_ms"], 472
        )
        self.assertEqual(
            summary_rows[0]["median_response_end_after_last_tor_byte_ms"], 45
        )
        self.assertIsNone(summary_rows[0]["max_receive_gap_ms"])

    def test_marks_reused_same_host_stream_match_as_ambiguous(self) -> None:
        base = int(parse_log_timestamp_ms("2026-06-06T23:12:37Z x") or 0)
        payload = {
            "profiles": {
                "arti_release_browser": {
                    "proxy_output_tail": [
                        f"timing_id=7 target_kind=hostname target_label=example.com port=443 conn_started_epoch_ms={base + 100} circ_id=Circ 0.4 hop=3 stream_id=11302 elapsed_ms=10 torfast socks timing stream linked",
                        f"timing_id=7 target_kind=hostname target_label=example.com port=443 conn_started_epoch_ms={base + 100} relay_ms=900 first_tor_to_client_ms=120 first_tor_to_client_epoch_ms={base + 220} last_tor_to_client_ms=800 tor_to_client_bytes=3400 elapsed_ms=900 ok=true torfast socks timing relay finished",
                        f"timing_id=8 target_kind=hostname target_label=example.com port=443 conn_started_epoch_ms={base + 110} circ_id=Circ 0.4 hop=3 stream_id=11303 elapsed_ms=10 torfast socks timing stream linked",
                        f"timing_id=8 target_kind=hostname target_label=example.com port=443 conn_started_epoch_ms={base + 110} relay_ms=900 first_tor_to_client_ms=120 first_tor_to_client_epoch_ms={base + 230} last_tor_to_client_ms=800 tor_to_client_bytes=3400 elapsed_ms=900 ok=true torfast socks timing relay finished",
                        f"event_epoch_ms={base + 300} circ_id=Circ 0.4 (Tunnel 15) hop=Some(HopNum(3)) stream_id=11302 relay_cmd=RelayCmd(DATA) data_len=498 queued_before_bytes=0 queued_after_bytes=498 closes_stream=false torfast relay receive delivered",
                        f"event_epoch_ms={base + 310} circ_id=Circ 0.4 (Tunnel 15) hop=Some(HopNum(3)) stream_id=11303 relay_cmd=RelayCmd(DATA) data_len=498 queued_before_bytes=0 queued_after_bytes=498 closes_stream=false torfast relay receive delivered",
                    ],
                    "benchmarks": {
                        "https://example.com/": {
                            "runs": [
                                {
                                    "run_index": 1,
                                    "ok": True,
                                    "performance_timing": {
                                        "time_origin_ms": base,
                                        "resources": [
                                            {
                                                "name": "https://example.com/app.css",
                                                "initiatorType": "link",
                                                "fetchStart": 0,
                                                "requestStart": 400,
                                                "responseStart": 500,
                                                "responseEnd": 600,
                                            }
                                        ],
                                    },
                                }
                            ]
                        }
                    },
                }
            }
        }

        rows = browser_resource_socks_relay_join_rows(payload)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["stream_set_match_confidence"], "ambiguous")
        self.assertEqual(rows[0]["host_lifetime_candidates"], 2)
        self.assertEqual(rows[0]["host_lifetime_candidate_stream_ids"], "11302, 11303")

    def test_maps_browser_resource_to_socks_stream_without_relay_receive_debug(
        self,
    ) -> None:
        base = int(parse_log_timestamp_ms("2026-06-06T23:12:37Z x") or 0)
        payload = {
            "profiles": {
                "arti_release_browser": {
                    "proxy_signal_lines": [
                        f"timing_id=7 target_kind=hostname port=443 conn_started_epoch_ms={base + 105} circ_id=Circ 0.4 hop=3 stream_id=11302 elapsed_ms=122 torfast socks timing stream linked",
                        f"timing_id=7 target_kind=hostname port=443 conn_started_epoch_ms={base + 105} relay_ms=900 first_tor_to_client_ms=145 first_tor_to_client_epoch_ms={base + 250} last_tor_to_client_ms=450 tor_to_client_bytes=3400 elapsed_ms=922 ok=false copy_error_kind=not_connected torfast socks timing relay finished",
                    ],
                    "benchmarks": {
                        "https://example.com/": {
                            "runs": [
                                {
                                    "run_index": 1,
                                    "ok": True,
                                    "performance_timing": {
                                        "time_origin_ms": base,
                                        "navigation": {
                                            "domContentLoadedEventEnd": 400,
                                            "loadEventEnd": 1000,
                                        },
                                        "resources": [
                                            {
                                                "name": "https://example.com/app.css",
                                                "initiatorType": "link",
                                                "connectStart": 100,
                                                "fetchStart": 10,
                                                "duration": 500,
                                                "requestStart": 120,
                                                "responseStart": 420,
                                                "responseEnd": 600,
                                                "encodedBodySize": 498,
                                            }
                                        ],
                                    },
                                }
                            ]
                        }
                    },
                }
            }
        }

        rows = browser_resource_socks_relay_join_rows(payload)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["resource"], "https://example.com/app.css")
        self.assertEqual(rows[0]["match_confidence"], "high")
        self.assertEqual(rows[0]["timing_id"], 7)
        self.assertEqual(rows[0]["circ_id"], "Circ 0.4")
        self.assertEqual(rows[0]["stream_id"], 11302)
        self.assertEqual(rows[0]["joined_relay_receive"], False)
        self.assertEqual(rows[0]["relay_ms"], 900)
        self.assertEqual(rows[0]["tor_to_client_bytes"], 3400)
        self.assertIsNone(rows[0].get("max_gap_ms"))

    def test_browser_run_late_phase_queue_context_rows(self) -> None:
        base = int(parse_log_timestamp_ms("2026-06-06T23:12:37Z x") or 0)
        payload = {
            "profiles": {
                "arti_release_browser": {
                    "proxy_output_tail": [
                        f"timing_id=7 target_kind=hostname port=443 conn_started_epoch_ms={base + 105} circ_id=Circ 0.4 hop=3 stream_id=11302 elapsed_ms=122 torfast socks timing stream linked",
                        f"timing_id=7 target_kind=hostname port=443 conn_started_epoch_ms={base + 105} relay_ms=1900 first_tor_to_client_ms=145 first_tor_to_client_epoch_ms={base + 250} first_tor_to_client_write_ms=185 first_tor_to_client_write_epoch_ms={base + 290} last_tor_to_client_ms=1450 last_tor_to_client_write_ms=1455 tor_to_client_bytes=3400 tor_to_client_write_bytes=3400 elapsed_ms=1922 ok=true torfast socks timing relay finished",
                        f"event_epoch_ms={base + 300} circ_id=Circ 0.4 (Tunnel 15) hop=Some(HopNum(3)) stream_id=11302 relay_cmd=RelayCmd(DATA) data_len=498 queued_before_bytes=0 queued_after_bytes=498 closes_stream=false torfast relay receive delivered",
                    ],
                    "benchmarks": {
                        "https://example.com/": {
                            "runs": [
                                {
                                    "run_index": 1,
                                    "ok": True,
                                    "proxy_signal_lines": [
                                        "2026-06-06T23:12:37Z DEBUG tor_circmgr::mgr: open_candidates=2 select_parallelism=1 select_load_aware=false select_health_aware=false select_avoid_bad_health=false selected_candidate_index=-1 candidate_assignment_summary=0:Circ~0.4:2,1:Circ~0.5:0 candidate_health_summary=0:Circ~0.4:0:0:0:0:0:0,1:Circ~0.5:4:12000:25:120000:100:1 selected_assigned_streams=2 usage_kind=\"exit\" restrict_circ=true tunnel_unique_id=Circ 0.4 torfast circuit selection open",
                                    ],
                                    "performance_timing": {
                                        "time_origin_ms": base,
                                        "navigation": {
                                            "responseStart": 100,
                                            "domContentLoadedEventEnd": 900,
                                            "loadEventEnd": 1400,
                                        },
                                        "resources": [
                                            {
                                                "name": "https://example.com/blocker.css",
                                                "nextHopProtocol": "http/1.1",
                                                "connectStart": 100,
                                                "fetchStart": 0,
                                                "requestStart": 100,
                                                "responseStart": 300,
                                                "responseEnd": 1300,
                                            },
                                            {
                                                "name": "https://example.com/queued.css",
                                                "nextHopProtocol": "http/1.1",
                                                "connectStart": 100,
                                                "fetchStart": 0,
                                                "requestStart": 1200,
                                                "responseStart": 1300,
                                                "responseEnd": 1500,
                                            },
                                        ],
                                    },
                                }
                            ]
                        }
                    },
                }
            }
        }

        rows = browser_run_late_phase_queue_context_rows(payload)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["response_to_dom_ms"], 800)
        self.assertEqual(rows[0]["dom_to_load_ms"], 500)
        self.assertEqual(rows[0]["queued_500ms"], 1)
        self.assertEqual(rows[0]["queued_1000ms"], 1)
        self.assertEqual(rows[0]["max_fetch_to_request_ms"], 1200.0)
        self.assertEqual(
            rows[0]["top_queued_resource"], "https://example.com/queued.css"
        )
        self.assertEqual(rows[0]["queue_timing_id"], 7)
        self.assertEqual(rows[0]["queue_circ_id"], "Circ 0.4 (Tunnel 15)")
        self.assertEqual(rows[0]["cluster_queued_1000ms"], 1)
        self.assertEqual(rows[0]["better_health_alt_rows"], 1)
        self.assertEqual(rows[0]["lower_assignment_alt_rows"], 1)
        self.assertIn("*0:Circ 0.4", rows[0]["candidate_context"])

    def test_arti_profile_late_queue_ab_rows_compare_extra_profile(self) -> None:
        def run(
            run_index: int,
            *,
            load_ms: float,
            response_to_dom_ms: float,
            dom_to_load_ms: float,
            queued_ms: float,
        ) -> dict[str, object]:
            return {
                "run_index": run_index,
                "ok": True,
                "load_ms": load_ms,
                "performance_timing": {
                    "navigation": {
                        "responseStart": 100,
                        "domContentLoadedEventEnd": 100 + response_to_dom_ms,
                        "loadEventEnd": 100 + response_to_dom_ms + dom_to_load_ms,
                    },
                    "resources": [
                        {
                            "name": f"https://example.com/r{run_index}.css",
                            "nextHopProtocol": "http/1.1",
                            "fetchStart": 0,
                            "requestStart": queued_ms,
                            "responseStart": queued_ms + 100,
                            "responseEnd": queued_ms + 200,
                        }
                    ],
                },
            }

        payload = {
            "targets": ["https://example.com/"],
            "profiles": {
                "arti_release_browser": {
                    "benchmarks": {
                        "https://example.com/": {
                            "runs": [
                                run(
                                    1,
                                    load_ms=1500,
                                    response_to_dom_ms=900,
                                    dom_to_load_ms=500,
                                    queued_ms=1000,
                                ),
                                run(
                                    2,
                                    load_ms=1400,
                                    response_to_dom_ms=500,
                                    dom_to_load_ms=800,
                                    queued_ms=700,
                                ),
                            ]
                        }
                    }
                },
                "arti_release_browser_healthaware_spread4": {
                    "benchmarks": {
                        "https://example.com/": {
                            "runs": [
                                run(
                                    1,
                                    load_ms=1300,
                                    response_to_dom_ms=700,
                                    dom_to_load_ms=500,
                                    queued_ms=800,
                                ),
                                run(
                                    2,
                                    load_ms=1600,
                                    response_to_dom_ms=900,
                                    dom_to_load_ms=600,
                                    queued_ms=1200,
                                ),
                            ]
                        }
                    }
                },
            },
        }

        rows = arti_profile_late_queue_ab_rows(payload)

        self.assertEqual(len(rows), 1)
        self.assertEqual(
            rows[0]["candidate_profile"], "arti_release_browser_healthaware_spread4"
        )
        self.assertEqual(rows[0]["paired_runs"], 2)
        self.assertEqual(rows[0]["candidate_queue_wins"], 1)
        self.assertEqual(rows[0]["median_queued_1000_delta"], 0.0)
        self.assertEqual(rows[0]["median_max_queue_delta_ms"], 150.0)
        self.assertEqual(rows[0]["median_response_to_dom_delta_ms"], 100.0)
        self.assertEqual(rows[0]["median_dom_to_load_delta_ms"], -100.0)
        self.assertEqual(rows[0]["candidate_max_queue_ms"], 1200.0)
        self.assertEqual(rows[0]["baseline_max_queue_ms"], 1000.0)

    def test_arti_profile_queue_loss_reason_rows_join_worst_queue_run(self) -> None:
        def run(
            run_index: int,
            *,
            load_ms: float,
            response_to_dom_ms: float,
            dom_to_load_ms: float,
            queued_ms: float,
        ) -> dict[str, object]:
            return {
                "run_index": run_index,
                "ok": True,
                "load_ms": load_ms,
                "performance_timing": {
                    "navigation": {
                        "responseStart": 100,
                        "domContentLoadedEventEnd": 100 + response_to_dom_ms,
                        "loadEventEnd": 100 + response_to_dom_ms + dom_to_load_ms,
                    },
                    "resources": [
                        {
                            "name": f"https://example.com/r{run_index}.css",
                            "nextHopProtocol": "http/1.1",
                            "fetchStart": 0,
                            "requestStart": queued_ms,
                            "responseStart": queued_ms + 100,
                            "responseEnd": queued_ms + 200,
                        }
                    ],
                },
            }

        payload = {
            "targets": ["https://example.com/"],
            "profiles": {
                "arti_release_browser": {
                    "benchmarks": {
                        "https://example.com/": {
                            "runs": [
                                run(
                                    1,
                                    load_ms=1000,
                                    response_to_dom_ms=500,
                                    dom_to_load_ms=400,
                                    queued_ms=300,
                                ),
                                run(
                                    2,
                                    load_ms=1100,
                                    response_to_dom_ms=500,
                                    dom_to_load_ms=400,
                                    queued_ms=400,
                                ),
                            ]
                        }
                    }
                },
                "arti_release_browser_healthaware_sameiso2": {
                    "benchmarks": {
                        "https://example.com/": {
                            "runs": [
                                run(
                                    1,
                                    load_ms=1800,
                                    response_to_dom_ms=900,
                                    dom_to_load_ms=700,
                                    queued_ms=1500,
                                ),
                                run(
                                    2,
                                    load_ms=1600,
                                    response_to_dom_ms=700,
                                    dom_to_load_ms=600,
                                    queued_ms=1200,
                                ),
                            ]
                        }
                    }
                },
            },
        }

        rows = arti_profile_queue_loss_reason_rows(payload)

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["candidate_profile"], "arti_release_browser_healthaware_sameiso2")
        self.assertEqual(row["median_load_delta_ms"], 650.0)
        self.assertEqual(row["median_queued_1000_delta"], 1.0)
        self.assertEqual(row["median_max_queue_delta_ms"], 1350.0)
        self.assertEqual(row["worst_queue_run"], 1)
        self.assertEqual(row["worst_run_load_delta_ms"], 800)
        self.assertEqual(row["worst_run_queued_1000_delta"], 1.0)
        self.assertEqual(row["worst_run_max_queue_delta_ms"], 1500.0)
        self.assertEqual(row["top_queued_resource"], "https://example.com/r1.css")
        self.assertEqual(row["reason_hint"], "browser resource queue")

    def test_arti_profile_queue_loss_mechanism_rows_identify_late_tor_data(
        self,
    ) -> None:
        base = int(parse_log_timestamp_ms("2026-06-06T23:12:37Z x") or 0)

        def run(
            run_index: int,
            *,
            load_ms: float,
            response_to_dom_ms: float,
            dom_to_load_ms: float,
            queued_ms: float,
            time_origin_ms: int,
            with_blocker: bool = False,
            signal_lines: list[str] | None = None,
        ) -> dict[str, object]:
            resources: list[dict[str, object]] = []
            if with_blocker:
                resources.append(
                    {
                        "name": "https://example.com/open-a.css",
                        "initiatorType": "link",
                        "nextHopProtocol": "http/1.1",
                        "connectStart": 100,
                        "fetchStart": 0,
                        "requestStart": 100,
                        "responseStart": 450,
                        "responseEnd": 2500,
                    }
                )
            resources.append(
                {
                    "name": f"https://example.com/r{run_index}.css",
                    "nextHopProtocol": "http/1.1",
                    "fetchStart": 0,
                    "requestStart": queued_ms,
                    "responseStart": queued_ms + 100,
                    "responseEnd": queued_ms + 200,
                }
            )
            result = {
                "run_index": run_index,
                "ok": True,
                "load_ms": load_ms,
                "performance_timing": {
                    "time_origin_ms": time_origin_ms,
                    "navigation": {
                        "responseStart": 100,
                        "domContentLoadedEventEnd": 100 + response_to_dom_ms,
                        "loadEventEnd": 100
                        + response_to_dom_ms
                        + dom_to_load_ms,
                    },
                    "resources": resources,
                },
            }
            if signal_lines is not None:
                result["proxy_signal_lines"] = signal_lines
            return result

        candidate_signal_lines = [
            '2026-06-06T23:12:37Z DEBUG tor_circmgr::mgr: launch_parallelism=1 plans=1 usage_kind="exit" torfast circuit selection build',
            f"timing_id=7 target_kind=hostname port=443 conn_started_epoch_ms={base + 105} circ_id=Circ 0.4 hop=3 stream_id=11302 elapsed_ms=122 torfast socks timing stream linked",
            f"timing_id=7 target_kind=hostname port=443 conn_started_epoch_ms={base + 105} relay_ms=2400 first_tor_to_client_ms=145 first_tor_to_client_epoch_ms={base + 250} first_tor_to_client_write_ms=185 first_tor_to_client_write_epoch_ms={base + 290} last_tor_to_client_ms=2395 last_tor_to_client_write_ms=2395 tor_to_client_idle_after_last_ms=27 tor_to_client_bytes=3400 tor_to_client_write_bytes=3400 elapsed_ms=2422 ok=true torfast socks timing relay finished",
            f"event_epoch_ms={base + 110} circ_id=Circ 0.4 (Tunnel 15) hop=HopNum(3) stream_id=11302 relay_cmd=RelayCmd(BEGIN) circuit_sender_queue_after_cells=0 delivery=\"channel_queued\" torfast stream lifecycle",
            f"event_epoch_ms={base + 210} circ_id=Circ 0.4 (Tunnel 15) hop=Some(HopNum(3)) stream_id=11302 relay_cmd=RelayCmd(CONNECTED) data_len=0 delivery=\"delivered\" torfast stream lifecycle",
            f"event_epoch_ms={base + 2400} circ_id=Circ 0.4 (Tunnel 15) hop=HopNum(3) stream_id=11302 relay_cmd=RelayCmd(DATA) circuit_sender_queue_after_cells=0 delivery=\"channel_queued\" torfast stream lifecycle",
            f"event_epoch_ms={base + 2500} circ_id=Circ 0.4 (Tunnel 15) hop=Some(HopNum(3)) stream_id=11302 relay_cmd=RelayCmd(DATA) data_len=300 delivery=\"delivered\" torfast stream lifecycle",
            f"event_epoch_ms={base + 2600} circ_id=Circ 0.4 (Tunnel 15) hop=Some(HopNum(3)) stream_id=11302 relay_cmd=RelayCmd(END) data_len=0 delivery=\"delivered\" torfast stream lifecycle",
            f"event_epoch_ms={base + 300} circ_id=Circ 0.4 (Tunnel 15) hop=Some(HopNum(3)) stream_id=11302 relay_cmd=RelayCmd(DATA) data_len=498 queued_before_bytes=0 queued_after_bytes=498 closes_stream=false torfast relay receive delivered",
            f"event_epoch_ms={base + 2500} circ_id=Circ 0.4 (Tunnel 15) hop=Some(HopNum(3)) stream_id=11302 relay_cmd=RelayCmd(DATA) data_len=300 queued_before_bytes=0 queued_after_bytes=300 closes_stream=false torfast relay receive delivered",
            f"event_epoch_ms={base + 2500} stream_id=11302 hop=None relay_cmd=DATA data_len=300 queued_after_bytes=0 recv_window_before=500 recv_window_after=499 sendme_due=false torfast stream receiver read",
            f"event_epoch_ms={base + 2500} circ_id=Circ 0.4 hop=#3 stream_id=11302 connected=true first_data_after_start_ms=145 transfer_ms=2395 idle_after_last_data_ms=0 max_data_gap_ms=1200 relay_data_bytes=3400 pending_after_bytes=0 user_read_bytes=3400 data_cells=7 read_events=7 sendmes=1 sendme_ok=1 min_recv_window_after_take=450 max_queued_after_bytes=498 error_kind= end_reason= returned_eof=true torfast stream receiver terminal summary",
            "2026-06-06T23:12:38Z INFO tor_proto::client::reactor::circuit::circhop: circ_id=Circ 0.4 (Tunnel 15) hop=#3 stream_id=11302 relay_cmd=DATA torfast stream scheduler picked",
            "2026-06-06T23:12:39Z INFO tor_proto::client::reactor::circuit::circhop: circ_id=Circ 0.4 (Tunnel 15) hop=#3 stream_id=11302 relay_cmd=DATA torfast stream scheduler picked",
            "2026-06-06T23:12:40Z INFO tor_proto::client::reactor::circuit: circ_id=Circ 0.4 (Tunnel 15) hop=#3 algorithm=fixed can_send=true cwnd_present=false cwnd=0 cwnd_full_present=false cwnd_full=false inflight_present=false inflight=0 torfast circuit congestion sendme sent",
            "2026-06-06T23:12:41Z INFO tor_proto::client::reactor::circuit: circ_id=Circ 0.4 (Tunnel 15) hop=#3 algorithm=fixed can_send=true cwnd_present=false cwnd=0 cwnd_full_present=false cwnd_full=false inflight_present=false inflight=0 channel_blocked=false channel_outbound_size=0 torfast circuit congestion sendme received",
        ]
        candidate_selection_line = "2026-06-06T23:12:37Z DEBUG tor_circmgr::mgr: open_candidates=1 select_load_aware=true select_health_aware=true selected_candidate_index=0 selected_assigned_streams=6 selected_active_streams=4 selected_health_score_bps=13125 selected_has_bad_health=false select_max_active_streams=0 active_stream_cap_moved=false active_stream_cap_saturated=false open_support_summary=total:3,supported:1,unusable:0,usage_kind:0,isolation:2,stability:0,port:0,country:0,other:0,exit_unisolated:0,exit_compatible_isolated:1,exit_incompatible_isolated:2,exit_port_blocked:0,exit_stability_blocked:0,exit_country_blocked:0 candidate_assignment_summary=0:Circ~0.4:6 candidate_health_summary=0:Circ~0.4:4:12000:351:13125:1000:351 usage_kind=\"exit\" restrict_circ=true tunnel_unique_id=Circ 0.4 torfast circuit selection open"

        payload = {
            "targets": ["https://example.com/"],
            "profiles": {
                "arti_release_browser": {
                    "benchmarks": {
                        "https://example.com/": {
                            "runs": [
                                run(
                                    1,
                                    load_ms=1000,
                                    response_to_dom_ms=500,
                                    dom_to_load_ms=400,
                                    queued_ms=300,
                                    time_origin_ms=base + 100000,
                                ),
                                run(
                                    2,
                                    load_ms=1100,
                                    response_to_dom_ms=500,
                                    dom_to_load_ms=400,
                                    queued_ms=400,
                                    time_origin_ms=base + 200000,
                                ),
                            ]
                        }
                    }
                },
                "arti_release_browser_healthaware_sameiso2": {
                    "proxy_output_tail": candidate_signal_lines,
                    "benchmarks": {
                        "https://example.com/": {
                            "runs": [
                                run(
                                    1,
                                    load_ms=1800,
                                    response_to_dom_ms=900,
                                    dom_to_load_ms=700,
                                    queued_ms=1200,
                                    time_origin_ms=base,
                                    with_blocker=True,
                                    signal_lines=candidate_signal_lines
                                    + [candidate_selection_line],
                                ),
                                run(
                                    2,
                                    load_ms=1600,
                                    response_to_dom_ms=700,
                                    dom_to_load_ms=600,
                                    queued_ms=1100,
                                    time_origin_ms=base + 300000,
                                ),
                            ]
                        }
                    },
                },
            },
        }

        rows = arti_profile_queue_loss_mechanism_rows(payload)

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(
            row["candidate_profile"], "arti_release_browser_healthaware_sameiso2"
        )
        self.assertEqual(row["worst_queue_run"], 1)
        self.assertEqual(row["median_load_delta_ms"], 650.0)
        self.assertEqual(row["worst_run_load_delta_ms"], 800)
        self.assertEqual(row["worst_run_queued_1000_delta"], 1.0)
        self.assertEqual(row["high_conf_queued_rows"], 1)
        self.assertEqual(row["high_conf_write_after_queue_1000ms"], 1)
        self.assertEqual(row["terminal_last_data_after_queue_1000ms"], 1)
        self.assertEqual(row["median_high_conf_write_after_queue_ms"], 1300.0)
        self.assertEqual(row["max_high_conf_write_after_queue_ms"], 1300.0)
        self.assertEqual(row["max_write_after_terminal_last_data_ms"], 0.0)
        self.assertEqual(row["max_terminal_data_gap_ms"], 1200.0)
        self.assertEqual(row["max_terminal_idle_after_last_data_ms"], 0.0)
        self.assertEqual(row["max_terminal_pending_after_bytes"], 0.0)
        self.assertEqual(row["terminal_sendmes"], 1.0)
        self.assertEqual(row["terminal_sendme_ok"], 1.0)
        self.assertEqual(row["min_terminal_recv_window_after_take"], 450.0)
        self.assertEqual(row["max_terminal_queued_after_bytes"], 498.0)
        self.assertEqual(row["queue_circuit"], "Circ 0.4 (Tunnel 15)")
        self.assertEqual(row["terminal_streams"], 1)
        self.assertAlmostEqual(row["terminal_relay_kib"], 3400 / 1024)
        self.assertEqual(row["terminal_data_cells"], 7.0)
        self.assertEqual(
            row["mechanism_hint"], "late Tor data, no local pending/window block"
        )

        selected_rows = arti_profile_queue_loss_selected_circuit_rows(payload)

        self.assertEqual(len(selected_rows), 1)
        selected = selected_rows[0]
        self.assertEqual(selected["queue_circuit"], "Circ 0.4 (Tunnel 15)")
        self.assertEqual(selected["late_resources"], 1)
        self.assertEqual(selected["late_timing_ids"], "7")
        self.assertEqual(selected["late_stream_ids"], "11302")
        self.assertEqual(selected["top_timing_id"], "7")
        self.assertEqual(selected["top_timing_share_pct"], 100.0)
        self.assertEqual(selected["top_stream_id"], "11302")
        self.assertEqual(selected["top_stream_share_pct"], 100.0)
        self.assertEqual(selected["terminal_streams"], 1)
        self.assertEqual(selected["terminal_stream_ids"], "11302")
        self.assertEqual(
            selected["selected_circuit_pattern_hint"], "single stream late"
        )

        cause_rows = arti_profile_queue_loss_cause_rows(payload)

        self.assertEqual(len(cause_rows), 1)
        cause = cause_rows[0]
        self.assertEqual(cause["queue_circuit"], "Circ 0.4 (Tunnel 15)")
        self.assertEqual(cause["scheduler_proof_hint"], "no scheduler monopoly seen")
        self.assertEqual(cause["scheduler_picks"], 2)
        self.assertEqual(cause["picked_streams"], 1)
        self.assertEqual(cause["congestion_events"], 2)
        self.assertEqual(cause["congestion_sendme_sent"], 1)
        self.assertEqual(cause["congestion_sendme_received"], 1)
        self.assertEqual(cause["congestion_scheduler_blocks"], 0)
        self.assertEqual(cause["congestion_can_send_false"], 0)
        self.assertEqual(cause["congestion_channel_blocked"], 0)
        self.assertEqual(cause["congestion_algorithms"], "fixed:2")
        self.assertEqual(
            cause["cause_hint"],
            "late selected-circuit DATA, not scheduler/congestion",
        )

        lifecycle_rows = resource_queue_lifecycle_evidence_rows(payload)

        self.assertEqual(len(lifecycle_rows), 1)
        lifecycle = lifecycle_rows[0]
        self.assertEqual(lifecycle["queued_resource"], "https://example.com/r1.css")
        self.assertEqual(lifecycle["timing_id"], 7)
        self.assertEqual(lifecycle["circ_id"], "Circ 0.4")
        self.assertEqual(lifecycle["stream_id"], 11302)
        self.assertEqual(lifecycle["lifecycle_state"], "END delivered and EOF")
        self.assertEqual(lifecycle["begin_to_connected_ms"], 100)
        self.assertEqual(lifecycle["data_to_data_ms"], 100)
        self.assertEqual(lifecycle["channel_queued"], 2)
        self.assertEqual(lifecycle["connected_delivered"], 1)
        self.assertEqual(lifecycle["data_delivered"], 1)
        self.assertEqual(lifecycle["end_delivered"], 1)
        self.assertEqual(lifecycle["queue_full"], 0)
        self.assertEqual(lifecycle["max_circuit_sender_queue_after_cells"], 0)
        self.assertEqual(lifecycle["terminal_pending_after_bytes"], 0)

        choice_rows = arti_profile_queue_loss_choice_rows(payload)

        self.assertEqual(len(choice_rows), 1)
        choice = choice_rows[0]
        self.assertEqual(choice["queue_circuit"], "Circ 0.4 (Tunnel 15)")
        self.assertEqual(choice["queued_1000ms"], 1)
        self.assertEqual(choice["slot_depth_6_queued_1000ms"], 0)
        self.assertEqual(choice["cluster_queued_1000ms"], 0)

        self.assertEqual(choice["better_health_alt_rows"], 0)
        self.assertEqual(choice["lower_assignment_alt_rows"], 0)
        self.assertEqual(
            choice["candidate_context"], "*0:Circ 0.4:a6:s13125.000:g351.000"
        )
        self.assertEqual(choice["choice_hint"], "only selected open circuit logged")

        capacity_rows = arti_profile_queue_loss_capacity_rows(payload)

        self.assertEqual(len(capacity_rows), 1)
        capacity = capacity_rows[0]
        self.assertEqual(capacity["queue_circuit"], "Circ 0.4 (Tunnel 15)")
        self.assertEqual(capacity["selected_open_rows"], 1)
        self.assertEqual(capacity["min_open_candidates"], 1.0)
        self.assertEqual(capacity["median_open_candidates"], 1.0)
        self.assertEqual(capacity["max_open_candidates"], 1.0)
        self.assertEqual(capacity["max_selected_assigned_streams"], 6.0)
        self.assertEqual(capacity["max_selected_active_streams"], 4.0)
        self.assertEqual(capacity["max_open_total"], 3)
        self.assertEqual(capacity["max_isolation_rejects"], 2)
        self.assertEqual(capacity["max_exit_unisolated"], 0)
        self.assertEqual(capacity["max_exit_compatible_isolated"], 1)
        self.assertEqual(capacity["max_exit_incompatible_isolated"], 2)
        self.assertEqual(capacity["max_port_rejects"], 0)
        self.assertEqual(capacity["max_unusable"], 0)
        self.assertEqual(capacity["max_active_cap"], 0.0)
        self.assertEqual(capacity["active_cap_moves"], 0)
        self.assertEqual(capacity["active_cap_saturated"], 0)
        self.assertEqual(capacity["load_aware_selected_rows"], 1)
        self.assertEqual(capacity["health_aware_selected_rows"], 1)
        self.assertEqual(capacity["builds"], 1)
        self.assertEqual(capacity["max_build_parallelism"], 1.0)
        self.assertEqual(capacity["same_isolation_topups"], 0)
        self.assertEqual(capacity["same_isolation_topup_failures"], 0)
        self.assertEqual(
            capacity["capacity_hint"],
            "other isolation groups own open circuits",
        )

        network_rows = arti_selected_circuit_network_evidence_rows(payload)

        self.assertEqual(len(network_rows), 1)
        network = network_rows[0]
        self.assertEqual(network["profile"], "arti_release_browser_healthaware_sameiso2")
        self.assertEqual(network["target"], "https://example.com/")
        self.assertEqual(network["run_index"], 1)
        self.assertEqual(network["circuit"], "Circ 0.4 (Tunnel 15)")
        self.assertEqual(network["late_resources"], 1)
        self.assertEqual(network["terminal_streams"], 1)
        self.assertEqual(network["scheduler_proof_hint"], "no scheduler monopoly seen")
        self.assertEqual(network["local_block_summary"], "no local block seen")
        self.assertEqual(
            network["candidate_context"], "*0:Circ 0.4:a6:s13125.000:g351.000"
        )
        self.assertEqual(network["choice_hint"], "only selected open circuit logged")
        self.assertEqual(network["max_circuit_data_gap_ms"], 2200)
        self.assertEqual(network["data_gap_scope_hint"], "whole circuit quiet")
        self.assertEqual(
            network["evidence_hint"],
            "whole-circuit DATA gap on selected circuit",
        )

        predictability_rows = arti_selected_circuit_gap_predictability_rows(payload)

        self.assertEqual(len(predictability_rows), 1)
        predictability = predictability_rows[0]
        self.assertEqual(
            predictability["profile"], "arti_release_browser_healthaware_sameiso2"
        )
        self.assertEqual(predictability["target"], "https://example.com/")
        self.assertEqual(predictability["run_index"], 1)
        self.assertEqual(predictability["circuit"], "Circ 0.4 (Tunnel 15)")
        self.assertEqual(predictability["stream_id"], 11302)
        self.assertEqual(predictability["actual_gap_ms"], 2200)
        self.assertEqual(predictability["selected_open_rows"], 1)
        self.assertEqual(predictability["selected_health_gap_ms"], 351)
        self.assertEqual(predictability["selected_health_score_bps"], 13125)
        self.assertEqual(predictability["selected_bad_health_rows"], 0)
        self.assertEqual(
            predictability["choice_hint"], "only selected open circuit logged"
        )
        self.assertEqual(
            predictability["predictability_hint"],
            "only selected open; later gap not predictable",
        )
        self.assertEqual(
            predictability["candidate_context"],
            "*0:Circ 0.4:a6:s13125.000:g351.000",
        )

        burst_rows = arti_one_eligible_open_circuit_burst_rows(payload)

        burst = next(
            row
            for row in burst_rows
            if row["profile"] == "arti_release_browser_healthaware_sameiso2"
        )
        self.assertEqual(
            burst["profile"], "arti_release_browser_healthaware_sameiso2"
        )
        self.assertEqual(burst["run_index"], 1)
        self.assertEqual(burst["one_candidate_exit_rows"], 1)
        self.assertEqual(burst["exit_open_rows"], 1)
        self.assertEqual(burst["max_selected_assigned_streams"], 6.0)
        self.assertEqual(burst["max_selected_active_streams"], 4.0)
        self.assertEqual(burst["max_open_total"], 3)
        self.assertEqual(burst["max_rejected_open"], 2)
        self.assertEqual(burst["max_isolation_rejects"], 2)
        self.assertEqual(burst["max_exit_unisolated"], 0)
        self.assertEqual(burst["max_exit_compatible_isolated"], 1)
        self.assertEqual(burst["max_exit_incompatible_isolated"], 2)
        self.assertEqual(burst["selected_circuits"], "Circ 0.4")
        self.assertEqual(
            burst["hint"], "other isolation groups own open circuits"
        )

    def test_browser_resource_queue_choice_class_summary_rows(self) -> None:
        base = int(parse_log_timestamp_ms("2026-06-06T23:12:37Z x") or 0)
        payload = {
            "targets": ["https://example.com/"],
            "profiles": {
                "arti_release_browser": {
                    "benchmarks": {
                        "https://example.com/": {
                            "runs": [
                                {
                                    "run_index": 1,
                                    "ok": True,
                                    "load_ms": 2000,
                                    "started_epoch_ms": base,
                                    "performance_timing": {
                                        "time_origin_ms": base,
                                        "navigation": {
                                            "responseStart": 100,
                                            "domContentLoadedEventEnd": 1500,
                                            "loadEventEnd": 2000,
                                        },
                                        "resources": [
                                            {
                                                "name": "https://example.com/r1.css",
                                                "initiatorType": "link",
                                                "nextHopProtocol": "http/1.1",
                                                "fetchStart": 0,
                                                "connectStart": 1200,
                                                "requestStart": 1200,
                                                "responseStart": 1300,
                                                "responseEnd": 1800,
                                                "duration": 1800,
                                            }
                                        ],
                                    },
                                    "proxy_signal_lines": [
                                        f"timing_id=7 target_kind=hostname port=443 conn_started_epoch_ms={base + 1200} circ_id=Circ 0.4 hop=3 stream_id=11302 elapsed_ms=0 torfast socks timing stream linked",
                                        f"timing_id=7 target_kind=hostname port=443 conn_started_epoch_ms={base + 1200} relay_ms=400 first_tor_to_client_ms=100 first_tor_to_client_epoch_ms={base + 1300} first_tor_to_client_write_ms=185 first_tor_to_client_write_epoch_ms={base + 1385} last_tor_to_client_ms=350 last_tor_to_client_epoch_ms={base + 1550} last_tor_to_client_write_ms=350 last_tor_to_client_write_epoch_ms={base + 1550} tor_to_client_bytes=4096 tor_to_client_write_bytes=4096 elapsed_ms=410 ok=true torfast socks timing relay finished",
                                        "2026-06-06T23:12:37Z DEBUG tor_circmgr::mgr: open_candidates=1 select_load_aware=true select_health_aware=true selected_candidate_index=0 selected_assigned_streams=6 selected_active_streams=4 selected_health_score_bps=13125 selected_has_bad_health=false select_max_active_streams=0 active_stream_cap_moved=false active_stream_cap_saturated=false candidate_assignment_summary=0:Circ~0.4:6 candidate_health_summary=0:Circ~0.4:4:12000:351:13125:1000:351 usage_kind=\"exit\" restrict_circ=true tunnel_unique_id=Circ 0.4 torfast circuit selection open",
                                    ],
                                }
                            ]
                        }
                    }
                }
            },
        }

        class_rows = browser_resource_queue_choice_class_summary_rows(payload)

        self.assertEqual(len(class_rows), 1)
        row = class_rows[0]
        self.assertEqual(row["profile"], "arti_release_browser")
        self.assertEqual(row["target"], "https://example.com/")
        self.assertEqual(row["choice_class"], "only selected open")
        self.assertEqual(row["rows"], 1)
        self.assertEqual(row["queued_1000ms"], 1)
        self.assertEqual(row["max_fetch_to_request_ms"], 1200)
        self.assertEqual(row["max_selected_assigned_streams"], 6)
        self.assertEqual(row["next_proof"], "same-isolation capacity timing")

    def test_browser_resource_queue_choice_class_marks_below_floor_health_alt(
        self,
    ) -> None:
        base = int(parse_log_timestamp_ms("2026-06-06T23:12:37Z x") or 0)
        payload = {
            "targets": ["https://example.com/"],
            "profiles": {
                "arti_release_browser_loadaware_healthyovercold0": {
                    "benchmarks": {
                        "https://example.com/": {
                            "runs": [
                                {
                                    "run_index": 1,
                                    "ok": True,
                                    "load_ms": 2000,
                                    "started_epoch_ms": base,
                                    "performance_timing": {
                                        "time_origin_ms": base,
                                        "navigation": {
                                            "responseStart": 100,
                                            "domContentLoadedEventEnd": 1500,
                                            "loadEventEnd": 2000,
                                        },
                                        "resources": [
                                            {
                                                "name": "https://example.com/r1.css",
                                                "initiatorType": "link",
                                                "nextHopProtocol": "http/1.1",
                                                "fetchStart": 0,
                                                "connectStart": 1200,
                                                "requestStart": 1200,
                                                "responseStart": 1300,
                                                "responseEnd": 1800,
                                                "duration": 1800,
                                            }
                                        ],
                                    },
                                    "proxy_signal_lines": [
                                        f"timing_id=7 target_kind=hostname port=443 conn_started_epoch_ms={base + 1200} circ_id=Circ 4.26 hop=3 stream_id=11302 elapsed_ms=0 torfast socks timing stream linked",
                                        f"timing_id=7 target_kind=hostname port=443 conn_started_epoch_ms={base + 1200} relay_ms=400 first_tor_to_client_ms=100 first_tor_to_client_epoch_ms={base + 1300} last_tor_to_client_ms=350 last_tor_to_client_epoch_ms={base + 1550} tor_to_client_bytes=4096 elapsed_ms=410 ok=true torfast socks timing relay finished",
                                        "2026-06-06T23:12:37Z INFO tor_circmgr::mgr: open_candidates=3 select_load_aware=true selected_candidate_index=0 selected_assigned_streams=0 selected_health_score_bps=0 selected_has_bad_health=false candidate_assignment_summary=0:Circ~4.26:0,1:Circ~4.30:1,2:Circ~4.42:0 candidate_health_summary=0:Circ~4.26:0:0:0:0:0:0:0:0:0,1:Circ~4.30:27:11760:444:14700:800:52:1:1:1500,2:Circ~4.42:0:0:0:0:0:0:0:0:0 usage_kind=\"exit\" restrict_circ=true tunnel_unique_id=Circ 4.26 torfast circuit selection open",
                                    ],
                                }
                            ]
                        }
                    }
                }
            },
        }

        selection_rows = browser_resource_queue_selection_context_rows(payload)
        self.assertEqual(len(selection_rows), 1)
        self.assertEqual(selection_rows[0]["better_health_alt_rows"], 1)
        self.assertEqual(selection_rows[0]["better_health_move_alt_rows"], 0)
        self.assertEqual(selection_rows[0]["below_floor_health_alt_rows"], 1)
        self.assertEqual(selection_rows[0]["max_alt_health_score_bps"], 14700.0)
        self.assertEqual(selection_rows[0]["health_min_move_score_bps"], 65536)

        class_rows = browser_resource_queue_choice_class_summary_rows(payload)
        self.assertEqual(len(class_rows), 1)
        row = class_rows[0]
        self.assertEqual(row["choice_class"], "below-floor health alternative")
        self.assertEqual(row["below_floor_health_alt_rows"], 1)
        self.assertEqual(row["max_alt_health_score_bps"], 14700.0)
        self.assertEqual(row["health_min_move_score_bps"], 65536)
        self.assertEqual(row["next_proof"], "stream gap proof")

    def test_selected_circuit_network_evidence_uses_direct_selection_context(
        self,
    ) -> None:
        base = int(parse_log_timestamp_ms("2026-06-06T23:12:37Z x") or 0)
        payload = {
            "targets": ["https://example.com/"],
            "profiles": {
                "arti_release_browser_loadaware": {
                    "benchmarks": {
                        "https://example.com/": {
                            "runs": [
                                {
                                    "run_index": 1,
                                    "ok": True,
                                    "proxy_signal_lines": [
                                        "2026-06-06T23:12:37Z INFO tor_circmgr::mgr: open_candidates=2 select_load_aware=true selected_candidate_index=0 candidate_assignment_summary=0:Circ~9.1:5,1:Circ~9.2:0 candidate_health_summary=0:Circ~9.1:1:100:500:100:1000:1,1:Circ~9.2:4:12000:20:120000:100:1 selected_assigned_streams=5 usage_kind=\"exit\" restrict_circ=true tunnel_unique_id=Circ 9.1 torfast circuit selection open",
                                        f"event_epoch_ms={base + 3000} circ_id=Circ 9.1 hop=#3 stream_id=2201 connected=false first_data_after_start_ms=100 transfer_ms=7000 idle_after_last_data_ms=2500 max_data_gap_ms=500 relay_data_bytes=100 data_cells=1 read_events=1 sendmes=0 sendme_ok=0 error_kind=not_connected returned_eof=false torfast stream receiver terminal summary",
                                    ],
                                    "performance_timing": {
                                        "time_origin_ms": base,
                                        "navigation": {
                                            "responseStart": 100,
                                            "domContentLoadedEventEnd": 600,
                                            "loadEventEnd": 900,
                                        },
                                        "resources": [],
                                    },
                                }
                            ]
                        }
                    }
                }
            },
        }

        rows = arti_selected_circuit_network_evidence_rows(payload)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["circuit"], "Circ 9.1")
        self.assertEqual(rows[0]["better_health_alt_rows"], 1)
        self.assertEqual(rows[0]["lower_assignment_alt_rows"], 1)
        self.assertIn("*0:Circ 9.1", rows[0]["candidate_context"])
        self.assertIn("1:Circ 9.2", rows[0]["candidate_context"])
        self.assertEqual(rows[0]["choice_hint"], "logged open alternative existed")

    def test_selected_circuit_network_evidence_uses_build_complete_context(
        self,
    ) -> None:
        base = int(parse_log_timestamp_ms("2026-06-06T23:12:37Z x") or 0)
        payload = {
            "targets": ["https://example.com/"],
            "profiles": {
                "arti_release_browser_loadaware": {
                    "benchmarks": {
                        "https://example.com/": {
                            "runs": [
                                {
                                    "run_index": 1,
                                    "ok": True,
                                    "proxy_signal_lines": [
                                        "2026-06-06T23:12:36Z INFO tor_circmgr::mgr: pending_id=0x9 pending_age_ms=540 usage_kind=exit tunnel_unique_id=Circ 9.3 torfast circuit selection build complete",
                                        f"event_epoch_ms={base + 3000} circ_id=Circ 9.3 hop=#3 stream_id=2202 connected=true first_data_after_start_ms=100 transfer_ms=7000 idle_after_last_data_ms=2500 max_data_gap_ms=500 relay_data_bytes=100 data_cells=1 read_events=1 sendmes=0 sendme_ok=0 error_kind=not_connected returned_eof=false torfast stream receiver terminal summary",
                                    ],
                                    "performance_timing": {
                                        "time_origin_ms": base,
                                        "navigation": {
                                            "responseStart": 100,
                                            "domContentLoadedEventEnd": 600,
                                            "loadEventEnd": 900,
                                        },
                                        "resources": [],
                                    },
                                }
                            ]
                        }
                    }
                }
            },
        }

        rows = arti_selected_circuit_network_evidence_rows(payload)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["circuit"], "Circ 9.3")
        self.assertEqual(
            rows[0]["candidate_context"], "build complete age=540.000ms usage=exit"
        )
        self.assertEqual(rows[0]["choice_hint"], "pending build context only")

    def test_selected_circuit_network_evidence_skips_recv_window_without_reads(
        self,
    ) -> None:
        base = int(parse_log_timestamp_ms("2026-06-06T23:12:37Z x") or 0)
        payload = {
            "targets": ["https://example.com/"],
            "profiles": {
                "arti_release_browser_sameiso2": {
                    "benchmarks": {
                        "https://example.com/": {
                            "runs": [
                                {
                                    "run_index": 1,
                                    "ok": False,
                                    "proxy_signal_lines": [
                                        f"event_epoch_ms={base + 3000} circ_id=Circ 9.4 (Tunnel 4) hop=#3 stream_id=2203 connected=false first_data_after_start_ms=0 transfer_ms=0 idle_after_last_data_ms=1500 max_data_gap_ms=0 relay_data_bytes=0 data_cells=0 read_events=0 sendmes=0 sendme_ok=0 min_recv_window_after_take=0 max_queued_after_bytes=0 error_kind=not_connected not_connected_source=receiver_err stream_close_cause=unknown returned_eof=false torfast stream receiver terminal summary",
                                    ],
                                    "performance_timing": {
                                        "time_origin_ms": base,
                                        "navigation": {
                                            "responseStart": 100,
                                            "domContentLoadedEventEnd": 600,
                                            "loadEventEnd": 900,
                                        },
                                        "resources": [],
                                    },
                                }
                            ]
                        }
                    }
                }
            },
        }

        rows = arti_selected_circuit_network_evidence_rows(payload)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["circuit"], "Circ 9.4 (Tunnel 4)")
        self.assertEqual(rows[0]["not_connected_sources"], "receiver_err:1")
        self.assertEqual(rows[0]["stream_close_causes"], "unknown:1")
        self.assertEqual(rows[0]["local_block_summary"], "local block not proved")

    def test_selected_circuit_network_evidence_marks_stream_target_closed_local(
        self,
    ) -> None:
        base = int(parse_log_timestamp_ms("2026-06-06T23:12:37Z x") or 0)
        payload = {
            "targets": ["https://example.com/"],
            "profiles": {
                "arti_release_browser_sameiso2": {
                    "benchmarks": {
                        "https://example.com/": {
                            "runs": [
                                {
                                    "run_index": 1,
                                    "ok": True,
                                    "proxy_signal_lines": [
                                        "timing_id=7 target_kind=hostname relay_ms=6200 circ_id=Circ 9.5 (Tunnel 5) stream_id=2204 ok=false copy_error_kind=not_connected torfast socks timing relay finished",
                                        f"event_epoch_ms={base + 2990} circ_id=Circ 9.5 (Tunnel 5) hop=#3 stream_id=2204 not_connected_source=receiver_none stream_close_cause=stream_target_closed queued_after_bytes=0 read_events=9 sendmes=0 sendme_ok=0 min_recv_window_after_take=491 max_queued_after_bytes=0 torfast stream receiver no-end close",
                                        f"event_epoch_ms={base + 3000} circ_id=Circ 9.5 (Tunnel 5) hop=#3 stream_id=2204 connected=true first_data_after_start_ms=200 transfer_ms=6000 idle_after_last_data_ms=1800 max_data_gap_ms=500 relay_data_bytes=4096 pending_after_bytes=0 user_read_bytes=4096 data_cells=9 read_events=9 sendmes=0 sendme_ok=0 min_recv_window_after_take=491 max_queued_after_bytes=0 error_kind=not_connected not_connected_source=receiver_err stream_close_cause=stream_target_closed returned_eof=false torfast stream receiver terminal summary",
                                    ],
                                    "performance_timing": {
                                        "time_origin_ms": base,
                                        "navigation": {
                                            "responseStart": 100,
                                            "domContentLoadedEventEnd": 600,
                                            "loadEventEnd": 900,
                                        },
                                        "resources": [],
                                    },
                                }
                            ]
                        }
                    }
                }
            },
        }

        rows = arti_selected_circuit_network_evidence_rows(payload)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["stream_close_causes"], "stream_target_closed:1")
        self.assertEqual(
            rows[0]["evidence_hint"], "local stream target closed after DATA idle"
        )

    def test_selected_circuit_network_evidence_marks_stream_specific_gap(
        self,
    ) -> None:
        base = int(parse_log_timestamp_ms("2026-06-06T23:12:37Z x") or 0)
        payload = {
            "targets": ["https://example.com/"],
            "profiles": {
                "arti_release_browser_sameiso2": {
                    "proxy_output_tail": [
                        f"timing_id=9 target_kind=hostname port=443 conn_started_epoch_ms={base + 100} circ_id=Circ 9.6 (Tunnel 6) hop=3 stream_id=2205 elapsed_ms=1 torfast socks timing stream linked",
                        f"timing_id=9 target_kind=hostname port=443 conn_started_epoch_ms={base + 100} relay_ms=6000 first_tor_to_client_ms=0 first_tor_to_client_epoch_ms={base + 100} last_tor_to_client_ms=5100 tor_to_client_bytes=1296 elapsed_ms=6100 ok=true torfast socks timing relay finished",
                        f"timing_id=10 target_kind=hostname port=443 conn_started_epoch_ms={base + 40} circ_id=Circ 9.6 (Tunnel 6) hop=3 stream_id=2301 elapsed_ms=1 torfast socks timing stream linked",
                        f"timing_id=10 target_kind=hostname port=443 conn_started_epoch_ms={base + 40} relay_ms=6000 first_tor_to_client_ms=0 first_tor_to_client_epoch_ms={base + 40} last_tor_to_client_ms=5960 tor_to_client_bytes=1296 elapsed_ms=6100 ok=true torfast socks timing relay finished",
                        f"timing_id=11 target_kind=hostname port=443 conn_started_epoch_ms={base + 50} circ_id=Circ 9.6 (Tunnel 6) hop=3 stream_id=2302 elapsed_ms=1 torfast socks timing stream linked",
                        f"timing_id=11 target_kind=hostname port=443 conn_started_epoch_ms={base + 50} relay_ms=6000 first_tor_to_client_ms=0 first_tor_to_client_epoch_ms={base + 50} last_tor_to_client_ms=5950 tor_to_client_bytes=1296 elapsed_ms=6100 ok=true torfast socks timing relay finished",
                        f"timing_id=12 target_kind=hostname port=443 conn_started_epoch_ms={base + 60} circ_id=Circ 9.6 (Tunnel 6) hop=3 stream_id=2303 elapsed_ms=1 torfast socks timing stream linked",
                        f"timing_id=12 target_kind=hostname port=443 conn_started_epoch_ms={base + 60} relay_ms=6000 first_tor_to_client_ms=0 first_tor_to_client_epoch_ms={base + 60} last_tor_to_client_ms=5940 tor_to_client_bytes=1296 elapsed_ms=6100 ok=true torfast socks timing relay finished",
                        f"timing_id=13 target_kind=hostname port=443 conn_started_epoch_ms={base + 70} circ_id=Circ 9.6 (Tunnel 6) hop=3 stream_id=2304 elapsed_ms=1 torfast socks timing stream linked",
                        f"timing_id=13 target_kind=hostname port=443 conn_started_epoch_ms={base + 70} relay_ms=6000 first_tor_to_client_ms=0 first_tor_to_client_epoch_ms={base + 70} last_tor_to_client_ms=5930 tor_to_client_bytes=1296 elapsed_ms=6100 ok=true torfast socks timing relay finished",
                        f"timing_id=14 target_kind=hostname port=443 conn_started_epoch_ms={base + 80} circ_id=Circ 9.6 (Tunnel 6) hop=3 stream_id=2305 elapsed_ms=1 torfast socks timing stream linked",
                        f"timing_id=14 target_kind=hostname port=443 conn_started_epoch_ms={base + 80} relay_ms=6000 first_tor_to_client_ms=0 first_tor_to_client_epoch_ms={base + 80} last_tor_to_client_ms=5920 tor_to_client_bytes=1296 elapsed_ms=6100 ok=true torfast socks timing relay finished",
                        f"event_epoch_ms={base + 40} circ_id=Circ 9.6 (Tunnel 6) hop=Some(3) stream_id=2301 relay_cmd=RelayCmd(DATA) data_len=498 queued_before_bytes=0 queued_after_bytes=498 closes_stream=false torfast relay receive delivered",
                        f"event_epoch_ms={base + 50} circ_id=Circ 9.6 (Tunnel 6) hop=Some(3) stream_id=2302 relay_cmd=RelayCmd(DATA) data_len=498 queued_before_bytes=0 queued_after_bytes=498 closes_stream=false torfast relay receive delivered",
                        f"event_epoch_ms={base + 60} circ_id=Circ 9.6 (Tunnel 6) hop=Some(3) stream_id=2303 relay_cmd=RelayCmd(DATA) data_len=498 queued_before_bytes=0 queued_after_bytes=498 closes_stream=false torfast relay receive delivered",
                        f"event_epoch_ms={base + 70} circ_id=Circ 9.6 (Tunnel 6) hop=Some(3) stream_id=2304 relay_cmd=RelayCmd(DATA) data_len=498 queued_before_bytes=0 queued_after_bytes=498 closes_stream=false torfast relay receive delivered",
                        f"event_epoch_ms={base + 80} circ_id=Circ 9.6 (Tunnel 6) hop=Some(3) stream_id=2305 relay_cmd=RelayCmd(DATA) data_len=498 queued_before_bytes=0 queued_after_bytes=498 closes_stream=false torfast relay receive delivered",
                        f"event_epoch_ms={base + 100} circ_id=Circ 9.6 (Tunnel 6) hop=Some(3) stream_id=2205 relay_cmd=RelayCmd(DATA) data_len=498 queued_before_bytes=0 queued_after_bytes=498 closes_stream=false torfast relay receive delivered",
                        f"event_epoch_ms={base + 2000} circ_id=Circ 9.6 (Tunnel 6) hop=Some(3) stream_id=2206 relay_cmd=RelayCmd(DATA) data_len=498 queued_before_bytes=0 queued_after_bytes=498 closes_stream=false torfast relay receive delivered",
                        f"event_epoch_ms={base + 5100} circ_id=Circ 9.6 (Tunnel 6) hop=Some(3) stream_id=2205 relay_cmd=RelayCmd(DATA) data_len=300 queued_before_bytes=0 queued_after_bytes=300 closes_stream=false torfast relay receive delivered",
                    ],
                    "benchmarks": {
                        "https://example.com/": {
                            "runs": [
                                {
                                    "run_index": 1,
                                    "ok": True,
                                    "proxy_signal_lines": [
                                        f"event_epoch_ms={base + 5200} circ_id=Circ 9.6 (Tunnel 6) hop=#3 stream_id=2205 connected=true first_data_after_start_ms=100 transfer_ms=6000 idle_after_last_data_ms=1500 max_data_gap_ms=5000 relay_data_bytes=1296 pending_after_bytes=0 user_read_bytes=1296 data_cells=3 read_events=3 sendmes=0 sendme_ok=0 min_recv_window_after_take=491 max_queued_after_bytes=498 error_kind=not_connected not_connected_source=receiver_err stream_close_cause=unknown returned_eof=false torfast stream receiver terminal summary",
                                    ],
                                    "performance_timing": {
                                        "time_origin_ms": base,
                                        "navigation": {
                                            "responseStart": 100,
                                            "domContentLoadedEventEnd": 600,
                                            "loadEventEnd": 7000,
                                        },
                                        "resources": [
                                            {
                                                "name": "https://example.com/slow.css",
                                                "initiatorType": "link",
                                                "startTime": 0,
                                                "connectStart": 100,
                                                "fetchStart": 0,
                                                "requestStart": 100,
                                                "responseStart": 200,
                                                "responseEnd": 6000,
                                                "duration": 6000,
                                                "nextHopProtocol": "http/1.1",
                                            },
                                            {
                                                "name": "https://example.com/blocker-1.js",
                                                "initiatorType": "script",
                                                "startTime": 0,
                                                "fetchStart": 0,
                                                "requestStart": 40,
                                                "responseStart": 200,
                                                "responseEnd": 6000,
                                                "duration": 6000,
                                                "nextHopProtocol": "http/1.1",
                                            },
                                            {
                                                "name": "https://example.com/blocker-2.js",
                                                "initiatorType": "script",
                                                "startTime": 0,
                                                "fetchStart": 0,
                                                "requestStart": 50,
                                                "responseStart": 200,
                                                "responseEnd": 6000,
                                                "duration": 6000,
                                                "nextHopProtocol": "http/1.1",
                                            },
                                            {
                                                "name": "https://example.com/blocker-3.js",
                                                "initiatorType": "script",
                                                "startTime": 0,
                                                "fetchStart": 0,
                                                "requestStart": 60,
                                                "responseStart": 200,
                                                "responseEnd": 6000,
                                                "duration": 6000,
                                                "nextHopProtocol": "http/1.1",
                                            },
                                            {
                                                "name": "https://example.com/blocker-4.js",
                                                "initiatorType": "script",
                                                "startTime": 0,
                                                "fetchStart": 0,
                                                "requestStart": 70,
                                                "responseStart": 200,
                                                "responseEnd": 6000,
                                                "duration": 6000,
                                                "nextHopProtocol": "http/1.1",
                                            },
                                            {
                                                "name": "https://example.com/blocker-5.js",
                                                "initiatorType": "script",
                                                "startTime": 0,
                                                "fetchStart": 0,
                                                "requestStart": 80,
                                                "responseStart": 200,
                                                "responseEnd": 6000,
                                                "duration": 6000,
                                                "nextHopProtocol": "http/1.1",
                                            },
                                        ],
                                    },
                                }
                            ]
                        }
                    },
                }
            },
        }

        rows = arti_selected_circuit_network_evidence_rows(payload)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["circuit"], "Circ 9.6 (Tunnel 6)")
        self.assertEqual(rows[0]["max_data_gap_ms"], 5000)
        self.assertEqual(rows[0]["max_circuit_data_gap_ms"], 3100)
        self.assertEqual(
            rows[0]["data_gap_scope_hint"],
            "stream-specific gap; circuit still active",
        )

        cross_rows = arti_selected_stream_gap_cross_activity_rows(payload)

        self.assertEqual(len(cross_rows), 1)
        self.assertEqual(cross_rows[0]["stream_id"], 2205)
        self.assertEqual(cross_rows[0]["actual_gap_ms"], 5000)
        self.assertEqual(cross_rows[0]["same_circuit_other_data_cells"], 1)
        self.assertEqual(cross_rows[0]["same_circuit_other_streams"], 1)
        self.assertEqual(cross_rows[0]["top_other_stream_id"], 2206)
        self.assertEqual(
            cross_rows[0]["cross_stream_evidence_hint"],
            "other streams active on same circuit",
        )

        resource_rows = arti_selected_stream_gap_resource_overlap_rows(payload)

        self.assertEqual(len(resource_rows), 1)
        self.assertEqual(resource_rows[0]["stream_id"], 2205)
        self.assertEqual(resource_rows[0]["same_stream_resources"], 1)
        self.assertEqual(resource_rows[0]["high_confidence_resources"], 1)
        self.assertEqual(resource_rows[0]["active_overlap_resources"], 1)
        self.assertEqual(resource_rows[0]["response_receive_overlap_ms"], 4900)
        self.assertEqual(
            resource_rows[0]["resource_overlap_hint"],
            "gap overlaps response receive",
        )

        slot_rows = arti_selected_stream_gap_slot_pressure_rows(payload)

        self.assertEqual(len(slot_rows), 1)
        self.assertEqual(slot_rows[0]["stream_id"], 2205)
        self.assertEqual(slot_rows[0]["protocol"], "http/1.1")
        self.assertEqual(slot_rows[0]["matched_active_overlap_ms"], 5000)
        self.assertEqual(slot_rows[0]["matched_top_phase"], "response_receive")
        self.assertEqual(slot_rows[0]["same_origin_active_at_gap_start"], 6)
        self.assertEqual(slot_rows[0]["max_same_origin_active_in_gap"], 6)
        self.assertEqual(slot_rows[0]["same_origin_active_resources_in_gap"], 6)
        self.assertEqual(slot_rows[0]["joined_active_resources"], 6)
        self.assertEqual(slot_rows[0]["joined_match_confidences"], "high:6")
        self.assertEqual(slot_rows[0]["high_conf_joined_active_resources"], 6)
        self.assertIn("2205", slot_rows[0]["high_conf_active_stream_ids"])
        self.assertEqual(slot_rows[0]["high_conf_relay_cells_after_gap_start"], 2)
        self.assertEqual(
            slot_rows[0]["slot_pressure_hint"],
            "HTTP/1.1 saturated while stream gap ran",
        )

    def test_selected_stream_slot_pressure_hint_does_not_overclaim_inactive_match(
        self,
    ) -> None:
        row = {
            "matched_resource": "https://example.com/",
            "matched_active_overlap_ms": 0,
            "protocol": "http/1.1",
            "max_same_origin_active_in_gap": 6,
            "same_origin_active_resources_in_gap": 11,
            "same_origin_queued_1000_resources_in_gap": 7,
            "matched_fetch_to_request_overlap_ms": 0,
        }

        self.assertEqual(
            selected_stream_gap_slot_pressure_hint(row),
            "same-origin slots busy; matched resource inactive",
        )

    def test_resource_stream_gap_context_rows_show_browser_phase_overlap(
        self,
    ) -> None:
        base = int(parse_log_timestamp_ms("2026-06-06T23:12:37Z x") or 0)
        payload = {
            "profiles": {
                "arti_release_browser": {
                    "proxy_output_tail": [
                        f"timing_id=7 target_kind=hostname port=443 conn_started_epoch_ms={base + 105} circ_id=Circ 0.4 hop=3 stream_id=11302 elapsed_ms=122 torfast socks timing stream linked",
                        f"timing_id=7 target_kind=hostname port=443 conn_started_epoch_ms={base + 105} relay_ms=5200 first_tor_to_client_ms=145 first_tor_to_client_epoch_ms={base + 250} elapsed_ms=5222 ok=true torfast socks timing relay finished",
                        f"event_epoch_ms={base + 300} circ_id=Circ 0.4 (Tunnel 15) hop=Some(HopNum(3)) stream_id=11302 relay_cmd=RelayCmd(DATA) data_len=498 queued_before_bytes=0 queued_after_bytes=498 closes_stream=false torfast relay receive delivered",
                        f"timing_id=7 target_kind=hostname direction=client_to_tor event_index=1 elapsed_ms=1000 event_epoch_ms={base + 1000} read_bytes=40 cumulative_bytes=40 torfast socks byte event",
                        f"timing_id=7 target_kind=hostname direction=client_to_tor_write event_index=1 elapsed_ms=1001 event_epoch_ms={base + 1001} write_bytes=40 cumulative_bytes=40 torfast socks byte event",
                        f"event_epoch_ms={base + 1300} circ_id=Circ 0.4 (Tunnel 15) hop=Some(HopNum(3)) stream_id=99123 relay_cmd=RelayCmd(DATA) data_len=256 queued_before_bytes=0 queued_after_bytes=256 closes_stream=false torfast relay receive delivered",
                        f"event_epoch_ms={base + 2300} circ_id=Circ 0.4 (Tunnel 15) hop=Some(HopNum(3)) stream_id=11302 relay_cmd=RelayCmd(DATA) data_len=498 queued_before_bytes=0 queued_after_bytes=498 closes_stream=false torfast relay receive delivered",
                    ],
                    "benchmarks": {
                        "https://example.com/": {
                            "runs": [
                                {
                                    "run_index": 1,
                                    "ok": True,
                                    "performance_timing": {
                                        "time_origin_ms": base,
                                        "navigation": {"loadEventEnd": 4000},
                                        "resources": [
                                            {
                                                "name": "https://example.com/app.css",
                                                "initiatorType": "link",
                                                "startTime": 100,
                                                "fetchStart": 100,
                                                "connectStart": 100,
                                                "requestStart": 200,
                                                "responseStart": 2500,
                                                "responseEnd": 2800,
                                                "duration": 2700,
                                                "encodedBodySize": 498,
                                            }
                                        ],
                                    },
                                }
                            ]
                        }
                    },
                }
            }
        }

        rows = browser_resource_stream_gap_context_rows(payload)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["timing_id"], 7)
        self.assertEqual(rows[0]["gap_ms"], 2000)
        self.assertEqual(rows[0]["gap_start_ms"], 300)
        self.assertEqual(rows[0]["gap_end_ms"], 2300)
        self.assertEqual(rows[0]["same_circuit_other_data_cells"], 1)
        self.assertEqual(rows[0]["same_circuit_other_streams"], 1)
        self.assertEqual(rows[0]["same_circuit_other_data_kib"], 0.25)
        self.assertEqual(rows[0]["max_circuit_data_gap_during_stream_gap_ms"], 1000)
        self.assertEqual(
            rows[0]["gap_scope_hint"],
            "stream-specific gap; circuit still active",
        )
        self.assertEqual(rows[0]["same_stream_resources"], 1)
        self.assertEqual(rows[0]["high_confidence_resources"], 1)
        self.assertEqual(rows[0]["slow_resources_2s"], 1)
        self.assertEqual(rows[0]["request_wait_overlap_resources"], 1)
        self.assertEqual(rows[0]["response_receive_overlap_resources"], 0)
        self.assertEqual(rows[0]["request_wait_overlap_ms"], 2000)
        self.assertEqual(rows[0]["response_receive_overlap_ms"], 0)
        self.assertEqual(rows[0]["top_overlap_resource"], "https://example.com/app.css")
        self.assertEqual(rows[0]["top_overlap_ms"], 2000)
        self.assertEqual(rows[0]["top_overlap_phase"], "request_wait")

        summary_rows = browser_resource_stream_gap_phase_summary_rows(payload)

        self.assertEqual(len(summary_rows), 1)
        self.assertEqual(summary_rows[0]["profile"], "arti_release_browser")
        self.assertEqual(summary_rows[0]["target"], "https://example.com/")
        self.assertEqual(summary_rows[0]["run_index"], 1)
        self.assertEqual(summary_rows[0]["gaps"], 1)
        self.assertEqual(summary_rows[0]["gaps_1s"], 1)
        self.assertEqual(summary_rows[0]["matched_gaps"], 1)
        self.assertEqual(summary_rows[0]["dominant_phase"], "request_wait")
        self.assertEqual(summary_rows[0]["request_wait_overlap_ms"], 2000)
        self.assertEqual(summary_rows[0]["unmatched_gap_ms"], 0)
        self.assertEqual(summary_rows[0]["max_gap_ms"], 2000)
        self.assertEqual(summary_rows[0]["top_overlap_resources"], "example.com/app.css")

        byte_rows = browser_resource_stream_gap_byte_context_rows(payload)

        self.assertEqual(len(byte_rows), 1)
        self.assertEqual(byte_rows[0]["timing_id"], 7)
        self.assertEqual(byte_rows[0]["client_events_in_gap"], 1)
        self.assertEqual(byte_rows[0]["client_bytes_in_gap"], 40)
        self.assertEqual(byte_rows[0]["client_events_on_gap_edges"], 0)
        self.assertEqual(byte_rows[0]["client_bytes_on_gap_edges"], 0)
        self.assertEqual(byte_rows[0]["client_write_events_in_gap"], 1)
        self.assertEqual(byte_rows[0]["client_write_bytes_in_gap"], 40)
        self.assertEqual(byte_rows[0]["client_write_events_on_gap_edges"], 0)
        self.assertEqual(byte_rows[0]["client_write_bytes_on_gap_edges"], 0)
        self.assertEqual(byte_rows[0]["first_client_in_gap_ms"], 1000)
        self.assertEqual(byte_rows[0]["last_client_in_gap_ms"], 1000)
        self.assertEqual(byte_rows[0]["gap_end_after_last_client_ms"], 1300)
        self.assertEqual(byte_rows[0]["last_client_cumulative_bytes"], 40)
        self.assertEqual(byte_rows[0]["tor_events_in_gap"], 0)
        self.assertEqual(byte_rows[0]["tor_bytes_in_gap"], 0)

    def test_arti_profile_top_resource_relay_ab_rows_add_join_context(self) -> None:
        base = int(parse_log_timestamp_ms("2026-06-06T23:12:37Z x") or 0)
        target = "https://example.com/"
        payload = {
            "targets": [target],
            "profiles": {
                "arti_release_browser": {
                    "proxy_output_tail": [
                        f"timing_id=7 target_kind=hostname port=443 conn_started_epoch_ms={base + 100} circ_id=Circ 0.4 hop=3 stream_id=11302 elapsed_ms=120 torfast socks timing stream linked",
                        f"timing_id=7 target_kind=hostname port=443 conn_started_epoch_ms={base + 100} relay_ms=700 tor_to_client_bytes=3400 elapsed_ms=820 ok=true torfast socks timing relay finished",
                        f"event_epoch_ms={base + 250} circ_id=Circ 0.4 (Tunnel 15) hop=Some(HopNum(3)) stream_id=11302 relay_cmd=RelayCmd(DATA) data_len=498 queued_before_bytes=0 queued_after_bytes=498 closes_stream=false torfast relay receive delivered",
                        f"event_epoch_ms={base + 300} circ_id=Circ 0.4 (Tunnel 15) hop=Some(HopNum(3)) stream_id=11302 relay_cmd=RelayCmd(DATA) data_len=200 queued_before_bytes=498 queued_after_bytes=698 closes_stream=false torfast relay receive delivered",
                    ],
                    "benchmarks": {
                        target: {
                            "runs": [
                                {
                                    "run_index": 1,
                                    "ok": True,
                                    "load_ms": 1000,
                                    "elapsed_ms": 1200,
                                    "performance_timing": {
                                        "time_origin_ms": base,
                                        "navigation": {
                                            "responseStart": 100,
                                            "domContentLoadedEventEnd": 300,
                                            "loadEventEnd": 1000,
                                        },
                                        "resources": [
                                            {
                                                "name": "https://example.com/app.css",
                                                "initiatorType": "link",
                                                "connectStart": 100,
                                                "duration": 300,
                                                "requestStart": 120,
                                                "responseStart": 220,
                                                "responseEnd": 400,
                                                "encodedBodySize": 498,
                                            }
                                        ],
                                    },
                                }
                            ]
                        }
                    },
                },
                "arti_release_browser_pending500ms": {
                    "proxy_output_tail": [
                        f"timing_id=8 target_kind=hostname port=443 conn_started_epoch_ms={base + 105} circ_id=Circ 0.5 hop=3 stream_id=11303 elapsed_ms=120 torfast socks timing stream linked",
                        f"timing_id=8 target_kind=hostname port=443 conn_started_epoch_ms={base + 105} relay_ms=1000 tor_to_client_bytes=3600 elapsed_ms=1120 ok=true torfast socks timing relay finished",
                        f"event_epoch_ms={base + 260} circ_id=Circ 0.5 (Tunnel 16) hop=Some(HopNum(3)) stream_id=11303 relay_cmd=RelayCmd(DATA) data_len=498 queued_before_bytes=0 queued_after_bytes=498 closes_stream=false torfast relay receive delivered",
                        f"event_epoch_ms={base + 460} circ_id=Circ 0.5 (Tunnel 16) hop=Some(HopNum(3)) stream_id=11303 relay_cmd=RelayCmd(DATA) data_len=200 queued_before_bytes=498 queued_after_bytes=698 closes_stream=false torfast relay receive delivered",
                    ],
                    "benchmarks": {
                        target: {
                            "runs": [
                                {
                                    "run_index": 1,
                                    "ok": True,
                                    "load_ms": 1100,
                                    "elapsed_ms": 1300,
                                    "performance_timing": {
                                        "time_origin_ms": base,
                                        "navigation": {
                                            "responseStart": 110,
                                            "domContentLoadedEventEnd": 350,
                                            "loadEventEnd": 1100,
                                        },
                                        "resources": [
                                            {
                                                "name": "https://example.com/app.css",
                                                "initiatorType": "link",
                                                "connectStart": 100,
                                                "duration": 500,
                                                "requestStart": 120,
                                                "responseStart": 420,
                                                "responseEnd": 620,
                                                "encodedBodySize": 498,
                                            }
                                        ],
                                    },
                                }
                            ]
                        }
                    },
                },
            },
        }

        rows = arti_profile_top_resource_relay_ab_rows(payload)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["resource"], "https://example.com/app.css")
        self.assertEqual(rows[0]["duration_delta_ms"], 200.0)
        self.assertEqual(rows[0]["tail_after_dom_delta_ms"], 170.0)
        self.assertEqual(rows[0]["relay_delta_ms"], 300.0)
        self.assertEqual(rows[0]["max_gap_delta_ms"], 150.0)
        self.assertEqual(rows[0]["candidate_high_confidence"], 1)
        self.assertEqual(rows[0]["baseline_high_confidence"], 1)
        self.assertEqual(rows[0]["candidate_timing_id"], 8)
        self.assertEqual(rows[0]["baseline_timing_id"], 7)

    def test_arti_profile_resource_http_phase_ab_rows_split_resource_wait(self) -> None:
        target = "https://example.com/"
        payload = {
            "targets": [target],
            "profiles": {
                "arti_release_browser": {
                    "benchmarks": {
                        target: {
                            "runs": [
                                {
                                    "run_index": 1,
                                    "ok": True,
                                    "load_ms": 500,
                                    "elapsed_ms": 600,
                                    "performance_timing": {
                                        "navigation": {
                                            "responseStart": 100,
                                            "domContentLoadedEventEnd": 300,
                                            "loadEventEnd": 500,
                                        },
                                        "resources": [
                                            {
                                                "name": "https://example.com/app.js",
                                                "initiatorType": "script",
                                                "nextHopProtocol": "http/1.1",
                                                "fetchStart": 100,
                                                "connectStart": 100,
                                                "connectEnd": 150,
                                                "requestStart": 200,
                                                "responseStart": 300,
                                                "responseEnd": 400,
                                                "duration": 300,
                                            }
                                        ],
                                    },
                                }
                            ]
                        }
                    }
                },
                "arti_release_browser_pending500ms": {
                    "benchmarks": {
                        target: {
                            "runs": [
                                {
                                    "run_index": 1,
                                    "ok": True,
                                    "load_ms": 700,
                                    "elapsed_ms": 800,
                                    "performance_timing": {
                                        "navigation": {
                                            "responseStart": 100,
                                            "domContentLoadedEventEnd": 500,
                                            "loadEventEnd": 700,
                                        },
                                        "resources": [
                                            {
                                                "name": "https://example.com/app.js",
                                                "initiatorType": "script",
                                                "nextHopProtocol": "http/1.1",
                                                "fetchStart": 100,
                                                "connectStart": 100,
                                                "connectEnd": 100,
                                                "requestStart": 400,
                                                "responseStart": 550,
                                                "responseEnd": 600,
                                                "duration": 500,
                                            }
                                        ],
                                    },
                                }
                            ]
                        }
                    }
                },
            },
        }

        rows = arti_profile_resource_http_phase_ab_rows(payload)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["resource"], "https://example.com/app.js")
        self.assertEqual(rows[0]["duration_delta_ms"], 200.0)
        self.assertEqual(rows[0]["fetch_to_request_delta_ms"], 200.0)
        self.assertEqual(rows[0]["request_wait_delta_ms"], 50.0)
        self.assertEqual(rows[0]["receive_delta_ms"], -50.0)
        self.assertEqual(rows[0]["fetch_to_response_delta_ms"], 250.0)
        self.assertEqual(rows[0]["candidate_zero_connect_setup"], 1)
        self.assertEqual(rows[0]["baseline_zero_connect_setup"], 0)
        self.assertEqual(rows[0]["candidate_protocol_summary"], "http/1.1:1")

    def test_arti_profile_http_queue_shape_ab_rows_compare_protocol_queue(self) -> None:
        target = "https://example.com/"
        payload = {
            "targets": [target],
            "profiles": {
                "arti_release_browser": {
                    "benchmarks": {
                        target: {
                            "runs": [
                                {
                                    "run_index": 1,
                                    "ok": True,
                                    "load_ms": 500,
                                    "elapsed_ms": 600,
                                    "performance_timing": {
                                        "navigation": {
                                            "responseStart": 100,
                                            "domContentLoadedEventEnd": 300,
                                            "loadEventEnd": 500,
                                        },
                                        "resources": [
                                            {
                                                "name": "https://example.com/a.js",
                                                "nextHopProtocol": "http/1.1",
                                                "fetchStart": 100,
                                                "connectStart": 100,
                                                "connectEnd": 100,
                                                "requestStart": 150,
                                                "responseStart": 250,
                                                "responseEnd": 300,
                                            },
                                            {
                                                "name": "https://example.com/b.js",
                                                "nextHopProtocol": "http/1.1",
                                                "fetchStart": 100,
                                                "connectStart": 100,
                                                "connectEnd": 150,
                                                "requestStart": 200,
                                                "responseStart": 300,
                                                "responseEnd": 400,
                                            },
                                        ],
                                    },
                                }
                            ]
                        }
                    }
                },
                "arti_release_browser_pending500ms": {
                    "benchmarks": {
                        target: {
                            "runs": [
                                {
                                    "run_index": 1,
                                    "ok": True,
                                    "load_ms": 700,
                                    "elapsed_ms": 800,
                                    "performance_timing": {
                                        "navigation": {
                                            "responseStart": 100,
                                            "domContentLoadedEventEnd": 500,
                                            "loadEventEnd": 700,
                                        },
                                        "resources": [
                                            {
                                                "name": "https://example.com/a.js",
                                                "nextHopProtocol": "http/1.1",
                                                "fetchStart": 100,
                                                "connectStart": 100,
                                                "connectEnd": 100,
                                                "requestStart": 400,
                                                "responseStart": 550,
                                                "responseEnd": 600,
                                            },
                                            {
                                                "name": "https://example.com/b.js",
                                                "nextHopProtocol": "http/1.1",
                                                "fetchStart": 100,
                                                "connectStart": 100,
                                                "connectEnd": 100,
                                                "requestStart": 700,
                                                "responseStart": 800,
                                                "responseEnd": 900,
                                            },
                                        ],
                                    },
                                }
                            ]
                        }
                    }
                },
            },
        }

        rows = arti_profile_http_queue_shape_ab_rows(payload)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["protocol"], "http/1.1")
        self.assertEqual(rows[0]["candidate_count"], 2)
        self.assertEqual(rows[0]["baseline_count"], 2)
        self.assertEqual(rows[0]["candidate_zero_connect_setup"], 2)
        self.assertEqual(rows[0]["baseline_zero_connect_setup"], 1)
        self.assertEqual(rows[0]["candidate_fetch_to_request_100ms"], 2)
        self.assertEqual(rows[0]["baseline_fetch_to_request_100ms"], 1)
        self.assertEqual(rows[0]["candidate_fetch_to_request_500ms"], 1)
        self.assertEqual(rows[0]["baseline_fetch_to_request_500ms"], 0)
        self.assertEqual(rows[0]["median_fetch_to_request_delta_ms"], 375.0)
        self.assertEqual(rows[0]["max_fetch_to_request_delta_ms"], 500.0)
        self.assertEqual(rows[0]["median_request_wait_delta_ms"], 25.0)
        self.assertEqual(rows[0]["median_receive_delta_ms"], 0.0)

    def test_maps_browser_navigation_to_nearest_socks_stream(self) -> None:
        payload = {
            "profiles": {
                "arti_release_browser": {
                    "proxy_signal_lines": [
                        'timing_id=7 target_kind="hostname" command=CONNECT port=443 conn_started_epoch_ms=1105 elapsed_ms=0 torfast socks timing request parsed',
                        'timing_id=7 target_kind="hostname" port=443 conn_started_epoch_ms=1105 connect_ms=200 elapsed_ms=200 torfast socks timing stream ready',
                        'timing_id=7 target_kind="hostname" port=443 conn_started_epoch_ms=1105 circ_id=Circ 0.4 (Tunnel 15) hop=3 stream_id=11302 elapsed_ms=201 torfast socks timing stream linked',
                        'timing_id=7 target_kind="hostname" port=443 conn_started_epoch_ms=1105 elapsed_ms=210 torfast socks timing socks reply sent',
                        'timing_id=7 target_kind="hostname" port=443 conn_started_epoch_ms=1105 relay_ms=900 elapsed_ms=1200 first_tor_to_client_ms=360 first_tor_to_client_epoch_ms=1465 tor_to_client_bytes=4096 ok=true torfast socks timing relay finished',
                        'timing_id=9 target_kind="hostname" command=CONNECT port=443 conn_started_epoch_ms=2200 elapsed_ms=0 torfast socks timing request parsed',
                    ],
                    "benchmarks": {
                        "https://example.com/": {
                            "runs": [
                                {
                                    "ok": True,
                                    "run_index": 1,
                                    "load_ms": 700,
                                    "performance_timing": {
                                        "time_origin_ms": 1000,
                                        "navigation": {
                                            "name": "https://example.com/",
                                            "initiatorType": "navigation",
                                            "startTime": 0,
                                            "fetchStart": 0,
                                            "connectStart": 100,
                                            "requestStart": 200,
                                            "responseStart": 500,
                                            "responseEnd": 650,
                                            "duration": 700,
                                            "encodedBodySize": 1234,
                                            "loadEventEnd": 700,
                                        },
                                    },
                                }
                            ]
                        }
                    },
                }
            }
        }

        rows = browser_navigation_socks_join_rows(payload)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["match_field"], "connectStart")
        self.assertEqual(rows[0]["match_delta_ms"], 5.0)
        self.assertEqual(rows[0]["match_confidence"], "high")
        self.assertEqual(rows[0]["timing_id"], 7)
        self.assertEqual(rows[0]["connect_ms"], 200)
        self.assertEqual(rows[0]["reply_elapsed_ms"], 210)
        self.assertEqual(rows[0]["first_tor_to_client_ms"], 360)
        self.assertEqual(rows[0]["first_tor_byte_to_response_ms"], 35.0)
        self.assertEqual(rows[0]["response_after_reply_ms"], 185.0)
        self.assertEqual(rows[0]["circ_id"], "Circ 0.4 (Tunnel 15)")
        self.assertEqual(rows[0]["stream_id"], 11302)
        self.assertEqual(rows[0]["resource_type"], "navigation")
        self.assertEqual(rows[0]["fetch_to_request_ms"], 200.0)
        self.assertEqual(rows[0]["wait_ms"], 300.0)
        self.assertEqual(rows[0]["receive_ms"], 150.0)

    def test_finds_slow_torfast_socks_rows(self) -> None:
        timings = parse_torfast_socks_timings(
            [
                "timing_id=1 command=CONNECT port=443 elapsed_ms=1 torfast socks timing request parsed",
                "timing_id=1 port=443 connect_ms=50 elapsed_ms=51 torfast socks timing stream ready",
                "timing_id=1 port=443 relay_ms=300 elapsed_ms=351 ok=true torfast socks timing relay finished",
                "timing_id=2 command=CONNECT port=443 elapsed_ms=1 torfast socks timing request parsed",
                "timing_id=2 port=443 connect_ms=5000 elapsed_ms=5001 torfast socks timing stream ready",
                "timing_id=2 port=443 relay_ms=275 elapsed_ms=5276 ok=true torfast socks timing relay finished",
                "timing_id=3 command=CONNECT port=443 elapsed_ms=1 torfast socks timing request parsed",
                "timing_id=3 port=443 connect_ms=0 elapsed_ms=1 torfast socks timing stream ready",
                "timing_id=3 port=443 relay_ms=7024 elapsed_ms=7025 ok=true torfast socks timing relay finished",
            ]
        )

        rows = torfast_slow_socks_rows(timings)

        self.assertEqual([row["timing_id"] for row in rows], [3, 2])
        self.assertEqual(rows[0]["relay_ms"], 7024)
        self.assertEqual(rows[1]["connect_ms"], 5000)

    def test_finds_unfinished_torfast_socks_rows(self) -> None:
        timings = parse_torfast_socks_timings(
            [
                "timing_id=3 command=CONNECT port=443 elapsed_ms=0 torfast socks timing request parsed",
                "timing_id=4 command=CONNECT port=443 elapsed_ms=0 torfast socks timing request parsed",
                "timing_id=4 port=443 connect_ms=0 elapsed_ms=0 torfast socks timing stream ready",
            ]
        )

        rows = torfast_unfinished_socks_rows(timings)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["timing_id"], 3)
        self.assertEqual(rows[0]["command"], "CONNECT")

    def test_parses_torfast_hspool_timings(self) -> None:
        timings = parse_torfast_hspool_timings(
            [
                "kind=GUARDED torfast hspool on-demand launch started",
                "kind=GUARDED launch_ms=783 torfast hspool on-demand circuit ready",
                "kind=NAIVE launch_ms=831 torfast hspool background circuit ready",
                "kind=GUARDED torfast hspool reused stem circuit",
                "kind=ClientIntro stem_kind=GUARDED source=pool elapsed_ms=12 torfast hspool timing stem ready",
                "kind=ClientIntro stem_kind=GUARDED source=on_demand elapsed_ms=900 torfast hspool timing stem failed",
                "kind=ClientIntro stem_kind=GUARDED elapsed_ms=13 torfast hspool timing stem selected",
                "kind=ClientIntro stem_kind=GUARDED extend_ms=44 elapsed_ms=57 torfast hspool timing specific circuit ready",
                "kind=ClientIntro stem_kind=GUARDED extend_ms=55 elapsed_ms=68 torfast hspool timing specific circuit failed",
                "kind=ClientRend stem_kind=GUARDED elapsed_ms=22 torfast hspool timing client rend circuit ready",
            ]
        )

        self.assertEqual(
            [item["event"] for item in timings],
            [
                "on_demand_start",
                "on_demand_ready",
                "background_ready",
                "reused_stem",
                "stem_ready",
                "stem_failed",
                "stem_selected",
                "specific_circuit_ready",
                "specific_circuit_failed",
                "client_rend_circuit_ready",
            ],
        )
        self.assertEqual(timings[1]["launch_ms"], 783)
        self.assertEqual(timings[2]["kind"], "NAIVE")
        self.assertEqual(timings[4]["source"], "pool")
        self.assertEqual(timings[7]["extend_ms"], 44)
        self.assertEqual(timings[9]["elapsed_ms"], 22)

    def test_parses_torfast_hs_timings(self) -> None:
        timings = parse_torfast_hs_timings(
            [
                "hs_connect_id=42 elapsed_ms=600 connect_elapsed_ms=600 torfast hs timing descriptor dir circuit ready",
                "hs_connect_id=42 elapsed_ms=650 connect_elapsed_ms=650 torfast hs timing descriptor dir stream ready",
                "hs_connect_id=42 elapsed_ms=775 connect_elapsed_ms=775 torfast hs timing descriptor response ready",
                "hs_connect_id=42 elapsed_ms=776 connect_elapsed_ms=776 torfast hs timing descriptor parsed",
                "hs_connect_id=42 elapsed_ms=800 connect_elapsed_ms=800 torfast hs timing descriptor ready",
                "hs_connect_id=42 elapsed_ms=900 connect_elapsed_ms=900 torfast hs timing descriptor refetch ready",
                "hs_connect_id=42 elapsed_ms=0 connect_elapsed_ms=801 torfast hs timing rendezvous circuit ready",
                "hs_connect_id=42 elapsed_ms=100 connect_elapsed_ms=901 torfast hs timing rendezvous established",
                "hs_connect_id=42 intro_index=IntroPtIndex(2) elapsed_ms=20 connect_elapsed_ms=921 torfast hs timing intro circuit ready",
                "hs_connect_id=42 intro_index=IntroPtIndex(2) elapsed_ms=120 connect_elapsed_ms=1021 torfast hs timing introduce ack received",
                "hs_connect_id=42 intro_index=IntroPtIndex(2) elapsed_ms=2200 connect_elapsed_ms=3221 torfast hs timing rendezvous2 received",
                "hs_connect_id=42 intro_index=IntroPtIndex(2) elapsed_ms=2201 connect_elapsed_ms=3222 torfast hs timing circuit established",
            ]
        )

        self.assertEqual([item["event"] for item in timings], [
            "descriptor_dir_circuit_ready",
            "descriptor_dir_stream_ready",
            "descriptor_response_ready",
            "descriptor_parsed",
            "descriptor_ready",
            "descriptor_refetch_ready",
            "rendezvous_circuit_ready",
            "rendezvous_established",
            "intro_circuit_ready",
            "introduce_ack_received",
            "rendezvous2_received",
            "circuit_established",
        ])
        self.assertEqual(
            event_median(timings, "rendezvous2_received", "elapsed_ms"), 2200.0
        )
        self.assertEqual(
            event_median(timings, "descriptor_dir_circuit_ready", "elapsed_ms"), 600.0
        )
        self.assertEqual(
            event_median(timings, "descriptor_response_ready", "elapsed_ms"), 775.0
        )
        self.assertEqual(event_median(timings, "descriptor_ready", "elapsed_ms"), 800.0)
        self.assertEqual({item["hs_connect_id"] for item in timings}, {42})
        self.assertEqual(
            event_median(timings, "circuit_established", "connect_elapsed_ms"), 3222.0
        )

    def test_parses_torfast_hs_client_timings(self) -> None:
        timings = parse_torfast_hs_client_timings(
            [
                "port=443 elapsed_ms=0 torfast hs client timing start",
                "port=443 elapsed_ms=0 torfast hs client timing bootstrap ready",
                "port=443 elapsed_ms=0 torfast hs client timing netdir ready",
                "port=443 elapsed_ms=0 torfast hs client timing keys ready",
                "port=443 elapsed_ms=2975 torfast hs client timing tunnel ready",
                "port=443 elapsed_ms=3328 tunnel_elapsed_ms=2975 begin_phase_ms=353 ok=true torfast hs client timing begin stream finished",
            ]
        )

        self.assertEqual([item["event"] for item in timings], [
            "start",
            "bootstrap_ready",
            "netdir_ready",
            "keys_ready",
            "tunnel_ready",
            "begin_stream_finished",
        ])
        self.assertEqual(event_median(timings, "tunnel_ready", "elapsed_ms"), 2975.0)
        self.assertEqual(
            event_median(timings, "begin_stream_finished", "begin_phase_ms"),
            353.0,
        )
        self.assertTrue(timings[-1]["ok"])

    def test_parses_torfast_hs_state_timings(self) -> None:
        timings = parse_torfast_hs_state_timings(
            [
                "port=443 elapsed_ms=0 torfast hs state timing client wrapper start",
                "port=443 elapsed_ms=2212 torfast hs state timing client wrapper finished",
                "elapsed_ms=0 torfast hs state timing spawn connect task",
                "timing_id=44 owner_timing_id=73 elapsed_ms=17 torfast hs state timing wait existing task",
                "elapsed_ms=2210 ok=true torfast hs state timing connect task finished",
                "elapsed_ms=2211 torfast hs state timing cache hit",
                "elapsed_ms=2212 torfast hs state timing tunnel returned",
            ]
        )

        self.assertEqual([item["event"] for item in timings], [
            "client_wrapper_start",
            "client_wrapper_finished",
            "spawn_connect_task",
            "wait_existing_task",
            "connect_task_finished",
            "cache_hit",
            "tunnel_returned",
        ])
        self.assertEqual(timings[3]["owner_timing_id"], 73)
        self.assertEqual(
            event_median(timings, "client_wrapper_finished", "elapsed_ms"),
            2212.0,
        )
        self.assertEqual(
            event_median(timings, "connect_task_finished", "elapsed_ms"), 2210.0
        )
        self.assertTrue(timings[4]["ok"])

    def test_hs_burst_run_rows_join_onion_context(self) -> None:
        payload = {
            "profiles": {
                "arti_release_browser": {
                    "benchmarks": {
                        "https://securedrop.org/": {
                            "runs": [
                                {
                                    "run_index": 5,
                                    "ok": True,
                                    "load_ms": 8622.704,
                                    "proxy_signal_lines": [
                                        "2026-06-25T16:16:57Z  INFO tor_hsclient::connect: torfast hs timing intro circuit ready hs_connect_id=15 intro_index=IntroPtIndex(1) elapsed_ms=1217 connect_elapsed_ms=12361",
                                        "2026-06-25T16:16:57Z  INFO tor_hsclient::state: torfast hs state timing connect task finished state_id=TableIndex(11v1) elapsed_ms=13224 ok=true",
                                        "2026-06-25T16:16:57Z  INFO tor_hsclient::state: torfast hs state timing tunnel returned state_id=TableIndex(11v1) elapsed_ms=13224",
                                        "2026-06-25T16:17:05Z  INFO tor_hsclient::connect: torfast hs timing circuit established hs_connect_id=12 intro_index=IntroPtIndex(1) elapsed_ms=415 connect_elapsed_ms=23977",
                                        "2026-06-25T16:17:05Z  INFO tor_hsclient::state: torfast hs state timing connect task finished state_id=TableIndex(12v1) elapsed_ms=23977 ok=true",
                                        "2026-06-25T16:17:05Z  INFO tor_hsclient::state: torfast hs state timing tunnel returned state_id=TableIndex(12v1) elapsed_ms=23977",
                                        "2026-06-25T16:17:06Z  INFO arti::proxy::socks: torfast socks timing request parsed timing_id=73 target_kind=onion target_label=cflarejlah424meo...id.onion command=CONNECT port=443 client_peer_port=54475 conn_started_epoch_ms=1782404226123 elapsed_ms=0",
                                    ],
                                }
                            ]
                        }
                    }
                }
            }
        }

        rows = torfast_hs_burst_run_rows(payload)

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["profile"], "arti_release_browser")
        self.assertEqual(row["target"], "https://securedrop.org/")
        self.assertEqual(row["run_index"], 5)
        self.assertEqual(row["onion_requests"], 1)
        self.assertEqual(row["onion_join_mode"], "run-only")
        self.assertEqual(row["hs_timing_ids"], "")
        self.assertEqual(row["waiter_timing_ids"], "")
        self.assertEqual(row["onion_timing_ids"], "73")
        self.assertEqual(row["hs_log_window_s"], "0.000-8.000")
        self.assertAlmostEqual(row["first_onion_after_hs_s"], 9.123, places=3)
        self.assertIn("cflarejlah424meo...id.onion", row["onion_targets"])
        self.assertIn("12:23977", row["slow_hs_connect_ids"])
        self.assertIn("15:12361", row["slow_hs_connect_ids"])
        self.assertIn("TableIndex(12v1):23977", row["slow_state_ids"])
        self.assertIn("TableIndex(11v1):13224", row["slow_state_ids"])

    def test_hs_burst_run_rows_prefer_exact_timing_id_matches(self) -> None:
        payload = {
            "profiles": {
                "arti_release_browser": {
                    "benchmarks": {
                        "https://securedrop.org/": {
                            "runs": [
                                {
                                    "run_index": 5,
                                    "ok": True,
                                    "load_ms": 8622.704,
                                    "proxy_signal_lines": [
                                        "2026-06-25T16:16:57Z  INFO tor_hsclient::connect: torfast hs timing intro circuit ready timing_id=73 hs_connect_id=15 intro_index=IntroPtIndex(1) elapsed_ms=1217 connect_elapsed_ms=12361",
                                        "2026-06-25T16:16:57Z  INFO tor_hsclient::state: torfast hs state timing connect task finished timing_id=73 state_id=TableIndex(11v1) elapsed_ms=13224 ok=true",
                                        "2026-06-25T16:17:05Z  INFO tor_hsclient::connect: torfast hs timing circuit established timing_id=73 hs_connect_id=12 intro_index=IntroPtIndex(1) elapsed_ms=415 connect_elapsed_ms=23977",
                                        "2026-06-25T16:17:05Z  INFO tor_hsclient::state: torfast hs state timing tunnel returned timing_id=73 state_id=TableIndex(12v1) elapsed_ms=23977",
                                        "2026-06-25T16:16:56Z  INFO arti::proxy::socks: torfast socks timing request parsed timing_id=44 target_kind=onion target_label=wrong.onion command=CONNECT port=443 client_peer_port=54474 conn_started_epoch_ms=1782404220000 elapsed_ms=0",
                                        "2026-06-25T16:17:06Z  INFO arti::proxy::socks: torfast socks timing request parsed timing_id=73 target_kind=onion target_label=cflarejlah424meo...id.onion command=CONNECT port=443 client_peer_port=54475 conn_started_epoch_ms=1782404226123 elapsed_ms=0",
                                    ],
                                }
                            ]
                        }
                    }
                }
            }
        }

        rows = torfast_hs_burst_run_rows(payload)

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["onion_join_mode"], "exact")
        self.assertEqual(row["hs_timing_ids"], "73")
        self.assertEqual(row["waiter_timing_ids"], "")
        self.assertEqual(row["onion_requests"], 1)
        self.assertEqual(row["onion_timing_ids"], "73")
        self.assertEqual(row["onion_targets"], "cflarejlah424meo...id.onion")
        self.assertNotIn("wrong.onion", row["onion_targets"])
        self.assertAlmostEqual(row["first_onion_after_hs_s"], 9.123, places=3)

    def test_hs_burst_run_rows_prefer_waiter_exact_timing_id_matches(self) -> None:
        payload = {
            "profiles": {
                "arti_release_browser": {
                    "benchmarks": {
                        "https://securedrop.org/": {
                            "runs": [
                                {
                                    "run_index": 5,
                                    "ok": True,
                                    "load_ms": 8622.704,
                                    "proxy_signal_lines": [
                                        "2026-06-25T16:16:57Z  INFO tor_hsclient::connect: torfast hs timing intro circuit ready timing_id=73 hs_connect_id=15 intro_index=IntroPtIndex(1) elapsed_ms=1217 connect_elapsed_ms=12361",
                                        "2026-06-25T16:16:57Z  INFO tor_hsclient::state: torfast hs state timing wait existing task timing_id=44 owner_timing_id=73 state_id=TableIndex(11v1) elapsed_ms=300",
                                        "2026-06-25T16:16:56Z  INFO arti::proxy::socks: torfast socks timing request parsed timing_id=55 target_kind=onion target_label=wrong.onion command=CONNECT port=443 client_peer_port=54474 conn_started_epoch_ms=1782404220000 elapsed_ms=0",
                                        "2026-06-25T16:17:06Z  INFO arti::proxy::socks: torfast socks timing request parsed timing_id=44 target_kind=onion target_label=fallback.onion command=CONNECT port=443 client_peer_port=54475 conn_started_epoch_ms=1782404226123 elapsed_ms=0",
                                    ],
                                }
                            ]
                        }
                    }
                }
            }
        }

        rows = torfast_hs_burst_run_rows(payload)

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["onion_join_mode"], "waiter-exact")
        self.assertEqual(row["hs_timing_ids"], "73")
        self.assertEqual(row["waiter_timing_ids"], "44")
        self.assertEqual(row["onion_timing_ids"], "44")
        self.assertEqual(row["onion_targets"], "fallback.onion")
        self.assertNotIn("wrong.onion", row["onion_targets"])

    def test_hs_burst_run_rows_flag_run_fallback_when_exact_id_missing(self) -> None:
        payload = {
            "profiles": {
                "arti_release_browser": {
                    "benchmarks": {
                        "https://securedrop.org/": {
                            "runs": [
                                {
                                    "run_index": 5,
                                    "ok": True,
                                    "load_ms": 8622.704,
                                    "proxy_signal_lines": [
                                        "2026-06-25T16:16:57Z  INFO tor_hsclient::connect: torfast hs timing intro circuit ready timing_id=73 hs_connect_id=15 intro_index=IntroPtIndex(1) elapsed_ms=1217 connect_elapsed_ms=12361",
                                        "2026-06-25T16:17:06Z  INFO arti::proxy::socks: torfast socks timing request parsed timing_id=44 target_kind=onion target_label=fallback.onion command=CONNECT port=443 client_peer_port=54475 conn_started_epoch_ms=1782404226123 elapsed_ms=0",
                                    ],
                                }
                            ]
                        }
                    }
                }
            }
        }

        rows = torfast_hs_burst_run_rows(payload)

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["onion_join_mode"], "run-fallback")
        self.assertEqual(row["hs_timing_ids"], "73")
        self.assertEqual(row["waiter_timing_ids"], "")
        self.assertEqual(row["onion_timing_ids"], "44")
        self.assertEqual(row["onion_targets"], "fallback.onion")

    def test_parses_torfast_exit_client_timings(self) -> None:
        timings = parse_torfast_exit_client_timings(
            [
                "port=443 tunnel_unique_id=Circ 4.11 elapsed_ms=1200 torfast exit client timing tunnel ready",
                "port=443 tunnel_unique_id=Circ 4.11 elapsed_ms=64000 tunnel_elapsed_ms=1200 begin_phase_ms=62800 ok=true torfast exit client timing begin stream finished",
                "port=443 elapsed_ms=5000 ok=false torfast exit client timing tunnel ready",
            ]
        )

        self.assertEqual(
            [item["event"] for item in timings],
            ["tunnel_ready", "begin_stream_finished", "tunnel_ready"],
        )
        self.assertEqual(event_median(timings, "tunnel_ready", "elapsed_ms"), 3100.0)
        self.assertEqual(
            event_median(timings, "begin_stream_finished", "begin_phase_ms"),
            62800.0,
        )
        self.assertEqual(timings[0]["tunnel_unique_id"], "Circ 4.11")
        self.assertTrue(timings[1]["ok"])
        self.assertFalse(timings[2]["ok"])

    def test_exit_client_slow_tunnel_rows_include_run_context(self) -> None:
        payload = {
            "profiles": {
                "arti_release_browser": {
                    "benchmarks": {
                        "https://example.test/": {
                            "runs": [
                                {
                                    "run_index": 2,
                                    "load_ms": 51000,
                                    "proxy_signal_lines": [
                                        "port=443 tunnel_unique_id=Circ 4.11 elapsed_ms=36790 torfast exit client timing tunnel ready",
                                        "port=443 tunnel_unique_id=Circ 4.11 elapsed_ms=36790 tunnel_elapsed_ms=36790 begin_phase_ms=0 ok=true torfast exit client timing begin stream finished",
                                    ],
                                }
                            ]
                        }
                    }
                }
            }
        }

        rows = torfast_exit_client_slow_tunnel_rows(payload)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["profile"], "arti_release_browser")
        self.assertEqual(rows[0]["target"], "https://example.test/")
        self.assertEqual(rows[0]["run_index"], 2)
        self.assertEqual(rows[0]["load_ms"], 51000)
        self.assertEqual(rows[0]["tunnel_unique_id"], "Circ 4.11")
        self.assertEqual(rows[0]["tunnel_ms"], 36790)
        self.assertEqual(rows[0]["begin_ms"], 36790)
        self.assertEqual(rows[0]["begin_phase_ms"], 0)
        self.assertTrue(rows[0]["ok"])

    def test_slow_connect_phase_rows_join_exit_and_hs_timings(self) -> None:
        payload = {
            "profiles": {
                "arti_release_browser": {
                    "benchmarks": {
                        "https://example.test/": {
                            "runs": [
                                {
                                    "run_index": 1,
                                    "proxy_signal_lines": [
                                        "torfast socks timing request parsed timing_id=7 target_kind=hostname command=CONNECT port=443 conn_started_epoch_ms=1000 elapsed_ms=0",
                                        "torfast exit client timing tunnel ready port=443 tunnel_unique_id=Circ 4.11 elapsed_ms=1500",
                                        "torfast exit client timing begin stream finished port=443 tunnel_unique_id=Circ 4.11 elapsed_ms=1501 tunnel_elapsed_ms=1500 begin_phase_ms=1 ok=true",
                                        "torfast socks timing stream ready timing_id=7 target_kind=hostname port=443 conn_started_epoch_ms=1000 connect_ms=1501 elapsed_ms=1501",
                                        "torfast socks timing stream linked timing_id=7 target_kind=hostname port=443 conn_started_epoch_ms=1000 circ_id=Circ 4.11 hop=#3 stream_id=10 elapsed_ms=1501",
                                        "torfast socks timing request parsed timing_id=8 target_kind=onion command=CONNECT port=443 conn_started_epoch_ms=2000 elapsed_ms=0",
                                        "torfast hs client timing begin stream finished port=443 elapsed_ms=2420 tunnel_elapsed_ms=1900 begin_phase_ms=520 ok=true",
                                        "torfast socks timing stream ready timing_id=8 target_kind=onion port=443 conn_started_epoch_ms=2000 connect_ms=2420 elapsed_ms=2420",
                                    ],
                                }
                            ]
                        }
                    }
                }
            }
        }

        rows = torfast_slow_connect_phase_rows(payload)

        self.assertEqual(len(rows), 2)
        by_timing_id = {row["timing_id"]: row for row in rows}
        exit_row = by_timing_id[7]
        self.assertEqual(exit_row["timing_id"], 7)
        self.assertEqual(exit_row["phase_source"], "exit")
        self.assertEqual(exit_row["join_method"], "tunnel id")
        self.assertEqual(exit_row["tunnel_ms"], 1500)
        self.assertEqual(exit_row["begin_phase_ms"], 1)
        self.assertEqual(exit_row["delay_hint"], "tunnel acquisition")
        hs_row = by_timing_id[8]
        self.assertEqual(hs_row["timing_id"], 8)
        self.assertEqual(hs_row["phase_source"], "hs")
        self.assertEqual(hs_row["join_method"], "elapsed")
        self.assertEqual(hs_row["tunnel_ms"], 1900)
        self.assertEqual(hs_row["begin_phase_ms"], 520)
        self.assertEqual(hs_row["delay_hint"], "tunnel acquisition")

    def test_parses_torfast_circuit_assignments(self) -> None:
        assignments = parse_torfast_circuit_assignments(
            [
                "DEBUG arti_client::client: Got a circuit for [scrubbed]:443 tunnel_id=Circ 1.1",
                "DEBUG arti_client::client: Got a circuit for [scrubbed]:443 tunnel_id=Circ 0.1",
                "DEBUG arti::proxy::socks: Got a stream for [scrubbed]:443",
            ]
        )

        self.assertEqual(
            [assignment["tunnel_id"] for assignment in assignments],
            ["Circ 1.1", "Circ 0.1"],
        )

    def test_builds_torfast_socks_context_rows(self) -> None:
        lines = [
            "2026-06-06T23:12:00Z timing_id=8 target_kind=onion command=CONNECT port=443 elapsed_ms=0 torfast socks timing request parsed",
            "2026-06-06T23:12:01Z tor_circmgr::hspool: launching 3 NAIVE and 1 GUARDED circuits",
            "2026-06-06T23:12:02Z tor_circmgr::build: Spawning reactor...",
            "2026-06-06T23:12:03Z arti_client::client: elapsed_ms=3000 torfast hs client timing start",
            "2026-06-06T23:12:04Z tor_hsclient::connect: hs conn to [...]onion: setting up rendezvous point",
            "2026-06-06T23:12:05Z tor_hsclient::connect: hs conn to [...]onion: HS circuit established",
            "2026-06-06T23:12:06Z timing_id=8 target_kind=onion port=443 connect_ms=5000 elapsed_ms=5000 torfast socks timing stream ready",
            "2026-06-06T23:12:07Z timing_id=8 target_kind=onion port=443 relay_ms=275 elapsed_ms=5276 ok=false torfast socks timing relay finished",
        ]
        timings = parse_torfast_socks_timings(lines)

        rows = torfast_context_rows(lines, torfast_slow_socks_rows(timings))

        self.assertEqual(rows[0]["timing_id"], 8)
        self.assertEqual(rows[0]["request_to_ready_lines"], 7)
        self.assertEqual(rows[0]["request_to_first_hs_s"], 3.0)
        self.assertEqual(rows[0]["first_hs_to_ready_s"], 3.0)
        self.assertEqual(rows[0]["hs_connect_lines"], 2)
        self.assertEqual(rows[0]["hspool_lines"], 1)
        self.assertEqual(rows[0]["spawned_reactors"], 1)


if __name__ == "__main__":
    unittest.main()
