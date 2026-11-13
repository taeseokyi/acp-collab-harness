"""검증 명령의 울타리 (`fleet_rt.sandbox`, `fleet_graph._verify`).

그래프 JSON 은 작업자가 쓸 수 있다 - 실행기가 `verify` 를 제 권한·환경으로 돌리면 작업자가 엔진을 거쳐 제 울타리 밖에
쓰거나 키를 읽는다. 여기서는 **진짜 bwrap** 으로 돌려 본다(이 기계에서 안 돌면 그 검사만 건너뛴다).
저장소 루트는 /tmp 아래 임시 폴더다 - 루트 자체가 /tmp 아래여도 울타리가 맞게 묶이는지도 같이 본다.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _fleet_env  # noqa: F401,E402

import pathlib
import shutil
import tempfile
import time
import unittest
from unittest import mock

import fleet_graph  # noqa: E402
from fleet_rt import sandbox  # noqa: E402

HAVE_BWRAP = sandbox.available()[0]


def _procs_with(token):
    """명령줄에 `token` 이 든 살아 있는 프로세스 pid 들 (좀비 제외)."""
    out = []
    for p in os.listdir("/proc"):
        if not p.isdigit():
            continue
        try:
            cmd = pathlib.Path(f"/proc/{p}/cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", "replace")
            stat = pathlib.Path(f"/proc/{p}/stat").read_text()
        except OSError:
            continue
        if token in cmd and stat.rpartition(")")[2].split()[0] != "Z":
            out.append(int(p))
    return out


class Base(unittest.TestCase):
    def setUp(self):
        self.root = pathlib.Path(tempfile.mkdtemp(prefix="rt-sandbox-")).resolve()
        self.addCleanup(shutil.rmtree, self.root, True)
        (self.root / ".aimem" / "graph").mkdir(parents=True)
        for p in (mock.patch.object(fleet_graph, "ROOT", self.root),
                  mock.patch.object(fleet_graph, "GRAPHS", self.root / ".aimem" / "graph"),
                  mock.patch.object(fleet_graph, "_LOGGED_ONCE", set())):
            p.start()
            self.addCleanup(p.stop)

    def verify(self, cmd):
        return fleet_graph._verify({"id": "T-1", "verify": cmd})


class CleanEnv(unittest.TestCase):
    def test_keys_markers_and_env_file_names_are_dropped(self):
        root = pathlib.Path(tempfile.mkdtemp(prefix="rt-sandbox-env-"))
        self.addCleanup(shutil.rmtree, root, True)
        (root / ".env").write_text("PLAIN_NAME=v1\nexport OTHER=v2\n", encoding="utf-8")
        os.chmod(root / ".env", 0o600)
        env = sandbox.clean_env({"PATH": "/usr/bin", "HOME": "/h", "LANG": "C.UTF-8", "PLAIN_NAME": "x", "OTHER": "y",
                                 "FK_API_KEY": "k", "GH_TOKEN": "t", "app_secret": "s", "AIFLEET_SESSION": "S",
                                 "AIFLEET_ROLE": "worker", "AIFLEET_SESSIONS_ROOT": "/r", "TOKENIZERS_PARALLELISM": "1"},
                                root)
        self.assertEqual(env, {"PATH": "/usr/bin", "HOME": "/h", "LANG": "C.UTF-8", "TOKENIZERS_PARALLELISM": "1"})

    def test_without_bwrap_the_command_line_is_unchanged_and_says_so(self):
        with mock.patch.object(sandbox, "available", return_value=(False, "bwrap 이 없습니다")):
            argv, note = sandbox.wrap(["bash", "-c", "true"], "/x")
        self.assertEqual(argv, ["bash", "-c", "true"])
        self.assertIn("울타리 없이", note)


class Unconfined(Base):
    """bwrap 이 없는 기계: 검증은 그대로 돌고(환경은 씻김), 그래프마다 한 번 로그에 남긴다."""

    def test_verify_still_runs_with_a_clean_env_and_the_runner_logs_once(self):
        with mock.patch.object(sandbox, "available", return_value=(False, "bwrap 이 없습니다")), \
                mock.patch.dict(os.environ, {"FK_API_KEY": "sekrit-1"}):
            rc, tail = self.verify('echo "k=${FK_API_KEY:-none}"; touch made.txt')
            self.assertEqual(rc, 0, tail)
            self.assertIn("k=none", tail)
            self.assertTrue((self.root / "made.txt").exists())
            g = {"id": "G-1", "nodes": []}
            fleet_graph._note_unconfined(g)
            fleet_graph._note_unconfined(g)
        log = (self.root / ".aimem" / "graph" / "G-1.log").read_text(encoding="utf-8")
        self.assertEqual(log.count("울타리 없이"), 1)

    def test_with_bwrap_nothing_is_logged(self):
        with mock.patch.object(sandbox, "available", return_value=(True, "")):
            fleet_graph._note_unconfined({"id": "G-2", "nodes": []})
        self.assertFalse((self.root / ".aimem" / "graph" / "G-2.log").exists())


@unittest.skipUnless(HAVE_BWRAP, "이 기계에서 bwrap 이 돌지 않는다")
class Confined(Base):
    def test_the_command_line(self):
        (self.root / ".env").write_text("X=1\n", encoding="utf-8")
        (self.root / ".aimem" / "tls").mkdir()
        argv, note = sandbox.wrap(["bash", "-c", "true"], self.root)
        self.assertEqual(note, "")
        r = str(self.root)
        joined = " ".join(argv)
        for part in ("--ro-bind / /", "--bind /tmp /tmp", f"--bind {r} {r}", f"--ro-bind /dev/null {r}/.env",
                     f"--tmpfs {r}/.aimem/tls", f"--chdir {r}", "--unshare-pid", "--new-session", "--die-with-parent"):
            self.assertIn(part, joined)
        # 가리기는 저장소 쓰기 묶기 뒤 (앞이면 다시 보인다)
        self.assertLess(joined.index(f"--bind {r} {r}"), joined.index(f"/dev/null {r}/.env"))
        self.assertEqual(argv[-3:], ["bash", "-c", "true"])

    def test_writes_inside_the_repo_and_tmp_work(self):
        tmpf = pathlib.Path(tempfile.gettempdir()) / f"rt-sandbox-{os.getpid()}-{time.time_ns()}.txt"
        self.addCleanup(lambda: tmpf.unlink() if tmpf.exists() else None)
        rc, tail = self.verify(f"pwd; mkdir -p sub && echo hi > sub/a.txt && echo t > {tmpf} && cat {tmpf}")
        self.assertEqual(rc, 0, tail)
        self.assertIn(str(self.root), tail)                     # 작업 폴더는 저장소
        self.assertEqual((self.root / "sub" / "a.txt").read_text(), "hi\n")
        self.assertEqual(tmpf.read_text(), "t\n")              # 진짜 /tmp - 작업자가 남긴 것을 검증이 읽을 수 있다

    def test_writes_outside_the_repo_and_tmp_fail_and_create_nothing(self):
        home = pathlib.Path(os.path.expanduser("~")) / f".rt-sandbox-{os.getpid()}-{time.time_ns()}"
        self.addCleanup(lambda: home.unlink() if home.exists() else None)
        rc, tail = self.verify(f"touch {home} || echo HOME-REFUSED; touch /etc/rt-sandbox-x || echo ETC-REFUSED; true")
        self.assertIn("HOME-REFUSED", tail)
        self.assertIn("ETC-REFUSED", tail)
        self.assertFalse(home.exists())
        self.assertFalse(pathlib.Path("/etc/rt-sandbox-x").exists())

    def test_git_dir_is_read_only(self):
        (self.root / ".git").mkdir()
        rc, _ = self.verify("touch .git/hooks-x")
        self.assertNotEqual(rc, 0)
        self.assertFalse((self.root / ".git" / "hooks-x").exists())

    def test_env_file_and_tls_dir_are_hidden_and_keys_are_not_passed(self):
        (self.root / ".env").write_text("FK_API_KEY=from-file-123\nPLAIN_NAME=plain-456\n", encoding="utf-8")
        os.chmod(self.root / ".env", 0o600)
        (self.root / ".aimem" / "tls").mkdir()
        (self.root / ".aimem" / "tls" / "access-token").write_text("tls-token-789", encoding="utf-8")
        with mock.patch.dict(os.environ, {"FK_API_KEY": "env-key-000", "PLAIN_NAME": "plain-env-111",
                                          "AIFLEET_SESSION": "sess-x-333", "SOME_TOKEN": "tok-222"}):
            rc, tail = self.verify(
                "cat .env; cat .aimem/tls/access-token; echo TLS=$(ls -A .aimem/tls | wc -l); "
                "echo LEAK=$(env | grep -c -e env-key-000 -e plain-env-111 -e sess-x-333 -e tok-222); "
                'echo "K=${FK_API_KEY-unset} P=${PLAIN_NAME-unset} A=${AIFLEET_SESSION-unset}"; echo PATH=$PATH')
        self.assertEqual(rc, 0, tail)
        self.assertIn("TLS=0", tail)
        self.assertIn("LEAK=0", tail)
        self.assertIn("K=unset P=unset A=unset", tail)
        for secret in ("from-file-123", "plain-456", "tls-token-789"):
            self.assertNotIn(secret, tail)
        self.assertIn("PATH=", tail)
        self.assertEqual((self.root / ".env").read_text(encoding="utf-8")[:10], "FK_API_KEY")   # 밖에서는 그대로

    def test_a_verify_cannot_see_or_signal_fleet_processes(self):
        rc, tail = self.verify(f"kill -0 {os.getpid()} 2>/dev/null && echo REACHED; ls /proc | grep -c '^[0-9]'")
        self.assertNotIn("REACHED", tail)
        self.assertLess(int(tail.strip().splitlines()[-1]), 10)   # 새 pid 이름공간 - 안의 몇 개만 보인다

    def test_timeout_kills_everything_inside(self):
        token = f"317.{os.getpid()}{time.time_ns() % 100000}"
        with mock.patch.object(fleet_graph, "VERIFY_TIMEOUT_SEC", 1):
            t = time.time()
            rc, tail = self.verify(f"sleep {token} & setsid sleep {token} & sleep {token}")
        self.assertEqual(rc, 124)
        self.assertIn("타임아웃", tail)
        self.assertLess(time.time() - t, 15)
        deadline = time.time() + 5
        while _procs_with(token) and time.time() < deadline:
            time.sleep(0.05)
        self.assertEqual(_procs_with(token), [])

    def test_python_imports_and_writes_pycache_inside_the_repo(self):
        (self.root / "tools").mkdir()
        (self.root / "tools" / "modx.py").write_text("V = 7\n", encoding="utf-8")
        (self.root / "tests").mkdir()
        (self.root / "tests" / "test_x.py").write_text(
            "import sys, unittest\nsys.path.insert(0, 'tools')\nimport modx\n"
            "class T(unittest.TestCase):\n    def test_v(self):\n        self.assertEqual(modx.V, 7)\n", encoding="utf-8")
        rc, tail = self.verify("python3 -m unittest discover -s tests -p 'test_x.py'")
        self.assertEqual(rc, 0, tail)
        self.assertIn("OK", tail)
        self.assertTrue(list((self.root / "tools" / "__pycache__").glob("modx.*.pyc")))


if __name__ == "__main__":
    unittest.main()
