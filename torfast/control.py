"""Minimal Tor control-port helpers for readiness checks."""

from __future__ import annotations

from pathlib import Path
import re
import shlex
import socket
import time


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
            chunk = self.sock.recv(65536)
            if not chunk:
                raise EOFError("control socket closed")
            data += chunk
            text = data.decode("utf-8", errors="replace")
            if "\r\n250 OK\r\n" in text or text.startswith("250 ") or text.startswith("5"):
                if text.startswith("5"):
                    raise RuntimeError(text.strip())
                return text

    def close(self) -> None:
        self.sock.close()


def wait_for_general_circuit(
    *,
    host: str,
    port: int,
    cookie_path: Path,
    timeout: float,
    poll_interval: float = 0.25,
) -> dict[str, object]:
    return wait_for_general_circuits(
        host=host,
        port=port,
        cookie_path=cookie_path,
        timeout=timeout,
        poll_interval=poll_interval,
        min_count=1,
    )


def wait_for_general_circuits(
    *,
    host: str,
    port: int,
    cookie_path: Path,
    timeout: float,
    poll_interval: float = 0.25,
    min_count: int = 1,
) -> dict[str, object]:
    if min_count < 1:
        raise ValueError("min_count must be at least 1")
    started = time.monotonic()
    last_error: str | None = None
    client: TorControlClient | None = None
    try:
        while time.monotonic() - started < timeout:
            if client is None:
                try:
                    client = TorControlClient.connect(
                        host=host,
                        port=port,
                        cookie_path=cookie_path,
                    )
                except (FileNotFoundError, OSError, RuntimeError, EOFError) as exc:
                    last_error = f"{type(exc).__name__}: {exc}"
                    time.sleep(poll_interval)
                    continue
            try:
                circuits = parse_circuits(client.command("GETINFO circuit-status"))
            except (OSError, RuntimeError, EOFError) as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                client.close()
                client = None
                time.sleep(poll_interval)
                continue
            matched = [circuit for circuit in circuits if is_built_general_circuit(circuit)]
            if len(matched) >= min_count:
                first = matched[0]
                ready_seconds = round(time.monotonic() - started, 3)
                return {
                    "ok": True,
                    "seconds": ready_seconds,
                    "circuit_id": first.get("id"),
                    "purpose": first.get("purpose"),
                    "path_length": len(first.get("path", [])),
                    "matched_circuit_count": len(matched),
                    "min_count": min_count,
                }
            time.sleep(poll_interval)
        return {
            "ok": False,
            "error": "general circuit wait timeout",
            "last_error": last_error,
            "min_count": min_count,
        }
    finally:
        if client is not None:
            client.close()


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


def is_built_general_circuit(circuit: dict[str, object]) -> bool:
    return (
        circuit.get("status") == "BUILT"
        and circuit.get("purpose") in {"GENERAL", "CONFLUX_LINKED"}
        and len(circuit.get("path", [])) == 3
    )


def parse_streams(reply: str) -> list[dict[str, object]]:
    streams: list[dict[str, object]] = []
    for line in reply.splitlines():
        if not line or line.startswith("250") or line == ".":
            continue
        parts = shlex.split(line)
        if len(parts) < 4:
            continue
        stream_id, status, circuit_id, target = parts[:4]
        fields = parse_fields(parts[4:])
        streams.append(
            {
                "id": stream_id,
                "status": status,
                "circuit_id": None if circuit_id == "0" else circuit_id,
                "target": target,
                "socks_username": fields.get("SOCKS_USERNAME"),
                "socks_password": fields.get("SOCKS_PASSWORD"),
                "client_protocol": fields.get("CLIENT_PROTOCOL"),
                "nym_epoch": parse_int_field(fields.get("NYM_EPOCH")),
                "session_group": parse_int_field(fields.get("SESSION_GROUP")),
                "iso_fields": split_csv_field(fields.get("ISO_FIELDS")),
            }
        )
    return streams


