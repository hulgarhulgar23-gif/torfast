import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


from torfast.control import (
    TorControlClient,
    is_built_general_circuit,
    parse_circuits,
    parse_streams,
    probe_stream_isolation,
    wait_for_general_circuit,
    wait_for_general_circuits,
)


class FakeClient:
    def __init__(self, replies):
        self.replies = list(replies)
        self.closed = False

    def command(self, command: str) -> str:
        assert command in {"GETINFO circuit-status", "GETINFO stream-status"}
        if not self.replies:
            raise EOFError("no more replies")
        return self.replies.pop(0)

    def close(self) -> None:
        self.closed = True


class TorfastControlTests(unittest.TestCase):
    def test_parse_circuits_and_general_filter(self) -> None:
        reply = (
            "250+circuit-status=\r\n"
            "1 BUILT $AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA~a,"
            "$BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB~b,"
            "$CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC~c PURPOSE=GENERAL\r\n"
            "2 BUILT $DDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDD~d "
            "PURPOSE=HS_CLIENT_INTRO\r\n"
            "250 OK\r\n"
        )

        circuits = parse_circuits(reply)

        self.assertEqual(len(circuits), 2)
        self.assertTrue(is_built_general_circuit(circuits[0]))
        self.assertFalse(is_built_general_circuit(circuits[1]))

    def test_wait_for_general_circuit_finds_built_general(self) -> None:
        replies = [
            "250+circuit-status=\r\n"
            "1 LAUNCHED PURPOSE=GENERAL\r\n"
            "250 OK\r\n",
            "250+circuit-status=\r\n"
            "1 BUILT $AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA~a,"
            "$BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB~b,"
            "$CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC~c PURPOSE=GENERAL\r\n"
            "250 OK\r\n",
        ]
        fake = FakeClient(replies)
        with tempfile.TemporaryDirectory() as tmp:
            cookie = Path(tmp) / "cookie"
            cookie.write_bytes(b"00")
            with (
                patch.object(TorControlClient, "connect", return_value=fake),
                patch("torfast.control.time.sleep"),
            ):
                result = wait_for_general_circuit(
                    host="127.0.0.1",
                    port=19000,
                    cookie_path=cookie,
                    timeout=1.0,
                    poll_interval=0.0,
                )

        self.assertTrue(result["ok"])
        self.assertEqual(result["purpose"], "GENERAL")
        self.assertEqual(result["path_length"], 3)
        self.assertTrue(fake.closed)

    def test_wait_for_general_circuit_times_out_cleanly(self) -> None:
        replies = ["250+circuit-status=\r\n250 OK\r\n"] * 8
        fake = FakeClient(replies)
        with tempfile.TemporaryDirectory() as tmp:
            cookie = Path(tmp) / "cookie"
            cookie.write_bytes(b"00")
            with (
                patch.object(TorControlClient, "connect", return_value=fake),
                patch("torfast.control.time.sleep"),
            ):
                result = wait_for_general_circuit(
                    host="127.0.0.1",
                    port=19000,
                    cookie_path=cookie,
                    timeout=0.001,
                    poll_interval=0.0,
                )

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "general circuit wait timeout")
        self.assertTrue(fake.closed)

    def test_wait_for_general_circuits_requires_min_count(self) -> None:
        replies = [
            "250+circuit-status=\r\n"
            "1 BUILT $AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA~a,"
            "$BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB~b,"
            "$CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC~c PURPOSE=GENERAL\r\n"
            "2 BUILT $DDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDD~d,"
            "$EEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEE~e,"
            "$FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF~f PURPOSE=GENERAL\r\n"
            "250 OK\r\n",
        ]
        fake = FakeClient(replies)
        with tempfile.TemporaryDirectory() as tmp:
            cookie = Path(tmp) / "cookie"
            cookie.write_bytes(b"00")
            with (
                patch.object(TorControlClient, "connect", return_value=fake),
                patch("torfast.control.time.sleep"),
            ):
                result = wait_for_general_circuits(
                    host="127.0.0.1",
                    port=19000,
                    cookie_path=cookie,
                    timeout=1.0,
                    poll_interval=0.0,
                    min_count=2,
                )

        self.assertTrue(result["ok"])
        self.assertEqual(result["matched_circuit_count"], 2)
        self.assertEqual(result["min_count"], 2)
        self.assertTrue(fake.closed)

    def test_parse_streams_reads_socks_auth_and_isolation_fields(self) -> None:
        reply = (
            "250+stream-status=\r\n"
            "12 SUCCEEDED 7 check.torproject.org:443 "
            'SOCKS_USERNAME="user" SOCKS_PASSWORD="secret" '
            "CLIENT_PROTOCOL=SOCKS5 NYM_EPOCH=3 SESSION_GROUP=-4 "
            "ISO_FIELDS=SOCKS_USERNAME,SOCKS_PASSWORD,NYM_EPOCH\r\n"
            "250 OK\r\n"
        )

        streams = parse_streams(reply)

        self.assertEqual(len(streams), 1)
        self.assertEqual(streams[0]["target"], "check.torproject.org:443")
        self.assertEqual(streams[0]["circuit_id"], "7")
        self.assertEqual(streams[0]["socks_username"], "user")
        self.assertEqual(streams[0]["socks_password"], "secret")
        self.assertEqual(streams[0]["client_protocol"], "SOCKS5")
        self.assertEqual(streams[0]["nym_epoch"], 3)
        self.assertEqual(streams[0]["session_group"], -4)
        self.assertEqual(
            streams[0]["iso_fields"],
            ["SOCKS_USERNAME", "SOCKS_PASSWORD", "NYM_EPOCH"],
        )

    def test_probe_stream_isolation_returns_hashed_auth_snapshot(self) -> None:
        replies = [
            "250+stream-status=\r\n250 OK\r\n",
            "250+stream-status=\r\n"
            "12 SUCCEEDED 7 check.torproject.org:443 "
            'SOCKS_USERNAME="user" SOCKS_PASSWORD="secret" '
            "CLIENT_PROTOCOL=SOCKS5 NYM_EPOCH=3 SESSION_GROUP=-4 "
            "ISO_FIELDS=SOCKS_USERNAME,SOCKS_PASSWORD,NYM_EPOCH\r\n"
            "250 OK\r\n",
        ]
        fake = FakeClient(replies)
        with tempfile.TemporaryDirectory() as tmp:
            cookie = Path(tmp) / "cookie"
            cookie.write_bytes(b"00")
            with (
                patch.object(TorControlClient, "connect", return_value=fake),
                patch("torfast.control.time.sleep"),
            ):
                result = probe_stream_isolation(
                    host="127.0.0.1",
                    port=19000,
                    cookie_path=cookie,
                    timeout=1.0,
                    poll_interval=0.0,
                    target_substrings=["check.torproject.org"],
                )

        self.assertTrue(result["ok"])
        self.assertEqual(result["observed_stream_count"], 1)
        self.assertEqual(result["circuit_ids"], ["7"])
        self.assertEqual(result["nym_epochs"], [3])
        self.assertNotIn("socks_username_sha256_12", result)
        self.assertNotIn("socks_password_sha256_12", result)
        self.assertTrue(fake.closed)
