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

from .fast_runtime import (
    DEFAULT_MANAGED_OPEN_ADAPTIVE_GENERAL_CIRCUIT_WAIT_TIMEOUT,
    wait_for_managed_service_gate,
)
from .profiles import (
    PROFILE_ORDER,
    PROFILES,
    active_profile_name,
    apply_profile_to_args,
    describe_profiles,
    save_profile,
)
from .term import (
    CapturedStdout,
    Spinner,
    color_enabled,
    format_seconds,
    human_output_enabled,
    presence_symbol,
    render_check_line,
    render_panel,
    render_wordmark,
    status_symbol,
    style,
)

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
WAIT_READY_GATE_CHOICES = (
    "auto",
    "socks_ready",
    "tor_boot_90",
    "tor_boot_95",
    "tor_boot_100",
)
DEFAULT_WAIT_READY_TIMEOUT = 180.0
VERSION_FALLBACK = "0.1.0"
ACTION_SPINNER_LABELS = {
    "start": "opening Tor Browser over Tor",
    "open": "opening Tor Browser over Tor",
    "launch": "opening Tor Browser over Tor",
    "warm": "warming managed Tor",
    "prime": "priming Tor directory cache",
    "plan": "writing launch plan",
    "stop": "stopping managed Tor",
}


def package_version() -> str:
    try:
        from importlib.metadata import version

        return version("torfast")
    except Exception:
        return VERSION_FALLBACK


def version_banner(*, enabled: bool) -> str:
    tagline = "faster Tor Browser launches with proven exact quality"
    return "\n".join(
        [
            render_wordmark(enabled=enabled),
            f"torfast {package_version()}  {style(tagline, 'dim', enabled=enabled)}",
        ]
    )


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
    human = human_output_enabled(args)

    try:
        if args.command == "profile":
            if args.name:
                report = save_profile(args.name)
                report.update(describe_profiles())
            else:
                report = describe_profiles()
            if human:
                print(render_profiles_human(report, enabled=color_enabled()))
            else:
                print(json.dumps(report, indent=2, sort_keys=True))
            return 0
        if args.command in {"start", "open", "warm", "prime", "launch", "plan"}:
            apply_profile_to_args(
                args,
                managed_state_root=str(DEFAULT_STATE_ROOT),
                auto_state_root=AUTO_STATE_ROOT,
                fresh_state_root=fresh_state_root,
            )
        if args.command == "status":
            report = collect_status(Path(args.state_root).resolve())
            if human:
                print(render_status_human(report, enabled=color_enabled()))
            else:
                print(json.dumps(report, indent=2, sort_keys=True))
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
            if human:
                print(render_doctor_human(report, enabled=color_enabled()))
            else:
                print(json.dumps(report, indent=2, sort_keys=True))
            return 0 if report.get("ok") else 1
        if args.command == "wait-ready":
            report = wait_for_managed_service_gate(
                Path(args.state_root).resolve(),
                requested_gate=args.gate,
                timeout=args.timeout,
            )
            if human:
                print(render_wait_ready_human(report, enabled=color_enabled()))
            else:
                print(json.dumps(report, indent=2, sort_keys=True))
            return 0 if report.get("ok") else 1
        if args.command == "install-app":
            from .app_bundle import install_app

            branded_bin: str | None = None
            branded_report: dict[str, object] | None = None
            if not args.no_branded_browser:
                branded_report = build_branded_browser_copy(args.browser_bin)
                if branded_report.get("ok"):
                    branded_bin = str(branded_report.get("browser_bin"))
            report = install_app(
                dest_root=Path(args.dest).expanduser().resolve() if args.dest else None,
                version=package_version(),
                force=args.force,
                include_summon_service=not args.no_summon_service,
                include_icon=not args.no_icon,
                browser_bin=branded_bin,
            )
            if branded_report is not None:
                report["branded_browser"] = branded_report
            if human:
                print(render_install_app_human(report, enabled=color_enabled()))
            else:
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
        if human:
            return run_action_command_human(command, command_name=args.command)
        return run_action_command(command)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2


def run_action_command_human(command: list[str], *, command_name: str) -> int:
    """Run an action with a live spinner and render a receipt panel.

    The launcher's machine output is captured, parsed, and re-rendered for
    people; if parsing fails the captured output is printed verbatim so no
    information is ever dropped.
    """
    label = ACTION_SPINNER_LABELS.get(command_name, command_name)
    with Spinner(label) as spinner:
        with CapturedStdout() as buffer:
            exit_code = run_action_command(command)
        wall_seconds = spinner.elapsed_seconds
    present_action_result(
        command_name,
        buffer.getvalue(),
        exit_code=exit_code,
        wall_seconds=wall_seconds,
    )
    return exit_code