def parse_int_field(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def split_csv_field(value: str | None) -> list[str]:
    if not value:
        return []
    return [part for part in value.split(",") if part]


def is_user_socks_stream(
    stream: dict[str, object],
    *,
    target_substrings: list[str] | None = None,
) -> bool:
    if stream.get("client_protocol") != "SOCKS5":
        return False
    if not isinstance(stream.get("socks_username"), str):
        return False
    if not isinstance(stream.get("socks_password"), str):
        return False
    target = stream.get("target")
    if target_substrings and isinstance(target, str):
        return any(substring in target for substring in target_substrings)
    return True


def probe_stream_isolation(
    *,
    host: str,
    port: int,
    cookie_path: Path,
    timeout: float,
    poll_interval: float = 0.1,
    target_substrings: list[str] | None = None,
) -> dict[str, object]:
    started = time.monotonic()
    last_error: str | None = None
    client: TorControlClient | None = None
    polls = 0
    try:
        while time.monotonic() - started < timeout:
            if client is None:
                try:
                    client = TorControlClient.connect(
                        host=host,
                        port=port,
                        cookie_path=cookie_path,
                    )
                except (FileNotFoundError, OSError, RuntimeError, EOFError) as exc:
                    last_error = f"{type(exc).__name__}: {exc}"
                    time.sleep(poll_interval)
                    continue
            try:
                streams = parse_streams(client.command("GETINFO stream-status"))
            except (OSError, RuntimeError, EOFError) as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                client.close()
                client = None
                time.sleep(poll_interval)
                continue
            polls += 1
            matched = [
                stream
                for stream in streams
                if is_user_socks_stream(
                    stream,
                    target_substrings=target_substrings,
                )
            ]
            if matched:
                return summarize_stream_isolation(
                    matched,
                    seconds=round(time.monotonic() - started, 3),
                    polls=polls,
                    target_substrings=target_substrings or [],
                )
            time.sleep(poll_interval)
        return {
            "ok": False,
            "error": "stream isolation probe timeout",
            "last_error": last_error,
            "polls": polls,
            "target_substrings": target_substrings or [],
        }
    finally:
        if client is not None:
            client.close()


def summarize_stream_isolation(
    streams: list[dict[str, object]],
    *,
    seconds: float,
    polls: int,
    target_substrings: list[str],
) -> dict[str, object]:
    stream_ids = sorted(
        {
            str(stream["id"])
            for stream in streams
            if isinstance(stream.get("id"), str)
        }
    )
    circuit_ids = sorted(
        {
            str(stream["circuit_id"])
            for stream in streams
            if isinstance(stream.get("circuit_id"), str)
        }
    )
    targets = sorted(
        {
            str(stream["target"])
            for stream in streams
            if isinstance(stream.get("target"), str)
        }
    )
    nym_epochs = sorted(
        {
            int(stream["nym_epoch"])
            for stream in streams
            if isinstance(stream.get("nym_epoch"), int)
        }
    )
    session_groups = sorted(
        {
            int(stream["session_group"])
            for stream in streams
            if isinstance(stream.get("session_group"), int)
        }
    )
    iso_fields = sorted(
        {
            ",".join(stream["iso_fields"])
            for stream in streams
            if isinstance(stream.get("iso_fields"), list)
        }
    )
    statuses = sorted(
        {
            str(stream["status"])
            for stream in streams
            if isinstance(stream.get("status"), str)
        }
    )
    return {
        "ok": True,
        "seconds": seconds,
        "polls": polls,
        "observed_stream_count": len(streams),
        "stream_ids": stream_ids,
        "circuit_ids": circuit_ids,
        "statuses": statuses,
        "target_count": len(targets),
        "targets": targets[:8],
        "nym_epochs": nym_epochs,
        "session_groups": session_groups,
        "iso_fields": iso_fields,
        "target_substrings": target_substrings,
    }
