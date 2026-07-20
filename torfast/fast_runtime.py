"""Fast runtime entry helpers for common torfast actions."""

from __future__ import annotations

import functools
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import time
from types import SimpleNamespace

from .control import read_general_circuit_snapshot, wait_for_general_circuits

REPO_ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = REPO_ROOT / "tools" / "launch_torfast_browser.py"
DEFAULT_BROWSER_BIN = (
    REPO_ROOT
    / "tmp"
    / "browser"
    / "Tor Browser.app"
    / "Contents"
    / "MacOS"
    / "firefox"
)
DEFAULT_TOR_BIN = (
    REPO_ROOT
    / "tmp"
    / "browser"
    / "Tor Browser.app"
    / "Contents"
    / "MacOS"
    / "Tor"
    / "tor"
)
DEFAULT_LOCAL_TOR_BIN = REPO_ROOT / "upstream" / "tor" / "src" / "app" / "tor"
DEFAULT_STATE_ROOT = REPO_ROOT / "tmp" / "torfast-browser"
DEFAULT_FRESH_STATE_ROOT_PARENT = REPO_ROOT / "tmp" / "torfast-launches"
DEFAULT_C_TOR_DIR_CACHE_SEED_ROOT = REPO_ROOT / "tmp" / "torfast-c-tor-dir-cache-seed"
DEFAULT_BROWSER_STARTUP_SEED_ROOT = (
    REPO_ROOT / "tmp" / "torfast-browser-startup-seed"
)
DEFAULT_URL = "about:tor"
AUTO_STATE_ROOT = "__TORFAST_AUTO_STATE_ROOT__"
DEFAULT_BROWSER_LAUNCH_GATE = "auto"
DEFAULT_PORT = 19450
DEFAULT_STREAM_ISOLATION_PROBE_TIMEOUT = 3.0
# Keep in sync with torfast.cli: promoted product default from the
# eager-overlap A/B campaign (results/torfast-promoted-quality-check-*).
DEFAULT_MANAGED_OPEN_ADAPTIVE_GENERAL_CIRCUIT_WAIT_TIMEOUT = 0.126
DEFAULT_WAIT_READY_TIMEOUT = 180.0
MANAGED_OPEN_ADAPTIVE_GENERAL_CIRCUIT_WAIT_POLL_INTERVAL_SECONDS = 0.05
MANAGED_OPEN_ADAPTIVE_GENERAL_CIRCUIT_WAIT_REPORT_NAME = (
    "managed-open-adaptive-general-circuit-wait.json"
)
RUNTIME_HELPER_DISABLED_ENV = "TORFAST_DISABLE_RUNTIME_HELPER"
WARM_RUNTIME_HELPER_PRESTART_ENABLED_ENV = (
    "TORFAST_ENABLE_WARM_RUNTIME_HELPER_PRESTART"
)
RUNTIME_HELPER_STARTUP_WAIT_SECONDS = 0.0
RUNTIME_HELPER_STALE_START_SECONDS = 5.0
RUNTIME_HELPER_IDLE_TIMEOUT_SECONDS = 60.0
RUNTIME_ACTIONS = frozenset(
    {"start", "open", "warm", "prime", "launch", "plan", "stop"}
)
CONFLUX_CLIENT_UX_CHOICES = frozenset(
    {"latency", "throughput", "throughput_lowmem"}
)
BROWSER_LAUNCH_GATE_CHOICES = frozenset(
    {"auto", "socks_ready", "tor_boot_90", "tor_boot_95", "tor_boot_100"}
)
VALUE_FLAGS = {
    "--browser-bin": "browser_bin",
    "--tor-bin": "tor_bin",
    "--url": "url",
    "--port": "port",
    "--state-root": "state_root",
    "--conflux-client-ux": "conflux_client_ux",
    "--browser-timeout": "browser_timeout",
    "--managed-open-adaptive-general-circuit-wait-timeout": (
        "managed_open_adaptive_general_circuit_wait_timeout"
    ),
    "--browser-launch-gate": "browser_launch_gate",
    "--stream-isolation-probe-timeout": "stream_isolation_probe_timeout",
    "--dir-cache-seed-root": "dir_cache_seed_root",
    "--browser-startup-seed-root": "browser_startup_seed_root",
    "--profile": "profile",
}
STORE_TRUE_FLAGS = {
    "--stock-ui": "stock_ui",
    "--headless": "headless",
    "--skip-browser-default-pref-check": "skip_browser_default_pref_check",
    "--gate-diagnostics": "gate_diagnostics",
    "--warm-browser-prestart": "warm_browser_prestart",
    "--stream-isolation-probe": "stream_isolation_probe",
    "--no-managed-open-browser-overlap": "no_managed_open_browser_overlap",
    "--no-managed-open-settle": "no_managed_open_settle",
    "--no-dir-cache-seed": "no_dir_cache_seed",
}
STORE_FALSE_FLAGS = {
    "--managed-open-browser-overlap": ("no_managed_open_browser_overlap", False),
    "--managed-open-settle": ("no_managed_open_settle", False),
    "--browser-startup-seed": ("no_browser_startup_seed", False),
    "--no-browser-startup-seed": ("no_browser_startup_seed", True),
}
EXCLUSIVE_BOOL_FLAG_FIELDS = frozenset(
    {
        "no_browser_startup_seed",
        "no_managed_open_browser_overlap",
        "no_managed_open_settle",
    }
)


