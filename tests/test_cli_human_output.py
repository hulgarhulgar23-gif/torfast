import contextlib
import io
import json
import sys
import unittest
from pathlib import Path
from unittest import mock


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from torfast import cli


def sample_launch_summary() -> dict[str, object]:
    return {
        "url": "https://check.torproject.org/",
        "port": 19450,
        "browser_launch_gate": "tor_boot_95",
        "browser": {"ok": True, "elapsed_seconds": 4.51, "exit_code": 0},
        "tor_boot": {"ok": True, "seconds": 0.9},
        "browser_default_pref_check": {"ok": True},
    }


class ParseLauncherOutputTests(unittest.TestCase):
    def test_parses_wrote_line_and_json_summary(self) -> None:
        captured = (
            "wrote /tmp/state/launch.json\n"
            + json.dumps(sample_launch_summary(), indent=2)
            + "\n"
        )
        wrote_path, summary = cli.parse_launcher_output(captured)
        self.assertEqual(wrote_path, "/tmp/state/launch.json")
        self.assertEqual(summary["port"], 19450)

    def test_returns_none_summary_for_garbage(self) -> None:
        wrote_path, summary = cli.parse_launcher_output("no json here\n")
        self.assertIsNone(wrote_path)
        self.assertIsNone(summary)

    def test_returns_none_summary_for_broken_json(self) -> None:
        wrote_path, summary = cli.parse_launcher_output(
            "wrote /tmp/x.json\n{broken\n"
        )
        self.assertEqual(wrote_path, "/tmp/x.json")
        self.assertIsNone(summary)


class RenderActionReceiptTests(unittest.TestCase):
    def test_receipt_shows_core_rows_without_ansi(self) -> None:
        receipt = cli.render_action_receipt(
            "open",
            sample_launch_summary(),
            wrote_path="/tmp/state/launch.json",
            wall_seconds=6.2,
            exit_code=0,
            enabled=False,
        )
        self.assertIn("✓ open done", receipt)
        self.assertIn("wall 6.2s", receipt)
        self.assertIn("https://check.torproject.org/", receipt)
        self.assertIn("tor ready", receipt)
        self.assertIn("0.9s", receipt)
        self.assertIn("browser session", receipt)
        self.assertIn("4.5s", receipt)
        self.assertIn("socks port", receipt)
        self.assertIn("/tmp/state/launch.json", receipt)
        self.assertNotIn("\x1b[", receipt)

    def test_receipt_marks_failure(self) -> None:
        receipt = cli.render_action_receipt(
            "launch",
            {},
            wrote_path=None,
            wall_seconds=1.0,
            exit_code=3,
            enabled=False,
        )
        self.assertIn("✗ launch failed", receipt)


class RenderStatusHumanTests(unittest.TestCase):
    def test_warm_status(self) -> None:
        report = {
            "ok": True,
            "paths": {"state_root": "/tmp/state"},
            "managed_tor": {
                "configured": True,
                "running": True,
                "stale": False,
                "pid": 4242,
                "port": 19450,
            },
            "last_launch": {"url": "https://example.org/"},
        }
        text = cli.render_status_human(report, enabled=False)
        self.assertIn("torfast status", text)
        self.assertIn("● warm", text)
        self.assertIn("4242", text)
        self.assertIn("19450", text)
        self.assertIn("https://example.org/", text)
        self.assertIn("/tmp/state", text)

    def test_off_status(self) -> None:
        report = {
            "ok": True,
            "paths": {"state_root": "/tmp/state"},
            "managed_tor": {
                "configured": False,
                "running": False,
                "stale": False,
                "pid": None,
                "port": None,
            },
            "last_launch": None,
        }
        text = cli.render_status_human(report, enabled=False)
        self.assertIn("○ off", text)
        self.assertIn("none", text)


class RenderDoctorHumanTests(unittest.TestCase):
    def doctor_report(self, *, ok: bool = True) -> dict[str, object]:
        return {
            "ok": ok,
            "browser": {
                "found": True,
                "path": "/apps/firefox",
                "default_pref_check": {"ok": True},
            },
            "tor": {
                "found": True,
                "path": "/apps/tor",
                "version": {"ok": True, "output": "Tor version 0.4.9.11."},
            },
            "managed_state": {
                "managed_tor": {"running": False},
            },
            "dir_cache_seed": {"present": True},
            "browser_startup_seed": {"exists": False},
        }

    def test_doctor_checklist(self) -> None:
        text = cli.render_doctor_human(self.doctor_report(), enabled=False)
        self.assertIn("✓ Tor Browser binary", text)
        self.assertIn("✓ C Tor binary  Tor version 0.4.9.11.", text)
        self.assertIn("✓ browser privacy defaults", text)
        self.assertIn("○ managed tor  not running", text)
        self.assertIn("● dir-cache seed  present", text)
        self.assertIn("○ browser startup seed  absent", text)
        self.assertIn("✓ overall", text)

    def test_doctor_failure_points_to_json(self) -> None:
        text = cli.render_doctor_human(self.doctor_report(ok=False), enabled=False)
        self.assertIn("✗ overall  see torfast doctor --json", text)


class RenderWaitReadyHumanTests(unittest.TestCase):
    def test_ready_line(self) -> None:
        text = cli.render_wait_ready_human(
            {"ok": True, "gate": "tor_boot_95", "waited_seconds": 2.4},
            enabled=False,
        )
        self.assertEqual(text, "  ✓ managed tor ready  gate tor_boot_95 in 2.4s")

    def test_failure_line(self) -> None:
        text = cli.render_wait_ready_human({"ok": False}, enabled=False)
        self.assertIn("✗ wait-ready failed", text)


