"""fleet_rt 세션 감독 검사 (sessions.py · run.py · harness/fake.py).

진짜 하네스는 띄우지 않는다(`_fleet_env` 가 AIFLEET_HARNESS=fake). 세션 저장소는 모두 임시 폴더이고,
신호는 이 검사가 띄운 프로세스에만 보낸다. 마지막에 이 검사의 저장소 표식을 단 프로세스가 하나도
남지 않았는지 본다.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # `python3 -m unittest tests/<이 파일>` 로도 돌게
import _fleet_env  # noqa: F401,E402

import json
import os
import pathlib
import shutil
import signal
import sqlite3
import subprocess
import tempfile
import time
import unittest
from unittest import mock

from fleet_rt import sessions
from fleet_rt.base import ENV_ROOT, ENV_SESSION, SESSION_COLUMNS, SessionSpec

BASE = None          # 이 모듈의 임시 폴더. 모든 세션 저장소가 이 아래에 있다
_N = [0]


def setUpModule():
    global BASE
    BASE = pathlib.Path(tempfile.mkdtemp(prefix="rt-sessions-"))


def _ours():
    """이 모듈의 임시 저장소 표식(ENV_ROOT 가 BASE 아래)을 단, 좀비 아닌 프로세스."""
    out = []
    for p in sessions._live_pids():
        env = sessions._proc_environ(p)
        if env and str(env.get(ENV_ROOT, "")).startswith(str(BASE) + os.sep) \
                and sessions._proc_state(p) not in (None, "Z"):
            out.append(p)
    return out


def tearDownModule():
    left = _ours()
    # 남은 것이 있으면 검사 실패로 알리되, 이 검사가 띄운 것(표식이 이 임시 저장소)이므로 치우고 끝낸다.
    for p in left:
        try:
            os.kill(p, signal.SIGKILL)
        except OSError:
            pass
    shutil.rmtree(BASE, ignore_errors=True)
    if left:
        raise AssertionError(f"검사 뒤 남은 프로세스: {left}")


def _clean_env(**extra):
    """이 검사 프로세스의 환경에서 함대 표식을 뺀 것 + extra. 검사가 함대 세션 안에서 돌더라도 섞이지 않게."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("AIFLEET_") or k == "AIFLEET_HARNESS"}
    env.update(extra)
    return env


def _gone(pid):
    return sessions._proc_state(pid) in (None, "Z")


def _wait(pred, timeout=10.0, step=0.05):
    deadline = time.time() + timeout
    while time.time() < deadline:
        v = pred()
        if v:
            return v
        time.sleep(step)
    return pred()


class Base(unittest.TestCase):
    def setUp(self):
        _N[0] += 1
        self.root = BASE / f"root{_N[0]}"
        self.work = BASE / f"work{_N[0]}"
        self.work.mkdir()
        self.db = BASE / f"db{_N[0]}.sqlite"

    def spawn(self, directives, sid=None, root=None, **kw):
        _N[0] += 1
        sid = f"s{_N[0]}" if sid is None else sid
        spec = SessionSpec(id=sid, role="worker", harness="fake", brief_path="", cwd=str(self.work),
                           write_paths=["out.txt"], **kw)
        brief = "SLOT=S9 검사\n" + "".join(f"FAKE: {d}\n" for d in directives)
        return sessions.spawn(spec, brief, root or self.root, db_path=self.db)

    def wait_end(self, d, timeout=10.0):
        st = _wait(lambda: sessions.state(d)["state"] != "running" and sessions.state(d), timeout)
        self.assertTrue(st, f"{d.name} 가 {timeout}초 안에 안 끝남")
        return st

    def wait_event(self, d, pred, timeout=10.0):
        return _wait(lambda: next((ev for _at, ev in sessions.tail(d, 50) if pred(ev)), None), timeout)

    def group_of(self, d):
        return sessions.group_members(sessions.load_meta(d)["pgid"])


