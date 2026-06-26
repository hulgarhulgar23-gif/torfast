import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from check_arti_rpc_path import combine_sample_validations, validate_path_description


def relay(relay_id, ipv4):
    return {
        "known_relay": {
            "ids": {"ed25519": relay_id},
            "addrs": [f"{ipv4}:9001"],
        }
    }


class ArtiRpcPathTests(unittest.TestCase):
    def test_accepts_three_hop_runtime_path_shape(self) -> None:
        result = validate_path_description(
            {
                "path": {
                    "circuit-1": [
                        relay("a", "10.1.1.1"),
                        relay("b", "11.1.1.1"),
                        relay("c", "12.1.1.1"),
                    ]
                }
            }
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["errors"], [])

    def test_rejects_reused_relay(self) -> None:
        result = validate_path_description(
            {
                "path": {
                    "circuit-1": [
                        relay("a", "10.1.1.1"),
                        relay("b", "11.1.1.1"),
                        relay("a", "12.1.1.1"),
                    ]
                }
            }
        )

        self.assertIn("path_reuses_relay:circuit-1", result["errors"])

    def test_rejects_same_ipv4_16(self) -> None:
        result = validate_path_description(
            {
                "path": {
                    "circuit-1": [
                        relay("a", "10.1.1.1"),
                        relay("b", "10.1.2.1"),
                        relay("c", "12.1.1.1"),
                    ]
                }
            }
        )

        self.assertIn(
            "path_reuses_ipv4_16:circuit-1:10.1.1.1:10.1.2.1",
            result["errors"],
        )

    def test_combines_sample_validations(self) -> None:
        first = validate_path_description(
            {
                "path": {
                    "path-a": [
                        relay("a", "10.1.1.1"),
                        relay("b", "11.1.1.1"),
                        relay("c", "12.1.1.1"),
                    ]
                }
            }
        )
        second = validate_path_description(
            {
                "path": {
                    "path-b": [
                        relay("d", "13.1.1.1"),
                        relay("e", "13.1.2.1"),
                        relay("f", "14.1.1.1"),
                    ]
                }
            }
        )

        result = combine_sample_validations(
            [
                {"index": 0, "validation": first},
                {"index": 1, "validation": second},
            ]
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["checked_paths"], 2)
        self.assertIn(
            "sample_1:path_reuses_ipv4_16:path-b:13.1.1.1:13.1.2.1",
            result["errors"],
        )


if __name__ == "__main__":
    unittest.main()
