"""접근 제어 보강과 HTTPS 전환 부작용 (2026-11-10, 클로드 코드).

- 비밀 설정 파일(저장소 루트 `.env`)을 읽되 권한이 넓으면 거절, 셸 환경을 덮지 않음
- 감사 로그: 줄 형식, 심볼릭 링크 거절, 토큰을 적지 않음
- `authinfo.who`, `subject_label`
- 관리 명령: 토큰 교체(0600·값 변경), GitHub 허용·삭제, 잘못된 계정 거절
- HSTS 는 이름(도메인)으로 들어온 요청에만 (localhost·IP 제외)
- HTTPS 포트로 들어온 평문 HTTP 는 https 로 301 (실제 TLS 서버로 확인 - openssl 있을 때만)
"""
import contextlib
import http.client
import http.server
import io
import json
import os
import pathlib
import shutil
import socket
import ssl
import sys
import subprocess
import tempfile
import threading
import time
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from aimem_monitor import TOKEN_FILE, GITHUB_ALLOW_FILE, server, admin  # noqa: E402


def _write(root, rel, text, mode=0o600):
    p = pathlib.Path(root) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    os.chmod(p, mode)
    return p


class EnvFileTest(unittest.TestCase):
    KEYS = ("KISTI_API_KEY", "GITHUB_CLIENT_ID", "GITHUB_CLIENT_SECRET")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        p = mock.patch.dict(os.environ, {k: "" for k in self.KEYS})
        p.start()
        self.addCleanup(p.stop)
        for k in self.KEYS:
            os.environ.pop(k, None)

    def test_reads_private_file_without_overriding_env(self):
        _write(self.root, server.MONITOR_ENV_FILE,
               '# 주석\nGITHUB_CLIENT_ID="abc"\nGITHUB_CLIENT_SECRET=s3\nKISTI_API_KEY=k1\nOTHER=x\n')
        os.environ["KISTI_API_KEY"] = "from-shell"
        loaded = dict(server.load_monitor_env(self.root))
        self.assertEqual(os.environ["GITHUB_CLIENT_ID"], "abc")
        self.assertEqual(os.environ["GITHUB_CLIENT_SECRET"], "s3")
        self.assertEqual(os.environ["KISTI_API_KEY"], "from-shell")    # 셸이 이긴다
        self.assertNotIn("KISTI_API_KEY", loaded)
        self.assertNotIn("OTHER", os.environ)                          # 정해진 키만

    def test_world_readable_file_is_ignored(self):
        _write(self.root, server.MONITOR_ENV_FILE, "GITHUB_CLIENT_ID=abc\n", 0o644)
        with contextlib.redirect_stderr(io.StringIO()) as err:
            server.load_monitor_env(self.root)
        self.assertNotIn("GITHUB_CLIENT_ID", os.environ)
        self.assertIn("chmod 600", err.getvalue())

    def test_no_other_env_files_are_read(self):
        """`.aimem/tls/monitor.env` 와 `~/.openclaw/.env` 는 더는 읽지 않는다 - `.env` 한 곳뿐."""
        _write(self.root, ".aimem/tls/monitor.env", "KISTI_API_KEY=old\nGITHUB_CLIENT_ID=old\n")
        self.assertEqual(server.load_monitor_env(self.root), [])
        self.assertNotIn("KISTI_API_KEY", os.environ)
        self.assertNotIn("GITHUB_CLIENT_ID", os.environ)
        self.assertFalse(hasattr(server, "OPENCLAW_ENV_FILE"))


class AuditTest(unittest.TestCase):
    def test_line_format_and_control_chars(self):
        with tempfile.TemporaryDirectory() as root:
            server.audit(root, "login-fail", "1.2.3.4", None, "x\x1b[31m")
            line = (pathlib.Path(root) / server.AUDIT_LOG).read_text(encoding="utf-8").strip()
            parts = line.split("\t")
            self.assertEqual(parts[1:4], ["login-fail", "1.2.3.4", "-"])
            self.assertNotIn("\x1b", line)
            self.assertEqual(oct((pathlib.Path(root) / server.AUDIT_LOG).stat().st_mode & 0o777), "0o600")

    def test_symlinked_log_is_refused(self):
        with tempfile.TemporaryDirectory() as root:
            target = pathlib.Path(root) / "elsewhere.txt"
            target.write_text("", encoding="utf-8")
            log = pathlib.Path(root) / server.AUDIT_LOG
            log.parent.mkdir(parents=True, exist_ok=True)
            log.symlink_to(target)
            server.audit(root, "x")
            self.assertEqual(target.read_text(encoding="utf-8"), "")

    def test_subject_label(self):
        self.assertEqual(server.subject_label("token"), "접근 토큰")
        self.assertEqual(server.subject_label("gh:tsyi"), "GitHub tsyi")
        self.assertIsNone(server.subject_label(None))


class RevokedAuditTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        self.token = "c" * 64
        _write(self.root, GITHUB_ALLOW_FILE, "octo-cat\n")
        handler = type("H", (server.Handler,), {
            "root": self.root, "require_auth": True, "tls": False,
            "access_token": self.token, "guard": server.LoginGuard(),
            "timeout": 5, "log_message": lambda *a, **k: None,
        })
        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        with server._revoked_lock:
            server._revoked_last.clear()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self._tmp.cleanup()
        with server._revoked_lock:
            server._revoked_last.clear()

    def cookie(self, login="octo-cat"):
        exp = int(time.time()) + 600
        return server.sign_session(self.token, server.SESSION_SUBJECT_GITHUB_PREFIX + login, exp)

    def get(self, path, login="octo-cat"):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("GET", path, headers={"Cookie": f"{server.SESSION_COOKIE}={self.cookie(login)}"})
        r = conn.getresponse()
        body = r.read()
        status = r.status
        conn.close()
        return status, body

    def revoked_lines(self):
        p = self.root / server.AUDIT_LOG
        if not p.exists():
            return []
        return [line.split("\t") for line in p.read_text(encoding="utf-8").splitlines()
                if line.split("\t")[1] == "github-revoked"]

    def test_revoked_account_is_audited_once(self):
        status, body = self.get("/api/authinfo")
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)["authenticated"])
        _write(self.root, GITHUB_ALLOW_FILE, "# no accounts\n")
        status, _ = self.get("/api/state")
        self.assertEqual(status, 401)
        lines = self.revoked_lines()
        self.assertEqual(len(lines), 1, lines)
        self.assertEqual(lines[0][1:], ["github-revoked", "127.0.0.1", "gh:octo-cat",
                                        "GET /api/state 허용 목록 밖"])
        self.assertNotIn(self.token, (self.root / server.AUDIT_LOG).read_text(encoding="utf-8"))

    def test_repeated_revoked_requests_do_not_add_lines(self):
        _write(self.root, GITHUB_ALLOW_FILE, "# no accounts\n")
        for _ in range(3):
            status, _ = self.get("/api/state")
            self.assertEqual(status, 401)
        self.assertEqual(len(self.revoked_lines()), 1)

    def test_zero_suppression_window_allows_new_lines(self):
        _write(self.root, GITHUB_ALLOW_FILE, "# no accounts\n")
        with mock.patch.object(server, "_REVOKED_AUDIT_MIN_SEC", 0):
            for _ in range(2):
                status, _ = self.get("/api/state")
                self.assertEqual(status, 401)
        self.assertEqual(len(self.revoked_lines()), 2)


class AdminTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)

    def run_admin(self, *argv):
        with contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()):
            try:
                rc = admin.main(list(argv), self.root)
            except SystemExit as e:          # argparse 거절(예: '-x' 를 옵션으로 읽음)
                rc = e.code
        return rc, out.getvalue()

    def test_token_rotate_changes_value_and_is_private(self):
        _write(self.root, TOKEN_FILE, "a" * 64 + "\n")
        rc, out = self.run_admin("token", "rotate")
        self.assertEqual(rc, 0)
        new = server.load_access_token(self.root)
        self.assertNotEqual(new, "a" * 64)
        self.assertEqual(out.strip(), new)
        self.assertEqual((self.root / TOKEN_FILE).stat().st_mode & 0o777, 0o600)
        log = (self.root / server.AUDIT_LOG).read_text(encoding="utf-8")
        self.assertIn("token-rotate", log)
        self.assertNotIn(new, log)                                     # 감사 로그에 토큰을 적지 않는다

    def test_rotated_token_invalidates_old_sessions(self):
        old = "b" * 64
        cookie = server.sign_session(old, "token", 2_000_000_000)
        _write(self.root, TOKEN_FILE, old + "\n")
        self.run_admin("token", "rotate")
        self.assertIsNone(server.verify_session(server.load_access_token(self.root), cookie))

    def test_github_allow_deny(self):
        self.assertEqual(self.run_admin("github", "allow", "Octo-Cat")[0], 0)
        self.assertIn("octo-cat", server.github_allowed_logins(self.root))
        self.assertEqual((self.root / GITHUB_ALLOW_FILE).stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.run_admin("github", "allow", "octo-cat")[0], 0)   # 중복은 그대로
        self.assertEqual(len(server.github_allowed_logins(self.root)), 1)
        self.assertEqual(self.run_admin("github", "deny", "OCTO-CAT")[0], 0)
        self.assertEqual(server.github_allowed_logins(self.root), set())

    def test_github_bad_login_rejected(self):
        for bad in ("-x", "a b", "a/../b", "x" * 40):
            self.assertEqual(self.run_admin("github", "allow", bad)[0], 2, bad)


