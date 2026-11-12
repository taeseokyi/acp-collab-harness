"""`/app/<프로젝트>/` 실행 경로의 뒷단 시험. 소켓은 열지 않고 함수를 직접 부릅니다."""
import contextlib
import email.message
import http.client
import http.server
import io
import json
import pathlib
import sys
import tempfile
import threading
import time
import unittest
import urllib.parse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools"))

from aimem_monitor import SERVER_KEYS, server  # noqa: E402


class ProjectAppTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = pathlib.Path(tmp.name)

    def project(self, name="알파"):
        d = self.root / "projects" / name
        d.mkdir(parents=True)
        return d

    def manifest(self, d, data):
        (d / "app.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def app(self):
        d = self.project()
        self.manifest(d, {"root": "web", "entry": "index.html"})
        (d / "web").mkdir()
        (d / "web" / "index.html").write_text("<!doctype html>", encoding="utf-8")
        return d

    def route(self, path, auth=False, host="localhost:18799", tls=False):
        h = server.Handler.__new__(server.Handler)
        h.path = path
        h.command = "GET"
        h.tls = tls
        h.require_auth = auth
        h.root = self.root
        h.access_token = None
        h.headers = email.message.Message()
        h.headers["Host"] = host
        h.client_address = ("127.0.0.1", 0)
        status, headers = [], []
        h.send_response = lambda code: status.append(code)
        h.send_header = lambda key, value: headers.append((key, value))
        h.end_headers = lambda: None
        h.wfile = io.BytesIO()
        h.do_GET()
        return status, headers, h.wfile.getvalue()

    def test_missing_manifest_is_not_runnable(self):
        self.project()
        self.assertIsNone(server.project_app("알파", self.root))

    def test_defaults(self):
        d = self.project()
        self.manifest(d, {})
        (d / "web").mkdir()
        (d / "web" / "index.html").write_text("기본", encoding="utf-8")
        app = server.project_app("알파", self.root)
        self.assertEqual(app["runnable"], True)
        self.assertEqual((app["root"], app["entry"], app["title"], app["url"]),
                         ("web", "index.html", "알파", "/app/알파/"))

    def test_explicit_values_are_returned(self):
        d = self.project("웹워들")
        self.manifest(d, {"root": "site", "entry": "main.html", "title": "웹워들 앱"})
        (d / "site").mkdir()
        (d / "site" / "main.html").write_text("ok", encoding="utf-8")
        app = server.project_app("웹워들", self.root)
        self.assertEqual((app["root"], app["entry"], app["title"], app["url"]),
                         ("site", "main.html", "웹워들 앱", "/app/웹워들/"))

    def test_broken_or_non_object_manifest_never_raises(self):
        d = self.project()
        for raw in ("{깨진", "[]", "null", '"문자열"', "123"):
            with self.subTest(raw=raw):
                (d / "app.json").write_text(raw, encoding="utf-8")
                app = server.project_app("알파", self.root)
                self.assertEqual(app["runnable"], False)
                self.assertIsInstance(app["reason"], str)

    def test_unsafe_root_is_rejected(self):
        d = self.project()
        for bad in ("../..", "/etc", ".hidden", "a\\b", "a/../../b"):
            with self.subTest(root=bad):
                self.manifest(d, {"root": bad})
                app = server.project_app("알파", self.root)
                self.assertEqual(app["runnable"], False)
                self.assertTrue(app["reason"])

    def test_symlinked_root_outside_project_is_rejected(self):
        d = self.project()
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "index.html").write_text("밖", encoding="utf-8")
        (d / "web").symlink_to(outside)
        self.manifest(d, {"root": "web", "entry": "index.html"})
        app = server.project_app("알파", self.root)
        self.assertEqual(app["runnable"], False)

    def test_missing_entry_is_rejected(self):
        d = self.project()
        (d / "web").mkdir()
        self.manifest(d, {"root": "web", "entry": "없는.html"})
        app = server.project_app("알파", self.root)
        self.assertEqual(app["runnable"], False)

    def test_empty_rel_serves_entry(self):
        d = self.app()
        raw = (d / "web" / "index.html").read_bytes()
        code, data, ctype = server.project_app_file("알파", "", self.root)
        self.assertEqual((code, data, ctype), (200, raw, "text/html; charset=utf-8"))

    def test_mjs_and_unknown_extension_content_types(self):
        d = self.app()
        (d / "web" / "js").mkdir()
        (d / "web" / "js" / "x.mjs").write_bytes(b"export default 1;")
        (d / "web" / "blob.bin").write_bytes(b"\x01\x02")
        code, data, ctype = server.project_app_file("알파", "js/x.mjs", self.root)
        self.assertEqual((code, data, ctype), (200, b"export default 1;",
                                              "text/javascript; charset=utf-8"))
        code, data, ctype = server.project_app_file("알파", "blob.bin", self.root)
        self.assertEqual((code, ctype), (200, "application/octet-stream"))

    def test_repository_files_do_not_leak(self):
        self.app()
        for rel in ("../../AIMEM.md", "../app.json"):
            with self.subTest(rel=rel):
                code, body, ctype = server.project_app_file("알파", rel, self.root)
                self.assertEqual((code, ctype), (404, None))

    def test_symlink_inside_app_folder_is_not_served(self):
        d = self.app()
        outside = self.root / "secret.txt"
        outside.write_text("밖", encoding="utf-8")
        (d / "web" / "escape.txt").symlink_to(outside)
        code, body, ctype = server.project_app_file("알파", "escape.txt", self.root)
        self.assertEqual((code, ctype), (404, None))

    def test_file_over_limit_is_413_without_truncated_body(self):
        d = self.app()
        big = d / "web" / "big.bin"
        big.write_bytes(b"\x00" * (server.PROJECT_APP_FILE_MAX_BYTES + 1))
        code, body, ctype = server.project_app_file("알파", "big.bin", self.root)
        self.assertEqual((code, ctype), (413, None))
        self.assertIsInstance(body, dict)

    def test_binary_is_served_byte_for_byte(self):
        d = self.app()
        raw = b"\x00\x89PNG\r\n\x1a\n\x00\x01"
        (d / "web" / "image.png").write_bytes(raw)
        self.assertEqual(server.project_app_file("알파", "image.png", self.root),
                         (200, raw, "image/png"))

    def test_csp_keeps_iframe_framing_and_stays_well_formed(self):
        origin = "https://h:1"
        csp = server.app_csp(origin)
        expected = ("sandbox allow-scripts allow-popups allow-modals; "
                    "default-src 'self' https://h:1; img-src 'self' https://h:1 data: blob:; "
                    "style-src 'self' https://h:1 'unsafe-inline'; script-src 'self' https://h:1; "
                    "connect-src 'self' https://h:1; font-src 'self' https://h:1 data:; "
                    "frame-ancestors 'self'; base-uri 'none'; form-action 'none'")
        self.assertEqual(csp, expected)
        self.assertTrue(csp.startswith("sandbox allow-scripts"))
        self.assertNotIn("allow-same-origin", csp)
        self.assertIn("frame-ancestors 'self'", csp)
        self.assertNotIn("'none'", csp.split("frame-ancestors 'self'")[0])
        self.assertEqual(csp.count(origin), 6)

        empty = server.app_csp("")
        self.assertEqual(empty.count("'none'"), 2)          # base-uri/form-action only
        self.assertNotIn("; ;", empty)
        self.assertNotIn("  ;", empty)
        self.assertNotIn(" ;", empty)

    def test_csp_sandbox_makes_origin_opaque(self):
        csp = server.app_csp("https://h:1")
        self.assertTrue(csp.startswith("sandbox allow-scripts allow-popups allow-modals; "))
        self.assertNotIn("allow-same-origin", csp)

    def test_list_projects_carries_app_and_none_for_missing_manifest(self):
        self.app()
        self.project("베타")
        got = {p["name"]: p for p in server.list_projects(self.root, [])}
        self.assertIn("app", got["알파"])
        self.assertEqual(got["알파"]["app"]["runnable"], True)
        self.assertIsNone(got["베타"]["app"])

    def test_contract_mentions_app(self):
        self.assertIn("app", SERVER_KEYS["projects"])

    def test_app_route_serves_and_uses_one_origin_aware_csp(self):
        self.app()
        status, headers, body = self.route("/app/알파/")
        self.assertEqual(status[-1], 302)
        location = dict(headers).get("Location")
        self.assertTrue(location.startswith("/app/~"))
        self.assertTrue(location.endswith("/%EC%95%8C%ED%8C%8C/"))

        status, headers, body = self.route(location)
        self.assertEqual((status[-1], body), (200, b"<!doctype html>"))
        self.assertEqual(dict(headers).get("Access-Control-Allow-Origin"), "null")
        self.assertEqual(dict(headers).get("Vary"), "Origin")
        self.assertIsNone(dict(headers).get("Access-Control-Allow-Credentials"))
        csp = [value for key, value in headers if key == "Content-Security-Policy"]
        self.assertEqual(len(csp), 1)
        self.assertTrue(csp[0].startswith("sandbox allow-scripts"))
        self.assertIn("frame-ancestors 'self'", csp[0])
        self.assertIn("http://localhost:18799", csp[0])

        status, headers, _ = self.route("/app/알파")
        self.assertEqual(status[-1], 302)
        location = dict(headers).get("Location")
        self.assertTrue(location.startswith("/app/~"))
        self.assertTrue(location.endswith("/%EC%95%8C%ED%8C%8C/"))

    def test_app_route_unauthenticated_redirects_to_login(self):
        self.app()
        status, headers, _ = self.route("/app/알파/", auth=True)
        self.assertEqual((status[-1], dict(headers).get("Location")), (302, "/login"))

    def test_placeholder_ticket_is_rejected_when_auth_is_on(self):
        self.app()
        ticket = server.app_ticket("알파", int(time.time()) + 60, server._APP_TICKET_FALLBACK_KEY, None)
        status, _, body = self.route(
            f"/app/~{ticket}/%EC%95%8C%ED%8C%8C/", auth=True)
        self.assertEqual(status[-1], 403)
        self.assertIn("실행 티켓이 만료됐습니다", json.loads(body)["error"])

        status, _, body = self.route(
            f"/app/~{ticket}/%EC%95%8C%ED%8C%8C/", auth=False)
        self.assertEqual((status[-1], body), (200, b"<!doctype html>"))

        expired = server.app_ticket("알파", int(time.time()) - 1, server._APP_TICKET_FALLBACK_KEY, None)
        status, _, body = self.route(
            f"/app/~{expired}/%EC%95%8C%ED%8C%8C/", auth=False)
        self.assertEqual(status[-1], 403)
        self.assertIn("실행 티켓이 만료됐습니다", json.loads(body)["error"])

    def test_app_ticket_roundtrip(self):
        key = b"0123456789abcdef0123456789abcdef"
        exp = int(time.time()) + 60
        ticket = server.app_ticket("알파", exp, key, "gh:kim")
        self.assertTrue(server.app_ticket_ok(ticket, "알파", key, "gh:kim"))
        self.assertEqual(server.app_ticket_resolve(ticket, key, ["gh:kim"]), "gh:kim")
        self.assertIsNone(server.app_ticket_resolve(ticket, key, ["gh:lee"]))

    def test_ticket_subject_is_bound_to_the_signer(self):
        key = b"0123456789abcdef0123456789abcdef"
        now = int(time.time())
        ticket = server.app_ticket("알파", now + 60, key, "gh:kim")
        self.assertRegex(ticket, r"\A\d{1,12}\.[0-9a-f]{12}\.[0-9a-f]{32}\Z")
        self.assertNotIn("gh:kim", ticket)
        self.assertIn(server.app_ticket_tag("gh:kim", key), ticket)
        self.assertTrue(server.app_ticket_ok(ticket, "알파", key, "gh:kim", now=now))
        self.assertTrue(server.app_ticket_ok(ticket, "알파", key, "gh:KiM", now=now))
        self.assertEqual(server.app_ticket_resolve(ticket, key, ["gh:KiM"]), "gh:KiM")
        self.assertFalse(server.app_ticket_ok(ticket, "알파", key, "gh:lee", now=now))

    def test_none_and_empty_subject_share_the_placeholder(self):
        key = b"0123456789abcdef0123456789abcdef"
        now = int(time.time())
        for subject in (None, ""):
            with self.subTest(subject=subject):
                ticket = server.app_ticket("알파", now + 60, key, subject)
                exp_s, tag, mac = ticket.split(".", 2)
                self.assertRegex(exp_s, r"\A\d{1,12}\Z")
                self.assertRegex(tag, r"\A[0-9a-f]{12}\Z")
                self.assertEqual(tag, server.app_ticket_tag(subject, key))
                self.assertRegex(mac, r"\A[0-9a-f]{32}\Z")
                self.assertNotIn("None", ticket)
                self.assertTrue(server.app_ticket_ok(ticket, "알파", key, "-", now=now))
                self.assertTrue(server.app_ticket_ok(ticket, "알파", key, None, now=now))
                self.assertTrue(server.app_ticket_ok(ticket, "알파", key, "", now=now))
                self.assertFalse(server.app_ticket_ok(ticket, "알파", key, "gh:kim", now=now))

    def test_expired_ticket_is_rejected(self):
        key = b"0123456789abcdef0123456789abcdef"
        ticket = server.app_ticket("알파", int(time.time()) - 1, key, "gh:kim")
        self.assertFalse(server.app_ticket_ok(ticket, "알파", key, "gh:kim"))

    def test_tampered_or_other_project_ticket_is_rejected(self):
        key = b"0123456789abcdef0123456789abcdef"
        ticket = server.app_ticket("알파", int(time.time()) + 60, key, "gh:kim")
        last = ticket[-1]
        tampered = ticket[:-1] + ("0" if last != "0" else "1")
        self.assertFalse(server.app_ticket_ok(tampered, "알파", key, "gh:kim"))
        self.assertFalse(server.app_ticket_ok(ticket, "베타", key, "gh:kim"))

    def test_malformed_tickets_never_raise(self):
        key = b"0123456789abcdef0123456789abcdef"
        for ticket in ("", "x", "1.2.3", "1.", "a.b", "é.0", "1." + "a" * 100,
                       "1.gh:kim.bad.mac", "1.gh:.kim.abcdef0123456789abcdef0123456789", None):
            with self.subTest(ticket=ticket):
                self.assertFalse(server.app_ticket_ok(ticket, "알파", key, "gh:kim"))
                self.assertIsNone(server.app_ticket_resolve(ticket, key, ["gh:kim"]))

    def test_csp_origin_is_https_under_tls(self):
        # 없으면 TLS 인데 출처가 http:// 로 변해도 아무 검사가 빨개지지 않는다.
        self.app()
        host = "192.168.0.5:18800"
        status, headers, _ = self.route("/app/알파/", tls=True, host=host)
        self.assertEqual(status[-1], 302)
        location = dict(headers).get("Location")
        status, headers, _ = self.route(location, tls=True, host=host)
        self.assertEqual(status[-1], 200)
        csp = dict(headers).get("Content-Security-Policy", "")
        self.assertIn("https://" + host, csp)
        self.assertNotIn("http://", csp)

    def test_csp_origin_rejects_unknown_host_name(self):
        # 없으면 Host: evil.com 하나로 evil.com 이 script-src 에 들어간 CSP 가 발급된다.
        self.app()
        for host in ("evil.com", "[::1].evil.com", "[::1]evil.com", "127.0.0.1:abc"):
            with self.subTest(host=host):
                status, headers, _ = self.route("/app/알파/", host=host)
                self.assertEqual(status[-1], 302)
                location = dict(headers).get("Location")
                status, headers, _ = self.route(location, host=host)
                self.assertEqual(status[-1], 200)
                csp = dict(headers).get("Content-Security-Policy", "")
                self.assertNotIn("evil.com", csp)
                self.assertNotIn("127.0.0.1", csp)
                self.assertIn("default-src 'self';", csp)

    def test_csp_origin_keeps_ip_and_localhost(self):
        # 없으면 운영이 IP 로 들어올 때 정상 출처가 막혀 CSP 가 'self' 만 남는다.
        self.app()
        for host, origin in (("127.0.0.1:18799", "http://127.0.0.1:18799"),
                             ("[::1]:18799", "http://[::1]:18799")):
            with self.subTest(host=host):
                status, headers, _ = self.route("/app/알파/", host=host)
                self.assertEqual(status[-1], 302)
                location = dict(headers).get("Location")
                status, headers, _ = self.route(location, host=host)
                self.assertEqual(status[-1], 200)
                csp = dict(headers).get("Content-Security-Policy", "")
                self.assertIn(origin, csp)

    def test_issued_ticket_expires_within_ttl(self):
        # 없으면 티켓 수명을 10년으로 바꿔도 아무 검사가 빨개지지 않는다.
        self.app()
        status, headers, _ = self.route("/app/알파/")
        self.assertEqual(status[-1], 302)
        location = dict(headers).get("Location")
        ticket = location.split("/app/~", 1)[1].split("/", 1)[0]
        exp = int(ticket.split(".")[0])
        now = time.time()
        self.assertGreater(exp, now)
        self.assertLess(exp, now + server.PROJECT_APP_TICKET_TTL_SEC + 2)

    def test_service_worker_skips_app_paths(self):
        # 없으면 서비스 워커가 /app/ 결과물을 캐시하기 시작해도 아무 검사가 빨개지지 않는다.
        sw = (pathlib.Path(__file__).resolve().parents[1]
              / "tools/aimem_monitor/static/sw.js").read_text(encoding="utf-8")
        lines = sw.splitlines()
        self.assertTrue(any("startswith('/app/')" in line.lower() and "return" in line
                            for line in lines))
        self.assertIn("VERSION", sw)

    def test_ticket_is_masked_in_server_log(self):
        h = server.Handler.__new__(server.Handler)
        h.log_date_time_string = lambda: "11/Nov/2026 00:00:00"
        mac = "97fa92835ac417492797dc21825a7fbb"
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            h.log_message('"%s" %s -', f"GET /app/~1794422924.{mac}/알파/index.html HTTP/1.1", "200")
        self.assertNotIn(mac, buf.getvalue())
        self.assertIn("/app/~***/", buf.getvalue())

    def test_mint_branch_needs_a_session_even_without_the_gate(self):
        self.app()
        h = server.Handler.__new__(server.Handler)
        h.path = "/app/%EC%95%8C%ED%8C%8C/"
        h.command = "GET"
        h.tls = False
        h.require_auth = True
        h.root = self.root
        h.access_token = "a" * 64
        h.headers = email.message.Message()
        h.headers["Host"] = "localhost:18799"
        h.client_address = ("127.0.0.1", 0)
        h._auth_gate = lambda path: False          # 인증 문이 뚫렸다고 치고
        status, headers = [], []
        h.send_response = lambda code: status.append(code)
        h.send_header = lambda key, value: headers.append((key, value))
        h.end_headers = lambda: None
        h.wfile = io.BytesIO()
        h.do_GET()
        self.assertEqual((status[-1], dict(headers).get("Location")), (302, "/login"))
        self.assertNotIn("/app/~", str(dict(headers).get("Location")))

    def test_csp_origin_rejects_lookalike_host_names(self):
        # 없으면 이름을 소문자·끝점으로 정규화한 뒤 허용하는 구현이 evil.com 계열을 통과시킨다.
        self.app()
        for host in ("evil.com:18799", "EVIL.COM", "evil.com."):
            with self.subTest(host=host):
                status, headers, _ = self.route("/app/알파/", host=host)
                self.assertEqual(status[-1], 302)
                location = dict(headers).get("Location")
                status, headers, _ = self.route(location, host=host)
                self.assertEqual(status[-1], 200)
                csp = dict(headers).get("Content-Security-Policy", "")
                self.assertNotIn("evil.com", csp)
                self.assertIn("default-src 'self';", csp)


