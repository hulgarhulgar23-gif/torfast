import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from check_c_tor_circuits import (
    CONFLUX_LINKED_MIN_BUILT,
    collect_conflux_runtime_proof,
    count_built_conflux_linked,
    parse_getconf_value,
    short_summary,
    validate_circuit,
)


def relay(name, fingerprint, *, flags, ipv4, family=None):
    return {
        "name": name,
        "fingerprint": fingerprint,
        "flags": flags,
        "ipv4": ipv4,
        "family": family or [],
    }


class CircuitQualityTests(unittest.TestCase):
    def test_accepts_safe_three_hop_circuit(self) -> None:
        circuit = {
            "path": [
                relay("guard", "A" * 40, flags=["Guard", "Fast", "Running", "Valid"], ipv4="10.1.1.1"),
                relay("middle", "B" * 40, flags=["Fast", "Running", "Valid"], ipv4="11.1.1.1"),
                relay("exit", "C" * 40, flags=["Exit", "Fast", "Running", "Valid"], ipv4="12.1.1.1"),
            ]
        }

        self.assertEqual(validate_circuit(circuit), [])

    def test_rejects_family_overlap(self) -> None:
        circuit = {
            "path": [
                relay(
                    "guard",
                    "A" * 40,
                    flags=["Guard", "Fast", "Running", "Valid"],
                    ipv4="10.1.1.1",
                    family=["B" * 40],
                ),
                relay("middle", "B" * 40, flags=["Fast", "Running", "Valid"], ipv4="11.1.1.1"),
                relay("exit", "C" * 40, flags=["Exit", "Fast", "Running", "Valid"], ipv4="12.1.1.1"),
            ]
        }

        self.assertIn("relays_share_family:guard:middle", validate_circuit(circuit))

    def test_rejects_same_ipv4_subnet(self) -> None:
        circuit = {
            "path": [
                relay("guard", "A" * 40, flags=["Guard", "Fast", "Running", "Valid"], ipv4="10.1.1.1"),
                relay("middle", "B" * 40, flags=["Fast", "Running", "Valid"], ipv4="10.1.2.1"),
                relay("exit", "C" * 40, flags=["Exit", "Fast", "Running", "Valid"], ipv4="12.1.1.1"),
            ]
        }

        self.assertIn("relays_share_ipv4_subnet:guard:middle", validate_circuit(circuit))


def circuit_status_reply(rows: list[str]) -> str:
    return "250+circuit-status=\r\n" + "\r\n".join(rows) + "\r\n.\r\n250 OK\r\n"


class FakeControlClient:
    def __init__(
        self,
        *,
        conflux_config_reply: str,
        circuit_status_replies: list[str],
    ):
        self.conflux_config_reply = conflux_config_reply
        self.circuit_status_replies = list(circuit_status_replies)
        self.commands: list[str] = []

    def command(self, command: str) -> str:
        self.commands.append(command)
        if command == "GETCONF ConfluxEnabled":
            return self.conflux_config_reply
        if command == "GETINFO circuit-status":
            if len(self.circuit_status_replies) > 1:
                return self.circuit_status_replies.pop(0)
            return self.circuit_status_replies[0]
        raise AssertionError(f"unexpected command: {command}")


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


LINKED_ROW = (
    "10 BUILT ${fp1}~g,${fp2}~m,${fp3}~e"
    " BUILD_FLAGS=NEED_CAPACITY PURPOSE=CONFLUX_LINKED".format(
        fp1="A" * 40, fp2="B" * 40, fp3="C" * 40
    )
)
SECOND_LINKED_ROW = (
    "11 BUILT ${fp1}~g,${fp2}~m,${fp3}~e"
    " BUILD_FLAGS=NEED_CAPACITY PURPOSE=CONFLUX_LINKED".format(
        fp1="A" * 40, fp2="D" * 40, fp3="C" * 40
    )
)
GENERAL_ROW = (
    "12 BUILT ${fp1}~g,${fp2}~m,${fp3}~e"
    " BUILD_FLAGS=NEED_CAPACITY PURPOSE=GENERAL".format(
        fp1="A" * 40, fp2="E" * 40, fp3="F" * 40
    )
)
UNLINKED_ROW = (
    "13 EXTENDED ${fp1}~g,${fp2}~m,${fp3}~e"
    " BUILD_FLAGS=NEED_CAPACITY PURPOSE=CONFLUX_UNLINKED".format(
        fp1="A" * 40, fp2="G" * 40, fp3="H" * 40
    )
)


