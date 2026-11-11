"""T-067 인증·TLS 계약 테스트 (`tools/aimem_monitor/server.py` 의 외부 공개 구현).

구현이 정본입니다. 어긋나면 테스트를 구현에 맞추지 말고 보고하십시오.
저장소의 `.aimem/tls/` 는 건드리지 않습니다 - 모든 토큰·인증서는 임시 root 안에서만 만듭니다.
실행: `python3 -m unittest discover -s tests -p "test_aimem_monitor_auth.py" -v`
"""
import http.client
import http.server
import json
import os
import pathlib
import re
import sys
import tempfile
import threading
import unittest
from unittest import mock

TOOLS = pathlib.Path(__file__).resolve().parent.parent / "tools"
sys.path.insert(0, str(TOOLS))

from aimem_monitor import server  # noqa: E402
from aimem_monitor import (CERT_FILE, KEY_FILE, SESSION_COOKIE,  # noqa: E402
                           SESSION_VERSION, TOKEN_FILE, GITHUB_ALLOW_FILE,
                           GITHUB_CLIENT_ID_ENV, GITHUB_CLIENT_SECRET_ENV)

TOKEN = "ab" * 32
OTHER = "cd" * 32
FAR = 4102444800  # 2100-01-01


def _write(root, rel, text, mode=0o600):
    p = pathlib.Path(root) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    os.chmod(p, mode)
    return p


class EnsureTokenTests(unittest.TestCase):
    def test_create_0600_64hex_idempotent(self):
        with tempfile.TemporaryDirectory() as root:
            tok, created = server.ensure_access_token(root)
            self.assertTrue(created)
            self.assertRegex(tok, r"\A[0-9a-f]{64}\Z")
            mode = (pathlib.Path(root) / TOKEN_FILE).stat().st_mode & 0o777
            self.assertEqual(mode, 0o600)
            tok2, created2 = server.ensure_access_token(root)
            self.assertEqual(tok2, tok)
            self.assertFalse(created2)
            self.assertEqual(server.load_access_token(root), tok)

    def test_create_false_returns_none_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(server.ensure_access_token(root, create=False), (None, False))
            self.assertFalse((pathlib.Path(root) / TOKEN_FILE).exists())

    def test_malformed_existing_file_stops_and_is_not_overwritten(self):
        # 꼴이 깨진 파일은 말없이 덮지 않고 SystemExit 로 사람을 부른다 (S4 검수 9번)
        with tempfile.TemporaryDirectory() as root:
            p = _write(root, TOKEN_FILE, "short\n")
            with self.assertRaises(SystemExit) as cm:
                server.ensure_access_token(root)
            self.assertIn(str(p), str(cm.exception))
            self.assertEqual(p.read_text(encoding="utf-8"), "short\n")

    def test_well_formed_existing_file_is_read_not_created(self):
        with tempfile.TemporaryDirectory() as root:
            p = _write(root, TOKEN_FILE, TOKEN + "\n")
            self.assertEqual(server.ensure_access_token(root), (TOKEN, False))
            self.assertEqual(p.read_text(encoding="utf-8"), TOKEN + "\n")

    def test_dangling_symlink_is_not_followed(self):
        # path.exists() 가 False 로 떨어지지만 O_NOFOLLOW 가 막는다 -> OSError
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as out:
            victim = pathlib.Path(out) / "victim"
            link = pathlib.Path(root) / TOKEN_FILE
            link.parent.mkdir(parents=True, exist_ok=True)
            link.symlink_to(victim)
            with self.assertRaises(OSError):
                server.ensure_access_token(root)
            self.assertFalse(victim.exists())
            self.assertTrue(link.is_symlink())

    def test_symlink_to_malformed_file_stops(self):
        # 링크가 따라가지는 대상이 꼴이 아니면 exists() 가 True -> SystemExit, 대상은 그대로
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as out:
            target = _write(out, "target", "short\n")
            link = pathlib.Path(root) / TOKEN_FILE
            link.parent.mkdir(parents=True, exist_ok=True)
            link.symlink_to(target)
            with self.assertRaises(SystemExit):
                server.ensure_access_token(root)
            self.assertEqual(target.read_text(encoding="utf-8"), "short\n")


