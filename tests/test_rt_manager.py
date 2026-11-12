"""관리자도 세션이다 (설계 `docs/FLEET-ENGINE-V2.md` 3.3·5.1·5.10) - `fleet_ctl` 이 관리자를 직접 띄우고·찾고·끊는다.

진짜 하네스는 띄우지 않는다(`_fleet_env` 가 AIFLEET_HARNESS=fake - 관리자의 claude 도 가짜 하네스가 된다).
모든 상태는 임시 폴더 아래이고, 감시자(`_chainwatch`) 배경 프로세스는 띄우지 않는다(`_start_watcher` 를 갈아끼운다 -
배경 프로세스는 갈아끼운 `fleet.ROOT` 를 모르고 운영 저장소를 본다). 감시 논리는 함수를 직접 짧게 돌려 본다.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _fleet_env  # noqa: F401,E402

import datetime as dt
import json
import pathlib
import re
import shutil
import signal
import tempfile
import threading
import time
import unittest
from unittest import mock

import fleet  # noqa: E402
import fleet_ctl  # noqa: E402
import fleet_graph  # noqa: E402
from fleet_rt import manager as rt_manager  # noqa: E402
from fleet_rt import sessions  # noqa: E402
from fleet_rt.base import ENV_ROOT  # noqa: E402

BASE = None
_N = [0]
_REAL_START_WATCHER = fleet_ctl._start_watcher      # 검사마다 갈아끼우기 전의 것 - 명령줄만 확인한다

TOML = """
[providers.anthropic]
max_concurrent = 3
models = ["opus", "sonnet"]

[providers.fk]
max_concurrent = 1
env_key = "FK_KEY"
base_url = "http://127.0.0.1:9/v1"
probe = "models"
models = ["x"]

[providers.ok]
max_concurrent = 3
models = ["x"]

[harness.claude]
binary = "claude"
providers = ["anthropic"]
default_model = "sonnet"

