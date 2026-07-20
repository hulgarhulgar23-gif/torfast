# Quality Bar

This is the hard line. A faster build is not accepted if it breaks these rules.

## Network rules

- Normal web browsing keeps Tor-style 3-hop circuits.
- The first hop must be a guard.
- Non-test circuits only use relays with the Fast flag.
- A circuit must not use the same relay twice.
- A circuit must not use two relays from the same relay family.
- A circuit must not use relays from the same network range.
- Exit choice must still obey exit policy.
- DNS must go through the Tor circuit, not local DNS.
- Circuit choice must stay diverse. We cannot always pick the fastest relays.
- C Tor circuit checks must pass `tools/check_c_tor_circuits.py` before we use
  a C Tor speed run as quality evidence.
- Conflux must be live at runtime, not just requested in the torrc:
  `tools/check_c_tor_circuits.py` gates on `ConfluxEnabled` resolving to
  `auto`/`1` on the control port and on at least `2` BUILT `CONFLUX_LINKED`
  circuits (one full linked set), and the linked legs must pass the same
  3-hop/guard/family/subnet path rules as GENERAL circuits. `ConfluxEnabled
  auto` defers to the network consensus, so a consensus flip or an
  unsupporting binary would silently drop the proven `~2-3x` bulk-throughput
  win without this gate. Lab A/B comparisons may bypass it with
  `--no-require-conflux`, but such runs are not promotion evidence.
- Arti source/config checks must pass `tools/check_arti_quality_config.py` for
  the current shipped-quality subset. The same report may also list advisory
  non-shipped-path or observability checks that do not block equal-quality
  proof until that behavior becomes part of the shipped path. This is still
  static proof only:
  Arti still needs runtime path proof before we call an Arti speed run
  equal quality.
- Arti RPC path checks with `tools/check_arti_rpc_path.py` must pass before an
  Arti speed run counts as equal-quality evidence. A full pass uses
  `arti:describe_path` plus C Tor directory data to check 3 hops, guard first
  hop, relay flags, exit flag, relay ID reuse, relay family, same IPv4 `/16`,
  and a successful target connection.

## Browser rules

- Use Tor Browser rules as the default quality target.
- Do not add a setting that makes one user look different from the crowd.
- Keep first-party isolation.
- Keep letterboxing behavior.
- Keep canvas, script, and fingerprint protections.
- Do not add background prefetch that can reveal interests or timing.
- Do not cache in a way that changes cross-site identity.
- Browser-speed tests must save proxy prefs and page screenshots, so we can
  prove the browser used Tor Browser rules and the expected SOCKS port.
- Browser-speed results must pass `tools/analyze_browser_compare.py` before we
  use them as evidence.
- Runtime fingerprint proof must be captured on the requested target page
  (`pageUrl` must match the requested URL), not on a privileged `about:` page.
  Privileged pages skip content protections, so a snapshot taken there proves
  nothing about what websites can see.
- Canvas extraction must be blocked on the target page: a probe that draws a
  known color and reads it back through `getImageData` must not get the drawn
  pixels back.
- The `resistFingerprinting` timezone spoof must be live on the target page:
  content must see exactly `UTC`. A zero-offset zone name like
  `Atlantic/Reykjavik` only proves the process env, not the spoof.
- The fast-lane browser must present the same stable fingerprint surface as a
  stock-launched instance of the same build
  (`STABLE_FINGERPRINT_REFERENCE_KEYS` in `tools/run_browser_compare.py`).
  Window-environment values (geometry, `devicePixelRatio`, `cookieEnabled`)
  are excluded because they track the display environment, not the browser
  configuration.
- A launched open must end with the requested page in the tab. Stream-level
  fetch proof alone is not enough: Tor Browser first-run can load `about:tor`
  over the already-committed target navigation, so the launcher keeps a
  target-navigation keeper and the verifier gates on the final page URL.

## Speed rules

- Every speed claim needs a benchmark.
- Compare against the same network, same time window, and same target type.
- Track connect time, first byte time, total time, and bytes.
- For the promoted-profile verifier, the speed gate is two-part: the
  candidate must beat baseline on median open-browser elapsed (the
  launch-controlled metric) on every target, and must not regress median
  combined wall on any target beyond a noise-scaled guard of
  `max(1.0s, 0.75 x baseline same-config stdev)`. Combined wall includes
  delivering the requested page over a random Tor circuit with measured
  same-config per-run spread of several seconds, so a fixed sub-noise
  threshold would gate on network noise the profile cannot influence.
- Browser tests also track bootstrap time, page-load time, screenshot time, and
  screenshot size.
- A speed change must list the privacy risk it might add.
- If we cannot prove the risk is unchanged, the change stays lab-only.

## Safe speed lanes

- Faster startup and bootstrap.
- Better local scheduling of already-safe circuits.
- Smarter prebuilt circuits, without target-specific leaks.
- Congestion-aware use of circuits.
- Conflux-style split traffic where the Tor protocol supports it.
- Browser CPU and disk work that does not change fingerprint behavior.
