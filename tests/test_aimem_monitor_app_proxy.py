"""R32 T-332: `/app/~<티켓>/<앱>/api/*` 이어 주기 - 진짜 소켓·진짜 자식 프로세스로 본다.

임시 저장소에 `projects/<앱>/app.json`(`server` 선언) + 가짜 앱 서버(`serve.py`: 받은 머리·본문을 JSON 으로 돌려주고 호출 기록을 남김)를
두고, 인증을 켠 모니터에 붙는다. 앱 서버에 **닿았는지**는 가짜 서버의 호출 기록(`calls.log`)으로 판단한다.
"""
import http.client
import http.server
import json
import os
import pathlib
import signal
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
import urllib.parse

HERE = pathlib.Path(__file__).resolve()
TOOLS = HERE.parents[1] / "tools"
sys.path.insert(0, str(TOOLS))

from aimem_monitor import app_server, server  # noqa: E402

TOKEN = "t" * 40
NAME = "알파"
Q = urllib.parse.quote(NAME)

FAKE_SERVE = r'''
import http.server, json, pathlib, sys, urllib.parse
args = sys.argv[1:]
port = int(args[args.index("--port") + 1])
LOG = pathlib.Path(__file__).resolve().parent / "calls.log"

class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _do(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n).decode("utf-8", "replace") if n else ""
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(self.command + " " + self.path + "\n")
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        status = int((q.get("status") or ["200"])[0])
        out = json.dumps({"method": self.command, "path": self.path, "body": body,
                          "headers": {k.lower(): v for k, v in self.headers.items()}}).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(out)
    do_GET = do_POST = do_HEAD = _do

http.server.ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
'''


def make_app(root, name, server_decl="serve.py", write_script=True):
    d = root / "projects" / name
    (d / "web").mkdir(parents=True)
    (d / "web" / "index.html").write_text("<!doctype html><p>APP</p>", encoding="utf-8")
    manifest = {"root": "web", "entry": "index.html"}
    if server_decl is not None:
        manifest["server"] = server_decl
    (d / "app.json").write_text(json.dumps(manifest), encoding="utf-8")
    if write_script:
        (d / "serve.py").write_text(FAKE_SERVE, encoding="utf-8")
    return d


def calls(d):
    p = d / "calls.log"
    return p.read_text(encoding="utf-8").splitlines() if p.exists() else []


def pid_alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    try:
        stat = pathlib.Path(f"/proc/{pid}/stat").read_text()
        if stat.rsplit(")", 1)[1].split()[0] == "Z":
            return False
    except (OSError, IndexError):
        return False
    return True


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = pathlib.Path(tmp.name).resolve()
        (self.root / "AIMEM.md").write_text("# AIMEM\n\n- **REV: 1**\n", encoding="utf-8")
        self.app = make_app(self.root, NAME)
        handler = type("H", (server.Handler,), {"root": self.root, "require_auth": True, "tls": False,
                                                "access_token": TOKEN, "guard": server.LoginGuard(),
                                                "log_message": lambda *a, **k: None})
        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=self.httpd.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True).start()
        self.port = self.httpd.server_address[1]
        self.reg = app_server.registry(self.root)
        self.addCleanup(self.httpd.server_close)
        self.addCleanup(self.httpd.shutdown)
        self.addCleanup(self.reg.stop_all)

    # -- 도우미 --
    def req(self, method, path, headers=None, body=None, port=None):
        con = http.client.HTTPConnection("127.0.0.1", port or self.port, timeout=20)
        try:
            con.putrequest(method, path, skip_accept_encoding=True)
            for k, v in (headers or {}).items():
                con.putheader(k, v)
            if body is not None:
                con.putheader("Content-Length", str(len(body)))
            con.endheaders(body)
            r = con.getresponse()
            return r.status, {k.lower(): v for k, v in r.getheaders()}, r.read()
        finally:
            con.close()

    def ticket_base(self, name=NAME, port=None):
        status, h, _ = self.req("GET", f"/app/{urllib.parse.quote(name)}/", {"Authorization": "Bearer " + TOKEN}, port=port)
        self.assertEqual(status, 302)
        return h["location"]          # /app/~<티켓>/<이름>/

    def forged(self, name=NAME, exp=None, subject=server.SESSION_SUBJECT_TOKEN, key=None):
        key = key or TOKEN.encode("ascii")
        exp = int(time.time()) + 3600 if exp is None else exp
        t = server.app_ticket(name, exp, key, subject)
        return f"/app/~{t}/{urllib.parse.quote(name)}/"


