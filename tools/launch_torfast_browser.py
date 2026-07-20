#!/usr/bin/env python3
"""Launch the current best proven fast, equal-quality Tor Browser path."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import queue
import re
import signal
import shutil
import socket
import subprocess
import sys
import threading
import time
from urllib.parse import urlparse

TOOLS_ROOT = Path(__file__).resolve().parent
REPO_ROOT = Path(__file__).resolve().parents[1]
for import_root in (TOOLS_ROOT, REPO_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from torfast.control import (
    TorControlClient,
    read_general_circuit_snapshot,
    read_general_circuit_snapshot_with_client,
    read_user_stream_snapshot_with_client,
    user_stream_snapshot_observed,
    wait_for_general_circuits,
)


DEFAULT_BROWSER_BIN = "tmp/browser/Tor Browser.app/Contents/MacOS/firefox"
DEFAULT_TOR_BIN = "tmp/browser/Tor Browser.app/Contents/MacOS/Tor/tor"
DEFAULT_STATE_ROOT = "tmp/torfast-browser"
DEFAULT_C_TOR_DIR_CACHE_SEED_ROOT = REPO_ROOT / "tmp" / "torfast-c-tor-dir-cache-seed"
DEFAULT_BROWSER_STARTUP_SEED_ROOT = (
    REPO_ROOT / "tmp" / "torfast-browser-startup-seed"
)
DEFAULT_PREF_CACHE_DIR = REPO_ROOT / "tmp" / "browser-default-prefs-cache"
DEFAULT_URL = "about:tor"
DEFAULT_BROWSER_LAUNCH_GATE = "auto"
DEFAULT_MANAGED_OPEN_SETTLE_SECONDS = 1.85
MANAGED_OPEN_ADAPTIVE_GENERAL_CIRCUIT_WAIT_POLL_INTERVAL_SECONDS = 0.05
MANAGED_OPEN_BROWSER_OVERLAP_MARIONETTE_PORT = 2828
WARM_BROWSER_PRESTART_MARIONETTE_PORT = 2828
HOT_PATH_STATUS_CACHE_DISABLED_ENV = "TORFAST_DISABLE_HOT_PATH_STATUS_CACHE"
ASYNC_BROWSER_RESET_DISABLED_ENV = "TORFAST_DISABLE_ASYNC_BROWSER_RESET"
PERSISTENT_CONTROL_WAIT_ENABLED_ENV = "TORFAST_ENABLE_PERSISTENT_CONTROL_WAIT"
PERSISTENT_CONTROL_WAIT_DISABLED_ENV = "TORFAST_DISABLE_PERSISTENT_CONTROL_WAIT"
CONTROL_BOOTSTRAP_PROBE_DISABLED_ENV = "TORFAST_DISABLE_CONTROL_BOOTSTRAP_PROBE"
MANAGED_SERVICE_METADATA_WAIT_DISABLED_ENV = (
    "TORFAST_DISABLE_MANAGED_SERVICE_METADATA_WAIT"
)
TARGET_STREAM_PROOF_ENABLED_ENV = "TORFAST_ENABLE_TARGET_STREAM_PROOF"
BROWSER_RUNTIME_QUALITY_PROOF_ENABLED_ENV = (
    "TORFAST_ENABLE_BROWSER_RUNTIME_QUALITY_PROOF"
)
MANAGED_SERVICE_METADATA_WAIT_START_POLL = 5
MANAGED_SERVICE_METADATA_WAIT_POLL_STRIDE = 5
PROMOTED_SERVICE_METADATA_WAIT_START_POLL = 2
PROMOTED_SERVICE_METADATA_WAIT_POLL_STRIDE = 1
REQUIRED_DEFAULT_PREFS = {
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
}
DEFAULT_PREF_KEYS = list(REQUIRED_DEFAULT_PREFS)
BROWSER_LAUNCH_GATE_READY_TEXT = {
    "socks_ready": "Opened Socks listener connection (ready)",
    "tor_boot_90": "Bootstrapped 90% (ap_handshake_done): Handshake finished with a relay to build circuits",
    "tor_boot_95": "Bootstrapped 95% (circuit_create): Establishing a Tor circuit",
    "tor_boot_100": "Bootstrapped 100%",
}
BROWSER_LAUNCH_GATE_ORDER = {
    "socks_ready": 0,
    "tor_boot_90": 1,
    "tor_boot_95": 2,
    "tor_boot_100": 3,
}


class LaunchError(RuntimeError):
    """Raised when the launcher cannot safely proceed."""


PRIVATE_DIR_MODE = 0o700


def gate_reaches_dir_cache_seed_refresh_threshold(gate: object) -> bool:
    if not isinstance(gate, str):
        return False
    return BROWSER_LAUNCH_GATE_ORDER.get(gate, -1) >= BROWSER_LAUNCH_GATE_ORDER[
        "tor_boot_95"
    ]


def start_managed_dir_cache_seed_refresh_gate(
    plan: dict[str, object],
) -> str | None:
    tor_managed_ready = plan.get("tor_managed_ready")
    if isinstance(tor_managed_ready, dict) and tor_managed_ready.get("ok"):
        gate = tor_managed_ready.get("gate")
        if isinstance(gate, str):
            return gate
    tor_boot = plan.get("tor_boot")
    if isinstance(tor_boot, dict) and tor_boot.get("ok"):
        return "tor_boot_100"
    tor_browser_launch_gate = plan.get("tor_browser_launch_gate")
    if (
        isinstance(tor_browser_launch_gate, dict)
        and tor_browser_launch_gate.get("ok")
    ):
        gate = tor_browser_launch_gate.get("gate")
        if isinstance(gate, str):
            return gate
    return None


PROCESS_POLL_INTERVAL_SECONDS = 0.05
JSON_READ_RETRIES = 3
JSON_READ_RETRY_SECONDS = 0.01
C_TOR_SOCKS_FLAGS = ["IsolateSOCKSAuth"]
SEED_MANIFEST_NAME = "seed.json"
SEED_FILES_DIRNAME = "files"
STAGED_BROWSER_RUNTIME_PREFIX = ".stale-"
BOOT_SIGNAL_SUBSTRINGS = (
    "looking for a consensus",
    "downloading certificates for consensus",
    "downloading microdescriptors",
    "marked consensus usable",
    "directory is complete",
    "we have enough information to build circuits",
    "proxy now functional",
    "bootstrapped",
    "directory failure",
    "directory timed out",
    "notdirectory",
    "partial response",
    "partial retry chunking signal",
    "torfast dirclient timing",
    "torfast channel open timing",
    "torfast circuit selection build failed",
    "terminal summary",
    "warn",
)


@dataclass(frozen=True)
class LaunchPaths:
    state_root: Path
    data_dir: Path
    torrc: Path
    tor_log: Path
    tor_service_json: Path
    control_cookie_path: Path
    browser_home_dir: Path
    browser_profile_dir: Path
    launch_json: Path
    prestarted_browser_json: Path

    def as_dict(self) -> dict[str, str]:
        return {
            "state_root": str(self.state_root),
            "data_dir": str(self.data_dir),
            "torrc": str(self.torrc),
            "tor_log": str(self.tor_log),
            "tor_service_json": str(self.tor_service_json),
            "control_cookie_path": str(self.control_cookie_path),
            "browser_home_dir": str(self.browser_home_dir),
            "browser_profile_dir": str(self.browser_profile_dir),
            "launch_json": str(self.launch_json),
            "prestarted_browser_json": str(self.prestarted_browser_json),
        }


@dataclass
class BrowserRuntimeResetCleanupEntry:
    label: str | None
    staged_path: Path


@dataclass
class BrowserRuntimeResetCleanup:
    summary: dict[str, object]
    entries: list[BrowserRuntimeResetCleanupEntry]
    worker: threading.Thread | None = None


class ExistingBrowserProcess:
    def __init__(self, pid: int):
        self.pid = pid
        self.returncode: int | None = None

    def poll(self) -> int | None:
        if process_is_alive(self.pid):
            return None
        if self.returncode is None:
            self.returncode = 0
        return self.returncode

    def wait(self, timeout: float | None = None) -> int:
        deadline = None if timeout is None else time.monotonic() + timeout
        while self.poll() is None:
            if deadline is not None and time.monotonic() >= deadline:
                raise subprocess.TimeoutExpired(args=["browser"], timeout=timeout)
            time.sleep(0.05)
        return 0 if self.returncode is None else self.returncode


_DEFAULT_PREF_MEMORY_CACHE: dict[tuple[object, ...], dict[str, object]] = {}
_DIR_CACHE_SEED_STATUS_MEMORY_CACHE: dict[tuple[object, ...], dict[str, object]] = {}
_BROWSER_STARTUP_SEED_STATUS_MEMORY_CACHE: dict[
    tuple[object, ...], dict[str, object]
] = {}
_TORRC_QUALITY_MEMORY_CACHE: dict[tuple[object, ...], dict[str, object]] = {}


def hot_path_status_cache_enabled() -> bool:
    return not os.environ.get(HOT_PATH_STATUS_CACHE_DISABLED_ENV)


def async_browser_reset_enabled() -> bool:
    return not os.environ.get(ASYNC_BROWSER_RESET_DISABLED_ENV)


def managed_service_metadata_wait_enabled() -> bool:
    return os.environ.get(MANAGED_SERVICE_METADATA_WAIT_DISABLED_ENV) != "1"


def promoted_service_metadata_wait_requested(
    service: dict[str, object] | None,
) -> bool:
    return (
        isinstance(service, dict)
        and service.get("runtime_helper_gate_promoter_requested") is True
    )


def should_refresh_managed_service_metadata_wait(
    *,
    polls: int,
    expected_service: dict[str, object] | None = None,
) -> bool:
    if promoted_service_metadata_wait_requested(expected_service):
        if polls < PROMOTED_SERVICE_METADATA_WAIT_START_POLL:
            return False
        return (
            polls == PROMOTED_SERVICE_METADATA_WAIT_START_POLL
            or (polls - PROMOTED_SERVICE_METADATA_WAIT_START_POLL)
            % PROMOTED_SERVICE_METADATA_WAIT_POLL_STRIDE
            == 0
        )
    if polls < MANAGED_SERVICE_METADATA_WAIT_START_POLL:
        return False
    return (
        polls == MANAGED_SERVICE_METADATA_WAIT_START_POLL
        or (polls - MANAGED_SERVICE_METADATA_WAIT_START_POLL)
        % MANAGED_SERVICE_METADATA_WAIT_POLL_STRIDE
        == 0
    )


def path_stat_key(path: Path) -> tuple[bool, int | None, int | None]:
    try:
        stat_result = path.stat()
    except OSError:
        return (False, None, None)
    return (True, stat_result.st_mtime_ns, stat_result.st_size)


def cached_browser_default_pref_key(
    *,
    omni: Path,
    source_mtime_ns: int,
    source_size: int,
) -> tuple[object, ...]:
    return (
        str(omni),
        source_mtime_ns,
        source_size,
        str(DEFAULT_PREF_CACHE_DIR),
    )


def seed_status_cache_key(seed_root: Path) -> tuple[object, ...]:
    paths = resolve_seed_paths_for_status(seed_root)
    return (
        str(seed_root),
        *path_stat_key(paths["manifest_path"]),
        *path_stat_key(paths["files_dir"]),
    )


def browser_startup_seed_status_cache_key(seed_root: Path) -> tuple[object, ...]:
    manifest_path = seed_root / SEED_MANIFEST_NAME
    return (str(seed_root), *path_stat_key(manifest_path))


def torrc_quality_cache_key(torrc: Path) -> tuple[object, ...]:
    return (str(torrc), *path_stat_key(torrc))


def load_cached_default_prefs(
    *,
    omni: Path,
    source_mtime_ns: int,
    source_size: int,
) -> dict[str, object] | None:
    memory_cache_key = cached_browser_default_pref_key(
        omni=omni,
        source_mtime_ns=source_mtime_ns,
        source_size=source_size,
    )
    if hot_path_status_cache_enabled():
        cached = _DEFAULT_PREF_MEMORY_CACHE.get(memory_cache_key)
        if cached is not None:
            return cached
    if not DEFAULT_PREF_CACHE_DIR.exists():
        return None
    for cache_path in DEFAULT_PREF_CACHE_DIR.glob("*.json"):
        try:
            payload = json.loads(cache_path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        if payload.get("source") != str(omni):
            continue
        if payload.get("source_mtime_ns") != source_mtime_ns:
            continue
        if payload.get("source_size") != source_size:
            continue
        cached_prefs = payload.get("prefs")
        if not isinstance(cached_prefs, dict):
            continue
        result = {
            "ok": True,
            "source": str(omni),
            "prefs": {key: cached_prefs.get(key) for key in DEFAULT_PREF_KEYS},
            "cache_hit": True,
            "cache_path": str(cache_path),
        }
        if hot_path_status_cache_enabled():
            _DEFAULT_PREF_MEMORY_CACHE[memory_cache_key] = result
        return result
    return None


def read_browser_default_prefs(browser_bin: Path) -> dict[str, object]:
    contents_dir = browser_bin.parent.parent
    omni = contents_dir / "Resources" / "browser" / "omni.ja"
    if not omni.exists():
        return {"ok": False, "error": f"not found: {omni}"}
    try:
        source_stat = omni.stat()
    except OSError as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    cache_key = cached_browser_default_pref_key(
        omni=omni,
        source_mtime_ns=source_stat.st_mtime_ns,
        source_size=source_stat.st_size,
    )
    if hot_path_status_cache_enabled():
        cached = _DEFAULT_PREF_MEMORY_CACHE.get(cache_key)
        if cached is not None:
            return cached
    cached = load_cached_default_prefs(
        omni=omni,
        source_mtime_ns=source_stat.st_mtime_ns,
        source_size=source_stat.st_size,
    )
    if cached is not None:
        return cached
    from torfast.browser_defaults import (
        read_browser_default_prefs as _read_browser_default_prefs,
    )

    result = _read_browser_default_prefs(browser_bin)
    if hot_path_status_cache_enabled():
        _DEFAULT_PREF_MEMORY_CACHE[cache_key] = result
    return result


def validate_default_prefs(default_prefs: dict[str, object]) -> dict[str, object]:
    failures: list[str] = []
    if not default_prefs.get("ok"):
        failures.append(str(default_prefs.get("error", "default prefs missing")))
        return {"ok": False, "failures": failures}
    prefs = default_prefs.get("prefs", {})
    if not isinstance(prefs, dict):
        return {"ok": False, "failures": ["default prefs payload is not a dict"]}
    for key, expected in REQUIRED_DEFAULT_PREFS.items():
        actual = prefs.get(key)
        if actual != expected:
            failures.append(f"{key}: expected {expected!r}, got {actual!r}")
    return {"ok": not failures, "failures": failures}


def resolve_seed_paths_for_status(seed_root: Path) -> dict[str, Path]:
    return {
        "manifest_path": seed_root / SEED_MANIFEST_NAME,
        "files_dir": seed_root / SEED_FILES_DIRNAME,
    }


def read_seed_manifest(seed_root: Path) -> dict[str, object] | None:
    manifest_path = resolve_seed_paths_for_status(seed_root)["manifest_path"]
    if not manifest_path.exists():
        return None
    try:
        payload = json.loads(manifest_path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def describe_seed(seed_root: Path) -> dict[str, object]:
    cache_key = seed_status_cache_key(seed_root)
    if hot_path_status_cache_enabled():
        cached = _DIR_CACHE_SEED_STATUS_MEMORY_CACHE.get(cache_key)
        if cached is not None:
            return cached
    paths = resolve_seed_paths_for_status(seed_root)
    manifest_path = paths["manifest_path"]
    files_dir = paths["files_dir"]
    manifest = read_seed_manifest(seed_root)
    available_files = sorted(
        path.name for path in files_dir.iterdir()
        if files_dir.exists() and path.is_file()
    ) if files_dir.exists() else []
    result = {
        "seed_root": str(seed_root),
        "manifest_json": str(manifest_path),
        "present": manifest is not None,
        "available_files": available_files,
        "manifest": manifest,
    }
    if hot_path_status_cache_enabled():
        _DIR_CACHE_SEED_STATUS_MEMORY_CACHE[cache_key] = result
    return result


def browser_startup_seed_files(manifest: dict[str, object] | None) -> list[str]:
    if not isinstance(manifest, dict):
        return []
    files = manifest.get("files")
    if not isinstance(files, list):
        return []
    resolved: list[str] = []
    for entry in files:
        if not isinstance(entry, dict):
            continue
        path = entry.get("path")
        if isinstance(path, str) and path:
            resolved.append(path)
    return resolved


def describe_browser_startup_seed(seed_root: Path) -> dict[str, object]:
    cache_key = browser_startup_seed_status_cache_key(seed_root)
    if hot_path_status_cache_enabled():
        cached = _BROWSER_STARTUP_SEED_STATUS_MEMORY_CACHE.get(cache_key)
        if cached is not None:
            return cached
    manifest = read_seed_manifest(seed_root)
    result = {
        "exists": seed_root.exists(),
        "seed_root": str(seed_root),
        "manifest": manifest,
        "distribution_app_profile_extension_ids": (
            manifest.get("distribution_app_profile_extension_ids", [])
            if isinstance(manifest, dict)
            else []
        ),
        "files": browser_startup_seed_files(manifest),
    }
    if hot_path_status_cache_enabled():
        _BROWSER_STARTUP_SEED_STATUS_MEMORY_CACHE[cache_key] = result
    return result


def apply_seed_to_data_dir(data_dir: Path, seed_root: Path) -> dict[str, object]:
    from torfast.dir_cache_seed import apply_seed_to_data_dir as _apply_seed_to_data_dir

    return _apply_seed_to_data_dir(data_dir, seed_root)


def update_seed_from_data_dir(data_dir: Path, seed_root: Path) -> dict[str, object]:
    from torfast.dir_cache_seed import (
        update_seed_from_data_dir as _update_seed_from_data_dir,
    )

    return _update_seed_from_data_dir(data_dir, seed_root)


def apply_browser_startup_seed_to_profile(
    profile_dir: Path,
    seed_root: Path,
) -> dict[str, object]:
    from torfast.browser_startup_seed import (
        apply_seed_to_profile as _apply_browser_startup_seed_to_profile,
    )

    return _apply_browser_startup_seed_to_profile(profile_dir, seed_root)


def update_browser_startup_seed_from_profile(
    profile_dir: Path,
    seed_root: Path,
) -> dict[str, object]:
    from torfast.browser_startup_seed import (
        update_seed_from_profile as _update_browser_startup_seed_from_profile,
    )

    return _update_browser_startup_seed_from_profile(profile_dir, seed_root)


def apply_ui_theme_to_browser_profile(profile_dir: Path) -> dict[str, object]:
    from torfast.theme import apply_ui_theme_to_profile as _apply_ui_theme_to_profile

    return _apply_ui_theme_to_profile(profile_dir)


def read_torrc_quality(torrc: Path) -> dict[str, object]:
    cache_key = torrc_quality_cache_key(torrc)
    if hot_path_status_cache_enabled():
        cached = _TORRC_QUALITY_MEMORY_CACHE.get(cache_key)
        if cached is not None:
            return cached
    text = torrc.read_text(errors="replace") if torrc.exists() else ""
    socks_lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip().startswith("SocksPort ")
    ]
    result = {
        "path": str(torrc),
        "socks_lines": socks_lines,
        "isolate_socks_auth": any("IsolateSOCKSAuth" in line for line in socks_lines),
    }
    if hot_path_status_cache_enabled():
        _TORRC_QUALITY_MEMORY_CACHE[cache_key] = result
    return result


def boot_signal_lines(lines: list[str]) -> list[str]:
    signals = []
    for line in lines:
        lower = line.lower()
        if any(marker in lower for marker in BOOT_SIGNAL_SUBSTRINGS):
            signals.append(line)
    return signals


def read_lines(proc: subprocess.Popen[str], lines: queue.Queue[str]) -> None:
    assert proc.stdout is not None
    for line in proc.stdout:
        lines.put(line.rstrip())


def wait_for_line(
    proc: subprocess.Popen[str],
    lines: queue.Queue[str],
    *,
    timeout: float,
    ready_text: str,
    process_name: str,
) -> dict[str, object]:
    started = time.monotonic()
    seen: list[str] = []
    while time.monotonic() - started < timeout:
        if proc.poll() is not None:
            return {
                "ok": False,
                "error": f"{process_name} exited with code {proc.returncode}",
                "lines": seen[-80:],
                "signal_lines": boot_signal_lines(seen),
            }
        try:
            line = lines.get(timeout=PROCESS_POLL_INTERVAL_SECONDS)
        except queue.Empty:
            continue
        seen.append(line)
        if ready_text in line:
            ready_monotonic = time.monotonic()
            return {
                "ok": True,
                "seconds": round(ready_monotonic - started, 3),
                "ready_epoch_ms": round(time.time() * 1000, 3),
                "ready_monotonic_seconds": round(ready_monotonic, 6),
                "lines": seen[-80:],
                "signal_lines": boot_signal_lines(seen),
            }
    return {
        "ok": False,
        "error": "bootstrap timeout",
        "lines": seen[-80:],
        "signal_lines": boot_signal_lines(seen),
    }


def stop_process(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=10.0)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=10.0)


def stop_process_tree(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        proc.wait(timeout=10.0)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.wait(timeout=10.0)


def port_is_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.2):
            return True
    except OSError:
        return False


def drain_queue(lines: queue.Queue[str]) -> list[str]:
    drained: list[str] = []
    while True:
        try:
            drained.append(lines.get_nowait())
        except queue.Empty:
            return drained


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--browser-bin", default=DEFAULT_BROWSER_BIN)
    parser.add_argument("--tor-bin", default=DEFAULT_TOR_BIN)
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--port", type=int, default=19450)
    parser.add_argument("--state-root", default=DEFAULT_STATE_ROOT)
    parser.add_argument(
        "--conflux-client-ux",
        choices=("latency", "throughput", "throughput_lowmem"),
        help=(
            "lab-only official C Tor Conflux UX override; omit to keep the "
            "current proven default auto behavior"
        ),
    )
    parser.add_argument(
        "--browser-timeout",
        type=float,
        default=0.0,
        help=(
            "seconds to keep the browser open before the launcher stops it; "
            "default 0 waits until the browser exits"
        ),
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="launch the browser in headless mode",
    )
    parser.add_argument(
        "--leave-tor-running",
        action="store_true",
        help="keep the managed C Tor process running after the browser exits",
    )
    parser.add_argument(
        "--reuse-tor-if-running",
        action="store_true",
        help="reuse an existing managed C Tor process under the same state root",
    )
    parser.add_argument(
        "--stop-managed-tor",
        action="store_true",
        help="stop the managed C Tor process under the selected state root and exit",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="write the launch plan and exit without starting Tor or the browser",
    )
    parser.add_argument(
        "--skip-browser-default-pref-check",
        action="store_true",
        help="skip the guard that verifies the browser ships Tor Browser defaults",
    )
    parser.add_argument(
        "--browser-launch-gate",
        choices=(DEFAULT_BROWSER_LAUNCH_GATE, *BROWSER_LAUNCH_GATE_READY_TEXT),
        default=DEFAULT_BROWSER_LAUNCH_GATE,
        help=(
            "browser launch gate; default auto keeps cold local about: pages "
            "on the fast SOCKS-ready gate, keeps cold network starts on the "
            "lighter tor_boot_95 gate, and lets managed warm-only prestarts "
            "return at socks_ready while reused network opens keep tor_boot_95"
        ),
    )
    parser.add_argument(
        "--stream-isolation-probe",
        action="store_true",
        help=(
            "default-off proof-only control-port probe that records browser "
            "SOCKS isolation metadata during launch"
        ),
    )
    parser.add_argument(
        "--gate-diagnostics",
        action="store_true",
        help=(
            "default-off proof mode: record reused-service gate-wait "
            "diagnostics during managed repeated-open runs"
        ),
    )
    parser.add_argument(
        "--stream-isolation-probe-timeout",
        type=float,
        default=3.0,
        help=(
            "seconds to wait for the optional stream-isolation probe to "
            "observe browser SOCKS streams"
        ),
    )
    managed_open_browser_overlap_group = parser.add_mutually_exclusive_group()
    managed_open_browser_overlap_group.add_argument(
        "--managed-open-browser-overlap",
        dest="no_managed_open_browser_overlap",
        action="store_false",
        help=(
            "enable overlapping reused-browser startup with the final managed "
            "tor_boot_95 gate wait before real navigation"
        ),
    )
    managed_open_browser_overlap_group.add_argument(
        "--no-managed-open-browser-overlap",
        dest="no_managed_open_browser_overlap",
        action="store_true",
        help="disable reused-browser startup overlap during managed open",
    )
    parser.add_argument(
        "--warm-browser-prestart",
        action="store_true",
        help=(
            "lab-only: after managed warm returns, start a fresh background "
            "browser on about:blank so the next reused open can navigate it "
            "instead of paying full browser startup again"
        ),
    )
    parser.add_argument(
        "--managed-open-adaptive-general-circuit-wait-timeout",
        type=float,
        default=0.0,
        help=(
            "lab-only: during a reused managed open, wait up to this many "
            "seconds for a built 3-hop general circuit, but only when the "
            "reused service is still below the normal reused network gate; "
            "with managed-open browser overlap enabled, only the hidden "
            "browser-startup window is spent before proceeding; 0 disables "
            "the wait"
        ),
    )
    parser.add_argument(
        "--start-managed-tor-only",
        action="store_true",
        help="start or reuse the managed C Tor service and exit without launching the browser",
    )
    parser.add_argument(
        "--dir-cache-seed-root",
        default=str(DEFAULT_C_TOR_DIR_CACHE_SEED_ROOT),
        help="shared cache-only seed root used to prime fresh C Tor data dirs",
    )
    parser.add_argument(
        "--no-dir-cache-seed",
        action="store_true",
        help="disable applying or updating the shared cache-only seed",
    )
    parser.add_argument(
        "--browser-startup-seed-root",
        default=str(DEFAULT_BROWSER_STARTUP_SEED_ROOT),
        help=(
            "shared startup-only Tor Browser profile seed used to prime fresh "
            "browser profiles with bundled extension startup artifacts"
        ),
    )
    managed_open_settle_group = parser.add_mutually_exclusive_group()
    managed_open_settle_group.add_argument(
        "--managed-open-settle",
        dest="no_managed_open_settle",
        action="store_false",
        help=(
            "opt in to the short managed-open settle window before reusing a "
            "freshly warmed managed Tor service for browser open"
        ),
    )
    managed_open_settle_group.add_argument(
        "--no-managed-open-settle",
        dest="no_managed_open_settle",
        action="store_true",
        help="disable the managed-open settle window",
    )
    browser_startup_seed_group = parser.add_mutually_exclusive_group()
    browser_startup_seed_group.add_argument(
        "--browser-startup-seed",
        dest="no_browser_startup_seed",
        action="store_false",
        help=(
            "enable applying and updating the shared browser startup seed; "
            "default is off because it is not yet a proven speed win"
        ),
    )
    browser_startup_seed_group.add_argument(
        "--no-browser-startup-seed",
        dest="no_browser_startup_seed",
        action="store_true",
        help="disable applying or updating the shared browser startup seed",
    )
    parser.add_argument(
        "--stock-ui",
        action="store_true",
        help=(
            "keep the stock Tor Browser chrome instead of the torfast zen UI "
            "theme; the theme is chrome-only userChrome.css that websites "
            "cannot read and that never changes viewport geometry"
        ),
    )
    parser.add_argument(
        "--profile-label",
        default=None,
        help="speed profile name recorded in the launch plan for receipts",
    )
    parser.set_defaults(
        no_managed_open_browser_overlap=False,
        no_managed_open_settle=True,
        no_browser_startup_seed=True,
    )
    args = parser.parse_args(argv)

    try:
        if args.browser_timeout < 0:
            raise LaunchError("--browser-timeout must be non-negative")
        if args.stream_isolation_probe_timeout < 0:
            raise LaunchError("--stream-isolation-probe-timeout must be non-negative")
        if args.managed_open_adaptive_general_circuit_wait_timeout < 0:
            raise LaunchError(
                "--managed-open-adaptive-general-circuit-wait-timeout must be "
                "non-negative"
            )

        browser_bin = Path(args.browser_bin).resolve()
        tor_bin = Path(args.tor_bin).resolve()
        state_root = Path(args.state_root).resolve()
        dir_cache_seed_root = Path(args.dir_cache_seed_root).resolve()
        browser_startup_seed_root = Path(args.browser_startup_seed_root).resolve()
        paths = resolve_launch_paths(state_root)
        control_port = managed_control_port(
            socks_port=args.port,
            leave_tor_running=args.leave_tor_running,
            reuse_tor_if_running=args.reuse_tor_if_running,
            start_managed_tor_only=args.start_managed_tor_only,
            stream_isolation_probe=args.stream_isolation_probe,
        )

        if args.stop_managed_tor:
            result = stop_managed_tor_service(paths)
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0 if result.get("ok") else 1

        if not tor_bin.exists():
            raise LaunchError(f"tor binary not found: {tor_bin}")
        if not browser_bin.exists():
            raise LaunchError(f"browser binary not found: {browser_bin}")

        desired_torrc = render_c_tor_torrc(
            port=args.port,
            data_dir=paths.data_dir,
            conflux_client_ux=args.conflux_client_ux,
            control_port=control_port,
            control_cookie_path=paths.control_cookie_path if control_port is not None else None,
        )
        reused_tor_service = None
        if args.reuse_tor_if_running:
            reused_tor_service = reusable_managed_tor_service(
                paths,
                desired_torrc=desired_torrc,
                port=args.port,
            )
        if reused_tor_service is None and port_is_open("127.0.0.1", args.port):
            raise LaunchError(f"port {args.port} is already in use")
        reused_prestarted_browser = reusable_prestarted_browser(paths)
        if reused_prestarted_browser is not None and not args.warm_browser_prestart:
            stop_prestarted_browser(paths)
            reused_prestarted_browser = None
        browser_launch_gate = resolve_managed_browser_launch_gate(
            requested_gate=args.browser_launch_gate,
            url=args.url,
            start_managed_tor_only=args.start_managed_tor_only,
            reused_tor_service=reused_tor_service,
        )

        browser_launch_skipped = (
            args.start_managed_tor_only and not args.warm_browser_prestart
        )

        if browser_launch_skipped:
            default_pref_proof = {
                "ok": True,
                "skipped": True,
                "reason": "browser launch skipped",
            }
            default_pref_check = {
                "ok": True,
                "skipped": True,
                "reason": "browser launch skipped",
            }
        else:
            default_pref_proof = read_browser_default_prefs(browser_bin)
            default_pref_check = validate_default_prefs(default_pref_proof)
            if (
                not args.skip_browser_default_pref_check
                and not default_pref_check.get("ok")
            ):
                failures = default_pref_check.get("failures", [])
                raise LaunchError(
                    "browser default pref check failed: " + "; ".join(failures)
                )

        ensure_state_dirs(paths)
        browser_runtime_reset, browser_runtime_reset_cleanup = reset_browser_runtime_dirs(
            paths,
            reset_requested=browser_runtime_reset_requested(
                leave_tor_running=args.leave_tor_running,
                reuse_tor_if_running=args.reuse_tor_if_running,
                start_managed_tor_only=args.start_managed_tor_only,
                reuse_prestarted_browser=(
                    isinstance(reused_prestarted_browser, dict)
                    and not args.start_managed_tor_only
                ),
            ),
        )
        if args.no_dir_cache_seed:
            dir_cache_seed_apply = {
                "ok": True,
                "applied": False,
                "reason": "disabled by flag",
                "seed_root": str(dir_cache_seed_root),
            }
        elif reused_tor_service is None:
            dir_cache_seed_apply = apply_seed_to_data_dir(
                paths.data_dir,
                dir_cache_seed_root,
            )
        else:
            dir_cache_seed_apply = {
                "ok": True,
                "applied": False,
                "reason": "reused managed tor service",
                "seed_root": str(dir_cache_seed_root),
            }
        if args.no_browser_startup_seed:
            browser_startup_seed_apply = {
                "ok": True,
                "applied": False,
                "reason": "disabled by flag",
                "seed_root": str(browser_startup_seed_root),
            }
        elif browser_launch_skipped:
            browser_startup_seed_apply = {
                "ok": True,
                "applied": False,
                "reason": "browser launch skipped",
                "seed_root": str(browser_startup_seed_root),
            }
        elif isinstance(reused_prestarted_browser, dict) and not args.start_managed_tor_only:
            browser_startup_seed_apply = {
                "ok": True,
                "applied": False,
                "reason": "reused prestarted browser",
                "seed_root": str(browser_startup_seed_root),
            }
        else:
            browser_startup_seed_apply = apply_browser_startup_seed_to_profile(
                paths.browser_profile_dir,
                browser_startup_seed_root,
            )
        if args.stock_ui:
            ui_theme_apply = {
                "ok": True,
                "applied": False,
                "theme": "stock",
                "reason": "stock ui requested",
            }
        elif browser_launch_skipped:
            ui_theme_apply = {
                "ok": True,
                "applied": False,
                "theme": "stock",
                "reason": "browser launch skipped",
            }
        elif (
            isinstance(reused_prestarted_browser, dict)
            and not args.start_managed_tor_only
        ):
            ui_theme_apply = {
                "ok": True,
                "applied": False,
                "theme": "zen",
                "reason": "reused prestarted browser profile keeps its theme",
            }
        else:
            ui_theme_apply = apply_ui_theme_to_browser_profile(
                paths.browser_profile_dir
            )
        if reused_tor_service is None:
            paths.torrc.write_text(desired_torrc)
        plan = build_launch_plan(
            browser_bin=browser_bin,
            tor_bin=tor_bin,
            paths=paths,
            port=args.port,
            url=args.url,
            headless=args.headless,
            browser_timeout=args.browser_timeout,
            browser_launch_gate=browser_launch_gate,
            browser_launch_gate_requested=args.browser_launch_gate,
            conflux_client_ux=args.conflux_client_ux,
            leave_tor_running=args.leave_tor_running,
            reuse_tor_if_running=args.reuse_tor_if_running,
            start_managed_tor_only=args.start_managed_tor_only,
            browser_runtime_reset=browser_runtime_reset,
            dir_cache_seed_root=dir_cache_seed_root,
            dir_cache_seed_apply=dir_cache_seed_apply,
            browser_startup_seed_root=browser_startup_seed_root,
            browser_startup_seed_apply=browser_startup_seed_apply,
            reused_tor_service=reused_tor_service,
            default_pref_proof=default_pref_proof,
            default_pref_check=default_pref_check,
            control_port=control_port,
            control_cookie_path=paths.control_cookie_path if control_port is not None else None,
            gate_diagnostics_enabled=args.gate_diagnostics,
            managed_open_settle_enabled=not args.no_managed_open_settle,
            managed_open_browser_overlap_enabled=(
                not args.no_managed_open_browser_overlap
            ),
            managed_open_adaptive_general_circuit_wait_timeout_seconds=(
                args.managed_open_adaptive_general_circuit_wait_timeout
            ),
            warm_browser_prestart_enabled=args.warm_browser_prestart,
            reused_prestarted_browser=reused_prestarted_browser,
            stream_isolation_probe=args.stream_isolation_probe,
            stream_isolation_probe_timeout=args.stream_isolation_probe_timeout,
            ui_theme_apply=ui_theme_apply,
            profile_label=args.profile_label,
        )

        if args.dry_run:
            finalize_browser_runtime_reset_cleanup(browser_runtime_reset_cleanup)
            write_plan(paths.launch_json, plan)
            print(f"wrote {paths.launch_json}")
            print(json.dumps(plan, indent=2, sort_keys=True))
            return 0

        return launch_browser_with_c_tor(
            plan,
            browser_runtime_reset_cleanup=browser_runtime_reset_cleanup,
        )
    except LaunchError as exc:
        print(str(exc), file=sys.stderr)
        return 2


def resolve_launch_paths(state_root: Path) -> LaunchPaths:
    return LaunchPaths(
        state_root=state_root,
        data_dir=state_root / "tor-data",
        torrc=state_root / "torrc",
        tor_log=state_root / "tor.log",
        tor_service_json=state_root / "tor-service.json",
        control_cookie_path=state_root / "control_auth_cookie",
        browser_home_dir=state_root / "browser-home",
        browser_profile_dir=state_root / "browser-profile",
        launch_json=state_root / "launch.json",
        prestarted_browser_json=state_root / "prestarted-browser.json",
    )


def ensure_state_dirs(paths: LaunchPaths) -> None:
    ensure_private_dir(paths.state_root)
    ensure_private_dir(paths.data_dir)
    ensure_private_dir(paths.browser_home_dir)
    ensure_private_dir(paths.browser_profile_dir)


def ensure_private_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    try:
        path.chmod(PRIVATE_DIR_MODE)
    except OSError:
        pass


def browser_runtime_reset_requested(
    *,
    leave_tor_running: bool,
    reuse_tor_if_running: bool,
    start_managed_tor_only: bool,
    reuse_prestarted_browser: bool = False,
) -> bool:
    if reuse_prestarted_browser:
        return False
    return not start_managed_tor_only and (
        leave_tor_running or reuse_tor_if_running
    )


def reset_browser_runtime_dirs(
    paths: LaunchPaths,
    *,
    reset_requested: bool,
) -> tuple[dict[str, object], BrowserRuntimeResetCleanup | None]:
    if not reset_requested:
        return {
            "ok": True,
            "cleared": False,
            "reason": "fresh browser reset not requested",
            "cleanup_mode": "none",
            "cleanup_complete": True,
        }, None

    if not async_browser_reset_enabled():
        summary = clear_browser_runtime_dirs_sync(paths)
        summary["cleanup_mode"] = "sync"
        summary["cleanup_complete"] = True
        return summary, None

    removed_files = 0
    removed_dirs = 0
    directory_summaries: dict[str, dict[str, object]] = {}
    cleanup_entries: list[BrowserRuntimeResetCleanupEntry] = []
    for label, directory in (
        ("browser_home_dir", paths.browser_home_dir),
        ("browser_profile_dir", paths.browser_profile_dir),
    ):
        try:
            staged_entry = stage_browser_runtime_dir_cleanup(
                label=label,
                directory=directory,
            )
        except OSError as exc:
            summary = clear_directory_contents(directory)
            directory_summaries[label] = {
                "path": str(directory),
                "removed_files": summary["removed_files"],
                "removed_dirs": summary["removed_dirs"],
                "reset_mode": "sync_fallback",
                "fallback_reason": f"{type(exc).__name__}: {exc}",
            }
            removed_files += int(summary["removed_files"])
            removed_dirs += int(summary["removed_dirs"])
            continue
        if staged_entry is not None:
            cleanup_entries.append(staged_entry)
            directory_summaries[label] = {
                "path": str(directory),
                "staged_path": str(staged_entry.staged_path),
                "removed_files": 0,
                "removed_dirs": 0,
                "reset_mode": "staged_rename",
            }
            continue

        summary = clear_directory_contents(directory)
        directory_summaries[label] = {
            "path": str(directory),
            "removed_files": summary["removed_files"],
            "removed_dirs": summary["removed_dirs"],
            "reset_mode": "sync_fallback",
        }
        removed_files += int(summary["removed_files"])
        removed_dirs += int(summary["removed_dirs"])

    staged_now = {entry.staged_path for entry in cleanup_entries}
    for stale_path in staged_browser_runtime_dirs(paths.state_root):
        if stale_path in staged_now:
            continue
        cleanup_entries.append(
            BrowserRuntimeResetCleanupEntry(
                label=None,
                staged_path=stale_path,
            )
        )

    summary = {
        "ok": True,
        "cleared": bool(removed_files or removed_dirs or cleanup_entries),
        "removed_files": removed_files,
        "removed_dirs": removed_dirs,
        "directories": directory_summaries,
        "cleanup_mode": "async_rename",
        "cleanup_complete": not cleanup_entries,
    }
    if not cleanup_entries:
        return summary, None
    return summary, BrowserRuntimeResetCleanup(
        summary=summary,
        entries=cleanup_entries,
    )


def clear_browser_runtime_dirs_sync(paths: LaunchPaths) -> dict[str, object]:
    removed_files = 0
    removed_dirs = 0
    directory_summaries: dict[str, dict[str, object]] = {}
    for label, directory in (
        ("browser_home_dir", paths.browser_home_dir),
        ("browser_profile_dir", paths.browser_profile_dir),
    ):
        summary = clear_directory_contents(directory)
        directory_summaries[label] = {
            "path": str(directory),
            "removed_files": summary["removed_files"],
            "removed_dirs": summary["removed_dirs"],
            "reset_mode": "sync",
        }
        removed_files += int(summary["removed_files"])
        removed_dirs += int(summary["removed_dirs"])
    return {
        "ok": True,
        "cleared": bool(removed_files or removed_dirs),
        "removed_files": removed_files,
        "removed_dirs": removed_dirs,
        "directories": directory_summaries,
    }


def staged_browser_runtime_dirs(state_root: Path) -> list[Path]:
    staged: list[Path] = []
    for pattern in (
        f"browser-home{STAGED_BROWSER_RUNTIME_PREFIX}*",
        f"browser-profile{STAGED_BROWSER_RUNTIME_PREFIX}*",
    ):
        staged.extend(
            path for path in state_root.glob(pattern) if path.is_dir()
        )
    return sorted(staged)


def stage_browser_runtime_dir_cleanup(
    *,
    label: str,
    directory: Path,
) -> BrowserRuntimeResetCleanupEntry | None:
    ensure_private_dir(directory)
    try:
        has_children = any(directory.iterdir())
    except OSError:
        return None
    if not has_children:
        return None
    staged_path = directory.with_name(
        f"{directory.name}{STAGED_BROWSER_RUNTIME_PREFIX}{time.time_ns()}"
    )
    directory.rename(staged_path)
    ensure_private_dir(directory)
    return BrowserRuntimeResetCleanupEntry(
        label=label,
        staged_path=staged_path,
    )


def count_tree_entries(path: Path) -> dict[str, int]:
    if not path.exists():
        return {"removed_files": 0, "removed_dirs": 0}
    if path.is_symlink() or path.is_file():
        return {"removed_files": 1, "removed_dirs": 0}
    removed_files = 0
    removed_dirs = 0
    for _root, dirnames, filenames in os.walk(path):
        removed_dirs += len(dirnames)
        removed_files += len(filenames)
    return {
        "removed_files": removed_files,
        "removed_dirs": removed_dirs,
    }


def run_browser_runtime_reset_cleanup(cleanup: BrowserRuntimeResetCleanup) -> None:
    summary = cleanup.summary
    try:
        removed_files = int(summary.get("removed_files", 0))
        removed_dirs = int(summary.get("removed_dirs", 0))
        directory_summaries = summary.get("directories")
        if not isinstance(directory_summaries, dict):
            directory_summaries = {}
            summary["directories"] = directory_summaries
        stale_cleanup_rows: list[dict[str, object]] = []
        for entry in cleanup.entries:
            counts = count_tree_entries(entry.staged_path)
            try:
                if entry.staged_path.exists():
                    shutil.rmtree(entry.staged_path)
            except OSError as exc:
                summary["ok"] = False
                errors = summary.setdefault("cleanup_errors", [])
                if isinstance(errors, list):
                    errors.append(f"{entry.staged_path}: {type(exc).__name__}: {exc}")
                continue
            removed_files += counts["removed_files"]
            removed_dirs += counts["removed_dirs"]
            if entry.label is None:
                stale_cleanup_rows.append(
                    {
                        "path": str(entry.staged_path),
                        **counts,
                    }
                )
                continue
            directory_summary = directory_summaries.get(entry.label)
            if isinstance(directory_summary, dict):
                directory_summary["removed_files"] = counts["removed_files"]
                directory_summary["removed_dirs"] = counts["removed_dirs"]
        summary["removed_files"] = removed_files
        summary["removed_dirs"] = removed_dirs
        if stale_cleanup_rows:
            summary["stale_cleanup"] = stale_cleanup_rows
    finally:
        summary["cleanup_complete"] = True


def start_browser_runtime_reset_cleanup(
    cleanup: BrowserRuntimeResetCleanup | None,
) -> None:
    if cleanup is None or cleanup.worker is not None:
        return
    cleanup.summary["cleanup_started"] = True
    cleanup.worker = threading.Thread(
        target=run_browser_runtime_reset_cleanup,
        args=(cleanup,),
        daemon=True,
    )
    cleanup.worker.start()


def finalize_browser_runtime_reset_cleanup(
    cleanup: BrowserRuntimeResetCleanup | None,
) -> None:
    if cleanup is None:
        return
    if cleanup.worker is None:
        run_browser_runtime_reset_cleanup(cleanup)
        return
    cleanup.worker.join()


def clear_directory_contents(path: Path) -> dict[str, int]:
    ensure_private_dir(path)
    removed_files = 0
    removed_dirs = 0
    for child in path.iterdir():
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
            removed_dirs += 1
            continue
        child.unlink()
        removed_files += 1
    ensure_private_dir(path)
    return {
        "removed_files": removed_files,
        "removed_dirs": removed_dirs,
    }


def render_c_tor_torrc(
    *,
    port: int,
    data_dir: Path,
    conflux_client_ux: str | None = None,
    control_port: int | None = None,
    control_cookie_path: Path | None = None,
) -> str:
    lines = [
        f"SocksPort 127.0.0.1:{port} {' '.join(C_TOR_SOCKS_FLAGS)}",
        f"DataDirectory {data_dir.resolve()}",
        "ClientOnly 1",
        "AvoidDiskWrites 1",
        "SafeLogging 1",
        "Log notice stdout",
        "ConfluxEnabled auto",
    ]
    if conflux_client_ux:
        lines.append(f"ConfluxClientUX {conflux_client_ux}")
    if control_port is not None and control_cookie_path is not None:
        lines.extend(
            [
                f"ControlPort 127.0.0.1:{control_port}",
                "CookieAuthentication 1",
                f"CookieAuthFile {control_cookie_path.resolve()}",
            ]
        )
    return "\n".join(lines) + "\n"


def managed_control_port(
    *,
    socks_port: int,
    leave_tor_running: bool,
    reuse_tor_if_running: bool,
    start_managed_tor_only: bool,
    stream_isolation_probe: bool,
) -> int | None:
    if (
        leave_tor_running
        or reuse_tor_if_running
        or start_managed_tor_only
        or stream_isolation_probe
    ):
        return socks_port + 10_000
    return None


def browser_launch_gate_ready_text(gate: str) -> str:
    try:
        return BROWSER_LAUNCH_GATE_READY_TEXT[gate]
    except KeyError as exc:
        raise LaunchError(f"unsupported browser launch gate: {gate}") from exc


def resolve_browser_launch_gate(*, requested_gate: str, url: str) -> str:
    if requested_gate != DEFAULT_BROWSER_LAUNCH_GATE:
        browser_launch_gate_ready_text(requested_gate)
        return requested_gate
    if urlparse(url).scheme.lower() == "about":
        return "socks_ready"
    return "tor_boot_95"


def resolve_managed_browser_launch_gate(
    *,
    requested_gate: str,
    url: str,
    start_managed_tor_only: bool,
    reused_tor_service: dict[str, object] | None,
) -> str:
    gate = resolve_browser_launch_gate(
        requested_gate=requested_gate,
        url=url,
    )
    if requested_gate != DEFAULT_BROWSER_LAUNCH_GATE:
        return gate
    if gate == "socks_ready":
        return gate
    if start_managed_tor_only:
        return "socks_ready"
    return gate


def managed_service_ready_for_gate(
    service: dict[str, object],
    gate: str,
) -> bool:
    ready_gate = service.get("ready_gate")
    if not isinstance(ready_gate, str):
        return False
    ready_rank = BROWSER_LAUNCH_GATE_ORDER.get(ready_gate)
    target_rank = BROWSER_LAUNCH_GATE_ORDER.get(gate)
    if ready_rank is None or target_rank is None:
        return False
    return ready_rank >= target_rank


def managed_service_ready_result(
    service: dict[str, object],
    *,
    gate: str,
) -> dict[str, object]:
    return {
        "ok": True,
        "seconds": 0.0,
        "ready_epoch_ms": service.get("ready_epoch_ms"),
        "ready_monotonic_seconds": service.get("ready_monotonic_seconds"),
        "lines": [],
        "signal_lines": [],
        "reused_service": True,
        "ready_gate": gate,
    }


def managed_service_ready_age_seconds(
    service: dict[str, object],
    *,
    now_epoch_ms: float | None = None,
) -> float | None:
    ready_epoch_ms = service.get("ready_epoch_ms")
    if not isinstance(ready_epoch_ms, (int, float)):
        return None
    if now_epoch_ms is None:
        now_epoch_ms = round(time.time() * 1000, 3)
    return round((float(now_epoch_ms) - float(ready_epoch_ms)) / 1000.0, 3)


def managed_open_browser_overlap_reason(
    *,
    enabled: bool,
    reused_tor_service: dict[str, object] | None,
    target_gate: str,
    url: str,
) -> str | None:
    if not enabled:
        return "disabled by flag"
    if not isinstance(reused_tor_service, dict):
        return "not reusing managed service"
    if target_gate != "tor_boot_95":
        return "non-tor_boot_95 target gate"
    if urlparse(url).scheme.lower() not in {"http", "https"}:
        return "non-network url"
    return None


def managed_open_overlap_initial_url(plan: dict[str, object]) -> str:
    target_url = str(plan.get("url") or "")
    if not target_url:
        return "about:blank"
    if managed_open_overlap_eager_target_navigation_requested(plan):
        return "about:blank"
    if urlparse(target_url).scheme.lower() == "about":
        return "about:blank"
    if str(plan.get("browser_launch_gate_requested") or DEFAULT_BROWSER_LAUNCH_GATE) != (
        DEFAULT_BROWSER_LAUNCH_GATE
    ):
        return "about:blank"
    if str(plan.get("browser_launch_gate") or DEFAULT_BROWSER_LAUNCH_GATE) != "tor_boot_95":
        return "about:blank"
    if (
        float(
            plan.get(
                "managed_open_adaptive_general_circuit_wait_timeout_seconds",
                0.0,
            )
        )
        <= 0
    ):
        return "about:blank"
    return target_url


def managed_open_overlap_eager_target_navigation_requested(
    plan: dict[str, object],
) -> bool:
    target_url = str(plan.get("url") or "")
    if not target_url:
        return False
    if urlparse(target_url).scheme.lower() == "about":
        return False
    if str(plan.get("browser_launch_gate_requested") or DEFAULT_BROWSER_LAUNCH_GATE) != (
        DEFAULT_BROWSER_LAUNCH_GATE
    ):
        return False
    if str(plan.get("browser_launch_gate") or DEFAULT_BROWSER_LAUNCH_GATE) != "tor_boot_95":
        return False
    return (
        float(
            plan.get(
                "managed_open_adaptive_general_circuit_wait_timeout_seconds",
                0.0,
            )
        )
        > 0
    )


def target_stream_substrings(url: object) -> list[str]:
    if not isinstance(url, str) or not url:
        return []
    hostname = urlparse(url).hostname
    return [hostname] if hostname else []


def clear_prestarted_browser_metadata(path: Path) -> None:
    try:
        if path.exists():
            path.unlink()
    except OSError:
        pass


def read_prestarted_browser_metadata(path: Path) -> dict[str, object] | None:
    payload = read_json(
        path,
        retries=JSON_READ_RETRIES,
        retry_delay=JSON_READ_RETRY_SECONDS,
    )
    return payload if isinstance(payload, dict) else None


def reusable_prestarted_browser(paths: LaunchPaths) -> dict[str, object] | None:
    metadata = read_prestarted_browser_metadata(paths.prestarted_browser_json)
    if not isinstance(metadata, dict):
        return None
    pid = metadata.get("pid")
    marionette_port = metadata.get("marionette_port")
    if not isinstance(pid, int) or not isinstance(marionette_port, int):
        clear_prestarted_browser_metadata(paths.prestarted_browser_json)
        return None
    if not process_is_alive(pid):
        clear_prestarted_browser_metadata(paths.prestarted_browser_json)
        return None
    return metadata


def start_warm_browser_prestart(
    plan: dict[str, object],
    *,
    paths_dict: dict[str, object],
) -> dict[str, object]:
    if port_is_open("127.0.0.1", WARM_BROWSER_PRESTART_MARIONETTE_PORT):
        raise LaunchError(
            "warm-browser-prestart marionette port "
            f"{WARM_BROWSER_PRESTART_MARIONETTE_PORT} is already in use"
        )
    browser_command = browser_launch_command(
        browser_bin=Path(str(plan["browser_bin"])),
        profile_dir=Path(str(paths_dict["browser_profile_dir"])),
        url="about:blank",
        headless=bool(plan.get("headless")),
        marionette=True,
    )
    browser_proc, browser_lines = start_browser_launcher(
        command=[str(part) for part in browser_command],
        env=browser_launch_env(
            os.environ.copy(),
            home_dir=Path(str(paths_dict["browser_home_dir"])),
            port=int(plan["port"]),
        ),
    )
    if browser_proc.poll() is not None:
        recent_lines = drain_queue(browser_lines)[-20:]
        raise LaunchError(
            "warm-browser-prestart browser exited immediately: "
            + repr(recent_lines)
        )
    metadata = {
        "pid": browser_proc.pid,
        "marionette_port": WARM_BROWSER_PRESTART_MARIONETTE_PORT,
        "browser_command": browser_command,
        "initial_url": "about:blank",
        "started_epoch_ms": round(time.time() * 1000, 3),
    }
    write_json(Path(str(paths_dict["prestarted_browser_json"])), metadata)
    return {
        "enabled": True,
        "applied": True,
        "pid": browser_proc.pid,
        "marionette_port": WARM_BROWSER_PRESTART_MARIONETTE_PORT,
        "initial_url": "about:blank",
        "browser_command": browser_command,
    }


def connect_existing_marionette_session(
    *,
    pid: int,
    marionette_port: int,
    timeout: float,
) -> object:
    from run_browser_compare import MarionetteClient

    started = time.monotonic()
    while time.monotonic() - started < timeout:
        if not process_is_alive(pid):
            raise TimeoutError(
                f"prestarted browser pid {pid} exited before marionette opened"
            )
        try:
            sock = socket.create_connection(
                ("127.0.0.1", marionette_port),
                timeout=1.0,
            )
        except OSError:
            time.sleep(0.2)
            continue
        sock.settimeout(max(10.0, timeout))
        client = MarionetteClient(sock, {})
        hello = client.read_packet()
        if isinstance(hello, dict):
            client.hello = hello
        client.command(
            "WebDriver:NewSession",
            {"capabilities": {"alwaysMatch": {}}},
        )
        client.command(
            "WebDriver:SetTimeouts",
            {
                "implicit": 0,
                "pageLoad": 300_000,
                "script": 30_000,
            },
        )
        return client
    raise TimeoutError(
        f"marionette did not open on 127.0.0.1:{marionette_port}"
    )


def collect_browser_target_load_probe(
    client: object,
    *,
    target_url: str,
) -> dict[str, object]:
    from run_browser_compare import collect_performance_timing, optional_command

    started = time.monotonic()
    current_url = optional_command(client, "WebDriver:GetCurrentURL")
    title = optional_command(client, "WebDriver:GetTitle")
    dom_snapshot: dict[str, object] = {}
    try:
        result = client.command(
            "WebDriver:ExecuteScript",
            {
                "script": r"""
