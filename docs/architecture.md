# Architecture

We should build this in layers. Each layer can be tested alone.

## Layer 1: measure

Use `tools/bench_http.py` to measure:

- direct network baseline
- Tor SOCKS baseline
- Arti SOCKS baseline, when available
- Tor Browser page-load baseline, later

The first target is not "fast". The first target is repeatable numbers.

## Layer 2: quality gates

Use code checks for path rules before testing any path or circuit idea.

The current checker covers:

- 3 hops
- first hop is a guard
- all relays have Fast
- no duplicate relay
- no family overlap
- no same subnet
- exit supports the target port

Later gates should add:

- guard lifetime and guard rotation rules
- consensus weight checks
- onion service path rules
- browser fingerprint checks

## Layer 3: compatible fast client

Best first base:

- C Tor for exact current behavior and wide support
- Arti for Rust experiments and cleaner client-side code

Do not fork protocol behavior first. Start with local client behavior:

- circuit warmup policy
- stream-to-circuit assignment
- timeout handling
- measuring congestion signals
- avoiding slow dead circuits earlier

These can improve user speed without changing the public browser fingerprint.

## Layer 4: browser shell

For exact quality, the browser should stay close to Tor Browser.

Possible safe work:

- profile startup speed
- disk I/O trim
- extension load timing
- UI startup path
- page-load CPU hot spots

Risky work:

- new browser features
- custom user agent
- changed screen/window behavior
- changed storage rules
- target-based prefetch

Risky work needs proof before it leaves lab mode.

## Layer 5: protocol work

Protocol speed work belongs upstream or must be compatible with upstream Tor.

Good areas:

- congestion control tuning
- Conflux traffic splitting
- better circuit scheduling
- relay queue behavior

Bad areas:

- shorter normal circuits
- fixed "fast relay" lists
- hidden custom relay preference
- weaker path constraints
