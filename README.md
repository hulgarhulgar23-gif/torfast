# tor-fast lab

Goal: build a faster Tor-like client/browser without dropping Tor quality.

This repo starts from one rule: speed is only real if privacy, safety, and
compatibility stay the same.

## Current stance

We should not make a "fast Tor" by doing unsafe things:

- no 1-hop or 2-hop normal browsing circuits
- no weaker crypto
- no custom browser fingerprint
- no relay picking that always chooses the same fastest relays
- no DNS leaks
- no cache or prefetch behavior that makes users more unique

The better path is:

1. Measure current Tor and Tor Browser speed.
2. Keep Tor path and browser privacy rules as hard checks.
3. Improve safe parts first: startup, circuit warmup, congestion-aware circuit
   use, Conflux-style split traffic where supported, and browser overhead.
4. Prove every change with benchmarks and quality checks.

First quality-preserving speed finding (2026-06-15): C Tor's Conflux, as
shipped with `ConfluxEnabled auto`, gives `~2-3x` bulk-download throughput
versus disabling it, while keeping standard 3-hop circuits. It is neutral on
small pages. Forcing a `ConfluxClientUX` mode did not beat `auto`. See
`docs/latest-results.md` for the proofs and the circuit-quality certification.

Current Arti local lab patches:

- preemptive circuit recheck delay: `10s` to `1s`
- SOCKS CONNECT uses optimistic streams, matching C Tor optimistic-data behavior
- normal exit-stream selection keeps width `1` by default
- the exit-selection width has a bounded lab A/B override,
  `TORFAST_EXIT_SELECT_PARALLELISM`, for testing wider spread values without
  making them default
- non-onion SOCKS CONNECT has a default-off, bounded lab soft-timeout override,
  `TORFAST_SOCKS_CONNECT_SOFT_TIMEOUT_MS`, for testing one retry of slow
  successful CONNECT attempts without changing `.onion` behavior
- normal exit circuit selection has a default-off, bounded lab pending-circuit
  hedge, `TORFAST_EXIT_PENDING_HEDGE_MS`, for testing one extra exit circuit
  when a pending exit circuit is already old; pending and initial build wait
  paths arm timers so the first slow waiter can recheck after the threshold
- normal exit circuit selection also has a default-off load-aware lab mode,
  `TORFAST_EXIT_SELECT_LOAD_AWARE`, that chooses the least-assigned circuit
  among already eligible open circuits without changing path rules or building
  extra circuits

## What is here now

- `docs/quality-bar.md` - the rules we must not break.
- `docs/architecture.md` - the first design for a fast but Tor-compatible build.
- `docs/roadmap.md` - work order.
- `torfast/path_rules.py` - a small checker for 3-hop path safety rules.
- `tools/bench_http.py` - a no-dependency HTTP/HTTPS benchmark for direct or
  SOCKS proxy traffic.
- `scripts/fetch_upstreams.sh` - fetches shallow C Tor and Arti source trees.
- `scripts/build_c_tor.sh` - builds C Tor from the fetched source on this Mac.
- `scripts/build_arti_release.sh` - builds optimized Arti from the fetched source.
- `tools/run_tor_matrix.py` - runs C Tor benchmark profiles when `tor` exists.
- `tools/run_conflux_compare.py` - boots C Tor Conflux profiles
  (`stock`/`noconflux`/`latency`/`throughput`) at the same time and fetches
  round-robin so the same network window hits every profile. It records
  first-byte/total time and transfer-phase throughput, and has a `--bulk-bytes`
  option to add a fixed-size CDN object for measuring sustained transfer. It
  only changes `ConfluxEnabled`/`ConfluxClientUX`; path rules stay the same.
- `tools/run_arti_baseline.py` - starts the built Arti proxy, benchmarks it,
  and stops it.
- `tools/run_proxy_compare.py` - compares direct, stock C Tor, and release Arti
  in one run.