return JSON.stringify({
  href: window.location.href,
  document_uri: document.documentURI,
  ready_state: document.readyState,
  visibility_state: document.visibilityState,
  body_text_prefix: document.body && typeof document.body.textContent === "string"
    ? document.body.textContent.slice(0, 160)
    : "",
});
""",
                "args": [],
                "newSandbox": False,
            },
        )
        value = result.get("value") if isinstance(result, dict) else None
        if isinstance(value, str):
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                dom_snapshot = parsed
        elif isinstance(value, dict):
            dom_snapshot = value
    except Exception as exc:  # noqa: BLE001 - proof-only diagnostics.
        dom_snapshot = {"error": f"{type(exc).__name__}: {exc}"}
    performance_timing = collect_performance_timing(client)
    navigation = (
        performance_timing.get("navigation")
        if isinstance(performance_timing, dict)
        else None
    )
    target_host = urlparse(target_url).hostname if target_url else None
    current_url_host = (
        urlparse(current_url).hostname if isinstance(current_url, str) else None
    )
    document_uri = dom_snapshot.get("document_uri")
    document_uri_host = (
        urlparse(document_uri).hostname if isinstance(document_uri, str) else None
    )
    return {
        "ok": True,
        "seconds": round(time.monotonic() - started, 3),
        "target_url": target_url,
        "target_host": target_host,
        "current_url": current_url,
        "current_url_host": current_url_host,
        "document_uri": document_uri,
        "document_uri_host": document_uri_host,
        "title": title,
        "ready_state": dom_snapshot.get("ready_state"),
        "visibility_state": dom_snapshot.get("visibility_state"),
        "body_text_prefix": dom_snapshot.get("body_text_prefix"),
        "same_host_as_target": bool(
            target_host
            and (current_url_host == target_host or document_uri_host == target_host)
        ),
        "navigation_entry_url": (
            navigation.get("name") if isinstance(navigation, dict) else None
        ),
        "navigation_entry_type": (
            navigation.get("type") if isinstance(navigation, dict) else None
        ),
        "resource_count": (
            performance_timing.get("resource_count")
            if isinstance(performance_timing, dict)
            else None
        ),
        "resource_count_by_type": (
            performance_timing.get("resource_count_by_type")
            if isinstance(performance_timing, dict)
            else None
        ),
        "performance_error": (
            performance_timing.get("error")
            if isinstance(performance_timing, dict)
            else None
        ),
    }


def collect_browser_runtime_quality_proof(
    *,
    client: object | None,
    browser_profile_dir: Path | None,
    target_url: str | None = None,
    fingerprint_max_attempts: int = 8,
    fingerprint_retry_delay_seconds: float = 0.5,
) -> dict[str, object]:
    report: dict[str, object] = {
        "enabled": (
            os.environ.get(BROWSER_RUNTIME_QUALITY_PROOF_ENABLED_ENV) == "1"
        ),
        "applied": False,
    }
    if report["enabled"] is not True:
        report["reason"] = "disabled"
        return report
    if client is None:
        report["reason"] = "marionette client unavailable"
        report["browser_quality_prefs"] = {
            "ok": False,
            "error": "browser runtime quality proof needs a marionette client",
        }
        report["browser_fingerprint_snapshot"] = {
            "ok": False,
            "error": "browser runtime quality proof needs a marionette client",
        }
        report["runtime_proxy_prefs"] = {}
        report["effective_proxy_prefs"] = {}
        return report
    from run_browser_compare import (
        collect_browser_fingerprint_snapshot,
        collect_browser_quality_prefs,
        read_runtime_prefs,
    )

    browser_quality_prefs = collect_browser_quality_prefs(client)
    runtime_proxy_prefs = (
        read_runtime_prefs(browser_profile_dir)
        if isinstance(browser_profile_dir, Path)
        else {}
    )
    effective_proxy_prefs = {
        "network.proxy.socks": runtime_proxy_prefs.get(
            "network.proxy.socks",
            "127.0.0.1",
        ),
        "network.proxy.socks_port": runtime_proxy_prefs.get(
            "network.proxy.socks_port",
            9150,
        ),
        "network.proxy.socks_remote_dns": runtime_proxy_prefs.get(
            "network.proxy.socks_remote_dns",
            True,
        ),
        "network.proxy.type": runtime_proxy_prefs.get("network.proxy.type", 1),
    }
    target_context: dict[str, object] | None = None
    if isinstance(target_url, str) and target_url.startswith(
        ("http://", "https://")
    ):
        # Pin the snapshot to the requested page so the fingerprint proof
        # measures the content-exposed surface, not a privileged about: page.
        target_context = ensure_marionette_session_on_target(
            client,
            url=target_url,
        )
    browser_fingerprint_attempts: list[dict[str, object]] = []
    browser_fingerprint_snapshot: dict[str, object] = {
        "ok": False,
        "error": "browser fingerprint snapshot not attempted",
    }
    expect_network_target = isinstance(target_url, str) and target_url.startswith(
        ("http://", "https://")
    )
    for attempt_index in range(max(1, fingerprint_max_attempts)):
        attempt = collect_browser_fingerprint_snapshot(client)
        browser_fingerprint_attempts.append(attempt)
        if attempt.get("ok") is True:
            browser_fingerprint_snapshot = attempt
            snapshot = attempt.get("snapshot")
            snapshot = snapshot if isinstance(snapshot, dict) else {}
            canvas_probe = snapshot.get("canvasProbe")
            canvas_blocked = (
                isinstance(canvas_probe, dict)
                and canvas_probe.get("extractionBlocked") is True
            )
            on_expected_page = (
                not expect_network_target
                or snapshot.get("pageUrl") == target_url
            )
            # Retry with spacing when the snapshot looks like a not-yet-settled
            # document (canvas protection not engaged, or still on the page
            # being replaced); keep the last capture either way.
            if canvas_blocked and on_expected_page:
                break
        if fingerprint_retry_delay_seconds > 0:
            time.sleep(fingerprint_retry_delay_seconds)
    report.update(
        {
            "applied": True,
            "browser_quality_prefs": browser_quality_prefs,
            "runtime_proxy_prefs": runtime_proxy_prefs,
            "effective_proxy_prefs": effective_proxy_prefs,
            "target_context": target_context,
            "browser_fingerprint_attempts": browser_fingerprint_attempts,
            "browser_fingerprint_snapshot": browser_fingerprint_snapshot,
            "ok": (
                browser_quality_prefs.get("ok") is True
                and browser_fingerprint_snapshot.get("ok") is True
            ),
        }
    )
    return report


def maybe_collect_target_launch_browser_probe(
    *,
    browser_proc: subprocess.Popen[str],
    overlap_report: dict[str, object] | None,
    target_url: str,
    timeout_seconds: float = 1.0,
) -> dict[str, object]:
    report: dict[str, object] = {
        "enabled": os.environ.get(TARGET_STREAM_PROOF_ENABLED_ENV) == "1",
        "applied": False,
        "target_url": target_url,
    }
    if report["enabled"] is not True:
        report["reason"] = "disabled"
        return report
    if not isinstance(overlap_report, dict):
        report["reason"] = "missing overlap report"
        return report
    if not overlap_report.get("launched_on_target_url"):
        report["reason"] = "not launched on target url"
        return report
    if overlap_report.get("marionette_listener_enabled") is not True:
        report["reason"] = "marionette listener unavailable"
        return report
    if browser_proc.poll() is not None:
        report["reason"] = "browser already exited"
        return report
    marionette_port = overlap_report.get("marionette_port")
    if not isinstance(marionette_port, int):
        report["reason"] = "missing marionette port"
        return report
    if not port_is_open("127.0.0.1", marionette_port):
        report["reason"] = "marionette port not open"
        return report
    client = None
    try:
        client = connect_existing_marionette_session(
            pid=browser_proc.pid,
            marionette_port=marionette_port,
            timeout=timeout_seconds,
        )
        report.update(
            {
                "applied": True,
                **collect_browser_target_load_probe(
                    client,
                    target_url=target_url,
                ),
            }
        )
        return report
    except Exception as exc:  # noqa: BLE001 - proof-only diagnostics.
        report.update(
            {
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
            }
        )
        return report
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass


def maybe_wait_for_managed_open_general_circuit_during_browser_startup(
    *,
    service_path: Path,
    reused_tor_service: dict[str, object],
    requested_gate: str,
    target_gate: str,
    browser_proc: subprocess.Popen[str],
    marionette_port: int,
    timeout_seconds: float,
    browser_session_done: threading.Event | None = None,
    browser_session_state: dict[str, object] | None = None,
    browser_session_timeout_seconds: float | None = None,
    gate_wait_timeout_seconds: float = 180.0,
    target_url: str | None = None,
    poll_interval: float = (
        MANAGED_OPEN_ADAPTIVE_GENERAL_CIRCUIT_WAIT_POLL_INTERVAL_SECONDS
    ),
) -> tuple[dict[str, object], dict[str, object]]:
    latest_service = (
        refresh_matching_managed_service(
            service_path,
            expected_service=reused_tor_service,
        )
        or reused_tor_service
    )
    timeout_seconds = round(float(timeout_seconds), 3)
    report: dict[str, object] = {
        "enabled": timeout_seconds > 0,
        "applied": False,
        "overlapped_with_browser_startup": True,
        "target_gate": target_gate,
        "timeout_seconds": timeout_seconds,
        "poll_interval_seconds": poll_interval,
        "service_ready_gate_before_wait": latest_service.get("ready_gate"),
        "service_ready_age_seconds_before_wait": managed_service_ready_age_seconds(
            latest_service
        ),
        "marionette_port": marionette_port,
    }
    target_substrings = target_stream_substrings(target_url)
    if target_substrings:
        report["target_substrings"] = list(target_substrings)
    if isinstance(browser_session_timeout_seconds, (int, float)):
        report["browser_session_timeout_seconds"] = round(
            float(browser_session_timeout_seconds),
            3,
        )
    report["gate_wait_timeout_seconds"] = round(
        float(gate_wait_timeout_seconds),
        3,
    )
    if timeout_seconds <= 0:
        report.update(
            {
                "ok": True,
                "skipped": True,
                "matched": False,
                "timed_out": False,
                "seconds": 0.0,
                "reason": "disabled by flag",
            }
        )
        return latest_service, report
    if requested_gate != DEFAULT_BROWSER_LAUNCH_GATE:
        report.update(
            {
                "ok": True,
                "skipped": True,
                "matched": False,
                "timed_out": False,
                "seconds": 0.0,
                "reason": "explicit gate requested",
            }
        )
        return latest_service, report
    if target_gate != "tor_boot_95":
        report.update(
            {
                "ok": True,
                "skipped": True,
                "matched": False,
                "timed_out": False,
                "seconds": 0.0,
                "reason": "non-default target gate",
            }
        )
        return latest_service, report
    if managed_service_ready_for_gate(latest_service, target_gate):
        report.update(
            {
                "ok": True,
                "skipped": True,
                "matched": False,
                "timed_out": False,
                "seconds": 0.0,
                "reason": "already ready for target gate",
            }
        )
        return latest_service, report
    control_port = latest_service.get("control_port")
    control_cookie_path = latest_service.get("control_cookie_path")
    if not isinstance(control_port, int) or not isinstance(control_cookie_path, str):
        report.update(
            {
                "ok": False,
                "reason": "missing control-port support",
                "skipped": True,
                "matched": False,
                "timed_out": False,
                "seconds": 0.0,
            }
        )
        return latest_service, report

    control_client: TorControlClient | None = None
    known_stream_ids: set[str] = set()

    def close_control_client() -> None:
        nonlocal control_client
        if control_client is None:
            return
        try:
            control_client.close()
        except OSError:
            pass
        control_client = None

    def read_snapshot_with_persistent_control() -> dict[str, object]:
        nonlocal control_client
        if control_client is None:
            try:
                control_client = TorControlClient.connect(
                    host="127.0.0.1",
                    port=control_port,
                    cookie_path=Path(control_cookie_path),
                )
            except (FileNotFoundError, OSError, RuntimeError, EOFError) as exc:
                return {
                    "ok": False,
                    "error": f"{type(exc).__name__}: {exc}",
                }
        try:
            return read_general_circuit_snapshot_with_client(control_client)
        except (OSError, RuntimeError, EOFError) as exc:
            close_control_client()
            return {
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
            }

    def read_target_stream_snapshot_with_persistent_control() -> dict[str, object]:
        nonlocal control_client
        if control_client is None:
            try:
                control_client = TorControlClient.connect(
                    host="127.0.0.1",
                    port=control_port,
                    cookie_path=Path(control_cookie_path),
                )
            except (FileNotFoundError, OSError, RuntimeError, EOFError) as exc:
                return {
                    "ok": False,
                    "error": f"{type(exc).__name__}: {exc}",
                }
        try:
            return read_user_stream_snapshot_with_client(
                control_client,
                target_substrings=target_substrings,
                known_stream_ids=known_stream_ids,
            )
        except (OSError, RuntimeError, EOFError) as exc:
            close_control_client()
            return {
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
            }

    def refresh_latest_service() -> dict[str, object]:
        nonlocal latest_service
        refreshed = (
            refresh_matching_managed_service(
                service_path,
                expected_service=latest_service,
            )
            or latest_service
        )
        latest_service = refreshed
        return refreshed

    def promote_latest_service_ready(wait_result: dict[str, object]) -> dict[str, object]:
        nonlocal latest_service
        latest_service = record_managed_service_ready(
            refresh_latest_service(),
            gate=target_gate,
            wait_result=wait_result,
            actor="launcher_reused_open_overlap",
        )
        write_json(service_path, latest_service)
        return latest_service

    try:
        initial_snapshot = read_snapshot_with_persistent_control()
        report["initial_snapshot"] = initial_snapshot
        last_snapshot: dict[str, object] = initial_snapshot
        last_target_stream_snapshot: dict[str, object] | None = None
        if (
            initial_snapshot.get("ok") is True
            and isinstance(initial_snapshot.get("matched_circuit_count"), int)
            and initial_snapshot["matched_circuit_count"] >= 1
        ):
            refreshed_service = (
                refresh_matching_managed_service(
                    service_path,
                    expected_service=latest_service,
                )
                or latest_service
            )
            report.update(
                {
                    "ok": True,
                    "matched": True,
                    "timed_out": False,
                    "seconds": 0.0,
                    "reason": "already_has_general_circuit",
                    "matched_circuit_count": initial_snapshot.get(
                        "matched_circuit_count"
                    ),
                    "service_ready_gate_after_wait": refreshed_service.get(
                        "ready_gate"
                    ),
                    "service_ready_age_seconds_after_wait": (
                        managed_service_ready_age_seconds(refreshed_service)
                    ),
                }
            )
            return refreshed_service, report

        started = time.monotonic()
        hidden_browser_deadline = timeout_seconds
        if isinstance(browser_session_timeout_seconds, (int, float)):
            hidden_browser_deadline = max(
                hidden_browser_deadline,
                round(float(browser_session_timeout_seconds), 3),
            )
        hidden_gate_deadline = max(
            hidden_browser_deadline,
            round(float(gate_wait_timeout_seconds), 3),
        )
        gate_wait_polls = 0
        while True:
            elapsed = round(time.monotonic() - started, 3)
            if browser_proc.poll() is not None:
                refreshed_service = refresh_latest_service()
                report.update(
                    {
                        "ok": False,
                        "applied": True,
                        "matched": False,
                        "timed_out": False,
                        "seconds": elapsed,
                        "reason": "browser_exited_during_overlap_wait",
                        "matched_circuit_count": last_snapshot.get(
                            "matched_circuit_count"
                        ),
                        "service_ready_gate_after_wait": refreshed_service.get(
                            "ready_gate"
                        ),
                        "service_ready_age_seconds_after_wait": (
                            managed_service_ready_age_seconds(refreshed_service)
                        ),
                    }
                )
                return refreshed_service, report
            browser_session_ready = False
            if browser_session_done is not None and browser_session_done.is_set():
                browser_session_ready = True
                refreshed_service = refresh_latest_service()
                if (
                    isinstance(browser_session_state, dict)
                    and browser_session_state.get("ok") is False
                ):
                    report.update(
                        {
                            "ok": False,
                            "applied": True,
                            "matched": False,
                            "timed_out": False,
                            "seconds": elapsed,
                            "reason": "browser_session_failed",
                            "browser_session_error": browser_session_state.get("error"),
                            "matched_circuit_count": last_snapshot.get(
                                "matched_circuit_count"
                            ),
                            "service_ready_gate_after_wait": refreshed_service.get(
                                "ready_gate"
                            ),
                            "service_ready_age_seconds_after_wait": (
                                managed_service_ready_age_seconds(refreshed_service)
                            ),
                        }
                    )
                    return refreshed_service, report
            snapshot = read_snapshot_with_persistent_control()
            if isinstance(snapshot, dict):
                last_snapshot = snapshot
            if (
                snapshot.get("ok") is True
                and isinstance(snapshot.get("matched_circuit_count"), int)
                and snapshot["matched_circuit_count"] >= 1
            ):
                refreshed_service = refresh_latest_service()
                report.update(
                    {
                        "ok": True,
                        "applied": True,
                        "matched": True,
                        "timed_out": False,
                        "seconds": elapsed,
                        "reason": "matched",
                        "matched_circuit_count": snapshot.get(
                            "matched_circuit_count"
                        ),
                        "wait": {
                            "ok": True,
                            "seconds": elapsed,
                            "matched_circuit_count": snapshot.get(
                                "matched_circuit_count"
                            ),
                            "matched_circuit_count_by_purpose": snapshot.get(
                                "matched_circuit_count_by_purpose"
                            ),
                            "source": "browser_startup_overlap",
                        },
                        "service_ready_gate_after_wait": refreshed_service.get(
                            "ready_gate"
                        ),
                        "service_ready_age_seconds_after_wait": (
                            managed_service_ready_age_seconds(refreshed_service)
                        ),
                    }
                )
                return refreshed_service, report
            if target_substrings:
                target_stream_snapshot = (
                    read_target_stream_snapshot_with_persistent_control()
                )
                if isinstance(target_stream_snapshot, dict):
                    last_target_stream_snapshot = target_stream_snapshot
                observed_stream_count = 0
                if isinstance(target_stream_snapshot.get("user_stream_count"), int):
                    observed_stream_count = int(
                        target_stream_snapshot["user_stream_count"]
                    )
                elif isinstance(
                    target_stream_snapshot.get("observed_stream_count"),
                    int,
                ):
                    observed_stream_count = int(
                        target_stream_snapshot["observed_stream_count"]
                    )
                if target_stream_snapshot.get("ok") is True and observed_stream_count > 0:
                    refreshed_service = refresh_latest_service()
                    report.update(
                        {
                            "ok": True,
                            "applied": True,
                            "matched": False,
                            "timed_out": False,
                            "seconds": elapsed,
                            "reason": "target_stream_activity",
                            "matched_circuit_count": last_snapshot.get(
                                "matched_circuit_count"
                            ),
                            "last_snapshot": last_snapshot,
                            "target_stream_snapshot": target_stream_snapshot,
                            "browser_launch_gate_wait": {
                                "ok": True,
                                "seconds": elapsed,
                                "polls": target_stream_snapshot.get("polls", 1),
                                "ready_via_target_stream_activity": True,
                                "target_stream_snapshot": target_stream_snapshot,
                                "ready_gate": target_gate,
                            },
                            "service_ready_gate_after_wait": refreshed_service.get(
                                "ready_gate"
                            ),
                            "service_ready_age_seconds_after_wait": (
                                managed_service_ready_age_seconds(refreshed_service)
                            ),
                        }
                    )
                    return refreshed_service, report
            if browser_session_done is None and port_is_open("127.0.0.1", marionette_port):
                browser_session_ready = True
                refreshed_service = refresh_latest_service()
                report.update(
                    {
                        "ok": True,
                        "applied": True,
                        "matched": False,
                        "timed_out": False,
                        "seconds": elapsed,
                        "reason": "browser_startup_proceed",
                        "matched_circuit_count": last_snapshot.get(
                            "matched_circuit_count"
                        ),
                        "last_snapshot": last_snapshot,
                        "target_stream_snapshot": last_target_stream_snapshot,
                        "service_ready_gate_after_wait": refreshed_service.get(
                            "ready_gate"
                        ),
                        "service_ready_age_seconds_after_wait": (
                            managed_service_ready_age_seconds(refreshed_service)
                        ),
                    }
                )
                return refreshed_service, report
            gate_wait_result: dict[str, object] | None = None
            if browser_session_ready:
                gate_wait_polls += 1
                refreshed_service = refresh_latest_service()
                if managed_service_ready_for_gate(refreshed_service, target_gate):
                    gate_wait_result = {
                        **managed_service_ready_result(
                            refreshed_service,
                            gate=target_gate,
                        ),
                        "seconds": elapsed,
                        "polls": gate_wait_polls,
                        "ready_via_service_metadata": True,
                    }
                elif control_client is not None:
                    control_ready = control_ready_for_gate_with_client(
                        gate=target_gate,
                        client=control_client,
                    )
                    if (
                        isinstance(control_ready, dict)
                        and control_ready.get("ok") is True
                    ):
                        ready_monotonic = time.monotonic()
                        gate_wait_result = {
                            "ok": True,
                            "seconds": round(ready_monotonic - started, 3),
                            "ready_epoch_ms": round(time.time() * 1000, 3),
                            "ready_monotonic_seconds": round(
                                ready_monotonic,
                                6,
                            ),
                            "lines": [],
                            "polls": gate_wait_polls,
                            "ready_via_control": True,
                            "control_bootstrap_phase": control_ready,
                            "signal_lines": [],
                            "reused_service": True,
                            "ready_gate": target_gate,
                        }
                        refreshed_service = promote_latest_service_ready(
                            gate_wait_result
                        )
                    elif control_ready is not None:
                        close_control_client()
                if gate_wait_result is not None:
                    report.update(
                        {
                            "ok": True,
                            "applied": True,
                            "matched": False,
                            "timed_out": elapsed >= timeout_seconds,
                            "seconds": elapsed,
                            "reason": (
                                "browser_startup_proceed"
                                if elapsed < timeout_seconds
                                else "timeout_proceed"
                            ),
                            "browser_session_ready": True,
                        "matched_circuit_count": last_snapshot.get(
                            "matched_circuit_count"
                        ),
                        "last_snapshot": last_snapshot,
                        "target_stream_snapshot": last_target_stream_snapshot,
                        "browser_launch_gate_wait": gate_wait_result,
                        "service_ready_gate_after_wait": refreshed_service.get(
                            "ready_gate"
                        ),
                            "service_ready_age_seconds_after_wait": (
                                managed_service_ready_age_seconds(refreshed_service)
                            ),
                        }
                    )
                    return refreshed_service, report
            if elapsed < timeout_seconds:
                time.sleep(poll_interval)
                continue
            if browser_session_done is not None:
                if not browser_session_ready and elapsed < hidden_browser_deadline:
                    time.sleep(poll_interval)
                    continue
                if browser_session_ready and elapsed < hidden_gate_deadline:
                    time.sleep(poll_interval)
                    continue
            final_snapshot = read_snapshot_with_persistent_control()
            if isinstance(final_snapshot, dict):
                last_snapshot = final_snapshot
            refreshed_service = refresh_latest_service()
            if browser_session_ready and elapsed >= hidden_gate_deadline:
                lines = []
                tor_log = refreshed_service.get("tor_log")
                if isinstance(tor_log, str):
                    lines = tail_lines(Path(tor_log), limit=80)
                gate_wait_result = {
                    "ok": False,
                    "error": "bootstrap timeout",
                    "seconds": elapsed,
                    "lines": lines,
                    "polls": gate_wait_polls,
                    "signal_lines": boot_signal_lines(lines),
                }
                report.update(
                    {
                        "applied": True,
                        "ok": True,
                        "matched": False,
                        "timed_out": True,
                        "seconds": elapsed,
                        "reason": "timeout_proceed",
                            "matched_circuit_count": last_snapshot.get(
                                "matched_circuit_count"
                            ),
                            "last_snapshot": last_snapshot,
                            "target_stream_snapshot": last_target_stream_snapshot,
                            "wait": {
                                "ok": False,
                                "error": "general circuit wait timeout",
                                "seconds": elapsed,
                                "matched_circuit_count": last_snapshot.get(
                                "matched_circuit_count"
                            ),
                            "source": "browser_startup_overlap",
                        },
                        "browser_launch_gate_wait": gate_wait_result,
                        "service_ready_gate_after_wait": refreshed_service.get(
                            "ready_gate"
                        ),
                        "service_ready_age_seconds_after_wait": (
                            managed_service_ready_age_seconds(refreshed_service)
                        ),
                    }
                )
                return refreshed_service, report
            break

        elapsed = round(time.monotonic() - started, 3)
        final_snapshot = read_snapshot_with_persistent_control()
        if isinstance(final_snapshot, dict):
            last_snapshot = final_snapshot
        refreshed_service = refresh_latest_service()
        matched_after_timeout = (
            final_snapshot.get("ok") is True
            and isinstance(final_snapshot.get("matched_circuit_count"), int)
            and final_snapshot["matched_circuit_count"] >= 1
        )
        report.update(
            {
                "applied": True,
                "ok": True,
                "matched": matched_after_timeout,
                "timed_out": not matched_after_timeout,
                "seconds": elapsed,
                "reason": "matched" if matched_after_timeout else "timeout_proceed",
                "matched_circuit_count": final_snapshot.get(
                    "matched_circuit_count"
                ),
                "target_stream_snapshot": last_target_stream_snapshot,
                "wait": (
                    {
                        "ok": True,
                        "seconds": elapsed,
                        "matched_circuit_count": final_snapshot.get(
                            "matched_circuit_count"
                        ),
                        "matched_circuit_count_by_purpose": final_snapshot.get(
                            "matched_circuit_count_by_purpose"
                        ),
                        "source": "browser_startup_overlap",
                    }
                    if matched_after_timeout
                    else {
                        "ok": False,
                        "error": "general circuit wait timeout",
                        "seconds": elapsed,
                        "matched_circuit_count": final_snapshot.get(
                            "matched_circuit_count"
                        ),
                        "source": "browser_startup_overlap",
                    }
                ),
                "service_ready_gate_after_wait": refreshed_service.get("ready_gate"),
                "service_ready_age_seconds_after_wait": (
                    managed_service_ready_age_seconds(refreshed_service)
                ),
            }
        )
        return refreshed_service, report
    finally:
        close_control_client()


def start_managed_open_browser_overlap_session(
    plan: dict[str, object],
    *,
    paths_dict: dict[str, object],
    service_path: Path | None = None,
    reused_tor_service: dict[str, object] | None = None,
) -> tuple[
    subprocess.Popen[str],
    queue.Queue[str],
    object | None,
    dict[str, object],
    dict[str, object] | None,
    dict[str, object] | None,
]:
    from run_browser_compare import MarionetteClient

    initial_url = managed_open_overlap_initial_url(plan)
    launched_on_target_url = initial_url == str(plan.get("url") or "")
    eager_target_navigation_enabled = managed_open_overlap_eager_target_navigation_requested(
        plan
    )
    marionette_proof_only = False
    use_marionette_session = not launched_on_target_url
    marionette_listener_enabled = (
        use_marionette_session or marionette_proof_only
    )
    if (
        marionette_listener_enabled
        and port_is_open("127.0.0.1", MANAGED_OPEN_BROWSER_OVERLAP_MARIONETTE_PORT)
    ):
        raise LaunchError(
            "managed-open browser overlap marionette port "
            f"{MANAGED_OPEN_BROWSER_OVERLAP_MARIONETTE_PORT} is already in use"
        )
    browser_command = browser_launch_command(
        browser_bin=Path(str(plan["browser_bin"])),
        profile_dir=Path(str(paths_dict["browser_profile_dir"])),
        url=initial_url,
        headless=bool(plan.get("headless")),
        marionette=marionette_listener_enabled,
    )
    browser_proc, browser_lines = start_browser_launcher(
        command=[str(part) for part in browser_command],
        env=browser_launch_env(
            os.environ.copy(),
            home_dir=Path(str(paths_dict["browser_home_dir"])),
            port=int(plan["port"]),
        ),
    )
    connect_timeout = min(
        30.0,
        max(10.0, float(plan.get("browser_timeout_seconds", 0.0)) + 5.0),
    )
    browser_session_done = threading.Event()
    browser_session_state: dict[str, object] = {
        "ok": None,
        "client": None,
        "error": None,
    }

    def connect_worker() -> None:
        client: object | None = None
        try:
            client = MarionetteClient.connect(
                host="127.0.0.1",
                port=MANAGED_OPEN_BROWSER_OVERLAP_MARIONETTE_PORT,
                proc=browser_proc,
                lines=browser_lines,
                timeout=connect_timeout,
            )
            client.sock.settimeout(
                max(10.0, float(plan.get("browser_timeout_seconds", 0.0)) + 10.0)
            )
            client.command(
                "WebDriver:NewSession",
                {"capabilities": {"alwaysMatch": {}}},
            )
            client.command(
                "WebDriver:SetTimeouts",
                {
                    "implicit": 0,
                    "pageLoad": 300_000,
                    "script": 30_000,
                },
            )
            if eager_target_navigation_enabled:
                browser_session_state["eager_target_navigation"] = (
                    navigate_managed_open_browser_overlap_session(
                        client,
                        url=str(plan.get("url") or ""),
                    )
                )
            browser_session_state["ok"] = True
            browser_session_state["client"] = client
        except Exception as exc:  # noqa: BLE001 - experimental proof path.
            if client is not None:
                try:
                    client.close()
                except Exception:
                    pass
            browser_session_state["ok"] = False
            browser_session_state["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            browser_session_done.set()

    if use_marionette_session:
        threading.Thread(target=connect_worker, daemon=True).start()
    else:
        browser_session_state["ok"] = True
        browser_session_done.set()
    overlap_adaptive_wait_report: dict[str, object] | None = None
    refreshed_tor_service = reused_tor_service
    if isinstance(reused_tor_service, dict) and service_path is not None:
        overlap_browser_session_done = (
            browser_session_done if use_marionette_session else None
        )
        overlap_browser_session_state = (
            browser_session_state if use_marionette_session else None
        )
        overlap_browser_session_timeout_seconds = (
            connect_timeout + 1.0 if use_marionette_session else None
        )
        (
            refreshed_tor_service,
            overlap_adaptive_wait_report,
        ) = maybe_wait_for_managed_open_general_circuit_during_browser_startup(
            service_path=service_path,
            reused_tor_service=reused_tor_service,
            requested_gate=str(
                plan.get("browser_launch_gate_requested")
                or DEFAULT_BROWSER_LAUNCH_GATE
            ),
            target_gate=str(plan.get("browser_launch_gate") or DEFAULT_BROWSER_LAUNCH_GATE),
            browser_proc=browser_proc,
            marionette_port=MANAGED_OPEN_BROWSER_OVERLAP_MARIONETTE_PORT,
            timeout_seconds=float(
                plan.get(
                    "managed_open_adaptive_general_circuit_wait_timeout_seconds",
                    0.0,
                )
            ),
            browser_session_done=overlap_browser_session_done,
            browser_session_state=overlap_browser_session_state,
            browser_session_timeout_seconds=overlap_browser_session_timeout_seconds,
            target_url=str(plan.get("url") or ""),
        )
    client = None
    if use_marionette_session:
        if not browser_session_done.wait(connect_timeout + 1.0):
            raise TimeoutError(
                "managed-open browser overlap session did not become ready in time"
            )
        if browser_session_state.get("ok") is not True:
            raise TimeoutError(
                str(
                    browser_session_state.get("error")
                    or "managed-open browser overlap session failed"
                )
            )
        client = browser_session_state.get("client")
        if client is None:
            raise TimeoutError("managed-open browser overlap session missing client")
    return (
        browser_proc,
        browser_lines,
        client,
        {
            "enabled": True,
            "applied": True,
            "browser_command": browser_command,
            "connect_timeout_seconds": connect_timeout if use_marionette_session else 0.0,
            "initial_url": initial_url,
            "marionette_port": MANAGED_OPEN_BROWSER_OVERLAP_MARIONETTE_PORT,
            "marionette_listener_enabled": marionette_listener_enabled,
            "marionette_proof_only": marionette_proof_only,
            "eager_target_navigation_enabled": eager_target_navigation_enabled,
            "launched_on_target_url": launched_on_target_url,
            "marionette_session_used": use_marionette_session,
            "eager_target_navigation": browser_session_state.get(
                "eager_target_navigation"
            ),
        },
        refreshed_tor_service,
        overlap_adaptive_wait_report,
    )


# Tor Browser's first-run startup can load its home page (about:tor) into the
# initial tab after the eager target navigation already committed, replacing
# the page the user asked for. The keeper watches the session during the open
# wait window and re-issues the target navigation when one of these startup
# pages steals the tab.
TARGET_NAVIGATION_STARTUP_CLOBBER_PAGES = frozenset(
    {"about:tor", "about:blank", "about:newtab", "about:home"}
)
TARGET_NAVIGATION_KEEPER_MAX_SECONDS = 20.0
TARGET_NAVIGATION_KEEPER_POLL_SECONDS = 0.25
# A correction restarts the whole target load over the Tor circuit, which can
# take several seconds to commit. Re-issuing before that window has passed
# keeps restarting the load and the page never arrives, so corrections are
# rate-limited by this grace period.
TARGET_NAVIGATION_CORRECTION_GRACE_SECONDS = 8.0


CORRECTION_NAVIGATE_PAGE_LOAD_TIMEOUT_MS = 250
SESSION_PAGE_LOAD_TIMEOUT_MS = 300_000


def renavigate_marionette_session_to_target(client: object, *, url: str) -> None:
    # Chrome-driven navigation: unlike a content-script location.replace it
    # also works when a privileged about: page owns the tab. The pageLoad
    # timeout is shrunk so the command returns as soon as the navigation is
    # issued while the browser keeps loading; a blocking Navigate here can
    # stall the whole open for the client socket timeout on a slow circuit.
    try:
        client.command(
            "WebDriver:SetTimeouts",
            {"pageLoad": CORRECTION_NAVIGATE_PAGE_LOAD_TIMEOUT_MS},
        )
        try:
            client.command("WebDriver:Navigate", {"url": url})
        except RuntimeError as exc:
            if "timeout" not in str(exc).lower():
                raise
    finally:
        client.command(
            "WebDriver:SetTimeouts",
            {"pageLoad": SESSION_PAGE_LOAD_TIMEOUT_MS},
        )


def run_target_navigation_keeper(
    client: object,
    *,
    url: str,
    stop_event: threading.Event,
    max_seconds: float = TARGET_NAVIGATION_KEEPER_MAX_SECONDS,
    poll_seconds: float = TARGET_NAVIGATION_KEEPER_POLL_SECONDS,
    correction_grace_seconds: float = TARGET_NAVIGATION_CORRECTION_GRACE_SECONDS,
) -> dict[str, object]:
    from run_browser_compare import optional_command

    report: dict[str, object] = {
        "enabled": True,
        "target_url": url,
        "checks": 0,
        "corrections": 0,
        "errors": [],
        "final_url": None,
    }
    started = time.monotonic()
    last_correction: float | None = None
    while not stop_event.is_set() and time.monotonic() - started < max_seconds:
        current_url = optional_command(client, "WebDriver:GetCurrentURL")
        report["checks"] = int(report["checks"]) + 1
        if isinstance(current_url, str):
            report["final_url"] = current_url
        if current_url == url:
            last_correction = None
        elif (
            isinstance(current_url, str)
            and current_url in TARGET_NAVIGATION_STARTUP_CLOBBER_PAGES
            and (
                last_correction is None
                or time.monotonic() - last_correction >= correction_grace_seconds
            )
        ):
            try:
                renavigate_marionette_session_to_target(client, url=url)
                report["corrections"] = int(report["corrections"]) + 1
                last_correction = time.monotonic()
            except Exception as exc:  # noqa: BLE001 - keeper is best effort.
                report["errors"].append(f"{type(exc).__name__}: {exc}")
                break
        stop_event.wait(poll_seconds)
    report["seconds"] = round(time.monotonic() - started, 3)
    return report


def start_target_navigation_keeper(
    client: object,
    *,
    url: str,
) -> dict[str, object]:
    stop_event = threading.Event()
    holder: dict[str, object] = {
        "enabled": True,
        "target_url": url,
        "pending": True,
    }

    def keeper_worker() -> None:
        report = run_target_navigation_keeper(
            client,
            url=url,
            stop_event=stop_event,
        )
        holder.update(report)
        holder["pending"] = False

    thread = threading.Thread(target=keeper_worker, daemon=True)
    thread.start()
    holder["_stop_event"] = stop_event
    holder["_thread"] = thread
    return holder


def finish_target_navigation_keeper(
    holder: dict[str, object] | None,
) -> dict[str, object] | None:
    if not isinstance(holder, dict):
        return None
    stop_event = holder.pop("_stop_event", None)
    thread = holder.pop("_thread", None)
    if isinstance(stop_event, threading.Event):
        stop_event.set()
    if isinstance(thread, threading.Thread):
        # A correction can block on WebDriver:Navigate until the client socket
        # timeout, so give the worker room to drain before the main thread
        # reuses the same Marionette client.
        thread.join(timeout=35.0)
    return holder


def ensure_marionette_session_on_target(
    client: object,
    *,
    url: str,
    timeout_seconds: float = 30.0,
    poll_seconds: float = 0.25,
    # The startup clobber can land more than once, including on top of an
    # earlier correction, and the tab URL cannot distinguish "correction in
    # flight" from "clobbered again". The grace period keeps re-corrections
    # from strangling an in-flight load while several attempts stay allowed.
    max_corrections: int = 3,
    correction_grace_seconds: float = TARGET_NAVIGATION_CORRECTION_GRACE_SECONDS,
) -> dict[str, object]:
    from run_browser_compare import optional_command

    report: dict[str, object] = {
        "target_url": url,
        "checks": 0,
        "corrections": 0,
        "errors": [],
        "on_target": False,
        "final_url": None,
    }
    started = time.monotonic()
    last_correction: float | None = None
    while True:
        current_url = optional_command(client, "WebDriver:GetCurrentURL")
        report["checks"] = int(report["checks"]) + 1
        if isinstance(current_url, str):
            report["final_url"] = current_url
        if current_url == url:
            report["on_target"] = True
            break
        if time.monotonic() - started >= timeout_seconds:
            break
        if (
            isinstance(current_url, str)
            and current_url in TARGET_NAVIGATION_STARTUP_CLOBBER_PAGES
            and int(report["corrections"]) < max_corrections
            and (
                last_correction is None
                or time.monotonic() - last_correction >= correction_grace_seconds
            )
        ):
            try:
                renavigate_marionette_session_to_target(client, url=url)
                report["corrections"] = int(report["corrections"]) + 1
                last_correction = time.monotonic()
            except Exception as exc:  # noqa: BLE001 - proof context repair only.
                report["errors"].append(f"{type(exc).__name__}: {exc}")
                break
        time.sleep(poll_seconds)
    report["seconds"] = round(time.monotonic() - started, 3)
    return report


def navigate_managed_open_browser_overlap_session(
    client: object,
    *,
    url: str,
) -> dict[str, object]:
    started = time.monotonic()
    try:
        result = client.command(
            "WebDriver:ExecuteScript",
            {
                "script": "window.location.replace(arguments[0]); return true;",
                "args": [url],
                "newSandbox": False,
            },
        )
    except Exception as exc:  # noqa: BLE001 - experimental proof path.
        return {
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
            "seconds": round(time.monotonic() - started, 3),
            "target_url": url,
        }
    return {
        "ok": True,
        "seconds": round(time.monotonic() - started, 3),
        "target_url": url,
        "value": result.get("value") if isinstance(result, dict) else None,
    }


def refresh_matching_managed_service(
    service_path: Path,
    *,
    expected_service: dict[str, object],
) -> dict[str, object] | None:
    latest_service = read_json(
        service_path,
        retries=JSON_READ_RETRIES,
        retry_delay=JSON_READ_RETRY_SECONDS,
    )
    if not isinstance(latest_service, dict):
        return None
    if latest_service.get("pid") != expected_service.get("pid"):
        return None
    if latest_service.get("tor_log") != expected_service.get("tor_log"):
        return None
    return latest_service


def latest_managed_service_for_update(
    service_path: Path,
    *,
    service: dict[str, object],
) -> dict[str, object]:
    refreshed_service = refresh_matching_managed_service(
        service_path,
        expected_service=service,
    )
    return refreshed_service or service


def current_process_is_runtime_helper(state_root: Path) -> bool:
    try:
        from torfast.fast_runtime import running_runtime_helper_metadata
    except Exception:
        return False
    metadata = running_runtime_helper_metadata(state_root)
    return isinstance(metadata, dict) and metadata.get("pid") == os.getpid()


def request_runtime_helper_gate_promoter(
    state_root: Path,
) -> dict[str, object]:
    report: dict[str, object] = {
        "requested": False,
        "active_after_request": False,
        "mode": "socket_request",
    }
    try:
        from torfast.fast_runtime import (
            running_runtime_helper_metadata,
            runtime_helper_start_pending,
        )
    except Exception:
        report["reason"] = "runtime helper unavailable"
        return report
    metadata = running_runtime_helper_metadata(state_root)
    if metadata is None and runtime_helper_start_pending(state_root):
        wait_started = time.monotonic()
        while time.monotonic() - wait_started < 0.1:
            time.sleep(0.01)
            metadata = running_runtime_helper_metadata(state_root)
            if metadata is not None:
                report["startup_wait_seconds"] = round(
                    time.monotonic() - wait_started,
                    3,
                )
                break
    if not isinstance(metadata, dict):
        report["reason"] = "runtime helper unavailable"
        return report
    socket_path = metadata.get("socket_path")
    if not isinstance(socket_path, str):
        report["reason"] = "runtime helper socket missing"
        return report
    report["requested"] = True
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(0.2)
            client.connect(socket_path)
            client.settimeout(None)
            client.sendall(b'{"start_gate_promoter": true}\n')
            client.shutdown(socket.SHUT_WR)
            chunks: list[bytes] = []
            while True:
                chunk = client.recv(65536)
                if not chunk:
                    break
                chunks.append(chunk)
    except OSError as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        return report
    try:
        payload = json.loads(b"".join(chunks).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        return report
    if not isinstance(payload, dict):
        report["error"] = "runtime helper returned non-dict payload"
        return report
    if payload.get("ok") is not True:
        report["error"] = str(payload.get("error") or "runtime helper request failed")
        return report
    report["active_after_request"] = bool(payload.get("active_after_request"))
    if isinstance(payload.get("reason"), str):
        report["reason"] = payload["reason"]
    return report


def maybe_start_runtime_helper_gate_promoter(
    state_root: Path,
) -> dict[str, object]:
    if not current_process_is_runtime_helper(state_root):
        return request_runtime_helper_gate_promoter(state_root)
    report: dict[str, object] = {
        "requested": False,
        "active_after_request": False,
        "mode": "in_process",
    }
    report["requested"] = True
    try:
        from torfast.runtime_helper import maybe_restart_background_gate_promoter
    except Exception as exc:  # pragma: no cover - defensive only
        report["error"] = f"{type(exc).__name__}: {exc}"
        return report
    promoter_thread = maybe_restart_background_gate_promoter(
        state_root,
        thread=None,
    )
    if promoter_thread is None:
        report["reason"] = "no promotable managed service"
        return report
    report["active_after_request"] = promoter_thread.is_alive()
    return report


def maybe_settle_recently_warmed_service(
    *,
    service_path: Path,
    reused_tor_service: dict[str, object],
    requested_gate: str,
    target_gate: str,
    settle_seconds: float = DEFAULT_MANAGED_OPEN_SETTLE_SECONDS,
    enabled: bool = True,
) -> tuple[dict[str, object], dict[str, object]]:
    latest_service = (
        refresh_matching_managed_service(
            service_path,
            expected_service=reused_tor_service,
        )
        or reused_tor_service
    )
    report: dict[str, object] = {
        "enabled": enabled,
        "applied": False,
        "target_gate": target_gate,
        "settle_seconds": round(float(settle_seconds), 3),
        "service_ready_gate_before_settle": latest_service.get("ready_gate"),
        "service_ready_age_seconds_before_settle": managed_service_ready_age_seconds(
            latest_service
        ),
    }
    if not enabled:
        report["reason"] = "disabled by flag"
        return latest_service, report
    if requested_gate != DEFAULT_BROWSER_LAUNCH_GATE:
        report["reason"] = "explicit gate requested"
        return latest_service, report
    if target_gate != "tor_boot_95":
        report["reason"] = "non-default target gate"
        return latest_service, report
    if managed_service_ready_for_gate(latest_service, target_gate):
        report["reason"] = "already ready for target gate"
        return latest_service, report
    if latest_service.get("ready_gate") != "socks_ready":
        report["reason"] = "unexpected starting gate"
        return latest_service, report
    ready_age = report["service_ready_age_seconds_before_settle"]
    if not isinstance(ready_age, (int, float)):
        report["reason"] = "missing ready timestamp"
        return latest_service, report
    remaining = round(float(settle_seconds) - float(ready_age), 3)
    if remaining <= 0:
        report["reason"] = "already aged past settle window"
        return latest_service, report
    time.sleep(remaining)
    refreshed_service = (
        refresh_matching_managed_service(
            service_path,
            expected_service=latest_service,
        )
        or latest_service
    )
    report.update(
        {
            "applied": True,
            "slept_seconds": remaining,
            "service_ready_gate_after_settle": refreshed_service.get("ready_gate"),
            "service_ready_age_seconds_after_settle": (
                managed_service_ready_age_seconds(refreshed_service)
            ),
        }
    )
    return refreshed_service, report


def maybe_wait_for_managed_open_general_circuit(
    *,
    service_path: Path,
    reused_tor_service: dict[str, object],
    requested_gate: str,
    target_gate: str,
    timeout_seconds: float,
    enabled: bool = False,
    poll_interval: float = (
        MANAGED_OPEN_ADAPTIVE_GENERAL_CIRCUIT_WAIT_POLL_INTERVAL_SECONDS
    ),
) -> tuple[dict[str, object], dict[str, object]]:
    latest_service = (
        refresh_matching_managed_service(
            service_path,
            expected_service=reused_tor_service,
        )
        or reused_tor_service
    )
    timeout_seconds = round(float(timeout_seconds), 3)
    report: dict[str, object] = {
        "enabled": enabled and timeout_seconds > 0,
        "applied": False,
        "target_gate": target_gate,
        "timeout_seconds": timeout_seconds,
        "poll_interval_seconds": poll_interval,
        "service_ready_gate_before_wait": latest_service.get("ready_gate"),
        "service_ready_age_seconds_before_wait": managed_service_ready_age_seconds(
            latest_service
        ),
    }
    if not enabled or timeout_seconds <= 0:
        report.update(
            {
                "ok": True,
                "skipped": True,
                "matched": False,
                "timed_out": False,
                "seconds": 0.0,
                "reason": "disabled by flag",
            }
        )
        return latest_service, report
    if requested_gate != DEFAULT_BROWSER_LAUNCH_GATE:
        report.update(
            {
                "ok": True,
                "skipped": True,
                "matched": False,
                "timed_out": False,
                "seconds": 0.0,
                "reason": "explicit gate requested",
            }
        )
        return latest_service, report
    if target_gate != "tor_boot_95":
        report.update(
            {
                "ok": True,
                "skipped": True,
                "matched": False,
                "timed_out": False,
                "seconds": 0.0,
                "reason": "non-default target gate",
            }
        )
        return latest_service, report
    if managed_service_ready_for_gate(latest_service, target_gate):
        report.update(
            {
                "ok": True,
                "skipped": True,
                "matched": False,
                "timed_out": False,
                "seconds": 0.0,
                "reason": "already ready for target gate",
            }
        )
        return latest_service, report
    control_port = latest_service.get("control_port")
    control_cookie_path = latest_service.get("control_cookie_path")
    if not isinstance(control_port, int) or not isinstance(control_cookie_path, str):
        report.update(
            {
                "ok": False,
                "reason": "missing control-port support",
                "skipped": True,
                "matched": False,
                "timed_out": False,
                "seconds": 0.0,
            }
        )
        return latest_service, report

    initial_snapshot = read_general_circuit_snapshot(
        host="127.0.0.1",
        port=control_port,
        cookie_path=Path(control_cookie_path),
    )
    report["initial_snapshot"] = initial_snapshot
    if (
        initial_snapshot.get("ok") is True
        and isinstance(initial_snapshot.get("matched_circuit_count"), int)
        and initial_snapshot["matched_circuit_count"] >= 1
    ):
        refreshed_service = (
            refresh_matching_managed_service(
                service_path,
                expected_service=latest_service,
            )
            or latest_service
        )
        report.update(
            {
                "ok": True,
                "matched": True,
                "timed_out": False,
                "seconds": 0.0,
                "reason": "already_has_general_circuit",
                "matched_circuit_count": initial_snapshot.get(
                    "matched_circuit_count"
                ),
                "service_ready_gate_after_wait": refreshed_service.get("ready_gate"),
                "service_ready_age_seconds_after_wait": (
                    managed_service_ready_age_seconds(refreshed_service)
                ),
            }
        )
        return refreshed_service, report

    wait = wait_for_general_circuits(
        host="127.0.0.1",
        port=control_port,
        cookie_path=Path(control_cookie_path),
        timeout=timeout_seconds,
        poll_interval=poll_interval,
        min_count=1,
    )
    refreshed_service = (
        refresh_matching_managed_service(
            service_path,
            expected_service=latest_service,
        )
        or latest_service
    )
    timed_out = wait.get("error") == "general circuit wait timeout"
    report.update(
        {
            "applied": True,
            "ok": bool(wait.get("ok")) or timed_out,
            "matched": bool(wait.get("ok")),
            "timed_out": timed_out,
            "seconds": round(
                float(wait.get("seconds"))
                if isinstance(wait.get("seconds"), (int, float))
                else timeout_seconds,
                3,
            ),
            "reason": "matched" if wait.get("ok") is True else "timeout_proceed",
            "matched_circuit_count": wait.get("matched_circuit_count"),
            "wait": wait,
            "service_ready_gate_after_wait": refreshed_service.get("ready_gate"),
            "service_ready_age_seconds_after_wait": (
                managed_service_ready_age_seconds(refreshed_service)
            ),
        }
    )
    return refreshed_service, report


def consume_managed_open_adaptive_general_circuit_wait_report(
    report_path: Path,
    *,
    expected_service: dict[str, object],
    requested_timeout_seconds: float,
) -> dict[str, object] | None:
    payload = read_json(
        report_path,
        retries=JSON_READ_RETRIES,
        retry_delay=JSON_READ_RETRY_SECONDS,
    )
    try:
        if report_path.exists():
            report_path.unlink()
    except OSError:
        pass
    if not isinstance(payload, dict):
        return None
    if payload.get("source") != "fast_runtime":
        return None
    if payload.get("service_pid") != expected_service.get("pid"):
        return None
    expected_started_epoch_ms = expected_service.get("started_epoch_ms")
    report_started_epoch_ms = payload.get("service_started_epoch_ms")
    if (
        isinstance(expected_started_epoch_ms, (int, float))
        and isinstance(report_started_epoch_ms, (int, float))
        and float(expected_started_epoch_ms) != float(report_started_epoch_ms)
    ):
        return None
    if round(float(payload.get("timeout_seconds", 0.0)), 3) != round(
        float(requested_timeout_seconds),
        3,
    ):
        return None
    return {
        **payload,
        "consumed_from_state_file": True,
    }


def combine_tor_wait_results(
    first: dict[str, object],
    second: dict[str, object],
) -> dict[str, object]:
    combined_lines = [
        *(
            first.get("lines")
            if isinstance(first.get("lines"), list)
            else []
        ),
        *(
            second.get("lines")
            if isinstance(second.get("lines"), list)
            else []
        ),
    ]
    combined: dict[str, object] = {
        **second,
        "lines": combined_lines[-80:],
        "signal_lines": boot_signal_lines(combined_lines),
    }
    first_seconds = first.get("seconds")
    second_seconds = second.get("seconds")
    if isinstance(first_seconds, (int, float)) and isinstance(
        second_seconds, (int, float)
    ):
        combined["seconds"] = round(float(first_seconds) + float(second_seconds), 3)
    return combined


def browser_launch_env_overrides(*, home_dir: Path, port: int) -> dict[str, str]:
    return {
        "HOME": str(home_dir.resolve()),
        "MOZ_CRASHREPORTER_DISABLE": "1",
        "TZ": "UTC",
        "TOR_PROVIDER": "none",
        "TOR_SKIP_LAUNCH": "1",
        "TOR_SOCKS_HOST": "127.0.0.1",
        "TOR_SOCKS_PORT": str(port),
    }


def browser_launch_env(
    base_env: dict[str, str],
    *,
    home_dir: Path,
    port: int,
) -> dict[str, str]:
    env = dict(base_env)
    env.update(browser_launch_env_overrides(home_dir=home_dir, port=port))
    return env


def browser_launch_command(
    *,
    browser_bin: Path,
    profile_dir: Path,
    url: str,
    headless: bool,
    marionette: bool = False,
) -> list[str]:
    command = [
        str(browser_bin),
        "--new-instance",
        "--no-remote",
        "-remote-allow-system-access",
        "--profile",
        str(profile_dir.resolve()),
    ]
    if headless:
        command.append("--headless")
    if marionette:
        command.append("--marionette")
    command.append(url)
    return command


def build_launch_plan(
    *,
    browser_bin: Path,
    tor_bin: Path,
    paths: LaunchPaths,
    port: int,
    url: str,
    headless: bool,
    browser_timeout: float,
    browser_launch_gate: str,
    browser_launch_gate_requested: str,
    conflux_client_ux: str | None,
    leave_tor_running: bool,
    reuse_tor_if_running: bool,
    start_managed_tor_only: bool,
    browser_runtime_reset: dict[str, object],
    dir_cache_seed_root: Path,
    dir_cache_seed_apply: dict[str, object],
    browser_startup_seed_root: Path,
    browser_startup_seed_apply: dict[str, object],
    reused_tor_service: dict[str, object] | None,
    default_pref_proof: dict[str, object],
    default_pref_check: dict[str, object],
    control_port: int | None,
    control_cookie_path: Path | None,
    gate_diagnostics_enabled: bool,
    managed_open_settle_enabled: bool,
    managed_open_browser_overlap_enabled: bool = False,
    managed_open_adaptive_general_circuit_wait_timeout_seconds: float = 0.0,
    warm_browser_prestart_enabled: bool = False,
    reused_prestarted_browser: dict[str, object] | None = None,
    stream_isolation_probe: bool,
    stream_isolation_probe_timeout: float,
    ui_theme_apply: dict[str, object] | None = None,
    profile_label: str | None = None,
) -> dict[str, object]:
    return {
        "created_at_epoch_ms": round(time.time() * 1000, 3),
        "profile": profile_label,
        "ui_theme": (
            ui_theme_apply.get("theme")
            if isinstance(ui_theme_apply, dict)
            else None
        ),
        "ui_theme_apply": ui_theme_apply,
        "browser_bin": str(browser_bin),
        "tor_bin": str(tor_bin),
        "paths": paths.as_dict(),
        "port": port,
        "url": url,
        "headless": headless,
        "browser_timeout_seconds": browser_timeout,
        "browser_launch_gate": browser_launch_gate,
        "browser_launch_gate_requested": browser_launch_gate_requested,
        "managed_open_settle_enabled": managed_open_settle_enabled,
        "managed_open_browser_overlap_enabled": managed_open_browser_overlap_enabled,
        "managed_open_adaptive_general_circuit_wait_timeout_seconds": (
            round(
                float(managed_open_adaptive_general_circuit_wait_timeout_seconds),
                3,
            )
        ),
        "warm_browser_prestart_enabled": warm_browser_prestart_enabled,
        "conflux_client_ux": conflux_client_ux,
        "leave_tor_running": leave_tor_running,
        "reuse_tor_if_running": reuse_tor_if_running,
        "start_managed_tor_only": start_managed_tor_only,
        "browser_runtime_reset": browser_runtime_reset,
        "dir_cache_seed_root": str(dir_cache_seed_root),
        "dir_cache_seed_apply": dir_cache_seed_apply,
        "dir_cache_seed_status": describe_seed(dir_cache_seed_root),
        "browser_startup_seed_root": str(browser_startup_seed_root),
        "browser_startup_seed_apply": browser_startup_seed_apply,
        "browser_startup_seed_status": describe_browser_startup_seed(
            browser_startup_seed_root
        ),
        "reused_tor_service": reused_tor_service,
        "reused_prestarted_browser": reused_prestarted_browser,
        "control_port": control_port,
        "control_cookie_path": (
            str(control_cookie_path) if control_cookie_path is not None else None
        ),
        "torrc_quality": read_torrc_quality(paths.torrc),
        "browser_default_prefs": default_pref_proof,
        "browser_default_pref_check": default_pref_check,
        "gate_diagnostics_enabled": gate_diagnostics_enabled,
        "stream_isolation_probe_enabled": stream_isolation_probe,
        "stream_isolation_probe_timeout_seconds": stream_isolation_probe_timeout,
        "browser_command": browser_launch_command(
            browser_bin=browser_bin,
            profile_dir=paths.browser_profile_dir,
            url=url,
            headless=headless,
        ),
        "browser_env_overrides": browser_launch_env_overrides(
            home_dir=paths.browser_home_dir,
            port=port,
        ),
        "tor_boot": None,
        "browser": None,
    }


def write_plan(path: Path, plan: dict[str, object]) -> None:
    atomic_write_text(path, json.dumps(plan, indent=2, sort_keys=True) + "\n")


def atomic_write_text(path: Path, text: str) -> None:
    ensure_private_dir(path.parent)
    temp_path = path.with_name(f".{path.name}.tmp-{os.getpid()}-{time.time_ns()}")
    try:
        temp_path.write_text(text, encoding="utf-8")
        temp_path.replace(path)
    finally:
        try:
            if temp_path.exists():
                temp_path.unlink()
        except OSError:
            pass


def start_c_tor_launcher(
    *,
    tor_bin: Path,
    torrc: Path,
) -> tuple[subprocess.Popen[str], queue.Queue[str]]:
    proc = subprocess.Popen(
        [str(tor_bin), "-f", str(torrc)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    lines: queue.Queue[str] = queue.Queue()
    threading.Thread(target=read_lines, args=(proc, lines), daemon=True).start()
    return proc, lines


def start_c_tor_detached(
    *,
    tor_bin: Path,
    torrc: Path,
    log_path: Path,
) -> subprocess.Popen[str]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as log_file:
        proc = subprocess.Popen(
            [str(tor_bin), "-f", str(torrc)],
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            start_new_session=True,
        )
    return proc


def start_browser_launcher(
    *,
    command: list[str],
    env: dict[str, str],
) -> tuple[subprocess.Popen[str], queue.Queue[str]]:
    proc = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        start_new_session=True,
        env=env,
    )
    lines: queue.Queue[str] = queue.Queue()
    threading.Thread(target=read_lines, args=(proc, lines), daemon=True).start()
    return proc, lines


def launch_browser_with_c_tor(
    plan: dict[str, object],
    *,
    browser_runtime_reset_cleanup: BrowserRuntimeResetCleanup | None = None,
) -> int:
    paths_dict = plan.get("paths", {})
    assert isinstance(paths_dict, dict)
    launch_json = Path(str(paths_dict["launch_json"]))

    tor_proc = None
    browser_proc = None
    tor_lines: queue.Queue[str] | None = None
    browser_lines: queue.Queue[str] | None = None
    overlap_browser_client = None
    overlap_browser_started = None
    prestarted_browser_client = None
    prestarted_browser_started = None
    leave_tor_running = bool(plan.get("leave_tor_running"))
    reused_tor_service = plan.get("reused_tor_service")
    reused_prestarted_browser = plan.get("reused_prestarted_browser")
    browser_launch_gate = str(
        plan.get("browser_launch_gate") or DEFAULT_BROWSER_LAUNCH_GATE
    )
    gate_diagnostics_enabled = bool(plan.get("gate_diagnostics_enabled"))
    keep_tor_running = False
    tor_boot: dict[str, object] | None = None
    tor_managed_ready: dict[str, object] | None = None
    pending_managed_service: dict[str, object] | None = None
    try:
        if isinstance(reused_tor_service, dict):
            keep_tor_running = True
            if plan.get("start_managed_tor_only"):
                if managed_service_ready_for_gate(
                    reused_tor_service,
                    browser_launch_gate,
                ):
                    tor_managed_ready = managed_service_ready_result(
                        reused_tor_service,
                        gate=browser_launch_gate,
                    )
                else:
                    tor_managed_ready = wait_for_existing_service_ready_in_log(
                        pid=int(reused_tor_service["pid"]),
                        log_path=Path(str(reused_tor_service["tor_log"])),
                        timeout=180.0,
                        gate=browser_launch_gate,
                        control_port=reused_tor_service.get("control_port"),
                        control_cookie_path=reused_tor_service.get("control_cookie_path"),
                        service_path=Path(str(paths_dict["tor_service_json"])),
                        expected_service=reused_tor_service,
                        ready_text=browser_launch_gate_ready_text(browser_launch_gate),
                        process_name="tor",
                    )
                plan["tor_managed_ready"] = {
                    **tor_managed_ready,
                    "service_pid": reused_tor_service.get("pid"),
                    "service_started_epoch_ms": reused_tor_service.get(
                        "started_epoch_ms"
                    ),
                    "port": reused_tor_service.get("port"),
                    "gate": browser_launch_gate,
                }
                if tor_managed_ready.get("ok"):
                    latest_reused_tor_service = latest_managed_service_for_update(
                        Path(str(paths_dict["tor_service_json"])),
                        service=reused_tor_service,
                    )
                    plan["reused_tor_service"] = record_managed_service_ready(
                        latest_reused_tor_service,
                        gate=browser_launch_gate,
                        wait_result=tor_managed_ready,
                        actor="launcher_reused_open",
                    )
                    write_json(
                        Path(str(paths_dict["tor_service_json"])),
                        plan["reused_tor_service"],
                    )
                else:
                    tor_boot = tor_managed_ready
            elif browser_launch_gate == "tor_boot_100":
                gate_diagnostics = None
                if gate_diagnostics_enabled:
                    gate_diagnostics = reused_service_gate_diagnostics_start(
                        reused_tor_service=reused_tor_service,
                        ready_text=browser_launch_gate_ready_text("tor_boot_100"),
                    )
                if managed_service_ready_for_gate(
                    reused_tor_service,
                    "tor_boot_100",
                ):
                    tor_boot = managed_service_ready_result(
                        reused_tor_service,
                        gate="tor_boot_100",
                    )
                else:
                    tor_boot = wait_for_existing_service_ready_in_log(
                        pid=int(reused_tor_service["pid"]),
                        log_path=Path(str(reused_tor_service["tor_log"])),
                        timeout=180.0,
                        gate="tor_boot_100",
                        control_port=reused_tor_service.get("control_port"),
                        control_cookie_path=reused_tor_service.get("control_cookie_path"),
                        service_path=Path(str(paths_dict["tor_service_json"])),
                        expected_service=reused_tor_service,
                        ready_text=browser_launch_gate_ready_text("tor_boot_100"),
                        process_name="tor",
                    )
                if tor_boot.get("ok"):
                    latest_reused_tor_service = latest_managed_service_for_update(
                        Path(str(paths_dict["tor_service_json"])),
                        service=reused_tor_service,
                    )
                    plan["reused_tor_service"] = record_managed_service_ready(
                        latest_reused_tor_service,
                        gate="tor_boot_100",
                        wait_result=tor_boot,
                        actor="launcher_reused_open",
                    )
                    write_json(
                        Path(str(paths_dict["tor_service_json"])),
                        plan["reused_tor_service"],
                    )
                if gate_diagnostics is not None:
                    tor_boot = {
                        **tor_boot,
                        "diagnostics": finalize_reused_service_gate_diagnostics(
                            gate_diagnostics,
                            reused_tor_service=reused_tor_service,
                            wait_result=tor_boot,
                            wait_skipped=bool(
                                managed_service_ready_for_gate(
                                    reused_tor_service,
                                    "tor_boot_100",
                                )
                            ),
                        ),
                    }
            else:
                managed_open_settle = None
                reused_tor_service, managed_open_settle = maybe_settle_recently_warmed_service(
                    service_path=Path(str(paths_dict["tor_service_json"])),
                    reused_tor_service=reused_tor_service,
                    requested_gate=str(
                        plan.get("browser_launch_gate_requested")
                        or DEFAULT_BROWSER_LAUNCH_GATE
                    ),
                    target_gate=browser_launch_gate,
                    enabled=bool(plan.get("managed_open_settle_enabled", True)),
                )
                plan["reused_tor_service"] = reused_tor_service
                plan["managed_open_settle"] = managed_open_settle
                warm_browser_prestart = {
                    "enabled": bool(plan.get("warm_browser_prestart_enabled", False)),
                    "applied": False,
                }
                if isinstance(reused_prestarted_browser, dict):
                    warm_browser_prestart.update(
                        {
                            "available": True,
                            "pid": reused_prestarted_browser.get("pid"),
                            "marionette_port": reused_prestarted_browser.get(
                                "marionette_port"
                            ),
                            "initial_url": reused_prestarted_browser.get(
                                "initial_url"
                            ),
                        }
                    )
                elif warm_browser_prestart["enabled"]:
                    warm_browser_prestart["reason"] = "no reusable prestarted browser"
                plan["warm_browser_prestart"] = warm_browser_prestart
                managed_open_browser_overlap = {
                    "enabled": bool(
                        plan.get("managed_open_browser_overlap_enabled", False)
                    ),
                    "applied": False,
                    "initial_url": "about:blank",
                    "target_url": plan.get("url"),
                    "marionette_port": (
                        MANAGED_OPEN_BROWSER_OVERLAP_MARIONETTE_PORT
                    ),
                }
                overlap_reason = managed_open_browser_overlap_reason(
                    enabled=bool(
                        plan.get("managed_open_browser_overlap_enabled", False)
                    ),
                    reused_tor_service=reused_tor_service,
                    target_gate=browser_launch_gate,
                    url=str(plan.get("url") or ""),
                )
                overlap_adaptive_general_circuit_wait = (
                    overlap_reason is None
                    and not isinstance(reused_prestarted_browser, dict)
                    and not managed_service_ready_for_gate(
                        reused_tor_service,
                        browser_launch_gate,
                    )
                )
                managed_open_adaptive_general_circuit_wait = None
                if not overlap_adaptive_general_circuit_wait:
                    managed_open_adaptive_general_circuit_wait = (
                        consume_managed_open_adaptive_general_circuit_wait_report(
                            Path(str(paths_dict["state_root"]))
                            / "managed-open-adaptive-general-circuit-wait.json",
                            expected_service=reused_tor_service,
                            requested_timeout_seconds=float(
                                plan.get(
                                    "managed_open_adaptive_general_circuit_wait_timeout_seconds",
                                    0.0,
                                )
                            ),
                        )
                    )
                    if managed_open_adaptive_general_circuit_wait is None:
                        (
                            reused_tor_service,
                            managed_open_adaptive_general_circuit_wait,
                        ) = maybe_wait_for_managed_open_general_circuit(
                            service_path=Path(str(paths_dict["tor_service_json"])),
                            reused_tor_service=reused_tor_service,
                            requested_gate=str(
                                plan.get("browser_launch_gate_requested")
                                or DEFAULT_BROWSER_LAUNCH_GATE
                            ),
                            target_gate=browser_launch_gate,
                            timeout_seconds=float(
                                plan.get(
                                    "managed_open_adaptive_general_circuit_wait_timeout_seconds",
                                    0.0,
                                )
                            ),
                            enabled=bool(
                                float(
                                    plan.get(
                                        (
                                            "managed_open_adaptive_general_circuit_wait_"
                                            "timeout_seconds"
                                        ),
                                        0.0,
                                    )
                                )
                                > 0
                            ),
                        )
                    else:
                        reused_tor_service = latest_managed_service_for_update(
                            Path(str(paths_dict["tor_service_json"])),
                            service=reused_tor_service,
                        )
                plan["reused_tor_service"] = reused_tor_service
                plan["managed_open_adaptive_general_circuit_wait"] = (
                    managed_open_adaptive_general_circuit_wait
                )
                if overlap_reason is not None:
                    managed_open_browser_overlap["reason"] = overlap_reason
                elif isinstance(reused_prestarted_browser, dict):
                    managed_open_browser_overlap["reason"] = (
                        "superseded by warm-browser-prestart"
                    )
                elif not managed_service_ready_for_gate(
                    reused_tor_service,
                    browser_launch_gate,
                ):
                    start_browser_runtime_reset_cleanup(
                        browser_runtime_reset_cleanup
                    )
                    overlap_browser_started = time.monotonic()
                    try:
                        (
                            browser_proc,
                            browser_lines,
                            overlap_browser_client,
                            overlap_report,
                            reused_tor_service,
                            overlap_adaptive_wait_report,
                        ) = start_managed_open_browser_overlap_session(
                            plan,
                            paths_dict=paths_dict,
                            service_path=Path(str(paths_dict["tor_service_json"])),
                            reused_tor_service=reused_tor_service,
                        )
                    except Exception as exc:  # noqa: BLE001 - experimental proof path.
                        managed_open_browser_overlap.update(
                            {
                                "ok": False,
                                "phase": "session_start",
                                "error": f"{type(exc).__name__}: {exc}",
                            }
                        )
                        plan["managed_open_browser_overlap"] = (
                            managed_open_browser_overlap
                        )
                        finalize_browser_runtime_reset_cleanup(
                            browser_runtime_reset_cleanup
                        )
                        print(f"wrote {launch_json}")
                        print(
                            json.dumps(
                                compact_launch_summary(plan),
                                indent=2,
                                sort_keys=True,
                            )
                        )
                        return 1
                    if overlap_adaptive_wait_report is not None:
                        plan["managed_open_adaptive_general_circuit_wait"] = (
                            overlap_adaptive_wait_report
                        )
                    plan["reused_tor_service"] = reused_tor_service
                    managed_open_browser_overlap.update(overlap_report)
                else:
                    managed_open_browser_overlap["reason"] = (
                        "already ready for target gate"
                    )
                plan["managed_open_browser_overlap"] = managed_open_browser_overlap
                gate_diagnostics = None
                wait_skipped = False
                overlap_gate_wait_result = None
                overlap_adaptive_wait = plan.get(
                    "managed_open_adaptive_general_circuit_wait"
                )
                if isinstance(overlap_adaptive_wait, dict):
                    candidate_gate_wait_result = overlap_adaptive_wait.get(
                        "browser_launch_gate_wait"
                    )
                    if isinstance(candidate_gate_wait_result, dict):
                        overlap_gate_wait_result = candidate_gate_wait_result
                if gate_diagnostics_enabled:
                    gate_diagnostics = reused_service_gate_diagnostics_start(
                        reused_tor_service=reused_tor_service,
                        ready_text=browser_launch_gate_ready_text(browser_launch_gate),
                    )
                if managed_service_ready_for_gate(
                    reused_tor_service,
                    browser_launch_gate,
                ):
                    wait_skipped = True
                    browser_launch_gate_result = managed_service_ready_result(
                        reused_tor_service,
                        gate=browser_launch_gate,
                    )
                elif overlap_gate_wait_result is not None:
                    wait_skipped = True
                    browser_launch_gate_result = overlap_gate_wait_result
                elif bool(managed_open_browser_overlap.get("launched_on_target_url")):
                    wait_skipped = True
                    browser_launch_gate_result = {
                        "ok": True,
                        "seconds": 0.0,
                        "polls": 0,
                        "reused_service": True,
                        "ready_gate": browser_launch_gate,
                        "ready_via_active_target_launch": True,
                        "reason": "active_target_launch",
                        "skipped": True,
                        "lines": [],
                        "signal_lines": [],
                    }
                else:
                    browser_launch_gate_result = (
                        wait_for_existing_service_ready_in_log(
                            pid=int(reused_tor_service["pid"]),
                            log_path=Path(str(reused_tor_service["tor_log"])),
                            timeout=180.0,
                            gate=browser_launch_gate,
                            control_port=reused_tor_service.get("control_port"),
                            control_cookie_path=reused_tor_service.get("control_cookie_path"),
                            service_path=Path(str(paths_dict["tor_service_json"])),
                            expected_service=reused_tor_service,
                            ready_text=browser_launch_gate_ready_text(
                                browser_launch_gate
                            ),
                            process_name="tor",
                        )
                    )
                if gate_diagnostics is not None:
                    browser_launch_gate_result = {
                        **browser_launch_gate_result,
                        "diagnostics": finalize_reused_service_gate_diagnostics(
                            gate_diagnostics,
                            reused_tor_service=reused_tor_service,
                            wait_result=browser_launch_gate_result,
                            wait_skipped=wait_skipped,
                        ),
                    }
                plan["tor_browser_launch_gate"] = {
                    "gate": browser_launch_gate,
                    **browser_launch_gate_result,
                }
                if not browser_launch_gate_result.get("ok"):
                    tor_boot = browser_launch_gate_result
                elif isinstance(reused_prestarted_browser, dict):
                    connect_timeout = min(
                        30.0,
                        max(10.0, float(plan.get("browser_timeout_seconds", 0.0)) + 5.0),
                    )
                    warm_browser_prestart = plan.get("warm_browser_prestart")
                    if not isinstance(warm_browser_prestart, dict):
                        warm_browser_prestart = {
                            "enabled": bool(
                                plan.get("warm_browser_prestart_enabled", False)
                            ),
                        }
                        plan["warm_browser_prestart"] = warm_browser_prestart
                    warm_browser_prestart["connect_timeout_seconds"] = connect_timeout
                    try:
                        prestarted_browser_client = connect_existing_marionette_session(
                            pid=int(reused_prestarted_browser["pid"]),
                            marionette_port=int(
                                reused_prestarted_browser["marionette_port"]
                            ),
                            timeout=connect_timeout,
                        )
                    except Exception as exc:  # noqa: BLE001 - lab-only path.
                        warm_browser_prestart.update(
                            {
                                "ok": False,
                                "phase": "connect",
                                "error": f"{type(exc).__name__}: {exc}",
                                "fallback_to_normal_launch": True,
                            }
                        )
                        clear_prestarted_browser_metadata(
                            Path(str(paths_dict["prestarted_browser_json"]))
                        )
                        plan["reused_prestarted_browser"] = None
                        reused_prestarted_browser = None
                    else:
                        warm_browser_prestart.update(
                            {
                                "applied": True,
                                "ok": True,
                            }
                        )
                        clear_prestarted_browser_metadata(
                            Path(str(paths_dict["prestarted_browser_json"]))
                        )
                        plan["reused_prestarted_browser"] = None
                        prestarted_browser_started = time.monotonic()
                        browser_proc = ExistingBrowserProcess(
                            int(reused_prestarted_browser["pid"])
                        )
                        browser_lines = queue.Queue()
        elif leave_tor_running:
            tor_proc = start_c_tor_detached(
                tor_bin=Path(str(plan["tor_bin"])),
                torrc=Path(str(paths_dict["torrc"])),
                log_path=Path(str(paths_dict["tor_log"])),
            )
            pending_managed_service = managed_tor_service_metadata(
                plan,
                pid=tor_proc.pid,
            )
            write_json(
                Path(str(paths_dict["tor_service_json"])),
                pending_managed_service,
            )
            if plan.get("start_managed_tor_only"):
                promoter_report = (
                    maybe_start_runtime_helper_gate_promoter(
                        Path(str(paths_dict["state_root"]))
                    )
                )
                plan["runtime_helper_gate_promoter"] = promoter_report
                if promoter_report.get("requested"):
                    pending_managed_service[
                        "runtime_helper_gate_promoter_requested"
                    ] = True
                    pending_managed_service[
                        "runtime_helper_gate_promoter_requested_epoch_ms"
                    ] = round(time.time() * 1000, 3)
                    if isinstance(promoter_report.get("mode"), str):
                        pending_managed_service[
                            "runtime_helper_gate_promoter_mode"
                        ] = promoter_report["mode"]
                    pending_managed_service[
                        "runtime_helper_gate_promoter_active_after_request"
                    ] = bool(promoter_report.get("active_after_request"))
                    write_json(
                        Path(str(paths_dict["tor_service_json"])),
                        pending_managed_service,
                    )
            initial_gate = (
                browser_launch_gate
                if plan.get("start_managed_tor_only") and leave_tor_running
                else "tor_boot_100"
                if browser_launch_gate == "tor_boot_100"
                else browser_launch_gate
            )
            gate_or_boot = wait_for_ready_in_log(
                proc=tor_proc,
                log_path=Path(str(paths_dict["tor_log"])),
                timeout=180.0,
                ready_text=browser_launch_gate_ready_text(initial_gate),
                process_name="tor",
            )
            if plan.get("start_managed_tor_only") and leave_tor_running:
                tor_managed_ready = {
                    "gate": initial_gate,
                    **gate_or_boot,
                }
                plan["tor_managed_ready"] = tor_managed_ready
                if tor_managed_ready.get("ok"):
                    keep_tor_running = True
                    assert pending_managed_service is not None
                    latest_pending_managed_service = latest_managed_service_for_update(
                        Path(str(paths_dict["tor_service_json"])),
                        service=pending_managed_service,
                    )
                    plan["reused_tor_service"] = record_managed_service_ready(
                        latest_pending_managed_service,
                        gate=initial_gate,
                        wait_result=tor_managed_ready,
                        actor="launcher_managed_warm",
                    )
                    write_json(
                        Path(str(paths_dict["tor_service_json"])),
                        plan["reused_tor_service"],
                    )
                else:
                    tor_boot = tor_managed_ready
            elif browser_launch_gate == "tor_boot_100":
                tor_boot = gate_or_boot
                if tor_boot.get("ok"):
                    keep_tor_running = True
                    assert pending_managed_service is not None
                    latest_pending_managed_service = latest_managed_service_for_update(
                        Path(str(paths_dict["tor_service_json"])),
                        service=pending_managed_service,
                    )
                    plan["reused_tor_service"] = record_managed_service_ready(
                        latest_pending_managed_service,
                        gate="tor_boot_100",
                        wait_result=tor_boot,
                        actor="launcher_new_tor",
                    )
                    write_json(
                        Path(str(paths_dict["tor_service_json"])),
                        plan["reused_tor_service"],
                    )
            else:
                plan["tor_browser_launch_gate"] = {
                    "gate": browser_launch_gate,
                    **gate_or_boot,
                }
                if not gate_or_boot.get("ok"):
                    tor_boot = gate_or_boot
            if tor_boot is not None and tor_boot.get("ok"):
                keep_tor_running = True
                if pending_managed_service is not None:
                    latest_pending_managed_service = latest_managed_service_for_update(
                        Path(str(paths_dict["tor_service_json"])),
                        service=pending_managed_service,
                    )
                    plan["reused_tor_service"] = record_managed_service_ready(
                        latest_pending_managed_service,
                        gate="tor_boot_100",
                        wait_result=tor_boot,
                        actor="launcher_new_tor",
                    )
                    write_json(
                        Path(str(paths_dict["tor_service_json"])),
                        plan["reused_tor_service"],
                    )
        else:
            tor_proc, tor_lines = start_c_tor_launcher(
                tor_bin=Path(str(plan["tor_bin"])),
                torrc=Path(str(paths_dict["torrc"])),
            )
            if browser_launch_gate == "tor_boot_100":
                tor_boot = wait_for_line(
                    tor_proc,
                    tor_lines,
                    timeout=180.0,
                    ready_text=browser_launch_gate_ready_text(browser_launch_gate),
                    process_name="tor",
                )
            else:
                browser_launch_gate_result = wait_for_line(
                    tor_proc,
                    tor_lines,
                    timeout=180.0,
                    ready_text=browser_launch_gate_ready_text(browser_launch_gate),
                    process_name="tor",
                )
                plan["tor_browser_launch_gate"] = {
                    "gate": browser_launch_gate,
                    **browser_launch_gate_result,
                }
                if not browser_launch_gate_result.get("ok"):
                    tor_boot = browser_launch_gate_result
        if tor_boot is not None:
            plan["tor_boot"] = tor_boot
        if tor_boot is not None and not tor_boot.get("ok"):
            finalize_browser_runtime_reset_cleanup(browser_runtime_reset_cleanup)
            print(f"wrote {launch_json}")
            print(json.dumps(compact_launch_summary(plan), indent=2, sort_keys=True))
            return 1

        used_existing_managed_service = isinstance(reused_tor_service, dict)
        seed_root = plan.get("dir_cache_seed_root")
        dir_cache_seed_update_deferred = False
        if isinstance(seed_root, str):
            dir_cache_seed_root = Path(seed_root)
            dir_cache_seed_apply = plan.get("dir_cache_seed_apply")
            seed_disabled = (
                isinstance(dir_cache_seed_apply, dict)
                and dir_cache_seed_apply.get("reason") == "disabled by flag"
            )
            if seed_disabled:
                plan["dir_cache_seed_update"] = {
                    "ok": True,
                    "updated": False,
                    "reason": "disabled by flag",
                    "seed_root": seed_root,
                }
            elif used_existing_managed_service:
                plan["dir_cache_seed_update"] = {
                    "ok": True,
                    "updated": False,
                    "reason": "reused managed tor service",
                    "seed_root": seed_root,
                }
            elif plan.get("start_managed_tor_only"):
                managed_ready_gate = start_managed_dir_cache_seed_refresh_gate(plan)
                if gate_reaches_dir_cache_seed_refresh_threshold(managed_ready_gate):
                    plan["dir_cache_seed_update"] = update_seed_from_data_dir(
                        Path(str(paths_dict["data_dir"])),
                        dir_cache_seed_root,
                    )
                else:
                    plan["dir_cache_seed_update"] = {
                        "ok": True,
                        "updated": False,
                        "reason": (
                            "managed tor has not reached tor_boot_95 for dir-cache "
                            "seed refresh"
                        ),
                        "seed_root": seed_root,
                        "ready_gate": managed_ready_gate,
                    }
            else:
                dir_cache_seed_update_deferred = True
                plan["dir_cache_seed_update"] = {
                    "ok": True,
                    "updated": False,
                    "reason": "deferred until post-browser tor boot",
                    "seed_root": seed_root,
                }
            plan["dir_cache_seed_status"] = describe_seed(dir_cache_seed_root)

        if plan.get("start_managed_tor_only"):
            warm_browser_prestart = {
                "enabled": bool(plan.get("warm_browser_prestart_enabled", False)),
                "applied": False,
            }
            if warm_browser_prestart["enabled"]:
                if isinstance(reused_prestarted_browser, dict):
                    warm_browser_prestart.update(
                        {
                            "reused_existing": True,
                            "pid": reused_prestarted_browser.get("pid"),
                            "marionette_port": reused_prestarted_browser.get(
                                "marionette_port"
                            ),
                            "initial_url": reused_prestarted_browser.get(
                                "initial_url"
                            ),
                        }
                    )
                elif keep_tor_running or isinstance(reused_tor_service, dict):
                    try:
                        warm_browser_prestart.update(
                            start_warm_browser_prestart(
                                plan,
                                paths_dict=paths_dict,
                            )
                        )
                    except Exception as exc:  # noqa: BLE001 - lab-only path.
                        warm_browser_prestart.update(
                            {
                                "ok": False,
                                "error": f"{type(exc).__name__}: {exc}",
                            }
                        )
                        plan["warm_browser_prestart"] = warm_browser_prestart
                        finalize_browser_runtime_reset_cleanup(
                            browser_runtime_reset_cleanup
                        )
                        print(f"wrote {launch_json}")
                        print(
                            json.dumps(
                                compact_launch_summary(plan),
                                indent=2,
                                sort_keys=True,
                            )
                        )
                        return 1
                else:
                    warm_browser_prestart["reason"] = (
                        "managed tor is not staying warm"
                    )
            plan["warm_browser_prestart"] = warm_browser_prestart
            browser_startup_seed_root = plan.get("browser_startup_seed_root")
            if isinstance(browser_startup_seed_root, str):
                browser_seed_apply = plan.get("browser_startup_seed_apply")
                browser_seed_disabled = (
                    isinstance(browser_seed_apply, dict)
                    and browser_seed_apply.get("reason") == "disabled by flag"
                )
                if browser_seed_disabled:
                    plan["browser_startup_seed_update"] = {
                        "ok": True,
                        "updated": False,
                        "reason": "disabled by flag",
                        "seed_root": browser_startup_seed_root,
                    }
                else:
                    plan["browser_startup_seed_update"] = {
                        "ok": True,
                        "updated": False,
                        "reason": (
                            "background browser still running"
                            if warm_browser_prestart["applied"]
                            or warm_browser_prestart.get("reused_existing")
                            else "browser launch skipped"
                        ),
                        "seed_root": browser_startup_seed_root,
                    }
                plan["browser_startup_seed_status"] = describe_browser_startup_seed(
                    Path(browser_startup_seed_root)
                )
            if isinstance(plan.get("tor_managed_ready"), dict):
                ready_gate = plan["tor_managed_ready"].get("gate")
                if warm_browser_prestart["applied"] or warm_browser_prestart.get(
                    "reused_existing"
                ):
                    note = (
                        "managed tor is ready at "
                        f"{ready_gate}; background browser prestart is ready"
                    )
                else:
                    note = (
                        "managed tor is ready at "
                        f"{ready_gate}; browser launch skipped as requested"
                    )
            elif keep_tor_running or isinstance(reused_tor_service, dict):
                if warm_browser_prestart["applied"] or warm_browser_prestart.get(
                    "reused_existing"
                ):
                    note = "managed tor is warm; background browser prestart started"
                else:
                    note = "managed tor is warm; browser launch skipped as requested"
            else:
                note = (
                    "tor bootstrapped successfully; browser launch skipped and "
                    "tor will stop as requested"
                )
            plan["browser"] = {
                "ok": True,
                "skipped": True,
                "timed_out": False,
                "interrupted": False,
                "note": note,
            }
            finalize_browser_runtime_reset_cleanup(browser_runtime_reset_cleanup)
            print(f"wrote {launch_json}")
            print(json.dumps(compact_launch_summary(plan), indent=2, sort_keys=True))
            return 0

        target_navigation_keeper: dict[str, object] | None = None
        if prestarted_browser_client is not None:
            navigate_result = navigate_managed_open_browser_overlap_session(
                prestarted_browser_client,
                url=str(plan["url"]),
            )
            warm_browser_prestart = plan.get("warm_browser_prestart")
            if isinstance(warm_browser_prestart, dict):
                warm_browser_prestart["navigate"] = navigate_result
            if navigate_result.get("ok") is not True:
                plan["browser"] = {
                    "ok": False,
                    "timed_out": False,
                    "interrupted": False,
                    "error": "warm-browser-prestart navigation failed",
                }
                finalize_browser_runtime_reset_cleanup(
                    browser_runtime_reset_cleanup
                )
                print(f"wrote {launch_json}")
                print(
                    json.dumps(
                        compact_launch_summary(plan),
                        indent=2,
                        sort_keys=True,
                    )
                )
                return 1
            browser_started = (
                prestarted_browser_started
                if isinstance(prestarted_browser_started, (int, float))
                else time.monotonic()
            )
            if str(plan["url"]).startswith(("http://", "https://")):
                target_navigation_keeper = start_target_navigation_keeper(
                    prestarted_browser_client,
                    url=str(plan["url"]),
                )
        elif overlap_browser_client is not None or (
            browser_proc is not None
            and isinstance(plan.get("managed_open_browser_overlap"), dict)
            and bool(
                plan["managed_open_browser_overlap"].get("launched_on_target_url")
            )
        ):
            overlap_report = plan.get("managed_open_browser_overlap")
            overlap_initial_url = (
                overlap_report.get("initial_url")
                if isinstance(overlap_report, dict)
                else None
            )
            target_url = str(plan["url"])
            eager_target_navigation = (
                overlap_report.get("eager_target_navigation")
                if isinstance(overlap_report, dict)
                else None
            )
            if (
                isinstance(eager_target_navigation, dict)
                and eager_target_navigation.get("ok") is True
            ):
                navigate_result = {
                    **eager_target_navigation,
                    "reason": "eager_target_navigation",
                    "started_during_overlap_session": True,
                }
            elif isinstance(overlap_initial_url, str) and overlap_initial_url == target_url:
                navigate_result = {
                    "ok": True,
                    "skipped": True,
                    "seconds": 0.0,
                    "target_url": target_url,
                    "reason": "launched_on_target_url",
                }
            else:
                navigate_result = navigate_managed_open_browser_overlap_session(
                    overlap_browser_client,
                    url=target_url,
                )
            if isinstance(overlap_report, dict):
                overlap_report["navigate"] = navigate_result
            if navigate_result.get("ok") is not True:
                plan["browser"] = {
                    "ok": False,
                    "timed_out": False,
                    "interrupted": False,
                    "error": "managed-open browser overlap navigation failed",
                }
                finalize_browser_runtime_reset_cleanup(
                    browser_runtime_reset_cleanup
                )
                print(f"wrote {launch_json}")
                print(
                    json.dumps(
                        compact_launch_summary(plan),
                        indent=2,
                        sort_keys=True,
                    )
                )
                return 1
            browser_started = (
                overlap_browser_started
                if isinstance(overlap_browser_started, (int, float))
                else time.monotonic()
            )
            if overlap_browser_client is not None and str(plan["url"]).startswith(
                ("http://", "https://")
            ):
                target_navigation_keeper = start_target_navigation_keeper(
                    overlap_browser_client,
                    url=str(plan["url"]),
                )
        else:
            start_browser_runtime_reset_cleanup(browser_runtime_reset_cleanup)
            browser_started = time.monotonic()
            browser_proc, browser_lines = start_browser_launcher(
                command=[str(part) for part in plan["browser_command"]],
                env=browser_launch_env(
                    os.environ.copy(),
                    home_dir=Path(str(paths_dict["browser_home_dir"])),
                    port=int(plan["port"]),
                ),
            )
        if plan.get("stream_isolation_probe_enabled"):
            plan["browser_stream_isolation_probe"] = record_stream_isolation_probe(
                control_port=plan.get("control_port"),
                control_cookie_path=plan.get("control_cookie_path"),
                url=str(plan["url"]),
                timeout_seconds=float(plan.get("stream_isolation_probe_timeout_seconds", 0.0)),
            )
        browser_result = wait_for_browser_exit(
            proc=browser_proc,
            lines=browser_lines,
            timeout_seconds=float(plan["browser_timeout_seconds"]),
            control_port=plan.get("control_port"),
            control_cookie_path=plan.get("control_cookie_path"),
            target_url=plan.get("url"),
            target_stream_proof_enabled=(
                os.environ.get(TARGET_STREAM_PROOF_ENABLED_ENV) == "1"
            ),
        )
        browser_result["elapsed_seconds"] = round(
            time.monotonic() - browser_started, 3
        )
        finished_keeper = finish_target_navigation_keeper(target_navigation_keeper)
        if finished_keeper is not None:
            plan["target_navigation_keeper"] = finished_keeper
            browser_result["target_navigation_keeper"] = finished_keeper
        runtime_quality_proof = collect_browser_runtime_quality_proof(
            client=prestarted_browser_client or overlap_browser_client,
            browser_profile_dir=Path(str(paths_dict["browser_profile_dir"])),
            target_url=str(plan["url"]),
        )
        plan["browser_runtime_quality_proof"] = runtime_quality_proof
        if runtime_quality_proof.get("enabled") is True:
            plan["browser_quality_prefs"] = runtime_quality_proof.get(
                "browser_quality_prefs"
            )
            plan["runtime_proxy_prefs"] = runtime_quality_proof.get(
                "runtime_proxy_prefs"
            )
            plan["effective_proxy_prefs"] = runtime_quality_proof.get(
                "effective_proxy_prefs"
            )
            plan["browser_fingerprint_snapshot"] = runtime_quality_proof.get(
                "browser_fingerprint_snapshot"
            )
        overlap_report = plan.get("managed_open_browser_overlap")
        if (
            isinstance(overlap_report, dict)
            and overlap_report.get("launched_on_target_url")
        ):
            target_load_probe = maybe_collect_target_launch_browser_probe(
                browser_proc=browser_proc,
                overlap_report=overlap_report,
                target_url=str(plan.get("url") or ""),
            )
            overlap_report["target_load_probe"] = target_load_probe
            browser_result["target_load_probe"] = target_load_probe
        plan["browser"] = browser_result
        if tor_boot is None:
            if browser_result.get("ok") is True:
                if tor_lines is None and isinstance(reused_tor_service, dict):
                    if managed_service_ready_for_gate(
                        reused_tor_service,
                        "tor_boot_100",
                    ):
                        full_boot_wait = managed_service_ready_result(
                            reused_tor_service,
                            gate="tor_boot_100",
                        )
                    else:
                        full_boot_wait = wait_for_existing_service_ready_in_log(
                            pid=int(reused_tor_service["pid"]),
                            log_path=Path(str(reused_tor_service["tor_log"])),
                            timeout=180.0,
                            gate="tor_boot_100",
                            control_port=reused_tor_service.get("control_port"),
                            control_cookie_path=reused_tor_service.get("control_cookie_path"),
                            service_path=Path(str(paths_dict["tor_service_json"])),
                            expected_service=reused_tor_service,
                            ready_text=browser_launch_gate_ready_text("tor_boot_100"),
                            process_name="tor",
                        )
                elif tor_lines is None:
                    full_boot_wait = wait_for_ready_in_log(
                        proc=tor_proc,
                        log_path=Path(str(paths_dict["tor_log"])),
                        timeout=180.0,
                        ready_text=browser_launch_gate_ready_text("tor_boot_100"),
                        process_name="tor",
                    )
                else:
                    full_boot_wait = wait_for_line(
                        tor_proc,
                        tor_lines,
                        timeout=180.0,
                        ready_text=browser_launch_gate_ready_text("tor_boot_100"),
                        process_name="tor",
                    )
                tor_boot = combine_tor_wait_results(
                    plan["tor_browser_launch_gate"],
                    full_boot_wait,
                )
                if (
                    tor_boot.get("ok")
                    and leave_tor_running
                ):
                    keep_tor_running = True
                    if isinstance(reused_tor_service, dict):
                        latest_reused_tor_service = latest_managed_service_for_update(
                            Path(str(paths_dict["tor_service_json"])),
                            service=reused_tor_service,
                        )
                        plan["reused_tor_service"] = record_managed_service_ready(
                            latest_reused_tor_service,
                            gate="tor_boot_100",
                            wait_result=tor_boot,
                            actor="launcher_reused_open",
                        )
                    elif pending_managed_service is not None:
                        latest_pending_managed_service = latest_managed_service_for_update(
                            Path(str(paths_dict["tor_service_json"])),
                            service=pending_managed_service,
                        )
                        plan["reused_tor_service"] = record_managed_service_ready(
                            latest_pending_managed_service,
                            gate="tor_boot_100",
                            wait_result=tor_boot,
                            actor="launcher_new_tor",
                        )
                    if isinstance(plan.get("reused_tor_service"), dict):
                        write_json(
                            Path(str(paths_dict["tor_service_json"])),
                            plan["reused_tor_service"],
                        )
            else:
                tor_boot = {
                    "ok": False,
                    "error": (
                        "browser failed before tor finished bootstrapping to 100%"
                    ),
                    "launch_gate": browser_launch_gate,
                }
            plan["tor_boot"] = tor_boot
        browser_startup_seed_root = plan.get("browser_startup_seed_root")
        if isinstance(browser_startup_seed_root, str):
            browser_seed_apply = plan.get("browser_startup_seed_apply")
            browser_seed_disabled = (
                isinstance(browser_seed_apply, dict)
                and browser_seed_apply.get("reason") == "disabled by flag"
            )
            if browser_seed_disabled:
                plan["browser_startup_seed_update"] = {
                    "ok": True,
                    "updated": False,
                    "reason": "disabled by flag",
                    "seed_root": browser_startup_seed_root,
                }
            elif browser_result.get("ok") is not True:
                plan["browser_startup_seed_update"] = {
                    "ok": True,
                    "updated": False,
                    "reason": "browser run failed",
                    "seed_root": browser_startup_seed_root,
                }
            else:
                plan["browser_startup_seed_update"] = (
                    update_browser_startup_seed_from_profile(
                        Path(str(paths_dict["browser_profile_dir"])),
                        Path(browser_startup_seed_root),
                    )
                )
            plan["browser_startup_seed_status"] = describe_browser_startup_seed(
                Path(browser_startup_seed_root)
            )
        if (
            dir_cache_seed_update_deferred
            and isinstance(seed_root, str)
        ):
            dir_cache_seed_root = Path(seed_root)
            if tor_boot is None or tor_boot.get("ok") is not True:
                plan["dir_cache_seed_update"] = {
                    "ok": True,
                    "updated": False,
                    "reason": "tor boot failed before deferred dir-cache seed refresh",
                    "seed_root": seed_root,
                }
            else:
                plan["dir_cache_seed_update"] = update_seed_from_data_dir(
                    Path(str(paths_dict["data_dir"])),
                    dir_cache_seed_root,
                )
            plan["dir_cache_seed_status"] = describe_seed(dir_cache_seed_root)
        print(f"wrote {launch_json}")
        print(json.dumps(compact_launch_summary(plan), indent=2, sort_keys=True))
        return (
            0
            if browser_result.get("ok") and tor_boot is not None and tor_boot.get("ok")
            else 1
        )
    finally:
        if prestarted_browser_client is not None:
            try:
                prestarted_browser_client.close()
            except Exception:
                pass
        if overlap_browser_client is not None:
            try:
                overlap_browser_client.close()
            except Exception:
                pass
        if browser_proc is not None:
            stop_process_tree(browser_proc)
        if tor_proc is not None and not keep_tor_running:
            stop_process(tor_proc)
            if pending_managed_service is not None:
                try:
                    Path(str(paths_dict["tor_service_json"])).unlink()
                except OSError:
                    pass
        if browser_lines is not None:
            browser_tail = drain_queue(browser_lines)[-40:]
            if browser_tail:
                browser = plan.setdefault("browser", {})
                if isinstance(browser, dict):
                    browser["output_tail"] = browser_tail
        if tor_lines is not None:
            tor_tail = drain_queue(tor_lines)[-80:]
            if tor_tail:
                plan["tor_output_tail"] = tor_tail
        elif Path(str(paths_dict["tor_log"])).exists():
            detached_tail = tail_lines(Path(str(paths_dict["tor_log"])), limit=80)
            if detached_tail:
                plan["tor_output_tail"] = detached_tail
        finalize_browser_runtime_reset_cleanup(browser_runtime_reset_cleanup)
        write_plan(launch_json, plan)


def wait_for_browser_exit(
    *,
    proc: subprocess.Popen[str],
    lines: queue.Queue[str],
    timeout_seconds: float,
    control_port: object = None,
    control_cookie_path: object = None,
    target_url: object = None,
    target_stream_proof_enabled: bool = False,
    target_stream_poll_interval_seconds: float = 0.1,
) -> dict[str, object]:
    started = time.monotonic()
    seen: list[str] = []
    target_substrings = target_stream_substrings(target_url)
    target_stream_probe_enabled = (
        target_stream_proof_enabled
        and isinstance(control_port, int)
        and isinstance(control_cookie_path, str)
        and bool(target_substrings)
    )
    target_stream_probe_polls = 0
    target_stream_probe_error: str | None = None
    target_stream_snapshot: dict[str, object] | None = None
    matched_target_stream_snapshot: dict[str, object] | None = None
    target_stream_poll_started: float | None = None
    control_client: TorControlClient | None = None
    known_stream_ids: set[str] = set()

    def close_control_client() -> None:
        nonlocal control_client
        if control_client is None:
            return
        try:
            control_client.close()
        except OSError:
            pass
        control_client = None

    def attach_target_stream_proof(report: dict[str, object]) -> dict[str, object]:
        if not target_stream_proof_enabled:
            return report
        report["target_stream_proof_enabled"] = target_stream_probe_enabled
        report["target_substrings"] = list(target_substrings)
        report["target_stream_probe_polls"] = target_stream_probe_polls
        if target_stream_probe_error is not None:
            report["target_stream_probe_error"] = target_stream_probe_error
        snapshot = matched_target_stream_snapshot or target_stream_snapshot
        if snapshot is not None:
            report["target_stream_snapshot"] = snapshot
        return report

    def maybe_poll_target_stream_snapshot(*, force: bool = False) -> None:
        nonlocal control_client
        nonlocal matched_target_stream_snapshot
        nonlocal target_stream_poll_started
        nonlocal target_stream_probe_error
        nonlocal target_stream_probe_polls
        nonlocal target_stream_snapshot
        if not target_stream_probe_enabled:
            return
        now = time.monotonic()
        if (
            not force
            and target_stream_poll_started is not None
            and (now - target_stream_poll_started) < target_stream_poll_interval_seconds
        ):
            return
        target_stream_poll_started = now
        if control_client is None:
            try:
                control_client = TorControlClient.connect(
                    host="127.0.0.1",
                    port=control_port,
                    cookie_path=Path(control_cookie_path),
                )
            except (FileNotFoundError, OSError, RuntimeError, EOFError) as exc:
                target_stream_probe_error = f"{type(exc).__name__}: {exc}"
                return
        try:
            snapshot = read_user_stream_snapshot_with_client(
                control_client,
                target_substrings=target_substrings,
                known_stream_ids=known_stream_ids,
            )
        except (OSError, RuntimeError, EOFError) as exc:
            target_stream_probe_error = f"{type(exc).__name__}: {exc}"
            close_control_client()
            return
        target_stream_probe_polls += 1
        target_stream_snapshot = snapshot
        if user_stream_snapshot_observed(snapshot):
            matched_target_stream_snapshot = snapshot
            target_stream_probe_error = None
    try:
        while True:
            maybe_poll_target_stream_snapshot()
            if proc.poll() is not None:
                exit_code = proc.returncode
                return attach_target_stream_proof(
                    {
                        "ok": exit_code == 0,
                        "exit_code": exit_code,
                        "timed_out": False,
                        "interrupted": False,
                        "output_tail": seen[-40:],
                    }
                )
            if timeout_seconds > 0 and time.monotonic() - started >= timeout_seconds:
                maybe_poll_target_stream_snapshot(force=True)
                return attach_target_stream_proof(
                    {
                        "ok": True,
                        "exit_code": None,
                        "timed_out": True,
                        "interrupted": False,
                        "note": (
                            f"browser timeout reached after {timeout_seconds:.3f}s; "
                            "launcher stopped browser as requested"
                        ),
                        "output_tail": seen[-40:],
                    }
                )
            try:
                line = lines.get(timeout=PROCESS_POLL_INTERVAL_SECONDS)
            except queue.Empty:
                continue
            seen.append(line)
    except KeyboardInterrupt:
        return attach_target_stream_proof(
            {
                "ok": False,
                "exit_code": None,
                "timed_out": False,
                "interrupted": True,
                "error": "interrupted by user",
                "output_tail": seen[-40:],
            }
        )
    finally:
        close_control_client()


def compact_launch_summary(plan: dict[str, object]) -> dict[str, object]:
    return {
        "browser": plan.get("browser"),
        "browser_launch_gate": plan.get("browser_launch_gate"),
        "browser_launch_gate_requested": plan.get("browser_launch_gate_requested"),
        "browser_default_pref_check": plan.get("browser_default_pref_check"),
        "browser_runtime_reset": plan.get("browser_runtime_reset"),
        "browser_startup_seed_apply": plan.get("browser_startup_seed_apply"),
        "browser_startup_seed_update": plan.get("browser_startup_seed_update"),
        "dir_cache_seed_apply": plan.get("dir_cache_seed_apply"),
        "dir_cache_seed_update": plan.get("dir_cache_seed_update"),
        "leave_tor_running": plan.get("leave_tor_running"),
        "managed_open_browser_overlap": plan.get("managed_open_browser_overlap"),
        "managed_open_browser_overlap_enabled": plan.get(
            "managed_open_browser_overlap_enabled"
        ),
        "managed_open_adaptive_general_circuit_wait": plan.get(
            "managed_open_adaptive_general_circuit_wait"
        ),
        "managed_open_adaptive_general_circuit_wait_timeout_seconds": plan.get(
            "managed_open_adaptive_general_circuit_wait_timeout_seconds"
        ),
        "managed_open_settle": plan.get("managed_open_settle"),
        "managed_open_settle_enabled": plan.get("managed_open_settle_enabled"),
        "warm_browser_prestart": plan.get("warm_browser_prestart"),
        "warm_browser_prestart_enabled": plan.get("warm_browser_prestart_enabled"),
        "port": plan.get("port"),
        "tor_browser_launch_gate": plan.get("tor_browser_launch_gate"),
        "tor_boot": plan.get("tor_boot"),
        "torrc_quality": plan.get("torrc_quality"),
        "url": plan.get("url"),
    }


def write_json(path: Path, payload: dict[str, object]) -> None:
    atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def managed_tor_service_metadata(
    plan: dict[str, object],
    *,
    pid: int,
) -> dict[str, object]:
    paths_dict = plan.get("paths", {})
    assert isinstance(paths_dict, dict)
    return {
        "pid": pid,
        "port": plan["port"],
        "control_port": plan.get("control_port"),
        "tor_bin": plan["tor_bin"],
        "torrc": paths_dict["torrc"],
        "tor_log": paths_dict["tor_log"],
        "control_cookie_path": plan.get("control_cookie_path"),
        "started_epoch_ms": round(time.time() * 1000, 3),
        "conflux_client_ux": plan.get("conflux_client_ux"),
        "ready_gate": None,
    }


def managed_service_ready_source(wait_result: dict[str, object]) -> str:
    if wait_result.get("ready_via_service_metadata") is True:
        return "service_metadata"
    if wait_result.get("ready_via_control") is True:
        return "control"
    return "log"


def record_managed_service_ready(
    service: dict[str, object],
    *,
    gate: str,
    wait_result: dict[str, object],
    actor: str | None = None,
) -> dict[str, object]:
    updated = dict(service)
    ready_epoch_ms = wait_result.get("ready_epoch_ms")
    if not isinstance(ready_epoch_ms, (int, float)):
        ready_epoch_ms = round(time.time() * 1000, 3)
    ready_monotonic_seconds = wait_result.get("ready_monotonic_seconds")
    if not isinstance(ready_monotonic_seconds, (int, float)):
        ready_monotonic_seconds = round(time.monotonic(), 6)
    source = managed_service_ready_source(wait_result)
    actor_name = actor or "launcher"
    updated["ready_gate"] = gate
    updated["ready_epoch_ms"] = ready_epoch_ms
    updated["ready_monotonic_seconds"] = ready_monotonic_seconds
    updated["ready_source"] = source
    updated["ready_actor"] = actor_name
    updated["ready_writer_pid"] = os.getpid()
    history = (
        list(updated.get("ready_gate_history"))
        if isinstance(updated.get("ready_gate_history"), list)
        else []
    )
    history.append(
        {
            "gate": gate,
            "ready_epoch_ms": ready_epoch_ms,
            "ready_monotonic_seconds": ready_monotonic_seconds,
            "source": source,
            "actor": actor_name,
            "writer_pid": os.getpid(),
            "polls": (
                int(wait_result["polls"])
                if isinstance(wait_result.get("polls"), int)
                else None
            ),
            "seconds": (
                float(wait_result["seconds"])
                if isinstance(wait_result.get("seconds"), (int, float))
                else None
            ),
        }
    )
    updated["ready_gate_history"] = history
    return updated


def read_json(
    path: Path,
    *,
    retries: int = 0,
    retry_delay: float = 0.0,
) -> dict[str, object] | None:
    if not path.exists():
        return None
    attempts = max(1, int(retries) + 1)
    for attempt in range(attempts):
        try:
            payload = json.loads(path.read_text())
        except OSError:
            return None
        except json.JSONDecodeError:
            if attempt + 1 >= attempts:
                return None
            time.sleep(max(0.0, retry_delay))
            continue
        return payload if isinstance(payload, dict) else None
    return None


def process_is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def reusable_managed_tor_service(
    paths: LaunchPaths,
    *,
    desired_torrc: str,
    port: int,
) -> dict[str, object] | None:
    service = read_json(
        paths.tor_service_json,
        retries=JSON_READ_RETRIES,
        retry_delay=JSON_READ_RETRY_SECONDS,
    )
    if not service:
        return None
    pid = service.get("pid")
    service_port = service.get("port")
    service_torrc = service.get("torrc")
    if not isinstance(pid, int) or not isinstance(service_port, int):
        return None
    if service_port != port:
        raise LaunchError(
            f"managed tor service uses port {service_port}, not requested {port}"
        )
    if not isinstance(service_torrc, str) or Path(service_torrc) != paths.torrc:
        raise LaunchError("managed tor service torrc path does not match state root")
    if not paths.torrc.exists() or paths.torrc.read_text() != desired_torrc:
        raise LaunchError(
            "managed tor service config does not match requested launch options; stop it first"
        )
    if not process_is_alive(pid):
        cleanup_stale_managed_tor_service(paths)
        return None
    if not port_is_open("127.0.0.1", port):
        cleanup_stale_managed_tor_service(paths)
        return None
    return service


def record_stream_isolation_probe(
    *,
    control_port: object,
    control_cookie_path: object,
    url: str,
    timeout_seconds: float,
) -> dict[str, object]:
    if not isinstance(control_port, int) or not isinstance(control_cookie_path, str):
        return {
            "ok": False,
            "error": "stream isolation probe requested without control-port support",
        }
    if timeout_seconds <= 0:
        return {
            "ok": False,
            "error": "stream isolation probe timeout must be positive",
        }
    target_substrings = target_stream_substrings(url)
    from torfast.control import probe_stream_isolation

    return probe_stream_isolation(
        host="127.0.0.1",
        port=control_port,
        cookie_path=Path(control_cookie_path),
        timeout=timeout_seconds,
        target_substrings=target_substrings or None,
    )


def read_bootstrap_phase_snapshot(
    *,
    control_port: object,
    control_cookie_path: object,
) -> dict[str, object]:
    if not isinstance(control_port, int) or not isinstance(control_cookie_path, str):
        return {
            "ok": False,
            "error": "control-port bootstrap probe unavailable",
        }
    started = time.monotonic()
    client: TorControlClient | None = None
    try:
        client = TorControlClient.connect(
            host="127.0.0.1",
            port=control_port,
            cookie_path=Path(control_cookie_path),
        )
        snapshot = read_bootstrap_phase_snapshot_with_client(
            client,
            include_timing=False,
        )
    except (FileNotFoundError, OSError, RuntimeError, EOFError) as exc:
        return {
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
        }
    finally:
        if client is not None:
            client.close()
    if snapshot.get("ok") is not True:
        return snapshot
    return {
        **snapshot,
        "seconds": round(time.monotonic() - started, 3),
    }


def bootstrap_phase_snapshot_from_reply(
    reply: str,
    *,
    seconds: float | None = None,
) -> dict[str, object]:
    line = ""
    for reply_line in reply.splitlines():
        if "status/bootstrap-phase=" in reply_line:
            line = reply_line
            break
    line = line or reply.strip()
    progress_match = re.search(r"PROGRESS=(\d+)", line)
    tag_match = re.search(r"TAG=([^ ]+)", line)
    summary_match = re.search(r'SUMMARY="([^"]*)"', line)
    snapshot: dict[str, object] = {
        "ok": True,
        "line": line,
        "progress": (
            int(progress_match.group(1)) if progress_match is not None else None
        ),
        "tag": tag_match.group(1) if tag_match is not None else None,
        "summary": summary_match.group(1) if summary_match is not None else None,
    }
    if seconds is not None:
        snapshot["seconds"] = seconds
    return snapshot


def read_bootstrap_phase_snapshot_with_client(
    client: TorControlClient,
    *,
    include_timing: bool = False,
) -> dict[str, object]:
    started = time.monotonic() if include_timing else None
    try:
        reply = client.command("GETINFO status/bootstrap-phase")
    except (OSError, RuntimeError, EOFError) as exc:
        return {
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
        }
    elapsed = None
    if started is not None:
        elapsed = round(time.monotonic() - started, 3)
    return bootstrap_phase_snapshot_from_reply(reply, seconds=elapsed)


def gate_progress_requirement(gate: str | None) -> int | None:
    if gate == "tor_boot_90":
        return 90
    if gate == "tor_boot_95":
        return 95
    if gate == "tor_boot_100":
        return 100
    return None


def control_ready_for_gate(
    *,
    gate: str | None,
    control_port: object,
    control_cookie_path: object,
) -> dict[str, object] | None:
    progress_requirement = gate_progress_requirement(gate)
    if progress_requirement is None:
        return None
    snapshot = read_bootstrap_phase_snapshot(
        control_port=control_port,
        control_cookie_path=control_cookie_path,
    )
    if snapshot.get("ok") is not True:
        return snapshot
    progress = snapshot.get("progress")
    if isinstance(progress, int) and progress >= progress_requirement:
        return snapshot
    return None


def control_ready_for_gate_with_client(
    *,
    gate: str | None,
    client: TorControlClient,
) -> dict[str, object] | None:
    progress_requirement = gate_progress_requirement(gate)
    if progress_requirement is None:
        return None
    snapshot = read_bootstrap_phase_snapshot_with_client(
        client,
        include_timing=False,
    )
    if snapshot.get("ok") is not True:
        return snapshot
    progress = snapshot.get("progress")
    if isinstance(progress, int) and progress >= progress_requirement:
        return snapshot
    return None


def reused_service_gate_diagnostics_start(
    *,
    reused_tor_service: dict[str, object],
    ready_text: str,
) -> dict[str, object]:
    log_path = reused_tor_service.get("tor_log")
    seen = (
        tail_lines(Path(str(log_path)), limit=200)
        if isinstance(log_path, str)
        else []
    )
    now_epoch_ms = round(time.time() * 1000, 3)
    started_epoch_ms = reused_tor_service.get("started_epoch_ms")
    started_age = None
    if isinstance(started_epoch_ms, (int, float)):
        started_age = round((now_epoch_ms - float(started_epoch_ms)) / 1000.0, 3)
    ready_age = managed_service_ready_age_seconds(
        reused_tor_service,
        now_epoch_ms=now_epoch_ms,
    )
    return {
        "service_ready_gate_before_wait": reused_tor_service.get("ready_gate"),
        "service_uptime_seconds_before_wait": started_age,
        "service_ready_age_seconds_before_wait": ready_age,
        "ready_text_present_before_wait": any(ready_text in line for line in seen),
        "initial_signal_lines": boot_signal_lines(seen)[-20:],
        "control_bootstrap_phase_before_wait": read_bootstrap_phase_snapshot(
            control_port=reused_tor_service.get("control_port"),
            control_cookie_path=reused_tor_service.get("control_cookie_path"),
        ),
    }


def finalize_reused_service_gate_diagnostics(
    diagnostics: dict[str, object],
    *,
    reused_tor_service: dict[str, object],
    wait_result: dict[str, object],
    wait_skipped: bool,
) -> dict[str, object]:
    updated = dict(diagnostics)
    updated["wait_skipped"] = wait_skipped
    updated["wait_polls"] = wait_result.get("polls")
    updated["control_bootstrap_phase_after_wait"] = read_bootstrap_phase_snapshot(
        control_port=reused_tor_service.get("control_port"),
        control_cookie_path=reused_tor_service.get("control_cookie_path"),
    )
    return updated


def cleanup_stale_managed_tor_service(paths: LaunchPaths) -> None:
    for path in (paths.tor_service_json,):
        try:
            if path.exists():
                path.unlink()
        except OSError:
            pass


def stop_prestarted_browser(paths: LaunchPaths) -> dict[str, object]:
    metadata = read_prestarted_browser_metadata(paths.prestarted_browser_json)
    if not metadata:
        return {
            "ok": True,
            "stopped": False,
            "already_stopped": True,
            "browser": None,
            "note": f"no prestarted browser metadata at {paths.prestarted_browser_json}",
        }
    pid = metadata.get("pid")
    if not isinstance(pid, int):
        clear_prestarted_browser_metadata(paths.prestarted_browser_json)
        return {
            "ok": False,
            "error": "prestarted browser metadata is missing a pid",
        }
    if not process_is_alive(pid):
        clear_prestarted_browser_metadata(paths.prestarted_browser_json)
        return {
            "ok": True,
            "stopped": False,
            "already_stopped": True,
            "browser": metadata,
        }
    try:
        os.killpg(pid, signal.SIGTERM)
    except ProcessLookupError:
        clear_prestarted_browser_metadata(paths.prestarted_browser_json)
        return {
            "ok": True,
            "stopped": False,
            "already_stopped": True,
            "browser": metadata,
        }
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        if not process_is_alive(pid):
            clear_prestarted_browser_metadata(paths.prestarted_browser_json)
            return {"ok": True, "stopped": True, "browser": metadata}
        time.sleep(0.1)
    try:
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if not process_is_alive(pid):
            clear_prestarted_browser_metadata(paths.prestarted_browser_json)
            return {
                "ok": True,
                "stopped": True,
                "killed": True,
                "browser": metadata,
            }
        time.sleep(0.1)
    return {
        "ok": False,
        "error": f"prestarted browser pid {pid} did not stop",
        "browser": metadata,
    }


def stop_managed_tor_service(paths: LaunchPaths) -> dict[str, object]:
    browser_stop = stop_prestarted_browser(paths)
    service = read_json(
        paths.tor_service_json,
        retries=JSON_READ_RETRIES,
        retry_delay=JSON_READ_RETRY_SECONDS,
    )
    if not service:
        return {
            "ok": True,
            "stopped": False,
            "already_stopped": True,
            "service": None,
            "prestarted_browser": browser_stop,
            "note": f"no managed tor service metadata at {paths.tor_service_json}",
        }
    pid = service.get("pid")
    if not isinstance(pid, int):
        cleanup_stale_managed_tor_service(paths)
        return {
            "ok": False,
            "error": "managed tor service metadata is missing a pid",
            "prestarted_browser": browser_stop,
        }
    if not process_is_alive(pid):
        cleanup_stale_managed_tor_service(paths)
        return {
            "ok": True,
            "stopped": False,
            "already_stopped": True,
            "service": service,
            "prestarted_browser": browser_stop,
        }
    try:
        os.killpg(pid, signal.SIGTERM)
    except ProcessLookupError:
        cleanup_stale_managed_tor_service(paths)
        return {
            "ok": True,
            "stopped": False,
            "already_stopped": True,
            "service": service,
            "prestarted_browser": browser_stop,
        }
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        if not process_is_alive(pid):
            cleanup_stale_managed_tor_service(paths)
            return {
                "ok": True,
                "stopped": True,
                "service": service,
                "prestarted_browser": browser_stop,
            }
        time.sleep(0.1)
    try:
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if not process_is_alive(pid):
            cleanup_stale_managed_tor_service(paths)
            return {
                "ok": True,
                "stopped": True,
                "killed": True,
                "service": service,
                "prestarted_browser": browser_stop,
            }
        time.sleep(0.1)
    return {
        "ok": False,
        "error": f"managed tor service pid {pid} did not stop",
        "service": service,
        "prestarted_browser": browser_stop,
    }


def wait_for_ready_in_log(
    *,
    proc: subprocess.Popen[str],
    log_path: Path,
    timeout: float,
    ready_text: str,
    process_name: str,
) -> dict[str, object]:
    started = time.monotonic()
    seen: list[str] = []
    while time.monotonic() - started < timeout:
        if proc.poll() is not None:
            seen = tail_lines(log_path, limit=80)
            return {
                "ok": False,
                "error": f"{process_name} exited with code {proc.returncode}",
                "lines": seen,
                "signal_lines": boot_signal_lines(seen),
            }
        seen = tail_lines(log_path, limit=200)
        if any(ready_text in line for line in seen):
            ready_monotonic = time.monotonic()
            return {
                "ok": True,
                "seconds": round(ready_monotonic - started, 3),
                "ready_epoch_ms": round(time.time() * 1000, 3),
                "ready_monotonic_seconds": round(ready_monotonic, 6),
                "lines": seen[-80:],
                "signal_lines": boot_signal_lines(seen),
            }
        time.sleep(PROCESS_POLL_INTERVAL_SECONDS)
    seen = tail_lines(log_path, limit=80)
    return {
        "ok": False,
        "error": "bootstrap timeout",
        "lines": seen,
        "signal_lines": boot_signal_lines(seen),
    }


def wait_for_existing_service_ready_in_log(
    *,
    pid: int,
    log_path: Path,
    timeout: float,
    ready_text: str,
    process_name: str,
    gate: str | None = None,
    control_port: object = None,
    control_cookie_path: object = None,
    service_path: Path | None = None,
    expected_service: dict[str, object] | None = None,
) -> dict[str, object]:
    started = time.monotonic()
    seen: list[str] = []
    polls = 0
    progress_requirement = gate_progress_requirement(gate)
    control_cookie = (
        Path(control_cookie_path)
        if isinstance(control_cookie_path, str)
        else None
    )
    persistent_control_wait_enabled = (
        os.environ.get(PERSISTENT_CONTROL_WAIT_ENABLED_ENV) == "1"
    )
    if os.environ.get(PERSISTENT_CONTROL_WAIT_DISABLED_ENV) == "1":
        persistent_control_wait_enabled = False
    control_bootstrap_probe_enabled = (
        os.environ.get(CONTROL_BOOTSTRAP_PROBE_DISABLED_ENV) != "1"
    )
    prefer_promoted_service_metadata = promoted_service_metadata_wait_requested(
        expected_service,
    )
    control_client: TorControlClient | None = None
    try:
        while time.monotonic() - started < timeout:
            if not process_is_alive(pid):
                seen = tail_lines(log_path, limit=80)
                return {
                    "ok": False,
                    "error": f"{process_name} exited before reaching {ready_text}",
                    "lines": seen,
                    "polls": polls,
                    "signal_lines": boot_signal_lines(seen),
                }
            seen = tail_lines(log_path, limit=200)
            polls += 1
            metadata_wait_requested = (
                managed_service_metadata_wait_enabled()
                and progress_requirement is not None
                and service_path is not None
                and isinstance(expected_service, dict)
                and should_refresh_managed_service_metadata_wait(
                    polls=polls,
                    expected_service=expected_service,
                )
            )
            if prefer_promoted_service_metadata and metadata_wait_requested:
                refreshed_service = refresh_matching_managed_service(
                    service_path,
                    expected_service=expected_service,
                )
                if (
                    isinstance(refreshed_service, dict)
                    and managed_service_ready_for_gate(refreshed_service, gate)
                ):
                    ready_monotonic = time.monotonic()
                    return {
                        "ok": True,
                        "seconds": round(ready_monotonic - started, 3),
                        "ready_epoch_ms": refreshed_service.get("ready_epoch_ms"),
                        "ready_monotonic_seconds": refreshed_service.get(
                            "ready_monotonic_seconds"
                        ),
                        "lines": seen[-80:],
                        "polls": polls,
                        "ready_via_service_metadata": True,
                        "signal_lines": boot_signal_lines(seen),
                    }
            if not prefer_promoted_service_metadata and any(
                ready_text in line for line in seen
            ):
                ready_monotonic = time.monotonic()
                return {
                    "ok": True,
                    "seconds": round(ready_monotonic - started, 3),
                    "ready_epoch_ms": round(time.time() * 1000, 3),
                    "ready_monotonic_seconds": round(ready_monotonic, 6),
                    "lines": seen[-80:],
                    "polls": polls,
                    "signal_lines": boot_signal_lines(seen),
                }
            if not prefer_promoted_service_metadata and metadata_wait_requested:
                refreshed_service = refresh_matching_managed_service(
                    service_path,
                    expected_service=expected_service,
                )
                if (
                    isinstance(refreshed_service, dict)
                    and managed_service_ready_for_gate(refreshed_service, gate)
                ):
                    ready_monotonic = time.monotonic()
                    return {
                        "ok": True,
                        "seconds": round(ready_monotonic - started, 3),
                        "ready_epoch_ms": refreshed_service.get("ready_epoch_ms"),
                        "ready_monotonic_seconds": refreshed_service.get(
                            "ready_monotonic_seconds"
                        ),
                        "lines": seen[-80:],
                        "polls": polls,
                        "ready_via_service_metadata": True,
                        "signal_lines": boot_signal_lines(seen),
                    }
            if (
                control_bootstrap_probe_enabled
                and progress_requirement is not None
                and isinstance(control_port, int)
                and control_cookie is not None
            ):
                if not persistent_control_wait_enabled:
                    control_ready = control_ready_for_gate(
                        gate=gate,
                        control_port=control_port,
                        control_cookie_path=str(control_cookie),
                    )
                    if (
                        isinstance(control_ready, dict)
                        and control_ready.get("ok") is True
                        and isinstance(control_ready.get("progress"), int)
                    ):
                        ready_monotonic = time.monotonic()
                        return {
                            "ok": True,
                            "seconds": round(ready_monotonic - started, 3),
                            "ready_epoch_ms": round(time.time() * 1000, 3),
                            "ready_monotonic_seconds": round(ready_monotonic, 6),
                            "lines": seen[-80:],
                            "polls": polls,
                            "ready_via_control": True,
                            "control_bootstrap_phase": control_ready,
                            "signal_lines": boot_signal_lines(seen),
                        }
                else:
                    if control_client is None:
                        try:
                            control_client = TorControlClient.connect(
                                host="127.0.0.1",
                                port=control_port,
                                cookie_path=control_cookie,
                            )
                        except (FileNotFoundError, OSError, RuntimeError, EOFError):
                            control_client = None
                    if control_client is not None:
                        control_ready = control_ready_for_gate_with_client(
                            gate=gate,
                            client=control_client,
                        )
                        if (
                            control_ready is not None
                            and control_ready.get("ok") is not True
                        ):
                            control_client.close()
                            control_client = None
                        elif (
                            isinstance(control_ready, dict)
                            and control_ready.get("ok") is True
                            and isinstance(control_ready.get("progress"), int)
                        ):
                            ready_monotonic = time.monotonic()
                            return {
                                "ok": True,
                                "seconds": round(ready_monotonic - started, 3),
                                "ready_epoch_ms": round(time.time() * 1000, 3),
                                "ready_monotonic_seconds": round(
                                    ready_monotonic, 6
                                ),
                                "lines": seen[-80:],
                                "polls": polls,
                                "ready_via_control": True,
                                "control_bootstrap_phase": control_ready,
                                "signal_lines": boot_signal_lines(seen),
                            }
            if prefer_promoted_service_metadata and any(
                ready_text in line for line in seen
            ):
                ready_monotonic = time.monotonic()
                return {
                    "ok": True,
                    "seconds": round(ready_monotonic - started, 3),
                    "ready_epoch_ms": round(time.time() * 1000, 3),
                    "ready_monotonic_seconds": round(ready_monotonic, 6),
                    "lines": seen[-80:],
                    "polls": polls,
                    "signal_lines": boot_signal_lines(seen),
                }
            time.sleep(PROCESS_POLL_INTERVAL_SECONDS)
        seen = tail_lines(log_path, limit=80)
        return {
            "ok": False,
            "error": "bootstrap timeout",
            "lines": seen,
            "polls": polls,
            "signal_lines": boot_signal_lines(seen),
        }
    finally:
        if control_client is not None:
            control_client.close()


def tail_lines(path: Path, *, limit: int) -> list[str]:
    if not path.exists():
        return []
    try:
        return path.read_text(errors="replace").splitlines()[-limit:]
    except OSError:
        return []


if __name__ == "__main__":
    raise SystemExit(main())
