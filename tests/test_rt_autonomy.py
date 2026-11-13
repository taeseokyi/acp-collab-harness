"""운영 방식이 실제로 작동하는가 + 관리자의 슬롯 자율성 (2026-11-13).

운영 방식(cost·quality·speed)은 관리자 지시 한 덩이였고 엔진 한도에 눌려 효과가 없었다. 이제 엔진이 지킨다:
  - 공급자 자리는 작업자 자리다(관리자를 세지 않는다)
  - 그래프 동시성 기본값 = 서로 다른 슬롯 수, 동시성이 붙잡으면 `waiting: concurrency:<n>`
  - 관리자가 슬롯을 더한다 - 운영 방식의 수·등급·공급자 자리 안에서만 (`aimem_db.slot_add`)
  - 막힌 노드를 다른 슬롯으로 옮긴다 (`fleet_graph.move_node`), `run --stop-on-block`
  - 공급자가 오래 응답하지 않으면 노드를 막는다 (`PROBE_WAIT_MAX_SEC`)
  - 라운드 끝에 실제 운용(`round.json["metrics"]`)을 남긴다
진짜 하네스는 띄우지 않는다(`_fleet_env` 가 AIFLEET_HARNESS=fake). 모든 상태는 임시 폴더 아래다.
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
import sqlite3
import tempfile
import time
import unittest
from unittest import mock

import aimem_db  # noqa: E402
import fleet  # noqa: E402
import fleet_ctl  # noqa: E402
import fleet_graph  # noqa: E402
from fleet_rt import config as rt_config  # noqa: E402
from fleet_rt import providers as rt_providers  # noqa: E402
from fleet_rt import sessions  # noqa: E402
from fleet_rt.base import ENV_ROLE, ENV_ROOT, ENV_SESSION  # noqa: E402

BASE = None
_N = [0]

TOML = """
[providers.anthropic]
tier = "paid"
max_concurrent = 3
models = ["opus", "sonnet"]

[providers.one]
tier = "free"
max_concurrent = 1
models = ["x"]

[providers.wide]
tier = "free"
max_concurrent = 8
models = ["y"]

[harness.claude]
providers = ["anthropic"]
default_model = "sonnet"

[harness.codex]
providers = ["one", "wide"]
default_model = "one/x"

