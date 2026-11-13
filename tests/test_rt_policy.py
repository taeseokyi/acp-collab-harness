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
