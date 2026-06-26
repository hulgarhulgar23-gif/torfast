# Source Map

This is the first map of real upstream code.

## C Tor

C Tor is the best exact-quality base because it is the current reference client.

Important files:

- `upstream/tor/src/app/config/config.c`
  - `ConfluxEnabled` default is `auto`.
  - `ConfluxClientUX` default text is `throughput`.
  - Accepted values are `latency`, `throughput`, `latency_lowmem`,
    `throughput_lowmem`.
- `upstream/tor/src/app/config/or_options_st.h`
  - `CircuitStreamTimeout`
  - `DisablePredictedCircuits`
  - `AlwaysCongestionControl`
  - `ConfluxEnabled`
  - `ConfluxClientUX`
  - `MaxClientCircuitsPending`
- `upstream/tor/src/core/or/versions.c`
  - Conflux support requires FlowCtrl congestion control and Conflux v1.
- `upstream/tor/src/core/or/conflux*.c`
  - Conflux implementation.
- `upstream/tor/src/core/or/congestion_control*.c`
  - congestion control implementation.
- `upstream/tor/src/core/or/circuituse.c`
  - stream to circuit use.
- `upstream/tor/src/core/or/circuitstats.c`
  - circuit build time learning.

First safe test lane:

1. Run stock C Tor.
2. Run C Tor with `ConfluxClientUX latency`.
3. Run C Tor with `ConfluxClientUX throughput`.
4. Compare connect, first byte, and total time.
5. Do not change path length, relay rules, or browser behavior.

Current local result:

- C Tor builds at `upstream/tor/src/app/tor`.
- Version: `0.5.0.0-alpha-dev (git-5478318f2517d218)`.
- It links against Libevent 2.1.12, OpenSSL 3.6.2, LZMA, and zstd.
- The saved matrix is `results/tor-matrix-20260607T033437/matrix.json`.
- In that small run, stock C Tor was faster than the tested Conflux UX
  overrides for the two tiny HTTP fetch targets.
- The fresh proxy compare is
  `results/proxy-compare-20260607T034459/compare.json`.
- In that later run, release Arti was faster than stock C Tor for the two tiny
  HTTP fetch targets, but C Tor booted faster.

## Arti

Arti is the best Rust experiment base, but it is not the exact Tor Browser base.

Important files:

- `upstream/arti/crates/tor-proto/src/client/rpc.rs`
  - RPC path description already expects multi-path tunnels.
  - It says Arti did not yet build Conflux tunnels as of April 2026.
  - `arti:describe_path` returns live relay IDs and relay addresses for a
    stream/tunnel path.
- `upstream/arti/crates/arti/src/proxy/socks.rs`
  - SOCKS extended auth can attach a stream to an RPC object ID.
  - SOCKS username/password auth is also mapped into stream isolation.
  - Local lab patch calls `prefs.optimistic()` for normal SOCKS CONNECT, to
    match C Tor optimistic-data behavior.
  - Local lab patch can apply a default-off, bounded non-onion SOCKS CONNECT
    soft timeout with `TORFAST_SOCKS_CONNECT_SOFT_TIMEOUT_MS`. It skips
    `.onion`, and the browser runner exposes it as
    `--arti-socks-connect-soft-timeout-ms` or as an extra same-window profile
    with `--extra-arti-socks-connect-soft-timeout-ms`.
  - The soft-timeout lab path now uses the timeout only while another retry is
    still allowed. The final CONNECT attempt waits normally instead of turning
    a slow path into an early browser neterror.
  - `tools/run_browser_compare.py` can now create a same-window extra profile
    with both settings together:
    `--extra-arti-socks-connect-soft-timeout-combo MS:ATTEMPTS`.
  - The runner can also create one extra profile with both the SOCKS
    soft-timeout combo and the exit pending hedge:
    `--extra-arti-socks-connect-soft-timeout-pending-hedge-combo MS:ATTEMPTS:HEDGE_MS`.
  - Local lab patch can apply a default-off, bounded partial-response idle close
    with `TORFAST_SOCKS_PARTIAL_RELAY_IDLE_TIMEOUT_MS`, exposed by
    `tools/run_browser_compare.py --arti-socks-partial-relay-idle-timeout-ms`
    and same-window extra profiles through
    `--extra-arti-socks-partial-relay-idle-timeout-ms`. It only runs when
    explicitly enabled, skips onion streams, and logs
    `torfast socks timing partial relay idle timeout` when it fires.
  - Latest focused proof:
    `results/browser-compare-20260609T041850/browser-compare.json` passed
    quality with a `4000ms` profile but fired `0` partial-idle timeouts, so its
    speed win is not mechanism proof.
    `results/browser-compare-20260609T042353/browser-compare.json` passed
    quality with `2000ms` and `3000ms` profiles, each firing `2` partial-idle
    timeouts. The `3000ms` profile cut max idle after last Tor byte from
    `21872ms` to `3178ms`, but remains lab-only until source can distinguish
    browser-abandoned resource tails from needed transfers.
  - `tools/analyze_browser_compare.py` now prints
    `Torfast SOCKS Partial Idle Resource Context`. In
    `results/browser-compare-20260609T042353/browser-compare.json`, the timeout
    streams had `0` exact browser-resource matches and nearest-resource phase
    split `2` `after_response` / `2` `receiving`. Active-resource counts at
    timeout were `14`, `8`, `14`, and `5`, so a broad timeout close is not safe
    enough for exact quality. `promotion_blocker_summary_rows()` and
    `arti_profile_promotion_risk_rows()` now use that same active-resource
    proof to block these lab profiles until there is client-abandon proof. The
    same context table now also prints active-resource samples and max active
    time left after close.
  - `upstream/arti/crates/arti/src/proxy/socks.rs` now includes at-timeout
    client-abandon fields on `torfast socks timing partial relay idle timeout`:
    client EOF/error, Tor-to-browser write error/close error, and written bytes.
    `tools/analyze_browser_compare.py` prints these as
    `client abandon at timeout`. Static guard
    `results/arti-quality-config-20260609T045234/arti-quality-config.json`
    passed `47` checks and requires those fields.
    `results/browser-compare-20260609T045506/browser-compare.json` used the
    rebuilt binary and showed both `2000ms` timeout closes had
    `client abandon at timeout = no`; the analyzer now blocks this with
    `partial idle no client abandon`. The promotion summary also marks failed
    comparison baselines as `baseline failed` and changes next proof to
    `clean baseline proof`.
  - Local lab patch can apply a default-off, bounded non-onion no-byte relay
    close with `TORFAST_SOCKS_NO_TOR_BYTE_RELAY_TIMEOUT_MS`, exposed by
    `tools/run_browser_compare.py --arti-socks-no-tor-byte-relay-timeout-ms`
    and same-window extra profiles through
    `--extra-arti-socks-no-tor-byte-relay-timeout-ms`. It only fires after the
    browser has sent bytes and Tor has sent no bytes back, skips onion streams,
    and logs `torfast socks timing no tor byte relay timeout` when it fires.
    The no-byte timeout log now also includes client EOF/error and write-close
    proof fields, so the analyzer can tell whether the browser had abandoned the
    stream.
  - Local debug code can log SOCKS first-byte timing and bounded byte timelines
    when debug logging is enabled.
  - Local debug code also logs last-byte timing for SOCKS relay directions, so
    failed-run analysis can tell "no data" from "data arrived, then went idle".
  - Local debug code now logs SOCKS `timing_id` to Arti circuit/stream links
    after stream creation.
- `upstream/arti/crates/tor-proto/src/client/stream/data.rs`
  - Local debug helper exposes a `DataStream` stream key for SOCKS timing joins.
  - Local low-log stream terminal summaries now include read count, stream
    SENDME count, successful SENDME count, minimum receive window after taking a
    cell, and maximum queued stream bytes seen by the receiver. This is
    diagnostic only.
  - Local terminal summary code now records stream idle-after-last-Tor-byte
    tails into the owning client circuit when the stream had Tor DATA cells.
    This feeds local health only; it does not close streams or change browser
    behavior by itself.
- `upstream/arti/crates/tor-proto/src/client/circuit.rs`
  - `CircuitHealthSnapshot` now includes stream terminal idle fields:
    event count, max idle, bytes, and most recent idle time.
  - It also records `active_streams_started_at`, so the lab can tell how long a
    circuit has had active streams without fresh relay DATA.
  - `MutableState::note_stream_terminal_idle` updates those fields locally for
    one circuit.
- `upstream/arti/crates/arti-rpcserver/src/stream.rs`
  - `arti:new_oneshot_client` creates an RPC-visible stream handle.
- `upstream/arti/crates/tor-proto/src/client/reactor/conflux.rs`
  - client Conflux set code exists behind the feature work.
- `upstream/arti/crates/tor-proto/src/client/reactor/conflux/msghandler.rs`
  - client Conflux message handling.
- `upstream/arti/crates/tor-proto/src/circuit/reactor/*`
  - stream and circuit reactor path.
- `upstream/arti/crates/tor-proto/src/circuit/circhop.rs`
  - local debug code logs relay receive delivery, queue-full, stream-gone,
    incoming-request, and unknown-stream events.
  - local debug code now includes millisecond `event_epoch_ms` fields for those
    relay receive events.
- `upstream/arti/crates/tor-proto/src/stream/raw.rs`
  - local debug code logs stream receiver reads and SENDME sends with stream id,
    relay command, data bytes, queued bytes, receive window, and
    millisecond `event_epoch_ms` fields.
  - local diagnostic state keeps per-stream read/SENDME counters and receive
    window/queued-byte extrema for later terminal summaries.
- `upstream/arti/crates/tor-proto/src/congestion/sendme.rs`
  - local debug support exposes the current receive-window value for stream
    receiver diagnostics.
- `upstream/arti/crates/tor-proto/src/congestion/*`
  - congestion control pieces.
- `upstream/arti/crates/arti/src/arti-example-config.toml`
  - default preemptive circuit config predicts ports `80` and `443`.
  - `min_exit_circs_for_port` default is documented as the target number of
    available circuits per predicted exit port.
  - the browser runner can override this for lab tests with
    `--arti-min-exit-circs-for-port`, without changing the source default.
- `upstream/arti/crates/tor-circmgr/src/lib.rs`
  - upstream preemptive circuit task used a `10s` base delay before rechecking
    and launching predicted circuits.
  - local lab patch changes that recheck delay to `1s` to make normal predicted
    exit circuits ready sooner without changing path rules.
- `upstream/arti/crates/tor-circmgr/src/hspool.rs`
  - local startup fix retries the background hidden-service stem pool after
    `1s` when the first wakeup happens before timely netdir is ready.
  - normal idle delay stays `30s`; this does not change path length, relay
    choice rules, stream isolation, or browser behavior.
  - local lab patch can test bounded background hidden-service stem launch
    parallelism with `TORFAST_HSPOOL_LAUNCH_PARALLELISM`. Default remains
    serial width `1`; valid lab values are `1` through `4`. The wider path
    still uses the normal `launch_hs_unmanaged` builder and puts failed launch
    targets back for retry.
  - the browser runner can start same-window HS-pool launch A/B profiles with
    `--extra-arti-hspool-launch-parallelism`.
  - the browser runner can also start same-window HS-pool background-start-delay
    A/B profiles with `--extra-arti-hspool-background-start-delay-ms`. This
    uses the existing source env `TORFAST_HSPOOL_BACKGROUND_START_DELAY_MS`;
    default stays `1000ms` and harness values are bounded to `0..60000ms`.
  - the browser runner now adds `tor_circmgr=debug` to hspool launch A/B
    profiles so compact runs retain hspool mechanism rows.
  - Fresh proof `results/browser-compare-20260613T000747/browser-compare.json`
    passed quality with launch width `2`, but rejects promotion: homepage
    median improved, Tor check and download median loads worsened, and a
    `63027.689ms` homepage tail plus boot directory, resource queue, slow
    onion/data-gap, and slow hostname blockers remained.
  - Focused proof `results/browser-compare-20260613T002829/browser-compare.json`
    retained launch-enabled and background-ready rows, but still rejected speed:
    homepage load was `12373.766ms` versus base Arti `8184.036ms` and local C
    Tor `3931.445ms`, with slow onion still in tunnel acquisition.
  - low-log proof rows show hspool stem reuse, background-ready circuits,
    on-demand starts, and failures. Focused proof
    `results/browser-compare-20260612T212307/browser-compare.json` passed
    quality with `11` reused stems, `3` background stems ready, `0` on-demand
    starts, and `0` hspool failures.
  - local lab patch can test bounded on-demand pool grace with
    `TORFAST_HSPOOL_ON_DEMAND_POOL_GRACE_MS`. Default remains `0`; valid lab
    values are capped at `1000ms`. It waits briefly for a ready background HS
    stem before launching the on-demand stem, while keeping the same target,
    family, vanguard, and suitability checks.
  - the browser runner can start same-window HS-pool grace A/B profiles with
    `--extra-arti-hspool-on-demand-grace-ms`.
  - Proof `results/browser-compare-20260613T095400/browser-compare.json` passed
    quality but rejected promotion: `50ms` grace used on-demand starts and was
    `+904.046ms` slower than base Arti; `150ms` won that one sample but did not
    use the new grace path. Repeat proof
    `results/browser-compare-20260613T095613/browser-compare.json` also passed
    quality and rejected hard: `hspoolgrace150ms` loaded in `67565.351ms`
    versus base Arti `9373.039ms`. Keep this lab-only; the next source target is
    a no-delay race with on-demand launch or better preemptive HS pool readiness.
  - local lab patch can test a no-delay on-demand pool race with
    `TORFAST_HSPOOL_ON_DEMAND_POOL_RACE_MS`. Default remains `0`; valid lab
    values are capped at `1000ms`. It starts normal on-demand launch right away
    and races a ready background HS stem against that pending launch, while
    keeping the same target, family, vanguard, and suitability checks.
  - the browser runner can start same-window HS-pool race A/B profiles with
    `--extra-arti-hspool-on-demand-race-ms`.
  - Proof `results/browser-compare-20260613T101211/browser-compare.json` passed
    quality but did not promote: `150ms` won one sample without retained race
    mechanism proof, while `500ms` exercised the race path and lost by
    `+2863.948ms` versus base Arti. Repeat proof
    `results/browser-compare-20260613T101413/browser-compare.json` also passed
    quality and rejected promotion: `hspoolrace150ms` lost all `3` paired runs
    and was `+4248.678ms` slower than base Arti by summary median load. Keep
    this lab-only; the better source target is earlier HS pool readiness or
    hidden-service tunnel setup after descriptor fetch.
  - Proof `results/browser-compare-20260613T102523/browser-compare.json` tested
    existing HS-pool background startup delays `0ms` and `250ms`. It passed
    quality and looked promising only because base Arti had a large tail. Repeat
    proof `results/browser-compare-20260613T102711/browser-compare.json` passed
    quality and rejected promotion: `hspoolstart0ms` lost by `+1951.530ms`
    summary median load versus base Arti and won only `1/3` paired runs.
  - local source now emits info-level `torfast hspool timing` rows for stem
    ready/failed, stem selected, final specific-circuit extension ready/failed,
    and client rendezvous circuit ready. These rows split HS pool stem selection
    from final HS extension without target names or relay identities.
  - Proof `results/browser-compare-20260613T111942/browser-compare.json`, with
    analyzer output at `results/browser-compare-20260613T111942/analysis.md`,
    passed quality and retained the new low-log rows: `6` stem-ready rows, `4`
    specific-circuit-ready rows, `2` client-rend-ready rows, median final HS
    extension `350ms`, max extension `376ms`, and max stem `714ms`.
    This is mechanism proof only; the blocker row still flags `resource queue,
    slow onion/data gap`.
  - `crates/tor-circmgr/src/hspool/pool.rs` now has a bounded guarded-stem
    target lab override, `TORFAST_HSPOOL_GUARDED_STEM_TARGET`. The local
    default target remains `2`; lab values are accepted only from `2` through
    `16`, and `0`/`off`/invalid values fall back to the default. The runner
    exposes same-window A/B profiles with
    `--extra-arti-hspool-guarded-stem-target` and records
    `arti_hspool_guarded_stem_target`.
  - Proof `results/browser-compare-20260613T113902/browser-compare.json`, with
    analyzer output at `results/browser-compare-20260613T113902/analysis.md`,
    passed quality. `hspoolguarded6` beat base Arti in this one run
    (`9528.209ms` load versus `10727.941ms`, paired delta `-1199.732ms`), but
    still lost local C Tor (`5830.591ms`) and kept `resource queue, slow
    onion/data gap` blockers. Keep this lab-only; repeat or pair it with a
    stronger HS tunnel/resource-tail fix before considering promotion.
  - Guarded-target sweep
    `results/browser-compare-20260613T114503/browser-compare.json`, with
    analyzer output at `results/browser-compare-20260613T114503/analysis.md`,
    passed quality and showed `hspoolguarded8_3` winning `3/3` paired loads
    against base Arti, but still losing local C Tor by `+2265.304ms` paired
    median load. Focused warm-cache repeat
    `results/browser-compare-20260613T114935/browser-compare.json` rejected
    `hspoolguarded8`: it lost base Arti `0/5`, had `+2352.817ms` paired median
    load delta, and had a `71130.057ms` max-load tail from a `64569ms` onion
    CONNECT. Keep this knob lab-only and do not use a simple guarded-stem
    target increase as the next promotion path.
- `upstream/arti/crates/tor-hsclient/src/connect.rs`
  - local lab patch can overlap hidden-service intro-circuit acquisition with
    rendezvous setup when `TORFAST_HS_INTRO_REND_OVERLAP=1`.
  - default behavior is unchanged: the env flag is off unless explicitly set.
    The patch still uses the normal rendezvous and intro circuit builders and
    does not change HS path length, relay choice rules, INTRODUCE1 content, or
    stream isolation.
  - `tools/run_browser_compare.py` exposes it as
    `--extra-arti-hs-intro-rend-overlap` and adds `tor_hsclient=debug` for that
    profile so compact browser proofs retain `torfast hs timing` mechanism rows.
  - Fresh proof `results/browser-compare-20260613T004328/browser-compare.json`
    passed quality, but rejects promotion: the overlap profile lost homepage
    median load to base Arti (`13323.528ms` versus `5038.101ms`), lost Tor check
    to base Arti (`2171.106ms` versus `1845.912ms`), and still lost download to
    local C Tor (`8181.027ms` versus `5233.424ms`). Mechanism rows showed intro
    ready at `652ms` while rendezvous finished at `2238ms`, but analyzer still
    showed worse HS tunnel median and resource queue blockers.
  - local lab patch can start normal rendezvous setup before descriptor fetch
    finishes when `TORFAST_HS_REND_PREBUILD_BEFORE_DESC=1`. Default behavior is
    unchanged. If the early rendezvous fails, it logs the failure and falls back
    to the normal descriptor-then-rendezvous path. It does not add intro
    attempts and does not change descriptor choice, relay choice, path rules,
    INTRODUCE1 content, or stream isolation.
  - `tools/run_browser_compare.py` exposes it as
    `--extra-arti-hs-rend-prebuild-before-desc` and records
    `arti_hs_rend_prebuild_before_desc`; compact runs retain mechanism rows
    with `tor_hsclient=debug`.
  - Proof `results/browser-compare-20260613T104056/browser-compare.json` passed
    quality and showed a one-run win with mechanism rows retained. Repeat proof
    `results/browser-compare-20260613T104210/browser-compare.json` also passed
    quality and improved summary median load (`6063.357ms` versus base Arti
    `6454.160ms`) plus HS tunnel median (`1917ms` versus `3131ms`). Do not
    promote yet: paired A/B against base Arti won only `1/3` runs and paired
    median load was `+408.932ms` slower.
  - Five-run proof `results/browser-compare-20260613T105207/browser-compare.json`
    passed quality and rejected promotion: `hsrendpredesc` loaded in
    `9624.547ms` versus base Arti `7683.071ms` and local C Tor `5029.269ms`.
    It won only `2/5` paired runs against base Arti, `0/5` against local C Tor,
    and its median HS tunnel was no better than base. Keep this lab-only; the
    next source target should be the remaining C Tor gap in HS tunnel/intro
    timing and resource-queue tails, not earlier rendezvous setup alone.
  - local lab patch can share only a valid HS descriptor across same blinded HS
    identity and same client-secret-key identity when
    `TORFAST_HS_DESC_SHARED_CACHE=1`. Default behavior is unchanged. The cache
    key uses the blinded onion identity and either `none` for empty client
    secret keys or the existing secret-key `Arc` identity for non-empty keys.
    It copies only the `HsDescForTp` descriptor into each isolation-scoped
    `Data.desc`; it does not share `Data.ipts`, `Data.hsdirs`, streams,
    rendezvous circuits, intro history, relay choice, path choice, or browser
    behavior.
  - `tools/run_browser_compare.py` exposes this as
    `--extra-arti-hs-desc-shared-cache` and records
    `arti_hs_desc_shared_cache`. `tools/analyze_browser_compare.py` now prints
    descriptor shared-cache hit/store counts in the HS timing tables, and
    `tools/check_arti_quality_config.py` verifies the default-off,
    descriptor-only shape.
  - Proof `results/browser-compare-20260613T125354/browser-compare.json`, with
    analyzer output at `results/browser-compare-20260613T125354/analysis.md`,
    passed quality and proved the mechanism (`2` shared hits, `4` stores,
    HSDir descriptor responses down to `4` from base Arti `6`). It rejected
    promotion: `hsdescshare` lost base Arti by `+929.136ms` paired median load,
    won only `1/3` paired loads, and was much slower than local C Tor. Keep this
    lab-only.
  - local lab patch can hedge slow hidden-service intro-circuit acquisition with
    one backup normal intro-circuit request when
    `TORFAST_HS_INTRO_CIRCUIT_HEDGE_MS` is set. Default behavior is unchanged.
    Valid lab values are `500` through `60000`; `0`/`off`/invalid values disable
    it. The hedge uses the same intro target and normal circuit builder; it does
    not change descriptor choice, path length, relay choice rules, INTRODUCE1
    content, or stream isolation.
  - `tools/run_browser_compare.py` exposes it as
    `--extra-arti-hs-intro-circuit-hedge-ms` and records
    `arti_hs_intro_circuit_hedge_ms`. The quality guard covers the env name,
    bounds, parser, helper, hedge logs, and same-builder use.
  - Proof `results/browser-compare-20260613T120718/browser-compare.json`, with
    analyzer output at `results/browser-compare-20260613T120718/analysis.md`,
    passed quality but rejected `hsintrohedge1500ms`: it won only `1/3` paired
    loads against base Arti, had `+3390.772ms` paired median load delta, and had
    a worse max tail (`12339.044ms` versus base `10077.482ms`). Logs confirmed
    the hedge path was armed and one backup launched, but the primary won. Keep
    this knob lab-only.
- `upstream/arti/crates/tor-circmgr/src/impls.rs`
  - local lab patch keeps normal exit-stream selection at width `1` by default.
  - this keeps existing circuit eligibility and isolation checks; it does not
    launch extra circuits.
  - `TORFAST_EXIT_SELECT_PARALLELISM` is a bounded lab-only env override used
    by `tools/run_browser_compare.py --arti-exit-select-parallelism` for A/B
    tests of wider values. Valid values are `1` through `8`; default remains
    `1`.
  - the browser runner can start an extra same-window Arti A/B profile with
    `--extra-arti-exit-select-parallelism`.
  - local lab patch also keeps normal exit circuit launch parallelism at width
    `1` by default, but can test bounded wider exit launches with
    `TORFAST_EXIT_LAUNCH_PARALLELISM`. Valid lab values are `1` through `4`;
    default remains `1`. This still uses the normal target usage and isolation
    rules; it only races compatible exit circuit builds.
  - the browser runner can start same-window launch-width A/B profiles with
    `--arti-exit-launch-parallelism` and
    `--extra-arti-exit-launch-parallelism`.
  - Fresh proof in
    `results/browser-compare-20260612T223525/browser-compare.json` showed launch
    `2` passed quality and beat base Arti median page load on all three
    standard targets, but still lost local C Tor on all three. Fresh proof in
    `results/browser-compare-20260612T224226/browser-compare.json` showed launch
    `3` and `4` also passed quality but did not beat local C Tor cleanly. Keep
    exit launch parallelism lab-only.
- `upstream/arti/crates/tor-circmgr/src/mgr.rs`
  - local debug logs show open, pending, and build circuit-selection choices.
  - `AbstractTunnel` now exposes an optional read-only
    `CircuitHealthSnapshot`, and the load-aware debug log includes
    `candidate_health_summary`.
  - `OpenEntry` still tracks `assigned_streams`; the default-off
    `TORFAST_EXIT_SELECT_HEALTH_AWARE` lab selector can also score candidates
    from observed RELAY DATA cells and bytes. It only runs inside the
    load-aware exit candidate set. It requires enough recent DATA evidence,
    rejects max gaps above `750ms`, rejects scores older than `2000ms`, and
    only moves away from assignment on a high absolute score or a `2x`
    improvement.
  - `TORFAST_EXIT_SELECT_AVOID_BAD_HEALTH` is another default-off lab guard
    inside load-aware exit selection. It does not change eligibility or build
    extra circuits; it only avoids a selected open circuit when fresh local
    relay DATA evidence says the circuit is bad and another eligible circuit
    has fresh good health evidence. Cold, unknown, or stale circuits are not
    enough reason to move.
  - `TORFAST_EXIT_SELECT_BAD_HEALTH_STREAM_IDLE_MS` is a default-off, bounded
    lab extension to the same bad-health guard. When set from `1000ms` through
    `120000ms`, a recent stream terminal idle tail can mark a circuit bad for
    the existing guard. It is stale after the same `2000ms` health age window
    and does not alter eligibility, isolation, path length, or relay choice.
  - `TORFAST_EXIT_SELECT_BAD_HEALTH_ACTIVE_NO_DATA_MS` is another default-off,
    bounded lab extension. When set from `1000ms` through `120000ms`, a circuit
    with active streams and no fresh relay DATA can be marked bad for the
    existing guard. It only uses already eligible open circuits and does not
    change path rules, isolation, path length, or relay choice.
  - load-aware circuit-selection logs now include `selected_active_stream_age_ms`,
    and `candidate_health_summary` rows can include candidate
    `active_stream_age_ms`. This is diagnostic proof only and does not change
    circuit choice by itself.
  - local lab patch records pending-circuit age and can use
    `TORFAST_EXIT_PENDING_HEDGE_MS` to launch one extra pending normal exit
    circuit when the oldest pending exit circuit is already old. The env var is
    default-off, bounded from `500ms` through `60000ms`, and keeps the max
    pending cap at `2`.
  - actual pending-hedge launch, pending-hedge failure, pending-hedge
    timer-fire, build-hedge timer-fire, and build-hedge launch events are
    info-level, so low-log lab runs can prove whether either hedge path fired.
  - the pending wait path and initial build wait path now carry hedge timers, so
    the first slow waiter can re-run circuit selection after the threshold
    instead of relying on a later request to notice that the pending circuit is
    old.
  - local lab patch can use `TORFAST_EXIT_SAME_ISOLATION_TARGET` to build
    extra exit capacity for the exact same `TargetTunnelUsage`. It is
    default-off, bounded from `2` through `4`, exit-only, and preserves stream
    isolation by not sharing circuits across incompatible isolation groups.
  - local diagnostic code can use `TORFAST_EXIT_SELECT_LOW_LOG_CONTEXT` to emit
    the open-circuit candidate context at info level. It is default-off and does
    not change the selected circuit, eligibility, isolation, path length, relay
    choice, or circuit build behavior.

