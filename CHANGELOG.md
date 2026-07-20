# Changelog

## Unreleased

- added: speed profiles — `torfast profile turbo|balanced|paranoid` saves a
  default, `--profile` overrides per run. Profiles only trade what stays
  resident or cached locally (warm managed Tor, directory seeds, runtime
  helper) for speed; circuits, fingerprint, and quality gates are identical
  at every level. `turbo` makes `launch` behave like `open` on the stable
  managed root; `paranoid` makes every open a cold one-shot on a fresh state
  root with no seeds and no runtime helper, and rejects `warm`
- added: `torfast install-app` — generates Torfast.app (own generated icon,
  Dock/Spotlight/Launchpad presence; clicking it shows an instant opening
  notification and brings the themed browser up over the warm managed Tor
  with no terminal, logging to `~/Library/Logs/torfast-app.log`; clicking
  again focuses the open browser instead of relaunching, and clicking
  during warm-up is a no-op) plus an "Open Torfast" macOS Quick Action
  that routes through the app so a global keyboard shortcut can summon the
  browser from anywhere; the app launches a Torfast-branded clone of the
  verified Tor Browser bundle (APFS clonefile; Dock icon, app name, and
  bundle identifier only — binaries and every content-visible byte stay
  identical, the real Tor Browser install is never modified, and CLI runs
  and benchmarks keep the stock-identity copy), with `--no-branded-browser`
  to opt out
- added: the torfast zen UI — a chrome-only `userChrome.css` theme written
  into each generated browser profile (calm dark surface, pill tabs,
  floating urlbar with a focus glow). Geometry-safe by rule and by test:
  no property that could move the content viewport, so websites see the
  exact stock fingerprint surface; `--stock-ui` opts out per run, and the
  launch plan records `ui_theme` plus the applied file paths

- fixed: Tor Browser first-run `about:tor` could replace the requested page
  after the eager overlap navigation had already committed; a rate-limited
  target-navigation keeper in the launcher now guarantees the requested page
  is delivered
- changed: `--managed-open-adaptive-general-circuit-wait-timeout` now
  defaults to `0.126` (the benchmark-proven faster profile); pass `0` to
  restore the old behavior
- added: runtime quality proof now gates on canvas extraction blocking, a
  live `resistFingerprinting` timezone spoof, snapshot capture on the
  requested page, and stable-fingerprint equality against a stock-launched
  reference of the same build
- added: human terminal output for the CLI — `torfast status` renders a
  panel, `torfast doctor` a checklist, and action commands show a spinner
  plus a launch receipt with the proven timings; human mode only engages on
  a TTY, respects `NO_COLOR`, and `--json` (or piping) keeps the machine
  output byte-identical, so scripts and benchmarks are unaffected
- added: `torfast --version` banner, `tools/render_verifier_scorecard.py`
  (markdown scorecard for promoted-quality-check artifacts, latest copy in
  `docs/latest-scorecard.md`), and a generated animated terminal demo
  (`tools/render_terminal_demo.py` → `docs/assets/torfast-demo.svg`) embedded
  in the README with numbers from the latest green verifier artifact
- added: `tools/check_c_tor_circuits.py` now proves Conflux is live at
  runtime (control-port `ConfluxEnabled` resolves to `auto`/`1` and at least
  one full linked set — `2` BUILT `CONFLUX_LINKED` legs — is present, with
  the legs held to the same path rules); the promoted-profile verifier
  inherits this gate, so the proven `~2-3x` bulk-throughput Conflux default
  can no longer silently regress

## v0.1.0 - 2026-06-26

Initial public source release.

- `torfast` launcher and CLI for verified Tor Browser workflows
- verified Tor Browser install, warm/open, and launch helpers
- benchmark and analysis tools for Tor Browser, C Tor, and Arti
- saved proof for the first quality-preserving speed finding: C Tor Conflux,
  with standard 3-hop circuits kept intact, showed about `2-3x` bulk-download
  throughput versus disabling it
- privacy and compatibility quality gates
- contributor guide, security policy, code ownership, and CI smoke checks
