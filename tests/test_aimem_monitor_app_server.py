"""app_server.py 시험 - 작은 가짜 앱 서버를 진짜로 띄웁니다."""
import json
import os
import pathlib
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools"))

from aimem_monitor import app_server  # noqa: E402
from aimem_monitor.app_server import AppServerError, AppServers  # noqa: E402

FAKE = r'''
import http.server, json, os, sys, time
args = sys.argv[1:]
host = args[args.index("--host") + 1]
port = int(args[args.index("--port") + 1])

class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass
    def _send(self, code, body, ctype="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def handle_any(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n) if n else b""
        if self.path.startswith("/api/slow"):
            time.sleep(3)
            return self._send(200, b"{}")
        if self.path.startswith("/api/big"):
            return self._send(200, b"x" * 5000, "text/plain")
        out = {"headers": {k.lower(): v for k, v in self.headers.items()},
               "body": body.decode("utf-8", "replace"), "pid": os.getpid(), "host": host,
               "method": self.command, "path": self.path,
               "secret": os.environ.get("AIMEM_TEST_SECRET"),
               "key": os.environ.get("FOO_API_KEY"),
               "path_env": "PATH" in os.environ}
        self._send(200, json.dumps(out).encode())
    do_GET = do_POST = handle_any

class S(http.server.ThreadingHTTPServer):
    daemon_threads = True

S((host, port), H).serve_forever()
'''


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = pathlib.Path(tmp.name)
        self.cwd = self.tmp / "proj"
        self.cwd.mkdir()
        self.script = self.cwd / "serve.py"
        self.script.write_text(FAKE, encoding="utf-8")
        os.environ["AIMEM_TEST_SECRET"] = "s3cret"
        os.environ["FOO_API_KEY"] = "k3y"
        self.addCleanup(os.environ.pop, "AIMEM_TEST_SECRET", None)
        self.addCleanup(os.environ.pop, "FOO_API_KEY", None)
        self.pids = []
        self.servers = []

    def make(self, **kw):
        kw.setdefault("start_timeout", 5.0)
        kw.setdefault("forward_timeout", 5.0)
        s = AppServers(self.tmp / "state", **kw)
        self.servers.append(s)
        return s

    def tearDown(self):
        for s in self.servers:
            for e in list(s._entries.values()):
                self.pids.append(e.proc.pid)
            s.stop_all()
        for pid in self.pids:
            self.assertTrue(app_server._gone(pid), f"남은 자식 {pid}")

    def get(self, s, path="/api/echo", method="GET", headers=None, body=b""):
        st, ct, data = s.forward("a", self.script, self.cwd, method, path, headers or {}, body)
        return st, ct, data


