import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from run_browser_compare import REQUIRED_DEFAULT_PREFS
from run_torfast_promoted_quality_check import (
    pairwise_quality_failures,
    path_lengths_are_three_hop,
    payload_ok,
    validate_open_launch_quality,
)


def quality_pref_audit() -> dict[str, object]:
    return {
        "ok": True,
        "prefs": {
            key: {"type": "bool" if isinstance(value, bool) else "int", "value": value}
            for key, value in REQUIRED_DEFAULT_PREFS.items()
        },
    }


def fingerprint_snapshot(*, webdriver: bool = True) -> dict[str, object]:
    return {
        "webdriver": webdriver,
        "timezoneOffset": 0,
        "timezone": "UTC",
        "colorDepth": 24,
        "pixelDepth": 24,
        "maxTouchPoints": 0,
        "userAgent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:140.0)",
        "platform": "MacIntel",
        "oscpu": "Intel Mac OS X 10.15",
        "language": "en-US",
        "languages": ["en-US", "en"],
        "hardwareConcurrency": 8,
        "doNotTrack": "unspecified",
        "reducedMotion": False,
        "forcedColors": False,
        "darkScheme": False,
        "pluginsLength": 5,
        "mimeTypesLength": 2,
        "pageUrl": "https://check.torproject.org/",
        "canvasProbe": {
            "total": 256,
            "matches": 0,
            "extractionBlocked": True,
            "error": None,
        },
    }


def reference_fingerprint_snapshot() -> dict[str, object]:
    reference = fingerprint_snapshot(webdriver=False)
    reference["timezone"] = "Atlantic/Reykjavik"
    reference["pageUrl"] = "file:///proof/fingerprint.html"
    return reference


def fingerprint_audit(*, webdriver: bool = True) -> dict[str, object]:
    return {
        "ok": True,
        "snapshot": fingerprint_snapshot(webdriver=webdriver),
    }


def open_launch() -> dict[str, object]:
    return {
        "port": 19450,
        "url": "https://check.torproject.org/",
        "browser": {
            "ok": True,
            "target_stream_snapshot": {
                "ok": True,
                "user_stream_count": 1,
                "observed_stream_count": 1,
                "matched_circuit_path_length_counts": {"3": 1},
                "iso_fields": ["SOCKS_USERNAME,SOCKS_PASSWORD"],
            },
        },
        "browser_default_pref_check": {"ok": True},
        "browser_runtime_reset": {"ok": True},
        "browser_runtime_quality_proof": {"enabled": True, "applied": True},
        "browser_quality_prefs": quality_pref_audit(),
        "browser_fingerprint_snapshot": fingerprint_audit(),
        "effective_proxy_prefs": {
            "network.proxy.socks": "127.0.0.1",
            "network.proxy.socks_port": 19450,
            "network.proxy.socks_remote_dns": True,
            "network.proxy.type": 1,
        },
        "browser_stream_isolation_probe": {
            "ok": True,
            "observed_stream_count": 1,
            "iso_fields": ["SOCKS_USERNAME,SOCKS_PASSWORD"],
        },
        "torrc_quality": {"isolate_socks_auth": True},
    }


