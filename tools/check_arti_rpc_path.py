#!/usr/bin/env python3
"""Check Arti runtime paths through experimental RPC.

This needs an Arti binary built with `--features rpc,experimental-api`.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import ipaddress
import json
from pathlib import Path
import queue
import socket
import struct
import subprocess
import sys
import threading
import time
from typing import Any

import check_c_tor_circuits as ctor


TARGET_HOST = "check.torproject.org"
TARGET_PORT = 443


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--arti-bin", default="tmp/arti-rpc/arti")
    parser.add_argument("--socks-port", type=int, default=19130)
    parser.add_argument("--tor-bin", default="upstream/tor/src/app/tor")
    parser.add_argument("--tor-socks-port", type=int, default=19132)
    parser.add_argument("--tor-control-port", type=int, default=19133)
    parser.add_argument("--skip-directory-proof", action="store_true")
    parser.add_argument("--samples", type=int, default=1)
    parser.add_argument("--target-host", default=TARGET_HOST)
    parser.add_argument("--target-port", type=int, default=TARGET_PORT)
    args = parser.parse_args()

    arti_bin = Path(args.arti_bin).resolve()
    if not arti_bin.exists():
        print(f"RPC-enabled arti binary not found: {arti_bin}", file=sys.stderr)
        return 2

    run_id = time.strftime("%Y%m%dT%H%M%S")
    output_dir = Path("results") / f"arti-rpc-path-{run_id}"
    output_dir.mkdir(parents=True, exist_ok=True)

    payload = run_check(
        arti_bin=arti_bin,
        socks_port=args.socks_port,
        tor_bin=None if args.skip_directory_proof else Path(args.tor_bin).resolve(),
        tor_socks_port=args.tor_socks_port,
        tor_control_port=args.tor_control_port,
        samples=args.samples,
        target_host=args.target_host,
        target_port=args.target_port,
        output_dir=output_dir,
    )
    output_path = output_dir / "arti-rpc-path.json"
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"wrote {output_path}")
    print(json.dumps(short_summary(payload), indent=2, sort_keys=True))
    return 0 if payload["ok"] else 1


def run_check(
    *,
    arti_bin: Path,
    socks_port: int,
    tor_bin: Path | None,
    tor_socks_port: int,
    tor_control_port: int,
    samples: int,
    target_host: str,
    target_port: int,
    output_dir: Path,
) -> dict[str, Any]:
    if samples < 1:
        raise ValueError("samples must be at least 1")

    config = write_config(output_dir=output_dir, socks_port=socks_port)
    proc = subprocess.Popen(
        [
            str(arti_bin),
            "proxy",
            "--disable-fs-permission-checks",
            "-l",
            "info",
            "-c",
            str(config.config_path),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    lines: queue.Queue[str] = queue.Queue()
    threading.Thread(target=read_lines, args=(proc, lines), daemon=True).start()

    payload: dict[str, Any] = {
        "ok": False,
        "arti_bin": str(arti_bin),
        "socks_port": socks_port,
        "rpc_socket": str(config.rpc_socket),
        "target": f"{target_host}:{target_port}",
        "sample_count": samples,
        "samples": [],
        "boot": None,
        "path": None,
        "validation": None,
        "directory_validation": None,
        "runtime_path_shape_proof": False,
        "full_runtime_quality_proof": False,
        "limits": [],
    }
    try:
        boot = wait_for_ready(proc, lines, config.rpc_socket, timeout=180.0)
        payload["boot"] = boot
        if not boot["ok"]:
            return payload

        with RpcClient.connect(config.rpc_socket) as rpc:
            session_id = rpc.authenticate()
            sample_payloads = []
            for sample_index in range(samples):
                stream_id = rpc.call(
                    session_id,
                    "arti:new_oneshot_client",
                    {},
                )["id"]
                stream = socks_connect_rpc_stream(
                    host="127.0.0.1",
                    port=socks_port,
                    rpc_object=stream_id,
                    target_host=target_host,
                    target_port=target_port,
                    isolation=f"arti-path-sample-{sample_index}",
                )
                try:
                    path = rpc.call(
                        stream_id,
                        "arti:describe_path",
                        {"include_deprecated_ids": True},
                    )
                finally:
                    stream.close()
                sample_payloads.append(
                    {
                        "index": sample_index,
                        "target": f"{target_host}:{target_port}",
                        "stream_id": stream_id,
                        "path": path,
                        "validation": validate_path_description(path),
                    }
                )

        validation = combine_sample_validations(sample_payloads)
        payload["samples"] = sample_payloads
        payload["path"] = sample_payloads[0]["path"]
        payload["validation"] = validation
        payload["runtime_path_shape_proof"] = True
        if tor_bin is not None and tor_bin.exists():
            directory_validation = validate_with_c_tor_directory(
                tor_bin=tor_bin,
                socks_port=tor_socks_port,
                control_port=tor_control_port,
                output_dir=output_dir,
                validation=validation,
            )
            payload["directory_validation"] = directory_validation
            payload["full_runtime_quality_proof"] = (
                validation["ok"] and directory_validation["ok"]
            )
        payload["ok"] = validation["ok"] and (
            payload["directory_validation"] is None
            or payload["directory_validation"]["ok"]
        )
        return payload
    except Exception as exc:
        payload["error"] = str(exc)
        return payload
    finally:
        stop_process(proc)


@dataclass
class ArtiRpcConfig:
    config_path: Path
    rpc_socket: Path


def write_config(*, output_dir: Path, socks_port: int) -> ArtiRpcConfig:
    cache_dir = (output_dir / "cache").resolve()
    state_dir = (output_dir / "state").resolve()
    rpc_dir = (output_dir / "rpc").resolve()
    for path in (cache_dir, state_dir, rpc_dir):
        path.mkdir(parents=True, exist_ok=True)

    rpc_socket = rpc_dir / "arti_rpc_socket"
    connect_path = output_dir / "rpc-connect.toml"
    connect_path.write_text(
        "\n".join(
            [
                "[connect]",
                f'socket = "unix:{rpc_socket}"',
                'auth = "none"',
            ]
        )
        + "\n"
    )

    config_path = output_dir / "arti-rpc.toml"
    config_path.write_text(
        "\n".join(
            [
                "[storage]",
                f'cache_dir = "{cache_dir}"',
                f'state_dir = "{state_dir}"',
                "",
                "[proxy]",
                f'socks_listen = ["127.0.0.1:{socks_port}"]',
                "",
                "[rpc]",
                "enable = true",
                "",
                '[rpc.listen."local"]',
                f'file = "{connect_path.resolve()}"',
            ]
        )
        + "\n"
    )
    return ArtiRpcConfig(config_path=config_path.resolve(), rpc_socket=rpc_socket)


class RpcClient:
    def __init__(self, sock: socket.socket):
        self.sock = sock
        self.file = sock.makefile("rwb")
        self.next_id = 1

    @classmethod
    def connect(cls, rpc_socket: Path) -> "RpcClient":
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(30.0)
        sock.connect(str(rpc_socket))
        client = cls(sock)
        banner = client._read()
        if "arti_rpc" not in banner:
            raise RuntimeError(f"bad RPC banner: {banner}")
        return client

    def __enter__(self) -> "RpcClient":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def authenticate(self) -> str:
        result = self.call(
            "connection",
            "auth:authenticate",
            {"scheme": "auth:inherent"},
        )
        return result["session"]

    def call(self, obj: str, method: str, params: dict[str, Any]) -> dict[str, Any]:
        request_id = self.next_id
        self.next_id += 1
        request = {
            "id": request_id,
            "obj": obj,
            "method": method,
            "params": params,
        }
        self.file.write(json.dumps(request, separators=(",", ":")).encode("utf-8") + b"\n")
        self.file.flush()
        while True:
            response = self._read()
            if response.get("id") != request_id:
                continue
            if "error" in response:
                raise RuntimeError(json.dumps(response["error"], sort_keys=True))
            if "result" in response:
                return response["result"]

    def _read(self) -> dict[str, Any]:
        line = self.file.readline()
        if not line:
            raise RuntimeError("RPC socket closed")
        return json.loads(line)

    def close(self) -> None:
        self.file.close()
        self.sock.close()


def socks_connect_rpc_stream(
    *,
    host: str,
    port: int,
    rpc_object: str,
    target_host: str,
    target_port: int,
    isolation: str = "",
) -> socket.socket:
    stream = socket.create_connection((host, port), timeout=60.0)
    stream.settimeout(60.0)
    try:
        stream.sendall(b"\x05\x01\x02")
        assert_response(stream.recv(2), b"\x05\x02", "SOCKS auth method")

        username = f"<torS0X>1{rpc_object}".encode("utf-8")
        password = isolation.encode("utf-8")
        if len(username) > 255:
            raise RuntimeError("RPC object id too long for SOCKS username")
        if len(password) > 255:
            raise RuntimeError("SOCKS isolation value too long")
        stream.sendall(b"\x01" + bytes([len(username)]) + username + bytes([len(password)]) + password)
        assert_response(stream.recv(2), b"\x01\x00", "SOCKS username auth")

        host_bytes = target_host.encode("idna")
        if len(host_bytes) > 255:
            raise RuntimeError("target host too long for SOCKS")
        request = (
            b"\x05\x01\x00\x03"
            + bytes([len(host_bytes)])
            + host_bytes
            + struct.pack("!H", target_port)
        )
        stream.sendall(request)
        reply = stream.recv(4)
        if len(reply) != 4 or reply[:2] != b"\x05\x00":
            raise RuntimeError(f"SOCKS connect failed: {reply!r}")
        atyp = reply[3]
        if atyp == 1:
            stream.recv(4)
        elif atyp == 3:
            size = stream.recv(1)[0]
            stream.recv(size)
        elif atyp == 4:
            stream.recv(16)
        else:
            raise RuntimeError(f"bad SOCKS address type: {atyp}")
        stream.recv(2)
        return stream
    except Exception:
        stream.close()
        raise


def assert_response(actual: bytes, expected: bytes, label: str) -> None:
    if actual != expected:
        raise RuntimeError(f"{label} failed: expected {expected!r}, got {actual!r}")


def validate_path_description(path: dict[str, Any]) -> dict[str, Any]:
    path_map = path.get("path")
    errors: list[str] = []
    checked_paths = 0
    if not isinstance(path_map, dict) or not path_map:
        return {"ok": False, "errors": ["path_missing"], "checked_paths": 0}

    normalized_paths = {}
    for path_id, entries in path_map.items():
        checked_paths += 1
        relays = [normalize_entry(entry) for entry in entries]
        normalized_paths[path_id] = relays
        if len(relays) != 3:
            errors.append(f"path_length_not_3:{path_id}:{len(relays)}")
        ids = [relay["id"] for relay in relays if relay["id"]]
        if len(ids) != len(set(ids)):
            errors.append(f"path_reuses_relay:{path_id}")
        ipv4s = [relay["ipv4"] for relay in relays if relay["ipv4"]]
        for left_index, left in enumerate(ipv4s):
            for right in ipv4s[left_index + 1 :]:
                if same_ipv4_16(left, right):
                    errors.append(f"path_reuses_ipv4_16:{path_id}:{left}:{right}")

    return {
        "ok": not errors,
        "errors": errors,
        "checked_paths": checked_paths,
        "paths": normalized_paths,
    }


def combine_sample_validations(samples: list[dict[str, Any]]) -> dict[str, Any]:
    errors: list[str] = []
    paths: dict[str, list[dict[str, Any]]] = {}
    for sample in samples:
        sample_index = sample["index"]
        validation = sample["validation"]
        for error in validation.get("errors", []):
            errors.append(f"sample_{sample_index}:{error}")
        for path_id, relays in validation.get("paths", {}).items():
            paths[f"sample_{sample_index}:{path_id}"] = relays
    return {
        "ok": not errors and bool(paths),
        "errors": errors,
        "checked_paths": len(paths),
        "paths": paths,
    }


def normalize_entry(entry: dict[str, Any]) -> dict[str, Any]:
    relay = entry.get("known_relay") if isinstance(entry, dict) else None
    if not isinstance(relay, dict):
        return {
            "id": None,
            "ed25519": None,
            "rsa": None,
            "fingerprint": None,
            "ipv4": None,
            "addrs": [],
            "kind": "unknown",
        }
    ids = relay.get("ids", {})
    ed25519 = ids.get("ed25519") if isinstance(ids, dict) else None
    rsa = ids.get("rsa") if isinstance(ids, dict) else None
    relay_id = ed25519 or rsa
    addrs = relay.get("addrs", [])
    ipv4 = first_ipv4(addrs)
    return {
        "id": relay_id,
        "ed25519": ed25519,
        "rsa": rsa,
        "fingerprint": rsa.upper() if isinstance(rsa, str) else None,
        "ipv4": ipv4,
        "addrs": addrs,
        "kind": "known_relay",
    }


def validate_with_c_tor_directory(
    *,
    tor_bin: Path,
    socks_port: int,
    control_port: int,
    output_dir: Path,
    validation: dict[str, Any],
) -> dict[str, Any]:
    data_dir = output_dir / "c-tor-directory-data"
    data_dir.mkdir(parents=True, exist_ok=True)
    cookie_path = output_dir / "c-tor-control-cookie"
    torrc = output_dir / "c-tor-directory.torrc"
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
    threading.Thread(target=ctor.read_lines, args=(proc, lines), daemon=True).start()
    try:
        boot = ctor.wait_for_line(
            proc,
            lines,
            timeout=180.0,
            ready_text="Bootstrapped 100%",
            process_name="tor",
        )
        result: dict[str, Any] = {
            "ok": False,
            "boot": boot,
            "checked_paths": 0,
            "errors": [],
            "circuits": {},
        }
        if not boot["ok"]:
            result["errors"] = ["c_tor_directory_boot_failed"]
            return result

        client = ctor.TorControlClient.connect(
            host="127.0.0.1",
            port=control_port,
            cookie_path=cookie_path,
        )
        try:
            errors: list[str] = []
            circuits = {}
            paths = validation.get("paths", {})
            for path_id, relays in paths.items():
                circuit = {"id": path_id, "path": []}
                compact_circuit = {"id": path_id, "path": []}
                for index, relay in enumerate(relays):
                    fingerprint = relay.get("fingerprint")
                    if not fingerprint:
                        errors.append(f"missing_rsa_fingerprint:{path_id}:{index}")
                        continue
                    router_info = ctor.read_router_info(client, fingerprint)
                    full_relay = {
                        "name": f"arti_{index}",
                        "fingerprint": fingerprint,
                        **router_info,
                    }
                    circuit["path"].append(full_relay)
                    compact_circuit["path"].append(
                        {
                            "name": full_relay["name"],
                            "fingerprint": fingerprint,
                            "flags": router_info["flags"],
                            "ipv4": router_info["ipv4"],
                            "family_count": len(router_info["family"]),
                        }
                    )
                circuit_errors = ctor.validate_circuit(circuit)
                if circuit_errors:
                    errors.extend(f"{path_id}:{error}" for error in circuit_errors)
                compact_circuit["errors"] = circuit_errors
                circuits[path_id] = compact_circuit
            result["checked_paths"] = len(circuits)
            result["errors"] = errors
            result["circuits"] = circuits
            result["ok"] = bool(circuits) and not errors
            return result
        finally:
            client.close()
    except Exception as exc:
        return {
            "ok": False,
            "boot": None,
            "checked_paths": 0,
            "errors": [str(exc)],
            "circuits": {},
        }
    finally:
        ctor.stop_process(proc)


def first_ipv4(addrs: list[str]) -> str | None:
    for addr in addrs:
        host = str(addr).rsplit(":", 1)[0]
        if host.startswith("[") and host.endswith("]"):
            host = host[1:-1]
        try:
            parsed = ipaddress.ip_address(host)
        except ValueError:
            continue
        if isinstance(parsed, ipaddress.IPv4Address):
            return str(parsed)
    return None


def same_ipv4_16(left: str, right: str) -> bool:
    left_addr = ipaddress.IPv4Address(left)
    right_addr = ipaddress.IPv4Address(right)
    return int(left_addr) >> 16 == int(right_addr) >> 16


def read_lines(proc: subprocess.Popen[str], lines: queue.Queue[str]) -> None:
    assert proc.stdout is not None
    for line in proc.stdout:
        lines.put(line.rstrip())


def wait_for_ready(
    proc: subprocess.Popen[str],
    lines: queue.Queue[str],
    rpc_socket: Path,
    *,
    timeout: float,
) -> dict[str, Any]:
    started = time.monotonic()
    seen: list[str] = []
    proxy_ready = False
    while time.monotonic() - started < timeout:
        if proc.poll() is not None:
            return {
                "ok": False,
                "error": f"arti exited with code {proc.returncode}",
                "lines": seen[-120:],
            }
        try:
            line = lines.get(timeout=0.25)
            seen.append(line)
            if "proxy now functional" in line:
                proxy_ready = True
        except queue.Empty:
            pass
        if proxy_ready and rpc_socket.exists():
            return {
                "ok": True,
                "seconds": round(time.monotonic() - started, 3),
                "lines": seen[-120:],
            }
    return {"ok": False, "error": "bootstrap timeout", "lines": seen[-120:]}


def stop_process(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=10.0)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=10.0)


def short_summary(payload: dict[str, Any]) -> dict[str, Any]:
    validation = payload.get("validation") or {}
    directory_validation = payload.get("directory_validation") or {}
    return {
        "ok": payload["ok"],
        "boot": payload["boot"],
        "runtime_path_shape_proof": payload["runtime_path_shape_proof"],
        "full_runtime_quality_proof": payload["full_runtime_quality_proof"],
        "sample_count": payload["sample_count"],
        "checked_paths": validation.get("checked_paths"),
        "directory_checked_paths": directory_validation.get("checked_paths"),
        "errors": validation.get("errors"),
        "directory_errors": directory_validation.get("errors"),
    }


if __name__ == "__main__":
    sys.exit(main())
