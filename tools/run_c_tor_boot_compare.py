#!/usr/bin/env python3
"""Compare C Tor cold bootstrap with documented client bootstrap knobs."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import queue
import shutil
import statistics
import subprocess
import sys
import threading
import time

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from run_browser_compare import C_TOR_SOCKS_FLAGS, read_torrc_quality, wait_for_line


@dataclass(frozen=True)
class CTorBootProfile:
    name: str
    extra_torrc_lines: tuple[str, ...] = ()


PROFILES = (
    CTorBootProfile("stock"),
    CTorBootProfile(
        "authdelay0",
        ("ClientBootstrapConsensusAuthorityDownloadInitialDelay 0",),
    ),
    CTorBootProfile(
        "maxtries5",
        ("ClientBootstrapConsensusMaxInProgressTries 5",),
    ),
    CTorBootProfile(
        "authdelay0_maxtries5",
        (
            "ClientBootstrapConsensusAuthorityDownloadInitialDelay 0",
            "ClientBootstrapConsensusMaxInProgressTries 5",
        ),
    ),
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tor-bin", default="upstream/tor/src/app/tor")
    parser.add_argument("--runs", type=int, default=2)
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--port-base", type=int, default=19800)
    parser.add_argument("--output-root", default="results")
    parser.add_argument(
        "--profiles",
        default=",".join(profile.name for profile in PROFILES),
        help="comma-separated profile names to run",
    )
    args = parser.parse_args()

    if args.runs < 1:
        print("--runs must be at least 1", file=sys.stderr)
        return 2

    tor_bin = Path(args.tor_bin).resolve()
    if not tor_bin.exists():
        print(f"tor binary not found: {tor_bin}", file=sys.stderr)
        return 2
    selected_profiles = select_profiles(args.profiles)
    if not selected_profiles:
        print("no valid profiles selected", file=sys.stderr)
        return 2

    run_id = time.strftime("%Y%m%dT%H%M%S")
    output_dir = Path(args.output_root).resolve() / f"c-tor-boot-compare-{run_id}"
    output_dir.mkdir(parents=True, exist_ok=True)

    payload: dict[str, object] = {
        "run_id": run_id,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "tor_bin": str(tor_bin),
        "runs": args.runs,
        "timeout_seconds": args.timeout,
        "profiles": {},
    }

    for profile in selected_profiles:
        payload["profiles"][profile.name] = {
            "extra_torrc_lines": list(profile.extra_torrc_lines),
            "runs": [],
        }

    for run_index in range(1, args.runs + 1):
        ordered_profiles = ordered_profiles_for_run(selected_profiles, run_index)
        for profile_index, profile in enumerate(ordered_profiles):
            port = args.port_base + (run_index - 1) * len(selected_profiles) + profile_index
            state_root = output_dir / profile.name / f"run-{run_index}"
            run_payload = run_profile(
                profile=profile,
                run_index=run_index,
                profile_order_index=profile_index,
                tor_bin=tor_bin,
                state_root=state_root,
                port=port,
                timeout=args.timeout,
            )
            profile_payload = payload["profiles"][profile.name]
            assert isinstance(profile_payload, dict)
            runs = profile_payload["runs"]
            assert isinstance(runs, list)
            runs.append(run_payload)

    profiles = payload["profiles"]
    assert isinstance(profiles, dict)
    for profile_payload in profiles.values():
        if isinstance(profile_payload, dict):
            profile_payload["summary"] = summarize_runs(profile_payload["runs"])
    payload["comparison"] = compare_profiles(profiles)

    output_path = output_dir / "c-tor-boot-compare.json"
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"wrote {output_path}")
    print(json.dumps(payload["comparison"], indent=2, sort_keys=True))
    return 0


def render_torrc(profile: CTorBootProfile, *, port: int, data_dir: Path) -> str:
    lines = [
        f"SocksPort 127.0.0.1:{port} {' '.join(C_TOR_SOCKS_FLAGS)}",
        f"DataDirectory {data_dir.resolve()}",
        "ClientOnly 1",
        "AvoidDiskWrites 1",
        "SafeLogging 1",
        "Log notice stdout",
        "ConfluxEnabled auto",
        *profile.extra_torrc_lines,
    ]
    return "\n".join(lines) + "\n"


def select_profiles(spec: str) -> list[CTorBootProfile]:
    wanted = [item.strip() for item in spec.split(",") if item.strip()]
    by_name = {profile.name: profile for profile in PROFILES}
    return [by_name[name] for name in wanted if name in by_name]


def ordered_profiles_for_run(
    profiles: list[CTorBootProfile],
    run_index: int,
) -> list[CTorBootProfile]:
    if not profiles:
        return []
    shift = (run_index - 1) % len(profiles)
    return profiles[shift:] + profiles[:shift]


def run_profile(
    *,
    profile: CTorBootProfile,
    run_index: int,
    profile_order_index: int,
    tor_bin: Path,
    state_root: Path,
    port: int,
    timeout: float,
) -> dict[str, object]:
    if state_root.exists():
        shutil.rmtree(state_root)
    state_root.mkdir(parents=True, exist_ok=True)
    data_dir = state_root / "tor-data"
    data_dir.mkdir(parents=True, exist_ok=True)
    torrc = state_root / "torrc"
    torrc.write_text(render_torrc(profile, port=port, data_dir=data_dir))

    proc = subprocess.Popen(
        [str(tor_bin), "-f", str(torrc)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    lines: queue.Queue[str] = queue.Queue()
    reader = threading.Thread(target=read_lines, args=(proc, lines), daemon=True)
    reader.start()
    try:
        boot = wait_for_line(
            proc,
            lines,
            timeout=timeout,
            ready_text="Bootstrapped 100%",
            process_name="tor",
        )
    finally:
        stop_process(proc)

    return {
        "run_index": run_index,
        "profile_order_index": profile_order_index,
        "port": port,
        "state_root": str(state_root),
        "torrc_quality": read_torrc_quality(torrc),
        "extra_torrc_lines": list(profile.extra_torrc_lines),
        "boot": boot,
    }


def read_lines(proc: subprocess.Popen[str], lines: queue.Queue[str]) -> None:
    assert proc.stdout is not None
    for line in proc.stdout:
        lines.put(line.rstrip())


def stop_process(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=10.0)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=10.0)


def summarize_runs(runs: list[dict[str, object]]) -> dict[str, object]:
    boot_seconds = [
        float(boot["seconds"])
        for run in runs
        if isinstance(run.get("boot"), dict)
        for boot in [run["boot"]]
        if boot.get("ok") is True and isinstance(boot.get("seconds"), (int, float))
    ]
    ok_runs = sum(
        1
        for run in runs
        if isinstance(run.get("boot"), dict) and run["boot"].get("ok") is True
    )
    summary: dict[str, object] = {
        "runs": len(runs),
        "ok_runs": ok_runs,
        "ok": bool(runs) and ok_runs == len(runs),
        "median_boot_seconds": round(float(statistics.median(boot_seconds)), 3)
        if boot_seconds
        else None,
        "min_boot_seconds": round(min(boot_seconds), 3) if boot_seconds else None,
        "max_boot_seconds": round(max(boot_seconds), 3) if boot_seconds else None,
    }
    return summary


def compare_profiles(profiles: dict[str, object]) -> dict[str, object]:
    stock = profile_median_seconds(profiles, "stock")
    authdelay0 = profile_median_seconds(profiles, "authdelay0")
    maxtries5 = profile_median_seconds(profiles, "maxtries5")
    combo = profile_median_seconds(profiles, "authdelay0_maxtries5")
    comparison: dict[str, object] = {
        "stock_median_boot_seconds": stock,
        "authdelay0_median_boot_seconds": authdelay0,
        "maxtries5_median_boot_seconds": maxtries5,
        "authdelay0_maxtries5_median_boot_seconds": combo,
    }
    if stock is not None:
        if authdelay0 is not None:
            comparison["authdelay0_minus_stock_seconds"] = round(authdelay0 - stock, 3)
        if maxtries5 is not None:
            comparison["maxtries5_minus_stock_seconds"] = round(maxtries5 - stock, 3)
        if combo is not None:
            comparison["authdelay0_maxtries5_minus_stock_seconds"] = round(
                combo - stock, 3
            )
    medians = {
        name: value
        for name, value in (
            ("stock", stock),
            ("authdelay0", authdelay0),
            ("maxtries5", maxtries5),
            ("authdelay0_maxtries5", combo),
        )
        if value is not None
    }
    if medians:
        comparison["fastest_profile"] = min(medians, key=medians.get)
        comparison["fastest_profile_median_boot_seconds"] = medians[
            comparison["fastest_profile"]
        ]
    return comparison


def profile_median_seconds(
    profiles: dict[str, object],
    profile_name: str,
) -> float | None:
    profile_payload = profiles.get(profile_name)
    if not isinstance(profile_payload, dict):
        return None
    summary = profile_payload.get("summary")
    if not isinstance(summary, dict):
        return None
    value = summary.get("median_boot_seconds")
    return float(value) if isinstance(value, (int, float)) else None


if __name__ == "__main__":
    raise SystemExit(main())
