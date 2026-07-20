"""Background helper for managed torfast runtime actions."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
from pathlib import Path
import socket
import sys
import threading
import time

REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_ROOT = REPO_ROOT / "tools"
for import_root in (TOOLS_ROOT, REPO_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from launch_torfast_browser import main as launcher_main
from launch_torfast_browser import (
    boot_signal_lines,
    browser_launch_gate_ready_text,
    control_ready_for_gate,
    control_ready_for_gate_with_client,
    managed_service_ready_for_gate,
    managed_service_ready_result,
    record_managed_service_ready,
    tail_lines,
    wait_for_existing_service_ready_in_log,
    write_json,
)
from torfast.control import TorControlClient

from .fast_runtime import (
    cleanup_runtime_helper_files,
    ensure_private_dir,
    process_is_alive,
    read_json_file,
    runtime_helper_context,
    runtime_helper_file_fingerprint,
    runtime_helper_json_path,
    runtime_helper_socket_path,
    runtime_helper_starting_path,
)

PROMOTION_GATES = ("tor_boot_95", "tor_boot_100")
HELPER_ACCEPT_TIMEOUT_SECONDS = 0.05
PROMOTER_CONTROL_POLL_INTERVAL_SECONDS = 0.02


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
        "context": runtime_helper_context(state_root),
        "pid": os_getpid(),
        "socket_path": str(runtime_helper_socket_path(state_root)),
        "fingerprint": runtime_helper_file_fingerprint(),
        "started_epoch_ms": round(time.time() * 1000, 3),
    }
    write_json(runtime_helper_json_path(state_root), payload)


def managed_service_json_path(state_root: Path) -> Path:
    return state_root / "tor-service.json"


def promote_managed_service_gate_with_persistent_control(
    service: dict[str, object],
    *,
    gate: str,
    timeout: float,
) -> dict[str, object] | None:
    pid = service.get("pid")
    tor_log = service.get("tor_log")
    control_port = service.get("control_port")
    control_cookie_path = service.get("control_cookie_path")
    if (
        not isinstance(pid, int)
        or not isinstance(tor_log, str)
        or not isinstance(control_port, int)
        or not isinstance(control_cookie_path, str)
    ):
        return None
    ready_text = browser_launch_gate_ready_text(gate)
    started = time.monotonic()
    polls = 0
    control_client: TorControlClient | None = None
    log_path = Path(tor_log)
    try:
        try:
            control_client = TorControlClient.connect(
                host="127.0.0.1",
                port=control_port,
                cookie_path=Path(control_cookie_path),
            )
        except (FileNotFoundError, OSError, RuntimeError, EOFError):
            return None
        while time.monotonic() - started < timeout:
            if not process_is_alive(pid):
                seen = tail_lines(log_path, limit=80)
                return {
                    "ok": False,
                    "error": f"tor exited before reaching {ready_text}",
                    "lines": seen,
                    "polls": polls,
                    "signal_lines": boot_signal_lines(seen),
                }
            seen = tail_lines(log_path, limit=200)
            polls += 1
            control_ready = control_ready_for_gate_with_client(
                gate=gate,
                client=control_client,
            )
            if (
                isinstance(control_ready, dict)
                and control_ready.get("ok") is True
                and isinstance(control_ready.get("progress"), int)
            ):
                ready_monotonic = time.monotonic()
                return {
                    "ok": True,
                    "seconds": round(ready_monotonic - started, 3),
                    "ready_epoch_ms": round(time.time() * 1000, 3),
                    "ready_monotonic_seconds": round(ready_monotonic, 6),
                    "lines": seen[-80:],
                    "polls": polls,
                    "ready_via_control": True,
                    "control_bootstrap_phase": control_ready,
                    "signal_lines": boot_signal_lines(seen),
                }
            if control_ready is not None and control_ready.get("ok") is not True:
                return None
            if any(ready_text in line for line in seen):
                ready_monotonic = time.monotonic()
                return {
                    "ok": True,
                    "seconds": round(ready_monotonic - started, 3),
                    "ready_epoch_ms": round(time.time() * 1000, 3),
                    "ready_monotonic_seconds": round(ready_monotonic, 6),
                    "lines": seen[-80:],
                    "polls": polls,
                    "signal_lines": boot_signal_lines(seen),
                }
            time.sleep(PROMOTER_CONTROL_POLL_INTERVAL_SECONDS)
        seen = tail_lines(log_path, limit=80)
        return {
            "ok": False,
            "error": "bootstrap timeout",
            "lines": seen,
            "polls": polls,
            "signal_lines": boot_signal_lines(seen),
        }
    finally:
        if control_client is not None:
            control_client.close()


def promote_managed_service_gate(
    state_root: Path,
    *,
    gate: str,
    timeout: float = 180.0,
) -> dict[str, object] | None:
    service_path = managed_service_json_path(state_root)
    service = read_json_file(service_path)
    if not isinstance(service, dict):
        return None
    if managed_service_ready_for_gate(service, gate):
        return service
    pid = service.get("pid")
    tor_log = service.get("tor_log")
    if not isinstance(pid, int) or not isinstance(tor_log, str):
        return None
    wait_result = promote_managed_service_gate_with_persistent_control(
        service,
        gate=gate,
        timeout=timeout,
    )
    if wait_result is None:
        wait_result = wait_for_existing_service_ready_in_log(
            pid=pid,
            log_path=Path(tor_log),
            timeout=timeout,
            gate=gate,
            control_port=service.get("control_port"),
            control_cookie_path=service.get("control_cookie_path"),
            service_path=service_path,
            expected_service=service,
            ready_text=browser_launch_gate_ready_text(gate),
            process_name="tor",
        )
    if wait_result.get("ok") is not True:
        return None
    latest_service = read_json_file(service_path)
    if (
        not isinstance(latest_service, dict)
        or latest_service.get("pid") != pid
        or latest_service.get("tor_log") != tor_log
    ):
        return None
    if managed_service_ready_for_gate(latest_service, gate):
        return latest_service
    updated_service = record_managed_service_ready(
        latest_service,
        gate=gate,
        wait_result=wait_result,
        actor="runtime_helper_promoter",
    )
    write_json(service_path, updated_service)
    return updated_service


def promote_managed_service_ready_gates(
    state_root: Path,
    *,
    gates: tuple[str, ...] = PROMOTION_GATES,
) -> dict[str, object] | None:
    latest_service: dict[str, object] | None = None
    for gate in gates:
        latest_service = promote_managed_service_gate(state_root, gate=gate)
        if latest_service is None:
            return None
    return latest_service


def start_background_gate_promoter(
    state_root: Path,
    *,
    thread: threading.Thread | None,
) -> threading.Thread:
    if thread is not None and thread.is_alive():
        return thread
    promoter = threading.Thread(
        target=promote_managed_service_ready_gates,
        args=(state_root,),
        daemon=True,
    )
    promoter.start()
    return promoter


def maybe_restart_background_gate_promoter(
    state_root: Path,
    *,
    thread: threading.Thread | None,
) -> threading.Thread | None:
    if thread is not None and thread.is_alive():
        return thread
    service = read_json_file(managed_service_json_path(state_root))
    if not isinstance(service, dict):
        return thread
    pid = service.get("pid")
    tor_log = service.get("tor_log")
    if not isinstance(pid, int) or not isinstance(tor_log, str):
        return thread
    if not process_is_alive(pid):
        return thread
    if managed_service_ready_for_gate(service, PROMOTION_GATES[-1]):
        return thread
    return start_background_gate_promoter(state_root, thread=thread)


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
        server.settimeout(HELPER_ACCEPT_TIMEOUT_SECONDS)
        write_metadata(state_root)
        promoter_thread = maybe_restart_background_gate_promoter(
            state_root,
            thread=None,
        )
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
                promoter_thread = maybe_restart_background_gate_promoter(
                    state_root,
                    thread=promoter_thread,
                )
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
                if request.get("start_gate_promoter") is True:
                    promoter_thread = maybe_restart_background_gate_promoter(
                        state_root,
                        thread=promoter_thread,
                    )
                    active_after_request = (
                        promoter_thread is not None and promoter_thread.is_alive()
                    )
                    respond(
                        conn,
                        {
                            "ok": True,
                            "exit_code": 0,
                            "stdout": "",
                            "stderr": "",
                            "requested": True,
                            "active_after_request": active_after_request,
                            "reason": (
                                None
                                if promoter_thread is not None
                                else "no promotable managed service"
                            ),
                        },
                    )
                    continue
                response, shutting_down = handle_request(request)
                if (
                    not shutting_down
                    and response.get("ok") is True
                ):
                    promoter_thread = maybe_restart_background_gate_promoter(
                        state_root,
                        thread=promoter_thread,
                    )
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