def run_fast_action_human(argv: list[str]) -> int | None:
    """Human-mode wrapper for the fast-path dispatch in `torfast.__main__`.

    Returns None when argv is not a fast action so the caller falls through
    to the full CLI, mirroring `try_fast_action`.
    """
    from .fast_runtime import try_fast_action

    command_name = next(
        (arg for arg in argv if not arg.startswith("-")), "action"
    )
    label = ACTION_SPINNER_LABELS.get(command_name, command_name)
    with Spinner(label) as spinner:
        with CapturedStdout() as buffer:
            exit_code = try_fast_action(argv)
        wall_seconds = spinner.elapsed_seconds
    captured = buffer.getvalue()
    if exit_code is None:
        if captured:
            print(captured, end="" if captured.endswith("\n") else "\n")
        return None
    present_action_result(
        command_name,
        captured,
        exit_code=exit_code,
        wall_seconds=wall_seconds,
    )
    return exit_code


def present_action_result(
    command_name: str,
    captured: str,
    *,
    exit_code: int,
    wall_seconds: float,
) -> None:
    wrote_path, summary = parse_launcher_output(captured)
    enabled = color_enabled()
    if summary is None:
        if captured:
            print(captured, end="" if captured.endswith("\n") else "\n")
        print(
            render_check_line(
                exit_code == 0,
                f"{command_name} {'finished' if exit_code == 0 else 'failed'}",
                f"in {format_seconds(wall_seconds)}",
                enabled=enabled,
            )
        )
        return
    if command_name == "wait-ready":
        print(render_wait_ready_human(summary, enabled=enabled))
        return
    print(
        render_action_receipt(
            command_name,
            summary,
            wrote_path=wrote_path,
            wall_seconds=wall_seconds,
            exit_code=exit_code,
            enabled=enabled,
        )
    )


def parse_launcher_output(
    captured: str,
) -> tuple[str | None, dict[str, object] | None]:
    """Split launcher stdout into the `wrote <path>` line and the JSON summary."""
    wrote_path: str | None = None
    json_start: int | None = None
    lines = captured.splitlines()
    for index, line in enumerate(lines):
        if line.startswith("wrote "):
            wrote_path = line[len("wrote ") :].strip()
        if line.startswith("{") and json_start is None:
            json_start = index
    if json_start is None:
        return wrote_path, None
    try:
        payload = json.loads("\n".join(lines[json_start:]))
    except json.JSONDecodeError:
        return wrote_path, None
    return wrote_path, payload if isinstance(payload, dict) else None


def render_action_receipt(
    command_name: str,
    summary: dict[str, object],
    *,
    wrote_path: str | None,
    wall_seconds: float,
    exit_code: int,
    enabled: bool,
) -> str:
    browser = summary.get("browser")
    browser = browser if isinstance(browser, dict) else {}
    tor_boot = summary.get("tor_boot")
    tor_boot = tor_boot if isinstance(tor_boot, dict) else {}
    pref_check = summary.get("browser_default_pref_check")
    pref_check = pref_check if isinstance(pref_check, dict) else {}

    ok = exit_code == 0
    lines = [
        render_check_line(
            ok,
            f"{command_name} {'done' if ok else 'failed'}",
            f"wall {format_seconds(wall_seconds)}",
            enabled=enabled,
        )
    ]
    rows: list[tuple[str, str]] = []
    url = summary.get("url")
    if isinstance(url, str):
        rows.append(("page", url))
    if isinstance(tor_boot.get("seconds"), (int, float)):
        rows.append(
            (
                "tor ready",
                f"{format_seconds(tor_boot.get('seconds'))} "
                + str(status_symbol(tor_boot.get("ok"), enabled=enabled)),
            )
        )
    if isinstance(browser.get("elapsed_seconds"), (int, float)):
        rows.append(
            (
                "browser session",
                f"{format_seconds(browser.get('elapsed_seconds'))} "
                + str(status_symbol(browser.get("ok"), enabled=enabled)),
            )
        )
    profile_label = summary.get("profile")
    if isinstance(profile_label, str):
        symbol = PROFILE_SYMBOLS.get(profile_label, "")
        rows.append(("profile", f"{symbol} {profile_label}".strip()))
    ui_theme = summary.get("ui_theme")
    if isinstance(ui_theme, str):
        rows.append(
            (
                "ui theme",
                ui_theme if ui_theme == "stock" else f"{ui_theme} (chrome-only)",
            )
        )
    gate = summary.get("browser_launch_gate")
    if isinstance(gate, str):
        rows.append(("launch gate", gate))
    port = summary.get("port")
    if isinstance(port, int):
        rows.append(("socks port", str(port)))
    if pref_check:
        rows.append(
            (
                "quality prefs",
                str(status_symbol(pref_check.get("ok"), enabled=enabled)),
            )
        )
    if wrote_path:
        rows.append(("full report", wrote_path))
    if rows:
        width = max(len(label) for label, _ in rows)
        for label, value in rows:
            lines.append(
                f"    {style(label.ljust(width), 'dim', enabled=enabled)}  {value}"
            )
    return "\n".join(lines)


