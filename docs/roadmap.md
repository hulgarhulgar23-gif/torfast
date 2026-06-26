# Roadmap

## Phase 0: base lab

- Create quality bar.
- Add path-rule checker.
- Add SOCKS benchmark tool.
- Record local tool state.

Done now:

- `tor` is not in `PATH`.
- `arti` is not in `PATH`.
- Arti source is fetched under `upstream/arti`.
- C Tor source is fetched under `upstream/tor`.
- Arti debug binary builds locally.
- Arti release binary builds locally.
- C Tor builds locally.
- Arti SOCKS baseline is saved under `results/`.
- C Tor profile matrix is saved under `results/`.
- Direct, C Tor, and release Arti compare run is saved under `results/`.
- Verified Tor Browser test copy is saved under `tmp/browser/`.
- Tor Browser browser-compare runs are saved under `results/`.
- C Tor control-port circuit checks are saved under `results/`.
- Arti source/config quality checks are saved under `results/`.
- Arti RPC runtime path checks are saved under `results/`.
- Cold/warm cache diagnostics are saved under `results/`.
- Python is available.
- Rust and Cargo are available.

## Phase 1: real baseline

- Install or build C Tor.
- Build Arti.
- Run the same benchmark through each SOCKS proxy.
- Save JSON result files under `results/`.
- Add a simple report script.

Done now:

- Arti debug build passed with `cargo build -p arti --locked`.
- `tools/run_arti_baseline.py` starts Arti, waits for bootstrap, benchmarks, and
  stops it.
- C Tor build passed with `scripts/build_c_tor.sh` equivalent commands.
- `tools/run_tor_matrix.py` benchmarks stock, latency, throughput, and
  throughput-low-memory Conflux UX settings.
- Arti release build passed with `scripts/build_arti_release.sh`.
- `tools/run_proxy_compare.py` benchmarks direct, stock C Tor, and release Arti
  in one time window.

## Phase 1.5: browser baseline

- Check for Tor Browser install.
- If missing, download or install a test copy.
- Run Tor Browser page-load timing through stock C Tor.
- Run Tor Browser page-load timing through Arti only if it can preserve Tor
  Browser settings and isolation behavior.
- Add fingerprint checks before calling any browser result "same quality".

Current state:

- Tor Browser was not found under `/Applications` on 2026-06-07 local time.
- Tor Browser `15.0.15` was downloaded from the Tor Project distribution
  directory, signature-checked, checksum-checked, codesign-checked, and
  notarization-checked.
- `tools/run_browser_compare.py` runs the verified app through bundled Tor,
  local C Tor, and release Arti external SOCKS proxies. It can also use
  `--warm-cache` to bootstrap each proxy once before the measured browser run,
  `--compact-output` to keep result folders small, and `--post-boot-wait` for
  circuit-readiness diagnostics.
- The C Tor browser harness now uses `SocksPort ... IsolateSOCKSAuth`, and the
  analyzer rejects C Tor browser results that lack this flag.
- `tools/analyze_browser_compare.py` checks screenshots, proxy prefs, and core
  Tor Browser privacy prefs before accepting browser timing evidence.
- Latest two-run browser sample passed quality, but Arti was slower than both C
  Tor options on page load. Do not call Arti faster for browser use yet.
- Latest focused one-run browser sample also records Navigation Timing and
  resource timing. In that narrow run, Arti beat bundled Tor but still lost to
  local C Tor on page-load time.
- Latest two-run warm-cache browser sample passed quality. Arti boot dropped to
  `0.350s`, but Arti still lost on page-load time: `8607.444ms` load for Arti,
  `6064.782ms` for bundled Tor, and `5379.617ms` for local C Tor.
- A 12 second post-boot wait improved Arti load to `6766.720ms`, but it still
  lost to bundled Tor at `5004.020ms` and local C Tor at `4695.390ms`. This
  points toward circuit readiness helping, but not enough.
- A local Arti patch changed the preemptive circuit recheck delay from `10s`
  to `1s`. In the next no-wait two-run browser sample, Arti load improved to
  `6184.888ms`, close to bundled Tor at `5976.150ms`, but still slower than
  local C Tor at `4147.518ms`.
- The latest trusted patched warm-cache browser sample
  `results/browser-compare-20260607T055802/browser-compare.json` used 5 runs,
  two targets, and `IsolateSOCKSAuth` on the C Tor SOCKS ports. With the
  optimistic SOCKS CONNECT patch, Arti still lost to C Tor on page-only load,
  but won launch-to-load:
  `6828.450ms` Arti launch-to-load versus bundled Tor `7061.549ms` and local C
  Tor `7151.303ms` on `www.torproject.org`.
- `tools/run_browser_compare.py --schedule interleaved` now keeps measured
  proxies running in one window and rotates browser loads by run, target, and
  profile.
- The rotating interleaved 5-run browser sample
  `results/browser-compare-20260607T062155/browser-compare.json` passed quality.
  Arti won page-only load on `check.torproject.org`, lost page-only load on
  `www.torproject.org`, and beat both C Tor profiles on launch-to-load.
- The analyzer now prints navigation phases. On the Tor homepage, Arti's
  remaining page-only loss starts at first response and continues through DOM
  and resource load, not proxy boot.
- `results/browser-compare-20260607T063128/browser-compare.json` proved the
  harness can capture Arti debug proxy tails and summarize SOCKS connects,
  circuit assignments, ready streams, preemptive circuits, reactor spawns, and
  onion-service connect log lines.
- `results/browser-compare-20260607T063922/browser-compare.json` used the
  rebuilt release Arti binary with debug-only SOCKS timing logs. The analyzer
  now shows notable `timing_id` rows and nearby context. In that one-run
  diagnostic, Arti had one `5000ms` connect outlier. That row also had
  onion-service and hspool log lines between request and stream-ready.
- Local Arti source now also has debug-only `torfast hspool` timing logs for
  onion-service pool reuse, on-demand launches, and background launches. These
  were added after `063922`.
- `results/browser-compare-20260607T065452/browser-compare.json` used those
  HsPool logs. In that one-run diagnostic, Arti had one unfinished SOCKS
  request, no SOCKS connect delay among ready streams, one on-demand GUARDED
  HsPool launch ready in `783ms`, and three background NAIVE launches with
  median `725ms`.
- `results/browser-compare-20260607T065905/browser-compare.json` ran a 3-run
  debug homepage sample. It found three SOCKS connect delays above `1s`
  (`3396ms`, `2812ms`, and `2213ms`). All three had onion-service context, but
  HsPool reused guarded stems and did not need on-demand launches.
- Local Arti source now also has debug-only `torfast hs timing` logs for
  rendezvous and introduction protocol phases.
- `results/browser-compare-20260607T071052/browser-compare.json` ran a 2-run
  HS timing debug sample. It found two SOCKS connect delays above `1s`
  (`43499ms` and `2260ms`). But the visible HS protocol phases were quick:
  rendezvous established median `246.5ms`, introduce ack median `410ms`, and
  RENDEZVOUS2 median `515ms`. The biggest wait happened before the visible HS
  sequence, so the next diagnostic needs better correlation between SOCKS timing
  ids and HS connect sequence start.
- Local Arti source now has debug-only HS client phase logs around hidden
  service bootstrap readiness, netdir lookup, key lookup, tunnel creation, and
  begin-stream completion.
- `results/browser-compare-20260607T072725/browser-compare.json` ran a 1-run
  HS client phase diagnostic. Arti timed out, so this is not speed proof. But
  it showed the onion SOCKS request started HS client work immediately, tunnel
  ready was `2975ms`, begin stream finished at `3328ms` with `ok=true`, and the
  later relay phase stalled for `56251ms`.
- Local Arti source now has debug-only relay byte counting for SOCKS relay
  traffic. It is enabled only when debug logging is enabled.
- `results/browser-compare-20260607T074146/browser-compare.json` ran a 1-run
  relay byte diagnostic on `check.torproject.org`. It passed quality. The two
  finished hostname streams had median relay time `1514.500ms`, median
  client-to-Tor bytes `2727`, and median Tor-to-client bytes `12139`; the onion
  request was unfinished in the captured tail.
- `results/browser-compare-20260607T074551/browser-compare.json` ran a 1-run
  homepage relay byte diagnostic. It passed quality. Arti beat both C Tor
  profiles in this one debug run, but this is not the main speed proof. The
  useful bottleneck fact is that the finished page streams were normal
  `hostname` streams carrying data, median relay time was `3188ms`, median
  client-to-Tor bytes were `4284`, median Tor-to-client bytes were `226595`,
  the `8` finished streams used `3` unique circuits with `6` streams on
  `Circ 0.1`, and the only unfinished stream was an `onion` side request that
  did not block page quality.
- `results/browser-compare-20260607T075831/browser-compare.json` tested Arti
  with `1 MB` local SOCKS socket send/receive buffers. It passed quality, but it
  was not a clear page-load win: Arti load was `4236.840ms`, close to the
  prior default-buffer diagnostic `4252.457ms`, and slower than bundled Tor's
  page-only `3877.678ms` in that run. Keep the runner option for future A/B
  checks, but do not make it a default from this evidence.
- `results/browser-compare-20260607T080620/browser-compare.json` tested a
  temporary Arti circuit-reactor patch that batched up to 4 already-ready
  outbound stream cells per turn. It passed quality but was slower: Arti load
  was `6020.619ms`, versus bundled Tor `4166.283ms` and local C Tor
  `4890.584ms`. The patch was removed. Do not retry that exact batching shape
  without a better scheduler model and traffic-shape review.
- Local Arti source now has debug-only stream scheduler logs for picked DATA
  cells, closed streams, and hop-level send-capacity blocks.
- `results/browser-compare-20260607T081637/browser-compare.json` ran a 1-run
  stream scheduler diagnostic. It passed quality. Arti load was `5479.681ms`,
  bundled Tor load was `4284.098ms`, and local C Tor load was `4568.295ms`.
  The Arti proxy tail showed `164` outbound DATA picks, `14` closed streams,
  `16` unique stream ids, and `0` hop-level scheduler blocks. This points away
  from a simple ready-stream send-capacity block.
- Local Arti source now has debug-only relay receive logs for delivered cells,
  queue-full events, stream-gone receive events, and per-stream queued bytes.
- `results/browser-compare-20260607T082829/browser-compare.json` ran a 1-run
  relay receive diagnostic. It passed quality. Arti load was `5217.089ms`,
  bundled Tor load was `4274.955ms`, and local C Tor load was `4792.050ms`.
  The Arti proxy tail showed `2825` delivered relay messages, `2813` DATA
  messages, `0` queue-full events, `0` stream-gone receive events, `11` stream
  ids, median queued-after bytes `1992`, and max queued-after bytes `20754`.
  This points away from local stream receive queue pressure.
- Local Arti source now has debug-only circuit-selection logs for open,
  pending, and build choices.
- `results/browser-compare-20260607T084058/browser-compare.json` ran a 1-run
  circuit-selection diagnostic. It passed quality. Arti load was `4281.488ms`,
  bundled Tor load was `4437.963ms`, and local C Tor load was `4965.919ms`.
  Arti often had `2` to `3` matching open circuits, but median select
  parallelism was `1`, and `11` of `13` circuit assignments used the same
  circuit. This made exit-circuit spreading worth a controlled A/B test.
- Local Arti source now has a lab patch where normal exit streams choose among
  up to `3` matching open exit circuits. It keeps the same eligibility and
  isolation checks and does not launch extra circuits.
- `results/browser-compare-20260607T084444/browser-compare.json` ran a 1-run
  A/B diagnostic for that exit-spread patch. It passed quality. Arti load was
  `3892.070ms`, bundled Tor load was `3109.866ms`, and local C Tor load was
  `2914.536ms`. The Arti proxy tail showed `7` spread open picks selecting
  `3` circuits, and top circuit assignments dropped from `11/13` in the prior
  diagnostic to `3/7`. This proves the patch changes stream distribution, but
  not yet that it is a speed win.
- `results/browser-compare-20260607T085332/browser-compare.json` ran a 5-run
  rotating interleaved browser proof for the exit-spread patch with
  `--arti-log-level info`. It passed quality. Arti beat bundled C Tor page-only
  load on both targets (`1662.317ms` vs `2066.908ms` on check, `5530.292ms` vs
  `5950.900ms` on homepage) and won boot+load on both targets. Arti still lost
  to local C Tor page-only load on both targets (`1309.308ms` check,
  `5192.698ms` homepage), so this is progress but not the final goal. The
  phase-delta table points mostly to first response: Arti is `+483.343ms` on
  check and `+466.676ms` on the homepage versus local C Tor before first
  browser response, while later browser phases are close.
- `results/browser-compare-20260607T090853/browser-compare.json` tested raising
  Arti `min_exit_circs_for_port` from `2` to `3`. It was rejected because Arti
  failed quality: one `check.torproject.org` run hit a neterror connection
  failure, and one homepage run hit a `120000ms` navigation timeout. The patch
  was reverted.
- `results/browser-compare-20260607T093521/browser-compare.json` added
  debug-only SOCKS first-byte timing. It passed quality. Hostname streams had
  median connect `0.000ms`, median SOCKS reply `0.000ms`, and median first Tor
  byte `423.000ms`.
- `results/browser-compare-20260607T094307/browser-compare.json` added epoch
  correlation between browser `responseStart` and SOCKS first Tor bytes. It
  passed quality. On `check.torproject.org`, the nearest hostname SOCKS first
  Tor byte arrived `747.545ms` before browser `responseStart`.
- `results/browser-compare-20260607T095237/browser-compare.json` added a
  bounded SOCKS byte timeline. It passed quality. On two normal hostname
  streams, client-to-Tor bytes started at `0ms`, first Tor-to-client bytes
  arrived at `314ms` and `326ms`, and shown encrypted byte events continued up
  to about `950ms` with max shown gaps of `202-490ms`. The nearest first Tor
  byte arrived `424.128ms` before browser `responseStart`.
- `tools/run_browser_compare.py --byte-tap` now puts the same neutral local
  byte-timing tap in front of bundled C Tor, local C Tor, and Arti. It logs
  byte counts, SOCKS reply timing, and first real stream-data timing without
  storing payload bytes.
- `results/browser-compare-20260607T100351/browser-compare.json` ran a 3-run
  rotating interleaved byte-tap proof. It passed quality. Arti's median first
  stream-data-to-browser time was `401.870ms`, versus bundled C Tor
  `604.255ms` and local C Tor `644.909ms`.
- `results/browser-compare-20260607T100731/browser-compare.json` repeated the
  same 3-run rotating interleaved proof without the byte tap. It passed
  quality. Arti beat both C Tor profiles on page-only load for both targets:
  `1033.798ms` vs bundled `1723.884ms` and local `1902.607ms` on
  `check.torproject.org`; `3591.679ms` vs bundled `5404.347ms` and local
  `5193.565ms` on `www.torproject.org`.
- `tools/analyze_browser_compare.py` now prints paired-run deltas against
  local C Tor, so run-by-run wins can be checked instead of trusting only
  separate medians.
- `tools/analyze_browser_compare.py` now also prints resource type deltas and
  top slower resources versus local C Tor. On the latest accepted normal proof,
  the download page shows Arti behind local C Tor on CSS by `+500.010ms`, images
  by `+566.678ms`, and font/other resources by `+316.673ms`.
- `results/browser-compare-20260607T101326/browser-compare.json` ran a stronger
  5-run, three-target normal proof. It passed quality. Arti beat bundled C Tor
  on page-only load and boot+load for all three targets, but did not beat local
  C Tor on the two larger pages. Paired load wins versus local C Tor were `2/5`
  on `check.torproject.org`, `1/5` on `www.torproject.org`, and `1/5` on
  `www.torproject.org/download/`.
- `results/browser-compare-20260607T102046/browser-compare.json` repeated the
  5-run three-target proof with `--byte-tap`, but failed quality. Arti had one
  `check.torproject.org` neterror `connectionFailure` and one homepage
  `netTimeout`, with missing screenshots. Treat it as rejected diagnostic data,
  not proof.
- `results/browser-compare-20260607T103305/browser-compare.json` ran one focused
  download-page debug diagnostic. It passed quality, but debug logging made Arti
  much slower, so it is not speed proof. It showed Arti reached first response
  earlier than local C Tor, then lost heavily from response-to-DOM and DOM-to-load.
  Relay receive logs showed `0` queue-full events, and stream scheduler logs
  showed `0` hop-level blocks.
- `tools/run_browser_compare.py` now saves `proxy_signal_lines` separately from
  the noisy proxy tail, and the analyzer reads both without double-counting.
- `results/browser-compare-20260607T104652/browser-compare.json` ran one focused
  retained-signal diagnostic. It passed quality, but remains debug evidence
  only. It proved the exit-spread patch was active in a real browser page load:
  `6` normal exit open picks used `select_parallelism=3`, and `6` circuit
  assignments used `4` unique circuits.
- The runner now has `--arti-exit-select-parallelism` for bounded normal
  no-debug A/B tests. `results/browser-compare-20260607T105812/browser-compare.json`
  used override `1` and passed quality with Arti download-page load
  `8288.334ms`. `results/browser-compare-20260607T110542/browser-compare.json`
  used override `3` and passed quality with Arti load `4269.500ms`; Arti beat
  bundled C Tor `6063.182ms` and local C Tor `4863.742ms` in that focused run.
  A nearby spread run `20260607T110049` had Arti success `3/3`, but the whole
  run failed quality because bundled C Tor missed one screenshot, so it is only
  rejected diagnostic data.
- The runner now also supports a same-window extra Arti profile with
  `--extra-arti-exit-select-parallelism`. It sets each Arti profile's
  `storage.port_info_file` inside that profile state directory, so multiple
  Arti proxies do not fight over the default global port-info file.
- The runner now also supports `--arti-min-exit-circs-for-port` as a bounded
  lab override. It records the override at the top level and in each Arti
  profile.
- `results/browser-compare-20260607T111656/browser-compare.json` ran the
  focused same-window A/B: Arti spread `3`, Arti control `1`, bundled C Tor,
  and local C Tor all in one measured proxy window. It passed quality. Arti
  spread `3` loaded the download page in `3173.693ms`; control `1` loaded in
  `8709.136ms`; bundled C Tor loaded in `5105.234ms`; local C Tor loaded in
  `4253.623ms`. Spread `3` beat control `1` in `3/3` paired runs with median
  load delta `-5535.443ms`.
- `results/browser-compare-20260607T112445/browser-compare.json` repeated the
  same-window A/B with 5 runs, 3 targets, and bundled C Tor included. It failed
  quality only because bundled C Tor had one homepage `netTimeout` and missed a
  screenshot. Arti width `3`, Arti width `1`, and local C Tor all succeeded.
  Use it as rejected diagnostic data only. Its Arti A/B table showed width `3`
  slower than width `1` on all three target medians.
- `results/browser-compare-20260607T113402/browser-compare.json` reran the
  stronger same-window A/B with `--skip-bundled-tor`, 5 runs, and 3 targets. It
  passed quality. Width `3` was slower than width `1` on all three paired
  median load deltas: `+965.497ms` on `check.torproject.org`, `+369.719ms` on
  the homepage, and `+3146.486ms` on the download page. Width `1` is the better
  current default; width `3` stays lab-only.
- `results/browser-compare-20260607T115225/browser-compare.json` tested the
  current rebuilt Arti binary with no exit-select env override. It passed
  quality and recorded `source_tweaks.arti_exit_select_parallelism = 1`.
  Page-only load still lost to local C Tor on all three targets: `+106.354ms`
  paired median on `check.torproject.org`, `+2906.736ms` on the homepage, and
  `+2192.737ms` on the download page. Fast warm boot kept boot+load faster on
  `check.torproject.org` and near-even on the download page, but this is not a
  full speed win.
- `tools/analyze_browser_compare.py` now prints load-tail resource deltas. On
  the latest default-width proof, the biggest Arti tail gaps were homepage and
  download images/CSS ending after DOM, such as `circle-pattern.svg`,
  `browse-freely.svg`, and `TBA10.0.png`.
- `tools/analyze_browser_compare.py` now also prints resource connection-shape
  rows: origin count, protocol summary, fetch-start buckets, request-start span,
  fetch-to-request median, and request-wait median.
- `results/browser-compare-20260607T120157/browser-compare.json` ran one
  current-default homepage debug correlation. It passed quality but is debug
  evidence only. It showed hostname SOCKS connect/reply was immediate, relay
  receive had `0` queue-full events, stream scheduler had `0` blocked hops, and
  the top six relay receive DATA streams were all on `Circ 0.0`.
- `results/browser-compare-20260607T120836/browser-compare.json` tested
  `--arti-min-exit-circs-for-port 3` without changing the source default of `2`.
  It passed quality but was much slower on the homepage: Arti median load
  `13434.135ms`, local C Tor `3642.484ms`, paired delta `+9791.651ms`, and Arti
  wins `0/2`. Reject this exact count `3` direction.
- `results/browser-compare-20260607T121622/browser-compare.json` ran a 3-run
  homepage resource-shape proof with `nextHopProtocol`. It passed quality.
  Arti still lost page-only load to local C Tor (`5686.759ms` versus
  `3928.422ms`), but both profiles used one origin and mostly HTTP/1.1:
  Arti `http/1.1:95, unknown:10`, local C Tor `http/1.1:89, unknown:16`.
  Arti was already ahead at response start but lost after that, with
  `+1366.694ms` DOM-to-load and larger same-origin resource tails.
- `results/browser-compare-20260607T122018/browser-compare.json` ran the same
  homepage through a neutral byte tap. It passed quality. Under the tap, Arti
  won page-only load (`4569.460ms` versus local C Tor `5584.255ms`) and had
  faster median first stream data (`385.090ms` versus `453.879ms`). Treat this
  as diagnostic only because the tap is a measurement hop, but it points away
  from SOCKS setup or late first bytes as the main remaining normal-run problem.
- The analyzer now also groups byte-tap connections by browser run. In the same
  tap proof, Arti stream-data spans tracked its load times (`7193.961ms`,
  `4662.501ms`, `3133.698ms`), while the slow local C Tor tap run had a
  `12689.837ms` stream-data span and a `3620.188ms` max data gap.
- `results/browser-compare-20260607T123004/browser-compare.json` ran a 2-run
  no-tap homepage debug proof with a large Arti proxy log tail. It passed
  quality. Arti lost page-only load to local C Tor (`6373.530ms` versus
  `4867.553ms`) but won boot+load. Internal relay receive grouping showed Arti
  run 1 had `717` DATA cells over `4` circuits and `16` streams with a
  `6000ms` receive span; run 2 had `856` DATA cells over `6` circuits and `17`
  streams with an `11000ms` receive span and a `4000ms` max receive gap.
- Local Arti source now adds millisecond `event_epoch_ms` fields to
  debug-only relay receive logs, and the analyzer prefers that field over the
  coarse log timestamp when present.
- `results/browser-compare-20260607T124126/browser-compare.json` reran the
  no-tap homepage debug proof with the higher-resolution relay receive logs.
  It passed quality but was much slower as debug evidence: Arti median load
  `14194.317ms`, local C Tor `3867.974ms`, paired delta `+10326.343ms`. The
  useful bottleneck fact is that run 2 had a `26563ms` internal receive span
  and a real `3730ms` max receive gap, so the prior gap signal was not just
  second-level log rounding.
- Local Arti source now logs a debug-only SOCKS stream link after stream
  creation: SOCKS `timing_id`, target kind, circuit id, hop, and stream id.
- The analyzer now prints `Torfast SOCKS To Relay Receive Join`, mapping SOCKS
  timing ids to exact Arti relay receive stream rows.
