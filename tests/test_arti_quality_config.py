import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from check_arti_quality_config import evaluate_sources


GOOD_SOURCES = {
    "config": """
fn default_reachable_addrs() -> Vec<AddrPortPattern> {
    vec![AddrPortPattern::new_all()]
}
fn ipv4_prefix_default() -> u8 {
    16
}
fn ipv6_prefix_default() -> u8 {
    32
}
fn default_preemptive_ports() -> Vec<u16> {
    vec![80, 443]
}
fn default_preemptive_min_exit_circs_for_port() -> usize {
    2
}
fn default_max_dirtiness() -> Duration {
    Duration::from_secs(60 * 10)
}
""",
    "path": """
let guard_exclusion = RelayExclusion::exclude_relays_in_same_family();
let (exit, middle_usage) = builder.pick_exit();
let mut family_exclusion = RelayExclusion::exclude_relays_in_same_family();
let (middle, info) = selector.select_relay();
""",
    "exitpath": """
assert_eq!(relays.len(), 3);
is_suitable_as_guard()
assert!(!r1.same_relay_ids(r2));
assert!(r1.can_share_circuit(r2, subnet_config, family_rules));
for _ in 0..1000 {}
""",
    "example_config": """
#ipv4_subnet_family_prefix = 16
#ipv6_subnet_family_prefix = 32
#reachable_addrs = [ "*:*" ]
#initial_predicted_ports = [80, 443]
#min_exit_circs_for_port = 2
#padding = "normal"
increasing the
traceability of the client connections
""",
    "oldest_config": """
#ipv4_subnet_family_prefix = 16
#ipv6_subnet_family_prefix = 32
#reachable_addrs = [ "*:*" ]
#initial_predicted_ports = [80, 443]
#min_exit_circs_for_port = 2
#padding = "normal"
increasing the
traceability of the client connections
""",
    "cargo": 'rpc = ["arti-rpcserver"]',
    "arti_client": """
"torfast exit client timing tunnel ready"
"torfast exit client timing begin stream finished"
"torfast hs client timing tunnel ready"
"torfast hs client timing begin stream finished"
if tunnel_elapsed_ms >= 1000 {
                    info!(
} else if begin_elapsed_ms >= 1000 {
                    info!(
if stream.is_err() || begin_elapsed_ms >= 1000 {
                    info!(
tunnel_unique_id = %tunnel_unique_id
tunnel_elapsed_ms
begin_phase_ms
""",
    "lib": 'if #[cfg(all(feature="experimental-api", feature="rpc"))] rpc_stub.rs',
    "circmgr_lib": """
let base_delay = Duration::from_secs(1);
pub async fn get_or_launch_dir_microdesc(&self, netdir: DirInfo<'_>) -> Result<ClientDirTunnel> {
    let tunnel = self.0.get_or_launch_dir_microdesc(netdir).await?;
    Ok(tunnel.into())
}
""",
    "circmgr_preemptive": """
const TORFAST_PREEMPTIVE_443_CIRCS_ENV: &str = "TORFAST_PREEMPTIVE_443_CIRCS";
const TORFAST_PREEMPTIVE_443_CIRCS_DEFAULT: usize = 3;
const TORFAST_PREEMPTIVE_443_CIRCS_MIN: usize = 2;
const TORFAST_PREEMPTIVE_443_CIRCS_MAX: usize = 4;
const TORFAST_PREEMPTIVE_443_BURST_MIN_REQUESTS_ENV: &str =
    "TORFAST_PREEMPTIVE_443_BURST_MIN_REQUESTS";
const TORFAST_PREEMPTIVE_443_BURST_MIN_REQUESTS_MIN: usize = 2;
const TORFAST_PREEMPTIVE_443_BURST_MIN_REQUESTS_MAX: usize = 32;
const TORFAST_PREEMPTIVE_443_BURST_WINDOW_MS: u64 = 2_000;
fn parse_torfast_preemptive_443_circs() {}
fn torfast_preemptive_443_circs_from_env_value() {
    std::env::var(TORFAST_PREEMPTIVE_443_CIRCS_ENV).ok().as_deref();
    value.to_ascii_lowercase().as_str();
    "0" | "false" | "no" | "off";
    port.port == 443;
    unwrap_or(default_circs);
}
fn parse_torfast_preemptive_443_burst_min_requests() {
    std::env::var(TORFAST_PREEMPTIVE_443_BURST_MIN_REQUESTS_ENV);
    "0" | "false" | "no" | "off";
    recent_443_usages: VecDeque<Instant>;
    recent_443_usage_count;
    circs.max(TORFAST_PREEMPTIVE_443_CIRCS_MAX);
}
""",
    "circmgr_hspool": """
const DELAY: Duration = Duration::from_secs(30);
const NETDIR_RETRY_DELAY: Duration = Duration::from_secs(1);
const TORFAST_HSPOOL_BACKGROUND_START_DELAY_MS_ENV: &str =
    "TORFAST_HSPOOL_BACKGROUND_START_DELAY_MS";
const TORFAST_HSPOOL_BACKGROUND_START_DELAY_DEFAULT_MS: u64 = 1_000;
const TORFAST_HSPOOL_BACKGROUND_START_DELAY_MAX_MS: u64 = 60_000;
fn torfast_hspool_background_start_delay() {}
schedule.fire_in(torfast_hspool_background_start_delay());
const TORFAST_HSPOOL_LAUNCH_PARALLELISM_ENV: &str = "TORFAST_HSPOOL_LAUNCH_PARALLELISM";
const TORFAST_HSPOOL_LAUNCH_PARALLELISM_DEFAULT: usize = 1;
const TORFAST_HSPOOL_LAUNCH_PARALLELISM_MAX: usize = 4;
fn torfast_hspool_launch_parallelism_from_env_value() {}
fn torfast_hspool_launch_parallelism() {}
const TORFAST_HSPOOL_ON_DEMAND_POOL_GRACE_MS_ENV: &str =
    "TORFAST_HSPOOL_ON_DEMAND_POOL_GRACE_MS";
const TORFAST_HSPOOL_ON_DEMAND_POOL_GRACE_DEFAULT_MS: u64 = 0;
const TORFAST_HSPOOL_ON_DEMAND_POOL_GRACE_MAX_MS: u64 = 1_000;
const TORFAST_HSPOOL_ON_DEMAND_POOL_GRACE_POLL_MS: u64 = 25;
fn torfast_hspool_on_demand_pool_grace_from_env_value() {}
fn torfast_hspool_on_demand_pool_grace() {}
const TORFAST_HSPOOL_ON_DEMAND_POOL_RACE_MS_ENV: &str =
    "TORFAST_HSPOOL_ON_DEMAND_POOL_RACE_MS";
const TORFAST_HSPOOL_ON_DEMAND_POOL_RACE_DEFAULT_MS: u64 = 0;
const TORFAST_HSPOOL_ON_DEMAND_POOL_RACE_MAX_MS: u64 = 1_000;
fn torfast_hspool_on_demand_pool_race_from_env_value() {}
fn torfast_hspool_on_demand_pool_race() {}
race_on_demand_with_ready_stem_circuit
launch_on_demand_stem_circuit
take_ready_stem_circuit
wait_for_ready_stem_circuit
maybe_extend_stem_circuit
ensure_suitable_circuit
use tracing::{debug, info, instrument, trace, warn};
torfast hspool timing stem ready
torfast hspool timing stem failed
torfast hspool timing stem selected
torfast hspool timing specific circuit ready
torfast hspool timing specific circuit failed
torfast hspool timing client rend circuit ready
source = "pool"
source = "on_demand"
extend_ms = extend_started.elapsed().as_millis()
let mut waiting_for_netdir = false;
waiting_for_netdir = true;
if launch_parallelism == 1 {}
FuturesUnordered;
launch_hs_unmanaged::<OwnedChanTarget>;
circs_to_launch.note_circ_launch_failed(kind);
if waiting_for_netdir && circs_to_launch.n_to_launch() > 0 {
    schedule.fire_in(NETDIR_RETRY_DELAY);
}
""",
    "circmgr_hspool_pool": """
const DEFAULT_GUARDED_STEM_TARGET: usize = 2;
const TORFAST_HSPOOL_GUARDED_STEM_TARGET_ENV: &str = "TORFAST_HSPOOL_GUARDED_STEM_TARGET";
const TORFAST_HSPOOL_GUARDED_STEM_TARGET_MAX: usize = 16;
fn torfast_hspool_guarded_stem_target_from_env_value() {}
fn torfast_hspool_guarded_stem_target() {}
guarded_stem_target: torfast_hspool_guarded_stem_target()
.clamp(
torfast_hspool_guarded_stem_target(),
MAX_GUARDED_STEM_TARGET
""",
    "circmgr_mgr": """
use tor_proto::client::circuit::CircuitHealthSnapshot;
const TORFAST_EXIT_PENDING_HEDGE_ENV: &str = "TORFAST_EXIT_PENDING_HEDGE_MS";
const TORFAST_EXIT_PENDING_HEDGE_MIN_MS: u64 = 500;
const TORFAST_EXIT_PENDING_HEDGE_MAX_MS: u64 = 60_000;
const TORFAST_EXIT_PENDING_HEDGE_MAX_PENDING: usize = 2;

fn circuit_health_snapshot(&self) -> Option<CircuitHealthSnapshot> {
    None
}

fn torfast_exit_pending_hedge_after() -> Option<Duration> {
    std::env::var(TORFAST_EXIT_PENDING_HEDGE_ENV).ok()
}

const TORFAST_EXIT_SELECT_LOAD_AWARE_ENV: &str = "TORFAST_EXIT_SELECT_LOAD_AWARE";
const TORFAST_EXIT_SELECT_LEAST_ASSIGNED_ENV: &str = "TORFAST_EXIT_SELECT_LEAST_ASSIGNED";
const TORFAST_EXIT_SELECT_HEALTH_AWARE_ENV: &str = "TORFAST_EXIT_SELECT_HEALTH_AWARE";
const TORFAST_EXIT_SELECT_HEALTH_AWARE_MIN_ASSIGNED_ENV: &str =
    "TORFAST_EXIT_SELECT_HEALTH_AWARE_MIN_ASSIGNED";
const TORFAST_EXIT_SELECT_AVOID_BAD_HEALTH_ENV: &str = "TORFAST_EXIT_SELECT_AVOID_BAD_HEALTH";
const TORFAST_EXIT_SELECT_AVOID_BAD_HEALTH_UNKNOWN_FALLBACK_ENV: &str =
    "TORFAST_EXIT_SELECT_AVOID_BAD_HEALTH_UNKNOWN_FALLBACK";
const TORFAST_EXIT_SELECT_BAD_HEALTH_HEDGE_ENV: &str =
    "TORFAST_EXIT_SELECT_BAD_HEALTH_HEDGE_MS";
const TORFAST_EXIT_SELECT_BAD_HEALTH_STREAM_IDLE_MS_ENV: &str =
    "TORFAST_EXIT_SELECT_BAD_HEALTH_STREAM_IDLE_MS";
const TORFAST_EXIT_SELECT_BAD_HEALTH_ACTIVE_NO_DATA_MS_ENV: &str =
    "TORFAST_EXIT_SELECT_BAD_HEALTH_ACTIVE_NO_DATA_MS";
const TORFAST_EXIT_SELECT_MAX_ACTIVE_STREAMS_ENV: &str =
    "TORFAST_EXIT_SELECT_MAX_ACTIVE_STREAMS";
const TORFAST_EXIT_SELECT_MAX_ASSIGNED_STREAMS_ENV: &str =
    "TORFAST_EXIT_SELECT_MAX_ASSIGNED_STREAMS";
const TORFAST_EXIT_SELECT_BAD_HEALTH_HEDGE_MIN_MS: u64 = 250;
const TORFAST_EXIT_SELECT_BAD_HEALTH_HEDGE_MAX_MS: u64 = 10_000;
const TORFAST_EXIT_SELECT_BAD_HEALTH_STREAM_IDLE_MIN_MS: u64 = 1_000;
const TORFAST_EXIT_SELECT_BAD_HEALTH_STREAM_IDLE_MAX_MS: u64 = 120_000;
const TORFAST_EXIT_SELECT_BAD_HEALTH_ACTIVE_NO_DATA_MIN_MS: u64 = 1_000;
const TORFAST_EXIT_SELECT_BAD_HEALTH_ACTIVE_NO_DATA_MAX_MS: u64 = 120_000;
const TORFAST_EXIT_SELECT_MAX_ACTIVE_STREAMS_MIN: u64 = 1;
const TORFAST_EXIT_SELECT_MAX_ACTIVE_STREAMS_MAX: u64 = 32;
const TORFAST_EXIT_SELECT_MAX_ASSIGNED_STREAMS_MIN: u64 = 1;
const TORFAST_EXIT_SELECT_MAX_ASSIGNED_STREAMS_MAX: u64 = 32;
const TORFAST_EXIT_SELECT_HEALTH_AWARE_MIN_ASSIGNED_MIN: u64 = 1;
const TORFAST_EXIT_SELECT_HEALTH_AWARE_MIN_ASSIGNED_MAX: u64 = 32;
const TORFAST_EXIT_SELECT_HEALTH_MIN_CELLS: u64 = 2;
const TORFAST_EXIT_SELECT_HEALTH_MIN_BYTES: u64 = 4096;
const TORFAST_EXIT_SELECT_HEALTH_MAX_GAP_MS: u128 = 750;
const TORFAST_EXIT_SELECT_HEALTH_MAX_AGE_MS: u128 = 2_000;
const TORFAST_EXIT_SELECT_HEALTH_MIN_MOVE_SCORE_BPS: u64 = 64 * 1024;
const TORFAST_EXIT_SELECT_HEALTH_MIN_IMPROVEMENT_NUM: u64 = 2;
const TORFAST_EXIT_SELECT_HEALTH_MIN_IMPROVEMENT_DEN: u64 = 1;
const TORFAST_EXIT_SELECT_MIN_ASSIGNMENT_SPREAD_ENV: &str = "TORFAST_EXIT_SELECT_MIN_ASSIGNMENT_SPREAD";
const TORFAST_EXIT_SELECT_MIN_ASSIGNMENT_SPREAD_MAX: u64 = 8;
const TORFAST_EXIT_SELECT_LOW_LOG_CONTEXT_ENV: &str = "TORFAST_EXIT_SELECT_LOW_LOG_CONTEXT";
const TORFAST_EXIT_SAME_ISOLATION_TARGET_ENV: &str = "TORFAST_EXIT_SAME_ISOLATION_TARGET";
const TORFAST_EXIT_SAME_ISOLATION_TARGET_MIN: usize = 2;
const TORFAST_EXIT_SAME_ISOLATION_TARGET_MAX: usize = 4;
const TORFAST_EXIT_SAME_ISOLATION_MIN_ASSIGNED_STREAMS_ENV: &str =
    "TORFAST_EXIT_SAME_ISOLATION_MIN_ASSIGNED_STREAMS";
const TORFAST_EXIT_SAME_ISOLATION_MIN_ASSIGNED_STREAMS_DEFAULT: u64 = 2;
const TORFAST_EXIT_SAME_ISOLATION_MIN_ASSIGNED_STREAMS_MAX: u64 = 8;
const TORFAST_EXIT_SAME_ISOLATION_REQUIRE_BAD_HEALTH_ENV: &str =
    "TORFAST_EXIT_SAME_ISOLATION_REQUIRE_BAD_HEALTH";
const TORFAST_EXIT_SAME_ISOLATION_PREWARM_FIRST_STREAM_ENV: &str =
    "TORFAST_EXIT_SAME_ISOLATION_PREWARM_FIRST_STREAM";
const TORFAST_EXIT_SAME_ISOLATION_PENDING_WAIT_ENV: &str =
    "TORFAST_EXIT_SAME_ISOLATION_PENDING_WAIT_MS";
const TORFAST_EXIT_SAME_ISOLATION_PENDING_WAIT_MIN_MS: u64 = 50;
const TORFAST_EXIT_SAME_ISOLATION_PENDING_WAIT_MAX_MS: u64 = 2_000;
const TORFAST_EXIT_SAME_ISOLATION_OTHER_ISOLATION_MIN_ENV: &str =
    "TORFAST_EXIT_SAME_ISOLATION_OTHER_ISOLATION_MIN";
const TORFAST_EXIT_SAME_ISOLATION_OTHER_ISOLATION_MAX: usize = 64;
const TORFAST_EXIT_SELECT_PREFER_COLD_SAME_ISOLATION_ENV: &str =
    "TORFAST_EXIT_SELECT_PREFER_COLD_SAME_ISOLATION";
const TORFAST_DIR_SELECT_SPREAD_ENV: &str = "TORFAST_DIR_SELECT_SPREAD";
const TORFAST_PREEMPTIVE_443_BUSY_ACTIVE_AGE_MS_ENV: &str =
    "TORFAST_PREEMPTIVE_443_BUSY_ACTIVE_AGE_MS";
const TORFAST_PREEMPTIVE_443_BUSY_ACTIVE_AGE_MIN_MS: u64 = 100;
const TORFAST_PREEMPTIVE_443_BUSY_ACTIVE_AGE_MAX_MS: u64 = 60_000;
const TORFAST_PREEMPTIVE_443_BUSY_MIN_ACTIVE_STREAMS: u64 = 2;
const TORFAST_PREEMPTIVE_443_BUSY_EXTRA_CIRCS_CAP: usize = 1;

fn torfast_exit_select_load_aware() -> bool {
    let _env = TORFAST_EXIT_SELECT_LOAD_AWARE_ENV;
    torfast_env_flag(None, false)
}

fn torfast_exit_select_least_assigned() -> bool {
    let _env = TORFAST_EXIT_SELECT_LEAST_ASSIGNED_ENV;
    torfast_env_flag(None, false)
}

fn torfast_exit_select_least_assigned_is_enabled(usage: &TargetTunnelUsage) -> bool {
    matches!(usage, TargetTunnelUsage::Exit { .. }) && torfast_exit_select_least_assigned()
}

fn torfast_exit_select_health_aware() -> bool {
    let _env = TORFAST_EXIT_SELECT_HEALTH_AWARE_ENV;
    torfast_env_flag(None, false)
}

fn torfast_exit_select_min_assignment_spread() -> u64 {
    std::env::var(TORFAST_EXIT_SELECT_MIN_ASSIGNMENT_SPREAD_ENV).ok().unwrap_or(0)
}

fn torfast_exit_select_load_aware_is_enabled(usage: &TargetTunnelUsage) -> bool {
    matches!(usage, TargetTunnelUsage::Exit { .. }) && torfast_exit_select_load_aware()
}

fn torfast_exit_select_low_log_context() -> bool {
    std::env::var(TORFAST_EXIT_SELECT_LOW_LOG_CONTEXT_ENV).ok().unwrap_or(false)
}

fn torfast_exit_select_health_aware_is_enabled(usage: &TargetTunnelUsage) -> bool {
    torfast_exit_select_load_aware_is_enabled(usage) && torfast_exit_select_health_aware()
}

fn torfast_exit_select_health_aware_min_assigned(usage: &TargetTunnelUsage) -> Option<u64> {
    torfast_exit_select_health_aware_is_enabled(usage);
    std::env::var(TORFAST_EXIT_SELECT_HEALTH_AWARE_MIN_ASSIGNED_ENV).ok();
}

fn torfast_exit_select_avoid_bad_health() -> bool {
    let _env = TORFAST_EXIT_SELECT_AVOID_BAD_HEALTH_ENV;
    torfast_env_flag(None, false)
}

fn torfast_exit_select_avoid_bad_health_is_enabled(usage: &TargetTunnelUsage) -> bool {
    torfast_exit_select_load_aware_is_enabled(usage) && torfast_exit_select_avoid_bad_health()
}

fn torfast_exit_select_avoid_bad_health_unknown_fallback() -> bool {
    std::env::var(TORFAST_EXIT_SELECT_AVOID_BAD_HEALTH_UNKNOWN_FALLBACK_ENV).ok().unwrap_or(false)
}

fn torfast_exit_select_avoid_bad_health_unknown_fallback_is_enabled(
    usage: &TargetTunnelUsage,
) -> bool {
    torfast_exit_select_avoid_bad_health_is_enabled(usage)
        && torfast_exit_select_avoid_bad_health_unknown_fallback()
}

fn torfast_exit_select_bad_health_hedge_is_enabled(usage: &TargetTunnelUsage) -> Option<Duration> {
    torfast_exit_select_avoid_bad_health_is_enabled(usage);
    std::env::var(TORFAST_EXIT_SELECT_BAD_HEALTH_HEDGE_ENV).ok()
}

fn torfast_exit_select_bad_health_stream_idle_ms() -> Option<u128> {
    std::env::var(TORFAST_EXIT_SELECT_BAD_HEALTH_STREAM_IDLE_MS_ENV).ok()
}

fn torfast_exit_select_bad_health_active_no_data_ms() -> Option<u128> {
    std::env::var(TORFAST_EXIT_SELECT_BAD_HEALTH_ACTIVE_NO_DATA_MS_ENV).ok()
}

fn torfast_exit_select_max_active_streams(usage: &TargetTunnelUsage) -> Option<u64> {
    std::env::var(TORFAST_EXIT_SELECT_MAX_ACTIVE_STREAMS_ENV).ok()
}

fn torfast_exit_select_max_assigned_streams(usage: &TargetTunnelUsage) -> Option<u64> {
    torfast_exit_select_load_aware_is_enabled(usage);
    std::env::var(TORFAST_EXIT_SELECT_MAX_ASSIGNED_STREAMS_ENV).ok()
}

fn find_best_index_before_active_cap() {}
fn selected_candidate_index_before_active_cap() {}
fn selected_candidate_index_after_active_cap() {}
fn active_stream_cap_moved() {}
fn active_stream_cap_saturated() {}
fn assigned_stream_capped_selected_index() {}
fn assigned_stream_cap_moved() {}
fn assigned_stream_cap_saturated() {}
fn selected_before_assigned_cap_assigned_streams() {}
fn selected_assigned_streams() {}

fn torfast_exit_same_isolation_target(usage: &TargetTunnelUsage) -> Option<usize> {
    if !matches!(usage, TargetTunnelUsage::Exit { .. }) {
        return None;
    }
    let _env = TORFAST_EXIT_SAME_ISOLATION_TARGET_ENV;
    torfast_env_usize_in_range(None, None)
}

fn torfast_exit_same_isolation_min_assigned_streams() -> u64 {
    TORFAST_EXIT_SAME_ISOLATION_MIN_ASSIGNED_STREAMS_DEFAULT
}

fn torfast_exit_same_isolation_require_bad_health() -> bool {
    false
}

fn torfast_exit_same_isolation_prewarm_first_stream() -> bool {
    std::env::var(TORFAST_EXIT_SAME_ISOLATION_PREWARM_FIRST_STREAM_ENV)
        .ok()
        .map(|value| matches!(value.as_str(), "1" | "true"))
        .unwrap_or(false)
}

fn torfast_exit_same_isolation_pending_wait(
    usage: &TargetTunnelUsage,
    same_isolation_target: Option<usize>,
) -> Option<Duration> {
    if same_isolation_target.is_none() || !matches!(usage, TargetTunnelUsage::Exit { .. }) {
        return None;
    }
    std::env::var(TORFAST_EXIT_SAME_ISOLATION_PENDING_WAIT_ENV)
        .ok()
        .and_then(|value| value.parse::<u64>().ok())
        .filter(|value| {
            (TORFAST_EXIT_SAME_ISOLATION_PENDING_WAIT_MIN_MS
                ..=TORFAST_EXIT_SAME_ISOLATION_PENDING_WAIT_MAX_MS)
                .contains(value)
        })
        .map(Duration::from_millis)
}

fn torfast_exit_same_isolation_other_isolation_min(usage: &TargetTunnelUsage) -> Option<usize> {
    if !matches!(usage, TargetTunnelUsage::Exit { .. }) {
        return None;
    }
    std::env::var(TORFAST_EXIT_SAME_ISOLATION_OTHER_ISOLATION_MIN_ENV)
        .ok()
        .and_then(|value| value.parse::<usize>().ok())
        .filter(|value| (1..=TORFAST_EXIT_SAME_ISOLATION_OTHER_ISOLATION_MAX).contains(value))
}

fn torfast_exit_select_prefer_cold_same_isolation() -> bool {
    let _env = TORFAST_EXIT_SELECT_PREFER_COLD_SAME_ISOLATION_ENV;
    torfast_env_flag(None, false)
}

fn torfast_exit_select_prefer_cold_same_isolation_is_enabled(
    usage: &TargetTunnelUsage,
) -> bool {
    torfast_exit_select_health_aware_is_enabled(usage)
        && torfast_exit_select_prefer_cold_same_isolation()
}

const TORFAST_EXIT_SELECT_HEALTHY_OVER_COLD_MIN_ASSIGNED: &str =
    "TORFAST_EXIT_SELECT_HEALTHY_OVER_COLD_MIN_ASSIGNED";
const TORFAST_EXIT_SELECT_HEALTHY_OVER_COLD_MIN_ASSIGNED_MIN: u64 = 0;
const TORFAST_EXIT_SELECT_HEALTHY_OVER_COLD_MIN_ASSIGNED_MAX: u64 = 32;
fn torfast_exit_select_healthy_over_cold_min_assigned(
    usage: &TargetTunnelUsage,
) -> Option<u64> {
    if !torfast_exit_select_load_aware_is_enabled(usage) {
        return None;
    }
    Some(TORFAST_EXIT_SELECT_HEALTHY_OVER_COLD_MIN_ASSIGNED_MIN)
}
fn healthy_over_cold_selected_index() {
    if assignment.assigned_streams < min_assigned {
        return;
    }
    Self::torfast_entry_health_score(assignment).is_some();
    Self::health_aware_beats_assignment(ents, health_selected, assignment_selected, false);
}

const TORFAST_EXIT_SELECT_HEALTHY_OVER_COLD_GUARD_ONLY_MIN_ASSIGNED: &str =
    "TORFAST_EXIT_SELECT_HEALTHY_OVER_COLD_GUARD_ONLY_MIN_ASSIGNED";
const TORFAST_EXIT_SELECT_HEALTHY_OVER_COLD_GUARD_ONLY_MIN_ASSIGNED_ENV: &str =
    "TORFAST_EXIT_SELECT_HEALTHY_OVER_COLD_GUARD_ONLY_MIN_ASSIGNED";
const TORFAST_EXIT_SELECT_HEALTHY_OVER_COLD_GUARD_ONLY_MIN_ASSIGNED_MIN: u64 = 1;
const TORFAST_EXIT_SELECT_HEALTHY_OVER_COLD_GUARD_ONLY_MIN_ASSIGNED_MAX: u64 = 32;
fn torfast_exit_select_healthy_over_cold_guard_only_min_assigned(
    usage: &TargetTunnelUsage,
) -> Option<u64> {
    if !matches!(usage, TargetTunnelUsage::Exit { .. }) {
        return None;
    }
    std::env::var(TORFAST_EXIT_SELECT_HEALTHY_OVER_COLD_GUARD_ONLY_MIN_ASSIGNED_ENV);
    Some(TORFAST_EXIT_SELECT_HEALTHY_OVER_COLD_GUARD_ONLY_MIN_ASSIGNED_MIN)
}

fn torfast_dir_select_spread_is_enabled(usage: &TargetTunnelUsage) -> bool {
    match usage {
        TargetTunnelUsage::Dir => std::env::var(TORFAST_DIR_SELECT_SPREAD_ENV)
            .ok()
            .is_some_and(|value| value == "1"),
        TargetTunnelUsage::DirMicrodesc => true,
        _ => false,
    }
}

const TORFAST_DIR_MICRODESC_PENDING_SPREAD_ENV: &str =
    "TORFAST_DIR_MICRODESC_PENDING_SPREAD";

fn torfast_dir_microdesc_pending_spread_is_enabled(usage: &TargetTunnelUsage) -> bool {
    matches!(usage, TargetTunnelUsage::DirMicrodesc)
        && std::env::var(TORFAST_DIR_MICRODESC_PENDING_SPREAD_ENV)
            .ok()
            .is_some_and(|value| value == "1")
}

fn torfast_should_top_up_same_isolation() -> bool {
    let assigned_stream_pressure =
        selected_assigned_streams > torfast_exit_same_isolation_min_assigned_streams();
    let active_cap_pressure = active_stream_cap_saturated
        && select_max_active_streams
            .is_some_and(|cap| selected_active_streams >= cap);
    let first_stream_prewarm = prewarm_first_stream && selected_assigned_streams == 0;
    let other_isolation_pressure =
        other_isolation_min.is_some_and(|min| exit_incompatible_isolated >= min);
    let effective_target = target
        .saturating_add(usize::from(active_cap_pressure))
        .min(TORFAST_EXIT_SAME_ISOLATION_TARGET_MAX + 1);
    (assigned_stream_pressure
        || active_cap_pressure
        || first_stream_prewarm
        || other_isolation_pressure)
    && (!require_bad_health || selected_has_bad_health)
    && open_candidates + pending_supported_count < effective_target
}
fn torfast_should_wait_for_same_isolation_pending() -> bool {
    let first_stream_prewarm_followup = prewarm_first_stream && selected_assigned_streams > 0;
    open_candidates <= target && first_stream_prewarm_followup
}
select_max_active_streams = select_max_active_streams.unwrap_or(0)
prewarm_first_stream = same_isolation_prewarm_first_stream
let same_isolation_pending_wait =
let same_isolation_pending_wait_pressure =
same_isolation_pending_wait_selected_assigned_streams
open_candidates < target
Action::OpenAfterSameIsolationPendingWait
torfast circuit selection same isolation pending wait
torfast circuit selection same isolation pending wait won
torfast circuit selection same isolation pending wait timer fired
list.get_open_mut(&fallback.id())
Same-isolation pending wait fallback restriction failed
let same_isolation_other_isolation_min = same_isolation_target
let exit_incompatible_isolated = if same_isolation_other_isolation_min.is_some()
torfast_exit_incompatible_isolated_count
exit_incompatible_isolated
other_isolation_min
other_isolation_pressure

fn active_stream_capped_selected_index() {}
fn least_assigned_parallelism_index() {}
fn torfast_entry_active_streams() {}
fn torfast_health_has_active_no_data_idle() {}
fn torfast_preemptive_443_busy_active_after() {}
fn torfast_counts_toward_preemptive_target() {}
fn torfast_preemptive_target_extra_circs() {}
active_streams_started_at
snapshot.active_streams < TORFAST_PREEMPTIVE_443_BUSY_MIN_ACTIVE_STREAMS

assigned_streams
least_assigned_index
select_least_assigned
load_aware_selected_index
least_assigned_index_with_min_spread
least_assigned_index_avoiding_bad_health
torfast_has_unassigned_open_alternate
torfast_should_skip_assigned_dir_microdesc
entry.assigned_streams > 0
torfast_pending_supported_count(usage) > 0
let mut skipped_assigned_dir_microdesc = None;
debug!("torfast dir microdesc pending spread skipped assigned tunnel");
debug!("torfast dir microdesc pending spread used fallback tunnel");
assignment_spread
let select_load_aware = torfast_exit_select_load_aware_is_enabled(usage);
let select_dir_spread = torfast_dir_select_spread_is_enabled(usage);
let same_isolation_target = torfast_exit_same_isolation_target(usage);
let same_isolation_prewarm_first_stream = same_isolation_target;
let low_log_selection_context = torfast_exit_select_low_log_context();
let collect_selection_context =
    tracing::enabled!(tracing::Level::DEBUG) || low_log_selection_context;
let open_support_summary = if collect_selection_context {}
let candidate_assignment_summary = if collect_selection_context {}
let candidate_health_summary = if collect_selection_context {}
if low_log_selection_context {
    info!("torfast circuit selection open")
}
torfast_candidate_health_summary
let select_prefer_cold_same_isolation = torfast_exit_select_prefer_cold_same_isolation_is_enabled(usage, same_isolation_target)
let selected_candidate_index_before_active_cap = if select_dir_spread {}
OpenEntry::find_best_index_before_active_cap_with_guard_context(
    &open,
    usage,
    parallelism,
    select_prefer_cold_same_isolation,
)
find_best_index_before_active_cap_with_guard_context
find_best_index_before_guard_only
OpenEntry::active_stream_capped_selected_index(
if select_dir_spread {
    OpenEntry::least_assigned_index(&open)
}
|| torfast_dir_select_spread_is_enabled(usage)
OpenEntry::find_best_index(&open, usage, parallelism)
let bad_health_hedge_after = torfast_exit_select_bad_health_hedge_is_enabled(usage)
|| bad_health_hedge_after.is_some()
load_aware_assignment_candidate_index
load_aware_min_assignment_spread
avoid_bad_health_unknown_fallback
Self::torfast_entry_has_good_health(entry)
if !avoid_bad_health_unknown_fallback
!Self::torfast_entry_has_bad_health(entry)
entry.assigned_streams == 0
open_support_summary
torfast_support_reason
health_aware_best_index
health_aware_beats_assignment
cold_assignment_should_beat_health
torfast_health_score
torfast_health_has_recent_stream_idle
select_health_aware
health_aware_min_assigned
if health_aware_min_assigned.is_some_and(|min_assigned| ents[assigned_selected].assigned_streams < min_assigned)
select_health_aware_min_assigned
select_avoid_bad_health_unknown_fallback
select_prefer_cold_same_isolation
select_healthy_over_cold_min_assigned
healthy_over_cold_candidate_index
select_healthy_over_cold_guard_only_min_assigned
healthy_over_cold_guard_only_candidate_index
health_aware_candidate_index
health_aware_assignment_score_bps
selected_health_score_bps
selected_health_max_gap_ms
selected_health_age_ms
torfast_pending_supported_count
open_candidates + pending_supported_count < target
pending_id
torfast_force_info_lifecycle: bool
torfast_force_info_lifecycle: false
plan.torfast_force_info_lifecycle = true
if torfast_force_info_lifecycle
    || pending_age_ms >= TORFAST_SLOW_TUNNEL_BUILD_LOG_MS
Action::OpenAfterBadHealthHedge

fn torfast_exit_pending_hedge_is_enabled(usage: &TargetTunnelUsage) -> Option<Duration> {
    match usage {
        TargetTunnelUsage::Exit { .. } => torfast_exit_pending_hedge_after(),
        _ => None,
    }
}

let pending_hedge_delay = Some(Duration::from_millis(1500));
info!(
    pending_candidates,
    "torfast circuit selection pending hedge"
);
info!(
    pending_candidates,
    "torfast circuit selection pending hedge failed"
);
info!(
    delay_ms = delay.as_millis(),
    "torfast circuit selection pending hedge timer fired"
);
info!(
    delay_ms = delay.as_millis(),
    "torfast circuit selection build hedge timer fired"
);
info!(
    delay_ms = delay.as_millis(),
    plans = plans.len(),
    "torfast circuit selection build hedge"
);
debug!("torfast circuit selection same isolation topup");
debug!("torfast circuit selection same isolation topup failed");
debug!("torfast circuit selection bad health hedge");
debug!("torfast circuit selection bad health hedge won");
debug!("torfast circuit selection bad health hedge timer fired");
debug!("torfast circuit selection build complete");
debug!("torfast circuit selection build failed");
debug!("torfast circuit selection build canceled");
const TORFAST_SLOW_TUNNEL_BUILD_LOG_MS: u128 = 5_000;
pending_age_ms >= TORFAST_SLOW_TUNNEL_BUILD_LOG_MS
usage_kind
info!(
tunnel_unique_id = %tunnel_unique_id
""",
    "circmgr_usage": """
enum TargetTunnelUsage {
    Dir,
    DirMicrodesc,
}
enum SupportedTunnelUsage {
    Dir,
}
match self {
    TargetTunnelUsage::Dir | TargetTunnelUsage::DirMicrodesc => {
        Ok((path, SupportedTunnelUsage::Dir, Some(mon), Some(usable)))
    }
}
match (self, target) {
    (Dir, TargetTunnelUsage::Dir | TargetTunnelUsage::DirMicrodesc) => "supported",
}
supported.len() >= circs.saturating_add(extra_cap)
""",
    "tor_hsclient_connect": """
const TORFAST_HS_INTRO_REND_OVERLAP_ENV: &str = "TORFAST_HS_INTRO_REND_OVERLAP";
const TORFAST_HS_REND_PREBUILD_BEFORE_DESC_ENV: &str =
    "TORFAST_HS_REND_PREBUILD_BEFORE_DESC";
const TORFAST_HS_INTRO_CIRCUIT_HEDGE_MS_ENV: &str = "TORFAST_HS_INTRO_CIRCUIT_HEDGE_MS";
const TORFAST_HS_DESC_SHARED_CACHE_ENV: &str = "TORFAST_HS_DESC_SHARED_CACHE";
const TORFAST_HS_INTRO_CIRCUIT_HEDGE_MIN_MS: u64 = 500;
const TORFAST_HS_INTRO_CIRCUIT_HEDGE_MAX_MS: u64 = 60_000;
struct TorfastHsDescSharedCacheKey { hs_blind_id: HsBlindId }
fn torfast_hs_intro_rend_overlap_from_env_value() {}
fn torfast_hs_intro_rend_overlap() {}
fn torfast_hs_rend_prebuild_before_desc_from_env_value() {}
fn torfast_hs_rend_prebuild_before_desc() {}
fn torfast_hs_desc_shared_cache_from_env_value() {}
fn torfast_hs_desc_shared_cache_enabled() {}
fn torfast_hs_intro_circuit_hedge_ms_from_env_value() {}
fn torfast_hs_intro_circuit_hedge_delay() {}
fn torfast_hs_desc_shared_cache_get() {}
fn torfast_hs_desc_shared_cache_store() {}
Arc::as_ptr(&self.secret_keys.keys);
refetch.is_none();
data.insert(shared_desc);
desc.clone();
desc: DataHsDesc;
ipts: DataIpts;
hsdirs: DataHsDirs;
saved_rendezvous.is_none();
futures::join!(descriptor, rendezvous);
futures::join!(establish_rendezvous, obtain_intro_circuit);
self.establish_rendezvous();
self.obtain_intro_circuit(ipt, hs_timing_started);
intro_rend_connect(desc, &mut data.ipts, prebuilt_rendezvous);
intro_rend_connect(desc, &mut data.ipts, None);
self.exchange_introduce_with_circ();
fn obtain_intro_circuit_with_hedge() {}
torfast hs timing intro circuit hedge launched
torfast hs timing intro circuit hedge won
torfast hs timing descriptor shared cache hit
torfast hs timing descriptor shared cache store
self.obtain_intro_circuit_once();
m_get_or_launch_intro();
""",
    "circmgr_build": """
const TORFAST_SLOW_CHANNEL_OPEN_LOG_MS: u128 = 1_000;

fn torfast_channel_usage_kind() {}
fn torfast_channel_provenance_kind() {}

async fn open_channel() {
    let channel_open_started = Instant::now();
    let result = chanmgr.get_or_launch(target, usage).await;
    let elapsed_ms = channel_open_started.elapsed().as_millis();
    let usage_kind = torfast_channel_usage_kind(usage);
    match &result {
        Ok((_chan, provenance)) => {
            let provenance = torfast_channel_provenance_kind(*provenance);
            if elapsed_ms >= TORFAST_SLOW_CHANNEL_OPEN_LOG_MS {
                info!(
                    elapsed_ms,
                    usage_kind,
                    provenance,
                    outcome = "ok",
                    "torfast channel open timing"
                );
            }
        }
        Err(cause) => {
            info!(
                elapsed_ms,
                usage_kind,
                error_kind = ?cause.kind(),
                outcome = "err",
                "torfast channel open timing"
            );
        }
    }
}
""",
    "circmgr_impls": """
	use tor_proto::client::circuit::CircuitHealthSnapshot;
	const TORFAST_DEFAULT_EXIT_SELECT_PARALLELISM: usize = 1;
	const TORFAST_EXIT_SELECT_PARALLELISM_ENV: &str = "TORFAST_EXIT_SELECT_PARALLELISM";
	const TORFAST_DEFAULT_EXIT_LAUNCH_PARALLELISM: usize = 1;
	const TORFAST_EXIT_LAUNCH_PARALLELISM_ENV: &str = "TORFAST_EXIT_LAUNCH_PARALLELISM";

fn circuit_health_snapshot(&self) -> Option<CircuitHealthSnapshot> {
    ClientTunnel::circuit_health_snapshot(self).ok()
}

	fn torfast_exit_select_parallelism() -> usize {
	    std::env::var(TORFAST_EXIT_SELECT_PARALLELISM_ENV)
	        .ok()
	        .and_then(|value| value.parse::<usize>().ok())
	        .filter(|value| (1..=8).contains(value))
	        .unwrap_or(TORFAST_DEFAULT_EXIT_SELECT_PARALLELISM)
	}

	fn torfast_exit_launch_parallelism() -> usize {
	    std::env::var(TORFAST_EXIT_LAUNCH_PARALLELISM_ENV)
	        .ok()
	        .and_then(|value| value.parse::<usize>().ok())
	        .filter(|value| (1..=4).contains(value))
	        .unwrap_or(TORFAST_DEFAULT_EXIT_LAUNCH_PARALLELISM)
	}

	fn launch_parallelism(&self, spec: &TargetTunnelUsage) -> usize {
	    match spec {
	        TargetTunnelUsage::Dir | TargetTunnelUsage::DirMicrodesc => 3,
	        TargetTunnelUsage::Exit { .. } => torfast_exit_launch_parallelism(),
	        _ => 1,
	    }
	}

	fn select_parallelism(&self, spec: &TargetTunnelUsage) -> usize {
	    match spec {
        TargetTunnelUsage::Exit { .. } => torfast_exit_select_parallelism(),
        _ => self.launch_parallelism(spec),
    }
}
""",
    "dirmgr_bootstrap": """
const TORFAST_DIR_INCREMENTAL_MICRODESCS_ENV: &str = "TORFAST_DIR_INCREMENTAL_MICRODESCS";
const TORFAST_DIR_MICRODESC_EARLY_USABLE_NOTIFY_ENV: &str =
    "TORFAST_DIR_MICRODESC_EARLY_USABLE_NOTIFY";
const TORFAST_DIR_MICRODESC_HEDGE_MS_ENV: &str = "TORFAST_DIR_MICRODESC_HEDGE_MS";
const TORFAST_DIR_MICRODESC_RETRY_IDS_PER_REQUEST_ENV: &str =
    "TORFAST_DIR_MICRODESC_RETRY_IDS_PER_REQUEST";
const TORFAST_DIR_MICRODESC_RETRY_DELAY_MAX_MS_ENV: &str =
    "TORFAST_DIR_MICRODESC_RETRY_DELAY_MAX_MS";
const TORFAST_DIR_MICRODESC_EARLY_RETRY_ON_PARTIAL_ENV: &str =
    "TORFAST_DIR_MICRODESC_EARLY_RETRY_ON_PARTIAL";
    "TORFAST_DIR_MICRODESC_PARTIAL_RETRY_CHUNKING";
const MIN_MICRODESC_HEDGE_MS: u64 = 2_000;
const MAX_MICRODESC_HEDGE_MS: u64 = 10_000;
const MIN_MICRODESC_RETRY_IDS_PER_REQUEST: usize = 64;
const MAX_MICRODESC_RETRY_IDS_PER_REQUEST: usize = 500;
const MIN_MICRODESC_RETRY_DELAY_MAX_MS: u64 = 250;
const MAX_MICRODESC_RETRY_DELAY_MAX_MS: u64 = 2_000;

fn torfast_missing_docs_are_microdescs(missing: &[DocId]) -> bool {
    !missing.is_empty()
        && missing.iter().all(|doc| matches!(doc, DocId::Microdesc(_)))
}

fn torfast_dir_incremental_microdescs_enabled(missing: &[DocId]) -> bool {
    torfast_missing_docs_are_microdescs(missing)
        && std::env::var(TORFAST_DIR_INCREMENTAL_MICRODESCS_ENV)
            .ok()
            .is_some_and(|value| value == "1")
}

fn torfast_dir_microdesc_early_usable_notify_enabled(missing: &[DocId]) -> bool {
    torfast_missing_docs_are_microdescs(missing)
        && std::env::var(TORFAST_DIR_MICRODESC_EARLY_USABLE_NOTIFY_ENV)
            .ok()
            .is_some_and(|value| value == "1")
}

fn torfast_microdesc_hedge_delay(request: &ClientRequest) -> Option<Duration> {
    if !matches!(request, ClientRequest::Microdescs(_)) {
        return None;
    }
    std::env::var(TORFAST_DIR_MICRODESC_HEDGE_MS_ENV)
        .ok()
        .filter(|value| {
            (MIN_MICRODESC_HEDGE_MS..=MAX_MICRODESC_HEDGE_MS)
        })
        .map(Duration::from_millis)
}

fn torfast_microdesc_retry_ids_per_request() -> Option<usize> {
    std::env::var(TORFAST_DIR_MICRODESC_RETRY_IDS_PER_REQUEST_ENV)
        .ok()
        .filter(|value| {
            (MIN_MICRODESC_RETRY_IDS_PER_REQUEST..=MAX_MICRODESC_RETRY_IDS_PER_REQUEST)
        })
}

fn torfast_microdesc_retry_delay_max() -> Option<Duration> {
    std::env::var(TORFAST_DIR_MICRODESC_RETRY_DELAY_MAX_MS_ENV)
        .ok()
        .filter(|value| {
            (MIN_MICRODESC_RETRY_DELAY_MAX_MS..=MAX_MICRODESC_RETRY_DELAY_MAX_MS)
        })
}

fn torfast_microdesc_early_retry_on_partial_enabled(missing: &[DocId]) -> bool {
    torfast_missing_docs_are_microdescs(missing)
        && std::env::var(TORFAST_DIR_MICRODESC_EARLY_RETRY_ON_PARTIAL_ENV)
            .ok()
            .is_some_and(|value| value == "1")
}

fn torfast_microdesc_partial_retry_chunking_enabled(missing: &[DocId]) -> bool {
    torfast_missing_docs_are_microdescs(missing)
        && std::env::var(TORFAST_DIR_MICRODESC_PARTIAL_RETRY_CHUNKING_ENV)
            .ok()
            .is_some_and(|value| value == "1")
}

fn torfast_microdesc_partial_retry_chunking_signal(missing: &[DocId]) -> bool {
    torfast_microdesc_partial_retry_chunking_enabled(missing)
        && response.error().is_some()
    info!("torfast microdescriptor partial retry chunking signal");
}

fn fetch_single_maybe_hedged() {
    info!("torfast microdescriptor hedge started");
    dir_fetch_outcome_is_clean();
}

async fn download_attempt_incremental_microdescs() {
    if state.is_ready(Readiness::Usable) {
        info!("torfast incremental microdescriptor fetch reached usable directory");
    }
}

fn notify_usable_if_ready() {
    if state.is_ready(Readiness::Usable) {
        info!("torfast microdescriptor early usable notification");
    }
}

async fn download_attempt_microdescs_early_usable_notify() {
    while let Some(response) = responses.next().await {
        torfast_microdesc_partial_retry_chunking_signal(missing);
        n_errors += 1;
        notify_usable_if_ready();
    }
}

async fn download_attempt() {
    let download_error_count = 1;
    let microdesc_ids_per_request =
        microdesc_ids_per_request.filter(|_| torfast_missing_docs_are_microdescs(&missing));
    info!("torfast microdescriptor retry request chunking enabled");
}

async fn fetch_multiple(missing: &[DocId]) {
    torfast_microdesc_partial_retry_chunking_signal(missing);
    download_error_count += 1;
    useful_responses.push((request, response));
    if torfast_microdesc_early_retry_on_partial_enabled(missing) {
        if response.error().is_some() {
            info!("torfast microdescriptor early retry on partial");
        }
    }
}

fn should_enable_microdesc_retry_chunking() {}

async fn download() {
    let mut retry_microdesc_chunking_allowed = false;
    if retry_microdesc_chunking_allowed {
        torfast_microdesc_retry_ids_per_request();
    }
    if retry_microdesc_chunking_allowed && torfast_missing_docs_are_microdescs(&state.missing_docs()) {
        if let Some(max_delay) = torfast_microdesc_retry_delay_max() {
            real_delay = real_delay.min(max_delay);
            info!("torfast microdescriptor retry delay capped");
        }
    }
}
""",
    "dirmgr_docid": """
const TORFAST_DIR_MICRODESC_IDS_PER_REQUEST_ENV: &str = "TORFAST_DIR_MICRODESC_IDS_PER_REQUEST";
const DEFAULT_DOCS_PER_REQUEST: usize = 500;
const MIN_MICRODESC_IDS_PER_REQUEST: usize = 64;
const MAX_MICRODESC_IDS_PER_REQUEST: usize = DEFAULT_DOCS_PER_REQUEST;

fn torfast_microdesc_ids_per_request() -> usize {
    std::env::var(TORFAST_DIR_MICRODESC_IDS_PER_REQUEST_ENV)
        .ok()
        .and_then(|value| value.parse::<usize>().ok())
        .and_then(bounded_microdesc_ids_per_request)
        .unwrap_or(DEFAULT_DOCS_PER_REQUEST)
}

fn bounded_microdesc_ids_per_request() {
    (MIN_MICRODESC_IDS_PER_REQUEST..=MAX_MICRODESC_IDS_PER_REQUEST)
}

fn split_for_download() {
    let n = microdesc_ids_per_request
        .unwrap_or_else(torfast_microdesc_ids_per_request);
}

fn split_for_download_with_microdesc_limit() {}
""",
    "tor_dirclient": """
const TORFAST_DIRCLIENT_READ_TIMEOUT_ENV: &str = "TORFAST_DIRCLIENT_READ_TIMEOUT_MS";
const TORFAST_DIRCLIENT_PROGRESS_READ_TIMEOUT_ENV: &str =
    "TORFAST_DIRCLIENT_PROGRESS_READ_TIMEOUT_MS";
const TORFAST_DIRCLIENT_MICRODESC_BODY_MAX_ENV: &str =
    "TORFAST_DIRCLIENT_MICRODESC_BODY_MAX_MS";
const TORFAST_DIRCLIENT_MICRODESC_MIN_RATE_ENV: &str =
    "TORFAST_DIRCLIENT_MICRODESC_MIN_RATE_BPS";
const TORFAST_DIRCLIENT_TIMING_LOG_ENV: &str = "TORFAST_DIRCLIENT_TIMING_LOG";
const TORFAST_DIR_MICRODESC_SOURCE_SPREAD_ENV: &str =
    "TORFAST_DIR_MICRODESC_SOURCE_SPREAD";
const DEFAULT_DIRCLIENT_READ_TIMEOUT: Duration = Duration::from_secs(10);
const MIN_DIRCLIENT_READ_TIMEOUT_MS: u64 = 2_000;
const MAX_DIRCLIENT_READ_TIMEOUT_MS: u64 = 10_000;
const MIN_MICRODESC_MIN_RATE_BPS: u64 = 32 * 1024;
const MAX_MICRODESC_MIN_RATE_BPS: u64 = 256 * 1024;
const MICRODESC_MIN_RATE_AFTER: Duration = Duration::from_secs(7);

fn dirclient_read_timeout() -> Duration {
    std::env::var(TORFAST_DIRCLIENT_READ_TIMEOUT_ENV)
        .ok()
        .filter(|value| {
            (MIN_DIRCLIENT_READ_TIMEOUT_MS..=MAX_DIRCLIENT_READ_TIMEOUT_MS)
        })
        .unwrap_or(DEFAULT_DIRCLIENT_READ_TIMEOUT)
}

let read_timeout = dirclient_read_timeout();

fn dirclient_progress_read_timeout() -> Option<Duration> {
    std::env::var(TORFAST_DIRCLIENT_PROGRESS_READ_TIMEOUT_ENV)
        .ok()
        .filter(|value| {
            (MIN_DIRCLIENT_READ_TIMEOUT_MS..=MAX_DIRCLIENT_READ_TIMEOUT_MS)
        })
        .map(Duration::from_millis)
}

fn dirclient_microdesc_body_max() -> Option<Duration> {
    std::env::var(TORFAST_DIRCLIENT_MICRODESC_BODY_MAX_ENV)
        .ok()
        .filter(|value| {
            (MIN_DIRCLIENT_READ_TIMEOUT_MS..=MAX_DIRCLIENT_READ_TIMEOUT_MS)
        })
        .map(Duration::from_millis)
}

fn dirclient_microdesc_min_rate_bps() -> Option<u64> {
    std::env::var(TORFAST_DIRCLIENT_MICRODESC_MIN_RATE_ENV)
        .ok()
        .filter(|value| {
            (MIN_MICRODESC_MIN_RATE_BPS..=MAX_MICRODESC_MIN_RATE_BPS)
        })
}

let progress_read_timeout = dirclient_progress_read_timeout();
let body_start = Instant::now();
let microdesc_body_max = if request_kind == "microdesc" && partial_ok {
    dirclient_microdesc_body_max()
} else {
    None
};
let microdesc_min_rate_bps = if request_kind == "microdesc" && partial_ok {
    dirclient_microdesc_min_rate_bps()
} else {
    None
};

let mut read_deadline = if let Some(progress_read_timeout) = progress_read_timeout {
    progress_read_timeout
} else {
    read_timeout
};
if let Some(microdesc_body_max) = microdesc_body_max {
    if let Some(remaining) = microdesc_body_max.checked_sub(body_start.elapsed()) {
        read_deadline = read_deadline.min(remaining);
    }
}
let elapsed = body_start.elapsed();
if elapsed >= MICRODESC_MIN_RATE_AFTER {
    if rate_bps < u128::from(min_rate_bps) {}
}
runtime.timeout(read_deadline, stream.read(buf)).await;
struct DirclientBodyTiming;
let body_read_calls = 1;
let body_first_byte_ms = 1;
let body_last_byte_ms = 2;
let body_max_read_gap_ms = 1;
let body_timeout_after_last_byte_ms = 0;
let microdesc_body_max_ms = 0;
let microdesc_min_rate_bps = 0;
let microdesc_min_rate_after_ms = 7000;
let body_avg_rate_bps = 1;
let body_eof = true;
let source_circ = source.unique_circ_id().to_string().replace(' ', "~");
timing_start: Instant
timing.note_timeout(timing_start);
timing.note_read(timing_start, written_in_this_loop);

fn dirclient_timing_log_enabled() -> bool {
    std::env::var(TORFAST_DIRCLIENT_TIMING_LOG_ENV)
        .ok()
        .is_some_and(|value| value == "1")
}

fn dirclient_microdesc_source_spread_enabled() -> bool {
    std::env::var(TORFAST_DIR_MICRODESC_SOURCE_SPREAD_ENV)
        .ok()
        .is_some_and(|value| value == "1")
}

if request_kind == Some("microdesc") {
    circ_mgr.get_or_launch_dir_microdesc(dirinfo).await?;
}

fn dirclient_request_kind(path: &str) -> &'static str {
    "microdesc"
}

fn log_dirclient_timing() {
    if !enabled {
        return;
    }
    info!("torfast dirclient timing");
}
""",
    "tor_proto_client": """
	pub fn circuit_health_snapshot(&self) -> Result<circuit::CircuitHealthSnapshot> {
	    self.as_single_circ()?.health_snapshot()
	}
	fn note_stream_terminal_idle(&self) {}
	fn note_stream_active_opened(&self) {}
	fn note_stream_active_closed(&self) {}
	""",
    "tor_proto_circuit": """
pub struct CircuitHealthSnapshot {
    pub relay_data_cells: u64,
    pub relay_data_bytes: u64,
    pub max_relay_data_gap: Option<Duration>,
	    pub stream_terminal_idle_events: u64,
	    pub max_stream_terminal_idle: Option<Duration>,
	    pub last_stream_terminal_idle_at: Option<Instant>,
	    pub active_streams: u64,
	    pub max_active_streams: u64,
	    pub active_streams_started_at: Option<Instant>,
	    pub last_relay_data_at: Option<Instant>,
	}

		fn note_relay_data(&mut self, now: Instant, data_len: usize) {}
	fn note_stream_terminal_idle(&mut self, idle: Duration) {}
	fn note_stream_active_opened(&mut self) {}
	fn note_stream_active_closed(&mut self) {}
	pub fn circuit_health_snapshot(&self) -> Result<CircuitHealthSnapshot> {}
""",
    "tor_proto_circuit_circhop": """
const TORFAST_STREAM_LIFECYCLE_LOG_ENV: &str = "TORFAST_STREAM_LIFECYCLE_LOG";

fn torfast_stream_lifecycle_log_enabled() -> bool {
    std::env::var(TORFAST_STREAM_LIFECYCLE_LOG_ENV).ok().unwrap_or(false)
}

if torfast_stream_lifecycle_log_enabled() {
    info!(delivery = "sent", "torfast stream lifecycle");
}
info!(
    channel_circ_id = 2147483650,
    channel_queue_count_available = true,
    channel_queue_after_cells = 1,
    circuit_sender_queue_after_cells = 0,
    delivery = "channel_queued",
    "torfast stream lifecycle"
);
info!(delivery = "delivered", "torfast stream lifecycle");
info!(delivery = "stream_gone", "torfast stream lifecycle");
info!(delivery = "queue_full", "torfast stream lifecycle");
""",
    "tor_proto_reactor_circuit": """
const TORFAST_CIRCUIT_CONGESTION_LOG_ENV: &str = "TORFAST_CIRCUIT_CONGESTION_LOG";
const TORFAST_STREAM_SCHEDULER_LOG_ENV: &str = "TORFAST_STREAM_SCHEDULER_LOG";

fn torfast_circuit_congestion_log_enabled() -> bool {
    std::env::var(TORFAST_CIRCUIT_CONGESTION_LOG_ENV).ok().unwrap_or(false)
}

fn torfast_stream_scheduler_log_enabled() -> bool {
    std::env::var(TORFAST_STREAM_SCHEDULER_LOG_ENV).ok().unwrap_or(false)
}

if relay_cmd == RelayCmd::DATA {
    self.mutable.note_relay_data(now, data_len.into());
}

if torfast_circuit_congestion_log_enabled() {
    info!("torfast circuit congestion sendme sent");
}

if torfast_circuit_congestion_log_enabled() {
    info!("torfast circuit congestion sendme received");
}
""",
    "tor_proto_reactor_circuit_circhop": """
if super::torfast_circuit_congestion_log_enabled() {
    info!("torfast circuit congestion scheduler hop blocked");
}

if super::torfast_stream_scheduler_log_enabled() {
    info!("torfast stream scheduler hop blocked");
    info!("torfast stream scheduler stream closed");
    info!("torfast stream scheduler picked");
}
""",
    "tor_proto_channel_reactor": """
if torfast_stream_lifecycle_log_enabled() {
    info!(
        channel_reactor_queue_count_available = true,
        channel_reactor_queue_after_cells = 1,
        delivery = "channel_flushed",
        "torfast channel flush"
    );
}
""",
    "tor_proto_data_stream": """
TORFAST_STREAM_READY_DATA_COALESCE_BYTES
fn torfast_stream_ready_data_coalesce_bytes() -> Option<usize> {}
TORFAST_STREAM_READY_DATA_COALESCE_BYTES_MIN: usize = 498
TORFAST_STREAM_READY_DATA_COALESCE_BYTES_MAX: usize = 64 * 1024
std::env::var(TORFAST_STREAM_READY_DATA_COALESCE_BYTES_ENV)
if let Some(max_bytes) = torfast_stream_ready_data_coalesce_bytes() {}
while imp.should_ready_coalesce_data(max_bytes) {}
self.pending_bytes() < max_bytes && self.s.next_queued_msg_is_data()
TORFAST_STREAM_SLOW_TRANSFER_LOG_MS: u128 = 5_000
transfer_ms >= TORFAST_STREAM_SLOW_TRANSFER_LOG_MS || !returned_eof
torfast_user_read_bytes
torfast_data_cells
torfast_note_stream_terminal_idle
torfast_note_stream_active_opened
torfast_note_stream_active_closed
debug!(
    first_data_after_start_ms,
    transfer_ms,
    idle_after_last_data_ms,
    max_data_gap_ms,
    relay_data_bytes,
    user_read_bytes = self.torfast_user_read_bytes,
    data_cells = self.torfast_data_cells,
    error_kind = %torfast_reader_error_kind(error),
    returned_eof,
    "torfast stream receiver terminal"
);
info!(
    first_data_after_start_ms,
    transfer_ms,
    idle_after_last_data_ms,
    max_data_gap_ms,
    relay_data_bytes,
    "torfast stream receiver terminal summary"
);
""",
    "tor_proto_stream_raw": """
pub(crate) fn next_queued_msg_is_data(&mut self) -> bool {
    msg.cmd() == RelayCmd::DATA
}
""",
    "socks_proxy": """
SocksCmd::CONNECT
fn interpret_socks_auth() {}
ProvidedIsolation::LegacySocks(auth.clone())
prefs.set_isolation(StreamIsolationKey(conn_isolation, interp.isolation))
prefs.optimistic()
connect_with_prefs(&tor_addr, &prefs)
const SOCKS_CONNECT_SOFT_TIMEOUT_ENV: &str = "TORFAST_SOCKS_CONNECT_SOFT_TIMEOUT_MS";
const SOCKS_CONNECT_SOFT_TIMEOUT_ATTEMPTS_ENV: &str =
    "TORFAST_SOCKS_CONNECT_SOFT_TIMEOUT_ATTEMPTS";
const SOCKS_RELAY_BYTE_TIMING_ENV: &str = "TORFAST_SOCKS_RELAY_BYTE_TIMING";
const SOCKS_TOR_TO_CLIENT_COALESCE_BYTES_ENV: &str =
    "TORFAST_SOCKS_TOR_TO_CLIENT_COALESCE_BYTES";
const SOCKS_PARTIAL_RELAY_IDLE_TIMEOUT_ENV: &str =
    "TORFAST_SOCKS_PARTIAL_RELAY_IDLE_TIMEOUT_MS";
const SOCKS_NO_TOR_BYTE_RELAY_TIMEOUT_ENV: &str =
    "TORFAST_SOCKS_NO_TOR_BYTE_RELAY_TIMEOUT_MS";
const SOCKS_CONNECT_SOFT_TIMEOUT_MIN_MS: u64 = 500;
const SOCKS_CONNECT_SOFT_TIMEOUT_MAX_MS: u64 = 60_000;
const SOCKS_PARTIAL_RELAY_IDLE_TIMEOUT_MIN_MS: u64 = 500;
const SOCKS_PARTIAL_RELAY_IDLE_TIMEOUT_MAX_MS: u64 = 60_000;
const SOCKS_NO_TOR_BYTE_RELAY_TIMEOUT_MIN_MS: u64 = 500;
const SOCKS_NO_TOR_BYTE_RELAY_TIMEOUT_MAX_MS: u64 = 60_000;
const SOCKS_TOR_TO_CLIENT_COALESCE_BYTES_MIN: usize = 498;
const SOCKS_TOR_TO_CLIENT_COALESCE_BYTES_MAX: usize = 64 * 1024;
const SOCKS_CONNECT_RETRY_ATTEMPTS_DEFAULT: usize = 2;
const SOCKS_CONNECT_RETRY_ATTEMPTS_MIN: usize = 1;
const SOCKS_CONNECT_RETRY_ATTEMPTS_MAX: usize = 4;
const SOCKS_SLOW_CONNECT_LOG_MS: u128 = 1_000;
const SOCKS_SLOW_RELAY_LOG_MS: u128 = 5_000;
std::env::var(SOCKS_CONNECT_SOFT_TIMEOUT_ENV)
Err(_) => None
std::env::var(SOCKS_CONNECT_SOFT_TIMEOUT_ATTEMPTS_ENV)
std::env::var(SOCKS_PARTIAL_RELAY_IDLE_TIMEOUT_ENV)
std::env::var(SOCKS_NO_TOR_BYTE_RELAY_TIMEOUT_ENV)
fn torfast_socks_relay_byte_timing() -> bool {}
fn torfast_socks_tor_to_client_coalesce_bytes() -> Option<usize> {}
fn torfast_socks_partial_relay_idle_timeout() -> Option<Duration> {}
fn torfast_socks_no_tor_byte_relay_timeout() -> Option<Duration> {}
std::env::var(SOCKS_RELAY_BYTE_TIMING_ENV)
std::env::var(SOCKS_TOR_TO_CLIENT_COALESCE_BYTES_ENV)
let low_log_socks_timing = torfast_socks_relay_byte_timing()
struct ReadyCoalescingReader
let Some(max_bytes) = this.max_bytes else
return Pin::new(&mut this.inner).poll_read(cx, out)
ReadyCoalescingReader::new(b_reader, tor_to_client_coalesce_bytes)
connect_ms >= SOCKS_SLOW_CONNECT_LOG_MS || low_log_socks_timing
let partial_idle_timeout = if target_kind == "onion" {}
let collect_relay_byte_timing = tracing::enabled!(tracing::Level::DEBUG)
|| low_log_socks_timing
|| partial_idle_timeout.is_some()
|| no_tor_byte_timeout.is_some()
	if target_kind == "onion" {}
	SOCKS_CONNECT_RETRY_ATTEMPTS_DEFAULT
	torfast_socks_connect_soft_timeout_attempts()
	.timeout(soft_timeout, connect_attempt)
	let can_retry_after_timeout = attempt < soft_timeout_attempts;
	(soft_timeout, can_retry_after_timeout)
	Some(connect_attempt.await)
	if connect_ms >= SOCKS_SLOW_CONNECT_LOG_MS {}
if relay_ms >= SOCKS_SLOW_RELAY_LOG_MS || !relay_ok || low_log_socks_timing {}
if !tracing::enabled!(tracing::Level::DEBUG) {}
target_kind == "onion"
let torfast_stream_key = tor_stream.torfast_debug_stream_key()
circ_id = %torfast_circ_id
stream_id = %torfast_stream_id
info!(
	first_client_to_tor_ms
	client_to_tor_eof_ms
	client_to_tor_write_close_ms
	tor_to_client_error_ms
	Pin::new(&mut this.inner).poll_fill_buf(cx)
	Poll::Ready(Ok(buf)) if buf.is_empty() => timing.note_read_eof()
	last_tor_to_client_write_ms
	client_to_tor_write_bytes
	tor_to_client_write_bytes
	"torfast socks timing stream ready"
	"torfast socks timing stream linked"
		"torfast socks timing socks reply sent"
		"torfast socks timing relay finished"
		partial_relay_idle_timeout_ms
		client_to_tor_error_ms
		tor_to_client_write_error_ms
		tor_to_client_write_close_error_ms
		"torfast socks timing partial relay idle timeout"
		tor_to_client_timing.bytes() == 0
		client_to_tor_timing.first_byte_elapsed_ms_or_zero()
		no_tor_byte_relay_timeout_ms
		client_to_tor_eof_ms
		client_to_tor_error_ms
		tor_to_client_write_error_ms
		tor_to_client_write_close_error_ms
		tor_to_client_write_bytes
		"torfast socks timing no tor byte relay timeout"
		std::io::ErrorKind::TimedOut
		copy_error_kind = %torfast_io_error_kind
	copy_error = %torfast_io_error_token
	""",
	}


class ArtiQualityConfigTests(unittest.TestCase):
    def test_accepts_expected_static_quality_sources(self) -> None:
        checks = evaluate_sources(sources=GOOD_SOURCES, help_text="proxy help")

        self.assertTrue(all(check.ok for check in checks))

    def test_rejects_changed_ipv4_subnet_default(self) -> None:
        sources = dict(GOOD_SOURCES)
        sources["config"] = sources["config"].replace("16", "24", 1)

        checks = evaluate_sources(sources=sources, help_text=None)
        failed = [check.name for check in checks if not check.ok]

        self.assertIn("default_ipv4_subnet_family_prefix_is_16", failed)


if __name__ == "__main__":
    unittest.main()
