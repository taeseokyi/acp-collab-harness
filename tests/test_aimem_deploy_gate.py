"""배포 문지기 (`tools/aimem_monitor/deploy_gate.py`, 2026-11-19) - 배포한 앱 앞에서 인증서·토큰·공개 여부를 맡는다.

실제 문지기를 띄워 본다 (앱 서버는 `--host --port` 만 받고, 루프백 이름이 아니면 403 을 내는 혼자 띄우기용 서버):

- 누구나: 토큰 없이 정적 파일과 `/api/*` 가 다 된다 - 바깥 이름(Host)으로 와도 앱 서버의 루프백 검사에 걸리지 않는다
- 토큰으로 막기: 토큰 없이는 화면도 `/api/*` 도 401, Bearer 머리나 토큰 화면이 심는 쿠키로 통과. 다른 배포의 쿠키는 안 통한다
- 배포 토큰(머리·쿠키)은 앱 서버로 넘어가지 않고, 다른 출처에서 온 `/api/*` 는 403
- 큰 본문이 그대로 오가고, 앱 서버가 죽으면 다음 요청 때 다시 띄운다
- 정적 파일: 폴더 밖·점 파일·심볼릭 링크는 404, 서버가 없는 앱은 `/api/*` 도 정적으로 본다
- TLS 로도 뜬다 (openssl 이 있을 때만)
"""
import hashlib
import http.client
import json
import os
import pathlib
import shutil
import signal
import socket
import ssl
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
GATE = ROOT / "tools" / "aimem_monitor" / "deploy_gate.py"
sys.path.insert(0, str(ROOT / "tools"))

from aimem_monitor import deploy_gate  # noqa: E402

BACKEND = '''import argparse, json, os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
ap = argparse.ArgumentParser(); ap.add_argument("--host"); ap.add_argument("--port", type=int)
a = ap.parse_args()
class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def log_message(self, *x): pass
    def _go(self):
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0]
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n) if n else b""
        if host not in ("127.0.0.1", "localhost"):
            out, code = b'{"error": "loopback only"}', 403
        elif self.path == "/api/big":
            out, code = b"x" * 3000000, 200
        elif self.path == "/api/die":
            os._exit(0)
        else:
            out = json.dumps({"path": self.path, "method": self.command, "len": len(body), "pid": os.getpid(),
                              "headers": {k.lower(): v for k, v in self.headers.items()},
                              "token_env": os.environ.get("AIMEM_DEPLOY_TOKEN")}).encode()
            code = 200
        self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out))); self.end_headers(); self.wfile.write(out)
    do_GET = do_POST = do_DELETE = _go
ThreadingHTTPServer((a.host, a.port), H).serve_forever()
'''


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class GateCase(unittest.TestCase):
    TOKEN = None
    SERVER = True
    TLS = False

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dir = pathlib.Path(cls.tmp.name)
        web = cls.dir / "app" / "web"
        (web / "js").mkdir(parents=True)
        (web / "index.html").write_text("<p>첫 화면</p>", encoding="utf-8")
        (web / "js" / "a.js").write_text("let a = 1;")
        (web / "manifest.webmanifest").write_text("{}")
        (web / ".secret").write_text("no")
        (cls.dir / "outside.txt").write_text("no")
        os.symlink(cls.dir / "outside.txt", web / "link.txt")
        (cls.dir / "app" / "serve.py").write_text(BACKEND)
        cls.port = free_port()
        cmd = [sys.executable, str(GATE), "--port", str(cls.port), "--root", str(web), "--title", "시험 앱"]
        if cls.SERVER:
            cmd += ["--server", str(cls.dir / "app" / "serve.py"), "--cwd", str(cls.dir / "app")]
        if cls.TLS:
            crt, key = cls.dir / "c.crt", cls.dir / "c.key"
            subprocess.run(["openssl", "req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:prime256v1", "-nodes",
                            "-keyout", str(key), "-out", str(crt), "-days", "2", "-subj", "/CN=localhost"],
                           check=True, capture_output=True)
            cmd += ["--tls-cert", str(crt), "--tls-key", str(key)]
        env = {k: v for k, v in os.environ.items() if k != deploy_gate.TOKEN_ENV}
        if cls.TOKEN:
            env[deploy_gate.TOKEN_ENV] = cls.TOKEN
        cls.proc = subprocess.Popen(cmd, env=env, stderr=subprocess.DEVNULL, start_new_session=True)
        deadline = time.monotonic() + 15
        while not deploy_gate._port_open(cls.port):
            if cls.proc.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError("문지기가 뜨지 않았습니다")
            time.sleep(0.05)

    @classmethod
    def tearDownClass(cls):
        try:
            os.killpg(cls.proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        cls.proc.wait(5)
        cls.tmp.cleanup()

    def req(self, method, path, headers=None, body=None, host="pc.example:18810"):
        if self.TLS:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            conn = http.client.HTTPSConnection("127.0.0.1", self.port, timeout=20, context=ctx)
        else:
            conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=20)
        try:
            conn.putrequest(method, path, skip_host=True)
            conn.putheader("Host", host)
            for k, v in (headers or {}).items():
                conn.putheader(k, v)
            if body is not None:
                conn.putheader("Content-Length", str(len(body)))
            conn.endheaders(body)
            res = conn.getresponse()
            return res.status, dict((k.lower(), v) for k, v in res.getheaders()), res.read()
        finally:
            conn.close()


