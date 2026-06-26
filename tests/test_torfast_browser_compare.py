import queue
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from run_torfast_browser_compare import (
    BROADER_TARGETS,
    BUNDLED_PROFILE,
    BUNDLED_SEEDED_PROFILE,
    COLD_PROFILE,
    DEFAULT_TARGETS,
    SEEDED_PROFILE,
    SEEDED_CIRCUIT_READY_PROFILE,
    annotate_general_circuit_ready,
    build_arg_parser,
    bundled_seeded_conflux_ux_profile_name,
    bundled_seeded_general_circuits_profile_name,
    cycle_order,
    launch_ready_seconds_for_run,
    parse_extra_conflux_ux_values,
    parse_min_general_circuit_counts,
    parse_extra_wait_values,
    payload_ok,
    profile_bundled_seeded_conflux_ux,
    profile_min_general_circuit_count,
    profile_extra_post_boot_wait_seconds,
    profile_run_ok,
    run_measured_c_tor_browser,
    resolve_targets,
    seeded_wait_profile_name,
    short_summary,
    summarize_profile_runs,
)


def browser_run(*, ok: bool, elapsed_ms: float, load_ms: float) -> dict[str, object]:
    return {
        "ok": ok,
        "elapsed_ms": elapsed_ms,
        "load_ms": load_ms,
        "screenshot": {"bytes": 100},
        "performance_timing": {},
    }