PROFILE_SYMBOLS = {name: PROFILES[name].symbol for name in PROFILE_ORDER}
PROFILE_SYMBOL_COLORS = {
    "turbo": ("yellow",),
    "balanced": ("green",),
    "paranoid": ("cyan",),
}


def render_profiles_human(
    report: dict[str, object],
    *,
    enabled: bool,
) -> str:
    profiles = report.get("profiles")
    profiles = profiles if isinstance(profiles, list) else []
    lines = [style("torfast speed profiles", "bold", enabled=enabled)]
    saved_name = report.get("profile") if report.get("ok") else None
    if isinstance(saved_name, str):
        lines.append(
            render_check_line(
                True,
                f"profile set to {saved_name}",
                "applies to every next run",
                enabled=enabled,
            )
        )
    name_width = max((len(str(p.get("name"))) for p in profiles), default=0)
    estimate_width = max(
        (len(str(p.get("open_estimate"))) for p in profiles), default=0
    )
    for payload in profiles:
        if not isinstance(payload, dict):
            continue
        name = str(payload.get("name"))
        active = payload.get("active") is True
        symbol = style(
            PROFILE_SYMBOLS.get(name, " "),
            *PROFILE_SYMBOL_COLORS.get(name, ()),
            enabled=enabled,
        )
        marker = style("▸", "magenta", "bold", enabled=enabled) if active else " "
        name_text = name.ljust(name_width)
        if active:
            name_text = style(name_text, "bold", enabled=enabled)
        estimate = style(
            str(payload.get("open_estimate", "")).ljust(estimate_width),
            "dim" if not active else "cyan",
            enabled=enabled,
        )
        tagline = str(payload.get("tagline", ""))
        lines.append(f"{marker} {symbol} {name_text}  {estimate}  {tagline}")
    lines.append(
        render_check_line(
            True,
            "anonymity identical at every level",
            "3-hop circuits · stock fingerprint · same quality gates",
            enabled=enabled,
        )
    )
    return "\n".join(lines)


def render_install_app_human(report: dict[str, object], *, enabled: bool) -> str:
    icon = report.get("icon")
    icon = icon if isinstance(icon, dict) else {}
    service = report.get("summon_service")
    service = service if isinstance(service, dict) else {}
    lines = [style("torfast app", "bold", enabled=enabled)]
    ok = report.get("ok") is True
    lines.append(
        render_check_line(
            ok,
            "Torfast.app",
            str(report.get("app_path") if ok else report.get("reason", "")),
            enabled=enabled,
        )
    )
    if not ok:
        return "\n".join(lines)
    lines.append(
        render_check_line(
            icon.get("ok"),
            "app icon",
            "generated" if icon.get("ok") is True else str(icon.get("reason", "")),
            enabled=enabled,
        )
    )
    branded = report.get("branded_browser")
    if isinstance(branded, dict) and branded.get("skipped") is not True:
        lines.append(
            render_check_line(
                branded.get("ok"),
                "branded browser",
                (
                    str(branded.get("target_app"))
                    if branded.get("ok") is True
                    else str(branded.get("reason", ""))
                ),
                enabled=enabled,
            )
        )
    if service.get("skipped") is not True:
        lines.append(
            render_check_line(
                service.get("ok"),
                "summon quick action",
                str(service.get("workflow_path") or service.get("reason", "")),
                enabled=enabled,
            )
        )
    step = style("▸", "magenta", "bold", enabled=enabled)
    lines.append(
        f"  {step} open it from Spotlight (⌘Space → \"torfast\") or pin it to the Dock"
    )
    hint = report.get("shortcut_binding_hint")
    if isinstance(hint, str):
        lines.append(f"  {step} bind a summon key: {hint}")
    return "\n".join(lines)


