"""운영 방식 (2026-11-13) - 라운드마다 관리자가 슬롯을 어떻게 쓰나: cost(무료 중심) · quality(품질 중심) · speed(빠른 구현).

엔진의 배정은 같고 관리자에게 주는 지시 한 덩이만 다르다. 지시 틀은 `.aimem/briefs/policy-<키>.md` 이고 검사는 임시 폴더에
제 것을 만든다. 진짜 하네스는 띄우지 않는다(`_fleet_env` 가 AIFLEET_HARNESS=fake). 감시자·구동기 배경 프로세스도 띄우지 않는다
(갈아 끼운 `fleet.ROOT` 를 모르고 운영 저장소를 보기 때문 - `test_rt_manager` 와 같은 까닭).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _fleet_env  # noqa: F401,E402

import contextlib
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
from fleet_rt import config as rt_config  # noqa: E402
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
providers = ["anthropic"]
default_model = "sonnet"

[harness.codex]
providers = ["ok"]
default_model = "ok/x"
"""


def setUpModule():
    global BASE
    BASE = pathlib.Path(tempfile.mkdtemp(prefix="rt-policy-"))


def _ours(prefix):
    out = []
    for p in sessions._live_pids():
        env = sessions._proc_environ(p)
        if env and str(env.get(ENV_ROOT, "")).startswith(str(prefix) + os.sep) and sessions._proc_state(p) not in (None, "Z"):
            out.append(p)
    return out


def tearDownModule():
    for p in _ours(BASE):
        try:
            os.kill(p, signal.SIGKILL)
        except OSError:
            pass
    shutil.rmtree(BASE, ignore_errors=True)


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
        self.root = BASE / f"t{_N[0]}"
        self.aimem = self.root / ".aimem"
        self.briefs = self.aimem / "briefs"
        self.briefs.mkdir(parents=True)
        (self.root / "fleet.toml").write_text(TOML, encoding="utf-8")
        self.sroot = self.aimem / "sessions"
        self.graphs = self.aimem / "graph"
        self.graphs.mkdir()
        self.watchers = []
        patches = [
            mock.patch.object(fleet, "ROOT", self.root),
            mock.patch.object(fleet, "RUNS", self.aimem / "runs"),
            mock.patch.object(fleet_graph, "ROOT", self.root),
            mock.patch.object(fleet_graph, "GRAPHS", self.graphs),
            mock.patch.object(fleet_graph, "_LOGGED_ONCE", set()),
            mock.patch.object(fleet, "roster", return_value={"S2": ("bbbbbb", "codex", "")}),
            mock.patch.object(fleet, "_slot_model", return_value="ok/x"),
            mock.patch.object(fleet, "read_rev", return_value=7),
            mock.patch.object(fleet, "db_state", return_value=None),
            mock.patch.object(fleet, "owned_paths", return_value=[]),
            mock.patch.object(fleet_ctl, "_rev_lint_checks", return_value=[]),
            mock.patch.object(fleet_ctl, "_start_watcher",
                              side_effect=lambda n, close_only=False: self.watchers.append((n, close_only)) or True),
            mock.patch.dict(os.environ, {fleet_ctl.FORCE_ENV: ""}),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self._reap)
        # 표준 브리프: 가짜 하네스가 할 일 없이 바로 끝난다 (FAKE 줄 없음)
        (self.briefs / fleet_ctl.STANDARD_BRIEF).write_text("# 관리자 R{round} 표준 브리프\n", encoding="utf-8")

    def _reap(self):
        try:
            for sid in sessions.list_ids(self.sroot):
                if sessions.state(self.sroot / sid)["state"] == "running":
                    sessions.cancel(self.sroot / sid, "검사 정리")
        except Exception:  # noqa: BLE001
            pass
        _wait(lambda: not _ours(self.root), 5)
        for p in _ours(self.root):
            try:
                os.kill(p, signal.SIGKILL)
            except OSError:
                pass

    def policies(self, *keys):
        for k in keys:
            (self.briefs / f"policy-{k}.md").write_text(
                f"## 운영 방식 {k}\nR{{round}} · {{date}} · REV {{rev}} · {{workspace}} 에서 {k} 로 슬롯을 씁니다.\n", encoding="utf-8")

    def record(self, n):
        return json.loads((self.root / "rounds" / f"R{n}" / "round.json").read_text(encoding="utf-8"))

    def launch(self, policy=None):
        fleet_ctl.set_mode("ready", "test")
        return fleet_ctl.launch_round("test", policy=policy)


