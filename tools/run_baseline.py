#!/usr/bin/env python3
"""Run the first repeatable network baseline for this lab."""

from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
import shutil
import socket
import time

from bench_http import fetch, summarize


DEFAULT_URLS = [
    "https://check.torproject.org/",
    "https://www.torproject.org/",
]

SOCKS_PORTS = [
    ("tor_9050", ("127.0.0.1", 9050)),
    ("tor_browser_9150", ("127.0.0.1", 9150)),
    ("arti_19060", ("127.0.0.1", 19060)),
]


def main() -> int:
    results_dir = Path("results")
    results_dir.mkdir(exist_ok=True)

    run_id = time.strftime("%Y%m%dT%H%M%S")
    payload = {
        "run_id": run_id,
        "tools": {
            "tor": shutil.which("tor"),
            "arti": shutil.which("arti"),
        },
        "proxies": {},
        "targets": DEFAULT_URLS,
        "results": {},
    }

    for proxy_name, address in SOCKS_PORTS:
        payload["proxies"][proxy_name] = {
            "address": f"{address[0]}:{address[1]}",
            "open": port_is_open(address),
        }

    for url in DEFAULT_URLS:
        payload["results"][f"direct:{url}"] = run_one(url, socks=None)
        for proxy_name, address in SOCKS_PORTS:
            if payload["proxies"][proxy_name]["open"]:
                payload["results"][f"{proxy_name}:{url}"] = run_one(url, socks=address)

    output_path = results_dir / f"baseline-{run_id}.json"
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")

    print(f"wrote {output_path}")
    print(json.dumps(short_summary(payload), indent=2, sort_keys=True))
    return 0


def run_one(url: str, *, socks: tuple[str, int] | None) -> dict[str, object]:
    runs = [fetch(url, socks=socks, timeout=45.0, max_bytes=2_000_000) for _ in range(3)]
    return {
        "runs": [asdict(run) for run in runs],
        "summary": summarize(runs),
    }


def port_is_open(address: tuple[str, int]) -> bool:
    try:
        with socket.create_connection(address, timeout=0.25):
            return True
    except OSError:
        return False


def short_summary(payload: dict[str, object]) -> dict[str, object]:
    return {
        "tools": payload["tools"],
        "proxies": payload["proxies"],
        "result_summaries": {
            name: value["summary"] for name, value in payload["results"].items()
        },
    }


if __name__ == "__main__":
    raise SystemExit(main())
