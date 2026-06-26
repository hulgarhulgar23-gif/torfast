#!/usr/bin/env python3
"""Fair interleaved Conflux A/B for C Tor.

This does not weaken Tor. It only changes official client options:
`ConfluxEnabled` and `ConfluxClientUX`. Path rules, hop count, guard use, exit
policy, and DNS handling are unchanged. Conflux is a standard Tor feature that
links two normal 3-hop circuits, so privacy stays the same.

Why a new tool: `run_tor_matrix.py` runs each profile to completion one after
another, so the network window differs between profiles. Conflux benefit is
small and easily hidden by that drift. This harness boots every profile at the
same time, warms them, then fetches round-robin so the same network variance
hits every profile. Each fetch records connect / first-byte / total time.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import queue
import shutil
import statistics
import subprocess
import sys
import threading
import time

from bench_http import fetch


# Profiles. "stock" is exactly what Tor Browser ships today (ConfluxEnabled
# auto, default UX). The others force conflux on and pick an official UX mode.
PROFILES = [
    {"name": "stock", "port": 19060, "enabled": "auto", "ux": None},
    {"name": "noconflux", "port": 19061, "enabled": "0", "ux": None},
    {"name": "latency", "port": 19062, "enabled": "1", "ux": "latency"},
    {"name": "throughput", "port": 19063, "enabled": "1", "ux": "throughput"},
]

DEFAULT_URLS = [
    "https://check.torproject.org/",
    "https://www.torproject.org/",
]

# A CDN endpoint that returns exactly N bytes. Used for bulk-throughput tests,
# where Conflux throughput UX is supposed to help. This does not weaken Tor; it
# is just a large, fixed-size object so multipath transfer can be measured.
BULK_URL_TEMPLATE = "https://speed.cloudflare.com/__down?bytes={bytes}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tor-bin",
        default=None,
        help="Tor binary. Defaults to PATH tor, then upstream/tor/src/app/tor.",
    )
    parser.add_argument("--runs", type=int, default=8, help="interleaved rounds")
    parser.add_argument("--warmup", type=int, default=3, help="warmup fetches per profile")
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--max-bytes", type=int, default=2_000_000)
    parser.add_argument(
        "--bulk-bytes",
        type=int,
        default=None,
        help=(
            "If set, add a fixed-size CDN bulk download of this many bytes and "
            "raise --max-bytes/--timeout to fit it. Use this to measure Conflux "
            "throughput UX, which only helps sustained transfer, not small pages."
        ),
    )
    parser.add_argument("--boot-timeout", type=float, default=180.0)
    parser.add_argument(
        "--only",
        default=None,
        help="comma list of profile names to run (default: all)",
    )
    parser.add_argument(
        "--urls",
        nargs="+",
        default=DEFAULT_URLS,
        help="target URLs to fetch",
    )
    args = parser.parse_args()

    if args.bulk_bytes:
        bulk_url = BULK_URL_TEMPLATE.format(bytes=args.bulk_bytes)
        if bulk_url not in args.urls:
            args.urls = list(args.urls) + [bulk_url]
        # Make sure we actually read the whole object and allow time for it.
        args.max_bytes = max(args.max_bytes, args.bulk_bytes)
        args.timeout = max(args.timeout, 180.0)

    tor_bin = find_tor(args.tor_bin)
    if not tor_bin:
        print("tor not found. Build C Tor or pass --tor-bin.", file=sys.stderr)
        return 2

    profiles = PROFILES
    if args.only:
        wanted = {name.strip() for name in args.only.split(",") if name.strip()}
        profiles = [p for p in PROFILES if p["name"] in wanted]
        if not profiles:
            print(f"no profiles match --only {args.only}", file=sys.stderr)
            return 2

    run_id = time.strftime("%Y%m%dT%H%M%S")
    output_dir = Path("results") / f"conflux-compare-{run_id}"
    output_dir.mkdir(parents=True, exist_ok=True)

    instances: list[TorInstance] = []
    try:
        # Boot every profile at the same time.
        for profile in profiles:
            inst = TorInstance(tor_bin, profile, output_dir)
            inst.start()
            instances.append(inst)

        print(f"booting {len(instances)} profiles concurrently ...", flush=True)
        for inst in instances:
            inst.wait_bootstrap(args.boot_timeout)
            state = "ok" if inst.boot.get("ok") else "FAILED"
            print(
                f"  {inst.name:11s} boot {state} "
                f"{inst.boot.get('seconds', '?')}s conflux={inst.conflux_summary()}",
                flush=True,
            )

        live = [inst for inst in instances if inst.boot.get("ok")]
        if not live:
            print("no profile bootstrapped; aborting", file=sys.stderr)
            return 1

        socks = {inst.name: ("127.0.0.1", inst.port) for inst in live}

        # Warm each profile so conflux sets and circuits are pre-built before we
        # start the measured, interleaved rounds.
        if args.warmup:
            print(f"warming {args.warmup} fetches/profile ...", flush=True)
            for url in args.urls:
                for _ in range(args.warmup):
                    for inst in live:
                        fetch(url, socks=socks[inst.name], timeout=args.timeout, max_bytes=args.max_bytes)

        # Measured rounds: round-robin, rotating profile order each round so no
        # profile is always first.
        records: dict[str, dict[str, list]] = {
            inst.name: {url: [] for url in args.urls} for inst in live
        }
        print(f"measuring {args.runs} interleaved rounds ...", flush=True)
        for round_index in range(args.runs):
            order = live[round_index % len(live):] + live[: round_index % len(live)]
            for url in args.urls:
                for inst in order:
                    result = fetch(url, socks=socks[inst.name], timeout=args.timeout, max_bytes=args.max_bytes)
                    records[inst.name][url].append(result)
            print(f"  round {round_index + 1}/{args.runs} done", flush=True)

        payload = build_payload(run_id, tor_bin, args, live, records)
        out_path = output_dir / "conflux-compare.json"
        out_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        print(f"\nwrote {out_path}")
        print_report(payload)
        return 0
    finally:
        for inst in instances:
            inst.stop()


def build_payload(run_id, tor_bin, args, live, records) -> dict:
    profiles_out: dict[str, object] = {}
    for inst in live:
        url_stats = {}
        for url in args.urls:
            runs = records[inst.name][url]
            url_stats[url] = {
                "runs": [asdict(r) for r in runs],
                "stats": stat_block(runs),
            }
        profiles_out[inst.name] = {
            "port": inst.port,
            "enabled": inst.profile["enabled"],
            "ux": inst.profile["ux"],
            "boot_seconds": inst.boot.get("seconds"),
            "conflux_evidence": inst.conflux_lines,
            "urls": url_stats,
        }
    return {
        "run_id": run_id,
        "tor_bin": tor_bin,
        "runs": args.runs,
        "warmup": args.warmup,
        "urls": args.urls,
        "profiles": profiles_out,
    }


def stat_block(runs) -> dict[str, object]:
    ok = [r for r in runs if r.ok]
    if not ok:
        return {"ok": False, "successes": 0, "failures": len(runs)}

    def pct(values, p):
        s = sorted(values)
        if not s:
            return None
        k = max(0, min(len(s) - 1, int(round((p / 100.0) * (len(s) - 1)))))
        return round(s[k], 3)

    totals = [r.total_ms for r in ok]
    fbs = [r.first_byte_ms for r in ok]

    # Transfer-phase throughput: only the body-download part, after first byte.
    # This is where Conflux throughput UX is supposed to help. Megabits/sec.
    def transfer_mbps(r) -> float | None:
        transfer_ms = r.total_ms - r.first_byte_ms
        if transfer_ms <= 1.0 or r.bytes_read <= 0:
            return None
        return (r.bytes_read * 8.0) / 1000.0 / transfer_ms

    mbps = [v for v in (transfer_mbps(r) for r in ok) if v is not None]
    return {
        "ok": len(ok) == len(runs),
        "successes": len(ok),
        "failures": len(runs) - len(ok),
        "median_first_byte_ms": round(statistics.median(fbs), 3),
        "median_total_ms": round(statistics.median(totals), 3),
        "p90_total_ms": pct(totals, 90),
        "min_total_ms": round(min(totals), 3),
        "max_total_ms": round(max(totals), 3),
        "median_bytes_read": int(statistics.median([r.bytes_read for r in ok])),
        "median_transfer_mbps": round(statistics.median(mbps), 3) if mbps else None,
        "max_transfer_mbps": round(max(mbps), 3) if mbps else None,
    }


def print_report(payload: dict) -> None:
    print("\n=== Conflux interleaved compare ===")
    for url in payload["urls"]:
        print(f"\n# {url}")
        header = (
            f"{'profile':12s} {'ok':>5s} {'med_fb':>9s} {'med_tot':>9s} "
            f"{'p90_tot':>9s} {'min_tot':>9s} {'bytes':>9s} {'xfer_mbps':>10s}"
        )
        print(header)
        rows = []
        for name, data in payload["profiles"].items():
            st = data["urls"][url]["stats"]
            if not st.get("ok") and not st.get("successes"):
                print(f"{name:12s} {'0':>5s}")
                continue
            rows.append((name, st))
            mbps = st.get("median_transfer_mbps")
            mbps_text = f"{mbps:>10.2f}" if mbps is not None else f"{'-':>10s}"
            print(
                f"{name:12s} {st['successes']:>5d} "
                f"{st['median_first_byte_ms']:>9.1f} {st['median_total_ms']:>9.1f} "
                f"{st['p90_total_ms']:>9.1f} {st['min_total_ms']:>9.1f} "
                f"{st['median_bytes_read']:>9d} {mbps_text}"
            )
        # For bulk objects, throughput is the real signal; show the best.
        mbps_rows = [(n, st) for n, st in rows if st.get("median_transfer_mbps")]
        if mbps_rows:
            best_mbps = max(mbps_rows, key=lambda kv: kv[1]["median_transfer_mbps"])
            stock_mbps = next((st for n, st in mbps_rows if n == "stock"), None)
            line = (
                f"  -> best median transfer: {best_mbps[0]} "
                f"({best_mbps[1]['median_transfer_mbps']:.2f} Mbps)"
            )
            if stock_mbps is not None and best_mbps[0] != "stock":
                delta = best_mbps[1]["median_transfer_mbps"] - stock_mbps["median_transfer_mbps"]
                line += f"  ({delta:+.2f} Mbps vs stock)"
            print(line)
        # Highlight best median total.
        if rows:
            best = min(rows, key=lambda kv: kv[1]["median_total_ms"])
            stock = next((st for n, st in rows if n == "stock"), None)
            line = f"  -> best median total: {best[0]} ({best[1]['median_total_ms']:.1f} ms)"
            if stock is not None and best[0] != "stock":
                delta = stock["median_total_ms"] - best[1]["median_total_ms"]
                line += f"  ({delta:+.1f} ms vs stock)"
            print(line)


def find_tor(value: str | None) -> str | None:
    if value:
        path = Path(value).resolve()
        return str(path) if path.exists() else None
    path_tor = shutil.which("tor")
    if path_tor:
        return path_tor
    local_tor = Path("upstream/tor/src/app/tor").resolve()
    if local_tor.exists():
        return str(local_tor)
    return None


class TorInstance:
    def __init__(self, tor_bin: str, profile: dict, output_dir: Path) -> None:
        self.tor_bin = tor_bin
        self.profile = profile
        self.name = str(profile["name"])
        self.port = int(profile["port"])
        self.dir = output_dir / self.name
        self.dir.mkdir(parents=True, exist_ok=True)
        self.proc: subprocess.Popen[str] | None = None
        self.lines: queue.Queue[str] = queue.Queue()
        self.boot: dict[str, object] = {"ok": False}
        self.conflux_lines: list[str] = []
        self._seen: list[str] = []

    def render_torrc(self) -> str:
        data_dir = self.dir / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        lines = [
            f"SocksPort 127.0.0.1:{self.port}",
            f"DataDirectory {data_dir}",
            "ClientOnly 1",
            "AvoidDiskWrites 1",
            "SafeLogging 1",
            "Log notice stdout",
            f"ConfluxEnabled {self.profile['enabled']}",
        ]
        if self.profile["ux"]:
            lines.append(f"ConfluxClientUX {self.profile['ux']}")
        return "\n".join(lines) + "\n"

    def start(self) -> None:
        torrc = self.dir / "torrc"
        torrc.write_text(self.render_torrc())
        self.proc = subprocess.Popen(
            [self.tor_bin, "-f", str(torrc)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self) -> None:
        assert self.proc is not None and self.proc.stdout is not None
        for line in self.proc.stdout:
            self.lines.put(line.rstrip())

    def wait_bootstrap(self, timeout: float) -> None:
        started = time.monotonic()
        while time.monotonic() - started < timeout:
            if self.proc is not None and self.proc.poll() is not None:
                self.boot = {"ok": False, "error": f"exit {self.proc.returncode}", "lines": self._seen[-30:]}
                return
            try:
                line = self.lines.get(timeout=0.25)
            except queue.Empty:
                continue
            self._seen.append(line)
            if "onflux" in line:  # Conflux / conflux
                self.conflux_lines.append(line)
            if "Bootstrapped 100%" in line:
                self.boot = {"ok": True, "seconds": round(time.monotonic() - started, 3)}
                return
        self.boot = {"ok": False, "error": "boot timeout", "lines": self._seen[-30:]}

    def conflux_summary(self) -> str:
        return str(len(self.conflux_lines))

    def stop(self) -> None:
        # Drain any late conflux evidence.
        while True:
            try:
                line = self.lines.get_nowait()
            except queue.Empty:
                break
            if "onflux" in line:
                self.conflux_lines.append(line)
        if self.proc is None or self.proc.poll() is not None:
            return
        self.proc.terminate()
        try:
            self.proc.wait(timeout=10.0)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(timeout=10.0)


if __name__ == "__main__":
    raise SystemExit(main())
