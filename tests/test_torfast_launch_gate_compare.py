import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from run_torfast_launch_gate_compare import (
    cycle_profile_order,
    delta_vs_baseline,
    launch_gate_extra_wait_seconds,
    launch_gate_ready_text,
    summarize_results,
)


class TorfastLaunchGateCompareTests(unittest.TestCase):
    def test_launch_gate_ready_text_maps_known_gates(self) -> None:
        self.assertEqual(
            launch_gate_ready_text("socks_ready"),
            "Opened Socks listener connection (ready)",
        )
        self.assertEqual(
            launch_gate_ready_text("tor_boot_90"),
            "Bootstrapped 90% (ap_handshake_done): Handshake finished with a relay to build circuits",
        )
        self.assertEqual(
            launch_gate_ready_text("tor_boot_90_plus_200ms"),
            "Bootstrapped 90% (ap_handshake_done): Handshake finished with a relay to build circuits",
        )
        self.assertEqual(
            launch_gate_ready_text("tor_boot_90_plus_400ms"),
            "Bootstrapped 90% (ap_handshake_done): Handshake finished with a relay to build circuits",
        )
        self.assertEqual(
            launch_gate_ready_text("tor_boot_95"),
            "Bootstrapped 95% (circuit_create): Establishing a Tor circuit",
        )
        self.assertEqual(
            launch_gate_ready_text("tor_boot_75"),
            "Bootstrapped 75% (enough_dirinfo): Loaded enough directory info to build circuits",
        )
        self.assertEqual(
            launch_gate_ready_text("tor_boot_100"),
            "Bootstrapped 100%",
        )

    def test_launch_gate_extra_wait_seconds_maps_known_gates(self) -> None:
        self.assertEqual(launch_gate_extra_wait_seconds("tor_boot_90"), 0.0)
        self.assertEqual(launch_gate_extra_wait_seconds("tor_boot_90_plus_200ms"), 0.2)
        self.assertEqual(launch_gate_extra_wait_seconds("tor_boot_90_plus_400ms"), 0.4)
        self.assertEqual(launch_gate_extra_wait_seconds("tor_boot_95"), 0.0)

    def test_cycle_profile_order_rotates(self) -> None:
        gates = [
            "tor_boot_100",
            "tor_boot_95",
            "tor_boot_90_plus_200ms",
            "tor_boot_75",
            "socks_ready",
        ]

        self.assertEqual(
            cycle_profile_order(1, gates),
            [
                "tor_boot_100",
                "tor_boot_95",
                "tor_boot_90_plus_200ms",
                "tor_boot_75",
                "socks_ready",
            ],
        )
        self.assertEqual(
            cycle_profile_order(2, gates),
            [
                "tor_boot_95",
                "tor_boot_90_plus_200ms",
                "tor_boot_75",
                "socks_ready",
                "tor_boot_100",
            ],
        )
        self.assertEqual(
            cycle_profile_order(3, gates),
            [
                "tor_boot_90_plus_200ms",
                "tor_boot_75",
                "socks_ready",
                "tor_boot_100",
                "tor_boot_95",
            ],
        )

    def test_summarize_results_and_deltas(self) -> None:
        target = "https://check.torproject.org/"
        results = [
            {
                "target": target,
                "gate_name": "tor_boot_100",
                "wall_seconds_to_benchmark_end": 5.0,
                "browser_launch_gate": {"seconds": 2.5},
                "torrc": {"isolate_socks_auth": True},
                "boot_after_benchmark": {"ok": True},
                "benchmarks": {
                    target: {
                        "summary": {
                            "ok": True,
                            "median_elapsed_ms": 3000.0,
                            "median_load_ms": 2000.0,
                        }
                    }
                },
            },
            {
                "target": target,
                "gate_name": "tor_boot_90_plus_200ms",
                "wall_seconds_to_benchmark_end": 4.5,
                "browser_launch_gate": {"seconds": 2.2},
                "torrc": {"isolate_socks_auth": True},
                "boot_after_benchmark": {"ok": True},
                "benchmarks": {
                    target: {
                        "summary": {
                            "ok": True,
                            "median_elapsed_ms": 2800.0,
                            "median_load_ms": 1800.0,
                        }
                    }
                },
            },
        ]

        profiles = summarize_results(
            results,
            targets=[target],
            gates=["tor_boot_100", "tor_boot_90_plus_200ms"],
            baseline_gate="tor_boot_100",
        )

        self.assertEqual(
            profiles[target]["tor_boot_100"]["median_wall_seconds_to_benchmark_end"],
            5.0,
        )
        self.assertEqual(
            profiles[target]["tor_boot_90_plus_200ms"]["median_elapsed_ms"],
            2800.0,
        )

        deltas = delta_vs_baseline(
            profiles,
            targets=[target],
            gates=["tor_boot_100", "tor_boot_90_plus_200ms"],
            baseline_gate="tor_boot_100",
        )

        self.assertEqual(
            deltas[target]["tor_boot_100"]["wall_seconds_to_benchmark_end"],
            0.0,
        )
        self.assertEqual(
            deltas[target]["tor_boot_90_plus_200ms"]["wall_seconds_to_benchmark_end"],
            -0.5,
        )
        self.assertEqual(
            deltas[target]["tor_boot_90_plus_200ms"]["elapsed_ms"],
            -200.0,
        )


if __name__ == "__main__":
    unittest.main()
