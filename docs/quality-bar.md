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
- Arti source/config checks must pass `tools/check_arti_quality_config.py`, but
  that is static proof only. Arti still needs runtime path proof before we call
  an Arti speed run equal quality.
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

## Speed rules

- Every speed claim needs a benchmark.
- Compare against the same network, same time window, and same target type.
- Track connect time, first byte time, total time, and bytes.
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
