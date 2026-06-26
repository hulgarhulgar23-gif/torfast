#!/usr/bin/env python3
"""Check Arti source/config quality defaults.

This is static proof only. It does not prove live Arti circuit paths.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
import subprocess
import sys
import time


SOURCE_FILES = {
    "config": "crates/tor-circmgr/src/config.rs",
    "path": "crates/tor-circmgr/src/path.rs",
    "exitpath": "crates/tor-circmgr/src/path/exitpath.rs",
    "example_config": "crates/arti/src/arti-example-config.toml",
    "oldest_config": "crates/arti/src/oldest-supported-config.toml",
    "cargo": "crates/arti/Cargo.toml",
    "arti_client": "crates/arti-client/src/client.rs",
    "lib": "crates/arti/src/lib.rs",
    "circmgr_lib": "crates/tor-circmgr/src/lib.rs",
    "circmgr_build": "crates/tor-circmgr/src/build.rs",
    "circmgr_hspool": "crates/tor-circmgr/src/hspool.rs",
    "circmgr_hspool_pool": "crates/tor-circmgr/src/hspool/pool.rs",
    "circmgr_mgr": "crates/tor-circmgr/src/mgr.rs",
    "circmgr_impls": "crates/tor-circmgr/src/impls.rs",
    "circmgr_preemptive": "crates/tor-circmgr/src/preemptive.rs",
    "circmgr_usage": "crates/tor-circmgr/src/usage.rs",
    "tor_hsclient_connect": "crates/tor-hsclient/src/connect.rs",
    "dirmgr_bootstrap": "crates/tor-dirmgr/src/bootstrap.rs",
    "dirmgr_docid": "crates/tor-dirmgr/src/docid.rs",
    "tor_dirclient": "crates/tor-dirclient/src/lib.rs",
    "tor_proto_client": "crates/tor-proto/src/client.rs",
    "tor_proto_circuit": "crates/tor-proto/src/client/circuit.rs",
    "tor_proto_circuit_circhop": "crates/tor-proto/src/circuit/circhop.rs",
    "tor_proto_reactor_circuit": "crates/tor-proto/src/client/reactor/circuit.rs",
    "tor_proto_reactor_circuit_circhop": (
        "crates/tor-proto/src/client/reactor/circuit/circhop.rs"
    ),
    "tor_proto_channel_reactor": "crates/tor-proto/src/channel/reactor.rs",
    "tor_proto_data_stream": "crates/tor-proto/src/client/stream/data.rs",
    "tor_proto_stream_raw": "crates/tor-proto/src/stream/raw.rs",
    "socks_proxy": "crates/arti/src/proxy/socks.rs",
}


@dataclass
class QualityCheck:
    name: str
    ok: bool
    evidence: list[str]
    note: str


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--arti-root", default="upstream/arti")
    parser.add_argument("--arti-bin", default="upstream/arti/target/release/arti")
    args = parser.parse_args()

    arti_root = Path(args.arti_root).resolve()
    arti_bin = Path(args.arti_bin).resolve()
    run_id = time.strftime("%Y%m%dT%H%M%S")
    output_dir = Path("results") / f"arti-quality-config-{run_id}"
    output_dir.mkdir(parents=True, exist_ok=True)

    payload = run_check(arti_root=arti_root, arti_bin=arti_bin)
    output_path = output_dir / "arti-quality-config.json"
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")

    print(f"wrote {output_path}")
    print(json.dumps(short_summary(payload), indent=2, sort_keys=True))
    return 0 if payload["ok"] else 1


def run_check(*, arti_root: Path, arti_bin: Path | None = None) -> dict[str, object]:
    sources = read_sources(arti_root)
    help_text = read_arti_help(arti_bin) if arti_bin else None
    checks = evaluate_sources(sources=sources, help_text=help_text)
    failures = [check for check in checks if not check.ok]
    return {
        "ok": not failures,
        "claim": (
            "Arti source/config keeps key Tor quality defaults. "
            "This is not runtime circuit-path proof."
        ),
        "evidence_type": "static_source_config",
        "runtime_circuit_path_proof": False,
        "arti_root": str(arti_root),
        "arti_bin": str(arti_bin) if arti_bin else None,
        "checks": [asdict(check) for check in checks],
    }


def read_sources(arti_root: Path) -> dict[str, str]:
    sources: dict[str, str] = {}
    for key, relative in SOURCE_FILES.items():
        path = arti_root / relative
        sources[key] = path.read_text()
    return sources


def read_arti_help(arti_bin: Path | None) -> str | None:
    if arti_bin is None or not arti_bin.exists():
        return None
    chunks = []
    for args in ([str(arti_bin), "--help"], [str(arti_bin), "proxy", "--help"]):
        result = subprocess.run(
            args,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=20,
        )
        chunks.append(result.stdout)
    return "\n".join(chunks)


def evaluate_sources(
    *,
    sources: dict[str, str],
    help_text: str | None = None,
) -> list[QualityCheck]:
    config = sources["config"]
    path = sources["path"]
    exitpath = sources["exitpath"]
    example_config = sources["example_config"]
    oldest_config = sources["oldest_config"]
    cargo = sources["cargo"]
    arti_client = sources["arti_client"]
    lib = sources["lib"]
    circmgr_lib = sources["circmgr_lib"]
    circmgr_build = sources["circmgr_build"]
    circmgr_hspool = sources["circmgr_hspool"]
    circmgr_hspool_pool = sources["circmgr_hspool_pool"]
    circmgr_mgr = sources["circmgr_mgr"]
    circmgr_impls = sources["circmgr_impls"]
    circmgr_preemptive = sources["circmgr_preemptive"]
    circmgr_usage = sources["circmgr_usage"]
    tor_hsclient_connect = sources["tor_hsclient_connect"]
    dirmgr_bootstrap = sources["dirmgr_bootstrap"]
    dirmgr_docid = sources["dirmgr_docid"]
    tor_dirclient = sources["tor_dirclient"]
    tor_proto_client = sources["tor_proto_client"]
    tor_proto_circuit = sources["tor_proto_circuit"]
    tor_proto_circuit_circhop = sources["tor_proto_circuit_circhop"]
    tor_proto_reactor_circuit = sources["tor_proto_reactor_circuit"]
    tor_proto_reactor_circuit_circhop = sources["tor_proto_reactor_circuit_circhop"]
    tor_proto_channel_reactor = sources["tor_proto_channel_reactor"]
    tor_proto_data_stream = sources["tor_proto_data_stream"]
    tor_proto_stream_raw = sources["tor_proto_stream_raw"]
    socks_proxy = sources["socks_proxy"]

    checks = [
        check_regex(
            "default_ipv4_subnet_family_prefix_is_16",
            config,
            r"fn\s+ipv4_prefix_default\(\)\s*->\s*u8\s*\{\s*16\s*\}",
            ["crates/tor-circmgr/src/config.rs"],
            "Arti default keeps relays from the same IPv4 /16 in one circuit.",
        ),
        check_regex(
            "default_ipv6_subnet_family_prefix_is_32",
            config,
            r"fn\s+ipv6_prefix_default\(\)\s*->\s*u8\s*\{\s*32\s*\}",
            ["crates/tor-circmgr/src/config.rs"],
            "Arti default keeps relays from the same IPv6 /32 in one circuit.",
        ),
        check_regex(
            "default_reachable_addrs_is_all",
            config,
            r"fn\s+default_reachable_addrs\(\).*?\{\s*vec!\[AddrPortPattern::new_all\(\)\]\s*\}",
            ["crates/tor-circmgr/src/config.rs"],
            "Arti default does not restrict relay reachability to a risky small set.",
        ),
        check_contains_all(
            "example_configs_keep_path_rule_defaults",
            example_config + "\n" + oldest_config,
            [
                "#ipv4_subnet_family_prefix = 16",
                "#ipv6_subnet_family_prefix = 32",
                '#reachable_addrs = [ "*:*" ]',
            ],
            [
                "crates/arti/src/arti-example-config.toml",
                "crates/arti/src/oldest-supported-config.toml",
            ],
            "Public example configs show the same path-rule defaults.",
        ),
        check_regex(
            "default_preemptive_ports_are_80_and_443",
            config,
            r"fn\s+default_preemptive_ports\(\).*?\{\s*vec!\[80,\s*443\]\s*\}",
            ["crates/tor-circmgr/src/config.rs"],
            "Arti builds web exit circuits early for normal browser traffic.",
        ),
        check_contains_all(
            "example_configs_keep_preemptive_web_ports",
            example_config + "\n" + oldest_config,
            ["#initial_predicted_ports = [80, 443]"],
            [
                "crates/arti/src/arti-example-config.toml",
                "crates/arti/src/oldest-supported-config.toml",
            ],
            "Public example configs keep 80/443 as startup predicted ports.",
        ),
        check_regex(
            "preemptive_min_exit_circs_for_port_is_2",
            config,
            r"fn\s+default_preemptive_min_exit_circs_for_port\(\).*?\{\s*2\s*\}",
            ["crates/tor-circmgr/src/config.rs"],
            "Arti keeps the global preemptive default at two warm exit circuits per predicted web port; the promoted tuning only special-cases port 443.",
        ),
        check_contains_all(
            "example_configs_keep_preemptive_min_exit_circs_2",
            example_config + "\n" + oldest_config,
            ["#min_exit_circs_for_port = 2"],
            [
                "crates/arti/src/arti-example-config.toml",
                "crates/arti/src/oldest-supported-config.toml",
            ],
            "Public example configs keep the safer default preemptive circuit count.",
        ),
        check_contains_all(
            "preemptive_443_override_is_default_on_with_env_off_and_bounded",
            circmgr_preemptive,
            [
                "TORFAST_PREEMPTIVE_443_CIRCS_ENV",
                '\"TORFAST_PREEMPTIVE_443_CIRCS\"',
                "TORFAST_PREEMPTIVE_443_CIRCS_DEFAULT: usize = 3",
                "TORFAST_PREEMPTIVE_443_CIRCS_MIN: usize = 2",
                "TORFAST_PREEMPTIVE_443_CIRCS_MAX: usize = 4",
                "parse_torfast_preemptive_443_circs",
                "torfast_preemptive_443_circs_from_env_value",
                "std::env::var(TORFAST_PREEMPTIVE_443_CIRCS_ENV)",
                ".as_deref()",
                "value.to_ascii_lowercase().as_str()",
                '\"0\" | \"false\" | \"no\" | \"off\"',
                "port.port == 443",
                "unwrap_or(default_circs)",
            ],
            ["crates/tor-circmgr/src/preemptive.rs"],
            "The 443-only preemptive exit boost defaults to three circuits, can be disabled with 0/false/no/off, stays bounded to 2..4, and keeps the normal two-circuit default for other ports.",
        ),
        check_contains_all(
            "preemptive_443_burst_override_is_default_on_with_env_off_and_bounded",
            circmgr_preemptive,
            [
                "TORFAST_PREEMPTIVE_443_BURST_MIN_REQUESTS_ENV",
                '"TORFAST_PREEMPTIVE_443_BURST_MIN_REQUESTS"',
                "TORFAST_PREEMPTIVE_443_BURST_MIN_REQUESTS_MIN: usize = 2",
                "TORFAST_PREEMPTIVE_443_BURST_MIN_REQUESTS_MAX: usize = 32",
                "TORFAST_PREEMPTIVE_443_BURST_MIN_REQUESTS_DEFAULT: usize = 2",
                "TORFAST_PREEMPTIVE_443_BURST_WINDOW_MS: u64 = 2_000",
                "parse_torfast_preemptive_443_burst_min_requests",
                "torfast_preemptive_443_burst_min_requests_from_env_value",
                "std::env::var(TORFAST_PREEMPTIVE_443_BURST_MIN_REQUESTS_ENV)",
                ".as_deref()",
                '\"0\" | \"false\" | \"no\" | \"off\"',
                "recent_443_usages: VecDeque<Instant>",
                "recent_443_usage_count",
                "circs.max(TORFAST_PREEMPTIVE_443_CIRCS_MAX)",
            ],
            ["crates/tor-circmgr/src/preemptive.rs"],
            "The extra 443 burst circuit defaults on at a bounded two recent-requests threshold, can be disabled with 0/false/no/off, only escalates 443 to four circuits after bounded recent demand, and never raises other ports.",
        ),
        check_contains_all(
            "preemptive_443_busy_active_age_is_default_off_and_capped",
            circmgr_mgr + "\n" + circmgr_usage,
            [
                "TORFAST_PREEMPTIVE_443_BUSY_ACTIVE_AGE_MS_ENV",
                '"TORFAST_PREEMPTIVE_443_BUSY_ACTIVE_AGE_MS"',
                "TORFAST_PREEMPTIVE_443_BUSY_ACTIVE_AGE_MIN_MS: u64 = 100",
                "TORFAST_PREEMPTIVE_443_BUSY_ACTIVE_AGE_MAX_MS: u64 = 60_000",
                "TORFAST_PREEMPTIVE_443_BUSY_MIN_ACTIVE_STREAMS: u64 = 2",
                "TORFAST_PREEMPTIVE_443_BUSY_EXTRA_CIRCS_CAP: usize = 1",
                "torfast_preemptive_443_busy_active_after",
                "active_streams_started_at",
                "snapshot.active_streams < TORFAST_PREEMPTIVE_443_BUSY_MIN_ACTIVE_STREAMS",
                "torfast_counts_toward_preemptive_target",
                "torfast_preemptive_target_extra_circs",
                "supported.len() >= circs.saturating_add(extra_cap)",
            ],
            [
                "crates/tor-circmgr/src/mgr.rs",
                "crates/tor-circmgr/src/usage.rs",
            ],
            "Busy 443 circuits only stop counting toward the preemptive pool in explicit lab runs, require at least two active streams past a bounded active-age threshold, and cap themselves to one extra circuit.",
        ),
        check_regex(
            "preemptive_recheck_delay_is_1_second",
            circmgr_lib,
            r"let\s+base_delay\s*=\s*Duration::from_secs\(1\)",
            ["crates/tor-circmgr/src/lib.rs"],
            "Local lab patch rechecks preemptive circuit readiness quickly without changing path rules.",
        ),
        check_contains_all(
            "hspool_missing_netdir_retries_quickly",
            circmgr_hspool,
            [
                "const DELAY: Duration = Duration::from_secs(30)",
                "const NETDIR_RETRY_DELAY: Duration = Duration::from_secs(1)",
                "let mut waiting_for_netdir = false",
                "waiting_for_netdir = true",
                "if waiting_for_netdir && circs_to_launch.n_to_launch() > 0",
                "schedule.fire_in(NETDIR_RETRY_DELAY)",
            ],
            ["crates/tor-circmgr/src/hspool.rs"],
            "HS pool keeps the normal idle delay but retries quickly when its first wakeup happened before netdir was ready.",
        ),
        check_contains_all(
            "hspool_background_start_delay_is_bounded",
            circmgr_hspool,
            [
                "TORFAST_HSPOOL_BACKGROUND_START_DELAY_MS_ENV",
                '"TORFAST_HSPOOL_BACKGROUND_START_DELAY_MS"',
                "TORFAST_HSPOOL_BACKGROUND_START_DELAY_DEFAULT_MS: u64 = 1_000",
                "TORFAST_HSPOOL_BACKGROUND_START_DELAY_MAX_MS: u64 = 60_000",
                "torfast_hspool_background_start_delay()",
                "schedule.fire_in(torfast_hspool_background_start_delay())",
            ],
            ["crates/tor-circmgr/src/hspool.rs"],
            "HS pool startup delay remains bounded, defaults to the current one-second local startup behavior, and only changes through the explicit lab env.",
        ),
        check_contains_all(
            "hspool_background_waits_for_path_sufficient_netdir",
            circmgr_hspool,
            [
                "if !netdir.have_enough_paths()",
                "torfast hspool waiting for path-sufficient netdir",
                "waiting_for_netdir = true",
            ],
            ["crates/tor-circmgr/src/hspool.rs"],
            "HS pool background prebuild waits until the current netdir can support multihop paths before launching hidden-service stem circuits.",
        ),
        check_contains_all(
            "hspool_launch_parallelism_is_bounded_lab_only",
            circmgr_hspool,
            [
                "TORFAST_HSPOOL_LAUNCH_PARALLELISM_ENV",
                '"TORFAST_HSPOOL_LAUNCH_PARALLELISM"',
                "TORFAST_HSPOOL_LAUNCH_PARALLELISM_DEFAULT: usize = 1",
                "TORFAST_HSPOOL_LAUNCH_PARALLELISM_MAX: usize = 4",
                "torfast_hspool_launch_parallelism_from_env_value",
                "torfast_hspool_launch_parallelism()",
                "launch_parallelism == 1",
                "FuturesUnordered",
                "launch_hs_unmanaged_with_timeout_cap::<OwnedChanTarget>",
                "circs_to_launch.note_circ_launch_failed(kind)",
            ],
            ["crates/tor-circmgr/src/hspool.rs"],
            "HS pool background launch parallelism is explicit lab-only, defaults to serial, and keeps the normal HS circuit builder and bounds.",
        ),
        check_contains_all(
            "hspool_on_demand_pool_grace_is_default_off_and_bounded",
            circmgr_hspool,
            [
                "TORFAST_HSPOOL_ON_DEMAND_POOL_GRACE_MS_ENV",
                '"TORFAST_HSPOOL_ON_DEMAND_POOL_GRACE_MS"',
                "TORFAST_HSPOOL_ON_DEMAND_POOL_GRACE_DEFAULT_MS: u64 = 0",
                "TORFAST_HSPOOL_ON_DEMAND_POOL_GRACE_MAX_MS: u64 = 1_000",
                "TORFAST_HSPOOL_ON_DEMAND_POOL_GRACE_POLL_MS: u64 = 25",
                "torfast_hspool_on_demand_pool_grace_from_env_value",
                "torfast_hspool_on_demand_pool_grace()",
                "take_ready_stem_circuit",
                "wait_for_ready_stem_circuit",
                "maybe_extend_stem_circuit",
                "ensure_suitable_circuit",
            ],
            ["crates/tor-circmgr/src/hspool.rs"],
            "HS pool on-demand grace is explicit lab-only, default-off, bounded, and reuses the same ready-stem selection and suitability checks.",
        ),
        check_contains_all(
            "hspool_on_demand_pool_race_is_default_off_and_bounded",
            circmgr_hspool,
            [
                "TORFAST_HSPOOL_ON_DEMAND_POOL_RACE_MS_ENV",
                '"TORFAST_HSPOOL_ON_DEMAND_POOL_RACE_MS"',
                "TORFAST_HSPOOL_ON_DEMAND_POOL_RACE_DEFAULT_MS: u64 = 0",
                "TORFAST_HSPOOL_ON_DEMAND_POOL_RACE_MAX_MS: u64 = 1_000",
                "torfast_hspool_on_demand_pool_race_from_env_value",
                "torfast_hspool_on_demand_pool_race()",
                "race_on_demand_with_ready_stem_circuit",
                "launch_on_demand_stem_circuit",
                "take_ready_stem_circuit",
                "wait_for_ready_stem_circuit",
                "maybe_extend_stem_circuit",
                "ensure_suitable_circuit",
            ],
            ["crates/tor-circmgr/src/hspool.rs"],
            "HS pool on-demand race is explicit lab-only, default-off, bounded, starts the normal on-demand builder immediately, and only reuses pool circuits through the same suitability checks.",
        ),
        check_contains_all(
            "hspool_background_build_timeout_cap_is_default_off_and_bounded",
            circmgr_hspool,
            [
                "TORFAST_HSPOOL_BACKGROUND_BUILD_TIMEOUT_CAP_MS_ENV",
                '"TORFAST_HSPOOL_BACKGROUND_BUILD_TIMEOUT_CAP_MS"',
                "TORFAST_HSPOOL_BACKGROUND_BUILD_TIMEOUT_CAP_MIN_MS: u64 = 500",
                "TORFAST_HSPOOL_BACKGROUND_BUILD_TIMEOUT_CAP_MAX_MS: u64 = 10_000",
                "torfast_hspool_background_build_timeout_cap_from_env_value",
                "torfast_hspool_background_build_timeout_cap()",
                "launch_hs_unmanaged_with_timeout_cap",
            ],
            ["crates/tor-circmgr/src/hspool.rs"],
            "HS pool background build timeout capping is explicit lab-only, default-off, bounded, and scoped to background prebuilds rather than on-demand HS circuits.",
        ),
        check_contains_all(
            "dir_microdesc_bad_health_replacement_can_ignore_score_only_lab_only",
            circmgr_mgr,
            [
                "TORFAST_DIR_MICRODESC_BAD_HEALTH_REPLACEMENT_IGNORE_SCORE_ONLY_ENV",
                '"TORFAST_DIR_MICRODESC_BAD_HEALTH_REPLACEMENT_IGNORE_SCORE_ONLY"',
                "torfast_dir_microdesc_bad_health_replacement_ignore_score_only_from_env_value",
                "torfast_dir_microdesc_bad_health_replacement_ignore_score_only()",
                "torfast_health_is_bad_score_only",
                "score_only_dir_microdesc",
            ],
            ["crates/tor-circmgr/src/mgr.rs"],
            "Dir microdescriptor bad-health replacement can be suppressed for score-only health signals through an explicit default-off lab knob, while keeping replacement for stronger failure signals.",
        ),
        check_contains_all(
            "hspool_client_hsdir_extend_timeout_cap_is_default_off_and_bounded",
            circmgr_hspool,
            [
                "TORFAST_HSPOOL_CLIENT_HSDIR_EXTEND_TIMEOUT_CAP_MS_ENV",
                '"TORFAST_HSPOOL_CLIENT_HSDIR_EXTEND_TIMEOUT_CAP_MS"',
                "TORFAST_HSPOOL_CLIENT_HSDIR_EXTEND_TIMEOUT_CAP_MIN_MS: u64 = 500",
                "TORFAST_HSPOOL_CLIENT_HSDIR_EXTEND_TIMEOUT_CAP_MAX_MS: u64 = 10_000",
                "torfast_hspool_client_hsdir_extend_timeout_cap_from_env_value",
                "torfast_hspool_client_hsdir_extend_timeout_cap()",
                "if kind == HsCircKind::ClientHsDir",
                "extend_timeout_cap",
                "torfast hspool client hsdir extend timeout capped",
            ],
            ["crates/tor-circmgr/src/hspool.rs"],
            "Client HSDir extend timeout capping is explicit lab-only, default-off, bounded, and only shortens the specific HSDir extend phase without changing path selection.",
        ),
        check_contains_all(
            "hspool_guarded_stem_target_is_default_same_and_bounded",
            circmgr_hspool_pool,
            [
                "TORFAST_HSPOOL_GUARDED_STEM_TARGET_ENV",
                '"TORFAST_HSPOOL_GUARDED_STEM_TARGET"',
                "DEFAULT_GUARDED_STEM_TARGET: usize = 2",
                "TORFAST_HSPOOL_GUARDED_STEM_TARGET_MAX: usize = 16",
                "torfast_hspool_guarded_stem_target_from_env_value",
                "torfast_hspool_guarded_stem_target()",
                "guarded_stem_target: torfast_hspool_guarded_stem_target()",
                ".clamp(",
                "torfast_hspool_guarded_stem_target(),",
                "MAX_GUARDED_STEM_TARGET",
            ],
            ["crates/tor-circmgr/src/hspool/pool.rs"],
            "HS pool guarded stem target is explicit lab-only, keeps the normal default of two guarded stems, and bounds startup pool growth.",
        ),
        check_contains_all(
            "hspool_info_timings_split_stem_and_extend_without_targets",
            circmgr_hspool,
            [
                "use tracing::{debug, info, instrument, trace, warn};",
                "torfast hspool timing stem ready",
                "torfast hspool timing stem failed",
                "torfast hspool timing stem selected",
                "torfast hspool timing specific circuit ready",
                "torfast hspool timing specific circuit failed",
                "torfast hspool timing client rend circuit ready",
                "source = \"pool\"",
                "source = \"on_demand\"",
                "extend_ms = extend_started.elapsed().as_millis()",
            ],
            ["crates/tor-circmgr/src/hspool.rs"],
            "HS pool timing rows are retained at info level and split stem selection from final HS extension without logging target names or relay identities.",
        ),
        check_contains_all(
            "hs_intro_rend_overlap_is_default_off_lab_only",
            tor_hsclient_connect,
            [
                "TORFAST_HS_INTRO_REND_OVERLAP_ENV",
                '"TORFAST_HS_INTRO_REND_OVERLAP"',
                "torfast_hs_intro_rend_overlap_from_env_value",
                "torfast_hs_intro_rend_overlap()",
                "saved_rendezvous.is_none()",
                "futures::join!(establish_rendezvous, obtain_intro_circuit)",
                "self.establish_rendezvous()",
                "self.obtain_intro_circuit(ipt, hs_timing_started)",
                "self.exchange_introduce_with_circ",
            ],
            ["crates/tor-hsclient/src/connect.rs"],
            "HS intro/rendezvous overlap is explicit lab-only, default-off, and only overlaps existing HS setup steps without changing path selection.",
        ),
        check_contains_all(
            "hs_rend_prebuild_before_desc_is_default_off_lab_only",
            tor_hsclient_connect,
            [
                "TORFAST_HS_REND_PREBUILD_BEFORE_DESC_ENV",
                '"TORFAST_HS_REND_PREBUILD_BEFORE_DESC"',
                "torfast_hs_rend_prebuild_before_desc_from_env_value",
                "torfast_hs_rend_prebuild_before_desc()",
                "futures::join!(descriptor, rendezvous)",
                "self.establish_rendezvous()",
                "intro_rend_connect(desc, &mut data.ipts, prebuilt_rendezvous)",
                "intro_rend_connect(desc, &mut data.ipts, None)",
            ],
            ["crates/tor-hsclient/src/connect.rs"],
            "HS rendezvous prebuild-before-descriptor is explicit lab-only, default-off, uses the normal rendezvous builder early, and falls back to the normal path.",
        ),
        check_contains_all(
            "hs_desc_shared_cache_is_default_off_descriptor_only",
            tor_hsclient_connect,
            [
                "TORFAST_HS_DESC_SHARED_CACHE_ENV",
                '"TORFAST_HS_DESC_SHARED_CACHE"',
                "torfast_hs_desc_shared_cache_from_env_value",
                "torfast_hs_desc_shared_cache_enabled()",
                "TorfastHsDescSharedCacheKey",
                "hs_blind_id: HsBlindId",
                "Arc::as_ptr(&self.secret_keys.keys)",
                "torfast_hs_desc_shared_cache_get",
                "torfast_hs_desc_shared_cache_store",
                "refetch.is_none()",
                "data.insert(shared_desc)",
                "desc.clone()",
                "desc: DataHsDesc",
                "ipts: DataIpts",
                "hsdirs: DataHsDirs",
                "torfast hs timing descriptor shared cache hit",
                "torfast hs timing descriptor shared cache store",
            ],
            ["crates/tor-hsclient/src/connect.rs"],
            "HS descriptor sharing is explicit lab-only, default-off, keyed by blinded onion and secret-key identity, and copies only the descriptor value.",
        ),
        check_contains_all(
            "hs_intro_circuit_hedge_is_default_off_lab_only",
            tor_hsclient_connect,
            [
                "TORFAST_HS_INTRO_CIRCUIT_HEDGE_MS_ENV",
                '"TORFAST_HS_INTRO_CIRCUIT_HEDGE_MS"',
                "TORFAST_HS_INTRO_CIRCUIT_HEDGE_MIN_MS: u64 = 500",
                "TORFAST_HS_INTRO_CIRCUIT_HEDGE_MAX_MS: u64 = 60_000",
                "torfast_hs_intro_circuit_hedge_ms_from_env_value",
                "torfast_hs_intro_circuit_hedge_delay()",
                "obtain_intro_circuit_with_hedge",
                "torfast hs timing intro circuit hedge launched",
                "torfast hs timing intro circuit hedge won",
                "self.obtain_intro_circuit_once",
                "m_get_or_launch_intro",
            ],
            ["crates/tor-hsclient/src/connect.rs"],
            "HS intro-circuit hedge is explicit lab-only, default-off, bounded, and only races the normal same-target intro circuit acquisition.",
        ),
        check_contains_all(
            "socks_auth_sets_stream_isolation",
            socks_proxy,
            [
                "fn interpret_socks_auth",
                "ProvidedIsolation::LegacySocks(auth.clone())",
                "prefs.set_isolation(StreamIsolationKey(conn_isolation, interp.isolation))",
            ],
            ["crates/arti/src/proxy/socks.rs"],
            "Arti maps SOCKS username/password auth into stream isolation.",
        ),
        check_contains_all(
            "socks_connect_uses_optimistic_streams",
            socks_proxy,
            [
                "SocksCmd::CONNECT",
                "prefs.optimistic()",
                "connect_with_prefs(&tor_addr, &prefs)",
            ],
            ["crates/arti/src/proxy/socks.rs"],
            "Local lab patch uses optimistic streams for SOCKS CONNECT, matching C Tor's optimistic-data behavior.",
        ),
        check_contains_all(
            "socks_connect_soft_timeout_is_bounded_lab_only",
            socks_proxy,
            [
                "TORFAST_SOCKS_CONNECT_SOFT_TIMEOUT_MS",
                "TORFAST_SOCKS_CONNECT_SOFT_TIMEOUT_ATTEMPTS",
                "SOCKS_CONNECT_SOFT_TIMEOUT_MIN_MS: u64 = 500",
                "SOCKS_CONNECT_SOFT_TIMEOUT_MAX_MS: u64 = 60_000",
                "SOCKS_CONNECT_RETRY_ATTEMPTS_DEFAULT: usize = 2",
                "SOCKS_CONNECT_RETRY_ATTEMPTS_MIN: usize = 1",
                "SOCKS_CONNECT_RETRY_ATTEMPTS_MAX: usize = 4",
                "std::env::var(SOCKS_CONNECT_SOFT_TIMEOUT_ENV)",
                "Err(_) => None",
                "std::env::var(SOCKS_CONNECT_SOFT_TIMEOUT_ATTEMPTS_ENV)",
                "if target_kind == \"onion\"",
                "SOCKS_CONNECT_RETRY_ATTEMPTS_DEFAULT",
                "torfast_socks_connect_soft_timeout_attempts()",
                ".timeout(soft_timeout, connect_attempt)",
            ],
            ["crates/arti/src/proxy/socks.rs"],
            "Slow CONNECT soft timeout and retry count are lab-only, bounded, default-off, and not applied to onion streams.",
        ),
        check_contains_all(
            "socks_connect_soft_timeout_final_attempt_waits_normally",
            socks_proxy,
            [
                "let can_retry_after_timeout = attempt < soft_timeout_attempts",
                "(soft_timeout, can_retry_after_timeout)",
                "Some(connect_attempt.await)",
            ],
            ["crates/arti/src/proxy/socks.rs"],
            "Soft CONNECT timeout can start one retry, but the final attempt waits normally instead of causing an early browser failure.",
        ),
        check_contains_all(
            "socks_slow_failure_summaries_are_low_log_parseable",
            socks_proxy,
            [
                "SOCKS_SLOW_CONNECT_LOG_MS: u128 = 1_000",
                "SOCKS_SLOW_RELAY_LOG_MS: u128 = 5_000",
                "if connect_ms >= SOCKS_SLOW_CONNECT_LOG_MS",
                "if relay_ms >= SOCKS_SLOW_RELAY_LOG_MS || !relay_ok",
                "let torfast_stream_key = tor_stream.torfast_debug_stream_key()",
                "circ_id = %torfast_circ_id",
                "stream_id = %torfast_stream_id",
                "info!(",
                "torfast socks timing stream ready",
                "torfast socks timing stream linked",
                "torfast socks timing socks reply sent",
                "torfast socks timing relay finished",
            ],
            ["crates/arti/src/proxy/socks.rs"],
            "Low-log browser gates retain slow or failed SOCKS timing summaries without enabling full debug logs.",
        ),
        check_contains_all(
            "channel_open_timing_is_low_log_parseable",
            circmgr_build,
            [
                "TORFAST_SLOW_CHANNEL_OPEN_LOG_MS: u128 = 1_000",
                "torfast_channel_usage_kind",
                "torfast_channel_provenance_kind",
                "elapsed_ms",
                "usage_kind",
                "provenance",
                "error_kind = ?cause.kind()",
                "torfast channel open timing",
                "if elapsed_ms >= TORFAST_SLOW_CHANNEL_OPEN_LOG_MS",
                "info!(",
            ],
            ["crates/tor-circmgr/src/build.rs"],
            "Channel open timing is parseable in low-log boot proof runs without logging relay identity.",
        ),
        check_contains_all(
            "socks_relay_byte_timing_is_default_off_lab_only",
            socks_proxy,
            [
                "TORFAST_SOCKS_RELAY_BYTE_TIMING",
                "fn torfast_socks_relay_byte_timing() -> bool",
                "std::env::var(SOCKS_RELAY_BYTE_TIMING_ENV)",
                "let low_log_socks_timing = torfast_socks_relay_byte_timing()",
                "connect_ms >= SOCKS_SLOW_CONNECT_LOG_MS || low_log_socks_timing",
                "let collect_relay_byte_timing = tracing::enabled!(tracing::Level::DEBUG)",
                "|| low_log_socks_timing",
                "|| partial_idle_timeout.is_some()",
                "|| no_tor_byte_timeout.is_some()",
                "first_client_to_tor_ms",
                "last_tor_to_client_write_ms",
                "client_to_tor_eof_ms",
                "client_to_tor_write_close_ms",
                "tor_to_client_error_ms",
                "Pin::new(&mut this.inner).poll_fill_buf(cx)",
                "Poll::Ready(Ok(buf)) if buf.is_empty() => timing.note_read_eof()",
                "client_to_tor_write_bytes",
                "tor_to_client_write_bytes",
                "if !tracing::enabled!(tracing::Level::DEBUG)",
                "relay_ms >= SOCKS_SLOW_RELAY_LOG_MS || !relay_ok || low_log_socks_timing",
            ],
            ["crates/arti/src/proxy/socks.rs"],
            "SOCKS relay byte timing is default-off and only expands slow/error low-log diagnostics when explicitly enabled.",
        ),
        check_contains_all(
            "socks_tor_to_client_coalesce_is_default_off_lab_only",
            socks_proxy,
            [
                "TORFAST_SOCKS_TOR_TO_CLIENT_COALESCE_BYTES",
                "fn torfast_socks_tor_to_client_coalesce_bytes() -> Option<usize>",
                "SOCKS_TOR_TO_CLIENT_COALESCE_BYTES_MIN: usize = 498",
                "SOCKS_TOR_TO_CLIENT_COALESCE_BYTES_MAX: usize = 64 * 1024",
                "std::env::var(SOCKS_TOR_TO_CLIENT_COALESCE_BYTES_ENV)",
                "struct ReadyCoalescingReader",
                "let Some(max_bytes) = this.max_bytes else",
                "return Pin::new(&mut this.inner).poll_read(cx, out)",
                "ReadyCoalescingReader::new(b_reader, tor_to_client_coalesce_bytes)",
            ],
            ["crates/arti/src/proxy/socks.rs"],
            "Tor-to-browser local write coalescing is bounded and default-off.",
        ),
        check_contains_all(
            "stream_ready_data_coalesce_is_default_on_bounded_and_offable",
            tor_proto_data_stream + "\n" + tor_proto_stream_raw,
            [
                "TORFAST_STREAM_READY_DATA_COALESCE_BYTES",
                "fn torfast_stream_ready_data_coalesce_bytes() -> Option<usize>",
                "TORFAST_STREAM_READY_DATA_COALESCE_BYTES_DEFAULT: usize = 498",
                "TORFAST_STREAM_READY_DATA_COALESCE_BYTES_MIN: usize = 498",
                "TORFAST_STREAM_READY_DATA_COALESCE_BYTES_MAX: usize = 64 * 1024",
                "TORFAST_STREAM_READY_DATA_COALESCE_START_BACKLOG_BYTES",
                "std::env::var(TORFAST_STREAM_READY_DATA_COALESCE_BYTES_ENV)",
                "Some(TORFAST_STREAM_READY_DATA_COALESCE_BYTES_DEFAULT)",
                "\"0\" | \"off\" | \"false\" | \"no\"",
                "fn torfast_should_ready_coalesce_data(",
                "if let Some(max_bytes) = torfast_stream_ready_data_coalesce_bytes()",
                "let effective_max_bytes = max_bytes.min(buf.len());",
                "while imp.should_ready_coalesce_data(effective_max_bytes)",
                "self.torfast_user_read_bytes > 0",
                "self.s.receiver.approx_stream_bytes()",
                "self.s.next_queued_msg_is_data()",
                "approx_queued_bytes >= TORFAST_STREAM_READY_DATA_COALESCE_START_BACKLOG_BYTES",
                "pub(crate) fn next_queued_msg_is_data(&mut self) -> bool",
                "msg.cmd() == RelayCmd::DATA",
            ],
            [
                "crates/tor-proto/src/client/stream/data.rs",
                "crates/tor-proto/src/stream/raw.rs",
            ],
            "Ready DATA cell coalescing defaults to a bounded 498-byte cap, can be explicitly disabled, and only batches after the first delivered chunk when real queued DATA backlog exists.",
        ),
        check_contains_all(
            "circuit_congestion_log_is_default_off_lab_only",
            tor_proto_reactor_circuit + "\n" + tor_proto_reactor_circuit_circhop,
            [
                "TORFAST_CIRCUIT_CONGESTION_LOG",
                "fn torfast_circuit_congestion_log_enabled() -> bool",
                "std::env::var(TORFAST_CIRCUIT_CONGESTION_LOG_ENV)",
                "if torfast_circuit_congestion_log_enabled()",
                "if super::torfast_circuit_congestion_log_enabled()",
                "torfast circuit congestion sendme sent",
                "torfast circuit congestion sendme received",
                "torfast circuit congestion scheduler hop blocked",
            ],
            [
                "crates/tor-proto/src/client/reactor/circuit.rs",
                "crates/tor-proto/src/client/reactor/circuit/circhop.rs",
            ],
            "Circuit congestion SENDME and scheduler diagnostics are default-off, with no path or flow-control behavior change.",
        ),
        check_contains_all(
            "stream_scheduler_log_is_default_off_lab_only",
            tor_proto_reactor_circuit + "\n" + tor_proto_reactor_circuit_circhop,
            [
                "TORFAST_STREAM_SCHEDULER_LOG",
                "fn torfast_stream_scheduler_log_enabled() -> bool",
                "std::env::var(TORFAST_STREAM_SCHEDULER_LOG_ENV)",
                "if super::torfast_stream_scheduler_log_enabled()",
                "torfast stream scheduler picked",
                "torfast stream scheduler stream closed",
                "torfast stream scheduler hop blocked",
            ],
            [
                "crates/tor-proto/src/client/reactor/circuit.rs",
                "crates/tor-proto/src/client/reactor/circuit/circhop.rs",
            ],
            "Stream scheduler diagnostics are default-off and only raise existing scheduler debug signals to info in lab runs.",
        ),
        check_contains_all(
            "stream_lifecycle_log_is_default_off_lab_only",
            tor_proto_circuit_circhop
            + "\n"
            + tor_proto_reactor_circuit
            + "\n"
            + tor_proto_channel_reactor,
            [
                "TORFAST_STREAM_LIFECYCLE_LOG",
                "fn torfast_stream_lifecycle_log_enabled() -> bool",
                "std::env::var(TORFAST_STREAM_LIFECYCLE_LOG_ENV)",
                "if torfast_stream_lifecycle_log_enabled()",
                "delivery = \"sent\"",
                "delivery = \"channel_queued\"",
                "delivery = \"delivered\"",
                "delivery = \"stream_gone\"",
                "delivery = \"queue_full\"",
                "channel_queue_count_available",
                "channel_queue_after_cells",
                "channel_circ_id",
                "circuit_sender_queue_after_cells",
                "torfast stream lifecycle",
                "channel_reactor_queue_count_available",
                "channel_reactor_queue_after_cells",
                "delivery = \"channel_flushed\"",
                "torfast channel flush",
            ],
            [
                "crates/tor-proto/src/circuit/circhop.rs",
                "crates/tor-proto/src/client/reactor/circuit.rs",
                "crates/tor-proto/src/channel/reactor.rs",
            ],
            "Stream and channel flush diagnostics are default-off, lab-only, and log delivery state without changing behavior.",
        ),
        check_contains_all(
            "socks_partial_relay_idle_timeout_is_bounded_lab_only",
            socks_proxy,
            [
                "TORFAST_SOCKS_PARTIAL_RELAY_IDLE_TIMEOUT_MS",
                "TORFAST_SOCKS_ONION_PARTIAL_RELAY_IDLE_TIMEOUT_MS",
                "SOCKS_PARTIAL_RELAY_IDLE_TIMEOUT_MIN_MS: u64 = 500",
                "SOCKS_PARTIAL_RELAY_IDLE_TIMEOUT_MAX_MS: u64 = 60_000",
                "std::env::var(SOCKS_PARTIAL_RELAY_IDLE_TIMEOUT_ENV)",
                "std::env::var(SOCKS_ONION_PARTIAL_RELAY_IDLE_TIMEOUT_ENV)",
                "torfast_socks_partial_relay_idle_timeout()",
                "torfast_socks_onion_partial_relay_idle_timeout()",
                "torfast_socks_partial_relay_idle_timeout_from_env_value(None)",
                "torfast_socks_onion_partial_relay_idle_timeout_from_env_value(None)",
                "let partial_idle_timeout = if target_kind == \"onion\"",
                "partial_relay_idle_timeout_ms",
                "client_to_tor_eof_ms",
                "client_to_tor_error_ms",
                "tor_to_client_write_error_ms",
                "tor_to_client_write_close_error_ms",
                "tor_to_client_write_bytes",
                "torfast socks timing partial relay idle timeout",
                "std::io::ErrorKind::TimedOut",
                "onion_partial_relay_idle_timeout_is_default_off_and_bounded",
            ],
            ["crates/arti/src/proxy/socks.rs"],
            "Partial-response idle close is default-off, bounded, keeps onion streams default-off unless explicitly enabled, and logs client-abandon evidence for explicit lab tests.",
        ),
        check_contains_all(
            "socks_no_tor_byte_relay_timeout_is_bounded_lab_only",
            socks_proxy,
            [
                "TORFAST_SOCKS_NO_TOR_BYTE_RELAY_TIMEOUT_MS",
                "SOCKS_NO_TOR_BYTE_RELAY_TIMEOUT_MIN_MS: u64 = 500",
                "SOCKS_NO_TOR_BYTE_RELAY_TIMEOUT_MAX_MS: u64 = 60_000",
                "std::env::var(SOCKS_NO_TOR_BYTE_RELAY_TIMEOUT_ENV)",
                "torfast_socks_no_tor_byte_relay_timeout()",
                "target_kind == \"onion\"",
                "tor_to_client_timing.bytes() == 0",
                "client_to_tor_timing.first_byte_elapsed_ms_or_zero()",
                "no_tor_byte_relay_timeout_ms",
                "client_to_tor_eof_ms",
                "client_to_tor_error_ms",
                "tor_to_client_write_error_ms",
                "tor_to_client_write_close_error_ms",
                "tor_to_client_write_bytes",
                "torfast socks timing no tor byte relay timeout",
                "std::io::ErrorKind::TimedOut",
            ],
            ["crates/arti/src/proxy/socks.rs"],
            "No-Tor-byte relay close is default-off, bounded, skips onion streams, only fires after client bytes are sent, and logs client-abandon evidence.",
        ),
        check_contains_all(
            "exit_bad_health_replacement_is_default_on_with_live_pressure_gate",
            circmgr_mgr,
            [
                "TORFAST_EXIT_BAD_HEALTH_REPLACEMENT",
                "TORFAST_EXIT_BAD_HEALTH_REPLACEMENT_MIN_ACTIVE_STREAMS",
                "fn torfast_exit_bad_health_replacement_from_env_value(value: Option<&str>) -> bool",
                "fn torfast_exit_bad_health_replacement_enabled() -> bool",
                "std::env::var(TORFAST_EXIT_BAD_HEALTH_REPLACEMENT_ENV)",
                "torfast_env_flag(value.map(str::to_owned), true)",
                "fn torfast_bad_health_replacement_is_enabled_with_exit_flag(",
                "selected_active_streams",
                "TargetTunnelUsage::Exit { .. } => {",
                ">= TORFAST_EXIT_BAD_HEALTH_REPLACEMENT_MIN_ACTIVE_STREAMS",
                "TargetTunnelUsage::DirMicrodesc =>",
                "_ => false",
                "bad_health_replacement_is_dir_microdesc_safe_and_exit_needs_live_pressure",
            ],
            ["crates/tor-circmgr/src/mgr.rs"],
            "Exit bad-health replacement is default-on only under live exit pressure, while microdescriptor bad-health replacement keeps its separate safe gating.",
        ),
        check_contains_all(
            "exit_client_phase_timing_is_low_log_parseable",
            arti_client,
            [
                "torfast exit client timing tunnel ready",
                "torfast exit client timing begin stream finished",
                "if tunnel_elapsed_ms >= 1000 {\n                    info!(",
                "} else if begin_elapsed_ms >= 1000 {\n                    info!(",
                "tunnel_unique_id = %tunnel_unique_id",
                "tunnel_elapsed_ms",
                "begin_phase_ms",
            ],
            ["crates/arti-client/src/client.rs"],
            "Exit CONNECT logs split slow/failure timing between tunnel acquisition and BEGIN completion.",
        ),
        check_contains_all(
            "hs_client_phase_timing_is_low_log_parseable",
            arti_client,
            [
                "torfast hs client timing tunnel ready",
                "torfast hs client timing begin stream finished",
                "if tunnel_elapsed_ms >= 1000 {\n                    info!(",
                "if stream.is_err() || begin_elapsed_ms >= 1000 {\n                    info!(",
                "tunnel_elapsed_ms",
                "begin_phase_ms",
            ],
            ["crates/arti-client/src/client.rs"],
            "Onion-service CONNECT logs split slow/failure timing between HS tunnel acquisition and BEGIN completion.",
        ),
        check_contains_all(
            "slow_tunnel_build_completion_is_low_log_parseable",
            circmgr_mgr,
            [
                "TORFAST_SLOW_TUNNEL_BUILD_LOG_MS: u128 = 5_000",
                "pending_age_ms >= TORFAST_SLOW_TUNNEL_BUILD_LOG_MS",
                "torfast circuit selection build complete",
                "torfast circuit selection build failed",
                "torfast circuit selection build canceled",
                "info!(",
                "usage_kind",
                "tunnel_unique_id = %tunnel_unique_id",
            ],
            ["crates/tor-circmgr/src/mgr.rs"],
            "Slow tunnel build completion, failure, and cancellation stay visible in low-log proof runs.",
        ),
        check_contains_all(
            "post_last_byte_diagnostics_are_parseable",
            socks_proxy + "\n" + tor_proto_data_stream,
            [
                "copy_error_kind = %torfast_io_error_kind",
                "copy_error = %torfast_io_error_token",
                "TORFAST_STREAM_SLOW_TRANSFER_LOG_MS: u128 = 5_000",
                "transfer_ms >= TORFAST_STREAM_SLOW_TRANSFER_LOG_MS || !returned_eof",
                "info!(",
                "torfast stream receiver terminal",
                "torfast stream receiver terminal summary",
                "first_data_after_start_ms",
                "transfer_ms",
                "idle_after_last_data_ms",
                "max_data_gap_ms",
                "relay_data_bytes",
                "user_read_bytes = self.torfast_user_read_bytes",
                "data_cells = self.torfast_data_cells",
                "error_kind = %torfast_reader_error_kind(error)",
                "returned_eof",
            ],
            [
                "crates/arti/src/proxy/socks.rs",
                "crates/tor-proto/src/client/stream/data.rs",
            ],
            "Debug logs expose SOCKS copy errors, and low-log slow/error reader summaries expose post-last-byte tail diagnosis.",
        ),
        check_contains_all(
            "exit_stream_select_parallelism_has_bounded_lab_override",
            circmgr_impls,
            [
                "TORFAST_DEFAULT_EXIT_SELECT_PARALLELISM: usize = 1",
                "TORFAST_EXIT_SELECT_PARALLELISM_ENV",
                "(1..=8).contains(value)",
                "fn select_parallelism",
                "TargetTunnelUsage::Exit { .. } => torfast_exit_select_parallelism()",
                "_ => self.launch_parallelism(spec)",
            ],
            ["crates/tor-circmgr/src/impls.rs"],
            "Local lab patch keeps normal exit selection at width 1 by default and provides a bounded env override for A/B tests.",
        ),
        check_contains_all(
            "exit_stream_launch_parallelism_has_bounded_lab_override",
            circmgr_impls,
            [
                "TORFAST_DEFAULT_EXIT_LAUNCH_PARALLELISM: usize = 1",
                "TORFAST_EXIT_LAUNCH_PARALLELISM_ENV",
                "(1..=4).contains(value)",
                "fn launch_parallelism",
                "TargetTunnelUsage::Exit { .. } => torfast_exit_launch_parallelism()",
                "_ => 1",
            ],
            ["crates/tor-circmgr/src/impls.rs"],
            "Local lab patch keeps normal exit launches at width 1 by default and provides a bounded env override for A/B tests.",
        ),
        check_contains_all(
            "exit_pending_hedge_is_bounded_lab_only",
            circmgr_mgr,
            [
                "TORFAST_EXIT_PENDING_HEDGE_MS",
                "TORFAST_EXIT_PENDING_HEDGE_MIN_MS: u64 = 500",
                "TORFAST_EXIT_PENDING_HEDGE_MAX_MS: u64 = 60_000",
                "TORFAST_EXIT_PENDING_HEDGE_MAX_PENDING: usize = 2",
                "std::env::var(TORFAST_EXIT_PENDING_HEDGE_ENV)",
                "TargetTunnelUsage::Exit { .. } => torfast_exit_pending_hedge_after()",
                "pending_hedge_delay",
                "torfast circuit selection pending hedge timer fired",
                "torfast circuit selection build hedge timer fired",
                "torfast circuit selection pending hedge",
            ],
            ["crates/tor-circmgr/src/mgr.rs"],
            "Exit pending hedge is lab-only, bounded, default-off, and limited to exit circuits.",
        ),
        check_regex(
            "exit_pending_hedge_actual_events_are_low_log_parseable",
            circmgr_mgr,
            (
                r"info!\(\s*pending_candidates,.*?"
                r'"torfast circuit selection pending hedge".*?'
                r"info!\(\s*pending_candidates,.*?"
                r'"torfast circuit selection pending hedge failed".*?'
                r"info!\(\s*delay_ms = delay\.as_millis\(\),.*?"
                r'"torfast circuit selection pending hedge timer fired"'
            ),
            ["crates/tor-circmgr/src/mgr.rs"],
            "Actual pending-hedge launch, failure, and timer-fire events are visible in info-level lab runs.",
        ),
        check_regex(
            "exit_build_hedge_actual_events_are_low_log_parseable",
            circmgr_mgr,
            (
                r"info!\(\s*delay_ms = delay\.as_millis\(\),.*?"
                r'"torfast circuit selection build hedge timer fired".*?'
                r"info!\(\s*delay_ms = delay\.as_millis\(\),.*?"
                r"plans = plans\.len\(\),.*?"
                r'"torfast circuit selection build hedge"'
            ),
            ["crates/tor-circmgr/src/mgr.rs"],
            "Actual build-hedge timer-fire and launch events are visible in info-level lab runs.",
        ),
        check_contains_all(
            "exit_select_load_aware_is_default_off_lab_only",
            circmgr_mgr,
            [
                "TORFAST_EXIT_SELECT_LOAD_AWARE",
                "TORFAST_EXIT_SELECT_MIN_ASSIGNMENT_SPREAD",
                "TORFAST_EXIT_SELECT_MIN_ASSIGNMENT_SPREAD_MAX: u64 = 8",
                "unwrap_or(false)",
                "unwrap_or(0)",
                "TargetTunnelUsage::Exit { .. }",
                "assigned_streams",
                "least_assigned_index",
                "load_aware_selected_index",
                "least_assigned_index_with_min_spread",
                "assignment_spread",
                "load_aware_min_assignment_spread",
                "load_aware_assignment_candidate_index",
                "candidate_assignment_summary",
                "selected_candidate_index",
                "open_support_summary",
                "torfast_support_reason",
            ],
            ["crates/tor-circmgr/src/mgr.rs"],
            "Load-aware exit selection is lab-only, default-off, and only chooses among already eligible exit circuits.",
        ),
        check_contains_all(
            "exit_select_least_assigned_is_default_off_lab_only",
            circmgr_mgr,
            [
                "TORFAST_EXIT_SELECT_LEAST_ASSIGNED",
                "fn torfast_exit_select_least_assigned() -> bool",
                "fn torfast_exit_select_least_assigned_is_enabled(usage: &TargetTunnelUsage) -> bool",
                "TargetTunnelUsage::Exit { .. }",
                "least_assigned_parallelism_index",
                "find_best_index_before_active_cap",
                "select_least_assigned",
            ],
            ["crates/tor-circmgr/src/mgr.rs"],
            "Least-assigned exit selection is lab-only, default-off, and only reorders already eligible open exit circuits.",
        ),
        check_regex(
            "exit_select_load_aware_helper_defaults_off",
            circmgr_mgr,
            (
                r"fn\s+torfast_exit_select_load_aware\(\)\s*->\s*bool\s*\{.*?"
                r"TORFAST_EXIT_SELECT_LOAD_AWARE_ENV.*?"
                r"torfast_env_flag\(.*?,\s*false\s*\)"
            ),
            ["crates/tor-circmgr/src/mgr.rs"],
            "The load-aware exit selector remains opt-in unless the lab env is explicitly enabled.",
        ),
        check_regex(
            "exit_select_least_assigned_helper_defaults_off",
            circmgr_mgr,
            (
                r"fn\s+torfast_exit_select_least_assigned\(\)\s*->\s*bool\s*\{.*?"
                r"TORFAST_EXIT_SELECT_LEAST_ASSIGNED_ENV.*?"
                r"torfast_env_flag\(.*?,\s*false\s*\)"
            ),
            ["crates/tor-circmgr/src/mgr.rs"],
            "The least-assigned exit selector remains opt-in unless the lab env is explicitly enabled.",
        ),
        check_regex(
            "exit_select_health_aware_helper_defaults_off",
            circmgr_mgr,
            (
                r"fn\s+torfast_exit_select_health_aware\(\)\s*->\s*bool\s*\{.*?"
                r"TORFAST_EXIT_SELECT_HEALTH_AWARE_ENV.*?"
                r"torfast_env_flag\(.*?,\s*false\s*\)"
            ),
            ["crates/tor-circmgr/src/mgr.rs"],
            "The health-aware selector stays lab-only and off by default.",
        ),
        check_contains_all(
            "health_aware_min_assigned_is_default_off_lab_only",
            circmgr_mgr,
            [
                "TORFAST_EXIT_SELECT_HEALTH_AWARE_MIN_ASSIGNED",
                "TORFAST_EXIT_SELECT_HEALTH_AWARE_MIN_ASSIGNED_MIN: u64 = 1",
                "TORFAST_EXIT_SELECT_HEALTH_AWARE_MIN_ASSIGNED_MAX: u64 = 32",
                "fn torfast_exit_select_health_aware_min_assigned",
                "torfast_exit_select_health_aware_is_enabled(usage)",
                "std::env::var(TORFAST_EXIT_SELECT_HEALTH_AWARE_MIN_ASSIGNED_ENV)",
                "health_aware_min_assigned",
                "ents[assigned_selected].assigned_streams < min_assigned",
                "select_health_aware_min_assigned",
            ],
            ["crates/tor-circmgr/src/mgr.rs"],
            "Health-aware min-assigned gating is bounded, default-off, health-aware-only, and only lets health-aware override assignment after local assignment pressure.",
        ),
        check_regex(
            "exit_select_avoid_bad_health_helper_defaults_off",
            circmgr_mgr,
            (
                r"fn\s+torfast_exit_select_avoid_bad_health\(\)\s*->\s*bool\s*\{.*?"
                r"TORFAST_EXIT_SELECT_AVOID_BAD_HEALTH_ENV.*?"
                r"torfast_env_flag\(.*?,\s*false\s*\)"
            ),
            ["crates/tor-circmgr/src/mgr.rs"],
            "Bad-health avoidance stays lab-only and off by default.",
        ),
        check_contains_all(
            "dir_select_spread_is_default_off_lab_only",
            circmgr_mgr,
            [
                "TORFAST_DIR_SELECT_SPREAD",
                "fn torfast_dir_select_spread_is_enabled(usage: &TargetTunnelUsage) -> bool",
                "TargetTunnelUsage::Dir => std::env::var(TORFAST_DIR_SELECT_SPREAD_ENV)",
                "std::env::var(TORFAST_DIR_SELECT_SPREAD_ENV)",
                'value == "1"',
                "let select_dir_spread = torfast_dir_select_spread_is_enabled(usage)",
                "if select_dir_spread",
                "OpenEntry::least_assigned_index(&open)",
                "|| torfast_dir_select_spread_is_enabled(usage)",
            ],
            ["crates/tor-circmgr/src/mgr.rs"],
            "Directory circuit spreading is default-off, Dir-only, and only chooses among already eligible open directory circuits.",
        ),
        check_contains_all(
            "dir_microdesc_source_spread_is_default_microdesc_only_safe",
            tor_dirclient + "\n" + circmgr_lib + "\n" + circmgr_mgr + "\n" + circmgr_usage,
            [
                "fn dirclient_microdesc_source_spread_enabled() -> bool",
                "true",
                'request_kind == Some("microdesc")',
                "circ_mgr.get_or_launch_dir_microdesc(dirinfo).await?",
                "TargetTunnelUsage::DirMicrodesc",
                "same path and eligibility rules as",
                "TargetTunnelUsage::Dir | TargetTunnelUsage::DirMicrodesc",
                "SupportedTunnelUsage::Dir",
                "OpenEntry::least_assigned_index(&open)",
            ],
            [
                "crates/tor-dirclient/src/lib.rs",
                "crates/tor-circmgr/src/lib.rs",
                "crates/tor-circmgr/src/mgr.rs",
                "crates/tor-circmgr/src/usage.rs",
            ],
            "Microdescriptor source spread is enabled by default, request-kind gated, and reuses the normal directory path and eligibility rules through the dedicated DirMicrodesc usage.",
        ),
        check_contains_all(
            "dir_microdesc_pending_spread_is_default_microdesc_only_safe",
            circmgr_mgr,
            [
                "fn torfast_dir_microdesc_pending_spread_is_enabled(usage: &TargetTunnelUsage) -> bool",
                "matches!(usage, TargetTunnelUsage::DirMicrodesc)",
                "torfast_should_skip_assigned_dir_microdesc",
                "entry.assigned_streams > 0",
                "torfast_has_unassigned_open_alternate",
                "torfast_pending_supported_count(usage) > 0",
                "skipped_assigned_dir_microdesc",
                "torfast dir microdesc pending spread used fallback tunnel",
            ],
            ["crates/tor-circmgr/src/mgr.rs"],
            "Microdescriptor pending spread is enabled by default, DirMicrodesc-only, prefers unused eligible directory circuits first, and keeps a fallback to the skipped circuit.",
        ),
        check_contains_all(
            "dir_microdesc_spare_topup_is_default_microdesc_only_safe",
            circmgr_mgr,
            [
                "TORFAST_DIR_MICRODESC_SPARE_TARGET: usize = 3",
                "fn torfast_should_top_up_dir_microdesc_spare(",
                "matches!(usage, TargetTunnelUsage::DirMicrodesc)",
                "pending_supported_count == 0",
                "!has_unassigned_open_alternate",
                "open_candidates < TORFAST_DIR_MICRODESC_SPARE_TARGET",
                "torfast_has_unassigned_open_alternate(usage, &selected_tunnel_id)",
                "torfast dir microdesc spare topup",
                "dir_microdesc_spare_topup_is_microdesc_only_and_bounded",
            ],
            ["crates/tor-circmgr/src/mgr.rs"],
            "Microdescriptor spare topup is enabled by default, DirMicrodesc-only, bounded to a small spare target, and only launches when no unused eligible or pending microdescriptor directory circuit remains.",
        ),
        check_contains_all(
            "dir_incremental_microdescs_is_default_off_lab_only",
            dirmgr_bootstrap,
            [
                "TORFAST_DIR_INCREMENTAL_MICRODESCS",
                "fn torfast_dir_incremental_microdescs_enabled(missing: &[DocId]) -> bool",
                "matches!(doc, DocId::Microdesc(_))",
                "std::env::var(TORFAST_DIR_INCREMENTAL_MICRODESCS_ENV)",
                'value == "1"',
                "download_attempt_incremental_microdescs",
                "state.is_ready(Readiness::Usable)",
                "torfast incremental microdescriptor fetch reached usable directory",
            ],
            ["crates/tor-dirmgr/src/bootstrap.rs"],
            "Incremental microdescriptor bootstrap is default-off, microdescriptor-only, and returns early only after the directory is usable.",
        ),
        check_contains_all(
            "dir_microdesc_early_usable_notify_is_default_microdesc_only_safe",
            dirmgr_bootstrap,
            [
                "fn torfast_dir_microdesc_early_usable_notify_enabled(missing: &[DocId]) -> bool",
                "torfast_missing_docs_are_microdescs(missing)",
                "download_attempt_microdescs_early_usable_notify",
                "notify_usable_if_ready",
                "state.is_ready(Readiness::Usable)",
                "torfast microdescriptor early usable notification",
                "while let Some(response) = responses.next().await",
            ],
            ["crates/tor-dirmgr/src/bootstrap.rs"],
            "Microdescriptor early usable notification is enabled by default for microdescriptors, uses the existing safe usability threshold, and keeps collecting responses after notifying.",
        ),
        check_contains_all(
            "dir_microdesc_hedge_is_default_on_bounded_and_offable",
            dirmgr_bootstrap,
            [
                "TORFAST_DIR_MICRODESC_HEDGE_MS",
                "TORFAST_DIR_MICRODESC_HEDGE_DEFAULT_MS: u64 = 2_000",
                "MIN_MICRODESC_HEDGE_MS: u64 = 2_000",
                "MAX_MICRODESC_HEDGE_MS: u64 = 10_000",
                "fn torfast_microdesc_hedge_delay_from_env_value(value: Option<&str>) -> Option<Duration>",
                "fn torfast_microdesc_hedge_delay(request: &ClientRequest) -> Option<Duration>",
                "matches!(request, ClientRequest::Microdescs(_))",
                "std::env::var(TORFAST_DIR_MICRODESC_HEDGE_MS_ENV)",
                "(MIN_MICRODESC_HEDGE_MS..=MAX_MICRODESC_HEDGE_MS)",
                "Some(Duration::from_millis(TORFAST_DIR_MICRODESC_HEDGE_DEFAULT_MS))",
                "\"0\" | \"off\" | \"false\" | \"no\"",
                "fetch_single_maybe_hedged",
                "torfast microdescriptor hedge started",
                "dir_fetch_outcome_is_clean",
            ],
            ["crates/tor-dirmgr/src/bootstrap.rs"],
            "Microdescriptor hedge is bounded, default-on at 2000ms, explicitly offable, microdescriptor-only, and keeps validation unchanged.",
        ),
        check_contains_all(
            "dir_microdesc_chunk_size_is_bounded_lab_only",
            dirmgr_docid,
            [
                "TORFAST_DIR_MICRODESC_IDS_PER_REQUEST",
                "DEFAULT_DOCS_PER_REQUEST: usize = 500",
                "MIN_MICRODESC_IDS_PER_REQUEST: usize = 64",
                "MAX_MICRODESC_IDS_PER_REQUEST: usize = DEFAULT_DOCS_PER_REQUEST",
                "fn torfast_microdesc_ids_per_request() -> usize",
                "std::env::var(TORFAST_DIR_MICRODESC_IDS_PER_REQUEST_ENV)",
                "bounded_microdesc_ids_per_request",
                "(MIN_MICRODESC_IDS_PER_REQUEST..=MAX_MICRODESC_IDS_PER_REQUEST)",
                "unwrap_or(DEFAULT_DOCS_PER_REQUEST)",
                "unwrap_or_else(torfast_microdesc_ids_per_request)",
            ],
            ["crates/tor-dirmgr/src/docid.rs"],
            "Microdescriptor request chunk size is bounded, default-off, and only changes microdescriptor request grouping.",
        ),
        check_contains_all(
            "dir_microdesc_retry_chunk_size_is_default_on_bounded_retry_only_safe",
            dirmgr_bootstrap + "\n" + dirmgr_docid,
            [
                "TORFAST_DIR_MICRODESC_RETRY_IDS_PER_REQUEST",
                "TORFAST_DIR_MICRODESC_RETRY_IDS_PER_REQUEST_DEFAULT: usize = 250",
                "MIN_MICRODESC_RETRY_IDS_PER_REQUEST: usize = 64",
                "MAX_MICRODESC_RETRY_IDS_PER_REQUEST: usize = 500",
                "fn parse_torfast_microdesc_retry_ids_per_request(value: Option<&str>) -> Option<usize>",
                "fn torfast_microdesc_retry_ids_per_request_from_env_value(value: Option<&str>) -> Option<usize>",
                "fn torfast_microdesc_retry_ids_per_request() -> Option<usize>",
                "std::env::var(TORFAST_DIR_MICRODESC_RETRY_IDS_PER_REQUEST_ENV)",
                "(MIN_MICRODESC_RETRY_IDS_PER_REQUEST..=MAX_MICRODESC_RETRY_IDS_PER_REQUEST)",
                "\"0\" | \"off\" | \"false\" | \"no\"",
                "retry_microdesc_chunking_allowed",
                "should_enable_microdesc_retry_chunking",
                "download_error_count",
                "torfast_missing_docs_are_microdescs(&missing)",
                "split_for_download_with_microdesc_limit",
                "torfast microdescriptor retry request chunking enabled",
            ],
            [
                "crates/tor-dirmgr/src/bootstrap.rs",
                "crates/tor-dirmgr/src/docid.rs",
            ],
            "Retry microdescriptor request chunk size is bounded, default-on at 250 IDs, explicitly offable, retry-only after a real download error, microdescriptor-only, and keeps normal document validation.",
        ),
        check_contains_all(
            "dir_microdesc_retry_delay_is_default_on_bounded_retry_only_safe",
            dirmgr_bootstrap,
            [
                "TORFAST_DIR_MICRODESC_RETRY_DELAY_MAX_MS",
                "TORFAST_DIR_MICRODESC_RETRY_DELAY_MAX_DEFAULT_MS: u64 = 500",
                "MIN_MICRODESC_RETRY_DELAY_MAX_MS: u64 = 250",
                "MAX_MICRODESC_RETRY_DELAY_MAX_MS: u64 = 2_000",
                "fn parse_torfast_microdesc_retry_delay_max_ms(value: Option<&str>) -> Option<Duration>",
                "fn torfast_microdesc_retry_delay_max_from_env_value(value: Option<&str>) -> Option<Duration>",
                "fn torfast_microdesc_retry_delay_max() -> Option<Duration>",
                "std::env::var(TORFAST_DIR_MICRODESC_RETRY_DELAY_MAX_MS_ENV)",
                "(MIN_MICRODESC_RETRY_DELAY_MAX_MS..=MAX_MICRODESC_RETRY_DELAY_MAX_MS)",
                "\"0\" | \"off\" | \"false\" | \"no\"",
                "retry_microdesc_chunking_allowed",
                "torfast_missing_docs_are_microdescs(&state.missing_docs())",
                "torfast_microdesc_retry_delay_max()",
                "real_delay = real_delay.min(max_delay)",
                "torfast microdescriptor retry delay capped",
            ],
            ["crates/tor-dirmgr/src/bootstrap.rs"],
            "Retry delay cap is bounded, default-on at 500ms, explicitly offable, retry-only after a real microdescriptor download error, and keeps normal document validation.",
        ),
        check_contains_all(
            "dir_microdesc_early_retry_on_partial_is_default_off_lab_only",
            dirmgr_bootstrap,
            [
                "TORFAST_DIR_MICRODESC_EARLY_RETRY_ON_PARTIAL",
                "fn torfast_microdesc_early_retry_on_partial_enabled(missing: &[DocId]) -> bool",
                "torfast_missing_docs_are_microdescs(missing)",
                "std::env::var(TORFAST_DIR_MICRODESC_EARLY_RETRY_ON_PARTIAL_ENV)",
                'value == "1"',
                "torfast_microdesc_early_retry_on_partial_enabled(missing)",
                "response.error().is_some()",
                "torfast microdescriptor early retry on partial",
            ],
            ["crates/tor-dirmgr/src/bootstrap.rs"],
            "Microdescriptor early retry on partial is default-off, microdescriptor-only, and only cuts off a batch after a partial response.",
        ),
        check_contains_all(
            "dir_microdesc_partial_retry_chunking_is_default_on_retry_only_offable",
            dirmgr_bootstrap,
            [
                "TORFAST_DIR_MICRODESC_PARTIAL_RETRY_CHUNKING",
                "fn torfast_microdesc_partial_retry_chunking_enabled(missing: &[DocId]) -> bool",
                "fn torfast_microdesc_partial_retry_chunking_from_env_value(value: Option<&str>) -> bool",
                "torfast_missing_docs_are_microdescs(missing)",
                "std::env::var(TORFAST_DIR_MICRODESC_PARTIAL_RETRY_CHUNKING_ENV)",
                "\"0\" | \"off\" | \"false\" | \"no\"",
                "torfast_microdesc_partial_retry_chunking_signal",
                "response.error().is_some()",
                "download_error_count += 1",
                "n_errors += 1",
                "torfast microdescriptor partial retry chunking signal",
                "while let Some(response) = responses.next().await",
                "useful_responses.push((request, response))",
            ],
            ["crates/tor-dirmgr/src/bootstrap.rs"],
            "Microdescriptor partial retry chunking is default-on, explicitly offable, microdescriptor-only, keeps the current batch, and only changes later retry shape after a partial response.",
        ),
        check_contains_all(
            "dirclient_read_timeout_is_bounded_lab_only",
            tor_dirclient,
            [
                "TORFAST_DIRCLIENT_READ_TIMEOUT_MS",
                "DEFAULT_DIRCLIENT_READ_TIMEOUT: Duration = Duration::from_secs(10)",
                "MIN_DIRCLIENT_READ_TIMEOUT_MS: u64 = 2_000",
                "MAX_DIRCLIENT_READ_TIMEOUT_MS: u64 = 10_000",
                "fn dirclient_read_timeout() -> Duration",
                "std::env::var(TORFAST_DIRCLIENT_READ_TIMEOUT_ENV)",
                "(MIN_DIRCLIENT_READ_TIMEOUT_MS..=MAX_DIRCLIENT_READ_TIMEOUT_MS)",
                "unwrap_or(DEFAULT_DIRCLIENT_READ_TIMEOUT)",
                "let read_timeout = dirclient_read_timeout()",
            ],
            ["crates/tor-dirclient/src/lib.rs"],
            "Directory read timeout override is bounded, default-off, and keeps the normal 10s timeout when unset.",
        ),
        check_contains_all(
            "dirclient_progress_read_timeout_is_bounded_lab_only",
            tor_dirclient,
            [
                "TORFAST_DIRCLIENT_PROGRESS_READ_TIMEOUT_MS",
                "fn dirclient_progress_read_timeout() -> Option<Duration>",
                "std::env::var(TORFAST_DIRCLIENT_PROGRESS_READ_TIMEOUT_ENV)",
                "(MIN_DIRCLIENT_READ_TIMEOUT_MS..=MAX_DIRCLIENT_READ_TIMEOUT_MS)",
                ".map(Duration::from_millis)",
                "let progress_read_timeout = dirclient_progress_read_timeout()",
                "let body_start = Instant::now()",
                "let mut read_deadline = if let Some(progress_read_timeout) = progress_read_timeout",
                "runtime.timeout(read_deadline, stream.read(buf))",
            ],
            ["crates/tor-dirclient/src/lib.rs"],
            "Directory progress read timeout is bounded, default-off, and only changes body-read timeout behavior when enabled.",
        ),
        check_contains_all(
            "dirclient_microdesc_body_max_is_bounded_lab_only",
            tor_dirclient,
            [
                "TORFAST_DIRCLIENT_MICRODESC_BODY_MAX_MS",
                "fn dirclient_microdesc_body_max() -> Option<Duration>",
                "std::env::var(TORFAST_DIRCLIENT_MICRODESC_BODY_MAX_ENV)",
                "(MIN_DIRCLIENT_READ_TIMEOUT_MS..=MAX_DIRCLIENT_READ_TIMEOUT_MS)",
                "let microdesc_body_max = if request_kind == \"microdesc\" && partial_ok",
                "dirclient_microdesc_body_max()",
                "microdesc_body_max.checked_sub(body_start.elapsed())",
                "read_deadline = read_deadline.min(remaining)",
            ],
            ["crates/tor-dirclient/src/lib.rs"],
            "Microdescriptor body max is bounded, default-off, microdescriptor-only, and only applies where partial directory bodies are already allowed.",
        ),
        check_contains_all(
            "dirclient_microdesc_min_rate_is_bounded_lab_only",
            tor_dirclient,
            [
                "TORFAST_DIRCLIENT_MICRODESC_MIN_RATE_BPS",
                "const MIN_MICRODESC_MIN_RATE_BPS: u64 = 32 * 1024",
                "const MAX_MICRODESC_MIN_RATE_BPS: u64 = 256 * 1024",
                "const MICRODESC_MIN_RATE_AFTER: Duration = Duration::from_secs(7)",
                "fn dirclient_microdesc_min_rate_bps() -> Option<u64>",
                "std::env::var(TORFAST_DIRCLIENT_MICRODESC_MIN_RATE_ENV)",
                "(MIN_MICRODESC_MIN_RATE_BPS..=MAX_MICRODESC_MIN_RATE_BPS)",
                "let microdesc_min_rate_bps = if request_kind == \"microdesc\" && partial_ok",
                "dirclient_microdesc_min_rate_bps()",
                "let elapsed = body_start.elapsed()",
                "elapsed >= MICRODESC_MIN_RATE_AFTER",
                "rate_bps < u128::from(min_rate_bps)",
                "microdesc_min_rate_bps",
                "body_avg_rate_bps",
            ],
            ["crates/tor-dirclient/src/lib.rs"],
            "Microdescriptor minimum body rate is bounded, default-off, microdescriptor-only, and checked only after the lab grace window.",
        ),
        check_contains_all(
            "dirclient_timing_log_is_default_off_lab_only",
            tor_dirclient,
            [
                "TORFAST_DIRCLIENT_TIMING_LOG",
                "fn dirclient_timing_log_enabled() -> bool",
                "std::env::var(TORFAST_DIRCLIENT_TIMING_LOG_ENV)",
                'value == "1"',
                "fn log_dirclient_timing(",
                "if !enabled",
                "DirclientBodyTiming",
                "body_read_calls",
                "body_first_byte_ms",
                "body_last_byte_ms",
                "body_max_read_gap_ms",
                "body_timeout_after_last_byte_ms",
                "microdesc_body_max_ms",
                "microdesc_min_rate_bps",
                "microdesc_min_rate_after_ms",
                "body_avg_rate_bps",
                "body_eof",
                "source_circ",
                "source.unique_circ_id().to_string()",
                ".replace(' ', \"~\")",
                "timing_start: Instant",
                "timing.note_timeout(timing_start)",
                "timing.note_read(timing_start, written_in_this_loop)",
                "torfast dirclient timing",
                "fn dirclient_request_kind(path: &str) -> &'static str",
            ],
            ["crates/tor-dirclient/src/lib.rs"],
            "Directory client timing logs are default-off, env-gated, and classify request paths without logging full URLs.",
        ),
        check_contains_all(
            "circuit_health_signal_is_available_for_lab_selector",
            tor_proto_client
            + "\n"
            + tor_proto_circuit
            + "\n"
            + tor_proto_reactor_circuit
            + "\n"
            + circmgr_mgr
            + "\n"
            + circmgr_impls,
            [
                "pub struct CircuitHealthSnapshot",
                "relay_data_cells",
                "relay_data_bytes",
                "max_relay_data_gap",
                "stream_terminal_idle_events",
                "max_stream_terminal_idle",
                "pub fn circuit_health_snapshot",
                "note_stream_terminal_idle",
                "fn circuit_health_snapshot(&self) -> Option<CircuitHealthSnapshot>",
                "ClientTunnel::circuit_health_snapshot(self).ok()",
                "RelayCmd::DATA",
                "note_relay_data(now",
                "candidate_health_summary",
                "torfast_candidate_health_summary",
                "TORFAST_EXIT_SELECT_HEALTH_AWARE",
                "torfast_exit_select_health_aware_is_enabled",
                "torfast_exit_select_load_aware_is_enabled(usage) && torfast_exit_select_health_aware()",
                "TORFAST_EXIT_SELECT_HEALTH_MIN_CELLS",
                "TORFAST_EXIT_SELECT_HEALTH_MIN_BYTES",
                "TORFAST_EXIT_SELECT_HEALTH_MAX_GAP_MS",
                "TORFAST_EXIT_SELECT_HEALTH_MAX_AGE_MS",
                "TORFAST_EXIT_SELECT_HEALTH_MIN_MOVE_SCORE_BPS",
                "TORFAST_EXIT_SELECT_HEALTH_MIN_IMPROVEMENT_NUM",
                "TORFAST_EXIT_SELECT_HEALTH_MIN_IMPROVEMENT_DEN",
                "TORFAST_EXIT_SELECT_PREFER_COLD_SAME_ISOLATION",
                "health_aware_best_index",
                "health_aware_beats_assignment",
                "cold_assignment_should_beat_health",
                "torfast_health_score",
                "select_health_aware",
                "select_prefer_cold_same_isolation",
                "health_aware_candidate_index",
                "health_aware_assignment_score_bps",
                "selected_health_score_bps",
            ],
            [
                "crates/tor-proto/src/client.rs",
                "crates/tor-proto/src/client/circuit.rs",
                "crates/tor-proto/src/client/reactor/circuit.rs",
                "crates/tor-circmgr/src/mgr.rs",
                "crates/tor-circmgr/src/impls.rs",
            ],
            "Circuit health is observed locally from incoming relay DATA cells and only used by the default-off load-aware lab selector.",
        ),
        check_contains_all(
            "stream_idle_bad_health_signal_is_default_off_lab_only",
            tor_proto_client
            + "\n"
            + tor_proto_circuit
            + "\n"
            + tor_proto_data_stream
            + "\n"
            + circmgr_mgr,
            [
                "TORFAST_EXIT_SELECT_BAD_HEALTH_STREAM_IDLE_MS",
                "TORFAST_EXIT_SELECT_BAD_HEALTH_STREAM_IDLE_MIN_MS: u64 = 1_000",
                "TORFAST_EXIT_SELECT_BAD_HEALTH_STREAM_IDLE_MAX_MS: u64 = 120_000",
                "fn torfast_exit_select_bad_health_stream_idle_ms",
                "std::env::var(TORFAST_EXIT_SELECT_BAD_HEALTH_STREAM_IDLE_MS_ENV)",
                "torfast_health_has_recent_stream_idle",
                "stream_terminal_idle_events",
                "max_stream_terminal_idle",
                "last_stream_terminal_idle_at",
                "note_stream_terminal_idle",
                "torfast_note_stream_terminal_idle",
            ],
            [
                "crates/tor-proto/src/client.rs",
                "crates/tor-proto/src/client/circuit.rs",
                "crates/tor-proto/src/client/stream/data.rs",
                "crates/tor-circmgr/src/mgr.rs",
            ],
            "Stream terminal idle health is recorded locally, but it only affects selection when the bounded lab env var is set.",
        ),
        check_contains_all(
            "active_no_data_bad_health_signal_is_default_off_lab_only",
            tor_proto_client
            + "\n"
            + tor_proto_circuit
            + "\n"
            + tor_proto_data_stream
            + "\n"
            + circmgr_mgr,
            [
                "TORFAST_EXIT_SELECT_BAD_HEALTH_ACTIVE_NO_DATA_MS",
                "TORFAST_EXIT_SELECT_BAD_HEALTH_ACTIVE_NO_DATA_MIN_MS: u64 = 1_000",
                "TORFAST_EXIT_SELECT_BAD_HEALTH_ACTIVE_NO_DATA_MAX_MS: u64 = 120_000",
                "fn torfast_exit_select_bad_health_active_no_data_ms",
                "std::env::var(TORFAST_EXIT_SELECT_BAD_HEALTH_ACTIVE_NO_DATA_MS_ENV)",
                "torfast_health_has_active_no_data_idle",
                "active_streams_started_at",
                "last_relay_data_at",
                "note_stream_active_opened",
                "note_stream_active_closed",
                "torfast_note_stream_active_opened",
                "torfast_note_stream_active_closed",
            ],
            [
                "crates/tor-proto/src/client.rs",
                "crates/tor-proto/src/client/circuit.rs",
                "crates/tor-proto/src/client/stream/data.rs",
                "crates/tor-circmgr/src/mgr.rs",
            ],
            "Active no-DATA health is recorded locally, default-off, bounded, and only used by the lab bad-health guard.",
        ),
        check_contains_all(
            "active_stream_cap_is_default_off_lab_only",
            tor_proto_client
            + "\n"
            + tor_proto_circuit
            + "\n"
            + tor_proto_data_stream
            + "\n"
            + circmgr_mgr,
            [
                "TORFAST_EXIT_SELECT_MAX_ACTIVE_STREAMS",
                "TORFAST_EXIT_SELECT_MAX_ACTIVE_STREAMS_MIN: u64 = 1",
                "TORFAST_EXIT_SELECT_MAX_ACTIVE_STREAMS_MAX: u64 = 32",
                "fn torfast_exit_select_max_active_streams",
                "std::env::var(TORFAST_EXIT_SELECT_MAX_ACTIVE_STREAMS_ENV)",
                "active_stream_capped_selected_index",
                "find_best_index_before_active_cap",
                "selected_candidate_index_before_active_cap",
                "active_stream_cap_moved",
                "active_stream_cap_saturated",
                "torfast_entry_active_streams",
                "active_streams",
                "max_active_streams",
                "note_stream_active_opened",
                "note_stream_active_closed",
                "torfast_note_stream_active_opened",
                "torfast_note_stream_active_closed",
            ],
            [
                "crates/tor-proto/src/client.rs",
                "crates/tor-proto/src/client/circuit.rs",
                "crates/tor-proto/src/client/stream/data.rs",
                "crates/tor-circmgr/src/mgr.rs",
            ],
            "Active stream counts are local-only and only affect already eligible open-circuit selection when the bounded lab env var is set.",
        ),
        check_contains_all(
            "assigned_stream_cap_is_default_off_lab_only",
            circmgr_mgr,
            [
                "TORFAST_EXIT_SELECT_MAX_ASSIGNED_STREAMS",
                "TORFAST_EXIT_SELECT_MAX_ASSIGNED_STREAMS_MIN: u64 = 1",
                "TORFAST_EXIT_SELECT_MAX_ASSIGNED_STREAMS_MAX: u64 = 32",
                "fn torfast_exit_select_max_assigned_streams",
                "torfast_exit_select_load_aware_is_enabled(usage)",
                "std::env::var(TORFAST_EXIT_SELECT_MAX_ASSIGNED_STREAMS_ENV)",
                "assigned_stream_capped_selected_index",
                "selected_candidate_index_after_active_cap",
                "assigned_stream_cap_moved",
                "assigned_stream_cap_saturated",
                "selected_before_assigned_cap_assigned_streams",
                "selected_assigned_streams",
            ],
            [
                "crates/tor-circmgr/src/mgr.rs",
            ],
            "Assigned stream cap is bounded, default-off, load-aware-only, and only moves among already eligible open circuits.",
        ),
        check_contains_all(
            "same_isolation_assigned_stream_cap_is_default_off_lab_only",
            circmgr_mgr,
            [
                "TORFAST_EXIT_SELECT_SAME_ISOLATION_MAX_ASSIGNED_STREAMS",
                "TORFAST_EXIT_SELECT_SAME_ISOLATION_MAX_ASSIGNED_STREAMS_MIN: u64 = 1",
                "TORFAST_EXIT_SELECT_SAME_ISOLATION_MAX_ASSIGNED_STREAMS_MAX: u64 = 32",
                "fn torfast_exit_select_same_isolation_max_assigned_streams",
                "torfast_exit_select_load_aware_is_enabled(usage)",
                "std::env::var(TORFAST_EXIT_SELECT_SAME_ISOLATION_MAX_ASSIGNED_STREAMS_ENV)",
                "TORFAST_EXIT_SELECT_SAME_ISOLATION_MAX_ASSIGNED_STREAMS_TOPUP",
                "fn torfast_exit_select_same_isolation_max_assigned_streams_topup_is_enabled",
                "TORFAST_EXIT_SELECT_SAME_ISOLATION_MAX_ASSIGNED_STREAMS_PENDING_WAIT_MS",
                "TORFAST_EXIT_SELECT_SAME_ISOLATION_MAX_ASSIGNED_STREAMS_PENDING_WAIT_MIN_MS: u64 = 50",
                "TORFAST_EXIT_SELECT_SAME_ISOLATION_MAX_ASSIGNED_STREAMS_PENDING_WAIT_MAX_MS: u64 = 2_000",
                "fn torfast_exit_select_same_isolation_max_assigned_streams_pending_wait",
                "torfast_should_top_up_same_isolation_assigned_cap",
                "torfast_should_wait_for_same_isolation_assigned_cap_pending",
                "OpenAfterSameIsolationPendingWait",
                "same_isolation_assigned_stream_capped_selected_index",
                "selected_candidate_index_after_same_isolation_assigned_cap",
                "same_isolation_assigned_stream_cap_moved",
                "same_isolation_assigned_stream_cap_saturated",
                "torfast_exit_isolation_bucket(usage)",
                "\"exit_compatible_isolated\" | \"exit_unisolated\"",
            ],
            [
                "crates/tor-circmgr/src/mgr.rs",
            ],
            "Same-isolation assigned stream cap and its optional topup/pending wait are bounded, default-off, load-aware-only, and only act on already eligible compatible or unisolated exit circuits.",
        ),
        check_contains_all(
            "healthy_over_cold_guard_is_default_off_lab_only",
            circmgr_mgr,
            [
                "TORFAST_EXIT_SELECT_HEALTHY_OVER_COLD_MIN_ASSIGNED",
                "TORFAST_EXIT_SELECT_HEALTHY_OVER_COLD_MIN_ASSIGNED_MIN: u64 = 0",
                "TORFAST_EXIT_SELECT_HEALTHY_OVER_COLD_MIN_ASSIGNED_MAX: u64 = 32",
                "fn torfast_exit_select_healthy_over_cold_min_assigned",
                "torfast_exit_select_load_aware_is_enabled(usage)",
                "healthy_over_cold_selected_index",
                "assignment.assigned_streams < min_assigned",
                "Self::torfast_entry_health_score(assignment).is_some()",
                "Self::health_aware_beats_assignment(ents, health_selected, assignment_selected, false)",
                "select_healthy_over_cold_min_assigned",
                "healthy_over_cold_candidate_index",
            ],
            ["crates/tor-circmgr/src/mgr.rs"],
            "Healthy-over-cold is bounded, default-off, load-aware-only, and only moves from a busy cold eligible circuit to a locally proven healthier eligible circuit.",
        ),
        check_contains_all(
            "healthy_over_cold_guard_only_is_default_off_lab_only",
            circmgr_mgr,
            [
                "TORFAST_EXIT_SELECT_HEALTHY_OVER_COLD_GUARD_ONLY_MIN_ASSIGNED",
                "TORFAST_EXIT_SELECT_HEALTHY_OVER_COLD_GUARD_ONLY_MIN_ASSIGNED_MIN: u64 = 1",
                "TORFAST_EXIT_SELECT_HEALTHY_OVER_COLD_GUARD_ONLY_MIN_ASSIGNED_MAX: u64 = 32",
                "fn torfast_exit_select_healthy_over_cold_guard_only_min_assigned",
                "matches!(usage, TargetTunnelUsage::Exit { .. })",
                "std::env::var(TORFAST_EXIT_SELECT_HEALTHY_OVER_COLD_GUARD_ONLY_MIN_ASSIGNED_ENV)",
                "find_best_index_before_active_cap_with_guard_context",
                "find_best_index_before_guard_only",
                "healthy_over_cold_guard_only_candidate_index",
                "healthy_over_cold_selected_index",
                "select_healthy_over_cold_guard_only_min_assigned",
                "healthy_over_cold_guard_only_candidate_index",
            ],
            ["crates/tor-circmgr/src/mgr.rs"],
            "Guard-only healthy-over-cold is bounded, default-off, exit-only, and only overrides normal selection when the load-aware cold-circuit guard finds a locally proven healthier eligible circuit.",
        ),
        check_contains_all(
            "exit_select_unknown_fallback_is_default_off_and_guarded",
            circmgr_mgr,
            [
                "TORFAST_EXIT_SELECT_AVOID_BAD_HEALTH_UNKNOWN_FALLBACK",
                "fn torfast_exit_select_avoid_bad_health_unknown_fallback",
                "std::env::var(TORFAST_EXIT_SELECT_AVOID_BAD_HEALTH_UNKNOWN_FALLBACK_ENV)",
                "unwrap_or(false)",
                "fn torfast_exit_select_avoid_bad_health_unknown_fallback_is_enabled",
                "torfast_exit_select_avoid_bad_health_is_enabled(usage)\n        && torfast_exit_select_avoid_bad_health_unknown_fallback()",
                "least_assigned_index_avoiding_bad_health",
                "avoid_bad_health_unknown_fallback",
                "Self::torfast_entry_has_good_health(entry)",
                "if !avoid_bad_health_unknown_fallback",
                "!Self::torfast_entry_has_bad_health(entry)",
                "entry.assigned_streams == 0",
                "select_avoid_bad_health_unknown_fallback",
            ],
            ["crates/tor-circmgr/src/mgr.rs"],
            "Unknown-health fallback is default-off and only runs behind load-aware bad-health avoidance, choosing only unassigned already eligible open exit circuits.",
        ),
        check_contains_all(
            "exit_select_bad_health_hedge_is_bounded_lab_only",
            circmgr_mgr,
            [
                "TORFAST_EXIT_SELECT_BAD_HEALTH_HEDGE_MS",
                "TORFAST_EXIT_SELECT_BAD_HEALTH_HEDGE_MIN_MS: u64 = 250",
                "TORFAST_EXIT_SELECT_BAD_HEALTH_HEDGE_MAX_MS: u64 = 10_000",
                "fn torfast_exit_select_bad_health_hedge_is_enabled",
                "torfast_exit_select_avoid_bad_health_is_enabled(usage)",
                "std::env::var(TORFAST_EXIT_SELECT_BAD_HEALTH_HEDGE_ENV)",
                "let bad_health_hedge_after = torfast_exit_select_bad_health_hedge_is_enabled(usage)",
                "|| bad_health_hedge_after.is_some()",
                "Action::OpenAfterBadHealthHedge",
                "torfast circuit selection bad health hedge",
                "torfast circuit selection bad health hedge won",
                "torfast circuit selection bad health hedge timer fired",
            ],
            ["crates/tor-circmgr/src/mgr.rs"],
            "Bad-health hedge is default-off, bounded, and only runs behind load-aware bad-health avoidance.",
        ),
        check_contains_all(
            "normal_selector_logs_candidate_context_without_enabling_selector",
            circmgr_mgr,
            [
                "TORFAST_EXIT_SELECT_LOW_LOG_CONTEXT",
                "fn torfast_exit_select_low_log_context() -> bool",
                "std::env::var(TORFAST_EXIT_SELECT_LOW_LOG_CONTEXT_ENV)",
                "let select_load_aware = torfast_exit_select_load_aware_is_enabled(usage)",
                "let low_log_selection_context = torfast_exit_select_low_log_context()",
                "let collect_selection_context =",
                "tracing::enabled!(tracing::Level::DEBUG) || low_log_selection_context",
                "let open_support_summary = if collect_selection_context",
                "let candidate_assignment_summary = if collect_selection_context",
                "let candidate_health_summary = if collect_selection_context",
                "if low_log_selection_context {",
                "info!(",
                "torfast circuit selection open",
                "let selected_candidate_index_before_active_cap = if select_dir_spread",
                "OpenEntry::find_best_index_before_active_cap_with_guard_context(",
                "select_prefer_cold_same_isolation,",
                "OpenEntry::active_stream_capped_selected_index(",
            ],
            ["crates/tor-circmgr/src/mgr.rs"],
            "Normal exit selection keeps the same picker, while a default-off low-log knob can retain candidate IDs, assignment counts, local health context, and active-cap move proof.",
        ),
        check_regex(
            "prefer_cold_same_isolation_is_wired_into_open_selector",
            circmgr_mgr,
            (
                r"let\s+select_prefer_cold_same_isolation\s*=.*?"
                r"OpenEntry::find_best_index_before_active_cap_with_guard_context\(\s*"
                r"&open,\s*usage,\s*parallelism,\s*"
                r"select_prefer_cold_same_isolation,\s*\)"
            ),
            ["crates/tor-circmgr/src/mgr.rs"],
            "The default-off prefer-cold same-isolation selector flag is passed into the real open-circuit selector.",
        ),
        check_contains_all(
            "exit_same_isolation_topup_is_bounded_lab_only",
            circmgr_mgr,
            [
                "TORFAST_EXIT_SAME_ISOLATION_TARGET",
                "TORFAST_EXIT_SAME_ISOLATION_TARGET_MIN: usize = 2",
                "TORFAST_EXIT_SAME_ISOLATION_TARGET_MAX: usize = 4",
                "TORFAST_EXIT_SAME_ISOLATION_MIN_ASSIGNED_STREAMS",
                "TORFAST_EXIT_SAME_ISOLATION_MIN_ASSIGNED_STREAMS_DEFAULT: u64 = 2",
                "TORFAST_EXIT_SAME_ISOLATION_REQUIRE_BAD_HEALTH",
                "TORFAST_EXIT_SAME_ISOLATION_PREWARM_FIRST_STREAM",
                "TORFAST_EXIT_SAME_ISOLATION_PENDING_WAIT_MS",
                "TORFAST_EXIT_SAME_ISOLATION_PENDING_WAIT_MIN_MS: u64 = 50",
                "TORFAST_EXIT_SAME_ISOLATION_PENDING_WAIT_MAX_MS: u64 = 2_000",
                "TORFAST_EXIT_SAME_ISOLATION_OTHER_ISOLATION_MIN",
                "TORFAST_EXIT_SAME_ISOLATION_OTHER_ISOLATION_MAX: usize = 64",
                "fn torfast_exit_same_isolation_target",
                "fn torfast_exit_same_isolation_min_assigned_streams",
                "fn torfast_exit_same_isolation_require_bad_health",
                "fn torfast_exit_same_isolation_prewarm_first_stream",
                "fn torfast_exit_same_isolation_pending_wait",
                "fn torfast_exit_same_isolation_other_isolation_min",
                "fn torfast_exit_select_prefer_cold_same_isolation",
                "fn torfast_exit_select_prefer_cold_same_isolation_is_enabled",
                "fn torfast_should_wait_for_same_isolation_pending",
                "let same_isolation_target = torfast_exit_same_isolation_target(usage)",
                "let same_isolation_prewarm_first_stream = same_isolation_target",
                "let same_isolation_pending_wait =",
                "let same_isolation_pending_wait_pressure =",
                "let same_isolation_other_isolation_min = same_isolation_target",
                "fn torfast_should_top_up_same_isolation",
                "TargetTunnelUsage::Exit { .. }",
                "torfast_pending_supported_count",
                "torfast_exit_incompatible_isolated_count",
                "let exit_incompatible_isolated = if same_isolation_other_isolation_min.is_some()",
                "active_stream_cap_saturated",
                "selected_active_streams",
                "select_max_active_streams",
                "let active_cap_pressure = active_stream_cap_saturated",
                "selected_active_streams >= cap",
                "let first_stream_prewarm = prewarm_first_stream && selected_assigned_streams == 0",
                "let first_stream_prewarm_followup = prewarm_first_stream && selected_assigned_streams > 0",
                "let other_isolation_pressure =",
                "other_isolation_min.is_some_and(|min| exit_incompatible_isolated >= min)",
                "let effective_target = target",
                ".saturating_add(usize::from(active_cap_pressure))",
                ".min(TORFAST_EXIT_SAME_ISOLATION_TARGET_MAX + 1)",
                "assigned_stream_pressure",
                "|| active_cap_pressure",
                "|| first_stream_prewarm",
                "|| other_isolation_pressure",
                "selected_assigned_streams > torfast_exit_same_isolation_min_assigned_streams()",
                "(!require_bad_health || selected_has_bad_health)",
                "open_candidates + pending_supported_count < effective_target",
                "select_max_active_streams = select_max_active_streams.unwrap_or(0)",
                "prewarm_first_stream = same_isolation_prewarm_first_stream",
                "same_isolation_pending_wait_selected_assigned_streams",
                "exit_incompatible_isolated",
                "other_isolation_min",
                "other_isolation_pressure",
                "selected_health_max_gap_ms",
                "selected_health_score_bps",
                "selected_health_age_ms",
                "pending_id",
                "torfast_force_info_lifecycle: bool",
                "torfast_force_info_lifecycle: false",
                "plan.torfast_force_info_lifecycle = true",
                "|| pending_age_ms >= TORFAST_SLOW_TUNNEL_BUILD_LOG_MS",
                "torfast circuit selection build complete",
                "torfast circuit selection build failed",
                "torfast circuit selection build canceled",
                "torfast circuit selection same isolation topup",
                "open_candidates < target",
                "Action::OpenAfterSameIsolationPendingWait",
                "torfast circuit selection same isolation pending wait",
                "torfast circuit selection same isolation pending wait won",
                "torfast circuit selection same isolation pending wait timer fired",
                "list.get_open_mut(&fallback.id())",
                "Same-isolation pending wait fallback restriction failed",
            ],
            ["crates/tor-circmgr/src/mgr.rs"],
            "Same-isolation top-up is bounded, default-off, and can require bad local circuit health before building extra same-usage capacity.",
        ),
        check_regex(
            "same_isolation_target_helper_defaults_off",
            circmgr_mgr,
            (
                r"fn\s+torfast_exit_same_isolation_target\(.*?\)\s*->\s*Option<usize>\s*\{.*?"
                r"TORFAST_EXIT_SAME_ISOLATION_TARGET_ENV.*?"
                r"torfast_env_usize_in_range\(.*?,\s*None\s*\)"
            ),
            ["crates/tor-circmgr/src/mgr.rs"],
            "Same-isolation top-up stays disabled until a lab target is explicitly requested.",
        ),
        check_regex(
            "same_isolation_prewarm_first_stream_defaults_off",
            circmgr_mgr,
            (
                r"fn\s+torfast_exit_same_isolation_prewarm_first_stream\(\)\s*->\s*bool\s*\{.*?"
                r"TORFAST_EXIT_SAME_ISOLATION_PREWARM_FIRST_STREAM_ENV.*?"
                r"unwrap_or\(false\)"
            ),
            ["crates/tor-circmgr/src/mgr.rs"],
            "First-stream same-isolation prewarm remains opt-in for lab runs.",
        ),
        check_regex(
            "prefer_cold_same_isolation_defaults_off",
            circmgr_mgr,
            (
                r"fn\s+torfast_exit_select_prefer_cold_same_isolation\(\)\s*->\s*bool\s*\{.*?"
                r"TORFAST_EXIT_SELECT_PREFER_COLD_SAME_ISOLATION_ENV.*?"
                r"torfast_env_flag\(.*?,\s*false\s*\)"
            ),
            ["crates/tor-circmgr/src/mgr.rs"],
            "Prefer-cold same-isolation selection remains lab-only and off by default.",
        ),
        check_regex(
            "default_max_dirtiness_is_10_minutes",
            config,
            r"fn\s+default_max_dirtiness\(\).*?\{\s*Duration::from_secs\(60\s*\*\s*10\)\s*\}",
            ["crates/tor-circmgr/src/config.rs"],
            "Arti default circuit reuse window is 10 minutes.",
        ),
        check_contains_all(
            "example_configs_warn_against_reduced_padding",
            example_config + "\n" + oldest_config,
            [
                '#padding = "normal"',
                "increasing the",
                "traceability of the client connections",
            ],
            [
                "crates/arti/src/arti-example-config.toml",
                "crates/arti/src/oldest-supported-config.toml",
            ],
            "The config docs keep normal padding and warn reduced padding hurts privacy.",
        ),
        check_contains_all(
            "exit_path_builder_excludes_guard_and_exit_families",
            path,
            [
                "let guard_exclusion",
                "RelayExclusion::exclude_relays_in_same_family",
                "let (exit, middle_usage) = builder.pick_exit",
                "let mut family_exclusion",
                "let (middle, info) = selector.select_relay",
            ],
            ["crates/tor-circmgr/src/path.rs"],
            "Arti path code excludes related relays while picking exit and middle hops.",
        ),
        check_contains_all(
            "exit_path_tests_check_three_hops_guard_reuse_family_subnet",
            exitpath,
            [
                "assert_eq!(relays.len(), 3)",
                "is_suitable_as_guard()",
                "assert!(!r1.same_relay_ids(r2))",
                "assert!(r1.can_share_circuit(r2, subnet_config, family_rules))",
                "for _ in 0..1000",
            ],
            ["crates/tor-circmgr/src/path/exitpath.rs"],
            "Arti upstream tests cover 3-hop paths, guard use, no relay reuse, family and subnet sharing.",
        ),
        check_contains_all(
            "rpc_is_feature_gated",
            cargo + "\n" + lib,
            [
                'rpc = ["arti-rpcserver"',
                'if #[cfg(all(feature="experimental-api", feature="rpc"))]',
                'rpc_stub.rs',
            ],
            ["crates/arti/Cargo.toml", "crates/arti/src/lib.rs"],
            "The normal build may not expose RPC path visibility unless built with RPC features.",
        ),
    ]

    if help_text is not None:
        checks.append(
            QualityCheck(
                name="release_help_has_no_c_tor_control_port",
                ok=("ControlPort" not in help_text and "circuit-status" not in help_text),
                evidence=["upstream/arti/target/release/arti --help", "arti proxy --help"],
                note="The release CLI help does not show C Tor-style circuit-status access.",
            )
        )
    return checks


def check_regex(
    name: str,
    text: str,
    pattern: str,
    evidence: list[str],
    note: str,
) -> QualityCheck:
    return QualityCheck(
        name=name,
        ok=re.search(pattern, text, flags=re.DOTALL) is not None,
        evidence=evidence,
        note=note,
    )


def check_contains_all(
    name: str,
    text: str,
    needles: list[str],
    evidence: list[str],
    note: str,
) -> QualityCheck:
    missing = [needle for needle in needles if needle not in text]
    return QualityCheck(
        name=name,
        ok=not missing,
        evidence=evidence + [f"missing: {needle}" for needle in missing],
        note=note,
    )


def short_summary(payload: dict[str, object]) -> dict[str, object]:
    checks = payload["checks"]
    assert isinstance(checks, list)
    failed = [
        check["name"]
        for check in checks
        if isinstance(check, dict) and not check.get("ok")
    ]
    return {
        "ok": payload["ok"],
        "evidence_type": payload["evidence_type"],
        "runtime_circuit_path_proof": payload["runtime_circuit_path_proof"],
        "checks": len(checks),
        "failed": failed,
    }


if __name__ == "__main__":
    sys.exit(main())