- The analyzer now also prints `Torfast SOCKS To Relay Per-Run Summary`, which
  groups those joined streams by browser run window.
- The analyzer now prints `Browser Resource To SOCKS Relay Join (nearest)`,
  which maps browser resource URLs to the nearest joined SOCKS stream by
  connection timing. This is an approximate match because the browser does not
  expose Arti stream ids.
- The analyzer now also prints `Browser Resource To SOCKS Relay Summary`, which
  groups those approximate resource matches by profile and target. It keeps
  resource count, match confidence, slow-resource count, median resource phases,
  critical resource-tail fields, median relay time, and max joined receive gap
  in one row.
- `results/browser-compare-20260607T125446/browser-compare.json` ran a 2-run
  no-tap homepage debug proof with that join table. It passed quality. Arti won
  this debug sample, so it is not the slow-tail proof we need, but it proved the
  join works. The largest joined receive gap was `684ms`; the largest joined
  DATA stream had `721` DATA cells, `346978` DATA bytes, `1695ms` receive span,
  and `437ms` max receive gap. The per-run join summary found `14` joined
  streams in each Arti run, with max joined receive gaps of `616ms` and `684ms`.
  The nearest resource join table matched the slowest favicon row to timing id
  `8`, stream `672`, with a `285ms` max receive gap.
- `results/browser-compare-20260607T131326/browser-compare.json` ran the normal
  5-run, 3-target same-window gate with `--arti-log-level info`, but failed
  quality because Arti homepage run 2 hit `about:neterror` connection failure.
  The proxy log showed `All tunnel attempts failed due to timeout`.
- Local Arti source now retries SOCKS CONNECT once when `connect_with_prefs`
  returns `ErrorKind::TorNetworkTimeout`. This is a quality-preserving fallback:
  it does not retry invalid targets, remote failures, or non-timeout errors.
- `results/browser-compare-20260607T132404/browser-compare.json` reran the full
  normal 5-run, 3-target same-window gate after that retry patch. It passed
  quality. Arti beat local C Tor median page-only load on all three targets:
  `1934.205ms` vs `2707.171ms` on `check.torproject.org`,
  `5734.770ms` vs `5913.474ms` on the homepage, and `5992.235ms` vs
  `7901.429ms` on the download page. Paired load wins were `4/5`, `3/5`, and
  `4/5`.
- `results/browser-compare-20260607T133349/browser-compare.json` repeated the
  same full gate. It also passed quality. Arti lost `check.torproject.org` by
  page-only median load (`2802.599ms` vs `2052.168ms`, paired delta
  `+93.280ms`, Arti wins `2/5`) but won the homepage (`4423.439ms` vs
  `6335.317ms`, paired delta `-195.951ms`, Arti wins `3/5`) and download page
  (`6530.057ms` vs `8458.377ms`, paired delta `-559.974ms`, Arti wins `3/5`).
- `results/arti-rpc-path-20260607T134227/arti-rpc-path.json` passed after the
  retry patch. It checked 3 live Arti RPC paths against C Tor directory data:
  3 hops, guard first hop, required relay flags, exit last hop, no relay ID
  reuse, no relay-family overlap, and no same IPv4 `/16`.
- `results/browser-compare-20260607T135113/browser-compare.json` ran a debug
  3-run, 3-target diagnostic. It passed quality but is not a fair speed proof.
  The new navigation-to-SOCKS join table showed the homepage outlier was a
  slow successful CONNECT: `49891ms` until stream ready, then only `288.348ms`
  from first Tor byte to browser response. Small-page and download main
  navigation streams did not show that same 50s connect wait.
- Local Arti source now has a default-off, bounded lab soft-timeout override
  for non-onion SOCKS CONNECT:
  `TORFAST_SOCKS_CONNECT_SOFT_TIMEOUT_MS`. It retries one slow successful
  CONNECT attempt without changing `.onion` streams.
- `results/browser-compare-20260607T140722/browser-compare.json` ran a focused
  5-run homepage lab with `--arti-socks-connect-soft-timeout-ms 5000`. It
  passed quality, but the analyzer found `0` soft timeouts. Arti was slower by
  median load (`6820.331ms` vs `4203.084ms`), though response start was faster
  (`850.017ms` vs `983.353ms`). This proves wiring and safety only; it is not
  slow-CONNECT speed proof.
- `results/browser-compare-20260607T141652/browser-compare.json` ran a
  same-window baseline Arti vs `--extra-arti-socks-connect-soft-timeout-ms
  1500` A/B. It passed quality, but the analyzer again found `0` soft
  timeouts. Soft-timeout Arti had a better median load (`3832.178ms`) than
  baseline Arti (`4990.866ms`) and local C Tor (`4154.073ms`), but its max load
  was `81790.668ms`, with a `60430ms` relay receive gap and `82252ms` hostname
  relay span. This is not speed proof; it points to relay/resource tail
  behavior.
- The joined-stream gap detail for `20260607T141652` shows that gap exactly:
  timing id `20`, hostname stream `54447`, `Circ 0.11 (Tunnel 17)`, had a
  `60430ms` `DATA` to `DATA` gap. The next event's `queued_before` was `0`, so
  the local output queue was not visibly backed up when data resumed.
- Local Arti source now logs stream receiver read and SENDME/window context.
  `results/browser-compare-20260607T144256/browser-compare.json` passed quality
  and proved the new analyzer tables work, but it did not reproduce the long
  tail: max joined stream gap was `665ms`, with receiver reads visible inside
  those smaller gaps and `0` SENDMEs due inside them.
- `results/browser-compare-20260607T144921/browser-compare.json` reproduced a
  bad debug homepage tail and passed quality. The bad Arti run waited
  `43414ms` before SOCKS reply on timing id `42`; circuit-selection logs showed
  one pending exit circuit at `06:50:53` and a new build at `06:51:36`. Joined
  page streams only had `486ms` max receive gap, so this tail was pending exit
  circuit wait, not stream receiver/SENDME pressure.
- Local Arti source now has a default-off, bounded pending exit-circuit hedge
  with `TORFAST_EXIT_PENDING_HEDGE_MS`. It is exit-only, bounded from `500ms`
  through `60000ms`, keeps the max pending cap at `2`, and now arms a timer so
  the first slow waiter can re-run circuit selection after the threshold.
- `results/browser-compare-20260607T150149/browser-compare.json` tested a
  same-window `1500ms` pending-hedge profile. It failed quality because the
  hedge profile run 5 hit Firefox `netTimeout`. The analyzer saw `0` pending
  hedge events, so this did not exercise or prove the hedge.
- `results/browser-compare-20260607T151858/browser-compare.json` reran the
  hedge A/B after the timer patch with a warm-cache 3-run `500ms` profile. It
  passed quality, but still had `0` pending hedge launches. Baseline Arti median
  load was `4236.640ms`; pending-hedge Arti was `4533.537ms`; local C Tor was
  `5105.223ms`.
- `results/browser-compare-20260607T152131/browser-compare.json` tried a
  no-warm-cache 2-run `500ms` hedge profile. It passed quality, but again had
  `0` pending hedge launches. Baseline Arti median load was `3859.752ms`;
  pending-hedge Arti was `8365.920ms`; local C Tor was `6212.244ms`.
- `results/browser-compare-20260607T153223/browser-compare.json` added generic
  stream-reactor congestion-block logging and ran a warm-cache 3-run homepage
  proof. It passed quality. Arti median load was `3113.562ms`; local C Tor was
  `4516.283ms`. Arti had `0` stream-reactor congestion blocks and `0`
  stream-scheduler hop blocks, so this proof does not point at the generic
  `can_send()` gate.
- The analyzer now adds a per-run circuit-shape table. In
  `20260607T153223`, each run had one dominant hostname circuit. The slow run
  put `9` streams and `1253594` data bytes on `Circ 1.4 (Tunnel 13)`, with a
  max receive span of `5196ms`.
- Local Arti source now has a default-off load-aware open-circuit selector for
  exit streams. It chooses the least-assigned circuit among already eligible
  open circuits, keeps all path/isolation checks, and does not build extra
  circuits.
- `results/browser-compare-20260607T154907/browser-compare.json` ran a
  same-window load-aware A/B. It passed quality. Baseline Arti median load was
  `6207.200ms`; load-aware Arti was `3449.575ms`; local C Tor was
  `3455.741ms`. The analyzer counted `26` load-aware exit picks and `0`
  stream-reactor congestion blocks.
- `tools/analyze_browser_compare.py` now prints an `Arti Profile A/B` table for
  extra Arti profiles, with paired phase/load deltas and max-load tail deltas
  against baseline Arti. It also prints direct Arti profile resource type,
  top-resource, load-tail, HTTP-phase, HTTP queue-shape, and top-resource
  relay-context A/B tables for the same baseline/candidate pairs.
- `results/browser-compare-20260607T155934/browser-compare.json` ran the wider
  5-run, 3-target same-window load-aware gate. It passed quality. Load-aware
  Arti beat baseline Arti by median load on all three targets:
  `1780.184ms` vs `1887.842ms` on `check.torproject.org`, `4232.771ms` vs
  `9061.474ms` on the homepage, and `6000.187ms` vs `8937.480ms` on the
  download page. It also beat local C Tor by median load on the two larger
  pages, but not on `check.torproject.org`.
- The same wider load-aware gate is not default-ready: load-aware Arti's
  download-page max load was `65953.543ms`, while baseline Arti's max was
  `11525.708ms`. Fix the tail before promotion.
- Inspecting that bad download tail showed timing id `35` waited about
  `60027ms`, returned `TorNetworkTimeout`, then retried and connected in
  `746ms`. It was not caused by choosing among open circuits; Arti had no
  eligible open circuit and was waiting for isolated exit readiness.
- `results/browser-compare-20260607T161639/browser-compare.json` ran a focused
  download-page profile with load-aware baseline Arti plus an extra load-aware
  `--extra-arti-socks-connect-soft-timeout-ms 5000` profile. It passed quality.
  The soft-timeout profile beat load-aware baseline Arti on paired loads `5/5`
  and had median load `5335.235ms` versus baseline `13570.841ms` and local C
  Tor `7209.919ms`. But the analyzer counted `0` soft timeouts, so this does
  not prove the exact 60s CONNECT tail is fixed.
- `tools/analyze_browser_compare.py` now prints a direct
  `Torfast SOCKS Connect Retries` table and target-kind max CONNECT rows. On
  the older bad load-aware gate, that table exposes timing id `35`: one
  `TorNetworkTimeout` retry at `60027ms`, retry success in `746ms`, final
  connect `60773ms`.
- `results/browser-compare-20260607T162821/browser-compare.json` ran the same
  focused download-page A/B with a lower `1000ms` non-onion soft timeout. It
  passed quality but did not fire the timeout. The `1000ms` profile was slower:
  median load `7301.248ms` versus load-aware baseline `5440.053ms` and local C
  Tor `4755.504ms`. Its hostname CONNECT max was `928ms`; the slow connects
  were `.onion`, which the timeout correctly skips.
- Local Arti source now also lets `TORFAST_EXIT_PENDING_HEDGE_MS` cover the
  initial build wait path. `results/browser-compare-20260607T164207/browser-compare.json`
  tested load-aware baseline Arti against load-aware plus a `1500ms` pending
  hedge profile on the download page. It passed quality and counted `1` pending
  hedge, but `0` build hedge timers. The hedge profile was slower: median load
  `7529.626ms` versus baseline `5928.687ms` and local C Tor `4481.306ms`.
  Direct resource A/B says every sampled type was slower too: CSS `+733.348ms`,
  images `+708.348ms`, scripts `+516.677ms`, links `+466.676ms`, and other/font
  resources `+383.341ms`.
- `results/browser-compare-20260607T165147/browser-compare.json` then ran a
  no-warm-cache `500ms` hedge A/B on the download page. It passed quality and
  counted `1` build hedge timer plus `1` pending hedge. The hedge profile was
  still slower by median load: `5783.041ms` versus baseline `5236.727ms` and
  local C Tor `4603.830ms`, though its max load was lower than baseline
  (`5936.394ms` versus `7543.990ms`).
- The new resource-to-relay summary for `20260607T165147` shows the mixed shape:
  the `500ms` hedge profile had lower matched median relay time (`3987ms` versus
  `4162ms`) and lower max receive gap (`878ms` versus `1482ms`) than load-aware
  baseline, but still worse median page load. Do not treat one lower tail metric
  as a speed win.
- The critical-tail fields for the same run sharpen that: max resource response
  end improved, but max tail after DOM was slightly worse and median
  resource-end-before-load was similar. The next speed idea needs to improve
  late resource pacing across the page, not just launch another circuit sooner.
- The direct Arti A/B phase split for `20260607T165147` shows the largest hedge
  regression was response-to-DOM (`+583.345ms`), not first response
  (`+116.669ms`) or DOM-to-load (`+116.669ms`). Focus the next source idea on
  resource/stream pacing during page construction.
- Direct resource A/B for `20260607T165147` names the bad groups and rows:
  images were `+291.672ms` by median duration, links `+91.668ms`, scripts
  `+33.334ms`, and the worst exact losses were `get-connected.svg`
  `+733.348ms`, `fa-regular-400.woff2` `+450.009ms`, `stay-safe.svg`
  `+450.009ms`, and `modernizr.js` `+316.673ms`. Load-tail losses after DOM were
  concentrated in icon/image/font resources.
- The new top-resource relay-context A/B table for `20260607T165147` says those
  resource losses did not come from a simple worse matched relay median. The top
  image/font losses had relay delta `-175ms`, and the high-confidence script
  losses had relay delta `-177ms` plus max receive gap delta `-604ms`.
- The direct HTTP-phase A/B table for `20260607T165147` says the same top losses
  were all `http/1.1`, mostly with zero connect setup in both profiles.
  `get-connected.svg` lost mainly before request send (`+483.343ms`
  fetch-to-request) and waiting for response (`+166.670ms` request-wait), not in
  body receive (`+33.334ms`). `modernizr.js` lost mainly in request-wait
  (`+216.671ms`).
- The broader HTTP queue-shape A/B table for `20260607T165147` says `500ms` did
  not create a whole-page queue blow-up: `http/1.1` queued `>=500ms` resources
  were `80/104` versus baseline `79/103`, zero-connect resources were `87/104`
  versus `88/103`, and median fetch-to-request was `-33.334ms`. The broad median
  request-wait still worsened by `+58.334ms`.
- `results/browser-compare-20260607T173526/browser-compare.json` reran the
  focused no-warm-cache download-page A/B with `--byte-tap`. It passed quality.
  The `500ms` profile was faster in that tap window: median load `5085.237ms`
  versus load-aware baseline `5927.124ms` and local C Tor `5930.657ms`, but it
  counted `0` pending hedge timers, `0` build hedge timers, and `0` pending
  hedges. Treat this as byte-tap connection-shape proof, not hedge speed proof.
- The resource-to-byte-tap group table for `20260607T173526` supports the
  shared HTTP/1.1 connection hypothesis. In the `500ms` profile, the cleanest
  next target is run 2 connection `21`: `10/10` rows high confidence, `8/8`
  slow rows high confidence, median slow duration `2641.720ms`, median slow
  fetch-to-request `891.685ms`, median slow wait `1325.027ms`, stream bytes
  `46924`, and max data gap `292.436ms`. Run 1 connection `4` was also clean
  (`4/4` slow rows high confidence) but much more tail-heavy. Some larger groups
  were low-confidence nearest matches, so do not patch from those alone.
- `results/browser-compare-20260607T175344/browser-compare.json` reran the
  focused byte-tap proof after adding per-run relay context capture. It passed
  quality and proves the new capture works: each Arti browser run saved per-run
  proxy signal lines and `1000` relay context lines, so middle-run relay joins
  are no longer lost.
- The cleanest source target in `20260607T175344` is
  `arti_release_browser_pending500ms` run `2`, tap connection `18`. It had
  `9/9` slow tap rows high confidence and `9/9` relay joins high confidence.
  All those slow resources joined to timing id `19`, circuit
  `Circ 3.5 (Tunnel 18)`, stream `11369`. The browser loss was mostly before
  request/response: median slow fetch-to-request `1850.037ms`, wait
  `483.343ms`, receive only `116.669ms`.
- The matching stream context does not look like a simple local queue/SENDME
  failure. Timing id `19` had relay time `3346ms`, max relay gap `476ms`,
  `8` receiver reads inside that gap, `1` successful SENDME, min receive window
  `451`, and max queued bytes `2736`.
- The same queue-shape table for `20260607T164207` says `1500ms` did create a
  broad HTTP/1.1 queue/request-wait regression: queued `>=500ms` resources were
  `146/174` versus baseline `134/176`, median fetch-to-request was `+366.674ms`,
  and median request-wait was `+250.005ms`.
- Earlier interleaved files before `20260607T061526` undercounted some boot
  timings. Result `20260607T061526` fixed boot timing but did not rotate
  profile order, so `20260607T115225` is the latest accepted default-width
  browser proof.
- `tools/check_c_tor_circuits.py` passed against local C Tor and checked 6
  built 3-hop circuits.
- `tools/check_arti_quality_config.py` passed 23 static source/config checks,
  including Arti SOCKS auth to stream-isolation mapping and optimistic SOCKS
  CONNECT, plus bounded exit-select and non-onion CONNECT soft-timeout lab
  override checks, bounded pending exit-circuit hedge timer checks including the
  initial build timer log, and the reverted preemptive count default of `2`,
  plus the default-off load-aware open-circuit selector and same-isolation
  capacity top-up. This is useful, but it is not live circuit-path proof.
- `tools/check_arti_rpc_path.py` passed against an RPC-enabled Arti build and
  checked 3 live paths from the patched source with RPC plus C Tor directory
  data: 3 hops, guard first hop, required relay flags, exit flag, no relay ID
  reuse, no relay-family overlap, and no same IPv4 `/16`.
- `tools/run_cache_diagnostic.py` showed Arti warm-cache boot can be very fast,
  but warm Arti still does not clearly win on fetches and does not explain the
  browser page-load slowdown.

Next:

- Keep normal exit-select width `1` as the default. Width `3` helped one
  one-target same-window run, but the accepted 5-run, 3-target A/B rejected it
  as a default.
- Treat the post-timeout-retry speed result as promising but not final. Two full
  gates passed, and Arti won both larger pages twice, but `check.torproject.org`
  is mixed by page-only load.
- Keep the slow-successful-CONNECT fallback lab-only. The latest two soft
  timeout runs did not fire it, so do not treat it as a speed fix.
- The load-aware plus soft-timeout download run is promising, but also lab-only.
  It was faster than load-aware baseline Arti and local C Tor in that window,
  but the soft timeout did not fire.
- Reject `1000ms` as a speed direction for now. It passed quality, but it was
  slower by median load and still did not fire because normal hostname CONNECT
  stayed below the threshold in that run.
- Keep the pending exit-circuit hedge lab-only. One bad tail proves the pending
  wait exists, and later passing runs captured both `pending_hedge` and
  `build_hedge_timer` events. But both hedge profiles were slower by median
  load, so do not promote them.
- Reject the current `500ms` and `1500ms` hedge thresholds as speed directions
  for now. A better hedge needs a sharper condition than "waited this many ms."
- Also keep chasing relay/resource tails. The latest hedge-profile failure had
  immediate CONNECT and live hedge events, but the direct resource A/B table put
  the loss in image/font/icon/script tails during response-to-DOM, and relay
  context did not show worse matched relay medians for the top losses. The
  HTTP-phase and queue-shape tables point to specific late HTTP/1.1
  request/response scheduling, not a broad new-connect problem.
- Keep using the navigation-to-SOCKS and resource-to-relay join tables for the
  next proof. They directly separate stream-ready wait, first-byte delay, and
  relay/resource receive stalls.
- The SOCKS write diagnostic ruled out browser-facing writes in the latest clean
  proof: slow high-confidence tap/relay groups had `0.000ms` write lag. Do not
  spend the next patch on local SOCKS flush. Follow the long relay receive gaps
  and stream receiver path instead.
- The circuit-gap replay on the same clean proof says the worst same-stream
  receive gap, `4917ms`, was not a whole-circuit idle gap. The largest same-run
  gap on that circuit was `2924ms`, and another stream moved on the circuit.
  Do not patch the generic circuit reactor from this evidence.
- Do not simply make width `3`, preemptive count `3`, or broad exit racing the
  default; broader proof rejected those or needs a relay-bias review first.
- Next source proof should use the new stream receiver gap-context table on a
  reproduced long relay receive gap. If stream reads keep moving, SENDME is not
  due, and the circuit is not idle, inspect per-stream resource/HTTP timing or
  exit/server latency next. The queue bytes already suggest this is not simply a
  full local stream queue.
- The new browser resource stream-gap context table names the best current
  target from `20260607T181517`: timing id `19`, stream `25673`, had a `3803ms`
  relay receive gap that fully overlapped browser `request_wait` and had `33`
  same-stream resource matches. Inspect this path before changing global
  circuit scheduling.
- The new byte-context table says timing id `19` had `0` strict-middle browser
  bytes and `528` browser bytes on the gap edges. Local Arti source now logs
  debug-only `client_to_tor_write` byte events. Next fresh proof should check
  whether those browser bytes are written into the Tor stream immediately.
- The fresh write-side proof saved
  `results/browser-compare-20260607T184405/browser-compare.json`. It passed
  quality and showed `client_to_tor_write` matching `client_to_tor` timings and
  bytes in sampled streams. It did not reproduce the old `3803ms` request-wait
  gap; max joined stream gap was `701ms`. Treat the apparent `500ms` hedge win
  in this run as diagnostic only because debug logging and byte tap were on.
- The clean normal hedge gate saved
  `results/browser-compare-20260607T184844/browser-compare.json`. It passed
  quality with no debug logging and no byte tap. Base load-aware Arti beat local
  C Tor by median load, `5147.814ms` versus `6913.908ms`, but the `500ms` hedge
  profile lost to base load-aware Arti at `6239.814ms`. Reject the `500ms`
  hedge as a page-load speed direction for this shape.
- The broader normal load-aware gate saved
  `results/browser-compare-20260607T185521/browser-compare.json`. It failed
  quality because base load-aware Arti had one `check.torproject.org`
  connection-failure neterror with no screenshot. It still beat local C Tor by
  median load on the homepage and download page, but lost on check and had a
  download max load of `58775.544ms` with browser `connectEnd` at
  `52751.055ms`.
- The first focused `500ms` soft-CONNECT A/B saved
  `results/browser-compare-20260607T190326/browser-compare.json`. It failed
  quality because the soft-timeout profile caused early browser neterrors. Local
  Arti source now uses the timeout only while another retry is still allowed;
  the final attempt waits normally.
- The fixed focused `500ms` soft-CONNECT A/B saved
  `results/browser-compare-20260607T191031/browser-compare.json`. It passed
  quality, proving the early-failure shape is fixed in this sample, but
  `500ms` soft timeout still lost to local C Tor on both focused targets by
  median load.
- The retained-log download diagnostic saved
  `results/browser-compare-20260607T192045/browser-compare.json`. It passed
  quality with debug logs, so it is diagnostic only. Base load-aware Arti was
  much slower than local C Tor by median load, `15464.467ms` versus
  `5127.752ms`. Fixed soft-timeout Arti was closer at `5519.348ms`, but it
  counted `0` soft timeouts and still lost to local C Tor. Hostname CONNECT was
  immediate in this run; the loss was response-to-DOM, DOM-to-load,
  relay/resource tail, and HTTP/1.1 queue timing. The analyzer also saw `0`
  stream scheduler hop blocks and `0` relay queue-full events. The corrected
  circuit table shows multiple exit candidates often existed, but select
  parallelism stayed `1` and slow tails remained.
