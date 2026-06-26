import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from run_torfast_warm_open_benchmark_compare import (
    benchmark_elapsed_ms,
    benchmark_load_ms,
    benchmark_summary_for_result,
    build_profile_specs,
    combined_wall_seconds,
    cycle_profile_order,
    delta_vs_baseline,
    parse_extra_wait_values,
    summarize_results,
    waited_profile_name,
)


class TorfastWarmOpenBenchmarkCompareTests(unittest.TestCase):
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
        )

        self.assertEqual(
            specs,
            [
                {
                    "name": "auto",
                    "base_profile_name": "auto",
                    "extra_post_warm_wait_seconds": 0.0,
                },
                {
                    "name": "auto_wait_250ms",
                    "base_profile_name": "auto",
                    "extra_post_warm_wait_seconds": 0.25,
                },
                {
                    "name": "tor_boot_95",
                    "base_profile_name": "tor_boot_95",
                    "extra_post_warm_wait_seconds": 0.0,
                },
                {
                    "name": "tor_boot_95_wait_250ms",
                    "base_profile_name": "tor_boot_95",
                    "extra_post_warm_wait_seconds": 0.25,
                },
            ],
        )

    def test_cycle_profile_order_rotates_and_randomizes_repeatably(self) -> None:
        specs = build_profile_specs(
            profile_names=["auto", "tor_boot_95"],
            extra_post_warm_wait_seconds=[0.25],
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
