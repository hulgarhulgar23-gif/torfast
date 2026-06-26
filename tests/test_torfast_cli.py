import json
import io
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from torfast.cli import (
    AUTO_STATE_ROOT,
    DEFAULT_BROWSER_LAUNCH_GATE,
    DEFAULT_FRESH_STATE_ROOT_PARENT,
    DEFAULT_STATE_ROOT,
    build_parser,
    build_action_command,
    collect_doctor,
    collect_status,
    discover_browser_bin,
    discover_tor_bin,
    main,
    resolve_runtime_state_root,
    resolve_state_paths,
)


class TorfastCliTests(unittest.TestCase):
    EXISTING_BIN = str(Path(sys.executable).resolve())

    def test_resolve_state_paths(self) -> None:
        root = Path("/tmp/torfast-cli")

        paths = resolve_state_paths(root)

        self.assertEqual(paths.state_root, root)
        self.assertEqual(paths.tor_service_json, root / "tor-service.json")
        self.assertEqual(paths.launch_json, root / "launch.json")

    def test_build_start_command_keeps_warm_service(self) -> None:
        args = SimpleNamespace(
            command="start",
            browser_bin=self.EXISTING_BIN,
            tor_bin=self.EXISTING_BIN,
            url="about:tor",
            port=19450,
            state_root=str(DEFAULT_STATE_ROOT),
            conflux_client_ux=None,
            browser_timeout=0.0,
            headless=False,
            skip_browser_default_pref_check=False,
            dir_cache_seed_root="/tmp/torfast-seed",
            no_dir_cache_seed=False,
            browser_startup_seed_root="/tmp/torfast-browser-startup-seed",
            no_browser_startup_seed=False,
        )

        command = build_action_command(args)

        self.assertIn("--leave-tor-running", command)
        self.assertIn("--reuse-tor-if-running", command)
        self.assertNotIn("--dry-run", command)

    def test_build_warm_command_skips_browser_launch(self) -> None:
        args = SimpleNamespace(
            command="warm",
            browser_bin=self.EXISTING_BIN,
            tor_bin=self.EXISTING_BIN,
            url="about:tor",
            port=19450,
            state_root=str(DEFAULT_STATE_ROOT),
            conflux_client_ux=None,
            browser_timeout=0.0,
            headless=False,
            skip_browser_default_pref_check=False,
            dir_cache_seed_root="/tmp/torfast-seed",
            no_dir_cache_seed=False,
            browser_startup_seed_root="/tmp/torfast-browser-startup-seed",
            no_browser_startup_seed=False,
        )

        command = build_action_command(args)

        self.assertIn("--leave-tor-running", command)
        self.assertIn("--reuse-tor-if-running", command)
        self.assertIn("--start-managed-tor-only", command)

    def test_build_prime_command_primes_without_leaving_service_running(self) -> None:
        args = SimpleNamespace(
            command="prime",
            browser_bin=self.EXISTING_BIN,
            tor_bin=self.EXISTING_BIN,
            url="about:tor",
            port=19450,
            state_root=str(DEFAULT_STATE_ROOT),
            conflux_client_ux=None,
            browser_timeout=0.0,
            headless=False,
            skip_browser_default_pref_check=False,
            dir_cache_seed_root="/tmp/torfast-seed",
            no_dir_cache_seed=False,
            browser_startup_seed_root="/tmp/torfast-browser-startup-seed",
            no_browser_startup_seed=False,
        )

        command = build_action_command(args)

        self.assertIn("--start-managed-tor-only", command)
        self.assertNotIn("--leave-tor-running", command)
        self.assertNotIn("--reuse-tor-if-running", command)

    def test_build_launch_command_is_one_shot(self) -> None:
        args = SimpleNamespace(
            command="launch",
            browser_bin=self.EXISTING_BIN,
            tor_bin=self.EXISTING_BIN,
            url="about:tor",
            port=19450,
            state_root=str(DEFAULT_STATE_ROOT),
            conflux_client_ux="throughput",
            browser_timeout=30.0,
            headless=True,
            skip_browser_default_pref_check=True,
            dir_cache_seed_root="/tmp/torfast-seed",
            no_dir_cache_seed=False,
            browser_startup_seed_root="/tmp/torfast-browser-startup-seed",
            no_browser_startup_seed=False,
        )

        command = build_action_command(args)

        self.assertNotIn("--leave-tor-running", command)
        self.assertNotIn("--reuse-tor-if-running", command)
        self.assertIn("--conflux-client-ux", command)
        self.assertIn("throughput", command)
        self.assertIn("--browser-timeout", command)
        self.assertIn("30.0", command)
        self.assertIn("--headless", command)
        self.assertIn("--skip-browser-default-pref-check", command)

    def test_build_launch_command_forwards_nondefault_browser_launch_gate(self) -> None:
        args = SimpleNamespace(
            command="launch",
            browser_bin=self.EXISTING_BIN,
            tor_bin=self.EXISTING_BIN,
            url="about:tor",
            port=19450,
            state_root=str(DEFAULT_STATE_ROOT),
            conflux_client_ux=None,
            browser_timeout=0.0,
            headless=False,
            skip_browser_default_pref_check=False,
            browser_launch_gate="tor_boot_100",
            dir_cache_seed_root="/tmp/torfast-seed",
            no_dir_cache_seed=False,
            browser_startup_seed_root="/tmp/torfast-browser-startup-seed",
            no_browser_startup_seed=False,
        )

        command = build_action_command(args)

        self.assertIn("--browser-launch-gate", command)
        self.assertIn("tor_boot_100", command)

    def test_build_launch_command_uses_fresh_state_root_by_default(self) -> None:
        args = SimpleNamespace(
            command="launch",
            browser_bin=self.EXISTING_BIN,
            tor_bin=self.EXISTING_BIN,
            url="about:tor",
            port=19450,
            state_root=AUTO_STATE_ROOT,
            conflux_client_ux=None,
            browser_timeout=0.0,
            headless=False,
            skip_browser_default_pref_check=False,
            dir_cache_seed_root="/tmp/torfast-seed",
            no_dir_cache_seed=False,
            browser_startup_seed_root="/tmp/torfast-browser-startup-seed",
            no_browser_startup_seed=False,
        )

        with (
            patch("torfast.cli.time.strftime", return_value="20260624T130000"),
            patch("torfast.cli.time.time_ns", return_value=1234567890),
            patch("torfast.cli.os.getpid", return_value=4242),
        ):
            command = build_action_command(args)

        state_root = command[command.index("--state-root") + 1]
        self.assertEqual(
            state_root,
            str(
                (
                    DEFAULT_FRESH_STATE_ROOT_PARENT
                    / "launch-20260624T130000-4242-234567890"
                ).resolve()
            ),
        )
        self.assertNotIn("--leave-tor-running", command)
        self.assertNotIn("--reuse-tor-if-running", command)

    def test_build_plan_command_uses_dry_run(self) -> None:
        args = SimpleNamespace(
            command="plan",
            browser_bin=self.EXISTING_BIN,
            tor_bin=self.EXISTING_BIN,
            url="about:tor",
            port=19450,
            state_root=str(DEFAULT_STATE_ROOT),
            conflux_client_ux=None,
            browser_timeout=0.0,
            headless=False,
            skip_browser_default_pref_check=False,
            dir_cache_seed_root="/tmp/torfast-seed",
            no_dir_cache_seed=False,
            browser_startup_seed_root="/tmp/torfast-browser-startup-seed",
            no_browser_startup_seed=False,
        )

        command = build_action_command(args)

        self.assertIn("--dry-run", command)

    def test_parser_defaults_browser_launch_gate_to_socks_ready(self) -> None:
        parser = build_parser()

        args = parser.parse_args(["launch"])

        self.assertEqual(args.browser_launch_gate, DEFAULT_BROWSER_LAUNCH_GATE)

    def test_resolve_runtime_state_root_keeps_explicit_path(self) -> None:
        resolved = resolve_runtime_state_root(
            command="launch",
            state_root="/tmp/torfast-explicit",
        )

        self.assertEqual(resolved, Path("/tmp/torfast-explicit").resolve())

    def test_resolve_runtime_state_root_generates_fresh_launch_path(self) -> None:
        with (
            patch("torfast.cli.time.strftime", return_value="20260624T130001"),
            patch("torfast.cli.time.time_ns", return_value=2345678901),
            patch("torfast.cli.os.getpid", return_value=777),
        ):
            resolved = resolve_runtime_state_root(
                command="launch",
                state_root=AUTO_STATE_ROOT,
            )

        self.assertEqual(
            resolved,
            (
                DEFAULT_FRESH_STATE_ROOT_PARENT
                / "launch-20260624T130001-777-345678901"
            ).resolve(),
        )

    def test_collect_status_without_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            status = collect_status(Path(tmp))

        self.assertTrue(status["ok"])
        managed = status["managed_tor"]
        self.assertFalse(managed["configured"])
        self.assertFalse(managed["running"])
        self.assertIsNone(status["last_launch"])

    def test_collect_status_with_running_service(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = resolve_state_paths(root)
            paths.state_root.mkdir(parents=True, exist_ok=True)
            paths.tor_service_json.write_text(
                json.dumps({"pid": 1234, "port": 19460, "tor_bin": "/tmp/tor"}) + "\n"
            )
            paths.launch_json.write_text(json.dumps({"url": "about:tor"}) + "\n")

            with patch("torfast.cli.process_is_alive", return_value=True):
                status = collect_status(root)

        self.assertTrue(status["managed_tor"]["configured"])
        self.assertTrue(status["managed_tor"]["running"])
        self.assertFalse(status["managed_tor"]["stale"])
        self.assertEqual(status["managed_tor"]["pid"], 1234)
        self.assertEqual(status["last_launch"]["url"], "about:tor")

    def test_discover_browser_bin_accepts_explicit_existing_path(self) -> None:
        result = discover_browser_bin("/bin/echo")

        self.assertTrue(result["found"])
        self.assertEqual(result["source"], "explicit")
        self.assertEqual(result["path"], str(Path("/bin/echo").resolve()))

    def test_discover_tor_bin_accepts_explicit_existing_path(self) -> None:
        result = discover_tor_bin("/bin/echo")

        self.assertTrue(result["found"])
        self.assertEqual(result["source"], "explicit")
        self.assertEqual(result["path"], str(Path("/bin/echo").resolve()))

    def test_discover_tor_bin_prefers_bundled_tor_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            browser_bin = root / "Tor Browser.app" / "Contents" / "MacOS" / "firefox"
            bundled_tor = browser_bin.parent / "Tor" / "tor"
            browser_bin.parent.mkdir(parents=True, exist_ok=True)
            bundled_tor.parent.mkdir(parents=True, exist_ok=True)
            browser_bin.write_text("", encoding="utf-8")
            bundled_tor.write_text("", encoding="utf-8")

            with (
                patch("torfast.cli.candidate_browser_bins", return_value=[browser_bin]),
                patch("torfast.cli.shutil.which", return_value=None),
                patch("torfast.cli.DEFAULT_TOR_BIN", root / "missing-bundled-tor"),
                patch("torfast.cli.DEFAULT_LOCAL_TOR_BIN", root / "missing-local-tor"),
            ):
                result = discover_tor_bin(None)

        self.assertTrue(result["found"])
        self.assertEqual(result["source"], "auto")
        self.assertEqual(result["path"], str(bundled_tor.resolve()))

    def test_collect_doctor_reports_missing_browser(self) -> None:
        with patch(
            "torfast.cli.discover_browser_bin",
            return_value={
                "found": False,
                "path": None,
                "source": "auto",
                "candidates": ["/missing/browser"],
            },
        ), patch(
            "torfast.cli.discover_tor_bin",
            return_value={
                "found": True,
                "path": "/bin/echo",
                "source": "auto",
                "candidates": ["/bin/echo"],
            },
        ), patch(
            "torfast.cli.read_tor_version",
            return_value={"ok": True, "exit_code": 0, "output": "Tor version test"},
        ), patch(
            "torfast.cli.collect_status",
            return_value={"ok": True, "managed_tor": {}, "last_launch": None},
        ):
            report = collect_doctor(Path("/tmp/torfast-doctor"))

        self.assertFalse(report["ok"])
        self.assertIsNone(report["browser"]["default_pref_proof"])
        self.assertIsNone(report["browser"]["default_pref_check"])
        self.assertTrue(report["tor"]["version"]["ok"])

    def test_collect_doctor_is_ok_when_checks_pass(self) -> None:
        with patch(
            "torfast.cli.discover_browser_bin",
            return_value={
                "found": True,
                "path": "/tmp/browser/firefox",
                "source": "auto",
                "candidates": ["/tmp/browser/firefox"],
            },
        ), patch(
            "torfast.cli.discover_tor_bin",
            return_value={
                "found": True,
                "path": "/tmp/tor",
                "source": "auto",
                "candidates": ["/tmp/tor"],
            },
        ), patch(
            "torfast.cli.read_browser_default_prefs",
            return_value={"ok": True, "prefs": {}},
        ), patch(
            "torfast.cli.validate_default_prefs",
            return_value={"ok": True, "failures": []},
        ), patch(
            "torfast.cli.read_tor_version",
            return_value={"ok": True, "exit_code": 0, "output": "Tor version test"},
        ), patch(
            "torfast.cli.collect_status",
            return_value={"ok": True, "managed_tor": {}, "last_launch": None},
        ):
            report = collect_doctor(Path("/tmp/torfast-doctor"))

        self.assertTrue(report["ok"])
        self.assertTrue(report["browser"]["default_pref_check"]["ok"])
        self.assertTrue(report["tor"]["version"]["ok"])
        self.assertIn("browser_startup_seed", report)

    def test_doctor_parser_accepts_explicit_binaries(self) -> None:
        args = build_parser().parse_args(
            [
                "doctor",
                "--state-root",
                "/tmp/torfast-doctor",
                "--browser-bin",
                "/tmp/browser/firefox",
                "--tor-bin",
                "/tmp/tor",
                "--dir-cache-seed-root",
                "/tmp/torfast-seed",
                "--browser-startup-seed-root",
                "/tmp/torfast-browser-startup-seed",
            ]
        )

        self.assertEqual(args.command, "doctor")
        self.assertEqual(args.state_root, "/tmp/torfast-doctor")
        self.assertEqual(args.browser_bin, "/tmp/browser/firefox")
        self.assertEqual(args.tor_bin, "/tmp/tor")
        self.assertEqual(args.dir_cache_seed_root, "/tmp/torfast-seed")
        self.assertEqual(
            args.browser_startup_seed_root,
            "/tmp/torfast-browser-startup-seed",
        )

    def test_install_browser_parser_accepts_paths(self) -> None:
        args = build_parser().parse_args(
            [
                "install-browser",
                "--install-root",
                "/tmp/browser",
                "--download-root",
                "/tmp/browser-downloads",
                "--prime-state-root",
                "/tmp/torfast-prime",
                "--prime-port",
                "19502",
                "--prime-dir-cache-seed-root",
                "/tmp/torfast-seed",
                "--prime-browser-startup-seed-after-install",
                "--prime-browser-startup-timeout",
                "9",
                "--force",
                "--dry-run",
            ]
        )

        self.assertEqual(args.command, "install-browser")
        self.assertEqual(args.version, "latest")
        self.assertEqual(args.install_root, "/tmp/browser")
        self.assertEqual(args.download_root, "/tmp/browser-downloads")
        self.assertTrue(args.prime_after_install)
        self.assertEqual(args.prime_state_root, "/tmp/torfast-prime")
        self.assertEqual(args.prime_port, 19502)
        self.assertEqual(args.prime_dir_cache_seed_root, "/tmp/torfast-seed")
        self.assertTrue(args.prime_browser_startup_seed_after_install)
        self.assertEqual(args.prime_browser_startup_timeout, 9.0)
        self.assertTrue(args.force)
        self.assertTrue(args.dry_run)

    def test_install_browser_parser_allows_explicit_prime_opt_out(self) -> None:
        args = build_parser().parse_args(
            [
                "install-browser",
                "--no-prime-after-install",
                "--no-prime-browser-startup-seed-after-install",
            ]
        )

        self.assertEqual(args.command, "install-browser")
        self.assertFalse(args.prime_after_install)
        self.assertFalse(args.prime_browser_startup_seed_after_install)

    def test_install_browser_main_can_run_optional_browser_startup_prime(self) -> None:
        with (
            patch(
                "torfast.cli.install_browser",
                return_value={
                    "ok": True,
                    "plan": {"browser_bin": "/tmp/browser/firefox"},
                },
            ),
            patch(
                "torfast.cli.run_followup_command",
                side_effect=[
                    {"ok": True, "command": ["prime"], "exit_code": 0, "stdout_tail": [], "stderr_tail": []},
                    {"ok": True, "command": ["launch"], "exit_code": 0, "stdout_tail": [], "stderr_tail": []},
                ],
            ) as run_followup,
            patch("sys.stdout", new_callable=io.StringIO),
        ):
            exit_code = main(
                [
                    "install-browser",
                    "--prime-browser-startup-seed-after-install",
                ]
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(run_followup.call_count, 2)
        prime_command = run_followup.call_args_list[0].args[0]
        launch_command = run_followup.call_args_list[1].args[0]
        self.assertIn("prime", prime_command)
        self.assertIn("launch", launch_command)
        self.assertIn("--headless", launch_command)
        self.assertIn("--browser-timeout", launch_command)
        self.assertIn("8.0", launch_command)

    def test_main_runs_runtime_actions_in_process(self) -> None:
        launcher_main = Mock(return_value=7)

        with (
            patch("torfast.cli.load_launcher_main", return_value=launcher_main),
            patch("torfast.cli.subprocess.run") as subprocess_run,
        ):
            exit_code = main(["stop", "--state-root", "/tmp/torfast-stop"])

        self.assertEqual(exit_code, 7)
        launcher_main.assert_called_once_with(
            [
                "--state-root",
                str(Path("/tmp/torfast-stop").resolve()),
                "--stop-managed-tor",
            ]
        )
        subprocess_run.assert_not_called()

    def test_warm_parser_accepts_runtime_args(self) -> None:
        args = build_parser().parse_args(
            [
                "warm",
                "--browser-bin",
                "/tmp/browser/firefox",
                "--tor-bin",
                "/tmp/tor",
                "--state-root",
                "/tmp/torfast-warm",
                "--port",
                "19500",
                "--browser-startup-seed-root",
                "/tmp/torfast-browser-startup-seed",
                "--no-browser-startup-seed",
            ]
        )

        self.assertEqual(args.command, "warm")
        self.assertEqual(args.browser_bin, "/tmp/browser/firefox")
        self.assertEqual(args.tor_bin, "/tmp/tor")
        self.assertEqual(args.state_root, "/tmp/torfast-warm")
        self.assertEqual(args.port, 19500)
        self.assertEqual(
            args.browser_startup_seed_root,
            "/tmp/torfast-browser-startup-seed",
        )
        self.assertTrue(args.no_browser_startup_seed)

    def test_launch_parser_defaults_to_auto_state_root(self) -> None:
        args = build_parser().parse_args(["launch"])

        self.assertEqual(args.state_root, AUTO_STATE_ROOT)
        self.assertTrue(args.no_browser_startup_seed)

    def test_plan_parser_defaults_to_auto_state_root(self) -> None:
        args = build_parser().parse_args(["plan"])

        self.assertEqual(args.state_root, AUTO_STATE_ROOT)
        self.assertTrue(args.no_browser_startup_seed)

    def test_launch_parser_accepts_browser_startup_seed_opt_in(self) -> None:
        args = build_parser().parse_args(["launch", "--browser-startup-seed"])

        self.assertFalse(args.no_browser_startup_seed)

    def test_prime_parser_accepts_runtime_args(self) -> None:
        args = build_parser().parse_args(
            [
                "prime",
                "--browser-bin",
                "/tmp/browser/firefox",
                "--tor-bin",
                "/tmp/tor",
                "--state-root",
                "/tmp/torfast-prime",
                "--port",
                "19501",
                "--browser-startup-seed-root",
                "/tmp/torfast-browser-startup-seed",
            ]
        )

        self.assertEqual(args.command, "prime")
        self.assertEqual(args.browser_bin, "/tmp/browser/firefox")
        self.assertEqual(args.tor_bin, "/tmp/tor")
        self.assertEqual(args.state_root, "/tmp/torfast-prime")
        self.assertEqual(args.port, 19501)
        self.assertEqual(
            args.browser_startup_seed_root,
            "/tmp/torfast-browser-startup-seed",
        )