- The candidate-choice diagnostic saved
  `results/browser-compare-20260607T193855/browser-compare.json`. It passed
  quality with debug logs. Base load-aware Arti was close to local C Tor by
  median load, `5227.943ms` versus `4871.780ms`, while fixed soft-timeout Arti
  was much slower at `9211.781ms`. The new candidate assignment log showed the
  load-aware picker alternating to the least-assigned circuit when multiple
  candidates existed. The bad soft-timeout tail had `0/6` exit picks with more
  than one candidate and reused one circuit up to `5` assigned streams.
- The support-cause diagnostic saved
  `results/browser-compare-20260607T194925/browser-compare.json`. It passed
  quality with debug logs. Base load-aware Arti beat local C Tor by median load,
  `3908.519ms` versus `4075.043ms`; fixed soft-timeout Arti was faster by
  median load at `3373.252ms` but still had a `14936.910ms` max-load tail. The
  new open-support summary showed the candidate shrink was mostly stream
  isolation: fixed soft-timeout run 3 had max open total `9`, max rejected open
  `8`, max isolation rejects `7`, max port rejects `0`, and max unusable `0`.
- The same-isolation capacity lab saved
  `results/browser-compare-20260607T201555/browser-compare.json` and
  `results/browser-compare-20260607T201803/browser-compare.json`. Both passed
  quality. Target `2` had `0` top-ups, so it was wiring proof only. Target `3`
  had `4` same-isolation top-ups and `0` failures, cut max Arti load from
  `10379.077ms` to `6551.679ms`, but median load stayed flat:
  `3880.539ms` versus baseline `3844.865ms`. Keep it lab-only.
- The broader same-isolation debug proof saved
  `results/browser-compare-20260607T202610/browser-compare.json`. It passed
  quality and exercised target `3` and target `4` in one window. Target `3`
  helped the download page but hurt the smaller pages. Target `4` helped some
  medians but still had a `59612.396ms` download max tail.
- Local Arti source now gates same-isolation top-up on reuse pressure:
  `selected_assigned_streams > 0`. This keeps the lab path from building extra
  circuits on the first use of a new isolation group. The top-up event now logs
  at info level so low-log runs can still count it.
- The pressure-gated target `3` proof saved
  `results/browser-compare-20260607T204728/browser-compare.json`. It passed
  quality with `9` top-ups and `0` failures. It beat baseline Arti and local C
  Tor on the homepage and download-page medians, but was slower than baseline
  Arti on the small page.
- The fairer low-log 5-run gate saved
  `results/browser-compare-20260607T205407/browser-compare.json`, but failed
  quality. Target `3` had one download-page `about:neterror` timeout and no
  screenshot. Treat it as rejected speed proof, even though info-level top-up
  counting worked.
- The smaller low-log target `2` download-page gate saved
  `results/browser-compare-20260607T212007/browser-compare.json`. It passed
  quality and counted `1` same-isolation top-up with `0` failures, but it was
  slower by median load than baseline Arti: `8298.258ms` versus `4415.803ms`.
  Reject target `2` as speed proof.
- The smaller low-log target `3` download-page gate saved
  `results/browser-compare-20260607T212559/browser-compare.json`. It passed
  quality and counted `1` same-isolation top-up with `0` failures, but it was
  also slower than baseline Arti: `6627.799ms` versus `5003.338ms`. Reject
  this focused target `3` run as speed proof too.
- The browser connection pref diagnostic saved
  `results/browser-compare-20260607T213549/browser-compare.json`. It passed
  quality and proved the focused download page used HTTP/1.1 under the normal
  Tor Browser cap of `6` persistent connections per server. Do not tune browser
  connection prefs as the speed path; keep the browser behavior and work on
  Tor-side resource/relay tails.
- `tools/analyze_browser_compare.py` now prints a browser resource stream-gap
  phase summary. It groups joined relay gaps by browser phase so a fresh proof
  can show whether the slow time is fetch-to-request queueing, request wait,
  response receive, or unmatched relay/resource time.
- The focused replay saved
  `results/browser-compare-20260607T214417/browser-compare.json`. It passed
  quality with debug logs. Base Arti beat local C Tor on the download page by
  median load, `3636.147ms` versus `6204.217ms`, but load-aware Arti lost to
  base Arti at `5540.512ms`. The new phase summary showed the load-aware loss
  came with larger request-wait overlap and unmatched stream-gap time. Keep
  load-aware lab-only.
- Local Arti source now has a default-off load-aware spread guardrail:
  `TORFAST_EXIT_SELECT_MIN_ASSIGNMENT_SPREAD`. It only lets load-aware
  selection move away from the normal first eligible circuit when assigned
  stream spread reaches the configured value. The focused spread `2` proof saved
  `results/browser-compare-20260607T215932/browser-compare.json`. It passed
  quality and activated the guardrail `5` times, but spread-guarded load-aware
  was slower than base Arti by `735.496ms` median load. Reject spread `2` as a
  speed proof.
- `tools/analyze_browser_compare.py` now prints `Torfast SOCKS Relay Circuit
  Quality` and a run summary. The spread `2` proof shows the selector spread
  work onto some circuits with long relay times and low rough receive rates:
  base Arti had `0` low-rate circuits in both runs, while old load-aware and
  spread `2` each had low-rate circuits. The next proof should measure circuit
  health instead of adding another spread threshold.
- The analyzer now also prints a load-aware selected-vs-first health outcome
  table. In `20260607T215932`, old load-aware picked a worse non-first circuit
  `3/3` times in run 1 and `4/4` times in run 2; spread `2` did this `3/3`
  times in run 1.
- Local Arti source now exposes a read-only circuit health snapshot from
  incoming RELAY DATA cells and logs `candidate_health_summary` for load-aware
  candidate circuits.
- The focused `20260607T223225` browser proof passed quality and confirmed the
  health signal is visible in logs: load-aware had `30` parsed candidate health
  rows. Load-aware was faster than base Arti and local C Tor in this narrow
  2-run debug window, but it stays lab-only until repeated broader proof.
- Local Arti now has a default-off `TORFAST_EXIT_SELECT_HEALTH_AWARE` lab
  selector. It only runs with `TORFAST_EXIT_SELECT_LOAD_AWARE` on exit requests,
  keeps the already eligible candidate set, and scores candidates from observed
  RELAY DATA cells and bytes.
- The focused `20260607T225227` health-aware browser proof passed quality. It
  beat base Arti by `1548.366ms` median load and the selector changed `12`
  assignment-only choices, but it lost to plain load-aware by `63.886ms` median
  load and to local C Tor by `1600.430ms`. Keep it lab-only and improve the
  low-rate or slow-relay guard before broader gates.
- The follow-up `20260607T230909` proof rejected an early guard shape:
  health-aware median load was `12815.382ms`, and selector logs showed a
  once-fast circuit could be chosen after its score had gone stale.
- Local Arti now rejects stale health scores older than `2000ms`. The focused
  `20260607T231745` proof passed quality: health-aware median load was
  `5011.993ms` versus base Arti `6931.042ms`, plain load-aware `5716.333ms`,
  and local C Tor `6638.935ms`. It stays lab-only because this is only a
  2-run debug proof and run 1 still had low-rate and slow-relay circuits.
- The broader `20260607T232339` health-aware gate passed quality across check,
  homepage, and download, with 3 runs per target. Health-aware beat base Arti
  and plain load-aware on all three target medians and cut their bad tails.
  Against local C Tor it was basically tied on check, `68.302ms` slower on the
  homepage, and `480.184ms` faster on download by paired median page load. Keep
  it lab-only because this is still a small debug gate.
- The larger low-log `20260607T233909` health-aware gate failed quality.
  Health-aware download run 3 hit browser `about:neterror` connection failure
  after `61518.070ms` elapsed and had no screenshot proof. The accepted
  health-aware download median was also slow: `11170.564ms` versus base Arti
  `5989.706ms`, plain load-aware `5679.386ms`, and local C Tor `4774.818ms`.
  Reject health-aware promotion until a retained-log failure proof or reliability
  guard explains this.
- The runner now retains failed-run evidence in compact mode: failed browser
  profile/home directories stay, and failed runs keep a per-run proxy output
  tail even if there are no `torfast` signal lines.
- The runner also has a default-off `--proxy-run-tail-lines` option for
  successful interleaved runs, and the analyzer prints `Browser Run Proxy
  Tails` when those per-run tails exist.
- The focused retained-runner check `20260607T235651` passed quality on the
  download page, but health-aware was much slower: median load `16524.629ms`
  versus base Arti `5592.204ms`, plain load-aware `6362.165ms`, and local C
  Tor `4207.812ms`. Health-aware lost all paired page-load runs to both base
  Arti and local C Tor.
- The retained-tail check `20260608T000334` passed quality and showed the new
  option works. Health-aware beat base Arti by paired median load but still
  lost to local C Tor and plain load-aware; plain load-aware was best in that
  small window. Low-log success tails only appeared on first runs, so use debug
  `torfast` signals for the next cause-finding proof.
- The debug retained-tail check `20260608T000956` passed quality, but it
  rejected the current health-aware and plain load-aware selectors. Base Arti
  median load was `3752.832ms`, local C Tor was `5800.624ms`, health-aware was
  `18465.459ms`, and plain load-aware was `12139.927ms`. Both selector profiles
  lost all paired page-load runs to base Arti, with long relay/resource tails
  after first response.
- The selector debug logs now include candidate health score, receive span, and
  age, and the analyzer prints those fields in selection outcome tables.
  `20260608T002242` proved the new fields work and showed default
  health-aware often selected zero-score cold circuits; it still lost to base
  Arti. The lab knob `TORFAST_EXIT_SELECT_HEALTH_MIN_MOVE_SCORE_BPS` keeps the
  old default `65536`. A one-run `16000` probe `20260608T002719` changed the
  health-aware choice pattern but still lost to base Arti and kept slow-relay
  tails, so it is not a promotion path.
- Local Arti now has a default-off
  `TORFAST_EXIT_SELECT_AVOID_BAD_HEALTH` guard. It only runs inside
  load-aware exit selection and only avoids an already eligible open circuit
  when recent RELAY DATA evidence is fresh and clearly bad. The focused
  `20260608T003712` retained-tail run passed quality on the download page:
  base Arti load was `5365.140ms`, health-aware plus bad-health guard was
  `3122.296ms`, plain load-aware plus bad-health guard was `3467.987ms`, and
  local C Tor was `5030.610ms`. Base Arti had a max relay gap of `1011ms`,
  versus `352ms` and `230ms` for the guarded profiles. Keep it lab-only until a
  repeated multi-run gate proves the tail reduction is stable.
- The same-window `20260608T004859` debug gate passed quality but rejected that
  first guard shape. Plain health-aware was best at `3562.335ms` median load.
  Base Arti was `4631.022ms`, local C Tor was `4469.264ms`, plain load-aware
  was `4963.036ms`, load-aware plus bad-health guard was `5102.284ms`, and
  health-aware plus bad-health guard was `10710.535ms`. The guard could avoid a
  bad circuit and land on an unknown or weak circuit, so do not promote it.
- Local Arti now tightens `TORFAST_EXIT_SELECT_AVOID_BAD_HEALTH`: it can move
  away from a bad selected circuit only if another eligible circuit has fresh
  good health evidence. The rebuilt `20260608T005748` smoke run passed quality
  in a slow one-run window; load-aware plus tightened guard was `3865.683ms`,
  health-aware plus tightened guard was `4419.023ms`, base Arti was
  `8295.104ms`, and local C Tor was `10750.993ms`. Treat this as smoke proof
  only; the next gate must repeat it.
- The repeated same-window `20260608T010444` debug gate passed quality. The
  tightened health-aware guard was best at `4481.908ms` median load, versus
  base Arti at `7636.023ms`, plain health-aware at `4894.313ms`, plain
  load-aware at `6068.906ms`, load-aware plus tightened guard at `5927.750ms`,
  and local C Tor at `11648.196ms`. Browser max-load tails also improved:
  base Arti was `9137.651ms`, while the tightened health-aware guard was
  `6196.668ms`. Keep it lab-only because this was a debug one-target gate and
  local C Tor was slow in that network window. The next gate should be a
  low-log, no-debug, multi-target browser run.
- The low-log, no-debug `20260608T011500` 3-target gate passed quality, but it
  rejected tightened health-aware guard promotion. The guarded profile beat base
  Arti on homepage paired median load by `1280.281ms`, but lost on
  `check.torproject.org` by `116.114ms` and on the download page by
  `690.079ms`. It also had bad accepted-run tails: `62471.482ms` on
  `check.torproject.org` and `20819.463ms` on the download page. Keep it
  default-off and look for a tail-prevention rule before another promotion gate.
- The focused debug `20260608T012700` replay passed quality and did not
  reproduce the 60s first-response stall, but it confirmed the guarded
  download-page loss: guarded selector median load was `9634.479ms` versus base
  Arti `4716.176ms`, and the slow guarded runs put `6` joined streams on one
  circuit. A combined guarded same-isolation target `2` runner profile was added
  and tested in `20260608T013207`; it passed quality but was much slower
  (`10043.645ms`) than base Arti (`3610.841ms`) and guarded selector alone
  (`3577.011ms`). Reject this combination.
- The focused `20260608T013809` download-page check passed quality but rejected
  guarded minimum assignment spread `2`: base Arti median load was
  `4610.687ms`, guarded spread `2` was slower at `7525.410ms`, and local C Tor
  was `4467.486ms`. Its max load was also worse (`14123.421ms` versus base
  Arti `8023.550ms`). Keep it off.
- The runner now supports same-window health-aware threshold profiles with
  `--extra-arti-exit-select-health-min-move-score-bps`. The first threshold
  debug check `20260608T014735` failed quality because base Arti timed out on
  run `2` after `61265.920ms`, so it is not speed proof. Accepted rows still
  reject `32768`: median load was `13738.993ms` with bad relay/resource tails.
  `131072` was stable but slower than default health-aware and local C Tor in
  this window, so keep threshold tuning lab-only.
- The analyzer now prints `Browser Failed Run Torfast SOCKS Streams`. For
  `20260608T014735`, that table shows the failed base Arti run had two hostname
  streams at `60167ms` and `59810ms` relay time and one onion stream with
  `3179ms` connect plus `56021ms` relay. Treat the next source target as
  long relay-wait handling, not browser prefs or another threshold tweak.
- SOCKS relay debug logs now include last Tor-to-browser byte timing. The failed
  run table also prints idle time after that byte, so the next proof can tell
  whether a timeout was no-data wait or after-data idle wait.
- `results/browser-compare-20260608T020551/browser-compare.json` reran a
  2-run warm-cache download-page debug proof after rebuilding release Arti. It
  passed quality but was slower than local C Tor on median load
  (`4129.896ms` versus `3464.572ms`). The analyzer now also prints last-byte
  and idle-after-last-byte fields in the main SOCKS tables. This run showed
  median last Tor byte `2457.500ms`, median idle after last byte `265.500ms`,
  and max idle after last byte `3240.000ms`, so do not treat every long relay
  total as active Tor data delay. The resource-to-SOCKS join now also shows
  response end against the stream's last Tor byte; the median was `-883.959ms`,
  so this replay points next at HTTP/resource queue timing, not a broad relay
  lifetime timeout. The resource connection table now shows queue-tail counts:
  Arti had `22` resources queued at least `1000ms` before request start versus
  local C Tor `15`, and max fetch-to-request was `2450.049ms` versus
  `2050.041ms`. The new direct queue-delta table says this is an HTTP/1.1
  queue-tail gap: `+7` resources queued at least `1000ms` and `+400.008ms`
  worse max fetch-to-request for Arti. The new slot-saturation table says most
  of the long tail starts when the normal same-origin HTTP/1.1 slot cap is
  already full: Arti had `21/22` resources queued at least `1000ms` at slot
  depth `>=6`, versus local C Tor `11/15`; both median/max slot depths were
  `6`. Do not change Tor Browser caps; make the underlying stream/resource
  work finish earlier. The new slot-blocker table gives the next source target:
  the worst Arti queued row had `5` same-origin blockers, led by a
  high-confidence timing id `9` / `Circ 1.2` blocker with `516.677ms` receive
  time left; another blocker in the same row still had `400.008ms` first-byte
  wait left. For that high-confidence blocker, Arti's last write was
  `532.677ms` after the queued request started and browser response end was
  only `-16.000ms` from that write. The top local C Tor row had only
  `100.002ms` max blocker time left (`16.667ms` wait, `83.335ms` receive).
  The same blocker had `0.000ms` write-after-relay and `0.000ms`
  write-after-stream-receiver-read, with max receiver queued bytes `3948`, so
  source work should move before SOCKS copy write. After queue start, that
  blocker received `121523` relay bytes from `+172.677ms` to `+532.677ms`, with
  max after-queue relay gap `51.000ms`. Run 2 points at timing id `18` /
  `Circ 1.5` blockers with `366.674ms` max time left. The next source work
  should explain late circuit/stream relay bursts under unchanged Tor Browser
  caps. Arti source now keeps normal selector behavior unchanged but logs
  candidate assignment and health summaries at debug level even when the
  load-aware selector is off; the next debug browser replay can use that to show
  whether the late blockers had better open-circuit choices. The new
  queue-to-SOCKS tail table says
  the top queued resource was high-confidence timing id `8` on `Circ 0.0`, but
  many following rows are low-confidence nearest matches around timing id `9`;
  use this as a pointer to request/connection-slot timing, not as final circuit
  blame. The high-confidence cluster table is the better next source target:
  timing id `18` had `21` queued resources, timing id `8` had `11`, and timing
  id `9` had `4`.
- `results/browser-compare-20260608T030643/browser-compare.json` is the clean
  selector-context replay. It passed quality, but page load was still slower:
  Arti median load `4369.638ms` versus local C Tor `3669.699ms`, paired Arti
  delta `+699.939ms`. Arti boot+load was faster (`4737.638ms` versus
  `6308.699ms`), but that is not enough to claim browser speed. The queue tail
  stayed worse for Arti: `25` resources queued at least `1000ms` versus local C
  Tor `16`, and `23` of those Arti rows were at slot depth `>=6` versus local C
  Tor `8`. The new `Browser Resource Queue Selection Context` table says a
  naive selector promotion is not proved: run 1 selected `Circ 0.4` later had
  stronger health than alternatives, run 2 cold `Circ 1.6` did not look stuck,
  and the worst run 2 `Circ 0.5` cluster had no other open choice. Keep selector
  changes lab-only. Next source work should target same-isolation
  capacity/readiness or earlier resource completion while keeping browser caps,
  isolation, and path rules unchanged.
- Same-isolation capacity can now be tested without load-aware selection:
  `TORFAST_EXIT_SAME_ISOLATION_TARGET` is no longer gated by load-aware, and the
  extra same-isolation runner profile inherits the baseline selector. Target `2`
  in `results/browser-compare-20260608T032051/browser-compare.json` passed
  quality but made `0` top-ups, so it is not proof. Target `4` in
  `results/browser-compare-20260608T032422/browser-compare.json` passed quality,
  made `3` top-ups and `0` failures with `0` load-aware open picks, and cut
  same-window median load to `4646.399ms` versus baseline Arti `9463.184ms` and
  local C Tor `6524.087ms`. It also cut max Arti load to `4822.725ms` from
  `14876.409ms`. The low-log multi-target gate in
  `results/browser-compare-20260608T033012/browser-compare.json` then rejected
  both target `3` and target `4`: quality passed, load-aware stayed off, target
  `3` made `9` top-ups, target `4` made `12`, both had `0` failures, but both
  were slower than baseline Arti on check, homepage, and download medians.
  Target `4` also had a bad `51463.133ms` accepted homepage tail. Keep this
  capacity knob lab-only.
- Source now makes that lab knob stricter with
  `TORFAST_EXIT_SAME_ISOLATION_MIN_ASSIGNED_STREAMS`, default `2`, and the
  analyzer reports top-up selected-stream count plus top-up floor. The `min=2`
  gate in `results/browser-compare-20260608T034639/browser-compare.json` passed
  quality, kept load-aware off, and kept browser prefs unchanged. Target `3`
  made `8` top-ups and helped the download median (`3541.465ms` vs baseline
  `3992.234ms`), but it lost check/home and had a worse download max tail.
  Target `4` made `16` top-ups and still lost homepage/download. The `min=3`
  focused gate in `results/browser-compare-20260608T035149/browser-compare.json`
  passed quality but lost homepage and download. The lower target `2` gate in
  `results/browser-compare-20260608T035831/browser-compare.json` passed quality
  and made only `3` top-ups, but download median was much worse than baseline
  (`10049.471ms` vs `6199.955ms`). The analyzer now splits same-isolation
  top-up attempt runs from no-attempt runs; on this gate, download top-up
  attempts had median load `14997.160ms` vs paired baseline `14508.584ms`.
  Source now has that more selective signal as a lab-only option:
  `TORFAST_EXIT_SAME_ISOLATION_REQUIRE_BAD_HEALTH`. The first 3-target run,
  `results/browser-compare-20260608T041700/browser-compare.json`, is rejected as
  clean proof because baseline Arti hit a homepage `netTimeout`, although the
  health-gated sameiso2 profile itself finished `3/3` on all targets. The clean
  focused proof,
  `results/browser-compare-20260608T042223/browser-compare.json`, passed quality,
  kept browser prefs unchanged, made `1` bad-health-required top-up with `0`
  failures, and improved paired median load by `336.149ms` on check and
  `790.623ms` on download. The wider repeat,
  `results/browser-compare-20260608T042918/browser-compare.json`, also passed
  quality across check, homepage, and download with `5` interleaved runs, kept
  browser prefs unchanged, kept load-aware off, and made `7`
  bad-health-required top-ups with `0` failures. It beat baseline Arti summary
  medians on check and download, beat local C Tor summary medians on all three
  targets, and cut baseline Arti max-load tails on all three targets. Do not
  promote it yet: homepage summary median still lost to baseline Arti, homepage
  max load still lost to local C Tor, and this needs a larger repeated low-log
  gate. The independent repeat,
  `results/browser-compare-20260608T044143/browser-compare.json`, passed quality
  but rejected promotion: baseline Arti beat sameiso2 on all three summary
  medians, and sameiso2 had a bad accepted homepage max tail of `64615.774ms`.
  Keep health-gated sameiso2 lab-only. Next source work should explain or
  prevent the homepage top-up tail before another promotion gate. Source and the
  analyzer now expose selected-circuit top-up health detail fields so the next
  retained proof can say whether the bad tail came from stale, low-score, or
  high-gap health. The first retained diagnostic with those fields,
  `results/browser-compare-20260608T045852/browser-compare.json`, failed quality
  because baseline Arti hit a homepage `netTimeout`; the sameiso2 profile itself
  finished `8/8` and showed fresh but low-score selected top-up circuits (max
  gap `338ms`, min score `14869`, max age `37ms`). The existing combined lab
  profile (health-aware, avoid-bad-health, sameiso2, and bad-health-required
  top-up) then passed two focused homepage windows:
  `results/browser-compare-20260608T050606/browser-compare.json` and
  `results/browser-compare-20260608T051154/browser-compare.json`. It beat
  baseline Arti median load in both (`5531.888ms` vs `6743.920ms`, then
  `4929.467ms` vs `8090.484ms`) and kept browser prefs unchanged, but it remains
  one-target lab evidence. The broader check/homepage/download gate,
  `results/browser-compare-20260608T051703/browser-compare.json`, passed quality
  but rejected promotion: the profile still beat check and homepage medians, but
  download regressed badly (`13857.582ms` vs baseline Arti `5314.784ms`) and its
  max download tail was `66948.318ms` vs baseline `12564.660ms`. Download top-up
  attempt runs won `0/4` and lost by `+7549.335ms` median load. Keep it lab-only;
  next selector work must explain or prevent the download top-up tail before any
  new promotion gate. The focused download isolation,
  `results/browser-compare-20260608T052735/browser-compare.json`, also rejected
  health-aware avoid-bad-health without top-up (`6279.622ms` median load vs
  baseline Arti `4973.318ms`, with a `61523.104ms` max tail) and rejected
  sameiso2 harder (`13245.888ms` median load; top-up attempts won `0/3` and lost
  by `+9336.977ms`). Do not tune simple same-isolation counts or bad-health
  gates next; gather stronger relay/resource-tail evidence first. The focused
  debug replay, `results/browser-compare-20260608T053529/browser-compare.json`,
  passed quality but is diagnostic only. In that small window, health-aware
  avoid-bad-health without top-up beat baseline Arti (`4462.620ms` vs
  `5278.454ms` median load), while sameiso2 was slower (`5720.123ms`). Its only
  top-up-attempt run lost by `+3929.443ms`, while no-attempt sameiso2 runs were
  faster by `-1836.445ms`. Source and analyzer now add top-up lifecycle evidence:
  top-up `pending_id` plus build complete/failed/canceled counts. The next debug
  replay should use those fields to prove whether extra circuits arrive too late
  or just compete with the active page.