class EnsureTests(Base):
    def test_ensure_starts_then_reuses(self):
        s = self.make()
        p1 = s.ensure("a", self.script, self.cwd)
        p2 = s.ensure("a", self.script, self.cwd)
        self.assertEqual(p1, p2)
        pid1 = json.loads(self.get(s)[2])["pid"]
        pid2 = json.loads(self.get(s)[2])["pid"]
        self.assertEqual(pid1, pid2)

    def test_concurrent_ensure_starts_one(self):
        s = self.make()
        ports = []
        ts = [threading.Thread(target=lambda: ports.append(s.ensure("a", self.script, self.cwd)))
              for _ in range(4)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(len(set(ports)), 1)
        self.assertEqual(len(s._entries), 1)

    def test_binds_loopback(self):
        s = self.make()
        self.assertEqual(json.loads(self.get(s)[2])["host"], "127.0.0.1")

    def test_record_written(self):
        s = self.make()
        port = s.ensure("a", self.script, self.cwd)
        rec = json.loads((self.tmp / "state" / "a.json").read_text())
        self.assertEqual(rec["port"], port)
        self.assertEqual(rec["script"], str(self.script))

    def test_changed_script_restarts_child(self):
        s = self.make()
        pid1 = json.loads(self.get(s)[2])["pid"]
        self.pids.append(pid1)
        script_b = self.cwd / "serve_b.py"
        script_b.write_text(FAKE, encoding="utf-8")
        s.ensure("a", script_b, self.cwd)
        pid2 = s._entries["a"].proc.pid
        self.pids.append(pid2)
        self.assertNotEqual(pid1, pid2)
        self.assertEqual(s._entries["a"].script, str(script_b))
        self.assertTrue(app_server._gone(pid1))

    def test_dead_child_restarted(self):
        s = self.make()
        pid1 = json.loads(self.get(s)[2])["pid"]
        self.pids.append(pid1)
        os.killpg(pid1, 9)
        deadline = time.time() + 3
        while not app_server._gone(pid1, s._entries["a"].proc) and time.time() < deadline:
            time.sleep(0.05)
        pid2 = json.loads(self.get(s)[2])["pid"]
        self.assertNotEqual(pid1, pid2)

    def test_failing_script_503_no_leftover(self):
        bad = self.cwd / "bad.py"
        bad.write_text("import sys; sys.exit(3)\n")
        s = self.make()
        with self.assertRaises(AppServerError) as cm:
            s.ensure("b", bad, self.cwd)
        self.assertEqual(cm.exception.status, 503)
        self.assertFalse(s._entries)

    def test_never_listening_script_503_killed(self):
        idle = self.cwd / "idle.py"
        idle.write_text("import time; time.sleep(60)\n")
        s = self.make(start_timeout=0.6)
        with self.assertRaises(AppServerError) as cm:
            s.ensure("c", idle, self.cwd)
        self.assertEqual(cm.exception.status, 503)
        self.assertNotIn("c", s._entries)
        import subprocess
        ps = subprocess.run(["ps", "-eo", "args"], capture_output=True, text=True).stdout
        self.assertFalse([l for l in ps.splitlines() if str(idle) in l])


class ForwardTests(Base):
    def test_headers_narrowed(self):
        s = self.make()
        st, ct, data = self.get(s, "/api/echo?x=1", "POST", {
            "Cookie": "a=b", "Authorization": "Bearer z", "Origin": "http://evil",
            "Referer": "http://evil/", "X-Forwarded-For": "1.2.3.4",
            "Content-Type": "application/json", "Accept": "application/json",
            "Host": "monitor.example"}, b'{"a":1}')
        self.assertEqual(st, 200)
        out = json.loads(data)
        h = out["headers"]
        port = s._entries["a"].port
        self.assertEqual(h["host"], f"127.0.0.1:{port}")
        for bad in ("cookie", "authorization", "origin", "referer", "x-forwarded-for"):
            self.assertNotIn(bad, h)
        self.assertEqual(h["content-type"], "application/json")
        self.assertEqual(out["body"], '{"a":1}')
        self.assertEqual(out["path"], "/api/echo?x=1")
        self.assertTrue(ct.startswith("application/json"))

    def test_child_env_narrow(self):
        s = self.make()
        out = json.loads(self.get(s)[2])
        self.assertIsNone(out["secret"])
        self.assertIsNone(out["key"])
        self.assertTrue(out["path_env"])

    def test_request_body_limit_413(self):
        s = self.make(max_req_body=10)
        with self.assertRaises(AppServerError) as cm:
            self.get(s, "/api/echo", "POST", {}, b"x" * 11)
        self.assertEqual(cm.exception.status, 413)
        self.assertFalse(s._entries)

    def test_response_limit_502(self):
        s = self.make(max_resp_body=1000)
        with self.assertRaises(AppServerError) as cm:
            self.get(s, "/api/big")
        self.assertEqual(cm.exception.status, 502)

    def test_slow_504(self):
        s = self.make(forward_timeout=0.5)
        with self.assertRaises(AppServerError) as cm:
            self.get(s, "/api/slow")
        self.assertEqual(cm.exception.status, 504)

    def test_non_api_path_404(self):
        s = self.make()
        for p in ("/index.html", "/", "/apix", "/api", "/api/a\r\nX: y"):
            with self.assertRaises(AppServerError) as cm:
                self.get(s, p)
            self.assertEqual(cm.exception.status, 404)
        self.assertFalse(s._entries)

    def test_inflight_429(self):
        s = self.make(max_inflight=1, forward_timeout=5.0)
        s.ensure("a", self.script, self.cwd)
        t = threading.Thread(target=lambda: self.get(s, "/api/slow"))
        t.start()
        deadline = time.time() + 3
        while s._entries["a"].inflight < 1 and time.time() < deadline:
            time.sleep(0.02)
        with self.assertRaises(AppServerError) as cm:
            self.get(s, "/api/echo")
        self.assertEqual(cm.exception.status, 429)
        t.join()
        self.assertEqual(self.get(s)[0], 200)


class StopTests(Base):
    def test_stop_kills(self):
        s = self.make()
        pid = json.loads(self.get(s)[2])["pid"]
        self.pids.append(pid)
        self.assertTrue(s.stop("a"))
        self.assertTrue(app_server._gone(pid))
        self.assertFalse(s.stop("a"))
        self.assertFalse((self.tmp / "state" / "a.json").exists())

    def test_stop_all(self):
        s = self.make()
        pids = []
        for n in ("a", "b"):
            s.ensure(n, self.script, self.cwd)
            pids.append(s._entries[n].proc.pid)
        self.pids += pids
        s.stop_all()
        for pid in pids:
            self.assertTrue(app_server._gone(pid))
        self.assertFalse(s._entries)

    def test_reap_idle(self):
        s = self.make(idle_sec=60)
        s.ensure("a", self.script, self.cwd)
        pid = s._entries["a"].proc.pid
        self.pids.append(pid)
        self.assertEqual(s.reap_idle(), [])
        self.assertEqual(s.reap_idle(now=time.time() + 120), ["a"])
        self.assertTrue(app_server._gone(pid))

    def test_cleanup_stale_kills_recorded(self):
        s1 = self.make()
        s1.ensure("a", self.script, self.cwd)
        pid = s1._entries["a"].proc.pid
        self.pids.append(pid)
        s2 = self.make()  # 새 모니터
        self.assertEqual(s2.cleanup_stale(), [pid])
        self.assertTrue(app_server._gone(pid))
        self.assertFalse((self.tmp / "state" / "a.json").exists())

    def test_cleanup_stale_spares_dash_c_record(self):
        import subprocess
        other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"],
                                 start_new_session=True)
        self.addCleanup(other.wait)
        self.addCleanup(other.kill)
        state = self.tmp / "state"
        state.mkdir()
        (state / "zz.json").write_text(json.dumps(
            {"pid": other.pid, "port": 1, "script": "-c", "started": 0}))
        s = self.make()
        self.assertEqual(s.cleanup_stale(), [])
        self.assertIsNone(other.poll())

    def test_cleanup_stale_spares_other_cmdline(self):
        import subprocess
        other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"],
                                 start_new_session=True)
        self.addCleanup(other.wait)
        self.addCleanup(other.kill)
        state = self.tmp / "state"
        state.mkdir()
        (state / "x.json").write_text(json.dumps(
            {"pid": other.pid, "port": 1, "script": str(self.script), "started": 0}))
        s = self.make()
        self.assertEqual(s.cleanup_stale(), [])
        self.assertIsNone(other.poll())
        self.assertFalse((state / "x.json").exists())


class RegistryTests(unittest.TestCase):
    def test_registry_same_per_root(self):
        with tempfile.TemporaryDirectory() as d:
            a = app_server.registry(d)
            self.assertIs(a, app_server.registry(d))
            self.assertEqual(a.state_dir, pathlib.Path(d).resolve() / ".aimem" / "appservers")

    def test_error_fields(self):
        e = AppServerError(413, "크다")
        self.assertEqual((e.status, e.message), (413, "크다"))


if __name__ == "__main__":
    unittest.main()