- `tools/run_browser_compare.py` - runs verified Tor Browser through local
  SOCKS proxies and saves page-load screenshots plus browser timing data. It
  uses `IsolateSOCKSAuth` for C Tor SOCKS ports and can compact bulky
  temporary browser/proxy state after saving JSON proof. It also has an
  interleaved schedule that rotates profile order in one measured proxy window,
  can test Arti SOCKS socket buffer sizes, can override Arti exit selection
  width, Arti preemptive exit circuit counts, Arti non-onion SOCKS CONNECT
  soft timeouts, Arti pending exit-circuit hedges, and Arti load-aware exit
  selection for lab A/B tests, can start extra same-window Arti profiles for
  exit-width, soft-timeout, pending-hedge, or load-aware A/B tests, can put a
  neutral byte-timing tap in front of every SOCKS proxy, records browser time
  origins for debug correlation, and retains key proxy signal lines separately
  from noisy log tails.
- `tools/analyze_browser_compare.py` - checks browser result quality evidence
  and prints timing, navigation phases, per-run phase rows, phase deltas versus
  local C Tor, slow resources, resource phase summaries, resource
  connection-shape summaries, resource type/top-resource deltas and load-tail
  resource deltas versus local C Tor for each Arti profile, direct baseline Arti
  versus extra Arti profile resource type/top-resource/load-tail/HTTP-phase and
  HTTP queue-shape A/B deltas, and direct top-resource relay-context A/B rows
  when join data is present, proxy log signals when present,
  Arti SOCKS/HsPool/HS/client timing rows,
  SOCKS first-byte timing by target kind, bounded SOCKS byte
  timelines, paired-run deltas versus local C Tor for each Arti profile, neutral
  byte-tap summaries and per-run tap spans, no-tap relay receive per-run spans,
  using high-resolution relay receive event timestamps when present, browser
  response vs SOCKS/byte-tap first-byte correlation when present, nearest
  browser resource-to-byte-tap connection joins and slow-resource tap connection
  group summaries plus tap-group relay context and SOCKS write lag when present,
  SOCKS-to-relay
  receive join rows, per-run summaries, nearest browser
  navigation/resource join rows and resource-to-relay summary rows when present,
  direct SOCKS connect retry rows, target-kind max CONNECT rows, SOCKS timeout retry timing rows,
  page-load tail rows, relay byte counts when present, relay receive
  queue timing rows, gap-edge detail rows, and circuit-level relay gap rows
  when present, SOCKS-to-relay
  joined stream gap rows when present, stream scheduler timing rows when
  present, stream receiver read/SENDME timing and gap-context rows when
  present, browser resource stream-gap and byte-context rows when present,
  circuit-selection rows when present, circuit assignment summaries, and direct
  baseline Arti versus extra Arti profile phase/load A/B deltas.
- `tools/run_torfast_browser_compare.py` - compares bundled Tor, local cold C
  Tor, and cache-seeded local C Tor first-use Tor Browser page loads, can add
  optional seeded control-port general-circuit-ready profiles, optional
  bundled-seeded minimum-general-circuit profiles, optional bundled-seeded
  official `ConfluxClientUX` lab profiles, or seeded fixed post-boot wait
  variants, supports named target packs, rotates profile order across cycles,
  and records Tor boot, browser load, launch+load, screenshots, proxy-pref
  proof, and the cache-only seed files copied into each measured seeded run.
- `tools/launch_torfast_browser.py` - launches the current best proven
  equal-quality fast path: official Tor Browser over bundled C Tor by default,
  with shared cache-only seed reuse and `ConfluxEnabled auto`.
- `tools/check_c_tor_circuits.py` - starts local C Tor with a control port and
  checks observable 3-hop circuit quality.
- `tools/check_arti_quality_config.py` - checks Arti source/config quality
  defaults and marks the result as static proof only.
- `tools/check_arti_rpc_path.py` - starts an RPC-enabled Arti build, checks
  live path shape through `arti:describe_path`, and uses C Tor directory data
  for sampled relay flags and family checks.
- `tools/run_cache_diagnostic.py` - compares cold and warm directory-cache
  behavior for C Tor and Arti.