- The follow-up debug replay,
  `results/browser-compare-20260608T054800/browser-compare.json`, failed quality
  because baseline Arti and local C Tor each had a failed download run, so it is
  not speed proof. Sameiso2 itself finished `5/5` and made `3` top-ups with `0`
  failures. Lifecycle matching showed those top-ups built quickly (`540ms`,
  `538ms`, `462ms`), but only the run `5` top-up circuit was later used by page
  traffic. The analyzer now prints this as a
  `Torfast Same-Isolation Top-Up Lifecycle` table. The expanded table showed
  run `3` still had exit open picks after build, but skipped cold `Circ 1.6` for
  active `Circ 1.5` with stronger recent health (`185759` vs `0`); run `4` had
  no post-build exit open picks; run `5` selected and used its built top-up.
  Next work should explain when a cold built top-up becomes better than a hot
  active circuit, not only when it finishes building.
- Source now adds a default-off A/B candidate for that exact question:
  `TORFAST_EXIT_SELECT_PREFER_COLD_SAME_ISOLATION`. It only runs when
  same-isolation, load-aware, and health-aware lab modes are enabled, and it
  keeps the same circuit eligibility and isolation rules. The first focused
  download-page A/B,
  `results/browser-compare-20260608T061926/browser-compare.json`, passed quality
  and showed prefer-cold sameiso2 winning `3/3` paired loads against baseline
  Arti (`3488.752ms` vs `7508.323ms` median load), with a lower max tail too
  (`4946.213ms` vs `12413.143ms`). The wider same-window gate,
  `results/browser-compare-20260608T062521/browser-compare.json`, passed quality
  but rejected promotion: prefer-cold lost check and homepage and only barely
  improved the download summary median, while paired median deltas were worse
  on all three pages. Keep it lab-only. Next work should explain why top-up
  attempt rows can look okay while the full profile loses, instead of widening
  this selector again.
- The follow-up clean-profile gate,
  `results/browser-compare-20260608T063525/browser-compare.json`, tested
  prefer-cold without the avoid-bad-health guard. It passed quality but failed
  the speed question: download median load regressed to `12824.702ms` versus
  baseline Arti `6549.739ms`, with `0/3` paired wins. The guarded prefer-cold
  profile looked better in paired medians in that run, but had a bad accepted
  check tail (`24061.174ms` max load). Do not remove the guard; next work should
  investigate why guarded prefer-cold can produce a long check-page tail.
- The analyzer now has an `Arti Profile Promotion Risks` table that makes this
  tail rule explicit. A candidate is not promotable if any target is slower by
  paired median, slower by summary median, worse by max tail, or has low paired
  wins. Future speed work should clear this table on check, homepage, and
  download before calling a lab flag a real win.
- The matching `Arti Profile Promotion Risk Max Runs` table shows the guarded
  prefer-cold check tail in `063525` was nav connect/TLS (`20583.745ms`), not a
  resource fetch.
- The focused debug replay
  `results/browser-compare-20260608T065456/browser-compare.json` passed quality
  but did not repeat that `20s` connect/TLS stall. It still rejected guarded
  prefer-cold promotion: paired median was slower by `+499.573ms`, summary
  median was slower by `+20.120ms`, and paired wins were only `2/5`. The new
  `Arti Profile Promotion Risk SOCKS Context` table showed the max risk run had
  SOCKS connect/reply at `0ms`/`0ms`, first Tor byte at `293ms`, relay at
  `5394ms`, and max receive gap at `2901ms`. Next work should explain and
  reduce relay/response-to-DOM tails while keeping the earlier connect/TLS tail
  as a blocker until it is explained or prevented.
- A new default-off lab guard now targets one concrete bad selector shape:
  `TORFAST_EXIT_SELECT_AVOID_BAD_HEALTH_UNKNOWN_FALLBACK`. It only extends the
  existing load-aware bad-health guard. When the least-used eligible circuit is
  known bad and there is no clearly good alternative, it may use an unassigned
  cold/unknown eligible circuit instead of staying on the known-bad one. This
  keeps normal Tor behavior unchanged and does not relax path or isolation
  rules.
- `results/browser-compare-20260608T122133/browser-compare.json` ran that
  unknown-fallback profile against baseline Arti and the existing guarded
  prefer-cold profile. It passed quality and beat baseline Arti median load on
  all three targets, but reject promotion: local C Tor still beat it on download
  median load (`4737.364ms` vs `5581.750ms`), and the promotion-risk table
  showed much worse max tails on homepage (`61500.660ms` vs baseline
  `5954.526ms`) and download (`17385.026ms` vs baseline `5909.866ms`). Next work
  should explain or prevent the unknown-fallback relay-tail shape before trying
  a larger gate.
- `results/browser-compare-20260608T123655/browser-compare.json` reran after
  tightening unknown fallback to unassigned circuits only. It failed quality:
  unknown-fallback download run `2` timed out after `91876.956ms` with no
  screenshot proof. Failed-run SOCKS rows showed a hostname stream with relay
  `89332ms` and an onion stream with relay `83919ms`. Next work should not tune
  unknown fallback further until the 90s relay/connect timeout shape is
  explained or a quality-preserving retry/avoidance rule is proven separately.
- `results/browser-compare-20260608T124751/browser-compare.json` tested a
  focused download-page retry with global non-onion SOCKS soft timeout set to
  `5000ms`. It still failed quality: guarded prefer-cold download run `2`
  reached `about:neterror?e=netTimeout` after `61452.374ms`. The failure still
  had onion CONNECT and relay-after-reply tails, so soft timeout alone is not a
  promotion path.
- The analyzer cause summary now makes that explicit: `124751` is
  `mixed connect wait + relay-after-reply tail`, with `2` slow onion CONNECT
  streams, `3` relay-tail streams, and `0` soft timeouts. Next implementation
  work should target this mixed wait shape without weakening onion handling or
  browser isolation.
- The relay-tail split shows `2` partial-response idle stalls and `1` no-byte
  relay stall in that same failed run. A safe next design should first collect or
  prove per-stream stall context after SOCKS reply; closing or retrying these
  browser-visible streams blindly would be a quality regression.
- The relay-tail detail table now shows the partial-response stalls were not
  caused by large gaps between received relay DATA cells: timing ids `10` and
  `12` had max receive gaps `230ms` and `679ms`, then idled after last Tor byte
  for `59203ms` and `54141ms`. Next work should instrument post-last-byte stream
  close/error state before trying a behavior change.
- The source now has that post-last-byte instrumentation: SOCKS relay-finished
  logs include copy error kind/token, stream-reader terminal logs include
  circuit, stream, byte, cell, pending, and EOF context, and the analyzer parses
  them. SOCKS also emits bounded info-level slow/failure summaries, so low-log
  gates can keep cause rows without full debug logs. The `20260608T142558`
  low-log replay passed quality and proved those SOCKS rows are retained and
  parsed, but it is diagnostic proof only. The repeated wide gate
  `20260608T143029` passed quality but still rejected the hedge: download had a
  `66992.133ms` accepted max tail, now tied to a `60699ms` hostname CONNECT
  after one `5000ms` soft timeout. The new non-onion soft-timeout attempt-count
  knob is bounded and lab-only; the focused attempts-`3` replay `20260608T144556`
  passed quality but was slower, so do not promote it.
- The runner now supports same-window attempt-count A/B profiles. The focused
  attempts-`3` download A/B `20260608T145305` passed quality and won `3/3`
  paired loads with median load `3786.624ms` vs baseline Arti `11503.625ms`.
  Treat it as promising narrow proof only; rerun a wide gate before any default
  or promotion claim.
- The wider attempts-`3` gate `20260608T145856` passed quality and improved
  medians on all three targets, but it is rejected: check and homepage max
  tails were worse, and the homepage tail was a `60451ms` final CONNECT after
  two `5000ms` soft timeouts. The attempts-`4` homepage follow-up
  `20260608T150858` passed quality and lowered max tail, but it was slower by
  median and won only `1/5` paired loads. Do not promote attempt-count changes.
- The analyzer now prints SOCKS retry attempt caps and traces. On `145856`, the
  bad attempts-`3` rows show two short soft timeouts, then a normal final
  attempt waiting about `50s`. Next work should target why the final CONNECT
  can still choose or sit on a bad path, not just raise retry count.
- New exit-client phase timing splits tunnel acquisition from BEGIN completion.
  The proof run `20260608T152416` passed quality and showed a slow homepage
  load where tunnel acquisition was `4467ms`, BEGIN phase was only `1ms`, and
  SOCKS relay tails reached `38465ms`. Next candidate work should use relay
  health/transfer evidence, not CONNECT retry count.
- New low-log stream receiver terminal summaries are live. The proof run
  `20260608T153828` passed quality and captured `9` summaries with max transfer
  `3450ms`, max data gap `465ms`, and max idle after last data `3012ms`. This
  run did not reproduce the long relay stall, but it proves future info-level
  gates can explain slow resource transfer without full debug logging.
- The wider low-log proof `20260608T154415` passed quality and beat local C Tor
  by median load on check and homepage, but it also exposed an accepted
  `62261.348ms` check-page tail. The retained logs tied the bad tail to a
  `60042ms` exit tunnel-ready failure plus retry, while transfer summaries had
  max data gap `880ms`. Next work should target slow CONNECT/tunnel acquisition
  and keep transfer summaries as the check for post-data stalls.
- The first soft-timeout A/B `20260608T154736` is a harness caveat: the runner
  split `5000ms` and `3 attempts` into separate extra profiles. `soft5000ms`
  was rejected on speed, and `softattempts3` is not combined-profile proof.
- The runner now supports
  `--extra-arti-socks-connect-soft-timeout-combo MS:ATTEMPTS`. The corrected
  focused A/B `20260608T155501` passed quality and the `5000ms + 3 attempts`
  profile beat baseline Arti by `1539.870ms` paired median load on check, with
  lower max load. Treat it as narrow lab proof only; next proof should be a
  wider same-window gate across check, homepage, and download.
- The wider combined A/B `20260608T160018` passed browser quality but rejected
  promotion. The combo beat baseline Arti on check and homepage medians, but
  homepage max load got worse (`16848.073ms` vs `8021.455ms`) and download
  median load got slightly worse than baseline (`+138.804ms` paired median
  load, `1/3` paired wins). It still lost to local C Tor by median page load on
  check and download. Do not promote the combo profile.
- The analyzer now prints top stream receiver terminal summaries. In
  `20260608T160018`, the combo had terminal stream transfer up to `13404ms`,
  max data gap `4976ms`, and idle after last data up to `15808ms`. The worst
  rows map to homepage run `3` on circuits `3.15` and `3.16`, plus download run
  `3` on circuits `3.20` and `3.21`. Next work should explain those late
  resource/stream tails rather than tuning CONNECT attempts again.
- `20260608T162621` proves the retained low-log top-stream join is now useful:
  SOCKS `relay finished` rows include `circ_id` and `stream_id`, and the
  analyzer fills top-stream timing id, target kind, relay ms, SOCKS ok, and
  copy-error columns. The same run keeps the `5000ms + 3 attempts` combo
  rejected: homepage was slower than baseline by paired median load, and the
  download page had a `51860.171ms` accepted load with a `46796ms` CONNECT.
- `20260608T164228` proves the next diagnostic link is wired: exit-client slow
  tunnel rows can retain `tunnel_unique_id`, and tunnel builds older than
  `5000ms` now log complete/failed/canceled outcomes at info level. The proof
  passed quality and captured `10003..10004ms` build failures during bootstrap.
  It did not reproduce the earlier page-load CONNECT stall, so treat it as
  diagnostic proof only. The combo was faster in this tiny download-page window
  but still had only `1/2` paired wins, so keep `5000ms + 3 attempts` lab-only.
- `20260608T164626` is rejected as a promotion gate because overall browser
  quality failed. It still confirms the slow-tunnel diagnostics are useful:
  baseline Arti check run `3` hit a `60002ms` build failure, then a `120065ms`
  hostname CONNECT failure and two `85..90s` relay tails with only tiny reader
  output. Do not promote the combo from this run even though it passed all
  targets and beat baseline on homepage/download medians.
- The runner now also supports
  `--extra-arti-socks-connect-soft-timeout-pending-hedge-combo MS:ATTEMPTS:HEDGE_MS`,
  which starts one extra Arti profile with both the non-onion SOCKS
  soft-timeout combo and the exit pending hedge. Actual pending-hedge launch,
  failure, and timer-fire events are now info-level so low-log runs can prove
  whether the hedge path fired.
- `20260608T170429` passed quality on a narrow check-page `3`-run A/B. The
  `5000ms + 3 attempts + 1500ms hedge` profile beat baseline Arti by
  `-415.839ms` summary median load and `-388.630ms` paired median load, while
  soft-timeout-only was slower. This is harness proof only, not promotion proof.
- `20260608T171004` used the rebuilt binary on check plus download and failed
  overall quality because local C Tor check run `1` hit `nssFailure2`. All Arti
  profiles passed. The combined soft-timeout plus pending-hedge profile was
  flat on check (`-0.736ms` paired median, `1/2` wins, max tail `+16.169ms`)
  and faster on download (`-1508.440ms` paired median, `2/2` wins, max tail
  `-1755.690ms`). Soft-timeout-only was rejected again with a `41013ms`
  hostname CONNECT after two `5000ms` soft timeouts. No pending-hedge info lines
  appeared, so do not call this a hedge speed fix.
- Build-hedge timer-fire and launch rows are now low-log parseable, and the
  analyzer counts actual build hedges separately from normal builds. The
  focused download proof `20260608T172159` passed quality: baseline Arti median
  load was `4354.853ms`, soft-timeout-only was `4026.041ms`, combined
  soft-timeout plus `1500ms` hedge was `3986.091ms`, and local C Tor was
  `5223.020ms`. Both lab profiles still had worse max load than baseline, and
  no pending-hedge or build-hedge timer lines fired. Keep both lab-only; the
  next proof still needs a real slow-build hedge-fire event or a broader clean
  win with no max-tail regression.
- The analyzer now prints `Browser Run Late Phase Queue Context`. The focused
  debug replay `20260608T173542` passed quality but rejected any speed claim:
  Arti load was `+1500.055ms` slower than local C Tor. It reached first
  response `83.335ms` earlier, then lost `+3083.395ms` in response-to-DOM.
  The new row links the Arti queue loss to timing ids `4` and `7` on
  `Circ 4.0 (Tunnel 5)` with a `3466.736ms` max queued resource. Treat this as
  source-target evidence: explain or reduce late page construction/resource
  queue delay under unchanged browser caps and Tor path rules.
- The analyzer now prints `Arti Profile Late Queue A/B`. It keeps extra Arti
  profile claims tied to the late queue bottleneck instead of only page-load
  medians. On `20260608T174515`, `healthaware_spread4` cut median max queue
  delay by `-4950.099ms` versus base Arti, but only won `1/2` paired queue
  runs, so it remains lab-only.
- The stricter spread `4` debug lab proof `20260608T174012` passed quality but
  is rejected: the spread profile lost to base Arti by `+1932.340ms` paired
  median load, won `0/2`, and had a `+2157.597ms` worse max tail. It selected
  some low-rate/slow-relay circuits, so assignment pressure alone is not a safe
  next promotion path.
- The runner now supports
  `--extra-arti-exit-select-health-aware-min-assignment-spread`, named
  `arti_release_browser_healthaware_spreadN`. The focused download proof
  `20260608T174515` passed quality and cut median page load versus base Arti,
  but it won only `1/2` direct A/B pairs. Keep this combined profile lab-only.
- The wider `20260608T175759` gate rejects `healthaware_spread4` as a promotion
  path. It passed quality, but max tails worsened on check, homepage, and
  download. Homepage was the clearest loss: `+8208.762ms` paired median load,
  `0/3` paired wins, and `+6566.798ms` median max queue delay.
- The analyzer now prints `Arti Profile Promotion Risk Stream Receiver
  Context`. On `20260608T175759`, the rejected `healthaware_spread4` risk rows
  tie to `not_connected` stream receiver endings with long idle-after-last-data
  windows: `32620ms` on check, `12595ms` on homepage, and `51028ms` on
  download. The next source work should target slow stream endings or tunnel
  acquisition tails, not another spread selector.
- The analyzer now also prints `Torfast Stream Receiver Not-Connected Summary`.
  It shows this tail class also exists in base Arti: download run `3` had `8`
  not-connected streams and `35403ms` max idle after last data. Work on this as
  a general tail problem, not a `healthaware_spread4`-only issue.
- Local Arti now has default-off low-log SOCKS relay byte timing behind
  `TORFAST_SOCKS_RELAY_BYTE_TIMING`, with runner flag
  `--arti-socks-relay-byte-timing`. The focused proof `20260608T182354` passed
  quality and showed the fields at info level. It was not a speed win: Arti
  load was `5673.865ms` versus local C Tor `4003.608ms`. It did prove the next
  source target more clearly: timing id `1` had last Tor-to-browser byte at
  `1318ms` but relay finish at `6123ms` (`4805ms` idle), while timing id `2`
  moved `362459` Tor-to-browser bytes and still ended `not_connected`.
  Inspect close/EOF handling and browser slot release around slow stream tails.
- Follow-up proof `20260608T183445` passed quality and was a one-run diagnostic
  speed win only: Arti load was `2864.382ms` versus local C Tor `5099.072ms`.
  It did not prove the browser EOF guess. Logged `not_connected` streams had no
  recorded browser EOF or Tor read-error timestamp, while Tor-writer close
  landed at relay finish. Add tighter close/error proof before behavior changes.
- The `183445` missing EOF/error fields were a diagnostic blind spot, not proof
  against browser EOF. `CountingBufStream::poll_fill_buf` now records EOF/error
  timing. Proof `20260608T184334` passed quality and showed `10` close streams,
  `9` `not_connected`, and all `9` had browser EOF plus Tor read error at the
  same close moment. Treat that class as local close-after-browser-done evidence
  and focus next on real resource queue, boot, and transfer tails.
- The analyzer now maps browser resources to SOCKS streams even in low-log runs
  without debug relay-cell lines. Re-analyzing `20260608T184334` mapped `36`
  resources, including `17` high-confidence matches. The next concrete
  bottleneck is the queued-resource shape: timing id `9` had `4` resources
  queued at least `1000ms`, and timing id `10` carried `tor-logo@2x.png` after
  `5600.112ms` fetch-to-request delay.
- The new `Resource Queue Slot Release Summary` makes that queue shape easier
  to read. In `20260608T184334`, Arti had `23` queued resources at least
  `1000ms`, `16` at slot depth `>=6`, `23` rows with joined blocker evidence,
  and `13` high-confidence blocker rows. Of those queued rows, `15` were
  receive-dominant, `8` wait-dominant, and `9` high-confidence rows still had
  blocker writes at least `1000ms` after the queued request started. Next work
  should explain which late stream-transfer path keeps those slot holders open.
- `Resource Queue Late Write Summary` now says this is not mainly browser
  holding slots after Arti wrote the bytes. In `20260608T184334`, only `2` rows
  had positive browser release after final matched Arti write, and none were at
  least `500ms`; the max write-after-queue was `4978.163ms`. Stream receiver
  terminal summaries covered all `13` high-confidence queued rows and showed
  median write-after-terminal-data `0ms`, max terminal pending bytes `0`, and
  max terminal data gap `1097ms`. Next work should inspect why stream receiver
  data arrives late on those slot-holding streams.
- `Resource Queue Late Stream Detail` now points to the concrete blockers:
  `fallback.js` waited on terminal last data `4979.163ms` after queue start with
  timing ids `8, 4`, while `stay-safe@3x.png` and `TBA10.0.png` waited
  `4595.822ms` with timing ids `4, 8`; all were on `Circ 4.1`. Next source work
  should inspect same-circuit late stream data gaps for timing ids `4`, `8`,
  and `9`.
- `Resource Queue Late Circuit Summary` now shows all `13` late queued rows were
  on `Circ 4.1`, which carried `7` terminal streams, `1178.332 KiB`, `2505`
  data cells, max terminal transfer `6499ms`, and max terminal data gap
  `1196ms`. Next source work should focus on same-circuit stream fairness or
  circuit assignment for parallel browser fetches.
- The latest static Arti quality check is
  `results/arti-quality-config-20260608T185645/arti-quality-config.json` with
  `34` passing checks, including normal-selector candidate-context logging, the
  bounded same-isolation top-up rule, the default-off health-aware lab selector
  with stale-score, absolute-score, and 2x-improvement guards, and the
  default-off unassigned-only unknown-health fallback guard, plus the
  bounded bad-health hedge, low-log SOCKS slow/failure summaries, the bounded
  non-onion soft-timeout attempt knob, default-off low-log SOCKS byte timing,
  low-log relay-finished stream keys,
  low-log slow tunnel build outcomes, low-log pending-hedge actual events,
  low-log build-hedge actual events, and post-last-byte plus close/error
  diagnostic parser guard.
- The generic stream-reactor congestion gate has now been probed once on the
  homepage and did not fire. Keep it as a diagnostic, but focus the next proof
  on relay/resource tails and circuit assignment shape.
