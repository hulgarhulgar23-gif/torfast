#!/usr/bin/env python3
"""Check observable C Tor circuit quality through the control port."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import ipaddress
import json
from pathlib import Path
import queue
import re
import socket
import subprocess
import sys
import threading
import time

from bench_http import fetch


TARGET = "https://check.torproject.org/"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tor-bin", default="upstream/tor/src/app/tor")
    parser.add_argument("--target", default=TARGET)
    parser.add_argument("--socks-port", type=int, default=19110)
    parser.add_argument("--control-port", type=int, default=19111)
    args = parser.parse_args()

    tor_bin = Path(args.tor_bin).resolve()
    if not tor_bin.exists():
        print(f"tor binary not found: {tor_bin}", file=sys.stderr)
        return 2

    run_id = time.strftime("%Y%m%dT%H%M%S")
    output_dir = Path("results") / f"circuit-check-{run_id}"
    output_dir.mkdir(parents=True, exist_ok=True)

    payload = run_check(
        tor_bin=tor_bin,
        target=args.target,
        socks_port=args.socks_port,
        control_port=args.control_port,
        output_dir=output_dir,
    )
    output_path = output_dir / "c-tor-circuits.json"
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"wrote {output_path}")
    print(json.dumps(short_summary(payload), indent=2, sort_keys=True))
    return 0 if payload["ok"] else 1


def run_check(
    *,
    tor_bin: Path,
    target: str,
    socks_port: int,
    control_port: int,
    output_dir: Path,
) -> dict[str, object]:
    data_dir = output_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    cookie_path = output_dir / "control_auth_cookie"
    torrc = output_dir / "torrc"
    torrc.write_text(
        "\n".join(
            [
                f"SocksPort 127.0.0.1:{socks_port}",
                f"ControlPort 127.0.0.1:{control_port}",
                "CookieAuthentication 1",
                f"CookieAuthFile {cookie_path.resolve()}",
                f"DataDirectory {data_dir.resolve()}",
                "ClientOnly 1",
                "AvoidDiskWrites 1",
                "SafeLogging 1",
                "Log notice stdout",
                "ConfluxEnabled auto",
            ]
        )
        + "\n"
    )

    proc = subprocess.Popen(
        [str(tor_bin), "-f", str(torrc)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    lines: queue.Queue[str] = queue.Queue()
    threading.Thread(target=read_lines, args=(proc, lines), daemon=True).start()
    try:
        boot = wait_for_line(
            proc,
            lines,
            timeout=180.0,
            ready_text="Bootstrapped 100%",
            process_name="tor",
        )
        payload: dict[str, object] = {
            "target": target,
            "tor_bin": str(tor_bin),
            "boot": boot,
            "fetch": None,
            "circuits": [],
            "checked_circuit_count": 0,
            "ok": False,
        }
        if not boot["ok"]:
            return payload

        fetch_result = fetch(
            target,
            socks=("127.0.0.1", socks_port),
            timeout=60.0,
            max_bytes=2_000_000,
        )
        payload["fetch"] = asdict(fetch_result)

        client = TorControlClient.connect(
            host="127.0.0.1",
            port=control_port,
            cookie_path=cookie_path,
        )
        try:
            circuits = parse_circuits(client.command("GETINFO circuit-status"))
            router_cache: dict[str, dict[str, object]] = {}
            checked = []
            for circuit in circuits:
                if not should_check_circuit(circuit):
                    continue
                for relay in circuit["path"]:
                    fp = relay["fingerprint"]
                    if fp not in router_cache:
                        router_cache[fp] = read_router_info(client, fp)
                    relay.update(router_cache[fp])
                circuit["errors"] = validate_circuit(circuit)
                circuit["ok"] = not circuit["errors"]
                checked.append(circuit)
            payload["circuits"] = checked
            payload["checked_circuit_count"] = len(checked)
            payload["ok"] = (
                fetch_result.ok
                and bool(checked)
                and all(circuit["ok"] for circuit in checked)
            )
            return payload
        finally:
            client.close()
    finally:
        stop_process(proc)


class TorControlClient:
    def __init__(self, sock: socket.socket):
        self.sock = sock

    @classmethod
    def connect(cls, *, host: str, port: int, cookie_path: Path) -> "TorControlClient":
        sock = socket.create_connection((host, port), timeout=10.0)
        sock.settimeout(10.0)
        client = cls(sock)
        cookie = cookie_path.read_bytes().hex()
        client.command(f"AUTHENTICATE {cookie}")
        return client

    def command(self, command: str) -> str:
        self.sock.sendall((command + "\r\n").encode("ascii"))
        data = b""
        while True:
            data += self.sock.recv(65536)
            text = data.decode("utf-8", errors="replace")
            if "\r\n250 OK\r\n" in text or text.startswith("250 ") or text.startswith("5"):
                if text.startswith("5"):
                    raise RuntimeError(text.strip())
                return text

    def close(self) -> None:
        self.sock.close()


def parse_circuits(reply: str) -> list[dict[str, object]]:
    circuits: list[dict[str, object]] = []
    for line in reply.splitlines():
        if not line or line.startswith("250") or line == ".":
            continue
        parts = line.split()
        if len(parts) < 3:
            continue
        circuit_id, status, path_text = parts[:3]
        fields = parse_fields(parts[3:])
        circuits.append(
            {
                "id": circuit_id,
                "status": status,
                "purpose": fields.get("PURPOSE", ""),
                "build_flags": fields.get("BUILD_FLAGS", ""),
                "path": parse_path(path_text),
            }
        )
    return circuits


def parse_fields(parts: list[str]) -> dict[str, str]:
    fields: dict[str, str] = {}
    for part in parts:
        key, sep, value = part.partition("=")
        if sep:
            fields[key] = value
    return fields


def parse_path(path_text: str) -> list[dict[str, object]]:
    relays: list[dict[str, object]] = []
    for relay_text in path_text.split(","):
        match = re.match(r"\$([A-F0-9]{40})(?:~([^,= ]+))?", relay_text)
        if not match:
            continue
        relays.append(
            {
                "fingerprint": match.group(1),
                "name": match.group(2) or "",
            }
        )
    return relays


def should_check_circuit(circuit: dict[str, object]) -> bool:
    return (
        circuit.get("status") == "BUILT"
        and circuit.get("purpose") in {"GENERAL", "CONFLUX_LINKED"}
        and len(circuit.get("path", [])) == 3
    )


def read_router_info(client: TorControlClient, fingerprint: str) -> dict[str, object]:
    ns = client.command(f"GETINFO ns/id/{fingerprint}")
    md = client.command(f"GETINFO md/id/{fingerprint}")
    return {
        "flags": parse_flags(ns),
        "ipv4": parse_ipv4(ns),
        "family": parse_family(md),
    }


def parse_flags(ns_reply: str) -> list[str]:
    for line in ns_reply.splitlines():
        if line.startswith("s "):
            return line.split()[1:]
    return []


def parse_ipv4(ns_reply: str) -> str | None:
    for line in ns_reply.splitlines():
        if line.startswith("r "):
            parts = line.split()
            return parts[6] if len(parts) > 6 else None
    return None


def parse_family(md_reply: str) -> list[str]:
    family: list[str] = []
    for line in md_reply.splitlines():
        if line.startswith("family "):
            family.extend(item.lstrip("$") for item in line.split()[1:])
    return family


def validate_circuit(circuit: dict[str, object]) -> list[str]:
    errors: list[str] = []
    path = circuit.get("path", [])
    if len(path) != 3:
        return ["path_length_must_be_3"]

    fingerprints = [relay["fingerprint"] for relay in path]
    if len(set(fingerprints)) != len(fingerprints):
        errors.append("path_reuses_relay")

    first_flags = set(path[0].get("flags", []))
    if "Guard" not in first_flags:
        errors.append(f"first_hop_must_be_guard:{path[0].get('name', '')}")

    for relay in path:
        flags = set(relay.get("flags", []))
        name = relay.get("name", "")
        for flag in ("Fast", "Running", "Valid"):
            if flag not in flags:
                errors.append(f"relay_missing_{flag}:{name}")

    exit_flags = set(path[-1].get("flags", []))
    if "Exit" not in exit_flags:
        errors.append(f"last_hop_missing_exit_flag:{path[-1].get('name', '')}")

    for index, left in enumerate(path):
        for right in path[index + 1 :]:
            if share_family(left, right):
                errors.append(
                    f"relays_share_family:{left.get('name', '')}:{right.get('name', '')}"
                )
            if share_ipv4_subnet(left.get("ipv4"), right.get("ipv4")):
                errors.append(
                    f"relays_share_ipv4_subnet:{left.get('name', '')}:{right.get('name', '')}"
                )
    return errors


def share_family(left: dict[str, object], right: dict[str, object]) -> bool:
    left_fp = left["fingerprint"]
    right_fp = right["fingerprint"]
    left_family = set(left.get("family", []))
    right_family = set(right.get("family", []))
    return right_fp in left_family or left_fp in right_family or bool(
        left_family.intersection(right_family)
    )


def share_ipv4_subnet(left: object, right: object) -> bool:
    if not isinstance(left, str) or not isinstance(right, str):
        return False
    try:
        left_net = ipaddress.ip_network(f"{left}/16", strict=False)
        right_net = ipaddress.ip_network(f"{right}/16", strict=False)
    except ValueError:
        return False
    return left_net == right_net


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
            }
        try:
            line = lines.get(timeout=0.25)
        except queue.Empty:
            continue
        seen.append(line)
        if ready_text in line:
            return {
                "ok": True,
                "seconds": round(time.monotonic() - started, 3),
                "lines": seen[-80:],
            }
    return {"ok": False, "error": "bootstrap timeout", "lines": seen[-80:]}


def stop_process(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=10.0)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=10.0)


def short_summary(payload: dict[str, object]) -> dict[str, object]:
    return {
        "ok": payload["ok"],
        "boot": payload["boot"],
        "fetch_ok": payload["fetch"]["ok"] if payload.get("fetch") else False,
        "checked_circuit_count": payload["checked_circuit_count"],
        "circuit_errors": {
            circuit["id"]: circuit["errors"]
            for circuit in payload.get("circuits", [])
            if circuit.get("errors")
        },
    }


if __name__ == "__main__":
    raise SystemExit(main())
