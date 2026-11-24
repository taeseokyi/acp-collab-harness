"""POST /api/ask 본문이 요청 시작부터 body_grace 안에 다 오지 않으면 400 으로 답하는지 (R41-N5, R42-N3). 표준 라이브러리만."""
import http.client
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
FAST_DRIP = 0.002  # 마감 안에 다 오는 느린 본문 - 1바이트 사이 침묵(합계 < GRACE)
SLOW_DRIP = 0.03  # 마감을 넘기는 느린 본문 - 침묵은 짧지만(<< GRACE) 합계 > GRACE
REASON = "본문이 중간에 끊겼습니다"  # serve.py _read_body 가 내는 400 까닭


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
        # 본문 `ids` 가 실제 있는 녹음을 가리키게 한다 - 없거나 없는 id 면 다른 까닭의 400 이 난다
        self.rid = self.server.store.add_recording(b"fake-audio", "audio/webm")["id"]
        self.server.store.set_transcript(self.rid, "가짜 녹취 글")

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(5)
        self.tmp.cleanup()

    def _ask_body(self):
        return json.dumps({"kind": "summary", "prompt": "", "ids": [self.rid]},
                          ensure_ascii=False).encode("utf-8")

    def _post_head(self, sock, length):
        sock.sendall(
            b"POST /api/ask HTTP/1.1\r\nHost: 127.0.0.1\r\n"
            b"Content-Type: application/json\r\n"
            b"Content-Length: " + str(length).encode("ascii") + b"\r\n\r\n")

    def _drip(self, sock, body, delay):
        stop = threading.Event()

        def send():
            for byte in body:
                if stop.is_set():
                    return
                try:
                    sock.sendall(bytes((byte,)))
                except (BrokenPipeError, ConnectionResetError):
                    return
                time.sleep(delay)

        sender = threading.Thread(target=send, daemon=True)
        sender.start()
        return stop, sender

    def test_partial_body_kept_open_gets_400(self):
        body = self._ask_body()
        sock = socket.create_connection(("127.0.0.1", self.port), timeout=5)
        self.addCleanup(sock.close)
        self._post_head(sock, len(body))
        sock.sendall(body[:7])                       # 선언한 길이 중 7 바이트만 보내고 연결을 살려 둔다
        sock.settimeout(GRACE + 3)
        head, response_body = self._read_response(sock)
        self.assertTrue(head.startswith(b"HTTP/1.1 400"), head)
        self.assertIn(REASON, json.loads(response_body.decode("utf-8"))["error"])

    def test_slow_body_finishing_within_grace_is_accepted(self):
        body = self._ask_body()
        sock = socket.create_connection(("127.0.0.1", self.port), timeout=5)
        self.addCleanup(sock.close)
        self._post_head(sock, len(body))
        stop, sender = self._drip(sock, body, FAST_DRIP)   # 합계 < GRACE
        sock.settimeout(GRACE + 5)
        try:
            head, response_body = self._read_response(sock)
        finally:
            stop.set()
            sender.join(2)
        self.assertTrue(head.startswith(b"HTTP/1.1 202"), head)   # 묻기를 받아들였다
        ans = json.loads(response_body.decode("utf-8"))
        got = self._wait_answer(ans["id"])
        self.assertEqual(got["status"], "done")
        self.assertIn("가짜 답", got["answer"])

    def test_slow_body_past_grace_gets_400_even_with_short_gaps(self):
        body = self._ask_body()
        sock = socket.create_connection(("127.0.0.1", self.port), timeout=5)
        self.addCleanup(sock.close)
        self._post_head(sock, len(body))
        stop, sender = self._drip(sock, body, SLOW_DRIP)   # 침묵은 짧지만 합계 > GRACE
        sock.settimeout(GRACE + 6)
        try:
            head, response_body = self._read_response(sock)
        finally:
            stop.set()
            sender.join(2)
        # 시작부터의 마감이 아니라 '유휴 시간' 으로 재는 변이는 여기서 400 이 아니라 202 를 낸다
        self.assertTrue(head.startswith(b"HTTP/1.1 400"), head)
        self.assertIn(REASON, json.loads(response_body.decode("utf-8"))["error"])

    def _wait_answer(self, aid, timeout=10):
        end = time.time() + timeout
        got = None
        while time.time() < end:
            conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
            try:
                conn.request("GET", "/api/answers/" + aid)
                got = json.loads(conn.getresponse().read().decode("utf-8"))
            finally:
                conn.close()
            if got.get("status") != "running":
                return got
            time.sleep(0.05)
        return got

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