class TorfastBrowserCompareTests(unittest.TestCase):
    def test_parser_defaults_browser_diagnostics_off(self) -> None:
        args = build_arg_parser().parse_args([])

        self.assertFalse(args.browser_net_log)
        self.assertFalse(args.browser_serial_http_connections)
        self.assertIsNone(args.browser_max_persistent_connections_per_server)
        self.assertEqual(args.browser_block_url_substrings, [])
        self.assertTrue(args.no_browser_startup_seed)
        self.assertIsNotNone(args.browser_startup_seed_root)

    def test_parser_accepts_browser_diagnostics_flags(self) -> None:
        args = build_arg_parser().parse_args(
            ["--browser-net-log", "--browser-serial-http-connections"]
        )

        self.assertTrue(args.browser_net_log)
        self.assertTrue(args.browser_serial_http_connections)

    def test_parser_accepts_browser_connection_cap_flag(self) -> None:
        args = build_arg_parser().parse_args(
            ["--browser-max-persistent-connections-per-server", "10"]
        )

        self.assertEqual(args.browser_max_persistent_connections_per_server, 10)

    def test_parser_accepts_bundled_seeded_conflux_ux_flags(self) -> None:
        args = build_arg_parser().parse_args(
            [
                "--extra-bundled-seeded-conflux-ux",
                "throughput",
                "--extra-bundled-seeded-conflux-ux",
                "latency",
            ]
        )

        self.assertEqual(
            args.extra_bundled_seeded_conflux_ux,
            ["throughput", "latency"],
        )

    def test_parser_accepts_browser_request_blocker_flags(self) -> None:
        args = build_arg_parser().parse_args(
            [
                "--browser-block-url-substring",
                "/static/js/fallback.js",
                "--browser-block-url-substring",
                "/fonts/fontawesome/png/",
            ]
        )

        self.assertEqual(
            args.browser_block_url_substrings,
            ["/static/js/fallback.js", "/fonts/fontawesome/png/"],
        )

    def test_parser_accepts_browser_startup_seed_flags(self) -> None:
        args = build_arg_parser().parse_args(
            [
                "--browser-startup-seed",
                "--browser-startup-seed-root",
                "/tmp/torfast-browser-startup-seed",
            ]
        )

        self.assertEqual(
            args.browser_startup_seed_root,
            "/tmp/torfast-browser-startup-seed",
        )
        self.assertFalse(args.no_browser_startup_seed)

    def test_cycle_order_rotates_profiles(self) -> None:
        self.assertEqual(
            cycle_order(
                1,
                [
                    BUNDLED_PROFILE,
                    BUNDLED_SEEDED_PROFILE,
                    bundled_seeded_general_circuits_profile_name(2),
                    COLD_PROFILE,
                    SEEDED_PROFILE,
                    SEEDED_CIRCUIT_READY_PROFILE,
                    seeded_wait_profile_name(0.5),
                ],
            ),
            [
                BUNDLED_PROFILE,
                BUNDLED_SEEDED_PROFILE,
                bundled_seeded_general_circuits_profile_name(2),
                COLD_PROFILE,
                SEEDED_PROFILE,
                SEEDED_CIRCUIT_READY_PROFILE,
                seeded_wait_profile_name(0.5),
            ],
        )
        self.assertEqual(
            cycle_order(
                2,
                [
                    BUNDLED_PROFILE,
                    BUNDLED_SEEDED_PROFILE,
                    bundled_seeded_general_circuits_profile_name(2),
                    COLD_PROFILE,
                    SEEDED_PROFILE,
                    SEEDED_CIRCUIT_READY_PROFILE,
                    seeded_wait_profile_name(0.5),
                ],
            ),
            [
                BUNDLED_SEEDED_PROFILE,
                bundled_seeded_general_circuits_profile_name(2),
                COLD_PROFILE,
                SEEDED_PROFILE,
                SEEDED_CIRCUIT_READY_PROFILE,
                seeded_wait_profile_name(0.5),
                BUNDLED_PROFILE,
            ],
        )
        self.assertEqual(
            cycle_order(2, [COLD_PROFILE, SEEDED_PROFILE]),
            [SEEDED_PROFILE, COLD_PROFILE],
        )

    def test_wait_profile_name_round_trip(self) -> None:
        name = seeded_wait_profile_name(0.5)

        self.assertEqual(name, "local_c_tor_browser_seeded_wait_500ms")
        self.assertEqual(profile_extra_post_boot_wait_seconds(name), 0.5)
        self.assertEqual(parse_extra_wait_values(["0.5", "0.500", "1"]), [0.5, 1.0])
        self.assertEqual(parse_min_general_circuit_counts(["2", "2", "3"]), [2, 3])
        bundled_name = bundled_seeded_general_circuits_profile_name(2)
        self.assertEqual(
            bundled_name,
            "bundled_c_tor_browser_seeded_general_circuits_2",
        )
        self.assertEqual(profile_min_general_circuit_count(bundled_name), 2)
        bundled_conflux_name = bundled_seeded_conflux_ux_profile_name("throughput")
        self.assertEqual(
            bundled_conflux_name,
            "bundled_c_tor_browser_seeded_confluxux_throughput",
        )
        self.assertEqual(
            profile_bundled_seeded_conflux_ux(bundled_conflux_name),
            "throughput",
        )
        self.assertEqual(
            parse_extra_conflux_ux_values(["throughput", "throughput", "latency"]),
            ["throughput", "latency"],
        )

    def test_resolve_targets_uses_named_pack_or_explicit_override(self) -> None:
        self.assertEqual(resolve_targets("focused", None), DEFAULT_TARGETS)
        self.assertEqual(resolve_targets("broader", None), BROADER_TARGETS)
        self.assertEqual(
            resolve_targets("broader", ["https://example.com/", "https://openai.com/"]),
            ["https://example.com/", "https://openai.com/"],
        )

    def test_profile_run_ok_requires_seed_proof_for_seeded_profile(self) -> None:
        seeded_run = {
            "profile": SEEDED_PROFILE,
            "boot": {"ok": True, "seconds": 2.8},
            "seed_prime": {
                "boot": {"ok": True, "seconds": 14.5},
                "seed_update": {"ok": True, "updated": True},
            },
            "seed_apply": {"ok": True, "applied": True},
            "benchmarks": {
                "https://check.torproject.org/": {
                    "summary": {"ok": True},
                    "runs": [browser_run(ok=True, elapsed_ms=900.0, load_ms=700.0)],
                }
            },
        }

        self.assertTrue(profile_run_ok(seeded_run))

        seeded_run["seed_apply"] = {"ok": True, "applied": False}

        self.assertFalse(profile_run_ok(seeded_run))

        bundled_seeded_run = {
            "profile": BUNDLED_SEEDED_PROFILE,
            "boot": {"ok": True, "seconds": 2.8},
            "seed_prime": {
                "boot": {"ok": True, "seconds": 14.5},
                "seed_update": {"ok": True, "updated": True},
            },
            "seed_apply": {"ok": True, "applied": True},
            "benchmarks": {
                "https://check.torproject.org/": {
                    "summary": {"ok": True},
                    "runs": [browser_run(ok=True, elapsed_ms=900.0, load_ms=700.0)],
                }
            },
        }

        self.assertTrue(profile_run_ok(bundled_seeded_run))

        bundled_seeded_run["seed_prime"] = None

        self.assertFalse(profile_run_ok(bundled_seeded_run))

    def test_run_measured_profile_forwards_browser_request_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            with patch(
                "run_torfast_browser_compare.start_c_tor_profile",
                return_value=(object(), queue.Queue()),
            ), patch(
                "run_torfast_browser_compare.wait_for_line",
                return_value={"ok": True, "seconds": 1.5},
            ), patch(
                "run_torfast_browser_compare.read_torrc_quality",
                return_value={"path": str(run_dir / "torrc")},
            ), patch(
                "run_torfast_browser_compare.run_browser_benchmarks",
                return_value={
                    "https://example.com/": {
                        "summary": {"ok": True},
                        "runs": [],
                    }
                },
            ) as run_browser_benchmarks, patch(
                "run_torfast_browser_compare.stop_process"
            ), patch(
                "run_torfast_browser_compare.record_proxy_output_tail"
            ):
                run_measured_c_tor_browser(
                    profile_name=COLD_PROFILE,
                    run_index=1,
                    run_dir=run_dir,
                    browser_bin=Path("/tmp/firefox"),
                    tor_bin=Path("/tmp/tor"),
                    port=9150,
                    targets=["https://example.com/"],
                    timeout=1.0,
                    window_size="1000,1000",
                    post_boot_wait=0.0,
                    compact_output=False,
                    browser_block_url_substrings=["/static/js/fallback.js"],
                )

        self.assertEqual(
            run_browser_benchmarks.call_args.kwargs["browser_block_url_substrings"],
            ["/static/js/fallback.js"],
        )

    def test_run_measured_profile_forwards_conflux_ux_to_tor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            with patch(
                "run_torfast_browser_compare.start_c_tor_profile",
                return_value=(object(), queue.Queue()),
            ) as start_c_tor_profile, patch(
                "run_torfast_browser_compare.wait_for_line",
                return_value={"ok": True, "seconds": 1.5},
            ), patch(
                "run_torfast_browser_compare.read_torrc_quality",
                return_value={"path": str(run_dir / "torrc")},
            ), patch(
                "run_torfast_browser_compare.run_browser_benchmarks",
                return_value={
                    "https://example.com/": {
                        "summary": {"ok": True},
                        "runs": [],
                    }
                },
            ), patch(
                "run_torfast_browser_compare.stop_process"
            ), patch(
                "run_torfast_browser_compare.record_proxy_output_tail"
            ):
                run_measured_c_tor_browser(
                    profile_name=bundled_seeded_conflux_ux_profile_name("throughput"),
                    run_index=1,
                    run_dir=run_dir,
                    browser_bin=Path("/tmp/firefox"),
                    tor_bin=Path("/tmp/tor"),
                    port=9150,
                    targets=["https://example.com/"],
                    timeout=1.0,
                    window_size="1000,1000",
                    post_boot_wait=0.0,
                    compact_output=False,
                    conflux_client_ux="throughput",
                )

        self.assertEqual(
            start_c_tor_profile.call_args.kwargs["conflux_client_ux"],
            "throughput",
        )

    def test_summarize_profile_runs_adds_boot_to_browser_medians(self) -> None:
        runs = [
            {
                "profile": COLD_PROFILE,
                "boot": {"ok": True, "seconds": 10.0},
                "benchmarks": {
                    "https://check.torproject.org/": {
                        "summary": {"ok": True},
                        "runs": [browser_run(ok=True, elapsed_ms=1200.0, load_ms=800.0)],
                    }
                },
            },
            {
                "profile": COLD_PROFILE,
                "boot": {"ok": True, "seconds": 14.0},
                "benchmarks": {
                    "https://check.torproject.org/": {
                        "summary": {"ok": True},
                        "runs": [browser_run(ok=True, elapsed_ms=1800.0, load_ms=1000.0)],
                    }
                },
            },
        ]

        summary = summarize_profile_runs(runs, ["https://check.torproject.org/"])

        self.assertTrue(summary["ok"])
        self.assertEqual(summary["median_boot_seconds"], 12.0)
        target = summary["targets"]["https://check.torproject.org/"]
        self.assertEqual(target["median_elapsed_ms"], 1500.0)
        self.assertEqual(target["median_load_ms"], 900.0)
        self.assertEqual(target["median_launch_elapsed_ms"], 13500.0)
        self.assertEqual(target["median_launch_load_ms"], 12900.0)

    def test_launch_ready_seconds_prefers_general_circuit_ready(self) -> None:
        run = {
            "boot": {"ok": True, "seconds": 10.0},
            "general_circuit_ready": {"ok": True, "total_ready_seconds": 12.5},
        }

        self.assertEqual(launch_ready_seconds_for_run(run), 12.5)

    def test_launch_ready_seconds_adds_post_boot_wait_when_no_circuit_gate(self) -> None:
        run = {
            "boot": {"ok": True, "seconds": 10.0},
            "post_boot_wait_seconds": 0.5,
        }

        self.assertEqual(launch_ready_seconds_for_run(run), 10.5)

    def test_annotate_general_circuit_ready_adds_total_time(self) -> None:
        boot = {"ok": True, "seconds": 10.0}
        ready = {"ok": True, "seconds": 1.25}

        annotate_general_circuit_ready(boot, ready)

        self.assertEqual(ready["after_boot_seconds"], 1.25)
        self.assertEqual(ready["total_ready_seconds"], 11.25)

    def test_summarize_profile_runs_uses_general_circuit_ready_for_launch_medians(self) -> None:
        runs = [
            {
                "profile": SEEDED_CIRCUIT_READY_PROFILE,
                "boot": {"ok": True, "seconds": 10.0},
                "general_circuit_ready": {
                    "ok": True,
                    "after_boot_seconds": 1.0,
                    "total_ready_seconds": 11.0,
                },
                "seed_prime": {
                    "boot": {"ok": True, "seconds": 8.0},
                    "seed_update": {"ok": True, "updated": True},
                },
                "seed_apply": {"ok": True, "applied": True},
                "benchmarks": {
                    "https://check.torproject.org/": {
                        "summary": {"ok": True},
                        "runs": [browser_run(ok=True, elapsed_ms=1000.0, load_ms=600.0)],
                    }
                },
            },
            {
                "profile": SEEDED_CIRCUIT_READY_PROFILE,
                "boot": {"ok": True, "seconds": 12.0},
                "general_circuit_ready": {
                    "ok": True,
                    "after_boot_seconds": 1.0,
                    "total_ready_seconds": 13.0,
                },
                "seed_prime": {
                    "boot": {"ok": True, "seconds": 8.0},
                    "seed_update": {"ok": True, "updated": True},
                },
                "seed_apply": {"ok": True, "applied": True},
                "benchmarks": {
                    "https://check.torproject.org/": {
                        "summary": {"ok": True},
                        "runs": [browser_run(ok=True, elapsed_ms=2000.0, load_ms=1000.0)],
                    }
                },
            },
        ]

        summary = summarize_profile_runs(runs, ["https://check.torproject.org/"])

        self.assertTrue(summary["ok"])
        self.assertEqual(summary["median_boot_seconds"], 11.0)
        self.assertEqual(summary["median_general_circuit_ready_seconds"], 12.0)
        self.assertEqual(summary["median_general_circuit_post_boot_wait_seconds"], 1.0)
        target = summary["targets"]["https://check.torproject.org/"]
        self.assertEqual(target["median_launch_elapsed_ms"], 13500.0)
        self.assertEqual(target["median_launch_load_ms"], 12800.0)

    def test_short_summary_reports_seeded_deltas_vs_cold(self) -> None:
        payload = {
            "browser_quality": {
                "default_prefs": {"ok": True},
                "no_marionette_fingerprint": {"ok": True},
            },
            "profiles": {
                BUNDLED_PROFILE: {
                    "skipped": True,
                    "reason": "disabled by flag",
                },
                BUNDLED_SEEDED_PROFILE: {
                    "skipped": True,
                    "reason": "disabled by default",
                },
                bundled_seeded_general_circuits_profile_name(2): {
                    "summary": {
                        "ok": True,
                        "runs": 1,
                        "ok_runs": 1,
                        "median_boot_seconds": 3.0,
                        "median_general_circuit_ready_seconds": 3.4,
                        "median_launch_ready_seconds": 3.4,
                        "targets": {
                            "https://check.torproject.org/": {
                                "ok": True,
                                "median_elapsed_ms": 1300.0,
                                "median_load_ms": 780.0,
                                "median_launch_elapsed_ms": 4700.0,
                                "median_launch_load_ms": 4180.0,
                            }
                        },
                    }
                },
                SEEDED_CIRCUIT_READY_PROFILE: {
                    "skipped": True,
                    "reason": "disabled by default",
                },
                seeded_wait_profile_name(0.5): {
                    "summary": {
                        "ok": True,
                        "runs": 1,
                        "ok_runs": 1,
                        "median_boot_seconds": 3.0,
                        "median_launch_ready_seconds": 3.5,
                        "targets": {
                            "https://check.torproject.org/": {
                                "ok": True,
                                "median_elapsed_ms": 1550.0,
                                "median_load_ms": 950.0,
                                "median_launch_elapsed_ms": 5050.0,
                                "median_launch_load_ms": 4450.0,
                            }
                        },
                    }
                },
                COLD_PROFILE: {
                    "summary": {
                        "ok": True,
                        "runs": 1,
                        "ok_runs": 1,
                        "median_boot_seconds": 12.0,
                        "targets": {
                            "https://check.torproject.org/": {
                                "ok": True,
                                "median_elapsed_ms": 1500.0,
                                "median_load_ms": 900.0,
                                "median_launch_elapsed_ms": 13500.0,
                                "median_launch_load_ms": 12900.0,
                            }
                        },
                    }
                },
                SEEDED_PROFILE: {
                    "summary": {
                        "ok": True,
                        "runs": 1,
                        "ok_runs": 1,
                        "median_boot_seconds": 3.0,
                        "median_seed_prime_boot_seconds": 15.0,
                        "targets": {
                            "https://check.torproject.org/": {
                                "ok": True,
                                "median_elapsed_ms": 1600.0,
                                "median_load_ms": 1000.0,
                                "median_launch_elapsed_ms": 4600.0,
                                "median_launch_load_ms": 4000.0,
                            }
                        },
                    }
                },
            },
        }

        summary = short_summary(payload)

        self.assertTrue(payload_ok(payload))
        self.assertTrue(summary["ok"])
        self.assertTrue(summary["profiles"][BUNDLED_PROFILE]["skipped"])
        self.assertTrue(summary["profiles"][BUNDLED_SEEDED_PROFILE]["skipped"])
        self.assertTrue(summary["profiles"][SEEDED_CIRCUIT_READY_PROFILE]["skipped"])
        delta = summary["delta_vs_cold"]["https://check.torproject.org/"]
        self.assertEqual(delta["boot_seconds"], -9.0)
        self.assertEqual(delta["launch_elapsed_ms"], -8900.0)
        self.assertEqual(delta["launch_load_ms"], -8900.0)
        self.assertEqual(delta["elapsed_ms"], 100.0)
        self.assertEqual(delta["load_ms"], 100.0)
        variant_delta = summary["delta_seeded_variants_vs_seeded"][
            seeded_wait_profile_name(0.5)
        ]["https://check.torproject.org/"]
        self.assertEqual(variant_delta["launch_elapsed_ms"], 450.0)
        self.assertEqual(variant_delta["launch_load_ms"], 450.0)

    def test_short_summary_reports_seeded_deltas_vs_bundled(self) -> None:
        payload = {
            "browser_quality": {
                "default_prefs": {"ok": True},
                "no_marionette_fingerprint": {"ok": True},
            },
            "profiles": {
                BUNDLED_PROFILE: {
                    "summary": {
                        "ok": True,
                        "runs": 1,
                        "ok_runs": 1,
                        "median_boot_seconds": 11.0,
                        "targets": {
                            "https://check.torproject.org/": {
                                "ok": True,
                                "median_elapsed_ms": 1700.0,
                                "median_load_ms": 1100.0,
                                "median_launch_elapsed_ms": 12700.0,
                                "median_launch_load_ms": 12100.0,
                            }
                        },
                    }
                },
                BUNDLED_SEEDED_PROFILE: {
                    "summary": {
                        "ok": True,
                        "runs": 1,
                        "ok_runs": 1,
                        "median_boot_seconds": 4.0,
                        "targets": {
                            "https://check.torproject.org/": {
                                "ok": True,
                                "median_elapsed_ms": 1400.0,
                                "median_load_ms": 850.0,
                                "median_launch_elapsed_ms": 5400.0,
                                "median_launch_load_ms": 4850.0,
                            }
                        },
                    }
                },
                bundled_seeded_general_circuits_profile_name(2): {
                    "summary": {
                        "ok": True,
                        "runs": 1,
                        "ok_runs": 1,
                        "median_boot_seconds": 3.5,
                        "median_general_circuit_ready_seconds": 3.8,
                        "median_launch_ready_seconds": 3.8,
                        "targets": {
                            "https://check.torproject.org/": {
                                "ok": True,
                                "median_elapsed_ms": 1300.0,
                                "median_load_ms": 760.0,
                                "median_launch_elapsed_ms": 5100.0,
                                "median_launch_load_ms": 4560.0,
                            }
                        },
                    }
                },
                COLD_PROFILE: {
                    "summary": {
                        "ok": True,
                        "runs": 1,
                        "ok_runs": 1,
                        "median_boot_seconds": 12.0,
                        "targets": {
                            "https://check.torproject.org/": {
                                "ok": True,
                                "median_elapsed_ms": 1500.0,
                                "median_load_ms": 900.0,
                                "median_launch_elapsed_ms": 13500.0,
                                "median_launch_load_ms": 12900.0,
                            }
                        },
                    }
                },
                SEEDED_PROFILE: {
                    "summary": {
                        "ok": True,
                        "runs": 1,
                        "ok_runs": 1,
                        "median_boot_seconds": 3.0,
                        "median_seed_prime_boot_seconds": 15.0,
                        "targets": {
                            "https://check.torproject.org/": {
                                "ok": True,
                                "median_elapsed_ms": 1600.0,
                                "median_load_ms": 1000.0,
                                "median_launch_elapsed_ms": 4600.0,
                                "median_launch_load_ms": 4000.0,
                            }
                        },
                    }
                },
                SEEDED_CIRCUIT_READY_PROFILE: {
                    "skipped": True,
                    "reason": "not used in this fixture",
                },
            },
        }

        summary = short_summary(payload)

        self.assertTrue(payload_ok(payload))
        delta = summary["delta_vs_bundled"]["https://check.torproject.org/"]
        self.assertEqual(delta["boot_seconds"], -8.0)
        self.assertEqual(delta["launch_elapsed_ms"], -8100.0)
        self.assertEqual(delta["launch_load_ms"], -8100.0)
        self.assertEqual(delta["elapsed_ms"], -100.0)
        self.assertEqual(delta["load_ms"], -100.0)
        bundled_seeded_delta = summary["delta_bundled_seeded_vs_bundled"][
            "https://check.torproject.org/"
        ]
        self.assertEqual(bundled_seeded_delta["boot_seconds"], -7.0)
        self.assertEqual(bundled_seeded_delta["launch_elapsed_ms"], -7300.0)
        bundled_variant_delta = summary[
            "delta_bundled_seeded_variants_vs_bundled_seeded"
        ][bundled_seeded_general_circuits_profile_name(2)]["https://check.torproject.org/"]
        self.assertEqual(bundled_variant_delta["launch_elapsed_ms"], -300.0)
        self.assertEqual(bundled_variant_delta["launch_load_ms"], -290.0)
        bundled_seeded_vs_local = summary["delta_bundled_seeded_vs_local_seeded"][
            "https://check.torproject.org/"
        ]
        self.assertEqual(bundled_seeded_vs_local["boot_seconds"], 1.0)
        self.assertEqual(bundled_seeded_vs_local["launch_elapsed_ms"], 800.0)


if __name__ == "__main__":
    unittest.main()
