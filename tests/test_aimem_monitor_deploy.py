"""앱 배포 (`tools/aimem_monitor/deploy.py`, 2026-11-16) - 앱을 배포 포트에 계속 띄워 두기.

- 켜면 포트(첫 포트부터)·토큰을 받고, 배포 문지기가 약속한 인자로 뜨고, 프록시 설정에 공개 포트가 적힌다
- 다시 켜도 같은 프로세스, 내리면 죽고 포트·토큰은 남는다(다시 켜면 같은 주소·토큰)
- 토큰은 인자가 아니라 환경으로 넘어가고, 토큰 없이 켜면 안 넘어간다. 토큰 쓰기나 선언이 바뀌면 다시 띄운다
- 서버가 없는 앱도 배포된다(`--server` 없이)
- 바로 죽는 문지기·인증서 없음·포트 소진은 까닭을 말하며 거절한다
- 모니터가 뜰 때 죽어 있는 배포를 다시 띄운다. 프로젝트를 지우면 잊는다
- 서버 경로: 운영 저장소가 아니면 403, 형식 오류 400, 실행 선언이 없으면 409, 선언만 있으면(서버 없이도) 배포 대상이다

문지기 자체(`deploy_gate.py`)는 `test_aimem_deploy_gate.py` 가 본다 - 여기서는 인자·환경만 적는 가짜 문지기를 쓴다.
"""
import json
import os
import pathlib
import socket
import stat
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from aimem_monitor import deploy, server  # noqa: E402

FAKE = '''import argparse, json, os, pathlib, socket, sys, time
ap = argparse.ArgumentParser()
for a in ("--host", "--port", "--root", "--entry", "--title", "--server", "--cwd", "--tls-cert", "--tls-key"):
    ap.add_argument(a)
a = ap.parse_args()
pathlib.Path(a.root, "gate.argv").write_text(json.dumps({"argv": sys.argv[1:], "token": os.environ.get("AIMEM_DEPLOY_TOKEN"),
                                                         "env": sorted(os.environ)}))
s = socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind((a.host, int(a.port))); s.listen(5)
while True:
    c, _ = s.accept(); c.close()
'''


