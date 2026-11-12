"""실행 기록에 프로젝트·라운드를 **식별자와 따로** 남기는 길 (2026-11-10 태석님: 식별자에는 붙이지 않는다,
알아볼 수만 있으면 된다 / 작업 실행 상태에서 프로젝트 구분)."""
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools"))

import fleet  # noqa: E402
from aimem_monitor import reader  # noqa: E402


class CurrentRoundAndProject(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = pathlib.Path(tmp.name)
        (self.root / ".aimem" / "runs").mkdir(parents=True)
        for attr, value in (("RUNS", self.root / ".aimem" / "runs"), ("ROOT", self.root)):
            p = mock.patch.object(fleet, attr, value)
            p.start()
            self.addCleanup(p.stop)

    def test_current_round_is_the_running_manager_round(self):
        import fleet_ctl
        # 도는 관리자 세션이 없으면 라운드도 없다 (함대 모드 파일이 없을 때)
        with mock.patch.object(fleet_ctl, "mode", return_value="running"), \
                mock.patch.object(fleet_ctl, "active_round", return_value=8, create=True):
            self.assertEqual(fleet.current_round(), 8)
        with mock.patch.object(fleet_ctl, "mode", return_value="running"), \
                mock.patch.object(fleet_ctl, "active_round", return_value=None, create=True):
            self.assertIsNone(fleet.current_round())
        # 함대가 '실행' 이 아니면 도는 라운드가 없다 - 끝난 뒤 손으로 띄운 실행에 지난 번호를 붙이지 않는다
        with mock.patch.object(fleet_ctl, "mode", return_value="ready"), \
                mock.patch.object(fleet_ctl, "active_round", return_value=8, create=True):
            self.assertIsNone(fleet.current_round())
        # active_round 가 아직 없는 fleet_ctl 이어도 죽지 않는다
        with mock.patch.object(fleet_ctl, "mode", return_value="running"), \
                mock.patch.object(fleet_ctl, "active_round", None, create=True):
            self.assertIsNone(fleet.current_round())

    def test_task_project_follows_task_to_request(self):
        reqs = self.root / ".aimem" / "requests"
        reqs.mkdir()
        (reqs / "Q-261110-ab12-x.json").write_text(json.dumps({"id": "Q-261110-ab12", "project": "알파"}), encoding="utf-8")
        (reqs / "Q-261110-cd34.json").write_text(json.dumps({"id": "Q-261110-cd34", "project": ""}), encoding="utf-8")
        state = {"tasks": [{"id": "T-101", "request_id": "Q-261110-ab12"}, {"id": "T-102", "request_id": "Q-261110-cd34"},
                           {"id": "T-103", "request_id": None}, {"id": "T-104", "request_id": "../../etc"}]}
        with mock.patch.object(fleet, "db_state", return_value=state):
            self.assertEqual(fleet.task_project("T-101"), "알파")
            for tid in ("T-102", "T-103", "T-104", "T-999", "ADHOC", None):
                self.assertEqual(fleet.task_project(tid), "", tid)


class SpawnTaskIdFromLabel(unittest.TestCase):
    """R8: 관리자가 그래프 밖에서 `--label "T-113 …"` 만 주고 띄운 실행이 ADHOC 으로 남았다."""

    def test_label_names_the_task_when_task_id_is_missing(self):
        self.assertEqual(fleet.spawn_task_id(None, "T-113 dvh 대비 복구"), "T-113")
        self.assertEqual(fleet.spawn_task_id("", "  t-002b 무엇"), "T-002B")
        self.assertEqual(fleet.spawn_task_id("t-050", "T-113 라벨보다 명시가 먼저"), "T-050")
        for label in (None, "", "점검만", "브리프 T-113 을 다시", "T-", "T-12x34"):
            self.assertEqual(fleet.spawn_task_id(None, label), "ADHOC", label)


class RunRowsCarryProjectAndRound(unittest.TestCase):
    def test_reader_exposes_them_without_touching_the_id(self):
        with tempfile.TemporaryDirectory() as t:
            root = pathlib.Path(t)
            runs = root / ".aimem" / "runs"
            runs.mkdir(parents=True)
            (root / "AIMEM.md").write_text("# AIMEM\n\n- **REV: 1**\n", encoding="utf-8")
            for rid, extra in (("T-101-S1-a1-101010", {"task": "T-101", "project": "알파", "round": 7}),
                               ("T-102-S2-a1-101011", {"task": "T-102", "project": "", "round": None}),
                               ("T-103-S2-a1-101012", {"project": ["x"], "round": True}),
                               ("20261109-163112-S1", {})):
                (runs / f"{rid}.json").write_text(json.dumps(dict({"id": rid, "slot": "S1", "harness": "codex"}, **extra)),
                                                 encoding="utf-8")
            got = {r["id"]: (r["task"], r["project"], r["round"]) for r in reader.collect(root)["runs"]}
        self.assertEqual(got["T-101-S1-a1-101010"], ("T-101", "알파", 7))
        self.assertEqual(got["T-102-S2-a1-101011"], ("T-102", "", None))
        self.assertEqual(got["T-103-S2-a1-101012"], (None, None, None))       # 꼴이 다른 값은 버린다
        self.assertEqual(got["20261109-163112-S1"], (None, None, None))       # 옛 기록


if __name__ == "__main__":
    unittest.main()
