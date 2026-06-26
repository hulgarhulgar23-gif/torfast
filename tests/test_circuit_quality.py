import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from check_c_tor_circuits import validate_circuit


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


if __name__ == "__main__":
    unittest.main()
