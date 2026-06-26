import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from run_torfast_warm_open_compare import (
    build_stop_command,
    build_torfast_command,
    combined_wall_seconds,
    cycle_profile_order,
    delta_vs_baseline,
    open_launch_gate_seconds,
    summarize_results,
)


class TorfastWarmOpenCompareTests(unittest.TestCase):
    def test_cycle_profile_order_rotates(self) -> None:
        profiles = [
            "auto",
            "tor_boot_100",
            "tor_boot_95",
            "tor_boot_90",
            "socks_ready",
        ]

        self.assertEqual(
            cycle_profile_order(1, profiles),
            [
                "auto",
                "tor_boot_100",
                "tor_boot_95",
                "tor_boot_90",
                "socks_ready",
            ],
        )
        self.assertEqual(
            cycle_profile_order(2, profiles),
            [
                "tor_boot_100",
                "tor_boot_95",
                "tor_boot_90",
                "socks_ready",
                "auto",
            ],
        )
        self.assertEqual(
            cycle_profile_order(3, profiles),
            [
                "tor_boot_95",
                "tor_boot_90",
                "socks_ready",
                "auto",
                "tor_boot_100",
            ],
        )

    def test_build_open_command_adds_gate_and_headless(self) -> None:
        command = build_torfast_command(
            action="open",
            state_root=Path("/tmp/state"),
            browser_bin=Path("/tmp/browser"),
            tor_bin=Path("/tmp/tor"),
            target="https://check.torproject.org/",
            port=19450,
            profile_name="tor_boot_95",
            browser_timeout=3.0,
            browser_startup_seed_root=Path("/tmp/browser-seed"),
            browser_startup_seed_enabled=False,
            headed=False,
        )

        self.assertIn("open", command)
        self.assertIn("--browser-launch-gate", command)
        self.assertIn("tor_boot_95", command)
        self.assertIn("--headless", command)
        self.assertIn("--browser-timeout", command)
        self.assertIn("--no-browser-startup-seed", command)

    def test_build_warm_command_keeps_auto_gate_implicit(self) -> None:
        command = build_torfast_command(
            action="warm",
            state_root=Path("/tmp/state"),
            browser_bin=Path("/tmp/browser"),
            tor_bin=Path("/tmp/tor"),
            target="about:tor",
            port=19450,
            profile_name="auto",
            browser_timeout=3.0,
            browser_startup_seed_root=Path("/tmp/browser-seed"),
            browser_startup_seed_enabled=True,
            headed=True,
        )

        self.assertIn("warm", command)
        self.assertNotIn("--browser-launch-gate", command)
        self.assertNotIn("--headless", command)
        self.assertIn("--browser-startup-seed", command)

    def test_build_stop_command(self) -> None:
        command = build_stop_command(Path("/tmp/state"))
        self.assertEqual(command[-3:], ["stop", "--state-root", "/tmp/state"])

    def test_open_launch_gate_seconds_prefers_launch_gate_then_boot(self) -> None:
        self.assertEqual(
            open_launch_gate_seconds(
                {
                    "open_launch": {
                        "tor_browser_launch_gate": {"seconds": 1.234},
                        "tor_boot": {"seconds": 2.0},
                    }
                }
            ),
            1.234,
        )
        self.assertEqual(
            open_launch_gate_seconds(
                {
                    "open_launch": {
                        "tor_boot": {"seconds": 2.0},
                    }
                }
            ),
            2.0,
        )

    def test_combined_wall_seconds_adds_warm_and_open(self) -> None:
        result = {
            "warm": {"wall_seconds": 0.25},
            "open": {"wall_seconds": 3.75},
        }

        self.assertEqual(combined_wall_seconds(result), 4.0)

    def test_summarize_results_and_deltas(self) -> None:
        target = "https://check.torproject.org/"
        results = [
            {
                "target": target,
                "profile_name": "auto",
                "warm": {"ok": True, "wall_seconds": 0.25},
                "warm_launch": {"tor_managed_ready": {"ok": True, "gate": "tor_boot_95", "seconds": 0.2}},
                "open": {"ok": True, "wall_seconds": 5.5},
                "open_launch": {
                    "browser": {"ok": True, "elapsed_seconds": 3.0},
                    "browser_launch_gate": "tor_boot_95",
                    "tor_browser_launch_gate": {"gate": "tor_boot_95", "seconds": 1.8},
                    "tor_boot": {"ok": True, "seconds": 2.1},
                    "torrc_quality": {"isolate_socks_auth": True},
                    "reused_tor_service": {"pid": 1234, "ready_gate": "tor_boot_100"},
                },
                "stop": {"ok": True},
            },
            {
                "target": target,
                "profile_name": "tor_boot_100",
                "warm": {"ok": True, "wall_seconds": 2.0},
                "warm_launch": {"tor_managed_ready": {"ok": True, "gate": "tor_boot_100", "seconds": 1.9}},
                "open": {"ok": True, "wall_seconds": 6.0},
                "open_launch": {
                    "browser": {"ok": True, "elapsed_seconds": 3.0},
                    "browser_launch_gate": "tor_boot_100",
                    "tor_boot": {"ok": True, "seconds": 2.0},
                    "torrc_quality": {"isolate_socks_auth": True},
                    "reused_tor_service": {"pid": 1235, "ready_gate": "tor_boot_100"},
                },
                "stop": {"ok": True},
            },
        ]

        profiles = summarize_results(
            results,
            targets=[target],
            profile_names=["auto", "tor_boot_100"],
        )

        self.assertEqual(
            profiles[target]["auto"]["median_warm_wall_seconds"],
            0.25,
        )
        self.assertEqual(
            profiles[target]["auto"]["median_combined_wall_seconds"],
            5.75,
        )
        self.assertEqual(
            profiles[target]["tor_boot_100"]["median_open_launch_gate_seconds"],
            2.0,
        )

        deltas = delta_vs_baseline(
            profiles,
            targets=[target],
            profile_names=["auto", "tor_boot_100"],
            baseline_profile="tor_boot_100",
        )

        self.assertEqual(
            deltas[target]["auto"]["combined_wall_seconds"],
            -2.25,
        )
        self.assertEqual(
            deltas[target]["tor_boot_100"]["combined_wall_seconds"],
            0.0,
        )


if __name__ == "__main__":
    unittest.main()
