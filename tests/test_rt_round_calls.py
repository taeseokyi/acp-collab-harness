"""호출 방식 라운드 (설계 `docs/FLEET-ENGINE-V2.md` 5.9) - 관리자는 ① 계획 ② 판정 ③ 마감에서만 뜨고 그 사이 그래프는
엔진의 구동기(`fleet_ctl._drive`)가 돌린다.

진짜 하네스는 띄우지 않는다(`_fleet_env` 가 AIFLEET_HARNESS=fake). 모든 상태는 임시 폴더 아래이고 배경 구동기
(`_rounddrive`)는 띄우지 않는다(`_start_driver` 를 갈아끼운다 - 배경 프로세스는 갈아끼운 `fleet.ROOT` 를 모르고 운영
저장소를 본다). 고리 논리는 이음새(`spawn_call`·`run_graphs`)를 갈아 끼워 프로세스 없이 보고, 끝에서 끝까지는 진짜
(가짜 하네스) 세션으로 한 번 돈다. '살아 있는 구동기' 는 명령줄에 `_rounddrive` 를 단 `sleep` 프로세스로 흉내 낸다.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _fleet_env  # noqa: F401,E402

import datetime as dt
import json
import pathlib
import shutil
import signal
import subprocess
import tempfile
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

TOML = """
[providers.anthropic]
max_concurrent = 3
models = ["opus", "sonnet"]

[providers.ok]
max_concurrent = 3
models = ["x"]

[harness.claude]
binary = "claude"
providers = ["anthropic"]
default_model = "sonnet"

[harness.codex]
binary = "codex"
providers = ["ok"]
default_model = "ok/x"

