#!/usr/bin/env python3
"""Render a human-readable scorecard for a promoted-quality-check artifact.

The verifier's `summary.json` is complete but dense; this tool renders the
same facts as a short markdown scorecard so reviewers can see the verdict,
the gates, and the speed deltas without reading raw JSON. It never computes
new judgments: every row is read from (or recomputed with the same functions
as) the verifier payload.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_torfast_promoted_quality_check import (
    combined_wall_regression_guard_seconds,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RESULTS_ROOT = REPO_ROOT / "results"
ARTIFACT_GLOB = "torfast-promoted-quality-check-*"
PASS_MARK = "✅"
FAIL_MARK = "❌"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--artifact-dir",
        default=None,
        help=(
            "verifier artifact directory; defaults to the latest "
            f"results/{ARTIFACT_GLOB}"
        ),
    )
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="print the scorecard without writing scorecard.md",
    )
    args = parser.parse_args(argv)

    artifact_dir = resolve_artifact_dir(args.artifact_dir)
    if artifact_dir is None:
        print("no verifier artifact found", file=sys.stderr)
        return 2
    summary_path = artifact_dir / "summary.json"
    if not summary_path.exists():
        print(f"missing summary.json in {artifact_dir}", file=sys.stderr)
        return 2
    summary = json.loads(summary_path.read_text())
    scorecard = render_scorecard(summary, artifact_name=artifact_dir.name)
    if not args.no_write:
        (artifact_dir / "scorecard.md").write_text(scorecard + "\n")
        print(f"wrote {artifact_dir / 'scorecard.md'}", file=sys.stderr)
    print(scorecard)
    return 0


def resolve_artifact_dir(explicit: str | None) -> Path | None:
    if explicit:
        return Path(explicit).resolve()
    candidates = sorted(DEFAULT_RESULTS_ROOT.glob(ARTIFACT_GLOB))
    return candidates[-1] if candidates else None


def mark(ok: object) -> str:
    return PASS_MARK if ok is True else FAIL_MARK


def short_target(target: str) -> str:
    return target.removeprefix("https://").removeprefix("http://").rstrip("/")


def format_delta(value: object) -> str:
    if not isinstance(value, (int, float)):
        return "-"
    return f"{value:+.3f}s"


def quality_counts(summary: dict[str, object]) -> tuple[int, int]:
    rows = summary.get("results")
    rows = rows if isinstance(rows, list) else []
    ok_rows = sum(
        1
        for row in rows
        if isinstance(row, dict)
        and isinstance(row.get("quality"), dict)
        and row["quality"].get("ok") is True
    )
    return ok_rows, len(rows)


def pairwise_counts(summary: dict[str, object]) -> tuple[int, int]:
    rows = summary.get("pairwise_consistency")
    rows = rows if isinstance(rows, list) else []
    ok_rows = sum(
        1 for row in rows if isinstance(row, dict) and row.get("ok") is True
    )
    return ok_rows, len(rows)


def circuit_rows(
    summary: dict[str, object],
) -> list[tuple[str, dict[str, object]]]:
    checks = summary.get("c_tor_circuit_checks")
    checks = checks if isinstance(checks, dict) else {}
    return [
        (target, check)
        for target, check in sorted(checks.items())
        if isinstance(check, dict) and check.get("skipped") is not True
    ]


def baseline_guard(summary: dict[str, object], target: str) -> float:
    profiles = summary.get("profiles")
    profiles = profiles if isinstance(profiles, dict) else {}
    profile_names = summary.get("profile_names")
    baseline_name = (
        profile_names[0]
        if isinstance(profile_names, list) and profile_names
        else None
    )
    target_profiles = profiles.get(target)
    baseline_summary = (
        target_profiles.get(baseline_name)
        if isinstance(target_profiles, dict) and isinstance(baseline_name, str)
        else None
    )
    return combined_wall_regression_guard_seconds(
        baseline_summary if isinstance(baseline_summary, dict) else None
    )


def render_scorecard(
    summary: dict[str, object],
    *,
    artifact_name: str,
) -> str:
    ok = summary.get("ok") is True
    quality_ok, quality_total = quality_counts(summary)
    pairwise_ok, pairwise_total = pairwise_counts(summary)
    circuits = circuit_rows(summary)
    deltas = summary.get("delta_vs_baseline")
    deltas = deltas if isinstance(deltas, dict) else {}
    cycles = summary.get("cycles")

    lines = [
        f"# torfast verifier scorecard — `{artifact_name}`",
        "",
        f"**Verdict: {'PASS' if ok else 'FAIL'}** {mark(ok)}"
        + (f" ({cycles} cycles)" if isinstance(cycles, int) else ""),
        "",
        "| gate | result |",
        "|---|---|",
        (
            f"| runtime quality runs | {mark(quality_ok == quality_total and quality_total > 0)} "
            f"{quality_ok}/{quality_total} |"
        ),
        (
            f"| pairwise fingerprint consistency | "
            f"{mark(pairwise_ok == pairwise_total and pairwise_total > 0)} "
            f"{pairwise_ok}/{pairwise_total} |"
        ),
    ]
    for target, check in circuits:
        conflux = check.get("summary")
        conflux = conflux if isinstance(conflux, dict) else {}
        conflux = conflux.get("conflux")
        conflux = conflux if isinstance(conflux, dict) else {}
        legs = conflux.get("linked_built_count")
        conflux_note = (
            f", conflux live ({legs} linked legs)"
            if isinstance(legs, int)
            else ""
        )
        lines.append(
            f"| circuit rules — {short_target(target)} | "
            f"{mark(check.get('ok'))} 3-hop/guard/family/subnet{conflux_note} |"
        )

    lines.extend(
        [
            "",
            "## Speed vs baseline (medians)",
            "",
            "| target | open-browser elapsed Δ | combined wall Δ | guard |",
            "|---|---:|---:|---:|",
        ]
    )
    for target, delta in sorted(deltas.items()):
        if not isinstance(delta, dict):
            continue
        open_delta = delta.get("open_browser_elapsed_seconds")
        combined_delta = delta.get("combined_wall_seconds")
        guard = baseline_guard(summary, target)
        open_ok = isinstance(open_delta, (int, float)) and open_delta < 0
        combined_ok = (
            isinstance(combined_delta, (int, float)) and combined_delta <= guard
        )
        lines.append(
            f"| {short_target(target)} | {mark(open_ok)} {format_delta(open_delta)} | "
            f"{mark(combined_ok)} {format_delta(combined_delta)} | "
            f"{guard:.3f}s |"
        )

    lines.extend(
        [
            "",
            "Negative deltas are faster than baseline. The combined-wall guard is "
            "`max(1.0s, 0.75 x baseline same-config stdev)` because page delivery "
            "rides a random Tor circuit (see `docs/quality-bar.md`).",
        ]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
