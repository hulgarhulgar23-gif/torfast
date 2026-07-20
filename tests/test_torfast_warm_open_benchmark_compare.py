import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from run_torfast_warm_open_benchmark_compare import (
    benchmark_elapsed_ms,
    benchmark_load_ms,
    benchmark_summary_for_result,
    build_parser,
    build_profile_specs,
    capture_managed_service_state_snapshot,
    combined_wall_seconds,
    cycle_profile_order,
    delta_vs_baseline,
    main,
    managed_general_circuit_profile_name,
    parse_extra_wait_values,
    preserve_benchmark_browser_net_logs,
    run_target_profile_once,
    summarize_results,
    waited_profile_name,
)


class TorfastWarmOpenBenchmarkCompareTests(unittest.TestCase):
    def test_parser_defaults_browser_diagnostics_off(self) -> None:
        args = build_parser().parse_args([])

        self.assertFalse(args.browser_net_log)
        self.assertFalse(args.browser_serial_http_connections)
        self.assertIsNone(args.browser_max_persistent_connections_per_server)
        self.assertEqual(args.browser_block_url_substrings, [])
        self.assertEqual(args.extra_browser_block_url_substring, [])
        self.assertEqual(
            args.extra_browser_max_persistent_connections_per_server, []
        )
        self.assertFalse(args.extra_browser_serial_http_connections)
        self.assertFalse(args.browser_startup_seed)
        self.assertFalse(args.extra_browser_startup_seed)
        self.assertFalse(args.extra_no_browser_startup_seed)
        self.assertFalse(args.persistent_control_wait)
        self.assertFalse(args.extra_no_persistent_control_wait)
        self.assertFalse(args.extra_no_control_bootstrap_probe)
        self.assertFalse(args.extra_no_async_browser_reset)
        self.assertFalse(args.extra_no_managed_service_metadata_wait)
        self.assertFalse(args.managed_open_settle)
        self.assertTrue(args.managed_open_browser_overlap)
        self.assertFalse(args.warm_helper_prestart)
        self.assertFalse(args.warm_browser_prestart)
        self.assertFalse(args.extra_no_managed_open_settle)
        self.assertFalse(args.extra_no_managed_open_browser_overlap)
        self.assertFalse(args.extra_no_warm_helper_prestart)
        self.assertFalse(args.extra_no_warm_browser_prestart)
        self.assertFalse(args.benchmark_general_circuit_timeline)
        self.assertFalse(args.benchmark_stream_isolation_timeline)

    def test_parser_accepts_browser_diagnostics_flags(self) -> None:
        args = build_parser().parse_args(
            [
                "--browser-net-log",
                "--browser-serial-http-connections",
                "--browser-block-url-substring",
                "/static/js/fallback.js",
            ]
        )

        self.assertTrue(args.browser_net_log)
        self.assertTrue(args.browser_serial_http_connections)
        self.assertEqual(args.browser_block_url_substrings, ["/static/js/fallback.js"])

    def test_parser_accepts_extra_browser_diagnostic_variant_flags(self) -> None:
        args = build_parser().parse_args(
            [
                "--extra-browser-block-url-substring",
                "/fonts/fontawesome/png/white/brands/",
                "--extra-browser-max-persistent-connections-per-server",
                "7",
                "--extra-browser-serial-http-connections",
            ]
        )

        self.assertEqual(
            args.extra_browser_block_url_substring,
            ["/fonts/fontawesome/png/white/brands/"],
        )
        self.assertEqual(
            args.extra_browser_max_persistent_connections_per_server,
            ["7"],
        )
        self.assertTrue(args.extra_browser_serial_http_connections)

    def test_parser_accepts_compare_variant_flags(self) -> None:
        args = build_parser().parse_args(
            [
                "--warm-helper-prestart",
                "--persistent-control-wait",
                "--extra-no-control-bootstrap-probe",
                "--extra-no-managed-service-metadata-wait",
                "--extra-no-warm-helper-prestart",
                "--no-managed-open-browser-overlap",
                "--conflux-client-ux",
                "latency",
            ]
        )

        self.assertTrue(args.warm_helper_prestart)
        self.assertTrue(args.persistent_control_wait)
        self.assertTrue(args.extra_no_control_bootstrap_probe)
        self.assertTrue(args.extra_no_managed_service_metadata_wait)
        self.assertTrue(args.extra_no_warm_helper_prestart)
        self.assertFalse(args.managed_open_browser_overlap)
        self.assertEqual(args.conflux_client_ux, "latency")

    def test_parser_accepts_managed_general_circuit_gate_flag(self) -> None:
        args = build_parser().parse_args(["--use-managed-general-circuit-gate"])

        self.assertTrue(args.use_managed_general_circuit_gate)
        self.assertEqual(args.managed_general_circuit_min_count, 1)

    def test_parser_accepts_managed_general_circuit_min_count(self) -> None:
        args = build_parser().parse_args(
            [
                "--use-managed-general-circuit-gate",
                "--managed-general-circuit-min-count",
                "2",
            ]
        )

        self.assertTrue(args.use_managed_general_circuit_gate)
        self.assertEqual(args.managed_general_circuit_min_count, 2)

    def test_parser_accepts_extra_managed_general_circuit_min_count(self) -> None:
        args = build_parser().parse_args(
            [
                "--extra-managed-general-circuit-min-count",
                "2",
                "--extra-managed-general-circuit-min-count",
                "3",
            ]
        )

        self.assertEqual(args.extra_managed_general_circuit_min_count, ["2", "3"])

    def test_parser_accepts_benchmark_general_circuit_timeline_flag(self) -> None:
        args = build_parser().parse_args(["--benchmark-general-circuit-timeline"])

        self.assertTrue(args.benchmark_general_circuit_timeline)

    def test_parser_accepts_benchmark_stream_isolation_timeline_flag(self) -> None:
        args = build_parser().parse_args(["--benchmark-stream-isolation-timeline"])

        self.assertTrue(args.benchmark_stream_isolation_timeline)

    def test_main_rejects_managed_general_circuit_min_count_without_gate(self) -> None:
        with self.assertRaises(SystemExit) as raised:
            main(["--managed-general-circuit-min-count", "2"])

        self.assertEqual(
            str(raised.exception),
            "--managed-general-circuit-min-count requires "
            "--use-managed-general-circuit-gate",
        )

    def test_parse_extra_wait_values_dedupes_and_rounds(self) -> None:
        self.assertEqual(
            parse_extra_wait_values(["0.25", "0.2504", "0.5"]),
            [0.25, 0.5],
        )

    def test_waited_profile_name_and_build_profile_specs(self) -> None:
        self.assertEqual(waited_profile_name("auto", 0.25), "auto_wait_250ms")
        specs = build_profile_specs(
            profile_names=["auto", "tor_boot_95"],
            extra_post_warm_wait_seconds=[0.25],
            extra_browser_block_url_substrings=[],
            extra_browser_max_persistent_connections_per_server=[],
            extra_browser_serial_http_connections=False,
            extra_managed_general_circuit_min_count=[],
        )

        self.assertEqual(
            specs,
            [
                {
                    "name": "auto",
                    "base_profile_name": "auto",
                    "extra_post_warm_wait_seconds": 0.0,
                    "browser_serial_http_connections": False,
                    "browser_max_persistent_connections_per_server": None,
                    "extra_browser_block_url_substrings": [],
                },
                {
                    "name": "auto_wait_250ms",
                    "base_profile_name": "auto",
                    "extra_post_warm_wait_seconds": 0.25,
                    "browser_serial_http_connections": False,
                    "browser_max_persistent_connections_per_server": None,
                    "extra_browser_block_url_substrings": [],
                },
                {
                    "name": "tor_boot_95",
                    "base_profile_name": "tor_boot_95",
                    "extra_post_warm_wait_seconds": 0.0,
                    "browser_serial_http_connections": False,
                    "browser_max_persistent_connections_per_server": None,
                    "extra_browser_block_url_substrings": [],
                },
                {
                    "name": "tor_boot_95_wait_250ms",
                    "base_profile_name": "tor_boot_95",
                    "extra_post_warm_wait_seconds": 0.25,
                    "browser_serial_http_connections": False,
                    "browser_max_persistent_connections_per_server": None,
                    "extra_browser_block_url_substrings": [],
                },
            ],
        )

    def test_build_profile_specs_adds_browser_diagnostic_variants(self) -> None:
        specs = build_profile_specs(
            profile_names=["auto"],
            extra_post_warm_wait_seconds=[],
            extra_browser_block_url_substrings=[
                "/fonts/fontawesome/png/white/brands/"
            ],
            extra_browser_max_persistent_connections_per_server=[7],
            extra_browser_serial_http_connections=True,
            extra_managed_general_circuit_min_count=[],
        )

        self.assertEqual(
            specs,
            [
                {
                    "name": "auto",
                    "base_profile_name": "auto",
                    "extra_post_warm_wait_seconds": 0.0,
                    "browser_serial_http_connections": False,
                    "browser_max_persistent_connections_per_server": None,
                    "extra_browser_block_url_substrings": [],
                },
                {
                    "name": "auto_block_fonts-fontawesome-png-white-brands",
                    "base_profile_name": "auto",
                    "extra_post_warm_wait_seconds": 0.0,
                    "browser_serial_http_connections": False,
                    "browser_max_persistent_connections_per_server": None,
                    "extra_browser_block_url_substrings": [
                        "/fonts/fontawesome/png/white/brands/"
                    ],
                },
                {
                    "name": "auto_maxconn_7",
                    "base_profile_name": "auto",
                    "extra_post_warm_wait_seconds": 0.0,
                    "browser_serial_http_connections": False,
                    "browser_max_persistent_connections_per_server": 7,
                    "extra_browser_block_url_substrings": [],
                },
                {
                    "name": "auto_serialhttp",
                    "base_profile_name": "auto",
                    "extra_post_warm_wait_seconds": 0.0,
                    "browser_serial_http_connections": True,
                    "browser_max_persistent_connections_per_server": None,
                    "extra_browser_block_url_substrings": [],
                },
            ],
        )

    def test_build_profile_specs_adds_general_circuit_variants(self) -> None:
        self.assertEqual(
            managed_general_circuit_profile_name("auto", 2),
            "auto_gencirc_2",
        )
        specs = build_profile_specs(
            profile_names=["auto"],
            extra_post_warm_wait_seconds=[0.25],
            extra_browser_block_url_substrings=[],
            extra_browser_max_persistent_connections_per_server=[],
            extra_browser_serial_http_connections=False,
            extra_managed_general_circuit_min_count=[2],
        )

        self.assertEqual(
            specs,
            [
                {
                    "name": "auto",
                    "base_profile_name": "auto",
                    "extra_post_warm_wait_seconds": 0.0,
                    "browser_serial_http_connections": False,
                    "browser_max_persistent_connections_per_server": None,
                    "extra_browser_block_url_substrings": [],
                },
                {
                    "name": "auto_wait_250ms",
                    "base_profile_name": "auto",
                    "extra_post_warm_wait_seconds": 0.25,
                    "browser_serial_http_connections": False,
                    "browser_max_persistent_connections_per_server": None,
                    "extra_browser_block_url_substrings": [],
                },
                {
                    "name": "auto_gencirc_2",
                    "base_profile_name": "auto",
                    "extra_post_warm_wait_seconds": 0.0,
                    "browser_serial_http_connections": False,
                    "browser_max_persistent_connections_per_server": None,
                    "extra_browser_block_url_substrings": [],
                    "use_managed_general_circuit_gate": True,
                    "managed_general_circuit_min_count": 2,
                },
                {
                    "name": "auto_wait_250ms_gencirc_2",
                    "base_profile_name": "auto",
                    "extra_post_warm_wait_seconds": 0.25,
                    "browser_serial_http_connections": False,
                    "browser_max_persistent_connections_per_server": None,
                    "extra_browser_block_url_substrings": [],
                    "use_managed_general_circuit_gate": True,
                    "managed_general_circuit_min_count": 2,
                },
            ],
        )

    def test_build_profile_specs_adds_compare_variants(self) -> None:
        specs = build_profile_specs(
            profile_names=["auto"],
            extra_post_warm_wait_seconds=[],
            base_warm_helper_prestart_enabled=True,
            extra_no_control_bootstrap_probe=True,
            extra_no_managed_service_metadata_wait=True,
            extra_no_warm_helper_prestart=True,
            extra_browser_block_url_substrings=[],
            extra_browser_max_persistent_connections_per_server=[],
            extra_browser_serial_http_connections=False,
            extra_managed_general_circuit_min_count=[],
        )

        by_name = {str(spec["name"]): spec for spec in specs}

        self.assertIn("auto", by_name)
        self.assertIn("auto_noprestart", by_name)
        self.assertIn("auto_nocontrolprobe", by_name)
        self.assertIn("auto_nometadatawait", by_name)
        self.assertFalse(by_name["auto_noprestart"]["warm_helper_prestart_enabled"])
        self.assertFalse(
            by_name["auto_nocontrolprobe"]["control_bootstrap_probe_enabled"]
        )
        self.assertFalse(
            by_name["auto_nometadatawait"][
                "managed_service_metadata_wait_enabled"
            ]
        )

    def test_cycle_profile_order_rotates_and_randomizes_repeatably(self) -> None:
        specs = build_profile_specs(
            profile_names=["auto", "tor_boot_95"],
            extra_post_warm_wait_seconds=[0.25],
            extra_browser_block_url_substrings=[],
            extra_browser_max_persistent_connections_per_server=[],
            extra_browser_serial_http_connections=False,
            extra_managed_general_circuit_min_count=[],
        )

        self.assertEqual(
            [spec["name"] for spec in cycle_profile_order(2, specs)],
            ["auto_wait_250ms", "tor_boot_95", "tor_boot_95_wait_250ms", "auto"],
        )
        self.assertEqual(
            [
                spec["name"]
                for spec in cycle_profile_order(
                    3,
                    specs,
                    profile_order="randomized",
                    random_seed=123,
                )
            ],
            ["tor_boot_95", "tor_boot_95_wait_250ms", "auto_wait_250ms", "auto"],
        )

    def test_main_rejects_extra_browser_maxconn_with_global_serial(self) -> None:
        with self.assertRaises(SystemExit) as raised:
            main(
                [
                    "--browser-serial-http-connections",
                    "--extra-browser-max-persistent-connections-per-server",
                    "7",
                ]
            )

        self.assertEqual(
            str(raised.exception),
            "--extra-browser-max-persistent-connections-per-server cannot be "
            "combined with --browser-serial-http-connections",
        )

    def test_main_expands_extra_browser_variants_into_profile_runs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output_root = root / "results"
            browser_bin = root / "firefox"
            browser_bin.write_text("")
            tor_bin = root / "tor"
            tor_bin.write_text("")
            browser_startup_seed_root = root / "seed"
            browser_startup_seed_root.mkdir()

            fake_result = {
                "target": "https://www.torproject.org/",
                "profile_name": "auto",
                "warm": {"ok": True, "wall_seconds": 0.2},
                "benchmarks": {
                    "https://www.torproject.org/": {
                        "summary": {
                            "ok": True,
                            "median_elapsed_ms": 1000.0,
                            "median_load_ms": 900.0,
                        }
                    }
                },
                "benchmark_wall_seconds": 1.0,
            }

            captured_calls: list[dict[str, object]] = []

            def fake_run_target_profile_once(**kwargs: object) -> dict[str, object]:
                captured_calls.append(kwargs)
                result = dict(fake_result)
                result["profile_name"] = kwargs["profile_name"]
                return result

            with patch(
                "run_torfast_warm_open_benchmark_compare.run_target_profile_once",
                side_effect=fake_run_target_profile_once,
            ):
                main(
                    [
                        "--browser-bin",
                        str(browser_bin),
                        "--tor-bin",
                        str(tor_bin),
                        "--browser-startup-seed-root",
                        str(browser_startup_seed_root),
                        "--output-root",
                        str(output_root),
                        "--targets",
                        "https://www.torproject.org/",
                        "--profiles",
                        "auto",
                        "--cycles",
                        "1",
                        "--extra-browser-block-url-substring",
                        "/fonts/fontawesome/png/white/brands/",
                        "--extra-browser-max-persistent-connections-per-server",
                        "7",
                        "--extra-browser-serial-http-connections",
                        "--extra-managed-general-circuit-min-count",
                        "2",
                    ]
                )

        self.assertEqual(
            [call["profile_name"] for call in captured_calls],
            [
                "auto",
                "auto_block_fonts-fontawesome-png-white-brands",
                "auto_maxconn_7",
                "auto_serialhttp",
                "auto_gencirc_2",
                "auto_block_fonts-fontawesome-png-white-brands_gencirc_2",
                "auto_maxconn_7_gencirc_2",
                "auto_serialhttp_gencirc_2",
            ],
        )
        self.assertEqual(captured_calls[0]["browser_block_url_substrings"], [])
        self.assertEqual(
            captured_calls[1]["browser_block_url_substrings"],
            ["/fonts/fontawesome/png/white/brands/"],
        )
        self.assertEqual(
            captured_calls[2]["browser_max_persistent_connections_per_server"], 7
        )
        self.assertFalse(captured_calls[2]["browser_serial_http_connections"])
        self.assertTrue(captured_calls[3]["browser_serial_http_connections"])
        self.assertIsNone(
            captured_calls[3]["browser_max_persistent_connections_per_server"]
        )
        self.assertTrue(captured_calls[4]["use_managed_general_circuit_gate"])
        self.assertEqual(captured_calls[4]["managed_general_circuit_min_count"], 2)
        self.assertTrue(captured_calls[5]["use_managed_general_circuit_gate"])
        self.assertEqual(captured_calls[6]["browser_max_persistent_connections_per_server"], 7)
        self.assertTrue(captured_calls[7]["browser_serial_http_connections"])

    def test_main_expands_compare_variants_into_profile_runs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output_root = root / "results"
            browser_bin = root / "firefox"
            browser_bin.write_text("")
            tor_bin = root / "tor"
            tor_bin.write_text("")
            browser_startup_seed_root = root / "seed"
            browser_startup_seed_root.mkdir()

            fake_result = {
                "target": "https://check.torproject.org/",
                "profile_name": "auto",
                "warm": {"ok": True, "wall_seconds": 0.2},
                "warm_launch": {"tor_managed_ready": {"ok": True}},
                "benchmarks": {
                    "https://check.torproject.org/": {
                        "summary": {
                            "ok": True,
                            "median_elapsed_ms": 1000.0,
                            "median_load_ms": 900.0,
                        }
                    }
                },
                "benchmark_wall_seconds": 1.0,
                "torrc": {"isolate_socks_auth": True},
                "boot_after_benchmark": {"ok": True},
                "stop": {"ok": True},
            }

            captured_calls: list[dict[str, object]] = []

            def fake_run_target_profile_once(**kwargs: object) -> dict[str, object]:
                captured_calls.append(kwargs)
                result = dict(fake_result)
                result["profile_name"] = kwargs["profile_name"]
                return result

            with patch(
                "run_torfast_warm_open_benchmark_compare.run_target_profile_once",
                side_effect=fake_run_target_profile_once,
            ):
                main(
                    [
                        "--browser-bin",
                        str(browser_bin),
                        "--tor-bin",
                        str(tor_bin),
                        "--browser-startup-seed-root",
                        str(browser_startup_seed_root),
                        "--output-root",
                        str(output_root),
                        "--profiles",
                        "auto",
                        "--cycles",
                        "1",
                        "--warm-helper-prestart",
                        "--extra-no-control-bootstrap-probe",
                        "--extra-no-managed-service-metadata-wait",
                    ]
                )

        self.assertEqual(
            [call["profile_name"] for call in captured_calls],
            [
                "auto",
                "auto_nocontrolprobe",
                "auto_nometadatawait",
                "auto_nocontrolprobe_nometadatawait",
            ],
        )
        self.assertTrue(captured_calls[0]["warm_helper_prestart_enabled"])
        self.assertTrue(captured_calls[0]["managed_open_browser_overlap_enabled"])
        self.assertFalse(captured_calls[1]["control_bootstrap_probe_enabled"])
        self.assertFalse(captured_calls[2]["managed_service_metadata_wait_enabled"])
        self.assertFalse(captured_calls[3]["control_bootstrap_probe_enabled"])
        self.assertFalse(captured_calls[3]["managed_service_metadata_wait_enabled"])

    def test_benchmark_summary_for_result_returns_target_summary(self) -> None:
        target = "https://check.torproject.org/"
        result = {
            "target": target,
            "benchmarks": {
                target: {
                    "summary": {
                        "ok": True,
                        "median_elapsed_ms": 3210.0,
                        "median_load_ms": 2100.0,
                    }
                }
            },
        }

        self.assertEqual(
            benchmark_summary_for_result(result, target)["median_elapsed_ms"],
            3210.0,
        )
        self.assertEqual(benchmark_elapsed_ms(result), 3210.0)
        self.assertEqual(benchmark_load_ms(result), 2100.0)

    def test_combined_wall_seconds_adds_warm_and_benchmark(self) -> None:
        result = {
            "warm": {"wall_seconds": 0.25},
            "benchmark_wall_seconds": 4.75,
        }

        self.assertEqual(combined_wall_seconds(result), 5.0)

    def test_combined_wall_seconds_includes_open_gate_wait(self) -> None:
        result = {
            "warm": {"wall_seconds": 0.25},
            "open_gate_wait": {"seconds": 1.5},
            "benchmark_wall_seconds": 4.75,
        }

        self.assertEqual(combined_wall_seconds(result), 6.5)

    def test_combined_wall_seconds_includes_general_circuit_wait(self) -> None:
        result = {
            "warm": {"wall_seconds": 0.25},
            "open_gate_wait": {"seconds": 1.5},
            "general_circuit_wait": {"seconds": 0.75},
            "benchmark_wall_seconds": 4.75,
        }

        self.assertEqual(combined_wall_seconds(result), 7.25)

    def test_run_target_profile_once_forwards_browser_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output_dir = root / "output"
            output_dir.mkdir()
            browser_bin = root / "firefox"
            browser_bin.write_text("")
            tor_bin = root / "tor"
            tor_bin.write_text("")
            browser_startup_seed_root = root / "seed"
            browser_startup_seed_root.mkdir()

            benchmark_payload = {
                "https://www.torproject.org/": {
                    "runs": [
                        {
                            "ok": True,
                            "started_epoch_ms": 1100.0,
                            "elapsed_ms": 600.0,
                            "nav_finished_epoch_ms": 1600.0,
                            "finished_epoch_ms": 1700.0,
                        }
                    ],
                    "summary": {
                        "ok": True,
                        "median_elapsed_ms": 1234.0,
                        "median_load_ms": 987.0,
                    }
                }
            }
            warm_launch = {
                "tor_managed_ready": {
                    "ok": True,
                    "gate": "socks_ready",
                    "seconds": 0.055,
                },
                "reused_tor_service": {
                    "pid": 4321,
                    "tor_log": str(root / "tor.log"),
                },
            }
            (root / "tor.log").write_text(
                "\n".join(
                    [
                        "notice before benchmark event_epoch_ms=900",
                        "notice torfast circuit selection open event_epoch_ms=1100 circ_id=1",
                        "notice torfast socks timing stream linked event_epoch_ms=1200 timing_id=7 circ_id=1 stream_id=2",
                        "notice torfast relay receive delivered event_epoch_ms=1300 timing_id=7 circ_id=1 stream_id=2",
                        "notice torfast stream receiver terminal event_epoch_ms=1400 circ_id=1 stream_id=2",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            with (
                patch(
                    "run_torfast_warm_open_benchmark_compare.build_torfast_command",
                    return_value=["warm"],
                ) as build_torfast_command,
                patch(
                    "run_torfast_warm_open_benchmark_compare.build_stop_command",
                    return_value=["stop"],
                ),
                patch(
                    "run_torfast_warm_open_benchmark_compare.run_command",
                    side_effect=[
                        {"ok": True, "wall_seconds": 0.125},
                        {"ok": True, "stdout_tail": ["{}"]},
                    ],
                ) as run_command,
                patch(
                    "run_torfast_warm_open_benchmark_compare.read_json_file",
                    return_value=warm_launch,
                ),
                patch(
                    "run_torfast_warm_open_benchmark_compare.read_torrc_quality",
                    return_value={"isolate_socks_auth": True},
                ),
                patch(
                    "run_torfast_warm_open_benchmark_compare.parse_json_text",
                    return_value={},
                ),
                patch(
                    "run_torfast_warm_open_benchmark_compare.wait_for_existing_service_ready_in_log",
                    return_value={"ok": True, "seconds": 0.0},
                ),
                patch(
                    "run_torfast_warm_open_benchmark_compare.capture_managed_service_state_snapshot",
                    side_effect=[
                        {"control_bootstrap_phase": {"ok": True, "progress": 95}},
                        {"control_bootstrap_phase": {"ok": True, "progress": 100}},
                    ],
                ),
                patch(
                    "run_torfast_warm_open_benchmark_compare.run_browser_benchmarks",
                    return_value=benchmark_payload,
                ) as run_browser_benchmarks,
                patch(
                    "run_torfast_warm_open_benchmark_compare.time.monotonic",
                    side_effect=[100.0, 104.25],
                ),
            ):
                result = run_target_profile_once(
                    target="https://www.torproject.org/",
                    profile_name="auto",
                    base_profile_name="auto",
                    extra_post_warm_wait_seconds=0.0,
                    cycle=1,
                    port=20550,
                    browser_bin=browser_bin,
                    tor_bin=tor_bin,
                    timeout=45.0,
                    window_size="1280,800",
                    compact_output=True,
                    keep_run_dir=True,
                    browser_startup_seed_root=browser_startup_seed_root,
                    browser_startup_seed_enabled=False,
                    browser_net_log=True,
                    browser_serial_http_connections=True,
                    browser_max_persistent_connections_per_server=None,
                    browser_block_url_substrings=["/static/js/fallback.js"],
                    use_managed_open_gate=False,
                    use_managed_general_circuit_gate=False,
                    managed_general_circuit_min_count=1,
                    benchmark_general_circuit_timeline=False,
                    benchmark_stream_isolation_timeline=False,
                    output_dir=output_dir,
                    run_id="testrun",
                )

        build_torfast_command.assert_called_once_with(
            action="warm",
            state_root=Path(result["state_root"]),
            browser_bin=browser_bin,
            tor_bin=tor_bin,
            target="https://www.torproject.org/",
            port=20550,
            profile_name="auto",
            conflux_client_ux=None,
            browser_timeout=45.0,
            browser_startup_seed_root=browser_startup_seed_root,
            browser_startup_seed_enabled=False,
            managed_open_settle_enabled=False,
            managed_open_browser_overlap_enabled=True,
            warm_browser_prestart_enabled=False,
            headed=True,
        )
        self.assertEqual(
            run_command.call_args_list[0].kwargs["env_overrides"],
            {
                "TORFAST_ENABLE_PERSISTENT_CONTROL_WAIT": "0",
                "TORFAST_DISABLE_PERSISTENT_CONTROL_WAIT": "1",
                "TORFAST_DISABLE_CONTROL_BOOTSTRAP_PROBE": "0",
                "TORFAST_DISABLE_ASYNC_BROWSER_RESET": "",
                "TORFAST_DISABLE_MANAGED_SERVICE_METADATA_WAIT": "0",
                "TORFAST_ENABLE_TARGET_STREAM_PROOF": "0",
            },
        )
        run_browser_benchmarks.assert_called_once_with(
            browser_bin=browser_bin,
            port=20550,
            output_dir=Path(result["run_dir"]),
            targets=["https://www.torproject.org/"],
            runs=1,
            timeout=45.0,
            window_size="1280,800",
            compact_output=True,
            browser_net_log=True,
            browser_serial_http_connections=True,
            browser_max_persistent_connections_per_server=None,
            browser_block_url_substrings=["/static/js/fallback.js"],
            browser_startup_seed_root=browser_startup_seed_root,
            no_browser_startup_seed=True,
        )
        self.assertTrue(result["browser_net_log"])
        self.assertTrue(result["browser_serial_http_connections"])
        self.assertEqual(
            result["browser_block_url_substrings"], ["/static/js/fallback.js"]
        )
        self.assertEqual(result["browser_net_log_archive"]["copied_files"], [])
        self.assertEqual(result["benchmark_wall_seconds"], 4.25)
        self.assertEqual(
            result["benchmark_service_state_before_browser"],
            {"control_bootstrap_phase": {"ok": True, "progress": 95}},
        )
        self.assertEqual(
            result["benchmark_service_state_after_browser"],
            {"control_bootstrap_phase": {"ok": True, "progress": 100}},
        )
        self.assertIsNone(result["benchmark_general_circuit_timeline"])
        self.assertEqual(
            result["benchmark_proxy_signal_capture"]["captured_run_count"],
            1,
        )
        benchmark_run = result["benchmarks"]["https://www.torproject.org/"]["runs"][0]
        self.assertIn(
            "notice torfast socks timing stream linked event_epoch_ms=1200 timing_id=7 circ_id=1 stream_id=2",
            benchmark_run["proxy_signal_lines"],
        )
        self.assertIn(
            "notice torfast relay receive delivered event_epoch_ms=1300 timing_id=7 circ_id=1 stream_id=2",
            benchmark_run["proxy_relay_context_lines"],
        )
        self.assertEqual(
            benchmark_run["proxy_output_tail"],
            [
                "notice before benchmark event_epoch_ms=900",
                "notice torfast circuit selection open event_epoch_ms=1100 circ_id=1",
                "notice torfast socks timing stream linked event_epoch_ms=1200 timing_id=7 circ_id=1 stream_id=2",
                "notice torfast relay receive delivered event_epoch_ms=1300 timing_id=7 circ_id=1 stream_id=2",
                "notice torfast stream receiver terminal event_epoch_ms=1400 circ_id=1 stream_id=2",
            ],
        )
        self.assertIn(
            "notice torfast circuit selection open event_epoch_ms=1100 circ_id=1",
            result["benchmarks"]["https://www.torproject.org/"]["proxy_signal_lines"],
        )
        self.assertIn(
            "notice torfast relay receive delivered event_epoch_ms=1300 timing_id=7 circ_id=1 stream_id=2",
            result["benchmarks"]["https://www.torproject.org/"][
                "proxy_relay_context_lines"
            ],
        )

    def test_run_target_profile_once_reuses_prestarted_browser_for_benchmark(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output_dir = root / "output"
            output_dir.mkdir()
            browser_bin = root / "firefox"
            browser_bin.write_text("")
            tor_bin = root / "tor"
            tor_bin.write_text("")
            browser_startup_seed_root = root / "seed"
            browser_startup_seed_root.mkdir()

            benchmark_payload = {
                "https://check.torproject.org/": {
                    "summary": {
                        "ok": True,
                        "median_elapsed_ms": 1200.0,
                        "median_load_ms": 800.0,
                    }
                }
            }
            warm_launch = {
                "tor_managed_ready": {
                    "ok": True,
                    "gate": "tor_boot_95",
                    "seconds": 0.1,
                },
                "reused_tor_service": {
                    "pid": 4321,
                    "tor_log": str(root / "tor.log"),
                },
                "warm_browser_prestart": {
                    "enabled": True,
                    "applied": True,
                    "pid": 9999,
                    "marionette_port": 2828,
                },
                "browser_startup_seed_apply": {"ok": True, "applied": False},
            }
            (root / "tor.log").write_text("Bootstrapped 100%\n", encoding="utf-8")

            with (
                patch(
                    "run_torfast_warm_open_benchmark_compare.build_torfast_command",
                    return_value=["warm"],
                ),
                patch(
                    "run_torfast_warm_open_benchmark_compare.build_stop_command",
                    return_value=["stop"],
                ),
                patch(
                    "run_torfast_warm_open_benchmark_compare.run_command",
                    side_effect=[
                        {"ok": True, "wall_seconds": 0.15},
                        {"ok": True, "stdout_tail": ["{}"]},
                    ],
                ),
                patch(
                    "run_torfast_warm_open_benchmark_compare.read_json_file",
                    return_value=warm_launch,
                ),
                patch(
                    "run_torfast_warm_open_benchmark_compare.read_torrc_quality",
                    return_value={"isolate_socks_auth": True},
                ),
                patch(
                    "run_torfast_warm_open_benchmark_compare.parse_json_text",
                    return_value={},
                ),
                patch(
                    "run_torfast_warm_open_benchmark_compare.wait_for_existing_service_ready_in_log",
                    return_value={"ok": True, "seconds": 0.0},
                ),
                patch(
                    "run_torfast_warm_open_benchmark_compare.capture_managed_service_state_snapshot",
                    side_effect=[{"phase": "before"}, {"phase": "after"}],
                ),
                patch(
                    "run_torfast_warm_open_benchmark_compare.run_prestarted_browser_benchmarks",
                    return_value=benchmark_payload,
                ) as run_prestarted_browser_benchmarks,
                patch(
                    "run_torfast_warm_open_benchmark_compare.run_browser_benchmarks",
                ) as run_browser_benchmarks,
                patch(
                    "run_torfast_warm_open_benchmark_compare.time.monotonic",
                    side_effect=[10.0, 12.0],
                ),
            ):
                result = run_target_profile_once(
                    target="https://check.torproject.org/",
                    profile_name="auto",
                    base_profile_name="auto",
                    extra_post_warm_wait_seconds=0.0,
                    cycle=1,
                    port=20550,
                    browser_bin=browser_bin,
                    tor_bin=tor_bin,
                    timeout=45.0,
                    window_size="1280,800",
                    compact_output=True,
                    keep_run_dir=True,
                    browser_startup_seed_root=browser_startup_seed_root,
                    browser_startup_seed_enabled=False,
                    persistent_control_wait_enabled=False,
                    control_bootstrap_probe_enabled=True,
                    async_browser_reset_enabled=True,
                    managed_service_metadata_wait_enabled=True,
                    managed_open_settle_enabled=False,
                    managed_open_browser_overlap_enabled=True,
                    warm_helper_prestart_enabled=False,
                    warm_browser_prestart_enabled=True,
                    browser_net_log=False,
                    browser_serial_http_connections=False,
                    browser_max_persistent_connections_per_server=None,
                    browser_block_url_substrings=[],
                    use_managed_open_gate=False,
                    use_managed_general_circuit_gate=False,
                    managed_general_circuit_min_count=1,
                    benchmark_general_circuit_timeline=False,
                    benchmark_stream_isolation_timeline=False,
                    output_dir=output_dir,
                    run_id="testrun",
                )

        run_prestarted_browser_benchmarks.assert_called_once()
        run_browser_benchmarks.assert_not_called()
        self.assertEqual(
            result["benchmarks"]["https://check.torproject.org/"]["summary"][
                "median_elapsed_ms"
            ],
            1200.0,
        )

    def test_run_target_profile_once_forwards_torfast_variant_env_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output_dir = root / "output"
            output_dir.mkdir()
            browser_bin = root / "firefox"
            browser_bin.write_text("")
            tor_bin = root / "tor"
            tor_bin.write_text("")
            browser_startup_seed_root = root / "seed"
            browser_startup_seed_root.mkdir()

            benchmark_payload = {
                "https://check.torproject.org/": {
                    "summary": {
                        "ok": True,
                        "median_elapsed_ms": 1100.0,
                        "median_load_ms": 700.0,
                    }
                }
            }
            warm_launch = {
                "tor_managed_ready": {
                    "ok": True,
                    "gate": "tor_boot_95",
                    "seconds": 0.1,
                },
                "reused_tor_service": {
                    "pid": 4321,
                    "tor_log": str(root / "tor.log"),
                },
            }
            (root / "tor.log").write_text("Bootstrapped 100%\n", encoding="utf-8")

            with (
                patch(
                    "run_torfast_warm_open_benchmark_compare.build_torfast_command",
                    return_value=["warm"],
                ) as build_torfast_command,
                patch(
                    "run_torfast_warm_open_benchmark_compare.build_stop_command",
                    return_value=["stop"],
                ),
                patch(
                    "run_torfast_warm_open_benchmark_compare.run_command",
                    side_effect=[
                        {"ok": True, "wall_seconds": 0.2},
                        {"ok": True, "stdout_tail": ["{}"]},
                    ],
                ) as run_command,
                patch(
                    "run_torfast_warm_open_benchmark_compare.read_json_file",
                    return_value=warm_launch,
                ),
                patch(
                    "run_torfast_warm_open_benchmark_compare.read_torrc_quality",
                    return_value={"isolate_socks_auth": True},
                ),
                patch(
                    "run_torfast_warm_open_benchmark_compare.parse_json_text",
                    return_value={},
                ),
                patch(
                    "run_torfast_warm_open_benchmark_compare.wait_for_existing_service_ready_in_log",
                    return_value={"ok": True, "seconds": 0.0},
                ),
                patch(
                    "run_torfast_warm_open_benchmark_compare.capture_managed_service_state_snapshot",
                    side_effect=[{"phase": "before"}, {"phase": "after"}],
                ),
                patch(
                    "run_torfast_warm_open_benchmark_compare.run_browser_benchmarks",
                    return_value=benchmark_payload,
                ),
                patch(
                    "run_torfast_warm_open_benchmark_compare.time.monotonic",
                    side_effect=[10.0, 11.5],
                ),
            ):
                result = run_target_profile_once(
                    target="https://check.torproject.org/",
                    profile_name="auto_nocontrolprobe_nometadatawait",
                    base_profile_name="auto",
                    extra_post_warm_wait_seconds=0.0,
                    conflux_client_ux="latency",
                    cycle=1,
                    port=20550,
                    browser_bin=browser_bin,
                    tor_bin=tor_bin,
                    timeout=45.0,
                    window_size="1280,800",
                    compact_output=True,
                    keep_run_dir=True,
                    browser_startup_seed_root=browser_startup_seed_root,
                    browser_startup_seed_enabled=False,
                    persistent_control_wait_enabled=False,
                    control_bootstrap_probe_enabled=False,
                    async_browser_reset_enabled=False,
                    managed_service_metadata_wait_enabled=False,
                    managed_open_settle_enabled=False,
                    managed_open_browser_overlap_enabled=True,
                    warm_helper_prestart_enabled=True,
                    warm_browser_prestart_enabled=False,
                    browser_net_log=False,
                    browser_serial_http_connections=False,
                    browser_max_persistent_connections_per_server=None,
                    browser_block_url_substrings=[],
                    use_managed_open_gate=False,
                    use_managed_general_circuit_gate=False,
                    managed_general_circuit_min_count=1,
                    benchmark_general_circuit_timeline=False,
                    benchmark_stream_isolation_timeline=False,
                    output_dir=output_dir,
                    run_id="testrun",
                )

        build_torfast_command.assert_called_once_with(
            action="warm",
            state_root=Path(result["state_root"]),
            browser_bin=browser_bin,
            tor_bin=tor_bin,
            target="https://check.torproject.org/",
            port=20550,
            profile_name="auto",
            conflux_client_ux="latency",
            browser_timeout=45.0,
            browser_startup_seed_root=browser_startup_seed_root,
            browser_startup_seed_enabled=False,
            managed_open_settle_enabled=False,
            managed_open_browser_overlap_enabled=True,
            warm_browser_prestart_enabled=False,
            headed=True,
        )
        self.assertEqual(
            run_command.call_args_list[0].kwargs["env_overrides"],
            {
                "TORFAST_ENABLE_WARM_RUNTIME_HELPER_PRESTART": "1",
                "TORFAST_ENABLE_PERSISTENT_CONTROL_WAIT": "0",
                "TORFAST_DISABLE_PERSISTENT_CONTROL_WAIT": "1",
                "TORFAST_DISABLE_CONTROL_BOOTSTRAP_PROBE": "1",
                "TORFAST_DISABLE_ASYNC_BROWSER_RESET": "1",
                "TORFAST_DISABLE_MANAGED_SERVICE_METADATA_WAIT": "1",
                "TORFAST_ENABLE_TARGET_STREAM_PROOF": "0",
            },
        )
        self.assertEqual(result["conflux_client_ux"], "latency")
        self.assertTrue(result["warm_helper_prestart_enabled"])
        self.assertFalse(result["control_bootstrap_probe_enabled"])
        self.assertFalse(result["managed_service_metadata_wait_enabled"])

    def test_preserve_benchmark_browser_net_logs_copies_files_and_rewrites_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_dir = root / "run" / "browser_net_logs"
            source_dir.mkdir(parents=True)
            parent_log = source_dir / "https-example-1.mozlog.moz_log"
            child_log = source_dir / "https-example-1.mozlog.child-1.moz_log"
            parent_log.write_text("parent\n", encoding="utf-8")
            child_log.write_text("child\n", encoding="utf-8")

            benchmarks = {
                "https://www.torproject.org/": {
                    "runs": [
                        {
                            "browser_net_log": {
                                "enabled": True,
                                "files": [str(parent_log), str(child_log)],
                            }
                        }
                    ]
                }
            }

            archive = preserve_benchmark_browser_net_logs(
                benchmarks,
                archive_root=root / "results" / "browser_net_logs",
                target="https://www.torproject.org/",
                profile_name="auto",
                cycle=2,
            )

            archived_files = benchmarks["https://www.torproject.org/"]["runs"][0][
                "browser_net_log"
            ]["files"]
            self.assertEqual(len(archived_files), 2)
            self.assertEqual(len(archive["copied_files"]), 2)
            self.assertEqual(archive["missing_files"], [])
            self.assertEqual(archive["errors"], [])
            for archived_path in archived_files:
                self.assertTrue(Path(archived_path).exists())
            self.assertIn("auto-cycle2-run1", archived_files[0])

    def test_run_target_profile_once_waits_for_general_circuit_when_requested(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output_dir = root / "output"
            output_dir.mkdir()
            browser_bin = root / "firefox"
            browser_bin.write_text("")
            tor_bin = root / "tor"
            tor_bin.write_text("")
            browser_startup_seed_root = root / "seed"
            browser_startup_seed_root.mkdir()

            benchmark_payload = {
                "https://check.torproject.org/": {
                    "summary": {
                        "ok": True,
                        "median_elapsed_ms": 1200.0,
                        "median_load_ms": 800.0,
                    }
                }
            }
            warm_launch = {
                "tor_managed_ready": {
                    "ok": True,
                    "gate": "tor_boot_95",
                    "seconds": 2.5,
                },
                "reused_tor_service": {
                    "pid": 4321,
                    "tor_log": str(root / "tor.log"),
                },
            }

            with (
                patch(
                    "run_torfast_warm_open_benchmark_compare.build_torfast_command",
                    return_value=["warm"],
                ),
                patch(
                    "run_torfast_warm_open_benchmark_compare.build_stop_command",
                    return_value=["stop"],
                ),
                patch(
                    "run_torfast_warm_open_benchmark_compare.run_command",
                    side_effect=[
                        {"ok": True, "wall_seconds": 0.2},
                        {"ok": True, "stdout_tail": ["{}"]},
                    ],
                ),
                patch(
                    "run_torfast_warm_open_benchmark_compare.read_json_file",
                    return_value=warm_launch,
                ),
                patch(
                    "run_torfast_warm_open_benchmark_compare.read_torrc_quality",
                    return_value={"isolate_socks_auth": True},
                ),
                patch(
                    "run_torfast_warm_open_benchmark_compare.parse_json_text",
                    return_value={},
                ),
                patch(
                    "run_torfast_warm_open_benchmark_compare.wait_for_existing_service_ready_in_log",
                    return_value={"ok": True, "seconds": 0.0},
                ),
                patch(
                    "run_torfast_warm_open_benchmark_compare.wait_for_managed_general_circuit",
                    return_value={
                        "gate": "general_circuit",
                        "ok": True,
                        "seconds": 0.75,
                    },
                ) as wait_for_managed_general_circuit,
                patch(
                    "run_torfast_warm_open_benchmark_compare.capture_managed_service_state_snapshot",
                    side_effect=[{"phase": "before"}, {"phase": "after"}],
                ),
                patch(
                    "run_torfast_warm_open_benchmark_compare.run_browser_benchmarks",
                    return_value=benchmark_payload,
                ),
                patch(
                    "run_torfast_warm_open_benchmark_compare.time.monotonic",
                    side_effect=[10.0, 12.5],
                ),
            ):
                result = run_target_profile_once(
                    target="https://check.torproject.org/",
                    profile_name="auto",
                    base_profile_name="auto",
                    extra_post_warm_wait_seconds=0.0,
                    cycle=1,
                    port=20550,
                    browser_bin=browser_bin,
                    tor_bin=tor_bin,
                    timeout=45.0,
                    window_size="1280,800",
                    compact_output=True,
                    keep_run_dir=True,
                    browser_startup_seed_root=browser_startup_seed_root,
                    browser_startup_seed_enabled=False,
                    browser_net_log=False,
                    browser_serial_http_connections=False,
                    browser_max_persistent_connections_per_server=None,
                    browser_block_url_substrings=[],
                    use_managed_open_gate=False,
                    use_managed_general_circuit_gate=True,
                    managed_general_circuit_min_count=2,
                    benchmark_general_circuit_timeline=False,
                    benchmark_stream_isolation_timeline=False,
                    output_dir=output_dir,
                    run_id="testrun",
                )

        wait_for_managed_general_circuit.assert_called_once()
        self.assertEqual(
            wait_for_managed_general_circuit.call_args.kwargs["min_count"],
            2,
        )
        self.assertEqual(
            result["general_circuit_wait"],
            {"gate": "general_circuit", "ok": True, "seconds": 0.75},
        )
        self.assertTrue(result["use_managed_general_circuit_gate"])
        self.assertEqual(result["managed_general_circuit_min_count"], 2)

    def test_run_target_profile_once_collects_benchmark_general_circuit_timeline(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output_dir = root / "output"
            output_dir.mkdir()
            browser_bin = root / "firefox"
            browser_bin.write_text("")
            tor_bin = root / "tor"
            tor_bin.write_text("")
            browser_startup_seed_root = root / "seed"
            browser_startup_seed_root.mkdir()

            benchmark_payload = {
                "https://www.torproject.org/": {
                    "summary": {
                        "ok": True,
                        "median_elapsed_ms": 1500.0,
                        "median_load_ms": 1000.0,
                    }
                }
            }
            warm_launch = {
                "tor_managed_ready": {
                    "ok": True,
                    "gate": "socks_ready",
                    "seconds": 0.1,
                },
                "reused_tor_service": {
                    "pid": 4321,
                    "tor_log": str(root / "tor.log"),
                    "control_port": 19000,
                    "control_cookie_path": str(root / "cookie"),
                },
            }
            timeline_payload = {
                "enabled": True,
                "ok": True,
                "samples": [{"elapsed_seconds": 0.1}],
                "sample_count": 1,
            }

            with (
                patch(
                    "run_torfast_warm_open_benchmark_compare.build_torfast_command",
                    return_value=["warm"],
                ),
                patch(
                    "run_torfast_warm_open_benchmark_compare.build_stop_command",
                    return_value=["stop"],
                ),
                patch(
                    "run_torfast_warm_open_benchmark_compare.run_command",
                    side_effect=[
                        {"ok": True, "wall_seconds": 0.15},
                        {"ok": True, "stdout_tail": ["{}"]},
                    ],
                ),
                patch(
                    "run_torfast_warm_open_benchmark_compare.read_json_file",
                    return_value=warm_launch,
                ),
                patch(
                    "run_torfast_warm_open_benchmark_compare.read_torrc_quality",
                    return_value={"isolate_socks_auth": True},
                ),
                patch(
                    "run_torfast_warm_open_benchmark_compare.parse_json_text",
                    return_value={},
                ),
                patch(
                    "run_torfast_warm_open_benchmark_compare.wait_for_existing_service_ready_in_log",
                    return_value={"ok": True, "seconds": 0.0},
                ),
                patch(
                    "run_torfast_warm_open_benchmark_compare.capture_managed_service_state_snapshot",
                    side_effect=[{"phase": "before"}, {"phase": "after"}],
                ),
                patch(
                    "run_torfast_warm_open_benchmark_compare.start_benchmark_general_circuit_timeline_collector",
                    return_value={"payload": timeline_payload},
                ) as start_timeline,
                patch(
                    "run_torfast_warm_open_benchmark_compare.stop_benchmark_general_circuit_timeline_collector",
                ) as stop_timeline,
                patch(
                    "run_torfast_warm_open_benchmark_compare.run_browser_benchmarks",
                    return_value=benchmark_payload,
                ),
                patch(
                    "run_torfast_warm_open_benchmark_compare.time.monotonic",
                    side_effect=[10.0, 12.0],
                ),
            ):
                result = run_target_profile_once(
                    target="https://www.torproject.org/",
                    profile_name="auto",
                    base_profile_name="auto",
                    extra_post_warm_wait_seconds=0.0,
                    cycle=1,
                    port=20550,
                    browser_bin=browser_bin,
                    tor_bin=tor_bin,
                    timeout=45.0,
                    window_size="1280,800",
                    compact_output=True,
                    keep_run_dir=True,
                    browser_startup_seed_root=browser_startup_seed_root,
                    browser_startup_seed_enabled=False,
                    browser_net_log=False,
                    browser_serial_http_connections=False,
                    browser_max_persistent_connections_per_server=None,
                    browser_block_url_substrings=[],
                    use_managed_open_gate=False,
                    use_managed_general_circuit_gate=False,
                    managed_general_circuit_min_count=1,
                    benchmark_general_circuit_timeline=True,
                    benchmark_stream_isolation_timeline=False,
                    output_dir=output_dir,
                    run_id="testrun",
                )

        start_timeline.assert_called_once()
        stop_timeline.assert_called_once()
        self.assertTrue(result["benchmark_general_circuit_timeline_enabled"])
        self.assertEqual(result["benchmark_general_circuit_timeline"], timeline_payload)

    def test_run_target_profile_once_collects_benchmark_stream_isolation_timeline(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output_dir = root / "output"
            output_dir.mkdir()
            browser_bin = root / "firefox"
            browser_bin.write_text("")
            tor_bin = root / "tor"
            tor_bin.write_text("")
            browser_startup_seed_root = root / "seed"
            browser_startup_seed_root.mkdir()

            benchmark_payload = {
                "https://www.torproject.org/": {
                    "summary": {
                        "ok": True,
                        "median_elapsed_ms": 1500.0,
                        "median_load_ms": 1000.0,
                    }
                }
            }
            warm_launch = {
                "tor_managed_ready": {
                    "ok": True,
                    "gate": "socks_ready",
                    "seconds": 0.1,
                },
                "reused_tor_service": {
                    "pid": 4321,
                    "tor_log": str(root / "tor.log"),
                    "control_port": 19000,
                    "control_cookie_path": str(root / "cookie"),
                },
            }
            timeline_payload = {
                "enabled": True,
                "ok": True,
                "samples": [{"elapsed_seconds": 0.1, "user_stream_count": 1}],
                "sample_count": 1,
            }

            with (
                patch(
                    "run_torfast_warm_open_benchmark_compare.build_torfast_command",
                    return_value=["warm"],
                ),
                patch(
                    "run_torfast_warm_open_benchmark_compare.build_stop_command",
                    return_value=["stop"],
                ),
                patch(
                    "run_torfast_warm_open_benchmark_compare.run_command",
                    side_effect=[
                        {"ok": True, "wall_seconds": 0.15},
                        {"ok": True, "stdout_tail": ["{}"]},
                    ],
                ),
                patch(
                    "run_torfast_warm_open_benchmark_compare.read_json_file",
                    return_value=warm_launch,
                ),
                patch(
                    "run_torfast_warm_open_benchmark_compare.read_torrc_quality",
                    return_value={"isolate_socks_auth": True},
                ),
                patch(
                    "run_torfast_warm_open_benchmark_compare.parse_json_text",
                    return_value={},
                ),
                patch(
                    "run_torfast_warm_open_benchmark_compare.wait_for_existing_service_ready_in_log",
                    return_value={"ok": True, "seconds": 0.0},
                ),
                patch(
                    "run_torfast_warm_open_benchmark_compare.capture_managed_service_state_snapshot",
                    side_effect=[{"phase": "before"}, {"phase": "after"}],
                ),
                patch(
                    "run_torfast_warm_open_benchmark_compare.start_benchmark_stream_isolation_timeline_collector",
                    return_value={"payload": timeline_payload},
                ) as start_timeline,
                patch(
                    "run_torfast_warm_open_benchmark_compare.stop_benchmark_stream_isolation_timeline_collector",
                ) as stop_timeline,
                patch(
                    "run_torfast_warm_open_benchmark_compare.run_browser_benchmarks",
                    return_value=benchmark_payload,
                ),
                patch(
                    "run_torfast_warm_open_benchmark_compare.time.monotonic",
                    side_effect=[10.0, 12.0],
                ),
            ):
                result = run_target_profile_once(
                    target="https://www.torproject.org/",
                    profile_name="auto",
                    base_profile_name="auto",
                    extra_post_warm_wait_seconds=0.0,
                    cycle=1,
                    port=20550,
                    browser_bin=browser_bin,
                    tor_bin=tor_bin,
                    timeout=45.0,
                    window_size="1280,800",
                    compact_output=True,
                    keep_run_dir=True,
                    browser_startup_seed_root=browser_startup_seed_root,
                    browser_startup_seed_enabled=False,
                    browser_net_log=False,
                    browser_serial_http_connections=False,
                    browser_max_persistent_connections_per_server=None,
                    browser_block_url_substrings=[],
                    use_managed_open_gate=False,
                    use_managed_general_circuit_gate=False,
                    managed_general_circuit_min_count=1,
                    benchmark_general_circuit_timeline=False,
                    benchmark_stream_isolation_timeline=True,
                    output_dir=output_dir,
                    run_id="testrun",
                )

        start_timeline.assert_called_once()
        stop_timeline.assert_called_once()
        self.assertTrue(result["benchmark_stream_isolation_timeline_enabled"])
        self.assertEqual(result["benchmark_stream_isolation_timeline"], timeline_payload)

    def test_capture_managed_service_state_snapshot_collects_control_probes(self) -> None:
        service = {
            "ready_gate": "tor_boot_95",
            "started_epoch_ms": 1_000.0,
            "ready_epoch_ms": 2_000.0,
            "control_port": 19000,
            "control_cookie_path": "/tmp/control_auth_cookie",
        }

        with (
            patch(
                "run_torfast_warm_open_benchmark_compare.time.time",
                return_value=3.5,
            ),
            patch(
                "run_torfast_warm_open_benchmark_compare.read_bootstrap_phase_snapshot",
                return_value={"ok": True, "progress": 95},
            ),
            patch(
                "run_torfast_warm_open_benchmark_compare.read_general_circuit_snapshot",
                return_value={
                    "ok": True,
                    "matched_circuit_count": 1,
                    "has_built_general_circuit": True,
                },
            ),
        ):
            snapshot = capture_managed_service_state_snapshot(service)

        self.assertEqual(snapshot["service_metadata_ready_gate"], "tor_boot_95")
        self.assertEqual(snapshot["service_uptime_seconds"], 2.5)
        self.assertEqual(snapshot["service_ready_age_seconds"], 1.5)
        self.assertEqual(
            snapshot["control_bootstrap_phase"],
            {"ok": True, "progress": 95},
        )
        self.assertEqual(
            snapshot["general_circuit_snapshot"]["matched_circuit_count"],
            1,
        )

    def test_summarize_results_and_deltas(self) -> None:
        target = "https://check.torproject.org/"
        results = [
            {
                "target": target,
                "profile_name": "auto",
                "warm": {"ok": True, "wall_seconds": 2.4},
                "post_warm_wait_seconds": 0.0,
                "warm_launch": {
                    "tor_managed_ready": {"ok": True, "gate": "tor_boot_95", "seconds": 2.3},
                    "reused_tor_service": {"pid": 1234, "tor_log": "/tmp/tor.log"},
                },
                "benchmarks": {
                    target: {
                        "summary": {
                            "ok": True,
                            "median_elapsed_ms": 3800.0,
                            "median_load_ms": 2500.0,
                        }
                    }
                },
                "benchmark_wall_seconds": 4.1,
                "boot_after_benchmark": {"ok": True},
                "torrc": {"isolate_socks_auth": True},
                "stop": {"ok": True},
            },
            {
                "target": target,
                "profile_name": "tor_boot_100",
                "warm": {"ok": True, "wall_seconds": 2.8},
                "post_warm_wait_seconds": 0.25,
                "warm_launch": {
                    "tor_managed_ready": {"ok": True, "gate": "tor_boot_100", "seconds": 2.7},
                    "reused_tor_service": {"pid": 1235, "tor_log": "/tmp/tor.log"},
                },
                "benchmarks": {
                    target: {
                        "summary": {
                            "ok": True,
                            "median_elapsed_ms": 3600.0,
                            "median_load_ms": 2400.0,
                        }
                    }
                },
                "benchmark_wall_seconds": 4.0,
                "boot_after_benchmark": {"ok": True},
                "torrc": {"isolate_socks_auth": True},
                "stop": {"ok": True},
            },
        ]

        profiles = summarize_results(
            results,
            targets=[target],
            profile_names=["auto", "tor_boot_100"],
        )

        self.assertEqual(
            profiles[target]["auto"]["median_combined_wall_seconds"],
            6.5,
        )
        self.assertEqual(
            profiles[target]["tor_boot_100"]["median_elapsed_ms"],
            3600.0,
        )
        self.assertEqual(
            profiles[target]["tor_boot_100"]["median_post_warm_wait_seconds"],
            0.25,
        )
        self.assertEqual(profiles[target]["tor_boot_100"]["p90_elapsed_ms"], 3600.0)
        self.assertEqual(profiles[target]["tor_boot_100"]["max_load_ms"], 2400.0)
        self.assertEqual(
            profiles[target]["tor_boot_100"]["max_combined_wall_seconds"],
            6.8,
        )

        deltas = delta_vs_baseline(
            profiles,
            targets=[target],
            profile_names=["auto", "tor_boot_100"],
            baseline_profile="auto",
        )

        self.assertEqual(
            deltas[target]["tor_boot_100"]["warm_wall_seconds"],
            0.4,
        )
        self.assertEqual(
            deltas[target]["tor_boot_100"]["benchmark_wall_seconds"],
            -0.1,
        )
        self.assertEqual(
            deltas[target]["tor_boot_100"]["post_warm_wait_seconds"],
            0.25,
        )
        self.assertEqual(deltas[target]["tor_boot_100"]["p90_elapsed_ms"], -200.0)
        self.assertEqual(deltas[target]["tor_boot_100"]["max_load_ms"], -100.0)
        self.assertEqual(
            deltas[target]["tor_boot_100"]["combined_wall_seconds"],
            0.3,
        )
        self.assertEqual(
            deltas[target]["tor_boot_100"]["max_combined_wall_seconds"],
            0.3,
        )


if __name__ == "__main__":
    unittest.main()
