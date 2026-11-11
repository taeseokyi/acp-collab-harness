"""R11 적대적 검수 A 결함 1 (인증 우회)의 회귀 시험 - 진짜 소켓으로 본다.

무인증 `GET /app/<이름>/../~x/` 는 정규화하면 `/app/~x` 라 인증 문을 지났고, 라우팅은 원본을 "티켓 없음 → 발급" 으로 읽어
**유효한 12시간 티켓을 서명해 302 로 내줬다.** `urllib`·`curl` 은 `..` 를 접어 보내므로 `http.client` 로 원본 그대로 보낸다.
"""
import http.client
import http.server
import json
import pathlib
import sys
import tempfile
import threading
import time
import unittest
import urllib.parse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools"))

from aimem_monitor import server  # noqa: E402

TOKEN = "t" * 40
NAME = "알파"
Q = urllib.parse.quote(NAME)
GITHUB_LOGIN = "taeseok"


class AppGateRegression(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = pathlib.Path(tmp.name)
        web = root / "projects" / NAME / "web"
        web.mkdir(parents=True)
        (web / "index.html").write_text("<!doctype html><p id=secret>APP-BODY</p>", encoding="utf-8")
        (root / "projects" / NAME / "app.json").write_text(json.dumps({"root": "web", "entry": "index.html"}), encoding="utf-8")
        (root / "AIMEM.md").write_text("# AIMEM\n\n- **REV: 1**\n", encoding="utf-8")
        allowed = root / server.GITHUB_ALLOW_FILE
        allowed.parent.mkdir(parents=True)
        allowed.write_text(GITHUB_LOGIN + "\n", encoding="utf-8")
        handler = type("H", (server.Handler,), {"root": root, "require_auth": True, "tls": False, "access_token": TOKEN,
                                                "guard": server.LoginGuard(), "log_message": lambda *a, **k: None})
        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.addCleanup(self.httpd.server_close)
        self.addCleanup(self.httpd.shutdown)
        self.port = self.httpd.server_address[1]

    def get(self, path, headers=None):
        con = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            con.putrequest("GET", path, skip_host=False, skip_accept_encoding=True)
            for k, v in (headers or {}).items():
                con.putheader(k, v)
            con.endheaders()
            r = con.getresponse()
            return r.status, r.getheader("Location") or "", r.read()
        finally:
            con.close()

    def test_no_ticket_is_minted_without_a_session(self):
        for path in (f"/app/{Q}/../~x/", f"/app/{Q}/x/../../~x", f"/app/{Q}/../~", f"/app/{Q}/./../~/",
                     "/app/abc/../~x/", f"/app//~x/{Q}/", f"/app/~x/./{Q}/", f"/app/{Q}/%2e%2e/~x/"):
            with self.subTest(path=path):
                status, loc, body = self.get(path)
                self.assertNotIn("/app/~", loc if "." in loc.split("/app/~")[-1][:12] else "", path)   # 티켓 꼴의 Location 이 없다
                self.assertFalse(loc.startswith("/app/~") and loc[6:7].isdigit(), f"{path} -> 티켓을 내줬다: {loc}")
                self.assertIn(status, (302, 401, 404), path)
                self.assertNotIn(b"APP-BODY", body)
                if status == 302:
                    self.assertEqual(loc, "/login", path)

    def test_the_normal_flow_still_works(self):
        status, loc, _ = self.get(f"/app/{Q}/")
        self.assertEqual((status, loc), (302, "/login"))                                  # 무인증은 로그인으로
        status, loc, _ = self.get(f"/app/{Q}/", {"Authorization": "Bearer " + TOKEN})
        self.assertEqual(status, 302)
        self.assertRegex(loc, r"\A/app/~\d+\.[0-9a-f]{32}/" + Q + r"/\Z")                 # 로그인한 사람에게만 티켓
        status, _, body = self.get(loc)                                                   # 티켓 경로는 쿠키 없이
        self.assertEqual(status, 200)
        self.assertIn(b"APP-BODY", body)
        status, _, body = self.get(loc.replace("/app/~", "/app/~9", 1))                   # 위조
        self.assertEqual(status, 403)
        self.assertNotIn(b"APP-BODY", body)
        ticket = loc.split("/")[2]
        for path in (f"/app/{ticket}/../../api/state", f"/app/{ticket}/{Q}/../../../api/state"):
            self.assertIn(self.get(path)[0], (401, 404), path)                            # 티켓으로 /api 에 못 간다

    def github_headers(self, login=GITHUB_LOGIN, exp=None, token=TOKEN):
        if exp is None:
            exp = int(time.time()) + server.SESSION_TTL_SEC
        value = server.sign_session(token, f"gh:{login}", exp)
        return {"Cookie": f"{server.SESSION_COOKIE}={value}"}

    def test_github_session_gets_an_app_ticket(self):
        status, loc, body = self.get(f"/app/{Q}/", self.github_headers())
        self.assertEqual(status, 302)
        self.assertRegex(loc, r"\A/app/~\d+\.[0-9a-f]{32}/" + Q + r"/\Z")
        self.assertNotIn(b"APP-BODY", body)

    def test_github_app_ticket_opens_the_app(self):
        status, loc, _ = self.get(f"/app/{Q}/", self.github_headers())
        self.assertEqual(status, 302)
        status, _, body = self.get(loc, self.github_headers())
        self.assertEqual(status, 200)
        self.assertIn(b"APP-BODY", body)
        self.assertTrue(body.lstrip().lower().startswith(b"<!doctype html"))

    def test_github_session_outside_allowlist_gets_no_ticket(self):
        status, loc, body = self.get(f"/app/{Q}/", self.github_headers("retired-user"))
        self.assertNotIn("/app/~", loc)
        self.assertIn(status, (302, 401, 403))
        if status == 302:
            self.assertEqual(loc, "/login")
        self.assertNotIn(b"APP-BODY", body)

    def test_github_session_with_bad_signature_gets_no_ticket(self):
        headers = self.github_headers()
        name, value = headers["Cookie"].split("=", 1)
        headers["Cookie"] = name + "=" + value[:-1] + ("0" if value[-1] != "0" else "1")
        status, loc, body = self.get(f"/app/{Q}/", headers)
        self.assertNotIn("/app/~", loc)
        self.assertIn(status, (302, 401, 403))
        if status == 302:
            self.assertEqual(loc, "/login")
        self.assertNotIn(b"APP-BODY", body)

    def test_expired_github_session_gets_no_ticket(self):
        status, loc, body = self.get(f"/app/{Q}/", self.github_headers(exp=int(time.time()) - 60))
        self.assertNotIn("/app/~", loc)
        self.assertIn(status, (302, 401, 403))
        if status == 302:
            self.assertEqual(loc, "/login")
        self.assertNotIn(b"APP-BODY", body)

    def test_github_session_outside_allowlist_gets_no_api(self):
        status, _, _ = self.get("/api/state", self.github_headers("retired-user"))
        self.assertNotEqual(status, 200)

    def test_github_session_with_missing_allowlist_gets_no_ticket(self):
        root = self.httpd.RequestHandlerClass.root
        allowed = root / server.GITHUB_ALLOW_FILE
        allowed.rename(allowed.with_name(allowed.name + ".bak"))
        status, loc, body = self.get(f"/app/{Q}/", self.github_headers())
        self.assertNotIn("/app/~", loc)
        self.assertIn(status, (302, 401, 403))
        if status == 302:
            self.assertEqual(loc, "/login")
        self.assertNotIn(b"APP-BODY", body)

    def test_github_allowlist_match_is_case_insensitive(self):
        root = self.httpd.RequestHandlerClass.root
        allowed = root / server.GITHUB_ALLOW_FILE
        allowed.write_text("TaeSeok\n", encoding="utf-8")
        status, loc, body = self.get(f"/app/{Q}/", self.github_headers("taeseok"))
        self.assertEqual(status, 302)
        self.assertRegex(loc, r"\A/app/~\d+\.[0-9a-f]{32}/" + Q + r"/\Z")
        self.assertNotIn(b"APP-BODY", body)
        status, _, body = self.get(loc, self.github_headers("taeseok"))
        self.assertEqual(status, 200)
        self.assertIn(b"APP-BODY", body)

    def test_github_session_mixed_case_login_still_works(self):
        root = self.httpd.RequestHandlerClass.root
        allowed = root / server.GITHUB_ALLOW_FILE
        allowed.write_text("taeseok\n", encoding="utf-8")
        headers = self.github_headers("TaeSeok")
        status, loc, _ = self.get(f"/app/{Q}/", headers)
        self.assertEqual(status, 302)
        self.assertIn("/app/~", loc)
        status, _, body = self.get(loc, headers)
        self.assertEqual(status, 200)
        self.assertIn(b"APP-BODY", body)

    def test_github_session_mixed_case_outside_allowlist_is_refused(self):
        root = self.httpd.RequestHandlerClass.root
        allowed = root / server.GITHUB_ALLOW_FILE
        allowed.write_text("someoneelse\n", encoding="utf-8")
        status, loc, body = self.get(f"/app/{Q}/", self.github_headers("TaeSeok"))
        self.assertNotIn("/app/~", loc)
        self.assertIn(status, (302, 401, 403))
        if status == 302:
            self.assertEqual(loc, "/login")
        self.assertNotIn(b"APP-BODY", body)


if __name__ == "__main__":
    unittest.main()
