import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from run_boot_compare import (
    boot_signal_counts,
    boot_timeline,
    compare_profiles,
    summarize_boot_runs,
)


class BootCompareTests(unittest.TestCase):
    def test_boot_signal_counts_directory_errors(self) -> None:
        boot = {
            "ok": True,
            "seconds": 30.4,
            "lines": [
                "WARN tor_dirclient: directory timed out",
                "INFO tor_proto: NOTDIRECTORY END cell",
                "INFO tor_dirclient: Retiring circuit because of directory failure: Partial response",
                "INFO tor_dirmgr::bootstrap: torfast microdescriptor partial retry chunking signal attempt=3",
                "INFO torfast stream receiver terminal summary stream_id=7",
            ],
        }

        counts = boot_signal_counts(boot)

        self.assertTrue(counts["has_directory_signal"])
        self.assertEqual(counts["directory_failures"], 1)
        self.assertEqual(counts["directory_timeouts"], 1)
        self.assertEqual(counts["notdirectory"], 1)
        self.assertEqual(counts["partial_response"], 1)
        self.assertEqual(counts["partial_retry_chunking_signals"], 1)
        self.assertEqual(counts["terminal_summaries"], 1)
        self.assertEqual(counts["warnings"], 1)
        self.assertIn("Partial response", counts["last_signal"])

    def test_boot_signal_counts_tracks_partial_retry_chunking_without_failure(self) -> None:
        counts = boot_signal_counts(
            {
                "ok": True,
                "seconds": 8.0,
                "lines": [
                    "2026-06-09T22:19:31Z  INFO tor_dirmgr::bootstrap: torfast microdescriptor partial retry chunking signal attempt=9"
                ],
            }
        )

        self.assertFalse(counts["has_directory_signal"])
        self.assertEqual(counts["partial_retry_chunking_signals"], 1)
        self.assertEqual(counts["last_signal"], "")

    def test_boot_signal_counts_skips_warning_only_signal(self) -> None:
        counts = boot_signal_counts(
            {
                "ok": True,
                "seconds": 1.0,
                "lines": ["Jun 08 21:30:14.404 [warn] Fixing permissions"],
            }
        )

        self.assertFalse(counts["has_directory_signal"])
        self.assertEqual(counts["warnings"], 1)
        self.assertEqual(counts["last_signal"], "")

    def test_boot_timeline_tracks_directory_boot_phases(self) -> None:
        boot = {
            "ok": True,
            "seconds": 44.296,
            "lines": [
                "2026-06-08T14:22:54Z  INFO tor_dirmgr::bootstrap: 1: Looking for a consensus. attempt=1",
                "2026-06-08T14:23:03Z  INFO tor_dirclient: Circ 0.0: Retiring circuit because of directory failure: Partial response",
                "2026-06-08T14:23:03Z  WARN tor_dirmgr::bootstrap: error while downloading error=error: directory timed out",
                "2026-06-08T14:23:04Z  INFO tor_dirmgr::bootstrap: 2: Looking for a consensus. attempt=1",
                '2026-06-08T14:23:05Z  INFO tor_dirclient: torfast dirclient timing request_kind="consensus" anonymized=Direct outcome="error" status=None body_bytes=0 elapsed_ms=10003 read_timeout_ms=10000 body_read_calls=0 body_first_byte_ms=0 body_last_byte_ms=0 body_max_read_gap_ms=0 body_timeout_after_last_byte_ms=10003 body_eof=false source_circ="Circ~0.0" error_kind=Some(TorNetworkTimeout)',
                '2026-06-08T14:23:05Z  INFO tor_circmgr::build: torfast channel open timing elapsed_ms=10004 usage_kind="dir" provenance="newly_created" outcome="err" error_kind=TorAccessFailed',
                "2026-06-08T14:23:05Z  INFO tor_circmgr::mgr: torfast circuit selection build failed pending_id=0x96501cb10 pending_age_ms=10005 usage_kind=dir err=Problem opening a channel to [scrubbed]",
                '2026-06-08T14:23:06Z  INFO tor_dirclient: torfast dirclient timing request_kind="microdesc" anonymized=Direct outcome="ok" status=Some(200) body_bytes=746286 elapsed_ms=7726 read_timeout_ms=10000 body_read_calls=729 body_first_byte_ms=100 body_last_byte_ms=7700 body_max_read_gap_ms=900 body_timeout_after_last_byte_ms=0 body_eof=true source_circ="Circ~0.0" error_kind=None',
                '2026-06-08T14:23:06Z  INFO tor_circmgr::build: torfast channel open timing elapsed_ms=50 usage_kind="dir" provenance="preexisting" outcome="ok"',
                "2026-06-08T14:23:06Z  INFO tor_dirmgr::bootstrap: torfast microdescriptor partial retry chunking signal attempt=2",
                "2026-06-08T14:23:07Z  INFO tor_circmgr::mgr: torfast circuit selection build failed pending_id=0x96501cd10 pending_age_ms=12001 usage_kind=dir err=Problem opening a channel to [scrubbed]",
                "2026-06-08T14:23:12Z  INFO tor_proto::client::stream::data: torfast stream receiver terminal summary transfer_ms=7726 max_data_gap_ms=385 relay_data_bytes=746286 max_queued_after_bytes=35756 error_kind=end_done",
                "2026-06-08T14:23:12Z  INFO tor_dirmgr::bootstrap: 1: Downloading certificates for consensus (we are missing 8/8). attempt=1",
                "2026-06-08T14:23:13Z  INFO tor_dirmgr::bootstrap: 1: Downloading microdescriptors (we are missing 9773). attempt=1",
                "2026-06-08T14:23:38Z  INFO tor_dirmgr: Marked consensus usable.",
                "2026-06-08T14:23:38Z  INFO tor_dirmgr: Directory is complete. attempt=1",
                "2026-06-08T14:23:38Z  INFO tor_dirmgr: We have enough information to build circuits.",
                "2026-06-08T14:23:38Z  INFO arti::subcommands::proxy: Sufficiently bootstrapped; proxy now functional.",
            ],
        }

        timeline = boot_timeline(boot)

        self.assertEqual(timeline["consensus_attempts"], 2)
        self.assertEqual(timeline["first_directory_failure_seconds"], 9.0)
        self.assertEqual(timeline["first_directory_timeout_seconds"], 9.0)
        self.assertEqual(
            timeline["first_partial_retry_chunking_signal_seconds"], 12.0
        )
        self.assertEqual(timeline["first_circuit_build_failure_seconds"], 11.0)
        self.assertEqual(timeline["partial_retry_chunking_signals"], 1)
        self.assertEqual(timeline["circuit_build_failures"], 2)
        self.assertEqual(timeline["circuit_build_channel_failures"], 2)
        self.assertEqual(timeline["circuit_build_dir_failures"], 2)
        self.assertEqual(timeline["circuit_build_exit_failures"], 0)
        self.assertEqual(timeline["max_circuit_build_pending_age_ms"], 12001)
        self.assertEqual(timeline["first_certificates_seconds"], 18.0)
        self.assertEqual(timeline["first_microdescriptors_seconds"], 19.0)
        self.assertEqual(timeline["consensus_usable_seconds"], 44.0)
        self.assertEqual(timeline["proxy_functional_seconds"], 44.0)
        self.assertEqual(timeline["terminal_summaries"], 1)
        self.assertEqual(timeline["terminal_summary_max_transfer_ms"], 7726)
        self.assertEqual(timeline["terminal_summary_max_data_gap_ms"], 385)
        self.assertEqual(timeline["terminal_summary_total_relay_bytes"], 746286)
        self.assertEqual(timeline["dirclient_timing_rows"], 2)
        self.assertEqual(timeline["dirclient_timing_error_rows"], 1)
        self.assertEqual(timeline["dirclient_timing_timeout_rows"], 1)
        self.assertEqual(timeline["dirclient_timing_max_elapsed_ms"], 10003)
        self.assertEqual(timeline["dirclient_timing_max_elapsed_kind"], "consensus")
        self.assertEqual(timeline["dirclient_timing_max_body_bytes"], 746286)
        self.assertEqual(timeline["dirclient_timing_max_body_read_calls"], 729)
        self.assertEqual(timeline["dirclient_timing_max_body_first_byte_ms"], 100)
        self.assertEqual(timeline["dirclient_timing_max_body_last_byte_ms"], 7700)
        self.assertEqual(timeline["dirclient_timing_max_body_read_gap_ms"], 900)
        self.assertEqual(
            timeline["dirclient_timing_max_body_timeout_after_last_byte_ms"], 10003
        )
        self.assertEqual(timeline["dirclient_timing_body_eof_rows"], 1)
        self.assertEqual(timeline["dirclient_timing_max_source_circ"], "Circ~0.0")
        self.assertEqual(timeline["dirclient_timing_max_source_circ_rows"], 2)
        self.assertEqual(
            timeline["dirclient_timing_max_timeout_source_circ"], "Circ~0.0"
        )
        self.assertEqual(timeline["dirclient_timing_max_source_circ_timeout_rows"], 1)
        self.assertEqual(timeline["dirclient_timing_max_partial_source_circ"], "")
        self.assertEqual(timeline["dirclient_timing_max_source_circ_partial_rows"], 0)
        self.assertEqual(timeline["channel_open_timing_rows"], 2)
        self.assertEqual(timeline["channel_open_timing_errors"], 1)
        self.assertEqual(timeline["channel_open_dir_rows"], 2)
        self.assertEqual(timeline["channel_open_newly_created_rows"], 1)
        self.assertEqual(timeline["channel_open_preexisting_rows"], 1)
        self.assertEqual(timeline["channel_open_max_elapsed_ms"], 10004)
        self.assertEqual(timeline["channel_open_max_elapsed_usage_kind"], "dir")
        self.assertEqual(timeline["channel_open_max_elapsed_outcome"], "err")

    def test_summarize_boot_runs(self) -> None:
        runs = [
            {
                "run_index": 1,
                "boot": {"ok": True, "seconds": 10.0, "lines": []},
                "signals": {
                    "has_directory_signal": False,
                    "directory_failures": 0,
                    "directory_timeouts": 0,
                    "notdirectory": 0,
                    "partial_response": 0,
                    "partial_retry_chunking_signals": 0,
                    "terminal_summaries": 0,
                    "warnings": 0,
                    "last_signal": "",
                },
            },
            {
                "run_index": 2,
                "boot": {
                    "ok": True,
                    "seconds": 30.0,
                    "lines": [
                        "WARN tor_dirclient: directory timed out",
                        "INFO tor_dirmgr::bootstrap: torfast microdescriptor partial retry chunking signal attempt=4",
                    ],
                },
                "signals": boot_signal_counts(
                    {
                        "ok": True,
                        "seconds": 30.0,
                        "lines": [
                            "WARN tor_dirclient: directory timed out",
                            "INFO tor_dirmgr::bootstrap: torfast microdescriptor partial retry chunking signal attempt=4",
                        ],
                    }
                ),
            },
            {
                "run_index": 3,
                "boot": {"ok": True, "seconds": 20.0, "lines": []},
                "signals": {
                    "has_directory_signal": False,
                    "directory_failures": 0,
                    "directory_timeouts": 0,
                    "notdirectory": 0,
                    "partial_response": 0,
                    "partial_retry_chunking_signals": 0,
                    "terminal_summaries": 0,
                    "warnings": 0,
                    "last_signal": "",
                },
            },
        ]

        summary = summarize_boot_runs(runs)

        self.assertEqual(summary["runs"], 3)
        self.assertEqual(summary["successes"], 3)
        self.assertEqual(summary["failures"], 0)
        self.assertEqual(summary["directory_signal_runs"], 1)
        self.assertEqual(summary["median_boot_seconds"], 20.0)
        self.assertEqual(summary["min_boot_seconds"], 10.0)
        self.assertEqual(summary["max_boot_seconds"], 30.0)
        self.assertEqual(summary["slowest_run_index"], 2)
        self.assertEqual(summary["directory_timeouts"], 1)
        self.assertEqual(summary["partial_retry_chunking_signals"], 1)

    def test_summarize_boot_runs_tracks_circuit_build_failures(self) -> None:
        runs = [
            {
                "run_index": 1,
                "boot": {
                    "ok": True,
                    "seconds": 21.0,
                    "lines": [
                        "2026-06-08T21:50:30Z  INFO tor_dirmgr::bootstrap: 1: Looking for a consensus. attempt=1",
                        '2026-06-08T21:50:40Z  INFO tor_circmgr::build: torfast channel open timing elapsed_ms=10004 usage_kind="dir" provenance="newly_created" outcome="err" error_kind=TorAccessFailed',
                        "2026-06-08T21:50:40Z  INFO tor_circmgr::mgr: torfast circuit selection build failed pending_id=0x96501cb10 pending_age_ms=10005 usage_kind=dir err=Problem opening a channel to [scrubbed]",
                        "2026-06-08T21:50:42Z  INFO tor_dirmgr::bootstrap: 1: Downloading certificates for consensus (we are missing 8/8). attempt=1",
                        "2026-06-08T21:50:42Z  INFO tor_dirmgr::bootstrap: 1: Downloading microdescriptors (we are missing 9786). attempt=1",
                        "2026-06-08T21:50:53Z  INFO arti::subcommands::proxy: Sufficiently bootstrapped; proxy now functional.",
                    ],
                },
            },
            {
                "run_index": 2,
                "boot": {
                    "ok": True,
                    "seconds": 8.0,
                    "lines": [
                        "2026-06-08T21:51:00Z  INFO tor_dirmgr::bootstrap: 1: Looking for a consensus. attempt=1",
                        "2026-06-08T21:51:03Z  INFO tor_dirmgr::bootstrap: 1: Downloading microdescriptors (we are missing 9786). attempt=1",
                        "2026-06-08T21:51:08Z  INFO arti::subcommands::proxy: Sufficiently bootstrapped; proxy now functional.",
                    ],
                },
            },
        ]

        summary = summarize_boot_runs(runs)

        self.assertEqual(summary["circuit_build_failures"], 1)
        self.assertEqual(summary["circuit_build_channel_failures"], 1)
        self.assertEqual(summary["circuit_build_dir_failures"], 1)
        self.assertEqual(summary["circuit_build_exit_failures"], 0)
        self.assertEqual(summary["median_first_circuit_build_failure_seconds"], 10.0)
        self.assertEqual(summary["max_circuit_build_pending_age_ms"], 10005)
        self.assertEqual(summary["channel_open_timing_rows"], 1)
        self.assertEqual(summary["channel_open_timing_errors"], 1)
        self.assertEqual(summary["channel_open_dir_rows"], 1)
        self.assertEqual(summary["max_channel_open_elapsed_ms"], 10004)

    def test_compare_profiles_reports_median_delta(self) -> None:
        profiles = {
            "arti_release_boot": {"summary": {"median_boot_seconds": 8.0}},
            "local_c_tor_boot": {"summary": {"median_boot_seconds": 10.5}},
            "arti_release_boot_dirspread": {
                "summary": {"median_boot_seconds": 7.5}
            },
            "arti_release_boot_incrmd": {"summary": {"median_boot_seconds": 6.0}},
            "arti_release_boot_mdearlyusable": {
                "summary": {"median_boot_seconds": 5.5}
            },
            "arti_release_boot_dirread5000ms": {
                "summary": {"median_boot_seconds": 7.0}
            },
            "arti_release_boot_dirprogress3000ms": {
                "summary": {"median_boot_seconds": 6.5}
            },
            "arti_release_boot_mdbodymax7000ms": {
                "summary": {"median_boot_seconds": 6.25}
            },
            "arti_release_boot_mdminrate98304bps": {
                "summary": {"median_boot_seconds": 6.75}
            },
            "arti_release_boot_mdretrydelay500ms": {
                "summary": {"median_boot_seconds": 6.9}
            },
            "arti_release_boot_mdearlyretrypartial": {
                "summary": {"median_boot_seconds": 6.8}
            },
            "arti_release_boot_mdpartialretrychunking": {
                "summary": {"median_boot_seconds": 6.1}
            },
            "arti_release_boot_mdsrcspread": {
                "summary": {"median_boot_seconds": 6.6}
            },
            "arti_release_boot_mdsrcspreadearlyusable": {
                "summary": {"median_boot_seconds": 6.4}
            },
            "arti_release_boot_mdsrcspreadpending": {
                "summary": {"median_boot_seconds": 6.3}
            },
            "arti_release_boot_mdsrcspreadpendingearlyusable": {
                "summary": {"median_boot_seconds": 6.2}
            },
            "arti_release_boot_mdsrcspreadpendingearlyusablepartialretrychunking": {
                "summary": {"median_boot_seconds": 5.8}
            },
        }

        comparison = compare_profiles(profiles)

        self.assertEqual(comparison["arti_minus_local_median_boot_seconds"], -2.5)
        self.assertEqual(comparison["faster_median_boot_profile"], "arti_release_boot")
        self.assertEqual(
            comparison["dirspread_minus_default_median_boot_seconds"], -0.5
        )
        self.assertEqual(
            comparison["faster_arti_median_boot_profile"],
            "arti_release_boot_dirspread",
        )
        self.assertEqual(comparison["incrmd_minus_default_median_boot_seconds"], -2.0)
        self.assertEqual(
            comparison["faster_arti_incrmd_median_boot_profile"],
            "arti_release_boot_incrmd",
        )
        self.assertEqual(
            comparison["mdearlyusable_minus_default_median_boot_seconds"], -2.5
        )
        self.assertEqual(
            comparison["faster_arti_mdearlyusable_median_boot_profile"],
            "arti_release_boot_mdearlyusable",
        )
        self.assertEqual(
            comparison[
                "arti_release_boot_dirread5000ms_minus_default_median_boot_seconds"
            ],
            -1.0,
        )
        self.assertEqual(
            comparison[
                "faster_arti_release_boot_dirread5000ms_median_boot_profile"
            ],
            "arti_release_boot_dirread5000ms",
        )
        self.assertEqual(
            comparison[
                "arti_release_boot_dirprogress3000ms_minus_default_median_boot_seconds"
            ],
            -1.5,
        )
        self.assertEqual(
            comparison[
                "faster_arti_release_boot_dirprogress3000ms_median_boot_profile"
            ],
            "arti_release_boot_dirprogress3000ms",
        )
        self.assertEqual(
            comparison[
                "arti_release_boot_mdbodymax7000ms_minus_default_median_boot_seconds"
            ],
            -1.75,
        )
        self.assertEqual(
            comparison[
                "faster_arti_release_boot_mdbodymax7000ms_median_boot_profile"
            ],
            "arti_release_boot_mdbodymax7000ms",
        )
        self.assertEqual(
            comparison[
                "arti_release_boot_mdminrate98304bps_minus_default_median_boot_seconds"
            ],
            -1.25,
        )
        self.assertEqual(
            comparison[
                "faster_arti_release_boot_mdminrate98304bps_median_boot_profile"
            ],
            "arti_release_boot_mdminrate98304bps",
        )
        self.assertEqual(
            comparison[
                "arti_release_boot_mdretrydelay500ms_minus_default_median_boot_seconds"
            ],
            -1.1,
        )
        self.assertEqual(
            comparison[
                "faster_arti_release_boot_mdretrydelay500ms_median_boot_profile"
            ],
            "arti_release_boot_mdretrydelay500ms",
        )
        self.assertEqual(
            comparison[
                "arti_release_boot_mdearlyretrypartial_minus_default_median_boot_seconds"
            ],
            -1.2,
        )
        self.assertEqual(
            comparison[
                "faster_arti_release_boot_mdearlyretrypartial_median_boot_profile"
            ],
            "arti_release_boot_mdearlyretrypartial",
        )
        self.assertEqual(
            comparison[
                "arti_release_boot_mdpartialretrychunking_minus_default_median_boot_seconds"
            ],
            -1.9,
        )
        self.assertEqual(
            comparison[
                "faster_arti_release_boot_mdpartialretrychunking_median_boot_profile"
            ],
            "arti_release_boot_mdpartialretrychunking",
        )
        self.assertEqual(
            comparison[
                "arti_release_boot_mdsrcspread_minus_default_median_boot_seconds"
            ],
            -1.4,
        )
        self.assertEqual(
            comparison[
                "faster_arti_release_boot_mdsrcspread_median_boot_profile"
            ],
            "arti_release_boot_mdsrcspread",
        )
        self.assertEqual(
            comparison[
                "arti_release_boot_mdsrcspreadearlyusable_minus_default_median_boot_seconds"
            ],
            -1.6,
        )
        self.assertEqual(
            comparison[
                "faster_arti_release_boot_mdsrcspreadearlyusable_median_boot_profile"
            ],
            "arti_release_boot_mdsrcspreadearlyusable",
        )
        self.assertEqual(
            comparison[
                "arti_release_boot_mdsrcspreadpending_minus_default_median_boot_seconds"
            ],
            -1.7,
        )
        self.assertEqual(
            comparison[
                "faster_arti_release_boot_mdsrcspreadpending_median_boot_profile"
            ],
            "arti_release_boot_mdsrcspreadpending",
        )
        self.assertEqual(
            comparison[
                "arti_release_boot_mdsrcspreadpendingearlyusable_minus_default_median_boot_seconds"
            ],
            -1.8,
        )
        self.assertEqual(
            comparison[
                "faster_arti_release_boot_mdsrcspreadpendingearlyusable_median_boot_profile"
            ],
            "arti_release_boot_mdsrcspreadpendingearlyusable",
        )
        self.assertEqual(
            comparison[
                "arti_release_boot_mdsrcspreadpendingearlyusablepartialretrychunking_minus_default_median_boot_seconds"
            ],
            -2.2,
        )
        self.assertEqual(
            comparison[
                "faster_arti_release_boot_mdsrcspreadpendingearlyusablepartialretrychunking_median_boot_profile"
            ],
            "arti_release_boot_mdsrcspreadpendingearlyusablepartialretrychunking",
        )


if __name__ == "__main__":
    unittest.main()
