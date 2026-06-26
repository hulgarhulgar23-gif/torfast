import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from run_torfast_runtime_compare import (
    derive_run_metrics,
    parse_first_json_object,
    seeded_launch_order_for_run,
    short_summary,
    summarize_profile_runs,
    tail_lines,
)


class TorfastRuntimeCompareTests(unittest.TestCase):
    def test_derive_run_metrics_for_cold_launch(self) -> None:
        run = {
            "exit_code": 0,
            "wall_seconds": 14.5,
            "launch": {
                "browser": {
                    "ok": True,
                    "elapsed_seconds": 6.2,
                    "timed_out": True,
                },
                "tor_boot": {
                    "ok": True,
                    "seconds": 8.0,
                },
                "browser_startup_seed_apply": {"applied": True},
                "reused_tor_service": None,
            },
        }

        metrics = derive_run_metrics(run, browser_timeout_seconds=6.0)

        self.assertTrue(metrics["ok"])
        self.assertFalse(metrics["reused_tor_service"])
        self.assertTrue(metrics["browser_startup_seed_applied"])
        self.assertEqual(metrics["tor_boot_seconds"], 8.0)
        self.assertEqual(metrics["launch_overhead_seconds"], 8.5)
        self.assertEqual(metrics["post_boot_browser_overhead_seconds"], 0.5)

    def test_derive_run_metrics_for_reused_service_defaults_boot_to_zero(self) -> None:
        run = {
            "exit_code": 0,
            "wall_seconds": 6.4,
            "launch": {
                "browser": {
                    "ok": True,
                    "elapsed_seconds": 6.1,
                    "timed_out": True,
                },
                "tor_boot": {
                    "ok": True,
                    "reused_service": True,
                },
                "reused_tor_service": {"pid": 1234},
            },
        }

        metrics = derive_run_metrics(run, browser_timeout_seconds=6.0)

        self.assertTrue(metrics["ok"])
        self.assertTrue(metrics["reused_tor_service"])
        self.assertEqual(metrics["tor_boot_seconds"], 0.0)
        self.assertEqual(metrics["launch_overhead_seconds"], 0.4)
        self.assertEqual(metrics["post_boot_browser_overhead_seconds"], 0.4)

    def test_derive_run_metrics_does_not_mark_new_warm_service_as_reused(self) -> None:
        run = {
            "exit_code": 0,
            "wall_seconds": 17.0,
            "launch": {
                "browser": {
                    "ok": True,
                    "elapsed_seconds": 6.0,
                    "timed_out": True,
                },
                "tor_boot": {
                    "ok": True,
                    "seconds": 10.5,
                },
                "reused_tor_service": {"pid": 1234},
            },
        }

        metrics = derive_run_metrics(run, browser_timeout_seconds=6.0)

        self.assertFalse(metrics["reused_tor_service"])
        self.assertEqual(metrics["tor_boot_seconds"], 10.5)

    def test_derive_run_metrics_for_prime_does_not_subtract_browser_timeout(self) -> None:
        run = {
            "exit_code": 0,
            "wall_seconds": 8.5,
            "launch": {
                "browser": {
                    "ok": True,
                    "skipped": True,
                    "timed_out": False,
                },
                "tor_boot": {
                    "ok": True,
                    "seconds": 8.0,
                },
            },
        }

        metrics = derive_run_metrics(run, browser_timeout_seconds=6.0)

        self.assertTrue(metrics["ok"])
        self.assertEqual(metrics["launch_overhead_seconds"], 8.5)
        self.assertEqual(metrics["post_boot_browser_overhead_seconds"], 0.5)

    def test_summarize_profile_runs_computes_medians(self) -> None:
        runs = [
            {"metrics": {"ok": True, "reused_tor_service": False, "timed_out": True, "wall_seconds": 10.0, "tor_boot_seconds": 4.0, "browser_elapsed_seconds": 6.0, "browser_startup_seed_applied": True, "launch_overhead_seconds": 4.0, "post_boot_browser_overhead_seconds": 0.0}},
            {"metrics": {"ok": True, "reused_tor_service": False, "timed_out": True, "wall_seconds": 12.0, "tor_boot_seconds": 6.0, "browser_elapsed_seconds": 6.0, "browser_startup_seed_applied": False, "launch_overhead_seconds": 6.0, "post_boot_browser_overhead_seconds": 0.0}},
        ]

        summary = summarize_profile_runs(runs)

        self.assertTrue(summary["ok"])
        self.assertEqual(summary["runs"], 2)
        self.assertEqual(summary["ok_runs"], 2)
        self.assertEqual(summary["browser_startup_seed_applied_runs"], 1)
        self.assertEqual(summary["median_elapsed_ms"], 11000.0)
        self.assertEqual(summary["median_tor_boot_seconds"], 5.0)
        self.assertEqual(summary["min_elapsed_ms"], 10000.0)
        self.assertEqual(summary["max_elapsed_ms"], 12000.0)

    def test_summarize_profile_runs_keeps_prime_medians(self) -> None:
        runs = [
            {"metrics": {"ok": True, "reused_tor_service": False, "timed_out": True, "wall_seconds": 5.0, "tor_boot_seconds": 2.0, "browser_elapsed_seconds": 3.0, "launch_overhead_seconds": 2.0, "post_boot_browser_overhead_seconds": 0.0, "prime_wall_seconds": 11.0, "prime_tor_boot_seconds": 10.0}},
            {"metrics": {"ok": True, "reused_tor_service": False, "timed_out": True, "wall_seconds": 7.0, "tor_boot_seconds": 3.0, "browser_elapsed_seconds": 3.0, "launch_overhead_seconds": 4.0, "post_boot_browser_overhead_seconds": 1.0, "prime_wall_seconds": 13.0, "prime_tor_boot_seconds": 12.0}},
        ]

        summary = summarize_profile_runs(runs)

        self.assertEqual(summary["median_prime_wall_seconds"], 12.0)
        self.assertEqual(summary["median_prime_tor_boot_seconds"], 11.0)

    def test_short_summary_requires_all_profiles_ok(self) -> None:
        payload = {
            "url": "about:tor",
            "browser_timeout_seconds": 6.0,
            "profiles": {
                "cold_launch": {"summary": {"ok": True}},
                "seeded_launch": {
                    "summary": {
                        "ok": True,
                        "median_elapsed_ms": 8000.0,
                        "median_tor_boot_seconds": 2.5,
                        "median_launch_overhead_seconds": 2.0,
                        "median_post_boot_browser_overhead_seconds": 0.3,
                    }
                },
                "seeded_launch_no_browser_startup_seed": {
                    "summary": {
                        "ok": True,
                        "median_elapsed_ms": 8600.0,
                        "median_tor_boot_seconds": 2.5,
                        "median_launch_overhead_seconds": 2.6,
                        "median_post_boot_browser_overhead_seconds": 0.9,
                    }
                },
                "warm_seed": {"summary": {"ok": True}},
                "warm_reuse": {"summary": {"ok": False}},
            },
        }

        summary = short_summary(payload)

        self.assertFalse(summary["ok"])
        self.assertEqual(summary["url"], "about:tor")
        self.assertEqual(
            summary["delta_seeded_launch_vs_no_browser_startup_seed"],
            {
                "elapsed_ms": -600.0,
                "tor_boot_seconds": 0.0,
                "launch_overhead_seconds": -0.6,
                "post_boot_browser_overhead_seconds": -0.6,
            },
        )

    def test_parse_first_json_object_returns_dict(self) -> None:
        payload = parse_first_json_object('{"ok": true, "stopped": false}\n')

        self.assertEqual(payload, {"ok": True, "stopped": False})

    def test_tail_lines_omits_blank_lines(self) -> None:
        lines = tail_lines("one\n\ntwo\nthree\n", limit=2)

        self.assertEqual(lines, ["two", "three"])

    def test_seeded_launch_order_rotates_by_run_index(self) -> None:
        self.assertEqual(
            seeded_launch_order_for_run(1),
            ["seeded_launch", "seeded_launch_no_browser_startup_seed"],
        )
        self.assertEqual(
            seeded_launch_order_for_run(2),
            ["seeded_launch_no_browser_startup_seed", "seeded_launch"],
        )


if __name__ == "__main__":
    unittest.main()
