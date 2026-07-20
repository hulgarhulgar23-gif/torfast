import json
import os
import queue
import stat
import subprocess
import sys
import threading
import time
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from launch_torfast_browser import (
    BROWSER_RUNTIME_QUALITY_PROOF_ENABLED_ENV,
    DEFAULT_BROWSER_STARTUP_SEED_ROOT,
    DEFAULT_BROWSER_LAUNCH_GATE,
    LaunchError,
    MANAGED_SERVICE_METADATA_WAIT_DISABLED_ENV,
    browser_runtime_reset_requested,
    combine_tor_wait_results,
    build_launch_plan,
    browser_launch_gate_ready_text,
    browser_launch_command,
    browser_launch_env,
    collect_browser_runtime_quality_proof,
    ensure_marionette_session_on_target,
    ensure_state_dirs,
    finish_target_navigation_keeper,
    run_target_navigation_keeper,
    start_target_navigation_keeper,
    finalize_browser_runtime_reset_cleanup,
    launch_browser_with_c_tor,
    main,
    managed_open_browser_overlap_reason,
    managed_open_overlap_initial_url,
    maybe_collect_target_launch_browser_probe,
    maybe_wait_for_managed_open_general_circuit_during_browser_startup,
    maybe_wait_for_managed_open_general_circuit,
    maybe_start_runtime_helper_gate_promoter,
    read_browser_default_prefs,
    render_c_tor_torrc,
    reset_browser_runtime_dirs,
    resolve_browser_launch_gate,
    resolve_managed_browser_launch_gate,
    resolve_launch_paths,
    reusable_managed_tor_service,
    should_refresh_managed_service_metadata_wait,
    start_managed_open_browser_overlap_session,
    start_c_tor_detached,
    stop_managed_tor_service,
    wait_for_existing_service_ready_in_log,
    wait_for_browser_exit,
)