class TorfastPromotedQualityCheckTests(unittest.TestCase):
    def test_path_lengths_are_three_hop_accepts_all_three_hop(self) -> None:
        self.assertTrue(
            path_lengths_are_three_hop(
                {"matched_circuit_path_length_counts": {"3": 2}}
            )
        )

    def test_path_lengths_are_three_hop_rejects_other_lengths(self) -> None:
        self.assertFalse(
            path_lengths_are_three_hop(
                {"matched_circuit_path_length_counts": {"2": 1, "3": 1}}
            )
        )

    def test_validate_open_launch_quality_accepts_good_launch(self) -> None:
        result = validate_open_launch_quality(
            open_launch(),
            allow_webdriver_artifact=True,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["failures"], [])
        self.assertTrue(result["browser_quality_pref_check_ok"])
        self.assertTrue(result["browser_fingerprint_validation_ok"])
        self.assertTrue(result["browser_rfp_timezone_spoof_ok"])
        self.assertTrue(result["stable_fingerprint_matches_reference_ok"])
        self.assertTrue(result["effective_proxy_prefs_ok"])
        self.assertTrue(result["target_navigation_proven"])
        self.assertTrue(result["target_stream_three_hop_proven"])
        self.assertTrue(result["target_stream_three_hop_if_known_ok"])

    def test_validate_open_launch_quality_accepts_matching_reference(self) -> None:
        result = validate_open_launch_quality(
            open_launch(),
            allow_webdriver_artifact=True,
            reference_fingerprint_snapshot=reference_fingerprint_snapshot(),
        )

        self.assertTrue(result["ok"])
        self.assertTrue(result["stable_fingerprint_matches_reference_ok"])
        self.assertEqual(result["stable_fingerprint_reference_failures"], [])

    def test_validate_open_launch_quality_rejects_reference_mismatch(self) -> None:
        reference = reference_fingerprint_snapshot()
        reference["hardwareConcurrency"] = 2

        result = validate_open_launch_quality(
            open_launch(),
            allow_webdriver_artifact=True,
            reference_fingerprint_snapshot=reference,
        )

        self.assertFalse(result["ok"])
        self.assertIn("stable_fingerprint_matches_reference_ok", result["failures"])
        self.assertEqual(
            result["stable_fingerprint_reference_failures"],
            ["hardwareConcurrency: expected 2, got 8"],
        )

    def test_validate_open_launch_quality_rejects_unspoofed_timezone(self) -> None:
        launch = open_launch()
        launch["browser_fingerprint_snapshot"]["snapshot"]["timezone"] = (
            "Atlantic/Reykjavik"
        )

        result = validate_open_launch_quality(
            launch,
            allow_webdriver_artifact=True,
        )

        self.assertFalse(result["ok"])
        self.assertIn("browser_rfp_timezone_spoof_ok", result["failures"])

    def test_validate_open_launch_quality_rejects_non_target_page_snapshot(
        self,
    ) -> None:
        launch = open_launch()
        launch["browser_fingerprint_snapshot"]["snapshot"]["pageUrl"] = "about:tor"

        result = validate_open_launch_quality(
            launch,
            allow_webdriver_artifact=True,
        )

        self.assertFalse(result["ok"])
        self.assertIn("browser_fingerprint_page_is_target_ok", result["failures"])

    def test_validate_open_launch_quality_rejects_unblocked_canvas_extraction(
        self,
    ) -> None:
        launch = open_launch()
        launch["browser_fingerprint_snapshot"]["snapshot"]["canvasProbe"] = {
            "total": 256,
            "matches": 256,
            "extractionBlocked": False,
            "error": None,
        }

        result = validate_open_launch_quality(
            launch,
            allow_webdriver_artifact=True,
        )

        self.assertFalse(result["ok"])
        self.assertIn("browser_fingerprint_validation_ok", result["failures"])

    def test_validate_open_launch_quality_rejects_missing_runtime_proof(self) -> None:
        launch = open_launch()
        launch["browser_runtime_quality_proof"] = {"enabled": False, "applied": False}

        result = validate_open_launch_quality(
            launch,
            allow_webdriver_artifact=True,
        )

        self.assertFalse(result["ok"])
        self.assertIn("browser_runtime_quality_proof_enabled", result["failures"])

    def test_validate_open_launch_quality_allows_missing_path_lengths(self) -> None:
        launch = open_launch()
        launch["browser"]["target_stream_snapshot"] = {
            "ok": True,
            "user_stream_count": 1,
            "observed_stream_count": 1,
            "matched_circuit_path_length_counts": {},
            "iso_fields": ["SOCKS_USERNAME,SOCKS_PASSWORD"],
        }

        result = validate_open_launch_quality(
            launch,
            allow_webdriver_artifact=True,
        )

        self.assertTrue(result["ok"])
        self.assertFalse(result["target_stream_three_hop_proven"])
        self.assertTrue(result["target_stream_three_hop_if_known_ok"])

    def test_pairwise_quality_failures_detects_fingerprint_mismatch(self) -> None:
        baseline = open_launch()
        candidate = open_launch()
        candidate["browser_fingerprint_snapshot"] = fingerprint_audit(webdriver=False)

        failures = pairwise_quality_failures(baseline, candidate)

        self.assertEqual(
            failures,
            ["browser_fingerprint_snapshot_mismatch"],
        )

    def test_pairwise_quality_failures_ignores_window_geometry_jitter(self) -> None:
        baseline = open_launch()
        candidate = open_launch()
        baseline["browser_fingerprint_snapshot"]["snapshot"].update(
            {
                "innerHeight": 562,
                "outerHeight": 695,
                "screenWidth": 1200,
                "screenHeight": 500,
                "availWidth": 1200,
                "availHeight": 500,
                "devicePixelRatio": 2,
                "cookieEnabled": True,
            }
        )
        candidate["browser_fingerprint_snapshot"]["snapshot"].update(
            {
                "innerHeight": 563,
                "outerHeight": 696,
                "screenWidth": 1366,
                "screenHeight": 768,
                "availWidth": 1366,
                "availHeight": 768,
                "devicePixelRatio": 1,
                "cookieEnabled": False,
            }
        )

        failures = pairwise_quality_failures(baseline, candidate)

        self.assertEqual(failures, [])

    def test_payload_ok_accepts_all_target_circuit_checks(self) -> None:
        payload = {
            "no_marionette_fingerprint_proof": {
                "ok": True,
                "validation": {"ok": True},
            },
            "c_tor_circuit_checks": {
                "https://check.torproject.org/": {"ok": True},
                "https://www.torproject.org/": {"ok": True},
            },
            "targets": ["https://check.torproject.org/"],
            "delta_vs_baseline": {
                "https://check.torproject.org/": {
                    "combined_wall_seconds": -1.0,
                    "open_browser_elapsed_seconds": -5.0,
                }
            },
            "pairwise_consistency": [{"ok": True}],
            "results": [
                {
                    "warm": {"ok": True},
                    "open": {"ok": True},
                    "stop": {"ok": True},
                    "quality": {"ok": True},
                }
            ],
        }

        self.assertTrue(payload_ok(payload))

    def test_payload_ok_allows_combined_wall_within_noise_guard(self) -> None:
        payload = {
            "no_marionette_fingerprint_proof": {
                "ok": True,
                "validation": {"ok": True},
            },
            "c_tor_circuit_checks": {
                "https://check.torproject.org/": {"ok": True},
            },
            "targets": ["https://check.torproject.org/"],
            "delta_vs_baseline": {
                "https://check.torproject.org/": {
                    "combined_wall_seconds": 0.9,
                    "open_browser_elapsed_seconds": -5.0,
                }
            },
            "pairwise_consistency": [{"ok": True}],
            "results": [
                {
                    "warm": {"ok": True},
                    "open": {"ok": True},
                    "stop": {"ok": True},
                    "quality": {"ok": True},
                }
            ],
        }

        # Guard floor is 1.0s when no baseline spread is recorded.
        self.assertTrue(payload_ok(payload))

        payload["delta_vs_baseline"]["https://check.torproject.org/"][
            "combined_wall_seconds"
        ] = 1.2
        self.assertFalse(payload_ok(payload))

    def test_payload_ok_scales_combined_wall_guard_with_baseline_noise(self) -> None:
        payload = {
            "no_marionette_fingerprint_proof": {
                "ok": True,
                "validation": {"ok": True},
            },
            "c_tor_circuit_checks": {
                "https://check.torproject.org/": {"ok": True},
            },
            "targets": ["https://check.torproject.org/"],
            "profile_names": ["auto", "auto_managedadaptivegencirc_0p126s"],
            "profiles": {
                "https://check.torproject.org/": {
                    "auto": {"stdev_combined_wall_seconds": 4.0},
                }
            },
            "delta_vs_baseline": {
                "https://check.torproject.org/": {
                    "combined_wall_seconds": 2.7,
                    "open_browser_elapsed_seconds": -5.0,
                }
            },
            "pairwise_consistency": [{"ok": True}],
            "results": [
                {
                    "warm": {"ok": True},
                    "open": {"ok": True},
                    "stop": {"ok": True},
                    "quality": {"ok": True},
                }
            ],
        }

        # Guard becomes 0.75 * 4.0 = 3.0s with the baseline spread recorded.
        self.assertTrue(payload_ok(payload))

        payload["delta_vs_baseline"]["https://check.torproject.org/"][
            "combined_wall_seconds"
        ] = 3.2
        self.assertFalse(payload_ok(payload))

    def test_payload_ok_requires_faster_open_browser_elapsed(self) -> None:
        payload = {
            "no_marionette_fingerprint_proof": {
                "ok": True,
                "validation": {"ok": True},
            },
            "c_tor_circuit_checks": {
                "https://check.torproject.org/": {"ok": True},
            },
            "targets": ["https://check.torproject.org/"],
            "delta_vs_baseline": {
                "https://check.torproject.org/": {
                    "combined_wall_seconds": -1.0,
                    "open_browser_elapsed_seconds": 0.1,
                }
            },
            "pairwise_consistency": [{"ok": True}],
            "results": [
                {
                    "warm": {"ok": True},
                    "open": {"ok": True},
                    "stop": {"ok": True},
                    "quality": {"ok": True},
                }
            ],
        }

        self.assertFalse(payload_ok(payload))

    def test_payload_ok_rejects_failed_target_circuit_check(self) -> None:
        payload = {
            "no_marionette_fingerprint_proof": {
                "ok": True,
                "validation": {"ok": True},
            },
            "c_tor_circuit_checks": {
                "https://check.torproject.org/": {"ok": False},
            },
            "targets": ["https://check.torproject.org/"],
            "delta_vs_baseline": {
                "https://check.torproject.org/": {
                    "combined_wall_seconds": -1.0,
                }
            },
            "pairwise_consistency": [{"ok": True}],
            "results": [
                {
                    "warm": {"ok": True},
                    "open": {"ok": True},
                    "stop": {"ok": True},
                    "quality": {"ok": True},
                }
            ],
        }

        self.assertFalse(payload_ok(payload))


if __name__ == "__main__":
    unittest.main()