def free_base():
    """배포 포트 20개와 안쪽 포트가 운영 것과 겹치지 않을 빈 구간의 첫 포트."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        p = s.getsockname()[1]
    return 20000 + (p % 20000)


class DeployTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        (self.root / ".aimem" / "tls").mkdir(parents=True)
        (self.root / ".aimem" / "tls" / "server.crt").write_text("crt")
        (self.root / ".aimem" / "tls" / "server.key").write_text("key")
        self.host = self.root / "host"
        self.host.mkdir()
        self.app = self.root / "projects" / "앱"
        self.app.mkdir(parents=True)
        (self.app / "web").mkdir()
        self.script = self.app / "serve.py"
        self.script.write_text("")
        self.gate = self.root / "gate.py"
        self.gate.write_text(FAKE)
        self.target = self.make_target(self.app)
        self.base = free_base()
        self.dep = deploy.Deploys(self.root, proxy_config=self.host / "ports.json", start_timeout=8, port_first=self.base,
                                  gate=self.gate)
        self.addCleanup(self.stop_all)

    def stop_all(self):
        for name in list(self.dep.status()):
            self.dep.off(name)

    def ports(self):
        return json.loads((self.host / "ports.json").read_text())["ports"]

    @staticmethod
    def make_target(app, server=True):
        return {"root": app / "web", "entry": "index.html", "cwd": app, "title": app.name,
                "server": app / "serve.py" if server else None}

    def seen(self, app=None):
        return json.loads(((app or self.app) / "web" / "gate.argv").read_text())

    def test_on_off_keeps_port_and_token(self):
        out = self.dep.on("앱", self.target)
        self.assertEqual((out["port"], out["on"], out["alive"], out["auth"], out["proxy"]), (self.base, True, True, True, True))
        self.assertGreaterEqual(len(out["token"]), 24)
        self.assertEqual(self.ports(), [self.base])
        seen = self.seen()
        self.assertEqual(seen["argv"], ["--host", "127.0.0.1", "--port", str(self.base + 100),
                                        "--root", str(self.app / "web"), "--entry", "index.html", "--title", "앱",
                                        "--tls-cert", str(self.root / ".aimem/tls/server.crt"),
                                        "--tls-key", str(self.root / ".aimem/tls/server.key"),
                                        "--server", str(self.script), "--cwd", str(self.app)])
        self.assertEqual(seen["token"], out["token"])                                             # 토큰은 환경으로만
        self.assertNotIn(out["token"], " ".join(seen["argv"]))
        self.assertLessEqual(set(seen["env"]), {"PATH", "HOME", "LANG", "LC_ALL", "TZ", "AIMEM_DEPLOY_TOKEN", "LC_CTYPE"})
        rec = json.loads(self.dep.file.read_text())["apps"]["앱"]
        self.assertEqual(stat.S_IMODE(self.dep.file.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.dep.dir.stat().st_mode), 0o700)
        self.assertEqual(self.dep.on("앱", self.target)["token"], out["token"])       # 다시 켜도 그대로
        self.assertEqual(json.loads(self.dep.file.read_text())["apps"]["앱"]["pid"], rec["pid"])
        self.assertNotIn("token", self.dep.status()["앱"])                                       # 상태에는 토큰이 없다
        off = self.dep.off("앱")
        self.assertEqual((off["on"], off["alive"], off["port"]), (False, False, self.base))
        self.assertEqual(self.ports(), [])
        self.assertIsNone(deploy._proc_start(rec["pid"]) and None)
        time.sleep(0.2)
        self.assertFalse(deploy._port_open(self.base + 100, 0.2))
        again = self.dep.on("앱", self.target)
        self.assertEqual((again["port"], again["token"]), (self.base, out["token"]))

    def test_without_token_and_switching_restarts(self):
        out = self.dep.on("앱", self.target, auth=False)
        self.assertEqual((out["auth"], out["token"]), (False, None))
        self.assertIsNone(self.seen()["token"])
        self.assertIsNone(self.dep.token("앱"))
        pid = json.loads(self.dep.file.read_text())["apps"]["앱"]["pid"]
        self.assertEqual(self.dep.on("앱", self.target)["auth"], False)                # 안 주면 지난번대로
        self.assertEqual(json.loads(self.dep.file.read_text())["apps"]["앱"]["pid"], pid)
        out = self.dep.on("앱", self.target, auth=True)
        self.assertTrue(out["token"])
        self.assertEqual(self.seen()["token"], out["token"])
        self.assertNotEqual(json.loads(self.dep.file.read_text())["apps"]["앱"]["pid"], pid)

    def test_static_only_app_and_changed_declaration_restarts(self):
        out = self.dep.on("앱", self.make_target(self.app, server=False), auth=False)           # 서버가 없는 앱도 배포된다
        self.assertTrue(out["alive"])
        self.assertNotIn("--server", self.seen()["argv"])
        pid = json.loads(self.dep.file.read_text())["apps"]["앱"]["pid"]
        self.dep.on("앱", self.target)                                                           # 선언에 server 가 생겼다
        self.assertIn("--server", self.seen()["argv"])
        self.assertNotEqual(json.loads(self.dep.file.read_text())["apps"]["앱"]["pid"], pid)

    def test_second_app_next_port_and_forget(self):
        other = self.root / "projects" / "둘"
        other.mkdir()
        (other / "web").mkdir()
        a = self.dep.on("앱", self.target)
        b = self.dep.on("둘", self.make_target(other, server=False))
        self.assertEqual((a["port"], b["port"]), (self.base, self.base + 1))
        self.assertNotEqual(a["token"], b["token"])
        self.assertEqual(self.ports(), [self.base, self.base + 1])
        self.dep.off("앱", forget=True)
        self.assertEqual(list(self.dep.status()), ["둘"])
        self.assertEqual(self.ports(), [self.base + 1])
        self.assertIsNone(self.dep.off("없는것"))

    def test_refusals(self):
        bad = self.root / "bad.py"
        bad.write_text("import sys; sys.exit(2)")
        dying = deploy.Deploys(self.root, proxy_config=self.host / "ports.json", port_first=self.base, gate=bad)
        with self.assertRaises(deploy.DeployError) as cm:
            dying.on("앱", self.target)
        self.assertEqual(cm.exception.status, 502)
        self.assertFalse(self.dep.status()["앱"]["on"])
        (self.root / ".aimem/tls/server.key").unlink()
        with self.assertRaises(deploy.DeployError) as cm:
            self.dep.on("앱", self.target)
        self.assertEqual(cm.exception.status, 409)
        with self.assertRaises(deploy.DeployError):
            self.dep.on("../x", self.target)

    def test_proxy_folder_missing_is_reported_not_fatal(self):
        dep = deploy.Deploys(self.root, proxy_config=self.root / "nope" / "ports.json", port_first=self.base, gate=self.gate)
        out = dep.on("앱", self.target)
        self.assertEqual((out["alive"], out["proxy"]), (True, False))
        self.assertIn("프록시", out["proxy_note"])

    def test_ensure_all_restarts_dead_ones(self):
        self.dep.on("앱", self.target)
        rec = json.loads(self.dep.file.read_text())["apps"]["앱"]
        os.killpg(rec["pid"], 9)
        for _ in range(50):
            if not self.dep.status()["앱"]["alive"]:
                break
            time.sleep(0.1)
        self.assertEqual(self.dep.status()["앱"], {"name": "앱", "port": self.base, "on": True, "alive": False,
                                                    "auth": True, "started": None})
        self.assertEqual(self.dep.ensure_all(lambda n: None), [("앱", mock.ANY)])
        self.assertEqual(self.dep.ensure_all(lambda n: self.target), [("앱", "started")])
        self.assertTrue(self.dep.status()["앱"]["alive"])
        self.assertEqual(self.dep.ensure_all(lambda n: self.target), [])


class DeployRouteTest(unittest.TestCase):
    def test_route_and_validation(self):
        self.assertTrue(server._REQ_PROJECT_DEPLOY_RE.match("/api/projects/VoxLog/deploy"))
        self.assertFalse(server._REQ_PROJECT_DEPLOY_RE.match("/api/projects/a/b/deploy"))
        with tempfile.TemporaryDirectory() as t:
            root = pathlib.Path(t)
            self.assertEqual(server.project_deploy_action("앱", {"action": "on"}, root)[0], 403)      # 운영 저장소가 아니다
            self.assertEqual(server.deploy_states(root), {})
            with mock.patch.object(server, "ROOT", root.resolve()):
                for bad in (["x"], {}, {"action": "run"}, {"action": "on", "auth": "no"}):
                    self.assertEqual(server.project_deploy_action("앱", bad, root)[0], 400, bad)
                self.assertEqual(server.project_deploy_action("../x", {"action": "on"}, root)[0], 400)
                code, out = server.project_deploy_action("앱", {"action": "on"}, root)                # app.json 없음
                self.assertEqual(code, 409, out)
                web = root / "projects" / "앱" / "web"                                                # 서버 없는 선언도 배포 대상이다
                web.mkdir(parents=True)
                (web / "index.html").write_text("<p>hi</p>")
                (root / "projects" / "앱" / "app.json").write_text("{}")
                target, why = server._deploy_target("앱", root)
                self.assertIsNone(why)
                self.assertEqual((target["root"], target["entry"], target["server"]), (web, "index.html", None))
                self.assertEqual(server.project_deploy_action("앱", {"action": "off"}, root)[0], 404)
                self.assertEqual(server.project_deploy_action("앱", {"action": "token"}, root)[0], 404)


if __name__ == "__main__":
    unittest.main()