class ProxyTests(Base):
    def test_ticket_get_is_forwarded_with_app_headers(self):
        base = self.ticket_base()
        status, h, body = self.req("GET", base + "api/echo?x=1&status=200")
        self.assertEqual(status, 200)
        got = json.loads(body)
        self.assertEqual((got["method"], got["path"]), ("GET", "/api/echo?x=1&status=200"))
        self.assertEqual(h["access-control-allow-origin"], "null")
        self.assertIn("sandbox", h["content-security-policy"])
        self.assertEqual(calls(self.app), ["GET /api/echo?x=1&status=200"])

    def test_ticket_post_is_forwarded_with_status_and_body(self):
        base = self.ticket_base()
        payload = json.dumps({"a": "가나다"}).encode("utf-8")
        status, h, body = self.req("POST", base + "api/save?status=201",
                                   {"Content-Type": "application/json"}, payload)
        self.assertEqual(status, 201)
        got = json.loads(body)
        self.assertEqual((got["method"], got["body"]), ("POST", payload.decode("utf-8")))
        self.assertEqual(got["headers"]["content-type"], "application/json")
        self.assertEqual(h["access-control-allow-origin"], "null")
        self.assertIn("sandbox", h["content-security-policy"])

    def test_app_status_codes_pass_through(self):
        base = self.ticket_base()
        status, _, body = self.req("GET", base + "api/x?status=418")
        self.assertEqual(status, 418)
        self.assertEqual(json.loads(body)["path"], "/api/x?status=418")

    def test_no_ticket_never_reaches_the_app_server(self):
        for method, headers, body in (("GET", None, None), ("POST", {"Content-Type": "application/json"}, b"{}"),
                                      ("GET", {"Authorization": "Bearer " + TOKEN}, None)):
            with self.subTest(method=method, headers=bool(headers)):
                status, h, _ = self.req(method, f"/app/{Q}/api/x", headers, body)
                self.assertIn(status, (302, 401, 403))
                if status == 302:      # 로그인 또는 티켓 발급(이 요청은 앱 서버로 가지 않음)
                    self.assertTrue(h["location"] == "/login" or h["location"].startswith("/app/~"))
        self.assertEqual(calls(self.app), [])
        self.assertFalse((self.root / ".aimem" / "appservers" / f"{NAME}.json").exists())

    def test_forged_ticket_is_403_and_not_forwarded(self):
        good = self.ticket_base()
        parts = good.split("/")
        bad_mac = parts[2][:-4] + ("0000" if not parts[2].endswith("0000") else "1111")
        for label, base in (("서명 틀림", f"/app/{bad_mac}/{Q}/"),
                            ("다른 키", self.forged(key=b"k" * 40)),
                            ("쓰레기", f"/app/~garbage/{Q}/")):
            for method, body in (("GET", None), ("POST", b"{}")):
                with self.subTest(label=label, method=method):
                    status, _, _ = self.req(method, base + "api/x", {"Content-Type": "application/json"}, body)
                    self.assertEqual(status, 403)
        self.assertEqual(calls(self.app), [])

    def test_expired_ticket_is_403_and_not_forwarded(self):
        base = self.forged(exp=int(time.time()) - 10)
        for method, body in (("GET", None), ("POST", b"{}")):
            with self.subTest(method=method):
                status, _, _ = self.req(method, base + "api/x", {"Content-Type": "application/json"}, body)
                self.assertEqual(status, 403)
        self.assertEqual(calls(self.app), [])

    def test_other_apps_ticket_is_403(self):
        beta = make_app(self.root, "베타")
        other = self.ticket_base("베타")
        status, _, _ = self.req("GET", other.replace(urllib.parse.quote("베타"), Q) + "api/x")
        self.assertEqual(status, 403)
        status, _, _ = self.req("POST", other.replace(urllib.parse.quote("베타"), Q) + "api/x",
                                {"Content-Type": "application/json"}, b"{}")
        self.assertEqual(status, 403)
        self.assertEqual(calls(self.app) + calls(beta), [])

    def test_app_without_server_declaration_keeps_old_behaviour(self):
        plain = make_app(self.root, "웹", server_decl=None)
        base = self.ticket_base("웹")
        status, _, _ = self.req("GET", base + "api/x")
        self.assertEqual(status, 404)
        status, _, _ = self.req("POST", base + "api/x", {"Content-Type": "application/json"}, b"{}")
        self.assertEqual(status, 404)
        status, _, body = self.req("GET", base)          # 정적 파일은 그대로
        self.assertEqual(status, 200)
        self.assertIn(b"APP", body)
        self.assertEqual(calls(plain), [])
        self.assertEqual(list((self.root / ".aimem" / "appservers").glob("*.json")) if (self.root / ".aimem" / "appservers").exists() else [], [])

    def test_bad_server_declarations_are_not_forwarded(self):
        outside = self.root / "밖.py"
        outside.write_text(FAKE_SERVE, encoding="utf-8")
        cases = {"dotdot": ("../밖.py", True), "absolute": (str(outside), True), "missing": ("없음.py", False),
                 "not-py": ("serve.txt", True), "symlink": ("link.py", True), "dotfile": (".hidden.py", True),
                 "backslash": ("a\\b.py", False)}
        for label, (decl, write_script) in cases.items():
            with self.subTest(label=label):
                d = make_app(self.root, f"p-{label}", server_decl=decl, write_script=write_script)
                (d / "serve.txt").write_text(FAKE_SERVE, encoding="utf-8")
                (d / ".hidden.py").write_text(FAKE_SERVE, encoding="utf-8")
                (d / "link.py").symlink_to(d / "serve.py")
                app = server.project_app(f"p-{label}", self.root)
                self.assertTrue(app["runnable"])                    # 앱 전체는 그대로 실행 가능
                self.assertNotIn("server", app)
                self.assertTrue(app.get("server_error"))
                base = self.ticket_base(f"p-{label}")
                status, _, _ = self.req("GET", base + "api/x")
                self.assertEqual(status, 404)
                self.assertEqual(calls(d), [])
        status, _, _ = self.req("GET", self.ticket_base() + "api/ok")   # 올바른 선언은 그대로 된다
        self.assertEqual(status, 200)
        self.assertEqual(server.project_app(NAME, self.root)["server"], "serve.py")

    def test_symlinked_directory_in_server_path_is_refused(self):
        d = make_app(self.root, "디렉", server_decl="sub/serve.py", write_script=False)
        real = self.root / "real"
        real.mkdir()
        (real / "serve.py").write_text(FAKE_SERVE, encoding="utf-8")
        (d / "sub").symlink_to(real)
        app = server.project_app("디렉", self.root)
        self.assertNotIn("server", app)
        self.assertTrue(app.get("server_error"))

    def test_forwarded_request_carries_no_monitor_credentials(self):
        base = self.ticket_base()
        status, _, body = self.req("POST", base + "api/echo", {
            "Content-Type": "application/json", "Authorization": "Bearer " + TOKEN,
            "Cookie": "aimem_session=abc; other=1", "Origin": "null", "Referer": "http://x/",
            "X-Forwarded-For": "1.2.3.4", "Accept": "application/json", "X-Custom": "y"}, b"{}")
        self.assertEqual(status, 200)
        hdrs = json.loads(body)["headers"]
        for banned in ("cookie", "authorization", "origin", "referer", "x-forwarded-for", "x-custom"):
            self.assertNotIn(banned, hdrs)
        self.assertNotIn(TOKEN, body.decode("utf-8"))
        child_port = json.loads((self.root / ".aimem" / "appservers" / f"{NAME}.json").read_text())["port"]
        self.assertEqual(hdrs["host"], f"127.0.0.1:{child_port}")
        self.assertNotEqual(child_port, self.port)
        self.assertEqual(hdrs["accept"], "application/json")

    def test_options_preflight_needs_ticket_and_answers_204(self):
        base = self.ticket_base()
        status, h, body = self.req("OPTIONS", base + "api/save", {"Origin": "null"})
        self.assertEqual(status, 204)
        self.assertEqual(body, b"")
        self.assertEqual(h["access-control-allow-origin"], "null")
        self.assertEqual(h["access-control-allow-methods"], "GET, POST")
        self.assertEqual(h["access-control-allow-headers"], "Content-Type")
        self.assertEqual(h["access-control-max-age"], "600")
        self.assertEqual(calls(self.app), [])                  # 사전 요청은 앱 서버까지 가지 않는다

    def test_options_without_valid_ticket_or_declaration_is_refused(self):
        plain = make_app(self.root, "웹", server_decl=None)
        no_ticket = self.req("OPTIONS", f"/app/{Q}/api/save")[0]
        forged = self.req("OPTIONS", f"/app/~garbage/{Q}/api/save")[0]
        expired = self.req("OPTIONS", self.forged(exp=int(time.time()) - 5) + "api/save")[0]
        undeclared = self.req("OPTIONS", self.ticket_base("웹") + "api/save")[0]
        elsewhere = self.req("OPTIONS", "/api/state")[0]
        self.assertIn(no_ticket, (401, 403, 501))
        self.assertEqual(forged, 403)
        self.assertEqual(expired, 403)
        self.assertIn(undeclared, (404, 501))
        self.assertIn(elsewhere, (401, 501))
        self.assertEqual(calls(plain) + calls(self.app), [])

    def test_options_forged_ticket_same_answer_declared_or_not(self):
        make_app(self.root, "웹", server_decl=None)
        declared = self.req("OPTIONS", f"/app/~garbage/{Q}/api/save")
        undeclared = self.req("OPTIONS", "/app/~garbage/%EC%9B%B9/api/save")
        missing = self.req("OPTIONS", "/app/~garbage/nosuchapp/api/save")
        self.assertEqual(declared[0], 403)
        self.assertEqual(undeclared[0], 403)
        self.assertEqual(missing[0], 403)

    def test_oversized_body_is_413_before_reading(self):
        base = self.ticket_base()
        con = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            con.putrequest("POST", base + "api/big")
            con.putheader("Content-Type", "application/json")
            con.putheader("Content-Length", str(self.reg.max_req_body + 1))
            con.endheaders()                       # 본문은 보내지 않는다 - 읽기 전에 거절해야 한다
            r = con.getresponse()
            self.assertEqual(r.status, 413)
            self.assertEqual(r.getheader("Access-Control-Allow-Origin"), "null")
            r.read()
        finally:
            con.close()
        self.assertEqual(calls(self.app), [])

    def test_missing_or_negative_content_length(self):
        base = self.ticket_base()
        con = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            con.putrequest("POST", base + "api/x")
            con.putheader("Content-Type", "application/json")
            con.endheaders()
            r = con.getresponse()
            self.assertEqual(r.status, 411)
            r.read()
        finally:
            con.close()
        con = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            con.putrequest("POST", base + "api/x")
            con.putheader("Content-Length", "-1")
            con.endheaders()
            self.assertEqual(con.getresponse().status, 400)
        finally:
            con.close()
        self.assertEqual(calls(self.app), [])

    def test_audit_log_has_app_api_line_without_ticket(self):
        base = self.ticket_base()
        ticket = base.split("/")[2][1:]
        self.req("GET", base + "api/echo?secret=zzz&status=202")
        log = (self.root / server.AUDIT_LOG).read_text(encoding="utf-8")
        lines = [l for l in log.splitlines() if "\tapp-api\t" in l]
        self.assertEqual(len(lines), 1)
        self.assertIn("GET", lines[0])
        self.assertIn("/api/echo", lines[0])
        self.assertIn("202", lines[0])
        self.assertIn("ms", lines[0])
        self.assertNotIn(ticket, log)                           # 티켓은 가려짐
        self.assertNotIn("secret=zzz", lines[0])                # 쿼리는 남기지 않음

    def test_path_traversal_in_api_is_not_forwarded(self):
        base = self.ticket_base()
        for tail in ("api/%2e%2e/x", "api/%2E%2E%2fsecret"):
            with self.subTest(tail=tail):
                status, _, _ = self.req("GET", base + tail)
                self.assertIn(status, (403, 404))
        self.assertEqual(calls(self.app), [])


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = pathlib.Path(tmp.name).resolve()
        (self.root / "AIMEM.md").write_text("# AIMEM\n\n- **REV: 1**\n", encoding="utf-8")
        self.app = make_app(self.root, NAME)

    def test_monitor_shutdown_takes_the_child_down(self):
        s = socket_free_port()
        env = dict(os.environ, PYTHONPATH=str(TOOLS))
        mon = subprocess.Popen([sys.executable, "-m", "aimem_monitor", "--auth", "--port", str(s),
                                "--root", str(self.root)], env=env, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, start_new_session=True)
        child = None
        try:
            token = wait_for_token(self.root)
            self.wait_up(s)
            con = http.client.HTTPConnection("127.0.0.1", s, timeout=20)
            con.request("GET", f"/app/{Q}/", headers={"Authorization": "Bearer " + token})
            loc = con.getresponse().getheader("Location")
            con.close()
            con = http.client.HTTPConnection("127.0.0.1", s, timeout=20)
            con.request("GET", loc + "api/x")
            r = con.getresponse()
            r.read()
            con.close()
            self.assertEqual(r.status, 200)
            child = json.loads((self.root / ".aimem" / "appservers" / f"{NAME}.json").read_text())["pid"]
            self.assertTrue(pid_alive(child))
            mon.send_signal(signal.SIGTERM)
            mon.wait(timeout=20)
            deadline = time.time() + 10
            while pid_alive(child) and time.time() < deadline:
                time.sleep(0.1)
            self.assertFalse(pid_alive(child), "모니터를 내렸는데 앱 서버 자식이 남았다")
        finally:
            if mon.poll() is None:
                mon.kill()
                mon.wait()
            if child and pid_alive(child):
                os.kill(child, signal.SIGKILL)

    def wait_up(self, port):
        deadline = time.time() + 15
        while time.time() < deadline:
            try:
                with __import__("socket").create_connection(("127.0.0.1", port), timeout=0.3):
                    return
            except OSError:
                time.sleep(0.1)
        self.fail("모니터가 뜨지 않았다")

    def test_cleanup_stale_takes_down_a_leftover_child(self):
        script = self.app / "serve.py"
        port = socket_free_port()
        proc = subprocess.Popen([sys.executable, str(script), "--host", "127.0.0.1", "--port", str(port)],
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                start_new_session=True)
        self.addCleanup(lambda: proc.poll() is None and proc.kill())
        state = self.root / ".aimem" / "appservers"
        state.mkdir(parents=True)
        (state / f"{NAME}.json").write_text(json.dumps(
            {"pid": proc.pid, "port": port, "script": str(script), "started": time.time()}), encoding="utf-8")
        self.assertTrue(pid_alive(proc.pid))
        killed = app_server.AppServers(state).cleanup_stale()
        self.assertEqual(killed, [proc.pid])
        proc.wait(timeout=5)
        self.assertFalse(pid_alive(proc.pid))
        self.assertFalse((state / f"{NAME}.json").exists())

    def test_cleanup_stale_leaves_unrelated_pid_alone(self):
        other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"],
                                 stdin=subprocess.DEVNULL, start_new_session=True)
        self.addCleanup(lambda: other.poll() is None and other.kill())
        state = self.root / ".aimem" / "appservers"
        state.mkdir(parents=True)
        (state / "x.json").write_text(json.dumps(
            {"pid": other.pid, "port": 1, "script": str(self.app / "serve.py"), "started": 0}), encoding="utf-8")
        self.assertEqual(app_server.AppServers(state).cleanup_stale(), [])   # 재사용된 pid 보호
        self.assertIsNone(other.poll())
        self.assertFalse((state / "x.json").exists())


def socket_free_port():
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_for_token(root):
    p = root / server.TOKEN_FILE
    deadline = time.time() + 15
    while time.time() < deadline:
        if p.exists() and p.read_text().strip():
            return p.read_text().strip()
        time.sleep(0.1)
    raise AssertionError("토큰 파일이 생기지 않았다")


if __name__ == "__main__":
    unittest.main()