- Keep load-aware open-circuit choice lab-only for now. The wider 5-run,
  3-target gate improved median load, but one download-page run had a
  `65953.543ms` tail. The latest broader normal gate also failed quality and
  showed a `52751.055ms` browser CONNECT tail. The latest focused replay passed
  quality but load-aware was slower than base Arti by `1904.365ms` median load.
  The spread `2` guardrail also passed quality but was slower than base Arti by
  `735.496ms` median load. The latest health-signal proof passed quality and was
  faster in a narrow 2-run debug window, but it is not enough to promote
  load-aware selection. The new health-aware selector beat plain load-aware in a
  broader debug gate and was near local C Tor, but the larger low-log gate
  failed quality on health-aware download and had a slow accepted download
  median. The focused retained-runner checks are mixed for health-aware and
  still keep it lab-only. Plain load-aware won one focused window, but the
  latest debug retained-tail check rejected both selector profiles again. The
  lower health move threshold avoids some zero-score cold picks but still does
  not prevent slow relay tails. The first bad-health guard shape has now been
  rejected by a repeated same-window gate. The tightened guard passed a repeated
  debug gate, but the low-log 3-target gate found bad accepted-run tails, so it
  is not default-ready. The guarded same-isolation target `2` combination was
  also slower, so do not use it as the next fix. Guarded minimum assignment
  spread `2` was also slower and had a worse tail, so do not use it as the next
  fix either. The failed-quality threshold check rejects `32768` and does not
  prove `131072`, so threshold tuning is not the next promotion path. The
  failed-run SOCKS table ties the latest timeout to ~60s relay waits, so focus
  on explaining or reducing those waits without lowering Tor path quality.
  The latest retained-log proof says not to patch hostname CONNECT next.
  Pressure-gated same-isolation target
  `3` is the best safe capacity proof so far, but it failed the stronger
  low-log quality gate. Targets `2` and `3` both passed smaller low-log
  download-page checks but were slower. Do not share across incompatible
  isolation groups. The fixed bad-health hedge beat baseline in one focused
  homepage replay, but the wider 3-target gate failed quality on check and kept
  a huge accepted homepage tail, so keep that hedge lab-only too. The browser
  pref audit says not to change Tor Browser connection caps for speed.
- The rebuilt low-log stream-terminal proof
  `results/browser-compare-20260608T193519/browser-compare.json` failed quality
  on the download page. It is useful failure proof, not speed proof: Arti got
  partial Tor bytes on 3 streams, then idled until browser timeout. The new
  receive-window counters do not show SENDME/window pressure for this failure
  shape (`sendmes=0`, min receive window at least `479`, max queued bytes
  `2998`). The next source step should inspect partial-response idle tails,
  stream close/circuit health, and relay-tail handling before another selector
  or timeout promotion gate.
- Do not treat the byte tap as a speed proof unless all targets pass quality.
  The latest tap run failed reliability on Arti.
- Do not retry `min_exit_circs_for_port = 3` without a better reliability
  reason. The first source-patch proof failed quality, and the runner-only lab
  flag passed quality but made the homepage much slower.
- The focused combined `5000ms + 3 attempts` soft-timeout profile is rejected
  for promotion by the wider gate. Keep it lab-only unless a later source
  change removes the homepage/download tail risks.
- The new `4000ms` partial-response idle close lab passed a focused
  download-page quality proof and fired once, but it was not a speed win:
  Arti load was `10177.693ms` versus local C Tor `4631.612ms`. Keep it
  lab-only. The next source work should explain the remaining `8s` to `10s`
  resource-stream endings and HTTP/1.1 browser queue delay, not promote early
  close.
- The circuit congestion diagnostic proof
  `results/browser-compare-20260608T200133/browser-compare.json` passed quality
  but was still slower than local C Tor. Its retained tail showed `29` circuit
  SENDME-sent events on `Circ 3.3`, `0` scheduler blocks, and `0`
  `can_send=false` rows. The low-log circuit-quality fallback shows the same
  circuit carried `1412598` bytes at about `166.424 KiB/s`, with max relay time
  `8780ms`. Do not chase circuit send-window blocking for this shape. Next,
  inspect late relay/circuit data arrival or circuit quality.
- The low-log selector-context proof
  `results/browser-compare-20260608T202100/browser-compare.json` passed quality
  and was a narrow speed win: Arti load `3878.303ms` versus local C Tor
  `4110.630ms`. The selected late-resource circuit had no better-health
  alternative in the retained context, and circuit congestion still showed `0`
  scheduler blocks and `0` `can_send=false` rows. Keep
  `TORFAST_EXIT_SELECT_LOW_LOG_CONTEXT` diagnostic-only. Next work should stay
  on HTTP/1.1 resource queueing and late relay data arrival, not selector
  promotion.
- The separate FlowCtrl build proof
  `results/browser-compare-20260608T204136/browser-compare.json` passed quality
  and proved the FlowCtrl binary can use Vegas (`vegas:95`), but it was slower
  than normal Arti by `668.958ms` page load and much slower by boot+load.
  Do not promote FlowCtrl from this proof. Keep it as a separate A/B lane.
- The rebuilt normal 3-target gate
  `results/browser-compare-20260608T204644/browser-compare.json` is not an
  accepted speed proof because local C Tor timed out once, but it shows normal
  Arti passed all `9/9` page loads. Arti won page-only on the small check page
  and lost page-only on the two larger pages, while winning boot+load on all
  three targets. The final goal is still not stable.
- The focused byte-timing diagnostic
  `results/browser-compare-20260608T205102/browser-compare.json` passed quality
  and had Arti page-only wins on both larger pages, but local C Tor had a huge
  homepage tail. Use it as bottleneck evidence, not final proof. The useful
  clue is still late HTTP/1.1 queue release on selected circuits, with no
  receive-window/SENDME starvation evidence.
- The clean 3-target gate
  `results/browser-compare-20260608T205724/browser-compare.json` passed quality
  but rejected a speed claim: Arti lost page-only median load on check and the
  homepage, while winning the download page. The bad homepage tail again pointed
  at HTTP/1.1 queueing plus slow relay data on one chosen circuit.
- The same-window load-aware A/B
  `results/browser-compare-20260608T210112/browser-compare.json` passed quality
  but did not promote load-aware selection. It was slower by summary median load
  on all three targets, though it removed the base Arti `65s` download max tail.
  Keep it as tail-control evidence only.
- The focused soft5000 A/B
  `results/browser-compare-20260608T210541/browser-compare.json` passed quality
  and beat base Arti on the download page, but it counted `0` soft timeouts.
  Keep the soft-timeout path lab-only until timeout firings are proved to help
  without browser failures.
- Circuit congestion SENDME/scheduler info logs are now default-off behind
  `TORFAST_CIRCUIT_CONGESTION_LOG=1`. This does not change Tor behavior; it
  removes diagnostic overhead from normal info-level speed gates. Static proof
  `results/arti-quality-config-20260608T211029/arti-quality-config.json` passed
  `36` checks, `cargo check -p tor-proto -p arti --locked` passed, and the
  release binary rebuilt. Normal proof
  `results/browser-compare-20260608T211244/browser-compare.json` passed quality
  with no circuit congestion rows; diagnostic proof
  `results/browser-compare-20260608T211322/browser-compare.json` passed quality
  and showed the rows when byte timing enabled the env var.
- The clean 3-target gate
  `results/browser-compare-20260608T211630/browser-compare.json` passed quality
  and had Arti page-only median wins on all three targets, but cold boot made
  boot+load lose badly. The analyzer boot summary counted Arti directory
  failures/timeouts/NOTDIRECTORY/partial-response rows during boot. Treat cold
  directory/bootstrap reliability as the main blocker before claiming final
  speed.
- The warm-cache run
  `results/browser-compare-20260608T212524/browser-compare.json` passed quality
  and showed Arti cache boot is fast (`0.403s` versus local C Tor `2.751s`), but
  page-only medians were mixed: Arti won check and lost the two larger pages.
  Use this as separation proof, not final speed proof.
- The small cold repeat
  `results/browser-compare-20260608T213014/browser-compare.json` passed quality
  and did not repeat the 30s boot failure: Arti boot was `12.428s` versus local
  C Tor `14.026s`, and Arti won check-page load. This means the cold boot loss
  is transient, so any directory/bootstrap change needs repeat proof before
  promotion.
- The repeated boot-only proof
  `results/boot-compare-20260608T133540/boot-compare.json` showed the cold
  directory problem is repeatable: default Arti median boot was `19.966s`
  versus local C Tor `14.591s`, with Arti directory failure signals in `2/3`
  boots and none for local C Tor.
- The same-window dir-spread A/B
  `results/boot-compare-20260608T134519/boot-compare.json` rejected
  `TORFAST_DIR_SELECT_SPREAD=1` as a speed change. It removed directory failure
  signals in that window but made median Arti boot slower (`16.648s` versus
  default Arti `12.153s`). Static proof
  `results/arti-quality-config-20260608T220328/arti-quality-config.json` passed
  `38` checks. Keep dir-spread lab-only and do not promote it.
- Incremental microdescriptor bootstrap is implemented behind
  `TORFAST_DIR_INCREMENTAL_MICRODESCS=1`. It applies microdescriptor responses
  as they arrive and can mark the directory usable before every parallel fetch
  completes. The first 3-run proof
  `results/boot-compare-20260608T135535/boot-compare.json` was promising by
  median but had a worse max boot. The wider 5-run proof
  `results/boot-compare-20260608T140019/boot-compare.json` rejected promotion:
  default Arti median boot was `13.282s`, incremental was `15.525s`. Keep it
  lab-only.
- Directory read-timeout testing is implemented behind
  `TORFAST_DIRCLIENT_READ_TIMEOUT_MS`. The normal Arti timeout stays `10s` when
  unset, and lab values are bounded from `2000ms` through `10000ms`. Static
  proof `results/arti-quality-config-20260608T223350/arti-quality-config.json`
  passed `39` checks. The 5-run `5000ms` proof
  `results/boot-compare-20260608T141134/boot-compare.json` was too aggressive
  because it raised timeout counts. The 5-run `8000ms` proof
  `results/boot-compare-20260608T141435/boot-compare.json` is the current
  lab-only boot candidate: median boot improved from `26.023s` to `11.167s`,
  max boot improved from `28.018s` to `18.090s`, and the `8000ms` profile had
  `0` directory timeout signals. The first browser gate
  `results/browser-compare-20260608T222249/browser-compare.json` passed quality
  but rejected promotion: `8000ms` boot was `44.296s` with directory timeout
  signals, versus default Arti `18.452s` and local C Tor `13.573s`. Keep this
  timeout override as lab diagnostic only, not a speed path.
- Boot diagnostics now save a directory timeline in
  `tools/run_boot_compare.py`, and browser analysis prints the same timeline.
  Directory client request timing rows are default-off behind
  `TORFAST_DIRCLIENT_TIMING_LOG=1`; static proof
  `results/arti-quality-config-20260608T223906/arti-quality-config.json` passed
  `40` checks.
  The rejected `8000ms` browser gate shows the bad shape clearly: first timeout
  at `9.000s`, retry, microdescriptors at `19.000s`, usable directory at
  `44.000s`. The fresh boot-only proof
  `results/boot-compare-20260608T143102/boot-compare.json` shows the good shape:
  default Arti median boot `10.548s`, local C Tor `11.758s`, no directory
  failures in `5/5` runs, median microdescriptor phase at `3.000s`, and median
  usable directory at `11.000s`. Next source work should target the bad
  retry/timeout path without slowing the good one.
- `results/boot-compare-20260608T144325/boot-compare.json` caught the bad path
  with timing rows. Arti succeeded `10/10`, but `3/10` runs had directory
  signals and max boot was `38.568s`. Consensus was not the bottleneck:
  consensus max was `2956ms`. The tail was large microdescriptor downloads:
  microdescriptor p90-ish was `6284ms`, max was `11013ms`, and timeout rows were
  microdescriptor partial responses.
- `results/boot-compare-20260608T144641/boot-compare.json` rejects incremental
  microdescriptor promotion again. It reduced max boot but made median boot
  worse (`15.054s` versus default `12.947s`) and had more timeouts (`9` versus
  `5`). Next source idea should reduce large microdescriptor tail waits without
  making the normal median path slower.
- `TORFAST_DIR_MICRODESC_IDS_PER_REQUEST` is now available as a bounded
  default-off lab diagnostic. Static proof
  `results/arti-quality-config-20260608T225832/arti-quality-config.json` passed
  `41` checks. The 10-run `250` chunk A/B
  `results/boot-compare-20260608T150048/boot-compare.json` rejects smaller
  chunks: median boot was `19.292s` versus default `14.849s`. The 10-run `375`
  chunk A/B `results/boot-compare-20260608T150541/boot-compare.json` also
  rejects it: `14.631s` versus default `13.057s`. Smaller chunks reduced
  per-request microdescriptor body size but added too many requests.
- Higher microdescriptor download parallelism is also rejected by
  `results/boot-compare-20260608T151034/boot-compare.json`. Default
  parallelism `4` had median boot `13.322s`; parallelism `6` had `17.229s`;
  parallelism `8` had `15.482s` and more directory failures. Do not increase
  simultaneous directory requests as the next source path.
- `TORFAST_DIR_MICRODESC_HEDGE_MS` is now available as a bounded default-off
  lab diagnostic for starting backup microdescriptor requests after a slow
  tail delay. Static proof
  `results/arti-quality-config-20260608T232103/arti-quality-config.json` passed
  `42` checks. The 10-run A/B
  `results/boot-compare-20260608T152310/boot-compare.json` rejects `7000ms` and
  `8000ms`: default median boot was `11.055s`, hedge `7000ms` was `15.040s`,
  and hedge `8000ms` was `21.303s`. Do not add more backup directory requests
  as the next source path.
- Same-window local SOCKS buffer A/B is now available in
  `tools/run_browser_compare.py` with `--extra-arti-proxy-buffer-size`. The
  warm-cache proof `results/browser-compare-20260608T233309/browser-compare.json`
  passed quality, but rejects `1 MB` as a default: it helped the homepage
  (`4494.622ms` versus default `5004.984ms`) but hurt the small check page
  (`1319.338ms` versus default `1133.558ms`) and was flagged as a promotion
  risk.
- The smaller-buffer follow-up
  `results/browser-compare-20260608T233953/browser-compare.json` also passed
  quality but rejects `256 KB` and `512 KB`. `256 KB` was much slower on both
  targets. `512 KB` helped check-page summary median but lost homepage median
  and had low paired wins. Do not tune local SOCKS buffer size as the next
  default speed path.
- The clean cold default gate
  `results/browser-compare-20260608T234644/browser-compare.json` passed quality.
  Arti boot was faster than local C Tor (`9.378s` versus `10.608s`), so this
  window is not a boot loss. Arti still lost page-only load on both targets and
  had `0/3` paired load wins on each target. The remaining gap is first
  response plus homepage resource-tail behavior.
- The focused byte-tap homepage diagnostic
  `results/browser-compare-20260608T235050/browser-compare.json` passed quality
  and narrowed the homepage loss to late resource delivery on a few Arti
  circuits, not local SOCKS buffering. The main page response was close, but
  Arti DOM-to-load was much worse.
- The focused clean load-aware homepage A/B
  `results/browser-compare-20260608T235305/browser-compare.json` passed quality
  and is promising for page load: load-aware Arti median load was `3701.049ms`
  versus default Arti `7036.249ms` and local C Tor `6118.898ms`, with `3/3`
  paired page-load wins. Keep it lab-only because this was one homepage gate
  and the load-aware profile had cold directory timeout signals during boot.
- The wider clean 3-target gate
  `results/browser-compare-20260608T235720/browser-compare.json` passed quality
  and rejects load-aware promotion. Default Arti beat local C Tor on all three
  page-load medians and booted cleanly in `7.394s`, but load-aware lost to
  default Arti on the homepage and download page, booted in `34.334s`, and had
  directory timeout signals plus large page tails. The next proof should repeat
  default Arti versus local C Tor for stability, not promote load-aware.
- The repeat default-only gate
  `results/browser-compare-20260609T000427/browser-compare.json` passed quality
  and partly repeated the default Arti page-load win: Arti beat local C Tor on
  homepage and download medians, but lost the small check page narrowly. Arti
  boot was slow (`25.279s` versus local C Tor `13.875s`), so final work is
  cold directory/bootstrap stability plus small-page consistency.
- `TORFAST_DIRCLIENT_PROGRESS_READ_TIMEOUT_MS` is now available as a bounded
  default-off lab diagnostic, but the 5-run proof
  `results/boot-compare-20260608T161854/boot-compare.json` rejects
  `2000ms` for speed: default median boot was `12.603s`, progress-read median
  boot was `16.225s`, and the progress profile had a `41.890s` max boot. Do
  not use progress-only body timeout as the next source path.
- `TORFAST_DIR_MICRODESC_EARLY_USABLE_NOTIFY=1` is now available as a
  default-off lab diagnostic. The 5-run boot proof
  `results/boot-compare-20260608T163146/boot-compare.json` was promising
  (`10.598s` median versus default `18.782s`), but the 3-target browser gate
  `results/browser-compare-20260609T003557/browser-compare.json` passed quality
  and rejected promotion: default Arti booted faster in that window and
  early-usable lost all page-load medians to default. Keep it lab-only.
- The repeat health-aware 3-target browser gate
  `results/browser-compare-20260609T004224/browser-compare.json` passed quality
  and improved page-only medians versus default Arti on all three targets, but
  it booted slower (`19.693s` versus `10.740s`) with directory timeout signals.
  Keep health-aware and plain load-aware lab-only; the next source work needs a
  boot-stable rule that cuts relay/page tails without making launch-to-load
  worse.
- `TORFAST_DIR_MICRODESC_RETRY_IDS_PER_REQUEST` is now available as a
  default-off lab diagnostic. It keeps first-attempt microdescriptor grouping at
  normal Arti defaults and only changes grouping after a prior download/add
  error when the current missing set is all microdescriptors. Static proof
  `results/arti-quality-config-20260609T012503/arti-quality-config.json` passed
  `45` checks. The broad `250` boot gate
  `results/boot-compare-20260608T170538/boot-compare.json` is rejected
  (`23.181s` median versus default `13.401s`). The broad `375` boot gate
  `results/boot-compare-20260608T170746/boot-compare.json` was promising
  (`8.798s` median versus default `20.662s`, with timeout rows `17` to `0`),
  but browser proof is mixed. The repeat browser gate
  `results/browser-compare-20260609T011415/browser-compare.json` passed quality
  and improved homepage/download medians, but lost boot, lost the check-page
  median, and had a worse homepage max tail. The signal-gated boot gate
  `results/boot-compare-20260608T172658/boot-compare.json` improved median a
  little (`7.967s` versus default `8.214s`) and max boot a lot (`9.890s`
  versus `29.484s`), but the browser gate
  `results/browser-compare-20260609T012818/browser-compare.json` passed quality
  with mixed speed: homepage/download medians improved, while boot and
  check-page median got worse. Keep it lab-only.
- The clean current-state gate
  `results/browser-compare-20260609T013711/browser-compare.json` failed quality
  and showed the next failure class: after SOCKS reply, some streams had no
  Tor-to-browser bytes for about `115s` to `120s`. A new bounded, default-off
  diagnostic, `TORFAST_SOCKS_NO_TOR_BYTE_RELAY_TIMEOUT_MS`, can close only
  non-onion no-byte relay stalls after the browser has sent bytes. Static proof
  `results/arti-quality-config-20260609T014903/arti-quality-config.json` passed
  `46` checks, and the focused/wider browser A/B gates
  `results/browser-compare-20260609T015102/browser-compare.json` and
  `results/browser-compare-20260609T015405/browser-compare.json` passed
  quality. Keep it lab-only because no timeout event fired in those clean runs
  and the wider gate still had one homepage max-tail risk.
- Same-window partial-idle A/B profiles are now available with
  `--extra-arti-socks-partial-relay-idle-timeout-ms`, and partial-idle now skips
  onion streams. Static proof
  `results/arti-quality-config-20260609T021714/arti-quality-config.json` passed
  `46` checks. The focused homepage gate
  `results/browser-compare-20260609T020444/browser-compare.json` passed quality
  and showed partial-idle can fire on hostname streams while the page still
  completes, but the wider gate
  `results/browser-compare-20260609T021003/browser-compare.json` failed quality.
  The tightened no-byte plus partial-idle combo gate
  `results/browser-compare-20260609T021908/browser-compare.json` passed quality
  but is rejected because the download median exploded to `68449.375ms`. Keep
  partial-idle diagnostic-only; do not promote it.
- `tools/analyze_browser_compare.py` now prints `Arti Promotion Blocker
  Summary`. On the latest combo gate
  `results/browser-compare-20260609T021908/browser-compare.json`, both Arti
  profiles still have boot directory trouble, all `3` targets slower than local
  C Tor, resource queue tails, slow onion/data-gap streams, and slow hostname
  streams. Treat the next speed lane as stream-gap proof first; do not add
  another idle timeout without evidence.
- The neutral stream-gap proof
  `results/browser-compare-20260609T023626/browser-compare.json` reproduced
  the bad shape: a homepage timeout with `13` hostname relay tails and `1`
  onion relay tail, including many no-Tor-byte hostname stalls around `57s` to
  `59s` and an onion partial-data idle around `55s`. The follow-up no-byte
  homepage A/B `results/browser-compare-20260609T024437/browser-compare.json`
  passed quality and improved page-only load (`3540.493ms` versus default
  `6767.394ms`), but boot+load was worse and no no-byte timeout event fired.
  Keep no-byte lab-only. Next source work should explain why hostname streams
  sit with no Tor bytes and why onion streams idle after partial data.
- Stream lifecycle proof is now instrumented behind
  `TORFAST_STREAM_LIFECYCLE_LOG=1` and the browser runner enables it with
  `--arti-socks-relay-byte-timing`. Static proof
  `results/arti-quality-config-20260609T025559/arti-quality-config.json` passed
  `46` checks, Python unit tests passed, and `cargo check -p tor-proto --locked`
  passed. Next run: rerun the neutral stream-gap proof and compare lifecycle
  `sent`/`delivered`/`stream_gone` rows against SOCKS relay-tail rows.
- The lifecycle rerun
  `results/browser-compare-20260609T030206/browser-compare.json` failed quality
  and gave the split we needed. The failed homepage run had timing id `30`
  as hostname `BEGIN sent, no CONNECTED` with no Tor bytes and relay `62857ms`,
  plus timing id `31` as onion `DATA delivered, no EOF` with `3514` Tor bytes
  and `57895ms` idle. There were no `stream_gone` or `queue_full` rows. Next
  source work should target exit/stream completion or relay-side progress after
  BEGIN/DATA, not the local stream delivery queue.
- The no-byte A/B
  `results/browser-compare-20260609T031233/browser-compare.json` passed quality
  but is still rejected. No no-byte timeout event fired, the homepage median
  got worse (`4115.376ms` versus default Arti `3823.454ms`), and max tails got
  worse on both targets. Keep no-byte lab-only; it is proof of the shape, not a
  promotable speed fix.
- The queue-proof rerun
  `results/browser-compare-20260609T032922/browser-compare.json` passed quality
  with outbound `channel_queued` lifecycle rows enabled. It captured `134`
  channel-queued rows and still had `0` `stream_gone`, `0` `queue_full`, max
  circuit-sender queue after send `0`. The channel queue count was not
  available in the normal release feature set, so this proves no local
  circuit-sender backlog in that clean window but not an empty channel reactor
  queue. Next source work should follow stream/exit progress after cells leave
  the local client path.
- The direct release-Arti channel-flush smoke proof
  `results/arti-channel-flush-smoke-20260608T195800/arti.log` fetched
  `https://www.torproject.org/` through Arti SOCKS with HTTP `200` and matched
  `915/915` stream `channel_queued` rows to channel reactor flush rows by
  `channel_circ_id` with median `1ms`, max `2ms`, unmatched `0`. That points
  away from circuit-to-channel-output delay. In the same smoke log, `23/24`
  queued BEGIN streams reached CONNECTED with median `152ms`, max `188ms`, and
  `23/24` queued DATA streams got DATA back with median `199ms`, max `547ms`.
  Next source work should focus on full-browser resource queueing and the
  post-output path: TLS/kernel, relay, exit, or remote response/EOF timing.
