import io
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from torfast import fast_runtime
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

    def test_fast_build_launcher_args_matches_cli_stop(self) -> None:
        args = SimpleNamespace(
            command="stop",
            state_root="/tmp/torfast-stop",
        )

        self.assertEqual(
            fast_runtime.build_launcher_args(args),
            build_action_command(args)[2:],
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

    def test_main_uses_fast_path_for_open(self) -> None:
        launcher_main = Mock(return_value=7)

        with patch(
            "torfast.fast_runtime.request_runtime_helper",
            return_value={"status": "unavailable"},
        ), patch(
            "torfast.fast_runtime.load_launcher_main",
            return_value=launcher_main,
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
                "--no-browser-startup-seed",
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

        with (
            patch(
                "torfast.fast_runtime.load_launcher_main",
                return_value=launcher_main,
            ),
            patch("torfast.fast_runtime.start_runtime_helper") as start_runtime_helper,
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
        start_runtime_helper.assert_called_once_with(
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
