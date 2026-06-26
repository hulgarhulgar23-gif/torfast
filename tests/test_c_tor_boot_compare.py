import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from run_c_tor_boot_compare import (
    CTorBootProfile,
    compare_profiles,
    ordered_profiles_for_run,
    render_torrc,
    select_profiles,
    summarize_runs,
)


class CTorBootCompareTests(unittest.TestCase):
    def test_render_torrc_keeps_quality_defaults_and_extra_lines(self) -> None:
        profile = CTorBootProfile(
            "authdelay0_maxtries5",
            (
                "ClientBootstrapConsensusAuthorityDownloadInitialDelay 0",
                "ClientBootstrapConsensusMaxInProgressTries 5",
            ),
        )

        torrc = render_torrc(profile, port=19800, data_dir=Path("/tmp/c-tor-boot"))

        self.assertIn("SocksPort 127.0.0.1:19800 IsolateSOCKSAuth", torrc)
        self.assertIn("ClientOnly 1", torrc)
        self.assertIn("AvoidDiskWrites 1", torrc)
        self.assertIn("SafeLogging 1", torrc)
        self.assertIn("ConfluxEnabled auto", torrc)
        self.assertIn("ClientBootstrapConsensusAuthorityDownloadInitialDelay 0", torrc)
        self.assertIn("ClientBootstrapConsensusMaxInProgressTries 5", torrc)

    def test_summarize_runs_calculates_medians(self) -> None:
        runs = [
            {"boot": {"ok": True, "seconds": 10.0}},
            {"boot": {"ok": True, "seconds": 14.0}},
            {"boot": {"ok": True, "seconds": 12.0}},
        ]

        summary = summarize_runs(runs)

        self.assertTrue(summary["ok"])
        self.assertEqual(summary["runs"], 3)
        self.assertEqual(summary["ok_runs"], 3)
        self.assertEqual(summary["median_boot_seconds"], 12.0)
        self.assertEqual(summary["min_boot_seconds"], 10.0)
        self.assertEqual(summary["max_boot_seconds"], 14.0)

    def test_compare_profiles_reports_deltas_and_fastest(self) -> None:
        profiles = {
            "stock": {"summary": {"median_boot_seconds": 15.0}},
            "authdelay0": {"summary": {"median_boot_seconds": 12.5}},
            "maxtries5": {"summary": {"median_boot_seconds": 13.0}},
            "authdelay0_maxtries5": {"summary": {"median_boot_seconds": 11.75}},
        }

        comparison = compare_profiles(profiles)

        self.assertEqual(comparison["authdelay0_minus_stock_seconds"], -2.5)
        self.assertEqual(comparison["maxtries5_minus_stock_seconds"], -2.0)
        self.assertEqual(
            comparison["authdelay0_maxtries5_minus_stock_seconds"], -3.25
        )
        self.assertEqual(comparison["fastest_profile"], "authdelay0_maxtries5")
        self.assertEqual(comparison["fastest_profile_median_boot_seconds"], 11.75)

    def test_select_profiles_filters_and_preserves_order(self) -> None:
        profiles = select_profiles("authdelay0,stock,missing")

        self.assertEqual([profile.name for profile in profiles], ["authdelay0", "stock"])

    def test_ordered_profiles_for_run_rotates_each_cycle(self) -> None:
        profiles = [
            CTorBootProfile("stock"),
            CTorBootProfile("authdelay0"),
            CTorBootProfile("maxtries5"),
        ]

        run1 = ordered_profiles_for_run(profiles, 1)
        run2 = ordered_profiles_for_run(profiles, 2)
        run3 = ordered_profiles_for_run(profiles, 3)

        self.assertEqual([profile.name for profile in run1], ["stock", "authdelay0", "maxtries5"])
        self.assertEqual([profile.name for profile in run2], ["authdelay0", "maxtries5", "stock"])
        self.assertEqual([profile.name for profile in run3], ["maxtries5", "stock", "authdelay0"])


if __name__ == "__main__":
    unittest.main()