class HstsTest(unittest.TestCase):
    def want(self, host, tls=True):
        h = mock.Mock(spec=["tls", "headers"])
        h.tls = tls
        h.headers = {"Host": host}
        return server.Handler._want_hsts(h)

    def test_hsts_only_for_named_hosts_over_tls(self):
        self.assertTrue(self.want("aimem.example.org:18799"))
        self.assertTrue(self.want("aimem-fleet:18799"))
        for host in ("localhost:18799", "127.0.0.1:18799", "172.26.105.67", "[::1]:18799", "x.localhost", ""):
            self.assertFalse(self.want(host), host)
        self.assertFalse(self.want("aimem.example.org", tls=False))


class PlainHttpOnTlsPortTest(unittest.TestCase):
    """실제 TLS 서버: 평문 HTTP 는 https 로 301, TLS 는 그대로 동작."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.root = pathlib.Path(cls._tmp.name)
        with contextlib.redirect_stdout(io.StringIO()):
            admin.cert_renew(cls.root, days=2)
        handler = type("H", (server.Handler,), {"root": cls.root, "require_auth": True, "tls": True,
                                                 "access_token": "c" * 64, "guard": server.LoginGuard(),
                                                 "timeout": 5, "log_message": lambda *a, **k: None})
        cls.httpd = server.TLSThreadingHTTPServer(("127.0.0.1", 0), handler)
        cls.httpd.ssl_context = server.build_ssl_context(cls.root)
        cls.httpd.daemon_threads = True
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls._tmp.cleanup()

    def raw(self, data):
        with socket.create_connection(("127.0.0.1", self.port), timeout=5) as s:
            s.sendall(data)
            return s.recv(4096).decode("latin-1")

    def test_plain_http_redirects_to_https(self):
        resp = self.raw(f"GET /api/state?x=1 HTTP/1.1\r\nHost: 127.0.0.1:{self.port}\r\n\r\n".encode())
        self.assertTrue(resp.startswith("HTTP/1.1 301"), resp[:80])
        self.assertIn(f"Location: https://127.0.0.1:{self.port}/api/state?x=1\r\n", resp)

    def test_plain_http_header_injection_is_not_reflected(self):
        resp = self.raw(b"GET /a%0d%0aSet-Cookie:x HTTP/1.1\r\nHost: evil\r\nX: \r\n\r\n")
        loc = [l for l in resp.split("\r\n") if l.startswith("Location:")]
        self.assertEqual(len(loc), 1)
        self.assertNotIn("Set-Cookie", resp.split("\r\n\r\n")[0].replace(loc[0], ""))

    def test_tls_still_works_and_authinfo_has_who(self):
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        c = http.client.HTTPSConnection("127.0.0.1", self.port, timeout=5, context=ctx)
        c.request("GET", "/api/authinfo", headers={"Authorization": "Bearer " + "c" * 64})
        r = c.getresponse()
        body = json.loads(r.read())
        self.assertEqual(r.status, 200)
        self.assertEqual((body["tls"], body["authenticated"], body["who"]), (True, True, "접근 토큰"))
        self.assertIsNone(r.getheader("Strict-Transport-Security"))      # IP 로 들어왔으므로 HSTS 없음
        c.close()


if __name__ == "__main__":
    unittest.main()


class CertRenewWithCATests(unittest.TestCase):
    """`admin cert renew --ca-dir` - 사설 CA 서명 + 발급 조건 기억 (2026-11-10, 공유 CA 전환)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        self.ca = self.root / "ca"
        self.ca.mkdir()
        subprocess.run(["openssl", "req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:prime256v1",
                        "-nodes", "-keyout", str(self.ca / "ca.key"), "-out", str(self.ca / "ca.crt"), "-days", "2",
                        "-subj", "/CN=test CA", "-addext", "basicConstraints=critical,CA:TRUE"],
                       check=True, capture_output=True)

    def tearDown(self):
        self._tmp.cleanup()

    def _x509(self, *args):
        return subprocess.run(["openssl", "x509", "-in", str(self.root / admin.CERT_FILE), "-noout", *args],
                              capture_output=True, text=True, check=True).stdout

    def test_ca_signed_and_profile_remembered(self):
        with contextlib.redirect_stdout(io.StringIO()):
            admin.cert_renew(self.root, extra_ips=["192.0.2.7"], extra_dns=["pc-name"], days=2, ca_dir=self.ca)
        self.assertIn("CN=test CA", self._x509("-issuer"))
        san = self._x509("-ext", "subjectAltName")
        self.assertIn("192.0.2.7", san)
        self.assertIn("pc-name", san)
        self.assertTrue((self.root / admin.CA_FILE).exists(), "CA 공개 인증서 사본")
        self.assertFalse(list((self.root / ".aimem/tls").glob("*.tmp")), "임시 CSR/ext 가 남으면 안 된다")
        # CA 개인키는 복사하지 않는다
        self.assertFalse((self.root / ".aimem/tls/ca.key").exists())
        # 서버가 그대로 올릴 수 있어야 한다
        server.build_ssl_context(self.root)
        # 두 번째 renew 는 인자 없이도 같은 CA·같은 SAN 을 다시 쓴다
        with contextlib.redirect_stdout(io.StringIO()):
            admin.cert_renew(self.root, days=2)
        self.assertIn("CN=test CA", self._x509("-issuer"))
        self.assertIn("192.0.2.7", self._x509("-ext", "subjectAltName"))
        # --self-signed 는 CA 를 무시한다
        with contextlib.redirect_stdout(io.StringIO()):
            admin.cert_renew(self.root, days=2, self_signed=True)
        self.assertIn("CN=aimem-fleet", self._x509("-issuer"))

    def test_missing_ca_files_is_an_error(self):
        with self.assertRaises(SystemExit):
            admin.cert_renew(self.root, days=2, ca_dir=self.root / "nowhere")


