import sys
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from run_torfast_warm_open_compare import (
    adaptive_general_circuit_wait_seconds,
    adaptive_general_circuit_wait_variant_profile_name,
    async_browser_reset_variant_profile_name,
    browser_startup_seed_variant_profile_name,
    build_parser,
    build_profile_specs,
    build_stop_command,
    build_torfast_command,
    build_wait_ready_command,
    combined_wall_seconds,
    control_bootstrap_probe_variant_profile_name,
    conflux_variant_profile_name,
    cycle_profile_order,
    delta_vs_baseline,
    managed_open_adaptive_general_circuit_wait_variant_profile_name,
    managed_service_metadata_wait_variant_profile_name,
    maybe_wait_for_managed_general_circuit,
    next_available_port,
    open_launch_gate_seconds,
    parse_extra_adaptive_general_circuit_wait_timeout_values,
    parse_extra_wait_values,
    parse_json_text,
    port_is_available,
    persistent_control_wait_variant_profile_name,
    result_ok,
    summarize_results,
    torfast_command_env,
    total_wall_seconds,
    waited_profile_name,
    warm_browser_prestart_variant_profile_name,
    warm_helper_prestart_variant_profile_name,
)


class TorfastWarmOpenCompareTests(unittest.TestCase):
    def test_parser_defaults_managed_open_browser_overlap_on(self) -> None:
        args = build_parser().parse_args([])

        self.assertTrue(args.managed_open_browser_overlap)

    def test_parser_can_disable_managed_open_browser_overlap(self) -> None:
        args = build_parser().parse_args(["--no-managed-open-browser-overlap"])

        self.assertFalse(args.managed_open_browser_overlap)

    def test_cycle_profile_order_rotates(self) -> None:
        profiles = build_profile_specs(
            profile_names=[
                "auto",
                "tor_boot_100",
                "tor_boot_95",
                "tor_boot_90",
                "socks_ready",
            ],
            extra_post_warm_wait_seconds=[],
        )

        self.assertEqual(
            cycle_profile_order(1, profiles),
            [
                {"name": "auto", "base_profile_name": "auto", "extra_post_warm_wait_seconds": 0.0, "conflux_client_ux": None},
                {"name": "tor_boot_100", "base_profile_name": "tor_boot_100", "extra_post_warm_wait_seconds": 0.0, "conflux_client_ux": None},
                {"name": "tor_boot_95", "base_profile_name": "tor_boot_95", "extra_post_warm_wait_seconds": 0.0, "conflux_client_ux": None},
                {"name": "tor_boot_90", "base_profile_name": "tor_boot_90", "extra_post_warm_wait_seconds": 0.0, "conflux_client_ux": None},
                {"name": "socks_ready", "base_profile_name": "socks_ready", "extra_post_warm_wait_seconds": 0.0, "conflux_client_ux": None},
            ],
        )
        self.assertEqual(
            cycle_profile_order(2, profiles),
            [
                {"name": "tor_boot_100", "base_profile_name": "tor_boot_100", "extra_post_warm_wait_seconds": 0.0, "conflux_client_ux": None},
                {"name": "tor_boot_95", "base_profile_name": "tor_boot_95", "extra_post_warm_wait_seconds": 0.0, "conflux_client_ux": None},
                {"name": "tor_boot_90", "base_profile_name": "tor_boot_90", "extra_post_warm_wait_seconds": 0.0, "conflux_client_ux": None},
                {"name": "socks_ready", "base_profile_name": "socks_ready", "extra_post_warm_wait_seconds": 0.0, "conflux_client_ux": None},
                {"name": "auto", "base_profile_name": "auto", "extra_post_warm_wait_seconds": 0.0, "conflux_client_ux": None},
            ],
        )
        self.assertEqual(
            cycle_profile_order(3, profiles),
            [
                {"name": "tor_boot_95", "base_profile_name": "tor_boot_95", "extra_post_warm_wait_seconds": 0.0, "conflux_client_ux": None},
                {"name": "tor_boot_90", "base_profile_name": "tor_boot_90", "extra_post_warm_wait_seconds": 0.0, "conflux_client_ux": None},
                {"name": "socks_ready", "base_profile_name": "socks_ready", "extra_post_warm_wait_seconds": 0.0, "conflux_client_ux": None},
                {"name": "auto", "base_profile_name": "auto", "extra_post_warm_wait_seconds": 0.0, "conflux_client_ux": None},
                {"name": "tor_boot_100", "base_profile_name": "tor_boot_100", "extra_post_warm_wait_seconds": 0.0, "conflux_client_ux": None},
            ],
        )

    def test_parse_extra_wait_values_and_profile_specs(self) -> None:
        waits = parse_extra_wait_values(["5", "1.5", "5.000"])
        self.assertEqual(waits, [5.0, 1.5])
        self.assertEqual(waited_profile_name("auto", 1.5), "auto_wait_1p5s")
        self.assertEqual(
            conflux_variant_profile_name("auto_wait_1p5s", "throughput_lowmem"),
            "auto_wait_1p5s_confluxux_throughput_lowmem",
        )

        specs = build_profile_specs(
            profile_names=["auto"],
            extra_post_warm_wait_seconds=waits,
        )

        self.assertEqual(
            specs,
            [
                {
                    "name": "auto",
                    "base_profile_name": "auto",
                    "extra_post_warm_wait_seconds": 0.0,
                    "conflux_client_ux": None,
                },
                {
                    "name": "auto_wait_5s",
                    "base_profile_name": "auto",
                    "extra_post_warm_wait_seconds": 5.0,
                    "conflux_client_ux": None,
                },
                {
                    "name": "auto_wait_1p5s",
                    "base_profile_name": "auto",
                    "extra_post_warm_wait_seconds": 1.5,
                    "conflux_client_ux": None,
                },
            ],
        )

    def test_parse_extra_adaptive_general_circuit_wait_timeout_values(self) -> None:
        timeouts = parse_extra_adaptive_general_circuit_wait_timeout_values(
            ["0.5", "1", "0.500", "0.1256", "0.1260"]
        )

        self.assertEqual(timeouts, [0.5, 1.0, 0.1256, 0.126])
        self.assertEqual(
            adaptive_general_circuit_wait_variant_profile_name("auto", 0.5),
            "auto_adaptivegencirc_0p5s",
        )
        self.assertEqual(
            adaptive_general_circuit_wait_variant_profile_name("auto", 0.1256),
            "auto_adaptivegencirc_0p1256s",
        )
        self.assertEqual(
            managed_open_adaptive_general_circuit_wait_variant_profile_name(
                "auto",
                0.1256,
            ),
            "auto_managedadaptivegencirc_0p1256s",
        )

    def test_build_profile_specs_adds_conflux_variants(self) -> None:
        specs = build_profile_specs(
            profile_names=["auto"],
            extra_post_warm_wait_seconds=[1.5],
            extra_conflux_client_ux=["throughput_lowmem"],
        )

        self.assertEqual(
            specs,
            [
                {
                    "name": "auto",
                    "base_profile_name": "auto",
                    "extra_post_warm_wait_seconds": 0.0,
                    "conflux_client_ux": None,
                },
                {
                    "name": "auto_wait_1p5s",
                    "base_profile_name": "auto",
                    "extra_post_warm_wait_seconds": 1.5,
                    "conflux_client_ux": None,
                },
                {
                    "name": "auto_confluxux_throughput_lowmem",
                    "base_profile_name": "auto",
                    "extra_post_warm_wait_seconds": 0.0,
                    "conflux_client_ux": "throughput_lowmem",
                },
                {
                    "name": "auto_wait_1p5s_confluxux_throughput_lowmem",
                    "base_profile_name": "auto",
                    "extra_post_warm_wait_seconds": 1.5,
                    "conflux_client_ux": "throughput_lowmem",
                },
            ],
        )

    def test_build_profile_specs_can_add_adaptive_general_circuit_wait_variants(
        self,
    ) -> None:
        specs = build_profile_specs(
            profile_names=["auto"],
            extra_post_warm_wait_seconds=[1.5],
            extra_adaptive_general_circuit_wait_timeout_seconds=[0.5],
        )

        self.assertEqual(
            specs,
            [
                {
                    "name": "auto",
                    "base_profile_name": "auto",
                    "extra_post_warm_wait_seconds": 0.0,
                    "conflux_client_ux": None,
                },
                {
                    "name": "auto_wait_1p5s",
                    "base_profile_name": "auto",
                    "extra_post_warm_wait_seconds": 1.5,
                    "conflux_client_ux": None,
                },
                {
                    "name": "auto_adaptivegencirc_0p5s",
                    "base_profile_name": "auto",
                    "extra_post_warm_wait_seconds": 0.0,
                    "conflux_client_ux": None,
                    "adaptive_general_circuit_wait_timeout_seconds": 0.5,
                },
                {
                    "name": "auto_wait_1p5s_adaptivegencirc_0p5s",
                    "base_profile_name": "auto",
                    "extra_post_warm_wait_seconds": 1.5,
                    "conflux_client_ux": None,
                    "adaptive_general_circuit_wait_timeout_seconds": 0.5,
                },
            ],
        )

    def test_build_profile_specs_can_add_managed_open_adaptive_wait_variants(
        self,
    ) -> None:
        specs = build_profile_specs(
            profile_names=["auto"],
            extra_post_warm_wait_seconds=[1.5],
            extra_managed_open_adaptive_general_circuit_wait_timeout_seconds=[0.75],
        )

        self.assertEqual(
            managed_open_adaptive_general_circuit_wait_variant_profile_name(
                "auto",
                0.75,
            ),
            "auto_managedadaptivegencirc_0p75s",
        )
        self.assertIn(
            {
                "name": "auto_managedadaptivegencirc_0p75s",
                "base_profile_name": "auto",
                "extra_post_warm_wait_seconds": 0.0,
                "conflux_client_ux": None,
                "managed_open_adaptive_general_circuit_wait_timeout_seconds": 0.75,
            },
            specs,
        )
        self.assertIn(
            {
                "name": "auto_wait_1p5s_managedadaptivegencirc_0p75s",
                "base_profile_name": "auto",
                "extra_post_warm_wait_seconds": 1.5,
                "conflux_client_ux": None,
                "managed_open_adaptive_general_circuit_wait_timeout_seconds": 0.75,
            },
            specs,
        )

    def test_build_profile_specs_keeps_distinct_fine_grained_managed_open_variants(
        self,
    ) -> None:
        specs = build_profile_specs(
            profile_names=["auto"],
            extra_post_warm_wait_seconds=[],
            extra_managed_open_adaptive_general_circuit_wait_timeout_seconds=[
                0.1256,
                0.126,
            ],
        )

        self.assertEqual(
            [spec["name"] for spec in specs],
            [
                "auto",
                "auto_managedadaptivegencirc_0p1256s",
                "auto_managedadaptivegencirc_0p126s",
            ],
        )

    def test_build_profile_specs_can_add_no_settle_variants(self) -> None:
        specs = build_profile_specs(
            profile_names=["auto"],
            extra_post_warm_wait_seconds=[1.5],
            base_managed_open_settle_enabled=True,
            extra_no_managed_open_settle=True,
        )

        self.assertEqual(
            specs,
            [
                {
                    "name": "auto",
                    "base_profile_name": "auto",
                    "extra_post_warm_wait_seconds": 0.0,
                    "conflux_client_ux": None,
                },
                {
                    "name": "auto_wait_1p5s",
                    "base_profile_name": "auto",
                    "extra_post_warm_wait_seconds": 1.5,
                    "conflux_client_ux": None,
                },
                {
                    "name": "auto_nosettle",
                    "base_profile_name": "auto",
                    "extra_post_warm_wait_seconds": 0.0,
                    "conflux_client_ux": None,
                    "managed_open_settle_enabled": False,
                },
                {
                    "name": "auto_wait_1p5s_nosettle",
                    "base_profile_name": "auto",
                    "extra_post_warm_wait_seconds": 1.5,
                    "conflux_client_ux": None,
                    "managed_open_settle_enabled": False,
                },
            ],
        )

    def test_build_profile_specs_can_add_no_overlap_variants(self) -> None:
        specs = build_profile_specs(
            profile_names=["auto"],
            extra_post_warm_wait_seconds=[1.5],
            base_managed_open_browser_overlap_enabled=True,
            extra_no_managed_open_browser_overlap=True,
        )

        self.assertEqual(
            specs,
            [
                {
                    "name": "auto",
                    "base_profile_name": "auto",
                    "extra_post_warm_wait_seconds": 0.0,
                    "conflux_client_ux": None,
                },
                {
                    "name": "auto_wait_1p5s",
                    "base_profile_name": "auto",
                    "extra_post_warm_wait_seconds": 1.5,
                    "conflux_client_ux": None,
                },
                {
                    "name": "auto_nooverlap",
                    "base_profile_name": "auto",
                    "extra_post_warm_wait_seconds": 0.0,
                    "conflux_client_ux": None,
                    "managed_open_browser_overlap_enabled": False,
                },
                {
                    "name": "auto_wait_1p5s_nooverlap",
                    "base_profile_name": "auto",
                    "extra_post_warm_wait_seconds": 1.5,
                    "conflux_client_ux": None,
                    "managed_open_browser_overlap_enabled": False,
                },
            ],
        )

    def test_build_profile_specs_can_add_browser_startup_seed_variants(self) -> None:
        self.assertEqual(
            browser_startup_seed_variant_profile_name(
                "auto",
                browser_startup_seed_enabled=True,
            ),
            "auto_browserstartupseed",
        )
        specs = build_profile_specs(
            profile_names=["auto"],
            extra_post_warm_wait_seconds=[1.5],
            extra_browser_startup_seed=True,
        )

        self.assertEqual(
            specs,
            [
                {
                    "name": "auto",
                    "base_profile_name": "auto",
                    "extra_post_warm_wait_seconds": 0.0,
                    "conflux_client_ux": None,
                },
                {
                    "name": "auto_wait_1p5s",
                    "base_profile_name": "auto",
                    "extra_post_warm_wait_seconds": 1.5,
                    "conflux_client_ux": None,
                },
                {
                    "name": "auto_browserstartupseed",
                    "base_profile_name": "auto",
                    "extra_post_warm_wait_seconds": 0.0,
                    "conflux_client_ux": None,
                    "browser_startup_seed_enabled": True,
                },
                {
                    "name": "auto_wait_1p5s_browserstartupseed",
                    "base_profile_name": "auto",
                    "extra_post_warm_wait_seconds": 1.5,
                    "conflux_client_ux": None,
                    "browser_startup_seed_enabled": True,
                },
            ],
        )

    def test_build_profile_specs_can_add_no_browser_startup_seed_variants(
        self,
    ) -> None:
        self.assertEqual(
            browser_startup_seed_variant_profile_name(
                "auto",
                browser_startup_seed_enabled=False,
            ),
            "auto_nobrowserstartupseed",
        )
        specs = build_profile_specs(
            profile_names=["auto"],
            extra_post_warm_wait_seconds=[1.5],
            base_browser_startup_seed_enabled=True,
            extra_no_browser_startup_seed=True,
        )

        self.assertEqual(
            specs,
            [
                {
                    "name": "auto",
                    "base_profile_name": "auto",
                    "extra_post_warm_wait_seconds": 0.0,
                    "conflux_client_ux": None,
                },
                {
                    "name": "auto_wait_1p5s",
                    "base_profile_name": "auto",
                    "extra_post_warm_wait_seconds": 1.5,
                    "conflux_client_ux": None,
                },
                {
                    "name": "auto_nobrowserstartupseed",
                    "base_profile_name": "auto",
                    "extra_post_warm_wait_seconds": 0.0,
                    "conflux_client_ux": None,
                    "browser_startup_seed_enabled": False,
                },
                {
                    "name": "auto_wait_1p5s_nobrowserstartupseed",
                    "base_profile_name": "auto",
                    "extra_post_warm_wait_seconds": 1.5,
                    "conflux_client_ux": None,
                    "browser_startup_seed_enabled": False,
                },
            ],
        )

    def test_build_profile_specs_can_add_no_persistent_control_wait_variants(
        self,
    ) -> None:
        self.assertEqual(
            persistent_control_wait_variant_profile_name(
                "auto",
                persistent_control_wait_enabled=False,
            ),
            "auto_nopersistctrl",
        )
        specs = build_profile_specs(
            profile_names=["auto"],
            extra_post_warm_wait_seconds=[1.5],
            base_persistent_control_wait_enabled=True,
            extra_no_persistent_control_wait=True,
        )

        self.assertEqual(
            specs,
            [
                {
                    "name": "auto",
                    "base_profile_name": "auto",
                    "extra_post_warm_wait_seconds": 0.0,
                    "conflux_client_ux": None,
                },
                {
                    "name": "auto_wait_1p5s",
                    "base_profile_name": "auto",
                    "extra_post_warm_wait_seconds": 1.5,
                    "conflux_client_ux": None,
                },
                {
                    "name": "auto_nopersistctrl",
                    "base_profile_name": "auto",
                    "extra_post_warm_wait_seconds": 0.0,
                    "conflux_client_ux": None,
                    "persistent_control_wait_enabled": False,
                },
                {
                    "name": "auto_wait_1p5s_nopersistctrl",
                    "base_profile_name": "auto",
                    "extra_post_warm_wait_seconds": 1.5,
                    "conflux_client_ux": None,
                    "persistent_control_wait_enabled": False,
                },
            ],
        )

    def test_build_profile_specs_can_add_no_control_bootstrap_probe_variants(
        self,
    ) -> None:
        self.assertEqual(
            control_bootstrap_probe_variant_profile_name(
                "auto",
                control_bootstrap_probe_enabled=False,
            ),
            "auto_nocontrolprobe",
        )
        specs = build_profile_specs(
            profile_names=["auto"],
            extra_post_warm_wait_seconds=[1.5],
            extra_no_control_bootstrap_probe=True,
        )

        self.assertEqual(
            specs,
            [
                {
                    "name": "auto",
                    "base_profile_name": "auto",
                    "extra_post_warm_wait_seconds": 0.0,
                    "conflux_client_ux": None,
                },
                {
                    "name": "auto_wait_1p5s",
                    "base_profile_name": "auto",
                    "extra_post_warm_wait_seconds": 1.5,
                    "conflux_client_ux": None,
                },
                {
                    "name": "auto_nocontrolprobe",
                    "base_profile_name": "auto",
                    "extra_post_warm_wait_seconds": 0.0,
                    "conflux_client_ux": None,
                    "control_bootstrap_probe_enabled": False,
                },
                {
                    "name": "auto_wait_1p5s_nocontrolprobe",
                    "base_profile_name": "auto",
                    "extra_post_warm_wait_seconds": 1.5,
                    "conflux_client_ux": None,
                    "control_bootstrap_probe_enabled": False,
                },
            ],
        )

    def test_build_profile_specs_can_add_no_async_browser_reset_variants(
        self,
    ) -> None:
        self.assertEqual(
            async_browser_reset_variant_profile_name(
                "auto",
                async_browser_reset_enabled=False,
            ),
            "auto_noasyncreset",
        )
        specs = build_profile_specs(
            profile_names=["auto"],
            extra_post_warm_wait_seconds=[1.5],
            extra_no_async_browser_reset=True,
        )

        self.assertEqual(
            specs,
            [
                {
                    "name": "auto",
                    "base_profile_name": "auto",
                    "extra_post_warm_wait_seconds": 0.0,
                    "conflux_client_ux": None,
                },
                {
                    "name": "auto_wait_1p5s",
                    "base_profile_name": "auto",
                    "extra_post_warm_wait_seconds": 1.5,
                    "conflux_client_ux": None,
                },
                {
                    "name": "auto_noasyncreset",
                    "base_profile_name": "auto",
                    "extra_post_warm_wait_seconds": 0.0,
                    "conflux_client_ux": None,
                    "async_browser_reset_enabled": False,
                },
                {
                    "name": "auto_wait_1p5s_noasyncreset",
                    "base_profile_name": "auto",
                    "extra_post_warm_wait_seconds": 1.5,
                    "conflux_client_ux": None,
                    "async_browser_reset_enabled": False,
                },
            ],
        )

    def test_build_profile_specs_can_add_no_service_metadata_wait_variants(
        self,
    ) -> None:
        self.assertEqual(
            managed_service_metadata_wait_variant_profile_name(
                "auto",
                managed_service_metadata_wait_enabled=False,
            ),
            "auto_nometadatawait",
        )
        specs = build_profile_specs(
            profile_names=["auto"],
            extra_post_warm_wait_seconds=[1.5],
            extra_no_managed_service_metadata_wait=True,
        )

        self.assertEqual(
            specs,
            [
                {
                    "name": "auto",
                    "base_profile_name": "auto",
                    "extra_post_warm_wait_seconds": 0.0,
                    "conflux_client_ux": None,
                },
                {
                    "name": "auto_wait_1p5s",
                    "base_profile_name": "auto",
                    "extra_post_warm_wait_seconds": 1.5,
                    "conflux_client_ux": None,
                },
                {
                    "name": "auto_nometadatawait",
                    "base_profile_name": "auto",
                    "extra_post_warm_wait_seconds": 0.0,
                    "conflux_client_ux": None,
                    "managed_service_metadata_wait_enabled": False,
                },
                {
                    "name": "auto_wait_1p5s_nometadatawait",
                    "base_profile_name": "auto",
                    "extra_post_warm_wait_seconds": 1.5,
                    "conflux_client_ux": None,
                    "managed_service_metadata_wait_enabled": False,
                },
            ],
        )

    def test_build_profile_specs_can_add_no_warm_helper_prestart_variants(self) -> None:
        specs = build_profile_specs(
            profile_names=["auto"],
            extra_post_warm_wait_seconds=[1.5],
            base_warm_helper_prestart_enabled=True,
            extra_no_warm_helper_prestart=True,
        )

        self.assertEqual(
            specs,
            [
                {
                    "name": "auto",
                    "base_profile_name": "auto",
                    "extra_post_warm_wait_seconds": 0.0,
                    "conflux_client_ux": None,
                },
                {
                    "name": "auto_wait_1p5s",
                    "base_profile_name": "auto",
                    "extra_post_warm_wait_seconds": 1.5,
                    "conflux_client_ux": None,
                },
                {
                    "name": "auto_noprestart",
                    "base_profile_name": "auto",
                    "extra_post_warm_wait_seconds": 0.0,
                    "conflux_client_ux": None,
                    "warm_helper_prestart_enabled": False,
                },
                {
                    "name": "auto_wait_1p5s_noprestart",
                    "base_profile_name": "auto",
                    "extra_post_warm_wait_seconds": 1.5,
                    "conflux_client_ux": None,
                    "warm_helper_prestart_enabled": False,
                },
            ],
        )

    def test_build_profile_specs_can_add_no_warm_browser_prestart_variants(
        self,
    ) -> None:
        specs = build_profile_specs(
            profile_names=["auto"],
            extra_post_warm_wait_seconds=[1.5],
            base_warm_browser_prestart_enabled=True,
            extra_no_warm_browser_prestart=True,
        )

        self.assertEqual(
            specs,
            [
                {
                    "name": "auto",
                    "base_profile_name": "auto",
                    "extra_post_warm_wait_seconds": 0.0,
                    "conflux_client_ux": None,
                },
                {
                    "name": "auto_wait_1p5s",
                    "base_profile_name": "auto",
                    "extra_post_warm_wait_seconds": 1.5,
                    "conflux_client_ux": None,
                },
                {
                    "name": "auto_nobrowserprestart",
                    "base_profile_name": "auto",
                    "extra_post_warm_wait_seconds": 0.0,
                    "conflux_client_ux": None,
                    "warm_browser_prestart_enabled": False,
                },
                {
                    "name": "auto_wait_1p5s_nobrowserprestart",
                    "base_profile_name": "auto",
                    "extra_post_warm_wait_seconds": 1.5,
                    "conflux_client_ux": None,
                    "warm_browser_prestart_enabled": False,
                },
            ],
        )

    def test_build_profile_specs_preserves_no_overlap_on_noprestart_variants(
        self,
    ) -> None:
        specs = build_profile_specs(
            profile_names=["auto"],
            extra_post_warm_wait_seconds=[],
            base_managed_open_browser_overlap_enabled=True,
            base_warm_helper_prestart_enabled=True,
            extra_no_managed_open_browser_overlap=True,
            extra_no_warm_helper_prestart=True,
        )

        self.assertIn(
            {
                "name": "auto_nooverlap_noprestart",
                "base_profile_name": "auto",
                "extra_post_warm_wait_seconds": 0.0,
                "conflux_client_ux": None,
                "managed_open_browser_overlap_enabled": False,
                "warm_helper_prestart_enabled": False,
            },
            specs,
        )

    def test_build_profile_specs_preserves_browser_startup_seed_on_noprestart_variants(
        self,
    ) -> None:
        specs = build_profile_specs(
            profile_names=["auto"],
            extra_post_warm_wait_seconds=[],
            base_warm_helper_prestart_enabled=True,
            extra_browser_startup_seed=True,
            extra_no_warm_helper_prestart=True,
        )

        self.assertIn(
            {
                "name": "auto_noprestart_browserstartupseed",
                "base_profile_name": "auto",
                "extra_post_warm_wait_seconds": 0.0,
                "conflux_client_ux": None,
                "browser_startup_seed_enabled": True,
                "warm_helper_prestart_enabled": False,
            },
            specs,
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
            conflux_client_ux=None,
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

    def test_next_available_port_skips_reserved_and_busy_ports(self) -> None:
        with patch(
            "run_torfast_warm_open_compare.port_is_available",
            side_effect=lambda port: port == 20452,
        ):
            self.assertEqual(
                next_available_port(20450, reserved_ports={20450}),
                20452,
            )

    def test_port_is_available_rejects_bound_port(self) -> None:
        import socket

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
            self.assertFalse(port_is_available(port))

    def test_build_command_can_enable_managed_open_settle(self) -> None:
        command = build_torfast_command(
            action="open",
            state_root=Path("/tmp/state"),
            browser_bin=Path("/tmp/browser"),
            tor_bin=Path("/tmp/tor"),
            target="https://check.torproject.org/",
            port=19450,
            profile_name="auto",
            conflux_client_ux=None,
            browser_timeout=3.0,
            browser_startup_seed_root=Path("/tmp/browser-seed"),
            browser_startup_seed_enabled=False,
            managed_open_settle_enabled=True,
            headed=False,
        )

        self.assertIn("--managed-open-settle", command)

    def test_build_command_can_enable_managed_open_browser_overlap(self) -> None:
        command = build_torfast_command(
            action="open",
            state_root=Path("/tmp/state"),
            browser_bin=Path("/tmp/browser"),
            tor_bin=Path("/tmp/tor"),
            target="https://check.torproject.org/",
            port=19450,
            profile_name="auto",
            conflux_client_ux=None,
            browser_timeout=3.0,
            browser_startup_seed_root=Path("/tmp/browser-seed"),
            browser_startup_seed_enabled=False,
            managed_open_browser_overlap_enabled=True,
            headed=False,
        )

        self.assertIn("--managed-open-browser-overlap", command)
        self.assertNotIn("--no-managed-open-browser-overlap", command)

    def test_build_command_can_disable_managed_open_browser_overlap(self) -> None:
        command = build_torfast_command(
            action="open",
            state_root=Path("/tmp/state"),
            browser_bin=Path("/tmp/browser"),
            tor_bin=Path("/tmp/tor"),
            target="https://check.torproject.org/",
            port=19450,
            profile_name="auto",
            conflux_client_ux=None,
            browser_timeout=3.0,
            browser_startup_seed_root=Path("/tmp/browser-seed"),
            browser_startup_seed_enabled=False,
            managed_open_browser_overlap_enabled=False,
            headed=False,
        )

        self.assertIn("--no-managed-open-browser-overlap", command)

    def test_build_command_can_enable_warm_browser_prestart(self) -> None:
        command = build_torfast_command(
            action="open",
            state_root=Path("/tmp/state"),
            browser_bin=Path("/tmp/browser"),
            tor_bin=Path("/tmp/tor"),
            target="https://check.torproject.org/",
            port=19450,
            profile_name="auto",
            conflux_client_ux=None,
            browser_timeout=3.0,
            browser_startup_seed_root=Path("/tmp/browser-seed"),
            browser_startup_seed_enabled=False,
            warm_browser_prestart_enabled=True,
            headed=False,
        )

        self.assertIn("--warm-browser-prestart", command)

    def test_build_command_can_enable_managed_open_adaptive_wait_timeout(
        self,
    ) -> None:
        command = build_torfast_command(
            action="open",
            state_root=Path("/tmp/state"),
            browser_bin=Path("/tmp/browser"),
            tor_bin=Path("/tmp/tor"),
            target="https://check.torproject.org/",
            port=19450,
            profile_name="auto",
            conflux_client_ux=None,
            browser_timeout=3.0,
            browser_startup_seed_root=Path("/tmp/browser-seed"),
            browser_startup_seed_enabled=False,
            managed_open_adaptive_general_circuit_wait_timeout_seconds=0.75,
            headed=False,
        )

        self.assertIn(
            "--managed-open-adaptive-general-circuit-wait-timeout",
            command,
        )
        self.assertIn("0.75", command)

    def test_build_wait_ready_command(self) -> None:
        command = build_wait_ready_command(
            state_root=Path("/tmp/state"),
            gate="tor_boot_100",
            timeout=45.0,
        )

        self.assertEqual(
            command,
            [
                sys.executable,
                "-m",
                "torfast",
                "wait-ready",
                "--state-root",
                "/tmp/state",
                "--gate",
                "tor_boot_100",
                "--timeout",
                "45.0",
            ],
        )

    def test_build_warm_command_keeps_auto_gate_implicit(self) -> None:
        command = build_torfast_command(
            action="warm",
            state_root=Path("/tmp/state"),
            browser_bin=Path("/tmp/browser"),
            tor_bin=Path("/tmp/tor"),
            target="about:tor",
            port=19450,
            profile_name="auto",
            conflux_client_ux=None,
            browser_timeout=3.0,
            browser_startup_seed_root=Path("/tmp/browser-seed"),
            browser_startup_seed_enabled=True,
            headed=True,
        )

        self.assertIn("warm", command)
        self.assertNotIn("--browser-launch-gate", command)
        self.assertNotIn("--headless", command)
        self.assertIn("--browser-startup-seed", command)

    def test_build_command_adds_conflux_client_ux(self) -> None:
        command = build_torfast_command(
            action="open",
            state_root=Path("/tmp/state"),
            browser_bin=Path("/tmp/browser"),
            tor_bin=Path("/tmp/tor"),
            target="https://check.torproject.org/",
            port=19450,
            profile_name="auto",
            conflux_client_ux="throughput_lowmem",
            browser_timeout=3.0,
            browser_startup_seed_root=Path("/tmp/browser-seed"),
            browser_startup_seed_enabled=False,
            headed=False,
        )

        self.assertIn("--conflux-client-ux", command)
        self.assertIn("throughput_lowmem", command)

    def test_warm_helper_prestart_variant_name_and_env(self) -> None:
        self.assertEqual(
            warm_helper_prestart_variant_profile_name(
                "auto",
                warm_helper_prestart_enabled=False,
            ),
            "auto_noprestart",
        )
        self.assertEqual(
            torfast_command_env(
                action="warm",
                persistent_control_wait_enabled=True,
                control_bootstrap_probe_enabled=True,
                async_browser_reset_enabled=True,
                managed_service_metadata_wait_enabled=True,
                warm_helper_prestart_enabled=True,
            ),
            {
                "TORFAST_DISABLE_CONTROL_BOOTSTRAP_PROBE": "0",
                "TORFAST_DISABLE_ASYNC_BROWSER_RESET": "",
                "TORFAST_DISABLE_MANAGED_SERVICE_METADATA_WAIT": "0",
                "TORFAST_ENABLE_TARGET_STREAM_PROOF": "0",
                "TORFAST_ENABLE_PERSISTENT_CONTROL_WAIT": "1",
                "TORFAST_DISABLE_PERSISTENT_CONTROL_WAIT": "0",
                "TORFAST_ENABLE_WARM_RUNTIME_HELPER_PRESTART": "1",
            },
        )
        self.assertEqual(
            torfast_command_env(
                action="open",
                persistent_control_wait_enabled=True,
                control_bootstrap_probe_enabled=True,
                async_browser_reset_enabled=True,
                managed_service_metadata_wait_enabled=True,
                warm_helper_prestart_enabled=True,
            ),
            {
                "TORFAST_DISABLE_CONTROL_BOOTSTRAP_PROBE": "0",
                "TORFAST_DISABLE_ASYNC_BROWSER_RESET": "",
                "TORFAST_DISABLE_MANAGED_SERVICE_METADATA_WAIT": "0",
                "TORFAST_ENABLE_TARGET_STREAM_PROOF": "1",
                "TORFAST_ENABLE_PERSISTENT_CONTROL_WAIT": "1",
                "TORFAST_DISABLE_PERSISTENT_CONTROL_WAIT": "0",
            },
        )
        self.assertEqual(
            torfast_command_env(
                action="warm",
                persistent_control_wait_enabled=True,
                control_bootstrap_probe_enabled=False,
                async_browser_reset_enabled=True,
                managed_service_metadata_wait_enabled=False,
                warm_helper_prestart_enabled=False,
            ),
            {
                "TORFAST_DISABLE_CONTROL_BOOTSTRAP_PROBE": "1",
                "TORFAST_DISABLE_ASYNC_BROWSER_RESET": "",
                "TORFAST_DISABLE_MANAGED_SERVICE_METADATA_WAIT": "1",
                "TORFAST_ENABLE_TARGET_STREAM_PROOF": "0",
                "TORFAST_ENABLE_PERSISTENT_CONTROL_WAIT": "1",
                "TORFAST_DISABLE_PERSISTENT_CONTROL_WAIT": "0",
            },
        )
        self.assertEqual(
            torfast_command_env(
                action="open",
                persistent_control_wait_enabled=False,
                control_bootstrap_probe_enabled=False,
                async_browser_reset_enabled=False,
                managed_service_metadata_wait_enabled=False,
                warm_helper_prestart_enabled=False,
            ),
            {
                "TORFAST_DISABLE_CONTROL_BOOTSTRAP_PROBE": "1",
                "TORFAST_DISABLE_ASYNC_BROWSER_RESET": "1",
                "TORFAST_DISABLE_MANAGED_SERVICE_METADATA_WAIT": "1",
                "TORFAST_ENABLE_TARGET_STREAM_PROOF": "1",
                "TORFAST_ENABLE_PERSISTENT_CONTROL_WAIT": "0",
                "TORFAST_DISABLE_PERSISTENT_CONTROL_WAIT": "1",
            },
        )

    def test_warm_browser_prestart_variant_name(self) -> None:
        self.assertEqual(
            warm_browser_prestart_variant_profile_name(
                "auto",
                warm_browser_prestart_enabled=False,
            ),
            "auto_nobrowserprestart",
        )

    def test_build_stop_command(self) -> None:
        command = build_stop_command(Path("/tmp/state"))
        self.assertEqual(command[-3:], ["stop", "--state-root", "/tmp/state"])

    def test_maybe_wait_for_managed_general_circuit_skips_when_already_ready(
        self,
    ) -> None:
        result = {
            "warm_launch": {
                "reused_tor_service": {
                    "control_port": 19150,
                    "control_cookie_path": "/tmp/control_auth_cookie",
                }
            }
        }

        with patch(
            "run_torfast_warm_open_compare.read_general_circuit_snapshot",
            return_value={"ok": True, "matched_circuit_count": 1},
        ), patch(
            "run_torfast_warm_open_compare.wait_for_general_circuits"
        ) as wait_for_general_circuits:
            payload = maybe_wait_for_managed_general_circuit(
                result,
                timeout_seconds=0.5,
            )

        self.assertTrue(payload["ok"])
        self.assertTrue(payload["matched"])
        self.assertFalse(payload["timed_out"])
        self.assertEqual(payload["seconds"], 0.0)
        self.assertEqual(payload["reason"], "already_ready")
        wait_for_general_circuits.assert_not_called()

    def test_maybe_wait_for_managed_general_circuit_continues_on_timeout(
        self,
    ) -> None:
        result = {
            "warm_launch": {
                "reused_tor_service": {
                    "control_port": 19150,
                    "control_cookie_path": "/tmp/control_auth_cookie",
                }
            }
        }

        with patch(
            "run_torfast_warm_open_compare.read_general_circuit_snapshot",
            return_value={"ok": True, "matched_circuit_count": 0},
        ), patch(
            "run_torfast_warm_open_compare.wait_for_general_circuits",
            return_value={
                "ok": False,
                "error": "general circuit wait timeout",
                "last_error": None,
                "min_count": 1,
            },
        ):
            payload = maybe_wait_for_managed_general_circuit(
                result,
                timeout_seconds=0.5,
            )

        self.assertTrue(payload["ok"])
        self.assertFalse(payload["matched"])
        self.assertTrue(payload["timed_out"])
        self.assertEqual(payload["reason"], "timeout_proceed")
        self.assertGreaterEqual(payload["seconds"], 0.0)

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

    def test_combined_wall_seconds_adds_wait_ready(self) -> None:
        result = {
            "warm": {"wall_seconds": 0.25},
            "wait_ready": {"wall_seconds": 0.15},
            "open": {"wall_seconds": 3.75},
        }

        self.assertEqual(combined_wall_seconds(result), 4.15)

    def test_combined_wall_seconds_adds_adaptive_general_circuit_wait(self) -> None:
        result = {
            "warm": {"wall_seconds": 0.25},
            "adaptive_general_circuit_wait": {"seconds": 0.4},
            "open": {"wall_seconds": 3.75},
        }

        self.assertEqual(adaptive_general_circuit_wait_seconds(result), 0.4)
        self.assertEqual(combined_wall_seconds(result), 4.4)

    def test_total_wall_seconds_adds_hidden_wait(self) -> None:
        result = {
            "post_warm_wait_seconds": 1.5,
            "warm": {"wall_seconds": 0.25},
            "wait_ready": {"wall_seconds": 0.15},
            "open": {"wall_seconds": 3.75},
        }

        self.assertEqual(total_wall_seconds(result), 5.65)

    def test_parse_json_text_rejects_truncated_tail(self) -> None:
        self.assertIsNone(parse_json_text('"ok": true\n}'))
        self.assertEqual(parse_json_text('{"ok": true}\n'), {"ok": True})

    def test_result_ok_requires_network_target_stream_proof(self) -> None:
        base_result = {
            "target": "https://check.torproject.org/",
            "wait_ready_enabled": False,
            "warm": {"ok": True},
            "warm_launch": {"tor_managed_ready": {"ok": True}},
            "open": {"ok": True},
            "open_launch": {
                "browser": {
                    "ok": True,
                    "target_stream_snapshot": {
                        "ok": True,
                        "user_stream_count": 0,
                        "observed_stream_count": 0,
                    },
                },
                "browser_default_pref_check": {"ok": True},
                "browser_runtime_reset": {"ok": True},
                "tor_boot": {"ok": True},
                "torrc_quality": {"isolate_socks_auth": True},
                "reused_tor_service": {"pid": 1234},
            },
            "stop": {"ok": True},
        }

        self.assertFalse(result_ok(base_result))

        proven_result = {
            **base_result,
            "open_launch": {
                **base_result["open_launch"],
                "browser": {
                    "ok": True,
                    "target_stream_snapshot": {
                        "ok": True,
                        "user_stream_count": 1,
                        "observed_stream_count": 1,
                        "targets": ["check.torproject.org:443"],
                    },
                },
            },
        }

        self.assertTrue(result_ok(proven_result))

    def test_summarize_results_and_deltas(self) -> None:
        target = "https://check.torproject.org/"
        results = [
            {
                "target": target,
                "profile_name": "auto",
                "post_warm_wait_seconds": 0.0,
                "wait_ready_enabled": False,
                "wait_ready": None,
                "wait_ready_response": None,
                "warm": {"ok": True, "wall_seconds": 0.25},
                "warm_launch": {"tor_managed_ready": {"ok": True, "gate": "tor_boot_95", "seconds": 0.2}},
                "open": {"ok": True, "wall_seconds": 5.5},
                "open_launch": {
                    "browser": {
                        "ok": True,
                        "elapsed_seconds": 3.0,
                        "target_stream_snapshot": {
                            "ok": True,
                            "user_stream_count": 1,
                            "observed_stream_count": 1,
                            "targets": ["check.torproject.org:443"],
                        },
                    },
                    "browser_default_pref_check": {"ok": True},
                    "browser_launch_gate": "tor_boot_95",
                    "browser_runtime_reset": {"ok": True},
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
                "post_warm_wait_seconds": 1.5,
                "wait_ready_enabled": True,
                "wait_ready": {"ok": True, "wall_seconds": 0.2},
                "wait_ready_response": {"ok": True, "resolved_gate": "tor_boot_100"},
                "warm": {"ok": True, "wall_seconds": 2.0},
                "warm_launch": {"tor_managed_ready": {"ok": True, "gate": "tor_boot_100", "seconds": 1.9}},
                "open": {"ok": True, "wall_seconds": 6.0},
                "open_launch": {
                    "browser": {
                        "ok": True,
                        "elapsed_seconds": 3.0,
                        "target_stream_snapshot": {
                            "ok": True,
                            "user_stream_count": 1,
                            "observed_stream_count": 1,
                            "targets": ["check.torproject.org:443"],
                        },
                    },
                    "browser_default_pref_check": {"ok": True},
                    "browser_launch_gate": "tor_boot_100",
                    "browser_runtime_reset": {"ok": True},
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
            profiles[target]["auto"]["p90_combined_wall_seconds"],
            5.75,
        )
        self.assertEqual(
            profiles[target]["auto"]["max_combined_wall_seconds"],
            5.75,
        )
        self.assertEqual(
            profiles[target]["tor_boot_100"]["median_total_wall_seconds"],
            9.7,
        )
        self.assertEqual(
            profiles[target]["tor_boot_100"]["median_open_launch_gate_seconds"],
            2.0,
        )
        self.assertEqual(
            profiles[target]["tor_boot_100"]["p90_open_launch_gate_seconds"],
            2.0,
        )
        self.assertEqual(
            profiles[target]["tor_boot_100"]["max_open_launch_gate_seconds"],
            2.0,
        )
        self.assertEqual(
            profiles[target]["tor_boot_100"]["median_post_warm_wait_seconds"],
            1.5,
        )
        self.assertEqual(
            profiles[target]["tor_boot_100"]["median_wait_ready_wall_seconds"],
            0.2,
        )
        self.assertEqual(
            profiles[target]["auto"]["median_wait_ready_wall_seconds"],
            0.0,
        )
        self.assertEqual(
            profiles[target]["auto"]["browser_default_pref_check_ok_runs"],
            1,
        )
        self.assertEqual(
            profiles[target]["tor_boot_100"]["browser_runtime_reset_ok_runs"],
            1,
        )

        deltas = delta_vs_baseline(
            profiles,
            targets=[target],
            profile_names=["auto", "tor_boot_100"],
            baseline_profile="tor_boot_100",
        )

        self.assertEqual(
            deltas[target]["auto"]["combined_wall_seconds"],
            -2.45,
        )
        self.assertEqual(
            deltas[target]["auto"]["p90_combined_wall_seconds"],
            -2.45,
        )
        self.assertEqual(
            deltas[target]["auto"]["max_combined_wall_seconds"],
            -2.45,
        )
        self.assertEqual(
            deltas[target]["tor_boot_100"]["combined_wall_seconds"],
            0.0,
        )
        self.assertEqual(
            deltas[target]["auto"]["total_wall_seconds"],
            -3.95,
        )
        self.assertEqual(
            deltas[target]["auto"]["post_warm_wait_seconds"],
            -1.5,
        )
        self.assertEqual(
            deltas[target]["auto"]["wait_ready_wall_seconds"],
            -0.2,
        )
        self.assertEqual(
            deltas[target]["auto"]["p90_open_launch_gate_seconds"],
            -0.2,
        )
        self.assertEqual(
            deltas[target]["auto"]["max_open_launch_gate_seconds"],
            -0.2,
        )

    def test_summarize_results_tracks_adaptive_general_circuit_wait(self) -> None:
        target = "https://check.torproject.org/"
        results = [
            {
                "target": target,
                "profile_name": "auto",
                "post_warm_wait_seconds": 0.0,
                "adaptive_general_circuit_wait_enabled": False,
                "adaptive_general_circuit_wait": None,
                "wait_ready_enabled": False,
                "wait_ready": None,
                "wait_ready_response": None,
                "warm": {"ok": True, "wall_seconds": 0.25},
                "warm_launch": {
                    "tor_managed_ready": {
                        "ok": True,
                        "gate": "tor_boot_95",
                        "seconds": 0.2,
                    }
                },
                "open": {"ok": True, "wall_seconds": 5.5},
                "open_launch": {
                    "browser": {
                        "ok": True,
                        "elapsed_seconds": 3.0,
                        "target_stream_snapshot": {
                            "ok": True,
                            "user_stream_count": 1,
                            "observed_stream_count": 1,
                            "targets": ["check.torproject.org:443"],
                        },
                    },
                    "browser_default_pref_check": {"ok": True},
                    "browser_launch_gate": "tor_boot_95",
                    "browser_runtime_reset": {"ok": True},
                    "tor_browser_launch_gate": {
                        "gate": "tor_boot_95",
                        "seconds": 1.8,
                    },
                    "tor_boot": {"ok": True, "seconds": 2.1},
                    "torrc_quality": {"isolate_socks_auth": True},
                    "reused_tor_service": {"pid": 1234, "ready_gate": "tor_boot_100"},
                },
                "stop": {"ok": True},
            },
            {
                "target": target,
                "profile_name": "auto_adaptivegencirc_0p5s",
                "post_warm_wait_seconds": 0.0,
                "adaptive_general_circuit_wait_enabled": True,
                "adaptive_general_circuit_wait_timeout_seconds": 0.5,
                "adaptive_general_circuit_wait": {
                    "ok": True,
                    "matched": False,
                    "timed_out": True,
                    "seconds": 0.5,
                },
                "wait_ready_enabled": False,
                "wait_ready": None,
                "wait_ready_response": None,
                "warm": {"ok": True, "wall_seconds": 0.25},
                "warm_launch": {
                    "tor_managed_ready": {
                        "ok": True,
                        "gate": "tor_boot_95",
                        "seconds": 0.2,
                    }
                },
                "open": {"ok": True, "wall_seconds": 5.0},
                "open_launch": {
                    "browser": {
                        "ok": True,
                        "elapsed_seconds": 2.8,
                        "target_stream_snapshot": {
                            "ok": True,
                            "user_stream_count": 1,
                            "observed_stream_count": 1,
                            "targets": ["check.torproject.org:443"],
                        },
                    },
                    "browser_default_pref_check": {"ok": True},
                    "browser_launch_gate": "tor_boot_95",
                    "browser_runtime_reset": {"ok": True},
                    "tor_browser_launch_gate": {
                        "gate": "tor_boot_95",
                        "seconds": 1.7,
                    },
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
            profile_names=["auto", "auto_adaptivegencirc_0p5s"],
        )
        deltas = delta_vs_baseline(
            profiles,
            targets=[target],
            profile_names=["auto", "auto_adaptivegencirc_0p5s"],
            baseline_profile="auto",
        )

        self.assertEqual(
            profiles[target]["auto_adaptivegencirc_0p5s"][
                "median_adaptive_general_circuit_wait_seconds"
            ],
            0.5,
        )
        self.assertEqual(
            profiles[target]["auto_adaptivegencirc_0p5s"][
                "adaptive_general_circuit_wait_timeout_runs"
            ],
            1,
        )
        self.assertEqual(
            deltas[target]["auto_adaptivegencirc_0p5s"][
                "adaptive_general_circuit_wait_seconds"
            ],
            0.5,
        )


if __name__ == "__main__":
    unittest.main()
