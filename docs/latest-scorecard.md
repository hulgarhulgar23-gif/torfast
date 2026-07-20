# torfast verifier scorecard — `torfast-promoted-quality-check-20260707T002336`

**Verdict: PASS** ✅ (5 cycles)

| gate | result |
|---|---|
| runtime quality runs | ✅ 30/30 |
| pairwise fingerprint consistency | ✅ 15/15 |
| circuit rules — check.torproject.org | ✅ 3-hop/guard/family/subnet, conflux live (6 linked legs) |
| circuit rules — www.torproject.org | ✅ 3-hop/guard/family/subnet, conflux live (6 linked legs) |
| circuit rules — www.torproject.org/download | ✅ 3-hop/guard/family/subnet, conflux live (4 linked legs) |

## Speed vs baseline (medians)

| target | open-browser elapsed Δ | combined wall Δ | guard |
|---|---:|---:|---:|
| check.torproject.org | ✅ -6.840s | ✅ -1.834s | 1.613s |
| www.torproject.org | ✅ -7.914s | ✅ +0.000s | 1.157s |
| www.torproject.org/download | ✅ -7.611s | ✅ -0.433s | 1.811s |

Negative deltas are faster than baseline. The combined-wall guard is `max(1.0s, 0.75 x baseline same-config stdev)` because page delivery rides a random Tor circuit (see `docs/quality-bar.md`).
