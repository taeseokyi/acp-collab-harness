"""POST /api/ask 본문이 요청 시작부터 body_grace 안에 다 오지 않으면 400 으로 답하는지 (R41-N5). 표준 라이브러리만."""
import json
import socket
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

import serve  # noqa: E402

GRACE = 1.0  # 본문 마감(초) - 검사가 몇 초 안에 끝나도록 짧게 준다
DRIP_SLEEP = 0.2  # 느린 본문 1바이트 사이의 침묵 - body_grace 보다 짧다


class AskBodyTimeoutTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.server = serve.make_server(
            "127.0.0.1", 0, self.tmp.name, env={},
            stt_fn=lambda path, mime, env: "", llm_run=lambda prompt, env=None: "가짜 답",
            body_grace=GRACE)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(5)
        self.tmp.cleanup()

    def test_partial_body_kept_open_gets_400(self):
        sock = socket.create_connection(("127.0.0.1", self.port), timeout=5)
        self.addCleanup(sock.close)
        sock.sendall(
            b"POST /api/ask HTTP/1.1\r\nHost: 127.0.0.1\r\n"
            b"Content-Type: application/json\r\nContent-Length: 100\r\n\r\n")
        sock.sendall(b'{"kind"')                     # 100 바이트 중 7 바이트만 보내고 연결을 살려 둔다
        sock.settimeout(GRACE + 3)
        head, body = self._read_response(sock)
        self.assertTrue(head.startswith(b"HTTP/1.1 400"), head)
        self.assertIn("본문", json.loads(body.decode("utf-8"))["error"])

    def test_slow_continuous_body_gets_400_after_grace(self):
        body = b'{"kind":"summary","prompt":"' + b"x" * 24 + b'","ids":["r-x"]}'  # 68 바이트
        self.assertEqual(len(body), 68)
        sock = socket.create_connection(("127.0.0.1", self.port), timeout=5)
        self.addCleanup(sock.close)
        sock.sendall(
            b"POST /api/ask HTTP/1.1\r\nHost: 127.0.0.1\r\n"
            b"Content-Type: application/json\r\nContent-Length: 68\r\n\r\n")
        stop = threading.Event()

        def drip():
            for byte in body:
                if stop.is_set():
                    return
                try:
                    sock.sendall(bytes((byte,)))
                except (BrokenPipeError, ConnectionResetError):
                    return
                time.sleep(DRIP_SLEEP)

        sender = threading.Thread(target=drip, daemon=True)
        sender.start()
        sock.settimeout(GRACE + 3)
        try:
            head, response_body = self._read_response(sock)
        finally:
            stop.set()
            sender.join(2)
        self.assertTrue(head.startswith(b"HTTP/1.1 400"), head)
        self.assertIn("error", json.loads(response_body.decode("utf-8")))

    def _read_response(self, sock):
        raw = b""
        while b"\r\n\r\n" not in raw:
            chunk = sock.recv(4096)
            if not chunk:
                break
            raw += chunk
        head, _, body = raw.partition(b"\r\n\r\n")
        length = 0
        for line in head.split(b"\r\n")[1:]:
            name, _, value = line.partition(b":")
            if name.strip().lower() == b"content-length":
                length = int(value.strip())
        while len(body) < length:
            chunk = sock.recv(4096)
            if not chunk:
                break
            body += chunk
        return head, body


if __name__ == "__main__":
    unittest.main()