[manager]
mode = "calls"
"""


def setUpModule():
    global BASE
    BASE = pathlib.Path(tempfile.mkdtemp(prefix="rt-calls-"))


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


class Base(unittest.TestCase):
    N = 5

    def setUp(self):
        _N[0] += 1
        self.root = BASE / f"t{_N[0]}"
        self.aimem = self.root / ".aimem"
        (self.aimem / "briefs").mkdir(parents=True)
        (self.root / "fleet.toml").write_text(TOML, encoding="utf-8")
        self.sroot = self.aimem / "sessions"
        self.graphs = self.aimem / "graph"
        self.graphs.mkdir()
        self.drivers = []                     # (라운드, 마감만?) - `_start_driver` 를 어떻게 불렀나
        self.watchers = []
        patches = [
            mock.patch.object(fleet, "ROOT", self.root),
            mock.patch.object(fleet, "RUNS", self.aimem / "runs"),
            mock.patch.object(fleet_graph, "ROOT", self.root),
            mock.patch.object(fleet_graph, "GRAPHS", self.graphs),
            mock.patch.object(fleet_graph, "_LOGGED_ONCE", set()),
            mock.patch.object(fleet, "roster", return_value={"S2": ("bbbbbb", "codex", "")}),
            mock.patch.object(fleet, "_slot_model", return_value="ok/x"),
            mock.patch.object(fleet, "read_rev", return_value=1),
            mock.patch.object(fleet, "db_state", return_value=None),
            mock.patch.object(fleet, "owned_paths", return_value=[]),
            mock.patch.object(fleet_ctl, "_rev_lint_checks", return_value=[]),
            mock.patch.object(fleet_ctl, "_CHAIN_ARMED", [False]),
            mock.patch.object(fleet_ctl, "_start_driver",
                              side_effect=lambda n, close_only=False: self.drivers.append((n, close_only)) or True),
            mock.patch.object(fleet_ctl, "_start_watcher",
                              side_effect=lambda n, close_only=False: self.watchers.append((n, close_only)) or True),
            mock.patch.dict(os.environ, {fleet_ctl.FORCE_ENV: ""}),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self._reap_all)
        self.spawned, self.ran = [], []

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
    def templates(self, plan="", judge="", close=""):
        for phase, body in (("plan", plan), ("judge", judge), ("close", close)):
            (self.aimem / "briefs" / f"manager-call-{phase}.md").write_text(
                f"# R{{round}} 호출 {phase} ({{date}}, REV {{rev}}, {{workspace}})\n{body}", encoding="utf-8")
        (self.aimem / "briefs" / fleet_ctl.STANDARD_BRIEF).write_text("# 상주 표준 브리프 R{round}\n", encoding="utf-8")

    def calls_round(self, n=None):
        """런처가 남기는 것과 같은 호출 방식 라운드 기록 (구동기는 띄우지 않음)."""
        n = n or self.N
        self.templates()
        fleet_ctl.set_mode("running", "test")
        fleet_ctl._write_round_record(n, dt.datetime.now(), fleet_ctl.STANDARD_BRIEF, session=f"M-R{n}-000001", calls_by="test")
        return n

    def graph(self, gid, n, statuses=("todo",)):
        nodes = [{"id": f"T-{gid[2:]}{i}", "title": f"노드 {i}", "slot": "S2", "status": s, "attempts": [], "deps": []}
                 for i, s in enumerate(statuses)]
        (self.graphs / f"{gid}.json").write_text(json.dumps({"id": gid, "round": n, "created": fleet_ctl._now(),
                                                             "nodes": nodes}), encoding="utf-8")

    def record(self, n=None):
        return json.loads((self.root / "rounds" / f"R{n or self.N}" / "round.json").read_text(encoding="utf-8"))

    def report(self, n=None):
        p = self.root / "rounds" / f"R{n or self.N}" / "REPORT.md"
        return p.read_text(encoding="utf-8") if p.exists() else None

    def script(self, *steps):
        """호출마다 차례로 (상태, 보고) 또는 그것을 돌려주는 함수(부수 효과용)."""
        it = iter(steps)

        def spawn_call(n, phase, sid, name, text, at, by):
            self.spawned.append({"phase": phase, "sid": sid, "name": name, "text": text})
            st = next(it)
            state, report = st() if callable(st) else st
            # 끝난 세션 폴더를 남긴다 - 진짜 호출처럼 화면·마감·'지금까지' 가 세션 폴더에서 읽는다
            d = self.sroot / sid
            d.mkdir(parents=True)
            (d / "meta.json").write_text(json.dumps({"id": sid, "role": "manager", "round": n, "harness": "claude",
                                                     "label": sid, "started": fleet_ctl._now(), "supervisor_pid": 999999,
                                                     "proc_start": 1, "extra": {"by": by, "phase": phase}}), encoding="utf-8")
            (d / "end.json").write_text(json.dumps({"state": state, "rc": 0, "ended": fleet_ctl._now()}), encoding="utf-8")
            (d / "report.md").write_text(report, encoding="utf-8")
            return state, report
        return spawn_call

    def runner(self, outcome="done"):
        def run(n, gids):
            self.ran.append(list(gids))
            for gid in gids:
                f = self.graphs / f"{gid}.json"
                g = json.loads(f.read_text(encoding="utf-8"))
                for node in g["nodes"]:
                    node["status"] = "done"
                f.write_text(json.dumps(g), encoding="utf-8")
            return outcome(gids) if callable(outcome) else outcome
        return run

    def closer(self, status="DONE"):
        def close():
            (self.root / "rounds" / f"R{self.N}" / "REPORT.md").write_text(f"# R{self.N}\n\n상태: {status}\n", encoding="utf-8")
            return "done", "마감했습니다\nNEXT: CLOSE"
        return close

    def drive(self, *steps, outcome="done", close_only=True):
        return fleet_ctl._drive(self.N, close_only, spawn_call=self.script(*steps), run_graphs=self.runner(outcome),
                                poll=0.01, chain_wait=2)

    def phases(self):
        return [c["phase"] for c in self.record()["calls"]]


class NextLine(unittest.TestCase):
    def test_parse(self):
        p = fleet_ctl.parse_next
        self.assertEqual(p("계획\n\nNEXT: RUN G-001 G-002\n"), {"kind": "RUN", "graphs": ["G-001", "G-002"]})
        self.assertEqual(p("**NEXT: RUN G-001, G-001**"), {"kind": "RUN", "graphs": ["G-001"]})
        self.assertEqual(p("x\n`NEXT: close`"), {"kind": "CLOSE"})
        self.assertEqual(p("NEXT: JUDGE"), {"kind": "JUDGE"})
        self.assertEqual(p("NEXT: STOP 슬롯 장애 - 사람이 봐야 함"), {"kind": "STOP", "why": "슬롯 장애 - 사람이 봐야 함"})
        for bad in ("", "끝", "NEXT: RUN", "NEXT: MAYBE", "NEXT: CLOSE\n그리고 한 줄 더", "NEXT: CLOSEOUT"):
            self.assertIsNone(p(bad), bad)


class Loop(Base):
    """고리 논리 - 이음새를 갈아 끼워 프로세스 없이."""

    def test_plan_run_judge_close(self):
        self.calls_round()
        self.graph("G-001", self.N)
        self.drive(("done", "그래프 G-001 을 만들었습니다\nNEXT: RUN G-001"), ("done", "모두 통과\nNEXT: CLOSE"), self.closer())
        self.assertEqual(self.ran, [["G-001"]])
        rec = self.record()
        self.assertEqual(rec["mode"], "calls")
        self.assertEqual([(c["phase"], c["state"], c["next"]) for c in rec["calls"]],
                         [("plan", "done", "RUN G-001"), ("judge", "done", "CLOSE"), ("close", "done", "CLOSE")])
        self.assertEqual(rec["calls"][0]["session"], f"M-R{self.N}-000001")        # 계획 호출 id 는 런처가 적은 것
        self.assertEqual(rec["session"], rec["calls"][-1]["session"])
        self.assertTrue(all(c["started"] and c["ended"] for c in rec["calls"]))
        self.assertIn("상태: DONE", self.report())
        d = self.root / "rounds" / f"R{self.N}"
        self.assertEqual(sorted(p.name for p in d.glob("brief-*.md")), ["brief-close.md", "brief-judge.md", "brief-plan.md"])
        plan, judge = self.spawned[0]["text"], self.spawned[1]["text"]
        self.assertIn(f"# R{self.N} 호출 plan", plan)
        self.assertIn(f"rounds/R{self.N}", plan)
        self.assertNotIn("지금까지", plan)                                         # 계획 호출에는 붙이지 않는다
        self.assertIn("## 지금까지", judge)
        self.assertIn("### G-001", judge)
        self.assertEqual((d / "brief-judge.md").read_text(encoding="utf-8"), judge)  # 보낸 그대로가 남는다

    def test_a_followup_graph_goes_round_again(self):
        self.calls_round()
        self.graph("G-001", self.N)

        def judge_opens_followup():
            self.graph("G-002", self.N)
            return "done", "검수 결함 2건 - 후속 그래프\nNEXT: RUN G-002"
        self.drive(("done", "NEXT: RUN G-001"), judge_opens_followup, ("done", "NEXT: CLOSE"), self.closer())
        self.assertEqual(self.ran, [["G-001"], ["G-002"]])
        self.assertEqual(self.phases(), ["plan", "judge", "judge", "close"])
        self.assertTrue((self.root / "rounds" / f"R{self.N}" / "brief-judge-2.md").is_file())
        second = self.spawned[2]["text"]
        self.assertLess(second.index("### G-002"), second.index("### G-001"))      # 최신 그래프 먼저
        self.assertIn("검수 결함 2건", "\n".join(ln for ln in second.splitlines() if ln.startswith(">")))  # 앞선 호출의 보고는 인용으로

    def test_a_blocked_run_calls_the_judge(self):
        self.calls_round()
        self.graph("G-001", self.N)
        self.drive(("done", "NEXT: RUN G-001"), ("done", "NEXT: CLOSE"), self.closer(), outcome="blocked")
        self.assertEqual(self.phases(), ["plan", "judge", "close"])
        self.assertIn("실행 결과 `blocked`", self.spawned[1]["text"])          # 판정은 왜 불렸는지 안다

    def test_missing_or_garbled_next_lines_fall_back(self):
        self.calls_round()
        self.graph("G-001", self.N)
        # 계획: NEXT 없음 + 덜 끝난 그래프 있음 -> 돌린다. 판정: 엉뚱한 줄 + 덜 끝난 것 없음 -> 판정 한 번 더 -> 또 엉뚱 -> 마감
        self.drive(("done", "그래프를 만들었습니다"), ("done", "NEXT: MAYBE"), ("done", "음"), self.closer())
        self.assertEqual(self.ran, [["G-001"]])
        self.assertEqual(self.phases(), ["plan", "judge", "judge", "close"])
        self.assertEqual([c["next"] for c in self.record()["calls"]][:3], [None, None, None])

    def test_run_ignores_other_rounds_and_finished_graphs(self):
        self.calls_round()
        self.graph("G-009", self.N - 1)                       # 다른 라운드
        self.graph("G-001", self.N, ("done", "done"))         # 끝난 그래프
        self.graph("G-002", self.N)
        self.drive(("done", "NEXT: RUN G-009 G-001 G-002 G-404"), ("done", "NEXT: CLOSE"), self.closer())
        self.assertEqual(self.ran, [["G-002"]])
        # 하나도 남지 않으면 대체 길로: 덜 끝난 것이 없으니 판정 한 번
        self.N = 6
        self.calls_round()
        self.graph("G-010", self.N - 1)
        self.spawned.clear()
        self.drive(("done", "NEXT: RUN G-010 ../../etc/passwd"), ("done", "NEXT: CLOSE"), self.closer())
        self.assertEqual(self.ran, [["G-002"]])                                   # 더 돈 것이 없다
        self.assertEqual(self.phases(), ["plan", "judge", "close"])

    def test_judge_calls_are_capped(self):
        self.calls_round()
        steps = [("done", "NEXT: RUN G-001")] + [("done", "NEXT: JUDGE")] * 20 + [self.closer()]
        self.graph("G-001", self.N)
        self.drive(*steps)
        ph = self.phases()
        self.assertEqual(ph.count("judge"), fleet_graph.ROUND_GRAPHS_HARD)
        self.assertEqual(ph[-1], "close")

    def test_a_close_is_skipped_when_the_plan_already_reported_nothing_to_do(self):
        self.calls_round()

        def nothing():
            (self.root / "rounds" / f"R{self.N}" / "REPORT.md").write_text("상태: DONE\n할 일 없음\n", encoding="utf-8")
            return "done", "할 일 없음\nNEXT: CLOSE"
        self.drive(nothing)
        self.assertEqual(self.phases(), ["plan"])

    def test_a_failed_call_writes_the_minimal_close_and_the_chain_stops(self):
        self.calls_round()
        fleet_ctl.chain_set(True, None, 3, "test", all_=True)
        self.graph("G-001", self.N)
        with mock.patch.object(fleet_ctl, "launch_round") as lr:
            self.drive(("done", "NEXT: RUN G-001"), ("failed", ""), close_only=False)
        lr.assert_not_called()
        self.assertEqual([(c["phase"], c["state"]) for c in self.record()["calls"]], [("plan", "done"), ("judge", "failed")])
        text = self.report()
        self.assertIn("상태: PARTIAL", text)
        self.assertIn("judge", text)
        st = fleet_ctl.chain_state()
        self.assertEqual((st["on"], st["stopped_kind"]), (False, "report"))

    def test_stop_line_writes_the_minimal_close_with_the_reason_and_stops_the_chain(self):
        self.calls_round()
        fleet_ctl.chain_set(True, None, 3, "test", all_=True)
        self.graph("G-001", self.N)
        with mock.patch.object(fleet_ctl, "launch_round") as lr:
            self.drive(("done", "NEXT: RUN G-001"), ("done", "NEXT: STOP 무료 슬롯이 모두 죽음"), close_only=False)
        lr.assert_not_called()
        self.assertEqual(self.phases(), ["plan", "judge"])
        self.assertIn("무료 슬롯이 모두 죽음", self.report())
        st = fleet_ctl.chain_state()
        self.assertEqual((st["on"], st["stopped_kind"]), (False, "report"))
        self.assertIn("무료 슬롯이 모두 죽음", st["stopped_why"])

    def test_a_done_round_with_chaining_on_steps_the_chain(self):
        self.calls_round()
        fleet_ctl.chain_set(True, None, 3, "test", all_=True)
        self.graph("G-001", self.N)
        with mock.patch.object(fleet_ctl, "chain_step", return_value={"ok": True}) as cs:
            self.drive(("done", "NEXT: RUN G-001"), ("done", "NEXT: CLOSE"), self.closer(), close_only=False)
        cs.assert_called_once_with(self.N)
        # 마감만 보는 구동기는 같은 파일을 보고도 잇지 않는다 - 사람이 도중에 켜 신호를 받았을 때만
        self.N = 6
        self.calls_round()
        with mock.patch.object(fleet_ctl, "chain_step", return_value={"ok": True}) as cs:
            self.drive(("done", "NEXT: CLOSE"), self.closer())
            cs.assert_not_called()
            self.N = 7
            self.calls_round()
            fleet_ctl._CHAIN_ARMED[0] = True
            self.drive(("done", "NEXT: CLOSE"), self.closer())
            cs.assert_called_once_with(7)

    def test_pause_between_calls_stops_driving_without_writing(self):
        self.calls_round()
        self.graph("G-001", self.N)

        def plan_then_paused():
            fleet_ctl.set_mode("paused", "사람")                # 사람이 계획 호출 도중에 일시 중지
            return "done", "NEXT: RUN G-001"
        self.drive(plan_then_paused)
        self.assertEqual(self.ran, [])
        self.assertEqual(self.phases(), ["plan"])
        self.assertIsNone(self.report())                        # 마감은 쓰지 않는다 - '완전 중지' 의 몫
        # 그래프를 돌리던 중에 멈춘 경우도 같다
        self.N = 6
        self.calls_round()
        self.graph("G-002", self.N)
        self.spawned.clear()
        self.drive(("done", "NEXT: RUN G-002"), outcome="halted")
        self.assertEqual(self.phases(), ["plan"])
        self.assertIsNone(self.report())

    def test_a_restarted_driver_continues_from_the_record(self):
        """일시 중지 뒤 '실행' - 구동기를 다시 띄우면 계획을 다시 하지 않고 남은 그래프부터."""
        self.calls_round()
        self.graph("G-001", self.N)

        def plan_then_paused():
            fleet_ctl.set_mode("paused", "사람")
            return "done", "NEXT: RUN G-001"
        self.drive(plan_then_paused)
        out = fleet_ctl.resume("사람")
        self.assertEqual(out["driver"], True)
        self.assertEqual(self.drivers, [(self.N, True)])
        self.assertEqual(out["resumed_graphs"], [])             # 그 라운드의 그래프는 구동기가 돌린다
        self.spawned.clear()
        self.drive(("done", "NEXT: CLOSE"), self.closer())
        self.assertEqual(self.ran, [["G-001"]])
        self.assertEqual(self.phases(), ["plan", "judge", "close"])
        self.assertIsNone(fleet_ctl.resume("사람").get("driver"))  # 보고가 있는 라운드는 다시 띄우지 않는다


class RunGraphs(Base):
    """`_run_round_graphs` - 같은 잠금·검증·틱, 막히면 새 노드를 띄우지 않고 떠 있는 것만 거둔 뒤 판정으로."""

    def test_a_new_failure_stops_spawning_and_returns_blocked(self):
        self.calls_round()
        self.graph("G-001", self.N, ("todo", "todo", "todo"))
        ticks = []

        def step(g, concurrency=None, allow_spawn=None):
            ticks.append(allow_spawn)
            nodes = g["nodes"]
            if len(ticks) == 1:
                nodes[0]["status"], nodes[1]["status"] = "failed", "running"
            elif len(ticks) == 3:
                nodes[1]["status"] = "done"
            return all(n["status"] in fleet_graph.TERMINAL for n in nodes)
        with mock.patch.object(fleet_graph, "step", side_effect=step), \
                mock.patch.object(fleet_graph, "_validate_or_report", return_value=True):
            out = fleet_ctl._run_round_graphs(self.N, ["G-001"], poll=0.01, timeout=5)
        self.assertEqual(out, "blocked")
        self.assertEqual(ticks, [None, False, False])            # 막힌 뒤로는 띄우지 않고 거두기만
        # 이미 막혀 있던 노드는 새 실패가 아니다 - 끝까지 돈다
        self.graph("G-002", self.N, ("failed", "todo"))
        with mock.patch.object(fleet_graph, "step", side_effect=lambda g, **k: [n.update(status="done") for n in g["nodes"]
                                                                              if n["status"] == "todo"] and True), \
                mock.patch.object(fleet_graph, "_validate_or_report", return_value=True):
            self.assertEqual(fleet_ctl._run_round_graphs(self.N, ["G-002"], poll=0.01, timeout=5), "done")

    def test_paused_or_held_graphs(self):
        self.calls_round()
        self.graph("G-001", self.N)
        fleet_ctl.set_mode("paused", "사람")
        with mock.patch.object(fleet_graph, "step") as st, mock.patch.object(fleet_graph, "_validate_or_report", return_value=True):
            self.assertEqual(fleet_ctl._run_round_graphs(self.N, ["G-001"], poll=0.01, timeout=5), "halted")
        st.assert_not_called()
        fleet_ctl.set_mode("running", "test")
        with fleet_graph.graph_lock("G-001", "다른 실행자"):
            # 같은 프로세스의 flock 은 열린 파일마다 따로라 둘째 잠금이 실패한다 - 남이 잡은 그래프는 건너뛴다
            with mock.patch.object(fleet_graph, "step") as st:
                self.assertEqual(fleet_ctl._run_round_graphs(self.N, ["G-001"], poll=0.01, timeout=5), "skipped")
            st.assert_not_called()


class LiveDriver(Base):
    """구동기가 살아 있는 동안(호출 사이)의 함대 상태와 `stop`."""

    def driver_proc(self, n, driver=True, word="_rounddrive"):
        p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)", word])
        self.addCleanup(lambda: (p.kill(), p.wait()))
        _wait(lambda: word in sessions._proc_cmdline(p.pid), 5)
        rec = {"pid": p.pid, "start": sessions.proc_start(p.pid), "round": n, "at": fleet_ctl._now(), "close_only": True}
        if driver:
            rec["driver"] = True
        (self.aimem / "fleet-chain.watch.json").write_text(json.dumps(rec), encoding="utf-8")
        return p

    def plan_done(self, n):
        sid = f"M-R{n}-000001"
        d = self.sroot / sid
        d.mkdir(parents=True)
        (d / "meta.json").write_text(json.dumps({"id": sid, "role": "manager", "round": n, "harness": "claude",
                                                 "label": f"관리자 R{n} ① 계획", "started": "2026-11-13T10:00:00",
                                                 "supervisor_pid": 999999, "proc_start": 1,
                                                 "extra": {"by": "test", "phase": "plan"}}), encoding="utf-8")
        (d / "end.json").write_text(json.dumps({"state": "done", "rc": 0, "ended": "2026-11-13T10:05:00"}), encoding="utf-8")
        fleet_ctl._save_calls(n, [{"phase": "plan", "session": sid, "state": "done", "started": "2026-11-13T10:00:00",
                                   "ended": "2026-11-13T10:05:00", "next": "RUN G-001"}], sid)

    def test_between_calls_the_round_is_in_progress_and_stop_closes_it(self):
        n = self.calls_round()
        self.plan_done(n)
        self.assertIsNone(fleet_ctl.round_in_progress())
        self.assertEqual(fleet_ctl.public_state()["manager"]["state"], "done")
        p = self.driver_proc(n)
        self.assertEqual(fleet_ctl.round_in_progress(), n)
        self.assertEqual(fleet_ctl.active_round(), n)
        self.assertEqual(fleet.current_round(), n)                 # 작업자 실행·`fleet_graph new` 가 적는 라운드
        self.assertFalse(fleet_ctl.round_over())
        st = fleet_ctl.public_state()
        m = st["manager"]
        self.assertEqual((m["state"], m["mode"], m["phase"], m["calls"], m["session"]), ("driving", "calls", "plan", 1, f"M-R{n}-000001"))
        self.assertFalse(st["idle"])
        self.assertFalse(st["can"]["round"])
        self.assertTrue(st["can"]["stop"])
        self.assertFalse(st["can"]["prepare"])
        chk = next(c for c in fleet_ctl.prepare("test")["checks"] if c["name"] == "실행 중인 관리자 없음")
        self.assertFalse(chk["ok"])
        self.assertIn("구동기", chk["detail"])
        self.assertIsNone(fleet_ctl.close_if_unreported(n))        # 구동기가 살아 있으면 마감하지 않는다
        fleet_ctl.set_mode("ready", "test")
        out = fleet_ctl.launch_round("test")
        self.assertFalse(out["ok"])
        self.assertIn("아직 돌고 있습니다", out["error"])
        fleet_ctl.set_mode("running", "test")
        res = fleet_ctl.stop("test")
        self.assertEqual(res["chain_watcher"], p.pid)
        self.assertIsNotNone(p.wait(timeout=5))
        self.assertEqual(res["managers"], [])
        self.assertIn(n, res["closed_rounds"])
        self.assertIn("상태: PARTIAL", self.report(n))
        self.assertIsNone(fleet_ctl.round_in_progress())

    def test_stop_during_a_call(self):
        n = self.calls_round()
        self.plan_done(n)
        sid = f"M-R{n}-000002"
        spec = rt_manager.spec(sid, n, self.root, by="test", workspace=f"rounds/R{n}", phase="judge")
        sessions.spawn(spec, "FAKE: hang\n", self.sroot, env_root=str(self.root))
        calls = self.record()["calls"] + [{"phase": "judge", "session": sid, "state": "launching", "started": fleet_ctl._now(), "ended": None}]
        fleet_ctl._save_calls(n, calls, sid)
        p = self.driver_proc(n)
        self.assertTrue(_wait(lambda: fleet_ctl.manager_running(), 10))
        m = fleet_ctl.public_state()["manager"]
        self.assertEqual((m["state"], m["phase"], m["session"]), ("running", "judge", sid))
        self.assertEqual(sessions.load_meta(self.sroot / sid)["extra"]["phase"], "judge")
        res = fleet_ctl.stop("test")
        self.assertEqual([(x["id"], x["outcome"]) for x in res["managers"]], [(sid, "killed")])
        self.assertEqual(res["chain_watcher"], p.pid)
        self.assertEqual(res["closed_rounds"], [n])
        self.assertIn("관리자 없이 끝남 (killed)", self.report(n))
        self.assertEqual(_ours(self.root), [])

    def test_a_record_that_is_not_a_live_driver_does_not_count(self):
        n = self.calls_round()
        self.driver_proc(n, driver=False)                        # 상주 방식의 감시자 기록 (driver 없음)
        self.assertIsNone(fleet_ctl.round_in_progress())
        self.driver_proc(n, word="_somethingelse")              # 명령줄이 구동기가 아니다
        self.assertIsNone(fleet_ctl.round_in_progress())
        rec = json.loads((self.aimem / "fleet-chain.watch.json").read_text(encoding="utf-8"))
        rec["start"] = 1
        (self.aimem / "fleet-chain.watch.json").write_text(json.dumps(rec), encoding="utf-8")
        self.assertIsNone(fleet_ctl.round_in_progress())        # 시작 시각이 다르다 (pid 재사용)

    def test_chain_switched_on_mid_round_signals_the_driver_instead_of_a_watcher(self):
        n = self.calls_round()
        self.plan_done(n)
        p = self.driver_proc(n)
        with mock.patch.object(fleet_ctl.os, "kill") as kill, mock.patch.object(fleet_ctl, "_end_chain_watcher") as end:
            fleet_ctl.chain_set(True, None, 3, "사람", all_=True)
        kill.assert_called_once_with(p.pid, signal.SIGUSR1)
        end.assert_not_called()
        self.assertEqual(self.watchers, [])


class Launch(Base):
    def test_launch_in_calls_mode_starts_a_driver_not_a_manager(self):
        self.templates()
        fleet_ctl.set_mode("ready", "test")
        out = fleet_ctl.launch_round("test")
        self.assertTrue(out["ok"], out)
        n, sid = out["round"], out["session"]
        self.assertEqual((out["manager_mode"], out["driver"]), ("calls", True))
        self.assertEqual(self.drivers, [(n, True)])                # 이어 달리기가 꺼져 있으면 마감만
        self.assertEqual(self.watchers, [])
        self.assertFalse(self.sroot.exists() and any(self.sroot.iterdir()))   # 관리자는 구동기가 띄운다
        rec = self.record(n)
        self.assertEqual((rec["mode"], rec["calls"], rec["session"], rec["by"]), ("calls", [], sid, "test"))
        self.assertFalse((self.root / "rounds" / f"R{n}" / "brief.md").exists())
        self.assertEqual(fleet_ctl.mode(), "running")
        m = fleet_ctl.public_state()["manager"]
        self.assertEqual((m["state"], m["mode"], m["phase"]), ("launching", "calls", "plan"))
        # 단계 브리프가 없으면 띄우지 않는다
        (self.aimem / "briefs" / "manager-call-judge.md").unlink()
        fleet_ctl.set_mode("ready", "test")
        bad = fleet_ctl.launch_round("test")
        self.assertFalse(bad["ok"])
        self.assertIn("manager-call-judge.md", bad["error"])

    def test_resident_mode_is_untouched(self):
        (self.root / "fleet.toml").write_text(TOML.replace('mode = "calls"', 'mode = "resident"'), encoding="utf-8")
        self.templates()
        (self.aimem / "briefs" / fleet_ctl.STANDARD_BRIEF).write_text("# 상주 R{round}\nFAKE: hang\n", encoding="utf-8")
        fleet_ctl.set_mode("ready", "test")
        out = fleet_ctl.launch_round("test")
        self.assertTrue(out["ok"], out)
        self.assertEqual(self.drivers, [])
        self.assertEqual(self.watchers, [(out["round"], True)])
        rec = self.record(out["round"])
        self.assertNotIn("mode", rec)
        self.assertNotIn("calls", rec)
        self.assertTrue(_wait(lambda: fleet_ctl.manager_running(), 10))
        m = fleet_ctl.public_state()["manager"]
        self.assertEqual(set(m), {"round", "label", "session", "state", "by", "at", "ended", "brief", "workspace", "last_event_at"})
        self.assertNotIn("phase", sessions.load_meta(self.sroot / out["session"])["extra"])
        self.assertEqual(sessions.load_meta(self.sroot / out["session"])["timeout"], rt_manager.MANAGER_TIMEOUT_SEC)
        fleet_ctl.stop("test")


class EndToEnd(Base):
    """진짜(가짜 하네스) 세션으로 한 바퀴: 계획 호출이 그래프 파일을 쓰고 -> 구동기가 작업자 하나를 돌리고 -> 판정 -> 마감."""

    def test_one_round(self):
        node = {"id": "T-1", "title": "작은 일", "slot": "S2", "task": "FAKE: report DONE", "deps": [], "write": [],
                "max_attempts": 1, "status": "todo", "attempts": []}
        g = {"id": "G-001", "round": "@R@", "created": "2026-11-13T00:00:00", "concurrency": 1, "nodes": [node]}
        gline = json.dumps(g, ensure_ascii=False).replace('"@R@"', "{round}")
        self.templates(
            plan=f"FAKE: write .aimem/graph/G-001.json {gline}\nFAKE: report 그래프 G-001 을 만들었습니다\\nNEXT: RUN G-001\n",
            judge="FAKE: report T-1 통과\\nNEXT: CLOSE\n",
            close="FAKE: write rounds/R{round}/REPORT.md # R{round}\\n\\n상태: DONE\\n\nFAKE: report 마감\\nNEXT: CLOSE\n")
        fleet_ctl.set_mode("ready", "test")
        out = fleet_ctl.launch_round("test")
        self.assertTrue(out["ok"], out)
        n = out["round"]
        self.N = n
        fleet_ctl._drive(n, True, poll=0.1)                        # 구동기 본체를 이 프로세스에서
        rec = self.record(n)
        self.assertEqual([(c["phase"], c["state"], c["next"]) for c in rec["calls"]],
                         [("plan", "done", "RUN G-001"), ("judge", "done", "CLOSE"), ("close", "done", "CLOSE")], rec)
        self.assertEqual(rec["calls"][0]["session"], out["session"])
        g = json.loads((self.graphs / "G-001.json").read_text(encoding="utf-8"))
        self.assertEqual(g["nodes"][0]["status"], "done")
        self.assertIn("상태: DONE", self.report(n))
        phases = {sessions.load_meta(self.sroot / c["session"])["extra"]["phase"] for c in rec["calls"]}
        self.assertEqual(phases, {"plan", "judge", "close"})
        for c in rec["calls"]:
            meta = sessions.load_meta(self.sroot / c["session"])
            self.assertEqual((meta["role"], meta["round"], meta["tools"], meta["timeout"]),
                             ("manager", n, rt_manager.MANAGER_TOOLS, rt_manager.CALL_TIMEOUT_SEC))
        worker = g["nodes"][0]["attempts"][-1]["run_id"]
        self.assertEqual((fleet._run_meta(worker) or {}).get("round"), n)   # 호출 사이에 띄운 작업자도 이 라운드
        judge = (self.root / "rounds" / f"R{n}" / "brief-judge.md").read_text(encoding="utf-8")
        self.assertIn("**T-1** 작은 일 · S2 · done · 시도 1", judge)
        self.assertIn("> DONE", judge)
        m = fleet_ctl.public_state()["manager"]
        self.assertEqual((m["state"], m["phase"], m["calls"]), ("done", "close", 3))
        self.assertIsNone(fleet_ctl.close_if_unreported(n))
        self.assertEqual(_ours(self.root), [])


if __name__ == "__main__":
    unittest.main()