[harness.codex]
binary = "codex"
providers = ["fk", "ok"]
default_model = "ok/x"
"""


def setUpModule():
    global BASE
    BASE = pathlib.Path(tempfile.mkdtemp(prefix="rt-manager-"))


def _ours(prefix=None):
    prefix = str(prefix or BASE)
    out = []
    for p in sessions._live_pids():
        env = sessions._proc_environ(p)
        if env and str(env.get(ENV_ROOT, "")).startswith(prefix + os.sep) and sessions._proc_state(p) not in (None, "Z"):
            out.append(p)
    return out


def tearDownModule():
    left = _ours()
    for p in left:
        try:
            os.kill(p, signal.SIGKILL)
        except OSError:
            pass
    shutil.rmtree(BASE, ignore_errors=True)
    if left:
        raise AssertionError(f"검사 뒤 남은 프로세스: {left}")


def _wait(pred, timeout=10.0, step=0.05):
    deadline = time.time() + timeout
    while time.time() < deadline:
        v = pred()
        if v:
            return v
        time.sleep(step)
    return pred()


def _gone(pid):
    return sessions._proc_state(pid) in (None, "Z")


class Base(unittest.TestCase):
    def setUp(self):
        _N[0] += 1
        self.root = BASE / f"t{_N[0]}"
        self.aimem = self.root / ".aimem"
        (self.aimem / "briefs").mkdir(parents=True)
        (self.root / "fleet.toml").write_text(TOML, encoding="utf-8")
        self.sroot = self.aimem / "sessions"
        self.graphs = self.aimem / "graph"
        self.started = []
        self.watch_modes = []           # (라운드, 마감만?) - 감시자를 어떤 방식으로 띄웠나
        patches = [
            mock.patch.object(fleet, "ROOT", self.root),
            mock.patch.object(fleet, "RUNS", self.aimem / "runs"),
            mock.patch.object(fleet_graph, "ROOT", self.root),
            mock.patch.object(fleet_graph, "GRAPHS", self.graphs),
            mock.patch.object(fleet_graph, "_LOGGED_ONCE", set()),
            mock.patch.object(fleet, "roster", return_value={"S1": ("aaaaaa", "codex", ""), "S2": ("bbbbbb", "codex", "")}),
            mock.patch.object(fleet, "_slot_model", side_effect=lambda slot: {"S1": "fk/x", "S2": "ok/x"}.get(slot)),
            mock.patch.object(fleet, "read_rev", return_value=1),
            mock.patch.object(fleet, "db_state", return_value=None),
            mock.patch.object(fleet_ctl, "_rev_lint_checks", return_value=[]),
            mock.patch.object(fleet_ctl, "_start_watcher",
                              side_effect=lambda n, close_only=False: self.started.append(n) or self.watch_modes.append(
                                  (n, close_only)) or True),
            mock.patch.dict(os.environ, {fleet_ctl.FORCE_ENV: ""}),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self._reap_all)

    def _reap_all(self):
        try:
            for sid in sessions.list_ids(self.sroot):
                if sessions.state(self.sroot / sid)["state"] == "running":
                    sessions.cancel(self.sroot / sid, "검사 정리")
        except Exception:  # noqa: BLE001
            pass
        _wait(lambda: not _ours(self.root), 5)
        left = _ours(self.root)
        for p in left:
            try:
                os.kill(p, signal.SIGKILL)
            except OSError:
                pass
        if left:
            self.fail(f"검사가 끝났는데 프로세스가 남았다: {left}")

    # ---- 도우미
    def brief(self, *fake_lines):
        text = "# 관리자 R{round} 브리프 ({date}, REV {rev}, {workspace})\n" + "".join(f"FAKE: {x}\n" for x in fake_lines)
        (self.aimem / "briefs" / fleet_ctl.STANDARD_BRIEF).write_text(text, encoding="utf-8")

    def launch(self, *fake_lines):
        self.brief(*fake_lines)
        fleet_ctl.set_mode("ready", "test")
        out = fleet_ctl.launch_round("test")
        self.assertTrue(out["ok"], out)
        return out

    def report_path(self, n):
        return self.root / "rounds" / f"R{n}" / "REPORT.md"

    def fake_session(self, sid, n, end_state="done"):
        d = self.sroot / sid
        d.mkdir(parents=True)
        (d / "meta.json").write_text(json.dumps({"id": sid, "role": "manager", "round": n, "harness": "claude",
                                                 "label": f"관리자 R{n}", "started": "2026-11-12T10:00:00",
                                                 "supervisor_pid": 999999, "proc_start": 1, "extra": {"by": "옛"}}),
                                     encoding="utf-8")
        (d / "end.json").write_text(json.dumps({"state": end_state, "rc": 0, "ended": "2026-11-12T11:00:00"}), encoding="utf-8")
        return d


class LaunchAndStop(Base):
    def test_launch_spawns_a_manager_session_and_stop_ends_it_with_a_minimal_close(self):
        (self.root / "rounds" / "R7").mkdir(parents=True)
        (self.root / "rounds" / "R7" / "round.json").write_text(json.dumps({"round": 7}), encoding="utf-8")
        self.assertIsNone(fleet_ctl.public_state()["manager"])
        out = self.launch("child 300", "detach-child 300", "hang")
        n, sid = out["round"], out["session"]
        self.assertEqual(n, 8)                                     # 번호는 라운드 기록 폴더 다음
        self.assertRegex(sid, r"\AM-R8-\d{6}\Z")
        self.assertEqual(rt_manager.round_of(sid), 8)
        self.assertEqual(self.started, [8])                        # 감시자를 띄운다
        meta = sessions.load_meta(self.sroot / sid)
        self.assertEqual((meta["role"], meta["round"], meta["model"], meta["tools"], meta["idle_timeout"]),
                         ("manager", 8, "opus", rt_manager.MANAGER_TOOLS, None))
        self.assertEqual((meta["extra"]["by"], meta["extra"]["workspace"], meta["provider"]), ("test", "rounds/R8", "anthropic"))
        self.assertTrue(re.fullmatch(r"[0-9a-f-]{36}", meta["extra"]["harness_session_id"]))
        self.assertIn("관리자 R8 브리프", (self.sroot / sid / "brief.md").read_text(encoding="utf-8"))
        rec = json.loads((self.root / "rounds" / "R8" / "round.json").read_text(encoding="utf-8"))
        self.assertEqual(rec["session"], sid)
        self.assertEqual(fleet_ctl.mode(), "running")
        # 관리자 하네스가 손자 둘을 띄울 때까지
        ev = _wait(lambda: len([ln for ln in (self.sroot / sid / "events.jsonl").read_text(encoding="utf-8").splitlines()
                                if "child" in ln]) >= 2 if (self.sroot / sid / "events.jsonl").exists() else False)
        self.assertTrue(ev)
        kids = [json.loads(ln.partition("\t")[2])["pid"] for ln in
                (self.sroot / sid / "events.jsonl").read_text(encoding="utf-8").splitlines() if "child" in ln]

        st = fleet_ctl.public_state()
        m = st["manager"]
        self.assertEqual((m["round"], m["session"], m["by"], m["workspace"]), (8, sid, "test", "rounds/R8"))
        self.assertIn(m["state"], ("launching", "running"))
        self.assertEqual(set(m), {"round", "label", "session", "state", "by", "at", "ended", "brief", "workspace", "last_event_at"})
        self.assertNotIn("relay", st)
        self.assertFalse(st["idle"])
        self.assertFalse(st["can"]["round"])
        self.assertTrue(st["can"]["stop"])
        self.assertEqual([s["id"] for s in fleet_ctl.manager_running()], [sid])
        self.assertEqual(fleet_ctl.active_round(), 8)
        self.assertEqual(fleet_ctl.running_runs(), [])            # 관리자는 작업자로 세지 않는다
        self.assertFalse(fleet_ctl.round_over())
        # 거절: '실행' 중에는 새 라운드 없음, 준비로 돌려도 관리자가 살아 있으면 없음
        self.assertIn("준비", fleet_ctl.launch_round("test")["error"])
        fleet_ctl.set_mode("ready", "test")
        out2 = fleet_ctl.launch_round("test")
        self.assertFalse(out2["ok"])
        self.assertIn("이미 실행 중인 관리자", out2["error"])

        res = fleet_ctl.stop("test")
        self.assertEqual([(x["id"], x["outcome"]) for x in res["managers"]], [(sid, "killed")])
        self.assertEqual(res["closed_rounds"], [8])
        self.assertTrue(_wait(lambda: all(_gone(p) for p in kids), 5), kids)
        self.assertEqual(_ours(self.root), [])                    # 이 저장소 표식을 단 프로세스가 하나도 없다
        text = self.report_path(8).read_text(encoding="utf-8")
        self.assertIn("관리자 없이 끝남 (killed)", text)
        self.assertEqual(fleet_ctl.round_report_status(8), "PARTIAL")
        self.assertEqual(fleet_ctl.public_state()["manager"]["state"], "killed")
        self.assertIsNone(fleet_ctl.active_round())
        self.assertEqual(fleet_ctl.mode(), "stopped")
        # 보고가 이미 있으면 덮지 않는다
        self.assertFalse(fleet_ctl.write_minimal_close(8, "다시"))

    def test_stop_ends_the_chain_watcher_only_if_it_is_the_recorded_one(self):
        import subprocess
        code = "import time; time.sleep(60)"
        other = subprocess.Popen([sys.executable, "-c", code, "x"])          # 명령줄이 감시자가 아니다
        watcher = subprocess.Popen([sys.executable, "-c", code, "_chainwatch"])
        self.addCleanup(lambda: [p.kill() for p in (other, watcher)])
        path = self.aimem / "fleet-chain.watch.json"
        path.write_text(json.dumps({"pid": other.pid, "start": sessions.proc_start(other.pid)}), encoding="utf-8")
        self.assertIsNone(fleet_ctl._end_chain_watcher())
        path.write_text(json.dumps({"pid": watcher.pid, "start": 1}), encoding="utf-8")             # 시작 시각이 다르다
        self.assertIsNone(fleet_ctl._end_chain_watcher())
        path.write_text(json.dumps({"pid": watcher.pid, "start": sessions.proc_start(watcher.pid)}), encoding="utf-8")
        fleet_ctl.set_mode("running", "test")
        self.assertEqual(fleet_ctl.stop("test")["chain_watcher"], watcher.pid)
        self.assertIsNotNone(watcher.wait(timeout=5))
        self.assertIsNone(other.poll())

    def test_spawn_failure_marks_the_round_failed_and_stops_the_chain(self):
        self.brief()
        fleet_ctl.set_mode("ready", "test")
        fleet_ctl.chain_set(True, None, 3, "test", all_=True)
        with mock.patch.object(sessions, "spawn", side_effect=RuntimeError("감독 실패")):
            out = fleet_ctl.launch_round("test")
        self.assertFalse(out["ok"])
        self.assertIn("감독 실패", out["error"])
        rec = json.loads((self.root / "rounds" / f"R{out['round']}" / "round.json").read_text(encoding="utf-8"))
        self.assertEqual(rec["state"], "failed")
        self.assertEqual(fleet_ctl.mode(), "ready")
        self.assertEqual(fleet_ctl.public_state()["manager"]["state"], "failed")
        st = fleet_ctl.chain_state()
        self.assertEqual((st["on"], st["stopped_kind"]), (False, "error"))
        self.assertEqual(self.started, [])


class Watcher(Base):
    def test_a_manager_that_fails_gets_a_minimal_close_and_the_chain_stops(self):
        req = self.aimem / "requests"
        req.mkdir()
        (req / "Q-1.json").write_text(json.dumps({"id": "Q-1", "status": "NEW"}), encoding="utf-8")
        out = self.launch("emit 시작", "exit 3")
        n, sid = out["round"], out["session"]
        self.graphs.mkdir(parents=True, exist_ok=True)
        (self.graphs / "G-950.json").write_text(json.dumps({"id": "G-950", "round": n, "nodes": [
            {"id": "A", "title": "끝남", "status": "done"}, {"id": "B", "title": "남음", "status": "running"}]}), encoding="utf-8")
        fleet_ctl.chain_set(True, None, 3, "test", all_=True)
        self.assertEqual(_wait(lambda: sessions.state(self.sroot / sid)["state"] != "running", 10)
                         and sessions.state(self.sroot / sid)["state"], "failed")
        # 그래프 노드가 'running' 으로 남았지만 실행기는 없다 - 라운드는 끝난 것으로 보고 이어 달리기가 판단한다
        rc = fleet_ctl._chain_wait_and_step(n, poll=0.05, wait=5)
        self.assertEqual(rc, 0)
        text = self.report_path(n).read_text(encoding="utf-8")
        self.assertIn("상태: PARTIAL", text)
        self.assertIn("관리자 없이 끝남 (failed)", text)
        self.assertIn("G-950 / B (running) 남음", text)
        self.assertNotIn("G-950 / A", text)
        self.assertIn("git status", text)
        st = fleet_ctl.chain_state()
        self.assertEqual((st["on"], st["stopped_kind"]), (False, "report"))     # PARTIAL 은 사람이 본다
        self.assertEqual(fleet_ctl.public_state()["last_round"]["report_status"], "PARTIAL")

    def test_a_manager_that_finishes_done_is_not_overwritten(self):
        out = self.launch("report DONE\\n끝")
        n, sid = out["round"], out["session"]
        _wait(lambda: sessions.state(self.sroot / sid)["state"] == "done", 10)
        self.assertIsNone(fleet_ctl.close_if_unreported(n))
        self.assertFalse(self.report_path(n).exists())
        self.assertEqual(fleet_ctl._chain_wait_and_step(n, poll=0.05, wait=2), 0)   # 이어 달리기가 꺼져 있으면 바로 끝
        self.assertEqual(fleet_ctl.public_state()["manager"]["state"], "done")
        self.assertTrue(fleet_ctl.public_state()["idle"])


class Numbering(Base):
    def test_round_numbers_come_from_round_records_and_manager_sessions(self):
        self.brief()
        self.assertEqual(fleet_ctl.latest_brief()["round"], 1)
        (self.root / "rounds" / "R7").mkdir(parents=True)
        (self.root / "rounds" / "R7" / "round.json").write_text(json.dumps({"round": 7}), encoding="utf-8")
        self.assertEqual(fleet_ctl.latest_brief()["round"], 8)
        self.fake_session("M-R12-101010", 12)
        rows = fleet_ctl.manager_sessions()
        self.assertEqual([(r["id"], r["round"], r["status"]) for r in rows], [("M-R12-101010", 12, "done")])
        self.assertEqual(set(rows[0]), {"id", "label", "round", "status", "why", "started", "ended", "last_event_at",
                                        "orphaned", "by", "brief", "workspace"})
        self.assertEqual(fleet_ctl.latest_brief()["round"], 13)
        self.assertEqual(fleet_ctl.manager_running(), [])
        self.assertIsNone(fleet_ctl.active_round())
        m = fleet_ctl.public_state()["manager"]
        self.assertEqual((m["round"], m["session"], m["state"]), (12, "M-R12-101010", "done"))
        # 작업자 세션 폴더는 관리자로 세지 않는다
        (self.sroot / "T-1-S1-a1-101010").mkdir()
        (self.sroot / "T-1-S1-a1-101010" / "meta.json").write_text(json.dumps({"role": "worker", "round": 40}), encoding="utf-8")
        self.assertEqual(len(fleet_ctl.manager_sessions()), 1)
        self.assertEqual(fleet_ctl.latest_brief()["round"], 13)


class Prepare(Base):
    def env_file(self, text="FK_KEY=\n"):
        p = self.root / ".env"
        p.write_text(text, encoding="utf-8")
        os.chmod(p, 0o600)

    def checks(self):
        res = fleet_ctl.prepare("test")
        return res, {c["name"]: c for c in res["checks"]}

    def test_runtime_checks(self):
        self.brief()
        self.env_file()
        res, c = self.checks()
        self.assertTrue(c["하네스 claude (관리자)"]["ok"])          # 가짜 하네스의 probe
        self.assertTrue(c["하네스 codex (S1, S2)"]["ok"])
        self.assertTrue(c["키 파일 .env"]["ok"])
        self.assertTrue(c["공급자 anthropic (관리자)"]["ok"])
        self.assertTrue(c["공급자 ok (S2)"]["ok"])
        # 키가 없는 무료 공급자 하나는 키 줄에서 실패한다 (이름만 본다). 응답 점검은 키를 보내지 않는다 -
        # 여기 base_url(127.0.0.1:9)은 아무도 듣지 않으므로 응답 줄도 실패한다
        self.assertFalse(c["키 fk (S1)"]["ok"])
        self.assertIn("FK_KEY", c["키 fk (S1)"]["detail"])
        self.assertFalse(c["공급자 fk (S1)"]["ok"])
        self.assertNotIn("키 anthropic (관리자)", c)                 # 키를 쓰지 않는 공급자는 키 줄이 없다
        self.assertTrue(c["남은 세션 프로세스 없음"]["ok"])
        self.assertTrue(c["실행 중인 관리자 없음"]["ok"])
        self.assertFalse(res["ok"])
        self.assertFalse(any("openclaw" in name for name in c))
        # 공급자를 둘 다 통과시키면 준비가 된다
        with mock.patch.object(fleet, "_slot_model", return_value="ok/x"):
            res, c = self.checks()
        self.assertTrue(res["ok"], [x for x in res["checks"] if not x["ok"]])
        self.assertEqual(fleet_ctl.mode(), "ready")

    def test_missing_env_file_fails(self):
        with mock.patch.object(fleet, "_slot_model", return_value="ok/x"):
            res, c = self.checks()
        self.assertFalse(c["키 파일 .env"]["ok"])
        self.assertFalse(res["ok"])
        self.env_file()
        os.chmod(self.root / ".env", 0o644)
        with mock.patch.object(fleet, "_slot_model", return_value="ok/x"):
            res, c = self.checks()
        self.assertFalse(c["키 파일 .env"]["ok"])
        self.assertIn("600", c["키 파일 .env"]["detail"])

    def test_a_leftover_session_process_fails_and_is_not_killed(self):
        self.env_file()
        pid = _fleet_env.marked_pid(self.sroot, "T-9-S2-a1-000000")       # 세션 폴더 없이 표식만 단 프로세스
        self.assertTrue(_wait(lambda: any(o["pid"] == pid for o in sessions.find_orphans(self.sroot)), 5))
        with mock.patch.object(fleet, "_slot_model", return_value="ok/x"):
            res, c = self.checks()
        self.assertFalse(c["남은 세션 프로세스 없음"]["ok"])
        self.assertIn(f"pid {pid}", c["남은 세션 프로세스 없음"]["detail"])
        self.assertFalse(res["ok"])
        self.assertFalse(_gone(pid))                               # 준비는 끊지 않는다 - 사람이 '완전 중지' 로
        fleet_ctl.set_mode("running", "test")
        res = fleet_ctl.stop("test")
        self.assertIn(pid, [o["pid"] for o in res["reaped"]])
        self.assertTrue(_wait(lambda: _gone(pid), 5))


class ReviewFixes(Base):
    """2026-11-12 적대적 검수의 재현(`race_repro.py`·`forge2.py`·`chain_repro.py` 등)을 회귀 검사로."""

    def texts(self, d):
        return [ev.text for _at, ev in sessions.tail(d, 200) if ev.kind == "text"]

    # ---- 4. 두 번 누름
    def test_two_concurrent_launches_leave_one_manager_and_the_mode_running(self):
        self.brief("hang")
        fleet_ctl.set_mode("ready", "test")
        real = fleet_ctl._round_brief_path
        bar = threading.Barrier(2)

        def slow(b, at):
            time.sleep(0.4)          # 첫 누름이 관리자를 띄우는 사이에 둘째 누름이 들어온다
            return real(b, at)
        res = []

        def tap():
            bar.wait(5)
            res.append(fleet_ctl.launch_round("test"))
        with mock.patch.object(fleet_ctl, "_round_brief_path", side_effect=slow):
            ts = [threading.Thread(target=tap) for _ in range(2)]
            [t.start() for t in ts]
            [t.join(30) for t in ts]
        self.assertEqual(sorted(bool(r["ok"]) for r in res), [False, True], res)
        lost = next(r for r in res if not r["ok"])
        self.assertIn("이미", lost["error"])
        won = next(r for r in res if r["ok"])
        self.assertEqual(fleet_ctl.mode(), "running")                  # 진 쪽이 '준비' 로 돌리지 않았다
        self.assertTrue(fleet_ctl.spawn_allowed()[0])                  # 도는 관리자가 작업자를 띄울 수 있다
        rec = json.loads((self.root / "rounds" / f"R{won['round']}" / "round.json").read_text(encoding="utf-8"))
        self.assertNotEqual(rec.get("state"), "failed")
        self.assertEqual([s["id"] for s in fleet_ctl.manager_running()], [won["session"]])

    def test_a_busy_launch_lock_refuses_without_touching_mode_or_records(self):
        import fcntl
        self.brief("hang")
        fleet_ctl.set_mode("ready", "test")
        with open(self.aimem / "fleet-launch.lock", "a") as held:
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
            out = fleet_ctl.launch_round("test")
        self.assertEqual(out, {"ok": False, "error": "이미 라운드를 띄우는 중입니다"})
        self.assertEqual(fleet_ctl.mode(), "ready")
        self.assertFalse((self.root / "rounds").exists())

    def test_spawn_file_exists_while_a_manager_runs_does_not_fail_the_round(self):
        out = self.launch("hang")
        n, sid = out["round"], out["session"]
        self.assertTrue(_wait(lambda: fleet_ctl.manager_running(), 5))
        fleet_ctl.set_mode("ready", "test")
        b = dict(fleet_ctl.latest_brief(), round=n, workspace=f"rounds/R{n}")
        real_running = fleet_ctl.manager_running
        calls = []

        def first_empty():                       # 잠금 밖 경쟁을 흉내: 앞의 확인은 관리자를 못 보고 지나간다
            calls.append(1)
            return [] if len(calls) == 1 else real_running()
        with mock.patch.object(fleet_ctl, "latest_brief", return_value=b), \
                mock.patch.object(fleet_ctl, "_new_manager_id", return_value=sid), \
                mock.patch.object(fleet_ctl, "manager_running", side_effect=first_empty), \
                mock.patch.object(fleet_ctl, "round_over", return_value=False):
            out2 = fleet_ctl.launch_round("test")
        self.assertFalse(out2["ok"])
        self.assertIn("이미 실행 중인 관리자", out2["error"])
        rec = json.loads((self.root / "rounds" / f"R{n}" / "round.json").read_text(encoding="utf-8"))
        self.assertNotEqual(rec.get("state"), "failed")
        self.assertEqual(fleet_ctl.mode(), "running")

    def test_set_mode_is_safe_when_called_concurrently(self):
        errs = []

        def hammer():
            try:
                for _ in range(30):
                    fleet_ctl.set_mode("ready", "t")
            except Exception as e:  # noqa: BLE001
                errs.append(e)
        ts = [threading.Thread(target=hammer) for _ in range(6)]
        [t.start() for t in ts]
        [t.join(30) for t in ts]
        self.assertEqual(errs, [])
        self.assertEqual(fleet_ctl.mode(), "ready")
        self.assertEqual([p.name for p in self.aimem.glob("fleet-mode.json*.tmp")], [])

    # ---- 5. 꾸민 관리자 폴더
    def forged(self, sid, started, supervisor_pid=None):
        d = self.sroot / sid
        d.mkdir(parents=True)
        (d / "meta.json").write_text(json.dumps({"id": sid, "role": "manager", "round": 99, "label": "관리자 R99 (Opus)",
                                                 "started": started, "supervisor_pid": supervisor_pid}), encoding="utf-8")
        return d

    def test_a_forged_manager_folder_dated_in_the_future_does_not_block_rounds(self):
        self.brief()
        fleet_ctl._write_round_record(7, dt.datetime.now(), "x")
        d = self.forged("M-R99-000000", "9999-12-31T00:00:00")
        self.assertEqual(sessions.state(d)["state"], "lost")            # '띄우는 중' 이 아니다
        self.forged("M-R98-000000", "언제인지 모름")
        self.assertEqual(sessions.state(self.sroot / "M-R98-000000")["state"], "lost")
        self.assertEqual(fleet_ctl.manager_running(), [])
        self.assertIsNone(fleet_ctl.active_round())
        fleet_ctl.set_mode("ready", "test")
        st = fleet_ctl.public_state()
        self.assertEqual(st["manager"]["state"], "lost")
        self.assertTrue(st["can"]["round"])
        fleet_ctl.set_mode("running", "test")
        out = fleet_ctl.stop("test")
        self.assertEqual(out["managers"], [])                            # 끊을 것이 없다 ('refused' 가 아니다)
        self.assertIn(99, out["closed_rounds"])                          # 사라진 관리자의 라운드도 마감한다
        self.assertIn("관리자 없이 끝남 (lost)", self.report_path(99).read_text(encoding="utf-8"))
        self.assertTrue(fleet_ctl.prepare("test")["checks"])
        self.assertTrue(next(c for c in fleet_ctl.prepare("test")["checks"] if c["name"] == "실행 중인 관리자 없음")["ok"])

    def test_a_round_record_dated_in_the_future_is_not_launching_forever(self):
        self.brief()
        d = self.root / "rounds" / "R100"
        d.mkdir(parents=True)
        (d / "round.json").write_text(json.dumps({"round": 100, "at": "9999-12-31T00:00:00", "session": "M-R100-000000"}),
                                      encoding="utf-8")
        fleet_ctl.set_mode("ready", "test")
        st = fleet_ctl.public_state()
        self.assertEqual(st["manager"]["state"], "lost")
        self.assertTrue(st["can"]["round"])

    def test_a_forged_manager_with_a_marked_process_is_ended_by_stop(self):
        sid = "M-R99-000001"
        pid = _fleet_env.marked_pid(self.sroot, sid)
        self.forged(sid, "9999-12-31T00:00:00", supervisor_pid=1)
        self.assertEqual([s["id"] for s in fleet_ctl.manager_running()], [sid])
        fleet_ctl.set_mode("running", "test")
        out = fleet_ctl.stop("test")
        self.assertEqual([(m["id"], m["outcome"]) for m in out["managers"]], [(sid, "killed")])
        self.assertTrue(_wait(lambda: _gone(pid), 5))

    # ---- 3. 감시자
    def test_a_round_launched_with_chaining_off_gets_a_close_only_watcher(self):
        out = self.launch("hang")
        self.assertEqual(self.watch_modes, [(out["round"], True)])
        with mock.patch.object(fleet_ctl, "_end_chain_watcher", return_value=None) as end:
            fleet_ctl.chain_set(True, None, 3, "사람", all_=True)          # 사람이 도중에 켜면 이어 달리기 감시자로 갈아 끼운다
        end.assert_called_once()
        self.assertEqual(self.watch_modes, [(out["round"], True), (out["round"], False)])

    def test_a_round_launched_with_chaining_on_gets_a_chain_watcher(self):
        self.brief("hang")
        fleet_ctl.set_mode("ready", "test")
        fleet_ctl.chain_set(True, None, 3, "test", all_=True)
        out = fleet_ctl.launch_round("test")
        self.assertTrue(out["ok"], out)
        self.assertEqual(self.watch_modes, [(out["round"], False)])

    def test_close_only_mode_travels_on_the_command_line(self):
        with mock.patch.object(fleet_ctl.subprocess, "Popen") as po:
            self.assertTrue(_REAL_START_WATCHER(5, close_only=True))
            self.assertTrue(_REAL_START_WATCHER(6))
        self.assertEqual(po.call_args_list[0][0][0][-3:], ["--round", "5", "--close-only"])
        self.assertEqual(po.call_args_list[1][0][0][-2:], ["--round", "6"])
        with mock.patch.object(fleet_ctl, "_chain_wait_and_step", return_value=0) as w:
            fleet_ctl.main(["_chainwatch", "--round", "5", "--close-only"])
            fleet_ctl.main(["_chainwatch", "--round", "6"])
        self.assertEqual(w.call_args_list, [mock.call(5, close_only=True), mock.call(6, close_only=False)])

    def test_a_close_only_watcher_ignores_a_chain_file_a_worker_switched_on(self):
        (self.root / "rounds" / "R5").mkdir(parents=True)
        fleet_ctl.set_mode("running", "human")
        fleet_ctl._write_round_record(5, dt.datetime.now() - dt.timedelta(minutes=10), "x", session="M-R5-120000")
        # 작업자가 쓴 파일들 (모두 저장소 안의 평범한 파일)
        (self.aimem / "fleet-chain.json").write_text(json.dumps({
            "on": True, "all": True, "fleet": True, "projects": [], "max_rounds": 10, "renew": True, "autonomous": True,
            "total_rounds": 0, "goals_done": -1, "open_requests": ["Q-x"], "queue_left": 99}), encoding="utf-8")
        self.report_path(5).write_text("상태: DONE\n", encoding="utf-8")
        (self.aimem / "requests").mkdir()
        (self.aimem / "requests" / "Q-evil.json").write_text(json.dumps({"id": "Q-evil", "status": "NEW"}), encoding="utf-8")
        (self.aimem / "briefs" / "manager-round900-2026-11-12.md").write_text("작업자가 고른 브리프", encoding="utf-8")
        with mock.patch.object(fleet_ctl, "launch_round") as lr:
            self.assertEqual(fleet_ctl._watch(5, poll=0.01, wait=2, close_only=True), 0)
        lr.assert_not_called()
        self.assertTrue(fleet_ctl.chain_state()["on"])                    # 파일도 건드리지 않는다
        # 비교: 이어 달리기 감시자(사람이 켜고 띄운 것)는 같은 파일로 다음 라운드를 판단한다
        with mock.patch.object(fleet_ctl, "launch_round", return_value={"ok": True, "round": 900}) as lr:
            fleet_ctl._watch(5, poll=0.01, wait=2)
        lr.assert_called_once()

    # ---- 11. 라운드 폴더 링크
    def test_a_planted_rounds_symlink_is_refused_before_spawning(self):
        outside = BASE / f"outside{_N[0]}"
        outside.mkdir()
        self.brief("hang")
        fleet_ctl.set_mode("ready", "test")
        (self.root / "rounds").mkdir()
        (self.root / "rounds" / "R1").symlink_to(outside, target_is_directory=True)
        out = fleet_ctl.launch_round("test")
        self.assertFalse(out["ok"])
        self.assertIn("심볼릭 링크", out["error"])
        self.assertEqual(list(outside.iterdir()), [])                     # 저장소 밖에 아무것도 쓰지 않았다
        self.assertFalse(self.sroot.exists() and any(self.sroot.iterdir()))   # 관리자를 띄우지 않았다
        self.assertEqual(fleet_ctl.mode(), "ready")
        self.assertFalse(fleet_ctl.write_minimal_close(1, "검사"))
        self.assertEqual(list(outside.iterdir()), [])
        # `rounds/` 자체가 링크여도 마찬가지
        (self.root / "rounds" / "R1").unlink()
        (self.root / "rounds").rmdir()
        (self.root / "rounds").symlink_to(outside, target_is_directory=True)
        self.assertFalse(fleet_ctl.launch_round("test")["ok"])
        self.assertFalse(fleet_ctl.write_minimal_close(1, "검사"))
        self.assertEqual(list(outside.iterdir()), [])

    def test_a_planted_brief_link_inside_the_round_folder_is_replaced_not_followed(self):
        outside = BASE / f"outside-file{_N[0]}"
        outside.write_text("밖의 파일", encoding="utf-8")
        (self.root / "rounds" / "R1").mkdir(parents=True)
        (self.root / "rounds" / "R1" / "brief.md").symlink_to(outside)
        (self.root / "rounds" / "R1" / "round.json").symlink_to(outside)
        b = {"round": 1, "file": fleet_ctl.STANDARD_BRIEF, "standard": True}
        self.brief()
        p = fleet_ctl._round_brief_path(b, dt.datetime.now())
        fleet_ctl._write_round_record(1, dt.datetime.now(), "x")
        self.assertEqual(outside.read_text(encoding="utf-8"), "밖의 파일")
        self.assertFalse(p.is_symlink())
        self.assertFalse((self.root / "rounds" / "R1" / "round.json").is_symlink())

    # ---- 2·6. 관리자 세션의 환경과 도구
    def test_the_manager_gets_nothing_from_env_file_and_the_deny_list(self):
        p = self.root / ".env"
        p.write_text("FK_KEY=fk-value\nANTHROPIC_BASE_URL=http://evil.invalid\nBASH_ENV=/tmp/evil\n", encoding="utf-8")
        os.chmod(p, 0o600)
        with mock.patch.dict(os.environ):
            for k in ("FK_KEY", "ANTHROPIC_BASE_URL", "BASH_ENV"):
                os.environ.pop(k, None)
            out = self.launch("env ANTHROPIC_BASE_URL", "env BASH_ENV", "env FK_KEY", "exit 0")
        d = self.sroot / out["session"]
        self.assertTrue(_wait(lambda: sessions.state(d)["state"] != "running", 10))
        texts = self.texts(d)
        for name in ("ANTHROPIC_BASE_URL", "BASH_ENV", "FK_KEY"):
            self.assertIn(f"{name}=", texts)                             # 관리자(anthropic)는 `.env` 에서 아무것도 받지 않는다
        meta = sessions.load_meta(d)
        self.assertEqual(meta["env_file_names"], [])
        self.assertEqual(meta["extra"]["disallowed_tools"], rt_manager.MANAGER_DENIED)


if __name__ == "__main__":
    unittest.main()