First safe Rust lane:

1. Build Arti.
2. Run it as a SOCKS proxy.
3. Measure it with `tools/run_baseline.py`.
4. Only then inspect if a small client scheduling patch is worth trying.

Current local result:

- Release Arti builds at `upstream/arti/target/release/arti`.
- Version: `2.4.0`.
- The fresh proxy compare measured release Arti against stock C Tor in one run.
- Release Arti was faster on the two tiny fetch targets, but this is not browser
  quality proof.
- `tools/check_arti_rpc_path.py` passed against patched `tmp/arti-rpc/arti` and
  saved `results/arti-rpc-path-20260607T134227/arti-rpc-path.json`.
- That patched RPC plus C Tor directory result proves 3 sampled live paths had
  3 hops, a guard first hop, required relay flags, an exit last hop, no relay ID
  reuse, no relay-family overlap, and no same IPv4 `/16`.
- Two-run warm-cache browser compare saved
  `results/browser-compare-20260607T050816/browser-compare.json`. Arti boot was
  fast at `0.350s`, but Arti page load was still slower than both C Tor paths.
- Adding a 12 second post-boot wait saved
  `results/browser-compare-20260607T051124/browser-compare.json`. Arti improved,
  but still lost on page load, so preemptive readiness is only part of the issue.
- The 1 second preemptive recheck patch saved
  `results/browser-compare-20260607T052016/browser-compare.json`. Arti improved
  again and came close to bundled Tor, but still lost to bundled Tor and local C
  Tor on page load.
- The latest trusted patched 5-run browser compare saved
  `results/browser-compare-20260607T055802/browser-compare.json`. The C Tor
  SOCKS ports used `IsolateSOCKSAuth`. Arti still lost on page-only load, but
  won launch-to-load because measured warm-cache Arti boot was `0.354s`.
- The current exit-spread 5-run browser compare saved
  `results/browser-compare-20260607T085332/browser-compare.json`. Arti beat
  bundled C Tor page-only load on both targets and won boot+load on both
  targets, but still lost page-only load to local C Tor on both targets. The
  analyzer phase-delta view shows the main local C Tor gap is first response,
  not later DOM/resource phases.
- Raising Arti `min_exit_circs_for_port` from `2` to `3` saved
  `results/browser-compare-20260607T090853/browser-compare.json`. It failed
  quality with one neterror connection failure and one navigation timeout, so
  that patch was reverted.
- The first-byte diagnostics saved
  `results/browser-compare-20260607T093521/browser-compare.json` and
  `results/browser-compare-20260607T094307/browser-compare.json`. They passed
  quality and showed that normal hostname SOCKS connect/reply is immediate, and
  first Tor bytes arrive before browser `responseStart`. The next gap is after
  initial Tor bytes, around TLS/HTTP response round trips and relay/resource
  timing.
- The bounded byte-timeline diagnostic saved
  `results/browser-compare-20260607T095237/browser-compare.json`. It passed
  quality and showed first encrypted server bytes at `314-326ms`, later visible
  encrypted byte events through about `950ms`, and first Tor bytes `424.128ms`
  before browser `responseStart`.
- `tools/run_browser_compare.py --byte-tap` adds a neutral local byte-timing
  tap in front of each SOCKS proxy. It saves byte counts and first real
  stream-data timing without storing payload bytes.
- The neutral byte-tap proof saved
  `results/browser-compare-20260607T100351/browser-compare.json`. It passed
  quality and showed median first stream data at `401.870ms` for Arti,
  `604.255ms` for bundled C Tor, and `644.909ms` for local C Tor.
- The 3-run normal no-tap interleaved proof saved
  `results/browser-compare-20260607T100731/browser-compare.json`. It passed
  quality and showed Arti beating both C Tor profiles on page-only load and
  boot+load for both tested pages.
- The latest accepted normal no-tap proof saved
  `results/browser-compare-20260607T101326/browser-compare.json`. It passed
  quality with 5 runs and three targets. Arti beat bundled C Tor page-only and
  boot+load on all targets, but lost page-only to local C Tor on the homepage
  and download page. The remaining safe work is later page/resource timing
  against local C Tor, not path shortening.
- The later 5-run byte-tap proof saved
  `results/browser-compare-20260607T102046/browser-compare.json`, but failed
  quality from Arti neterror failures. Do not use it as speed proof.
- The focused download-page debug diagnostic saved
  `results/browser-compare-20260607T103305/browser-compare.json`. It passed
  quality, but debug logging made Arti much slower, so it is diagnostic only.
  It showed first response was not the slow part in that run; the loss was later
  response-to-DOM, DOM-to-load, and resource relay/page-load work. Relay receive
  and stream scheduler logs did not show queue-full events or hop-level blocks.
- The retained-signal diagnostic saved
  `results/browser-compare-20260607T104652/browser-compare.json`. It passed
  quality and proved the exit-spread code path was active for normal exit
  streams: `6` exit open picks used `select_parallelism=3`, and `6` circuit
  assignments used `4` unique circuits. This is still debug evidence, not speed
  proof.
- The focused normal exit-spread A/B saved
  `results/browser-compare-20260607T105812/browser-compare.json` for override
  `1` and `results/browser-compare-20260607T110542/browser-compare.json` for
  override `3`. Both passed quality. On the download page, Arti load improved
  from `8288.334ms` with spread `1` to `4269.500ms` with spread `3`, and the
  spread run beat both C Tor profiles. This is promising one-target evidence,
  not final proof.
- The stronger same-window exit-spread A/B saved
  `results/browser-compare-20260607T111656/browser-compare.json`. It passed
  quality. The same measured proxy window included Arti spread `3`, Arti
  control `1`, bundled C Tor, and local C Tor. On the download page, spread `3`
  loaded in `3173.693ms`, control `1` loaded in `8709.136ms`, bundled C Tor
  loaded in `5105.234ms`, and local C Tor loaded in `4253.623ms`. Spread `3`
  beat control `1` in `3/3` paired runs.
- The later 5-run, 3-target same-window A/B with bundled C Tor included saved
  `results/browser-compare-20260607T112445/browser-compare.json`, but failed
  quality because bundled C Tor hit one homepage `netTimeout` and missed a
  screenshot. Arti width `3`, Arti width `1`, and local C Tor all succeeded,
  and the rejected diagnostic table showed width `3` slower than width `1` on
  all three target medians.
- The accepted 5-run, 3-target same-window A/B saved
  `results/browser-compare-20260607T113402/browser-compare.json`. It used
  `--skip-bundled-tor` and passed quality. Width `3` was slower than width `1`
  on all three target medians, with paired load deltas of `+965.497ms`,
  `+369.719ms`, and `+3146.486ms`. Width `1` is now the default, and wider
  values stay lab-only.
- The fresh no-override default-width proof saved
  `results/browser-compare-20260607T115225/browser-compare.json`. It passed
  quality and recorded `source_tweaks.arti_exit_select_parallelism = 1` with no
  Arti exit-select override. Arti still lost page-only load to local C Tor on
  all three targets, so the next source work should target resource/page phase
  behavior at width `1`, not wider exit selection.
- The focused default-width homepage debug proof saved
  `results/browser-compare-20260607T120157/browser-compare.json`. It passed
  quality as diagnostic evidence. SOCKS setup was immediate, relay receive had
  no queue-full events, stream scheduling had no blocked hops, but resource
  DATA was concentrated on `Circ 0.0`. This points to bounded ready exit
  capacity for resource bursts as the next source area to inspect.
- The runner-only preemptive count proof saved
  `results/browser-compare-20260607T120836/browser-compare.json`. It passed
  quality and kept source default `min_exit_circs_for_port = 2`, but the lab
  override `3` made homepage median load much slower: Arti `13434.135ms` versus
  local C Tor `3642.484ms`. Do not use count `3` as the next source patch.
- The homepage resource-shape proof saved
  `results/browser-compare-20260607T121622/browser-compare.json`. It passed
  quality and showed both Arti and local C Tor used one resource origin and
  mostly HTTP/1.1. Arti was not behind at first response, but lost in
  response-to-DOM, DOM-to-load, request-start span, and same-origin resource
  tails. The next source inspection should focus on stream/resource pacing, not
  browser protocol differences or more preemptive circuits.
- The homepage byte-tap proof saved
  `results/browser-compare-20260607T122018/browser-compare.json`. It passed
  quality as diagnostic evidence. With the same tap in front of both proxies,
  Arti had faster median first stream data and won page-only load, while normal
  no-tap proof still had Arti slower. This points source inspection after first
  bytes arrive: relay stream pacing, circuit receive pacing, and browser request
  pacing.
- The analyzer now groups byte-tap connections by browser run. That makes the
  next source target more specific: add normal no-tap Arti evidence for
  per-stream data spans and gaps, then compare it with browser load and resource
  tails.
- The analyzer now also maps browser resources to nearest byte-tap connections
  when tap data is present. A replay of the passing `20260607T100351` tap proof
  mapped several slow homepage resources to the same high-confidence tap
  connection. The download-page tap proof saved
  `results/browser-compare-20260607T173526/browser-compare.json` passed quality
  and showed the same shape on the focused `500ms` profile: slow HTTP/1.1
  resources grouped on a few local TCP tap connections. The strongest groups
  are now visible in `Browser Resource Byte Tap Connection Groups`: run 2
  connection `21` had `8/8` slow high-confidence rows, median slow
  fetch-to-request `891.685ms`, median slow wait `1325.027ms`, and max data gap
  `292.436ms`; run 1 connection `4` had `4/4` slow high-confidence rows. Run 1
  connection `7` had `18` slow nearest rows and a `905.816ms` max data gap, but
  most were low-confidence nearest matches. Use this table to pick the next
  exact stream/resource pacing proof.
- `tools/run_browser_compare.py` now saves per-run proxy signal lines and
  per-run relay context lines during interleaved runs. This fixes the
  middle-run evidence gap where a clean byte-tap group existed but the matching
  Arti relay rows were lost before final proxy tail capture.
- The analyzer now also prints `Browser Resource Byte Tap Groups With Relay
  Context`. The proof saved
  `results/browser-compare-20260607T175344/browser-compare.json` passed quality
  and used that table to tie `arti_release_browser_pending500ms` run `2`, tap
  connection `18`, to timing id `19`, circuit `Circ 3.5 (Tunnel 18)`, stream
  `11369`, with `9/9` slow tap rows and `9/9` relay joins high confidence. The
  matching stream receiver context had reads and a successful SENDME during the
  max `476ms` relay gap, so the next code inspection should focus on
  browser-facing stream pacing/write/flush behavior, not a simple SENDME stall.
- The no-tap relay receive proof saved
  `results/browser-compare-20260607T123004/browser-compare.json`. It passed
  quality as debug evidence and showed Arti's slow no-tap page load has internal
  relay receive spans and a `4000ms` receive gap in one run. That older file
  used coarse timestamps and led to the high-resolution follow-up below.
- The high-resolution no-tap relay receive proof saved
  `results/browser-compare-20260607T124126/browser-compare.json`. It passed
  quality as debug evidence after rebuilding Arti with millisecond relay
  receive `event_epoch_ms` fields. Arti was much slower in that debug run, but
  the bottleneck fact is useful: the slow run had a real `3730ms` max receive
  gap and a `26563ms` internal receive span. The next code area is now
  request/resource to Arti stream correlation, not another broad speed patch.
- The SOCKS-to-relay join proof saved
  `results/browser-compare-20260607T125446/browser-compare.json`. It passed
  quality as debug evidence and proved SOCKS `timing_id` can now be joined to
  exact Arti circuit and stream ids, then to relay receive spans and gaps. The
  analyzer now groups those joined streams by browser run too, maps browser
  resource URLs to the nearest joined stream by connection timing, and summarizes
  those resource-to-relay matches by profile and target. This run was not the
  slow Arti tail case; next evidence should capture a slow run with these
  tables.
- The post-timeout-retry proof saved
  `results/browser-compare-20260607T132404/browser-compare.json`. It passed the
  normal 5-run, 3-target browser gate after `socks.rs` added one retry for
  `ErrorKind::TorNetworkTimeout` from `connect_with_prefs`. The prior
  `20260607T131326` full gate failed on an Arti homepage `about:neterror` after
  Arti logged tunnel-attempt timeouts. The analyzer now parses debug retry
  events for future timeout evidence.
- The repeat post-timeout-retry proof saved
  `results/browser-compare-20260607T133349/browser-compare.json`. It also
  passed quality. Arti won median page-only load on the homepage and download
  page, but `check.torproject.org` stayed mixed and slightly slower by paired
  load median.
- The navigation-to-SOCKS diagnostic saved
  `results/browser-compare-20260607T135113/browser-compare.json`. It passed
  quality under debug logging and added `Browser Navigation To SOCKS Join
  (nearest)`, so main document response-start can be matched to the exact Arti
  SOCKS stream. The key outlier was homepage run 2: `connect_ms=49891ms`, then
  only `288.348ms` from first Tor byte to browser response.
- The non-onion CONNECT soft-timeout lab saved
  `results/browser-compare-20260607T140722/browser-compare.json`. It passed
  quality with `--arti-socks-connect-soft-timeout-ms 5000`, but the analyzer
  found `0` soft timeouts. This proves the lab wiring did not break quality in
  that sample; it does not prove a speed win.
- The same-window soft-timeout A/B saved
  `results/browser-compare-20260607T141652/browser-compare.json`. It passed
  quality with baseline Arti plus `--extra-arti-socks-connect-soft-timeout-ms
  1500`, but again found `0` soft timeouts. The soft profile had a bad
  `81790.668ms` page-load tail with a `60430ms` relay receive gap, so the next
  useful source area is relay/resource tail behavior.
- The analyzer now prints relay gap edge tables. For `20260607T141652`, the
  decisive joined-stream edge is timing id `20`, hostname stream `54447` on
  `Circ 0.11 (Tunnel 17)`: `60430ms` between `DATA` cells, with the next event
  showing `queued_before=0`. That narrows the next source probe to SENDME,
  stream/circuit window, or congestion state, not the local output queue.
- The stream receiver diagnostic saved
  `results/browser-compare-20260607T144256/browser-compare.json`. It passed
  quality and proved the new receiver read/SENDME analyzer tables work. It did
  not reproduce the long tail: max joined stream gap was `665ms`, with receiver
  reads visible inside the smaller gaps and no SENDMEs due inside them.
- The pending-exit wait proof saved
  `results/browser-compare-20260607T144921/browser-compare.json`. It passed
  quality and reproduced a bad Arti tail: timing id `42` waited `43414ms`
  before SOCKS reply while circuit selection waited on one pending exit circuit
  and later launched a new build. Joined page streams only had `486ms` max
  receive gap, so this points to pending exit circuit wait.
- The first pending-hedge A/B saved
  `results/browser-compare-20260607T150149/browser-compare.json`. It failed
  quality on the hedge profile run 5 with Firefox `netTimeout`, and the analyzer
  saw `0` pending hedge events. This means the code is wired but not proven by
  that run.
- The timer-capable pending-hedge proofs saved
  `results/browser-compare-20260607T151858/browser-compare.json` and
  `results/browser-compare-20260607T152131/browser-compare.json`. Both passed
  quality with a `500ms` hedge profile, but both still had `0` pending hedge
  launches. The hedge profile was slower than baseline Arti in both runs, so it
  remains lab-only and unproven.
- `upstream/arti/crates/tor-proto/src/circuit/reactor/stream.rs` now logs
  `torfast stream reactor congestion blocked` when ready stream data is waiting
  but the generic stream reactor cannot send because `can_send()` is false.
  `results/browser-compare-20260607T153223/browser-compare.json` passed quality
  and counted `0` of these events, with `0` stream-scheduler hop blocks. That
  rules out this generic congestion gate for that homepage proof, so the next
  source search should stay on relay/resource tail timing and circuit assignment
  shape.
- `tools/analyze_browser_compare.py` now prints `Torfast SOCKS Relay Circuit
  Shape` from existing SOCKS-to-relay joins. In `20260607T153223`, the slow run
  concentrated `9` hostname streams and `1253594` data bytes on
  `Circ 1.4 (Tunnel 13)`, with a `5196ms` max receive span. This led to
  load-aware selection among already eligible open circuits, not changing path
  rules or building more circuits.
- `upstream/arti/crates/tor-circmgr/src/mgr.rs` now has a default-off
  `TORFAST_EXIT_SELECT_LOAD_AWARE` lab mode. It tracks assigned exit streams
  per open circuit and chooses the least-assigned circuit among already eligible
  open exit circuits. It does not change path eligibility, isolation, or circuit
  building.
- The same file now has a default-off
  `TORFAST_EXIT_SELECT_HEALTH_AWARE` lab mode. It only runs when load-aware mode
  is on for an exit request. It scores already eligible candidates from observed
  incoming RELAY DATA cells, bytes, first-to-last DATA span, max DATA gap, and
  the age of the latest DATA cell. This is not a default change.
- The same file now has a default-off
  `TORFAST_EXIT_SELECT_MAX_ASSIGNED_STREAMS` lab mode. It only runs when
  load-aware exit selection is enabled and caps assigned streams after normal
  selection, moving only among already eligible open circuits.
- `tools/run_browser_compare.py` can run the load-aware A/B with
  `--arti-exit-select-load-aware` or
  `--extra-arti-exit-select-load-aware`. The first proof saved
  `results/browser-compare-20260607T154907/browser-compare.json`. It passed
  quality: baseline Arti median load was `6207.200ms`, load-aware Arti was
  `3449.575ms`, and local C Tor was `3455.741ms`. The analyzer counted `26`
  load-aware exit picks for the extra profile.
- It can run the health-aware same-window profile with
  `--extra-arti-exit-select-health-aware`; the profile is named
  `arti_release_browser_healthaware`.
- It can run same-window health-aware threshold profiles with
  `--extra-arti-exit-select-health-min-move-score-bps`; those profiles are named
  `arti_release_browser_healthaware_min{score}bps`.
- It can run same-window health-aware threshold plus assigned-cap profiles with
  `--extra-arti-exit-select-health-min-move-score-assigned-cap` using
  `SCORE:CAP`; those profiles are named
  `arti_release_browser_healthaware_min{score}bps_assignedcap{cap}`.
- It can run same-window health-aware threshold plus same-isolation pending-wait
  profiles with `--extra-arti-exit-select-health-min-move-score-same-isolation-pending-wait`
  using `TARGET:SCORE:WAIT_MS`; those profiles are named
  `arti_release_browser_healthaware_min{score}bps_sameiso{target}_wait{wait}ms`.
- It can run same-window health-aware plus minimum-assignment-spread profiles
  with `--extra-arti-exit-select-health-aware-min-assignment-spread`; those
  profiles are named `arti_release_browser_healthaware_spread{spread}`.
- It can also run the health-aware bad-health-guard same-window profile with
  `--extra-arti-exit-select-health-aware-avoid-bad-health`, and the combined
  health-aware bad-health-guard plus same-isolation profile with
  `--extra-arti-exit-select-health-aware-avoid-bad-health-same-isolation-target`.
- The first health-aware proof saved
  `results/browser-compare-20260607T225227/browser-compare.json`. It passed
  quality. Health-aware beat base Arti by `1548.366ms` median load and changed
  `12` assignment-only choices, but it was `63.886ms` slower than plain
  load-aware and `1600.430ms` slower than local C Tor.
- The stale-score guard proof saved
  `results/browser-compare-20260607T231745/browser-compare.json`. It passed
  quality. Health-aware median load was `5011.993ms` versus base Arti
  `6931.042ms`, plain load-aware `5716.333ms`, and local C Tor `6638.935ms`.
  Health-aware changed `4` assignment-only choices and kept assignment `12`
  times.
- The broader health-aware gate saved
  `results/browser-compare-20260607T232339/browser-compare.json`. It passed
  quality across check, homepage, and download with 3 runs per target.
  Health-aware beat base Arti and plain load-aware on all three target medians.
  Against local C Tor, paired median page load was basically tied on check,
  `68.302ms` slower on the homepage, and `480.184ms` faster on download. It
  stays lab-only because this is still a small debug gate.
- The larger low-log health-aware gate saved
  `results/browser-compare-20260607T233909/browser-compare.json`. It failed
  quality: health-aware download run 3 hit browser `about:neterror` connection
  failure after `61518.070ms` elapsed and had no screenshot proof. The accepted
  health-aware download median was `11170.564ms`, slower than base Arti,
  plain load-aware Arti, and local C Tor. Do not promote health-aware from the
  debug proof.
- `tools/run_browser_compare.py` now retains failed-run evidence in compact
  output: failed browser profile/home directories stay, and failed runs keep a
  per-run proxy output tail even if there are no `torfast` signal lines.
- `tools/run_browser_compare.py` also has a default-off
  `--proxy-run-tail-lines` option to retain ordinary proxy tail lines after
  successful interleaved runs.
- The focused retained-runner proof saved
  `results/browser-compare-20260607T235651/browser-compare.json`. It passed
  quality on the download page, but health-aware median load was
  `16524.629ms`, slower than base Arti `5592.204ms`, plain load-aware
  `6362.165ms`, and local C Tor `4207.812ms`.
- The retained-tail proof saved
  `results/browser-compare-20260608T000334/browser-compare.json`. It passed
  quality and proved `--proxy-run-tail-lines 120` records per-run proxy tails,
  but low-log Arti only emitted those lines on first runs. Health-aware median
  load was `6026.292ms`, base Arti `7587.330ms`, plain load-aware
  `5446.530ms`, and local C Tor `5101.879ms`.
- The debug retained-tail proof saved
  `results/browser-compare-20260608T000956/browser-compare.json`. It passed
  quality, but rejected the current health-aware and plain load-aware selector
  shape in this window. Base Arti median load was `3752.832ms`, local C Tor was
  `5800.624ms`, health-aware was `18465.459ms`, and plain load-aware was
  `12139.927ms`. The analyzer tied the loss to long relay/resource tails after
  first response, not browser connection prefs.
- The selector now logs candidate health as
  `index:circuit:cells:bytes:max_gap_ms:score:span_ms:age_ms`, and the analyzer
  remains compatible with the old shorter format. `20260608T002242` proved the
  new fields work and showed default health-aware can select zero-score cold
  circuits. `TORFAST_EXIT_SELECT_HEALTH_MIN_MOVE_SCORE_BPS` is a lab-only
  threshold knob that keeps the old default `65536`; `20260608T002719` tested
  `16000`, changed the choice pattern, but still lost to base Arti and kept
  slow-relay tails.
- The first same-window threshold-profile check saved
  `results/browser-compare-20260608T014735/browser-compare.json`. It failed
  quality because base Arti hit an `about:neterror` timeout on run `2` after
  `61265.920ms`, so it is not speed proof. It still rejects `32768`: median load
  was `13738.993ms` and the selector outcome table showed low-rate and
  slow-relay selected circuits. The `131072` profile was stable but slower than
  default health-aware and local C Tor in this window.
- `tools/analyze_browser_compare.py` now prints
  `Browser Failed Run Torfast SOCKS Streams` after `Browser Failed Runs`. It
  parses failed-run `proxy_signal_lines`, `proxy_relay_context_lines`, and
  `proxy_output_tail`, then lists slow SOCKS streams from that failed run only.
  It now includes last Tor-to-browser byte timing and idle time after that last
  byte for new debug logs.
  The main `Torfast SOCKS Timings` and target-kind tables now also print median
  last Tor byte and idle-after-last-byte fields.
  On `20260608T014735`, it surfaced the base Arti timeout streams directly:
  timing ids `11` and `12` were hostname relay waits of `60167ms` and
  `59810ms`, and timing id `13` was an onion stream with `3179ms` connect plus
  `56021ms` relay.