class Resident(Base):
    def test_default_is_cost_and_runs_without_a_policy_file(self):
        """cost 지시 파일이 없으면 덧붙임 없이 뜬다 - 운영 방식이 생기기 전과 같다."""
        out = self.launch()
        self.assertTrue(out["ok"], out)
        self.assertEqual(out["policy"], "cost")
        n = out["round"]
        self.assertEqual(self.record(n)["policy"], "cost")
        self.assertFalse((self.root / "rounds" / f"R{n}" / "policy.md").exists())
        sent = (self.sroot / out["session"] / "brief.md").read_text(encoding="utf-8")
        self.assertEqual(sent, (self.root / "rounds" / f"R{n}" / "brief.md").read_text(encoding="utf-8"))

    def test_each_policy_is_frozen_recorded_and_sent(self):
        self.policies("cost", "quality", "speed")
        for key in rt_config.POLICIES:
            with self.subTest(key=key):
                out = self.launch(key)
                self.assertTrue(out["ok"], out)
                n, sid = out["round"], out["session"]
                d = self.root / "rounds" / f"R{n}"
                self.assertEqual(self.record(n)["policy"], key)
                frozen = (d / "policy.md").read_text(encoding="utf-8")
                self.assertIn(f"## 운영 방식 {key}", frozen)
                self.assertIn(f"R{n} · ", frozen)
                self.assertIn(f"REV 7 · rounds/R{n} 에서", frozen)
                self.assertNotIn("{", frozen)                                  # 자리표시가 다 찼다
                brief = (d / "brief.md").read_text(encoding="utf-8")
                self.assertNotIn("운영 방식", brief)                           # 표준 브리프를 굳힌 파일은 그대로
                sent = (self.sroot / sid / "brief.md").read_text(encoding="utf-8")
                self.assertEqual(sent, brief.rstrip("\n") + "\n\n" + frozen)   # 보낸 글 = 브리프 + 지시
                self.assertEqual(fleet_ctl.public_state()["manager"]["policy"], key)
                self.assertTrue(_wait(lambda: sessions.state(self.sroot / sid)["state"] != "running", 10))
                fleet_ctl.stop("test")

    def test_an_unknown_policy_is_refused_without_side_effects(self):
        fleet_ctl.set_mode("ready", "test")
        before = fleet_ctl.read_mode()
        for bad in ("fast", "", 3, ["cost"]):
            out = fleet_ctl.launch_round("test", policy=bad)
            self.assertFalse(out["ok"])
            self.assertIn("운영 방식", out["error"])
        self.assertFalse((self.root / "rounds").exists())
        self.assertFalse(self.sroot.exists())
        self.assertEqual(fleet_ctl.read_mode(), before)
        self.assertEqual(self.watchers, [])

    def test_a_missing_policy_file_is_refused(self):
        self.policies("speed")
        fleet_ctl.set_mode("ready", "test")
        out = fleet_ctl.launch_round("test", policy="quality")
        self.assertFalse(out["ok"])
        self.assertIn(".aimem/briefs/policy-quality.md", out["error"])
        self.assertFalse((self.root / "rounds").exists())
        self.assertFalse(self.sroot.exists())
        self.assertEqual(fleet_ctl.mode(), "ready")

    def test_config_default_is_used(self):
        self.policies("speed")
        (self.root / "fleet.toml").write_text(TOML + '\n[policy]\ndefault = "speed"\n', encoding="utf-8")
        out = self.launch()
        self.assertTrue(out["ok"], out)
        self.assertEqual(self.record(out["round"])["policy"], "speed")

    def test_public_state_and_status(self):
        st = fleet_ctl.public_state()["policy"]
        self.assertEqual(st, {"current": None, "default": "cost", "chain": None, "choices": fleet_ctl.POLICY_CHOICES})
        self.assertEqual([c["key"] for c in fleet_ctl.POLICY_CHOICES], list(rt_config.POLICIES))
        self.assertEqual([c["label"] for c in fleet_ctl.POLICY_CHOICES], ["무료 중심", "품질 중심", "빠른 구현"])
        self.assertTrue(all(set(c) == {"key", "label", "desc"} and c["desc"] for c in fleet_ctl.POLICY_CHOICES))
        self.policies("quality")
        out = self.launch("quality")
        self.assertTrue(out["ok"], out)
        st = fleet_ctl.public_state()
        self.assertEqual(st["policy"]["current"], "quality")
        self.assertEqual(st["manager"]["policy"], "quality")
        self.assertEqual(fleet_ctl.status()["policy"]["current"], "quality")
        # 기록을 고쳐 모르는 키를 심어도 화면에는 내보내지 않는다
        f = self.root / "rounds" / f"R{out['round']}" / "round.json"
        rec = json.loads(f.read_text(encoding="utf-8"))
        f.write_text(json.dumps({**rec, "policy": "<script>"}), encoding="utf-8")
        self.assertIsNone(fleet_ctl.public_state()["policy"]["current"])
        self.assertIsNone(fleet_ctl.public_state()["manager"]["policy"])


