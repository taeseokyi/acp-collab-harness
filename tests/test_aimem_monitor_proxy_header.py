"""윈도우 통과 프록시가 붙이는 PROXY 줄에서 진짜 접속자 주소를 읽는다 - loopback 에서 온 것만 믿는다."""
import pathlib
import socket
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools"))

from aimem_monitor import server  # noqa: E402


class ProxyHeader(unittest.TestCase):
    def pair(self, payload):
        a, b = socket.socketpair()
        self.addCleanup(a.close)
        self.addCleanup(b.close)
        a.sendall(payload)
        b.settimeout(2)
        return b

    def test_loopback_peer_with_a_proxy_line_yields_the_real_client(self):
        tls_hello = b"\x16\x03\x01rest-of-handshake"
        s = self.pair(b"PROXY TCP4 203.0.113.7 127.0.0.1 51234 18799\r\n" + tls_hello)
        self.assertEqual(server.read_proxy_header(s, ("127.0.0.1", 40000)), ("203.0.113.7", 51234))
        self.assertEqual(s.recv(100), tls_hello)                         # 그 줄만 꺼냈고 뒤는 그대로 남는다
        s = self.pair(b"PROXY TCP6 2001:db8::1 ::1 51234 18799\r\n\x16")
        self.assertEqual(server.read_proxy_header(s, ("::1", 40000, 0, 0)), ("2001:db8::1", 51234, 0, 0))

    def test_no_proxy_line_or_a_bad_one_keeps_the_socket_address(self):
        for payload in (b"\x16\x03\x01hello", b"GET / HTTP/1.1\r\nHost: x\r\n\r\n", b"PROXY TCP4 not-an-ip 127.0.0.1 1 2\r\n\x16",
                        b"PROXY UNKNOWN\r\n\x16", b"PROXY TCP4 1.2.3.4 127.0.0.1 99999 2\r\n\x16", b"PROXY TCP4 1.2.3.4 127.0.0.1 1 2"):
            with self.subTest(payload=payload[:24]):
                s = self.pair(payload)
                self.assertEqual(server.read_proxy_header(s, ("127.0.0.1", 40000)), ("127.0.0.1", 40000))

    def test_a_remote_peer_cannot_claim_another_address(self):
        payload = b"PROXY TCP4 10.9.9.9 127.0.0.1 1 2\r\n\x16"
        s = self.pair(payload)
        self.assertEqual(server.read_proxy_header(s, ("192.168.0.77", 40000)), ("192.168.0.77", 40000))
        self.assertEqual(s.recv(200), payload)                           # 한 바이트도 읽지 않았다 - TLS 핸드셰이크에서 떨어진다


if __name__ == "__main__":
    unittest.main()