class OpenGateTest(GateCase):
    def test_static_and_api_work_under_an_outside_name(self):
        code, hdr, body = self.req("GET", "/")
        self.assertEqual((code, body.decode()), (200, "<p>첫 화면</p>"))
        self.assertIn("text/html", hdr["content-type"])
        self.assertEqual(hdr["cache-control"], "no-cache")
        self.assertEqual(self.req("GET", "/js/a.js")[1]["content-type"], "text/javascript; charset=utf-8")
        self.assertEqual(self.req("GET", "/manifest.webmanifest")[1]["content-type"], "application/manifest+json; charset=utf-8")
        self.assertEqual(self.req("GET", "/", {"If-None-Match": hdr["etag"]})[0], 304)
        self.assertEqual(self.req("HEAD", "/")[2], b"")
        code, hdr, body = self.req("GET", "/api/x?q=1")
        seen = json.loads(body)
        self.assertEqual((code, seen["path"]), (200, "/api/x?q=1"))
        self.assertTrue(seen["headers"]["host"].startswith("127.0.0.1:"))
        self.assertEqual(hdr["connection"], "close")
        self.assertEqual(self.req("GET", "/~deploy/login")[0], 404)          # 토큰이 없으면 토큰 화면도 없다

    def test_origin_is_rewritten_or_refused(self):
        code, _, body = self.req("POST", "/api/x", {"Origin": "http://pc.example:18810"}, b"abc")
        seen = json.loads(body)
        self.assertEqual((code, seen["len"]), (200, 3))
        self.assertEqual(seen["headers"]["origin"], "http://" + seen["headers"]["host"])
        for bad in ("https://evil.example", "null", "https://pc.example:18810"):     # 마지막은 평문 문지기에서 scheme 이 다르다
            self.assertEqual(self.req("POST", "/api/x", {"Origin": bad}, b"abc")[0], 403, bad)
        for site, want in (("cross-site", 403), ("same-site", 403), ("same-origin", 200), ("none", 200)):
            self.assertEqual(self.req("GET", "/api/x", {"Sec-Fetch-Site": site})[0], want, site)   # Origin 없는 GET 도 막는다

    def test_abandoned_upload_does_not_hold_the_backend(self):
        for _ in range(30):
            with socket.create_connection(("127.0.0.1", self.port), timeout=10) as s:
                s.sendall(b"POST /api/up HTTP/1.1\r\nHost: h\r\nContent-Length: 1000000\r\n\r\n")
        time.sleep(1.5)
        fds = len(os.listdir("/proc/%d/fd" % self.proc.pid))
        self.assertLess(fds, 20, fds)

    def test_own_cookies_stay_at_the_gate(self):
        cookie = "aimem_deploy_1=a; mine=1; aimem_session=MON; AIMEM_x=2"
        seen = json.loads(self.req("GET", "/api/x", {"Cookie": cookie})[2])
        self.assertEqual(seen["headers"]["cookie"], "mine=1")

    def test_big_bodies_both_ways(self):
        big = b"y" * 3_000_000
        code, _, body = self.req("POST", "/api/up", {"Content-Type": "application/octet-stream"}, big)
        self.assertEqual((code, json.loads(body)["len"]), (200, len(big)))
        code, _, body = self.req("GET", "/api/big")
        self.assertEqual((code, len(body)), (200, 3_000_000))

    def test_static_refusals(self):
        for path in ("/.secret", "/link.txt", "/../outside.txt", "/%2e%2e/outside.txt", "/js/../../outside.txt",
                     "/js%5c..%5ca.js", "/nope.html", "/js", "/%ff"):
            self.assertEqual(self.req("GET", path)[0], 404, path)
        self.assertEqual(self.req("POST", "/", body=b"x")[0], 405)
        self.assertEqual(self.req("DELETE", "/index.html")[0], 405)

    def test_malformed_requests(self):
        for raw in (b"GET / HTTP/1.1\r\n\r\n", b"GET http://x/ HTTP/1.1\r\nHost: a\r\n\r\n", b"BROKEN\r\n\r\n",
                    b"GET / HTTP/1.1\r\nHost: a\r\nHost: b\r\n\r\n",
                    b"POST /api/x HTTP/1.1\r\nHost: a\r\nContent-Length: 1\r\nTransfer-Encoding: chunked\r\n\r\n",
                    b"GET / HTTP/1.1\r\nHost: a\r\nX: " + b"a" * 70000 + b"\r\n\r\n",
                    b"GET /api/x HTTP/1.1\r\nHost: a\r\nX: a\nOrigin: https://evil.example\r\n\r\n",       # 홑 LF 로 머리 끼워 넣기
                    b"GET /api/one\tHTTP/1.1\nHost:b\n\nPOST\t/api/two\tHTTP/1.1 HTTP/1.1\r\nHost: a\r\n\r\n",
                    b"POST /api/x HTTP/1.1\r\nHost: a\r\nOrigin: http://a\r\nOrigin: https://evil.example\r\n\r\n"):
            with socket.create_connection(("127.0.0.1", self.port), timeout=10) as s:
                s.sendall(raw)
                self.assertTrue(s.recv(64).startswith(b"HTTP/1.1 400"), raw[:40])

    def test_backend_is_restarted_when_dead(self):
        pid = json.loads(self.req("GET", "/api/x")[2])["pid"]
        self.req("GET", "/api/die")
        for _ in range(40):
            code, _, body = self.req("GET", "/api/x")
            if code == 200:
                break
            time.sleep(0.25)
        self.assertEqual(code, 200)
        self.assertNotEqual(json.loads(body)["pid"], pid)


