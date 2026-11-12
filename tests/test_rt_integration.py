"""엔진 v2 끝에서 끝까지 검사: 그래프 실행기 -> `fleet.cmd_spawn` -> `fleet_rt.sessions.spawn` -> 감독 -> 가짜 하네스.

진짜 하네스는 띄우지 않는다(`_fleet_env` 가 AIFLEET_HARNESS=fake). 모든 상태는 임시 폴더 아래이고
(`fleet.RUNS`·`fleet.ROOT`·`fleet_graph.GRAPHS`·`fleet_graph.ROOT` 를 갈아끼운다), 신호는 이 검사가 띄운 프로세스에만 간다.
마지막에 이 검사의 저장소 표식(AIFLEET_SESSIONS_ROOT)을 단 프로세스가 하나도 남지 않았는지 본다.

공급자: 임시 `fleet.toml` 에 `fk`(침묵 한도 2초)와 `ok`(600초)를 두고 노드의 `model` 로 고른다.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _fleet_env  # noqa: F401,E402

import argparse
import contextlib
import datetime as dt
import io
import json
import pathlib
import shutil
import signal
import tempfile
import time
import unittest
from unittest import mock

import fleet  # noqa: E402
import fleet_ctl  # noqa: E402
import fleet_graph  # noqa: E402
from fleet_rt import harness as rt_harness  # noqa: E402
from fleet_rt import sessions  # noqa: E402
from fleet_rt.base import ENV_ROOT  # noqa: E402

BASE = None
_N = [0]

TOML = """
[providers.fk]
max_concurrent = 3
idle_timeout_sec = 2
models = ["x"]

[providers.ok]
max_concurrent = 3
idle_timeout_sec = 600
models = ["x"]

