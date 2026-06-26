import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from bench_http import FetchResult
from run_conflux_compare import (
    PROFILES,
    TorInstance,
    find_tor,
    stat_block,
)


def _result(total_ms: float, *, ok: bool = True, first_byte_ms: float | None = None) -> FetchResult:
    return FetchResult(
        mode="socks",
        url="https://example.invalid/",
        ok=ok,
        status_line="HTTP/1.1 200 OK" if ok else "",
        connect_ms=10.0,
        tls_ms=5.0,
        first_byte_ms=first_byte_ms if first_byte_ms is not None else total_ms - 50.0,
        total_ms=total_ms,
        bytes_read=1000,
        error=None if ok else "boom",
    )


# Lines that may legitimately appear in a profile torrc. Anything outside this
# set could change Tor's privacy behavior and must fail the test.
ALLOWED_TORRC_PREFIXES = (
    "SocksPort ",
    "DataDirectory ",
    "ClientOnly 1",
    "AvoidDiskWrites 1",
    "SafeLogging 1",
    "Log notice stdout",
    "ConfluxEnabled ",
    "ConfluxClientUX ",
)


class StatBlockTests(unittest.TestCase):
    def test_empty_runs_marked_not_ok(self) -> None:
        block = stat_block([])
        self.assertFalse(block["ok"])
        self.assertEqual(block["successes"], 0)

    def test_all_failures_marked_not_ok(self) -> None:
        block = stat_block([_result(100.0, ok=False), _result(120.0, ok=False)])
        self.assertFalse(block["ok"])
        self.assertEqual(block["successes"], 0)
        self.assertEqual(block["failures"], 2)

    def test_medians_and_percentiles(self) -> None:
        runs = [_result(v) for v in (100.0, 200.0, 300.0, 400.0, 500.0)]
        block = stat_block(runs)
        self.assertTrue(block["ok"])
        self.assertEqual(block["successes"], 5)
        self.assertEqual(block["failures"], 0)
        self.assertEqual(block["median_total_ms"], 300.0)
        self.assertEqual(block["min_total_ms"], 100.0)
        self.assertEqual(block["max_total_ms"], 500.0)
        # p90 of 5 sorted values lands on the last element.
        self.assertEqual(block["p90_total_ms"], 500.0)

    def test_partial_failures_flag_not_fully_ok(self) -> None:
        runs = [_result(100.0), _result(200.0, ok=False), _result(300.0)]
        block = stat_block(runs)
        self.assertFalse(block["ok"])  # not every run succeeded
        self.assertEqual(block["successes"], 2)
        self.assertEqual(block["failures"], 1)
        # Medians use only the successful runs.
        self.assertEqual(block["median_total_ms"], 200.0)

    def test_transfer_throughput_computed_from_body_phase(self) -> None:
        # Each _result reads 1000 bytes with a 50 ms body phase
        # (first_byte = total - 50). mbps = bytes*8/1000/transfer_ms.
        runs = [_result(v) for v in (100.0, 200.0, 300.0)]
        block = stat_block(runs)
        expected = round((1000 * 8.0) / 1000.0 / 50.0, 3)  # 0.16 Mbps
        self.assertEqual(block["median_transfer_mbps"], expected)
        self.assertEqual(block["max_transfer_mbps"], expected)

    def test_transfer_throughput_none_when_body_phase_too_short(self) -> None:
        # first_byte == total -> transfer phase ~0, no throughput signal.
        runs = [_result(100.0, first_byte_ms=100.0)]
        block = stat_block(runs)
        self.assertIsNone(block["median_transfer_mbps"])
        self.assertIsNone(block["max_transfer_mbps"])


class TorrcSafetyTests(unittest.TestCase):
    """The conflux harness must only change Conflux options, never path rules."""

    def test_every_profile_torrc_only_touches_conflux(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            for profile in PROFILES:
                inst = TorInstance("/bin/true", profile, out)
                torrc = inst.render_torrc()
                lines = [ln for ln in torrc.splitlines() if ln.strip()]
                for line in lines:
                    self.assertTrue(
                        line.startswith(ALLOWED_TORRC_PREFIXES),
                        msg=f"profile {profile['name']} has unexpected torrc line: {line!r}",
                    )
                # Must keep client-only and a single 3-hop default (no override
                # of hop count, guards, exit nodes, or DNS).
                self.assertIn("ClientOnly 1", lines)
                for banned in (
                    "ExitNodes",
                    "EntryNodes",
                    "ExcludeNodes",
                    "UseEntryGuards 0",
                    "EnforceDistinctSubnets 0",
                    "PathsNeededToBuildCircuits",
                    "__LeaveStreamsUnattached",
                    "MapAddress",
                ):
                    self.assertNotIn(banned, torrc)

    def test_conflux_enabled_matches_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            by_name = {p["name"]: p for p in PROFILES}
            for name, enabled in (("stock", "auto"), ("noconflux", "0"), ("latency", "1")):
                inst = TorInstance("/bin/true", by_name[name], out)
                self.assertIn(f"ConfluxEnabled {enabled}", inst.render_torrc())

    def test_ux_line_only_present_when_set(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            by_name = {p["name"]: p for p in PROFILES}
            stock = TorInstance("/bin/true", by_name["stock"], out).render_torrc()
            latency = TorInstance("/bin/true", by_name["latency"], out).render_torrc()
            self.assertNotIn("ConfluxClientUX", stock)
            self.assertIn("ConfluxClientUX latency", latency)


class FindTorTests(unittest.TestCase):
    def test_missing_explicit_binary_returns_none(self) -> None:
        self.assertIsNone(find_tor("/no/such/tor/binary/here"))


if __name__ == "__main__":
    unittest.main()
