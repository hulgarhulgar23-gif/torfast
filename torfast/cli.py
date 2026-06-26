"""Command-line interface for the current tor-fast runtime."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import functools
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

REPO_ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = REPO_ROOT / "tools" / "launch_torfast_browser.py"
DEFAULT_BROWSER_BIN = REPO_ROOT / "tmp" / "browser" / "Tor Browser.app" / "Contents" / "MacOS" / "firefox"
DEFAULT_TOR_BIN = REPO_ROOT / "tmp" / "browser" / "Tor Browser.app" / "Contents" / "MacOS" / "Tor" / "tor"
DEFAULT_LOCAL_TOR_BIN = REPO_ROOT / "upstream" / "tor" / "src" / "app" / "tor"
DEFAULT_STATE_ROOT = REPO_ROOT / "tmp" / "torfast-browser"
DEFAULT_FRESH_STATE_ROOT_PARENT = REPO_ROOT / "tmp" / "torfast-launches"
DEFAULT_BROWSER_INSTALL_ROOT = REPO_ROOT / "tmp" / "browser"
DEFAULT_BROWSER_DOWNLOAD_ROOT = REPO_ROOT / "tmp" / "browser-downloads"
DEFAULT_C_TOR_DIR_CACHE_SEED_ROOT = REPO_ROOT / "tmp" / "torfast-c-tor-dir-cache-seed"
DEFAULT_BROWSER_STARTUP_SEED_ROOT = (
    REPO_ROOT / "tmp" / "torfast-browser-startup-seed"
)
DEFAULT_URL = "about:tor"
AUTO_STATE_ROOT = "__TORFAST_AUTO_STATE_ROOT__"
DEFAULT_BROWSER_LAUNCH_GATE = "auto"


@dataclass(frozen=True)
class StatePaths:
    state_root: Path
    tor_service_json: Path
    launch_json: Path

    def as_dict(self) -> dict[str, str]:
        return {
            "state_root": str(self.state_root),
            "tor_service_json": str(self.tor_service_json),
            "launch_json": str(self.launch_json),
        }


def read_browser_default_prefs(browser_bin: Path) -> dict[str, object]:
    from .browser_defaults import read_browser_default_prefs as _read_browser_default_prefs

    return _read_browser_default_prefs(browser_bin)


def validate_default_prefs(
    default_pref_proof: dict[str, object],
) -> dict[str, object]:
    from .browser_defaults import validate_default_prefs as _validate_default_prefs

    return _validate_default_prefs(default_pref_proof)


def install_browser(*args: object, **kwargs: object) -> dict[str, object]:
    from .browser_install import install_browser as _install_browser

    return _install_browser(*args, **kwargs)


def describe_seed(seed_root: Path) -> dict[str, object]:
    from .dir_cache_seed import describe_seed as _describe_seed

    return _describe_seed(seed_root)


def describe_browser_startup_seed(seed_root: Path) -> dict[str, object]:
    from .browser_startup_seed import (
        describe_seed as _describe_browser_startup_seed,
    )

    return _describe_browser_startup_seed(seed_root)


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


def launcher_args_from_command(command: list[str]) -> list[str] | None:
    if len(command) < 2:
        return None
    try:
        launcher_path = Path(command[1]).resolve()
    except OSError:
        return None
    if launcher_path != LAUNCHER.resolve():
        return None
    return command[2:]


def run_action_command(command: list[str]) -> int:
    launcher_args = launcher_args_from_command(command)
    if launcher_args is None:
        completed = subprocess.run(command, cwd=REPO_ROOT)
        return completed.returncode

    # Keep the old command shape for tests and logs, but skip the extra Python hop.
    launcher_main = load_launcher_main()
    try:
        result = launcher_main(launcher_args)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 1
    return int(result) if result is not None else 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "status":
            print(
                json.dumps(
                    collect_status(Path(args.state_root).resolve()),
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        if args.command == "doctor":
            report = collect_doctor(
                Path(args.state_root).resolve(),
                browser_bin=args.browser_bin,
                tor_bin=args.tor_bin,
                dir_cache_seed_root=Path(args.dir_cache_seed_root).resolve(),
                browser_startup_seed_root=Path(
                    args.browser_startup_seed_root
                ).resolve(),
            )
            print(json.dumps(report, indent=2, sort_keys=True))
            return 0 if report.get("ok") else 1
        if args.command == "install-browser":
            report = install_browser(
                version=args.version,
                install_root=Path(args.install_root).resolve(),
                downloads_root=Path(args.download_root).resolve(),
                force=args.force,
                dry_run=args.dry_run,
            )
            if args.prime_after_install and not args.dry_run:
                plan = report.get("plan", {})
                browser_bin = (
                    plan.get("browser_bin") if isinstance(plan, dict) else None
                )
                if not isinstance(browser_bin, str):
                    raise RuntimeError("install-browser report did not include browser_bin")
                prime_command = [
                    sys.executable,
                    "-m",
                    "torfast",
                    "prime",
                    "--browser-bin",
                    browser_bin,
                    "--state-root",
                    str(Path(args.prime_state_root).resolve()),
                    "--port",
                    str(args.prime_port),
                    "--dir-cache-seed-root",
                    str(Path(args.prime_dir_cache_seed_root).resolve()),
                ]
                report["prime_after_install"] = run_followup_command(prime_command)
                if not report["prime_after_install"].get("ok"):
                    report["ok"] = False
            if (
                args.prime_browser_startup_seed_after_install
                and not args.dry_run
            ):
                plan = report.get("plan", {})
                browser_bin = (
                    plan.get("browser_bin") if isinstance(plan, dict) else None
                )
                if not isinstance(browser_bin, str):
                    raise RuntimeError(
                        "install-browser report did not include browser_bin"
                    )
                if args.prime_browser_startup_timeout <= 0:
                    raise RuntimeError(
                        "--prime-browser-startup-timeout must be positive"
                    )
                if not report.get("ok"):
                    report["prime_browser_startup_seed_after_install"] = {
                        "command": None,
                        "exit_code": None,
                        "stdout_tail": [],
                        "stderr_tail": [],
                        "ok": False,
                        "skipped": True,
                        "reason": "prior install follow-up step failed",
                    }
                else:
                    startup_seed_command = [
                        sys.executable,
                        "-m",
                        "torfast",
                        "launch",
                        "--browser-bin",
                        browser_bin,
                        "--state-root",
                        str(Path(args.prime_state_root).resolve()),
                        "--port",
                        str(args.prime_port),
                        "--dir-cache-seed-root",
                        str(Path(args.prime_dir_cache_seed_root).resolve()),
                        "--headless",
                        "--browser-timeout",
                        str(args.prime_browser_startup_timeout),
                        "--url",
                        DEFAULT_URL,
                    ]
                    report["prime_browser_startup_seed_after_install"] = (
                        run_followup_command(startup_seed_command)
                    )
                    if not report["prime_browser_startup_seed_after_install"].get(
                        "ok"
                    ):
                        report["ok"] = False
            print(json.dumps(report, indent=2, sort_keys=True))
            return 0 if report.get("ok") else 1

        command = build_action_command(args)
        return run_action_command(command)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2


def run_followup_command(command: list[str]) -> dict[str, object]:
    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    return {
        "command": command,
        "exit_code": completed.returncode,
        "stdout_tail": completed.stdout.splitlines()[-40:],
        "stderr_tail": completed.stderr.splitlines()[-40:],
        "ok": completed.returncode == 0,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="torfast")
    subparsers = parser.add_subparsers(dest="command", required=True)

    start = subparsers.add_parser(
        "start",
        aliases=["open"],
        help="open Tor Browser and keep managed C Tor warm for the next run",
    )
    add_runtime_args(start, default_state_root=str(DEFAULT_STATE_ROOT))

    warm = subparsers.add_parser(
        "warm",
        help="start or reuse managed C Tor without opening the browser; default auto now returns once the managed warm path reaches its current ready gate",
    )
    add_runtime_args(warm, default_state_root=str(DEFAULT_STATE_ROOT))

    prime = subparsers.add_parser(
        "prime",
        help="bootstrap C Tor once and stop, leaving cached state for later launches",
    )
    add_runtime_args(prime, default_state_root=str(DEFAULT_STATE_ROOT))

    launch = subparsers.add_parser(
        "launch",
        help="open Tor Browser once and stop managed C Tor when the browser exits",
    )
    add_runtime_args(launch, default_state_root=AUTO_STATE_ROOT)

    plan = subparsers.add_parser(
        "plan",
        help="write the current launch plan without starting Tor or the browser",
    )
    add_runtime_args(plan, default_state_root=AUTO_STATE_ROOT)

    install_browser_parser = subparsers.add_parser(
        "install-browser",
        help="download, verify, and install a Tor Browser app copy",
    )
    add_install_browser_args(install_browser_parser)

    stop = subparsers.add_parser(
        "stop",
        help="stop the managed warm C Tor process for this state root",
    )
    add_state_root_arg(stop)

    status = subparsers.add_parser(
        "status",
        help="show the managed service and last-launch state for this state root",
    )
    add_state_root_arg(status)

    doctor = subparsers.add_parser(
        "doctor",
        help="check binary discovery, browser default prefs, and managed service state",
    )
    add_doctor_args(doctor)

    return parser


def add_state_root_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--state-root", default=str(DEFAULT_STATE_ROOT))


def add_runtime_args(
    parser: argparse.ArgumentParser,
    *,
    default_state_root: str,
) -> None:
    add_binary_args(parser)
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--port", type=int, default=19450)
    parser.add_argument("--state-root", default=default_state_root)
    parser.add_argument(
        "--conflux-client-ux",
        choices=("latency", "throughput", "throughput_lowmem"),
    )
    parser.add_argument("--browser-timeout", type=float, default=0.0)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--skip-browser-default-pref-check", action="store_true")
    parser.add_argument(
        "--browser-launch-gate",
        choices=("auto", "socks_ready", "tor_boot_90", "tor_boot_95", "tor_boot_100"),
        default=DEFAULT_BROWSER_LAUNCH_GATE,
        help=(
            "browser launch gate; default auto keeps cold network starts on "
            "tor_boot_95 but uses socks_ready on warm/reused managed paths"
        ),
    )
    parser.add_argument("--stream-isolation-probe", action="store_true")
    parser.add_argument("--stream-isolation-probe-timeout", type=float, default=3.0)
    parser.add_argument(
        "--dir-cache-seed-root",
        default=str(DEFAULT_C_TOR_DIR_CACHE_SEED_ROOT),
    )
    parser.add_argument("--no-dir-cache-seed", action="store_true")
    parser.add_argument(
        "--browser-startup-seed-root",
        default=str(DEFAULT_BROWSER_STARTUP_SEED_ROOT),
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
    )
    parser.set_defaults(no_browser_startup_seed=True)


def add_binary_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--browser-bin")
    parser.add_argument("--tor-bin")


def add_dir_cache_seed_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--dir-cache-seed-root",
        default=str(DEFAULT_C_TOR_DIR_CACHE_SEED_ROOT),
    )


def add_doctor_args(parser: argparse.ArgumentParser) -> None:
    add_state_root_arg(parser)
    add_binary_args(parser)
    add_dir_cache_seed_args(parser)
    parser.add_argument(
        "--browser-startup-seed-root",
        default=str(DEFAULT_BROWSER_STARTUP_SEED_ROOT),
    )


def add_install_browser_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--version", default="latest")
    parser.add_argument("--install-root", default=str(DEFAULT_BROWSER_INSTALL_ROOT))
    parser.add_argument("--download-root", default=str(DEFAULT_BROWSER_DOWNLOAD_ROOT))
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    prime_group = parser.add_mutually_exclusive_group()
    prime_group.add_argument(
        "--prime-after-install",
        dest="prime_after_install",
        action="store_true",
        help="prime the shared cache-only Tor seed after install or reuse",
    )
    prime_group.add_argument(
        "--no-prime-after-install",
        dest="prime_after_install",
        action="store_false",
        help="skip the post-install Tor seed prime step",
    )
    parser.set_defaults(prime_after_install=True)
    parser.add_argument("--prime-state-root", default=str(DEFAULT_STATE_ROOT))
    parser.add_argument("--prime-port", type=int, default=19450)
    parser.add_argument(
        "--prime-dir-cache-seed-root",
        default=str(DEFAULT_C_TOR_DIR_CACHE_SEED_ROOT),
    )
    startup_seed_group = parser.add_mutually_exclusive_group()
    startup_seed_group.add_argument(
        "--prime-browser-startup-seed-after-install",
        dest="prime_browser_startup_seed_after_install",
        action="store_true",
        help=(
            "optionally do one short headless Tor Browser launch after install "
            "or reuse so the shared startup-only browser seed exists before "
            "the first real launch"
        ),
    )
    startup_seed_group.add_argument(
        "--no-prime-browser-startup-seed-after-install",
        dest="prime_browser_startup_seed_after_install",
        action="store_false",
        help="skip the optional headless browser-startup-seed prime step",
    )
    parser.set_defaults(prime_browser_startup_seed_after_install=False)
    parser.add_argument(
        "--prime-browser-startup-timeout",
        type=float,
        default=8.0,
        help="seconds to keep the headless browser open when priming the browser startup seed",
    )


def build_action_command(args: argparse.Namespace) -> list[str]:
    if args.command == "stop":
        return [
            sys.executable,
            str(LAUNCHER),
            "--state-root",
            str(Path(args.state_root).resolve()),
            "--stop-managed-tor",
        ]

    browser = discover_browser_bin(args.browser_bin)
    if not browser["found"]:
        candidates = ", ".join(browser["candidates"])
        raise RuntimeError(
            "Tor Browser binary not found; pass --browser-bin or install it in one of: "
            + candidates
        )
    tor = discover_tor_bin(args.tor_bin)
    if not tor["found"]:
        candidates = ", ".join(tor["candidates"])
        raise RuntimeError(
            "C Tor binary not found; pass --tor-bin or build/install it in one of: "
            + candidates
        )

    command = [
        sys.executable,
        str(LAUNCHER),
        "--browser-bin",
        str(Path(str(browser["path"])).resolve()),
        "--tor-bin",
        str(Path(str(tor["path"])).resolve()),
        "--url",
        args.url,
        "--port",
        str(args.port),
        "--state-root",
        str(resolve_runtime_state_root(command=args.command, state_root=args.state_root)),
    ]
    if args.conflux_client_ux:
        command.extend(["--conflux-client-ux", args.conflux_client_ux])
    if args.browser_timeout != 0.0:
        command.extend(["--browser-timeout", str(args.browser_timeout)])
    if args.headless:
        command.append("--headless")
    if args.skip_browser_default_pref_check:
        command.append("--skip-browser-default-pref-check")
    if (
        getattr(args, "browser_launch_gate", DEFAULT_BROWSER_LAUNCH_GATE)
        != DEFAULT_BROWSER_LAUNCH_GATE
    ):
        command.extend(["--browser-launch-gate", args.browser_launch_gate])
    if getattr(args, "stream_isolation_probe", False):
        command.append("--stream-isolation-probe")
    if getattr(args, "stream_isolation_probe_timeout", 3.0) != 3.0:
        command.extend(
            [
                "--stream-isolation-probe-timeout",
                str(args.stream_isolation_probe_timeout),
            ]
        )
    if args.dir_cache_seed_root != str(DEFAULT_C_TOR_DIR_CACHE_SEED_ROOT):
        command.extend(["--dir-cache-seed-root", str(Path(args.dir_cache_seed_root).resolve())])
    if args.no_dir_cache_seed:
        command.append("--no-dir-cache-seed")
    if args.browser_startup_seed_root != str(DEFAULT_BROWSER_STARTUP_SEED_ROOT):
        command.extend(
            [
                "--browser-startup-seed-root",
                str(Path(args.browser_startup_seed_root).resolve()),
            ]
        )
    if args.no_browser_startup_seed:
        command.append("--no-browser-startup-seed")
    else:
        command.append("--browser-startup-seed")

    if args.command == "warm":
        command.extend(
            [
                "--leave-tor-running",
                "--reuse-tor-if-running",
                "--start-managed-tor-only",
            ]
        )
    elif args.command == "prime":
        command.append("--start-managed-tor-only")
    elif args.command in ("start", "open"):
        command.extend(["--leave-tor-running", "--reuse-tor-if-running"])
    elif args.command == "plan":
        command.append("--dry-run")

    return command


def resolve_runtime_state_root(*, command: str, state_root: str) -> Path:
    if state_root != AUTO_STATE_ROOT:
        return Path(state_root).resolve()
    if command not in {"launch", "plan"}:
        return DEFAULT_STATE_ROOT.resolve()
    return fresh_state_root(command)


def fresh_state_root(command_name: str) -> Path:
    run_id = time.strftime("%Y%m%dT%H%M%S")
    suffix = time.time_ns() % 1_000_000_000
    return (
        DEFAULT_FRESH_STATE_ROOT_PARENT
        / f"{command_name}-{run_id}-{os.getpid()}-{suffix:09d}"
    ).resolve()


def resolve_state_paths(state_root: Path) -> StatePaths:
    return StatePaths(
        state_root=state_root,
        tor_service_json=state_root / "tor-service.json",
        launch_json=state_root / "launch.json",
    )


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


def collect_status(state_root: Path) -> dict[str, object]:
    paths = resolve_state_paths(state_root)
    service = read_json(paths.tor_service_json)
    launch = read_json(paths.launch_json)

    pid = service.get("pid") if isinstance(service, dict) else None
    port = service.get("port") if isinstance(service, dict) else None
    running = isinstance(pid, int) and process_is_alive(pid)

    return {
        "ok": True,
        "paths": paths.as_dict(),
        "managed_tor": {
            "configured": isinstance(service, dict),
            "running": running,
            "stale": isinstance(service, dict) and not running,
            "pid": pid,
            "port": port,
            "service": service,
        },
        "last_launch": launch,
    }


def candidate_browser_bins() -> list[Path]:
    candidates: list[Path] = []
    env_value = os.environ.get("TORFAST_BROWSER_BIN")
    if env_value:
        candidates.append(Path(env_value).expanduser())
    candidates.extend(
        [
            DEFAULT_BROWSER_BIN,
            Path("/Applications/Tor Browser.app/Contents/MacOS/firefox"),
            Path.home() / "Applications" / "Tor Browser.app" / "Contents" / "MacOS" / "firefox",
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


def read_tor_version(path: Path) -> dict[str, object]:
    try:
        completed = subprocess.run(
            [str(path), "--version"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=15.0,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    output = (completed.stdout or completed.stderr or "").strip()
    return {
        "ok": completed.returncode == 0,
        "exit_code": completed.returncode,
        "output": output,
    }


def collect_doctor(
    state_root: Path,
    *,
    browser_bin: str | None = None,
    tor_bin: str | None = None,
    dir_cache_seed_root: Path | None = None,
    browser_startup_seed_root: Path | None = None,
) -> dict[str, object]:
    browser = discover_browser_bin(browser_bin)
    tor = discover_tor_bin(tor_bin)
    seed_root = dir_cache_seed_root or DEFAULT_C_TOR_DIR_CACHE_SEED_ROOT
    startup_seed_root = (
        browser_startup_seed_root or DEFAULT_BROWSER_STARTUP_SEED_ROOT
    )

    browser_pref_proof: dict[str, object] | None = None
    browser_pref_check: dict[str, object] | None = None
    if browser["found"] and isinstance(browser.get("path"), str):
        browser_pref_proof = read_browser_default_prefs(Path(browser["path"]))
        browser_pref_check = validate_default_prefs(browser_pref_proof)

    tor_version: dict[str, object] | None = None
    if tor["found"] and isinstance(tor.get("path"), str):
        tor_version = read_tor_version(Path(tor["path"]))

    status = collect_status(state_root)
    ok = (
        browser["found"]
        and tor["found"]
        and isinstance(browser_pref_check, dict)
        and browser_pref_check.get("ok") is True
    )
    return {
        "ok": ok,
        "repo_root": str(REPO_ROOT),
        "launcher": str(LAUNCHER),
        "browser": {
            **browser,
            "default_pref_proof": browser_pref_proof,
            "default_pref_check": browser_pref_check,
        },
        "tor": {
            **tor,
            "version": tor_version,
        },
        "managed_state": status,
        "dir_cache_seed": describe_seed(Path(seed_root)),
        "browser_startup_seed": describe_browser_startup_seed(
            Path(startup_seed_root)
        ),
    }