class ConfluxRuntimeProofTests(unittest.TestCase):
    def test_parse_getconf_value_reads_plain_value(self) -> None:
        self.assertEqual(
            parse_getconf_value("250 ConfluxEnabled=auto\r\n", "ConfluxEnabled"),
            "auto",
        )

    def test_parse_getconf_value_reads_multiline_reply(self) -> None:
        reply = "250-ConfluxEnabled=1\r\n250 SocksPort=9050\r\n"
        self.assertEqual(parse_getconf_value(reply, "ConfluxEnabled"), "1")

    def test_parse_getconf_value_returns_none_when_missing(self) -> None:
        self.assertIsNone(parse_getconf_value("250 OK\r\n", "ConfluxEnabled"))

    def test_count_built_conflux_linked_ignores_unlinked_and_general(self) -> None:
        circuits = [
            {"status": "BUILT", "purpose": "CONFLUX_LINKED"},
            {"status": "BUILT", "purpose": "CONFLUX_LINKED"},
            {"status": "EXTENDED", "purpose": "CONFLUX_LINKED"},
            {"status": "BUILT", "purpose": "CONFLUX_UNLINKED"},
            {"status": "BUILT", "purpose": "GENERAL"},
        ]
        self.assertEqual(count_built_conflux_linked(circuits), 2)

    def test_proof_passes_when_linked_set_is_present(self) -> None:
        client = FakeControlClient(
            conflux_config_reply="250 ConfluxEnabled=auto\r\n",
            circuit_status_replies=[
                circuit_status_reply([LINKED_ROW, SECOND_LINKED_ROW, GENERAL_ROW])
            ],
        )
        clock = FakeClock()

        proof, circuits = collect_conflux_runtime_proof(
            client, monotonic=clock.monotonic, sleep=clock.sleep
        )

        self.assertTrue(proof["ok"])
        self.assertTrue(proof["config_ok"])
        self.assertEqual(proof["config_value"], "auto")
        self.assertEqual(proof["linked_built_count"], 2)
        self.assertEqual(proof["linked_built_required"], CONFLUX_LINKED_MIN_BUILT)
        self.assertEqual(len(circuits), 3)

    def test_proof_polls_until_legs_link(self) -> None:
        client = FakeControlClient(
            conflux_config_reply="250 ConfluxEnabled=auto\r\n",
            circuit_status_replies=[
                circuit_status_reply([UNLINKED_ROW, GENERAL_ROW]),
                circuit_status_reply([LINKED_ROW, GENERAL_ROW]),
                circuit_status_reply([LINKED_ROW, SECOND_LINKED_ROW, GENERAL_ROW]),
            ],
        )
        clock = FakeClock()

        proof, circuits = collect_conflux_runtime_proof(
            client, monotonic=clock.monotonic, sleep=clock.sleep
        )

        self.assertTrue(proof["ok"])
        self.assertEqual(proof["linked_built_count"], 2)
        self.assertEqual(
            client.commands.count("GETINFO circuit-status"),
            3,
        )
        self.assertEqual(len(circuits), 3)

    def test_proof_fails_when_legs_never_link(self) -> None:
        client = FakeControlClient(
            conflux_config_reply="250 ConfluxEnabled=auto\r\n",
            circuit_status_replies=[circuit_status_reply([GENERAL_ROW])],
        )
        clock = FakeClock()

        proof, _ = collect_conflux_runtime_proof(
            client,
            wait_max_seconds=5.0,
            poll_seconds=1.0,
            monotonic=clock.monotonic,
            sleep=clock.sleep,
        )

        self.assertFalse(proof["ok"])
        self.assertTrue(proof["config_ok"])
        self.assertEqual(proof["linked_built_count"], 0)
        self.assertGreaterEqual(proof["wait_seconds"], 5.0)

    def test_proof_fails_when_config_rejects_conflux(self) -> None:
        client = FakeControlClient(
            conflux_config_reply="250 ConfluxEnabled=0\r\n",
            circuit_status_replies=[
                circuit_status_reply([LINKED_ROW, SECOND_LINKED_ROW])
            ],
        )
        clock = FakeClock()

        proof, _ = collect_conflux_runtime_proof(
            client, monotonic=clock.monotonic, sleep=clock.sleep
        )

        self.assertFalse(proof["ok"])
        self.assertFalse(proof["config_ok"])
        self.assertEqual(proof["config_value"], "0")

    def test_short_summary_reports_conflux_proof(self) -> None:
        payload = {
            "ok": True,
            "boot": {"ok": True},
            "fetch": {"ok": True},
            "checked_circuit_count": 3,
            "circuits": [],
            "conflux": {
                "ok": True,
                "config_value": "auto",
                "config_ok": True,
                "linked_built_count": 4,
                "linked_built_required": 2,
                "wait_seconds": 0.0,
            },
        }

        summary = short_summary(payload)

        self.assertEqual(
            summary["conflux"],
            {"ok": True, "config_value": "auto", "linked_built_count": 4},
        )

    def test_short_summary_handles_missing_conflux_proof(self) -> None:
        payload = {
            "ok": False,
            "boot": {"ok": False},
            "fetch": None,
            "checked_circuit_count": 0,
            "circuits": [],
            "conflux": None,
        }

        self.assertIsNone(short_summary(payload)["conflux"])


if __name__ == "__main__":
    unittest.main()
