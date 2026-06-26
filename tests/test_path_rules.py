import unittest

from torfast.path_rules import relay, validate_three_hop_path


class PathRulesTests(unittest.TestCase):
    def test_accepts_basic_safe_path(self) -> None:
        path = [
            relay("guard", "g", flags=["Fast", "Guard"], ipv4="10.1.0.1"),
            relay("middle", "m", flags=["Fast"], ipv4="11.1.0.1"),
            relay("exit", "e", flags=["Fast", "Exit"], ipv4="12.1.0.1", exit_ports=[443]),
        ]

        self.assertEqual(validate_three_hop_path(path, target_port=443), [])

    def test_rejects_short_path(self) -> None:
        path = [
            relay("guard", "g", flags=["Fast", "Guard"]),
            relay("exit", "e", flags=["Fast", "Exit"], exit_ports=[443]),
        ]

        self.assertIn("path_length_must_be_3", validate_three_hop_path(path, target_port=443))

    def test_rejects_missing_guard(self) -> None:
        path = [
            relay("not-guard", "a", flags=["Fast"], ipv4="10.1.0.1"),
            relay("middle", "m", flags=["Fast"], ipv4="11.1.0.1"),
            relay("exit", "e", flags=["Fast", "Exit"], ipv4="12.1.0.1", exit_ports=[443]),
        ]

        errors = validate_three_hop_path(path, target_port=443)

        self.assertIn("first_hop_must_be_guard:not-guard", errors)

    def test_rejects_duplicate_relay(self) -> None:
        path = [
            relay("guard", "same", flags=["Fast", "Guard"], ipv4="10.1.0.1"),
            relay("middle", "m", flags=["Fast"], ipv4="11.1.0.1"),
            relay("again", "same", flags=["Fast", "Exit"], ipv4="12.1.0.1", exit_ports=[443]),
        ]

        errors = validate_three_hop_path(path, target_port=443)

        self.assertIn("path_reuses_relay", errors)

    def test_rejects_family_overlap(self) -> None:
        path = [
            relay("guard", "g", flags=["Fast", "Guard"], family=["fam1"], ipv4="10.1.0.1"),
            relay("middle", "m", flags=["Fast"], family=["fam1"], ipv4="11.1.0.1"),
            relay("exit", "e", flags=["Fast", "Exit"], ipv4="12.1.0.1", exit_ports=[443]),
        ]

        errors = validate_three_hop_path(path, target_port=443)

        self.assertIn("relays_share_family:guard:middle", errors)

    def test_rejects_same_ipv4_subnet(self) -> None:
        path = [
            relay("guard", "g", flags=["Fast", "Guard"], ipv4="10.1.0.1"),
            relay("middle", "m", flags=["Fast"], ipv4="10.1.2.3"),
            relay("exit", "e", flags=["Fast", "Exit"], ipv4="12.1.0.1", exit_ports=[443]),
        ]

        errors = validate_three_hop_path(path, target_port=443)

        self.assertIn("relays_share_ipv4_subnet:guard:middle", errors)

    def test_rejects_exit_policy_miss(self) -> None:
        path = [
            relay("guard", "g", flags=["Fast", "Guard"], ipv4="10.1.0.1"),
            relay("middle", "m", flags=["Fast"], ipv4="11.1.0.1"),
            relay("exit", "e", flags=["Fast", "Exit"], ipv4="12.1.0.1", exit_ports=[80]),
        ]

        errors = validate_three_hop_path(path, target_port=443)

        self.assertIn("exit_policy_rejects_port:exit:443", errors)


if __name__ == "__main__":
    unittest.main()
