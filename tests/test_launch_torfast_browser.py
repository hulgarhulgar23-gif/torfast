import json
import queue
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from launch_torfast_browser import (
    DEFAULT_BROWSER_LAUNCH_GATE,
    LaunchError,
    browser_runtime_reset_requested,
    combine_tor_wait_results,
    browser_launch_gate_ready_text,
    browser_launch_command,
    browser_launch_env,
    ensure_state_dirs,
    finalize_browser_runtime_reset_cleanup,
    launch_browser_with_c_tor,
    read_browser_default_prefs,
    render_c_tor_torrc,
    reset_browser_runtime_dirs,
    resolve_browser_launch_gate,
    resolve_managed_browser_launch_gate,
    resolve_launch_paths,
    start_c_tor_detached,
    stop_managed_tor_service,
    wait_for_browser_exit,
)


class LaunchTorfastBrowserTests(unittest.TestCase):
    def test_read_browser_default_prefs_uses_matching_cache_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            browser_bin = (
                root
                / "Tor Browser.app"
                / "Contents"
                / "MacOS"
                / "firefox"
            )
            omni = (
                root
                / "Tor Browser.app"
                / "Contents"
                / "Resources"
                / "browser"
                / "omni.ja"
            )
            cache_dir = root / "browser-default-prefs-cache"
            browser_bin.parent.mkdir(parents=True, exist_ok=True)
            omni.parent.mkdir(parents=True, exist_ok=True)
            browser_bin.write_text("", encoding="utf-8")
            omni.write_text("stub", encoding="utf-8")
            source_stat = omni.stat()
            cache_path = cache_dir / "cached.json"
            cache_dir.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(
                json.dumps(
                    {
                        "source": str(omni),
                        "source_mtime_ns": source_stat.st_mtime_ns,
                        "source_size": source_stat.st_size,
                        "prefs": {
                            "browser.privatebrowsing.autostart": True,
                            "extensions.torbutton.use_nontor_proxy": False,
                            "network.dns.disabled": True,
                            "network.http.http3.enable": False,
                            "network.proxy.allow_bypass": False,
                            "network.proxy.failover_direct": False,
                            "network.proxy.no_proxies_on": "",
                            "network.proxy.socks_remote_dns": True,
                            "privacy.firstparty.isolate": True,
                            "privacy.resistFingerprinting": True,
                            "privacy.resistFingerprinting.letterboxing": True,
                        },
                    }
                ),
                encoding="utf-8",
            )

            with patch(
                "launch_torfast_browser.DEFAULT_PREF_CACHE_DIR",
                cache_dir,
            ):
                result = read_browser_default_prefs(browser_bin)

        self.assertTrue(result["ok"])
        self.assertTrue(result["cache_hit"])
        self.assertEqual(result["source"], str(omni))
        self.assertEqual(result["cache_path"], str(cache_path))

    def test_start_c_tor_detached_truncates_previous_log(self) -> None:
        class FakeProc:
            pass

        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            torrc = root / "torrc"
            torrc.write_text("", encoding="utf-8")
            log_path = root / "tor.log"
            log_path.write_text("old line\n", encoding="utf-8")

            with patch(
                "subprocess.Popen",
                return_value=FakeProc(),
            ):
                start_c_tor_detached(
                    tor_bin=Path("/tmp/tor"),
                    torrc=torrc,
                    log_path=log_path,
                )

            self.assertEqual(log_path.read_text(encoding="utf-8"), "")

    def test_cold_managed_open_uses_launch_gate_before_full_boot(self) -> None:
        class FakeProc:
            def __init__(self, pid: int) -> None:
                self.pid = pid
                self.returncode = None

            def poll(self) -> None:
                return None

        with tempfile.TemporaryDirectory() as tempdir:
            paths = resolve_launch_paths(Path(tempdir) / "state-root")
            ensure_state_dirs(paths)
            paths.torrc.write_text(
                "SocksPort 127.0.0.1:19450 IsolateSOCKSAuth\n",
                encoding="utf-8",
            )
            plan = {
                "browser_command": ["/tmp/firefox", "https://check.torproject.org/"],
                "browser_launch_gate": "tor_boot_95",
                "browser_startup_seed_apply": {
                    "ok": True,
                    "applied": False,
                    "reason": "disabled by flag",
                },
                "browser_startup_seed_root": str(Path(tempdir) / "browser-seed"),
                "browser_timeout_seconds": 0.0,
                "control_cookie_path": str(paths.control_cookie_path),
                "control_port": 29450,
                "conflux_client_ux": None,
                "dir_cache_seed_apply": {
                    "ok": True,
                    "applied": False,
                    "reason": "disabled by flag",
                },
                "dir_cache_seed_root": str(Path(tempdir) / "dir-seed"),
                "leave_tor_running": True,
                "paths": paths.as_dict(),
                "port": 19450,
                "reused_tor_service": None,
                "start_managed_tor_only": False,
                "stream_isolation_probe_enabled": False,
                "tor_bin": "/tmp/tor",
                "url": "https://check.torproject.org/",
            }
            events: list[str] = []
            wait_results = [
                {
                    "ok": True,
                    "seconds": 0.5,
                    "lines": ["Opened Socks listener connection (ready)"],
                    "signal_lines": [],
                },
                {
                    "ok": True,
                    "seconds": 1.0,
                    "lines": ["Bootstrapped 100% (done): Done"],
                    "signal_lines": ["Bootstrapped 100% (done): Done"],
                },
            ]

            def fake_wait_for_ready_in_log(*, ready_text: str, **_kwargs) -> dict[str, object]:
                events.append(f"wait:{ready_text}")
                return wait_results.pop(0)

            with (
                patch(
                    "launch_torfast_browser.start_c_tor_detached",
                    return_value=FakeProc(4321),
                ),
                patch(
                    "launch_torfast_browser.wait_for_ready_in_log",
                    side_effect=fake_wait_for_ready_in_log,
                ),
                patch(
                    "launch_torfast_browser.start_browser_launcher",
                    side_effect=lambda **_kwargs: (
                        events.append("browser_start") or FakeProc(5432),
                        queue.Queue(),
                    ),
                ),
                patch(
                    "launch_torfast_browser.wait_for_browser_exit",
                    return_value={
                        "ok": True,
                        "exit_code": 0,
                        "timed_out": False,
                        "interrupted": False,
                    },
                ),
                patch("launch_torfast_browser.stop_process_tree"),
                patch("launch_torfast_browser.stop_process"),
                patch("launch_torfast_browser.describe_seed", return_value={}),
                patch(
                    "launch_torfast_browser.describe_browser_startup_seed",
                    return_value={},
                ),
                patch("builtins.print"),
            ):
                exit_code = launch_browser_with_c_tor(plan)

            self.assertEqual(exit_code, 0)
            self.assertEqual(
                events,
                [
                    f"wait:{browser_launch_gate_ready_text('tor_boot_95')}",
                    "browser_start",
                    f"wait:{browser_launch_gate_ready_text('tor_boot_100')}",
                ],
            )
            self.assertEqual(plan["tor_browser_launch_gate"]["gate"], "tor_boot_95")
            self.assertTrue(plan["tor_boot"]["ok"])
            self.assertEqual(plan["reused_tor_service"]["pid"], 4321)
            service = json.loads(paths.tor_service_json.read_text())
            self.assertEqual(service["pid"], 4321)

    def test_warm_returns_after_managed_ready_gate(self) -> None:
        class FakeProc:
            def __init__(self, pid: int) -> None:
                self.pid = pid
                self.returncode = None

            def poll(self) -> None:
                return None

        with tempfile.TemporaryDirectory() as tempdir:
            paths = resolve_launch_paths(Path(tempdir) / "state-root")
            ensure_state_dirs(paths)
            paths.torrc.write_text(
                "SocksPort 127.0.0.1:19450 IsolateSOCKSAuth\n",
                encoding="utf-8",
            )
            plan = {
                "browser_command": ["/tmp/firefox", "about:tor"],
                "browser_launch_gate": "socks_ready",
                "browser_startup_seed_apply": {
                    "ok": True,
                    "applied": False,
                    "reason": "disabled by flag",
                },
                "browser_startup_seed_root": str(Path(tempdir) / "browser-seed"),
                "browser_timeout_seconds": 0.0,
                "control_cookie_path": str(paths.control_cookie_path),
                "control_port": 29450,
                "conflux_client_ux": None,
                "dir_cache_seed_apply": {
                    "ok": True,
                    "applied": False,
                    "reason": "disabled by flag",
                },
                "dir_cache_seed_root": str(Path(tempdir) / "dir-seed"),
                "leave_tor_running": True,
                "paths": paths.as_dict(),
                "port": 19450,
                "reused_tor_service": None,
                "start_managed_tor_only": True,
                "stream_isolation_probe_enabled": False,
                "tor_bin": "/tmp/tor",
                "url": "about:tor",
            }

            with (
                patch(
                    "launch_torfast_browser.start_c_tor_detached",
                    return_value=FakeProc(9876),
                ),
                patch(
                    "launch_torfast_browser.wait_for_ready_in_log",
                    return_value={
                        "ok": True,
                        "seconds": 0.25,
                        "ready_epoch_ms": 1000.0,
                        "ready_monotonic_seconds": 50.0,
                        "lines": ["Opened Socks listener connection (ready)"],
                        "signal_lines": [],
                    },
                ),
                patch("launch_torfast_browser.stop_process"),
                patch("launch_torfast_browser.describe_seed", return_value={}),
                patch(
                    "launch_torfast_browser.describe_browser_startup_seed",
                    return_value={},
                ),
                patch("builtins.print"),
            ):
                exit_code = launch_browser_with_c_tor(plan)

            self.assertEqual(exit_code, 0)
            self.assertIsNone(plan.get("tor_boot"))
            self.assertEqual(plan["tor_managed_ready"]["gate"], "socks_ready")
            self.assertTrue(plan["browser"]["skipped"])
            self.assertEqual(
                plan["reused_tor_service"]["ready_gate"],
                "socks_ready",
            )
            service = json.loads(paths.tor_service_json.read_text())
            self.assertEqual(service["pid"], 9876)
            self.assertEqual(service["ready_gate"], "socks_ready")

    def test_reused_managed_open_waits_for_gate_then_full_boot(self) -> None:
        class FakeProc:
            def __init__(self, pid: int) -> None:
                self.pid = pid
                self.returncode = None

            def poll(self) -> None:
                return None

        with tempfile.TemporaryDirectory() as tempdir:
            paths = resolve_launch_paths(Path(tempdir) / "state-root")
            ensure_state_dirs(paths)
            paths.torrc.write_text(
                "SocksPort 127.0.0.1:19450 IsolateSOCKSAuth\n",
                encoding="utf-8",
            )
            service = {
                "pid": 2468,
                "port": 19450,
                "torrc": str(paths.torrc),
                "tor_log": str(paths.tor_log),
                "started_epoch_ms": 100.0,
                "ready_gate": "socks_ready",
            }
            paths.tor_service_json.write_text(
                json.dumps(service),
                encoding="utf-8",
            )
            plan = {
                "browser_command": ["/tmp/firefox", "https://check.torproject.org/"],
                "browser_launch_gate": "tor_boot_95",
                "browser_startup_seed_apply": {
                    "ok": True,
                    "applied": False,
                    "reason": "disabled by flag",
                },
                "browser_startup_seed_root": str(Path(tempdir) / "browser-seed"),
                "browser_timeout_seconds": 0.0,
                "control_cookie_path": str(paths.control_cookie_path),
                "control_port": 29450,
                "conflux_client_ux": None,
                "dir_cache_seed_apply": {
                    "ok": True,
                    "applied": False,
                    "reason": "disabled by flag",
                },
                "dir_cache_seed_root": str(Path(tempdir) / "dir-seed"),
                "leave_tor_running": True,
                "paths": paths.as_dict(),
                "port": 19450,
                "reused_tor_service": service,
                "start_managed_tor_only": False,
                "stream_isolation_probe_enabled": False,
                "tor_bin": "/tmp/tor",
                "url": "https://check.torproject.org/",
            }
            events: list[str] = []
            wait_results = [
                {
                    "ok": True,
                    "seconds": 0.4,
                    "ready_epoch_ms": 1000.0,
                    "ready_monotonic_seconds": 50.0,
                    "lines": ["Bootstrapped 95% (circuit_create): Establishing a Tor circuit"],
                    "signal_lines": [],
                },
                {
                    "ok": True,
                    "seconds": 0.6,
                    "ready_epoch_ms": 1200.0,
                    "ready_monotonic_seconds": 51.0,
                    "lines": ["Bootstrapped 100% (done): Done"],
                    "signal_lines": ["Bootstrapped 100% (done): Done"],
                },
            ]

            def fake_wait_for_existing_service_ready_in_log(*, ready_text: str, **_kwargs) -> dict[str, object]:
                events.append(f"wait:{ready_text}")
                return wait_results.pop(0)

            with (
                patch(
                    "launch_torfast_browser.wait_for_existing_service_ready_in_log",
                    side_effect=fake_wait_for_existing_service_ready_in_log,
                ),
                patch(
                    "launch_torfast_browser.start_browser_launcher",
                    side_effect=lambda **_kwargs: (
                        events.append("browser_start") or FakeProc(1357),
                        queue.Queue(),
                    ),
                ),
                patch(
                    "launch_torfast_browser.wait_for_browser_exit",
                    return_value={
                        "ok": True,
                        "exit_code": 0,
                        "timed_out": False,
                        "interrupted": False,
                    },
                ),
                patch("launch_torfast_browser.stop_process_tree"),
                patch("launch_torfast_browser.describe_seed", return_value={}),
                patch(
                    "launch_torfast_browser.describe_browser_startup_seed",
                    return_value={},
                ),
                patch("builtins.print"),
            ):
                exit_code = launch_browser_with_c_tor(plan)

            self.assertEqual(exit_code, 0)
            self.assertEqual(
                events,
                [
                    f"wait:{browser_launch_gate_ready_text('tor_boot_95')}",
                    "browser_start",
                    f"wait:{browser_launch_gate_ready_text('tor_boot_100')}",
                ],
            )
            self.assertEqual(plan["tor_browser_launch_gate"]["gate"], "tor_boot_95")
            self.assertTrue(plan["tor_boot"]["ok"])
            self.assertEqual(
                plan["reused_tor_service"]["ready_gate"],
                "tor_boot_100",
            )
            service_after = json.loads(paths.tor_service_json.read_text())
            self.assertEqual(service_after["ready_gate"], "tor_boot_100")

    def test_reused_managed_open_skips_redundant_waits_after_full_boot(self) -> None:
        class FakeProc:
            def __init__(self, pid: int) -> None:
                self.pid = pid
                self.returncode = None

            def poll(self) -> None:
                return None

        with tempfile.TemporaryDirectory() as tempdir:
            paths = resolve_launch_paths(Path(tempdir) / "state-root")
            ensure_state_dirs(paths)
            paths.torrc.write_text(
                "SocksPort 127.0.0.1:19450 IsolateSOCKSAuth\n",
                encoding="utf-8",
            )
            service = {
                "pid": 2468,
                "port": 19450,
                "torrc": str(paths.torrc),
                "tor_log": str(paths.tor_log),
                "started_epoch_ms": 100.0,
                "ready_epoch_ms": 1200.0,
                "ready_monotonic_seconds": 51.0,
                "ready_gate": "tor_boot_100",
            }
            paths.tor_service_json.write_text(
                json.dumps(service),
                encoding="utf-8",
            )
            plan = {
                "browser_command": ["/tmp/firefox", "https://check.torproject.org/"],
                "browser_launch_gate": "tor_boot_95",
                "browser_startup_seed_apply": {
                    "ok": True,
                    "applied": False,
                    "reason": "disabled by flag",
                },
                "browser_startup_seed_root": str(Path(tempdir) / "browser-seed"),
                "browser_timeout_seconds": 0.0,
                "control_cookie_path": str(paths.control_cookie_path),
                "control_port": 29450,
                "conflux_client_ux": None,
                "dir_cache_seed_apply": {
                    "ok": True,
                    "applied": False,
                    "reason": "disabled by flag",
                },
                "dir_cache_seed_root": str(Path(tempdir) / "dir-seed"),
                "leave_tor_running": True,
                "paths": paths.as_dict(),
                "port": 19450,
                "reused_tor_service": service,
                "start_managed_tor_only": False,
                "stream_isolation_probe_enabled": False,
                "tor_bin": "/tmp/tor",
                "url": "https://check.torproject.org/",
            }

            with (
                patch(
                    "launch_torfast_browser.wait_for_existing_service_ready_in_log"
                ) as wait_for_existing,
                patch(
                    "launch_torfast_browser.start_browser_launcher",
                    return_value=(FakeProc(1357), queue.Queue()),
                ),
                patch(
                    "launch_torfast_browser.wait_for_browser_exit",
                    return_value={
                        "ok": True,
                        "exit_code": 0,
                        "timed_out": False,
                        "interrupted": False,
                    },
                ),
                patch("launch_torfast_browser.stop_process_tree"),
                patch("launch_torfast_browser.describe_seed", return_value={}),
                patch(
                    "launch_torfast_browser.describe_browser_startup_seed",
                    return_value={},
                ),
                patch("builtins.print"),
            ):
                exit_code = launch_browser_with_c_tor(plan)

            self.assertEqual(exit_code, 0)
            wait_for_existing.assert_not_called()
            self.assertEqual(plan["tor_browser_launch_gate"]["gate"], "tor_boot_95")
            self.assertEqual(plan["tor_browser_launch_gate"]["seconds"], 0.0)
            self.assertTrue(plan["tor_browser_launch_gate"]["reused_service"])
            self.assertTrue(plan["tor_boot"]["ok"])
            self.assertEqual(plan["tor_boot"]["seconds"], 0.0)
            self.assertTrue(plan["tor_boot"]["reused_service"])
            self.assertEqual(plan["reused_tor_service"]["ready_gate"], "tor_boot_100")
            service_after = json.loads(paths.tor_service_json.read_text())
            self.assertEqual(service_after["ready_gate"], "tor_boot_100")

    def test_reused_managed_full_boot_gate_skips_wait_after_full_boot(self) -> None:
        class FakeProc:
            def __init__(self, pid: int) -> None:
                self.pid = pid
                self.returncode = None

            def poll(self) -> None:
                return None

        with tempfile.TemporaryDirectory() as tempdir:
            paths = resolve_launch_paths(Path(tempdir) / "state-root")
            ensure_state_dirs(paths)
            paths.torrc.write_text(
                "SocksPort 127.0.0.1:19450 IsolateSOCKSAuth\n",
                encoding="utf-8",
            )
            service = {
                "pid": 2468,
                "port": 19450,
                "torrc": str(paths.torrc),
                "tor_log": str(paths.tor_log),
                "started_epoch_ms": 100.0,
                "ready_epoch_ms": 1200.0,
                "ready_monotonic_seconds": 51.0,
                "ready_gate": "tor_boot_100",
            }
            paths.tor_service_json.write_text(
                json.dumps(service),
                encoding="utf-8",
            )
            plan = {
                "browser_command": ["/tmp/firefox", "https://check.torproject.org/"],
                "browser_launch_gate": "tor_boot_100",
                "browser_startup_seed_apply": {
                    "ok": True,
                    "applied": False,
                    "reason": "disabled by flag",
                },
                "browser_startup_seed_root": str(Path(tempdir) / "browser-seed"),
                "browser_timeout_seconds": 0.0,
                "control_cookie_path": str(paths.control_cookie_path),
                "control_port": 29450,
                "conflux_client_ux": None,
                "dir_cache_seed_apply": {
                    "ok": True,
                    "applied": False,
                    "reason": "disabled by flag",
                },
                "dir_cache_seed_root": str(Path(tempdir) / "dir-seed"),
                "leave_tor_running": True,
                "paths": paths.as_dict(),
                "port": 19450,
                "reused_tor_service": service,
                "start_managed_tor_only": False,
                "stream_isolation_probe_enabled": False,
                "tor_bin": "/tmp/tor",
                "url": "https://check.torproject.org/",
            }

            with (
                patch(
                    "launch_torfast_browser.wait_for_existing_service_ready_in_log"
                ) as wait_for_existing,
                patch(
                    "launch_torfast_browser.start_browser_launcher",
                    return_value=(FakeProc(1357), queue.Queue()),
                ),
                patch(
                    "launch_torfast_browser.wait_for_browser_exit",
                    return_value={
                        "ok": True,
                        "exit_code": 0,
                        "timed_out": False,
                        "interrupted": False,
                    },
                ),
                patch("launch_torfast_browser.stop_process_tree"),
                patch("launch_torfast_browser.describe_seed", return_value={}),
                patch(
                    "launch_torfast_browser.describe_browser_startup_seed",
                    return_value={},
                ),
                patch("builtins.print"),
            ):
                exit_code = launch_browser_with_c_tor(plan)

            self.assertEqual(exit_code, 0)
            wait_for_existing.assert_not_called()
            self.assertTrue(plan["tor_boot"]["ok"])
            self.assertEqual(plan["tor_boot"]["seconds"], 0.0)
            self.assertTrue(plan["tor_boot"]["reused_service"])
            self.assertEqual(plan["reused_tor_service"]["ready_gate"], "tor_boot_100")
            service_after = json.loads(paths.tor_service_json.read_text())
            self.assertEqual(service_after["ready_gate"], "tor_boot_100")

    def test_resolve_launch_paths_uses_expected_layout(self) -> None:
        root = Path("/tmp/torfast-browser-test")

        paths = resolve_launch_paths(root)

        self.assertEqual(paths.state_root, root)
        self.assertEqual(paths.data_dir, root / "tor-data")
        self.assertEqual(paths.torrc, root / "torrc")
        self.assertEqual(paths.tor_log, root / "tor.log")
        self.assertEqual(paths.tor_service_json, root / "tor-service.json")
        self.assertEqual(paths.browser_home_dir, root / "browser-home")
        self.assertEqual(paths.browser_profile_dir, root / "browser-profile")
        self.assertEqual(paths.launch_json, root / "launch.json")

    def test_render_c_tor_torrc_keeps_quality_defaults(self) -> None:
        torrc = render_c_tor_torrc(
            port=19080,
            data_dir=Path("/tmp/tor-data"),
        )

        self.assertIn("SocksPort 127.0.0.1:19080 IsolateSOCKSAuth", torrc)
        self.assertIn("ClientOnly 1", torrc)
        self.assertIn("AvoidDiskWrites 1", torrc)
        self.assertIn("SafeLogging 1", torrc)
        self.assertIn("ConfluxEnabled auto", torrc)
        self.assertNotIn("ConfluxClientUX", torrc)

    def test_render_c_tor_torrc_adds_optional_ux_override(self) -> None:
        torrc = render_c_tor_torrc(
            port=19080,
            data_dir=Path("/tmp/tor-data"),
            conflux_client_ux="throughput",
        )

        self.assertIn("ConfluxClientUX throughput", torrc)

    def test_render_c_tor_torrc_adds_optional_control_port(self) -> None:
        torrc = render_c_tor_torrc(
            port=19080,
            data_dir=Path("/tmp/tor-data"),
            control_port=29080,
            control_cookie_path=Path("/tmp/control_auth_cookie"),
        )

        self.assertIn("ControlPort 127.0.0.1:29080", torrc)
        self.assertIn("CookieAuthentication 1", torrc)
        self.assertIn(
            f"CookieAuthFile {Path('/tmp/control_auth_cookie').resolve()}",
            torrc,
        )

    def test_browser_launch_env_points_browser_at_external_tor(self) -> None:
        env = browser_launch_env(
            {"PATH": "/usr/bin"},
            home_dir=Path("/tmp/browser-home"),
            port=19450,
        )

        self.assertEqual(env["PATH"], "/usr/bin")
        self.assertEqual(env["HOME"], str(Path("/tmp/browser-home").resolve()))
        self.assertEqual(env["TOR_PROVIDER"], "none")
        self.assertEqual(env["TOR_SKIP_LAUNCH"], "1")
        self.assertEqual(env["TOR_SOCKS_HOST"], "127.0.0.1")
        self.assertEqual(env["TOR_SOCKS_PORT"], "19450")
        self.assertEqual(env["TZ"], "UTC")

    def test_browser_launch_command_uses_profile_and_url(self) -> None:
        command = browser_launch_command(
            browser_bin=Path("/Applications/Tor Browser.app/Contents/MacOS/firefox"),
            profile_dir=Path("/tmp/browser-profile"),
            url="about:tor",
            headless=False,
        )

        self.assertEqual(
            command[:4],
            [
                "/Applications/Tor Browser.app/Contents/MacOS/firefox",
                "--new-instance",
                "--no-remote",
                "-remote-allow-system-access",
            ],
        )
        self.assertIn("--profile", command)
        self.assertIn(str(Path("/tmp/browser-profile").resolve()), command)
        self.assertEqual(command[-1], "about:tor")
        self.assertNotIn("--headless", command)

    def test_browser_launch_command_adds_headless_when_requested(self) -> None:
        command = browser_launch_command(
            browser_bin=Path("/Applications/Tor Browser.app/Contents/MacOS/firefox"),
            profile_dir=Path("/tmp/browser-profile"),
            url="https://check.torproject.org/",
            headless=True,
        )

        self.assertIn("--headless", command)
        self.assertEqual(command[-1], "https://check.torproject.org/")

    def test_browser_launch_gate_ready_text_matches_expected_signal(self) -> None:
        self.assertEqual(
            browser_launch_gate_ready_text("socks_ready"),
            "Opened Socks listener connection (ready)",
        )
        self.assertEqual(
            browser_launch_gate_ready_text("tor_boot_90"),
            "Bootstrapped 90% (ap_handshake_done): Handshake finished with a relay to build circuits",
        )
        self.assertEqual(
            browser_launch_gate_ready_text("tor_boot_95"),
            "Bootstrapped 95% (circuit_create): Establishing a Tor circuit",
        )
        self.assertEqual(
            browser_launch_gate_ready_text("tor_boot_100"),
            "Bootstrapped 100%",
        )

    def test_browser_launch_gate_ready_text_rejects_unknown_gate(self) -> None:
        with self.assertRaises(LaunchError):
            browser_launch_gate_ready_text("bad_gate")

    def test_resolve_browser_launch_gate_defaults_about_pages_to_socks_ready(self) -> None:
        gate = resolve_browser_launch_gate(
            requested_gate=DEFAULT_BROWSER_LAUNCH_GATE,
            url="about:tor",
        )

        self.assertEqual(gate, "socks_ready")

    def test_resolve_browser_launch_gate_defaults_network_pages_to_full_boot(self) -> None:
        gate = resolve_browser_launch_gate(
            requested_gate=DEFAULT_BROWSER_LAUNCH_GATE,
            url="https://check.torproject.org/",
        )

        self.assertEqual(gate, "tor_boot_95")

    def test_resolve_browser_launch_gate_keeps_explicit_choice(self) -> None:
        gate = resolve_browser_launch_gate(
            requested_gate="socks_ready",
            url="https://check.torproject.org/",
        )

        self.assertEqual(gate, "socks_ready")

    def test_resolve_managed_browser_launch_gate_keeps_cold_network_auto_at_95(self) -> None:
        gate = resolve_managed_browser_launch_gate(
            requested_gate=DEFAULT_BROWSER_LAUNCH_GATE,
            url="https://check.torproject.org/",
            start_managed_tor_only=False,
            reused_tor_service=None,
        )

        self.assertEqual(gate, "tor_boot_95")

    def test_resolve_managed_browser_launch_gate_uses_socks_ready_for_network_warm(self) -> None:
        gate = resolve_managed_browser_launch_gate(
            requested_gate=DEFAULT_BROWSER_LAUNCH_GATE,
            url="https://check.torproject.org/",
            start_managed_tor_only=True,
            reused_tor_service=None,
        )

        self.assertEqual(gate, "socks_ready")

    def test_resolve_managed_browser_launch_gate_uses_socks_ready_for_reused_network_open(self) -> None:
        gate = resolve_managed_browser_launch_gate(
            requested_gate=DEFAULT_BROWSER_LAUNCH_GATE,
            url="https://check.torproject.org/",
            start_managed_tor_only=False,
            reused_tor_service={"pid": 1234},
        )

        self.assertEqual(gate, "socks_ready")

    def test_resolve_managed_browser_launch_gate_keeps_explicit_choice(self) -> None:
        gate = resolve_managed_browser_launch_gate(
            requested_gate="tor_boot_95",
            url="https://check.torproject.org/",
            start_managed_tor_only=True,
            reused_tor_service={"pid": 1234},
        )

        self.assertEqual(gate, "tor_boot_95")

    def test_combine_tor_wait_results_keeps_full_boot_timing(self) -> None:
        combined = combine_tor_wait_results(
            {
                "ok": True,
                "seconds": 0.25,
                "lines": [
                    "Bootstrapped 0% (starting): Starting",
                    "Opened Socks listener connection (ready)",
                ],
            },
            {
                "ok": True,
                "seconds": 1.75,
                "lines": [
                    "Bootstrapped 75% (enough_dirinfo): Loaded enough directory info to build circuits",
                    "Bootstrapped 100% (done): Done",
                ],
            },
        )

        self.assertEqual(combined["seconds"], 2.0)
        self.assertEqual(combined["lines"][-1], "Bootstrapped 100% (done): Done")
        self.assertIn(
            "Bootstrapped 100% (done): Done",
            combined["signal_lines"],
        )

    def test_browser_runtime_reset_requested_only_for_warm_browser_flows(self) -> None:
        self.assertFalse(
            browser_runtime_reset_requested(
                leave_tor_running=False,
                reuse_tor_if_running=False,
                start_managed_tor_only=False,
            )
        )
        self.assertFalse(
            browser_runtime_reset_requested(
                leave_tor_running=True,
                reuse_tor_if_running=False,
                start_managed_tor_only=True,
            )
        )
        self.assertTrue(
            browser_runtime_reset_requested(
                leave_tor_running=True,
                reuse_tor_if_running=False,
                start_managed_tor_only=False,
            )
        )
        self.assertTrue(
            browser_runtime_reset_requested(
                leave_tor_running=False,
                reuse_tor_if_running=True,
                start_managed_tor_only=False,
            )
        )

    def test_ensure_state_dirs_sets_private_permissions(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            paths = resolve_launch_paths(Path(tempdir) / "state-root")

            ensure_state_dirs(paths)

            for path in (
                paths.state_root,
                paths.data_dir,
                paths.browser_home_dir,
                paths.browser_profile_dir,
            ):
                self.assertTrue(path.is_dir())
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o700)

    def test_reset_browser_runtime_dirs_clears_existing_browser_state(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            paths = resolve_launch_paths(Path(tempdir) / "state-root")
            ensure_state_dirs(paths)
            (paths.browser_home_dir / "old-home.txt").write_text("home\n")
            (paths.browser_profile_dir / "prefs.js").write_text("user_pref();\n")
            nested = paths.browser_profile_dir / "storage"
            nested.mkdir()
            (nested / "ls-archive.sqlite").write_text("db\n")

            result, cleanup = reset_browser_runtime_dirs(paths, reset_requested=True)
            finalize_browser_runtime_reset_cleanup(cleanup)

            self.assertTrue(result["ok"])
            self.assertTrue(result["cleared"])
            self.assertEqual(result["cleanup_mode"], "async_rename")
            self.assertTrue(result["cleanup_complete"])
            self.assertEqual(list(paths.browser_home_dir.iterdir()), [])
            self.assertEqual(list(paths.browser_profile_dir.iterdir()), [])

    def test_reset_browser_runtime_dirs_can_force_sync_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            paths = resolve_launch_paths(Path(tempdir) / "state-root")
            ensure_state_dirs(paths)
            (paths.browser_profile_dir / "prefs.js").write_text("user_pref();\n")

            with patch.dict(
                "os.environ",
                {"TORFAST_DISABLE_ASYNC_BROWSER_RESET": "1"},
                clear=False,
            ):
                result, cleanup = reset_browser_runtime_dirs(
                    paths,
                    reset_requested=True,
                )

            self.assertIsNone(cleanup)
            self.assertTrue(result["ok"])
            self.assertEqual(result["cleanup_mode"], "sync")
            self.assertTrue(result["cleanup_complete"])
            self.assertEqual(list(paths.browser_profile_dir.iterdir()), [])

    def test_stop_managed_tor_service_is_idempotent_without_metadata(self) -> None:
        paths = resolve_launch_paths(Path("/tmp/torfast-browser-missing"))

        result = stop_managed_tor_service(paths)

        self.assertTrue(result["ok"])
        self.assertTrue(result["already_stopped"])
        self.assertFalse(result["stopped"])

    def test_wait_for_browser_exit_treats_timeout_as_intentional_stop(self) -> None:
        proc = subprocess.Popen(
            ["/bin/sh", "-c", "sleep 10"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        try:
            result = wait_for_browser_exit(
                proc=proc,
                lines=queue.Queue(),
                timeout_seconds=0.01,
            )
        finally:
            proc.kill()
            proc.wait()
            if proc.stdout is not None:
                proc.stdout.close()

        self.assertTrue(result["ok"])
        self.assertTrue(result["timed_out"])
        self.assertFalse(result["interrupted"])
        self.assertIn("launcher stopped browser as requested", result["note"])


if __name__ == "__main__":
    unittest.main()
