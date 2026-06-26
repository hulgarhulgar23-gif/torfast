#!/usr/bin/env python3
"""Summarize saved benchmark JSON files."""

from __future__ import annotations

import json
from pathlib import Path


def main() -> int:
    results_dir = Path("results")
    rows = collect_rows(results_dir)
    quality_rows = collect_quality_rows(results_dir)
    if not rows and not quality_rows:
        print("No result JSON found.")
        return 1

    if rows:
        print("# Latest Benchmark Results")
        print()
        print(
            "| source | profile | target | cache | warmup s | boot s | post wait s | "
            "median total/elapsed ms | launch+elapsed ms | median load ms | "
            "launch+load ms | median first byte ms | ok |"
        )
        print("|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|")
        for row in rows:
            print(
                "| {source} | {profile} | {target} | {cache} | {warmup} | {boot} | "
                "{post_wait} | {total} | {launch_total} | {load} | {launch_load} | "
                "{first_byte} | {ok} |".format(
                    **row
                )
            )

    if quality_rows:
        print()
        print("## Latest Quality Checks")
        print()
        print("| source | check | evidence | runtime path proof | full quality proof | ok |")
        print("|---|---|---|---|---|---|")
        for row in quality_rows:
            print(
                "| {source} | {check} | {evidence} | {runtime_path_proof} | {full_quality_proof} | {ok} |".format(
                    **row
                )
            )
    return 0


