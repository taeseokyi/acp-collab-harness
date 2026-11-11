"""`/app/<프로젝트>/` 실행 경로의 뒷단 시험. 소켓은 열지 않고 함수를 직접 부릅니다."""
import email.message
import io
import json
import pathlib
import sys
import tempfile
import time
import unittest

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

    def route(self, path, auth=False):
        h = server.Handler.__new__(server.Handler)
        h.path = path
        h.command = "GET"
        h.tls = False
        h.require_auth = auth
        h.root = self.root
        h.access_token = None
        h.headers = email.message.Message()
        h.headers["Host"] = "localhost:18799"
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

    def test_ticket_path_passes_auth_gate_without_session(self):
        self.app()
        ticket = server.app_ticket("알파", int(time.time()) + 60, server._APP_TICKET_FALLBACK_KEY)
        status, headers, body = self.route(
            f"/app/~{ticket}/%EC%95%8C%ED%8C%8C/", auth=True)
        self.assertEqual((status[-1], body), (200, b"<!doctype html>"))

        expired = server.app_ticket("알파", int(time.time()) - 1, server._APP_TICKET_FALLBACK_KEY)
        status, headers, body = self.route(
            f"/app/~{expired}/%EC%95%8C%ED%8C%8C/", auth=True)
        self.assertEqual(status[-1], 403)
        self.assertIn("실행 티켓이 만료됐습니다", json.loads(body)["error"])

    def test_app_ticket_roundtrip(self):
        key = b"0123456789abcdef0123456789abcdef"
        exp = int(time.time()) + 60
        ticket = server.app_ticket("알파", exp, key)
        self.assertTrue(server.app_ticket_ok(ticket, "알파", key))

    def test_expired_ticket_is_rejected(self):
        key = b"0123456789abcdef0123456789abcdef"
        ticket = server.app_ticket("알파", int(time.time()) - 1, key)
        self.assertFalse(server.app_ticket_ok(ticket, "알파", key))

    def test_tampered_or_other_project_ticket_is_rejected(self):
        key = b"0123456789abcdef0123456789abcdef"
        ticket = server.app_ticket("알파", int(time.time()) + 60, key)
        last = ticket[-1]
        tampered = ticket[:-1] + ("0" if last != "0" else "1")
        self.assertFalse(server.app_ticket_ok(tampered, "알파", key))
        self.assertFalse(server.app_ticket_ok(ticket, "베타", key))

    def test_malformed_tickets_never_raise(self):
        key = b"0123456789abcdef0123456789abcdef"
        for ticket in ("", "x", "1.2.3", "1.", "a.b", "é.0", "1." + "a" * 100, None):
            with self.subTest(ticket=ticket):
                self.assertFalse(server.app_ticket_ok(ticket, "알파", key))


if __name__ == "__main__":
    unittest.main()