@functools.lru_cache(maxsize=1)
def load_launcher_main():
    spec = importlib.util.spec_from_file_location(
        "torfast_runtime_launcher",
        LAUNCHER,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load launcher module: {LAUNCHER}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    launcher_main = getattr(module, "main", None)
    if not callable(launcher_main):
        raise RuntimeError(f"launcher module missing main(): {LAUNCHER}")
    return launcher_main


def run_launcher_args(launcher_args: list[str]) -> int:
    launcher_main = load_launcher_main()
    try:
        result = launcher_main(launcher_args)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 1
    return int(result) if result is not None else 0


def unique_paths(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    unique: list[Path] = []
    for path in paths:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


def candidate_browser_bins() -> list[Path]:
    candidates: list[Path] = []
    env_value = os.environ.get("TORFAST_BROWSER_BIN")
    if env_value:
        candidates.append(Path(env_value).expanduser())
    candidates.extend(
        [
            DEFAULT_BROWSER_BIN,
            Path("/Applications/Tor Browser.app/Contents/MacOS/firefox"),
            (
                Path.home()
                / "Applications"
                / "Tor Browser.app"
                / "Contents"
                / "MacOS"
                / "firefox"
            ),
        ]
    )
    return unique_paths(candidates)


def candidate_tor_bins() -> list[Path]:
    candidates: list[Path] = []
    env_value = os.environ.get("TORFAST_TOR_BIN")
    if env_value:
        candidates.append(Path(env_value).expanduser())
    candidates.append(DEFAULT_TOR_BIN)
    for browser_bin in candidate_browser_bins():
        candidates.append(browser_bin.parent / "Tor" / "tor")
    candidates.append(DEFAULT_LOCAL_TOR_BIN)
    which_tor = shutil.which("tor")
    if which_tor:
        candidates.append(Path(which_tor))
    return unique_paths(candidates)


def discover_browser_bin(explicit: str | None) -> dict[str, object]:
    if explicit:
        path = Path(explicit).expanduser().resolve()
        return {
            "found": path.exists(),
            "path": str(path) if path.exists() else None,
            "source": "explicit",
            "candidates": [str(path)],
        }
    candidates = [path.resolve() for path in candidate_browser_bins()]
    selected = next((path for path in candidates if path.exists()), None)
    return {
        "found": selected is not None,
        "path": str(selected) if selected is not None else None,
        "source": "auto",
        "candidates": [str(path) for path in candidates],
    }


def discover_tor_bin(explicit: str | None) -> dict[str, object]:
    if explicit:
        path = Path(explicit).expanduser().resolve()
        return {
            "found": path.exists(),
            "path": str(path) if path.exists() else None,
            "source": "explicit",
            "candidates": [str(path)],
        }
    candidates = [path.resolve() for path in candidate_tor_bins()]
    selected = next((path for path in candidates if path.exists()), None)
    return {
        "found": selected is not None,
        "path": str(selected) if selected is not None else None,
        "source": "auto",
        "candidates": [str(path) for path in candidates],
    }


def fresh_state_root(command_name: str) -> Path:
    run_id = time.strftime("%Y%m%dT%H%M%S")
    suffix = time.time_ns() % 1_000_000_000
    return (
        DEFAULT_FRESH_STATE_ROOT_PARENT
        / f"{command_name}-{run_id}-{os.getpid()}-{suffix:09d}"
    ).resolve()


def resolve_runtime_state_root(*, command: str, state_root: str) -> Path:
    if state_root != AUTO_STATE_ROOT:
        return Path(state_root).resolve()
    if command not in {"launch", "plan"}:
        return DEFAULT_STATE_ROOT.resolve()
    return fresh_state_root(command)


def build_launcher_args(args: SimpleNamespace) -> list[str]:
    if args.command == "stop":
        return [
            "--state-root",
            str(Path(args.state_root).resolve()),
            "--stop-managed-tor",
        ]

    browser = discover_browser_bin(getattr(args, "browser_bin", None))
    if not browser["found"]:
        candidates = ", ".join(browser["candidates"])
        raise RuntimeError(
            "Tor Browser binary not found; pass --browser-bin or install it in one of: "
            + candidates
        )
    tor = discover_tor_bin(getattr(args, "tor_bin", None))
    if not tor["found"]:
        candidates = ", ".join(tor["candidates"])
        raise RuntimeError(
            "C Tor binary not found; pass --tor-bin or build/install it in one of: "
            + candidates
        )

    launcher_args = [
        "--browser-bin",
        str(Path(str(browser["path"])).resolve()),
        "--tor-bin",
        str(Path(str(tor["path"])).resolve()),
        "--url",
        args.url,
        "--port",
        str(args.port),
        "--state-root",
        str(
            resolve_runtime_state_root(
                command=args.command,
                state_root=args.state_root,
            )
        ),
    ]
    if args.conflux_client_ux:
        launcher_args.extend(["--conflux-client-ux", args.conflux_client_ux])
    if args.browser_timeout != 0.0:
        launcher_args.extend(["--browser-timeout", str(args.browser_timeout)])
    if args.headless:
        launcher_args.append("--headless")
    if args.skip_browser_default_pref_check:
        launcher_args.append("--skip-browser-default-pref-check")
    if getattr(args, "gate_diagnostics", False):
        launcher_args.append("--gate-diagnostics")
    if not getattr(args, "no_managed_open_settle", True):
        launcher_args.append("--managed-open-settle")
    if not getattr(args, "no_managed_open_browser_overlap", False):
        launcher_args.append("--managed-open-browser-overlap")
    if getattr(args, "warm_browser_prestart", False):
        launcher_args.append("--warm-browser-prestart")
    # Forward the value even when it is 0 so an explicit opt-out reaches the
    # launcher instead of silently falling back to the launcher default.
    launcher_args.extend(
        [
            "--managed-open-adaptive-general-circuit-wait-timeout",
            str(
                float(
                    getattr(
                        args,
                        "managed_open_adaptive_general_circuit_wait_timeout",
                        DEFAULT_MANAGED_OPEN_ADAPTIVE_GENERAL_CIRCUIT_WAIT_TIMEOUT,
                    )
                )
            ),
        ]
    )
    browser_launch_gate = args.browser_launch_gate
    if args.command == "prime" and browser_launch_gate == DEFAULT_BROWSER_LAUNCH_GATE:
        browser_launch_gate = "tor_boot_100"
    if browser_launch_gate != DEFAULT_BROWSER_LAUNCH_GATE:
        launcher_args.extend(["--browser-launch-gate", browser_launch_gate])
    if args.stream_isolation_probe:
        launcher_args.append("--stream-isolation-probe")
    if args.stream_isolation_probe_timeout != DEFAULT_STREAM_ISOLATION_PROBE_TIMEOUT:
        launcher_args.extend(
            [
                "--stream-isolation-probe-timeout",
                str(args.stream_isolation_probe_timeout),
            ]
        )
    if args.dir_cache_seed_root != str(DEFAULT_C_TOR_DIR_CACHE_SEED_ROOT):
        launcher_args.extend(
            [
                "--dir-cache-seed-root",
                str(Path(args.dir_cache_seed_root).resolve()),
            ]
        )
    if args.no_dir_cache_seed:
        launcher_args.append("--no-dir-cache-seed")
    if args.browser_startup_seed_root != str(DEFAULT_BROWSER_STARTUP_SEED_ROOT):
        launcher_args.extend(
            [
                "--browser-startup-seed-root",
                str(Path(args.browser_startup_seed_root).resolve()),
            ]
        )
    if args.no_browser_startup_seed:
        launcher_args.append("--no-browser-startup-seed")
    else:
        launcher_args.append("--browser-startup-seed")
    if getattr(args, "stock_ui", False):
        launcher_args.append("--stock-ui")
    resolved_profile = getattr(args, "resolved_profile", None)
    if resolved_profile:
        launcher_args.extend(["--profile-label", resolved_profile])

    managed_reuse_on_open = getattr(args, "managed_reuse_on_open", True)
    keep_tor_warm_after_launch = getattr(args, "keep_tor_warm_after_launch", False)
    if args.command == "warm":
        launcher_args.extend(
            [
                "--leave-tor-running",
                "--reuse-tor-if-running",
                "--start-managed-tor-only",
            ]
        )
    elif args.command == "prime":
        launcher_args.append("--start-managed-tor-only")
    elif args.command in ("start", "open"):
        if managed_reuse_on_open:
            launcher_args.extend(["--leave-tor-running", "--reuse-tor-if-running"])
    elif args.command == "launch":
        if keep_tor_warm_after_launch:
            launcher_args.extend(["--leave-tor-running", "--reuse-tor-if-running"])
    elif args.command == "plan":
        if keep_tor_warm_after_launch:
            launcher_args.extend(["--leave-tor-running", "--reuse-tor-if-running"])
        launcher_args.append("--dry-run")

    return launcher_args


def build_action_command(args: SimpleNamespace) -> list[str]:
    return [sys.executable, str(LAUNCHER), *build_launcher_args(args)]


def ensure_private_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    try:
        path.chmod(0o700)
    except OSError:
        pass


def process_is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def read_json_file(path: Path) -> dict[str, object] | None:
    import json

    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def write_json_file(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def managed_open_adaptive_general_circuit_wait_report_path(
    state_root: Path,
) -> Path:
    return state_root / MANAGED_OPEN_ADAPTIVE_GENERAL_CIRCUIT_WAIT_REPORT_NAME


def clear_managed_open_adaptive_general_circuit_wait_report(state_root: Path) -> None:
    try:
        managed_open_adaptive_general_circuit_wait_report_path(state_root).unlink()
    except FileNotFoundError:
        pass
    except OSError:
        pass


def runtime_helper_socket_path(state_root: Path) -> Path:
    import hashlib
    import tempfile

    digest = hashlib.sha256(str(state_root).encode("utf-8")).hexdigest()[:20]
    return Path(tempfile.gettempdir()) / f"torfast-runtime-{digest}.sock"


def runtime_helper_json_path(state_root: Path) -> Path:
    return state_root / "runtime-helper.json"


def runtime_helper_log_path(state_root: Path) -> Path:
    return state_root / "runtime-helper.log"


def runtime_helper_starting_path(state_root: Path) -> Path:
    return state_root / "runtime-helper.starting"


def runtime_helper_context(state_root: Path) -> dict[str, object]:
    return {
        "uid": os.getuid(),
        "python_executable": sys.executable,
        "state_root": str(state_root),
    }


def runtime_helper_file_fingerprint() -> dict[str, int]:
    fingerprints: dict[str, int] = {}
    for path in (
        LAUNCHER,
        Path(__file__).resolve(),
        REPO_ROOT / "torfast" / "runtime_helper.py",
    ):
        try:
            fingerprints[str(path)] = path.stat().st_mtime_ns
        except OSError:
            fingerprints[str(path)] = -1
    return fingerprints


def cleanup_runtime_helper_files(state_root: Path) -> None:
    for path in (
        runtime_helper_socket_path(state_root),
        runtime_helper_json_path(state_root),
        runtime_helper_starting_path(state_root),
    ):
        try:
            if path.exists():
                path.unlink()
        except OSError:
            pass


def runtime_helper_start_pending(state_root: Path) -> bool:
    starting_path = runtime_helper_starting_path(state_root)
    if not starting_path.exists():
        return False
    try:
        age_seconds = time.time() - starting_path.stat().st_mtime
    except OSError:
        return False
    if age_seconds > RUNTIME_HELPER_STALE_START_SECONDS:
        cleanup_runtime_helper_files(state_root)
        return False
    return True


def stop_runtime_helper(state_root: Path) -> None:
    import signal
    import socket

    metadata = read_json_file(runtime_helper_json_path(state_root))
    socket_path = runtime_helper_socket_path(state_root)
    pid = metadata.get("pid") if isinstance(metadata, dict) else None
    if socket_path.exists():
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(0.2)
                client.connect(str(socket_path))
                client.sendall(b'{"shutdown": true}\n')
                client.shutdown(socket.SHUT_WR)
                while client.recv(4096):
                    pass
        except OSError:
            pass
    if isinstance(pid, int) and process_is_alive(pid):
        try:
            os.killpg(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        except OSError:
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
    cleanup_runtime_helper_files(state_root)


def running_runtime_helper_metadata(state_root: Path) -> dict[str, object] | None:
    metadata = read_json_file(runtime_helper_json_path(state_root))
    if not isinstance(metadata, dict):
        return None
    pid = metadata.get("pid")
    socket_path = metadata.get("socket_path")
    fingerprint = metadata.get("fingerprint")
    context = metadata.get("context")
    if not isinstance(pid, int) or not isinstance(socket_path, str):
        cleanup_runtime_helper_files(state_root)
        return None
    if context != runtime_helper_context(state_root):
        stop_runtime_helper(state_root)
        return None
    if not process_is_alive(pid) or not Path(socket_path).exists():
        cleanup_runtime_helper_files(state_root)
        return None
    if fingerprint != runtime_helper_file_fingerprint():
        stop_runtime_helper(state_root)
        return None
    return metadata


def maybe_wait_for_runtime_helper(state_root: Path) -> dict[str, object] | None:
    metadata = running_runtime_helper_metadata(state_root)
    if metadata is not None:
        return metadata
    if not runtime_helper_start_pending(state_root):
        return None
    if RUNTIME_HELPER_STARTUP_WAIT_SECONDS <= 0:
        return None
    deadline = time.monotonic() + RUNTIME_HELPER_STARTUP_WAIT_SECONDS
    while time.monotonic() < deadline:
        metadata = running_runtime_helper_metadata(state_root)
        if metadata is not None:
            return metadata
        time.sleep(0.01)
    return None


def start_runtime_helper(state_root: Path) -> None:
    import subprocess

    if os.environ.get(RUNTIME_HELPER_DISABLED_ENV):
        return
    if running_runtime_helper_metadata(state_root) is not None:
        return
    ensure_private_dir(state_root)
    cleanup_runtime_helper_files(state_root)
    runtime_helper_starting_path(state_root).write_text(
        '{"created_at_epoch_ms": %.3f}\n' % round(time.time() * 1000, 3)
    )
    subprocess.Popen(
        [
            sys.executable,
            "-m",
            "torfast.runtime_helper",
            "--state-root",
            str(state_root),
        ],
        cwd=REPO_ROOT,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
        start_new_session=True,
    )


def should_prestart_runtime_helper_for_warm(state_root: Path) -> bool:
    if os.environ.get(RUNTIME_HELPER_DISABLED_ENV):
        return False
    if not os.environ.get(WARM_RUNTIME_HELPER_PRESTART_ENABLED_ENV):
        return False
    if running_runtime_helper_metadata(state_root) is not None:
        return False
    if runtime_helper_start_pending(state_root):
        return False
    return True


def request_runtime_helper(
    state_root: Path,
    launcher_args: list[str],
) -> dict[str, object]:
    import json
    import socket

    if os.environ.get(RUNTIME_HELPER_DISABLED_ENV):
        return {"status": "disabled"}
    metadata = maybe_wait_for_runtime_helper(state_root)
    if metadata is None:
        return {"status": "unavailable"}
    socket_path = metadata.get("socket_path")
    if not isinstance(socket_path, str):
        return {"status": "unavailable"}
    request = {"launcher_args": launcher_args}
    dispatched = False
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(0.2)
            client.connect(socket_path)
            client.settimeout(None)
            client.sendall((json.dumps(request) + "\n").encode("utf-8"))
            dispatched = True
            client.shutdown(socket.SHUT_WR)
            chunks: list[bytes] = []
            while True:
                chunk = client.recv(65536)
                if not chunk:
                    break
                chunks.append(chunk)
    except OSError as exc:
        if not dispatched:
            return {"status": "unavailable", "error": f"{type(exc).__name__}: {exc}"}
        return {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
    try:
        payload = json.loads(b"".join(chunks).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
    if not isinstance(payload, dict):
        return {"status": "error", "error": "runtime helper returned non-dict payload"}
    return {"status": "ok", "response": payload}


def relay_runtime_helper_response(payload: dict[str, object]) -> int:
    stdout = payload.get("stdout")
    stderr = payload.get("stderr")
    if isinstance(stdout, str) and stdout:
        print(stdout, end="")
    if isinstance(stderr, str) and stderr:
        print(stderr, end="", file=sys.stderr)
    exit_code = payload.get("exit_code")
    if isinstance(exit_code, int):
        return exit_code
    return 1


def resolve_wait_ready_gate(requested_gate: str) -> str:
    if requested_gate == DEFAULT_BROWSER_LAUNCH_GATE:
        return "tor_boot_95"
    return requested_gate


def wait_for_managed_service_gate(
    state_root: Path,
    *,
    requested_gate: str,
    timeout: float,
    start_helper_if_needed: bool = True,
) -> dict[str, object]:
    from .runtime_helper import (
        browser_launch_gate_ready_text,
        control_ready_for_gate,
        managed_service_ready_for_gate,
        managed_service_ready_result,
        record_managed_service_ready,
        wait_for_existing_service_ready_in_log,
        write_json,
    )

    resolved_gate = resolve_wait_ready_gate(requested_gate)
    report: dict[str, object] = {
        "ok": False,
        "state_root": str(state_root),
        "requested_gate": requested_gate,
        "resolved_gate": resolved_gate,
        "timeout_seconds": round(float(timeout), 3),
    }
    if timeout <= 0:
        report["error"] = "timeout must be positive"
        return report

    service_path = state_root / "tor-service.json"
    service = read_json_file(service_path)
    report["service_before"] = service
    if not isinstance(service, dict):
        report["error"] = f"no managed tor service metadata at {service_path}"
        return report

    pid = service.get("pid")
    tor_log = service.get("tor_log")
    if not isinstance(pid, int) or not isinstance(tor_log, str):
        report["error"] = "managed tor service metadata is incomplete"
        return report
    if not process_is_alive(pid):
        report["error"] = f"managed tor service pid {pid} is not running"
        report["service_after"] = read_json_file(service_path)
        return report

    already_ready = managed_service_ready_for_gate(service, resolved_gate)
    helper_before = running_runtime_helper_metadata(state_root)
    helper_start_requested = False
    if not already_ready and helper_before is None and start_helper_if_needed:
        start_runtime_helper(state_root)
        helper_start_requested = True
        time.sleep(0.05)
    helper_after = running_runtime_helper_metadata(state_root)
    report["runtime_helper"] = {
        "running_before": helper_before is not None,
        "start_requested": helper_start_requested,
        "running_after": helper_after is not None,
    }
    report["already_ready"] = already_ready

    if already_ready:
        report["wait"] = managed_service_ready_result(service, gate=resolved_gate)
        report["service_after"] = service
        report["ok"] = True
        return report

    control_ready = control_ready_for_gate(
        gate=resolved_gate,
        control_port=service.get("control_port"),
        control_cookie_path=service.get("control_cookie_path"),
    )
    if (
        isinstance(control_ready, dict)
        and control_ready.get("ok") is True
        and isinstance(control_ready.get("progress"), int)
    ):
        ready_now = {
            "ok": True,
            "seconds": 0.0,
            "ready_epoch_ms": round(time.time() * 1000, 3),
            "ready_monotonic_seconds": round(time.monotonic(), 6),
            "lines": [],
            "polls": 0,
            "ready_via_control": True,
            "control_bootstrap_phase": control_ready,
            "signal_lines": [],
        }
        updated_service = record_managed_service_ready(
            service,
            gate=resolved_gate,
            wait_result=ready_now,
            actor="fast_runtime_wait_ready",
        )
        write_json(service_path, updated_service)
        report["wait"] = {
            **ready_now,
            "requested_gate": requested_gate,
            "resolved_gate": resolved_gate,
        }
        report["service_after"] = updated_service
        report["ok"] = True
        return report

    wait_result = wait_for_existing_service_ready_in_log(
        pid=pid,
        log_path=Path(tor_log),
        timeout=timeout,
        gate=resolved_gate,
        control_port=service.get("control_port"),
        control_cookie_path=service.get("control_cookie_path"),
        service_path=service_path,
        expected_service=service,
        ready_text=browser_launch_gate_ready_text(resolved_gate),
        process_name="tor",
    )
    report["wait"] = {
        **wait_result,
        "requested_gate": requested_gate,
        "resolved_gate": resolved_gate,
    }
    if wait_result.get("ok") is not True:
        report["error"] = wait_result.get("error") or "managed service wait failed"
        report["service_after"] = read_json_file(service_path)
        return report

    latest_service = read_json_file(service_path)
    if (
        not isinstance(latest_service, dict)
        or latest_service.get("pid") != pid
        or latest_service.get("tor_log") != tor_log
    ):
        report["error"] = "managed tor service changed while waiting"
        report["service_after"] = latest_service
        return report

    if managed_service_ready_for_gate(latest_service, resolved_gate):
        report["service_after"] = latest_service
        report["ok"] = True
        return report

    updated_service = record_managed_service_ready(
        latest_service,
        gate=resolved_gate,
        wait_result=wait_result,
        actor="fast_runtime_wait_ready",
    )
    write_json(service_path, updated_service)
    report["service_after"] = updated_service
    report["ok"] = True
    return report


def maybe_wait_for_managed_open_general_circuit_before_launch(
    state_root: Path,
    *,
    requested_gate: str,
    timeout: float,
) -> dict[str, object]:
    resolved_gate = resolve_wait_ready_gate(requested_gate)
    report: dict[str, object] = {
        "source": "fast_runtime",
        "ok": False,
        "enabled": timeout > 0,
        "requested_gate": requested_gate,
        "resolved_gate": resolved_gate,
        "timeout_seconds": round(float(timeout), 3),
        "poll_interval_seconds": (
            MANAGED_OPEN_ADAPTIVE_GENERAL_CIRCUIT_WAIT_POLL_INTERVAL_SECONDS
        ),
        "state_root": str(state_root),
    }
    if timeout <= 0:
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
        return report
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
        return report
    if resolved_gate != "tor_boot_95":
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
        return report

    service_path = state_root / "tor-service.json"
    service = read_json_file(service_path)
    report["service_before"] = service
    if not isinstance(service, dict):
        report.update(
            {
                "reason": "no managed tor service metadata",
                "skipped": True,
                "matched": False,
                "timed_out": False,
                "seconds": 0.0,
            }
        )
        return report

    report["service_pid"] = service.get("pid")
    report["service_started_epoch_ms"] = service.get("started_epoch_ms")
    control_port = service.get("control_port")
    control_cookie_path = service.get("control_cookie_path")
    ready_gate = service.get("ready_gate")
    if ready_gate == "tor_boot_95" or ready_gate == "tor_boot_100":
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
        return report
    if not isinstance(control_port, int) or not isinstance(control_cookie_path, str):
        report.update(
            {
                "reason": "missing control-port support",
                "skipped": True,
                "matched": False,
                "timed_out": False,
                "seconds": 0.0,
            }
        )
        return report

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
            }
        )
        return report

    wait = wait_for_general_circuits(
        host="127.0.0.1",
        port=control_port,
        cookie_path=Path(control_cookie_path),
        timeout=timeout,
        poll_interval=(
            MANAGED_OPEN_ADAPTIVE_GENERAL_CIRCUIT_WAIT_POLL_INTERVAL_SECONDS
        ),
        min_count=1,
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
                else float(timeout),
                3,
            ),
            "reason": "matched" if wait.get("ok") is True else "timeout_proceed",
            "matched_circuit_count": wait.get("matched_circuit_count"),
            "wait": wait,
        }
    )
    return report


def runtime_helper_state_root_for_args(args: SimpleNamespace) -> Path | None:
    if args.command not in {"warm", "open", "start", "stop"}:
        return None
    return resolve_runtime_state_root(command=args.command, state_root=args.state_root)


def default_runtime_values(command: str) -> dict[str, object]:
    default_state_root = (
        AUTO_STATE_ROOT if command in {"launch", "plan"} else str(DEFAULT_STATE_ROOT)
    )
    return {
        "browser_bin": None,
        "tor_bin": None,
        "url": DEFAULT_URL,
        "port": DEFAULT_PORT,
        "state_root": default_state_root,
        "conflux_client_ux": None,
        "browser_timeout": 0.0,
        "headless": False,
        "skip_browser_default_pref_check": False,
        "gate_diagnostics": False,
        "no_managed_open_browser_overlap": False,
        "warm_browser_prestart": False,
        "managed_open_adaptive_general_circuit_wait_timeout": (
            DEFAULT_MANAGED_OPEN_ADAPTIVE_GENERAL_CIRCUIT_WAIT_TIMEOUT
        ),
        "browser_launch_gate": DEFAULT_BROWSER_LAUNCH_GATE,
        "stream_isolation_probe": False,
        "stream_isolation_probe_timeout": DEFAULT_STREAM_ISOLATION_PROBE_TIMEOUT,
        "dir_cache_seed_root": str(DEFAULT_C_TOR_DIR_CACHE_SEED_ROOT),
        "no_dir_cache_seed": False,
        "browser_startup_seed_root": str(DEFAULT_BROWSER_STARTUP_SEED_ROOT),
        "no_managed_open_settle": True,
        "no_browser_startup_seed": True,
        "profile": None,
        "stock_ui": False,
    }


def coerce_runtime_value(name: str, raw: str) -> object:
    if name == "port":
        return int(raw)
    if name in {
        "browser_timeout",
        "stream_isolation_probe_timeout",
        "managed_open_adaptive_general_circuit_wait_timeout",
    }:
        return float(raw)
    if name == "conflux_client_ux":
        if raw not in CONFLUX_CLIENT_UX_CHOICES:
            raise ValueError(raw)
        return raw
    if name == "browser_launch_gate":
        if raw not in BROWSER_LAUNCH_GATE_CHOICES:
            raise ValueError(raw)
        return raw
    if name == "profile":
        from .profiles import PROFILES

        if raw not in PROFILES:
            raise ValueError(raw)
        return raw
    return raw


def parse_runtime_action_args(argv: list[str]) -> SimpleNamespace | None:
    if not argv:
        return None
    command = argv[0]
    if command not in RUNTIME_ACTIONS:
        return None
    if any(token in {"-h", "--help"} for token in argv[1:]):
        return None

    values = default_runtime_values(command)
    saw_exclusive_bool_flags: set[str] = set()
    index = 1
    while index < len(argv):
        token = argv[index]
        if token == "--":
            return None
        field = VALUE_FLAGS.get(token)
        if field is not None:
            if index + 1 >= len(argv):
                return None
            try:
                values[field] = coerce_runtime_value(field, argv[index + 1])
            except ValueError:
                return None
            index += 2
            continue
        field = STORE_TRUE_FLAGS.get(token)
        if field is not None:
            if field in EXCLUSIVE_BOOL_FLAG_FIELDS:
                if field in saw_exclusive_bool_flags:
                    return None
                saw_exclusive_bool_flags.add(field)
            values[field] = True
            index += 1
            continue
        toggled_flag = STORE_FALSE_FLAGS.get(token)
        if toggled_flag is not None:
            field_name, field_value = toggled_flag
            if field_name in EXCLUSIVE_BOOL_FLAG_FIELDS:
                if field_name in saw_exclusive_bool_flags:
                    return None
                saw_exclusive_bool_flags.add(field_name)
            values[field_name] = field_value
            index += 1
            continue
        return None
    return SimpleNamespace(command=command, **values)


def parse_wait_ready_action_args(argv: list[str]) -> SimpleNamespace | None:
    if not argv or argv[0] != "wait-ready":
        return None
    if any(token in {"-h", "--help"} for token in argv[1:]):
        return None

    state_root = str(DEFAULT_STATE_ROOT)
    gate = DEFAULT_BROWSER_LAUNCH_GATE
    timeout = DEFAULT_WAIT_READY_TIMEOUT
    index = 1
    while index < len(argv):
        token = argv[index]
        if token == "--":
            return None
        if token == "--state-root":
            if index + 1 >= len(argv):
                return None
            state_root = argv[index + 1]
            index += 2
            continue
        if token == "--gate":
            if index + 1 >= len(argv):
                return None
            value = argv[index + 1]
            if value not in BROWSER_LAUNCH_GATE_CHOICES:
                return None
            gate = value
            index += 2
            continue
        if token == "--timeout":
            if index + 1 >= len(argv):
                return None
            try:
                timeout = float(argv[index + 1])
            except ValueError:
                return None
            index += 2
            continue
        return None
    return SimpleNamespace(
        command="wait-ready",
        state_root=state_root,
        gate=gate,
        timeout=timeout,
    )


def try_fast_action(argv: list[str]) -> int | None:
    wait_ready_args = parse_wait_ready_action_args(argv)
    if wait_ready_args is not None:
        report = wait_for_managed_service_gate(
            Path(wait_ready_args.state_root).resolve(),
            requested_gate=wait_ready_args.gate,
            timeout=float(wait_ready_args.timeout),
        )
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report.get("ok") else 1

    args = parse_runtime_action_args(argv)
    if args is None:
        return None
    try:
        from .profiles import apply_profile_to_args

        apply_profile_to_args(
            args,
            managed_state_root=str(DEFAULT_STATE_ROOT),
            auto_state_root=AUTO_STATE_ROOT,
            fresh_state_root=fresh_state_root,
        )
        launcher_args = build_launcher_args(args)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    helper_state_root = runtime_helper_state_root_for_args(args)
    if args.command == "open" and helper_state_root is not None:
        adaptive_wait_timeout = float(
            getattr(
                args,
                "managed_open_adaptive_general_circuit_wait_timeout",
                0.0,
            )
        )
        if adaptive_wait_timeout > 0:
            if (
                not getattr(args, "no_managed_open_browser_overlap", False)
                and not getattr(args, "warm_browser_prestart", False)
            ):
                clear_managed_open_adaptive_general_circuit_wait_report(
                    helper_state_root
                )
            else:
                report = maybe_wait_for_managed_open_general_circuit_before_launch(
                    helper_state_root,
                    requested_gate=args.browser_launch_gate,
                    timeout=adaptive_wait_timeout,
                )
                write_json_file(
                    managed_open_adaptive_general_circuit_wait_report_path(
                        helper_state_root
                    ),
                    report,
                )
        else:
            clear_managed_open_adaptive_general_circuit_wait_report(
                helper_state_root
            )
    warm_helper_prestarted = False
    if (
        args.command == "warm"
        and helper_state_root is not None
        and should_prestart_runtime_helper_for_warm(helper_state_root)
    ):
        start_runtime_helper(helper_state_root)
        warm_helper_prestarted = True
    if args.command in {"open", "start"} and helper_state_root is not None:
        helper_result = request_runtime_helper(helper_state_root, launcher_args)
        if helper_result.get("status") == "ok":
            response = helper_result.get("response")
            if isinstance(response, dict):
                return relay_runtime_helper_response(response)
            print("runtime helper returned invalid response", file=sys.stderr)
            return 1
        if helper_result.get("status") == "error":
            print(
                "runtime helper request failed after dispatch: "
                + str(helper_result.get("error", "unknown error")),
                file=sys.stderr,
            )
            return 1
    exit_code = run_launcher_args(launcher_args)
    if helper_state_root is not None:
        if args.command == "stop":
            stop_runtime_helper(helper_state_root)
        elif exit_code != 0 and args.command == "warm" and warm_helper_prestarted:
            stop_runtime_helper(helper_state_root)
        elif exit_code == 0 and args.command in {"warm", "open", "start"}:
            if not (args.command == "warm" and warm_helper_prestarted):
                start_runtime_helper(helper_state_root)
    return exit_code