class PwaAssetsTest(unittest.TestCase):
    """폰 설치(PWA, 2026-11-10): 매니페스트·아이콘·서비스 워커는 인증 없이, app.js·API 는 여전히 인증 뒤."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.root = pathlib.Path(cls._tmp.name)
        with contextlib.redirect_stdout(io.StringIO()):
            admin.cert_renew(cls.root, days=2)
        handler = type("H", (server.Handler,), {"root": cls.root, "require_auth": True, "tls": True,
                                                 "access_token": "c" * 64, "guard": server.LoginGuard(),
                                                 "timeout": 5, "log_message": lambda *a, **k: None})
        cls.httpd = server.TLSThreadingHTTPServer(("127.0.0.1", 0), handler)
        cls.httpd.ssl_context = server.build_ssl_context(cls.root)
        cls.httpd.daemon_threads = True
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown(); cls.httpd.server_close(); cls._tmp.cleanup()

    def get(self, path):
        import http.client, ssl
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
        c = http.client.HTTPSConnection("127.0.0.1", self.port, context=ctx, timeout=5)
        c.request("GET", path); r = c.getresponse(); body = r.read(); c.close()
        return r.status, r.getheader("Content-Type") or "", body

    def test_install_assets_are_public_and_typed(self):
        st, ct, body = self.get("/manifest.webmanifest")
        self.assertEqual(st, 200); self.assertIn("manifest+json", ct)
        m = json.loads(body)
        self.assertEqual((m["display"], m["start_url"], m["scope"]), ("standalone", "/", "/"))
        self.assertTrue(any(i["sizes"] == "512x512" for i in m["icons"]))
        st, ct, body = self.get("/sw.js")
        self.assertEqual(st, 200); self.assertIn("javascript", ct)
        self.assertNotIn("caches.put(req", body.decode().split("startsWith('/api/')")[0])   # API 경로는 캐시 분기 전에 빠진다
        st, ct, body = self.get("/icon-192.png")
        self.assertEqual((st, ct), (200, "image/png")); self.assertTrue(body.startswith(b"\x89PNG"))

    def test_app_and_api_still_require_auth(self):
        self.assertEqual(self.get("/app.js")[0], 401)
        self.assertEqual(self.get("/api/state")[0], 401)
        self.assertEqual(self.get("/style.css")[0], 401)
