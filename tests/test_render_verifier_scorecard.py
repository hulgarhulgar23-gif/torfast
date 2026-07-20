import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from render_verifier_scorecard import render_scorecard, short_target


def sample_summary(*, ok: bool = True) -> dict[str, object]:
    quality = {"ok": True}
    return {
        "ok": ok,
        "cycles": 5,
        "profile_names": ["auto", "candidate"],
        "results": [
            {"quality": quality},
            {"quality": quality},
        ],
        "pairwise_consistency": [{"ok": True}],
        "c_tor_circuit_checks": {
            "https://check.torproject.org/": {
                "ok": True,
                "summary": {
                    "conflux": {
                        "ok": True,
                        "config_value": "auto",
                        "linked_built_count": 6,
                    }
                },
            },
            "https://skipped.example/": {"ok": True, "skipped": True},
        },
        "delta_vs_baseline": {
            "https://check.torproject.org/": {
                "open_browser_elapsed_seconds": -6.84,
                "combined_wall_seconds": -1.834,
            }
        },
        "profiles": {
            "https://check.torproject.org/": {
                "auto": {"stdev_combined_wall_seconds": 2.0},
            }
        },
        "targets": ["https://check.torproject.org/"],
    }


class ScorecardTests(unittest.TestCase):
    def test_pass_scorecard_contents(self) -> None:
        text = render_scorecard(sample_summary(), artifact_name="run-x")
        self.assertIn("**Verdict: PASS** ✅ (5 cycles)", text)
        self.assertIn("| runtime quality runs | ✅ 2/2 |", text)
        self.assertIn("| pairwise fingerprint consistency | ✅ 1/1 |", text)
        self.assertIn("conflux live (6 linked legs)", text)
        self.assertIn("✅ -6.840s", text)
        # guard = max(1.0, 0.75 * 2.0)
        self.assertIn("1.500s", text)
        # skipped circuit checks are not rendered as gates
        self.assertNotIn("skipped.example", text)

    def test_fail_scorecard_verdict(self) -> None:
        text = render_scorecard(sample_summary(ok=False), artifact_name="run-y")
        self.assertIn("**Verdict: FAIL** ❌", text)

    def test_regressing_delta_marked_failed(self) -> None:
        summary = sample_summary()
        summary["delta_vs_baseline"]["https://check.torproject.org/"] = {
            "open_browser_elapsed_seconds": 0.5,
            "combined_wall_seconds": 9.0,
        }
        text = render_scorecard(summary, artifact_name="run-z")
        self.assertIn("❌ +0.500s", text)
        self.assertIn("❌ +9.000s", text)

    def test_short_target(self) -> None:
        self.assertEqual(
            short_target("https://www.torproject.org/download/"),
            "www.torproject.org/download",
        )


if __name__ == "__main__":
    unittest.main()