[harness.opencode]
providers = ["wide"]
default_model = "wide/y"
"""

WORK = "FAKE: sleep {s}\nFAKE: write {w} ok\nFAKE: report DONE\\nok"


def setUpModule():
    global BASE
    BASE = pathlib.Path(tempfile.mkdtemp(prefix="rt-autonomy-"))


def _ours(prefix):
    out = []
    for p in sessions._live_pids():
        env = sessions._proc_environ(p)
        if env and str(env.get(ENV_ROOT, "")).startswith(str(prefix) + os.sep) and sessions._proc_state(p) not in (None, "Z"):
            out.append(p)
    return out


def tearDownModule():
    left = _ours(BASE)
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


def quiet(fn, *a, **kw):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = fn(*a, **kw)
    return rc, out.getvalue(), err.getvalue()


class Base(unittest.TestCase):
    """임시 저장소: fleet.toml · aimem.db(명부·소유) · 브리프. 명부는 DB 가 정본 (`fleet.roster` 를 갈아끼우지 않는다)."""
    SLOTS = ()        # (슬롯, 하네스, 모델)
    TOML = TOML

    def setUp(self):
        _N[0] += 1
        self.root = BASE / f"t{_N[0]}"
        self.aimem = self.root / ".aimem"
        self.briefs = self.aimem / "briefs"
        self.briefs.mkdir(parents=True)
        self.graphs = self.aimem / "graph"
        self.graphs.mkdir()
        self.sroot = self.aimem / "sessions"
        self.db = self.aimem / "aimem.db"
        (self.root / "fleet.toml").write_text(self.TOML, encoding="utf-8")
        patches = [
            mock.patch.object(fleet, "ROOT", self.root),
            mock.patch.object(fleet, "RUNS", self.aimem / "runs"),
            mock.patch.object(fleet, "DB_CACHE_TTL_SEC", 0.0),
            mock.patch.object(fleet_graph, "ROOT", self.root),
            mock.patch.object(fleet_graph, "GRAPHS", self.graphs),
            mock.patch.object(fleet_graph, "_LOGGED_ONCE", set()),
            mock.patch.object(fleet_graph, "_PROBE_CACHE", {}),
            mock.patch.object(aimem_db, "ROOT", self.root),
            mock.patch.object(aimem_db, "DB", self.db),
            mock.patch.object(fleet_ctl, "_rev_lint_checks", return_value=[]),
            mock.patch.object(fleet_ctl, "_start_watcher", return_value=True),
            mock.patch.dict(os.environ, {fleet_ctl.FORCE_ENV: ""}),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self._reap)
        quiet(aimem_db.cmd_init)
        with aimem_db.connect() as con:
            con.execute("INSERT INTO meta(key,value) VALUES('rev','7')")
            con.commit()
        for s, h, m in self.SLOTS:
            aimem_db.slot_add(s, h, m, f"{s} 역할", "", "test")
        (self.briefs / fleet_ctl.STANDARD_BRIEF).write_text("# R{round}\n", encoding="utf-8")

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

    # ---- 도우미
    def own(self, path, slot):
        aimem_db.ownership_set(path, slot, actor="test")

    def manager_env(self, sid):
        return mock.patch.dict(os.environ, {ENV_ROLE: "manager", ENV_SESSION: sid})

    def round_json(self, n, **rec):
        d = self.root / "rounds" / f"R{n}"
        d.mkdir(parents=True, exist_ok=True)
        (d / "round.json").write_text(json.dumps({"round": n, **rec}), encoding="utf-8")

    def record(self, n):
        return json.loads((self.root / "rounds" / f"R{n}" / "round.json").read_text(encoding="utf-8"))

    def new_graph(self, nodes, gid="G-001", concurrency=None):
        f = self.aimem / f"{gid}-nodes.json"
        f.write_text(json.dumps(nodes), encoding="utf-8")
        rc, out, err = quiet(fleet_graph.cmd_new, argparse.Namespace(id=gid, request="t", nodes=str(f),
                                                                     concurrency=concurrency, followup=None))
        self.assertEqual(rc, 0, out + err)
        return fleet_graph._load(gid)

    def node(self, nid, slot, task=None, write=None, **kw):
        w = write if write is not None else [f"out/{nid}.txt"]
        n = {"id": nid, "title": nid, "slot": slot, "task": task or WORK.format(s=2, w=w[0] if w else "out/x.txt"),
             "write": w, "deps": [], "max_attempts": 1}
        n.update(kw)
        return n

    def drive(self, g, pred, timeout=30.0):
        end = time.time() + timeout
        while time.time() < end:
            done = fleet_graph.step(g)
            if pred(g):
                return True
            if done:
                return pred(g)
            time.sleep(0.2)
        return False

    def events(self, kind):
        con = sqlite3.connect(self.db)
        try:
            return [r[0] for r in con.execute("SELECT body FROM events WHERE kind=? ORDER BY seq", (kind,))]
        finally:
            con.close()

    def owner_of(self, path):
        con = sqlite3.connect(self.db)
        try:
            r = con.execute("SELECT owner FROM ownership WHERE path_pattern=?", (path,)).fetchone()
            return r[0] if r else None
        finally:
            con.close()

    def launch_manager(self, policy):
        """살아 있는 가짜 관리자 하나 (60초 잔다). 라운드 기록·운영 방식은 진짜 `launch_round` 가 쓴다."""
        (self.briefs / fleet_ctl.STANDARD_BRIEF).write_text("FAKE: sleep 60\n# R{round}\n", encoding="utf-8")
        for k in rt_config.POLICIES:
            (self.briefs / f"policy-{k}.md").write_text(f"## {k}\n{{slots}}\n남은 {{extra_slots}} · {{slot_tiers}}\n",
                                                         encoding="utf-8")
        fleet_ctl.set_mode("ready", "test")
        out = fleet_ctl.launch_round("test", policy=policy)
        self.assertTrue(out["ok"], out)
        self.assertTrue(_wait(lambda: sessions.state(self.sroot / out["session"])["state"] == "running", 10))
        return out


# ---------------------------------------------------------------- 1. 설정
class ConfigTiers(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="cfg-", dir=BASE))

    def load(self, text):
        d = pathlib.Path(tempfile.mkdtemp(dir=self.tmp))
        (d / "fleet.toml").write_text(text, encoding="utf-8")
        return rt_config.load(d)

    def test_repo_tiers_and_policy_limits(self):
        cfg = rt_config.load(pathlib.Path(__file__).resolve().parent.parent)
        self.assertEqual({p: cfg.tier(p) for p in cfg.providers()},
                         {"kisti": "free", "exaone": "free", "opencode": "free", "anthropic": "paid", "openrouter": "paid"})
        self.assertEqual(cfg.policy("cost"), {"extra_slots": 2, "slot_tiers": ["free"]})
        self.assertEqual(cfg.policy("quality"), {"extra_slots": 2, "slot_tiers": ["free", "paid"]})
        self.assertEqual(cfg.policy("speed"), {"extra_slots": 4, "slot_tiers": ["free", "paid"]})
        self.assertEqual(cfg.policy_default(), "cost")
        self.assertEqual(cfg.slot_tier("codex", None), "free")
        self.assertEqual(cfg.slot_tier("claude", "opus"), "paid")
        self.assertEqual(cfg.slot_tier("codex", "openrouter/deepseek/deepseek-v4.1-flash"), "paid")

    def test_unknown_provider_or_missing_tier_is_paid(self):
        cfg = self.load('[providers.a]\nmodels = ["x"]\n[harness.codex]\nproviders = ["a"]\ndefault_model = "a/x"\n')
        self.assertEqual(cfg.tier("a"), "paid")
        self.assertEqual(cfg.tier("zzz"), "paid")
        self.assertEqual(cfg.tier(None), "paid")
        self.assertEqual(cfg.slot_tier("codex", "mystery"), "paid")
        # [policy.*] 표가 없는 옛 설정은 내장값
        self.assertEqual(cfg.policy("speed"), {"extra_slots": 4, "slot_tiers": ["free", "paid"]})
        self.assertEqual(cfg.policy("bogus"), cfg.policy("cost"))

    def test_validation(self):
        for bad in ('[providers.a]\ntier = "cheap"\n',
                    '[policy.speed]\nextra_slots = -1\n', '[policy.speed]\nextra_slots = "4"\n',
                    '[policy.speed]\nextra_slots = true\n', '[policy.cost]\nslot_tiers = ["free", "gold"]\n',
                    '[policy.cost]\nslot_tiers = "free"\n', '[policy.fast]\nextra_slots = 1\n'):
            with self.assertRaises(rt_config.ConfigError, msg=bad):
                self.load(bad)
        cfg = self.load('[policy]\ndefault = "speed"\n[policy.speed]\nextra_slots = 0\nslot_tiers = []\n')
        self.assertEqual(cfg.policy("speed"), {"extra_slots": 0, "slot_tiers": []})
        self.assertEqual(cfg.policy_default(), "speed")

    def test_model_allowed(self):
        cfg = rt_config.load(pathlib.Path(__file__).resolve().parent.parent)
        ok = [("claude", "opus"), ("claude", "claude-opus-5-5"), ("claude", None), ("codex", "kisti/kistillm"),
              ("opencode", "opencode/deepseek-v4.1-flash-free"), ("codex", "")]
        for h, m in ok:
            self.assertEqual(cfg.model_allowed(h, m), (True, ""), (h, m))
        no = {("claude", "sonet"): "설정된 모델이 아닙니다", ("codex", "anthropic/claude-sonnet"): "받을 수 없습니다",
              ("codex", "opus"): "받을 수 없습니다", ("codex", "opencode/deepseek-v4.1-flash-free"): "가능: opencode",
              ("claude", "kisti/kistillm"): "받을 수 없습니다"}
        for (h, m), why in no.items():
            ok_, msg = cfg.model_allowed(h, m)
            self.assertFalse(ok_, (h, m))
            self.assertIn(why, msg)


# ---------------------------------------------------------------- 2. 공급자 자리는 작업자 자리
class ManagerHoldsNoSeat(Base):
    SLOTS = (("S1", "claude", "sonnet"), ("S2", "claude", "sonnet"), ("S3", "claude", "opus"))

    def test_three_claude_workers_run_beside_a_running_manager(self):
        out = self.launch_manager("speed")
        for i in (1, 2, 3):
            self.own(f"out/T-{i}.txt", f"S{i}")
        g = self.new_graph([self.node(f"T-{i}", f"S{i}") for i in (1, 2, 3)])
        fleet_graph.step(g)
        self.assertEqual([n["status"] for n in g["nodes"]], ["running"] * 3, [n.get("waiting") for n in g["nodes"]])
        busy, by_prov = fleet_graph._live_scan(g)
        self.assertEqual(by_prov, {"anthropic": 3})                     # 관리자(anthropic)는 세지 않았다
        self.assertEqual(sessions.state(self.sroot / out["session"])["state"], "running")
        self.assertTrue(self.drive(g, lambda g: all(n["status"] == "done" for n in g["nodes"])))
        fleet_ctl.stop("test")


# ---------------------------------------------------------------- 3. 동시성
class Concurrency(Base):
    SLOTS = tuple((f"S{i}", "opencode", "wide/y") for i in range(1, 7))

    def setUp(self):
        super().setUp()
        fleet_ctl.set_mode("running", "test")
        for i in range(1, 7):
            self.own(f"out/T-{i}.txt", f"S{i}")

    def test_default_is_distinct_slots_and_all_start_in_one_tick(self):
        g = self.new_graph([self.node(f"T-{i}", f"S{i}") for i in range(1, 7)])
        self.assertEqual(g["concurrency"], 6)
        fleet_graph.step(g)
        self.assertEqual([n["status"] for n in g["nodes"]], ["running"] * 6)
        self.assertTrue(self.drive(g, lambda g: all(n["status"] == "done" for n in g["nodes"])))

    def test_explicit_value_wins_and_the_cap_is_recorded_as_waiting(self):
        g = self.new_graph([self.node(f"T-{i}", f"S{i}") for i in range(1, 7)], concurrency=2)
        self.assertEqual(g["concurrency"], 2)
        fleet_graph.step(g)
        st = [n["status"] for n in g["nodes"]]
        self.assertEqual(st.count("running"), 2)
        waiting = [n.get("waiting") for n in g["nodes"] if n["status"] == "todo"]
        self.assertEqual(waiting, ["concurrency:2"] * 4)
        self.assertTrue(all(n.get("waiting_since") for n in g["nodes"] if n["status"] == "todo"))
        log = (self.graphs / "G-001.log").read_text(encoding="utf-8")
        self.assertIn("wait T-3 - concurrency:2", log)
        self.assertTrue(self.drive(g, lambda g: all(n["status"] == "done" for n in g["nodes"])))
        self.assertFalse(any("waiting" in n or "waiting_since" in n for n in g["nodes"]))

    def test_one_slot_graph_defaults_to_one(self):
        self.assertEqual(fleet_graph.default_concurrency([{"slot": "S1"}, {"slot": "S1"}]), 1)
        self.assertEqual(fleet_graph.default_concurrency([]), 1)
        self.assertEqual(fleet_graph._graph_concurrency({"nodes": [{"slot": "S1"}, {"slot": "S2"}]}), 2)


# ---------------------------------------------------------------- 4. 노드 옮기기 · run --stop-on-block
class Move(Base):
    SLOTS = (("S1", "codex", "one/x"), ("S2", "opencode", "wide/y"), ("S3", "claude", "sonnet"))

    def setUp(self):
        super().setUp()
        fleet_ctl.set_mode("running", "test")
        self.own("out/T-1.txt", "S1")
        self.own("out/T-2.txt", "S1")

    def blocked_graph(self, round_n=None, policy=None):
        if round_n is not None:
            self.round_json(round_n, policy=policy)
        g = self.new_graph([self.node("T-1", "S1", task="FAKE: report BLOCKED\\n공급자가 막힘"),
                            self.node("T-2", "S1", deps=["T-1"])])
        g["round"] = round_n
        fleet_graph._save(g)
        self.assertTrue(self.drive(g, lambda g: g["nodes"][0]["status"] == "blocked"))
        self.assertEqual(g["nodes"][1]["status"], "blocked")             # 의존 실패로 막힘
        return g

    def test_move_to_a_free_slot_moves_ownership_and_finishes(self):
        g = self.blocked_graph()
        n = g["nodes"][0]
        n["task"] = WORK.format(s=0, w="out/T-1.txt")                   # 다른 엔진에서는 된다
        ok, msg = fleet_graph.move_node(g, "T-1", "S2", why="S1 공급자 막힘")
        self.assertTrue(ok, msg)
        self.assertEqual((n["slot"], n["status"], n["max_attempts"]), ("S2", "todo", 2))   # 한 번 더 허용
        self.assertEqual(g["nodes"][1]["status"], "todo")                # 뒤쪽도 풀렸다
        self.assertEqual([(m["from"], m["to"], m["why"]) for m in n["moves"]], [("S1", "S2", "S1 공급자 막힘")])
        self.assertEqual(self.owner_of("out/T-1.txt"), "S2")
        self.assertIn("out/T-1.txt -> S2", self.events("ownership"))
        self.assertEqual(fleet_graph.validate_graph(g, spawnable_only=True), [])
        fleet_graph._save(g)
        self.assertTrue(self.drive(g, lambda g: all(x["status"] == "done" for x in g["nodes"])))
        self.assertEqual((self.root / "out/T-1.txt").read_text(encoding="utf-8").strip(), "ok")

    def test_refusals(self):
        g = self.blocked_graph()
        for args, why in ((("T-9", "S2"), "노드가 없습니다"), (("T-1", "S9"), "명부에 없습니다"),
                          (("T-1", "S1"), "이미 S1")):
            ok, msg = fleet_graph.move_node(g, *args)
            self.assertFalse(ok)
            self.assertIn(why, msg)
        g["nodes"][0]["status"] = "done"
        ok, msg = fleet_graph.move_node(g, "T-1", "S2")
        self.assertFalse(ok)
        self.assertIn("todo/failed/blocked 만", msg)
        g["nodes"][0]["status"] = "blocked"
        with mock.patch.object(fleet, "_run_state", return_value=("running", None)):
            ok, msg = fleet_graph.move_node(g, "T-1", "S2")
        self.assertFalse(ok)
        self.assertIn("아직 살아 있습니다", msg)

    def test_cost_refuses_a_paid_target_and_speed_allows_it(self):
        g = self.blocked_graph(round_n=4, policy="cost")
        self.assertEqual(fleet_graph.round_policy(4), "cost")
        ok, msg = fleet_graph.move_node(g, "T-1", "S3")
        self.assertFalse(ok)
        self.assertIn("운영 방식 cost 에서는 무료 슬롯으로만", msg)
        self.assertIn("유료", msg)
        self.assertEqual(g["nodes"][0]["slot"], "S1")
        self.assertEqual(self.owner_of("out/T-1.txt"), "S1")             # 거절은 아무것도 바꾸지 않는다
        ok, msg = fleet_graph.move_node(g, "T-1", "S3", policy="speed")
        self.assertTrue(ok, msg)
        self.assertEqual(fleet_graph.round_policy(None), "cost")         # 모르면 가장 좁은 쪽
        self.round_json(5, policy="<x>")
        self.assertEqual(fleet_graph.round_policy(5), "cost")

    def test_a_carried_over_graph_follows_the_round_that_runs_it(self):
        """무료 중심 라운드에서 만든 그래프를 빠른 구현 라운드가 돌리면 지금 라운드의 방식을 따른다."""
        import fleet_ctl  # noqa: PLC0415
        g = self.blocked_graph(round_n=4, policy="cost")
        self.round_json(6, policy="speed")
        with mock.patch.object(fleet_ctl, "active_round", return_value=6):
            self.assertEqual(fleet_graph.graph_policy(g), "speed")
            ok, msg = fleet_graph.move_node(g, "T-1", "S3")
        self.assertTrue(ok, msg)
        with mock.patch.object(fleet_ctl, "active_round", return_value=None):      # 도는 관리자가 없으면 만든 라운드의 것
            self.assertEqual(fleet_graph.graph_policy(g), "cost")

    def test_cli_move_takes_the_graph_lock(self):
        self.blocked_graph()
        a = argparse.Namespace(id="G-001", node="T-1", slot="S2", why="")
        with fleet_graph.graph_lock("G-001", "다른 실행자"):
            rc, out, err = quiet(fleet_graph.cmd_move, a)
        self.assertEqual(rc, 2)
        self.assertIn("`run` 이 돌아온 뒤 다시 move", err)
        self.assertEqual(fleet_graph._load("G-001")["nodes"][0]["slot"], "S1")
        rc, out, err = quiet(fleet_graph.cmd_move, a)
        self.assertEqual(rc, 0, err)
        self.assertIn("T-1: S1 → S2", out)
        self.assertEqual(fleet_graph._load("G-001")["nodes"][0]["slot"], "S2")

    def test_no_db_skips_ownership_quietly(self):
        g = self.blocked_graph()
        with mock.patch.object(fleet_graph, "_board_db", return_value=self.aimem / "none.db"):
            ok, msg = fleet_graph.move_node(g, "T-1", "S2")
        self.assertTrue(ok, msg)
        self.assertEqual(self.owner_of("out/T-1.txt"), "S1")

    def run_graph(self, stop=None):
        a = argparse.Namespace(id="G-001", timeout=30, poll=0.1, concurrency=None, stop_on_block=stop)
        return quiet(fleet_graph.cmd_run, a)

    def stop_graph(self, round_n, policy):
        self.round_json(round_n, policy=policy)
        self.own("out/T-3.txt", "S2")
        g = self.new_graph([self.node("T-1", "S1", task="FAKE: sleep 1\nFAKE: report BLOCKED\\n막힘"),
                            self.node("T-2", "S1"),            # 같은 슬롯이라 T-1 뒤에 뜬다 - 띄우기를 멈추면 안 뜬다
                            self.node("T-3", "S2", task=WORK.format(s=2, w="out/T-3.txt"))])
        g["round"] = round_n
        fleet_graph._save(g)

    def test_stop_on_block_returns_early_under_speed(self):
        self.stop_graph(6, "speed")
        rc, out, err = self.run_graph()
        self.assertEqual(rc, 1, out + err)
        self.assertIn("막힌 노드: T-1(blocked, S1)", out)
        self.assertIn("fleet_graph.py move G-001", out)
        st = {n["id"]: n["status"] for n in fleet_graph._load("G-001")["nodes"]}
        self.assertEqual(st, {"T-1": "blocked", "T-2": "todo", "T-3": "done"})   # 떠 있던 T-3 은 거뒀다

    def test_cost_runs_on_and_explicit_flag_wins(self):
        self.stop_graph(6, "cost")
        rc, out, err = self.run_graph()
        self.assertEqual(rc, 1)
        self.assertNotIn("막힌 노드:", out)
        st = {n["id"]: n["status"] for n in fleet_graph._load("G-001")["nodes"]}
        self.assertEqual(st, {"T-1": "blocked", "T-2": "done", "T-3": "done"})

    def test_explicit_flag_overrides_policy(self):
        self.stop_graph(6, "cost")
        rc, out, _ = self.run_graph(stop=True)
        self.assertIn("막힌 노드: T-1", out)
        self.assertEqual(fleet_graph._load("G-001")["nodes"][1]["status"], "todo")

    def test_cli_flags(self):
        with mock.patch.object(sys, "argv", ["fleet_graph.py", "run", "G-001", "--no-stop-on-block"]), \
                mock.patch.object(fleet_graph, "cmd_run", return_value=0) as cr:
            fleet_graph.main()
        self.assertIs(cr.call_args.args[0].stop_on_block, False)
        with mock.patch.object(sys, "argv", ["fleet_graph.py", "move", "G-001", "T-1", "--slot", "S2"]), \
                mock.patch.object(fleet_graph, "cmd_move", return_value=0) as cm:
            fleet_graph.main()
        self.assertEqual((cm.call_args.args[0].node, cm.call_args.args[0].slot), ("T-1", "S2"))


# ---------------------------------------------------------------- 5. 공급자를 한없이 기다리지 않는다
class ProbeWait(Base):
    SLOTS = (("S1", "codex", "one/x"),)

    def test_long_probe_wait_blocks_with_infra_and_unblock_requeues(self):
        fleet_ctl.set_mode("running", "test")
        self.own("out/T-1.txt", "S1")
        g = self.new_graph([self.node("T-1", "S1")])
        n = g["nodes"][0]
        n["infra_attempts"] = [{"run_id": "T-1-S1-a1-000000", "fail_kind": "infra"}]
        with mock.patch("fleet_rt.providers.probe", return_value=(False, "연결 실패: ConnectionRefusedError")):
            fleet_graph.step(g)
            self.assertEqual((n["status"], n["waiting"]), ("todo", "probe:one"))
            self.assertTrue(n["waiting_since"])
            fleet_graph.step(g)
            self.assertEqual(n["status"], "todo")                          # 아직 한도 안
            old = (dt.datetime.now() - dt.timedelta(seconds=fleet_graph.PROBE_WAIT_MAX_SEC + 5)).isoformat(timespec="seconds")
            n["waiting_since"] = old
            fleet_graph._PROBE_CACHE.clear()
            fleet_graph.step(g)
        self.assertEqual(n["status"], "blocked")
        self.assertTrue(n["infra"])
        self.assertNotIn("waiting", n)
        self.assertTrue(n["infra_attempts"][-1]["infra"])
        self.assertEqual(fleet_graph._status_node(n)["note"], "(공급자 장애)")
        log = (self.graphs / "G-001.log").read_text(encoding="utf-8")
        self.assertIn("넘게 응답하지 않아 기다리기를 그만둡니다", log)
        ok, msg = fleet_graph.unblock(g, "T-1")
        self.assertTrue(ok, msg)
        self.assertEqual(n["status"], "todo")


# ---------------------------------------------------------------- 6. 슬롯 자율성 (aimem_db)
class SlotAutonomy(Base):
    SLOTS = (("S1", "claude", "sonnet"), ("S2", "codex", "one/x"))

    def add(self, *a, **kw):
        return aimem_db.slot_add(*a, **kw)

    def test_every_caller_gets_model_validation(self):
        for h, m in (("claude", "sonet"), ("codex", "anthropic/claude-sonnet"), ("codex", "wide/zzz")):
            with self.assertRaises(ValueError, msg=(h, m)) as cm:
                self.add(None, h, m)
            self.assertTrue("모델" in str(cm.exception) or "받을 수 없습니다" in str(cm.exception))
        with self.assertRaises(ValueError):
            aimem_db.slot_set("S2", model="opus")
        with self.assertRaises(ValueError):
            aimem_db.slot_set("S1", harness="codex")                       # 남은 모델 sonnet 은 codex 가 못 받는다
        r = self.add(None, "opencode", "wide/y", "만들기")
        self.assertEqual((r["slot"], r["origin"], r["round"]), ("S3", "owner", None))

    def test_owner_has_no_policy_limits(self):
        for _ in range(5):
            self.add(None, "claude", "opus")
        self.assertEqual(len(aimem_db.slot_list()), 7)

    def test_manager_add_follows_the_round_policy(self):
        self.round_json(9, policy="speed")
        with self.manager_env("M-R9-120000"):
            self.assertEqual(aimem_db.manager_caller(), {"round": 9, "policy": "speed"})
            a = self.add(None, "claude", "opus", "속도 만들기")
            b = self.add(None, "opencode", "wide/y", "만들기")
            with self.assertRaises(ValueError) as cm:
                self.add(None, "codex", "one/x")                            # one 은 동시 1 - S2 가 이미 있다
        self.assertIn("공급자 one 는 동시에 1개까지라 슬롯을 더해도 빨라지지 않습니다", str(cm.exception))
        self.assertEqual((a["origin"], a["round"], b["origin"]), ("manager", 9, "manager"))
        ev = self.events("slot")
        self.assertTrue(any("slot add S3 claude" in e and "관리자 추가 R9, 운영 speed" in e for e in ev), ev)
        rc, out, _ = quiet(aimem_db.cmd_slot, argparse.Namespace(action="list"))
        self.assertIn("[관리자 추가 R9]", out)
        self.assertEqual(out.count("관리자 추가"), 2)

    def test_manager_cap_and_tiers_under_cost(self):
        self.round_json(3, policy="cost")
        with self.manager_env("M-R3-120000"):
            with self.assertRaises(ValueError) as cm:
                self.add(None, "claude", "opus")
            self.assertIn("운영 방식 cost 에서 관리자는 무료 슬롯만 둘 수 있습니다", str(cm.exception))
            self.add(None, "opencode", "wide/y")
            self.add(None, "opencode", "wide/y")
            with self.assertRaises(ValueError) as cm:
                self.add(None, "opencode", "wide/y")
        self.assertIn("관리자가 더할 수 있는 슬롯은 2개이고 이미 2개를 더했습니다 (S3, S4)", str(cm.exception))

    def test_unknown_round_or_policy_is_cost(self):
        with self.manager_env("M-R77-120000"):
            self.assertEqual(aimem_db.manager_caller(), {"round": 77, "policy": "cost"})
        with self.manager_env("weird"):
            self.assertEqual(aimem_db.manager_caller(), {"round": None, "policy": "cost"})
        with mock.patch.dict(os.environ, {ENV_ROLE: "worker", ENV_SESSION: "M-R9-1"}):
            self.assertIsNone(aimem_db.manager_caller())

    def test_manager_set_and_remove_rights(self):
        self.round_json(9, policy="speed")
        with self.manager_env("M-R9-120000"):
            mine = self.add(None, "opencode", "wide/y")["slot"]
            r, ch = aimem_db.slot_set("S1", role="판단", note="검수")               # 역할·비고는 어느 슬롯이든
            self.assertEqual(ch, ["역할", "비고"])
            with self.assertRaises(ValueError) as cm:
                aimem_db.slot_set("S1", model="opus")
            self.assertIn("사람이 둔 슬롯이라 관리자는 하네스·모델을 바꾸지 않습니다", str(cm.exception))
            r, ch = aimem_db.slot_set(mine, harness="claude", model="opus")
            self.assertEqual(r["model"], "opus")
            with self.assertRaises(ValueError) as cm:
                aimem_db.slot_remove("S2")
            self.assertIn("사람이 둔 슬롯이라 관리자는 지우지 않습니다", str(cm.exception))
            aimem_db.slot_remove(mine)
        self.assertEqual([s["slot"] for s in aimem_db.slot_list()], ["S1", "S2"])

    def test_remove_refuses_a_running_worker_for_everyone(self):
        d = self.sroot / "T-1-S2-a1-000000"
        d.mkdir(parents=True)
        pid = _fleet_env.marked_pid(self.sroot, d.name)
        (d / "meta.json").write_text(json.dumps({"id": d.name, "role": "worker", "slot": "S2", "supervisor_pid": pid,
                                                 "proc_start": sessions.proc_start(pid)}), encoding="utf-8")
        with self.assertRaises(ValueError) as cm:
            aimem_db.slot_remove("S2")
        self.assertIn("S2 에 작업자가 돌고 있습니다 (T-1-S2-a1-000000)", str(cm.exception))
        (d / "end.json").write_text(json.dumps({"state": "done", "rc": 0}), encoding="utf-8")
        os.kill(pid, signal.SIGKILL)
        _wait(lambda: sessions.state(d)["state"] != "running", 5)
        aimem_db.slot_remove("S2")

    def test_monitor_reader_passes_the_marker(self):
        self.round_json(9, policy="speed")
        with self.manager_env("M-R9-1"):
            aimem_db.slot_add(None, "opencode", "wide/y")
        from aimem_monitor import reader  # noqa: PLC0415
        slots = {s["slot"]: s for s in reader.collect(self.root)["slots"]}
        self.assertEqual((slots["S3"]["origin"], slots["S3"]["round"]), ("manager", 9))
        self.assertEqual((slots["S1"]["origin"], slots["S1"]["round"]), ("owner", None))
        js = (pathlib.Path(__file__).resolve().parent.parent / "tools/aimem_monitor/static/app.js").read_text(encoding="utf-8")
        self.assertIn("s.origin === 'manager'", js)

    def test_web_and_cli_share_the_model_rule(self):
        from aimem_monitor import server  # noqa: PLC0415
        for h, m in (("claude", "sonet"), ("codex", "anthropic/claude-sonnet"), ("codex", "opus")):
            web = server._model_allowed(m, h, self.root)
            self.assertFalse(web[0])
            with self.assertRaises(ValueError) as cm:
                aimem_db.slot_add(None, h, m)
            self.assertEqual(str(cm.exception), web[1])

    def test_old_db_gains_the_columns(self):
        con = sqlite3.connect(self.db)
        con.executescript("DROP TABLE slots; CREATE TABLE slots(slot TEXT PRIMARY KEY, token TEXT NOT NULL, harness TEXT NOT NULL,"
                          " model TEXT, role TEXT, note TEXT, updated TEXT);"
                          "INSERT INTO slots VALUES('S1','aaaaaa','codex',NULL,'r','',NULL);")
        con.close()
        rows = aimem_db.slot_list()
        self.assertEqual((rows[0]["origin"], rows[0]["round"]), ("owner", None))
        self.assertEqual(aimem_db.slot_origin_label(rows[0]), "")
        self.assertEqual(aimem_db.slot_origin_label({"origin": "manager", "round": 4}), "관리자 추가 R4")


# ---------------------------------------------------------------- 7. 자리표시
class Placeholders(Base):
    SLOTS = (("S1", "claude", "opus"), ("S2", "codex", None), ("S10", "opencode", "wide/y"))

    def test_slots_extra_slots_and_tiers(self):
        aimem_db.slot_set("S2", role="만들기·고치기")
        self.round_json(9, policy="speed")
        with self.manager_env("M-R9-1"):
            aimem_db.slot_add(None, "opencode", "wide/y", "더함")
        at = dt.datetime(2026, 11, 13, 9, 0)
        text = "{slots}\n[{extra_slots}] [{slot_tiers}] {round} {unknown}"
        got = fleet_ctl._fill_placeholders(text, 9, at, "speed")
        lines = got.splitlines()
        self.assertEqual(lines[:4], [
            "- S1 · claude · opus · 유료 · 공급자 anthropic(동시 3) · S1 역할",
            "- S2 · codex · one/x · 무료 · 공급자 one(동시 1) · 만들기·고치기",
            "- S10 · opencode · wide/y · 무료 · 공급자 wide(동시 8) · S10 역할",
            "- S11 · opencode · wide/y · 무료 · 공급자 wide(동시 8) · 더함 · 관리자 추가"])
        self.assertEqual(lines[4], "[3] [무료·유료] 9 {unknown}")
        self.assertIn("[1] [무료]", fleet_ctl._fill_placeholders(text, 9, at, "cost"))
        self.assertIn("[3]", fleet_ctl._fill_placeholders(text, 9, at))        # 정하지 않으면 그 라운드 기록의 것
        self.assertEqual(fleet_ctl._fill_placeholders("{round}", 9, at), "9")

    def test_policy_text_is_frozen_with_the_live_roster(self):
        out = self.launch_manager("speed")
        frozen = (self.root / "rounds" / f"R{out['round']}" / "policy.md").read_text(encoding="utf-8")
        self.assertIn("- S10 · opencode · wide/y · 무료", frozen)
        self.assertIn("남은 4 · 무료·유료", frozen)
        fleet_ctl.stop("test")


# ---------------------------------------------------------------- 8. 이어 달리기의 운영 방식
class ChainPolicy(Base):
    def test_turning_on_from_off_takes_the_default(self):
        for k in rt_config.POLICIES:
            (self.briefs / f"policy-{k}.md").write_text(f"## {k}\n", encoding="utf-8")
        fleet_ctl.chain_set(True, by="test", fleet_on=True, policy="speed")
        fleet_ctl.chain_set(True, by="test", fleet_on=True)                     # 켜진 채 다시 - 지금 것 그대로
        self.assertEqual(fleet_ctl.chain_state()["policy"], "speed")
        fleet_ctl.chain_set(False, by="test")
        fleet_ctl.chain_set(True, by="test", fleet_on=True)                     # 꺼진 데서 - 설정 기본값
        self.assertEqual(fleet_ctl.chain_state()["policy"], "cost")
        fleet_ctl.chain_set(False, by="test")
        fleet_ctl.chain_set(True, by="test", fleet_on=True, policy="quality")   # 준 것이 이긴다
        self.assertEqual(fleet_ctl.chain_state()["policy"], "quality")


# ---------------------------------------------------------------- 10. 운용 기록
class Metrics(Base):
    def session(self, sid, role="worker", rnd=3, slot="S1", provider="anthropic", start=None, minutes=None):
        d = self.sroot / sid
        d.mkdir(parents=True)
        (d / "meta.json").write_text(json.dumps({"id": sid, "role": role, "round": rnd, "slot": slot, "provider": provider,
                                                 "started": start}), encoding="utf-8")
        if minutes is not None:
            end = (dt.datetime.fromisoformat(start) + dt.timedelta(minutes=minutes)).isoformat(timespec="seconds")
            (d / "end.json").write_text(json.dumps({"state": "done", "rc": 0, "ended": end}), encoding="utf-8")

    def test_round_metrics_and_recorded_once(self):
        t0 = "2026-11-13T10:00:00"
        self.session("a", slot="S1", provider="anthropic", start=t0, minutes=10)
        self.session("b", slot="S2", provider="kisti", start="2026-11-13T10:05:00", minutes=10)
        self.session("c", slot="S2", provider="kisti", start="2026-11-13T10:15:00", minutes=5)    # b 가 끝난 순간 시작 - 겹침 아님
        self.session("d", slot="S3", provider="kisti", start="2026-11-13T10:06:00", minutes=2)
        self.session("e", slot="S3", provider="kisti", start=t0)                                  # 끝나지 않음 - 수에만
        self.session("m", role="manager", slot=None, provider="anthropic", start=t0, minutes=60)  # 관리자는 세지 않는다
        self.session("x", rnd=4, start=t0, minutes=60)                                            # 다른 라운드
        (self.sroot / "broken").mkdir()
        (self.sroot / "broken" / "meta.json").write_text("{", encoding="utf-8")
        (self.root / "fleet.toml").write_text(TOML + '\n[providers.kisti]\ntier = "free"\nmodels = ["k"]\n', encoding="utf-8")
        self.round_json(3, policy="speed")
        g = {"id": "G-001", "round": 3, "nodes": [{"id": "T-1", "slot": "S1", "moves": [{"from": "S2", "to": "S1"}]},
                                                  {"id": "T-2", "slot": "S2"}]}
        (self.graphs / "G-001.json").write_text(json.dumps(g), encoding="utf-8")
        with self.manager_env("M-R3-1"):
            aimem_db.slot_add("S5", "opencode", "wide/y")
        m = fleet_ctl.round_metrics(3)
        self.assertEqual(m["workers"], 5)
        self.assertEqual(m["peak_parallel"], 3)
        self.assertEqual(m["minutes"], {"free": 17.0, "paid": 10.0})
        self.assertEqual(m["by_slot"]["S2"], {"runs": 2, "minutes": 15.0, "tier": "free"})
        self.assertEqual(m["by_slot"]["S1"], {"runs": 1, "minutes": 10.0, "tier": "paid"})
        self.assertEqual(m["by_slot"]["S3"]["runs"], 2)
        self.assertEqual((m["moves"], m["manager_slots"]), (1, ["S5"]))
        self.assertEqual(fleet_ctl.record_round_metrics(3), m)
        self.assertEqual(self.record(3)["metrics"], m)
        self.assertEqual(self.record(3)["policy"], "speed")                    # 다른 칸은 그대로
        self.session("late", slot="S1", start=t0, minutes=1)
        self.assertEqual(fleet_ctl.record_round_metrics(3), m)                 # 한 번만 적는다
        self.assertIsNone(fleet_ctl.record_round_metrics(99))                  # 기록이 없으면 아무것도 안 만든다
        self.assertFalse((self.root / "rounds" / "R99").exists())
        self.assertEqual(fleet_ctl.public_state()["last_round"]["round"], 3)
        self.assertEqual(fleet_ctl.public_state()["last_round"]["metrics"], m)


# ---------------------------------------------------------------- 끝에서 끝까지 (점검 재현)
class EndToEnd(Base):
    SLOTS = (("S1", "claude", "sonnet"), ("S2", "codex", "one/x"), ("S3", "opencode", "wide/y"))

    def test_speed_round_uses_its_freedom(self):
        out = self.launch_manager("speed")
        n, sid = out["round"], out["session"]
        self.assertEqual(self.record(n)["policy"], "speed")
        # 관리자가 슬롯 둘을 더한다 (한도 4, 등급 무료·유료), 셋째는 자리가 없는 공급자라 거절
        with self.manager_env(sid):
            s4 = aimem_db.slot_add(None, "claude", "opus", "속도 - 큰 노드")["slot"]
            s5 = aimem_db.slot_add(None, "opencode", "wide/y", "속도 - 만들기")["slot"]
            with self.assertRaises(ValueError) as cm:
                aimem_db.slot_add(None, "codex", "one/x")
        self.assertEqual((s4, s5), ("S4", "S5"))
        self.assertIn("빨라지지 않습니다", str(cm.exception))
        for i in range(1, 6):
            self.own(f"out/T-{i}.txt", f"S{i}")
        # 서로 기다리지 않는 노드 다섯이 슬롯 다섯에 - 한 틱에 다 뜬다 (관리자는 anthropic 자리를 잡지 않는다)
        nodes = [self.node(f"T-{i}", f"S{i}", task=WORK.format(s=2, w=f"out/T-{i}.txt")) for i in range(1, 6)]
        nodes[1]["task"] = "FAKE: sleep 2\nFAKE: report BLOCKED\\n공급자 one 이 막힘"   # 다섯이 함께 돈 시간이 기록에 남게
        g = self.new_graph(nodes)
        self.assertEqual((g["round"], g["concurrency"]), (n, 5))
        fleet_graph.step(g)
        self.assertEqual([x["status"] for x in g["nodes"]], ["running"] * 5)
        self.assertEqual(sessions.state(self.sroot / sid)["state"], "running")
        fleet_graph._save(g)
        # speed 라 run 은 막힌 노드에서 돌아온다
        rc, text, err = quiet(fleet_graph.cmd_run, argparse.Namespace(id="G-001", timeout=60, poll=0.1, concurrency=None,
                                                                         stop_on_block=None))
        self.assertEqual(rc, 1, text + err)
        self.assertIn("막힌 노드: T-2(blocked, S2)", text)
        # 관리자가 막힌 노드를 다른 슬롯으로 옮기고 다시 돌린다
        g = fleet_graph._load("G-001")
        g["nodes"][1]["task"] = WORK.format(s=1, w="out/T-2.txt")
        fleet_graph._save(g)
        with self.manager_env(sid):
            rc, text, err = quiet(fleet_graph.cmd_move, argparse.Namespace(id="G-001", node="T-2", slot="S5", why="one 막힘"))
        self.assertEqual(rc, 0, err)
        rc, text, err = quiet(fleet_graph.cmd_run, argparse.Namespace(id="G-001", timeout=60, poll=0.1, concurrency=None,
                                                                         stop_on_block=None))
        self.assertEqual(rc, 0, text + err)
        self.assertEqual(self.owner_of("out/T-2.txt"), "S5")
        # 라운드를 닫으면 실제 운용이 남는다
        fleet_ctl.stop("test")
        m = self.record(n)["metrics"]
        self.assertEqual(m["workers"], 6)
        self.assertEqual(m["peak_parallel"], 5)
        self.assertGreater(m["minutes"]["paid"], 0)
        self.assertGreater(m["minutes"]["free"], 0)
        self.assertEqual(m["by_slot"]["S4"]["tier"], "paid")
        self.assertEqual(m["by_slot"]["S5"]["runs"], 2)
        self.assertEqual((m["moves"], m["manager_slots"]), (1, ["S4", "S5"]))
        self.assertEqual(fleet_ctl.public_state()["last_round"]["metrics"], m)

    def test_cost_round_keeps_the_manager_on_free_slots(self):
        out = self.launch_manager("cost")
        sid = out["session"]
        with self.manager_env(sid):
            with self.assertRaises(ValueError) as cm:
                aimem_db.slot_add(None, "claude", "opus")
            self.assertIn("무료 슬롯만", str(cm.exception))
            self.assertEqual(aimem_db.slot_add(None, "opencode", "wide/y")["origin"], "manager")
        self.own("out/T-1.txt", "S2")
        g = self.new_graph([self.node("T-1", "S2", task="FAKE: report BLOCKED\\n막힘")])
        self.assertTrue(self.drive(g, lambda g: g["nodes"][0]["status"] == "blocked"))
        ok, msg = fleet_graph.move_node(g, "T-1", "S1")
        self.assertFalse(ok)
        self.assertIn("운영 방식 cost 에서는 무료 슬롯으로만", msg)
        ok, msg = fleet_graph.move_node(g, "T-1", "S4")
        self.assertTrue(ok, msg)
        fleet_ctl.stop("test")


if __name__ == "__main__":
    unittest.main()