- The new `Notable Torfast SOCKS Stream Lifecycle` table on
  `results/browser-compare-20260609T032922/browser-compare.json` found `25`
  notable slow Arti streams. `16` already had DATA delivered, and the worst row
  was a hostname partial-response idle tail: timing id `29`, relay `34436ms`,
  `7785` Tor bytes, `33129ms` idle after last Tor byte. This keeps the next
  safe target on partial-response idle/EOF/resource-tail behavior, not local
  circuit or channel queues.
- The partial-idle follow-ups split signal from proof. In
  `results/browser-compare-20260609T041850/browser-compare.json`, a `4000ms`
  profile passed quality and was faster, but no timeout fired. In
  `results/browser-compare-20260609T042353/browser-compare.json`, `2000ms` and
  `3000ms` profiles passed quality and each fired `2` partial-idle timeouts;
  `3000ms` cut max idle after last Tor byte from `21872ms` to `3178ms` and won
  `2/3` paired loads versus local C Tor. Keep this lab-only. The next source
  target is selective close/EOF handling for browser-abandoned resource tails,
  not a broad timeout default.
- The new partial-idle resource-context table on
  `results/browser-compare-20260609T042353/browser-compare.json` found `0`
  exact browser-resource matches for the four timeout streams. Nearest resource
  context split `2` `after_response` and `2` `receiving`. The stricter
  active-at-timeout count found `14`, `8`, `14`, and `5` active browser
  resources at those close moments, with waiting resources in all four rows and
  receiving resources in three rows. This blocks a blind early-close default.
  The promotion blocker and risk tables now also mark these profiles with
  `partial idle active resources`, `2` active closes, max active resources
  `14`, and next proof `client-abandon proof`. The partial-idle resource
  context now also prints active-resource samples and max time left after the
  close; the latest run still had resources with up to about `1059ms` left.
  The Arti lab timeout event now logs client EOF/error and Tor-to-browser write
  error/close-error fields at the timeout moment, so the next replay can prove
  `client abandon at timeout` as `yes` or `no` instead of inferring from final
  relay state. Static guard
  `results/arti-quality-config-20260609T045234/arti-quality-config.json`
  passed `47` checks and requires those fields.
  Rebuilt-Arti replay
  `results/browser-compare-20260609T045506/browser-compare.json` failed quality
  because local C Tor had a `120s` browser timeout, but it proved the new field:
  both `2000ms` partial-idle closes had `client abandon at timeout = no`, client
  EOF at timeout `0`, and active browser resources still present (`12` and
  `19`). The promotion tables now block this as `partial idle no client abandon`
  plus `partial idle active resources`. They also mark this replay `baseline
  failed` with `baseline failures = 2` and next proof `clean baseline proof`,
  so fast deltas from a failed local C Tor baseline cannot be promoted.
  Next source work needs a stronger client-abandoned signal or a narrower rule
  than "partial idle for N ms".
- Clean follow-up
  `results/browser-compare-20260609T050615/browser-compare.json` passed quality:
  release Arti median load `6115.255ms`, local C Tor `8221.188ms`, paired load
  delta `-2105.933ms`. The analyzer now adds same-close proof to the promotion
  summary. It found `8` slow streams in the same-close not-connected shape, and
  `Torfast SOCKS Close Shape` showed `15/15` not-connected closes with client
  EOF plus Tor read error at the same moment. After splitting same-close rows
  and client-reset-plus-END rows from unresolved rows, slow unresolved streams
  are `0`, slow hostname clears, and slow onion/data gap clears for this run.
  Resource queue also clears because Arti's target-level queue delta is better
  than local C Tor (`-12` queued `>=1000ms`, `-533.344ms` median queue, and
  `-616.679ms` max queue). The promotion row is now `none seen`, so next proof
  is broader A/B, not the rejected broad timeout.
- Broader A/B
  `results/browser-compare-20260609T052706/browser-compare.json` passed quality
  across the check page, Tor homepage, and download page, but it rejects
  promotion. Current blockers are slow clean boot, a check-page page-load loss,
  and a resource-queue regression. Slow-stream quality is clear now:
  unresolved slow streams are `0` after resolved close-shape classification.
  The next source target is the check-page slow path and boot time, not partial
  idle timeout work.
- Focused check-page A/B
  `results/browser-compare-20260609T054435/browser-compare.json` passed quality.
  Default Arti beat local C Tor page-only on this window but still lost
  boot-plus-load. Plain health-aware cut the default Arti max load tail from
  `8474.244ms` to `2294.943ms`, but it booted slower and was slightly slower by
  summary median than default Arti, so keep it lab-only. Health-aware plus the
  bad-health guard is rejected on this path because it produced a `19590.578ms`
  max load and one unresolved slow hostname stream. The analyzer now ignores
  tiny queue noise when choosing promotion blockers; the next source target is
  boot stability plus a tail rule stronger than the current health/bad-health
  guard.
- Repeat boot proof
  `results/boot-compare-20260608T215008/boot-compare.json` rejects microdesc
  retry chunk `375`: default Arti median boot was `14.536s`, local C Tor was
  `12.758s`, and retry chunk `375` was worse at `16.899s` with directory
  timeout/failure signals. Refreshed boot timeline fields counted `8` default
  Arti circuit build failures, all channel-open failures, with first failure at
  about `10s`. Slow default boot now points at the first directory
  channel/tunnel setup and source reliability before certificate and microdesc
  download, not retry chunk size.
- Rebuilt diagnostic proof
  `results/boot-compare-20260608T220401/boot-compare.json` confirms the new
  release-binary `usage_kind` field: `3/3` default-Arti boots succeeded, median
  boot was `8.785s`, and the one slow run had `1` channel-open build failure
  with `usage_kind="dir"` at `10s`. Next source work should inspect why the
  first directory tunnel/channel open can sit pending for about `10s`.
- Channel-open timing proof
  `results/boot-compare-20260608T221237/boot-compare.json` confirms the new
  low-log channel-open timing field: `3/3` default-Arti boots succeeded, median
  boot was `8.140s`, and the slow run had a successful `dir` channel open in
  `1172ms` but then hit `4` microdescriptor partial-response directory
  timeouts with max dirclient elapsed `12366ms`. The next boot work has two
  separate lanes: first directory channel-open stalls and microdescriptor body
  timeout/tail after a good channel open.
- Body-progress timing proof
  `results/boot-compare-20260608T222441/boot-compare.json` confirms the fixed
  directory body timing fields: `3/3` default-Arti boots succeeded, median boot
  was `7.861s`, all `66` dirclient timing rows reached EOF, max body first byte
  was `992ms`, max body last byte was `2278ms`, max body read gap was `657ms`,
  and timeout-after-last-byte was `0ms`. The next timeout capture should now
  show exactly where the microdescriptor body read got stuck.
- Wider body-progress capture
  `results/boot-compare-20260608T222751/boot-compare.json` ran `8/8`
  successful default-Arti boots, median boot `9.252s`, max boot `13.982s`, with
  no directory timeouts and max timeout-after-last-byte `0ms`. It did show one
  bad-source retry case: run `1` had two microdescriptor `NOTDIRECTORY` partial
  responses before body bytes, then retried and booted in `9.731s`. Run `4` was
  slow but clean, with max body first byte `2038ms`, max body last byte
  `3916ms`, and max body read gap `1287ms`. Next work should inspect directory
  source retry/mark-failed behavior and body read-gap tail.
- Focused retry-chunk/body-timing proof
  `results/boot-compare-20260608T223455/boot-compare.json` keeps
  `TORFAST_DIR_MICRODESC_RETRY_IDS_PER_REQUEST=375` lab-only. It was only
  `0.232s` faster by median than default (`9.327s` versus `9.559s`) and added
  channel-open/circuit-build and `NOTDIRECTORY` signals. It removed the default
  profile's `4` directory timeouts and cut max body last byte from `11265ms` to
  `5874ms`, but the default timeout was slow trickle until near the `10s` total
  timeout, not idle after the last byte. Next work should target early
  replacement of slow/truncated microdescriptor bodies from one source.
- Microdescriptor body cap proof
  `results/boot-compare-20260608T224426/boot-compare.json` rejects the new
  default-off `TORFAST_DIRCLIENT_MICRODESC_BODY_MAX_MS=7000` path for promotion:
  default Arti median boot was `8.062s`, the cap median was `15.292s`, and the
  cap added `9` directory timeouts/partial responses across `3/5` runs. It did
  reduce max boot from `28.745s` to `18.809s`, but a plain elapsed cap cuts too
  many useful microdescriptor bodies. Keep it lab-only and target health-based
  source/body replacement instead.
- Microdescriptor minimum body-rate proof
  `TORFAST_DIRCLIENT_MICRODESC_MIN_RATE_BPS` is wired as a default-off bounded
  lab switch and uses a body-read-start clock, so slow headers do not spend the
  normal body timeout or lab rate window. Static proof
  `results/arti-quality-config-20260609T065856/arti-quality-config.json`
  passed `50` checks. The corrected `98304` B/s boot A/B
  `results/boot-compare-20260608T230100/boot-compare.json` was faster by median
  (`11.510s` versus `18.677s`) but added `4` directory timeouts/partial
  responses and worsened max boot (`25.301s` versus `22.329s`). The gentler
  `65536` B/s A/B
  `results/boot-compare-20260608T230303/boot-compare.json` had no candidate
  directory failures/timeouts/partials, but lost by median (`14.009s` versus
  `12.645s`) and max boot (`26.760s` versus `21.488s`). Keep minimum body-rate
  cutoffs lab-only and continue with source/body health replacement.
- Microdescriptor retry-delay cap proof
  `TORFAST_DIR_MICRODESC_RETRY_DELAY_MAX_MS` is wired as a default-off bounded
  lab switch. It only caps sleep before the next retry after a real
  microdescriptor download error, and only while the missing docs are still all
  microdescriptors. Static proof
  `results/arti-quality-config-20260609T070934/arti-quality-config.json`
  passed `51` checks. The first `500ms` boot A/B
  `results/boot-compare-20260608T231150/boot-compare.json` lost to default by
  median (`15.415s` versus `13.721s`), had slightly worse max boot (`30.110s`
  versus `29.864s`), and added timeout rows (`5` versus `3`). The cap fired
  only in `2/5` candidate runs, capping `1000ms` to `500ms`; `2000ms` would not
  change this observed path. Keep retry-delay capping lab-only and do not make
  it the next promotion lane.
- Source-circuit directory timing proof
  `results/boot-compare-20260608T232537/boot-compare.json` used the new scrubbed
  `source_circ` dirclient timing field. All `5/5` default-Arti boots succeeded,
  but run `4` booted in `32.828s` and had `4` microdescriptor partial timeouts
  on `source_circ="Circ~2.0"`. Max body last byte was `22197ms`, max read gap
  was `2146ms`, and the run summary counted max same-source partial rows `4`.
  This makes the next source work clearer: avoid letting several concurrent
  microdescriptor requests depend on one slow directory circuit/source, or
  replace that source earlier, without changing validation or path rules.
- Microdescriptor early-retry-on-partial proof
  `TORFAST_DIR_MICRODESC_EARLY_RETRY_ON_PARTIAL=1` is wired as a default-off
  microdescriptor-only lab switch. Static proof
  `results/arti-quality-config-20260609T074338/arti-quality-config.json` passed
  `52` checks. The first 5-run A/B
  `results/boot-compare-20260608T234014/boot-compare.json` rejects it: default
  Arti median boot was `14.820s`, early-retry-on-partial median was `22.668s`,
  and the candidate added directory failures/timeouts, `NOTDIRECTORY`, partial
  responses, and a warning. Keep it lab-only; early batch cutoff is not the next
  promotion lane.
- Microdescriptor source-spread proof
  `TORFAST_DIR_MICRODESC_SOURCE_SPREAD=1` is wired as a default-off
  microdescriptor-only lab switch. It uses a distinct `DirMicrodesc` usage with
  the same one-hop directory path and eligibility rules as normal directory
  circuits, then chooses the least-assigned eligible open directory circuit.
  Static proof `results/arti-quality-config-20260609T075456/arti-quality-config.json`
  passed `53` checks. The first 5-run A/B
  `results/boot-compare-20260608T235159/boot-compare.json` improved median boot
  from `16.917s` to `13.296s`, but worsened max boot (`33.123s` versus
  `23.253s`) and added directory failures/timeouts/partials. Keep it lab-only;
  the next source work should keep the median source-spread gain while avoiding
  the single-source tail.
- Microdescriptor source-spread plus early-usable proof
  `--extra-arti-dir-microdesc-source-spread-early-usable` combines
  `TORFAST_DIR_MICRODESC_SOURCE_SPREAD=1` with Arti's existing early usable
  notification. The parser now also reports which source-circuit label owns the
  most timeout rows and which owns the most partial rows. Static proof
  `results/arti-quality-config-20260609T075951/arti-quality-config.json` passed
  `53` checks. The first 5-run A/B
  `results/boot-compare-20260608T235958/boot-compare.json` rejects the combo as
  a speed change: default median boot was `9.986s`, combo median was `14.255s`,
  and default remained the faster profile. The combo removed directory
  failures/timeouts/partials in this small run, but added one circuit-build
  failure and lost by median, so keep it lab-only.
- Microdescriptor pending-spread proof
  `TORFAST_DIR_MICRODESC_PENDING_SPREAD=1` is wired as a default-off
  `DirMicrodesc`-only lab switch. It tests the pending-circuit concentration
  path by skipping an already-assigned microdescriptor directory circuit once
  when another unused eligible circuit may still arrive, with fallback to the
  skipped circuit if nothing else works. Static proof
  `results/arti-quality-config-20260609T080825/arti-quality-config.json` passed
  `54` checks. The first 5-run A/B
  `results/boot-compare-20260609T001032/boot-compare.json` improved median boot
  from `13.701s` to `10.255s` and had `0` directory failures/timeouts/partials
  in both profiles, but worsened max boot (`22.870s` versus `17.010s`), raised
  circuit-build failures (`3` versus `2`), and still had high same-source rows.
  Keep it lab-only; next work should target slow clean-body tails and
  same-source concentration together.
- Microdescriptor source-spread plus pending-spread plus early-usable proof
  `--extra-arti-dir-microdesc-source-spread-pending-spread-early-usable`
  combines the `DirMicrodesc` source spread, the pending-spread fallback guard,
  and Arti's existing early usable notification. Static proof
  `results/arti-quality-config-20260609T085046/arti-quality-config.json` passed
  `54` checks. The first 5-run boot A/B
  `results/boot-compare-20260609T001539/boot-compare.json` improved median boot
  from `16.786s` to `11.172s`, improved max boot from `32.615s` to `17.377s`,
  and removed the default-side directory failure/partial/`NOTDIRECTORY` signals
  in that window. The first browser gate
  `results/browser-compare-20260609T081953/browser-compare.json` passed quality
  and beat default Arti and local C Tor on boot plus median load. The diagnostic
  browser replay `results/browser-compare-20260609T082109/browser-compare.json`
  also passed quality and showed the slow onion probe streams were local
  close/no-data shapes, not browser page-data stalls, but that sample had slower
  combo boot and slower combo median load than default Arti. Keep it lab-only
  until a wider browser A/B repeats the speed win.
- Wider source-spread browser proof
  `results/browser-compare-20260609T082814/browser-compare.json` rejects the
  triple combo for promotion: the combo finished all `15` page loads, but max
  load hit `40443.433ms` on check and `65683.059ms` on download. The focused
  diagnostic `results/browser-compare-20260609T083656/browser-compare.json`
  reproduced the bad download shape with lifecycle logs: combo download run `3`
  timed out after `121682.818ms`, with `15` hostname relay tails on one circuit
  and one stream idling `78591ms` after the last Tor byte. A new browser-runner
  flag, `--extra-arti-dir-microdesc-source-spread-pending-spread`, tested the
  same source and pending spread without early usable notification in
  `results/browser-compare-20260609T084334/browser-compare.json`; it also failed
  one download run and lost download page-only median to local C Tor. Keep both
  source-spread profiles lab-only. `tools/analyze_browser_compare.py` now prints
  `Browser Failed Run Relay-Tail Circuit Concentration` to group failed
  relay-tail streams by circuit. It shows `15/15` combo download tails on
  `Circ 4.14` in `083656`, and `21/24` default-Arti download tails on
  `Circ 3.14` in `084334`. Next work should target browser resource relay-tail
  circuit concentration on the download page.
- Source-spread plus exit-load-aware proof
  `tools/run_browser_compare.py --extra-arti-dir-microdesc-source-spread-pending-spread-early-usable-load-aware`
  adds a same-window profile that combines the source-spread boot combo with
  exit load-aware selection. Focused download proof
  `results/browser-compare-20260609T090110/browser-compare.json` passed quality,
  but the load-aware combo was slower than the old source-spread combo
  (`4051.174ms` median load versus `3113.566ms`) and had worse max load
  (`6025.671ms` versus `5599.319ms`). The guarded repeat with
  `--arti-exit-select-min-assignment-spread 2`,
  `results/browser-compare-20260609T090433/browser-compare.json`, also passed
  quality but was worse: guarded load-aware median load `7384.016ms` versus
  default Arti `4352.253ms` and local C Tor `4782.564ms`. Do not promote exit
  load-aware on top of the source-spread boot combo.
- Accepted-run relay-tail concentration proof
  `tools/analyze_browser_compare.py` now prints
  `Browser Successful Run Relay-Tail Circuit Concentration`, so completed slow
  browser runs expose circuit concentration too. On `20260609T090433`, the
  rejected guarded load-aware combo had `4` accepted slow hostname tails on
  `Circ 3.9` in run `3`; the old source-spread combo showed only one-stream
  accepted tails. Keep the next source work on resource-tail circuit
  concentration, not broader load-aware or assignment-spread knobs.
- Stream-terminal-idle bad-health proof
  `TORFAST_EXIT_SELECT_BAD_HEALTH_STREAM_IDLE_MS` is wired as a default-off,
  bounded lab signal behind the existing bad-health guard. Static proof
  `results/arti-quality-config-20260609T092948/arti-quality-config.json` passed
  `55` checks. Focused download proof
  `results/browser-compare-20260609T093222/browser-compare.json` passed browser
  quality with a `5000ms` threshold, but rejected this as a speed path: the
  source-spread plus load-aware plus terminal-idle profile had `6240.065ms`
  median load and `7232.918ms` max load, worse than default Arti
  (`4644.632ms`) and local C Tor (`3563.410ms`). Keep it lab-only.
- Active-stream cap proof
  `TORFAST_EXIT_SELECT_MAX_ACTIVE_STREAMS` is wired as a default-off, bounded
  exit-selection lab signal. It only chooses among already eligible open
  circuits and does not change path rules, relay choice, isolation, DNS, or
  browser prefs. Static proof
  `results/arti-quality-config-20260609T095109/arti-quality-config.json` passed
  `56` checks. Focused download proof
  `results/browser-compare-20260609T095334/browser-compare.json` passed browser
  quality with cap `2`. The old source-spread combo beat local C Tor by median
  page load in that small window (`3871.064ms` versus `4984.858ms`), but it
  still had a `10338.744ms` max load and slow hostname tails clustered on
  single circuits. The log fields did not yet prove the cap moved a selection.
  Keep it lab-only; next work should add direct cap-move proof and rerun a
  wider A/B.
- Active-stream cap move proof
  Local selection logs now include `selected_candidate_index_before_active_cap`
  and `active_stream_cap_moved`, and the browser runner keeps circuit-selection
  rows in compact signal context. Static proof
  `results/arti-quality-config-20260609T101530/arti-quality-config.json` passed
  `56` checks. Focused download proof
  `results/browser-compare-20260609T101308/browser-compare.json` passed browser
  quality with cap `1` and proved real exit-selection moves: default Arti
  moved `2/23`, source-spread moved `10/23`, and source-spread plus load-aware
  moved `1/22`. Do not promote it: resource-queue blockers remain, slow tails
  still cluster on single circuits, and the load-aware combo was slower than
  local C Tor by median load. Next work should handle the no-under-cap case
  where every eligible open circuit is already at or above the active cap.
- Active-stream saturated-fallback proof
  The no-under-cap case now chooses the least-active already eligible open exit
  circuit when all eligible open circuits are at or above
  `TORFAST_EXIT_SELECT_MAX_ACTIVE_STREAMS`. Selection logs include
  `active_stream_cap_saturated`, and static proof
  `results/arti-quality-config-20260609T104117/arti-quality-config.json` passed
  `56` checks. Focused download proof
  `results/browser-compare-20260609T102258/browser-compare.json` passed browser
  quality and proved saturated cases: default Arti had `12`, source-spread had
  `11`, and source-spread plus load-aware had `11`. Do not promote it: default
  Arti only looked slightly better by raw median load, paired load and boot+load
  were worse, source-spread/load-aware regressed, and resource-queue plus
  single-circuit tail blockers remain. Next work should reduce page resource
  queue safely.
- Same-isolation selection-only clue
  The analyzer now de-duplicates repeated same-isolation top-up log rows and
  reports `built runs`, `used runs`, and `missing lifecycle runs` in the top-up
  A/B table. Replaying `20260608T062521` shows the older top-up attempt proof
  had no built/used lifecycle rows, so top-up capacity itself was not proved.
  New focused proof `results/browser-compare-20260609T103420/browser-compare.json`
  also had a top-up attempt with `0` built and `0` used runs. The follow-up
  `results/browser-compare-20260609T103700/browser-compare.json` raised the
  top-up floor to `8`, made `0` top-ups, and still had sameiso2 prefer-cold beat
  baseline Arti in `3/3` paired download loads with lower max load. Do not
  promote: local C Tor had a bad same-window tail and this was only one target.
  The wider repeat `results/browser-compare-20260609T104252/browser-compare.json`
  passed quality but failed speed: sameiso2 prefer-cold was slower than baseline
  Arti on homepage and download paired medians and had a `39195.816ms` download
  max load tail. It also still made `1` same-isolation top-up attempt at the
  exact `8` assigned-stream floor, with no built/used lifecycle rows. Keep it
  lab-only. Next work should explain the page-resource queue and make the floor
  strict before more cold-candidate tests.
- Strict same-isolation top-up floor
  Source now requires `selected_assigned_streams` to be strictly greater than
  `TORFAST_EXIT_SAME_ISOLATION_MIN_ASSIGNED_STREAMS` before a lab top-up. The
  direct Rust test `same_isolation_topup_waits_for_reuse_pressure` passed, and
  static proof `results/arti-quality-config-20260609T111042/arti-quality-config.json`
  passed `56` checks. After rebuilding release Arti, browser proof
  `results/browser-compare-20260609T110147/browser-compare.json` passed quality
  and top-upped only at `9` assigned streams with floor `8`, not at exact floor.
  Do not promote sameiso2 prefer-cold: download improved, but homepage paired
  median regressed by `+4556.186ms`. Next work should explain the homepage
  resource queue before testing another selector.
- Homepage resource-queue attribution
  `tools/analyze_browser_compare.py` now adds `Arti Profile Queue Loss Reason`
  and `Arti Profile Queue Loss Mechanism`.
  Replaying `results/browser-compare-20260609T110147/browser-compare.json` shows
  the sameiso2 prefer-cold homepage loss had median queued `>=1000ms` delta
  `+16`, median max queue delta `+1550.031ms`, and worst-run load delta
  `+5327.003ms`. The worst queue circuit was `Circ 3.12` with only one candidate
  context and no better-health or lower-assignment alternative rows. The
  mechanism row adds `19` high-confidence queued rows, `16` late writes,
  `0` terminal pending bytes, `445/445` SENDMEs, min receive window `450`, and
  `0ms` write lag after terminal data, so the current cause label is late Tor
  data with no local pending/window block. Next work should diagnose why one
  selected circuit held late page-resource data, not tune cold-candidate
  selection.
