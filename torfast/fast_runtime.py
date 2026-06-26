"""Fast runtime entry helpers for common torfast actions."""

from __future__ import annotations

import functools
import importlib.util
import os
from pathlib import Path
import shutil
import sys
import time
from types import SimpleNamespace

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
RUNTIME_HELPER_DISABLED_ENV = "TORFAST_DISABLE_RUNTIME_HELPER"
RUNTIME_HELPER_STARTUP_WAIT_SECONDS = 0.25
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
    "--browser-launch-gate": "browser_launch_gate",
    "--stream-isolation-probe-timeout": "stream_isolation_probe_timeout",
    "--dir-cache-seed-root": "dir_cache_seed_root",
    "--browser-startup-seed-root": "browser_startup_seed_root",
}
STORE_TRUE_FLAGS = {
    "--headless": "headless",
    "--skip-browser-default-pref-check": "skip_browser_default_pref_check",
    "--stream-isolation-probe": "stream_isolation_probe",
    "--no-dir-cache-seed": "no_dir_cache_seed",
}
STORE_FALSE_FLAGS = {
    "--browser-startup-seed": ("no_browser_startup_seed", False),
    "--no-browser-startup-seed": ("no_browser_startup_seed", True),
}


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
    if args.browser_launch_gate != DEFAULT_BROWSER_LAUNCH_GATE:
        launcher_args.extend(["--browser-launch-gate", args.browser_launch_gate])
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
        launcher_args.extend(["--leave-tor-running", "--reuse-tor-if-running"])
    elif args.command == "plan":
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
        "browser_launch_gate": DEFAULT_BROWSER_LAUNCH_GATE,
        "stream_isolation_probe": False,
        "stream_isolation_probe_timeout": DEFAULT_STREAM_ISOLATION_PROBE_TIMEOUT,
        "dir_cache_seed_root": str(DEFAULT_C_TOR_DIR_CACHE_SEED_ROOT),
        "no_dir_cache_seed": False,
        "browser_startup_seed_root": str(DEFAULT_BROWSER_STARTUP_SEED_ROOT),
        "no_browser_startup_seed": True,
    }


def coerce_runtime_value(name: str, raw: str) -> object:
    if name == "port":
        return int(raw)
    if name in {"browser_timeout", "stream_isolation_probe_timeout"}:
        return float(raw)
    if name == "conflux_client_ux":
        if raw not in CONFLUX_CLIENT_UX_CHOICES:
            raise ValueError(raw)
        return raw
    if name == "browser_launch_gate":
        if raw not in BROWSER_LAUNCH_GATE_CHOICES:
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
    saw_browser_startup_seed_flag = False
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
            values[field] = True
            index += 1
            continue
        startup_seed_flag = STORE_FALSE_FLAGS.get(token)
        if startup_seed_flag is not None:
            if saw_browser_startup_seed_flag:
                return None
            saw_browser_startup_seed_flag = True
            field_name, field_value = startup_seed_flag
            values[field_name] = field_value
            index += 1
            continue
        return None
    return SimpleNamespace(command=command, **values)


def try_fast_action(argv: list[str]) -> int | None:
    args = parse_runtime_action_args(argv)
    if args is None:
        return None
    try:
        launcher_args = build_launcher_args(args)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    helper_state_root = runtime_helper_state_root_for_args(args)
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
        elif exit_code == 0 and args.command in {"warm", "open", "start"}:
            start_runtime_helper(helper_state_root)
    return exit_code