def collect_rows(results_dir: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    if not results_dir.exists():
        return rows

    rows.extend(rows_from_latest_baseline(results_dir))
    rows.extend(rows_from_latest_arti(results_dir))
    rows.extend(rows_from_latest_tor_matrix(results_dir))
    rows.extend(rows_from_latest_proxy_compare(results_dir))
    rows.extend(rows_from_latest_browser_compare(results_dir))
    rows.extend(rows_from_latest_torfast_browser_compare(results_dir))
    rows.extend(rows_from_latest_c_tor_boot_compare(results_dir))
    rows.extend(rows_from_latest_torfast_runtime_compare(results_dir))
    rows.extend(rows_from_latest_cache_diagnostic(results_dir))
    return rows


def collect_quality_rows(results_dir: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    if not results_dir.exists():
        return rows

    rows.extend(rows_from_latest_c_tor_circuits(results_dir))
    rows.extend(rows_from_latest_arti_quality_config(results_dir))
    rows.extend(rows_from_latest_arti_rpc_path(results_dir))
    return rows


def rows_from_latest_baseline(results_dir: Path) -> list[dict[str, str]]:
    paths = sorted(results_dir.glob("baseline-*.json"))
    if not paths:
        return []
    payload = load_json(paths[-1])
    rows: list[dict[str, str]] = []
    for name, data in sorted(payload["results"].items()):
        profile, target = name.split(":", 1)
        rows.append(row(paths[-1], profile, target, None, data["summary"]))
    return rows


def rows_from_latest_arti(results_dir: Path) -> list[dict[str, str]]:
    paths = sorted(results_dir.glob("arti-baseline-*/arti-baseline.json"))
    if not paths:
        return []
    payload = load_json(paths[-1])
    rows: list[dict[str, str]] = []
    boot = payload.get("boot", {}).get("seconds")
    for target, data in sorted(payload["benchmarks"].items()):
        rows.append(row(paths[-1], "arti", target, boot, data["summary"]))
    return rows


def rows_from_latest_tor_matrix(results_dir: Path) -> list[dict[str, str]]:
    paths = sorted(results_dir.glob("tor-matrix-*/matrix.json"))
    if not paths:
        return []
    payload = load_json(paths[-1])
    rows: list[dict[str, str]] = []
    for profile, data in sorted(payload["profiles"].items()):
        boot = data.get("boot", {}).get("seconds")
        for target, bench in sorted(data.get("benchmarks", {}).items()):
            rows.append(row(paths[-1], profile, target, boot, bench["summary"]))
    return rows


def rows_from_latest_proxy_compare(results_dir: Path) -> list[dict[str, str]]:
    paths = sorted(results_dir.glob("proxy-compare-*/compare.json"))
    if not paths:
        return []
    payload = load_json(paths[-1])
    rows: list[dict[str, str]] = []
    for profile, data in sorted(payload["profiles"].items()):
        boot = data.get("boot", {}).get("seconds")
        warmup = data.get("warmup_boot")
        warmup_seconds = warmup.get("seconds") if isinstance(warmup, dict) else None
        cache = str(data.get("cache_mode", payload.get("cache_mode", "")))
        for target, bench in sorted(data.get("benchmarks", {}).items()):
            rows.append(
                row(
                    paths[-1],
                    profile,
                    target,
                    boot,
                    bench["summary"],
                    cache=cache,
                    warmup=warmup_seconds,
                )
            )
    return rows


def rows_from_latest_browser_compare(results_dir: Path) -> list[dict[str, str]]:
    paths = sorted(results_dir.glob("browser-compare-*/browser-compare.json"))
    if not paths:
        return []
    payload = load_json(paths[-1])
    rows: list[dict[str, str]] = []
    for profile, data in sorted(payload["profiles"].items()):
        boot = data.get("boot", {}).get("seconds")
        warmup = data.get("warmup_boot")
        warmup_seconds = warmup.get("seconds") if isinstance(warmup, dict) else None
        cache = str(data.get("cache_mode", payload.get("cache_mode", "")))
        post_wait = data.get("post_boot_wait_seconds", payload.get("post_boot_wait_seconds"))
        for target, bench in sorted(data.get("benchmarks", {}).items()):
            rows.append(
                row(
                    paths[-1],
                    profile,
                    target,
                    boot,
                    bench["summary"],
                    cache=cache,
                    warmup=warmup_seconds,
                    post_wait=post_wait,
                )
            )
    return rows


def rows_from_latest_torfast_browser_compare(results_dir: Path) -> list[dict[str, str]]:
    paths = sorted(results_dir.glob("torfast-browser-compare-*/torfast-browser-compare.json"))
    if not paths:
        return []
    payload = load_json(paths[-1])
    profiles = payload.get("profiles", {})
    if not isinstance(profiles, dict):
        return []
    rows: list[dict[str, str]] = []
    for profile_name, profile in sorted(profiles.items()):
        if not isinstance(profile, dict):
            continue
        summary = profile.get("summary", {})
        if not isinstance(summary, dict):
            continue
        targets = summary.get("targets", {})
        if not isinstance(targets, dict):
            continue
        boot = summary.get("median_boot_seconds")
        launch_boot = summary.get("median_launch_ready_seconds")
        if not isinstance(launch_boot, (int, float)):
            launch_boot = boot
        cache = "seeded" if "seeded" in profile_name else "cold"
        for target, target_summary in sorted(targets.items()):
            if not isinstance(target_summary, dict):
                continue
            rows.append(
                row(
                    paths[-1],
                    profile_name,
                    target,
                    boot,
                    target_summary,
                    cache=cache,
                    launch_boot=launch_boot,
                )
            )
    return rows


def rows_from_latest_torfast_runtime_compare(results_dir: Path) -> list[dict[str, str]]:
    paths = sorted(results_dir.glob("torfast-runtime-compare-*/torfast-runtime-compare.json"))
    if not paths:
        return []
    payload = load_json(paths[-1])
    profiles = payload.get("profiles", {})
    if not isinstance(profiles, dict):
        return []
    rows: list[dict[str, str]] = []
    target = str(payload.get("url", "about:tor"))
    for profile_name, profile in sorted(profiles.items()):
        if not isinstance(profile, dict):
            continue
        summary = profile.get("summary")
        if not isinstance(summary, dict):
            continue
        rows.append(
            row(
                paths[-1],
                profile_name,
                target,
                summary.get("median_tor_boot_seconds"),
                summary,
                cache="runtime",
            )
        )
    return rows


def rows_from_latest_c_tor_boot_compare(results_dir: Path) -> list[dict[str, str]]:
    paths = sorted(results_dir.glob("c-tor-boot-compare-*/c-tor-boot-compare.json"))
    if not paths:
        return []
    payload = load_json(paths[-1])
    profiles = payload.get("profiles", {})
    if not isinstance(profiles, dict):
        return []
    rows: list[dict[str, str]] = []
    for profile_name, profile in sorted(profiles.items()):
        if not isinstance(profile, dict):
            continue
        summary = profile.get("summary")
        if not isinstance(summary, dict):
            continue
        rows.append(
            row(
                paths[-1],
                f"c_tor_boot_{profile_name}",
                "bootstrap",
                summary.get("median_boot_seconds"),
                summary,
                cache="cold",
            )
        )
    return rows


def rows_from_latest_cache_diagnostic(results_dir: Path) -> list[dict[str, str]]:
    paths = sorted(results_dir.glob("cache-diagnostic-*/cache-diagnostic.json"))
    if not paths:
        return []
    payload = load_json(paths[-1])
    rows: list[dict[str, str]] = []
    for profile, phases in sorted(payload["profiles"].items()):
        for phase, data in sorted(phases.items()):
            boot = data.get("boot", {}).get("seconds")
            for target, bench in sorted(data.get("benchmarks", {}).items()):
                rows.append(row(paths[-1], f"{profile}_{phase}", target, boot, bench["summary"]))
    return rows


def rows_from_latest_c_tor_circuits(results_dir: Path) -> list[dict[str, str]]:
    paths = sorted(results_dir.glob("circuit-check-*/c-tor-circuits.json"))
    if not paths:
        return []
    payload = load_json(paths[-1])
    return [
        quality_row(
            paths[-1],
            "c_tor_circuit_probe",
            f"{payload.get('checked_circuit_count', 0)} checked circuits",
            True,
            True,
            bool(payload.get("ok")),
        )
    ]


def rows_from_latest_arti_quality_config(results_dir: Path) -> list[dict[str, str]]:
    paths = sorted(results_dir.glob("arti-quality-config-*/arti-quality-config.json"))
    if not paths:
        return []
    payload = load_json(paths[-1])
    checks = payload.get("checks", [])
    return [
        quality_row(
            paths[-1],
            "arti_source_config",
            f"{len(checks)} static checks",
            bool(payload.get("runtime_circuit_path_proof")),
            False,
            bool(payload.get("ok")),
        )
    ]


def rows_from_latest_arti_rpc_path(results_dir: Path) -> list[dict[str, str]]:
    paths = sorted(results_dir.glob("arti-rpc-path-*/arti-rpc-path.json"))
    if not paths:
        return []
    payload = load_json(paths[-1])
    validation = payload.get("validation") or {}
    checked_paths = validation.get("checked_paths", 0) if isinstance(validation, dict) else 0
    full = bool(payload.get("full_runtime_quality_proof"))
    return [
        quality_row(
            paths[-1],
            "arti_rpc_path_directory" if full else "arti_rpc_path_shape",
            f"{checked_paths} checked {plural(checked_paths, 'path')}",
            bool(payload.get("runtime_path_shape_proof")),
            full,
            bool(payload.get("ok")),
        )
    ]


def row(
    source: Path,
    profile: str,
    target: str,
    boot: float | None,
    summary: dict[str, object],
    *,
    cache: str = "",
    warmup: float | None = None,
    post_wait: float | None = None,
    launch_boot: float | None = None,
) -> dict[str, str]:
    effective_launch_boot = launch_boot if launch_boot is not None else boot
    return {
        "source": str(source),
        "profile": profile,
        "target": target,
        "cache": cache,
        "warmup": fmt(warmup),
        "post_wait": fmt(post_wait),
        "boot": fmt(boot),
        "total": fmt(summary.get("median_total_ms") or summary.get("median_elapsed_ms")),
        "launch_total": fmt(
            add_boot_ms(
                effective_launch_boot,
                summary.get("median_total_ms") or summary.get("median_elapsed_ms"),
            )
        ),
        "load": fmt(summary.get("median_load_ms")),
        "launch_load": fmt(
            add_boot_ms(effective_launch_boot, summary.get("median_load_ms"))
        ),
        "first_byte": fmt(summary.get("median_first_byte_ms")),
        "ok": "yes" if summary.get("ok") else "no",
    }


def quality_row(
    source: Path,
    check: str,
    evidence: str,
    runtime_path_proof: bool,
    full_quality_proof: bool,
    ok: bool,
) -> dict[str, str]:
    return {
        "source": str(source),
        "check": check,
        "evidence": evidence,
        "runtime_path_proof": "yes" if runtime_path_proof else "no",
        "full_quality_proof": "yes" if full_quality_proof else "no",
        "ok": "yes" if ok else "no",
    }


def fmt(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def add_boot_ms(boot_seconds: object, metric_ms: object) -> float | None:
    if not isinstance(boot_seconds, (int, float)):
        return None
    if not isinstance(metric_ms, (int, float)):
        return None
    return boot_seconds * 1000 + metric_ms


def plural(count: object, singular: str) -> str:
    return singular if count == 1 else f"{singular}s"


def load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text())


if __name__ == "__main__":
    raise SystemExit(main())
