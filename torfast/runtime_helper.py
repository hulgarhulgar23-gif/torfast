"""Background helper for managed torfast runtime actions."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
from pathlib import Path
import socket
import sys
import time

REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_ROOT = REPO_ROOT / "tools"
for import_root in (TOOLS_ROOT, REPO_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from launch_torfast_browser import main as launcher_main

from .fast_runtime import (
    cleanup_runtime_helper_files,
    ensure_private_dir,
    runtime_helper_file_fingerprint,
    runtime_helper_json_path,
    runtime_helper_socket_path,
    runtime_helper_starting_path,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-root", required=True)
    return parser


def read_request(conn: socket.socket) -> dict[str, object] | None:
    chunks: list[bytes] = []
    while True:
        chunk = conn.recv(65536)
        if not chunk:
            break
        chunks.append(chunk)
    if not chunks:
        return None
    try:
        payload = json.loads(b"".join(chunks).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def respond(conn: socket.socket, payload: dict[str, object]) -> None:
    conn.sendall((json.dumps(payload) + "\n").encode("utf-8"))


def handle_request(request: dict[str, object]) -> tuple[dict[str, object], bool]:
    if request.get("shutdown") is True:
        return {"ok": True, "exit_code": 0, "stdout": "", "stderr": ""}, True
    launcher_args = request.get("launcher_args")
    if not isinstance(launcher_args, list) or not all(
        isinstance(item, str) for item in launcher_args
    ):
        return {
            "ok": False,
            "exit_code": 1,
            "stdout": "",
            "stderr": "runtime helper request missing launcher_args\n",
        }, False
    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()
    with (
        contextlib.redirect_stdout(stdout_buffer),
        contextlib.redirect_stderr(stderr_buffer),
    ):
        try:
            exit_code = launcher_main(launcher_args)
        except SystemExit as exc:
            exit_code = exc.code if isinstance(exc.code, int) else 1
        except Exception as exc:  # pragma: no cover - defensive only
            print(f"runtime helper internal error: {type(exc).__name__}: {exc}", file=sys.stderr)
            exit_code = 1
    return {
        "ok": exit_code == 0,
        "exit_code": int(exit_code),
        "stdout": stdout_buffer.getvalue(),
        "stderr": stderr_buffer.getvalue(),
    }, False


def write_metadata(state_root: Path) -> None:
    payload = {
        "pid": os_getpid(),
        "socket_path": str(runtime_helper_socket_path(state_root)),
        "fingerprint": runtime_helper_file_fingerprint(),
        "started_epoch_ms": round(time.time() * 1000, 3),
    }
    runtime_helper_json_path(state_root).write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n"
    )


def os_getpid() -> int:
    import os

    return os.getpid()


def serve(state_root: Path) -> int:
    ensure_private_dir(state_root)
    socket_path = runtime_helper_socket_path(state_root)
    metadata_path = runtime_helper_json_path(state_root)
    starting_path = runtime_helper_starting_path(state_root)
    for path in (socket_path, metadata_path):
        try:
            if path.exists():
                path.unlink()
        except OSError:
            pass
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
        server.bind(str(socket_path))
        socket_path.chmod(0o600)
        server.listen(1)
        server.settimeout(1.0)
        write_metadata(state_root)
        try:
            if starting_path.exists():
                starting_path.unlink()
        except OSError:
            pass
        shutting_down = False
        while not shutting_down:
            try:
                conn, _ = server.accept()
            except TimeoutError:
                continue
            with conn:
                request = read_request(conn)
                if request is None:
                    respond(
                        conn,
                        {
                            "ok": False,
                            "exit_code": 1,
                            "stdout": "",
                            "stderr": "runtime helper received invalid request\n",
                        },
                    )
                    continue
                response, shutting_down = handle_request(request)
                respond(conn, response)
    cleanup_runtime_helper_files(state_root)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    state_root = Path(args.state_root).resolve()
    try:
        return serve(state_root)
    finally:
        cleanup_runtime_helper_files(state_root)


if __name__ == "__main__":
    raise SystemExit(main())
