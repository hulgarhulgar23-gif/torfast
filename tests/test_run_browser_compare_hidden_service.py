import sys
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import run_browser_compare_hidden_service


class RunBrowserCompareHiddenServiceTests(unittest.TestCase):
    def test_default_wrapper_includes_promoted_cold_scope_candidate(self) -> None:
        with patch("sys.argv", ["run_browser_compare_hidden_service.py"]), patch(
            "run_browser_compare_hidden_service.subprocess.run"
        ) as run_mock:
            run_mock.return_value.returncode = 0

            rc = run_browser_compare_hidden_service.main()

        self.assertEqual(rc, 0)
        cmd = run_mock.call_args.args[0]
        self.assertIn("--extra-arti-hs-desc-shared-cache", cmd)
        flag = "--extra-arti-hs-desc-shared-cache-stream-ready-data-coalesce-min-hop-combo"
        self.assertIn(flag, cmd)
        flag_index = cmd.index(flag)
        self.assertEqual(cmd[flag_index + 1], "4096:4")
        self.assertNotIn(
            "--extra-arti-hs-desc-shared-cache-hsdir-extend-timeout-cap-startup-only-ms",
            cmd,
        )
        self.assertNotIn(
            "--extra-arti-hs-desc-shared-cache-hspool-race-background-start-on-demand-ms",
            cmd,
        )

    def test_wrapper_still_forwards_explicit_startup_only_cap(self) -> None:
        with patch(
            "sys.argv",
            [
                "run_browser_compare_hidden_service.py",
                "--extra-arti-hs-desc-shared-cache-hsdir-extend-timeout-cap-startup-only-ms",
                "3000",
            ],
        ), patch("run_browser_compare_hidden_service.subprocess.run") as run_mock:
            run_mock.return_value.returncode = 0

            rc = run_browser_compare_hidden_service.main()

        self.assertEqual(rc, 0)
        cmd = run_mock.call_args.args[0]
        startup_only_flag = (
            "--extra-arti-hs-desc-shared-cache-hsdir-extend-timeout-cap-startup-only-ms"
        )
        self.assertIn(startup_only_flag, cmd)
        flag_index = cmd.index(startup_only_flag)
        self.assertEqual(cmd[flag_index + 1], "3000")

    def test_wrapper_still_forwards_explicit_post_boot_only_cap(self) -> None:
        with patch(
            "sys.argv",
            [
                "run_browser_compare_hidden_service.py",
                "--extra-arti-hs-desc-shared-cache-hsdir-extend-timeout-cap-post-boot-only-ms",
                "3000",
            ],
        ), patch("run_browser_compare_hidden_service.subprocess.run") as run_mock:
            run_mock.return_value.returncode = 0

            rc = run_browser_compare_hidden_service.main()

        self.assertEqual(rc, 0)
        cmd = run_mock.call_args.args[0]
        post_boot_only_flag = (
            "--extra-arti-hs-desc-shared-cache-hsdir-extend-timeout-cap-post-boot-only-ms"
        )
        self.assertIn(post_boot_only_flag, cmd)
        flag_index = cmd.index(post_boot_only_flag)
        self.assertEqual(cmd[flag_index + 1], "3000")

    def test_wrapper_still_forwards_explicit_demand_start(self) -> None:
        with patch(
            "sys.argv",
            [
                "run_browser_compare_hidden_service.py",
                "--extra-arti-hs-desc-shared-cache-hspool-race-background-start-on-demand-ms",
                "50",
            ],
        ), patch("run_browser_compare_hidden_service.subprocess.run") as run_mock:
            run_mock.return_value.returncode = 0

            rc = run_browser_compare_hidden_service.main()

        self.assertEqual(rc, 0)
        cmd = run_mock.call_args.args[0]
        demand_start_flag = (
            "--extra-arti-hs-desc-shared-cache-hspool-race-background-start-on-demand-ms"
        )
        self.assertIn(demand_start_flag, cmd)
        flag_index = cmd.index(demand_start_flag)
        self.assertEqual(cmd[flag_index + 1], "50")

    def test_wrapper_forwards_guarded_defer_hsdir_cap_combo(self) -> None:
        with patch(
            "sys.argv",
            [
                "run_browser_compare_hidden_service.py",
                "--extra-arti-hs-desc-shared-cache-hspool-race-background-start-on-demand-hsdir-extend-timeout-cap-guarded-stem-target-defer-post-bootstrap-combo",
                "50:2000:4",
            ],
        ), patch("run_browser_compare_hidden_service.subprocess.run") as run_mock:
            run_mock.return_value.returncode = 0

            rc = run_browser_compare_hidden_service.main()

        self.assertEqual(rc, 0)
        cmd = run_mock.call_args.args[0]
        flag = (
            "--extra-arti-hs-desc-shared-cache-hspool-race-background-start-on-demand-"
            "hsdir-extend-timeout-cap-guarded-stem-target-defer-post-bootstrap-combo"
        )
        self.assertIn(flag, cmd)
        self.assertEqual(cmd[cmd.index(flag) + 1], "50:2000:4")

    def test_wrapper_forwards_pure_bg_on_demand_flag(self) -> None:
        with patch(
            "sys.argv",
            [
                "run_browser_compare_hidden_service.py",
                "--extra-arti-hs-desc-shared-cache-hspool-background-start-on-demand",
            ],
        ), patch("run_browser_compare_hidden_service.subprocess.run") as run_mock:
            run_mock.return_value.returncode = 0

            rc = run_browser_compare_hidden_service.main()

        self.assertEqual(rc, 0)
        cmd = run_mock.call_args.args[0]
        self.assertIn(
            "--extra-arti-hs-desc-shared-cache-hspool-background-start-on-demand",
            cmd,
        )

    def test_wrapper_forwards_hsdescshare_scheduler_burst_flag(self) -> None:
        with patch(
            "sys.argv",
            [
                "run_browser_compare_hidden_service.py",
                "--extra-arti-hs-desc-shared-cache-stream-scheduler-burst",
                "2",
            ],
        ), patch("run_browser_compare_hidden_service.subprocess.run") as run_mock:
            run_mock.return_value.returncode = 0

            rc = run_browser_compare_hidden_service.main()

        self.assertEqual(rc, 0)
        cmd = run_mock.call_args.args[0]
        flag = "--extra-arti-hs-desc-shared-cache-stream-scheduler-burst"
        self.assertIn(flag, cmd)
        self.assertEqual(cmd[cmd.index(flag) + 1], "2")

    def test_wrapper_forwards_hsdescshare_socks_tor_to_client_coalesce_flag(
        self,
    ) -> None:
        with patch(
            "sys.argv",
            [
                "run_browser_compare_hidden_service.py",
                "--extra-arti-hs-desc-shared-cache-socks-tor-to-client-coalesce-bytes",
                "4096",
            ],
        ), patch("run_browser_compare_hidden_service.subprocess.run") as run_mock:
            run_mock.return_value.returncode = 0

            rc = run_browser_compare_hidden_service.main()

        self.assertEqual(rc, 0)
        cmd = run_mock.call_args.args[0]
        flag = "--extra-arti-hs-desc-shared-cache-socks-tor-to-client-coalesce-bytes"
        self.assertIn(flag, cmd)
        self.assertEqual(cmd[cmd.index(flag) + 1], "4096")

    def test_wrapper_forwards_hsdescshare_stream_ready_data_coalesce_flag(
        self,
    ) -> None:
        with patch(
            "sys.argv",
            [
                "run_browser_compare_hidden_service.py",
                "--extra-arti-hs-desc-shared-cache-stream-ready-data-coalesce-bytes",
                "4096",
            ],
        ), patch("run_browser_compare_hidden_service.subprocess.run") as run_mock:
            run_mock.return_value.returncode = 0

            rc = run_browser_compare_hidden_service.main()

        self.assertEqual(rc, 0)
        cmd = run_mock.call_args.args[0]
        flag = "--extra-arti-hs-desc-shared-cache-stream-ready-data-coalesce-bytes"
        self.assertIn(flag, cmd)
        self.assertEqual(cmd[cmd.index(flag) + 1], "4096")

    def test_wrapper_forwards_hsdescshare_reuse_max_active_streams_flag(
        self,
    ) -> None:
        with patch(
            "sys.argv",
            [
                "run_browser_compare_hidden_service.py",
                "--extra-arti-hs-desc-shared-cache-reuse-max-active-streams",
                "2",
            ],
        ), patch("run_browser_compare_hidden_service.subprocess.run") as run_mock:
            run_mock.return_value.returncode = 0

            rc = run_browser_compare_hidden_service.main()

        self.assertEqual(rc, 0)
        cmd = run_mock.call_args.args[0]
        flag = "--extra-arti-hs-desc-shared-cache-reuse-max-active-streams"
        self.assertIn(flag, cmd)
        self.assertEqual(cmd[cmd.index(flag) + 1], "2")

    def test_wrapper_forwards_hsdescshare_stream_ready_data_coalesce_min_hop_combo_flag(
        self,
    ) -> None:
        with patch(
            "sys.argv",
            [
                "run_browser_compare_hidden_service.py",
                "--extra-arti-hs-desc-shared-cache-stream-ready-data-coalesce-min-hop-combo",
                "8192:5",
            ],
        ), patch("run_browser_compare_hidden_service.subprocess.run") as run_mock:
            run_mock.return_value.returncode = 0

            rc = run_browser_compare_hidden_service.main()

        self.assertEqual(rc, 0)
        cmd = run_mock.call_args.args[0]
        flag = "--extra-arti-hs-desc-shared-cache-stream-ready-data-coalesce-min-hop-combo"
        self.assertIn(flag, cmd)
        values = [
            cmd[index + 1] for index, token in enumerate(cmd[:-1]) if token == flag
        ]
        self.assertIn("4096:4", values)
        self.assertIn("8192:5", values)

    def test_wrapper_forwards_hsdescshare_rendezvous_establish_timeout_floor_flag(
        self,
    ) -> None:
        with patch(
            "sys.argv",
            [
                "run_browser_compare_hidden_service.py",
                "--extra-arti-hs-desc-shared-cache-rendezvous-establish-timeout-floor-ms",
                "1500",
            ],
        ), patch("run_browser_compare_hidden_service.subprocess.run") as run_mock:
            run_mock.return_value.returncode = 0

            rc = run_browser_compare_hidden_service.main()

        self.assertEqual(rc, 0)
        cmd = run_mock.call_args.args[0]
        flag = "--extra-arti-hs-desc-shared-cache-rendezvous-establish-timeout-floor-ms"
        self.assertIn(flag, cmd)
        self.assertEqual(cmd[cmd.index(flag) + 1], "1500")

    def test_wrapper_forwards_hsdescshare_stream_ready_data_coalesce_min_hop_rendezvous_establish_timeout_floor_combo_flag(
        self,
    ) -> None:
        with patch(
            "sys.argv",
            [
                "run_browser_compare_hidden_service.py",
                "--extra-arti-hs-desc-shared-cache-stream-ready-data-coalesce-min-hop-rendezvous-establish-timeout-floor-combo",
                "4096:4:1500",
            ],
        ), patch("run_browser_compare_hidden_service.subprocess.run") as run_mock:
            run_mock.return_value.returncode = 0

            rc = run_browser_compare_hidden_service.main()

        self.assertEqual(rc, 0)
        cmd = run_mock.call_args.args[0]
        flag = (
            "--extra-arti-hs-desc-shared-cache-stream-ready-data-coalesce-min-hop-rendezvous-establish-timeout-floor-combo"
        )
        self.assertIn(flag, cmd)
        self.assertEqual(cmd[cmd.index(flag) + 1], "4096:4:1500")

    def test_wrapper_forwards_hsdescshare_stream_ready_data_coalesce_min_hop_start_backlog_combo_flag(
        self,
    ) -> None:
        with patch(
            "sys.argv",
            [
                "run_browser_compare_hidden_service.py",
                "--extra-arti-hs-desc-shared-cache-stream-ready-data-coalesce-min-hop-start-backlog-combo",
                "4096:4:1494",
            ],
        ), patch("run_browser_compare_hidden_service.subprocess.run") as run_mock:
            run_mock.return_value.returncode = 0

            rc = run_browser_compare_hidden_service.main()

        self.assertEqual(rc, 0)
        cmd = run_mock.call_args.args[0]
        flag = "--extra-arti-hs-desc-shared-cache-stream-ready-data-coalesce-min-hop-start-backlog-combo"
        self.assertIn(flag, cmd)
        self.assertEqual(cmd[cmd.index(flag) + 1], "4096:4:1494")

    def test_wrapper_forwards_hsdescshare_stream_ready_data_coalesce_min_hop_busy_max_combo_flag(
        self,
    ) -> None:
        with patch(
            "sys.argv",
            [
                "run_browser_compare_hidden_service.py",
                "--extra-arti-hs-desc-shared-cache-stream-ready-data-coalesce-min-hop-busy-max-combo",
                "4096:4:996",
            ],
        ), patch("run_browser_compare_hidden_service.subprocess.run") as run_mock:
            run_mock.return_value.returncode = 0

            rc = run_browser_compare_hidden_service.main()

        self.assertEqual(rc, 0)
        cmd = run_mock.call_args.args[0]
        flag = "--extra-arti-hs-desc-shared-cache-stream-ready-data-coalesce-min-hop-busy-max-combo"
        self.assertIn(flag, cmd)
        self.assertEqual(cmd[cmd.index(flag) + 1], "4096:4:996")

    def test_wrapper_forwards_skip_local_c_tor_flag(self) -> None:
        with patch(
            "sys.argv",
            [
                "run_browser_compare_hidden_service.py",
                "--skip-local-c-tor",
            ],
        ), patch("run_browser_compare_hidden_service.subprocess.run") as run_mock:
            run_mock.return_value.returncode = 0

            rc = run_browser_compare_hidden_service.main()

        self.assertEqual(rc, 0)
        cmd = run_mock.call_args.args[0]
        self.assertIn("--skip-local-c-tor", cmd)

    def test_wrapper_forwards_arti_socks_relay_byte_timing_flag(self) -> None:
        with patch(
            "sys.argv",
            [
                "run_browser_compare_hidden_service.py",
                "--arti-socks-relay-byte-timing",
            ],
        ), patch("run_browser_compare_hidden_service.subprocess.run") as run_mock:
            run_mock.return_value.returncode = 0

            rc = run_browser_compare_hidden_service.main()

        self.assertEqual(rc, 0)
        cmd = run_mock.call_args.args[0]
        self.assertIn("--arti-socks-relay-byte-timing", cmd)

    def test_wrapper_forwards_shared_hit_only_prebuild_flag(self) -> None:
        with patch(
            "sys.argv",
            [
                "run_browser_compare_hidden_service.py",
                "--extra-arti-hs-rend-prebuild-before-desc-shared-cache-shared-hit-only",
            ],
        ), patch("run_browser_compare_hidden_service.subprocess.run") as run_mock:
            run_mock.return_value.returncode = 0

            rc = run_browser_compare_hidden_service.main()

        self.assertEqual(rc, 0)
        cmd = run_mock.call_args.args[0]
        self.assertIn(
            "--extra-arti-hs-rend-prebuild-before-desc-shared-cache-shared-hit-only",
            cmd,
        )

    def test_wrapper_forwards_shared_hit_only_stream_ready_data_coalesce_flag(
        self,
    ) -> None:
        with patch(
            "sys.argv",
            [
                "run_browser_compare_hidden_service.py",
                "--extra-arti-hs-rend-prebuild-before-desc-shared-cache-shared-hit-only-stream-ready-data-coalesce-bytes",
                "4096",
            ],
        ), patch("run_browser_compare_hidden_service.subprocess.run") as run_mock:
            run_mock.return_value.returncode = 0

            rc = run_browser_compare_hidden_service.main()

        self.assertEqual(rc, 0)
        cmd = run_mock.call_args.args[0]
        flag = (
            "--extra-arti-hs-rend-prebuild-before-desc-shared-cache-shared-hit-only-stream-ready-data-coalesce-bytes"
        )
        self.assertIn(flag, cmd)
        self.assertEqual(cmd[cmd.index(flag) + 1], "4096")

    def test_wrapper_forwards_shared_hit_only_cold_late_flag(self) -> None:
        with patch(
            "sys.argv",
            [
                "run_browser_compare_hidden_service.py",
                "--extra-arti-hs-rend-prebuild-before-desc-shared-cache-shared-hit-only-cold-late-ms",
                "1000",
            ],
        ), patch("run_browser_compare_hidden_service.subprocess.run") as run_mock:
            run_mock.return_value.returncode = 0

            rc = run_browser_compare_hidden_service.main()

        self.assertEqual(rc, 0)
        cmd = run_mock.call_args.args[0]
        flag = (
            "--extra-arti-hs-rend-prebuild-before-desc-shared-cache-shared-hit-only-cold-late-ms"
        )
        self.assertIn(flag, cmd)
        self.assertEqual(cmd[cmd.index(flag) + 1], "1000")

    def test_wrapper_forwards_shared_hit_only_reuse_max_active_streams_flag(self) -> None:
        with patch(
            "sys.argv",
            [
                "run_browser_compare_hidden_service.py",
                "--extra-arti-hs-rend-prebuild-before-desc-shared-cache-shared-hit-only-reuse-max-active-streams",
                "1",
            ],
        ), patch("run_browser_compare_hidden_service.subprocess.run") as run_mock:
            run_mock.return_value.returncode = 0

            rc = run_browser_compare_hidden_service.main()

        self.assertEqual(rc, 0)
        cmd = run_mock.call_args.args[0]
        flag = (
            "--extra-arti-hs-rend-prebuild-before-desc-shared-cache-shared-hit-only-reuse-max-active-streams"
        )
        self.assertIn(flag, cmd)
        self.assertEqual(cmd[cmd.index(flag) + 1], "1")

    def test_wrapper_forwards_shared_hit_only_reuse_startup_only_hsdir_cap_combo_flag(
        self,
    ) -> None:
        with patch(
            "sys.argv",
            [
                "run_browser_compare_hidden_service.py",
                "--extra-arti-hs-rend-prebuild-before-desc-shared-cache-shared-hit-only-reuse-max-active-streams-startup-only-hsdir-extend-timeout-cap-combo",
                "1:3000",
            ],
        ), patch("run_browser_compare_hidden_service.subprocess.run") as run_mock:
            run_mock.return_value.returncode = 0

            rc = run_browser_compare_hidden_service.main()

        self.assertEqual(rc, 0)
        cmd = run_mock.call_args.args[0]
        flag = (
            "--extra-arti-hs-rend-prebuild-before-desc-shared-cache-shared-hit-only-reuse-max-active-streams-startup-only-hsdir-extend-timeout-cap-combo"
        )
        self.assertIn(flag, cmd)
        self.assertEqual(cmd[cmd.index(flag) + 1], "1:3000")

    def test_wrapper_forwards_shared_hit_only_reuse_cold_late_combo_flag(self) -> None:
        with patch(
            "sys.argv",
            [
                "run_browser_compare_hidden_service.py",
                "--extra-arti-hs-rend-prebuild-before-desc-shared-cache-shared-hit-only-reuse-max-active-streams-cold-late-combo",
                "2:1000",
            ],
        ), patch("run_browser_compare_hidden_service.subprocess.run") as run_mock:
            run_mock.return_value.returncode = 0

            rc = run_browser_compare_hidden_service.main()

        self.assertEqual(rc, 0)
        cmd = run_mock.call_args.args[0]
        flag = (
            "--extra-arti-hs-rend-prebuild-before-desc-shared-cache-shared-hit-only-reuse-max-active-streams-cold-late-combo"
        )
        self.assertIn(flag, cmd)
        self.assertEqual(cmd[cmd.index(flag) + 1], "2:1000")

    def test_wrapper_forwards_skip_plain_arti_flag(self) -> None:
        with patch(
            "sys.argv",
            [
                "run_browser_compare_hidden_service.py",
                "--skip-plain-arti",
            ],
        ), patch("run_browser_compare_hidden_service.subprocess.run") as run_mock:
            run_mock.return_value.returncode = 0

            rc = run_browser_compare_hidden_service.main()

        self.assertEqual(rc, 0)
        cmd = run_mock.call_args.args[0]
        self.assertIn("--skip-plain-arti", cmd)

    def test_wrapper_forwards_main_hspool_knobs(self) -> None:
        with patch(
            "sys.argv",
            [
                "run_browser_compare_hidden_service.py",
                "--arti-hspool-launch-parallelism",
                "2",
                "--arti-hspool-background-start-delay-ms",
                "4000",
                "--arti-hspool-guarded-stem-target",
                "4",
                "--arti-hspool-guarded-stem-target-defer-post-bootstrap",
                "--arti-hspool-on-demand-grace-ms",
                "25",
                "--arti-hspool-on-demand-race-ms",
                "50",
            ],
        ), patch("run_browser_compare_hidden_service.subprocess.run") as run_mock:
            run_mock.return_value.returncode = 0

            rc = run_browser_compare_hidden_service.main()

        self.assertEqual(rc, 0)
        cmd = run_mock.call_args.args[0]
        self.assertIn("--arti-hspool-launch-parallelism", cmd)
        self.assertEqual(cmd[cmd.index("--arti-hspool-launch-parallelism") + 1], "2")
        self.assertIn("--arti-hspool-background-start-delay-ms", cmd)
        self.assertEqual(
            cmd[cmd.index("--arti-hspool-background-start-delay-ms") + 1], "4000"
        )
        self.assertIn("--arti-hspool-guarded-stem-target", cmd)
        self.assertEqual(cmd[cmd.index("--arti-hspool-guarded-stem-target") + 1], "4")
        self.assertIn("--arti-hspool-guarded-stem-target-defer-post-bootstrap", cmd)
        self.assertIn("--arti-hspool-on-demand-grace-ms", cmd)
        self.assertEqual(cmd[cmd.index("--arti-hspool-on-demand-grace-ms") + 1], "25")
        self.assertIn("--arti-hspool-on-demand-race-ms", cmd)
        self.assertEqual(cmd[cmd.index("--arti-hspool-on-demand-race-ms") + 1], "50")

    def test_wrapper_forwards_compact_and_proxy_tail_flags(self) -> None:
        with patch(
            "sys.argv",
            [
                "run_browser_compare_hidden_service.py",
                "--compact-output",
                "--proxy-log-tail-lines",
                "400",
                "--proxy-run-tail-lines",
                "120",
            ],
        ), patch("run_browser_compare_hidden_service.subprocess.run") as run_mock:
            run_mock.return_value.returncode = 0

            rc = run_browser_compare_hidden_service.main()

        self.assertEqual(rc, 0)
        cmd = run_mock.call_args.args[0]
        self.assertIn("--compact-output", cmd)
        proxy_log_flag = "--proxy-log-tail-lines"
        self.assertIn(proxy_log_flag, cmd)
        self.assertEqual(cmd[cmd.index(proxy_log_flag) + 1], "400")
        proxy_run_flag = "--proxy-run-tail-lines"
        self.assertIn(proxy_run_flag, cmd)
        self.assertEqual(cmd[cmd.index(proxy_run_flag) + 1], "120")


if __name__ == "__main__":
    unittest.main()
