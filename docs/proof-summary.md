# Public Proof Summary

This page is the short public proof summary for `torfast`.

For the full running log, see [Latest Results](latest-results.md).

## Why this repo matters

- `torfast` is a public project to make Tor Browser faster without weakening
  privacy.
- The work touches Tor Browser, C Tor, and Arti.
- Privacy and compatibility stay as hard gates, not optional tradeoffs.

## Maintainer signal

- One maintainer handles issue triage, review, releases, docs, benchmarks, and
  quality checks.
- `main` is protected and requires the `smoke` and `Analyze (python)` checks.
- CI and CodeQL are green on `main`.
- Public issue forms, a PR template, CODEOWNERS, and a security policy are in
  place.

## Public proof highlights

- `v0.1.0` is published as a public source release.
- The release notes include a concrete benchmark result.
- The release page also includes an attached proof file:
  `proof-summary-v0.1.0.md`.
- First quality-preserving speed finding: C Tor Conflux, with standard 3-hop
  circuits kept intact, showed about `2-3x` bulk-download throughput versus
  disabling it.
- Warm/open proof under
  `results/torfast-warm-open-fresh-browser-proof-20260624T165129/` shows the
  repeated-open path keeps Tor warm for speed while clearing old browser state
  before launch.
- CLI default-path proof under
  `results/torfast-cli-default-proof-20260624T125839/` shows ordinary fresh
  launch uses the shared seeds on a fresh root and keeps `IsolateSOCKSAuth`
  intact.
- Seed apply proof under
  `results/torfast-seed-apply-proof-20260624T130633/` shows the local seed-copy
  step dropped from `0.05298s` median to `0.03486s` median, about `34%`
  faster, without changing Tor path rules or browser privacy prefs.

## Where to look next

- [README](../README.md) for project status and repo signals.
- [Latest Results](latest-results.md) for the full proof log.
- [Security Policy](../SECURITY.md) for reporting and repo protections.