[harness.codex]
binary = "codex"
providers = ["fk", "ok"]
default_model = "ok/x"
"""


def setUpModule():
    global BASE
    BASE = pathlib.Path(tempfile.mkdtemp(prefix="rt-integ-"))


def _ours(prefix=None):
    """저장소 표식(ENV_ROOT)이 prefix(기본: 이 모듈의 임시 폴더) 아래인, 좀비 아닌 프로세스."""
    prefix = str(prefix or BASE)
    out = []
    for p in sessions._live_pids():
        env = sessions._proc_environ(p)
        if env and str(env.get(ENV_ROOT, "")).startswith(prefix + os.sep) \
                and sessions._proc_state(p) not in (None, "Z"):
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


def _event_pids(d, name):
    """세션 events.jsonl 의 tool 사건 가운데 이름이 name 인 것의 pid 들."""
    out = []
    try:
        lines = (pathlib.Path(d) / "events.jsonl").read_text(encoding="utf-8").splitlines()
    except OSError:
        return out
    for ln in lines:
        _, _, raw = ln.partition("\t")
        try:
            ev = json.loads(raw)
        except ValueError:
            continue
        if isinstance(ev, dict) and ev.get("name") == name and isinstance(ev.get("pid"), int):
            out.append(ev["pid"])
    return out


class Base(unittest.TestCase):
    OWNED = ["out/**"]

    def setUp(self):
        _N[0] += 1
        self.root = BASE / f"t{_N[0]}"
        self.aimem = self.root / ".aimem"
        self.aimem.mkdir(parents=True)
        (self.root / "fleet.toml").write_text(TOML, encoding="utf-8")
        self.graphs = self.aimem / "graph"
        self.sroot = self.aimem / "sessions"
        patches = [
            mock.patch.object(fleet, "ROOT", self.root),
            mock.patch.object(fleet, "RUNS", self.aimem / "runs"),
            mock.patch.object(fleet_graph, "ROOT", self.root),
            mock.patch.object(fleet_graph, "GRAPHS", self.graphs),
            mock.patch.object(fleet_graph, "_LOGGED_ONCE", set()),
            mock.patch.object(fleet, "roster", return_value={"S1": ("aaaaaa", "codex", ""),
                                                             "S2": ("bbbbbb", "codex", "")}),
            mock.patch.object(fleet, "owned_paths", side_effect=lambda slot: list(self.OWNED)),
            mock.patch.object(fleet, "read_rev", return_value=1),
            mock.patch.object(fleet, "db_state", return_value=None),
            mock.patch.object(fleet, "_slot_model", return_value=None),
            mock.patch.object(fleet, "_db_sync", return_value=None),
            mock.patch.dict(os.environ, {fleet_ctl.FORCE_ENV: ""}),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        fleet_ctl.set_mode("running", "test")
        self.addCleanup(self._reap_all)

    def _reap_all(self):
        """이 검사의 저장소에 남은 세션은 끊고, 그래도 남은 프로세스는 죽인다(전부 이 검사가 띄운 것)."""
        try:
            for sid in sessions.list_ids(self.sroot):
                d = self.sroot / sid
                if sessions.state(d)["state"] == "running":
                    sessions.cancel(d, "검사 정리")
        except Exception:  # noqa: BLE001
            pass
        _wait(lambda: not _ours(self.root), 5)         # 끝마무리 중인 감독은 곧 스스로 끝난다
        left = _ours(self.root)
        for p in left:
            try:
                os.kill(p, signal.SIGKILL)
            except OSError:
                pass
        _wait(lambda: not _ours(self.root), 3)
        if left:
            self.fail(f"검사가 끝났는데 프로세스가 남았다: {left}")

    # ---- 도우미
    def node(self, nid, task, slot="S1", write=None, model="ok/x", **kw):
        n = {"id": nid, "title": nid, "slot": slot, "task": task, "deps": [], "write": list(write or []),
             "max_attempts": 1, "model": model, "status": "todo", "attempts": []}
        n.update(kw)
        return n

    def graph(self, nodes, gid="G-901"):
        g = {"id": gid, "request": "integration", "created": dt.datetime.now().isoformat(timespec="seconds"),
             "concurrency": 3, "nodes": nodes}
        fleet_graph._save(g)
        return g

    def drive(self, g, pred, timeout=30.0, tick=0.2):
        """step() 을 pred(g) 가 참이 되거나 그래프가 끝날 때까지 돌린다."""
        end = time.time() + timeout
        while time.time() < end:
            done = fleet_graph.step(g)
            if pred(g):
                return True
            if done:
                return pred(g)
            time.sleep(tick)
        return False

    def reload(self, gid="G-901"):
        return json.loads((self.graphs / f"{gid}.json").read_text(encoding="utf-8"))

    def args(self, task, **kw):
        a = dict(slot="S1", harness=None, model="ok/x", label="adhoc", task_id=None, attempt=1, write=[],
                 task=task, task_file=None, project=None, round=None, timeout=60)
        a.update(kw)
        return argparse.Namespace(**a)

    def spawn(self, task, **kw):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
            fleet.cmd_spawn(self.args(task, **kw))
        return buf.getvalue().strip().splitlines()[-1]

    def sdir(self, rid):
        return self.sroot / rid

    def run_dirs(self):
        return sorted(p.name for p in self.sroot.iterdir()) if self.sroot.is_dir() else []


class IntegrationTests(Base):
    # 1
    def test_success_writes_file_and_reports_done(self):
        g = self.graph([self.node(
            "T-1", "FAKE: write out/a.txt hello\nFAKE: report DONE\\n한 일: a.txt",
            write=["out/a.txt"], verify="grep -q hello out/a.txt")])
        self.assertTrue(self.drive(g, lambda g: g["nodes"][0]["status"] in ("done", "failed", "blocked")))
        n = self.reload()["nodes"][0]
        self.assertEqual(n["status"], "done", n)
        self.assertEqual((self.root / "out" / "a.txt").read_text(encoding="utf-8"), "hello")
        att = n["attempts"][0]
        rid = att["run_id"]
        d = self.sdir(rid)
        for f in ("meta.json", "end.json", "report.md", "events.jsonl", "brief.md"):
            self.assertTrue((d / f).is_file(), f)
        self.assertEqual(sessions.load_meta(d)["harness_effective"], "fake")
        self.assertEqual(sessions.load_end(d)["state"], "done")
        self.assertEqual(fleet._run_state(rid), ("done", 0))
        self.assertTrue(fleet.run_report(rid).startswith("DONE"), fleet.run_report(rid))
        self.assertIn("한 일: a.txt", fleet.run_report(rid))
        self.assertEqual(att["verify_rc"], 0)
        self.assertIn(rid, fleet._list_runs())
        # 지시문 머리말: 슬롯·토큰·작업 폴더
        brief = (d / "brief.md").read_text(encoding="utf-8")
        self.assertIn("SLOT=S1", brief)
        self.assertIn("aaaaaa", brief)
        self.assertIn(str(self.root), brief)
        self.assertFalse(_ours(self.root))

    # 2
    def test_work_failure_then_retry_succeeds(self):
        g = self.graph([self.node("T-1", "FAKE: exit 3", max_attempts=2)])
        n = g["nodes"][0]
        fleet_graph.step(g)
        rid1 = n["attempts"][0]["run_id"]
        self.assertTrue(_wait(lambda: fleet._run_state(rid1)[0] == "done", 15))
        # 거둔 틱이 곧바로 재시도를 띄우므로(같은 틱 3단계) 거두기만 한다 - 그래야 task 를 갈아끼울 수 있다
        fleet_graph.step(g, allow_spawn=False)
        self.assertEqual(n["status"], "todo")
        self.assertEqual(len(n["attempts"]), 1)
        att1 = n["attempts"][0]
        self.assertEqual(att1["rc"], 3)
        self.assertEqual(att1["verify_rc"], -1)
        self.assertEqual(fleet._run_state(att1["run_id"]), ("done", 3))
        # 가짜 하네스는 시도 번호로 갈라지지 못한다 - 노드의 task 를 갈아끼워 재시도가 성공하게 한다
        n["task"] = "FAKE: report DONE\\nretry ok"
        self.assertTrue(self.drive(g, lambda g: n["status"] in ("done", "failed", "blocked")))
        self.assertEqual(n["status"], "done")
        self.assertEqual(len(n["attempts"]), 2)
        brief2 = (self.sdir(n["attempts"][1]["run_id"]) / "brief.md").read_text(encoding="utf-8")
        self.assertIn("[재시도 2/2]", brief2)
        self.assertIn(att1["run_id"], brief2)
        self.assertEqual(sessions.load_meta(self.sdir(n["attempts"][1]["run_id"]))["attempt"], 2)

    # 3
    def test_blocked_report_is_terminal(self):
        g = self.graph([self.node("T-1", "FAKE: report BLOCKED: 키 없음", max_attempts=3)])
        self.assertTrue(self.drive(g, lambda g: g["nodes"][0]["status"] in ("done", "failed", "blocked")))
        n = g["nodes"][0]
        self.assertEqual(n["status"], "blocked")
        self.assertEqual(len(n["attempts"]), 1)
        self.assertEqual(n["attempts"][0]["rc"], 0)
        self.assertTrue(n["attempts"][0]["report"].startswith("BLOCKED"))
        fleet_graph.step(g)
        self.assertEqual(len(self.run_dirs()), 1)     # 재시도 없음

    # 4
    def test_stall_is_infra_requeued_then_blocked_after_three(self):
        # 침묵으로 끊긴 세션은 기반 장애다 - 시도를 쓰지 않고 다시 넣고, INFRA_RETRY_MAX 번 겹치면 failed 가 아니라 blocked
        g = self.graph([self.node("T-1", "FAKE: hang", model="fk/x", max_attempts=1)])
        t0 = time.time()
        self.assertTrue(self.drive(g, lambda g: g["nodes"][0]["status"] in ("done", "failed", "blocked"), timeout=45))
        n = g["nodes"][0]
        self.assertLess(time.time() - t0, 35)
        self.assertEqual(n["status"], "blocked")
        self.assertIs(n.get("infra"), True)
        self.assertEqual(n["attempts"], [])
        self.assertEqual(len(n["infra_attempts"]), fleet_graph.INFRA_RETRY_MAX)
        for att in n["infra_attempts"]:
            d = self.sdir(att["run_id"])
            self.assertEqual(sessions.state(d)["state"], "stalled")
            # 감독이 침묵으로 끊은 세션은 하네스의 신호 종료코드(-15)가 아니라 125 로 보인다 (`fleet._SESSION_RC`)
            self.assertEqual(att["rc"], 125)
            self.assertEqual((att["state"], att["session_state"], att["fail_kind"]), ("done", "stalled", "infra"))
            self.assertEqual(att["provider"], "fk")
            self.assertEqual(sessions.load_meta(d)["idle_timeout"], 2.0)
        self.assertIs(n["infra_attempts"][-1].get("infra"), True)
        saved = self.reload()["nodes"][0]
        self.assertEqual(saved["infra_attempts"][0]["fail_kind"], "infra")
        log = (self.graphs / "G-901.log").read_text(encoding="utf-8")
        self.assertIn("INFRA T-1", log)
        self.assertIn("공급자 fk", log)
        self.assertTrue(_wait(lambda: not _ours(self.root), 5))
        # 사람이 공급자를 확인하고 풀면 장애 횟수를 비우고 다시 뜬다 (시도 횟수는 그대로 0)
        ok, _msg = fleet_graph.unblock(g, "T-1")
        self.assertTrue(ok, _msg)
        self.assertEqual(n["status"], "todo")
        self.assertEqual(fleet_graph._infra_count(n), 0)
        n["task"] = "FAKE: report DONE\\nok"
        self.assertTrue(self.drive(g, lambda g: n["status"] in ("done", "failed", "blocked"), timeout=30))
        self.assertEqual((n["status"], len(n["attempts"])), ("done", 1))

    # 5
    def test_node_timeout_kills_via_cancel(self):
        g = self.graph([self.node("T-1", "FAKE: child 60\nFAKE: sleep 60", timeout_sec=2, max_attempts=1)])
        self.assertTrue(self.drive(g, lambda g: g["nodes"][0]["status"] in ("done", "failed", "blocked"), timeout=30))
        n, att = g["nodes"][0], g["nodes"][0]["attempts"][0]
        self.assertEqual(n["status"], "failed")
        self.assertEqual(att["state"], "timeout")
        self.assertEqual(att["rc"], 124)
        self.assertEqual(att["kill_outcome"], "killed")
        d = self.sdir(att["run_id"])
        self.assertEqual(sessions.state(d)["state"], "killed")
        self.assertIn("그래프 실행기", sessions.load_end(d)["why"])
        child = _event_pids(d, "child")
        self.assertEqual(len(child), 1)
        self.assertTrue(_wait(lambda: _gone(child[0]), 5))
        self.assertTrue(_wait(lambda: not _ours(self.root), 5))

    def test_node_timeout_requeues_when_attempts_remain(self):
        g = self.graph([self.node("T-1", "FAKE: sleep 60", timeout_sec=2, max_attempts=2)])
        n = g["nodes"][0]
        fleet_graph.step(g)
        rid = n["attempts"][0]["run_id"]
        time.sleep(3.5)
        fleet_graph.step(g, allow_spawn=False)       # 한도 넘김 -> cancel -> 재시도 대기(todo)
        self.assertEqual(n["status"], "todo")
        self.assertEqual(len(n["attempts"]), 1)
        self.assertEqual((n["attempts"][0]["state"], n["attempts"][0]["rc"]), ("timeout", 124))
        self.assertEqual(sessions.state(self.sdir(rid))["state"], "killed")
        self.assertTrue(_wait(lambda: not _ours(self.root), 5))
        self.assertEqual(len(self.run_dirs()), 1)
        fleet_graph.step(g)                           # 이제 재시도가 뜬다
        self.assertEqual(n["status"], "running")
        self.assertEqual(len(n["attempts"]), 2)

    # 6
    def test_stop_kills_worker_and_grandchild_and_requeues(self):
        g = self.graph([self.node("T-1", "FAKE: child 60\nFAKE: sleep 60", max_attempts=2)])
        n = g["nodes"][0]
        fleet_graph.step(g)
        rid = n["attempts"][0]["run_id"]
        d = self.sdir(rid)
        child = _wait(lambda: _event_pids(d, "child"))
        self.assertTrue(child)
        meta = sessions.load_meta(d)
        sup = meta["supervisor_pid"]
        self.assertFalse(_gone(child[0]))
        res = fleet_ctl.stop("test")
        self.assertTrue(res["ok"])
        self.assertIn("G-901", res["halted_graphs"])
        self.assertTrue(_wait(lambda: _gone(child[0]) and _gone(sup), 5))
        g2 = self.reload()
        n2 = g2["nodes"][0]
        self.assertEqual(n2["status"], "todo")
        self.assertEqual(n2["attempts"], [])
        self.assertEqual(len(n2["stopped_attempts"]), 1)
        self.assertEqual(n2["stopped_attempts"][0]["run_id"], rid)
        self.assertEqual(n2["stopped_attempts"][0]["state"], "stopped")
        self.assertEqual(sessions.state(d)["state"], "killed")
        self.assertEqual(fleet._run_state(rid), ("lost", None))
        self.assertEqual(fleet_ctl.mode(), "stopped")
        before = self.run_dirs()
        fleet_graph.step(g2)
        self.assertEqual(self.run_dirs(), before)
        self.assertEqual(self.reload()["nodes"][0]["status"], "todo")
        self.assertFalse(_ours(self.root))

    # 6b: 그래프 밖(ADHOC) 실행도 완전 중지가 끝내야 한다
    def test_stop_kills_adhoc_session_outside_any_graph(self):
        # 회귀 검사: `fleet_ctl.running_runs()` 가 옛 `RUNS/*.json` 만 훑던 때에는 그래프에 안 묶인 세션을
        # stop() 이 살려 두었다. 지금은 `fleet._list_runs()` 로 세션도 본다.
        rid = self.spawn("FAKE: sleep 60")
        d = self.sdir(rid)
        sup = sessions.load_meta(d)["supervisor_pid"]
        fleet_ctl.stop("test")
        self.assertTrue(_wait(lambda: _gone(sup), 8), "stop() 이 그래프 밖 세션을 끊지 않았다")

    # 7
    def test_busy_slot_blocks_second_node_until_first_finishes(self):
        g = self.graph([self.node("T-1", "FAKE: sleep 3", slot="S2"),
                        self.node("T-2", "FAKE: report DONE\\nsecond", slot="S2")])
        n1, n2 = g["nodes"]
        fleet_graph.step(g)
        self.assertEqual(n1["status"], "running")
        self.assertEqual(n2["status"], "todo")
        self.assertEqual(len(self.run_dirs()), 1)
        fleet_graph.step(g)
        self.assertEqual(n2["status"], "todo")
        self.assertEqual(len(self.run_dirs()), 1)
        self.assertEqual(fleet_graph._busy_slots(g), {"S2"})
        self.assertTrue(self.drive(g, lambda g: n2["status"] == "done", timeout=30))
        self.assertEqual(n1["status"], "done")
        self.assertEqual(len(self.run_dirs()), 2)
        e1 = sessions.load_end(self.sdir(n1["attempts"][0]["run_id"]))["ended"]
        st2 = sessions.load_meta(self.sdir(n2["attempts"][0]["run_id"]))["started"]
        self.assertLessEqual(e1[:19], st2[:19])        # 둘째는 첫째가 끝난 뒤에 떴다

    def test_other_slot_runs_in_parallel(self):
        g = self.graph([self.node("T-1", "FAKE: sleep 3", slot="S1"), self.node("T-2", "FAKE: sleep 3", slot="S2")])
        fleet_graph.step(g)
        self.assertEqual([n["status"] for n in g["nodes"]], ["running", "running"])
        self.assertEqual(len(self.run_dirs()), 2)

    # 8
    def test_spawn_refused_when_paused(self):
        fleet_ctl.set_mode("paused", "test")
        with self.assertRaises(SystemExit):
            self.spawn("FAKE: emit hi")
        self.assertEqual(self.run_dirs(), [])

    def test_spawn_refused_without_mode_file(self):
        (self.aimem / "fleet-mode.json").unlink()
        with self.assertRaises(SystemExit):
            self.spawn("FAKE: emit hi")
        self.assertEqual(self.run_dirs(), [])

    def test_spawn_refused_for_unowned_write_path(self):
        with self.assertRaises(SystemExit) as cm:
            self.spawn("FAKE: write src/x.py no", write=["src/x.py"])
        self.assertIn("소유", str(cm.exception))
        self.assertEqual(self.run_dirs(), [])
        self.assertFalse((self.root / "src").exists())

    def test_graph_marks_node_failed_when_spawn_refused(self):
        g = self.graph([self.node("T-1", "FAKE: write src/x.py no", write=["src/x.py"])])
        fleet_graph.step(g)
        self.assertEqual(g["nodes"][0]["status"], "failed")
        self.assertEqual(self.run_dirs(), [])

    # 9
    def test_detached_grandchild_is_found_and_reaped_as_orphan(self):
        rid = self.spawn("FAKE: detach-child 60\nFAKE: report DONE\\nok")
        d = self.sdir(rid)
        self.assertTrue(_wait(lambda: sessions.state(d)["state"] == "done", 15))
        pids = _event_pids(d, "detach-child")
        self.assertEqual(len(pids), 1)
        # setsid 로 떨어져 나간 손자도 감독이 끝나기 전에 정리한다 (적대적 검수 6번) - 고아로 남지 않는다
        self.assertTrue(_wait(lambda: _gone(pids[0]), 5))
        self.assertEqual(sessions.find_orphans(self.sroot), [])

    # 10
    def test_cmd_reap_collects_session_whose_supervisor_was_killed(self):
        rid = self.spawn("FAKE: child 60\nFAKE: sleep 60")
        d = self.sdir(rid)
        child = _wait(lambda: _event_pids(d, "child"))
        self.assertTrue(child)
        sup = sessions.load_meta(d)["supervisor_pid"]
        self.assertEqual(fleet._run_state(rid), ("running", None))
        os.kill(sup, signal.SIGKILL)                       # 감독만 - 이 검사가 띄운 pid
        # 감독만 죽고 하네스가 살아 있으면 lost 가 아니라 running(orphaned) 이다 - 슬롯이 비면 안 된다 (검수 3번)
        self.assertTrue(_wait(lambda: sessions.state(d).get("orphaned"), 5))
        self.assertEqual(fleet._run_state(rid), ("running", None))
        self.assertFalse((d / "end.json").exists())
        self.assertFalse(_gone(child[0]))                  # 하네스·손자는 아직 산다
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(fleet.cmd_reap(argparse.Namespace()), 0)
        self.assertIn(f"reaped {rid}", buf.getvalue())
        end = sessions.load_end(d)
        self.assertEqual(end["state"], "killed")
        self.assertTrue(_wait(lambda: _gone(child[0]), 5))
        self.assertTrue(_wait(lambda: not _ours(self.root), 5))
        self.assertEqual(fleet._run_state(rid), ("lost", None))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            fleet.cmd_reap(argparse.Namespace())            # 두 번째는 거둘 것이 없다
        self.assertIn("거둘 lost 실행 없음", buf.getvalue())

    def test_cmd_wait_prints_report(self):
        rid = self.spawn("FAKE: report DONE\\nwaited")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = fleet.cmd_wait(argparse.Namespace(id=[rid], timeout=20, poll=0.1))
        self.assertEqual(rc, 0)
        self.assertIn("DONE", buf.getvalue())
        self.assertIn("waited", buf.getvalue())

    # 11
    def test_fake_harness_is_forced_by_env(self):
        self.assertEqual(os.environ.get("AIFLEET_HARNESS"), "fake")
        for name in ("codex", "claude", "opencode", "fake"):
            self.assertEqual(rt_harness.get(name).name, "fake")
        rid = self.spawn("FAKE: emit hi", harness="claude")
        self.assertEqual(sessions.load_meta(self.sdir(rid))["harness_effective"], "fake")
        self.assertTrue(_wait(lambda: sessions.state(self.sdir(rid))["state"] == "done", 15))



def _gate_toml(ok_max):
    return TOML.replace("[providers.ok]\nmax_concurrent = 3", f"[providers.ok]\nmax_concurrent = {ok_max}")


class FailKindTests(Base):
    """실패의 종류 (설계 5.3): infra 는 시도를 쓰지 않는다, work·timeout 은 쓴다."""

    def setUp(self):
        super().setUp()
        p = mock.patch.object(fleet_graph, "_PROBE_CACHE", {})
        p.start()
        self.addCleanup(p.stop)

    def _reap_one(self, g, n):
        rid = n["attempts"][-1]["run_id"]
        self.assertTrue(_wait(lambda: fleet._run_state(rid)[0] == "done", 15))
        fleet_graph.step(g, allow_spawn=False)
        return rid

    def test_infra_twice_then_success_counts_one_attempt(self):
        # 재접속 오류만 내고 rc 1 - 모델이 한마디도 못 했으니 감독이 fail_kind=infra 로 적는다
        g = self.graph([self.node("T-1", "FAKE: error Reconnecting 1/5\nFAKE: exit 1", max_attempts=2)])
        n = g["nodes"][0]
        for k in (1, 2):
            fleet_graph.step(g)
            self.assertEqual(n["status"], "running")
            rid = self._reap_one(g, n)
            self.assertEqual(sessions.state(self.sdir(rid))["fail_kind"], "infra")
            self.assertEqual(n["status"], "todo")
            self.assertEqual(n["attempts"], [])
            self.assertEqual(len(n["infra_attempts"]), k)
            self.assertEqual(n["infra_attempts"][-1]["fail_kind"], "infra")
            self.assertEqual(n["infra_attempts"][-1]["provider"], "ok")
        n["task"] = "FAKE: report DONE\\nok"
        self.assertTrue(self.drive(g, lambda g: n["status"] in ("done", "failed", "blocked")))
        self.assertEqual(n["status"], "done")
        self.assertEqual(len(n["attempts"]), 1)            # 시도 1/2 로 done
        self.assertIsNone(n["attempts"][0]["fail_kind"])
        self.assertEqual(len(n["infra_attempts"]), 2)
        self.assertNotIn("infra", n)
        # 첫 시도라 재시도 머리말이 붙지 않는다 (기반 장애는 시도가 아니다)
        brief = (self.sdir(n["attempts"][0]["run_id"]) / "brief.md").read_text(encoding="utf-8")
        self.assertNotIn("[재시도", brief)
        self.assertEqual(sessions.load_meta(self.sdir(n["attempts"][0]["run_id"]))["attempt"], 1)
        st = fleet_graph._status_node(self.reload()["nodes"][0])
        self.assertEqual((st["attempts"], st["infra_attempts"], st["fail_kind"]), (1, 2, None))

    def test_work_failure_still_consumes_attempts(self):
        g = self.graph([self.node("T-1", "FAKE: emit 해 봤다\nFAKE: exit 3", max_attempts=2)])
        n = g["nodes"][0]
        self.assertTrue(self.drive(g, lambda g: n["status"] in ("done", "failed", "blocked"), timeout=30))
        self.assertEqual(n["status"], "failed")
        self.assertEqual(len(n["attempts"]), 2)
        self.assertEqual([a["fail_kind"] for a in n["attempts"]], ["work", "work"])
        self.assertNotIn("infra_attempts", n)

    def test_probe_gates_respawn_after_infra(self):
        g = self.graph([self.node("T-1", "FAKE: error timeout\nFAKE: exit 1", max_attempts=1)])
        n = g["nodes"][0]
        fleet_graph.step(g)
        with mock.patch("fleet_rt.providers.probe", return_value=(False, "연결 실패: ConnectionRefusedError")) as pr:
            self._reap_one(g, n)
            self.assertEqual(n["status"], "todo")
            for _ in range(3):
                fleet_graph.step(g)
            self.assertEqual(pr.call_count, 1)                 # 30초 캐시 - 틱마다 두드리지 않는다
        self.assertEqual(n["status"], "todo")
        self.assertEqual(n["waiting"], "probe:ok")
        self.assertEqual(len(self.run_dirs()), 1)              # 다시 띄우지 않았다
        log = (self.graphs / "G-901.log").read_text(encoding="utf-8")
        self.assertEqual(log.count("wait T-1 - probe:ok"), 1)  # 바뀔 때 한 번만
        self.assertEqual(self.reload()["nodes"][0]["waiting"], "probe:ok")
        n["task"] = "FAKE: report DONE\\nok"
        fleet_graph._PROBE_CACHE.clear()                       # 30초가 지난 셈
        with mock.patch("fleet_rt.providers.probe", return_value=(True, "GET /models 401 (응답함)")):
            fleet_graph.step(g)
        self.assertEqual(n["status"], "running")
        self.assertNotIn("waiting", n)
        self.assertTrue(self.drive(g, lambda g: n["status"] == "done"))

    def test_legacy_run_failure_is_work_not_infra(self):
        # 옛 실행(.aimem/runs)은 감독 판정이 없다 - 오늘 규칙(work/timeout/limit) 그대로
        runs = self.aimem / "runs"
        runs.mkdir(parents=True, exist_ok=True)
        (runs / "OLD-1.json").write_text(json.dumps({"slot": "S1", "harness": "codex", "pid": 999999}), encoding="utf-8")
        (runs / "OLD-1.rc").write_text("1\n", encoding="utf-8")
        (runs / "OLD-1.out").write_text("", encoding="utf-8")
        n = self.node("T-1", "x", max_attempts=1, status="running",
                      attempts=[{"run_id": "OLD-1", "started": dt.datetime.now().isoformat(timespec="seconds")}])
        g = self.graph([n])
        fleet_graph.step(g, allow_spawn=False)
        self.assertEqual(n["status"], "failed")
        self.assertEqual(n["attempts"][0]["fail_kind"], "work")
        self.assertNotIn("session_state", n["attempts"][0])
        self.assertNotIn("infra_attempts", n)


class ProviderGateTests(Base):
    """공급자 문지기 (설계 3.5·5.4): 같은 공급자를 쓰는 노드는 `max_concurrent` 를 넘겨 함께 돌지 않는다."""

    def _times(self, n):
        d = self.sdir(n["attempts"][0]["run_id"])
        return sessions.load_meta(d)["started"][:19], sessions.load_end(d)["ended"][:19]

    def test_same_provider_max_one_never_overlaps(self):
        (self.root / "fleet.toml").write_text(_gate_toml(1), encoding="utf-8")
        g = self.graph([self.node("T-1", "FAKE: sleep 2\nFAKE: report DONE\\na", slot="S1"),
                        self.node("T-2", "FAKE: sleep 1\nFAKE: report DONE\\nb", slot="S2")])
        n1, n2 = g["nodes"]
        fleet_graph.step(g)
        self.assertEqual((n1["status"], n2["status"]), ("running", "todo"))
        self.assertEqual(n2["waiting"], "provider:ok")
        self.assertEqual(self.reload()["nodes"][1]["waiting"], "provider:ok")
        self.assertEqual(fleet_graph._status_node(n2)["waiting"], "provider:ok")
        fleet_graph.step(g)
        self.assertEqual(len(self.run_dirs()), 1)
        self.assertTrue(self.drive(g, lambda g: n1["status"] == "done" and n2["status"] == "done", timeout=30))
        self.assertNotIn("waiting", n2)
        s1, e1 = self._times(n1)
        s2, e2 = self._times(n2)
        self.assertLessEqual(e1, s2)                       # 둘째는 첫째가 끝난 뒤에 떴다 - 겹친 순간이 없다
        log = (self.graphs / "G-901.log").read_text(encoding="utf-8")
        self.assertEqual(log.count("wait T-2 - provider:ok"), 1)

    def test_provider_with_room_two_runs_both(self):
        (self.root / "fleet.toml").write_text(_gate_toml(2), encoding="utf-8")
        g = self.graph([self.node("T-1", "FAKE: sleep 2", slot="S1"), self.node("T-2", "FAKE: sleep 2", slot="S2")])
        fleet_graph.step(g)
        self.assertEqual([n["status"] for n in g["nodes"]], ["running", "running"])
        self.assertEqual(fleet_graph._live_scan(g), ({"S1", "S2"}, {"ok": 2}))

    def test_other_provider_is_not_gated(self):
        (self.root / "fleet.toml").write_text(_gate_toml(1), encoding="utf-8")
        g = self.graph([self.node("T-1", "FAKE: sleep 2", slot="S1"),
                        self.node("T-2", "FAKE: sleep 2", slot="S2", model="fk/x")])
        fleet_graph.step(g)
        self.assertEqual([n["status"] for n in g["nodes"]], ["running", "running"])

    def test_outside_session_holds_the_provider_seat(self):
        # 그래프 밖에서 띄운 세션도 공급자 자리를 잡는다 (문지기는 세션 폴더를 센다)
        (self.root / "fleet.toml").write_text(_gate_toml(1), encoding="utf-8")
        self.spawn("FAKE: sleep 3", slot="S2")
        g = self.graph([self.node("T-1", "FAKE: report DONE\\na", slot="S1")])
        fleet_graph.step(g)
        self.assertEqual(g["nodes"][0]["status"], "todo")
        self.assertEqual(g["nodes"][0]["waiting"], "provider:ok")

    def test_more_dependents_go_first(self):
        (self.root / "fleet.toml").write_text(_gate_toml(1), encoding="utf-8")
        g = self.graph([self.node("T-1", "FAKE: sleep 2", slot="S1"),                     # 아무도 안 기다림
                        self.node("T-2", "FAKE: sleep 2", slot="S2"),                     # T-3·T-4 가 기다림
                        self.node("T-3", "FAKE: sleep 1", slot="S1", deps=["T-2"]),
                        self.node("T-4", "FAKE: sleep 1", slot="S1", deps=["T-3"])])
        self.assertEqual(fleet_graph._dependents(g), {"T-1": 0, "T-2": 2, "T-3": 1, "T-4": 0})
        fleet_graph.step(g)
        st = {n["id"]: n["status"] for n in g["nodes"]}
        self.assertEqual((st["T-1"], st["T-2"]), ("todo", "running"))
        self.assertEqual(g["nodes"][0]["waiting"], "provider:ok")


class BoardSyncTests(Base):
    """보드 동기화 (설계 5.8): 태스크 노드의 상태를 임시 `aimem.db` 의 `tasks.status` 에 옮긴다."""

    def setUp(self):
        super().setUp()
        import sqlite3
        import aimem_db
        self.db = self.aimem / "aimem.db"
        con = sqlite3.connect(self.db)
        con.executescript(aimem_db.SCHEMA)
        con.execute("INSERT INTO meta(key,value) VALUES('rev','7')")
        for tid, st in (("T-1", "TODO"), ("T-2", "TODO"), ("T-3", "DONE"), ("T-4", "ASSIGNED")):
            con.execute("INSERT INTO tasks(id,title,slot,status) VALUES(?,?,?,?)", (tid, tid, "S1", st))
        con.commit()
        con.close()

    def board(self):
        import sqlite3
        con = sqlite3.connect(self.db)
        try:
            return dict(con.execute("SELECT id,status FROM tasks").fetchall())
        finally:
            con.close()

    def events(self):
        import sqlite3
        con = sqlite3.connect(self.db)
        try:
            return con.execute("SELECT actor,rev,kind,body FROM events ORDER BY seq").fetchall()
        finally:
            con.close()

    def test_running_done_failed_and_done_kept(self):
        g = self.graph([self.node("T-1", "FAKE: sleep 1\nFAKE: report DONE\\nok", slot="S1"),
                        self.node("T-2", "FAKE: emit 해 봄\nFAKE: exit 3", slot="S2"),
                        self.node("T-3", "FAKE: report DONE\\nagain", slot="S1", deps=["T-1"])])
        fleet_graph.step(g)
        self.assertEqual(self.board(), {"T-1": "IN-PROGRESS", "T-2": "IN-PROGRESS", "T-3": "DONE", "T-4": "ASSIGNED"})
        self.assertTrue(self.drive(g, lambda g: all(n["status"] in fleet_graph.TERMINAL for n in g["nodes"]), timeout=30))
        self.assertEqual([n["status"] for n in g["nodes"]], ["done", "failed", "done"])
        b = self.board()
        self.assertEqual((b["T-1"], b["T-2"]), ("REVIEW", "BLOCKED"))   # done 은 REVIEW - 판정은 관리자
        self.assertEqual(b["T-3"], "DONE")                                # DONE 은 덮지 않는다
        self.assertEqual(b["T-4"], "ASSIGNED")                            # 그래프에 없는 태스크는 그대로
        ev = [e for e in self.events() if e[2] == "task"]
        self.assertIn((fleet_graph.BOARD_ACTOR, 7, "task", "T-1 IN-PROGRESS S1"), ev)
        self.assertIn((fleet_graph.BOARD_ACTOR, 7, "task", "T-1 REVIEW S1"), ev)
        self.assertIn((fleet_graph.BOARD_ACTOR, 7, "task", "T-2 BLOCKED S2"), ev)
        self.assertFalse(any(e[3].startswith("T-3") for e in ev))
        self.assertEqual(len(ev), 4)                                      # 같은 상태는 다시 적지 않는다

    def test_no_task_row_is_not_created_and_non_task_ids_ignored(self):
        g = self.graph([self.node("T-99", "FAKE: report DONE\\nok"), self.node("N1", "FAKE: report DONE\\nok", slot="S2")])
        self.assertTrue(self.drive(g, lambda g: all(n["status"] == "done" for n in g["nodes"])))
        self.assertNotIn("T-99", self.board())
        self.assertEqual(self.events(), [])

    def test_no_db_no_error(self):
        self.db.unlink()
        g = self.graph([self.node("T-1", "FAKE: report DONE\\nok")])
        self.assertTrue(self.drive(g, lambda g: g["nodes"][0]["status"] == "done"))
        self.assertFalse(self.db.exists())                                # 새로 만들지 않는다

    def test_locked_or_broken_db_does_not_break_the_runner(self):
        self.db.write_bytes(b"not a database")
        g = self.graph([self.node("T-1", "FAKE: report DONE\\nok")])
        self.assertTrue(self.drive(g, lambda g: g["nodes"][0]["status"] == "done"))
        log = (self.graphs / "G-901.log").read_text(encoding="utf-8")
        self.assertEqual(log.count("보드 동기화 실패"), 1)                 # 로그는 한 번


if __name__ == "__main__":
    unittest.main()
