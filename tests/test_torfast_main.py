import json
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from torfast import fast_runtime
from torfast import runtime_helper
from torfast.__main__ import main
from torfast.cli import build_action_command


class TorfastMainTests(unittest.TestCase):
    EXISTING_BIN = str(Path("/bin/echo").resolve())

    def test_fast_build_launcher_args_matches_cli_open(self) -> None:
        args = SimpleNamespace(
            command="open",
            browser_bin=self.EXISTING_BIN,
            tor_bin=self.EXISTING_BIN,
            url="https://check.torproject.org/",
            port=19450,
            state_root="/tmp/torfast-open",
            conflux_client_ux="throughput",
            browser_timeout=3.0,
            headless=True,
            skip_browser_default_pref_check=True,
            managed_open_adaptive_general_circuit_wait_timeout=0.75,
            browser_launch_gate="tor_boot_95",
            stream_isolation_probe=True,
            stream_isolation_probe_timeout=4.0,
            dir_cache_seed_root="/tmp/torfast-seed",
            no_dir_cache_seed=True,
            browser_startup_seed_root="/tmp/torfast-browser-seed",
            no_browser_startup_seed=False,
        )

        self.assertEqual(
            fast_runtime.build_launcher_args(args),
            build_action_command(args)[2:],
        )

    def test_fast_build_launcher_args_matches_cli_warm(self) -> None:
        args = SimpleNamespace(
            command="warm",
            browser_bin=self.EXISTING_BIN,
            tor_bin=self.EXISTING_BIN,
            url="about:tor",
            port=19451,
            state_root="/tmp/torfast-warm",
            conflux_client_ux=None,
            browser_timeout=0.0,
            headless=False,
            skip_browser_default_pref_check=False,
            browser_launch_gate=fast_runtime.DEFAULT_BROWSER_LAUNCH_GATE,
            stream_isolation_probe=False,
            stream_isolation_probe_timeout=3.0,
            dir_cache_seed_root=str(fast_runtime.DEFAULT_C_TOR_DIR_CACHE_SEED_ROOT),
            no_dir_cache_seed=False,
            browser_startup_seed_root=str(
                fast_runtime.DEFAULT_BROWSER_STARTUP_SEED_ROOT
            ),
            no_browser_startup_seed=True,
        )

        self.assertEqual(
            fast_runtime.build_launcher_args(args),
            build_action_command(args)[2:],
        )

    def test_fast_build_launcher_args_matches_cli_warm_browser_prestart(self) -> None:
        args = SimpleNamespace(
            command="warm",
            browser_bin=self.EXISTING_BIN,
            tor_bin=self.EXISTING_BIN,
            url="about:tor",
            port=19451,
            state_root="/tmp/torfast-warm",
            conflux_client_ux=None,
            browser_timeout=0.0,
            headless=False,
            skip_browser_default_pref_check=False,
            gate_diagnostics=False,
            managed_open_browser_overlap=False,
            warm_browser_prestart=True,
            browser_launch_gate=fast_runtime.DEFAULT_BROWSER_LAUNCH_GATE,
            stream_isolation_probe=False,
            stream_isolation_probe_timeout=3.0,
            dir_cache_seed_root=str(fast_runtime.DEFAULT_C_TOR_DIR_CACHE_SEED_ROOT),
            no_dir_cache_seed=False,
            browser_startup_seed_root=str(
                fast_runtime.DEFAULT_BROWSER_STARTUP_SEED_ROOT
            ),
            no_managed_open_settle=True,
            no_browser_startup_seed=True,
        )

        self.assertEqual(
            fast_runtime.build_launcher_args(args),
            build_action_command(args)[2:],
        )

    def test_fast_build_launcher_args_matches_cli_prime(self) -> None:
        args = SimpleNamespace(
            command="prime",
            browser_bin=self.EXISTING_BIN,
            tor_bin=self.EXISTING_BIN,
            url="about:tor",
            port=19451,
            state_root="/tmp/torfast-prime",
            conflux_client_ux=None,
            browser_timeout=0.0,
            headless=False,
            skip_browser_default_pref_check=False,
            gate_diagnostics=False,
            managed_open_browser_overlap=False,
            warm_browser_prestart=False,
            browser_launch_gate=fast_runtime.DEFAULT_BROWSER_LAUNCH_GATE,
            stream_isolation_probe=False,
            stream_isolation_probe_timeout=3.0,
            dir_cache_seed_root=str(fast_runtime.DEFAULT_C_TOR_DIR_CACHE_SEED_ROOT),
            no_dir_cache_seed=False,
            browser_startup_seed_root=str(
                fast_runtime.DEFAULT_BROWSER_STARTUP_SEED_ROOT
            ),
            no_managed_open_settle=True,
            no_browser_startup_seed=True,
        )

        self.assertEqual(
            fast_runtime.build_launcher_args(args),
            build_action_command(args)[2:],
        )
        launcher_args = fast_runtime.build_launcher_args(args)
        self.assertIn("--browser-launch-gate", launcher_args)
        self.assertIn("tor_boot_100", launcher_args)

    def test_fast_build_launcher_args_matches_cli_stop(self) -> None:
        args = SimpleNamespace(
            command="stop",
            state_root="/tmp/torfast-stop",
        )

        self.assertEqual(
            fast_runtime.build_launcher_args(args),
            build_action_command(args)[2:],
        )

    def test_resolve_wait_ready_gate_promotes_auto_to_95(self) -> None:
        self.assertEqual(
            fast_runtime.resolve_wait_ready_gate(
                fast_runtime.DEFAULT_BROWSER_LAUNCH_GATE
            ),
            "tor_boot_95",
        )
        self.assertEqual(
            fast_runtime.resolve_wait_ready_gate("tor_boot_100"),
            "tor_boot_100",
        )

    def test_fast_build_launcher_args_generates_fresh_launch_root(self) -> None:
        args = SimpleNamespace(
            command="launch",
            browser_bin=self.EXISTING_BIN,
            tor_bin=self.EXISTING_BIN,
            url="about:tor",
            port=19452,
            state_root=fast_runtime.AUTO_STATE_ROOT,
            conflux_client_ux=None,
            browser_timeout=0.0,
            headless=False,
            skip_browser_default_pref_check=False,
            browser_launch_gate=fast_runtime.DEFAULT_BROWSER_LAUNCH_GATE,
            stream_isolation_probe=False,
            stream_isolation_probe_timeout=3.0,
            dir_cache_seed_root=str(fast_runtime.DEFAULT_C_TOR_DIR_CACHE_SEED_ROOT),
            no_dir_cache_seed=False,
            browser_startup_seed_root=str(
                fast_runtime.DEFAULT_BROWSER_STARTUP_SEED_ROOT
            ),
            no_browser_startup_seed=True,
        )

        with (
            patch("torfast.fast_runtime.time.strftime", return_value="20260625T090000"),
            patch("torfast.fast_runtime.time.time_ns", return_value=1234567890),
            patch("torfast.fast_runtime.os.getpid", return_value=4242),
        ):
            launcher_args = fast_runtime.build_launcher_args(args)

        self.assertIn("--state-root", launcher_args)
        self.assertEqual(
            launcher_args[launcher_args.index("--state-root") + 1],
            str(
                (
                    fast_runtime.DEFAULT_FRESH_STATE_ROOT_PARENT
                    / "launch-20260625T090000-4242-234567890"
                ).resolve()
            ),
        )

    def test_parse_runtime_action_args_returns_none_for_help(self) -> None:
        self.assertIsNone(fast_runtime.parse_runtime_action_args(["open", "--help"]))

    def test_runtime_helper_socket_path_stays_short(self) -> None:
        socket_path = fast_runtime.runtime_helper_socket_path(
            Path("/tmp/" + ("very-long-state-root-" * 8))
        )

        self.assertLess(len(str(socket_path)), 100)

    def test_maybe_wait_for_runtime_helper_returns_none_without_wait(self) -> None:
        with (
            patch(
                "torfast.fast_runtime.running_runtime_helper_metadata",
                return_value=None,
            ),
            patch(
                "torfast.fast_runtime.runtime_helper_start_pending",
                return_value=True,
            ),
            patch("torfast.fast_runtime.time.sleep") as sleep,
        ):
            result = fast_runtime.maybe_wait_for_runtime_helper(Path("/tmp/helper"))

        self.assertIsNone(result)
        sleep.assert_not_called()

    def test_should_prestart_runtime_helper_for_warm_requires_opt_in_env(self) -> None:
        with (
            patch.dict(
                "torfast.fast_runtime.os.environ",
                {
                    fast_runtime.WARM_RUNTIME_HELPER_PRESTART_ENABLED_ENV: "1",
                },
                clear=False,
            ),
            patch(
                "torfast.fast_runtime.running_runtime_helper_metadata",
                return_value=None,
            ),
            patch(
                "torfast.fast_runtime.runtime_helper_start_pending",
                return_value=False,
            ),
        ):
            self.assertTrue(
                fast_runtime.should_prestart_runtime_helper_for_warm(
                    Path("/tmp/helper")
                )
            )
        with (
            patch.dict("torfast.fast_runtime.os.environ", {}, clear=True),
            patch(
                "torfast.fast_runtime.running_runtime_helper_metadata",
                return_value=None,
            ),
            patch(
                "torfast.fast_runtime.runtime_helper_start_pending",
                return_value=False,
            ),
        ):
            self.assertFalse(
                fast_runtime.should_prestart_runtime_helper_for_warm(
                    Path("/tmp/helper")
                )
            )

    def test_runtime_helper_write_metadata_includes_context(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            state_root = Path(tempdir) / "state-root"
            state_root.mkdir(parents=True, exist_ok=True)

            runtime_helper.write_metadata(state_root)

            payload = json.loads(
                fast_runtime.runtime_helper_json_path(state_root).read_text()
            )

        self.assertEqual(
            payload["context"],
            fast_runtime.runtime_helper_context(state_root),
        )

    def test_running_runtime_helper_metadata_accepts_matching_context(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            state_root = Path(tempdir) / "state-root"
            state_root.mkdir(parents=True, exist_ok=True)
            socket_path = fast_runtime.runtime_helper_socket_path(state_root)
            socket_path.write_text("", encoding="utf-8")
            metadata = {
                "pid": 1234,
                "socket_path": str(socket_path),
                "fingerprint": fast_runtime.runtime_helper_file_fingerprint(),
                "context": fast_runtime.runtime_helper_context(state_root),
            }
            fast_runtime.runtime_helper_json_path(state_root).write_text(
                json.dumps(metadata),
                encoding="utf-8",
            )

            with patch("torfast.fast_runtime.process_is_alive", return_value=True):
                result = fast_runtime.running_runtime_helper_metadata(state_root)

        self.assertEqual(result, metadata)

    def test_runtime_helper_promotes_managed_service_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            state_root = Path(tempdir) / "state-root"
            state_root.mkdir(parents=True, exist_ok=True)
            service_path = state_root / "tor-service.json"
            service_path.write_text(
                json.dumps(
                    {
                        "pid": 1234,
                        "tor_log": str(state_root / "tor.log"),
                        "ready_gate": "socks_ready",
                    }
                ),
                encoding="utf-8",
            )

            with patch(
                "torfast.runtime_helper.wait_for_existing_service_ready_in_log",
                return_value={
                    "ok": True,
                    "seconds": 0.5,
                    "ready_epoch_ms": 1000.0,
                    "ready_monotonic_seconds": 50.0,
                },
            ):
                result = runtime_helper.promote_managed_service_gate(
                    state_root,
                    gate="tor_boot_95",
                )

            updated = json.loads(service_path.read_text())

        self.assertIsNotNone(result)
        self.assertEqual(updated["ready_gate"], "tor_boot_95")
        self.assertEqual(updated["ready_epoch_ms"], 1000.0)
        self.assertEqual(updated["ready_source"], "log")
        self.assertEqual(updated["ready_actor"], "runtime_helper_promoter")
        self.assertEqual(
            updated["ready_gate_history"],
            [
                {
                    "gate": "tor_boot_95",
                    "ready_epoch_ms": 1000.0,
                    "ready_monotonic_seconds": 50.0,
                    "source": "log",
                    "actor": "runtime_helper_promoter",
                    "writer_pid": updated["ready_writer_pid"],
                    "polls": None,
                    "seconds": 0.5,
                }
            ],
        )

    def test_runtime_helper_promotes_managed_service_gate_via_persistent_control(
        self,
    ) -> None:
        class FakeControlClient:
            def __init__(self) -> None:
                self.closed = False

            def close(self) -> None:
                self.closed = True

        with tempfile.TemporaryDirectory() as tempdir:
            state_root = Path(tempdir) / "state-root"
            state_root.mkdir(parents=True, exist_ok=True)
            service_path = state_root / "tor-service.json"
            service_path.write_text(
                json.dumps(
                    {
                        "pid": 1234,
                        "tor_log": str(state_root / "tor.log"),
                        "ready_gate": "socks_ready",
                        "control_port": 29050,
                        "control_cookie_path": str(
                            state_root / "control_auth_cookie"
                        ),
                    }
                ),
                encoding="utf-8",
            )
            fake_client = FakeControlClient()

            with (
                patch(
                    "torfast.runtime_helper.TorControlClient.connect",
                    return_value=fake_client,
                ) as connect,
                patch(
                    "torfast.runtime_helper.control_ready_for_gate_with_client",
                    return_value={
                        "ok": True,
                        "progress": 95,
                        "tag": "circuit_create",
                        "summary": "Establishing a Tor circuit",
                    },
                ) as control_ready,
                patch("torfast.runtime_helper.process_is_alive", return_value=True),
                patch(
                    "torfast.runtime_helper.tail_lines",
                    return_value=[
                        "Bootstrapped 95% (circuit_create): Establishing a Tor circuit"
                    ],
                ),
                patch("torfast.runtime_helper.time.monotonic", return_value=0.0),
                patch("torfast.runtime_helper.time.time", return_value=1.0),
                patch("torfast.runtime_helper.time.sleep") as sleep,
                patch(
                    "torfast.runtime_helper.wait_for_existing_service_ready_in_log"
                ) as fallback_wait,
            ):
                result = runtime_helper.promote_managed_service_gate(
                    state_root,
                    gate="tor_boot_95",
                )

            updated = json.loads(service_path.read_text())

        self.assertIsNotNone(result)
        self.assertEqual(updated["ready_gate"], "tor_boot_95")
        self.assertEqual(updated["ready_epoch_ms"], 1000.0)
        self.assertEqual(updated["ready_source"], "control")
        self.assertEqual(updated["ready_actor"], "runtime_helper_promoter")
        self.assertEqual(updated["ready_gate_history"][0]["source"], "control")
        connect.assert_called_once()
        control_ready.assert_called_once()
        fallback_wait.assert_not_called()
        self.assertTrue(fake_client.closed)
        sleep.assert_not_called()

    def test_runtime_helper_promote_stops_if_service_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            state_root = Path(tempdir) / "state-root"
            state_root.mkdir(parents=True, exist_ok=True)
            service_path = state_root / "tor-service.json"
            service_path.write_text(
                json.dumps(
                    {
                        "pid": 1234,
                        "tor_log": str(state_root / "tor.log"),
                        "ready_gate": "socks_ready",
                    }
                ),
                encoding="utf-8",
            )

            def rewrite_service(*_args, **_kwargs):
                service_path.write_text(
                    json.dumps(
                        {
                            "pid": 9999,
                            "tor_log": str(state_root / "other.log"),
                            "ready_gate": "socks_ready",
                        }
                    ),
                    encoding="utf-8",
                )
                return {
                    "ok": True,
                    "seconds": 0.5,
                    "ready_epoch_ms": 1000.0,
                    "ready_monotonic_seconds": 50.0,
                }

            with patch(
                "torfast.runtime_helper.wait_for_existing_service_ready_in_log",
                side_effect=rewrite_service,
            ):
                result = runtime_helper.promote_managed_service_gate(
                    state_root,
                    gate="tor_boot_95",
                )

            updated = json.loads(service_path.read_text())

        self.assertIsNone(result)
        self.assertEqual(updated["pid"], 9999)
        self.assertEqual(updated["ready_gate"], "socks_ready")

    def test_runtime_helper_watchdog_restarts_promoter_for_partial_service(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            state_root = Path(tempdir) / "state-root"
            state_root.mkdir(parents=True, exist_ok=True)
            (state_root / "tor-service.json").write_text(
                json.dumps(
                    {
                        "pid": 1234,
                        "tor_log": str(state_root / "tor.log"),
                        "ready_gate": "socks_ready",
                    }
                ),
                encoding="utf-8",
            )
            dead_thread = Mock()
            dead_thread.is_alive.return_value = False
            restarted_thread = Mock()

            with (
                patch("torfast.runtime_helper.process_is_alive", return_value=True),
                patch(
                    "torfast.runtime_helper.start_background_gate_promoter",
                    return_value=restarted_thread,
                ) as start_promoter,
            ):
                result = runtime_helper.maybe_restart_background_gate_promoter(
                    state_root,
                    thread=dead_thread,
                )

        self.assertIs(result, restarted_thread)
        start_promoter.assert_called_once_with(state_root, thread=dead_thread)

    def test_runtime_helper_watchdog_skips_fully_ready_service(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            state_root = Path(tempdir) / "state-root"
            state_root.mkdir(parents=True, exist_ok=True)
            (state_root / "tor-service.json").write_text(
                json.dumps(
                    {
                        "pid": 1234,
                        "tor_log": str(state_root / "tor.log"),
                        "ready_gate": "tor_boot_100",
                    }
                ),
                encoding="utf-8",
            )
            dead_thread = Mock()
            dead_thread.is_alive.return_value = False

            with (
                patch("torfast.runtime_helper.process_is_alive", return_value=True),
                patch(
                    "torfast.runtime_helper.start_background_gate_promoter"
                ) as start_promoter,
            ):
                result = runtime_helper.maybe_restart_background_gate_promoter(
                    state_root,
                    thread=dead_thread,
                )

        self.assertIs(result, dead_thread)
        start_promoter.assert_not_called()

    def test_wait_for_managed_service_gate_returns_immediate_ready_report(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            state_root = Path(tempdir) / "state-root"
            state_root.mkdir(parents=True, exist_ok=True)
            service_path = state_root / "tor-service.json"
            service = {
                "pid": 1234,
                "tor_log": str(state_root / "tor.log"),
                "ready_gate": "tor_boot_100",
                "ready_epoch_ms": 1000.0,
                "ready_monotonic_seconds": 50.0,
            }
            service_path.write_text(json.dumps(service), encoding="utf-8")

            with patch("torfast.fast_runtime.process_is_alive", return_value=True):
                report = fast_runtime.wait_for_managed_service_gate(
                    state_root,
                    requested_gate="tor_boot_95",
                    timeout=30.0,
                )

        self.assertTrue(report["ok"])
        self.assertTrue(report["already_ready"])
        self.assertEqual(report["resolved_gate"], "tor_boot_95")
        self.assertEqual(report["service_after"], service)
        self.assertEqual(report["wait"]["seconds"], 0.0)

    def test_wait_for_managed_service_gate_waits_and_updates_service(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            state_root = Path(tempdir) / "state-root"
            state_root.mkdir(parents=True, exist_ok=True)
            service_path = state_root / "tor-service.json"
            service = {
                "pid": 1234,
                "tor_log": str(state_root / "tor.log"),
                "ready_gate": "socks_ready",
            }
            service_path.write_text(json.dumps(service), encoding="utf-8")

            with (
                patch("torfast.fast_runtime.process_is_alive", return_value=True),
                patch(
                    "torfast.fast_runtime.running_runtime_helper_metadata",
                    return_value=None,
                ),
                patch("torfast.fast_runtime.start_runtime_helper") as start_helper,
                patch(
                    "torfast.runtime_helper.wait_for_existing_service_ready_in_log",
                    return_value={
                        "ok": True,
                        "seconds": 0.6,
                        "ready_epoch_ms": 1200.0,
                        "ready_monotonic_seconds": 51.0,
                        "polls": 2,
                        "lines": ["Bootstrapped 95% (circuit_create): Establishing a Tor circuit"],
                        "signal_lines": [],
                    },
                ),
            ):
                report = fast_runtime.wait_for_managed_service_gate(
                    state_root,
                    requested_gate=fast_runtime.DEFAULT_BROWSER_LAUNCH_GATE,
                    timeout=30.0,
                )

            updated = json.loads(service_path.read_text())

        self.assertTrue(report["ok"])
        self.assertFalse(report["already_ready"])
        self.assertEqual(report["resolved_gate"], "tor_boot_95")
        self.assertEqual(updated["ready_gate"], "tor_boot_95")
        self.assertEqual(updated["ready_epoch_ms"], 1200.0)
        self.assertEqual(updated["ready_source"], "log")
        self.assertEqual(updated["ready_actor"], "fast_runtime_wait_ready")
        self.assertEqual(updated["ready_gate_history"][0]["actor"], "fast_runtime_wait_ready")
        start_helper.assert_called_once_with(state_root)

    def test_parse_runtime_action_args_returns_none_for_unknown_flag(self) -> None:
        self.assertIsNone(
            fast_runtime.parse_runtime_action_args(["open", "--unknown-flag"])
        )

    def test_parse_runtime_action_args_returns_none_for_conflicting_seed_flags(
        self,
    ) -> None:
        self.assertIsNone(
            fast_runtime.parse_runtime_action_args(
                ["open", "--browser-startup-seed", "--no-browser-startup-seed"]
            )
        )

    def test_parse_runtime_action_args_accepts_gate_diagnostics(self) -> None:
        args = fast_runtime.parse_runtime_action_args(["open", "--gate-diagnostics"])

        self.assertIsNotNone(args)
        assert args is not None
        self.assertTrue(args.gate_diagnostics)

    def test_parse_runtime_action_args_accepts_managed_open_settle(self) -> None:
        args = fast_runtime.parse_runtime_action_args(
            ["open", "--managed-open-settle"]
        )

        self.assertIsNotNone(args)
        assert args is not None
        self.assertFalse(args.no_managed_open_settle)

    def test_parse_runtime_action_args_accepts_managed_open_browser_overlap(
        self,
    ) -> None:
        args = fast_runtime.parse_runtime_action_args(
            ["open", "--managed-open-browser-overlap"]
        )

        self.assertIsNotNone(args)
        assert args is not None
        self.assertFalse(args.no_managed_open_browser_overlap)

    def test_parse_runtime_action_args_accepts_managed_open_adaptive_wait_timeout(
        self,
    ) -> None:
        args = fast_runtime.parse_runtime_action_args(
            [
                "open",
                "--managed-open-adaptive-general-circuit-wait-timeout",
                "0.75",
            ]
        )

        self.assertIsNotNone(args)
        assert args is not None
        self.assertEqual(
            args.managed_open_adaptive_general_circuit_wait_timeout,
            0.75,
        )

    def test_parse_runtime_action_args_accepts_managed_open_browser_overlap_opt_out(
        self,
    ) -> None:
        args = fast_runtime.parse_runtime_action_args(
            ["open", "--no-managed-open-browser-overlap"]
        )

        self.assertIsNotNone(args)
        assert args is not None
        self.assertTrue(args.no_managed_open_browser_overlap)

    def test_parse_wait_ready_action_args_accepts_defaults(self) -> None:
        args = fast_runtime.parse_wait_ready_action_args(["wait-ready"])

        self.assertIsNotNone(args)
        assert args is not None
        self.assertEqual(args.command, "wait-ready")
        self.assertEqual(args.state_root, str(fast_runtime.DEFAULT_STATE_ROOT))
        self.assertEqual(args.gate, fast_runtime.DEFAULT_BROWSER_LAUNCH_GATE)
        self.assertEqual(args.timeout, fast_runtime.DEFAULT_WAIT_READY_TIMEOUT)

    def test_parse_wait_ready_action_args_accepts_explicit_values(self) -> None:
        args = fast_runtime.parse_wait_ready_action_args(
            [
                "wait-ready",
                "--state-root",
                "/tmp/torfast-warm",
                "--gate",
                "tor_boot_100",
                "--timeout",
                "45",
            ]
        )

        self.assertIsNotNone(args)
        assert args is not None
        self.assertEqual(args.state_root, "/tmp/torfast-warm")
        self.assertEqual(args.gate, "tor_boot_100")
        self.assertEqual(args.timeout, 45.0)

    def test_main_uses_fast_path_for_open(self) -> None:
        launcher_main = Mock(return_value=7)

        with patch(
            "torfast.fast_runtime.request_runtime_helper",
            return_value={"status": "unavailable"},
        ), patch(
            "torfast.fast_runtime.load_launcher_main",
            return_value=launcher_main,
        ), patch.dict(os.environ, {"TORFAST_PROFILE": "balanced"}):
            exit_code = main(
                [
                    "open",
                    "--browser-bin",
                    self.EXISTING_BIN,
                    "--tor-bin",
                    self.EXISTING_BIN,
                    "--state-root",
                    "/tmp/torfast-fast-open",
                ]
            )

        self.assertEqual(exit_code, 7)
        launcher_main.assert_called_once_with(
            [
                "--browser-bin",
                self.EXISTING_BIN,
                "--tor-bin",
                self.EXISTING_BIN,
                "--url",
                "about:tor",
                "--port",
                "19450",
                "--state-root",
                str(Path("/tmp/torfast-fast-open").resolve()),
                "--managed-open-browser-overlap",
                "--managed-open-adaptive-general-circuit-wait-timeout",
                "0.126",
                "--no-browser-startup-seed",
                "--profile-label",
                "balanced",
                "--leave-tor-running",
                "--reuse-tor-if-running",
            ]
        )

    def test_main_uses_runtime_helper_for_open_when_available(self) -> None:
        with (
            patch(
                "torfast.fast_runtime.request_runtime_helper",
                return_value={
                    "status": "ok",
                    "response": {
                        "exit_code": 5,
                        "stdout": "helper-stdout\n",
                        "stderr": "helper-stderr\n",
                    },
                },
            ),
            patch("torfast.fast_runtime.load_launcher_main") as load_launcher_main,
            patch("sys.stdout", new_callable=io.StringIO) as stdout,
            patch("sys.stderr", new_callable=io.StringIO) as stderr,
        ):
            exit_code = main(
                [
                    "open",
                    "--browser-bin",
                    self.EXISTING_BIN,
                    "--tor-bin",
                    self.EXISTING_BIN,
                    "--state-root",
                    "/tmp/torfast-helper-open",
                ]
            )

        self.assertEqual(exit_code, 5)
        self.assertEqual(stdout.getvalue(), "helper-stdout\n")
        self.assertEqual(stderr.getvalue(), "helper-stderr\n")
        load_launcher_main.assert_not_called()

    def test_open_overlap_skips_prelaunch_adaptive_wait(self) -> None:
        launcher_main = Mock(return_value=0)

        with (
            patch(
                "torfast.fast_runtime.request_runtime_helper",
                return_value={"status": "unavailable"},
            ),
            patch(
                "torfast.fast_runtime.load_launcher_main",
                return_value=launcher_main,
            ),
            patch(
                "torfast.fast_runtime.clear_managed_open_adaptive_general_circuit_wait_report"
            ) as clear_report,
            patch(
                "torfast.fast_runtime.maybe_wait_for_managed_open_general_circuit_before_launch"
            ) as prelaunch_wait,
        ):
            exit_code = main(
                [
                    "open",
                    "--browser-bin",
                    self.EXISTING_BIN,
                    "--tor-bin",
                    self.EXISTING_BIN,
                    "--state-root",
                    "/tmp/torfast-fast-open",
                    "--managed-open-adaptive-general-circuit-wait-timeout",
                    "0.75",
                ]
            )

        self.assertEqual(exit_code, 0)
        clear_report.assert_called_once_with(Path("/tmp/torfast-fast-open").resolve())
        prelaunch_wait.assert_not_called()

    def test_open_without_overlap_keeps_prelaunch_adaptive_wait(self) -> None:
        launcher_main = Mock(return_value=0)

        with (
            patch(
                "torfast.fast_runtime.request_runtime_helper",
                return_value={"status": "unavailable"},
            ),
            patch(
                "torfast.fast_runtime.load_launcher_main",
                return_value=launcher_main,
            ),
            patch(
                "torfast.fast_runtime.clear_managed_open_adaptive_general_circuit_wait_report"
            ) as clear_report,
            patch(
                "torfast.fast_runtime.maybe_wait_for_managed_open_general_circuit_before_launch",
                return_value={"ok": True, "reason": "timeout_proceed"},
            ) as prelaunch_wait,
            patch("torfast.fast_runtime.write_json_file") as write_json_file,
        ):
            exit_code = main(
                [
                    "open",
                    "--browser-bin",
                    self.EXISTING_BIN,
                    "--tor-bin",
                    self.EXISTING_BIN,
                    "--state-root",
                    "/tmp/torfast-fast-open",
                    "--managed-open-adaptive-general-circuit-wait-timeout",
                    "0.75",
                    "--no-managed-open-browser-overlap",
                ]
            )

        self.assertEqual(exit_code, 0)
        prelaunch_wait.assert_called_once_with(
            Path("/tmp/torfast-fast-open").resolve(),
            requested_gate=fast_runtime.DEFAULT_BROWSER_LAUNCH_GATE,
            timeout=0.75,
        )
        write_json_file.assert_called_once()
        clear_report.assert_not_called()

    def test_main_does_not_fallback_after_helper_dispatch_error(self) -> None:
        with (
            patch(
                "torfast.fast_runtime.request_runtime_helper",
                return_value={
                    "status": "error",
                    "error": "broken pipe",
                },
            ),
            patch("torfast.fast_runtime.load_launcher_main") as load_launcher_main,
            patch("sys.stderr", new_callable=io.StringIO) as stderr,
        ):
            exit_code = main(
                [
                    "open",
                    "--browser-bin",
                    self.EXISTING_BIN,
                    "--tor-bin",
                    self.EXISTING_BIN,
                    "--state-root",
                    "/tmp/torfast-helper-open",
                ]
            )

        self.assertEqual(exit_code, 1)
        self.assertIn("runtime helper request failed after dispatch", stderr.getvalue())
        load_launcher_main.assert_not_called()

    def test_main_falls_back_to_cli_for_status(self) -> None:
        with patch("torfast.cli.main", return_value=9) as cli_main:
            exit_code = main(["status"])

        self.assertEqual(exit_code, 9)
        cli_main.assert_called_once_with(["status"])

    def test_main_uses_fast_path_for_wait_ready(self) -> None:
        with (
            patch(
                "torfast.fast_runtime.wait_for_managed_service_gate",
                return_value={"ok": True, "resolved_gate": "tor_boot_95"},
            ) as wait_ready,
            patch("sys.stdout", new_callable=io.StringIO) as stdout,
            patch("torfast.cli.main") as cli_main,
        ):
            exit_code = main(["wait-ready", "--state-root", "/tmp/torfast-warm"])

        self.assertEqual(exit_code, 0)
        wait_ready.assert_called_once_with(
            Path("/tmp/torfast-warm").resolve(),
            requested_gate=fast_runtime.DEFAULT_BROWSER_LAUNCH_GATE,
            timeout=fast_runtime.DEFAULT_WAIT_READY_TIMEOUT,
        )
        self.assertEqual(
            json.loads(stdout.getvalue()),
            {"ok": True, "resolved_gate": "tor_boot_95"},
        )
        cli_main.assert_not_called()

    def test_main_falls_back_to_cli_for_wait_ready_help(self) -> None:
        with patch("torfast.cli.main", return_value=15) as cli_main:
            exit_code = main(["wait-ready", "--help"])

        self.assertEqual(exit_code, 15)
        cli_main.assert_called_once_with(["wait-ready", "--help"])

    def test_main_falls_back_to_cli_for_help(self) -> None:
        with patch("torfast.cli.main", return_value=11) as cli_main:
            exit_code = main(["open", "--help"])

        self.assertEqual(exit_code, 11)
        cli_main.assert_called_once_with(["open", "--help"])

    def test_main_falls_back_to_cli_for_unknown_fast_arg(self) -> None:
        with patch("torfast.cli.main", return_value=13) as cli_main:
            exit_code = main(["open", "--unknown-flag"])

        self.assertEqual(exit_code, 13)
        cli_main.assert_called_once_with(["open", "--unknown-flag"])

    def test_warm_success_starts_runtime_helper(self) -> None:
        launcher_main = Mock(return_value=0)
        events: list[str] = []

        def record_start(state_root: Path) -> None:
            self.assertEqual(state_root, Path("/tmp/torfast-warm-helper").resolve())
            events.append("start")

        def record_launch(argv: list[str]) -> int:
            events.append("launch")
            return launcher_main(argv)

        with (
            patch.dict(
                "torfast.fast_runtime.os.environ",
                {
                    fast_runtime.WARM_RUNTIME_HELPER_PRESTART_ENABLED_ENV: "1",
                },
                clear=False,
            ),
            patch(
                "torfast.fast_runtime.load_launcher_main",
                return_value=record_launch,
            ),
            patch(
                "torfast.fast_runtime.start_runtime_helper",
                side_effect=record_start,
            ) as start_runtime_helper,
        ):
            exit_code = main(
                [
                    "warm",
                    "--browser-bin",
                    self.EXISTING_BIN,
                    "--tor-bin",
                    self.EXISTING_BIN,
                    "--state-root",
                    "/tmp/torfast-warm-helper",
                ]
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(events[:2], ["start", "launch"])
        start_runtime_helper.assert_called_once_with(
            Path("/tmp/torfast-warm-helper").resolve()
        )

    def test_warm_failure_stops_prestarted_runtime_helper(self) -> None:
        launcher_main = Mock(return_value=1)

        with (
            patch.dict(
                "torfast.fast_runtime.os.environ",
                {
                    fast_runtime.WARM_RUNTIME_HELPER_PRESTART_ENABLED_ENV: "1",
                },
                clear=False,
            ),
            patch(
                "torfast.fast_runtime.load_launcher_main",
                return_value=launcher_main,
            ),
            patch("torfast.fast_runtime.start_runtime_helper") as start_runtime_helper,
            patch("torfast.fast_runtime.stop_runtime_helper") as stop_runtime_helper,
        ):
            exit_code = main(
                [
                    "warm",
                    "--browser-bin",
                    self.EXISTING_BIN,
                    "--tor-bin",
                    self.EXISTING_BIN,
                    "--state-root",
                    "/tmp/torfast-warm-helper",
                ]
            )

        self.assertEqual(exit_code, 1)
        start_runtime_helper.assert_called_once_with(
            Path("/tmp/torfast-warm-helper").resolve()
        )
        stop_runtime_helper.assert_called_once_with(
            Path("/tmp/torfast-warm-helper").resolve()
        )

    def test_stop_shuts_down_runtime_helper(self) -> None:
        launcher_main = Mock(return_value=0)

        with (
            patch(
                "torfast.fast_runtime.load_launcher_main",
                return_value=launcher_main,
            ),
            patch("torfast.fast_runtime.stop_runtime_helper") as stop_runtime_helper,
        ):
            exit_code = main(["stop", "--state-root", "/tmp/torfast-stop-helper"])

        self.assertEqual(exit_code, 0)
        stop_runtime_helper.assert_called_once_with(
            Path("/tmp/torfast-stop-helper").resolve()
        )


if __name__ == "__main__":
    unittest.main()
