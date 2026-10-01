from contextlib import contextmanager
import json
from pathlib import Path
import socket
import tempfile
import threading
import unittest

from cph_ai_companion.protocol import PROTOCOL_VERSION, schema_digest
from cph_ai_companion.transport import (JsonRpcClient, SessionDescriptor, TransportError,
                                        discover_sessions, strict_json)


@contextmanager
def bridge(handler):
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    errors = []

    def serve():
        try:
            connection, _ = listener.accept()
            with connection, connection.makefile("rb") as stream:
                for line in stream:
                    request = json.loads(line)
                    answer = handler(request)
                    if isinstance(answer, bytes):
                        connection.sendall(answer)
                    else:
                        connection.sendall(json.dumps(answer).encode() + b"\n")
        except OSError:
            pass
        except Exception as exc:
            errors.append(exc)
    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        yield port
    finally:
        listener.close()
        thread.join(2)
        if errors:
            raise errors[0]


def session(directory, port):
    root = Path(directory)
    root.chmod(0o700)
    path = root / "instance"
    path.mkdir(mode=0o700)
    credential = path / "credential"
    credential.write_text("a" * 64)
    credential.chmod(0o600)
    descriptor = path / "session.json"
    descriptor.write_text(json.dumps({"session_id": "instance", "host": "127.0.0.1", "port": port,
                                     "credential_file": "credential", "protocol_version": PROTOCOL_VERSION,
                                      "schema_digest": schema_digest()}))
    descriptor.chmod(0o600)
    return SessionDescriptor.load(descriptor)


def handshake(request):
    return {"id": request["id"], "ok": True, "result": {"session_id": "instance",
            "protocol_version": PROTOCOL_VERSION, "schema_digest": schema_digest()}}


class TransportTests(unittest.TestCase):
    def test_authenticated_explicit_descriptor_and_requests(self):
        received = []

        def handler(request):
            received.append(request)
            if request["method"] == "hello":
                return handshake(request)
            return {"id": request["id"], "ok": True, "result": {"state": "idle"}}
        with tempfile.TemporaryDirectory() as directory, bridge(handler) as port:
            descriptor = session(directory, port)
            self.assertEqual(len(discover_sessions(directory)), 1)
            with JsonRpcClient(descriptor) as client:
                self.assertEqual(client.request("status"), {"state": "idle"})
            self.assertEqual(received[0]["params"]["credential"], "a" * 64)
            self.assertNotIn("credential", descriptor.public_info())

    def test_handshake_missing_identity_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory, bridge(lambda r: {"id": r["id"], "ok": True, "result": {}}) as port:
            client = JsonRpcClient(session(directory, port))
            with self.assertRaises(TransportError):
                client.connect()
            self.assertIsNone(client._socket)

    def test_remote_error_body_is_never_exposed(self):
        def handler(request):
            if request["method"] == "hello":
                return handshake(request)
            return {"id": request["id"], "ok": False, "error": {"code": "arbitrary key secret", "message": "PRIVATE"}}
        with tempfile.TemporaryDirectory() as directory, bridge(handler) as port:
            with JsonRpcClient(session(directory, port)) as client:
                with self.assertRaisesRegex(TransportError, "^bridge_rejected$"):
                    client.request("status")

    def test_world_read_permissions_and_symlinks_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            descriptor = session(directory, 12345)
            descriptor.path.chmod(0o644)
            with self.assertRaisesRegex(TransportError, "insecure_session_permissions"):
                SessionDescriptor.load(descriptor.path)
            descriptor.path.chmod(0o600)
            descriptor.credential_file.unlink()
            descriptor.credential_file.symlink_to(descriptor.path)
            with self.assertRaises(TransportError):
                descriptor.credential()

    def test_no_nonloopback_or_parent_credential_path(self):
        with tempfile.TemporaryDirectory() as directory:
            descriptor = session(directory, 12345)
            original = json.loads(descriptor.path.read_text())
            for patch in ({"host": "example.com"}, {"credential_file": "../credential"}):
                descriptor.path.write_text(json.dumps({**original, **patch}))
                with self.assertRaises(TransportError):
                    SessionDescriptor.load(descriptor.path)

    def test_duplicate_json_and_nonfinite_values_rejected(self):
        for value in (b'{"a":1,"a":2}', b'{"a":NaN}', b'[]'):
            with self.assertRaises(TransportError):
                strict_json(value)


if __name__ == "__main__":
    unittest.main()