def render_status_human(report: dict[str, object], *, enabled: bool) -> str:
    managed = report.get("managed_tor")
    managed = managed if isinstance(managed, dict) else {}
    paths = report.get("paths")
    paths = paths if isinstance(paths, dict) else {}
    running = managed.get("running") is True
    state_lines = []
    if running:
        state = style("warm", "green", "bold", enabled=enabled)
    elif managed.get("stale") is True:
        state = style("stale", "yellow", enabled=enabled)
    else:
        state = style("off", "dim", enabled=enabled)
    rows = [
        ("managed tor", f"{presence_symbol(running, enabled=enabled)} {state}"),
    ]
    profile_name = report.get("profile")
    if isinstance(profile_name, str):
        symbol = style(
            PROFILE_SYMBOLS.get(profile_name, ""),
            *PROFILE_SYMBOL_COLORS.get(profile_name, ()),
            enabled=enabled,
        )
        rows.append(("profile", f"{symbol} {profile_name}".strip()))
    pid = managed.get("pid")
    if isinstance(pid, int):
        rows.append(("pid", str(pid)))
    port = managed.get("port")
    if isinstance(port, int):
        rows.append(("socks port", str(port)))
    launch = report.get("last_launch")
    if isinstance(launch, dict):
        url = launch.get("url")
        rows.append(("last launch", str(url) if isinstance(url, str) else "recorded"))
    else:
        rows.append(("last launch", style("none", "dim", enabled=enabled)))
    state_root = paths.get("state_root")
    if isinstance(state_root, str):
        rows.append(("state root", state_root))
    panel = render_panel("torfast status", rows, enabled=enabled)
    state_lines.append(panel)
    return "\n".join(state_lines)


def render_doctor_human(report: dict[str, object], *, enabled: bool) -> str:
    browser = report.get("browser")
    browser = browser if isinstance(browser, dict) else {}
    tor = report.get("tor")
    tor = tor if isinstance(tor, dict) else {}
    pref_check = browser.get("default_pref_check")
    pref_check = pref_check if isinstance(pref_check, dict) else {}
    tor_version = tor.get("version")
    tor_version = tor_version if isinstance(tor_version, dict) else {}
    managed = report.get("managed_state")
    managed = managed if isinstance(managed, dict) else {}
    managed_tor = managed.get("managed_tor")
    managed_tor = managed_tor if isinstance(managed_tor, dict) else {}
    dir_seed = report.get("dir_cache_seed")
    dir_seed = dir_seed if isinstance(dir_seed, dict) else {}
    startup_seed = report.get("browser_startup_seed")
    startup_seed = startup_seed if isinstance(startup_seed, dict) else {}

    version_output = tor_version.get("output")
    version_detail = ""
    if isinstance(version_output, str) and version_output:
        version_detail = version_output.splitlines()[0]

    def presence_line(on: bool, label: str, detail: str) -> str:
        return (
            f"  {presence_symbol(on, enabled=enabled)} {label}  "
            + style(detail, "dim", enabled=enabled)
        )

    lines = [
        style("torfast doctor", "bold", enabled=enabled),
        render_check_line(
            browser.get("found"),
            "Tor Browser binary",
            str(browser.get("path") or "not found"),
            enabled=enabled,
        ),
        render_check_line(
            tor.get("found"),
            "C Tor binary",
            version_detail or str(tor.get("path") or "not found"),
            enabled=enabled,
        ),
        render_check_line(
            pref_check.get("ok"),
            "browser privacy defaults",
            "match Tor Browser rules" if pref_check.get("ok") is True else "",
            enabled=enabled,
        ),
        presence_line(
            managed_tor.get("running") is True,
            "managed tor",
            "warm" if managed_tor.get("running") is True else "not running",
        ),
        presence_line(
            dir_seed.get("present") is True,
            "dir-cache seed",
            "present" if dir_seed.get("present") is True else "absent",
        ),
        presence_line(
            startup_seed.get("exists") is True,
            "browser startup seed",
            "present" if startup_seed.get("exists") is True else "absent",
        ),
        render_check_line(
            report.get("ok"),
            "overall",
            "" if report.get("ok") is True else "see torfast doctor --json",
            enabled=enabled,
        ),
    ]
    return "\n".join(lines)


