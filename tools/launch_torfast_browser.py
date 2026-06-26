#!/usr/bin/env python3
"""Launch the current best proven fast, equal-quality Tor Browser path."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import queue
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
HOT_PATH_STATUS_CACHE_DISABLED_ENV = "TORFAST_DISABLE_HOT_PATH_STATUS_CACHE"
ASYNC_BROWSER_RESET_DISABLED_ENV = "TORFAST_DISABLE_ASYNC_BROWSER_RESET"
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
PROCESS_POLL_INTERVAL_SECONDS = 0.05
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
            "lighter tor_boot_95 gate, and uses socks_ready again on the "
            "warm/reused managed path"
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
        "--stream-isolation-probe-timeout",
        type=float,
        default=3.0,
        help=(
            "seconds to wait for the optional stream-isolation probe to "
            "observe browser SOCKS streams"
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
    parser.set_defaults(no_browser_startup_seed=True)
    args = parser.parse_args(argv)

    try:
        if args.browser_timeout < 0:
            raise LaunchError("--browser-timeout must be non-negative")
        if args.stream_isolation_probe_timeout < 0:
            raise LaunchError("--stream-isolation-probe-timeout must be non-negative")

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
        browser_launch_gate = resolve_managed_browser_launch_gate(
            requested_gate=args.browser_launch_gate,
            url=args.url,
            start_managed_tor_only=args.start_managed_tor_only,
            reused_tor_service=reused_tor_service,
        )

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
        else:
            browser_startup_seed_apply = apply_browser_startup_seed_to_profile(
                paths.browser_profile_dir,
                browser_startup_seed_root,
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
            stream_isolation_probe=args.stream_isolation_probe,
            stream_isolation_probe_timeout=args.stream_isolation_probe_timeout,
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
) -> bool:
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
    if start_managed_tor_only or isinstance(reused_tor_service, dict):
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
    stream_isolation_probe: bool,
    stream_isolation_probe_timeout: float,
) -> dict[str, object]:
    return {
        "created_at_epoch_ms": round(time.time() * 1000, 3),
        "browser_bin": str(browser_bin),
        "tor_bin": str(tor_bin),
        "paths": paths.as_dict(),
        "port": port,
        "url": url,
        "headless": headless,
        "browser_timeout_seconds": browser_timeout,
        "browser_launch_gate": browser_launch_gate,
        "browser_launch_gate_requested": browser_launch_gate_requested,
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
        "control_port": control_port,
        "control_cookie_path": (
            str(control_cookie_path) if control_cookie_path is not None else None
        ),
        "torrc_quality": read_torrc_quality(paths.torrc),
        "browser_default_prefs": default_pref_proof,
        "browser_default_pref_check": default_pref_check,
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
    path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n")


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
    leave_tor_running = bool(plan.get("leave_tor_running"))
    reused_tor_service = plan.get("reused_tor_service")
    browser_launch_gate = str(
        plan.get("browser_launch_gate") or DEFAULT_BROWSER_LAUNCH_GATE
    )
    keep_tor_running = False
    tor_boot: dict[str, object] | None = None
    tor_managed_ready: dict[str, object] | None = None
    pending_managed_service: dict[str, object] | None = None
    try:
        if isinstance(reused_tor_service, dict):
            keep_tor_running = True
            if plan.get("start_managed_tor_only"):
                plan["tor_managed_ready"] = {
                    "ok": True,
                    "reused_service": True,
                    "service_pid": reused_tor_service.get("pid"),
                    "service_started_epoch_ms": reused_tor_service.get(
                        "started_epoch_ms"
                    ),
                    "port": reused_tor_service.get("port"),
                    "gate": reused_tor_service.get("ready_gate"),
                }
            elif browser_launch_gate == "tor_boot_100":
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
                        ready_text=browser_launch_gate_ready_text("tor_boot_100"),
                        process_name="tor",
                    )
                if tor_boot.get("ok"):
                    plan["reused_tor_service"] = record_managed_service_ready(
                        reused_tor_service,
                        gate="tor_boot_100",
                        wait_result=tor_boot,
                    )
                    write_json(
                        Path(str(paths_dict["tor_service_json"])),
                        plan["reused_tor_service"],
                    )
            else:
                if managed_service_ready_for_gate(
                    reused_tor_service,
                    browser_launch_gate,
                ):
                    browser_launch_gate_result = managed_service_ready_result(
                        reused_tor_service,
                        gate=browser_launch_gate,
                    )
                else:
                    browser_launch_gate_result = (
                        wait_for_existing_service_ready_in_log(
                            pid=int(reused_tor_service["pid"]),
                            log_path=Path(str(reused_tor_service["tor_log"])),
                            timeout=180.0,
                            ready_text=browser_launch_gate_ready_text(
                                browser_launch_gate
                            ),
                            process_name="tor",
                        )
                    )
                plan["tor_browser_launch_gate"] = {
                    "gate": browser_launch_gate,
                    **browser_launch_gate_result,
                }
                if not browser_launch_gate_result.get("ok"):
                    tor_boot = browser_launch_gate_result
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
                    plan["reused_tor_service"] = record_managed_service_ready(
                        pending_managed_service,
                        gate=initial_gate,
                        wait_result=tor_managed_ready,
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
                    plan["reused_tor_service"] = record_managed_service_ready(
                        pending_managed_service,
                        gate="tor_boot_100",
                        wait_result=tor_boot,
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
                    plan["reused_tor_service"] = record_managed_service_ready(
                        pending_managed_service,
                        gate="tor_boot_100",
                        wait_result=tor_boot,
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

        seed_root = plan.get("dir_cache_seed_root")
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
            elif isinstance(reused_tor_service, dict):
                plan["dir_cache_seed_update"] = {
                    "ok": True,
                    "updated": False,
                    "reason": "reused managed tor service",
                    "seed_root": seed_root,
                }
            else:
                plan["dir_cache_seed_update"] = update_seed_from_data_dir(
                    Path(str(paths_dict["data_dir"])),
                    dir_cache_seed_root,
                )
            plan["dir_cache_seed_status"] = describe_seed(dir_cache_seed_root)

        if plan.get("start_managed_tor_only"):
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
                        "reason": "browser launch skipped",
                        "seed_root": browser_startup_seed_root,
                    }
                plan["browser_startup_seed_status"] = describe_browser_startup_seed(
                    Path(browser_startup_seed_root)
                )
            if isinstance(plan.get("tor_managed_ready"), dict):
                ready_gate = plan["tor_managed_ready"].get("gate")
                note = (
                    "managed tor is ready at "
                    f"{ready_gate}; browser launch skipped as requested"
                )
            elif keep_tor_running or isinstance(reused_tor_service, dict):
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
        )
        browser_result["elapsed_seconds"] = round(
            time.monotonic() - browser_started, 3
        )
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
                        plan["reused_tor_service"] = record_managed_service_ready(
                            reused_tor_service,
                            gate="tor_boot_100",
                            wait_result=tor_boot,
                        )
                    elif pending_managed_service is not None:
                        plan["reused_tor_service"] = record_managed_service_ready(
                            pending_managed_service,
                            gate="tor_boot_100",
                            wait_result=tor_boot,
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
        print(f"wrote {launch_json}")
        print(json.dumps(compact_launch_summary(plan), indent=2, sort_keys=True))
        return (
            0
            if browser_result.get("ok") and tor_boot is not None and tor_boot.get("ok")
            else 1
        )
    finally:
        if browser_proc is not None:
            stop_process_tree(browser_proc)
        if tor_proc is not None and not keep_tor_running:
            stop_process(tor_proc)
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
) -> dict[str, object]:
    started = time.monotonic()
    seen: list[str] = []
    try:
        while True:
            if proc.poll() is not None:
                exit_code = proc.returncode
                return {
                    "ok": exit_code == 0,
                    "exit_code": exit_code,
                    "timed_out": False,
                    "interrupted": False,
                    "output_tail": seen[-40:],
                }
            if timeout_seconds > 0 and time.monotonic() - started >= timeout_seconds:
                return {
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
            try:
                line = lines.get(timeout=PROCESS_POLL_INTERVAL_SECONDS)
            except queue.Empty:
                continue
            seen.append(line)
    except KeyboardInterrupt:
        return {
            "ok": False,
            "exit_code": None,
            "timed_out": False,
            "interrupted": True,
            "error": "interrupted by user",
            "output_tail": seen[-40:],
        }


def compact_launch_summary(plan: dict[str, object]) -> dict[str, object]:
    reused_tor_service = plan.get("reused_tor_service")
    if isinstance(reused_tor_service, dict):
        reused_tor_service = {
            "pid": reused_tor_service.get("pid"),
            "port": reused_tor_service.get("port"),
            "control_port": reused_tor_service.get("control_port"),
            "started_epoch_ms": reused_tor_service.get("started_epoch_ms"),
            "ready_epoch_ms": reused_tor_service.get("ready_epoch_ms"),
            "ready_gate": reused_tor_service.get("ready_gate"),
            "conflux_client_ux": reused_tor_service.get("conflux_client_ux"),
        }
    return {
        "browser": plan.get("browser"),
        "browser_launch_gate": plan.get("browser_launch_gate"),
        "browser_launch_gate_requested": plan.get("browser_launch_gate_requested"),
        "browser_default_pref_check": plan.get("browser_default_pref_check"),
        "browser_stream_isolation_probe": plan.get("browser_stream_isolation_probe"),
        "browser_runtime_reset": plan.get("browser_runtime_reset"),
        "browser_startup_seed_apply": plan.get("browser_startup_seed_apply"),
        "browser_startup_seed_update": plan.get("browser_startup_seed_update"),
        "dir_cache_seed_apply": plan.get("dir_cache_seed_apply"),
        "dir_cache_seed_update": plan.get("dir_cache_seed_update"),
        "leave_tor_running": plan.get("leave_tor_running"),
        "port": plan.get("port"),
        "reused_tor_service": reused_tor_service,
        "tor_managed_ready": plan.get("tor_managed_ready"),
        "tor_browser_launch_gate": plan.get("tor_browser_launch_gate"),
        "tor_boot": plan.get("tor_boot"),
        "torrc_quality": plan.get("torrc_quality"),
        "url": plan.get("url"),
    }


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


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


def record_managed_service_ready(
    service: dict[str, object],
    *,
    gate: str,
    wait_result: dict[str, object],
) -> dict[str, object]:
    updated = dict(service)
    updated["ready_gate"] = gate
    if isinstance(wait_result.get("ready_epoch_ms"), (int, float)):
        updated["ready_epoch_ms"] = wait_result["ready_epoch_ms"]
    if isinstance(wait_result.get("ready_monotonic_seconds"), (int, float)):
        updated["ready_monotonic_seconds"] = wait_result["ready_monotonic_seconds"]
    return updated


def read_json(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


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
    service = read_json(paths.tor_service_json)
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
    target_substrings = []
    hostname = urlparse(url).hostname
    if hostname:
        target_substrings.append(hostname)
    from torfast.control import probe_stream_isolation

    return probe_stream_isolation(
        host="127.0.0.1",
        port=control_port,
        cookie_path=Path(control_cookie_path),
        timeout=timeout_seconds,
        target_substrings=target_substrings or None,
    )


def cleanup_stale_managed_tor_service(paths: LaunchPaths) -> None:
    for path in (paths.tor_service_json,):
        try:
            if path.exists():
                path.unlink()
        except OSError:
            pass


def stop_managed_tor_service(paths: LaunchPaths) -> dict[str, object]:
    service = read_json(paths.tor_service_json)
    if not service:
        return {
            "ok": True,
            "stopped": False,
            "already_stopped": True,
            "service": None,
            "note": f"no managed tor service metadata at {paths.tor_service_json}",
        }
    pid = service.get("pid")
    if not isinstance(pid, int):
        cleanup_stale_managed_tor_service(paths)
        return {"ok": False, "error": "managed tor service metadata is missing a pid"}
    if not process_is_alive(pid):
        cleanup_stale_managed_tor_service(paths)
        return {
            "ok": True,
            "stopped": False,
            "already_stopped": True,
            "service": service,
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
        }
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        if not process_is_alive(pid):
            cleanup_stale_managed_tor_service(paths)
            return {"ok": True, "stopped": True, "service": service}
        time.sleep(0.1)
    try:
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if not process_is_alive(pid):
            cleanup_stale_managed_tor_service(paths)
            return {"ok": True, "stopped": True, "killed": True, "service": service}
        time.sleep(0.1)
    return {
        "ok": False,
        "error": f"managed tor service pid {pid} did not stop",
        "service": service,
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
) -> dict[str, object]:
    started = time.monotonic()
    seen: list[str] = []
    while time.monotonic() - started < timeout:
        if not process_is_alive(pid):
            seen = tail_lines(log_path, limit=80)
            return {
                "ok": False,
                "error": f"{process_name} exited before reaching {ready_text}",
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


def tail_lines(path: Path, *, limit: int) -> list[str]:
    if not path.exists():
        return []
    try:
        return path.read_text(errors="replace").splitlines()[-limit:]
    except OSError:
        return []


if __name__ == "__main__":
    raise SystemExit(main())