class AppTicketSubjectRevocationTests(unittest.TestCase):
    """허용 목록에서 지운 계정이 이미 받은 티켓을 다시 쓸 수 없다는 회귀 시험."""
    TOKEN = "t" * 40
    NAME = "알파"
    Q = urllib.parse.quote(NAME)
    GITHUB_LOGIN = "taeseok"

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = pathlib.Path(tmp.name)
        web = self.root / "projects" / self.NAME / "web"
        web.mkdir(parents=True)
        (web / "index.html").write_text("<!doctype html><p id=secret>APP-BODY</p>", encoding="utf-8")
        (web / "style.css").write_text("body { color: #123; }\n", encoding="utf-8")
        (web / "app.js").write_text("document.title = 'JS-RAN';\n", encoding="utf-8")
        (self.root / "projects" / self.NAME / "app.json").write_text(
            json.dumps({"root": "web", "entry": "index.html"}), encoding="utf-8")
        (self.root / "AIMEM.md").write_text("# AIMEM\n\n- **REV: 1**\n", encoding="utf-8")
        allowed = self.root / server.GITHUB_ALLOW_FILE
        allowed.parent.mkdir(parents=True)
        allowed.write_text(self.GITHUB_LOGIN + "\n", encoding="utf-8")
        handler = type("H", (server.Handler,), {
            "root": self.root, "require_auth": True, "tls": False, "access_token": self.TOKEN,
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

    def github_headers(self, login=GITHUB_LOGIN):
        exp = int(time.time()) + server.SESSION_TTL_SEC
        value = server.sign_session(self.TOKEN, f"gh:{login}", exp)
        return {"Cookie": f"{server.SESSION_COOKIE}={value}"}

    def test_deleted_allowlist_account_cannot_reuse_its_ticket(self):
        headers = self.github_headers()
        status, loc, _ = self.get(f"/app/{self.Q}/", headers)
        self.assertEqual(status, 302)
        self.assertTrue(loc.startswith("/app/~"))
        status, _, body = self.get(loc)
        self.assertEqual(status, 200)
        self.assertIn(b"APP-BODY", body)

        allowed = self.root / server.GITHUB_ALLOW_FILE
        allowed.write_text("someoneelse\n", encoding="utf-8")
        status, _, body = self.get(loc)
        self.assertEqual(status, 403)
        self.assertIn("실행 티켓이 만료됐습니다", json.loads(body)["error"])
        self.assertNotIn(b"APP-BODY", body)

    def test_ticket_path_serves_index_and_subresources_without_credentials(self):
        status, loc, _ = self.get(f"/app/{self.Q}/", self.github_headers())
        self.assertEqual(status, 302)
        for path in (loc, loc + "index.html", loc + "style.css", loc + "app.js"):
            with self.subTest(path=path):
                status, _, body = self.get(path)
                self.assertEqual(status, 200, path)
                self.assertTrue(body)
        status, _, body = self.get(loc + "app.js")
        self.assertEqual(body, b"document.title = 'JS-RAN';\n")

    def test_other_subjects_ticket_is_refused_with_a_different_cookie(self):
        allowed = self.root / server.GITHUB_ALLOW_FILE
        allowed.write_text("kim\nlee\n", encoding="utf-8")
        status, loc, _ = self.get(f"/app/{self.Q}/", self.github_headers("kim"))
        self.assertEqual(status, 302)
        status, _, body = self.get(loc, self.github_headers("lee"))
        self.assertEqual(status, 403)
        self.assertIn("실행 티켓이 만료됐습니다", json.loads(body)["error"])
        self.assertNotIn(b"APP-BODY", body)


class TicketLimitAndLogRedactionTests(unittest.TestCase):
    key = b"0123456789abcdef0123456789abcdef"
    name = "알파"
    subject = "gh:kim"
    ticket_body = "1234.abcdef012345.abcdef0123456789abcdef0123456789"

    def test_ticket_length_allows_a_39_char_github_login(self):
        now = int(time.time())
        subject = "gh:" + "a" * 39
        ticket = server.app_ticket(self.name, now + 60, self.key, subject)
        self.assertLessEqual(len(ticket), 160)
        self.assertTrue(server.app_ticket_ok(ticket, self.name, self.key, subject, now=now))

    def test_ticket_within_ttl_is_valid(self):
        now = int(time.time())
        ticket = server.app_ticket(self.name, now + server.PROJECT_APP_TICKET_TTL_SEC, self.key, self.subject)
        self.assertTrue(server.app_ticket_ok(ticket, self.name, self.key, self.subject, now=now))

    def test_expired_ticket_is_rejected(self):
        now = int(time.time())
        ticket = server.app_ticket(self.name, now - 10, self.key, self.subject)
        self.assertFalse(server.app_ticket_ok(ticket, self.name, self.key, self.subject, now=now))

    def test_ticket_beyond_ttl_window_is_rejected(self):
        # 서명 키가 샜을 때 10년짜리 영구 티켓이 통과하지 않아야 한다.
        now = int(time.time())
        ticket = server.app_ticket(
            self.name, now + server.PROJECT_APP_TICKET_TTL_SEC + 3600, self.key, self.subject)
        self.assertFalse(server.app_ticket_ok(ticket, self.name, self.key, self.subject, now=now))

    def test_ticket_inside_ttl_grace_is_valid(self):
        now = int(time.time())
        ticket = server.app_ticket(
            self.name, now + server.PROJECT_APP_TICKET_TTL_SEC + 30, self.key, self.subject)
        self.assertTrue(server.app_ticket_ok(ticket, self.name, self.key, self.subject, now=now))

    def test_ticket_log_hides_plain_tilde_path(self):
        line = f"GET /app/~{self.ticket_body}/웹워들/ HTTP/1.1"
        redacted = server._TICKET_LOG_RE.sub("/app/~***", line)
        self.assertIn("/app/~***", redacted)
        self.assertNotIn(self.ticket_body, redacted)

    def test_ticket_log_hides_upper_percent_encoded_path(self):
        line = f"GET /app/%7E{self.ticket_body}/웹워들/ HTTP/1.1"
        redacted = server._TICKET_LOG_RE.sub("/app/~***", line)
        self.assertIn("/app/~***", redacted)
        self.assertNotIn(self.ticket_body, redacted)

    def test_ticket_log_hides_lower_percent_encoded_path(self):
        line = f"GET /app/%7e{self.ticket_body}/웹워들/ HTTP/1.1"
        redacted = server._TICKET_LOG_RE.sub("/app/~***", line)
        self.assertIn("/app/~***", redacted)
        self.assertNotIn(self.ticket_body, redacted)

    def test_ticket_log_leaves_ticketless_path_alone(self):
        line = "GET /app/웹워들/ HTTP/1.1"
        self.assertEqual(server._TICKET_LOG_RE.sub("/app/~***", line), line)


if __name__ == "__main__":
    unittest.main()
