#!/usr/bin/env python3
"""Compare Tor Browser page screenshots through local Tor SOCKS proxies."""

from __future__ import annotations

import argparse
import base64
from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import platform
import queue
import re
import signal
import shutil
import socket
import statistics
import struct
import subprocess
import sys
import threading
import time
import zipfile
import zlib

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from torfast.browser_startup_seed import (
    DEFAULT_BROWSER_STARTUP_SEED_ROOT,
    apply_seed_to_profile as apply_browser_startup_seed_to_profile,
)


URLS = [
    "https://check.torproject.org/",
    "https://www.torproject.org/",
]


REQUIRED_DEFAULT_PREFS = {
    "browser.privatebrowsing.autostart": True,
    "extensions.torbutton.use_nontor_proxy": False,
    "network.dns.disabled": True,
    "network.http.http3.enable": False,
    "network.proxy.allow_bypass": False,
    "network.proxy.failover_direct": False,
    "network.proxy.no_proxies_on": "",
    "network.proxy.socks_remote_dns": True,
    "privacy.firstparty.isolate": True,
    "privacy.resistFingerprinting": True,
    "privacy.resistFingerprinting.letterboxing": True,
}

DEFAULT_PREF_KEYS = list(REQUIRED_DEFAULT_PREFS)
BROWSER_QUALITY_PREF_KEYS = list(REQUIRED_DEFAULT_PREFS)
ZERO_OFFSET_TIMEZONES = {None, "UTC", "Atlantic/Reykjavik"}

BROWSER_CONNECTION_PREF_KEYS = [
    "network.http.http3.enable",
    "network.http.spdy.enabled",
    "network.http.spdy.enabled.http2",
    "network.http.max-connections",
    "network.http.max-persistent-connections-per-server",
    "network.http.max-persistent-connections-per-proxy",
]

BROWSER_SERIAL_HTTP_PREFS = {
    "network.http.max-connections": 1,
    "network.http.max-persistent-connections-per-server": 1,
    "network.http.max-persistent-connections-per-proxy": 1,
}

TORFAST_BROWSER_ACTIVITY_SANDBOX = "torfast_browser_activity_probe"
BROWSER_ACTIVITY_PROBE_TOPICS = [
    "http-on-modify-request",
    "http-on-before-connect",
    "http-on-examine-response",
    "http-on-stop-request",
]
BROWSER_ACTIVITY_PROBE_LIMIT = 2_000
TORFAST_BROWSER_REQUEST_BLOCKER_SANDBOX = "torfast_browser_request_blocker"
BROWSER_REQUEST_BLOCKER_LIMIT = 400

RUNTIME_PREF_KEYS = [
    "network.proxy.socks",
    "network.proxy.socks_port",
    "network.proxy.socks_remote_dns",
    "network.proxy.type",
]

C_TOR_SOCKS_FLAGS = ["IsolateSOCKSAuth"]

MARIONETTE_PORT = 2828
PROCESS_POLL_INTERVAL_SECONDS = 0.05
DEFAULT_BYTE_TAP_EVENT_LIMIT = 24
BROWSER_NET_MOZ_LOG = "timestamp,nsHttp:5,nsSocketTransport:5,nsHostResolver:3"
BROWSER_NET_LOG_TAIL_LINES = 80
PROXY_SIGNAL_LINE_LIMIT = 1000
PROXY_SIGNAL_SUBSTRINGS = (
    "Got a socks request",
    "Got a circuit for",
    "Got a stream for",
    "Preemptive circuit was created",
    "Spawning reactor",
    "hs conn to",
    "torfast socks timing",
    "torfast socks byte event",
    "torfast stream scheduler",
    "torfast stream receiver already closed",
    "torfast stream receiver no-end close",
    "torfast stream receiver terminal",
    "torfast stream reactor congestion",
    "torfast stream lifecycle",
    "torfast channel flush",
    "torfast circuit congestion",
    "torfast circuit selection",
    "torfast hspool",
    "torfast hs timing",
    "torfast hs client timing",
    "torfast hs state timing",
    "torfast exit client timing",
)
PROXY_ALWAYS_KEEP_SUBSTRINGS = (
    "torfast hspool",
    "torfast hs timing",
    "torfast hs client timing",
    "torfast hs state timing",
    "torfast exit client timing",
)
BOOT_SIGNAL_SUBSTRINGS = (
    "looking for a consensus",
    "downloading certificates for consensus",
    "downloading microdescriptors",
    "marked consensus usable",
    "directory is complete",
    "we have enough information to build circuits",
    "proxy now functional",
    "bootstrapped",
    "directory failure",
    "directory timed out",
    "notdirectory",
    "partial response",
    "partial retry chunking signal",
    "torfast dirclient timing",
    "torfast channel open timing",
    "torfast circuit selection build failed",
    "terminal summary",
    "warn",
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--browser-bin",
        default="tmp/browser/Tor Browser.app/Contents/MacOS/firefox",
    )
    parser.add_argument(
        "--bundled-tor-bin",
        default="tmp/browser/Tor Browser.app/Contents/MacOS/Tor/tor",
    )
    parser.add_argument("--tor-bin", default="upstream/tor/src/app/tor")
    parser.add_argument("--arti-bin", default="upstream/arti/target/release/arti")
    parser.add_argument(
        "--extra-arti-bin",
        action="append",
        default=[],
        metavar="LABEL:PATH",
        help=(
            "add another Arti binary as a same-window profile; label becomes "
            "arti_release_browser_LABEL"
        ),
    )
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--tor-port", type=int, default=19080)
    parser.add_argument("--local-tor-port", type=int, default=19081)
    parser.add_argument("--arti-port", type=int, default=19082)
    parser.add_argument(
        "--skip-bundled-tor",
        action="store_true",
        help="omit the bundled Tor Browser tor profile from this focused run",
    )
    parser.add_argument(
        "--extra-c-tor-conflux-ux",
        action="append",
        default=[],
        choices=("latency", "throughput", "throughput_lowmem"),
        help=(
            "add an extra same-window local C Tor profile that sets the official "
            "ConfluxClientUX option to this value; profile is named "
            "local_c_tor_browser_confluxux_<ux>. Quality-safe: only changes the "
            "requested Conflux latency/throughput tradeoff, not path rules. "
            "Sequential schedule only."
        ),
    )
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument(
        "--post-boot-wait",
        type=float,
        default=0.0,
        help="seconds to wait after measured proxy boot before browser runs",
    )
    parser.add_argument("--window-size", default="1000,1000")
    parser.add_argument("--targets", nargs="*", default=URLS)
    parser.add_argument(
        "--warm-cache",
        action="store_true",
        help="bootstrap each proxy once before the measured browser run",
    )
    parser.add_argument(
        "--share-arti-warm-cache-seed",
        action="store_true",
        help=(
            "for interleaved runs, seed later Arti profiles from the first "
            "warmed Arti cache before their own warmup"
        ),
    )
    parser.add_argument(
        "--compact-output",
        action="store_true",
        help="remove bulky browser profile/HOME dirs after saving JSON evidence",
    )
    parser.add_argument(
        "--browser-startup-seed-root",
        default=str(DEFAULT_BROWSER_STARTUP_SEED_ROOT),
        help=(
            "shared startup-only Tor Browser seed to apply to fresh benchmark "
            "profiles before launch"
        ),
    )
    browser_startup_seed_group = parser.add_mutually_exclusive_group()
    browser_startup_seed_group.add_argument(
        "--browser-startup-seed",
        dest="no_browser_startup_seed",
        action="store_false",
        help=(
            "enable applying the shared startup-only browser seed in "
            "benchmarks; default is off because it is not yet a proven speed win"
        ),
    )
    browser_startup_seed_group.add_argument(
        "--no-browser-startup-seed",
        dest="no_browser_startup_seed",
        action="store_true",
        help="disable applying the shared startup-only browser seed in benchmarks",
    )
    parser.set_defaults(no_browser_startup_seed=True)
    parser.add_argument(
        "--browser-net-log",
        action="store_true",
        help=(
            "lab-only: capture Firefox/Tor Browser network MOZ_LOG files for "
            "resource-to-SOCKS mapping evidence"
        ),
    )
    parser.add_argument(
        "--browser-serial-http-connections",
        action="store_true",
        help=(
            "lab-only proof mode: limit browser HTTP connection concurrency so "
            "resource-to-SOCKS stream joins are unambiguous"
        ),
    )
    parser.add_argument(
        "--browser-max-persistent-connections-per-server",
        type=int,
        help=(
            "lab-only proof mode: override Tor Browser's "
            "network.http.max-persistent-connections-per-server value"
        ),
    )
    parser.add_argument(
        "--browser-block-url-substring",
        action="append",
        dest="browser_block_url_substrings",
        default=[],
        metavar="SUBSTRING",
        help=(
            "lab-only proof mode: cancel browser HTTP(S) requests whose URL "
            "contains this substring; repeat to block multiple requests"
        ),
    )
    parser.add_argument(
        "--schedule",
        choices=("sequential", "interleaved"),
        default="sequential",
        help="sequential runs each profile fully; interleaved rotates profiles in one proxy window",
    )
    parser.add_argument(
        "--interleaved-target-order",
        choices=("fixed", "rotating"),
        default="fixed",
        help=(
            "for interleaved runs, keep target order fixed or rotate target "
            "positions by round"
        ),
    )
    parser.add_argument(
        "--arti-log-level",
        default="info",
        help="Arti proxy log level for measured and warmup runs",
    )
    parser.add_argument(
        "--proxy-log-tail-lines",
        type=int,
        default=200,
        help="proxy log lines to keep after browser runs",
    )
    parser.add_argument(
        "--proxy-run-tail-lines",
        type=int,
        default=0,
        help=(
            "default-off diagnostic: proxy log lines to keep after each "
            "interleaved browser run, including successful runs"
        ),
    )
    parser.add_argument(
        "--arti-socks-relay-byte-timing",
        action="store_true",
        help=(
            "default-off diagnostic: add browser-facing SOCKS relay byte "
            "timing fields to slow or failed low-log Arti relay summaries"
        ),
    )
    parser.add_argument(
        "--arti-socks-partial-relay-idle-timeout-ms",
        type=int,
        help=(
            "lab-only timeout for Arti SOCKS streams that got Tor bytes and "
            "then went idle; default Arti behavior is unchanged when unset"
        ),
    )
    parser.add_argument(
        "--arti-socks-no-tor-byte-relay-timeout-ms",
        type=int,
        help=(
            "lab-only timeout for non-onion Arti SOCKS streams that sent "
            "client bytes but received no Tor bytes; default Arti behavior is unchanged"
        ),
    )
    parser.add_argument(
        "--arti-dirclient-read-timeout-ms",
        type=int,
        help=(
            "lab-only Arti directory read timeout; normal Arti keeps 10s when unset"
        ),
    )
    parser.add_argument(
        "--arti-proxy-buffer-size",
        help='override Arti SOCKS socket send/recv buffers, for example "1 MB"',
    )
    parser.add_argument(
        "--arti-proxy-app-buffer-len",
        type=int,
        help=(
            "lab-only override for Arti proxy application/Tor stream BufReader "
            "capacity in bytes; default Arti behavior is unchanged when unset"
        ),
    )
    parser.add_argument(
        "--extra-arti-proxy-buffer-size",
        action="append",
        default=[],
        help=(
            "start one extra same-window Arti profile with this local SOCKS "
            'socket send/recv buffer size, for example "1 MB"'
        ),
    )
    parser.add_argument(
        "--extra-arti-proxy-app-buffer-len",
        action="append",
        default=[],
        type=int,
        help=(
            "start one extra same-window Arti profile with this proxy "
            "application/Tor stream BufReader capacity in bytes"
        ),
    )
    parser.add_argument(
        "--extra-arti-socks-tor-to-client-coalesce-bytes",
        action="append",
        default=[],
        type=int,
        help=(
            "start one extra same-window Arti profile that coalesces ready "
            "Tor-to-browser SOCKS bytes up to this size before local write"
        ),
    )
    parser.add_argument(
        "--extra-arti-stream-ready-data-coalesce-bytes",
        action="append",
        default=[],
        type=int,
        help=(
            "start one extra same-window Arti profile that drains ready "
            "Tor DATA cells into each local stream read up to this size"
        ),
    )
    parser.add_argument(
        "--arti-stream-scheduler-burst",
        type=int,
        help=(
            "lab-only Arti per-stream DATA burst cap after a stream is established; "
            "default Arti behavior is unchanged when unset"
        ),
    )
    parser.add_argument(
        "--extra-arti-stream-scheduler-burst",
        action="append",
        type=int,
        default=[],
        help=(
            "start one extra same-window Arti profile with this established-stream "
            "DATA burst cap"
        ),
    )
    parser.add_argument(
        "--arti-exit-select-parallelism",
        type=int,
        help="lab override for Arti normal exit open-circuit selection width",
    )
    parser.add_argument(
        "--arti-exit-launch-parallelism",
        type=int,
        help="lab override for Arti normal exit circuit launch width",
    )
    parser.add_argument(
        "--arti-min-exit-circs-for-port",
        type=int,
        help="lab override for Arti preemptive exit circuits per predicted port",
    )
    parser.add_argument(
        "--extra-arti-min-exit-circs-for-port",
        action="append",
        type=int,
        default=[],
        help=(
            "start one extra same-window Arti profile with this preemptive "
            "exit-circuit count per predicted port"
        ),
    )
    parser.add_argument(
        "--extra-arti-preemptive-443-circs",
        action="append",
        type=int,
        default=[],
        help=(
            "start one extra same-window Arti profile with this lab-only "
            "minimum preemptive exit-circuit count for port 443"
        ),
    )
    parser.add_argument(
        "--extra-arti-preemptive-443-burst-min-requests",
        action="append",
        type=int,
        default=[],
        help=(
            "start one extra same-window Arti profile that only escalates "
            "port-443 preemptive circuits during short 443 request bursts"
        ),
    )
    parser.add_argument(
        "--extra-arti-preemptive-443-busy-active-age-ms",
        action="append",
        type=int,
        default=[],
        help=(
            "start one extra same-window Arti profile that treats long-busy "
            "port-443 circuits as temporarily unavailable for preemptive "
            "pool sizing"
        ),
    )
    parser.add_argument(
        "--arti-socks-connect-soft-timeout-ms",
        type=int,
        help=(
            "lab-only soft timeout for non-onion Arti SOCKS CONNECT attempts; "
            "times out one slow attempt and retries instead of racing circuits"
        ),
    )
    parser.add_argument(
        "--arti-socks-connect-soft-timeout-attempts",
        type=int,
        help=(
            "lab-only attempt count for non-onion Arti SOCKS CONNECT soft "
            "timeouts; default Arti behavior is unchanged when unset"
        ),
    )
    parser.add_argument(
        "--arti-socks-connect-hedge-ms",
        type=int,
        help=(
            "lab-only delay before hedging slow non-onion Arti SOCKS CONNECT "
            "attempts; default Arti behavior is unchanged when unset"
        ),
    )
    parser.add_argument(
        "--arti-exit-pending-hedge-ms",
        type=int,
        help=(
            "lab-only hedge for non-onion Arti exit requests waiting on one "
            "old pending exit circuit; launches at most one backup pending circuit"
        ),
    )
    parser.add_argument(
        "--arti-exit-select-load-aware",
        action="store_true",
        help=(
            "lab-only Arti open-exit-circuit selector that prefers the already "
            "eligible circuit with fewer assigned streams"
        ),
    )
    parser.add_argument(
        "--arti-exit-select-health-aware",
        action="store_true",
        help=(
            "lab-only Arti open-exit-circuit selector that uses observed "
            "circuit health inside the load-aware candidate set"
        ),
    )
    parser.add_argument(
        "--arti-exit-select-health-min-move-score-bps",
        type=int,
        help=(
            "lab-only minimum observed circuit health score for moving away "
            "from an unknown assignment-selected circuit"
        ),
    )
    parser.add_argument(
        "--arti-exit-select-avoid-bad-health",
        action="store_true",
        help=(
            "lab-only Arti open-exit-circuit guard that avoids known-bad "
            "recent relay-health candidates inside load-aware selection"
        ),
    )
    parser.add_argument(
        "--arti-exit-select-avoid-bad-health-unknown-fallback",
        action="store_true",
        help=(
            "lab-only extension of the bad-health guard: if the least-used "
            "candidate is known bad, allow a cold or unknown eligible circuit "
            "to beat it"
        ),
    )
    parser.add_argument(
        "--arti-exit-select-bad-health-hedge-ms",
        type=int,
        help=(
            "lab-only bad-health hedge; when an exit circuit has fresh bad "
            "local health, wait this many ms for one same-usage replacement "
            "before falling back"
        ),
    )
    parser.add_argument(
        "--arti-exit-select-bad-health-stream-idle-ms",
        type=int,
        help=(
            "lab-only bad-health signal; treat a circuit as locally bad when "
            "a stream recently ended after this many ms idle after its last "
            "Tor byte"
        ),
    )
    parser.add_argument(
        "--arti-exit-select-bad-health-active-no-data-ms",
        type=int,
        help=(
            "lab-only bad-health signal; treat a circuit as locally bad when "
            "it has active streams but no recent incoming Tor DATA for this "
            "many ms"
        ),
    )
    parser.add_argument(
        "--arti-exit-select-max-active-streams",
        type=int,
        help=(
            "lab-only open-circuit selector cap; when the selected exit circuit "
            "already has this many live streams, choose another eligible open "
            "circuit below the cap if one exists"
        ),
    )
    parser.add_argument(
        "--arti-exit-select-max-assigned-streams",
        type=int,
        help=(
            "lab-only load-aware selector cap; when the selected exit circuit "
            "already has this many assigned streams, choose another eligible "
            "open circuit below the cap if one exists"
        ),
    )
    parser.add_argument(
        "--arti-exit-select-min-assignment-spread",
        type=int,
        help=(
            "lab-only guardrail for load-aware exit selection; only move away "
            "from the normal first eligible circuit when assigned-stream "
            "spread is at least this value"
        ),
    )
    parser.add_argument(
        "--arti-exit-select-healthy-over-cold-min-assigned",
        type=int,
        help=(
            "lab-only load-aware selector guard; when the assignment-selected "
            "exit circuit is cold and has at least this many assigned streams, "
            "use a proven healthier eligible open circuit if one exists"
        ),
    )
    parser.add_argument(
        "--arti-exit-select-healthy-over-cold-guard-only-min-assigned",
        type=int,
        help=(
            "lab-only selector guard; keep normal exit selection unless the "
            "selected circuit is cold, has at least this many assigned streams, "
            "and a proven healthier eligible open circuit exists"
        ),
    )
    parser.add_argument(
        "--arti-exit-same-isolation-target",
        type=int,
        help=(
            "lab-only Arti top-up target for already active exit stream "
            "isolation groups; preserves stream isolation"
        ),
    )
    parser.add_argument(
        "--arti-hs-rend-prebuild-before-desc",
        action="store_true",
        help=(
            "enable the hidden-service rendezvous prebuild-before-descriptor "
            "path on the main Arti profile"
        ),
    )
    parser.add_argument(
        "--extra-arti-exit-select-parallelism",
        action="append",
        type=int,
        default=[],
        help=(
            "start one extra Arti profile with this exit selection width; "
            "repeat for more same-window A/B profiles"
        ),
    )
    parser.add_argument(
        "--extra-arti-exit-launch-parallelism",
        action="append",
        type=int,
        default=[],
        help=(
            "start one extra Arti profile with this exit launch width; "
            "repeat for more same-window A/B profiles"
        ),
    )
    parser.add_argument(
        "--extra-arti-hspool-launch-parallelism",
        action="append",
        type=int,
        default=[],
        help=(
            "start one extra Arti profile with this hidden-service pool "
            "background launch width; repeat for more same-window A/B profiles"
        ),
    )
    parser.add_argument(
        "--extra-arti-hspool-background-start-delay-ms",
        action="append",
        type=int,
        default=[],
        help=(
            "start one extra Arti profile with this hidden-service pool "
            "background startup delay in ms; repeat for more same-window A/B profiles"
        ),
    )
    parser.add_argument(
        "--extra-arti-hspool-guarded-stem-target",
        action="append",
        type=int,
        default=[],
        help=(
            "start one extra Arti profile with this hidden-service guarded "
            "stem pool target; repeat for more same-window A/B profiles"
        ),
    )
    parser.add_argument(
        "--extra-arti-hspool-guarded-stem-target-defer-post-bootstrap",
        action="append",
        type=int,
        default=[],
        help=(
            "start one extra Arti profile with this hidden-service guarded "
            "stem target, but keep cold boot pinned to one guarded circuit "
            "until bootstrap settles; repeat for more same-window A/B profiles"
        ),
    )
    parser.add_argument(
        "--extra-arti-hspool-on-demand-grace-ms",
        action="append",
        type=int,
        default=[],
        help=(
            "start one extra Arti profile with this hidden-service pool "
            "on-demand grace wait in ms; repeat for more same-window A/B profiles"
        ),
    )
    parser.add_argument(
        "--extra-arti-hspool-on-demand-race-ms",
        action="append",
        type=int,
        default=[],
        help=(
            "start one extra Arti profile that launches on demand immediately "
            "while racing a ready hidden-service pool circuit for this many ms"
        ),
    )
    parser.add_argument(
        "--extra-arti-hs-intro-rend-overlap",
        action="store_true",
        help=(
            "start one extra Arti profile with lab-only hidden-service "
            "intro/rendezvous setup overlap"
        ),
    )
    parser.add_argument(
        "--extra-arti-hs-rend-prebuild-before-desc",
        action="store_true",
        help=(
            "start one extra Arti profile that prebuilds the normal "
            "hidden-service rendezvous before descriptor fetch finishes"
        ),
    )
    parser.add_argument(
        "--extra-arti-hs-desc-shared-cache",
        action="store_true",
        help=(
            "start one extra Arti profile with lab-only descriptor sharing "
            "across same-onion same-key hidden-service state records"
        ),
    )
    parser.add_argument(
        "--extra-arti-hs-intro-circuit-hedge-ms",
        action="append",
        type=int,
        default=[],
        help=(
            "start one extra Arti profile that hedges hidden-service intro "
            "circuit acquisition after this many ms; repeat for more profiles"
        ),
    )
    parser.add_argument(
        "--extra-arti-socks-connect-soft-timeout-ms",
        action="append",
        type=int,
        default=[],
        help=(
            "start one extra Arti profile with this non-onion SOCKS CONNECT "
            "soft timeout; repeat for more same-window A/B profiles"
        ),
    )
    parser.add_argument(
        "--extra-arti-socks-connect-soft-timeout-attempts",
        action="append",
        type=int,
        default=[],
        help=(
            "start one extra Arti profile with this non-onion SOCKS CONNECT "
            "soft-timeout attempt count; repeat for more same-window A/B profiles"
        ),
    )
    parser.add_argument(
        "--extra-arti-socks-connect-hedge-ms",
        action="append",
        type=int,
        default=[],
        help=(
            "start one extra Arti profile with this non-onion SOCKS CONNECT "
            "hedge delay; repeat for more same-window A/B profiles"
        ),
    )
    parser.add_argument(
        "--extra-arti-socks-connect-soft-timeout-combo",
        action="append",
        default=[],
        metavar="MS:ATTEMPTS",
        help=(
            "start one extra Arti profile with both a non-onion SOCKS CONNECT "
            "soft timeout and attempt count, for example 5000:3"
        ),
    )
    parser.add_argument(
        "--extra-arti-socks-connect-soft-timeout-pending-hedge-combo",
        action="append",
        default=[],
        metavar="MS:ATTEMPTS:HEDGE_MS",
        help=(
            "start one extra Arti profile with both a non-onion SOCKS CONNECT "
            "soft-timeout combo and an exit pending hedge, for example 5000:3:1500"
        ),
    )
    parser.add_argument(
        "--extra-arti-socks-no-tor-byte-relay-timeout-ms",
        action="append",
        type=int,
        default=[],
        help=(
            "start one extra Arti profile with this non-onion no-Tor-byte "
            "relay timeout; repeat for more same-window A/B profiles"
        ),
    )
    parser.add_argument(
        "--extra-arti-socks-partial-relay-idle-timeout-ms",
        action="append",
        type=int,
        default=[],
        help=(
            "start one extra Arti profile with this partial-response relay "
            "idle timeout; repeat for more same-window A/B profiles"
        ),
    )
    parser.add_argument(
        "--extra-arti-exit-pending-hedge-ms",
        action="append",
        type=int,
        default=[],
        help=(
            "start one extra Arti profile with this exit pending hedge; "
            "repeat for more same-window A/B profiles"
        ),
    )
    parser.add_argument(
        "--extra-arti-dirclient-read-timeout-ms",
        action="append",
        type=int,
        default=[],
        help=(
            "start one extra Arti profile with this directory read timeout; "
            "repeat for more same-window A/B profiles"
        ),
    )
    parser.add_argument(
        "--extra-arti-dir-microdesc-early-usable-notify",
        action="store_true",
        help=(
            "start one extra same-window Arti profile that reports bootstrap "
            "usable as soon as microdescriptor downloads reach Arti's usable threshold"
        ),
    )
    parser.add_argument(
        "--extra-arti-dir-microdesc-source-spread-pending-spread-early-usable",
        action="store_true",
        help=(
            "start one extra same-window Arti profile with microdescriptor "
            "source spread, pending spread, and early usable notification"
        ),
    )
    parser.add_argument(
        "--extra-arti-dir-microdesc-source-spread-pending-spread-early-usable-load-aware",
        action="store_true",
        help=(
            "start one extra same-window Arti profile with microdescriptor "
            "source spread, pending spread, early usable notification, and "
            "load-aware exit selection"
        ),
    )
    parser.add_argument(
        "--extra-arti-dir-microdesc-source-spread-pending-spread-early-usable-load-aware-no-dir-bad-health-replacement",
        action="store_true",
        help=(
            "start one extra same-window Arti profile with the load-aware "
            "directory combo, but disable dir-microdesc bad-health replacement"
        ),
    )
    parser.add_argument(
        "--extra-arti-dir-microdesc-source-spread-pending-spread-early-usable-load-aware-bad-health-replacement-suppress-gap-ms",
        action="append",
        type=int,
        default=[],
        help=(
            "start one extra same-window Arti profile with the load-aware "
            "directory combo plus this dir-microdesc bad-health-replacement "
            "gap suppression threshold; repeat for more profiles"
        ),
    )
    parser.add_argument(
        "--extra-arti-dir-microdesc-source-spread-pending-spread-early-usable-load-aware-bad-health-replacement-gate",
        action="append",
        default=[],
        metavar="GAP_MS:MIN_ASSIGNED:MIN_ACTIVE",
        help=(
            "start one extra same-window Arti profile with the load-aware "
            "directory combo plus a targeted dir-microdesc bad-health "
            "suppression gate using GAP_MS:MIN_ASSIGNED:MIN_ACTIVE; repeat "
            "for more profiles"
        ),
    )
    parser.add_argument(
        "--extra-arti-dir-microdesc-source-spread-pending-spread-early-usable-load-aware-early-retry-on-partial",
        action="store_true",
        help=(
            "start one extra same-window Arti profile with the load-aware "
            "directory combo plus microdescriptor early retry after a partial "
            "directory response"
        ),
    )
    parser.add_argument(
        "--extra-arti-dir-microdesc-source-spread-pending-spread-early-usable-load-aware-partial-retry-chunking",
        action="store_true",
        help=(
            "start one extra same-window Arti profile with the load-aware "
            "directory combo plus partial-response retry chunking"
        ),
    )
    parser.add_argument(
        "--extra-arti-dir-microdesc-source-spread-pending-spread-early-usable-load-aware-partial-retry-chunking-max-active-streams",
        action="append",
        type=int,
        default=[],
        help=(
            "start one extra same-window Arti profile with the load-aware "
            "partial-retry directory combo plus this active-stream cap per "
            "selected circuit; repeat for more profiles"
        ),
    )
    parser.add_argument(
        "--extra-arti-dir-microdesc-source-spread-pending-spread-early-usable-load-aware-partial-retry-chunking-bad-health-replacement-gate",
        action="append",
        default=[],
        metavar="GAP_MS:MIN_ASSIGNED:MIN_ACTIVE",
        help=(
            "start one extra same-window Arti profile with the load-aware "
            "partial-retry directory combo plus a targeted dir-microdesc "
            "bad-health suppression gate using GAP_MS:MIN_ASSIGNED:MIN_ACTIVE; "
            "repeat for more profiles"
        ),
    )
    parser.add_argument(
        "--extra-arti-dir-microdesc-source-spread-pending-spread-early-usable-partial-retry-chunking",
        action="store_true",
        help=(
            "start one extra same-window Arti profile with the directory "
            "source-spread/pending-spread/early-usable combo plus "
            "partial-response retry chunking, but without load-aware selection"
        ),
    )
    parser.add_argument(
        "--extra-arti-dir-microdesc-source-spread-pending-spread-early-usable-partial-retry-chunking-max-active-streams",
        action="append",
        type=int,
        default=[],
        help=(
            "start one extra same-window Arti profile with the no-load-aware "
            "partial-retry directory combo plus this active-stream cap per "
            "selected circuit; repeat for more profiles"
        ),
    )
    parser.add_argument(
        "--extra-arti-dir-microdesc-source-spread-pending-spread-early-usable-load-aware-partial-retry-chunking-socks-connect-hedge-ms",
        action="append",
        type=int,
        default=[],
        help=(
            "start one extra same-window Arti profile with the current "
            "load-aware directory combo plus this hostname SOCKS CONNECT hedge"
        ),
    )
    parser.add_argument(
        "--extra-arti-dir-microdesc-source-spread-pending-spread-early-usable-load-aware-partial-retry-chunking-socks-connect-soft-timeout-combo",
        action="append",
        default=[],
        metavar="MS:ATTEMPTS",
        help=(
            "start one extra same-window Arti profile with the current "
            "load-aware directory combo plus a non-onion SOCKS CONNECT soft "
            "timeout and attempt count, for example 5000:3"
        ),
    )
    parser.add_argument(
        "--extra-arti-dir-microdesc-source-spread-pending-spread-early-usable-load-aware-partial-retry-chunking-hs-rend-prebuild-before-desc",
        action="store_true",
        help=(
            "start one extra same-window Arti profile with the current "
            "load-aware directory combo plus hidden-service rendezvous "
            "prebuild before descriptor fetch finishes"
        ),
    )
    parser.add_argument(
        "--extra-arti-dir-microdesc-source-spread-pending-spread-early-usable-partial-retry-chunking-hs-rend-prebuild-before-desc",
        action="store_true",
        help=(
            "start one extra same-window Arti profile with the no-load-aware "
            "partial-retry directory combo plus hidden-service rendezvous "
            "prebuild before descriptor fetch finishes"
        ),
    )
    parser.add_argument(
        "--extra-arti-dir-microdesc-source-spread-pending-spread",
        action="store_true",
        help=(
            "start one extra same-window Arti profile with microdescriptor "
            "source spread and pending spread, without early usable notification"
        ),
    )
    parser.add_argument(
        "--extra-arti-dir-microdesc-retry-ids-per-request",
        action="append",
        type=int,
        default=[],
        help=(
            "start one extra same-window Arti profile that uses this "
            "microdescriptor request size only after the first download retry"
        ),
    )
    parser.add_argument(
        "--extra-arti-exit-select-load-aware",
        action="store_true",
        help="start one extra same-window Arti profile with load-aware exit selection",
    )
    parser.add_argument(
        "--extra-arti-exit-select-health-aware",
        action="store_true",
        help="start one extra same-window Arti profile with health-aware load-aware selection",
    )
    parser.add_argument(
        "--extra-arti-exit-select-health-min-move-score-bps",
        action="append",
        type=int,
        default=[],
        help=(
            "start one extra same-window health-aware Arti profile with this "
            "minimum move score; repeat for more profiles"
        ),
    )
    parser.add_argument(
        "--extra-arti-exit-select-health-min-move-score-assigned-cap",
        action="append",
        default=[],
        metavar="SCORE:CAP",
        help=(
            "start one extra same-window health-aware Arti profile with this "
            "minimum move score and assigned-stream cap; repeat for more profiles"
        ),
    )
    parser.add_argument(
        "--extra-arti-exit-select-health-aware-min-assignment-spread",
        action="append",
        type=int,
        default=[],
        help=(
            "start one extra same-window health-aware Arti profile with this "
            "minimum assigned-stream spread; repeat for more profiles"
        ),
    )
    parser.add_argument(
        "--extra-arti-exit-select-health-aware-min-assigned",
        action="append",
        type=int,
        default=[],
        help=(
            "start one extra same-window health-aware Arti profile gated until "
            "the assignment-selected circuit has this many assigned streams; "
            "repeat for more profiles"
        ),
    )
    parser.add_argument(
        "--extra-arti-exit-select-avoid-bad-health",
        action="store_true",
        help=(
            "start one extra same-window load-aware Arti profile with the "
            "bad-health guard"
        ),
    )
    parser.add_argument(
        "--extra-arti-exit-select-health-aware-avoid-bad-health",
        action="store_true",
        help=(
            "start one extra same-window health-aware Arti profile with the "
            "bad-health guard"
        ),
    )
    parser.add_argument(
        "--extra-arti-exit-select-health-aware-avoid-bad-health-same-isolation-target",
        action="append",
        type=int,
        default=[],
        help=(
            "start one extra same-window health-aware bad-health-guard Arti "
            "profile with this same-isolation target; repeat for more profiles"
        ),
    )
    parser.add_argument(
        "--extra-arti-exit-select-health-aware-same-isolation-prefer-cold-target",
        action="append",
        type=int,
        default=[],
        help=(
            "start one extra same-window health-aware same-isolation profile "
            "with cold-candidate preference but without the bad-health guard; "
            "repeat for more profiles"
        ),
    )
    parser.add_argument(
        "--extra-arti-exit-select-min-assignment-spread",
        action="append",
        type=int,
        default=[],
        help=(
            "start one extra same-window load-aware Arti profile with this "
            "minimum assigned-stream spread; repeat for more profiles"
        ),
    )
    parser.add_argument(
        "--extra-arti-exit-select-healthy-over-cold-min-assigned",
        action="append",
        type=int,
        default=[],
        help=(
            "start one extra same-window load-aware Arti profile with the "
            "healthy-over-cold guard at this assigned-stream floor; repeat "
            "for more profiles"
        ),
    )
    parser.add_argument(
        "--extra-arti-exit-select-healthy-over-cold-guard-only-min-assigned",
        action="append",
        type=int,
        default=[],
        help=(
            "start one extra same-window Arti profile with the guard-only "
            "healthy-over-cold selector at this assigned-stream floor; repeat "
            "for more profiles"
        ),
    )
    parser.add_argument(
        "--extra-arti-exit-select-max-active-streams",
        action="append",
        type=int,
        default=[],
        help=(
            "start one extra same-window load-aware Arti profile with this "
            "active-stream cap per selected circuit; repeat for more profiles"
        ),
    )
    parser.add_argument(
        "--extra-arti-exit-select-max-assigned-streams",
        action="append",
        type=int,
        default=[],
        help=(
            "start one extra same-window load-aware Arti profile with this "
            "assigned-stream cap per selected circuit; repeat for more profiles"
        ),
    )
    parser.add_argument(
        "--extra-arti-exit-select-bad-health-active-no-data-ms",
        action="append",
        type=int,
        default=[],
        help=(
            "start one extra same-window load-aware bad-health profile that "
            "marks active no-DATA circuits bad after this many ms; repeat for "
            "more profiles"
        ),
    )
    parser.add_argument(
        "--extra-arti-exit-select-bad-health-hedge-ms",
        action="append",
        type=int,
        default=[],
        help=(
            "start one extra same-window load-aware bad-health profile that "
            "waits this many ms for a same-usage replacement before falling "
            "back; repeat for more profiles"
        ),
    )
    parser.add_argument(
        "--extra-arti-exit-same-isolation-target",
        action="append",
        type=int,
        default=[],
        help=(
            "start one extra Arti profile with this same-isolation exit "
            "capacity target; repeat for more same-window A/B profiles"
        ),
    )
    parser.add_argument(
        "--extra-arti-exit-same-isolation-other-isolation-pressure",
        action="append",
        default=[],
        metavar="TARGET:MIN",
        help=(
            "start one extra Arti profile with same-isolation target TARGET, "
            "and top up when at least MIN open exit circuits belong to other "
            "isolation groups"
        ),
    )
    parser.add_argument(
        "--extra-arti-exit-same-isolation-other-isolation-pressure-assigned-cap",
        action="append",
        default=[],
        metavar="TARGET:MIN:CAP",
        help=(
            "start one extra Arti profile with same-isolation target TARGET, "
            "top up when at least MIN open exit circuits belong to other "
            "isolation groups, and cap selected assigned streams at CAP"
        ),
    )
    parser.add_argument(
        "--extra-arti-exit-same-isolation-other-isolation-pressure-assigned-cap-prewarm",
        action="append",
        default=[],
        metavar="TARGET:MIN:CAP",
        help=(
            "start one extra Arti profile with same-isolation target TARGET, "
            "top up when at least MIN open exit circuits belong to other "
            "isolation groups, cap selected assigned streams at CAP, and "
            "prewarm the first stream"
        ),
    )
    parser.add_argument(
        "--extra-arti-exit-select-prefer-cold-same-isolation-other-isolation-pressure",
        action="append",
        default=[],
        metavar="TARGET:MIN",
        help=(
            "start one extra health-aware avoid-bad-health prefer-cold Arti "
            "profile with same-isolation target TARGET, and top up when at "
            "least MIN open exit circuits belong to other isolation groups"
        ),
    )
    parser.add_argument(
        "--extra-arti-exit-load-aware-same-isolation-target",
        action="append",
        type=int,
        default=[],
        help=(
            "start one extra Arti profile with load-aware selection and this "
            "same-isolation exit capacity target, without first-stream prewarm "
            "or health-aware selector rules"
        ),
    )
    parser.add_argument(
        "--extra-arti-exit-same-isolation-prewarm-target",
        action="append",
        type=int,
        default=[],
        help=(
            "start one extra Arti profile with this same-isolation exit "
            "capacity target and first-stream prewarm, without extra selector "
            "rules; repeat for more same-window A/B profiles"
        ),
    )
    parser.add_argument(
        "--extra-arti-exit-same-isolation-min-assigned-streams",
        action="append",
        default=[],
        metavar="TARGET:MIN_ASSIGNED",
        help=(
            "start one extra Arti profile with same-isolation target TARGET, "
            "first-stream prewarm, and same-isolation top-up floor "
            "MIN_ASSIGNED assigned streams"
        ),
    )
    parser.add_argument(
        "--extra-arti-exit-same-isolation-prefer-topup-on-tie",
        action="append",
        type=int,
        default=[],
        help=(
            "start one extra Arti profile with this same-isolation exit "
            "capacity target, first-stream prewarm, and unused top-up tie "
            "preference enabled"
        ),
    )
    parser.add_argument(
        "--extra-arti-exit-load-aware-same-isolation-prewarm-target",
        action="append",
        type=int,
        default=[],
        help=(
            "start one extra Arti profile with load-aware selection, this "
            "same-isolation exit capacity target, and first-stream prewarm; "
            "does not enable health-aware or bad-health selector rules"
        ),
    )
    parser.add_argument(
        "--extra-arti-exit-health-aware-same-isolation-prewarm-target",
        action="append",
        type=int,
        default=[],
        help=(
            "start one extra Arti profile with health-aware load-aware "
            "selection, this same-isolation exit capacity target, and "
            "first-stream prewarm; does not enable avoid-bad-health or "
            "prefer-cold selector rules"
        ),
    )
    parser.add_argument(
        "--extra-arti-exit-select-health-min-move-score-same-isolation-pending-wait",
        action="append",
        default=[],
        metavar="TARGET:SCORE:WAIT_MS",
        help=(
            "start one extra health-aware Arti profile with a health move "
            "score, same-isolation target, and pending wait; repeat for more "
            "same-window A/B profiles"
        ),
    )
    parser.add_argument(
        "--arti-exit-same-isolation-require-bad-health",
        action="store_true",
        help=(
            "require recent bad local circuit health before same-isolation "
            "top-up lab capacity is added"
        ),
    )
    parser.add_argument(
        "--arti-exit-same-isolation-min-assigned-streams",
        type=int,
        help=(
            "lab-only same-isolation top-up floor; top up only after this many "
            "assigned streams on the selected circuit"
        ),
    )
    parser.add_argument(
        "--arti-exit-same-isolation-pending-wait-ms",
        type=int,
        help=(
            "lab-only same-isolation pending wait; when matching top-up capacity "
            "is already building, wait this many ms before falling back"
        ),
    )
    parser.add_argument(
        "--arti-exit-same-isolation-prewarm-first-stream",
        action="store_true",
        help=(
            "lab-only same-isolation standby rule; after the first selected "
            "exit stream for an isolation group, start building one matching "
            "standby circuit in the background"
        ),
    )
    parser.add_argument(
        "--arti-exit-select-prefer-cold-same-isolation",
        action="store_true",
        help=(
            "lab-only selector rule: when same-isolation and health-aware "
            "lab modes are enabled, let a cold least-assigned same-isolation "
            "candidate beat a busy active circuit"
        ),
    )
    parser.add_argument(
        "--extra-arti-exit-select-prefer-cold-same-isolation-target",
        action="append",
        type=int,
        default=[],
        help=(
            "start one extra health-aware avoid-bad-health same-isolation "
            "profile with cold-candidate preference; repeat for more profiles"
        ),
    )
    parser.add_argument(
        "--extra-arti-exit-select-prefer-cold-same-isolation-active-cap",
        action="append",
        default=[],
        metavar="TARGET:CAP",
        help=(
            "start one extra health-aware avoid-bad-health same-isolation "
            "prefer-cold profile with this same-isolation target and "
            "active-stream cap, for example 2:1"
        ),
    )
    parser.add_argument(
        "--extra-arti-exit-select-prefer-cold-same-isolation-prewarm-target",
        action="append",
        type=int,
        default=[],
        help=(
            "start one extra health-aware avoid-bad-health same-isolation "
            "prefer-cold profile with first-stream prewarm; repeat for more profiles"
        ),
    )
    parser.add_argument(
        "--extra-arti-exit-select-health-aware-same-isolation-prefer-cold-prewarm-pending-wait",
        action="append",
        default=[],
        metavar="TARGET:WAIT_MS",
        help=(
            "start one extra health-aware same-isolation prefer-cold profile "
            "with first-stream prewarm and pending wait, without the "
            "bad-health guard; repeat for more profiles"
        ),
    )
    parser.add_argument(
        "--extra-arti-exit-select-avoid-bad-health-unknown-fallback-prefer-cold-same-isolation-target",
        action="append",
        type=int,
        default=[],
        help=(
            "start one extra health-aware same-isolation profile with "
            "bad-health guard, unknown fallback, and cold-candidate "
            "preference; repeat for more profiles"
        ),
    )
    parser.add_argument(
        "--extra-arti-port-start",
        type=int,
        default=19083,
        help="first SOCKS port for extra Arti A/B profiles",
    )
    parser.add_argument(
        "--byte-tap",
        action="store_true",
        help="put a neutral local byte timing tap between the browser and each SOCKS proxy",
    )
    parser.add_argument(
        "--byte-tap-port-offset",
        type=int,
        default=100,
        help="tap listen port is proxy port plus this offset",
    )
    parser.add_argument(
        "--byte-tap-event-limit",
        type=int,
        default=DEFAULT_BYTE_TAP_EVENT_LIMIT,
        help="max byte events to save per connection direction",
    )
    parser.add_argument(
        "--byte-tap-socks-reply-bind-port-tag",
        action="store_true",
        help=(
            "lab-only proof mode: rewrite SOCKS5 CONNECT reply bind ports in "
            "the neutral byte tap to a per-connection tag"
        ),
    )
    args = parser.parse_args()

    browser_bin = Path(args.browser_bin).resolve()
    bundled_tor_bin = Path(args.bundled_tor_bin).resolve()
    tor_bin = Path(args.tor_bin).resolve()
    arti_bin = Path(args.arti_bin).resolve()

    if not browser_bin.exists():
        print(f"browser binary not found: {browser_bin}", file=sys.stderr)
        return 2
    if not tor_bin.exists():
        print(f"tor binary not found: {tor_bin}", file=sys.stderr)
        return 2
    if not arti_bin.exists():
        print(f"arti binary not found: {arti_bin}", file=sys.stderr)
        return 2
    if args.arti_exit_select_parallelism is not None and not (
        1 <= args.arti_exit_select_parallelism <= 8
    ):
        print("--arti-exit-select-parallelism must be between 1 and 8", file=sys.stderr)
        return 2
    if args.arti_exit_launch_parallelism is not None and not (
        1 <= args.arti_exit_launch_parallelism <= 4
    ):
        print("--arti-exit-launch-parallelism must be between 1 and 4", file=sys.stderr)
        return 2
    if args.arti_min_exit_circs_for_port is not None and not (
        1 <= args.arti_min_exit_circs_for_port <= 4
    ):
        print("--arti-min-exit-circs-for-port must be between 1 and 4", file=sys.stderr)
        return 2
    if args.arti_socks_connect_soft_timeout_ms is not None and not (
        500 <= args.arti_socks_connect_soft_timeout_ms <= 60_000
    ):
        print(
            "--arti-socks-connect-soft-timeout-ms must be between 500 and 60000",
            file=sys.stderr,
        )
        return 2
    if (
        args.browser_max_persistent_connections_per_server is not None
        and not (1 <= args.browser_max_persistent_connections_per_server <= 32)
    ):
        print(
            "--browser-max-persistent-connections-per-server must be between 1 and 32",
            file=sys.stderr,
        )
        return 2
    if (
        args.browser_serial_http_connections
        and args.browser_max_persistent_connections_per_server is not None
    ):
        print(
            "--browser-serial-http-connections cannot be combined with "
            "--browser-max-persistent-connections-per-server",
            file=sys.stderr,
        )
        return 2
    try:
        browser_block_url_substrings = normalize_browser_block_url_substrings(
            args.browser_block_url_substrings
        )
    except ValueError as exc:
        print(f"--browser-block-url-substring {exc}", file=sys.stderr)
        return 2
    if args.arti_socks_connect_soft_timeout_attempts is not None and not (
        1 <= args.arti_socks_connect_soft_timeout_attempts <= 4
    ):
        print(
            "--arti-socks-connect-soft-timeout-attempts must be between 1 and 4",
            file=sys.stderr,
        )
        return 2
    if args.arti_socks_connect_hedge_ms is not None and not (
        500 <= args.arti_socks_connect_hedge_ms <= 60_000
    ):
        print(
            "--arti-socks-connect-hedge-ms must be between 500 and 60000",
            file=sys.stderr,
        )
        return 2
    if args.arti_socks_partial_relay_idle_timeout_ms is not None and not (
        500 <= args.arti_socks_partial_relay_idle_timeout_ms <= 60_000
    ):
        print(
            "--arti-socks-partial-relay-idle-timeout-ms must be between 500 and 60000",
            file=sys.stderr,
        )
        return 2
    if args.arti_socks_no_tor_byte_relay_timeout_ms is not None and not (
        500 <= args.arti_socks_no_tor_byte_relay_timeout_ms <= 60_000
    ):
        print(
            "--arti-socks-no-tor-byte-relay-timeout-ms must be between 500 and 60000",
            file=sys.stderr,
        )
        return 2
    invalid_extra_no_tor_byte_timeouts = [
        value
        for value in args.extra_arti_socks_no_tor_byte_relay_timeout_ms
        if not (500 <= value <= 60_000)
    ]
    if invalid_extra_no_tor_byte_timeouts:
        print(
            "--extra-arti-socks-no-tor-byte-relay-timeout-ms must be between 500 and 60000",
            file=sys.stderr,
        )
        return 2
    invalid_extra_partial_idle_timeouts = [
        value
        for value in args.extra_arti_socks_partial_relay_idle_timeout_ms
        if not (500 <= value <= 60_000)
    ]
    if invalid_extra_partial_idle_timeouts:
        print(
            "--extra-arti-socks-partial-relay-idle-timeout-ms must be between 500 and 60000",
            file=sys.stderr,
        )
        return 2
    invalid_extra_dir_bad_health_gap_thresholds = [
        value
        for value in args.extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_bad_health_replacement_suppress_gap_ms
        if not (1_000 <= value <= 60_000)
    ]
    if invalid_extra_dir_bad_health_gap_thresholds:
        print(
            "--extra-arti-dir-microdesc-source-spread-pending-spread-early-usable-load-aware-bad-health-replacement-suppress-gap-ms must be between 1000 and 60000",
            file=sys.stderr,
        )
        return 2
    try:
        extra_dir_bad_health_gate_combos = parse_dir_bad_health_gate_combos(
            args.extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_bad_health_replacement_gate
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    try:
        extra_dir_partial_retry_chunk_bad_health_gate_combos = (
            parse_dir_bad_health_gate_combos(
                args.extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_partial_retry_chunking_bad_health_replacement_gate,
                option=(
                    "--extra-arti-dir-microdesc-source-spread-pending-spread-"
                    "early-usable-load-aware-partial-retry-chunking-bad-health-"
                    "replacement-gate"
                ),
            )
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.arti_dirclient_read_timeout_ms is not None and not (
        2_000 <= args.arti_dirclient_read_timeout_ms <= 10_000
    ):
        print(
            "--arti-dirclient-read-timeout-ms must be between 2000 and 10000",
            file=sys.stderr,
        )
        return 2
    try:
        extra_soft_timeout_combos = parse_soft_timeout_combos(
            args.extra_arti_socks_connect_soft_timeout_combo
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    try:
        extra_soft_timeout_pending_hedge_combos = (
            parse_soft_timeout_pending_hedge_combos(
                args.extra_arti_socks_connect_soft_timeout_pending_hedge_combo
            )
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    try:
        extra_dir_combo_soft_timeout_combos = parse_soft_timeout_combos(
            args.extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_partial_retry_chunking_socks_connect_soft_timeout_combo
        )
    except ValueError as exc:
        print(
            str(exc).replace(
                "--extra-arti-socks-connect-soft-timeout-combo",
                "--extra-arti-dir-microdesc-source-spread-pending-spread-early-usable-load-aware-partial-retry-chunking-socks-connect-soft-timeout-combo",
            ),
            file=sys.stderr,
        )
        return 2
    try:
        extra_prefer_cold_sameiso_active_cap_combos = (
            parse_same_iso_active_cap_combos(
                args.extra_arti_exit_select_prefer_cold_same_isolation_active_cap
            )
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    try:
        extra_sameiso_other_iso_pressure_combos = (
            parse_same_iso_other_iso_pressure_combos(
                args.extra_arti_exit_same_isolation_other_isolation_pressure
            )
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    try:
        extra_sameiso_other_iso_assigned_cap_combos = (
            parse_same_iso_other_iso_assigned_cap_combos(
                args.extra_arti_exit_same_isolation_other_isolation_pressure_assigned_cap
            )
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    try:
        extra_sameiso_other_iso_assigned_cap_prewarm_combos = (
            parse_same_iso_other_iso_assigned_cap_combos(
                args.extra_arti_exit_same_isolation_other_isolation_pressure_assigned_cap_prewarm
            )
        )
    except ValueError as exc:
        print(
            str(exc).replace(
                "--extra-arti-exit-same-isolation-other-isolation-pressure-assigned-cap",
                "--extra-arti-exit-same-isolation-other-isolation-pressure-assigned-cap-prewarm",
            ),
            file=sys.stderr,
        )
        return 2
    try:
        extra_prefer_cold_sameiso_other_iso_pressure_combos = (
            parse_same_iso_other_iso_pressure_combos(
                args.extra_arti_exit_select_prefer_cold_same_isolation_other_isolation_pressure
            )
        )
    except ValueError as exc:
        print(
            str(exc).replace(
                "--extra-arti-exit-same-isolation-other-isolation-pressure",
                "--extra-arti-exit-select-prefer-cold-same-isolation-other-isolation-pressure",
            ),
            file=sys.stderr,
        )
        return 2
    try:
        extra_sameiso_min_assigned_combos = parse_same_iso_min_assigned_combos(
            args.extra_arti_exit_same_isolation_min_assigned_streams
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    try:
        extra_health_min_sameiso_pending_wait_combos = (
            parse_health_min_sameiso_pending_wait_combos(
                args.extra_arti_exit_select_health_min_move_score_same_isolation_pending_wait
            )
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    try:
        extra_health_aware_sameiso_prefer_cold_prewarm_pending_wait_combos = (
            parse_sameiso_pending_wait_combos(
                args.extra_arti_exit_select_health_aware_same_isolation_prefer_cold_prewarm_pending_wait,
                "--extra-arti-exit-select-health-aware-same-isolation-prefer-cold-prewarm-pending-wait",
            )
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    try:
        extra_health_min_assigned_cap_combos = parse_health_min_assigned_cap_combos(
            args.extra_arti_exit_select_health_min_move_score_assigned_cap
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    try:
        extra_arti_bins = parse_extra_arti_bin_specs(args.extra_arti_bin)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    missing_extra_arti_bins = [
        path for _profile_name, path in extra_arti_bins if not path.exists()
    ]
    if missing_extra_arti_bins:
        print(
            f"extra Arti binary not found: {missing_extra_arti_bins[0]}",
            file=sys.stderr,
        )
        return 2
    if args.arti_exit_pending_hedge_ms is not None and not (
        500 <= args.arti_exit_pending_hedge_ms <= 60_000
    ):
        print(
            "--arti-exit-pending-hedge-ms must be between 500 and 60000",
            file=sys.stderr,
        )
        return 2
    if args.arti_exit_select_bad_health_hedge_ms is not None and not (
        250 <= args.arti_exit_select_bad_health_hedge_ms <= 10_000
    ):
        print(
            "--arti-exit-select-bad-health-hedge-ms must be between 250 and 10000",
            file=sys.stderr,
        )
        return 2
    if any(
        not (250 <= value <= 10_000)
        for value in args.extra_arti_exit_select_bad_health_hedge_ms
    ):
        print(
            "--extra-arti-exit-select-bad-health-hedge-ms values must be between 250 and 10000",
            file=sys.stderr,
        )
        return 2
    if args.arti_exit_select_bad_health_stream_idle_ms is not None and not (
        1_000 <= args.arti_exit_select_bad_health_stream_idle_ms <= 120_000
    ):
        print(
            "--arti-exit-select-bad-health-stream-idle-ms must be between 1000 and 120000",
            file=sys.stderr,
        )
        return 2
    if args.arti_exit_select_bad_health_active_no_data_ms is not None and not (
        1_000 <= args.arti_exit_select_bad_health_active_no_data_ms <= 120_000
    ):
        print(
            "--arti-exit-select-bad-health-active-no-data-ms must be between 1000 and 120000",
            file=sys.stderr,
        )
        return 2
    if any(
        not (1_000 <= value <= 120_000)
        for value in args.extra_arti_exit_select_bad_health_active_no_data_ms
    ):
        print(
            "--extra-arti-exit-select-bad-health-active-no-data-ms values must be between 1000 and 120000",
            file=sys.stderr,
        )
        return 2
    if args.arti_exit_select_max_active_streams is not None and not (
        1 <= args.arti_exit_select_max_active_streams <= 32
    ):
        print(
            "--arti-exit-select-max-active-streams must be between 1 and 32",
            file=sys.stderr,
        )
        return 2
    if any(
        not (1 <= cap <= 32)
        for cap in args.extra_arti_exit_select_max_active_streams
    ):
        print(
            "--extra-arti-exit-select-max-active-streams values must be between 1 and 32",
            file=sys.stderr,
        )
        return 2
    if any(
        not (1 <= cap <= 32)
        for cap in (
            args.extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_partial_retry_chunking_max_active_streams
        )
    ):
        print(
            "--extra-arti-dir-microdesc-source-spread-pending-spread-early-usable-load-aware-partial-retry-chunking-max-active-streams values must be between 1 and 32",
            file=sys.stderr,
        )
        return 2
    if any(
        not (1 <= cap <= 32)
        for cap in (
            args.extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_partial_retry_chunking_max_active_streams
        )
    ):
        print(
            "--extra-arti-dir-microdesc-source-spread-pending-spread-early-usable-partial-retry-chunking-max-active-streams values must be between 1 and 32",
            file=sys.stderr,
        )
        return 2
    if args.arti_exit_select_max_assigned_streams is not None and not (
        1 <= args.arti_exit_select_max_assigned_streams <= 32
    ):
        print(
            "--arti-exit-select-max-assigned-streams must be between 1 and 32",
            file=sys.stderr,
        )
        return 2
    if any(
        not (1 <= cap <= 32)
        for cap in args.extra_arti_exit_select_max_assigned_streams
    ):
        print(
            "--extra-arti-exit-select-max-assigned-streams values must be between 1 and 32",
            file=sys.stderr,
        )
        return 2
    if args.arti_exit_select_health_min_move_score_bps is not None and not (
        0 <= args.arti_exit_select_health_min_move_score_bps <= 1_048_576
    ):
        print(
            "--arti-exit-select-health-min-move-score-bps must be between 0 and 1048576",
            file=sys.stderr,
        )
        return 2
    if args.arti_exit_select_min_assignment_spread is not None and not (
        0 <= args.arti_exit_select_min_assignment_spread <= 8
    ):
        print(
            "--arti-exit-select-min-assignment-spread must be between 0 and 8",
            file=sys.stderr,
        )
        return 2
    if args.arti_exit_select_healthy_over_cold_min_assigned is not None and not (
        0 <= args.arti_exit_select_healthy_over_cold_min_assigned <= 32
    ):
        print(
            "--arti-exit-select-healthy-over-cold-min-assigned must be between 0 and 32",
            file=sys.stderr,
        )
        return 2
    if (
        args.arti_exit_select_healthy_over_cold_guard_only_min_assigned is not None
        and not (1 <= args.arti_exit_select_healthy_over_cold_guard_only_min_assigned <= 32)
    ):
        print(
            "--arti-exit-select-healthy-over-cold-guard-only-min-assigned must be between 1 and 32",
            file=sys.stderr,
        )
        return 2
    if args.arti_exit_same_isolation_target is not None and not (
        2 <= args.arti_exit_same_isolation_target <= 4
    ):
        print(
            "--arti-exit-same-isolation-target must be between 2 and 4",
            file=sys.stderr,
        )
        return 2
    if args.arti_exit_same_isolation_min_assigned_streams is not None and not (
        1 <= args.arti_exit_same_isolation_min_assigned_streams <= 8
    ):
        print(
            "--arti-exit-same-isolation-min-assigned-streams must be between 1 and 8",
            file=sys.stderr,
        )
        return 2
    invalid_extra = [
        value
        for value in args.extra_arti_exit_select_parallelism
        if not (1 <= value <= 8)
    ]
    if invalid_extra:
        print(
            "--extra-arti-exit-select-parallelism must be between 1 and 8",
            file=sys.stderr,
        )
        return 2
    invalid_extra_launch = [
        value
        for value in args.extra_arti_exit_launch_parallelism
        if not (1 <= value <= 4)
    ]
    if invalid_extra_launch:
        print(
            "--extra-arti-exit-launch-parallelism must be between 1 and 4",
            file=sys.stderr,
        )
        return 2
    invalid_extra_hspool_launch = [
        value
        for value in args.extra_arti_hspool_launch_parallelism
        if not (1 <= value <= 4)
    ]
    if invalid_extra_hspool_launch:
        print(
            "--extra-arti-hspool-launch-parallelism must be between 1 and 4",
            file=sys.stderr,
        )
        return 2
    invalid_extra_hspool_start_delay = [
        value
        for value in args.extra_arti_hspool_background_start_delay_ms
        if not (0 <= value <= 60000)
    ]
    if invalid_extra_hspool_start_delay:
        print(
            "--extra-arti-hspool-background-start-delay-ms must be between 0 and 60000",
            file=sys.stderr,
        )
        return 2
    invalid_extra_hspool_guarded_target = [
        value
        for value in args.extra_arti_hspool_guarded_stem_target
        if not (2 <= value <= 16)
    ]
    if invalid_extra_hspool_guarded_target:
        print(
            "--extra-arti-hspool-guarded-stem-target must be between 2 and 16",
            file=sys.stderr,
        )
        return 2
    invalid_extra_hspool_guarded_target_defer_post_boot = [
        value
        for value in args.extra_arti_hspool_guarded_stem_target_defer_post_bootstrap
        if not (2 <= value <= 16)
    ]
    if invalid_extra_hspool_guarded_target_defer_post_boot:
        print(
            "--extra-arti-hspool-guarded-stem-target-defer-post-bootstrap must be between 2 and 16",
            file=sys.stderr,
        )
        return 2
    invalid_extra_hspool_grace = [
        value
        for value in args.extra_arti_hspool_on_demand_grace_ms
        if not (1 <= value <= 1000)
    ]
    if invalid_extra_hspool_grace:
        print(
            "--extra-arti-hspool-on-demand-grace-ms must be between 1 and 1000",
            file=sys.stderr,
        )
        return 2
    invalid_extra_hspool_race = [
        value
        for value in args.extra_arti_hspool_on_demand_race_ms
        if not (1 <= value <= 1000)
    ]
    if invalid_extra_hspool_race:
        print(
            "--extra-arti-hspool-on-demand-race-ms must be between 1 and 1000",
            file=sys.stderr,
        )
        return 2
    invalid_extra_hs_intro_circuit_hedge = [
        value
        for value in args.extra_arti_hs_intro_circuit_hedge_ms
        if not (500 <= value <= 60000)
    ]
    if invalid_extra_hs_intro_circuit_hedge:
        print(
            "--extra-arti-hs-intro-circuit-hedge-ms must be between 500 and 60000",
            file=sys.stderr,
        )
        return 2
    invalid_extra_min_exit_circs = [
        value
        for value in args.extra_arti_min_exit_circs_for_port
        if not (1 <= value <= 4)
    ]
    if invalid_extra_min_exit_circs:
        print(
            "--extra-arti-min-exit-circs-for-port must be between 1 and 4",
            file=sys.stderr,
        )
        return 2
    invalid_extra_preemptive_443_circs = [
        value
        for value in args.extra_arti_preemptive_443_circs
        if not (2 <= value <= 4)
    ]
    if invalid_extra_preemptive_443_circs:
        print(
            "--extra-arti-preemptive-443-circs must be between 2 and 4",
            file=sys.stderr,
        )
        return 2
    invalid_extra_preemptive_443_burst_min_requests = [
        value
        for value in args.extra_arti_preemptive_443_burst_min_requests
        if not (2 <= value <= 32)
    ]
    if invalid_extra_preemptive_443_burst_min_requests:
        print(
            "--extra-arti-preemptive-443-burst-min-requests must be between 2 and 32",
            file=sys.stderr,
        )
        return 2
    invalid_extra_preemptive_443_busy_active_age_ms = [
        value
        for value in args.extra_arti_preemptive_443_busy_active_age_ms
        if not (100 <= value <= 60_000)
    ]
    if invalid_extra_preemptive_443_busy_active_age_ms:
        print(
            "--extra-arti-preemptive-443-busy-active-age-ms must be between 100 and 60000",
            file=sys.stderr,
        )
        return 2
    invalid_extra_soft_timeouts = [
        value
        for value in args.extra_arti_socks_connect_soft_timeout_ms
        if not (500 <= value <= 60_000)
    ]
    if invalid_extra_soft_timeouts:
        print(
            "--extra-arti-socks-connect-soft-timeout-ms must be between 500 and 60000",
            file=sys.stderr,
        )
        return 2
    invalid_extra_soft_timeout_attempts = [
        value
        for value in args.extra_arti_socks_connect_soft_timeout_attempts
        if not (1 <= value <= 4)
    ]
    if invalid_extra_soft_timeout_attempts:
        print(
            "--extra-arti-socks-connect-soft-timeout-attempts must be between 1 and 4",
            file=sys.stderr,
        )
        return 2
    invalid_extra_connect_hedges = [
        value
        for value in args.extra_arti_socks_connect_hedge_ms
        if not (500 <= value <= 60_000)
    ]
    if invalid_extra_connect_hedges:
        print(
            "--extra-arti-socks-connect-hedge-ms must be between 500 and 60000",
            file=sys.stderr,
        )
        return 2
    invalid_extra_dir_combo_connect_hedges = [
        value
        for value in (
            args.extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_partial_retry_chunking_socks_connect_hedge_ms
        )
        if not (500 <= value <= 60_000)
    ]
    if invalid_extra_dir_combo_connect_hedges:
        print(
            "--extra-arti-dir-microdesc-source-spread-pending-spread-early-usable-load-aware-partial-retry-chunking-socks-connect-hedge-ms must be between 500 and 60000",
            file=sys.stderr,
        )
        return 2
    invalid_extra_dir_combo_soft_timeout_combos = [
        (timeout_ms, attempts)
        for timeout_ms, attempts in extra_dir_combo_soft_timeout_combos
        if not (500 <= timeout_ms <= 60_000 and 1 <= attempts <= 4)
    ]
    if invalid_extra_dir_combo_soft_timeout_combos:
        print(
            "--extra-arti-dir-microdesc-source-spread-pending-spread-early-usable-load-aware-partial-retry-chunking-socks-connect-soft-timeout-combo values must be MS 500..60000 and ATTEMPTS 1..4",
            file=sys.stderr,
        )
        return 2
    invalid_extra_soft_timeout_combos = [
        (timeout_ms, attempts)
        for timeout_ms, attempts in extra_soft_timeout_combos
        if not (500 <= timeout_ms <= 60_000 and 1 <= attempts <= 4)
    ]
    if invalid_extra_soft_timeout_combos:
        print(
            "--extra-arti-socks-connect-soft-timeout-combo values must be MS 500..60000 and ATTEMPTS 1..4",
            file=sys.stderr,
        )
        return 2
    invalid_extra_soft_timeout_pending_hedge_combos = [
        (timeout_ms, attempts, hedge_ms)
        for timeout_ms, attempts, hedge_ms in extra_soft_timeout_pending_hedge_combos
        if not (
            500 <= timeout_ms <= 60_000
            and 1 <= attempts <= 4
            and 500 <= hedge_ms <= 60_000
        )
    ]
    if invalid_extra_soft_timeout_pending_hedge_combos:
        print(
            "--extra-arti-socks-connect-soft-timeout-pending-hedge-combo values must be MS 500..60000, ATTEMPTS 1..4, and HEDGE_MS 500..60000",
            file=sys.stderr,
        )
        return 2
    invalid_extra_pending_hedges = [
        value
        for value in args.extra_arti_exit_pending_hedge_ms
        if not (500 <= value <= 60_000)
    ]
    if invalid_extra_pending_hedges:
        print(
            "--extra-arti-exit-pending-hedge-ms must be between 500 and 60000",
            file=sys.stderr,
        )
        return 2
    invalid_extra_dirclient_read_timeouts = [
        value
        for value in args.extra_arti_dirclient_read_timeout_ms
        if not (2_000 <= value <= 10_000)
    ]
    if invalid_extra_dirclient_read_timeouts:
        print(
            "--extra-arti-dirclient-read-timeout-ms must be between 2000 and 10000",
            file=sys.stderr,
        )
        return 2
    invalid_extra_microdesc_retry_chunks = [
        value
        for value in args.extra_arti_dir_microdesc_retry_ids_per_request
        if not (64 <= value <= 500)
    ]
    if invalid_extra_microdesc_retry_chunks:
        print(
            "--extra-arti-dir-microdesc-retry-ids-per-request must be between 64 and 500",
            file=sys.stderr,
        )
        return 2
    invalid_extra_health_min_scores = [
        value
        for value in args.extra_arti_exit_select_health_min_move_score_bps
        if not (0 <= value <= 1_048_576)
    ]
    if invalid_extra_health_min_scores:
        print(
            "--extra-arti-exit-select-health-min-move-score-bps must be between 0 and 1048576",
            file=sys.stderr,
        )
        return 2
    invalid_extra_health_aware_min_assignment_spreads = [
        value
        for value in args.extra_arti_exit_select_health_aware_min_assignment_spread
        if not (0 <= value <= 8)
    ]
    if invalid_extra_health_aware_min_assignment_spreads:
        print(
            "--extra-arti-exit-select-health-aware-min-assignment-spread must be between 0 and 8",
            file=sys.stderr,
        )
        return 2
    invalid_extra_health_aware_min_assigned = [
        value
        for value in args.extra_arti_exit_select_health_aware_min_assigned
        if not (1 <= value <= 32)
    ]
    if invalid_extra_health_aware_min_assigned:
        print(
            "--extra-arti-exit-select-health-aware-min-assigned must be between 1 and 32",
            file=sys.stderr,
        )
        return 2
    invalid_extra_min_assignment_spreads = [
        value
        for value in args.extra_arti_exit_select_min_assignment_spread
        if not (0 <= value <= 8)
    ]
    if invalid_extra_min_assignment_spreads:
        print(
            "--extra-arti-exit-select-min-assignment-spread must be between 0 and 8",
            file=sys.stderr,
        )
        return 2
    invalid_extra_healthy_over_cold_min_assigned = [
        value
        for value in args.extra_arti_exit_select_healthy_over_cold_min_assigned
        if not (0 <= value <= 32)
    ]
    if invalid_extra_healthy_over_cold_min_assigned:
        print(
            "--extra-arti-exit-select-healthy-over-cold-min-assigned must be between 0 and 32",
            file=sys.stderr,
        )
        return 2
    invalid_extra_healthy_over_cold_guard_only_min_assigned = [
        value
        for value in args.extra_arti_exit_select_healthy_over_cold_guard_only_min_assigned
        if not (1 <= value <= 32)
    ]
    if invalid_extra_healthy_over_cold_guard_only_min_assigned:
        print(
            "--extra-arti-exit-select-healthy-over-cold-guard-only-min-assigned must be between 1 and 32",
            file=sys.stderr,
        )
        return 2
    invalid_extra_same_isolation_targets = [
        value
        for value in args.extra_arti_exit_same_isolation_target
        if not (2 <= value <= 4)
    ]
    if invalid_extra_same_isolation_targets:
        print(
            "--extra-arti-exit-same-isolation-target must be between 2 and 4",
            file=sys.stderr,
        )
        return 2
    invalid_extra_load_aware_same_isolation_targets = [
        value
        for value in args.extra_arti_exit_load_aware_same_isolation_target
        if not (2 <= value <= 4)
    ]
    if invalid_extra_load_aware_same_isolation_targets:
        print(
            "--extra-arti-exit-load-aware-same-isolation-target must be between 2 and 4",
            file=sys.stderr,
        )
        return 2
    invalid_extra_same_isolation_prewarm_targets = [
        value
        for value in args.extra_arti_exit_same_isolation_prewarm_target
        if not (2 <= value <= 4)
    ]
    if invalid_extra_same_isolation_prewarm_targets:
        print(
            "--extra-arti-exit-same-isolation-prewarm-target must be between 2 and 4",
            file=sys.stderr,
        )
        return 2
    invalid_extra_same_isolation_prefer_topup_on_tie_targets = [
        value
        for value in args.extra_arti_exit_same_isolation_prefer_topup_on_tie
        if not (2 <= value <= 4)
    ]
    if invalid_extra_same_isolation_prefer_topup_on_tie_targets:
        print(
            "--extra-arti-exit-same-isolation-prefer-topup-on-tie must be between 2 and 4",
            file=sys.stderr,
        )
        return 2
    invalid_extra_load_aware_same_isolation_prewarm_targets = [
        value
        for value in args.extra_arti_exit_load_aware_same_isolation_prewarm_target
        if not (2 <= value <= 4)
    ]
    if invalid_extra_load_aware_same_isolation_prewarm_targets:
        print(
            "--extra-arti-exit-load-aware-same-isolation-prewarm-target must be between 2 and 4",
            file=sys.stderr,
        )
        return 2
    invalid_extra_health_aware_same_isolation_prewarm_targets = [
        value
        for value in args.extra_arti_exit_health_aware_same_isolation_prewarm_target
        if not (2 <= value <= 4)
    ]
    if invalid_extra_health_aware_same_isolation_prewarm_targets:
        print(
            "--extra-arti-exit-health-aware-same-isolation-prewarm-target must be between 2 and 4",
            file=sys.stderr,
        )
        return 2
    invalid_extra_guarded_same_isolation_targets = [
        value
        for value in (
            args.extra_arti_exit_select_health_aware_avoid_bad_health_same_isolation_target
        )
        if not (2 <= value <= 4)
    ]
    if invalid_extra_guarded_same_isolation_targets:
        print(
            "--extra-arti-exit-select-health-aware-avoid-bad-health-same-isolation-target must be between 2 and 4",
            file=sys.stderr,
        )
        return 2
    invalid_extra_health_same_iso_prefer_cold_targets = [
        value
        for value in (
            args.extra_arti_exit_select_health_aware_same_isolation_prefer_cold_target
        )
        if not (2 <= value <= 4)
    ]
    if invalid_extra_health_same_iso_prefer_cold_targets:
        print(
            "--extra-arti-exit-select-health-aware-same-isolation-prefer-cold-target must be between 2 and 4",
            file=sys.stderr,
        )
        return 2
    invalid_extra_prefer_cold_same_isolation_targets = [
        value
        for value in args.extra_arti_exit_select_prefer_cold_same_isolation_target
        if not (2 <= value <= 4)
    ]
    if invalid_extra_prefer_cold_same_isolation_targets:
        print(
            "--extra-arti-exit-select-prefer-cold-same-isolation-target must be between 2 and 4",
            file=sys.stderr,
        )
        return 2
    invalid_extra_prefer_cold_same_isolation_prewarm_targets = [
        value
        for value in args.extra_arti_exit_select_prefer_cold_same_isolation_prewarm_target
        if not (2 <= value <= 4)
    ]
    if invalid_extra_prefer_cold_same_isolation_prewarm_targets:
        print(
            "--extra-arti-exit-select-prefer-cold-same-isolation-prewarm-target must be between 2 and 4",
            file=sys.stderr,
        )
        return 2
    invalid_extra_unknown_fallback_prefer_cold_targets = [
        value
        for value in (
            args.extra_arti_exit_select_avoid_bad_health_unknown_fallback_prefer_cold_same_isolation_target
        )
        if not (2 <= value <= 4)
    ]
    if invalid_extra_unknown_fallback_prefer_cold_targets:
        print(
            "--extra-arti-exit-select-avoid-bad-health-unknown-fallback-prefer-cold-same-isolation-target must be between 2 and 4",
            file=sys.stderr,
        )
        return 2
    if args.extra_c_tor_conflux_ux and args.schedule != "sequential":
        print(
            "--extra-c-tor-conflux-ux requires --schedule sequential",
            file=sys.stderr,
        )
        return 2
    if args.extra_arti_exit_select_parallelism and args.schedule != "interleaved":
        print(
            "--extra-arti-exit-select-parallelism requires --schedule interleaved",
            file=sys.stderr,
        )
        return 2
    if args.extra_arti_exit_launch_parallelism and args.schedule != "interleaved":
        print(
            "--extra-arti-exit-launch-parallelism requires --schedule interleaved",
            file=sys.stderr,
        )
        return 2
    if args.extra_arti_hspool_launch_parallelism and args.schedule != "interleaved":
        print(
            "--extra-arti-hspool-launch-parallelism requires --schedule interleaved",
            file=sys.stderr,
        )
        return 2
    if (
        args.extra_arti_hspool_background_start_delay_ms
        and args.schedule != "interleaved"
    ):
        print(
            "--extra-arti-hspool-background-start-delay-ms requires --schedule interleaved",
            file=sys.stderr,
        )
        return 2
    if args.extra_arti_hspool_guarded_stem_target and args.schedule != "interleaved":
        print(
            "--extra-arti-hspool-guarded-stem-target requires --schedule interleaved",
            file=sys.stderr,
        )
        return 2
    if (
        args.extra_arti_hspool_guarded_stem_target_defer_post_bootstrap
        and args.schedule != "interleaved"
    ):
        print(
            "--extra-arti-hspool-guarded-stem-target-defer-post-bootstrap requires --schedule interleaved",
            file=sys.stderr,
        )
        return 2
    if args.extra_arti_hspool_on_demand_grace_ms and args.schedule != "interleaved":
        print(
            "--extra-arti-hspool-on-demand-grace-ms requires --schedule interleaved",
            file=sys.stderr,
        )
        return 2
    if args.extra_arti_hspool_on_demand_race_ms and args.schedule != "interleaved":
        print(
            "--extra-arti-hspool-on-demand-race-ms requires --schedule interleaved",
            file=sys.stderr,
        )
        return 2
    if args.extra_arti_hs_intro_rend_overlap and args.schedule != "interleaved":
        print(
            "--extra-arti-hs-intro-rend-overlap requires --schedule interleaved",
            file=sys.stderr,
        )
        return 2
    if args.extra_arti_hs_rend_prebuild_before_desc and args.schedule != "interleaved":
        print(
            "--extra-arti-hs-rend-prebuild-before-desc requires --schedule interleaved",
            file=sys.stderr,
        )
        return 2
    if args.extra_arti_hs_desc_shared_cache and args.schedule != "interleaved":
        print(
            "--extra-arti-hs-desc-shared-cache requires --schedule interleaved",
            file=sys.stderr,
        )
        return 2
    if args.extra_arti_hs_intro_circuit_hedge_ms and args.schedule != "interleaved":
        print(
            "--extra-arti-hs-intro-circuit-hedge-ms requires --schedule interleaved",
            file=sys.stderr,
        )
        return 2
    if args.extra_arti_min_exit_circs_for_port and args.schedule != "interleaved":
        print(
            "--extra-arti-min-exit-circs-for-port requires --schedule interleaved",
            file=sys.stderr,
        )
        return 2
    if args.extra_arti_preemptive_443_circs and args.schedule != "interleaved":
        print(
            "--extra-arti-preemptive-443-circs requires --schedule interleaved",
            file=sys.stderr,
        )
        return 2
    if (
        args.extra_arti_preemptive_443_burst_min_requests
        and args.schedule != "interleaved"
    ):
        print(
            "--extra-arti-preemptive-443-burst-min-requests requires --schedule interleaved",
            file=sys.stderr,
        )
        return 2
    if (
        args.extra_arti_preemptive_443_busy_active_age_ms
        and args.schedule != "interleaved"
    ):
        print(
            "--extra-arti-preemptive-443-busy-active-age-ms requires --schedule interleaved",
            file=sys.stderr,
        )
        return 2
    if args.extra_arti_socks_connect_soft_timeout_ms and args.schedule != "interleaved":
        print(
            "--extra-arti-socks-connect-soft-timeout-ms requires --schedule interleaved",
            file=sys.stderr,
        )
        return 2
    if (
        args.extra_arti_socks_connect_soft_timeout_attempts
        and args.schedule != "interleaved"
    ):
        print(
            "--extra-arti-socks-connect-soft-timeout-attempts requires --schedule interleaved",
            file=sys.stderr,
        )
        return 2
    if args.extra_arti_socks_connect_hedge_ms and args.schedule != "interleaved":
        print(
            "--extra-arti-socks-connect-hedge-ms requires --schedule interleaved",
            file=sys.stderr,
        )
        return 2
    if (
        args.extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_partial_retry_chunking_socks_connect_hedge_ms
        and args.schedule != "interleaved"
    ):
        print(
            "--extra-arti-dir-microdesc-source-spread-pending-spread-early-usable-load-aware-partial-retry-chunking-socks-connect-hedge-ms requires --schedule interleaved",
            file=sys.stderr,
        )
        return 2
    if (
        args.extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_partial_retry_chunking_socks_connect_soft_timeout_combo
        and args.schedule != "interleaved"
    ):
        print(
            "--extra-arti-dir-microdesc-source-spread-pending-spread-early-usable-load-aware-partial-retry-chunking-socks-connect-soft-timeout-combo requires --schedule interleaved",
            file=sys.stderr,
        )
        return 2
    if (
        args.extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_partial_retry_chunking_hs_rend_prebuild_before_desc
        and args.schedule != "interleaved"
    ):
        print(
            "--extra-arti-dir-microdesc-source-spread-pending-spread-early-usable-load-aware-partial-retry-chunking-hs-rend-prebuild-before-desc requires --schedule interleaved",
            file=sys.stderr,
        )
        return 2
    if (
        args.extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_partial_retry_chunking_hs_rend_prebuild_before_desc
        and args.schedule != "interleaved"
    ):
        print(
            "--extra-arti-dir-microdesc-source-spread-pending-spread-early-usable-partial-retry-chunking-hs-rend-prebuild-before-desc requires --schedule interleaved",
            file=sys.stderr,
        )
        return 2
    if (
        args.extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_partial_retry_chunking_bad_health_replacement_gate
        and args.schedule != "interleaved"
    ):
        print(
            "--extra-arti-dir-microdesc-source-spread-pending-spread-early-usable-load-aware-partial-retry-chunking-bad-health-replacement-gate requires --schedule interleaved",
            file=sys.stderr,
        )
        return 2
    if (
        args.extra_arti_socks_connect_soft_timeout_combo
        and args.schedule != "interleaved"
    ):
        print(
            "--extra-arti-socks-connect-soft-timeout-combo requires --schedule interleaved",
            file=sys.stderr,
        )
        return 2
    if (
        args.extra_arti_socks_connect_soft_timeout_pending_hedge_combo
        and args.schedule != "interleaved"
    ):
        print(
            "--extra-arti-socks-connect-soft-timeout-pending-hedge-combo requires --schedule interleaved",
            file=sys.stderr,
        )
        return 2
    if args.extra_arti_exit_pending_hedge_ms and args.schedule != "interleaved":
        print(
            "--extra-arti-exit-pending-hedge-ms requires --schedule interleaved",
            file=sys.stderr,
        )
        return 2
    if args.extra_arti_dirclient_read_timeout_ms and args.schedule != "interleaved":
        print(
            "--extra-arti-dirclient-read-timeout-ms requires --schedule interleaved",
            file=sys.stderr,
        )
        return 2
    if (
        args.extra_arti_dir_microdesc_early_usable_notify
        and args.schedule != "interleaved"
    ):
        print(
            "--extra-arti-dir-microdesc-early-usable-notify requires --schedule interleaved",
            file=sys.stderr,
        )
        return 2
    if (
        args.extra_arti_dir_microdesc_source_spread_pending_spread_early_usable
        and args.schedule != "interleaved"
    ):
        print(
            "--extra-arti-dir-microdesc-source-spread-pending-spread-early-usable requires --schedule interleaved",
            file=sys.stderr,
        )
        return 2
    if (
        args.extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware
        and args.schedule != "interleaved"
    ):
        print(
            "--extra-arti-dir-microdesc-source-spread-pending-spread-early-usable-load-aware requires --schedule interleaved",
            file=sys.stderr,
        )
        return 2
    if (
        args.extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_no_dir_bad_health_replacement
        and args.schedule != "interleaved"
    ):
        print(
            "--extra-arti-dir-microdesc-source-spread-pending-spread-early-usable-load-aware-no-dir-bad-health-replacement requires --schedule interleaved",
            file=sys.stderr,
        )
        return 2
    if (
        args.extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_bad_health_replacement_suppress_gap_ms
        and args.schedule != "interleaved"
    ):
        print(
            "--extra-arti-dir-microdesc-source-spread-pending-spread-early-usable-load-aware-bad-health-replacement-suppress-gap-ms requires --schedule interleaved",
            file=sys.stderr,
        )
        return 2
    if (
        args.extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_bad_health_replacement_gate
        and args.schedule != "interleaved"
    ):
        print(
            "--extra-arti-dir-microdesc-source-spread-pending-spread-early-usable-load-aware-bad-health-replacement-gate requires --schedule interleaved",
            file=sys.stderr,
        )
        return 2
    if (
        args.extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_early_retry_on_partial
        and args.schedule != "interleaved"
    ):
        print(
            "--extra-arti-dir-microdesc-source-spread-pending-spread-early-usable-load-aware-early-retry-on-partial requires --schedule interleaved",
            file=sys.stderr,
        )
        return 2
    if (
        args.extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_partial_retry_chunking
        and args.schedule != "interleaved"
    ):
        print(
            "--extra-arti-dir-microdesc-source-spread-pending-spread-early-usable-load-aware-partial-retry-chunking requires --schedule interleaved",
            file=sys.stderr,
        )
        return 2
    if (
        args.extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_partial_retry_chunking_max_active_streams
        and args.schedule != "interleaved"
    ):
        print(
            "--extra-arti-dir-microdesc-source-spread-pending-spread-early-usable-load-aware-partial-retry-chunking-max-active-streams requires --schedule interleaved",
            file=sys.stderr,
        )
        return 2
    if (
        args.extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_partial_retry_chunking
        and args.schedule != "interleaved"
    ):
        print(
            "--extra-arti-dir-microdesc-source-spread-pending-spread-early-usable-partial-retry-chunking requires --schedule interleaved",
            file=sys.stderr,
        )
        return 2
    if (
        args.extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_partial_retry_chunking_max_active_streams
        and args.schedule != "interleaved"
    ):
        print(
            "--extra-arti-dir-microdesc-source-spread-pending-spread-early-usable-partial-retry-chunking-max-active-streams requires --schedule interleaved",
            file=sys.stderr,
        )
        return 2
    if (
        args.extra_arti_dir_microdesc_source_spread_pending_spread
        and args.schedule != "interleaved"
    ):
        print(
            "--extra-arti-dir-microdesc-source-spread-pending-spread requires --schedule interleaved",
            file=sys.stderr,
        )
        return 2
    if (
        args.extra_arti_dir_microdesc_retry_ids_per_request
        and args.schedule != "interleaved"
    ):
        print(
            "--extra-arti-dir-microdesc-retry-ids-per-request requires --schedule interleaved",
            file=sys.stderr,
        )
        return 2
    if args.extra_arti_exit_select_load_aware and args.schedule != "interleaved":
        print(
            "--extra-arti-exit-select-load-aware requires --schedule interleaved",
            file=sys.stderr,
        )
        return 2
    if args.extra_arti_exit_select_health_aware and args.schedule != "interleaved":
        print(
            "--extra-arti-exit-select-health-aware requires --schedule interleaved",
            file=sys.stderr,
        )
        return 2
    if (
        args.extra_arti_exit_select_health_min_move_score_bps
        and args.schedule != "interleaved"
    ):
        print(
            "--extra-arti-exit-select-health-min-move-score-bps requires --schedule interleaved",
            file=sys.stderr,
        )
        return 2
    if (
        extra_health_min_assigned_cap_combos
        and args.schedule != "interleaved"
    ):
        print(
            "--extra-arti-exit-select-health-min-move-score-assigned-cap requires --schedule interleaved",
            file=sys.stderr,
        )
        return 2
    if (
        args.extra_arti_exit_select_health_aware_min_assignment_spread
        and args.schedule != "interleaved"
    ):
        print(
            "--extra-arti-exit-select-health-aware-min-assignment-spread requires --schedule interleaved",
            file=sys.stderr,
        )
        return 2
    if (
        args.extra_arti_exit_select_health_aware_min_assigned
        and args.schedule != "interleaved"
    ):
        print(
            "--extra-arti-exit-select-health-aware-min-assigned requires --schedule interleaved",
            file=sys.stderr,
        )
        return 2
    if args.extra_arti_exit_select_avoid_bad_health and args.schedule != "interleaved":
        print(
            "--extra-arti-exit-select-avoid-bad-health requires --schedule interleaved",
            file=sys.stderr,
        )
        return 2
    if (
        args.extra_arti_exit_select_health_aware_avoid_bad_health
        and args.schedule != "interleaved"
    ):
        print(
            "--extra-arti-exit-select-health-aware-avoid-bad-health requires --schedule interleaved",
            file=sys.stderr,
        )
        return 2
    if (
        args.extra_arti_exit_select_health_aware_avoid_bad_health_same_isolation_target
        and args.schedule != "interleaved"
    ):
        print(
            "--extra-arti-exit-select-health-aware-avoid-bad-health-same-isolation-target requires --schedule interleaved",
            file=sys.stderr,
        )
        return 2
    if (
        args.extra_arti_exit_select_prefer_cold_same_isolation_target
        and args.schedule != "interleaved"
    ):
        print(
            "--extra-arti-exit-select-prefer-cold-same-isolation-target requires --schedule interleaved",
            file=sys.stderr,
        )
        return 2
    if (
        extra_prefer_cold_sameiso_active_cap_combos
        and args.schedule != "interleaved"
    ):
        print(
            "--extra-arti-exit-select-prefer-cold-same-isolation-active-cap requires --schedule interleaved",
            file=sys.stderr,
        )
        return 2
    if (
        args.extra_arti_exit_select_prefer_cold_same_isolation_prewarm_target
        and args.schedule != "interleaved"
    ):
        print(
            "--extra-arti-exit-select-prefer-cold-same-isolation-prewarm-target requires --schedule interleaved",
            file=sys.stderr,
        )
        return 2
    if (
        extra_health_aware_sameiso_prefer_cold_prewarm_pending_wait_combos
        and args.schedule != "interleaved"
    ):
        print(
            "--extra-arti-exit-select-health-aware-same-isolation-prefer-cold-prewarm-pending-wait requires --schedule interleaved",
            file=sys.stderr,
        )
        return 2
    if (
        args.extra_arti_exit_select_health_aware_same_isolation_prefer_cold_target
        and args.schedule != "interleaved"
    ):
        print(
            "--extra-arti-exit-select-health-aware-same-isolation-prefer-cold-target requires --schedule interleaved",
            file=sys.stderr,
        )
        return 2
    if (
        extra_health_min_sameiso_pending_wait_combos
        and args.schedule != "interleaved"
    ):
        print(
            "--extra-arti-exit-select-health-min-move-score-same-isolation-pending-wait requires --schedule interleaved",
            file=sys.stderr,
        )
        return 2
    if (
        args.extra_arti_exit_select_avoid_bad_health_unknown_fallback_prefer_cold_same_isolation_target
        and args.schedule != "interleaved"
    ):
        print(
            "--extra-arti-exit-select-avoid-bad-health-unknown-fallback-prefer-cold-same-isolation-target requires --schedule interleaved",
            file=sys.stderr,
        )
        return 2
    if args.extra_arti_exit_select_min_assignment_spread and args.schedule != "interleaved":
        print(
            "--extra-arti-exit-select-min-assignment-spread requires --schedule interleaved",
            file=sys.stderr,
        )
        return 2
    if (
        args.extra_arti_exit_select_healthy_over_cold_min_assigned
        and args.schedule != "interleaved"
    ):
        print(
            "--extra-arti-exit-select-healthy-over-cold-min-assigned requires --schedule interleaved",
            file=sys.stderr,
        )
        return 2
    if (
        args.extra_arti_exit_select_healthy_over_cold_guard_only_min_assigned
        and args.schedule != "interleaved"
    ):
        print(
            "--extra-arti-exit-select-healthy-over-cold-guard-only-min-assigned requires --schedule interleaved",
            file=sys.stderr,
        )
        return 2
    if (
        args.extra_arti_exit_select_bad_health_active_no_data_ms
        and args.schedule != "interleaved"
    ):
        print(
            "--extra-arti-exit-select-bad-health-active-no-data-ms requires --schedule interleaved",
            file=sys.stderr,
        )
        return 2
    if (
        args.extra_arti_exit_select_bad_health_hedge_ms
        and args.schedule != "interleaved"
    ):
        print(
            "--extra-arti-exit-select-bad-health-hedge-ms requires --schedule interleaved",
            file=sys.stderr,
        )
        return 2
    if args.extra_arti_exit_same_isolation_target and args.schedule != "interleaved":
        print(
            "--extra-arti-exit-same-isolation-target requires --schedule interleaved",
            file=sys.stderr,
        )
        return 2
    if (
        args.extra_arti_exit_same_isolation_other_isolation_pressure
        and args.schedule != "interleaved"
    ):
        print(
            "--extra-arti-exit-same-isolation-other-isolation-pressure requires --schedule interleaved",
            file=sys.stderr,
        )
        return 2
    if (
        extra_sameiso_other_iso_assigned_cap_combos
        and args.schedule != "interleaved"
    ):
        print(
            "--extra-arti-exit-same-isolation-other-isolation-pressure-assigned-cap requires --schedule interleaved",
            file=sys.stderr,
        )
        return 2
    if (
        extra_sameiso_other_iso_assigned_cap_prewarm_combos
        and args.schedule != "interleaved"
    ):
        print(
            "--extra-arti-exit-same-isolation-other-isolation-pressure-assigned-cap-prewarm requires --schedule interleaved",
            file=sys.stderr,
        )
        return 2
    if (
        extra_prefer_cold_sameiso_other_iso_pressure_combos
        and args.schedule != "interleaved"
    ):
        print(
            "--extra-arti-exit-select-prefer-cold-same-isolation-other-isolation-pressure requires --schedule interleaved",
            file=sys.stderr,
        )
        return 2
    if (
        args.extra_arti_exit_load_aware_same_isolation_target
        and args.schedule != "interleaved"
    ):
        print(
            "--extra-arti-exit-load-aware-same-isolation-target requires --schedule interleaved",
            file=sys.stderr,
        )
        return 2
    if (
        args.extra_arti_exit_same_isolation_prewarm_target
        and args.schedule != "interleaved"
    ):
        print(
            "--extra-arti-exit-same-isolation-prewarm-target requires --schedule interleaved",
            file=sys.stderr,
        )
        return 2
    if (
        args.extra_arti_exit_same_isolation_min_assigned_streams
        and args.schedule != "interleaved"
    ):
        print(
            "--extra-arti-exit-same-isolation-min-assigned-streams requires --schedule interleaved",
            file=sys.stderr,
        )
        return 2
    if (
        args.extra_arti_exit_same_isolation_prefer_topup_on_tie
        and args.schedule != "interleaved"
    ):
        print(
            "--extra-arti-exit-same-isolation-prefer-topup-on-tie requires --schedule interleaved",
            file=sys.stderr,
        )
        return 2
    if (
        args.extra_arti_exit_load_aware_same_isolation_prewarm_target
        and args.schedule != "interleaved"
    ):
        print(
            "--extra-arti-exit-load-aware-same-isolation-prewarm-target requires --schedule interleaved",
            file=sys.stderr,
        )
        return 2
    if (
        args.extra_arti_exit_health_aware_same_isolation_prewarm_target
        and args.schedule != "interleaved"
    ):
        print(
            "--extra-arti-exit-health-aware-same-isolation-prewarm-target requires --schedule interleaved",
            file=sys.stderr,
        )
        return 2
    if args.extra_arti_proxy_buffer_size and args.schedule != "interleaved":
        print("--extra-arti-proxy-buffer-size requires --schedule interleaved", file=sys.stderr)
        return 2
    if args.extra_arti_proxy_app_buffer_len and args.schedule != "interleaved":
        print(
            "--extra-arti-proxy-app-buffer-len requires --schedule interleaved",
            file=sys.stderr,
        )
        return 2
    if (
        args.extra_arti_socks_tor_to_client_coalesce_bytes
        and args.schedule != "interleaved"
    ):
        print(
            "--extra-arti-socks-tor-to-client-coalesce-bytes requires --schedule interleaved",
            file=sys.stderr,
        )
        return 2
    if (
        args.extra_arti_stream_ready_data_coalesce_bytes
        and args.schedule != "interleaved"
    ):
        print(
            "--extra-arti-stream-ready-data-coalesce-bytes requires --schedule interleaved",
            file=sys.stderr,
        )
        return 2
    invalid_extra_coalesce_bytes = [
        value
        for value in args.extra_arti_socks_tor_to_client_coalesce_bytes
        if not (498 <= value <= 65_536)
    ]
    if invalid_extra_coalesce_bytes:
        print(
            "--extra-arti-socks-tor-to-client-coalesce-bytes must be between 498 and 65536",
            file=sys.stderr,
        )
        return 2
    invalid_extra_ready_data_coalesce_bytes = [
        value
        for value in args.extra_arti_stream_ready_data_coalesce_bytes
        if not (498 <= value <= 65_536)
    ]
    if invalid_extra_ready_data_coalesce_bytes:
        print(
            "--extra-arti-stream-ready-data-coalesce-bytes must be between 498 and 65536",
            file=sys.stderr,
        )
        return 2
    if args.arti_stream_scheduler_burst is not None and not (
        1 <= args.arti_stream_scheduler_burst <= 8
    ):
        print(
            "--arti-stream-scheduler-burst must be between 1 and 8",
            file=sys.stderr,
        )
        return 2
    if args.extra_arti_stream_scheduler_burst and args.schedule != "interleaved":
        print(
            "--extra-arti-stream-scheduler-burst requires --schedule interleaved",
            file=sys.stderr,
        )
        return 2
    invalid_extra_stream_scheduler_bursts = [
        value
        for value in args.extra_arti_stream_scheduler_burst
        if not (1 <= value <= 8)
    ]
    if invalid_extra_stream_scheduler_bursts:
        print(
            "--extra-arti-stream-scheduler-burst must be between 1 and 8",
            file=sys.stderr,
        )
        return 2
    proxy_app_buffer_values = [
        value
        for value in [
            args.arti_proxy_app_buffer_len,
            *args.extra_arti_proxy_app_buffer_len,
        ]
        if value is not None
    ]
    invalid_proxy_app_buffers = [
        value for value in proxy_app_buffer_values if not (4096 <= value <= 1048576)
    ]
    if invalid_proxy_app_buffers:
        print(
            "--arti-proxy-app-buffer-len values must be between 4096 and 1048576",
            file=sys.stderr,
        )
        return 2
    if extra_arti_bins and args.schedule != "interleaved":
        print("--extra-arti-bin requires --schedule interleaved", file=sys.stderr)
        return 2
    main_ports = {args.tor_port, args.local_tor_port, args.arti_port}
    extra_arti_count = len(args.extra_arti_exit_select_parallelism) + len(
        args.extra_arti_exit_launch_parallelism
    ) + len(
        args.extra_arti_hspool_launch_parallelism
    ) + len(
        args.extra_arti_hspool_background_start_delay_ms
    ) + len(
        args.extra_arti_hspool_guarded_stem_target
    ) + len(
        args.extra_arti_hspool_on_demand_grace_ms
    ) + len(
        args.extra_arti_hspool_on_demand_race_ms
    ) + int(
        args.extra_arti_hs_intro_rend_overlap
    ) + int(
        args.extra_arti_hs_rend_prebuild_before_desc
    ) + int(
        args.extra_arti_hs_desc_shared_cache
    ) + len(
        args.extra_arti_hs_intro_circuit_hedge_ms
    ) + len(
        args.extra_arti_min_exit_circs_for_port
    ) + len(
        args.extra_arti_preemptive_443_circs
    ) + len(
        args.extra_arti_socks_connect_soft_timeout_ms
    ) + len(
        args.extra_arti_socks_connect_soft_timeout_attempts
    ) + len(
        args.extra_arti_socks_connect_hedge_ms
    ) + len(
        extra_soft_timeout_combos
    ) + len(
        extra_soft_timeout_pending_hedge_combos
    ) + len(
        args.extra_arti_socks_no_tor_byte_relay_timeout_ms
    ) + len(
        args.extra_arti_socks_partial_relay_idle_timeout_ms
    ) + len(args.extra_arti_exit_pending_hedge_ms) + len(
        args.extra_arti_dirclient_read_timeout_ms
    ) + int(
        args.extra_arti_dir_microdesc_early_usable_notify
    ) + int(
        args.extra_arti_dir_microdesc_source_spread_pending_spread_early_usable
    ) + int(
        args.extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware
    ) + int(
        args.extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_early_retry_on_partial
    ) + int(
        args.extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_partial_retry_chunking
    ) + int(
        args.extra_arti_dir_microdesc_source_spread_pending_spread
    ) + len(
        args.extra_arti_dir_microdesc_retry_ids_per_request
    ) + int(
        args.extra_arti_exit_select_load_aware
    ) + int(
        args.extra_arti_exit_select_health_aware
    ) + len(
        args.extra_arti_exit_select_health_min_move_score_bps
    ) + len(
        extra_health_min_assigned_cap_combos
    ) + len(
        args.extra_arti_exit_select_health_aware_min_assignment_spread
    ) + len(
        args.extra_arti_exit_select_health_aware_min_assigned
    ) + int(
        args.extra_arti_exit_select_avoid_bad_health
    ) + int(
        args.extra_arti_exit_select_health_aware_avoid_bad_health
    ) + len(
        args.extra_arti_exit_select_health_aware_avoid_bad_health_same_isolation_target
    ) + len(
        args.extra_arti_exit_select_health_aware_same_isolation_prefer_cold_target
    ) + len(
        args.extra_arti_exit_select_prefer_cold_same_isolation_target
    ) + len(
        extra_prefer_cold_sameiso_active_cap_combos
    ) + len(
        args.extra_arti_exit_select_prefer_cold_same_isolation_prewarm_target
    ) + len(
        extra_health_aware_sameiso_prefer_cold_prewarm_pending_wait_combos
    ) + len(
        args.extra_arti_exit_select_avoid_bad_health_unknown_fallback_prefer_cold_same_isolation_target
    ) + len(
        args.extra_arti_exit_select_min_assignment_spread
    ) + len(
        args.extra_arti_exit_select_healthy_over_cold_min_assigned
    ) + len(
        args.extra_arti_exit_select_healthy_over_cold_guard_only_min_assigned
    ) + len(
        args.extra_arti_exit_select_max_active_streams
    ) + len(
        args.extra_arti_exit_select_max_assigned_streams
    ) + len(
        args.extra_arti_exit_select_bad_health_active_no_data_ms
    ) + len(
        args.extra_arti_exit_select_bad_health_hedge_ms
    ) + len(
        args.extra_arti_exit_same_isolation_target
    ) + len(
        extra_sameiso_other_iso_pressure_combos
    ) + len(
        extra_sameiso_other_iso_assigned_cap_combos
    ) + len(
        extra_prefer_cold_sameiso_other_iso_pressure_combos
    ) + len(
        extra_sameiso_other_iso_assigned_cap_prewarm_combos
    ) + len(
        args.extra_arti_exit_load_aware_same_isolation_target
    ) + len(
        args.extra_arti_exit_same_isolation_prewarm_target
    ) + len(
        extra_sameiso_min_assigned_combos
    ) + len(
        args.extra_arti_exit_load_aware_same_isolation_prewarm_target
    ) + len(
        args.extra_arti_exit_health_aware_same_isolation_prewarm_target
    ) + len(
        extra_health_min_sameiso_pending_wait_combos
    ) + len(
        args.extra_arti_proxy_buffer_size
    ) + len(
        args.extra_arti_proxy_app_buffer_len
    ) + len(
        args.extra_arti_stream_scheduler_burst
    ) + len(
        extra_arti_bins
    )
    extra_ports = {
        args.extra_arti_port_start + index
        for index in range(extra_arti_count)
    }
    if main_ports & extra_ports or len(extra_ports) != extra_arti_count:
        print("extra Arti ports must not overlap existing proxy ports", file=sys.stderr)
        return 2

    run_id = time.strftime("%Y%m%dT%H%M%S")
    output_dir = Path("results") / f"browser-compare-{run_id}"
    output_dir.mkdir(parents=True, exist_ok=True)

    default_prefs = read_browser_default_prefs(browser_bin)
    payload: dict[str, object] = {
        "run_id": run_id,
        "runs_per_target": args.runs,
        "targets": args.targets,
        "window_size": args.window_size,
        "cache_mode": "warm" if args.warm_cache else "cold",
        "compact_output": args.compact_output,
        "proxy_run_tail_lines": args.proxy_run_tail_lines,
        "schedule": args.schedule,
        "post_boot_wait_seconds": args.post_boot_wait,
        "skip_bundled_tor": args.skip_bundled_tor,
        "arti_proxy_buffer_size": args.arti_proxy_buffer_size,
        "arti_proxy_app_buffer_len": args.arti_proxy_app_buffer_len,
        "arti_stream_scheduler_burst": args.arti_stream_scheduler_burst,
        "arti_exit_select_parallelism_override": args.arti_exit_select_parallelism,
        "arti_exit_launch_parallelism_override": args.arti_exit_launch_parallelism,
        "arti_min_exit_circs_for_port_override": args.arti_min_exit_circs_for_port,
        "arti_socks_connect_soft_timeout_ms": args.arti_socks_connect_soft_timeout_ms,
        "arti_socks_connect_soft_timeout_attempts": (
            args.arti_socks_connect_soft_timeout_attempts
        ),
        "arti_socks_connect_hedge_ms": args.arti_socks_connect_hedge_ms,
        "arti_socks_relay_byte_timing": args.arti_socks_relay_byte_timing,
        "arti_socks_partial_relay_idle_timeout_ms": (
            args.arti_socks_partial_relay_idle_timeout_ms
        ),
        "arti_socks_no_tor_byte_relay_timeout_ms": (
            args.arti_socks_no_tor_byte_relay_timeout_ms
        ),
        "arti_dirclient_read_timeout_ms": args.arti_dirclient_read_timeout_ms,
        "arti_exit_pending_hedge_ms": args.arti_exit_pending_hedge_ms,
        "arti_exit_select_load_aware": args.arti_exit_select_load_aware,
        "arti_exit_select_health_aware": args.arti_exit_select_health_aware,
        "arti_exit_select_health_min_move_score_bps": (
            args.arti_exit_select_health_min_move_score_bps
        ),
        "arti_exit_select_avoid_bad_health": (
            args.arti_exit_select_avoid_bad_health
        ),
        "arti_exit_select_avoid_bad_health_unknown_fallback": (
            args.arti_exit_select_avoid_bad_health_unknown_fallback
        ),
        "arti_exit_select_bad_health_hedge_ms": (
            args.arti_exit_select_bad_health_hedge_ms
        ),
        "arti_exit_select_bad_health_stream_idle_ms": (
            args.arti_exit_select_bad_health_stream_idle_ms
        ),
        "arti_exit_select_bad_health_active_no_data_ms": (
            args.arti_exit_select_bad_health_active_no_data_ms
        ),
        "arti_exit_select_max_active_streams": (
            args.arti_exit_select_max_active_streams
        ),
        "arti_exit_select_max_assigned_streams": (
            args.arti_exit_select_max_assigned_streams
        ),
        "arti_exit_select_min_assignment_spread": (
            args.arti_exit_select_min_assignment_spread
        ),
        "arti_exit_select_healthy_over_cold_min_assigned": (
            args.arti_exit_select_healthy_over_cold_min_assigned
        ),
        "arti_exit_select_healthy_over_cold_guard_only_min_assigned": (
            args.arti_exit_select_healthy_over_cold_guard_only_min_assigned
        ),
        "arti_exit_same_isolation_target": args.arti_exit_same_isolation_target,
        "arti_hs_rend_prebuild_before_desc": (
            args.arti_hs_rend_prebuild_before_desc
        ),
        "arti_exit_same_isolation_require_bad_health": (
            args.arti_exit_same_isolation_require_bad_health
        ),
        "arti_exit_same_isolation_min_assigned_streams": (
            args.arti_exit_same_isolation_min_assigned_streams
        ),
        "arti_exit_select_prefer_cold_same_isolation": (
            args.arti_exit_select_prefer_cold_same_isolation
        ),
        "arti_exit_same_isolation_prewarm_first_stream": (
            args.arti_exit_same_isolation_prewarm_first_stream
        ),
        "extra_arti_exit_select_parallelism_overrides": (
            args.extra_arti_exit_select_parallelism
        ),
        "extra_arti_exit_launch_parallelism_overrides": (
            args.extra_arti_exit_launch_parallelism
        ),
        "extra_arti_hspool_launch_parallelism_overrides": (
            args.extra_arti_hspool_launch_parallelism
        ),
        "extra_arti_hspool_background_start_delay_ms": (
            args.extra_arti_hspool_background_start_delay_ms
        ),
        "extra_arti_hspool_guarded_stem_target": (
            args.extra_arti_hspool_guarded_stem_target
        ),
        "extra_arti_hspool_guarded_stem_target_defer_post_bootstrap": (
            args.extra_arti_hspool_guarded_stem_target_defer_post_bootstrap
        ),
        "extra_arti_hspool_on_demand_grace_ms": (
            args.extra_arti_hspool_on_demand_grace_ms
        ),
        "extra_arti_hspool_on_demand_race_ms": (
            args.extra_arti_hspool_on_demand_race_ms
        ),
        "extra_arti_hs_intro_rend_overlap": args.extra_arti_hs_intro_rend_overlap,
        "extra_arti_hs_rend_prebuild_before_desc": (
            args.extra_arti_hs_rend_prebuild_before_desc
        ),
        "extra_arti_hs_desc_shared_cache": args.extra_arti_hs_desc_shared_cache,
        "extra_arti_hs_intro_circuit_hedge_ms": (
            args.extra_arti_hs_intro_circuit_hedge_ms
        ),
        "extra_arti_min_exit_circs_for_port": (
            args.extra_arti_min_exit_circs_for_port
        ),
        "extra_arti_preemptive_443_circs": (
            args.extra_arti_preemptive_443_circs
        ),
        "extra_arti_preemptive_443_burst_min_requests": (
            args.extra_arti_preemptive_443_burst_min_requests
        ),
        "extra_arti_preemptive_443_busy_active_age_ms": (
            args.extra_arti_preemptive_443_busy_active_age_ms
        ),
        "extra_arti_socks_connect_soft_timeout_ms": (
            args.extra_arti_socks_connect_soft_timeout_ms
        ),
        "extra_arti_socks_connect_soft_timeout_attempts": (
            args.extra_arti_socks_connect_soft_timeout_attempts
        ),
        "extra_arti_socks_connect_hedge_ms": (
            args.extra_arti_socks_connect_hedge_ms
        ),
        "extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_partial_retry_chunking_socks_connect_hedge_ms": (
            args.extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_partial_retry_chunking_socks_connect_hedge_ms
        ),
        "extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_partial_retry_chunking_hs_rend_prebuild_before_desc": (
            args.extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_partial_retry_chunking_hs_rend_prebuild_before_desc
        ),
        "extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_partial_retry_chunking_bad_health_replacement_gate_combos": [
            {
                "gap_ms": gap_ms,
                "min_assigned_streams": min_assigned_streams,
                "min_active_streams": min_active_streams,
            }
            for gap_ms, min_assigned_streams, min_active_streams in (
                extra_dir_partial_retry_chunk_bad_health_gate_combos
            )
        ],
        "extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_partial_retry_chunking_socks_connect_soft_timeout_combos": [
            {"timeout_ms": timeout_ms, "attempts": attempts}
            for timeout_ms, attempts in extra_dir_combo_soft_timeout_combos
        ],
        "extra_arti_socks_connect_soft_timeout_combos": [
            {"timeout_ms": timeout_ms, "attempts": attempts}
            for timeout_ms, attempts in extra_soft_timeout_combos
        ],
        "extra_arti_socks_connect_soft_timeout_pending_hedge_combos": [
            {
                "timeout_ms": timeout_ms,
                "attempts": attempts,
                "hedge_ms": hedge_ms,
            }
            for timeout_ms, attempts, hedge_ms in (
                extra_soft_timeout_pending_hedge_combos
            )
        ],
        "extra_arti_socks_no_tor_byte_relay_timeout_ms": (
            args.extra_arti_socks_no_tor_byte_relay_timeout_ms
        ),
        "extra_arti_socks_partial_relay_idle_timeout_ms": (
            args.extra_arti_socks_partial_relay_idle_timeout_ms
        ),
        "extra_arti_exit_pending_hedge_ms": (
            args.extra_arti_exit_pending_hedge_ms
        ),
        "extra_arti_dirclient_read_timeout_ms": (
            args.extra_arti_dirclient_read_timeout_ms
        ),
        "extra_arti_dir_microdesc_early_usable_notify": (
            args.extra_arti_dir_microdesc_early_usable_notify
        ),
        "extra_arti_dir_microdesc_source_spread_pending_spread_early_usable": (
            args.extra_arti_dir_microdesc_source_spread_pending_spread_early_usable
        ),
        "extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware": (
            args.extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware
        ),
        "extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_no_dir_bad_health_replacement": (
            args.extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_no_dir_bad_health_replacement
        ),
        "extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_bad_health_replacement_suppress_gap_ms": (
            args.extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_bad_health_replacement_suppress_gap_ms
        ),
        "extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_bad_health_replacement_gate_combos": [
            {
                "gap_ms": gap_ms,
                "min_assigned_streams": min_assigned_streams,
                "min_active_streams": min_active_streams,
            }
            for gap_ms, min_assigned_streams, min_active_streams in (
                extra_dir_bad_health_gate_combos
            )
        ],
        "extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_early_retry_on_partial": (
            args.extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_early_retry_on_partial
        ),
        "extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_partial_retry_chunking": (
            args.extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_partial_retry_chunking
        ),
        "extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_partial_retry_chunking_max_active_streams": (
            args.extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_partial_retry_chunking_max_active_streams
        ),
        "extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_partial_retry_chunking": (
            args.extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_partial_retry_chunking
        ),
        "extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_partial_retry_chunking_max_active_streams": (
            args.extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_partial_retry_chunking_max_active_streams
        ),
        "extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_partial_retry_chunking_hs_rend_prebuild_before_desc": (
            args.extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_partial_retry_chunking_hs_rend_prebuild_before_desc
        ),
        "extra_arti_dir_microdesc_source_spread_pending_spread": (
            args.extra_arti_dir_microdesc_source_spread_pending_spread
        ),
        "extra_arti_dir_microdesc_retry_ids_per_request": (
            args.extra_arti_dir_microdesc_retry_ids_per_request
        ),
        "extra_arti_exit_select_load_aware": args.extra_arti_exit_select_load_aware,
        "extra_arti_exit_select_health_aware": (
            args.extra_arti_exit_select_health_aware
        ),
        "extra_arti_exit_select_health_min_move_score_bps": (
            args.extra_arti_exit_select_health_min_move_score_bps
        ),
        "extra_arti_exit_select_health_min_move_score_assigned_cap": [
            {"score": score, "cap": cap}
            for score, cap in extra_health_min_assigned_cap_combos
        ],
        "extra_arti_exit_select_health_aware_min_assignment_spread": (
            args.extra_arti_exit_select_health_aware_min_assignment_spread
        ),
        "extra_arti_exit_select_health_aware_min_assigned": (
            args.extra_arti_exit_select_health_aware_min_assigned
        ),
        "extra_arti_exit_select_avoid_bad_health": (
            args.extra_arti_exit_select_avoid_bad_health
        ),
        "extra_arti_exit_select_health_aware_avoid_bad_health": (
            args.extra_arti_exit_select_health_aware_avoid_bad_health
        ),
        "extra_arti_exit_select_health_aware_avoid_bad_health_same_isolation_target": (
            args.extra_arti_exit_select_health_aware_avoid_bad_health_same_isolation_target
        ),
        "extra_arti_exit_select_health_aware_same_isolation_prefer_cold_target": (
            args.extra_arti_exit_select_health_aware_same_isolation_prefer_cold_target
        ),
        "extra_arti_exit_select_prefer_cold_same_isolation_target": (
            args.extra_arti_exit_select_prefer_cold_same_isolation_target
        ),
        "extra_arti_exit_select_prefer_cold_same_isolation_active_cap": [
            {"target": target, "cap": cap}
            for target, cap in extra_prefer_cold_sameiso_active_cap_combos
        ],
        "extra_arti_exit_select_prefer_cold_same_isolation_prewarm_target": (
            args.extra_arti_exit_select_prefer_cold_same_isolation_prewarm_target
        ),
        "extra_arti_exit_select_health_aware_same_isolation_prefer_cold_prewarm_pending_wait": [
            {"target": target, "wait_ms": wait_ms}
            for target, wait_ms in (
                extra_health_aware_sameiso_prefer_cold_prewarm_pending_wait_combos
            )
        ],
        "extra_arti_exit_select_avoid_bad_health_unknown_fallback_prefer_cold_same_isolation_target": (
            args.extra_arti_exit_select_avoid_bad_health_unknown_fallback_prefer_cold_same_isolation_target
        ),
        "extra_arti_exit_select_min_assignment_spread": (
            args.extra_arti_exit_select_min_assignment_spread
        ),
        "extra_arti_exit_select_healthy_over_cold_min_assigned": (
            args.extra_arti_exit_select_healthy_over_cold_min_assigned
        ),
        "extra_arti_exit_select_healthy_over_cold_guard_only_min_assigned": (
            args.extra_arti_exit_select_healthy_over_cold_guard_only_min_assigned
        ),
        "extra_arti_exit_select_max_active_streams": (
            args.extra_arti_exit_select_max_active_streams
        ),
        "extra_arti_exit_select_max_assigned_streams": (
            args.extra_arti_exit_select_max_assigned_streams
        ),
        "extra_arti_exit_select_bad_health_active_no_data_ms": (
            args.extra_arti_exit_select_bad_health_active_no_data_ms
        ),
        "extra_arti_exit_select_bad_health_hedge_ms": (
            args.extra_arti_exit_select_bad_health_hedge_ms
        ),
        "extra_arti_exit_same_isolation_target": (
            args.extra_arti_exit_same_isolation_target
        ),
        "extra_arti_exit_same_isolation_other_isolation_pressure": [
            {"target": target, "minimum": minimum}
            for target, minimum in extra_sameiso_other_iso_pressure_combos
        ],
        "extra_arti_exit_same_isolation_other_isolation_pressure_assigned_cap": [
            {"target": target, "minimum": minimum, "cap": cap}
            for target, minimum, cap in extra_sameiso_other_iso_assigned_cap_combos
        ],
        "extra_arti_exit_same_isolation_other_isolation_pressure_assigned_cap_prewarm": [
            {"target": target, "minimum": minimum, "cap": cap}
            for target, minimum, cap in extra_sameiso_other_iso_assigned_cap_prewarm_combos
        ],
        "extra_arti_exit_select_prefer_cold_same_isolation_other_isolation_pressure": [
            {"target": target, "minimum": minimum}
            for target, minimum in extra_prefer_cold_sameiso_other_iso_pressure_combos
        ],
        "extra_arti_exit_load_aware_same_isolation_target": (
            args.extra_arti_exit_load_aware_same_isolation_target
        ),
        "extra_arti_exit_same_isolation_prewarm_target": (
            args.extra_arti_exit_same_isolation_prewarm_target
        ),
        "extra_arti_exit_same_isolation_min_assigned_streams": [
            {"target": target, "min_assigned": min_assigned}
            for target, min_assigned in extra_sameiso_min_assigned_combos
        ],
        "extra_arti_exit_same_isolation_prefer_topup_on_tie": (
            args.extra_arti_exit_same_isolation_prefer_topup_on_tie
        ),
        "extra_arti_exit_load_aware_same_isolation_prewarm_target": (
            args.extra_arti_exit_load_aware_same_isolation_prewarm_target
        ),
        "extra_arti_exit_health_aware_same_isolation_prewarm_target": (
            args.extra_arti_exit_health_aware_same_isolation_prewarm_target
        ),
        "extra_arti_exit_select_health_min_move_score_same_isolation_pending_wait": [
            {"target": target, "score": score, "wait_ms": wait_ms}
            for target, score, wait_ms in extra_health_min_sameiso_pending_wait_combos
        ],
        "arti_exit_same_isolation_pending_wait_ms": (
            args.arti_exit_same_isolation_pending_wait_ms
        ),
        "extra_arti_proxy_buffer_size": args.extra_arti_proxy_buffer_size,
        "extra_arti_proxy_app_buffer_len": args.extra_arti_proxy_app_buffer_len,
        "extra_arti_stream_scheduler_burst": args.extra_arti_stream_scheduler_burst,
        "extra_arti_socks_tor_to_client_coalesce_bytes": (
            args.extra_arti_socks_tor_to_client_coalesce_bytes
        ),
        "extra_arti_stream_ready_data_coalesce_bytes": (
            args.extra_arti_stream_ready_data_coalesce_bytes
        ),
        "extra_arti_bins": [
            {"profile": profile_name, "path": str(path)}
            for profile_name, path in extra_arti_bins
        ],
        "byte_tap": {
            "enabled": args.byte_tap,
            "port_offset": args.byte_tap_port_offset,
            "event_limit_per_direction": args.byte_tap_event_limit,
            "socks_reply_bind_port_tag": args.byte_tap_socks_reply_bind_port_tag,
        },
        "browser_lab": {
            "serial_http_connections": args.browser_serial_http_connections,
            "max_persistent_connections_per_server": (
                args.browser_max_persistent_connections_per_server
            ),
        },
        "browser_request_blocker": {
            "enabled": bool(browser_block_url_substrings),
            "url_substrings": browser_block_url_substrings,
        },
        "browser_net_log": {
            "enabled": args.browser_net_log,
            "moz_log": BROWSER_NET_MOZ_LOG if args.browser_net_log else None,
        },
        "browser_startup_seed": {
            "enabled": not args.no_browser_startup_seed,
            "seed_root": str(Path(args.browser_startup_seed_root).resolve()),
        },
        "system": {
            "platform": platform.platform(),
            "python": platform.python_version(),
        },
        "binaries": {
            "browser": {
                "path": str(browser_bin),
                "version": run_version([str(browser_bin), "--version"]),
            },
            "bundled_tor": binary_info(bundled_tor_bin),
            "local_c_tor": binary_info(tor_bin),
            "arti_release": binary_info(arti_bin),
        },
        "source_tweaks": detect_source_tweaks(Path("upstream/arti")),
        "browser_default_prefs": default_prefs,
        "browser_quality": {
            "default_prefs": validate_default_prefs(default_prefs),
            "no_marionette_fingerprint": collect_no_marionette_fingerprint_snapshot(
                browser_bin=browser_bin,
                output_dir=output_dir,
                window_size=args.window_size,
                compact_output=args.compact_output,
            ),
        },
        "profiles": {},
    }
    if args.schedule == "interleaved":
        payload["interleaved_order_strategy"] = "balanced_latin_square"
        payload["interleaved_launch_strategy"] = "warmup_boot_alignment"
        payload["interleaved_target_order_strategy"] = (
            "rotating_round_robin"
            if args.interleaved_target_order == "rotating"
            else "fixed_input_order"
        )

    if args.schedule == "interleaved":
        profiles = run_interleaved_profiles(
            bundled_tor_bin=bundled_tor_bin,
            tor_bin=tor_bin,
            arti_bin=arti_bin,
            ports={
                "bundled_c_tor_browser": args.tor_port,
                "local_c_tor_browser": args.local_tor_port,
                "arti_release_browser": args.arti_port,
            },
            output_dir=output_dir,
            browser_bin=browser_bin,
            targets=args.targets,
            runs=args.runs,
            timeout=args.timeout,
            window_size=args.window_size,
            warm_cache=args.warm_cache,
            share_arti_warm_cache_seed=args.share_arti_warm_cache_seed,
            compact_output=args.compact_output,
            post_boot_wait=args.post_boot_wait,
            arti_log_level=args.arti_log_level,
            arti_proxy_buffer_size=args.arti_proxy_buffer_size,
            arti_proxy_app_buffer_len=args.arti_proxy_app_buffer_len,
            arti_exit_select_parallelism=args.arti_exit_select_parallelism,
            arti_exit_launch_parallelism=args.arti_exit_launch_parallelism,
            arti_min_exit_circs_for_port=args.arti_min_exit_circs_for_port,
            arti_socks_connect_soft_timeout_ms=(
                args.arti_socks_connect_soft_timeout_ms
            ),
            arti_socks_connect_soft_timeout_attempts=(
                args.arti_socks_connect_soft_timeout_attempts
            ),
            arti_socks_connect_hedge_ms=args.arti_socks_connect_hedge_ms,
            arti_socks_relay_byte_timing=args.arti_socks_relay_byte_timing,
            arti_socks_partial_relay_idle_timeout_ms=(
                args.arti_socks_partial_relay_idle_timeout_ms
            ),
            arti_socks_no_tor_byte_relay_timeout_ms=(
                args.arti_socks_no_tor_byte_relay_timeout_ms
            ),
            arti_dirclient_read_timeout_ms=args.arti_dirclient_read_timeout_ms,
            arti_exit_pending_hedge_ms=args.arti_exit_pending_hedge_ms,
            arti_exit_select_load_aware=args.arti_exit_select_load_aware,
            arti_exit_select_health_aware=args.arti_exit_select_health_aware,
            arti_exit_select_health_min_move_score_bps=(
                args.arti_exit_select_health_min_move_score_bps
            ),
            arti_exit_select_avoid_bad_health=(
                args.arti_exit_select_avoid_bad_health
            ),
            arti_exit_select_avoid_bad_health_unknown_fallback=(
                args.arti_exit_select_avoid_bad_health_unknown_fallback
            ),
            arti_exit_select_bad_health_hedge_ms=(
                args.arti_exit_select_bad_health_hedge_ms
            ),
            arti_exit_select_bad_health_stream_idle_ms=(
                args.arti_exit_select_bad_health_stream_idle_ms
            ),
            arti_exit_select_bad_health_active_no_data_ms=(
                args.arti_exit_select_bad_health_active_no_data_ms
            ),
            arti_exit_select_max_active_streams=(
                args.arti_exit_select_max_active_streams
            ),
            arti_exit_select_max_assigned_streams=(
                args.arti_exit_select_max_assigned_streams
            ),
            arti_exit_select_min_assignment_spread=(
                args.arti_exit_select_min_assignment_spread
            ),
            arti_exit_select_healthy_over_cold_min_assigned=(
                args.arti_exit_select_healthy_over_cold_min_assigned
            ),
            arti_exit_select_healthy_over_cold_guard_only_min_assigned=(
                args.arti_exit_select_healthy_over_cold_guard_only_min_assigned
            ),
            arti_exit_same_isolation_target=args.arti_exit_same_isolation_target,
            arti_exit_same_isolation_require_bad_health=(
                args.arti_exit_same_isolation_require_bad_health
            ),
            arti_exit_same_isolation_min_assigned_streams=(
                args.arti_exit_same_isolation_min_assigned_streams
            ),
            arti_exit_same_isolation_pending_wait_ms=(
                args.arti_exit_same_isolation_pending_wait_ms
            ),
            arti_exit_same_isolation_prewarm_first_stream=(
                args.arti_exit_same_isolation_prewarm_first_stream
            ),
            arti_hs_rend_prebuild_before_desc=(
                args.arti_hs_rend_prebuild_before_desc
            ),
            arti_exit_select_prefer_cold_same_isolation=(
                args.arti_exit_select_prefer_cold_same_isolation
            ),
            extra_arti_exit_select_parallelism=args.extra_arti_exit_select_parallelism,
            extra_arti_exit_launch_parallelism=args.extra_arti_exit_launch_parallelism,
            extra_arti_hspool_launch_parallelism=(
                args.extra_arti_hspool_launch_parallelism
            ),
            extra_arti_hspool_background_start_delay_ms=(
                args.extra_arti_hspool_background_start_delay_ms
            ),
            extra_arti_hspool_guarded_stem_target=(
                args.extra_arti_hspool_guarded_stem_target
            ),
            extra_arti_hspool_guarded_stem_target_defer_post_boot=(
                args.extra_arti_hspool_guarded_stem_target_defer_post_bootstrap
            ),
            extra_arti_hspool_on_demand_grace_ms=(
                args.extra_arti_hspool_on_demand_grace_ms
            ),
            extra_arti_hspool_on_demand_race_ms=(
                args.extra_arti_hspool_on_demand_race_ms
            ),
            extra_arti_hs_intro_rend_overlap=(
                args.extra_arti_hs_intro_rend_overlap
            ),
            extra_arti_hs_rend_prebuild_before_desc=(
                args.extra_arti_hs_rend_prebuild_before_desc
            ),
            extra_arti_hs_desc_shared_cache=args.extra_arti_hs_desc_shared_cache,
            extra_arti_hs_intro_circuit_hedge_ms=(
                args.extra_arti_hs_intro_circuit_hedge_ms
            ),
            extra_arti_min_exit_circs_for_port=(
                args.extra_arti_min_exit_circs_for_port
            ),
            extra_arti_preemptive_443_circs=(
                args.extra_arti_preemptive_443_circs
            ),
            extra_arti_preemptive_443_burst_min_requests=(
                args.extra_arti_preemptive_443_burst_min_requests
            ),
            extra_arti_preemptive_443_busy_active_age_ms=(
                args.extra_arti_preemptive_443_busy_active_age_ms
            ),
            extra_arti_socks_connect_soft_timeout_ms=(
                args.extra_arti_socks_connect_soft_timeout_ms
            ),
            extra_arti_socks_connect_soft_timeout_attempts=(
                args.extra_arti_socks_connect_soft_timeout_attempts
            ),
            extra_arti_socks_connect_hedge_ms=(
                args.extra_arti_socks_connect_hedge_ms
            ),
            extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_partial_retry_chunking_socks_connect_hedge_ms=(
                args.extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_partial_retry_chunking_socks_connect_hedge_ms
            ),
            extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_partial_retry_chunking_hs_rend_prebuild_before_desc=(
                args.extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_partial_retry_chunking_hs_rend_prebuild_before_desc
            ),
            extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_partial_retry_chunking_hs_rend_prebuild_before_desc=(
                args.extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_partial_retry_chunking_hs_rend_prebuild_before_desc
            ),
            extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_partial_retry_chunking_bad_health_replacement_gate_combos=(
                extra_dir_partial_retry_chunk_bad_health_gate_combos
            ),
            extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_partial_retry_chunking_socks_connect_soft_timeout_combos=(
                extra_dir_combo_soft_timeout_combos
            ),
            extra_arti_socks_connect_soft_timeout_combos=(
                extra_soft_timeout_combos
            ),
            extra_arti_socks_connect_soft_timeout_pending_hedge_combos=(
                extra_soft_timeout_pending_hedge_combos
            ),
            extra_arti_socks_no_tor_byte_relay_timeout_ms=(
                args.extra_arti_socks_no_tor_byte_relay_timeout_ms
            ),
            extra_arti_socks_partial_relay_idle_timeout_ms=(
                args.extra_arti_socks_partial_relay_idle_timeout_ms
            ),
            extra_arti_exit_pending_hedge_ms=args.extra_arti_exit_pending_hedge_ms,
            extra_arti_dirclient_read_timeout_ms=(
                args.extra_arti_dirclient_read_timeout_ms
            ),
            extra_arti_dir_microdesc_early_usable_notify=(
                args.extra_arti_dir_microdesc_early_usable_notify
            ),
            extra_arti_dir_microdesc_source_spread_pending_spread_early_usable=(
                args.extra_arti_dir_microdesc_source_spread_pending_spread_early_usable
            ),
            extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware=(
                args.extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware
            ),
            extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_no_dir_bad_health_replacement=(
                args.extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_no_dir_bad_health_replacement
            ),
            extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_bad_health_replacement_suppress_gap_ms=(
                args.extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_bad_health_replacement_suppress_gap_ms
            ),
            extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_bad_health_replacement_gate_combos=(
                extra_dir_bad_health_gate_combos
            ),
            extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_early_retry_on_partial=(
                args.extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_early_retry_on_partial
            ),
            extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_partial_retry_chunking=(
                args.extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_partial_retry_chunking
            ),
            extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_partial_retry_chunking_max_active_streams=(
                args.extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_partial_retry_chunking_max_active_streams
            ),
            extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_partial_retry_chunking=(
                args.extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_partial_retry_chunking
            ),
            extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_partial_retry_chunking_max_active_streams=(
                args.extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_partial_retry_chunking_max_active_streams
            ),
            extra_arti_dir_microdesc_source_spread_pending_spread=(
                args.extra_arti_dir_microdesc_source_spread_pending_spread
            ),
            extra_arti_dir_microdesc_retry_ids_per_request=(
                args.extra_arti_dir_microdesc_retry_ids_per_request
            ),
            extra_arti_exit_select_load_aware=args.extra_arti_exit_select_load_aware,
            extra_arti_exit_select_health_aware=(
                args.extra_arti_exit_select_health_aware
            ),
            extra_arti_exit_select_health_min_move_score_bps=(
                args.extra_arti_exit_select_health_min_move_score_bps
            ),
            extra_arti_exit_select_health_min_move_score_assigned_cap=(
                extra_health_min_assigned_cap_combos
            ),
            extra_arti_exit_select_health_aware_min_assignment_spread=(
                args.extra_arti_exit_select_health_aware_min_assignment_spread
            ),
            extra_arti_exit_select_health_aware_min_assigned=(
                args.extra_arti_exit_select_health_aware_min_assigned
            ),
            extra_arti_exit_select_avoid_bad_health=(
                args.extra_arti_exit_select_avoid_bad_health
            ),
            extra_arti_exit_select_health_aware_avoid_bad_health=(
                args.extra_arti_exit_select_health_aware_avoid_bad_health
            ),
            extra_arti_exit_select_health_aware_avoid_bad_health_same_isolation_target=(
                args.extra_arti_exit_select_health_aware_avoid_bad_health_same_isolation_target
            ),
            extra_arti_exit_select_health_aware_same_isolation_prefer_cold_target=(
                args.extra_arti_exit_select_health_aware_same_isolation_prefer_cold_target
            ),
            extra_arti_exit_select_prefer_cold_same_isolation_target=(
                args.extra_arti_exit_select_prefer_cold_same_isolation_target
            ),
            extra_arti_exit_select_prefer_cold_same_isolation_active_cap=(
                extra_prefer_cold_sameiso_active_cap_combos
            ),
            extra_arti_exit_select_prefer_cold_same_isolation_prewarm_target=(
                args.extra_arti_exit_select_prefer_cold_same_isolation_prewarm_target
            ),
            extra_arti_exit_select_health_aware_same_isolation_prefer_cold_prewarm_pending_wait=(
                extra_health_aware_sameiso_prefer_cold_prewarm_pending_wait_combos
            ),
            extra_arti_exit_select_avoid_bad_health_unknown_fallback_prefer_cold_same_isolation_target=(
                args.extra_arti_exit_select_avoid_bad_health_unknown_fallback_prefer_cold_same_isolation_target
            ),
            extra_arti_exit_select_min_assignment_spread=(
                args.extra_arti_exit_select_min_assignment_spread
            ),
            extra_arti_exit_select_healthy_over_cold_min_assigned=(
                args.extra_arti_exit_select_healthy_over_cold_min_assigned
            ),
            extra_arti_exit_select_healthy_over_cold_guard_only_min_assigned=(
                args.extra_arti_exit_select_healthy_over_cold_guard_only_min_assigned
            ),
            extra_arti_exit_select_max_active_streams=(
                args.extra_arti_exit_select_max_active_streams
            ),
            extra_arti_exit_select_max_assigned_streams=(
                args.extra_arti_exit_select_max_assigned_streams
            ),
            extra_arti_exit_select_bad_health_active_no_data_ms=(
                args.extra_arti_exit_select_bad_health_active_no_data_ms
            ),
            extra_arti_exit_select_bad_health_hedge_ms=(
                args.extra_arti_exit_select_bad_health_hedge_ms
            ),
            extra_arti_exit_same_isolation_target=(
                args.extra_arti_exit_same_isolation_target
            ),
            extra_arti_exit_same_isolation_other_isolation_pressure=(
                extra_sameiso_other_iso_pressure_combos
            ),
            extra_arti_exit_same_isolation_other_isolation_pressure_assigned_cap=(
                extra_sameiso_other_iso_assigned_cap_combos
            ),
            extra_arti_exit_same_isolation_other_isolation_pressure_assigned_cap_prewarm=(
                extra_sameiso_other_iso_assigned_cap_prewarm_combos
            ),
            extra_arti_exit_select_prefer_cold_same_isolation_other_isolation_pressure=(
                extra_prefer_cold_sameiso_other_iso_pressure_combos
            ),
            extra_arti_exit_load_aware_same_isolation_target=(
                args.extra_arti_exit_load_aware_same_isolation_target
            ),
            extra_arti_exit_same_isolation_prewarm_target=(
                args.extra_arti_exit_same_isolation_prewarm_target
            ),
            extra_arti_exit_same_isolation_min_assigned_streams=(
                extra_sameiso_min_assigned_combos
            ),
            extra_arti_exit_same_isolation_prefer_topup_on_tie=(
                args.extra_arti_exit_same_isolation_prefer_topup_on_tie
            ),
            extra_arti_exit_load_aware_same_isolation_prewarm_target=(
                args.extra_arti_exit_load_aware_same_isolation_prewarm_target
            ),
            extra_arti_exit_health_aware_same_isolation_prewarm_target=(
                args.extra_arti_exit_health_aware_same_isolation_prewarm_target
            ),
            extra_arti_exit_select_health_min_move_score_same_isolation_pending_wait=(
                extra_health_min_sameiso_pending_wait_combos
            ),
            arti_stream_scheduler_burst=args.arti_stream_scheduler_burst,
            extra_arti_proxy_buffer_size=args.extra_arti_proxy_buffer_size,
            extra_arti_proxy_app_buffer_len=args.extra_arti_proxy_app_buffer_len,
            extra_arti_stream_scheduler_burst=args.extra_arti_stream_scheduler_burst,
            extra_arti_socks_tor_to_client_coalesce_bytes=(
                args.extra_arti_socks_tor_to_client_coalesce_bytes
            ),
            extra_arti_stream_ready_data_coalesce_bytes=(
                args.extra_arti_stream_ready_data_coalesce_bytes
            ),
            extra_arti_bins=extra_arti_bins,
            extra_arti_port_start=args.extra_arti_port_start,
            include_bundled_tor=not args.skip_bundled_tor,
            proxy_log_tail_lines=args.proxy_log_tail_lines,
            proxy_run_tail_lines=args.proxy_run_tail_lines,
            byte_tap=args.byte_tap,
            byte_tap_port_offset=args.byte_tap_port_offset,
            byte_tap_event_limit=args.byte_tap_event_limit,
            byte_tap_socks_reply_bind_port_tag=(
                args.byte_tap_socks_reply_bind_port_tag
            ),
            browser_net_log=args.browser_net_log,
            browser_serial_http_connections=args.browser_serial_http_connections,
            browser_max_persistent_connections_per_server=(
                args.browser_max_persistent_connections_per_server
            ),
            browser_block_url_substrings=browser_block_url_substrings,
            browser_startup_seed_root=Path(args.browser_startup_seed_root).resolve(),
            no_browser_startup_seed=args.no_browser_startup_seed,
            interleaved_target_order=args.interleaved_target_order,
            source_tweaks=payload["source_tweaks"],
        )
    else:
        profiles: dict[str, object] = {}
        if not args.skip_bundled_tor and bundled_tor_bin.exists():
            profiles["bundled_c_tor_browser"] = run_c_tor(
                tor_bin=bundled_tor_bin,
                port=args.tor_port,
                output_dir=output_dir / "bundled_c_tor_browser",
                browser_bin=browser_bin,
                targets=args.targets,
                runs=args.runs,
                timeout=args.timeout,
                window_size=args.window_size,
                warm_cache=args.warm_cache,
                compact_output=args.compact_output,
                post_boot_wait=args.post_boot_wait,
                proxy_log_tail_lines=args.proxy_log_tail_lines,
                byte_tap=args.byte_tap,
                byte_tap_port_offset=args.byte_tap_port_offset,
                byte_tap_event_limit=args.byte_tap_event_limit,
                byte_tap_socks_reply_bind_port_tag=(
                    args.byte_tap_socks_reply_bind_port_tag
                ),
                browser_net_log=args.browser_net_log,
                browser_serial_http_connections=args.browser_serial_http_connections,
                browser_max_persistent_connections_per_server=(
                    args.browser_max_persistent_connections_per_server
                ),
                browser_block_url_substrings=browser_block_url_substrings,
                browser_startup_seed_root=Path(args.browser_startup_seed_root).resolve(),
                no_browser_startup_seed=args.no_browser_startup_seed,
            )
        else:
            profiles["bundled_c_tor_browser"] = {
                "skipped": True,
                "reason": (
                    "disabled by --skip-bundled-tor"
                    if args.skip_bundled_tor
                    else f"bundled tor not found: {bundled_tor_bin}"
                ),
            }

        profiles["local_c_tor_browser"] = run_c_tor(
            tor_bin=tor_bin,
            port=args.local_tor_port,
            output_dir=output_dir / "local_c_tor_browser",
            browser_bin=browser_bin,
            targets=args.targets,
            runs=args.runs,
            timeout=args.timeout,
            window_size=args.window_size,
            warm_cache=args.warm_cache,
            compact_output=args.compact_output,
            post_boot_wait=args.post_boot_wait,
            proxy_log_tail_lines=args.proxy_log_tail_lines,
            byte_tap=args.byte_tap,
            byte_tap_port_offset=args.byte_tap_port_offset,
            byte_tap_event_limit=args.byte_tap_event_limit,
            byte_tap_socks_reply_bind_port_tag=args.byte_tap_socks_reply_bind_port_tag,
            browser_net_log=args.browser_net_log,
            browser_serial_http_connections=args.browser_serial_http_connections,
            browser_max_persistent_connections_per_server=(
                args.browser_max_persistent_connections_per_server
            ),
            browser_block_url_substrings=browser_block_url_substrings,
            browser_startup_seed_root=Path(args.browser_startup_seed_root).resolve(),
            no_browser_startup_seed=args.no_browser_startup_seed,
            source_tweaks=payload["source_tweaks"],
        )
        for ux_index, conflux_ux in enumerate(args.extra_c_tor_conflux_ux):
            ux_port = args.local_tor_port + 120 + ux_index
            ux_name = f"local_c_tor_browser_confluxux_{conflux_ux}"
            profiles[ux_name] = run_c_tor(
                tor_bin=tor_bin,
                port=ux_port,
                output_dir=output_dir / ux_name,
                browser_bin=browser_bin,
                targets=args.targets,
                runs=args.runs,
                timeout=args.timeout,
                window_size=args.window_size,
                warm_cache=args.warm_cache,
                compact_output=args.compact_output,
                post_boot_wait=args.post_boot_wait,
                proxy_log_tail_lines=args.proxy_log_tail_lines,
                byte_tap=args.byte_tap,
                byte_tap_port_offset=args.byte_tap_port_offset,
                byte_tap_event_limit=args.byte_tap_event_limit,
                byte_tap_socks_reply_bind_port_tag=(
                    args.byte_tap_socks_reply_bind_port_tag
                ),
                browser_net_log=args.browser_net_log,
                browser_serial_http_connections=args.browser_serial_http_connections,
                browser_max_persistent_connections_per_server=(
                    args.browser_max_persistent_connections_per_server
                ),
                browser_block_url_substrings=browser_block_url_substrings,
                browser_startup_seed_root=Path(args.browser_startup_seed_root).resolve(),
                no_browser_startup_seed=args.no_browser_startup_seed,
                source_tweaks=payload["source_tweaks"],
                conflux_client_ux=conflux_ux,
            )
        profiles["arti_release_browser"] = run_arti(
            arti_bin=arti_bin,
            port=args.arti_port,
            output_dir=output_dir / "arti_release_browser",
            browser_bin=browser_bin,
            targets=args.targets,
            runs=args.runs,
            timeout=args.timeout,
            window_size=args.window_size,
            warm_cache=args.warm_cache,
            compact_output=args.compact_output,
            post_boot_wait=args.post_boot_wait,
            arti_log_level=args.arti_log_level,
            arti_proxy_buffer_size=args.arti_proxy_buffer_size,
            arti_stream_scheduler_burst=args.arti_stream_scheduler_burst,
            arti_exit_select_parallelism=args.arti_exit_select_parallelism,
            arti_exit_launch_parallelism=args.arti_exit_launch_parallelism,
            arti_min_exit_circs_for_port=args.arti_min_exit_circs_for_port,
            arti_socks_connect_soft_timeout_ms=(
                args.arti_socks_connect_soft_timeout_ms
            ),
            arti_socks_connect_soft_timeout_attempts=(
                args.arti_socks_connect_soft_timeout_attempts
            ),
            arti_socks_connect_hedge_ms=args.arti_socks_connect_hedge_ms,
            arti_socks_relay_byte_timing=args.arti_socks_relay_byte_timing,
            arti_socks_partial_relay_idle_timeout_ms=(
                args.arti_socks_partial_relay_idle_timeout_ms
            ),
            arti_socks_no_tor_byte_relay_timeout_ms=(
                args.arti_socks_no_tor_byte_relay_timeout_ms
            ),
            arti_dirclient_read_timeout_ms=args.arti_dirclient_read_timeout_ms,
            arti_exit_pending_hedge_ms=args.arti_exit_pending_hedge_ms,
            arti_exit_select_load_aware=args.arti_exit_select_load_aware,
            arti_exit_select_health_aware=args.arti_exit_select_health_aware,
            arti_exit_select_health_min_move_score_bps=(
                args.arti_exit_select_health_min_move_score_bps
            ),
            arti_exit_select_avoid_bad_health=(
                args.arti_exit_select_avoid_bad_health
            ),
            arti_exit_select_avoid_bad_health_unknown_fallback=(
                args.arti_exit_select_avoid_bad_health_unknown_fallback
            ),
            arti_exit_select_bad_health_hedge_ms=(
                args.arti_exit_select_bad_health_hedge_ms
            ),
            arti_exit_select_bad_health_stream_idle_ms=(
                args.arti_exit_select_bad_health_stream_idle_ms
            ),
            arti_exit_select_bad_health_active_no_data_ms=(
                args.arti_exit_select_bad_health_active_no_data_ms
            ),
            arti_exit_select_max_active_streams=(
                args.arti_exit_select_max_active_streams
            ),
            arti_exit_select_max_assigned_streams=(
                args.arti_exit_select_max_assigned_streams
            ),
            arti_exit_select_min_assignment_spread=(
                args.arti_exit_select_min_assignment_spread
            ),
            arti_exit_select_healthy_over_cold_min_assigned=(
                args.arti_exit_select_healthy_over_cold_min_assigned
            ),
            arti_exit_select_healthy_over_cold_guard_only_min_assigned=(
                args.arti_exit_select_healthy_over_cold_guard_only_min_assigned
            ),
            arti_exit_same_isolation_target=args.arti_exit_same_isolation_target,
            arti_exit_same_isolation_require_bad_health=(
                args.arti_exit_same_isolation_require_bad_health
            ),
            arti_exit_same_isolation_min_assigned_streams=(
                args.arti_exit_same_isolation_min_assigned_streams
            ),
            arti_exit_select_prefer_cold_same_isolation=(
                args.arti_exit_select_prefer_cold_same_isolation
            ),
            proxy_log_tail_lines=args.proxy_log_tail_lines,
            byte_tap=args.byte_tap,
            byte_tap_port_offset=args.byte_tap_port_offset,
            byte_tap_event_limit=args.byte_tap_event_limit,
            byte_tap_socks_reply_bind_port_tag=args.byte_tap_socks_reply_bind_port_tag,
            browser_net_log=args.browser_net_log,
            browser_serial_http_connections=args.browser_serial_http_connections,
            browser_max_persistent_connections_per_server=(
                args.browser_max_persistent_connections_per_server
            ),
            browser_block_url_substrings=browser_block_url_substrings,
            browser_startup_seed_root=Path(args.browser_startup_seed_root).resolve(),
            no_browser_startup_seed=args.no_browser_startup_seed,
        )
    payload["profiles"] = profiles

    output_path = output_dir / "browser-compare.json"
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"wrote {output_path}")
    print(json.dumps(short_summary(payload), indent=2, sort_keys=True))
    return 0 if payload_ok(payload) else 1


def binary_info(path: Path) -> dict[str, object]:
    if not path.exists():
        return {"path": str(path), "exists": False}
    if path.name == "arti":
        version = run_version([str(path), "--version"])
    else:
        version = run_version([str(path), "--version"])
    return {"path": str(path), "exists": True, "version": version}


def run_version(command: list[str]) -> str:
    try:
        proc = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=20.0,
            check=False,
        )
    except Exception as exc:  # noqa: BLE001 - command metadata only.
        return f"{type(exc).__name__}: {exc}"
    return proc.stdout.strip()


def parse_soft_timeout_combos(values: list[str]) -> list[tuple[int, int]]:
    combos: list[tuple[int, int]] = []
    for value in values:
        parts = value.split(":", 1)
        if len(parts) != 2:
            raise ValueError(
                "--extra-arti-socks-connect-soft-timeout-combo must use MS:ATTEMPTS"
            )
        try:
            timeout_ms = int(parts[0])
            attempts = int(parts[1])
        except ValueError as exc:
            raise ValueError(
                "--extra-arti-socks-connect-soft-timeout-combo must use integer MS:ATTEMPTS"
            ) from exc
        combos.append((timeout_ms, attempts))
    return combos


def parse_soft_timeout_pending_hedge_combos(
    values: list[str],
) -> list[tuple[int, int, int]]:
    combos: list[tuple[int, int, int]] = []
    for value in values:
        parts = value.split(":")
        if len(parts) != 3:
            raise ValueError(
                "--extra-arti-socks-connect-soft-timeout-pending-hedge-combo must use MS:ATTEMPTS:HEDGE_MS"
            )
        try:
            timeout_ms = int(parts[0])
            attempts = int(parts[1])
            hedge_ms = int(parts[2])
        except ValueError as exc:
            raise ValueError(
                "--extra-arti-socks-connect-soft-timeout-pending-hedge-combo must use integer MS:ATTEMPTS:HEDGE_MS"
            ) from exc
        combos.append((timeout_ms, attempts, hedge_ms))
    return combos


def parse_dir_bad_health_gate_combos(
    values: list[str],
    *,
    option: str = (
        "--extra-arti-dir-microdesc-source-spread-pending-spread-early-usable-"
        "load-aware-bad-health-replacement-gate"
    ),
) -> list[tuple[int, int, int]]:
    combos: list[tuple[int, int, int]] = []
    for raw in values:
        parts = raw.split(":")
        if len(parts) != 3:
            raise ValueError(
                f"{option} must use GAP_MS:MIN_ASSIGNED:MIN_ACTIVE"
            )
        try:
            gap_ms, min_assigned_streams, min_active_streams = (
                int(part) for part in parts
            )
        except ValueError as exc:
            raise ValueError(f"{option} values must be integers") from exc
        if not (1_000 <= gap_ms <= 60_000):
            raise ValueError(f"{option} gap_ms must be between 1000 and 60000")
        if not (1 <= min_assigned_streams <= 64):
            raise ValueError(
                f"{option} min_assigned_streams must be between 1 and 64"
            )
        if not (1 <= min_active_streams <= 64):
            raise ValueError(f"{option} min_active_streams must be between 1 and 64")
        combos.append((gap_ms, min_assigned_streams, min_active_streams))
    return combos


def parse_same_iso_active_cap_combos(values: list[str]) -> list[tuple[int, int]]:
    combos: list[tuple[int, int]] = []
    for raw in values:
        parts = raw.split(":")
        if len(parts) != 2:
            raise ValueError(
                "--extra-arti-exit-select-prefer-cold-same-isolation-active-cap "
                "must use TARGET:CAP"
            )
        try:
            target, cap = (int(part) for part in parts)
        except ValueError as exc:
            raise ValueError(
                "--extra-arti-exit-select-prefer-cold-same-isolation-active-cap "
                "values must be integers"
            ) from exc
        if not (2 <= target <= 4):
            raise ValueError(
                "--extra-arti-exit-select-prefer-cold-same-isolation-active-cap "
                "target must be between 2 and 4"
            )
        if not (1 <= cap <= 32):
            raise ValueError(
                "--extra-arti-exit-select-prefer-cold-same-isolation-active-cap "
                "cap must be between 1 and 32"
            )
        combos.append((target, cap))
    return combos


def parse_same_iso_other_iso_pressure_combos(
    values: list[str],
) -> list[tuple[int, int]]:
    combos: list[tuple[int, int]] = []
    for raw in values:
        parts = raw.split(":")
        if len(parts) != 2:
            raise ValueError(
                "--extra-arti-exit-same-isolation-other-isolation-pressure "
                "must use TARGET:MIN"
            )
        try:
            target, minimum = (int(part) for part in parts)
        except ValueError as exc:
            raise ValueError(
                "--extra-arti-exit-same-isolation-other-isolation-pressure "
                "values must be integers"
            ) from exc
        if not (2 <= target <= 4):
            raise ValueError(
                "--extra-arti-exit-same-isolation-other-isolation-pressure "
                "target must be between 2 and 4"
            )
        if not (1 <= minimum <= 64):
            raise ValueError(
                "--extra-arti-exit-same-isolation-other-isolation-pressure "
                "minimum must be between 1 and 64"
            )
        combos.append((target, minimum))
    return combos


def parse_same_iso_min_assigned_combos(values: list[str]) -> list[tuple[int, int]]:
    option = "--extra-arti-exit-same-isolation-min-assigned-streams"
    combos: list[tuple[int, int]] = []
    for raw in values:
        parts = raw.split(":")
        if len(parts) != 2:
            raise ValueError(f"{option} must use TARGET:MIN_ASSIGNED")
        try:
            target, min_assigned = (int(part) for part in parts)
        except ValueError as exc:
            raise ValueError(f"{option} values must be integers") from exc
        if not (2 <= target <= 4):
            raise ValueError(f"{option} target must be between 2 and 4")
        if not (1 <= min_assigned <= 8):
            raise ValueError(f"{option} min_assigned must be between 1 and 8")
        combos.append((target, min_assigned))
    return combos


def parse_same_iso_other_iso_assigned_cap_combos(
    values: list[str],
) -> list[tuple[int, int, int]]:
    option = (
        "--extra-arti-exit-same-isolation-other-isolation-pressure-assigned-cap"
    )
    combos: list[tuple[int, int, int]] = []
    for raw in values:
        parts = raw.split(":")
        if len(parts) != 3:
            raise ValueError(f"{option} must use TARGET:MIN:CAP")
        try:
            target, minimum, cap = (int(part) for part in parts)
        except ValueError as exc:
            raise ValueError(f"{option} values must be integers") from exc
        if not (2 <= target <= 4):
            raise ValueError(f"{option} target must be between 2 and 4")
        if not (1 <= minimum <= 64):
            raise ValueError(f"{option} minimum must be between 1 and 64")
        if not (1 <= cap <= 32):
            raise ValueError(f"{option} cap must be between 1 and 32")
        combos.append((target, minimum, cap))
    return combos


def parse_health_min_sameiso_pending_wait_combos(
    values: list[str],
) -> list[tuple[int, int, int]]:
    option = (
        "--extra-arti-exit-select-health-min-move-score-same-isolation-pending-wait"
    )
    combos: list[tuple[int, int, int]] = []
    for raw in values:
        parts = raw.split(":")
        if len(parts) != 3:
            raise ValueError(f"{option} must use TARGET:SCORE:WAIT_MS")
        try:
            target, score, wait_ms = (int(part) for part in parts)
        except ValueError as exc:
            raise ValueError(f"{option} values must be integers") from exc
        if not (2 <= target <= 4):
            raise ValueError(f"{option} target must be between 2 and 4")
        if not (0 <= score <= 1_048_576):
            raise ValueError(f"{option} score must be between 0 and 1048576")
        if not (1 <= wait_ms <= 60_000):
            raise ValueError(f"{option} wait_ms must be between 1 and 60000")
        combos.append((target, score, wait_ms))
    return combos


def parse_sameiso_pending_wait_combos(
    values: list[str], option: str
) -> list[tuple[int, int]]:
    combos: list[tuple[int, int]] = []
    for raw in values:
        parts = raw.split(":")
        if len(parts) != 2:
            raise ValueError(f"{option} must use TARGET:WAIT_MS")
        try:
            target, wait_ms = (int(part) for part in parts)
        except ValueError as exc:
            raise ValueError(f"{option} values must be integers") from exc
        if not (2 <= target <= 4):
            raise ValueError(f"{option} target must be between 2 and 4")
        if not (1 <= wait_ms <= 60_000):
            raise ValueError(f"{option} wait_ms must be between 1 and 60000")
        combos.append((target, wait_ms))
    return combos


def parse_health_min_assigned_cap_combos(values: list[str]) -> list[tuple[int, int]]:
    option = "--extra-arti-exit-select-health-min-move-score-assigned-cap"
    combos: list[tuple[int, int]] = []
    for raw in values:
        parts = raw.split(":")
        if len(parts) != 2:
            raise ValueError(f"{option} must use SCORE:CAP")
        try:
            score, cap = (int(part) for part in parts)
        except ValueError as exc:
            raise ValueError(f"{option} values must be integers") from exc
        if not (0 <= score <= 1_048_576):
            raise ValueError(f"{option} score must be between 0 and 1048576")
        if not (1 <= cap <= 32):
            raise ValueError(f"{option} cap must be between 1 and 32")
        combos.append((score, cap))
    return combos


def parse_extra_arti_bin_specs(values: list[str]) -> list[tuple[str, Path]]:
    specs: list[tuple[str, Path]] = []
    for value in values:
        label, sep, path_text = value.partition(":")
        if not sep or not label or not path_text:
            raise ValueError("--extra-arti-bin must use LABEL:PATH")
        if not re.fullmatch(r"[A-Za-z0-9_]+", label):
            raise ValueError(
                "--extra-arti-bin LABEL may only use letters, numbers, and underscore"
            )
        specs.append((f"arti_release_browser_{label}", Path(path_text).resolve()))
    return specs


def detect_source_tweaks(arti_root: Path) -> dict[str, object]:
    circmgr = arti_root / "crates" / "tor-circmgr" / "src" / "lib.rs"
    circmgr_config = arti_root / "crates" / "tor-circmgr" / "src" / "config.rs"
    circmgr_impls = arti_root / "crates" / "tor-circmgr" / "src" / "impls.rs"
    circmgr_mgr = arti_root / "crates" / "tor-circmgr" / "src" / "mgr.rs"
    circmgr_hspool = arti_root / "crates" / "tor-circmgr" / "src" / "hspool.rs"
    circmgr_hspool_pool = (
        arti_root / "crates" / "tor-circmgr" / "src" / "hspool" / "pool.rs"
    )
    hsclient_connect = arti_root / "crates" / "tor-hsclient" / "src" / "connect.rs"
    socks = arti_root / "crates" / "arti" / "src" / "proxy" / "socks.rs"
    proxy = arti_root / "crates" / "arti" / "src" / "proxy.rs"
    reactor_circuit = (
        arti_root / "crates" / "tor-proto" / "src" / "client" / "reactor" / "circuit.rs"
    )
    circuit_circhop = arti_root / "crates" / "tor-proto" / "src" / "circuit" / "circhop.rs"
    data_stream = (
        arti_root / "crates" / "tor-proto" / "src" / "client" / "stream" / "data.rs"
    )
    if not circmgr.exists():
        return {}
    circmgr_text = circmgr.read_text(errors="replace")
    circmgr_config_text = (
        circmgr_config.read_text(errors="replace") if circmgr_config.exists() else ""
    )
    circmgr_impls_text = (
        circmgr_impls.read_text(errors="replace") if circmgr_impls.exists() else ""
    )
    circmgr_mgr_text = (
        circmgr_mgr.read_text(errors="replace") if circmgr_mgr.exists() else ""
    )
    circmgr_hspool_text = (
        circmgr_hspool.read_text(errors="replace") if circmgr_hspool.exists() else ""
    )
    circmgr_hspool_pool_text = (
        circmgr_hspool_pool.read_text(errors="replace")
        if circmgr_hspool_pool.exists()
        else ""
    )
    hsclient_connect_text = (
        hsclient_connect.read_text(errors="replace") if hsclient_connect.exists() else ""
    )
    socks_text = socks.read_text(errors="replace") if socks.exists() else ""
    proxy_text = proxy.read_text(errors="replace") if proxy.exists() else ""
    reactor_circuit_text = (
        reactor_circuit.read_text(errors="replace") if reactor_circuit.exists() else ""
    )
    circuit_circhop_text = (
        circuit_circhop.read_text(errors="replace") if circuit_circhop.exists() else ""
    )
    data_stream_text = (
        data_stream.read_text(errors="replace") if data_stream.exists() else ""
    )
    match = re.search(
        r"let\s+base_delay\s*=\s*Duration::from_secs\((\d+)\)", circmgr_text
    )
    min_exit_circs = re.search(
        r"fn\s+default_preemptive_min_exit_circs_for_port\(\).*?\{\s*(\d+)\s*\}",
        circmgr_config_text,
        re.DOTALL,
    )
    exit_select_parallelism = re.search(
        r"TargetTunnelUsage::Exit\s*\{\s*\.\.\s*\}\s*=>\s*(\d+)",
        circmgr_impls_text,
    )
    exit_select_parallelism_default = re.search(
        r"TORFAST_DEFAULT_EXIT_SELECT_PARALLELISM:\s*usize\s*=\s*(\d+)",
        circmgr_impls_text,
    )
    exit_launch_parallelism_default = re.search(
        r"TORFAST_DEFAULT_EXIT_LAUNCH_PARALLELISM:\s*usize\s*=\s*(\d+)",
        circmgr_impls_text,
    )
    same_isolation_target_default = re.search(
        r"TORFAST_EXIT_SAME_ISOLATION_TARGET_DEFAULT:\s*usize\s*=\s*(\d+)",
        circmgr_mgr_text,
    )
    guarded_same_isolation_active_cap_default = re.search(
        r"TORFAST_EXIT_SELECT_GUARDED_SAME_ISOLATION_ACTIVE_CAP_DEFAULT:\s*u64\s*=\s*(\d+)",
        circmgr_mgr_text,
    )
    hspool_launch_parallelism_default = re.search(
        r"TORFAST_HSPOOL_LAUNCH_PARALLELISM_DEFAULT:\s*usize\s*=\s*(\d+)",
        circmgr_hspool_text,
    )
    hspool_background_start_delay_default = re.search(
        r"TORFAST_HSPOOL_BACKGROUND_START_DELAY_DEFAULT_MS:\s*u64\s*=\s*([0-9_]+)",
        circmgr_hspool_text,
    )
    hspool_on_demand_grace_default = re.search(
        r"TORFAST_HSPOOL_ON_DEMAND_POOL_GRACE_DEFAULT_MS:\s*u64\s*=\s*(\d+)",
        circmgr_hspool_text,
    )
    hspool_on_demand_race_default = re.search(
        r"TORFAST_HSPOOL_ON_DEMAND_POOL_RACE_DEFAULT_MS:\s*u64\s*=\s*(\d+)",
        circmgr_hspool_text,
    )
    stream_scheduler_burst_default = re.search(
        r"TORFAST_STREAM_SCHEDULER_BURST_DEFAULT:\s*usize\s*=\s*(\d+)",
        reactor_circuit_text,
    )
    hspool_guarded_stem_target_default = re.search(
        r"DEFAULT_GUARDED_STEM_TARGET:\s*usize\s*=\s*(\d+)",
        circmgr_hspool_pool_text,
    )

    def detect_env_flag_default(function_name: str) -> bool | None:
        function_match = re.search(
            rf"fn\s+{function_name}\s*\(\)\s*->\s*bool\s*\{{(?P<body>.*?)^}}",
            circmgr_mgr_text,
            re.DOTALL | re.MULTILINE,
        )
        if not function_match:
            return None
        function_body = function_match.group("body")
        helper_match = re.search(
            r"torfast_env_flag\(.*?,\s*(true|false)\s*,?\s*\)",
            function_body,
            re.DOTALL,
        )
        if helper_match:
            return helper_match.group(1) == "true"
        unwrap_match = re.search(
            r"unwrap_or\((true|false)\)",
            function_body,
            re.DOTALL,
        )
        if unwrap_match:
            return unwrap_match.group(1) == "true"
        return None

    return {
        "arti_preemptive_recheck_seconds": int(match.group(1)) if match else None,
        "arti_preemptive_min_exit_circs_for_port": (
            int(min_exit_circs.group(1)) if min_exit_circs else None
        ),
        "arti_socks_connect_optimistic": "prefs.optimistic()" in socks_text,
        "arti_exit_select_parallelism": (
            int(exit_select_parallelism.group(1))
            if exit_select_parallelism
            else (
                int(exit_select_parallelism_default.group(1))
                if exit_select_parallelism_default
                else None
            )
        ),
        "arti_exit_launch_parallelism": (
            int(exit_launch_parallelism_default.group(1))
            if exit_launch_parallelism_default
            else None
        ),
        "arti_hspool_launch_parallelism_lab": (
            "TORFAST_HSPOOL_LAUNCH_PARALLELISM" in circmgr_hspool_text
        ),
        "arti_hspool_launch_parallelism_default": (
            int(hspool_launch_parallelism_default.group(1))
            if hspool_launch_parallelism_default
            else None
        ),
        "arti_hspool_background_start_delay_lab": (
            "TORFAST_HSPOOL_BACKGROUND_START_DELAY_MS" in circmgr_hspool_text
        ),
        "arti_hspool_background_start_delay_default_ms": (
            int(hspool_background_start_delay_default.group(1).replace("_", ""))
            if hspool_background_start_delay_default
            else None
        ),
        "arti_hspool_on_demand_grace_lab": (
            "TORFAST_HSPOOL_ON_DEMAND_POOL_GRACE_MS" in circmgr_hspool_text
        ),
        "arti_hspool_on_demand_grace_default_ms": (
            int(hspool_on_demand_grace_default.group(1))
            if hspool_on_demand_grace_default
            else None
        ),
        "arti_hspool_on_demand_race_lab": (
            "TORFAST_HSPOOL_ON_DEMAND_POOL_RACE_MS" in circmgr_hspool_text
        ),
        "arti_hspool_on_demand_race_default_ms": (
            int(hspool_on_demand_race_default.group(1))
            if hspool_on_demand_race_default
            else None
        ),
        "arti_hspool_guarded_stem_target_lab": (
            "TORFAST_HSPOOL_GUARDED_STEM_TARGET" in circmgr_hspool_pool_text
        ),
        "arti_hspool_guarded_stem_target_default": (
            int(hspool_guarded_stem_target_default.group(1))
            if hspool_guarded_stem_target_default
            else None
        ),
        "arti_hs_intro_rend_overlap_lab": (
            "TORFAST_HS_INTRO_REND_OVERLAP" in hsclient_connect_text
        ),
        "arti_hs_rend_prebuild_before_desc_lab": (
            "TORFAST_HS_REND_PREBUILD_BEFORE_DESC" in hsclient_connect_text
        ),
        "arti_hs_desc_shared_cache_lab": (
            "TORFAST_HS_DESC_SHARED_CACHE" in hsclient_connect_text
        ),
        "arti_hs_intro_circuit_hedge_lab": (
            "TORFAST_HS_INTRO_CIRCUIT_HEDGE_MS" in hsclient_connect_text
        ),
        "arti_socks_connect_soft_timeout_lab": (
            "TORFAST_SOCKS_CONNECT_SOFT_TIMEOUT_MS" in socks_text
        ),
        "arti_socks_connect_hedge_lab": (
            "TORFAST_SOCKS_CONNECT_HEDGE_MS" in socks_text
        ),
        "arti_socks_relay_byte_timing_lab": (
            "TORFAST_SOCKS_RELAY_BYTE_TIMING" in socks_text
        ),
        "arti_socks_tor_to_client_coalesce_lab": (
            "TORFAST_SOCKS_TOR_TO_CLIENT_COALESCE_BYTES" in socks_text
        ),
        "arti_stream_ready_data_coalesce_lab": (
            "TORFAST_STREAM_READY_DATA_COALESCE_BYTES" in data_stream_text
        ),
        "arti_proxy_app_stream_buffer_lab": (
            "TORFAST_APP_STREAM_BUF_LEN" in proxy_text
        ),
        "arti_circuit_congestion_log_lab": (
            "TORFAST_CIRCUIT_CONGESTION_LOG" in reactor_circuit_text
        ),
        "arti_stream_scheduler_log_lab": (
            "TORFAST_STREAM_SCHEDULER_LOG" in reactor_circuit_text
        ),
        "arti_stream_scheduler_burst_lab": (
            "TORFAST_STREAM_SCHEDULER_BURST" in reactor_circuit_text
        ),
        "arti_stream_scheduler_burst_default": (
            int(stream_scheduler_burst_default.group(1))
            if stream_scheduler_burst_default
            else None
        ),
        "arti_stream_lifecycle_log_lab": (
            "TORFAST_STREAM_LIFECYCLE_LOG" in circuit_circhop_text
        ),
        "arti_socks_no_tor_byte_relay_timeout_lab": (
            "TORFAST_SOCKS_NO_TOR_BYTE_RELAY_TIMEOUT_MS" in socks_text
        ),
        "arti_socks_partial_relay_idle_timeout_lab": (
            "TORFAST_SOCKS_PARTIAL_RELAY_IDLE_TIMEOUT_MS" in socks_text
        ),
        "arti_exit_pending_hedge_lab": (
            "TORFAST_EXIT_PENDING_HEDGE_MS" in circmgr_mgr_text
        ),
        "arti_exit_select_load_aware_lab": (
            "TORFAST_EXIT_SELECT_LOAD_AWARE" in circmgr_mgr_text
        ),
        "arti_exit_select_load_aware_default": detect_env_flag_default(
            "torfast_exit_select_load_aware"
        ),
        "arti_exit_select_health_aware_lab": (
            "TORFAST_EXIT_SELECT_HEALTH_AWARE" in circmgr_mgr_text
        ),
        "arti_exit_select_health_aware_default": detect_env_flag_default(
            "torfast_exit_select_health_aware"
        ),
        "arti_exit_select_health_min_move_score_lab": (
            "TORFAST_EXIT_SELECT_HEALTH_MIN_MOVE_SCORE_BPS" in circmgr_mgr_text
        ),
        "arti_exit_select_avoid_bad_health_lab": (
            "TORFAST_EXIT_SELECT_AVOID_BAD_HEALTH" in circmgr_mgr_text
        ),
        "arti_exit_select_avoid_bad_health_default": detect_env_flag_default(
            "torfast_exit_select_avoid_bad_health"
        ),
        "arti_exit_select_avoid_bad_health_unknown_fallback_lab": (
            "TORFAST_EXIT_SELECT_AVOID_BAD_HEALTH_UNKNOWN_FALLBACK"
            in circmgr_mgr_text
        ),
        "arti_exit_select_min_assignment_spread_lab": (
            "TORFAST_EXIT_SELECT_MIN_ASSIGNMENT_SPREAD" in circmgr_mgr_text
        ),
        "arti_exit_select_healthy_over_cold_lab": (
            "TORFAST_EXIT_SELECT_HEALTHY_OVER_COLD_MIN_ASSIGNED"
            in circmgr_mgr_text
        ),
        "arti_exit_select_healthy_over_cold_guard_only_lab": (
            "TORFAST_EXIT_SELECT_HEALTHY_OVER_COLD_GUARD_ONLY_MIN_ASSIGNED"
            in circmgr_mgr_text
        ),
        "arti_exit_select_max_active_streams_lab": (
            "TORFAST_EXIT_SELECT_MAX_ACTIVE_STREAMS" in circmgr_mgr_text
        ),
        "arti_exit_select_max_assigned_streams_lab": (
            "TORFAST_EXIT_SELECT_MAX_ASSIGNED_STREAMS" in circmgr_mgr_text
        ),
        "arti_exit_select_bad_health_active_no_data_lab": (
            "TORFAST_EXIT_SELECT_BAD_HEALTH_ACTIVE_NO_DATA_MS"
            in circmgr_mgr_text
        ),
        "arti_exit_select_low_log_context_lab": (
            "TORFAST_EXIT_SELECT_LOW_LOG_CONTEXT" in circmgr_mgr_text
        ),
        "arti_exit_select_low_log_info_unconditional": (
            "if low_log_selection_context {" in circmgr_mgr_text
            and "if low_log_selection_context && !tracing::enabled!(tracing::Level::DEBUG)"
            not in circmgr_mgr_text
        ),
        "arti_exit_same_isolation_target_lab": (
            "TORFAST_EXIT_SAME_ISOLATION_TARGET" in circmgr_mgr_text
        ),
        "arti_exit_same_isolation_target_default": (
            int(same_isolation_target_default.group(1))
            if same_isolation_target_default
            else None
        ),
        "arti_exit_same_isolation_other_isolation_min_lab": (
            "TORFAST_EXIT_SAME_ISOLATION_OTHER_ISOLATION_MIN" in circmgr_mgr_text
        ),
        "arti_exit_same_isolation_min_assigned_streams_lab": (
            "TORFAST_EXIT_SAME_ISOLATION_MIN_ASSIGNED_STREAMS" in circmgr_mgr_text
        ),
        "arti_exit_same_isolation_prewarm_first_stream_lab": (
            "TORFAST_EXIT_SAME_ISOLATION_PREWARM_FIRST_STREAM" in circmgr_mgr_text
        ),
        "arti_exit_same_isolation_pending_wait_lab": (
            "TORFAST_EXIT_SAME_ISOLATION_PENDING_WAIT_MS" in circmgr_mgr_text
        ),
        "arti_exit_same_isolation_require_bad_health_lab": (
            "TORFAST_EXIT_SAME_ISOLATION_REQUIRE_BAD_HEALTH" in circmgr_mgr_text
        ),
        "arti_exit_select_prefer_cold_same_isolation_lab": (
            "TORFAST_EXIT_SELECT_PREFER_COLD_SAME_ISOLATION" in circmgr_mgr_text
        ),
        "arti_exit_select_prefer_cold_same_isolation_default": (
            detect_env_flag_default("torfast_exit_select_prefer_cold_same_isolation")
        ),
        "arti_exit_select_guarded_same_isolation_active_cap_default": (
            int(guarded_same_isolation_active_cap_default.group(1))
            if guarded_same_isolation_active_cap_default
            else None
        ),
    }


def effective_arti_exit_selector_metadata(
    *,
    requested_load_aware: bool,
    requested_health_aware: bool,
    requested_avoid_bad_health: bool,
    requested_avoid_bad_health_unknown_fallback: bool,
    requested_same_isolation_target: int | None,
    requested_prefer_cold_same_isolation: bool,
    requested_max_active_streams: int | None,
    source_tweaks: dict[str, object] | None,
) -> dict[str, object]:
    tweaks = source_tweaks or {}
    effective_load_aware = (
        requested_load_aware
        or requested_health_aware
        or bool(tweaks.get("arti_exit_select_load_aware_default"))
    )
    effective_health_aware = effective_load_aware and (
        requested_health_aware
        or bool(tweaks.get("arti_exit_select_health_aware_default"))
    )
    effective_avoid_bad_health = effective_load_aware and (
        requested_avoid_bad_health
        or bool(tweaks.get("arti_exit_select_avoid_bad_health_default"))
    )
    effective_same_isolation_target = requested_same_isolation_target
    if effective_same_isolation_target is None:
        same_isolation_default = tweaks.get("arti_exit_same_isolation_target_default")
        if isinstance(same_isolation_default, int):
            effective_same_isolation_target = same_isolation_default
    effective_prefer_cold_same_isolation = (
        effective_same_isolation_target is not None
        and effective_health_aware
        and (
            requested_prefer_cold_same_isolation
            or bool(tweaks.get("arti_exit_select_prefer_cold_same_isolation_default"))
        )
    )
    effective_max_active_streams = requested_max_active_streams
    if (
        effective_max_active_streams is None
        and effective_same_isolation_target == 2
        and effective_avoid_bad_health
        and effective_prefer_cold_same_isolation
    ):
        guarded_active_cap_default = tweaks.get(
            "arti_exit_select_guarded_same_isolation_active_cap_default"
        )
        if isinstance(guarded_active_cap_default, int):
            effective_max_active_streams = guarded_active_cap_default
    return {
        "arti_exit_select_load_aware_effective": effective_load_aware,
        "arti_exit_select_health_aware_effective": effective_health_aware,
        "arti_exit_select_avoid_bad_health_effective": effective_avoid_bad_health,
        "arti_exit_select_avoid_bad_health_unknown_fallback_effective": (
            effective_avoid_bad_health and requested_avoid_bad_health_unknown_fallback
        ),
        "arti_exit_same_isolation_target_effective": effective_same_isolation_target,
        "arti_exit_select_prefer_cold_same_isolation_effective": (
            effective_prefer_cold_same_isolation
        ),
        "arti_exit_select_max_active_streams_effective": effective_max_active_streams,
    }


@dataclass
class ProxySpec:
    name: str
    kind: str
    bin_path: Path
    port: int
    output_dir: Path
    log_level: str = "info"
    arti_proxy_buffer_size: str | None = None
    arti_proxy_app_buffer_len: int | None = None
    arti_exit_select_parallelism: int | None = None
    arti_exit_launch_parallelism: int | None = None
    arti_hspool_launch_parallelism: int | None = None
    arti_hspool_background_start_delay_ms: int | None = None
    arti_hspool_guarded_stem_target: int | None = None
    arti_hspool_guarded_stem_target_defer_post_boot: bool = False
    arti_hspool_on_demand_grace_ms: int | None = None
    arti_hspool_on_demand_race_ms: int | None = None
    arti_min_exit_circs_for_port: int | None = None
    arti_preemptive_443_circs: int | None = None
    arti_preemptive_443_burst_min_requests: int | None = None
    arti_preemptive_443_busy_active_age_ms: int | None = None
    arti_socks_connect_soft_timeout_ms: int | None = None
    arti_socks_connect_soft_timeout_attempts: int | None = None
    arti_socks_connect_hedge_ms: int | None = None
    arti_socks_relay_byte_timing: bool = False
    arti_socks_tor_to_client_coalesce_bytes: int | None = None
    arti_stream_ready_data_coalesce_bytes: int | None = None
    arti_stream_scheduler_burst: int | None = None
    arti_socks_partial_relay_idle_timeout_ms: int | None = None
    arti_socks_no_tor_byte_relay_timeout_ms: int | None = None
    arti_dirclient_read_timeout_ms: int | None = None
    arti_dir_microdesc_early_usable_notify: bool = False
    arti_dir_microdesc_early_retry_on_partial: bool = False
    arti_dir_microdesc_partial_retry_chunking: bool = False
    arti_dir_microdesc_disable_bad_health_replacement: bool = False
    arti_dir_microdesc_bad_health_replacement_suppress_gap_ms: int | None = None
    arti_dir_microdesc_bad_health_replacement_suppress_min_assigned_streams: (
        int | None
    ) = None
    arti_dir_microdesc_bad_health_replacement_suppress_min_active_streams: (
        int | None
    ) = None
    arti_dir_microdesc_source_spread: bool = False
    arti_dir_microdesc_pending_spread: bool = False
    arti_dir_microdesc_retry_ids_per_request: int | None = None
    arti_dir_microdesc_retry_delay_max_ms: int | None = None
    arti_exit_pending_hedge_ms: int | None = None
    arti_exit_select_load_aware: bool = False
    arti_exit_select_health_aware: bool = False
    arti_exit_select_health_aware_min_assigned: int | None = None
    arti_exit_select_health_min_move_score_bps: int | None = None
    arti_exit_select_avoid_bad_health: bool = False
    arti_exit_select_avoid_bad_health_unknown_fallback: bool = False
    arti_exit_select_bad_health_hedge_ms: int | None = None
    arti_exit_select_bad_health_stream_idle_ms: int | None = None
    arti_exit_select_bad_health_active_no_data_ms: int | None = None
    arti_exit_select_max_active_streams: int | None = None
    arti_exit_select_max_assigned_streams: int | None = None
    arti_exit_select_min_assignment_spread: int | None = None
    arti_exit_select_healthy_over_cold_min_assigned: int | None = None
    arti_exit_select_healthy_over_cold_guard_only_min_assigned: int | None = None
    arti_exit_same_isolation_target: int | None = None
    arti_exit_same_isolation_other_isolation_min: int | None = None
    arti_exit_same_isolation_require_bad_health: bool = False
    arti_exit_same_isolation_min_assigned_streams: int | None = None
    arti_exit_same_isolation_pending_wait_ms: int | None = None
    arti_exit_same_isolation_prewarm_first_stream: bool = False
    arti_exit_same_isolation_prefer_topup_on_tie: bool = False
    arti_exit_select_prefer_cold_same_isolation: bool = False
    arti_hs_intro_rend_overlap: bool = False
    arti_hs_rend_prebuild_before_desc: bool = False
    arti_hs_desc_shared_cache: bool = False
    arti_hs_intro_circuit_hedge_ms: int | None = None


def effective_arti_log_level(
    log_level: str,
    socks_relay_byte_timing: bool,
    hspool_launch_parallelism: int | None = None,
    hspool_background_start_delay_ms: int | None = None,
    hspool_guarded_stem_target: int | None = None,
    hspool_on_demand_grace_ms: int | None = None,
    hspool_on_demand_race_ms: int | None = None,
    hs_intro_rend_overlap: bool = False,
    hs_rend_prebuild_before_desc: bool = False,
    hs_desc_shared_cache: bool = False,
    hs_intro_circuit_hedge_ms: int | None = None,
) -> str:
    parts = [part.strip() for part in log_level.split(",") if part.strip()]
    if not parts:
        parts = ["info"]
    if parts == ["info"] and socks_relay_byte_timing:
        parts.append("tor_proto=debug")
    if (
        hspool_launch_parallelism is not None
        and hspool_launch_parallelism > 1
        and "tor_circmgr=debug" not in parts
    ):
        parts.append("tor_circmgr=debug")
    if (
        hspool_background_start_delay_ms is not None
        and "tor_circmgr=debug" not in parts
    ):
        parts.append("tor_circmgr=debug")
    if (
        hspool_guarded_stem_target is not None
        and hspool_guarded_stem_target > 2
        and "tor_circmgr=debug" not in parts
    ):
        parts.append("tor_circmgr=debug")
    if (
        hspool_on_demand_grace_ms is not None
        and hspool_on_demand_grace_ms > 0
        and "tor_circmgr=debug" not in parts
    ):
        parts.append("tor_circmgr=debug")
    if (
        hspool_on_demand_race_ms is not None
        and hspool_on_demand_race_ms > 0
        and "tor_circmgr=debug" not in parts
    ):
        parts.append("tor_circmgr=debug")
    if (
        (
            socks_relay_byte_timing
            or hs_intro_rend_overlap
            or hs_rend_prebuild_before_desc
            or hs_desc_shared_cache
            or hs_intro_circuit_hedge_ms is not None
        )
        and "tor_hsclient=debug" not in parts
    ):
        parts.append("tor_hsclient=debug")
    return ",".join(parts)


@dataclass
class RunningProxy:
    spec: ProxySpec
    proc: subprocess.Popen[str]
    lines: queue.Queue[str]
    storage_paths: dict[str, Path]
    started_monotonic_seconds: float


@dataclass
class InterleavedLaunchPlanEntry:
    spec: ProxySpec
    launch_order: int
    launch_offset_seconds: float
    expected_boot_seconds: float | None


class SocksProxyToClientParser:
    """Find server data after SOCKS5 proxy replies without storing payload."""

    def __init__(self) -> None:
        self.state = "method_reply"
        self.buffer = bytearray()
        self.selected_method: int | None = None

    def feed(self, data: bytes) -> int:
        stream_data_bytes, _output, _updates = self.feed_with_reply_tag(
            data, reply_tag_port=None
        )
        return stream_data_bytes

    def feed_with_reply_tag(
        self, data: bytes, *, reply_tag_port: int | None
    ) -> tuple[int, bytes, dict[str, object]]:
        self.buffer.extend(data)
        output = bytearray()
        updates: dict[str, object] = {}
        stream_data_bytes = 0
        while self.buffer:
            if self.state == "stream_data":
                stream_data_bytes += len(self.buffer)
                output.extend(self.buffer)
                self.buffer.clear()
                break
            if self.state == "method_reply":
                if len(self.buffer) < 2:
                    break
                if self.buffer[0] != 5:
                    self.state = "stream_data"
                    continue
                self.selected_method = self.buffer[1]
                output.extend(self.buffer[:2])
                del self.buffer[:2]
                self.state = (
                    "auth_reply" if self.selected_method == 2 else "connect_reply"
                )
                continue
            if self.state == "auth_reply":
                if len(self.buffer) < 2:
                    break
                output.extend(self.buffer[:2])
                del self.buffer[:2]
                self.state = "connect_reply"
                continue
            if self.state == "connect_reply":
                reply_len = socks5_connect_reply_len(self.buffer)
                if reply_len is None:
                    break
                if reply_len <= 0:
                    self.state = "stream_data"
                    continue
                reply = bytearray(self.buffer[:reply_len])
                if (
                    reply_tag_port is not None
                    and reply_len >= 2
                    and reply[0] == 5
                    and reply[1] == 0
                ):
                    original_port = struct.unpack("!H", bytes(reply[-2:]))[0]
                    reply[-2:] = struct.pack("!H", reply_tag_port)
                    updates["socks_reply_original_bind_port"] = original_port
                    updates["socks_reply_tag_bind_port"] = reply_tag_port
                output.extend(reply)
                del self.buffer[:reply_len]
                self.state = "stream_data"
                continue
            break
        return stream_data_bytes, bytes(output), updates


def socks5_connect_reply_len(buffer: bytearray) -> int | None:
    if len(buffer) < 4:
        return None
    if buffer[0] != 5:
        return 0
    atyp = buffer[3]
    if atyp == 1:
        addr_len = 4
    elif atyp == 3:
        if len(buffer) < 5:
            return None
        addr_len = 1 + buffer[4]
    elif atyp == 4:
        addr_len = 16
    else:
        return 0
    reply_len = 4 + addr_len + 2
    return reply_len if len(buffer) >= reply_len else None


class SocksClientToProxyParser:
    """Find SOCKS5 client request metadata without storing auth secrets."""

    def __init__(self) -> None:
        self.state = "greeting"
        self.buffer = bytearray()
        self.auth_seen = False

    def feed(
        self, data: bytes, *, elapsed_ms: float, event_epoch_ms: float
    ) -> dict[str, object]:
        self.buffer.extend(data)
        updates: dict[str, object] = {}
        while self.buffer:
            if self.state == "done":
                self.buffer.clear()
                break
            if self.state == "greeting":
                if len(self.buffer) < 2:
                    break
                if self.buffer[0] != 5:
                    updates.setdefault("socks_client_parse_error", "not_socks5")
                    self.state = "done"
                    continue
                method_count = self.buffer[1]
                greeting_len = 2 + method_count
                if len(self.buffer) < greeting_len:
                    break
                updates["socks_client_version"] = 5
                updates["socks_client_methods"] = list(self.buffer[2:greeting_len])
                updates["socks_greeting_epoch_ms"] = round(event_epoch_ms, 3)
                updates["socks_greeting_elapsed_ms"] = round(elapsed_ms, 3)
                del self.buffer[:greeting_len]
                self.state = "auth_or_request"
                continue
            if self.state == "auth_or_request":
                if not self.buffer:
                    break
                if self.buffer[0] == 1:
                    auth_updates = self._parse_auth_request(
                        elapsed_ms=elapsed_ms,
                        event_epoch_ms=event_epoch_ms,
                    )
                    if auth_updates is None:
                        break
                    updates.update(auth_updates)
                    self.state = "request"
                    continue
                self.state = "request"
                continue
            if self.state == "request":
                request = socks5_client_request_parts(self.buffer)
                if request is None:
                    break
                if request.get("request_len", 0) <= 0:
                    updates.setdefault("socks_client_parse_error", "bad_request")
                    self.state = "done"
                    continue
                request_len = int(request.pop("request_len"))
                updates.update(request)
                updates.setdefault("socks_auth_present", self.auth_seen)
                updates["socks_connect_request_epoch_ms"] = round(event_epoch_ms, 3)
                updates["socks_connect_request_elapsed_ms"] = round(elapsed_ms, 3)
                del self.buffer[:request_len]
                self.state = "done"
                continue
            break
        return updates

    def _parse_auth_request(
        self, *, elapsed_ms: float, event_epoch_ms: float
    ) -> dict[str, object] | None:
        if len(self.buffer) < 2:
            return None
        username_len = self.buffer[1]
        if len(self.buffer) < 2 + username_len + 1:
            return None
        password_len_offset = 2 + username_len
        password_len = self.buffer[password_len_offset]
        auth_len = password_len_offset + 1 + password_len
        if len(self.buffer) < auth_len:
            return None
        username = bytes(self.buffer[2:password_len_offset])
        password = bytes(self.buffer[password_len_offset + 1 : auth_len])
        del self.buffer[:auth_len]
        self.auth_seen = True
        return {
            "socks_auth_present": True,
            "socks_auth_request_epoch_ms": round(event_epoch_ms, 3),
            "socks_auth_request_elapsed_ms": round(elapsed_ms, 3),
            "socks_auth_username_len": username_len,
            "socks_auth_password_len": password_len,
        }


def socks5_client_request_parts(buffer: bytearray) -> dict[str, object] | None:
    if len(buffer) < 4:
        return None
    if buffer[0] != 5:
        return {"request_len": 0}
    command = buffer[1]
    atyp = buffer[3]
    offset = 4
    if atyp == 1:
        addr_len = 4
        if len(buffer) < offset + addr_len + 2:
            return None
        host = socket.inet_ntop(socket.AF_INET, bytes(buffer[offset : offset + addr_len]))
    elif atyp == 3:
        if len(buffer) < 5:
            return None
        addr_len = buffer[4]
        offset = 5
        if len(buffer) < offset + addr_len + 2:
            return None
        host = bytes(buffer[offset : offset + addr_len]).decode(
            "utf-8", errors="replace"
        )
    elif atyp == 4:
        addr_len = 16
        if len(buffer) < offset + addr_len + 2:
            return None
        host = socket.inet_ntop(socket.AF_INET6, bytes(buffer[offset : offset + addr_len]))
    else:
        return {"request_len": 0}
    port_offset = offset + addr_len
    port = struct.unpack("!H", bytes(buffer[port_offset : port_offset + 2]))[0]
    return {
        "request_len": port_offset + 2,
        "socks_command": socks5_command_label(command),
        "socks_target_atyp": atyp,
        "socks_target_host": host,
        "socks_target_port": port,
    }


def socks5_command_label(command: int) -> str:
    if command == 1:
        return "connect"
    if command == 2:
        return "bind"
    if command == 3:
        return "udp_associate"
    return f"cmd_{command}"


def socket_addr_host_port(addr: object) -> tuple[str | None, int | None]:
    if not isinstance(addr, tuple) or len(addr) < 2:
        return None, None
    host, port = addr[0], addr[1]
    return str(host), int(port) if isinstance(port, int) else None


def socks_reply_bind_port_tag_for_connection(connection_id: int) -> int:
    return 40000 + (connection_id % 20000)


class ByteTapServer:
    def __init__(
        self,
        *,
        profile_name: str,
        listen_port: int,
        upstream_port: int,
        event_limit: int,
        socks_reply_bind_port_tag: bool = False,
    ) -> None:
        self.profile_name = profile_name
        self.listen_port = listen_port
        self.upstream_port = upstream_port
        self.event_limit = event_limit
        self.socks_reply_bind_port_tag = socks_reply_bind_port_tag
        self.events: list[dict[str, object]] = []
        self.connections: dict[int, dict[str, object]] = {}
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._next_connection_id = 0
        self._listener: socket.socket | None = None
        self._threads: list[threading.Thread] = []

    def start(self) -> None:
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", self.listen_port))
        listener.listen()
        listener.settimeout(0.2)
        self._listener = listener
        thread = threading.Thread(target=self._accept_loop, daemon=True)
        thread.start()
        self._threads.append(thread)

    def stop(self) -> None:
        self._stop.set()
        if self._listener is not None:
            try:
                self._listener.close()
            except OSError:
                pass
        for thread in self._threads:
            thread.join(timeout=1.0)

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            return {
                "enabled": True,
                "ok": True,
                "listen_host": "127.0.0.1",
                "listen_port": self.listen_port,
                "profile_name": self.profile_name,
                "upstream_host": "127.0.0.1",
                "upstream_port": self.upstream_port,
                "event_limit_per_direction": self.event_limit,
                "socks_reply_bind_port_tag": self.socks_reply_bind_port_tag,
                "connections": sorted(
                    self.connections.values(),
                    key=lambda item: int(item.get("connection_id", 0)),
                ),
                "events": list(self.events),
            }

    def _accept_loop(self) -> None:
        assert self._listener is not None
        while not self._stop.is_set():
            try:
                client_sock, client_addr = self._listener.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            thread = threading.Thread(
                target=self._handle_connection,
                args=(client_sock, client_addr),
                daemon=True,
            )
            thread.start()
            self._threads.append(thread)

    def _handle_connection(
        self, client_sock: socket.socket, client_addr: object
    ) -> None:
        started_perf = time.perf_counter()
        started_epoch_ms = time.time() * 1000
        browser_peer_host, browser_peer_port = socket_addr_host_port(client_addr)
        tap_local_host, tap_local_port = socket_addr_host_port(client_sock.getsockname())
        with self._lock:
            self._next_connection_id += 1
            connection_id = self._next_connection_id
            self.connections[connection_id] = {
                "connection_id": connection_id,
                "started_epoch_ms": round(started_epoch_ms, 3),
                "browser_peer_host": browser_peer_host,
                "browser_peer_port": browser_peer_port,
                "tap_local_host": tap_local_host,
                "tap_local_port": tap_local_port,
                "browser_to_proxy_bytes": 0,
                "proxy_to_browser_bytes": 0,
                "proxy_to_browser_stream_data_bytes": 0,
            }
        try:
            upstream_sock = socket.create_connection(
                ("127.0.0.1", self.upstream_port), timeout=10.0
            )
        except OSError as exc:
            self._update_connection(
                connection_id,
                {
                    "ok": False,
                    "error": f"upstream connect failed: {exc}",
                    "duration_ms": round((time.perf_counter() - started_perf) * 1000, 3),
                },
            )
            client_sock.close()
            return

        upstream_local_host, upstream_local_port = socket_addr_host_port(
            upstream_sock.getsockname()
        )
        upstream_peer_host, upstream_peer_port = socket_addr_host_port(
            upstream_sock.getpeername()
        )
        self._update_connection(
            connection_id,
            {
                "upstream_local_host": upstream_local_host,
                "upstream_local_port": upstream_local_port,
                "upstream_peer_host": upstream_peer_host,
                "upstream_peer_port": upstream_peer_port,
            },
        )

        client_parser = SocksClientToProxyParser()
        server_parser = SocksProxyToClientParser()
        client_sock.settimeout(0.5)
        upstream_sock.settimeout(0.5)
        threads = [
            threading.Thread(
                target=self._pump,
                args=(
                    client_sock,
                    upstream_sock,
                    connection_id,
                    "browser_to_proxy",
                    started_perf,
                    client_parser,
                ),
                daemon=True,
            ),
            threading.Thread(
                target=self._pump,
                args=(
                    upstream_sock,
                    client_sock,
                    connection_id,
                    "proxy_to_browser",
                    started_perf,
                    server_parser,
                ),
                daemon=True,
            ),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        client_sock.close()
        upstream_sock.close()
        self._update_connection(
            connection_id,
            {
                "ok": True,
                "duration_ms": round((time.perf_counter() - started_perf) * 1000, 3),
            },
        )

    def _pump(
        self,
        src: socket.socket,
        dst: socket.socket,
        connection_id: int,
        direction: str,
        started_perf: float,
        parser: SocksClientToProxyParser | SocksProxyToClientParser,
    ) -> None:
        event_index = 0
        cumulative_bytes = 0
        cumulative_stream_data_bytes = 0
        while not self._stop.is_set():
            try:
                chunk = src.recv(65536)
            except socket.timeout:
                continue
            except OSError:
                break
            if not chunk:
                break

            now_perf = time.perf_counter()
            event_epoch_ms = time.time() * 1000
            elapsed_ms = (now_perf - started_perf) * 1000
            event_index += 1
            cumulative_bytes += len(chunk)
            output_chunk = chunk
            stream_data_bytes = 0
            phase = ""
            connection_updates: dict[str, object] = {}
            if direction == "proxy_to_browser":
                assert isinstance(parser, SocksProxyToClientParser)
                reply_tag_port = (
                    socks_reply_bind_port_tag_for_connection(connection_id)
                    if self.socks_reply_bind_port_tag
                    else None
                )
                (
                    stream_data_bytes,
                    output_chunk,
                    connection_updates,
                ) = parser.feed_with_reply_tag(
                    chunk, reply_tag_port=reply_tag_port
                )
                cumulative_stream_data_bytes += stream_data_bytes
                phase = "stream_data" if stream_data_bytes == len(chunk) else "socks"
                if 0 < stream_data_bytes < len(chunk):
                    phase = "mixed"
            elif direction == "browser_to_proxy":
                assert isinstance(parser, SocksClientToProxyParser)
                connection_updates = parser.feed(
                    chunk, elapsed_ms=elapsed_ms, event_epoch_ms=event_epoch_ms
                )

            self._record_byte_event(
                connection_id=connection_id,
                direction=direction,
                event_index=event_index,
                elapsed_ms=elapsed_ms,
                event_epoch_ms=event_epoch_ms,
                read_bytes=len(chunk),
                cumulative_bytes=cumulative_bytes,
                stream_data_bytes=stream_data_bytes,
                cumulative_stream_data_bytes=cumulative_stream_data_bytes,
                phase=phase,
                connection_updates=connection_updates,
            )

            if output_chunk:
                try:
                    dst.sendall(output_chunk)
                except OSError:
                    break
        try:
            dst.shutdown(socket.SHUT_WR)
        except OSError:
            pass

    def _record_byte_event(
        self,
        *,
        connection_id: int,
        direction: str,
        event_index: int,
        elapsed_ms: float,
        event_epoch_ms: float,
        read_bytes: int,
        cumulative_bytes: int,
        stream_data_bytes: int,
        cumulative_stream_data_bytes: int,
        phase: str,
        connection_updates: dict[str, object] | None = None,
    ) -> None:
        updates: dict[str, object] = dict(connection_updates or {})
        byte_key = f"{direction}_bytes"
        updates[byte_key] = cumulative_bytes
        first_key = f"first_{direction}_ms"
        first_epoch_key = f"first_{direction}_epoch_ms"
        with self._lock:
            connection = self.connections[connection_id]
            if first_key not in connection:
                updates[first_key] = round(elapsed_ms, 3)
                updates[first_epoch_key] = round(event_epoch_ms, 3)
            if direction == "proxy_to_browser":
                updates["proxy_to_browser_stream_data_bytes"] = (
                    cumulative_stream_data_bytes
                )
                if (
                    stream_data_bytes > 0
                    and "first_stream_data_to_browser_ms" not in connection
                ):
                    updates["first_stream_data_to_browser_ms"] = round(
                        elapsed_ms, 3
                    )
                    updates["first_stream_data_to_browser_epoch_ms"] = round(
                        event_epoch_ms, 3
                    )
            connection.update(updates)
            if event_index <= self.event_limit:
                event: dict[str, object] = {
                    "connection_id": connection_id,
                    "direction": direction,
                    "event_index": event_index,
                    "elapsed_ms": round(elapsed_ms, 3),
                    "event_epoch_ms": round(event_epoch_ms, 3),
                    "read_bytes": read_bytes,
                    "cumulative_bytes": cumulative_bytes,
                }
                if direction == "proxy_to_browser":
                    event["phase"] = phase
                    event["stream_data_bytes"] = stream_data_bytes
                    event["cumulative_stream_data_bytes"] = (
                        cumulative_stream_data_bytes
                    )
                self.events.append(event)

    def _update_connection(
        self, connection_id: int, updates: dict[str, object]
    ) -> None:
        with self._lock:
            self.connections.setdefault(connection_id, {"connection_id": connection_id})
            self.connections[connection_id].update(updates)


def run_interleaved_profiles(
    *,
    bundled_tor_bin: Path,
    tor_bin: Path,
    arti_bin: Path,
    ports: dict[str, int],
    output_dir: Path,
    browser_bin: Path,
    targets: list[str],
    runs: int,
    timeout: float,
    window_size: str,
    warm_cache: bool = False,
    share_arti_warm_cache_seed: bool = False,
    compact_output: bool = False,
    post_boot_wait: float = 0.0,
    arti_log_level: str = "info",
    arti_proxy_buffer_size: str | None = None,
    arti_proxy_app_buffer_len: int | None = None,
    arti_stream_scheduler_burst: int | None = None,
    arti_exit_select_parallelism: int | None = None,
    arti_exit_launch_parallelism: int | None = None,
    arti_hspool_launch_parallelism: int | None = None,
    arti_hspool_background_start_delay_ms: int | None = None,
    arti_hspool_guarded_stem_target: int | None = None,
    arti_hspool_on_demand_grace_ms: int | None = None,
    arti_hspool_on_demand_race_ms: int | None = None,
    arti_min_exit_circs_for_port: int | None = None,
    arti_preemptive_443_circs: int | None = None,
    arti_preemptive_443_burst_min_requests: int | None = None,
    arti_preemptive_443_busy_active_age_ms: int | None = None,
    arti_socks_connect_soft_timeout_ms: int | None = None,
    arti_socks_connect_soft_timeout_attempts: int | None = None,
    arti_socks_connect_hedge_ms: int | None = None,
    arti_socks_relay_byte_timing: bool = False,
    arti_socks_partial_relay_idle_timeout_ms: int | None = None,
    arti_socks_no_tor_byte_relay_timeout_ms: int | None = None,
    arti_dirclient_read_timeout_ms: int | None = None,
    arti_exit_pending_hedge_ms: int | None = None,
    arti_exit_select_load_aware: bool = False,
    arti_exit_select_health_aware: bool = False,
    arti_exit_select_health_aware_min_assigned: int | None = None,
    arti_exit_select_health_min_move_score_bps: int | None = None,
    arti_exit_select_avoid_bad_health: bool = False,
    arti_exit_select_avoid_bad_health_unknown_fallback: bool = False,
    arti_exit_select_bad_health_hedge_ms: int | None = None,
    arti_exit_select_bad_health_stream_idle_ms: int | None = None,
    arti_exit_select_bad_health_active_no_data_ms: int | None = None,
    arti_exit_select_max_active_streams: int | None = None,
    arti_exit_select_max_assigned_streams: int | None = None,
    arti_exit_select_min_assignment_spread: int | None = None,
    arti_exit_select_healthy_over_cold_min_assigned: int | None = None,
    arti_exit_select_healthy_over_cold_guard_only_min_assigned: int | None = None,
    arti_exit_same_isolation_target: int | None = None,
    arti_exit_same_isolation_require_bad_health: bool = False,
    arti_exit_same_isolation_min_assigned_streams: int | None = None,
    arti_exit_same_isolation_pending_wait_ms: int | None = None,
    arti_exit_same_isolation_prewarm_first_stream: bool = False,
    arti_hs_rend_prebuild_before_desc: bool = False,
    arti_exit_select_prefer_cold_same_isolation: bool = False,
    extra_arti_exit_select_parallelism: list[int] | None = None,
    extra_arti_exit_launch_parallelism: list[int] | None = None,
    extra_arti_hspool_launch_parallelism: list[int] | None = None,
    extra_arti_hspool_background_start_delay_ms: list[int] | None = None,
    extra_arti_hspool_guarded_stem_target: list[int] | None = None,
    extra_arti_hspool_guarded_stem_target_defer_post_boot: list[int] | None = None,
    extra_arti_hspool_on_demand_grace_ms: list[int] | None = None,
    extra_arti_hspool_on_demand_race_ms: list[int] | None = None,
    extra_arti_hs_intro_rend_overlap: bool = False,
    extra_arti_hs_rend_prebuild_before_desc: bool = False,
    extra_arti_hs_desc_shared_cache: bool = False,
    extra_arti_hs_intro_circuit_hedge_ms: list[int] | None = None,
    extra_arti_min_exit_circs_for_port: list[int] | None = None,
    extra_arti_preemptive_443_circs: list[int] | None = None,
    extra_arti_preemptive_443_burst_min_requests: list[int] | None = None,
    extra_arti_preemptive_443_busy_active_age_ms: list[int] | None = None,
    extra_arti_socks_connect_soft_timeout_ms: list[int] | None = None,
    extra_arti_socks_connect_soft_timeout_attempts: list[int] | None = None,
    extra_arti_socks_connect_hedge_ms: list[int] | None = None,
    extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_partial_retry_chunking_socks_connect_hedge_ms: list[
        int
    ]
    | None = None,
    extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_partial_retry_chunking_hs_rend_prebuild_before_desc: bool = False,
    extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_partial_retry_chunking_bad_health_replacement_gate_combos: list[
        tuple[int, int, int]
    ]
    | None = None,
    extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_partial_retry_chunking_socks_connect_soft_timeout_combos: list[
        tuple[int, int]
    ]
    | None = None,
    extra_arti_socks_connect_soft_timeout_combos: list[tuple[int, int]] | None = None,
    extra_arti_socks_connect_soft_timeout_pending_hedge_combos: list[
        tuple[int, int, int]
    ]
    | None = None,
    extra_arti_socks_no_tor_byte_relay_timeout_ms: list[int] | None = None,
    extra_arti_socks_partial_relay_idle_timeout_ms: list[int] | None = None,
    extra_arti_exit_pending_hedge_ms: list[int] | None = None,
    extra_arti_dirclient_read_timeout_ms: list[int] | None = None,
    extra_arti_dir_microdesc_early_usable_notify: bool = False,
    extra_arti_dir_microdesc_source_spread_pending_spread_early_usable: bool = False,
    extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware: bool = False,
    extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_no_dir_bad_health_replacement: bool = False,
    extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_bad_health_replacement_suppress_gap_ms: list[
        int
    ]
    | None = None,
    extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_bad_health_replacement_gate_combos: list[
        tuple[int, int, int]
    ]
    | None = None,
    extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_early_retry_on_partial: bool = False,
    extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_partial_retry_chunking: bool = False,
    extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_partial_retry_chunking_max_active_streams: list[
        int
    ]
    | None = None,
    extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_partial_retry_chunking: bool = False,
    extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_partial_retry_chunking_max_active_streams: list[
        int
    ]
    | None = None,
    extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_partial_retry_chunking_hs_rend_prebuild_before_desc: bool = False,
    extra_arti_dir_microdesc_source_spread_pending_spread: bool = False,
    extra_arti_dir_microdesc_retry_ids_per_request: list[int] | None = None,
    extra_arti_exit_select_load_aware: bool = False,
    extra_arti_exit_select_health_aware: bool = False,
    extra_arti_exit_select_health_min_move_score_bps: list[int] | None = None,
    extra_arti_exit_select_health_min_move_score_assigned_cap: list[tuple[int, int]]
    | None = None,
    extra_arti_exit_select_health_aware_min_assignment_spread: list[int]
    | None = None,
    extra_arti_exit_select_health_aware_min_assigned: list[int] | None = None,
    extra_arti_exit_select_avoid_bad_health: bool = False,
    extra_arti_exit_select_health_aware_avoid_bad_health: bool = False,
    extra_arti_exit_select_health_aware_avoid_bad_health_same_isolation_target: list[
        int
    ]
    | None = None,
    extra_arti_exit_select_health_aware_same_isolation_prefer_cold_target: list[
        int
    ]
    | None = None,
    extra_arti_exit_select_prefer_cold_same_isolation_target: list[int]
    | None = None,
    extra_arti_exit_select_prefer_cold_same_isolation_active_cap: list[
        tuple[int, int]
    ]
    | None = None,
    extra_arti_exit_select_prefer_cold_same_isolation_prewarm_target: list[int]
    | None = None,
    extra_arti_exit_select_health_aware_same_isolation_prefer_cold_prewarm_pending_wait: list[
        tuple[int, int]
    ]
    | None = None,
    extra_arti_exit_select_avoid_bad_health_unknown_fallback_prefer_cold_same_isolation_target: list[
        int
    ]
    | None = None,
    extra_arti_exit_select_min_assignment_spread: list[int] | None = None,
    extra_arti_exit_select_healthy_over_cold_min_assigned: list[int]
    | None = None,
    extra_arti_exit_select_healthy_over_cold_guard_only_min_assigned: list[int]
    | None = None,
    extra_arti_exit_select_max_active_streams: list[int] | None = None,
    extra_arti_exit_select_max_assigned_streams: list[int] | None = None,
    extra_arti_exit_select_bad_health_active_no_data_ms: list[int]
    | None = None,
    extra_arti_exit_select_bad_health_hedge_ms: list[int] | None = None,
    extra_arti_exit_same_isolation_target: list[int] | None = None,
    extra_arti_exit_same_isolation_other_isolation_pressure: list[tuple[int, int]]
    | None = None,
    extra_arti_exit_same_isolation_other_isolation_pressure_assigned_cap: list[
        tuple[int, int, int]
    ]
    | None = None,
    extra_arti_exit_same_isolation_other_isolation_pressure_assigned_cap_prewarm: list[
        tuple[int, int, int]
    ]
    | None = None,
    extra_arti_exit_select_prefer_cold_same_isolation_other_isolation_pressure: list[
        tuple[int, int]
    ]
    | None = None,
    extra_arti_exit_load_aware_same_isolation_target: list[int] | None = None,
    extra_arti_exit_same_isolation_prewarm_target: list[int] | None = None,
    extra_arti_exit_same_isolation_min_assigned_streams: list[tuple[int, int]]
    | None = None,
    extra_arti_exit_same_isolation_prefer_topup_on_tie: list[int] | None = None,
    extra_arti_exit_load_aware_same_isolation_prewarm_target: list[int] | None = None,
    extra_arti_exit_health_aware_same_isolation_prewarm_target: list[int]
    | None = None,
    extra_arti_exit_select_health_min_move_score_same_isolation_pending_wait: list[
        tuple[int, int, int]
    ]
    | None = None,
    extra_arti_proxy_buffer_size: list[str] | None = None,
    extra_arti_proxy_app_buffer_len: list[int] | None = None,
    extra_arti_stream_scheduler_burst: list[int] | None = None,
    extra_arti_socks_tor_to_client_coalesce_bytes: list[int] | None = None,
    extra_arti_stream_ready_data_coalesce_bytes: list[int] | None = None,
    extra_arti_bins: list[tuple[str, Path]] | None = None,
    extra_arti_port_start: int = 19083,
    include_bundled_tor: bool = True,
    proxy_log_tail_lines: int = 200,
    proxy_run_tail_lines: int = 0,
    byte_tap: bool = False,
    byte_tap_port_offset: int = 100,
    byte_tap_event_limit: int = DEFAULT_BYTE_TAP_EVENT_LIMIT,
    byte_tap_socks_reply_bind_port_tag: bool = False,
    browser_net_log: bool = False,
    browser_serial_http_connections: bool = False,
    browser_max_persistent_connections_per_server: int | None = None,
    browser_block_url_substrings: list[str] | None = None,
    browser_startup_seed_root: Path = DEFAULT_BROWSER_STARTUP_SEED_ROOT,
    no_browser_startup_seed: bool = False,
    interleaved_target_order: str = "fixed",
    source_tweaks: dict[str, object] | None = None,
) -> dict[str, object]:
    profiles: dict[str, object] = {}
    specs: list[ProxySpec] = []
    if include_bundled_tor and bundled_tor_bin.exists():
        specs.append(
            ProxySpec(
                name="bundled_c_tor_browser",
                kind="c_tor",
                bin_path=bundled_tor_bin,
                port=ports["bundled_c_tor_browser"],
                output_dir=output_dir / "bundled_c_tor_browser",
            )
        )
    else:
        profiles["bundled_c_tor_browser"] = {
            "skipped": True,
            "reason": (
                "disabled by --skip-bundled-tor"
                if not include_bundled_tor
                else f"bundled tor not found: {bundled_tor_bin}"
            ),
        }
    specs.extend(
        [
            ProxySpec(
                name="local_c_tor_browser",
                kind="c_tor",
                bin_path=tor_bin,
                port=ports["local_c_tor_browser"],
                output_dir=output_dir / "local_c_tor_browser",
            ),
            ProxySpec(
                name="arti_release_browser",
                kind="arti",
                bin_path=arti_bin,
                port=ports["arti_release_browser"],
                output_dir=output_dir / "arti_release_browser",
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_proxy_app_buffer_len=arti_proxy_app_buffer_len,
                arti_stream_scheduler_burst=arti_stream_scheduler_burst,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_hspool_background_start_delay_ms=(
                    arti_hspool_background_start_delay_ms
                ),
                arti_hspool_on_demand_grace_ms=arti_hspool_on_demand_grace_ms,
                arti_hspool_on_demand_race_ms=arti_hspool_on_demand_race_ms,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=(
                    arti_socks_connect_soft_timeout_attempts
                ),
                arti_socks_connect_hedge_ms=arti_socks_connect_hedge_ms,
                arti_socks_partial_relay_idle_timeout_ms=(
                    arti_socks_partial_relay_idle_timeout_ms
                ),
                arti_socks_no_tor_byte_relay_timeout_ms=(
                    arti_socks_no_tor_byte_relay_timeout_ms
                ),
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=arti_exit_select_load_aware,
                arti_exit_select_health_aware=arti_exit_select_health_aware,
                arti_exit_select_health_min_move_score_bps=(
                    arti_exit_select_health_min_move_score_bps
                ),
                arti_exit_select_avoid_bad_health=(
                    arti_exit_select_avoid_bad_health
                ),
                arti_exit_select_min_assignment_spread=(
                    arti_exit_select_min_assignment_spread
                ),
                arti_exit_select_healthy_over_cold_min_assigned=(
                    arti_exit_select_healthy_over_cold_min_assigned
                ),
                arti_exit_select_healthy_over_cold_guard_only_min_assigned=(
                    arti_exit_select_healthy_over_cold_guard_only_min_assigned
                ),
                arti_exit_same_isolation_target=arti_exit_same_isolation_target,
                arti_hs_rend_prebuild_before_desc=(
                    arti_hs_rend_prebuild_before_desc
                ),
                arti_exit_select_prefer_cold_same_isolation=(
                    arti_exit_select_prefer_cold_same_isolation
                ),
            ),
        ]
    )
    next_extra_port = extra_arti_port_start
    for profile_name, extra_bin in extra_arti_bins or []:
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=extra_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=(
                    arti_socks_connect_soft_timeout_attempts
                ),
                arti_socks_partial_relay_idle_timeout_ms=(
                    arti_socks_partial_relay_idle_timeout_ms
                ),
                arti_socks_no_tor_byte_relay_timeout_ms=(
                    arti_socks_no_tor_byte_relay_timeout_ms
                ),
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=arti_exit_select_load_aware,
                arti_exit_select_health_aware=arti_exit_select_health_aware,
                arti_exit_select_health_min_move_score_bps=(
                    arti_exit_select_health_min_move_score_bps
                ),
                arti_exit_select_avoid_bad_health=(
                    arti_exit_select_avoid_bad_health
                ),
                arti_exit_select_min_assignment_spread=(
                    arti_exit_select_min_assignment_spread
                ),
                arti_exit_same_isolation_target=arti_exit_same_isolation_target,
                arti_exit_select_prefer_cold_same_isolation=(
                    arti_exit_select_prefer_cold_same_isolation
                ),
            )
        )
        next_extra_port += 1
    for index, parallelism in enumerate(extra_arti_exit_select_parallelism or []):
        profile_name = extra_arti_profile_name(parallelism, index)
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_exit_select_parallelism=parallelism,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=arti_socks_connect_soft_timeout_attempts,
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=arti_exit_select_load_aware,
                arti_exit_select_health_aware=arti_exit_select_health_aware,
                arti_exit_select_health_min_move_score_bps=(
                    arti_exit_select_health_min_move_score_bps
                ),
                arti_exit_select_avoid_bad_health=(
                    arti_exit_select_avoid_bad_health
                ),
                arti_exit_select_min_assignment_spread=(
                    arti_exit_select_min_assignment_spread
                ),
                arti_exit_same_isolation_target=arti_exit_same_isolation_target,
            )
        )
        next_extra_port += 1
    for index, parallelism in enumerate(extra_arti_exit_launch_parallelism or []):
        profile_name = extra_arti_launch_profile_name(parallelism, index)
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_exit_launch_parallelism=parallelism,
                arti_hspool_launch_parallelism=arti_hspool_launch_parallelism,
                arti_hspool_background_start_delay_ms=(
                    arti_hspool_background_start_delay_ms
                ),
                arti_hspool_on_demand_grace_ms=arti_hspool_on_demand_grace_ms,
                arti_hspool_on_demand_race_ms=arti_hspool_on_demand_race_ms,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=arti_socks_connect_soft_timeout_attempts,
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=arti_exit_select_load_aware,
                arti_exit_select_health_aware=arti_exit_select_health_aware,
                arti_exit_select_health_min_move_score_bps=(
                    arti_exit_select_health_min_move_score_bps
                ),
                arti_exit_select_avoid_bad_health=(
                    arti_exit_select_avoid_bad_health
                ),
                arti_exit_select_min_assignment_spread=(
                    arti_exit_select_min_assignment_spread
                ),
                arti_exit_same_isolation_target=arti_exit_same_isolation_target,
            )
        )
        next_extra_port += 1
    for index, parallelism in enumerate(extra_arti_hspool_launch_parallelism or []):
        profile_name = extra_arti_hspool_launch_profile_name(parallelism, index)
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_exit_launch_parallelism=arti_exit_launch_parallelism,
                arti_hspool_launch_parallelism=parallelism,
                arti_hspool_background_start_delay_ms=(
                    arti_hspool_background_start_delay_ms
                ),
                arti_hspool_on_demand_grace_ms=arti_hspool_on_demand_grace_ms,
                arti_hspool_on_demand_race_ms=arti_hspool_on_demand_race_ms,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=(
                    arti_socks_connect_soft_timeout_attempts
                ),
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=arti_exit_select_load_aware,
                arti_exit_select_health_aware=arti_exit_select_health_aware,
                arti_exit_select_health_min_move_score_bps=(
                    arti_exit_select_health_min_move_score_bps
                ),
                arti_exit_select_avoid_bad_health=(
                    arti_exit_select_avoid_bad_health
                ),
                arti_exit_select_min_assignment_spread=(
                    arti_exit_select_min_assignment_spread
                ),
                arti_exit_same_isolation_target=arti_exit_same_isolation_target,
            )
        )
        next_extra_port += 1
    for index, delay_ms in enumerate(extra_arti_hspool_background_start_delay_ms or []):
        profile_name = extra_arti_hspool_background_start_delay_profile_name(delay_ms, index)
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_exit_launch_parallelism=arti_exit_launch_parallelism,
                arti_hspool_launch_parallelism=arti_hspool_launch_parallelism,
                arti_hspool_background_start_delay_ms=delay_ms,
                arti_hspool_on_demand_grace_ms=arti_hspool_on_demand_grace_ms,
                arti_hspool_on_demand_race_ms=arti_hspool_on_demand_race_ms,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=(
                    arti_socks_connect_soft_timeout_attempts
                ),
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=arti_exit_select_load_aware,
                arti_exit_select_health_aware=arti_exit_select_health_aware,
                arti_exit_select_health_min_move_score_bps=(
                    arti_exit_select_health_min_move_score_bps
                ),
                arti_exit_select_avoid_bad_health=(
                    arti_exit_select_avoid_bad_health
                ),
                arti_exit_select_min_assignment_spread=(
                    arti_exit_select_min_assignment_spread
                ),
                arti_exit_same_isolation_target=arti_exit_same_isolation_target,
            )
        )
        next_extra_port += 1
    for index, guarded_target in enumerate(
        extra_arti_hspool_guarded_stem_target or []
    ):
        profile_name = extra_arti_hspool_guarded_stem_target_profile_name(
            guarded_target, index
        )
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_exit_launch_parallelism=arti_exit_launch_parallelism,
                arti_hspool_launch_parallelism=arti_hspool_launch_parallelism,
                arti_hspool_background_start_delay_ms=(
                    arti_hspool_background_start_delay_ms
                ),
                arti_hspool_guarded_stem_target=guarded_target,
                arti_hspool_on_demand_grace_ms=arti_hspool_on_demand_grace_ms,
                arti_hspool_on_demand_race_ms=arti_hspool_on_demand_race_ms,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=(
                    arti_socks_connect_soft_timeout_attempts
                ),
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=arti_exit_select_load_aware,
                arti_exit_select_health_aware=arti_exit_select_health_aware,
                arti_exit_select_health_min_move_score_bps=(
                    arti_exit_select_health_min_move_score_bps
                ),
                arti_exit_select_avoid_bad_health=(
                    arti_exit_select_avoid_bad_health
                ),
                arti_exit_select_min_assignment_spread=(
                    arti_exit_select_min_assignment_spread
                ),
                arti_exit_same_isolation_target=arti_exit_same_isolation_target,
            )
        )
        next_extra_port += 1
    for index, guarded_target in enumerate(
        extra_arti_hspool_guarded_stem_target_defer_post_boot or []
    ):
        profile_name = extra_arti_hspool_guarded_stem_target_defer_post_boot_profile_name(
            guarded_target, index
        )
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_exit_launch_parallelism=arti_exit_launch_parallelism,
                arti_hspool_launch_parallelism=arti_hspool_launch_parallelism,
                arti_hspool_background_start_delay_ms=(
                    arti_hspool_background_start_delay_ms
                ),
                arti_hspool_guarded_stem_target=guarded_target,
                arti_hspool_guarded_stem_target_defer_post_boot=True,
                arti_hspool_on_demand_grace_ms=arti_hspool_on_demand_grace_ms,
                arti_hspool_on_demand_race_ms=arti_hspool_on_demand_race_ms,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=(
                    arti_socks_connect_soft_timeout_attempts
                ),
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=arti_exit_select_load_aware,
                arti_exit_select_health_aware=arti_exit_select_health_aware,
                arti_exit_select_health_min_move_score_bps=(
                    arti_exit_select_health_min_move_score_bps
                ),
                arti_exit_select_avoid_bad_health=(
                    arti_exit_select_avoid_bad_health
                ),
                arti_exit_select_min_assignment_spread=(
                    arti_exit_select_min_assignment_spread
                ),
                arti_exit_same_isolation_target=arti_exit_same_isolation_target,
            )
        )
        next_extra_port += 1
    for index, grace_ms in enumerate(extra_arti_hspool_on_demand_grace_ms or []):
        profile_name = extra_arti_hspool_on_demand_grace_profile_name(grace_ms, index)
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_exit_launch_parallelism=arti_exit_launch_parallelism,
                arti_hspool_launch_parallelism=arti_hspool_launch_parallelism,
                arti_hspool_background_start_delay_ms=(
                    arti_hspool_background_start_delay_ms
                ),
                arti_hspool_on_demand_grace_ms=grace_ms,
                arti_hspool_on_demand_race_ms=arti_hspool_on_demand_race_ms,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=(
                    arti_socks_connect_soft_timeout_attempts
                ),
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=arti_exit_select_load_aware,
                arti_exit_select_health_aware=arti_exit_select_health_aware,
                arti_exit_select_health_min_move_score_bps=(
                    arti_exit_select_health_min_move_score_bps
                ),
                arti_exit_select_avoid_bad_health=(
                    arti_exit_select_avoid_bad_health
                ),
                arti_exit_select_min_assignment_spread=(
                    arti_exit_select_min_assignment_spread
                ),
                arti_exit_same_isolation_target=arti_exit_same_isolation_target,
            )
        )
        next_extra_port += 1
    for index, race_ms in enumerate(extra_arti_hspool_on_demand_race_ms or []):
        profile_name = extra_arti_hspool_on_demand_race_profile_name(race_ms, index)
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_exit_launch_parallelism=arti_exit_launch_parallelism,
                arti_hspool_launch_parallelism=arti_hspool_launch_parallelism,
                arti_hspool_background_start_delay_ms=(
                    arti_hspool_background_start_delay_ms
                ),
                arti_hspool_on_demand_grace_ms=arti_hspool_on_demand_grace_ms,
                arti_hspool_on_demand_race_ms=race_ms,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=(
                    arti_socks_connect_soft_timeout_attempts
                ),
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=arti_exit_select_load_aware,
                arti_exit_select_health_aware=arti_exit_select_health_aware,
                arti_exit_select_health_min_move_score_bps=(
                    arti_exit_select_health_min_move_score_bps
                ),
                arti_exit_select_avoid_bad_health=(
                    arti_exit_select_avoid_bad_health
                ),
                arti_exit_select_min_assignment_spread=(
                    arti_exit_select_min_assignment_spread
                ),
                arti_exit_same_isolation_target=arti_exit_same_isolation_target,
            )
        )
        next_extra_port += 1
    if extra_arti_hs_intro_rend_overlap:
        profile_name = extra_arti_hs_intro_rend_overlap_profile_name()
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_exit_launch_parallelism=arti_exit_launch_parallelism,
                arti_hspool_launch_parallelism=arti_hspool_launch_parallelism,
                arti_hspool_background_start_delay_ms=(
                    arti_hspool_background_start_delay_ms
                ),
                arti_hspool_on_demand_grace_ms=arti_hspool_on_demand_grace_ms,
                arti_hspool_on_demand_race_ms=arti_hspool_on_demand_race_ms,
                arti_hs_intro_rend_overlap=True,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=(
                    arti_socks_connect_soft_timeout_attempts
                ),
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=arti_exit_select_load_aware,
                arti_exit_select_health_aware=arti_exit_select_health_aware,
                arti_exit_select_health_min_move_score_bps=(
                    arti_exit_select_health_min_move_score_bps
                ),
                arti_exit_select_avoid_bad_health=(
                    arti_exit_select_avoid_bad_health
                ),
                arti_exit_select_min_assignment_spread=(
                    arti_exit_select_min_assignment_spread
                ),
                arti_exit_same_isolation_target=arti_exit_same_isolation_target,
            )
        )
        next_extra_port += 1
    if extra_arti_hs_rend_prebuild_before_desc:
        profile_name = extra_arti_hs_rend_prebuild_before_desc_profile_name()
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_exit_launch_parallelism=arti_exit_launch_parallelism,
                arti_hspool_launch_parallelism=arti_hspool_launch_parallelism,
                arti_hspool_background_start_delay_ms=(
                    arti_hspool_background_start_delay_ms
                ),
                arti_hspool_on_demand_grace_ms=arti_hspool_on_demand_grace_ms,
                arti_hspool_on_demand_race_ms=arti_hspool_on_demand_race_ms,
                arti_hs_rend_prebuild_before_desc=True,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=(
                    arti_socks_connect_soft_timeout_attempts
                ),
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=arti_exit_select_load_aware,
                arti_exit_select_health_aware=arti_exit_select_health_aware,
                arti_exit_select_health_min_move_score_bps=(
                    arti_exit_select_health_min_move_score_bps
                ),
                arti_exit_select_avoid_bad_health=(
                    arti_exit_select_avoid_bad_health
                ),
                arti_exit_select_min_assignment_spread=(
                    arti_exit_select_min_assignment_spread
                ),
                arti_exit_same_isolation_target=arti_exit_same_isolation_target,
            )
        )
        next_extra_port += 1
    if extra_arti_hs_desc_shared_cache:
        profile_name = extra_arti_hs_desc_shared_cache_profile_name()
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_exit_launch_parallelism=arti_exit_launch_parallelism,
                arti_hspool_launch_parallelism=arti_hspool_launch_parallelism,
                arti_hspool_background_start_delay_ms=(
                    arti_hspool_background_start_delay_ms
                ),
                arti_hspool_on_demand_grace_ms=arti_hspool_on_demand_grace_ms,
                arti_hspool_on_demand_race_ms=arti_hspool_on_demand_race_ms,
                arti_hs_desc_shared_cache=True,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=(
                    arti_socks_connect_soft_timeout_attempts
                ),
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=arti_exit_select_load_aware,
                arti_exit_select_health_aware=arti_exit_select_health_aware,
                arti_exit_select_health_min_move_score_bps=(
                    arti_exit_select_health_min_move_score_bps
                ),
                arti_exit_select_avoid_bad_health=(
                    arti_exit_select_avoid_bad_health
                ),
                arti_exit_select_min_assignment_spread=(
                    arti_exit_select_min_assignment_spread
                ),
                arti_exit_same_isolation_target=arti_exit_same_isolation_target,
            )
        )
        next_extra_port += 1
    for index, hedge_ms in enumerate(extra_arti_hs_intro_circuit_hedge_ms or []):
        profile_name = extra_arti_hs_intro_circuit_hedge_profile_name(
            hedge_ms, index
        )
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_exit_launch_parallelism=arti_exit_launch_parallelism,
                arti_hspool_launch_parallelism=arti_hspool_launch_parallelism,
                arti_hspool_background_start_delay_ms=(
                    arti_hspool_background_start_delay_ms
                ),
                arti_hspool_on_demand_grace_ms=arti_hspool_on_demand_grace_ms,
                arti_hspool_on_demand_race_ms=arti_hspool_on_demand_race_ms,
                arti_hs_intro_circuit_hedge_ms=hedge_ms,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=(
                    arti_socks_connect_soft_timeout_attempts
                ),
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=arti_exit_select_load_aware,
                arti_exit_select_health_aware=arti_exit_select_health_aware,
                arti_exit_select_health_min_move_score_bps=(
                    arti_exit_select_health_min_move_score_bps
                ),
                arti_exit_select_avoid_bad_health=(
                    arti_exit_select_avoid_bad_health
                ),
                arti_exit_select_min_assignment_spread=(
                    arti_exit_select_min_assignment_spread
                ),
                arti_exit_same_isolation_target=arti_exit_same_isolation_target,
            )
        )
        next_extra_port += 1
    for index, min_exit_circs_for_port in enumerate(
        extra_arti_min_exit_circs_for_port or []
    ):
        profile_name = extra_arti_min_exit_circs_profile_name(
            min_exit_circs_for_port,
            index,
        )
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_min_exit_circs_for_port=min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=(
                    arti_socks_connect_soft_timeout_attempts
                ),
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=arti_exit_select_load_aware,
                arti_exit_select_health_aware=arti_exit_select_health_aware,
                arti_exit_select_health_min_move_score_bps=(
                    arti_exit_select_health_min_move_score_bps
                ),
                arti_exit_select_avoid_bad_health=(
                    arti_exit_select_avoid_bad_health
                ),
                arti_exit_select_min_assignment_spread=(
                    arti_exit_select_min_assignment_spread
                ),
                arti_exit_same_isolation_target=arti_exit_same_isolation_target,
            )
        )
        next_extra_port += 1
    for index, preemptive_443_circs in enumerate(extra_arti_preemptive_443_circs or []):
        profile_name = extra_arti_preemptive_443_circs_profile_name(
            preemptive_443_circs,
            index,
        )
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_preemptive_443_circs=preemptive_443_circs,
                arti_socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=(
                    arti_socks_connect_soft_timeout_attempts
                ),
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=arti_exit_select_load_aware,
                arti_exit_select_health_aware=arti_exit_select_health_aware,
                arti_exit_select_health_min_move_score_bps=(
                    arti_exit_select_health_min_move_score_bps
                ),
                arti_exit_select_avoid_bad_health=(
                    arti_exit_select_avoid_bad_health
                ),
                arti_exit_select_min_assignment_spread=(
                    arti_exit_select_min_assignment_spread
                ),
                arti_exit_same_isolation_target=arti_exit_same_isolation_target,
            )
        )
        next_extra_port += 1
    for index, burst_min_requests in enumerate(
        extra_arti_preemptive_443_burst_min_requests or []
    ):
        profile_name = extra_arti_preemptive_443_burst_profile_name(
            burst_min_requests,
            index,
        )
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_preemptive_443_burst_min_requests=burst_min_requests,
                arti_socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=(
                    arti_socks_connect_soft_timeout_attempts
                ),
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=arti_exit_select_load_aware,
                arti_exit_select_health_aware=arti_exit_select_health_aware,
                arti_exit_select_health_min_move_score_bps=(
                    arti_exit_select_health_min_move_score_bps
                ),
                arti_exit_select_avoid_bad_health=(
                    arti_exit_select_avoid_bad_health
                ),
                arti_exit_select_min_assignment_spread=(
                    arti_exit_select_min_assignment_spread
                ),
                arti_exit_same_isolation_target=arti_exit_same_isolation_target,
            )
        )
        next_extra_port += 1
    for index, busy_active_age_ms in enumerate(
        extra_arti_preemptive_443_busy_active_age_ms or []
    ):
        profile_name = extra_arti_preemptive_443_busy_active_age_profile_name(
            busy_active_age_ms,
            index,
        )
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_preemptive_443_busy_active_age_ms=busy_active_age_ms,
                arti_socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=(
                    arti_socks_connect_soft_timeout_attempts
                ),
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=arti_exit_select_load_aware,
                arti_exit_select_health_aware=arti_exit_select_health_aware,
                arti_exit_select_health_min_move_score_bps=(
                    arti_exit_select_health_min_move_score_bps
                ),
                arti_exit_select_avoid_bad_health=(
                    arti_exit_select_avoid_bad_health
                ),
                arti_exit_select_min_assignment_spread=(
                    arti_exit_select_min_assignment_spread
                ),
                arti_exit_same_isolation_target=arti_exit_same_isolation_target,
            )
        )
        next_extra_port += 1
    for index, proxy_buffer_size in enumerate(extra_arti_proxy_buffer_size or []):
        profile_name = extra_arti_proxy_buffer_profile_name(proxy_buffer_size, index)
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=proxy_buffer_size,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=arti_socks_connect_soft_timeout_attempts,
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=arti_exit_select_load_aware,
                arti_exit_select_health_aware=arti_exit_select_health_aware,
                arti_exit_select_health_min_move_score_bps=(
                    arti_exit_select_health_min_move_score_bps
                ),
                arti_exit_select_avoid_bad_health=(
                    arti_exit_select_avoid_bad_health
                ),
                arti_exit_select_min_assignment_spread=(
                    arti_exit_select_min_assignment_spread
                ),
                arti_exit_same_isolation_target=arti_exit_same_isolation_target,
            )
        )
        next_extra_port += 1
    for index, app_buffer_len in enumerate(extra_arti_proxy_app_buffer_len or []):
        profile_name = extra_arti_proxy_app_buffer_profile_name(
            app_buffer_len, index
        )
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_proxy_app_buffer_len=app_buffer_len,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=(
                    arti_socks_connect_soft_timeout_attempts
                ),
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=arti_exit_select_load_aware,
                arti_exit_select_health_aware=arti_exit_select_health_aware,
                arti_exit_select_health_min_move_score_bps=(
                    arti_exit_select_health_min_move_score_bps
                ),
                arti_exit_select_avoid_bad_health=(
                    arti_exit_select_avoid_bad_health
                ),
                arti_exit_select_min_assignment_spread=(
                    arti_exit_select_min_assignment_spread
                ),
                arti_exit_same_isolation_target=arti_exit_same_isolation_target,
            )
        )
        next_extra_port += 1
    for index, burst in enumerate(extra_arti_stream_scheduler_burst or []):
        profile_name = extra_arti_stream_scheduler_burst_profile_name(burst, index)
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_stream_scheduler_burst=burst,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=(
                    arti_socks_connect_soft_timeout_attempts
                ),
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=arti_exit_select_load_aware,
                arti_exit_select_health_aware=arti_exit_select_health_aware,
                arti_exit_select_health_min_move_score_bps=(
                    arti_exit_select_health_min_move_score_bps
                ),
                arti_exit_select_avoid_bad_health=(
                    arti_exit_select_avoid_bad_health
                ),
                arti_exit_select_min_assignment_spread=(
                    arti_exit_select_min_assignment_spread
                ),
                arti_exit_same_isolation_target=arti_exit_same_isolation_target,
            )
        )
        next_extra_port += 1
    for index, coalesce_bytes in enumerate(
        extra_arti_socks_tor_to_client_coalesce_bytes or []
    ):
        profile_name = extra_arti_socks_tor_to_client_coalesce_profile_name(
            coalesce_bytes, index
        )
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_socks_tor_to_client_coalesce_bytes=coalesce_bytes,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=(
                    arti_socks_connect_soft_timeout_attempts
                ),
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=arti_exit_select_load_aware,
                arti_exit_select_health_aware=arti_exit_select_health_aware,
                arti_exit_select_health_min_move_score_bps=(
                    arti_exit_select_health_min_move_score_bps
                ),
                arti_exit_select_avoid_bad_health=(
                    arti_exit_select_avoid_bad_health
                ),
                arti_exit_select_min_assignment_spread=(
                    arti_exit_select_min_assignment_spread
                ),
                arti_exit_same_isolation_target=arti_exit_same_isolation_target,
            )
        )
        next_extra_port += 1
    for index, coalesce_bytes in enumerate(
        extra_arti_stream_ready_data_coalesce_bytes or []
    ):
        profile_name = extra_arti_stream_ready_data_coalesce_profile_name(
            coalesce_bytes, index
        )
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_stream_ready_data_coalesce_bytes=coalesce_bytes,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=(
                    arti_socks_connect_soft_timeout_attempts
                ),
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=arti_exit_select_load_aware,
                arti_exit_select_health_aware=arti_exit_select_health_aware,
                arti_exit_select_health_min_move_score_bps=(
                    arti_exit_select_health_min_move_score_bps
                ),
                arti_exit_select_avoid_bad_health=(
                    arti_exit_select_avoid_bad_health
                ),
                arti_exit_select_min_assignment_spread=(
                    arti_exit_select_min_assignment_spread
                ),
                arti_exit_same_isolation_target=arti_exit_same_isolation_target,
            )
        )
        next_extra_port += 1
    for index, soft_timeout_ms in enumerate(
        extra_arti_socks_connect_soft_timeout_ms or []
    ):
        profile_name = extra_arti_soft_timeout_profile_name(soft_timeout_ms, index)
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=arti_socks_connect_soft_timeout_attempts,
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=arti_exit_select_load_aware,
                arti_exit_select_health_aware=arti_exit_select_health_aware,
                arti_exit_select_health_min_move_score_bps=(
                    arti_exit_select_health_min_move_score_bps
                ),
                arti_exit_select_avoid_bad_health=(
                    arti_exit_select_avoid_bad_health
                ),
                arti_exit_select_min_assignment_spread=(
                    arti_exit_select_min_assignment_spread
                ),
                arti_exit_same_isolation_target=arti_exit_same_isolation_target,
            )
        )
        next_extra_port += 1
    for index, attempts in enumerate(
        extra_arti_socks_connect_soft_timeout_attempts or []
    ):
        profile_name = extra_arti_soft_timeout_attempts_profile_name(attempts, index)
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=attempts,
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=arti_exit_select_load_aware,
                arti_exit_select_health_aware=arti_exit_select_health_aware,
                arti_exit_select_health_min_move_score_bps=(
                    arti_exit_select_health_min_move_score_bps
                ),
                arti_exit_select_avoid_bad_health=(
                    arti_exit_select_avoid_bad_health
                ),
                arti_exit_select_min_assignment_spread=(
                    arti_exit_select_min_assignment_spread
                ),
                arti_exit_same_isolation_target=arti_exit_same_isolation_target,
            )
        )
        next_extra_port += 1
    for index, hedge_ms in enumerate(extra_arti_socks_connect_hedge_ms or []):
        profile_name = extra_arti_socks_connect_hedge_profile_name(hedge_ms, index)
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=arti_socks_connect_soft_timeout_attempts,
                arti_socks_connect_hedge_ms=hedge_ms,
                arti_exit_select_healthy_over_cold_min_assigned=(
                    arti_exit_select_healthy_over_cold_min_assigned
                ),
                arti_exit_select_healthy_over_cold_guard_only_min_assigned=(
                    arti_exit_select_healthy_over_cold_guard_only_min_assigned
                ),
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=arti_exit_select_load_aware,
                arti_exit_select_health_aware=arti_exit_select_health_aware,
                arti_exit_select_health_min_move_score_bps=(
                    arti_exit_select_health_min_move_score_bps
                ),
                arti_exit_select_avoid_bad_health=(
                    arti_exit_select_avoid_bad_health
                ),
                arti_exit_select_min_assignment_spread=(
                    arti_exit_select_min_assignment_spread
                ),
                arti_exit_same_isolation_target=arti_exit_same_isolation_target,
            )
        )
        next_extra_port += 1
    for index, (soft_timeout_ms, attempts) in enumerate(
        extra_arti_socks_connect_soft_timeout_combos or []
    ):
        profile_name = extra_arti_soft_timeout_combo_profile_name(
            soft_timeout_ms, attempts, index
        )
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=attempts,
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=arti_exit_select_load_aware,
                arti_exit_select_health_aware=arti_exit_select_health_aware,
                arti_exit_select_health_min_move_score_bps=(
                    arti_exit_select_health_min_move_score_bps
                ),
                arti_exit_select_avoid_bad_health=(
                    arti_exit_select_avoid_bad_health
                ),
                arti_exit_select_min_assignment_spread=(
                    arti_exit_select_min_assignment_spread
                ),
                arti_exit_same_isolation_target=arti_exit_same_isolation_target,
            )
        )
        next_extra_port += 1
    for index, timeout_ms in enumerate(
        extra_arti_socks_no_tor_byte_relay_timeout_ms or []
    ):
        profile_name = extra_arti_no_tor_byte_timeout_profile_name(timeout_ms, index)
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=(
                    arti_socks_connect_soft_timeout_attempts
                ),
                arti_socks_no_tor_byte_relay_timeout_ms=timeout_ms,
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=arti_exit_select_load_aware,
                arti_exit_select_health_aware=arti_exit_select_health_aware,
                arti_exit_select_health_min_move_score_bps=(
                    arti_exit_select_health_min_move_score_bps
                ),
                arti_exit_select_avoid_bad_health=(
                    arti_exit_select_avoid_bad_health
                ),
                arti_exit_select_min_assignment_spread=(
                    arti_exit_select_min_assignment_spread
                ),
                arti_exit_same_isolation_target=arti_exit_same_isolation_target,
            )
        )
        next_extra_port += 1
    for index, timeout_ms in enumerate(
        extra_arti_socks_partial_relay_idle_timeout_ms or []
    ):
        profile_name = extra_arti_partial_idle_timeout_profile_name(
            timeout_ms, index
        )
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=(
                    arti_socks_connect_soft_timeout_attempts
                ),
                arti_socks_partial_relay_idle_timeout_ms=timeout_ms,
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=arti_exit_select_load_aware,
                arti_exit_select_health_aware=arti_exit_select_health_aware,
                arti_exit_select_health_min_move_score_bps=(
                    arti_exit_select_health_min_move_score_bps
                ),
                arti_exit_select_avoid_bad_health=(
                    arti_exit_select_avoid_bad_health
                ),
                arti_exit_select_min_assignment_spread=(
                    arti_exit_select_min_assignment_spread
                ),
                arti_exit_same_isolation_target=arti_exit_same_isolation_target,
            )
        )
        next_extra_port += 1
    for index, (soft_timeout_ms, attempts, pending_hedge_ms) in enumerate(
        extra_arti_socks_connect_soft_timeout_pending_hedge_combos or []
    ):
        profile_name = extra_arti_soft_timeout_pending_hedge_combo_profile_name(
            soft_timeout_ms, attempts, pending_hedge_ms, index
        )
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=attempts,
                arti_exit_pending_hedge_ms=pending_hedge_ms,
                arti_exit_select_load_aware=arti_exit_select_load_aware,
                arti_exit_select_health_aware=arti_exit_select_health_aware,
                arti_exit_select_health_min_move_score_bps=(
                    arti_exit_select_health_min_move_score_bps
                ),
                arti_exit_select_avoid_bad_health=(
                    arti_exit_select_avoid_bad_health
                ),
                arti_exit_select_min_assignment_spread=(
                    arti_exit_select_min_assignment_spread
                ),
                arti_exit_same_isolation_target=arti_exit_same_isolation_target,
            )
        )
        next_extra_port += 1
    for index, pending_hedge_ms in enumerate(extra_arti_exit_pending_hedge_ms or []):
        profile_name = extra_arti_pending_hedge_profile_name(pending_hedge_ms, index)
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=arti_socks_connect_soft_timeout_attempts,
                arti_exit_pending_hedge_ms=pending_hedge_ms,
                arti_exit_select_load_aware=arti_exit_select_load_aware,
                arti_exit_select_health_aware=arti_exit_select_health_aware,
                arti_exit_select_health_min_move_score_bps=(
                    arti_exit_select_health_min_move_score_bps
                ),
                arti_exit_select_avoid_bad_health=(
                    arti_exit_select_avoid_bad_health
                ),
                arti_exit_select_min_assignment_spread=(
                    arti_exit_select_min_assignment_spread
                ),
                arti_exit_same_isolation_target=arti_exit_same_isolation_target,
            )
        )
        next_extra_port += 1
    for index, read_timeout_ms in enumerate(
        extra_arti_dirclient_read_timeout_ms or []
    ):
        profile_name = extra_arti_dirclient_read_timeout_profile_name(
            read_timeout_ms, index
        )
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=arti_socks_connect_soft_timeout_attempts,
                arti_dirclient_read_timeout_ms=read_timeout_ms,
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=arti_exit_select_load_aware,
                arti_exit_select_health_aware=arti_exit_select_health_aware,
                arti_exit_select_health_min_move_score_bps=(
                    arti_exit_select_health_min_move_score_bps
                ),
                arti_exit_select_avoid_bad_health=(
                    arti_exit_select_avoid_bad_health
                ),
                arti_exit_select_min_assignment_spread=(
                    arti_exit_select_min_assignment_spread
                ),
                arti_exit_same_isolation_target=arti_exit_same_isolation_target,
            )
        )
        next_extra_port += 1
    dir_combo_same_isolation_kwargs = {
        "arti_exit_same_isolation_target": arti_exit_same_isolation_target,
        "arti_exit_same_isolation_require_bad_health": (
            arti_exit_same_isolation_require_bad_health
        ),
        "arti_exit_same_isolation_min_assigned_streams": (
            arti_exit_same_isolation_min_assigned_streams
        ),
        "arti_exit_same_isolation_pending_wait_ms": (
            arti_exit_same_isolation_pending_wait_ms
        ),
        "arti_exit_same_isolation_prewarm_first_stream": (
            arti_exit_same_isolation_prewarm_first_stream
        ),
        "arti_exit_select_prefer_cold_same_isolation": (
            arti_exit_select_prefer_cold_same_isolation
        ),
    }
    if extra_arti_dir_microdesc_early_usable_notify:
        profile_name = "arti_release_browser_mdearlyusable"
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=arti_socks_connect_soft_timeout_attempts,
                arti_dir_microdesc_early_usable_notify=True,
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=arti_exit_select_load_aware,
                arti_exit_select_health_aware=arti_exit_select_health_aware,
                arti_exit_select_health_min_move_score_bps=(
                    arti_exit_select_health_min_move_score_bps
                ),
                arti_exit_select_avoid_bad_health=(
                    arti_exit_select_avoid_bad_health
                ),
                arti_exit_select_min_assignment_spread=(
                    arti_exit_select_min_assignment_spread
                ),
                **dir_combo_same_isolation_kwargs,
            )
        )
        next_extra_port += 1
    if extra_arti_dir_microdesc_source_spread_pending_spread_early_usable:
        profile_name = "arti_release_browser_mdsrcspreadpendingearlyusable"
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=arti_socks_connect_soft_timeout_attempts,
                arti_dir_microdesc_early_usable_notify=True,
                arti_dir_microdesc_source_spread=True,
                arti_dir_microdesc_pending_spread=True,
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=arti_exit_select_load_aware,
                arti_exit_select_health_aware=arti_exit_select_health_aware,
                arti_exit_select_health_min_move_score_bps=(
                    arti_exit_select_health_min_move_score_bps
                ),
                arti_exit_select_avoid_bad_health=(
                    arti_exit_select_avoid_bad_health
                ),
                arti_exit_select_min_assignment_spread=(
                    arti_exit_select_min_assignment_spread
                ),
                **dir_combo_same_isolation_kwargs,
            )
        )
        next_extra_port += 1
    if extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware:
        profile_name = "arti_release_browser_mdsrcspreadpendingearlyusable_loadaware"
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=arti_socks_connect_soft_timeout_attempts,
                arti_dir_microdesc_early_usable_notify=True,
                arti_dir_microdesc_source_spread=True,
                arti_dir_microdesc_pending_spread=True,
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=True,
                arti_exit_select_health_aware=arti_exit_select_health_aware,
                arti_exit_select_health_min_move_score_bps=(
                    arti_exit_select_health_min_move_score_bps
                ),
                arti_exit_select_avoid_bad_health=(
                    arti_exit_select_avoid_bad_health
                ),
                arti_exit_select_min_assignment_spread=(
                    arti_exit_select_min_assignment_spread
                ),
                **dir_combo_same_isolation_kwargs,
            )
        )
        next_extra_port += 1
    if (
        extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_no_dir_bad_health_replacement
    ):
        profile_name = (
            "arti_release_browser_"
            "mdsrcspreadpendingearlyusable_loadaware_"
            "nodirmicrodescbadhealthreplace"
        )
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=arti_socks_connect_soft_timeout_attempts,
                arti_dir_microdesc_early_usable_notify=True,
                arti_dir_microdesc_disable_bad_health_replacement=True,
                arti_dir_microdesc_source_spread=True,
                arti_dir_microdesc_pending_spread=True,
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=True,
                arti_exit_select_health_aware=arti_exit_select_health_aware,
                arti_exit_select_health_min_move_score_bps=(
                    arti_exit_select_health_min_move_score_bps
                ),
                arti_exit_select_avoid_bad_health=(
                    arti_exit_select_avoid_bad_health
                ),
                arti_exit_select_min_assignment_spread=(
                    arti_exit_select_min_assignment_spread
                ),
                **dir_combo_same_isolation_kwargs,
            )
        )
        next_extra_port += 1
    for index, gap_ms in enumerate(
        extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_bad_health_replacement_suppress_gap_ms
        or []
    ):
        profile_name = extra_arti_dir_combo_bad_health_gap_profile_name(gap_ms, index)
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=arti_socks_connect_soft_timeout_attempts,
                arti_dir_microdesc_early_usable_notify=True,
                arti_dir_microdesc_bad_health_replacement_suppress_gap_ms=gap_ms,
                arti_dir_microdesc_source_spread=True,
                arti_dir_microdesc_pending_spread=True,
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=True,
                arti_exit_select_health_aware=arti_exit_select_health_aware,
                arti_exit_select_health_min_move_score_bps=(
                    arti_exit_select_health_min_move_score_bps
                ),
                arti_exit_select_avoid_bad_health=(
                    arti_exit_select_avoid_bad_health
                ),
                arti_exit_select_min_assignment_spread=(
                    arti_exit_select_min_assignment_spread
                ),
                **dir_combo_same_isolation_kwargs,
            )
        )
        next_extra_port += 1
    for index, (
        gap_ms,
        min_assigned_streams,
        min_active_streams,
    ) in enumerate(
        extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_bad_health_replacement_gate_combos
        or []
    ):
        profile_name = extra_arti_dir_combo_bad_health_gate_profile_name(
            gap_ms, min_assigned_streams, min_active_streams, index
        )
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=arti_socks_connect_soft_timeout_attempts,
                arti_dir_microdesc_early_usable_notify=True,
                arti_dir_microdesc_bad_health_replacement_suppress_gap_ms=gap_ms,
                arti_dir_microdesc_bad_health_replacement_suppress_min_assigned_streams=(
                    min_assigned_streams
                ),
                arti_dir_microdesc_bad_health_replacement_suppress_min_active_streams=(
                    min_active_streams
                ),
                arti_dir_microdesc_source_spread=True,
                arti_dir_microdesc_pending_spread=True,
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=True,
                arti_exit_select_health_aware=arti_exit_select_health_aware,
                arti_exit_select_health_min_move_score_bps=(
                    arti_exit_select_health_min_move_score_bps
                ),
                arti_exit_select_avoid_bad_health=(
                    arti_exit_select_avoid_bad_health
                ),
                arti_exit_select_min_assignment_spread=(
                    arti_exit_select_min_assignment_spread
                ),
                **dir_combo_same_isolation_kwargs,
            )
        )
        next_extra_port += 1
    if (
        extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_early_retry_on_partial
    ):
        profile_name = (
            "arti_release_browser_"
            "mdsrcspreadpendingearlyusable_loadaware_earlyretrypartial"
        )
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=arti_socks_connect_soft_timeout_attempts,
                arti_dir_microdesc_early_usable_notify=True,
                arti_dir_microdesc_early_retry_on_partial=True,
                arti_dir_microdesc_source_spread=True,
                arti_dir_microdesc_pending_spread=True,
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=True,
                arti_exit_select_health_aware=arti_exit_select_health_aware,
                arti_exit_select_health_min_move_score_bps=(
                    arti_exit_select_health_min_move_score_bps
                ),
                arti_exit_select_avoid_bad_health=(
                    arti_exit_select_avoid_bad_health
                ),
                arti_exit_select_min_assignment_spread=(
                    arti_exit_select_min_assignment_spread
                ),
                **dir_combo_same_isolation_kwargs,
            )
        )
        next_extra_port += 1
    if (
        extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_partial_retry_chunking
    ):
        profile_name = (
            "arti_release_browser_"
            "mdsrcspreadpendingearlyusable_loadaware_partialretrychunk"
        )
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=arti_socks_connect_soft_timeout_attempts,
                arti_dir_microdesc_early_usable_notify=True,
                arti_dir_microdesc_partial_retry_chunking=True,
                arti_dir_microdesc_source_spread=True,
                arti_dir_microdesc_pending_spread=True,
                arti_dir_microdesc_retry_ids_per_request=250,
                arti_dir_microdesc_retry_delay_max_ms=500,
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=True,
                arti_exit_select_health_aware=arti_exit_select_health_aware,
                arti_exit_select_health_min_move_score_bps=(
                    arti_exit_select_health_min_move_score_bps
                ),
                arti_exit_select_avoid_bad_health=(
                    arti_exit_select_avoid_bad_health
                ),
                arti_exit_select_min_assignment_spread=(
                    arti_exit_select_min_assignment_spread
                ),
                **dir_combo_same_isolation_kwargs,
            )
        )
        next_extra_port += 1
    for index, cap in enumerate(
        extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_partial_retry_chunking_max_active_streams
        or []
    ):
        profile_name = (
            extra_arti_dir_combo_partial_retry_chunk_active_cap_profile_name(
                cap, index
            )
        )
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=arti_socks_connect_soft_timeout_attempts,
                arti_dir_microdesc_early_usable_notify=True,
                arti_dir_microdesc_partial_retry_chunking=True,
                arti_dir_microdesc_source_spread=True,
                arti_dir_microdesc_pending_spread=True,
                arti_dir_microdesc_retry_ids_per_request=250,
                arti_dir_microdesc_retry_delay_max_ms=500,
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=True,
                arti_exit_select_health_aware=False,
                arti_exit_select_health_min_move_score_bps=None,
                arti_exit_select_avoid_bad_health=False,
                arti_exit_select_max_active_streams=cap,
                arti_exit_select_min_assignment_spread=None,
                **dir_combo_same_isolation_kwargs,
            )
        )
        next_extra_port += 1
    for index, hedge_ms in enumerate(
        extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_partial_retry_chunking_socks_connect_hedge_ms
        or []
    ):
        profile_name = extra_arti_dir_combo_connect_hedge_profile_name(
            hedge_ms, index
        )
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=arti_socks_connect_soft_timeout_attempts,
                arti_socks_connect_hedge_ms=hedge_ms,
                arti_dir_microdesc_early_usable_notify=True,
                arti_dir_microdesc_partial_retry_chunking=True,
                arti_dir_microdesc_source_spread=True,
                arti_dir_microdesc_pending_spread=True,
                arti_dir_microdesc_retry_ids_per_request=250,
                arti_dir_microdesc_retry_delay_max_ms=500,
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=True,
                arti_exit_select_health_aware=arti_exit_select_health_aware,
                arti_exit_select_health_min_move_score_bps=(
                    arti_exit_select_health_min_move_score_bps
                ),
                arti_exit_select_avoid_bad_health=(
                    arti_exit_select_avoid_bad_health
                ),
                arti_exit_select_min_assignment_spread=(
                    arti_exit_select_min_assignment_spread
                ),
                **dir_combo_same_isolation_kwargs,
            )
        )
        next_extra_port += 1
    for index, (soft_timeout_ms, attempts) in enumerate(
        extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_partial_retry_chunking_socks_connect_soft_timeout_combos
        or []
    ):
        profile_name = extra_arti_dir_combo_soft_timeout_profile_name(
            soft_timeout_ms, attempts, index
        )
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=attempts,
                arti_dir_microdesc_early_usable_notify=True,
                arti_dir_microdesc_partial_retry_chunking=True,
                arti_dir_microdesc_source_spread=True,
                arti_dir_microdesc_pending_spread=True,
                arti_dir_microdesc_retry_ids_per_request=250,
                arti_dir_microdesc_retry_delay_max_ms=500,
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=True,
                arti_exit_select_health_aware=arti_exit_select_health_aware,
                arti_exit_select_health_min_move_score_bps=(
                    arti_exit_select_health_min_move_score_bps
                ),
                arti_exit_select_avoid_bad_health=(
                    arti_exit_select_avoid_bad_health
                ),
                arti_exit_select_min_assignment_spread=(
                    arti_exit_select_min_assignment_spread
                ),
                **dir_combo_same_isolation_kwargs,
            )
        )
        next_extra_port += 1
    if (
        extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_partial_retry_chunking_hs_rend_prebuild_before_desc
    ):
        profile_name = (
            extra_arti_dir_combo_hs_rend_prebuild_before_desc_profile_name()
        )
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_exit_launch_parallelism=arti_exit_launch_parallelism,
                arti_hspool_launch_parallelism=arti_hspool_launch_parallelism,
                arti_hspool_background_start_delay_ms=(
                    arti_hspool_background_start_delay_ms
                ),
                arti_hspool_on_demand_grace_ms=arti_hspool_on_demand_grace_ms,
                arti_hspool_on_demand_race_ms=arti_hspool_on_demand_race_ms,
                arti_hs_rend_prebuild_before_desc=True,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=(
                    arti_socks_connect_soft_timeout_attempts
                ),
                arti_dir_microdesc_early_usable_notify=True,
                arti_dir_microdesc_partial_retry_chunking=True,
                arti_dir_microdesc_source_spread=True,
                arti_dir_microdesc_pending_spread=True,
                arti_dir_microdesc_retry_ids_per_request=250,
                arti_dir_microdesc_retry_delay_max_ms=500,
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=True,
                arti_exit_select_health_aware=arti_exit_select_health_aware,
                arti_exit_select_health_min_move_score_bps=(
                    arti_exit_select_health_min_move_score_bps
                ),
                arti_exit_select_avoid_bad_health=(
                    arti_exit_select_avoid_bad_health
                ),
                arti_exit_select_min_assignment_spread=(
                    arti_exit_select_min_assignment_spread
                ),
                **dir_combo_same_isolation_kwargs,
            )
        )
        next_extra_port += 1
    for index, (
        gap_ms,
        min_assigned_streams,
        min_active_streams,
    ) in enumerate(
        extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_load_aware_partial_retry_chunking_bad_health_replacement_gate_combos
        or []
    ):
        profile_name = (
            extra_arti_dir_combo_partial_retry_chunk_bad_health_gate_profile_name(
                gap_ms, min_assigned_streams, min_active_streams, index
            )
        )
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=arti_socks_connect_soft_timeout_attempts,
                arti_dir_microdesc_early_usable_notify=True,
                arti_dir_microdesc_partial_retry_chunking=True,
                arti_dir_microdesc_bad_health_replacement_suppress_gap_ms=gap_ms,
                arti_dir_microdesc_bad_health_replacement_suppress_min_assigned_streams=(
                    min_assigned_streams
                ),
                arti_dir_microdesc_bad_health_replacement_suppress_min_active_streams=(
                    min_active_streams
                ),
                arti_dir_microdesc_source_spread=True,
                arti_dir_microdesc_pending_spread=True,
                arti_dir_microdesc_retry_ids_per_request=250,
                arti_dir_microdesc_retry_delay_max_ms=500,
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=True,
                arti_exit_select_health_aware=arti_exit_select_health_aware,
                arti_exit_select_health_min_move_score_bps=(
                    arti_exit_select_health_min_move_score_bps
                ),
                arti_exit_select_avoid_bad_health=(
                    arti_exit_select_avoid_bad_health
                ),
                arti_exit_select_min_assignment_spread=(
                    arti_exit_select_min_assignment_spread
                ),
                **dir_combo_same_isolation_kwargs,
            )
        )
        next_extra_port += 1
    if (
        extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_partial_retry_chunking
    ):
        profile_name = (
            "arti_release_browser_"
            "mdsrcspreadpendingearlyusable_partialretrychunk"
        )
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=arti_socks_connect_soft_timeout_attempts,
                arti_dir_microdesc_early_usable_notify=True,
                arti_dir_microdesc_partial_retry_chunking=True,
                arti_dir_microdesc_source_spread=True,
                arti_dir_microdesc_pending_spread=True,
                arti_dir_microdesc_retry_ids_per_request=250,
                arti_dir_microdesc_retry_delay_max_ms=500,
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=False,
                arti_exit_select_health_aware=False,
                arti_exit_select_health_min_move_score_bps=None,
                arti_exit_select_avoid_bad_health=False,
                arti_exit_select_min_assignment_spread=None,
                **dir_combo_same_isolation_kwargs,
            )
        )
        next_extra_port += 1
    for index, cap in enumerate(
        extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_partial_retry_chunking_max_active_streams
        or []
    ):
        profile_name = extra_arti_partial_retry_chunk_active_cap_profile_name(
            cap, index
        )
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=arti_socks_connect_soft_timeout_attempts,
                arti_dir_microdesc_early_usable_notify=True,
                arti_dir_microdesc_partial_retry_chunking=True,
                arti_dir_microdesc_source_spread=True,
                arti_dir_microdesc_pending_spread=True,
                arti_dir_microdesc_retry_ids_per_request=250,
                arti_dir_microdesc_retry_delay_max_ms=500,
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=False,
                arti_exit_select_health_aware=False,
                arti_exit_select_health_min_move_score_bps=None,
                arti_exit_select_avoid_bad_health=False,
                arti_exit_select_max_active_streams=cap,
                arti_exit_select_min_assignment_spread=None,
                **dir_combo_same_isolation_kwargs,
            )
        )
        next_extra_port += 1
    if (
        extra_arti_dir_microdesc_source_spread_pending_spread_early_usable_partial_retry_chunking_hs_rend_prebuild_before_desc
    ):
        profile_name = (
            extra_arti_partial_retry_chunk_hs_rend_prebuild_before_desc_profile_name()
        )
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_exit_launch_parallelism=arti_exit_launch_parallelism,
                arti_hspool_launch_parallelism=arti_hspool_launch_parallelism,
                arti_hspool_background_start_delay_ms=(
                    arti_hspool_background_start_delay_ms
                ),
                arti_hspool_on_demand_grace_ms=arti_hspool_on_demand_grace_ms,
                arti_hspool_on_demand_race_ms=arti_hspool_on_demand_race_ms,
                arti_hs_rend_prebuild_before_desc=True,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=arti_socks_connect_soft_timeout_attempts,
                arti_dir_microdesc_early_usable_notify=True,
                arti_dir_microdesc_partial_retry_chunking=True,
                arti_dir_microdesc_source_spread=True,
                arti_dir_microdesc_pending_spread=True,
                arti_dir_microdesc_retry_ids_per_request=250,
                arti_dir_microdesc_retry_delay_max_ms=500,
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=False,
                arti_exit_select_health_aware=False,
                arti_exit_select_health_min_move_score_bps=None,
                arti_exit_select_avoid_bad_health=False,
                arti_exit_select_min_assignment_spread=None,
                **dir_combo_same_isolation_kwargs,
            )
        )
        next_extra_port += 1
    if extra_arti_dir_microdesc_source_spread_pending_spread:
        profile_name = "arti_release_browser_mdsrcspreadpending"
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=arti_socks_connect_soft_timeout_attempts,
                arti_dir_microdesc_source_spread=True,
                arti_dir_microdesc_pending_spread=True,
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=arti_exit_select_load_aware,
                arti_exit_select_health_aware=arti_exit_select_health_aware,
                arti_exit_select_health_min_move_score_bps=(
                    arti_exit_select_health_min_move_score_bps
                ),
                arti_exit_select_avoid_bad_health=(
                    arti_exit_select_avoid_bad_health
                ),
                arti_exit_select_min_assignment_spread=(
                    arti_exit_select_min_assignment_spread
                ),
                arti_exit_same_isolation_target=arti_exit_same_isolation_target,
            )
        )
        next_extra_port += 1
    for index, ids_per_request in enumerate(
        extra_arti_dir_microdesc_retry_ids_per_request or []
    ):
        suffix = "" if index == 0 else f"_{index + 1}"
        profile_name = (
            f"arti_release_browser_mdretrychunk{ids_per_request}{suffix}"
        )
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=arti_socks_connect_soft_timeout_attempts,
                arti_dirclient_read_timeout_ms=arti_dirclient_read_timeout_ms,
                arti_dir_microdesc_retry_ids_per_request=ids_per_request,
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=arti_exit_select_load_aware,
                arti_exit_select_health_aware=arti_exit_select_health_aware,
                arti_exit_select_health_min_move_score_bps=(
                    arti_exit_select_health_min_move_score_bps
                ),
                arti_exit_select_avoid_bad_health=(
                    arti_exit_select_avoid_bad_health
                ),
                arti_exit_select_min_assignment_spread=(
                    arti_exit_select_min_assignment_spread
                ),
                arti_exit_same_isolation_target=arti_exit_same_isolation_target,
            )
        )
        next_extra_port += 1
    for index, target in enumerate(extra_arti_exit_same_isolation_target or []):
        profile_name = extra_arti_same_isolation_profile_name(target, index)
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=arti_socks_connect_soft_timeout_attempts,
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=arti_exit_select_load_aware,
                arti_exit_select_health_aware=arti_exit_select_health_aware,
                arti_exit_select_health_min_move_score_bps=(
                    arti_exit_select_health_min_move_score_bps
                ),
                arti_exit_select_avoid_bad_health=(
                    arti_exit_select_avoid_bad_health
                ),
                arti_exit_select_min_assignment_spread=(
                    arti_exit_select_min_assignment_spread
                ),
                arti_exit_same_isolation_target=target,
            )
        )
        next_extra_port += 1
    for index, (target, minimum) in enumerate(
        extra_arti_exit_same_isolation_other_isolation_pressure or []
    ):
        profile_name = extra_arti_same_isolation_other_iso_profile_name(
            target, minimum, index
        )
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=arti_socks_connect_soft_timeout_attempts,
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=arti_exit_select_load_aware,
                arti_exit_select_health_aware=arti_exit_select_health_aware,
                arti_exit_select_health_min_move_score_bps=(
                    arti_exit_select_health_min_move_score_bps
                ),
                arti_exit_select_avoid_bad_health=(
                    arti_exit_select_avoid_bad_health
                ),
                arti_exit_select_min_assignment_spread=(
                    arti_exit_select_min_assignment_spread
                ),
                arti_exit_same_isolation_target=target,
                arti_exit_same_isolation_other_isolation_min=minimum,
            )
        )
        next_extra_port += 1
    for index, (target, minimum, cap) in enumerate(
        extra_arti_exit_same_isolation_other_isolation_pressure_assigned_cap
        or []
    ):
        profile_name = extra_arti_same_isolation_other_iso_assigned_cap_profile_name(
            target, minimum, cap, index
        )
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=arti_socks_connect_soft_timeout_attempts,
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=arti_exit_select_load_aware,
                arti_exit_select_health_aware=arti_exit_select_health_aware,
                arti_exit_select_health_min_move_score_bps=(
                    arti_exit_select_health_min_move_score_bps
                ),
                arti_exit_select_avoid_bad_health=(
                    arti_exit_select_avoid_bad_health
                ),
                arti_exit_select_min_assignment_spread=(
                    arti_exit_select_min_assignment_spread
                ),
                arti_exit_select_max_assigned_streams=cap,
                arti_exit_same_isolation_target=target,
                arti_exit_same_isolation_other_isolation_min=minimum,
            )
        )
        next_extra_port += 1
    for index, (target, minimum, cap) in enumerate(
        extra_arti_exit_same_isolation_other_isolation_pressure_assigned_cap_prewarm
        or []
    ):
        profile_name = (
            extra_arti_same_isolation_other_iso_assigned_cap_prewarm_profile_name(
                target, minimum, cap, index
            )
        )
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=arti_socks_connect_soft_timeout_attempts,
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=arti_exit_select_load_aware,
                arti_exit_select_health_aware=arti_exit_select_health_aware,
                arti_exit_select_health_min_move_score_bps=(
                    arti_exit_select_health_min_move_score_bps
                ),
                arti_exit_select_avoid_bad_health=(
                    arti_exit_select_avoid_bad_health
                ),
                arti_exit_select_min_assignment_spread=(
                    arti_exit_select_min_assignment_spread
                ),
                arti_exit_select_max_assigned_streams=cap,
                arti_exit_same_isolation_target=target,
                arti_exit_same_isolation_other_isolation_min=minimum,
                arti_exit_same_isolation_prewarm_first_stream=True,
            )
        )
        next_extra_port += 1
    for index, (target, minimum) in enumerate(
        extra_arti_exit_select_prefer_cold_same_isolation_other_isolation_pressure
        or []
    ):
        profile_name = extra_arti_prefer_cold_same_iso_other_iso_profile_name(
            target, minimum, index
        )
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=arti_socks_connect_soft_timeout_attempts,
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=True,
                arti_exit_select_health_aware=True,
                arti_exit_select_health_min_move_score_bps=(
                    arti_exit_select_health_min_move_score_bps
                ),
                arti_exit_select_avoid_bad_health=True,
                arti_exit_select_min_assignment_spread=(
                    arti_exit_select_min_assignment_spread
                ),
                arti_exit_same_isolation_target=target,
                arti_exit_same_isolation_other_isolation_min=minimum,
                arti_exit_select_prefer_cold_same_isolation=True,
            )
        )
        next_extra_port += 1
    for index, target in enumerate(
        extra_arti_exit_load_aware_same_isolation_target or []
    ):
        profile_name = extra_arti_load_aware_same_isolation_profile_name(
            target, index
        )
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=arti_socks_connect_soft_timeout_attempts,
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=True,
                arti_exit_select_health_aware=False,
                arti_exit_select_health_min_move_score_bps=None,
                arti_exit_select_avoid_bad_health=False,
                arti_exit_select_min_assignment_spread=(
                    arti_exit_select_min_assignment_spread
                ),
                arti_exit_same_isolation_target=target,
            )
        )
        next_extra_port += 1
    for index, target in enumerate(
        extra_arti_exit_same_isolation_prewarm_target or []
    ):
        profile_name = extra_arti_same_isolation_prewarm_profile_name(target, index)
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=arti_socks_connect_soft_timeout_attempts,
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=arti_exit_select_load_aware,
                arti_exit_select_health_aware=arti_exit_select_health_aware,
                arti_exit_select_health_min_move_score_bps=(
                    arti_exit_select_health_min_move_score_bps
                ),
                arti_exit_select_avoid_bad_health=(
                    arti_exit_select_avoid_bad_health
                ),
                arti_exit_select_min_assignment_spread=(
                    arti_exit_select_min_assignment_spread
                ),
                arti_exit_same_isolation_target=target,
                arti_exit_same_isolation_prewarm_first_stream=True,
            )
        )
        next_extra_port += 1
    for index, (target, min_assigned) in enumerate(
        extra_arti_exit_same_isolation_min_assigned_streams or []
    ):
        profile_name = extra_arti_same_isolation_min_assigned_profile_name(
            target, min_assigned, index
        )
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=arti_socks_connect_soft_timeout_attempts,
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=arti_exit_select_load_aware,
                arti_exit_select_health_aware=arti_exit_select_health_aware,
                arti_exit_select_health_min_move_score_bps=(
                    arti_exit_select_health_min_move_score_bps
                ),
                arti_exit_select_avoid_bad_health=(
                    arti_exit_select_avoid_bad_health
                ),
                arti_exit_select_min_assignment_spread=(
                    arti_exit_select_min_assignment_spread
                ),
                arti_exit_same_isolation_target=target,
                arti_exit_same_isolation_min_assigned_streams=min_assigned,
                arti_exit_same_isolation_prewarm_first_stream=True,
            )
        )
        next_extra_port += 1
    for index, target in enumerate(
        extra_arti_exit_same_isolation_prefer_topup_on_tie or []
    ):
        profile_name = extra_arti_same_isolation_prefer_topup_on_tie_profile_name(
            target, index
        )
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=arti_socks_connect_soft_timeout_attempts,
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=arti_exit_select_load_aware,
                arti_exit_select_health_aware=arti_exit_select_health_aware,
                arti_exit_select_health_min_move_score_bps=(
                    arti_exit_select_health_min_move_score_bps
                ),
                arti_exit_select_avoid_bad_health=(
                    arti_exit_select_avoid_bad_health
                ),
                arti_exit_select_min_assignment_spread=(
                    arti_exit_select_min_assignment_spread
                ),
                arti_exit_same_isolation_target=target,
                arti_exit_same_isolation_prewarm_first_stream=True,
                arti_exit_same_isolation_prefer_topup_on_tie=True,
            )
        )
        next_extra_port += 1
    for index, target in enumerate(
        extra_arti_exit_load_aware_same_isolation_prewarm_target or []
    ):
        profile_name = extra_arti_load_aware_same_isolation_prewarm_profile_name(
            target, index
        )
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=arti_socks_connect_soft_timeout_attempts,
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=True,
                arti_exit_select_health_aware=False,
                arti_exit_select_health_min_move_score_bps=None,
                arti_exit_select_avoid_bad_health=False,
                arti_exit_select_min_assignment_spread=(
                    arti_exit_select_min_assignment_spread
                ),
                arti_exit_same_isolation_target=target,
                arti_exit_same_isolation_prewarm_first_stream=True,
            )
        )
        next_extra_port += 1
    for index, target in enumerate(
        extra_arti_exit_health_aware_same_isolation_prewarm_target or []
    ):
        profile_name = extra_arti_health_aware_same_isolation_prewarm_profile_name(
            target, index
        )
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=arti_socks_connect_soft_timeout_attempts,
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=True,
                arti_exit_select_health_aware=True,
                arti_exit_select_health_min_move_score_bps=(
                    arti_exit_select_health_min_move_score_bps
                ),
                arti_exit_select_avoid_bad_health=False,
                arti_exit_select_min_assignment_spread=(
                    arti_exit_select_min_assignment_spread
                ),
                arti_exit_same_isolation_target=target,
                arti_exit_same_isolation_prewarm_first_stream=True,
            )
        )
        next_extra_port += 1
    for index, (target, min_score, wait_ms) in enumerate(
        extra_arti_exit_select_health_min_move_score_same_isolation_pending_wait
        or []
    ):
        profile_name = extra_arti_health_min_score_same_iso_pending_wait_profile_name(
            target, min_score, wait_ms, index
        )
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=arti_socks_connect_soft_timeout_attempts,
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=True,
                arti_exit_select_health_aware=True,
                arti_exit_select_health_min_move_score_bps=min_score,
                arti_exit_select_avoid_bad_health=False,
                arti_exit_select_min_assignment_spread=(
                    arti_exit_select_min_assignment_spread
                ),
                arti_exit_same_isolation_target=target,
                arti_exit_same_isolation_pending_wait_ms=wait_ms,
            )
        )
        next_extra_port += 1
    if extra_arti_exit_select_load_aware:
        profile_name = extra_arti_load_aware_profile_name()
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=arti_socks_connect_soft_timeout_attempts,
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=True,
                arti_exit_select_health_aware=arti_exit_select_health_aware,
                arti_exit_select_health_min_move_score_bps=(
                    arti_exit_select_health_min_move_score_bps
                ),
                arti_exit_select_avoid_bad_health=(
                    arti_exit_select_avoid_bad_health
                ),
                arti_exit_select_min_assignment_spread=(
                    arti_exit_select_min_assignment_spread
                ),
                arti_exit_same_isolation_target=arti_exit_same_isolation_target,
            )
        )
        next_extra_port += 1
    if extra_arti_exit_select_health_aware:
        profile_name = extra_arti_health_aware_profile_name()
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=arti_socks_connect_soft_timeout_attempts,
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=True,
                arti_exit_select_health_aware=True,
                arti_exit_select_health_min_move_score_bps=(
                    arti_exit_select_health_min_move_score_bps
                ),
                arti_exit_select_avoid_bad_health=(
                    arti_exit_select_avoid_bad_health
                ),
                arti_exit_select_min_assignment_spread=(
                    arti_exit_select_min_assignment_spread
                ),
                arti_exit_same_isolation_target=arti_exit_same_isolation_target,
            )
        )
        next_extra_port += 1
    for index, min_score in enumerate(
        extra_arti_exit_select_health_min_move_score_bps or []
    ):
        profile_name = extra_arti_health_min_score_profile_name(min_score, index)
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=arti_socks_connect_soft_timeout_attempts,
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=True,
                arti_exit_select_health_aware=True,
                arti_exit_select_health_min_move_score_bps=min_score,
                arti_exit_select_avoid_bad_health=(
                    arti_exit_select_avoid_bad_health
                ),
                arti_exit_select_min_assignment_spread=(
                    arti_exit_select_min_assignment_spread
                ),
                arti_exit_same_isolation_target=arti_exit_same_isolation_target,
            )
        )
        next_extra_port += 1
    for index, (min_score, cap) in enumerate(
        extra_arti_exit_select_health_min_move_score_assigned_cap or []
    ):
        profile_name = extra_arti_health_min_score_assigned_cap_profile_name(
            min_score, cap, index
        )
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=arti_socks_connect_soft_timeout_attempts,
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=True,
                arti_exit_select_health_aware=True,
                arti_exit_select_health_min_move_score_bps=min_score,
                arti_exit_select_avoid_bad_health=(
                    arti_exit_select_avoid_bad_health
                ),
                arti_exit_select_max_assigned_streams=cap,
                arti_exit_select_min_assignment_spread=(
                    arti_exit_select_min_assignment_spread
                ),
                arti_exit_same_isolation_target=arti_exit_same_isolation_target,
            )
        )
        next_extra_port += 1
    for index, min_spread in enumerate(
        extra_arti_exit_select_health_aware_min_assignment_spread or []
    ):
        profile_name = extra_arti_health_aware_spread_profile_name(min_spread, index)
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=arti_socks_connect_soft_timeout_attempts,
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=True,
                arti_exit_select_health_aware=True,
                arti_exit_select_health_min_move_score_bps=(
                    arti_exit_select_health_min_move_score_bps
                ),
                arti_exit_select_avoid_bad_health=False,
                arti_exit_select_min_assignment_spread=min_spread,
                arti_exit_same_isolation_target=arti_exit_same_isolation_target,
            )
        )
        next_extra_port += 1
    for index, min_assigned in enumerate(
        extra_arti_exit_select_health_aware_min_assigned or []
    ):
        profile_name = extra_arti_health_aware_min_assigned_profile_name(
            min_assigned, index
        )
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=arti_socks_connect_soft_timeout_attempts,
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=True,
                arti_exit_select_health_aware=True,
                arti_exit_select_health_aware_min_assigned=min_assigned,
                arti_exit_select_health_min_move_score_bps=(
                    arti_exit_select_health_min_move_score_bps
                ),
                arti_exit_select_avoid_bad_health=(
                    arti_exit_select_avoid_bad_health
                ),
                arti_exit_select_min_assignment_spread=(
                    arti_exit_select_min_assignment_spread
                ),
                arti_exit_same_isolation_target=arti_exit_same_isolation_target,
            )
        )
        next_extra_port += 1
    if extra_arti_exit_select_avoid_bad_health:
        profile_name = extra_arti_avoid_bad_health_profile_name()
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=arti_socks_connect_soft_timeout_attempts,
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=True,
                arti_exit_select_health_aware=False,
                arti_exit_select_health_min_move_score_bps=(
                    arti_exit_select_health_min_move_score_bps
                ),
                arti_exit_select_avoid_bad_health=True,
                arti_exit_select_min_assignment_spread=(
                    arti_exit_select_min_assignment_spread
                ),
                arti_exit_same_isolation_target=arti_exit_same_isolation_target,
            )
        )
        next_extra_port += 1
    if extra_arti_exit_select_health_aware_avoid_bad_health:
        profile_name = extra_arti_health_aware_avoid_bad_health_profile_name()
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=arti_socks_connect_soft_timeout_attempts,
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=True,
                arti_exit_select_health_aware=True,
                arti_exit_select_health_min_move_score_bps=(
                    arti_exit_select_health_min_move_score_bps
                ),
                arti_exit_select_avoid_bad_health=True,
                arti_exit_select_min_assignment_spread=(
                    arti_exit_select_min_assignment_spread
                ),
                arti_exit_same_isolation_target=arti_exit_same_isolation_target,
            )
        )
        next_extra_port += 1
    for index, target in enumerate(
        extra_arti_exit_select_health_aware_avoid_bad_health_same_isolation_target
        or []
    ):
        profile_name = extra_arti_health_aware_avoid_bad_health_same_iso_profile_name(
            target, index
        )
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=arti_socks_connect_soft_timeout_attempts,
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=True,
                arti_exit_select_health_aware=True,
                arti_exit_select_health_min_move_score_bps=(
                    arti_exit_select_health_min_move_score_bps
                ),
                arti_exit_select_avoid_bad_health=True,
                arti_exit_select_min_assignment_spread=(
                    arti_exit_select_min_assignment_spread
                ),
                arti_exit_same_isolation_target=target,
            )
        )
        next_extra_port += 1
    for index, target in enumerate(
        extra_arti_exit_select_health_aware_same_isolation_prefer_cold_target or []
    ):
        profile_name = extra_arti_health_aware_same_iso_prefer_cold_profile_name(
            target, index
        )
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=arti_socks_connect_soft_timeout_attempts,
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=True,
                arti_exit_select_health_aware=True,
                arti_exit_select_health_min_move_score_bps=(
                    arti_exit_select_health_min_move_score_bps
                ),
                arti_exit_select_avoid_bad_health=False,
                arti_exit_select_min_assignment_spread=(
                    arti_exit_select_min_assignment_spread
                ),
                arti_exit_same_isolation_target=target,
                arti_exit_select_prefer_cold_same_isolation=True,
            )
        )
        next_extra_port += 1
    for index, target in enumerate(
        extra_arti_exit_select_prefer_cold_same_isolation_target or []
    ):
        profile_name = extra_arti_prefer_cold_same_iso_profile_name(target, index)
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=arti_socks_connect_soft_timeout_attempts,
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=True,
                arti_exit_select_health_aware=True,
                arti_exit_select_health_min_move_score_bps=(
                    arti_exit_select_health_min_move_score_bps
                ),
                arti_exit_select_avoid_bad_health=True,
                arti_exit_select_min_assignment_spread=(
                    arti_exit_select_min_assignment_spread
                ),
                arti_exit_same_isolation_target=target,
                arti_exit_select_prefer_cold_same_isolation=True,
            )
        )
        next_extra_port += 1
    for index, (target, cap) in enumerate(
        extra_arti_exit_select_prefer_cold_same_isolation_active_cap or []
    ):
        profile_name = extra_arti_prefer_cold_same_iso_active_cap_profile_name(
            target, cap, index
        )
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=arti_socks_connect_soft_timeout_attempts,
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=True,
                arti_exit_select_health_aware=True,
                arti_exit_select_health_min_move_score_bps=(
                    arti_exit_select_health_min_move_score_bps
                ),
                arti_exit_select_avoid_bad_health=True,
                arti_exit_select_max_active_streams=cap,
                arti_exit_select_min_assignment_spread=(
                    arti_exit_select_min_assignment_spread
                ),
                arti_exit_same_isolation_target=target,
                arti_exit_select_prefer_cold_same_isolation=True,
            )
        )
        next_extra_port += 1
    for index, target in enumerate(
        extra_arti_exit_select_prefer_cold_same_isolation_prewarm_target or []
    ):
        profile_name = extra_arti_prefer_cold_same_iso_prewarm_profile_name(
            target, index
        )
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=arti_socks_connect_soft_timeout_attempts,
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=True,
                arti_exit_select_health_aware=True,
                arti_exit_select_health_min_move_score_bps=(
                    arti_exit_select_health_min_move_score_bps
                ),
                arti_exit_select_avoid_bad_health=True,
                arti_exit_select_min_assignment_spread=(
                    arti_exit_select_min_assignment_spread
                ),
                arti_exit_same_isolation_target=target,
                arti_exit_same_isolation_prewarm_first_stream=True,
                arti_exit_select_prefer_cold_same_isolation=True,
            )
        )
        next_extra_port += 1
    for index, (target, wait_ms) in enumerate(
        extra_arti_exit_select_health_aware_same_isolation_prefer_cold_prewarm_pending_wait
        or []
    ):
        profile_name = (
            extra_arti_health_aware_same_iso_prefer_cold_prewarm_pending_wait_profile_name(
                target, wait_ms, index
            )
        )
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=arti_socks_connect_soft_timeout_attempts,
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=True,
                arti_exit_select_health_aware=True,
                arti_exit_select_health_min_move_score_bps=(
                    arti_exit_select_health_min_move_score_bps
                ),
                arti_exit_select_avoid_bad_health=False,
                arti_exit_select_min_assignment_spread=(
                    arti_exit_select_min_assignment_spread
                ),
                arti_exit_same_isolation_target=target,
                arti_exit_same_isolation_pending_wait_ms=wait_ms,
                arti_exit_same_isolation_prewarm_first_stream=True,
                arti_exit_select_prefer_cold_same_isolation=True,
            )
        )
        next_extra_port += 1
    for index, target in enumerate(
        extra_arti_exit_select_avoid_bad_health_unknown_fallback_prefer_cold_same_isolation_target
        or []
    ):
        profile_name = extra_arti_unknown_fallback_prefer_cold_same_iso_profile_name(
            target, index
        )
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=arti_socks_connect_soft_timeout_attempts,
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=True,
                arti_exit_select_health_aware=True,
                arti_exit_select_health_min_move_score_bps=(
                    arti_exit_select_health_min_move_score_bps
                ),
                arti_exit_select_avoid_bad_health=True,
                arti_exit_select_avoid_bad_health_unknown_fallback=True,
                arti_exit_select_min_assignment_spread=(
                    arti_exit_select_min_assignment_spread
                ),
                arti_exit_same_isolation_target=target,
                arti_exit_select_prefer_cold_same_isolation=True,
            )
        )
        next_extra_port += 1
    for index, min_spread in enumerate(
        extra_arti_exit_select_min_assignment_spread or []
    ):
        profile_name = extra_arti_load_aware_spread_profile_name(min_spread, index)
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=arti_socks_connect_soft_timeout_attempts,
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=True,
                arti_exit_select_health_aware=arti_exit_select_health_aware,
                arti_exit_select_health_min_move_score_bps=(
                    arti_exit_select_health_min_move_score_bps
                ),
                arti_exit_select_avoid_bad_health=(
                    arti_exit_select_avoid_bad_health
                ),
                arti_exit_select_min_assignment_spread=min_spread,
                arti_exit_same_isolation_target=arti_exit_same_isolation_target,
            )
        )
        next_extra_port += 1
    for index, min_assigned in enumerate(
        extra_arti_exit_select_healthy_over_cold_min_assigned or []
    ):
        profile_name = extra_arti_load_aware_healthy_over_cold_profile_name(
            min_assigned, index
        )
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=arti_socks_connect_soft_timeout_attempts,
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=True,
                arti_exit_select_health_min_move_score_bps=(
                    arti_exit_select_health_min_move_score_bps
                ),
                arti_exit_select_min_assignment_spread=(
                    arti_exit_select_min_assignment_spread
                ),
                arti_exit_select_healthy_over_cold_min_assigned=min_assigned,
                arti_exit_same_isolation_target=arti_exit_same_isolation_target,
            )
        )
        next_extra_port += 1
    for index, min_assigned in enumerate(
        extra_arti_exit_select_healthy_over_cold_guard_only_min_assigned or []
    ):
        profile_name = extra_arti_guard_only_healthy_over_cold_profile_name(
            min_assigned, index
        )
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=arti_socks_connect_soft_timeout_attempts,
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_health_min_move_score_bps=(
                    arti_exit_select_health_min_move_score_bps
                ),
                arti_exit_select_healthy_over_cold_guard_only_min_assigned=(
                    min_assigned
                ),
                arti_exit_same_isolation_target=arti_exit_same_isolation_target,
            )
        )
        next_extra_port += 1
    for index, cap in enumerate(extra_arti_exit_select_max_active_streams or []):
        profile_name = extra_arti_load_aware_active_cap_profile_name(cap, index)
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=arti_socks_connect_soft_timeout_attempts,
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=True,
                arti_exit_select_health_aware=arti_exit_select_health_aware,
                arti_exit_select_health_min_move_score_bps=(
                    arti_exit_select_health_min_move_score_bps
                ),
                arti_exit_select_avoid_bad_health=(
                    arti_exit_select_avoid_bad_health
                ),
                arti_exit_select_max_active_streams=cap,
                arti_exit_select_min_assignment_spread=(
                    arti_exit_select_min_assignment_spread
                ),
                arti_exit_same_isolation_target=arti_exit_same_isolation_target,
            )
        )
        next_extra_port += 1
    for index, cap in enumerate(extra_arti_exit_select_max_assigned_streams or []):
        profile_name = extra_arti_load_aware_assigned_cap_profile_name(cap, index)
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=arti_socks_connect_soft_timeout_attempts,
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=True,
                arti_exit_select_health_aware=arti_exit_select_health_aware,
                arti_exit_select_health_min_move_score_bps=(
                    arti_exit_select_health_min_move_score_bps
                ),
                arti_exit_select_avoid_bad_health=(
                    arti_exit_select_avoid_bad_health
                ),
                arti_exit_select_max_assigned_streams=cap,
                arti_exit_select_min_assignment_spread=(
                    arti_exit_select_min_assignment_spread
                ),
                arti_exit_same_isolation_target=arti_exit_same_isolation_target,
            )
        )
        next_extra_port += 1
    for index, active_no_data_ms in enumerate(
        extra_arti_exit_select_bad_health_active_no_data_ms or []
    ):
        profile_name = extra_arti_load_aware_active_no_data_profile_name(
            active_no_data_ms, index
        )
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=arti_socks_connect_soft_timeout_attempts,
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=True,
                arti_exit_select_health_aware=arti_exit_select_health_aware,
                arti_exit_select_health_min_move_score_bps=(
                    arti_exit_select_health_min_move_score_bps
                ),
                arti_exit_select_avoid_bad_health=True,
                arti_exit_select_bad_health_active_no_data_ms=(
                    active_no_data_ms
                ),
                arti_exit_select_max_active_streams=(
                    arti_exit_select_max_active_streams
                ),
                arti_exit_select_min_assignment_spread=(
                    arti_exit_select_min_assignment_spread
                ),
                arti_exit_same_isolation_target=arti_exit_same_isolation_target,
            )
        )
        next_extra_port += 1
    for index, hedge_ms in enumerate(
        extra_arti_exit_select_bad_health_hedge_ms or []
    ):
        profile_name = extra_arti_load_aware_bad_health_hedge_profile_name(
            hedge_ms, index
        )
        specs.append(
            ProxySpec(
                name=profile_name,
                kind="arti",
                bin_path=arti_bin,
                port=next_extra_port,
                output_dir=output_dir / profile_name,
                log_level=arti_log_level,
                arti_proxy_buffer_size=arti_proxy_buffer_size,
                arti_exit_select_parallelism=arti_exit_select_parallelism,
                arti_min_exit_circs_for_port=arti_min_exit_circs_for_port,
                arti_socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
                arti_socks_connect_soft_timeout_attempts=arti_socks_connect_soft_timeout_attempts,
                arti_exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
                arti_exit_select_load_aware=True,
                arti_exit_select_health_aware=arti_exit_select_health_aware,
                arti_exit_select_health_min_move_score_bps=(
                    arti_exit_select_health_min_move_score_bps
                ),
                arti_exit_select_avoid_bad_health=True,
                arti_exit_select_bad_health_hedge_ms=hedge_ms,
                arti_exit_select_max_active_streams=(
                    arti_exit_select_max_active_streams
                ),
                arti_exit_select_min_assignment_spread=(
                    arti_exit_select_min_assignment_spread
                ),
                arti_exit_same_isolation_target=arti_exit_same_isolation_target,
            )
        )
        next_extra_port += 1

    if arti_proxy_app_buffer_len is not None:
        for spec in specs:
            if spec.kind == "arti" and spec.arti_proxy_app_buffer_len is None:
                spec.arti_proxy_app_buffer_len = arti_proxy_app_buffer_len
    if arti_stream_scheduler_burst is not None:
        for spec in specs:
            if spec.kind == "arti" and spec.arti_stream_scheduler_burst is None:
                spec.arti_stream_scheduler_burst = arti_stream_scheduler_burst
    if arti_dirclient_read_timeout_ms is not None:
        for spec in specs:
            if spec.kind == "arti" and spec.arti_dirclient_read_timeout_ms is None:
                spec.arti_dirclient_read_timeout_ms = arti_dirclient_read_timeout_ms
    if arti_exit_launch_parallelism is not None:
        for spec in specs:
            if (
                spec.kind == "arti"
                and spec.arti_exit_launch_parallelism is None
            ):
                spec.arti_exit_launch_parallelism = arti_exit_launch_parallelism
    if arti_socks_relay_byte_timing:
        for spec in specs:
            if spec.kind == "arti":
                spec.arti_socks_relay_byte_timing = True
    if arti_socks_partial_relay_idle_timeout_ms is not None:
        for spec in specs:
            if spec.kind == "arti":
                spec.arti_socks_partial_relay_idle_timeout_ms = (
                    arti_socks_partial_relay_idle_timeout_ms
                )
    if arti_socks_no_tor_byte_relay_timeout_ms is not None:
        for spec in specs:
            if spec.kind == "arti":
                spec.arti_socks_no_tor_byte_relay_timeout_ms = (
                    arti_socks_no_tor_byte_relay_timeout_ms
                )
    if arti_exit_same_isolation_require_bad_health:
        for spec in specs:
            if spec.kind == "arti":
                spec.arti_exit_same_isolation_require_bad_health = True
    if arti_exit_same_isolation_min_assigned_streams is not None:
        for spec in specs:
            if spec.kind == "arti":
                spec.arti_exit_same_isolation_min_assigned_streams = (
                    arti_exit_same_isolation_min_assigned_streams
                )
    if arti_exit_same_isolation_pending_wait_ms is not None:
        for spec in specs:
            if spec.kind == "arti" and spec.arti_exit_same_isolation_target is not None:
                spec.arti_exit_same_isolation_pending_wait_ms = (
                    arti_exit_same_isolation_pending_wait_ms
                )
    if arti_exit_same_isolation_prewarm_first_stream:
        for spec in specs:
            if spec.kind == "arti":
                spec.arti_exit_same_isolation_prewarm_first_stream = True
    if arti_exit_select_prefer_cold_same_isolation:
        for spec in specs:
            if spec.kind == "arti":
                spec.arti_exit_select_prefer_cold_same_isolation = True
    if arti_exit_select_avoid_bad_health_unknown_fallback:
        for spec in specs:
            if spec.kind == "arti":
                spec.arti_exit_select_avoid_bad_health_unknown_fallback = True
    if arti_exit_select_bad_health_hedge_ms is not None:
        for spec in specs:
            if (
                spec.kind == "arti"
                and spec.arti_exit_select_bad_health_hedge_ms is None
            ):
                spec.arti_exit_select_bad_health_hedge_ms = (
                    arti_exit_select_bad_health_hedge_ms
                )
    if arti_exit_select_bad_health_stream_idle_ms is not None:
        for spec in specs:
            if spec.kind == "arti":
                spec.arti_exit_select_bad_health_stream_idle_ms = (
                    arti_exit_select_bad_health_stream_idle_ms
                )
    if arti_exit_select_bad_health_active_no_data_ms is not None:
        for spec in specs:
            if spec.kind == "arti":
                spec.arti_exit_select_bad_health_active_no_data_ms = (
                    arti_exit_select_bad_health_active_no_data_ms
                )
    if arti_exit_select_max_active_streams is not None:
        for spec in specs:
            if spec.kind == "arti":
                spec.arti_exit_select_max_active_streams = (
                    arti_exit_select_max_active_streams
                )
    if arti_exit_select_max_assigned_streams is not None:
        for spec in specs:
            if spec.kind == "arti":
                spec.arti_exit_select_max_assigned_streams = (
                    arti_exit_select_max_assigned_streams
                )
    if arti_exit_select_healthy_over_cold_min_assigned is not None:
        for spec in specs:
            if spec.kind == "arti":
                spec.arti_exit_select_load_aware = True
                spec.arti_exit_select_healthy_over_cold_min_assigned = (
                    arti_exit_select_healthy_over_cold_min_assigned
                )
    if arti_exit_select_healthy_over_cold_guard_only_min_assigned is not None:
        for spec in specs:
            if spec.kind == "arti":
                spec.arti_exit_select_healthy_over_cold_guard_only_min_assigned = (
                    arti_exit_select_healthy_over_cold_guard_only_min_assigned
                )

    running: list[RunningProxy] = []
    taps: dict[str, ByteTapServer] = {}
    storage_by_name: dict[str, dict[str, Path]] = {}
    bootable_specs: list[ProxySpec] = []
    arti_warm_cache_seed_storage: dict[str, Path] | None = None
    arti_warm_cache_seed_name: str | None = None
    try:
        for spec in specs:
            spec.output_dir.mkdir(parents=True, exist_ok=True)
            storage = prepare_proxy_storage(spec)
            storage_by_name[spec.name] = storage
            seeded_from = None
            if (
                warm_cache
                and share_arti_warm_cache_seed
                and spec.kind == "arti"
                and arti_warm_cache_seed_storage is not None
                and seed_arti_cache_dir(arti_warm_cache_seed_storage, storage)
            ):
                seeded_from = arti_warm_cache_seed_name
            warmup_boot = None
            if warm_cache:
                warmup_boot = warmup_proxy(spec, storage)
            profiles[spec.name] = {
                "cache_mode": "warm" if warm_cache else "cold",
                "warmup_boot": warmup_boot,
                "boot": {},
                "post_boot_wait_seconds": post_boot_wait,
                "benchmarks": {},
            }
            if seeded_from is not None:
                profiles[spec.name]["arti_warm_cache_seeded_from"] = seeded_from
            if spec.kind == "arti":
                assert isinstance(profiles[spec.name], dict)
                profiles[spec.name]["arti_bin"] = str(spec.bin_path)
                profiles[spec.name]["binary"] = binary_info(spec.bin_path)
                profiles[spec.name]["arti_log_level"] = effective_arti_log_level(
                    log_level=spec.log_level,
                    socks_relay_byte_timing=spec.arti_socks_relay_byte_timing,
                    hspool_launch_parallelism=spec.arti_hspool_launch_parallelism,
                    hspool_background_start_delay_ms=(
                        spec.arti_hspool_background_start_delay_ms
                    ),
                    hspool_guarded_stem_target=(
                        spec.arti_hspool_guarded_stem_target
                    ),
                    hspool_on_demand_grace_ms=spec.arti_hspool_on_demand_grace_ms,
                    hspool_on_demand_race_ms=spec.arti_hspool_on_demand_race_ms,
                    hs_intro_rend_overlap=spec.arti_hs_intro_rend_overlap,
                    hs_rend_prebuild_before_desc=(
                        spec.arti_hs_rend_prebuild_before_desc
                    ),
                    hs_desc_shared_cache=spec.arti_hs_desc_shared_cache,
                    hs_intro_circuit_hedge_ms=(
                        spec.arti_hs_intro_circuit_hedge_ms
                    ),
                )
                profiles[spec.name]["arti_proxy_buffer_size"] = spec.arti_proxy_buffer_size
                profiles[spec.name]["arti_proxy_app_buffer_len"] = (
                    spec.arti_proxy_app_buffer_len
                )
                profiles[spec.name]["arti_stream_scheduler_burst"] = (
                    spec.arti_stream_scheduler_burst
                )
                profiles[spec.name]["arti_socks_tor_to_client_coalesce_bytes"] = (
                    spec.arti_socks_tor_to_client_coalesce_bytes
                )
                profiles[spec.name]["arti_stream_ready_data_coalesce_bytes"] = (
                    spec.arti_stream_ready_data_coalesce_bytes
                )
                profiles[spec.name]["arti_exit_select_parallelism_override"] = (
                    spec.arti_exit_select_parallelism
                )
                profiles[spec.name]["arti_exit_launch_parallelism_override"] = (
                    spec.arti_exit_launch_parallelism
                )
                profiles[spec.name]["arti_min_exit_circs_for_port_override"] = (
                    spec.arti_min_exit_circs_for_port
                )
                profiles[spec.name]["arti_preemptive_443_circs"] = (
                    spec.arti_preemptive_443_circs
                )
                profiles[spec.name]["arti_preemptive_443_burst_min_requests"] = (
                    spec.arti_preemptive_443_burst_min_requests
                )
                profiles[spec.name]["arti_preemptive_443_busy_active_age_ms"] = (
                    spec.arti_preemptive_443_busy_active_age_ms
                )
                profiles[spec.name]["arti_socks_connect_soft_timeout_ms"] = (
                    spec.arti_socks_connect_soft_timeout_ms
                )
                profiles[spec.name]["arti_socks_connect_soft_timeout_attempts"] = (
                    spec.arti_socks_connect_soft_timeout_attempts
                )
                profiles[spec.name]["arti_socks_connect_hedge_ms"] = (
                    spec.arti_socks_connect_hedge_ms
                )
                profiles[spec.name]["arti_socks_relay_byte_timing"] = (
                    spec.arti_socks_relay_byte_timing
                )
                profiles[spec.name]["arti_socks_partial_relay_idle_timeout_ms"] = (
                    spec.arti_socks_partial_relay_idle_timeout_ms
                )
                profiles[spec.name]["arti_socks_no_tor_byte_relay_timeout_ms"] = (
                    spec.arti_socks_no_tor_byte_relay_timeout_ms
                )
                profiles[spec.name]["arti_dirclient_read_timeout_ms"] = (
                    spec.arti_dirclient_read_timeout_ms
                )
                profiles[spec.name]["arti_dir_microdesc_early_usable_notify"] = (
                    spec.arti_dir_microdesc_early_usable_notify
                )
                profiles[spec.name]["arti_dir_microdesc_early_retry_on_partial"] = (
                    spec.arti_dir_microdesc_early_retry_on_partial
                )
                profiles[spec.name]["arti_dir_microdesc_partial_retry_chunking"] = (
                    spec.arti_dir_microdesc_partial_retry_chunking
                )
                profiles[spec.name][
                    "arti_dir_microdesc_disable_bad_health_replacement"
                ] = spec.arti_dir_microdesc_disable_bad_health_replacement
                profiles[spec.name][
                    "arti_dir_microdesc_bad_health_replacement_suppress_gap_ms"
                ] = spec.arti_dir_microdesc_bad_health_replacement_suppress_gap_ms
                profiles[spec.name][
                    "arti_dir_microdesc_bad_health_replacement_suppress_min_assigned_streams"
                ] = (
                    spec.arti_dir_microdesc_bad_health_replacement_suppress_min_assigned_streams
                )
                profiles[spec.name][
                    "arti_dir_microdesc_bad_health_replacement_suppress_min_active_streams"
                ] = (
                    spec.arti_dir_microdesc_bad_health_replacement_suppress_min_active_streams
                )
                profiles[spec.name]["arti_dir_microdesc_source_spread"] = (
                    spec.arti_dir_microdesc_source_spread
                )
                profiles[spec.name]["arti_dir_microdesc_pending_spread"] = (
                    spec.arti_dir_microdesc_pending_spread
                )
                profiles[spec.name]["arti_dir_microdesc_retry_ids_per_request"] = (
                    spec.arti_dir_microdesc_retry_ids_per_request
                )
                profiles[spec.name]["arti_dir_microdesc_retry_delay_max_ms"] = (
                    spec.arti_dir_microdesc_retry_delay_max_ms
                )
                profiles[spec.name]["arti_exit_pending_hedge_ms"] = (
                    spec.arti_exit_pending_hedge_ms
                )
                profiles[spec.name]["arti_exit_select_load_aware"] = (
                    spec.arti_exit_select_load_aware
                )
                profiles[spec.name]["arti_exit_select_health_aware"] = (
                    spec.arti_exit_select_health_aware
                )
                profiles[spec.name]["arti_exit_select_health_aware_min_assigned"] = (
                    spec.arti_exit_select_health_aware_min_assigned
                )
                profiles[spec.name]["arti_exit_select_health_min_move_score_bps"] = (
                    spec.arti_exit_select_health_min_move_score_bps
                )
                profiles[spec.name]["arti_exit_select_avoid_bad_health"] = (
                    spec.arti_exit_select_avoid_bad_health
                )
                profiles[spec.name][
                    "arti_exit_select_avoid_bad_health_unknown_fallback"
                ] = spec.arti_exit_select_avoid_bad_health_unknown_fallback
                profiles[spec.name]["arti_exit_select_bad_health_hedge_ms"] = (
                    spec.arti_exit_select_bad_health_hedge_ms
                )
                profiles[spec.name]["arti_exit_select_bad_health_stream_idle_ms"] = (
                    spec.arti_exit_select_bad_health_stream_idle_ms
                )
                profiles[spec.name][
                    "arti_exit_select_bad_health_active_no_data_ms"
                ] = spec.arti_exit_select_bad_health_active_no_data_ms
                profiles[spec.name]["arti_exit_select_max_active_streams"] = (
                    spec.arti_exit_select_max_active_streams
                )
                profiles[spec.name]["arti_exit_select_max_assigned_streams"] = (
                    spec.arti_exit_select_max_assigned_streams
                )
                profiles[spec.name]["arti_exit_select_min_assignment_spread"] = (
                    spec.arti_exit_select_min_assignment_spread
                )
                profiles[spec.name][
                    "arti_exit_select_healthy_over_cold_min_assigned"
                ] = spec.arti_exit_select_healthy_over_cold_min_assigned
                profiles[spec.name][
                    "arti_exit_select_healthy_over_cold_guard_only_min_assigned"
                ] = spec.arti_exit_select_healthy_over_cold_guard_only_min_assigned
                profiles[spec.name]["arti_exit_same_isolation_target"] = (
                    spec.arti_exit_same_isolation_target
                )
                profiles[spec.name][
                    "arti_exit_same_isolation_other_isolation_min"
                ] = spec.arti_exit_same_isolation_other_isolation_min
                profiles[spec.name]["arti_exit_same_isolation_require_bad_health"] = (
                    spec.arti_exit_same_isolation_require_bad_health
                )
                profiles[spec.name]["arti_exit_same_isolation_min_assigned_streams"] = (
                    spec.arti_exit_same_isolation_min_assigned_streams
                )
                profiles[spec.name]["arti_exit_same_isolation_pending_wait_ms"] = (
                    spec.arti_exit_same_isolation_pending_wait_ms
                )
                profiles[spec.name]["arti_exit_same_isolation_prewarm_first_stream"] = (
                    spec.arti_exit_same_isolation_prewarm_first_stream
                )
                profiles[spec.name]["arti_exit_same_isolation_prefer_topup_on_tie"] = (
                    spec.arti_exit_same_isolation_prefer_topup_on_tie
                )
                profiles[spec.name]["arti_exit_select_prefer_cold_same_isolation"] = (
                    spec.arti_exit_select_prefer_cold_same_isolation
                )
                profiles[spec.name]["arti_hspool_launch_parallelism"] = (
                    spec.arti_hspool_launch_parallelism
                )
                profiles[spec.name]["arti_hspool_background_start_delay_ms"] = (
                    spec.arti_hspool_background_start_delay_ms
                )
                profiles[spec.name]["arti_hspool_guarded_stem_target"] = (
                    spec.arti_hspool_guarded_stem_target
                )
                profiles[spec.name]["arti_hspool_guarded_stem_target_defer_post_boot"] = (
                    spec.arti_hspool_guarded_stem_target_defer_post_boot
                )
                profiles[spec.name]["arti_hspool_on_demand_grace_ms"] = (
                    spec.arti_hspool_on_demand_grace_ms
                )
                profiles[spec.name]["arti_hspool_on_demand_race_ms"] = (
                    spec.arti_hspool_on_demand_race_ms
                )
                profiles[spec.name]["arti_hs_intro_rend_overlap"] = (
                    spec.arti_hs_intro_rend_overlap
                )
                profiles[spec.name]["arti_hs_rend_prebuild_before_desc"] = (
                    spec.arti_hs_rend_prebuild_before_desc
                )
                profiles[spec.name]["arti_hs_desc_shared_cache"] = (
                    spec.arti_hs_desc_shared_cache
                )
                profiles[spec.name]["arti_hs_intro_circuit_hedge_ms"] = (
                    spec.arti_hs_intro_circuit_hedge_ms
                )
                profiles[spec.name].update(
                    effective_arti_exit_selector_metadata(
                        requested_load_aware=spec.arti_exit_select_load_aware,
                        requested_health_aware=spec.arti_exit_select_health_aware,
                        requested_avoid_bad_health=spec.arti_exit_select_avoid_bad_health,
                        requested_avoid_bad_health_unknown_fallback=(
                            spec.arti_exit_select_avoid_bad_health_unknown_fallback
                        ),
                        requested_same_isolation_target=spec.arti_exit_same_isolation_target,
                        requested_prefer_cold_same_isolation=(
                            spec.arti_exit_select_prefer_cold_same_isolation
                        ),
                        requested_max_active_streams=(
                            spec.arti_exit_select_max_active_streams
                        ),
                        source_tweaks=source_tweaks,
                    )
                )
                if (
                    warm_cache
                    and share_arti_warm_cache_seed
                    and warmup_boot is not None
                    and warmup_boot.get("ok")
                    and arti_warm_cache_seed_storage is None
                ):
                    arti_warm_cache_seed_storage = storage
                    arti_warm_cache_seed_name = spec.name
            if warmup_boot is not None and not warmup_boot.get("ok"):
                profiles[spec.name]["boot"] = {
                    "ok": False,
                    "error": "warmup bootstrap failed",
                }
                continue
            bootable_specs.append(spec)

        launch_plan = plan_interleaved_launches(bootable_specs, profiles)
        launch_plan_by_name = {entry.spec.name: entry for entry in launch_plan}
        launch_started = time.monotonic()
        for entry in launch_plan:
            target_start = launch_started + entry.launch_offset_seconds
            remaining = target_start - time.monotonic()
            if remaining > 0:
                time.sleep(remaining)
            storage = storage_by_name[entry.spec.name]
            launch_started_epoch_ms = time.time() * 1000
            launch_started_monotonic_seconds = time.monotonic()
            proc, lines = start_proxy_for_spec(entry.spec, storage, torrc_name="torrc")
            running.append(
                RunningProxy(
                    spec=entry.spec,
                    proc=proc,
                    lines=lines,
                    storage_paths=storage,
                    started_monotonic_seconds=launch_started_monotonic_seconds,
                )
            )
            profile = profiles[entry.spec.name]
            assert isinstance(profile, dict)
            profile["interleaved_launch"] = {
                "strategy": (
                    "warmup_boot_alignment"
                    if entry.expected_boot_seconds is not None
                    else "as_listed"
                ),
                "order": entry.launch_order,
                "planned_offset_seconds": round(entry.launch_offset_seconds, 3),
                "expected_boot_seconds": (
                    round(entry.expected_boot_seconds, 3)
                    if entry.expected_boot_seconds is not None
                    else None
                ),
                "started_epoch_ms": round(launch_started_epoch_ms, 3),
            }

        boot_results = wait_for_interleaved_boots(running)
        for proxy in running:
            boot = boot_results.get(
                proxy.spec.name,
                {"ok": False, "error": "boot wait did not complete"},
            )
            normalize_interleaved_boot_seconds_from_launch(
                boot, proxy.started_monotonic_seconds
            )
            profile = profiles[proxy.spec.name]
            assert isinstance(profile, dict)
            profile["boot"] = boot
            if proxy.spec.kind == "c_tor":
                profile["torrc"] = read_torrc_quality(proxy.spec.output_dir / "torrc")

        if not all(
            isinstance(profiles[spec.name], dict)
            and profiles[spec.name].get("boot", {}).get("ok")
            for spec in bootable_specs
        ):
            return profiles

        running_by_name = {proxy.spec.name: proxy for proxy in running}

        if byte_tap:
            for spec in bootable_specs:
                profile = profiles[spec.name]
                assert isinstance(profile, dict)
                try:
                    taps[spec.name] = start_byte_tap_for_profile(
                        profile_name=spec.name,
                        proxy_port=spec.port,
                        port_offset=byte_tap_port_offset,
                        event_limit=byte_tap_event_limit,
                        socks_reply_bind_port_tag=(
                            byte_tap_socks_reply_bind_port_tag
                        ),
                    )
                except OSError as exc:
                    profile["byte_tap"] = {
                        "enabled": True,
                        "ok": False,
                        "error": str(exc),
                    }
                    profile["boot"] = {
                        "ok": False,
                        "error": f"byte tap failed: {exc}",
                    }
                    return profiles

        wait_after_boot(post_boot_wait)
        for spec in bootable_specs:
            profile = profiles[spec.name]
            assert isinstance(profile, dict)
            profile["benchmarks"] = {url: {"runs": []} for url in targets}

        profile_orders = balanced_latin_square_specs(bootable_specs)
        target_orders = (
            rotating_target_orders(targets)
            if interleaved_target_order == "rotating"
            else [list(targets)]
        )
        sequence_index = 0
        for run_index in range(1, runs + 1):
            ordered_targets = (
                target_orders[(run_index - 1) % len(target_orders)]
                if target_orders
                else []
            )
            for target_index, url in enumerate(ordered_targets):
                block_index = (run_index - 1) * len(targets) + target_index
                order_row_index = (
                    (run_index - 1 + target_index) % len(profile_orders)
                    if profile_orders
                    else 0
                )
                ordered_specs = (
                    profile_orders[order_row_index]
                    if profile_orders
                    else []
                )
                ordered_profile_names = [ordered_spec.name for ordered_spec in ordered_specs]
                for order_index, spec in enumerate(ordered_specs, start=1):
                    sequence_index += 1
                    profile = profiles[spec.name]
                    assert isinstance(profile, dict)
                    benchmarks = profile["benchmarks"]
                    assert isinstance(benchmarks, dict)
                    bench = benchmarks[url]
                    assert isinstance(bench, dict)
                    browser_port = browser_port_for_spec(spec, taps)
                    run = run_browser_once(
                        browser_bin=browser_bin,
                        port=browser_port,
                        output_dir=spec.output_dir,
                        url=url,
                        url_slug=slug(url),
                        run_index=run_index,
                        timeout=timeout,
                        window_size=window_size,
                        compact_output=compact_output,
                        browser_net_log=browser_net_log,
                        browser_serial_http_connections=(
                            browser_serial_http_connections
                        ),
                        browser_max_persistent_connections_per_server=(
                            browser_max_persistent_connections_per_server
                        ),
                        browser_block_url_substrings=browser_block_url_substrings,
                        browser_startup_seed_root=browser_startup_seed_root,
                        no_browser_startup_seed=no_browser_startup_seed,
                    )
                    run["schedule"] = {
                        "mode": "interleaved",
                        "sequence_index": sequence_index,
                        "round": run_index,
                        "target_index": target_index + 1,
                        "target_order": list(ordered_targets),
                        "block_index": block_index + 1,
                        "order_index": order_index,
                        "profile_count": len(ordered_specs),
                        "order_row_index": order_row_index + 1 if profile_orders else None,
                        "profile_order": ordered_profile_names,
                        "launch_order": (
                            launch_plan_by_name[spec.name].launch_order
                            if spec.name in launch_plan_by_name
                            else None
                        ),
                    }
                    proxy = running_by_name.get(spec.name)
                    if proxy is not None:
                        record_proxy_run_signals(
                            profile,
                            run,
                            proxy.lines,
                            tail_limit=proxy_log_tail_lines,
                            keep_success_tail_limit=proxy_run_tail_lines,
                        )
                    bench["runs"].append(run)

        for spec in bootable_specs:
            profile = profiles[spec.name]
            assert isinstance(profile, dict)
            benchmarks = profile.get("benchmarks", {})
            assert isinstance(benchmarks, dict)
            for bench in benchmarks.values():
                assert isinstance(bench, dict)
                runs_payload = bench.get("runs", [])
                assert isinstance(runs_payload, list)
                bench["summary"] = summarize_browser(runs_payload)
        return profiles
    finally:
        for tap in taps.values():
            tap.stop()
        for proxy in running:
            stop_process(proxy.proc)
            profile = profiles.get(proxy.spec.name)
            if isinstance(profile, dict):
                tap = taps.get(proxy.spec.name)
                if tap is not None:
                    profile["byte_tap"] = tap.snapshot()
                record_proxy_output_tail(
                    profile, proxy.lines, limit=proxy_log_tail_lines
                )
        if compact_output:
            for spec in specs:
                profile = profiles.get(spec.name)
                if not isinstance(profile, dict) or profile.get("skipped"):
                    continue
                profile["proxy_artifacts"] = cleanup_named_paths(
                    storage_by_name.get(spec.name, {})
                )


def prepare_proxy_storage(spec: ProxySpec) -> dict[str, Path]:
    if spec.kind == "c_tor":
        data_dir = spec.output_dir / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        return {"data_dir": data_dir}
    cache_dir = (spec.output_dir / "cache").resolve()
    state_dir = (spec.output_dir / "state").resolve()
    cache_dir.mkdir(parents=True, exist_ok=True)
    state_dir.mkdir(parents=True, exist_ok=True)
    return {"cache_dir": cache_dir, "state_dir": state_dir}


def seed_arti_cache_dir(seed_storage: dict[str, Path], storage: dict[str, Path]) -> bool:
    source_cache = seed_storage.get("cache_dir")
    dest_cache = storage.get("cache_dir")
    if not isinstance(source_cache, Path) or not isinstance(dest_cache, Path):
        return False
    if source_cache == dest_cache or not source_cache.exists():
        return False
    for child in source_cache.iterdir():
        target = dest_cache / child.name
        if child.is_dir():
            shutil.copytree(child, target, dirs_exist_ok=True)
        else:
            shutil.copy2(child, target)
    return True


def warmup_proxy(spec: ProxySpec, storage: dict[str, Path]) -> dict[str, object]:
    proc, lines = start_proxy_for_spec(spec, storage, torrc_name="warmup.torrc")
    try:
        return wait_for_line(
            proc,
            lines,
            timeout=180.0,
            ready_text=ready_text_for_spec(spec),
            process_name=f"{spec.kind} warmup",
        )
    finally:
        stop_process(proc)


def start_proxy_for_spec(
    spec: ProxySpec, storage: dict[str, Path], *, torrc_name: str
) -> tuple[subprocess.Popen[str], queue.Queue[str]]:
    if spec.kind == "c_tor":
        return start_c_tor(
            tor_bin=spec.bin_path,
            port=spec.port,
            data_dir=storage["data_dir"],
            torrc=spec.output_dir / torrc_name,
        )
    return start_arti(
        arti_bin=spec.bin_path,
        port=spec.port,
        cache_dir=storage["cache_dir"],
        state_dir=storage["state_dir"],
        log_level=spec.log_level,
        proxy_buffer_size=spec.arti_proxy_buffer_size,
        proxy_app_buffer_len=spec.arti_proxy_app_buffer_len,
        stream_scheduler_burst=spec.arti_stream_scheduler_burst,
        exit_select_parallelism=spec.arti_exit_select_parallelism,
        exit_launch_parallelism=spec.arti_exit_launch_parallelism,
        hspool_launch_parallelism=spec.arti_hspool_launch_parallelism,
        hspool_background_start_delay_ms=(
            spec.arti_hspool_background_start_delay_ms
        ),
        hspool_guarded_stem_target=spec.arti_hspool_guarded_stem_target,
        hspool_guarded_stem_target_defer_post_boot=(
            spec.arti_hspool_guarded_stem_target_defer_post_boot
        ),
        hspool_on_demand_grace_ms=spec.arti_hspool_on_demand_grace_ms,
        hspool_on_demand_race_ms=spec.arti_hspool_on_demand_race_ms,
        hs_intro_circuit_hedge_ms=spec.arti_hs_intro_circuit_hedge_ms,
        hs_rend_prebuild_before_desc=spec.arti_hs_rend_prebuild_before_desc,
        hs_desc_shared_cache=spec.arti_hs_desc_shared_cache,
        min_exit_circs_for_port=spec.arti_min_exit_circs_for_port,
        preemptive_443_circs=spec.arti_preemptive_443_circs,
        socks_connect_soft_timeout_ms=spec.arti_socks_connect_soft_timeout_ms,
        socks_connect_soft_timeout_attempts=(
            spec.arti_socks_connect_soft_timeout_attempts
        ),
        socks_connect_hedge_ms=spec.arti_socks_connect_hedge_ms,
        socks_relay_byte_timing=spec.arti_socks_relay_byte_timing,
        socks_tor_to_client_coalesce_bytes=(
            spec.arti_socks_tor_to_client_coalesce_bytes
        ),
        stream_ready_data_coalesce_bytes=(
            spec.arti_stream_ready_data_coalesce_bytes
        ),
        socks_partial_relay_idle_timeout_ms=(
            spec.arti_socks_partial_relay_idle_timeout_ms
        ),
        socks_no_tor_byte_relay_timeout_ms=(
            spec.arti_socks_no_tor_byte_relay_timeout_ms
        ),
        dirclient_read_timeout_ms=spec.arti_dirclient_read_timeout_ms,
        dir_microdesc_early_usable_notify=(
            spec.arti_dir_microdesc_early_usable_notify
        ),
        dir_microdesc_early_retry_on_partial=(
            spec.arti_dir_microdesc_early_retry_on_partial
        ),
        dir_microdesc_partial_retry_chunking=(
            spec.arti_dir_microdesc_partial_retry_chunking
        ),
        dir_microdesc_disable_bad_health_replacement=(
            spec.arti_dir_microdesc_disable_bad_health_replacement
        ),
        dir_microdesc_bad_health_replacement_suppress_gap_ms=(
            spec.arti_dir_microdesc_bad_health_replacement_suppress_gap_ms
        ),
        dir_microdesc_bad_health_replacement_suppress_min_assigned_streams=(
            spec.arti_dir_microdesc_bad_health_replacement_suppress_min_assigned_streams
        ),
        dir_microdesc_bad_health_replacement_suppress_min_active_streams=(
            spec.arti_dir_microdesc_bad_health_replacement_suppress_min_active_streams
        ),
        dir_microdesc_source_spread=spec.arti_dir_microdesc_source_spread,
        dir_microdesc_pending_spread=spec.arti_dir_microdesc_pending_spread,
        dir_microdesc_retry_ids_per_request=(
            spec.arti_dir_microdesc_retry_ids_per_request
        ),
        dir_microdesc_retry_delay_max_ms=(
            spec.arti_dir_microdesc_retry_delay_max_ms
        ),
        exit_pending_hedge_ms=spec.arti_exit_pending_hedge_ms,
        exit_select_load_aware=spec.arti_exit_select_load_aware,
        exit_select_health_aware=spec.arti_exit_select_health_aware,
        exit_select_health_aware_min_assigned=(
            spec.arti_exit_select_health_aware_min_assigned
        ),
        exit_select_health_min_move_score_bps=(
            spec.arti_exit_select_health_min_move_score_bps
        ),
        exit_select_avoid_bad_health=spec.arti_exit_select_avoid_bad_health,
        exit_select_avoid_bad_health_unknown_fallback=(
            spec.arti_exit_select_avoid_bad_health_unknown_fallback
        ),
        exit_select_bad_health_hedge_ms=(
            spec.arti_exit_select_bad_health_hedge_ms
        ),
        exit_select_bad_health_stream_idle_ms=(
            spec.arti_exit_select_bad_health_stream_idle_ms
        ),
        exit_select_bad_health_active_no_data_ms=(
            spec.arti_exit_select_bad_health_active_no_data_ms
        ),
        exit_select_max_active_streams=spec.arti_exit_select_max_active_streams,
        exit_select_max_assigned_streams=spec.arti_exit_select_max_assigned_streams,
        exit_select_min_assignment_spread=spec.arti_exit_select_min_assignment_spread,
        exit_select_healthy_over_cold_min_assigned=(
            spec.arti_exit_select_healthy_over_cold_min_assigned
        ),
        exit_select_healthy_over_cold_guard_only_min_assigned=(
            spec.arti_exit_select_healthy_over_cold_guard_only_min_assigned
        ),
        exit_same_isolation_target=spec.arti_exit_same_isolation_target,
        exit_same_isolation_other_isolation_min=(
            spec.arti_exit_same_isolation_other_isolation_min
        ),
        exit_same_isolation_require_bad_health=(
            spec.arti_exit_same_isolation_require_bad_health
        ),
        exit_same_isolation_min_assigned_streams=(
            spec.arti_exit_same_isolation_min_assigned_streams
        ),
        exit_same_isolation_pending_wait_ms=(
            spec.arti_exit_same_isolation_pending_wait_ms
        ),
        exit_same_isolation_prewarm_first_stream=(
            spec.arti_exit_same_isolation_prewarm_first_stream
        ),
        exit_same_isolation_prefer_topup_on_tie=(
            spec.arti_exit_same_isolation_prefer_topup_on_tie
        ),
        exit_select_prefer_cold_same_isolation=(
            spec.arti_exit_select_prefer_cold_same_isolation
        ),
        hs_intro_rend_overlap=spec.arti_hs_intro_rend_overlap,
    )


def ready_text_for_spec(spec: ProxySpec) -> str:
    if spec.kind == "c_tor":
        return "Bootstrapped 100%"
    return "proxy now functional"


def wait_for_interleaved_boots(
    running: list[RunningProxy],
) -> dict[str, dict[str, object]]:
    results: dict[str, dict[str, object]] = {}
    lock = threading.Lock()

    def wait_for_proxy(proxy: RunningProxy) -> None:
        boot = wait_for_line(
            proxy.proc,
            proxy.lines,
            timeout=180.0,
            ready_text=ready_text_for_spec(proxy.spec),
            process_name=proxy.spec.kind,
        )
        with lock:
            results[proxy.spec.name] = boot

    threads = [
        threading.Thread(target=wait_for_proxy, args=(proxy,), daemon=True)
        for proxy in running
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return results


def normalize_interleaved_boot_seconds_from_launch(
    boot: dict[str, object], started_monotonic_seconds: float
) -> None:
    if boot.get("ok") is not True:
        return
    ready_monotonic = numeric_value(boot.get("ready_monotonic_seconds"))
    if ready_monotonic is None:
        return
    wait_seconds = numeric_value(boot.get("seconds"))
    if wait_seconds is not None:
        boot["wait_seconds_after_launch_plan"] = round(wait_seconds, 3)
    seconds_from_launch = max(0.0, ready_monotonic - started_monotonic_seconds)
    rounded = round(seconds_from_launch, 3)
    boot["seconds"] = rounded
    boot["seconds_from_launch"] = rounded


def plan_interleaved_launches(
    specs: list[ProxySpec], profiles: dict[str, object]
) -> list[InterleavedLaunchPlanEntry]:
    estimates: list[tuple[int, ProxySpec, float | None]] = []
    max_expected_boot_seconds = 0.0
    has_expected_boot_seconds = False
    for index, spec in enumerate(specs):
        expected_boot_seconds = None
        profile = profiles.get(spec.name)
        if isinstance(profile, dict):
            warmup_boot = profile.get("warmup_boot")
            if isinstance(warmup_boot, dict) and warmup_boot.get("ok"):
                expected_boot_seconds = numeric_value(warmup_boot.get("seconds"))
        if expected_boot_seconds is not None:
            has_expected_boot_seconds = True
            max_expected_boot_seconds = max(
                max_expected_boot_seconds, expected_boot_seconds
            )
        estimates.append((index, spec, expected_boot_seconds))

    if not has_expected_boot_seconds:
        return [
            InterleavedLaunchPlanEntry(
                spec=spec,
                launch_order=index + 1,
                launch_offset_seconds=0.0,
                expected_boot_seconds=expected_boot_seconds,
            )
            for index, (_original_index, spec, expected_boot_seconds) in enumerate(
                estimates
            )
        ]

    ordered = sorted(
        estimates,
        key=lambda item: (
            -(item[2] if item[2] is not None else max_expected_boot_seconds),
            item[0],
        ),
    )
    return [
        InterleavedLaunchPlanEntry(
            spec=spec,
            launch_order=launch_order,
            launch_offset_seconds=max(
                0.0,
                max_expected_boot_seconds
                - (
                    expected_boot_seconds
                    if expected_boot_seconds is not None
                    else max_expected_boot_seconds
                ),
            ),
            expected_boot_seconds=expected_boot_seconds,
        )
        for launch_order, (_original_index, spec, expected_boot_seconds) in enumerate(
            ordered, start=1
        )
    ]


def balanced_latin_square_specs(specs: list[ProxySpec]) -> list[list[ProxySpec]]:
    count = len(specs)
    if count == 0:
        return []

    first_row: list[int] = []
    for position in range(count):
        if position == 0:
            index = 0
        elif position % 2 == 1:
            index = (position + 1) // 2
        else:
            index = count - position // 2
        first_row.append(index % count)

    rows = [
        [specs[(index + shift) % count] for index in first_row]
        for shift in range(count)
    ]
    if rows and [spec.name for spec in rows[0]] != [spec.name for spec in specs]:
        rows.insert(0, list(specs))
    if count % 2 == 1:
        rows.extend([list(reversed(row)) for row in rows])
    return rows


def rotating_target_orders(targets: list[str]) -> list[list[str]]:
    count = len(targets)
    if count == 0:
        return []
    return [targets[offset:] + targets[:offset] for offset in range(count)]


def extra_arti_profile_name(parallelism: int, index: int) -> str:
    name = f"arti_release_browser_exit{parallelism}"
    return name if index == 0 else f"{name}_{index + 1}"


def extra_arti_launch_profile_name(parallelism: int, index: int) -> str:
    name = f"arti_release_browser_launch{parallelism}"
    return name if index == 0 else f"{name}_{index + 1}"


def extra_arti_hspool_launch_profile_name(parallelism: int, index: int) -> str:
    name = f"arti_release_browser_hspoollaunch{parallelism}"
    return name if index == 0 else f"{name}_{index + 1}"


def extra_arti_hspool_background_start_delay_profile_name(delay_ms: int, index: int) -> str:
    name = f"arti_release_browser_hspoolstart{delay_ms}ms"
    return name if index == 0 else f"{name}_{index + 1}"


def extra_arti_hspool_guarded_stem_target_profile_name(target: int, index: int) -> str:
    name = f"arti_release_browser_hspoolguarded{target}"
    return name if index == 0 else f"{name}_{index + 1}"


def extra_arti_hspool_guarded_stem_target_defer_post_boot_profile_name(
    target: int, index: int
) -> str:
    name = f"arti_release_browser_hspoolguarded{target}_deferpostboot"
    return name if index == 0 else f"{name}_{index + 1}"


def extra_arti_hspool_on_demand_grace_profile_name(grace_ms: int, index: int) -> str:
    name = f"arti_release_browser_hspoolgrace{grace_ms}ms"
    return name if index == 0 else f"{name}_{index + 1}"


def extra_arti_hspool_on_demand_race_profile_name(race_ms: int, index: int) -> str:
    name = f"arti_release_browser_hspoolrace{race_ms}ms"
    return name if index == 0 else f"{name}_{index + 1}"


def extra_arti_hs_intro_rend_overlap_profile_name() -> str:
    return "arti_release_browser_hsintrooverlap"


def extra_arti_hs_rend_prebuild_before_desc_profile_name() -> str:
    return "arti_release_browser_hsrendpredesc"


def extra_arti_hs_desc_shared_cache_profile_name() -> str:
    return "arti_release_browser_hsdescshare"


def extra_arti_hs_intro_circuit_hedge_profile_name(hedge_ms: int, index: int) -> str:
    name = f"arti_release_browser_hsintrohedge{hedge_ms}ms"
    return name if index == 0 else f"{name}_{index + 1}"


def extra_arti_proxy_buffer_profile_name(buffer_size: str, index: int) -> str:
    token = re.sub(r"[^A-Za-z0-9]+", "", buffer_size).lower() or "custom"
    name = f"arti_release_browser_buf{token}"
    return name if index == 0 else f"{name}_{index + 1}"


def extra_arti_proxy_app_buffer_profile_name(buffer_len: int, index: int) -> str:
    name = f"arti_release_browser_appbuf{buffer_len}"
    return name if index == 0 else f"{name}_{index + 1}"


def extra_arti_stream_scheduler_burst_profile_name(burst: int, index: int) -> str:
    name = f"arti_release_browser_schedburst{burst}"
    return name if index == 0 else f"{name}_{index + 1}"


def extra_arti_socks_tor_to_client_coalesce_profile_name(
    coalesce_bytes: int, index: int
) -> str:
    name = f"arti_release_browser_torclientcoalesce{coalesce_bytes}"
    return name if index == 0 else f"{name}_{index + 1}"


def extra_arti_stream_ready_data_coalesce_profile_name(
    coalesce_bytes: int, index: int
) -> str:
    name = f"arti_release_browser_streamreadycoalesce{coalesce_bytes}"
    return name if index == 0 else f"{name}_{index + 1}"


def extra_arti_soft_timeout_profile_name(timeout_ms: int, index: int) -> str:
    name = f"arti_release_browser_soft{timeout_ms}ms"
    return name if index == 0 else f"{name}_{index + 1}"


def extra_arti_soft_timeout_attempts_profile_name(attempts: int, index: int) -> str:
    name = f"arti_release_browser_softattempts{attempts}"
    return name if index == 0 else f"{name}_{index + 1}"


def extra_arti_socks_connect_hedge_profile_name(hedge_ms: int, index: int) -> str:
    name = f"arti_release_browser_connecthedge{hedge_ms}ms"
    return name if index == 0 else f"{name}_{index + 1}"


def extra_arti_dir_combo_connect_hedge_profile_name(hedge_ms: int, index: int) -> str:
    name = (
        "arti_release_browser_"
        "mdsrcspreadpendingearlyusable_loadaware_partialretrychunk_"
        f"connecthedge{hedge_ms}ms"
    )
    return name if index == 0 else f"{name}_{index + 1}"


def extra_arti_dir_combo_hs_rend_prebuild_before_desc_profile_name() -> str:
    return (
        "arti_release_browser_"
        "mdsrcspreadpendingearlyusable_loadaware_partialretrychunk_"
        "hsrendpredesc"
    )


def extra_arti_partial_retry_chunk_hs_rend_prebuild_before_desc_profile_name() -> str:
    return (
        "arti_release_browser_"
        "mdsrcspreadpendingearlyusable_partialretrychunk_"
        "hsrendpredesc"
    )


def extra_arti_dir_combo_partial_retry_chunk_active_cap_profile_name(
    cap: int, index: int
) -> str:
    name = (
        "arti_release_browser_"
        "mdsrcspreadpendingearlyusable_loadaware_partialretrychunk_"
        f"activecap{cap}"
    )
    return name if index == 0 else f"{name}_{index + 1}"


def extra_arti_partial_retry_chunk_active_cap_profile_name(
    cap: int, index: int
) -> str:
    name = (
        "arti_release_browser_"
        "mdsrcspreadpendingearlyusable_partialretrychunk_"
        f"activecap{cap}"
    )
    return name if index == 0 else f"{name}_{index + 1}"


def extra_arti_dir_combo_bad_health_gap_profile_name(gap_ms: int, index: int) -> str:
    name = (
        "arti_release_browser_"
        "mdsrcspreadpendingearlyusable_loadaware_"
        f"badhealthgap{gap_ms}ms"
    )
    return name if index == 0 else f"{name}_{index + 1}"


def extra_arti_dir_combo_bad_health_gate_profile_name(
    gap_ms: int,
    min_assigned_streams: int,
    min_active_streams: int,
    index: int,
) -> str:
    name = (
        "arti_release_browser_"
        "mdsrcspreadpendingearlyusable_loadaware_"
        f"badhealthgate{gap_ms}ms_"
        f"assigned{min_assigned_streams}_"
        f"active{min_active_streams}"
    )
    return name if index == 0 else f"{name}_{index + 1}"


def extra_arti_dir_combo_partial_retry_chunk_bad_health_gate_profile_name(
    gap_ms: int,
    min_assigned_streams: int,
    min_active_streams: int,
    index: int,
) -> str:
    name = (
        "arti_release_browser_"
        "mdsrcspreadpendingearlyusable_loadaware_partialretrychunk_"
        f"badhealthgate{gap_ms}ms_"
        f"assigned{min_assigned_streams}_"
        f"active{min_active_streams}"
    )
    return name if index == 0 else f"{name}_{index + 1}"


def extra_arti_dir_combo_soft_timeout_profile_name(
    timeout_ms: int, attempts: int, index: int
) -> str:
    name = (
        "arti_release_browser_"
        "mdsrcspreadpendingearlyusable_loadaware_partialretrychunk_"
        f"soft{timeout_ms}ms_attempts{attempts}"
    )
    return name if index == 0 else f"{name}_{index + 1}"


def extra_arti_no_tor_byte_timeout_profile_name(timeout_ms: int, index: int) -> str:
    name = f"arti_release_browser_notorbyte{timeout_ms}ms"
    return name if index == 0 else f"{name}_{index + 1}"


def extra_arti_partial_idle_timeout_profile_name(timeout_ms: int, index: int) -> str:
    name = f"arti_release_browser_partialidle{timeout_ms}ms"
    return name if index == 0 else f"{name}_{index + 1}"


def extra_arti_soft_timeout_combo_profile_name(
    timeout_ms: int, attempts: int, index: int
) -> str:
    name = f"arti_release_browser_soft{timeout_ms}ms_attempts{attempts}"
    return name if index == 0 else f"{name}_{index + 1}"


def extra_arti_soft_timeout_pending_hedge_combo_profile_name(
    timeout_ms: int, attempts: int, hedge_ms: int, index: int
) -> str:
    name = (
        f"arti_release_browser_soft{timeout_ms}ms_attempts{attempts}"
        f"_pending{hedge_ms}ms"
    )
    return name if index == 0 else f"{name}_{index + 1}"


def extra_arti_pending_hedge_profile_name(hedge_ms: int, index: int) -> str:
    name = f"arti_release_browser_pending{hedge_ms}ms"
    return name if index == 0 else f"{name}_{index + 1}"


def extra_arti_min_exit_circs_profile_name(circs: int, index: int) -> str:
    name = f"arti_release_browser_preemptive{circs}"
    return name if index == 0 else f"{name}_{index + 1}"


def extra_arti_preemptive_443_circs_profile_name(circs: int, index: int) -> str:
    name = f"arti_release_browser_preemptive443_{circs}"
    return name if index == 0 else f"{name}_{index + 1}"


def extra_arti_preemptive_443_burst_profile_name(min_requests: int, index: int) -> str:
    name = f"arti_release_browser_preemptive443burst_{min_requests}"
    return name if index == 0 else f"{name}_{index + 1}"


def extra_arti_preemptive_443_busy_active_age_profile_name(
    busy_active_age_ms: int, index: int
) -> str:
    name = f"arti_release_browser_preemptive443busy{busy_active_age_ms}ms"
    return name if index == 0 else f"{name}_{index + 1}"


def extra_arti_same_isolation_other_iso_profile_name(
    target: int, minimum: int, index: int
) -> str:
    name = f"arti_release_browser_sameiso{target}_otheriso{minimum}"
    return name if index == 0 else f"{name}_{index + 1}"


def extra_arti_same_isolation_other_iso_assigned_cap_profile_name(
    target: int, minimum: int, cap: int, index: int
) -> str:
    name = f"arti_release_browser_sameiso{target}_otheriso{minimum}_assignedcap{cap}"
    return name if index == 0 else f"{name}_{index + 1}"


def extra_arti_same_isolation_other_iso_assigned_cap_prewarm_profile_name(
    target: int, minimum: int, cap: int, index: int
) -> str:
    name = (
        f"arti_release_browser_sameiso{target}_otheriso{minimum}"
        f"_assignedcap{cap}_prewarmfirst"
    )
    return name if index == 0 else f"{name}_{index + 1}"


def extra_arti_prefer_cold_same_iso_other_iso_profile_name(
    target: int, minimum: int, index: int
) -> str:
    name = (
        "arti_release_browser_healthaware_avoidbadhealth_"
        f"sameiso{target}_otheriso{minimum}_prefercold"
    )
    return name if index == 0 else f"{name}_{index + 1}"


def extra_arti_dirclient_read_timeout_profile_name(
    timeout_ms: int, index: int
) -> str:
    name = f"arti_release_browser_dirread{timeout_ms}ms"
    return name if index == 0 else f"{name}_{index + 1}"


def extra_arti_load_aware_profile_name() -> str:
    return "arti_release_browser_loadaware"


def extra_arti_health_aware_profile_name() -> str:
    return "arti_release_browser_healthaware"


def extra_arti_health_min_score_profile_name(min_score: int, index: int) -> str:
    name = f"arti_release_browser_healthaware_min{min_score}bps"
    return name if index == 0 else f"{name}_{index + 1}"


def extra_arti_health_min_score_assigned_cap_profile_name(
    min_score: int, cap: int, index: int
) -> str:
    name = f"arti_release_browser_healthaware_min{min_score}bps_assignedcap{cap}"
    return name if index == 0 else f"{name}_{index + 1}"


def extra_arti_health_aware_spread_profile_name(
    min_spread: int, index: int
) -> str:
    name = f"arti_release_browser_healthaware_spread{min_spread}"
    return name if index == 0 else f"{name}_{index + 1}"


def extra_arti_health_aware_min_assigned_profile_name(
    min_assigned: int, index: int
) -> str:
    name = f"arti_release_browser_healthaware_minassigned{min_assigned}"
    return name if index == 0 else f"{name}_{index + 1}"


def extra_arti_load_aware_active_cap_profile_name(cap: int, index: int) -> str:
    name = f"arti_release_browser_loadaware_activecap{cap}"
    return name if index == 0 else f"{name}_{index + 1}"


def extra_arti_load_aware_assigned_cap_profile_name(cap: int, index: int) -> str:
    name = f"arti_release_browser_loadaware_assignedcap{cap}"
    return name if index == 0 else f"{name}_{index + 1}"


def extra_arti_load_aware_active_no_data_profile_name(
    active_no_data_ms: int, index: int
) -> str:
    name = f"arti_release_browser_loadaware_activenodata{active_no_data_ms}ms"
    return name if index == 0 else f"{name}_{index + 1}"


def extra_arti_load_aware_bad_health_hedge_profile_name(
    hedge_ms: int, index: int
) -> str:
    name = f"arti_release_browser_loadaware_badhedge{hedge_ms}ms"
    return name if index == 0 else f"{name}_{index + 1}"


def extra_arti_avoid_bad_health_profile_name() -> str:
    return "arti_release_browser_avoidbadhealth"


def extra_arti_health_aware_avoid_bad_health_profile_name() -> str:
    return "arti_release_browser_healthaware_avoidbadhealth"


def extra_arti_health_aware_avoid_bad_health_same_iso_profile_name(
    target: int, index: int
) -> str:
    name = f"arti_release_browser_healthaware_avoidbadhealth_sameiso{target}"
    return name if index == 0 else f"{name}_{index + 1}"


def extra_arti_prefer_cold_same_iso_profile_name(target: int, index: int) -> str:
    name = f"arti_release_browser_healthaware_avoidbadhealth_sameiso{target}_prefercold"
    return name if index == 0 else f"{name}_{index + 1}"


def extra_arti_prefer_cold_same_iso_active_cap_profile_name(
    target: int, cap: int, index: int
) -> str:
    name = (
        "arti_release_browser_healthaware_avoidbadhealth_"
        f"sameiso{target}_prefercold_activecap{cap}"
    )
    return name if index == 0 else f"{name}_{index + 1}"


def extra_arti_prefer_cold_same_iso_prewarm_profile_name(
    target: int, index: int
) -> str:
    name = (
        "arti_release_browser_healthaware_avoidbadhealth_"
        f"sameiso{target}_prefercold_prewarmfirst"
    )
    return name if index == 0 else f"{name}_{index + 1}"


def extra_arti_unknown_fallback_prefer_cold_same_iso_profile_name(
    target: int, index: int
) -> str:
    name = (
        "arti_release_browser_healthaware_avoidbadhealth_unknownfallback_"
        f"sameiso{target}_prefercold"
    )
    return name if index == 0 else f"{name}_{index + 1}"


def extra_arti_health_aware_same_iso_prefer_cold_profile_name(
    target: int, index: int
) -> str:
    name = f"arti_release_browser_healthaware_sameiso{target}_prefercold"
    return name if index == 0 else f"{name}_{index + 1}"


def extra_arti_load_aware_spread_profile_name(min_spread: int, index: int) -> str:
    name = f"arti_release_browser_loadaware_spread{min_spread}"
    return name if index == 0 else f"{name}_{index + 1}"


def extra_arti_load_aware_healthy_over_cold_profile_name(
    min_assigned: int, index: int
) -> str:
    name = f"arti_release_browser_loadaware_healthyovercold{min_assigned}"
    return name if index == 0 else f"{name}_{index + 1}"


def extra_arti_guard_only_healthy_over_cold_profile_name(
    min_assigned: int, index: int
) -> str:
    name = f"arti_release_browser_guardonly_healthyovercold{min_assigned}"
    return name if index == 0 else f"{name}_{index + 1}"


def extra_arti_same_isolation_profile_name(target: int, index: int) -> str:
    name = f"arti_release_browser_sameiso{target}"
    return name if index == 0 else f"{name}_{index + 1}"


def extra_arti_load_aware_same_isolation_profile_name(
    target: int, index: int
) -> str:
    name = f"arti_release_browser_loadaware_sameiso{target}"
    return name if index == 0 else f"{name}_{index + 1}"


def extra_arti_same_isolation_prewarm_profile_name(target: int, index: int) -> str:
    name = f"arti_release_browser_sameiso{target}_prewarmfirst"
    return name if index == 0 else f"{name}_{index + 1}"


def extra_arti_same_isolation_min_assigned_profile_name(
    target: int, min_assigned: int, index: int
) -> str:
    name = (
        f"arti_release_browser_sameiso{target}_"
        f"minassigned{min_assigned}_prewarmfirst"
    )
    return name if index == 0 else f"{name}_{index + 1}"


def extra_arti_same_isolation_prefer_topup_on_tie_profile_name(
    target: int, index: int
) -> str:
    name = f"arti_release_browser_sameiso{target}_prewarmtie"
    return name if index == 0 else f"{name}_{index + 1}"


def extra_arti_load_aware_same_isolation_prewarm_profile_name(
    target: int, index: int
) -> str:
    name = f"arti_release_browser_loadaware_sameiso{target}_prewarmfirst"
    return name if index == 0 else f"{name}_{index + 1}"


def extra_arti_health_aware_same_isolation_prewarm_profile_name(
    target: int, index: int
) -> str:
    name = f"arti_release_browser_healthaware_sameiso{target}_prewarmfirst"
    return name if index == 0 else f"{name}_{index + 1}"


def extra_arti_health_min_score_same_iso_pending_wait_profile_name(
    target: int, min_score: int, wait_ms: int, index: int
) -> str:
    name = (
        "arti_release_browser_"
        f"healthaware_min{min_score}bps_sameiso{target}_wait{wait_ms}ms"
    )
    return name if index == 0 else f"{name}_{index + 1}"


def extra_arti_health_aware_same_iso_prefer_cold_prewarm_pending_wait_profile_name(
    target: int, wait_ms: int, index: int
) -> str:
    name = (
        "arti_release_browser_"
        f"healthaware_sameiso{target}_prewarmfirst_prefercold_wait{wait_ms}ms"
    )
    return name if index == 0 else f"{name}_{index + 1}"


def start_byte_tap_for_profile(
    *,
    profile_name: str,
    proxy_port: int,
    port_offset: int,
    event_limit: int,
    socks_reply_bind_port_tag: bool = False,
) -> ByteTapServer:
    listen_port = proxy_port + port_offset
    if port_is_open("127.0.0.1", listen_port):
        raise OSError(f"byte tap port {listen_port} is already in use")
    tap = ByteTapServer(
        profile_name=profile_name,
        listen_port=listen_port,
        upstream_port=proxy_port,
        event_limit=event_limit,
        socks_reply_bind_port_tag=socks_reply_bind_port_tag,
    )
    tap.start()
    return tap


def browser_port_for_spec(spec: ProxySpec, taps: dict[str, ByteTapServer]) -> int:
    tap = taps.get(spec.name)
    return tap.listen_port if tap is not None else spec.port


def run_c_tor(
    *,
    tor_bin: Path,
    port: int,
    output_dir: Path,
    browser_bin: Path,
    targets: list[str],
    runs: int,
    timeout: float,
    window_size: str,
    warm_cache: bool = False,
    compact_output: bool = False,
    post_boot_wait: float = 0.0,
    proxy_log_tail_lines: int = 200,
    byte_tap: bool = False,
    byte_tap_port_offset: int = 100,
    byte_tap_event_limit: int = DEFAULT_BYTE_TAP_EVENT_LIMIT,
    byte_tap_socks_reply_bind_port_tag: bool = False,
    browser_net_log: bool = False,
    browser_serial_http_connections: bool = False,
    browser_max_persistent_connections_per_server: int | None = None,
    browser_block_url_substrings: list[str] | None = None,
    browser_startup_seed_root: Path = DEFAULT_BROWSER_STARTUP_SEED_ROOT,
    no_browser_startup_seed: bool = False,
    source_tweaks: dict[str, object] | None = None,
    conflux_client_ux: str | None = None,
) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    data_dir = output_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    warmup_boot = None
    if warm_cache:
        warmup_proc, warmup_lines = start_c_tor(
            tor_bin=tor_bin,
            port=port,
            data_dir=data_dir,
            torrc=output_dir / "warmup.torrc",
            conflux_client_ux=conflux_client_ux,
        )
        try:
            warmup_boot = wait_for_line(
                warmup_proc,
                warmup_lines,
                timeout=180.0,
                ready_text="Bootstrapped 100%",
                process_name="tor warmup",
            )
        finally:
            stop_process(warmup_proc)
        if not warmup_boot["ok"]:
            return {
                "cache_mode": "warm",
                "warmup_boot": warmup_boot,
                "boot": {"ok": False, "error": "warmup bootstrap failed"},
                "benchmarks": {},
            }

    result: dict[str, object] = {}
    tap: ByteTapServer | None = None
    proc, lines = start_c_tor(
        tor_bin=tor_bin,
        port=port,
        data_dir=data_dir,
        torrc=output_dir / "torrc",
        conflux_client_ux=conflux_client_ux,
    )
    try:
        boot = wait_for_line(
            proc,
            lines,
            timeout=180.0,
            ready_text="Bootstrapped 100%",
            process_name="tor",
        )
        result = {
            "cache_mode": "warm" if warm_cache else "cold",
            "warmup_boot": warmup_boot,
            "boot": boot,
            "torrc": read_torrc_quality(output_dir / "torrc"),
            "post_boot_wait_seconds": post_boot_wait,
            "benchmarks": {},
        }
        if boot["ok"]:
            if byte_tap:
                try:
                    tap = start_byte_tap_for_profile(
                        profile_name=output_dir.name,
                        proxy_port=port,
                        port_offset=byte_tap_port_offset,
                        event_limit=byte_tap_event_limit,
                        socks_reply_bind_port_tag=(
                            byte_tap_socks_reply_bind_port_tag
                        ),
                    )
                except OSError as exc:
                    result["byte_tap"] = {
                        "enabled": True,
                        "ok": False,
                        "error": str(exc),
                    }
                    result["boot"] = {
                        "ok": False,
                        "error": f"byte tap failed: {exc}",
                    }
                    return result
            wait_after_boot(post_boot_wait)
            result["benchmarks"] = run_browser_benchmarks(
                browser_bin=browser_bin,
                port=tap.listen_port if tap is not None else port,
                output_dir=output_dir,
                targets=targets,
                runs=runs,
                timeout=timeout,
                window_size=window_size,
                compact_output=compact_output,
                browser_net_log=browser_net_log,
                browser_serial_http_connections=browser_serial_http_connections,
                browser_max_persistent_connections_per_server=(
                    browser_max_persistent_connections_per_server
                ),
                browser_block_url_substrings=browser_block_url_substrings,
                browser_startup_seed_root=browser_startup_seed_root,
                no_browser_startup_seed=no_browser_startup_seed,
            )
        return result
    finally:
        if tap is not None:
            tap.stop()
            result["byte_tap"] = tap.snapshot()
        stop_process(proc)
        record_proxy_output_tail(result, lines, limit=proxy_log_tail_lines)
        if compact_output:
            result["proxy_artifacts"] = cleanup_named_paths({"data_dir": data_dir})


def start_c_tor(
    *,
    tor_bin: Path,
    port: int,
    data_dir: Path,
    torrc: Path,
    conflux_client_ux: str | None = None,
) -> tuple[subprocess.Popen[str], queue.Queue[str]]:
    torrc_lines = [
        f"SocksPort 127.0.0.1:{port} {' '.join(C_TOR_SOCKS_FLAGS)}",
        f"DataDirectory {data_dir.resolve()}",
        "ClientOnly 1",
        "AvoidDiskWrites 1",
        "SafeLogging 1",
        "Log notice stdout",
        "ConfluxEnabled auto",
    ]
    # ConfluxClientUX is an official C Tor client option. It only changes which
    # supported Conflux user-experience tradeoff (latency vs throughput) the
    # client requests; it does not weaken path rules, relay choice, or any
    # other quality constraint. Default behavior (auto UX) is preserved when
    # conflux_client_ux is None.
    if conflux_client_ux:
        torrc_lines.append(f"ConfluxClientUX {conflux_client_ux}")
    torrc.write_text("\n".join(torrc_lines) + "\n")
    proc = subprocess.Popen(
        [str(tor_bin), "-f", str(torrc)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    lines: queue.Queue[str] = queue.Queue()
    threading.Thread(target=read_lines, args=(proc, lines), daemon=True).start()
    return proc, lines


def read_torrc_quality(torrc: Path) -> dict[str, object]:
    text = torrc.read_text(errors="replace") if torrc.exists() else ""
    socks_lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip().startswith("SocksPort ")
    ]
    return {
        "path": str(torrc),
        "socks_lines": socks_lines,
        "isolate_socks_auth": any("IsolateSOCKSAuth" in line for line in socks_lines),
    }


def run_arti(
    *,
    arti_bin: Path,
    port: int,
    output_dir: Path,
    browser_bin: Path,
    targets: list[str],
    runs: int,
    timeout: float,
    window_size: str,
    warm_cache: bool = False,
    compact_output: bool = False,
    post_boot_wait: float = 0.0,
    arti_log_level: str = "info",
    arti_proxy_buffer_size: str | None = None,
    arti_proxy_app_buffer_len: int | None = None,
    arti_stream_scheduler_burst: int | None = None,
    arti_exit_select_parallelism: int | None = None,
    arti_exit_launch_parallelism: int | None = None,
    arti_min_exit_circs_for_port: int | None = None,
    arti_preemptive_443_circs: int | None = None,
    arti_preemptive_443_burst_min_requests: int | None = None,
    arti_preemptive_443_busy_active_age_ms: int | None = None,
    arti_socks_connect_soft_timeout_ms: int | None = None,
    arti_socks_connect_soft_timeout_attempts: int | None = None,
    arti_socks_connect_hedge_ms: int | None = None,
    arti_socks_relay_byte_timing: bool = False,
    arti_socks_partial_relay_idle_timeout_ms: int | None = None,
    arti_socks_no_tor_byte_relay_timeout_ms: int | None = None,
    arti_dirclient_read_timeout_ms: int | None = None,
    arti_exit_pending_hedge_ms: int | None = None,
    arti_exit_select_load_aware: bool = False,
    arti_exit_select_health_aware: bool = False,
    arti_exit_select_health_aware_min_assigned: int | None = None,
    arti_exit_select_health_min_move_score_bps: int | None = None,
    arti_exit_select_avoid_bad_health: bool = False,
    arti_exit_select_avoid_bad_health_unknown_fallback: bool = False,
    arti_exit_select_bad_health_hedge_ms: int | None = None,
    arti_exit_select_bad_health_stream_idle_ms: int | None = None,
    arti_exit_select_bad_health_active_no_data_ms: int | None = None,
    arti_exit_select_max_active_streams: int | None = None,
    arti_exit_select_max_assigned_streams: int | None = None,
    arti_exit_select_min_assignment_spread: int | None = None,
    arti_exit_select_healthy_over_cold_min_assigned: int | None = None,
    arti_exit_select_healthy_over_cold_guard_only_min_assigned: int | None = None,
    arti_exit_same_isolation_target: int | None = None,
    arti_exit_same_isolation_require_bad_health: bool = False,
    arti_exit_same_isolation_min_assigned_streams: int | None = None,
    arti_exit_same_isolation_pending_wait_ms: int | None = None,
    arti_exit_same_isolation_prewarm_first_stream: bool = False,
    arti_exit_select_prefer_cold_same_isolation: bool = False,
    proxy_log_tail_lines: int = 200,
    byte_tap: bool = False,
    byte_tap_port_offset: int = 100,
    byte_tap_event_limit: int = DEFAULT_BYTE_TAP_EVENT_LIMIT,
    byte_tap_socks_reply_bind_port_tag: bool = False,
    browser_net_log: bool = False,
    browser_serial_http_connections: bool = False,
    browser_max_persistent_connections_per_server: int | None = None,
    browser_block_url_substrings: list[str] | None = None,
    browser_startup_seed_root: Path = DEFAULT_BROWSER_STARTUP_SEED_ROOT,
    no_browser_startup_seed: bool = False,
    source_tweaks: dict[str, object] | None = None,
) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = (output_dir / "cache").resolve()
    state_dir = (output_dir / "state").resolve()
    cache_dir.mkdir(parents=True, exist_ok=True)
    state_dir.mkdir(parents=True, exist_ok=True)
    selector_effective_metadata = effective_arti_exit_selector_metadata(
        requested_load_aware=(
            arti_exit_select_load_aware
            or arti_exit_select_health_aware_min_assigned is not None
            or arti_exit_select_healthy_over_cold_min_assigned is not None
        ),
        requested_health_aware=arti_exit_select_health_aware,
        requested_avoid_bad_health=arti_exit_select_avoid_bad_health,
        requested_avoid_bad_health_unknown_fallback=(
            arti_exit_select_avoid_bad_health_unknown_fallback
        ),
        requested_same_isolation_target=arti_exit_same_isolation_target,
        requested_prefer_cold_same_isolation=(
            arti_exit_select_prefer_cold_same_isolation
        ),
        requested_max_active_streams=arti_exit_select_max_active_streams,
        source_tweaks=source_tweaks,
    )
    warmup_boot = None
    if warm_cache:
        warmup_proc, warmup_lines = start_arti(
            arti_bin=arti_bin,
            port=port,
            cache_dir=cache_dir,
            state_dir=state_dir,
            log_level=arti_log_level,
            proxy_buffer_size=arti_proxy_buffer_size,
            proxy_app_buffer_len=arti_proxy_app_buffer_len,
            stream_scheduler_burst=arti_stream_scheduler_burst,
            exit_select_parallelism=arti_exit_select_parallelism,
            exit_launch_parallelism=arti_exit_launch_parallelism,
            min_exit_circs_for_port=arti_min_exit_circs_for_port,
            preemptive_443_circs=arti_preemptive_443_circs,
            preemptive_443_burst_min_requests=(
                arti_preemptive_443_burst_min_requests
            ),
            preemptive_443_busy_active_age_ms=(
                arti_preemptive_443_busy_active_age_ms
            ),
            socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
            socks_connect_soft_timeout_attempts=(
                arti_socks_connect_soft_timeout_attempts
            ),
            socks_connect_hedge_ms=arti_socks_connect_hedge_ms,
            socks_relay_byte_timing=arti_socks_relay_byte_timing,
            socks_partial_relay_idle_timeout_ms=(
                arti_socks_partial_relay_idle_timeout_ms
            ),
            socks_no_tor_byte_relay_timeout_ms=(
                arti_socks_no_tor_byte_relay_timeout_ms
            ),
            dirclient_read_timeout_ms=arti_dirclient_read_timeout_ms,
            exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
            exit_select_load_aware=arti_exit_select_load_aware,
            exit_select_health_aware=arti_exit_select_health_aware,
            exit_select_health_aware_min_assigned=(
                arti_exit_select_health_aware_min_assigned
            ),
            exit_select_health_min_move_score_bps=(
                arti_exit_select_health_min_move_score_bps
            ),
            exit_select_avoid_bad_health=arti_exit_select_avoid_bad_health,
            exit_select_avoid_bad_health_unknown_fallback=(
                arti_exit_select_avoid_bad_health_unknown_fallback
            ),
            exit_select_bad_health_hedge_ms=(
                arti_exit_select_bad_health_hedge_ms
            ),
            exit_select_bad_health_stream_idle_ms=(
                arti_exit_select_bad_health_stream_idle_ms
            ),
            exit_select_bad_health_active_no_data_ms=(
                arti_exit_select_bad_health_active_no_data_ms
            ),
            exit_select_max_active_streams=arti_exit_select_max_active_streams,
            exit_select_max_assigned_streams=(
                arti_exit_select_max_assigned_streams
            ),
            exit_select_min_assignment_spread=arti_exit_select_min_assignment_spread,
            exit_select_healthy_over_cold_min_assigned=(
                arti_exit_select_healthy_over_cold_min_assigned
            ),
            exit_select_healthy_over_cold_guard_only_min_assigned=(
                arti_exit_select_healthy_over_cold_guard_only_min_assigned
            ),
            exit_same_isolation_target=arti_exit_same_isolation_target,
            exit_same_isolation_require_bad_health=(
                arti_exit_same_isolation_require_bad_health
            ),
            exit_same_isolation_min_assigned_streams=(
                arti_exit_same_isolation_min_assigned_streams
            ),
            exit_same_isolation_pending_wait_ms=(
                arti_exit_same_isolation_pending_wait_ms
            ),
            exit_same_isolation_prewarm_first_stream=(
                arti_exit_same_isolation_prewarm_first_stream
            ),
            exit_select_prefer_cold_same_isolation=(
                arti_exit_select_prefer_cold_same_isolation
            ),
        )
        try:
            warmup_boot = wait_for_line(
                warmup_proc,
                warmup_lines,
                timeout=180.0,
                ready_text="proxy now functional",
                process_name="arti warmup",
            )
        finally:
            stop_process(warmup_proc)
        if not warmup_boot["ok"]:
            result = {
                "cache_mode": "warm",
                "warmup_boot": warmup_boot,
                "arti_log_level": effective_arti_log_level(
                    arti_log_level, arti_socks_relay_byte_timing
                ),
                "arti_proxy_buffer_size": arti_proxy_buffer_size,
                "arti_proxy_app_buffer_len": arti_proxy_app_buffer_len,
                "arti_stream_scheduler_burst": arti_stream_scheduler_burst,
                "arti_exit_select_parallelism_override": arti_exit_select_parallelism,
                "arti_exit_launch_parallelism_override": arti_exit_launch_parallelism,
                "arti_min_exit_circs_for_port_override": (
                    arti_min_exit_circs_for_port
                ),
                "arti_preemptive_443_circs": arti_preemptive_443_circs,
                "arti_socks_connect_soft_timeout_ms": (
                    arti_socks_connect_soft_timeout_ms
                ),
                "arti_socks_connect_soft_timeout_attempts": (
                    arti_socks_connect_soft_timeout_attempts
                ),
                "arti_socks_connect_hedge_ms": arti_socks_connect_hedge_ms,
                "arti_socks_relay_byte_timing": arti_socks_relay_byte_timing,
                "arti_socks_partial_relay_idle_timeout_ms": (
                    arti_socks_partial_relay_idle_timeout_ms
                ),
                "arti_socks_no_tor_byte_relay_timeout_ms": (
                    arti_socks_no_tor_byte_relay_timeout_ms
                ),
                "arti_dirclient_read_timeout_ms": arti_dirclient_read_timeout_ms,
                "arti_exit_pending_hedge_ms": arti_exit_pending_hedge_ms,
                "arti_exit_select_load_aware": (
                    arti_exit_select_load_aware
                    or arti_exit_select_health_aware_min_assigned is not None
                    or arti_exit_select_healthy_over_cold_min_assigned is not None
                ),
                "arti_exit_select_health_aware": arti_exit_select_health_aware,
                "arti_exit_select_health_aware_min_assigned": (
                    arti_exit_select_health_aware_min_assigned
                ),
                "arti_exit_select_health_min_move_score_bps": (
                    arti_exit_select_health_min_move_score_bps
                ),
                "arti_exit_select_avoid_bad_health": (
                    arti_exit_select_avoid_bad_health
                ),
                "arti_exit_select_avoid_bad_health_unknown_fallback": (
                    arti_exit_select_avoid_bad_health_unknown_fallback
                ),
                "arti_exit_select_bad_health_hedge_ms": (
                    arti_exit_select_bad_health_hedge_ms
                ),
                "arti_exit_select_bad_health_stream_idle_ms": (
                    arti_exit_select_bad_health_stream_idle_ms
                ),
                "arti_exit_select_bad_health_active_no_data_ms": (
                    arti_exit_select_bad_health_active_no_data_ms
                ),
                "arti_exit_select_max_active_streams": (
                    arti_exit_select_max_active_streams
                ),
                "arti_exit_select_max_assigned_streams": (
                    arti_exit_select_max_assigned_streams
                ),
                "arti_exit_select_min_assignment_spread": (
                    arti_exit_select_min_assignment_spread
                ),
                "arti_exit_select_healthy_over_cold_min_assigned": (
                    arti_exit_select_healthy_over_cold_min_assigned
                ),
                "arti_exit_select_healthy_over_cold_guard_only_min_assigned": (
                    arti_exit_select_healthy_over_cold_guard_only_min_assigned
                ),
                "arti_exit_same_isolation_target": arti_exit_same_isolation_target,
                "arti_exit_same_isolation_require_bad_health": (
                    arti_exit_same_isolation_require_bad_health
                ),
                "arti_exit_same_isolation_min_assigned_streams": (
                    arti_exit_same_isolation_min_assigned_streams
                ),
                "arti_exit_same_isolation_pending_wait_ms": (
                    arti_exit_same_isolation_pending_wait_ms
                ),
                "arti_exit_same_isolation_prewarm_first_stream": (
                    arti_exit_same_isolation_prewarm_first_stream
                ),
                "arti_exit_select_prefer_cold_same_isolation": (
                    arti_exit_select_prefer_cold_same_isolation
                ),
                "arti_preemptive_443_burst_min_requests": (
                    arti_preemptive_443_burst_min_requests
                ),
                "arti_preemptive_443_busy_active_age_ms": (
                    arti_preemptive_443_busy_active_age_ms
                ),
                "boot": {"ok": False, "error": "warmup bootstrap failed"},
                "benchmarks": {},
            }
            result.update(selector_effective_metadata)
            return result

    result: dict[str, object] = {}
    tap: ByteTapServer | None = None
    proc, lines = start_arti(
        arti_bin=arti_bin,
        port=port,
        cache_dir=cache_dir,
        state_dir=state_dir,
        log_level=arti_log_level,
        proxy_buffer_size=arti_proxy_buffer_size,
        proxy_app_buffer_len=arti_proxy_app_buffer_len,
        stream_scheduler_burst=arti_stream_scheduler_burst,
        exit_select_parallelism=arti_exit_select_parallelism,
        exit_launch_parallelism=arti_exit_launch_parallelism,
        min_exit_circs_for_port=arti_min_exit_circs_for_port,
        preemptive_443_circs=arti_preemptive_443_circs,
        preemptive_443_burst_min_requests=arti_preemptive_443_burst_min_requests,
        preemptive_443_busy_active_age_ms=arti_preemptive_443_busy_active_age_ms,
        socks_connect_soft_timeout_ms=arti_socks_connect_soft_timeout_ms,
        socks_connect_soft_timeout_attempts=(
            arti_socks_connect_soft_timeout_attempts
        ),
        socks_connect_hedge_ms=arti_socks_connect_hedge_ms,
        socks_relay_byte_timing=arti_socks_relay_byte_timing,
        socks_partial_relay_idle_timeout_ms=arti_socks_partial_relay_idle_timeout_ms,
        socks_no_tor_byte_relay_timeout_ms=arti_socks_no_tor_byte_relay_timeout_ms,
        dirclient_read_timeout_ms=arti_dirclient_read_timeout_ms,
        exit_pending_hedge_ms=arti_exit_pending_hedge_ms,
        exit_select_load_aware=arti_exit_select_load_aware,
        exit_select_health_aware=arti_exit_select_health_aware,
        exit_select_health_aware_min_assigned=(
            arti_exit_select_health_aware_min_assigned
        ),
        exit_select_health_min_move_score_bps=(
            arti_exit_select_health_min_move_score_bps
        ),
        exit_select_avoid_bad_health=arti_exit_select_avoid_bad_health,
        exit_select_avoid_bad_health_unknown_fallback=(
            arti_exit_select_avoid_bad_health_unknown_fallback
        ),
        exit_select_bad_health_hedge_ms=arti_exit_select_bad_health_hedge_ms,
        exit_select_bad_health_stream_idle_ms=(
            arti_exit_select_bad_health_stream_idle_ms
        ),
        exit_select_bad_health_active_no_data_ms=(
            arti_exit_select_bad_health_active_no_data_ms
        ),
        exit_select_max_active_streams=arti_exit_select_max_active_streams,
        exit_select_max_assigned_streams=arti_exit_select_max_assigned_streams,
        exit_select_min_assignment_spread=arti_exit_select_min_assignment_spread,
        exit_select_healthy_over_cold_min_assigned=(
            arti_exit_select_healthy_over_cold_min_assigned
        ),
        exit_select_healthy_over_cold_guard_only_min_assigned=(
            arti_exit_select_healthy_over_cold_guard_only_min_assigned
        ),
        exit_same_isolation_target=arti_exit_same_isolation_target,
        exit_same_isolation_require_bad_health=(
            arti_exit_same_isolation_require_bad_health
        ),
        exit_same_isolation_min_assigned_streams=(
            arti_exit_same_isolation_min_assigned_streams
        ),
        exit_same_isolation_pending_wait_ms=(
            arti_exit_same_isolation_pending_wait_ms
        ),
        exit_same_isolation_prewarm_first_stream=(
            arti_exit_same_isolation_prewarm_first_stream
        ),
        exit_select_prefer_cold_same_isolation=(
            arti_exit_select_prefer_cold_same_isolation
        ),
    )
    try:
        boot = wait_for_line(
            proc,
            lines,
            timeout=180.0,
            ready_text="proxy now functional",
            process_name="arti",
        )
        result = {
            "cache_mode": "warm" if warm_cache else "cold",
            "warmup_boot": warmup_boot,
            "boot": boot,
            "post_boot_wait_seconds": post_boot_wait,
            "arti_log_level": effective_arti_log_level(
                arti_log_level, arti_socks_relay_byte_timing
            ),
            "arti_proxy_buffer_size": arti_proxy_buffer_size,
            "arti_proxy_app_buffer_len": arti_proxy_app_buffer_len,
            "arti_stream_scheduler_burst": arti_stream_scheduler_burst,
            "arti_exit_select_parallelism_override": arti_exit_select_parallelism,
            "arti_exit_launch_parallelism_override": arti_exit_launch_parallelism,
            "arti_min_exit_circs_for_port_override": arti_min_exit_circs_for_port,
            "arti_preemptive_443_circs": arti_preemptive_443_circs,
            "arti_socks_connect_soft_timeout_ms": arti_socks_connect_soft_timeout_ms,
            "arti_socks_connect_soft_timeout_attempts": (
                arti_socks_connect_soft_timeout_attempts
            ),
            "arti_socks_connect_hedge_ms": arti_socks_connect_hedge_ms,
            "arti_socks_relay_byte_timing": arti_socks_relay_byte_timing,
            "arti_socks_partial_relay_idle_timeout_ms": (
                arti_socks_partial_relay_idle_timeout_ms
            ),
            "arti_socks_no_tor_byte_relay_timeout_ms": (
                arti_socks_no_tor_byte_relay_timeout_ms
            ),
            "arti_dirclient_read_timeout_ms": arti_dirclient_read_timeout_ms,
            "arti_exit_pending_hedge_ms": arti_exit_pending_hedge_ms,
            "arti_exit_select_load_aware": (
                arti_exit_select_load_aware
                or arti_exit_select_health_aware_min_assigned is not None
                or arti_exit_select_healthy_over_cold_min_assigned is not None
            ),
            "arti_exit_select_health_aware": arti_exit_select_health_aware,
            "arti_exit_select_health_aware_min_assigned": (
                arti_exit_select_health_aware_min_assigned
            ),
            "arti_exit_select_health_min_move_score_bps": (
                arti_exit_select_health_min_move_score_bps
            ),
            "arti_exit_select_avoid_bad_health": arti_exit_select_avoid_bad_health,
            "arti_exit_select_avoid_bad_health_unknown_fallback": (
                arti_exit_select_avoid_bad_health_unknown_fallback
            ),
            "arti_exit_select_bad_health_hedge_ms": (
                arti_exit_select_bad_health_hedge_ms
            ),
            "arti_exit_select_bad_health_stream_idle_ms": (
                arti_exit_select_bad_health_stream_idle_ms
            ),
            "arti_exit_select_bad_health_active_no_data_ms": (
                arti_exit_select_bad_health_active_no_data_ms
            ),
            "arti_exit_select_max_active_streams": (
                arti_exit_select_max_active_streams
            ),
            "arti_exit_select_max_assigned_streams": (
                arti_exit_select_max_assigned_streams
            ),
            "arti_exit_select_min_assignment_spread": (
                arti_exit_select_min_assignment_spread
            ),
            "arti_exit_select_healthy_over_cold_min_assigned": (
                arti_exit_select_healthy_over_cold_min_assigned
            ),
            "arti_exit_select_healthy_over_cold_guard_only_min_assigned": (
                arti_exit_select_healthy_over_cold_guard_only_min_assigned
            ),
            "arti_exit_same_isolation_target": arti_exit_same_isolation_target,
            "arti_exit_same_isolation_require_bad_health": (
                arti_exit_same_isolation_require_bad_health
            ),
            "arti_exit_same_isolation_min_assigned_streams": (
                arti_exit_same_isolation_min_assigned_streams
            ),
            "arti_exit_same_isolation_pending_wait_ms": (
                arti_exit_same_isolation_pending_wait_ms
            ),
            "arti_exit_same_isolation_prewarm_first_stream": (
                arti_exit_same_isolation_prewarm_first_stream
            ),
            "arti_exit_select_prefer_cold_same_isolation": (
                arti_exit_select_prefer_cold_same_isolation
            ),
            "arti_preemptive_443_burst_min_requests": (
                arti_preemptive_443_burst_min_requests
            ),
            "arti_preemptive_443_busy_active_age_ms": (
                arti_preemptive_443_busy_active_age_ms
            ),
            "benchmarks": {},
        }
        result.update(selector_effective_metadata)
        if boot["ok"]:
            if byte_tap:
                try:
                    tap = start_byte_tap_for_profile(
                        profile_name=output_dir.name,
                        proxy_port=port,
                        port_offset=byte_tap_port_offset,
                        event_limit=byte_tap_event_limit,
                        socks_reply_bind_port_tag=(
                            byte_tap_socks_reply_bind_port_tag
                        ),
                    )
                except OSError as exc:
                    result["byte_tap"] = {
                        "enabled": True,
                        "ok": False,
                        "error": str(exc),
                    }
                    result["boot"] = {
                        "ok": False,
                        "error": f"byte tap failed: {exc}",
                    }
                    return result
            wait_after_boot(post_boot_wait)
            result["benchmarks"] = run_browser_benchmarks(
                browser_bin=browser_bin,
                port=tap.listen_port if tap is not None else port,
                output_dir=output_dir,
                targets=targets,
                runs=runs,
                timeout=timeout,
                window_size=window_size,
                compact_output=compact_output,
                browser_net_log=browser_net_log,
                browser_serial_http_connections=browser_serial_http_connections,
                browser_max_persistent_connections_per_server=(
                    browser_max_persistent_connections_per_server
                ),
                browser_block_url_substrings=browser_block_url_substrings,
                browser_startup_seed_root=browser_startup_seed_root,
                no_browser_startup_seed=no_browser_startup_seed,
            )
        return result
    finally:
        if tap is not None:
            tap.stop()
            result["byte_tap"] = tap.snapshot()
        stop_process(proc)
        record_proxy_output_tail(result, lines, limit=proxy_log_tail_lines)
        if compact_output:
            result["proxy_artifacts"] = cleanup_named_paths(
                {"cache_dir": cache_dir, "state_dir": state_dir}
            )


def start_arti(
    *,
    arti_bin: Path,
    port: int,
    cache_dir: Path,
    state_dir: Path,
    log_level: str = "info",
    proxy_buffer_size: str | None = None,
    proxy_app_buffer_len: int | None = None,
    stream_scheduler_burst: int | None = None,
    exit_select_parallelism: int | None = None,
    exit_launch_parallelism: int | None = None,
    hspool_launch_parallelism: int | None = None,
    hspool_background_start_delay_ms: int | None = None,
    hspool_guarded_stem_target: int | None = None,
    hspool_guarded_stem_target_defer_post_boot: bool = False,
    hspool_on_demand_grace_ms: int | None = None,
    hspool_on_demand_race_ms: int | None = None,
    min_exit_circs_for_port: int | None = None,
    preemptive_443_circs: int | None = None,
    preemptive_443_burst_min_requests: int | None = None,
    preemptive_443_busy_active_age_ms: int | None = None,
    socks_connect_soft_timeout_ms: int | None = None,
    socks_connect_soft_timeout_attempts: int | None = None,
    socks_connect_hedge_ms: int | None = None,
    socks_relay_byte_timing: bool = False,
    socks_tor_to_client_coalesce_bytes: int | None = None,
    stream_ready_data_coalesce_bytes: int | None = None,
    socks_partial_relay_idle_timeout_ms: int | None = None,
    socks_no_tor_byte_relay_timeout_ms: int | None = None,
    exit_pending_hedge_ms: int | None = None,
    exit_select_load_aware: bool = False,
    exit_select_health_aware: bool = False,
    exit_select_health_aware_min_assigned: int | None = None,
    exit_select_health_min_move_score_bps: int | None = None,
    exit_select_avoid_bad_health: bool = False,
    exit_select_avoid_bad_health_unknown_fallback: bool = False,
    exit_select_bad_health_hedge_ms: int | None = None,
    exit_select_bad_health_stream_idle_ms: int | None = None,
    exit_select_bad_health_active_no_data_ms: int | None = None,
    exit_select_max_active_streams: int | None = None,
    exit_select_max_assigned_streams: int | None = None,
    exit_select_min_assignment_spread: int | None = None,
    exit_select_healthy_over_cold_min_assigned: int | None = None,
    exit_select_healthy_over_cold_guard_only_min_assigned: int | None = None,
    exit_same_isolation_target: int | None = None,
    exit_same_isolation_other_isolation_min: int | None = None,
    exit_same_isolation_require_bad_health: bool = False,
    exit_same_isolation_min_assigned_streams: int | None = None,
    exit_same_isolation_pending_wait_ms: int | None = None,
    exit_same_isolation_prewarm_first_stream: bool = False,
    exit_same_isolation_prefer_topup_on_tie: bool = False,
    exit_select_prefer_cold_same_isolation: bool = False,
    hs_intro_rend_overlap: bool = False,
    hs_rend_prebuild_before_desc: bool = False,
    hs_desc_shared_cache: bool = False,
    hs_intro_circuit_hedge_ms: int | None = None,
    dir_select_spread: bool = False,
    dir_incremental_microdescs: bool = False,
    dir_microdesc_early_usable_notify: bool = False,
    dir_microdesc_early_retry_on_partial: bool = False,
    dir_microdesc_partial_retry_chunking: bool = False,
    dir_microdesc_disable_bad_health_replacement: bool = False,
    dir_microdesc_bad_health_replacement_suppress_gap_ms: int | None = None,
    dir_microdesc_bad_health_replacement_suppress_min_assigned_streams: (
        int | None
    ) = None,
    dir_microdesc_bad_health_replacement_suppress_min_active_streams: (
        int | None
    ) = None,
    dir_microdesc_source_spread: bool = False,
    dir_microdesc_pending_spread: bool = False,
    dir_microdesc_ids_per_request: int | None = None,
    dir_microdesc_retry_ids_per_request: int | None = None,
    dir_microdesc_retry_delay_max_ms: int | None = None,
    dir_microdesc_parallelism: int | None = None,
    dir_microdesc_hedge_ms: int | None = None,
    dirclient_read_timeout_ms: int | None = None,
    dirclient_progress_read_timeout_ms: int | None = None,
    dirclient_microdesc_body_max_ms: int | None = None,
    dirclient_microdesc_min_rate_bps: int | None = None,
    dirclient_timing_log: bool = False,
) -> tuple[subprocess.Popen[str], queue.Queue[str]]:
    log_level = effective_arti_log_level(
        log_level=log_level,
        socks_relay_byte_timing=socks_relay_byte_timing,
        hspool_launch_parallelism=hspool_launch_parallelism,
        hspool_background_start_delay_ms=hspool_background_start_delay_ms,
        hspool_guarded_stem_target=hspool_guarded_stem_target,
        hspool_on_demand_grace_ms=hspool_on_demand_grace_ms,
        hspool_on_demand_race_ms=hspool_on_demand_race_ms,
        hs_intro_rend_overlap=hs_intro_rend_overlap,
        hs_rend_prebuild_before_desc=hs_rend_prebuild_before_desc,
        hs_desc_shared_cache=hs_desc_shared_cache,
        hs_intro_circuit_hedge_ms=hs_intro_circuit_hedge_ms,
    )
    command = [
        str(arti_bin),
        "proxy",
        "--disable-fs-permission-checks",
        "-l",
        log_level,
        "-p",
        str(port),
        "-o",
        f'storage.cache_dir="{cache_dir}"',
        "-o",
        f'storage.state_dir="{state_dir}"',
        "-o",
        f'storage.port_info_file="{state_dir / "port_info.json"}"',
    ]
    if dir_microdesc_parallelism is not None:
        command.extend(
            [
                "-o",
                f"download_schedule.retry_microdescs.parallelism={dir_microdesc_parallelism}",
            ]
        )
    if proxy_buffer_size:
        command.extend(
            [
                "-o",
                f'proxy.socket_send_buf_size="{proxy_buffer_size}"',
                "-o",
                f'proxy.socket_recv_buf_size="{proxy_buffer_size}"',
            ]
        )
    if min_exit_circs_for_port is not None:
        command.extend(
            [
                "-o",
                f"preemptive_circuits.min_exit_circs_for_port={min_exit_circs_for_port}",
            ]
        )
    env = os.environ.copy()
    if proxy_app_buffer_len is not None:
        env["TORFAST_APP_STREAM_BUF_LEN"] = str(proxy_app_buffer_len)
    if preemptive_443_circs is not None:
        env["TORFAST_PREEMPTIVE_443_CIRCS"] = str(preemptive_443_circs)
    if preemptive_443_burst_min_requests is not None:
        env["TORFAST_PREEMPTIVE_443_BURST_MIN_REQUESTS"] = str(
            preemptive_443_burst_min_requests
        )
    if preemptive_443_busy_active_age_ms is not None:
        env["TORFAST_PREEMPTIVE_443_BUSY_ACTIVE_AGE_MS"] = str(
            preemptive_443_busy_active_age_ms
        )
    if exit_select_parallelism is not None:
        env["TORFAST_EXIT_SELECT_PARALLELISM"] = str(exit_select_parallelism)
    if exit_launch_parallelism is not None:
        env["TORFAST_EXIT_LAUNCH_PARALLELISM"] = str(exit_launch_parallelism)
    if hspool_launch_parallelism is not None:
        env["TORFAST_HSPOOL_LAUNCH_PARALLELISM"] = str(hspool_launch_parallelism)
    if hspool_background_start_delay_ms is not None:
        env["TORFAST_HSPOOL_BACKGROUND_START_DELAY_MS"] = str(
            hspool_background_start_delay_ms
        )
    if hspool_guarded_stem_target is not None:
        env["TORFAST_HSPOOL_GUARDED_STEM_TARGET"] = str(hspool_guarded_stem_target)
    if hspool_guarded_stem_target_defer_post_boot:
        env["TORFAST_HSPOOL_GUARDED_STEM_TARGET_DEFER_POST_BOOT"] = "1"
    if hspool_on_demand_grace_ms is not None:
        env["TORFAST_HSPOOL_ON_DEMAND_POOL_GRACE_MS"] = str(
            hspool_on_demand_grace_ms
        )
    if hspool_on_demand_race_ms is not None:
        env["TORFAST_HSPOOL_ON_DEMAND_POOL_RACE_MS"] = str(
            hspool_on_demand_race_ms
        )
    if hs_intro_rend_overlap:
        env["TORFAST_HS_INTRO_REND_OVERLAP"] = "1"
    if hs_rend_prebuild_before_desc:
        env["TORFAST_HS_REND_PREBUILD_BEFORE_DESC"] = "1"
    if hs_desc_shared_cache:
        env["TORFAST_HS_DESC_SHARED_CACHE"] = "1"
    if hs_intro_circuit_hedge_ms is not None:
        env["TORFAST_HS_INTRO_CIRCUIT_HEDGE_MS"] = str(hs_intro_circuit_hedge_ms)
    if socks_connect_soft_timeout_ms is not None:
        env["TORFAST_SOCKS_CONNECT_SOFT_TIMEOUT_MS"] = str(
            socks_connect_soft_timeout_ms
        )
    if socks_connect_soft_timeout_attempts is not None:
        env["TORFAST_SOCKS_CONNECT_SOFT_TIMEOUT_ATTEMPTS"] = str(
            socks_connect_soft_timeout_attempts
        )
    if socks_connect_hedge_ms is not None:
        env["TORFAST_SOCKS_CONNECT_HEDGE_MS"] = str(socks_connect_hedge_ms)
    if socks_relay_byte_timing:
        env["TORFAST_SOCKS_RELAY_BYTE_TIMING"] = "1"
        env["TORFAST_EXIT_SELECT_LOW_LOG_CONTEXT"] = "1"
        env["TORFAST_CIRCUIT_CONGESTION_LOG"] = "1"
        env["TORFAST_STREAM_SCHEDULER_LOG"] = "1"
        env["TORFAST_STREAM_LIFECYCLE_LOG"] = "1"
    if socks_tor_to_client_coalesce_bytes is not None:
        env["TORFAST_SOCKS_TOR_TO_CLIENT_COALESCE_BYTES"] = str(
            socks_tor_to_client_coalesce_bytes
        )
    if stream_ready_data_coalesce_bytes is not None:
        env["TORFAST_STREAM_READY_DATA_COALESCE_BYTES"] = str(
            stream_ready_data_coalesce_bytes
        )
    if stream_scheduler_burst is not None:
        env["TORFAST_STREAM_SCHEDULER_BURST"] = str(stream_scheduler_burst)
    if socks_partial_relay_idle_timeout_ms is not None:
        env["TORFAST_SOCKS_PARTIAL_RELAY_IDLE_TIMEOUT_MS"] = str(
            socks_partial_relay_idle_timeout_ms
        )
    if socks_no_tor_byte_relay_timeout_ms is not None:
        env["TORFAST_SOCKS_NO_TOR_BYTE_RELAY_TIMEOUT_MS"] = str(
            socks_no_tor_byte_relay_timeout_ms
        )
    if exit_pending_hedge_ms is not None:
        env["TORFAST_EXIT_PENDING_HEDGE_MS"] = str(exit_pending_hedge_ms)
    if exit_select_load_aware or exit_select_healthy_over_cold_min_assigned is not None:
        env["TORFAST_EXIT_SELECT_LOAD_AWARE"] = "1"
    if exit_select_health_aware:
        env["TORFAST_EXIT_SELECT_LOAD_AWARE"] = "1"
        env["TORFAST_EXIT_SELECT_HEALTH_AWARE"] = "1"
    if exit_select_health_aware_min_assigned is not None:
        env["TORFAST_EXIT_SELECT_LOAD_AWARE"] = "1"
        env["TORFAST_EXIT_SELECT_HEALTH_AWARE"] = "1"
        env["TORFAST_EXIT_SELECT_HEALTH_AWARE_MIN_ASSIGNED"] = str(
            exit_select_health_aware_min_assigned
        )
    if exit_select_health_min_move_score_bps is not None:
        env["TORFAST_EXIT_SELECT_HEALTH_MIN_MOVE_SCORE_BPS"] = str(
            exit_select_health_min_move_score_bps
        )
    if exit_select_avoid_bad_health:
        env["TORFAST_EXIT_SELECT_AVOID_BAD_HEALTH"] = "1"
    if exit_select_avoid_bad_health_unknown_fallback:
        env["TORFAST_EXIT_SELECT_AVOID_BAD_HEALTH_UNKNOWN_FALLBACK"] = "1"
    if exit_select_bad_health_hedge_ms is not None:
        env["TORFAST_EXIT_SELECT_BAD_HEALTH_HEDGE_MS"] = str(
            exit_select_bad_health_hedge_ms
        )
    if exit_select_bad_health_stream_idle_ms is not None:
        env["TORFAST_EXIT_SELECT_BAD_HEALTH_STREAM_IDLE_MS"] = str(
            exit_select_bad_health_stream_idle_ms
        )
    if exit_select_bad_health_active_no_data_ms is not None:
        env["TORFAST_EXIT_SELECT_BAD_HEALTH_ACTIVE_NO_DATA_MS"] = str(
            exit_select_bad_health_active_no_data_ms
        )
    if exit_select_max_active_streams is not None:
        env["TORFAST_EXIT_SELECT_MAX_ACTIVE_STREAMS"] = str(
            exit_select_max_active_streams
        )
    if exit_select_max_assigned_streams is not None:
        env["TORFAST_EXIT_SELECT_MAX_ASSIGNED_STREAMS"] = str(
            exit_select_max_assigned_streams
        )
    if exit_select_min_assignment_spread is not None:
        env["TORFAST_EXIT_SELECT_MIN_ASSIGNMENT_SPREAD"] = str(
            exit_select_min_assignment_spread
        )
    if exit_select_healthy_over_cold_min_assigned is not None:
        env["TORFAST_EXIT_SELECT_HEALTHY_OVER_COLD_MIN_ASSIGNED"] = str(
            exit_select_healthy_over_cold_min_assigned
        )
    if exit_select_healthy_over_cold_guard_only_min_assigned is not None:
        env["TORFAST_EXIT_SELECT_HEALTHY_OVER_COLD_GUARD_ONLY_MIN_ASSIGNED"] = str(
            exit_select_healthy_over_cold_guard_only_min_assigned
        )
    if exit_same_isolation_target is not None:
        env["TORFAST_EXIT_SAME_ISOLATION_TARGET"] = str(exit_same_isolation_target)
    if exit_same_isolation_other_isolation_min is not None:
        env["TORFAST_EXIT_SAME_ISOLATION_OTHER_ISOLATION_MIN"] = str(
            exit_same_isolation_other_isolation_min
        )
    if exit_same_isolation_require_bad_health:
        env["TORFAST_EXIT_SAME_ISOLATION_REQUIRE_BAD_HEALTH"] = "1"
    if exit_same_isolation_min_assigned_streams is not None:
        env["TORFAST_EXIT_SAME_ISOLATION_MIN_ASSIGNED_STREAMS"] = str(
            exit_same_isolation_min_assigned_streams
        )
    if exit_same_isolation_pending_wait_ms is not None:
        env["TORFAST_EXIT_SAME_ISOLATION_PENDING_WAIT_MS"] = str(
            exit_same_isolation_pending_wait_ms
        )
    if exit_same_isolation_prewarm_first_stream:
        env["TORFAST_EXIT_SAME_ISOLATION_PREWARM_FIRST_STREAM"] = "1"
    if exit_same_isolation_prefer_topup_on_tie:
        env["TORFAST_EXIT_SAME_ISOLATION_PREFER_TOPUP_ON_TIE"] = "1"
    if exit_select_prefer_cold_same_isolation:
        env["TORFAST_EXIT_SELECT_PREFER_COLD_SAME_ISOLATION"] = "1"
    if dir_select_spread:
        env["TORFAST_DIR_SELECT_SPREAD"] = "1"
    if dir_incremental_microdescs:
        env["TORFAST_DIR_INCREMENTAL_MICRODESCS"] = "1"
    if dir_microdesc_early_usable_notify:
        env["TORFAST_DIR_MICRODESC_EARLY_USABLE_NOTIFY"] = "1"
    if dir_microdesc_early_retry_on_partial:
        env["TORFAST_DIR_MICRODESC_EARLY_RETRY_ON_PARTIAL"] = "1"
    if dir_microdesc_partial_retry_chunking:
        env["TORFAST_DIR_MICRODESC_PARTIAL_RETRY_CHUNKING"] = "1"
    if dir_microdesc_disable_bad_health_replacement:
        env["TORFAST_DIR_MICRODESC_DISABLE_BAD_HEALTH_REPLACEMENT"] = "1"
    if dir_microdesc_bad_health_replacement_suppress_gap_ms is not None:
        env["TORFAST_DIR_MICRODESC_BAD_HEALTH_REPLACEMENT_SUPPRESS_GAP_MS"] = str(
            dir_microdesc_bad_health_replacement_suppress_gap_ms
        )
    if dir_microdesc_bad_health_replacement_suppress_min_assigned_streams is not None:
        env[
            "TORFAST_DIR_MICRODESC_BAD_HEALTH_REPLACEMENT_SUPPRESS_MIN_ASSIGNED_STREAMS"
        ] = str(
            dir_microdesc_bad_health_replacement_suppress_min_assigned_streams
        )
    if dir_microdesc_bad_health_replacement_suppress_min_active_streams is not None:
        env[
            "TORFAST_DIR_MICRODESC_BAD_HEALTH_REPLACEMENT_SUPPRESS_MIN_ACTIVE_STREAMS"
        ] = str(dir_microdesc_bad_health_replacement_suppress_min_active_streams)
    if dir_microdesc_source_spread:
        env["TORFAST_DIR_MICRODESC_SOURCE_SPREAD"] = "1"
    if dir_microdesc_pending_spread:
        env["TORFAST_DIR_MICRODESC_PENDING_SPREAD"] = "1"
    if dir_microdesc_ids_per_request is not None:
        env["TORFAST_DIR_MICRODESC_IDS_PER_REQUEST"] = str(
            dir_microdesc_ids_per_request
        )
    if dir_microdesc_retry_ids_per_request is not None:
        env["TORFAST_DIR_MICRODESC_RETRY_IDS_PER_REQUEST"] = str(
            dir_microdesc_retry_ids_per_request
        )
    if dir_microdesc_retry_delay_max_ms is not None:
        env["TORFAST_DIR_MICRODESC_RETRY_DELAY_MAX_MS"] = str(
            dir_microdesc_retry_delay_max_ms
        )
    if dir_microdesc_hedge_ms is not None:
        env["TORFAST_DIR_MICRODESC_HEDGE_MS"] = str(dir_microdesc_hedge_ms)
    if dirclient_read_timeout_ms is not None:
        env["TORFAST_DIRCLIENT_READ_TIMEOUT_MS"] = str(dirclient_read_timeout_ms)
    if dirclient_progress_read_timeout_ms is not None:
        env["TORFAST_DIRCLIENT_PROGRESS_READ_TIMEOUT_MS"] = str(
            dirclient_progress_read_timeout_ms
        )
    if dirclient_microdesc_body_max_ms is not None:
        env["TORFAST_DIRCLIENT_MICRODESC_BODY_MAX_MS"] = str(
            dirclient_microdesc_body_max_ms
        )
    if dirclient_microdesc_min_rate_bps is not None:
        env["TORFAST_DIRCLIENT_MICRODESC_MIN_RATE_BPS"] = str(
            dirclient_microdesc_min_rate_bps
        )
    if dirclient_timing_log:
        env["TORFAST_DIRCLIENT_TIMING_LOG"] = "1"
    proc = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=env,
    )
    lines: queue.Queue[str] = queue.Queue()
    threading.Thread(target=read_lines, args=(proc, lines), daemon=True).start()
    return proc, lines


def wait_after_boot(seconds: float) -> None:
    if seconds > 0:
        time.sleep(seconds)


def run_browser_benchmarks(
    *,
    browser_bin: Path,
    port: int,
    output_dir: Path,
    targets: list[str],
    runs: int,
    timeout: float,
    window_size: str,
    compact_output: bool = False,
    browser_net_log: bool = False,
    browser_serial_http_connections: bool = False,
    browser_max_persistent_connections_per_server: int | None = None,
    browser_block_url_substrings: list[str] | None = None,
    browser_startup_seed_root: Path = DEFAULT_BROWSER_STARTUP_SEED_ROOT,
    no_browser_startup_seed: bool = False,
) -> dict[str, object]:
    normalized_browser_block_url_substrings = normalize_browser_block_url_substrings(
        browser_block_url_substrings
    )
    benchmarks: dict[str, object] = {}
    for url in targets:
        url_slug = slug(url)
        results = [
            run_browser_once(
                browser_bin=browser_bin,
                port=port,
                output_dir=output_dir,
                url=url,
                url_slug=url_slug,
                run_index=run_index,
                timeout=timeout,
                window_size=window_size,
                compact_output=compact_output,
                browser_net_log=browser_net_log,
                browser_serial_http_connections=browser_serial_http_connections,
                browser_max_persistent_connections_per_server=(
                    browser_max_persistent_connections_per_server
                ),
                browser_block_url_substrings=normalized_browser_block_url_substrings,
                browser_startup_seed_root=browser_startup_seed_root,
                no_browser_startup_seed=no_browser_startup_seed,
            )
            for run_index in range(1, runs + 1)
        ]
        benchmarks[url] = {
            "runs": results,
            "summary": summarize_browser(results),
        }
    return benchmarks


def run_browser_once(
    *,
    browser_bin: Path,
    port: int,
    output_dir: Path,
    url: str,
    url_slug: str,
    run_index: int,
    timeout: float,
    window_size: str,
    compact_output: bool = False,
    browser_net_log: bool = False,
    browser_serial_http_connections: bool = False,
    browser_max_persistent_connections_per_server: int | None = None,
    browser_block_url_substrings: list[str] | None = None,
    browser_startup_seed_root: Path = DEFAULT_BROWSER_STARTUP_SEED_ROOT,
    no_browser_startup_seed: bool = False,
) -> dict[str, object]:
    profile_dir = output_dir / "profiles" / f"{url_slug}-{run_index}"
    home_dir = output_dir / "homes" / f"{url_slug}-{run_index}"
    screenshot_path = output_dir / "screenshots" / f"{url_slug}-{run_index}.png"
    browser_net_log_path = (
        output_dir / "browser_net_logs" / f"{url_slug}-{run_index}.mozlog"
    )
    profile_dir.mkdir(parents=True, exist_ok=True)
    home_dir.mkdir(parents=True, exist_ok=True)
    screenshot_path.parent.mkdir(parents=True, exist_ok=True)
    if browser_net_log:
        browser_net_log_path.parent.mkdir(parents=True, exist_ok=True)
    if no_browser_startup_seed:
        browser_startup_seed_apply = {
            "ok": True,
            "applied": False,
            "reason": "disabled by flag",
            "seed_root": str(browser_startup_seed_root),
        }
    else:
        browser_startup_seed_apply = apply_browser_startup_seed_to_profile(
            profile_dir,
            browser_startup_seed_root,
        )

    env = os.environ.copy()
    env.update(
        {
            "HOME": str(home_dir.resolve()),
            "MOZ_CRASHREPORTER_DISABLE": "1",
            "MOZ_HEADLESS": "1",
            "TZ": "UTC",
            "TOR_PROVIDER": "none",
            "TOR_SKIP_LAUNCH": "1",
            "TOR_SOCKS_HOST": "127.0.0.1",
            "TOR_SOCKS_PORT": str(port),
        }
    )
    if browser_net_log:
        env.update(browser_net_log_env(browser_net_log_path))

    command = [
        str(browser_bin),
        "--new-instance",
        "--no-remote",
        "--headless",
        "--window-size",
        window_size,
        "-remote-allow-system-access",
        "--profile",
        str(profile_dir.resolve()),
        "--marionette",
        "about:blank",
    ]

    started = time.perf_counter()
    started_epoch_ms = time.time() * 1000
    timed_out = False
    exit_code = None
    error = None
    output_lines: list[str] = []
    capabilities: dict[str, object] = {}
    current_url = None
    title = None
    load_ms = None
    nav_started_epoch_ms = None
    nav_finished_epoch_ms = None
    browser_connection_prefs: dict[str, object] = {}
    browser_lab_prefs: dict[str, object] = {
        "serial_http_connections": {"enabled": browser_serial_http_connections},
        "max_persistent_connections_per_server": {
            "enabled": browser_max_persistent_connections_per_server is not None,
            "requested_value": browser_max_persistent_connections_per_server,
        },
    }
    browser_activity_probe: dict[str, object] = {"enabled": browser_net_log}
    browser_request_blocker: dict[str, object] = {
        "enabled": bool(browser_block_url_substrings),
        "url_substrings": list(browser_block_url_substrings or []),
    }
    browser_quality_prefs: dict[str, object] = {}
    browser_fingerprint_snapshot: dict[str, object] = {}
    performance_timing: dict[str, object] = {}

    if port_is_open("127.0.0.1", MARIONETTE_PORT):
        error = f"marionette port {MARIONETTE_PORT} is already in use"
        timed_out = True
    else:
        proc = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            start_new_session=True,
            env=env,
        )
        lines: queue.Queue[str] = queue.Queue()
        threading.Thread(target=read_lines, args=(proc, lines), daemon=True).start()

        client = None
        try:
            client = MarionetteClient.connect(
                host="127.0.0.1",
                port=MARIONETTE_PORT,
                proc=proc,
                lines=lines,
                timeout=min(30.0, timeout),
            )
            client.sock.settimeout(timeout + 10.0)
            session = client.command(
                "WebDriver:NewSession",
                {"capabilities": {"alwaysMatch": {}}},
            )
            capabilities = session.get("capabilities", {})
            client.command(
                "WebDriver:SetTimeouts",
                {
                    "implicit": 0,
                    "pageLoad": int(timeout * 1000),
                    "script": 30_000,
                },
            )
            browser_lab_prefs = configure_browser_lab_prefs(
                client,
                serial_http_connections=browser_serial_http_connections,
                max_persistent_connections_per_server=(
                    browser_max_persistent_connections_per_server
                ),
            )
            browser_request_blocker = install_browser_request_blocker(
                client, url_substrings=browser_block_url_substrings
            )
            browser_activity_probe = install_browser_activity_probe(
                client, enabled=browser_net_log
            )
            nav_started_epoch_ms = time.time() * 1000
            nav_started = time.perf_counter()
            client.command("WebDriver:Navigate", {"url": url})
            load_ms = (time.perf_counter() - nav_started) * 1000
            nav_finished_epoch_ms = time.time() * 1000

            screenshot = client.command("WebDriver:TakeScreenshot", {})
            raw_png = base64.b64decode(screenshot["value"])
            screenshot_path.write_bytes(raw_png)

            current_url = optional_command(client, "WebDriver:GetCurrentURL")
            title = optional_command(client, "WebDriver:GetTitle")
            performance_timing = collect_performance_timing(client)
            if isinstance(performance_timing, dict):
                performance_timing["page_resource_discovery"] = (
                    collect_page_resource_discovery(client)
                )
            browser_connection_prefs = collect_browser_connection_prefs(client)
            browser_quality_prefs = collect_browser_quality_prefs(client)
            browser_fingerprint_snapshot = collect_browser_fingerprint_snapshot(client)
        except TimeoutError as exc:
            timed_out = True
            error = str(exc)
        except Exception as exc:  # noqa: BLE001 - benchmark result should record it.
            error = f"{type(exc).__name__}: {exc}"
        finally:
            if client:
                browser_request_blocker = collect_browser_request_blocker(
                    client, browser_request_blocker
                )
                browser_activity_probe = collect_browser_activity_probe(
                    client, browser_activity_probe
                )
                client.close()
            stop_process_tree(proc)
            exit_code = proc.returncode
            output_lines = drain_queue(lines)

    elapsed_ms = (time.perf_counter() - started) * 1000
    finished_epoch_ms = time.time() * 1000
    image = png_info(screenshot_path)
    runtime_prefs = read_runtime_prefs(profile_dir)
    effective_proxy = {
        "network.proxy.socks": runtime_prefs.get("network.proxy.socks", "127.0.0.1"),
        "network.proxy.socks_port": runtime_prefs.get("network.proxy.socks_port", 9150),
        "network.proxy.socks_remote_dns": runtime_prefs.get(
            "network.proxy.socks_remote_dns", True
        ),
        "network.proxy.type": runtime_prefs.get("network.proxy.type", 1),
    }
    ok = (
        not timed_out
        and error is None
        and image["exists"]
        and image["bytes"] > 0
        and effective_proxy["network.proxy.socks"] == "127.0.0.1"
        and effective_proxy["network.proxy.socks_port"] == port
        and effective_proxy["network.proxy.socks_remote_dns"] is True
        and effective_proxy["network.proxy.type"] == 1
    )
    artifacts = cleanup_browser_artifacts(
        profile_dir=profile_dir,
        home_dir=home_dir,
        compact_output=compact_output,
        retain=not ok,
    )

    return {
        "url": url,
        "run_index": run_index,
        "ok": ok,
        "expected_socks_port": port,
        "started_epoch_ms": round(started_epoch_ms, 3),
        "finished_epoch_ms": round(finished_epoch_ms, 3),
        "nav_started_epoch_ms": (
            round(nav_started_epoch_ms, 3)
            if nav_started_epoch_ms is not None
            else None
        ),
        "nav_finished_epoch_ms": (
            round(nav_finished_epoch_ms, 3)
            if nav_finished_epoch_ms is not None
            else None
        ),
        "elapsed_ms": round(elapsed_ms, 3),
        "load_ms": round(load_ms, 3) if load_ms is not None else None,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "error": error,
        "current_url": current_url,
        "title": title,
        "capabilities": capabilities,
        "performance_timing": performance_timing,
        "browser_connection_prefs": browser_connection_prefs,
        "browser_lab_prefs": browser_lab_prefs,
        "browser_request_blocker": browser_request_blocker,
        "browser_activity_probe": browser_activity_probe,
        "browser_quality_prefs": browser_quality_prefs,
        "browser_fingerprint_snapshot": browser_fingerprint_snapshot,
        "screenshot": image,
        "profile_dir": str(profile_dir),
        "home_dir": str(home_dir),
        "artifacts": artifacts,
        "runtime_prefs": runtime_prefs,
        "effective_proxy_prefs": effective_proxy,
        "browser_net_log": summarize_browser_net_log(
            browser_net_log_path, enabled=browser_net_log
        ),
        "browser_startup_seed_apply": browser_startup_seed_apply,
        "output_tail": output_lines[-40:],
    }


def cleanup_browser_artifacts(
    *, profile_dir: Path, home_dir: Path, compact_output: bool, retain: bool = False
) -> dict[str, object]:
    artifacts = {
        "compact_output": compact_output,
        "profile_dir_retained": profile_dir.exists(),
        "home_dir_retained": home_dir.exists(),
        "removed": [],
        "errors": [],
    }
    if not compact_output:
        return artifacts
    if retain:
        artifacts["retain_reason"] = "failed_run"
        return artifacts
    for label, path in (("profile_dir", profile_dir), ("home_dir", home_dir)):
        try:
            if path.exists():
                shutil.rmtree(path)
                artifacts["removed"].append(label)
        except OSError as exc:
            artifacts["errors"].append(f"{label}: {exc}")
    artifacts["profile_dir_retained"] = profile_dir.exists()
    artifacts["home_dir_retained"] = home_dir.exists()
    return artifacts


def cleanup_named_paths(paths: dict[str, Path]) -> dict[str, object]:
    artifacts = {
        "removed": [],
        "retained": [],
        "errors": [],
    }
    for label, path in paths.items():
        try:
            if path.exists():
                shutil.rmtree(path)
                artifacts["removed"].append(label)
            else:
                artifacts["retained"].append(label)
        except OSError as exc:
            artifacts["errors"].append(f"{label}: {exc}")
    return artifacts


def record_proxy_output_tail(
    result: dict[str, object], lines: queue.Queue[str], *, limit: int
) -> None:
    drained = drain_queue(lines)
    signal_lines = proxy_signal_lines(drained)
    if signal_lines:
        append_proxy_signal_lines(result, signal_lines)
    relay_context_lines = proxy_relay_context_lines(drained)
    if relay_context_lines:
        append_proxy_relay_context_lines(result, relay_context_lines)
    if limit <= 0:
        return
    tail = drained[-limit:]
    if tail:
        result["proxy_output_tail"] = tail


def record_proxy_run_signals(
    profile: dict[str, object],
    run: dict[str, object],
    lines: queue.Queue[str],
    *,
    tail_limit: int = 200,
    keep_success_tail_limit: int = 0,
) -> None:
    all_drained = drain_queue(lines)
    drained = proxy_lines_in_run_window(all_drained, run)
    pre_run_selection_context = proxy_pre_run_circuit_selection_context_lines(
        all_drained, drained, run
    )
    run_tail_limit = keep_success_tail_limit if run.get("ok") is True else tail_limit
    if run_tail_limit > 0:
        tail = drained[-run_tail_limit:]
        if tail:
            run["proxy_output_tail"] = tail
    signal_lines = proxy_signal_lines(pre_run_selection_context + drained)
    if not signal_lines:
        relay_context_lines = proxy_relay_context_lines(drained)
        if relay_context_lines:
            bounded = relay_context_lines[-PROXY_SIGNAL_LINE_LIMIT:]
            run["proxy_relay_context_lines"] = bounded
            append_proxy_relay_context_lines(profile, relay_context_lines)
        return
    bounded = proxy_signal_lines_with_relay_context(signal_lines)
    run["proxy_signal_lines"] = bounded
    append_proxy_signal_lines(profile, signal_lines)
    relay_context_lines = proxy_relay_context_lines(drained)
    if relay_context_lines:
        bounded = proxy_signal_lines_with_relay_context(relay_context_lines)
        run["proxy_relay_context_lines"] = bounded
        append_proxy_relay_context_lines(profile, relay_context_lines)


def proxy_lines_in_run_window(
    lines: list[str],
    run: dict[str, object],
    *,
    start_grace_ms: float = 250.0,
    end_grace_ms: float = 2_000.0,
) -> list[str]:
    start_ms = numeric_value(run.get("started_epoch_ms"))
    elapsed_ms = numeric_value(run.get("elapsed_ms"))
    nav_finished_ms = numeric_value(run.get("nav_finished_epoch_ms"))
    finished_ms = numeric_value(run.get("finished_epoch_ms"))
    if start_ms is None:
        return lines

    end_candidates: list[float] = []
    if elapsed_ms is not None:
        end_candidates.append(start_ms + elapsed_ms)
    if nav_finished_ms is not None:
        end_candidates.append(nav_finished_ms)
    if finished_ms is not None and elapsed_ms is None:
        end_candidates.append(finished_ms)
    if not end_candidates:
        return lines

    window_start = start_ms - start_grace_ms
    window_end = max(end_candidates) + end_grace_ms
    filtered = []
    for line in lines:
        event_ms = proxy_line_epoch_ms(str(line))
        if event_ms is None or window_start <= event_ms <= window_end:
            filtered.append(line)
    return filtered


def proxy_pre_run_circuit_selection_context_lines(
    all_lines: list[str],
    run_lines: list[str],
    run: dict[str, object],
    *,
    start_grace_ms: float = 250.0,
) -> list[str]:
    start_ms = numeric_value(run.get("started_epoch_ms"))
    if start_ms is None:
        return []
    run_circuits = proxy_circuit_ids(run_lines)
    if not run_circuits:
        return []
    window_start = start_ms - start_grace_ms
    context = []
    for line in all_lines:
        text = str(line)
        if not (
            "torfast circuit selection open" in text
            or "torfast circuit selection build complete" in text
        ):
            continue
        event_ms = proxy_line_epoch_ms(text)
        if event_ms is None or event_ms >= window_start:
            continue
        if any(
            proxy_circuit_ids_match(candidate, run_circuit)
            for candidate in proxy_circuit_ids([text])
            for run_circuit in run_circuits
        ):
            context.append(text)
    return context


def proxy_circuit_ids(lines: list[str]) -> set[str]:
    circuits: set[str] = set()
    for line in lines:
        text = str(line)
        for pattern in (
            r"\bcirc_id=([^ ]+(?: [^ ]+)?)",
            r"\btunnel_unique_id=([^ ]+(?: [^ ]+)?)",
        ):
            for match in re.finditer(pattern, text):
                circuits.add(match.group(1))
    return circuits


def proxy_stream_keys(lines: list[str]) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    for line in lines:
        text = str(line)
        stream_match = re.search(r"\bstream_id=([0-9]+)", text)
        if not stream_match:
            continue
        stream_id = stream_match.group(1)
        for circ_id in proxy_circuit_ids([text]):
            keys.add((circ_id, stream_id))
    return keys


def proxy_stream_keys_match(left: tuple[str, str], right: tuple[str, str]) -> bool:
    return left[1] == right[1] and proxy_circuit_ids_match(left[0], right[0])


def proxy_circuit_ids_match(left: str, right: str) -> bool:
    return left == right or left.startswith(right) or right.startswith(left)


def proxy_line_epoch_ms(line: str) -> float | None:
    match = re.search(
        r"\b(?:event_epoch_ms|conn_started_epoch_ms|first_tor_to_client_epoch_ms)="
        r"([0-9]+(?:\.[0-9]+)?)",
        line,
    )
    if match:
        return numeric_value(match.group(1))
    timestamp_match = re.match(
        r"^([0-9]{4}-[0-9]{2}-[0-9]{2}T"
        r"[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?Z)\b",
        line,
    )
    if not timestamp_match:
        return None
    try:
        timestamp = datetime.fromisoformat(
            timestamp_match.group(1).replace("Z", "+00:00")
        )
    except ValueError:
        return None
    return timestamp.timestamp() * 1000.0


def numeric_value(value: object) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def append_proxy_signal_lines(
    result: dict[str, object], signal_lines: list[str]
) -> None:
    existing = result.get("proxy_signal_lines", [])
    if not isinstance(existing, list):
        existing = []
    result["proxy_signal_lines"] = proxy_signal_lines_with_relay_context(
        [str(line) for line in existing + signal_lines]
    )


def append_proxy_relay_context_lines(
    result: dict[str, object], relay_context_lines: list[str]
) -> None:
    existing = result.get("proxy_relay_context_lines", [])
    if not isinstance(existing, list):
        existing = []
    result["proxy_relay_context_lines"] = proxy_signal_lines_with_relay_context(
        [str(line) for line in existing + relay_context_lines]
    )


def proxy_signal_lines_with_relay_context(lines: list[str]) -> list[str]:
    text_lines = [str(line) for line in lines]
    if len(text_lines) <= PROXY_SIGNAL_LINE_LIMIT:
        return text_lines
    tail = text_lines[-PROXY_SIGNAL_LINE_LIMIT:]
    relay_finished_ids = set()
    tail_stream_keys = proxy_stream_keys(tail)
    tail_stream_timing_ids = set()
    slow_connect_ids = torfast_slow_connect_timing_ids(text_lines)
    slow_connect_windows = torfast_slow_connect_windows(text_lines)
    for line in text_lines:
        if "torfast socks timing stream linked" not in line:
            continue
        if not any(
            proxy_stream_keys_match(candidate, tail_key)
            for candidate in proxy_stream_keys([line])
            for tail_key in tail_stream_keys
        ):
            continue
        timing_id = torfast_timing_id(line)
        if timing_id is not None:
            tail_stream_timing_ids.add(timing_id)
    for line in tail:
        if "torfast socks timing relay finished" not in line:
            continue
        timing_id = torfast_timing_id(line)
        if timing_id is not None:
            relay_finished_ids.add(timing_id)
    context = [
        line
        for line in text_lines
        if "torfast circuit selection" in line
        or any(marker in line for marker in PROXY_ALWAYS_KEEP_SUBSTRINGS)
        or (
            "torfast socks timing" in line
            and torfast_timing_id(line) in slow_connect_ids
        )
        or torfast_phase_line_matches_slow_connect(line, slow_connect_windows)
        or (
            "torfast socks timing" in line
            and torfast_timing_id(line) in (relay_finished_ids | tail_stream_timing_ids)
        )
        or (
            "torfast socks byte event" in line
            and torfast_timing_id(line) in tail_stream_timing_ids
        )
        or (
            "torfast socks timing stream linked" in line
            and any(
                proxy_stream_keys_match(candidate, tail_key)
                for candidate in proxy_stream_keys([line])
                for tail_key in tail_stream_keys
            )
        )
    ]
    return merge_bounded_context_and_tail(context, tail, PROXY_SIGNAL_LINE_LIMIT)


def merge_bounded_context_and_tail(
    context: list[str], tail: list[str], limit: int
) -> list[str]:
    seen: set[str] = set()
    context_unique = []
    for line in context:
        if line in seen:
            continue
        seen.add(line)
        context_unique.append(line)
    tail_unique = []
    for line in tail:
        if line in seen:
            continue
        seen.add(line)
        tail_unique.append(line)
    kept_context = context_unique[-limit:]
    remaining = max(0, limit - len(kept_context))
    return kept_context + (tail_unique[-remaining:] if remaining else [])


def torfast_timing_id(line: str) -> int | None:
    match = re.search(r"\btiming_id=([0-9]+)", line)
    if not match:
        return None
    return int(match.group(1))


def torfast_slow_connect_timing_ids(lines: list[str]) -> set[int]:
    timing_ids: set[int] = set()
    for line in lines:
        if "torfast socks timing stream ready" not in line:
            continue
        connect_ms = torfast_connect_ms(line)
        timing_id = torfast_timing_id(line)
        if connect_ms is not None and connect_ms >= 1000 and timing_id is not None:
            timing_ids.add(timing_id)
    return timing_ids


def torfast_slow_connect_windows(lines: list[str]) -> list[dict[str, object]]:
    windows: list[dict[str, object]] = []
    for line in lines:
        if "torfast socks timing stream ready" not in line:
            continue
        connect_ms = torfast_connect_ms(line)
        if connect_ms is None or connect_ms < 1000:
            continue
        end_ms = None
        start_ms = numeric_value(torfast_log_field(line, "conn_started_epoch_ms"))
        if start_ms is not None:
            end_ms = start_ms + connect_ms
        else:
            event_ms = proxy_line_epoch_ms(line)
            if event_ms is not None:
                end_ms = event_ms
                start_ms = event_ms - connect_ms
        if start_ms is None or end_ms is None:
            continue
        windows.append(
            {
                "start_ms": start_ms,
                "end_ms": end_ms,
                "target_kind": torfast_log_field(line, "target_kind"),
                "port": torfast_log_field(line, "port"),
            }
        )
    return windows


def torfast_phase_line_matches_slow_connect(
    line: str, windows: list[dict[str, object]]
) -> bool:
    if not (
        "torfast hs client timing" in line
        or "torfast exit client timing" in line
    ):
        return False
    event_ms = proxy_line_epoch_ms(line)
    if event_ms is None:
        return False
    phase_kind = (
        "onion" if "torfast hs client timing" in line else "hostname"
    )
    port = torfast_log_field(line, "port")
    for window in windows:
        target_kind = window.get("target_kind")
        if target_kind and target_kind != phase_kind:
            continue
        window_port = window.get("port")
        if port and window_port and port != window_port:
            continue
        start_ms = numeric_value(window.get("start_ms"))
        end_ms = numeric_value(window.get("end_ms"))
        if start_ms is None or end_ms is None:
            continue
        if start_ms - 250 <= event_ms <= end_ms + 250:
            return True
    return False


def torfast_connect_ms(line: str) -> float | None:
    return numeric_value(torfast_log_field(line, "connect_ms"))


def torfast_log_field(line: str, field: str) -> str | None:
    match = re.search(rf"\b{re.escape(field)}=([^ ]+)", line)
    if not match:
        return None
    return match.group(1).strip('"')


def proxy_signal_lines(lines: list[str]) -> list[str]:
    signals = []
    for line in lines:
        if any(marker in line for marker in PROXY_SIGNAL_SUBSTRINGS):
            signals.append(line)
            continue
        if "torfast relay receive" in line and "delivered" not in line:
            signals.append(line)
    return signals


def proxy_relay_context_lines(lines: list[str]) -> list[str]:
    context = []
    seen = set()
    for line in proxy_signal_lines(lines):
        if line not in seen:
            seen.add(line)
            context.append(line)
    for line in lines:
        if (
            "torfast relay receive delivered" not in line
            and "torfast stream receiver" not in line
        ):
            continue
        if line in seen:
            continue
        seen.add(line)
        context.append(line)
    return context


def boot_signal_lines(lines: list[str]) -> list[str]:
    signals = []
    for line in lines:
        lower = line.lower()
        if any(marker in lower for marker in BOOT_SIGNAL_SUBSTRINGS):
            signals.append(line)
    return signals


def read_browser_default_prefs(browser_bin: Path) -> dict[str, object]:
    contents_dir = browser_bin.parent.parent
    omni = contents_dir / "Resources" / "browser" / "omni.ja"
    if not omni.exists():
        return {"ok": False, "error": f"not found: {omni}"}
    try:
        with zipfile.ZipFile(omni) as archive:
            text = archive.read("defaults/preferences/000-tor-browser.js").decode(
                "utf-8", errors="replace"
            )
    except Exception as exc:  # noqa: BLE001 - metadata only.
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    prefs = parse_default_pref_text(text)
    return {
        "ok": True,
        "source": str(omni),
        "prefs": {key: prefs.get(key) for key in DEFAULT_PREF_KEYS},
    }


def validate_default_prefs(default_prefs: dict[str, object]) -> dict[str, object]:
    failures: list[str] = []
    if not default_prefs.get("ok"):
        failures.append(str(default_prefs.get("error", "default prefs missing")))
        return {"ok": False, "failures": failures}
    prefs = default_prefs.get("prefs", {})
    if not isinstance(prefs, dict):
        return {"ok": False, "failures": ["default prefs payload is not a dict"]}
    for key, expected in REQUIRED_DEFAULT_PREFS.items():
        actual = prefs.get(key)
        if actual != expected:
            failures.append(f"{key}: expected {expected!r}, got {actual!r}")
    return {"ok": not failures, "failures": failures}


def parse_default_pref_text(text: str) -> dict[str, object]:
    prefs: dict[str, object] = {}
    pattern = re.compile(r'^\s*pref\("([^"]+)",\s*(.*?)\);\s*(?://.*)?$')
    for line in text.splitlines():
        match = pattern.match(line)
        if not match:
            continue
        key = match.group(1)
        value_text = match.group(2)
        if value_text.endswith(", locked"):
            value_text = value_text.removesuffix(", locked").strip()
        prefs[key] = parse_pref_value(value_text)
    return prefs


def normalize_browser_block_url_substrings(
    values: list[str] | None,
) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in values or []:
        value = str(raw).strip()
        if not value:
            raise ValueError("must not be blank")
        if value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


def read_runtime_prefs(profile_dir: Path) -> dict[str, object]:
    prefs_path = profile_dir / "prefs.js"
    if not prefs_path.exists():
        return {}
    prefs: dict[str, object] = {}
    pattern = re.compile(r'^user_pref\("([^"]+)",\s*(.*?)\);\s*$')
    for line in prefs_path.read_text(errors="replace").splitlines():
        match = pattern.match(line)
        if not match:
            continue
        key = match.group(1)
        if key in RUNTIME_PREF_KEYS:
            prefs[key] = parse_pref_value(match.group(2))
    return prefs


class MarionetteClient:
    def __init__(self, sock: socket.socket, hello: dict[str, object]):
        self.sock = sock
        self.hello = hello
        self.next_id = 0

    @classmethod
    def connect(
        cls,
        *,
        host: str,
        port: int,
        proc: subprocess.Popen[str],
        lines: queue.Queue[str],
        timeout: float,
    ) -> "MarionetteClient":
        started = time.monotonic()
        recent_lines: list[str] = []
        while time.monotonic() - started < timeout:
            if proc.poll() is not None:
                recent_lines.extend(drain_queue(lines))
                raise TimeoutError(
                    f"browser exited before marionette opened: {recent_lines[-20:]}"
                )
            try:
                sock = socket.create_connection((host, port), timeout=1.0)
                sock.settimeout(timeout)
                client = cls(sock, {})
                hello = client.read_packet()
                if isinstance(hello, dict):
                    client.hello = hello
                return client
            except OSError:
                recent_lines.extend(drain_queue(lines))
                time.sleep(0.2)
        recent_lines.extend(drain_queue(lines))
        raise TimeoutError(
            f"marionette did not open on {host}:{port}: {recent_lines[-20:]}"
        )

    def command(self, name: str, params: dict[str, object]) -> dict[str, object]:
        self.next_id += 1
        command_id = self.next_id
        self.write_packet([0, command_id, name, params])
        while True:
            packet = self.read_packet()
            if (
                isinstance(packet, list)
                and len(packet) >= 4
                and packet[0] == 1
                and packet[1] == command_id
            ):
                if packet[2] is not None:
                    raise RuntimeError(packet[2])
                result = packet[3]
                return result if isinstance(result, dict) else {"value": result}

    def write_packet(self, payload: object) -> None:
        data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.sock.sendall(str(len(data)).encode("ascii") + b":" + data)

    def read_packet(self) -> object:
        length_bytes = b""
        while True:
            char = self.sock.recv(1)
            if char == b":":
                break
            if not char:
                raise EOFError("marionette socket closed before packet length")
            length_bytes += char
        length = int(length_bytes)
        data = b""
        while len(data) < length:
            chunk = self.sock.recv(length - len(data))
            if not chunk:
                raise EOFError("marionette socket closed during packet body")
            data += chunk
        return json.loads(data.decode("utf-8"))

    def close(self) -> None:
        self.sock.close()


def optional_command(client: MarionetteClient, name: str) -> object:
    try:
        result = client.command(name, {})
    except Exception:  # noqa: BLE001 - optional evidence only.
        return None
    return result.get("value")


def configure_browser_lab_prefs(
    client: MarionetteClient,
    *,
    serial_http_connections: bool = False,
    max_persistent_connections_per_server: int | None = None,
) -> dict[str, object]:
    lab: dict[str, object] = {
        "serial_http_connections": {"enabled": serial_http_connections},
        "max_persistent_connections_per_server": {
            "enabled": max_persistent_connections_per_server is not None,
            "requested_value": max_persistent_connections_per_server,
        },
    }
    requested_prefs: dict[str, int] = {}
    if serial_http_connections:
        requested_prefs.update(BROWSER_SERIAL_HTTP_PREFS)
    if max_persistent_connections_per_server is not None:
        requested_prefs["network.http.max-persistent-connections-per-server"] = (
            max_persistent_connections_per_server
        )
    if not requested_prefs:
        return lab

    script = r"""
const requested = arguments[0];
const prefBranch = Components.classes["@mozilla.org/preferences-service;1"]
  .getService(Components.interfaces.nsIPrefBranch);
function typeName(type) {
  if (type === prefBranch.PREF_BOOL) {
    return "bool";
  }
  if (type === prefBranch.PREF_INT) {
    return "int";
  }
  if (type === prefBranch.PREF_STRING) {
    return "string";
  }
  return "invalid";
}
function readValue(key, type) {
  if (type === prefBranch.PREF_BOOL) {
    return prefBranch.getBoolPref(key);
  }
  if (type === prefBranch.PREF_INT) {
    return prefBranch.getIntPref(key);
  }
  if (type === prefBranch.PREF_STRING) {
    return prefBranch.getStringPref(key);
  }
  return null;
}
const rows = {};
for (const [key, value] of Object.entries(requested)) {
  const oldType = prefBranch.getPrefType(key);
  const oldValue = readValue(key, oldType);
  prefBranch.setIntPref(key, value);
  const newType = prefBranch.getPrefType(key);
  rows[key] = {
    old_type: typeName(oldType),
    old_value: oldValue,
    set_value: value,
    type: typeName(newType),
    value: readValue(key, newType),
  };
}
return JSON.stringify({ok: true, prefs: rows});
"""
    context_set = False
    try:
        client.command("Marionette:SetContext", {"value": "chrome"})
        context_set = True
        result = client.command(
            "WebDriver:ExecuteScript",
            {
                "script": script,
                "args": [requested_prefs],
                "newSandbox": True,
            },
        )
        value = result.get("value")
        parsed = json.loads(value) if isinstance(value, str) else value
        if not isinstance(parsed, dict):
            for state in lab.values():
                if isinstance(state, dict) and state.get("enabled"):
                    state.update({"ok": False, "error": "unexpected result"})
        else:
            if serial_http_connections:
                state = lab["serial_http_connections"]
                assert isinstance(state, dict)
                state.update(parsed)
            if max_persistent_connections_per_server is not None:
                state = lab["max_persistent_connections_per_server"]
                assert isinstance(state, dict)
                state.update(parsed)
    except Exception as exc:  # noqa: BLE001 - lab proof should record failures.
        for state in lab.values():
            if isinstance(state, dict) and state.get("enabled"):
                state.update({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
    finally:
        if context_set:
            try:
                client.command("Marionette:SetContext", {"value": "content"})
            except Exception:
                pass
    return lab


def install_browser_request_blocker(
    client: MarionetteClient,
    *,
    url_substrings: list[str] | None,
) -> dict[str, object]:
    normalized_url_substrings = normalize_browser_block_url_substrings(url_substrings)
    if not normalized_url_substrings:
        return {"enabled": False, "url_substrings": []}

    script = r"""
const Ci = Components.interfaces;
const Cr = Components.results;
let Services;
if (globalThis.Services) {
  Services = globalThis.Services;
} else {
  Services = ChromeUtils.import("resource://gre/modules/Services.jsm").Services;
}
const urlSubstrings = arguments[0];
const limit = arguments[1];
if (this.__torfastBrowserRequestBlockerObserver) {
  try {
    Services.obs.removeObserver(
      this.__torfastBrowserRequestBlockerObserver,
      "http-on-modify-request"
    );
  } catch (e) {}
}
this.__torfastBrowserRequestBlockerRows = [];
this.__torfastBrowserRequestBlockerObservedCount = 0;
this.__torfastBrowserRequestBlockerUrlSubstrings = urlSubstrings;
const rows = this.__torfastBrowserRequestBlockerRows;
function pushRow(row) {
  rows.push(row);
  while (rows.length > limit) {
    rows.shift();
  }
}
function readChannel(subject, row) {
  try {
    subject.QueryInterface(Ci.nsIHttpChannel);
    row.uri = subject.URI.spec;
    row.channel_id = subject.channelId;
    row.request_method = subject.requestMethod;
  } catch (e) {
    row.http_error = String(e);
  }
}
this.__torfastBrowserRequestBlockerObserver = {
  QueryInterface: ChromeUtils.generateQI(["nsIObserver"]),
  observe(subject, topic, data) {
    if (topic !== "http-on-modify-request") {
      return;
    }
    this.__torfastBrowserRequestBlockerObservedCount += 1;
    const row = {
      topic,
      observed_epoch_ms: Date.now(),
      data: String(data || ""),
    };
    readChannel(subject, row);
    const uri = row.uri || "";
    const matchedSubstrings = urlSubstrings.filter(
      (substring) => substring && uri.includes(substring)
    );
    if (!matchedSubstrings.length) {
      return;
    }
    row.matched_substrings = matchedSubstrings;
    try {
      subject.QueryInterface(Ci.nsIRequest);
      subject.cancel(Cr.NS_BINDING_ABORTED);
      row.cancelled = true;
      row.cancel_status = "NS_BINDING_ABORTED";
    } catch (e) {
      row.cancelled = false;
      row.cancel_error = String(e);
    }
    pushRow(row);
  },
};
Services.obs.addObserver(
  this.__torfastBrowserRequestBlockerObserver,
  "http-on-modify-request"
);
return JSON.stringify({
  enabled: true,
  ok: true,
  topic: "http-on-modify-request",
  limit,
  url_substrings: urlSubstrings,
});
"""
    context_set = False
    try:
        client.command("Marionette:SetContext", {"value": "chrome"})
        context_set = True
        result = client.command(
            "WebDriver:ExecuteScript",
            {
                "script": script,
                "args": [normalized_url_substrings, BROWSER_REQUEST_BLOCKER_LIMIT],
                "newSandbox": True,
                "sandbox": TORFAST_BROWSER_REQUEST_BLOCKER_SANDBOX,
            },
        )
        value = result.get("value")
        parsed = json.loads(value) if isinstance(value, str) else value
        if isinstance(parsed, dict):
            return parsed
        return {
            "enabled": True,
            "url_substrings": normalized_url_substrings,
            "ok": False,
            "error": "unexpected result",
        }
    except Exception as exc:  # noqa: BLE001 - lab evidence should record failures.
        return {
            "enabled": True,
            "url_substrings": normalized_url_substrings,
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
        }
    finally:
        if context_set:
            try:
                client.command("Marionette:SetContext", {"value": "content"})
            except Exception:
                pass


def collect_browser_request_blocker(
    client: MarionetteClient,
    blocker: dict[str, object],
) -> dict[str, object]:
    if blocker.get("enabled") is not True:
        return blocker

    script = r"""
let Services;
if (globalThis.Services) {
  Services = globalThis.Services;
} else {
  Services = ChromeUtils.import("resource://gre/modules/Services.jsm").Services;
}
const rows = this.__torfastBrowserRequestBlockerRows || [];
const observedRequestCount = this.__torfastBrowserRequestBlockerObservedCount || 0;
const urlSubstrings = this.__torfastBrowserRequestBlockerUrlSubstrings || [];
if (this.__torfastBrowserRequestBlockerObserver) {
  try {
    Services.obs.removeObserver(
      this.__torfastBrowserRequestBlockerObserver,
      "http-on-modify-request"
    );
  } catch (e) {}
}
this.__torfastBrowserRequestBlockerObserver = null;
this.__torfastBrowserRequestBlockerRows = [];
this.__torfastBrowserRequestBlockerObservedCount = 0;
this.__torfastBrowserRequestBlockerUrlSubstrings = [];
return JSON.stringify({
  enabled: true,
  ok: true,
  observed_request_count: observedRequestCount,
  blocked_request_count: rows.length,
  row_count: rows.length,
  rows,
  url_substrings: urlSubstrings,
});
"""
    context_set = False
    try:
        client.command("Marionette:SetContext", {"value": "chrome"})
        context_set = True
        result = client.command(
            "WebDriver:ExecuteScript",
            {
                "script": script,
                "args": [],
                "newSandbox": False,
                "sandbox": TORFAST_BROWSER_REQUEST_BLOCKER_SANDBOX,
            },
        )
        value = result.get("value")
        parsed = json.loads(value) if isinstance(value, str) else value
        if isinstance(parsed, dict):
            merged = dict(blocker)
            merged.update(parsed)
            return merged
        merged = dict(blocker)
        merged.update({"ok": False, "error": "unexpected result"})
        return merged
    except Exception as exc:  # noqa: BLE001 - lab evidence should record failures.
        merged = dict(blocker)
        merged.update({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
        return merged
    finally:
        if context_set:
            try:
                client.command("Marionette:SetContext", {"value": "content"})
            except Exception:
                pass


def install_browser_activity_probe(
    client: MarionetteClient,
    *,
    enabled: bool,
) -> dict[str, object]:
    if not enabled:
        return {"enabled": False}

    script = r"""
const Ci = Components.interfaces;
const Cc = Components.classes;
const topics = arguments[0];
const limit = arguments[1];
let Services;
if (globalThis.Services) {
  Services = globalThis.Services;
} else {
  Services = ChromeUtils.import("resource://gre/modules/Services.jsm").Services;
}
if (this.__torfastBrowserActivityObserver) {
  for (const topic of this.__torfastBrowserActivityTopics || []) {
    try {
      Services.obs.removeObserver(this.__torfastBrowserActivityObserver, topic);
    } catch (e) {}
  }
  try {
    if (this.__torfastBrowserActivityDistributor) {
      this.__torfastBrowserActivityDistributor.removeObserver(
        this.__torfastBrowserActivityObserver
      );
    }
  } catch (e) {}
}
this.__torfastBrowserActivityRows = [];
this.__torfastBrowserActivityTopics = topics;
const rows = this.__torfastBrowserActivityRows;
function pushRow(row) {
  rows.push(row);
  while (rows.length > limit) {
    rows.shift();
  }
}
function readChannelValue(channel, key, row) {
  try {
    row[key] = channel[key];
  } catch (e) {}
}
function readKnownObjectFields(value, prefix, row) {
  for (const key of [
    "connectionInfoHashKey",
    "connInfoKey",
    "host",
    "port",
    "localAddress",
    "localPort",
    "remoteAddress",
    "remotePort",
    "ssl",
    "hasECH",
    "isHttp3",
  ]) {
    try {
      const field = value[key];
      if (field !== undefined && field !== null) {
        row[prefix + key] = field;
      }
    } catch (e) {}
  }
}
function readActivitySubject(subject, row) {
  try {
    subject.QueryInterface(Ci.nsIHttpChannel);
    row.uri = subject.URI.spec;
    row.channel_id = subject.channelId;
    row.request_method = subject.requestMethod;
  } catch (e) {
    row.http_error = String(e);
  }
  try {
    subject.QueryInterface(Ci.nsIHttpChannelInternal);
    readChannelValue(subject, "localAddress", row);
    readChannelValue(subject, "localPort", row);
    readChannelValue(subject, "remoteAddress", row);
    readChannelValue(subject, "remotePort", row);
  } catch (e) {
    row.internal_error = String(e);
  }
  try {
    readKnownObjectFields(subject, "subject_", row);
  } catch (e) {}
}
function readActivityValue(value, prefix, row) {
  if (value === undefined || value === null) {
    return;
  }
  const type = typeof value;
  if (type === "string" || type === "number" || type === "boolean") {
    row[prefix + "value"] = value;
    return;
  }
  try {
    row[prefix + "string"] = String(value);
  } catch (e) {}
  try {
    readKnownObjectFields(value, prefix, row);
  } catch (e) {}
}
function recordActivity(method, args) {
  const row = {
    source: "http_activity",
    method,
    observed_epoch_ms: Date.now(),
    arg_count: args.length,
  };
  if (args.length >= 1) {
    readActivitySubject(args[0], row);
  }
  if (args.length >= 2) {
    row.activity_type = args[1];
  }
  if (args.length >= 3) {
    row.activity_subtype = args[2];
  }
  if (args.length >= 4) {
    row.activity_timestamp = args[3];
  }
  if (args.length >= 5) {
    row.extra_size_data = args[4];
  }
  if (args.length >= 6 && args[5] !== undefined && args[5] !== null) {
    row.extra_string_data = String(args[5]);
  }
  if (args.length >= 7) {
    readActivityValue(args[6], "extra_args_", row);
  }
  pushRow(row);
}
this.__torfastBrowserActivityObserver = {
  QueryInterface: ChromeUtils.generateQI(["nsIObserver", "nsIHttpActivityObserver"]),
  observe(subject, topic, data) {
    const row = {
      source: "observer_topic",
      topic,
      observed_epoch_ms: Date.now(),
      data: String(data || ""),
    };
    readActivitySubject(subject, row);
    if (
      row.localPort !== undefined ||
      row.remotePort !== undefined ||
      topic === "http-on-examine-response" ||
      topic === "http-on-stop-request"
    ) {
      pushRow(row);
    }
  },
  observeActivity(...args) {
    recordActivity("observeActivity", args);
  },
  observeActivityWithArgs(...args) {
    recordActivity("observeActivityWithArgs", args);
  },
};
for (const topic of topics) {
  Services.obs.addObserver(this.__torfastBrowserActivityObserver, topic);
}
let activityDistributorOk = false;
let activityDistributorError = "";
try {
  this.__torfastBrowserActivityDistributor = Cc[
    "@mozilla.org/network/http-activity-distributor;1"
  ].getService(Ci.nsIHttpActivityDistributor);
  this.__torfastBrowserActivityDistributor.addObserver(
    this.__torfastBrowserActivityObserver
  );
  activityDistributorOk = true;
} catch (e) {
  this.__torfastBrowserActivityDistributor = null;
  activityDistributorError = String(e);
}
return JSON.stringify({
  enabled: true,
  ok: true,
  topics,
  limit,
  activity_distributor_ok: activityDistributorOk,
  activity_distributor_error: activityDistributorError,
});
"""
    context_set = False
    try:
        client.command("Marionette:SetContext", {"value": "chrome"})
        context_set = True
        result = client.command(
            "WebDriver:ExecuteScript",
            {
                "script": script,
                "args": [BROWSER_ACTIVITY_PROBE_TOPICS, BROWSER_ACTIVITY_PROBE_LIMIT],
                "newSandbox": True,
                "sandbox": TORFAST_BROWSER_ACTIVITY_SANDBOX,
            },
        )
        value = result.get("value")
        parsed = json.loads(value) if isinstance(value, str) else value
        if isinstance(parsed, dict):
            return parsed
        return {"enabled": True, "ok": False, "error": "unexpected result"}
    except Exception as exc:  # noqa: BLE001 - lab evidence should record failures.
        return {"enabled": True, "ok": False, "error": f"{type(exc).__name__}: {exc}"}
    finally:
        if context_set:
            try:
                client.command("Marionette:SetContext", {"value": "content"})
            except Exception:
                pass


def collect_browser_activity_probe(
    client: MarionetteClient,
    probe: dict[str, object],
) -> dict[str, object]:
    if probe.get("enabled") is not True:
        return probe

    script = r"""
let Services;
if (globalThis.Services) {
  Services = globalThis.Services;
} else {
  Services = ChromeUtils.import("resource://gre/modules/Services.jsm").Services;
}
const rows = this.__torfastBrowserActivityRows || [];
if (this.__torfastBrowserActivityObserver) {
  for (const topic of this.__torfastBrowserActivityTopics || []) {
    try {
      Services.obs.removeObserver(this.__torfastBrowserActivityObserver, topic);
    } catch (e) {}
  }
  try {
    if (this.__torfastBrowserActivityDistributor) {
      this.__torfastBrowserActivityDistributor.removeObserver(
        this.__torfastBrowserActivityObserver
      );
    }
  } catch (e) {}
}
this.__torfastBrowserActivityObserver = null;
this.__torfastBrowserActivityDistributor = null;
return JSON.stringify({
  enabled: true,
  ok: true,
  row_count: rows.length,
  rows,
});
"""
    context_set = False
    try:
        client.command("Marionette:SetContext", {"value": "chrome"})
        context_set = True
        result = client.command(
            "WebDriver:ExecuteScript",
            {
                "script": script,
                "args": [],
                "newSandbox": False,
                "sandbox": TORFAST_BROWSER_ACTIVITY_SANDBOX,
            },
        )
        value = result.get("value")
        parsed = json.loads(value) if isinstance(value, str) else value
        if isinstance(parsed, dict):
            merged = dict(probe)
            merged.update(parsed)
            return merged
        merged = dict(probe)
        merged.update({"ok": False, "error": "unexpected result"})
        return merged
    except Exception as exc:  # noqa: BLE001 - lab evidence should record failures.
        merged = dict(probe)
        merged.update({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
        return merged
    finally:
        if context_set:
            try:
                client.command("Marionette:SetContext", {"value": "content"})
            except Exception:
                pass


def collect_performance_timing(client: MarionetteClient) -> dict[str, object]:
    script = r"""
const nav = performance.getEntriesByType("navigation")[0];
const resources = performance.getEntriesByType("resource").map((entry) => ({
	  name: entry.name,
	  initiatorType: entry.initiatorType,
	  nextHopProtocol: entry.nextHopProtocol || "",
	  startTime: entry.startTime,
  duration: entry.duration,
  fetchStart: entry.fetchStart,
  domainLookupStart: entry.domainLookupStart,
  domainLookupEnd: entry.domainLookupEnd,
  connectStart: entry.connectStart,
  connectEnd: entry.connectEnd,
  requestStart: entry.requestStart,
  responseStart: entry.responseStart,
  responseEnd: entry.responseEnd,
  requestWait: entry.responseStart - entry.requestStart,
  responseReceive: entry.responseEnd - entry.responseStart,
  fetchToResponse: entry.responseStart - entry.fetchStart,
  transferSize: entry.transferSize,
  encodedBodySize: entry.encodedBodySize,
  decodedBodySize: entry.decodedBodySize,
}));
const byType = {};
for (const entry of resources) {
  const key = entry.initiatorType || "unknown";
  byType[key] = (byType[key] || 0) + 1;
}
return JSON.stringify({
  time_origin_ms: performance.timeOrigin,
  navigation: nav ? nav.toJSON() : null,
  resource_count: resources.length,
  resource_count_by_type: byType,
  resources: resources
    .slice()
    .sort((left, right) => left.startTime - right.startTime),
  slowest_resources: resources
    .slice()
    .sort((left, right) => right.duration - left.duration)
    .slice(0, 20),
});
"""
    try:
        result = client.command(
            "WebDriver:ExecuteScript",
            {"script": script, "args": [], "newSandbox": True},
        )
        value = result.get("value")
        if isinstance(value, str):
            parsed = json.loads(value)
        else:
            parsed = value
        return parsed if isinstance(parsed, dict) else {"error": "unexpected result"}
    except Exception as exc:  # noqa: BLE001 - optional timing evidence only.
        return {"error": f"{type(exc).__name__}: {exc}"}


def collect_page_resource_discovery(client: MarionetteClient) -> dict[str, object]:
    script = r"""
function absoluteUrl(raw) {
  if (!raw) {
    return "";
  }
  try {
    return new URL(String(raw), document.baseURI).href;
  } catch (e) {
    return String(raw);
  }
}
function pushLimited(list, row, limit) {
  list.push(row);
  while (list.length > limit) {
    list.shift();
  }
}
function extractUrls(value) {
  if (typeof value !== "string" || !value.includes("url(")) {
    return [];
  }
  const urls = [];
  const regex = /url\(([^)]+)\)/g;
  let match;
  while ((match = regex.exec(value)) !== null) {
    let inner = match[1].trim();
    if (
      (inner.startsWith('"') && inner.endsWith('"')) ||
      (inner.startsWith("'") && inner.endsWith("'"))
    ) {
      inner = inner.slice(1, -1);
    }
    if (!inner || inner.startsWith("data:")) {
      continue;
    }
    urls.push(absoluteUrl(inner));
  }
  return urls;
}
function rowForUrl(map, url) {
  let row = map.get(url);
  if (!row) {
    row = {
      url,
      direct_refs: [],
      css_refs: [],
    };
    map.set(url, row);
  }
  return row;
}
function addDirectRef(map, url, ref) {
  if (!url) {
    return;
  }
  const row = rowForUrl(map, url);
  pushLimited(row.direct_refs, ref, 6);
}
function addCssRef(map, url, ref) {
  if (!url) {
    return;
  }
  const row = rowForUrl(map, url);
  pushLimited(row.css_refs, ref, 8);
}
function sampleClasses(element) {
  try {
    if (!element.classList) {
      return [];
    }
    return Array.from(element.classList).slice(0, 4);
  } catch (e) {
    return [];
  }
}
function collectDirectDomRefs(map) {
  for (const element of document.querySelectorAll("img,script[src],link[href],source[src]")) {
    const tag = element.tagName.toLowerCase();
    if (tag === "img") {
      addDirectRef(map, absoluteUrl(element.currentSrc || element.src), {
        tag,
        attr: "src",
        id: element.id || "",
        classes: sampleClasses(element),
      });
      continue;
    }
    if (tag === "script") {
      addDirectRef(map, absoluteUrl(element.src), {
        tag,
        attr: "src",
        id: element.id || "",
        classes: sampleClasses(element),
      });
      continue;
    }
    if (tag === "source") {
      addDirectRef(map, absoluteUrl(element.src), {
        tag,
        attr: "src",
        id: element.id || "",
        classes: sampleClasses(element),
      });
      continue;
    }
    if (tag === "link") {
      addDirectRef(map, absoluteUrl(element.href), {
        tag,
        attr: "href",
        rel: element.rel || "",
        as: element.as || "",
        id: element.id || "",
        classes: sampleClasses(element),
      });
    }
  }
}
function cssRuleKind(rule) {
  try {
    if (rule.type === CSSRule.FONT_FACE_RULE) {
      return "@font-face";
    }
    if (rule.type === CSSRule.IMPORT_RULE) {
      return "@import";
    }
    if (rule.selectorText) {
      return "style";
    }
  } catch (e) {}
  try {
    if (rule.constructor && rule.constructor.name) {
      return rule.constructor.name;
    }
  } catch (e) {}
  return "rule";
}
function collectRuleUrls(rule, stylesheetHref, map) {
  if (!rule) {
    return;
  }
  let nestedRules = null;
  try {
    nestedRules = rule.cssRules || rule.rules || null;
  } catch (e) {
    nestedRules = null;
  }
  if (nestedRules) {
    for (const nested of nestedRules) {
      collectRuleUrls(nested, stylesheetHref, map);
    }
  }
  let style = null;
  try {
    style = rule.style || null;
  } catch (e) {
    style = null;
  }
  if (!style) {
    return;
  }
  const selector = typeof rule.selectorText === "string" ? rule.selectorText : "";
  const kind = cssRuleKind(rule);
  for (const propertyName of Array.from(style)) {
    const value = style.getPropertyValue(propertyName);
    for (const url of extractUrls(value)) {
      addCssRef(map, url, {
        property: propertyName,
        selector: selector,
        stylesheet: stylesheetHref,
        rule_kind: kind,
      });
    }
  }
}
function collectStylesheetRefs(map) {
  for (const sheet of Array.from(document.styleSheets || [])) {
    let href = "";
    try {
      href = absoluteUrl(sheet.href || document.baseURI);
    } catch (e) {
      href = "";
    }
    let rules = null;
    try {
      rules = sheet.cssRules || sheet.rules || null;
    } catch (e) {
      rules = null;
    }
    if (!rules) {
      continue;
    }
    for (const rule of rules) {
      collectRuleUrls(rule, href, map);
    }
  }
}
function uniqueValues(values) {
  return Array.from(new Set(values.filter((value) => value)));
}
const map = new Map();
collectDirectDomRefs(map);
collectStylesheetRefs(map);
const rows = Array.from(map.values())
  .map((row) => {
    const domTags = uniqueValues(row.direct_refs.map((ref) => ref.tag || ""));
    const domRels = uniqueValues(row.direct_refs.map((ref) => ref.rel || ""));
    const cssProperties = uniqueValues(row.css_refs.map((ref) => ref.property || ""));
    const cssStylesheets = uniqueValues(
      row.css_refs.map((ref) => ref.stylesheet || "")
    );
    const cssSelectors = uniqueValues(
      row.css_refs.map((ref) => ref.selector || "").filter((value) => value)
    );
    const cssRuleKinds = uniqueValues(
      row.css_refs.map((ref) => ref.rule_kind || "")
    );
    return {
      url: row.url,
      direct_ref_count: row.direct_refs.length,
      css_ref_count: row.css_refs.length,
      dom_tags: domTags,
      dom_rels: domRels,
      css_properties: cssProperties,
      css_stylesheets: cssStylesheets.slice(0, 6),
      css_selectors: cssSelectors.slice(0, 6),
      css_rule_kinds: cssRuleKinds,
      direct_refs: row.direct_refs,
      css_refs: row.css_refs,
    };
  })
  .sort((left, right) => left.url.localeCompare(right.url));
return JSON.stringify({
  ok: true,
  row_count: rows.length,
  rows,
});
"""
    try:
        result = client.command(
            "WebDriver:ExecuteScript",
            {"script": script, "args": [], "newSandbox": True},
        )
        value = result.get("value")
        parsed = json.loads(value) if isinstance(value, str) else value
        if not isinstance(parsed, dict):
            return {"ok": False, "error": "unexpected result"}
        return parsed
    except Exception as exc:  # noqa: BLE001 - optional discovery evidence only.
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def collect_browser_connection_prefs(client: MarionetteClient) -> dict[str, object]:
    script = r"""
const keys = arguments[0];
const prefBranch = Components.classes["@mozilla.org/preferences-service;1"]
  .getService(Components.interfaces.nsIPrefBranch);
const prefs = {};
for (const key of keys) {
  const type = prefBranch.getPrefType(key);
  if (type === prefBranch.PREF_BOOL) {
    prefs[key] = { type: "bool", value: prefBranch.getBoolPref(key) };
  } else if (type === prefBranch.PREF_INT) {
    prefs[key] = { type: "int", value: prefBranch.getIntPref(key) };
  } else if (type === prefBranch.PREF_STRING) {
    prefs[key] = { type: "string", value: prefBranch.getStringPref(key) };
  } else {
    prefs[key] = { type: "invalid", value: null };
  }
}
return JSON.stringify(prefs);
"""
    context_set = False
    try:
        client.command("Marionette:SetContext", {"value": "chrome"})
        context_set = True
        result = client.command(
            "WebDriver:ExecuteScript",
            {
                "script": script,
                "args": [BROWSER_CONNECTION_PREF_KEYS],
                "newSandbox": True,
            },
        )
        value = result.get("value")
        parsed = json.loads(value) if isinstance(value, str) else value
        if not isinstance(parsed, dict):
            return {"ok": False, "error": "unexpected result"}
        return {"ok": True, "prefs": parsed}
    except Exception as exc:  # noqa: BLE001 - optional pref evidence only.
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    finally:
        if context_set:
            try:
                client.command("Marionette:SetContext", {"value": "content"})
            except Exception:
                pass


def collect_browser_quality_prefs(client: MarionetteClient) -> dict[str, object]:
    script = r"""
const keys = arguments[0];
const prefBranch = Components.classes["@mozilla.org/preferences-service;1"]
  .getService(Components.interfaces.nsIPrefBranch);
const prefs = {};
for (const key of keys) {
  const type = prefBranch.getPrefType(key);
  if (type === prefBranch.PREF_BOOL) {
    prefs[key] = { type: "bool", value: prefBranch.getBoolPref(key) };
  } else if (type === prefBranch.PREF_INT) {
    prefs[key] = { type: "int", value: prefBranch.getIntPref(key) };
  } else if (type === prefBranch.PREF_STRING) {
    prefs[key] = { type: "string", value: prefBranch.getStringPref(key) };
  } else {
    prefs[key] = { type: "invalid", value: null };
  }
}
return JSON.stringify(prefs);
"""
    context_set = False
    try:
        client.command("Marionette:SetContext", {"value": "chrome"})
        context_set = True
        result = client.command(
            "WebDriver:ExecuteScript",
            {
                "script": script,
                "args": [BROWSER_QUALITY_PREF_KEYS],
                "newSandbox": True,
            },
        )
        value = result.get("value")
        parsed = json.loads(value) if isinstance(value, str) else value
        if not isinstance(parsed, dict):
            return {"ok": False, "error": "unexpected result"}
        return {"ok": True, "prefs": parsed}
    except Exception as exc:  # noqa: BLE001 - optional pref evidence only.
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    finally:
        if context_set:
            try:
                client.command("Marionette:SetContext", {"value": "content"})
            except Exception:
                pass


def validate_browser_quality_prefs(pref_audit: dict[str, object]) -> dict[str, object]:
    failures: list[str] = []
    if not pref_audit.get("ok"):
        failures.append(str(pref_audit.get("error", "browser quality prefs missing")))
        return {"ok": False, "failures": failures}
    prefs = pref_audit.get("prefs", {})
    if not isinstance(prefs, dict):
        return {"ok": False, "failures": ["browser quality prefs payload is not a dict"]}
    for key, expected in REQUIRED_DEFAULT_PREFS.items():
        entry = prefs.get(key)
        if not isinstance(entry, dict):
            failures.append(f"{key}: runtime pref missing")
            continue
        actual = entry.get("value")
        if actual != expected:
            failures.append(f"{key}: expected {expected!r}, got {actual!r}")
    return {"ok": not failures, "failures": failures}


def collect_browser_fingerprint_snapshot(client: MarionetteClient) -> dict[str, object]:
    script = r"""
const nav = navigator;
const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || null;
const snapshot = {
  userAgent: nav.userAgent || null,
  platform: nav.platform || null,
  oscpu: nav.oscpu || null,
  language: nav.language || null,
  languages: Array.isArray(nav.languages) ? Array.from(nav.languages) : [],
  hardwareConcurrency:
    Number.isFinite(nav.hardwareConcurrency) ? nav.hardwareConcurrency : null,
  maxTouchPoints:
    Number.isFinite(nav.maxTouchPoints) ? nav.maxTouchPoints : null,
  webdriver: nav.webdriver === true,
  doNotTrack: nav.doNotTrack ?? null,
  cookieEnabled: nav.cookieEnabled ?? null,
  timezone,
  timezoneOffset: new Date().getTimezoneOffset(),
  colorDepth: screen.colorDepth ?? null,
  pixelDepth: screen.pixelDepth ?? null,
  innerWidth: window.innerWidth ?? null,
  innerHeight: window.innerHeight ?? null,
  outerWidth: window.outerWidth ?? null,
  outerHeight: window.outerHeight ?? null,
  screenWidth: screen.width ?? null,
  screenHeight: screen.height ?? null,
  availWidth: screen.availWidth ?? null,
  availHeight: screen.availHeight ?? null,
  devicePixelRatio:
    Number.isFinite(window.devicePixelRatio) ? window.devicePixelRatio : null,
  reducedMotion: window.matchMedia("(prefers-reduced-motion: reduce)").matches,
  forcedColors: window.matchMedia("(forced-colors: active)").matches,
  darkScheme: window.matchMedia("(prefers-color-scheme: dark)").matches,
  pluginsLength: nav.plugins ? nav.plugins.length : null,
  mimeTypesLength: nav.mimeTypes ? nav.mimeTypes.length : null,
};
return JSON.stringify(snapshot);
"""
    try:
        result = client.command(
            "WebDriver:ExecuteScript",
            {"script": script, "args": [], "newSandbox": True},
        )
        value = result.get("value")
        parsed = json.loads(value) if isinstance(value, str) else value
        if not isinstance(parsed, dict):
            return {"ok": False, "error": "unexpected result"}
        return {"ok": True, "snapshot": parsed}
    except Exception as exc:  # noqa: BLE001 - optional fingerprint evidence only.
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def collect_no_marionette_fingerprint_snapshot(
    *,
    browser_bin: Path,
    output_dir: Path,
    window_size: str,
    compact_output: bool = False,
) -> dict[str, object]:
    proof_dir = output_dir / "browser_quality" / "no_marionette_fingerprint"
    profile_dir = proof_dir / "profile"
    home_dir = proof_dir / "home"
    page_path = proof_dir / "fingerprint.html"
    screenshot_path = proof_dir / "fingerprint.png"
    profile_dir.mkdir(parents=True, exist_ok=True)
    home_dir.mkdir(parents=True, exist_ok=True)
    page_path.write_text(no_marionette_fingerprint_page())

    env = os.environ.copy()
    env.update(
        {
            "HOME": str(home_dir.resolve()),
            "MOZ_CRASHREPORTER_DISABLE": "1",
            "MOZ_HEADLESS": "1",
            "TZ": "UTC",
            "TOR_PROVIDER": "none",
            "TOR_SKIP_LAUNCH": "1",
        }
    )
    command = [
        str(browser_bin),
        "--headless",
        "--window-size",
        window_size,
        "--profile",
        str(profile_dir.resolve()),
        "--screenshot",
        str(screenshot_path.resolve()),
        page_path.resolve().as_uri(),
    ]
    started = time.perf_counter()
    try:
        proc = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=60.0,
            check=False,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "proof_mode": "no_marionette_file_canvas_screenshot",
            "error": "no-Marionette fingerprint screenshot timed out",
            "stdout_tail": output_tail(exc.stdout),
            "screenshot": png_info(screenshot_path),
        }
    elapsed_ms = (time.perf_counter() - started) * 1000

    result: dict[str, object] = {
        "ok": False,
        "proof_mode": "no_marionette_file_canvas_screenshot",
        "elapsed_ms": round(elapsed_ms, 3),
        "exit_code": proc.returncode,
        "stdout_tail": output_tail(proc.stdout),
        "screenshot": png_info(screenshot_path),
    }
    if proc.returncode != 0:
        result["error"] = f"browser exited with code {proc.returncode}"
        return result
    try:
        snapshot = decode_no_marionette_fingerprint_png(screenshot_path)
    except Exception as exc:  # noqa: BLE001 - proof payload should record parse failure.
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result
    validation = validate_browser_fingerprint_snapshot({"ok": True, "snapshot": snapshot})
    result["snapshot"] = snapshot
    result["validation"] = validation
    result["ok"] = bool(validation.get("ok"))
    if not result["ok"]:
        result["error"] = "; ".join(str(item) for item in validation.get("failures", []))
    if compact_output:
        shutil.rmtree(profile_dir, ignore_errors=True)
        shutil.rmtree(home_dir, ignore_errors=True)
    return result


def no_marionette_fingerprint_page() -> str:
    return r"""<!doctype html>
<meta charset="utf-8">
<style>
html, body { margin: 0; background: #fff; }
canvas { display: block; image-rendering: pixelated; }
</style>
<canvas id="fingerprint"></canvas>
<script>
const nav = navigator;
const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || null;
const snapshot = {
  userAgent: nav.userAgent || null,
  platform: nav.platform || null,
  oscpu: nav.oscpu || null,
  language: nav.language || null,
  languages: Array.isArray(nav.languages) ? Array.from(nav.languages) : [],
  hardwareConcurrency:
    Number.isFinite(nav.hardwareConcurrency) ? nav.hardwareConcurrency : null,
  maxTouchPoints:
    Number.isFinite(nav.maxTouchPoints) ? nav.maxTouchPoints : null,
  webdriver: nav.webdriver === true,
  doNotTrack: nav.doNotTrack ?? null,
  cookieEnabled: nav.cookieEnabled ?? null,
  timezone,
  timezoneOffset: new Date().getTimezoneOffset(),
  colorDepth: screen.colorDepth ?? null,
  pixelDepth: screen.pixelDepth ?? null,
  innerWidth: window.innerWidth ?? null,
  innerHeight: window.innerHeight ?? null,
  outerWidth: window.outerWidth ?? null,
  outerHeight: window.outerHeight ?? null,
  screenWidth: screen.width ?? null,
  screenHeight: screen.height ?? null,
  availWidth: screen.availWidth ?? null,
  availHeight: screen.availHeight ?? null,
  devicePixelRatio:
    Number.isFinite(window.devicePixelRatio) ? window.devicePixelRatio : null,
  reducedMotion: window.matchMedia("(prefers-reduced-motion: reduce)").matches,
  forcedColors: window.matchMedia("(forced-colors: active)").matches,
  darkScheme: window.matchMedia("(prefers-color-scheme: dark)").matches,
  pluginsLength: nav.plugins ? nav.plugins.length : null,
  mimeTypesLength: nav.mimeTypes ? nav.mimeTypes.length : null,
};
const payload = new TextEncoder().encode(JSON.stringify(snapshot));
const bytes = [
  84, 66, 70, 49,
  payload.length & 255,
  (payload.length >> 8) & 255,
  (payload.length >> 16) & 255,
  (payload.length >> 24) & 255,
  ...payload,
];
const cols = 64;
const cell = 8;
const rows = Math.ceil(bytes.length / cols);
const canvas = document.getElementById("fingerprint");
canvas.width = cols * cell;
canvas.height = rows * cell;
canvas.style.width = `${cols * cell}px`;
canvas.style.height = `${rows * cell}px`;
const ctx = canvas.getContext("2d");
ctx.fillStyle = "rgb(255,255,255)";
ctx.fillRect(0, 0, canvas.width, canvas.height);
for (let i = 0; i < bytes.length; i += 1) {
  const value = bytes[i];
  const x = (i % cols) * cell;
  const y = Math.floor(i / cols) * cell;
  ctx.fillStyle = `rgb(${value},${255 - value},${(value * 73) % 256})`;
  ctx.fillRect(x, y, cell, cell);
}
</script>
"""


def output_tail(output: object, limit: int = 1000) -> str:
    if output is None:
        return ""
    if isinstance(output, bytes):
        return output.decode("utf-8", "replace")[-limit:]
    return str(output)[-limit:]


def decode_no_marionette_fingerprint_png(path: Path) -> dict[str, object]:
    rows, width, height, channels = read_png_rows(path)
    for scale in (1, 2):
        try:
            payload = decode_pixel_payload(rows, width, height, channels, scale=scale)
        except ValueError:
            continue
        parsed = json.loads(payload.decode("utf-8"))
        if not isinstance(parsed, dict):
            raise ValueError("decoded fingerprint payload is not a dict")
        return parsed
    raise ValueError("fingerprint pixel payload not found")


def decode_pixel_payload(
    rows: list[bytearray],
    width: int,
    height: int,
    channels: int,
    *,
    scale: int,
) -> bytes:
    cols = 64
    cell = 8 * scale
    header_len = 8
    if width < cols * cell or height < cell:
        raise ValueError("screenshot is too small for fingerprint payload")

    def byte_at(index: int) -> int:
        x = (index % cols) * cell + cell // 2
        y = (index // cols) * cell + cell // 2
        if y >= height or x >= width:
            raise ValueError("fingerprint payload extends outside screenshot")
        return rows[y][x * channels]

    header = bytes(byte_at(index) for index in range(header_len))
    if header[:4] != b"TBF1":
        raise ValueError("fingerprint magic missing")
    payload_len = int.from_bytes(header[4:8], "little")
    if payload_len <= 0 or payload_len > 16_384:
        raise ValueError("fingerprint payload length out of range")
    return bytes(byte_at(index) for index in range(header_len, header_len + payload_len))


def read_png_rows(path: Path) -> tuple[list[bytearray], int, int, int]:
    data = path.read_bytes()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("not a PNG")
    pos = 8
    width = height = bit_depth = color_type = interlace = None
    idat_chunks: list[bytes] = []
    while pos < len(data):
        length = struct.unpack(">I", data[pos : pos + 4])[0]
        kind = data[pos + 4 : pos + 8]
        chunk = data[pos + 8 : pos + 8 + length]
        pos += 12 + length
        if kind == b"IHDR":
            (
                width,
                height,
                bit_depth,
                color_type,
                _compression,
                _filter,
                interlace,
            ) = struct.unpack(">IIBBBBB", chunk)
        elif kind == b"IDAT":
            idat_chunks.append(chunk)
        elif kind == b"IEND":
            break
    if not isinstance(width, int) or not isinstance(height, int):
        raise ValueError("PNG header missing")
    if bit_depth != 8 or color_type not in (2, 6) or interlace != 0:
        raise ValueError("unsupported PNG format")
    channels = 3 if color_type == 2 else 4
    raw = zlib.decompress(b"".join(idat_chunks))
    stride = width * channels
    rows: list[bytearray] = []
    previous = bytearray(stride)
    pos = 0
    for _y in range(height):
        filter_type = raw[pos]
        pos += 1
        row = bytearray(raw[pos : pos + stride])
        pos += stride
        apply_png_filter(row, previous, channels, filter_type)
        rows.append(row)
        previous = row
    return rows, width, height, channels


def apply_png_filter(
    row: bytearray, previous: bytearray, channels: int, filter_type: int
) -> None:
    for index in range(len(row)):
        left = row[index - channels] if index >= channels else 0
        up = previous[index]
        upper_left = previous[index - channels] if index >= channels else 0
        if filter_type == 0:
            continue
        if filter_type == 1:
            row[index] = (row[index] + left) & 255
        elif filter_type == 2:
            row[index] = (row[index] + up) & 255
        elif filter_type == 3:
            row[index] = (row[index] + ((left + up) // 2)) & 255
        elif filter_type == 4:
            row[index] = (row[index] + paeth_predictor(left, up, upper_left)) & 255
        else:
            raise ValueError(f"unsupported PNG filter {filter_type}")


def paeth_predictor(left: int, up: int, upper_left: int) -> int:
    estimate = left + up - upper_left
    left_distance = abs(estimate - left)
    up_distance = abs(estimate - up)
    upper_left_distance = abs(estimate - upper_left)
    if left_distance <= up_distance and left_distance <= upper_left_distance:
        return left
    if up_distance <= upper_left_distance:
        return up
    return upper_left


def validate_browser_fingerprint_snapshot(
    snapshot_audit: dict[str, object],
    *,
    allow_webdriver_artifact: bool = False,
) -> dict[str, object]:
    failures: list[str] = []
    if not snapshot_audit.get("ok"):
        failures.append(
            str(snapshot_audit.get("error", "browser fingerprint snapshot missing"))
        )
        return {"ok": False, "failures": failures}
    snapshot = snapshot_audit.get("snapshot", {})
    if not isinstance(snapshot, dict):
        return {"ok": False, "failures": ["browser fingerprint snapshot is not a dict"]}
    if snapshot.get("webdriver") is True and not allow_webdriver_artifact:
        failures.append("navigator.webdriver: expected False, got True")
    if snapshot.get("timezoneOffset") != 0:
        failures.append(
            f"timezoneOffset: expected 0, got {snapshot.get('timezoneOffset')!r}"
        )
    timezone = snapshot.get("timezone")
    if timezone not in ZERO_OFFSET_TIMEZONES:
        failures.append(
            "timezone: expected a zero-offset Tor Browser zone, "
            f"got {timezone!r}"
        )
    return {"ok": not failures, "failures": failures}


def parse_pref_value(raw: str) -> object:
    raw = raw.strip()
    if raw == "true":
        return True
    if raw == "false":
        return False
    if raw.startswith('"') and raw.endswith('"'):
        return raw[1:-1]
    try:
        return int(raw)
    except ValueError:
        return raw


def png_info(path: Path) -> dict[str, object]:
    if not path.exists():
        return {"path": str(path), "exists": False, "bytes": 0}
    size = path.stat().st_size
    width = None
    height = None
    try:
        data = path.read_bytes()[:24]
        if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
            width = int.from_bytes(data[16:20], "big")
            height = int.from_bytes(data[20:24], "big")
    except OSError:
        pass
    return {
        "path": str(path),
        "exists": True,
        "bytes": size,
        "width": width,
        "height": height,
    }


def browser_net_log_env(log_path: Path) -> dict[str, str]:
    return {
        "MOZ_LOG": BROWSER_NET_MOZ_LOG,
        "MOZ_LOG_FILE": str(log_path.resolve()),
    }


def browser_net_log_files(log_path: Path) -> list[Path]:
    files: list[Path] = []
    if log_path.exists() and log_path.is_file():
        files.append(log_path)
    if log_path.parent.exists():
        for candidate in sorted(log_path.parent.glob(f"{log_path.name}*")):
            if candidate.is_file() and candidate not in files:
                files.append(candidate)
    return files


def summarize_browser_net_log(log_path: Path, *, enabled: bool) -> dict[str, object]:
    if not enabled:
        return {"enabled": False}

    files = browser_net_log_files(log_path)
    errors: list[str] = []
    total_bytes = 0
    line_count = 0
    tail: list[str] = []
    for path in files:
        try:
            total_bytes += path.stat().st_size
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    line_count += 1
                    tail.append(line.rstrip())
                    if len(tail) > BROWSER_NET_LOG_TAIL_LINES:
                        tail = tail[-BROWSER_NET_LOG_TAIL_LINES:]
        except OSError as exc:
            errors.append(f"{path}: {exc}")

    return {
        "enabled": True,
        "ok": bool(files) and not errors,
        "moz_log": BROWSER_NET_MOZ_LOG,
        "path": str(log_path),
        "files": [str(path) for path in files],
        "bytes": total_bytes,
        "line_count": line_count,
        "tail": tail,
        "errors": errors,
    }


def read_lines(proc: subprocess.Popen[str], lines: queue.Queue[str]) -> None:
    assert proc.stdout is not None
    for line in proc.stdout:
        lines.put(line.rstrip())


def wait_for_line(
    proc: subprocess.Popen[str],
    lines: queue.Queue[str],
    *,
    timeout: float,
    ready_text: str,
    process_name: str,
) -> dict[str, object]:
    started = time.monotonic()
    seen: list[str] = []
    while time.monotonic() - started < timeout:
        if proc.poll() is not None:
            return {
                "ok": False,
                "error": f"{process_name} exited with code {proc.returncode}",
                "lines": seen[-80:],
                "signal_lines": boot_signal_lines(seen),
            }
        try:
            line = lines.get(timeout=PROCESS_POLL_INTERVAL_SECONDS)
        except queue.Empty:
            continue
        seen.append(line)
        if ready_text in line:
            ready_monotonic = time.monotonic()
            return {
                "ok": True,
                "seconds": round(ready_monotonic - started, 3),
                "ready_epoch_ms": round(time.time() * 1000, 3),
                "ready_monotonic_seconds": round(ready_monotonic, 6),
                "lines": seen[-80:],
                "signal_lines": boot_signal_lines(seen),
            }
    return {
        "ok": False,
        "error": "bootstrap timeout",
        "lines": seen[-80:],
        "signal_lines": boot_signal_lines(seen),
    }


def stop_process(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=10.0)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=10.0)


def stop_process_tree(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        proc.wait(timeout=10.0)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.wait(timeout=10.0)


def port_is_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.2):
            return True
    except OSError:
        return False


def drain_queue(lines: queue.Queue[str]) -> list[str]:
    drained: list[str] = []
    while True:
        try:
            drained.append(lines.get_nowait())
        except queue.Empty:
            return drained


def summarize_browser(results: list[dict[str, object]]) -> dict[str, object]:
    ok_results = [result for result in results if result["ok"]]
    if not ok_results:
        return {"ok": False, "successes": 0, "failures": len(results)}
    load_results = [
        result["load_ms"] for result in ok_results if result.get("load_ms") is not None
    ]
    summary = {
        "ok": len(ok_results) == len(results),
        "successes": len(ok_results),
        "failures": len(results) - len(ok_results),
        "median_elapsed_ms": median(result["elapsed_ms"] for result in ok_results),
        "median_load_ms": median(load_results) if load_results else None,
        "median_screenshot_bytes": median(
            result["screenshot"]["bytes"] for result in ok_results
        ),
    }
    summary.update(summarize_performance_timing(ok_results))
    return summary


def summarize_performance_timing(results: list[dict[str, object]]) -> dict[str, object]:
    navs = []
    resource_counts = []
    slowest = []
    for result in results:
        timing = result.get("performance_timing")
        if not isinstance(timing, dict) or timing.get("error"):
            continue
        nav = timing.get("navigation")
        if isinstance(nav, dict):
            navs.append(nav)
        resource_count = timing.get("resource_count")
        if isinstance(resource_count, int):
            resource_counts.append(resource_count)
        resources = timing.get("slowest_resources")
        if isinstance(resources, list):
            durations = [
                resource.get("duration")
                for resource in resources
                if isinstance(resource, dict)
                and isinstance(resource.get("duration"), (int, float))
            ]
            if durations:
                slowest.append(max(durations))

    def nav_median(field: str) -> float | None:
        values = [nav.get(field) for nav in navs if isinstance(nav.get(field), (int, float))]
        return median(values) if values else None

    def nav_phase_median(start_field: str, end_field: str) -> float | None:
        values = []
        for nav in navs:
            start = nav.get(start_field)
            end = nav.get(end_field)
            if isinstance(start, (int, float)) and isinstance(end, (int, float)):
                values.append(end - start)
        return median(values) if values else None

    return {
        "median_nav_response_start_ms": nav_median("responseStart"),
        "median_nav_dom_content_loaded_ms": nav_median("domContentLoadedEventEnd"),
        "median_nav_load_event_ms": nav_median("loadEventEnd"),
        "median_nav_duration_ms": nav_median("duration"),
        "median_nav_response_to_dom_ms": nav_phase_median(
            "responseStart", "domContentLoadedEventEnd"
        ),
        "median_nav_dom_to_load_ms": nav_phase_median(
            "domContentLoadedEventEnd", "loadEventEnd"
        ),
        "median_resource_count": median(resource_counts) if resource_counts else None,
        "median_slowest_resource_ms": median(slowest) if slowest else None,
    }


def median(values: object) -> float:
    return float(statistics.median(values))


def short_summary(payload: dict[str, object]) -> dict[str, object]:
    profiles = payload["profiles"]
    assert isinstance(profiles, dict)
    return {
        name: {
            "cache_mode": data.get("cache_mode", payload.get("cache_mode", "cold")),
            "warmup_boot": data.get("warmup_boot"),
            "boot": data.get("boot", {}),
            "benchmarks": {
                url: bench["summary"]
                for url, bench in data.get("benchmarks", {}).items()
            },
            "skipped": data.get("skipped", False),
        }
        for name, data in profiles.items()
    }


def all_profiles_ok(profiles: dict[str, object]) -> bool:
    ok = True
    for data in profiles.values():
        if data.get("skipped"):
            continue
        warmup = data.get("warmup_boot")
        if isinstance(warmup, dict) and not warmup.get("ok"):
            ok = False
        if not data.get("boot", {}).get("ok"):
            ok = False
            continue
        for bench in data.get("benchmarks", {}).values():
            if not bench.get("summary", {}).get("ok"):
                ok = False
    return ok


def payload_ok(payload: dict[str, object]) -> bool:
    quality = payload.get("browser_quality", {})
    if not isinstance(quality, dict):
        return False
    default_prefs = quality.get("default_prefs", {})
    if not isinstance(default_prefs, dict) or not default_prefs.get("ok"):
        return False
    no_marionette = quality.get("no_marionette_fingerprint", {})
    if not isinstance(no_marionette, dict) or not no_marionette.get("ok"):
        return False
    profiles = payload.get("profiles", {})
    return isinstance(profiles, dict) and all_profiles_ok(profiles)


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:80]


if __name__ == "__main__":
    raise SystemExit(main())
