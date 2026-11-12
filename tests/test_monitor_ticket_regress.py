"""T-210 회귀 시험 - `/app/` 실행 티켓의 주체 결속·꼴 검사·회수 감사.

R15 재검수 N1·N2·N6·D6 의 다섯 변이(M5/M8/M9/M10/M11)를 빨갛게 만든다.
절반은 함수를 바로 부르고, 나머지는 진짜 소켓으로 본다.
"""
import http.client
import http.server
import json
import pathlib
import re
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock
import urllib.parse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools"))

from aimem_monitor import server  # noqa: E402

TOKEN = "t" * 40
KEY = TOKEN.encode("ascii")
NAME = "알파"
Q = urllib.parse.quote(NAME)
Q_BETA = urllib.parse.quote("베타")
LOGIN = "kim"
OTHER = "lee"


class MonitorTicketRegression(unittest.TestCase):
    def setUp(self):
        with server._revoked_lock:
            server._revoked_last.clear()
        server._denied_window_start = 0.0
        server._denied_window_written = 0
        server._denied_cap_skipped = 0
        server._denied_evicted_skipped = 0
        server._denied_window_seen = set()

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

    def audit_event_lines(self, event):
        p = pathlib.Path(self.root) / server.AUDIT_LOG
        if not p.exists():
            return []
        return [line for line in p.read_text(encoding="utf-8").splitlines()
                if line.split("\t")[1] == event]

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

    def test_denied_audit_key_ignores_the_client_ip(self):
        before = self.audit_line_count()
        server._audit_denied(self.root, "github-revoked", "10.0.0.1", "gh:kim",
                             "/app/~***/알파/", "GET", "허용 목록 밖")
        server._audit_denied(self.root, "github-revoked", "10.0.0.2", "gh:kim",
                             "/app/~***/알파/", "GET", "허용 목록 밖")
        self.assertEqual(self.audit_line_count(), before + 1)
        server._audit_denied(self.root, "github-revoked", "10.0.0.1", "gh:kim",
                             "/app/~***/베타/", "GET", "허용 목록 밖")
        self.assertEqual(self.audit_line_count(), before + 2)

    def test_bad_bearer_is_audited(self):
        wrong = "x" * 40
        before = len(self.audit_event_lines("token-bad"))
        status, _, _ = self.get("/api/state", {"Authorization": f"Bearer {wrong}"})
        self.assertEqual(status, 401)
        lines = self.audit_event_lines("token-bad")
        self.assertEqual(len(lines), before + 1)
        self.assertNotIn(wrong, "\n".join(lines))

    def test_bad_session_cookie_is_audited(self):
        wrong = "COOKIEWRONGVALUE"
        before = len(self.audit_event_lines("session-bad"))
        status, _, _ = self.get("/api/state",
                                {"Cookie": f"{server.SESSION_COOKIE}={wrong}"})
        self.assertEqual(status, 401)
        lines = self.audit_event_lines("session-bad")
        self.assertEqual(len(lines), before + 1)
        self.assertNotIn(wrong, "\n".join(lines))

    def test_session_bad_needs_the_session_cookie(self):
        before = len(self.audit_event_lines("session-bad"))
        status, _, _ = self.get("/api/state", {"Cookie": "theme=dark"})
        self.assertEqual(status, 401)
        self.assertEqual(len(self.audit_event_lines("session-bad")), before)

    def test_suppression_table_stays_under_the_cap(self):
        for i in range(server._REVOKED_AUDIT_MAX + 10):
            server._audit_denied(self.root, "github-revoked", "127.0.0.1",
                                 f"gh:user{i}", f"/app/~***/p{i}/", "GET", "허용 목록 밖")
        self.assertLessEqual(len(server._revoked_last), server._REVOKED_AUDIT_MAX)

    def test_suppressed_count_is_reported(self):
        args = (self.root, "github-revoked", "127.0.0.1", "gh:kim",
                "/app/~***/알파/", "GET", "허용 목록 밖")
        with mock.patch.object(server, "_REVOKED_AUDIT_MIN_SEC", 0.1):
            server._audit_denied(*args)
            for _ in range(4):
                server._audit_denied(*args)
            time.sleep(0.12)
            server._audit_denied(*args)
        p = pathlib.Path(self.root) / server.AUDIT_LOG
        last = p.read_text(encoding="utf-8").splitlines()[-1]
        self.assertIn("생략 4건", last)

    def test_unauthenticated_flood_is_bounded(self):
        before = self.audit_line_count()
        for i in range(200):
            status, _, _ = self.get(f"/app/~bad{i}/{Q}/")
            self.assertNotEqual(status, 200)
        after = self.audit_line_count()
        self.assertGreaterEqual(after - before, 1)
        self.assertLessEqual(after - before, 10)

    def test_ticket_subject_cannot_grow_the_audit_keys(self):
        before = self.audit_line_count()
        exp = int(time.time()) + 600
        fake = f"{exp}.{'a' * 12}.{'b' * 32}"
        for i in range(120):
            status, _, _ = self.get(f"/app/~{fake}/{Q}/x{i}")
            self.assertEqual(status, 403)
        self.assertLessEqual(self.audit_line_count() - before, 5)

    def test_bad_bearer_flood_with_changing_paths_is_one_line(self):
        before = len(self.audit_event_lines("token-bad"))
        for i in range(120):
            status, _, _ = self.get(f"/api/x{i}", {"Authorization": "Bearer nope"})
            self.assertEqual(status, 401)
        self.assertLessEqual(len(self.audit_event_lines("token-bad")) - before, 2)

    def test_global_cap_limits_lines_per_minute(self):
        before = self.audit_line_count()
        cap = server._DENIED_AUDIT_MAX_PER_MIN
        for i in range(cap + 40):
            server._audit_denied(self.root, "app-ticket-bad", "127.0.0.1",
                                 "gh:user", f"/app/~***/p{i}/", "GET", "허용 목록 밖",
                                 authenticated=True)
        self.assertEqual(self.audit_line_count() - before, cap)

    def test_window_reopens_after_a_minute(self):
        before = self.audit_line_count()
        cap = server._DENIED_AUDIT_MAX_PER_MIN
        for i in range(cap + 40):
            server._audit_denied(self.root, "app-ticket-bad", "127.0.0.1",
                                 "gh:user", f"/app/~***/p{i}/", "GET", "허용 목록 밖",
                                 authenticated=True)
        server._denied_window_start = time.time() - 61
        server._audit_denied(self.root, "app-ticket-bad", "127.0.0.1",
                             "gh:fresh", "/app/~***/알파/", "GET", "허용 목록 밖",
                             authenticated=True)
        self.assertEqual(self.audit_line_count(), before + cap + 2)
        dropped = self.audit_event_lines("audit-dropped")
        self.assertTrue(dropped)
        self.assertIn("상한 생략", dropped[-1])
        self.assertRegex(dropped[-1], r"상한 생략 40건")

    def test_capped_denial_is_not_marked_as_written(self):
        cap = server._DENIED_AUDIT_MAX_PER_MIN
        for i in range(cap):
            server._audit_denied(self.root, "app-ticket-bad", "127.0.0.1",
                                 "gh:user", f"/app/~***/p{i}/", "GET", "허용 목록 밖",
                                 authenticated=True)
        before = self.audit_line_count()
        server._denied_window_seen.add(("app-ticket-bad", "gh:over"))
        args = (self.root, "app-ticket-bad", "127.0.0.1", "gh:over",
                "/app/~***/알파/", "GET", "허용 목록 밖")
        key = ("app-ticket-bad", "gh:over", "/app/~***/알파/", "GET", "허용 목록 밖")
        server._audit_denied(*args, authenticated=True)
        server._audit_denied(*args, authenticated=True)
        self.assertNotIn(key, server._revoked_last)
        self.assertEqual(self.audit_line_count(), before)
        server._denied_window_start = time.time() - 61
        server._audit_denied(*args, authenticated=True)
        self.assertGreater(self.audit_line_count(), before)
        self.assertIn(key, server._revoked_last)

    def test_suppressed_count_belongs_to_its_own_key(self):
        args = (self.root, "app-ticket-bad", "127.0.0.1", "gh:kim",
                "/app/~***/알파/", "GET", "허용 목록 밖")
        with mock.patch.object(server, "_REVOKED_AUDIT_MIN_SEC", 0.1):
            server._audit_denied(*args, authenticated=True)
            for _ in range(4):
                server._audit_denied(*args, authenticated=True)
            server._audit_denied(self.root, "token-bad", "127.0.0.1", None,
                                 "/api/x", "GET", "토큰 불일치")
            token_lines = self.audit_event_lines("token-bad")
            self.assertNotIn("생략", token_lines[-1])
            time.sleep(0.12)
            server._audit_denied(*args, authenticated=True)
        denied = self.audit_event_lines("app-ticket-bad")
        self.assertIn("생략 4건", denied[-1])

    def test_denied_line_uses_the_current_path(self):
        with mock.patch.object(server, "_REVOKED_AUDIT_MIN_SEC", 0.1):
            server._audit_denied(self.root, "app-ticket-bad", "127.0.0.1", "gh:kim",
                                 "/api/harmless", "GET", "허용 목록 밖")
            time.sleep(0.12)
            server._audit_denied(self.root, "app-ticket-bad", "127.0.0.1", "gh:kim",
                                 "/api/REAL-TARGET", "GET", "허용 목록 밖")
        p = pathlib.Path(self.root) / server.AUDIT_LOG
        last = p.read_text(encoding="utf-8").splitlines()[-1]
        self.assertIn("/api/REAL-TARGET", last)


    def test_real_ticket_subject_cannot_grow_the_audit_keys(self):
        ticket_loc = self.mint_ticket("kim")
        ticket = ticket_loc.split("/")[2][1:]
        before = self.audit_line_count()
        for i in range(200):
            status, _, _ = self.get(f"/app/~{ticket}/{Q_BETA}/z{i}")
            self.assertEqual(status, 403)
        after = self.audit_line_count()
        self.assertLessEqual(after - before, 5)
        new_lines = (pathlib.Path(self.root) / server.AUDIT_LOG).read_text(
            encoding="utf-8").splitlines()[before:after]
        self.assertTrue(any(line.split("\t")[3] == "gh:kim" for line in new_lines))

    def test_a_revoked_account_is_still_audited_during_a_ticket_flood(self):
        ticket_loc = self.mint_ticket("kim")
        ticket = ticket_loc.split("/")[2][1:]
        for i in range(200):
            status, _, _ = self.get(f"/app/~{ticket}/{Q_BETA}/z{i}")
            self.assertEqual(status, 403)
        self.revoke_all()
        before = len(self.audit_event_lines("github-revoked"))
        self.get("/api/state", self.github_headers("lee"))
        after = len(self.audit_event_lines("github-revoked"))
        self.assertGreaterEqual(after - before, 1)

    def test_credential_subject_mismatch_keeps_the_path_in_the_key(self):
        ticket_loc = self.mint_ticket("kim")
        ticket = ticket_loc.split("/")[2][1:]
        before = len(self.audit_event_lines("app-ticket-bad"))
        for suffix in ("a", "b", "c", "d", "e"):
            status, _, _ = self.get(f"/app/~{ticket}/{Q}/{suffix}",
                                    self.github_headers("lee"))
            self.assertEqual(status, 403)
        after = len(self.audit_event_lines("app-ticket-bad"))
        self.assertGreaterEqual(after - before, 3)

    def test_cap_skipped_count_is_reported_only_once(self):
        cap = server._DENIED_AUDIT_MAX_PER_MIN
        before = self.audit_line_count()
        for i in range(cap + 20):
            server._audit_denied(self.root, "app-ticket-bad", "127.0.0.1",
                                 "gh:user", f"/app/~***/p{i}/", "GET",
                                 "허용 목록 밖", authenticated=True)
        self.assertEqual(self.audit_line_count() - before, cap)

        server._denied_window_start = time.time() - 61
        server._audit_denied(self.root, "app-ticket-bad", "127.0.0.1",
                             "gh:fresh", "/app/~***/알파/", "GET",
                             "허용 목록 밖", authenticated=True)
        dropped = self.audit_event_lines("audit-dropped")
        self.assertEqual(len(dropped), 1)
        self.assertRegex(dropped[0], r"상한 생략 20건")

        server._denied_window_start = time.time() - 61
        server._audit_denied(self.root, "app-ticket-bad", "127.0.0.1",
                             "gh:fresh2", "/app/~***/베타/", "GET",
                             "허용 목록 밖", authenticated=True)
        dropped = self.audit_event_lines("audit-dropped")
        self.assertEqual(len(dropped), 1)

        skipped = sum(int(m.group(1)) for m in
                      (re.search(r"상한 생략 (\d+)건", line) for line in dropped) if m)
        self.assertEqual(skipped, 20)


    def test_first_seen_subject_is_written_after_the_cap(self):
        cap = server._DENIED_AUDIT_MAX_PER_MIN
        before = self.audit_line_count()
        for i in range(cap):
            server._audit_denied(self.root, "app-ticket-bad", "127.0.0.1",
                                 f"gh:user{i}", f"/app/~***/p{i}/", "GET",
                                 "허용 목록 밖", authenticated=True)
        self.assertEqual(self.audit_line_count() - before, cap)
        server._audit_denied(self.root, "app-ticket-bad", "127.0.0.1",
                             "gh:newcomer", "/app/~***/알파/", "GET",
                             "허용 목록 밖", authenticated=True)
        self.assertEqual(self.audit_line_count() - before, cap + 1)

    def test_a_hogging_subject_does_not_starve_another_subject(self):
        cap = server._DENIED_AUDIT_MAX_PER_MIN
        for i in range(cap + 40):
            server._audit_denied(self.root, "github-revoked", "6.6.6.6", "gh:evil",
                                 f"/api/x{i}", "GET", "허용 목록 밖", authenticated=True)
        server._audit_denied(self.root, "github-revoked", "9.9.9.9", "gh:park",
                             "/api/state", "GET", "허용 목록 밖", authenticated=True)
        p = pathlib.Path(self.root) / server.AUDIT_LOG
        lines = p.read_text(encoding="utf-8").splitlines()
        self.assertTrue(any(line.split("\t")[3] == "gh:park" for line in lines))

    def test_first_seen_guarantee_stops_at_the_first_max(self):
        cap = server._DENIED_AUDIT_MAX_PER_MIN
        first_max = server._DENIED_AUDIT_FIRST_MAX
        for i in range(cap + 10):
            server._audit_denied(self.root, "github-revoked", "6.6.6.6", "gh:evil",
                                 f"/api/x{i}", "GET", "허용 목록 밖", authenticated=True)
        server._denied_window_seen = {
            ("github-revoked", f"gh:u{i}") for i in range(first_max - 1)
        }
        before = self.audit_line_count()
        server._audit_denied(self.root, "github-revoked", "1.1.1.1", "gh:edge",
                             "/api/edge", "GET", "허용 목록 밖", authenticated=True)
        self.assertEqual(self.audit_line_count(), before + 1)
        server._denied_window_seen = {
            ("github-revoked", f"gh:u{i}") for i in range(first_max)
        }
        before = self.audit_line_count()
        server._audit_denied(self.root, "github-revoked", "1.1.1.1", "gh:extra",
                             "/api/extra", "GET", "허용 목록 밖", authenticated=True)
        self.assertEqual(self.audit_line_count(), before)

    def test_first_seen_guarantee_returns_in_a_new_window(self):
        cap = server._DENIED_AUDIT_MAX_PER_MIN
        for i in range(cap + 10):
            server._audit_denied(self.root, "github-revoked", "6.6.6.6", "gh:evil",
                                 f"/api/w1-{i}", "GET", "허용 목록 밖", authenticated=True)
        server._denied_window_start = time.time() - 61
        for i in range(cap + 10):
            server._audit_denied(self.root, "github-revoked", "6.6.6.6", "gh:evil",
                                 f"/api/w2-{i}", "GET", "허용 목록 밖", authenticated=True)
        server._audit_denied(self.root, "github-revoked", "9.9.9.9", "gh:park",
                             "/api/state", "GET", "허용 목록 밖", authenticated=True)
        p = pathlib.Path(self.root) / server.AUDIT_LOG
        lines = p.read_text(encoding="utf-8").splitlines()
        self.assertTrue(any(line.split("\t")[3] == "gh:park" for line in lines))

    def test_evicted_suppression_count_is_reported_next_window(self):
        with server._revoked_lock:
            server._revoked_last.clear()
            for i in range(server._REVOKED_AUDIT_MAX - 1):
                server._revoked_last[("app-ticket-bad", f"gh:old{i}", "GET")] = (
                    time.time(), 0)
            server._revoked_last[("app-ticket-bad", "gh:evict", "GET")] = (
                time.time(), 7)
            server._revoked_last.move_to_end(
                ("app-ticket-bad", "gh:evict", "GET"), last=False)
        server._audit_denied(self.root, "app-ticket-bad", "127.0.0.1", "gh:fresh",
                             "/app/~***/알파/", "GET", "허용 목록 밖", authenticated=True)
        server._denied_window_start = time.time() - 61
        server._audit_denied(self.root, "app-ticket-bad", "127.0.0.1", "gh:fresh2",
                             "/app/~***/베타/", "GET", "허용 목록 밖", authenticated=True)
        dropped = self.audit_event_lines("audit-dropped")
        self.assertTrue(any("상한 생략 7건" in line for line in dropped))

    def test_flush_denied_audit_writes_once(self):
        server._denied_cap_skipped = 5
        server._denied_evicted_skipped = 3
        before = self.audit_line_count()
        server.flush_denied_audit(self.root)
        self.assertEqual(self.audit_line_count(), before + 1)
        dropped = self.audit_event_lines("audit-dropped")
        self.assertEqual(len(dropped), 1)
        self.assertRegex(dropped[0], r"상한 생략 8건")
        self.assertEqual(server._denied_cap_skipped, 0)
        self.assertEqual(server._denied_evicted_skipped, 0)
        server.flush_denied_audit(self.root)
        self.assertEqual(self.audit_line_count(), before + 1)

    def test_app_ticket_bad_reasons_have_separate_keys(self):
        before = self.audit_line_count()
        server._audit_denied(self.root, "app-ticket-bad", "127.0.0.1", None,
                             "/app/~***/알파/", "GET", "형식")
        server._audit_denied(self.root, "app-ticket-bad", "127.0.0.1", None,
                             "/app/~***/알파/", "GET", "주체 못 찾음(회수 또는 위조)")
        self.assertEqual(self.audit_line_count() - before, 2)

    def test_app_ticket_bad_same_reason_is_still_suppressed(self):
        before = self.audit_line_count()
        args = (self.root, "app-ticket-bad", "127.0.0.1", None,
                "/app/~***/알파/", "GET", "형식")
        server._audit_denied(*args)
        server._audit_denied(*args)
        self.assertEqual(self.audit_line_count() - before, 1)

    def test_denied_audit_constants_are_pinned(self):
        self.assertEqual(server._DENIED_AUDIT_MAX_PER_MIN, 60)
        self.assertEqual(server._REVOKED_AUDIT_MIN_SEC, 60)
        self.assertEqual(server._REVOKED_AUDIT_MAX, 256)


if __name__ == "__main__":
    unittest.main()