class Chain(Base):
    def test_chain_stores_its_policy_and_keeps_it(self):
        self.policies("quality", "speed")
        out = fleet_ctl.chain_set(True, max_rounds=2, by="test", fleet_on=True, policy="quality")
        self.assertTrue(out["ok"], out)
        self.assertEqual(fleet_ctl.chain_state()["policy"], "quality")
        self.assertEqual(fleet_ctl.public_state()["policy"]["chain"], "quality")
        fleet_ctl.chain_set(True, max_rounds=2, by="test", fleet_on=True)          # 안 주면 지금 것을 그대로
        self.assertEqual(fleet_ctl.chain_state()["policy"], "quality")
        bad = fleet_ctl.chain_set(True, max_rounds=2, by="test", fleet_on=True, policy="fast")
        self.assertFalse(bad["ok"])
        self.assertEqual(fleet_ctl.chain_state()["policy"], "quality")             # 거절은 상태를 건드리지 않는다
        (self.briefs / "policy-quality.md").unlink()
        self.assertFalse(fleet_ctl.chain_set(True, by="test", fleet_on=True, policy="quality")["ok"])   # 파일 없음 - 켤 때 거절

    def test_a_fresh_chain_takes_the_config_default(self):
        fleet_ctl.chain_set(True, by="test", fleet_on=True)
        self.assertEqual(fleet_ctl.chain_state()["policy"], "cost")

    def test_chain_step_launches_with_the_chain_policy(self):
        self.policies("speed")
        fleet_ctl.chain_set(True, max_rounds=3, by="test", fleet_on=True, policy="speed")
        decide = {"action": "launch", "why": "남은 일", "goals": {}, "requests": ["Q-1"], "done": 0, "total": 0, "queue": 0}
        fleet_ctl.set_mode("ready", "test")
        with mock.patch.object(fleet_ctl, "chain_decide", return_value=decide):
            res = fleet_ctl.chain_step(1)
        self.assertTrue(res["launched"], res)
        self.assertEqual(self.record(res["round"])["policy"], "speed")
        self.assertIn("운영 방식 speed", (self.root / "rounds" / f"R{res['round']}" / "policy.md").read_text(encoding="utf-8"))

    def test_an_old_chain_state_without_a_policy_launches_with_the_default(self):
        fleet_ctl.chain_set(True, by="test", fleet_on=True)
        st = fleet_ctl.chain_state()
        st.pop("policy")
        fleet_ctl._chain_write(st)
        with mock.patch.object(fleet_ctl, "chain_decide", return_value={"action": "launch", "why": "x", "goals": {}, "done": 0}), \
                mock.patch.object(fleet_ctl, "launch_round", return_value={"ok": True, "round": 2}) as lr:
            fleet_ctl.chain_step(1)
        lr.assert_called_once_with("이어 달리기", policy=None)