class StaticOnlyGateTest(GateCase):
    SERVER = False

    def test_no_server_means_api_is_just_a_path(self):
        self.assertEqual(self.req("GET", "/")[0], 200)
        self.assertEqual(self.req("GET", "/api/x")[0], 404)
        self.assertEqual(self.req("POST", "/api/x", body=b"x")[0], 405)


class TokenGateTest(GateCase):
    TOKEN = "tok-SECRET-1234567890"

    def cookie(self):
        return "aimem_deploy_%d=%s" % (self.port, hashlib.sha256(("aimem-deploy-cookie:" + self.TOKEN).encode()).hexdigest())

    def test_everything_is_closed_without_the_token(self):
        code, hdr, body = self.req("GET", "/")
        self.assertEqual(code, 401)
        self.assertIn("토큰", body.decode())
        self.assertIn("시험 앱", body.decode())
        self.assertNotIn("첫 화면", body.decode())
        self.assertEqual(self.req("GET", "/js/a.js")[0], 401)
        code, hdr, body = self.req("GET", "/api/x")
        self.assertEqual((code, hdr["www-authenticate"]), (401, "Bearer"))
        self.assertNotIn(b"path", body)
        self.assertEqual(self.req("POST", "/api/x", body=b"abc")[0], 401)
        for bad in ("Bearer nope", "Bearer ", "Basic " + self.TOKEN, self.TOKEN):
            self.assertEqual(self.req("GET", "/api/x", {"Authorization": bad})[0], 401, bad)
        other = self.cookie().replace("aimem_deploy_%d" % self.port, "aimem_deploy_%d" % (self.port + 1))
        self.assertEqual(self.req("GET", "/", {"Cookie": other})[0], 401)                      # 다른 배포의 쿠키
        self.assertEqual(self.req("GET", "/", {"Cookie": "aimem_deploy_%d=%s" % (self.port, self.TOKEN)})[0], 401)

    def test_bearer_passes_and_the_token_stays_at_the_gate(self):
        self.assertEqual(self.req("GET", "/", {"Authorization": "Bearer " + self.TOKEN})[0], 200)
        code, _, body = self.req("POST", "/api/x", {"Authorization": "Bearer " + self.TOKEN,
                                                    "Cookie": "mine=1; " + self.cookie()}, b"abc")
        seen = json.loads(body)
        self.assertEqual((code, seen["len"]), (200, 3))
        self.assertNotIn("authorization", seen["headers"])
        self.assertEqual(seen["headers"]["cookie"], "mine=1")
        self.assertIsNone(seen["token_env"])
        self.assertNotIn(self.TOKEN, body.decode())

    def test_login_sets_a_cookie_that_opens_everything(self):
        self.assertEqual(self.req("GET", "/~deploy/login")[0], 401)
        code, hdr, body = self.req("POST", "/~deploy/login", {"Content-Type": "application/x-www-form-urlencoded"}, b"token=wrong")
        self.assertEqual(code, 401)
        self.assertNotIn("set-cookie", hdr)
        self.assertIn("맞지 않습니다", body.decode())
        code, hdr, _ = self.req("POST", "/~deploy/login", {"Content-Type": "application/x-www-form-urlencoded"},
                                ("token=" + self.TOKEN).encode())
        self.assertEqual((code, hdr["location"]), (303, "/"))
        cookie = hdr["set-cookie"]
        self.assertTrue(cookie.startswith(self.cookie() + ";"))
        self.assertIn("HttpOnly", cookie)
        self.assertNotIn(self.TOKEN, cookie)
        pair = cookie.split(";")[0]
        self.assertEqual(self.req("GET", "/", {"Cookie": pair})[0], 200)
        self.assertEqual(self.req("GET", "/api/x", {"Cookie": "a=b; " + pair})[0], 200)
        self.assertEqual(self.req("GET", "/~deploy/login", {"Cookie": pair})[0], 303)
        self.assertEqual(self.req("POST", "/~deploy/login", body=b"t" * 5000)[0], 400)


