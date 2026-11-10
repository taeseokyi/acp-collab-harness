"""GitHub 기기 흐름 로그인 (2026-11-10, 태석님 지시 - reefwiz-esp32 의 OAuth App 재사용).

GitHub 은 부르지 않는다 - `server.github_post_form` / `server.github_user_login` 을 갈아 끼운다.
"""
import json
import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from aimem_monitor import (GITHUB_ALLOW_FILE, GITHUB_CLIENT_ID_ENV, GITHUB_CLIENT_SECRET_ENV,  # noqa: E402
                           GITHUB_DEVICE_COOKIE, SESSION_COOKIE, server)
from test_aimem_monitor_auth import TOKEN, _Srv, _h, _write  # noqa: E402

JSON = {"Content-Type": "application/json"}
START, POLL = "/api/github/device/start", "/api/github/device/poll"


class EnabledTests(unittest.TestCase):
    def test_device_only_when_id_without_secret(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(GITHUB_CLIENT_ID_ENV, None)
            os.environ.pop(GITHUB_CLIENT_SECRET_ENV, None)
            self.assertFalse(server.github_device_enabled())
            os.environ[GITHUB_CLIENT_ID_ENV] = "id"
            self.assertTrue(server.github_device_enabled())
            self.assertFalse(server.github_enabled())
            os.environ[GITHUB_CLIENT_SECRET_ENV] = "secret"
            self.assertFalse(server.github_device_enabled())   # 둘 다 있으면 웹 흐름
            self.assertTrue(server.github_enabled())


class PendingTests(unittest.TestCase):
    def test_one_per_ip_cap_and_expiry(self):
        p = server.DevicePending(limit=2)
        a1 = p.add("1.1.1.1", "d1", 5, 900, now=0)
        a2 = p.add("1.1.1.1", "d2", 5, 900, now=1)          # 같은 IP - 앞의 것은 버린다
        self.assertEqual(p.due(a1, now=100), (None, False))
        self.assertIsNotNone(p.add("2.2.2.2", "d3", 5, 900, now=1))
        self.assertIsNone(p.add("3.3.3.3", "d4", 5, 900, now=2))       # 전체 상한
        self.assertIsNotNone(p.add("3.3.3.3", "d4", 5, 900, now=2000))  # 만료된 것이 자리를 비운다
        self.assertEqual(p.due(a2, now=2000), (None, False))

    def test_interval_is_respected_and_slow_down_widens_it(self):
        p = server.DevicePending()
        a = p.add("1.1.1.1", "d", 5, 900, now=0)
        self.assertFalse(p.due(a, now=4)[1])
        self.assertTrue(p.due(a, now=5)[1])
        self.assertFalse(p.due(a, now=9)[1])
        p.slow_down(a, now=10)
        self.assertFalse(p.due(a, now=19)[1])
        self.assertTrue(p.due(a, now=20)[1])
        self.assertEqual(p.due("없는것", now=0), (None, False))


class FlowTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = tmp.name
        _write(self.root, GITHUB_ALLOW_FILE, "octocat\n")
        env = mock.patch.dict(os.environ, {GITHUB_CLIENT_ID_ENV: "Iv1.testid"})
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop(GITHUB_CLIENT_SECRET_ENV, None)
        self.srv = _Srv(self.root)
        self.addCleanup(self.srv.close)
        self.pending = server.DevicePending()
        self.srv.httpd.RequestHandlerClass.device = self.pending
        self.forms = []
        self.token_reply = {"error": "authorization_pending"}
        self.login = "OctoCat"

        def post_form(url, fields):
            self.forms.append((url, dict(fields)))
            if url.endswith("/login/device/code"):
                return {"device_code": "DEVCODE-SECRET", "user_code": "ABCD-1234", "interval": 5, "expires_in": 900,
                        "verification_uri": "https://evil.example/phish"}
            return self.token_reply
        for name, fn in (("github_post_form", post_form), ("github_user_login", lambda tok: self.login)):
            p = mock.patch.object(server, name, fn)
            p.start()
            self.addCleanup(p.stop)

    def start(self):
        s, h, b = self.srv.req("POST", START, JSON, b"{}")
        ck = (_h(h, "Set-Cookie") or [""])[0].split(";")[0]
        return s, json.loads(b), ck

    def poll(self, ck, due=True):
        if due:
            for it in self.pending._items.values():
                it["next"] = 0
        s, h, b = self.srv.req("POST", POLL, dict(JSON, Cookie=ck), b"{}")
        return s, json.loads(b), _h(h, "Set-Cookie")

    def test_start_shows_code_but_never_device_code(self):
        s, d, ck = self.start()
        self.assertEqual(s, 200)
        self.assertEqual(d["user_code"], "ABCD-1234")
        self.assertEqual(d["verification_uri"], "https://github.com/login/device")   # 응답의 주소를 믿지 않는다
        self.assertNotIn("DEVCODE-SECRET", json.dumps(d))
        self.assertTrue(ck.startswith(GITHUB_DEVICE_COOKIE + "="))
        self.assertNotIn("DEVCODE-SECRET", ck)
        self.assertEqual(self.forms[0][1], {"client_id": "Iv1.testid", "scope": ""})

    def test_pending_then_approved_allowed_account_gets_session(self):
        _, _, ck = self.start()
        s, d, cookies = self.poll(ck)
        self.assertEqual((s, d["state"]), (200, "pending"))
        self.assertFalse(any(c.startswith(SESSION_COOKIE + "=") for c in cookies))
        self.token_reply = {"access_token": "gho_x"}
        s, d, cookies = self.poll(ck)
        self.assertEqual((s, d["state"], d["redirect"]), (200, "ok", "/"))
        sess = [c for c in cookies if c.startswith(SESSION_COOKIE + "=")][0].split(";")[0]
        s, _, b = self.srv.req("GET", "/api/authinfo", {"Cookie": sess})
        self.assertEqual(json.loads(b)["who"], "GitHub OctoCat")
        self.assertEqual(self.forms[-1][1]["device_code"], "DEVCODE-SECRET")
        s, d, _ = self.poll(ck)                     # 한 번 승인은 한 번의 로그인에만
        self.assertEqual((s, d["state"]), (410, "expired"))

    def test_account_not_on_allow_list_is_denied_without_session(self):
        _, _, ck = self.start()
        self.token_reply, self.login = {"access_token": "gho_x"}, "mallory"
        s, d, cookies = self.poll(ck)
        self.assertEqual((s, d["state"]), (403, "denied"))
        self.assertFalse(any(c.startswith(SESSION_COOKIE + "=") and "Max-Age=0" not in c for c in cookies))
        self.assertEqual(self.poll(ck)[0], 410)

    def test_poll_before_interval_does_not_ask_github(self):
        _, _, ck = self.start()
        n = len(self.forms)
        s, d, _ = self.poll(ck, due=False)
        self.assertEqual((s, d["state"]), (200, "pending"))
        self.assertEqual(len(self.forms), n)

    def test_denied_and_expired_and_unknown_cookie(self):
        _, _, ck = self.start()
        self.token_reply = {"error": "access_denied"}
        self.assertEqual(self.poll(ck)[1]["state"], "denied")
        _, _, ck = self.start()
        self.token_reply = {"error": "expired_token"}
        self.assertEqual(self.poll(ck)[0], 410)
        self.assertEqual(self.poll(GITHUB_DEVICE_COOKIE + "=nope")[0], 410)
        self.assertEqual(self.srv.req("POST", POLL, JSON, b"{}")[0], 410)

    def test_form_post_and_cross_origin_are_refused(self):
        s, _, _ = self.srv.req("POST", START, {"Content-Type": "text/plain"}, b"{}")
        self.assertEqual(s, 415)
        s, _, _ = self.srv.req("POST", START, dict(JSON, Origin="https://evil.example"), b"{}")
        self.assertEqual(s, 403)
        self.assertEqual(self.forms, [])

    def test_off_without_client_id_or_with_secret(self):
        with mock.patch.dict(os.environ, {GITHUB_CLIENT_SECRET_ENV: "s"}):
            self.assertEqual(self.start()[0], 404)
            s, _, b = self.srv.req("GET", "/api/authinfo")
            self.assertFalse(json.loads(b)["github_device"])
        s, _, b = self.srv.req("GET", "/api/authinfo")
        self.assertTrue(json.loads(b)["github_device"])
        os.environ.pop(GITHUB_CLIENT_ID_ENV)
        self.assertEqual(self.start()[0], 404)
        self.assertEqual(self.forms, [])


if __name__ == "__main__":
    unittest.main()