def render_wait_ready_human(report: dict[str, object], *, enabled: bool) -> str:
    gate = report.get("gate") or report.get("requested_gate")
    detail_parts = []
    if isinstance(gate, str):
        detail_parts.append(f"gate {gate}")
    waited = report.get("waited_seconds") or report.get("elapsed_seconds")
    if isinstance(waited, (int, float)):
        detail_parts.append(f"in {format_seconds(waited)}")
    return render_check_line(
        report.get("ok"),
        "managed tor ready" if report.get("ok") is True else "wait-ready failed",
        " ".join(detail_parts),
        enabled=enabled,
    )


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


class VersionBannerAction(argparse.Action):
    """Print the banner verbatim; argparse's version action re-wraps lines."""

    def __init__(self, option_strings, dest, **kwargs):
        kwargs.setdefault("nargs", 0)
        kwargs.setdefault("help", "show the torfast version and exit")
        super().__init__(option_strings, dest, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        print(version_banner(enabled=color_enabled()))
        parser.exit(0)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="torfast")
    parser.add_argument("--version", action=VersionBannerAction)
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

    install_app_parser = subparsers.add_parser(
        "install-app",
        help=(
            "generate Torfast.app (Dock/Spotlight launcher for the themed "
            "browser over warm Tor) plus an 'Open Torfast' Quick Action you "
            "can bind a global keyboard shortcut to"
        ),
    )
    add_install_app_args(install_app_parser)

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

    wait_ready = subparsers.add_parser(
        "wait-ready",
        help=(
            "wait for the managed warm Tor service to reach a stronger ready "
            "gate without launching the browser"
        ),
    )
    add_wait_ready_args(wait_ready)

    doctor = subparsers.add_parser(
        "doctor",
        help="check binary discovery, browser default prefs, and managed service state",
    )
    add_doctor_args(doctor)

    profile = subparsers.add_parser(
        "profile",
        help=(
            "show or set the speed profile (turbo/balanced/paranoid); "
            "profiles trade local warmth and caching for speed and never "
            "change circuits, fingerprint, or quality gates"
        ),
    )
    profile.add_argument(
        "name",
        nargs="?",
        choices=PROFILE_ORDER,
        help="profile to activate; omit to show the current profiles",
    )
    add_output_args(profile)

    return parser


def add_state_root_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--state-root", default=str(DEFAULT_STATE_ROOT))
    add_output_args(parser)


def add_output_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--json",
        action="store_true",
        help=(
            "always print machine JSON output; this is also the default "
            "whenever stdout is not a terminal"
        ),
    )


def add_wait_ready_args(parser: argparse.ArgumentParser) -> None:
    add_state_root_arg(parser)
    parser.add_argument(
        "--gate",
        default=DEFAULT_BROWSER_LAUNCH_GATE,
        choices=WAIT_READY_GATE_CHOICES,
        help=(
            "target managed-service gate; auto resolves to tor_boot_95 for the "
            "normal warmed browsing path"
        ),
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_WAIT_READY_TIMEOUT,
        help="seconds to wait for the managed service to reach the target gate",
    )


