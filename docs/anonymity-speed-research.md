# Research Note: Can We Have Exact Tor Anonymity at Clearnet Speed?

Written 2026-07-06. This note maps the design space for the question that
drives this repo: is Tor's slowness an engineering accident we can out-build,
or a structural cost of the anonymity itself? Short answer: the cost is
structural, the structure has one soft spot, and everything else is
engineering headroom that this repo is already harvesting.

## 1. The floor: why hiding costs time or bandwidth

Two facts create the floor. The first is literal physics: routing through
relays adds speed-of-light distance, so a 3-hop path across continents has a
round-trip time of hundreds of milliseconds before any queueing.

The second is information-theoretic. An observer who watches traffic enter
and leave a network links sender to receiver by **timing**. To break that
statistical link, a message must either wait among other messages
(**latency**) or hide among fake messages (**cover-traffic bandwidth**). A
system that pays neither leaves the correlation intact. This is not a designer
failing; it is an accounting identity about distinguishability.

## 2. The trilemma theorem

Das, Meiser, Mohammadi, and Kate formalized this in the
[Anonymity Trilemma (IEEE S&P 2018)](https://ieeexplore.ieee.org/abstract/document/8418599)
([eprint 2017/954](https://eprint.iacr.org/2017/954)): against a global
passive adversary, an anonymous communication protocol can achieve at most two
of strong anonymity, low bandwidth overhead, and low latency overhead.
[Follow-up work by the same group](https://freedom.cs.purdue.edu/assets/beyond-mix-nets.pdf)
extended the impossibility beyond mix-nets to broader protocol classes. The
result is a theorem inside a formal model, not a law of nature — which matters
in section 5.

Tor's own position in the triangle: low latency and low bandwidth overhead,
paid for by giving up strong anonymity against a *global* observer. Tor's
threat model assumes the adversary sees only part of the network. Any project
that claims "Tor anonymity but faster" must say which corner it is giving up —
usually it quietly gives up the anonymity one.

## 3. Survey of the design space

- **Fewer hops (VPN-style, 1-2 hop).** Fast, but a single operator (or a
  2-relay collusion) sees who talks to whom. Weaker threat model than Tor,
  not equal anonymity.
- **Mix networks (Nym, Loopix family).** Stronger anonymity than Tor against
  global observers, paid with deliberate per-hop delays and cover traffic.
  Recent latency-aware routing work —
  [LARMix (NDSS 2024)](https://www.ndss-symposium.org/wp-content/uploads/2024-221-paper.pdf),
  [LARMix++ (2024)](https://eprint.iacr.org/2024/1485),
  [CLAM (2024)](https://dl.acm.org/doi/10.1145/3658664.3659631) — cuts
  propagation latency substantially, and
  [usability studies](https://arxiv.org/pdf/2601.17845) find Nym's delay
  parameters "low enough to rival the performance of Tor," but the same
  studies note those low delays likely do not deliver the strong-adversary
  anonymity that justifies a mixnet in the first place. The trilemma, observed
  in the wild.
- **DC-nets and PIR-based messaging (Vuvuzela, Pung, Groove class).**
  Near-information-theoretic anonymity, but latency in seconds-to-minutes and
  tiny message sizes. Unusable for interactive browsing.
- **Network-layer onion routing (HORNET, LAP).** Line-rate speed, but weaker
  per-flow unlinkability and requires deployment inside ISPs and routers —
  not shippable by an application project.
- **I2P.** Similar onion structure, no speed advantage for exit browsing, and
  a much smaller crowd (see section 6).
- **Tor-over-QUIC / UDP transports.** A genuine engineering frontier
  ([tor-dev case for Tor-over-QUIC](https://lists.torproject.org/mailman3/hyperkitty/list/tor-dev@lists.torproject.org/thread/7KDMJMOUH34AAKYYUVBVBV2Z7YNMUAKI/),
  a [Rust QUIC pluggable-transport proposal, January 2026](https://forum.torproject.org/t/proposal-rust-based-quic-pluggable-transport-uat/21124),
  academic results like QuicTor showing head-of-line-blocking wins). This
  stays inside Tor's anonymity model, but requires relay-side support across
  the network, so it is the Tor Project's roadmap, not a client feature.
- **Conflux traffic splitting
  ([proposal 329](https://spec.torproject.org/proposals/329-traffic-splitting.html)).**
  Two full 3-hop circuits used in parallel, protocol-sanctioned, anonymity
  model intact. This repo's own benchmarks measured `~2-3x` bulk-download
  throughput (see `docs/latest-results.md`). Deployed reality, not research.

## 4. What "proving the trilemma wrong" would require

Three doors, in decreasing order of difficulty:

1. **Find an error in the proof.** Peer-reviewed since 2018 with follow-ups;
   vanishingly unlikely, and the timing-correlation engine of the proof is
   close to an information-theoretic identity.
2. **Escape the model's assumptions.** The theorem models a message-passing
   relay network against a global passive adversary. Legitimate escapes:
   assume a weaker adversary (Tor already plays this card — the escape is
   priced in), or change the primitive so there is no relayed message to
   correlate (section 5).
3. **Engineer to the boundary.** Accept the triangle and remove every cost
   the theorem does not force: startup, cold circuits, congestion, stalls,
   single-circuit throughput. This is this repo's lane.

A serious attempt at door 2 needs: a precise new adversary model, a protocol
with a formal anonymity proof in that model, survival of peer review at a top
venue, an implementation, and a user crowd (section 6). That is a multi-year
research program, not a browser feature.

## 5. The one live frontier: doubly-efficient PIR

Private information retrieval lets a client fetch a record from a server
without the server learning which record. For *static content*, a PIR-served
web would need **zero relay hops**: nothing to timing-correlate, because the
privacy comes from cryptography on the server side rather than from routing.
This attacks the trilemma's model rather than its math.

The economics used to be absurd (server work linear in the database per
query). That is changing fast:

- [Lin, Mook, Wichs (STOC 2023)](https://dl.acm.org/doi/10.1145/3564246.3585175):
  first doubly-efficient PIR with polylogarithmic online server work from
  Ring-LWE — purely theoretical at the time.
- [Towards Practical Doubly-Efficient PIR (FC 2024)](https://fc24.ifca.ai/preproceedings/148.pdf):
  orders-of-magnitude concrete improvements, first implementation.
- [Towards Making Doubly-Efficient PIR Practical (eprint 2026/243)](https://eprint.iacr.org/2026/243):
  reports roughly four orders of magnitude less server state and six orders
  of magnitude faster queries than prior work — `171GB` server state and
  `21ms` amortized query time on a `2^23`-record database.

`21ms` per query is clearnet speed. The honest caveats: it covers static
reads only (no interactivity, no writes, no logins), server state is still
huge per database, every content provider would have to run PIR servers, and
the anonymity story changes shape (the server learns *that* you queried, just
not *what*). This is the direction to watch — a plausible 5-10 year future is
a hybrid where static public content rides PIR-style delivery at clearnet
speed while interactive traffic still needs Tor-style routing.

## 6. Anonymity loves company

Independent of protocol design: anonymity is hiding in a crowd. Tor has
millions of daily users across thousands of relays; membership in that crowd
is most of the anonymity. A new network with a brilliant design and fifty
users identifies its users by membership alone. Consequence for this repo:
**ride Tor's network and crowd; never fork the anonymity set.** Any speed
work that requires "our own network" loses before it starts.

## 7. Implications for torfast

The layered plan, all inside `docs/quality-bar.md`:

1. **Launch and delivery** — done and proven (see
   `docs/latest-results.md`, 2026-07-06 entries): instant open, warm
   circuits, guaranteed target-page delivery, exact-quality gates.
2. **Conflux by default** — the proven `~2-3x` throughput win, to be pushed
   through the same promote-and-prove pipeline.
3. **Circuit pool and hedged builds** — never make a click wait for circuit
   construction; kill the multi-second tail.
4. **Congestion-aware stream migration** — move new streams off stalling
   circuits; turn rare 30s disasters into ordinary pages.
5. **Watch, don't build:** Tor-over-QUIC (needs relay support) and
   doubly-efficient PIR (needs a research-grade bet). Re-evaluate yearly.

What we will not do, ever, because it trades the anonymity we promised:
fewer hops, fastest-relay cherry-picking, cross-site caching, prefetching,
or a private relay network.

## References

- Anonymity Trilemma — [IEEE S&P 2018](https://ieeexplore.ieee.org/abstract/document/8418599), [eprint 2017/954](https://eprint.iacr.org/2017/954), [beyond mix-nets follow-up](https://freedom.cs.purdue.edu/assets/beyond-mix-nets.pdf), [project page](https://freedom.cs.purdue.edu/projects/trilemma.html)
- LARMix — [NDSS 2024 paper](https://www.ndss-symposium.org/wp-content/uploads/2024-221-paper.pdf), [LARMix++ eprint 2024/1485](https://eprint.iacr.org/2024/1485)
- CLAM — [IH&MMSec 2024](https://dl.acm.org/doi/10.1145/3658664.3659631)
- Mixnet latency usability study — [arXiv 2601.17845](https://arxiv.org/pdf/2601.17845)
- Doubly-efficient PIR — [STOC 2023](https://dl.acm.org/doi/10.1145/3564246.3585175), [FC 2024](https://fc24.ifca.ai/preproceedings/148.pdf), [eprint 2026/243](https://eprint.iacr.org/2026/243)
- Tor transport evolution — [Conflux proposal 329](https://spec.torproject.org/proposals/329-traffic-splitting.html), [Tor-over-QUIC discussion](https://lists.torproject.org/mailman3/hyperkitty/list/tor-dev@lists.torproject.org/thread/7KDMJMOUH34AAKYYUVBVBV2Z7YNMUAKI/), [QUIC pluggable transport proposal (2026)](https://forum.torproject.org/t/proposal-rust-based-quic-pluggable-transport-uat/21124)