class Switch(Base):
    """도는 라운드의 운영 방식을 지금 바꾸기 - 멈추고, 끝나지 않은 그래프를 버리고, 새 방식으로 다시 띄운다."""

    def running_round(self, policy):
        (self.briefs / fleet_ctl.STANDARD_BRIEF).write_text("# 관리자 R{round} 표준 브리프\nFAKE: hang\n", encoding="utf-8")
        env = self.root / ".env"                      # 바꾸기는 준비 점검을 거친다 - 점검이 키 파일을 본다
        env.write_text("X=1\n", encoding="utf-8")
        env.chmod(0o600)
        out = self.launch(policy)
        self.assertTrue(out["ok"], out)
        self.assertTrue(_wait(lambda: sessions.state(self.sroot / out["session"])["state"] == "running", 10))
        return out

    def graph(self, gid="G-1"):
        node = lambda i, st: {"id": f"T-{i}", "title": "t", "slot": "S2", "task": "x", "deps": [], "write": [],  # noqa: E731
                              "max_attempts": 1, "status": st, "attempts": []}
        g = {"id": gid, "concurrency": 2, "nodes": [node(1, "done"), node(2, "todo"), dict(node(3, "todo"), waiting="slot:S2")]}
        (self.graphs / f"{gid}.json").write_text(json.dumps(g), encoding="utf-8")

    def test_switch_stops_drops_and_relaunches_with_the_new_policy(self):
        self.policies("cost", "speed")
        old = self.running_round("speed")
        self.graph()
        self.assertTrue(fleet_ctl.public_state()["can"]["switch"])
        out = fleet_ctl.switch_policy("cost", "태석")
        self.assertTrue(out["ok"], out)
        self.assertEqual((out["old_round"], out["old_policy"], out["policy"]), (old["round"], "speed", "cost"))
        self.assertGreater(out["round"], old["round"])
        self.assertNotEqual(sessions.state(self.sroot / old["session"])["state"], "running")     # 앞 관리자는 끊겼다
        self.assertEqual(self.record(out["round"])["policy"], "cost")
        self.assertEqual(fleet_ctl.mode(), "running")
        # 그래프: 끝난 노드는 그대로, 남은 노드는 버림(blocked + dropped), 더는 이어 돌릴 것으로 보이지 않는다
        g = json.loads((self.graphs / "G-1.json").read_text(encoding="utf-8"))
        self.assertEqual([n["status"] for n in g["nodes"]], ["done", "blocked", "blocked"])
        self.assertIn("운영 방식 변경 (빠른 구현 → 무료 중심, 태석)", g["nodes"][1]["dropped"])
        self.assertNotIn("dropped", g["nodes"][0])
        self.assertNotIn("waiting", g["nodes"][2])
        self.assertEqual(out["dropped_graphs"], [{"graph": "G-1", "nodes": ["T-2", "T-3"]}])
        self.assertFalse(any(x["unfinished"] for x in fleet_ctl.graphs_overview()))
        self.assertIn("drop T-2, T-3", (self.graphs / "G-1.log").read_text(encoding="utf-8"))
        # 새 관리자에게 남긴 말
        inbox = (self.root / "rounds" / f"R{out['round']}" / "INBOX.md").read_text(encoding="utf-8")
        self.assertIn("G-1 는 버렸습니다", inbox)
        self.assertIn("그래프를 새로 짜십시오", inbox)
        self.assertEqual(fleet_ctl.chain_state().get("on", False), False)          # 꺼져 있던 이어 달리기는 켜지 않는다
        self.assertEqual(self.watchers[-1], (out["round"], True))

    def test_a_running_chain_carries_on_with_the_new_policy(self):
        self.policies("quality", "speed")
        fleet_ctl.chain_set(True, max_rounds=3, by="test", fleet_on=True, autonomous=True, policy="speed")
        st = dict(fleet_ctl.chain_state(), rounds_done=2, total_rounds=5, cycles=1)
        fleet_ctl._chain_write(st)
        old = self.running_round("speed")
        out = fleet_ctl.switch_policy("quality", "태석")
        self.assertTrue(out["ok"], out)
        st = fleet_ctl.chain_state()
        self.assertEqual((st["on"], st["policy"], st["autonomous"]), (True, "quality", True))
        self.assertEqual((st["rounds_done"], st["total_rounds"], st["cycles"]), (2, 5, 1))   # 세던 수는 그대로
        self.assertIsNone(st.get("stopped_kind"))
        self.assertIn(f"R{old['round']} 을 멈추고 운영 방식을 바꿔 다시 띄움", st["log"][-1])
        self.assertEqual(self.watchers[-1], (out["round"], False))                 # 이어 달리기 감시자로 뜬다
        self.assertEqual(fleet_ctl.public_state()["policy"]["chain"], "quality")

    def test_nothing_is_stopped_when_a_relaunch_is_known_to_fail(self):
        """멈추기 전에 볼 수 있는 것(키 파일·브리프·라운드 번호)이 어긋나면 도는 라운드를 건드리지 않는다."""
        self.policies("cost", "speed")
        old = self.running_round("speed")
        self.graph()
        before = (self.graphs / "G-1.json").read_text(encoding="utf-8")
        alive = lambda: sessions.state(self.sroot / old["session"])["state"] == "running"  # noqa: E731
        out = fleet_ctl.switch_policy("cost", "t", expect_round=old["round"] + 1)         # 확인창이 말한 라운드가 아니다
        self.assertIn(f"지금 도는 것은 R{old['round']} 입니다", out["error"])
        (self.root / ".env").unlink()
        out = fleet_ctl.switch_policy("cost", "t")
        self.assertIn(f"다시 띄울 수 없어 R{old['round']} 을 멈추지 않았습니다: 키 파일 .env", out["error"])
        (self.root / ".env").write_text("X=1\n", encoding="utf-8")
        (self.root / ".env").chmod(0o600)
        (self.briefs / fleet_ctl.STANDARD_BRIEF).rename(self.briefs / "b.md")
        self.assertIn("다음 라운드 브리프 없음", fleet_ctl.switch_policy("cost", "t")["error"])
        self.assertTrue(alive())
        self.assertEqual((self.graphs / "G-1.json").read_text(encoding="utf-8"), before)
        self.assertEqual(fleet_ctl.mode(), "running")

    def test_other_controls_are_refused_while_a_switch_is_under_way(self):
        """바꾸는 동안의 완전 중지·라운드 실행·이어 달리기 끄기는 거절된다 - 무시되거나 뒤집히지 않게."""
        self.policies("cost", "speed")
        fleet_ctl.chain_set(True, by="test", fleet_on=True, policy="speed")
        self.running_round("speed")
        import fcntl  # noqa: PLC0415
        with open(self.aimem / "fleet-switch.lock", "a") as other:      # 다른 프로세스가 바꾸는 중
            fcntl.flock(other, fcntl.LOCK_EX)
            self.assertTrue(fleet_ctl.switching())
            for call in (lambda: fleet_ctl.stop("t"), lambda: fleet_ctl.pause("t"), lambda: fleet_ctl.resume("t"), lambda: fleet_ctl.prepare("t"),
                         lambda: fleet_ctl.launch_round("t"), lambda: fleet_ctl.chain_set(False, by="t"),
                         lambda: fleet_ctl.chain_policy("cost", "t"), lambda: fleet_ctl.switch_policy("cost", "t")):
                out = call()
                self.assertEqual((out["ok"], out["error"]), (False, fleet_ctl.SWITCHING_ERROR))
            st = fleet_ctl.public_state()
            self.assertTrue(st["switching"])
            self.assertFalse(any(st["can"].values()))
            self.assertEqual((fleet_ctl.mode(), fleet_ctl.chain_state()["on"]), ("running", True))
        self.assertFalse(fleet_ctl.switching())
        self.assertFalse(fleet_ctl.public_state()["switching"])
        self.assertTrue(fleet_ctl.stop("t")["ok"])

    def test_only_this_rounds_graphs_are_dropped_and_dropped_nodes_stay_dropped(self):
        self.policies("cost", "speed")
        old = self.running_round("speed")
        n = old["round"]
        node = lambda i, st, deps=(): {"id": f"T-{i}", "title": "t", "slot": "S2", "task": "x", "deps": list(deps), "write": [],  # noqa: E731
                                       "max_attempts": 1, "status": st, "attempts": []}
        failed = dict(node(2, "failed"), verify="true", attempts=[{"run_id": "none", "rc": 0, "verify_rc": 1, "state": "done"}])
        graphs = {"G-1": {"id": "G-1", "round": n, "nodes": [node(1, "done"), failed, node(3, "todo", ["T-1"])]},
                  "G-2": {"id": "G-2", "round": n + 7, "nodes": [node(8, "todo")]},       # 다른 라운드의 것 - 둔다
                  "G-3": {"id": "G-3", "nodes": [node(9, "todo")]}}                       # 라운드 표시 없음 - 버린다
        for gid, g in graphs.items():
            (self.graphs / f"{gid}.json").write_text(json.dumps(g), encoding="utf-8")
        out = fleet_ctl.switch_policy("cost", "t", expect_round=n)
        self.assertTrue(out["ok"], out)
        self.assertEqual(sorted(d["graph"] for d in out["dropped_graphs"]), ["G-1", "G-3"])
        self.assertEqual(json.loads((self.graphs / "G-2.json").read_text(encoding="utf-8"))["nodes"][0]["status"], "todo")
        g = fleet_graph._load("G-1")
        self.assertEqual([x["status"] for x in g["nodes"]], ["done", "failed", "blocked"])
        ok, msg = fleet_graph.reverify(g, "T-2")                   # 앞쪽 노드가 풀려도 버린 노드는 따라 풀리지 않는다
        self.assertTrue(ok, msg)
        self.assertNotIn("T-3", msg)
        self.assertEqual(g["nodes"][2]["status"], "blocked")
        for fn in (lambda: fleet_graph.unblock(g, "T-3"), lambda: fleet_graph.move_node(g, "T-3", "S9")):
            ok, msg = fn()
            self.assertFalse(ok)
            self.assertIn("T-3 는 버린 노드입니다", msg)

    def test_no_launch_when_the_note_for_the_new_manager_cannot_be_written(self):
        self.policies("cost", "speed")
        old = self.running_round("speed")
        nxt = self.root / "rounds" / f"R{old['round'] + 1}"
        nxt.mkdir(parents=True)
        (nxt / "INBOX.md").symlink_to(self.root / "elsewhere.md")
        out = fleet_ctl.switch_policy("cost", "t")
        self.assertFalse(out["ok"])
        self.assertIn(f"R{old['round']} 은 멈췄지만 새 관리자에게 남길 말을 쓰지 못해", out["error"])
        self.assertEqual(len(fleet_ctl.manager_sessions()), 1)
        self.assertFalse((self.root / "elsewhere.md").exists())

    def test_chain_policy_changes_only_the_next_round(self):
        self.policies("quality", "speed")
        self.assertIn("이어 달리기가 꺼져 있습니다", fleet_ctl.chain_policy("quality", "t")["error"])
        fleet_ctl.chain_set(True, max_rounds=3, by="test", fleet_on=True, policy="speed")
        fleet_ctl._chain_write(dict(fleet_ctl.chain_state(), rounds_done=2, total_rounds=5))
        old = self.running_round("speed")
        (self.briefs / "policy-cost.md").write_text("x", encoding="utf-8")
        (self.briefs / "policy-quality.md").rename(self.briefs / "q.md")           # 지시 파일이 없는 방식은 거절
        for bad, msg in (("speed", "이미 빠른 구현"), ("fast", "운영 방식"), ("quality", "policy-quality.md")):
            self.assertIn(msg, fleet_ctl.chain_policy(bad, "t")["error"])
        (self.briefs / "q.md").rename(self.briefs / "policy-quality.md")
        self.assertEqual(fleet_ctl.chain_state()["policy"], "speed")
        out = fleet_ctl.chain_policy("quality", "태석")
        self.assertTrue(out["ok"], out)
        st = fleet_ctl.chain_state()
        self.assertEqual((st["on"], st["policy"], st["rounds_done"], st["total_rounds"]), (True, "quality", 2, 5))
        self.assertIn("다음 라운드부터 운영 방식 빠른 구현 → 품질 중심 (태석)", st["log"][-1])
        self.assertEqual(sessions.state(self.sroot / old["session"])["state"], "running")        # 도는 라운드는 그대로
        self.assertEqual(self.record(old["round"])["policy"], "speed")
        self.assertEqual(fleet_ctl.public_state()["policy"], dict(fleet_ctl.public_state()["policy"], current="speed", chain="quality"))

    def test_refusals_touch_nothing(self):
        self.policies("cost", "speed")
        self.assertIn("돌고 있는 라운드가 없습니다", fleet_ctl.switch_policy("speed", "t")["error"])   # 도는 라운드 없음
        self.assertFalse(fleet_ctl.public_state()["can"]["switch"])
        old = self.running_round("speed")
        self.graph()
        before = (self.graphs / "G-1.json").read_text(encoding="utf-8")
        for bad, msg in (("speed", "이미 빠른 구현"), ("fast", "운영 방식"), ("quality", "policy-quality.md")):
            out = fleet_ctl.switch_policy(bad, "t")
            self.assertFalse(out["ok"])
            self.assertIn(msg, out["error"])
        self.assertEqual(sessions.state(self.sroot / old["session"])["state"], "running")        # 도는 라운드는 그대로
        self.assertEqual((self.graphs / "G-1.json").read_text(encoding="utf-8"), before)
        self.assertEqual(fleet_ctl.mode(), "running")

    def test_a_failed_prepare_leaves_the_fleet_stopped_and_says_so(self):
        self.policies("cost", "speed")
        old = self.running_round("speed")
        failed = {"ok": False, "mode": "stopped", "checks": [{"name": "남은 세션 프로세스 없음", "ok": False, "required": True, "detail": ""}]}
        with mock.patch.object(fleet_ctl, "prepare", return_value=failed):       # 멈춘 뒤에야 알 수 있는 것
            out = fleet_ctl.switch_policy("cost", "t")
        self.assertFalse(out["ok"])
        self.assertIn(f"R{old['round']} 은 멈췄지만 준비 점검에서 막혀", out["error"])
        self.assertIn("남은 세션 프로세스 없음", out["error"])
        self.assertEqual(fleet_ctl.mode(), "stopped")
        self.assertEqual(len(fleet_ctl.manager_sessions()), 1)                                     # 새 관리자는 안 떴다