- `tools/report_results.py` - summarizes saved benchmark JSON.
- `tools/analyze_torfast_browser_compare.py` - analyzes a saved
  `torfast-browser-compare.json`, printing navigation phase medians, resource
  tail summaries, top load-tail resources, per-resource `fetch->request`
  start/queue timing, same-origin HTTP/1.1 slot-pressure and blocker-chain
  summaries, page-resource browser-net-log cache signals when available,
  page resource-discovery summaries, family-level discovery/size and
  blocker-cascade summaries, loaded-versus-current variant swaps, and
  per-resource deltas between the current best bundled-seeded path and a
  bundled/local cold baseline.

## Quick checks

Run tests:

```sh
python3 -m unittest discover
```

Benchmark direct HTTPS:

```sh
python3 tools/bench_http.py --url https://check.torproject.org/ --runs 3 --json
```

Benchmark through a local Tor SOCKS proxy:

```sh
python3 tools/bench_http.py --url https://check.torproject.org/ --socks 127.0.0.1:9050 --runs 3 --json
```

Benchmark through the local Arti test port:

```sh
python3 tools/bench_http.py --url https://check.torproject.org/ --socks 127.0.0.1:19060 --runs 3 --json
```

Run the repeatable baseline and write JSON under `results/`:

```sh
python3 tools/run_baseline.py
```

Fetch upstream source:

```sh
sh scripts/fetch_upstreams.sh
```

Build C Tor:

```sh
sh scripts/build_c_tor.sh
```

Build release Arti:

```sh
sh scripts/build_arti_release.sh
```

Run C Tor profile tests:

```sh
python3 tools/run_tor_matrix.py
```

Compare C Tor Conflux profiles on a bulk download in one network window:

```sh
python3 tools/run_conflux_compare.py --only stock,noconflux,throughput --bulk-bytes 5000000 --runs 8 --warmup 3
```

Run the built Arti proxy benchmark:

```sh
python3 tools/run_arti_baseline.py
```

Compare direct, C Tor, and release Arti:

```sh
python3 tools/run_proxy_compare.py
```

Compare verified Tor Browser through bundled Tor, local C Tor, and release Arti:

```sh
python3 tools/run_browser_compare.py
```

Dry-run the current proven browser launcher:

```sh
python3 tools/launch_torfast_browser.py --dry-run
```

If your verified Tor Browser copy is not at the default lab path, add
`--browser-bin /path/to/Tor\ Browser.app/Contents/MacOS/firefox`.

Launch the browser and keep the managed Tor service warm for the next run:

```sh
python3 tools/launch_torfast_browser.py --leave-tor-running
```

Reopen the browser against that already-warmed managed Tor service:

```sh
python3 tools/launch_torfast_browser.py --reuse-tor-if-running
```

Stop the managed warm Tor service:

```sh
python3 tools/launch_torfast_browser.py --stop-managed-tor
```

Install a verified Tor Browser test copy into the default lab path:

```sh
python3 -m torfast install-browser
```

The current recommended first-run setup is now one command: reuse or install
Tor Browser, then refresh the shared cache-only Tor seed immediately:

```sh
python3 -m torfast install-browser
```

Prime Tor directory state once, then stop it, so later launches boot much
faster without keeping a background Tor process resident:

```sh
python3 -m torfast prime
```

After that, ordinary fresh `torfast launch` runs on new state roots
automatically reuse the shared cache-only directory seed unless you disable it
with `--no-dir-cache-seed`. By default, the local `about:tor` startup page now
starts as soon as the local SOCKS listener is ready, instead of waiting for
full `Bootstrapped 100%`, so one-shot launch overlaps browser startup with the
last part of Tor boot. Cold direct network URLs still default to the lighter
`Bootstrapped 95%` gate, and you can still override with
`--browser-launch-gate ...` for lab checks. When the managed Tor service is
already warm or being warmed for reuse, `auto` now uses the faster
`socks_ready` gate on that managed path instead. `torfast warm` now returns
once the managed service reaches its current ready gate, and a later
`torfast open` waits only for the target gate it still needs before browser
start.

By default, `torfast launch` and `torfast plan` now generate a fresh state root
under `tmp/torfast-launches/` so the proven cache-only Tor seed can apply again
on each one-shot launch. Pass `--state-root /path/to/root` if you intentionally
want to pin or reuse a specific launch root. `torfast warm`, `torfast open`,
`torfast status`, and `torfast stop` still use the stable managed-service
state root unless you override it.