class MainHumanDispatchTests(unittest.TestCase):
    def test_status_human_mode_renders_panel(self) -> None:
        stdout = io.StringIO()
        with mock.patch.object(cli, "human_output_enabled", return_value=True):
            with contextlib.redirect_stdout(stdout):
                exit_code = cli.main(["status"])
        self.assertEqual(exit_code, 0)
        output = stdout.getvalue()
        self.assertIn("torfast status", output)
        self.assertNotIn('"managed_tor"', output)

    def test_status_json_stays_machine_readable(self) -> None:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            exit_code = cli.main(["status", "--json"])
        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertIn("managed_tor", payload)

    def test_action_human_mode_prints_receipt(self) -> None:
        def fake_run(command: list[str]) -> int:
            print("wrote /tmp/state/launch.json")
            print(json.dumps(sample_launch_summary(), indent=2))
            return 0

        stdout = io.StringIO()
        with mock.patch.object(cli, "human_output_enabled", return_value=True):
            with mock.patch.object(cli, "run_action_command", fake_run):
                with mock.patch.object(
                    cli, "build_action_command", return_value=["cmd"]
                ):
                    with contextlib.redirect_stdout(stdout):
                        exit_code = cli.main(["open"])
        self.assertEqual(exit_code, 0)
        output = stdout.getvalue()
        self.assertIn("open done", output)
        self.assertIn("https://check.torproject.org/", output)
        self.assertNotIn('"browser_launch_gate"', output)

    def test_action_human_mode_falls_back_to_raw_output(self) -> None:
        def fake_run(command: list[str]) -> int:
            print("something unexpected")
            return 1

        stdout = io.StringIO()
        with mock.patch.object(cli, "human_output_enabled", return_value=True):
            with mock.patch.object(cli, "run_action_command", fake_run):
                with mock.patch.object(
                    cli, "build_action_command", return_value=["cmd"]
                ):
                    with contextlib.redirect_stdout(stdout):
                        exit_code = cli.main(["open"])
        self.assertEqual(exit_code, 1)
        output = stdout.getvalue()
        self.assertIn("something unexpected", output)
        self.assertIn("✗ open failed", output)

    def test_fast_action_human_renders_receipt(self) -> None:
        def fake_fast_action(argv: list[str]) -> int:
            print("wrote /tmp/state/launch.json")
            print(json.dumps(sample_launch_summary(), indent=2))
            return 0

        stdout = io.StringIO()
        with mock.patch(
            "torfast.fast_runtime.try_fast_action", fake_fast_action
        ):
            with contextlib.redirect_stdout(stdout):
                exit_code = cli.run_fast_action_human(["open"])
        self.assertEqual(exit_code, 0)
        output = stdout.getvalue()
        self.assertIn("open done", output)
        self.assertIn("https://check.torproject.org/", output)

    def test_fast_action_human_falls_through_for_non_fast_commands(self) -> None:
        stdout = io.StringIO()
        with mock.patch(
            "torfast.fast_runtime.try_fast_action", lambda argv: None
        ):
            with contextlib.redirect_stdout(stdout):
                result = cli.run_fast_action_human(["status"])
        self.assertIsNone(result)
        self.assertEqual(stdout.getvalue(), "")

    def test_fast_action_human_renders_wait_ready_line(self) -> None:
        def fake_fast_action(argv: list[str]) -> int:
            print(
                json.dumps(
                    {"ok": True, "gate": "tor_boot_95", "waited_seconds": 1.2}
                )
            )
            return 0

        stdout = io.StringIO()
        with mock.patch(
            "torfast.fast_runtime.try_fast_action", fake_fast_action
        ):
            with contextlib.redirect_stdout(stdout):
                exit_code = cli.run_fast_action_human(["wait-ready"])
        self.assertEqual(exit_code, 0)
        self.assertIn("managed tor ready", stdout.getvalue())

    def test_module_main_uses_human_wrapper_on_tty(self) -> None:
        from torfast import __main__ as module_main

        stdout = io.StringIO()
        with mock.patch.object(
            module_main, "human_output_enabled", return_value=True
        ):
            with mock.patch.object(
                cli, "run_fast_action_human", return_value=7
            ) as wrapper:
                with contextlib.redirect_stdout(stdout):
                    exit_code = module_main.main(["open"])
        self.assertEqual(exit_code, 7)
        wrapper.assert_called_once_with(["open"])

    def test_module_main_keeps_machine_path_with_json_flag(self) -> None:
        from torfast import __main__ as module_main

        with mock.patch.object(
            module_main, "human_output_enabled", return_value=True
        ):
            with mock.patch.object(
                module_main, "try_fast_action", return_value=5
            ) as fast:
                exit_code = module_main.main(["open", "--json"])
        self.assertEqual(exit_code, 5)
        fast.assert_called_once_with(["open", "--json"])

    def test_version_banner_prints_wordmark(self) -> None:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            with self.assertRaises(SystemExit) as ctx:
                cli.main(["--version"])
        self.assertEqual(ctx.exception.code, 0)
        output = stdout.getvalue()
        self.assertIn("torfast 0.1.0", output)
        self.assertIn("█", output)


if __name__ == "__main__":
    unittest.main()