@unittest.skipUnless(shutil.which("openssl"), "openssl 이 없습니다")
class TlsGateTest(GateCase):
    TOKEN = "tok-TLS"
    TLS = True

    def test_over_tls(self):
        self.assertEqual(self.req("GET", "/")[0], 401)
        code, hdr, _ = self.req("POST", "/~deploy/login", body=("token=" + self.TOKEN).encode())
        self.assertEqual(code, 303)
        self.assertIn("Secure", hdr["set-cookie"])
        pair = hdr["set-cookie"].split(";")[0]
        code, _, body = self.req("POST", "/api/x", {"Cookie": pair, "Origin": "https://pc.example:18810"}, b"abc")
        self.assertEqual((code, json.loads(body)["len"]), (200, 3))
        self.assertEqual(self.req("POST", "/api/x", {"Cookie": pair, "Origin": "http://pc.example:18810"}, b"abc")[0], 403)


class SafeFileTest(unittest.TestCase):
    def test_parse_head(self):
        ok = deploy_gate.parse_head(b"GET /a?b=1 HTTP/1.1\r\nHost: x\r\nX-A: 1\r\n\r\n")
        self.assertEqual((ok.method, ok.path, ok.get("x-a"), ok.has_body), ("GET", "/a", "1", False))
        self.assertIsNone(deploy_gate.parse_head(b"GET /a HTTP/1.1\r\nHost: x\r\n folded\r\n\r\n"))
        self.assertIsNone(deploy_gate.parse_head(b"GET /a HTTP/1.1\r\nHost : x\r\n\r\n"))
        self.assertIsNone(deploy_gate.parse_head(b"GET /a HTTP/2\r\nHost: x\r\n\r\n"))


if __name__ == "__main__":
    unittest.main()