class LoadTokenTests(unittest.TestCase):
    def _load(self, text):
        with tempfile.TemporaryDirectory() as root:
            _write(root, TOKEN_FILE, text)
            return server.load_access_token(root)

    def test_good(self):
        self.assertEqual(self._load(TOKEN + "\n"), TOKEN)
        self.assertEqual(self._load(TOKEN), TOKEN)

    def test_bad_shapes_are_none(self):
        bad = {
            "empty": "",
            "only newline": "\n",
            "63 chars": TOKEN[:-1],
            "65 chars": TOKEN + "a",
            "uppercase": TOKEN.upper(),
            "non-hex": "g" * 64,
            "inner space": TOKEN[:10] + " " + TOKEN[10:],
            "inner newline": TOKEN[:32] + "\n" + TOKEN[32:],
            "two tokens": TOKEN + "\n" + TOKEN,
        }
        for name, text in bad.items():
            with self.subTest(name):
                self.assertIsNone(self._load(text))

    def test_missing_file_is_none(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertIsNone(server.load_access_token(root))

    def test_symlink_token_file_is_not_followed(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as out:
            target = _write(out, "target", TOKEN + "\n")
            link = pathlib.Path(root) / TOKEN_FILE
            link.parent.mkdir(parents=True, exist_ok=True)
            try:
                link.symlink_to(target)
            except OSError as exc:
                self.skipTest(f"심볼릭 링크를 만들 수 없습니다: {exc}")
            self.assertIsNone(server.load_access_token(root))
            self.assertEqual(target.read_text(encoding="utf-8"), TOKEN + "\n")

    def test_good_with_surrounding_whitespace_is_stripped(self):
        self.assertEqual(self._load(" \n" + TOKEN + "\n \t"), TOKEN)

    def test_malformed_shapes_are_none(self):
        for text in ("", "짧다", TOKEN + "a", "g" * 64):
            with self.subTest(text=text):
                self.assertIsNone(self._load(text))

    def test_token_path_directory_is_none(self):
        with tempfile.TemporaryDirectory() as root:
            path = pathlib.Path(root) / TOKEN_FILE
            path.mkdir(parents=True)
            self.assertIsNone(server.load_access_token(root))


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.now = 1_000_000
        self.exp = self.now + 3600
        self.cookie = server.sign_session(TOKEN, "token", self.exp)

    def test_roundtrip(self):
        self.assertTrue(self.cookie.startswith(SESSION_VERSION + "."))
        got = server.verify_session(TOKEN, self.cookie, now=self.now)
        self.assertEqual(got, {"subject": "token", "exp": self.exp})
        gh = server.sign_session(TOKEN, "gh:octocat", self.exp)
        self.assertEqual(server.verify_session(TOKEN, gh, now=self.now)["subject"], "gh:octocat")

    def test_cookie_shape(self):
        v, exp, subj, mac = self.cookie.split(".")
        self.assertEqual((v, exp, subj), ("v1", str(self.exp), "token"))
        self.assertRegex(mac, r"\A[0-9a-f]{64}\Z")

    def test_rejects(self):
        v, exp, subj, mac = self.cookie.split(".")
        flipped = mac[:-1] + ("0" if mac[-1] != "0" else "1")
        other_exp_mac = server.sign_session(TOKEN, "token", self.exp + 1).split(".")[3]
        cases = {
            "mac tampered": f"v1.{exp}.{subj}.{flipped}",
            "exp enlarged": f"v1.{int(exp) + 99999}.{subj}.{mac}",
            "same mac on another exp": f"v1.{int(exp) + 1}.{subj}.{mac}",
            "mac of other exp": f"v1.{exp}.{subj}.{other_exp_mac}",
            "subject swapped": f"v1.{exp}.gh:evil.{mac}",
            "v2 version": f"v2.{exp}.{subj}.{mac}",
            "too few parts": f"v1.{exp}.{subj}",
            "too many parts": f"{self.cookie}.x",
            "subject with dot": f"v1.{exp}.to.ken.{mac}",
            "subject with newline": f"v1.{exp}.to\nken.{mac}",
            "subject with semicolon": f"v1.{exp}.to;ken.{mac}",
            "empty subject": f"v1.{exp}..{mac}",
            "non-numeric exp": f"v1.1e9.{subj}.{mac}",
            "empty string": "",
            "None": None,
            "bytes": self.cookie.encode(),
        }
        for name, c in cases.items():
            with self.subTest(name):
                self.assertIsNone(server.verify_session(TOKEN, c, now=self.now))

    def test_expired(self):
        c = server.sign_session(TOKEN, "token", self.now - 1)
        self.assertIsNone(server.verify_session(TOKEN, c, now=self.now))
        # 경계: exp == now 도 만료
        c = server.sign_session(TOKEN, "token", self.now)
        self.assertIsNone(server.verify_session(TOKEN, c, now=self.now))

    def test_other_token_invalidates_all(self):
        self.assertIsNone(server.verify_session(OTHER, self.cookie, now=self.now))

    def test_no_token_is_none(self):
        self.assertIsNone(server.verify_session(None, self.cookie, now=self.now))
        self.assertIsNone(server.verify_session("", self.cookie, now=self.now))

    def test_sign_refuses_bad_subject(self):
        for bad in ("a.b", "a\nb", "a;b", "", None, "x" * 81):
            with self.subTest(repr(bad)):
                with self.assertRaises(ValueError):
                    server.sign_session(TOKEN, bad, FAR)


class GithubTests(unittest.TestCase):
    def test_enabled_needs_both_env(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(GITHUB_CLIENT_ID_ENV, None)
            os.environ.pop(GITHUB_CLIENT_SECRET_ENV, None)
            self.assertFalse(server.github_enabled())
            os.environ[GITHUB_CLIENT_ID_ENV] = "id"
            self.assertFalse(server.github_enabled())
            os.environ.pop(GITHUB_CLIENT_ID_ENV)
            os.environ[GITHUB_CLIENT_SECRET_ENV] = "secret"
            self.assertFalse(server.github_enabled())
            os.environ[GITHUB_CLIENT_ID_ENV] = "id"
            self.assertTrue(server.github_enabled())

    def test_enabled_empty_value_is_false(self):
        with mock.patch.dict(os.environ, {GITHUB_CLIENT_ID_ENV: "", GITHUB_CLIENT_SECRET_ENV: "s"}):
            self.assertFalse(server.github_enabled())

    def test_allowed_logins_missing_file_is_empty_set(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(server.github_allowed_logins(root), set())

    def test_allowed_logins_parsing(self):
        with tempfile.TemporaryDirectory() as root:
            _write(root, GITHUB_ALLOW_FILE,
                   "# 주석\n\nOctoCat\n  Alice  # 뒤 주석\n\n   \n#bob\nCAROL\n")
            self.assertEqual(server.github_allowed_logins(root), {"octocat", "alice", "carol"})


class LoginGuardTests(unittest.TestCase):
    def test_limit_delay_reset(self):
        g = server.LoginGuard(window=60, limit=3, delay=2.0)
        t = 1000.0
        for _ in range(3):
            self.assertEqual(g.check("1.1.1.1", now=t), 0.0)
            g.fail("1.1.1.1", now=t)
        self.assertGreater(g.check("1.1.1.1", now=t), 0.0)
        # 다른 IP 는 영향이 없다
        self.assertEqual(g.check("2.2.2.2", now=t), 0.0)
        g.reset("1.1.1.1")
        self.assertEqual(g.check("1.1.1.1", now=t), 0.0)

    def test_delay_grows_with_more_failures(self):
        g = server.LoginGuard(window=60, limit=2, delay=1.0)
        for _ in range(2):
            g.fail("ip", now=0.0)
        first = g.check("ip", now=0.0)
        g.fail("ip", now=0.0)
        self.assertGreater(g.check("ip", now=0.0), first)

    def test_window_expires(self):
        g = server.LoginGuard(window=60, limit=2, delay=1.0)
        for _ in range(2):
            g.fail("ip", now=1000.0)
        self.assertGreater(g.check("ip", now=1000.0), 0.0)
        self.assertGreater(g.check("ip", now=1060.0), 0.0)   # 정확히 창 길이는 아직 남는다
        self.assertEqual(g.check("ip", now=1061.0), 0.0)

    def test_reset_unknown_ip_is_noop(self):
        server.LoginGuard().reset("never-seen")


class _Srv:
    """임시 root 위에 핸들러를 포트 0 으로 띄웁니다."""

    def __init__(self, root, require_auth=True, token=TOKEN, tls=False):
        self.guard = server.LoginGuard()
        handler = type("H", (server.Handler,), {
            "root": pathlib.Path(root), "require_auth": require_auth, "tls": tls,
            "access_token": token if require_auth else None, "guard": self.guard,
            "timeout": 5,
            "log_message": lambda *a, **k: None,
        })
        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(5)

    def req(self, method, path, headers=None, body=None, raw_headers=None):
        """(status, headers(list), body bytes). `path` 는 **가공 없이** 그대로 보냅니다."""
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            c.putrequest(method, path, skip_host=False, skip_accept_encoding=True)
            for k, v in (headers or {}).items():
                c.putheader(k, v)
            for k, v in (raw_headers or []):
                c.putheader(k, v)
            if body is not None:
                c.putheader("Content-Length", str(len(body)))
                c.endheaders(body)
            else:
                c.endheaders()
            r = c.getresponse()
            data = r.read()
            return r.status, r.getheaders(), data
        finally:
            c.close()


def _h(headers, name):
    return [v for k, v in headers if k.lower() == name.lower()]


class AuthHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.root = cls._tmp.name
        # `_subject()` 가 `gh:` 주체마다 허용 목록을 다시 봅니다 (R12 T-156).
        # 목록이 없으면 빈 집합이라 어떤 GitHub 주체도 못 들어옵니다.
        _write(cls.root, GITHUB_ALLOW_FILE, "octocat\n")
        cls.srv = _Srv(cls.root)

    @classmethod
    def tearDownClass(cls):
        cls.srv.close()
        cls._tmp.cleanup()

    BEARER = {"Authorization": "Bearer " + TOKEN}

    def get(self, path, headers=None):
        return self.srv.req("GET", path, headers)

    def login_cookie(self):
        s, h, b = self.srv.req("POST", "/api/login", {"Content-Type": "application/json"},
                               json.dumps({"token": TOKEN}).encode())
        self.assertEqual(s, 200, b)
        sc = _h(h, "Set-Cookie")[0]
        return sc, sc.split(";")[0]          # (전체 헤더, `name=value`)

    # 7
    def test_unauthenticated_api_and_static_are_401(self):
        for p in ("/api/state", "/api/health", "/static/app.js", "/app.js",
                  "/api/runs/20260101T000000Z-S1", "/api/nope", "/static/../server.py"):
            with self.subTest(p):
                s, _, b = self.get(p)
                self.assertEqual(s, 401, b)
                self.assertFalse(json.loads(b)["ok"])

    def test_unauthenticated_post_requests_is_401(self):
        s, _, _ = self.srv.req("POST", "/api/requests", {"Content-Type": "application/json"}, b"{}")
        self.assertEqual(s, 401)

    # 8
    def test_root_redirects_to_login(self):
        for p in ("/", "/index.html"):
            with self.subTest(p):
                s, h, _ = self.get(p)
                self.assertEqual(s, 302)
                self.assertEqual(_h(h, "Location"), ["/login"])

    def test_redirect_only_for_get_head(self):
        s, _, _ = self.srv.req("POST", "/", {"Content-Type": "application/json"}, b"{}")
        self.assertEqual(s, 401)

    # 9
    def test_exempt_paths(self):
        s, _, _ = self.get("/login")
        self.assertEqual(s, 200)
        s, _, b = self.get("/api/authinfo")
        self.assertEqual(s, 200)
        info = json.loads(b)
        self.assertTrue(info["auth_required"])
        self.assertFalse(info["authenticated"])
        self.assertFalse(info["tls"])

    # 10
    def test_bearer(self):
        s, _, _ = self.get("/api/health", self.BEARER)
        self.assertEqual(s, 200)
        s, _, _ = self.get("/api/health", {"Authorization": "Bearer " + OTHER})
        self.assertEqual(s, 401)
        s, _, _ = self.get("/api/health", {"Authorization": "Bearer "})
        self.assertEqual(s, 401)
        s, _, _ = self.get("/api/health", {"Authorization": "Bearer"})
        self.assertEqual(s, 401)
        s, _, _ = self.get("/api/health", {"Authorization": "Basic " + TOKEN})
        self.assertEqual(s, 401)
        s, _, _ = self.get("/api/health", {"Authorization": TOKEN})
        self.assertEqual(s, 401)

    def test_bearer_wrong_does_not_fall_back_to_valid_cookie(self):
        # 구현 계약: Authorization: Bearer 가 있으면 그것만 본다.
        _, ck = self.login_cookie()
        s, _, _ = self.get("/api/health", {"Authorization": "Bearer " + OTHER, "Cookie": ck})
        self.assertEqual(s, 401)

    # 11
    def test_login_success_cookie_flags(self):
        s, h, b = self.srv.req("POST", "/api/login", {"Content-Type": "application/json"},
                               json.dumps({"token": TOKEN}).encode())
        self.assertEqual(s, 200)
        self.assertEqual(json.loads(b), {"ok": True, "redirect": "/"})
        sc = _h(h, "Set-Cookie")
        self.assertEqual(len(sc), 1)
        c = sc[0]
        self.assertTrue(c.startswith(SESSION_COOKIE + "=v1."))
        for want in ("HttpOnly", "SameSite=Strict", "Path=/"):
            self.assertIn(want, c)
        self.assertRegex(c, r"Max-Age=\d+")
        self.assertNotIn("Secure", c)            # TLS 가 아니므로

    def test_login_wrong_token_is_401_without_cookie(self):
        for payload in ({"token": OTHER}, {"token": ""}, {"token": 123}, {}, [], {"token": None}):
            with self.subTest(payload):
                s, h, _ = self.srv.req("POST", "/api/login", {"Content-Type": "application/json"},
                                       json.dumps(payload).encode())
                self.assertEqual(s, 401)
                self.assertEqual(_h(h, "Set-Cookie"), [])
        self.srv.guard.reset("127.0.0.1")        # 다른 테스트가 지연을 맞지 않도록

    def test_login_cookie_is_secure_under_tls(self):
        # 없으면 TLS 로그인 쿠키에 Secure 가 빠져도 아무 검사가 빨개지지 않는다.
        body = json.dumps({"token": TOKEN}).encode()
        srv = _Srv(self.root, tls=True)
        self.addCleanup(srv.close)
        s, h, b = srv.req("POST", "/api/login", {"Content-Type": "application/json"}, body)
        self.assertEqual(s, 200, b)
        c = _h(h, "Set-Cookie")[0]
        for want in ("Secure", "HttpOnly", "SameSite=Strict"):
            self.assertIn(want, c)

        plain = _Srv(self.root, tls=False)
        self.addCleanup(plain.close)
        s, h, b = plain.req("POST", "/api/login", {"Content-Type": "application/json"}, body)
        self.assertEqual(s, 200, b)
        c = _h(h, "Set-Cookie")[0]
        self.assertNotIn("Secure", c)
        self.assertIn("HttpOnly", c)

    def test_login_bad_json_is_400(self):
        s, _, _ = self.srv.req("POST", "/api/login", {"Content-Type": "application/json"}, b"{not json")
        self.assertEqual(s, 400)

    # 12
    def test_cookie_grants_access_and_tamper_is_401(self):
        _, ck = self.login_cookie()
        s, _, _ = self.get("/api/state", {"Cookie": ck})
        self.assertEqual(s, 200)
        s, _, b = self.get("/api/authinfo", {"Cookie": ck})
        self.assertTrue(json.loads(b)["authenticated"])
        name, val = ck.split("=", 1)
        flipped = val[:-1] + ("0" if val[-1] != "0" else "1")
        for bad in (f"{name}={flipped}", f"{name}=", f"{name}=garbage", "other=" + val,
                    f"{name}=" + val.replace("v1.", "v2.", 1)):
            with self.subTest(bad[:40]):
                s, _, _ = self.get("/api/state", {"Cookie": bad})
                self.assertEqual(s, 401)

    def test_cookie_signed_with_other_token_is_401(self):
        c = server.sign_session(OTHER, "token", FAR)
        s, _, _ = self.get("/api/state", {"Cookie": f"{SESSION_COOKIE}={c}"})
        self.assertEqual(s, 401)

    def test_expired_cookie_is_401(self):
        c = server.sign_session(TOKEN, "token", 1)
        s, _, _ = self.get("/api/state", {"Cookie": f"{SESSION_COOKIE}={c}"})
        self.assertEqual(s, 401)

    def test_github_subject_cookie_is_accepted(self):
        c = server.sign_session(TOKEN, "gh:octocat", FAR)
        s, _, _ = self.get("/api/health", {"Cookie": f"{SESSION_COOKIE}={c}"})
        self.assertEqual(s, 200)

    def test_github_subject_outside_allowlist_is_401(self):
        """허용 목록에서 지운 계정의 쿠키는 서명이 멀쩡해도 끊깁니다 (R12 T-156)."""
        c = server.sign_session(TOKEN, "gh:someoneelse", FAR)
        s, _, _ = self.get("/api/health", {"Cookie": f"{SESSION_COOKIE}={c}"})
        self.assertEqual(s, 401)

    # 13
    def test_logout_expires_cookie(self):
        s, h, _ = self.srv.req("POST", "/api/logout", {"Content-Type": "application/json"}, b"{}")
        self.assertEqual(s, 200)
        c = _h(h, "Set-Cookie")[0]
        self.assertIn("Max-Age=0", c)
        self.assertTrue(c.startswith(SESSION_COOKIE + "=;") or c.startswith(SESSION_COOKIE + "=\"\""))

    # 14
    def test_bypass_attempts_are_denied(self):
        paths = ["/login/../api/state", "//api/state", "/./api/state", "/api/state/",
                 "/LOGIN", "/login%2f..%2fapi/state", "/favicon.ico/../api/state",
                 "/login/..%2fapi/state", "/api/login/../state", "/%61pi/state",
                 "/login;/../api/state", "/login%00", "/login%00/../api/state",
                 "/api/state%00.js", "/.%2e/api/state",
                 "/static/..%2fapi/state"]
        for p in paths:
            with self.subTest(p):
                s, _, b = self.get(p)
                self.assertNotEqual(s, 200, b[:200])
                self.assertIn(s, (400, 401, 404))
                self.assertNotIn(b"\"aimem\"", b)       # state 본문이 새지 않았다

    def test_bypass_attempts_are_401_except_nul(self):
        # 브리프 14: 널바이트를 뺀 우회는 전부 정확히 401.
        for p in ("/login/../api/state", "//api/state", "/./api/state", "/api/state/",
                  "/LOGIN", "/login%2f..%2fapi/state", "/favicon.ico/../api/state"):
            with self.subTest(p):
                self.assertEqual(self.get(p)[0], 401)

    def test_nul_byte_is_rejected_before_auth(self):
        # 구현은 널바이트를 인증보다 먼저 400 으로 거른다 (브리프는 401 이라 적었다).
        s, _, _ = self.get("/login%00")
        self.assertEqual(s, 400)

    def test_bypass_with_valid_auth_is_normalized(self):
        # 인증되면 정규화된 경로로 라우팅된다 (`/api/state/` -> `/api/state`)
        s, _, _ = self.get("/api/state/", self.BEARER)
        self.assertEqual(s, 200)

    # 15
    def test_post_requests_guards(self):
        auth = dict(self.BEARER)
        host = f"127.0.0.1:{self.srv.port}"
        js = {**auth, "Content-Type": "application/json"}
        s, _, _ = self.srv.req("POST", "/api/requests", {**auth, "Content-Type": "text/plain"}, b"{}")
        self.assertEqual(s, 415)
        s, _, _ = self.srv.req("POST", "/api/requests", auth, b"{}")      # Content-Type 없음
        self.assertEqual(s, 415)
        s, _, _ = self.srv.req("POST", "/api/requests", {**js, "Origin": "http://evil.example"}, b"{}")
        self.assertEqual(s, 403)
        s, _, _ = self.srv.req("POST", "/api/requests", {**js, "Origin": f"http://{host}"}, b"not json")
        self.assertEqual(s, 400)             # Origin 은 통과, 본문에서 걸림
        # Content-Length 없음 -> 411
        s, _, _ = self.srv.req("POST", "/api/requests", js)
        self.assertEqual(s, 411)
        # 음수 -> 400
        s, _, _ = self.srv.req("POST", "/api/requests", js, raw_headers=[("Content-Length", "-1")])
        self.assertEqual(s, 400)
        s, _, _ = self.srv.req("POST", "/api/requests", js, raw_headers=[("Content-Length", "abc")])
        self.assertEqual(s, 400)
        # 상한 초과 -> 413 (본문을 읽기 전에 거른다)
        s, _, _ = self.srv.req("POST", "/api/requests", js,
                               raw_headers=[("Content-Length", str(server.MAX_BODY + 1))])
        self.assertEqual(s, 413)

    def test_post_requests_denied_paths_write_nothing(self):
        self.srv.req("POST", "/api/requests", {**self.BEARER, "Content-Type": "text/plain"}, b"{}")
        self.assertFalse((pathlib.Path(self.root) / ".aimem" / "requests").exists())

    # 16
    def test_security_headers_everywhere(self):
        cases = [("GET", "/api/state", None),            # 401
                 ("GET", "/", None),                     # 302
                 ("GET", "/login", None),                # 200
                 ("GET", "/api/health", self.BEARER),    # 200
                 ("GET", "/api/nope", self.BEARER),      # 404
                 ("POST", "/api/logout", None)]
        for m, p, hd in cases:
            with self.subTest(f"{m} {p}"):
                body = b"{}" if m == "POST" else None
                s, h, _ = self.srv.req(m, p, {**(hd or {}), **({"Content-Type": "application/json"} if body else {})}, body)
                self.assertIn(s, (200, 302, 401, 404))
                self.assertEqual(_h(h, "X-Content-Type-Options"), ["nosniff"])
                self.assertEqual(_h(h, "Referrer-Policy"), ["no-referrer"])
                csp = _h(h, "Content-Security-Policy")
                self.assertEqual(len(csp), 1)
                self.assertIn("default-src 'self'", csp[0])
                self.assertIn("frame-ancestors 'none'", csp[0])
                self.assertEqual(_h(h, "Strict-Transport-Security"), [])   # TLS 가 아니므로 HSTS 없음

    def test_server_header_hides_python_version(self):
        for p in ("/api/state", "/", "/login"):
            with self.subTest(p):
                _, h, _ = self.get(p)
                sv = _h(h, "Server")
                self.assertEqual(len(sv), 1)
                self.assertNotRegex(sv[0], r"(?i)python|\d+\.\d+")
                self.assertNotIn("BaseHTTP", sv[0])

    def test_secret_value_is_scrubbed_from_json(self):
        # 마지막 방어선: 응답 본문에 접근 토큰 값이 나가면 `***` 로 가려진다.
        h = object.__new__(type("X", (server.Handler,), {"access_token": TOKEN}))
        out = h._scrub_secrets('{"x": "%s"}' % TOKEN)
        self.assertNotIn(TOKEN, out)
        self.assertIn("***", out)

    def test_login_fail_throttle_is_delay_not_block(self):
        g = server.LoginGuard(window=60, limit=1, delay=0.0)
        g.fail("x", now=0.0)
        self.assertEqual(g.check("x", now=0.0), 0.0)     # delay=0 이면 상한을 넘어도 막지 않는다


class AuthOffHttpTests(unittest.TestCase):
    """17: 인증을 끄면 예전 그대로 - 공개 작업이 로컬 동작을 깨지 않았다."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.srv = _Srv(cls._tmp.name, require_auth=False)

    @classmethod
    def tearDownClass(cls):
        cls.srv.close()
        cls._tmp.cleanup()

    def test_open_routes(self):
        s, _, b = self.srv.req("GET", "/api/state")
        self.assertEqual(s, 200)
        self.assertIsInstance(json.loads(b), dict)
        s, _, _ = self.srv.req("GET", "/")
        self.assertEqual(s, 200)
        s, _, _ = self.srv.req("GET", "/api/health")
        self.assertEqual(s, 200)
        s, _, _ = self.srv.req("GET", "/static/app.js")
        self.assertEqual(s, 200)

    def test_authinfo_reports_off(self):
        s, _, b = self.srv.req("GET", "/api/authinfo")
        self.assertEqual(s, 200)
        self.assertFalse(json.loads(b)["auth_required"])

    def test_bearer_header_is_ignored_when_off(self):
        s, _, _ = self.srv.req("GET", "/api/health", {"Authorization": "Bearer nonsense"})
        self.assertEqual(s, 200)

    def test_default_handler_class_is_auth_off(self):
        # `serve()` 를 거치지 않은 맨 Handler 의 기본값이 옛 동작이어야 한다.
        self.assertFalse(server.Handler.require_auth)
        self.assertFalse(server.Handler.tls)
        self.assertIsNone(server.Handler.access_token)


class TlsContextTests(unittest.TestCase):
    def test_missing_cert_exits_with_howto(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(SystemExit) as cm:
                server.build_ssl_context(root)
            self.assertIn("openssl", str(cm.exception))

    def test_cert_without_key_exits(self):
        with tempfile.TemporaryDirectory() as root:
            _write(root, CERT_FILE, "dummy")
            with self.assertRaises(SystemExit):
                server.build_ssl_context(root)

    def test_loose_key_permission_exits(self):
        with tempfile.TemporaryDirectory() as root:
            _write(root, CERT_FILE, "dummy", 0o644)
            _write(root, KEY_FILE, "dummy", 0o644)
            with self.assertRaises(SystemExit) as cm:
                server.build_ssl_context(root)
            self.assertRegex(str(cm.exception), r"권한|chmod")

    def test_group_readable_key_exits(self):
        with tempfile.TemporaryDirectory() as root:
            _write(root, CERT_FILE, "dummy")
            _write(root, KEY_FILE, "dummy", 0o640)
            with self.assertRaises(SystemExit):
                server.build_ssl_context(root)

    def test_good_cert_builds_context(self):
        # 브리프 지시: 자체서명 인증서를 tests/ 안에서 만들지 않는다(`openssl` 호출 금지,
        # 저장소 `.aimem/tls/` 실물 복사도 금지). 정상 컨텍스트 생성은 건너뛰고 보고에 적는다.
        self.skipTest("정상 인증서 픽스처를 만들지 않기로 함 (T-067 브리프). 보고서 '못 덮은 것' 참조")


if __name__ == "__main__":
    unittest.main()
