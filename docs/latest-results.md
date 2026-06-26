# Latest Results

Measured through 2026-06-26 local time.

## 2026-06-24 status

Warm/open browser-state reset proof:

- `tools/launch_torfast_browser.py` now clears the managed
  `browser-home/` and `browser-profile/` directories before any browser launch
  on the warm/open path, while still reusing the managed warm Tor service.
- Durable proof under
  `results/torfast-warm-open-fresh-browser-proof-20260624T165129/` shows the
  exact fast repeated-open path now drops stale browser state instead of
  silently reusing it. In `summary.json`, a forced stale marker file plus the
  prior browser profile contents were removed before `torfast open`, with
  `browser_runtime_reset.removed_files = 11` and
  `browser_runtime_reset.removed_dirs = 7`.
- The same proof keeps the speed win: `open-launch.json` shows
  `tor_boot.reused_service = true`, the one-shot headless open finished in
  `1.336s` wall time with a `1.199s` browser run, and the stale marker files
  were gone after launch.
- This closes an important quality gap in the fastest repeated-open workflow.
  The warm/open path now keeps Tor warm for speed, but no longer keeps old
  browser cookies, storage, or profile files between browser runs.

Warm/open real runtime-state proof:

- Follow-up proof under
  `results/torfast-extension-state-reset-check-20260624T190420/report.json`
  used the browser's own persisted extension/runtime storage as the check
  target. Tor Browser private mode already clears ordinary first-party
  cookie/localStorage across full browser restarts, so that was the wrong proof
  target for this path.
- In `first-open`, the fresh managed profile created a real extension storage
  directory under
  `storage/default/moz-extension+++b1a02fe1-5a68-4eda-885c-e33a2c36cf37^userContextId=4294967295/`
  with IndexedDB files.
- In `reopen-no-clear`, that exact same extension storage directory and files
  were still present on the same warm Tor service, proving the reused profile
  would keep prior browser runtime state if we did not wipe it first.
- In `reopen-with-clear`, the launcher removed `31` files and `11` directories
  before browser start, the old extension storage directory was gone, and the
  next browser run created a fresh replacement runtime identity instead:
  `moz-extension+++41149472-0aa1-4247-bd10-8deda20c8ebe^userContextId=4294967295/`.
- That is stronger proof than the earlier forced-marker check: the fastest
  repeated-open path still keeps Tor warm, but it no longer reuses the prior
  browser runtime identity across browser runs.

Private runtime-dir proof:

- The launcher now creates the runtime state directories with private
  permissions up front instead of letting Tor fix them during boot.
- In the same proof directory,
  `fresh-launch.json` shows a seeded fresh launch still booted Tor to `100%`
  in `2.521s`, but the earlier `Fixing permissions on directory .../tor-data`
  warning is gone from `tor_boot.signal_lines`.
- This is a small safe startup cleanup only. It does not change Tor path
  rules, browser prefs, or seed scope.

CLI default-path alignment proof:

- `torfast/cli.py` now makes ordinary `torfast launch` and `torfast plan`
  generate a fresh state root under `tmp/torfast-launches/` by default, while
  `torfast warm`/`open` keep using the stable managed-service state root.
- Durable proof under
  `results/torfast-cli-default-proof-20260624T125839/` compares the two
  product paths directly. `fresh-default-launch.json` shows plain
  `python3 -m torfast launch --headless --browser-timeout 1` applied the
  shared cache-only Tor seed and the shared startup-only browser seed on a
  fresh root, kept `IsolateSOCKSAuth`, and booted Tor to `100%` in `2.516s`.
- The paired `pinned-state-root-launch.json` in the same proof directory shows
  the old fixed-root behavior instead reused an already-populated profile/data
  root, so both `dir_cache_seed_apply` and `browser_startup_seed_apply` were
  skipped with `reason = "data dir already has files"` /
  `reason = "profile dir not empty"`. That means the CLI now matches the repo's
  documented and previously proven seeded fresh-launch path instead of drifting
  into implicit whole-state reuse.

Shared seed refresh I/O proof:

- `torfast/dir_cache_seed.py` now refreshes the shared Tor cache seed
  incrementally, reusing unchanged cached files instead of recopying the whole
  seed tree whenever one small cache file changes.
- The same fresh default proof
  `results/torfast-cli-default-proof-20260624T125839/fresh-default-launch.json`
  also shows the post-launch seed refresh can now short-circuit cleanly:
  `dir_cache_seed_update.updated = false` with
  `reason = "seed already current"`.
- This is a product-path speed win that does not touch Tor path selection,
  browser privacy prefs, SOCKS isolation, or cached-state scope; it only cuts
  redundant local disk work after successful seeded launches.

Shared seed apply-path copy proof:

- `torfast/dir_cache_seed.py` now uses the stored manifest SHA256 during
  `apply_seed_to_data_dir()` instead of rehashing every seed file on every
  fresh launch, and it uses Python's platform-optimized `shutil.copy2()` path
  instead of the old manual Python read/write+hash loop.
- Durable proof under `results/torfast-seed-apply-proof-20260624T130633/`
  includes a real fresh launch plus a direct microbenchmark of the old versus
  new apply path over the current shared seed set
  (`cached-certs`, `cached-microdesc-consensus`, `cached-microdescs`,
  `cached-microdescs.new`).
- In `seed-apply-bench.json`, the old median apply time was `0.05298s` and the
  new median was `0.03486s`, a `0.01813s` drop (`~34%` faster) for the local
  seed-copy step while preserving identical seed-file contents and metadata in
  the launch record.
- The paired `fresh-default-launch.json` in the same proof directory still
  shows `dir_cache_seed_apply.applied = true`, `browser_startup_seed_apply.applied = true`,
  `dir_cache_seed_update.updated = false` with `reason = "seed already current"`,
  and `IsolateSOCKSAuth` intact.

Browser startup-seed preservation proof:

- `torfast/browser_startup_seed.py` now preserves an existing compatible
  `startupCache/webext.sc.lz4` entry when a later short browser run sees the
  same bundled extension XPI but does not regenerate the startup cache file.
- This closes a real regression: the shared startup seed had been reduced to
  only the bundled XPI after a short headless run, which weakened a previously
  proven speed path without changing privacy behavior.
- Durable proof under `results/torfast-startup-seed-preserve-proof-20260624T131453/`
  shows the repaired shared seed again contains both
  `extensions/{73a6fe31-595d-460b-a920-fcc0f8843232}.xpi` and
  `startupCache/webext.sc.lz4` in `doctor.json`, and the paired
  `fresh-default-launch.json` shows a fresh seeded launch now ends with
  `browser_startup_seed_update.updated = false` and
  `reason = "seed already current"` instead of degrading the seed contents.
- The same launch record keeps `browser_startup_seed_apply.applied = true`,
  `dir_cache_seed_apply.applied = true`, and `IsolateSOCKSAuth` intact, so this
  is a strict speed-path preservation fix rather than a Tor-behavior change.

Current product-path runtime check:

- Fresh runtime compare
  `results/torfast-runtime-compare-20260624T131719/torfast-runtime-compare.json`
  reran the current product path after the fresh-root CLI change plus the seed
  I/O fixes. The strongest medians in that `2`-run window were still the same:
  cold launch `25419ms`, seeded launch `6991ms`, primed launch `6934ms`, and
  warm reuse `4220ms`.
- That confirms the current safe direction still holds: shared cache-only seed
  reuse cuts one-shot launch wall time by roughly `18.4s` versus cold in this
  window, and warm reuse remains the absolute fastest repeated-open path.
- The same runtime compare also keeps browser-startup-seed promotion rejected
  as a speed claim. In this particular window, `seeded_launch` was
  `324ms` slower than `seeded_launch_no_browser_startup_seed`, so the preserved
  startup seed is now safe and non-degrading, but still not proven as a robust
  speed win by itself.
- Because of that evidence, the normal runtime default is now browser-startup
  seed off. Use `--browser-startup-seed` only for explicit A/B or lab runs.
- Direct proof under
  `results/torfast-browser-startup-default-proof-20260624T133924/` shows both
  modes on the current launcher path: `default-off-launch.json` records
  `browser_startup_seed_apply.applied = false` with
  `reason = "disabled by flag"`, while `opt-in-launch.json` records
  `browser_startup_seed_apply.applied = true` and copies both the bundled XPI
  and `startupCache/webext.sc.lz4`.

One-shot browser-launch overlap proof:

- `tools/launch_torfast_browser.py` now starts the browser on fresh one-shot
  `torfast launch` to the default local `about:tor` startup page as soon as C
  Tor opens the local SOCKS listener, instead of blocking browser start until
  `Bootstrapped 100%`.
- At that point, managed warm-service commands still waited for full boot, so
  `torfast warm` and `torfast open` kept the older managed-service behavior.
- Focused rotated A/B under
  `results/torfast-launch-gate-compare-20260624T215037/summary.json` ran `4`
  cycles of the new default `socks_ready` gate versus the old
  `--browser-launch-gate tor_boot_100` path on the same seeded fresh-launch
  setup (`about:tor`, headless, `1.0s` timeout, browser startup seed off).
- Result: default `socks_ready` median wall time was `2.444s`, versus
  `3.935s` for the old full-boot wait, a `-1.491s` drop in that same-window
  proof.
- The saved launch records show the expected mechanism. On the new path,
  `tor_browser_launch_gate.seconds` was only `0.005s` median before browser
  start, instead of making browser launch wait for the old full
  `Bootstrapped 100%` gate first.
- Tor quality proof stayed intact in every saved run:
  `tor_boot.ok = true`, `tor_boot` still reached `Bootstrapped 100%`,
  `dir_cache_seed_apply.applied = true`, and
  `torrc_quality.isolate_socks_auth = true`.
- This is a launch-path overlap win only. It does not change Tor path rules,
  seed scope, browser privacy prefs, or SOCKS isolation; it just stops wasting
  the last part of Tor bootstrap before starting the browser process on the
  local startup-page launch.

Direct external-page launch follow-up:

- The first external-page follow-up
  `results/torfast-launch-gate-browser-proof-20260624T220047/summary.json` is
  not the source of truth. That draft waited for full Tor boot before it
  launched the benchmark browser, so it did not really test browser-overlap
  timing.
- To fix that, the repo now has
  `tools/run_torfast_launch_gate_compare.py`, which starts the real benchmark
  browser right at the chosen gate, measures wall time only until the browser
  benchmark finishes, and then separately verifies that Tor still reached
  `Bootstrapped 100%` with `IsolateSOCKSAuth` intact.
- Strongest current proof is
  `results/torfast-launch-gate-compare-20260624T225720/summary.json`. It ran
  `5` rotated cycles across Tor Check, the Tor homepage, and the Tor download
  page for `tor_boot_95` versus the older `tor_boot_100` baseline.
- Quality stayed intact in every saved run:
  `boot_after_benchmark_ok_runs = 5` and
  `torrc_isolate_socks_auth_ok_runs = 5` for every target/gate pair.
- Result: `tor_boot_95` now looks like the best current network default.
  Relative to `tor_boot_100`, wall time to benchmark end improved on all three
  tested pages: `-0.959s` on Tor Check, `-1.107s` on the homepage, and
  `-0.501s` on download. Browser elapsed also improved on Tor Check
  (`-512.541ms`) and the homepage (`-587.307ms`), and was only slightly worse
  on download (`+38.190ms`).
- Earlier exploratory proof
  `results/torfast-launch-gate-compare-20260624T225253/summary.json` also
  pointed at the same direction: `tor_boot_95` was the strongest middle gate
  across the three-page rotated screen, while `tor_boot_90` was good on Tor
  Check and download but weaker on the homepage.
- `tor_boot_75` is still not a good network default. The broader `5`-cycle
  proof under `results/torfast-launch-gate-compare-20260624T223933/summary.json`
  showed it helped Tor Check but hurt the homepage badly.
- I also tested a tiny post-`90%` hold instead of jumping straight from `90%`
  to `95%`. The compare tool now supports `tor_boot_90_plus_200ms` and
  `tor_boot_90_plus_400ms` so we can test "launch a bit earlier, but not all
  the way down to raw `90%`" in the same real browser window.
- The first three-page screen under
  `results/torfast-launch-gate-compare-20260624T232409/summary.json` already
  rejected `tor_boot_90_plus_400ms`: it was slower than `tor_boot_95` on all
  three targets, including `+1.920s` wall on Tor Check and `+2.796s` wall on
  download.
- `tor_boot_90_plus_200ms` looked mixed in that first screen, so I ran a
  stronger direct `5`-cycle head-to-head under
  `results/torfast-launch-gate-compare-20260624T232841/summary.json`.
- That follow-up rejects promotion. Quality still held in every saved run
  (`boot_after_benchmark_ok_runs = 5`,
  `torrc_isolate_socks_auth_ok_runs = 5`), but speed did not stay robust:
  `tor_boot_90_plus_200ms` helped the homepage (`-0.956s` wall,
  `-1504.040ms` elapsed), was basically flat-to-worse on Tor Check
  (`+0.089s` wall, `-167.840ms` elapsed but `+648.758ms` raw load), and lost
  hard on download (`+1.756s` wall, `+1695.725ms` elapsed,
  `+1031.848ms` raw load).
- Decision stays the same: keep real network URLs on plain `tor_boot_95`.
  The tiny post-`90%` hold is another mixed lab lane, not a safe new default.
- I also tested a local file wait-page overlap lane after `socks_ready`, first
  with Marionette navigating to a local refresh page and then with the cleaner
  "start the browser on the local wait tab first" shape.
- The early draft under
  `results/torfast-launch-gate-compare-20260624T235353/summary.json` looked
  promising on wall time for `socks_ready_wait_1500ms`, but it was not stable:
  Tor Check only passed `1` of `2` runs and the failed run ended on an error
  page instead of the real target.
- The cleaner first-tab proof under
  `results/torfast-launch-gate-compare-20260625T000828/summary.json` rejected
  the lane completely. Both `socks_ready_wait_1500ms` and
  `socks_ready_wait_1800ms` failed every run on Tor Check and the homepage,
  while plain `tor_boot_95` stayed clean. The failure was not a network-speed
  issue: the browser session itself failed to start with
  `session not created ... browserElement is null`.
- Decision: reject the local wait-page lane. It is not a safe browser-overlap
  default for Tor Browser in this setup.
- Decision: keep the fast `socks_ready` overlap for the default local
  `about:` startup page, and move real network URLs from `tor_boot_100` to the
  new `tor_boot_95` default. Users can still override with
  `--browser-launch-gate ...` for lab checks.

Cold managed-open gate win:

- `tools/launch_torfast_browser.py` now lets cold `torfast open` / `torfast start`
  use the same proven browser launch gates as one-shot launch when they must
  start a fresh managed C Tor service themselves. At that point,
  `torfast warm` still waited for full boot because it did not launch the
  browser.
- Direct proof under
  `results/torfast-managed-open-gate-compare-20260625T002453/summary.json`
  ran `2` rotated cycles of fresh managed-state `torfast start` against
  `about:tor` and `https://check.torproject.org/`, comparing the new default
  auto gate against the old explicit `tor_boot_100` behavior with a `3.0s`
  headless browser timeout.
- Result: the new cold managed-open path was faster on both tested targets.
  On `about:tor`, median wall time dropped from `6.249s` to `3.446s`
  (`-2.803s`). On Tor Check, median wall time dropped from `6.146s` to
  `5.528s` (`-0.618s`).
- Quality and managed-service proof stayed intact in every saved auto-gate run:
  `tor_browser_launch_gate` recorded `socks_ready` for `about:tor` and
  `tor_boot_95` for Tor Check, `tor_boot` still reached
  `Bootstrapped 100%`, `torrc_quality.isolate_socks_auth = true`,
  `reused_tor_service` was written, and the paired `torfast stop` calls
  succeeded afterward, proving the managed Tor service stayed alive after the
  earlier browser start.
- Decision: keep the overlap gate for cold `torfast open` / `torfast start`.
  This makes the first managed open faster without changing Tor config, browser
  privacy prefs, or the already-proven network launch-gate policy.

Warm/open ready-gate win:

- `tools/launch_torfast_browser.py` now lets `torfast warm` return once the
  managed C Tor service reaches the current ready gate instead of always
  waiting for full `Bootstrapped 100%`. A reused `torfast open` now waits only
  for the gate the target needs on that same running service before browser
  start, and then still records full `Bootstrapped 100%` after the browser run.
- The same patch also now truncates the managed `tor.log` before each fresh
  detached boot so gate waits cannot match stale lines from an older service.
- Direct proof under
  `results/torfast-warm-open-launch-gate-compare-20260625T004158/summary.json`
  ran `2` rotated cycles of `torfast warm` then `torfast open` on
  `about:tor` and `https://check.torproject.org/`, comparing the new default
  auto behavior against the old warm-side `tor_boot_100` wait with a `3.0s`
  headless browser timeout.
- Result: the combined `warm + open` path got faster on both tested targets.
  On `about:tor`, median combined wall time dropped from `6.271s` to `3.639s`
  (`-2.632s`). On Tor Check, median combined wall time dropped from `6.223s`
  to `5.623s` (`-0.600s`).
- The saved launch records show the expected mechanism. In the new default
  path, `torfast warm` reached `tor_managed_ready.gate = socks_ready` in about
  `0.255s`. The later `torfast open` against Tor Check then waited only until
  `tor_boot_95` on the reused service (`1.910s` median) before browser start,
  while the `about:tor` open path started immediately from the reused
  `socks_ready` gate.
- Quality and service proof stayed intact in every saved default run:
  the later `open` launch still saved `tor_boot.ok = true` with
  `Bootstrapped 100%`, `torrc_quality.isolate_socks_auth = true`,
  `reused_tor_service.ready_gate = tor_boot_100` by the end of the open, and
  the paired `torfast stop` calls succeeded afterward.
- Decision: keep the ready-gate handoff for `torfast warm` and reused
  `torfast open`. It makes the two-command managed workflow faster without
  changing Tor config, browser privacy prefs, or SOCKS isolation.
- I then tightened the local polling granularity inside the launcher waiters
  from `250ms` to `50ms` so managed gate waits and browser-exit waits stop
  oversleeping after the ready signal has already happened.
- Focused same-machine local rerun under
  `results/torfast-warm-open-about-poll-compare-20260625T005218/summary.json`
  repeated only the `about:tor` warm/open path and compared it directly to the
  earlier saved `about:tor` proof
  `results/torfast-warm-open-launch-gate-compare-20260625T004158/summary.json`.
- Result: this is a small but real local win. For the current default
  `warm_open_auto` path, median `warm` wall time dropped from `0.397s` to
  `0.191s` (`-0.206s`), `open` wall time dropped from `3.242s` to `3.169s`
  (`-0.073s`), and combined wall time dropped from `3.639s` to `3.359s`
  (`-0.280s`). The old `tor_boot_100` warm path also improved by a similar
  local amount (`-0.290s` combined), which matches the intended mechanism:
  less launcher-side polling delay, not a Tor-behavior change.
- Decision: keep the tighter polling interval. It is a pure local timing win
  and does not change Tor config, browser privacy prefs, SOCKS isolation, or
  the selected launch gates.

Reusable warm/open compare harness:

- `tools/run_torfast_warm_open_compare.py` now gives the managed
  `torfast warm` + `torfast open` path the same kind of reusable proof harness
  that `tools/run_torfast_launch_gate_compare.py` already gives one-shot
  launch. It runs real `warm`, `open`, and `stop` commands, saves per-run
  JSON, and summarizes warm wall time, managed-ready seconds, open wall time,
  browser elapsed time, full-boot seconds, and the usual quality checks.
- Fresh same-machine proof under
  `results/torfast-warm-open-compare-20260625T021840/summary.json`
  reran `2` rotated cycles of `auto` versus `tor_boot_100` on `about:tor`
  and `https://check.torproject.org/` with a `3.0s` headless browser timeout.
- Result: it matched the earlier decision. Median combined `warm + open` wall
  time was `3.381s` for `auto` versus `6.732s` for `tor_boot_100` on
  `about:tor` (`-3.351s`), and `5.644s` versus `5.907s` on Tor Check
  (`-0.263s`).
- Quality stayed intact in every saved run. For both profiles on both targets,
  the summary kept `torrc_isolate_socks_auth_ok_runs = 2`,
  `open_tor_boot_ok_runs = 2`, `reused_service_ok_runs = 2`, and
  `stop_ok_runs = 2`.

Warm/open network `socks_ready` follow-up:

- I then used the new warm/open harness to probe only the real network-page
  bottleneck under
  `results/torfast-warm-open-compare-20260625T022519/summary.json`,
  comparing `auto`, `tor_boot_95`, `tor_boot_90`, `socks_ready`, and
  `tor_boot_100` on `https://check.torproject.org/`.
- On raw command wall time alone, `socks_ready` looked best. Median combined
  `warm + open` time was `3.370s` for `socks_ready` versus `5.647s` for the
  current `auto` path, while the saved summary still kept
  `open_tor_boot_ok_runs = 2`, `torrc_isolate_socks_auth_ok_runs = 2`,
  `reused_service_ok_runs = 2`, and `stop_ok_runs = 2`.
- But that measure can over-credit "return early and let the browser wait," so
  I reran the real page benchmark harness on the same Tor Check target under
  `results/torfast-launch-gate-compare-20260625T022651/summary.json`,
  comparing `tor_boot_95`, `socks_ready`, and `tor_boot_100`.
- Result: do not promote network `socks_ready` yet. It kept only `1/2` ok
  benchmark runs, and the bad `socks_ready` run timed out after `45000 ms`
  with `NS_ERROR_UNKNOWN_PROXY_HOST` while Tor later still reached
  `Bootstrapped 100%`. Even the one successful `socks_ready` sample was
  slightly slower than `tor_boot_95` on page metrics (`elapsed +86 ms`,
  `load +155 ms`).
- Decision: keep the current network default at `tor_boot_95`. `socks_ready`
  is only a command-wall win so far, not a proven real page-ready win.

Warm/reused network `socks_ready` promotion:

- I then added a reusable real page-load harness for the managed workflow in
  `tools/run_torfast_warm_open_benchmark_compare.py`. Unlike the earlier
  command-wall-only compare, this one runs `torfast warm`, then measures a real
  browser page load through that warmed SOCKS port, then waits for
  `Bootstrapped 100%` and stops the managed service.
- Fresh pre-patch proof under
  `results/torfast-warm-open-benchmark-compare-20260625T023336/summary.json`
  narrowed the question to `tor_boot_95`, `tor_boot_90`, and `socks_ready` on
  `https://check.torproject.org/` with `4` rotated cycles. That ruled out
  `tor_boot_90`: it was worse than `tor_boot_95` on both browser elapsed time
  (`+578 ms`) and page load time (`+728 ms`).
- The same stronger run also showed the important split for reused warm opens:
  `socks_ready` was slower inside the browser than `tor_boot_95`
  (`elapsed +932 ms`, `load +894 ms`), but still faster end-to-end from the
  start of `warm` to the finished page load because warm returned much earlier
  (`combined wall -1.160s`).
- That was enough to justify a narrow runtime change: keep cold network starts
  on `tor_boot_95`, but switch only the warm/reused managed `auto` path to
  `socks_ready`. In code, `tools/launch_torfast_browser.py` now leaves
  `resolve_browser_launch_gate()` unchanged for cold starts and adds a
  managed-path override through `resolve_managed_browser_launch_gate()`.
- Fresh post-patch command-path proof under
  `results/torfast-warm-open-compare-20260625T023844/summary.json`
  compared the new default `auto` against explicit `tor_boot_95` on
  `https://check.torproject.org/` across `4` rotated cycles. Result: the real
  `torfast warm` + `torfast open` flow is now faster by `-2.159s` combined
  wall time (`3.344s` versus `5.503s`) with `4/4` ok runs and all saved
  quality counters still green.
- Fresh post-patch real page-load proof under
  `results/torfast-warm-open-benchmark-compare-20260625T023936/summary.json`
  confirms the new default is also faster on actual loaded-page timing, not
  just earlier command return. Against explicit `tor_boot_95`, the new
  managed-path `auto` cut combined wall time by `-2.827s`, browser elapsed by
  `-696 ms`, and page load by `-747 ms`, again with `4/4` ok runs,
  `torrc_isolate_socks_auth_ok_runs = 4`, `boot_after_benchmark_ok_runs = 4`,
  and `stop_ok_runs = 4`.
- Decision: keep this narrow promotion. Cold network starts stay on
  `tor_boot_95`; warm/reused managed network `auto` now uses `socks_ready`
  because it is faster end-to-end there without degrading the saved Tor
  quality checks.

Warm/open post-warm wait family rejection:

- I extended `tools/run_torfast_warm_open_benchmark_compare.py` so warm-path
  wait A/B runs can save randomized cycle order plus `p90` and `max` tail
  fields. This is the right gate for tiny post-warm waits because medians
  alone hid bad tails in the smaller early slices.
- The `250ms` wait is rejected. The randomized `12`-cycle A/B under
  `results/torfast-warm-open-benchmark-compare-20260625T031523/summary.json`
  kept all Tor quality counters green, but relative to current `auto` it made
  median load slower (`+373.587ms`) and made tails clearly worse
  (`p90 combined +1.627s`, `p90 elapsed +1676.114ms`, `max load +4895.259ms`).
  The saved paired wins were `7/12`, but the losses were much larger, and a
  fresh `gpt-5.4-pro` second opinion said to keep current `auto`.
- The `50ms` wait is also rejected for default use. A first randomized
  `12`-cycle slice under
  `results/torfast-warm-open-benchmark-compare-20260625T032208/summary.json`
  looked promising on medians and `p90`, but it still had one bad slow-success
  outlier. The wider randomized `24`-cycle rerun under
  `results/torfast-warm-open-benchmark-compare-20260625T032828/summary.json`
  flipped the center the other way: `50ms` got slower on median combined wall
  (`+0.431s`), median elapsed (`+478.163ms`), and median load (`+532.087ms`)
  even though some `p90` and max fields improved. A second `gpt-5.4-pro` read
  again said to keep current `auto`.
- The tiny waits were not better enough either. The `10ms`/`25ms` sweep under
  `results/torfast-warm-open-benchmark-compare-20260625T033639/summary.json`
  showed `25ms` clearly worse on medians, while `10ms` was basically a wash:
  combined wall `-0.004s`, elapsed `+34.838ms`, load `-158.064ms`, with
  paired wins close to coin-flip. The outside read again said no product
  change from that sample.
- The larger `10ms` replication under
  `results/torfast-warm-open-benchmark-compare-20260625T034411/summary.json`
  closed the lane out for now. Even though median combined wall was slightly
  better (`-0.121s`), it made median load worse (`+141.588ms`) and made tails
  much worse (`p90 combined +4.865s`, `p90 elapsed +2661.637ms`,
  `max combined +3.278s`, `max load +9602.96ms`). `gpt-5.4-pro` again said to
  keep current `auto`.
- Decision: keep the current warm/reused managed `auto = socks_ready` path
  with no fixed post-warm delay. The fixed wait family is now lab-only; any
  later revisit should use the randomized harness and gate on `p90` and `max`
  stability, not median alone.

Warm/open startup-seed repeated-open check:

- Fresh proof
  `results/torfast-warm-open-browser-startup-compare-20260624T184217/summary.json`
  tested the new fresh-profile `warm/open` path directly, with the browser
  startup seed off versus on against the same managed warm Tor service and
  rotated order across `4` cycles.
- This is the right repeated-open promotion gate after the browser-state reset
  fix: each `open` run reused warm Tor, cleared the old browser profile/home
  state first, and then either skipped or applied the shared startup-only
  browser seed on that fresh profile.
- Result: still no meaningful speed win. Median `open` wall time was
  `1.324s` with the startup seed off and `1.327s` with it on. Median
  launch-overhead stayed effectively flat too: `0.324s` off versus `0.327s`
  on. The tiny browser elapsed difference (`1.185s` off versus `1.179s` on)
  is too small and inconsistent to promote.
- Decision stays the same: keep browser-startup seed opt-in only. It is safe to
  apply on the fresh-profile repeated-open path, but it still is not a real or
  durable speed lever.

Fresh-launch startup-seed order-bias fix and re-check:

- `tools/run_torfast_runtime_compare.py` now rotates the execution order of
  `seeded_launch` and `seeded_launch_no_browser_startup_seed` by run index
  instead of always running the seeded variant first. The focused unit guard is
  in `tests/test_torfast_runtime_compare.py`.
- This matters because the browser-startup-seed effect is small enough that a
  fixed same-window order can distort the answer. The comparison harness now
  gives a fairer fresh-launch read before any promotion call.
- Fresh proof under
  `results/torfast-runtime-compare-20260624T192538/torfast-runtime-compare.json`
  reran the official product-path compare with that rotated order and a tighter
  `1.0s` browser timeout to focus on first-open startup cost.
- Result: browser startup seed is still slower on the fresh-launch path.
  `seeded_launch` came in at median `4166ms`, while
  `seeded_launch_no_browser_startup_seed` came in at median `3792ms`. The saved
  delta stays against promotion too: `+374ms` elapsed,
  `+0.374s` launch overhead, and `+0.165s` Tor boot.
- Decision stays the same: keep browser-startup seed off by default even for
  fresh launch. The safe speed win is still the shared Tor dir-cache seed, not
  the browser startup seed.

Broader browser-seed lab rejection:

- I also tested a broader lab-only browser seed built from extra fresh-profile
  files that stayed byte-identical across multiple `about:tor` fresh launches,
  not just the current startup seed's bundled XPI plus startup cache.
- The lab seed manifest is under
  `results/torfast-browser-broad-seed-20260624T191421/manifest.json`, and the
  direct same-window three-way compare is under
  `results/torfast-browser-seed-threeway-compare-20260624T191455/summary.json`.
- That broader seed did not help. Its median wall time was `3.980s`, versus
  `3.816s` for the current startup seed and `3.991s` for no seed in that
  focused `1.0s` first-open check. Relative to the current startup seed, the
  broader seed was worse by `+0.164s` wall and `+0.173s` launch overhead.
- So that lane is rejected for now. It adds browser profile material without a
  real speed gain, which is the wrong trade.

Warm/open general-circuit gate rejection:

- I reran the warm/open Tor-side readiness idea with a stronger gate under
  `results/torfast-warm-open-general-circuit-compare-20260624T195304/summary.json`.
  This used `6` rotated cycles across `https://check.torproject.org/` and
  `https://www.torproject.org/`, with the current repeated-open default shape:
  warm managed C Tor, fresh browser benchmark state, and browser startup seed
  off.
- The earlier `4`-cycle slice had looked mixed. This broader same-window proof
  is not mixed anymore: waiting for one built `GENERAL`/`CONFLUX_LINKED`
  circuit during warm made the path slower on both targets and also made warm
  boot itself slower in this window.
- Plain warm/open had median boot `19.599s`, Tor Check `2886.222ms`, and
  homepage `5734.089ms`. The circuit-ready variant had median boot `21.326s`,
  extra general wait `0.258s`, Tor Check `3113.139ms`, and homepage
  `8047.927ms`.
- Relative to plain warm/open, the circuit-ready variant was worse by
  `+1.727s` on warm boot, `+226.917ms` on Tor Check elapsed, and
  `+2313.838ms` on homepage elapsed. Raw load also got worse on both targets
  (`+275.968ms` and `+2303.25ms`).
- Decision: reject warm-side general-circuit waiting for now. It is not a safe
  repeated-open speed lever, so the launcher should stay as-is and the next
  speed work should move away from more circuit-ready waits.

Dir-cache seed local clone win:

- `torfast/dir_cache_seed.py` now prefers the native macOS `clonefile` path
  when it applies the shared C Tor dir-cache seed into a fresh data dir, with
  normal `copy2` fallback when clone support is not available.
- Focused proof under
  `results/torfast-dir-cache-seed-apply-bench-20260624T200759/summary.json`
  compared the real launcher seed-apply step with clone enabled versus forced
  plain copy across `7` runs on the current seed set.
- Result: clone-enabled median seed apply was `0.549ms`, while forced copy was
  `33.222ms`, for a local delta of `-32.673ms`. Every clone-enabled run
  reported `copy_mode = "clone"`.
- Real product-path proof under
  `tmp/torfast-clone-proof-20260624T200818/launch.json` then confirmed one
  fresh headless `torfast launch` still passed browser and Tor checks and that
  all applied dir-cache seed files (`cached-certs`,
  `cached-microdesc-consensus`, `cached-microdescs`,
  `cached-microdescs.new`) used `copy_mode = "clone"` on this Mac.
- This is a small win, not the main answer: it removes unnecessary local disk
  work from every seeded fresh launch without changing Tor path rules, browser
  prefs, or seed contents.

Bundled-seeded Conflux UX browser-page check:

- `tools/run_torfast_browser_compare.py` can now add bundled-seeded same-window
  profiles that keep the bundled Tor binary and shared cache-only seed path,
  but force the official `ConfluxClientUX` mode to `latency`,
  `throughput`, or `throughput_lowmem`.
- First broader screen
  `results/torfast-browser-compare-20260624T202520/torfast-browser-compare.json`
  ran `2` rotated cycles across Tor check, homepage, and download with bundled
  cold, bundled seeded, local cold, local seeded, and the three forced
  bundled-seeded UX variants.
- In that small `n=2` window, forced `latency` looked promising against the
  current bundled-seeded default: Tor Check elapsed `-68.829ms`, homepage
  elapsed `-1578.111ms`, and download elapsed `-925.303ms`. But forced
  `throughput` was clearly worse on Tor Check (`+1489.405ms`) and homepage
  (`+1164.129ms`) and still slightly worse on download (`+168.047ms`), while
  `throughput_lowmem` was mixed and slightly worse on download
  (`+129.58ms`).
- Promotion check
  `results/torfast-bundled-seeded-latency-compare-20260624T204700/summary.json`
  then ran a cleaner direct `3`-cycle head-to-head between normal
  bundled-seeded and bundled-seeded plus `ConfluxClientUX latency` on the same
  broader pack. That contradicted the first slice: forced `latency` was worse
  on Tor Check (`+915.045ms` elapsed, `+54.447ms` raw load) and homepage
  (`+1623.244ms` elapsed, `+1427.317ms` raw load), and only helped the heavy
  download page (`-752.037ms` elapsed, `-726.41ms` raw load).
- Follow-up direct `3`-cycle head-to-head
  `results/torfast-bundled-seeded-throughput-lowmem-compare-20260624T130230/summary.json`
  also rejected `throughput_lowmem`: it was worse on Tor Check
  (`+375.94ms` elapsed, `+508.915ms` raw load) and on download
  (`+781.585ms` elapsed, `+745.065ms` raw load), and only improved the
  homepage (`-397.607ms` elapsed, `-442.198ms` raw load).
- Decision: keep forced `ConfluxClientUX` modes lab-only for the browser path.
  `throughput` was clearly bad in the first broader screen, `latency` failed
  the cleaner direct follow-up, and `throughput_lowmem` also failed the direct
  follow-up. The default stays `ConfluxEnabled auto` with no forced UX mode.

Browser default-pref proof cache win:

- `torfast/browser_defaults.py` now caches the parsed Tor Browser
  `000-tor-browser.js` proof by `omni.ja` path plus source size/mtime, so an
  unchanged browser app does not need to reopen and reparse the zip on every
  launch.
- Focused benchmark under
  `results/torfast-browser-default-prefs-cache-bench-20260624T131035/summary.json`
  measured `20` cold parse versus warm-cache reads on the current bundled Tor
  Browser app. Median cold parse was `17.709ms`; median warm-cache read was
  `0.065ms`; delta `-17.645ms`.
- Real product-path proof under
  `tmp/torfast-default-pref-cache-proof/` then showed the same default launch
  path stayed clean. In `run1/launch.json`,
  `browser_default_prefs.cache_hit = false`; in `run2/launch.json`,
  `browser_default_prefs.cache_hit = true`. Both runs still had
  `browser.ok = true`, `dir_cache_seed_apply.applied = true`, and normal Tor
  boot on fresh seeded state roots.
- This is another small safe default-path win only. It does not change Tor
  path rules, browser prefs, or the proof itself; it only avoids re-reading
  the same unchanged browser zip on later launches.

Warm/open SOCKS auth rotation proof:

- The fastest repeated-open path already keeps
  `SocksPort ... IsolateSOCKSAuth`. The next quality question was whether a
  second real browser run on the same warm Tor process still presents a fresh
  SOCKS isolation bucket, or whether it silently reuses the exact prior one.
- Local Tor source says this matters. In
  `upstream/tor/src/feature/control/control_fmt.c`, the controller status view
  exposes `SOCKS_USERNAME` and `SOCKS_PASSWORD` explicitly "used by
  IsolateSOCKSAuth". In `upstream/tor/src/core/or/or.h`,
  `ISO_DEFAULT` includes `ISO_SOCKSAUTH`. In
  `upstream/tor/src/core/or/connection_edge.c`, Tor rejects circuit reuse when
  the SOCKS username or password differs.
- Real proof under
  `results/torfast-warm-bench-isolation-20260624T212745/summary.json`
  reused one warm managed Tor service for two real
  `https://check.torproject.org/` browser benchmark runs. A local byte tap sat
  in front of the same warm SOCKS port and recorded only auth lengths plus
  short SHA256 prefixes, not the secrets themselves.
- Result: the second browser run did rotate the SOCKS auth bucket. For the
  `check.torproject.org` connection, run `1` used username hash
  `584e0257deab` and password hash `c17439c54b4c`; run `2` kept the same
  username hash but changed the password hash to `9039badda72a`. The paired
  `securedrop.org` bootstrap connection and the paired Cloudflare onion
  connection showed the same shape: stable per-origin username bucket, fresh
  password bucket on the second browser run.
- The same proof also tried the new default-off control-port
  `stream-status` probe, but it did not surface matching live rows in this
  setup. So the byte tap is the source of truth here, not the control-port
  probe.
- Stronger conclusion: the warm/open repeated-open path is safer than we had
  proved before. On the same warm Tor process, real browser reruns are not
  blindly reusing the exact previous SOCKS auth bucket that Tor uses for
  `ISO_SOCKSAUTH`. This is strong repeated-open isolation evidence, though it
  is still not the same as a full per-circuit reuse proof.

## 2026-06-21 status

Browser startup-seed decision check:

- The shared browser startup seed remains narrowly scoped to safe bundled
  extension startup artifacts only (`extensions/*.xpi` plus
  `startupCache/webext.sc.lz4`). It still does not copy cookies, browsing
  history, HTTP cache, or profile metadata with per-profile paths/timestamps.
- Real startup-seed refresh proof under
  `tmp/torfast-startup-seed-realcheck/launch.json` shows the applied seed was
  refreshed successfully in a real launch path
  (`browser_startup_seed_apply.applied = true`,
  `browser_startup_seed_update.updated = true`) after tightening refresh to
  already-whitelisted bundled addon IDs.
- Fresh product-path A/B proof
  `results/torfast-runtime-compare-20260621T004427/torfast-runtime-compare.json`
  compared cache-seeded fresh launch with and without applying that browser
  startup seed across `3` runs. Median whole-command wall time improved only
  from `11016ms` to `10982ms` (`-34ms`), median browser elapsed stayed flat
  (`8.139s` without versus `8.140s` with), and the per-run spread was not
  consistent enough to claim a robust win.
- Earlier n=`1` proof
  `results/torfast-runtime-compare-20260621T001830/torfast-runtime-compare.json`
  was also tiny (`-7ms` median whole-command delta), so the install-time
  browser-startup prime stays opt-in through
  `--prime-browser-startup-seed-after-install` rather than becoming the
  product default.
- The current recommendation is unchanged: use
  `python3 -m torfast install-browser` then `python3 -m torfast launch` for
  the normal safe path, `python3 -m torfast warm` then `python3 -m torfast open`
  for fastest repeated opens, and treat browser-startup priming as an optional
  first-use polish step rather than a meaningful speed lever.

## 2026-06-20 status

Verified browser-install/runtime proof path:

- `torfast/browser_install.py` and `python3 -m torfast install-browser` now
  resolve the live stable Tor Browser release from the Tor dist index, download
  the macOS DMG plus its detached signature, download the signed checksum file
  plus its detached signature, fetch the Tor Browser signing key pinned to the
  expected fingerprint, verify both detached signatures, match the DMG SHA256,
  and then copy the app bundle, re-check codesign/notarization, and prove the
  installed browser still ships Tor Browser default prefs.
- Durable proof is saved under `results/torfast-runtime-20260620T163949/`:
  `install-browser.json` for the verified install, `doctor.json` for
  auto-discovery and pref proof, and `launch.json` for a real headless runtime
  smoke over the earlier local-C-Tor lab path.
- The launcher also now treats `--browser-timeout` as an intentional stop, not
  a failure. Real proof `results/torfast-runtime-20260620T163949/launch.json`
  shows headless Tor Browser started against local C Tor, Tor boot reached
  `100%`, Tor Browser default-pref proof stayed green, and the launcher exited
  successfully after the requested `15s` timeout.
- This is product/runtime progress, not a final speed win. It removes the
  missing-browser blocker for real end-to-end validation and makes the current
  proven fast path reproducible on a clean machine.

Bundled-Tor default discovery proof:

- `torfast` now prefers the bundled Tor binary inside the discovered Tor
  Browser app before falling back to the local lab build.
- Direct proof `results/torfast-bundled-default-proof-20260620T201425/doctor.json`
  shows `torfast doctor` auto-discovered
  `tmp/browser/Tor Browser.app/Contents/MacOS/Tor/tor` ahead of the local
  build candidate list.
- Direct proof `tmp/torfast-bundled-default-proof-20260620T201425/launch.json`
  shows plain `python3 -m torfast launch --headless --browser-timeout 6`
  used that bundled Tor path, applied the shared cache-only seed, kept
  `IsolateSOCKSAuth`, and booted Tor to `100%` in `2.522s` before the fixed
  `6s` browser dwell completed successfully.

Torfast cold-vs-warm runtime proof:

- New runner `tools/run_torfast_runtime_compare.py` measures the current
  product path directly with the installed Tor Browser and the auto-discovered
  Tor binary. It now
  interleaves four real product flows: fresh one-shot cold launch, cache-primed
  launch on the same state root, cache-seeded launch on a different fresh state
  root, first browser open that leaves a managed Tor service warm, and
  immediate browser reopen that reuses that warm service. It records
  whole-command wall time plus derived launch-overhead, Tor-boot, post-boot
  browser overhead, and prime-step summaries.
- Fresh proof `results/torfast-runtime-compare-20260620T200853/torfast-runtime-compare.json`
  ran `2` interleaved cycles with `about:tor` headless and a fixed `6s`
  browser dwell. The run auto-discovered bundled Tor at
  `tmp/browser/Tor Browser.app/Contents/MacOS/Tor/tor`. Median whole-launch
  time was `25983ms` for cold launch, `8986ms` for cache-seeded launch on a
  different fresh state root, `8911ms` for cache-primed launch on the same
  state root, `37251ms` for the first warm-workflow open in that noisy window,
  and `6309ms` for warm reuse.
- The strongest new product result is that cache priming gives nearly all of
  the startup win without keeping Tor resident or reusing the whole Tor state
  root. Median Tor boot was `19.639s` cold, `2.571s` for cache-seeded fresh
  launch, `2.595s` for same-root cache priming, and `0s` on warm reuse.
  Post-boot browser overhead stayed small in every successful path (`0.345s`
  cold, `0.415s` cache-seeded, `0.317s` same-root primed, `0.309s` warm
  reuse), so
  the dominant delay is still Tor bootstrap and directory state, not browser
  work.
- That means the best current safe default direction is now stronger:
  `torfast prime` plus ordinary later `torfast launch` is the lightweight fast
  path, while `torfast open` after a prior `torfast warm` remains the absolute
  fastest repeated-open path if background residency is acceptable. Neither
  direction weakens Tor Browser prefs, SOCKS isolation, or Tor path rules.

Torfast real first-use browser page-load proof:

- New runner `tools/run_torfast_browser_compare.py` measures the current
  product path on real Tor Browser pages with fresh local C Tor state each
  cycle. It rotates cold versus seeded order across cycles, refreshes a
  private cache-only seed for each seeded run, applies that seed to a
  different fresh measured data dir, keeps the top-level Tor Browser
  default-pref and no-Marionette fingerprint proofs, and saves screenshots plus
  effective proxy-pref evidence for each page.
- Fresh proof
  `results/torfast-browser-compare-20260620T184347/torfast-browser-compare.json`
  ran `2` rotated cycles against `https://check.torproject.org/` and
  `https://www.torproject.org/`. Median Tor boot fell from `14.086s` cold to
  `2.886s` seeded.
- On `https://check.torproject.org/`, the seeded path improved both raw page
  load and end-to-end first-use launch+load: median browser load dropped from
  `1520ms` cold to `1102ms` seeded, while median launch+load dropped from
  `15606ms` to `3987ms` (`-11.619s`).
- On `https://www.torproject.org/`, raw browser load was roughly neutral and
  slightly slower after boot (`5587ms` cold versus `5809ms` seeded,
  `+222ms`), but median end-to-end first-use launch+load still dropped from
  `19673ms` to `8694ms` (`-10.979s`) because Tor bootstrap dominated the cold
  path.
- The saved browser runs kept the expected proxy prefs
  (`127.0.0.1`, the intended SOCKS port, remote DNS on, proxy type `1`), the
  `check.torproject.org` page title was
  `Congratulations. This browser is configured to use Tor.`, and both the seed
  refresh torrc and the measured seeded torrc kept `IsolateSOCKSAuth`.
- The same proof also shows that each seeded measured run copied only
  documented cache files into the fresh measured data dir:
  `cached-certs`, `cached-microdesc-consensus`, and `cached-microdescs.new`.
  No Tor `state` file was reused.
- Conclusion: yes, the lightweight cache-seeded path does translate into real
  first-use page wins end to end. The gain comes from startup/bootstrap, not
  from changing Tor Browser semantics once a page is already loading.

Torfast bundled-versus-local first-use browser proof:

- `tools/run_torfast_browser_compare.py` can now add a
  `bundled_c_tor_browser_seeded` profile that primes and reapplies the same
  cache-only directory files using the Tor Browser app's bundled Tor binary.
- Fresh proof
  `results/torfast-browser-compare-20260620T200118/torfast-browser-compare.json`
  ran `2` rotated cycles against `https://check.torproject.org/` and
  `https://www.torproject.org/` with bundled cold, bundled seeded, local cold,
  and local seeded.
- Median Tor boot was `17.002s` for bundled cold, `2.541s` for bundled seeded,
  `9.132s` for local cold, and `2.610s` for local seeded. So the bundled seed
  path kept the startup win while using the official bundled Tor binary.
- On `https://check.torproject.org/`, bundled seeded beat every other profile:
  raw page load `1229ms` versus bundled cold `1274ms`, local cold `1590ms`,
  and local seeded `3036ms`; launch+load `3770ms` versus bundled cold
  `18276ms`, local cold `10722ms`, and local seeded `5646ms`.
- On `https://www.torproject.org/`, bundled seeded kept the best end-to-end
  launch+load by a wide margin: `7453ms` versus bundled cold `21227ms`, local
  cold `14954ms`, and local seeded `13690ms`. Raw page load was slightly slower
  than bundled cold (`4912ms` versus `4225ms`) but still much better than local
  seeded (`11080ms`).
- The saved bundled seeded runs kept the expected proxy prefs, Tor check-page
  success title, `IsolateSOCKSAuth`, and copied only documented cache files.
- Strongest current conclusion: the best proven default path is now official
  Tor Browser plus bundled Tor with shared cache-only seed reuse. It is faster
  than the local seeded lab build on both proof targets and removes the need to
  rely on a separate local Tor binary for the default user flow.

Broader bundled-seeded target-pack proof:

- `tools/run_torfast_browser_compare.py` now has named target packs. The new
  `broader` pack adds `https://www.torproject.org/download/` so we can test a
  third page class without hand-assembling target lists each time.
- Fresh proof
  `results/torfast-browser-compare-20260620T202926/torfast-browser-compare.json`
  ran `2` rotated cycles against `https://check.torproject.org/`,
  `https://www.torproject.org/`, and `https://www.torproject.org/download/`
  with bundled cold, bundled seeded, local cold, and local seeded.
- Bundled seeded stayed best on end-to-end first-use launch+load for all three
  targets:
  `3849ms` on Tor check, `7253ms` on homepage, and `8012ms` on download,
  versus bundled cold `20683ms` / `25263ms` / `23425ms`.
- Bundled seeded also beat local seeded on all three page-only medians:
  Tor check `1235ms` versus `1308ms`, homepage `4639ms` versus `4928ms`, and
  download `5398ms` versus `5549ms`.
- The remaining raw page-load gap is narrower and more specific now:
  on the download page, bundled seeded still lost to bundled cold
  (`5398ms` versus `4329ms`) and local cold (`5398ms` versus `4881ms`) even
  though its startup win kept launch+load far ahead. That makes the download
  page the clearest remaining browser-phase bottleneck target.
- Stronger map of the problem: the current default path is already the best
  proven end-to-end user flow, and the next speed work should target the
  download-page raw load phase specifically rather than Tor bootstrap.

Download-page lab diagnosis with browser net logs:

- `tools/run_torfast_browser_compare.py` now exposes the same default-off
  browser diagnostics used by `tools/run_browser_compare.py`:
  `--browser-net-log` and `--browser-serial-http-connections`. They are for
  lab diagnosis only and do not change the default product path.
- Focused diagnostic proof
  `results/torfast-browser-compare-20260620T211004/torfast-browser-compare.json`
  ran `2` download-page cycles with bundled cold, bundled seeded, local cold,
  and local seeded while saving Firefox `MOZ_LOG` network traces and forcing
  serialized browser HTTP requests.
- This lab mode is not comparable to the normal proof medians, but it makes
  the browser waterfall much easier to read. In that run, bundled seeded still
  beat bundled cold on launch+load (`24159ms` versus `76151ms`) and raw load
  (`19777ms` versus `29172ms`).
- The most useful new evidence is phase placement: bundled seeded navigation
  `responseStart` stayed under `1s` (`~875ms` median), while the large delay
  lived later between DOM content and final load (`~13692ms` median
  DOM-to-load gap). Bundled cold showed the same shape with a larger tail
  (`~20592ms` DOM-to-load gap).
- The slowest resources were consistently secondary static assets rather than
  the main HTML response: fontawesome social PNGs, the Tor Browser product
  image `TBA10.0.png`, download-page SVGs such as `stay-safe.svg` and
  `get-connected.svg`, plus the favicon. That strongly suggests the remaining
  download-page bottleneck is a browser-side asset waterfall after the initial
  document fetch, not Tor bootstrap or first-byte time.
- `tools/analyze_torfast_browser_compare.py` now also reads page-resource
  browser net-log cache signals when `browser_net_log` files are present. On
  the same serialized diagnostic proof
  `results/torfast-browser-compare-20260620T211004/torfast-browser-compare.json`,
  bundled seeded showed `67` page-resource net-log rows on
  `https://www.torproject.org/download/`, with `63` `HTTP/1.1` `200` rows,
  `0` `304` rows, `67` new cache entries, `0` must-validate-yes rows, and
  `63` `no mandatory validation requirement` rows. Bundled cold and local cold
  showed the same first-use shape: all page-resource cache entries were new and
  `304` never appeared.
- That rules out ordinary HTTP cache revalidation as the main cause of the
  remaining first-use `download/` slowdown in this window. The next safe work
  should stay focused on request ordering and browser slot/asset-waterfall
  behavior for fresh `200` responses, not on cache-validation tweaks.

Download-page normal-mode resource analysis:

- `tools/analyze_torfast_browser_compare.py` now reads
  `torfast-browser-compare.json` directly and prints navigation phase medians,
  resource-tail summaries, top load-tail resources, and per-resource deltas
  between bundled-seeded and a cold baseline.
- Running it against the broader proof with
  `python3 tools/analyze_torfast_browser_compare.py results/torfast-browser-compare-20260620T202926/torfast-browser-compare.json --target https://www.torproject.org/download/ --top 8`
  produced `tmp/torfast-download-analysis-20260620T202926.md`.
- This stronger normal-mode view changes the diagnosis slightly: bundled seeded
  was still worse than bundled cold on raw `download/` load (`5398ms` versus
  `4329ms`), but the analyzer showed the extra time landed earlier in the page
  phase, not later. Its median navigation `responseStart -> DOMContentLoaded`
  grew to `2683ms` versus bundled cold `1508ms`, while `DOM -> load` got
  shorter (`1425ms` versus `1792ms`).
- The same download-page asset families still dominated both profiles:
  `stay-safe.svg`, `get-connected.svg`, and the Font Awesome social PNGs. But
  in bundled seeded several Font Awesome resources had larger total durations
  even while ending earlier relative to final load; for example bundled seeded
  `github.png` was `2633ms` versus bundled cold `1858ms`, and
  `linkedin.png` was `2492ms` versus `1842ms`.
- Best current conclusion: the remaining bundled-seeded raw-load loss on
  `download/` is not a simple late-tail problem anymore. It looks more like an
  earlier browser fetch/queue phase issue on secondary assets, so the next safe
  experiments should focus on browser resource start/queue behavior rather than
  more general-circuit waits.
- Follow-up focused proof
  `results/torfast-browser-compare-20260620T214055/torfast-browser-compare.json`
  plus
  `tmp/torfast-download-analysis-20260620T214055.md`
  showed that this phase split is not stable enough to treat as a final root
  cause yet. In that `3`-run `download/`-only window, bundled seeded still won
  launch+load (`9667ms` versus bundled cold `26340ms`) but lost raw load again
  (`6980ms` versus `6764ms`) and was slower across all three page phases:
  response start (`1650ms` versus `867ms`), `responseStart -> DOM`
  (`2383ms` versus `1983ms`), and `DOM -> load` (`3800ms` versus `3183ms`).
- The consistent part across both analyses is the asset family, not the exact
  phase split. The repeated heavy rows were still the same download-page SVGs,
  Font Awesome social PNGs, and Tor Browser product imagery, and in the
  focused run several bundled-seeded resources were `~1.1s` to `~1.4s` slower
  than bundled cold (`twitter.png`, `github.png`, `instagram.png`,
  `linkedin.png`, `mastodon.png`, and `stay-safe.svg`).
- The analyzer now includes per-resource `fetchStart -> requestStart` phase
  deltas, which makes the focused proof much clearer. Bundled seeded had
  higher median fetch-to-request time across all `download/` resources
  (`1633ms` versus bundled cold `1150ms`) and more resources queued for at
  least `1000ms` (`72` versus `67`).
- The analyzer now also includes `Resource Families` and `Family Delta`.
  Running that on the normal proof
  `results/torfast-browser-compare-20260620T202926/torfast-browser-compare.json`
  shows the bundled-seeded loss is concentrated in a few same-size families,
  not broader payload growth: `product window png` added `+1441.695ms`
  duration with `+1708.367ms` later request start and `0 KiB` encoded-size
  delta; `site image` / `tor-logo@2x.png` added `+908.352ms`,
  `+1208.358ms`, and `0 KiB`; `tb85 image` added `+708.348ms`,
  `+1175.024ms`, and `0 KiB`; and `fontawesome png` added `+500.010ms`,
  `+716.681ms`, and `0 KiB`.
- That same family view also sharpens what is *not* broken: `download png` was
  faster in bundled seeded (`-608.346ms` duration), while `download svg` was
  mixed — later request discovery (`+1008.353ms`) but faster on-connection
  work (`-425.009ms` duration). So the remaining raw `download/` loss is
  mostly later discovery / slot entry for secondary same-origin asset families,
  not larger responses or a broad transfer-rate regression.
- The new `Blocker Family Cascades` table makes that later-discovery loss more
  concrete. In the same normal proof, bundled seeded still showed
  `download svg -> fontawesome png` as the dominant cross-family cascade
  (`20` blocker occurrences across the two SVGs), while its heaviest
  self-cascade was `fontawesome png -> fontawesome png` (`66` occurrences).
  The seeded path also kept `fontawesome png -> product window png`
  (`11` occurrences) and `fontawesome png -> tb85 image` (`8` occurrences),
  which matches the stronger family-delay rows for `TBA10.0.png`,
  `tb85@2x.png`, and the Font Awesome PNG set.
- That narrows the next safe product-path investigation again: focus on why
  those early same-origin PNG families enter the six-slot queue later and then
  hold it long enough to cascade into the Font Awesome/self-blocker stage,
  rather than spending more time on generic transfer, payload-size, or
  cache-validation theories.
- Fresh live proof
  `results/torfast-browser-compare-20260621T014627/torfast-browser-compare.json`
  adds the first page `Resource Discovery` snapshot to the normal product path.
  Treat its speed numbers as a noisy n=`1` window, but the page-structure
  evidence is useful: `fontawesome png`, `tb85 image`, `source sans font`, and
  `source code font` were all CSS-only discoveries from
  `static/css/bootstrap.css`, while `download svg`, `TBA10.0.png`, and
  `tor-logo@2x.png` were direct DOM `<img>` resources.
- That means the remaining `download/` queue story is now narrower: early
  CSS-driven assets and fonts are discovered through `bootstrap.css`, then the
  later direct DOM images (`TBA10.0.png`, `tor-logo@2x.png`, `stay-safe.svg`,
  `get-connected.svg`) enter the same-origin `HTTP/1.1` slot queue afterward.
  The next safe product-path work should inspect why those bootstrap.css-driven
  assets occupy the queue long enough to delay the later direct-image stage.
- The same live proof now also prints `CSS Discovery Gates`, which measures how
  long after `bootstrap.css` finishes those CSS-only resources become fetchable
  and then requestable. In bundled seeded, `fontawesome png` had median
  fetch-start only `+16.667ms` after `bootstrap.css` response end, but median
  request-start still lagged by `+1066.688ms`; `tb85 image` was similar at
  `+883.351ms`, while `source sans font` and `source code font` were
  `+433.342ms`. That makes the next bottleneck more precise: the remaining
  delay is not just stylesheet transfer, but the post-stylesheet stage before
  the browser actually issues many CSS-driven same-origin requests.
- The live proof also now prints `Variant Swaps`, and it confirms a real
  duplicate-load mechanism on the page: every normal product profile loaded
  `download png` resources (`get-connected@3x.png`, `stay-safe@3x.png`) even
  though the final discovered DOM pointed at the matching `download svg`
  resources (`get-connected.svg`, `stay-safe.svg`).
- A direct source fetch of the live first-party page assets explains why. The
  current `fallback.js` contains explicit PNG→SVG rewrites for the same
  illustration containers and icon classes:
  `$(obj).find('img').attr('src')`, then
  `svgSrc = svg.replace(/png/g,"svg").replace(/@3x/,"")`, then
  `$(obj).find('img').attr("src",svgSrc)`. It also rewrites generic `-png`
  classes. So the remaining `download/` slowdown is not just passive browser
  queuing: the page actively causes duplicate illustration fetches plus a
  second direct-image stage after initial PNG discovery.
- A new lab-only blocker proof
  `results/torfast-browser-compare-20260621T024200/torfast-browser-compare.json`
  used the new `--browser-block-url-substring /static/js/fallback.js`
  experiment to cancel those first-party rewrite requests. The benchmark JSON's
  new `browser_request_blocker` evidence logged two cancelled
  `fallback.js?h=8a716acd` requests, and the final discovered DOM stayed on the
  PNG illustrations instead of switching to the SVG variants.
- That confirms `fallback.js` is causal for the variant swap, but it is not a
  win to block it. Compared with the matching baseline proof
  `results/torfast-browser-compare-20260621T023816/torfast-browser-compare.json`,
  bundled seeded raw `download/` load got worse (`2837.930ms` → `4950.691ms`,
  `+2112.761ms`), with `domContentLoadedEventEnd` also landing later
  (`1633.366ms` → `2983.393ms`).
- The reason is now clearer too: in the baseline run the initial PNG
  illustration entries were effectively zero-byte placeholders while the later
  SVG replacements cost about `22–30KiB` each and finished in roughly
  `1.1–1.2s`. After blocking `fallback.js`, the page stayed on the heavier PNGs
  and those same illustration requests became real `56–84KiB` transfers that
  each took about `3.0s` under the normal six-slot same-origin queue.
- Fresh net-log + activity-probe proof now makes that placeholder behavior
  explicit. In
  `results/torfast-browser-compare-20260621T025601/torfast-browser-compare.json`,
  the new `Pre-Network Cancels` analyzer section shows bundled seeded
  `download png -> download svg` with `2` resources and zero-byte timing, while
  the browser activity probe records only `http-on-stop-request` for those PNG
  channels — no `http-on-examine-response` and no socket-port evidence. That
  means the fast path is not "download PNG then download SVG"; it is "create
  PNG channels, cancel them before any response/socket work, then fetch SVG".
- The matching blocked proof
  `results/torfast-browser-compare-20260621T030123/torfast-browser-compare.json`
  shows the opposite shape. Its `Pre-Network Cancels` section only contains the
  request-blocked `fallback.js` rows, while the `download png` resources now
  have `http-on-examine-response`, socket-port evidence, and real `56–84KiB`
  transfers. Treat the raw load deltas across those n=`1` runs as noisy, but
  the lifecycle change itself is strong evidence.
- Updated guidance: keep the request blocker lab-only and default-off. The
  safe next work is not "block fallback.js", but rather explain why the normal
  product path sometimes lets the early PNG stage and the later SVG/CSS-driven
  stage occupy the same-origin queue so unevenly across runs. The strongest
  current browser-side hypothesis is now narrower: when early same-origin
  script discovery gets `fallback.js` in quickly enough, those PNG image
  channels are canceled before socket/response work; when it does not, the
  browser pays for the heavier PNG transfers directly.
- The top bundled-seeded losses all classified as `start/queue`, not response
  wait: for example `stay-safe.svg` added `1250ms` of fetch-to-request time
  versus only `100ms` more wait and `67ms` more receive; `github.png` and
  `twitter.png` showed the same pattern, with roughly `1.2s` to `1.4s` extra
  fetch-to-request time dominating their slower total duration.
- Same-origin slot-pressure proof is now explicit too. The regenerated
  `tmp/torfast-download-analysis-20260620T214055.md` shows the repeated heavy
  `download/` assets are all `http/1.1` and consistently hit a same-origin
  active-in-queue ceiling of `6`, matching normal browser per-host connection
  slot pressure. Bundled seeded did not lose because it used fewer slots; it
  lost because under the same `6`-active cap, those slots stayed occupied
  longer and kept later assets queued longer.
- The new blocker-chain section makes the queue owners concrete. In the focused
  bundled-seeded proof, early same-origin blockers repeatedly included
  `SourceSansPro-Bold.ttf`, the Font Awesome WOFF files
  (`fa-regular-400.woff2`, `fa-solid-900.woff2`, `fa-brands-400.woff2`),
  the large `tb85@2x.png` image, and `TBA10.0.png`. Later in the page, the
  queued Font Awesome social PNGs then became blockers for `get-connected.svg`
  and `stay-safe.svg`, which explains the visible cascade into the final
  download-page assets.
- That narrows the next proof target further: focus on which earlier same-origin
  assets are holding those six slots open longer in bundled seeded, rather than
  searching for more general circuit-ready or boot-time waits.
- Updated next-step guidance: keep launch+load default behavior as-is, and
  focus the next safe experiments on why those early same-origin font/image
  blockers stay active longer in bundled seeded, rather than more Tor circuit
  wait knobs.

Browser per-host slot-cap proof:

- A new lab-only proof
  `results/torfast-browser-compare-20260620T230127/torfast-browser-compare.json`
  plus
  `tmp/torfast-download-analysis-20260620T230127.md`
  raised Tor Browser's
  `network.http.max-persistent-connections-per-server` to `10` for all
  compared profiles on the focused `download/` target.
- This is not a shippable product default because it changes browser networking
  prefs and likely fingerprint surface. But it is strong causal evidence.
- Under the cap-`10` lab override, bundled seeded raw `download/` load dropped
  from the prior focused proof's `6980ms` to `3007ms`, and launch+load dropped
  from `9667ms` to `5624ms`. In that same run it beat bundled cold
  (`4284ms` raw, `29334ms` launch+load) and local seeded (`3252ms` raw,
  `5833ms` launch+load).
- The analyzer confirms why: bundled seeded `queued >=1000ms` resources fell
  from `72` in the prior focused proof to `11` under the cap-`10` override,
  and median `fetchStart -> requestStart` dropped from `1633ms` to `500ms`.
- A follow-up cap-`7` proof
  `results/torfast-browser-compare-20260620T231237/torfast-browser-compare.json`
  plus
  `tmp/torfast-download-analysis-20260620T231237.md`
  shows this is not an all-or-nothing effect. Raising the cap by only `+1`
  already cut bundled-seeded raw `download/` load from `6980ms` to `4051ms`,
  cut `queued >=1000ms` resources from `72` to `23`, and cut median
  `fetchStart -> requestStart` from `1633ms` to `675ms`.
- Cap `10` still helps more than cap `7`, but the slope matters: the big jump
  in performance happens immediately once the default slot cap is relaxed a
  little, which is strong evidence that the normal-cap queue boundary is the
  primary bottleneck rather than a minor side effect.
- Strongest current interpretation: the remaining `download/` regression in the
  normal product path is heavily driven by the browser's per-host slot limit
  interacting with a small set of early same-origin blockers. The product work
  should now concentrate on why those early assets stay active longer under the
  standard slot cap, not on more Tor bootstrap or general-circuit waits.

Bundled-seeded multi-circuit gate check:

- `tools/run_torfast_browser_compare.py` can now add bundled-seeded profiles
  that wait for at least `N` built GENERAL/CONFLUX_LINKED circuits before
  browser launch.
- A focused one-target proof
  `results/torfast-browser-compare-20260620T204307/torfast-browser-compare.json`
  looked promising on `https://www.torproject.org/download/`: waiting for `2`
  built general circuits cut bundled-seeded raw load from `8095ms` to
  `4452ms` and launch+load from `10734ms` to `7852ms` in that narrow window.
- But the broader promotion gate rejected it. Follow-up proof
  `results/torfast-browser-compare-20260620T205032/torfast-browser-compare.json`
  ran `2` rotated cycles across Tor check, homepage, and download with bundled
  cold, bundled seeded, bundled seeded plus `2` general circuits, local cold,
  and local seeded.
- A newer focused net-log proof
  `results/torfast-browser-compare-20260621T032906/torfast-browser-compare.json`
  now makes the rejection stronger on `https://www.torproject.org/download/`.
  In that `n=1` window, bundled seeded plus `2` general circuits was much worse
  than normal bundled seeded on raw load (`10526.762ms` versus `4439.388ms`).
  The new `Pre-Network Cancels` section also lost the cheap `download png ->
  download svg` shape that the faster bundled-seeded path showed, while
  `Variant Swaps` still remained and `CSS Discovery Gates` got worse.
- Against the current bundled-seeded default, the `2`-circuit profile was worse
  on Tor check (`5710ms` launch+load versus `3904ms`) and worse on download
  (`9436ms` versus `8292ms`). It only improved homepage raw load
  (`4761ms` versus `5284ms`), but even there launch+load got worse
  (`8383ms` versus `7851ms`) because of the extra wait.
- Conclusion: keep the minimum-general-circuit gate lab-only. It can help a
  single heavy page in some windows, but newer proof contradicts the early
  promising slice and it is not robust enough to replace the current
  bundled-seeded default path.

Arti stream-scheduler burst lab check:

- The browser runner now wires a lab-only
  `TORFAST_STREAM_SCHEDULER_BURST` override through both direct Arti runs and
  interleaved A/B profiles via `--arti-stream-scheduler-burst` and
  `--extra-arti-stream-scheduler-burst`. The default path is unchanged when the
  knob is unset, and unit coverage now checks env export, source detection, and
  interleaved profile metadata.
- Focused proof
  `results/browser-compare-20260621T035356/browser-compare.json`
  compared baseline Arti against `arti_release_browser_schedburst2` on
  `https://www.torproject.org/download/` in one cold interleaved window.
- `schedburst2` was clearly worse: boot `28.630s` versus `23.320s`, raw load
  `7069.494ms` versus `4117.993ms`, response start `1916.705ms` versus
  `950.019ms`, and DOM-to-load `2550.051ms` versus `1450.029ms`.
- The shared analyzer now also prints the same browser-side swap/cancel proof
  for plain `browser-compare.json` runs. In that result, baseline Arti and
  local C Tor both still show `download png -> download svg` in
  `Pre-Network Cancels`, but `arti_release_browser_schedburst2` disappears from
  `Pre-Network Cancels` and remains only in `Variant Swaps`, with much later
  PNG request timing (`4050.081ms` median request start versus `1100.022ms` for
  baseline Arti). That is strong evidence that the burst cap breaks the cheap
  placeholder-cancel path instead of helping it.
- The analyzer classified it as `boot slower, boot directory, resource queue,
  slow onion/data gap`. Its late same-origin queue cluster also got heavier:
  baseline Arti's main queue cluster centered on `TBA10.0.png`, `tor-logo@2x`,
  and `fallback.js`, while `schedburst2` still carried both `download png`
  and `download svg` assets in the same cluster (`stay-safe@3x.png`,
  `get-connected@3x.png`, `stay-safe.svg`, `get-connected.svg`).
- Conclusion: keep stream-scheduler burst lab-only and default-off. This
  established-stream burst cap does not improve the current `download/` queue
  problem and is not a promotion candidate.

Focused replay of the current broad directory combo:

- Fresh focused replay
  `results/browser-compare-20260621T045132/browser-compare.json`
  reran the current broad directory combo
  (`arti_release_browser_mdsrcspreadpendingearlyusable_loadaware_partialretrychunk`)
  against plain Arti and local C Tor on only
  `https://www.torproject.org/download/`, cold interleaved, with browser net
  logs enabled.
- In that `n=1` window, plain Arti fell into a catastrophic queue tail
  (`60720.938ms` raw load, `60701.214ms` response-to-DOM), while the directory
  combo stayed fast (`4214.459ms` raw load, `1733.368ms` response-to-DOM) and
  even beat local C Tor's raw load in the same slice (`5778.331ms`).
- The new browser-side proof explains the win: plain Arti lost the fast
  `download png -> download svg` placeholder-cancel path and only showed
  cancelled site-JS rows, while the directory combo preserved `2` pre-network
  `download png` cancels with a normal swap window (`fallback.js` end at
  `2183.377ms`, first PNG cancel stop at `2666.026ms`, first SVG request at
  `3383.401ms`).
- A short confirmation replay
  `results/browser-compare-20260621T045406/browser-compare.json`
  raised this from a one-off slice to a more useful focused proof. Across `2`
  cold runs on the same target, the directory combo beat plain Arti on summary
  median raw load (`5847.812ms` versus `6293.572ms`), beat plain Arti on max
  raw load (`6071.778ms` versus `7028.269ms`), and reduced late queue pressure
  (`paired median max queue delta -1375.027ms`).
- The cancel/swap evidence stayed stronger too. Across those `2` runs, the
  directory combo kept `4/4` `download png` resources in `Pre-Network Cancels`,
  while plain Arti only kept `1/4` and local C Tor kept `0/4`. The combo's
  `Variant Swap Windows` rows show consistent `fallback.js` completion followed
  by early PNG cancel (`18.000ms` and `351.353ms` later) before the SVG request
  (`2000.040ms` later in both runs). Plain Arti had one run with no download
  PNG cancel at all and one run with only a single late cancel.
- Conclusion: this remains the strongest current lab-only Arti candidate for
  the `download/` target. It appears to preserve the fast placeholder-cancel
  path more reliably than plain Arti while improving load and queue tail. It is
  still not promotion-safe yet because the focused `2`-run replay was only
  `1/2` paired load wins against plain Arti, page-only median still lost to
  local C Tor (`5847.812ms` versus `4377.153ms`), and boot was slower than
  plain Arti in the confirmation window (`16.114s` versus `11.045s`).
- Next source lane: use this directory combo as the lab baseline and compare a
  narrow first-byte/response-start tweak against it, while requiring the new
  `Variant Swap Windows` proof to keep the `download png -> download svg`
  pre-network cancel path intact.

Focused SOCKS CONNECT hedge check on the current broad directory combo:

- `tools/run_browser_compare.py` now has a dedicated same-window profile for
  the current directory combo plus a hostname SOCKS CONNECT hedge:
  `--extra-arti-dir-microdesc-source-spread-pending-spread-early-usable-load-aware-partial-retry-chunking-socks-connect-hedge-ms`.
  This lets us compare plain Arti, the current combo baseline, and the same
  combo plus a narrow first-byte/response-start tweak in one interleaved
  window.
- Fresh focused replay
  `results/browser-compare-20260621T051651/browser-compare.json` compared plain
  Arti, the current combo baseline, the current combo plus a `500ms` connect
  hedge, and local C Tor on only `https://www.torproject.org/download/`, cold
  interleaved, with browser net logs enabled.
- In this window the current combo baseline lost badly to plain Arti: plain
  Arti median raw load was `4007.304ms`, while the combo baseline was
  `7151.197ms`. Local C Tor was `4638.233ms`.
- The combo plus `500ms` hedge recovered some of that loss, but not enough:
  median raw load improved to `5938.660ms`, response start improved to
  `650.013ms` (faster than plain Arti `866.684ms` and local C Tor
  `1091.688ms`), and response-to-DOM improved to `1708.367ms` versus combo
  baseline `2216.711ms`.
- But the hedge profile still lost to plain Arti and local C Tor overall
  because DOM-to-load stayed much worse (`3566.738ms` versus plain Arti
  `1733.368ms` and local C Tor `1750.035ms`). Its worst run still turned into a
  browser queue tail (`8321.070ms` load, `5450.109ms` DOM-to-load,
  `5516.777ms` max queue, top queued `github.png`).
- The browser-side cancel/swap proof stayed intact, so the early placeholder
  path was not the issue in this replay. The combo plus hedge kept `4/4`
  `download png` resources in `Pre-Network Cancels`, earlier than the combo
  baseline (`850.017ms` median loaded-request start versus `1150.023ms`), and
  both combo profiles kept `4/4` download-PNG pre-network cancels.
- There was no mechanism proof. The analyzer emitted no `Torfast SOCKS Connect
  Hedges` section, and the saved proxy logs had no
  `torfast socks timing connect hedge` lines. So the `500ms` hedge did not
  actually launch in this replay.
- Conclusion: keep the combo-plus-hedge profile lab-only and do not promote it.
  It can move response start earlier and improve the bad combo baseline, but in
  this focused replay it still lost to plain Arti and did so without any actual
  hedge event. The next source lane should require a first-byte tweak that
  proves it fired, or shift back toward the remaining DOM-to-load/resource-queue
  tail rather than just earlier response start.

Focused SOCKS CONNECT soft-timeout check on the current broad directory combo:

- `tools/run_browser_compare.py` now also has a dedicated same-window profile
  for the current directory combo plus a non-onion SOCKS CONNECT soft-timeout
  combo:
  `--extra-arti-dir-microdesc-source-spread-pending-spread-early-usable-load-aware-partial-retry-chunking-socks-connect-soft-timeout-combo MS:ATTEMPTS`.
- Clean focused replay
  `results/browser-compare-20260621T053131/browser-compare.json`
  compared plain Arti, the current combo baseline, the combo plus
  `5000ms + 3 attempts`, and local C Tor on only
  `https://www.torproject.org/download/`, cold interleaved, with browser net
  logs enabled.
- In that clean window, the combo baseline beat plain Arti on page load
  (`4951.164ms` versus `5616.954ms`), and the combo plus
  `5000ms + 3 attempts` was best of all four profiles at `4454.995ms`, beating
  local C Tor `6312.398ms` and cutting plain Arti by `1161.960ms` on paired
  median load.
- The browser-side swap proof also improved in that same clean window. The
  combo baseline lost the pre-network placeholder-cancel path entirely (`0/4`
  `download png` resources in `Pre-Network Cancels`), while the soft-timeout
  combo kept `3/4` and moved the median loaded-request start earlier
  (`966.686ms` versus combo baseline `2450.049ms` in `Variant Swaps`).
- The phase win did not look like a first-byte mechanism proof. The
  soft-timeout combo was only slightly slower than the combo baseline at
  response start (`908.351ms` versus `833.350ms`) and slightly slower at
  response-to-DOM (`1783.369ms` versus `1708.368ms`), but it won much more in
  DOM-to-load (`1758.369ms` versus `2408.382ms`). So the gain in this clean
  replay came mainly from a shorter late page phase, not from an earlier first
  byte.
- There is still no direct soft-timeout mechanism proof. The analyzer printed
  no `Torfast SOCKS Connect Retries` section, and direct grep over both focused
  soft-timeout result bundles found no `connect soft timeout`, `connect retry`,
  or `connect retry succeeded` lines.
- Supporting replay
  `results/browser-compare-20260621T053428/browser-compare.json`
  is useful but not promotable because plain Arti had a failed run in that
  window. Even so, the combo plus `5000ms + 3 attempts` still looked best on
  raw page load among successful runs (`3796.086ms` versus combo baseline
  `4930.640ms`, local C Tor `3934.304ms`, and plain Arti successful-run median
  `4162.867ms`), which keeps this lane interesting.
- Broader same-window repeat
  `results/browser-compare-20260621T054045/browser-compare.json`
  then compared plain Arti, the current combo baseline, the combo plus
  `5000ms + 3 attempts`, and local C Tor across `3` cold runs on
  `https://check.torproject.org/`, `https://www.torproject.org/`, and
  `https://www.torproject.org/download/`, while keeping full proxy log tails.
- That broader repeat changes the ranking. Plain Arti had catastrophic homepage
  and download tails (`19240.865ms` and `18369.654ms` medians). The current
  combo baseline was strong on all three targets, beating local C Tor on check
  (`1491.948ms` versus `2019.977ms`), homepage (`3809.543ms` versus
  `4251.186ms`), and download (`3861.309ms` versus `4665.985ms`) while also
  booting faster (`12.874s` versus local C Tor `22.611s`).
- The soft-timeout add-on did not hold up as the better broad candidate. It won
  the homepage median (`3304.924ms` versus combo baseline `3809.543ms`), but it
  lost check (`1796.833ms` versus `1491.948ms`), lost download
  (`4945.728ms` versus `3861.309ms` and local C Tor `4665.985ms`), and booted
  slower than the combo baseline (`17.134s` versus `12.874s`).
- The mechanism gap still stands. Direct grep over the focused and broader
  soft-timeout result bundles found no `connect soft timeout` lines for the
  combo-plus-soft-timeout profile. The broader bundle did include ordinary
  `connect retry ... soft_timeout_attempts=2` rows, but those belong to the
  default retry path rather than the explicit `5000ms + 3 attempts` add-on.
- Conclusion: keep the combo-plus-soft-timeout profile lab-only and demote it
  from “next baseline candidate” back to “mixed clue.” The broader repeat says
  the current directory combo itself is the stronger lab-only baseline right
  now, while the soft-timeout add-on remains unproven and broader-target worse
  despite one clean focused `download/` win.

Directory-combo simplification: chunking without load-aware:

- `tools/run_browser_compare.py` now also has a dedicated same-window profile
  for the directory source-spread/pending-spread/early-usable combo plus
  partial-response retry chunking but without load-aware selection:
  `--extra-arti-dir-microdesc-source-spread-pending-spread-early-usable-partial-retry-chunking`.
- Clean no-net-log 4-profile gate
  `results/browser-compare-20260621T060154/browser-compare.json`
  compared plain Arti, `mdsrcspreadpendingearlyusable_loadaware`, the old full
  combo (`..._loadaware_partialretrychunk`), and local C Tor across `3` cold
  runs on Tor check, homepage, and download.
- That gate showed the current full combo was not the stable simplification
  winner in that window. `mdsrcspreadpendingearlyusable_loadaware` beat the old
  full combo on check (`1399.872ms` versus `1419.984ms`) and download
  (`4919.950ms` versus `5292.495ms`), but still lost homepage
  (`5389.143ms` versus full combo `4364.879ms`) and booted much slower
  (`28.969s` versus `12.030s`). So the old full combo still had the better
  cold-start shape there even though load-aware-only looked better on one large
  page.
- Clean no-net-log 5-profile gate
  `results/browser-compare-20260621T061212/browser-compare.json`
  then added the new no-loadaware chunked profile
  `arti_release_browser_mdsrcspreadpendingearlyusable_partialretrychunk`.
- That new no-loadaware chunked profile is not the isolated winner we want. It
  beat plain Arti on all `3` targets (`1595.041ms` vs `2321.196ms` on check,
  `4499.823ms` vs `4474.380ms` roughly tied on homepage, and `6042.809ms` vs
  `7934.175ms` on download), but it still lost to local C Tor on all `3`
  targets and lost clearly to the load-aware-only profile on download
  (`6042.809ms` versus `3432.504ms`).
- In that same 5-profile window, load-aware-only was the strongest broad page
  loader: check `2057.194ms`, homepage `4528.386ms`, download `3432.504ms`,
  and boot `11.170s`. It even beat local C Tor on download in that slice
  (`3432.504ms` versus `4117.903ms`).
- But the two clean broad gates disagree sharply on load-aware-only itself:
  `20260621T060154` had load-aware-only booting in `28.969s` and losing the
  homepage/download broad gate, while `20260621T061212` had it booting in
  `11.170s` and looking best overall. That instability is strong rejection
  evidence for promotion right now.
- Conclusion: chunking without load-aware does not isolate the broad win.
  Treat it as a negative simplification lane. The next source lane should focus
  on why `mdsrcspreadpendingearlyusable_loadaware` swings so widely between
  clean broad windows, or derive a guard that keeps its strong windows without
  the severe boot/homepage/download regressions seen elsewhere.

General-circuit readiness gate check:

- The same comprehensive proof added
  `local_c_tor_browser_seeded_general_circuit`, which waits for a built
  GENERAL/CONFLUX_LINKED circuit after Tor boot `100%` before launching the
  browser. Median extra post-boot wait was only `0.381s`, for a total
  circuit-ready time of `2.881s`.
- This gate is not strong enough to promote. On
  `https://check.torproject.org/`, it made end-to-end launch+load slightly
  worse (`4255ms` versus `4000ms` for plain seeded) and raw page load was
  effectively flat-to-worse (`1374ms` versus `1350ms`). On
  `https://www.torproject.org/`, it helped somewhat (`7559ms` versus `8273ms`
  launch+load, `5059ms` versus `5623ms` raw load).
- Because the effect is mixed across targets and the win is not clearly robust,
  we should not make general-circuit gating the default product path yet.

Fixed post-boot wait sweep:

- The focused runner can now add seeded fixed-wait variants in the same rotated
  window with `--extra-seeded-post-boot-wait-seconds`.
- Fresh proof
  `results/torfast-browser-compare-20260620T194446/torfast-browser-compare.json`
  compared plain seeded versus seeded `+250ms`, `+500ms`, and `+1000ms`
  post-boot waits across `2` cycles on `https://check.torproject.org/` and
  `https://www.torproject.org/`, with bundled Tor skipped to keep the window
  focused.
- Result: no fixed wait is promotable. `+250ms` and `+500ms` slightly reduced
  raw load on `check.torproject.org` but still made end-to-end launch+load
  worse than plain seeded once the extra wait was counted. On
  `https://www.torproject.org/`, both `+250ms` and `+500ms` were clearly worse
  than plain seeded on both raw load and launch+load.
- `+1000ms` is a hard reject. One `https://www.torproject.org/` run failed
  outright with a `120000 ms` navigation timeout and `NS_ERROR_UNKNOWN_PROXY_HOST`
  in the browser output tail, and even the successful run was far slower than
  plain seeded.
- Current conclusion stays the same: the best default remains plain seeded
  local C Tor with no fixed extra wait after boot.

Torfast prime proof:

- New CLI command `torfast prime` bootstraps the auto-discovered C Tor once
  (bundled Tor by default) and then stops it intentionally, refreshing the
  shared cache-only seed for later launches.
- Direct proof `results/torfast-prime-proof-20260620T172609/` shows the prime
  step reached Tor boot `100%` with `IsolateSOCKSAuth` intact and no browser
  launch, then a later one-shot `torfast launch` on the same state root used
  that cached state and booted Tor in `2.772s` before the fixed `6s` headless
  browser run completed successfully.

Cache-seeded fresh launch proof:

- Local Tor docs separate public cache files from the user `state` file:
  `cached-certs`, `cached-microdesc-consensus`, and
  `cached-microdescs(.new)` are `CacheDirectory` files, while guards and other
  persistent client state live in `DataDirectory/state`. So the new shared seed
  only copies documented cache files, not the Tor `state` file.
- Direct proof `results/torfast-default-seed-proof-20260620T174649/` shows the
  default shared seed path working across different state roots: `torfast prime`
  first refreshed the shared seed, and a later fresh `torfast launch` on a
  different state root reported `dir_cache_seed_apply.applied = true`, copied
  only cache files, kept `IsolateSOCKSAuth`, and booted Tor to `100%` in
  `2.781s` before the fixed `6s` headless browser run completed successfully.

Default setup proof:

- `python3 -m torfast install-browser` now primes by default. It reuses an
  already-verified browser install when present, then immediately refreshes the
  shared cache-only seed through `torfast prime` unless explicitly disabled
  with `--no-prime-after-install`.
- Direct proof `results/torfast-install-default-proof-20260620T182429/`
  reused the existing verified browser (`installed = false`,
  `reused_existing = true`), primed the shared seed successfully by default,
  and then a later fresh `torfast launch` on a different state root used that
  seed and booted Tor to `100%` in `2.605s` before the fixed `6s` headless
  browser run completed successfully.

Documented C Tor cold-boot knob check:

- New runner `tools/run_c_tor_boot_compare.py` compares cold C Tor boots with
  only documented client bootstrap knobs changed in torrc, while keeping
  `ClientOnly 1`, `AvoidDiskWrites 1`, `SafeLogging 1`, `ConfluxEnabled auto`,
  and `SocksPort ... IsolateSOCKSAuth`.
- The first broad 4-profile smoke
  `results/c-tor-boot-compare-20260620T175813/c-tor-boot-compare.json` looked
  promising for `ClientBootstrapConsensusAuthorityDownloadInitialDelay 0`, but
  it used a fixed profile order, so it was not strong enough to promote.
- Rotated-order follow-up A/B
  `results/c-tor-boot-compare-20260620T180256/c-tor-boot-compare.json`
  compared stock versus `ClientBootstrapConsensusAuthorityDownloadInitialDelay 0`
  across `4` cycles with order rotation. It rejected promotion: stock median
  cold boot was `16.108s`, while `authdelay0` was slower at `23.142s`.
- Rotated-order follow-up A/B
  `results/c-tor-boot-compare-20260620T180629/c-tor-boot-compare.json`
  compared stock versus `ClientBootstrapConsensusMaxInProgressTries 5` across
  `4` cycles with order rotation. It also rejected promotion: stock median was
  `13.166s`, while `maxtries5` was slower at `14.332s`.
- Conclusion for now: the lightweight cache-seed path is real and promotable,
  but these simple documented cold-bootstrap knobs are not. The next source
  lane should target stronger first-use evidence or deeper bootstrap causes,
  not ship `authdelay0` or `maxtries5` as defaults.

Torfast warm-only proof:

- `torfast warm` starts or reuses the managed C Tor service without opening the
  browser. Real proof `results/torfast-warm-proof-20260620T170259/` showed
  `torfast warm` booted Tor to `100%`, kept `IsolateSOCKSAuth`, wrote a
  managed-service record, and skipped browser launch intentionally; the
  following `torfast open` reused that exact warm Tor service and completed the
  fixed `6s` headless browser run successfully before `torfast stop` cleaned up
  the managed service.

Cold-boot partial-retry chunking proof path is now wired and verified:

- `tools/run_boot_compare.py` now exposes two cold-boot chunking profiles: a
  narrow `--extra-arti-dir-microdesc-partial-retry-chunking` A/B and a
  full-directory combo
  `--extra-arti-dir-microdesc-source-spread-pending-spread-early-usable-partial-retry-chunking`.
  Boot summaries now count `partial_retry_chunking_signals` and record
  `median_first_partial_retry_chunking_signal_seconds`, so we can prove whether
  the chunking signal actually fired without opening raw logs.
- Fresh proof `results/boot-compare-20260620T071225/boot-compare.json` ran `3`
  cold boots of default Arti, the full chunking combo, and local C Tor. The
  new signal plumbing worked: the combo recorded
  `partial_retry_chunking_signals = 2` and
  `median_first_partial_retry_chunking_signal_seconds = 18.0`, while default
  Arti and local C Tor recorded `0`.
- Speed result is a rejection for promotion. Default Arti was still best on
  cold boot with median `10.061s`, beating local C Tor `16.682s` by `6.621s`
  and beating the chunking combo `18.096s` by `8.035s`. The combo also kept
  directory trouble signals (`partial_response = 2`, `directory_timeouts = 2`,
  `directory_signal_runs = 1`), so it is not a safe default speed direction.
- This is still useful progress: the repo now has a direct cold-boot proof that
  the partial-retry chunking path can really fire in the lab, and that this
  broad combo is slower than default Arti on the current network window. The
  next source lane should keep the chunking/signal instrumentation, but shift
  optimization effort back toward a more selective retry/source-choice policy
  instead of promoting this full combo.

## 2026-06-15 status

Conflux bulk-throughput proof (first quality-preserving speed win):

- Background: every prior Conflux A/B only fetched tiny pages
  (`check.torproject.org` ~8.6KB, `www.torproject.org` ~23KB), including the
  newest undocumented run `results/conflux-compare-20260614T003311`. Those
  objects finish before multipath transfer engages, so they could never show
  Conflux's benefit. Conflux only helps sustained transfer, not first bytes.
- `tools/run_conflux_compare.py` now records transfer-phase throughput
  (`median_transfer_mbps`, `max_transfer_mbps`), computed only from the
  body-download phase after first byte (`bytes*8/1000/(total_ms-first_byte_ms)`).
  It also has a default-off `--bulk-bytes N` option that appends a fixed-size
  CDN object (`https://speed.cloudflare.com/__down?bytes=N`) and raises
  `--max-bytes`/`--timeout` to fit it. This does not weaken Tor: the torrc
  safety test still proves only `ConfluxEnabled`/`ConfluxClientUX` change, so
  path rules, hop count, guards, exit policy, and DNS are untouched.
- Main proof `results/conflux-compare-20260615T022217/conflux-compare.json`
  ran `stock,noconflux,latency,throughput` interleaved with `8` runs, `3`
  warmups, a `5MB` bulk object plus the `check.torproject.org` control. On the
  bulk object, median transfer throughput was: stock (`ConfluxEnabled auto`)
  `12.34 Mbps` (median total `4024.9ms`), throughput-UX `7.83 Mbps`
  (`7399.0ms`), noconflux `3.86 Mbps` (`11643.8ms`), latency-UX `2.01 Mbps`
  (`20916.0ms`). The stock and noconflux ranges did not overlap: stock p90
  total `5579.2ms` still beat noconflux min `9236.4ms`. On the small control
  page all profiles were within noise (`971.9..1284.9ms` median total), so
  Conflux is neutral for small pages and large for bulk, exactly as expected.
- Confirmation proof in a fresh window
  `results/conflux-compare-20260615T023424/conflux-compare.json`
  (`stock,noconflux,throughput`, same shape) reproduced it: stock
  `12.32 Mbps` / `4139.4ms`, noconflux `6.16 Mbps` / `7581.8ms`,
  throughput-UX `5.35 Mbps` / `8542.8ms`. Stock auto throughput was nearly
  identical across both independent windows (`12.34` then `12.32 Mbps`), and
  again the ranges did not overlap (stock p90 `4302.2ms` beat noconflux min
  `6560.4ms`). Stock advantage over noconflux was `3.2x` then `2.0x`.
- Two findings. First: Conflux as shipped (`ConfluxEnabled auto`, the Tor
  default) gives a large, reproducible bulk-throughput win (`~2-3x` versus
  forced `noconflux`), while preserving quality. Second: forcing
  `ConfluxClientUX` never beat `auto` for bulk, and `latency` UX was actively
  harmful (worst profile, even below `noconflux`). So the actionable result is
  to keep Conflux enabled and let UX stay `auto`; do not force a UX mode.
- Quality certified with Conflux on:
  `results/circuit-check-20260615T023935/c-tor-circuits.json` booted C Tor with
  `ConfluxEnabled auto` and passed (`ok=true`, `7` circuits checked, `0`
  circuit errors, fetch ok). Every GENERAL/CONFLUX_LINKED circuit was 3-hop,
  guard-first, Fast/Running/Valid, exit-flagged, with no relay reuse, no shared
  family, and no shared `/16` subnet. The earlier noisy `n=2` smoke test
  `results/conflux-compare-20260615T022043` is kept only as a reminder that
  small samples mislead: there stock looked far slower (`2.03 Mbps`), which the
  `n=8` runs reversed.
- Verification for this work: `python3 -m py_compile
  tools/run_conflux_compare.py`, `python3 -m unittest tests.test_conflux_compare`
  (`10` tests, including new throughput-metric cases), and
  `python3 -m unittest discover -s tests` (`235` tests) passed.

## 2026-06-13 status

HS-pool phase timing split:

- `upstream/arti/crates/tor-circmgr/src/hspool.rs` now emits info-level
  `torfast hspool timing` rows that split hidden-service stem readiness from
  final HS extension and client rendezvous readiness. The rows include only
  circuit kind, stem kind, source, and elapsed timings; they do not log target
  names or relay identities. This is instrumentation-only: no path choice,
  relay choice, stream isolation, circuit length, or browser behavior changed.
- `tools/analyze_browser_compare.py` now prints those rows in `Torfast HsPool
  Timings`, and `tools/check_arti_quality_config.py` checks that the source
  keeps the low-log split.
- Fresh one-run onion proof
  `results/browser-compare-20260613T111942/browser-compare.json`, with analyzer
  output at `results/browser-compare-20260613T111942/analysis.md`, passed
  quality. It retained `6` stem-ready rows, `4` specific-circuit-ready rows,
  and `2` client-rend-ready rows. Median stem time was `0ms` with max stem
  `714ms`; median final HS extension was `350ms`, max `376ms`, and median total
  specific-circuit time was `353.500ms`.
- This one-run sample is not promotion proof, even though Arti beat local C Tor
  on this page (`5202.762ms` load versus `6512.687ms`). The blocker row still
  says `resource queue, slow onion/data gap`, and the slow CONNECT join still
  points to hidden-service tunnel acquisition (`2302ms` and `3576ms`). Meaning:
  the next source target should stay on HS tunnel setup and active stream gaps,
  not another HS-pool grace/race/startup knob.

Selected-circuit stream/circuit gap split:

- `tools/analyze_browser_compare.py` now joins existing byte-timing relay
  receive rows into `Arti Selected-Circuit Network Evidence`. The table now
  prints `max observed stream gap ms`, `max circuit DATA gap ms`, and a
  `gap scope` label. This is analyzer-only: no Arti behavior, circuit choice,
  relay choice, path length, or browser behavior changed.
- Existing real proofs were regenerated to check the new signal. In
  `results/browser-compare-20260613T004328/analysis.md`, one base Arti download
  row had a `2204ms` observed stream gap while the selected circuit DATA gap was
  only `472ms`, labeled `stream-specific gap; circuit still active`. In
  `results/browser-compare-20260612T202757` replay output, the rejected broad
  directory combo had a `1007ms` stream gap while circuit DATA gap was only
  `367ms`, also stream-specific.
- Fresh focused proof
  `results/browser-compare-20260613T010206/browser-compare.json`, with analyzer
  output at `results/browser-compare-20260613T010206/analysis.md`, ran the
  download page for `3` cold interleaved runs with relay byte timing. Quality
  passed, but speed is rejected: Arti median load was `11396.900ms` versus
  local C Tor `4638.179ms`. The blocker row still says `slower than C Tor,
  resource queue, slow onion/data gap` and `next proof` remains `stream gap
  proof`.
- The fresh mechanism rows narrow the source target. Run `3` on `Circ 4.42
  (Tunnel 92)` had `12` late resources, `5249ms` max observed stream gap, and
  only `348ms` max circuit DATA gap. Run `2` on `Circ 4.27 (Tunnel 66)` had
  `21` late resources, `4216ms` observed stream gap, and only `247ms` circuit
  DATA gap. The scheduler table still says `no scheduler monopoly seen`. Next
  source work should inspect per-stream/resource lifecycle and browser request
  release on active selected circuits, not another whole-circuit quiet-DATA or
  selector stack.
- Follow-up analyzer replay on the same fresh proof expands
  `Torfast Bad-Health Replacement Lifecycle` with build waiters, build origin,
  page-load time left, stream start/link timing, and later-use counters. The
  run `3` bad-health replacement built `Circ 3.49`, but `build waiters` was
  `0`, all `8` stream starts were before the build, `0` stream starts were
  after it, and the replacement had `0` selected opens, `0` linked streams,
  and `0` scheduler picks. The reason is now
  `replacement missed active streams; no new stream starts after build`.
  Meaning: the current replacement is proof-only and too late for the active
  resource burst; do not promote it as a speed fix.
- Focused follow-up proof
  `results/browser-compare-20260613T011816/browser-compare.json`, with analyzer
  output at `results/browser-compare-20260613T011816/analysis.md`, reran the
  download page for `3` cold interleaved runs using the existing
  `--extra-arti-exit-select-bad-health-hedge-ms 800` profile. Quality passed.
  The hedge profile won page-load A/B against base Arti `3/3`, with paired
  median load delta `-2249.733ms`, summary median load `4564.211ms` versus
  base Arti `6813.944ms`, and local C Tor `6852.580ms`. It is not promotable:
  hedge Arti boot was `29.166s`, giving boot+load `33730.211ms` versus local
  C Tor `19480.580ms`, and the analyzer still shows stream-specific gaps on
  active selected circuits (`5023ms` observed stream gap with only `432ms`
  circuit DATA gap). Decision: keep bad-health hedge lab-only and repeat with
  boot controlled before treating it as a real speed direction.
- Boot-controlled repeat
  `results/browser-compare-20260613T012330/browser-compare.json`, with analyzer
  output at `results/browser-compare-20260613T012330/analysis.md`, used warm
  cache, shared Arti warm-cache seed, `5` interleaved download runs, relay byte
  timing, and the same `--extra-arti-exit-select-bad-health-hedge-ms 800`
  profile. Quality passed, but the prior page-load win did not hold. Against
  base Arti, the hedge profile won only `2/5` paired loads, paired median load
  delta was `+201.404ms`, summary median load was `+1264.319ms`, and max load
  was worse by `+5749.181ms` (`14371.659ms` versus `8622.478ms`). It won
  boot+load only because its measured warm boot was `0.809s` versus base
  Arti `11.674s`, not because the page path was better. The risk row flags
  `paired median slower, summary median slower, max tail worse, low paired
  wins`, and selected-circuit evidence still shows stream-specific gaps
  (`5497ms` observed stream gap with only `223ms` circuit DATA gap). Decision:
  reject bad-health hedge promotion; the next source work should target
  selected-circuit stream gaps and selector-health/capacity proof, not more
  bad-health waiting.
- Selector-health focused repeat
  `results/browser-compare-20260613T013523/browser-compare.json`, with analyzer
  output at `results/browser-compare-20260613T013523/analysis.md`, tested the
  existing `--extra-arti-exit-select-health-aware-min-assigned 2` profile on
  the same warm-cache, shared-seed, `5`-run download-page proof with relay byte
  timing. Quality passed, but speed is rejected. The gated health selector won
  only `1/5` paired loads versus base Arti, paired median load was
  `+2172.876ms` slower, summary median load was `+2713.594ms` slower, and max
  load was worse by `+8909.791ms` (`16812.711ms` versus `7902.920ms`). It also
  lost local C Tor by median load (`8424.391ms` versus `5293.815ms`). The bad
  row kept the same shape: `5056ms` observed stream gap with only `321ms`
  circuit DATA gap. Decision: reject this gated health selector for the
  download burst; the next source work should explain why the selected active
  stream stalls even when the selected circuit still has DATA activity.
- Active-cap focused repeat
  `results/browser-compare-20260613T014814/browser-compare.json`, with analyzer
  output at `results/browser-compare-20260613T014814/analysis.md`, tested the
  existing `--extra-arti-exit-select-max-active-streams 2` profile on the same
  warm-cache, shared-seed, `5`-run download-page proof with relay byte timing.
  Quality passed, but speed is rejected harder. `activecap2` won `0/5` paired
  loads versus base Arti, paired median load was `+5708.825ms` slower, summary
  median load was `+9721.581ms` slower, and max load was worse by
  `+45935.983ms` (`59471.491ms` versus `13535.508ms`). It also lost local C
  Tor by median load (`14379.552ms` versus `7359.021ms`). The worst remaining
  selected-circuit row was still stream-specific: `4879ms` observed stream gap
  with only `347ms` circuit DATA gap, and the queue summary still had
  `only selected open` rows. Decision: reject simple active-cap `2` for this
  burst; the next source work should stop retuning selector knobs and inspect
  the stream/resource stall itself.
- `tools/analyze_browser_compare.py` now also prints
  `Arti Selected Stream Gap Cross-Stream Activity`, using existing relay DATA
  timestamps to show whether other streams moved during the selected stream's
  DATA gap. The regenerated active-cap analysis shows run `5` on `Circ 1.45`:
  stream `48266` had a `1576ms` DATA gap while the same circuit delivered
  `224` other DATA cells (`104.733KiB`) across `5` other streams, with
  `no local block seen`. The regenerated selector-health analysis shows run
  `4` on `Circ 0.68`: stream `38116` had a `1372ms` DATA gap while the same
  circuit delivered `220` other DATA cells (`100.435KiB`) across `5` other
  streams. Meaning: selected stream stalls can happen while the circuit is busy,
  so the source target is per-stream/resource flow, not selector retuning,
  active cap, scheduler, SENDME/window, or whole-circuit silence.
- The analyzer now also prints
  `Arti Selected Stream Gap Resource Overlap`. It joins those selected-stream
  gaps to matched browser resources and navigation timing. This separates
  in-page gaps from later tail gaps: the active-cap run `5` selected-stream
  gap on stream `48266` matches the navigation stream, but the navigation was
  not active during that in-page DATA gap. The selector-health run `4` selected
  stream `38116` maps to `TBA10.0.png`, with the gap overlapping server wait
  (`180.086ms`) and response receive (`166.670ms`).
- The analyzer now also prints
  `Arti Selected Stream Gap Slot Pressure`. That table checks the matched
  resource's same-origin/protocol neighbors during the exact selected-stream
  gap, and now prints the matched resource's own active overlap so inactive
  matches do not overclaim. Active-cap run `5` stream `48266` had `6` active
  same-origin HTTP/1.1 slots, `11` active same-origin resources, and `7`
  resources queued at least `1000ms`, but the matched navigation resource had
  `0.000ms` active overlap, so this is same-origin page pressure, not proof
  that stream `48266` itself was waiting on a browser resource. The stronger
  live-stall row is selector-health run `4` stream `38116`: matched
  `TBA10.0.png` was active for `346.756ms` in request wait while same-origin
  HTTP/1.1 was full (`6` active slots), with `11` active resources,
  `5` queued-at-least-`1000ms` resources, `7240.090ms` request wait, and
  `883.351ms` response receive.
- The same table now separates timing confidence from stream-set confidence by
  carrying Arti `target_label`, matching the resource host, and checking whether
  the browser resource lifetime overlaps the SOCKS stream lifetime. This proves
  the active-stall row is not exactly attributable yet: selector-health run `4`
  stream `38116` has `11` joined active resources, but all `11` are
  `ambiguous` across streams `38116` and `38117` on `Circ 0.68` (`0` exact
  joins). Active-cap run `5` stream `48266` also has `11` ambiguous joined
  active resources and `0` exact joins; its old `high:3, low:8` numbers are
  only timing confidence, and the matched navigation resource was inactive. So
  the next source target is now stricter: add browser-side socket/request
  tagging, or another exact resource-to-SOCKS-stream tag, before patching active
  stream request-wait/slot pressure behavior. Do not change broad circuit
  selection or stream scheduling from this evidence alone.
- A default-off lab probe now exists for that target:
  `tools/run_browser_compare.py --browser-net-log` sets Firefox/Tor Browser
  `MOZ_LOG=timestamp,nsHttp:5,nsSocketTransport:5,nsHostResolver:3` and keeps
  per-run summaries in `browser_net_log`, with raw files under
  `browser_net_logs/`. This does not change Tor behavior; use it only to check
  whether browser-side network logs can produce exact resource-to-SOCKS-stream
  evidence.
- Live probe `results/browser-compare-20260613T031520/browser-compare.json`,
  with analyzer output at `results/browser-compare-20260613T031520/analysis.md`,
  passed quality on one `https://www.torproject.org/` run with
  `--browser-net-log --arti-log-level info,tor_proto=debug
  --arti-socks-relay-byte-timing`. Arti beat local C Tor in this one cold run
  (`4739.162ms` load vs `5566.756ms`; boot `18.217s` vs `50.641s`), but this
  is not promotion proof. The new analyzer table `Browser Net Log Resource
  Evidence` shows the browser-side part works and now reaches one step farther:
  Arti matched `36/36` performance resources to exact Firefox HTTP channel IDs,
  found parent-channel rows for `36`, and bridged `11` resources to Firefox
  proxy socket rows. Local C Tor matched `35/35`, found parent-channel rows for
  `36`, and bridged `9` resources to Firefox proxy socket rows. It still shows
  `SOCKS stream id = no`, because Firefox does not expose the local outgoing
  proxy TCP port in this log. The missing piece is exact Firefox proxy socket to
  Arti SOCKS stream mapping, not browser resource to Firefox proxy socket
  mapping.
- Follow-up bridge probe
  `results/browser-compare-20260613T035046/browser-compare.json`, with analyzer
  output at `results/browser-compare-20260613T035046/analysis.md`, used
  `--arti-bin upstream/arti/target/debug/arti --browser-net-log --byte-tap
  --arti-socks-relay-byte-timing`. It passed quality, and the new tap/Arti port
  bridge works: byte tap saved `upstream_local_port`, and Arti saved matching
  `client_peer_port` on `8/8` parsed SOCKS timing rows. The analyzer still kept
  `SOCKS stream id = no` for browser resources because Firefox opened several
  same-host proxy sockets within the same few milliseconds, so browser socket to
  tap connection was ambiguous. Treat this run as proof of the tap-to-Arti join
  only, not speed proof; debug Arti was much slower (`23182.221ms` load vs local
  C Tor `4337.082ms`).
- Serial browser-socket proof
  `results/browser-compare-20260613T040414/browser-compare.json`, with analyzer
  output at `results/browser-compare-20260613T040414/analysis.md`, used the new
  lab-only `--browser-serial-http-connections` switch with `--browser-net-log`,
  `--byte-tap`, and `--arti-socks-relay-byte-timing`. It passed quality and
  produced the first exact browser-resource-to-Arti-stream row:
  `channelId=17179869197` for
  `/static/js/bootstrap.bundle.min.js` mapped to byte-tap connection `3`,
  `upstream_local_port=61603`, Arti `client_peer_port=61603`, `timing_id=3`,
  and `stream_id=41201` with about `1ms` start delta. This proves the full
  evidence chain can work when browser socket concurrency is made
  unambiguous. It is not speed proof and not a production browser setting:
  the run forced browser HTTP connection limits to `1`, and debug Arti/local C
  Tor load times (`21275.185ms` vs `26808.745ms`) are not promotable.
- Normal browser-socket follow-up
  `results/browser-compare-20260613T042228/browser-compare.json`, with analyzer
  output at `results/browser-compare-20260613T042228/analysis.md`, removed the
  serial browser limit and kept `--browser-net-log`, `--byte-tap`, and
  `--arti-socks-relay-byte-timing`. Quality passed for the Arti and local C Tor
  browser runs. This is proof only, not speed proof: debug Arti loaded in
  `9474.402ms` and local C Tor loaded in `8693.476ms` on one cold run. The new
  browser activity probe worked and recorded `72` rows per profile, but proxied
  Tor Browser HTTPS exposed only `0.0.0.0:443` with local port `0`, not the
  outgoing local SOCKS port. The Firefox transaction-to-connection parser also
  worked (`41` Arti HTTP connection rows), but exact SOCKS stream rows remained
  `0` because normal Tor Browser opened several same-host proxy sockets within
  a few milliseconds. Next source target stays the same: add a real
  browser-side local SOCKS port/socket tag, or patch an equivalent exact tag at
  the browser/proxy boundary. Do not use timestamp rank guesses.
- SOCKS request tap proof
  `results/browser-compare-20260613T044713/browser-compare.json`, with analyzer
  output at `results/browser-compare-20260613T044713/analysis.md`, keeps normal
  browser concurrency and adds client-to-proxy SOCKS parsing inside the neutral
  byte tap. Quality passed. Arti loaded in `5414.510ms`; local C Tor loaded in
  `15604.078ms` on this one cold run, so this is proof only, not promotion
  proof. The new `Neutral Byte Tap SOCKS Request Evidence` table captured exact
  SOCKS request target/auth metadata for `11/11` Arti tap connections and
  `12/12` local C Tor tap connections, including `www.torproject.org:443`, the
  page onion/securedrop targets, browser peer ports, and upstream local ports.
  Auth secrets are not stored; only username/password lengths and short SHA256
  prefixes are written. Follow-up analyzer parsing also extracts Firefox's raw
  `nsHttpConnectionInfo` SOCKS auth digest prefix and matches it to tap auth:
  the regenerated `Browser Net Log Resource Evidence` table shows CI auth/tap
  matches for `35/35` Arti parent rows and `36/36` local C Tor parent rows.
  Arti still has only `8` exact SOCKS stream rows, because same-host sockets
  can share the same auth bucket. This improves the browser/proxy boundary
  proof, but the next source target is still a true browser-side local SOCKS
  port or per-socket tag for same-host resource-to-stream joins.
- Runtime browser activity distributor proof
  `results/browser-compare-20260613T050610/browser-compare.json`, with analyzer
  output at `results/browser-compare-20260613T050610/analysis.md`, adds a
  default-off `nsIHttpActivityObserver` to the existing Marionette activity
  probe. Quality passed. The observer installed cleanly and captured `569` rows
  for Arti and `522` rows for local C Tor. The new `Browser Activity Probe
  Evidence` table shows channel-level CI auth/tap matches for `488/488` Arti
  activity rows and `445/445` local C Tor activity rows, with two auth buckets
  per profile. It also shows `0` nonzero local-port rows and `0` exact local
  SOCKS rows. Decision: the runtime browser API gives exact channel-to-isolation
  bucket proof, but not the needed per-socket browser local SOCKS port. The next
  proof needs browser source/local-port tagging or another true per-socket tag.
- SOCKS reply tag proof
  `results/browser-compare-20260613T052031/browser-compare.json`, with analyzer
  output at `results/browser-compare-20260613T052031/analysis.md`, adds a
  default-off byte-tap lab flag
  `--byte-tap-socks-reply-bind-port-tag`. The tap rewrites only the SOCKS5
  CONNECT success reply bind port to a per-connection `400xx` tag. Quality
  passed. The browser activity probe exposed that tag as `localPort`: Arti had
  `282` SOCKS reply tag rows matching `9` tap connections, and local C Tor had
  `286` rows matching `10` tap connections. This is the first normal-concurrency
  per-socket browser/proxy boundary tag. It is lab-only proof, not speed proof
  and not a normal Tor behavior change. Next source work can use this tag to
  build exact resource-to-SOCKS-stream joins before changing stream/resource
  behavior.
- The analyzer now uses the reply tag for exact normal-concurrency resource to
  Arti SOCKS-stream joins. Replaying
  `results/browser-compare-20260613T052031/analysis.md` changed Arti
  `SOCKS stream rows` from timestamp-limited evidence to `29` exact stream rows
  and added `Browser Activity Tagged Stream Resources` plus grouped stream rows.
  Local C Tor still has tag rows but no stream IDs because C Tor does not emit
  the Arti `client_peer_port` stream-link log.
- Fresh download-page proof
  `results/browser-compare-20260613T053122/browser-compare.json`, with analyzer
  output at `results/browser-compare-20260613T053122/analysis.md`, used the
  same default-off tag, byte tap, browser net logs, and Arti relay byte timing.
  Quality passed. This is not promotion proof: Arti load was `12408.548ms`
  versus local C Tor `8574.652ms`, and Arti boot also lost (`29.584s` versus
  `21.733s`) after one directory partial-response/timeout path. The proof did
  produce `34` exact Arti SOCKS stream rows and `30` exact tagged resource rows.
  The worst exact group is timing id `6`, stream `38096` on `Circ 3.5`, with
  `5` resources, `3` queued at least `1000ms`, max queue `7083.475ms`, and top
  resource `favicon.ico`. The selected-circuit evidence still says
  `stream-specific gap; circuit still active`, max observed stream gap `1969ms`
  versus max circuit DATA gap `477ms`, with no scheduler monopoly or local
  block. Next source work should use this exact tag proof to reduce the
  selected stream/resource queue tail; do not retune broad selector knobs from
  this evidence alone.
- The same analyzer now prints `Browser Activity Tagged Stream Sequence`, which
  orders resources inside each tagged HTTP/SOCKS stream and shows whether a
  request started after the previous response on the same stream. On the same
  `053122` proof, the top slow stream `38096` shows `github.png` starting at
  request time `10900.218ms` exactly after `fa-solid-900.woff2`, and
  `favicon.ico` starting `300.006ms` after `github.png`. Several other tagged
  streams have `0.000ms` request-after-previous-response gaps. This means the
  large browser queue is mostly sequential keep-alive resource chains on active
  streams, so the next safe source target is shorter active-stream response
  tails under unchanged Tor Browser connection caps, not changing browser
  prefs or forcing different HTTP connection behavior.
- The analyzer now also prints `Browser Activity Tagged Connection Resources`,
  `Groups`, and `Sequence`. These rows need only the neutral SOCKS reply tag,
  not Arti stream-link logs, so the same `053122` proof now compares Arti and
  local C Tor at the browser/proxy connection boundary. Arti had `330` SOCKS
  reply tag rows matching `12` tap connections; local C Tor had `326` rows
  matching `8` tap connections. The worst Arti tagged connection was connection
  `7` / tag `40007` with `5` resources and max queue `7083.475ms`. The worst
  local C Tor tagged connection was connection `8` / tag `40008` with `6`
  resources and max queue `4666.760ms`. This keeps the browser-cap comparison
  honest and points back at Arti active-stream response/relay tail behavior;
  it is analyzer-only proof, not a speed change.
- Source now has a default-off app/Tor stream buffer lab knob:
  `TORFAST_APP_STREAM_BUF_LEN`, exposed by
  `tools/run_browser_compare.py --arti-proxy-app-buffer-len` and
  `--extra-arti-proxy-app-buffer-len`. It only changes the proxy
  `BufReader` capacity when explicitly set. Default Arti remains `4096`.
- Same-window proof with a larger `32768` buffer is a clear reject:
  `results/browser-compare-20260613T060228/browser-compare.json`, analyzer
  output at `results/browser-compare-20260613T060228/analysis.md`, quality
  passed. Default Arti loaded in `8083.751ms`; local C Tor loaded in
  `9598.371ms`; `arti_release_browser_appbuf32768` loaded in `22996.320ms`.
  The extra profile's worst tagged connection queue was `15400.308ms`. This is
  slower than both baselines and must not be promoted.
- Same-window proof with a smaller `8192` buffer is also a reject:
  `results/browser-compare-20260613T060436/browser-compare.json`, analyzer
  output at `results/browser-compare-20260613T060436/analysis.md`, quality
  passed. Default Arti loaded in `2850.192ms`; local C Tor loaded in
  `5223.242ms`; `arti_release_browser_appbuf8192` loaded in `6218.312ms`.
  The extra profile's worst tagged connection queue was `3716.741ms` versus
  default Arti's `1083.355ms`. Larger app stream buffers are now ruled out as
  a speed fix; keep using the tagged stream/connection proof to target
  selected active-stream response tails instead.
- The tagged stream analyzer now adds write-tail columns to exact
  resource-to-SOCKS-stream rows: `last write ms`, `response after write ms`,
  group `max write lag ms`, and group `median response after write ms`. It
  uses SOCKS timing rows first and can fall back to retained
  `torfast socks byte event` rows. Arti now raises those byte events to INFO
  when `TORFAST_SOCKS_RELAY_BYTE_TIMING=1`; normal logging is unchanged.
- Fresh proof
  `results/browser-compare-20260613T062407/browser-compare.json`, with analyzer
  output at `results/browser-compare-20260613T062407/analysis.md`, used the
  byte tap, SOCKS reply tag, browser net log, and Arti relay byte timing.
  Quality passed, but this is not a speed win: Arti loaded in `8829.720ms`
  versus local C Tor `6353.880ms` (`+2475.840ms`). The proof retained
  `client_to_tor` and `client_to_tor_write` byte events, but no
  `tor_to_client` or `tor_to_client_write` byte events, so the new write-tail
  columns stayed blank for real rows. Next source work should instrument the
  browser-facing write half without changing relay copy semantics; do not patch
  browser prefs or app stream buffers from this proof.
- Rejected follow-up proof
  `results/browser-compare-20260613T063857/browser-compare.json`, with analyzer
  output at `results/browser-compare-20260613T063857/analysis.md`, tried a
  timing-only hand-rolled copy loop in the byte-timing path. This is rejected
  and was reverted: Arti failed quality with Firefox
  `about:neterror?e=nssFailure2`, while local C Tor passed. The run still
  retained only `client_to_tor` and `client_to_tor_write` byte events (`12`
  retained rows total) and `0` `tor_to_client` / `tor_to_client_write` rows.
  Do not replace the relay copy loop for this diagnostic; the next hook must
  be passive.
- Passive follow-up hook now wraps only the split writer halves with
  `CountingWriter` in the byte-timing path. It keeps the existing
  `futures_copy::copy` relay loop and the same browser-style close behavior.
  First proof `results/browser-compare-20260613T065147/browser-compare.json`
  passed quality and retained response-side byte events
  (`tor_to_client=14`, `tor_to_client_write=14`), but the exact resource rows
  still did not get hostname write tails because early byte rows were dropped
  by harness retention. Arti loaded faster than local C Tor in that single run
  (`4621.800ms` versus `5170.867ms`), but this is not promotion proof.
- Harness retention now keeps `torfast socks byte event` rows for timing ids
  linked to retained terminal stream rows. Fresh proof
  `results/browser-compare-20260613T065745/browser-compare.json` passed
  quality and retained byte rows for all directions across timing ids `3..9`:
  `client_to_tor=45`, `client_to_tor_write=76`, `tor_to_client=79`, and
  `tor_to_client_write=79`. The tagged resource rows now have populated
  `last write ms` and `response after write ms` values. Speed is still a
  reject: Arti loaded in `4562.406ms` versus local C Tor `4251.651ms`, and
  Arti boot was `24.469s` versus local C Tor `13.565s`. The blocker row still
  says `boot slower, boot directory, slower than C Tor, resource queue, slow
  onion/data gap`; next proof remains `stream gap proof`.
- Analyzer replay now adds `Browser Activity Tagged Stream Queue Cause` for
  the exact tagged stream rows. In the same
  `results/browser-compare-20260613T065745/analysis.md`, the top queued
  resource `tor-logo@2x.png` on timing id `5`, stream `58501`, had
  `2450.049ms` of queue, and all `2450.049ms` was blocked by the previous
  same-stream response (`arrow-down.png`). The next rows show the same shape:
  `linkedin.png`, `github.png`, `twitter.png`, and `stay-safe.svg` all have
  `0.000ms` unexplained queue after the previous response. Decision: this
  points to same-stream response-chain tail work, not browser write lag,
  browser connection caps, app stream buffer size, or selector retuning.
- The same replay now adds `Browser Activity Tagged Connection Queue Cause
  Summary`, which compares Arti and local C Tor at the neutral browser/proxy
  tag boundary. Both stacks are almost entirely previous-response blocked, but
  Arti's total tagged connection queue was higher in this run:
  `33334.000ms` total queue with `33267.332ms` previous-response blocked
  (`99.800%`) and max queue `2450.049ms`; local C Tor had `29050.581ms` total
  queue with `29033.914ms` blocked (`99.943%`) and max queue `1766.702ms`.
  The phase split says most of that is inherited pre-request queue
  (`19617.059ms` Arti versus `17383.681ms` local C Tor), while Arti also has
  a larger previous-receive blocked bucket (`4333.420ms` versus
  `1966.706ms`). The neutral byte tap now splits that receive bucket too:
  Arti had proxy data in `10` previous-receive rows, `142.896 KiB` total, and
  `180.006ms` median browser-after-last-proxy-data (`438.927ms` max); local C
  Tor had `9` rows, `313.016 KiB`, and `19.776ms` median (`350.524ms` max).
  Previous-wait blocked time was not higher for Arti (`9316.853ms` versus
  `9683.527ms`). Decision: compare future work against local C Tor in this
  same table; the best next source target is response receive/tail, especially
  browser finish after last proxy byte, plus inherited queue-chain reduction,
  not server-wait, browser-write, browser-cap, buffer-size, or selector
  retuning.
- Source now has a default-off local proxy coalescing lab knob:
  `TORFAST_SOCKS_TOR_TO_CLIENT_COALESCE_BYTES`, exposed by
  `tools/run_browser_compare.py --extra-arti-socks-tor-to-client-coalesce-bytes`.
  It only coalesces already-ready Tor-to-browser bytes before the local SOCKS
  write when explicitly set; default Arti keeps the old copy path. Same-window
  proof `results/browser-compare-20260613T082131/browser-compare.json` with
  `4096` bytes passed quality but rejects promotion: default Arti loaded in
  `3574.126ms`, coalesce4096 in `4545.453ms`, and local C Tor in `5011.276ms`.
  The mechanism moved partly in the intended direction but not enough:
  coalesce4096 lowered median previous-response-end-after-last-proxy-data from
  `168.672ms` to `112.190ms` and max tagged queue from `1916.705ms` to
  `1483.363ms`, but worsened total tagged queue from `24350.487ms` to
  `28000.560ms` and load versus default. The neutral tap confirms chunk shape
  changed (`498.0` byte median default Arti proxy chunks versus `1900` with
  coalescing and `2422.0` for local C Tor). Keep this as negative proof: local
  write coalescing alone is not the speed win.
- Directory-spread combo proof
  `results/browser-compare-20260613T070615/browser-compare.json`, with analyzer
  output at `results/browser-compare-20260613T070615/analysis.md`, passed
  quality but rejects the combo. The global load-aware/healthy-over-cold
  threshold `1` base loaded the download page in `3936.005ms`; adding
  `mdsrcspreadpendingearlyusable` loaded in `5065.103ms`. The combo lost paired
  load by `+289.674ms`, won only `1/3` paired loads, and made max tail worse by
  `+1295.446ms`. Local C Tor boot was unusually slow in this window
  (`33.606s`), so this is not promotion proof for either profile.
- Threshold-zero healthy-over-cold lab proof
  `results/browser-compare-20260613T071358/browser-compare.json`, with analyzer
  output at `results/browser-compare-20260613T071358/analysis.md`, passed
  quality. The runner and Arti lab source now allow
  `TORFAST_EXIT_SELECT_HEALTHY_OVER_COLD_MIN_ASSIGNED=0`, and the unit test
  proves the helper can move a fresh cold selected circuit to a proven healthy
  candidate. The browser proof did not exercise that path:
  `healthy-over-cold moves` stayed `0`. The page-load win came from load-aware
  selection (`44` load-aware picks, `14` non-first selections), not from the
  new threshold. `arti_release_browser_loadaware_healthyovercold0` loaded in
  `4053.066ms` versus base Arti `6297.926ms` and local C Tor `4505.780ms`, but
  boot+load was still slower than local C Tor (`47370.066ms` versus
  `43226.780ms`) because Arti boot took `43.317s`. Decision: keep threshold
  `0` lab-only and do not promote it; next proof still needs real selector
  mechanism evidence with boot controlled.
- Analyzer replay now separates weak health alternatives from real
  selector-health move proof. In the same
  `results/browser-compare-20260613T071358/analysis.md`, the slow queue rows
  now classify as `below-floor health alternative`: base Arti had `13` queued
  rows with max alt health score `29547`, and the threshold-zero profile had
  `4` queued rows with max alt health score `19310`, both below the default
  move floor `65536`. That means the old `better-health alternative` label was
  too broad. Do not lower the floor from this proof; earlier `16000bps` repeats
  already lost. The next useful proof is still stream-gap/resource-queue tail
  behavior, not another broad health-score retune.
- Analyzer replay now joins each `Browser Resource Stream Gap Context` row to
  same-circuit DATA during that exact stream gap. In
  `results/browser-compare-20260613T071358/analysis.md`, threshold-zero run `3`
  timing id `25` / stream `1045` had a `5056ms` browser-resource stream gap;
  the same circuit had `2` other DATA cells on `2` other streams, but the max
  circuit DATA gap inside that same window was still `4734ms`. Timing ids `23`
  and `21` had more other-stream DATA (`61` and `37` cells) with the same
  `4734ms` max circuit quiet span. Decision: the current proof points to
  stream/resource tail behavior with partial circuit quiet, not a safe
  selector-health floor change.
- Verification for the threshold-zero lab change:
  `python3 -m py_compile tools/check_arti_quality_config.py
  tools/run_browser_compare.py tests/test_browser_quality.py`,
  `python3 tools/check_arti_quality_config.py` (`80` checks, latest output
  `results/arti-quality-config-20260613T072038/arti-quality-config.json`),
  `python3 -m unittest tests.test_browser_quality` (`199` tests), and
  `cargo test -p tor-circmgr healthy_over_cold` passed. Earlier in the same
  source state, `cargo fmt --package tor-circmgr` and
  `cargo build --release -p arti` also passed.
- Verification for this buffer and write-tail lab work: `python3 -m py_compile
  tools/analyze_browser_compare.py tools/run_browser_compare.py
  tests/test_browser_quality.py`, `python3 -m unittest
  tests.test_browser_quality` (`199` tests), `cargo fmt --package arti`,
  `cargo test -p arti torfast_app_stream_buf_len_env_is_bounded`, and
  `cargo build --release -p arti` passed.
- Harness fix: sequential `run_arti()` now defines the default
  `arti_exit_select_health_aware_min_assigned=None`; without that, the first
  `--browser-net-log` probe crashed before Arti could complete.
- Verification for this analyzer update:
  `python3 -m py_compile tools/analyze_browser_compare.py
  tools/run_browser_compare.py tests/test_browser_quality.py`,
  focused browser-net-log/parser/runner tests, and
  `python3 -m unittest tests.test_browser_quality` passed (`197` tests).

## 2026-06-12 status

HS intro/rendezvous overlap proof:

- Source and runner now expose a default-off lab knob
  `TORFAST_HS_INTRO_REND_OVERLAP`, plus a same-window browser A/B profile
  through `tools/run_browser_compare.py --extra-arti-hs-intro-rend-overlap`.
  It keeps the same HS path and relay rules, but overlaps intro-circuit
  acquisition with rendezvous setup when no saved rendezvous exists.
- `results/browser-compare-20260613T004328/browser-compare.json`, with analyzer
  output at `results/browser-compare-20260613T004328/analysis.md`, passed
  quality and all page loads passed. Promotion is rejected. The overlap profile
  lost the homepage badly versus base Arti (`13323.528ms` median load versus
  `5038.101ms`) and local C Tor (`3920.115ms`), lost Tor check versus base Arti
  (`2171.106ms` versus `1845.912ms`), and only improved download median versus
  base Arti by `402.176ms` while still losing local C Tor (`8181.027ms` versus
  `5233.424ms`).
- Mechanism proof is present: the overlap profile used
  `info,tor_proto=debug,tor_hsclient=debug`, retained `torfast hs timing`
  rows, and showed one overlapped setup where the intro circuit was ready at
  `652ms` while rendezvous was ready at `1779ms` and established at `2238ms`.
  The analyzer still showed worse HS tunnel median (`4189.500ms` versus base
  Arti `3735.000ms`) plus resource queue blockers. Decision: keep
  intro/rendezvous overlap lab-only; do not promote.
- Verification for this patch: Python compile passed for edited Python files,
  targeted browser-quality and quality-config unit tests passed (`5` tests),
  `cargo test -p tor-hsclient --all-features
  hs_intro_rend_overlap_env_is_default_off --manifest-path
  upstream/arti/Cargo.toml` passed, static quality config passed `80/80` at
  `results/arti-quality-config-20260613T004135/arti-quality-config.json`, and
  release Arti rebuilt with
  `cargo build --release -p arti --manifest-path upstream/arti/Cargo.toml`.

HS pool launch parallelism proof:

- Source and runner now expose a default-off, bounded lab knob
  `TORFAST_HSPOOL_LAUNCH_PARALLELISM`, plus same-window browser A/B profiles
  through `tools/run_browser_compare.py --extra-arti-hspool-launch-parallelism`.
  Default behavior remains serial launch width `1`; valid lab values are
  `1..4`.
- `results/browser-compare-20260613T000747/browser-compare.json`, with analyzer
  output at `results/browser-compare-20260613T000747/analysis.md`, tested HS
  pool launch width `2` with relay byte timing. Quality passed and all page
  loads passed (`9/9`) for the Arti profiles, but promotion is rejected.
  `hspoollaunch2` improved the Tor Project homepage median load versus base
  Arti (`4268.108ms` versus `7668.596ms`), but it lost Tor check
  (`2147.868ms` versus `1531.707ms`) and download (`6078.085ms` versus
  `5211.627ms`), had a `63027.689ms` homepage tail, and kept boot directory,
  resource queue, slow onion/data-gap, and slow hostname stream blockers.
  Decision: keep HS pool launch parallelism lab-only; do not promote.
- Runner follow-up: hspool A/B profiles now add `tor_circmgr=debug` to the
  effective Arti log level when the hspool launch lab knob is active, so compact
  browser runs retain `torfast hspool` mechanism rows. Focused proof
  `results/browser-compare-20260613T002829/browser-compare.json` passed quality
  on one homepage run and retained `8` hspool rows, including
  `launch_parallelism=2` and three background-ready stems (`1066ms`, `1083ms`,
  `1088ms`). It still rejected speed: hspoollaunch2 loaded homepage
  `12373.766ms` versus base Arti `8184.036ms` and local C Tor `3931.445ms`;
  slow onion remained tunnel acquisition (`2409ms` tunnel, `442ms` begin
  phase). Decision: mechanism logging is fixed, hspoollaunch2 remains lab-only.
- Verification for this patch: `python3 -m py_compile` passed for the edited
  Python files, targeted browser-quality and quality-config unit tests passed
  (`5` tests), `cargo test -p tor-circmgr --all-features
  hspool_launch_parallelism_env_is_serial_by_default_and_bounded
  --manifest-path upstream/arti/Cargo.toml` passed, static quality config
  passed `79/79` at
  `results/arti-quality-config-20260613T000527/arti-quality-config.json`, and
  release Arti rebuilt with
  `cargo build --release -p arti --manifest-path upstream/arti/Cargo.toml`.

Health-aware selector repeat:

- `results/browser-compare-20260613T001705/browser-compare.json`, with analyzer
  output at `results/browser-compare-20260613T001705/analysis.md`, tested the
  existing same-window `arti_release_browser_healthaware` profile against the
  same three targets. Quality passed and all page loads passed, but promotion is
  rejected. The profile improved over the bad base-Arti homepage tail
  (`11410.941ms` median load versus `61740.772ms`) and beat local C Tor on
  download (`7457.976ms` versus `10506.270ms`), but lost Tor check
  (`1542.333ms` versus local C Tor `1491.581ms`) and badly lost the homepage
  (`11410.941ms` versus local C Tor `4349.762ms`). Analyzer blockers remained
  `boot directory`, `slower than C Tor`, `resource queue`, and
  `slow onion/data gap`.
- Decision: health-aware selection remains useful lab evidence only. The next
  source target is still the page resource queue / slow onion-data-gap tail, not
  promoting selector health scoring.

Exit launch parallelism proof:

- Source and runner now expose a default-off, bounded lab knob
  `TORFAST_EXIT_LAUNCH_PARALLELISM`, plus
  `tools/run_browser_compare.py --arti-exit-launch-parallelism` and
  `--extra-arti-exit-launch-parallelism`. Default behavior remains launch width
  `1`; valid lab values are `1..4`.
- `results/browser-compare-20260612T223525/browser-compare.json`, with analyzer
  output at `results/browser-compare-20260612T223525/analysis.md`, tested launch
  width `2`. Quality passed and all page loads passed (`9/9`). Launch `2`
  improved base Arti median load on all three targets: Tor check `1795.575ms`
  versus `2659.357ms`, homepage `5441.568ms` versus `8118.284ms`, and download
  `6608.338ms` versus `6891.512ms`. It still lost to local C Tor on all three
  median loads: local C Tor was `1551.132ms`, `5063.833ms`, and `6148.911ms`.
  Decision: useful signal, but not promotable.
- `results/browser-compare-20260612T224226/browser-compare.json`, with analyzer
  output at `results/browser-compare-20260612T224226/analysis.md`, tested launch
  widths `3` and `4`. Quality passed and all page loads passed. Launch `3`
  lost Tor check (`2046.316ms` versus local C Tor `1623.602ms`), was effectively
  tied but still slightly slower on homepage (`5854.780ms` versus
  `5853.995ms`), and lost download (`5319.696ms` versus `4845.324ms`). Launch
  `4` lost local C Tor on all three targets and made homepage much worse
  (`7961.890ms`). Decision: keep launch `3` and `4` lab-only too.
- Verification for this patch: `python3 tools/check_arti_quality_config.py`
  passed `78/78` and wrote
  `results/arti-quality-config-20260612T235301/arti-quality-config.json`;
  `python3 -m unittest tests.test_arti_quality_config tests.test_browser_quality`
  passed `183` tests; `python3 -m unittest discover` passed `203` tests; and
  release Arti rebuilt with
  `cargo build --release -p arti --manifest-path upstream/arti/Cargo.toml`.
  The next source work should inspect the remaining launch `2` slow CONNECT
  tails before any promotion.
- Analyzer follow-up: `tools/analyze_browser_compare.py` now prints
  `Torfast Slow CONNECT Phase Join`, joining slow SOCKS CONNECT rows to the
  existing exit-client and HS-client phase logs. The regenerated launch `2`,
  `3`, and `4` analyses show the matched slow CONNECT rows are tunnel
  acquisition delay, not BEGIN delay: matched hostname rows have near-zero
  begin phase, and matched onion rows have `340..603ms` begin phases behind
  `1997..5064ms` tunnel waits. Some slow rows still show `phase missing`, so
  the next proof gap is retaining phase rows for every slow CONNECT before
  changing tunnel acquisition behavior.
- Harness follow-up: `tools/run_browser_compare.py` now retains slow CONNECT
  SOCKS rows and matching exit-client / HS-client phase rows even when the
  run-level proxy signal log is capped. This is proof-only; it does not change
  Tor behavior, path choice, stream isolation, browser prefs, or relay traffic.
  The next browser proof should rerun the launch `2` shape with relay timing and
  should no longer lose phase rows for slow CONNECTs.
- Fresh launch `2` retention retest
  `results/browser-compare-20260612T234009/browser-compare.json`, with analyzer
  output at `results/browser-compare-20260612T234009/analysis.md`, passed
  quality and all page loads, but still rejects promotion. Launch `2` lost to
  base Arti on all three median page loads: Tor check `2121.526ms` versus
  `1617.978ms`, homepage `5926.253ms` versus `5849.060ms`, and download
  `4875.826ms` versus `3724.126ms`. It also kept a slower-than-C-Tor blocker
  and boot directory failure signals. The slow CONNECT phase join now keeps
  most phase rows and shows tunnel acquisition delay, not BEGIN delay; two slow
  rows still have no lifecycle rows. Decision: launch `2` stays lab-only. Next
  source work should target tunnel acquisition / stream-gap tails, not promote
  launch parallelism.

Fresh active-cap 2 retest:

- Busy `443` preemptive proof
  `results/browser-compare-20260612T212929/browser-compare.json`, with analyzer
  output at `results/browser-compare-20260612T212929/analysis.md`, passed
  quality but is rejected. The busy profile helped the Tor Project homepage
  median load (`3369.350ms` versus base Arti `4403.163ms`) but hurt Tor check
  (`2875.479ms` versus `1780.032ms`) and download (`6266.567ms` versus
  `4654.442ms`) and made max tails worse. Do not promote the busy preemptive
  `443` rule.
- Active-cap 2 broad proof
  `results/browser-compare-20260612T213724/browser-compare.json`, with analyzer
  output at `results/browser-compare-20260612T213724/analysis.md`, passed
  quality and beat local C Tor on all three median page loads: Tor check
  `1111.091ms` versus `1654.888ms`, Tor Project homepage `4971.334ms` versus
  `6846.774ms`, and download `5104.357ms` versus `8280.703ms`. This is the best
  current active-cap signal, but it still had slow onion/hostname CONNECT
  blockers and worse small-page tail risk.
- Wider active-cap 2 repeat
  `results/browser-compare-20260612T214724/browser-compare.json` rejects
  promotion. Base Arti had one Tor-check failure, so the window is not clean;
  the active-cap 2 profile itself passed all `15/15` page loads, but lost median
  page load to local C Tor on Tor check (`2402.080ms` versus `1635.013ms`), Tor
  Project homepage (`6911.355ms` versus `5947.003ms`), and download
  (`8233.304ms` versus `4276.828ms`). Keep active-cap 2 lab-only. The next
  source work should target slow CONNECT/stream-gap tails, not promote
  active-cap 2 from the single good 3-run window.

Broad healthy-over-cold threshold `1` repeat
`results/browser-compare-20260612T220658/browser-compare.json` passed quality
but rejects promotion. The `arti_release_browser_loadaware_healthyovercold1`
profile passed all `9/9` page loads, but lost median page load to base Arti on
all three targets: Tor check `2468.175ms` versus `1824.513ms`, homepage
`6067.884ms` versus `4819.108ms`, and download `8018.242ms` versus
`5125.488ms`. It beat local C Tor only on homepage (`6067.884ms` versus
`6535.778ms`) and lost Tor check and download. A targeted log read found `224`
selection-open rows, `208` exit rows with load-aware on, and `0`
healthy-over-cold moves (`healthy_over_cold_candidate_index=-1` in every row).
So this broad run is a no-mechanism reject; do not promote threshold `1` from
the older focused homepage win.

The browser quality gate now has a no-Marionette fingerprint proof. The harness
launches Tor Browser without automation, screenshots a local canvas-encoded
fingerprint page, decodes it, and requires `navigator.webdriver=false` plus a
zero-offset timezone. This fixes the old false failure where Marionette itself
made timed browser runs report `navigator.webdriver=true`.

Fresh proof `results/browser-compare-20260612T133805/browser-compare.json`
passed quality. On Wikipedia with 10 paired warm runs, current base Arti won
page-load median against local C Tor (`1756.128ms` versus `2415.064ms`) and won
`9/10` paired loads. This is the best current page-load signal, but it is not a
promotion yet: analyzer blockers still include `boot slower`, `resource queue`,
and one unresolved slow hostname stream, and boot+median-load was still slower
because measured Arti boot was `1.042s`.

Wider proof `results/browser-compare-20260612T134217/browser-compare.json`
also passed quality across Tor check, Tor Project, and Wikipedia with 3 paired
runs per target. It rejected promotion: Arti won Tor check, but was slower on
Tor Project and slightly slower on Wikipedia, with slow hostname/onion stream
blockers and a large Tor-check tail. The next source work should target slow
CONNECT/stream-gap tails and Tor Project resource queues, not call the
Wikipedia-only win done.

Load-aware selection was retested in
`results/browser-compare-20260612T133633/browser-compare.json` and passed
quality, but it is not the next speed path: the load-aware profile was much
slower than base Arti on Wikipedia while only roughly matching local C Tor.

Follow-up: `tools/run_browser_compare.py` now exposes the existing default-off
SOCKS connect hedge as `--extra-arti-socks-connect-hedge-ms`. This is only a
same-window lab A/B switch; it does not change default Arti behavior. The
analyzer now has an explicit `Torfast SOCKS Connect Hedges` table when a result
captures hedge events. Unit tests passed (`193` tests), and static Arti quality
config passed (`72/72` checks).

Focused hedge runs all passed quality, but they do not prove the hedge is a
speed fix yet:

- `results/browser-compare-20260612T140918/browser-compare.json` tested
  Wikipedia with a `1500ms` connect hedge. The hedge profile had better median
  load than base Arti (`1552.788ms` versus `1830.158ms`) and local C Tor
  (`2302.215ms`), but no `connect hedge launched` log appeared.
- `results/browser-compare-20260612T141109/browser-compare.json` tested
  Wikipedia with a `500ms` connect hedge. It passed quality and beat base Arti
  by median load, but added a resource-queue blocker and still had no hedge
  launch log.
- `results/browser-compare-20260612T141408/browser-compare.json` tested Tor
  check with a `500ms` connect hedge. It passed quality and had better median
  load (`1202.864ms`) than base Arti (`1517.015ms`) and local C Tor
  (`1516.314ms`), but again did not prove an actual hedge launch.
- `results/browser-compare-20260612T141538/browser-compare.json` was a one-run
  `example.com` smoke test. It also passed quality and the hedge profile loaded
  faster, but still did not show a hedge launch. Treat this only as wiring and
  target-shape evidence.
- `results/browser-compare-20260612T142854/browser-compare.json` tested the Tor
  Project homepage with 3 interleaved warm runs and a `500ms` connect hedge. It
  passed quality. The hedge profile beat base Arti by median page load
  (`5833.854ms` versus `9091.147ms`) and won all 3 paired loads against base
  Arti, but it was still slower than local C Tor (`5299.667ms`) and slower on
  boot+load (`7344.854ms` versus `5299.667ms`). It also still showed promotion
  blockers: `boot slower`, `slower than C Tor`, `resource queue`, and
  `slow onion/data gap`. The new hedge-proof path found no `connect hedge`
  event, so this is not hedge speed proof.

Fresh stream-gap proof
`results/browser-compare-20260612T144129/browser-compare.json`, with analyzer
output at `results/browser-compare-20260612T144129/analysis.md`, reran Tor check
and the Tor Project homepage with `--arti-socks-relay-byte-timing`. Quality
passed. It rejects current Arti as a speed win: on Tor check, Arti median load
was `2695.687ms` versus local C Tor `1621.320ms`; on the Tor Project homepage,
Arti median load was `9373.477ms` versus local C Tor `7324.004ms`. The useful
proof is the blocker shape. The analyzer still flags `slower than C Tor`,
`resource queue`, and `slow onion/data gap`, but the detailed rows show no
local queue/window block and no scheduler monopoly. The late page resources map
to selected-circuit DATA gaps around `4.7s..5.0s`, with END delivered and zero
pending bytes. Do not tune blind no-byte or partial-idle closes from this; the
next source path is safer circuit choice for resource bursts or deeper
stream-gap proof.

Health-aware same-window A/B
`results/browser-compare-20260612T144707/browser-compare.json`, with analyzer
output at `results/browser-compare-20260612T144707/analysis.md`, tested
`--extra-arti-exit-select-health-aware` on the same two targets for `3` runs.
Quality passed, but it is not promotable. Health-aware helped the Tor Project
homepage a lot: median load `3775.094ms` versus base Arti `6807.006ms` and local
C Tor `5525.820ms`, with boot+load also ahead of local C Tor
(`4736.094ms` versus `5525.820ms`). It hurt Tor check: median load
`2089.105ms` versus base Arti `1826.580ms` and local C Tor `1592.844ms`, with
`0/3` paired load wins against base Arti and a worse max tail. Keep
health-aware lab-only. The next useful source work is not global health-aware;
it is a narrower trigger that only helps the large resource-burst case without
slowing small check pages.

Lower-spread health-aware A/B
`results/browser-compare-20260612T145548/browser-compare.json`, with analyzer
output at `results/browser-compare-20260612T145548/analysis.md`, tested
`--extra-arti-exit-select-health-aware-min-assignment-spread 1` and `2` on the
same two targets for `3` runs. Quality passed, but neither profile is
promotable. Spread `1` improved the Tor Project homepage median load
(`3902.350ms` versus base Arti `4809.413ms`) but hurt Tor check median load
(`2425.882ms` versus `1572.510ms`). Spread `2` had the best homepage queue tail
(`2283.379ms` max queued versus base Arti `10533.544ms`) and won all `3/3`
paired homepage loads against base Arti, but it was still worse on Tor check
and slower on homepage boot+load than base Arti. Keep these profiles lab-only.
The useful clue is that spread `2` can reduce large resource queues; the next
proof should use byte timing on spread `2` to see whether the selector really
moved streams onto healthier circuits without adding small-page risk.

Byte-timing spread `2` proof
`results/browser-compare-20260612T150653/browser-compare.json`, with analyzer
output at `results/browser-compare-20260612T150653/analysis.md`, reran spread
`2` with `--arti-socks-relay-byte-timing` for `2` runs. Quality passed. It is
still not promotable. Spread `2` improved the Tor Project homepage median load
against base Arti (`4317.828ms` versus `4952.594ms`) and reduced homepage max
queue (`1816.703ms` versus `2416.715ms`), but it hurt Tor check median load
(`1570.332ms` versus `1416.899ms`) and lost badly on boot+load because its boot
was `1.739s`. Against local C Tor, spread `2` was slightly faster on homepage
page load (`4317.828ms` versus `4491.476ms`) but slower on boot+load
(`6056.828ms` versus `4491.476ms`) and slower on Tor check (`1570.332ms`
versus `1390.836ms`). The mechanism is also weak: the best homepage run used a
very fast selected circuit, but the slower homepage run still had selected
circuit DATA gaps around `4.95s..5.02s`, zero local queue/window proof, and an
`only selected open` choice row. Do not add or promote another selector from
this. The next useful work is deeper selected-circuit gap proof or a guard that
only acts when a large resource burst has a proven healthier open alternative.

Same-isolation prewarm proof
`results/browser-compare-20260612T151330/browser-compare.json`, with analyzer
output at `results/browser-compare-20260612T151330/analysis.md`, tested
`--extra-arti-exit-same-isolation-prewarm-target 2` with relay byte timing for
`3` runs. Quality passed, but it is worse and not promotable. The prewarm
profile lost to base Arti on both targets: Tor check median load was
`1772.435ms` versus base Arti `1658.894ms`, and the Tor Project homepage median
load was `6352.371ms` versus base Arti `4287.372ms`. Boot was also much slower
at `4.354s`. The important proof is why: the same-isolation top-up built a
candidate, but the built circuit never appeared in later open candidates and
was not used by streams. The worst homepage queue still selected a cold
zero-health circuit while a healthier open alternative existed
(`selected_health_score_bps=0`, alternative health score `93325`). Do not keep
prewarming as the next path. The next source path should be a narrow lab-only
selector guard that avoids a cold selected circuit only when assigned-stream
pressure exists and a proven healthier open alternative is already available.

Healthy-over-cold selector guard follow-up:
Arti now has the default-off lab env
`TORFAST_EXIT_SELECT_HEALTHY_OVER_COLD_MIN_ASSIGNED`, and
`tools/run_browser_compare.py` can test it with
`--extra-arti-exit-select-healthy-over-cold-min-assigned`. The guard only runs
when load-aware selection is enabled. It can replace the assignment-selected
open circuit only when that selected circuit is busy enough, has no health
score, is not bad, and another open candidate already wins by the existing
health-aware comparison. Static quality config passed (`73` checks),
`python3 -m unittest tests.test_browser_quality` passed (`173` tests),
`cargo test -p tor-circmgr healthy_over_cold` passed, and release Arti rebuilt.

Fresh threshold `4` proof
`results/browser-compare-20260612T154234/browser-compare.json`, with analyzer
output at `results/browser-compare-20260612T154234/analysis.md`, passed
quality but rejects the guard. It did not fire in this run
(`healthy_over_cold_candidate_index` never selected another candidate), and the
profile was slower than base Arti on both targets: Tor check median load
`2414.277ms` versus `2021.674ms`, and the Tor Project homepage median load
`7343.070ms` versus `6176.137ms`. Decision: threshold `4` is too high for this
traffic shape and is not a speed win.

Lower threshold proof
`results/browser-compare-20260612T154920/browser-compare.json`, with analyzer
output at `results/browser-compare-20260612T154920/analysis.md`, tested
thresholds `1` and `2`. Overall quality failed because threshold `2` hit a Tor
check browser proof failure on run `3` (`nssFailure2` after `CONNRESET`), and
the threshold `2` guard did not move any circuit choice. Threshold `1` is the
useful clue: it did move selection `8` times and beat base Arti page-load on
both targets, with Tor check median load `1759.540ms` versus base Arti
`3445.853ms`, and homepage median load `5287.778ms` versus base Arti
`6990.466ms`. It is still not promotable: it lost page-load to local C Tor on
both targets (`1434.153ms` Tor check, `4544.921ms` homepage), and after boot it
lost to base Arti too (`4733.540ms` versus `3445.853ms` on Tor check,
`8261.778ms` versus `6990.466ms` on homepage). Decision: keep the guard
lab-only. Threshold `1` is a real mechanism clue for large resource bursts, but
not a safe speed fix yet.

Proof-harness fix:
`tools/run_browser_compare.py` now records true interleaved boot time from each
profile launch to ready. Before this, interleaved `boot.seconds` measured only
the leftover wait after the staggered launch plan, so long-boot profiles could
show `0.000s` boot if they were ready before the wait threads started.
`tools/analyze_browser_compare.py` now also derives true boot time for older
interleaved JSON from `interleaved_launch.started_epoch_ms` and
`boot.ready_epoch_ms`. This changes the interpretation of old boot+load rows:
the threshold `1` guard was not slower on boot+load in the mixed run, but that
mixed run still failed quality because threshold `2` failed one browser proof.

Clean threshold `1` repeat:
`results/browser-compare-20260612T161355/browser-compare.json`, with analyzer
output at `results/browser-compare-20260612T161355/analysis.md`, reran only
`--extra-arti-exit-select-healthy-over-cold-min-assigned 1` with relay byte
timing. Quality passed, and the guard fired (`6` selection moves). This is the
best guard proof so far. Against base Arti, threshold `1` improved summary
median load on both targets: Tor check `1843.213ms` versus `2763.968ms`, and
the Tor Project homepage `4508.272ms` versus `7946.265ms`. Boot was also much
faster than base in this window (`2.218s` versus `8.541s`), so boot+load was
better on both targets.

It still is not promotion proof. Against local C Tor, threshold `1` lost raw
Tor check page-load (`1843.213ms` versus `1574.611ms`) and had `0/3` paired
Tor check load wins. It did win the homepage raw load (`4508.272ms` versus
`6518.296ms`) and won boot+load on both targets, but the analyzer still lists
`slower than C Tor`, `resource queue`, `slow onion/data gap`, and
`slow hostname stream`. Decision: threshold `1` stays lab-only, but it is now a
real candidate path. The next proof should reduce the small-page Tor-check
risk without losing the homepage queue win, or run a broader repeat that proves
the Tor-check loss is noise.

Guard-only healthy-over-cold follow-up:
Arti now also has the default-off lab env
`TORFAST_EXIT_SELECT_HEALTHY_OVER_COLD_GUARD_ONLY_MIN_ASSIGNED`, and
`tools/run_browser_compare.py` can test it with
`--extra-arti-exit-select-healthy-over-cold-guard-only-min-assigned`. This
profile does not set `TORFAST_EXIT_SELECT_LOAD_AWARE`. Static quality config
passed (`74` checks), `python3 -m unittest tests.test_browser_quality` passed
after the runner wiring (`174` tests), `cargo test -p tor-circmgr
healthy_over_cold` passed, and release Arti rebuilt.

First guard-only proof
`results/browser-compare-20260612T164209/browser-compare.json`, with analyzer
output at `results/browser-compare-20260612T164209/analysis.md`, passed
quality. It was safe but not a mechanism proof: the guard-only profile made
`0` selection moves. Median load was slightly better than base Arti on both
targets (`1169.360ms` versus `1180.465ms` on Tor check, `4506.674ms` versus
`4560.847ms` on the Tor Project homepage), but this cannot be credited to the
new guard because it never fired.

Revised guard-only proof
`results/browser-compare-20260612T165435/browser-compare.json`, with analyzer
output at `results/browser-compare-20260612T165435/analysis.md`, failed
quality. The guard-only profile had a `90s` navigation timeout on Tor check
run `1`, and it still made `0` selection moves. The successful Tor-check runs
were also slower than base Arti (`1995.813ms` median across successful guard
runs versus base `948.971ms`). Decision: guard-only is not promotable and is
not the next speed path unless a future proof shows actual guarded moves with
no Tor-check proof failures.

Selector-move risk diagnostic:
`tools/analyze_browser_compare.py` now has an `Arti Profile Selector Move Risk`
table that joins profile A/B load results with real selector moves and SOCKS
connect waits. On the clean threshold `1` proof, Tor check had `12` load-aware
picks but `0` selected-nonfirst or healthy-over-cold moves; it still lost
paired load `1/3` with a `+451.974ms` paired median delta and max candidate
connect `3316ms`. The homepage had `54` load-aware picks, `22` selected-nonfirst
picks, and `12` healthy-over-cold moves; it won paired load `3/3` with a
`-2042.982ms` paired median delta. On the guard-only failed proof, both targets
had `0` guard-only moves. Meaning: the homepage win is tied to real
healthy-over-cold moves, but the small Tor-check loss is not explained by that
move and should be treated as CONNECT/circuit-readiness or run-window risk
before another selector patch.

Source quality correction:
`torfast_socks_connect_soft_timeout()` now returns `None` when
`TORFAST_SOCKS_CONNECT_SOFT_TIMEOUT_MS` is unset. Before this local lab code
silently used a `5000ms` SOCKS CONNECT soft timeout even without the env var,
which broke the default-off promise for that lab knob. This restores the
default path while keeping explicit bounded env testing available. Proof:
static quality config passed with `74` checks at
`results/arti-quality-config-20260612T180935/arti-quality-config.json`,
Python tests passed (`178` tests), `cargo test -p arti connect_hedge` passed
(`2` tests), the Arti format check passed, and release Arti rebuilt.

Hedge-plus-guard proof:
`tools/run_browser_compare.py` now lets the extra SOCKS CONNECT hedge profile
inherit the base healthy-over-cold selector threshold, so a same-window run can
compare threshold-only against threshold plus hedge. Unit proof passed. Fresh
Tor-check run `results/browser-compare-20260612T174909/browser-compare.json`,
with analyzer output at
`results/browser-compare-20260612T174909/analysis.md`, passed quality. The
threshold-plus-`500ms` hedge profile beat threshold-only Arti by median load
(`1289.583ms` versus `1445.873ms`) and beat local C Tor by median load
(`1289.583ms` versus `1427.925ms`). It won paired load `2/3` against
threshold-only Arti with paired median delta `-156.290ms`.

This is not hedge promotion proof. The result counted `0` connect hedge
launches, successes, skips, or retries. The candidate max tail was worse
(`2355.698ms` versus `1594.126ms`), and the worst candidate run was explained
by a selected-circuit hostname relay DATA gap of `4788ms`, not by CONNECT wait.
Decision: keep the SOCKS CONNECT hedge lab-only. This run moves the small-page
risk back to selected-circuit relay-data gap proof.

Health-aware selector proof:
Tor-check-only run `results/browser-compare-20260612T175827/browser-compare.json`,
with analyzer output at
`results/browser-compare-20260612T175827/analysis.md`, passed quality and looked
faster on the small page. The health-aware profile beat threshold-only Arti by
median load (`1512.128ms` versus `1646.270ms`) and won paired load `2/3` with a
paired median delta of `-304.786ms`. This was still weak proof: the selector
move table showed `18` load-aware picks but `0` selected-nonfirst,
healthy-over-cold, or guard-only moves, so the win was not tied to the intended
mechanism.

Broader same-window run `results/browser-compare-20260612T180307/browser-compare.json`,
with analyzer output at
`results/browser-compare-20260612T180307/analysis.md`, also passed quality but
rejected health-aware as a speed direction. Health-aware lost paired load `0/3`
on both targets. On Tor check it was slower by paired median load `+762.282ms`
and max load `+1183.149ms`. On the Tor homepage it was slower by paired median
load `+2733.027ms` and max load `+3721.278ms`; median load was `8275.002ms`
versus threshold-only Arti at `5146.655ms` and local C Tor at `4876.765ms`.
The risk table flags paired median slower, summary median slower, max tail
worse, and low paired wins for both targets. Decision: keep the health-aware
selector lab-only and do not promote it.

Analyzer update:
`tools/analyze_browser_compare.py` now prints an
`Arti Selected-Circuit Gap Predictability` table. On the broader run, the bad
health-aware homepage row shows a `5027ms` actual selected-circuit DATA gap, but
the selected circuit already had bad-health rows and no logged better open
alternative (`only selected open circuit logged`). Meaning: this is not proof
for broad health-aware selection. The next proof is a narrow "only bad open
circuit" path, such as safe capacity, top-up, or pending-wait proof, not another
open-candidate selector tweak.

Follow-up analyzer update:
`tools/analyze_browser_compare.py` now also prints a
`Torfast Bad-Health Replacement Lifecycle` table. On
`results/browser-compare-20260612T180307/analysis.md`, the bad health-aware
homepage run 3 row shows the background replacement did launch and build:
pending `0xb398b1b10`, built circuit `Circ 1.56`, fallback circuit `Circ 1.55`,
build age `707ms`, selected health score `13662`, selected health gap `422ms`.
But after build it had `5` open picks, `0` built-circuit candidate opens, `0`
selected opens, `0` linked streams, and reason
`replacement circuit never appeared in later open candidates`. Meaning: the
current background replacement is not enough for the exact bad case; the next
source proof must make the replacement usable in time or explain why it gets
filtered before later open selection.

Runtime diagnostic update:
`upstream/arti/crates/tor-circmgr/src/mgr.rs` now marks bad-health replacement
circuits with diagnostic-only lifecycle state, without making them same-isolation
top-ups or changing selector order. The fresh focused proof
`results/browser-compare-20260612T184429/browser-compare.json`, with analyzer
output at `results/browser-compare-20260612T184429/analysis.md`, passed quality.
Health-aware Arti median homepage load was `4107.730ms`; base Arti was
`4806.386ms`; local C Tor was `5002.197ms`. The new table shows why the
replacement itself is not the safe speed fix yet: one base replacement was
filtered by isolation, one base replacement was selected and used, and the two
health-aware replacements were skipped because a better-health circuit won.
Validation passed: Python compile, `tests.test_browser_quality`
and `tests.test_arti_quality_config` (`181` tests), static quality config
(`74` checks, `results/arti-quality-config-20260612T190410/arti-quality-config.json`),
`cargo fmt --manifest-path upstream/arti/Cargo.toml --package tor-circmgr --check`,
and `cargo test -p tor-circmgr bad_health --manifest-path upstream/arti/Cargo.toml`
(`5` tests).

Meaning: the runner can test the SOCKS connect hedge cleanly, but none of the
new hedge runs proved a real hedge event. The byte-timing proof moved the
source target back to selected-circuit stream gaps. Health-aware, lower spread,
and SOCKS CONNECT hedge are still lab-only. The healthy-over-cold guard is
narrower and did fire at threshold `1`, but the guard-only follow-up did not
fire and then failed quality on repeat. The current source target is
selected-circuit stream-gap proof or a different narrow trigger that handles an
already-bad selected circuit without small-page Tor-check risk.

## What this proves

- C Tor builds locally from official upstream source.
- Arti builds locally from official upstream source.
- Both can run as local SOCKS proxies and reach real websites through Tor.
- Release Arti can beat stock C Tor on small SOCKS fetches in a fresh local run.
- Changing C Tor `ConfluxClientUX` did not improve the earlier small fetch test.
- A verified Tor Browser 15.0.15 test copy can load real pages through bundled
  Tor, local C Tor, and release Arti external SOCKS proxies.
- Browser runs saved screenshots and proxy prefs for proof.
- `tools/analyze_browser_compare.py` passed on the latest browser results and
  now prints browser performance timing, the slowest page resources, proxy log
  signals, and Arti SOCKS/HsPool/HS/client timing rows plus relay byte counts
  relay receive queue rows, stream scheduler rows, circuit assignment summaries,
  resource connection-shape rows, SOCKS-to-relay receive join rows and per-run
  summaries, relay receive stream and circuit gap rows, nearest
  browser-navigation/resource-to-SOCKS join rows, compact resource-to-relay
  summary rows, resource type/top-resource deltas versus local C Tor, direct
  baseline Arti versus extra Arti profile resource A/B deltas, direct resource
  HTTP-phase and HTTP queue-shape A/B deltas, direct top-resource relay-context
  A/B rows, per-circuit relay quality rows plus run summaries, load-aware
  selected-vs-first health outcome rows, and browser resource stream-gap and
  byte-context rows when those logs or resource rows are present. It now also
  prints an Arti profile selector-move risk table that ties A/B load deltas to
  real selector moves and SOCKS connect waits.
- `tools/check_c_tor_circuits.py` passed on local C Tor and checked observable
  circuit quality.
- `tools/check_arti_quality_config.py` passed on local Arti source/config.
- `tools/check_arti_rpc_path.py` passed on an RPC-enabled Arti build and checked
  3 live paths with C Tor directory validation.
- `tools/run_cache_diagnostic.py` shows Arti warm directory-cache boot is fast,
  but this did not make Arti a browser-speed winner.
- `tools/run_browser_compare.py --warm-cache --compact-output` shows Arti
  browser boot can also be very fast from warm cache.
- `tools/run_browser_compare.py --post-boot-wait 12` shows waiting for circuit
  readiness helps Arti page load, but still does not beat C Tor.
- A local Arti lab patch changed preemptive circuit recheck from `10s` to `1s`.
  This improved no-wait browser timing.
- A second local Arti lab patch makes SOCKS CONNECT use optimistic streams,
  matching C Tor's optimistic-data behavior for normal exit streams.
- A third local Arti lab patch keeps normal exit-stream selection at width `1`
  by default, with a bounded env override for same-window A/B tests of wider
  values. It does not change isolation rules or launch extra circuits.
- The trusted sequential patched 5-run browser sample uses `IsolateSOCKSAuth` for
  both C Tor SOCKS listeners. It shows Arti still loses on page-only load, but
  still wins launch-to-load because warm-cache Arti boot is much faster.
- `tools/run_browser_compare.py --schedule interleaved` now keeps measured
  proxies running in the same window and rotates browser loads across profiles.
- `tools/run_browser_compare.py --byte-tap` can put the same neutral local TCP
  byte-timing tap in front of bundled C Tor, local C Tor, and Arti. It saves
  byte counts, SOCKS reply timing, and first real stream-data timing without
  saving payload bytes.
- `tools/run_browser_compare.py` now keeps key proxy signal lines separately
  from the noisy proxy-output tail. This keeps circuit-selection, SOCKS timing,
  HS timing, and scheduler lines visible even when relay receive logs are large.
- `tools/run_browser_compare.py` now filters run-level proxy evidence to each
  browser run's own timestamp window. This keeps boot, idle, and later-run Arti
  rows from being counted inside the wrong failed browser run.
- The analyzer now also keeps and counts generic stream-reactor congestion block
  lines. This tells us when ready stream data is stopped by the circuit
  congestion gate.
- The analyzer now prints a per-run circuit-shape table for joined SOCKS/relay
  streams. It shows how many streams and bytes each circuit carried, plus the
  largest receive span and gap on that circuit.
- The analyzer now also prints a direct `Arti Profile A/B` table for extra Arti
  profiles. This keeps baseline-vs-candidate median deltas and max-load tail
  deltas visible in same-window tests.
- The analyzer now also prints direct Arti profile resource type, top-resource,
  and load-tail A/B tables. This shows whether an extra Arti profile loses in
  exact resource groups after first response.
- The analyzer now also prints direct Arti profile resource HTTP-phase A/B rows.
  This splits slow resource rows into fetch-to-request, request-wait, receive,
  fetch-to-response, protocol, and zero-connect-setup counts.
- The analyzer now also prints direct Arti profile HTTP queue-shape A/B rows.
  This checks whether a candidate changed whole-protocol queue counts, zero
  connect setup, and median/max fetch-to-request timing.
- The analyzer now also prints a direct Arti profile top-resource relay-context
  A/B table. It joins the worst resource losses to nearest SOCKS/relay timing
  and shows match confidence, timing id, circuit, relay time, and receive gap.
- When byte-tap data is present, the analyzer now also prints
  `Browser Resource To Byte Tap Connection Join (nearest)`. This maps slow
  browser resources to the nearest neutral tap connection and shows connection
  id, stream-data timing, bytes, and tap data gaps.
- The analyzer now also prints `Browser Resource Byte Tap Connection Groups`.
  This ranks slow resources by neutral tap TCP connection, with high-confidence
  counts, slow-row medians, stream bytes, max data gap, and top resources.
- The analyzer now also prints `Browser Resource Byte Tap Groups With Relay
  Context`. This joins each slow tap connection group to nearest Arti
  SOCKS/relay stream rows, including timing id, circuit, stream, relay time,
  relay gap, and relay bytes.
- Interleaved browser runs now save per-run proxy signal lines and per-run relay
  context lines. This keeps middle-run Arti stream evidence instead of only the
  final proxy tail.
- The analyzer now also prints a direct `Torfast SOCKS Connect Retries` table
  and target-kind max CONNECT rows. This keeps `TorNetworkTimeout` retries and
  onion-vs-hostname connect waits visible.
- Local Arti source now has a default-off load-aware open-circuit selection lab
  mode. It keeps the same eligibility and isolation checks, uses only already
  open circuits, and does not build extra circuits.
- The first same-window homepage load-aware A/B passed quality. Baseline Arti
  median load was `6207.200ms`; load-aware Arti was `3449.575ms`; local C Tor
  was `3455.741ms`. The load-aware profile made `26` load-aware exit picks.
- The wider 5-run, 3-target load-aware A/B also passed quality. Load-aware Arti
  beat baseline Arti by median load on all three targets, but it had a bad
  download-page tail: max load `65953.543ms` versus baseline `11525.708ms`.
- A focused load-aware plus non-onion SOCKS soft-timeout profile passed quality
  on the download page and beat both load-aware baseline Arti and local C Tor in
  that window. But the analyzer found `0` soft timeouts, so this does not prove
  the exact earlier 60s CONNECT tail is fixed.
- A lower `1000ms` non-onion SOCKS soft-timeout A/B also passed quality, but it
  was slower by median load and still had `0` soft timeouts. In that run the
  slow connect waits were `.onion` side requests, which the timeout correctly
  skips.
- The same pending-exit hedge lab timer now also covers the initial build wait
  path. A download-page `1500ms` A/B passed quality and counted `1` pending
  hedge, but `0` build hedge timers. It was slower than load-aware baseline
  Arti, so it is not a speed direction or default.
- A no-warm-cache download-page `500ms` hedge A/B passed quality and counted
  `1` build hedge timer plus `1` pending hedge. It was still slower than
  load-aware baseline Arti by median load, so the hedge remains lab-only.
- A follow-up no-warm-cache `500ms` profile run with `--byte-tap` also passed
  quality. In that tap window the `500ms` profile was faster by median load, but
  it counted `0` hedge timers, so treat it as connection-shape proof, not hedge
  speed proof.
- The earlier rotating interleaved 5-run browser sample passed quality. With the
  exit-spread patch, Arti wins page-only load against bundled C Tor on both
  targets, loses page-only load against local C Tor on both targets, and wins
  launch-to-load on both targets.
- The newer rotating interleaved 3-run browser sample without the byte tap
  passed quality. In this run, Arti beat both bundled C Tor and local C Tor on
  page-only load and boot+load for both targets. This is the first normal
  browser sample where patched Arti beats local C Tor on both pages.
- The neutral byte-tap 3-run sample also passed quality. It showed
  median first stream-data-to-browser time of `401.870ms` for Arti,
  `604.255ms` for bundled C Tor, and `644.909ms` for local C Tor.
- The latest rotating interleaved 5-run browser sample added a third target and
  passed quality. Arti beat bundled C Tor on page-only load and boot+load for
  all three targets. Arti still lost page-only load to local C Tor on the two
  larger pages, so the final speed goal is still not met.
- The latest accepted same-window normal no-debug A/B used 5 runs and 3 targets
  with bundled C Tor skipped. It shows width `3` is not a better default:
  control width `1` beat width `3` on all three target medians.
- A fresh default-width run with no exit-select env override passed quality and
  proves the current rebuilt Arti binary really uses width `1` by default. It
  still loses page-only load to local C Tor on all three targets, while fast
  Arti boot keeps boot+load competitive on two targets.
- A runner-only `--arti-min-exit-circs-for-port 3` lab test passed quality but
  made the homepage much slower. It is rejected as a speed direction.
- The latest 3-run homepage resource-shape proof passed quality. It shows Arti
  and local C Tor used the same one-origin, mostly HTTP/1.1 browser resource
  shape, but Arti still had a longer request-start span and larger resource-tail
  gaps.
- The latest warm-cache homepage proof with stream-reactor congestion logs
  passed quality. Arti beat local C Tor on page-only load and boot+load, but
  showed `0` stream-reactor congestion blocks and `0` scheduler hop blocks.
- A focused 3-run neutral byte-tap homepage proof passed quality. With the tap
  in front of both proxies, Arti won page-load, had fewer measured SOCKS data
  connections, and had faster median first stream data than local C Tor. This is
  diagnostic only because the byte tap is a measurement hop.
- A focused 2-run no-tap debug homepage proof passed quality. Arti lost page
  load but won boot+load, and the new internal relay per-run table exposed
  receive spans, stream counts, and a `4000ms` receive gap in one run.
- A newer 2-run no-tap debug homepage proof rebuilt Arti with
  millisecond-resolution relay receive `event_epoch_ms` fields. It passed
  quality, but Arti was much slower in this debug run. The useful proof is that
  relay receive gaps are real sub-second/multi-second gaps, not just rounded log
  timestamps.
- The newest 2-run joined no-tap debug homepage proof adds a SOCKS
  `timing_id` to Arti circuit/stream join table. It passed quality and proves
  the analyzer can now map SOCKS streams to exact internal relay receive spans
  and gaps.
- The newest stream receiver diagnostic adds Arti stream read/SENDME timing
  logs and analyzer gap-context rows. It can now overlay stream receiver reads,
  receive-window values, SENDME sends, and queued bytes on an exact joined relay
  receive gap.
- A later 5-run debug homepage proof reproduced a bad Arti tail and mapped it
  to a slow pending exit circuit wait, not stream receiver/SENDME pressure.
- Local Arti source now has a default-off, bounded pending-exit-circuit hedge
  for lab A/B tests. The first same-window hedge A/B did not exercise the hedge
  and failed quality, so it is not speed proof.
- Two post-patch normal 5-run, 3-target proofs passed quality after adding a
  narrow retry for transient Arti SOCKS CONNECT `TorNetworkTimeout` failures.
  Arti won the two larger Tor Project pages in both full gates, while
  `check.torproject.org` stayed mixed by page-only load.
- Local Arti source now has a default-off bad-health guard for load-aware
  open-circuit selection. It only avoids already eligible open circuits when
  recent relay DATA evidence is fresh and clearly bad; unknown, cold, or stale
  circuits are not treated as bad.
- The focused `20260608T003712` retained-tail browser proof passed quality on
  the download page. Base Arti load was `5365.140ms`, health-aware plus
  bad-health guard was `3122.296ms`, plain load-aware plus bad-health guard was
  `3467.987ms`, and local C Tor was `5030.610ms`. Relay gap tails also improved:
  base Arti max relay gap was `1011ms`, health-aware was `352ms`, and load-aware
  was `230ms`. This is promising but still a one-run debug proof, so it remains
  lab-only.
- The wider same-window `20260608T004859` debug proof passed quality but
  rejected that first bad-health guard shape. Plain health-aware was best at
  `3562.335ms` median load. Base Arti was `4631.022ms`, local C Tor was
  `4469.264ms`, plain load-aware was `4963.036ms`, load-aware plus bad-health
  guard was `5102.284ms`, and health-aware plus bad-health guard was much worse
  at `10710.535ms`. The guard could move away from a bad circuit onto an
  unknown or weak circuit, so it is not a promotion path.
- Local Arti source now tightens the bad-health guard: it can avoid a bad
  selected circuit only when another eligible circuit has fresh good health
  evidence. Unknown, cold, or stale circuits are not enough reason to move.
  The rebuilt `20260608T005748` one-run smoke check passed quality in a slow
  window; load-aware plus the tightened guard was `3865.683ms`, health-aware
  plus the tightened guard was `4419.023ms`, base Arti was `8295.104ms`, and
  local C Tor was `10750.993ms`. This is smoke proof only, not promotion proof.
- The repeated same-window `20260608T010444` debug gate passed quality. The
  tightened health-aware guard was best at `4481.908ms` median load. Base Arti
  was `7636.023ms`, plain health-aware was `4894.313ms`, plain load-aware was
  `6068.906ms`, load-aware plus the tightened guard was `5927.750ms`, and local
  C Tor was `11648.196ms`. Browser load tails improved too: base Arti max load
  was `9137.651ms`, while the tightened health-aware guard max was
  `6196.668ms`. This is promising, but still lab-only because it is a debug
  one-target gate and local C Tor was slow in that network window.
- The low-log, no-debug, same-window `20260608T011500` 3-target gate passed
  quality, but rejected tightened health-aware guard promotion. The guarded
  profile had good median loads on `check.torproject.org` (`1377.008ms`) and
  the homepage (`6812.258ms`), but it lost to base Arti on paired median load on
  the download page by `690.079ms` and had bad tails: `62471.482ms` on
  `check.torproject.org` and `20819.463ms` on the download page. Base Arti's
  max loads in the same gate were `2855.357ms`, `9433.641ms`, and
  `8438.594ms`. Keep the guard default-off.
- The focused debug `20260608T012700` replay passed quality and did not
  reproduce the 60s first-response stall, but it confirmed the download-page
  loss shape: guarded selector median load was `9634.479ms` versus base Arti
  `4716.176ms`, with `6` joined streams on one circuit in runs `2` and `3`.
- The runner now has a focused same-window lab profile for health-aware plus
  bad-health guard plus same-isolation target. The first `20260608T013207`
  download-page check passed quality but rejected target `2`: base Arti was
  `3610.841ms`, guarded selector was `3577.011ms`, and guarded selector plus
  same-isolation target `2` was much slower at `10043.645ms`.
- The focused `20260608T013809` download-page check passed quality but rejected
  the guarded selector with minimum assignment spread `2`: base Arti median load
  was `4610.687ms`, guarded spread `2` was slower at `7525.410ms`, and local C
  Tor was `4467.486ms`. The guarded spread `2` tail was also worse
  (`14123.421ms` max load versus base Arti `8023.550ms`), so keep it off.
- The runner now has a same-window health-aware threshold profile through
  `--extra-arti-exit-select-health-min-move-score-bps`. The first threshold
  debug check `20260608T014735` failed quality because base Arti hit
  `about:neterror` timeout on run `2` after `61265.920ms`. Do not treat it as
  speed proof. Inside the accepted rows, default health-aware was best
  (`4282.921ms` median load), `131072` was slower (`5535.406ms`), and `32768`
  was clearly bad (`13738.993ms`) with slow relay/resource tails. Reject
  `32768`; threshold tuning is not the next promotion path.
- The analyzer now prints `Browser Failed Run Torfast SOCKS Streams` right
  after failed runs. Re-analyzing `20260608T014735` shows the base Arti timeout
  had two hostname streams stuck in relay for about `60s` (`60167ms` and
  `59810ms`) and one onion stream with `3179ms` connect plus `56021ms` relay.
  New debug logs also report the last Tor-to-browser byte and idle time after
  that last byte, so the next failed run can separate no-data waits from
  after-data idle waits.
  This points the next source work at relay/stream timeout handling, not browser
  prefs or simple selector threshold tuning.
- `results/browser-compare-20260608T020551/browser-compare.json` rebuilt release
  Arti and reran a 2-run warm-cache download-page debug proof. It passed quality
  but did not prove speed: Arti median load was `4129.896ms`, local C Tor was
  `3464.572ms`, and paired Arti load delta was `+665.324ms`. The new last-byte
  split showed median last Tor byte `2457.500ms`, median idle after last Tor
  byte `265.500ms`, and max idle after last Tor byte `3240.000ms`. Some long
  relay totals are close-idle, so the next speed work should focus on active
  resource/byte timing, not blindly cutting SOCKS relay lifetime. The
  resource-to-SOCKS join now also prints response-end-after-last-byte fields;
  in this run the median was negative (`-883.959ms`), so many matched resources
  ended before the joined stream's last Tor byte and the next source target is
  HTTP/resource queue timing unless later evidence says otherwise. The resource
  connection table now prints queue-tail counts: Arti had `22` resources with
  fetch-to-request delay at least `1000ms`, versus local C Tor `15`; Arti max
  fetch-to-request was `2450.049ms` versus `2050.041ms`. The new
  `Resource Queue Delta vs Local C Tor` table makes the gap direct: Arti had
  `+7` more HTTP/1.1 resources queued at least `1000ms`, `+2` more queued at
  least `500ms`, and max fetch-to-request was `+400.008ms` worse. The new
  `Resource Queue Slot Saturation` table shows most of that tail starts when
  normal same-origin HTTP/1.1 slots are already full: Arti had `21/22`
  resources queued at least `1000ms` at slot depth `>=6`, versus local C Tor
  `11/15`; both had median/max slot depth `6`. Keep browser caps unchanged and
  make the underlying resource/stream work finish earlier. The new
  `Resource Queue Slot Blockers` table shows the concrete final slot holders.
  The worst Arti queued resource, `tor-logo@2x.png`, started at slot depth `6`
  behind `5` same-origin blockers; its top high-confidence blocker was
  `SourceSansPro-Bold.ttf` on timing id `9` / `Circ 1.2`, with `516.677ms`
  left, all of it in receive/body time; the same queued row also had up to
  `400.008ms` first-byte wait left on another blocker. The high-confidence
  blocker still had Arti writes `532.677ms` after the queued request started,
  and browser response end was only `-16.000ms` from the last Arti write. This
  points before/during Arti byte delivery, not a browser post-write lag. The
  same high-confidence blocker had `0.000ms` write-after-relay and `0.000ms`
  write-after-stream-receiver-read, with max receiver queued bytes only
  `3948`, so the late part is final relay/read arrival timing, not SOCKS copy
  write lag. After the queued request started, that high-confidence blocker
  still received `121523` relay bytes from `+172.677ms` to `+532.677ms`, with
  only a `51.000ms` max after-queue relay gap. That points to a broad late
  circuit/stream arrival burst, not one stuck local queue. The comparable top
  local C Tor row had only `100.002ms` max blocker time left, split into
  `16.667ms` wait and `83.335ms` receive. In run 2, Arti's `get-connected.svg` /
  `stay-safe.svg` queue rows were blocked by high-confidence timing id `18` /
  `Circ 1.5` holders with `366.674ms` max time left. The next source check
  should inspect circuit/stream scheduling for late relay bursts, not change
  browser caps. Source now keeps normal selector behavior unchanged but logs
  candidate assignment and health summaries even when the load-aware selector is
  off, so the next debug browser replay can tell whether those late blockers had
  better open-circuit choices available. The new
  `Browser Resource Queue To SOCKS Relay Tail` table lists the worst queued
  resources with nearest SOCKS/circuit context. The top row was
  `tor-logo@2x.png` at `2450.049ms` fetch-to-request, high-confidence timing id
  `8` on `Circ 0.0`, with only a `363ms` receive gap. Several next rows mapped
  to timing id `9` on `Circ 1.2`, but many were low-confidence nearest matches,
  so treat clustering as a clue, not proof. The new high-confidence
  `Browser Resource Queue To SOCKS Relay Clusters` table is cleaner: run 2
  timing id `18` on `Circ 1.5` had `21` queued resources (`8` over `1000ms`),
  run 1 timing id `8` on `Circ 0.0` had `11` (`4` over `1000ms`), and run 1
  timing id `9` on `Circ 1.2` had `4` (`2` over `1000ms`).
- `results/browser-compare-20260608T030643/browser-compare.json` is the clean
  skip-bundled replay after normal-selector candidate logging was added. It
  passed quality, but it is not speed proof: Arti median load was
  `4369.638ms`, local C Tor was `3669.699ms`, and paired Arti load delta was
  `+699.939ms`. If boot time is counted, Arti was faster
  (`4737.638ms` boot+load versus local C Tor `6308.699ms`), but page-only load
  is still slower, so do not promote a speed feature from this run. Browser
  connection caps stayed unchanged. The queue gap stayed visible: Arti had
  `25` resources queued at least `1000ms` versus local C Tor `16`, and Arti had
  `23` such rows at slot depth `>=6` versus local C Tor `8`. The new
  `Browser Resource Queue Selection Context` table joined queue clusters to
  normal selector candidate summaries. Run 1 `Circ 0.4` clusters had some early
  alternatives with better health, but the selected circuit later reached a
  health score of `248663` while the best alternative score in those rows was
  `24550`; that does not prove a simple health-pick would help. Run 2 timing id
  `18` picked cold `Circ 1.6` over a busy high-score `Circ 0.5`, but `Circ 1.6`
  itself had only a `63ms` max receive gap, so this is not obvious bad
  selection. The worst run 2 cluster, timing id `17` on `Circ 0.5`, had six
  selected rows and no multi-candidate choice. Next work should not promote the
  selector yet; inspect same-isolation capacity/readiness and earlier resource
  completion under unchanged browser caps.
- Source now decouples `TORFAST_EXIT_SAME_ISOLATION_TARGET` from load-aware
  selection. The extra same-isolation browser profile also no longer silently
  enables load-aware, so it can test capacity alone. The later source guard
  adds `TORFAST_EXIT_SAME_ISOLATION_MIN_ASSIGNED_STREAMS`, default `2`, so
  lab top-up no longer fires after only one reused stream. The static quality
  check first saved
  `results/arti-quality-config-20260608T034428/arti-quality-config.json` with
  `25` passing checks; the latest stricter lifecycle/health-gated check saved
  `results/arti-quality-config-20260608T061540/arti-quality-config.json` with
  `25` passing checks. The latest source/config check also covers the
  default-off unknown-health fallback guard and saved
  `results/arti-quality-config-20260608T121551/arti-quality-config.json` with
  `26` passing checks.
- `results/browser-compare-20260608T032051/browser-compare.json` tested
  capacity-only target `2`. It passed quality and the profile was faster in
  that window, but it counted `0` same-isolation top-ups, so it is not source
  proof.
- `results/browser-compare-20260608T032422/browser-compare.json` tested
  capacity-only target `4`. It passed quality, kept load-aware off (`0`
  load-aware open picks), kept browser connection prefs unchanged, and counted
  `3` same-isolation top-ups with `0` failures. Sameiso4 median load was
  `4646.399ms` versus baseline Arti `9463.184ms` and local C Tor
  `6524.087ms`; paired against baseline it won `1/2` runs but cut the bad
  baseline tail (`4822.725ms` max load versus `14876.409ms`). HTTP/1.1 queue
  shape improved: queued `>=500ms` fell to `50/70` from `59/70`, median
  fetch-to-request was `150.003ms` lower, and max fetch-to-request was
  `1233.358ms` lower. This was a useful lab lead, but the wider low-log gate
  below overturned it.
- `results/browser-compare-20260608T033012/browser-compare.json` tested
  capacity-only targets `3` and `4` across check, homepage, and download with
  low Arti logs. It passed quality and kept browser connection prefs unchanged.
  Load-aware stayed off. Target `3` made `9` same-isolation top-ups and target
  `4` made `12`, both with `0` failures, so the feature activated cleanly.
  But both were slower than baseline Arti on the wider gate:
  - Check page median load: baseline `1144.710ms`, target `3`
    `1667.877ms`, target `4` `2512.488ms`.
  - Homepage median load: baseline `3418.458ms`, target `3`
    `6292.145ms`, target `4` `9237.596ms`.
  - Download median load: baseline `6828.342ms`, target `3`
    `14242.911ms`, target `4` `9716.223ms`.
  Target `4` also had a bad accepted homepage tail of `51463.133ms`. This
  rejects simple same-isolation capacity targets `3` and `4` as speed proof.
  Keep the knob lab-only.
- `results/browser-compare-20260608T034639/browser-compare.json` tested the
  stricter default floor `min_assigned_streams=2` across check, homepage, and
  download. It passed quality, kept load-aware off, and kept browser connection
  prefs unchanged. Target `3` made `8` top-ups and target `4` made `16`, both
  with `0` failures. Target `3` beat baseline on the download median
  (`3541.465ms` vs `3992.234ms`) but lost check and homepage, and its download
  max tail was worse (`9122.746ms` vs `4643.475ms`). Target `4` beat check but
  lost homepage and download. This is not default-ready.
- `results/browser-compare-20260608T035149/browser-compare.json` tested a still
  stricter target `3` floor, `min_assigned_streams=3`, on homepage and
  download. It passed quality and made only `2` top-ups with floor `3`, but it
  lost both targets to baseline Arti: homepage median `6268.137ms` vs
  `5798.988ms`, and download median `8752.130ms` vs `4944.291ms`. Raising the
  floor alone is rejected.
- `results/browser-compare-20260608T035831/browser-compare.json` tested the
  lower target `2` shape with the default floor `min_assigned_streams=2` across
  check, homepage, and download. It passed quality, kept load-aware off, and
  kept browser connection prefs unchanged. Sameiso2 made `3` top-ups with `0`
  failures. It beat baseline summary median on check (`2792.791ms` vs
  `3580.344ms`) and was close on homepage (`4492.307ms` vs `4526.299ms`), but
  A/B paired medians were weak and the homepage max tail was worse
  (`10935.026ms` vs `6846.781ms`). Download rejects it: median load
  `10049.471ms` vs baseline `6199.955ms` and local C Tor `5041.641ms`. Do not
  promote target `2`; same-isolation capacity count alone is not enough.
- The analyzer now prints `Arti Profile Same-Isolation Top-Up A/B`, splitting
  paired candidate runs into top-up-attempt and no-attempt buckets. On
  `results/browser-compare-20260608T035831/browser-compare.json`, target `2`
  top-up attempts were mixed rather than cleanly helpful: homepage had `1/1`
  attempt win, but download attempt runs had median load `14997.160ms` vs
  paired baseline `14508.584ms` and max `19944.848ms`. This points away from
  simple top-up count and toward a later signal that understands page/resource
  tail risk before adding capacity.
- Source now adds `TORFAST_EXIT_SAME_ISOLATION_REQUIRE_BAD_HEALTH`, still
  default-off and lab-only. When enabled, same-isolation top-up must pass the
  reuse floor and the selected circuit must have recent bad local RELAY DATA
  health. `results/browser-compare-20260608T041700/browser-compare.json` is
  useful but not clean speed proof: baseline Arti failed homepage run 3 with a
  `netTimeout`, while the health-gated sameiso2 profile itself finished `3/3`
  runs on all three targets.
- `results/browser-compare-20260608T042223/browser-compare.json` is the clean
  focused proof for the health-gated sameiso2 lead. It passed quality, kept
  browser prefs unchanged, made `1` top-up with `0` failures, and that top-up had
  `selected_has_bad_health=true` plus `require_bad_health=true`. Check-page
  median load improved to `1141.113ms` from baseline Arti `1477.262ms` and was
  close to local C Tor `1088.146ms`. Download-page median load improved to
  `3429.635ms` from baseline Arti `4220.258ms` and local C Tor `5445.822ms`.
  Paired A/B medians improved by `336.149ms` on check and `790.623ms` on
  download. Keep it lab-only: the run used only two targets and three runs, and
  the download max tail was still worse than baseline.
- `results/browser-compare-20260608T042918/browser-compare.json` repeated the
  health-gated sameiso2 shape across check, homepage, and download with `5`
  interleaved runs. It passed quality, kept browser connection prefs unchanged,
  kept load-aware off, and made `7` same-isolation top-ups with `0` failures;
  every top-up had `selected_has_bad_health=true` and `require_bad_health=true`.
  Sameiso2 won summary median load on check (`1362.277ms` vs baseline Arti
  `1783.925ms` and local C Tor `1780.515ms`) and download (`5594.804ms` vs
  baseline Arti `32294.919ms` and local C Tor `8284.527ms`). Homepage summary
  median was slightly slower than baseline Arti (`5311.680ms` vs `4762.142ms`)
  but faster than local C Tor (`5609.184ms`), and paired A/B versus baseline was
  slightly better (`-130.013ms`). Max load tails were much better than baseline
  Arti on all three targets, but homepage max was still worse than local C Tor
  (`12419.421ms` vs `6413.506ms`).
- `results/browser-compare-20260608T044143/browser-compare.json` repeated the
  same 5-run, 3-target gate. It also passed quality and kept browser prefs
  unchanged, with `8` same-isolation top-ups and `0` failures. This repeat did
  not confirm the speed win. Baseline Arti beat sameiso2 on all three summary
  medians: check `1511.730ms` vs `1553.519ms`, homepage `3617.257ms` vs
  `7044.966ms`, and download `5161.736ms` vs `6109.541ms`. Sameiso2 still beat
  local C Tor on check and download medians, but lost homepage median slightly
  (`7044.966ms` vs `6927.481ms`) and had a bad accepted homepage max tail
  (`64615.774ms`). Decision: health-gated sameiso2 stays lab-only and is not a
  promotion path yet. The next safe work should explain or prevent the homepage
  top-up tail before another promotion gate.
- Source and analyzer now log/display selected-circuit top-up health details:
  `selected_health_max_gap_ms`, `selected_health_score_bps`, and
  `selected_health_age_ms`. This is diagnostic only, not a behavior change; the
  next proof can show whether the bad homepage top-up was caused by stale,
  low-score, or high-gap local circuit health.
- `results/browser-compare-20260608T045852/browser-compare.json` is diagnostic
  only. Quality failed because baseline Arti homepage run 2 hit `netTimeout`
  after `62884.827ms`. The health-gated sameiso2 profile itself finished `8/8`
  homepage runs with median load `4318.9765ms`, max load `9651.001ms`, `3`
  top-ups, and `0` top-up failures. The new selected-health fields worked:
  top-up max health gap was `338ms`, min health score was `14869`, and max
  health age was `37ms`. This points to low-score selected circuits, not stale
  health or a high local gap, but it is not speed proof because baseline failed.
- The existing combined lab profile (health-aware, avoid-bad-health, sameiso2,
  and bad-health-required top-up) saved a clean homepage lead in
  `results/browser-compare-20260608T050606/browser-compare.json`. It passed
  quality, kept browser prefs unchanged, and won paired load `5/5` versus
  baseline Arti. Candidate median load was `5531.888ms` vs baseline Arti
  `6743.920ms` and local C Tor `7875.644ms`; candidate max load was
  `5728.244ms` vs baseline Arti `8533.900ms`. It made `2` top-ups with `0`
  failures; top-up max health gap was `259ms`, min score was `17239`, and max
  age was `71ms`. Keep it lab-only: this was one target and one 5-run window.
- `results/browser-compare-20260608T051154/browser-compare.json` repeated that
  combined homepage profile and also passed quality. Candidate median load was
  `4929.467ms` vs baseline Arti `8090.484ms` and local C Tor `5714.914ms`.
  Candidate won paired load `3/5`, improved paired median load by `475.682ms`,
  and improved summary median load by `3161.017ms`. Candidate max load was
  `12292.020ms` vs baseline Arti `15575.293ms` and local C Tor `16310.348ms`.
  It made `2` top-ups with `0` failures; top-up max health gap was `406ms`, min
  score was `14932`, and max age was `45ms`. This is now a repeated homepage
  lead, but not a promotion path until it survives a repeated 3-target gate.
- `results/browser-compare-20260608T051703/browser-compare.json` ran that
  combined profile across check, homepage, and download with `5` interleaved
  runs. It passed quality and kept browser prefs unchanged, but it rejected the
  promotion path. Candidate beat baseline Arti on check median load
  (`1600.279ms` vs `1726.238ms`) and homepage (`4776.506ms` vs `6299.856ms`),
  but lost download badly (`13857.582ms` vs `5314.784ms`) and had a worse
  download max tail (`66948.318ms` vs `12564.660ms`). Paired A/B showed the same
  shape: check `-178.857ms`, homepage `-2731.108ms`, download `+5293.891ms`.
  The download top-up-attempt bucket lost by `+7549.335ms` median load and won
  `0/4` attempt runs. Decision: keep the combined profile lab-only and do not
  promote it; next work must explain or prevent the download top-up tail.
- `results/browser-compare-20260608T052735/browser-compare.json` isolated the
  download page with two extra profiles: health-aware avoid-bad-health without
  same-isolation top-up, and the same profile with sameiso2. It passed quality
  and kept browser prefs unchanged. Baseline Arti stayed best on median load
  (`4973.318ms`). Health-aware avoid-bad-health without top-up lost
  (`6279.622ms`) and had a bad max tail (`61523.104ms`). Sameiso2 lost worse
  (`13245.888ms`). Sameiso2 top-up attempt runs won `0/3` and lost by
  `+9336.977ms` median load. This says the current selector/top-up family is
  not the download fix; do not patch a simple top-up threshold from this alone.
- `results/browser-compare-20260608T053529/browser-compare.json` is the focused
  debug replay for that download tail. It passed quality, but it is debug
  evidence only. In this small window, health-aware avoid-bad-health without
  top-up beat baseline Arti (`4462.620ms` vs `5278.454ms` median load), while
  sameiso2 was slower (`5720.123ms`). Sameiso2 had `1` top-up with `0` failures;
  that top-up-attempt run lost by `+3929.443ms`, while no-attempt sameiso2 runs
  were faster by `-1836.445ms`. SOCKS connect was not the main issue: sameiso2
  median connect was `0ms`, max hostname relay was high, and the slow run had
  late resource queue rows on the selected circuit. Source and analyzer now add
  top-up lifecycle diagnostics (`pending_id`, build complete/failed/canceled) so
  the next debug replay can tell whether extra circuits arrive too late or only
  compete with the active page.
- `results/browser-compare-20260608T054800/browser-compare.json` reran that
  debug replay with the rebuilt Arti. It failed quality because baseline Arti
  run `2` and local C Tor run `1` failed and had no screenshot proof, so it is
  not speed proof. The sameiso2 profile itself finished `5/5` with
  `7579.479ms` median load, `3` top-ups, and `0` top-up failures. The new
  lifecycle fields worked: the three top-up `pending_id`s built `Circ 1.6`,
  `Circ 1.8`, and `Circ 1.9` in `540ms`, `538ms`, and `462ms`. Only run `5`
  then selected and used its top-up circuit (`Circ 1.9`); runs `3` and `4`
  built the extra circuits but did not use them before the page finished. This
  sample says top-up builds were not too late, but it still is debug evidence
  only. The analyzer now prints `Torfast Same-Isolation Top-Up Lifecycle` so
  future runs show built-versus-used top-up circuits directly. The expanded
  lifecycle view also shows remaining demand: run `3` had `2` exit open picks
  after `Circ 1.6` built and saw it as a candidate, but chose active `Circ 1.5`
  instead because `Circ 1.5` had `6` assigned streams and a much stronger
  recent health score (`185759` vs cold `Circ 1.6` score `0`). Run `4` had no
  post-build exit open picks. Run `5` selected and used its built top-up
  circuit. This points away from "top-up built too late" and toward deciding
  when a cold built top-up is better than a hot active circuit.
- Source now has a new default-off lab selector flag,
  `TORFAST_EXIT_SELECT_PREFER_COLD_SAME_ISOLATION`, plus runner flags
  `--arti-exit-select-prefer-cold-same-isolation` and
  `--extra-arti-exit-select-prefer-cold-same-isolation-target`. It only applies
  when same-isolation, load-aware, and health-aware lab modes are already on.
  The rule lets a cold least-assigned same-isolation candidate stay selected
  when the health-aware alternative is already busy enough for the top-up floor.
  This is not a speed claim yet; it creates the next A/B candidate for the run
  `3` shape where cold `Circ 1.6` was skipped for hot `Circ 1.5`.
- `results/browser-compare-20260608T061926/browser-compare.json` is the first
  focused prefer-cold A/B. It passed quality, kept browser connection prefs
  unchanged, and is a positive diagnostic signal, not final speed proof. On the
  download page with `3` paired runs, prefer-cold sameiso2 won `3/3` loads
  against baseline Arti: median load `3488.752ms` versus `7508.323ms`, max load
  `4946.213ms` versus `12413.143ms`, and summary median elapsed
  `6323.848ms` versus `9611.943ms`. It also beat local C Tor on median load
  in this small window (`3488.752ms` versus `4696.296ms`). The lifecycle table
  saw `1` top-up, built `Circ 0.11` in `633ms`; the page had `2506.476ms` left
  after build and later linked one stream, but no post-build open-pick rows
  matched the built circuit. Treat this as a strong next lead and run a wider
  same-window gate before any promotion talk.
- `results/browser-compare-20260608T062521/browser-compare.json` is that wider
  same-window gate across check, homepage, and download. It passed quality and
  kept all profiles successful, but it rejects prefer-cold promotion. Against
  baseline Arti, prefer-cold sameiso2 lost check (`2703.367ms` vs
  `2008.257ms` median load, `0/3` paired load wins), lost homepage
  (`7090.900ms` vs `5746.419ms`, `1/3` wins), and only barely improved the
  download summary median (`5420.215ms` vs `5490.661ms`, `1/3` wins). The
  paired median deltas were still worse on all three pages: `+927.126ms`,
  `+3563.362ms`, and `+432.614ms`. Top-up-attempt rows were less bad than the
  full profile (`-252.124ms` homepage and `-12.627ms` download), but that is
  not enough to call the selector faster. Keep prefer-cold lab-only.
- The runner now also has
  `--extra-arti-exit-select-health-aware-same-isolation-prefer-cold-target`.
  This creates a cleaner prefer-cold profile without the avoid-bad-health guard,
  so the guard can be tested separately.
- `results/browser-compare-20260608T063525/browser-compare.json` tested that
  cleaner profile in the same window as the guarded variants. It passed quality,
  but it rejected the no-guard prefer-cold idea. The no-guard profile was close
  on check (`1848.320ms` vs baseline `1763.893ms` median load), slower on
  homepage (`5506.611ms` vs `4892.608ms`), and much worse on download
  (`12824.702ms` vs `6549.739ms`, `0/3` paired load wins, paired median
  `+4931.700ms`). Removing the guard is not the fix. The guarded prefer-cold
  profile did better in paired medians in this run, especially download
  (`5761.562ms` vs baseline `6549.739ms`), but it also had a bad accepted check
  tail (`24061.174ms` max load), so it is still not promotable.
- The analyzer now prints `Arti Profile Promotion Risks` after direct Arti A/B
  rows. It marks a candidate/target as risky when paired median is slower,
  summary median is slower, max load tail is worse, or paired load wins are too
  low. On `results/browser-compare-20260608T063525/browser-compare.json`, this
  table blocks the guarded prefer-cold check row because its max tail was
  `+21732.234ms`, and blocks the no-guard prefer-cold download row for paired
  median, summary median, max tail, and `0/3` wins.
- The analyzer now also prints `Arti Profile Promotion Risk Max Runs`. On
  `results/browser-compare-20260608T063525/browser-compare.json`, it shows the
  guarded prefer-cold check-page tail was a navigation connect/TLS stall:
  `20583.745ms` in nav connect/TLS on run `3`, while the slowest resource was
  only `1383.361ms`. That points the next investigation at circuit/connect/TLS
  path choice, not the check-page image fetch.
- `results/browser-compare-20260608T065456/browser-compare.json` is the focused
  debug replay for that check-page tail. It passed quality, but did not repeat
  the `063525` `20s` connect/TLS stall. The whole window was slow: baseline
  Arti median load was `4282.324ms`, guarded prefer-cold was `4302.444ms`, and
  local C Tor was `6496.505ms`. The guarded prefer-cold profile is still not
  promotable because paired median was slower (`+499.573ms`), summary median was
  slower (`+20.120ms`), and paired wins were low (`2/5`). Its max tail was lower
  than baseline in this replay (`5559.208ms` vs `5898.746ms`).
- The analyzer now also prints `Arti Profile Promotion Risk SOCKS Context`. On
  `results/browser-compare-20260608T065456/browser-compare.json`, the guarded
  prefer-cold max risk run was run `5`: phase hint `response-to-DOM
  4000.080ms`, SOCKS connect `0ms`, SOCKS reply `0ms`, first Tor byte `293ms`,
  response after reply `620.786ms`, relay `5394ms`, data bytes `16513`, and max
  receive gap `2901ms`. That means this replay's risky run was not blocked on
  SOCKS connect. The next target is relay/response-to-DOM tail control and
  repeated debug windows, while still treating the earlier `063525` connect/TLS
  tail as a promotion blocker until it is explained or prevented.
- Source now has a new default-off lab guard,
  `TORFAST_EXIT_SELECT_AVOID_BAD_HEALTH_UNKNOWN_FALLBACK`, plus runner support
  through `--arti-exit-select-avoid-bad-health-unknown-fallback` and
  `--extra-arti-exit-select-avoid-bad-health-unknown-fallback-prefer-cold-same-isolation-target`.
  It only applies when the existing load-aware bad-health guard is enabled. If
  the least-used eligible circuit is known bad and there is no clearly good
  alternative, this guard may pick an unassigned cold/unknown eligible circuit
  instead of staying on the known-bad one. It does not change path length, relay
  eligibility, SOCKS isolation, or browser prefs. After the `122133` tail, the
  fallback was tightened so already-assigned unknown circuits cannot keep
  winning as unknown.
- `results/browser-compare-20260608T122133/browser-compare.json` tested that
  unknown-fallback profile against baseline Arti and the existing guarded
  prefer-cold profile across check, homepage, and download. It passed quality
  and kept browser connection prefs unchanged. The unknown-fallback profile beat
  baseline Arti median load on all three targets: `1384.295ms` vs `2687.927ms`,
  `3433.314ms` vs `4769.678ms`, and `5581.750ms` vs `5766.895ms`. It beat local
  C Tor on check and homepage, but still lost download median load
  (`5581.750ms` vs `4737.364ms`). It is rejected for promotion because max tails
  were much worse on homepage and download: `61500.660ms` vs baseline
  `5954.526ms`, and `17385.026ms` vs baseline `5909.866ms`.
- In that same `122133` run, the unknown-fallback profile made `43` unknown
  fallback open picks, changed health-aware assignment `3` times, made `5`
  same-isolation top-ups, and had `0` top-up failures. The promotion-risk SOCKS
  context tied the homepage max tail to timing id `5`, with SOCKS connect/reply
  at `0ms`/`0ms` but relay time `13356ms`; the notable SOCKS table also showed
  several much larger relay waits in that profile, including `61905ms`.
- `results/browser-compare-20260608T123655/browser-compare.json` reran the
  same gate after tightening unknown fallback to unassigned circuits only. It
  failed quality: the unknown-fallback profile timed out on download run `2`
  after `91876.956ms` and had no screenshot proof. The failed-run SOCKS table
  showed timing id `35` with hostname CONNECT `1195ms`, relay `89332ms`, and
  timing id `37` with onion CONNECT `4212ms`, relay `83919ms`. The accepted
  median rows looked better, but the quality failure means this is not speed
  proof and the unknown-fallback profile stays rejected.
- `results/browser-compare-20260608T124751/browser-compare.json` tested the
  same download page with global non-onion SOCKS soft timeout set to `5000ms`.
  It still failed quality. The failing profile was guarded prefer-cold, which
  hit `about:neterror?e=netTimeout` after `61452.374ms`. The failed-run SOCKS
  table still showed long onion CONNECT and hostname relay waits, including
  hostname relay waits of `60342ms` and `59851ms`. Meaning: soft timeout alone
  does not fix this failure shape, and guarded prefer-cold stays rejected.
- The analyzer now prints `Browser Failed Run Cause Summary`. For `124751`, it
  classifies the failed run as `mixed connect wait + relay-after-reply tail`:
  `2` slow onion CONNECT streams, `3` relay-tail streams, `0` soft timeouts,
  max CONNECT `63268ms`, max relay `60342ms`, and max idle after last Tor byte
  `59203ms`.
- The same cause summary now splits relay tails by byte shape. In `124751`,
  `2` relay-tail streams had some Tor bytes and then long idle, while `1`
  relay-tail stream had no Tor bytes. This means the next design target is not
  just "retry connect"; it must explain partial-response stalls and no-byte
  relay stalls without changing onion safety or browser isolation.
- The analyzer now also prints `Browser Failed Run Relay-Tail Details`. For
  `124751`, timing ids `10` and `12` joined to relay receive context with small
  max receive gaps, `230ms` and `679ms`, but then idled after last Tor byte for
  `59203ms` and `54141ms`. Timing id `11` was a no-byte hostname relay tail.
- The source now logs SOCKS relay copy errors and stream-reader terminal state
  for these post-last-byte stalls. The old `124751` run does not have those new
  fields, so the next proof must rerun the browser gate and fill them in before
  changing behavior.
- Arti SOCKS now also emits bounded info-level `torfast socks timing` summaries
  for slow connects and slow or failed relay streams. This is diagnostic only:
  it does not change stream isolation, path choice, browser prefs, or retry
  behavior. The low-log replay
  `results/browser-compare-20260608T142558/browser-compare.json` passed quality
  and proved the summaries are retained at run level without debug logs: the
  analyzer printed `Torfast SOCKS Timings`, `Notable Torfast SOCKS Streams`, and
  `Browser Run Proxy Tails`. It is not promotion proof; it used only `2` runs
  on check and homepage, and the candidate was still risky on check
  (`1962.585ms` max load vs baseline `1582.965ms`).
- The repeated wide low-log gate with those summaries saved
  `results/browser-compare-20260608T143029/browser-compare.json`. It passed
  quality, but still rejected the bad-health hedge for promotion. The hedge
  profile beat baseline Arti summary median load on check (`1757.558ms` vs
  `1952.592ms`) and homepage (`4130.136ms` vs `4883.015ms`), but lost download
  (`4765.945ms` vs `4713.188ms`), had low paired wins, and had a bad accepted
  download max tail (`66992.133ms` vs baseline `6907.686ms`). The new SOCKS
  rows tied that tail to timing id `105`: the first non-onion CONNECT attempt
  hit the `5000ms` soft timeout, then the retry still waited `55696ms`
  (`60699ms` total CONNECT) before relay.
- Local Arti source now also has
  `TORFAST_SOCKS_CONNECT_SOFT_TIMEOUT_ATTEMPTS`, a bounded default-off lab
  count for non-onion soft-timeout attempts. The default stays `2`, valid lab
  values are `1..4`, and onion streams stay on the old default retry count. The
  focused attempts-`3` download replay
  `results/browser-compare-20260608T144556/browser-compare.json` passed quality
  but did not prove a speed fix: baseline Arti median load was `4347.238ms`,
  the hedge profile was slower at `6431.882ms`, local C Tor was faster at
  `3286.694ms`, and the hedge profile won only `1/3` paired loads. Keep the
  attempts knob lab-only.
- The runner can now add same-window attempt-count A/B profiles with
  `--extra-arti-socks-connect-soft-timeout-attempts`. The focused download A/B
  `results/browser-compare-20260608T145305/browser-compare.json` passed quality
  and was promising: attempts-`3` beat baseline Arti on `3/3` paired loads,
  median load was `3786.624ms` vs `11503.625ms`, and max load was
  `5483.781ms` vs `13661.879ms`. This is still narrow proof only: one target,
  three runs, and no default change.
- The wider attempts-`3` same-window gate
  `results/browser-compare-20260608T145856/browser-compare.json` also passed
  quality and improved median load on all three targets, but it is rejected for
  promotion. It had worse max tails on check (`11650.746ms` vs `9101.954ms`)
  and homepage (`65083.056ms` vs `7449.706ms`). The homepage risk row tied the
  tail to timing id `33`: two `5000ms` soft timeouts, then a `60451ms` final
  CONNECT wait. The focused attempts-`4` homepage follow-up
  `results/browser-compare-20260608T150858/browser-compare.json` passed quality
  and lowered max load (`5502.132ms` vs `6805.031ms`) but was slower by median
  (`4438.605ms` vs `3699.166ms`) and won only `1/5` paired loads. Keep both
  attempt counts lab-only.
- The analyzer's `Torfast SOCKS Connect Retries` table now keeps the attempt
  cap and an attempt trace. Re-reading `20260608T145856` shows the bad
  attempts-`3` rows plainly: `1:soft_timeout:5002ms`,
  `2:soft_timeout:5002ms`, then `3:ok:50446ms` for timing id `33`, and the
  same shape for timing id `100`. This confirms the rejected profile was not
  blocked by the short timeout wrapper itself; it was blocked by the final
  allowed CONNECT attempt waiting normally for about `50s`.
- Arti now emits low-log exit-client phase timing for slow or failed normal
  exit CONNECTs, and the analyzer prints `Torfast Exit Client Timings`. The
  focused proof `results/browser-compare-20260608T152416/browser-compare.json`
  passed quality and showed why the latest slow homepage load was different:
  exit tunnel acquisition was `4467ms`, BEGIN completion took only `1ms` after
  that, and the SOCKS table then showed relay tails up to `38465ms`. This
  points the next work toward relay/resource transfer and circuit health, not
  CONNECT retry count.
- Arti now also emits low-log stream receiver terminal summaries for slow or
  non-clean reader endings, and the analyzer prints `Torfast Stream Receiver
  Terminal Summaries`. The focused proof
  `results/browser-compare-20260608T153828/browser-compare.json` passed quality:
  Arti load was `3883.972ms` vs local C Tor `5581.214ms` in this one-run
  sample. It captured `9` terminal summaries, about `1302.085KiB` relayed,
  max transfer `3450ms`, max data gap `465ms`, and max idle after last data
  `3012ms`. This proves the low-log transfer summary is live and parseable; it
  does not promote a speed change.
- The wider low-log proof
  `results/browser-compare-20260608T154415/browser-compare.json` passed quality
  with 3 runs on `check.torproject.org` and the homepage. Arti beat local C Tor
  by median load on both targets (`1501.413ms` vs `1678.086ms` on check, and
  `4128.488ms` vs `4464.025ms` on the homepage), but one accepted check run had
  a `62261.348ms` max load. The new exit-client and stream terminal summaries
  tied that tail to a `60042ms` tunnel-ready failure followed by a successful
  `689ms` retry, while stream transfer summaries showed max transfer `5314ms`
  and max data gap `880ms`. This points at CONNECT/tunnel acquisition, not a
  post-data transfer stall.
- The first focused soft-timeout A/B
  `results/browser-compare-20260608T154736/browser-compare.json` passed quality,
  but the runner split `--extra-arti-socks-connect-soft-timeout-ms 5000` and
  `--extra-arti-socks-connect-soft-timeout-attempts 3` into two separate
  profiles. The `soft5000ms` profile was rejected: median load was
  `12638.173ms` vs baseline `1592.926ms`, paired wins were `0/3`, and max load
  was worse. The `softattempts3` profile was faster in this window, but it did
  not test `5000ms + 3 attempts` together.
- `tools/run_browser_compare.py` now has
  `--extra-arti-socks-connect-soft-timeout-combo MS:ATTEMPTS`, so a same-window
  extra Arti profile can set the non-onion soft timeout and retry count
  together. The focused combined A/B
  `results/browser-compare-20260608T155501/browser-compare.json` passed quality:
  `arti_release_browser_soft5000ms_attempts3` beat baseline Arti by paired
  median load by `1539.870ms`, won `2/3` paired loads, and cut max load from
  `2663.750ms` to `1651.442ms`. It also beat local C Tor by median page load
  on this one target (`1039.679ms` vs `1148.417ms`), but it still needs a wider
  multi-target gate before any default or promotion claim.
- The wider combined A/B
  `results/browser-compare-20260608T160018/browser-compare.json` passed browser
  quality but rejected promotion. The combo beat baseline Arti on check
  (`1610.906ms` vs `2816.483ms`, paired wins `3/3`) and homepage by median
  load (`2715.440ms` vs `6864.182ms`, paired wins `2/3`), but homepage max load
  was worse (`16848.073ms` vs baseline `8021.455ms`). On download, the combo
  was slower than baseline Arti by paired median load (`+138.804ms`, paired wins
  `1/3`) and much slower than local C Tor by median load (`7569.085ms` vs
  `4975.924ms`). Keep `5000ms + 3 attempts` lab-only.
- The analyzer now also prints `Torfast Stream Receiver Terminal Top Streams`.
  On `20260608T160018`, that table exposed the worst combo terminal streams:
  homepage run `3` had stream `11088` on `Circ 3.15` idle after last data for
  `15808ms` after only `7.581KiB`, and stream `38312` on `Circ 3.16` transferred
  for `13404ms` with a `4970ms` max data gap. Download run `3` had stream
  `42141` on `Circ 3.20` idle after last data for `13237ms`, and stream `1157`
  on `Circ 3.21` transferred for `12011ms` with a `4976ms` max data gap. This
  points the next work at late resource/stream transfer and idle tails, not at
  enabling the combo profile.
- The source and analyzer now join terminal stream rows to SOCKS relay rows
  directly through `circ_id` and `stream_id` on `relay finished`, even when the
  older `stream linked` line is missing from a retained run tail. The focused
  proof `results/browser-compare-20260608T162621/browser-compare.json` passed
  quality and showed populated top-stream `timing id`, `kind`, `relay ms`,
  `socks ok`, and `copy error` fields. It also rejected the combined
  `5000ms + 3 attempts` profile again: homepage was `+422.130ms` slower than
  baseline by paired median load, and download was `+24827.011ms` slower with a
  `51860.171ms` max load tied to timing id `35` and a `46796ms` CONNECT.
- Exit-client timing logs now include `tunnel_unique_id`, and slow tunnel build
  completion/failure/cancel rows are kept at info level when build age is at
  least `5000ms`. The analyzer now has `Torfast Exit Client Slow Tunnels` for
  per-run tunnel wait rows. The focused proof
  `results/browser-compare-20260608T164228/browser-compare.json` passed quality
  and showed the new low-log build-failure rows during bootstrap
  (`pending_age_ms=10003..10004`). It did not reproduce the `46796ms` page-load
  CONNECT stall, so the slow-tunnel table did not fire in accepted page runs.
  The combo looked faster on this one download-page 2-run window
  (`-1750.649ms` paired median load), but paired wins were only `1/2`; this is
  not promotion proof and does not override the wider `160018` and `162621`
  rejections.
- The stronger low-log 3-target gate
  `results/browser-compare-20260608T164626/browser-compare.json` failed quality:
  baseline Arti timed out on check run `3`, and local C Tor had one check-page
  proof failure. The retained Arti evidence is useful: baseline check run `3`
  had a `60002ms` tunnel build failure (`Circuit took too long to build`), a
  `120065ms` hostname CONNECT failure, and two relay tails around `85..90s`
  with tiny reader output (`7.683KiB` and `3.470KiB`). The combo passed all
  three targets and was faster on homepage/download in this window, but the
  whole gate is rejected because quality failed and check still had only `1/2`
  paired wins against accepted baseline runs.
- The browser runner now supports one real same-window extra profile with both
  SOCKS soft-timeout settings and the exit pending hedge:
  `--extra-arti-socks-connect-soft-timeout-pending-hedge-combo MS:ATTEMPTS:HEDGE_MS`.
  This is harness support only; it changes no default Arti behavior. The
  pending-hedge launch, failure, and timer-fire events are now info-level so a
  low-log run can prove whether the hedge actually fired.
- The first combined soft-timeout plus pending-hedge proof
  `results/browser-compare-20260608T170429/browser-compare.json` passed quality
  on the check page with `3` runs. The `5000ms + 3 attempts + 1500ms hedge`
  profile had median load `1074.465ms`, versus baseline Arti `1490.304ms`,
  soft-timeout-only `1720.063ms`, and local C Tor `1276.564ms`. Treat this as
  narrow harness proof only.
- The rebuilt-binary wider proof
  `results/browser-compare-20260608T171004/browser-compare.json` failed overall
  quality because local C Tor check run `1` hit `nssFailure2` and missed
  screenshot proof. All Arti profiles passed both check and download. The
  combined `5000ms + 3 attempts + 1500ms hedge` profile was basically flat on
  check (`-0.736ms` paired median load, `1/2` wins, max tail `+16.169ms`) and
  faster on download (`-1508.440ms` paired median load, `2/2` wins, max tail
  `-1755.690ms`). Soft-timeout-only was rejected again: download was
  `+19347.469ms` slower by paired median load, max tail was `+38938.698ms`, and
  timing id `15` showed two `5000ms` soft timeouts followed by a `31008ms`
  accepted exit tunnel wait. No pending-hedge info lines appeared in this run,
  so the combined profile is not proven as a hedge fix and must not be
  promoted.
- Build-hedge timer-fire and launch rows are now also info-level, and the
  analyzer keeps actual `build_hedge` separate from normal `build`. The focused
  rebuilt-binary download proof
  `results/browser-compare-20260608T172159/browser-compare.json` passed quality
  with `3` runs. Baseline Arti median load was `4354.853ms`,
  soft-timeout-only was `4026.041ms`, combined `5000ms + 3 attempts + 1500ms`
  hedge was `3986.091ms`, and local C Tor was `5223.020ms`. Both lab profiles
  beat baseline median load, but both had worse max tails (`+343.657ms` for
  soft-timeout-only, `+495.090ms` for combined). No pending-hedge or build-hedge
  timer lines fired; only build-failure rows appeared. Treat this as useful
  low-log proof and keep both profiles lab-only.
- `tools/analyze_browser_compare.py` now prints `Browser Run Late Phase Queue
  Context`, which ranks successful runs by response-to-DOM and DOM-to-load time
  and attaches resource queue, SOCKS timing id, circuit, and selector context
  when debug relay lines are available. The focused debug replay
  `results/browser-compare-20260608T173542/browser-compare.json` passed quality
  for local C Tor and Arti, but Arti was slower by `+1500.055ms` paired median
  load. Arti reached first response `83.335ms` earlier than local C Tor, then
  lost `+3083.395ms` in response-to-DOM while winning back `-1500.030ms` in
  DOM-to-load. The new table ties the Arti late phase to queued resources on
  timing ids `4` and `7`, `Circ 4.0 (Tunnel 5)`, with the worst queued resource
  at `3466.736ms`. This is diagnostic proof only; it says the next source work
  should explain late page construction/resource queue timing, not retry
  min-exit `3`, browser connection caps, or another soft-timeout promotion.
- The analyzer now also prints `Arti Profile Late Queue A/B` for extra Arti
  profiles. It compares base Arti and a candidate by paired run for queued
  resource count, max fetch-to-request queue time, response-to-DOM, and
  DOM-to-load. Re-analyzing `20260608T174515` showed
  `healthaware_spread4` improved median max queue by `-4950.099ms`, but still
  won only `1/2` paired queue runs, so the result stays lab-only.
- The stricter assignment-spread lab proof
  `results/browser-compare-20260608T174012/browser-compare.json` tested
  `--extra-arti-exit-select-min-assignment-spread 4` on the download page with
  debug logs. It passed quality, but rejected the idea: spread `4` was slower
  than base Arti by `+1932.340ms` paired median load, won `0/2` paired loads,
  and had a worse max tail (`+2157.597ms`). It made `9` load-aware picks in
  each run, but the circuit-quality summary found low-rate/slow-relay selected
  circuits. Keep assignment-spread selection lab-only; spread pressure alone is
  not the next fix.
- The runner now also supports
  `--extra-arti-exit-select-health-aware-min-assignment-spread`. It creates a
  same-window health-aware plus minimum-assignment-spread profile without
  changing the base Arti profile.
  `results/browser-compare-20260608T174515/browser-compare.json` tested value
  `4` on the download page. It passed quality and the candidate median load was
  `4228.945ms`, versus base Arti `9418.284ms` and local C Tor `7172.289ms`.
  But the direct A/B win count was only `1/2`, so treat this as a narrow
  lab-only clue, not a promotion result.
- The wider low-log same-window gate
  `results/browser-compare-20260608T175759/browser-compare.json` tested
  `healthaware_spread4` on check, homepage, and download with `3` runs per
  target. It passed quality, but rejected promotion. The candidate had worse
  max tails on all three targets: `+31710.236ms` on check, `+8381.266ms` on the
  homepage, and `+15472.882ms` on download. It also lost the homepage badly:
  `+8208.762ms` paired median load and `0/3` paired wins. The late-queue A/B
  table showed the homepage queue got worse by `+6566.798ms` median max queue
  delay, so the selector is not a safe speed path.
- The analyzer now also prints
  `Arti Profile Promotion Risk Stream Receiver Context`, joining each risky
  candidate max run to its worst retained stream receiver terminal row. On
  `20260608T175759`, the rejected `healthaware_spread4` tails all had
  `not_connected` stream endings. The check tail had `32620ms` idle after last
  data, the homepage tail had `12595ms`, and the download tail had `51028ms`.
  This points the next source target at slow or abandoned stream endings and
  tunnel acquisition tails, not another assignment-spread selector.
- The analyzer now also prints `Torfast Stream Receiver Not-Connected Summary`,
  grouped by profile, target, and run. Re-analyzing `20260608T175759` shows the
  abandoned-stream tail is not only a rejected-selector issue: base Arti
  download run `3` had `8` not-connected streams with `35403ms` max idle after
  last data, while `healthaware_spread4` download run `1` had `7` with
  `51028ms` max idle. This keeps the next source target general: reduce slow
  not-connected stream tails without changing path quality.
- Local Arti source now has a default-off low-log byte timing knob:
  `TORFAST_SOCKS_RELAY_BYTE_TIMING`, exposed in the runner as
  `--arti-socks-relay-byte-timing`. Normal runs stay unchanged. The focused
  download proof `results/browser-compare-20260608T182354/browser-compare.json`
  passed quality and proved the knob works at info level. This was not a speed
  win: Arti load was `5673.865ms` versus local C Tor `4003.608ms`. The useful
  proof is the byte timing itself: timing id `1` had last Tor-to-browser byte at
  `1318ms` but relay finished at `6123ms` (`4805ms` idle after last Tor byte),
  and timing id `2` carried `362459` Tor-to-browser bytes with last byte at
  `5193ms` before a `5774ms` `not_connected` finish. Next source work should
  inspect stream close/EOF and browser slot release behavior, not promote a
  selector knob.
- The follow-up byte-timing proof
  `results/browser-compare-20260608T183445/browser-compare.json` passed quality
  and was a one-run diagnostic speed win only: Arti load was `2864.382ms`
  versus local C Tor `5099.072ms`, and Arti elapsed was `4488.468ms` versus
  `7584.745ms`. Do not promote from one run. The useful close clue is that all
  logged `not_connected` streams had no recorded browser EOF or Tor read-error
  timestamp (`client_to_tor_eof_ms=0`, `tor_to_client_error_ms=0`), while
  `client_to_tor_write_close_ms` landed at relay finish (`2092-3318ms`). Add
  tighter close/error proof before changing behavior.
- The missing EOF/error timestamp clue above was a diagnostic blind spot:
  `copy_buf_bidirectional` uses buffered reads, so the timing wrapper now
  records EOF/error in `poll_fill_buf` too. The follow-up proof
  `results/browser-compare-20260608T184334/browser-compare.json` passed quality.
  It was still only one-run diagnostic evidence: Arti load was `7367.272ms`
  versus local C Tor `8237.511ms`, but Arti boot was worse (`26.750s` vs
  `16.551s`). The new `Torfast SOCKS Close Shape` table showed `10` close
  streams, `9` `not_connected`, and all `9` had browser EOF plus Tor read error
  at the same close moment (`0ms` median EOF-to-error). Treat most of this
  `not_connected` class as local close-after-browser-done evidence, not the next
  direct speed fix.
- The analyzer now falls back from debug relay-cell joins to low-log SOCKS
  stream timing when matching browser resources to streams. Re-analyzing
  `results/browser-compare-20260608T184334/browser-compare.json` filled the
  resource tables: `36` resources, `17` high-confidence resource-to-stream
  matches, and `25` slow resources at least `2s`. The strongest queue clusters
  were timing id `9` with `4` queued resources all at least `1000ms` queued
  (top resources `get-connected.svg` and `stay-safe.svg`), and timing id `10`
  for `tor-logo@2x.png` with `5600.112ms` fetch-to-request delay. Next source
  work should use this low-log mapping to inspect resource queue and transfer
  timing, not local close noise.
- The analyzer now also prints `Resource Queue Slot Release Summary`, which
  groups the blocker rows by run. On the same `184334` proof, Arti had `23`
  queued resources at least `1000ms`, `16` at slot depth `>=6`, `23` rows with
  joined blocker stream evidence, and `13` rows with high-confidence blockers.
  Of those queued Arti rows, `15` were receive-dominant, `8` were wait-dominant,
  `11` had high-confidence blocker writes at least `500ms` after the queued
  request started, and `9` had such writes at least `1000ms` after it started.
  The top queued Arti resource was `tor-logo@2x.png`; median max blocker left at
  request start was `666.680ms`, max blocker left was `2000.040ms`, median queue
  minus blocker-left was `2733.388ms`, and median high-confidence blocker
  write-after-queue was `1188.760ms`. This points the next proof at browser slot
  release plus late stream transfer shape.
- The new `Resource Queue Late Write Summary` narrows that further. In
  `184334`, Arti had `13` high-confidence queued rows with blocker writes after
  the queued request started; `11` were at least `500ms`, `9` were at least
  `1000ms`, median write-after-queue was `1188.760ms`, and max was
  `4978.163ms` on `fallback.js`. Stream receiver terminal summaries covered all
  `13` rows; `9` had terminal last-data at least `1000ms` after queue start,
  median terminal last-data-after-queue was `1188.760ms`, and max was
  `4979.163ms`. Median and max write-after-terminal-last-data were both `0ms`,
  with max terminal data gap `1097ms`, max idle-after-last-data `823ms`, and max
  terminal pending bytes `0`. Browser release after last write was positive for
  only `2` rows, none at least `500ms` (median positive release `245.604ms`).
  This makes late Tor stream data arrival the next source path to inspect, not
  SOCKS write delay or post-write browser slot holding.
- The new `Resource Queue Late Stream Detail` table names the worst rows. In
  `184334`, `fallback.js` queued `1016.687ms` and waited on terminal last data
  `4979.163ms` after queue start, with blocker timing ids `8, 4` on `Circ 4.1`
  and a `1097ms` terminal data gap. `stay-safe@3x.png` and `TBA10.0.png` both
  queued `1400.028ms` and waited on terminal last data `4595.822ms` after queue
  start, also on `Circ 4.1` with timing ids `4, 8`. The next source check should
  inspect why streams `4`, `8`, and `9` on `Circ 4.1` have late receiver data
  gaps while keeping Tor Browser slots full.
- `Resource Queue Late Circuit Summary` now confirms this is a same-circuit
  pile-up: all `13` late queued rows were on `Circ 4.1`. That circuit had `7`
  terminal streams, timing ids `2, 5, 4, 8, 9, 7, 10`, `1178.332 KiB` terminal
  relay data, `2505` data cells, max terminal transfer `6499ms`, max terminal
  data gap `1196ms`, and max terminal idle `823ms`. Next source work should
  inspect circuit-level stream scheduling/fairness or circuit choice for many
  same-origin browser fetches.
- Local Arti source now also has `TORFAST_EXIT_SELECT_BAD_HEALTH_HEDGE_MS`, a
  bounded default-off lab hedge behind the bad-health guard. If the chosen open
  exit circuit has fresh bad local health, Arti may start one same-usage
  replacement and wait only the configured short delay; if the timer fires or
  the build loses, it uses the original valid circuit. The plain no-top-up guard
  proof at `results/browser-compare-20260608T134350/browser-compare.json`
  passed quality but was rejected: candidate median load was `4736.420ms` vs
  baseline `3934.563ms`, paired wins were `1/5`, and the candidate max tail was
  `54967.352ms`.
- The first bad-health hedge proof,
  `results/browser-compare-20260608T135745/browser-compare.json`, was rejected
  and exposed a pending-count bug: candidate median load was `5150.726ms` vs
  baseline `4615.067ms`, with a `65842.917ms` max tail. After fixing the pending
  count, the focused homepage replay
  `results/browser-compare-20260608T140400/browser-compare.json` was promising:
  candidate median load was `6160.585ms` vs baseline `10951.012ms`, max load was
  `7574.374ms` vs `13503.874ms`, and paired wins were `5/5`. But the stronger
  low-log 3-target gate
  `results/browser-compare-20260608T140711/browser-compare.json` failed
  quality: check run `2` timed out with no screenshot proof, homepage still had
  an accepted `63981.474ms` max tail, and download max load was worse than
  baseline (`8381.048ms` vs `7251.876ms`). Keep the hedge lab-only and do not
  promote it.

## Important limits

- This is not enough to claim we built a faster Tor yet.
- These are small HTTP fetches, not a full browser page-load suite.
- Runs happened close together, but not in one perfect network window.
- Arti debug results should not be treated as fair release-speed results.
- The latest normal speed evidence is still local and small. The first 5-run
  health-gated gate passed and looked strong, but the independent repeat did not
  confirm it, so this is not broad enough to call the full goal done.
- The latest combined health-aware avoid-bad-health sameiso2 profile had two
  passing homepage windows, but the broader 3-target gate rejected it because the
  download page regressed badly.
- The focused download isolation also rejected health-aware avoid-bad-health
  without top-up, so the next work needs stronger relay/resource-tail evidence,
  not another simple count or bad-health gate.
- The latest debug replays are not speed claims. One showed sameiso2 top-up
  attempts were risky; the next showed those top-ups built quickly, with only
  one of three later used by page traffic. The latest analyzer output can also
  show whether the built circuit was skipped despite being an eligible
  candidate. Future debug reads should use the lifecycle table before changing
  the selector.
- The latest prefer-cold A/B looked strong on one focused download run, but the
  wider check/homepage/download gate rejected promotion. Prefer-cold can stay as
  a diagnostic selector, not a speed fix.
- The no-guard prefer-cold profile made the download page much worse, so the
  avoid-bad-health guard is protective in this lab shape. Do not remove it for
  speed.
- Promotion now needs to clear the `Arti Profile Promotion Risks` table, not
  only the median tables. A candidate with a worse accepted max tail is not a
  real speed win.
- The guarded prefer-cold check tail from `063525` was a connect/TLS tail, but
  the focused `065456` replay did not reproduce it. In `065456`, the risky run
  had fast SOCKS connect/reply and a long relay/response-to-DOM span. Future
  debug runs should capture both shapes and prevent either one before any
  promotion run.
- The unknown-fallback bad-health guard is rejected for now. One run passed
  quality but had bad accepted tails; the tighter rerun failed quality with a
  90s download timeout. Do not treat it as faster.
- The Arti SOCKS timing diagnostic is useful for finding bottlenecks, but it is
  still a one-run debug-log diagnostic, not a browser-speed proof.
- The Arti HsPool timing diagnostic is also a one-run debug-log diagnostic.
  It is bottleneck evidence only, not a fair speed claim.
- The Arti HS protocol timing diagnostic is also debug-log evidence only. It
  helps narrow the bottleneck, but it is not a fair speed claim.
- The Arti stream scheduler timing diagnostic is debug-log evidence only. It
  includes whatever proxy-tail lines were kept for that run, so use it to find
  bottlenecks, not to claim speed.
- The Arti relay receive diagnostic is also debug-log evidence only. It shows
  local receive queue behavior in the kept proxy tail, not a fair speed result.
- The Arti stream receiver diagnostic is also debug-log evidence only. It shows
  stream read and SENDME/window context in the kept proxy tail, not a fair speed
  result.
- The pending-exit-circuit hedge is also a local lab patch. It is default-off,
  bounded, and still not a speed fix. Later runs captured `1` pending hedge and
  `1` build hedge timer, but both hedge profiles were slower by median load.
- The bad-health hedge is also a local lab patch. One fixed focused homepage
  run looked good, but the wider 3-target gate failed quality and kept a huge
  accepted homepage tail, so it is not promotable.
- The load-aware open-circuit selector is also a local lab patch. The wider
  5-run, 3-target sample is promising by median load, but the bad download tail
  means it is still not default-ready.
- The bad-health guard is also lab-only and default-off. The first focused run
  improved the download-page tail, but the repeated proof rejected that first
  rule. The tightened rule passed a repeated debug gate, but the low-log
  3-target gate found bad tails, and the guarded same-isolation target `2`
  replay was slower, so do not promote it.
- The focused load-aware plus soft-timeout result is also lab-only. It was fast
  in that window, but `soft timeouts = 0`, so it is not proof that the soft
  timeout catches the earlier 60s CONNECT stall.
- The focused combined `5000ms + 3 attempts` result is also lab-only. It beat
  baseline Arti on one small target, but the wider `20260608T160018` gate
  rejected it on homepage max tail and download median load. It does not clear
  the multi-target promotion-risk bar.
- Release Arti is not Tor Browser. It does not prove exact browser fingerprint
  quality.
- The browser run uses Tor Browser with `TOR_PROVIDER=none` and an external
  SOCKS proxy. It keeps browser privacy prefs, but it is not full Tor Browser
  daemon/control-port integration.
- Latest full browser numbers are still a small local suite, not a full stable
  browser benchmark.
- Latest warm-cache browser timing is 5 runs on two Tor Project pages. It is
  stronger than the earlier samples, but still not enough alone for an upstream
  speed claim.
- The rotating interleaved result is still a small local suite. It is better
  than the sequential run for time-window fairness, but still not enough alone
  for an upstream speed claim.
- The latest 5-run normal result is stronger than the 3-run win and shows the
  remaining gap clearly: Arti beats bundled C Tor, but not local C Tor on the
  larger Tor Project pages.
- The focused one-target exit-spread A/B was promising, but the stronger
  5-run, 3-target same-window A/B did not confirm it. Treat wider exit-select
  values as lab-only until they win broader proof.
- The runner-only preemptive count `3` test did not change the source default
  of `2`, but it still made the homepage slower. Do not use it as a default.
- The byte tap is a measurement hop. It is fair because every profile uses the
  same local tap, but normal no-tap speed claims should still use no-tap runs.
- Interleaved results before `20260607T061526` undercounted some boot timings.
  Result `20260607T061526` fixed boot timing but did not rotate profile order.
  Use `20260607T101326` as the latest normal interleaved browser proof. Use
  `20260607T100351` as the latest passing neutral byte-tap proof; the later
  `20260607T102046` tap run failed quality.
- The 12 second post-boot wait diagnostic is not a user-visible speed win. It is
  only evidence that circuit readiness may be part of the browser slowdown.
- The 1 second preemptive recheck patch is a local lab patch, not an upstream
  accepted change.
- The optimistic SOCKS CONNECT patch is also a local lab patch. It improves
  speed by matching C Tor behavior, but it still needs broader review.
- The exit-spread patch is also a local lab patch. It keeps isolation
  eligibility checks, but still needs broader privacy and network-load review.
- C Tor circuit checks prove observable path facts for a sampled run, not every
  future circuit.
- Arti quality-config checks are static source/config proof only. They do not
  prove live Arti circuit paths.
- Arti RPC path checks now prove full sampled path quality when C Tor directory
  validation passes, but this is still 3 sampled paths, not every future path.
- Older browser compare results before `20260607T053854` did not enforce
  `IsolateSOCKSAuth` on the C Tor test SOCKS ports, so use them as old
  diagnostics, not as the best quality-matched browser comparison.

## Key Numbers

| source | profile | target | boot s | median total ms | median first byte ms | ok |
|---|---|---|---:|---:|---:|---|
| results/baseline-20260607T032836.json | arti_19060 | https://check.torproject.org/ |  | 1717.264 | 1518.056 | yes |
| results/baseline-20260607T032836.json | arti_19060 | https://www.torproject.org/ |  | 1469.538 | 1285.706 | yes |
| results/baseline-20260607T032836.json | direct | https://check.torproject.org/ |  | 503.247 | 495.038 | yes |
| results/baseline-20260607T032836.json | direct | https://www.torproject.org/ |  | 1359.471 | 1118.817 | yes |
| results/arti-baseline-20260607T032950/arti-baseline.json | arti | https://check.torproject.org/ | 15.387 | 1347.768 | 1347.710 | yes |
| results/arti-baseline-20260607T032950/arti-baseline.json | arti | https://www.torproject.org/ | 15.387 | 1545.750 | 1329.261 | yes |
| results/tor-matrix-20260607T033437/matrix.json | latency_auto | https://check.torproject.org/ | 12.553 | 1639.309 | 1639.264 | yes |
| results/tor-matrix-20260607T033437/matrix.json | latency_auto | https://www.torproject.org/ | 12.553 | 1780.795 | 1557.319 | yes |
| results/tor-matrix-20260607T033437/matrix.json | stock_auto | https://check.torproject.org/ | 8.643 | 1027.731 | 1027.676 | yes |
| results/tor-matrix-20260607T033437/matrix.json | stock_auto | https://www.torproject.org/ | 8.643 | 1088.838 | 971.362 | yes |
| results/tor-matrix-20260607T033437/matrix.json | throughput_auto | https://check.torproject.org/ | 9.544 | 1254.879 | 1180.627 | yes |
| results/tor-matrix-20260607T033437/matrix.json | throughput_auto | https://www.torproject.org/ | 9.544 | 1067.766 | 988.095 | yes |
| results/tor-matrix-20260607T033437/matrix.json | throughput_lowmem_auto | https://check.torproject.org/ | 136.764 | 1213.861 | 1134.219 | yes |
| results/tor-matrix-20260607T033437/matrix.json | throughput_lowmem_auto | https://www.torproject.org/ | 136.764 | 1210.149 | 1035.746 | yes |
| results/proxy-compare-20260607T034459/compare.json | arti_release | https://check.torproject.org/ | 15.573 | 1047.479 | 1047.427 | yes |
| results/proxy-compare-20260607T034459/compare.json | arti_release | https://www.torproject.org/ | 15.573 | 1437.844 | 1231.966 | yes |
| results/proxy-compare-20260607T034459/compare.json | c_tor_stock | https://check.torproject.org/ | 8.576 | 1380.860 | 1257.421 | yes |
| results/proxy-compare-20260607T034459/compare.json | c_tor_stock | https://www.torproject.org/ | 8.576 | 1669.580 | 1567.405 | yes |
| results/proxy-compare-20260607T034459/compare.json | direct_start | https://check.torproject.org/ |  | 590.759 | 581.255 | yes |
| results/proxy-compare-20260607T034459/compare.json | direct_start | https://www.torproject.org/ |  | 681.937 | 561.542 | yes |
| results/proxy-compare-20260607T034459/compare.json | direct_end | https://check.torproject.org/ |  | 497.552 | 488.739 | yes |
| results/proxy-compare-20260607T034459/compare.json | direct_end | https://www.torproject.org/ |  | 684.742 | 565.051 | yes |
| results/browser-compare-20260607T041426/browser-compare.json | arti_release_browser | https://check.torproject.org/ | 31.934 | 3835.399 |  | yes |
| results/browser-compare-20260607T041426/browser-compare.json | arti_release_browser | https://www.torproject.org/ | 31.934 | 9764.843 |  | yes |
| results/browser-compare-20260607T041426/browser-compare.json | bundled_c_tor_browser | https://check.torproject.org/ | 14.581 | 2566.255 |  | yes |
| results/browser-compare-20260607T041426/browser-compare.json | bundled_c_tor_browser | https://www.torproject.org/ | 14.581 | 8089.704 |  | yes |
| results/browser-compare-20260607T041426/browser-compare.json | local_c_tor_browser | https://check.torproject.org/ | 8.595 | 2443.044 |  | yes |
| results/browser-compare-20260607T041426/browser-compare.json | local_c_tor_browser | https://www.torproject.org/ | 8.595 | 5136.736 |  | yes |
| results/browser-compare-20260607T045144/browser-compare.json | arti_release_browser | https://www.torproject.org/ | 51.341 | 5946.052 |  | yes |
| results/browser-compare-20260607T045144/browser-compare.json | bundled_c_tor_browser | https://www.torproject.org/ | 31.856 | 8682.815 |  | yes |
| results/browser-compare-20260607T045144/browser-compare.json | local_c_tor_browser | https://www.torproject.org/ | 28.829 | 5016.938 |  | yes |
| results/browser-compare-20260607T050816/browser-compare.json | arti_release_browser | https://www.torproject.org/ | 0.350 | 10136.658 |  | yes |
| results/browser-compare-20260607T050816/browser-compare.json | bundled_c_tor_browser | https://www.torproject.org/ | 2.471 | 7630.318 |  | yes |
| results/browser-compare-20260607T050816/browser-compare.json | local_c_tor_browser | https://www.torproject.org/ | 2.723 | 6856.266 |  | yes |
| results/browser-compare-20260607T051124/browser-compare.json | arti_release_browser | https://www.torproject.org/ | 0.349 | 8210.350 |  | yes |
| results/browser-compare-20260607T051124/browser-compare.json | bundled_c_tor_browser | https://www.torproject.org/ | 2.648 | 6451.071 |  | yes |
| results/browser-compare-20260607T051124/browser-compare.json | local_c_tor_browser | https://www.torproject.org/ | 2.609 | 6140.308 |  | yes |
| results/browser-compare-20260607T052016/browser-compare.json | arti_release_browser | https://www.torproject.org/ | 0.374 | 7602.815 |  | yes |
| results/browser-compare-20260607T052016/browser-compare.json | bundled_c_tor_browser | https://www.torproject.org/ | 2.658 | 7555.848 |  | yes |
| results/browser-compare-20260607T052016/browser-compare.json | local_c_tor_browser | https://www.torproject.org/ | 2.607 | 5580.001 |  | yes |
| results/browser-compare-20260607T052911/browser-compare.json | arti_release_browser | https://check.torproject.org/ | 0.363 | 3142.846 |  | yes |
| results/browser-compare-20260607T052911/browser-compare.json | arti_release_browser | https://www.torproject.org/ | 0.363 | 6906.145 |  | yes |
| results/browser-compare-20260607T052911/browser-compare.json | bundled_c_tor_browser | https://check.torproject.org/ | 2.584 | 2578.733 |  | yes |
| results/browser-compare-20260607T052911/browser-compare.json | bundled_c_tor_browser | https://www.torproject.org/ | 2.584 | 4804.915 |  | yes |
| results/browser-compare-20260607T052911/browser-compare.json | local_c_tor_browser | https://check.torproject.org/ | 3.093 | 3064.261 |  | yes |
| results/browser-compare-20260607T052911/browser-compare.json | local_c_tor_browser | https://www.torproject.org/ | 3.093 | 8926.593 |  | yes |
| results/browser-compare-20260607T053854/browser-compare.json | arti_release_browser | https://check.torproject.org/ | 0.352 | 2972.130 |  | yes |
| results/browser-compare-20260607T053854/browser-compare.json | arti_release_browser | https://www.torproject.org/ | 0.352 | 7407.018 |  | yes |
| results/browser-compare-20260607T053854/browser-compare.json | bundled_c_tor_browser | https://check.torproject.org/ | 2.652 | 2541.233 |  | yes |
| results/browser-compare-20260607T053854/browser-compare.json | bundled_c_tor_browser | https://www.torproject.org/ | 2.652 | 6651.218 |  | yes |
| results/browser-compare-20260607T053854/browser-compare.json | local_c_tor_browser | https://check.torproject.org/ | 2.566 | 2532.176 |  | yes |
| results/browser-compare-20260607T053854/browser-compare.json | local_c_tor_browser | https://www.torproject.org/ | 2.566 | 5186.279 |  | yes |
| results/browser-compare-20260607T054721/browser-compare.json | arti_release_browser | https://check.torproject.org/ | 0.329 | 3225.350 |  | yes |
| results/browser-compare-20260607T054721/browser-compare.json | arti_release_browser | https://www.torproject.org/ | 0.329 | 6101.834 |  | yes |
| results/browser-compare-20260607T054721/browser-compare.json | bundled_c_tor_browser | https://check.torproject.org/ | 3.094 | 3533.643 |  | yes |
| results/browser-compare-20260607T054721/browser-compare.json | bundled_c_tor_browser | https://www.torproject.org/ | 3.094 | 6933.538 |  | yes |
| results/browser-compare-20260607T054721/browser-compare.json | local_c_tor_browser | https://check.torproject.org/ | 2.635 | 2586.040 |  | yes |
| results/browser-compare-20260607T054721/browser-compare.json | local_c_tor_browser | https://www.torproject.org/ | 2.635 | 5303.721 |  | yes |
| results/browser-compare-20260607T055802/browser-compare.json | arti_release_browser | https://check.torproject.org/ | 0.354 | 3054.672 |  | yes |
| results/browser-compare-20260607T055802/browser-compare.json | arti_release_browser | https://www.torproject.org/ | 0.354 | 7880.094 |  | yes |
| results/browser-compare-20260607T055802/browser-compare.json | bundled_c_tor_browser | https://check.torproject.org/ | 2.564 | 2572.321 |  | yes |
| results/browser-compare-20260607T055802/browser-compare.json | bundled_c_tor_browser | https://www.torproject.org/ | 2.564 | 6058.568 |  | yes |
| results/browser-compare-20260607T055802/browser-compare.json | local_c_tor_browser | https://check.torproject.org/ | 2.627 | 2567.934 |  | yes |
| results/browser-compare-20260607T055802/browser-compare.json | local_c_tor_browser | https://www.torproject.org/ | 2.627 | 5940.822 |  | yes |
| results/cache-diagnostic-20260607T042439/cache-diagnostic.json | arti_release_cold | https://check.torproject.org/ | 21.649 | 1497.891 | 1497.825 | yes |
| results/cache-diagnostic-20260607T042439/cache-diagnostic.json | arti_release_cold | https://www.torproject.org/ | 21.649 | 1281.016 | 1107.633 | yes |
| results/cache-diagnostic-20260607T042439/cache-diagnostic.json | arti_release_warm | https://check.torproject.org/ | 0.372 | 1784.638 | 1784.556 | yes |
| results/cache-diagnostic-20260607T042439/cache-diagnostic.json | arti_release_warm | https://www.torproject.org/ | 0.372 | 1332.785 | 1187.800 | yes |
| results/cache-diagnostic-20260607T042439/cache-diagnostic.json | c_tor_cold | https://check.torproject.org/ | 10.550 | 1211.698 | 1211.603 | yes |
| results/cache-diagnostic-20260607T042439/cache-diagnostic.json | c_tor_cold | https://www.torproject.org/ | 10.550 | 950.878 | 861.248 | yes |
| results/cache-diagnostic-20260607T042439/cache-diagnostic.json | c_tor_warm | https://check.torproject.org/ | 2.632 | 1268.857 | 1192.420 | yes |
| results/cache-diagnostic-20260607T042439/cache-diagnostic.json | c_tor_warm | https://www.torproject.org/ | 2.632 | 1444.485 | 1248.474 | yes |

## Latest Quality Checks

| source | check | evidence | runtime path proof | full quality proof | ok |
|---|---|---|---|---|---|
| results/circuit-check-20260607T042121/c-tor-circuits.json | C Tor circuit probe | 6 checked circuits | yes | yes | yes |
| results/arti-quality-config-20260608T185645/arti-quality-config.json | Arti source/config | 34 static checks | no | no | yes |
| results/arti-rpc-path-20260607T134227/arti-rpc-path.json | Arti RPC path + directory | 3 checked paths | yes | yes | yes |

## Latest Proxy Compare

In `results/proxy-compare-20260607T034459/compare.json`, release Arti was faster
than stock C Tor on both small fetch targets:

- `check.torproject.org`: Arti `1047.479ms`, C Tor `1380.860ms`, about `24.1%`
  faster.
- `www.torproject.org`: Arti `1437.844ms`, C Tor `1669.580ms`, about `13.9%`
  faster.

C Tor booted faster: `8.576s` versus Arti `15.573s`.

## Latest Full Browser Compare

In `results/browser-compare-20260607T041426/browser-compare.json`, the same
verified Tor Browser app was run through each local SOCKS proxy:

- bundled Tor Browser Tor `0.4.9.9`
- local C Tor `0.5.0.0-alpha-dev`
- release Arti `2.4.0`

All browser runs passed. `tools/analyze_browser_compare.py` reported
`quality: PASS`. Each run saved a PNG screenshot and showed effective proxy
prefs of `127.0.0.1:<port>`, remote DNS `true`, and proxy type `1`.

Tor Browser default-pref evidence in the JSON includes:

- private browsing auto-start `true`
- DNS disabled `true`
- HTTP/3 enable pref `false`
- proxy allow-bypass pref `false`
- failover-direct pref `false`
- SOCKS remote DNS `true`
- resist fingerprinting `true`
- letterboxing `true`

The two-run browser timing does **not** show an Arti win:

- `check.torproject.org`: local C Tor `2443.044ms`, bundled Tor `2566.255ms`,
  Arti `3835.399ms`.
- `www.torproject.org`: local C Tor `5136.736ms`, bundled Tor `8089.704ms`,
  Arti `9764.843ms`.

Browser page-load deltas from the analyzer:

- `check.torproject.org`: Arti median load was `106.3%` slower than bundled
  Tor and `136.3%` slower than local C Tor.
- `www.torproject.org`: Arti median load was `24.4%` slower than bundled Tor
  and `125.4%` slower than local C Tor.

Arti also booted slower in this two-run browser sample: `31.934s`, with several
directory timeout log lines. Bundled Tor booted in `14.581s`; local C Tor booted
in `8.595s`.

## Latest Focused Browser Timing

In `results/browser-compare-20260607T045144/browser-compare.json`, the same
browser compare was run once against `https://www.torproject.org/` with
Navigation Timing and resource timing captured.

All profiles passed quality checks. The analyzer result was:

- Arti: total `5946.052ms`, load `4545.673ms`, boot `51.341s`.
- bundled Tor: total `8682.815ms`, load `6789.512ms`, boot `31.856s`.
- local C Tor: total `5016.938ms`, load `3557.624ms`, boot `28.829s`.

In this focused one-run sample, Arti was faster than bundled Tor, but still
slower than local C Tor:

- total time: Arti was `31.5%` faster than bundled Tor and `18.5%` slower than
  local C Tor.
- load time: Arti was `33.0%` faster than bundled Tor and `27.8%` slower than
  local C Tor.

Performance timing shows where this sample was slow:

- response start: Arti `1183.357ms`, local C Tor `1033.354ms`, bundled Tor
  `700.014ms`.
- load event: Arti `4533.424ms`, local C Tor `3550.071ms`, bundled Tor
  `6783.469ms`.
- slowest resource: Arti `1700.034ms`, local C Tor `1466.696ms`, bundled Tor
  `3900.078ms`.

Meaning: this is useful diagnostic proof, not a speed claim. Arti can beat
bundled Tor in one focused page-load run, but it still loses to local C Tor and
its boot was much slower because of directory failures.

## Latest Warm-Cache Browser Timing

In `results/browser-compare-20260607T050816/browser-compare.json`, each proxy
was bootstrapped once, stopped, then started again with the same cache/data dir
before running two Tor Browser loads against `https://www.torproject.org/`.

All profiles passed quality checks. The analyzer result was:

- Arti: warmup `9.554s`, measured boot `0.350s`, load `8607.444ms`.
- bundled Tor: warmup `18.563s`, measured boot `2.471s`, load `6064.782ms`.
- local C Tor: warmup `10.638s`, measured boot `2.723s`, load `5379.617ms`.

In this warm-cache two-run sample, Arti was not faster:

- total time: Arti was `32.8%` slower than bundled Tor and `47.8%` slower than
  local C Tor.
- load time: Arti was `41.9%` slower than bundled Tor and `60.0%` slower than
  local C Tor.

Performance timing:

- response start: Arti `2225.044ms`, bundled Tor `1583.365ms`, local C Tor
  `1358.361ms`.
- load event: Arti `8600.172ms`, bundled Tor `6058.454ms`, local C Tor
  `5375.108ms`.
- slowest resource: Arti `3875.077ms`, bundled Tor `2833.390ms`, local C Tor
  `3225.064ms`.

The analyzer's slow-resource table shows Arti's warm runs spent about `2.4s` to
`5.0s` on same-origin static files, including `tor-logo@2x.png`, Font Awesome
PNG files, and home-page SVGs.

Meaning: Arti warm bootstrap is good in this run. The browser slowdown is now
mainly after response start, around page resources, not directory bootstrap.

## Post-Boot Wait Diagnostic

In `results/browser-compare-20260607T051124/browser-compare.json`, the same
two-run warm-cache browser compare waited `12s` after measured proxy boot before
starting Tor Browser page loads. This is a diagnostic, not a speed claim.

All profiles passed quality checks. The analyzer result was:

- Arti: boot `0.349s`, post-boot wait `12s`, load `6766.720ms`.
- bundled Tor: boot `2.648s`, post-boot wait `12s`, load `5004.020ms`.
- local C Tor: boot `2.609s`, post-boot wait `12s`, load `4695.390ms`.

Compared with no post-boot wait, Arti improved from `8607.444ms` load to
`6766.720ms`. Response start improved from `2225.044ms` to `1333.360ms`.

Meaning: letting Arti sit after bootstrap probably gives preemptive circuits
time to become useful. But this still does not beat C Tor, and adding a visible
wait is not a real speed win. The next safe path is to make useful circuits
ready earlier without changing path quality.

## Patched Arti Preemptive Recheck

The local Arti lab patch in
`upstream/arti/crates/tor-circmgr/src/lib.rs` changes the preemptive circuit
recheck delay from `10s` to `1s`. It does not change circuit length, relay
family checks, subnet checks, crypto, padding, or browser fingerprint prefs.

In `results/browser-compare-20260607T052016/browser-compare.json`, the patched
release Arti binary was tested with warm cache, no post-boot wait, two browser
runs, and compact output. The result JSON records:

- `source_tweaks.arti_preemptive_recheck_seconds = 1`
- Arti: boot `0.374s`, load `6184.888ms`.
- bundled Tor: boot `2.658s`, load `5976.150ms`.
- local C Tor: boot `2.607s`, load `4147.518ms`.

Compared with the previous no-wait warm-cache Arti result, the patch improved
Arti load from `8607.444ms` to `6184.888ms`, and response start from
`2225.044ms` to `1350.027ms`.

The patched Arti run still did not win:

- load time was `3.5%` slower than bundled Tor.
- load time was `49.1%` slower than local C Tor.

Meaning: earlier preemptive-circuit readiness is a real safe speed direction,
but it is not enough by itself. The next useful work is still around slow page
resources and stream/circuit use.

## Trusted Sequential Patched 5-Run Browser Compare

In `results/browser-compare-20260607T055802/browser-compare.json`, the patched
release Arti binary was tested with warm cache, no post-boot wait, compact
output, 5 browser runs, and two targets. Both C Tor SOCKS listeners used
`IsolateSOCKSAuth`:

- `https://check.torproject.org/`
- `https://www.torproject.org/`

All profiles passed quality checks. The JSON records:

- `source_tweaks.arti_preemptive_recheck_seconds = 1`
- `source_tweaks.arti_socks_connect_optimistic = true`
- C Tor profiles record `torrc.isolate_socks_auth = true`

Page-only load time still does not beat C Tor in this stronger sample:

- `check.torproject.org`: Arti `1710.507ms`, bundled Tor `1232.489ms`, local C
  Tor `1237.958ms`.
- `www.torproject.org`: Arti `6474.450ms`, bundled Tor `4497.549ms`, local C
  Tor `4524.303ms`.

Launch-to-load still shows an Arti win because warm-cache Arti booted in
`0.354s`:

- `check.torproject.org`: Arti `2064.507ms`, bundled Tor `3796.489ms`, local C
  Tor `3864.958ms`.
- `www.torproject.org`: Arti `6828.450ms`, bundled Tor `7061.549ms`, local C
  Tor `7151.303ms`.

Analyzer deltas:

- page-only load: Arti was `38.8%` slower than bundled Tor on
  `check.torproject.org`, and `44.0%` slower than bundled Tor on
  `www.torproject.org`.
- page-only load also lost to local C Tor: `38.2%` slower on
  `check.torproject.org`, and `43.1%` slower on `www.torproject.org`.
- launch-to-load: Arti was `45.6%` faster than bundled Tor on
  `check.torproject.org`, and `3.3%` faster than bundled Tor on
  `www.torproject.org`.
- launch-to-load also beat local C Tor: `46.6%` faster on
  `check.torproject.org`, and `4.5%` faster on `www.torproject.org`.

The previous 3-run sample showed an Arti page-only win over bundled Tor, but
this 5-run sample did not confirm it. Treat the 3-run result as useful but too
noisy for a speed claim.

Meaning: patched Arti is still a launch-to-load win, but not yet a page-load
win. The next safe work is to reduce page-only load time without changing relay
choice or browser privacy behavior.

## Rotating Interleaved 5-Run Browser Compare

In `results/browser-compare-20260607T062155/browser-compare.json`, the corrected
interleaved schedule ran all measured proxies in the same window, waited for
boot concurrently, then rotated the starting profile by run and target. The run
used warm cache, compact output, 5 browser runs, and two targets. Both C Tor
SOCKS listeners used `IsolateSOCKSAuth`.

All profiles passed quality checks. The analyzer result was:

- Arti: boot `0.397s`; load `1167.038ms` on `check.torproject.org` and
  `4493.003ms` on `www.torproject.org`.
- bundled Tor: boot `2.661s`; load `1218.789ms` on `check.torproject.org` and
  `4098.213ms` on `www.torproject.org`.
- local C Tor: boot `2.657s`; load `1344.792ms` on `check.torproject.org` and
  `3230.636ms` on `www.torproject.org`.

Page-only load is mixed:

- `check.torproject.org`: Arti was `4.2%` faster than bundled Tor and `13.2%`
  faster than local C Tor.
- `www.torproject.org`: Arti was `9.6%` slower than bundled Tor and `39.1%`
  slower than local C Tor.

Launch-to-load is a clear Arti win in this sample:

- `check.torproject.org`: Arti was `59.7%` faster than bundled Tor and `60.9%`
  faster than local C Tor.
- `www.torproject.org`: Arti was `27.7%` faster than bundled Tor and `16.9%`
  faster than local C Tor.

The new navigation phase table shows where the homepage loss is:

- Arti homepage: response start `1316.693ms`, response-to-DOM `1500.030ms`,
  DOM-to-load `1950.039ms`.
- bundled Tor homepage: response start `833.350ms`, response-to-DOM
  `1416.695ms`, DOM-to-load `1916.705ms`.
- local C Tor homepage: response start `1000.020ms`, response-to-DOM
  `1166.690ms`, DOM-to-load `1116.689ms`.

Meaning: Arti's remaining homepage page-only loss is not boot. It starts with a
slower first response, then continues through page construction and resources.

Earlier interleaved files `20260607T060736` and `20260607T061118` used the same
fixed profile order but measured some boot times incorrectly. Result
`20260607T061526` fixed boot timing but still used fixed profile order. Treat
all three as superseded by `20260607T062155` for the current interleaved claim.

Meaning: patched Arti is still not a full page-only winner because the Tor
homepage is slower through Arti in this sample. It does win launch-to-load on
both targets because warm-cache Arti boot is much faster.

## Arti Homepage Debug Diagnostic

In `results/browser-compare-20260607T063128/browser-compare.json`, the harness
ran one rotating interleaved homepage load with `--arti-log-level debug` and
saved proxy log tails. This is a diagnostic, not a speed proof.

All profiles passed quality checks. In this one run, Arti happened to win the
homepage page-only load:

- Arti: load `3254.774ms`, boot `0.400s`.
- bundled Tor: load `4734.568ms`, boot `2.845s`.
- local C Tor: load `5313.939ms`, boot `2.741s`.

The useful part is the new proxy-log signal table. The Arti tail had:

- `10` SOCKS CONNECT requests.
- `9` circuit assignments.
- `10` ready streams.
- `7` preemptive circuit creation log lines.
- `13` spawned reactor lines.
- `12` onion-service connect log lines.

Meaning: the harness can capture enough Arti proxy logs to inspect stream and
circuit behavior during a browser page load. The next diagnostic below adds
per-SOCKS timing, because counts alone do not prove which stream phase causes
the remaining multi-run homepage loss.

## Arti SOCKS Timing Diagnostic

In `results/browser-compare-20260607T063922/browser-compare.json`, the release
Arti binary was rebuilt with local debug-only SOCKS timing logs. The harness ran
one rotating interleaved homepage load with `--arti-log-level debug` and saved
proxy log tails. This is a diagnostic, not a speed proof.

All profiles passed quality checks. In this one run, Arti lost page-only load:

- Arti: load `6601.660ms`, boot `0.393s`.
- bundled Tor: load `3532.303ms`, boot `2.895s`.
- local C Tor: load `4796.291ms`, boot `3.011s`.

The new Torfast SOCKS timing table showed:

- `13` Arti SOCKS requests.
- `13` ready streams.
- median connect time `0ms`.
- max connect time `5000ms`.
- `1` connect at or above `1s`.
- median relay time `3428ms`.
- max relay time `7024ms`.

The notable stream table showed four rows:

- timing id `1`: reason `relay>=5s`, connect `0ms`, relay `7024ms`.
- timing id `2`: reason `relay>=5s`, connect `0ms`, relay `5556ms`.
- timing id `7`: reason `relay>=5s`, connect `0ms`, relay `5471ms`.
- timing id `8`: reason `connect>=1s`, connect `5000ms`, relay `275ms`.

The context table showed timing id `8` had `91` log lines between request and
stream-ready, including `12` onion-service connect lines, `2` hspool lines, and
`9` spawned reactors. The three `relay>=5s` rows were ready immediately, so
those relay durations are stream lifetime signals, not proof that stream setup
blocked the browser.

Meaning: in this run, most Arti SOCKS streams were assigned immediately. The
clearest setup delay is timing id `8`, which waited `5s` while onion-service
work was happening. That points to onion-service stream/circuit setup as the
next bottleneck to inspect, not proxy boot.

## Arti HsPool Timing Diagnostic

In `results/browser-compare-20260607T065452/browser-compare.json`, release Arti
was rebuilt again with debug-only `torfast hspool` timing logs. The harness ran
one rotating interleaved homepage load with `--arti-log-level debug` and saved
proxy log tails. This is a diagnostic, not a speed proof.

All profiles passed quality checks. In this one run, Arti happened to win
page-only load:

- Arti: load `2441.616ms`, boot `0.393s`.
- bundled Tor: load `5570.727ms`, boot `2.816s`.
- local C Tor: load `3867.000ms`, boot `2.879s`.

The useful diagnostic facts were:

- `8` Arti SOCKS requests.
- `7` ready streams.
- `0ms` max SOCKS connect time among streams that became ready.
- `1` unfinished SOCKS request: timing id `3`.
- `5` `torfast hspool` lines.
- `1` on-demand guarded HsPool launch, ready in `783ms`.
- `3` background naive HsPool launches, median `725ms`, max `831ms`.
- no onion-service connect lines in this run.

Meaning: the earlier `5s` onion-service setup delay did not repeat. In this
run, the HsPool on-demand guarded circuit was ready in under `1s`, and the page
still loaded quickly. The old slowdown is intermittent, so the next step is to
collect a small multi-run debug sample and compare slow runs against fast runs.

## Three-Run HsPool Debug Sample

In `results/browser-compare-20260607T065905/browser-compare.json`, the harness
ran a 3-run rotating interleaved homepage debug sample with the same HsPool
timing logs. This is better bottleneck evidence than a one-run diagnostic, but
it is still not a fair release-speed proof.

All profiles passed quality checks. In this debug sample, Arti had the best
median page-only load, but bundled C Tor had one very slow run and a very slow
warmup, so do not use this file as the main speed claim:

- Arti: median load `3602.570ms`, boot `0.401s`, warmup `6.703s`.
- bundled Tor: median load `14577.117ms`, boot `2.742s`, warmup `174.012s`.
- local C Tor: median load `4413.714ms`, boot `2.716s`, warmup `15.566s`.

The useful diagnostic facts were:

- `30` Arti SOCKS requests and `30` ready streams.
- max SOCKS connect time `3396ms`.
- `3` connects at or above `1s`: timing ids `17`, `3`, and `25`.
- `36` onion-service connect lines.
- `22` `torfast hspool` lines.
- `9` HsPool stem reuses.
- `0` on-demand HsPool launches.
- `13` background HsPool launches, median `454ms`, max `723ms`.

The three slow connect IDs all had onion-service context:

- timing id `17`: connect `3396ms`, `12` HS lines, `7` HsPool lines.
- timing id `3`: connect `2812ms`, `12` HS lines, `6` HsPool lines.
- timing id `25`: connect `2213ms`, `12` HS lines, `6` HsPool lines.

Meaning: this sample points away from HsPool circuit construction as the main
delay. HsPool reused ready guarded stems, and background launches were under
`1s`. The remaining slow connect cases happen during onion-service
rendezvous/introduction work after a stem has been reused.

## Two-Run HS Timing Debug Sample

In `results/browser-compare-20260607T071052/browser-compare.json`, release Arti
was rebuilt with debug-only onion-service protocol timing logs. The harness ran
a 2-run rotating interleaved homepage debug sample with `--arti-log-level
debug`. This is bottleneck evidence only, not a fair speed proof.

All profiles passed quality checks. Arti was faster in this noisy sample, but
local C Tor had a huge page-load outlier, so this file should not replace the
current 5-run interleaved proof:

- Arti: median load `4284.801ms`, boot `0.391s`, warmup `8.191s`.
- bundled Tor: median load `10188.429ms`, boot `2.873s`, warmup `19.621s`.
- local C Tor: median load `77895.012ms`, boot `3.027s`, warmup `12.682s`.

The useful diagnostic facts were:

- `22` Arti SOCKS requests and `22` ready streams.
- max SOCKS connect time `43499ms`.
- `2` connects at or above `1s`: timing ids `3` and `16`.
- `19` `torfast hspool` lines and `12` `torfast hs timing` lines.
- `6` HsPool stem reuses.
- `1` on-demand guarded HsPool launch, ready in `958ms`.
- `11` background HsPool launches, median `523ms`, max `910ms`.
- `2` complete HS timing sequences.
- HS rendezvous established median `246.5ms`.
- HS introduce ack median `410ms`.
- HS RENDEZVOUS2 median `515ms`, max `522ms`.

The two slow connect IDs both had onion-service context:

- timing id `3`: connect `43499ms`, `12` HS lines, `12` HsPool lines.
- timing id `16`: connect `2260ms`, `12` HS lines, `3` HsPool lines.

Meaning: in this sample, the visible HS rendezvous/introduction protocol was
fast once it started. The biggest SOCKS wait included a long gap before the
visible HS sequence. The next diagnostic should correlate each SOCKS timing id
with the start of its HS connect sequence, so we can separate queue/wait time
from actual rendezvous/introduction protocol time.

## One-Run HS Client Phase Diagnostic

In `results/browser-compare-20260607T072725/browser-compare.json`, release Arti
was rebuilt with debug-only HS client phase logs and redacted SOCKS
`target_kind` fields. The harness ran one rotating interleaved homepage debug
sample. This run failed Arti page quality because the Arti browser load timed
out, so it is not speed proof.

The useful diagnostic facts were:

- Arti had `3` SOCKS requests: `2` normal hostname requests and `1` onion
  request.
- The onion request was timing id `3`, with SOCKS connect `3328ms`.
- HS client timing started immediately after the SOCKS request.
- HS client tunnel ready was `2975ms`.
- HS client begin stream finished at `3328ms` with `ok=true`.
- HsPool on-demand guarded launch was ready in `546ms`.
- HS rendezvous established was `393ms`.
- HS introduce ack was `813ms`.
- HS RENDEZVOUS2 was `305ms`.
- After SOCKS stream-ready, relay time was very slow: onion relay `56251ms`;
  hostname relays `59769ms` and `60200ms`.

Meaning: this run points past hidden-service setup. The onion setup path was
ready in about `3.3s`, but the page then timed out during data relay/resource
loading. The next safe bottleneck is stream relay/resource behavior after the
stream is connected, not path length, crypto, or the visible HS protocol.

## One-Run Relay Byte Diagnostic

In `results/browser-compare-20260607T074146/browser-compare.json`, release Arti
was rebuilt with debug-only relay byte counting. The harness ran one rotating
interleaved `check.torproject.org` debug sample. This run passed quality, but it
is one run on a small page, so it is still diagnostic only.

Timing:

- Arti: load `1325.732ms`, boot `0.382s`, boot+load `1707.732ms`.
- bundled Tor: load `793.599ms`, boot `2.599s`, boot+load `3392.599ms`.
- local C Tor: load `1860.946ms`, boot `2.819s`, boot+load `4679.946ms`.

The useful diagnostic facts were:

- Arti had `3` SOCKS requests.
- `2` hostname streams were ready immediately.
- The two finished hostname relays had median relay time `1514.500ms`.
- Median client-to-Tor bytes were `2727`.
- Median Tor-to-client bytes were `12139`.
- The onion request was unfinished in the captured tail.

Meaning: the byte counter works and shows that normal page streams can transfer
data before closing with a relay error. For the larger homepage timeout, the
next step is to capture the same byte counters there and separate "no data
arrived" from "some data arrived but later resources stalled."

## One-Run Homepage Byte Diagnostic

In `results/browser-compare-20260607T074551/browser-compare.json`, release Arti
was rebuilt with the same debug-only relay byte counting and run against the Tor
homepage. The run passed quality, but it is one debug run, so it is still
diagnostic only.

Timing:

- Arti: load `4252.457ms`, boot `0.399s`, boot+load `4651.457ms`.
- bundled Tor: load `5133.733ms`, boot `2.965s`, boot+load `8098.733ms`.
- local C Tor: load `5577.506ms`, boot `2.666s`, boot+load `8243.506ms`.

The useful diagnostic facts were:

- Arti had `9` SOCKS requests.
- `8` streams became ready immediately with median connect time `0ms`.
- Finished streams were normal `hostname` streams.
- The `8` finished streams used `3` unique circuits.
- The top circuit, `Circ 0.1`, handled `6` streams.
- The finished streams had median relay time `3188ms`.
- Median client-to-Tor bytes were `4284`.
- Median Tor-to-client bytes were `226595`.
- The one unfinished stream was `target_kind=onion`, timing id `8`.
- That onion request reached HS client start/bootstrap/netdir/keys, but did not
  reach tunnel-ready or begin-stream in the captured tail.
- The page still passed quality, so that onion request was not on the critical
  page-load path in this run.

Meaning: the latest homepage diagnostic points away from hidden-service setup as
the main page-load path for `www.torproject.org`. The page load was mostly
normal hostname streams with real data transfer, and most streams reused one
exit circuit. The next safe bottleneck is exit-stream/resource behavior:
response-to-DOM and resource loading, not path length, crypto, or the unfinished
onion side request.

## One-Run Arti SOCKS Buffer Experiment

In `results/browser-compare-20260607T075831/browser-compare.json`, Arti was run
with `proxy.socket_send_buf_size="1 MB"` and
`proxy.socket_recv_buf_size="1 MB"`. This changes only the local browser-to-Arti
SOCKS sockets. It does not change Tor path length, relay choice, crypto, or
browser privacy prefs. The run passed quality, but it is one run only.

Timing:

- Arti: load `4236.840ms`, boot `0.399s`, boot+load `4635.840ms`.
- bundled Tor: load `3877.678ms`, boot `2.726s`, boot+load `6603.678ms`.
- local C Tor: load `5168.112ms`, boot `2.796s`, boot+load `7964.112ms`.

Meaning: the larger local SOCKS buffer is not a clear win. Arti's page-only load
was almost the same as the prior default-buffer homepage diagnostic
(`4252.457ms`), and Arti was slower than bundled Tor on page-only load in this
run. Do not turn this into a default without stronger A/B evidence.

The analyzer now prints slow resource phase splits. In this run, Arti's slowest
resources had wait times around `316ms` to `466ms` and receive times around
`16ms` to `150ms`, so the visible slow-resource cost is mostly scheduling/gap
time around resources rather than large body transfer time.

## Removed Scheduler Batch Experiment

In `results/browser-compare-20260607T080620/browser-compare.json`, a temporary
Arti patch batched up to 4 already-ready outbound stream cells per circuit
reactor turn. The run passed quality, but it was slower and the patch was
removed.

Timing:

- Arti: load `6020.619ms`, boot `0.395s`, boot+load `6415.619ms`.
- bundled Tor: load `4166.283ms`, boot `2.846s`, boot+load `7012.283ms`.
- local C Tor: load `4890.584ms`, boot `2.958s`, boot+load `7848.584ms`.

Meaning: this batch shape is not a safe speed win. It made Arti `44.5%` slower
than bundled Tor on page-only load in this one run. Do not retry this exact
batching change without a better scheduler model and deeper traffic-shape
review.

## Latest Stream Scheduler Diagnostic

In `results/browser-compare-20260607T081637/browser-compare.json`, release Arti
was rebuilt with debug-only stream scheduler logs. This was a diagnostic run,
not a fair speed proof. It passed quality.

Timing:

- Arti: load `5479.681ms`, boot `0.387s`, boot+load `5866.681ms`.
- bundled Tor: load `4284.098ms`, boot `3.181s`, boot+load `7465.098ms`.
- local C Tor: load `4568.295ms`, boot `2.938s`, boot+load `7506.295ms`.

Scheduler facts from the Arti proxy tail:

- picked `164` outbound DATA cells.
- closed `14` streams.
- saw `0` hop-level scheduler blocks.
- touched `16` unique stream ids.

Meaning: the simple circuit scheduler was not visibly stuck on send capacity in
this run. The remaining homepage gap still looks more like resource/relay timing
after connection than a basic "ready stream cannot be picked" problem.

## Latest Relay Receive Diagnostic

In `results/browser-compare-20260607T082829/browser-compare.json`, release Arti
was rebuilt with debug-only receive-side relay delivery logs. This was a
diagnostic run, not a fair speed proof. It passed quality.

Timing:

- Arti: load `5217.089ms`, boot `0.394s`, boot+load `5611.089ms`.
- bundled Tor: load `4274.955ms`, boot `2.963s`, boot+load `7237.955ms`.
- local C Tor: load `4792.050ms`, boot `2.819s`, boot+load `7611.050ms`.

Receive-side facts from the Arti proxy tail:

- delivered `2825` relay messages to streams.
- delivered `2813` DATA messages.
- saw `0` queue-full events.
- saw `0` stream-gone receive events.
- touched `11` stream ids.
- median queued-after bytes: `1992`.
- max queued-after bytes: `20754`.

Meaning: the local Arti stream receive queue was not filling up in this run.
The page gap is more likely in network/relay timing, circuit choice under load,
or browser resource timing, not a simple local queue backpressure bug.

## Latest Circuit Selection Diagnostic

In `results/browser-compare-20260607T084058/browser-compare.json`, release Arti
was rebuilt with debug-only circuit-selection logs. This was a 1-run homepage
diagnostic, not a fair speed proof. It passed quality.

Timing:

- Arti: load `4281.488ms`, boot `0.395s`, boot+load `4676.488ms`.
- bundled Tor: load `4437.963ms`, boot `2.853s`, boot+load `7290.963ms`.
- local C Tor: load `4965.919ms`, boot `2.839s`, boot+load `7804.919ms`.

Circuit-selection facts from the Arti proxy tail:

- saw `61` open-circuit picks.
- median open candidates: `2`.
- max open candidates: `3`.
- median select parallelism: `1`.
- circuit assignments were concentrated: `13` assignments, `3` unique circuits,
  top circuit `Circ 0.2` used `11` times.
- top relay receive streams were also concentrated on `Circ 0.2`.

Meaning: Arti often had more than one matching open circuit, but normal
selection still chose from only one. That makes exit-circuit spreading a real
candidate to test, as long as it keeps the same isolation and circuit
eligibility rules.

## Latest Exit Circuit Spread Candidate

In `results/browser-compare-20260607T084444/browser-compare.json`, local Arti
used the lab exit-select override at width `3`. This did not launch extra
circuits and did not relax stream isolation; it only picked among circuits that
already supported the same target usage. This was a 1-run A/B diagnostic, not a
fair speed proof. It passed quality.

Timing:

- Arti: load `3892.070ms`, boot `0.393s`, boot+load `4285.070ms`.
- bundled Tor: load `3109.866ms`, boot `2.681s`, boot+load `5790.866ms`.
- local C Tor: load `2914.536ms`, boot `2.733s`, boot+load `5647.536ms`.

Circuit facts from the Arti proxy tail:

- saw `40` open-circuit picks.
- `7` open picks had select parallelism greater than `1`.
- those spread picks selected `3` different circuits.
- circuit assignments were less concentrated: `7` assignments, `3` unique
  circuits, top circuit used `3` times.
- top relay receive streams were split across `Circ 0.1`, `Circ 0.0`, and
  smaller streams on other circuits.

Meaning: the candidate did spread page streams across valid open circuits and
reduced the one-circuit pileup seen in the prior diagnostic. It is not yet a
win claim: this single pass was noisy, and Arti page-only load was still slower
than both C Tor profiles in that same run. The next proof needs a repeated
interleaved run.

## Latest Exit-Spread Interleaved Proof

In `results/browser-compare-20260607T085332/browser-compare.json`, local Arti
used the exit-spread patch in a repeated rotating interleaved browser run. This
run used 5 runs, warm cache, compact output, two targets, and `--arti-log-level
info` so debug logging would not skew the speed result. It passed quality.

Timing:

- `check.torproject.org` page-only load:
  - Arti: `1662.317ms`.
  - bundled Tor: `2066.908ms`.
  - local C Tor: `1309.308ms`.
- `www.torproject.org` page-only load:
  - Arti: `5530.292ms`.
  - bundled Tor: `5950.900ms`.
  - local C Tor: `5192.698ms`.
- `check.torproject.org` boot+load:
  - Arti: `2063.317ms`.
  - bundled Tor: `4669.908ms`.
  - local C Tor: `4117.308ms`.
- `www.torproject.org` boot+load:
  - Arti: `5931.292ms`.
  - bundled Tor: `8553.900ms`.
  - local C Tor: `8000.698ms`.

Meaning: exit-spread Arti now beats bundled C Tor page-only on both targets and
keeps the large warm-cache boot+load win. It still does not beat local C Tor on
page-only load, so the final "faster Tor with exact quality" goal is not met.
Keep the candidate for now, but the next work must target the remaining
page-only gap versus local C Tor.

The analyzer now prints phase deltas against local C Tor and a resource phase
summary. On this accepted proof, Arti is mainly late before first browser
response: `+483.343ms` on `check.torproject.org` and `+466.676ms` on the
homepage. Later browser phases are close: Arti is `-0.000ms` response-to-DOM
and `+0.000ms` DOM-to-load on `check.torproject.org`, and `-50.001ms`
response-to-DOM and `+116.669ms` DOM-to-load on the homepage. The next
bottleneck to inspect is normal hostname first-response delay, not more
preemptive circuits.

## First-Byte Diagnostic

`results/browser-compare-20260607T093521/browser-compare.json` added
debug-only SOCKS first-byte timing. It was a one-run debug diagnostic, not a
speed claim. It passed quality. For normal hostname streams, Arti used
optimistic SOCKS replies immediately: median connect `0.000ms`, median reply
elapsed `0.000ms`. Median first bytes from Tor to the browser arrived after
`423.000ms`, and median relay lifetime was `3702.000ms`.

`results/browser-compare-20260607T094307/browser-compare.json` added epoch
timestamps on both sides so browser `responseStart` can be lined up with Arti
SOCKS first-byte timing. It was a one-target debug diagnostic and passed
quality. For `check.torproject.org`, the nearest hostname SOCKS first Tor byte
arrived `747.545ms` before browser `responseStart`.

Meaning: the current first-response gap is not waiting for any Tor DATA at all.
Arti receives initial Tor bytes before the browser reports HTTP response start.
The next bottleneck is the interval after first Tor bytes arrive, likely TLS
and HTTP response round trips over the stream, plus later resource relay timing.

`results/browser-compare-20260607T095237/browser-compare.json` added a bounded
debug-only byte timeline for the first chunks on each SOCKS stream. It was a
one-target debug diagnostic and passed quality. For the two normal hostname
streams:

- client-to-Tor bytes started at `0ms` on both streams.
- first Tor-to-client bytes arrived at `314ms` and `326ms`.
- shown Tor-to-client events continued until `955ms` and `735ms`.
- max shown Tor-to-client gaps were `202ms` and `277ms`.
- shown client-to-Tor events continued until `955ms` and `950ms`.
- max shown client-to-Tor gaps were `316ms` and `490ms`.
- nearest hostname SOCKS first Tor byte arrived `424.128ms` before browser
  `responseStart`.

Meaning: Arti is not stuck before the first encrypted server bytes. The visible
delay is in the encrypted conversation after initial bytes, where browser,
TLS/HTTP, stream scheduling, relay pacing, and resource loading can all matter.

## Neutral Byte-Tap Proof

`results/browser-compare-20260607T100351/browser-compare.json` added the same
local TCP byte-timing tap in front of bundled C Tor, local C Tor, and Arti. It
was a 3-run rotating interleaved sample with warm cache, compact output, two
targets, and `--arti-log-level info`. It passed quality.

Page-only load:

- `check.torproject.org`: Arti `1023.115ms`, bundled C Tor `1152.590ms`,
  local C Tor `1095.867ms`.
- `www.torproject.org`: Arti `4342.852ms`, bundled C Tor `4529.498ms`,
  local C Tor `5127.379ms`.

Neutral first stream-data timing:

- Arti median first stream data: `401.870ms`.
- bundled C Tor median first stream data: `604.255ms`.
- local C Tor median first stream data: `644.909ms`.

Resource-to-byte-tap replay:

- The analyzer now maps browser resources to nearest tap connections when byte
  tap data is present.
- In this old passing tap proof, several slow bundled C Tor homepage resources in
  run 3 mapped with high confidence to the same tap connection `41`.
- That connection carried `143311` stream-data bytes and had max shown proxy data
  gap `238.737ms`.
- Rows on that same connection included `circle-pattern.svg`,
  `browse-freely.svg`, `fingerprinting.svg`, `encryption.svg`, and multiple
  fontawesome icon resources.

Meaning: with the same tap in front of every proxy, Arti delivered first real
stream data earlier in this run. This is useful bottleneck evidence, not the
final speed proof, because the tap is still an extra local hop. The new resource
join table is useful for the next tap run because it can show whether late
HTTP/1.1 resources share one browser-to-proxy TCP connection.

## Earlier Normal Interleaved Win

`results/browser-compare-20260607T100731/browser-compare.json` repeated the
same shape without the byte tap. It was a 3-run rotating interleaved sample
with warm cache, compact output, two targets, and `--arti-log-level info`. It
passed quality.

Page-only load:

- `check.torproject.org`: Arti `1033.798ms`, bundled C Tor `1723.884ms`,
  local C Tor `1902.607ms`.
- `www.torproject.org`: Arti `3591.679ms`, bundled C Tor `5404.347ms`,
  local C Tor `5193.565ms`.

Boot+load:

- `check.torproject.org`: Arti `1428.798ms`, bundled C Tor `5136.884ms`,
  local C Tor `5646.607ms`.
- `www.torproject.org`: Arti `3986.679ms`, bundled C Tor `8817.347ms`,
  local C Tor `8937.565ms`.

Meaning: this is the first normal browser sample where patched Arti beats both
C Tor profiles on both pages, while all browser quality checks pass. It is
strong progress, but not the final claim yet: it is 3 runs, C Tor varied
between nearby samples, and the earlier 5-run proof did not beat local C Tor.
Next proof should repeat this at 5+ runs and add more targets.

## Latest Normal Interleaved Proof

`results/browser-compare-20260607T101326/browser-compare.json` ran a stronger
normal no-tap proof. It used 5 runs, warm cache, compact output, three targets,
and `--arti-log-level info`. It passed quality.

Page-only load:

- `check.torproject.org`: Arti `1561.395ms`, bundled C Tor `1960.175ms`,
  local C Tor `1623.443ms`.
- `www.torproject.org`: Arti `3793.446ms`, bundled C Tor `6064.431ms`,
  local C Tor `3387.670ms`.
- `www.torproject.org/download/`: Arti `5780.675ms`, bundled C Tor
  `6553.387ms`, local C Tor `5135.034ms`.

Paired run deltas versus local C Tor:

- `check.torproject.org`: Arti won `2/5` paired page-load runs, median paired
  load delta `+55.432ms`.
- `www.torproject.org`: Arti won `1/5`, median paired load delta `+228.109ms`.
- `www.torproject.org/download/`: Arti won `1/5`, median paired load delta
  `+365.712ms`.

Boot+load still favors Arti because warm-cache boot is much faster:

- `check.torproject.org`: Arti `1962.395ms`, bundled C Tor `4631.175ms`,
  local C Tor `4278.443ms`.
- `www.torproject.org`: Arti `4194.446ms`, bundled C Tor `8735.431ms`,
  local C Tor `6042.670ms`.
- `www.torproject.org/download/`: Arti `6181.675ms`, bundled C Tor
  `9224.387ms`, local C Tor `7790.034ms`.

Meaning: patched Arti now reliably beats bundled C Tor in this local suite and
keeps a large launch-to-load win. It does not yet beat local C Tor on
page-only load for heavier pages. The remaining gap is mainly later page and
resource work: on the download page, Arti is `+266.672ms` at first response and
`+566.678ms` from DOM to load versus local C Tor.

The analyzer now also prints resource type and top-resource deltas against local
C Tor. In this accepted 5-run proof, the download-page resource type gaps are:

- CSS: Arti `+500.010ms`.
- Images: Arti `+566.678ms`.
- Other resources, mostly fonts: Arti `+316.673ms`.
- Scripts: Arti `-100.002ms`.

Top slower resources include `SourceCodePro-Regular.ttf` at `+1100.022ms`,
`fa-regular-400.woff2` at `+1000.020ms`, and `tor-logo@2x.png` at
`+983.353ms`. This supports the same conclusion: the next safe work is
later page/resource timing, not shorter paths or weaker browser privacy.

## Rejected 5-Run Byte-Tap Proof

`results/browser-compare-20260607T102046/browser-compare.json` repeated the
same 5-run, three-target shape with `--byte-tap`. It failed quality and must
not be used as speed proof.

Why:

- Arti `check.torproject.org` run 4 hit a neterror `connectionFailure`.
- Arti `www.torproject.org` run 3 hit a neterror `netTimeout`.
- screenshots were missing for both failed runs.

Useful but rejected diagnostic fact: among successful connections, neutral
median first stream-data-to-browser timing was Arti `572.538ms`, bundled C Tor
`589.220ms`, and local C Tor `726.834ms`. Because quality failed, this only
suggests the local C Tor gap is not simply first stream-data arrival; it does
not prove speed.

## Download Page Debug Resource Diagnostic

`results/browser-compare-20260607T103305/browser-compare.json` ran one focused
download-page diagnostic with `--arti-log-level debug`. It passed quality, but it
is not speed proof because debug logging made Arti much slower: page-only load
was Arti `13644.534ms`, bundled C Tor `6262.635ms`, and local C Tor
`5476.778ms`.

Useful bottleneck facts from this debug run:

- Arti reached browser response earlier than local C Tor by `516.677ms`, but then
  lost `1983.373ms` from response to DOM and `6683.467ms` from DOM to load.
- Arti resource median duration was `3433.402ms`, versus local C Tor
  `1325.026ms`.
- Resource type duration gaps versus local C Tor were large for CSS
  `+2883.391ms`, images `+2858.391ms`, scripts `+1433.362ms`, and other
  resources `+1908.372ms`.
- Arti relay receive logs showed `1845` delivered relay messages, `1838` DATA
  messages, `0` queue-full events, and `0` stream-gone receive events.
- Stream scheduler logs showed `44` DATA picks and `0` hop-level scheduler
  blocks.

Meaning: this debug run again points after first response, around resource relay
and page load. It does not show a simple local queue-full or hop-send-capacity
block.

## Retained-Signal Circuit Selection Diagnostic

`results/browser-compare-20260607T104652/browser-compare.json` ran one focused
download-page diagnostic with `--arti-log-level debug` after adding
`proxy_signal_lines` retention. It passed quality. It is still debug evidence,
not speed proof.

What it proved:

- The JSON kept `556` retained signal lines plus an `800` line proxy tail.
- The analyzer saw `626` unique proxy log lines after de-duplicating retained
  signals and tail lines.
- Normal exit-stream selection did use the exit-spread patch: `6` open exit
  picks had `select_parallelism=3`.
- Those `6` exit picks selected `4` unique circuits; the circuit-assignment
  summary had `6` assignments across `4` circuits.
- The same run still showed `0` relay receive queue-full events and `0`
  hop-level scheduler blocks.

The one-run page timing was mixed and should not be used as proof: Arti load was
`4233.716ms`, bundled C Tor `3715.657ms`, and local C Tor `4494.001ms`.

Meaning: the wider exit-select override is not just present in source; it can
be used for normal exit streams in a real browser page load. Later stronger
A/B evidence rejected width `3` as the default, so this remains lab-only.

## Same-Window Exit-Select A/B

`results/browser-compare-20260607T113402/browser-compare.json` is the latest
accepted exit-select A/B. It ran Arti width `3`, Arti control width `1`, and
local C Tor in one measured proxy window. It used warm cache, compact output,
interleaved schedule, `--skip-bundled-tor`, 5 runs, 3 targets,
`--arti-log-level info`, `--arti-exit-select-parallelism 3`, and
`--extra-arti-exit-select-parallelism 1`. It passed quality.

Page-only load medians:

- `check.torproject.org`: width `3` `2671.301ms`, width `1` `1577.791ms`,
  local C Tor `1344.683ms`.
- `www.torproject.org`: width `3` `5552.903ms`, width `1` `5885.118ms`,
  local C Tor `4839.428ms`.
- `www.torproject.org/download/`: width `3` `6212.785ms`, width `1`
  `3391.149ms`, local C Tor `5959.905ms`.

Paired width `3` minus width `1` load deltas:

- `check.torproject.org`: `+965.497ms`, width `3` won `1/5`.
- `www.torproject.org`: `+369.719ms`, width `3` won `2/5`.
- `www.torproject.org/download/`: `+3146.486ms`, width `3` won `1/5`.

Meaning: the stronger same-window A/B rejected width `3` as the default. Width
`1` is the better current default, and wider values should stay lab-only until
they win broader proof. Width `1` still does not beat local C Tor on
`check.torproject.org` or the homepage, but it did beat local C Tor on the
download page in this run.

`results/browser-compare-20260607T112445/browser-compare.json` ran the fuller
same-window shape with bundled C Tor included. The result failed quality only
because bundled C Tor hit a homepage `netTimeout` on run 1 and missed a
screenshot. Arti width `3`, Arti width `1`, and local C Tor all succeeded. Use
it as rejected diagnostic data only. It still agrees with the accepted A/B:
width `3` was slower than width `1` on all three target medians.

Older one-target evidence now contradicted by the stronger A/B:

- `results/browser-compare-20260607T111656/browser-compare.json` passed quality
  on the download page with 3 runs. Width `3` loaded in `3173.693ms`, width `1`
  loaded in `8709.136ms`, bundled C Tor loaded in `5105.234ms`, and local C Tor
  loaded in `4253.623ms`. Width `3` beat width `1` in `3/3` paired runs.
- `results/browser-compare-20260607T105812/browser-compare.json` and
  `results/browser-compare-20260607T110542/browser-compare.json` were nearby
  separate-run A/B data for width `1` and width `3`. They are weaker than the
  same-window runs.
- `results/browser-compare-20260607T110049/browser-compare.json` had Arti
  success `3/3` with width `3`, but failed quality because bundled C Tor missed
  one screenshot. Use it only as rejected diagnostic data.

The analyzer now prints an `Arti Exit-Select A/B` table when a result contains
multiple Arti profiles with different exit-select widths.

Rejected harness attempt:
`results/browser-compare-20260607T111406/browser-compare.json` failed before
browser benchmarks because the extra Arti process used the default global
`port_info.json` path and exited. The runner now sets
`storage.port_info_file` inside each Arti profile state directory.

## Latest Default-Width Browser Proof

`results/browser-compare-20260607T115225/browser-compare.json` tested the
current rebuilt Arti binary with no exit-select env override. It used warm
cache, compact output, interleaved schedule, `--skip-bundled-tor`, 5 runs,
3 targets, and `--arti-log-level info`. It passed quality.

The JSON records:

- `source_tweaks.arti_exit_select_parallelism = 1`.
- top-level `arti_exit_select_parallelism_override = null`.
- the Arti profile has no per-profile override.

Page-only load medians:

- `check.torproject.org`: Arti `1621.183ms`, local C Tor `1514.829ms`.
- `www.torproject.org`: Arti `8199.249ms`, local C Tor `5183.005ms`.
- `www.torproject.org/download/`: Arti `5812.759ms`, local C Tor `3813.777ms`.

Paired Arti-minus-local-C-Tor page-load deltas:

- `check.torproject.org`: `+106.354ms`, Arti won `2/5`.
- `www.torproject.org`: `+2906.736ms`, Arti won `1/5`.
- `www.torproject.org/download/`: `+2192.737ms`, Arti won `1/5`.

Boot+load is still helped by Arti's fast warm boot:

- `check.torproject.org`: Arti `2015.183ms`, local C Tor `4113.829ms`.
- `www.torproject.org`: Arti `8593.249ms`, local C Tor `7782.005ms`.
- `www.torproject.org/download/`: Arti `6206.759ms`, local C Tor
  `6412.777ms`.

The analyzer now prints a per-run navigation phase table. In this result, Arti
is close on `check.torproject.org`, but the homepage and download page losses
are mainly later page/resource work:

- homepage median phase delta: response start `+300.006ms`, response-to-DOM
  `-400.008ms`, DOM-to-load `+1016.687ms`.
- download median phase delta: response start `-216.671ms`, response-to-DOM
  `+333.340ms`, DOM-to-load `+850.017ms`.

Meaning: current default-width Arti is quality-passing and has fast warm boot,
but it is not a page-only speed win. The next safe bottleneck is resource/page
phase behavior, especially DOM-to-load on larger pages, not wider exit
selection.

The analyzer now also prints a load-tail resource table. In the same default
proof, the biggest Arti tail gaps versus local C Tor were real page assets, not
browser startup:

- download `tor-browser-mobile-window/png/TBA10.0.png`: response end
  `+2416.715ms`, tail after DOM `+1400.028ms`.
- homepage `circle-pattern.svg`: response end `+3100.062ms`, tail after DOM
  `+1250.025ms`.
- homepage `browse-freely.svg`: response end `+3000.060ms`, tail after DOM
  `+1133.356ms`.
- homepage `encryption.svg`: response end `+2900.058ms`, tail after DOM
  `+950.019ms`.

## Homepage Resource Shape Proof

`results/browser-compare-20260607T121622/browser-compare.json` ran a 3-run
homepage check after adding `nextHopProtocol` collection and a resource
connection-shape analyzer table. It used warm cache, compact output,
interleaved schedule, `--skip-bundled-tor`, and `--arti-log-level info`. It
passed quality. Treat it as a focused diagnostic, not final speed proof.

Page timing:

- Arti homepage median load `5686.759ms`.
- local C Tor homepage median load `3928.422ms`.
- paired Arti-minus-local-C-Tor load delta `+2101.809ms`, Arti wins `1/3`.
- Arti response start was `116.669ms` earlier than local C Tor.
- Arti response-to-DOM was `633.346ms` slower.
- Arti DOM-to-load was `1366.694ms` slower.

Resource connection shape:

- both profiles had `105` sampled resources across the three runs.
- both profiles used one resource origin: `https://www.torproject.org`.
- Arti protocols: `http/1.1:95`, `unknown:10`.
- local C Tor protocols: `http/1.1:89`, `unknown:16`.
- fetch-start bucket counts were close: Arti `9`, local C Tor `10`.
- Arti request-start span was longer: `4700.094ms` versus local C Tor
  `2983.393ms`.
- Arti median fetch-to-request was `733.348ms` versus local C Tor `650.013ms`.
- Arti median request wait was `383.341ms` versus local C Tor `300.006ms`.

Largest load-tail gaps in this run:

- `circle-pattern.svg`: response end `+1866.704ms`, tail after DOM
  `+1466.696ms`.
- `encryption.svg`: response end `+1733.368ms`, tail after DOM `+1400.028ms`.
- `browse-freely.svg`: response end `+1716.701ms`, tail after DOM
  `+1383.361ms`.

Meaning: the browser is not choosing a different origin or protocol shape for
Arti. The remaining homepage loss is same-origin resource/stream timing after
first response. The next useful diagnostic is to combine this shape table with
byte-tap or debug stream evidence, not to add more preemptive circuits.

## Homepage Byte-Tap Resource Proof

`results/browser-compare-20260607T122018/browser-compare.json` ran a 3-run
homepage proof with the neutral byte tap in front of Arti and local C Tor. It
used warm cache, compact output, interleaved schedule, `--skip-bundled-tor`,
`--arti-log-level info`, and `--byte-tap`. It passed quality, but it is
diagnostic only because the tap is a local measurement hop.

Page timing under the tap:

- Arti homepage median load `4569.460ms`.
- local C Tor homepage median load `5584.255ms`.
- paired Arti-minus-local-C-Tor load delta `-1014.795ms`, Arti wins `3/3`.
- Arti boot+load delta `-3332.795ms`.

Resource shape stayed matched:

- Arti sampled `107` resources; local C Tor sampled `105`.
- both profiles used one resource origin: `https://www.torproject.org`.
- Arti protocols: `http/1.1:92`, `unknown:15`.
- local C Tor protocols: `http/1.1:91`, `unknown:14`.

Byte-tap facts:

- Arti: `27` total tap connections, `25` data connections.
- local C Tor: `32` total tap connections, `29` data connections.
- Arti median first stream data `385.090ms`; local C Tor `453.879ms`.
- Arti max first stream data `3965.918ms`; local C Tor `3265.557ms`.
- Arti median stream bytes `157742`; local C Tor `138490`.
- Arti median max data gap `309.259ms`; local C Tor `456.498ms`.
- nearest stream data arrived before browser response in every run for both
  profiles.

Per-run tap spans:

- Arti run 1: load `7405.356ms`, `10` data connections, stream-data span
  `7193.961ms`, max data gap `1388.987ms`.
- Arti run 2: load `4569.460ms`, `8` data connections, stream-data span
  `4662.501ms`, max data gap `823.896ms`.
- Arti run 3: load `3514.238ms`, `7` data connections, stream-data span
  `3133.698ms`, max data gap `597.181ms`.
- local C Tor run 1: load `11664.641ms`, `10` data connections, stream-data span
  `12689.837ms`, max data gap `3620.188ms`.
- local C Tor run 2: load `5584.255ms`, `10` data connections, stream-data span
  `5706.408ms`, max data gap `1422.085ms`.
- local C Tor run 3: load `4030.807ms`, `9` data connections, stream-data span
  `4288.871ms`, max data gap `415.651ms`.

Meaning: under this neutral tap, the gap does not look like slow SOCKS setup or
late first bytes. The normal no-tap 3-run proof still had Arti slower, so this
does not prove Arti is faster. It says the next source diagnostic should inspect
post-first-byte stream/resource pacing in normal no-tap runs.

## No-Tap Relay Receive Run Proof

`results/browser-compare-20260607T123004/browser-compare.json` ran a focused
2-run homepage diagnostic with no byte tap. It used warm cache, compact output,
interleaved schedule, `--skip-bundled-tor`, `--arti-log-level debug`, and a
large proxy log tail. It passed quality, but it is debug evidence only.

Page timing:

- Arti homepage median load `6373.530ms`.
- local C Tor homepage median load `4867.553ms`.
- paired Arti-minus-local-C-Tor load delta `+1505.977ms`, Arti wins `0/2`.
- Arti response start was `175.004ms` earlier.
- Arti DOM-to-load was `1600.032ms` slower.
- Arti boot+load delta was `-729.023ms`.

Resource shape:

- Arti sampled `71` resources; local C Tor sampled `70`.
- both profiles used one origin.
- Arti protocols: `http/1.1:68`, `unknown:3`.
- local C Tor protocols: `http/1.1:58`, `unknown:12`.
- Arti median fetch-to-request `1000.020ms`; local C Tor `800.016ms`.
- Arti median request wait `383.341ms`; local C Tor `325.006ms`.

Internal Arti relay receive per run:

- run 1: load `6247.533ms`, `717` DATA cells, `316554` DATA bytes,
  `4` circuits, `16` streams, receive span `6000ms`, max receive gap `1000ms`,
  max queued bytes `25658`.
- run 2: load `6499.527ms`, `856` DATA cells, `382346` DATA bytes,
  `6` circuits, `17` streams, receive span `11000ms`, max receive gap `4000ms`,
  max queued bytes `21624`.

Meaning: this no-tap debug proof confirms the remaining loss is after first
response and visible in internal stream/resource work. The run grouping is still
coarse because relay logs have second-level timestamps and streams can cross
browser-run windows. The next source diagnostic should add better stream/request
correlation or higher-resolution internal timing before trying another speed
patch.

## High-Resolution No-Tap Relay Receive Proof

`results/browser-compare-20260607T124126/browser-compare.json` ran the same
focused homepage diagnostic after rebuilding Arti with millisecond
`event_epoch_ms` fields on relay receive logs. It used warm cache, compact
output, interleaved schedule, `--skip-bundled-tor`, `--arti-log-level debug`,
and a large proxy log tail. It passed quality, but it is debug evidence only.

Page timing:

- Arti homepage median load `14194.317ms`.
- local C Tor homepage median load `3867.974ms`.
- paired Arti-minus-local-C-Tor load delta `+10326.343ms`, Arti wins `0/2`.
- Arti response start was `2758.389ms` slower.
- Arti response-to-DOM was `1600.032ms` slower.
- Arti DOM-to-load was `5966.786ms` slower.

Resource shape:

- both profiles used one origin and mostly HTTP/1.1.
- Arti protocols: `http/1.1:61`, `unknown:11`.
- local C Tor protocols: `http/1.1:60`, `unknown:10`.
- Arti request-start span `19950.399ms`; local C Tor `3800.076ms`.
- Arti median fetch-to-request `1033.354ms`; local C Tor `575.012ms`.
- Arti median request wait `408.341ms`; local C Tor `241.672ms`.

Internal Arti relay receive per run:

- run 1: load `5165.883ms`, `1850` DATA cells, `882686` DATA bytes,
  `4` circuits, `9` streams, receive span `3447ms`, max receive gap `321ms`,
  max queued bytes `15936`.
- run 2: load `23222.751ms`, `3463` DATA cells, `1658038` DATA bytes,
  `8` circuits, `22` streams, receive span `26563ms`, max receive gap
  `3730ms`, max queued bytes `34752`.

Top slow internal streams:

- `Circ 0.4 (Tunnel 15)` stream `11302`: `847` DATA cells, `411460` bytes,
  span `15197ms`, max gap `2527ms`.
- `Circ 0.4 (Tunnel 15)` stream `11301`: `448` DATA cells, `216138` bytes,
  span `10940ms`, max gap `3732ms`.

Meaning: the earlier `4000ms` receive-gap signal was not just second-level log
rounding. Arti can have real multi-second internal relay receive gaps during
slow homepage loads. The per-run grouping is still not enough by itself because
some streams cross browser-run windows. The follow-up diagnostic below adds the
SOCKS timing id to Arti stream-id join.

## SOCKS To Relay Receive Join Proof

`results/browser-compare-20260607T125446/browser-compare.json` ran a focused
2-run homepage diagnostic after adding a debug-only SOCKS stream-link log. It
used warm cache, compact output, interleaved schedule, `--skip-bundled-tor`,
`--arti-log-level debug`, and a large proxy log tail. It passed quality, but it
is debug evidence only.

Page timing:

- Arti homepage median load `4690.247ms`.
- local C Tor homepage median load `10661.930ms`.
- paired Arti-minus-local-C-Tor load delta `-5971.682ms`, Arti wins `2/2`.
- This is not a normal speed claim because debug logging was enabled and local
  C Tor had a slow second run.

New join evidence:

- The analyzer now prints `Torfast SOCKS To Relay Receive Join`.
- It maps SOCKS `timing_id` to circuit, stream id, SOCKS relay bytes, relay
  receive DATA cells/bytes, receive span, max receive gap, and max queued bytes.
- The analyzer also prints `Torfast SOCKS To Relay Per-Run Summary`. In this
  proof, run 1 and run 2 each had `14` joined streams. Run 1 had `2687` DATA
  cells, `1277869` DATA bytes, and a `616ms` max joined receive gap. Run 2 had
  `2633` DATA cells, `1254247` DATA bytes, and a `684ms` max joined receive gap.
- The analyzer also prints `Browser Resource To SOCKS Relay Join (nearest)`.
  This maps browser resource URLs to the nearest joined SOCKS stream by browser
  connection timing. It is not a browser-provided stream id, but the top real
  rows matched within about `24ms` or less in this proof.
- The slowest resource row was
  `www.torproject.org/static/images/favicon/favicon.ico`: duration `3833.410ms`,
  wait `300.006ms`, receive `50.001ms`, matched to timing id `8`,
  `Circ 0.2 (Tunnel 6)`, stream `672`, with `11471` joined DATA bytes and
  `285ms` max receive gap.
- The largest joined Arti receive gap in this run was `684ms`, on timing id
  `19`, `Circ 1.4 (Tunnel 11)`, stream `39418`.
- The largest joined stream by DATA cells was timing id `23`,
  `Circ 0.10 (Tunnel 16)`, stream `43977`: `721` DATA cells, `346978` DATA
  bytes, receive span `1695ms`, max receive gap `437ms`.
- The top relay receive stream overall matched the SOCKS join table, so the
  new link is usable for real stream-level bottleneck work.

Meaning: we can now inspect exact Arti stream ids for browser/SOCKS flows, place
joined streams inside browser run windows, and make a nearest-time browser URL to
stream guess. This run did not reproduce the very slow Arti tail from
`20260607T124126`; the next diagnostic should capture a slow Arti run with these
tables.

## Default-Width Homepage Debug Correlation

`results/browser-compare-20260607T120157/browser-compare.json` ran one focused
homepage diagnostic with current default width `1`, no exit-select override,
warm cache, compact output, `--skip-bundled-tor`, and `--arti-log-level debug`.
It passed quality, but it is debug evidence only.

Timing:

- Arti load `3987.776ms`, local C Tor load `2842.851ms`.
- Arti response start was `+216.671ms` behind local C Tor.
- Arti response-to-DOM was `+500.010ms` behind.
- Arti DOM-to-load was `+433.342ms` behind.

Resource tail:

- top Arti tail gap was `fontawesome/.../arrow-down.png`: response end
  `+1283.359ms`, tail after DOM `+566.678ms`.
- `circle-pattern.svg`: response end `+1266.692ms`, tail after DOM `+550.011ms`.
- `surveillance.svg` and `block-trackers.svg`: response end `+1166.690ms`,
  tail after DOM `+450.009ms`.

Arti log facts:

- `8` hostname SOCKS streams became ready with `0ms` connect and `0ms` SOCKS
  reply.
- median first Tor byte after SOCKS reply was `553.500ms`.
- relay receive had `536` delivered relay messages, `0` queue-full events, and
  `0` stream-gone events.
- stream scheduler had `26` DATA picks, `0` blocked hops, and `9` unique
  streams.
- circuit selection saw `4` exit open picks, mostly with only `1` open
  candidate.
- circuit assignments were concentrated: `4` assignments, `2` circuits, top
  circuit `Circ 0.0` used `3` times.
- relay receive was also concentrated: the top six DATA streams were all on
  `Circ 0.0`.

Meaning: the focused debug run points away from SOCKS setup, local receive
queue pressure, and simple scheduler send blocking. It points toward resource
traffic being concentrated on too few ready exit circuits during page load.
Because width `3` failed broader A/B, the next patch should not simply make
wide selection default. The safer next idea is a bounded, quality-preserving
way to make enough already-valid exit capacity available for resource bursts,
then prove it with the same 5-run, 3-target quality gate.

## Rejected Preemptive Count 3 Test

`results/browser-compare-20260607T120836/browser-compare.json` tested the new
runner-only lab flag `--arti-min-exit-circs-for-port 3` on the homepage. It used
warm cache, compact output, interleaved schedule, `--skip-bundled-tor`, 2 runs,
and `--arti-log-level info`. It passed quality, but was much slower.

The JSON records:

- top-level `arti_min_exit_circs_for_port_override = 3`.
- Arti profile `arti_min_exit_circs_for_port_override = 3`.
- `source_tweaks.arti_preemptive_min_exit_circs_for_port = 2`, so the source
  default stayed unchanged.

Timing:

- Arti homepage median load `13434.135ms`.
- local C Tor homepage median load `3642.484ms`.
- paired Arti-minus-local-C-Tor load delta `+9791.651ms`, Arti wins `0/2`.
- Arti DOM-to-load delta `+7833.490ms`.

Load-tail resource gaps were also much worse:

- `browse-freely.svg`: response end `+9783.529ms`, tail after DOM
  `+7825.157ms`.
- `circle-pattern.svg`: response end `+9375.188ms`, tail after DOM
  `+7416.815ms`.
- `encryption.svg`: response end `+8691.840ms`, tail after DOM `+6733.468ms`.

Meaning: raising the preemptive count through a lab flag preserves the source
default and passes this tiny quality gate, but it is not a speed win. Do not
make count `3` default. Do not run the bigger 5-run proof for this exact idea
unless there is a new reason.

In `results/browser-compare-20260607T090853/browser-compare.json`, local Arti
temporarily raised `min_exit_circs_for_port` from `2` to `3`, to match the
exit-spread width. This was rejected.

Why:

- quality failed.
- Arti had one failed `check.torproject.org` run with a neterror connection
  failure.
- Arti had one failed `www.torproject.org` run with a `120000ms` navigation
  timeout.
- screenshots were missing for both failed runs.

Meaning: more preemptive circuits may help some successful-run medians, but this
test did not preserve reliability. The patch was reverted. Current accepted
state keeps `min_exit_circs_for_port = 2`.

## Latest C Tor Circuit Check

In `results/circuit-check-20260607T042121/c-tor-circuits.json`, local C Tor
passed the control-port circuit probe:

- fetched `https://check.torproject.org/` through local C Tor SOCKS.
- checked 6 built 3-hop circuits.
- all checked circuits had a Guard first hop.
- all checked relays had `Fast`, `Running`, and `Valid`.
- last hops had the `Exit` flag.
- no checked path reused a relay.
- no checked path had a detected relay-family overlap.
- no checked path shared an IPv4 `/16` subnet.

## Post-Patch SOCKS Timeout Retry Proof

`results/browser-compare-20260607T131326/browser-compare.json` ran the normal
5-run, 3-target same-window shape with warm cache, compact output, interleaved
schedule, `--skip-bundled-tor`, and `--arti-log-level info`. It failed quality:

- Arti `https://www.torproject.org/` run 2 hit `about:neterror` with
  `connectionFailure`.
- The run lasted `61405.381ms`.
- The Arti proxy log showed `All tunnel attempts failed due to timeout`,
  `Request failed`, and `Connection exited error=error: tor operation timed out`
  in the same measured window.
- Because the screenshot proof was missing, this result is not a speed proof.

Source response: `upstream/arti/crates/arti/src/proxy/socks.rs` now retries
SOCKS CONNECT once when `connect_with_prefs` fails with
`ErrorKind::TorNetworkTimeout`. It does not retry invalid targets, bad SOCKS
commands, remote exit failures, or non-timeout errors. Debug logs now include
`torfast socks timing connect retry`, `connect retry succeeded`, and the analyzer
parses those retry events.

Focused validation:

- `results/browser-compare-20260607T132211/browser-compare.json` ran 5 normal
  homepage runs after the retry patch.
- It passed quality: Arti `5/5`, local C Tor `5/5`.
- Arti was slower in that focused sample: Arti homepage median load
  `6400.977ms`, local C Tor `5432.889ms`.

Full post-patch validation:

- `results/browser-compare-20260607T132404/browser-compare.json` ran the full
  normal 5-run, 3-target same-window shape after the retry patch.
- It passed quality for all targets and both profiles.
- Arti median page-only load:
  - `check.torproject.org`: `1934.205ms` versus local C Tor `2707.171ms`.
  - Tor homepage: `5734.770ms` versus local C Tor `5913.474ms`.
  - Tor download page: `5992.235ms` versus local C Tor `7901.429ms`.
- Paired Arti-minus-local-C-Tor median load deltas:
  - `check.torproject.org`: `-445.178ms`, Arti wins `4/5`.
  - Tor homepage: `-129.138ms`, Arti wins `3/5`.
  - Tor download page: `-2119.008ms`, Arti wins `4/5`.
- Arti boot was `0.376s`; local C Tor boot was `3.310s`, so boot+load also
  favored Arti on all three targets.

Repeat full post-patch validation:

- `results/browser-compare-20260607T133349/browser-compare.json` reran the same
  normal 5-run, 3-target same-window shape.
- It passed quality for all targets and both profiles.
- Arti median page-only load:
  - `check.torproject.org`: `2802.599ms` versus local C Tor `2052.168ms`.
  - Tor homepage: `4423.439ms` versus local C Tor `6335.317ms`.
  - Tor download page: `6530.057ms` versus local C Tor `8458.377ms`.
- Paired Arti-minus-local-C-Tor median load deltas:
  - `check.torproject.org`: `+93.280ms`, Arti wins `2/5`.
  - Tor homepage: `-195.951ms`, Arti wins `3/5`.
  - Tor download page: `-559.974ms`, Arti wins `3/5`.
- Arti boot was `0.366s`; local C Tor boot was `2.399s`, so boot+load favored
  Arti on all three targets.

Meaning: the timeout retry fixed the observed hard quality failure in the next
two full same-window gates. The speed win is now more stable on the larger Tor
Project pages, but `check.torproject.org` is still mixed by page-only load.
This is good evidence, not final proof of "faster Tor with exact quality."

## Navigation-To-SOCKS Diagnostic

`results/browser-compare-20260607T135113/browser-compare.json` ran a debug
3-run, 3-target same-window diagnostic after the retry patch. It passed quality
for Arti and local C Tor, but it is not a fair release-speed proof because Arti
ran with debug logging.

The new analyzer table `Browser Navigation To SOCKS Join (nearest)` matched
main document navigation timing to exact Arti SOCKS streams with high
confidence:

- `check.torproject.org`: Arti main navigation connects were `0ms`, `0ms`, and
  `479ms`; first Tor byte to browser response was about `258ms`, `314ms`, and
  `315ms`.
- Tor homepage run 2 had the clear bad case: main navigation `connect_ms` was
  `49891ms`, browser response start was `50417.675ms`, and first Tor byte to
  browser response was only `288.348ms`.
- Tor download main navigation connects were `0ms`, `440ms`, and `457ms`; first
  Tor byte to browser response stayed under `384ms`.

Meaning: the next safe bottleneck is slow successful CONNECT/circuit readiness,
not browser response parsing. The obvious but risky answer is exit-circuit
racing; do not make that default without a path-quality and relay-bias review.

## Slow CONNECT Soft-Timeout Lab

`results/browser-compare-20260607T140722/browser-compare.json` ran a focused
5-run homepage lab with debug logging and
`--arti-socks-connect-soft-timeout-ms 5000`. It passed quality for Arti and
local C Tor.

Result:

- Arti homepage median load was `6820.331ms`; local C Tor was `4203.084ms`.
- Arti median response start was faster: `850.017ms` versus local C Tor
  `983.353ms`.
- Paired Arti-minus-local-C-Tor median load delta was `+2617.247ms`; Arti won
  `2/5` loads.
- The analyzer found `0` SOCKS CONNECT soft timeouts. Main navigation CONNECT
  times were all `0ms`; the only connects above `1s` were `.onion` streams, and
  the lab soft timeout is intentionally not applied to `.onion`.

Meaning: the default-off soft-timeout code is wired and did not hurt quality in
this sample, but this run did not exercise the fallback. It is not speed proof.
The next proof needs a slow non-onion successful CONNECT where the analyzer
shows `soft timeouts` above `0`.

`results/browser-compare-20260607T141652/browser-compare.json` then ran a
same-window A/B with baseline Arti and one extra Arti profile using
`--extra-arti-socks-connect-soft-timeout-ms 1500`. It passed quality for all
three measured profiles: baseline Arti, soft-timeout Arti, and local C Tor.

Result:

- Baseline Arti median load was `4990.866ms`; max load was `7357.102ms`.
- Soft-timeout Arti median load was `3832.178ms`; max load was `81790.668ms`.
- Local C Tor median load was `4154.073ms`; max load was `6906.576ms`.
- The analyzer found `0` soft timeouts for both Arti profiles.
- The soft-timeout profile's bad run had main-navigation `connect_ms=0`, but
  page load `81790.668ms`.
- The joined relay rows showed a `60430ms` max receive gap in that bad run, and
  a hostname SOCKS stream with `relay_ms=82252`.
- The new joined-stream gap detail table showed the exact bad edge: timing id
  `20`, hostname stream `54447` on `Circ 0.11 (Tunnel 17)`, had a `60430ms`
  `DATA` to `DATA` gap. The previous queued-after value was `3053` bytes, and
  the next event had `queued_before=0` and `queued_after=39`, so this does not
  look like a local stream output queue that stayed full.

Meaning: the 1500ms A/B is not speed proof. The median looked good, but the
tail was much worse than both baseline Arti and local C Tor, and the soft
timeout never fired. The next target is circuit/stream receive stall behavior,
not CONNECT setup.

## Stream Receiver Gap Context Proof

After the `20260607T141652` bad tail, local Arti source now has debug-only
stream receiver logs in `stream/raw.rs`. They record stream id, relay command,
data bytes, queued bytes, receive-window value, and SENDME sends.
`tools/analyze_browser_compare.py` now prints `Torfast Stream Receiver Timings`
and `Torfast Stream Receiver Gap Context`.

`results/browser-compare-20260607T144256/browser-compare.json` ran one
warm-cache homepage proof with debug logging and bundled C Tor skipped. It
passed quality for Arti and local C Tor.

Result:

- Arti homepage load was `5527.895ms`; local C Tor was `6896.895ms`.
- Arti boot+load was `5902.895ms`; local C Tor was `9461.895ms`.
- The analyzer saw `2827` stream receiver read events and `52` SENDMEs.
- The max joined stream relay gap was only `665ms`, so this run did not
  reproduce the `60430ms` tail from `20260607T141652`.
- For the shown joined gaps, receiver reads continued inside the gap and
  `sendmes in gap` was `0`.

Meaning: the stream receiver diagnostic is wired and parseable. It is not speed
proof and it did not reproduce the long tail. The next slow-tail run should use
this gap-context table first; if reads keep moving with no SENDME due, the next
source probe should be circuit/congestion state.

## Pending Exit Circuit Wait Proof

`results/browser-compare-20260607T144921/browser-compare.json` ran a 5-run
warm-cache homepage proof with debug logging and bundled C Tor skipped. It
passed quality for Arti and local C Tor.

Result:

- Arti median homepage load was `4077.242ms`; local C Tor was `4680.109ms`.
- Arti run 5 had a bad tail: load `45865.979ms`, elapsed `47552.928ms`.
- The main hostname SOCKS stream was timing id `42`.
- Timing id `42` waited `43414ms` before SOCKS reply and first Tor byte arrived
  at `43613ms`.
- The circuit-selection log showed one pending exit circuit at `06:50:53`, then
  a new build at `06:51:36`; that new circuit became `Circ 0.16 (Tunnel 31)`.
- Joined page streams had max receive gap only `486ms`. The `39022ms` relay
  receive gap in the run was between unrelated circuits/streams.

Meaning: this bad tail was a pending exit-circuit wait, not a local stream
receiver queue, SENDME, or browser response parsing problem.

After that result, local Arti source added
`TORFAST_EXIT_PENDING_HEDGE_MS`. It is default-off, bounded from `500ms` through
`60000ms`, only applies to normal exit usage, and can launch at most one extra
pending exit circuit while keeping the pending cap at `2`. The wait path now
arms a timer, so the first slow waiter can re-run circuit selection after the
threshold instead of needing a later request to trigger the hedge.

`results/browser-compare-20260607T150149/browser-compare.json` then ran a
same-window baseline Arti versus `--extra-arti-exit-pending-hedge-ms 1500` A/B.
It failed quality because the hedge profile had one Firefox `netTimeout` on run
5.

Result:

- Baseline Arti passed 5/5, median load `4603.341ms`, max load `9228.660ms`.
- Pending-hedge Arti passed 4/5, median successful load `4412.815ms`, but run 5
  timed out after `61483.412ms`.
- Local C Tor passed 5/5, median load `5182.066ms`.
- The analyzer saw `0` pending hedge events, so the hedge did not fire.
- The failed hedge-profile run opened hostname streams immediately
  (`connect_ms=0`) and then stalled in the relay phase. Timing id `37` got no
  Tor bytes; timing ids `36` and `38` got some Tor bytes, then stopped until
  timeout.

Meaning: the pending hedge code is wired but not proven. The failed A/B does
not show the hedge helped or hurt, because the hedge count was `0`. The next
proof at that point needed `pending hedges > 0` and a passing quality result.

`results/browser-compare-20260607T151858/browser-compare.json` reran the hedge
A/B after adding the timer path, using a `500ms` hedge threshold, warm cache,
3 runs, and debug logging. It passed quality.

Result:

- Baseline Arti median load was `4236.640ms`; local C Tor was `5105.223ms`.
- Pending-hedge Arti median load was `4533.537ms`.
- Pending-hedge Arti passed 3/3, but was slower than baseline Arti.
- Circuit-selection counts still showed `0` pending hedge launches.

`results/browser-compare-20260607T152131/browser-compare.json` then tried a
smaller no-warm-cache 2-run proof to make pending exits more likely. It also
passed quality.

Result:

- Baseline Arti median load was `3859.752ms`; local C Tor was `6212.244ms`.
- Pending-hedge Arti median load was `8365.920ms`.
- Pending-hedge Arti passed 2/2, but was slower than baseline Arti and local C
  Tor by page load.
- Circuit-selection counts still showed `0` pending hedge launches.

Meaning at that point: the timer-capable hedge path was in the binary and passed
static checks, but live browser samples had still not naturally exercised it.
The useful next proof then needed a captured `pending_hedge` launch, not only
`pending` waits.

`results/browser-compare-20260607T153223/browser-compare.json` then ran a
focused warm-cache 3-run homepage proof with debug logs and no hedge profile.
It passed quality.

Result:

- Arti median load was `3113.562ms`; local C Tor was `4516.283ms`.
- Arti boot+load was `3487.562ms`; local C Tor was `7189.283ms`.
- Arti was `31.1%` faster by page-only median load and `51.5%` faster by
  boot+load in this sample.
- The analyzer counted `0` generic stream-reactor congestion blocks and `0`
  stream-scheduler hop blocks.
- Relay receive logging was active (`7905` relay receive lines), and the worst
  Arti run still had a `5747.178ms` page load with relay/resource tails.
- The new circuit-shape table showed one dominant hostname circuit per run. In
  the slow run, `Circ 1.4 (Tunnel 13)` carried `9` streams, `1253594` data
  bytes, and had a max receive span of `5196ms`.

Meaning: the new stream-reactor congestion diagnostic works and did not fire on
this proof. The current homepage tail is not caused by ready stream data being
stopped at the generic `can_send()` gate. This led to testing load-aware
circuit choice among already eligible open circuits, not blind wider spread and
not extra circuit building.

`results/browser-compare-20260607T154907/browser-compare.json` then ran a
same-window load-aware open-circuit selection A/B. It used warm cache,
interleaved schedule, `--skip-bundled-tor`, 3 homepage runs, debug logs, and
`--extra-arti-exit-select-load-aware`. It passed quality.

Result:

- Baseline Arti median load was `6207.200ms`; local C Tor was `3455.741ms`.
- Load-aware Arti median load was `3449.575ms`.
- Load-aware Arti was `44.4%` faster than baseline Arti by page-only median
  load in this sample.
- Load-aware Arti was `0.2%` faster than local C Tor by page-only median load
  and `36.4%` faster by boot+load.
- The analyzer counted `26` load-aware exit picks for the load-aware profile
  and `0` for baseline Arti.
- Baseline Arti's max selected assigned-stream count was `8`; load-aware
  Arti's max was `5`.
- Stream-reactor congestion blocks stayed at `0`.

Meaning: this is the first promising proof for changing open-circuit selection.
It keeps path rules and circuit eligibility the same and only changes which
already open eligible exit circuit gets the next stream. It led to the wider
gate below.

`results/browser-compare-20260607T155934/browser-compare.json` then ran that
broader same-window load-aware gate. It used warm cache, interleaved schedule,
`--skip-bundled-tor`, 5 runs, 3 targets, debug logs, and
`--extra-arti-exit-select-load-aware`. It passed quality.

Result:

- `check.torproject.org`: baseline Arti median load was `1887.842ms`;
  load-aware Arti was `1780.184ms`; local C Tor was `1478.114ms`.
- `www.torproject.org`: baseline Arti median load was `9061.474ms`;
  load-aware Arti was `4232.771ms`; local C Tor was `8739.569ms`.
- `www.torproject.org/download/`: baseline Arti median load was `8937.480ms`;
  load-aware Arti was `6000.187ms`; local C Tor was `15770.862ms`.
- Load-aware Arti had `67` load-aware exit picks; baseline Arti had `0`.
- The new `Arti Profile A/B` table shows load-aware median-load deltas versus
  baseline Arti of `-107.658ms`, `-4828.703ms`, and `-2937.293ms`.
- Load-aware Arti beat baseline Arti on paired page-load runs `2/5`, `4/5`,
  and `3/5` for the three targets.
- Stream-reactor congestion blocks stayed at `0`.
- The bad part: load-aware Arti's download-page max load was `65953.543ms`.
  Baseline Arti's download-page max load was `11525.708ms`, so the load-aware
  tail was `54427.835ms` worse.

Meaning: load-aware open-circuit selection is a stronger speed direction than
blind width `3`, because it keeps circuit eligibility the same and improved
median load across the wider gate. It is still not safe to make default because
the download-page tail regressed badly once. The next source work should reduce
that tail before promotion.

Follow-up inspection of that bad download tail found the problem was not a
load-aware choice among open circuits. For timing id `35`, Arti had no eligible
open circuit, waited about `60027ms`, returned `TorNetworkTimeout`, retried, and
then connected in `746ms`. That points at isolated exit-circuit readiness and
CONNECT retry timing, not at the load-aware open-circuit picker itself.

`results/browser-compare-20260607T161639/browser-compare.json` then ran a
focused download-page test with load-aware Arti as the baseline and an extra
same-window load-aware plus `--extra-arti-socks-connect-soft-timeout-ms 5000`
profile. It used warm cache, interleaved schedule, `--skip-bundled-tor`, 5
runs, debug logs, and a large proxy log tail. It passed quality.

Result:

- Load-aware baseline Arti median load was `13570.841ms`; local C Tor was
  `7209.919ms`.
- Load-aware plus soft-timeout Arti median load was `5335.235ms`.
- The soft-timeout profile beat load-aware baseline Arti on paired page-load
  runs `5/5`.
- The `Arti Profile A/B` table shows a paired median load delta of
  `-6604.829ms`, a summary median load delta of `-8235.606ms`, and a max-load
  delta of `-11563.130ms` versus load-aware baseline Arti.
- Versus local C Tor, the soft-timeout profile was `26.0%` faster by page-only
  median load and `40.9%` faster by boot+load.
- The analyzer found `0` SOCKS CONNECT soft timeouts in this run. Baseline
  max CONNECT was `17893ms`; the soft-timeout profile max CONNECT was
  `4355ms`.

Meaning: the combined load-aware plus soft-timeout profile is promising and did
not hurt quality in this window. But because the soft-timeout counter stayed at
`0`, this run does not prove the `5000ms` timeout caught the earlier 60s
CONNECT retry shape. The next proof must either reproduce a slow CONNECT with
the soft timeout firing, or add a safer early-retry gate that can be shown to
fire on the bad shape.

`results/browser-compare-20260607T162821/browser-compare.json` then ran a
lower-threshold follow-up with load-aware Arti as the baseline and an extra
same-window load-aware plus `--extra-arti-socks-connect-soft-timeout-ms 1000`
profile. It used the same download page, warm cache, interleaved schedule,
`--skip-bundled-tor`, 5 runs, debug logs, and a large proxy log tail. It passed
quality.

Result:

- Load-aware baseline Arti median load was `5440.053ms`; local C Tor was
  `4755.504ms`.
- Load-aware plus `1000ms` soft-timeout Arti median load was `7301.248ms`.
- The `1000ms` profile beat load-aware baseline Arti on paired page-load runs
  `2/5`.
- The `Arti Profile A/B` table shows a paired median load delta of
  `+1050.288ms` and a summary median load delta of `+1861.195ms` versus
  load-aware baseline Arti. Its max-load tail was slightly better:
  `7473.467ms` versus baseline `7886.265ms`.
- The analyzer found `0` SOCKS CONNECT soft timeouts. In the `1000ms` profile,
  hostname CONNECT max was only `928ms`, while `.onion` CONNECT max was
  `6231ms`. The lab timeout correctly skips `.onion`.

Meaning: `1000ms` is not a speed direction from this sample. It did not fire
because the slow waits were onion-side requests, not normal hostname CONNECT
waits. The new retry table still helps: it makes the earlier bad timing id `35`
directly visible as one `TorNetworkTimeout` retry at `60027ms`, retry success
in `746ms`, and final connect at `60773ms`.

After that, local Arti source extended `TORFAST_EXIT_PENDING_HEDGE_MS` to the
initial build wait path too. The same default-off, exit-only, bounded env var can
now make the first build waiter re-check circuit selection after the threshold.

`results/browser-compare-20260607T164207/browser-compare.json` tested that source
with load-aware baseline Arti and an extra load-aware plus
`--extra-arti-exit-pending-hedge-ms 1500` profile on the download page. It used
warm cache, interleaved schedule, `--skip-bundled-tor`, 5 runs, debug logs, and a
large proxy log tail. It passed quality.

Result:

- Load-aware baseline Arti median load was `5928.687ms`; local C Tor was
  `4481.306ms`.
- Load-aware plus `1500ms` pending-hedge Arti median load was `7529.626ms`.
- The `1500ms` profile beat load-aware baseline Arti on paired page-load runs
  `2/5`.
- The `Arti Profile A/B` table shows a paired median load delta of
  `+1341.521ms` and a summary median load delta of `+1600.939ms` versus
  load-aware baseline Arti. Its max-load tail was also worse: `9712.473ms`
  versus baseline `8330.138ms`.
- Direct resource type A/B was worse for every sampled type: CSS `+733.348ms`,
  images `+708.348ms`, scripts `+516.677ms`, links `+466.676ms`, and other/font
  resources `+383.341ms` by median duration versus load-aware baseline Arti.
- Exact top-resource A/B rows show the biggest duration losses were the mobile
  browser image `TBA10.0.png` at `+1066.688ms`, `linkedin.png` at
  `+1050.021ms`, and `mastodon.png` at `+950.019ms`.
- Load-tail A/B rows show late DOM-tail losses too: `SourceSansPro-Bold.ttf`
  tail after DOM `+883.351ms`, `stay-safe.svg` `+850.017ms`, and
  `get-connected.svg` `+816.683ms`.
- HTTP queue-shape A/B shows this `1500ms` loss was broad for `http/1.1`:
  queued `>=500ms` resources rose to `146/174` from `134/176`, median
  fetch-to-request worsened by `+366.674ms`, median request-wait by
  `+250.005ms`, and median receive by only `+50.001ms`.
- Circuit selection counted `1` pending hedge, `0` pending hedge timers, and
  `0` build hedge timers for the `1500ms` profile.
- Hostname CONNECT max was `974ms` in the `1500ms` profile. The slow `>=1s`
  CONNECT waits were `.onion` side requests.

Meaning: the older pending-hedge launch path has now fired once in a passing
quality run, but it did not help speed. The new initial-build hedge timer is
wired in source and static checks, but this run did not exercise it. Keep the
hedge lab-only. At this point, the next useful proof needed
`build hedge timers > 0`, passing quality, and a better tail.

`results/browser-compare-20260607T165147/browser-compare.json` then tried to
exercise the build hedge timer with a no-warm-cache `500ms` hedge profile. It
used load-aware baseline Arti, an extra load-aware plus
`--extra-arti-exit-pending-hedge-ms 500` profile, local C Tor, interleaved
schedule, `--skip-bundled-tor`, 3 runs, debug logs, and a large proxy log tail.
It passed quality.

Result:

- Load-aware baseline Arti median load was `5236.727ms`; local C Tor was
  `4603.830ms`.
- Load-aware plus `500ms` pending/build-hedge Arti median load was `5783.041ms`.
- The `500ms` profile beat load-aware baseline Arti on paired page-load runs
  `1/3`.
- The `Arti Profile A/B` table shows a paired median load delta of
  `+699.667ms` and a summary median load delta of `+546.314ms` versus
  load-aware baseline Arti.
- The same direct Arti A/B table now shows phase deltas. The `500ms` profile
  lost mostly between response and DOM: response start `+116.669ms`,
  response-to-DOM `+583.345ms`, and DOM-to-load `+116.669ms` versus baseline.
- Direct resource type A/B shows the `500ms` profile's median image duration got
  worse by `+291.672ms`, links by `+91.668ms`, scripts by `+33.334ms`, and
  other/font resources by `+16.667ms`; CSS duration was `-50.001ms`, but CSS
  wait was still worse by `+83.335ms`.
- Exact top-resource A/B rows show the biggest `500ms` duration losses were
  `get-connected.svg` at `+733.348ms`, `fa-regular-400.woff2` at `+450.009ms`,
  `stay-safe.svg` at `+450.009ms`, and `modernizr.js` at `+316.673ms`.
- Load-tail A/B rows show the late DOM-tail losses were concentrated in exact
  resources: `get-connected.svg` `+750.015ms`, `github.png` `+733.348ms`,
  `apple.png` `+716.681ms`, `twitter.png` `+700.014ms`, and `TBA10.0.png`
  `+700.014ms`.
- The new HTTP-phase A/B table shows the same top `500ms` losses were all
  `http/1.1`. For `get-connected.svg`, the duration loss was mostly
  fetch-to-request `+483.343ms` and request-wait `+166.670ms`; receive was only
  `+33.334ms`. `stay-safe.svg` was similar: fetch-to-request `+383.341ms`,
  request-wait `-33.334ms`, receive `+0ms`. `modernizr.js` lost mostly in
  request-wait `+216.671ms`. Most of these top rows had zero connect setup in
  both profiles, so this looks like reused/queued HTTP/1.1 resource timing, not
  new TCP connect time.
- The broader HTTP queue-shape A/B table says the `500ms` run was not a whole
  page queue explosion: `http/1.1` queued `>=500ms` resources were `80/104`
  versus baseline `79/103`, zero-connect resources were `87/104` versus
  `88/103`, and median fetch-to-request was `-33.334ms`. The broad median
  request-wait still got worse by `+58.334ms`.
- The new top-resource relay-context A/B table is approximate, but useful. For
  the top `500ms` duration losses, matched median relay time was not worse:
  `get-connected.svg`, `fa-regular-400.woff2`, and `stay-safe.svg` each showed
  relay delta `-175ms` while their DOM tails got worse. High-confidence script
  rows showed the same direction: `modernizr.js`, `popper.min.js`, and
  `scrollspy.min.js` had relay delta `-177ms` and max receive gap delta
  `-604ms`, but resource duration still got worse.
- The `500ms` profile did improve max load in this small sample:
  `5936.394ms` versus baseline `7543.990ms`.
- Circuit selection counted `1` build hedge timer, `1` pending hedge, and
  `0` pending hedge timers for the `500ms` profile.
- Hostname CONNECT max was `758ms` in the `500ms` profile. The slow `>=1s`
  CONNECT waits were `.onion` side requests.
- The new resource-to-relay summary shows why this is mixed: the `500ms` profile
  had lower matched median relay time (`3987ms` versus `4162ms`) and lower max
  receive gap (`878ms` versus `1482ms`), but still worse page median. So the
  remaining loss is not just one obvious relay gap.
- The same summary now carries critical-tail fields. In `20260607T165147`, the
  `500ms` profile had lower max resource response end (`5900.118ms` versus
  `7533.484ms`) and fewer resources ending in the final second (`34` versus
  `37`), but max tail after DOM was slightly worse (`2616.719ms` versus
  `2516.717ms`) and median resource-end-before-load was similar. Together with
  the phase split, that points to response-to-DOM/resource processing, not one
  missing hedge.

Meaning: the initial-build hedge timer is now live-proven in a passing browser
run, but the `500ms` threshold is not a speed win. It helped the max tail in
this tiny sample but hurt median page load. Keep it lab-only and do not promote
it as a default. The direct resource A/B rows point at image/font/icon/script
tails during response-to-DOM, and the relay-context rows show those losses can
remain even when matched relay timing is not worse. The broader HTTP queue shape
says `500ms` did not cause a whole-page queue blow-up, so the next source work
should inspect per-stream request/response scheduling for specific late HTTP/1.1
resources, or a safer retry condition that only fires on proven bad waits.

`results/browser-compare-20260607T173526/browser-compare.json` reran the same
focused no-warm-cache download-page shape with `--byte-tap`. It used load-aware
baseline Arti, an extra load-aware plus `500ms` profile, local C Tor,
interleaved schedule, `--skip-bundled-tor`, 3 runs, and the neutral local TCP
byte tap. It passed quality.

Result:

- Load-aware baseline Arti median load was `5927.124ms`; local C Tor was
  `5930.657ms`.
- Load-aware plus `500ms` profile median load was `5085.237ms`.
- The `500ms` profile beat load-aware baseline Arti on paired page-load runs
  `2/3`.
- Direct Arti A/B shows paired median load delta `-788.747ms`, response start
  `-433.342ms`, response-to-DOM `+200.004ms`, and DOM-to-load `+1100.022ms`.
- HTTP queue-shape A/B stayed close: `http/1.1` queued `>=500ms` resources were
  `78/106` versus baseline `76/106`, median fetch-to-request was `+33.334ms`,
  median request-wait was `+16.667ms`, and median receive was `+8.333ms`.
- Circuit selection counted `0` pending hedge timers, `0` build hedge timers,
  and `0` pending hedges for the `500ms` profile. So this run is not hedge speed
  proof.
- The neutral byte-tap summary shows the `500ms` profile's slowest tap run had
  max data gap `1449.091ms`; baseline Arti's max tap gap was `937.801ms`.
- The new grouped resource-to-byte-tap table shows many slow HTTP/1.1 resources
  share a small number of browser-to-proxy TCP connections. In the `500ms`
  profile, the cleanest target is run 2 connection `21`: `10/10` total rows
  high confidence, `8/8` slow rows high confidence, median slow duration
  `2641.720ms`, median slow fetch-to-request `891.685ms`, median slow wait
  `1325.027ms`, stream bytes `46924`, and max data gap `292.436ms`.
- Other useful but less clean groups were run 1 connection `4` (`4/4` slow rows
  high confidence, median slow duration `7016.807ms`, `232365` stream bytes),
  run 1 connection `7` (`18` slow rows, but only `1/18` high confidence,
  `905.816ms` max gap), and run 1 connection `9` (`5` slow rows, only `1/5`
  high confidence).
- The printed top rows show high-confidence joins for `TBA10.0.png` and
  `tor-logo@2x.png` on tap connection `4`, plus `favicon.ico` on connection
  `7`. Several icon CSS resources nearest connection `7` are low-confidence, so
  use the table as a direction finder, not a final causal proof.

Meaning: the byte-tap run supports the shared HTTP/1.1 connection hypothesis.
Late resource tails are often connection-local and can share one browser-to-proxy
TCP stream, but the exact bad rows still need high-confidence proof before
changing Arti scheduling. The next source change should target observable
per-connection or per-stream pacing, not a broad new hedge.

`results/browser-compare-20260607T175344/browser-compare.json` reran the focused
download-page byte-tap proof after the runner started saving per-run proxy relay
context. It passed quality. It is not hedge speed proof: the `500ms` profile was
slower than load-aware baseline by median load (`6758.489ms` versus
`3951.561ms`) and slower than local C Tor (`5090.587ms`).

The value is source targeting:

- Every Arti browser run now has saved per-run proxy signal lines, and every
  Arti run in this file has `1000` relay context lines. The relay join tables
  are populated for runs `1`, `2`, and `3`, not only the final tail.
- The cleanest combined tap-to-relay group is `arti_release_browser_pending500ms`
  run `2`, tap connection `18`. It has `9/9` slow rows high confidence and
  `9/9` relay joins high confidence.
- All those slow resources map to Arti timing id `19`, circuit
  `Circ 3.5 (Tunnel 18)`, stream `11369`.
- The slow rows are mostly icon/image resources on one reused HTTP/1.1 local
  connection. Median slow duration was `2616.719ms`; median slow
  fetch-to-request was `1850.037ms`; median slow wait was `483.343ms`; median
  receive was only `116.669ms`.
- The relay context for that same stream shows median relay time `3346ms`, max
  relay gap `476ms`, and max relay data bytes `25984`.
- The stream receiver gap context for timing id `19` says the `476ms` relay gap
  had `8` receiver reads, `1` SENDME, `1` successful SENDME, min receive window
  `451`, and max receiver queued bytes `2736`. This is not a simple full local
  queue or missing SENDME case.

Meaning: we now have a concrete source target, not just a page-load symptom.
The next Arti source inspection should follow stream `11369`/timing id `19` and
look at why many same-connection browser resources waited before request/response
while the relay side kept moving and queue/window state looked healthy.

## Latest Arti Quality Config Check

In `results/arti-quality-config-20260607T220354/arti-quality-config.json`,
local Arti source/config passed 23 checks:

- default IPv4 subnet-family prefix is `/16`.
- default IPv6 subnet-family prefix is `/32`.
- reachable addresses default to all addresses.
- default web prebuilt ports are `80` and `443`.
- default preemptive exit circuits per predicted web port remains `2`.
- default circuit dirtiness is `10 minutes`.
- config docs keep normal padding and warn reduced padding hurts privacy.
- preemptive circuit recheck delay is `1s` in the local lab patch.
- SOCKS username/password auth is mapped into Arti stream isolation.
- SOCKS CONNECT uses optimistic streams in the local lab patch.
- exit stream selection defaults to width `1`, with a bounded env override
  from `1` through `8` for A/B tests of wider values.
- non-onion SOCKS CONNECT has a default-off, bounded lab soft-timeout override;
  the check verifies the env var, `500ms` through `60000ms` bounds, runtime
  timeout wrapper, and `.onion` exclusion.
- normal exit pending-circuit hedging has a default-off, bounded lab override;
  the check verifies the env var, `500ms` through `60000ms` bounds, a max
  pending cap of `2`, exit-only use, the timer wait path, the initial-build
  timer log, and the hedge log string.
- load-aware open-circuit selection is default-off and exit-only; the check
  verifies the env var, default false behavior, assignment counters, and the
  least-assigned helper.
- same-isolation exit capacity top-up is default-off, bounded from `2` through
  `4`, exit-only, tied to the exact same `TargetTunnelUsage`, and waits until
  the selected same-isolation circuit already has reuse pressure.
- the browser runner can set `--arti-min-exit-circs-for-port` as a bounded lab
  override, but the latest count `3` run was rejected.
- exit path source/tests cover 3 hops, guard use, relay reuse, relay family,
  and subnet sharing.
- RPC path visibility is feature-gated; release help does not show C
  Tor-style circuit-status access.

Meaning: Arti has useful static quality evidence, but that file by itself is
not live circuit-path proof.

## Latest Arti RPC Path Check

In `results/arti-rpc-path-20260607T134227/arti-rpc-path.json`, an RPC-enabled
Arti build from the patched source at `tmp/arti-rpc/arti` passed a live path
probe with C Tor directory validation:

- Arti booted in `7.847s`.
- opened 3 isolated streams to `check.torproject.org:443`.
- `arti:describe_path` returned 3 paths with 3 known relays each.
- C Tor directory data showed the first hop had `Guard`.
- C Tor directory data showed all relays had `Fast`, `Running`, and `Valid`.
- C Tor directory data showed the last hop had `Exit`.
- no relay ID was reused.
- no detected relay-family overlap.
- no relays shared the same IPv4 `/16`.

Meaning: this is full sampled runtime path-quality proof for 3 Arti paths. It
is still not proof for every future Arti path.

## Latest Cache Diagnostic

In `results/cache-diagnostic-20260607T042439/cache-diagnostic.json`, the same
directory cache was reused for a cold and warm run.

Boot result:

- C Tor cold: `10.550s`; warm: `2.632s`.
- Arti cold: `21.649s`; warm: `0.372s`.
- Arti cold had 8 directory-failure lines. Arti warm loaded a good directory
  from cache with no directory-failure lines.

Fetch result:

- Warm Arti did not clearly beat warm C Tor overall.
- `check.torproject.org`: warm C Tor `1268.857ms`, warm Arti `1784.638ms`.
- `www.torproject.org`: warm Arti `1332.785ms`, warm C Tor `1444.485ms`.

Meaning: Arti's slow browser run is not explained only by a missing warm
directory cache. Warm Arti boots quickly, but browser page loads are still slow
in the current evidence.

## Latest Browser Write Diagnostic

In `results/browser-compare-20260607T181517/browser-compare.json`, the focused
download-page browser compare passed quality with byte tap and SOCKS write
timing enabled.

- Base Arti: median load `4203.461ms`, median elapsed `5741.647ms`.
- `500ms` pending-hedge Arti: median load `29856.490ms`, median elapsed
  `31344.108ms`.
- Local C Tor: median load `5729.532ms`, median elapsed `7726.299ms`.
- The `500ms` hedge profile is rejected again; it lost badly in this clean run.
- The new browser-facing write diagnostic worked. The top slow
  high-confidence tap/relay groups had `0.000ms` median and max write lag.

Meaning: this run does not prove a new speed patch. It does rule out local
SOCKS-to-browser write delay for the reproduced slow groups. The next source
target is relay receive / stream receiver timing, not browser socket flush.

## Latest Circuit Gap Split

Replaying the same
`results/browser-compare-20260607T181517/browser-compare.json` with the new
circuit-level relay gap table passed quality.

- Worst same-stream gap in the clean slow run: `4917ms` on timing id `21`,
  stream `12719`, `Circ 2.8 (Tunnel 21)`.
- Same run and same circuit had a smaller whole-circuit max gap: `2924ms`.
- A `1050ms` circuit gap ended on the next `12719` DATA cell, while another
  stream on the same circuit also moved.
- Earlier SOCKS write lag for the same slow groups was `0.000ms`.

Meaning: the worst visible delay is not a full idle circuit and not a local
SOCKS write stall. Do not patch the generic circuit reactor or browser-facing
flush from this proof. The next target is per-stream resource/HTTP timing, or
exit/server latency for the slow stream.

## Latest Resource/Stream Gap Context

The analyzer now also prints `Browser Resource Stream Gap Context`, joining
each SOCKS/relay stream gap back to browser resource phases on the same stream.
The replay of `20260607T181517` still passed quality.

- Timing id `21`, stream `12719`, had the largest same-stream gap, `4917ms`,
  but it had `0` browser resource phase overlaps. Do not chase this as the main
  browser-load symptom.
- Timing id `22`, stream `12720`, had a `4827ms` gap, but only `0/3`
  same-stream resources were high confidence, so it is weak proof.
- Timing id `19`, stream `25673`, `Circ 3.6 (Tunnel 17)`, is now the best next
  target: gap `3803ms`, `33` same-stream resources, `14` high-confidence
  matches, `31` slow resources, and the top overlap is the full `3803ms` inside
  browser `request_wait`.

Meaning: the next source work should inspect why one stream with many
same-connection resources waits for response data. This points to per-stream
HTTP/resource pacing or exit/server latency, not broad circuit idle, SOCKS
flush, path length, or crypto.

## Latest Stream Gap Byte Context

The analyzer now also prints `Browser Resource Stream Gap Byte Context`. This
separates browser bytes read by the SOCKS proxy, bytes written into the Tor
stream, and response bytes during each slow stream gap.

On the replay of `20260607T181517`, timing id `19` / stream `25673` had:

- `0` browser read bytes inside the strict `3803ms` gap.
- `528` browser read bytes on the gap edges.
- `0` retained response byte events inside the strict gap.
- The saved proof predates the new `client_to_tor_write` source log, so Tor
  write columns are `0` until a fresh run is captured.

Local Arti source now logs debug-only `client_to_tor_write` byte events and
relay-finished totals, matching the earlier `tor_to_client_write` proof. The
next fresh debug run should prove whether browser bytes are written into the Tor
stream immediately at this request-wait edge.

## Latest Client-To-Tor Write Proof

`results/browser-compare-20260607T184405/browser-compare.json` rebuilt release
Arti with the new `client_to_tor_write` debug log and reran the focused
download-page shape: cold cache, interleaved, bundled Tor skipped, byte tap,
load-aware Arti, and a diagnostic `500ms` pending-hedge profile. It passed
quality.

- Base Arti median load: `6642.422ms`.
- `500ms` pending-hedge Arti median load: `4821.044ms`.
- Local C Tor median load: `5157.569ms`.
- `500ms` pending-hedge Arti counted `1` pending hedge, but this is still debug
  and byte-tap evidence only.
- The new byte log worked: `client_to_tor_write` rows appeared for both Arti
  profiles.
- In the sampled rows, `client_to_tor` and `client_to_tor_write` matched
  first/last timings and cumulative bytes. Example: base Arti timing id `2`
  had both directions at `4671` bytes through `3801ms`; pending-hedge timing id
  `2` had both directions at `4277` bytes through `3023ms`.
- The older `3803ms` request-wait gap did not reproduce. The largest joined
  stream gap in this fresh proof was `701ms`.
- Top request-wait byte-context rows mostly had browser read bytes and Tor write
  bytes on gap edges, not in the strict quiet middle. Example: base Arti timing
  id `4` had `504` read-edge bytes and `504` write-edge bytes, with `0` strict
  middle bytes.

Meaning: this fresh proof does not show local outbound write delay. The next
normal-speed gate can test whether the `500ms` pending-hedge result repeats
without debug logging and without byte tap, but it should not be promoted from
this diagnostic run alone.

## Latest Normal Hedge Gate

`results/browser-compare-20260607T184844/browser-compare.json` reran the
download-page A/B without debug logging and without byte tap: cold cache,
interleaved, bundled Tor skipped, load-aware Arti, and a diagnostic `500ms`
pending-hedge profile. It passed quality.

- Base load-aware Arti median load: `5147.814ms`.
- `500ms` pending-hedge Arti median load: `6239.814ms`.
- Local C Tor median load: `6913.908ms`.
- Base load-aware Arti beat local C Tor on this one normal download-page gate.
- The `500ms` hedge profile lost to base load-aware Arti by `1092.000ms` median
  load and `1110.114ms` median elapsed.
- Resource type A/B was worse for the `500ms` profile across css, image, link,
  other, and script rows.

Meaning: the `500ms` hedge is rejected as a page-load speed direction for this
shape. The good news is base load-aware Arti beat local C Tor in a clean normal
run, but this is still one target. The next proof should be a broader normal
multi-target load-aware gate and more resource-tail work, not hedge promotion.

## Latest Multi-Target Load-Aware Gate

`results/browser-compare-20260607T185521/browser-compare.json` ran the broader
normal no-debug, no-byte-tap load-aware gate across `check.torproject.org`, the
Tor homepage, and the download page. It failed quality.

- Base load-aware Arti had `1` failed `check.torproject.org` run with a browser
  `connectionFailure` neterror and missing screenshot.
- On accepted median page-load rows, base load-aware Arti beat local C Tor on
  the homepage (`4138.525ms` versus `8046.356ms`) and download page
  (`4504.104ms` versus `6818.213ms`).
- It still lost badly on `check.torproject.org`: `3063.882ms` versus local C
  Tor `1337.111ms`.
- The download page also had a huge accepted Arti tail: max load `58775.544ms`,
  with browser `connectEnd` at `52751.055ms`.

Meaning: load-aware Arti is not default-ready. The median win on larger pages is
useful, but exact quality failed and the slow path is a browser CONNECT/first
response tail, not the rejected pending hedge.

## Latest Soft-Connect Safety Fix

`results/browser-compare-20260607T190326/browser-compare.json` tested
load-aware Arti plus a `500ms` SOCKS CONNECT soft-timeout profile before the
source fix. It failed quality: the soft-timeout profile had one
`check.torproject.org` neterror and one download-page neterror.

Local Arti source now applies the soft timeout only while another retry is still
allowed. The final CONNECT attempt waits normally instead of returning an early
SOCKS failure to the browser. The latest static source check
`results/arti-quality-config-20260607T220354/arti-quality-config.json` passed
with `23` checks and still covers this rule.

`results/browser-compare-20260607T191031/browser-compare.json` reran the same
focused normal A/B after rebuilding release Arti. It passed quality.

- Base load-aware Arti median load: `3058.087ms` on `check.torproject.org` and
  `14503.510ms` on the download page.
- Fixed soft-timeout Arti median load: `3221.547ms` on `check.torproject.org`
  and `9596.071ms` on the download page.
- Local C Tor median load: `1099.239ms` on `check.torproject.org` and
  `7422.857ms` on the download page.
- The fix removed the early-failure quality problem in this focused rerun, but
  `500ms` soft timeout still lost to local C Tor on both targets.

Meaning: keep the soft-timeout path lab-only. The source fix is good because it
protects quality, but it is not a faster-Tor result. Next work should inspect
the load-aware resource tail and CONNECT/response-start tail with debug logs,
not promote `500ms` soft timeout.

## Latest Load-Aware Tail Diagnostic

`results/browser-compare-20260607T192045/browser-compare.json` reran the
download page with retained Arti debug logs: cold cache, interleaved, bundled
Tor skipped, load-aware Arti, fixed load-aware plus `500ms` soft-timeout Arti,
and local C Tor. It passed quality. This is debug evidence only, not speed
proof.

- Base load-aware Arti median load: `15464.467ms`.
- Fixed soft-timeout Arti median load: `5519.348ms`.
- Local C Tor median load: `5127.752ms`.
- Fixed soft-timeout Arti was close to local C Tor but still slower by median
  load. It counted `0` soft timeouts, so this run does not prove the timeout
  caused the win over base load-aware Arti.
- Base load-aware Arti's browser response start was only `400.008ms` slower
  than local C Tor, but response-to-DOM was `3733.408ms` slower and DOM-to-load
  was `6200.124ms` slower.
- Hostname SOCKS CONNECT was not the slow step in this debug run:
  `median connect = 0.000ms`, `max hostname connect = 0.000ms`.
- The notable slow base Arti rows were `relay>=5s` hostname streams, not slow
  hostname CONNECT rows.
- The analyzer saw `0` stream scheduler hop blocks and `0` relay queue-full
  events.
- The corrected analyzer now separates open candidates from select
  parallelism. Base load-aware Arti had `18` exit open picks with more than one
  candidate, and fixed soft-timeout Arti had `19`. Both still had `0` exit
  picks with select parallelism above `1`.
- The slow shape was mixed: base run 2 had `9/9` exit open picks with more than
  one candidate and was still slow, while base run 3 had only `1/10` and reused
  a circuit with `8` assigned streams.

Meaning: do not patch the CONNECT retry path as the next default speed change.
In this proof, the problem moved after stream creation into resource/relay tail
and HTTP/1.1 queue timing. The next source work should inspect chosen-circuit
relay quality, late single-candidate reuse, and whether least-assigned
load-aware choice needs a safe circuit-quality signal.

## Latest Candidate-Choice Diagnostic

`results/browser-compare-20260607T193855/browser-compare.json` reran the
download page after adding debug-only candidate assignment summaries to Arti's
load-aware open-circuit log. It used cold cache, interleaved schedule, bundled
Tor skipped, load-aware Arti, load-aware plus `500ms` soft-timeout Arti, and
local C Tor. It passed quality. This is diagnostic evidence only, not speed
proof.

- Base load-aware Arti median load: `5227.943ms`.
- Fixed soft-timeout Arti median load: `9211.781ms`.
- Local C Tor median load: `4871.780ms`.
- Fixed soft-timeout Arti was worse than base load-aware Arti by
  `3983.838ms` median load and worse than local C Tor by `89.1%`.
- Base load-aware Arti had `21` exit load-aware open picks, `20` exit picks
  with more than one candidate, and `8` selected a non-first candidate. Its
  max selected assigned-stream count was `2`.
- Fixed soft-timeout Arti had `22` exit load-aware open picks, `16` exit picks
  with more than one candidate, and `9` selected a non-first candidate. Its
  max selected assigned-stream count was `5`.
- The bad soft-timeout run was run 3: page load `14531.549ms`, `0/6` exit
  picks with more than one candidate, max selected assigned streams `5`, and
  repeated use of `Circ 3.12`. The navigation SOCKS join for that run had
  `1239ms` connect, `13429ms` relay, and `1011ms` max receive gap.
- When multiple candidates existed, the new log showed the picker alternating
  to the least-assigned circuit. The worst tail happened when there was no
  alternative eligible exit circuit left.

Meaning: do not promote `500ms` soft timeout and do not add broad circuit
racing. The next proof should explain why the eligible exit set shrinks to one
circuit during the resource burst, and whether a safe readiness/capacity
signal can avoid late single-candidate reuse without changing Tor path rules.

## Latest Support-Cause Diagnostic

`results/browser-compare-20260607T194925/browser-compare.json` reran the
download page after adding debug-only open-circuit support summaries to Arti's
load-aware log. It used cold cache, interleaved schedule, bundled Tor skipped,
load-aware Arti, load-aware plus `500ms` soft-timeout Arti, and local C Tor. It
passed quality. This is diagnostic evidence only, not default-readiness proof.

- Base load-aware Arti median load: `3908.519ms`.
- Fixed soft-timeout Arti median load: `3373.252ms`.
- Local C Tor median load: `4075.043ms`.
- Base load-aware Arti was `4.1%` faster than local C Tor by median load in
  this window. Fixed soft-timeout Arti was `17.2%` faster by median load, but
  still had a bad max-load tail: `14936.910ms`.
- Base load-aware Arti run 3 had only `1/7` exit picks with more than one
  candidate. Its support summary showed max open total `12`, max rejected open
  `11`, max isolation rejects `9`, max port rejects `0`, and max unusable `2`.
- Fixed soft-timeout Arti run 3 had `0/6` exit picks with more than one
  candidate. Its support summary showed max open total `9`, max rejected open
  `8`, max isolation rejects `7`, max port rejects `0`, and max unusable `0`.
- The slow fixed soft-timeout navigation row had `8730ms` CONNECT,
  `6292ms` relay, and used `Circ 3.12`. This is still not a reason to promote
  the soft timeout.

Meaning: the eligible exit set shrinks mainly because open circuits are already
restricted to other stream-isolation groups. That is a quality boundary, not
free capacity. The next safe proof must preserve stream isolation and inspect
whether Arti can prepare enough capacity for the active isolation group without
sharing circuits across incompatible isolation groups.

## Latest Same-Isolation Capacity Lab

Local Arti source now has a default-off same-isolation exit capacity top-up for
lab tests. It can build extra exit circuits only for the exact same
`TargetTunnelUsage`; it does not share circuits across incompatible stream
isolation groups. The static check
`results/arti-quality-config-20260607T220354/arti-quality-config.json` passed
with `23` checks.

`results/browser-compare-20260607T201555/browser-compare.json` tested
load-aware baseline Arti against same-isolation target `2` on the download page
with warm cache. It passed quality.

- Baseline Arti median load: `4949.773ms`; max load: `6263.231ms`.
- Same-isolation target `2` median load: `3933.909ms`; max load: `5515.623ms`.
- Local C Tor median load: `3630.921ms`.
- The analyzer counted `0` same-isolation top-ups, so this proves wiring and
  quality only. It does not prove the top-up behavior helped.

`results/browser-compare-20260607T201803/browser-compare.json` tested
same-isolation target `3` in the same warm-cache shape. It passed quality and
did exercise the code path.

- Baseline Arti median load: `3844.865ms`; max load: `10379.077ms`.
- Same-isolation target `3` median load: `3880.539ms`; max load: `6551.679ms`.
- Local C Tor median load: `4383.813ms`.
- Same-isolation target `3` won `2/3` paired loads against baseline Arti and
  cut max load by `3827.398ms`.
- The analyzer counted `4` same-isolation top-ups and `0` top-up failures.

The broader debug proof
`results/browser-compare-20260607T202610/browser-compare.json` tested targets
`3` and `4` over three Tor Project pages. It passed quality.

- Target `3`: `12` top-ups, `0` failures. It helped the download page
  (`5149.197ms` vs baseline `7704.376ms`) but hurt the small page and homepage.
- Target `4`: `19` top-ups, `0` failures. It helped homepage and download
  medians versus baseline, but still had a `59612.396ms` download max tail.

Local source then tightened the lab rule: same-isolation top-up now waits until
the selected circuit already has assigned streams. This avoids building extra
circuits on the first use of a new isolation group. The top-up log moved to
info level so low-log gates can still count it.

`results/browser-compare-20260607T203902/browser-compare.json` tested the
pressure-gated target `4`. It passed quality and counted `16` top-ups, but it
still lost the download-page median to both baseline Arti and local C Tor.

`results/browser-compare-20260607T204728/browser-compare.json` tested the
pressure-gated target `3`. It passed quality and counted `9` top-ups with
`0` failures.

- Small page: target `3` was slower than baseline Arti (`2355.649ms` vs
  `2037.250ms`) but close to local C Tor (`2405.469ms`).
- Homepage: target `3` beat baseline Arti (`3773.437ms` vs `6340.231ms`) and
  local C Tor (`5380.545ms`).
- Download page: target `3` beat baseline Arti (`4048.667ms` vs `7172.675ms`)
  and local C Tor (`7712.941ms`), with max load `4115.672ms` versus baseline
  `9959.526ms`.

The fairer low-log 5-run gate
`results/browser-compare-20260607T205407/browser-compare.json` failed quality.
Target `3` had one download-page `about:neterror` timeout and missed its
screenshot. Info-level top-up logging worked and counted `16` top-ups with
`0` failures, but this file is rejected as speed proof.

`results/browser-compare-20260607T212007/browser-compare.json` then tested the
safer pressure-gated target `2` on the download page with low logs. It passed
quality and the new browser-run timestamp fields were present, but it was not a
speed win.

- Baseline Arti median load: `4415.803ms`; max load: `9265.125ms`.
- Same-isolation target `2` median load: `8298.258ms`; max load:
  `8470.335ms`.
- Local C Tor median load: `6732.451ms`.
- Target `2` counted `1` same-isolation top-up and `0` top-up failures.

This target `2` result is rejected as speed proof. It reduced the worst Arti
tail in this small window, but it lost median load to both baseline Arti and
local C Tor.

`results/browser-compare-20260607T212559/browser-compare.json` repeated the
focused download-page check with pressure-gated target `3` and low logs. It
also passed quality, and the timestamp fields were present, but it lost speed
in this window.

- Baseline Arti median load: `5003.338ms`; max load: `5344.091ms`.
- Same-isolation target `3` median load: `6627.799ms`; max load:
  `6655.497ms`.
- Local C Tor median load: `4373.648ms`.
- Target `3` counted `1` same-isolation top-up and `0` top-up failures.

This focused target `3` result is also rejected as speed proof. It passed
quality, but it lost median load to baseline Arti by `1624.461ms` and to local
C Tor by `2254.151ms`.

Meaning at that time: pressure-gated target `3` was the best same-isolation
capacity shape, but it was still lab-only. Newer capacity-only target `4`
evidence in `results/browser-compare-20260608T032422/browser-compare.json`
looked like the next lead, but the wider low-log gate in
`results/browser-compare-20260608T033012/browser-compare.json` rejected both
target `3` and target `4`. Do not make either default.

## Latest Browser Connection Pref Diagnostic

`results/browser-compare-20260607T213549/browser-compare.json` added a
read-only browser connection pref audit to the focused download-page run. It
passed quality. This is diagnostic evidence only, not a speed proof.

- The browser used HTTP/1.1 for the sampled download-page resources:
  `37/37` Arti resources and `34/36` local C Tor resources.
- The audited Tor Browser prefs matched for both profiles:
  `network.http.http3.enable=false`,
  `network.http.max-connections=900`,
  `network.http.max-persistent-connections-per-server=6`, and
  `network.http.max-persistent-connections-per-proxy=256`.
- The old HTTP/2 pref keys checked by the audit were not present in this
  Firefox build.
- Arti had `25` resources with at least `500ms` fetch-to-request queue time;
  local C Tor had `27`.

Meaning: do not change browser connection prefs as a speed fix. That would
change Tor Browser behavior. The next safe source work should keep the same
browser settings and improve Tor-side resource/relay tails under normal
HTTP/1.1 page loading.

## Latest Load-Aware Replay And Gap Summary

`results/browser-compare-20260607T214417/browser-compare.json` added the new
browser resource stream-gap phase summary to a focused download-page replay.
It used warm cache, interleaved schedule, bundled Tor skipped, base Arti,
load-aware Arti, and local C Tor. It passed quality. This is diagnostic
evidence only because debug logging was on.

- Base Arti median load: `3636.147ms`.
- Load-aware Arti median load: `5540.512ms`.
- Local C Tor median load: `6204.217ms`.
- Load-aware Arti lost to base Arti by `1904.365ms` median load.
- Base Arti beat local C Tor by `2568.070ms` median load in this focused run.
- Both Arti profiles used unchanged Tor Browser connection prefs:
  HTTP/3 disabled and `6` persistent connections per server.
- The new stream-gap phase summary showed load-aware run 1 had `3064.615ms`
  request-wait overlap and `1940.000ms` unmatched gap time. Base Arti's two
  runs had lower request-wait overlap, `1094.670ms` and `1155.000ms`.

Meaning: do not promote load-aware selection from this replay. The next useful
source work is to explain request-wait and unmatched relay/resource gaps without
changing Tor Browser prefs or sharing circuits across isolation groups.

## Latest Load-Aware Spread Guardrail Lab

`results/browser-compare-20260607T215932/browser-compare.json` tested a
default-off load-aware guardrail:
`TORFAST_EXIT_SELECT_MIN_ASSIGNMENT_SPREAD=2`. The guardrail keeps the normal
first eligible circuit unless candidate assigned-stream spread is at least `2`.
It used warm cache, interleaved schedule, bundled Tor skipped, base Arti,
old load-aware Arti, spread-guarded load-aware Arti, and local C Tor. It passed
quality. This is diagnostic evidence only because debug logging was on.

- Base Arti median load: `5212.234ms`.
- Old load-aware Arti median load: `5408.240ms`.
- Spread-guarded load-aware Arti median load: `5947.730ms`.
- Local C Tor median load: `7136.471ms`.
- Old load-aware lost to base Arti by `196.007ms` median load, but cut max load
  by `826.426ms`.
- Spread-guarded load-aware lost to base Arti by `735.496ms` median load and
  had a worse max load by `371.824ms`.
- The analyzer counted `5` guardrail-kept-first decisions for the spread `2`
  profile, so the new rule did run.
- The new per-circuit quality table shows why simple spreading is weak:
  load-aware and spread-guarded runs used more circuits, but some chosen
  circuits had long relay times and very low rough receive rates. Examples:
  load-aware run 1 had one circuit at `8.502 KiB/s` with a `4593ms` relay time,
  while spread `2` run 1 had circuits at `23.718 KiB/s` and `7.119 KiB/s`.
- The new run summary makes the rule clearer: base Arti had `0` low-rate
  circuits in both runs, old load-aware had `2` then `1`, and spread `2` had
  `2` then `1`.
- The selected-vs-first health outcome table shows the selector often picked a
  later-measured worse circuit than candidate `0`: old load-aware had `3/3`
  worse non-first picks in run 1 and `4/4` in run 2; spread `2` had `3/3`
  worse non-first picks in run 1.

Meaning: reject `min_assignment_spread=2` as a speed proof. A simple
assigned-stream spread threshold is not enough; the remaining useful direction
is circuit-health, relay, and resource-tail evidence, not broader balancing.

## Latest Circuit Health Signal Proof

`results/browser-compare-20260607T223225/browser-compare.json` rebuilt release
Arti with the read-only `CircuitHealthSnapshot` source hook and ran a focused
download-page proof with warm cache, interleaved schedule, bundled Tor skipped,
debug logs, base Arti, load-aware Arti, and local C Tor. It passed quality.
This is diagnostic evidence only because it used 2 runs and debug logging.

- Base Arti median load: `9344.381ms`.
- Load-aware Arti median load: `4089.913ms`.
- Local C Tor median load: `5445.368ms`.
- Load-aware Arti beat base Arti by `5254.468ms` median load and beat local C
  Tor by `1355.455ms` median load in this narrow window.
- The new source hook worked: the circuit-selection summary parsed `30`
  candidate health rows for the load-aware profile, with max candidate health
  bytes `11760` and max candidate health gap `204ms`.
- Per-run candidate health rows were nonzero for load-aware: `22` rows in run 1
  and `8` rows in run 2.
- The selected-vs-first health outcome was mixed in run 1: `4` non-first picks,
  `2` later worse than candidate `0` and `2` later better. Run 2 had `0`
  non-first picks.
- The load-aware run 2 circuit-quality summary had `0` low-rate circuits and
  `0` slow-relay circuits; base Arti had low-rate circuits in both runs.

Meaning: the health signal is now real enough to drive future proof. Do not
promote load-aware from this 2-run debug result. The next source step should
test a health-aware selector as a lab-only candidate and compare it against
base and load-aware in a larger same-window gate.

## Latest Health-Aware Selector Patch

Local Arti now has a second default-off lab flag:
`TORFAST_EXIT_SELECT_HEALTH_AWARE`. It only has an effect when
`TORFAST_EXIT_SELECT_LOAD_AWARE` is also enabled and the request is an exit
request. It still chooses only among already eligible open exit circuits, so it
does not change path length, relay eligibility, stream isolation, or browser
prefs.

- The selector starts from the existing least-assigned load-aware choice.
- If health-aware mode is on, it can choose the candidate with the best observed
  circuit health score.
- A candidate needs at least `2` incoming RELAY DATA cells, at least `4096`
  incoming RELAY DATA bytes, max RELAY DATA gap at most `750ms`, and a last
  DATA cell no older than `2000ms`.
- The score is rough observed bytes per second over the circuit's RELAY DATA
  first-to-last span.
- If the assignment-selected circuit has no score, the health-selected
  candidate must score at least `64 KiB/s`. If both have scores, the
  health-selected candidate must be at least `2x` better.
- Debug logs now include `select_health_aware`,
  `load_aware_assignment_candidate_index`, `health_aware_candidate_index`,
  `health_aware_assignment_score_bps`, `health_aware_candidate_score_bps`, and
  `selected_health_score_bps`.
- The analyzer now reports both `health-aware changed assignment` and
  `health-aware kept assignment`.
- `tools/run_browser_compare.py` can start the same-window extra profile with
  `--extra-arti-exit-select-health-aware`; that profile is named
  `arti_release_browser_healthaware`.

Meaning: this source patch is testable and default-off. The first browser gate
below proves the mode runs, but does not make it default-ready.

## Latest Health-Aware Selector Browser Proof

`results/browser-compare-20260607T225227/browser-compare.json` tested base Arti,
plain load-aware Arti, health-aware Arti, and local C Tor in one focused
download-page window. It used warm cache, interleaved schedule, bundled Tor
skipped, debug logs, and 2 runs. It passed quality.

- Base Arti median load: `7362.023ms`.
- Health-aware Arti median load: `5813.657ms`.
- Plain load-aware Arti median load: `5749.771ms`.
- Local C Tor median load: `4213.227ms`.
- Health-aware beat base Arti by `1548.366ms` median load and cut max load by
  `2019.417ms`.
- Health-aware lost to plain load-aware by `63.886ms` median load and to local C
  Tor by `1600.430ms` median load.
- The selector really ran: health-aware had `18` exit load-aware picks and
  `12` choices changed away from the assignment-only candidate.
- The analyzer parsed `51` health candidate rows for health-aware, with max
  candidate bytes `284963`. Candidate logs include all candidates, so the max
  logged gap `760ms` can be above the scoring cutoff even if that candidate is
  not score-eligible.
- Health-aware run 1 still had `2` low-rate circuits and `1` slow-relay circuit.
  Health-aware run 2 had `0` low-rate and `0` slow-relay circuits.

Meaning: keep health-aware lab-only. It is better than base Arti in this narrow
debug proof, but it did not beat plain load-aware or local C Tor. The scoring
rule needs a stronger guard against low-rate or slow-relay choices before any
larger gate.

## Latest Health-Aware Stale-Score Guard Proof

`results/browser-compare-20260607T230909/browser-compare.json` passed quality,
but rejected the first guard shape: health-aware median load was
`12815.382ms`, worse than base Arti `4892.849ms`, plain load-aware
`7613.632ms`, and local C Tor `4611.300ms`. The raw selector log showed a
once-fast circuit could be chosen several seconds later, then hit multi-second
relay gaps. The source now rejects health scores older than `2000ms`.

`results/browser-compare-20260607T231745/browser-compare.json` rebuilt release
Arti with that stale-score guard and reran the same focused download-page
window: warm cache, interleaved schedule, bundled Tor skipped, debug logs, base
Arti, health-aware Arti, plain load-aware Arti, and local C Tor. It passed
quality.

- Base Arti median load: `6931.042ms`.
- Health-aware Arti median load: `5011.993ms`.
- Plain load-aware Arti median load: `5716.333ms`.
- Local C Tor median load: `6638.935ms`.
- Health-aware beat base Arti by `1919.049ms` median load, plain load-aware by
  `704.340ms`, and local C Tor by `1626.943ms` in this narrow window.
- Health-aware had `18` exit load-aware picks, changed `4` assignment-only
  choices, and kept the assignment choice `12` times.
- The analyzer parsed `58` health candidate rows for health-aware. Candidate
  logs include all candidates, so max candidate gap can exceed the scoring
  cutoff; score eligibility still requires gap at most `750ms` and age at most
  `2000ms`.
- Health-aware run 1 still had `2` low-rate circuits and `3` slow-relay
  circuits. Health-aware run 2 had `0` low-rate and `0` slow-relay circuits.

Meaning: this is the best focused health-aware result so far, but it is still
lab-only. The next proof should repeat it on a broader target set and more
runs before any default discussion.

## Latest Health-Aware Broader Gate

`results/browser-compare-20260607T232339/browser-compare.json` repeated the
health-aware test across `check.torproject.org`, the Tor Project homepage, and
the Tor Project download page. It used warm cache, interleaved schedule,
bundled Tor skipped, debug logs, base Arti, health-aware Arti, plain load-aware
Arti, and local C Tor. It ran 3 times per target and passed quality.

- Health-aware beat base Arti on all three target medians: `1589.501ms` versus
  `5070.158ms` on check, `4966.648ms` versus `64215.261ms` on the homepage,
  and `4733.131ms` versus `20120.651ms` on download.
- Health-aware also beat plain load-aware on all three target medians. Plain
  load-aware medians were `1830.191ms` on check, `10669.904ms` on the
  homepage, and `6843.666ms` on download.
- Health-aware cut the plain load-aware tails: homepage max load was
  `5923.578ms` versus `62408.544ms`, and download max load was `6231.047ms`
  versus `29598.095ms`.
- Against local C Tor, health-aware was basically tied on check
  (`-0.022ms` paired median load delta), slower on the homepage by `68.302ms`,
  and faster on download by `480.184ms`.
- Health-aware still won boot+load against local C Tor on all three targets:
  `-2269.022ms` on check, `-2200.698ms` on the homepage, and `-2749.184ms` on
  download.
- The selector really ran at broader scale: `53` health-aware open picks, `6`
  changed assignment choices, `12` kept assignment choices, and `136` parsed
  candidate health rows.
- Health-aware SOCKS relay timing was much better than base Arti and plain
  load-aware in this gate: median relay `2032ms`, max relay `6339ms`, versus
  base Arti median `13192ms` and max `87635ms`, and plain load-aware median
  `4289ms` and max `62804ms`.
- Some health-aware runs still had low-rate or slow-relay circuits, but the
  bad tails were much smaller than base Arti and plain load-aware.

Meaning: this is the strongest health-aware result so far. It is still lab-only
because it is a 3-run debug gate, and the homepage is only a near-tie against
local C Tor by page-only load.

## Latest Low-Log Health-Aware Rejection

`results/browser-compare-20260607T233909/browser-compare.json` reran
health-aware with lower Arti logging: warm cache, interleaved schedule,
bundled Tor skipped, `--arti-log-level info`, 5 runs, 3 targets, base Arti,
health-aware Arti, plain load-aware Arti, and local C Tor. It failed quality.

- Health-aware download run 3 failed after `61518.070ms` elapsed with a browser
  `about:neterror` connection failure and no screenshot proof.
- Health-aware download summary was not ok: `4` successes, `1` failure, median
  load `11170.564ms`, and max successful load `25025.532ms`.
- On download, base Arti median load was `5989.706ms`, plain load-aware Arti
  was `5679.386ms`, and local C Tor was `4774.818ms`.
- Health-aware was good on the homepage median in this window:
  `5281.338ms`, versus base Arti `7279.818ms`, plain load-aware `7929.384ms`,
  and local C Tor `7317.988ms`.
- Health-aware was slower on check: `2474.152ms`, versus base Arti
  `1965.395ms`, plain load-aware `1788.387ms`, and local C Tor `2262.682ms`.
- The analyzer now prints a `Browser Failed Runs` table. For this gate it shows
  the failed health-aware download run, elapsed time, missing screenshot, and
  browser error text directly.

Meaning: this rejects promoting health-aware from the debug proof. It may still
be a useful lab direction, but the next source step needs retained failure logs
or a stronger reliability guard, not a default change.

## Latest Retained-Failure Runner Check

The browser runner now keeps more evidence when compact-output runs fail. In
compact mode, failed browser runs keep their profile and home directories, and
`record_proxy_run_signals` keeps a per-run `proxy_output_tail` even when the
proxy logs have no special `torfast` signal lines. The analyzer's
`Browser Failed Runs` table now also reports proxy-tail line count and the last
proxy line. The runner also has a default-off `--proxy-run-tail-lines` option
for successful interleaved runs, and the analyzer now prints `Browser Run Proxy
Tails` when those per-run tails are present.

`results/browser-compare-20260607T235651/browser-compare.json` then ran a
focused low-log download-page check with warm cache, interleaved schedule,
bundled Tor skipped, `--arti-log-level info`, 3 runs, base Arti, health-aware
Arti, plain load-aware Arti, and local C Tor. It passed quality, but rejected
health-aware as a speed direction in this window.

- Health-aware median load was `16524.629ms`.
- Base Arti median load was `5592.204ms`.
- Plain load-aware Arti median load was `6362.165ms`.
- Local C Tor median load was `4207.812ms`.
- Health-aware lost all paired page-load runs against local C Tor and was
  `+12316.817ms` slower by paired median page load.
- Health-aware lost all paired page-load runs against base Arti and was
  `+7303.998ms` slower by paired median page load.
- The main health-aware loss was after the first response: response-to-DOM was
  `+6016.787ms` versus local C Tor, and DOM-to-load was `+4566.758ms`.

Meaning: health-aware remains rejected for now. The next useful source work is
to explain or prevent the late-page/resource queue shape, not to promote the
selector.

`results/browser-compare-20260608T000334/browser-compare.json` then repeated the
focused download-page check with `--proxy-run-tail-lines 120`. It passed
quality. The retained run-tail table proved the option works, but at low Arti
`info` logging only the first successful runs emitted proxy lines; later slow
successes had no proxy lines. This means the next cause-finding proof still
needs debug-level `torfast` signals.

- Health-aware median load was `6026.292ms`.
- Base Arti median load was `7587.330ms`.
- Plain load-aware Arti median load was `5446.530ms`.
- Local C Tor median load was `5101.879ms`.
- Health-aware beat base Arti by `1691.096ms` paired median page load, but lost
  to local C Tor by `794.355ms` and to plain load-aware by median load.
- Plain load-aware was the best Arti profile in this window and beat local C Tor
  by `749.723ms` paired median page load, but earlier wider gates still keep it
  lab-only because of bad tails and quality failures.

Meaning: the retained-tail tooling is useful, but low-log success tails are not
enough to explain the remaining loss. Health-aware and load-aware both stay
lab-only until debug-level evidence explains the late resource queue/tail shape.

`results/browser-compare-20260608T000956/browser-compare.json` then repeated the
focused download-page check with debug `torfast` logs, 2 runs, base Arti,
health-aware Arti, plain load-aware Arti, and local C Tor. It passed quality,
but rejected the current health-aware and plain load-aware selectors in this
window.

- Base Arti median load was `3752.832ms`.
- Local C Tor median load was `5800.624ms`.
- Health-aware median load was `18465.459ms`.
- Plain load-aware median load was `12139.927ms`.
- Health-aware lost all paired page-load runs against base Arti and was
  `+14712.626ms` slower by paired median load.
- Plain load-aware lost all paired page-load runs against base Arti and was
  `+8387.094ms` slower by paired median load.
- The loss was after first response. Health-aware had `+4316.753ms`
  response-to-DOM and `+9900.198ms` DOM-to-load versus base Arti. Plain
  load-aware had `+616.679ms` response-to-DOM and `+7250.145ms` DOM-to-load.
- The relay/resource join showed long tails: health-aware median relay time was
  `10417.000ms` with max tail-after-DOM `17733.688ms`; plain load-aware median
  relay time was `4407.000ms` with max tail-after-DOM `15533.644ms`.
- `Notable Torfast SOCKS Streams` showed many `relay>=5s` hostname streams in
  both selector profiles, while browser connection prefs stayed unchanged.

Meaning: this debug proof says not to promote either selector, and not to patch
Tor Browser connection prefs. The next useful source step is to explain why the
chosen circuits later produce long relay/resource tails, or add a default-off
guard that rejects those choices without changing Tor quality rules.

The selector logs now include score, span, and age in
`candidate_health_summary`: `index:circuit:cells:bytes:max_gap_ms:score:span_ms:age_ms`.
The analyzer keeps old log parsing compatible and adds those fields to circuit
selection and load-aware health-outcome tables. This is diagnostics only; it
does not change default Tor behavior.

`results/browser-compare-20260608T002242/browser-compare.json` then proved the
new fields work in a one-run debug download-page check. It passed quality, but
again rejected selector promotion.

- Base Arti load was `4126.153ms`.
- Local C Tor load was `4423.169ms`.
- Health-aware load was `7066.667ms`.
- Plain load-aware load was `7611.330ms`.
- The health-outcome table showed the old default often selected zero-score
  circuits: median selected score was `0.000`, while median first score was
  `19502.000`.
- Those selected circuits still had slow relay outcomes: health-aware selected
  slow-relay circuits `9` times, and plain load-aware selected slow-relay
  circuits `7` times.

Meaning: the default health-aware threshold can leave the selector on cold
zero-score assignment choices. That is a cause clue, not a fix.

The source now has a default-preserving lab knob,
`TORFAST_EXIT_SELECT_HEALTH_MIN_MOVE_SCORE_BPS`, with the old default kept at
`65536`. `results/browser-compare-20260608T002719/browser-compare.json` then
tested `TORFAST_EXIT_SELECT_HEALTH_MIN_MOVE_SCORE_BPS=16000` in a one-run debug
download-page check. It passed quality, but still rejected promotion.

- Base Arti load was `4689.826ms`.
- Local C Tor load was `3749.085ms`.
- Health-aware load was `6573.011ms`.
- Plain load-aware load was `4567.526ms`.
- The lower threshold changed the health-aware choice pattern: health-aware
  changed assignment `7` times, selected non-first `0` times, and median
  selected score was `17872.000`.
- It still selected slow-relay circuits `8` times and lost to base Arti by
  `1883.185ms` paired page load.

Meaning: lowering the cold-move threshold is useful as a lab probe, but is not
a speed fix. The next safe selector work should reject circuits that later show
slow relay tails, not promote this threshold.

## Next Decision

Do not patch path length or crypto. Keep normal exit-select width `1` as the
default. Wider exit-select values are lab-only because the stronger same-window
5-run, 3-target A/B did not confirm the earlier download-page win for width
`3`. The new load-aware open-circuit selector is promising, but still lab-only.
The broader same-window gate passed and improved median load, but one
load-aware download run had a `65953.543ms` max load. The focused
load-aware-plus-soft-timeout profile is promising, but its soft timeout did not
fire. The `1000ms` soft-timeout follow-up also did not fire and was slower by
median load. The `500ms` pending hedge is rejected again after the clean normal
gate `20260607T184844`: it was `1092.000ms` slower than base load-aware Arti by
median load, and its resource type rows were all worse. Earlier clean and debug
proofs also ruled out browser-facing SOCKS write lag and local outbound
client-to-Tor write delay for the reproduced slow groups. The broader
multi-target load-aware gate `20260607T185521` failed exact quality and exposed
a `52751.055ms` browser CONNECT phase on the download page. The first `500ms`
soft-timeout A/B also failed quality by causing early neterrors, so the source
now makes the final retry attempt wait normally. The fixed soft-timeout A/B
`20260607T191031` passed quality, but still lost to local C Tor on both focused
targets by median load. The retained-log diagnostic `20260607T192045` passed
quality and showed hostname CONNECT was immediate; the loss was response-to-DOM,
DOM-to-load, relay/resource tail, and HTTP/1.1 queue timing. It also counted
`0` soft timeouts. The corrected analyzer shows multiple eligible exit
candidates often existed, but select parallelism stayed `1` and slow tails
remained. The candidate-choice diagnostic `20260607T193855` added the missing
candidate assignment evidence: the selector alternated correctly when multiple
candidates existed, but the worst soft-timeout tail had only one eligible exit
circuit and reused it up to `5` assigned streams. The support-cause diagnostic
`20260607T194925` showed the main rejection reason was stream isolation:
fixed soft-timeout run 3 had max open total `9`, max rejected open `8`, and
max isolation rejects `7`. Same-isolation target `3` was the best lab shape at
that point after adding reuse-pressure gating: `20260607T204728` passed quality
and beat baseline Arti on the homepage and download page, with `9` top-ups and
`0` failures. But later low-log gates rejected target `3` and target `4` as
speed proof. Keep same-isolation capacity lab-only. Do not promote `500ms` soft
timeout, broad racing, or cross-isolation sharing. The latest focused replay
`20260607T214417` also rejects promoting
load-aware selection right now: it passed quality, but load-aware Arti was
`1904.365ms` slower than base Arti by median load. The latest spread-guardrail
lab `20260607T215932` also stays rejected: spread `2` passed quality and
activated `5` times, but was `735.496ms` slower than base Arti by median load.
The new per-circuit quality table shows spreading chose some low-throughput
circuits, and the run summary shows base Arti had none of those low-rate
circuits in this proof. Source inspection shows the current selector layer only
had eligibility/usability and `assigned_streams`, not relay throughput, RTT,
receive gaps, or first-byte health; the new `20260607T223225` proof confirms a
read-only circuit-health signal is now exposed and logged. The selected-vs-first
outcome table still warns against blind assignment balancing: in earlier proof,
the load-aware selector often moved away from candidate `0` onto a circuit that
later measured worse.
Local Arti source now exposes a read-only `CircuitHealthSnapshot` built from
incoming RELAY DATA cells and has a default-off health-aware lab selector that
can use it only inside the already eligible load-aware exit candidate set. This
is not a default change. The first health-aware browser proof passed quality and
showed the selector changes choices, but it was still slightly slower than plain
load-aware by median load. The latest stale-score guard proof is now faster than
base Arti, plain load-aware, and local C Tor in the focused download-page
window, but it stays lab-only because it is only a 2-run debug proof and run 1
still had low-rate and slow-relay circuits. The broader health-aware gate
`20260607T232339` is stronger: health-aware beat base Arti and plain load-aware
on all three target medians, and it was near local C Tor by page-only load. Keep
it lab-only until a larger low-log gate confirms the result and the remaining
low-rate or slow-relay circuits are reduced further. The larger low-log gate
`20260607T233909` did not confirm it: health-aware failed quality on the
download page with a browser connection failure, and its accepted download runs
were slower than base Arti, plain load-aware Arti, and local C Tor by median
load. Do not promote health-aware; get retained failure logs or add a reliability
guard before the next speed gate. The focused retained-runner check
`20260607T235651` passed quality but also rejected health-aware on speed:
health-aware was much slower than base Arti, plain load-aware Arti, and local C
Tor on the download page. The next retained-tail check `20260608T000334` was
less bad for health-aware and good for plain load-aware, but it still leaves
both selectors lab-only because low-log success tails did not expose enough
cause evidence and prior broader gates showed bad tails or quality failures.
The debug retained-tail check `20260608T000956` rejects the current selector
shape again: base Arti was faster than both health-aware and plain load-aware,
and the losses came from long relay/resource tails after first response, not
from browser connection prefs. The new score/span/age diagnostic check
`20260608T002242` showed default health-aware can still select zero-score cold
circuits. The lower-threshold lab `20260608T002719` avoided that pattern but
still lost to base Arti and kept slow-relay tails. Keep both selectors lab-only
and look for a relay-tail guard or selector rejection rule before another
promotion gate. The tightened bad-health guard later passed a repeated debug
gate, but the low-log `20260608T011500` 3-target gate found bad accepted-run
tails, so keep that guard lab-only too. The focused `20260608T013207`
same-isolation target `2` combination also passed quality but was much slower,
so do not combine those knobs as a fix. The focused `20260608T013809`
minimum assignment spread `2` check also passed quality but was slower than base
Arti and had a worse max-load tail, so do not use spread `2` as the next fix.
The failed-quality `20260608T014735` threshold check adds `32768` to the reject
list and does not prove `131072`; keep threshold tuning lab-only. The added
failed-run SOCKS table shows that the browser timeout was backed by ~60s Tor
relay waits, so the next source step should explain or reduce those long relay
waits without changing path quality.
The health-aware plus spread `4` lab profile is only a narrow clue: it improved
median download-page load in `20260608T174515`, but won only `1/2` direct A/B
pairs. The wider `20260608T175759` gate rejects it for promotion because it had
bad accepted tails on all three targets and a large homepage loss. The new
stream receiver risk table ties those accepted tails to `not_connected` stream
endings and long idle-after-last-data windows, so the next source target should
be slow stream ending or tunnel acquisition handling. The not-connected summary
shows base Arti has the same tail class on bad download runs, so the next fix
should be general, not selector-specific.
Do not retry preemptive count `3`; the source-patch run failed quality and the
runner-only lab flag made the homepage much slower.
Local Arti source now adds stream receive-window counters to the existing
low-log stream terminal summary: `read_events`, `sendmes`, `sendme_ok`,
`min_recv_window_after_take`, and `max_queued_after_bytes`. This is diagnostic
only and does not change stream windows, SENDME rules, circuit choice, browser
prefs, path length, or relay eligibility. The analyzer now carries those fields
through the terminal summary, terminal top-stream, and resource queue late-stream
tables. The rebuilt low-log proof
`results/browser-compare-20260608T193519/browser-compare.json` failed quality:
Arti hit `about:neterror?e=netTimeout` on the download page while local C Tor
loaded it. This is not speed proof. It is useful failure proof because all 3
failed Arti streams got partial Tor bytes and then idled for tens of seconds
before the browser timed out. Max relay time was `60295ms`, and max idle after
last Tor byte was `59006ms`. The new terminal counters point away from
receive-window/SENDME pressure for this shape: `sendmes=0`, min receive window
stayed at least `479`, and max queued stream bytes was only `2998`. The next
source work should inspect partial-response idle tails, stream close/circuit
health, and relay-tail handling before more selector or timeout promotion work.
Local Arti source now has a default-off, bounded partial-response idle close
lab knob, `TORFAST_SOCKS_PARTIAL_RELAY_IDLE_TIMEOUT_MS`, exposed by
`tools/run_browser_compare.py --arti-socks-partial-relay-idle-timeout-ms`. It
does not change default Arti behavior. The focused `4000ms` proof
`results/browser-compare-20260608T194844/browser-compare.json` passed quality
and fired `1` partial idle timeout, so the browser can still complete after one
early close. But it is not a speed win: Arti load was `10177.693ms` versus local
C Tor `4631.612ms`, and Arti boot+load was also slightly worse
(`17665.693ms` versus `17157.612ms`). Keep this lab-only and do not promote it.
The remaining slow shape is many resource streams ending around `8s` to `10s`
with browser queue delay, so the next source step should inspect why those
streams and the HTTP/1.1 resource queue stay slow after the first retry.
Local Arti source now emits low-log circuit congestion diagnostics for circuit
SENDMEs and scheduler hop blocks, and the analyzer reads per-run proxy tails
for those rows. The focused proof
`results/browser-compare-20260608T200133/browser-compare.json` passed quality
but again was not a speed win: Arti load was `9834.808ms` versus local C Tor
`5539.833ms`. The retained tail showed `29` circuit congestion events on
`Circ 3.3`, all `sendme sent`, with `0` scheduler blocks and `0`
`can_send=false` rows. That points away from Arti circuit send-window blocking
as the cause of this slow page. The same run still had one partial idle timeout,
six slow terminal resource streams, `57/57` stream SENDMEs OK, min receive
window `450`, and max stream data gap `1896ms`. The analyzer's low-log fallback
now fills the circuit-quality row from terminal summaries: `Circ 3.3` carried
`1412598` bytes across six streams at about `166.424 KiB/s`, with max relay
time `8780ms`. Keep the early-close knob lab-only. The next source step should
inspect relay/circuit quality or late data arrival on the selected circuit, not
scheduler blocking.
Local Arti source now has a default-off low-log selector context knob,
`TORFAST_EXIT_SELECT_LOW_LOG_CONTEXT`. The browser runner enables it only for
explicit SOCKS relay byte-timing proof runs. It prints the same open-circuit
candidate context at info level without changing circuit choice, isolation,
path length, relay eligibility, stream windows, or browser prefs. The focused
proof `results/browser-compare-20260608T202100/browser-compare.json` passed
quality. Arti loaded the download page in `3878.303ms` versus local C Tor
`4110.630ms`, and boot+load was much faster because Arti boot was `7.873s`
versus local C Tor `21.641s`. The new selector context showed no better-health
alternative for the late queued resource circuit: candidate context was
`*0:Circ 3.0:a0:s0:g0, 1:Circ 3.1:a0:s0:g0, 2:Circ 4.0:a0:s0:g0`. Circuit
quality rows showed `Circ 3.0` carried `1412359` bytes across seven streams at
about `398.860 KiB/s`, while tiny `Circ 3.2` carried `7851` bytes at about
`7.847 KiB/s`. The same proof had `54` circuit congestion events, `0`
scheduler blocks, and `0` `can_send=false` rows. This points away from a missed
healthy open circuit and away from local send-window blocking in this fast run;
the remaining visible cost is HTTP/1.1 resource queueing plus late relay data
arrival on the chosen circuit.
The separate FlowCtrl build proof
`results/browser-compare-20260608T204136/browser-compare.json` passed quality,
but it rejects FlowCtrl as the next default. The FlowCtrl profile did use Vegas
congestion control (`vegas:95` circuit congestion rows, with cwnd `124` to
`156`), while normal Arti stayed fixed-window (`fixed:31`). But normal Arti was
faster in the same window: normal Arti load was `3132.312ms`, FlowCtrl Arti was
`3801.270ms`, and local C Tor was `5302.438ms`. FlowCtrl also had slower
boot+load than normal Arti (`22025.270ms` versus `14640.312ms`) and a worse
HTTP/1.1 queue tail (`11` resources queued at least `1000ms` versus `7` for
normal Arti). Keep the FlowCtrl build and runner support for future proof, but
do not promote it from this result.
The rebuilt normal 3-target gate
`results/browser-compare-20260608T204644/browser-compare.json` is not accepted
as a speed proof because local C Tor timed out once on the homepage. It is still
useful state: normal Arti itself passed all `9/9` page loads. In that window
Arti beat local C Tor page-only on `check.torproject.org` (`1787.238ms` versus
`1853.591ms`) but lost on the homepage (`6309.196ms` versus `5095.070ms`) and
download page (`5641.471ms` versus `4471.761ms`). Arti won boot+load on all
three targets because boot was faster. This says the full exact-speed goal is
not stable yet.
The focused low-log byte-timing diagnostic
`results/browser-compare-20260608T205102/browser-compare.json` passed quality
on the two larger pages. In that window Arti beat local C Tor on page-only load:
homepage `3977.682ms` versus `50366.981ms`, and download `4992.648ms` versus
`5801.206ms`. Treat this as diagnostic, not final promotion proof, because it
used explicit relay byte-timing and local C Tor had a huge homepage tail. The
Arti queue rows still show HTTP/1.1 slot pressure and late data on selected
circuits. The worst Arti download run had `18` late queued resources tied to
`Circ 3.16`, max terminal data after queue `3244.717ms`, max terminal data gap
`592ms`, and min receive window `450`, so this still points away from local
SENDME/window starvation and toward resource queueing plus circuit/relay data
arrival variance.

The clean 3-target gate
`results/browser-compare-20260608T205724/browser-compare.json` passed quality
for both normal Arti and local C Tor. It is not an accepted speed proof:
Arti lost page-only median load on `check.torproject.org` (`2629.658ms` versus
`1566.568ms`) and the homepage (`6915.512ms` versus `4604.596ms`), while it won
the download page (`5058.995ms` versus `5543.050ms`). The bad Arti homepage run
had a large HTTP/1.1 queue tail on `Circ 2.45`, with up to `11466.896ms` queued
before request start and relay times over `10s`.

The same-window load-aware A/B
`results/browser-compare-20260608T210112/browser-compare.json` passed quality
but still does not promote load-aware selection. Load-aware was slower by
summary median load on all three targets, though it cut the worst base Arti
download tail from `65295.833ms` to `5934.092ms`. Treat it as tail-control
evidence only.

The focused soft-timeout A/B
`results/browser-compare-20260608T210541/browser-compare.json` passed quality
and soft5000 beat base Arti on the download page in all `3/3` paired runs:
paired median load delta `-646.322ms`, summary median load delta `-738.633ms`,
and max-load delta `-8199.727ms`. But the analyzer counted `0` soft timeouts,
so this is not proof that the soft-timeout mechanism caused the win. Keep it
lab-only until a run shows actual timeout firings without quality loss.

Local Arti source now gates circuit congestion SENDME/scheduler info logs behind
`TORFAST_CIRCUIT_CONGESTION_LOG=1`. This is a measurement cleanup, not a path or
relay-choice change. It keeps normal info-level speed gates from logging every
SENDME while preserving the diagnostic. Static proof
`results/arti-quality-config-20260608T211029/arti-quality-config.json` passed
with `36` checks. Rust `cargo check -p tor-proto -p arti --locked` passed, and
`scripts/build_arti_release.sh` rebuilt the release binary.

The default-off proof
`results/browser-compare-20260608T211244/browser-compare.json` passed quality on
`check.torproject.org` and had no `torfast circuit congestion` rows in the saved
result. Arti boot was `8.423s` versus local C Tor `11.752s`. The explicit
diagnostic proof `results/browser-compare-20260608T211322/browser-compare.json`
also passed quality and showed `torfast circuit congestion sendme` rows again
when `--arti-socks-relay-byte-timing` set `TORFAST_CIRCUIT_CONGESTION_LOG=1`.

The clean 3-target gate
`results/browser-compare-20260608T211630/browser-compare.json` passed quality
and is the strongest page-only proof so far, but it is not a complete win
because cold Arti boot was bad. Arti beat local C Tor on page-only median load
for all three targets: check `1070.479ms` versus `1546.388ms`, homepage
`4546.753ms` versus `4661.898ms`, and download `4141.062ms` versus
`4333.680ms`. But Arti boot was `30.436s` versus local C Tor `9.637s`. The new
boot directory summary counted `4` Arti directory failures, `3` directory
timeouts, `3` NOTDIRECTORY rows, and `4` partial responses. Local C Tor had no
directory failures in its measured boot. This makes cold directory/bootstrap
reliability the current blocker.

The warm-cache separation run
`results/browser-compare-20260608T212524/browser-compare.json` passed quality.
Arti measured boot from cache was `0.403s` versus local C Tor `2.751s`, so the
cache path is fast. Page-only speed was mixed: Arti won check
(`1689.501ms` versus `2006.831ms`) but lost the homepage (`6149.704ms` versus
`4904.120ms`) and download (`3708.379ms` versus `3341.372ms`). Because the
warm-cache page medians were noisy and mixed, do not claim final speed
completion. Keep the next work on cold directory reliability and large-page
tail stability.

The small cold repeat
`results/browser-compare-20260608T213014/browser-compare.json` passed quality on
`check.torproject.org` and did not repeat the 30s directory-failure boot. Arti
booted in `12.428s` versus local C Tor `14.026s`, and Arti page load was
`1205.358ms` versus local C Tor `1902.941ms`. Treat the earlier 30s boot loss
as real but transient. The analyzer now suppresses warning-only boot rows, so
harmless local C Tor permission warnings do not appear as directory failures.

The repeated cold boot-only proof
`results/boot-compare-20260608T133540/boot-compare.json` reproduced the cold
directory problem without browser page-load noise. Across three fresh boots,
default Arti had median boot `19.966s` versus local C Tor `14.591s`.
Arti succeeded every time, but `2/3` boots had directory failure signals:
`6` directory failures, `6` directory timeouts, and `6` partial responses.
Local C Tor had `0` directory failure signals.

The same-window directory-spread A/B
`results/boot-compare-20260608T134519/boot-compare.json` rejects
`TORFAST_DIR_SELECT_SPREAD=1` as a speed win. Default Arti median boot was
`12.153s`; dir-spread Arti median boot was `16.648s`; local C Tor median boot
was `20.815s`. Dir-spread had no directory failure signals in that window, but
it was `4.495s` slower than default Arti by median. Keep it lab-only and do not
promote it. Static proof
`results/arti-quality-config-20260608T220328/arti-quality-config.json` passed
`38` checks and confirms the dir-spread and incremental-microdescriptor paths
are default-off lab paths.

The first incremental microdescriptor bootstrap A/B
`results/boot-compare-20260608T135535/boot-compare.json` showed a possible
signal but not enough proof. `TORFAST_DIR_INCREMENTAL_MICRODESCS=1` marks the
directory usable as soon as enough microdescriptor responses have been applied,
instead of waiting for every parallel request to finish. In the 3-run window it
beat default Arti by median boot (`12.162s` versus `15.320s`) and logged
`torfast incremental microdescriptor fetch reached usable directory`, but it
still had one timeout run and a worse max boot (`30.993s` versus `28.907s`).

The wider 5-run incremental A/B
`results/boot-compare-20260608T140019/boot-compare.json` rejects incremental
microdescriptor bootstrap as a promotion candidate for now. Default Arti median
boot was `13.282s`; incremental median boot was `15.525s`; local C Tor median
boot was `18.560s`. Incremental reduced max Arti boot slightly
(`22.662s` versus `23.462s`) and reduced timeout counts, but it was slower by
median. Keep `TORFAST_DIR_INCREMENTAL_MICRODESCS=1` lab-only.

The directory read-timeout A/B keeps the normal Arti timeout at `10s` unless
`TORFAST_DIRCLIENT_READ_TIMEOUT_MS` is set. Static proof
`results/arti-quality-config-20260608T223350/arti-quality-config.json` passed
`39` checks, and release Arti rebuilt. The first 5-run boot proof
`results/boot-compare-20260608T141134/boot-compare.json` rejected `5000ms` as
too aggressive: median boot improved only from `14.317s` to `13.364s`, while
directory timeouts rose from `2` to `4`. The second 5-run proof
`results/boot-compare-20260608T141435/boot-compare.json` makes `8000ms` the
current lab-only boot candidate: default Arti median boot was `26.023s`, `8000ms`
median boot was `11.167s`, max boot improved from `28.018s` to `18.090s`, and
the `8000ms` profile had `0` directory timeout signals. Keep it lab-only until
a browser page-load gate proves it does not hurt normal browsing.

The first browser gate for the `8000ms` directory read timeout
`results/browser-compare-20260608T222249/browser-compare.json` passed quality
but rejects promotion. Default Arti boot was `18.452s`, local C Tor boot was
`13.573s`, and `arti_release_browser_dirread8000ms` boot was `44.296s` with
directory timeout/failure signals. Page-only load was mixed: `8000ms` was slower
on `check.torproject.org` (`2278.250ms` versus default Arti `1849.639ms`) and
faster on the homepage (`6068.182ms` versus default Arti `9762.499ms`), but
boot+load was much worse on both targets. Keep `TORFAST_DIRCLIENT_READ_TIMEOUT_MS`
as a lab diagnostic only, not a speed candidate.

Boot diagnostics are now sharper. `tools/run_boot_compare.py` saves a per-run
directory boot timeline with consensus attempts, certificate and microdescriptor
phase timing, usable-directory timing, first directory timeout, stream
terminal-summary transfer stats, and default-off `torfast dirclient timing`
request rows. `tools/analyze_browser_compare.py` now prints the same
`Boot Directory Timeline` for browser results. Static proof
`results/arti-quality-config-20260608T223906/arti-quality-config.json` passed
`40` checks and confirms the timing logs are default-off behind
`TORFAST_DIRCLIENT_TIMING_LOG=1`. On the rejected browser gate above, default
Arti reached microdescriptors at `2.000s` and usable directory at `18.000s`,
while the `8000ms` profile timed out at `9.000s`, retried consensus, reached
microdescriptors at `19.000s`, and became usable at `44.000s`.

The fresh boot-only proof
`results/boot-compare-20260608T143102/boot-compare.json` shows the cold boot
problem is intermittent, not constant. Default Arti had median boot `10.548s`
versus local C Tor `11.758s`, with `0` directory failure signals across `5/5`
runs. Default Arti's median microdescriptor phase started at `3.000s`, and
median usable-directory/proxy-functional time was `11.000s`. This means the next
speed work should not shorten the good path; it should identify and avoid the
bad retry/timeout path without changing Tor path quality.

The first 5-run timing-log boot proof
`results/boot-compare-20260608T144143/boot-compare.json` also stayed on the good
path. Default Arti median boot was `10.465s` versus local C Tor `10.599s`, with
`0` directory failures. It saved `110` directory client timing rows. Consensus
requests had median `1287ms` and max `1753ms`; authcert requests had median
`561ms`; microdescriptor requests had median `1136.5ms` and max `5154ms`.

The 10-run Arti-only timing proof
`results/boot-compare-20260608T144325/boot-compare.json` caught the bad path.
Arti still succeeded `10/10`, but `3/10` runs had directory signals, max boot
was `38.568s`, and the slow rows were microdescriptor downloads. Consensus was
not the tail: consensus median was `1312ms`, max `2956ms`. Microdescriptor
median was `1123ms`, p90-ish was `6284ms`, max was `11013ms`, and the timeout
rows were microdescriptor partial responses.

The 10-run default-vs-incremental timing proof
`results/boot-compare-20260608T144641/boot-compare.json` rejects incremental
microdescriptor promotion again. Default Arti median boot was `12.947s`;
incremental was `15.054s`. Incremental reduced max boot (`24.555s` versus
default `27.454s`) but had more directory timeouts (`9` versus `5`) and worse
median usable-directory time (`15.000s` versus `12.500s`). Keep the next source
idea focused on reducing large microdescriptor tail waits without returning
early in a way that hurts the normal median path.

Microdescriptor request-size testing is now default-off behind
`TORFAST_DIR_MICRODESC_IDS_PER_REQUEST`. Normal Arti keeps `500` IDs per
request when unset, and lab values are bounded from `64` through `500`. Static
proof `results/arti-quality-config-20260608T225832/arti-quality-config.json`
passed `41` checks. The 10-run `250` A/B
`results/boot-compare-20260608T150048/boot-compare.json` rejects smaller chunks
as a speed path: default Arti median boot was `14.849s`, `250`-ID chunks were
`19.292s`. The `250` profile cut median microdescriptor request size from about
`1.85MB` to `0.93MB` and reduced partial microdescriptor responses from `12` to
`4`, but it nearly doubled microdescriptor request rows (`200` to `399`) and
made usable-directory time worse. The 10-run `375` A/B
`results/boot-compare-20260608T150541/boot-compare.json` also rejects the idea:
default Arti median boot was `13.057s`, while `375`-ID chunks were `14.631s`.
Keep this as a lab diagnostic only.

Microdescriptor parallelism testing uses the official Arti config
`download_schedule.retry_microdescs.parallelism`; the default is `4`. The
10-run A/B `results/boot-compare-20260608T151034/boot-compare.json` rejects
higher parallelism for cold boot. Default Arti median boot was `13.322s`;
parallelism `6` was `17.229s`; parallelism `8` was `15.482s`. Parallelism `8`
also raised directory failures to `23` and directory timeout signals to `23`.
This means the next safe direction should avoid more simultaneous directory
requests and instead look for a way to avoid or replace only the slow
microdescriptor tail response.

Microdescriptor hedge testing is now available behind the default-off bounded
lab switch `TORFAST_DIR_MICRODESC_HEDGE_MS`. It starts a duplicate
microdescriptor request only after a request has already been slow for the
configured delay; consensus and cert requests are not hedged, and normal
document validation is unchanged. Static proof
`results/arti-quality-config-20260608T232103/arti-quality-config.json` passed
`42` checks. The 10-run A/B
`results/boot-compare-20260608T152310/boot-compare.json` rejects this idea for
speed: default Arti median boot was `11.055s`, hedge `7000ms` was `15.040s`,
and hedge `8000ms` was `21.303s`. Hedge `7000ms` started `20` backup requests
but only got `3` second clean responses; hedge `8000ms` started `36` backups
and raised partial microdescriptor responses to `15`. Keep this lab-only and do
not promote it.

The browser runner now supports same-window local SOCKS buffer A/B profiles
with `--extra-arti-proxy-buffer-size`. This changes only Arti's local
browser-facing proxy socket send/receive buffers; it does not change Tor path
length, relay choice, crypto, browser prefs, or directory behavior. The
warm-cache 3-run A/B
`results/browser-compare-20260608T233309/browser-compare.json` passed quality
with default Arti, `arti_release_browser_buf1mb`, and local C Tor. The `1 MB`
buffer profile helped the Tor Project homepage by median load (`4494.622ms`
versus default Arti `5004.984ms`, and local C Tor `4597.760ms`) but hurt the
small check page (`1319.338ms` versus default Arti `1133.558ms`, and local C Tor
`1200.742ms`). The analyzer flags the check-page profile as a promotion risk:
paired median slower, summary median slower, max tail worse, and only `1/3`
paired load wins. Do not promote `1 MB` local SOCKS buffers as a default.

The follow-up warm-cache 3-run A/B
`results/browser-compare-20260608T233953/browser-compare.json` tested smaller
local SOCKS buffers and also passed quality. It rejects `256 KB`: check-page
median load was `2026.564ms` versus default Arti `1128.755ms`, and homepage
median load was `14215.192ms` versus default `4480.588ms`. It also rejects
`512 KB` as a default despite a small check-page median win (`1005.126ms`
versus default `1128.755ms`), because homepage median was slower
(`4788.228ms` versus default `4480.588ms`) and the analyzer flagged low paired
wins on both targets. Local SOCKS buffer size is not the next speed path.

The fresh cold default browser gate
`results/browser-compare-20260608T234644/browser-compare.json` passed quality
with default Arti and local C Tor. This run points away from boot as the current
loss: Arti booted faster (`9.378s` versus local C Tor `10.608s`). Arti still
lost page-only load on both targets, with `1584.270ms` versus `1170.031ms` on
`check.torproject.org` and `4931.633ms` versus `4191.873ms` on
`www.torproject.org`. Paired load wins were `0/3` on both targets. The phase
delta points mostly to first response (`+450.009ms` on check, `+550.011ms` on
the homepage), plus a bad homepage resource queue tail where Arti max load was
`10617.560ms` versus local C Tor `5851.557ms`. The next bottleneck is page-load
response/tail behavior, not cold boot in this clean window.

The focused homepage byte-tap diagnostic
`results/browser-compare-20260608T235050/browser-compare.json` passed quality
and reproduced a larger Arti homepage tail. In that run the first page response
was close (`950.019ms` Arti versus `833.350ms` local C Tor), but DOM-to-load was
much worse (`8166.830ms` versus `1900.038ms`). The neutral tap and Arti relay
join showed the slow rows were not local proxy buffering: slow Arti resources
matched Tor-side relay delivery on a few circuits, with `Circ 4.1` and
`Circ 4.4` carrying many streams and relay times around `8s` to `10s`. This
points to eligible-circuit assignment and relay-tail behavior as the next page
load bottleneck.

The focused clean load-aware homepage A/B
`results/browser-compare-20260608T235305/browser-compare.json` passed quality
and showed the assignment signal can help page load. `arti_release_browser_loadaware`
beat default Arti and local C Tor on page-only median load: `3701.049ms` versus
default Arti `7036.249ms` and local C Tor `6118.898ms`. It won all `3/3`
paired page-load runs versus local C Tor and all `3/3` versus default Arti. It
also cut the worst Arti homepage tail from `15199.510ms` to `4989.029ms`.
Do not promote it yet: this is one focused homepage gate, older wider gates were
mixed, and this run's load-aware boot had directory timeout/failure signals
(`4` partial-response timeouts). The next proof needs a wider clean gate before
any default change.

The wider clean 3-target load-aware gate
`results/browser-compare-20260608T235720/browser-compare.json` passed quality
and rejects load-aware promotion again. Default Arti had a clean fast boot
(`7.394s`) and beat local C Tor on all three page-only medians:
`1923.510ms` versus `2009.526ms` on `check.torproject.org`, `4313.528ms`
versus `7986.082ms` on the homepage, and `3825.801ms` versus `7291.421ms` on
the download page. The load-aware profile won only the small check-page median
(`1605.102ms`), but lost to default Arti on the homepage (`7621.856ms`) and
download page (`7315.067ms`). It also had a bad cold boot (`34.334s`) with `4`
directory timeout/failure signals, plus large tails: check max load
`63519.342ms` and homepage max load `40296.525ms`. Keep load-aware lab-only.
The next proof should repeat default Arti versus local C Tor for stability,
because the current default Arti can win a wide window but earlier default gates
were mixed.

The repeat default-only 3-target gate
`results/browser-compare-20260609T000427/browser-compare.json` passed quality
and partly repeated the default Arti page-load win. Arti won the two larger
targets by page-only median: homepage `5212.137ms` versus local C Tor
`8755.032ms`, and download `4965.497ms` versus `6672.395ms`. Arti lost the
small check page narrowly (`2386.369ms` versus `2256.208ms`). But cold boot was
still not good enough: Arti boot was `25.279s` versus local C Tor `13.875s`.
The boot timeline had no directory failure rows, but it did include `6`
terminal summary rows and usable directory only at `25s`, so the final blocker
is now clearer: default Arti page-load behavior on larger pages is promising,
but cold directory/bootstrap stability and small-page consistency are not solved.

The progress-read timeout boot A/B
`results/boot-compare-20260608T161854/boot-compare.json` rejects
`TORFAST_DIRCLIENT_PROGRESS_READ_TIMEOUT_MS=2000` for speed. The switch is
default-off and bounded, and static proof
`results/arti-quality-config-20260609T001630/arti-quality-config.json` passed
`43` checks. But the 5-run boot proof was slower than default: default Arti
median boot was `12.603s`, while progress-read Arti was `16.225s`
(`+3.622s`). It reduced some directory signals (`5` failures and `4` timeouts
down to `3` and `3`), but it let slow trickle transfers run too long: max boot
rose from `18.882s` to `41.890s`, max directory-client elapsed rose from
`11698ms` to `24113ms`, and max terminal-summary transfer rose to `22446ms`.
Do not use progress-only body timeout as the next speed path.

The microdescriptor early-usable boot A/B
`results/boot-compare-20260608T163146/boot-compare.json` showed a strong
boot-only win for `TORFAST_DIR_MICRODESC_EARLY_USABLE_NOTIFY=1`. The switch is
default-off, microdescriptor-only, and uses Arti's existing
`Readiness::Usable` threshold while continuing to collect descriptor responses.
Static proof `results/arti-quality-config-20260609T002902/arti-quality-config.json`
passed `44` checks. In the 5-run boot gate, default Arti median boot was
`18.782s`, while early-usable was `10.598s` (`-8.184s`); max boot fell from
`52.960s` to `11.774s`, and directory timeouts fell from `14` to `0`.

The browser gate
`results/browser-compare-20260609T003557/browser-compare.json` passed quality
but rejects early-usable for promotion. In this same-window browser run, default
Arti booted faster than early-usable (`9.342s` versus `13.479s`) and early-usable
lost all three page-load medians against default: check page `2218.756ms` versus
`1496.021ms`, homepage `7234.602ms` versus `5431.091ms`, and download
`8548.647ms` versus `3729.406ms`. Keep the switch lab-only. The useful lesson is
that Arti's normal complete-directory path can already be fast in clean windows;
the next source path should reduce slow microdescriptor/source tails without
starting browser traffic from a worse in-flight directory state.

The repeat health-aware 3-target browser gate
`results/browser-compare-20260609T004224/browser-compare.json` passed quality
and shows page-load promise, but still rejects promotion. Health-aware Arti beat
default Arti on all three page-only medians: check page `1730.249ms` versus
`1878.593ms`, homepage `7214.344ms` versus `9065.350ms`, and download
`6033.579ms` versus `7854.276ms`. It also cut the default download max tail from
`24782.122ms` to `8264.520ms`. The bad part is launch-to-load: health-aware
boot was slower (`19.693s` versus default `10.740s`) with `4` directory timeout
signals, so boot+load was worse on every target. Health-aware also had a small
homepage max-tail risk (`9826.257ms` versus default `9369.906ms`). Plain
load-aware still had huge tails (`69987.266ms` homepage and `64854.625ms`
download). Keep both selectors lab-only; the next safe source path needs a
boot-stable, tail-aware rule before any default change.

The retry-only microdescriptor chunk experiment adds
`TORFAST_DIR_MICRODESC_RETRY_IDS_PER_REQUEST` as a default-off lab switch. It
keeps the first microdescriptor download attempt at Arti's normal grouping and
only changes request grouping after a prior download/add error when the current
missing set is all microdescriptors. Normal document parsing, storage, checksum,
and netdir validation stay unchanged. Static proof
`results/arti-quality-config-20260609T012503/arti-quality-config.json` passed
`45` checks, `cargo check -p tor-dirmgr --locked` passed, and
`cargo test -p tor-dirmgr --lib --locked` passed `45` tests.

The `250` retry-chunk boot gate
`results/boot-compare-20260608T170538/boot-compare.json` rejects `250`:
default Arti median boot was `13.401s`, while retry chunk `250` was
`23.181s` (`+9.780s`). It reduced max boot (`35.613s` to `26.621s`) but added
more directory signals: timeout rows rose from `8` to `12`, directory failures
from `8` to `13`, and signal runs from `2/5` to `4/5`.

The `375` retry-chunk boot gate
`results/boot-compare-20260608T170746/boot-compare.json` is the best boot clue
for this idea. Default Arti median boot was `20.662s`; retry chunk `375` was
`8.798s` (`-11.864s`). Max boot fell from `40.995s` to `17.490s`, directory
timeout rows fell from `17` to `0`, and max directory-client elapsed fell from
`14613ms` to `7424ms`.

The browser proof is mixed, so do not promote `375`. The first browser gate
`results/browser-compare-20260609T010947/browser-compare.json` failed quality
because local C Tor had one `check.torproject.org` proof failure, though both
Arti profiles completed. In that window, retry chunk `375` beat default Arti on
all three Arti page-load medians and booted faster (`6.793s` versus
`18.468s`), but its download max tail was worse (`23035.152ms` versus
`14017.752ms`). The repeat gate
`results/browser-compare-20260609T011415/browser-compare.json` passed quality,
but was still not promotion-ready: retry chunk `375` lost boot
(`14.279s` versus default `13.423s`) and check-page median
(`2303.546ms` versus `2042.498ms`). It did beat default on homepage
(`4478.759ms` versus `9041.498ms`) and download (`5412.131ms` versus
`9743.996ms`), but had a worse homepage max tail (`65466.623ms` versus
`11188.006ms`). That broad retry trigger stays rejected.

The signal-gated retry chunk version is safer, but still lab-only. The boot
gate `results/boot-compare-20260608T172658/boot-compare.json` was promising:
default Arti median boot was `8.214s`, while signal-gated `375` was `7.967s`;
max boot fell from `29.484s` to `9.890s`, timeout rows fell from `3` to `0`,
and directory failures fell from `5` to `2`. The browser gate
`results/browser-compare-20260609T012818/browser-compare.json` passed quality,
but mixed the speed result. Signal-gated `375` improved homepage load
(`4931.453ms` versus default `25898.841ms`) and download load
(`5431.368ms` versus `5973.184ms`), but lost boot (`25.013s` versus
`16.237s`) and check-page load (`1881.045ms` versus `1500.403ms`). Keep it
default-off until a repeat gate proves boot stays stable.

The clean current-state browser gate
`results/browser-compare-20260609T013711/browser-compare.json` failed quality
and exposed the next exact-quality blocker: default Arti had one
`check.torproject.org` timeout with no screenshot proof. The failed run showed
one onion connect delay (`4271ms`) plus three long relay tails, including two
hostname streams and one onion stream with no Tor-to-browser bytes for about
`115s` to `120s`. This is not a speed win; it is the failure shape the next
lab switch targets.

`TORFAST_SOCKS_NO_TOR_BYTE_RELAY_TIMEOUT_MS` is now available as a bounded,
default-off SOCKS relay diagnostic. It only runs when explicitly enabled, skips
onion streams, and only closes a non-onion relay after the browser has sent
bytes but Tor has sent no bytes back for the configured time. Static proof
`results/arti-quality-config-20260609T014903/arti-quality-config.json` passed
`46` checks. `cargo check -p arti --locked`, `cargo fmt --check -p arti`,
`scripts/build_arti_release.sh`, and the focused Python unit checks passed.

The focused check-page A/B
`results/browser-compare-20260609T015102/browser-compare.json` passed quality:
the `5000ms` no-byte-timeout profile beat default Arti on page load
(`1638.045ms` versus `1990.884ms`) and won `3/3` paired Arti-vs-Arti load
runs. The wider 3-target gate
`results/browser-compare-20260609T015405/browser-compare.json` also passed
quality and improved all three default-Arti medians: check page `2211.025ms`
versus `3081.375ms`, homepage `5690.553ms` versus `8465.674ms`, and download
`6205.269ms` versus `8602.927ms`. It beat local C Tor on download median
(`6205.269ms` versus `9799.749ms`) but still lost check page
(`2211.025ms` versus `1371.230ms`) and homepage (`5690.553ms` versus
`5365.632ms`). Do not promote it: no no-byte timeout event fired in either
clean pass, and the wider gate had one homepage max-tail risk (`12113.657ms`
versus default `11804.672ms`). This is safe-path evidence, not a proven stall
fix.

The runner now has same-window partial-idle extra profiles with
`--extra-arti-socks-partial-relay-idle-timeout-ms`, and the extra no-byte
profile count is included in the port-overlap safety check. This is harness
work only; it does not change default Arti behavior.

The focused homepage partial-idle gate
`results/browser-compare-20260609T020444/browser-compare.json` passed quality.
Partial-idle `5000ms` fired on hostname streams and the page still completed:
default Arti homepage median load was `15964.229ms`, no-byte `5000ms` was
`5930.159ms`, partial-idle `5000ms` was `6974.692ms`, and local C Tor was
`5774.569ms`. This was useful but not a promotion result: partial-idle still
lost to local C Tor page-only load and booted slower than default Arti
(`21.500s` versus `12.659s`).

The wider partial-idle gate
`results/browser-compare-20260609T021003/browser-compare.json` failed quality.
Default Arti had one download-page net timeout, and partial-idle had one
homepage net timeout. The failed partial-idle run showed a no-Tor-byte hostname
stall plus partial-idle timeout rows, including onion streams. That rejected
partial-idle as originally shaped.

After that failure, `TORFAST_SOCKS_PARTIAL_RELAY_IDLE_TIMEOUT_MS` was tightened
to skip onion streams, matching the no-byte timeout. Static proof
`results/arti-quality-config-20260609T021714/arti-quality-config.json` passed
`46` checks, Python compile passed, `107` Python unit tests passed,
`cargo fmt --check -p arti` passed, `cargo check -p arti --locked` passed, and
`scripts/build_arti_release.sh` rebuilt Arti `2.4.0`.

The tightened combo gate
`results/browser-compare-20260609T021908/browser-compare.json` passed quality
but rejects the combo. The base Arti profile had no-byte `5000ms`; the extra
profile added partial-idle `5000ms`, now non-onion only. The combo helped the
homepage versus no-byte-only (`8813.628ms` versus `14928.322ms`) but badly hurt
the download page (`68449.375ms` versus no-byte-only `14021.912ms` and local C
Tor `5878.197ms`). All partial-idle timeout events in that run were hostname
events, so the onion skip worked. The result still says no: partial-idle is a
diagnostic clue, not a speed path to promote.

`tools/analyze_browser_compare.py` now prints an `Arti Promotion Blocker
Summary` near the top of the report. On
`results/browser-compare-20260609T021908/browser-compare.json`, both Arti
profiles still show the same promotion blockers: boot directory trouble,
slower-than-C-Tor medians on all `3` targets, resource queue tails, slow onion
or data-gap streams, and slow hostname streams. The no-byte-only profile had
`21` directory failure signals, `6` queued runs, `8` slow onion streams, `54`
slow hostname streams, and max relay `85552ms`. The partial-idle combo had
`22` directory failure signals, `6` queued runs, `9` slow onion streams, `52`
slow hostname streams, and max relay `65110ms`. The next proof should be
stream-gap proof, not another idle timeout.

The focused neutral stream-gap proof
`results/browser-compare-20260609T023626/browser-compare.json` failed quality
and reproduced the slow shape without any timeout knob enabled. Arti boot was
fast (`7.489s`), but the homepage had one `120s` navigation timeout and the
download page had one net timeout. The failed homepage run had `14` relay-tail
streams: `13` hostname and `1` onion. Most hostname tails got no Tor bytes for
about `57s` to `59s`; the onion stream got some bytes and then idled for about
`55s`. This proves the next work must handle both no-byte hostname tails and
onion partial-data idle without force-closing onion streams.

The focused homepage no-byte A/B
`results/browser-compare-20260609T024437/browser-compare.json` passed quality
and improved page-only load in the same window: no-byte `5000ms` was
`3540.493ms` versus default Arti `6767.394ms`, winning `3/3` paired loads.
But it still is not promotable: boot got worse (`32.656s` versus `21.999s`),
boot+load got worse (`36196.493ms` versus `28766.394ms`), and no
`torfast socks timing no tor byte relay timeout` event appeared. Treat it as
evidence that no-byte hostname tails matter, not as a proven fix.

The stream-gap proof path now has lifecycle logging. `TORFAST_STREAM_LIFECYCLE_LOG`
is default-off and only enabled by the browser runner during
`--arti-socks-relay-byte-timing` proof runs. It logs stream id, relay command,
queue bytes, and delivery state (`sent`, `delivered`, `stream_gone`, or
`queue_full`), without hostnames or URLs. Static proof
`results/arti-quality-config-20260609T025559/arti-quality-config.json` passed
`46` checks. `python3 -m unittest tests.test_browser_quality
tests.test_arti_quality_config`, `cargo fmt --check -p tor-proto`, and
`cargo check -p tor-proto --locked` passed. The next browser proof should rerun
the neutral stream-gap case with relay-byte timing so the analyzer can print
`Torfast Stream Lifecycle` beside the SOCKS and relay-tail rows.

That rerun is now
`results/browser-compare-20260609T030206/browser-compare.json`. It failed
quality, which is useful proof. Arti booted faster than local C Tor (`9.359s`
versus `17.532s`) and was faster on the homepage median load among successful
runs (`3233.556ms` versus `7895.414ms`), but it had one homepage net timeout
and was much slower on the download page (`18455.563ms` versus local C Tor
`3926.500ms`). The new failed-run lifecycle table split the timeout into two
clear stream states: timing id `30` was a hostname stream with `BEGIN sent, no
CONNECTED`, no Tor bytes, relay `62857ms`; timing id `31` was an onion stream
with `DATA delivered, no EOF`, `3514` Tor bytes, then `57895ms` idle. There
were `0` `stream_gone` and `0` `queue_full` rows. So the next source target is
exit/stream completion or relay-side progress after BEGIN/DATA, not local
stream queue delivery.

The follow-up no-byte A/B
`results/browser-compare-20260609T031233/browser-compare.json` passed quality
but rejects no-byte as a fix. The no-byte profile had no timeout events, made
the homepage median load worse (`4115.376ms` versus default Arti `3823.454ms`),
and made the worst tail worse on both tested pages. It helped the download
median (`4951.935ms` versus `5892.335ms`), but that is not enough to promote
it. Keep no-byte lab-only. The next source target is still the stream or exit
progress after `BEGIN`/`DATA`, not local queue delivery and not another blind
timeout.

The next queue-proof rerun
`results/browser-compare-20260609T032922/browser-compare.json` passed quality
and captured outbound `channel_queued` lifecycle rows. Arti beat local C Tor on
homepage median load (`5601.930ms` versus `6868.130ms`) but lost the download
median (`9289.052ms` versus `7023.535ms`) and booted slower (`23.969s` versus
`10.702s`). The run had `134` channel-queued lifecycle rows, `0` stream-gone
rows, `0` queue-full rows, and max circuit-sender queue after send `0`. The
channel queue count was not available in the normal release feature set. That
proves no local circuit-sender backlog in this clean window, but it does not
prove the channel reactor queue was empty. The remaining blocker is still
stream/exit progress after the cell leaves the local client path.

The channel-flush smoke proof
`results/arti-channel-flush-smoke-20260608T195800/arti.log` used release Arti
with `TORFAST_STREAM_LIFECYCLE_LOG=1` and fetched `https://www.torproject.org/`
through Arti SOCKS with HTTP `200`. It captured `16621` stream lifecycle rows
and `1380` channel flush rows. The analyzer matched `915/915` stream
`channel_queued` rows with a `channel_circ_id` to later channel reactor flush
rows: median queue-to-flush gap `1ms`, max `2ms`, unmatched `0`. The reactor
queue depth counter was still unavailable in the normal release feature set,
but the timing proof points away from delay between circuit enqueue and channel
reactor output-sink acceptance. Stream response gaps in the same log were:
`23/24` queued BEGIN streams reached CONNECTED with median `152ms`, max
`188ms`; `23/24` queued DATA streams got DATA back with median `199ms`, max
`547ms`. The next bottleneck target is after channel output acceptance:
TLS/kernel, relay, exit, remote response/EOF timing, or browser-side resource
queueing in full browser runs.

The slow-stream lifecycle readout on
`results/browser-compare-20260609T032922/browser-compare.json` adds
`Notable Torfast SOCKS Stream Lifecycle`. It found `25` notable slow Arti SOCKS
streams: `18` relay-only slow, `6` connect-only slow, and `1` both. State split:
`16` `DATA delivered`, `1` `DATA delivered, no EOF`, `1` `CONNECTED delivered,
no DATA`, and `7` limited tail rows with only retained lifecycle proof. The
worst row was download run `2`, timing id `29`: hostname relay `34436ms`,
`7785` Tor bytes, and `33129ms` idle after the last Tor byte. That points more
at partial-response idle/EOF/resource-tail behavior than at local Arti queueing.

The partial-response idle follow-up
`results/browser-compare-20260609T041850/browser-compare.json` passed quality on
the download page, but the `4000ms` profile had no partial-idle timeout events.
Its median load was fast (`3488.816ms` versus default Arti `8581.738ms` and
local C Tor `8993.757ms`), so this is useful signal, not mechanism proof.

The shorter partial-response idle follow-up
`results/browser-compare-20260609T042353/browser-compare.json` passed quality
and proved the close path can fire without breaking this page. The `2000ms`
profile fired `2` partial-idle timeouts and loaded in `5216.123ms` median versus
default Arti `8967.295ms` and local C Tor `4565.604ms`. The `3000ms` profile
also fired `2` partial-idle timeouts and loaded in `4783.598ms`, winning `2/3`
paired page loads versus local C Tor with median delta `-617.433ms`. It reduced
max idle after last Tor byte from default Arti `21872ms` to `3178ms`. Keep this
lab-only: it is one target, C Tor was faster by summary median, and the same
profile had a cold-boot directory partial-response signal. The next safe source
work is to classify which partial-response tails are browser-abandoned resource
tails versus still-needed transfers, then close only the safe class.

The analyzer now prints `Torfast SOCKS Partial Idle Resource Context` for
timeout events. On `results/browser-compare-20260609T042353/browser-compare.json`,
the four timeout events had `0` exact browser-resource matches by timing id.
Nearest browser resources around the close time split into `2` `after_response`
and `2` `receiving` rows. The stricter active-resource count shows every timeout
also fired while the browser still had active resources: `14`, `8`, `14`, and
`5` active resources at the close moment, with waiting resources present in all
four rows and receiving resources present in three rows. That blocks a default
early close. The promotion tables now treat that as a first-class blocker:
both `2000ms` and `3000ms` profiles show `partial idle active resources`,
`2` partial-idle active closes, max active resources `14`, and next proof
`client-abandon proof`, even though their paired load deltas were faster than
default Arti. The same table now prints active-resource samples and max time
left after the close. These closes happened while resources still had up to
about `1059ms` left, including image, font, and SVG resources. The next source
step should first expose or infer a real browser/client-abandoned signal, then
apply any close only to that safe class.

The Arti lab timeout event now logs that missing client-abandon evidence at the
timeout moment: client EOF/error, Tor-to-browser write error/close error, and
Tor-to-browser bytes written. The analyzer prints this as `client abandon at
timeout`, with old logs shown as `unknown`. The next partial-idle replay should
use the rebuilt Arti binary and require `yes` before treating any close as safe.
Static guard `results/arti-quality-config-20260609T045234/arti-quality-config.json`
passed `47` checks and now requires those at-timeout fields.

The rebuilt-Arti replay
`results/browser-compare-20260609T045506/browser-compare.json` failed quality
because local C Tor had one `120s` browser navigation timeout, so it is not a
promotion gate. It still proves the new source field works. The `2000ms`
partial-idle profile fired `2` timeout closes and both showed `client abandon
at timeout = no` with `client EOF at timeout ms = 0`. Those same closes still
had active browser resources: `12` and `19`, with max active time left about
`567ms` and `1433ms`. The promotion tables now block this as both `partial idle
no client abandon` and `partial idle active resources`. They also block all
profiles in this failed replay with `baseline failed`, `baseline failures = 2`,
and next proof `clean baseline proof`, so the fast deltas cannot be treated as
a valid win against C Tor.

The clean follow-up
`results/browser-compare-20260609T050615/browser-compare.json` passed quality.
Default release Arti beat local C Tor on this one download-page gate: median
load `6115.255ms` versus `8221.188ms`, and paired load delta `-2105.933ms`.
No partial-idle timeout fired. The remaining promotion blockers are
none on this one target. The new resolved-close columns show `8` slow streams
closed in the same-close browser shape and `1` slow stream closed by client
reset plus an outbound END at the same moment. All `7` slow hostname streams
are same-close, and the only slow onion connect row is now classified as client
reset plus END, so unresolved slow streams are `0`. The resource queue blocker
also clears because Arti's queue shape is not worse than local C Tor on the
target-level delta: queued `>=1000ms` resources are `12` fewer, median
fetch-to-request is `533.344ms` lower, and max fetch-to-request is `616.679ms`
lower. The next proof is `broader A/B`, not the rejected broad timeout path.

`Arti Promotion Unresolved Slow Streams` now prints only stream-risk rows after
same-close and client-reset filtering. For the clean follow-up, it is empty.
The former unresolved row, download run `1` timing id `3`, is now classified as
client reset plus END: onion connect `3482ms`, relay `1219ms`, `3492`
Tor-to-client bytes, client-side `connection_reset` at `4702ms`, and outbound
END queued at `4703ms` on `Circ 3.3` / stream `43984`.

The broader A/B gate
`results/browser-compare-20260609T052706/browser-compare.json` passed quality on
three targets: `https://check.torproject.org/`,
`https://www.torproject.org/`, and `https://www.torproject.org/download/`.
Default release Arti won page-only median load on the Tor homepage and download
page, but lost badly on the check page: `6897.666ms` versus local C Tor
`1151.650ms` (`+5746.016ms`). Boot also lost: Arti booted in `22.878s` versus
local C Tor `10.545s` (`+12333ms`), so boot plus load is slower on all three
targets. Promotion blockers are now `boot slower`, `slower than C Tor`, and
`resource queue`. Slow stream quality is no longer a blocker because unresolved
slow streams are `0` after same-close, client-reset-plus-END, and remote-END
close shapes are classified as resolved. The next proof is `slow target proof`:
inspect the check-page path first, where Arti response start was `6033.454ms`
later than local C Tor.

The regenerated analysis now includes `Arti Promotion Slow Target Proof` for
that gate. The bad check-page run was run `1`: load `12607.764ms`, navigation
response start `11416.895ms`, and main-document wait after request start
`10450.209ms`. The navigation-matched SOCKS stream was timing id `2` with
relay `11526ms` and first Tor byte `10697.427ms` before browser response. The
worst stream in the same run was timing id `1`, lifecycle `DATA delivered, no
EOF`, relay `12990ms`, and `11588ms` idle after last data. This points the next
source proof at slow relay/remote-response timing on the check page, separate
from the boot-time blocker.

The focused check-page A/B
`results/browser-compare-20260609T054435/browser-compare.json` passed quality
with default Arti, health-aware Arti, health-aware plus bad-health guard, and
local C Tor. Default Arti beat local C Tor on page-only median load
(`1458.158ms` versus `1765.019ms`) but still lost boot plus load because boot
was `17.919s` versus local C Tor `14.581s`. Plain health-aware reduced the bad
Arti max page tail from `8474.244ms` to `2294.943ms`, but it is not a promotion
path yet: summary median load was slightly slower than default Arti
(`1526.596ms` versus `1458.158ms`) and boot was slower at `21.747s`. The
health-aware bad-health guard is rejected for this path: median load was
`2025.925ms`, max load was `19590.578ms`, and the promotion table found one
unresolved slow hostname stream. The analyzer queue gate was tightened after
this run so an `8ms` median queue noise delta no longer becomes a resource-queue
promotion blocker; the broader `052706` gate still has a real queue blocker
because its check-page max queue delta is `+416.675ms`.

The repeat boot proof
`results/boot-compare-20260608T215008/boot-compare.json` rejects the
microdesc retry chunk `375` experiment. Default Arti booted in `14.536s`
median, local C Tor booted in `12.758s`, and retry chunk `375` booted in
`16.899s`. The retry chunk also added `3` directory failures, `3` directory
timeouts, `3` partial responses, and a worse max dirclient elapsed time
(`11386ms`). Default Arti had no directory failure signals, but refreshed
timeline fields now show `8` circuit build failures, all `8` from channel-open
failure, with first failure at about `10s`. The slow default runs delayed
certificates and microdescriptors until about `12s`, after those channel
failures. The next boot proof should focus on the first directory
channel/tunnel setup and source reliability, not larger retry chunks.

The rebuilt Arti diagnostic proof
`results/boot-compare-20260608T220401/boot-compare.json` confirms the new
`usage_kind` field works in the release binary; static proof
`results/arti-quality-config-20260609T060154/arti-quality-config.json` passed
`47` checks. It ran `3` default-Arti boots with no local C Tor baseline: all
`3` succeeded, median boot was `8.785s`, and there were no directory failures
or timeouts. The slowest run was `15.950s` and had `1` circuit build failure,
`1` channel-open failure, and `1` `usage_kind="dir"` failure at `10s`; the two
faster runs had no build failures. That makes the next boot source proof
narrower: directory tunnel/channel setup can delay boot even when the directory
fetches themselves do not report failure.

The next rebuilt diagnostic proof
`results/boot-compare-20260608T221237/boot-compare.json` adds low-log channel
open timing from release Arti; static proof
`results/arti-quality-config-20260609T061037/arti-quality-config.json` passed
`48` checks. It ran `3` default-Arti boots with no local C Tor baseline: all
`3` succeeded and median boot was `8.140s`. The slow run was `19.431s`, but it
had no circuit build failures and no channel-open error. Its only channel-open
row was a successful `usage_kind="dir"` newly-created channel in `1172ms`; the
delay came later from `4` microdescriptor partial-response directory timeouts,
with max dirclient elapsed `12366ms`. The channel-open log now separates two
boot blockers: some windows have first directory channel-open failures, while
this window had directory body timeout/tail after a good channel open.

The fixed body-progress diagnostic proof
`results/boot-compare-20260608T222441/boot-compare.json` confirms the
directory body timing fields are real after correcting the diagnostic clock;
static proof `results/arti-quality-config-20260609T062250/arti-quality-config.json`
passed `48` checks. It ran `3` default-Arti boots: all `3` succeeded, median
boot was `7.861s`, max boot was `8.331s`, there were no directory failures or
timeouts, and all `66` dirclient timing rows reached body EOF. The max
dirclient elapsed was `2280ms`; max body first byte was `992ms`, max body last
byte was `2278ms`, max body read gap was `657ms`, and max body timeout-after-
last-byte gap was `0ms`. This is the clean baseline for the next timeout
capture: when a future microdescriptor timeout happens, the log will now show
whether the loss was before first byte, between body reads, or after last byte.

The wider body-progress capture
`results/boot-compare-20260608T222751/boot-compare.json` ran `8` default-Arti
boots with no local C Tor baseline. All `8` boots succeeded, median boot was
`9.252s`, max boot was `13.982s`, and no directory timeout happened. The old
timeout-after-last-byte shape did not repeat: max body timeout-after-last-byte
gap stayed `0ms`, with max body first byte `2038ms`, max body last byte
`3916ms`, and max body read gap `1287ms`. The only directory failures were a
different shape in run `1`: two microdescriptor requests got `NOTDIRECTORY`
before body bytes, produced `2` partial responses, and then Arti retried other
sources and still booted in `9.731s`. Run `4` was the slowest but clean, so the
next source target is bad directory-source retry/mark-failed behavior plus the
long body first-byte/read-gap tail, not channel open in this window.

The focused retry-chunk/body-timing proof
`results/boot-compare-20260608T223455/boot-compare.json` reran
`TORFAST_DIR_MICRODESC_RETRY_IDS_PER_REQUEST=375` against default Arti with the
new body timing fields. Both profiles had `5/5` successful boots, but retry
chunk `375` is still not clean enough to promote: it was only `0.232s` faster by
median (`9.327s` versus `9.559s`), while adding `2` circuit build failures, `3`
channel-open timing errors, `6` `NOTDIRECTORY` rows, and `2` partial responses.
It did remove the default profile's `4` directory timeout rows and cut max body
last byte from `11265ms` to `5874ms`, but the default slow run shows the real
timeout shape: four microdescriptor partial bodies on the same circuit kept
reading bytes until near the `10s` total timeout, with max timeout-after-last-
byte only `382ms`. That means the next source path should detect or replace
slow/truncated microdescriptor bodies from one source earlier, not promote
smaller retry chunks or an idle-after-last-byte timeout.

The new microdescriptor body cap lab switch
`TORFAST_DIRCLIENT_MICRODESC_BODY_MAX_MS` is now wired as a default-off bounded
diagnostic. It only applies to microdescriptor responses where Arti already
allows partial bodies; consensus and certificates keep normal behavior, and
normal document parsing/validation is unchanged. Static proof
`results/arti-quality-config-20260609T064708/arti-quality-config.json` passed
`49` checks. The first same-window boot A/B
`results/boot-compare-20260608T224426/boot-compare.json` rejects `7000ms`:
default Arti median boot was `8.062s`, while `7000ms` was `15.292s`
(`+7.230s`). The cap lowered max boot from `28.745s` to `18.809s` and capped
max body last byte at `7000ms`, but it added `9` directory timeouts, `9`
partial responses, and directory signals in `3/5` runs. Keep it lab-only. The
useful lesson is sharper: a plain elapsed cap cuts useful in-flight
microdescriptor bodies too often, so the next fix needs source/body health
replacement criteria, not just a shorter body clock.

The microdescriptor minimum body-rate lab switch
`TORFAST_DIRCLIENT_MICRODESC_MIN_RATE_BPS` is also wired as default-off and
bounded (`32768..262144` B/s). While wiring it, the directory body clock was
fixed so the normal `10s` body-read timeout, the lab body cap, and the new
minimum-rate check start at body-read start, not request start; slow headers no
longer spend the body budget. Static proof
`results/arti-quality-config-20260609T065856/arti-quality-config.json` passed
`50` checks. The corrected `98304` B/s boot A/B
`results/boot-compare-20260608T230100/boot-compare.json` is rejected for
promotion: it cut median boot from `18.677s` to `11.510s`, but added `4`
directory timeouts, `4` partial responses, and raised max boot from `22.329s`
to `25.301s`. The gentler `65536` B/s A/B
`results/boot-compare-20260608T230303/boot-compare.json` was clean on the
candidate side (`0` directory failures/timeouts/partials), but slower by median
(`14.009s` versus `12.645s`) and worse by max boot (`26.760s` versus
`21.488s`). Keep both thresholds lab-only; do not promote a minimum-rate cutoff
without a browser-quality gate and cleaner boot proof.

The microdescriptor retry-delay cap
`TORFAST_DIR_MICRODESC_RETRY_DELAY_MAX_MS` is now wired as another default-off
bounded lab switch (`250..2000ms`). It only runs after a microdescriptor
download attempt already had a real error and the remaining missing documents
are still microdescriptors; normal validation, storage, and path rules are
unchanged. Static proof
`results/arti-quality-config-20260609T070934/arti-quality-config.json` passed
`51` checks. The first 5-run A/B
`results/boot-compare-20260608T231150/boot-compare.json` rejects `500ms`:
default Arti median boot was `13.721s`, while the retry-delay cap median was
`15.415s` (`+1.694s`). Max boot was also slightly worse (`30.110s` versus
`29.864s`), and the candidate had more directory timeout rows (`5` versus `3`).
The cap only fired in `2/5` candidate runs, and both times it capped the normal
retry delay from `1000ms` to `500ms`; a `2000ms` cap would not have changed
this run. Keep it lab-only and do not pursue retry-delay capping as the next
promotion path.

The directory client timing rows now include a scrubbed `source_circ` field, for
example `Circ~2.0`, so repeated slow or partial microdescriptor bodies can be
grouped by circuit without logging relay identity. `tools/run_boot_compare.py`
now summarizes max same-source-circuit row, timeout, and partial counts. Static
proof `results/arti-quality-config-20260609T073120/arti-quality-config.json`
passed `51` checks. The focused 5-run default-Arti capture
`results/boot-compare-20260608T232537/boot-compare.json` confirms the next real
target: all `5/5` boots succeeded, but run `4` had `4` microdescriptor partial
timeouts on `source_circ="Circ~2.0"`, max body last byte `22197ms`, max read gap
`2146ms`, and boot time `32.828s`. The run summary counted max same-source
partial rows `4` and timeout rows `4`. This points away from body caps and
retry-delay caps; the next candidate should prevent several concurrent
microdescriptor requests from depending on one slow directory circuit/source, or
replace that source earlier, while keeping validation and path rules unchanged.

The microdescriptor early-retry-on-partial lab switch
`TORFAST_DIR_MICRODESC_EARLY_RETRY_ON_PARTIAL=1` is now wired as a default-off
microdescriptor-only diagnostic. It stops waiting for the rest of a
microdescriptor batch after the first partial `200` response, keeps the partial
body for normal parsing, and then lets the normal retry loop fetch the still
missing documents. Static proof
`results/arti-quality-config-20260609T074338/arti-quality-config.json` passed
`52` checks. The first 5-run A/B
`results/boot-compare-20260608T234014/boot-compare.json` rejects it: default
Arti median boot was `14.820s`, while early-retry-on-partial was `22.668s`
(`+7.848s`). The candidate kept `5/5` boots successful, but added `2`
directory failures, `1` directory timeout row, `3` `NOTDIRECTORY` signals, `2`
partial responses, and `1` warning. Keep this lab-only and do not promote early
batch cutoff.

The microdescriptor source-spread lab switch
`TORFAST_DIR_MICRODESC_SOURCE_SPREAD=1` is now wired as a default-off,
microdescriptor-only diagnostic. It asks `tor-dirclient` to use a distinct
`DirMicrodesc` circuit usage only for microdescriptor requests; that usage keeps
the same one-hop directory path and eligibility rules as normal directory
circuits, but picks the least-assigned eligible open directory circuit. Static
proof `results/arti-quality-config-20260609T075456/arti-quality-config.json`
passed `53` checks. The first 5-run A/B
`results/boot-compare-20260608T235159/boot-compare.json` is promising but not
safe enough to promote: median boot improved from `16.917s` to `13.296s`
(`-3.621s`), and median microdescriptor start improved from `4.000s` to
`3.000s`; however max boot worsened from `23.253s` to `33.123s`, directory
failures increased from `1` to `4`, directory timeouts from `0` to `4`, partial
responses from `1` to `4`, and max same-source timeout rows from `0` to `4`.
Keep it lab-only. The next source idea should preserve the median win while
preventing a one-circuit tail when only one usable microdescriptor directory
source is available.

The boot runner now also has
`--extra-arti-dir-microdesc-source-spread-early-usable`, which combines source
spread with Arti's existing early usable notification. The same parser now
reports the specific source-circuit label with the most timeout rows and the
specific label with the most partial rows, not only the largest total
source-circuit row count. Static proof
`results/arti-quality-config-20260609T075951/arti-quality-config.json` passed
`53` checks. The first combo A/B
`results/boot-compare-20260608T235958/boot-compare.json` rejects the combo as a
speed change: default Arti median boot was `9.986s`, while
source-spread-plus-early-usable median was `14.255s` (`+4.269s`). Both profiles
had `5/5` successful boots. The combo was cleaner on directory download signals
in this small run (`0` directory failures, `0` directory timeouts, `0` partial
responses), while default had one slow run with `4` timeout and partial rows on
`source_circ="Circ~2.0"`. But the combo added one circuit-build failure and was
slower by median, so keep it lab-only and do not promote it.

The microdescriptor pending-spread lab switch
`TORFAST_DIR_MICRODESC_PENDING_SPREAD=1` is now wired as a default-off
`DirMicrodesc`-only diagnostic. It is meant to test the pending-circuit
concentration path: when source-spread is active and a microdescriptor request
gets an already-assigned pending/open circuit while another unused eligible
directory circuit may still arrive, it skips that assigned circuit once and
keeps it as a fallback. It does not change document validation, directory
eligibility, or path rules. Static proof
`results/arti-quality-config-20260609T080825/arti-quality-config.json` passed
`54` checks. The first 5-run boot A/B
`results/boot-compare-20260609T001032/boot-compare.json` is promising but not
safe enough to promote: source-spread-plus-pending-spread median boot improved
from `13.701s` to `10.255s` (`-3.446s`), and both profiles had `5/5` successful
boots with `0` directory failures, `0` directory timeouts, and `0` partial
responses. But candidate max boot worsened from `17.010s` to `22.870s`, circuit
build failures rose from `2` to `3`, max body first byte worsened from `1323ms`
to `10139ms`, max body last byte worsened from `4336ms` to `15953ms`, and max
same-source rows rose from `13` to `22`. Keep it lab-only; the next source work
needs to preserve the clean median gain while reducing slow clean-body tails and
same-source concentration.

The boot runner now also has
`--extra-arti-dir-microdesc-source-spread-pending-spread-early-usable`, which
combines source spread, pending spread, and Arti's existing early usable
notification. Static proof
`results/arti-quality-config-20260609T085046/arti-quality-config.json` passed
`54` checks. The first 5-run boot A/B
`results/boot-compare-20260609T001539/boot-compare.json` is the strongest boot
proof for this source path so far: default Arti median boot was `16.786s`, the
combo median was `11.172s` (`-5.614s`), max boot improved from `32.615s` to
`17.377s`, and both profiles had `5/5` successful boots. Default Arti had `2`
directory failures, `2` partial responses, `6` `NOTDIRECTORY` signals, and `2`
warnings; the combo had `0` directory failures, `0` timeouts, `0` partial
responses, `0` `NOTDIRECTORY` signals, and `0` warnings. The combo also lowered
max same-source rows from `14` to `10` and circuit build failures from `2` to
`1`. This is still lab-only until browser gates repeat cleanly.

The first focused browser gate for that triple combo,
`results/browser-compare-20260609T081953/browser-compare.json`, passed browser
quality and kept Tor Browser prefs unchanged. It was also a strong same-window
win: default Arti boot was `19.616s`, the combo boot was `6.294s`, and local C
Tor boot was `14.673s`. Median page load was `1280.903ms` for default Arti,
`1166.404ms` for the combo, and `1264.869ms` for local C Tor. Boot plus median
load was `20896.903ms` for default Arti, `7460.404ms` for the combo, and
`15937.869ms` for local C Tor. The analyzer still asked for stream-gap proof
because both Arti profiles had slow onion probe streams with no full lifecycle
context.

The diagnostic browser replay
`results/browser-compare-20260609T082109/browser-compare.json` reran the same
gate with SOCKS relay byte timing and lifecycle logs. It also passed browser
quality. In this sample, default Arti booted faster (`6.503s`) than the combo
(`13.402s`), and the combo was slower by summary median page load
(`1338.561ms` versus `963.276ms`), though it still beat local C Tor page load
(`2495.332ms`). The stream-gap blocker was no longer unresolved: the slow onion
probe streams reached `CONNECTED delivered, no DATA` and closed locally with no
relay bytes, so they are not browser page-data stalls. This makes the combo
cleaner, but not promotable yet. Treat it as a promising boot candidate that
needs a wider browser A/B before any default-on decision.

The wider 5-run, 3-target browser A/B
`results/browser-compare-20260609T082814/browser-compare.json` rejects the
triple combo as a promotion path. It failed quality because default Arti had
one homepage failure, but the combo's own shape is also not safe enough: it had
`0` failures across all `15` page loads, but max load hit `40443.433ms` on
check and `65683.059ms` on download. The combo kept the faster boot
(`7.596s` versus default Arti `10.904s` and local C Tor `19.603s`) and won
boot+load against local C Tor on all three targets, but page-only median load
still lost to local C Tor on check (`1450.261ms` versus `1316.083ms`). The
download tail is too large for exact-quality speed work.

The focused diagnostic replay
`results/browser-compare-20260609T083656/browser-compare.json` reproduced the
bad shape with SOCKS relay byte timing. It failed quality on combo download run
`3`, timing out after `121682.818ms`. The failed run had `15` hostname relay
tails on one circuit (`Circ 4.14`), including timing id `39` with `90077ms`
relay time, `124617` Tor-to-client bytes, and `78591ms` idle after the last Tor
byte. This is a page-resource relay tail, not a directory boot issue.

The browser runner now also exposes
`--extra-arti-dir-microdesc-source-spread-pending-spread`, which tests source
spread plus pending spread without early usable notification. Focused A/B
`results/browser-compare-20260609T084334/browser-compare.json` shows removing
early usable does not fix the quality problem. The new no-early profile booted
in `16.116s` and beat local C Tor on check page-only load (`1096.788ms` versus
`1142.825ms`), but it failed one download run and lost download page-only
median to local C Tor (`5294.1845ms` versus `4388.279ms`). Keep both
source-spread profiles lab-only. The next useful work should target the
download page's relay/resource tail directly, not more directory early-usable
gating.

`tools/analyze_browser_compare.py` now prints
`Browser Failed Run Relay-Tail Circuit Concentration` after the relay-tail
detail table. This groups failed-run relay tails by circuit so the next work
can see whether one circuit owns the stuck resource work. On
`results/browser-compare-20260609T083656/browser-compare.json`, combo download
run `3` had all `15/15` relay tails on `Circ 4.14`: `12` streams had Tor bytes,
`3` had no Tor bytes, and max idle after the last Tor byte was `78591ms`. On
`results/browser-compare-20260609T084334/browser-compare.json`, default Arti
download run `2` had `21/24` relay tails on `Circ 3.14`; the no-early
source+pending failure split into three one-tail circuits. This keeps the
source-spread profiles lab-only and points the next patch at browser resource
tail circuit concentration, not boot directory timing.

`tools/run_browser_compare.py` now also has
`--extra-arti-dir-microdesc-source-spread-pending-spread-early-usable-load-aware`.
It starts one extra profile with the source-spread boot combo plus exit
load-aware selection, without changing the baseline Arti profile. The first
focused download-only A/B,
`results/browser-compare-20260609T090110/browser-compare.json`, passed quality
for all profiles. The old source-spread combo was best in that small sample:
median load `3113.566ms`, max load `5599.319ms`, boot `6.624s`. The new
load-aware combo had median load `4051.174ms`, max load `6025.671ms`, and boot
`9.690s`; it still beat local C Tor median load (`4161.839ms`) and boot+load,
but it was slower and had worse max load than the old source-spread combo.
Treat load-aware-on-top as not better from this proof.

The guarded repeat with `--arti-exit-select-min-assignment-spread 2`,
`results/browser-compare-20260609T090433/browser-compare.json`, also passed
quality but rejects that guard: default Arti median load was `4352.253ms`,
local C Tor was `4782.564ms`, the old source-spread combo was `5754.381ms`,
and the guarded load-aware combo was worst at `7384.016ms` with max load
`7834.186ms`. Do not promote the exit load-aware source-spread combo or the
spread-`2` guard from these proofs.

`tools/analyze_browser_compare.py` now also prints
`Browser Successful Run Relay-Tail Circuit Concentration`. This is proof-only:
it groups slow relay tails from completed browser runs by circuit, so accepted
max-tail regressions are visible without waiting for a page failure. The table
keeps the existing failed-run concentration table unchanged. Replaying
`results/browser-compare-20260609T090110/browser-compare.json` shows the new
source-spread-plus-load-aware profile had two accepted slow-tail clusters with
`2` hostname streams on one circuit, while the older source-spread combo only
showed one-stream accepted tails in that sample. Replaying
`results/browser-compare-20260609T090433/browser-compare.json` sharpens the
rejection: the guarded load-aware combo had `4` accepted slow hostname tails on
`Circ 3.9` in run `3`, while the old source-spread combo's accepted tails were
one stream per circuit. This keeps the next source target on resource-tail
circuit concentration, not another broad load-aware or spread guard.

Local Arti source now also records stream terminal idle tails into the local
circuit-health snapshot. A new bounded lab env var,
`TORFAST_EXIT_SELECT_BAD_HEALTH_STREAM_IDLE_MS`, can make the existing
bad-health guard treat a circuit as bad when a recent stream ended after a long
idle after the last Tor byte. This is default-off and does not change circuit
eligibility, path rules, relay choice, isolation, or browser prefs unless the
lab env var is set. Static proof
`results/arti-quality-config-20260609T092948/arti-quality-config.json` passed
`55` checks.

The first focused download-page browser proof for that terminal-idle signal,
`results/browser-compare-20260609T093222/browser-compare.json`, passed quality
with `--arti-exit-select-bad-health-stream-idle-ms 5000`, but rejects this knob
as a speed path. Default Arti median load was `4644.632ms`, the old
source-spread combo was `5260.104ms`, local C Tor was `3563.410ms`, and the
source-spread plus load-aware plus terminal-idle profile was worst at
`6240.065ms` median load with max load `7232.918ms`. The successful-run
relay-tail table still showed `6` accepted slow-tail rows for that profile,
with max relay `6725ms` and max idle after the last Tor byte `5028ms`. Keep the
terminal-idle health signal lab-only; it did not clear the resource-tail
problem.

Local Arti source now also records active stream counts on each client circuit.
A new bounded lab env var, `TORFAST_EXIT_SELECT_MAX_ACTIVE_STREAMS`, can keep
exit selection from placing a new stream on an already eligible open circuit
when that circuit is at the active-stream cap and another eligible open circuit
is below the cap. This is default-off and does not change circuit eligibility,
path rules, relay choice, isolation, DNS, or browser prefs unless the lab env
var is set. Static proof
`results/arti-quality-config-20260609T095109/arti-quality-config.json` passed
`56` checks.

The first focused download-page browser proof for the active-stream cap,
`results/browser-compare-20260609T095334/browser-compare.json`, passed quality
with `--arti-exit-select-max-active-streams 2`. In this small window, the old
source-spread combo was fastest by median page load (`3871.064ms`) and beat
local C Tor (`4984.858ms`); the source-spread plus load-aware combo also beat
local C Tor (`4699.432ms`). But this is not promotion proof. Local C Tor had a
large tail in this window, the source-spread combo still had a `10338.744ms`
max load, and retained relay-tail rows still showed slow hostname streams
clustered on single circuits. The logs showed active-stream fields for the
load-aware profile, but did not prove an active-cap move. Keep the active-stream
cap lab-only; next proof needs direct cap-move evidence and a wider A/B.

The runner now retains `torfast circuit selection` rows as compact signal
context even when stream lifecycle logs are large. Local Arti selection logs now
include both `selected_candidate_index_before_active_cap` and
`active_stream_cap_moved`, so the analyzer can count real active-cap moves.
Static proof `results/arti-quality-config-20260609T101530/arti-quality-config.json`
passed `56` checks.

The stronger active-cap proof
`results/browser-compare-20260609T101308/browser-compare.json` passed browser
quality with `--arti-exit-select-max-active-streams 1`. It proved the cap can
move real exit selections: default Arti had `23` active-cap exit picks and `2`
moves, the source-spread combo had `23` picks and `10` moves, and the
source-spread plus load-aware combo had `22` picks and `1` move. But this still
does not promote the cap. The source-spread combo beat local C Tor by median
page load in this small window (`3550.874ms` versus `3885.907ms`), but all Arti
profiles still had resource-queue blockers, the load-aware combo was much
slower (`6593.344ms` median load), and accepted slow-tail rows still clustered
on single circuits. Keep active-cap selection lab-only; the next safe work is
to handle the no-under-cap case where every eligible open circuit is already at
or above the active cap.

Local Arti selection now handles that no-under-cap case too. When
`TORFAST_EXIT_SELECT_MAX_ACTIVE_STREAMS` is set and every already eligible open
exit circuit is at or above the cap, the lab code chooses the least-active
already eligible circuit instead of staying on the first selected capped
circuit. It still does not change path rules, relay choice, isolation, DNS, or
browser prefs. Selection logs now also include `active_stream_cap_saturated`,
and the analyzer reports saturated counts. Static proof
`results/arti-quality-config-20260609T104117/arti-quality-config.json` passed
`56` checks.

The focused saturated-fallback browser proof
`results/browser-compare-20260609T102258/browser-compare.json` passed quality
with `--arti-exit-select-max-active-streams 1`. It proved saturated cases in
real exit selection: default Arti had `22` active-cap picks, `6` moves, and
`12` saturated cases; source-spread had `21` picks, `7` moves, and `11`
saturated cases; source-spread plus load-aware had `23` picks, `1` move, and
`11` saturated cases. Do not promote it. Default Arti's raw median page load was
slightly better than local C Tor (`3817.971ms` versus `3945.040ms`), but paired
median load delta was still `+328.380ms`, boot+load was slower, source-spread
regressed to `5583.030ms`, and load-aware regressed to `6172.805ms`. Slow
hostname tails and resource-queue blockers remain. Keep the saturated fallback
lab-only; the next safe work should explain and reduce the page resource queue
without changing Tor path or privacy rules.

`tools/analyze_browser_compare.py` now de-duplicates repeated same-isolation
top-up log rows by `pending_id` and extends `Arti Profile Same-Isolation Top-Up
A/B` with `built runs`, `used runs`, and `missing lifecycle runs`. This is
proof-only. Replaying `results/browser-compare-20260608T062521/browser-compare.json`
now shows the old sameiso2 and prefer-cold top-up attempt rows had `0` built
runs, `0` used runs, and only missing lifecycle rows in the retained proof.
That old attempt/no-attempt split did not prove extra top-up capacity helped.

The focused retained download proof
`results/browser-compare-20260609T103420/browser-compare.json` passed quality.
`arti_release_browser_healthaware_avoidbadhealth_sameiso2_prefercold` made `1`
same-isolation top-up attempt, but had `0` built runs, `0` used runs, and `1`
missing lifecycle run. The profile still beat baseline Arti in `2/3` paired
loads and cut max load (`5097.107ms` versus `7287.177ms`), but its summary
median was only noise-better/worse versus baseline (`+34.894ms`) and it was
still slower than local C Tor by paired median load (`+512.330ms`). Do not
promote it; this points away from top-up capacity and toward cold-candidate
selection.

The selection-only follow-up
`results/browser-compare-20260609T103700/browser-compare.json` passed quality
with `--arti-exit-same-isolation-min-assigned-streams 8`, so the sameiso2
prefer-cold profile made `0` top-ups. In this one download-page window it beat
baseline Arti in `3/3` paired loads, improved paired and summary median load by
`-1637.684ms`, and cut max load from `8317.983ms` to `4965.125ms`. This is a
promising clue, not promotion proof: local C Tor had a bad same-window tail
(`7548.193ms` median load, `21219.058ms` max load, `38.641s` boot), and this was
only one target with three runs. Next proof should repeat selection-only
prefer-cold across check, homepage, and download before changing any default.

That wider repeat is
`results/browser-compare-20260609T104252/browser-compare.json`. It passed
quality, but rejected the idea for promotion. The sameiso2 prefer-cold profile
was slower than baseline Arti on the homepage and download page by paired median
load (`+1017.165ms` and `+5231.706ms`), and the download max tail regressed badly
(`39195.816ms` versus `6278.899ms`). It also still emitted `1` same-isolation
top-up attempt at the exact `8` assigned-stream floor, with `0` built runs,
`0` used runs, and `1` missing lifecycle run. Keep this lab-only; next work
should explain the slow page-resource queue and make the same-isolation floor
strict before any more cold-candidate tests.

The same-isolation top-up floor is now strict in source:
`selected_assigned_streams > torfast_exit_same_isolation_min_assigned_streams()`.
The direct Rust unit test `same_isolation_topup_waits_for_reuse_pressure` passed:
assigned-stream count `2` at the default floor no longer top-ups, while `3`
does. Static proof `results/arti-quality-config-20260609T111042/arti-quality-config.json`
passed `56` checks. A stale-binary rerun
`results/browser-compare-20260609T105226/browser-compare.json` still showed the
old exact-floor `8` top-up, which proved the release binary had not been rebuilt.
After `scripts/build_arti_release.sh`, the rebuilt runtime proof
`results/browser-compare-20260609T110147/browser-compare.json` passed quality.
It made `1` same-isolation top-up only at `9` assigned streams with floor `8`,
so the exact-floor leak is fixed. Do not promote sameiso2 prefer-cold: it
improved download paired median load by `-2042.580ms`, but regressed homepage by
`+4556.186ms` and still had a homepage promotion risk.

`tools/analyze_browser_compare.py` now prints `Arti Profile Queue Loss Reason`
for candidate A/B rows where load and browser resource queue both regress. On
`results/browser-compare-20260609T110147/browser-compare.json`, the new table
pins the sameiso2 prefer-cold homepage loss to a queue regression, not a clean
selector win/loss: paired load delta was `+4556.186ms`, median queued `>=1000ms`
delta was `+16`, median max queue delta was `+1550.031ms`, and the worst queued
run lost by `+5327.003ms`. That worst run's selected queue circuit was
`Circ 3.12` with context `*0:Circ 3.12:a1:s8711.000:g529.000`, `0`
better-health alt rows, and `0` lower-assignment alt rows. This says the next
safe work is single-circuit page-resource queue diagnosis, not more
cold-candidate preference tuning.

The analyzer now also prints `Arti Profile Queue Loss Mechanism`, which joins
that loss row to the late-write and circuit summaries. On the same
`20260609T110147` proof, the homepage loss had `19` high-confidence queued rows,
`16` writes still `>=1000ms` after queue, and `16` terminal last-data rows still
`>=1000ms` after queue on `Circ 3.12`. Terminal pending bytes stayed `0`,
SENDMEs were `445/445`, min receive window was `450`, and max write after
terminal data was `0ms`. The table therefore labels the loss as late Tor data
with no local pending/window block. Next work should inspect why one circuit's
terminal data stayed late for page resources.

To test whether active-stream caps help that exact sameiso2 prefer-cold loss,
the runner now has
`--extra-arti-exit-select-prefer-cold-same-isolation-active-cap TARGET:CAP`.
It creates an extra same-window health-aware avoid-bad-health same-isolation
prefer-cold profile with only that profile's active-stream cap set, leaving
baseline Arti unchanged. Parser/unit proof passed, and static source/config
proof `results/arti-quality-config-20260609T114333/arti-quality-config.json`
passed `56` checks.

The focused proof is
`results/browser-compare-20260609T113311/browser-compare.json`. It passed
browser quality for all non-skipped profiles and kept browser prefs unchanged,
but rejects active-cap sameiso2 prefer-cold as promotion proof. Versus baseline
Arti, `arti_release_browser_healthaware_avoidbadhealth_sameiso2_prefercold_activecap1`
won download by paired median load (`-456.909ms`, summary `-443.078ms`) and cut
the old prefer-cold download loss, but it still lost check (`+833.840ms` paired,
`+1416.802ms` summary) and homepage (`+2327.441ms` paired, `+1926.950ms`
summary). It also had a homepage queue-loss row: median queued `>=1000ms` delta
`+10`, median max queue delta `+2150.043ms`, worst-run queue circuit
`Circ 3.29`, and mechanism `late Tor data, no local pending/window block`.
Circuit-selection proof says the active-cap profile had `55` active-cap picks,
`0` active-cap moves, and `37` saturated cases, so cap `1` did not actually
move selections in this window. Keep it lab-only; next work needs a rule that
can act in saturated same-isolation page loads, or a lower-level fix for late
terminal data on one circuit.

Local Arti source now has a bounded saturated active-cap top-up variant for the
sameiso prefer-cold lab path. When active-stream cap selection reports all
same-isolation candidates saturated, top-up may use `target + 1`, capped at the
normal max target plus one. This is still default-off and lab-only: path rules,
isolation rules, and browser prefs are unchanged. Static proof
`results/arti-quality-config-20260609T120202/arti-quality-config.json` passed
`56` checks.

The same-window proof is
`results/browser-compare-20260609T115220/browser-compare.json`. It passed
browser quality and kept default browser prefs unchanged. Versus baseline Arti,
`arti_release_browser_healthaware_avoidbadhealth_sameiso2_prefercold_activecap1`
won download by paired median load (`-3074.228ms`, summary `-2042.835ms`), but
lost check (`+863.064ms` paired, `+863.064ms` summary) and homepage
(`+1469.777ms` paired, `+689.345ms` summary). Circuit-selection proof counted
`41` active-cap picks, `7` active-cap moves, and `28` saturated cases, but `0`
same-isolation top-ups and `0` active-cap saturated top-ups. Keep this lab-only:
the active cap helped download in this window, but it did not fix check/homepage
and the saturated top-up path still needs a run where it actually fires.

The lower-floor proof
`results/browser-compare-20260609T120503/browser-compare.json` reran the same
shape with `--arti-exit-same-isolation-min-assigned-streams 4`. It did make the
saturated path fire: activecap1 counted `6` same-isolation top-ups, all `6`
with `active_stream_cap_saturated=true`; the non-activecap prefer-cold profile
counted `4` top-ups. But this is rejection proof, not promotion proof. The full
gate exited nonzero because baseline Arti had one download failure, and
activecap1 still showed a bad speed risk: versus baseline Arti it lost download
by `+5601.995ms` paired median load (`+6186.542ms` summary) with max tail
`+68825.639ms` and a `72201.249ms` candidate max load. The analyzer also marked
all top-up lifecycle rows as `missing`, meaning the extra circuit did not become
usable in time for the page load. Keep floor `4` rejected; the next useful work
is not more same-isolation floor tuning, but earlier avoidance of late
single-circuit data or a different way to make extra capacity usable before the
resource burst.

Local source then moved the active-cap pressure check earlier. The sameiso
top-up gate now treats `active_stream_cap_saturated` plus
`selected_active_streams >= cap` as reuse pressure, so the lab-only top-up can
start before the assigned-stream floor when the active cap is already full.
This is still default-off and bounded, and it does not change path rules,
isolation rules, or browser prefs. Static proof
`results/arti-quality-config-20260609T122405/arti-quality-config.json` passed
`56` checks.

The rebuilt browser proof is
`results/browser-compare-20260609T122640/browser-compare.json`. It passed
quality and prefs, and proved the new gate fired: activecap1 counted `9`
same-isolation top-ups, all `9` active-cap saturated, with max selected active
streams `2` and cap `1`. It is still rejection proof. All top-up lifecycle rows
were `missing`, so the extra circuit still was not usable before the page
resource burst. Versus baseline Arti, activecap1 lost check by `+922.914ms`,
homepage by `+3389.940ms`, and download by `+2310.709ms` paired median load.
The better lead from this window is plain `healthaware_avoidbadhealth`: it won
homepage by `-734.434ms` and download by `-605.680ms`, but lost check by
`+394.294ms`. Next work should stop tuning sameiso active-cap top-up and either
investigate that health-aware-only lead or the late Tor-data cause.

The wider health-aware-only repeat
`results/browser-compare-20260609T123806/browser-compare.json` passed browser
quality, but rejected promotion. It won check by paired median load
`-210.281ms`, but lost homepage by `+187.148ms` with max-tail delta
`+28174.935ms`, and lost download by `+1636.365ms`. The homepage max load was
`36480.399ms`. The queue loss still looked like late Tor data with no local
pending/window block. Selector-only health awareness is not enough.

Local source now also has a default-off first-stream same-isolation prewarm
lab switch. The env is `TORFAST_EXIT_SAME_ISOLATION_PREWARM_FIRST_STREAM`, the
runner flag is
`--extra-arti-exit-select-prefer-cold-same-isolation-prewarm-target`, and the
analyzer reports `topup first-stream prewarm`. Static proof
`results/arti-quality-config-20260609T125441/arti-quality-config.json` passed
`56` checks, and focused unit/build checks passed.

The browser proof
`results/browser-compare-20260609T125803/browser-compare.json` failed quality.
The candidate
`arti_release_browser_healthaware_avoidbadhealth_sameiso2_prefercold_prewarmfirst`
timed out homepage run `3` at `121487.242ms`, so screenshot proof was missing.
It made `3` same-isolation top-ups, including `1` real first-stream prewarm,
but all `3` lifecycle rows were `missing`. Keep this rejected and lab-only.
Starting the extra circuit at first stream still did not make capacity usable in
time; next work should explain why top-up builds do not finish or appear before
use, or use a different design for usable parallel capacity.

Local source and analyzer now fix that proof gap. Same-isolation top-up build
lifecycle rows are forced to `info` for lab top-up plans, so future runs should
show build complete/failed/canceled even when the build is faster than `5000ms`.
Static proof `results/arti-quality-config-20260609T132017/arti-quality-config.json`
passed `56` checks, `128` Python tests passed, `cargo check -p tor-circmgr`
passed, and the rebuilt release Arti binary still reports `Arti 2.4.0`.

The analyzer also now labels old hidden-build evidence as
`candidate_seen_no_build_log` when a new zero-assigned same-isolation candidate
appears after a top-up. Replaying
`results/browser-compare-20260609T125803/browser-compare.json` keeps the run
rejected, but corrects the mechanism: the check top-up still has `missing`
lifecycle proof, while homepage run `3` saw `Circ 3.27` after top-up without a
build-complete log. The small sanity proof
`results/browser-compare-20260609T131341/browser-compare.json` passed quality
and prefs, but made `0` top-ups, so it is only a no-regression run. Next proof
should rerun a top-up-firing shape with the new forced-info lifecycle logs.

The top-up-firing repeat with the new lifecycle logs is
`results/browser-compare-20260609T132248/browser-compare.json`. It passed
browser quality and kept prefs unchanged. The new proof rows worked: sameiso2
prewarmfirst made `2` top-ups, both built fast (`517ms` and `615ms`), with `0`
build failures and `0` missing lifecycle rows. One top-up was selected later on
the download page; the homepage top-up built but was not selected again in the
retained rows.

This is useful but still not promotion proof. Versus baseline Arti, the
candidate lost check by `+65.142ms` paired median load and had a worse check
max tail by `+930.432ms`. It won homepage by `-1521.870ms` paired median load
and download by `-4791.892ms`, cutting the baseline download max tail from
`67106.386ms` to `6155.415ms`. Versus local C Tor medians, it was faster on the
homepage by `-349.161ms`, but slower on check by `+118.779ms` and slower on
download by `+872.720ms`. Promotion blockers remain `slower than C Tor` and
`resource queue`. The next source work should keep the top-up lifecycle proof,
but solve the check regression and avoid using this heavy selector/top-up shape
where it cannot help.

The light selector follow-up is
`results/browser-compare-20260609T133530/browser-compare.json`. It added only a
runner profile, not a source behavior change:
`--extra-arti-exit-same-isolation-prewarm-target 2` starts
`arti_release_browser_sameiso2_prewarmfirst` with same-isolation target `2` and
first-stream prewarm, but without load-aware, health-aware, avoid-bad-health,
or prefer-cold selection. Browser quality passed and Tor Browser prefs stayed
unchanged.

This proof is useful but still lab-only. The light profile made `4`
same-isolation top-ups, all `4` built (`764ms`, `1381ms`, `923ms`, `1338ms`),
with `0` failures and `0` missing lifecycle rows. None of the built top-up
circuits was used by retained streams. Median load versus baseline Arti was
`+372.627ms` on check, `-750.062ms` on the homepage, and `-22762.675ms` on
download. Versus local C Tor median load, it was nearly tied on check
(`+6.710ms`) and faster on homepage/download (`-4661.543ms`,
`-4868.005ms`). The blocker is boot: `32.815s`, which is `+16.221s` slower
than baseline Arti and `+17.136s` slower than local C Tor. Keep the runner
profile for proof, but do not promote it until boot is fixed and a built top-up
is actually used.

The proof tooling now keeps filtered boot signal lines separately from the
noisy boot log tail. `tools/run_browser_compare.py` stores `boot.signal_lines`,
and `tools/run_boot_compare.py`/`tools/analyze_browser_compare.py` use those
lines for the Boot Directory Timeline when present. This matters because
`--arti-socks-relay-byte-timing` can fill the old `boot.lines[-80:]` tail with
stream lifecycle rows and hide the directory phase that made boot slow.

The small fresh proof with the new boot signals is
`results/browser-compare-20260609T135043/browser-compare.json`. It passed
browser quality and prefs. The new signal field worked: baseline Arti kept
`10` boot signal rows, light sameiso prewarm kept `10`, and local C Tor kept
`20`. This run also shows the earlier `32.815s` boot blocker was not stable:
light sameiso prewarm booted in `12.740s`, near local C Tor at `12.581s`.

The profile is still rejected. On a one-run check/download sanity proof,
`arti_release_browser_sameiso2_prewarmfirst` was only `+23.799ms` slower than
baseline Arti on check, but lost download by `+8754.013ms` paired load. It made
one top-up, which built in `754ms`, but retained streams still did not use it.
The analyzer labels the download loss as `single selected circuit queue` /
`late Tor data, no local pending/window block`. The practical lesson is that
same-isolation prewarm alone can build capacity, but normal selection still may
not use that capacity; do not promote without a selector design that avoids the
old check/tail regressions.

The load-aware light-prewarm follow-up is
`results/browser-compare-20260609T135829/browser-compare.json`. It adds only a
runner profile,
`--extra-arti-exit-load-aware-same-isolation-prewarm-target 2`, creating
`arti_release_browser_loadaware_sameiso2_prewarmfirst`. This keeps
same-isolation target `2` plus first-stream prewarm, turns on load-aware
selection, and leaves health-aware, avoid-bad-health, and prefer-cold selection
off. Browser quality passed and Tor Browser prefs stayed unchanged.

This proof is useful but rejected. The profile finally used one built top-up:
the retained lifecycle row built in `615ms`, was later selected on homepage run
`3`, and `used_by_streams` was true. But the user-facing result was still bad.
Versus local C Tor median load it lost check by `+353.989ms`, homepage by
`+286.023ms`, and download by `+3582.929ms`. Versus baseline Arti it only won
homepage by `-255.569ms`, while losing check by `+535.925ms` and download by
`+1519.945ms`. The worst tails were also worse: check max load `8998.789ms`
and homepage max load `28467.569ms`. Keep this as proof that load-aware can
use prebuilt capacity, but do not promote it; the selected extra circuit can
still produce slow page tails.

The stricter bad-health-gated repeat is
`results/browser-compare-20260609T140545/browser-compare.json`. It used the
same runner profile plus `--arti-exit-same-isolation-require-bad-health`, so a
same-isolation top-up could only be added after the selected circuit had bad
local health. Browser quality passed and Tor Browser prefs stayed unchanged.

This is also rejected. The profile won check versus local C Tor by
`-1130.888ms` median load, but lost homepage by `+720.244ms` and download by
`+6405.873ms`. Versus baseline Arti it won check by `-871.686ms` and homepage
by `-3525.226ms`, but lost download by `+4052.894ms`. It made one top-up on
download run `2` after the selected circuit had `9` assigned streams and bad
health, but that top-up failed to build after `4511ms` and was not used. The
analyzer now correctly matches that later same-profile failure by `pending_id`
and timestamp, instead of reporting the row as `missing`. Practical lesson:
bad-health gating avoids the earlier cold-circuit-use tail, but it is too late
to rescue the slow download page when the backup build fails.

Scheduler fairness proof is now wired but not yet proven on a fresh browser
run. Replaying
`results/browser-compare-20260609T140545/browser-compare.json` with the updated
analyzer adds `Torfast Stream Scheduler Late Circuit Fairness`; every late
circuit row currently says `no matching scheduler picks` because that older
run did not retain scheduler diagnostics. The browser runner now sets
`TORFAST_STREAM_SCHEDULER_LOG=1` when `--arti-socks-relay-byte-timing` is used,
and Arti only raises the existing scheduler `debug!` rows to `info!` under that
lab-only env var. Static proof
`results/arti-quality-config-20260609T142930/arti-quality-config.json` passed
`57` checks. Next browser proof should rerun the bad download shape with byte
timing before changing scheduler behavior.

The fresh scheduler/logged download proof is
`results/browser-compare-20260609T144811/browser-compare.json`, with analyzer
output saved at `results/browser-compare-20260609T144811/analysis.md`. It adds
a runner-only profile,
`--extra-arti-exit-health-aware-same-isolation-prewarm-target 2`, creating
`arti_release_browser_healthaware_sameiso2_prewarmfirst`. The command also set
`--arti-exit-select-health-min-move-score-bps 20000` and
`--arti-exit-same-isolation-require-bad-health`, and compared it in the same
window against baseline Arti, local C Tor, and
`arti_release_browser_loadaware_sameiso2_prewarmfirst`.

Quality passed and browser prefs stayed unchanged, but the new profile is a
hard reject. Baseline Arti was already faster than local C Tor on the download
page: median load `3623.586ms` vs `4784.481ms`, and boot `7.168s` vs `14.616s`.
The new health-aware prewarm profile had median load `12463.985ms`, max load
`118389.890ms`, and boot `21.628s`. Versus baseline Arti, it lost paired
median load by `+8840.399ms` and made the max tail `+112684.882ms` worse.
The queue loss reason was `single selected circuit queue`, not a better-health
miss: the worst run had `0` better-health alt rows and candidate context
`*0:Circ 4.1:a0:s0:g0, 1:Circ 4.7:a0:s0:g0, 2:Circ 4.8:a0:s0:g0`. The queue
mechanism hint was `receive window risk`, with max relay `118823ms`. Keep this
flag as lab proof only; do not tune sameiso prewarm by adding health-aware
selection. The safer next direction is to preserve the fast default Arti result
and investigate receive-window/resource-queue behavior only when a current
same-window proof shows baseline Arti loses.

The clean default-vs-local browser repeat is
`results/browser-compare-20260609T145904/browser-compare.json`, with analyzer
output at `results/browser-compare-20260609T145904/analysis.md`. It used only
default Arti and local C Tor on check, homepage, and download, with no extra
lab profile. Browser quality passed and prefs stayed unchanged, but default
Arti lost all three page-load medians to local C Tor: check `2795.674ms` vs
`1491.005ms`, homepage `8270.914ms` vs `4515.363ms`, and download
`14458.610ms` vs `5790.420ms`. Boot was also bad: Arti `40.246s` vs local C
Tor `10.633s`. The boot log had a directory build failure, a partial response,
and a directory timeout. This proves the prior download-only Arti win was not
stable enough; the active source target is still cold directory reliability and
page resource tails.

The existing directory-spread rescue profile was retested in
`results/browser-compare-20260609T150602/browser-compare.json`, with analyzer
output at `results/browser-compare-20260609T150602/analysis.md`. The overall
run failed quality because default Arti hit one homepage `netTimeout`, but the
candidate `arti_release_browser_mdsrcspreadpendingearlyusable` itself passed
all `9/9` page loads and kept prefs unchanged. It fixed the current boot
failure shape: default Arti boot was `25.694s` with `NOTDIRECTORY` and partial
response signals, while the combo boot was `12.758s` with no directory failure
signals.

Do not promote the directory combo yet. It won page-load medians on check
(`1166.739ms` vs local C Tor `1240.915ms`) and download (`3680.224ms` vs
`3921.001ms`), but lost homepage (`6560.444ms` vs `4866.763ms`) and still lost
boot-plus-load on every target. The homepage tail concentrated on unresolved
relay/CONNECT streams with no full lifecycle context in this non-byte-timing
run. Next work should diagnose that homepage loss with byte timing before
turning the source-spread combo into a default behavior change.

The focused homepage byte-timing proof is
`results/browser-compare-20260609T151737/browser-compare.json`, with analyzer
output at `results/browser-compare-20260609T151737/analysis.md`. It passed
quality and prefs. The source-spread combo improved over baseline Arti on the
homepage: median load `4585.615ms` vs `5485.691ms`, max load `6143.391ms` vs
`16544.737ms`, and boot+load `5016.615ms` vs `6043.691ms`. It was still just
slower than local C Tor by page-load median (`4585.615ms` vs `4430.342ms`), but
faster by boot+load (`5016.615ms` vs `7264.342ms`). The remaining blocker was
resource queue only: max queued `3416.735ms`, with no scheduler monopoly seen.
This says the homepage loss was not a directory failure and not a reason to add
sameiso/health-aware tuning.

The follow-up homepage byte-timing proof is
`results/browser-compare-20260609T152122/browser-compare.json`, with analyzer
output at `results/browser-compare-20260609T152122/analysis.md`. It also passed
quality and prefs. In this same-window repeat, the plain source-spread combo was
the best Arti profile and beat local C Tor on homepage page-load median:
`2931.112ms` vs `5510.561ms`, with boot+load `5676.112ms` vs `8936.561ms`.
The load-aware version also beat local C Tor, but it was worse than the plain
source-spread combo: median load `4309.839ms` vs `2931.112ms`, max load
`5441.475ms` vs `4096.910ms`, and boot+load `6022.839ms` vs `5676.112ms`.
Keep load-aware out of the promotion path. The best next gate is a broader
check/homepage/download repeat of the plain source-spread combo with normal
logging, then byte timing only if that wider run regresses again.

The broader normal check/homepage/download gate is
`results/browser-compare-20260609T152840/browser-compare.json`, with analyzer
output at `results/browser-compare-20260609T152840/analysis.md`. Overall
quality failed only because baseline Arti hit a download `netTimeout` on run
`2` and had no screenshot proof. The source-spread combo itself passed all
`9/9` page loads and kept browser prefs unchanged. It beat local C Tor on check
(`1406.007ms` vs `1921.729ms`) and homepage (`3583.635ms` vs `3747.166ms`), and
won boot+load on all three targets. But it lost download page-load median to
local C Tor (`4611.889ms` vs `3159.719ms`) and still had resource-queue and slow
stream blockers. This is useful rescue proof, not promotion proof.

The focused download byte-timing follow-up is
`results/browser-compare-20260609T153532/browser-compare.json`, with analyzer
output at `results/browser-compare-20260609T153532/analysis.md`. It passed
quality and prefs. In that download-only window, both Arti profiles beat local
C Tor: source-spread median load `4806.959ms` vs local `6776.733ms`, and
boot+load `5231.959ms` vs local `9623.733ms`. But source-spread lost to default
Arti: default median load `3514.894ms`, boot+load `4113.894ms`; source-spread
paired median load was `+1590.574ms` slower with only `1/3` paired load wins.
The loss reason was `single selected circuit queue`, and the mechanism hint was
`late Tor data, no local pending/window block`. Do not make source-spread a
default yet. The next safe move is to keep the directory-spread rescue as a
lab switch and target download resource queue / late Tor data without changing
path rules, relay choice, or browser prefs.

The focused download active-cap proof is
`results/browser-compare-20260609T155220/browser-compare.json`, with analyzer
output at `results/browser-compare-20260609T155220/analysis.md`. It passed
quality and prefs. The new runner-only profile
`arti_release_browser_loadaware_activecap2` beat default Arti on all `3/3`
paired download runs: median load `4266.003ms` vs default `10073.885ms`, and
boot+load `4773.003ms` vs default `11534.885ms`. It also beat local C Tor on
download median load (`4266.003ms` vs `5128.153ms`) and boot+load
(`4773.003ms` vs `8043.153ms`). This directly targets the prior
single-selected-circuit queue, cutting max queue from `8216.831ms` on default
Arti to `2183.377ms`. Keep it lab-only until it survives a broad
check/homepage/download gate and privacy review, because it changes stream
placement across already eligible circuits.

The broader active-cap check/homepage/download gate is
`results/browser-compare-20260609T155804/browser-compare.json`, with analyzer
output at `results/browser-compare-20260609T155804/analysis.md`. Overall
quality failed because baseline Arti hit a download `netTimeout` on run `3`
and had no screenshot proof. The `arti_release_browser_loadaware_activecap2`
candidate itself passed all `9/9` page loads and kept browser prefs unchanged.
It beat local C Tor on every median load: check `1333.735ms` vs `1500.443ms`,
homepage `5855.529ms` vs `6502.864ms`, and download `6436.895ms` vs
`10277.696ms`. It also beat local C Tor on every boot+load median:
`1794.735ms` vs `4754.443ms`, `6316.529ms` vs `9756.864ms`, and `6897.895ms`
vs `13531.696ms`. Versus baseline Arti, activecap2 won check `2/3` paired
loads, homepage `3/3`, and download `2/2` comparable loads because baseline
failed the third download run. It cut homepage max queue from `10150.203ms` to
`4250.085ms`, and download max queue from `10350.207ms` to `2550.051ms`.
Still keep it lab-only: the proof is not clean quality PASS, the candidate
still reports slow onion/data-gap and slow hostname-stream blockers, and stream
placement across eligible circuits needs privacy review before any default
path.

The active-cap tuning follow-up is
`results/browser-compare-20260609T161014/browser-compare.json`, with analyzer
output at `results/browser-compare-20260609T161014/analysis.md`. It passed
quality and prefs while testing caps `1`, `2`, and `3` on the download page in
one byte-timing window. Cap `1` had the best download median load
(`4967.970ms`) and cap `2` was close (`5521.975ms`); both beat local C Tor
(`5918.361ms`) and default Arti (`10032.914ms`). Cap `2` had the lower queue
tail: max queue `1783.369ms` vs cap `1` at `2566.718ms`. Cap `3` was too loose:
it lost page-load median to local C Tor (`7962.335ms` vs `5918.361ms`) and kept
a resource-queue blocker. This says cap `1` and `2` both deserve broad checks,
but cap `3` should stay rejected.

The broad cap `1` check/homepage/download gate is
`results/browser-compare-20260609T161607/browser-compare.json`, with analyzer
output at `results/browser-compare-20260609T161607/analysis.md`. It passed
quality and prefs, but it is not a broad speed win. Cap `1` lost every
page-load median to local C Tor: check `1580.961ms` vs `1424.149ms`, homepage
`11140.730ms` vs `3788.382ms`, and download `10929.473ms` vs `4249.073ms`.
It also kept the same promotion blockers as baseline Arti: slower than C Tor,
resource queue, slow onion/data gap, and slow hostname streams. Reject cap `1`
for promotion. Cap `2` remains the better active-cap lab path because its broad
run passed all candidate page loads and beat local C Tor on all medians, even
though that run was not a clean overall quality pass due to baseline Arti's
download timeout.

The cap `2` broad repeat is
`results/browser-compare-20260609T162554/browser-compare.json`, with analyzer
output at `results/browser-compare-20260609T162554/analysis.md`. It failed
overall quality because local C Tor hit a check-page `nssFailure2` on run `3`
and had no screenshot proof. The activecap2 candidate itself passed all `9/9`
page loads and kept browser prefs unchanged, but the speed result was not
stable enough for promotion. Activecap2 beat local C Tor on homepage median
load (`4513.803ms` vs `5552.429ms`), but lost check (`1448.363ms` vs
`1114.690ms`) and download (`5514.653ms` vs `4838.174ms`) page-load medians.
It still won all boot+load medians because its boot was much faster
(`0.497s` vs local C Tor `2.754s`). Versus baseline Arti, activecap2 improved
check and homepage but lost download (`+276.040ms` summary median load delta)
and had a worse download max tail (`8943.008ms` vs `5332.854ms`). Treat the
active-cap selector as useful queue lab evidence only, not a promotion path yet.
The next proof should target the remaining stream-gap/no-Tor-byte failures
directly and keep active-cap behind a lab switch.

The focused stream-gap byte proof is
`results/browser-compare-20260609T163624/browser-compare.json`, with analyzer
output at `results/browser-compare-20260609T163624/analysis.md`. It failed
quality because default Arti download run `2` timed out after `120000ms` and had
no screenshot proof. The failed run points to a clear stream-gap shape:
`Circ 0.11` carried `10` hostname relay-tail streams, with `8` no-Tor-byte
streams and `2` partial-then-idle streams. Lifecycle proof shows `4` streams
with `BEGIN` queued but no `CONNECTED`, and `4` streams with `CONNECTED`
delivered but no `DATA`. The worst idle-after-last-Tor-byte gap was
`117048ms`, and the max relay tail was `120412ms`. Activecap2 avoided that
timeout in the same byte window and passed its own page loads and prefs, with a
download median load of `4802.226ms` versus local C Tor at `5649.783ms`, but it
lost homepage median load (`5251.300ms` vs `4034.122ms`). Keep active-cap
lab-only. The next implementation should be a default-off no-data/idle stream
health proof knob that checks whether this `Circ 0.11` stall can be avoided
without changing path rules or browser privacy prefs.

The active no-DATA bad-health proof is
`results/browser-compare-20260609T171439/browser-compare.json`, with analyzer
output at `results/browser-compare-20260609T171439/analysis.md`. Static proof
`results/arti-quality-config-20260609T170331/arti-quality-config.json` passed
`58` checks, and release Arti was rebuilt before the browser run. The proof used
`--extra-arti-exit-select-bad-health-active-no-data-ms 5000` and failed quality:
default Arti failed `1/3` download runs, the active-no-DATA profile failed `2/3`
download runs, and local C Tor failed `0/3`. The active-no-DATA profile's
successful download median load was close to the others (`4082.360ms` vs default
Arti `4181.024ms` and local C Tor `4147.803ms`), but the worse failure rate
rejects it for promotion. It also did not reproduce the multi-stream `Circ 0.11`
pileup: failed relay tails were one stream per circuit. Do not broaden the
bad-health selector from this result. The next proof should target per-stream
relay-tail timeout, abandon, or retry behavior with strict privacy guardrails.

The no-Tor-byte timeout analyzer guard now records client-abandon evidence for
`TORFAST_SOCKS_NO_TOR_BYTE_RELAY_TIMEOUT_MS` events and prints a matching
browser-resource context table when such events fire. Static proof
`results/arti-quality-config-20260609T173625/arti-quality-config.json` passed
`58` checks, Python unit tests passed (`158` tests), `cargo check -p arti
--locked` passed, and release Arti was rebuilt.

The same-window no-Tor-byte timeout repeat is
`results/browser-compare-20260609T174005/browser-compare.json`, with analyzer
output at `results/browser-compare-20260609T174005/analysis.md`. It passed
quality and prefs, but rejects `--extra-arti-socks-no-tor-byte-relay-timeout-ms
5000` as a speed path. The no-byte profile fired `0` no-byte timeouts, so it did
not prove the mechanism. It also badly lost the download page: median load
`10036.529ms` vs default Arti `3913.271ms` and local C Tor `5512.791ms`, with a
max load tail of `40764.704ms` vs default Arti `5256.253ms`. The loss was a
single selected-circuit queue on `Circ 1.15`, with late Tor data and no local
pending/window block. Keep the no-byte close lab-only; the next proof should
diagnose late Tor data on selected circuits, not lower this timeout.

The saved analyzer now prints an `Arti Profile Queue Loss Selected Circuit` table
for that proof. It shows the bad `Circ 1.15 (Tunnel 33)` run was a multi-stream
late circuit, not one stuck stream: `17` late queued resources, `6` terminal
streams, top timing/stream share `40.476%`, max terminal last data after queue
`9746.873ms`, and max terminal data gap `4173.000ms`. Next source work should
look at selected-circuit multi-stream late DATA, not no-byte timeout tuning.

The analyzer also now prints an `Arti Profile Queue Loss Cause` row for the same
proof. For `Circ 1.15 (Tunnel 33)`, the scheduler proof shows `36` DATA picks
across `6` streams, top stream share `27.778%`, max same-stream streak `3`, and
`no scheduler monopoly seen`. Circuit congestion proof shows `10` events,
`9/1` SENDME sent/received, `0` scheduler blocks, `0` `can_send=false`, `0`
channel-blocked rows, fixed-window mode, `0` terminal pending bytes, all
terminal SENDMEs OK, and min terminal recv window `450`. The cause label is now
`late selected-circuit DATA, not scheduler/congestion`. Do not patch the stream
scheduler from this result; target circuit choice or network-side late DATA
evidence next.

The analyzer now also prints `Arti Profile Queue Loss Circuit Choice`. For the
same `Circ 1.15 (Tunnel 33)` loss, the page had `35` resources queued at least
`1000ms`, `23` queued resources at slot depth `>=6`, and max queue
`31633.966ms`. The selected queue cluster had `2` queued resources, relay
`9267.000ms`, and max relay gap `3037.000ms`. Choice context was only
`*0:Circ 1.15:a1:s13125.000:g351.000`, with `0` better-health and `0`
lower-assignment alternative rows, so the table labels it
`only selected open circuit logged`. This points away from another scoring tweak
for already-open circuits; next source work should prove/build safer capacity
before the resource burst or gather deeper network-side late-DATA evidence.

The analyzer now also prints `Arti Profile Queue Loss Capacity Pressure`. The
same bad run had `28` selected open rows for `Circ 1.15`, and open candidates
were always `1.000/1.000/1.000` min/median/max. Selected assigned streams rose to
`14.000`, selected active streams rose to `5.000`, open support saw `14` total
open circuits with `12` isolation rejects and `1` port reject, active cap stayed
`0.000`, and there were `0` same-isolation topups. The table labels this
`eligible same-isolation open capacity missing`; the next source target is usable
same-isolation capacity before the burst, not another open-circuit score tweak.

The runner now exposes a load-aware same-isolation capacity profile without
first-stream prewarm through
`--extra-arti-exit-load-aware-same-isolation-target`. It creates
`arti_release_browser_loadaware_sameisoN`, enabling load-aware exit selection and
`TORFAST_EXIT_SAME_ISOLATION_TARGET=N` while leaving health-aware,
avoid-bad-health, prefer-cold, and first-stream prewarm off.

The target `2` proof is
`results/browser-compare-20260609T182940/browser-compare.json`, with analyzer
output at `results/browser-compare-20260609T182940/analysis.md`. It passed
quality and prefs but rejects target `2` as speed proof. The candidate median
download load was `5996.385ms` versus baseline Arti `4575.725ms` and local C Tor
`4251.036ms`. It reduced max load versus baseline Arti (`6479.001ms` vs
`11715.209ms`), but the paired median load delta was `+1420.660ms` and it made
`0` same-isolation topups. The capacity row shows `2.000/2.000/2.000` open
candidates and target `2`, so the profile did not add capacity; it mostly
changed selection.

The target `3` proof is
`results/browser-compare-20260609T183428/browser-compare.json`, with analyzer
output at `results/browser-compare-20260609T183428/analysis.md`. It failed
quality: `arti_release_browser_loadaware_sameiso3` failed download run `3`, and
local C Tor also had one failed run, so this is not promotion proof. The
candidate itself is clearly rejected: median download load was `62244.336ms`
with max load `119453.966ms`, versus baseline Arti median `6447.233ms`. The
failed Arti run hit a net timeout with hostname/onion relay tails around
`57s-60s`. Do not continue same-isolation capacity target `3` without a new,
stricter idea; target `2` did not add capacity and target `3` damaged quality.

The focused active-cap `2` repeat is
`results/browser-compare-20260609T184543/browser-compare.json`, with analyzer
output at `results/browser-compare-20260609T184543/analysis.md`. It used
`--arti-socks-relay-byte-timing` and
`--extra-arti-exit-select-max-active-streams 2` for `5` download runs. Overall
quality failed because default Arti timed out on run `5` and local C Tor hit a
download net timeout on run `3`. The activecap2 candidate itself completed
`5/5` runs and kept browser prefs unchanged, but it is rejected as speed proof:
median load was `12315.364ms` versus default Arti successful-run median
`10197.894ms` and local C Tor `5776.944ms`. It won only `1/4` paired loads
versus baseline Arti, and its max load was much worse (`83266.910ms` vs
`17247.869ms`). The mechanism did not really fire: the selection table shows
`47` active-cap picks, `27` saturated cases, but `0` active-cap moves. The
worst queue row again says late Tor data with no local pending/window block,
and capacity pressure says one eligible open candidate
(`1.000/1.000/1.000`). Do not promote activecap2. The next work should stop
treating active cap as the main mechanism and focus on why Arti is often left
with one eligible open circuit during resource bursts, or on deeper
network-side late-DATA proof.

The analyzer now also prints `Arti One-Eligible Open-Circuit Bursts`. Replaying
`results/browser-compare-20260609T184543/browser-compare.json` shows the notable
one-candidate bursts are all labeled `isolation rejects most open circuits`, not
port rejection. In activecap2 run `5`, all `16/16` exit-open rows had only one
candidate, max open total was `14`, max rejected open was `13`, isolation
rejects were `12`, port rejects were `0`, max selected assigned streams was
`8`, max selected active streams was `4`, and load was `12315.364ms`. In default
Arti failed run `5`, `36/39` exit-open rows had one candidate, max rejected open
was `11`, isolation rejects were `11`, and port rejects were `0`. This confirms
the active cap is not the main mechanism; same-isolation eligibility and
capacity timing are. Because simple sameiso target/prewarm profiles already lost
or failed quality, the next source idea needs a stricter privacy-safe trigger,
not broad sameiso capacity.

Local Arti source now adds privacy-safe isolation-shape counters to
`open_support_summary`: `exit_unisolated`, `exit_compatible_isolated`, and
`exit_incompatible_isolated`, plus port/stability/country exit-block buckets.
These counters do not log the isolation value or SOCKS auth. The analyzer now
prints them in `Arti Profile Queue Loss Capacity Pressure` and
`Arti One-Eligible Open-Circuit Bursts`. Replaying the old
`20260609T184543` result proves backward compatibility, but not the new
mechanism yet because that result was captured before these fields existed. The
next browser proof should use low-log selection context and check whether the
one-eligible bursts are mostly unclaimed-circuit shortage or other isolation
groups owning otherwise usable open exits.

`scripts/build_arti_release.sh` rebuilt the release Arti binary after this
proof-only source change. Static guard
`results/arti-quality-config-20260609T191507/arti-quality-config.json` passed
`58` checks. The rebuilt binary is now ready for a fresh browser proof with the
new isolation-shape counters.

Fresh proof `results/browser-compare-20260609T191722/browser-compare.json`
reran the download shape with `--arti-socks-relay-byte-timing`,
`--extra-arti-exit-select-max-active-streams 2`, and `3` runs. Browser prefs
stayed valid, but overall quality failed because default Arti timed out on run
`3`. Activecap2 completed `3/3`, but it is still rejected: median load was
`7618.258ms` versus local C Tor `6026.216ms`, and activecap2 run `1` had a huge
`116838.145ms` load tail. The new isolation buckets explain the one-candidate
rows. In the capacity-pressure row, activecap2 run `2` had only `1` eligible
open candidate, `13` open circuits total, `10` isolation rejects,
`exit_unisolated=0`, `exit_compatible_isolated=1`, and
`exit_incompatible_isolated=10`; the hint is `other isolation groups own open
circuits`. One-eligible burst rows repeat the same shape in activecap2 runs `2`
and `3`, with up to `12` other-isolation open exits. This means active cap is
the wrong mechanism: the safe target is selective same-isolation capacity for
the current isolation group, not generic open-circuit spreading or active-cap
tuning.

Fresh same-isolation pressure proof
`results/browser-compare-20260609T194122/browser-compare.json` tested the
stricter lab trigger
`--extra-arti-exit-same-isolation-other-isolation-pressure 2:3` on the download
target for `3` runs, with analyzer output at
`results/browser-compare-20260609T194122/analysis.md`. Quality passed and
browser prefs stayed valid. The `arti_release_browser_sameiso2_otheriso3`
candidate completed `3/3`, booted in `11.265s`, and had median load
`3365.224ms`, median elapsed `4927.431ms`, and max load `4249.901ms`. Default
Arti was `3/3` with median load `4688.072ms` and max load `12231.235ms`; local C
Tor was `3/3` with median load `5541.779ms` and max load `8234.795ms`. Against
default Arti, the candidate won `2/3` paired loads, had paired median load delta
`-1328.709ms`, and cut max load by `7981.334ms`. The mechanism fired once:
same-isolation topups `1`, failures `0`, built `1`, used `1`,
other-isolation pressure `1`, max other-isolation exits `6.000`, and floor
`3.000`. This is promising first proof only. It is not promotion proof until a
broader A/B covers check, homepage, download, more runs, and repeat windows.

The broader A/B proof is
`results/browser-compare-20260609T194752/browser-compare.json`, with analyzer
output at `results/browser-compare-20260609T194752/analysis.md`. It reran
check, homepage, and download for `5` runs with
`--extra-arti-exit-same-isolation-other-isolation-pressure 2:3`. Overall
quality failed because default Arti hit a homepage net timeout on run `2` and
missed screenshot proof; browser prefs still passed. The candidate itself was
clean (`15/15` successful page runs), but it is rejected as broad speed proof.
It beat default Arti on check (`2079.790ms` vs `2596.256ms`) but lost homepage
badly (`7604.470ms` vs default Arti successful-run median `5224.163ms` and local
C Tor `5430.312ms`) and lost download to local C Tor (`7944.794ms` vs
`5795.200ms`). The A/B table flags homepage as risky: paired wins `1/4`, paired
median load delta `+1874.053ms`, summary median load delta `+2380.307ms`, and
max tail worse by `+7731.781ms`. Download was mixed: paired wins `3/5`, but
summary median load was still `+1386.137ms` slower than default Arti. The
top-up mechanism built without failures, but it did not make the broad page
case faster: homepage top-up attempt runs had median load delta `+3668.504ms`,
and the worst queue row still says `late selected-circuit DATA, not
scheduler/congestion`. Keep `2:3` lab-only and do not promote it. The next work
should diagnose why selected circuits go late after the extra same-isolation
capacity exists, or try a stricter trigger that proves no homepage/download
regression.

The analyzer now prints `Arti Profile Same-Isolation Top-Up Timing Diagnosis`.
Replaying `results/browser-compare-20260609T194752/browser-compare.json`
narrows the failed mechanism. For homepage, top-ups were built/seen `3/3`, but
only `1/3` was used, median load left after build was still `6609.324ms`, and
top-up runs were slower whether used or not: used-run median load delta
`+10038.343ms`, unused-run median load delta `+1874.053ms`. For download,
top-ups were built/seen `4/4` and used `3/4`; used top-ups helped
(`-1211.454ms`), but the unused top-up run regressed (`+1386.137ms`). This
rules out "top-ups are simply too late" as the whole explanation. The real next
bottleneck is safer circuit choice/use after capacity exists: the client must
avoid putting page-critical streams on a same-isolation circuit that later goes
late, without changing Tor Browser prefs, path rules, or relay privacy rules.

Added runner-only
`--extra-arti-exit-select-prefer-cold-same-isolation-other-isolation-pressure TARGET:MIN`
to combine the guarded prefer-cold selector with the other-isolation pressure
top-up trigger. Small proof
`results/browser-compare-20260609T200842/browser-compare.json`, with analyzer
output at `results/browser-compare-20260609T200842/analysis.md`, failed overall
quality because default Arti and the plain sameiso2/otheriso3 lab profile timed
out. The new guarded prefer-cold sameiso2/otheriso3 profile itself completed
`6/6` page runs, but it is not a promotion candidate: boot was `41.486s` vs
local C Tor `16.552s`, homepage median load was `4588.226ms` vs local C Tor
`4179.903ms`, and download median load was `5438.444ms` vs local C Tor
`5179.894ms`. Keep this as a diagnostic hook only.

Rebuilt release Arti and reran the same guarded prefer-cold sameiso2/otheriso3
other-isolation-pressure proof with stricter
`--arti-exit-same-isolation-min-assigned-streams 8`:
`results/browser-compare-20260609T202137/browser-compare.json`, with analyzer
output at `results/browser-compare-20260609T202137/analysis.md`. This is a hard
reject. Overall quality failed. The guarded prefer-cold profile failed `4/6`
page runs: homepage runs `1` and `2` timed out, and download runs `1` and `2`
timed out. Its only successful homepage load was `7306.479ms`, and its only
successful download load was `10519.385ms`. The top-up timing table shows the
homepage top-ups were built but not used (`2` top-ups, `0` used), while download
used one top-up and still only had one successful run. Raising the floor did not
make this path safe. Next work should stop trying broader same-isolation
pressure and focus on the current baseline Arti failure shape: download run `1`
hit `nssFailure2`, and the analyzer points to stream gaps/resource queues as
the next proof target.

The analyzer now prints `Arti Selected-Circuit Network Evidence`, and
`results/browser-compare-20260609T202137/analysis.md` was regenerated with it.
The table joins late resource queues, failed relay tails, stream receiver
endings, scheduler fairness, and circuit choice context. For the baseline
download failure, run `1` shows two failed selected circuits: `Circ 2.3` had
one relay-tail stream, one `not_connected` stream, max relay `39775ms`, and
idle after last data `37133ms`; `Circ 1.7` had max relay `34661ms` and idle
`33036ms`. Both are labeled `failed run partial DATA then idle`. Successful
baseline download runs show the other half of the same shape: run `3` on
`Circ 1.16` had `28` late resources, `6` terminal streams, no scheduler
monopoly, no local block seen, only the selected open circuit logged, and the
hint `late DATA on selected circuit`; run `2` on `Circ 2.2` had `18` late
resources with no local block seen, but did log open alternatives. This does
not make any profile promotable. It narrows the next source target to safer
circuit choice/capacity proof or deeper network-side late-DATA evidence, not a
stream scheduler patch and not broader same-isolation pressure.

Added a source-only trace for the next replay: `tor-proto/src/stream/raw.rs`
now logs `torfast stream receiver no-end close` when a stream receiver ends
without an END cell and returns `not_connected`. The log carries circuit, hop,
stream id, queued bytes, read count, SENDME counts, min receive window, and max
queued bytes. `tools/analyze_browser_compare.py` parses it, joins it to
terminal stream rows, and adds a `no-END closes` column to `Arti
Selected-Circuit Network Evidence` and `Torfast Stream Receiver Terminal Top
Streams`. Replaying old `20260609T202137` shows `0` no-END closes because those
logs did not exist yet. The next browser proof should rebuild Arti and check
whether the baseline `failed run partial DATA then idle` rows also show no-END
close events on the same streams.

Rebuilt release Arti and ran that focused baseline replay:
`results/browser-compare-20260609T205638/browser-compare.json`, with analyzer
output at `results/browser-compare-20260609T205638/analysis.md`. Quality
failed. Baseline Arti timed out on download run `3` after `121406.088ms`; local
C Tor completed `3/3`. Arti's two successful runs had median load
`5855.0225ms` and median elapsed `7330.389ms`, versus local C Tor median load
`5603.517ms` and median elapsed `7081.369ms`. Boot stayed faster for Arti
(`6.795s` vs `14.922s`), but this is not a speed win because quality failed.

The useful result is the new close trace. The worst failed stream was timing id
`22`, onion stream `10599` on `Circ 2.8`: connect `3179ms`, relay `116073ms`,
first Tor byte `3737ms`, last Tor byte `63641ms`, idle after last Tor byte
`55612ms`, `3530` Tor bytes in `9` DATA cells, terminal pending bytes `0`, and
`not_connected:eof=no`. The terminal table joins this to `1` no-END close,
`10` read events, `0` SENDMEs, min receive window `491`, and max queued bytes
after read `2922`. The selected-circuit evidence hint is now `failed partial
DATA then no-END close`.

Not every no-END close means the same thing. `Circ 3.9` in the same failed run
had six no-Tor-byte `not_connected` streams with six no-END closes and a
receive-window local-block risk. Successful baseline runs also still show late
selected-circuit DATA: `Circ 2.3` in run `2` and `Circ 3.1` in run `1` had
late resources, terminal streams, no scheduler monopoly, no local block seen,
and logged open alternatives. So the next source target is still circuit
choice/capacity and network-side late-DATA teardown proof. Do not promote this
build, do not tune the stream scheduler from this result, and stop widening
same-isolation pressure until this baseline failure shape is understood.

Added one more source-only trace at the actual stream-map close decision:
`tor-proto/src/circuit/circhop.rs` now logs `delivery="close_decision"` with
`close_reason`, `should_send_end`, and `close_behavior`. The analyzer joins
that to terminal stream rows and selected-circuit evidence. Focused proof
`results/browser-compare-20260609T211227/browser-compare.json`, with analyzer
output at `results/browser-compare-20260609T211227/analysis.md`, passed quality:
Arti completed `3/3` download runs and local C Tor completed `3/3`.

This run was page-fast but not promotion-safe. Arti median load was
`4612.915ms` versus local C Tor `5535.373ms`, median elapsed was `6065.960ms`
versus `7794.970ms`, and paired load wins were `3/3`. But boot was much worse:
Arti boot `26.092s` versus local C Tor `10.561s`; boot+median load was
`30704.915ms` versus `16096.373ms`. The promotion blocker is `boot slower,
boot directory`, with `12` directory-failure signals. Keep this as proof only.

The new close-decision join changes how to read no-END closes. In the passing
run, the selected-circuit table shows no-END terminal streams matched local
`StreamTargetClosed` decisions with `should_send_end=Send`: examples include
`Circ 3.7` (`6` no-END closes, `6` close decisions), `Circ 3.1` (`6` no-END
closes, `4` close decisions), and the long idle rows on `Circ 3.0`, `Circ 4.10`,
and `Circ 3.3`, each labeled `local close sent END after DATA idle`. So no-END
alone is not enough to prove a network-side failure. The next useful replay is
to reproduce the `20260609T205638` timeout shape with close-decision logging
enabled, while separately fixing or proving the cold boot directory delay.

Retested the directory boot rescue after the `20260609T211227` boot failure.
Focused proof `results/browser-compare-20260609T212012/browser-compare.json`,
with analyzer output at `results/browser-compare-20260609T212012/analysis.md`,
passed quality. The source-spread plus pending-spread plus early-usable profile
booted in `6.498s` versus local C Tor `20.726s`, with no directory failure
signals. It was still not promotion-safe: median page load was `6520.434ms`
versus local C Tor `3628.001ms`, and the blocker stayed `slower than C Tor,
resource queue`, though boot+median load was faster (`13018.434ms` versus
`24354.001ms`).

The load-aware version did better on the focused page. Proof
`results/browser-compare-20260609T212221/browser-compare.json`, with analyzer
output at `results/browser-compare-20260609T212221/analysis.md`, passed quality.
It had no promotion blocker in that one-target analyzer table, beat local C Tor
median load (`3982.714ms` versus `6097.335ms`), and beat local C Tor
boot+median load (`26756.714ms` versus `44801.335ms`). But boot was noisy at
`22.774s`, so this was only a prompt for broader A/B.

The broader 5-run, 3-target load-aware directory-combo proof is
`results/browser-compare-20260609T212517/browser-compare.json`, with analyzer
output at `results/browser-compare-20260609T212517/analysis.md`. It passed
quality. The candidate completed `15/15` page runs, booted in `6.969s` versus
local C Tor `15.565s`, and beat local C Tor summary median load on all three
targets: check `1819.063ms` versus `1852.504ms`, homepage `4951.799ms` versus
`9089.944ms`, and download `4342.098ms` versus `6174.269ms`. It also won
boot+median load by `49.5%`, `51.6%`, and `48.0%` for check, homepage, and
download. This is the best broad speed proof so far, but not a default-on
answer yet: the analyzer still flags one paired check-page slow target
(`+440.117ms`) and unresolved slow stream rows, so the next proof was a
byte-timing replay.

That byte-timing replay is
`results/browser-compare-20260609T213125/browser-compare.json`, with analyzer
output at `results/browser-compare-20260609T213125/analysis.md`. It also passed
browser quality, but it rejects promotion for now. The load-aware directory
combo hit the old boot-directory tail again: boot `22.334s` versus local C Tor
`11.798s`, `5` directory-failure signals, `3` `NOTDIRECTORY` signals, and `1`
partial response. In that replay it lost median page load to local C Tor on
both focused targets: check `2178.303ms` versus `1904.300ms`, and download
`5622.465ms` versus `4755.895ms`. Treat `20260609T212517` as promising broad
proof, not solved work. The next source target is to fix or safely retry the
microdescriptor partial/NOTDIRECTORY boot path for this combo, then repeat the
same 5-run, 3-target gate.

Tested the existing early-retry-on-partial boot idea inside the load-aware
directory combo. The runner now exposes
`--extra-arti-dir-microdesc-source-spread-pending-spread-early-usable-load-aware-early-retry-on-partial`,
which creates
`arti_release_browser_mdsrcspreadpendingearlyusable_loadaware_earlyretrypartial`
for lab A/B only. Proof
`results/browser-compare-20260609T214104/browser-compare.json`, with analyzer
output at `results/browser-compare-20260609T214104/analysis.md`, passed quality
but rejects this path. Early retry booted in `20.671s` versus local C Tor
`18.580s` and the clean load-aware combo `14.880s`. Its blocker list was
`boot slower, boot directory, slower than C Tor, resource queue`, with `6`
directory-failure signals, `2` directory failures, `2` directory timeouts, and
`2` partial-response signals. It also lost median load to local C Tor on both
targets: check `1136.053ms` versus `1128.923ms`, and download `6156.145ms`
versus `5557.543ms`.

Keep early-retry-on-partial lab-only and rejected for this combo. In the same
proof, the clean load-aware combo had no blocker, no directory-failure signals,
and beat local C Tor on boot+median load on both focused targets. The next
source target is a safer microdescriptor retry/source-choice policy, not
stopping the batch on the first partial response.

Added that safer lab path as partial-retry chunking. The source switch
`TORFAST_DIR_MICRODESC_PARTIAL_RETRY_CHUNKING=1` counts a partial
microdescriptor response as a retry signal but does not stop the current batch.
The browser runner profile
`arti_release_browser_mdsrcspreadpendingearlyusable_loadaware_partialretrychunk`
combines it with source spread, pending spread, early usable notification,
load-aware exit selection, retry chunks of `250`, and retry delay cap `500ms`.

Focused proof `results/browser-compare-20260609T215458/browser-compare.json`,
with analyzer output at `results/browser-compare-20260609T215458/analysis.md`,
passed quality. The new profile had no promotion blocker in that two-target
run and beat local C Tor median load on both focused targets, but this was only
a prompt for broader A/B.

The first broad attempt
`results/browser-compare-20260609T215915/browser-compare.json`, with analyzer
output at `results/browser-compare-20260609T215915/analysis.md`, is invalid as
a promotion proof because local C Tor failed one `check.torproject.org` run with
`nssFailure2`. Still, all Arti profiles completed their page runs. The
partial-retry profile was better than the clean load-aware combo on page tails
in that window, but it still had boot-directory failures and the analyzer asked
for clean baseline proof.

Clean rerun `results/browser-compare-20260609T220925/browser-compare.json`,
with analyzer output at `results/browser-compare-20260609T220925/analysis.md`,
passed quality on `3` runs across check, homepage, and download. The
partial-retry profile booted fast (`6.258s` versus local C Tor `12.946s`) with
no directory-failure signals, and boot+median load beat local C Tor on all
three targets. It is still not promotion-safe: the analyzer flags `slower than
C Tor, resource queue`, and page-only median load still lost to local C Tor on
check (`2347.816ms` versus `2323.391ms`) and download (`7195.288ms` versus
`6984.073ms`). The next proof needs a clean 5-run gate and retained evidence
that the partial-retry signal actually fired; the next source work is still the
resource-queue/late selected-circuit tail.

Clean 5-run gate `results/browser-compare-20260609T221818/browser-compare.json`,
with analyzer output at `results/browser-compare-20260609T221818/analysis.md`,
also passed quality on check, homepage, and download. The partial-retry profile
was enabled and booted faster than local C Tor (`12.669s` versus `14.990s`) with
no directory-failure signals, and boot+median load beat local C Tor on check and
homepage. It still does not promote: page-only median load lost to local C Tor
on all three targets (`2479.774ms` versus `2114.235ms`, `8628.144ms` versus
`7087.982ms`, and `13123.819ms` versus `8040.273ms`), download boot+load also
lost, and the analyzer flags `slower than C Tor, resource queue, slow hostname
stream`. The stored boot signals do not include `partial retry chunking signal`,
so this run proves the combined profile was active but does not prove the new
partial-retry path fired. Next proof should target stream-gap/resource-queue
cause before any new speed rule.

The stream-gap proof plumbing is now fixed for fresh byte-timing runs.
`tools/run_browser_compare.py --arti-socks-relay-byte-timing` raises the default
Arti log directive from `info` to `info,tor_proto=debug`, so it keeps
`torfast relay receive delivered` and `torfast stream receiver read` rows without
turning on unrelated full debug logs. Focused proof
`results/browser-compare-20260609T223414/browser-compare.json`, with analysis at
`results/browser-compare-20260609T223414/analysis.md`, passed quality and printed
the missing relay receive, stream receiver, and browser resource stream-gap
tables.

That proof does not justify a new source speed rule. Baseline Arti lost download
page-only median load to local C Tor by `+5190.900ms`; the analyzer labels the
blocker `slower than C Tor, resource queue`. The slow rows show no scheduler
monopoly and no local pending/window block. They do show late page-resource
queueing on selected circuits, with logged open alternatives. The partial-retry
combo won page-only load in this small two-run download proof (`5275.464ms`
versus local C Tor `6080.022ms`), but boot was bad (`21.479s` versus local
`13.942s`) due directory build failure signals, so it remains lab-only.

Focused load-aware-only follow-up
`results/browser-compare-20260609T223935/browser-compare.json`, with analysis at
`results/browser-compare-20260609T223935/analysis.md`, also passed quality. It
used the download page only, cold cache, interleaved schedule, three runs,
bundled Tor skipped, byte-timing logs, and
`--extra-arti-exit-select-load-aware`. Load-aware Arti median load was
`5203.072ms`, versus baseline Arti `7495.951ms` and local C Tor `6919.567ms`.
It beat local C Tor by `-1820.029ms` page-only median load and by
`-10336.029ms` boot+load, and beat baseline Arti by `-2292.879ms` median load.

This is still not a promotion. The load-aware blocker list is `resource queue`,
its worst run had a bigger tail than baseline Arti (`8064.902ms` versus
`7508.069ms`, `+556.833ms`), and max queued time reached `6383.461ms`. The
relay receive and stream receiver tables stayed present, so the proof plumbing
worked. The next useful proof is a bigger same-window gate or a smaller source
change that reduces the late page-resource queue/tail without changing Tor
quality.

Fixed one remaining proof hole after that run. `tor-circmgr` now emits the
default-off low-log circuit-selection row at `INFO` whenever
`TORFAST_EXIT_SELECT_LOW_LOG_CONTEXT=1`, instead of suppressing it when another
crate has debug logging enabled. Tiny proof
`results/browser-compare-20260609T225109/browser-compare.json`, with analysis at
`results/browser-compare-20260609T225109/analysis.md`, passed quality and
captured selector rows again: `52` circuit-selection rows for baseline Arti and
`26` for load-aware Arti, including `8` exit load-aware picks. The one-run speed
shape was good for load-aware (`3660.506ms` page load versus local C Tor
`5843.801ms`), but boot was slower (`18.045s` versus `11.827s`), so this only
proves the next queue-tail proof will have candidate-choice evidence.

Run-level proxy evidence is now windowed to each browser run. The failed
load-aware gate `results/browser-compare-20260609T225534/browser-compare.json`
had polluted run-1 proxy rows: the saved run contained boot/idle rows and later
rows outside the browser navigation window. The runner now filters proxy rows by
`started_epoch_ms`, `elapsed_ms`, `nav_finished_epoch_ms`, and row timestamps
(`event_epoch_ms`, SOCKS epoch fields, or leading ISO log time). Focused unit
proof covers numeric epoch rows, ISO timestamp rows, and no-epoch tail rows.

Fresh clean proof
`results/browser-compare-20260609T233054/browser-compare.json`, with analysis at
`results/browser-compare-20260609T233054/analysis.md`, passed quality and prefs
for the same download-page, cold-cache, interleaved, three-run load-aware test.
Do not promote load-aware from this result. Baseline Arti median load was
`4515.505ms`, local C Tor was `4735.462ms`, and load-aware Arti was slower at
`6850.239ms`. Load-aware won `2/3` paired loads against baseline Arti, but its
summary median was `+2334.734ms` slower and its max load tail was worse
(`10807.155ms` versus baseline `8864.259ms`). The blocker list is
`slower than C Tor, resource queue, slow onion/data gap`.

The clean proof also says not to patch the stream scheduler from this slice.
Scheduler rows were present (`37` load-aware DATA picks), but there were `0`
blocked hops. The slow load-aware run had one selected circuit carrying the big
resource burst and several `not_connected` terminal streams with local ENDs
after DATA idle. The next source target is deeper selected-circuit/late-DATA
evidence or a stricter circuit-choice signal, not more same-isolation,
active-cap, or scheduler tuning.

Replayed the same proof after fixing analyzer choice-context matching. The
`Arti Selected-Circuit Network Evidence` table now uses per-run circuit
selection rows directly when the resource-queue join has no matching cluster.
For the slow load-aware run `3`, `Circ 2.13` now shows `12` selected open rows
with only one eligible open circuit logged, no better-health alternative, and no
lower-assignment alternative; `Circ 3.5` shows the same one-candidate shape.
`Circ 2.9` still has missing choice context because no selection-open row for
that circuit exists in the run-windowed proof. Decision: do not patch selector
scoring, stream scheduling, sameiso target, or active cap from this replay. The
next useful change is tighter evidence or source logic around why Arti reaches
the resource burst with only one eligible same-isolation exit circuit.

The runner now keeps one more bounded proof row for future fresh runs: if a
circuit appears inside the browser run window, and a timestamped
`torfast circuit selection open` row for the same circuit appeared before the
run, that pre-run selection row is added to the run signal context. Old
unrelated rows and post-run rows stay filtered out. This should fill missing
choice context for reused circuits like `Circ 2.9` without returning to polluted
run evidence. Validation after these proof-only changes: `python3 -m unittest
discover` passed `162` tests, `python3 -m py_compile tools/*.py tests/*.py
torfast/*.py` passed, and `tools/check_arti_quality_config.py` wrote
`results/arti-quality-config-20260609T234702/arti-quality-config.json` with
`59` checks passing.

Fresh same-window proof with the pre-run selector-context runner fix:
`results/browser-compare-20260609T234755/browser-compare.json`, with analyzer
output at `results/browser-compare-20260609T234755/analysis.md`. Quality and
prefs passed for baseline Arti, load-aware Arti, and local C Tor on the
download page. Load-aware beat local C Tor in this noisy window
(`6034.965ms` median load vs `10086.426ms`) and booted slightly faster
(`17.749s` vs `18.778s`), but it is still not a promotion candidate: baseline
Arti was faster (`4538.359ms` median load), load-aware lost `0/3` paired loads
to baseline, and its max tail was worse (`6491.456ms` vs `4944.563ms`). The
promotion risk is `paired median slower, summary median slower, max tail worse,
low paired wins`.

The fresh selected-circuit evidence is better but still points away from simple
selector scoring. Most load-aware slow terminal circuits now have context:
`Circ 3.4`, `Circ 3.5`, and `Circ 3.0` all show no better logged open
alternative, while `Circ 4.6` shows an alternative existed. `Circ 4.11` still
has missing context because no `circuit selection open` row for that circuit was
present anywhere in the saved proof. Next proof/source work should keep
separating reused-circuit evidence from real selection mistakes, and should not
promote load-aware or retune sameiso/active-cap/scheduler from this result.

Fixed the next proof gap for future captures. `tor-circmgr` now emits
`torfast circuit selection build complete/failed/canceled` at `INFO` when the
default-off `TORFAST_EXIT_SELECT_LOW_LOG_CONTEXT=1` proof knob is enabled, even
for fast builds that are normally debug-only. The runner also keeps pre-run
`build complete` rows for circuits later seen inside the browser run window,
and the analyzer labels those rows as `pending build context only` instead of
`choice context missing`. This is still proof-only; it does not change circuit
choice or Tor quality. Validation: `python3 -m unittest discover` passed `163`
tests, `python3 -m py_compile tools/*.py tests/*.py torfast/*.py` passed,
`tools/check_arti_quality_config.py` wrote
`results/arti-quality-config-20260609T235535/arti-quality-config.json` with
`59` checks passing, `cargo fmt --check -p tor-circmgr` passed, and
`cargo check -p tor-circmgr` passed.

After rebuilding release Arti, fresh proof
`results/browser-compare-20260609T235823/browser-compare.json` passed quality
and prefs for baseline Arti, load-aware Arti, and local C Tor on the download
page. Analyzer output is
`results/browser-compare-20260609T235823/analysis.md`. The run confirms the new
fast-build proof path is live: load-aware saved a retained pre-run
`build complete` context row for `Circ 2.6` (`956ms`, exit usage). The selected
circuit evidence table did not hit a load-aware slow terminal circuit in this
one-run window, so the new `pending build context only` label was not exercised
there. Load-aware page load was `5146.116ms`, versus baseline Arti
`5607.022ms` and local C Tor `5675.523ms`, but baseline Arti still booted
faster (`13.369s` versus load-aware `19.216s`) and this is only a one-run proof.
Decision: this confirms proof capture, not promotion.

Fresh 3-run proof after that rebuild:
`results/browser-compare-20260610T000342/browser-compare.json`, with analyzer
output at `results/browser-compare-20260610T000342/analysis.md`. Quality and
prefs passed for baseline Arti, load-aware Arti, and local C Tor on the
download page. It rejects plain load-aware again: baseline Arti median load was
`4164.807ms`, local C Tor was `5009.176ms`, and load-aware was much slower at
`8457.081ms` with a bad `59930.601ms` max tail. The analyzer risk row says
`paired median slower, summary median slower, max tail worse, low paired wins`.
The worst load-aware run had `DOM-to-load 55784.449ms`, one terminal stream on
`Circ 2.4` idle for `54633ms` after DATA, and missing SOCKS stream-link context.
Decision: keep load-aware lab-only; patch proof capture, not circuit choice.

Proof-only capture fix after that failure: `arti::proxy::socks` now logs
`torfast socks timing stream linked` at `INFO` whenever
`TORFAST_SOCKS_RELAY_BYTE_TIMING=1`, even for fast connects. The runner now
keeps terminal receiver rows in signal context and retains matching
`stream linked` rows by `(circ_id, stream_id)` when bounded logs would otherwise
drop them. This changes only diagnostic output, not stream, circuit, relay, or
browser behavior. Validation: `python3 -m unittest discover` passed `164`
tests, `python3 -m py_compile tools/*.py tests/*.py torfast/*.py` passed,
`tools/check_arti_quality_config.py` wrote
`results/arti-quality-config-20260610T001141/arti-quality-config.json` with
`59` checks passing, `cargo fmt --check -p arti` passed, `cargo check -p arti`
passed, and `cargo build --release -p arti` passed.

Fresh one-run proof with the rebuilt binary:
`results/browser-compare-20260610T001352/browser-compare.json`, with analyzer
output at `results/browser-compare-20260610T001352/analysis.md`. Quality passed.
The saved JSON now includes `30` retained `torfast socks timing stream linked`
rows, including fast `elapsed_ms=0` hostname streams, so future slow terminal
rows can be joined to SOCKS timing ids. In this one-run window baseline Arti
loaded in `3144.885ms`, load-aware in `4821.689ms`, and local C Tor in
`7980.319ms`. Load-aware beat local C Tor in that noisy slice but still lost to
baseline Arti (`+1676.804ms`, `0/1` paired wins) and booted slower, so this is
capture proof only, not speed promotion.

Fresh health-aware A/B proof:
`results/browser-compare-20260610T001702/browser-compare.json`, with analyzer
output at `results/browser-compare-20260610T001702/analysis.md`. Quality passed
on the download page. Health-aware looked strong in this narrow window:
median load was `4296.496ms` versus baseline Arti `13337.450ms` and local C Tor
`5800.935ms`, with `3/3` paired load wins over baseline. The saved proof kept
`141` stream-link rows. This result kept health-aware worth testing, but it was
only one target and one noisy window.

The wider health-aware gate rejects promotion:
`results/browser-compare-20260610T002123/browser-compare.json`, with analyzer
output at `results/browser-compare-20260610T002123/analysis.md`. Quality passed
for baseline Arti, health-aware Arti, and local C Tor across check, homepage,
and download. Health-aware beat baseline only on download
(`7236.901ms` vs `8867.088ms` median load), but lost check
(`1621.850ms` vs `981.092ms`) and homepage (`8842.815ms` vs `8300.421ms`).
It also booted slower than baseline Arti and local C Tor (`22.399s` vs
`18.455s` and `12.888s`) and had bad max tails on check and homepage
(`26611.767ms` and `26310.613ms`). Decision: keep health-aware lab-only and do
not promote it. Next source work should target stream-gap/resource-queue tails,
not health-aware selector promotion.

Analyzer proof patch after the wider gate: `tools/analyze_browser_compare.py`
now prints `Resource Queue Lifecycle Evidence`, joining late queued browser
resources back to the exact SOCKS stream lifecycle rows. Replaying
`results/browser-compare-20260610T002123/browser-compare.json` shows the slow
queued resources had DATA delivered, `queue full` was `0`, max circuit sender
queue was `0`, and terminal pending bytes were `0`. This strengthens the
current read: the queue tail is late selected-circuit DATA, not a local Arti
queue-full or pending-byte block. Validation: focused unit test
`tests.test_browser_quality.BrowserQualityTests.test_arti_profile_queue_loss_mechanism_rows_identify_late_tor_data`
passed, `python3 -m unittest discover` passed `164` tests, and
`python3 -m py_compile tools/*.py tests/*.py torfast/*.py` passed.

Follow-up analyzer proof patch: `tools/analyze_browser_compare.py` now prints
`Browser Resource Queue Choice Class Summary`, grouping slow queued browser
resources by the circuit choice shape seen in
`Browser Resource Queue Selection Context`. Replaying
`results/browser-compare-20260610T002123/browser-compare.json` shows `19`
slow rows with only the selected open circuit, `5` rows with a lower-assignment
alternative, and `0` rows with a better-health alternative. This keeps the next
source lane pointed at same-isolation capacity timing first, with guarded
assignment proof second, not broad health selector scoring. Validation:
focused tests
`tests.test_browser_quality.BrowserQualityTests.test_arti_profile_queue_loss_mechanism_rows_identify_late_tor_data`
and
`tests.test_browser_quality.BrowserQualityTests.test_browser_resource_queue_choice_class_summary_rows`
passed, `python3 -m unittest discover` passed `165` tests, and
`python3 -m py_compile tools/*.py tests/*.py torfast/*.py` passed.

Fresh same-isolation prewarm test:
`results/browser-compare-20260610T004615/browser-compare.json`, with analyzer
output at `results/browser-compare-20260610T004615/analysis.md`. Quality
passed across baseline Arti, plain health-aware Arti, health-aware
`sameiso2_prewarmfirst`, and local C Tor. The prewarm profile was not a
promotion result: it beat baseline Arti on homepage median load
(`5260.249ms` vs `7591.664ms`) and booted fast (`8.560s`), but it was slower on
check (`1976.586ms` vs `1900.374ms`) and download (`5163.388ms` vs
`4641.347ms`) with only `1/3` paired wins on those targets. The same-isolation
diagnosis says top-ups were built on homepage and download but were not used.
Decision: prewarm is useful proof, not a speed win.

Fresh guarded prefer-cold same-isolation prewarm test:
`results/browser-compare-20260610T005212/browser-compare.json`, with analyzer
output at `results/browser-compare-20260610T005212/analysis.md`. Quality
failed: download run `1` hit a browser net timeout and missed screenshot proof.
The profile beat baseline on homepage median load (`5683.521ms` vs
`8240.958ms`) but was much slower on successful download runs
(`8708.618ms` vs `3917.674ms`) and had worse boot than baseline Arti
(`16.634s` vs `8.911s`). Top-ups were built and seen, but still had `0` used
top-ups. The queue classifier moved the candidate's worst slow rows to
lower-assignment alternatives, so this rejects the guarded prefer-cold prewarm
path and points the next proof at why built same-isolation top-ups are not used
or why lower-assignment alternatives are not chosen safely.

Analyzer follow-up: `tools/analyze_browser_compare.py` now prints
`Arti Profile Same-Isolation Top-Up Nonuse Detail`. Replaying
`results/browser-compare-20260610T004615/browser-compare.json` found `5`
unused built/seen top-ups: `4` never appeared in later open candidates, and `1`
appeared but lost to a better-health circuit. Replaying
`results/browser-compare-20260610T005212/browser-compare.json` found `6`
unused built/seen top-ups: `2` never appeared in later open candidates, and `4`
appeared but lost to better-health circuits. This proves the next source lane is
not "make more same-isolation prewarm"; it is either making built top-ups appear
as usable open candidates in time, or changing a guarded cold/unknown-health rule
if that can be made safe. Validation: the focused `3` tests passed,
`python3 -m unittest discover` passed `166` tests, and
`python3 -m py_compile tools/*.py tests/*.py torfast/*.py` passed. Analyzer
replay for `20260610T005212` still exits non-zero because that saved run failed
quality, which is expected.

Source follow-up: `upstream/arti/crates/tor-circmgr/src/mgr.rs` now wires
`select_prefer_cold_same_isolation` into the real open-circuit selector. Before
this patch, the code logged the flag but passed `false` into
`find_best_index_before_active_cap`, so guarded prefer-cold same-isolation runs
could still let health-aware selection beat the cold assignment candidate. This
does not promote the profile yet; it only makes the lab flag actually test the
intended rule. Validation: `python3 tools/check_arti_quality_config.py
--arti-root upstream/arti` passed and wrote
`results/arti-quality-config-20260610T011101/arti-quality-config.json`, the
Python unit suite passed `166` tests, `python3 -m py_compile tools/*.py
tests/*.py torfast/*.py` passed, and `cargo test -p tor-circmgr` passed `70`
Rust tests plus doc-tests.

Fresh patched-release rerun after that wiring fix:
`results/browser-compare-20260610T011528/browser-compare.json`, with analyzer
output at `results/browser-compare-20260610T011528/analysis.md`. Quality still
failed because the guarded prefer-cold sameiso2 prewarm profile hit a download
run `1` browser net timeout and missed screenshot proof. The failure was a mixed
connect wait plus relay-after-reply tail: `3` relay-tail streams, all with no
Tor bytes, with max relay `59166ms`. The patched profile looked better on
homepage median load (`4437.772ms` vs baseline Arti `12150.056ms`, local C Tor
`4719.683ms`), but lost check (`1266.237ms` vs baseline `1091.595ms`) and
download (`5572.921ms` vs baseline `3959.029ms`, local C Tor `4086.796ms`) and
had only `2/3`, `2/3`, and `0/2` paired wins on check, homepage, and download.
The refreshed nonuse table now shows `3` built/seen top-ups with no later
circuit-selection event after proof. In all `3` rows, the streams that linked
after proof had already started before the top-up was ready (`2` such stream
 links in each row). The earlier better-health-selection loss shape did not
 appear in this rerun. Decision: wiring is fixed, but this profile remains
 lab-only and rejected for promotion. Next source work should make same-isolation
 prewarm happen earlier or force a useful later selection after build, and
 separately explain why failed download streams can wait ~59s with no Tor bytes.

Fresh same-isolation pending-wait patch:
`upstream/arti/crates/tor-circmgr/src/mgr.rs` now has a default-off lab knob,
`TORFAST_EXIT_SAME_ISOLATION_PENDING_WAIT_MS`, bounded to `50..=2000ms`. When
same-isolation target capacity is already building, exit stream selection can
wait briefly for that pending circuit, then fall back to the already selected
open circuit if the wait does not win. `tools/run_browser_compare.py` exposes
this as `--arti-exit-same-isolation-pending-wait-ms`, and
`tools/check_arti_quality_config.py` checks the knob, bounds, action, and logs.
Validation passed: Python compile, `python3 -m unittest discover` (`167`
tests), `python3 tools/check_arti_quality_config.py --arti-root upstream/arti`,
`cargo test -p tor-circmgr` (`70` tests plus doc-tests), and
`cargo build --release -p arti`.

Fresh live proof:
`results/browser-compare-20260610T014101/browser-compare.json`, with analyzer
output at `results/browser-compare-20260610T014101/analysis.md`. Quality passed.
The pending-wait sameiso2/prefer-cold/prewarm profile beat baseline Arti in
A/B on both tested targets: homepage paired median load delta `-3529.439ms`
and download paired median load delta `-4320.682ms`. It was close to C Tor but
not a full promotion: homepage median load was `2.5%` slower than bundled Tor
and `4.9%` slower than local C Tor, while download median load was `41.7%`
slower than bundled Tor but `6.2%` faster than local C Tor. Boot stayed worse
than baseline Arti (`22.128s` vs `12.385s`) because the profile hit directory
partial-response timeouts. The same-isolation nonuse table still had `1`
built/seen top-up with no later circuit selection; its linked streams had
already started before the top-up was ready. Decision: promising lab result,
still not promoted. Next source work should make first-stream top-up earlier
and reduce boot directory failures.

Pending-wait pressure follow-up:
`upstream/arti/crates/tor-circmgr/src/mgr.rs` now lets the lab-only
same-isolation pending wait fire when the selected circuit is already assigned
and matching capacity is pending, even if `open_candidates == target`. This is
still gated by `TORFAST_EXIT_SAME_ISOLATION_PENDING_WAIT_MS`; default behavior
is unchanged. `tools/analyze_browser_compare.py` now parses
`same_isolation_pending_wait`, `same_isolation_pending_wait_won`, and
`same_isolation_pending_wait_timer`, so the existing `pending waits` table shows
this mechanism. Validation passed: Python compile, `python3 -m unittest
discover` (`167` tests), `python3 tools/check_arti_quality_config.py
--arti-root upstream/arti`, `cargo test -p tor-circmgr` (`71` tests plus
doc-tests), and `cargo build --release -p arti`.

Fresh live proof:
`results/browser-compare-20260610T015105/browser-compare.json`, with analyzer
output at `results/browser-compare-20260610T015105/analysis.md`. Quality passed.
The pressure wait fired: analyzer now reports `9` pending waits for the patched
profile, and raw logs show one `same isolation pending wait won`. The profile
beat baseline Arti A/B on both tested targets: homepage paired median load
delta `-4447.160ms`, download paired median load delta `-2677.191ms`. It also
beat local C Tor on homepage (`16.6%` faster median load, `13.0%` faster median
elapsed), but still lost download page load to local C Tor (`35.6%` slower
median load, `26.4%` slower median elapsed). Boot+download was faster because
baseline Arti boot was very bad in this run, but page-load alone is not enough.
Decision: pressure-wait is useful proof and stays lab-only; next work should
target the slow download relay tails and directory boot failures.

SOCKS byte-timing proof follow-up:
`upstream/arti/crates/arti/src/proxy/socks.rs` now promotes fast SOCKS
`stream ready`, `socks reply sent`, and byte-timing relay summaries to INFO
when the default-off lab flag `TORFAST_SOCKS_RELAY_BYTE_TIMING=1` is set.
Normal logging is unchanged. `tools/run_browser_compare.py` also keeps all
SOCKS timing rows for timing ids linked to late terminal streams, so the
browser proof no longer drops the connect/reply context for fast streams.
Validation passed: focused runner tests, `tests.test_arti_quality_config`,
Python compile, static Arti quality config (`60` checks), `cargo fmt --check -p
arti`, `cargo check -p arti`, and `cargo build --release -p arti`.

Fresh focused byte-timing proof:
`results/browser-compare-20260610T021009/browser-compare.json`, with analyzer
output at `results/browser-compare-20260610T021009/analysis.md`. Quality passed,
and the analyzer now shows fast SOCKS connect/reply rows (`7/7` for baseline
Arti, `11/11` for the patched profile). The run rejected the patched profile:
download median load was `61687.470ms` vs local C Tor `5236.324ms`. The slow
profile had several selected circuits with `4079..4801ms` DATA gaps and very
low rough receive rates, including a worst selected circuit around `0.856`
KiB/s. Decision: do not promote pending-wait/prefer-cold sameiso from this
proof. Next work should focus on selected-circuit health/low-rate evidence and
boot directory failures, not on adding more same-isolation capacity.

Active-stream-age diagnostic:
`upstream/arti/crates/tor-circmgr/src/mgr.rs` now adds
`active_stream_age_ms` to the load-aware candidate health summary and
`selected_active_stream_age_ms` to circuit-selection logs. This is proof logging
only; default Tor behavior is unchanged. `tools/analyze_browser_compare.py`
now parses old and new summary formats and prints max active-stream age in the
circuit-selection tables plus selected/first active age in
`Torfast Load-Aware Selection Health Outcome`.

Fresh diagnostic proof:
`results/browser-compare-20260610T022130/browser-compare.json`, with analyzer
output at `results/browser-compare-20260610T022130/analysis.md`. Quality passed.
The `--extra-arti-exit-select-bad-health-active-no-data-ms 5000` profile is
rejected: baseline Arti load was `2726.419ms`, the active-no-data profile was
`5524.763ms`, and the profile made `5` selected low-rate picks. The new report
shows max selected active age `0ms` and max first active age `1142ms`, so this
bad run was not fixed by simply avoiding active streams with no data. Local C
Tor was very slow in this one-run network window (`17492.971ms` load), so use
this as diagnostic proof only, not broad Arti-vs-C-Tor proof. Next work should
target selected low-rate circuit guards, not promote active-no-data alone.

Health-aware threshold repeat:
`results/browser-compare-20260610T023142/browser-compare.json`, with analyzer
output at `results/browser-compare-20260610T023142/analysis.md`, was a narrow
one-run clue. Quality passed and `arti_release_browser_healthaware_min16000bps`
beat local C Tor page-load in that window: `3802.737ms` versus `4542.306ms`,
with `0` low-rate circuits. This was not enough proof, so it was repeated.

The stronger 3-run repeat is
`results/browser-compare-20260610T023311/browser-compare.json`, with analyzer
output at `results/browser-compare-20260610T023311/analysis.md`. Quality passed
but rejected the `16000bps` health-aware profile. It had `0/3` paired load wins
against baseline Arti, paired median load was `+6029.752ms` slower, max load
was worse by `+6029.752ms`, and it also lost page-load to local C Tor
(`19340.436ms` vs `11825.831ms`). The selector avoided low-rate circuits in the
run summary, but page resource queue and stream-gap tails got worse. Decision:
do not promote lower health-aware threshold; next work needs a guard that avoids
known bad/cold picks without forcing slow same-circuit resource queues.

Health-aware same-isolation pending-wait diagnostic:
`tools/run_browser_compare.py` now has
`--extra-arti-exit-select-health-min-move-score-same-isolation-pending-wait`
for a clean same-window profile that combines health-aware min score,
same-isolation target, and pending wait without changing baseline Arti.
Validation passed: Python compile, focused runner tests, static Arti quality
config (`60` checks), and analyzer.

Fresh diagnostic proof:
`results/browser-compare-20260610T024537/browser-compare.json`, with analyzer
output at `results/browser-compare-20260610T024537/analysis.md`. Quality passed.
The new `arti_release_browser_healthaware_min16000bps_sameiso2_wait800ms`
profile beat baseline Arti in the one paired run: load `4897.583ms` vs
`5861.453ms` (`-963.870ms`). It also fixed the plain health-aware result in
that window: plain `16000bps` load was `7185.025ms`. But it still lost page-load
to local C Tor (`4897.583ms` vs `3598.995ms`) and boot was slower
(`20.446s` vs baseline Arti `12.493s`). Decision: promising diagnostic, not
promotion proof. Next work should run a multi-run repeat and reduce boot
directory failures before treating this as a real speed win.

The 3-run repeat is
`results/browser-compare-20260610T025054/browser-compare.json`, with analyzer
output at `results/browser-compare-20260610T025054/analysis.md`. Quality passed,
but it rejected the combined `16000bps_sameiso2_wait800ms` profile. Median load
was `20387.059ms`, versus baseline Arti `4062.821ms` and local C Tor
`7052.261ms`. It won only `1/3` paired loads against baseline Arti and had a
bad max tail: `27902.504ms` versus baseline max `8372.393ms`. The analyzer
points at late resource queues: paired median DOM-to-load was `+13666.940ms`
slower than baseline, and max queue was `22750.455ms`. Decision: reject the
combined same-isolation pending-wait profile for speed. Next work should focus
on guarded assignment after selection and resource-queue tails, not on waiting
longer for same-isolation pending capacity.

Assigned-cap follow-up:
`tools/run_browser_compare.py` now has
`--extra-arti-exit-select-health-min-move-score-assigned-cap SCORE:CAP`, and
Arti has the default-off lab env `TORFAST_EXIT_SELECT_MAX_ASSIGNED_STREAMS`.
It caps assigned streams after normal health-aware selection, without changing
path eligibility or isolation. Validation passed: Python compile, focused
runner tests, Rust selector unit test, release build, and static Arti quality
config (`61` checks).

Fresh proof:
`results/browser-compare-20260610T031147/browser-compare.json`, with analyzer
output at `results/browser-compare-20260610T031147/analysis.md`. Quality failed.
The `arti_release_browser_healthaware_min16000bps_assignedcap4` profile had
one browser timeout: run 3 took `121615.880ms`, missed load and screenshot
proof, and the analyzer called it a connect wait. The two successful cap runs
looked better than plain health-aware, but not enough: cap profile median load
was `4674.788ms` versus baseline Arti `3580.733ms`; paired A/B against baseline
won only `1/2` successful runs and summary median was `+1094.055ms` slower.
Decision: reject this exact `16000bps_assignedcap4` combo. The cap may reduce
some resource queues, but it does not pass the quality bar.

Runner follow-up: `tools/run_browser_compare.py` now also supports
`--extra-arti-exit-same-isolation-other-isolation-pressure-assigned-cap TARGET:MIN:CAP`.
It creates a same-window Arti profile that keeps the stricter other-isolation
pressure same-isolation trigger, then caps selected assigned streams with the
existing `TORFAST_EXIT_SELECT_MAX_ASSIGNED_STREAMS` lab knob. This keeps path
rules, stream isolation, and browser prefs unchanged while testing
same-isolation capacity timing plus guarded assignment together. Validation:
focused runner tests passed, `python3 -m unittest discover` passed `173` tests,
and `python3 -m py_compile tools/*.py tests/*.py torfast/*.py` passed.

Fresh proof:
`results/browser-compare-20260610T110716/browser-compare.json`, with analyzer
output at `results/browser-compare-20260610T110716/analysis.md`. Quality
passed, but it rejects `arti_release_browser_sameiso2_otheriso3_assignedcap4`
as a promotion path. The profile booted fast from warm cache (`0.399s` versus
local C Tor `3.291s`) and slightly improved baseline Arti on the download page
median load (`6029.074ms` versus `6172.505ms`), but it still lost page-only
load to local C Tor on both targets: homepage `4352.006ms` versus
`4276.860ms`, and download `6029.074ms` versus `4000.811ms`. The analyzer kept
the same blocker shape: `slower than C Tor, resource queue, slow onion/data
gap, slow hostname stream`, with worse queued-run evidence on both targets than
baseline Arti. Warmup also hit directory partial-response timeouts and took
`45.944s`, so even though measured boot was quick, this is not a stable broad
speed direction. Decision: keep the new combo lab-only. The next useful work
should stay on stream-gap/resource-queue cause and safer circuit choice after
capacity exists, not this assigned-cap combination alone.

Focused pending-wait follow-up:
`results/browser-compare-20260610T111820/browser-compare.json`, with analyzer
output at `results/browser-compare-20260610T111820/analysis.md`, reran the same
`sameiso2_otheriso3_assignedcap4` profile with
`--arti-exit-same-isolation-pending-wait-ms 800`. Quality passed. In that
2-target, 3-run warm-cache window, the profile beat both baseline Arti and
local C Tor on median page-only load for homepage and download: homepage
`3469.020ms` versus baseline Arti `4641.358ms` and local C Tor `9471.591ms`;
download `4341.950ms` versus baseline Arti `14151.096ms` and local C Tor
`11548.619ms`. This is still not promotion proof: the homepage had a huge bad
tail (`63959.593ms` max load), and the analyzer says the same-isolation top-ups
were built/seen but still not used. Treat this as a promising noisy slice, not
a solved path. The useful lesson is that pending-wait plus assigned-cap can win
in a good window, but it still leaves catastrophic no-byte relay tails.

Broader repeat:
`results/browser-compare-20260610T112438/browser-compare.json`, with analyzer
output at `results/browser-compare-20260610T112438/analysis.md`, reran that
pending-wait profile across `check`, homepage, and download for `3` runs.
Overall quality failed because local C Tor had one failed download run after a
very slow warmup (`157.980s`), so this is not promotion proof. The candidate
itself completed `9/9` page runs, but it is a hard rejection for speed:
check median load was `6276.830ms` versus baseline Arti `1060.060ms` and local
C Tor `1664.842ms`; homepage median load was `15396.479ms` versus baseline
Arti `5499.444ms` and local C Tor `6929.010ms`; only download stayed fast at
`4381.255ms` versus baseline Arti `3467.514ms` and local C Tor successful-run
median `27621.111ms`. The analyzer flags `paired median slower, summary median
slower, max tail worse, low paired wins` on all three targets versus baseline
Arti, and again shows same-isolation top-ups built/seen but not used. Decision:
keep pending-wait plus `sameiso2_otheriso3_assignedcap4` lab-only and rejected.
The next source work should explain why built same-isolation capacity still gets
no later selection and why no-byte relay tails can still dominate check/homepage
after the extra capacity exists, not add more wait/cap tuning to this exact
combo.

Source quality fix:
`upstream/arti/crates/tor-circmgr/src/mgr.rs` now restricts the fallback open
tunnel before returning it from the `Action::OpenAfterSameIsolationPendingWait`
path. Before this fix, a pending-wait timeout or empty-wait fallback could hand
back the open tunnel without calling `restrict_mut`, so the tunnel would not
record the new exit assignment or expiration state for that request. This is a
quality and accounting bug fix first; it does not add a new lab knob. The
static source/config check now requires the fallback restriction path and wrote
`results/arti-quality-config-20260610T115719/arti-quality-config.json` with
`61` passing checks. Validation also passed with
`cargo test -p tor-circmgr --locked` (`73` Rust tests plus doc-tests) and
`python3 -m unittest discover` (`173` tests).

Fresh rerun after the fallback restriction fix:
`results/browser-compare-20260610T115131/browser-compare.json`, with analyzer
output at `results/browser-compare-20260610T115131/analysis.md`, reran the same
2-target pending-wait profile after rebuilding release Arti. Quality passed,
but the profile still rejects for speed.
`arti_release_browser_sameiso2_otheriso3_assignedcap4` lost page-only median
load to both baseline Arti and local C Tor on both targets: homepage
`8158.323ms` versus baseline Arti `3507.433ms` and local C Tor `4445.846ms`;
download `5602.251ms` versus baseline Arti `3945.687ms` and local C Tor
`4854.175ms`. The analyzer again flags
`paired median slower, summary median slower, max tail worse, low paired wins`,
and the same-isolation timing diagnosis still says top-ups were built/seen but
were not used. This means the fallback restriction bug fix was necessary for
quality, but it does not make this pending-wait plus assigned-cap path
promotable. The next source work stays the same: explain why built same-isolation
capacity gets no later selection and why selected circuits still collapse into
single-circuit queue and no-byte relay tails on large page bursts.

Bad-health replacement follow-up:
`upstream/arti/crates/tor-circmgr/src/mgr.rs` now has a lab-only path behind
the existing `TORFAST_EXIT_SELECT_BAD_HEALTH_HEDGE_MS` knob that waits for an
already pending same-usage/same-isolation bad-health replacement before
launching a duplicate replacement. This keeps the same isolation and fallback
rules. The analyzer now parses `bad_health_pending_wait`,
`bad_health_pending_wait_won`, and `bad_health_pending_wait_timer`, and
`tools/run_browser_compare.py` now supports
`--extra-arti-exit-select-bad-health-hedge-ms` for same-window A/B proof.

Validation passed: Python compile, focused runner tests,
`python3 -m unittest tests.test_browser_quality tests.test_arti_quality_config`
(`181` tests), static Arti quality config (`74` checks),
`cargo fmt --manifest-path upstream/arti/Cargo.toml --package tor-circmgr
--check`, `cargo test -p tor-circmgr bad_health --manifest-path
upstream/arti/Cargo.toml` (`6` tests), and release Arti build.

Fresh proof:
`results/browser-compare-20260612T192228/browser-compare.json`, with analyzer
output at `results/browser-compare-20260612T192228/analysis.md`, tested
`--extra-arti-exit-select-bad-health-hedge-ms 800` on the Tor Project homepage
for `3` cold interleaved runs. Quality passed and the new path fired: logs show
`bad health pending wait` and one `bad health pending wait won` using
replacement `Circ 3.72`. It is not a speed win. The hedge profile completed
`3/3` runs but was slower than base Arti: median load `8605.161ms` versus
`4750.699ms`, median elapsed `11290.867ms` versus `8115.021ms`, and paired A/B
won `0/3` loads. The analyzer flags `paired median slower, summary median
slower, max tail worse, low paired wins`. Decision: keep this path lab-only and
do not promote it. The useful next step is to use the fired logs to understand
why a won replacement can still create worse resource queues.

Bad-health pending-wait guard:
The bad-health pending-wait path now stops stacking extra requests on the same
pending replacement after the selected bad-health circuit already has more
than one assigned stream. When this happens it logs
`bad health pending wait skipped` and returns the already restricted fallback
immediately, without launching a duplicate replacement. This keeps path choice
and stream isolation unchanged, and only removes the added wait delay for later
page-burst streams. Validation passed: Python compile, parser unit test,
`python3 -m unittest tests.test_browser_quality tests.test_arti_quality_config`
(`181` tests), static Arti quality config (`74` checks), Rust fmt check,
`cargo test -p tor-circmgr bad_health --manifest-path upstream/arti/Cargo.toml`
(`7` tests), and release Arti build.

Guard proof:
`results/browser-compare-20260612T193549/browser-compare.json`, with analyzer
output at `results/browser-compare-20260612T193549/analysis.md`, reran the
same Tor Project homepage `--extra-arti-exit-select-bad-health-hedge-ms 800`
profile for `3` cold interleaved runs. Quality passed. The guard fired:
`bad health pending wait skipped` appeared for assigned-stream counts `2..5`;
there were no bad-health pending-wait wins or pending-wait timers, and hedge
builds could still win later. This is an improvement over the prior hedge
proof but still not a speed win. The hedge profile median load was
`6570.343ms` versus base Arti `6261.456ms` and local C Tor `4364.398ms`; paired
A/B against base won only `1/3` loads. Max load improved versus base
(`7171.784ms` versus `7874.882ms`), but the analyzer still flags
`paired median slower, summary median slower, low paired wins`. Decision: keep
the guard because it removes a proven harmful wait shape, but do not promote
the bad-health hedge profile. The next useful source work is selected-circuit
DATA-gap/resource-queue proof, not more bad-health waiting.

Assigned-stream cap proof:
`results/browser-compare-20260612T194331/browser-compare.json`, with analyzer
output at `results/browser-compare-20260612T194331/analysis.md`, tested
existing load-aware assigned caps `4` and `3` on the Tor Project homepage for
`3` cold interleaved runs. Quality passed, but neither cap is a source-change
win against base Arti. Cap `4` improved max-load tail versus base
(`5095.824ms` versus `8176.876ms`) and beat local C Tor in this window, but it
lost to base Arti on median load: `5034.637ms` versus `3727.510ms`, with paired
A/B wins only `1/3`. Cap `3` was worse: median load `5961.406ms`, max load
`9450.646ms`, and paired A/B wins only `1/3`. The analyzer flags both profiles
with `paired median slower, summary median slower, low paired wins`; cap `3`
also has `max tail worse`. Decision: do not add or promote an assigned-stream
cap from this proof. The remaining useful path is slow onion/DATA-gap proof:
all profiles still show slow onion connects, and cap `4` still has a selected
circuit with late Tor data and no local pending/window block.

Fresh load-aware/health-aware selector proof:
`results/browser-compare-20260612T195250/browser-compare.json`, with analyzer
output at `results/browser-compare-20260612T195250/analysis.md`, retested pure
load-aware and health-aware selection on the Tor Project homepage for `3` cold
interleaved runs. Quality passed. Both selector profiles beat base Arti on all
paired page loads: health-aware median load `4649.691ms` versus base
`7475.957ms`, paired median delta `-3206.712ms`, max-load delta
`-3878.014ms`; pure load-aware median load `4839.529ms`, paired median delta
`-2719.630ms`, max-load delta `-3619.022ms`. Health-aware also beat local C Tor
by page-load median in this window (`4649.691ms` versus `4873.976ms`). This is
useful evidence that selector health can fix a large homepage burst. Decision:
do not promote global health-aware or load-aware from this one-target proof,
because same-day two-target proof already showed global health-aware can hurt
Tor check. The next safe path is a narrower trigger: use health-aware choice
only for the large resource-burst shape, not for small pages.

Health-aware min-assigned gate proof:
Added default-off lab knob `TORFAST_EXIT_SELECT_HEALTH_AWARE_MIN_ASSIGNED`.
When set with health-aware selection, it only lets health-aware override the
assignment choice after the assignment-selected circuit has at least the given
assigned-stream count. Validation passed: Python compile, focused runner and
quality-config unit tests, static Arti quality config (`75` checks), release
Arti build, and focused Rust selector test
`health_aware_min_assigned_gates_health_candidate`.

Fresh proof:
`results/browser-compare-20260612T201207/browser-compare.json`, with analyzer
output at `results/browser-compare-20260612T201207/analysis.md`, tested
`--extra-arti-exit-select-health-aware-min-assigned 2` on the Tor Project
homepage and Tor check for `3` cold interleaved runs. Quality passed. Against
base Arti, the gated profile improved median load on both targets:
`4007.694ms` versus `5131.345ms` on the homepage and `1865.625ms` versus
`1936.006ms` on Tor check. Paired A/B load wins were `2/3` on both targets.
This is better than global health-aware for Tor check in the earlier two-target
run, but it is still not promotable: max-load tail got worse on both targets
(`+229.120ms` homepage, `+945.334ms` Tor check), boot was much slower
(`23.314s` versus base `12.796s`), and Tor check was still `44.3%` slower than
local C Tor by median load. Decision: keep the knob lab-only. Next useful work
is to reduce resource queue / DATA-gap tail before considering this selector
shape for promotion.

Fresh broad directory combo proof:
`results/browser-compare-20260612T201846/browser-compare.json`, with analyzer
output at `results/browser-compare-20260612T201846/analysis.md`, reran the
directory source-spread + pending-spread + early-usable + load-aware +
partial-retry chunking profile on Tor check, the Tor Project homepage, and the
download page for `5` cold interleaved runs. Quality passed. This is the best
current broad proof, but it is still not promotion-safe.

Against base Arti, the candidate booted much faster (`7.699s` versus
`32.406s`), had no boot directory failure signals, won paired page loads on
all Tor check runs (`5/5`), most homepage runs (`4/5`), and most download runs
(`3/5`), and lowered max-load tails on all three targets. Median load improved
on Tor check (`1867.964ms` versus `2739.291ms`) and the homepage (`4285.683ms`
versus `6643.099ms`). The download summary median was slightly slower than
base Arti (`5389.701ms` versus `5272.854ms`), even though paired median load
and max tail were better.

Against local C Tor, the candidate was faster by boot+load on all three
targets and faster by median load on the homepage (`22.8%`) and download page
(`13.5%`). It still lost Tor check by median load (`31.8%` slower), and the
promotion blocker table still flags `slower than C Tor`, `slow onion/data gap`,
and `slow hostname stream`; next proof remains `stream gap proof`. Decision:
keep this profile as the strongest lab-only broad candidate. Next step is a
byte-timing stream-gap run for the same profile before making another source
change.

Byte-timing broad directory combo proof:
`results/browser-compare-20260612T202757/browser-compare.json`, with analyzer
output at `results/browser-compare-20260612T202757/analysis.md`, reran the
same broad directory combo with `--arti-socks-relay-byte-timing` for `3` cold
interleaved runs on Tor check, the Tor Project homepage, and the download
page. Quality passed, but this rejects the broad profile as a promotion path.

Against base Arti, the combo lost paired median load on all three targets:
Tor check `+1829.827ms` with `0/3` paired load wins, homepage `+1002.866ms`
with `1/3` wins, and download `+2575.422ms` with `0/3` wins. It also worsened
max-load tail on Tor check (`+3535.826ms`) and download (`+6677.267ms`).
Against local C Tor it still lost page-load median on Tor check (`202.7%`
slower) and download (`18.3%` slower), even though boot+load was faster.

The useful proof is the cause shape. The analyzer tied the worst download loss
to `single selected circuit queue`: `Circ 3.68` had max fetch-to-request queue
`7766.822ms` for `tor-browser-mobile-window/png/TBA10.0.png`. The queue-choice
summary says the combo had `only selected open` rows with up to `11` selected
assigned streams on the homepage and `6` on the download page, plus some
`better-health alternative` rows. Relay byte timing did not show a simple
missing-byte fix; the slow rows are mostly selector/capacity-use problems.
Decision: do not promote this broad directory combo. The next useful live
proof is a broader repeat of the narrower `healthy-over-cold` selector guard,
not more broad same-isolation capacity tuning.

Broad healthy-over-cold guard repeat:
`results/browser-compare-20260612T203626/browser-compare.json`, with analyzer
output at `results/browser-compare-20260612T203626/analysis.md`, reran
`--extra-arti-exit-select-healthy-over-cold-min-assigned 1` on Tor check, the
Tor Project homepage, and the download page for `5` cold interleaved runs.
Quality passed, but this rejects the threshold-`1` guard as a broad speed fix.

Against base Arti, the guard lost Tor check and homepage. Tor check paired
median load delta was `+8.298ms` with only `2/5` paired load wins, summary
median load was worse (`2029.234ms` versus `1658.815ms`), and max tail was
worse by `+879.177ms`. Homepage was a hard loss: paired median load delta
`+3357.051ms`, only `1/5` paired load wins, summary median `7041.506ms` versus
base `4578.654ms`, and max tail worse by `+3293.266ms`. Download was the only
partial win: paired median load improved by `-219.344ms` with `4/5` wins and
max tail improved by `-504.784ms`, but summary median was still slightly worse
than base (`5057.622ms` versus `4720.897ms`).

Against local C Tor, the guard still lost Tor check page-load median by
`50.4%`. It beat local C Tor page-load median on homepage (`7.5%`) and
download (`17.2%`), but boot+load was slower on all three targets. The analyzer
kept the same blocker shape: `boot slower`, `slower than C Tor`,
`slow onion/data gap`, and `slow hostname stream`. The selector move-risk table
saw no useful selector moves in the captured logs and labels the homepage loss
as `no selector move; more connect wait`.

Decision: keep `TORFAST_EXIT_SELECT_HEALTHY_OVER_COLD_MIN_ASSIGNED` lab-only
and do not promote threshold `1`. The next source work should not stack another
selector on top. It should either improve the baseline path that already beat
local C Tor page-load on homepage/download, or add stronger low-log proof for
why slow CONNECT/onion streams remain on Tor check without changing privacy
rules.

Low-log CONNECT phase proof:
`upstream/arti/crates/arti-client/src/client.rs` now emits slow successful
normal-exit and onion-service CONNECT phase rows at `INFO`. Normal exit rows
split slow CONNECT into tunnel acquisition and BEGIN completion. Onion rows now
do the same with `torfast hs client timing tunnel ready` and
`torfast hs client timing begin stream finished`, including `tunnel_elapsed_ms`
and `begin_phase_ms`. This is diagnostic only; it does not change circuit
choice, stream behavior, or privacy rules. The analyzer now prints HS client
begin phase medians and max.

Validation passed:
`python3 -m unittest tests.test_arti_quality_config`,
focused `tests.test_browser_quality` parser/signal tests,
`python3 tools/check_arti_quality_config.py --arti-root upstream/arti --arti-bin upstream/arti/target/release/arti`
with `76` checks, `cargo check -p arti-client`, and
`cargo build --release -p arti`.

Focused Tor-check proof
`results/browser-compare-20260612T205659/browser-compare.json`, with analyzer
output at `results/browser-compare-20260612T205659/analysis.md`, passed quality
for `3` cold interleaved runs on `https://check.torproject.org/`. The new HS
rows were live: one onion tunnel took `2302ms`, BEGIN phase took `636ms`, and
there were no SOCKS CONNECT rows at or above `1s` in that small sample. Arti
was faster than local C Tor by elapsed and boot+load, but still `21.1%` slower
by median page load on Tor check. This proves the logging path, not a speed
win.

Broader 3-target proof
`results/browser-compare-20260612T205904/browser-compare.json`, with analyzer
output at `results/browser-compare-20260612T205904/analysis.md`, reproduced the
old slow-CONNECT shape and failed quality because Arti download run `1` timed
out after `120s`. The failed-run cause table labels it `connect wait` with one
slow onion CONNECT: timing id `15`, connect `4525ms`. Its lifecycle rows show
`DATA delivered, no EOF`, `535ms` BEGIN-to-CONNECTED, `714ms` DATA-to-DATA, and
no queue-full or stream-gone signal. The same failed run also hit a
default-off partial-idle timeout: `10000ms` timeout, event elapsed `16112ms`,
last Tor byte `5918ms`, idle after Tor byte `10194ms`, `3527` Tor bytes, and
no active browser resource matched at timeout.

The new phase rows explain the slow CONNECTs better. The one slow hostname
CONNECT was all tunnel wait: `1553ms` tunnel, `0ms` BEGIN phase. Onion CONNECTs
were mostly HS tunnel acquisition, not BEGIN delay: HS median tunnel `3988ms`,
median begin `3760ms`, median begin phase `536ms`, max begin phase `622ms`.
Individual retained rows show onion tunnel waits from `2495ms` to `4780ms` and
BEGIN phases from `393ms` to `622ms`.

Even with one failed Arti run, successful-run medians beat local C Tor on all
three targets in that sample: Tor check `28.8%` faster by median load,
homepage `42.7%` faster, and download `40.3%` faster. But quality failed, so
there is no promotion. Next source work should focus on HS tunnel acquisition
latency and the partial-idle/no-client-abandon path, not another exit selector
stack.

HS-pool netdir retry fix:
`upstream/arti/crates/tor-circmgr/src/hspool.rs` now retries the background
hidden-service stem pool after `1s` when the first wakeup happens before timely
netdir is ready. The normal idle delay stays `30s`. This is a small startup
fix: it does not change path length, relay choice rules, stream isolation, or
browser behavior. Static quality config now checks this guard, raising the
current check count to `77`.

Validation passed:
`cargo fmt --package tor-circmgr --package arti-client`,
Python compile for the touched tools/tests,
`python3 -m unittest tests.test_arti_quality_config`,
`python3 tools/check_arti_quality_config.py --arti-root upstream/arti --arti-bin upstream/arti/target/release/arti`,
`cargo check -p tor-circmgr -p arti-client`, and
`cargo build --release -p arti`.

Broad proof `results/browser-compare-20260612T211603/browser-compare.json`,
with analyzer output at
`results/browser-compare-20260612T211603/analysis.md`, passed quality across
Tor check, the Tor Project homepage, and the download page for `3` cold
interleaved runs. Compared with the failed run before the fix, slow onion
CONNECT rows dropped from `5` to `1`, and there was no Arti timeout. It is still
not promotion-safe: Arti lost page-load median to local C Tor on all three
targets, with blockers `slower than C Tor`, `resource queue`,
`slow onion/data gap`, and `slow hostname stream`. Boot+load was faster than
local C Tor on all three targets in that window, but that is not enough for a
quality-safe speed claim.

Focused hspool proof
`results/browser-compare-20260612T212307/browser-compare.json`, with analyzer
output at `results/browser-compare-20260612T212307/analysis.md`, passed quality
on the Tor Project homepage and download page with hspool debug logs enabled.
It proves the mechanism: `11` hspool stem reuses, `3` background stems ready,
`0` on-demand starts, and `0` hspool failures. Arti beat local C Tor by raw
median load on both targets (`4471.244ms` versus `8442.186ms` homepage,
`4204.493ms` versus `5669.890ms` download), but boot+load still lost because
Arti boot was slower (`15.896s` versus `11.501s`). Remaining blockers are
`boot slower`, `slow onion/data gap`, and `slow hostname stream`; the next
proof should target boot/directory time and the remaining CONNECT stream gap.

Stream-ready DATA coalescing proof:
`upstream/arti/crates/tor-proto/src/client/stream/data.rs` now has a
default-off lab knob, `TORFAST_STREAM_READY_DATA_COALESCE_BYTES`, bounded to
`498..65536`. When set, `DataReaderInner` drains already queued DATA cells into
one local stream read up to the bound; it only does this when
`StreamReceiver::next_queued_msg_is_data()` proves the next visible queued
message is DATA. `tools/run_browser_compare.py` exposes this as
`--extra-arti-stream-ready-data-coalesce-bytes` and records the profile as
`arti_release_browser_streamreadycoalesceN`.

Validation passed:
`python3 -m unittest tests.test_browser_quality`,
`python3 -m py_compile tools/run_browser_compare.py tools/check_arti_quality_config.py tests/test_browser_quality.py`,
`python3 tools/check_arti_quality_config.py`,
`rustfmt --edition 2021 --check crates/tor-proto/src/client/stream/data.rs crates/tor-proto/src/stream/raw.rs`,
`cargo test -p tor-proto stream_ready_data_coalesce_bytes_is_default_off_and_bounded`,
and `cargo build --release -p arti`. The static quality guard now has `82`
checks and no failures.

Browser proof `results/browser-compare-20260613T083550/browser-compare.json`,
with analyzer output at `results/browser-compare-20260613T083550/analysis.md`,
passed quality but rejects promotion. Default Arti loaded the download page in
`5306.571ms`; `streamreadycoalesce4096` loaded in `5398.779ms`; local C Tor
loaded in `7366.845ms`. The candidate lost paired load `0/1` and was `+92.208ms`
slower than default Arti. Queue shape also worsened: max tagged connection queue
rose from `1733.368ms` to `3283.399ms`, queued rows at least `1000ms` rose from
`17` to `20`, total tagged queue rose from `27550.551ms` to `42850.857ms`, and
late queue A/B reported `+1550.031ms` max queue delta. Neutral byte tap did not
show a useful tail fix: median max data gap rose from `300.266ms` to
`434.642ms`. Keep this as negative proof; draining ready DATA cells alone is
not the speed win.

HS state proof retention:
`crates/arti-client/src/client.rs` now emits `torfast hs state timing client
wrapper start/finished` around the hidden-service tunnel wait. `tor-hsclient`
state logs now cover cache hits, task spawn/wait/finish, and tunnel return.
`tor-hsclient` connect proof rows are `INFO`, and
`tools/run_browser_compare.py` keeps HS proof rows under the `1000` signal-line
cap. This is proof-only; it does not change path choice, relay rules, stream
isolation, or browser behavior.

Validation passed:
`python3 -m py_compile tools/analyze_browser_compare.py tools/run_browser_compare.py tests/test_browser_quality.py tools/check_arti_quality_config.py`,
`python3 -m unittest tests.test_browser_quality` (`203` tests),
`python3 tools/check_arti_quality_config.py` (`82` checks, no failures),
`rustfmt --edition 2021 --check crates/arti-client/src/client.rs crates/tor-hsclient/src/state.rs crates/tor-hsclient/src/connect.rs`,
and `cargo build --release -p arti`.

Browser proof `results/browser-compare-20260613T090904/browser-compare.json`,
with analyzer output at `results/browser-compare-20260613T090904/analysis.md`,
passed quality. Arti loaded the download page in `4370.515ms`; local C Tor
loaded in `3988.209ms`, so this is not a speed promotion. The important proof
is the slow onion CONNECT join: timing id `3` connected in `2784ms`; HS tunnel
acquisition was `2243ms`; BEGIN phase was `540ms`; and the new
`Torfast HS State Timings` table retained wrapper, cache, spawn, wait, task
done, and returned rows. Next source work should target HS tunnel acquisition
and boot/directory time, not local DATA coalescing.

HS descriptor split proof:
`crates/tor-hsclient/src/connect.rs` now emits
`torfast hs timing descriptor ready` and
`torfast hs timing descriptor refetch ready`. `tools/analyze_browser_compare.py`
prints descriptor counts and median descriptor time in `Torfast HS Timings`.
This is proof-only; it does not change descriptor choice, HSDir choice, path
rules, INTRODUCE behavior, stream isolation, or browser behavior.

Validation passed:
`python3 -m py_compile tools/analyze_browser_compare.py tools/run_browser_compare.py tests/test_browser_quality.py tools/check_arti_quality_config.py`,
focused HS parser/retention tests,
`python3 -m unittest tests.test_browser_quality` (`203` tests),
`python3 tools/check_arti_quality_config.py` (`82` checks, no failures),
`rustfmt --edition 2021 --check crates/tor-hsclient/src/connect.rs crates/tor-hsclient/src/state.rs crates/arti-client/src/client.rs`,
and `cargo build --release -p arti`.

Direct onion proof `results/browser-compare-20260613T091712/browser-compare.json`,
with analyzer output at `results/browser-compare-20260613T091712/analysis.md`,
passed quality, but rejects promotion. Arti loaded the onion download page in
`9038.328ms`; local C Tor loaded it in `5662.739ms`. The split is now visible:
descriptor rows `2`, median descriptor `1462ms`; median HS tunnel `4662ms`;
median BEGIN phase `382ms`, max `457ms`. The two slow onion CONNECT rows were
still tunnel acquisition: timing id `2` was `4766ms` connect with `4459ms`
tunnel and `307ms` BEGIN phase; timing id `3` was `5322ms` connect with
`4865ms` tunnel and `457ms` BEGIN phase. The run also kept the resource queue
blocker (`+3375.589ms` load delta, `+1300.026ms` DOM-to-load delta), so the
next source work should target HS descriptor/tunnel acquisition plus the later
page resource queue, not BEGIN handling.

HS descriptor fetch subphase proof:
`crates/tor-hsclient/src/connect.rs` now emits descriptor fetch subphase rows:
HSDir circuit ready, BEGINDIR stream ready, descriptor response ready, and
descriptor parsed. `tools/analyze_browser_compare.py` prints these in
`Torfast HS Descriptor Fetch Timings`. This is proof-only; it does not change
descriptor choice, HSDir choice, circuit path rules, retry rules, stream
isolation, or browser behavior.

Validation passed:
`python3 -m py_compile tools/analyze_browser_compare.py tests/test_browser_quality.py tools/run_browser_compare.py`,
focused HS parser/retention tests,
`python3 -m unittest tests.test_browser_quality` (`203` tests),
`python3 tools/check_arti_quality_config.py` (`82` checks, no failures),
`rustfmt --edition 2021 --check crates/tor-hsclient/src/connect.rs`,
`git -C upstream/arti diff --check`,
and `cargo build --release -p arti`.

Direct onion proof `results/browser-compare-20260613T092626/browser-compare.json`,
with analyzer output at `results/browser-compare-20260613T092626/analysis.md`,
passed quality and proved the new descriptor subphase rows are live. Arti loaded
in `10755.099ms`; local C Tor loaded in `67872.814ms`, so this one-run sample is
not promotion proof because local C Tor had a large outlier. The mechanism split
is still useful: descriptor rows `2`, median descriptor `1151.5ms`; HSDir
circuit median `341ms`; BEGINDIR stream median `342ms`; descriptor response
median `771.5ms`; parse median `773.5ms`. Median HS tunnel was `4981.5ms` and
median BEGIN phase was `450ms`, so the remaining cold onion delay is mostly
after descriptor fetch and before BEGIN. Next source work should target
hidden-service tunnel acquisition after descriptor fetch, and add failed
descriptor-attempt rows if retry cost needs to be separated.

HS per-attempt connect timing proof:
`crates/tor-hsclient/src/connect.rs` now gives each HS connect attempt a local
`hs_connect_id` plus shared `connect_elapsed_ms`. The analyzer prints
`Torfast HS Attempt Timings`, grouped by that id, so descriptor, intro, rend,
and established rows can be read on one clock. This is proof-only; it does not
change path choice, retry rules, stream isolation, or browser behavior.

Validation passed:
`python3 -m py_compile tools/analyze_browser_compare.py tests/test_browser_quality.py tools/run_browser_compare.py`,
focused HS parser/retention tests,
`python3 -m unittest tests.test_browser_quality` (`203` tests),
`python3 tools/check_arti_quality_config.py` (`82` checks, no failures),
`rustfmt --edition 2021 --check crates/tor-hsclient/src/connect.rs`,
`git -C upstream/arti diff --check`,
and `cargo build --release -p arti`.

Direct onion proof `results/browser-compare-20260613T094026/browser-compare.json`,
with analyzer output at `results/browser-compare-20260613T094026/analysis.md`,
passed quality but rejects speed promotion. Arti loaded in `9008.722ms`; local C
Tor loaded in `6542.820ms`, so Arti was `2465.902ms` slower on page load.
Boot plus load still favored Arti (`6.205s` boot versus C Tor `15.573s` boot),
but page-load speed does not promote. The grouped HS attempt rows show attempt
`1` finished descriptor parse at `879ms`, reached intro ack at `2625ms`, rend2
at `2892ms`, and established at `2893ms`; post-descriptor setup was `2014ms`.
Attempt `2` parsed descriptor at `1926ms`, reached intro ack at `2854ms`, rend2
at `3143ms`, and established at `3143ms`; post-descriptor setup was `1217ms`.
The later BEGIN phase was smaller (`383..540ms`). Next source work should target
hidden-service tunnel acquisition after descriptor fetch, especially intro
circuit readiness before intro ack, not descriptor parsing or BEGIN handling.

HS-pool on-demand grace lab proof:
`upstream/arti/crates/tor-circmgr/src/hspool.rs` now has a default-off,
bounded lab knob, `TORFAST_HSPOOL_ON_DEMAND_POOL_GRACE_MS`. Valid lab values
wait up to `1000ms` for a ready background HS stem before launching an on-demand
stem. Default `0` keeps normal behavior. The path keeps the same target,
family, vanguard, and suitability checks; it only changes timing when the env
is set. `tools/run_browser_compare.py` exposes this with
`--extra-arti-hspool-on-demand-grace-ms`, and the static quality check now
covers the default-off and bounds guard.

Validation passed:
`python3 -m py_compile tools/run_browser_compare.py tools/check_arti_quality_config.py tests/test_browser_quality.py`,
focused browser-quality tests,
`python3 -m unittest tests.test_browser_quality` (`203` tests),
`python3 tools/check_arti_quality_config.py` (`83` checks, no failures),
`rustfmt --edition 2021 --check crates/tor-circmgr/src/hspool.rs crates/tor-circmgr/src/hspool/pool.rs`,
`git -C upstream/arti diff --check`,
and `cargo build --release -p arti`.

Direct onion proof `results/browser-compare-20260613T095400/browser-compare.json`,
with analyzer output at `results/browser-compare-20260613T095400/analysis.md`,
passed quality but rejects promotion. Base Arti loaded in `7738.769ms`; the
`50ms` grace profile loaded in `8642.815ms`, so it lost to base by `904.046ms`.
The `150ms` profile loaded in `6265.188ms`, but HsPool rows show it did not use
the new grace path: `0` on-demand starts and `6` background-ready reuses. The
`50ms` profile did use the on-demand path (`3` on-demand starts, `3` ready,
`0` background ready), but it was slower.

Repeat proof `results/browser-compare-20260613T095613/browser-compare.json`,
with analyzer output at `results/browser-compare-20260613T095613/analysis.md`,
also passed quality and rejects promotion harder. Base Arti loaded in
`9373.039ms`; local C Tor loaded in `7115.191ms`; `hspoolgrace150ms` loaded in
`67565.351ms`. The A/B delta against base was `+58192.312ms`, with a
`64658ms` onion CONNECT. Decision: serially waiting for the pool before
on-demand launch is the wrong speed shape. Keep it lab-only. Next source work
should race a background ready stem against on-demand launch without adding
delay, or improve preemptive HS pool readiness before the request arrives.

HS-pool no-delay race lab proof:
`upstream/arti/crates/tor-circmgr/src/hspool.rs` now has a second default-off,
bounded lab knob, `TORFAST_HSPOOL_ON_DEMAND_POOL_RACE_MS`. Valid lab values are
capped at `1000ms`. The path starts the normal on-demand stem launch right away,
then races it against a ready background HS stem for the configured window. If
the pool wins, it uses the pool stem. If the race window expires, it waits for
the already-started on-demand launch. Default `0` keeps normal behavior. The
path keeps the same target, family, vanguard, and suitability checks.
`tools/run_browser_compare.py` exposes this with
`--extra-arti-hspool-on-demand-race-ms`, and the static quality check covers the
default-off and bounds guard.

Validation passed:
`python3 -m py_compile tools/run_browser_compare.py tools/check_arti_quality_config.py tests/test_browser_quality.py`,
focused browser-quality tests,
`python3 -m unittest tests.test_browser_quality` (`203` tests),
`python3 tools/check_arti_quality_config.py` (`84` checks, no failures),
`rustfmt --edition 2021 --check crates/tor-circmgr/src/hspool.rs`,
`git -C upstream/arti diff --check`,
and `cargo build --release -p arti`.

Direct onion proof `results/browser-compare-20260613T101211/browser-compare.json`,
with analyzer output at `results/browser-compare-20260613T101211/analysis.md`,
passed quality but does not promote. Base Arti loaded in `7597.155ms`; local C
Tor loaded in `10818.658ms`; `hspoolrace150ms` loaded in `4408.927ms`; and
`hspoolrace500ms` loaded in `10461.103ms`. The `150ms` profile beat base by
`3188.228ms`, but retained HsPool rows showed no race mechanism proof:
`0` on-demand starts and `6` background-ready reuses. Treat that as old
pool-readiness or sample noise, not proof of the new race. The `500ms` profile
did exercise the race path, but it lost to base by `2863.948ms` and had a
resource-queue blocker.

Repeat proof `results/browser-compare-20260613T101413/browser-compare.json`,
with analyzer output at `results/browser-compare-20260613T101413/analysis.md`,
also passed quality and rejects promotion. Base Arti median load was
`5133.007ms`; local C Tor was `5988.876ms`; `hspoolrace150ms` was
`9381.685ms`. The race profile lost all `3` paired runs, with `+4248.678ms`
summary median load delta and `+5179.725ms` paired median load delta against
base Arti. Raw retained profile text showed the race did start (`25` race
starts), but the pool never won (`0` pool reuses, `25` waits for the already
started on-demand path). Decision: the no-delay race is safer than serial grace,
but it still does not make this page faster unless the background HS pool is
already ready. Keep it lab-only. Next source work should improve HS pool
readiness before the request arrives or target hidden-service tunnel setup after
descriptor fetch.

HS-pool background-start delay harness proof:
`tools/run_browser_compare.py` now exposes the existing source knob
`TORFAST_HSPOOL_BACKGROUND_START_DELAY_MS` through
`--extra-arti-hspool-background-start-delay-ms`. The source default remains
`1000ms`, valid harness values are bounded to `0..60000ms`, and the runner adds
`tor_circmgr=debug` for this profile so compact browser runs keep HsPool rows.
The static quality check now covers the bounded source env and default.

Validation passed:
`python3 -m py_compile tools/run_browser_compare.py tools/check_arti_quality_config.py tests/test_browser_quality.py`,
focused browser-quality tests, and
`python3 tools/check_arti_quality_config.py` (`85` checks, no failures). No
Rust source changed for this harness patch.

Direct onion proof `results/browser-compare-20260613T102523/browser-compare.json`,
with analyzer output at `results/browser-compare-20260613T102523/analysis.md`,
passed quality. In the one-run sample, base Arti loaded in `21093.151ms`;
`hspoolstart0ms` loaded in `9367.844ms`; `hspoolstart250ms` loaded in
`11036.029ms`; local C Tor loaded in `7633.452ms`. This looked promising only
because the base Arti run had a large resource-queue tail.

Repeat proof `results/browser-compare-20260613T102711/browser-compare.json`,
with analyzer output at `results/browser-compare-20260613T102711/analysis.md`,
also passed quality and rejects promotion. Base Arti median load was
`5170.400ms`; `hspoolstart0ms` was `7121.930ms`; local C Tor was `6770.750ms`.
The `0ms` startup-delay profile won only `1/3` paired runs and was
`+1951.530ms` slower than base Arti by summary median load (`+1564.039ms`
paired median). Decision: starting the HS pool immediately is safe to test, but
it does not fix the measured slow page. Keep it as harness-only lab evidence.
Next source work should target the remaining slow onion connect / HS tunnel
setup path rather than just waking the pool earlier.

HS rendezvous prebuild-before-descriptor lab proof:
`upstream/arti/crates/tor-hsclient/src/connect.rs` now has a default-off lab
knob, `TORFAST_HS_REND_PREBUILD_BEFORE_DESC`. When set, the client starts the
normal rendezvous setup while the onion-service descriptor fetch is still in
flight. If that early rendezvous fails, it logs the failure and falls back to
the normal descriptor-then-rendezvous path. Default behavior is unchanged. This
does not add intro attempts, does not change descriptor choice, relay choice,
path rules, INTRODUCE1 content, or stream isolation; it only starts the normal
rendezvous builder earlier for lab proof.

`tools/run_browser_compare.py` exposes the knob as
`--extra-arti-hs-rend-prebuild-before-desc`, records
`arti_hs_rend_prebuild_before_desc`, and adds `tor_hsclient=debug` so compact
browser runs retain `torfast hs timing rend prebuild before descriptor` rows.
The static quality check now covers the default-off env and fallback path.

Validation passed:
`python3 -m py_compile tools/run_browser_compare.py tools/check_arti_quality_config.py tests/test_browser_quality.py tests/test_arti_quality_config.py`,
focused browser-quality tests,
`python3 -m unittest tests.test_browser_quality` (`203` tests),
`python3 tools/check_arti_quality_config.py` (`86` checks, no failures),
`cargo test -p tor-hsclient --all-features hs_rend_prebuild_before_desc_env_is_default_off --manifest-path upstream/arti/Cargo.toml`,
`rustfmt --edition 2021 crates/tor-hsclient/src/connect.rs`,
`cargo build --release -p arti --manifest-path upstream/arti/Cargo.toml`, and
`git -C upstream/arti diff --check`.

One-run proof `results/browser-compare-20260613T104056/browser-compare.json`,
with analyzer output at `results/browser-compare-20260613T104056/analysis.md`,
passed quality and showed the mechanism firing. Base Arti loaded in
`11549.987ms`; the `hsrendpredesc` profile loaded in `4122.374ms`; local C Tor
loaded in `7387.323ms`. Logs show `rend prebuild before descriptor enabled`,
then `rendezvous established` before descriptor ready, then
`rend prebuild before descriptor ready`.

Repeat proof `results/browser-compare-20260613T104210/browser-compare.json`,
with analyzer output at `results/browser-compare-20260613T104210/analysis.md`,
also passed quality. The `hsrendpredesc` profile was better by summary median
load (`6063.357ms` versus base Arti `6454.160ms` and local C Tor
`6858.863ms`) and better than local C Tor on median load by `11.6%`. The HS
mechanism moved in the right direction: median HS tunnel dropped from
`3131ms` to `1917ms`, median rendezvous-established time from `320.0ms` to
`171.5ms`, and max HS state task from `10985ms` to `3784ms`.

Do not promote yet. The direct A/B paired result against base Arti was mixed:
the candidate won only `1/3` paired runs and paired median load was
`+408.932ms` slower, even though summary median load was `390.803ms` faster.
Keep it lab-only. Next proof should run more paired samples or combine this
with a cleaner HS-tunnel target before making any default change.

Five-run follow-up proof
`results/browser-compare-20260613T105207/browser-compare.json`, with analyzer
output at `results/browser-compare-20260613T105207/analysis.md`, passed quality
and rejects promotion. Base Arti median load was `7683.071ms`; local C Tor was
`5029.269ms`; `hsrendpredesc` was `9624.547ms`. Against base Arti, the
candidate won only `2/5` paired runs and had `+3442.063ms` paired median load
delta (`+1941.476ms` summary median load delta). Against local C Tor, it won
`0/5` paired runs and was `+3813.695ms` slower by paired median load. The HS
timing did not reproduce the earlier gain: median HS tunnel was `3739.5ms`
versus base `3726ms`, median descriptor was worse (`1446.5ms` versus
`1288ms`), and median intro ack was worse (`1099.5ms` versus `722ms`).
Decision: keep `TORFAST_HS_REND_PREBUILD_BEFORE_DESC` lab-only and do not
promote. The next source target should not be earlier rendezvous setup alone;
focus on the remaining C Tor gap in HS tunnel/intro timing and resource-queue
tails.

HS-pool guarded-stem target lab proof:
`upstream/arti/crates/tor-circmgr/src/hspool/pool.rs` now has a bounded lab
override, `TORFAST_HSPOOL_GUARDED_STEM_TARGET`, for the guarded stem target.
The local default target remains `2`; lab values are accepted only from `2`
through `16`, and `0`/`off`/invalid values fall back to the default. The runner
exposes same-window A/B profiles with
`--extra-arti-hspool-guarded-stem-target`.

Fresh one-run proof `results/browser-compare-20260613T113902/browser-compare.json`,
with analyzer output at `results/browser-compare-20260613T113902/analysis.md`,
passed quality. The `hspoolguarded6` profile launched `6` guarded circuits and
beat base Arti in this sample: load `9528.209ms` versus base Arti
`10727.941ms`, paired load delta `-1199.732ms`, and boot+load delta
`-9058.732ms`. It still lost to local C Tor, which loaded in `5830.591ms`;
the guarded profile was `+3697.618ms` slower by paired load. The analyzer still
blocks promotion with `boot directory, slower than C Tor, resource queue, slow
onion/data gap`, and the slow onion CONNECT rows remain tunnel-acquisition
heavy (`4002ms` and `3854ms`). Keep this lab-only. The next proof needs a
repeat or a stronger HS tunnel/resource-tail fix before any promotion claim.

Guarded-target sweep `results/browser-compare-20260613T114503/browser-compare.json`,
with analyzer output at `results/browser-compare-20260613T114503/analysis.md`,
ran `3` cold interleaved download-page samples for guarded targets `4`, `6`,
and `8`. Quality passed. Against base Arti, `hspoolguarded8_3` was the best
page-load row in that run: it won `3/3` paired loads and improved summary
median load by `-2918.124ms` (`8088.441ms` versus base `11006.565ms`).
But it still lost local C Tor by paired median load (`+2265.304ms`), and the
same analyzer still blocked promotion with `slower than C Tor, slow
onion/data gap`. `hspoolguarded4` and `hspoolguarded6_2` also improved summary
median versus base, but both had worse max tails than base. This was useful
directional evidence only, not a speed fix.

Focused warm-cache repeat
`results/browser-compare-20260613T114935/browser-compare.json`, with analyzer
output at `results/browser-compare-20260613T114935/analysis.md`, rejects
`hspoolguarded8`. It passed quality, but lost base Arti `0/5` paired loads:
paired median load delta was `+2352.817ms`, summary median load delta was
`+4719.959ms`, and max load was worse by `+63418.440ms` (`71130.057ms` versus
base `7711.617ms`). It also lost local C Tor `0/5`, with paired median load
delta `+5956.130ms`. The worst run was a `64569ms` onion CONNECT before SOCKS
reply. Decision: do not promote a simple guarded-stem target increase. Keep
`TORFAST_HSPOOL_GUARDED_STEM_TARGET` as lab-only source and use the next work
on HS tunnel acquisition/resource-tail proof, not broader guarded prebuild by
itself.

HS intro-circuit hedge lab proof:
`upstream/arti/crates/tor-hsclient/src/connect.rs` now has a bounded default-off
lab override, `TORFAST_HS_INTRO_CIRCUIT_HEDGE_MS`, for racing one backup normal
intro-circuit acquisition after a delay. Valid lab values are `500` through
`60000`; `0`/`off`/invalid values keep the normal path. The runner exposes this
with `--extra-arti-hs-intro-circuit-hedge-ms` and records
`arti_hs_intro_circuit_hedge_ms`.

Focused warm-cache proof `results/browser-compare-20260613T120718/browser-compare.json`,
with analyzer output at `results/browser-compare-20260613T120718/analysis.md`,
rejects `hsintrohedge1500ms`. Quality passed and the hedge code was exercised:
logs show `intro circuit hedge armed`, one `intro circuit hedge launched`, and
`intro circuit hedge primary won`. It did not improve the page. Against base
Arti, the hedge profile won only `1/3` paired loads, had `+3390.772ms` paired
median load delta, `+1222.599ms` summary median load delta, and a worse max load
tail by `+2261.562ms` (`12339.044ms` versus `10077.482ms`). It still beat local
C Tor by median load in this small run, but less than base Arti did
(`8662.110ms` versus C Tor `9059.490ms`, while base Arti was `7439.511ms`).
Decision: keep this knob lab-only and do not promote a simple intro-circuit
hedge. The next target should focus on the remaining HS tunnel/resource queue
gap, not adding more intro races by itself.

Tagged byte-tap diagnostic after intro hedge:
`results/browser-compare-20260613T121334/browser-compare.json`, with analyzer
output at `results/browser-compare-20260613T121334/analysis.md`, is diagnostic
only and must not be used as speed proof. Quality failed: Arti completed only
`1/3` browser runs, while local C Tor completed `3/3`. The failed Arti runs
ended at Tor Browser `onionServices.descNotFound`, and the analyzer tied both
to slow onion CONNECT waits (`4530ms` and `5951ms` max connect rows).

The one successful Arti run still gave useful exact stream evidence. The
SOCKS reply tag bridged Firefox resources to byte tap, Arti client peer port,
Arti SOCKS timing id, stream id, and circuit. It joined `34` stream resources
on `6` streams over one circuit (`Circ 1.68`). The worst tagged resource queue
was `2366.714ms`, several same-stream resources started `0.000ms` after the
previous response, and relay receive did not show whole-circuit starvation:
the joined streams delivered `461` DATA cells, `225735` bytes, max relay
receive gap `441ms`, and SENDME/windows were not low in the gap context.

Decision: keep this run as failed-quality source evidence only. The next source
target should inspect HS descriptor/tunnel reliability and the exact active
stream/resource tail. Do not add more intro races, selector knobs, scheduler
changes, or SENDME/window changes from this sample alone.

Follow-up analyzer/source proof for the same failed run:
`tools/analyze_browser_compare.py` now prints `Browser Failed Run HS State
Diagnosis` for failed browser runs with HS state rows. It uses the saved
per-run proxy tails to show failed onion SOCKS IDs, wrapper ports, state-task
counts, HS connect IDs, descriptor parse/establish IDs, HSDir `404` rows, and
descriptor-download failures. Replaying
`results/browser-compare-20260613T121334/browser-compare.json` keeps quality
failed, as expected, but now shows the important split directly: the failed
browser requests were port `80` SOCKS connects returning
`OnionServiceNotFound`, while other HS connects in the same failed run window
parsed descriptors, and run `2` also established one HS tunnel. This supports a
narrow next check around isolation-scoped HS descriptor/task reuse or failure
propagation, not broad circuit selection or stream scheduling.

`upstream/arti/crates/tor-hsclient/src/state.rs` now adds a local `state_id`
field to HS state timing rows (`cache hit`, `spawn connect task`, `wait
existing task`, `connect task finished`, `existing task finished`, and `tunnel
returned`). This is instrumentation only; it does not change path choice, relay
choice, circuit length, descriptor choice, isolation, or browser behavior. It is
for the next browser proof so the analyzer can say whether the successful and
failed HS connects were the same isolation/state task or separate ones.

Validation passed: `python3 -m py_compile tools/analyze_browser_compare.py`,
analyzer replay on `results/browser-compare-20260613T121334/browser-compare.json`
(exit `1` because saved quality is still `FAIL`), `rustfmt --edition 2021
--check crates/tor-hsclient/src/state.rs`, and `cargo check -p tor-hsclient
--all-features --manifest-path upstream/arti/Cargo.toml`.

State-id browser proof:
`results/browser-compare-20260613T123334/browser-compare.json`, with analyzer
output at `results/browser-compare-20260613T123334/analysis.md`, reran the
download page after rebuilding release Arti with HS `state_id` timing rows. It
used warm cache, shared Arti warm-cache seed, normal browser concurrency,
browser net logs, byte tap, SOCKS reply bind-port tags, and relay byte timing.
Quality passed: Arti completed `3/3` runs and local C Tor completed `3/3`.

This is not a speed win. Arti median load was `8713.650ms` versus local C Tor
`7556.057ms`, so Arti was `+1157.593ms` slower by median load. Boot+load was
also slower (`12575.650ms` versus `10371.057ms`). The analyzer still blocks
promotion with `slower than C Tor`, `resource queue`, `slow onion/data gap`,
and `partial idle` rows.

The useful proof is the new `Torfast HS State Per-Run` table. In all `3` Arti
runs, port `80` and port `443` used separate HS state records for the same
onion page:

- run `1`: `80->TableIndex(1v1)`, `443->TableIndex(2v1)`
- run `2`: `80->TableIndex(3v1)`, `443->TableIndex(4v1)`
- run `3`: `80->TableIndex(5v1)`, `443->TableIndex(6v1)`

That explains why the earlier failed diagnostic could have a port `80`
`OnionServiceNotFound` while another same-window HS connect parsed a descriptor
or built a tunnel. The source target is now narrower: inspect whether
descriptor fetch/cache can be shared or single-flighted across these separate
HS state records without sharing streams, rendezvous circuits, intro history,
stream isolation, path choice, relay choice, or browser behavior. Do not change
this by default until the privacy/quality argument and browser proof both hold.

Validation passed: `cargo build --release -p arti --manifest-path
upstream/arti/Cargo.toml`, `python3 -m py_compile
tools/analyze_browser_compare.py`, and analyzer replay on
`results/browser-compare-20260613T123334/browser-compare.json` (exit `0`).

Descriptor-share lab proof:
`results/browser-compare-20260613T125354/browser-compare.json`, with analyzer
output at `results/browser-compare-20260613T125354/analysis.md`, tested the
default-off HS descriptor shared-cache profile
`arti_release_browser_hsdescshare`. It used the same warm-cache browser shape
as the state-id proof, plus `--extra-arti-hs-desc-shared-cache`. Quality
passed: base Arti, descriptor-share Arti, and local C Tor all completed `3/3`
runs.

The mechanism worked but is not a speed win. The descriptor-share profile logged
`2` shared descriptor-cache hits and `4` stores. Its descriptor fetch table
dropped HSDir fetch work versus base Arti (`dir circuit` `4` vs `9`,
`response`/`parsed` `4` vs `6`). Two HS attempts returned a descriptor from the
shared cache with `0.000ms` descriptor connect time.

The page result rejects promotion. Descriptor-share median load was
`12413.535ms` versus base Arti `7736.204ms` and local C Tor `4473.435ms`. In
direct A/B against base Arti it won only `1/3` paired loads and was
`+929.136ms` slower by paired median load; summary median load was
`+4677.331ms` worse. The analyzer still blocks it with `slower than C Tor`,
`resource queue`, `slow onion/data gap`, and `partial idle` rows. Keep
`TORFAST_HS_DESC_SHARED_CACHE` lab-only and do not promote descriptor-only
sharing as the next speed path.

Validation passed: `cargo check -p tor-hsclient --all-features --manifest-path
upstream/arti/Cargo.toml`, `cargo build --release -p arti --manifest-path
upstream/arti/Cargo.toml`, `python3 -m py_compile tools/run_browser_compare.py
tools/analyze_browser_compare.py tools/check_arti_quality_config.py`,
`python3 -m unittest tests.test_browser_quality tests.test_arti_quality_config`,
`python3 tools/check_arti_quality_config.py`, and analyzer replay on
`results/browser-compare-20260613T125354/browser-compare.json` (exit `0`).

## Latest Dir-Microdesc Bad-Health Replacement Suppression Lab

`upstream/arti/crates/tor-circmgr/src/mgr.rs` now exposes a default-off lab
switch `TORFAST_DIR_MICRODESC_DISABLE_BAD_HEALTH_REPLACEMENT`. It only
suppresses the `torfast circuit selection bad health replacement` fallback when
the original request is `usage_kind="dir_microdesc"`. Exit selection, normal
directory selection, browser prefs, DNS behavior, path rules, isolation, state
reuse, and default behavior stay unchanged. `tools/run_browser_compare.py` now
wires it as
`--extra-arti-dir-microdesc-source-spread-pending-spread-early-usable-load-aware-no-dir-bad-health-replacement`,
creating profile
`arti_release_browser_mdsrcspreadpendingearlyusable_loadaware_nodirmicrodescbadhealthreplace`.

Validation passed: `python3 -m py_compile tools/run_browser_compare.py
tests/test_browser_quality.py`, `python3 -m unittest tests.test_browser_quality`,
`cargo test -p tor-circmgr bad_health_replacement_state_tracks_later_selection_and_use
--lib --manifest-path upstream/arti/Cargo.toml`, and analyzer replays on
`results/browser-compare-20260621T064124/browser-compare.json` and
`results/browser-compare-20260621T064837/browser-compare.json` (both exit `0`).

Broad A/B proof:
`results/browser-compare-20260621T064124/browser-compare.json`, with analyzer
output at `results/browser-compare-20260621T064124/analysis.md`, compared base
Arti, the current load-aware directory combo, the same combo with
dir-microdesc bad-health replacement disabled, and local C Tor on the cold
three-target gate. Quality passed.

This is not a promotion for the new knob. The existing load-aware combo stayed
best overall of the two Arti combo profiles: boot was `8.834s` versus
`14.035s`, and median page loads on
`check/homepage/download` were `2038.636ms / 4476.544ms / 4467.188ms` versus
`1745.120ms / 5467.678ms / 5607.575ms`. The no-dir-bad-health profile only won
the small check page and lost the homepage and download page badly.

The critical caveat is that this run did not actually hit the targeted source
path. Neither combo profile logged a dir-microdesc bad-health-replacement event
in boot, so this result cannot validate the original root-cause hypothesis; it
only says that blanket suppression is not a clear same-window improvement in a
clean broad window where the fallback never fired.

Quick boot follow-up:
`results/browser-compare-20260621T064837/browser-compare.json`, with analyzer
output at `results/browser-compare-20260621T064837/analysis.md`, reran a
single cold-cache `check.torproject.org` sample for another boot slice. Quality
passed.

This one is also not enough to promote the knob. Load-aware booted in
`19.952s`; the no-dir-bad-health profile booted in `11.545s`; both beat local
C Tor on the one page load. But again neither combo profile logged a
dir-microdesc bad-health-replacement event. Instead both profiles logged the
same `10.003s` `TorAccessFailed` directory channel/build failure during boot.
That makes the faster no-dir sample non-attributable to the new knob.

Decision: keep `TORFAST_DIR_MICRODESC_DISABLE_BAD_HEALTH_REPLACEMENT` lab-only
and do not promote blanket suppression. The better next source lane is a
stricter dir-microdesc gate keyed to the heavy/stale bad snapshot seen in the
slow window (`selected_assigned_streams=5`, `selected_active_streams=3`,
`selected_health_max_gap_ms=7570`) while preserving the fast replacement case
from the good window (`1`, `1`, and `2682` respectively).

## Latest Torfast Warm/Open Hot-Path Import Cut

`tools/launch_torfast_browser.py` now keeps the repeated warm/open runtime path
lighter by avoiding heavy module imports until they are actually needed:

- The old top-level imports of `torfast.browser_defaults`,
  `torfast.dir_cache_seed`, and `torfast.browser_startup_seed` are gone from
  the hot launcher path.
- The launcher now uses a cache-first local Tor Browser default-pref proof
  reader on the normal repeated-open path, then falls back to the shared
  module only if the on-disk cache is missing or stale.
- Lightweight local seed-status readers now cover the normal launch JSON/status
  fields, while the real seed apply/update helpers are imported only inside the
  branches that actually use them.
- The optional stream-isolation probe import stays lazy and default-off.

Validation passed:

- `python3 -m unittest tests.test_launch_torfast_browser tests.test_torfast_cli`
- `python3 -m py_compile tools/launch_torfast_browser.py torfast/cli.py tests/test_launch_torfast_browser.py tests/test_torfast_cli.py`

Direct hot-path proof:

- `torfast.cli.load_launcher_main()` dropped from about `38.558ms` to about
  `10.230ms` after the lazy-helper change on the same machine.
- Saved repeated reused-open proof lives at
  `results/torfast-reused-open-bench-20260625T051448/summary.json`.
- Both saved 12-run replicates held the same Tor behavior: every run kept
  `tor_browser_launch_gate.seconds = 0.0` and `tor_boot.seconds = 0.0` on the
  reused-service `about:tor` path.
- Replicate `r1`: median wall `1.125s`, p90 `1.224s`, max `1.311s`, median
  browser elapsed `1.027s`, median non-browser overhead `0.097s`.
- Replicate `r2`: median wall `1.107s`, p90 `1.122s`, max `1.130s`, median
  browser elapsed `1.026s`, median non-browser overhead `0.077s`.

Decision: keep the lazy-helper hot-path cut. It does not change Tor config,
Tor Browser default-pref requirements, SOCKS isolation, or the reused-service
gate rules, and it produced a small but repeatable repeated-open win on the
real product path.

## Latest Torfast Fast Runtime Entry Path

`torfast/__main__.py` now tries a tiny runtime-only entry path first for the
common product commands (`start`/`open`, `warm`, `prime`, `launch`, `plan`,
and `stop`), then falls back to the old full CLI for help, admin commands, and
anything unusual. The launcher and Tor behavior stay the same; this cut only
changes how `python3 -m torfast ...` reaches the existing launcher.

What changed:

- Added `torfast/fast_runtime.py`, a small parser/builder for the normal
  runtime actions.
- `torfast/__main__.py` now uses that fast path first and imports
  `torfast.cli` only when it still needs the general CLI.
- `pyproject.toml` now points the installed `torfast` console script at
  `torfast.__main__:main` so installed copies pick up the same fast path after
  reinstall.
- Added `tests/test_torfast_main.py` to compare the fast path launcher args
  against the existing CLI and to prove fallback still works for `status`,
  `--help`, and weird or conflicting fast-path argv.

Validation passed:

- `python3 -m unittest tests.test_torfast_main tests.test_torfast_cli tests.test_launch_torfast_browser`
- `python3 -m py_compile torfast/__main__.py torfast/fast_runtime.py torfast/cli.py tests/test_torfast_main.py tests/test_torfast_cli.py tests/test_launch_torfast_browser.py`

Direct hot-path proof:

- Fresh local import timing dropped from about `38.095ms` for
  `import torfast.__main__` on the old path to about `7.895ms` after the fast
  entry cut on the same machine.
- Plain `python3 -m torfast open --help` command-start median dropped from
  about `55.857ms` before this change to about `47.468ms` after it.
- Saved repeated reused-open proof lives at
  `results/torfast-fast-entry-reused-open-bench-20260625T052559/summary.json`.
- That saved proof measures the steady-state reused-open hot path after one
  uncounted priming open, so every saved sample kept both
  `tor_browser_launch_gate.seconds = 0.0` and `tor_boot.seconds = 0.0`.
- Replicate `r1`: median wall `1.101s`, p90 `1.144s`, max `1.147s`, median
  browser elapsed `1.028s`, median non-browser overhead `0.075s`.
- Replicate `r2`: median wall `1.107s`, p90 `1.121s`, max `1.138s`, median
  browser elapsed `1.030s`, median non-browser overhead `0.076s`.
- Against the earlier saved reused-open proof in
  `results/torfast-reused-open-bench-20260625T051448/summary.json`, the
  combined 24-sample median wall moved from about `1.117s` to `1.104s`, and
  the combined median non-browser overhead moved from about `0.081s` to
  `0.075s`.

Decision: keep the fast runtime entry path. It does not touch Tor config, Tor
Browser pref checks, SOCKS isolation, or reused-service gate rules, and it
gives a small steady-state product-path speed win while keeping the old CLI as
the fallback path for everything outside the common runtime actions.

## Latest Torfast Managed Runtime Helper

The next safe repeated-open cut is now in the managed runtime path itself.
`torfast/fast_runtime.py` now starts a small background helper after
successful managed `warm` / `open` / `start` runs and reuses that loaded
worker for later managed `open` / `start` commands under the same stable state
root. The helper only relays the same existing launcher logic; it does not
change Tor config, browser prefs, SOCKS isolation, or gate rules.

What changed:

- Added `torfast/runtime_helper.py`, a small Unix-socket worker that loads the
  existing launcher once and serves later managed runtime requests.
- `torfast/fast_runtime.py` now fingerprints the helper-relevant files, starts
  the helper in the background after successful managed warm/reuse commands,
  uses it for later managed opens when ready, and shuts it down on
  `torfast stop`.
- The helper socket now uses a short hashed temp-path instead of the long
  state-root path so it stays under macOS Unix-socket limits.
- `TORFAST_DISABLE_RUNTIME_HELPER=1` now gives an exact opt-out for A/B or
  fallback.
- `tests/test_torfast_main.py` now covers helper use, helper fallback, helper
  dispatch-error behavior, warm helper start, stop helper shutdown, and the
  short socket-path regression.

Validation passed:

- `python3 -m unittest tests.test_torfast_main tests.test_torfast_cli tests.test_launch_torfast_browser`
- `python3 -m py_compile torfast/__main__.py torfast/fast_runtime.py torfast/runtime_helper.py torfast/cli.py tests/test_torfast_main.py tests/test_torfast_cli.py tests/test_launch_torfast_browser.py`

Direct hot-path proof:

- Saved helper compare lives at
  `results/torfast-runtime-helper-reused-open-compare-20260625T060619/summary.json`.
- In both saved helper-on replicates, the helper was ready before the measured
  samples, all measured runs kept
  `tor_browser_launch_gate.seconds = 0.0` and `tor_boot.seconds = 0.0`, and
  `torfast stop` removed the helper cleanly afterward.
- Helper-on replicate `r1`: warm wall `0.202s`, repeated-open median wall
  `1.081s`, median browser elapsed `1.020s`, median non-browser overhead
  `0.062s`.
- Helper-on replicate `r2`: warm wall `0.146s`, repeated-open median wall
  `1.090s`, median browser elapsed `1.021s`, median non-browser overhead
  `0.068s`.
- Against the earlier stable repeated-open baseline in
  `results/torfast-fast-entry-reused-open-bench-20260625T052559/summary.json`,
  the combined helper-on 24-sample median moved from about `1.104s` to
  `1.085s` wall (`-20 ms`), browser elapsed moved from about `1.030s` to
  `1.021s` (`-9 ms`), and median non-browser overhead moved from about
  `0.075s` to `0.066s` (`-10 ms`).

Decision: keep the managed runtime helper. It is a small but real repeated-open
win on the exact managed workflow, and it keeps the same Tor-side proof while
still allowing an exact opt-out through `TORFAST_DISABLE_RUNTIME_HELPER=1`.

## Latest Browser Compare Winner

Fresh browser proof now has a short wrapper:
`python3 tools/run_browser_compare_current_winner.py`

The wrapper runs the current best exact-privacy browser recipe:

- interleaved 3-target compare on Tor check, Tor Project homepage, and the
  Tor Project download page
- same-isolation target `2`
- first-stream same-isolation prewarm
- health-aware selector
- prefer-cold same-isolation selector
- same-window guarded defer-post-boot comparison lane for A/B proof

Saved proof:
`results/browser-compare-20260626T064859/browser-compare.json`, with analyzer
output at `results/browser-compare-20260626T064859/analysis.md`, passed
quality.

- Plain Arti was the within-run winner with `3/3` success on all three
  targets.
- Plain Arti median load times were `1598.310ms` on Tor check,
  `5304.503ms` on the homepage, and `4316.420ms` on the download page.
- Plain Arti boot was `13.306s`, and boot plus median load total was about
  `24.525s`.
- In that same window, local C Tor landed at about `26.176s` boot plus median
  load, and the guarded defer-post-boot lane landed at about `28.855s`.
- The earlier same-window proof
  `results/browser-compare-20260626T063136/browser-compare.json`, with analyzer
  output at `results/browser-compare-20260626T063136/analysis.md`, failed
  quality on plain Arti download and had the guarded lane at
  `16006.601ms` median download load. In the fresh proof, that guarded lane
  dropped to `9270.298ms` and stayed `3/3`.
- `gpt-5.4-pro` second opinion via `cz` said the next smallest move should be
  prefer-cold same-isolation. The fresh proof matches that advice.

Saved selector metadata now also treats `health-aware` runs as effective
load-aware runs, so the saved browser-compare JSON matches the real selector
behavior used in the proof.

Decision: keep this lane as the current repeatable browser winner. It stays
lab-only for now, but it is the best current fast path that kept browser
quality clean in this repo. Keep that claim scoped to this 3-target browser
workload until it survives more reruns across time and network conditions.

Pending-wait follow-up on the exact same winner shape was rejected. The run
`results/browser-compare-20260626T071624/browser-compare.json`, with analyzer
output at `results/browser-compare-20260626T071624/analysis.md`, added only
`wait800ms` to
`arti_release_browser_healthaware_sameiso2_prewarmfirst_prefercold_wait800ms`.
Quality failed on `check.torproject.org` run `2` with `about:neterror`
`netTimeout`, and the failed run was missing screenshot, browser-pref, and
fingerprint proof. The lane also booted much slower at `20.266s` because boot
directory work hit timeout and partial-response rows.

Even though that lane got better medians on Tor check and the download page, it
was not a real winner. Boot plus median loads landed at about `30.936s`, versus
`21.088s` for the clean plain-Arti winner in the same window, and `27.993s`
for local C Tor. `gpt-5.4-pro` via `cz` agreed with the reject call: do not
promote the pending-wait variant, and do not keep pushing in the `wait800ms`
direction for this exact browser recipe.

Directory-rescue follow-up on the same winner shape also stays rejected for
now. The challenger `arti_release_browser_mdsrcspreadpendingearlyusable` had
mixed evidence across the next three same-window reruns:

- `results/browser-compare-20260626T073001/browser-compare.json`, with analyzer
  output at `results/browser-compare-20260626T073001/analysis.md`, was faster
  overall than plain Arti but failed quality on `check.torproject.org` run `3`
  with `about:neterror` `e=nssFailure2`, and it also had a successful download
  tail that reached `65239.940ms`.
- `results/browser-compare-20260626T073638/browser-compare.json`, with analyzer
  output at `results/browser-compare-20260626T073638/analysis.md`, passed
  quality and beat plain Arti in that window, so `gpt-5.4-pro` via `cz` said
  the right next step was one more clean rerun before any promotion.
- `results/browser-compare-20260626T075342/browser-compare.json`, with analyzer
  output at `results/browser-compare-20260626T075342/analysis.md`, passed
  quality but lost clearly. Plain Arti booted in `9.554s` and landed at
  `11376.140ms`, `14703.024ms`, and `15409.595ms` for boot plus median load
  across check, homepage, and download. The directory-rescue lane booted in
  `16.267s` and landed at `20138.321ms`, `24640.454ms`, and `24760.779ms`.

Decision: do not promote `mdsrcspreadpendingearlyusable` to the current winner
wrapper or docs claim. Keep the current plain-Arti sameiso2/prewarm/health-aware
prefer-cold recipe as the winner for this exact 3-target browser workload.

Full directory-combo follow-up on that same winner shape also stays rejected.
`tools/run_browser_compare.py` now carries the top-level same-isolation winner
fields into the directory-combo extra profiles, so this was the first fair
same-window test of the old full combo on top of the real current winner
shape. The run `results/browser-compare-20260626T081334/browser-compare.json`,
with analyzer output at `results/browser-compare-20260626T081334/analysis.md`,
passed quality.

Plain Arti booted in `14.318s` and landed at `15852.224ms`, `21949.178ms`,
and `20886.063ms` for boot plus median load across check, homepage, and
download. The challenger
`arti_release_browser_mdsrcspreadpendingearlyusable_loadaware_partialretrychunk`
booted in `16.252s` and landed at `17869.026ms`, `22088.186ms`, and
`22736.546ms`. The challenger did improve raw median load on the homepage
(`5836.186ms` versus `7631.178ms`) and slightly on download
(`6484.546ms` versus `6568.063ms`), but the extra boot cost erased that gain
and made end-to-end speed worse on all three pages.

In this same window, local C Tor also beat both Arti lanes by boot plus median
load, so this run does not widen the current-winner claim; it only says the
old full directory combo is still not promotable on top of the current winner
shape. `gpt-5.4-pro` via `cz` agreed with the strict call: keep the current
winner unchanged and reject promotion.

Default guarded HS-pool target with deferred post-boot backfill also stays
rejected. This was the narrowest boot-focused follow-up in the current-winner
family: keep the guarded hidden-service pool target at the default `2`, but
defer the second guarded stem until after bootstrap settles. The run
`results/browser-compare-20260626T082521/browser-compare.json`, with analyzer
output at `results/browser-compare-20260626T082521/analysis.md`, passed
quality.

It did improve raw median page loads on the two bigger pages. The challenger
`arti_release_browser_hspoolguarded2_deferpostboot` landed at `8073.130ms` on
the homepage and `5478.271ms` on download, versus plain Arti at
`11973.349ms` and `6513.524ms`. But the real user path got much worse because
boot exploded: plain Arti booted in `5.519s`, while the challenger took
`19.254s`. Boot plus median load therefore lost badly on all three pages:
plain Arti landed at `7645.600ms`, `17492.349ms`, and `12032.524ms`, while the
challenger landed at `21018.584ms`, `27327.130ms`, and `24732.271ms`.

The boot proof is also stricter rejection evidence, not just a speed loss. The
challenger had `3` directory failures, `3` directory timeouts, and `3` partial
responses, versus plain Arti with `2` directory failures, `0` timeouts, and
`2` partial responses in the same window. `gpt-5.4-pro` via `cz` agreed with
the reject call: keep the current winner unchanged and do not promote deferred
guarded target `2`.

Hidden-service rendezvous prebuild is now promoted into the current-winner
wrapper for this exact 3-target browser workload. The run
`results/browser-compare-20260626T083813/browser-compare.json`, with analyzer
output at `results/browser-compare-20260626T083813/analysis.md`, passed
quality and was strong enough to move from lab-only compare lane to the main
wrapper recipe.

Plain Arti booted in `23.614s` and landed at `26656.267ms`, `38061.145ms`,
and `42273.182ms` for boot plus median load across check, homepage, and
download. The challenger `arti_release_browser_hsrendpredesc` booted in
`21.997s` and landed at `23679.635ms`, `30845.777ms`, and `26026.556ms`. It
also beat plain Arti on raw median load on all three pages:
`1682.635ms` versus `3042.267ms`, `8848.777ms` versus `14447.145ms`, and
`4029.556ms` versus `18659.182ms`.

Against local C Tor, the promoted recipe is still not a full broad winner yet.
Raw median load is still slower on Tor check (`1682.635ms` versus
`1293.831ms`) and the homepage (`8848.777ms` versus `4992.565ms`), even
though boot plus median load now wins on all three pages:
`23679.635ms`, `30845.777ms`, and `26026.556ms` versus `27978.831ms`,
`31677.565ms`, and `31493.302ms`. The analyzer still flags
`slower than C Tor`, `resource queue`, `slow onion/data gap`, and
`slow hostname stream`.

`gpt-5.4-pro` via `cz` said `PROMOTE` for the current-winner wrapper, with the
same scope limit: this is a clean real-user-path win for the wrapper, not yet
a repo-wide release claim. The wrapper `python3 tools/run_browser_compare_current_winner.py`
now turns on `--arti-hs-rend-prebuild-before-desc` on the main Arti lane. Next
proof should be a larger interleaved rerun and should pull raw Tor check and
homepage closer to local C Tor before any wider claim.

That promotion did not hold up on a larger repeat. The five-run wrapper proof
`results/browser-compare-20260626T085718/browser-compare.json`, with analyzer
output at `results/browser-compare-20260626T085718/analysis.md`, did not give
a clean broader winner call. Quality failed because local C Tor timed out on
download run `5`, and the surviving median comparison still showed the
promoted lane slower than local C Tor on all three raw page-load medians:
`2693.526ms` versus `1537.730ms` on Tor check, `10779.833ms` versus
`5670.103ms` on the homepage, and `12977.041ms` versus `5058.365ms` on the
download page.

The decisive follow-up was a strict same-window A/B between plain current-family
Arti and the promoted hidden-service prebuild lane. The run
`results/browser-compare-20260626T090500/browser-compare.json`, with analyzer
output at `results/browser-compare-20260626T090500/analysis.md`, passed
quality and shows the promotion should be reverted.

Plain Arti booted slower (`13.724s` versus `10.769s`), but it was much better
on the real browse path for the two bigger pages. On the homepage, plain Arti
loaded at `4169.376ms` versus `8658.454ms`; paired median load delta was
`+3610.853ms` against the promoted lane, summary median load delta was
`+4489.078ms`, and boot plus median load was also worse for the promoted lane
at `19427.454ms` versus `17893.376ms`. On the download page, plain Arti loaded
at `4932.036ms` versus `5506.091ms`; paired median load delta was
`+1667.320ms` and summary median load delta was `+574.055ms`, even though the
faster boot let the promoted lane win boot plus median load there.

The risk tables are strong reject evidence, not a tie. The promoted lane had
worse max tails on all three pages, including `+27398.951ms` on Tor check,
`+12579.498ms` on the homepage, and `+6164.084ms` on the download page. The
homepage and download risk rows both say `paired median slower`, `summary
median slower`, `max tail worse`, and `low paired wins`. Queue evidence also
got worse on the bigger pages, with median max queue deltas of `+700.014ms`
on the homepage and `+1350.027ms` on the download page.

`gpt-5.4-pro` via `cz` agreed with the revert call: the hidden-service
prebuild lane is not promotable now because its wins are mostly startup-offset
while normal browse-path medians and tails get worse. The current-winner
wrapper `python3 tools/run_browser_compare_current_winner.py` is back to plain
Arti with same-isolation target `2`, prewarm-first-stream, health-aware
selection, and prefer-cold same-isolation. Keep
`hs_rend_prebuild_before_desc` as lab-only for now, and only revisit it with a
larger cold A/B plus a hidden-service-heavy workload where that knob should
actually matter.

That hidden-service-heavy follow-up is now on the board, and the call is
conditional rather than broad promotion. The run
`results/browser-compare-20260626T092411/browser-compare.json`, with analyzer
output at `results/browser-compare-20260626T092411/analysis.md`, passed
quality on `5` cold interleaved runs against `https://securedrop.org/`.

On raw hidden-service page load, `arti_release_browser_hsrendpredesc` clearly
beat plain current-family Arti: `4/5` paired load wins, paired median load
delta `-1962.848ms`, summary median load delta `-1782.857ms`, and a much
smaller max tail (`3736.002ms` versus `11298.039ms`). Queue shape also got
better on this page: `4/5` queue wins, median max queue delta `-2100.042ms`,
and the selector-risk row says `no selector move`.

But the exact cold user path is still worse, so this does not go back into the
default winner wrapper. Plain Arti booted in `11.043s` and landed at
`16407.729ms` for boot plus median load; `hsrendpredesc` booted in `18.488s`
and landed at `22069.872ms`. The candidate also still trailed local C Tor on
raw median load (`3581.872ms` versus `3183.012ms`), even though it beat local
C Tor on elapsed time after boot.

`gpt-5.4-pro` via `cz` said `CONDITIONAL`: no clear privacy/quality regression
signal, a real hidden-service page-load win after boot, but not broad
promotion because the cold path is slower overall and the proof is still narrow
(`1` onion target, cold-only, `5` runs). Keep
`hs_rend_prebuild_before_desc` out of the broad default path. Next proof should
be a larger hidden-service-only matrix with fresh-process cold and
reused-process warm cases across multiple onion sites to see whether the load
win survives once boot cost can amortize.

That broader hidden-service matrix is now in the repo, and it rejects the
single-target conditional read. There is a short wrapper for it:
`python3 tools/run_browser_compare_hidden_service.py`

The wrapper keeps the same current-family Arti baseline and compares it against
`hsrendpredesc` on two hidden-service-heavy targets:

- `https://securedrop.org/`
- `http://2gzyxa5ihm7nsggfxnu52rck2vv4rvmdlkiu3zzui5du4xyclen53wid.onion/download/index.html`

The direct onion target was first smoke-checked in
`results/browser-compare-20260626T093159/browser-compare.json`, which passed
quality and proved the harness can load that page through both plain Arti and
the `hsrendpredesc` lane. That one-run proof is target-validation only, not a
promotion call.

The first broader matrix
`results/browser-compare-20260626T093505/browser-compare.json`, with analyzer
output at `results/browser-compare-20260626T093505/analysis.md`, passed
quality on `3` cold interleaved runs across both targets and rejects
promotion.

The candidate did boot faster (`7.821s` versus plain Arti `14.038s`), but it
lost badly on page load everywhere that matters. On `securedrop`, plain Arti
loaded at `2701.538ms`, while `hsrendpredesc` loaded at `6187.906ms`; paired
median load delta was `+3682.323ms`, summary median load delta was
`+3486.368ms`, and max load got much worse (`14122.533ms` versus
`2859.194ms`). On the direct Tor onion download page, plain Arti loaded at
`9693.830ms`, while `hsrendpredesc` loaded at `16456.129ms`; paired median
load delta was `+5700.995ms`, summary median load delta was `+6762.299ms`, and
max load again got worse (`17741.679ms` versus `10755.134ms`).

This is also not just a cold-boot tradeoff. Later-run after-boot medians
stayed worse: `+2509.034ms` on `securedrop` and `+3345.626ms` on the direct
onion page. The analyzer risk rows for both targets say `paired median slower`,
`summary median slower`, `max tail worse`, and `low paired wins`. The selector
table says there was no selector gain; the slowdown came from more queue or
connect wait outside selector choice.

`gpt-5.4-pro` via `cz` said `LAB-ONLY`: the boot win does not convert into real
page-load wins, the candidate is slower on both hidden-service targets, later
runs are still worse, and the analyzer risk stays negative. Keep
`hs_rend_prebuild_before_desc` lab-only. The next useful proof is an
HS-focused A/B with per-phase connect and rendezvous instrumentation to explain
why this knob is increasing queue and connect time in the broader matrix.

That exact phase proof is now in the analyzer. `tools/analyze_browser_compare.py`
prints a new `Torfast HS Per-Run Phase A/B` section, and the refreshed
`results/browser-compare-20260626T093505/analysis.md` shows the per-run hidden-service
handoff instead of only profile-level medians.

The new rows say the same thing more precisely. `hsrendpredesc` can make
`rendezvous established` earlier, but that win often gets paid back later. On
the direct onion page, run `1` improved early rendezvous by `-1625ms` but made
`descriptor parsed` `+4174ms`, `intro ack` `+3297ms`, and
state/tunnel return `+2741ms` slower; run `2` again made early rendezvous
`-1485ms` faster but still lost `+8047.849ms` on page load. Only run `3` was a
clean win. On `securedrop`, all `3/3` runs were slower, with the worst rows
showing `descriptor parsed` `+7680ms`, `intro ack` `+3888ms`, and extra state
waits.

`gpt-5.4-pro` via `cz` matched that read and stayed at `LAB-ONLY`. In plain
words: prebuild sometimes starts rendezvous earlier, but mostly just pushes the
wait downstream into descriptor parse, intro ack, and tunnel/state handoff.
The first code area to inspect is
`upstream/arti/crates/tor-hsclient/src/connect.rs`, around the
`hs_rend_prebuild_before_desc` branch and its handoff into
`intro_rend_connect()` (`~642-694` and `~1112+`).

## Latest HS Descriptor-Share Recheck

The hidden-service follow-up now has two important code changes.

First, `upstream/arti/crates/tor-hsclient/src/connect.rs` no longer lets
`hs_rend_prebuild_before_desc` do work on a cold descriptor miss. The branch
now only runs when a timely hidden-service descriptor already exists in
per-service state or in the shared descriptor cache. On cold misses it skips
prebuild and stays on the normal descriptor-first path. That keeps the old
cold-path waste out of the default hidden-service flow. Focused validation
passed: `cargo fmt --all -- crates/tor-hsclient/src/connect.rs`,
`cargo test -p tor-hsclient hs_desc_is_timely_with_valid_descriptor --lib`,
`cargo test -p tor-hsclient hs_desc_is_timely_with_expired_descriptor --lib`,
`cargo test -p tor-hsclient test_connect --lib`, and
`cargo build -p arti --release`.

Second, `tools/run_boot_compare.py` now has
`--extra-arti-hs-desc-shared-cache`, so the repo can isolate bootstrap-only
behavior for the same baseline versus `hsdescshare` A/B without hiding it
inside a browser run. Validation passed:
`python3 -m py_compile tools/run_boot_compare.py`.

Single-target hidden-service recheck on `https://securedrop.org/`:

- `results/browser-compare-20260626T100520/browser-compare.json`, with
  analyzer output at `results/browser-compare-20260626T100520/analysis.md`,
  proved the gated `hs_rend_prebuild_before_desc` fix was really live. In the
  rebuilt run, `arti_release_browser_hsrendpredesc` logged only
  `rend prebuild before descriptor skipped cold descriptor`, never the old
  enabled path, so the cold hidden-service regression was removed.
- `results/browser-compare-20260626T100845/browser-compare.json`, with
  analyzer output at `results/browser-compare-20260626T100845/analysis.md`,
  then showed `arti_release_browser_hsdescshare` as the strongest next
  single-target lane. It beat baseline on both paired loads, improved boot plus
  median load, and showed real shared-cache use.
- The stronger follow-up
  `results/browser-compare-20260626T102427/browser-compare.json`, with
  analyzer output at `results/browser-compare-20260626T102427/analysis.md`,
  kept that read on the same target. On `securedrop`, baseline booted in
  `16.112s` and loaded at `8810.176ms`, while `hsdescshare` booted in
  `20.723s` and loaded at `2557.536ms`. In direct A/B, `hsdescshare` won
  `4/5` paired loads, paired median load delta was `-5203.951ms`, summary
  median load delta was `-6252.640ms`, summary boot plus load delta was
  `-1641.640ms`, and max load delta was `-12497.470ms`.

Bootstrap-only check cleared the earlier bootstrap blocker:

- `results/boot-compare-20260626T023058/boot-compare.json` compared exact
  baseline boot against exact `hsdescshare` boot with no page load.
- Baseline median boot was `10.209s`; `hsdescshare` median boot was `7.693s`.
- Baseline max boot was `33.609s`; `hsdescshare` max boot was `14.049s`.
- Baseline had `2` directory-signal runs with `3` directory failures,
  `2` directory timeouts, `6` `NOTDIRECTORY` rows, and `3` partial responses.
  `hsdescshare` had `0` directory-signal runs and `0` rows in all four of
  those fields.
- `gpt-5.4-pro` via `cz` agreed with the strict read: the old
  candidate-bootstrap worry is no longer the best explanation, and
  `hsdescshare` should move to the next validation gate rather than stay
  blocked on bootstrap fear.

Multi-target hidden-service signoff still failed, so this is not broad
promotion yet:

- `results/browser-compare-20260626T103438/browser-compare.json`, with
  analyzer output at `results/browser-compare-20260626T103438/analysis.md`,
  compared baseline versus `hsdescshare` across both `securedrop` and the
  direct onion download page
  `http://2gzyxa5ihm7nsggfxnu52rck2vv4rvmdlkiu3zzui5du4xyclen53wid.onion/download/index.html`.
- On the direct onion page, `hsdescshare` was a real win. Baseline median load
  was `9368.697ms`; `hsdescshare` was `5590.539ms`. Paired median load delta
  was `-858.287ms`, summary median load delta was `-3778.158ms`, and max load
  delta was `-9942.163ms`.
- But on `securedrop`, `hsdescshare` lost. Baseline median load was
  `5095.526ms`; `hsdescshare` was `6541.518ms`. Paired median load delta was
  `+352.963ms`, summary median load delta was `+1445.992ms`, and max tail was
  worse too (`7496.843ms` versus `7143.880ms`).
- The boot path also went bad again in that multi-target run. Baseline boot was
  `19.176s`; `hsdescshare` boot was `28.847s`. The candidate logged `8`
  directory failures, `8` directory timeouts, `8` partial responses, and a
  `boot directory` blocker row in the analyzer.

Decision now stays strict. `hsdescshare` is a real hidden-service speed lane,
and it is the strongest current lab follow-up after the cold-miss prebuild
fix, but it is not ready for broad promotion. `gpt-5.4-pro` via `cz` matched
the call: do not jump to the gated-prebuild plus `hsdescshare` combo yet.
First make `hsdescshare` survive more multi-target hidden-service reruns with
clean boot behavior and no target-specific regressions.