class TestRun(Base):
    def test_success(self):
        envroot = BASE / f"envroot{_N[0]}"
        envroot.mkdir()
        # `.env` 에서는 그 세션 공급자의 키 하나만 넘어간다 - 나머지(다른 키·실행을 바꾸는 변수)는 넘어가지 않는다
        (envroot / ".env").write_text("FAKE_SECRET_API_KEY=sekrit-value\nOTHER_API_KEY=other-value\n"
                                      "BASH_ENV=/tmp/x\nFAKE_STEER_URL=http://evil\n", encoding="utf-8")
        os.chmod(envroot / ".env", 0o600)
        (envroot / "fleet.toml").write_text('[providers.fk]\nenv_key = "FAKE_SECRET_API_KEY"\nmodels = ["x"]\n'
                                            '[providers.other]\nenv_key = "OTHER_API_KEY"\nmodels = ["y"]\n', encoding="utf-8")
        spec = SessionSpec(id="ok-1", role="reviewer", harness="fake", brief_path="", cwd=str(self.work),
                           write_paths=["out.txt"], task_id="T-1", label="성공", provider="fk")
        brief = "\n".join(["FAKE: emit 안녕", "FAKE: tool Bash ls tools", "FAKE: env AIFLEET_SESSION",
                           "FAKE: env AIFLEET_ROLE", "FAKE: env AIFLEET_SESSIONS_ROOT", "FAKE: env FAKE_SECRET_API_KEY",
                           "FAKE: env OTHER_API_KEY", "FAKE: env BASH_ENV", "FAKE: env FAKE_STEER_URL",
                           "FAKE: write out.txt 결과", "FAKE: usage 10 5 0.25", "FAKE: usage 1 2",
                           "FAKE: stderr 경고 한 줄", "FAKE: report DONE\\n다 했다"])
        with mock.patch.dict(os.environ):
            for k in ("FAKE_SECRET_API_KEY", "OTHER_API_KEY", "BASH_ENV", "FAKE_STEER_URL"):
                os.environ.pop(k, None)
            d = sessions.spawn(spec, brief, self.root, db_path=self.db, env_root=envroot)
        self.assertEqual(sessions.state(d)["state"], "running")
        st = self.wait_end(d)
        self.assertEqual((st["state"], st["rc"], st["fail_kind"]), ("done", 0, None))
        end = json.loads((d / "end.json").read_text(encoding="utf-8"))
        self.assertEqual(set(end), {"state", "rc", "ended", "fail_kind", "why"})
        self.assertEqual(sessions.report(d), "DONE\n다 했다")
        self.assertEqual((self.work / "out.txt").read_text(encoding="utf-8"), "결과")
        self.assertIn("경고 한 줄", (d / "stderr.log").read_text(encoding="utf-8"))
        for ln in (d / "events.jsonl").read_text(encoding="utf-8").splitlines():
            self.assertRegex(ln, r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}\t\{")
        texts = [ev.text for _at, ev in sessions.tail(d, 50) if ev.kind == "text"]
        self.assertIn("AIFLEET_SESSION=ok-1", texts)
        self.assertIn("AIFLEET_ROLE=reviewer", texts)
        self.assertIn(f"AIFLEET_SESSIONS_ROOT={os.path.abspath(self.root)}", texts)
        self.assertIn("FAKE_SECRET_API_KEY=sekrit-value", texts)      # 공급자 키는 하네스에 닿는다
        for name in ("OTHER_API_KEY", "BASH_ENV", "FAKE_STEER_URL"):   # 나머지 `.env` 줄은 닿지 않는다
            self.assertIn(f"{name}=", texts)
        meta_text = (d / "meta.json").read_text(encoding="utf-8")
        self.assertNotIn("sekrit-value", meta_text)                     # 값은 meta 에 안 적힌다
        meta = json.loads(meta_text)
        self.assertEqual(meta["env_file_names"], ["FAKE_SECRET_API_KEY"])   # 넘긴 이름은 보인다
        self.assertEqual(meta["pgid"], meta["supervisor_pid"])
        self.assertIsInstance(meta["proc_start"], int)
        self.assertEqual(meta["brief_path"], str(d / "brief.md"))
        self.assertEqual(sessions.last_event_at(d), st["last_event_at"])
        self.assertTrue(_wait(lambda: _gone(meta["supervisor_pid"]), 5))
        # DB 색인
        row = sqlite3.connect(self.db).execute(
            f"SELECT {', '.join(SESSION_COLUMNS)} FROM sessions WHERE id='ok-1'").fetchone()
        row = dict(zip(SESSION_COLUMNS, row))
        self.assertEqual((row["state"], row["rc"], row["report_status"]), ("done", 0, "DONE"))
        self.assertEqual((row["tokens_in"], row["tokens_out"], row["cost_usd"]), (11, 7, 0.25))
        self.assertEqual(row["harness_session_id"], "fake-ok-1")
        self.assertEqual(json.loads(row["write_paths"]), ["out.txt"])
        self.assertEqual(sessions.list_ids(self.root), ["ok-1"])

    def test_failed_rc(self):
        d = self.spawn(["emit 하다 말았다", "exit 3"])
        st = self.wait_end(d)
        self.assertEqual((st["state"], st["rc"], st["fail_kind"]), ("failed", 3, None))

    def test_failed_limit(self):
        st = self.wait_end(self.spawn(["limit"]))
        self.assertEqual((st["state"], st["fail_kind"]), ("failed", "limit"))

    def test_failed_infra(self):
        st = self.wait_end(self.spawn(["error Provider response headers timed out", "exit 1"]))
        self.assertEqual((st["state"], st["fail_kind"]), ("failed", "infra"))

    def test_stalled(self):
        d = self.spawn(["hang"], idle_timeout=1.0)
        t = time.time()
        st = self.wait_end(d)
        self.assertEqual((st["state"], st["fail_kind"]), ("stalled", "infra"))
        self.assertLess(time.time() - t, 6)
        self.assertTrue(_wait(lambda: not self.group_of(d), 3))     # 감독은 end.json 뒤 DB 를 적고 끝난다

    def test_reading_without_events_is_not_silence(self):
        """사건은 없어도 데이터를 계속 읽는 하네스(긴 생성 중)는 침묵으로 끊지 않는다 - 읽기가 멈추면 끊는다."""
        d = self.spawn(["busy-read 5", "emit 끝"], idle_timeout=2.5)
        st = self.wait_end(d, 20)
        self.assertEqual(st["state"], "done", st)
        d2 = self.spawn(["hang"], idle_timeout=2.5)
        st2 = self.wait_end(d2, 20)
        self.assertEqual((st2["state"], st2["fail_kind"]), ("stalled", "infra"))
        self.assertIn("읽기도 없음", st2["why"])
        self.assertTrue(_wait(lambda: not self.group_of(d) and not self.group_of(d2), 5))   # 감독이 DB 를 적고 끝날 때까지

    def test_reading_by_a_detached_child_is_not_silence(self):
        """하네스가 그룹을 벗어난(setsid) 백그라운드 명령을 기다리는 동안도, 그 명령이 읽고 있으면 침묵이 아니다."""
        d = self.spawn(["detached-busy 5", "emit 끝"], idle_timeout=2.5)
        st = self.wait_end(d, 20)
        self.assertEqual(st["state"], "done", st)
        self.assertTrue(_wait(lambda: not self.group_of(d), 5))

    def test_timeout(self):
        d = self.spawn(["emit 시작", "sleep 30"], timeout=1.5)
        st = self.wait_end(d)
        self.assertEqual((st["state"], st["fail_kind"]), ("timeout", "timeout"))
        self.assertTrue(_wait(lambda: not self.group_of(d), 3))     # 감독은 end.json 뒤 DB 를 적고 끝난다

    def test_grandchild_cleaned_on_normal_exit(self):
        d = self.spawn(["child 60", "emit 끝"])
        self.assertEqual(self.wait_end(d)["state"], "done")
        ev = self.wait_event(d, lambda e: e.kind == "tool" and e.data.get("name") == "child")
        self.assertTrue(_wait(lambda: _gone(ev.data["pid"]), 3))


class TestCancel(Base):
    def test_cancel_running_with_child(self):
        d = self.spawn(["child 60", "hang"])
        ev = self.wait_event(d, lambda e: e.kind == "text" and e.text == "hang")
        self.assertIsNotNone(ev)
        meta = sessions.load_meta(d)
        members = self.group_of(d)
        self.assertGreaterEqual(len(members), 3)            # 감독 + 하네스 + 손자
        self.assertEqual(sessions.cancel(d, why="검사 취소"), "killed")
        self.assertTrue(all(_gone(p) for p in members), members)
        self.assertFalse(sessions._pgroup_alive(meta["pgid"]))
        st = sessions.state(d)
        self.assertEqual((st["state"], st["why"]), ("killed", "검사 취소"))
        self.assertTrue((d / "cancel.json").exists())

    def test_cancel_ignore_term(self):
        d = self.spawn(["ignore-term", "hang"])
        self.assertIsNotNone(self.wait_event(d, lambda e: e.kind == "text" and e.text == "hang"))
        members = self.group_of(d)
        t = time.time()
        self.assertEqual(sessions.cancel(d, why="안 죽는 하네스"), "killed")
        self.assertGreater(time.time() - t, 2.0)            # TERM 이 안 먹어 KILL 길을 탔다
        self.assertTrue(all(_gone(p) for p in members), members)
        self.assertEqual(sessions.state(d)["state"], "killed")

    def test_cancel_finished_is_gone(self):
        d = self.spawn(["emit 끝"])
        self.wait_end(d)
        self.assertTrue(_wait(lambda: _gone(sessions.load_meta(d)["supervisor_pid"]), 5))
        self.assertEqual(sessions.cancel(d), "gone")
        self.assertEqual(sessions.state(d)["state"], "done")       # 끝난 기록은 그대로

    def test_supervisor_killed_harness_alive_is_running_orphaned(self):
        """검수 #3: 감독만 SIGKILL 되고 하네스가 살아 있으면 lost 가 아니라 running(orphaned) - 슬롯을 비우면
        같은 소유 경로에 둘째 작업자가 뜬다. 고아 청소로 하네스를 끝내야 비로소 lost."""
        d = self.spawn(["hang"])
        self.assertIsNotNone(self.wait_event(d, lambda e: e.kind == "text" and e.text == "hang"))
        meta = sessions.load_meta(d)
        harness_pids = [p for p in self.group_of(d) if p != meta["supervisor_pid"]]
        self.assertTrue(harness_pids)
        os.kill(meta["supervisor_pid"], signal.SIGKILL)     # 이 검사가 띄운 감독에만
        self.assertTrue(_wait(lambda: _gone(meta["supervisor_pid"]), 5))
        for _ in range(3):                                  # 캐시가 있든 없든 같은 답
            st = sessions.state(d)
            self.assertEqual((st["state"], st["orphaned"]), ("running", True), st)
            self.assertIn("감독 없이", st["why"])
            time.sleep(0.4)
        orphans = sessions.find_orphans(self.root)
        self.assertEqual(sorted(o["pid"] for o in orphans), sorted(harness_pids))
        reaped = sessions.reap_orphans(self.root, kill=True)
        self.assertTrue(all(o["killed"] for o in reaped))
        self.assertTrue(_wait(lambda: all(_gone(p) for p in harness_pids), 5))
        self.assertEqual(sessions.find_orphans(self.root), [])
        self.assertEqual(sessions.state(d)["state"], "lost")

    def test_cancel_lost_session_frees_slot(self):
        d = self.spawn(["hang"])
        self.assertIsNotNone(self.wait_event(d, lambda e: e.kind == "text" and e.text == "hang"))
        meta = sessions.load_meta(d)
        harness_pids = [p for p in self.group_of(d) if p != meta["supervisor_pid"]]
        os.kill(meta["supervisor_pid"], signal.SIGKILL)
        self.assertTrue(_wait(lambda: _gone(meta["supervisor_pid"]), 5))
        self.assertTrue(sessions.state(d)["orphaned"])
        self.assertEqual(sessions.cancel(d, why="정리"), "killed")      # 남은 하네스를 표식으로 찾아 끝냄
        self.assertTrue(_wait(lambda: all(_gone(p) for p in harness_pids), 5))
        st = sessions.state(d)
        self.assertEqual(st["state"], "killed")
        self.assertIn("감독 프로세스가 이미 없음", st["why"])


class TestRefusals(Base):
    def _fake_session(self, sid, **meta):
        d = self.root / sid
        d.mkdir(parents=True)
        m = {"id": sid, "role": "worker", "harness": "fake", "harness_effective": "fake",
             "sessions_root": str(self.root), "started": "2026-01-01T00:00:00"}
        m.update(meta)
        (d / "meta.json").write_text(json.dumps(m), encoding="utf-8")
        return d

    def _cancel_no_signal(self, d):
        with mock.patch("os.killpg") as kpg, mock.patch("os.kill") as k:
            out = sessions.cancel(d)
        kpg.assert_not_called()
        k.assert_not_called()
        return out

    def _sleeper(self, sid, new_session, root=None):
        """`sleep 30` 하나. 표식은 sid + root(기본은 어느 저장소도 아닌 곳)."""
        env = _clean_env(**{ENV_SESSION: sid, ENV_ROOT: os.path.abspath(root or (BASE / "nowhere"))})
        p = subprocess.Popen(["sleep", "30"], env=env, start_new_session=new_session,
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(lambda: (p.kill(), p.wait()))
        _wait(lambda: sessions._proc_environ(p.pid) and sessions._proc_environ(p.pid).get(ENV_SESSION) == sid, 3)
        return p

    def test_pid_one(self):
        d = self._fake_session("r-one", supervisor_pid=1, pgid=1, proc_start=1)
        self.assertEqual(self._cancel_no_signal(d), "refused")

    def test_own_pid(self):
        d = self._fake_session("r-own", supervisor_pid=os.getpid(), pgid=os.getpgid(0),
                               proc_start=sessions.proc_start(os.getpid()))
        self.assertEqual(self._cancel_no_signal(d), "refused")

    def test_bad_pid_types(self):
        for i, v in enumerate([None, "123", True, -5]):
            d = self._fake_session(f"r-type{i}", supervisor_pid=v)
            self.assertEqual(self._cancel_no_signal(d), "refused")

    def test_not_group_leader(self):
        p = self._sleeper("r-nolead", new_session=False, root=self.root)   # 표식은 맞고 리더만 아님
        d = self._fake_session("r-nolead", supervisor_pid=p.pid, pgid=p.pid, proc_start=sessions.proc_start(p.pid))
        self.assertEqual(self._cancel_no_signal(d), "refused")
        self.assertIn("세션 리더 아님", sessions.LAST_REFUSAL[str(d)])
        self.assertFalse(_gone(p.pid))

    def test_start_time_mismatch_is_foreign(self):
        p = self._sleeper("r-reuse", new_session=True)
        d = self._fake_session("r-reuse", supervisor_pid=p.pid, pgid=p.pid,
                               proc_start=sessions.proc_start(p.pid) + 1)
        self.assertEqual(self._cancel_no_signal(d), "foreign")
        self.assertFalse(_gone(p.pid))
        self.assertEqual(sessions.state(d)["state"], "lost")

    def test_other_session_marker_is_foreign(self):
        p = self._sleeper("someone-else", new_session=True)
        d = self._fake_session("r-env", supervisor_pid=p.pid, pgid=p.pid, proc_start=sessions.proc_start(p.pid))
        self.assertEqual(self._cancel_no_signal(d), "foreign")
        self.assertFalse(_gone(p.pid))

    def test_corrupt_meta(self):
        d = self.root / "r-corrupt"
        d.mkdir(parents=True)
        (d / "meta.json").write_text("{깨짐", encoding="utf-8")
        st = sessions.state(d)
        self.assertEqual(st["state"], "lost")
        self.assertTrue(st["why"])
        self.assertEqual(self._cancel_no_signal(d), "refused")
        (d / "meta.json").write_text("[1, 2]", encoding="utf-8")
        self.assertEqual(sessions.state(d)["state"], "lost")
        self.assertEqual(sessions.state(self.root / "없는-세션")["state"], "lost")
        self.assertEqual(sessions.tail(d, 5), [])
        self.assertEqual(sessions.report(d), "")
        self.assertEqual(sessions.index_row(d)["state"], "lost")


class TestSpawnAndOrphans(Base):
    def test_existing_id_refused(self):
        d = self.spawn(["emit a"], sid="dup")
        with self.assertRaises(FileExistsError):
            self.spawn(["emit b"], sid="dup")
        self.wait_end(d)
        self.assertEqual(sessions.report(d), "DONE\nfake 하네스")

    def test_bad_id_refused(self):
        for bad in ("../x", "a/b", "", ".hidden"):
            with self.assertRaises(ValueError):
                self.spawn(["emit a"], sid=bad)
        self.assertFalse(self.root.exists() and any(self.root.iterdir()))

    def test_adapter_value_error_leaves_nothing(self):
        spec = SessionSpec(id="bad-cwd", role="worker", harness="fake", brief_path="", cwd=str(BASE / "없는폴더"))
        with self.assertRaises(ValueError):
            sessions.spawn(spec, "FAKE: emit x\n", self.root)
        self.assertFalse((self.root / "bad-cwd").exists())

        class Boom:
            name = "boom"

            def command(self, spec):
                raise ValueError("저장소 밖")
        spec = SessionSpec(id="bad-adapter", role="worker", harness="fake", brief_path="", cwd=str(self.work))
        with mock.patch("fleet_rt.harness.get", return_value=Boom()):
            with self.assertRaises(ValueError):
                sessions.spawn(spec, "FAKE: emit x\n", self.root)
        self.assertFalse((self.root / "bad-adapter").exists())
        self.assertFalse([p for p in _ours()
                          if sessions._proc_environ(p).get(ENV_SESSION) in ("bad-cwd", "bad-adapter")])

    def test_orphans_by_root(self):
        """감독이 죽은 세션의 하네스·setsid 손자는 고아. 다른 저장소의 고아는 건드리지 않는다.
        (감독이 살아 있으면 setsid 손자도 감독이 끝낸다 - test_detached_grandchild_ended_by_supervisor)"""
        other = BASE / f"other{_N[0]}"
        d1 = self.spawn(["detach-child 60", "hang"], sid="orph-a")
        d2 = self.spawn(["detach-child 60", "hang"], sid="orph-b", root=other)
        evs = {}
        for d in (d1, d2):
            self.assertIsNotNone(self.wait_event(d, lambda e: e.kind == "text" and e.text == "hang"))
            evs[d] = self.wait_event(d, lambda e: e.kind == "tool" and e.data.get("name") == "detach-child")
            self.assertEqual(sessions.find_orphans(d.parent), [])      # 감독이 지키는 동안은 고아가 아니다
        c1, c2 = evs[d1].data["pid"], evs[d2].data["pid"]
        m1, m2 = sessions.load_meta(d1), sessions.load_meta(d2)
        h1 = [p for p in self.group_of(d1) if p != m1["supervisor_pid"]]
        for m in (m1, m2):
            os.kill(m["supervisor_pid"], signal.SIGKILL)            # 이 검사가 띄운 감독에만
            self.assertTrue(_wait(lambda: _gone(m["supervisor_pid"]), 5))
        want1 = sorted(h1 + [c1])
        self.assertEqual(sorted(o["pid"] for o in sessions.find_orphans(self.root)), want1)
        self.assertIn(c2, [o["pid"] for o in sessions.find_orphans(other)])
        self.assertEqual(sorted(o["pid"] for o in sessions.reap_orphans(self.root)), want1)   # kill=False: 보기만
        self.assertFalse(_gone(c1))
        with mock.patch("os.killpg") as kpg:
            reaped = sessions.reap_orphans(self.root, kill=True)
        kpg.assert_not_called()                              # 그룹 신호는 쓰지 않는다
        self.assertEqual(sorted((o["pid"], o["killed"]) for o in reaped), [(p, True) for p in want1])
        self.assertTrue(_wait(lambda: all(_gone(p) for p in want1), 5))
        self.assertFalse(_gone(c2))                          # 다른 저장소의 고아는 건드리지 않았다
        self.assertEqual(sessions.state(d2)["state"], "running")
        sessions.reap_orphans(other, kill=True)
        self.assertTrue(_wait(lambda: _gone(c2), 5))
        self.assertEqual(sessions.state(d1)["state"], "lost")

    def test_orphan_without_folder(self):
        env = _clean_env(**{ENV_SESSION: "no-such-session", ENV_ROOT: os.path.abspath(self.root)})
        self.root.mkdir(parents=True, exist_ok=True)
        p = subprocess.Popen(["sleep", "30"], env=env, start_new_session=True,
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(lambda: (p.kill(), p.wait()))
        _wait(lambda: sessions._proc_environ(p.pid) and ENV_SESSION in sessions._proc_environ(p.pid), 3)
        o = sessions.find_orphans(self.root)
        self.assertEqual([(x["pid"], x["why"]) for x in o], [(p.pid, "세션 폴더 없음")])
        sessions.reap_orphans(self.root, kill=True)
        self.assertEqual(p.wait(timeout=5), -signal.SIGTERM)


class TestReviewFindings(Base):
    """2026-11-12 적대 검수의 재현 각본(exp.py·exp2~4.py)을 회귀 검사로. 번호는 검수 결함 번호."""

    def wait_hang(self, d):
        self.assertIsNotNone(self.wait_event(d, lambda e: e.kind == "text" and e.text == "hang"))

    def session_pids(self, d):
        return list(sessions._session_remnants(d))

    # 1
    def test_cancel_on_copied_folder_leaves_original_alone(self):
        d = self.spawn(["hang"], sid="live1")
        self.wait_hang(d)
        pids = self.session_pids(d)
        self.assertGreaterEqual(len(pids), 2)                    # 감독 + 하네스
        copy_root = BASE / f"copy{_N[0]}" / "sessions"
        shutil.copytree(self.root, copy_root)
        cd = copy_root / "live1"
        st = sessions.state(cd)
        self.assertEqual((st["state"], st["orphaned"]), ("lost", False))     # 복사본은 아무것도 안 돈다
        with mock.patch("os.killpg") as kpg, mock.patch("os.kill") as k:
            self.assertEqual(sessions.cancel(cd, why="복사본에서"), "foreign")
        kpg.assert_not_called()
        k.assert_not_called()
        self.assertEqual(sessions.state(d)["state"], "running")
        self.assertTrue(all(not _gone(p) for p in pids))
        self.assertEqual(sessions.find_orphans(copy_root), [])
        self.assertEqual(sessions.cancel(d, why="원본"), "killed")
        self.assertTrue(_wait(lambda: all(_gone(p) for p in pids), 5))

    # 2
    def test_forged_meta_pointing_at_unrelated_leader_is_foreign(self):
        d = self.spawn(["emit 끝"], sid="victimsess")
        self.assertEqual(self.wait_end(d)["state"], "done")
        self.assertTrue(_wait(lambda: not self.session_pids(d), 5))
        os.unlink(d / "end.json")
        # 남의 그룹 리더 - 명령줄에 세션 폴더가 들어 있다 (터미널의 `tail -f .../events.jsonl`). 표식 없음.
        x = subprocess.Popen(["tail", "-f", str(d / "events.jsonl")], start_new_session=True, env=_clean_env(),
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(lambda: (x.kill(), x.wait()))
        self.assertTrue(_wait(lambda: str(d) in sessions._proc_cmdline(x.pid), 3))
        m = sessions.load_meta(d)
        m.update(supervisor_pid=x.pid, pgid=x.pid, proc_start=sessions.proc_start(x.pid))
        sessions.write_json_atomic(d / "meta.json", m)
        self.assertEqual(sessions.state(d)["state"], "lost")
        with mock.patch("os.killpg") as kpg, mock.patch("os.kill") as k:
            self.assertEqual(sessions.cancel(d), "foreign")
        kpg.assert_not_called()
        k.assert_not_called()
        self.assertIsNone(x.poll())

    # 2 (id 앞부분이 같은 이웃 세션 - 옛 명령줄 부분 문자열 대조가 T-1 과 T-1-2 를 가리지 못했다)
    def test_forged_meta_pointing_at_prefix_sibling_is_foreign(self):
        sib = self.spawn(["hang"], sid="T-1-2")
        self.wait_hang(sib)
        sib_pids = self.session_pids(sib)
        sm = sessions.load_meta(sib)
        d = self.root / "T-1"
        d.mkdir()
        forged = dict(sm, id="T-1")                               # 이웃 감독의 pid·시작 시각을 그대로 베낌
        (d / "meta.json").write_text(json.dumps(forged), encoding="utf-8")
        self.assertEqual(sessions.state(d)["state"], "lost")
        with mock.patch("os.killpg") as kpg, mock.patch("os.kill") as k:
            self.assertEqual(sessions.cancel(d), "foreign")
        kpg.assert_not_called()
        k.assert_not_called()
        self.assertEqual(sessions.state(sib)["state"], "running")
        self.assertTrue(all(not _gone(p) for p in sib_pids))
        self.assertEqual(sessions.cancel(sib), "killed")

    # 4
    def test_forged_end_json_while_running(self):
        root = self.work / "sessions"
        d = self.spawn(['write sessions/fe1/end.json {"state":"done","rc":0}', "hang"], sid="fe1", root=root)
        self.wait_hang(d)
        self.assertTrue((d / "end.json").exists())
        pids = self.session_pids(d)
        for _ in range(2):
            st = sessions.state(d)
            self.assertEqual((st["state"], st["orphaned"]), ("running", False), st)
            self.assertIn("end.json 이 있는데", st["why"])
            time.sleep(FINALISE + 0.2)
        self.assertEqual(sessions.cancel(d, why="검사"), "killed")   # gone 으로 빠지지 않는다
        self.assertTrue(_wait(lambda: all(_gone(p) for p in pids), 5))
        st = sessions.state(d)
        self.assertEqual(st["state"], "killed")
        self.assertIn("end.json 이 있었지만", st["why"])

    # 4 (감독 쪽: 미리 써 둔 done 이 실패를 덮지 못한다)
    def test_forged_end_json_then_failure_is_failed(self):
        root = self.work / "sessions"
        d = self.spawn(['write sessions/fe2/end.json {"state":"done","rc":0}', "exit 3"], sid="fe2", root=root)
        st = _wait(lambda: not self.session_pids(d) and sessions.state(d), 10)
        self.assertTrue(st)
        self.assertEqual((st["state"], st["rc"]), ("failed", 3))
        self.assertIn("감독 판정으로 덮음", st["why"])

    # 4 (meta.json 이 깨지거나 사라져도 살아 있으면 busy, cancel 은 표식으로 끝낸다)
    def test_corrupt_or_missing_meta_while_alive(self):
        d = self.spawn(["child 60", "hang"])
        self.wait_hang(d)
        pids = self.session_pids(d)
        self.assertGreaterEqual(len(pids), 3)
        good = (d / "meta.json").read_text(encoding="utf-8")
        (d / "meta.json").write_text("{", encoding="utf-8")
        st = sessions.state(d)
        self.assertEqual((st["state"], st["orphaned"]), ("running", True), st)
        os.unlink(d / "meta.json")
        self.assertEqual(sessions.state(d)["state"], "running")
        (d / "meta.json").write_text(good, encoding="utf-8")
        self.assertEqual(sessions.state(d)["state"], "running")
        (d / "meta.json").write_text("[1]", encoding="utf-8")
        self.assertEqual(sessions.cancel(d, why="깨진 meta"), "killed")
        self.assertTrue(_wait(lambda: all(_gone(p) for p in pids), 6))
        self.assertEqual(sessions.state(d)["state"], "killed")

    # 3 (낡은 색인이 '아무도 없음' 을 단정하지 않는다)
    def test_stale_index_does_not_report_lost(self):
        self.root.mkdir(parents=True, exist_ok=True)
        stale = sessions.live_index(self.root)                  # 세션이 뜨기 전에 훑은 색인
        d = self.spawn(["hang"])
        self.wait_hang(d)
        meta = sessions.load_meta(d)
        os.kill(meta["supervisor_pid"], signal.SIGKILL)
        self.assertTrue(_wait(lambda: _gone(meta["supervisor_pid"]), 5))
        st = sessions.state(d, live=stale)
        self.assertEqual((st["state"], st["orphaned"]), ("running", True), st)
        fresh = sessions.live_index(self.root)
        self.assertEqual(sessions.state(d, live=fresh), st)
        other = sessions.live_index(BASE / "nowhere")           # 다른 저장소의 색인은 무시한다
        self.assertEqual(sessions.state(d, live=other)["state"], "running")
        self.assertEqual(sessions.cancel(d), "killed")

    # 6
    def test_detached_grandchild_ended_by_supervisor(self):
        d = self.spawn(["detach-child 120", "exit 0"])
        self.assertEqual(self.wait_end(d)["state"], "done")
        c = self.wait_event(d, lambda e: e.kind == "tool" and e.data.get("name") == "detach-child").data["pid"]
        self.assertTrue(_wait(lambda: _gone(c), 5))
        self.assertEqual(sessions.find_orphans(self.root), [])

    # 6 (cancel 도 그룹 밖 손자를 끝낸다)
    def test_cancel_ends_detached_grandchild(self):
        d = self.spawn(["detach-child 120", "hang"])
        self.wait_hang(d)
        c = self.wait_event(d, lambda e: e.kind == "tool" and e.data.get("name") == "detach-child").data["pid"]
        self.assertEqual(sessions.cancel(d), "killed")
        self.assertTrue(_wait(lambda: _gone(c), 5))
        self.assertEqual(sessions.state(d)["state"], "killed")

    # 8
    def test_missing_proc_start_is_not_alive(self):
        x = subprocess.Popen(["sleep", "30"], start_new_session=True, env=_clean_env(),
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(lambda: (x.kill(), x.wait()))
        d = self.root / "nostart"
        d.mkdir(parents=True)
        (d / "meta.json").write_text(json.dumps({
            "id": "nostart", "harness": "fake", "started": "2026-01-01T00:00:00",
            "supervisor_pid": x.pid, "pgid": x.pid, "proc_start": None}), encoding="utf-8")
        self.assertEqual(sessions.state(d)["state"], "lost")
        with mock.patch("os.killpg") as kpg, mock.patch("os.kill") as k:
            self.assertEqual(sessions.cancel(d), "foreign")
        kpg.assert_not_called()
        k.assert_not_called()
        self.assertIsNone(x.poll())

    # 9a
    def test_own_cancel_json_without_signal_is_failed(self):
        root = self.work / "sessions"
        d = self.spawn(['write sessions/cj1/cancel.json {"why":"가짜 취소"}', "exit 3"], sid="cj1", root=root)
        st = self.wait_end(d)
        self.assertEqual((st["state"], st["rc"]), ("failed", 3))

    # 9b / 끝마무리: end.json 이 막 쓰였고 감독만 살아 있으면 끝난 것이고, cancel 은 gone 이며 기록을 안 바꾼다
    def test_finalising_supervisor_is_finished_and_not_cancelled(self):
        x = subprocess.Popen(["sleep", "30"], start_new_session=True,
                             env=_clean_env(**{ENV_SESSION: "fin1", ENV_ROOT: os.path.abspath(self.root)}),
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(lambda: (x.poll() is None and x.kill(), x.wait()))
        _wait(lambda: (sessions._proc_environ(x.pid) or {}).get(ENV_SESSION) == "fin1", 3)
        d = self.root / "fin1"
        d.mkdir(parents=True)
        (d / "meta.json").write_text(json.dumps({
            "id": "fin1", "harness": "fake", "started": "2026-01-01T00:00:00",
            "supervisor_pid": x.pid, "pgid": x.pid, "proc_start": sessions.proc_start(x.pid)}), encoding="utf-8")
        done = {"state": "done", "rc": 0, "ended": "2026-01-01T00:01:00", "fail_kind": None, "why": None}
        (d / "end.json").write_text(json.dumps(done), encoding="utf-8")
        self.assertEqual(sessions.state(d)["state"], "done")
        with mock.patch("os.killpg") as kpg, mock.patch("os.kill") as k:
            self.assertEqual(sessions.cancel(d), "gone")
        kpg.assert_not_called()
        k.assert_not_called()
        self.assertEqual(sessions.load_end(d), done)
        # 끝마무리 유예를 넘겨서도 '감독' 이 살아 있으면 end.json 을 믿지 않는다 → 끊고 killed 로 덮는다.
        old = time.time() - FINALISE - 5
        os.utime(d / "end.json", (old, old))
        self.assertEqual(sessions.state(d)["state"], "running")
        self.assertEqual(sessions.cancel(d, why="오래 산 감독"), "killed")
        self.assertEqual(x.wait(timeout=5), -signal.SIGTERM)
        self.assertEqual(sessions.load_end(d)["state"], "killed")

    def test_cancel_after_finish_keeps_result(self):
        """9b: 이미 끝난 세션을 cancel 하면 gone 이고 끝난 기록(done)은 그대로."""
        d = self.spawn(["emit 끝"])
        self.wait_end(d)
        self.assertTrue(_wait(lambda: not self.session_pids(d), 5))
        before = (d / "end.json").read_text(encoding="utf-8")
        self.assertEqual(sessions.cancel(d, why="늦은 타임아웃"), "gone")
        self.assertEqual((d / "end.json").read_text(encoding="utf-8"), before)


FINALISE = sessions.FINALISE_GRACE_SEC


class TestDb(Base):
    def test_upsert(self):
        row = {"id": "x1", "role": "worker", "harness": "fake", "state": "running", "rc": None}
        self.assertTrue(sessions.db_upsert(self.db, row))
        self.assertTrue(sessions.db_upsert(self.db, dict(row, state="done", rc=0)))
        got = sqlite3.connect(self.db).execute("SELECT state, rc FROM sessions WHERE id='x1'").fetchall()
        self.assertEqual(got, [("done", 0)])

    def test_bad_path(self):
        self.assertFalse(sessions.db_upsert(BASE / "없는" / "폴더" / "x.db", {"id": "x", "role": "w",
                                                                              "harness": "f", "state": "s"}))
        self.assertFalse(sessions.db_upsert(None, {"id": "x"}))
        self.assertFalse(sessions.db_upsert(self.db, {"id": "x"}))   # NOT NULL 위반도 예외 없이 False


class TestZZNoLeftovers(unittest.TestCase):
    def test_no_processes_left(self):
        self.assertTrue(_wait(lambda: not _ours(), 5), _ours())


if __name__ == "__main__":
    unittest.main()
