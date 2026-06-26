#!/usr/bin/env python3
"""Measure HTTP/HTTPS timing direct or through a SOCKS5 proxy.

This tool has no third-party dependencies. For Tor, pass a local SOCKS address,
for example: --socks 127.0.0.1:9050
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import socket
import ssl
import statistics
import sys
import time
from typing import BinaryIO
from urllib.parse import urlparse


@dataclass
class FetchResult:
    mode: str
    url: str
    ok: bool
    status_line: str
    connect_ms: float
    tls_ms: float
    first_byte_ms: float
    total_ms: float
    bytes_read: int
    error: str | None = None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--max-bytes", type=int, default=2_000_000)
    parser.add_argument("--socks", help="host:port for SOCKS5 proxy")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    parsed = urlparse(args.url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        print("Only http:// and https:// URLs are supported.", file=sys.stderr)
        return 2

    socks = parse_socks(args.socks) if args.socks else None
    mode = "socks" if socks else "direct"
    results = [
        fetch(args.url, socks=socks, timeout=args.timeout, max_bytes=args.max_bytes)
        for _ in range(args.runs)
    ]

    payload = {
        "mode": mode,
        "url": args.url,
        "runs": [asdict(result) for result in results],
        "summary": summarize(results),
    }

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print_human(payload)

    return 0 if all(result.ok for result in results) else 1


def fetch(
    url: str, *, socks: tuple[str, int] | None, timeout: float, max_bytes: int
) -> FetchResult:
    parsed = urlparse(url)
    assert parsed.hostname is not None
    host = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    target = parsed.path or "/"
    if parsed.query:
        target += "?" + parsed.query
    mode = "socks" if socks else "direct"

    started = time.perf_counter()
    connect_ms = 0.0
    tls_ms = 0.0
    first_byte_ms = 0.0
    total_ms = 0.0
    bytes_read = 0
    status_line = ""

    try:
        if socks:
            raw_sock = open_socks5(host, port, socks_host=socks[0], socks_port=socks[1], timeout=timeout)
        else:
            raw_sock = socket.create_connection((host, port), timeout=timeout)
        raw_sock.settimeout(timeout)
        connect_ms = elapsed_ms(started)

        stream: socket.socket | ssl.SSLSocket = raw_sock
        if parsed.scheme == "https":
            tls_started = time.perf_counter()
            context = ssl.create_default_context()
            stream = context.wrap_socket(raw_sock, server_hostname=host)
            tls_ms = elapsed_ms(tls_started)

        request = (
            f"GET {target} HTTP/1.1\r\n"
            f"Host: {host}\r\n"
            "User-Agent: torfast-bench/0\r\n"
            "Accept: */*\r\n"
            "Connection: close\r\n\r\n"
        ).encode("ascii")

        stream.sendall(request)
        file = stream.makefile("rb")
        first = file.readline()
        first_byte_ms = elapsed_ms(started)
        status_line = first.decode("iso-8859-1", errors="replace").strip()
        bytes_read += len(first)
        bytes_read += drain(file, max_bytes=max_bytes - bytes_read)
        total_ms = elapsed_ms(started)
        stream.close()

        return FetchResult(
            mode=mode,
            url=url,
            ok=status_line.startswith("HTTP/"),
            status_line=status_line,
            connect_ms=connect_ms,
            tls_ms=tls_ms,
            first_byte_ms=first_byte_ms,
            total_ms=total_ms,
            bytes_read=bytes_read,
        )
    except Exception as exc:  # noqa: BLE001 - this is a CLI, return the error.
        total_ms = elapsed_ms(started)
        return FetchResult(
            mode=mode,
            url=url,
            ok=False,
            status_line=status_line,
            connect_ms=connect_ms,
            tls_ms=tls_ms,
            first_byte_ms=first_byte_ms,
            total_ms=total_ms,
            bytes_read=bytes_read,
            error=f"{type(exc).__name__}: {exc}",
        )


def open_socks5(
    host: str, port: int, *, socks_host: str, socks_port: int, timeout: float
) -> socket.socket:
    sock = socket.create_connection((socks_host, socks_port), timeout=timeout)
    sock.settimeout(timeout)

    sock.sendall(b"\x05\x01\x00")
    version, method = recv_exact(sock, 2)
    if version != 5 or method != 0:
        sock.close()
        raise OSError("SOCKS5 proxy did not accept no-auth mode")

    host_bytes = host.encode("idna")
    if len(host_bytes) > 255:
        sock.close()
        raise ValueError("host name is too long for SOCKS5")

    request = (
        b"\x05\x01\x00\x03"
        + bytes([len(host_bytes)])
        + host_bytes
        + port.to_bytes(2, "big")
    )
    sock.sendall(request)

    version, reply, _reserved, address_type = recv_exact(sock, 4)
    if version != 5:
        sock.close()
        raise OSError("bad SOCKS5 response version")
    if reply != 0:
        sock.close()
        raise OSError(f"SOCKS5 connect failed with code {reply}")

    if address_type == 1:
        recv_exact(sock, 4)
    elif address_type == 3:
        size = recv_exact(sock, 1)[0]
        recv_exact(sock, size)
    elif address_type == 4:
        recv_exact(sock, 16)
    else:
        sock.close()
        raise OSError("bad SOCKS5 address type")
    recv_exact(sock, 2)
    return sock


def recv_exact(sock: socket.socket, size: int) -> bytes:
    data = b""
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            raise OSError("connection closed early")
        data += chunk
    return data


def drain(file: BinaryIO, *, max_bytes: int) -> int:
    total = 0
    while total < max_bytes:
        chunk = file.read(min(64 * 1024, max_bytes - total))
        if not chunk:
            break
        total += len(chunk)
    return total


def parse_socks(value: str) -> tuple[str, int]:
    host, sep, port_text = value.rpartition(":")
    if not sep or not host:
        raise argparse.ArgumentTypeError("SOCKS value must be host:port")
    return host, int(port_text)


def summarize(results: list[FetchResult]) -> dict[str, object]:
    ok_results = [result for result in results if result.ok]
    if not ok_results:
        return {"ok": False, "successes": 0, "failures": len(results)}
    return {
        "ok": len(ok_results) == len(results),
        "successes": len(ok_results),
        "failures": len(results) - len(ok_results),
        "median_connect_ms": median(result.connect_ms for result in ok_results),
        "median_tls_ms": median(result.tls_ms for result in ok_results),
        "median_first_byte_ms": median(result.first_byte_ms for result in ok_results),
        "median_total_ms": median(result.total_ms for result in ok_results),
        "median_bytes_read": median(result.bytes_read for result in ok_results),
    }


def median(values) -> float:
    return float(statistics.median(values))


def elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 3)


def print_human(payload: dict[str, object]) -> None:
    print(f"mode: {payload['mode']}")
    print(f"url: {payload['url']}")
    print(json.dumps(payload["summary"], indent=2, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