The shared browser-startup seed is now default-off on normal runtime paths
because current product-path A/B does not show a durable speed win from it.
Opt in with `--browser-startup-seed` if you want to test it explicitly.

For a noninteractive runtime smoke, launch headless and stop it after a fixed
time:

```sh
python3 -m torfast launch --headless --browser-timeout 15
```

Compare real one-shot browser launch gates on network pages:

```sh
python3 tools/run_torfast_launch_gate_compare.py --cycles 3
```

Compare repeated `torfast warm` + `torfast open` launch gates on the managed
workflow:

```sh
python3 tools/run_torfast_warm_open_compare.py --profiles auto tor_boot_100 --cycles 3
```

Benchmark real page loads after `torfast warm` on the managed workflow:

```sh
python3 tools/run_torfast_warm_open_benchmark_compare.py --profiles auto tor_boot_95 --cycles 4
```

For fair warm-path wait A/B checks, add
`--profile-order randomized --random-seed 123`. The saved summary now also
includes the per-cycle profile order plus `p90`/`max` tail fields for browser
elapsed time, page load time, and combined wall time.

Use the packaged CLI for the current lightweight fast path:

```sh
python3 -m pip install -e .
torfast install-browser
torfast launch
```

Use the packaged CLI for the fastest repeated-open workflow:

```sh
torfast warm
torfast doctor
torfast open
torfast status
torfast stop
```

`torfast doctor` uses auto-discovery by default. It now prefers the bundled
Tor binary inside the discovered Tor Browser app before falling back to a local
build. If your Tor Browser binary is outside the default macOS paths, pass
`--browser-bin /path/to/Tor\ Browser.app/Contents/MacOS/firefox` or set
`TORFAST_BROWSER_BIN` before running it.

`torfast install-browser` now primes the shared cache-only Tor seed by default
after install or verified reuse. Pass `--no-prime-after-install` if you need to
skip that setup step.

If you want the first real launch to also start with a prebuilt shared
startup-only browser seed, add
`--prime-browser-startup-seed-after-install`. That runs one short headless
`about:tor` launch after install or reuse so later fresh profiles can reuse
the bundled extension startup artifacts immediately. Current product-path A/B
still shows only a tiny, noisy win here, so this remains opt-in rather than a
default setup step.

`torfast prime` bootstraps the auto-discovered C Tor once (bundled Tor by
default), stops it, and keeps the Tor data directory state in a shared
cache-only seed so later fresh launches can reuse public directory documents
without copying the Tor `state` file or keeping Tor resident in the background.

`torfast warm` starts or reuses the managed C Tor service without opening the
browser, and now returns once that managed service reaches its current ready
gate instead of always waiting for full boot. A later `torfast open` on that
same service waits only for the remaining target gate it still needs, while
still clearing the old browser home/profile directories before each open.

When enabled with `--browser-startup-seed`, `torfast` updates a separate shared
startup-only browser seed from safe bundled-extension artifacts
(`extensions/*.xpi` plus extension startup cache) and reuses it on later fresh
browser profiles. It intentionally does not copy browsing history, cookies,
HTTP cache, or profile metadata files with per-profile paths or timestamps.

You can also run the package without installing the console script:

```sh
python3 -m torfast install-browser
python3 -m torfast prime
python3 -m torfast launch
```

Or keep Tor warm between browser opens:

```sh
python3 -m torfast warm
python3 -m torfast open
python3 -m torfast status
python3 -m torfast stop
```