- Sameiso prefer-cold active-cap proof
  `tools/run_browser_compare.py` now adds
  `--extra-arti-exit-select-prefer-cold-same-isolation-active-cap TARGET:CAP`,
  so a same-window lab profile can combine sameiso prefer-cold with an
  active-stream cap without changing baseline Arti. Static proof
  `results/arti-quality-config-20260609T114333/arti-quality-config.json` passed
  `56` checks. Browser proof
  `results/browser-compare-20260609T113311/browser-compare.json` passed quality,
  but rejects promotion: activecap1 won download versus baseline Arti by
  `-456.909ms` paired median load, but lost check by `+833.840ms` and homepage
  by `+2327.441ms`. It also had `55` active-cap picks, `0` active-cap moves,
  and `37` saturated cases. Next work should handle saturated same-isolation
  page loads or late terminal data on one circuit; cap `1` alone is not enough.
- Saturated active-cap sameiso top-up proof
  Local Arti source now allows the sameiso prefer-cold lab top-up gate to use
  `target + 1` when active-cap selection says all same-isolation candidates are
  saturated, capped at the normal max target plus one. Static proof
  `results/arti-quality-config-20260609T120202/arti-quality-config.json` passed
  `56` checks. Browser proof
  `results/browser-compare-20260609T115220/browser-compare.json` passed quality
  and prefs, but still rejects promotion: activecap1 won download by
  `-3074.228ms` paired median load, but lost check by `+863.064ms` and homepage
  by `+1469.777ms`. It had `41` active-cap picks, `7` moves, and `28` saturated
  cases, but `0` saturated top-ups. Keep it lab-only; next proof needs the new
  top-up path to actually fire or should go back to late terminal-data diagnosis.
- Lower-floor saturated top-up rejection
  Proof `results/browser-compare-20260609T120503/browser-compare.json` used the
  same shape with `--arti-exit-same-isolation-min-assigned-streams 4`. It made
  the path fire: activecap1 counted `6` same-isolation top-ups and all `6` were
  active-cap saturated. Do not promote it. The run exited nonzero because
  baseline Arti had one download failure, and activecap1 lost download by
  `+5601.995ms` paired median load with a `+68825.639ms` max-tail delta. The
  top-up lifecycle rows were all `missing`, so extra capacity was not usable
  before the page load. Stop tuning simple same-isolation floors; next work
  should target late single-circuit data or earlier usable capacity.
- Active-cap pressure early top-up rejection
  Source now lets the sameiso top-up gate count saturated active-cap pressure
  as reuse pressure only when the active-cap lab flag is set and the selected
  same-isolation candidate is at or above cap. Static proof
  `results/arti-quality-config-20260609T122405/arti-quality-config.json` passed
  `56` checks. Browser proof
  `results/browser-compare-20260609T122640/browser-compare.json` passed quality
  and prefs and made the new gate fire: activecap1 counted `9` same-isolation
  top-ups, all `9` active-cap saturated. Do not promote it. All lifecycle rows
  were still `missing`, and activecap1 lost paired median load versus baseline
  on check by `+922.914ms`, homepage by `+3389.940ms`, and download by
  `+2310.709ms`. Next work should leave sameiso active-cap top-up alone and
  inspect the health-aware-only lead or late Tor-data cause.
- Health-aware-only repeat rejection
  Proof `results/browser-compare-20260609T123806/browser-compare.json` passed
  quality, but rejected promotion. Health-aware avoid-bad-health won check by
  `-210.281ms` paired median load, but lost homepage by `+187.148ms` with a
  `+28174.935ms` max-tail delta, and lost download by `+1636.365ms`. The queue
  mechanism was still late Tor data with no local pending/window block, so a
  selector-only fix is not enough.
- First-stream sameiso prewarm rejection
  Source, runner, and analyzer now support the default-off lab switch
  `TORFAST_EXIT_SAME_ISOLATION_PREWARM_FIRST_STREAM`, exposed through
  `--extra-arti-exit-select-prefer-cold-same-isolation-prewarm-target` and the
  analyzer column `topup first-stream prewarm`. Static proof
  `results/arti-quality-config-20260609T125441/arti-quality-config.json` passed
  `56` checks. Browser proof
  `results/browser-compare-20260609T125803/browser-compare.json` failed quality:
  homepage run `3` timed out at `121487.242ms`, screenshot proof was missing,
  and all `3` top-up lifecycle rows were `missing`. Keep it lab-only; the next
  target is why extra same-isolation circuits do not become usable in time.
- Sameiso top-up lifecycle proof fix
  Source now forces build lifecycle logs to `info` for lab same-isolation
  top-up plans, and the analyzer separates true `missing` rows from
  `candidate_seen_no_build_log`. Static proof
  `results/arti-quality-config-20260609T132017/arti-quality-config.json` passed
  `56` checks. Replaying
  `results/browser-compare-20260609T125803/browser-compare.json` still rejects
  prewarmfirst, but shows the old "all missing" label was too broad: the check
  top-up stayed `missing`, while homepage run `3` saw `Circ 3.27` after top-up
  without a build-complete log. The next proof should rerun a top-up-firing
  shape with the new logs before changing speed logic again.
- Top-up lifecycle repeat with real build proof
  Proof `results/browser-compare-20260609T132248/browser-compare.json` passed
  quality and prefs. Sameiso2 prewarmfirst made `2` top-ups; both built at
  `info` level (`517ms` and `615ms`), with `0` build failures and `0` missing
  lifecycle rows. One was selected later on the download page. The profile beat
  baseline Arti on homepage by `-1521.870ms` paired median load and download by
  `-4791.892ms`, but lost check by `+65.142ms` and had a worse check max tail
  by `+930.432ms`. It still lost to local C Tor on check by `+118.779ms` and
  download by `+872.720ms` on summary medians. Keep lab-only; next work should
  keep the proof path but avoid applying the heavy selector/top-up shape to
  simple check-style loads.
- Light sameiso prewarm runner proof
  Proof `results/browser-compare-20260609T133530/browser-compare.json` passed
  quality and prefs for the new
  `--extra-arti-exit-same-isolation-prewarm-target 2` runner profile. This
  profile keeps same-isolation target `2` plus first-stream prewarm, but leaves
  load-aware, health-aware, avoid-bad-health, and prefer-cold selection off. It
  made `4` top-ups and all built, but none was used by retained streams. Median
  load was nearly tied with local C Tor on check (`+6.710ms`) and faster on
  homepage/download, but boot was `+17.136s` slower than local C Tor. Keep it
  as proof only; next work should fix boot and prove top-up use before any
  promotion.
- Boot-signal proof fix and light sameiso rejection repeat
  `tools/run_browser_compare.py` now records filtered `boot.signal_lines`, and
  the boot timeline analyzer uses them when present. This keeps directory boot
  rows visible even when relay lifecycle logging floods `boot.lines`. Small
  proof `results/browser-compare-20260609T135043/browser-compare.json` passed
  quality and prefs and proved the field works. It also showed light sameiso
  boot was not consistently slow (`12.740s`, near local C Tor `12.581s`), but
  the profile still rejected: download lost by `+8754.013ms`, the one top-up
  built in `754ms`, and retained streams did not use it. Next selector work
  must prove top-up use without reviving check/tail regressions.
- Load-aware sameiso prewarm rejection
  Runner proof `results/browser-compare-20260609T135829/browser-compare.json`
  passed quality and prefs for
  `--extra-arti-exit-load-aware-same-isolation-prewarm-target 2`. This finally
  proved a built top-up can be selected later: one retained top-up built in
  `615ms` and `used_by_streams` was true. Do not promote it. Median load still
  lost to local C Tor on all targets, including download by `+3582.929ms`, and
  the homepage max tail hit `28467.569ms`. Next selector work needs a safer
  rule that avoids selecting a cold extra circuit when it causes page-tail
  loss.
- Bad-health-gated load-aware sameiso rejection
  Proof `results/browser-compare-20260609T140545/browser-compare.json` passed
  quality and prefs with
  `--arti-exit-same-isolation-require-bad-health` plus the load-aware sameiso
  prewarm runner profile. Do not promote it. It won check, but still lost to
  local C Tor on homepage by `+720.244ms` and download by `+6405.873ms`.
  The only same-isolation top-up was requested after bad local health, then
  failed to build after `4511ms` and was not used. The analyzer now matches
  later same-profile build failures by `pending_id` and timestamp, so this row
  is no longer falsely labeled `missing`.
- Scheduler fairness proof setup
  `tools/analyze_browser_compare.py` now adds `Torfast Stream Scheduler Late
  Circuit Fairness`, but replaying
  `results/browser-compare-20260609T140545/browser-compare.json` showed no
  matching scheduler picks because that older run did not retain scheduler
  diagnostics. Arti now has default-off `TORFAST_STREAM_SCHEDULER_LOG`, and the
  browser runner enables it in byte-timing proof mode. Next step: rerun the bad
  download shape with byte timing, then only touch scheduling if the new table
  shows a real pick monopoly or same-stream streak.
- Health-aware sameiso prewarm rejection
  Proof `results/browser-compare-20260609T144811/browser-compare.json` passed
  quality and prefs but rejects
  `--extra-arti-exit-health-aware-same-isolation-prewarm-target 2` with
  `--arti-exit-select-health-min-move-score-bps 20000`. Baseline Arti already
  beat local C Tor on download median load (`3623.586ms` vs `4784.481ms`) and
  boot (`7.168s` vs `14.616s`). The health-aware sameiso prewarm profile lost
  badly: median load `12463.985ms`, max load `118389.890ms`, and queue loss
  reason `single selected circuit queue` with `0` better-health alt rows.
  Do not keep tuning sameiso prewarm with health-aware selection. Next work
  should protect the fast default path and investigate receive-window/resource
  queue risk only when baseline Arti loses in a same-window proof.
- Clean default-vs-local repeat
  Proof `results/browser-compare-20260609T145904/browser-compare.json` passed
  quality and prefs, but default Arti lost all three page-load medians to local
  C Tor: check `2795.674ms` vs `1491.005ms`, homepage `8270.914ms` vs
  `4515.363ms`, and download `14458.610ms` vs `5790.420ms`. Boot was also bad:
  `40.246s` vs local C Tor `10.633s`, with directory build failure, partial
  response, and directory timeout signals. The earlier download-only Arti win is
  not stable proof.
- Directory-spread rescue repeat
  Proof `results/browser-compare-20260609T150602/browser-compare.json` failed
  overall quality because default Arti had one homepage `netTimeout`, but
  `arti_release_browser_mdsrcspreadpendingearlyusable` passed all `9/9` own page
  loads and cut boot to `12.758s` with no directory failure signals. It won check
  and download page-load medians against local C Tor, but lost homepage
  (`6560.444ms` vs `4866.763ms`) and still lost boot-plus-load on every target.
  Keep it lab-only; next proof should diagnose the homepage loss with byte
  timing before any default change.
- Homepage byte-timing rescue proof
  Proof `results/browser-compare-20260609T151737/browser-compare.json` passed
  quality and prefs. The source-spread combo beat baseline Arti on homepage
  median load (`4585.615ms` vs `5485.691ms`) and max load (`6143.391ms` vs
  `16544.737ms`), but was still slightly slower than local C Tor by page-load
  median (`4585.615ms` vs `4430.342ms`). The blocker was resource queue only,
  with no scheduler monopoly seen.
- Homepage load-aware repeat
  Proof `results/browser-compare-20260609T152122/browser-compare.json` passed
  quality and prefs. The plain source-spread combo was best in that window:
  homepage median load `2931.112ms` vs local C Tor `5510.561ms`. The load-aware
  version was worse than plain source-spread (`4309.839ms` vs `2931.112ms`), so
  do not use load-aware for promotion. Next gate: broad normal check/homepage/
  download repeat for the plain source-spread combo.
- Broad source-spread gate
  Proof `results/browser-compare-20260609T152840/browser-compare.json` failed
  overall quality because baseline Arti had one download `netTimeout`, but the
  source-spread combo passed all `9/9` own page loads and kept prefs unchanged.
  It beat local C Tor on check and homepage medians and won boot+load on all
  three targets, but lost download page-load median (`4611.889ms` vs
  `3159.719ms`). Keep it lab-only.
- Download byte-timing follow-up
  Proof `results/browser-compare-20260609T153532/browser-compare.json` passed
  quality and prefs. Source-spread beat local C Tor on download median load
  (`4806.959ms` vs `6776.733ms`) and boot+load, but lost to default Arti
  (`3514.894ms`) with only `1/3` paired load wins. The loss was a single
  selected-circuit queue with late Tor data, not a local pending/window block.
  Next work should target download resource queue / late Tor data without
  changing path rules, relay choice, or browser prefs.
- Download active-cap proof
  `tools/run_browser_compare.py` now exposes
  `--extra-arti-exit-select-max-active-streams` for a runner-only same-window
  profile. Proof `results/browser-compare-20260609T155220/browser-compare.json`
  passed quality and prefs. `arti_release_browser_loadaware_activecap2` beat
  default Arti on all `3/3` paired download loads (`4266.003ms` median vs
  `10073.885ms`) and beat local C Tor (`5128.153ms`). It cut the worst queue
  from `8216.831ms` to `2183.377ms`. Keep it lab-only until a broad
  check/homepage/download gate passes and the stream-placement privacy risk is
  reviewed.
- Broad active-cap gate
  Proof `results/browser-compare-20260609T155804/browser-compare.json` failed
  overall quality because baseline Arti hit one download `netTimeout`, but
  `arti_release_browser_loadaware_activecap2` passed all `9/9` own page loads
  and kept prefs unchanged. Activecap2 beat local C Tor on check, homepage, and
  download median loads (`1333.735ms`, `5855.529ms`, `6436.895ms`) and on all
  boot+load medians. It also cut homepage/download max queue versus baseline
  Arti (`10150.203ms` to `4250.085ms`, `10350.207ms` to `2550.051ms`). Still
  lab-only: the gate was not a clean quality PASS, slow stream-gap blockers
  remain, and stream placement privacy needs review.
- Active-cap tuning
  Proof `results/browser-compare-20260609T161014/browser-compare.json` passed
  quality and prefs on download. Cap `1` had the best median load
  (`4967.970ms`), cap `2` was close (`5521.975ms`) and had the lower max queue
  (`1783.369ms` vs `2566.718ms`), and cap `3` lost to local C Tor. Follow-up
  broad proof `results/browser-compare-20260609T161607/browser-compare.json`
  rejects cap `1`: quality passed, but it lost check, homepage, and download
  medians to local C Tor. Keep cap `2` as the active-cap lab path; reject cap
  `1` for broad promotion and cap `3` as too loose.
- Active-cap stability repeat
  Proof `results/browser-compare-20260609T162554/browser-compare.json` failed
  overall quality because local C Tor had one check-page `nssFailure2`. The
  activecap2 candidate passed all `9/9` own page loads and prefs, but it was not
  a stable broad speed win: it beat local C Tor on homepage median load, but
  lost check and download medians. It also lost download versus baseline Arti in
  this repeat. Keep active-cap as lab-only queue evidence and shift the next
  proof to stream-gap/no-Tor-byte failures.
- Stream-gap/no-data proof
  Proof `results/browser-compare-20260609T163624/browser-compare.json` failed
  quality because default Arti download run `2` timed out after `120000ms`.
  `Circ 0.11` had `10` hostname relay-tail streams: `8` no-Tor-byte streams and
  `2` partial-then-idle streams, including `BEGIN` queued with no `CONNECTED`
  and `CONNECTED` with no `DATA`. Activecap2 avoided the timeout and beat local
  C Tor on download median load, but lost homepage median load. Do not broaden
  active-cap. Next test a default-off no-data/idle stream health knob, with
  privacy review, and keep path rules plus browser prefs unchanged.
- Active no-DATA bad-health rejection
  `TORFAST_EXIT_SELECT_BAD_HEALTH_ACTIVE_NO_DATA_MS` is wired as a default-off,
  bounded lab signal behind the existing bad-health guard. Static proof
  `results/arti-quality-config-20260609T170331/arti-quality-config.json` passed
  `58` checks. Browser proof
  `results/browser-compare-20260609T171439/browser-compare.json` failed quality:
  the active-no-DATA profile failed `2/3` download runs, default Arti failed
  `1/3`, and local C Tor failed `0/3`. It also did not reproduce the multi-stream
  `Circ 0.11` pileup; failed tails were one stream per circuit. Do not promote or
  broaden this selector. Next work should target per-stream relay-tail timeout,
  abandon, or retry behavior with strict privacy guardrails.
- No-Tor-byte timeout repeat rejection
  The analyzer now gives `TORFAST_SOCKS_NO_TOR_BYTE_RELAY_TIMEOUT_MS` the same
  safety context as partial-idle closes: client-abandon fields and active browser
  resource context. Static proof
  `results/arti-quality-config-20260609T173625/arti-quality-config.json` passed
  `58` checks. Browser proof
  `results/browser-compare-20260609T174005/browser-compare.json` passed quality
  and prefs, but the no-byte `5000ms` profile fired `0` no-byte timeout events
  and lost download badly (`10036.529ms` median load vs default Arti
  `3913.271ms`, max `40764.704ms` vs `5256.253ms`). Keep no-byte close lab-only.
  The saved selected-circuit proof now shows the bad `Circ 1.15 (Tunnel 33)` run
  was a multi-stream late circuit: `17` late queued resources across `6`
  terminal streams, with max terminal last data after queue `9746.873ms` and max
  terminal data gap `4173.000ms`. Next work should diagnose selected-circuit
  multi-stream late DATA, not lower this timeout. A new cause table now rules
  out the local stream scheduler and circuit send block for that row: `36`
  scheduler DATA picks across `6` streams, top share `27.778%`, max streak `3`,
  `0` congestion scheduler blocks, `0` `can_send=false`, fixed-window mode,
  `0` terminal pending bytes, all terminal SENDMEs OK, and min recv window
  `450`. The next source target should be circuit choice or network-side late
  DATA evidence, not stream scheduler changes.
- Queue-loss circuit-choice proof
  The analyzer now prints `Arti Profile Queue Loss Circuit Choice`. For the same
  no-byte repeat loss, `Circ 1.15 (Tunnel 33)` had `35` resources queued at
  least `1000ms`, `23` queued at slot depth `>=6`, and max queue `31633.966ms`.
  Choice context was only `*0:Circ 1.15:a1:s13125.000:g351.000`, with `0`
	  better-health and `0` lower-assignment alternative rows. The table labels the
	  choice `only selected open circuit logged`. Next work should not be another
	  score tweak among already-open circuits; prove/build safer open capacity
	  before the resource burst, or collect deeper network-side late-DATA evidence.
- Queue-loss capacity-pressure proof
  The analyzer now prints `Arti Profile Queue Loss Capacity Pressure`. Replaying
  the same bad run shows `28` selected open rows for `Circ 1.15`, always `1`
  eligible open candidate, max selected assigned streams `14`, max selected
  active streams `5`, open support max `14` with `12` isolation rejects and `1`
  port reject, active cap `0`, and `0` same-isolation topups. The label is
  `eligible same-isolation open capacity missing`. Next source work should make
  usable same-isolation capacity ready before the burst, or prove the network
  side is late.
- Load-aware same-isolation target rejection
  `tools/run_browser_compare.py` now exposes
  `--extra-arti-exit-load-aware-same-isolation-target` for lab-only A/B proof
  without first-stream prewarm. Target `2`
  (`results/browser-compare-20260609T182940/browser-compare.json`) passed
  quality but lost median load to both baseline Arti and local C Tor, and made
  `0` same-isolation topups because `2` eligible open candidates already met the
  target. Target `3`
  (`results/browser-compare-20260609T183428/browser-compare.json`) failed
  quality and produced a `62244.336ms` median load with `119453.966ms` max load.
  Reject this route for speed. Next work should not just raise same-isolation
  capacity targets; it needs a stricter trigger or a different late-DATA proof.
- Active-cap focused repeat rejection
  Proof `results/browser-compare-20260609T184543/browser-compare.json` used
  byte timing and `--extra-arti-exit-select-max-active-streams 2` for `5`
  download runs. It failed overall quality because default Arti and local C Tor
  each had one failed run. The activecap2 candidate completed `5/5`, but lost
  median load (`12315.364ms`) to both default Arti successful runs
  (`10197.894ms`) and local C Tor (`5776.944ms`), with a bad `83266.910ms` max
  tail. It had `47` active-cap picks, `27` saturated cases, and `0` active-cap
  moves, so the cap did not actually move selected circuits in this proof.
  Treat active-cap as rejected for promotion until a new mechanism proves real
  movement and stable quality. Next work should target one-eligible-circuit
  bursts or network-side late-DATA evidence.
- One-eligible open-circuit burst proof
  The analyzer now prints `Arti One-Eligible Open-Circuit Bursts`. Replaying
  `results/browser-compare-20260609T184543/browser-compare.json` shows the
  notable one-candidate bursts are labeled `isolation rejects most open
  circuits`. In activecap2 run `5`, all `16/16` exit-open rows had only one
  candidate, with max open total `14`, max rejected open `13`, isolation rejects
  `12`, port rejects `0`, and load `12315.364ms`. The default Arti failed run
  `5` had `36/39` exit-open rows with one candidate and `11` isolation rejects.
  Do not keep tuning active cap from this proof. Next source work needs a
  stricter privacy-safe same-isolation capacity trigger, or deeper proof that
  the network side is late.
- Isolation-shape proof hook
  Local Arti now adds scrubbed exit-isolation buckets to `open_support_summary`:
  unisolated exits, compatible isolated exits, incompatible isolated exits, and
  exit port/stability/country blockers. The analyzer prints these fields in the
  capacity-pressure and one-eligible-burst tables. This is proof-only and logs
  no isolation value or SOCKS auth. Next proof should rerun the one-eligible
  download shape and decide whether the shortage is free same-isolation capacity
  or open exits already owned by other isolation groups.
- Fresh isolation-shape activecap rejection
  `results/browser-compare-20260609T191722/browser-compare.json` reran the
  download shape with the rebuilt binary. Browser prefs stayed valid, but
  default Arti timed out once, so overall quality failed. Activecap2 completed
  `3/3`, but lost median load to local C Tor and had a `116838.145ms` max load.
  The new counters proved the shortage: activecap2 run `2` had `13` open
  circuits, only `1` compatible isolated exit, `10` other-isolation exits, and
  `0` free unisolated exits. The next source target should be selective
  same-isolation capacity for the current isolation group, not active-cap
  selection.
- Same-isolation other-isolation pressure first positive proof
  `results/browser-compare-20260609T194122/browser-compare.json` tested
  `--extra-arti-exit-same-isolation-other-isolation-pressure 2:3` on the
  download target for `3` runs. Quality passed and prefs stayed valid. The
  candidate completed `3/3`, beat default Arti median load
  (`3365.224ms` vs `4688.072ms`), beat local C Tor median load
  (`3365.224ms` vs `5541.779ms`), and kept max load at `4249.901ms`. The table
  shows `1` same-isolation topup, `0` failures, `1` built, `1` used, and
  other-isolation pressure over the `3` floor. This is promising only. Next
  proof must be a broader A/B across check, homepage, download, more runs, and
  repeat windows before promotion.