- The last-byte diagnostic replay saved
  `results/browser-compare-20260608T020551/browser-compare.json`. It passed
  quality for 2 warm-cache download-page runs, but was not speed proof: Arti
  median load was `4129.896ms` versus local C Tor `3464.572ms`. The new SOCKS
  split showed median last Tor byte `2457.500ms`, median idle after last Tor
  byte `265.500ms`, and max idle after last Tor byte `3240.000ms`. Treat
  relay totals carefully: some long relay rows are close-wait, not active Tor
  data delay. The browser-resource-to-SOCKS join now carries last-byte and
  response-end-after-last-byte fields; for this replay the median matched
  resource ended `883.959ms` before the stream's last Tor byte, so resource
  queue timing is the next source target unless a later run proves active byte
  delay. The resource connection table now includes queued-resource counts and
  max fetch-to-request time; this replay showed Arti had `22` resources queued
  at least `1000ms` versus local C Tor `15`, with max fetch-to-request
  `2450.049ms` versus `2050.041ms`. The analyzer now prints
  `Resource Queue Delta vs Local C Tor`, which shows the same gap directly:
  `+7` HTTP/1.1 resources queued at least `1000ms` and `+400.008ms` worse max
  fetch-to-request for Arti. The analyzer now also prints
  `Resource Queue Slot Saturation`; in this replay Arti had `21/22` resources
  queued at least `1000ms` at same-origin HTTP/1.1 slot depth `>=6`, while
  local C Tor had `11/15`, and both median/max slot depths were `6`. This says
  the right source target is earlier stream/resource completion under unchanged
  Tor Browser caps. The analyzer now also prints `Resource Queue Slot Blockers`.
  In this replay, the worst Arti queued row had `5` final same-origin blockers;
  the top high-confidence blocker mapped to timing id `9` / `Circ 1.2` with
  `516.677ms` left in receive/body time, while another blocker still had
  `400.008ms` first-byte wait left. For the high-confidence blocker, Arti's
  last write was `532.677ms` after the queued request started, and browser
  response end was only `-16.000ms` from that write. The top local C Tor blocker
  row had only `100.002ms` left (`16.667ms` wait, `83.335ms` receive). The new
  relay/read comparison says timing id `9` had `0.000ms` write-after-relay and
  `0.000ms` write-after-stream-receiver-read, with max receiver queued bytes
  `3948`; source work should move earlier than SOCKS copy write. The same
  high-confidence blocker received `121523` relay bytes after the queued
  request began, from `+172.677ms` to `+532.677ms`, with max after-queue relay
  gap only `51.000ms`. Run 2's cleaner blocker rows point to timing id `18` /
  `Circ 1.5` with `366.674ms` max blocker time left. The next source probe
  should explain late circuit/stream relay bursts. Arti source now logs normal
  selector candidate assignment and health summaries at debug level without
  enabling a lab selector; use the next browser replay to see whether the late
  blockers had better open-circuit candidates. The analyzer now also prints
  `Browser Resource Queue To SOCKS Relay Tail`, sorted by fetch-to-request and
  joined to nearest SOCKS/circuit context. In this replay, top queue tail was
  `tor-logo@2x.png` on high-confidence timing id `8`, while many following
  rows were low-confidence nearest matches around timing id `9`. The companion
  high-confidence cluster table showed timing id `18` had `21` queued
  resources, timing id `8` had `11`, and timing id `9` had `4`, so use those
  clusters for the next source inspection.
- The analyzer now also prints `Browser Run Late Phase Queue Context`, which
  starts from each successful browser run's response-to-DOM and DOM-to-load
  phases, then attaches queued-resource counts, the strongest joined SOCKS
  timing id/circuit, relay gap, and selector candidate context when retained
  debug lines allow it. The debug replay `20260608T173542` used this to show
  an Arti response-to-DOM loss on timing ids `4` and `7`, `Circ 4.0 (Tunnel
  5)`, while first response was already earlier than local C Tor.
- It also prints `Arti Profile Late Queue A/B`, which compares extra Arti
  profiles against base Arti on paired late queue rows. On `20260608T174515`,
  `healthaware_spread4` improved median max queue delay but won only `1/2`
  paired queue runs, so the selector stays lab-only.
- It also prints `Arti Profile Promotion Risk Stream Receiver Context`, which
  joins risky candidate max runs to the worst retained stream receiver terminal
  row in that run.
- It also prints `Torfast Stream Receiver Not-Connected Summary`, grouped by
  profile, target, and run, so abandoned stream tails can be compared across
  base Arti and lab profiles.
- `crates/arti/src/proxy/socks.rs` now has default-off low-log SOCKS relay byte
  timing behind `TORFAST_SOCKS_RELAY_BYTE_TIMING`. The runner exposes it as
  `--arti-socks-relay-byte-timing`. The focused proof
  `results/browser-compare-20260608T182354/browser-compare.json` passed quality
  and showed browser-facing byte fields at info level. In that run, Arti lost
  page load to local C Tor (`5673.865ms` vs `4003.608ms`), but the useful
  source clue is stronger: timing id `1` idled `4805ms` after its last
  Tor-to-browser byte before `not_connected`, and timing id `2` moved `362459`
  Tor-to-browser bytes before a `not_connected` finish. Use this to inspect
  close/EOF and browser slot release behavior around stream tails.
- The follow-up byte-timing proof
  `results/browser-compare-20260608T183445/browser-compare.json` passed quality
  and was a one-run diagnostic speed win only. Arti load was `2864.382ms`
  versus local C Tor `5099.072ms`, but this is not promotion proof. All logged
  `not_connected` streams had no recorded browser EOF or Tor read-error
  timestamp (`client_to_tor_eof_ms=0`, `tor_to_client_error_ms=0`), while
  `client_to_tor_write_close_ms` matched relay finish (`2092-3318ms`). Use this
  as a reason to add better close/error proof before behavior changes.
- `CountingBufStream::poll_fill_buf` now records EOF/error timing too, because
  `copy_buf_bidirectional` uses buffered reads. The proof
  `results/browser-compare-20260608T184334/browser-compare.json` passed quality
  and showed the corrected close shape: `10` close streams, `9`
  `not_connected`, and all `9` had browser EOF plus Tor read error at the same
  close moment. The analyzer now prints `Torfast SOCKS Close Shape`; use it to
  avoid blaming local close-after-browser-done streams as direct page-load
  causes.
- `tools/analyze_browser_compare.py` now lets browser resource-to-SOCKS joins
  fall back to low-log SOCKS stream timing when debug relay-cell logs are not
  present. On `results/browser-compare-20260608T184334/browser-compare.json`,
  this restored `36` resource joins and `17` high-confidence matches. The
  clearest queued-resource clusters were timing id `9` (`4` resources queued at
  least `1000ms`) and timing id `10` (`tor-logo@2x.png` with `5600.112ms`
  fetch-to-request delay). Use these tables for the next resource queue and
  transfer-tail proof.
- `tools/analyze_browser_compare.py` also prints
  `Resource Queue Slot Release Summary`. On the same `184334` run, Arti had
  `23` queued resources at least `1000ms`, `16` at slot depth `>=6`, `23` rows
  with joined blocker stream evidence, and `13` high-confidence blocker rows;
  `15` rows were receive-dominant, `8` wait-dominant, and `9` high-confidence
  rows still had blocker writes at least `1000ms` after the queued request
  started. This is the compact table to check first before digging into the long
  blocker rows.
- The analyzer now also prints `Resource Queue Late Write Summary`. On
  `184334`, only `2` rows had positive browser release time after the final
  matched Arti write, and none were at least `500ms`. The late part is Arti
  still writing after queue start: max `4978.163ms`, top resource `fallback.js`.
  The table now joins stream receiver terminal summaries too: all `13`
  high-confidence rows had terminal coverage, median write-after-terminal-data
  was `0ms`, and max terminal pending bytes was `0`.
- `tools/analyze_browser_compare.py` now prints
  `Resource Queue Late Stream Detail`, which names the queued resource and
  blocker stream timing ids behind late terminal data. In `184334`, the worst
  rows were `fallback.js` (`4979.163ms` terminal last-data-after-queue,
  timing ids `8, 4`) and `stay-safe@3x.png`/`TBA10.0.png` (`4595.822ms`,
  timing ids `4, 8`), all on `Circ 4.1`.
- `tools/analyze_browser_compare.py` now also prints
  `Resource Queue Late Circuit Summary`. In `184334`, all `13` late queued rows
  mapped to `Circ 4.1`, which carried `7` terminal streams, `1178.332 KiB`, and
  `2505` terminal data cells.
- The selector-context replay saved
  `results/browser-compare-20260608T030643/browser-compare.json`. It passed
  quality but was still slower on page load: Arti median load was
  `4369.638ms` versus local C Tor `3669.699ms`, with paired Arti load delta
  `+699.939ms`. The queue gap also remained: Arti had `25` resources queued at
  least `1000ms` versus local C Tor `16`, and `23` of those Arti rows were at
  slot depth `>=6` versus local C Tor `8`. The analyzer now prints
  `Browser Resource Queue Selection Context`, which joins high-confidence queue
  clusters to normal selector candidate summaries. That table did not prove a
  safe selector promotion: run 1 `Circ 0.4` later had a much stronger selected
  health score than its alternatives, run 2 timing id `18` picked a cold circuit
  that did not itself look stalled, and the worst run 2 cluster had no
  multi-candidate choice. Use this as evidence to keep selector changes lab-only
  and look next at same-isolation capacity/readiness or earlier resource
  completion without browser cap changes.
- `TORFAST_EXIT_SAME_ISOLATION_TARGET` is no longer gated by
  `TORFAST_EXIT_SELECT_LOAD_AWARE`, and `tools/run_browser_compare.py
  --extra-arti-exit-same-isolation-target` now inherits the baseline selector
  instead of forcing load-aware. This lets capacity be tested alone. The first
  capacity-only target `2` replay,
  `results/browser-compare-20260608T032051/browser-compare.json`, passed
  quality but made `0` same-isolation top-ups, so it is not activation proof.
  The target `4` replay,
  `results/browser-compare-20260608T032422/browser-compare.json`, passed
  quality with load-aware still off, made `3` top-ups and `0` failures, and cut
  same-window median load to `4646.399ms` versus baseline Arti `9463.184ms`.
  It also cut the baseline max load from `14876.409ms` to `4822.725ms` and
  reduced HTTP/1.1 queue tails (`50/70` queued `>=500ms` versus `59/70`). A
  wider low-log multi-target gate then overturned that lab lead:
  `results/browser-compare-20260608T033012/browser-compare.json` passed
  quality and activated cleanly, with `9` top-ups for target `3`, `12` top-ups
  for target `4`, `0` failures, load-aware still off, and unchanged browser
  prefs. But both targets were slower than baseline Arti on check, homepage,
  and download medians. Target `4` also had a `51463.133ms` accepted homepage
  tail. Do not promote simple same-isolation capacity target `3` or `4`; next
  source work should explain why extra top-ups worsened low-log resource tails,
  or find a more selective trigger. Source now has a stricter lab floor:
  `TORFAST_EXIT_SAME_ISOLATION_MIN_ASSIGNED_STREAMS`, default `2`, and the
  analyzer prints top-up selected-stream count plus top-up floor. The
  `min=2` low-log gate in
  `results/browser-compare-20260608T034639/browser-compare.json` passed quality
  and improved target `3` download median (`3541.465ms` vs baseline
  `3992.234ms`) but still lost check/home and had a worse download max tail.
  The `min=3` focused gate in
  `results/browser-compare-20260608T035149/browser-compare.json` also passed
  quality but lost homepage and download. The lower target `2` gate in
  `results/browser-compare-20260608T035831/browser-compare.json` passed quality
  and made only `3` top-ups, but download median was much worse than baseline
  (`10049.471ms` vs `6199.955ms`). `tools/analyze_browser_compare.py` now prints
  `Arti Profile Same-Isolation Top-Up A/B`; on that run, download top-up
  attempt runs had median load `14997.160ms` vs paired baseline `14508.584ms`
  and max `19944.848ms`. Raising or lowering the simple reuse floor is not
  enough; next source work needs a different signal or a more selective trigger
  than same-isolation capacity count alone.
- The more selective health-gated target `2` proof saved
  `results/browser-compare-20260608T042223/browser-compare.json`. It passed
  quality, kept browser prefs unchanged, made `1` bad-health-required top-up
  with `0` failures, and improved paired median load by `336.149ms` on check
  and `790.623ms` on download. This is the current same-isolation lead, but it
  stays lab-only because it was only a two-target, three-run proof and the
  download max tail was worse than baseline.
- The 5-run, 3-target repeat saved
  `results/browser-compare-20260608T042918/browser-compare.json`. It passed
  quality, kept browser prefs unchanged, kept load-aware off, made `7`
  bad-health-required top-ups with `0` failures, and improved sameiso2 max-load
  tails versus baseline Arti on check, homepage, and download. Sameiso2 median
  load beat local C Tor on all three targets in this window, but homepage max
  load was still worse than local C Tor.
- The independent repeat saved
  `results/browser-compare-20260608T044143/browser-compare.json`. It also passed
  quality, but it rejected promotion: baseline Arti beat sameiso2 on all three
  summary medians, and sameiso2 had a bad accepted homepage max tail of
  `64615.774ms`. Keep health-gated sameiso2 lab-only. The next source target is
  explaining or preventing the homepage top-up tail, not promoting the knob.
- Top-up logs now include selected-circuit health detail fields
  (`selected_health_max_gap_ms`, `selected_health_score_bps`, and
  `selected_health_age_ms`), and `tools/analyze_browser_compare.py` prints those
  fields in the Torfast circuit-selection tables. This is diagnostic only.
- The first retained diagnostic with those fields is
  `results/browser-compare-20260608T045852/browser-compare.json`. Quality failed
  because baseline Arti hit a homepage `netTimeout`, so it is not speed proof.
  The sameiso2 profile itself finished `8/8`, made `3` top-ups with `0`
  failures, and showed top-up max health gap `338ms`, min score `14869`, and max
  age `37ms`. The problem looked like low-score selected circuits, not stale
  health or a large local gap.
- The existing combined lab profile (health-aware, avoid-bad-health, sameiso2,
  and bad-health-required top-up) then passed two focused homepage windows:
  `results/browser-compare-20260608T050606/browser-compare.json` and
  `results/browser-compare-20260608T051154/browser-compare.json`. In `050606`,
  candidate median load was `5531.888ms` vs baseline Arti `6743.920ms`, and it
  won paired load `5/5`. In `051154`, candidate median load was `4929.467ms` vs
  baseline Arti `8090.484ms`, and it won paired load `3/5`. Both kept browser
  prefs unchanged and made `2` top-ups with `0` failures. This is a repeated
  homepage lead only; it still needs repeated check/homepage/download proof.
- The broader check/homepage/download gate saved
  `results/browser-compare-20260608T051703/browser-compare.json`. It passed
  quality and kept browser prefs unchanged, but it rejected the combined profile
  as a promotion path. Candidate beat baseline Arti median load on check
  (`1600.279ms` vs `1726.238ms`) and homepage (`4776.506ms` vs `6299.856ms`),
  but lost download (`13857.582ms` vs `5314.784ms`) with a much worse max tail
  (`66948.318ms` vs `12564.660ms`). Same-isolation top-up A/B ties the loss to
  download top-up attempts: attempt median load delta was `+7549.335ms`, and
  attempt wins were `0/4`.
- The focused download isolation saved
  `results/browser-compare-20260608T052735/browser-compare.json`. It compared
  baseline Arti, health-aware avoid-bad-health without top-up, and the same
  profile with sameiso2. Quality passed and browser prefs stayed unchanged.
  Baseline Arti median load was `4973.318ms`; health-aware avoid-bad-health lost
  at `6279.622ms` with a `61523.104ms` max tail; sameiso2 lost worse at
  `13245.888ms`. Sameiso2 top-up attempt runs won `0/3` and lost by
  `+9336.977ms` median load. This narrows the next source step away from simple
  same-isolation count gates.
- The focused debug replay saved
  `results/browser-compare-20260608T053529/browser-compare.json`. It passed
  quality, but is debug evidence only. Health-aware avoid-bad-health without
  top-up beat baseline Arti in this small window (`4462.620ms` vs `5278.454ms`
  median load), while sameiso2 was slower (`5720.123ms`). Sameiso2 made `1`
  top-up with `0` failures; the top-up-attempt run lost by `+3929.443ms`, while
  no-attempt sameiso2 runs were faster by `-1836.445ms`. Source now logs a
  top-up `pending_id`, and build complete/failed/canceled circuit-selection
  events; the analyzer counts those lifecycle fields in the circuit-selection
  tables.
- The follow-up debug replay saved
  `results/browser-compare-20260608T054800/browser-compare.json`. It failed
  quality because baseline Arti and local C Tor each had a failed download run,
  so it is not speed proof. Sameiso2 itself finished `5/5`, made `3` top-ups
  with `0` top-up failures, and reported `18` build-complete, `1`
  build-failed, and `0` build-canceled events. Per-run lifecycle matching shows
  top-ups built `Circ 1.6`, `Circ 1.8`, and `Circ 1.9` in `540ms`, `538ms`,
  and `462ms`; only `Circ 1.9` was later selected by page traffic. This says
  the debug fields work and top-up builds were not late in this sample.
  `tools/analyze_browser_compare.py` now prints a
  `Torfast Same-Isolation Top-Up Lifecycle` table so this built-versus-used
  split is visible without manual log parsing. The table now also reports page
  load time left after build, later open picks, later stream links, and whether
  the built circuit appeared as a skipped candidate. In run `3`, built `Circ
  1.6` was a candidate, but the selector chose `Circ 1.5` with a much stronger
  recent health score (`185759` vs `0`).
- Local Arti source now has `TORFAST_EXIT_SELECT_PREFER_COLD_SAME_ISOLATION`,
  a default-off lab rule inside health-aware same-isolation selection. It leaves
  default Tor behavior unchanged, keeps the same isolation and eligible-circuit
  filters, and only prevents a busy hot circuit from overriding a cold
  least-assigned candidate when same-isolation top-up mode is active. The
  browser runner exposes it through
  `--extra-arti-exit-select-prefer-cold-same-isolation-target`.
- The first focused prefer-cold replay is
  `results/browser-compare-20260608T061926/browser-compare.json`. It passed
  quality and showed prefer-cold sameiso2 beating baseline Arti on the download
  page in all `3` paired loads (`3488.752ms` versus `7508.323ms` median load),
  with lower max load too (`4946.213ms` versus `12413.143ms`). Keep this as
  diagnostic evidence only until a wider same-window gate passes.
- The wider same-window gate is
  `results/browser-compare-20260608T062521/browser-compare.json`. It passed
  quality but rejected prefer-cold promotion: check and homepage were slower
  than baseline Arti, and download was only a tiny summary-median win with a
  worse paired median. Keep the flag lab-only.
- `tools/run_browser_compare.py` also exposes
  `--extra-arti-exit-select-health-aware-same-isolation-prefer-cold-target`,
  which creates `arti_release_browser_healthaware_sameisoN_prefercold` without
  the avoid-bad-health guard. The same-window proof
  `results/browser-compare-20260608T063525/browser-compare.json` rejected that
  no-guard variant: download median load regressed to `12824.702ms` versus
  baseline Arti `6549.739ms`.
- `tools/analyze_browser_compare.py` now prints `Arti Profile A/B` for any
  extra `arti_release_browser_*` profile. This direct baseline table shows
  paired phase/load deltas, summary median deltas, and max-load tail deltas. It
  also prints direct resource type, top-resource, load-tail, HTTP-phase, HTTP
  queue-shape, and top-resource relay-context A/B tables for the same
  baseline/candidate pair.
- `tools/analyze_browser_compare.py` now also prints
  `Arti Profile Promotion Risks`. It uses the direct A/B rows to block
  candidate/target promotion when paired median is slower, summary median is
  slower, max load tail is worse, or paired wins are too low. This prevents a
  median-only read from hiding accepted tail regressions like the guarded
  prefer-cold check-page tail in
  `results/browser-compare-20260608T063525/browser-compare.json`.
- `tools/analyze_browser_compare.py` now also prints
  `Arti Profile Promotion Risk Max Runs`, with the worst candidate run, phase
  hint, navigation connect time, response/DOM phases, and slowest resource. The
  `063525` guarded prefer-cold check tail is identified as nav connect/TLS
  (`20583.745ms`), not a slow resource.
- `tools/analyze_browser_compare.py` now also prints
  `Arti Profile Promotion Risk SOCKS Context` when a risky max run can be
  matched to a Tor SOCKS stream. It joins the max-risk browser run to timing id,
  SOCKS connect/reply, first Tor byte, response-after-reply, circuit, stream,
  relay time, data bytes, and max receive gap. On
  `results/browser-compare-20260608T065456/browser-compare.json`, this showed
  guarded prefer-cold run `5` had fast SOCKS connect/reply (`0ms`/`0ms`) but a
  long relay span (`5394ms`) and receive gap (`2901ms`), so that replay points
  at relay/response-to-DOM tails instead of SOCKS connect.