class LaunchTorfastBrowserTests(unittest.TestCase):
    def test_collect_browser_runtime_quality_proof_is_disabled_by_default(self) -> None:
        with patch.dict("os.environ", {}, clear=False):
            result = collect_browser_runtime_quality_proof(
                client=None,
                browser_profile_dir=None,
            )

        self.assertFalse(result["enabled"])
        self.assertFalse(result["applied"])
        self.assertEqual(result["reason"], "disabled")

    def test_collect_browser_runtime_quality_proof_collects_when_enabled(self) -> None:
        client = object()
        with (
            patch.dict(
                "os.environ",
                {BROWSER_RUNTIME_QUALITY_PROOF_ENABLED_ENV: "1"},
                clear=False,
            ),
            patch(
                "run_browser_compare.read_runtime_prefs",
                return_value={
                    "network.proxy.socks": "127.0.0.1",
                    "network.proxy.socks_port": 19450,
                    "network.proxy.socks_remote_dns": True,
                    "network.proxy.type": 1,
                },
            ),
            patch(
                "run_browser_compare.collect_browser_quality_prefs",
                return_value={"ok": True, "prefs": {"privacy.resistFingerprinting": {}}},
            ) as collect_prefs,
            patch(
                "run_browser_compare.collect_browser_fingerprint_snapshot",
                return_value={
                    "ok": True,
                    "snapshot": {
                        "timezoneOffset": 0,
                        "canvasProbe": {"extractionBlocked": True},
                    },
                },
            ) as collect_fingerprint,
        ):
            result = collect_browser_runtime_quality_proof(
                client=client,
                browser_profile_dir=Path("/tmp/browser-profile"),
            )

        self.assertTrue(result["enabled"])
        self.assertTrue(result["applied"])
        self.assertTrue(result["ok"])
        self.assertEqual(
            result["browser_quality_prefs"],
            {"ok": True, "prefs": {"privacy.resistFingerprinting": {}}},
        )
        self.assertEqual(
            result["browser_fingerprint_snapshot"],
            {
                "ok": True,
                "snapshot": {
                    "timezoneOffset": 0,
                    "canvasProbe": {"extractionBlocked": True},
                },
            },
        )
        self.assertEqual(
            result["effective_proxy_prefs"],
            {
                "network.proxy.socks": "127.0.0.1",
                "network.proxy.socks_port": 19450,
                "network.proxy.socks_remote_dns": True,
                "network.proxy.type": 1,
            },
        )
        collect_prefs.assert_called_once_with(client)
        # A satisfactory snapshot (canvas blocked, expected page) stops the
        # retry loop immediately.
        self.assertEqual(collect_fingerprint.call_count, 1)

    def test_collect_browser_runtime_quality_proof_retries_unsettled_snapshot(
        self,
    ) -> None:
        target = "https://check.torproject.org/"
        unsettled = {
            "ok": True,
            "snapshot": {
                "pageUrl": target,
                "canvasProbe": {"extractionBlocked": False},
            },
        }
        settled = {
            "ok": True,
            "snapshot": {
                "pageUrl": target,
                "canvasProbe": {"extractionBlocked": True},
            },
        }
        with (
            patch.dict(
                "os.environ",
                {BROWSER_RUNTIME_QUALITY_PROOF_ENABLED_ENV: "1"},
                clear=False,
            ),
            patch("run_browser_compare.read_runtime_prefs", return_value={}),
            patch(
                "run_browser_compare.collect_browser_quality_prefs",
                return_value={"ok": True, "prefs": {}},
            ),
            patch(
                "run_browser_compare.collect_browser_fingerprint_snapshot",
                side_effect=[unsettled, unsettled, settled],
            ) as collect_fingerprint,
            patch(
                "launch_torfast_browser.ensure_marionette_session_on_target",
                return_value={"on_target": True},
            ),
        ):
            result = collect_browser_runtime_quality_proof(
                client=object(),
                browser_profile_dir=None,
                target_url=target,
                fingerprint_retry_delay_seconds=0.0,
            )

        self.assertEqual(collect_fingerprint.call_count, 3)
        self.assertEqual(result["browser_fingerprint_snapshot"], settled)
        self.assertEqual(len(result["browser_fingerprint_attempts"]), 3)

    def test_collect_browser_runtime_quality_proof_pins_target_context(self) -> None:
        client = object()
        with (
            patch.dict(
                "os.environ",
                {BROWSER_RUNTIME_QUALITY_PROOF_ENABLED_ENV: "1"},
                clear=False,
            ),
            patch(
                "run_browser_compare.read_runtime_prefs",
                return_value={},
            ),
            patch(
                "run_browser_compare.collect_browser_quality_prefs",
                return_value={"ok": True, "prefs": {}},
            ),
            patch(
                "run_browser_compare.collect_browser_fingerprint_snapshot",
                return_value={"ok": True, "snapshot": {"timezoneOffset": 0}},
            ),
            patch(
                "launch_torfast_browser.ensure_marionette_session_on_target",
                return_value={
                    "on_target": True,
                    "final_url": "https://check.torproject.org/",
                    "corrections": 1,
                },
            ) as ensure_on_target,
        ):
            result = collect_browser_runtime_quality_proof(
                client=client,
                browser_profile_dir=None,
                target_url="https://check.torproject.org/",
                fingerprint_retry_delay_seconds=0.0,
            )

        ensure_on_target.assert_called_once_with(
            client,
            url="https://check.torproject.org/",
        )
        self.assertEqual(
            result["target_context"],
            {
                "on_target": True,
                "final_url": "https://check.torproject.org/",
                "corrections": 1,
            },
        )

    def test_run_target_navigation_keeper_corrects_startup_clobber(self) -> None:
        target = "https://check.torproject.org/"

        class FakeClient:
            def __init__(self) -> None:
                self.current_url = "about:tor"
                self.navigations: list[str] = []

            def command(self, name, params):
                if name == "WebDriver:GetCurrentURL":
                    return {"value": self.current_url}
                if name == "WebDriver:SetTimeouts":
                    return {"value": None}
                if name == "WebDriver:Navigate":
                    self.navigations.append(params["url"])
                    self.current_url = params["url"]
                    return {"value": None}
                raise AssertionError(f"unexpected command {name}")

        client = FakeClient()
        stop_event = threading.Event()

        report = run_target_navigation_keeper(
            client,
            url=target,
            stop_event=stop_event,
            max_seconds=0.3,
            poll_seconds=0.01,
        )

        self.assertEqual(report["corrections"], 1)
        self.assertEqual(client.navigations, [target])
        self.assertEqual(report["final_url"], target)
        self.assertGreaterEqual(report["checks"], 2)

    def test_run_target_navigation_keeper_rate_limits_corrections(self) -> None:
        target = "https://check.torproject.org/"

        class FakeClient:
            def __init__(self) -> None:
                self.navigations: list[str] = []

            def command(self, name, params):
                if name == "WebDriver:GetCurrentURL":
                    return {"value": "about:tor"}
                if name == "WebDriver:SetTimeouts":
                    return {"value": None}
                if name == "WebDriver:Navigate":
                    self.navigations.append(params["url"])
                    return {"value": None}
                raise AssertionError(f"unexpected command {name}")

        client = FakeClient()

        report = run_target_navigation_keeper(
            client,
            url=target,
            stop_event=threading.Event(),
            max_seconds=0.2,
            poll_seconds=0.01,
        )

        self.assertEqual(report["corrections"], 1)
        self.assertEqual(client.navigations, [target])
        self.assertGreaterEqual(report["checks"], 5)

    def test_run_target_navigation_keeper_tolerates_page_load_timeout(self) -> None:
        target = "https://check.torproject.org/"

        class FakeClient:
            def __init__(self) -> None:
                self.navigations: list[str] = []
                self.timeouts: list[object] = []

            def command(self, name, params):
                if name == "WebDriver:GetCurrentURL":
                    return {"value": "about:tor"}
                if name == "WebDriver:SetTimeouts":
                    self.timeouts.append(params["pageLoad"])
                    return {"value": None}
                if name == "WebDriver:Navigate":
                    self.navigations.append(params["url"])
                    raise RuntimeError(
                        {"error": "timeout", "message": "Timeout loading page"}
                    )
                raise AssertionError(f"unexpected command {name}")

        client = FakeClient()

        report = run_target_navigation_keeper(
            client,
            url=target,
            stop_event=threading.Event(),
            max_seconds=0.1,
            poll_seconds=0.01,
        )

        self.assertEqual(report["corrections"], 1)
        self.assertEqual(report["errors"], [])
        self.assertEqual(client.navigations, [target])
        self.assertEqual(client.timeouts, [250, 300_000])

    def test_run_target_navigation_keeper_leaves_non_startup_pages_alone(self) -> None:
        class FakeClient:
            def __init__(self) -> None:
                self.navigations: list[str] = []

            def command(self, name, params):
                if name == "WebDriver:GetCurrentURL":
                    return {"value": "https://example.org/other"}
                if name == "WebDriver:SetTimeouts":
                    return {"value": None}
                if name == "WebDriver:Navigate":
                    self.navigations.append(params["url"])
                    return {"value": None}
                raise AssertionError(f"unexpected command {name}")

        client = FakeClient()

        report = run_target_navigation_keeper(
            client,
            url="https://check.torproject.org/",
            stop_event=threading.Event(),
            max_seconds=0.05,
            poll_seconds=0.01,
        )

        self.assertEqual(report["corrections"], 0)
        self.assertEqual(client.navigations, [])
        self.assertEqual(report["final_url"], "https://example.org/other")

    def test_start_and_finish_target_navigation_keeper_round_trip(self) -> None:
        target = "https://check.torproject.org/"

        class FakeClient:
            def command(self, name, params):
                if name == "WebDriver:GetCurrentURL":
                    return {"value": target}
                raise AssertionError(f"unexpected command {name}")

        holder = start_target_navigation_keeper(FakeClient(), url=target)
        time.sleep(0.05)
        report = finish_target_navigation_keeper(holder)

        self.assertIsNotNone(report)
        self.assertFalse(report["pending"])
        self.assertEqual(report["target_url"], target)
        self.assertEqual(report["corrections"], 0)
        self.assertNotIn("_thread", report)
        self.assertNotIn("_stop_event", report)

    def test_finish_target_navigation_keeper_accepts_missing_holder(self) -> None:
        self.assertIsNone(finish_target_navigation_keeper(None))

    def test_ensure_marionette_session_on_target_renavigates(self) -> None:
        target = "https://check.torproject.org/"

        class FakeClient:
            def __init__(self) -> None:
                self.current_url = "about:tor"
                self.navigations: list[str] = []

            def command(self, name, params):
                if name == "WebDriver:GetCurrentURL":
                    return {"value": self.current_url}
                if name == "WebDriver:SetTimeouts":
                    return {"value": None}
                if name == "WebDriver:Navigate":
                    self.navigations.append(params["url"])
                    self.current_url = params["url"]
                    return {"value": None}
                raise AssertionError(f"unexpected command {name}")

        client = FakeClient()

        report = ensure_marionette_session_on_target(
            client,
            url=target,
            timeout_seconds=2.0,
            poll_seconds=0.01,
        )

        self.assertTrue(report["on_target"])
        self.assertEqual(report["corrections"], 1)
        self.assertEqual(report["final_url"], target)

    def test_main_skips_browser_only_work_for_managed_warm(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            browser_bin = (
                root
                / "Tor Browser.app"
                / "Contents"
                / "MacOS"
                / "firefox"
            )
            tor_bin = root / "tor"
            state_root = root / "state-root"
            browser_bin.parent.mkdir(parents=True, exist_ok=True)
            browser_bin.write_text("", encoding="utf-8")
            tor_bin.write_text("", encoding="utf-8")
            captured_plan: dict[str, object] = {}

            def fake_launch(
                plan: dict[str, object],
                *,
                browser_runtime_reset_cleanup=None,
            ) -> int:
                del browser_runtime_reset_cleanup
                captured_plan.update(plan)
                return 0

            with (
                patch("launch_torfast_browser.read_browser_default_prefs") as read_prefs,
                patch("launch_torfast_browser.validate_default_prefs") as validate_prefs,
                patch(
                    "launch_torfast_browser.apply_browser_startup_seed_to_profile"
                ) as apply_seed,
                patch("launch_torfast_browser.port_is_open", return_value=False),
                patch(
                    "launch_torfast_browser.launch_browser_with_c_tor",
                    side_effect=fake_launch,
                ),
                patch("launch_torfast_browser.describe_seed", return_value={}),
                patch(
                    "launch_torfast_browser.describe_browser_startup_seed",
                    return_value={},
                ),
            ):
                exit_code = main(
                    [
                        "--browser-bin",
                        str(browser_bin),
                        "--tor-bin",
                        str(tor_bin),
                        "--state-root",
                        str(state_root),
                        "--url",
                        "https://www.torproject.org/",
                        "--leave-tor-running",
                        "--browser-startup-seed",
                        "--start-managed-tor-only",
                    ]
                )

        self.assertEqual(exit_code, 0)
        read_prefs.assert_not_called()
        validate_prefs.assert_not_called()
        apply_seed.assert_not_called()
        self.assertEqual(
            captured_plan["browser_default_prefs"],
            {
                "ok": True,
                "skipped": True,
                "reason": "browser launch skipped",
            },
        )
        self.assertEqual(
            captured_plan["browser_default_pref_check"],
            {
                "ok": True,
                "skipped": True,
                "reason": "browser launch skipped",
            },
        )
        self.assertEqual(
            captured_plan["browser_startup_seed_apply"],
            {
                "ok": True,
                "applied": False,
                "reason": "browser launch skipped",
                "seed_root": str(DEFAULT_BROWSER_STARTUP_SEED_ROOT),
            },
        )

    def test_build_launch_plan_keeps_gate_diagnostics_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            paths = resolve_launch_paths(root / "state-root")
            ensure_state_dirs(paths)
            paths.torrc.write_text(
                "SocksPort 127.0.0.1:19450 IsolateSOCKSAuth\n",
                encoding="utf-8",
            )

            with (
                patch("launch_torfast_browser.describe_seed", return_value={}),
                patch(
                    "launch_torfast_browser.describe_browser_startup_seed",
                    return_value={},
                ),
            ):
                plan = build_launch_plan(
                    browser_bin=Path("/tmp/firefox"),
                    tor_bin=Path("/tmp/tor"),
                    paths=paths,
                    port=19450,
                    url="https://check.torproject.org/",
                    headless=False,
                    browser_timeout=3.0,
                    browser_launch_gate="tor_boot_95",
                    browser_launch_gate_requested="tor_boot_95",
                    conflux_client_ux=None,
                    leave_tor_running=True,
                    reuse_tor_if_running=True,
                    start_managed_tor_only=False,
                    browser_runtime_reset={"ok": True},
                    dir_cache_seed_root=root / "dir-seed",
                    dir_cache_seed_apply={"ok": True, "applied": False},
                    browser_startup_seed_root=root / "browser-seed",
                    browser_startup_seed_apply={"ok": True, "applied": False},
                    reused_tor_service=None,
                    default_pref_proof={"ok": True},
                    default_pref_check={"ok": True},
                    control_port=29450,
                    control_cookie_path=paths.control_cookie_path,
                    gate_diagnostics_enabled=True,
                    managed_open_settle_enabled=True,
                    managed_open_browser_overlap_enabled=True,
                    managed_open_adaptive_general_circuit_wait_timeout_seconds=0.75,
                    warm_browser_prestart_enabled=True,
                    reused_prestarted_browser={"pid": 321, "marionette_port": 2828},
                    stream_isolation_probe=False,
                    stream_isolation_probe_timeout=1.5,
                )

        self.assertTrue(plan["gate_diagnostics_enabled"])
        self.assertTrue(plan["managed_open_browser_overlap_enabled"])
        self.assertEqual(
            plan["managed_open_adaptive_general_circuit_wait_timeout_seconds"],
            0.75,
        )
        self.assertTrue(plan["warm_browser_prestart_enabled"])
        self.assertEqual(plan["reused_prestarted_browser"]["pid"], 321)

    def test_managed_open_browser_overlap_reason_requires_reused_http_tor_boot_95(
        self,
    ) -> None:
        self.assertEqual(
            managed_open_browser_overlap_reason(
                enabled=False,
                reused_tor_service={},
                target_gate="tor_boot_95",
                url="https://check.torproject.org/",
            ),
            "disabled by flag",
        )
        self.assertEqual(
            managed_open_browser_overlap_reason(
                enabled=True,
                reused_tor_service=None,
                target_gate="tor_boot_95",
                url="https://check.torproject.org/",
            ),
            "not reusing managed service",
        )
        self.assertEqual(
            managed_open_browser_overlap_reason(
                enabled=True,
                reused_tor_service={},
                target_gate="tor_boot_100",
                url="https://check.torproject.org/",
            ),
            "non-tor_boot_95 target gate",
        )
        self.assertEqual(
            managed_open_browser_overlap_reason(
                enabled=True,
                reused_tor_service={},
                target_gate="tor_boot_95",
                url="about:blank",
            ),
            "non-network url",
        )

    def test_managed_open_overlap_initial_url_uses_about_blank_for_default_network_overlap(
        self,
    ) -> None:
        self.assertEqual(
            managed_open_overlap_initial_url(
                {
                    "url": "https://check.torproject.org/",
                    "browser_launch_gate_requested": "auto",
                    "browser_launch_gate": "tor_boot_95",
                    "managed_open_adaptive_general_circuit_wait_timeout_seconds": 0.12,
                }
            ),
            "about:blank",
        )
        self.assertEqual(
            managed_open_overlap_initial_url(
                {
                    "url": "https://check.torproject.org/",
                    "browser_launch_gate_requested": "tor_boot_95",
                    "browser_launch_gate": "tor_boot_95",
                    "managed_open_adaptive_general_circuit_wait_timeout_seconds": 0.12,
                }
            ),
            "about:blank",
        )

    def test_maybe_wait_for_managed_open_general_circuit_times_out_and_proceeds(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            service_path = Path(tempdir) / "tor-service.json"
            service = {
                "pid": 2468,
                "tor_log": "/tmp/tor.log",
                "ready_gate": "socks_ready",
                "control_port": 29050,
                "control_cookie_path": "/tmp/control_auth_cookie",
            }
            service_path.write_text(json.dumps(service), encoding="utf-8")

            with (
                patch(
                    "launch_torfast_browser.read_general_circuit_snapshot",
                    return_value={"ok": True, "matched_circuit_count": 0},
                ),
                patch(
                    "launch_torfast_browser.wait_for_general_circuits",
                    return_value={
                        "ok": False,
                        "error": "general circuit wait timeout",
                        "last_error": None,
                        "min_count": 1,
                    },
                ),
            ):
                refreshed, report = maybe_wait_for_managed_open_general_circuit(
                    service_path=service_path,
                    reused_tor_service=service,
                    requested_gate="auto",
                    target_gate="tor_boot_95",
                    timeout_seconds=0.75,
                    enabled=True,
                )

        self.assertEqual(refreshed["ready_gate"], "socks_ready")
        self.assertTrue(report["enabled"])
        self.assertTrue(report["applied"])
        self.assertTrue(report["ok"])
        self.assertFalse(report["matched"])
        self.assertTrue(report["timed_out"])
        self.assertEqual(report["reason"], "timeout_proceed")
        self.assertEqual(report["seconds"], 0.75)

    def test_maybe_wait_for_managed_open_general_circuit_skips_when_already_matched(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            service_path = Path(tempdir) / "tor-service.json"
            service = {
                "pid": 2468,
                "tor_log": "/tmp/tor.log",
                "ready_gate": "socks_ready",
                "control_port": 29050,
                "control_cookie_path": "/tmp/control_auth_cookie",
            }
            service_path.write_text(json.dumps(service), encoding="utf-8")

            with (
                patch(
                    "launch_torfast_browser.read_general_circuit_snapshot",
                    return_value={"ok": True, "matched_circuit_count": 1},
                ),
                patch("launch_torfast_browser.wait_for_general_circuits") as wait,
            ):
                refreshed, report = maybe_wait_for_managed_open_general_circuit(
                    service_path=service_path,
                    reused_tor_service=service,
                    requested_gate="auto",
                    target_gate="tor_boot_95",
                    timeout_seconds=0.75,
                    enabled=True,
                )

        self.assertEqual(refreshed["ready_gate"], "socks_ready")
        self.assertTrue(report["ok"])
        self.assertTrue(report["matched"])
        self.assertFalse(report["timed_out"])
        self.assertEqual(report["seconds"], 0.0)
        self.assertEqual(report["reason"], "already_has_general_circuit")
        wait.assert_not_called()
        self.assertIsNone(
            managed_open_browser_overlap_reason(
                enabled=True,
                reused_tor_service={"pid": 1234},
                target_gate="tor_boot_95",
                url="https://check.torproject.org/",
            )
        )

    def test_overlap_adaptive_wait_proceeds_when_browser_startup_wins(self) -> None:
        class FakeProc:
            def poll(self) -> None:
                return None

        class FakeControlClient:
            def __init__(self) -> None:
                self.closed = False

            def close(self) -> None:
                self.closed = True

        with tempfile.TemporaryDirectory() as tempdir:
            service_path = Path(tempdir) / "tor-service.json"
            service = {
                "pid": 2468,
                "tor_log": "/tmp/tor.log",
                "ready_gate": "socks_ready",
                "control_port": 29050,
                "control_cookie_path": "/tmp/control_auth_cookie",
            }
            service_path.write_text(json.dumps(service), encoding="utf-8")
            client = FakeControlClient()

            with (
                patch(
                    "launch_torfast_browser.TorControlClient.connect",
                    return_value=client,
                ) as connect,
                patch(
                    "launch_torfast_browser.read_general_circuit_snapshot_with_client",
                    side_effect=[
                        {"ok": True, "matched_circuit_count": 0},
                        {"ok": True, "matched_circuit_count": 0},
                        {"ok": True, "matched_circuit_count": 0},
                    ],
                ),
                patch("launch_torfast_browser.port_is_open", return_value=True),
            ):
                refreshed, report = (
                    maybe_wait_for_managed_open_general_circuit_during_browser_startup(
                        service_path=service_path,
                        reused_tor_service=service,
                        requested_gate="auto",
                        target_gate="tor_boot_95",
                        browser_proc=FakeProc(),
                        marionette_port=2828,
                        timeout_seconds=0.75,
                    )
                )

        self.assertEqual(refreshed["ready_gate"], "socks_ready")
        self.assertTrue(report["enabled"])
        self.assertTrue(report["applied"])
        self.assertTrue(report["ok"])
        self.assertFalse(report["matched"])
        self.assertFalse(report["timed_out"])
        self.assertEqual(report["reason"], "browser_startup_proceed")
        self.assertEqual(report["matched_circuit_count"], 0)
        connect.assert_called_once_with(
            host="127.0.0.1",
            port=29050,
            cookie_path=Path("/tmp/control_auth_cookie"),
        )
        self.assertTrue(client.closed)

    def test_overlap_adaptive_wait_accepts_target_stream_activity(self) -> None:
        class FakeProc:
            def poll(self) -> None:
                return None

        class FakeControlClient:
            def __init__(self) -> None:
                self.closed = False

            def close(self) -> None:
                self.closed = True

        with tempfile.TemporaryDirectory() as tempdir:
            service_path = Path(tempdir) / "tor-service.json"
            service = {
                "pid": 2468,
                "tor_log": "/tmp/tor.log",
                "ready_gate": "socks_ready",
                "control_port": 29050,
                "control_cookie_path": "/tmp/control_auth_cookie",
            }
            service_path.write_text(json.dumps(service), encoding="utf-8")
            client = FakeControlClient()

            with (
                patch(
                    "launch_torfast_browser.TorControlClient.connect",
                    return_value=client,
                ),
                patch(
                    "launch_torfast_browser.read_general_circuit_snapshot_with_client",
                    return_value={"ok": True, "matched_circuit_count": 0},
                ),
                patch(
                    "launch_torfast_browser.read_user_stream_snapshot_with_client",
                    return_value={
                        "ok": True,
                        "polls": 1,
                        "observed_stream_count": 1,
                        "user_stream_count": 1,
                        "targets": ["check.torproject.org:443"],
                        "target_substrings": ["check.torproject.org"],
                    },
                ),
            ):
                refreshed, report = (
                    maybe_wait_for_managed_open_general_circuit_during_browser_startup(
                        service_path=service_path,
                        reused_tor_service=service,
                        requested_gate="auto",
                        target_gate="tor_boot_95",
                        browser_proc=FakeProc(),
                        marionette_port=2828,
                        timeout_seconds=0.75,
                        target_url="https://check.torproject.org/",
                    )
                )

        self.assertEqual(refreshed["ready_gate"], "socks_ready")
        self.assertTrue(report["ok"])
        self.assertEqual(report["reason"], "target_stream_activity")
        self.assertTrue(
            report["browser_launch_gate_wait"]["ready_via_target_stream_activity"]
        )
        self.assertEqual(
            report["target_stream_snapshot"]["targets"],
            ["check.torproject.org:443"],
        )
        self.assertTrue(client.closed)

    def test_overlap_adaptive_wait_promotes_target_gate_when_hidden_window_allows(
        self,
    ) -> None:
        class FakeProc:
            def poll(self) -> None:
                return None

        class FakeControlClient:
            def __init__(self) -> None:
                self.closed = False

            def close(self) -> None:
                self.closed = True

        with tempfile.TemporaryDirectory() as tempdir:
            service_path = Path(tempdir) / "tor-service.json"
            service = {
                "pid": 2468,
                "tor_log": str(Path(tempdir) / "tor.log"),
                "ready_gate": "socks_ready",
                "control_port": 29050,
                "control_cookie_path": "/tmp/control_auth_cookie",
            }
            service_path.write_text(json.dumps(service), encoding="utf-8")
            client = FakeControlClient()
            browser_session_done = threading.Event()
            browser_session_done.set()

            with (
                patch(
                    "launch_torfast_browser.TorControlClient.connect",
                    return_value=client,
                ),
                patch(
                    "launch_torfast_browser.read_general_circuit_snapshot_with_client",
                    side_effect=[
                        {"ok": True, "matched_circuit_count": 0},
                        {"ok": True, "matched_circuit_count": 0},
                        {"ok": True, "matched_circuit_count": 0},
                    ],
                ),
                patch(
                    "launch_torfast_browser.control_ready_for_gate_with_client",
                    side_effect=[
                        None,
                        {
                            "ok": True,
                            "progress": 95,
                            "tag": "circuit_create",
                        },
                    ],
                ),
                patch("launch_torfast_browser.time.sleep"),
            ):
                refreshed, report = (
                    maybe_wait_for_managed_open_general_circuit_during_browser_startup(
                        service_path=service_path,
                        reused_tor_service=service,
                        requested_gate="auto",
                        target_gate="tor_boot_95",
                        browser_proc=FakeProc(),
                        marionette_port=2828,
                        timeout_seconds=0.75,
                        browser_session_done=browser_session_done,
                        browser_session_state={"ok": True},
                        browser_session_timeout_seconds=1.0,
                    )
                )
            updated_service = json.loads(service_path.read_text(encoding="utf-8"))

        self.assertEqual(refreshed["ready_gate"], "tor_boot_95")
        self.assertTrue(report["ok"])
        self.assertFalse(report["matched"])
        self.assertEqual(report["reason"], "browser_startup_proceed")
        self.assertTrue(report["browser_launch_gate_wait"]["ok"])
        self.assertTrue(report["browser_launch_gate_wait"]["ready_via_control"])
        self.assertEqual(updated_service["ready_gate"], "tor_boot_95")
        self.assertTrue(client.closed)

    def test_start_managed_open_browser_overlap_session_uses_eager_target_navigation_by_default(
        self,
    ) -> None:
        class FakeProc:
            def __init__(self) -> None:
                self.pid = 1357
                self.returncode = None

            def poll(self) -> None:
                return None

        class FakeSock:
            def settimeout(self, _timeout: float) -> None:
                return None

        class FakeClient:
            def __init__(self) -> None:
                self.sock = FakeSock()
                self.commands: list[tuple[str, dict[str, object]]] = []

            def command(self, name: str, params: dict[str, object]) -> dict[str, object]:
                self.commands.append((name, params))
                if name == "WebDriver:ExecuteScript":
                    return {"value": True}
                return {"value": None}

        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            paths = resolve_launch_paths(root / "state-root")
            ensure_state_dirs(paths)
            browser_bin = root / "firefox"
            browser_bin.write_text("", encoding="utf-8")
            service = {
                "pid": 2468,
                "tor_log": str(paths.tor_log),
                "ready_gate": "socks_ready",
                "control_port": 29450,
                "control_cookie_path": str(paths.control_cookie_path),
            }
            paths.tor_service_json.write_text(json.dumps(service), encoding="utf-8")
            plan = {
                "browser_bin": str(browser_bin),
                "browser_launch_gate": "tor_boot_95",
                "browser_launch_gate_requested": "auto",
                "browser_timeout_seconds": 3.0,
                "headless": True,
                "managed_open_adaptive_general_circuit_wait_timeout_seconds": 0.125,
                "port": 19450,
                "url": "https://check.torproject.org/",
            }
            client_stub = FakeClient()

            with (
                patch(
                    "launch_torfast_browser.start_browser_launcher",
                    return_value=(FakeProc(), queue.Queue()),
                ),
                patch(
                    "run_browser_compare.MarionetteClient.connect",
                    return_value=client_stub,
                ),
                patch(
                    "launch_torfast_browser.maybe_wait_for_managed_open_general_circuit_during_browser_startup",
                    return_value=(service, {"ok": True, "applied": True}),
                ) as adaptive_wait,
                patch("launch_torfast_browser.port_is_open", return_value=False),
            ):
                (
                    _browser_proc,
                    _browser_lines,
                    client,
                    overlap_report,
                    _refreshed_service,
                    _overlap_wait_report,
                ) = start_managed_open_browser_overlap_session(
                    plan,
                    paths_dict=paths.as_dict(),
                    service_path=paths.tor_service_json,
                    reused_tor_service=service,
                )

        self.assertIs(client, client_stub)
        self.assertFalse(overlap_report["launched_on_target_url"])
        self.assertTrue(overlap_report["marionette_session_used"])
        self.assertTrue(overlap_report["eager_target_navigation_enabled"])
        self.assertTrue(overlap_report["eager_target_navigation"]["ok"])
        self.assertEqual(
            overlap_report["initial_url"],
            "about:blank",
        )
        self.assertIsNotNone(adaptive_wait.call_args.kwargs["browser_session_done"])
        self.assertIsNotNone(adaptive_wait.call_args.kwargs["browser_session_state"])
        self.assertIsNotNone(
            adaptive_wait.call_args.kwargs["browser_session_timeout_seconds"]
        )

    def test_start_managed_open_browser_overlap_session_uses_eager_target_navigation_when_target_stream_proof_enabled(
        self,
    ) -> None:
        class FakeProc:
            def __init__(self) -> None:
                self.pid = 1357
                self.returncode = None

            def poll(self) -> None:
                return None

        class FakeSock:
            def settimeout(self, _timeout: float) -> None:
                return None

        class FakeClient:
            def __init__(self) -> None:
                self.sock = FakeSock()
                self.commands: list[tuple[str, dict[str, object]]] = []

            def command(self, name: str, params: dict[str, object]) -> dict[str, object]:
                self.commands.append((name, params))
                if name == "WebDriver:ExecuteScript":
                    return {"value": True}
                return {"value": None}

        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            paths = resolve_launch_paths(root / "state-root")
            ensure_state_dirs(paths)
            browser_bin = root / "firefox"
            browser_bin.write_text("", encoding="utf-8")
            service = {
                "pid": 2468,
                "tor_log": str(paths.tor_log),
                "ready_gate": "socks_ready",
                "control_port": 29450,
                "control_cookie_path": str(paths.control_cookie_path),
            }
            paths.tor_service_json.write_text(json.dumps(service), encoding="utf-8")
            plan = {
                "browser_bin": str(browser_bin),
                "browser_launch_gate": "tor_boot_95",
                "browser_launch_gate_requested": "auto",
                "browser_timeout_seconds": 3.0,
                "headless": True,
                "managed_open_adaptive_general_circuit_wait_timeout_seconds": 0.125,
                "port": 19450,
                "url": "https://check.torproject.org/",
            }
            client_stub = FakeClient()

            with (
                patch.dict(
                    "os.environ",
                    {"TORFAST_ENABLE_TARGET_STREAM_PROOF": "1"},
                    clear=False,
                ),
                patch(
                    "launch_torfast_browser.start_browser_launcher",
                    return_value=(FakeProc(), queue.Queue()),
                ) as start_browser,
                patch(
                    "run_browser_compare.MarionetteClient.connect",
                    return_value=client_stub,
                ),
                patch(
                    "launch_torfast_browser.maybe_wait_for_managed_open_general_circuit_during_browser_startup",
                    return_value=(service, {"ok": True, "applied": True}),
                ) as adaptive_wait,
                patch("launch_torfast_browser.port_is_open", return_value=False),
            ):
                (
                    _browser_proc,
                    _browser_lines,
                    client,
                    overlap_report,
                    _refreshed_service,
                    _overlap_wait_report,
                ) = start_managed_open_browser_overlap_session(
                    plan,
                    paths_dict=paths.as_dict(),
                    service_path=paths.tor_service_json,
                    reused_tor_service=service,
                )

        command = start_browser.call_args.kwargs["command"]
        self.assertIn("--marionette", command)
        self.assertIs(client, client_stub)
        self.assertFalse(overlap_report["launched_on_target_url"])
        self.assertTrue(overlap_report["marionette_listener_enabled"])
        self.assertFalse(overlap_report["marionette_proof_only"])
        self.assertTrue(overlap_report["marionette_session_used"])
        self.assertTrue(overlap_report["eager_target_navigation_enabled"])
        self.assertTrue(overlap_report["eager_target_navigation"]["ok"])
        self.assertEqual(overlap_report["initial_url"], "about:blank")
        self.assertIsNotNone(adaptive_wait.call_args.kwargs["browser_session_done"])
        self.assertIsNotNone(adaptive_wait.call_args.kwargs["browser_session_state"])

    def test_maybe_collect_target_launch_browser_probe_uses_marionette_when_available(
        self,
    ) -> None:
        class FakeProc:
            def __init__(self) -> None:
                self.pid = 1357

            def poll(self) -> None:
                return None

        class FakeClient:
            def __init__(self) -> None:
                self.closed = False

            def close(self) -> None:
                self.closed = True

        client = FakeClient()
        with (
            patch.dict(
                "os.environ",
                {"TORFAST_ENABLE_TARGET_STREAM_PROOF": "1"},
                clear=False,
            ),
            patch("launch_torfast_browser.port_is_open", return_value=True),
            patch(
                "launch_torfast_browser.connect_existing_marionette_session",
                return_value=client,
            ),
            patch(
                "launch_torfast_browser.collect_browser_target_load_probe",
                return_value={
                    "ok": True,
                    "current_url": "https://check.torproject.org/",
                    "same_host_as_target": True,
                },
            ),
        ):
            result = maybe_collect_target_launch_browser_probe(
                browser_proc=FakeProc(),
                overlap_report={
                    "launched_on_target_url": True,
                    "marionette_listener_enabled": True,
                    "marionette_port": 2828,
                },
                target_url="https://check.torproject.org/",
            )

        self.assertTrue(result["applied"])
        self.assertTrue(result["same_host_as_target"])
        self.assertEqual(result["current_url"], "https://check.torproject.org/")
        self.assertTrue(client.closed)

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
                "gate_diagnostics_enabled": True,
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
                patch(
                    "launch_torfast_browser.read_bootstrap_phase_snapshot",
                    side_effect=[
                        {
                            "ok": True,
                            "progress": 75,
                            "tag": "enough_dirinfo",
                            "summary": "Loaded enough directory info to build circuits",
                        },
                        {
                            "ok": True,
                            "progress": 95,
                            "tag": "circuit_create",
                            "summary": "Establishing a Tor circuit",
                        },
                    ],
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
                "gate_diagnostics_enabled": True,
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
                patch(
                    "launch_torfast_browser.read_bootstrap_phase_snapshot",
                    side_effect=[
                        {
                            "ok": True,
                            "progress": 75,
                            "tag": "enough_dirinfo",
                            "summary": "Loaded enough directory info to build circuits",
                        },
                        {
                            "ok": True,
                            "progress": 95,
                            "tag": "circuit_create",
                            "summary": "Establishing a Tor circuit",
                        },
                    ],
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

    def test_warm_writes_pending_managed_service_metadata_before_wait(self) -> None:
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
                "gate_diagnostics_enabled": False,
                "leave_tor_running": True,
                "paths": paths.as_dict(),
                "port": 19450,
                "reused_tor_service": None,
                "start_managed_tor_only": True,
                "stream_isolation_probe_enabled": False,
                "tor_bin": "/tmp/tor",
                "url": "about:tor",
            }

            def wait_side_effect(**_kwargs):
                service = json.loads(paths.tor_service_json.read_text())
                self.assertEqual(service["pid"], 9876)
                self.assertIsNone(service["ready_gate"])
                return {
                    "ok": True,
                    "seconds": 0.25,
                    "ready_epoch_ms": 1000.0,
                    "ready_monotonic_seconds": 50.0,
                    "lines": ["Opened Socks listener connection (ready)"],
                    "signal_lines": [],
                }

            with (
                patch(
                    "launch_torfast_browser.start_c_tor_detached",
                    return_value=FakeProc(9876),
                ),
                patch(
                    "launch_torfast_browser.wait_for_ready_in_log",
                    side_effect=wait_side_effect,
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
            service = json.loads(paths.tor_service_json.read_text())
            self.assertEqual(service["ready_gate"], "socks_ready")

    def test_warm_requests_runtime_helper_gate_promoter_before_wait(self) -> None:
        class FakeProc:
            def __init__(self, pid: int) -> None:
                self.pid = pid
                self.returncode = None

            def poll(self) -> None:
                return None

        class FakeThread:
            def is_alive(self) -> bool:
                return True

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
                "gate_diagnostics_enabled": False,
                "leave_tor_running": True,
                "paths": paths.as_dict(),
                "port": 19450,
                "reused_tor_service": None,
                "start_managed_tor_only": True,
                "stream_isolation_probe_enabled": False,
                "tor_bin": "/tmp/tor",
                "url": "about:tor",
            }

            def wait_side_effect(**_kwargs):
                service = json.loads(paths.tor_service_json.read_text())
                self.assertEqual(
                    plan["runtime_helper_gate_promoter"],
                    {
                        "requested": True,
                        "active_after_request": True,
                        "mode": "in_process",
                    },
                )
                self.assertTrue(service["runtime_helper_gate_promoter_requested"])
                self.assertEqual(
                    service["runtime_helper_gate_promoter_mode"],
                    "in_process",
                )
                return {
                    "ok": True,
                    "seconds": 0.25,
                    "ready_epoch_ms": 1000.0,
                    "ready_monotonic_seconds": 50.0,
                    "lines": ["Opened Socks listener connection (ready)"],
                    "signal_lines": [],
                }

            with (
                patch(
                    "launch_torfast_browser.start_c_tor_detached",
                    return_value=FakeProc(9876),
                ),
                patch(
                    "torfast.fast_runtime.running_runtime_helper_metadata",
                    return_value={"pid": os.getpid()},
                ),
                patch(
                    "torfast.runtime_helper.maybe_restart_background_gate_promoter",
                    return_value=FakeThread(),
                ) as start_promoter,
                patch(
                    "launch_torfast_browser.wait_for_ready_in_log",
                    side_effect=wait_side_effect,
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
            start_promoter.assert_called_once_with(
                paths.state_root,
                thread=None,
            )

    def test_maybe_start_runtime_helper_gate_promoter_can_request_helper_socket(
        self,
    ) -> None:
        class FakeSocket:
            def __init__(self) -> None:
                self.connected_path = None
                self.sent = []

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb) -> None:
                del exc_type, exc, tb
                return None

            def settimeout(self, _value: object) -> None:
                return None

            def connect(self, path: str) -> None:
                self.connected_path = path

            def sendall(self, payload: bytes) -> None:
                self.sent.append(payload)

            def shutdown(self, _how: object) -> None:
                return None

            def recv(self, _size: int) -> bytes:
                if self.sent:
                    self.sent.clear()
                    return json.dumps(
                        {
                            "ok": True,
                            "active_after_request": True,
                        }
                    ).encode("utf-8")
                return b""

        fake_socket = FakeSocket()
        with (
            patch(
                "torfast.fast_runtime.running_runtime_helper_metadata",
                return_value={
                    "pid": 999999,
                    "socket_path": "/tmp/torfast-helper.sock",
                },
            ),
            patch(
                "launch_torfast_browser.socket.socket",
                return_value=fake_socket,
            ),
        ):
            result = maybe_start_runtime_helper_gate_promoter(
                Path("/tmp/state-root")
            )

        self.assertEqual(
            result,
            {
                "requested": True,
                "active_after_request": True,
                "mode": "socket_request",
            },
        )
        self.assertEqual(fake_socket.connected_path, "/tmp/torfast-helper.sock")
        self.assertEqual(
            fake_socket.sent,
            [],
        )

    def test_should_refresh_managed_service_metadata_wait_is_eager_for_promoter(
        self,
    ) -> None:
        requested_service = {
            "runtime_helper_gate_promoter_requested": True,
        }

        self.assertFalse(
            should_refresh_managed_service_metadata_wait(
                polls=1,
                expected_service=requested_service,
            )
        )
        self.assertTrue(
            should_refresh_managed_service_metadata_wait(
                polls=2,
                expected_service=requested_service,
            )
        )
        self.assertTrue(
            should_refresh_managed_service_metadata_wait(
                polls=3,
                expected_service=requested_service,
            )
        )
        self.assertFalse(
            should_refresh_managed_service_metadata_wait(
                polls=3,
                expected_service={},
            )
        )

    def test_warm_managed_dir_cache_seed_refresh_skips_before_tor_boot_95(
        self,
    ) -> None:
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
            seed_root = Path(tempdir) / "dir-seed"
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
                },
                "dir_cache_seed_root": str(seed_root),
                "gate_diagnostics_enabled": True,
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
                patch("launch_torfast_browser.update_seed_from_data_dir") as update_seed,
                patch("launch_torfast_browser.describe_seed", return_value={}),
                patch(
                    "launch_torfast_browser.describe_browser_startup_seed",
                    return_value={},
                ),
                patch("builtins.print"),
            ):
                exit_code = launch_browser_with_c_tor(plan)

            self.assertEqual(exit_code, 0)
            update_seed.assert_not_called()
            self.assertEqual(
                plan["dir_cache_seed_update"],
                {
                    "ok": True,
                    "updated": False,
                    "reason": (
                        "managed tor has not reached tor_boot_95 for dir-cache "
                        "seed refresh"
                    ),
                    "seed_root": str(seed_root),
                    "ready_gate": "socks_ready",
                },
            )

    def test_warm_managed_dir_cache_seed_refresh_updates_at_tor_boot_95(self) -> None:
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
            seed_root = Path(tempdir) / "dir-seed"
            plan = {
                "browser_command": ["/tmp/firefox", "about:tor"],
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
                },
                "dir_cache_seed_root": str(seed_root),
                "gate_diagnostics_enabled": True,
                "leave_tor_running": True,
                "paths": paths.as_dict(),
                "port": 19450,
                "reused_tor_service": None,
                "start_managed_tor_only": True,
                "stream_isolation_probe_enabled": False,
                "tor_bin": "/tmp/tor",
                "url": "about:tor",
            }
            update_result = {
                "ok": True,
                "updated": True,
                "seed_root": str(seed_root),
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
                        "lines": [
                            "Bootstrapped 95% (circuit_create): Establishing a Tor circuit"
                        ],
                        "signal_lines": [],
                    },
                ),
                patch(
                    "launch_torfast_browser.update_seed_from_data_dir",
                    return_value=update_result,
                ) as update_seed,
                patch("launch_torfast_browser.describe_seed", return_value={}),
                patch(
                    "launch_torfast_browser.describe_browser_startup_seed",
                    return_value={},
                ),
                patch("builtins.print"),
            ):
                exit_code = launch_browser_with_c_tor(plan)

            self.assertEqual(exit_code, 0)
            update_seed.assert_called_once_with(paths.data_dir, seed_root)
            self.assertEqual(plan["dir_cache_seed_update"], update_result)

    def test_fresh_open_defers_dir_cache_seed_refresh_until_post_browser_tor_boot(
        self,
    ) -> None:
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
            seed_root = Path(tempdir) / "dir-seed"
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
                },
                "dir_cache_seed_root": str(seed_root),
                "gate_diagnostics_enabled": False,
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

            def fake_wait_for_ready_in_log(*, ready_text: str, **_kwargs) -> dict[str, object]:
                if ready_text == browser_launch_gate_ready_text("tor_boot_95"):
                    events.append("wait:tor_boot_95")
                    return {
                        "ok": True,
                        "seconds": 0.25,
                        "ready_epoch_ms": 1000.0,
                        "ready_monotonic_seconds": 50.0,
                        "lines": [
                            "Bootstrapped 95% (circuit_create): Establishing a Tor circuit"
                        ],
                        "signal_lines": [],
                    }
                events.append("wait:tor_boot_100")
                return {
                    "ok": True,
                    "seconds": 0.4,
                    "ready_epoch_ms": 1200.0,
                    "ready_monotonic_seconds": 51.0,
                    "lines": ["Bootstrapped 100% (done): Done"],
                    "signal_lines": ["Bootstrapped 100% (done): Done"],
                }

            def fake_start_browser_launcher(**_kwargs) -> tuple[FakeProc, queue.Queue[str]]:
                events.append("browser_start")
                return FakeProc(1357), queue.Queue()

            update_result = {
                "ok": True,
                "updated": True,
                "seed_root": str(seed_root),
            }

            def fake_update_seed_from_data_dir(*_args) -> dict[str, object]:
                events.append("seed_update")
                return update_result

            with (
                patch(
                    "launch_torfast_browser.start_c_tor_detached",
                    return_value=FakeProc(2468),
                ),
                patch(
                    "launch_torfast_browser.wait_for_ready_in_log",
                    side_effect=fake_wait_for_ready_in_log,
                ),
                patch(
                    "launch_torfast_browser.start_browser_launcher",
                    side_effect=fake_start_browser_launcher,
                ),
                patch(
                    "launch_torfast_browser.wait_for_browser_exit",
                    side_effect=lambda **_kwargs: (
                        events.append("browser_exit")
                        or {
                            "ok": True,
                            "exit_code": 0,
                            "timed_out": False,
                            "interrupted": False,
                        }
                    ),
                ),
                patch(
                    "launch_torfast_browser.update_seed_from_data_dir",
                    side_effect=fake_update_seed_from_data_dir,
                ) as update_seed,
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
                    "wait:tor_boot_95",
                    "browser_start",
                    "browser_exit",
                    "wait:tor_boot_100",
                    "seed_update",
                ],
            )
            update_seed.assert_called_once_with(paths.data_dir, seed_root)
            self.assertEqual(plan["dir_cache_seed_update"], update_result)

    def test_prime_one_shot_dir_cache_seed_refresh_updates_after_full_boot(
        self,
    ) -> None:
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
            seed_root = Path(tempdir) / "dir-seed"
            plan = {
                "browser_command": ["/tmp/firefox", "about:tor"],
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
                },
                "dir_cache_seed_root": str(seed_root),
                "gate_diagnostics_enabled": False,
                "leave_tor_running": False,
                "paths": paths.as_dict(),
                "port": 19450,
                "reused_tor_service": None,
                "start_managed_tor_only": True,
                "stream_isolation_probe_enabled": False,
                "tor_bin": "/tmp/tor",
                "url": "about:tor",
            }
            update_result = {
                "ok": True,
                "updated": True,
                "seed_root": str(seed_root),
            }

            with (
                patch(
                    "launch_torfast_browser.start_c_tor_launcher",
                    return_value=(FakeProc(2468), queue.Queue()),
                ),
                patch(
                    "launch_torfast_browser.wait_for_line",
                    return_value={
                        "ok": True,
                        "seconds": 0.8,
                        "ready_epoch_ms": 1200.0,
                        "ready_monotonic_seconds": 51.0,
                        "lines": ["Bootstrapped 100% (done): Done"],
                        "signal_lines": ["Bootstrapped 100% (done): Done"],
                    },
                ),
                patch(
                    "launch_torfast_browser.update_seed_from_data_dir",
                    return_value=update_result,
                ) as update_seed,
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
            update_seed.assert_called_once_with(paths.data_dir, seed_root)
            self.assertTrue(plan["tor_boot"]["ok"])
            self.assertEqual(plan["dir_cache_seed_update"], update_result)

    def test_reused_managed_warm_waits_for_requested_gate(self) -> None:
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
                "gate_diagnostics_enabled": False,
                "leave_tor_running": True,
                "paths": paths.as_dict(),
                "port": 19450,
                "reused_tor_service": service,
                "start_managed_tor_only": True,
                "stream_isolation_probe_enabled": False,
                "tor_bin": "/tmp/tor",
                "url": "https://check.torproject.org/",
            }

            with (
                patch(
                    "launch_torfast_browser.wait_for_existing_service_ready_in_log",
                    return_value={
                        "ok": True,
                        "polls": 2,
                        "seconds": 0.6,
                        "ready_epoch_ms": 1200.0,
                        "ready_monotonic_seconds": 51.0,
                        "lines": ["Bootstrapped 100% (done): Done"],
                        "signal_lines": ["Bootstrapped 100% (done): Done"],
                    },
                ) as wait_for_existing,
                patch("builtins.print"),
            ):
                exit_code = launch_browser_with_c_tor(plan)

            self.assertEqual(exit_code, 0)
            wait_for_existing.assert_called_once()
            self.assertEqual(
                wait_for_existing.call_args.kwargs["ready_text"],
                browser_launch_gate_ready_text("tor_boot_100"),
            )
            self.assertEqual(plan["tor_managed_ready"]["gate"], "tor_boot_100")
            self.assertTrue(plan["browser"]["skipped"])
            self.assertEqual(
                plan["reused_tor_service"]["ready_gate"],
                "tor_boot_100",
            )
            service_after = json.loads(paths.tor_service_json.read_text())
            self.assertEqual(service_after["ready_gate"], "tor_boot_100")

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
                "gate_diagnostics_enabled": True,
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
                    "polls": 1,
                    "seconds": 0.4,
                    "ready_epoch_ms": 1000.0,
                    "ready_monotonic_seconds": 50.0,
                    "lines": ["Bootstrapped 95% (circuit_create): Establishing a Tor circuit"],
                    "signal_lines": [],
                },
                {
                    "ok": True,
                    "polls": 2,
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
                patch(
                    "launch_torfast_browser.read_bootstrap_phase_snapshot",
                    side_effect=[
                        {
                            "ok": True,
                            "progress": 75,
                            "tag": "enough_dirinfo",
                            "summary": "Loaded enough directory info to build circuits",
                        },
                        {
                            "ok": True,
                            "progress": 95,
                            "tag": "circuit_create",
                            "summary": "Establishing a Tor circuit",
                        },
                    ],
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
            self.assertEqual(
                plan["tor_browser_launch_gate"]["diagnostics"][
                    "service_ready_gate_before_wait"
                ],
                "socks_ready",
            )
            self.assertFalse(
                plan["tor_browser_launch_gate"]["diagnostics"][
                    "ready_text_present_before_wait"
                ]
            )
            self.assertEqual(
                plan["tor_browser_launch_gate"]["diagnostics"][
                    "control_bootstrap_phase_before_wait"
                ]["progress"],
                75,
            )
            self.assertEqual(
                plan["tor_browser_launch_gate"]["diagnostics"][
                    "control_bootstrap_phase_after_wait"
                ]["progress"],
                95,
            )
            self.assertEqual(
                plan["tor_browser_launch_gate"]["diagnostics"]["wait_polls"],
                1,
            )
            self.assertTrue(plan["tor_boot"]["ok"])
            self.assertEqual(
                plan["reused_tor_service"]["ready_gate"],
                "tor_boot_100",
            )
            service_after = json.loads(paths.tor_service_json.read_text())
            self.assertEqual(service_after["ready_gate"], "tor_boot_100")

    def test_reused_managed_open_can_reuse_prestarted_browser(self) -> None:
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
            prestarted = {
                "pid": 9753,
                "marionette_port": 2828,
                "initial_url": "about:blank",
            }
            paths.tor_service_json.write_text(json.dumps(service), encoding="utf-8")
            paths.prestarted_browser_json.write_text(
                json.dumps(prestarted),
                encoding="utf-8",
            )
            plan = {
                "browser_command": ["/tmp/firefox", "https://check.torproject.org/"],
                "browser_launch_gate": "tor_boot_95",
                "browser_launch_gate_requested": "auto",
                "browser_startup_seed_apply": {
                    "ok": True,
                    "applied": False,
                    "reason": "reused prestarted browser",
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
                "managed_open_settle_enabled": False,
                "managed_open_browser_overlap_enabled": False,
                "warm_browser_prestart_enabled": True,
                "paths": paths.as_dict(),
                "port": 19450,
                "reused_tor_service": service,
                "reused_prestarted_browser": prestarted,
                "start_managed_tor_only": False,
                "stream_isolation_probe_enabled": False,
                "tor_bin": "/tmp/tor",
                "url": "https://check.torproject.org/",
            }

            class FakeClient:
                def close(self) -> None:
                    return None

            with (
                patch(
                    "launch_torfast_browser.connect_existing_marionette_session",
                    return_value=FakeClient(),
                ) as connect_existing,
                patch(
                    "launch_torfast_browser.navigate_managed_open_browser_overlap_session",
                    return_value={"ok": True, "seconds": 0.01},
                ) as navigate,
                patch(
                    "launch_torfast_browser.wait_for_browser_exit",
                    return_value={
                        "ok": True,
                        "exit_code": 0,
                        "timed_out": False,
                        "interrupted": False,
                    },
                ),
                patch("launch_torfast_browser.start_browser_launcher") as start_browser,
                patch("launch_torfast_browser.stop_process_tree"),
                patch("launch_torfast_browser.describe_seed", return_value={}),
                patch(
                    "launch_torfast_browser.describe_browser_startup_seed",
                    return_value={},
                ),
                patch("launch_torfast_browser.process_is_alive", return_value=True),
                patch("builtins.print"),
            ):
                exit_code = launch_browser_with_c_tor(plan)

            self.assertEqual(exit_code, 0)
            start_browser.assert_not_called()
            connect_existing.assert_called_once()
            navigate.assert_called_once()
            self.assertTrue(plan["warm_browser_prestart"]["applied"])
            self.assertFalse(paths.prestarted_browser_json.exists())

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

    def test_reused_managed_open_auto_settles_recent_service_before_browser(self) -> None:
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
                "ready_epoch_ms": 1000.0,
                "ready_monotonic_seconds": 50.0,
                "ready_gate": "socks_ready",
            }
            refreshed_service = {
                **service,
                "ready_epoch_ms": 2200.0,
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
                "browser_launch_gate_requested": "auto",
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
                "managed_open_settle_enabled": True,
                "paths": paths.as_dict(),
                "port": 19450,
                "reused_tor_service": service,
                "start_managed_tor_only": False,
                "stream_isolation_probe_enabled": False,
                "tor_bin": "/tmp/tor",
                "url": "https://check.torproject.org/",
            }

            read_json_calls = 0

            def read_json_side_effect(*_args, **_kwargs):
                nonlocal read_json_calls
                read_json_calls += 1
                if read_json_calls == 1:
                    return service
                return refreshed_service

            with (
                patch(
                    "launch_torfast_browser.read_json",
                    side_effect=read_json_side_effect,
                ),
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
                patch(
                    "launch_torfast_browser.wait_for_existing_service_ready_in_log"
                ) as wait_for_existing,
                patch(
                    "launch_torfast_browser.maybe_wait_for_managed_open_general_circuit",
                    return_value=(
                        refreshed_service,
                        {
                            "enabled": False,
                            "applied": False,
                            "reason": "disabled by flag",
                        },
                    ),
                ),
                patch("launch_torfast_browser.stop_process_tree"),
                patch("launch_torfast_browser.describe_seed", return_value={}),
                patch(
                    "launch_torfast_browser.describe_browser_startup_seed",
                    return_value={},
                ),
                patch("launch_torfast_browser.time.time", side_effect=[2.0, 2.7]),
                patch("launch_torfast_browser.time.sleep") as sleep,
                patch("builtins.print"),
            ):
                exit_code = launch_browser_with_c_tor(plan)

            self.assertEqual(exit_code, 0)
            sleep.assert_called_once_with(0.85)
            wait_for_existing.assert_not_called()
            self.assertTrue(plan["managed_open_settle"]["applied"])
            self.assertEqual(plan["managed_open_settle"]["slept_seconds"], 0.85)
            self.assertEqual(
                plan["managed_open_settle"]["service_ready_gate_after_settle"],
                "tor_boot_100",
            )
            self.assertEqual(plan["tor_browser_launch_gate"]["gate"], "tor_boot_95")
            self.assertEqual(plan["tor_browser_launch_gate"]["seconds"], 0.0)
            self.assertTrue(plan["tor_browser_launch_gate"]["reused_service"])
            self.assertEqual(plan["reused_tor_service"]["ready_gate"], "tor_boot_100")

    def test_reused_managed_open_calls_adaptive_general_circuit_wait_when_enabled(
        self,
    ) -> None:
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
                "ready_epoch_ms": 1000.0,
                "ready_monotonic_seconds": 50.0,
                "ready_gate": "socks_ready",
                "control_port": 29450,
                "control_cookie_path": str(paths.control_cookie_path),
            }
            paths.tor_service_json.write_text(
                json.dumps(service),
                encoding="utf-8",
            )
            plan = {
                "browser_command": ["/tmp/firefox", "https://check.torproject.org/"],
                "browser_launch_gate": "tor_boot_95",
                "browser_launch_gate_requested": "auto",
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
                "managed_open_settle_enabled": False,
                "managed_open_browser_overlap_enabled": False,
                "managed_open_adaptive_general_circuit_wait_timeout_seconds": 0.75,
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
                    "launch_torfast_browser.maybe_wait_for_managed_open_general_circuit",
                    return_value=(
                        service,
                        {
                            "enabled": True,
                            "applied": True,
                            "ok": True,
                            "matched": False,
                            "timed_out": True,
                            "seconds": 0.75,
                        },
                    ),
                ) as adaptive_wait,
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
                patch(
                    "launch_torfast_browser.wait_for_existing_service_ready_in_log",
                    return_value={
                        "ok": True,
                        "seconds": 0.0,
                        "polls": 1,
                        "reused_service": True,
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
            adaptive_wait.assert_called_once()
            self.assertEqual(
                plan["managed_open_adaptive_general_circuit_wait"]["seconds"],
                0.75,
            )

    def test_launch_browser_with_c_tor_uses_overlap_adaptive_wait_when_enabled(
        self,
    ) -> None:
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
                "tor_log": str(paths.tor_log),
                "ready_gate": "socks_ready",
                "control_port": 29450,
                "control_cookie_path": str(paths.control_cookie_path),
            }
            paths.tor_service_json.write_text(json.dumps(service), encoding="utf-8")
            plan = {
                "browser_command": ["/tmp/firefox", "https://check.torproject.org/"],
                "browser_launch_gate": "tor_boot_95",
                "browser_launch_gate_requested": "auto",
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
                "managed_open_settle_enabled": False,
                "managed_open_browser_overlap_enabled": True,
                "managed_open_adaptive_general_circuit_wait_timeout_seconds": 0.75,
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
                    "launch_torfast_browser.maybe_wait_for_managed_open_general_circuit"
                ) as serial_wait,
                patch(
                    "launch_torfast_browser.start_managed_open_browser_overlap_session",
                    return_value=(
                        FakeProc(1357),
                        queue.Queue(),
                        None,
                        {
                            "enabled": True,
                            "applied": True,
                            "initial_url": "https://check.torproject.org/",
                            "launched_on_target_url": True,
                        },
                        service,
                        {
                            "enabled": True,
                            "applied": True,
                            "ok": True,
                            "matched": False,
                            "timed_out": False,
                            "seconds": 0.25,
                            "reason": "browser_startup_proceed",
                        },
                    ),
                ),
                patch(
                    "launch_torfast_browser.navigate_managed_open_browser_overlap_session",
                ) as navigate,
                patch(
                    "launch_torfast_browser.wait_for_browser_exit",
                    return_value={
                        "ok": True,
                        "exit_code": 0,
                        "timed_out": False,
                        "interrupted": False,
                    },
                ),
                patch(
                    "launch_torfast_browser.wait_for_existing_service_ready_in_log",
                    return_value={
                        "ok": True,
                        "seconds": 0.0,
                        "polls": 1,
                        "reused_service": True,
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
        serial_wait.assert_not_called()
        self.assertEqual(
            plan["managed_open_adaptive_general_circuit_wait"]["reason"],
            "browser_startup_proceed",
        )

    def test_launch_browser_with_c_tor_records_target_launch_probe(
        self,
    ) -> None:
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
                "tor_log": str(paths.tor_log),
                "ready_gate": "socks_ready",
                "control_port": 29450,
                "control_cookie_path": str(paths.control_cookie_path),
            }
            paths.tor_service_json.write_text(json.dumps(service), encoding="utf-8")
            plan = {
                "browser_command": ["/tmp/firefox", "https://check.torproject.org/"],
                "browser_launch_gate": "tor_boot_95",
                "browser_launch_gate_requested": "auto",
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
                "managed_open_settle_enabled": False,
                "managed_open_browser_overlap_enabled": True,
                "managed_open_adaptive_general_circuit_wait_timeout_seconds": 0.126,
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
                    "launch_torfast_browser.maybe_wait_for_managed_open_general_circuit"
                ) as serial_wait,
                patch(
                    "launch_torfast_browser.start_managed_open_browser_overlap_session",
                    return_value=(
                        FakeProc(1357),
                        queue.Queue(),
                        None,
                        {
                            "enabled": True,
                            "applied": True,
                            "initial_url": "https://check.torproject.org/",
                            "launched_on_target_url": True,
                            "marionette_listener_enabled": True,
                            "marionette_session_used": False,
                            "marionette_port": 2828,
                        },
                        service,
                        {
                            "enabled": True,
                            "applied": True,
                            "ok": True,
                            "matched": False,
                            "timed_out": True,
                            "seconds": 0.126,
                            "reason": "timeout_proceed",
                        },
                    ),
                ),
                patch(
                    "launch_torfast_browser.navigate_managed_open_browser_overlap_session",
                ) as navigate,
                patch(
                    "launch_torfast_browser.wait_for_browser_exit",
                    return_value={
                        "ok": True,
                        "exit_code": None,
                        "timed_out": True,
                        "interrupted": False,
                    },
                ),
                patch(
                    "launch_torfast_browser.maybe_collect_target_launch_browser_probe",
                    return_value={
                        "enabled": True,
                        "applied": True,
                        "ok": True,
                        "current_url": "https://check.torproject.org/",
                        "same_host_as_target": True,
                    },
                ) as target_probe,
                patch(
                    "launch_torfast_browser.wait_for_existing_service_ready_in_log",
                    return_value={
                        "ok": True,
                        "seconds": 0.0,
                        "polls": 1,
                        "reused_service": True,
                    },
                ),
                patch("launch_torfast_browser.stop_process_tree"),
                patch("launch_torfast_browser.describe_seed", return_value={}),
                patch(
                    "launch_torfast_browser.describe_browser_startup_seed",
                    return_value={},
                ),
                patch("builtins.print"),
                patch.dict(
                    "os.environ",
                    {"TORFAST_ENABLE_TARGET_STREAM_PROOF": "1"},
                    clear=False,
                ),
            ):
                exit_code = launch_browser_with_c_tor(plan)

        self.assertEqual(exit_code, 0)
        serial_wait.assert_not_called()
        navigate.assert_not_called()
        target_probe.assert_called_once()
        self.assertEqual(
            plan["browser"]["target_load_probe"]["current_url"],
            "https://check.torproject.org/",
        )
        self.assertTrue(
            plan["managed_open_browser_overlap"]["target_load_probe"][
                "same_host_as_target"
            ]
        )

    def test_launch_browser_with_c_tor_skips_duplicate_navigate_after_eager_target_navigation(
        self,
    ) -> None:
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
                "tor_log": str(paths.tor_log),
                "ready_gate": "socks_ready",
                "control_port": 29450,
                "control_cookie_path": str(paths.control_cookie_path),
            }
            paths.tor_service_json.write_text(json.dumps(service), encoding="utf-8")
            overlap_client = object()
            plan = {
                "browser_command": ["/tmp/firefox", "https://check.torproject.org/"],
                "browser_launch_gate": "tor_boot_95",
                "browser_launch_gate_requested": "auto",
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
                "managed_open_settle_enabled": False,
                "managed_open_browser_overlap_enabled": True,
                "managed_open_adaptive_general_circuit_wait_timeout_seconds": 0.126,
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
                    "launch_torfast_browser.maybe_wait_for_managed_open_general_circuit"
                ) as serial_wait,
                patch(
                    "launch_torfast_browser.start_managed_open_browser_overlap_session",
                    return_value=(
                        FakeProc(1357),
                        queue.Queue(),
                        overlap_client,
                        {
                            "enabled": True,
                            "applied": True,
                            "initial_url": "about:blank",
                            "launched_on_target_url": False,
                            "marionette_listener_enabled": True,
                            "marionette_session_used": True,
                            "marionette_port": 2828,
                            "eager_target_navigation_enabled": True,
                            "eager_target_navigation": {
                                "ok": True,
                                "seconds": 0.01,
                                "target_url": "https://check.torproject.org/",
                            },
                        },
                        service,
                        {
                            "enabled": True,
                            "applied": True,
                            "ok": True,
                            "matched": False,
                            "timed_out": False,
                            "seconds": 0.1,
                            "reason": "browser_startup_proceed",
                        },
                    ),
                ),
                patch(
                    "launch_torfast_browser.navigate_managed_open_browser_overlap_session",
                ) as navigate,
                patch(
                    "launch_torfast_browser.wait_for_browser_exit",
                    return_value={
                        "ok": True,
                        "exit_code": 0,
                        "timed_out": False,
                        "interrupted": False,
                    },
                ),
                patch(
                    "launch_torfast_browser.wait_for_existing_service_ready_in_log",
                    return_value={
                        "ok": True,
                        "seconds": 0.0,
                        "polls": 1,
                        "reused_service": True,
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
        serial_wait.assert_not_called()
        navigate.assert_not_called()
        self.assertEqual(
            plan["managed_open_browser_overlap"]["navigate"]["reason"],
            "eager_target_navigation",
        )
        self.assertTrue(
            plan["managed_open_browser_overlap"]["navigate"][
                "started_during_overlap_session"
            ]
        )

    def test_launch_browser_with_c_tor_skips_gate_wait_from_overlap_report(
        self,
    ) -> None:
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
                "tor_log": str(paths.tor_log),
                "ready_gate": "socks_ready",
                "control_port": 29450,
                "control_cookie_path": str(paths.control_cookie_path),
            }
            paths.tor_service_json.write_text(json.dumps(service), encoding="utf-8")
            plan = {
                "browser_command": ["/tmp/firefox", "https://check.torproject.org/"],
                "browser_launch_gate": "tor_boot_95",
                "browser_launch_gate_requested": "auto",
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
                "managed_open_settle_enabled": False,
                "managed_open_browser_overlap_enabled": True,
                "managed_open_adaptive_general_circuit_wait_timeout_seconds": 0.75,
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
                    "launch_torfast_browser.maybe_wait_for_managed_open_general_circuit"
                ) as serial_wait,
                patch(
                    "launch_torfast_browser.start_managed_open_browser_overlap_session",
                    return_value=(
                        FakeProc(1357),
                        queue.Queue(),
                        object(),
                        {
                            "enabled": True,
                            "applied": True,
                            "initial_url": "https://check.torproject.org/",
                        },
                        service,
                        {
                            "enabled": True,
                            "applied": True,
                            "ok": True,
                            "matched": False,
                            "timed_out": False,
                            "seconds": 0.25,
                            "reason": "browser_startup_proceed",
                            "browser_launch_gate_wait": {
                                "ok": True,
                                "seconds": 0.25,
                                "polls": 2,
                                "ready_via_control": True,
                                "ready_gate": "tor_boot_95",
                            },
                        },
                    ),
                ),
                patch(
                    "launch_torfast_browser.navigate_managed_open_browser_overlap_session",
                    return_value={"ok": True, "seconds": 0.01},
                ) as navigate,
                patch(
                    "launch_torfast_browser.wait_for_browser_exit",
                    return_value={
                        "ok": True,
                        "exit_code": 0,
                        "timed_out": False,
                        "interrupted": False,
                    },
                ),
                patch(
                    "launch_torfast_browser.wait_for_existing_service_ready_in_log",
                    return_value={
                        "ok": True,
                        "seconds": 0.0,
                        "polls": 1,
                        "reused_service": True,
                    },
                ) as wait_for_gate,
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
        serial_wait.assert_not_called()
        wait_for_gate.assert_called_once()
        self.assertEqual(wait_for_gate.call_args.kwargs["gate"], "tor_boot_100")
        navigate.assert_not_called()
        self.assertTrue(plan["tor_browser_launch_gate"]["ready_via_control"])

    def test_launch_browser_with_c_tor_uses_target_stream_activity_gate_for_eager_target_navigation(
        self,
    ) -> None:
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
                "tor_log": str(paths.tor_log),
                "ready_gate": "socks_ready",
                "control_port": 29450,
                "control_cookie_path": str(paths.control_cookie_path),
            }
            paths.tor_service_json.write_text(json.dumps(service), encoding="utf-8")
            plan = {
                "browser_command": ["/tmp/firefox", "https://check.torproject.org/"],
                "browser_launch_gate": "tor_boot_95",
                "browser_launch_gate_requested": "auto",
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
                "managed_open_settle_enabled": False,
                "managed_open_browser_overlap_enabled": True,
                "managed_open_adaptive_general_circuit_wait_timeout_seconds": 0.126,
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
                    "launch_torfast_browser.maybe_wait_for_managed_open_general_circuit"
                ) as serial_wait,
                patch(
                    "launch_torfast_browser.start_managed_open_browser_overlap_session",
                    return_value=(
                        FakeProc(1357),
                        queue.Queue(),
                        object(),
                        {
                            "enabled": True,
                            "applied": True,
                            "initial_url": "about:blank",
                            "launched_on_target_url": False,
                            "marionette_session_used": True,
                            "eager_target_navigation_enabled": True,
                            "eager_target_navigation": {
                                "ok": True,
                                "seconds": 0.01,
                                "target_url": "https://check.torproject.org/",
                            },
                        },
                        service,
                        {
                            "enabled": True,
                            "applied": True,
                            "ok": True,
                            "matched": False,
                            "timed_out": False,
                            "seconds": 0.126,
                            "reason": "target_stream_activity",
                            "browser_launch_gate_wait": {
                                "ok": True,
                                "seconds": 0.126,
                                "polls": 1,
                                "ready_gate": "tor_boot_95",
                                "ready_via_target_stream_activity": True,
                            },
                        },
                    ),
                ),
                patch(
                    "launch_torfast_browser.navigate_managed_open_browser_overlap_session",
                    return_value={"ok": True, "seconds": 0.01},
                ) as navigate,
                patch(
                    "launch_torfast_browser.wait_for_browser_exit",
                    return_value={
                        "ok": True,
                        "exit_code": 0,
                        "timed_out": False,
                        "interrupted": False,
                    },
                ),
                patch(
                    "launch_torfast_browser.wait_for_existing_service_ready_in_log",
                    return_value={
                        "ok": True,
                        "seconds": 0.0,
                        "polls": 1,
                        "reused_service": True,
                    },
                ) as wait_for_gate,
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
        serial_wait.assert_not_called()
        wait_for_gate.assert_called_once()
        self.assertEqual(wait_for_gate.call_args.kwargs["gate"], "tor_boot_100")
        navigate.assert_not_called()
        self.assertTrue(
            plan["tor_browser_launch_gate"]["ready_via_target_stream_activity"]
        )

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

    def test_reusable_managed_service_retries_transient_unreadable_json(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            paths = resolve_launch_paths(Path(tempdir) / "state-root")
            ensure_state_dirs(paths)
            desired_torrc = render_c_tor_torrc(
                port=19450,
                data_dir=paths.data_dir,
            )
            paths.torrc.write_text(desired_torrc, encoding="utf-8")
            paths.tor_service_json.write_text("{}", encoding="utf-8")
            service = {
                "pid": 2468,
                "port": 19450,
                "torrc": str(paths.torrc),
                "tor_log": str(paths.tor_log),
            }

            with (
                patch(
                    "launch_torfast_browser.json.loads",
                    side_effect=[
                        json.JSONDecodeError("transient", "{}", 0),
                        service,
                    ],
                ) as json_loads_mock,
                patch("launch_torfast_browser.process_is_alive", return_value=True),
                patch("launch_torfast_browser.port_is_open", return_value=True),
                patch("launch_torfast_browser.time.sleep") as sleep,
            ):
                reused = reusable_managed_tor_service(
                    paths,
                    desired_torrc=desired_torrc,
                    port=19450,
                )

        self.assertEqual(reused, service)
        self.assertEqual(json_loads_mock.call_count, 2)
        sleep.assert_called_once_with(0.01)

    def test_wait_for_existing_service_ready_uses_control_progress(self) -> None:
        class FakeControlClient:
            def __init__(self) -> None:
                self.commands: list[str] = []
                self.closed = False

            def command(self, command: str) -> str:
                self.commands.append(command)
                return (
                    '250-status/bootstrap-phase=NOTICE BOOTSTRAP '
                    'PROGRESS=95 TAG=circuit_create '
                    'SUMMARY="Establishing a Tor circuit"\r\n'
                    "250 OK\r\n"
                )

            def close(self) -> None:
                self.closed = True

        fake_client = FakeControlClient()
        with (
            patch("launch_torfast_browser.process_is_alive", return_value=True),
            patch("launch_torfast_browser.tail_lines", return_value=[]),
            patch(
                "launch_torfast_browser.TorControlClient.connect",
                return_value=fake_client,
            ) as connect,
            patch.dict(
                "launch_torfast_browser.os.environ",
                {"TORFAST_ENABLE_PERSISTENT_CONTROL_WAIT": "1"},
                clear=False,
            ),
            patch("launch_torfast_browser.time.sleep") as sleep,
        ):
            result = wait_for_existing_service_ready_in_log(
                pid=1234,
                log_path=Path("/tmp/tor.log"),
                timeout=1.0,
                gate="tor_boot_95",
                control_port=29050,
                control_cookie_path="/tmp/control_auth_cookie",
                ready_text=browser_launch_gate_ready_text("tor_boot_95"),
                process_name="tor",
            )

        self.assertTrue(result["ok"])
        self.assertTrue(result["ready_via_control"])
        self.assertEqual(result["polls"], 1)
        self.assertEqual(result["control_bootstrap_phase"]["progress"], 95)
        self.assertEqual(fake_client.commands, ["GETINFO status/bootstrap-phase"])
        self.assertTrue(fake_client.closed)
        connect.assert_called_once()
        sleep.assert_not_called()

    def test_wait_for_existing_service_ready_reuses_control_client_across_polls(
        self,
    ) -> None:
        class FakeControlClient:
            def __init__(self) -> None:
                self.replies = [
                    (
                        '250-status/bootstrap-phase=NOTICE BOOTSTRAP '
                        'PROGRESS=90 TAG=ap_handshake_done '
                        'SUMMARY="Handshake finished with a relay to build circuits"\r\n'
                        "250 OK\r\n"
                    ),
                    (
                        '250-status/bootstrap-phase=NOTICE BOOTSTRAP '
                        'PROGRESS=95 TAG=circuit_create '
                        'SUMMARY="Establishing a Tor circuit"\r\n'
                        "250 OK\r\n"
                    ),
                ]
                self.commands: list[str] = []
                self.closed = False

            def command(self, command: str) -> str:
                self.commands.append(command)
                if not self.replies:
                    raise EOFError("no more replies")
                return self.replies.pop(0)

            def close(self) -> None:
                self.closed = True

        fake_client = FakeControlClient()
        monotonic_values = iter([0.0, 0.0, 0.1, 0.1])
        with (
            patch("launch_torfast_browser.process_is_alive", return_value=True),
            patch("launch_torfast_browser.tail_lines", return_value=[]),
            patch(
                "launch_torfast_browser.TorControlClient.connect",
                return_value=fake_client,
            ) as connect,
            patch.dict(
                "launch_torfast_browser.os.environ",
                {"TORFAST_ENABLE_PERSISTENT_CONTROL_WAIT": "1"},
                clear=False,
            ),
            patch(
                "launch_torfast_browser.time.monotonic",
                side_effect=lambda: next(monotonic_values),
            ),
            patch("launch_torfast_browser.time.time", return_value=time.time()),
            patch("launch_torfast_browser.time.sleep") as sleep,
        ):
            result = wait_for_existing_service_ready_in_log(
                pid=1234,
                log_path=Path("/tmp/tor.log"),
                timeout=1.0,
                gate="tor_boot_95",
                control_port=29050,
                control_cookie_path="/tmp/control_auth_cookie",
                ready_text=browser_launch_gate_ready_text("tor_boot_95"),
                process_name="tor",
            )

        self.assertTrue(result["ok"])
        self.assertTrue(result["ready_via_control"])
        self.assertEqual(result["polls"], 2)
        self.assertEqual(
            fake_client.commands,
            [
                "GETINFO status/bootstrap-phase",
                "GETINFO status/bootstrap-phase",
            ],
        )
        self.assertTrue(fake_client.closed)
        connect.assert_called_once()
        sleep.assert_called_once_with(0.05)

    def test_wait_for_existing_service_ready_can_use_refreshed_service_metadata(
        self,
    ) -> None:
        refreshed_service = {
            "pid": 1234,
            "tor_log": "/tmp/tor.log",
            "ready_gate": "tor_boot_95",
            "ready_epoch_ms": 1700000000000.0,
            "ready_monotonic_seconds": 123.456,
        }
        with (
            patch("launch_torfast_browser.process_is_alive", return_value=True),
            patch("launch_torfast_browser.tail_lines", return_value=[]),
            patch(
                "launch_torfast_browser.should_refresh_managed_service_metadata_wait",
                return_value=True,
            ),
            patch(
                "launch_torfast_browser.refresh_matching_managed_service",
                return_value=refreshed_service,
            ) as refresh,
            patch("launch_torfast_browser.control_ready_for_gate") as control_ready,
            patch("launch_torfast_browser.TorControlClient.connect") as connect,
            patch("launch_torfast_browser.time.sleep") as sleep,
        ):
            result = wait_for_existing_service_ready_in_log(
                pid=1234,
                log_path=Path("/tmp/tor.log"),
                timeout=1.0,
                gate="tor_boot_95",
                control_port=29050,
                control_cookie_path="/tmp/control_auth_cookie",
                service_path=Path("/tmp/tor-service.json"),
                expected_service={"pid": 1234, "tor_log": "/tmp/tor.log"},
                ready_text=browser_launch_gate_ready_text("tor_boot_95"),
                process_name="tor",
            )

        self.assertTrue(result["ok"])
        self.assertTrue(result["ready_via_service_metadata"])
        self.assertEqual(result["polls"], 1)
        self.assertEqual(result["ready_epoch_ms"], 1700000000000.0)
        refresh.assert_called_once_with(
            Path("/tmp/tor-service.json"),
            expected_service={"pid": 1234, "tor_log": "/tmp/tor.log"},
        )
        control_ready.assert_not_called()
        connect.assert_not_called()
        sleep.assert_not_called()

    def test_wait_for_existing_service_ready_prefers_promoted_metadata_over_log(
        self,
    ) -> None:
        ready_text = browser_launch_gate_ready_text("tor_boot_95")
        refreshed_service = {
            "pid": 1234,
            "tor_log": "/tmp/tor.log",
            "ready_gate": "tor_boot_95",
            "ready_epoch_ms": 1700000000000.0,
            "ready_monotonic_seconds": 123.456,
        }
        expected_service = {
            "pid": 1234,
            "tor_log": "/tmp/tor.log",
            "runtime_helper_gate_promoter_requested": True,
        }
        with (
            patch("launch_torfast_browser.process_is_alive", return_value=True),
            patch(
                "launch_torfast_browser.tail_lines",
                return_value=[ready_text],
            ),
            patch(
                "launch_torfast_browser.should_refresh_managed_service_metadata_wait",
                return_value=True,
            ),
            patch(
                "launch_torfast_browser.refresh_matching_managed_service",
                return_value=refreshed_service,
            ) as refresh,
            patch("launch_torfast_browser.control_ready_for_gate") as control_ready,
            patch("launch_torfast_browser.TorControlClient.connect") as connect,
            patch("launch_torfast_browser.time.sleep") as sleep,
        ):
            result = wait_for_existing_service_ready_in_log(
                pid=1234,
                log_path=Path("/tmp/tor.log"),
                timeout=1.0,
                gate="tor_boot_95",
                control_port=29050,
                control_cookie_path="/tmp/control_auth_cookie",
                service_path=Path("/tmp/tor-service.json"),
                expected_service=expected_service,
                ready_text=ready_text,
                process_name="tor",
            )

        self.assertTrue(result["ok"])
        self.assertTrue(result["ready_via_service_metadata"])
        self.assertEqual(result["polls"], 1)
        refresh.assert_called_once_with(
            Path("/tmp/tor-service.json"),
            expected_service=expected_service,
        )
        control_ready.assert_not_called()
        connect.assert_not_called()
        sleep.assert_not_called()

    def test_wait_for_existing_service_ready_keeps_log_priority_without_promoter(
        self,
    ) -> None:
        ready_text = browser_launch_gate_ready_text("tor_boot_95")
        with (
            patch("launch_torfast_browser.process_is_alive", return_value=True),
            patch(
                "launch_torfast_browser.tail_lines",
                return_value=[ready_text],
            ),
            patch(
                "launch_torfast_browser.should_refresh_managed_service_metadata_wait",
                return_value=True,
            ),
            patch(
                "launch_torfast_browser.refresh_matching_managed_service",
                return_value={
                    "pid": 1234,
                    "tor_log": "/tmp/tor.log",
                    "ready_gate": "tor_boot_95",
                    "ready_epoch_ms": 1700000000000.0,
                    "ready_monotonic_seconds": 123.456,
                },
            ) as refresh,
            patch("launch_torfast_browser.control_ready_for_gate") as control_ready,
            patch("launch_torfast_browser.TorControlClient.connect") as connect,
            patch("launch_torfast_browser.time.sleep") as sleep,
        ):
            result = wait_for_existing_service_ready_in_log(
                pid=1234,
                log_path=Path("/tmp/tor.log"),
                timeout=1.0,
                gate="tor_boot_95",
                control_port=29050,
                control_cookie_path="/tmp/control_auth_cookie",
                service_path=Path("/tmp/tor-service.json"),
                expected_service={"pid": 1234, "tor_log": "/tmp/tor.log"},
                ready_text=ready_text,
                process_name="tor",
            )

        self.assertTrue(result["ok"])
        self.assertIsNone(result.get("ready_via_service_metadata"))
        refresh.assert_not_called()
        control_ready.assert_not_called()
        connect.assert_not_called()
        sleep.assert_not_called()

    def test_wait_for_existing_service_ready_can_disable_service_metadata_wait(
        self,
    ) -> None:
        with (
            patch("launch_torfast_browser.process_is_alive", return_value=True),
            patch("launch_torfast_browser.tail_lines", return_value=[]),
            patch(
                "launch_torfast_browser.should_refresh_managed_service_metadata_wait",
                return_value=True,
            ),
            patch(
                "launch_torfast_browser.refresh_matching_managed_service",
                return_value={
                    "pid": 1234,
                    "tor_log": "/tmp/tor.log",
                    "ready_gate": "tor_boot_95",
                },
            ) as refresh,
            patch(
                "launch_torfast_browser.control_ready_for_gate",
                return_value={
                    "ok": True,
                    "progress": 95,
                    "tag": "circuit_create",
                    "summary": "Establishing a Tor circuit",
                },
            ) as control_ready,
            patch.dict(
                "launch_torfast_browser.os.environ",
                {MANAGED_SERVICE_METADATA_WAIT_DISABLED_ENV: "1"},
                clear=False,
            ),
            patch("launch_torfast_browser.time.sleep") as sleep,
        ):
            result = wait_for_existing_service_ready_in_log(
                pid=1234,
                log_path=Path("/tmp/tor.log"),
                timeout=1.0,
                gate="tor_boot_95",
                control_port=29050,
                control_cookie_path="/tmp/control_auth_cookie",
                service_path=Path("/tmp/tor-service.json"),
                expected_service={"pid": 1234, "tor_log": "/tmp/tor.log"},
                ready_text=browser_launch_gate_ready_text("tor_boot_95"),
                process_name="tor",
            )

        self.assertTrue(result["ok"])
        self.assertTrue(result["ready_via_control"])
        refresh.assert_not_called()
        control_ready.assert_called_once()
        sleep.assert_not_called()

    def test_wait_for_existing_service_ready_can_disable_persistent_control_wait(
        self,
    ) -> None:
        with (
            patch("launch_torfast_browser.process_is_alive", return_value=True),
            patch("launch_torfast_browser.tail_lines", return_value=[]),
            patch(
                "launch_torfast_browser.control_ready_for_gate",
                return_value={
                    "ok": True,
                    "progress": 95,
                    "tag": "circuit_create",
                    "summary": "Establishing a Tor circuit",
                },
            ) as control_ready,
            patch("launch_torfast_browser.TorControlClient.connect") as connect,
            patch.dict(
                "launch_torfast_browser.os.environ",
                {"TORFAST_DISABLE_PERSISTENT_CONTROL_WAIT": "1"},
                clear=False,
            ),
            patch("launch_torfast_browser.time.sleep") as sleep,
        ):
            result = wait_for_existing_service_ready_in_log(
                pid=1234,
                log_path=Path("/tmp/tor.log"),
                timeout=1.0,
                gate="tor_boot_95",
                control_port=29050,
                control_cookie_path="/tmp/control_auth_cookie",
                ready_text=browser_launch_gate_ready_text("tor_boot_95"),
                process_name="tor",
            )

        self.assertTrue(result["ok"])
        self.assertTrue(result["ready_via_control"])
        control_ready.assert_called_once()
        connect.assert_not_called()
        sleep.assert_not_called()

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

    def test_resolve_managed_browser_launch_gate_keeps_reused_network_open_at_95(self) -> None:
        gate = resolve_managed_browser_launch_gate(
            requested_gate=DEFAULT_BROWSER_LAUNCH_GATE,
            url="https://check.torproject.org/",
            start_managed_tor_only=False,
            reused_tor_service={"pid": 1234},
        )

        self.assertEqual(gate, "tor_boot_95")

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
        self.assertFalse(
            browser_runtime_reset_requested(
                leave_tor_running=True,
                reuse_tor_if_running=True,
                start_managed_tor_only=False,
                reuse_prestarted_browser=True,
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

    def test_wait_for_browser_exit_records_target_stream_snapshot(self) -> None:
        class FakeControlClient:
            def __init__(self) -> None:
                self.closed = False

            def close(self) -> None:
                self.closed = True

        proc = subprocess.Popen(
            ["/bin/sh", "-c", "sleep 0.12"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        client = FakeControlClient()
        try:
            with (
                patch(
                    "launch_torfast_browser.TorControlClient.connect",
                    return_value=client,
                ),
                patch(
                    "launch_torfast_browser.read_user_stream_snapshot_with_client",
                    return_value={
                        "ok": True,
                        "observed_stream_count": 1,
                        "user_stream_count": 1,
                        "targets": ["check.torproject.org:443"],
                    },
                ),
            ):
                result = wait_for_browser_exit(
                    proc=proc,
                    lines=queue.Queue(),
                    timeout_seconds=1.0,
                    control_port=29050,
                    control_cookie_path="/tmp/control_auth_cookie",
                    target_url="https://check.torproject.org/",
                    target_stream_proof_enabled=True,
                    target_stream_poll_interval_seconds=0.0,
                )
        finally:
            proc.kill()
            proc.wait()
            if proc.stdout is not None:
                proc.stdout.close()

        self.assertTrue(result["ok"])
        self.assertTrue(result["target_stream_proof_enabled"])
        self.assertGreaterEqual(result["target_stream_probe_polls"], 1)
        self.assertEqual(
            result["target_stream_snapshot"]["targets"],
            ["check.torproject.org:443"],
        )
        self.assertTrue(client.closed)


if __name__ == "__main__":
    unittest.main()