- Same-isolation other-isolation pressure broad rejection
  `results/browser-compare-20260609T194752/browser-compare.json` is that broader
  A/B: check, homepage, download, `5` runs, same `2:3` trigger. Overall quality
  failed because default Arti timed out on one homepage run. The candidate
  itself completed `15/15` runs and prefs stayed valid, but it is not speed
  proof. It improved check, then lost homepage to both default Arti and local C
  Tor, and lost download to local C Tor. Homepage was the blocker: paired wins
  `1/4`, summary median load delta `+2380.307ms`, and max tail delta
  `+7731.781ms`. The mechanism built top-ups without failures, but homepage
  top-up attempt runs were much slower (`+3668.504ms`). Keep `2:3` lab-only.
  Next source work should not promote broad same-isolation pressure; diagnose
  late selected-circuit DATA after top-up, or prove a stricter trigger that does
  not regress homepage/download.
- Same-isolation top-up timing diagnosis
  The analyzer now groups top-up lifecycle rows by target. Replaying
  `20260609T194752` shows homepage top-ups were early enough to matter
  (`6609.324ms` median load left after build), but still bad: used-run load
  delta `+10038.343ms`, unused-run load delta `+1874.053ms`. Download was
  split: used top-ups helped (`-1211.454ms`), but the unused top-up run regressed
  (`+1386.137ms`). This means the next useful source idea is not just "build
  more same-isolation circuits earlier"; it must make safer use/choice of that
  capacity, or prove why a selected same-isolation circuit goes late.
- Guarded prefer-cold plus other-isolation pressure
  Runner-only flag
  `--extra-arti-exit-select-prefer-cold-same-isolation-other-isolation-pressure`
  now tests guarded prefer-cold selection together with the other-isolation
  pressure trigger. Proof `results/browser-compare-20260609T200842/browser-compare.json`
  failed overall quality because default Arti and plain sameiso2/otheriso3 had
  timeout failures. The guarded prefer-cold sameiso2/otheriso3 profile completed
  `6/6` page runs, but stayed slower than local C Tor on boot and median loads.
  Keep it lab-only; it is useful as a reliability contrast, not speed proof.
- Strict-floor guarded prefer-cold other-isolation pressure rejection
  Rebuilt release Arti, then reran the same guarded prefer-cold sameiso2/otheriso3
  other-isolation-pressure profile with
  `--arti-exit-same-isolation-min-assigned-streams 8`.
  `results/browser-compare-20260609T202137/browser-compare.json` failed quality.
  The guarded prefer-cold profile timed out on `4/6` page runs and the plain
  sameiso2/otheriso3 profile also timed out on homepage run `3`. The successful
	  guarded prefer-cold loads were still not good enough: homepage `7306.479ms`,
	  download `10519.385ms`. Do not continue widening this same-isolation-pressure
	  path until baseline Arti stream gaps/resource queues are understood.
	- Selected-circuit network evidence table
	  The analyzer now prints `Arti Selected-Circuit Network Evidence`. Replaying
	  `20260609T202137` shows the baseline failed download run as partial DATA then
	  long idle on selected circuits `Circ 2.3` and `Circ 1.7`
	  (`39775ms`/`34661ms` max relay, `37133ms`/`33036ms` idle). The successful
	  baseline download tail also shows selected-circuit late DATA: `Circ 1.16` had
	  `28` late resources, `6` terminal streams, no scheduler monopoly, no local
	  block seen, only selected open circuit logged, and the hint `late DATA on
	  selected circuit`. Next source work should target safer circuit
	  choice/capacity proof or deeper network-side late-DATA evidence. Do not patch
	  the stream scheduler from this proof.
		- Stream receiver no-END close trace
		  `tor-proto/src/stream/raw.rs` now logs
		  `torfast stream receiver no-end close` when a stream receiver closes without
		  an END cell and returns `not_connected`. The analyzer parses it, joins it to
		  terminal stream rows, and shows `no-END closes` in the selected-circuit
		  network evidence table. Old `20260609T202137` logs show `0` because the trace
		  was not present yet. Next proof should rebuild Arti and check whether the
		  baseline partial-DATA idle failures close this way.
		- Baseline no-END close proof
		  Rebuilt release Arti and ran
		  `results/browser-compare-20260609T205638/browser-compare.json`, with analyzer
		  output at `results/browser-compare-20260609T205638/analysis.md`. Quality
		  failed: baseline Arti timed out on download run `3` after `121406.088ms`,
		  while local C Tor completed `3/3`. The worst failed onion stream was timing
		  id `22` on `Circ 2.8`, stream `10599`: partial DATA arrived, then it idled
		  `55612ms` after the last Tor byte, then the receiver closed without END
		  (`1` no-END close, `10` read events, `0` SENDMEs, min receive window `491`,
		  max queued bytes after read `2922`, pending bytes `0`). The analyzer labels
		  this `failed partial DATA then no-END close`. Keep this as proof only. Next
		  source work should explain why the selected stream tears down after long
		  late DATA and why selected circuits go late even when open alternatives
		  exist. Do not promote this build, do not patch the stream scheduler from this
		  proof, and do not keep widening same-isolation pressure.
		- Close-decision proof
		  `tor-proto/src/circuit/circhop.rs` now logs the stream-map close decision
		  (`close_reason`, `should_send_end`, `close_behavior`) as
		  `delivery="close_decision"`, and the analyzer joins it to terminal streams
		  and selected-circuit evidence. Proof
		  `results/browser-compare-20260609T211227/browser-compare.json`, with
		  analyzer output at `results/browser-compare-20260609T211227/analysis.md`,
		  passed quality: Arti and local C Tor both completed `3/3` download runs.
		  Arti was page-fast (`4612.915ms` median load vs local C Tor `5535.373ms`,
		  paired load wins `3/3`) but not promotion-safe because boot was slower
		  (`26.092s` vs `10.561s`, boot+median load `30704.915ms` vs
		  `16096.373ms`) and the blocker is `boot slower, boot directory`.
		  The no-END rows in this passing run mostly match local `StreamTargetClosed`
		  with `should_send_end=Send`, so no-END alone is not network-side proof. Next
		  work should reproduce the failed timeout with this trace enabled, and fix or
		  prove the cold boot directory delay separately.
		- Load-aware directory-combo proof
		  The source-spread plus pending-spread plus early-usable plus load-aware
		  profile is the best broad speed proof so far, but it is not solved. Broad
		  proof `results/browser-compare-20260609T212517/browser-compare.json` passed
		  quality, completed `15/15` candidate page runs, booted in `6.969s` versus
		  local C Tor `15.565s`, and beat local C Tor summary median load on check,
		  homepage, and download. But byte-timing replay
		  `results/browser-compare-20260609T213125/browser-compare.json` hit the old
		  boot-directory tail again: candidate boot `22.334s` versus local C Tor
		  `11.798s`, with `NOTDIRECTORY` and partial-response signals. Do not promote
		  this profile yet. Next source work should fix or safely retry the
		  microdescriptor partial/NOTDIRECTORY boot path for this combo, then rerun
		  the same 5-run, 3-target gate.
		  Follow-up proof
		  `results/browser-compare-20260609T214104/browser-compare.json` tested the
		  existing early-retry-on-partial boot idea inside this combo and rejected it.
		  The early-retry profile booted in `20.671s` versus local C Tor `18.580s`,
		  had `6` directory-failure signals, and lost median load on both focused
		  targets. Keep `TORFAST_DIR_MICRODESC_EARLY_RETRY_ON_PARTIAL` lab-only for
		  this path. The next source work should build a safer retry/source-choice
		  policy instead of stopping the batch on the first partial response.
		  Partial-retry chunking is that safer lab shape:
		  `TORFAST_DIR_MICRODESC_PARTIAL_RETRY_CHUNKING=1` counts partial
		  microdescriptor responses as retry signals while keeping the current batch.
		  Clean proof `results/browser-compare-20260609T220925/browser-compare.json`
		  passed quality and booted the partial-retry profile in `6.258s` versus
		  local C Tor `12.946s`, but it still lost page-only median load to local C
		  Tor on check and download and kept the `resource queue` blocker. Do not
		  promote it yet. Next proof should retain the partial-retry signal in boot
		  logs and pass a clean 5-run gate; next source work should target the late
		  selected-circuit/resource-queue tail.
		  Clean 5-run proof
		  `results/browser-compare-20260609T221818/browser-compare.json` also
		  passed quality. The profile booted in `12.669s` versus local C Tor
		  `14.990s`, but page-only median load lost to local C Tor on all three
		  targets and download boot+load also lost. The boot signals did not include
		  `partial retry chunking signal`, so this proves the combo was enabled but
		  not that partial-retry chunking fired. Keep this lab-only; next proof
		  should explain the stream-gap/resource-queue tail.
		  Runner proof plumbing now makes that next proof possible:
		  `--arti-socks-relay-byte-timing` auto-uses `info,tor_proto=debug` when
		  the caller leaves the normal `info` default, so relay receive and stream
		  receiver rows are retained without unrelated full debug logs. Focused
		  proof `results/browser-compare-20260609T223414/browser-compare.json`
		  passed quality and printed the stream-gap tables. It points at late page
		  resource queueing on selected circuits, not a scheduler monopoly or local
		  pending/window block. Keep patching proof/source in that lane.
		  Follow-up load-aware-only proof
		  `results/browser-compare-20260609T223935/browser-compare.json` passed
		  quality and beat local C Tor on the download-page median
		  (`5203.072ms` versus `6919.567ms`), but it still had the `resource queue`
		  blocker and a worse max tail than baseline Arti. Keep load-aware
		  lab-only; use it as a comparison point for the next queue-tail proof.
		  Low-log selector proof is fixed too:
		  `results/browser-compare-20260609T225109/browser-compare.json` passed
		  quality and captured circuit-selection rows at `INFO` with
		  `TORFAST_EXIT_SELECT_LOW_LOG_CONTEXT=1`. The next queue-tail proof can
		  now include candidate-choice context without full debug logging.
		  The first clean 3-run follow-up with run-windowed proxy evidence is
		  `results/browser-compare-20260609T233054/browser-compare.json`. It
		  passed quality, but rejects load-aware promotion: load-aware median
		  download load was `6850.239ms`, slower than baseline Arti
		  `4515.505ms` and local C Tor `4735.462ms`, with a worse max tail
		  (`10807.155ms`). Scheduler rows were retained and showed `0` blocked
		  hops, so do not patch stream scheduling from this proof. Next work
		  should target selected-circuit late-DATA/queue evidence or a stricter
		  circuit-choice signal while leaving sameiso and active-cap tuning alone.
		  Analyzer replay now fills that stricter choice signal for the two main
		  slow load-aware circuits: run `3` `Circ 2.13` had `12` selected-open
		  rows and `Circ 3.5` had `2`, but both had only one eligible open
		  circuit and no better logged alternative. The remaining missing
		  context is for circuits selected before the run-window proof slice.
		  Next work should explain or change the timing that leaves the browser
		  burst with one eligible same-isolation exit, not retune selector score,
		  sameiso target, active cap, or scheduler picks.
		  The runner also keeps pre-run selection-open context for circuits that
		  actually appear inside the run window, while still dropping unrelated
		  old rows and post-run rows. Use a fresh run before treating any reused
		  circuit as "choice context missing".
		  Fresh proof `results/browser-compare-20260609T234755/browser-compare.json`
		  passed quality and showed load-aware beating local C Tor in that window,
		  but still losing to baseline Arti (`0/3` paired wins, `+1496.606ms`
		  summary median load, worse max tail). Most slow selected circuits now
		  have choice context and mostly show no better logged open alternative.
		  Keep the next work in reused-circuit/late-DATA proof or capacity timing,
		  not selector-score promotion.
		  Follow-up proof plumbing now raises fast
		  `torfast circuit selection build complete/failed/canceled` rows to
		  `INFO` under `TORFAST_EXIT_SELECT_LOW_LOG_CONTEXT=1`, keeps matching
		  pre-run build-complete rows for circuits later seen in the run, and
		  labels those as pending-build context. The next fresh benchmark should
		  confirm whether rows like `Circ 4.11` are pending-built circuits or
		  true selector blind spots.
		  Fresh rebuild proof
		  `results/browser-compare-20260609T235823/browser-compare.json`
		  confirms those fast build-complete rows are captured in saved proof.
		  It did not hit a load-aware slow selected-circuit row needing the new
		  pending-build label, and it was only one run, so keep load-aware
		  lab-only and repeat before any promotion call.
		  Fresh 3-run proof
		  `results/browser-compare-20260610T000342/browser-compare.json`
		  rejects plain load-aware again: median load `8457.081ms` and max tail
		  `59930.601ms` versus baseline Arti `4164.807ms`. The worst tail missed
		  SOCKS stream-link context, so the next patch stayed proof-only.
		  Rebuilt proof `results/browser-compare-20260610T001352/browser-compare.json`
		  confirms fast `stream linked` rows are now retained under byte timing
		  (`30` saved rows). Next work can use that stronger join before making
		  another circuit-choice change.
		  Fresh health-aware A/B proof
		  `results/browser-compare-20260610T001702/browser-compare.json` was a
		  useful narrow positive: download median load was `4296.496ms` versus
		  baseline Arti `13337.450ms` and local C Tor `5800.935ms`, with quality
		  passing and `141` stream-link rows retained. Do not treat it as a
		  promotion result because it covered only one target.
		  Wider gate `results/browser-compare-20260610T002123/browser-compare.json`
		  rejects health-aware promotion. Quality passed across check, homepage,
		  and download, but health-aware lost check and homepage to baseline Arti,
		  booted slower than both baseline Arti and local C Tor, and had bad max
		  tails around `26s` on check/homepage. Keep health-aware lab-only; target
		  stream-gap/resource-queue tails next instead of promoting selector health
		  scoring.
		  Analyzer proof now adds `Resource Queue Lifecycle Evidence`, which joins
		  late queued browser resources to the exact SOCKS stream lifecycle. Replaying
		  `results/browser-compare-20260610T002123/browser-compare.json` shows the
		  slow queued resources had DATA delivered, `queue full` was `0`, max circuit
		  sender queue was `0`, and terminal pending bytes were `0`. This keeps the
		  next source lane pointed at late selected-circuit DATA, not local queue-full
		  or pending-byte behavior. Python unit discovery still passes `164` tests and
		  Python compile still passes.
		  Follow-up analyzer proof adds `Browser Resource Queue Choice Class Summary`.
		  Replaying `results/browser-compare-20260610T002123/browser-compare.json`
		  classifies the slow rows as `19` only-selected-open, `5`
		  lower-assignment-alternative, and `0` better-health-alternative. Keep the
		  next source work on same-isolation capacity timing first, with guarded
		  assignment proof second. Do not spend the next pass on broad health selector
		  scoring.
		  Fresh same-isolation prewarm proof
		  `results/browser-compare-20260610T004615/browser-compare.json` passed
		  quality and improved homepage median load, but lost check and download and
		  showed homepage/download top-ups were built but not used. Fresh guarded
		  prefer-cold prewarm proof
		  `results/browser-compare-20260610T005212/browser-compare.json` failed
		  quality on download with a browser net timeout, made download much slower
		  on successful runs, and still used `0` built top-ups. Reject both as
		  promotion paths. The next proof should explain why built same-isolation
		  top-ups are not selected/used, and why lower-assignment alternatives are
		  not chosen safely.
		  Analyzer follow-up now prints `Arti Profile Same-Isolation Top-Up Nonuse
		  Detail`. Replays show `004615` had `5` unused built/seen top-ups (`4`
		  never appeared later; `1` lost to better health), while `005212` had `6`
		  (`2` never appeared later; `4` lost to better health). The next source
		  work should make built top-ups become usable open candidates in time, or
		  prove a safe cold/unknown-health choice rule. Do not spend the next pass
		  on simply making more same-isolation prewarm circuits.
		  Source follow-up fixed the lab flag wiring in `tor-circmgr/src/mgr.rs`:
		  `select_prefer_cold_same_isolation` is now passed into
		  `find_best_index_before_active_cap` instead of being logged but dropped.
		  Next proof should rerun the guarded prefer-cold same-isolation prewarm
		  gate before making any promotion claim.
		  Rerun `results/browser-compare-20260610T011528/browser-compare.json`
		  used the rebuilt patched Arti. It still failed quality on download run
		  `1` with a browser net timeout, `3` no-Tor-byte relay tails, and max
		  relay `59166ms`. It improved homepage median load, but lost check and
		  download and had `0/2` paired download wins. The nonuse detail changed
		  again after analyzer cleanup: `3` built/seen top-ups had no later
		  circuit-selection event after proof, and the linked streams had already
		  started before proof. Keep this profile lab-only. Next source work
		  should make same-isolation prewarm earlier or create useful later
		  selection after build, plus handle no-Tor-byte stream waits, not more
		  prewarm count or the prefer-cold wiring.
		  Pending-wait follow-up added default-off
		  `TORFAST_EXIT_SAME_ISOLATION_PENDING_WAIT_MS` (`50..=2000ms`) so a
		  stream can briefly wait for same-isolation capacity that is already
		  building, then fall back to the selected open circuit. Validation passed:
		  Python compile, `python3 -m unittest discover` (`167` tests), static
		  Arti quality config, `cargo test -p tor-circmgr` (`70` tests plus
		  doc-tests), and release build. Live proof
		  `results/browser-compare-20260610T014101/browser-compare.json` passed
		  quality and beat baseline Arti A/B on both tested targets, but still did
		  not fully beat C Tor and boot got worse from directory partial-response
		  timeouts. Keep it lab-only. Next work: earlier first-stream top-up and
		  boot directory reliability.
		  Pressure-wait follow-up widened that lab-only wait so it can fire when
		  the selected same-isolation circuit is already assigned and matching
		  capacity is pending, even when `open_candidates == target`. Analyzer
		  parsing now counts these waits. Proof
		  `results/browser-compare-20260610T015105/browser-compare.json` passed
		  quality, showed `9` pending waits and one wait win, and beat baseline
		  Arti A/B on both tested pages. It beat local C Tor on homepage, but
		  still lost download page-load to local C Tor by `35.6%` median load.
		  Keep it lab-only. Next work: slow download relay tails and boot
		  directory failures.
		  SOCKS byte-timing proof follow-up promoted fast connect/reply proof
		  rows only under default-off `TORFAST_SOCKS_RELAY_BYTE_TIMING=1`, and
		  the runner now keeps all SOCKS timing rows for timing ids linked to
		  late terminal streams. Proof
		  `results/browser-compare-20260610T021009/browser-compare.json` passed
		  quality and confirmed the rows are present (`7/7` baseline Arti and
		  `11/11` patched profile stream-ready/reply rows). It rejected the
		  patched profile: download load was `61687.470ms` vs local C Tor
		  `5236.324ms`, with multiple selected circuits showing `4079..4801ms`
		  DATA gaps and very low receive rates. Keep this lab-only. Next work:
		  selected-circuit health/low-rate evidence and boot directory failures,
		  not more same-isolation capacity.
		  Active-stream-age follow-up added proof-only
		  `active_stream_age_ms` candidate logging and analyzer columns. Proof
		  `results/browser-compare-20260610T022130/browser-compare.json` passed
		  quality, but rejected
		  `--extra-arti-exit-select-bad-health-active-no-data-ms 5000`: baseline
		  Arti load was `2726.419ms`, the active-no-data profile was
		  `5524.763ms`, and selected low-rate picks stayed at `5`. Keep it
		  lab-only. Next work: selected low-rate circuit guard evidence, not
		  active-no-data promotion.
		  Health-aware threshold repeat tested the existing
		  `--extra-arti-exit-select-health-min-move-score-bps 16000` knob before
		  adding new selector logic. One-run proof
		  `results/browser-compare-20260610T023142/browser-compare.json` passed
		  quality and looked good, but the 3-run repeat
		  `results/browser-compare-20260610T023311/browser-compare.json` rejected
		  it: `0/3` paired load wins against baseline Arti, paired median load
		  `+6029.752ms`, max tail worse, and local C Tor page-load was faster.
		  Keep lower health-aware threshold lab-only. Next work: avoid slow
		  resource queues after selection, not just avoid low-rate circuits.
		  A clean combined runner profile was added:
		  `--extra-arti-exit-select-health-min-move-score-same-isolation-pending-wait`.
		  It tests health-aware min score plus same-isolation target and pending
		  wait without changing baseline Arti. Diagnostic proof
		  `results/browser-compare-20260610T024537/browser-compare.json` passed
		  quality. The `16000bps_sameiso2_wait800ms` profile beat baseline Arti
		  by `963.870ms` in its one paired run, but still lost page-load to local
		  C Tor by `1298.588ms` and booted slower. Keep it lab-only. Next work:
		  multi-run repeat plus boot directory cleanup before any promotion claim.
		  The 3-run repeat
		  `results/browser-compare-20260610T025054/browser-compare.json` rejected
		  that combined profile: median load `20387.059ms` versus baseline Arti
		  `4062.821ms`, local C Tor `7052.261ms`, only `1/3` paired wins against
		  baseline Arti, and max queue `22750.455ms`. Stop this exact
		  same-isolation pending-wait combo. Next work: guarded assignment and
		  resource-queue tails after selection.
		  The assigned-cap follow-up added a same-window
		  health-min assigned-cap runner profile plus default-off
		  `TORFAST_EXIT_SELECT_MAX_ASSIGNED_STREAMS`. The runner flag is
		  `--extra-arti-exit-select-health-min-move-score-assigned-cap` with
		  `SCORE:CAP`. Proof
		  `results/browser-compare-20260610T031147/browser-compare.json`
		  rejected `16000bps_assignedcap4`: quality failed with one
		  `121615.880ms` browser timeout and no screenshot on run 3. The two
		  successful cap runs reduced queues, but the profile still lost summary
		  median load to baseline Arti (`4674.788ms` vs `3580.733ms`) and only
		  won `1/2` paired successful loads. Keep this lab-only; cap 4 is not a
		  promotion path.
		- Find the next safe bottleneck after transient timeout reliability. Be careful
		  with exit-circuit racing because it can bias relay choice and needs privacy
		  review.
- Keep reducing page-only browser load without changing path rules, relay
  choice, or browser privacy prefs.

## Phase 2: safe client speed ideas

- Test circuit warmup counts.
- Test timeout policy.
- Test stream scheduling.
- Test congestion-aware circuit choice.
- Reject any idea that breaks `docs/quality-bar.md`.

Findings (2026-06-15):

- First quality-preserving speed win: Conflux as shipped (`ConfluxEnabled
  auto`, the Tor default) gives a large, reproducible bulk-throughput gain.
  Two independent interleaved A/B windows on a `5MB` object measured stock auto
  at `12.34` then `12.32 Mbps`, versus forced `noconflux` at `3.86` then
  `6.16 Mbps` (`~2-3x`), with non-overlapping ranges. Small pages were neutral,
  which is why earlier tiny-page Conflux runs (through
  `results/conflux-compare-20260614T003311`) saw no benefit. Proofs:
  `results/conflux-compare-20260615T022217` and
  `results/conflux-compare-20260615T023424`. Quality certified with Conflux on
  at `results/circuit-check-20260615T023935` (3-hop, guard-first, no reuse, no
  shared family/subnet). This needs no patch: the win is to keep Conflux
  enabled and leave `ConfluxClientUX` at `auto`.
- Negative result: forcing `ConfluxClientUX` never beat `auto` for bulk, and
  `latency` UX was the worst profile (below `noconflux`). Do not force a UX
  mode.

## Phase 3: browser quality

- Use Tor Browser as the privacy target.
- Add browser startup and page-load benchmarks.
- Add fingerprint checks before and after changes.
- Do not ship browser changes that make users easier to tell apart.

## Phase 4: upstream path

- Turn safe wins into small patches.
- Prefer upstream Tor or Arti patches.
- Keep a clear benchmark and risk note for each patch.