- Local Arti source now also has
  `TORFAST_EXIT_SELECT_AVOID_BAD_HEALTH_UNKNOWN_FALLBACK`, a default-off lab
  extension to the bad-health guard. It lets a cold/unknown eligible open
  circuit beat a known-bad least-used circuit when no clearly good candidate is
  available. `tools/run_browser_compare.py` exposes it with
  `--arti-exit-select-avoid-bad-health-unknown-fallback` and the same-window
  profile flag
  `--extra-arti-exit-select-avoid-bad-health-unknown-fallback-prefer-cold-same-isolation-target`.
  The analyzer's circuit-selection tables now include `unknown fallback open
  picks` so debug logs show when this lab guard was active. After
  `results/browser-compare-20260608T122133/browser-compare.json` showed repeated
  unknown fallback could pile streams onto unproven circuits, source tightened
  the fallback to unassigned unknown candidates only.
- `results/browser-compare-20260608T122133/browser-compare.json` tested that
  unknown-fallback profile against baseline Arti and guarded prefer-cold. It
  passed quality and beat baseline Arti median load on check, homepage, and
  download, but it is not promotable because promotion-risk rows show much
  worse accepted max tails: homepage `61500.660ms` versus baseline `5954.526ms`,
  and download `17385.026ms` versus baseline `5909.866ms`. The run counted `43`
  unknown fallback open picks and `0` top-up failures.
- `results/browser-compare-20260608T123655/browser-compare.json` reran after
  the unassigned-only fallback tightening. It failed quality because the
  unknown-fallback profile timed out on download run `2` after `91876.956ms`
  with no screenshot proof. The failed-run SOCKS table showed long relay waits:
  hostname timing id `35` had relay `89332ms`, and onion timing id `37` had
  relay `83919ms`.
- `results/browser-compare-20260608T124751/browser-compare.json` tested the
  focused download page with global `--arti-socks-connect-soft-timeout-ms 5000`
  plus the same guarded prefer-cold and unknown-fallback profiles. It failed
  quality because guarded prefer-cold download run `2` hit
  `about:neterror?e=netTimeout` after `61452.374ms`. Failed-run SOCKS rows still
  showed the bad wait shape: onion CONNECT `63268ms`, hostname relay `60342ms`
  and `59851ms`, plus onion relay `55869ms`. Soft timeout is not enough proof or
  a fix for relay-after-reply and onion waits.
- `tools/analyze_browser_compare.py` now also prints `Browser Failed Runs` when
  quality fails. It includes profile, target, run, elapsed time, timeout state,
  screenshot state, proxy-tail line count, last proxy line, and compact browser
  error text.
- `tools/analyze_browser_compare.py` now also prints `Browser Failed Run Cause
  Summary` before the raw failed-run rows. It buckets failed runs into connect
  waits, relay-after-reply tails, mixed failures, and browser proof failures, and
  reports soft-timeout and retry counts. On `124751`, it shows mixed connect and
  relay-tail failure with `0` soft timeouts, so the next fix should not be only
  another non-onion SOCKS timeout.
- That cause summary now splits relay tails into no-byte tails and partial-byte
  idle tails. On `124751`, the bad run had `2` relay tails with Tor bytes then
  idle and `1` relay tail with no Tor bytes. This makes a browser-visible
  post-SOCKS-reply failure class explicit.
- `tools/analyze_browser_compare.py` now also prints `Browser Failed Run
  Relay-Tail Details`. It joins failed-run SOCKS relay tails to relay receive
  context when possible and keeps unjoined tails visible. On `124751`, timing
  ids `10` and `12` had joined stream/circuit context and small max receive gaps
  (`230ms` and `679ms`) before long idle-after-last-byte tails. Timing id `11`
  had no Tor bytes.
- `crates/arti/src/proxy/socks.rs` now includes the SOCKS relay copy error kind
  and token in the relay-finished diagnostic, and
  `crates/tor-proto/src/client/stream/data.rs` now logs stream-reader terminal
  state with circuit, hop, stream, byte, cell, pending, and EOF context.
  `tools/analyze_browser_compare.py` parses those fields into the relay-tail
  detail table. Old runs such as `124751` leave the new columns blank.
- The same SOCKS file now emits bounded info-level `torfast socks timing`
  summaries for slow connects and slow or failed relay streams. This lets
  low-log browser gates keep enough SOCKS cause evidence without enabling full
  debug logs. `results/browser-compare-20260608T142558/browser-compare.json`
  proved the rows are retained at run level and parsed by the analyzer's SOCKS
  timing and notable-stream tables. It is diagnostic proof only, not a speed
  claim.
- `crates/arti/src/proxy/socks.rs` now also has
  `TORFAST_SOCKS_CONNECT_SOFT_TIMEOUT_ATTEMPTS`, a bounded lab-only attempt
  count for non-onion soft-timeout retries. The default remains `2`, valid lab
  values are `1..4`, and onion streams keep the old retry count. The repeated
  wide gate `results/browser-compare-20260608T143029/browser-compare.json`
  used the new low-log summaries to show the latest accepted download tail was
  a `60699ms` hostname CONNECT after the first `5000ms` soft timeout. The
  focused attempts-`3` replay
  `results/browser-compare-20260608T144556/browser-compare.json` passed quality
  but was slower by median load, so this is only a test knob.
- `tools/run_browser_compare.py` can now add same-window attempt-count A/B
  profiles with `--extra-arti-socks-connect-soft-timeout-attempts`. The focused
  download proof `results/browser-compare-20260608T145305/browser-compare.json`
  passed quality and attempts-`3` won `3/3` paired loads (`3786.624ms` median
  load vs baseline Arti `11503.625ms`), but it is one-target narrow proof and
  must not be promoted by itself.
- The wider attempts-`3` proof
  `results/browser-compare-20260608T145856/browser-compare.json` passed quality
  and improved medians on check, homepage, and download, but the analyzer
  rejected promotion because max tails worsened on check and homepage. The
  homepage tail was a `60451ms` final CONNECT after two `5000ms` soft timeouts.
  The focused attempts-`4` homepage follow-up
  `results/browser-compare-20260608T150858/browser-compare.json` passed quality
  and had a lower max tail, but it was slower by median and won only `1/5`
  paired loads. Keep this as lab evidence, not a default.
- `tools/analyze_browser_compare.py` now prints the SOCKS retry attempt cap and
  per-attempt trace. On `20260608T145856`, the bad attempts-`3` rows show
  two short soft timeouts followed by a normal final attempt that waited about
  `50s`, so the next useful work is not simply raising the attempt count.
- `crates/arti-client/src/client.rs` now emits low-log normal exit-client phase
  timing for slow or failed exits: `tunnel ready` and `begin stream finished`.
  `tools/analyze_browser_compare.py` prints this as `Torfast Exit Client
  Timings`. The proof run
  `results/browser-compare-20260608T152416/browser-compare.json` passed quality
  and showed tunnel acquisition at `4467ms` and BEGIN phase at `1ms`, while
  SOCKS relay tails reached `38465ms`.
- `crates/tor-proto/src/client/stream/data.rs` now emits low-log stream
  receiver terminal summaries for slow or non-clean reader endings. The proof
  run `results/browser-compare-20260608T153828/browser-compare.json` passed
  quality and captured `9` summaries with max transfer `3450ms`, max data gap
  `465ms`, and max idle after last data `3012ms`.
- The wider low-log run
  `results/browser-compare-20260608T154415/browser-compare.json` passed quality
  and beat local C Tor by median page load on check and homepage, but it also
  exposed a `62261.348ms` accepted check-page load. The retained logs tied the
  tail to a `60042ms` exit tunnel-ready failure followed by a successful retry,
  not to a slow stream transfer after data started.
- The split soft-timeout A/B
  `results/browser-compare-20260608T154736/browser-compare.json` is a harness
  caveat: `soft5000ms` and `softattempts3` were two separate profiles, not a
  combined `5000ms + 3 attempts` profile. `soft5000ms` was rejected on speed.
- The corrected combined A/B
  `results/browser-compare-20260608T155501/browser-compare.json` passed quality
  and showed `arti_release_browser_soft5000ms_attempts3` beating baseline Arti
  on the focused check-page run, but it remains lab-only because it is one
  target and three runs.
- The wider combined A/B
  `results/browser-compare-20260608T160018/browser-compare.json` passed browser
  quality but rejected promotion. The combo improved check and homepage median
  load against baseline Arti, but homepage max tail got worse and download
  median load was slower than baseline Arti. It also still lost to local C Tor
  by median page load on check and download.
- `tools/analyze_browser_compare.py` now prints
  `Torfast Stream Receiver Terminal Top Streams`, listing the worst terminal
  stream summaries by target, run, load, stream id, circuit id, transfer, data
	gap, idle time, and first-data wait. This keeps slow stream ids visible in
	low-log gates. On `20260608T160018`, the rejected combo tail was split across
	homepage run `3` and download run `3`, with idle-after-data rows on circuits
	`3.15` and `3.20` and long-transfer/data-gap rows on circuits `3.16` and
	`3.21`.
- `upstream/arti/crates/tor-proto/src/stream/raw.rs` now logs
  `torfast stream receiver no-end close` when the raw stream receiver closes
  without an END cell and returns `not_connected`. The analyzer parses those
  rows, joins them to terminal stream rows, and shows `no-END closes` in
  `Torfast Stream Receiver Terminal Top Streams` and `Arti Selected-Circuit
  Network Evidence`. Use this after rebuilding Arti to prove whether partial
  DATA idle failures are stream receiver no-END closes on the same stream.
- `crates/arti/src/proxy/socks.rs` now also includes `circ_id`, `hop`, and
  `stream_id` on `torfast socks timing relay finished` rows. The analyzer
  copies those fields from relay-finished events too, so retained info-level
  runs can join stream receiver terminal summaries to SOCKS timing ids even
  when an earlier `stream linked` row fell out of the bounded tail.
- `crates/arti-client/src/client.rs` now includes `tunnel_unique_id` on
  low-log exit-client tunnel-ready and begin-stream timing rows.
  `crates/tor-circmgr/src/mgr.rs` also keeps tunnel build complete, failed, and
  canceled rows at info level once pending age reaches `5000ms`. The analyzer
  prints `Torfast Exit Client Slow Tunnels` when a retained run has slow
  tunnel-ready rows.
- `crates/tor-circmgr/src/mgr.rs` now has
  `TORFAST_EXIT_SELECT_BAD_HEALTH_HEDGE_MS`, a default-off bounded lab hedge
  behind bad-health avoidance. It keeps the same usage and isolation, opens at
  most one replacement for a locally bad open exit circuit, and falls back to
  the original valid circuit after the short timer. The first hedge proof
  `results/browser-compare-20260608T135745/browser-compare.json` was rejected
  and exposed a pending-count bug. The fixed focused replay
  `results/browser-compare-20260608T140400/browser-compare.json` beat baseline
  Arti on the homepage, but the wider
  `results/browser-compare-20260608T140711/browser-compare.json` gate failed
  quality on check and kept a huge accepted homepage tail, so the hedge is not
  promotable.
- `tools/analyze_browser_compare.py` now also prints `Browser Run Proxy Tails`
  when any run has a per-run `proxy_output_tail`.
- `tools/analyze_browser_compare.py` now also prints `Torfast SOCKS Connect
  Retries` plus target-kind max CONNECT and slow-connect counts. This exposes
  soft timeout, retry, and `TorNetworkTimeout` events directly instead of
  burying them in proxy tails.
- The wider load-aware proof saved
  `results/browser-compare-20260607T155934/browser-compare.json`. It passed
  quality and improved median load versus baseline Arti on all three targets:
  `1780.184ms` vs `1887.842ms`, `4232.771ms` vs `9061.474ms`, and
  `6000.187ms` vs `8937.480ms`. It is still lab-only because the load-aware
  download-page max load was `65953.543ms` versus baseline `11525.708ms`.
- Inspecting that bad load-aware download tail found a slow CONNECT retry shape:
  timing id `35` waited about `60027ms`, returned `TorNetworkTimeout`, then
  retried and connected in `746ms`. Arti had no eligible open circuit at that
  point, so the failure points to isolated exit-circuit readiness or retry
  timing, not to the open-circuit load-aware picker.
- The focused follow-up saved
  `results/browser-compare-20260607T161639/browser-compare.json`. It ran
  load-aware baseline Arti against load-aware plus
  `--extra-arti-socks-connect-soft-timeout-ms 5000` on the download page. It
  passed quality; the soft-timeout profile won paired loads `5/5`, with median
  load `5335.235ms` versus baseline `13570.841ms` and local C Tor
  `7209.919ms`. But the analyzer counted `0` soft timeouts, so this is not yet
  proof that the 60s CONNECT stall is fixed.
- The lower-threshold follow-up saved
  `results/browser-compare-20260607T162821/browser-compare.json`. It ran
  load-aware baseline Arti against load-aware plus
  `--extra-arti-socks-connect-soft-timeout-ms 1000` on the download page. It
  passed quality but was slower by median load: `7301.248ms` versus baseline
  `5440.053ms` and local C Tor `4755.504ms`. It still had `0` soft timeouts;
  hostname CONNECT max was `928ms`, while the slow connect waits were `.onion`
  and correctly excluded from the non-onion timeout.
- The build-wait hedge follow-up saved
  `results/browser-compare-20260607T164207/browser-compare.json`. It ran
  load-aware baseline Arti against load-aware plus
  `--extra-arti-exit-pending-hedge-ms 1500` on the download page. It passed
  quality and counted `1` pending hedge, but `0` build hedge timers. The hedge
  profile was slower: median load `7529.626ms` versus baseline `5928.687ms` and
  local C Tor `4481.306ms`. This proves the analyzer can now see a real
  pending hedge with fields after the log message, but it does not prove the new
  build hedge timer helps. Direct resource A/B says every sampled resource type
  was slower too.
- The next build-wait hedge follow-up saved
  `results/browser-compare-20260607T165147/browser-compare.json`. It used no
  warm cache and a `500ms` hedge profile. It passed quality and counted `1`
  build hedge timer plus `1` pending hedge, so the build timer path is now
  live-proven. It was still slower by median load: `5783.041ms` versus baseline
  `5236.727ms` and local C Tor `4603.830ms`. Its resource-to-relay summary had
  lower matched median relay time and max receive gap than baseline, so the
  remaining loss is broader than one relay gap. The critical-tail fields show a
  similar late-resource tail after DOM, even with lower max resource response
  end, and the direct A/B phase split puts most regression in response-to-DOM.
  Direct resource A/B names the main losses as image/font/icon/script tails such
  as `get-connected.svg`, `fa-regular-400.woff2`, `stay-safe.svg`, and
  `modernizr.js`. The new relay-context A/B table says those top losses did not
  have worse matched relay medians; high-confidence script rows even had lower
  max receive gaps. The HTTP-phase A/B table says the rows were all `http/1.1`
  and mostly lost in fetch-to-request or request-wait, not body receive. The
  broader queue-shape table says `500ms` did not create a whole-page queue
  blow-up, while `1500ms` did show a broad HTTP/1.1 queue/request-wait
  regression. Keep both thresholds lab-only.
- The byte-tap follow-up saved
  `results/browser-compare-20260607T173526/browser-compare.json`. It used the
  same focused download-page shape with `--byte-tap` and passed quality. The
  `500ms` profile was faster in this tap window, but it counted `0` hedge
  timers and `0` pending hedges, so it is not hedge speed proof. Its main value
  is connection shape: late slow resources often mapped to the same neutral
  local TCP tap connection.
- The fixed-capture byte-tap follow-up saved
  `results/browser-compare-20260607T175344/browser-compare.json`. It passed
  quality and confirmed middle-run relay evidence is now retained. The `500ms`
  profile was slower than baseline and local C Tor, so it is not speed proof.
  Its main value is the exact source target: tap connection `18` joined to Arti
  stream `11369` / timing id `19` with high confidence.
- The SOCKS-write diagnostic follow-up saved
  `results/browser-compare-20260607T181517/browser-compare.json`. It passed
  quality. Base Arti beat local C Tor in this window by median load,
  `4203.461ms` versus `5729.532ms`, but the `500ms` hedge profile badly
  regressed to
  `29856.490ms`. The new `tor_to_client_write` byte events appeared, and the
  slow high-confidence tap/relay groups all showed `0.000ms` write lag. That
  rules out browser-facing SOCKS writes as the main tail source for this proof.
- The analyzer now also prints `Torfast Relay Receive Circuit Gap Details`.
  Replaying `20260607T181517` showed the worst same-stream gap was `4917ms` on
  timing id `21`, stream `12719`, `Circ 2.8 (Tunnel 21)`, but the largest
  same-run gap on that circuit was only `2924ms`; another stream also moved on
  that circuit. This rules out a simple whole-circuit idle stall for that proof.
- The analyzer now also prints `Browser Resource Stream Gap Context`. Replaying
  `20260607T181517` showed timing id `19`, stream `25673`, as the strongest
  source target: `3803ms` relay receive gap, `33` same-stream resources, `14`
  high-confidence matches, `31` slow resources, and full `3803ms` overlap with
  browser `request_wait`.
- The analyzer now also prints `Browser Resource Stream Gap Byte Context`.
  Replaying `20260607T181517` showed timing id `19` had `0` strict-middle
  browser read bytes and `528` browser read bytes on the gap edges. Local
  `socks.rs` now also logs debug-only `client_to_tor_write` events and
  relay-finished totals so the next run can rule in/out local outbound write
  delay.
- The fresh write-side run saved
  `results/browser-compare-20260607T184405/browser-compare.json`. It passed
  quality. The new `client_to_tor_write` events appeared and matched
  `client_to_tor` byte counts/timings in sampled streams. The old `3803ms`
  request-wait gap did not reproduce; the largest joined stream gap was
  `701ms`, so this run points away from local outbound write delay.
- The clean normal hedge gate saved
  `results/browser-compare-20260607T184844/browser-compare.json`. It passed
  quality with no debug logging and no byte tap. Base load-aware Arti beat local
  C Tor by median load, `5147.814ms` versus `6913.908ms`, but the `500ms`
  hedge profile was slower than base load-aware Arti at `6239.814ms`. Do not
  promote the `500ms` hedge from this shape.
- The broader normal load-aware gate saved
  `results/browser-compare-20260607T185521/browser-compare.json`. It failed
  quality because base load-aware Arti had one `check.torproject.org` browser
  connection-failure neterror. It also exposed a download-page browser CONNECT
  tail: `connectEnd` was `52751.055ms`.
- The first focused `500ms` soft-CONNECT A/B saved
  `results/browser-compare-20260607T190326/browser-compare.json` and failed
  quality with early neterrors. Local `socks.rs` now keeps the final CONNECT
  attempt out of the soft-timeout wrapper so it waits normally.
- The fixed focused `500ms` soft-CONNECT A/B saved
  `results/browser-compare-20260607T191031/browser-compare.json`. It passed
  quality, but the soft-timeout profile still lost to local C Tor by median
  load on both focused targets. Keep this lab-only.
- The retained-log download diagnostic saved
  `results/browser-compare-20260607T192045/browser-compare.json`. It passed
  quality with debug logs. Base load-aware Arti had immediate hostname CONNECT
  but slow relay/resource tails; fixed soft-timeout Arti counted `0` soft
  timeouts and still lost to local C Tor by median load. The corrected analyzer
  now shows multiple exit candidates often existed, but select parallelism
  stayed `1` and slow tails remained. The next source target is chosen-circuit
  relay timing, late single-candidate reuse, and whether least-assigned
  load-aware choice needs a safe circuit-quality signal, not CONNECT retry.
- The candidate-choice diagnostic saved
  `results/browser-compare-20260607T193855/browser-compare.json`. It passed
  quality with debug logs after adding `selected_candidate_index` and
  `candidate_assignment_summary` to Arti's load-aware open-circuit log. The
  picker alternated to the least-assigned circuit when multiple candidates
  existed. The worst soft-timeout run had `0/6` exit picks with more than one
  candidate and reused one circuit up to `5` assigned streams. The next source
  target is why the eligible exit set shrinks during the resource burst.
- The support-cause diagnostic saved
  `results/browser-compare-20260607T194925/browser-compare.json`. It passed
  quality with debug logs after adding `open_support_summary` to the
  load-aware open-circuit log. The main candidate-shrink reason was stream
  isolation, not exit port policy: fixed soft-timeout run 3 had max open total
  `9`, max rejected open `8`, max isolation rejects `7`, max port rejects `0`,
  and max unusable `0`. The next source target is safe same-isolation capacity.
- `upstream/arti/crates/tor-circmgr/src/mgr.rs` now has default-off
  same-isolation capacity top-up with
  `TORFAST_EXIT_SAME_ISOLATION_TARGET`. `tools/run_browser_compare.py` exposes
  it as `--arti-exit-same-isolation-target` and
  `--extra-arti-exit-same-isolation-target`; the runner also has the combined
  guarded selector form above for focused A/B tests. Top-up is still lab-only
  and now waits for real reuse pressure: the chosen same-isolation circuit must
  already have assigned streams, and open plus pending supported circuits must
  be below the target. The newer
  `TORFAST_EXIT_SAME_ISOLATION_REQUIRE_BAD_HEALTH` lab gate can also require
  the selected circuit to have recent bad local RELAY DATA health before adding
  more same-usage capacity. The analyzer counts `same isolation topups` and
  `same isolation topup failures`; Arti logs top-up attempts at `info` so
  low-log proof runs can count them.
- The same-isolation proof saved
  `results/browser-compare-20260607T201803/browser-compare.json`. It passed
  quality, counted `4` top-ups and `0` failures, and cut max Arti load from
  `10379.077ms` to `6551.679ms`. Median load was flat, so this stays lab-only.
- The broader same-isolation debug proof saved
  `results/browser-compare-20260607T202610/browser-compare.json`. It passed
  quality for target `3` and target `4` on check, home, and download pages.
  Target `3` helped the download median, while target `4` helped more medians
  but still had a `59612.396ms` download tail. Both stayed lab-only.
- The pressure-gated target `4` run saved
  `results/browser-compare-20260607T203902/browser-compare.json`. It passed
  quality and counted `16` top-ups and `0` failures, but it lost the download
  median and still lost to local C Tor, so target `4` is not a default.
- The pressure-gated target `3` run saved
  `results/browser-compare-20260607T204728/browser-compare.json`. It passed
  quality, counted `9` top-ups and `0` failures, cut home median by
  `2566.794ms`, cut download median by `3124.008ms`, and cut download max by
  `5843.854ms` versus baseline Arti. At that point it was the best
  same-isolation capacity shape, but it remained lab-only.
- The stronger low-log target `3` gate saved
  `results/browser-compare-20260607T205407/browser-compare.json`. It failed
  quality because one download-page run hit a browser `netTimeout` and had no
  screenshot proof. It still counted `16` top-ups and `0` failures, but this
  run is rejected as speed proof.
- The smaller low-log target `2` download-page gate saved
  `results/browser-compare-20260607T212007/browser-compare.json`. It passed
  quality and counted `1` top-up with `0` failures, but median load was slower
  than baseline Arti: `8298.258ms` versus `4415.803ms`. Target `2` is also
  rejected as speed proof.
- The smaller low-log target `3` download-page gate saved
  `results/browser-compare-20260607T212559/browser-compare.json`. It passed
  quality and counted `1` top-up with `0` failures, but median load was slower
  than baseline Arti: `6627.799ms` versus `5003.338ms`. This focused target
  `3` run is also rejected as speed proof.
- `tools/run_browser_compare.py` now launches Firefox with the automation-only
  `-remote-allow-system-access` flag so it can read browser connection prefs in
  chrome context. It does not change proxy prefs or page prefs.
- `tools/run_browser_compare.py --extra-arti-proxy-buffer-size SIZE` adds a
  same-window Arti A/B profile with a different local SOCKS socket send/receive
  buffer size. The profile name is `arti_release_browser_buf{size}` after
  stripping spaces and punctuation, for example `arti_release_browser_buf1mb`.
  The warm-cache proof
  `results/browser-compare-20260608T233309/browser-compare.json` passed quality
  but rejects `1 MB` as a default because it helped the homepage and hurt the
  small check page. The follow-up
  `results/browser-compare-20260608T233953/browser-compare.json` rejects
  `256 KB` and `512 KB` too: `256 KB` was much slower on both targets, and
  `512 KB` was mixed with low paired wins.
- The cold default browser gate
  `results/browser-compare-20260608T234644/browser-compare.json` passed quality
  and keeps the next work focused on page-load timing instead of boot. Default
  Arti booted faster than local C Tor in that window, but Arti lost page-only
  load on both targets. The analyzer showed first-response deltas of about
  `+450ms` on check and `+550ms` on the homepage, with one bad homepage
  resource queue tail.
- The byte-tap homepage diagnostic
  `results/browser-compare-20260608T235050/browser-compare.json` showed the
  larger homepage loss came after the main response. Slow resource groups
  matched Arti relay delivery on a few circuits instead of local proxy write
  delay, so keep the next source work on already-eligible exit circuit
  assignment and relay-tail behavior.
- The clean same-window load-aware homepage A/B
  `results/browser-compare-20260608T235305/browser-compare.json` showed
  `TORFAST_EXIT_SELECT_LOAD_AWARE=1` can cut the homepage tail in a focused
  window: load-aware Arti median load was `3701.049ms` versus default Arti
  `7036.249ms`. This is still lab-only because it is not a wide clean gate and
  the load-aware boot had directory timeout signals.
- The wider 3-target gate
  `results/browser-compare-20260608T235720/browser-compare.json` rejects
  `TORFAST_EXIT_SELECT_LOAD_AWARE=1` for promotion. It helped only the small
  check-page median, while losing to default Arti on the homepage and download
  page and adding large tails. Default Arti itself beat local C Tor on all three
  page medians in that window, so the next source work should first prove
  default stability before adding more selector complexity.
- The repeat default-only gate
  `results/browser-compare-20260609T000427/browser-compare.json` showed default
  Arti's page-load edge can repeat on the larger pages, but cold boot can still
  lose badly. Do not add more exit selector complexity until the cold
  directory/bootstrap path is stable enough that page-load wins are not erased
  by launch-to-load time.
- The browser connection pref diagnostic saved
  `results/browser-compare-20260607T213549/browser-compare.json`. It passed
  quality and showed the focused download page used HTTP/1.1, with Tor Browser
  prefs `network.http.http3.enable=false`,
  `network.http.max-persistent-connections-per-server=6`,
  `network.http.max-persistent-connections-per-proxy=256`, and
  `network.http.max-connections=900`. This points away from browser-pref
  changes and toward Tor-side resource/relay-tail work.
- `tools/analyze_browser_compare.py` now prints
  `Browser Resource Stream Gap Phase Summary` after the per-gap stream context.
  The row builder is
  `browser_resource_stream_gap_phase_summary_rows()`. It groups each run's
  joined relay gaps into fetch-to-request, request-wait, response-receive, and
  unmatched buckets.
- `tools/analyze_browser_compare.py` now also prints `Arti Promotion Blocker
  Summary`. The row builder is `promotion_blocker_summary_rows()`. It combines
  boot directory failure signals, paired load deltas versus local C Tor,
  resource queue tails, partial-idle active-resource closes, and slow SOCKS
  onion/hostname stream counts into one next-proof hint.
- The focused replay saved
  `results/browser-compare-20260607T214417/browser-compare.json`. It passed
  quality with debug logs and unchanged Tor Browser connection prefs. Base Arti
  median load was `3636.147ms`, load-aware Arti was `5540.512ms`, and local C
  Tor was `6204.217ms`. The load-aware profile had larger request-wait overlap
  and unmatched stream-gap time, so keep load-aware selection lab-only.
- `upstream/arti/crates/tor-circmgr/src/mgr.rs` now has
  `TORFAST_EXIT_SELECT_MIN_ASSIGNMENT_SPREAD`, a default-off lab guardrail for
  load-aware selection. It is bounded to `0..=8`, logs
  `load_aware_assignment_spread` and `load_aware_min_assignment_spread`, and
  stays inside already eligible exit circuits. `tools/run_browser_compare.py`
  exposes it as `--arti-exit-select-min-assignment-spread` and
  `--extra-arti-exit-select-min-assignment-spread`. The analyzer counts
  `load-aware guardrail kept first`.
- The spread `2` lab proof saved
  `results/browser-compare-20260607T215932/browser-compare.json`. It passed
  quality and the guardrail activated `5` times, but spread-guarded load-aware
  was slower than base Arti by `735.496ms` median load. Treat spread `2` as
  rejected speed proof.
- The stricter spread `4` debug proof saved
  `results/browser-compare-20260608T174012/browser-compare.json`. It passed
  quality but was slower than base Arti by `1932.340ms`, won `0/2` paired
  loads, and selected low-rate/slow-relay circuits. This rejects assignment
  pressure alone as the next fix.
- The health-aware plus spread `4` debug proof saved
  `results/browser-compare-20260608T174515/browser-compare.json`. It passed
  quality and improved median page load, but won only `1/2` paired loads versus
  base Arti. Treat it as narrow lab evidence, not a default-ready selector.
- The wider low-log gate saved
  `results/browser-compare-20260608T175759/browser-compare.json`. It passed
  quality but rejected `healthaware_spread4`: max tails were worse on all three
  targets, and homepage lost by `8208.762ms` paired median load with `0/3`
  paired wins. The promotion-risk stream receiver table ties those tails to
  `not_connected` stream endings with long idle-after-last-data windows. Do not
  promote health-aware plus spread `4`.
- `tools/analyze_browser_compare.py` now prints `Torfast SOCKS Relay Circuit
  Quality` from `torfast_socks_relay_circuit_quality_rows`, plus run summaries
  from `torfast_socks_relay_circuit_quality_run_summary_rows`. It groups joined
  SOCKS/relay streams by browser run and circuit, then reports streams, data
  bytes, first-byte timing, relay time, receive span/gap, rough receive rate,
  and low-rate circuit counts. On `20260607T215932`, spreading increased
  circuit use but still chose some low-rate circuits, so the next source idea
  needs circuit-health proof before selector changes.
- The analyzer also prints `Torfast Load-Aware Selection Health Outcome` from
  `torfast_load_aware_selection_health_outcome_rows`. It joins load-aware
  candidate summaries to later circuit-quality rows and compares the selected
  circuit with candidate `0`. On `20260607T215932`, non-first picks were often
  worse by later receive-rate evidence.
- It also parses load-aware `candidate_health_summary` log rows when Arti emits
  them. The focused `20260607T223225` proof confirmed non-empty health rows:
  `30` aggregate load-aware candidate health rows, with `22` in run 1 and `8`
  in run 2.
- It also counts health-aware open picks, cases where health-aware selection
  changed away from the assignment-only load-aware candidate, and cases where
  the guard kept the assignment candidate.
- Local Arti source now records `CircuitHealthSnapshot` in
  `upstream/arti/crates/tor-proto/src/client/circuit.rs` from incoming RELAY
  DATA cells in `client/reactor/circuit.rs`, exposes it through
  `ClientTunnel::circuit_health_snapshot`, and logs load-aware
  `candidate_health_summary` in `tor-circmgr/src/mgr.rs`.
- `tools/check_arti_quality_config.py` now checks that load-aware selection is
  default-off, exit-only, assignment-count based, and logs candidate assignment
  plus open-support and health summaries for diagnostics. It also checks the
  default-off health-aware lab selector with stale-score, absolute-score, and
  2x-improvement guards, the build-hedge timer log string, the soft-timeout
  final-attempt fallback, the bounded non-onion soft-timeout attempt knob, and
  the bounded, reuse-pressure-gated same-isolation top-up rule, including the
  stronger minimum assigned-stream floor. It now
  also checks that the unknown-health fallback is default-off, gated behind
  bad-health avoidance, limited to unassigned candidates, that the bad-health
  hedge is bounded and lab-only, that slow/failure SOCKS summaries are
  low-log parseable, that relay-finished stream keys are retained, that slow
  tunnel build outcomes are low-log parseable, that actual pending-hedge and
  build-hedge events are low-log parseable, that default-off low-log SOCKS byte
  timing is guarded, that circuit congestion low-log rows are default-off behind
  `TORFAST_CIRCUIT_CONGESTION_LOG`, that directory circuit spreading is
  default-off and Dir-only behind `TORFAST_DIR_SELECT_SPREAD=1`, that
  incremental microdescriptor bootstrap is default-off and microdescriptor-only
  behind `TORFAST_DIR_INCREMENTAL_MICRODESCS=1`, that directory read-timeout
  override is bounded and default-off behind
  `TORFAST_DIRCLIENT_READ_TIMEOUT_MS`, that the microdescriptor body cap is
  bounded and default-off behind `TORFAST_DIRCLIENT_MICRODESC_BODY_MAX_MS`, that
  the microdescriptor minimum body-rate cutoff is bounded and default-off behind
  `TORFAST_DIRCLIENT_MICRODESC_MIN_RATE_BPS`, that the microdescriptor retry
  delay cap is bounded and default-off behind
  `TORFAST_DIR_MICRODESC_RETRY_DELAY_MAX_MS`, that microdescriptor early retry on
  partial is default-off and microdescriptor-only behind
  `TORFAST_DIR_MICRODESC_EARLY_RETRY_ON_PARTIAL=1`, that microdescriptor source
  spread is default-off and microdescriptor-only behind
  `TORFAST_DIR_MICRODESC_SOURCE_SPREAD=1`, that directory client timing logs are
  default-off behind
  `TORFAST_DIRCLIENT_TIMING_LOG=1`, and that post-last-byte plus close/error
  diagnostics and scrubbed `source_circ` fields are parseable. The latest static
  result is
  `results/arti-quality-config-20260609T075456/arti-quality-config.json` with
  `53` passing checks.
- `upstream/arti/crates/tor-proto/src/client/reactor/circuit.rs` now keeps the
  `torfast circuit congestion sendme sent` and `sendme received` diagnostics
  behind `TORFAST_CIRCUIT_CONGESTION_LOG=1`.
  `upstream/arti/crates/tor-proto/src/client/reactor/circuit/circhop.rs` gates
  `torfast circuit congestion scheduler hop blocked` the same way.
  `congestion.rs`, `fixed.rs`, and `vegas.rs` expose the small internal
  diagnostic accessors needed for those rows. These logs do not change path
  rules or flow-control behavior.
- `tools/analyze_browser_compare.py` now includes per-run `proxy_output_tail`
  in `proxy_log_lines`, preserves repeated identical log events from the same
  source, prints `Torfast Circuit Congestion`, and prints `Boot Directory
  Failure Summary` plus `Boot Directory Timeline` from measured proxy boot
  lines. It also falls back to
  low-log stream terminal summaries when the detailed relay-receive join is not
  present, so `Torfast SOCKS Relay Circuit Quality` still reports per-circuit
  bytes, relay time, gaps, and rough receive rate. Use these rows to check
  whether a slow resource circuit was blocked locally, whether it was just
  receiving data slowly, or whether cold boot lost time in directory fetches.
  Warning-only and terminal-summary-only boots are suppressed so harmless
  permission warnings and normal large directory transfers do not look like
  directory failures.
- `tools/run_boot_compare.py` runs repeated fresh proxy boots without browser
  page loads and saves `results/boot-compare-*/boot-compare.json`. It can also
  add a same-window `arti_release_boot_dirspread` profile with
  `--extra-arti-dir-select-spread` to test `TORFAST_DIR_SELECT_SPREAD=1`
  against default Arti and local C Tor, or `arti_release_boot_incrmd` with
  `--extra-arti-dir-incremental-microdescs` to test
  `TORFAST_DIR_INCREMENTAL_MICRODESCS=1`. It can also add
  `arti_release_boot_dirread{MS}ms` with
  `--extra-arti-dirclient-read-timeout-ms MS` to test the bounded directory
  read-timeout lab override, or
  `arti_release_boot_dirprogress{MS}ms` with
  `--extra-arti-dirclient-progress-read-timeout-ms MS` to test the bounded
  directory progress-read timeout lab override, or
  `arti_release_boot_mdbodymax{MS}ms` with
  `--extra-arti-dirclient-microdesc-body-max-ms MS` to test the bounded
  microdescriptor-only body elapsed cap, or
  `arti_release_boot_mdearlyusable` with
  `--extra-arti-dir-microdesc-early-usable-notify` to test early usable
  notification during microdescriptor download. It can also add
  `arti_release_boot_mdchunk{N}` with
  `--extra-arti-dir-microdesc-ids-per-request N` and
  `arti_release_boot_mdpar{N}` with
  `--extra-arti-dir-microdesc-parallelism N`. It can also add
  `arti_release_boot_mdhedge{MS}ms` with
  `--extra-arti-dir-microdesc-hedge-ms MS`, or
  `arti_release_boot_mdretrychunk{N}` with
  `--extra-arti-dir-microdesc-retry-ids-per-request N`, or
  `arti_release_boot_mdretrydelay{MS}ms` with
  `--extra-arti-dir-microdesc-retry-delay-max-ms MS`, or
  `arti_release_boot_mdearlyretrypartial` with
  `--extra-arti-dir-microdesc-early-retry-on-partial`, or
  `arti_release_boot_mdsrcspread` with
  `--extra-arti-dir-microdesc-source-spread`, or
  `arti_release_boot_mdsrcspreadearlyusable` with
  `--extra-arti-dir-microdesc-source-spread-early-usable`, or
  `arti_release_boot_mdsrcspreadpending` with
  `--extra-arti-dir-microdesc-source-spread-pending-spread`, or
  `arti_release_boot_mdsrcspreadpendingearlyusable` with
  `--extra-arti-dir-microdesc-source-spread-pending-spread-early-usable`. Each boot run now saves
  a directory timeline with consensus attempts, microdescriptor timing,
  usable-directory timing, first directory timeout, stream terminal-summary
  transfer stats, circuit build failure counts, first circuit-build-failure
  timing, max pending circuit-build age, usage-kind counts for new build-failed
  rows, channel-open timing counts, max channel-open elapsed, body-read timing
  maxima from directory client rows, same-source-circuit dirclient row, timeout,
  and partial summaries, including the specific source-circuit labels with the
  most timeout rows and the most partial rows. It also saves default-off
  directory client request timing rows when `--arti-dirclient-timing-log` is set.
- `upstream/arti/crates/tor-circmgr/src/mgr.rs` has a default-off lab switch
  `TORFAST_DIR_SELECT_SPREAD=1`. Slow tunnel build failed/complete/canceled
  logs now include a scrubbed `usage_kind` such as `dir`, `exit`, or
  `preemptive`, so boot proofs can separate directory-channel setup from
  exit-circuit work without logging relay identity. Static proof
  `results/arti-quality-config-20260609T060154/arti-quality-config.json`
  passed `47` checks. When directory spread is enabled for directory circuits
  only, it chooses the least-assigned already eligible open directory circuit
  and counts directory assignments. The same-window proof
  `results/boot-compare-20260608T134519/boot-compare.json` rejected it for
  speed, so do not promote it.
- `upstream/arti/crates/tor-circmgr/src/build.rs` now logs low-log
  `torfast channel open timing` rows when channel open is slow (`>=1000ms`) or
  fails. The row includes only `elapsed_ms`, scrubbed `usage_kind`, provenance,
  broad error kind on failure, and outcome; it does not log relay identity or
  change channel selection/retry behavior. Static proof
  `results/arti-quality-config-20260609T061037/arti-quality-config.json`
  passed `48` checks. The rebuilt proof
  `results/boot-compare-20260608T221237/boot-compare.json` showed a slow boot
  with a successful `dir` channel open in `1172ms`, then `4` microdescriptor
  partial-response directory timeouts and max dirclient elapsed `12366ms`.
- `upstream/arti/crates/tor-dirmgr/src/bootstrap.rs` has a default-off lab
  switch `TORFAST_DIR_INCREMENTAL_MICRODESCS=1`. It processes downloaded
  microdescriptor responses as they arrive and returns early once
  `Readiness::Usable` is reached. The 5-run proof
  `results/boot-compare-20260608T140019/boot-compare.json` rejected it for
  promotion because median boot was slower than default Arti, so keep it
  lab-only.
- The same file has a default-off lab switch
  `TORFAST_DIR_MICRODESC_EARLY_USABLE_NOTIFY=1`. It is microdescriptor-only and
  sends the usable bootstrap notification as soon as Arti's existing
  `Readiness::Usable` threshold is reached, while continuing to collect
  descriptor responses. Static proof
  `results/arti-quality-config-20260609T002902/arti-quality-config.json` passed
  `44` checks. The 5-run boot proof
  `results/boot-compare-20260608T163146/boot-compare.json` was promising
  (`10.598s` median versus default `18.782s`), but the browser gate
  `results/browser-compare-20260609T003557/browser-compare.json` passed quality
  and rejected promotion because default Arti booted faster and won all
  page-load medians in that window. `tools/run_browser_compare.py` can test it
  with `--extra-arti-dir-microdesc-early-usable-notify`.
- The repeat same-window health-aware gate saved
  `results/browser-compare-20260609T004224/browser-compare.json`. It passed
  quality and health-aware beat default Arti on all three page-only medians, but
  boot was worse (`19.693s` versus `10.740s`) with directory timeout signals,
  so boot+load lost on every target. Keep `TORFAST_EXIT_SELECT_HEALTH_AWARE`
  and plain `TORFAST_EXIT_SELECT_LOAD_AWARE` lab-only.
- `upstream/arti/crates/tor-dirmgr/src/docid.rs` has a default-off bounded lab
  switch `TORFAST_DIR_MICRODESC_IDS_PER_REQUEST`. Normal Arti keeps `500`
  document IDs per request when unset; lab values are accepted only from `64`
  through `500`. Static proof
  `results/arti-quality-config-20260608T225832/arti-quality-config.json` passed
  `41` checks. The `250` and `375` 10-run A/Bs
  `results/boot-compare-20260608T150048/boot-compare.json` and
  `results/boot-compare-20260608T150541/boot-compare.json` rejected smaller
  chunks for speed, so keep this diagnostic lab-only.
- `upstream/arti/crates/tor-dirmgr/src/bootstrap.rs` has a default-off bounded
  lab switch `TORFAST_DIR_MICRODESC_RETRY_IDS_PER_REQUEST`. It keeps the first
  microdescriptor request grouping unchanged and only passes a smaller
  microdescriptor limit to `split_for_download_with_microdesc_limit` after a
  prior download/add error when the current missing documents are all
  microdescriptors. `DownloadAttemptOutcome.download_error_count` and
  `retry_microdesc_chunking_allowed` are the gate; normal parsing, storage,
  checksum, and netdir validation stay unchanged.
  `tools/run_boot_compare.py` exposes it with
  `--extra-arti-dir-microdesc-retry-ids-per-request`; `tools/run_browser_compare.py`
  exposes the same extra profile as
  `arti_release_browser_mdretrychunk{N}`. Static proof
  `results/arti-quality-config-20260609T012503/arti-quality-config.json` passed
  `45` checks. The broad retry trigger rejected `250`, made `375` promising in
  boot-only proof, then failed browser promotion because it lost boot/check-page
  and had a worse homepage max tail. The signal-gated proof
  `results/boot-compare-20260608T172658/boot-compare.json` improved median
  boot a little and max boot a lot, but
  `results/browser-compare-20260609T012818/browser-compare.json` passed quality
  with mixed speed: homepage/download medians improved, while boot and
  check-page median got worse. Keep it lab-only. The repeat 5-run proof
  `results/boot-compare-20260608T215008/boot-compare.json` rejects `375` for
  boot too: default Arti median boot was `14.536s`, local C Tor was `12.758s`,
  and retry chunk `375` was worse at `16.899s` with directory timeout/failure
  signals. Refreshed timeline fields counted `8` default Arti circuit build
  failures, all channel-open failures, with first failure at about `10s` before
  certificate and microdescriptor download, so the next boot proof should
  inspect first directory channel/tunnel setup and source reliability before
  changing retry chunk size again. The rebuilt diagnostic proof
  `results/boot-compare-20260608T220401/boot-compare.json` confirmed the new
  `usage_kind` field from release Arti: `3/3` default boots succeeded, median
  boot was `8.785s`, and the one slow run had `1` channel-open build failure
  with `usage_kind="dir"` at `10s`.
  The focused body-timing repeat
  `results/boot-compare-20260608T223455/boot-compare.json` keeps retry chunk
  `375` lab-only: it barely won median boot (`9.327s` versus default `9.559s`)
  and removed default directory timeouts, but added channel-open/circuit-build
  and `NOTDIRECTORY` signals. The default slow run's partial bodies kept reading
  until near the total `10s` timeout, so this is a slow/truncated-body source
  replacement problem, not an idle-after-last-byte problem.
- `upstream/arti/crates/tor-dirmgr/src/bootstrap.rs` also has a default-off
  bounded lab switch `TORFAST_DIR_MICRODESC_RETRY_DELAY_MAX_MS`. It only caps
  sleep before a next retry after a real microdescriptor download error and
  only while the current missing documents are all microdescriptors. Static
  proof `results/arti-quality-config-20260609T070934/arti-quality-config.json`
  passed `51` checks. The first proof
  `results/boot-compare-20260608T231150/boot-compare.json` rejects `500ms`: it
  lost by median (`15.415s` versus default `13.721s`), slightly worsened max
  boot, and added timeout rows. The cap fired only `2/5` times, reducing
  `1000ms` to `500ms`; `2000ms` would not affect that observed path. Keep it
  lab-only.
- `upstream/arti/crates/tor-dirmgr/src/bootstrap.rs` also has a default-off
  microdescriptor-only lab switch
  `TORFAST_DIR_MICRODESC_EARLY_RETRY_ON_PARTIAL=1`. In a microdescriptor batch,
  it stops waiting for remaining in-flight responses after the first partial
  `200` response, keeps that partial body for normal parsing, and uses the
  normal retry loop for still-missing documents. Static proof
  `results/arti-quality-config-20260609T074338/arti-quality-config.json` passed
  `52` checks. The first 5-run proof
  `results/boot-compare-20260608T234014/boot-compare.json` rejects it: median
  boot worsened from `14.820s` to `22.668s`, and the candidate added directory
  failures/timeouts, `NOTDIRECTORY`, partial responses, and a warning. Keep it
  lab-only.
- `upstream/arti/crates/tor-dirclient/src/lib.rs`,
  `upstream/arti/crates/tor-circmgr/src/lib.rs`,
  `upstream/arti/crates/tor-circmgr/src/mgr.rs`, and
  `upstream/arti/crates/tor-circmgr/src/usage.rs` now have a default-off
  microdescriptor source-spread lab path behind
  `TORFAST_DIR_MICRODESC_SOURCE_SPREAD=1`. `tor-dirclient` gates it by
  classified request kind before circuit selection. The circuit manager uses a
  distinct `DirMicrodesc` target usage with the same one-hop directory path and
  normal directory eligibility, then picks the least-assigned eligible open
  directory circuit. Static proof
  `results/arti-quality-config-20260609T075456/arti-quality-config.json` passed
  `53` checks. The first 5-run proof
  `results/boot-compare-20260608T235159/boot-compare.json` improved median boot
  from `16.917s` to `13.296s`, but worsened max boot and added directory
  failure/timeout/partial rows. Keep it lab-only until the one-source tail is
  fixed.
- `upstream/arti/crates/tor-circmgr/src/mgr.rs` also has
  `TORFAST_DIR_MICRODESC_PENDING_SPREAD=1`, a default-off `DirMicrodesc`-only
  diagnostic. It only affects the pending-circuit handoff: if a later
  microdescriptor request receives a circuit that already has a microdescriptor
  assignment and another unused eligible open/pending circuit may still be
  available, it skips that assigned circuit once and keeps it as fallback.
  Static proof `results/arti-quality-config-20260609T080825/arti-quality-config.json`
  passed `54` checks. The first proof
  `results/boot-compare-20260609T001032/boot-compare.json` improved median boot
  (`10.255s` versus default `13.701s`) with no directory download signals, but
  worsened max boot and circuit-build failures, so it remains lab-only.
- `tools/run_boot_compare.py --extra-arti-dir-microdesc-parallelism N` uses
  Arti's official `download_schedule.retry_microdescs.parallelism` config to
  test directory download width. The default is `4`. The 10-run proof
  `results/boot-compare-20260608T151034/boot-compare.json` rejected `6` and
  `8` because both were slower by median and `8` raised directory failures.
- `upstream/arti/crates/tor-dirmgr/src/bootstrap.rs` has a default-off bounded
  lab switch `TORFAST_DIR_MICRODESC_HEDGE_MS`. It only hedges
  `ClientRequest::Microdescs` after the configured delay, races the normal
  request against a backup request, prefers a clean `200` response, and keeps
  normal document parsing and validation unchanged. Static proof
  `results/arti-quality-config-20260608T232103/arti-quality-config.json` passed
  `42` checks. The 10-run proof
  `results/boot-compare-20260608T152310/boot-compare.json` rejected `7000ms`
  and `8000ms` because both were slower and added directory failures/timeouts.
- `upstream/arti/crates/tor-dirclient/src/lib.rs` has a default-off bounded
  lab switch `TORFAST_DIRCLIENT_READ_TIMEOUT_MS`. Normal Arti keeps the `10s`
  directory read timeout when unset. Lab values are accepted only from `2000ms`
  through `10000ms`. The 5-run `5000ms` proof
  `results/boot-compare-20260608T141134/boot-compare.json` was too aggressive,
  but the 5-run `8000ms` proof
  `results/boot-compare-20260608T141435/boot-compare.json` is the current
  boot-only candidate: it improved median and max boot and had `0` directory
  timeout signals in that window. `tools/run_browser_compare.py` can test this
  path with `--arti-dirclient-read-timeout-ms` or the same-window A/B flag
  `--extra-arti-dirclient-read-timeout-ms`. The first browser gate
  `results/browser-compare-20260608T222249/browser-compare.json` passed quality
  but rejected promotion because the `8000ms` profile booted in `44.296s` with
  directory timeout/failure signals, worse than default Arti `18.452s` and
  local C Tor `13.573s`. The new timeline table shows the bad shape as timeout
  at `9.000s`, retry, microdescriptors at `19.000s`, and usable directory at
  `44.000s`; the fresh boot-only
  `results/boot-compare-20260608T143102/boot-compare.json` shows good default
  Arti boots can reach median usable directory at `11.000s` with no directory
  failure signals.
- The same file has a default-off bounded lab switch
  `TORFAST_DIRCLIENT_PROGRESS_READ_TIMEOUT_MS`. Normal Arti keeps the existing
  total directory body-read timeout when unset. When set, lab runs use the
  configured timeout as a per-read progress/idle timeout for directory body
  reads. Static proof
  `results/arti-quality-config-20260609T001630/arti-quality-config.json` passed
  `43` checks. The 5-run proof
  `results/boot-compare-20260608T161854/boot-compare.json` rejected `2000ms`
  because median boot was slower than default (`16.225s` versus `12.603s`) and
  max boot rose to `41.890s`. Keep this diagnostic lab-only.
- The same file has a default-off bounded lab switch
  `TORFAST_DIRCLIENT_MICRODESC_BODY_MAX_MS`. It only applies to request kind
  `microdesc` when `partial_response_body_ok()` is already true; normal
  consensus/certificate fetches and normal unset Arti keep the regular `10s`
  body-read timeout. Static proof
  `results/arti-quality-config-20260609T064708/arti-quality-config.json` passed
  `49` checks. The first 5-run proof
  `results/boot-compare-20260608T224426/boot-compare.json` rejects `7000ms`:
  it capped max body last byte at `7000ms` and lowered max boot, but median boot
  got much worse (`15.292s` versus default `8.062s`) and it added `9` directory
  timeout/partial-response signals. Keep it lab-only.
- The same file has a default-off bounded lab switch
  `TORFAST_DIRCLIENT_MICRODESC_MIN_RATE_BPS`. It only applies to request kind
  `microdesc` when `partial_response_body_ok()` is already true, and it starts
  checking after `7s` of body-read time, not request time. The same body-start
  clock also keeps the normal unset `10s` body timeout from being spent by slow
  headers. Static proof
  `results/arti-quality-config-20260609T065856/arti-quality-config.json` passed
  `50` checks. The corrected `98304` B/s proof
  `results/boot-compare-20260608T230100/boot-compare.json` was faster by median
  but added `4` directory timeouts/partials and worsened max boot. The `65536`
  B/s proof `results/boot-compare-20260608T230303/boot-compare.json` was clean
  on directory signals but slower by median and max boot. Keep min-rate cutoffs
  lab-only.
- The same file has a default-off diagnostic switch
  `TORFAST_DIRCLIENT_TIMING_LOG=1`. When enabled, it logs
  `torfast dirclient timing` rows with classified request kind, anonymization
  mode, outcome, status, body bytes, elapsed time, read timeout, body read
  calls, first/last body byte timing, max body read gap, timeout-after-last-byte
  gap, EOF flag, error kind, and a scrubbed `source_circ` such as `Circ~2.0`.
  It classifies paths as
  consensus/authcert/microdesc/routerdesc/other rather than logging full
  directory URLs or relay identity. Static proof
  `results/arti-quality-config-20260609T073120/arti-quality-config.json` passed
  `51` checks. `results/boot-compare-20260608T144325/boot-compare.json` used
  the older rows to show the bad cold-boot path is large microdescriptor tail
  latency: consensus max `2956ms`, microdescriptor max `11013ms`, with timeout
  rows on microdescriptor partial responses. The fixed body-progress proof
  `results/boot-compare-20260608T222441/boot-compare.json` is the clean
  baseline: max body first byte `992ms`, max body last byte `2278ms`, max body
  read gap `657ms`, timeout-after-last-byte `0ms`, and `66/66` body EOF rows.
  Wider proof `results/boot-compare-20260608T222751/boot-compare.json` ran
  `8/8` successful boots, saw no directory timeouts, and kept max
  timeout-after-last-byte at `0ms`. It captured a separate run-1 source failure:
  two microdescriptor `NOTDIRECTORY` partial responses before body bytes,
  followed by successful retry. The slow clean run had max body first byte
  `2038ms`, max body last byte `3916ms`, and max body read gap `1287ms`.
  The source-circuit proof
  `results/boot-compare-20260608T232537/boot-compare.json` then grouped the
  timeout rows by safe source label: run `4` had `4` microdescriptor partial
  timeouts on `source_circ="Circ~2.0"` and booted in `32.828s`.
- `tools/run_boot_compare.py --extra-arti-dir-microdesc-source-spread-early-usable`
  tests source spread together with Arti's existing early usable notification.
  Static proof `results/arti-quality-config-20260609T075951/arti-quality-config.json`
  passed `53` checks. The first proof
  `results/boot-compare-20260608T235958/boot-compare.json` kept `5/5` boots
  successful and removed directory timeout/partial rows in the combo profile,
  but lost by median boot (`14.255s` versus default `9.986s`) and added one
  circuit-build failure, so it stays lab-only.
- `tools/run_boot_compare.py --extra-arti-dir-microdesc-source-spread-pending-spread`
  tests source spread together with the pending-circuit spread guard. Static
  proof `results/arti-quality-config-20260609T080825/arti-quality-config.json`
  passed `54` checks. The first proof
  `results/boot-compare-20260609T001032/boot-compare.json` kept `5/5` boots
  successful and had `0` directory failures/timeouts/partials in both profiles.
  It improved median boot by `3.446s`, but worsened max boot and same-source
  concentration, so it stays lab-only.
- `tools/run_boot_compare.py --extra-arti-dir-microdesc-source-spread-pending-spread-early-usable`
  tests source spread, the pending-circuit spread guard, and Arti's existing
  early usable notification together. `tools/run_browser_compare.py` exposes the
  same combo with
  `--extra-arti-dir-microdesc-source-spread-pending-spread-early-usable` and
  also exposes source spread plus pending spread without early usable
  notification with
  `--extra-arti-dir-microdesc-source-spread-pending-spread`. Both browser
  profiles record `arti_dir_microdesc_source_spread`,
  `arti_dir_microdesc_pending_spread`, and
  `arti_dir_microdesc_early_usable_notify` in each profile. Static proof
  `results/arti-quality-config-20260609T085046/arti-quality-config.json` passed
  `54` checks. The first boot proof
  `results/boot-compare-20260609T001539/boot-compare.json` improved median and
  max boot and removed directory failure/partial/`NOTDIRECTORY` signals in that
  window. Browser proofs
  `results/browser-compare-20260609T081953/browser-compare.json` and
  `results/browser-compare-20260609T082109/browser-compare.json` both passed
  quality, but the second proof was slower than default Arti by boot and median
  load. Wider proof `results/browser-compare-20260609T082814/browser-compare.json`
  then showed huge combo max tails (`40443.433ms` check and `65683.059ms`
  download), and diagnostic proof
  `results/browser-compare-20260609T083656/browser-compare.json` reproduced a
  download timeout with `15` hostname relay tails on one circuit. The no-early
  source+pending browser profile in
  `results/browser-compare-20260609T084334/browser-compare.json` also failed one
  download run. Fresh rescue proof
  `results/browser-compare-20260609T150602/browser-compare.json` showed the
  early-usable source-spread combo passed all `9/9` own page loads and fixed the
  current directory boot failure shape (`12.758s`, no directory failure signals),
  but it lost homepage (`6560.444ms` vs local C Tor `4866.763ms`) and lost
  boot-plus-load on every target. Focused byte-timing proof
  `results/browser-compare-20260609T151737/browser-compare.json` then showed the
  combo improved homepage median and max load versus baseline Arti and only
  trailed local C Tor by `191.124ms` paired median load, with resource queue as
  the remaining blocker and no scheduler monopoly. Repeat proof
  `results/browser-compare-20260609T152122/browser-compare.json` passed quality
  and had the plain combo beat local C Tor on homepage median load
  (`2931.112ms` vs `5510.561ms`). The broader normal gate
  `results/browser-compare-20260609T152840/browser-compare.json` did not promote
  it: baseline Arti failed one download run, while the combo passed all `9/9`
  own page loads, beat local C Tor on check/homepage, but lost download page-load
  median (`4611.889ms` vs `3159.719ms`). Focused download byte proof
  `results/browser-compare-20260609T153532/browser-compare.json` passed quality
  and showed the combo beat local C Tor on download, but lost to default Arti
  (`4806.959ms` vs `3514.894ms`) because of a single selected-circuit queue with
  late Tor data. The combo stays lab-only.
- `tools/run_browser_compare.py` exposes
  `--extra-arti-exit-select-max-active-streams` for a same-window, runner-only
  load-aware active stream cap profile. It creates
  `arti_release_browser_loadaware_activecapN` and leaves baseline Arti
  unchanged. Focused download proof
  `results/browser-compare-20260609T155220/browser-compare.json` passed quality
  and prefs. `activecap2` beat default Arti on all `3/3` paired download runs,
  beat local C Tor on download median load (`4266.003ms` vs `5128.153ms`), and
  cut max queue to `2183.377ms`. Keep it lab-only until broader
  check/homepage/download proof and privacy review.
- Broad proof `results/browser-compare-20260609T155804/browser-compare.json`
  is stronger but still not promotion proof. Baseline Arti failed one download
  run with `netTimeout`; activecap2 passed all `9/9` candidate page loads and
  kept prefs unchanged. It beat local C Tor on check, homepage, and download
  medians, and cut homepage/download max queue versus baseline Arti. Keep the
  profile lab-only because slow stream-gap blockers remain and stream placement
  across eligible circuits needs privacy review.
- Active-cap tuning proof
  `results/browser-compare-20260609T161014/browser-compare.json` compared caps
  `1`, `2`, and `3` on download with byte timing. Cap `1` had the best median,
  cap `2` had the lower max queue, and cap `3` lost to local C Tor. Broad proof
  `results/browser-compare-20260609T161607/browser-compare.json` rejects cap
  `1` for promotion because it passed quality but lost check, homepage, and
  download medians to local C Tor. Keep cap `2` as the active-cap lab path.
- Broad repeat `results/browser-compare-20260609T162554/browser-compare.json`
  weakens activecap2 promotion. The candidate passed all `9/9` own page loads,
  but it lost check and download page-load medians to local C Tor and lost
  download to baseline Arti. Keep active-cap lab-only and use it as queue
  evidence while the next work targets stream-gap/no-Tor-byte failures.
- Fresh broad proof `results/browser-compare-20260612T213724/browser-compare.json`
  briefly strengthened activecap2 again: quality passed and activecap2 beat
  local C Tor on check, homepage, and download median page loads. But the
  analyzer still showed slow onion/hostname CONNECT stream blockers and small
  tail risk. Wider repeat
  `results/browser-compare-20260612T214724/browser-compare.json` rejects
  promotion: base Arti had one Tor-check failure, activecap2 passed all `15/15`
  own page loads, but it lost all three median page loads to local C Tor
  (`2402.080ms` vs `1635.013ms`, `6911.355ms` vs `5947.003ms`, and
  `8233.304ms` vs `4276.828ms`). Keep activecap2 lab-only; do not make it a
  default speed patch from the single good 3-run window.
- `tools/analyze_browser_compare.py` now prints
  `Arti One-Eligible Open-Circuit Bursts`. Replaying
  `results/browser-compare-20260609T184543/browser-compare.json` shows the
  activecap2 proof still leaves one eligible open circuit during bursts because
  isolation rejects most open circuits. The worst activecap2 rows had open
  totals up to `14`, rejected open circuits up to `13`, isolation rejects up to
  `12`, port rejects `0`, and `0` active-cap moves. Treat active-cap as lab
  evidence only; the next source target is a stricter privacy-safe
  same-isolation capacity trigger, not broad capacity growth.
- `upstream/arti/crates/tor-circmgr/src/usage.rs` adds
  `torfast_exit_isolation_bucket()`, and `mgr.rs` adds those scrubbed buckets to
  `open_support_summary`. The fields are counts only:
  `exit_unisolated`, `exit_compatible_isolated`,
  `exit_incompatible_isolated`, `exit_port_blocked`,
  `exit_stability_blocked`, and `exit_country_blocked`. They do not expose the
  isolation key or SOCKS auth. `tools/analyze_browser_compare.py` now carries
  those fields into the queue-loss capacity and one-eligible burst tables.
- Rebuilt proof `results/browser-compare-20260609T191722/browser-compare.json`
  shows those buckets in live browser data. In the activecap2 capacity-pressure
  row, open total was `13`, max isolation rejects `10`, free unisolated exits
  `0`, compatible isolated exits `1`, and incompatible isolated exits `10`.
  Analyzer hint: `other isolation groups own open circuits`. This rejects
  active-cap tuning and points to a stricter current-isolation capacity trigger.
- Focused stream-gap byte proof
  `results/browser-compare-20260609T163624/browser-compare.json` reproduces the
  no-data stall in default Arti: download run `2` timed out after `120000ms`,
  and `Circ 0.11` held `10` hostname relay-tail streams, with `8` no-Tor-byte
  streams and `2` partial-then-idle streams. Activecap2 avoided that timeout and
  passed its own page loads and prefs, but still lost homepage median load to
  local C Tor. Keep active-cap lab-only. The next source target is a
  default-off no-data/idle stream health proof that preserves path rules and
  browser privacy prefs.
- `tools/run_browser_compare.py --arti-exit-select-bad-health-active-no-data-ms MS`
  sets `TORFAST_EXIT_SELECT_BAD_HEALTH_ACTIVE_NO_DATA_MS` for Arti lab profiles.
  The same-window flag
  `--extra-arti-exit-select-bad-health-active-no-data-ms MS` creates
  `arti_release_browser_loadaware_activenodataMSms` while leaving baseline Arti
  unchanged. Static proof
  `results/arti-quality-config-20260609T170331/arti-quality-config.json` passed
  `58` checks. Browser proof
  `results/browser-compare-20260609T171439/browser-compare.json` failed quality:
  the active-no-DATA profile failed `2/3` download runs versus default Arti
  `1/3` and local C Tor `0/3`. Keep this lab-only and shift the next proof to
  per-stream relay-tail timeout, abandon, or retry behavior.
- `tools/analyze_browser_compare.py` now prints no-Tor-byte timeout safety rows
  when `TORFAST_SOCKS_NO_TOR_BYTE_RELAY_TIMEOUT_MS` fires: timeout rows,
  client-abandon evidence, and browser resource context. Static proof
  `results/arti-quality-config-20260609T173625/arti-quality-config.json` passed
  `58` checks. Browser proof
  `results/browser-compare-20260609T174005/browser-compare.json` passed quality
  but rejects no-byte `5000ms` as a speed path: it fired `0` no-byte timeout
  events and made download much slower (`10036.529ms` median load, max
  `40764.704ms`). Its selected-circuit analyzer table shows `Circ 1.15 (Tunnel
  33)` was a multi-stream late circuit: `17` late queued resources across `6`
  terminal streams, max terminal last data after queue `9746.873ms`, max terminal
  data gap `4173.000ms`. The new cause table combines this with scheduler and
  congestion proof: `36` scheduler DATA picks across `6` streams, top stream
  share `27.778%`, max same-stream streak `3`, `0` congestion scheduler blocks,
  `0` `can_send=false`, fixed-window mode, `0` terminal pending bytes, all
  terminal SENDMEs OK, and min recv window `450`. The next source target is
  selected-circuit multi-stream late DATA or circuit choice, not another lower
  no-byte timeout and not a stream scheduler patch from this evidence.
- `tools/analyze_browser_compare.py` now also prints
  `Arti Profile Queue Loss Circuit Choice`. Replaying
  `results/browser-compare-20260609T174005/browser-compare.json` shows the bad
  `Circ 1.15 (Tunnel 33)` run had `35` resources queued at least `1000ms`, `23`
  queued at slot depth `>=6`, and max queue `31633.966ms`; the choice context was
	  only `*0:Circ 1.15:a1:s13125.000:g351.000`, with `0` better-health and `0`
	  lower-assignment alternatives. Next source work should prove/build safer open
	  capacity before the resource burst, or collect deeper network-side late-DATA
	  evidence, not another already-open-circuit scoring tweak from this proof.
- `tools/analyze_browser_compare.py` now also prints
  `Arti Profile Queue Loss Capacity Pressure`. The same replay shows `28`
  selected open rows for `Circ 1.15`, open candidates always `1`, max selected
  assigned streams `14`, max selected active streams `5`, open support max `14`
  with `12` isolation rejects and `1` port reject, active cap `0`, and `0`
  same-isolation topups. The label is
  `eligible same-isolation open capacity missing`; the next source target is
  usable same-isolation capacity before the burst, or deeper network-side late
  DATA proof.
- `tools/run_browser_compare.py` also exposes
  `--extra-arti-dir-microdesc-source-spread-pending-spread-early-usable-load-aware`.
  It creates `arti_release_browser_mdsrcspreadpendingearlyusable_loadaware`,
  which combines the source-spread boot combo with
  `TORFAST_EXIT_SELECT_LOAD_AWARE=1` while leaving baseline Arti unchanged.
  Focused proofs
  `results/browser-compare-20260609T090110/browser-compare.json` and
  `results/browser-compare-20260609T090433/browser-compare.json` passed quality,
  but rejected this as a promotion path: load-aware was slower than the old
  source-spread combo in the first proof, and the spread-`2` guard was slower
  than default Arti and local C Tor in the second proof. Repeat proof
  `results/browser-compare-20260609T152122/browser-compare.json` keeps that
  decision: load-aware passed quality and beat local C Tor in that window, but
  was worse than the plain source-spread combo on median load (`4309.839ms` vs
  `2931.112ms`) and max load (`5441.475ms` vs `4096.910ms`).
- `tools/run_browser_compare.py` also exposes
  `--extra-arti-dir-microdesc-source-spread-pending-spread-early-usable-load-aware-early-retry-on-partial`.
  It creates
  `arti_release_browser_mdsrcspreadpendingearlyusable_loadaware_earlyretrypartial`,
  which combines the same load-aware directory combo with
  `TORFAST_DIR_MICRODESC_EARLY_RETRY_ON_PARTIAL=1`. Proof
  `results/browser-compare-20260609T214104/browser-compare.json` passed browser
  quality but rejects this path: it booted slower than local C Tor, produced
  directory timeout and partial-response signals, and lost median load on both
  focused targets. Keep it lab-only.
- `upstream/arti/crates/tor-dirmgr/src/bootstrap.rs` has default-off lab switch
  `TORFAST_DIR_MICRODESC_PARTIAL_RETRY_CHUNKING=1`. It is microdescriptor-only
  and counts `DirResponse::error()` on a useful partial response as a retry
  signal without stopping the current batch. `tools/run_browser_compare.py`
  exposes
  `--extra-arti-dir-microdesc-source-spread-pending-spread-early-usable-load-aware-partial-retry-chunking`,
  creating
  `arti_release_browser_mdsrcspreadpendingearlyusable_loadaware_partialretrychunk`.
  `tools/run_boot_compare.py` now exposes both a narrow
  `--extra-arti-dir-microdesc-partial-retry-chunking` profile and a cold-boot
  mirror of the current best directory combo,
  `--extra-arti-dir-microdesc-source-spread-pending-spread-early-usable-partial-retry-chunking`.
  Boot summaries now count `partial_retry_chunking_signals`, so future cold-boot
  proof can tell whether the signal actually fired without digging through raw logs.
  That profile sets source spread, pending spread, early usable notification,
  load-aware exit selection, partial-retry chunking, retry chunks of `250`, and
  retry delay cap `500ms`. Proof
  `results/browser-compare-20260609T220925/browser-compare.json` passed quality
  and booted fast, but still lost page-only median load to local C Tor on check
  and download, so it stays lab-only. The runner boot-signal allow-list now also
  retains `partial retry chunking signal` for future proof.
  Clean 5-run proof `results/browser-compare-20260609T221818/browser-compare.json`
  also passed quality and booted this profile faster than local C Tor, but
  page-only median load lost on all three targets, download boot+load lost, and
  the stored boot signals did not include `partial retry chunking signal`. Treat
  it as combo proof only, not proof that partial-retry chunking fired.
- `tools/run_browser_compare.py --arti-exit-select-bad-health-stream-idle-ms MS`
  sets `TORFAST_EXIT_SELECT_BAD_HEALTH_STREAM_IDLE_MS` for Arti lab profiles.
  Static proof `results/arti-quality-config-20260609T092948/arti-quality-config.json`
  passed `55` checks. Focused browser proof
  `results/browser-compare-20260609T093222/browser-compare.json` passed quality
  with `MS=5000`, but the source-spread plus load-aware plus terminal-idle
  profile was slower than default Arti and local C Tor, so this knob stays
  lab-only.
- `tools/run_browser_compare.py --arti-exit-select-max-active-streams N` sets
  `TORFAST_EXIT_SELECT_MAX_ACTIVE_STREAMS` for Arti lab profiles. Valid values
  are `1` through `32`. `upstream/arti/crates/tor-proto/src/client/circuit.rs`
  stores active-stream counts in `CircuitHealthSnapshot`, and
  `upstream/arti/crates/tor-proto/src/client/stream/data.rs` increments the
  count when a client stream opens and decrements it when the stream closes or
  reaches terminal idle. `upstream/arti/crates/tor-circmgr/src/mgr.rs` applies
  the cap only after normal open-circuit eligibility and only among already
  eligible open exit circuits. Static proof
  `results/arti-quality-config-20260609T095109/arti-quality-config.json` passed
  `56` checks. Focused browser proof
  `results/browser-compare-20260609T095334/browser-compare.json` passed quality
  with `N=2`, but did not prove an active-cap move and still showed
  single-circuit relay-tail clusters, so this knob stays lab-only.
- `upstream/arti/crates/tor-circmgr/src/mgr.rs` now logs
  `selected_candidate_index_before_active_cap` and `active_stream_cap_moved` on
  `torfast circuit selection open`. `tools/run_browser_compare.py` keeps
  circuit-selection rows in compact signal context, and
  `tools/analyze_browser_compare.py` reports active-cap picks, moves, selected
  active-stream counts, and candidate active-stream counts. Static proof
  `results/arti-quality-config-20260609T101530/arti-quality-config.json` passed
  `56` checks. Focused browser proof
  `results/browser-compare-20260609T101308/browser-compare.json` passed quality
  with `N=1` and proved real moves (`10/23` on the source-spread combo), but it
  remains lab-only because resource-queue blockers and single-circuit slow-tail
  clusters remain.
- `upstream/arti/crates/tor-circmgr/src/mgr.rs` also handles saturated active
  caps: if every already eligible open exit circuit is at or above
  `TORFAST_EXIT_SELECT_MAX_ACTIVE_STREAMS`, the lab code chooses the least-active
  eligible circuit instead of staying on the first selected capped circuit.
  Selection logs include `active_stream_cap_saturated`, and
  `tools/analyze_browser_compare.py` reports saturated counts. Static proof
  `results/arti-quality-config-20260609T104117/arti-quality-config.json` passed
  `56` checks. Focused browser proof
  `results/browser-compare-20260609T102258/browser-compare.json` passed quality
  and proved saturated cases, but speed did not hold, so this remains lab-only.
- `tools/analyze_browser_compare.py` now de-duplicates same-isolation top-up
  rows by `pending_id` and adds built/used/missing lifecycle run counts to
  `Arti Profile Same-Isolation Top-Up A/B`. This showed the old sameiso2
  top-up attempt proof did not prove built or used top-up circuits. Focused
  proof `results/browser-compare-20260609T103420/browser-compare.json` also had
  `1` top-up attempt but `0` built and `0` used runs. The follow-up
  `results/browser-compare-20260609T103700/browser-compare.json` used
  `--arti-exit-same-isolation-min-assigned-streams 8`, made `0` top-ups, and
  still had sameiso2 prefer-cold beat baseline Arti in `3/3` paired download
  loads with a lower max load. The wider repeat
  `results/browser-compare-20260609T104252/browser-compare.json` passed quality
  but failed speed: homepage and download paired medians were slower than
  baseline Arti, download max load jumped to `39195.816ms`, and one top-up
  attempt still appeared at the exact `8` assigned-stream floor with no
  built/used lifecycle rows. Keep it lab-only. Source work should explain the
  page-resource queue and make the top-up floor strict before more
  cold-candidate tests.
- `upstream/arti/crates/tor-circmgr/src/mgr.rs` now makes that top-up floor
  strict: `torfast_should_top_up_same_isolation` uses
  `selected_assigned_streams > torfast_exit_same_isolation_min_assigned_streams()`.
  Its Rust unit test covers the boundary. Static proof
  `results/arti-quality-config-20260609T111042/arti-quality-config.json` passed,
  and rebuilt-browser proof
  `results/browser-compare-20260609T110147/browser-compare.json` passed quality
  with the only top-up at `9` assigned streams and floor `8`. This fixes the
  exact-floor leak, but sameiso2 prefer-cold remains lab-only because homepage
  speed regressed.
- `tools/analyze_browser_compare.py` now has `Arti Profile Queue Loss Reason`,
  which joins profile A/B load loss to late browser resource queue context and
  selected-circuit candidate context. On
  `results/browser-compare-20260609T110147/browser-compare.json`, it attributes
  the sameiso2 prefer-cold homepage regression to queued page resources on
  `Circ 3.12`, with no better-health or lower-assignment alternative rows. This
  points the next source work at single-circuit page-resource queue behavior.
- The same analyzer now also has `Arti Profile Queue Loss Mechanism`, which
  joins that profile-loss row to `Resource Queue Late Write Summary` and
  `Resource Queue Late Circuit Summary`. On the same proof, the joined row says
  the loss had late Tor data on `Circ 3.12` with `0` terminal pending bytes,
  `445/445` SENDMEs, min receive window `450`, and `0ms` write lag after
  terminal data. This points away from local pending bytes, SENDME/window
  blockage, or browser write lag.
- `tools/run_browser_compare.py` now exposes
  `--extra-arti-exit-select-prefer-cold-same-isolation-active-cap TARGET:CAP`.
  It builds a same-window health-aware avoid-bad-health sameiso prefer-cold
  profile with `TORFAST_EXIT_SELECT_MAX_ACTIVE_STREAMS` set only on that extra
  profile. The first proof,
  `results/browser-compare-20260609T113311/browser-compare.json`, passed
  quality but did not promote the idea: cap `1` had `0` active-cap moves and
  still lost check/homepage versus baseline Arti, although it helped download.
- `upstream/arti/crates/tor-circmgr/src/mgr.rs` now has a default-off saturated
  active-cap sameiso top-up path. If active-cap selection says all
  same-isolation candidates are saturated, the lab top-up gate may use
  `target + 1`, capped at the normal max target plus one. Static proof
  `results/arti-quality-config-20260609T120202/arti-quality-config.json` passed
  `56` checks. Browser proof
  `results/browser-compare-20260609T115220/browser-compare.json` passed quality
  and prefs, but activecap1 still lost check/homepage and counted `0` saturated
  top-ups, so this is not promotion proof.
- `results/browser-compare-20260609T120503/browser-compare.json` lowers the
  same-isolation floor to `4` for the same saturated active-cap lab shape. It
  proves the path can fire: activecap1 had `6` same-isolation top-ups and `6`
  active-cap saturated top-ups. It also rejects the idea as a speed path:
  activecap1 lost download by `+5601.995ms` paired median load, had a
  `72201.249ms` candidate max load, and every top-up lifecycle row was
  `missing`. Keep the source path lab-only and do not keep tuning the floor.
- `upstream/arti/crates/tor-circmgr/src/mgr.rs` now moves the saturated
  active-cap pressure check earlier in the sameiso top-up gate. When the lab
  active cap is set, `active_stream_cap_saturated` plus
  `selected_active_streams >= cap` can count as reuse pressure before the
  assigned-stream floor. Top-up logs include `selected_active_streams` and
  `select_max_active_streams`, and
  `tools/analyze_browser_compare.py` reports top-up max selected active streams
  plus max active cap. Static proof
  `results/arti-quality-config-20260609T122405/arti-quality-config.json` passed
  `56` checks. Browser proof
  `results/browser-compare-20260609T122640/browser-compare.json` passed quality
  and prefs, and activecap1 counted `9` same-isolation top-ups with all `9`
  active-cap saturated. This still rejects promotion: all top-up lifecycle rows
  were `missing`, and activecap1 lost check, homepage, and download versus
  baseline Arti by paired median load. Keep it lab-only; the next source target
  is not more sameiso active-cap top-up tuning.
- The same analyzer now prints terminal-only `Torfast SOCKS Relay Circuit
  Quality` rows even when detailed SOCKS stream-link rows are absent. This keeps
  low-log proof runs useful when the browser closes streams after enough data
  and Arti records them as `not_connected` terminal summaries.
- `tools/run_browser_compare.py --arti-socks-relay-byte-timing` now also sets
  `TORFAST_EXIT_SELECT_LOW_LOG_CONTEXT=1` and
  `TORFAST_CIRCUIT_CONGESTION_LOG=1` and
  `TORFAST_STREAM_LIFECYCLE_LOG=1`, so focused proof runs retain circuit
  candidate context, congestion rows, and stream lifecycle rows without
  requiring full debug logging. Normal info-level speed gates leave these
  extra rows off. The runner also raises the effective Arti log directive from
  default `info` to `info,tor_proto=debug` only for byte-timing proof runs, so
  `torfast relay receive delivered` and `torfast stream receiver read` rows are
  retained without unrelated full debug logs. Focused proof
  `results/browser-compare-20260609T223414/browser-compare.json` confirmed the
  analyzer now prints relay receive and browser resource stream-gap tables.
  Follow-up proof `results/browser-compare-20260609T223935/browser-compare.json`
  used that path with `--extra-arti-exit-select-load-aware`; it passed quality
  and beat local C Tor on download-page median load, but still had the
  `resource queue` blocker and a worse max tail than baseline Arti.
- `tools/analyze_browser_compare.py` now joins the byte-timing relay receive
  rows back into `Arti Selected-Circuit Network Evidence`, so each selected
  circuit can show `max observed stream gap ms`, `max circuit DATA gap ms`, and
  a `gap scope` label. Fresh proof
  `results/browser-compare-20260613T010206/browser-compare.json` passed quality
  but rejected speed. Its bad download rows were stream-specific on active
  selected circuits: `Circ 4.42` had a `5249ms` observed stream gap with only a
  `348ms` circuit DATA gap, and `Circ 4.27` had `4216ms` observed stream gap
  with only a `247ms` circuit DATA gap. Next source target is per-stream or
  browser-resource lifecycle on an active selected circuit, not whole-circuit
  quiet-DATA or another selector stack.
- `tools/analyze_browser_compare.py` now expands
  `Torfast Bad-Health Replacement Lifecycle` with build waiters/origin, page
  load time left after build, exit-open count, stream start/link timing,
  scheduler/use counters, and later-proof labels. Replaying
  `results/browser-compare-20260613T010206/browser-compare.json` shows the
  run `3` replacement built `Circ 3.49` with `0` build waiters and `8847ms`
  left before page load, but all `8` stream starts were before the build and
  `0` stream starts were after it. The new reason is
  `replacement missed active streams; no new stream starts after build`.
  This is analyzer-only proof; it does not change Tor behavior.
- Focused proof `results/browser-compare-20260613T011816/browser-compare.json`
  tested the existing bad-health hedge profile on the same download target
  with `--extra-arti-exit-select-bad-health-hedge-ms 800`. Quality passed and
  page-load A/B improved against base Arti: `4564.211ms` median load versus
  `6813.944ms`, with `3/3` paired wins. Do not promote it yet: Arti boot for
  the hedge profile was `29.166s`, boot+load lost badly to local C Tor, and
  selected-circuit evidence still shows stream-specific gaps on active selected
  circuits. Next proof should repeat this shape with boot controlled and keep
  checking selected-circuit stream gaps.
- Boot-controlled repeat
  `results/browser-compare-20260613T012330/browser-compare.json` used warm
  cache, shared Arti warm-cache seed, and `5` interleaved download runs with the
  same bad-health hedge profile. Quality passed, but the page-load win did not
  repeat: hedge won only `2/5` paired loads versus base Arti, paired median
  load delta was `+201.404ms`, summary median load delta was `+1264.319ms`, and
  max tail was worse by `+5749.181ms`. Treat bad-health hedge as rejected for
  promotion. It may still be useful as a mechanism trace, but the next source
  path is selected-circuit stream-gap and selector-health/capacity proof.
- Selector-health focused repeat
  `results/browser-compare-20260613T013523/browser-compare.json` tested
  `--extra-arti-exit-select-health-aware-min-assigned 2` on the same warm-cache
  shared-seed download proof with relay byte timing. Quality passed, but the
  profile is rejected: it won only `1/5` paired loads versus base Arti, had a
  `+2172.876ms` paired median load delta, and made max load worse by
  `+8909.791ms`. The worst selected-circuit row still had a stream-specific
  gap: `5056ms` observed stream gap versus `321ms` circuit DATA gap. This says
  gated selector health is not enough for the download burst; the source target
  stays the active selected stream/resource stall.
- Active-cap focused repeat
  `results/browser-compare-20260613T014814/browser-compare.json` tested
  `--extra-arti-exit-select-max-active-streams 2` on the same warm-cache
  shared-seed download proof with relay byte timing. Quality passed, but
  `activecap2` is rejected: it won `0/5` paired loads versus base Arti, had a
  `+5708.825ms` paired median load delta, and made max load worse by
  `+45935.983ms`. The worst selected-circuit row still had a stream-specific
  gap: `4879ms` observed stream gap versus `347ms` circuit DATA gap. This says
  the simple active-stream cap is not the fix for this burst; inspect the
  active stream/resource stall instead of retuning selector knobs.
- `tools/analyze_browser_compare.py` now also prints
  `Arti Selected Stream Gap Cross-Stream Activity`. It finds the selected
  stream's DATA gap window and counts same-circuit DATA on other streams during
  that window. Regenerated active-cap proof shows `Circ 1.45` stream `48266`
  had a `1576ms` gap while the same circuit delivered `224` other DATA cells
  across `5` streams, with `no local block seen`. Regenerated selector-health
  proof shows `Circ 0.68` stream `38116` had a `1372ms` gap while the same
  circuit delivered `220` other DATA cells across `5` streams. This makes the
  next source target per-stream/resource flow, not whole-circuit silence,
  selector retuning, active cap, scheduler, SENDME/window, or local copy.
- The same analyzer now prints `Arti Selected Stream Gap Resource Overlap`.
  It includes navigation as a matched resource-like row. Replaying active-cap
  run `5` shows the in-page stream `48266` gap is on the navigation stream but
  the navigation resource is already inactive; the older multi-second stream
  gaps in the generic gap table end after page load and should not drive the
  next speed patch by themselves. Replaying selector-health run `4` maps stream
  `38116` to `TBA10.0.png`, where the selected gap overlaps server wait and
  response receive.
- The analyzer now also prints `Arti Selected Stream Gap Slot Pressure`. It
  checks same-origin/protocol browser resources during the exact selected-stream
  gap and prints matched-resource active overlap. Replaying active-cap run `5`
  stream `48266` shows `6` active same-origin HTTP/1.1 slots, `11` active
  same-origin resources, and `7` queued-at-least-`1000ms` resources, but the
  matched navigation resource had `0.000ms` active overlap. Treat that as
  page-level same-origin pressure, not proof that stream `48266` itself was
  waiting on a browser resource. Replaying selector-health run `4` stream
  `38116` gives the stronger active-stall row: matched `TBA10.0.png` was active
  for `346.756ms` in request wait while same-origin HTTP/1.1 was full (`6`
  active slots), with `11` active resources, `5` queued-at-least-`1000ms`
  resources, `7240.090ms` request wait, and `883.351ms` response receive. The
  table now also separates timing confidence from stream-set confidence by
  carrying Arti `target_label`, matching the resource host, and checking
  resource lifetime against SOCKS stream lifetime. The active-stall row has
  `11` joined active resources, but all `11` are `ambiguous` across streams
  `38116` and `38117` on `Circ 0.68` (`0` exact joins). Active-cap run `5`
  stream `48266` also has `11` ambiguous active joins and `0` exact joins; the
  old `high:3, low:8` numbers are timing confidence only, and the matched
  navigation resource is inactive. Next source inspection should add
  browser-side socket/request tagging, or another exact resource-to-SOCKS-stream
  tag, before changing Tor circuit selection, stream scheduling, or
  request-wait behavior.
- `tools/run_browser_compare.py --browser-net-log` is now the default-off lab
  probe for that source inspection. It sets Firefox/Tor Browser
  `MOZ_LOG=timestamp,nsHttp:5,nsSocketTransport:5,nsHostResolver:3`, stores raw
  files in each profile's `browser_net_logs/`, and writes a compact
  `browser_net_log` summary into each run result. This is evidence capture
  only; it should not be treated as a Tor behavior change or a promotion proof
  until a real browser run shows exact resource-to-SOCKS mapping.
- `tools/analyze_browser_compare.py` now prints `Browser Net Log Resource
  Evidence` when those files are present. It parses Firefox HTTP channel
  pointer, `channelId`, URI, start/data/stop timing, parent `HttpChannelParent`
  rows, parent `nsHttpChannel` transaction rows, and Firefox proxy socket rows.
  Proof `results/browser-compare-20260613T031520/browser-compare.json` matched
  all Arti run resources (`36/36`) and local C Tor resources (`35/35`) to
  browser channel IDs. It found parent-channel rows for `36` resources in each
  profile and bridged `11` Arti resources plus `9` local C Tor resources to
  Firefox proxy socket rows. It still shows `SOCKS stream id = no`, because the
  Firefox log does not include the local outgoing proxy TCP port. Next source
  target: connect Firefox proxy socket rows to SOCKS stream IDs, or add a
  same-run tag at the proxy/browser boundary before patching stream scheduling.
- `tools/run_browser_compare.py --byte-tap` now records browser peer,
  tap-listener, and upstream proxy socket ports for each tap connection. Arti's
  default-off `TORFAST_SOCKS_RELAY_BYTE_TIMING=1` rows now include
  `client_peer_port`, without changing the listener isolation key. The analyzer
  can join byte tap `upstream_local_port` to Arti `client_peer_port` and only
  marks `SOCKS stream id = yes` when the Firefox proxy socket has one unique
  matching target/time candidate. Proof
  `results/browser-compare-20260613T035046/browser-compare.json` passed quality
  and had matching peer ports on `8/8` Arti SOCKS rows, but still had `0` exact
  browser-resource stream rows because Firefox opened several same-host proxy
  sockets within a few milliseconds. Next source target is browser-side local
  port capture or another same-run browser/socket tag; do not guess by nearest
  timestamp.
- `tools/run_browser_compare.py --browser-serial-http-connections` is a
  lab-only proof switch that sets Firefox HTTP connection limits to `1` through
  Marionette and records the old/new pref values in each run. Proof
  `results/browser-compare-20260613T040414/browser-compare.json` passed quality
  and produced one exact browser-resource-to-Arti-stream row:
  `channelId=17179869197` to byte-tap connection `3`,
  `upstream_local_port=61603`, Arti `client_peer_port=61603`, `timing_id=3`,
  `stream_id=41201`. This proves the full evidence chain, but only with
  browser concurrency constrained. Normal-mode speed work still needs a true
  browser-side local port or socket tag so the analyzer can join concurrent
  same-host Firefox sockets without changing browser behavior.
- `tools/run_browser_compare.py` now also installs a default-off Marionette
  browser activity observer when `--browser-net-log` is enabled. It records
  HTTP observer rows with channel id, URI, method, address, and port fields, and
  `tools/analyze_browser_compare.py` can use those rows before falling back to
  byte-tap timestamp matching. Normal proof
  `results/browser-compare-20260613T042228/browser-compare.json` passed quality
  without serial browser limits, but Tor Browser proxied HTTPS exposed
  `0.0.0.0:443` with local port `0`, not the local SOCKS port. The new Firefox
  transaction-to-connection parser found `41` Arti HTTP connection rows, but
  exact SOCKS stream rows stayed `0` because several same-host sockets opened
  within the same few milliseconds. Next source target is still an exact
  browser/proxy boundary tag; do not guess by timestamp rank.
- `tools/run_browser_compare.py --byte-tap` now also parses browser-to-proxy
  SOCKS5 client requests in the neutral tap. It records methods, command,
  target host/port, request time, auth presence, auth lengths, and short
  SHA256 prefixes for username/password, but not the raw auth secret. The
  analyzer prints these rows in `Neutral Byte Tap SOCKS Request Evidence`.
  Proof `results/browser-compare-20260613T044713/browser-compare.json` passed
  quality and captured exact request metadata for every tapped connection
  (`11/11` Arti and `12/12` local C Tor). This proves target/auth capture at
  the browser/proxy boundary, but it still does not replace a browser-side
  local SOCKS port or per-socket tag for same-host resource-to-stream joins.
- `tools/analyze_browser_compare.py` also parses Firefox raw
  `nsHttpConnectionInfo` SOCKS auth digest bytes from parent `MOZ_LOG` rows and
  reports `CI auth rows` plus `CI auth tap matches` in `Browser Net Log Resource
  Evidence`. On `results/browser-compare-20260613T044713/browser-compare.json`,
  every parsed CI auth row matches a tap auth hash (`35/35` Arti, `36/36` local
  C Tor), but only `8` Arti rows have exact SOCKS stream IDs. The digest proves
  the browser-side isolation bucket; it does not uniquely identify each
  same-host concurrent socket.
- `tools/run_browser_compare.py --browser-net-log` now installs an
  `nsIHttpActivityObserver` through Marionette in addition to the observer-topic
  rows. It records activity subtype/timestamp, channel id, URI, and
  `subject_connectionInfoHashKey` when the browser exposes it. The analyzer
  prints `Browser Activity Probe Evidence` with activity row counts, CI
  auth/tap matches, CI bucket counts, nonzero local-port rows, and exact local
  SOCKS rows. Proof `results/browser-compare-20260613T050610/browser-compare.json`
  passed quality and captured CI auth/tap matches for all parsed activity rows
  (`488/488` Arti and `445/445` local C Tor), but still found `0` nonzero local
  SOCKS port rows. This rules out the runtime activity API as the missing
  per-socket join; browser source/local-port tagging is still needed.
- `tools/run_browser_compare.py --byte-tap-socks-reply-bind-port-tag` is a
  default-off lab-only proof switch for exact browser/proxy boundary tagging.
  When the neutral byte tap sees a SOCKS5 CONNECT success reply, it rewrites the
  reply bind port to a deterministic per-connection `400xx` value and stores
  the original/tagged ports in `byte_tap.connections`. It does not change Tor
  stream payload bytes and should not be used as a normal speed setting. Proof
  `results/browser-compare-20260613T052031/browser-compare.json` passed quality;
  the browser activity probe exposed those tags as `localPort`, and
  `tools/analyze_browser_compare.py` now reports `SOCKS reply tag rows` plus
  `tag connection matches`. This gives a normal-concurrency per-socket tag for
  exact resource-to-SOCKS-stream proof before any stream/resource behavior
  patch.
- `tools/analyze_browser_compare.py` now uses that reply tag to produce exact
  `Browser Activity Tagged Stream Resources` and grouped stream rows. It joins
  Firefox activity channel id plus tagged local port to byte-tap connection,
  then byte-tap upstream port to Arti `client_peer_port` and stream id. Fresh
  download proof `results/browser-compare-20260613T053122/browser-compare.json`
  produced `34` Arti stream rows and showed the exact slow group: timing id `6`,
  stream `38096`, `Circ 3.5`, `5` resources, max browser queue `7083.475ms`,
  top resource `favicon.ico`. Treat this as the next source target for selected
  stream/resource queue tail proof. It is not a selector-retuning signal by
  itself.
- The tagged sequence table orders resources on the same stream and shows the
  previous response edge. On the same `053122` proof, several requests on the
  slow tagged streams start `0.000ms` after the prior response, and
  `favicon.ico` on stream `38096` starts `300.006ms` after `github.png`. This
  points source inspection toward reducing active-stream response/relay tails
  in `arti/src/proxy/socks.rs`, `tor-proto/src/stream/raw.rs`, and the
  circuit/stream receive path, while keeping Tor Browser's normal HTTP
  connection caps unchanged.
- The analyzer also has tag-only `Browser Activity Tagged Connection
  Resources`, `Groups`, and `Sequence` tables. These do not need Arti
  `client_peer_port` stream-link logs, so they can compare local C Tor and Arti
  from the same neutral SOCKS reply tag. On proof
  `results/browser-compare-20260613T053122/browser-compare.json`, Arti had
  `330` tagged activity rows matching `12` tap connections; local C Tor had
  `326` rows matching `8` tap connections. The worst Arti tagged connection
  queue was `7083.475ms` on connection `7` / tag `40007`; the worst local C Tor
  tagged connection queue was `4666.760ms` on connection `8` / tag `40008`.
  Use this table as the baseline comparison when changing active-stream
  response/relay behavior. It is analyzer proof only and must not be treated as
  a speed patch.
- `upstream/arti/crates/arti/src/proxy.rs` owns the default-off
  `TORFAST_APP_STREAM_BUF_LEN` parser. It keeps the normal `4096` byte proxy
  app/Tor stream `BufReader` capacity unless the env var is set, and rejects
  values below the SOCKS buffer length or above `1048576`.
  `upstream/arti/crates/arti/src/proxy/socks.rs` and
  `upstream/arti/crates/arti/src/proxy/http_connect.rs` use
  `super::app_stream_buf_len()` for Tor stream readers.
  `tools/run_browser_compare.py` exposes this as
  `--arti-proxy-app-buffer-len` and same-window
  `--extra-arti-proxy-app-buffer-len` profiles. Proofs
  `results/browser-compare-20260613T060228/browser-compare.json` (`32768`) and
  `results/browser-compare-20260613T060436/browser-compare.json` (`8192`) both
  passed quality but loaded slower and raised tagged queue tails. Keep the knob
  as lab-only negative proof; do not promote larger app stream buffers.
- `upstream/arti/crates/arti/src/proxy/socks.rs` now raises
  `torfast socks byte event` rows to INFO when
  `TORFAST_SOCKS_RELAY_BYTE_TIMING=1`, using the default-off `ByteTiming`
  `info_events` flag. `tools/analyze_browser_compare.py` joins exact tagged
  stream rows to SOCKS timing rows and retained byte-event tails, then prints
  write-tail columns in the tagged resource, group, and sequence tables.
  Proof `results/browser-compare-20260613T062407/browser-compare.json` passed
  quality but was slower than local C Tor (`8829.720ms` versus `6353.880ms`).
  It retained `client_to_tor` and `client_to_tor_write` byte events but no
  `tor_to_client` or `tor_to_client_write` byte events, so the next source
  target is passive browser-facing write-half instrumentation.
- Do not replace `torfast_copy_buf_bidirectional_browser_style()` with a
  hand-rolled timed copy loop for this proof. Rejected proof
  `results/browser-compare-20260613T063857/browser-compare.json` failed Arti
  quality with Firefox `nssFailure2`, while local C Tor passed, and still did
  not retain any `tor_to_client` / `tor_to_client_write` byte events. The
  source was restored to the existing browser-style copy path.
- The passive write-tail hook now uses `CountingWriter` around the split writer
  halves inside
  `torfast_copy_buf_bidirectional_browser_style_with_write_timing()`. It keeps
  the existing `futures_copy::copy` relay path and the same close behavior.
  `CountingBufStream` now remains read-side only. `tools/run_browser_compare.py`
  keeps `torfast socks byte event` rows for timing ids linked to retained
  terminal stream rows, so early hostname write rows are not dropped before
  analysis. Proof `results/browser-compare-20260613T065745/browser-compare.json`
  passed quality and retained all byte directions across timing ids `3..9`,
  letting the tagged resource tables populate `last write ms` and
  `response after write ms`. Speed is still rejected: Arti loaded in
  `4562.406ms` versus local C Tor `4251.651ms`, with boot `24.469s` versus
  `13.565s`.
- `tools/analyze_browser_compare.py` now prints
  `Browser Activity Tagged Stream Queue Cause`. It reuses the exact tagged
  stream sequence rows and computes how much queued time is explained by the
  previous response on the same stream. Replaying
  `results/browser-compare-20260613T065745/browser-compare.json` shows the top
  queued resources have `0.000ms` unexplained queue after the previous response;
  for example `tor-logo@2x.png` on timing id `5` / stream `58501` had
  `2450.049ms` queue and `2450.049ms` blocked by the prior same-stream
  `arrow-down.png` response. Use this as source direction: same-stream
  response-chain tail first, not browser write lag, buffer size, or selector
  retuning.
- `tools/analyze_browser_compare.py` also prints
  `Browser Activity Tagged Connection Queue Cause Summary` and detail rows.
  These work for both Arti and local C Tor because they use only the neutral
  SOCKS reply tag. Replaying
  `results/browser-compare-20260613T065745/browser-compare.json` shows Arti
  had `33334.000ms` tagged connection queue with `99.800%` blocked by previous
  responses, while local C Tor had `29050.581ms` with `99.943%` blocked. The
  summary also splits previous blockage into pre-request queue, wait, and
  receive: Arti had `19617.059ms` pre-request, `9316.853ms` wait, and
  `4333.420ms` receive blocked; local C Tor had `17383.681ms`, `9683.527ms`,
  and `1966.706ms`. It now joins neutral byte-tap proxy data inside the
  previous receive window: Arti had `10` rows with proxy data, `142.896 KiB`
  total, and `180.006ms` median browser-after-last-proxy-data (`438.927ms`
  max), while local C Tor had `9` rows, `313.016 KiB`, and `19.776ms` median
  (`350.524ms` max). Use this as the same-window baseline for response-tail,
  browser finish after last proxy byte, and inherited queue-chain changes.
- `upstream/arti/crates/arti/src/proxy/socks.rs` now has default-off local
  Tor-to-browser write coalescing through
  `TORFAST_SOCKS_TOR_TO_CLIENT_COALESCE_BYTES` (`498..65536`). It wraps only
  the local SOCKS Tor-to-client read side with `ReadyCoalescingReader`; when
  unset, it delegates to the normal read path. `tools/run_browser_compare.py`
  exposes same-window extra profiles with
  `--extra-arti-socks-tor-to-client-coalesce-bytes`, records
  `arti_socks_tor_to_client_coalesce_bytes`, and names the first profile
  `arti_release_browser_torclientcoalesceN`. Quality guard:
  `tools/check_arti_quality_config.py` has
  `socks_tor_to_client_coalesce_is_default_off_lab_only`. Proof
  `results/browser-compare-20260613T082131/browser-compare.json` (`4096`)
  passed quality but rejects promotion: it changed chunk shape and lowered
  median response-end-after-last-proxy-data (`168.672ms` default Arti to
  `112.190ms`) plus max tagged queue (`1916.705ms` to `1483.363ms`), but
  worsened load (`3574.126ms` to `4545.453ms`) and total tagged queue
  (`24350.487ms` to `28000.560ms`). Keep it lab-only negative proof; local
  write coalescing alone is not the response-tail fix.
- `upstream/arti/crates/tor-circmgr/src/mgr.rs` now allows the default-off lab
  `TORFAST_EXIT_SELECT_HEALTHY_OVER_COLD_MIN_ASSIGNED=0`; the runner validation
  in `tools/run_browser_compare.py` accepts `0`, and
  `tools/check_arti_quality_config.py` checks that lower bound. The focused
  unit test proves threshold `0` can move a fresh cold selected circuit to a
  proven healthy candidate while still rejecting a low-score candidate. Browser
  proof `results/browser-compare-20260613T071358/browser-compare.json` passed
  quality but showed `0` healthy-over-cold moves, so the observed load win came
  from load-aware selection, not this new threshold. Keep it lab-only.
- `tools/analyze_browser_compare.py` now distinguishes real selector-health
  move alternatives from health alternatives below the safe move-score floor.
  The default floor is `65536`, or the profile's saved
  `arti_exit_select_health_min_move_score_bps` when a lab proof lowers it. The
  queue-choice summary now prints below-floor rows, max alt score, and score
  floor. Replaying `results/browser-compare-20260613T071358/browser-compare.json`
  changed the old broad `better-health alternative` rows to
  `below-floor health alternative`, so the right next proof is stream-gap tail
  behavior, not another health-score retune.
- `tools/analyze_browser_compare.py` now adds same-circuit relay DATA context to
  `Browser Resource Stream Gap Context`. Each stream-gap row prints other DATA
  cells, other stream count, same-circuit DATA KiB, max circuit DATA gap inside
  the stream gap, and a gap-scope hint. Replaying
  `results/browser-compare-20260613T071358/browser-compare.json` showed the
  worst threshold-zero run `3` stream gaps were not explained by selector-health
  scoring: timing id `25` / stream `1045` had a `5056ms` stream gap with `2`
  same-circuit other DATA cells, but still had a `4734ms` max circuit quiet
  span inside that gap.
- Sequential `run_arti()` defines
  `arti_exit_select_health_aware_min_assigned=None`; this fixes the harness
  crash hit by the first `--browser-net-log` probe before Arti started.
- `upstream/arti/crates/tor-circmgr/src/mgr.rs` emits the default-off
  `TORFAST_EXIT_SELECT_LOW_LOG_CONTEXT` selector row at `INFO` whenever that
  env flag is enabled. This avoids losing selector context when a proof run uses
  `info,tor_proto=debug`: `tor_proto` debug is on, but `tor_circmgr` debug is
  not. Proof `results/browser-compare-20260609T225109/browser-compare.json`
  confirmed `Torfast Circuit Selection` rows are captured again.
- `upstream/arti/crates/tor-proto/src/circuit/circhop.rs` owns the default-off
  `TORFAST_STREAM_LIFECYCLE_LOG` diagnostic. When enabled, it emits
  `torfast stream lifecycle` rows with stream id, relay command, queue bytes,
  close flag, optional channel queue counts, and delivery state. The send-side
  `channel_queued` rows are emitted from
  `upstream/arti/crates/tor-proto/src/client/reactor/circuit.rs`.
  They include `channel_circ_id`, the protocol circuit id used by the channel
  reactor. `channel_queue_count_available` marks whether the channel queue count
  is real; the analyzer hides unavailable channel queue maxima and counts them
  as unknown instead.
- `upstream/arti/crates/tor-proto/src/channel/reactor.rs` emits default-off
  `torfast channel flush` rows when `TORFAST_STREAM_LIFECYCLE_LOG=1`. These
  rows mark cells leaving the channel reactor for the TLS/network sink with
  `channel_circ_id`, channel command, optional reactor queue count, and
  `delivery="channel_flushed"`. `tools/analyze_browser_compare.py` parses them
  into `Torfast Channel Flush` and `Torfast Channel Queue To Flush`, matching
  stream `channel_queued` rows to later flush rows by `channel_circ_id`.
  The analyzer also emits `Torfast Stream Response Gaps` from lifecycle rows,
  summarizing queued BEGIN-to-CONNECTED and queued DATA-to-DATA response times
  by stream. `Notable Torfast SOCKS Stream Lifecycle` reuses the same lifecycle
  rows for slow successful or failed SOCKS streams, so slow relay/connect rows
  can be classified as DATA delivered, no EOF, no CONNECTED, queue full, or
  limited retained-tail evidence.
  `tools/analyze_browser_compare.py` parses those rows into
  `Torfast Stream Lifecycle` and the failed-run
  `Browser Failed Run Stream Lifecycle` table, which joins SOCKS timing ids to
  lifecycle states such as `BEGIN queued to channel, no CONNECTED` or
  `DATA delivered, no EOF`.
- `tools/analyze_browser_compare.py` now also prints
  `Browser Failed Run Relay-Tail Circuit Concentration`. It groups failed-run
  relay-tail SOCKS rows by circuit and reports tail count, target kinds, no-byte
  versus partial-byte shapes, total Tor bytes, max relay time, max idle after
  the last Tor byte, reader terminal counts, lifecycle states, and top timing
  ids. The first real proof shows `15/15` failed combo download tails on
  `Circ 4.14` in
  `results/browser-compare-20260609T083656/browser-compare.json`, and `21/24`
  default-Arti download tails on `Circ 3.14` in
  `results/browser-compare-20260609T084334/browser-compare.json`.
- `tools/analyze_browser_compare.py` also prints
  `Browser Successful Run Relay-Tail Circuit Concentration`. It reuses the same
  relay-tail grouping for completed browser runs, so accepted max-tail
  regressions are visible. Replaying
  `results/browser-compare-20260609T090433/browser-compare.json` shows the
  guarded source-spread-plus-load-aware profile had `4` accepted slow hostname
  tails on `Circ 3.9` in run `3`, while the older source-spread combo's accepted
  tails were one stream per circuit. This makes resource-tail circuit
  concentration the next proof target.
- The same analyzer now carries same-close SOCKS proof into the promotion
  summary. It counts slow streams whose `copy_error_kind=not_connected` also
  has client EOF and Tor read error at the same moment, and prints the max time
  from last Tor byte to browser EOF. It also counts client reset plus outbound
  END at the same moment as a resolved close shape, and it treats remote END
  delivered plus client close as resolved too. Same-close, client-reset, and
  remote-END rows are separated from unresolved slow streams before choosing
  promotion blockers, so browser-close tails stay visible without falsely
  keeping slow-stream blockers alive. The `Arti Promotion Unresolved Slow
  Streams` table then lists any remaining stream-risk rows with timing id,
  kind, connect/relay time, copy error, circuit, and stream id. Resource queue
  now blocks promotion only when Arti's target-level queue delta is worse than
  local C Tor; queues that exist in both profiles but are no worse in Arti stay
  visible in queue tables without becoming blockers. The promotion summary also
  has a `boot slower` blocker, reports boot delta, and picks `slow target proof`
  when the next needed work is a concrete slow page instead of an unresolved
  stream proof. When that proof is needed, the analyzer prints `Arti Promotion
  Slow Target Proof`, which joins the slow target's worst browser run to
  navigation timing, the navigation-matched SOCKS stream, and the worst stream
  receiver/lifecycle row. Resource-queue promotion blockers now require a real
  target-level regression: more resources queued for at least `1000ms`, or a
  median/max fetch-to-request delta over `100ms`. Tiny positive median noise is
  still visible in queue tables but no longer blocks promotion by itself.
- `scripts/build_arti_release_flowctl.sh` builds a separate release Arti binary
  under `upstream/arti/target/flowctl/release/arti` with Cargo feature
  `flowctl-cc`. This does not replace the normal release binary.
- `tools/run_browser_compare.py --extra-arti-bin LABEL:PATH` can add a second
  Arti binary as a same-window interleaved A/B profile. The result JSON records
  each Arti profile's binary path and `--version` output.
- `upstream/arti/crates/arti/Cargo.toml`,
  `upstream/arti/crates/arti-client/Cargo.toml`,
  `upstream/arti/crates/tor-circmgr/Cargo.toml`, and
  `upstream/arti/crates/tor-proto/Cargo.toml` carry the `flowctl-cc` feature
  chain. `cargo check -p arti --features flowctl-cc -vv` shows
  `--cfg feature="flowctl-cc"` reaching `arti` and `tor-proto`; the Arti
  `--version` optional-features text still prints `<none>`, so use runtime
  circuit congestion rows to prove whether the profile is fixed-window or
  Vegas.
- `upstream/arti/crates/tor-circmgr/src/mgr.rs` now also has a default-off
  first-stream same-isolation prewarm lab switch:
  `TORFAST_EXIT_SAME_ISOLATION_PREWARM_FIRST_STREAM`. The runner exposes it
  through
  `--extra-arti-exit-select-prefer-cold-same-isolation-prewarm-target`, and
  `tools/analyze_browser_compare.py` reports `topup first-stream prewarm`.
  Static proof `results/arti-quality-config-20260609T125441/arti-quality-config.json`
  passed `56` checks. Browser proof
  `results/browser-compare-20260609T125803/browser-compare.json` rejects the
  idea: homepage timed out, screenshot proof was missing, and all `3` top-up
  lifecycle rows were `missing`.
- `upstream/arti/crates/tor-circmgr/src/mgr.rs` now forces
  same-isolation lab top-up build lifecycle rows to `info`, by setting
  `torfast_force_info_lifecycle` only on those top-up plans. This keeps
  behavior unchanged but prevents fast build-complete rows from disappearing at
  info log level. `tools/analyze_browser_compare.py` now also reports
  `candidate_seen_no_build_log` when old logs show a new zero-assigned
  same-isolation candidate after a top-up but no build-complete row. Static
  proof `results/arti-quality-config-20260609T132017/arti-quality-config.json`
  passed `56` checks.
- `tools/analyze_browser_compare.py` treats a later
  `torfast circuit selection open` row for the built top-up circuit as use
  proof, even if lower-level stream-link rows are absent from retained logs.
  The proof `results/browser-compare-20260609T132248/browser-compare.json`
  confirms the forced-info lifecycle path: two sameiso2 prewarmfirst top-ups
  built at `517ms` and `615ms`, and one was selected later. It is still lab-only
  because the profile loses check and still trails local C Tor on check/download
  summary medians.
- `tools/run_browser_compare.py` now also exposes the lighter same-isolation
  prewarm profile through
  `--extra-arti-exit-same-isolation-prewarm-target`. It sets
  `TORFAST_EXIT_SAME_ISOLATION_TARGET` plus
  `TORFAST_EXIT_SAME_ISOLATION_PREWARM_FIRST_STREAM`, but does not turn on
  load-aware, health-aware, avoid-bad-health, or prefer-cold selection. Proof
  `results/browser-compare-20260609T133530/browser-compare.json` passed quality
  and prefs, made `4` built top-ups, and showed `0` retained stream uses; boot
  stayed the blocker at `+17.136s` versus local C Tor.
- `tools/run_browser_compare.py` now saves filtered `boot.signal_lines`.
  `tools/run_boot_compare.py` and `tools/analyze_browser_compare.py` prefer
  that list for boot timelines when present, falling back to old `boot.lines`
  for older JSON. Proof
  `results/browser-compare-20260609T135043/browser-compare.json` shows this
  keeps boot directory signals even with relay lifecycle log flood. The same
  proof keeps light sameiso prewarm rejected: boot was near local C Tor, but
  download regressed by `+8754.013ms` and the built top-up was not used.
- `tools/run_browser_compare.py` also exposes a load-aware version of that
  runner-only proof through
  `--extra-arti-exit-load-aware-same-isolation-prewarm-target`. It creates
  `arti_release_browser_loadaware_sameiso2_prewarmfirst`, setting load-aware
  selection plus same-isolation target and first-stream prewarm, while leaving
  health-aware, avoid-bad-health, and prefer-cold selection off. Proof
  `results/browser-compare-20260609T135829/browser-compare.json` passed quality
  and prefs and proved one built top-up was selected later, but the profile
  still lost median load to local C Tor on all targets and had a bad homepage
  tail. Keep it lab-only.
- `tools/analyze_browser_compare.py` now matches same-isolation top-up terminal
  build rows across later same-profile retained log lines by `pending_id` and
  timestamp. This fixes proofs where the top-up request appears in one retained
  run bucket and the later build failure appears in another target/run bucket.
  Replaying `results/browser-compare-20260609T140545/browser-compare.json`
  changes the bad-health-gated load-aware sameiso row from `missing` to
  `build_failed` with `4511ms` pending age. The profile still rejects: it won
  check, but lost homepage/download to local C Tor and the top-up was not used.
- `tools/analyze_browser_compare.py` now prints `Torfast Stream Scheduler Late
  Circuit Fairness` after the late-circuit queue table. It joins late browser
  queue circuits to scheduler picks and reports picked-stream count, top-stream
  share, same-stream streak, and a proof hint. `upstream/arti/crates/tor-proto`
  now has default-off `TORFAST_STREAM_SCHEDULER_LOG`; when enabled, existing
  scheduler `debug!` rows are raised to `info!`. `tools/run_browser_compare.py`
  sets it with `--arti-socks-relay-byte-timing`, and static proof
  `results/arti-quality-config-20260609T142930/arti-quality-config.json`
  passed `57` checks.
- `tools/run_browser_compare.py` now filters run-level proxy proof rows inside
  `record_proxy_run_signals` to the current browser run's timestamp window. It
  uses `started_epoch_ms`, `elapsed_ms`, `nav_finished_epoch_ms`, and proxy row
  timestamps from `event_epoch_ms`, SOCKS epoch fields, or leading ISO log
  times. This fixed the polluted failed-run evidence seen in
  `results/browser-compare-20260609T225534/browser-compare.json`. Fresh clean
  proof `results/browser-compare-20260609T233054/browser-compare.json` passed
  quality but rejects load-aware promotion: load-aware median download load was
  `6850.239ms` versus baseline Arti `4515.505ms` and local C Tor `4735.462ms`,
  with `0` scheduler blocked hops.
- `tools/analyze_browser_compare.py` now builds direct per-circuit selection
  context rows for selected-circuit evidence, so slow terminal streams can get
  choice context even when the browser resource-queue join has no matching
  cluster. Replaying `results/browser-compare-20260609T233054/browser-compare.json`
  shows the main slow load-aware circuits (`Circ 2.13` and `Circ 3.5`) had only
  one eligible open circuit logged and no better alternative. Keep load-aware
  lab-only and do not retune scheduler, sameiso target, or active cap from this
  proof.
- `tools/run_browser_compare.py` now adds bounded pre-run circuit-selection
  context to a run when the same circuit appears inside that run's proxy rows.
  This keeps reused-circuit selector context for the next proof while preserving
  the run-window filter: unrelated old selection rows and post-run rows are
  still dropped.
- Fresh proof `results/browser-compare-20260609T234755/browser-compare.json`
  confirms the runner/analyzer path works on a new capture, but rejects
  promotion: load-aware beat local C Tor in that window, yet lost to baseline
  Arti on `0/3` paired loads with a `+1496.606ms` summary median delta and a
  worse max tail.
- `upstream/arti/crates/tor-circmgr/src/mgr.rs` now raises
  `torfast circuit selection build complete/failed/canceled` rows to `INFO`
  when `TORFAST_EXIT_SELECT_LOW_LOG_CONTEXT=1`, so fast pending-built circuits
  can be seen in normal proof runs. The runner keeps matching pre-run
  build-complete rows for circuits later seen inside the run window, and the
  analyzer reports that as `pending build context only`.
- Fresh proof `results/browser-compare-20260609T235823/browser-compare.json`
  confirms the fast-build proof path is live after a release rebuild. The saved
  load-aware proof includes retained build-complete context for `Circ 2.6`
  (`956ms`, exit usage). The selected-circuit evidence table did not need the
  pending-build fallback in this one-run window, so this is capture proof only,
  not selector promotion proof.
- `tools/run_browser_compare.py` now also exposes
  `--extra-arti-exit-health-aware-same-isolation-prewarm-target`. It creates
  `arti_release_browser_healthaware_sameisoN_prewarmfirst`, setting
  load-aware plus health-aware selection, same-isolation target, and first-stream
  prewarm, while leaving avoid-bad-health and prefer-cold selection off. Proof
  `results/browser-compare-20260609T144811/browser-compare.json` rejects it:
  quality passed, but median load was `12463.985ms` and max load was
  `118389.890ms` on the download page, while baseline Arti was `3623.586ms`.
  Keep this as a lab-only negative proof.
- `tools/run_browser_compare.py` now exposes
  `--extra-arti-exit-load-aware-same-isolation-target`. It creates
  `arti_release_browser_loadaware_sameisoN`, setting load-aware exit selection
  plus `TORFAST_EXIT_SAME_ISOLATION_TARGET=N`, without health-aware,
  avoid-bad-health, prefer-cold, or first-stream prewarm. Target `2` proof
  `results/browser-compare-20260609T182940/browser-compare.json` passed quality
  but lost median load and made `0` same-isolation topups. Target `3` proof
  `results/browser-compare-20260609T183428/browser-compare.json` failed quality
  and hit a `119453.966ms` max load. Keep the flag only as a negative lab
  proof.
- `upstream/arti/crates/tor-circmgr/src/mgr.rs` now also has a default-off,
  bounded same-isolation lab trigger:
  `TORFAST_EXIT_SAME_ISOLATION_OTHER_ISOLATION_MIN`. It only applies to exit
  usage, is capped at `64`, and lets same-isolation top-up fire only when enough
  otherwise usable open exits are owned by other isolation groups. The runner
  exposes it through
  `--extra-arti-exit-same-isolation-other-isolation-pressure TARGET:MIN`, and
  the analyzer reports other-isolation pressure, max other isolation, and the
  floor. Static proof
  `results/arti-quality-config-20260609T193910/arti-quality-config.json` passed
  `58` checks. Browser proof
  `results/browser-compare-20260609T194122/browser-compare.json` passed quality
  and prefs on the download target: `sameiso2_otheriso3` completed `3/3`, median
  load was `3365.224ms` versus default Arti `4688.072ms` and local C Tor
  `5541.779ms`, with `1` top-up built and used. Keep it lab-only until broader
  A/B proof covers more targets, runs, and repeat windows.
- Broader proof
  `results/browser-compare-20260609T194752/browser-compare.json` rejects
  `sameiso2_otheriso3` for promotion. The candidate completed `15/15` browser
  runs and prefs stayed valid, but the analyzer failed overall quality because
  default Arti timed out on one homepage run. More importantly, the candidate
  lost the broad speed bar: homepage median load was `7604.470ms` versus default
  Arti successful-run median `5224.163ms` and local C Tor `5430.312ms`, and
  download median load was `7944.794ms` versus local C Tor `5795.200ms`. The
  A/B risk row says homepage paired wins `1/4`, summary median load delta
  `+2380.307ms`, and max tail delta `+7731.781ms`. The analyzer says the worst
  homepage queue case was late selected-circuit DATA, not scheduler or
  congestion. Keep the flag as a lab hook; do not promote the `2:3` profile.
- `tools/analyze_browser_compare.py` now prints
  `Arti Profile Same-Isolation Top-Up Timing Diagnosis` after the top-up A/B
  table. It reuses `torfast_same_isolation_topup_lifecycle_rows` and groups
  top-up runs by target, reporting built/seen top-ups, used top-ups,
  first-selected top-ups, median build age, load time left after build, first
  candidate/use timing, and used versus unused run deltas. Replaying
  `results/browser-compare-20260609T194752/browser-compare.json` shows homepage
  top-up runs were slower whether used or not, while download only helped when
  the top-up was used. This turns the next bottleneck from "top-ups are too
  late" into "same-isolation capacity exists, but circuit choice/use still
  allows late selected-circuit DATA."
- `tools/run_browser_compare.py` now accepts runner-only
  `--extra-arti-exit-select-prefer-cold-same-isolation-other-isolation-pressure TARGET:MIN`.
  It creates a same-window profile that combines load-aware, health-aware,
  avoid-bad-health, prefer-cold same-isolation selection, same-isolation target,
  and the other-isolation pressure trigger. Proof
  `results/browser-compare-20260609T200842/browser-compare.json` failed overall
  quality, but the new guarded prefer-cold sameiso2/otheriso3 profile completed
  all `6` page runs and still lost to local C Tor on boot and median loads.
  Treat it as a diagnostic hook, not a source-promotion path.
- `upstream/arti/crates/tor-proto/src/stream/raw.rs` logs
  `torfast stream receiver no-end close` when a stream receiver ends without an
  END cell. `tools/analyze_browser_compare.py` parses that trace and shows
  `no-END closes` in selected-circuit and terminal-stream tables. Proof
  `results/browser-compare-20260609T205638/browser-compare.json` failed
  quality, but it tied the worst failed onion stream (`Circ 2.8`, stream
  `10599`) to partial DATA, long idle, and one no-END close. Keep the trace for
  the next source pass; it is proof, not a speed change.
- `upstream/arti/crates/tor-proto/src/circuit/circhop.rs` logs
  `delivery="close_decision"` when the stream map terminates a stream. The
  analyzer joins `close_reason`, `should_send_end`, and `close_behavior` to
  terminal stream rows and selected-circuit evidence. Proof
  `results/browser-compare-20260609T211227/browser-compare.json` passed quality
  and showed no-END rows can be local `StreamTargetClosed` closes with
  `should_send_end=Send`; use that trace before treating no-END as
  network-side failure proof.
- `upstream/arti/crates/arti/src/proxy/socks.rs` now raises
  `torfast socks timing stream linked` to `INFO` when
  `TORFAST_SOCKS_RELAY_BYTE_TIMING=1`. This keeps fast SOCKS stream-to-circuit
  join rows visible in low-log byte-timing proofs. `tools/run_browser_compare.py`
  also keeps terminal receiver rows in signal context and retains matching
  stream-link rows by `(circ_id, stream_id)` when bounded logs would otherwise
  drop them. Fresh proof
  `results/browser-compare-20260610T001352/browser-compare.json` confirms `30`
  retained stream-link rows after rebuilding release Arti. This is proof-only;
  it does not change stream, circuit, relay, or browser behavior.
- `tools/analyze_browser_compare.py` now prints
  `Resource Queue Lifecycle Evidence`. It joins late queued browser resources to
  high-confidence SOCKS timing ids, then to stream lifecycle rows, so the report
  shows BEGIN/CONNECTED/DATA lifecycle counts, queue-full rows, circuit sender
  queue depth, terminal idle, and terminal pending bytes for the exact streams
  blocking browser slots. Replay of
  `results/browser-compare-20260610T002123/browser-compare.json` shows the slow
  queue rows had DATA delivered with `0` queue-full rows, `0` max circuit sender
  queue, and `0` terminal pending bytes. This is analyzer-only proof; it does
  not change Tor behavior.
- `tools/analyze_browser_compare.py` now also prints
  `Browser Resource Queue Choice Class Summary`. It groups slow browser queue
  rows into better-health alternative, lower-assignment alternative,
  multi-candidate no-better-alt, only-selected-open, or missing-context classes.
  Replay of `results/browser-compare-20260610T002123/browser-compare.json`
  shows `19` only-selected-open rows, `5` lower-assignment-alternative rows, and
  `0` better-health-alternative rows. This is analyzer-only proof; it does not
  change Tor behavior.
- `tools/analyze_browser_compare.py` now also prints
  `Arti Profile Same-Isolation Top-Up Nonuse Detail`. It explains built/seen
  same-isolation top-ups that were not used by later streams, including whether
  they never appeared as later open candidates or lost to another selected
  circuit with better logged health. This is analyzer-only proof; it does not
  change Tor behavior.
- `upstream/arti/crates/tor-circmgr/src/mgr.rs` now passes
  `select_prefer_cold_same_isolation` into
  `OpenEntry::find_best_index_before_active_cap`. Before this source fix, the
  flag was computed and logged but the selector call used `false`, so the
  default-off guarded prefer-cold same-isolation lab profile did not actually
  test the intended cold-assignment rule on normal open-circuit selection.
  `tools/check_arti_quality_config.py` has a static check for this wiring.
- Rerun `results/browser-compare-20260610T011528/browser-compare.json` used the
  rebuilt Arti after the selector wiring fix. The guarded prefer-cold sameiso2
  prewarm profile still failed quality on download. After analyzer cleanup, its
  `3` built/seen top-ups had no later circuit-selection event after proof, and
  the streams linked after proof had already started before proof. This points
  the next source inspection at earlier same-isolation prewarm or useful later
  selection after build, plus separate no-Tor-byte stream waits, not at the
  prefer-cold flag wiring.
- `upstream/arti/crates/tor-circmgr/src/mgr.rs` now adds default-off
  same-isolation pending wait with
  `TORFAST_EXIT_SAME_ISOLATION_PENDING_WAIT_MS`, bounded to `50..=2000ms`. The
  new `OpenAfterSameIsolationPendingWait` action waits briefly for already
  building same-isolation capacity, then falls back to the chosen open circuit.
  `tools/run_browser_compare.py` exposes this with
  `--arti-exit-same-isolation-pending-wait-ms`, and
  `tools/check_arti_quality_config.py` checks the knob, bounds, action, and log
  lines. Proof `results/browser-compare-20260610T014101/browser-compare.json`
  passed quality and beat baseline Arti A/B on both tested targets, but it is
  still lab-only because it did not fully beat C Tor and boot directory failures
  got worse.
- `upstream/arti/crates/tor-circmgr/src/mgr.rs` now widens that same lab-only
  pending wait to reuse pressure: when the selected same-isolation circuit is
  already assigned and matching capacity is pending, the wait can fire even when
  `open_candidates == target`. `tools/analyze_browser_compare.py` now parses
  same-isolation pending-wait open, win, and timer rows and counts them in
  `pending waits`. Proof
  `results/browser-compare-20260610T015105/browser-compare.json` passed quality,
  showed `9` pending waits and one wait win, and beat baseline Arti A/B on both
  tested targets. It remains lab-only because download page-load still lost to
  local C Tor.
- `upstream/arti/crates/arti/src/proxy/socks.rs` now promotes fast SOCKS
  `stream ready`, `socks reply sent`, and byte-timing relay summary rows to
  INFO only when `TORFAST_SOCKS_RELAY_BYTE_TIMING=1` is set. This keeps normal
  logging unchanged but makes lab byte-timing proof parseable for fast streams.
- `tools/run_browser_compare.py` now keeps all SOCKS timing rows for timing ids
  linked to terminal tail streams, instead of keeping only the matching
  `stream linked` line. `tests/test_browser_quality.py` covers this retention
  path.
- Proof `results/browser-compare-20260610T021009/browser-compare.json` confirms
  the fast connect/reply rows are now present in analysis. It also rejects the
  patched sameiso pending-wait/prefer-cold profile for promotion because the
  download page hit `61687.470ms` load, with several selected circuits showing
  `4079..4801ms` DATA gaps and very low receive rates.
- `tools/analyze_browser_compare.py` now parses the 11-field
  `candidate_health_summary` format with `active_stream_age_ms`, prints max
  candidate active age in circuit-selection tables, and prints selected/first
  active age in `Torfast Load-Aware Selection Health Outcome`. Proof
  `results/browser-compare-20260610T022130/browser-compare.json` passed quality
  and rejected the active-no-data `5000ms` profile because it was slower than
  baseline Arti and still selected `5` low-rate circuits.
- Repeat proof `results/browser-compare-20260610T023311/browser-compare.json`
  rejects simply lowering `TORFAST_EXIT_SELECT_HEALTH_MIN_MOVE_SCORE_BPS` to
  `16000`: quality passed and low-rate circuit counts improved, but page-load
  lost `0/3` paired runs against baseline Arti and had worse resource queues.
  Treat the threshold as lab-only; future source work should address queue/tail
  behavior after selection rather than only moving to a scored circuit.
- `tools/run_browser_compare.py` now adds a clean lab-only combined profile for
  health-aware min-score plus same-isolation pending wait:
  `--extra-arti-exit-select-health-min-move-score-same-isolation-pending-wait`.
  This avoids using global same-isolation flags that would pollute baseline
  Arti in A/B runs. Diagnostic proof
  `results/browser-compare-20260610T024537/browser-compare.json` passed quality.
  The combined `16000bps_sameiso2_wait800ms` profile beat baseline Arti in its
  one paired run by `963.870ms`, but still lost page-load to local C Tor by
  `1298.588ms` and had slower boot. Keep it lab-only; next proof needs a
  multi-run repeat and boot-directory cleanup before any promotion claim.
- Repeat proof `results/browser-compare-20260610T025054/browser-compare.json`
  rejects that combined same-isolation pending-wait profile. Quality passed, but
  the profile had median load `20387.059ms`, only `1/3` paired wins against
  baseline Arti, and max queue `22750.455ms`. Treat the runner flag as
  diagnostic only; future work should target guarded assignment and late
  resource queues after circuit selection.
- Assigned-cap proof `results/browser-compare-20260610T031147/browser-compare.json`
  rejects `arti_release_browser_healthaware_min16000bps_assignedcap4`. Quality
  failed because run 3 timed out at `121615.880ms` with no screenshot. The two
  successful cap runs lowered queue tails, but summary median load still lost
  to baseline Arti (`4674.788ms` vs `3580.733ms`), so cap 4 stays diagnostic
  only.
- `crates/arti-client/src/client.rs` now keeps slow successful CONNECT phase
  rows visible in low-log byte-timing proofs. Normal exit CONNECT rows already
  split tunnel acquisition from BEGIN completion; they now use `INFO` for slow
  successful rows. Onion-service CONNECT rows now do the same with
  `torfast hs client timing tunnel ready` and
  `torfast hs client timing begin stream finished`, including
  `tunnel_elapsed_ms` and `begin_phase_ms`. `tools/analyze_browser_compare.py`
  prints HS client median and max begin phase. Proof
  `results/browser-compare-20260612T205904/browser-compare.json` reproduced
  slow onion CONNECTs and showed they were mostly HS tunnel acquisition
  (`2495..4780ms`) with smaller BEGIN phases (`393..622ms`).
- HS tunnel acquisition proof is now retained more directly. `crates/arti-client/src/client.rs`
  emits `torfast hs state timing client wrapper start/finished` around
  `get_or_launch_tunnel`; `crates/tor-hsclient/src/state.rs` emits cache,
  task-spawn, wait, task-finished, and returned rows; and
  `crates/tor-hsclient/src/connect.rs` raises the existing HS protocol proof rows
  to `INFO` and now also emits descriptor-ready/refetch-ready timing rows.
  `crates/tor-hsclient/src/state.rs` also shows that Arti already shares one
  `Working` HS connect task for matching service/secret/isolation records:
  later callers log `wait existing task` and get the stored result. This sharing
  is still isolation-scoped through `crates/tor-hsclient/src/isol_map.rs`, so
  different Tor Browser isolation buckets can still create separate HS state
  tasks. After the failed `20260613T121334` byte-tap diagnostic, the next source
  check should explain which isolation/task failed with `descNotFound` before
  changing descriptor retry or tunnel behavior. The state rows now carry a
  local `state_id` field so the next browser proof can separate same-task waits
  from separate isolation-scoped tasks without logging onion names or relay
  identities. `tools/analyze_browser_compare.py` prints this in
  `Torfast HS State Per-Run`.
  Proof `results/browser-compare-20260613T123334/browser-compare.json` passed
  quality and showed port `80` and port `443` using separate HS state records
  on every Arti run. This makes the next source target descriptor-only sharing
  or single-flight across separate HS state records, if it can be done without
  sharing streams, rendezvous circuits, intro history, stream isolation, path
  choice, relay choice, or browser behavior.
  `tools/run_browser_compare.py` gives HS proof rows retention priority under
  the `1000` line cap, and `tools/analyze_browser_compare.py` prints
  `Torfast HS State Timings` plus descriptor counts and median descriptor time
  in `Torfast HS Timings`. Proof
  `results/browser-compare-20260613T090904/browser-compare.json` passed quality
  and tied the slow onion CONNECT to tunnel acquisition: `2784ms` connect,
  `2243ms` HS tunnel/wrapper, and `540ms` BEGIN phase.
  Direct-onion proof `results/browser-compare-20260613T091712/browser-compare.json`
  also passed quality and kept the descriptor split live: descriptor rows `2`,
  median descriptor `1462ms`, median HS tunnel `4662ms`, median BEGIN phase
  `382ms`. It rejected speed promotion because Arti loaded in `9038.328ms`
  versus local C Tor `5662.739ms`.
  `crates/tor-hsclient/src/connect.rs` now also emits descriptor fetch subphase
  rows for HSDir circuit ready, BEGINDIR stream ready, descriptor response
  ready, and descriptor parsed. `tools/analyze_browser_compare.py` prints
  `Torfast HS Descriptor Fetch Timings`. Proof
  `results/browser-compare-20260613T092626/browser-compare.json` passed quality
  and showed descriptor fetch was not parse-bound: median HSDir circuit
  `341ms`, BEGINDIR stream `342ms`, response `771.5ms`, parse `773.5ms`, while
  median HS tunnel remained `4981.5ms`. That one run is not promotion proof
  because local C Tor had a large load outlier.
  `crates/tor-hsclient/src/connect.rs` now adds a per-attempt
  `hs_connect_id` plus shared `connect_elapsed_ms` to HS connect proof rows, and
  `tools/analyze_browser_compare.py` prints `Torfast HS Attempt Timings`.
  Proof `results/browser-compare-20260613T094026/browser-compare.json` passed
  quality but rejected promotion: Arti loaded in `9008.722ms` versus local C Tor
  `6542.820ms`. The grouped attempts showed post-descriptor HS setup of
  `2014ms` and `1217ms`, while BEGIN phase was only `383..540ms`, so the next
  source target is hidden-service tunnel acquisition after descriptor fetch.
  `upstream/arti/crates/tor-circmgr/src/hspool.rs` now has a default-off
  on-demand grace lab knob,
  `TORFAST_HSPOOL_ON_DEMAND_POOL_GRACE_MS`. Same-window proof
  `results/browser-compare-20260613T095400/browser-compare.json` and repeat
  proof `results/browser-compare-20260613T095613/browser-compare.json` both
  passed quality but rejected promotion: the serial wait either did not use the
  grace path or made the page much slower. Next source target is a no-delay
  background-pool/on-demand race or better preemptive HS pool readiness. The
  follow-up race knob, `TORFAST_HSPOOL_ON_DEMAND_POOL_RACE_MS`, starts
  on-demand immediately and races a ready pool stem without adding serial delay.
  Proofs `results/browser-compare-20260613T101211/browser-compare.json` and
  `results/browser-compare-20260613T101413/browser-compare.json` passed quality
  but rejected speed promotion, so it stays lab-only. The browser runner also
  exposed the existing `TORFAST_HSPOOL_BACKGROUND_START_DELAY_MS` startup-delay
  env. Proofs `results/browser-compare-20260613T102523/browser-compare.json`
  and `results/browser-compare-20260613T102711/browser-compare.json` passed
  quality but rejected speed promotion for immediate HS-pool startup.
  `crates/tor-hsclient/src/connect.rs` now has the default-off
  `TORFAST_HS_REND_PREBUILD_BEFORE_DESC` lab knob to start normal rendezvous
  setup while descriptor fetch is in flight, with normal fallback if the early
  rendezvous fails. Proof
  `results/browser-compare-20260613T104210/browser-compare.json` passed quality
  and improved summary median load plus HS tunnel median, but direct paired A/B
  against base Arti was mixed. Larger proof
  `results/browser-compare-20260613T105207/browser-compare.json` passed quality
  and rejected promotion, so this stays lab-only.
- `crates/tor-proto/src/client/stream/data.rs` now has default-off, bounded
  stream-ready DATA coalescing through
  `TORFAST_STREAM_READY_DATA_COALESCE_BYTES` (`498..65536`). It acts below the
  SOCKS proxy: after one DATA cell is read, it drains only already queued DATA
  cells into `pending` up to the bound. `crates/tor-proto/src/stream/raw.rs`
  adds `next_queued_msg_is_data()` so the drain does not cross visible
  non-DATA/control cells. `tools/run_browser_compare.py` exposes same-window
  A/B profiles with `--extra-arti-stream-ready-data-coalesce-bytes`, records
  `arti_stream_ready_data_coalesce_bytes`, and names the first profile
  `arti_release_browser_streamreadycoalesceN`. Static guard:
  `tools/check_arti_quality_config.py` checks the env, bounds, drain loop, and
  DATA-only peek path.
- Proof `results/browser-compare-20260613T083550/browser-compare.json` with
  `streamreadycoalesce4096` passed quality but rejects promotion. Default Arti
  loaded `https://www.torproject.org/download/` in `5306.571ms`; the coalesce
  profile loaded in `5398.779ms`; local C Tor loaded in `7366.845ms`. The
  candidate lost paired load `0/1` and was `+92.208ms` slower than default
  Arti. It also worsened the queue/tail proof: max tagged connection queue rose
  from `1733.368ms` to `3283.399ms`, queued rows at least `1000ms` rose from
  `17` to `20`, total tagged queue rose from `27550.551ms` to `42850.857ms`,
  and neutral byte-tap median max data gap rose from `300.266ms` to
  `434.642ms`. Keep this as lab-only negative proof; ready DATA coalescing
  alone is not the response-tail fix.