def add_runtime_args(
    parser: argparse.ArgumentParser,
    *,
    default_state_root: str,
) -> None:
    add_binary_args(parser)
    add_output_args(parser)
    parser.add_argument(
        "--profile",
        choices=PROFILE_ORDER,
        default=None,
        help=(
            "speed profile for this run only; overrides the saved "
            "`torfast profile` choice"
        ),
    )
    parser.add_argument(
        "--stock-ui",
        action="store_true",
        help=(
            "keep the stock Tor Browser chrome instead of the torfast zen "
            "UI theme (chrome-only CSS websites cannot read)"
        ),
    )
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
        "--gate-diagnostics",
        action="store_true",
        help=(
            "default-off proof mode: record reused-service gate-wait diagnostics "
            "for managed repeated-open runs"
        ),
    )
    parser.add_argument(
        "--warm-browser-prestart",
        action="store_true",
        help=(
            "lab-only: after `warm`, start a fresh background browser on "
            "about:blank so the next reused `open` can navigate it instead of "
            "restarting the browser from scratch"
        ),
    )
    parser.add_argument(
        "--managed-open-adaptive-general-circuit-wait-timeout",
        type=float,
        default=DEFAULT_MANAGED_OPEN_ADAPTIVE_GENERAL_CIRCUIT_WAIT_TIMEOUT,
        help=(
            "during a reused managed open, wait up to this many seconds for "
            "a built 3-hop general circuit when the reused service is still "
            "below the normal reused network gate; when managed-open browser "
            "overlap is active, only the hidden browser-startup window is "
            "spent before proceeding; 0 disables the wait"
        ),
    )
    parser.add_argument(
        "--browser-launch-gate",
        choices=("auto", "socks_ready", "tor_boot_90", "tor_boot_95", "tor_boot_100"),
        default=DEFAULT_BROWSER_LAUNCH_GATE,
        help=(
            "browser launch gate; default auto keeps cold network starts on "
            "tor_boot_95, while managed warm-only prestarts still return at "
            "socks_ready"
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
    parser.set_defaults(no_managed_open_browser_overlap=False)
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
    )
    parser.set_defaults(no_managed_open_settle=True)
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


def build_branded_browser_copy(explicit_browser_bin: str | None) -> dict[str, object]:
    from .browser_brand import (
        BRANDED_BUNDLE_DIRNAME,
        create_branded_browser,
        source_app_root_for_bin,
    )

    browser = discover_browser_bin(explicit_browser_bin)
    if not browser["found"]:
        return {
            "ok": False,
            "skipped": True,
            "reason": "no Tor Browser found to brand; app will use default discovery",
        }
    source_app = source_app_root_for_bin(Path(str(browser["path"])))
    if source_app is None:
        return {
            "ok": False,
            "skipped": True,
            "reason": f"browser binary is not inside an .app bundle: {browser['path']}",
        }
    return create_branded_browser(
        source_app,
        DEFAULT_BROWSER_INSTALL_ROOT / BRANDED_BUNDLE_DIRNAME,
    )


def add_install_app_args(parser: argparse.ArgumentParser) -> None:
    add_output_args(parser)
    add_binary_args(parser)
    parser.add_argument(
        "--no-branded-browser",
        action="store_true",
        help=(
            "skip creating the Torfast-branded browser copy (Dock icon and "
            "app name); the app then opens the browser under its stock "
            "Tor Browser identity"
        ),
    )
    parser.add_argument(
        "--dest",
        default=None,
        help=(
            "folder to install Torfast.app into; default tries /Applications "
            "then ~/Applications"
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="replace an existing Torfast.app",
    )
    parser.add_argument(
        "--no-summon-service",
        action="store_true",
        help="skip installing the 'Open Torfast' Quick Action",
    )
    parser.add_argument(
        "--no-icon",
        action="store_true",
        help="skip generating the app icon",
    )


def add_install_browser_args(parser: argparse.ArgumentParser) -> None:
    add_output_args(parser)
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
    if getattr(args, "gate_diagnostics", False):
        command.append("--gate-diagnostics")
    if not getattr(args, "no_managed_open_settle", True):
        command.append("--managed-open-settle")
    if not getattr(args, "no_managed_open_browser_overlap", False):
        command.append("--managed-open-browser-overlap")
    if getattr(args, "warm_browser_prestart", False):
        command.append("--warm-browser-prestart")
    # Forward the value even when it is 0 so an explicit opt-out reaches the
    # launcher instead of silently falling back to the launcher default.
    command.extend(
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
    browser_launch_gate = getattr(
        args,
        "browser_launch_gate",
        DEFAULT_BROWSER_LAUNCH_GATE,
    )
    if args.command == "prime" and browser_launch_gate == DEFAULT_BROWSER_LAUNCH_GATE:
        browser_launch_gate = "tor_boot_100"
    if browser_launch_gate != DEFAULT_BROWSER_LAUNCH_GATE:
        command.extend(["--browser-launch-gate", browser_launch_gate])
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
    if getattr(args, "stock_ui", False):
        command.append("--stock-ui")
    resolved_profile = getattr(args, "resolved_profile", None)
    if resolved_profile:
        command.extend(["--profile-label", resolved_profile])

    managed_reuse_on_open = getattr(args, "managed_reuse_on_open", True)
    keep_tor_warm_after_launch = getattr(args, "keep_tor_warm_after_launch", False)
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
        if managed_reuse_on_open:
            command.extend(["--leave-tor-running", "--reuse-tor-if-running"])
    elif args.command == "launch":
        if keep_tor_warm_after_launch:
            command.extend(["--leave-tor-running", "--reuse-tor-if-running"])
    elif args.command == "plan":
        if keep_tor_warm_after_launch:
            command.extend(["--leave-tor-running", "--reuse-tor-if-running"])
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
        "profile": active_profile_name(),
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
