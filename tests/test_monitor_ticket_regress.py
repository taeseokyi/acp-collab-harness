"""T-210 회귀 시험 - `/app/` 실행 티켓의 주체 결속·꼴 검사·회수 감사.

R15 재검수 N1·N2·N6·D6 의 다섯 변이(M5/M8/M9/M10/M11)를 빨갛게 만든다.
절반은 함수를 바로 부르고, 나머지는 진짜 소켓으로 본다.
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
KEY = TOKEN.encode("ascii")
NAME = "알파"
Q = urllib.parse.quote(NAME)
LOGIN = "kim"
OTHER = "lee"


class MonitorTicketRegression(unittest.TestCase):
    def setUp(self):
        with server._revoked_lock:
            server._revoked_last.clear()

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = pathlib.Path(tmp.name)
        self.root = root
        web = root / "projects" / NAME / "web"
        web.mkdir(parents=True)
        (web / "index.html").write_text("<!doctype html><p id=secret>APP-BODY</p>", encoding="utf-8")
        (root / "projects" / NAME / "app.json").write_text(
            json.dumps({"root": "web", "entry": "index.html"}), encoding="utf-8")
        (root / "AIMEM.md").write_text("# AIMEM\n\n- **REV: 1**\n", encoding="utf-8")
        allowed = root / server.GITHUB_ALLOW_FILE
        allowed.parent.mkdir(parents=True)
        allowed.write_text(LOGIN + "\n" + OTHER + "\n", encoding="utf-8")

        handler = type("H", (server.Handler,), {
            "root": root, "require_auth": True, "tls": False, "access_token": TOKEN,
            "guard": server.LoginGuard(), "log_message": lambda *a, **k: None,
        })
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

    def github_headers(self, login=LOGIN, exp=None, token=TOKEN):
        if exp is None:
            exp = int(time.time()) + server.SESSION_TTL_SEC
        return {"Cookie": f"{server.SESSION_COOKIE}={server.sign_session(token, f'gh:{login}', exp)}"}

    def mint_ticket(self, login=LOGIN):
        status, loc, _ = self.get(f"/app/{Q}/", self.github_headers(login))
        self.assertEqual(status, 302)
        self.assertRegex(loc, r"\A/app/~\d+\.[0-9a-f]{12}\.[0-9a-f]{32}/" + Q + r"/\Z")
        return loc

    def revoke_all(self):
        (pathlib.Path(self.root) / server.GITHUB_ALLOW_FILE).write_text("", encoding="utf-8")

    def audit_line_count(self):
        p = pathlib.Path(self.root) / server.AUDIT_LOG
        if not p.exists():
            return 0
        return len(p.read_text(encoding="utf-8").splitlines())

    def test_tag_swap_with_same_mac_is_refused(self):
        exp = int(time.time()) + 600
        ticket = server.app_ticket(NAME, exp, KEY, "gh:kim")
        exp_s, _, mac = ticket.split(".", 2)
        swapped = f"{exp_s}.{server.app_ticket_tag('gh:lee', KEY)}.{mac}"
        self.assertFalse(server.app_ticket_ok(swapped, NAME, KEY, "gh:lee"))

    def test_tag_swap_over_http_is_403(self):
        exp = int(time.time()) + 600
        ticket = server.app_ticket(NAME, exp, KEY, "gh:kim")
        exp_s, _, mac = ticket.split(".", 2)
        swapped = f"{exp_s}.{server.app_ticket_tag('gh:lee', KEY)}.{mac}"
        status, _, body = self.get(f"/app/~{swapped}/{Q}/")
        self.assertEqual(status, 403)
        self.assertNotIn(b"APP-BODY", body)

    def test_tag_is_not_the_login(self):
        ticket = server.app_ticket(NAME, int(time.time()) + 600, KEY, "gh:kim")
        self.assertNotIn("kim", ticket)
        self.assertNotIn("gh:", ticket)

    def test_ticket_longer_than_160_is_not_routed(self):
        long_path = "/app/~" + "a" * 161 + f"/{Q}/"
        self.assertIsNone(server._APP_RE.match(long_path))

    def test_long_ticket_over_http_is_not_served(self):
        long_path = "/app/~" + "a" * 161 + f"/{Q}/"
        status, _, body = self.get(long_path)
        self.assertNotEqual(status, 200)
        self.assertNotIn(b"APP-BODY", body)

    def test_revoked_ticket_path_is_audited(self):
        ticket_loc = self.mint_ticket("kim")
        status, _, body = self.get(ticket_loc)
        self.assertEqual(status, 200)
        self.assertIn(b"APP-BODY", body)

        before = self.audit_line_count()
        self.revoke_all()
        status, _, body = self.get(ticket_loc)
        self.assertEqual(status, 403)
        self.assertNotIn(b"APP-BODY", body)
        self.assertGreater(self.audit_line_count(), before)

    def test_audit_line_hides_the_ticket(self):
        ticket_loc = self.mint_ticket("kim")
        self.revoke_all()
        status, _, _ = self.get(ticket_loc)
        self.assertEqual(status, 403)

        p = pathlib.Path(self.root) / server.AUDIT_LOG
        lines = p.read_text(encoding="utf-8").splitlines()
        self.assertTrue(lines)
        last = lines[-1]
        ticket = ticket_loc.split("/")[2][1:]
        self.assertNotIn(ticket, last)
        self.assertIn("/app/~***", last)

    def test_bad_tag_shapes_are_refused(self):
        exp = str(int(time.time()) + 600)
        mac = "a" * 32
        for tag in ("AAAA", "gh:kim", "", "0" * 13):
            ticket = f"{exp}.{tag}.{mac}"
            with self.subTest(tag=tag):
                self.assertIsNone(server._app_ticket_parts(ticket))

    def test_bad_project_name_fails_ticket_ok(self):
        exp = int(time.time()) + 600
        subject = "gh:kim"
        for name in ("../etc", "알파/베타", ""):
            ticket = server.app_ticket(name, exp, KEY, subject)
            with self.subTest(name=name):
                self.assertFalse(server.app_ticket_ok(ticket, name, KEY, subject))

    def test_resolve_returns_none_for_unknown_tag(self):
        ticket = server.app_ticket(NAME, int(time.time()) + 600, KEY, "gh:zzz")
        self.assertIsNone(server.app_ticket_resolve(ticket, KEY, ["gh:kim", "gh:lee"]))

    def test_mixed_case_login_resolves_to_the_canonical_subject(self):
        self.assertEqual(server.app_ticket_tag("gh:KiM", KEY),
                         server.app_ticket_tag("gh:kim", KEY))
        ticket = server.app_ticket(NAME, int(time.time()) + 600, KEY, "gh:KiM")
        self.assertEqual(server.app_ticket_resolve(ticket, KEY, ["gh:kim"]), "gh:kim")


if __name__ == "__main__":
    unittest.main()