That warm/open path now keeps the Tor process warm but resets browser state on
each open, so it does not keep old browser profile/runtime state, including
extension storage identities, between browser runs. If there is no warm managed
service yet, `torfast open` now uses the same early browser-start gate as
`torfast launch` and still leaves the managed Tor process warm after full boot.
If `torfast warm` was started just before that, the later `open` will pick up
the same still-booting managed service and only wait for the remaining gate it
needs. On the repeated reused `about:tor` path, the hot launcher now also keeps
heavy benchmark-only helper imports off the normal runtime path; current local
proof has that repeated open shape down to about `1.081s` to `1.090s` median
wall with about `0.062s` to `0.068s` median non-browser overhead after one
uncounted priming open. That path now also starts a small managed runtime
helper after successful warm/reused runs so later `open` commands can reuse a
loaded launcher worker under the same state root. Set
`TORFAST_DISABLE_RUNTIME_HELPER=1` if you need to A/B or bypass that helper.

Run the same browser compare after warming each proxy directory cache:

```sh
python3 tools/run_browser_compare.py --warm-cache --compact-output --runs 2 --targets https://www.torproject.org/
```

Run a fairer interleaved browser compare in one proxy window:

```sh
python3 tools/run_browser_compare.py --warm-cache --compact-output --schedule interleaved --runs 2 --targets https://check.torproject.org/ https://www.torproject.org/
```

Run a diagnostic wait after proxy boot to test preemptive-circuit readiness:

```sh
python3 tools/run_browser_compare.py --warm-cache --compact-output --post-boot-wait 12 --runs 2 --targets https://www.torproject.org/
```

Measure the current product runtime path directly:

```sh
python3 tools/run_torfast_runtime_compare.py --runs 2 --browser-timeout 6
```

Measure real first-use browser loads for bundled Tor, local cold, and
cache-seeded launch:

```sh
python3 tools/run_torfast_browser_compare.py --runs 2 --compact-output
```

Run the broader bundled-seeded proof pack with check, homepage, and download:

```sh
python3 tools/run_torfast_browser_compare.py --runs 2 --compact-output --extra-bundled-seeded --target-pack broader
```

Probe bundled-seeded official `ConfluxClientUX` modes in one broader window:

```sh
python3 tools/run_torfast_browser_compare.py --runs 2 --compact-output --extra-bundled-seeded --extra-bundled-seeded-conflux-ux latency --extra-bundled-seeded-conflux-ux throughput --extra-bundled-seeded-conflux-ux throughput_lowmem --target-pack broader
```

Probe a bundled-seeded `2`-general-circuit gate on the download page:

```sh
python3 tools/run_torfast_browser_compare.py --runs 2 --compact-output --extra-bundled-seeded --extra-bundled-seeded-min-general-circuits 2 --targets https://www.torproject.org/download/
```

Capture download-page browser net logs with serialized HTTP for lab diagnosis:

```sh
python3 tools/run_torfast_browser_compare.py --runs 2 --compact-output --extra-bundled-seeded --targets https://www.torproject.org/download/ --browser-net-log --browser-serial-http-connections
```

Analyze the latest torfast browser compare for download-page phase and resource bottlenecks:

```sh
python3 tools/analyze_torfast_browser_compare.py --target https://www.torproject.org/download/ --top 8
```

Probe whether the `download/` bottleneck is mainly browser per-host slot pressure:

```sh
python3 tools/run_torfast_browser_compare.py --runs 2 --compact-output --extra-bundled-seeded --targets https://www.torproject.org/download/ --browser-max-persistent-connections-per-server 10
```

Sweep small seeded post-boot waits in one rotated window:

```sh
python3 tools/run_torfast_browser_compare.py --runs 2 --compact-output --skip-bundled-tor --extra-seeded-post-boot-wait-seconds 0.25 --extra-seeded-post-boot-wait-seconds 0.5 --extra-seeded-post-boot-wait-seconds 1.0
```

Run an Arti local SOCKS socket buffer experiment:

```sh
python3 tools/run_browser_compare.py --warm-cache --compact-output --schedule interleaved --targets https://www.torproject.org/ --arti-proxy-buffer-size "1 MB"
```

Run a same-window Arti exit-spread A/B:

```sh
python3 tools/run_browser_compare.py --warm-cache --compact-output --schedule interleaved --runs 3 --targets https://www.torproject.org/download/ --arti-exit-select-parallelism 3 --extra-arti-exit-select-parallelism 1
```

Run an Arti preemptive exit-circuit-count lab test:

```sh
python3 tools/run_browser_compare.py --warm-cache --compact-output --schedule interleaved --skip-bundled-tor --runs 2 --targets https://www.torproject.org/ --arti-min-exit-circs-for-port 3
```

Run an Arti non-onion SOCKS CONNECT soft-timeout lab test:

```sh
python3 tools/run_browser_compare.py --warm-cache --compact-output --schedule interleaved --skip-bundled-tor --runs 5 --targets https://www.torproject.org/ --arti-socks-connect-soft-timeout-ms 5000
```

Run a same-window baseline Arti vs soft-timeout Arti A/B:

```sh
python3 tools/run_browser_compare.py --warm-cache --compact-output --schedule interleaved --skip-bundled-tor --runs 5 --targets https://www.torproject.org/ --extra-arti-socks-connect-soft-timeout-ms 1500
```

Run a same-window baseline Arti vs pending-exit-circuit hedge A/B:

```sh
python3 tools/run_browser_compare.py --warm-cache --compact-output --schedule interleaved --skip-bundled-tor --runs 5 --targets https://www.torproject.org/ --extra-arti-exit-pending-hedge-ms 1500
```

Run a same-window baseline Arti vs same-isolation other-isolation-pressure plus assigned-cap A/B:

```sh
python3 tools/run_browser_compare.py --warm-cache --compact-output --schedule interleaved --skip-bundled-tor --runs 2 --targets https://www.torproject.org/ https://www.torproject.org/download/ --extra-arti-exit-same-isolation-other-isolation-pressure-assigned-cap 2:3:4
```

Run the same shape with first-stream prewarm enabled on the extra same-isolation profile:

```sh
python3 tools/run_browser_compare.py --warm-cache --compact-output --schedule interleaved --skip-bundled-tor --runs 2 --targets https://www.torproject.org/download/ --extra-arti-exit-same-isolation-other-isolation-pressure-assigned-cap-prewarm 2:3:4
```

Run a same-window baseline Arti vs load-aware open-circuit selection A/B:

```sh
python3 tools/run_browser_compare.py --warm-cache --compact-output --schedule interleaved --skip-bundled-tor --runs 3 --targets https://www.torproject.org/ --arti-log-level debug --proxy-log-tail-lines 100000 --extra-arti-exit-select-load-aware
```

Run a focused load-aware plus SOCKS CONNECT soft-timeout download-page A/B:

```sh
python3 tools/run_browser_compare.py --warm-cache --compact-output --schedule interleaved --skip-bundled-tor --runs 5 --targets https://www.torproject.org/download/ --arti-log-level debug --proxy-log-tail-lines 100000 --arti-exit-select-load-aware --extra-arti-socks-connect-soft-timeout-ms 5000
```

Run plain Arti vs the current broad directory combo vs the same combo plus a
`500ms` SOCKS CONNECT hedge on the download page:

```sh
python3 tools/run_browser_compare.py --compact-output --schedule interleaved --skip-bundled-tor --runs 2 --targets https://www.torproject.org/download/ --browser-net-log --proxy-log-tail-lines 100000 --extra-arti-dir-microdesc-source-spread-pending-spread-early-usable-load-aware-partial-retry-chunking --extra-arti-dir-microdesc-source-spread-pending-spread-early-usable-load-aware-partial-retry-chunking-socks-connect-hedge-ms 500
```

Run plain Arti vs the current broad directory combo vs the same combo plus a
`5000ms + 3 attempts` SOCKS CONNECT soft-timeout profile on the download page:

```sh
python3 tools/run_browser_compare.py --compact-output --schedule interleaved --skip-bundled-tor --runs 2 --targets https://www.torproject.org/download/ --browser-net-log --proxy-log-tail-lines 100000 --extra-arti-dir-microdesc-source-spread-pending-spread-early-usable-load-aware-partial-retry-chunking --extra-arti-dir-microdesc-source-spread-pending-spread-early-usable-load-aware-partial-retry-chunking-socks-connect-soft-timeout-combo 5000:3
```

Run the broader 3-target repeat for plain Arti vs the current broad directory
combo vs the same combo plus `5000ms + 3 attempts`:

```sh
python3 tools/run_browser_compare.py --compact-output --schedule interleaved --skip-bundled-tor --runs 3 --targets https://check.torproject.org/ https://www.torproject.org/ https://www.torproject.org/download/ --proxy-log-tail-lines 100000 --extra-arti-dir-microdesc-source-spread-pending-spread-early-usable-load-aware-partial-retry-chunking --extra-arti-dir-microdesc-source-spread-pending-spread-early-usable-load-aware-partial-retry-chunking-socks-connect-soft-timeout-combo 5000:3
```

Run a clean broad simplification gate for plain Arti vs load-aware-only vs
chunking-without-load-aware vs the old full combo:

```sh
python3 tools/run_browser_compare.py --compact-output --schedule interleaved --skip-bundled-tor --runs 3 --targets https://check.torproject.org/ https://www.torproject.org/ https://www.torproject.org/download/ --proxy-log-tail-lines 100000 --extra-arti-dir-microdesc-source-spread-pending-spread-early-usable-load-aware --extra-arti-dir-microdesc-source-spread-pending-spread-early-usable-partial-retry-chunking --extra-arti-dir-microdesc-source-spread-pending-spread-early-usable-load-aware-partial-retry-chunking
```

Run a clean broad A/B for the load-aware directory combo vs the same combo with
dir-microdesc bad-health replacement disabled:

```sh
python3 tools/run_browser_compare.py --compact-output --schedule interleaved --skip-bundled-tor --runs 3 --targets https://check.torproject.org/ https://www.torproject.org/ https://www.torproject.org/download/ --proxy-log-tail-lines 100000 --extra-arti-dir-microdesc-source-spread-pending-spread-early-usable-load-aware --extra-arti-dir-microdesc-source-spread-pending-spread-early-usable-load-aware-no-dir-bad-health-replacement
```

Run a cheap one-target follow-up when you want another boot sample for that same
bad-health-replacement A/B:

```sh
python3 tools/run_browser_compare.py --compact-output --schedule interleaved --skip-bundled-tor --runs 1 --targets https://check.torproject.org/ --proxy-log-tail-lines 100000 --extra-arti-dir-microdesc-source-spread-pending-spread-early-usable-load-aware --extra-arti-dir-microdesc-source-spread-pending-spread-early-usable-load-aware-no-dir-bad-health-replacement
```

Run a focused homepage proof with stream-reactor congestion logs:

```sh
python3 tools/run_browser_compare.py --warm-cache --compact-output --schedule interleaved --skip-bundled-tor --runs 3 --targets https://www.torproject.org/ --arti-log-level debug --proxy-log-tail-lines 100000
```

Run a neutral byte-tap browser compare:

```sh
python3 tools/run_browser_compare.py --warm-cache --compact-output --schedule interleaved --runs 3 --targets https://check.torproject.org/ https://www.torproject.org/ --byte-tap
```

Analyze the latest browser compare:

```sh
python3 tools/analyze_browser_compare.py
```

Check observable C Tor circuit quality:

```sh
python3 tools/check_c_tor_circuits.py
```

Check Arti source/config quality defaults:

```sh
python3 tools/check_arti_quality_config.py
```

Check Arti live RPC paths after building and copying an RPC-enabled binary:

```sh
cd upstream/arti
cargo build -p arti --release --features rpc,experimental-api --locked
cd ../..
mkdir -p tmp/arti-rpc
cp upstream/arti/target/release/arti tmp/arti-rpc/arti
python3 tools/check_arti_rpc_path.py --samples 3
```

Check cold and warm directory-cache behavior:

```sh
python3 tools/run_cache_diagnostic.py
```

Run a cold-boot partial-retry chunking A/B on the best current directory combo:

```sh
python3 tools/run_boot_compare.py --runs 5 --compact-output --arti-dirclient-timing-log --extra-arti-dir-microdesc-source-spread-pending-spread-early-usable-partial-retry-chunking
```

Print the latest saved benchmark table:

```sh
python3 tools/report_results.py
```

This machine does not currently have `tor` or `arti` in `PATH`, so the SOCKS
benchmark needs a Tor client installed or launched first.