class FrozenPolicy(Base):
    def test_a_policy_link_planted_in_the_round_folder_is_not_followed(self):
        self.policies("quality")
        out = self.launch("quality")
        n = out["round"]
        p = self.root / "rounds" / f"R{n}" / "policy.md"
        secret = self.root / "secret.txt"
        secret.write_text("비밀", encoding="utf-8")
        p.unlink()
        p.symlink_to(secret)
        self.assertIsNone(fleet_ctl._frozen_policy(n))


class Cli(unittest.TestCase):
    def test_round_and_chain_take_policy(self):
        buf = io.StringIO()
        with mock.patch.object(fleet_ctl, "launch_round", return_value={"ok": True}) as lr, contextlib.redirect_stdout(buf):
            self.assertEqual(fleet_ctl.main(["round", "--policy", "speed", "--by", "t"]), 0)
        lr.assert_called_once_with("t", policy="speed")
        with mock.patch.object(fleet_ctl, "chain_set", return_value={"ok": True}) as cs, contextlib.redirect_stdout(buf):
            self.assertEqual(fleet_ctl.main(["chain", "on", "--fleet", "--policy", "quality"]), 0)
        self.assertEqual(cs.call_args.kwargs["policy"], "quality")
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            fleet_ctl.main(["round", "--policy", "fast"])


if __name__ == "__main__":
    unittest.main()
