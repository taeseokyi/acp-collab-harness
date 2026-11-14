"""`aimem_db.py` 명령·스냅샷·아카이브 테스트 (임시 저장소만 쓴다 - 운영 DB 는 건드리지 않는다)."""
import argparse
import contextlib
import io
import json
import os
import pathlib
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
import _fleet_env  # noqa: F401,E402 - 세션 표식을 걷는다 (관리자 세션 안에서 돌려도 같은 결과)
sys.path.insert(0, str(ROOT / "tools"))

import aimem_db  # noqa: E402


def ns(**kw):
    base = {"actor": "test", "id": None, "request": None, "title": None, "slot": None, "status": None,
            "artifacts": None, "detail": None, "requester": None, "days": 14, "dry_run": False, "project": None}
    base.update(kw)
    return argparse.Namespace(**base)

# 명령이 찍는 줄이 unittest 요약 뒤에 섞이지 않게 모듈 동안 표준출력을 막는다 (`tail -3 | grep OK` 검증용)
_QUIET = []


def setUpModule():
    cm = contextlib.redirect_stdout(io.StringIO())
    cm.__enter__()
    _QUIET.append(cm)


def tearDownModule():
    while _QUIET:
        _QUIET.pop().__exit__(None, None, None)


class DbFixture:
    """임시 저장소 + 빈 DB. 테스트가 없는 믹스인이라 하위 클래스마다 시험이 다시 돌지 않는다."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        (self.root / ".aimem" / "requests").mkdir(parents=True)
        patches = [mock.patch.object(aimem_db, "ROOT", self.root),
                   mock.patch.object(aimem_db, "DB", self.root / ".aimem" / "aimem.db"),
                   mock.patch.object(aimem_db, "AIMEM", self.root / "AIMEM.md"),
                   mock.patch.object(aimem_db, "HANDOFF", self.root / ".aimem" / "handoff.md")]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self.tmp.cleanup)
        with contextlib.redirect_stdout(io.StringIO()):
            aimem_db.cmd_init()

    def run_cmd(self, fn, **kw):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            fn(ns(**kw))
        return out.getvalue()

    def row(self, sql, *args):
        with aimem_db.connect() as con:
            return con.execute(sql, args).fetchone()

    def rows(self, sql, *args):
        with aimem_db.connect() as con:
            return con.execute(sql, args).fetchall()

    def handoff_count(self):
        return self.row("SELECT count(*) FROM events WHERE kind='handoff'")[0]


class AimemDbCliTest(DbFixture, unittest.TestCase):
    def test_request_set_without_status_updates_existing(self):
        self.run_cmd(aimem_db.cmd_request, action="set", id="Q-1", title="t", status="NEW")
        self.run_cmd(aimem_db.cmd_request, action="set", id="Q-1", detail="줄1\n줄2")
        r = self.row("SELECT status, detail, title FROM requests WHERE id=?", "Q-1")
        self.assertEqual((r["status"], r["detail"], r["title"]), ("NEW", "줄1\n줄2", "t"))

    def test_request_set_new_defaults_to_new(self):
        self.run_cmd(aimem_db.cmd_request, action="set", id="Q-2", title="x")
        self.assertEqual(self.row("SELECT status FROM requests WHERE id=?", "Q-2")["status"], "NEW")

    def test_request_set_syncs_request_file(self):
        f = self.root / ".aimem" / "requests" / "Q-3-x.json"
        f.write_text(json.dumps({"id": "Q-3", "title": "x", "detail": "", "status": "NEW", "subtasks": []}),
                     encoding="utf-8")
        self.run_cmd(aimem_db.cmd_request, action="set", id="Q-3", status="DONE")
        self.assertEqual(json.loads(f.read_text(encoding="utf-8"))["status"], "DONE")

    def test_request_list_sees_web_request_files(self):
        """REV 145: 웹 폼은 파일만 만든다 - `request list` 가 DB 에 싣지 않으면 관리자에게 NEW 가 안 보였다."""
        f = self.root / ".aimem" / "requests" / "Q-261110-ab12-x.json"
        f.write_text(json.dumps({"id": "Q-261110-ab12", "title": "웹에서 넣음", "detail": "d", "requester": "태석",
                                 "project": "데모", "status": "NEW", "subtasks": []}), encoding="utf-8")
        out = self.run_cmd(aimem_db.cmd_request, action="list")
        self.assertIn("Q-261110-ab12", out)
        self.assertIn("NEW", out)
        self.assertIn("[데모] 웹에서 넣음", out)
        # 그 요청에 태스크를 바로 이을 수 있다 (외래 키)
        self.run_cmd(aimem_db.cmd_task, action="set", id="T-900", request="Q-261110-ab12", title="t")
        self.assertEqual(self.row("SELECT request_id FROM tasks WHERE id=?", "T-900")["request_id"], "Q-261110-ab12")

    def test_request_set_project_writes_file_and_validates(self):
        self.run_cmd(aimem_db.cmd_request, action="set", id="Q-9", title="관리자가 만든 요청", project="알파")
        rec = json.loads((self.root / ".aimem" / "requests" / "Q-9.json").read_text(encoding="utf-8"))
        self.assertEqual((rec["project"], rec["status"], rec["title"]), ("알파", "NEW", "관리자가 만든 요청"))
        self.run_cmd(aimem_db.cmd_request, action="set", id="Q-9", project="베타")      # 있는 파일은 고친다
        self.assertEqual(json.loads((self.root / ".aimem" / "requests" / "Q-9.json").read_text(encoding="utf-8"))["project"], "베타")
        with self.assertRaises(SystemExit):
            self.run_cmd(aimem_db.cmd_request, action="set", id="Q-9", project="../x")

    def test_requests_taken_up_mid_round_join_the_round_record(self):
        """라운드 도중에 다룬 요청과 그 프로젝트가 도는 라운드의 `round.json` 에 덧붙는다."""
        import fleet
        rd = self.root / "rounds" / "R7"
        rd.mkdir(parents=True)
        rj = rd / "round.json"
        rj.write_text(json.dumps({"round": 7, "at": "2026-11-10T22:00:00", "requests": ["Q-a"], "projects": ["알파"]}),
                      encoding="utf-8")
        (self.root / ".aimem" / "requests" / "Q-b.json").write_text(json.dumps(
            {"id": "Q-b", "title": "도중에 넣음", "detail": "", "project": "베타", "status": "NEW", "subtasks": []}), encoding="utf-8")
        read = lambda: json.loads(rj.read_text(encoding="utf-8"))  # noqa: E731
        # 다른 저장소(이 임시 폴더)의 라운드는 건드리지 않는다 - fleet.ROOT 가 다르면 아무것도 안 한다
        self.run_cmd(aimem_db.cmd_task, action="set", id="T-1", request="Q-b", title="x")
        self.assertEqual(read()["projects"], ["알파"])
        with mock.patch.object(fleet, "ROOT", self.root):
            with mock.patch.object(fleet, "current_round", return_value=None):      # 도는 라운드가 없으면 그대로
                self.run_cmd(aimem_db.cmd_task, action="set", id="T-1", request="Q-b")
                self.assertEqual(read()["requests"], ["Q-a"])
            with mock.patch.object(fleet, "current_round", return_value=7):
                self.run_cmd(aimem_db.cmd_task, action="set", id="T-1", request="Q-b")
                self.assertEqual((read()["requests"], read()["projects"]), (["Q-a", "Q-b"], ["베타", "알파"]))
                self.run_cmd(aimem_db.cmd_task, action="set", id="T-1", status="DONE")   # 요청을 안 주면 손대지 않는다
                self.run_cmd(aimem_db.cmd_request, action="set", id="Q-c", title="관리자가 만든 후속", project="감마")
                self.assertEqual((read()["requests"], read()["projects"]), (["Q-a", "Q-b", "Q-c"], ["감마", "베타", "알파"]))
                self.assertEqual(read()["at"], "2026-11-10T22:00:00")
                rec = read(); rec["state"] = "failed"; rj.write_text(json.dumps(rec), encoding="utf-8")
                self.run_cmd(aimem_db.cmd_request, action="set", id="Q-d", title="x", project="델타")   # 실패한 라운드는 그대로
                self.assertNotIn("델타", read()["projects"])
            with mock.patch.object(fleet, "current_round", return_value=9):          # 기록 파일이 없는 라운드 - 만들지 않는다
                self.run_cmd(aimem_db.cmd_request, action="set", id="Q-e", title="x", project="엡실론")
                self.assertFalse((self.root / "rounds" / "R9").exists())

    def test_archive_plan_survives_a_node_whose_task_is_the_whole_brief(self):
        """노드의 `task` 가 지시 본문 전체여도 계획이 죽지 않는다 (파일 이름 꼴일 때만 입력 파일로 본다)."""
        g = self.root / ".aimem" / "graph"
        (g / "inputs").mkdir(parents=True)
        (g / "inputs" / "T-1.md").write_text("x", encoding="utf-8")
        (g / "inputs" / "brief-a.md").write_text("x", encoding="utf-8")
        long_task = "# T-2 긴 지시\n\n" + "가나다라 " * 400 + "\n../../etc/passwd"
        (g / "G-001.json").write_text(json.dumps({"id": "G-001", "request": "r", "created": "2026-11-01T00:00:00", "nodes": [
            {"id": "T-1", "status": "done", "task": "brief-a"},
            {"id": "T-2", "status": "done", "task": long_task},
            {"id": "T-3", "status": "failed", "task": None}]}), encoding="utf-8")
        plan = aimem_db.archive_plan(0)
        self.assertEqual([x["id"] for x in plan["graphs"]], ["G-001"])
        self.assertEqual(sorted(plan["graphs"][0]["inputs"]), ["T-1.md", "brief-a.md"])

    def test_project_name_rule_is_one_rule(self):
        import fleet
        import aimem_monitor
        self.assertEqual(aimem_db.PROJECT_NAME_RE, aimem_monitor.PROJECT_NAME_RE)
        self.assertEqual(fleet.PROJECT_NAME_RE, aimem_monitor.PROJECT_NAME_RE)

    def test_task_set_without_status_keeps_status(self):
        self.run_cmd(aimem_db.cmd_task, action="set", id="T-1", title="a", status="REVIEW")
        self.run_cmd(aimem_db.cmd_task, action="set", id="T-1", artifacts="x.py")
        r = self.row("SELECT status, artifacts FROM tasks WHERE id=?", "T-1")
        self.assertEqual((r["status"], r["artifacts"]), ("REVIEW", "x.py"))

    def _old_done(self, tid, updated):
        with aimem_db.connect() as con:
            con.execute("INSERT INTO tasks(id,title,slot,status,created,updated) VALUES(?,?,?,?,?,?)",
                        (tid, "제목 | 파이프", "S1", "DONE", updated, updated))
            con.commit()

    def test_archive_moves_old_done_only(self):
        self._old_done("T-OLD", "2026-09-01T10:00:00")
        self._old_done("T-NEW", "2999-01-01T10:00:00")
        self.run_cmd(aimem_db.cmd_task, action="set", id="T-REV", title="r", status="REVIEW")
        self.run_cmd(aimem_db.cmd_archive)
        self.assertIsNone(self.row("SELECT 1 FROM tasks WHERE id=?", "T-OLD"))
        self.assertIsNotNone(self.row("SELECT 1 FROM tasks WHERE id=?", "T-NEW"))
        self.assertIsNotNone(self.row("SELECT 1 FROM tasks WHERE id=?", "T-REV"))
        text = (self.root / ".aimem" / "archive" / "board-2026-09.md").read_text(encoding="utf-8")
        self.assertIn("| T-OLD |", text)
        self.assertIn("제목 \\| 파이프", text)   # 표가 깨지지 않게 파이프를 이스케이프

    def test_archive_dry_run_changes_nothing(self):
        self._old_done("T-OLD", "2026-09-01T10:00:00")
        out = self.run_cmd(aimem_db.cmd_archive, dry_run=True)
        self.assertIn("T-OLD", out)
        self.assertIsNotNone(self.row("SELECT 1 FROM tasks WHERE id=?", "T-OLD"))
        self.assertFalse((self.root / ".aimem" / "archive").exists())


class SlotCommandTest(DbFixture, unittest.TestCase):
    """`aimem_db.py slot add|set|remove|list` (2026-11-10, 태석님 지시) - DB 가 슬롯 모델의 유일한 정본이다(거울 파일 `tools/fleet_slots.json` 은 더는 쓰지 않는다)."""

    def _json(self):
        """DB 슬롯 행으로 만든 {슬롯: {harness, model?}} - 예전 거울 파일 꼴."""
        out = {}
        for r in aimem_db.slot_list():
            out[r["slot"]] = {"harness": r["harness"], **({"model": r["model"]} if r["model"] else {})}
        return out

    def test_add_set_remove_roundtrip_and_no_mirror_file(self):
        r = aimem_db.slot_add(None, "claude", "anthropic/claude-opus-5-5", "판단형", "", actor="t")
        self.assertEqual(r["slot"], "S1")
        self.assertEqual(len(r["token"]), 6)
        r2 = aimem_db.slot_add(None, "codex", None, "", "", actor="t")
        self.assertEqual(r2["slot"], "S2")
        self.assertEqual(self._json(), {"S1": {"harness": "claude", "model": "anthropic/claude-opus-5-5"}, "S2": {"harness": "codex"}})
        row, changes = aimem_db.slot_set("S2", model="kisti/kistillm", role="테스트", actor="t")
        self.assertEqual(row["model"], "kisti/kistillm")
        self.assertEqual(len(changes), 2)
        row, changes = aimem_db.slot_set("S2", clear_model=True, actor="t")
        self.assertIsNone(row["model"])
        self.assertEqual(self._json()["S2"], {"harness": "codex"})
        res = aimem_db.slot_remove("S2", actor="t")
        self.assertEqual([s["slot"] for s in aimem_db.slot_list()], ["S1"])
        self.assertNotIn("S2", self._json())
        self.assertFalse((self.root / "tools" / "fleet_slots.json").exists())   # 거울 파일을 만들지 않는다
        with aimem_db.connect() as con:
            kinds = [r["kind"] for r in con.execute("SELECT kind FROM events")]
        self.assertEqual(kinds.count("slot"), 5)   # add, add, set, set, remove

    def test_validation_and_open_task_guard(self):
        with self.assertRaises(ValueError):
            aimem_db.slot_add("X1", "claude")
        with self.assertRaises(ValueError):
            aimem_db.slot_add("S1", "gemini")
        aimem_db.slot_add("S1", "claude", actor="t")
        with self.assertRaises(ValueError):
            aimem_db.slot_add("S1", "claude", actor="t")   # 중복
        with self.assertRaises(ValueError):
            aimem_db.slot_set("S1", model="bad model with space", actor="t")
        with aimem_db.connect() as con:
            con.execute("INSERT INTO tasks(id,request_id,title,slot,status,inherited,artifacts,created,updated) VALUES('T-1',NULL,'x','S1','ASSIGNED','','',?,?)", (aimem_db._now(), aimem_db._now()))
            con.commit()
        with self.assertRaises(ValueError):
            aimem_db.slot_remove("S1", actor="t")            # 미완 태스크
        self.assertEqual(aimem_db.slot_remove("S1", actor="t", force=True)["open_tasks"], ["T-1"])
        self.assertEqual(aimem_db.next_slot_id(), "S1")


class ArchiveRequestsGraphsTest(DbFixture, unittest.TestCase):
    """REV 123: `archive` 가 닫힌 요청 파일과 끝난 그래프(부속 파일·inputs 포함)도 내린다."""

    def _seed_files(self):
        rdir, gdir = self.root / ".aimem" / "requests", self.root / ".aimem" / "graph"
        (gdir / "inputs").mkdir(parents=True)
        (rdir / "Q-1-old.json").write_text(json.dumps({"id": "Q-1", "status": "DONE", "title": "옛 요청", "created": "2026-01-01 10:00", "updated": "2026-01-02 10:00"}), encoding="utf-8")
        (rdir / "Q-2-new.json").write_text(json.dumps({"id": "Q-2", "status": "NEW", "title": "열린 요청", "created": "2026-01-01 10:00"}), encoding="utf-8")
        (rdir / "Q-3-recent.json").write_text(json.dumps({"id": "Q-3", "status": "DONE", "title": "방금 끝난 요청", "created": aimem_db._now(), "updated": aimem_db._now()}), encoding="utf-8")
        (gdir / "G-1.json").write_text(json.dumps({"id": "G-1", "request": "끝난 그래프", "created": "2026-01-01T10:00:00", "updated": "2026-01-02T10:00:00",
                                                   "nodes": [{"id": "T-10", "status": "done"}, {"id": "T-11", "status": "failed"}]}), encoding="utf-8")
        for name in ("G-1.log", "G-1.lock", "G-1-T-10-a1.task.md"):
            (gdir / name).write_text("x", encoding="utf-8")
        (gdir / "inputs" / "G-1-nodes.json").write_text("{}", encoding="utf-8")
        (gdir / "inputs" / "T-10.md").write_text("brief", encoding="utf-8")
        (gdir / "G-2.json").write_text(json.dumps({"id": "G-2", "request": "도는 그래프", "created": "2026-01-01T10:00:00", "updated": "2026-01-02T10:00:00",
                                                   "nodes": [{"id": "T-20", "status": "running"}]}), encoding="utf-8")
        (gdir / "inputs" / "T-20.md").write_text("brief", encoding="utf-8")

    def test_plan_and_apply(self):
        self._seed_files()
        plan = aimem_db.archive_plan(14)
        self.assertEqual([r["id"] for r in plan["requests"]], ["Q-1"])        # NEW 와 최근 DONE 은 남는다
        self.assertEqual([g["id"] for g in plan["graphs"]], ["G-1"])          # running 노드가 있는 G-2 는 남는다
        self.assertEqual(sorted(plan["graphs"][0]["side_files"]), ["G-1-T-10-a1.task.md", "G-1.lock", "G-1.log"])
        self.assertEqual(sorted(plan["graphs"][0]["inputs"]), ["G-1-nodes.json", "T-10.md"])
        out = aimem_db.archive_apply(plan, actor="t")
        self.assertEqual((out["requests"], out["graphs"], out["files"]), (["Q-1"], ["G-1"], 7))
        arch = self.root / ".aimem" / "archive"
        self.assertTrue((arch / "requests-2026-01" / "Q-1-old.json").exists())
        self.assertTrue((arch / "graph-2026-01" / "G-1.json").exists())
        self.assertTrue((arch / "graph-2026-01" / "inputs" / "T-10.md").exists())
        self.assertFalse((self.root / ".aimem" / "graph" / "G-1.lock").exists())
        self.assertTrue((self.root / ".aimem" / "graph" / "G-2.json").exists())
        self.assertTrue((self.root / ".aimem" / "graph" / "inputs" / "T-20.md").exists())
        self.assertTrue((self.root / ".aimem" / "requests" / "Q-2-new.json").exists())
        with aimem_db.connect() as con:
            body = con.execute("SELECT body FROM events WHERE kind='archive'").fetchone()[0]
        self.assertIn("요청 1건, 그래프 1개", body)
        # days=0 이면 방금 끝난 요청도 내린다 (같은 초라도 - 1초 더하는 우회 없이)
        plan0 = aimem_db.archive_plan(0)
        self.assertEqual([r["id"] for r in plan0["requests"]], ["Q-3"])

    def _round(self, n, at="2026-01-01T10:00:00"):
        d = self.root / "rounds" / f"R{n}"
        d.mkdir(parents=True)
        (d / "round.json").write_text(json.dumps({"round": n, "at": at, "projects": ["가"]}), encoding="utf-8")
        (d / "REPORT.md").write_text("상태: DONE\n", encoding="utf-8")
        return d

    def test_round_records_move_but_the_latest_and_live_ones_stay(self):
        for n in (1, 2, 3, 4, 5):
            self._round(n)
        self._round(6, at=aimem_db._now())                                   # 가장 높은 번호 - 다음 번호의 근거
        (self.root / "rounds" / "R1" / "round.json").write_text("{깨진", encoding="utf-8")   # 언제 떴는지 모르면 남긴다
        gdir = self.root / ".aimem" / "graph"
        gdir.mkdir(parents=True)
        (gdir / "G-9.json").write_text(json.dumps({"id": "G-9", "round": 2, "nodes": [{"id": "T-90", "status": "todo"}]}), encoding="utf-8")
        live = self.root / ".aimem" / "sessions" / "M-R3-101010"
        live.mkdir(parents=True)                                             # end.json 없음 = 관리자가 아직 돈다
        (self.root / "outside").mkdir()
        (self.root / "rounds" / "R0").symlink_to(self.root / "outside")
        plan = aimem_db.archive_plan(14)
        self.assertEqual([r["round"] for r in plan["rounds"]], [4, 5])
        out = aimem_db.archive_apply(plan, actor="t")
        self.assertEqual(out["rounds"], [4, 5])
        arch = self.root / ".aimem" / "archive" / "rounds-2026-01"
        self.assertTrue((arch / "R4" / "REPORT.md").is_file() and (arch / "R5" / "round.json").is_file())
        self.assertEqual(sorted(d.name for d in (self.root / "rounds").iterdir()), ["R0", "R1", "R2", "R3", "R6"])
        with aimem_db.connect() as con:
            body = con.execute("SELECT body FROM events WHERE kind='archive'").fetchone()[0]
        self.assertIn("라운드 기록 2개", body)
        self.assertEqual(aimem_db.archive_plan(14)["rounds"], [])

    def test_ownership_rows_of_a_removed_project_are_dropped(self):
        (self.root / "projects" / "산것").mkdir(parents=True)
        for path, owner in (("projects/산것/web/**", "S2"), ("projects/치운것/web/**", "S2"), ("projects/치운것/app.json", "S3"),
                            ("projects/새것/**", "S2"), ("projects/**", "관리자"), ("tools/**", "S1")):
            aimem_db.ownership_set(path, owner, actor="t")
        rdir = self.root / ".aimem" / "requests"
        rdir.mkdir(parents=True, exist_ok=True)
        (rdir / "Q-9-new.json").write_text(json.dumps({"id": "Q-9", "status": "NEW", "project": "새것", "created": aimem_db._now()}), encoding="utf-8")
        plan = aimem_db.archive_plan(14)
        self.assertEqual([o["path"] for o in plan["ownership"]], ["projects/치운것/app.json", "projects/치운것/web/**"])
        self.assertEqual(plan["total"], 2)
        (self.root / "projects" / "치운것").mkdir()                          # 계획 뒤에 되살아나면 남긴다
        self.assertEqual(aimem_db.archive_apply(plan, actor="t")["ownership"], [])
        (self.root / "projects" / "치운것").rmdir()
        out = aimem_db.archive_apply(aimem_db.archive_plan(14), actor="t")
        self.assertEqual(len(out["ownership"]), 2)
        left = [r[0] for r in self.rows("SELECT path_pattern FROM ownership ORDER BY path_pattern")]
        self.assertEqual(left, ["projects/**", "projects/산것/web/**", "projects/새것/**", "tools/**"])

    def test_cutoff_is_inclusive_same_second(self):
        """REV 119 메모의 결함: 기준 시각과 같은 초에 끝난 태스크·요청·그래프가 `<` 비교로 빠져 두 번 돌려야 했다."""
        now = aimem_db.dt.datetime(2026, 11, 10, 12, 0, 0)
        stamp = now.isoformat(timespec="seconds")
        with aimem_db.connect() as con:
            con.execute("INSERT INTO tasks(id,title,slot,status,created,updated) VALUES(?,?,?,?,?,?)",
                        ("T-SAME", "같은 초", "S1", "DONE", stamp, stamp))
            con.commit()
        rdir, gdir = self.root / ".aimem" / "requests", self.root / ".aimem" / "graph"
        gdir.mkdir(parents=True)
        (rdir / "Q-S.json").write_text(json.dumps({"id": "Q-S", "status": "DONE", "title": "같은 초", "updated": stamp.replace("T", " ")}), encoding="utf-8")
        (gdir / "G-S.json").write_text(json.dumps({"id": "G-S", "updated": stamp, "nodes": [{"id": "T-S", "status": "done"}]}), encoding="utf-8")
        plan = aimem_db.archive_plan(0, now=now)
        self.assertEqual(([r["id"] for r in plan["tasks"]], [r["id"] for r in plan["requests"]], [g["id"] for g in plan["graphs"]]),
                         (["T-SAME"], ["Q-S"], ["G-S"]))
        # 기준보다 1초 뒤에 끝난 것은 여전히 남는다
        later = (now + aimem_db.dt.timedelta(seconds=1)).isoformat(timespec="seconds")
        (gdir / "G-L.json").write_text(json.dumps({"id": "G-L", "updated": later, "nodes": [{"id": "T-L", "status": "done"}]}), encoding="utf-8")
        self.assertNotIn("G-L", [g["id"] for g in aimem_db.archive_plan(0, now=now)["graphs"]])

    def test_cmd_dry_run_moves_nothing(self):
        self._seed_files()
        out = self.run_cmd(aimem_db.cmd_archive, days=14, dry_run=True, actor="t")
        self.assertIn("요청 <- Q-1", out)
        self.assertIn("그래프 <- G-1", out)
        self.assertTrue((self.root / ".aimem" / "requests" / "Q-1-old.json").exists())


class MigrateTest(DbFixture, unittest.TestCase):
    """`migrate` 는 요청 파일·handoff.md·세션 폴더만 적재한다 - AIMEM.md 의 옛 표·4절 로그와 `.aimem/runs` 는 읽지 않는다."""

    def test_markdown_tables_and_legacy_runs_are_not_imported(self):
        (self.root / "AIMEM.md").write_text(
            "# AIMEM.md\n\n- **REV: 5** (x)\n\n## 2. 세션 명부\n\n| 슬롯 | 확인토큰 | 하네스 | 역할 |\n| --- | --- | --- | --- |\n"
            "| S9 | `abc123` | claude | x |\n\n## 3. 작업 보드\n\n| ID | 태스크 | 담당 | 상태 |\n| --- | --- | --- | --- |\n"
            "| T-9 | t | S9 | TODO |\n\n## 4. Handoff Log\n\n- `2026-11-10 19:00` 관리자: **REV 5.** 옛 4절 항목\n\n"
            "## 4.5 대기 큐\n\n| 순서 | 태스크 |\n| --- | --- |\n| 1 | 큐 |\n\n## 6. 파일 소유권\n\n"
            "| 경로 패턴 | 쓰기 소유 |\n| --- | --- |\n| `a.py` | S9 |\n", encoding="utf-8")
        runs = self.root / ".aimem" / "runs"
        runs.mkdir()
        (runs / "r1.json").write_text(json.dumps({"id": "r1", "task": "T-9"}), encoding="utf-8")
        (runs / "r1.rc").write_text("0", encoding="utf-8")
        (self.root / ".aimem" / "graph").mkdir()
        (self.root / ".aimem" / "graph" / "G-1.json").write_text(json.dumps({"id": "G-1", "nodes": [{"id": "T-9"}]}), encoding="utf-8")
        aimem_db.migrate(verbose=False)
        for table in ("slots", "tasks", "queue", "ownership", "runs", "graphs", "nodes"):
            self.assertEqual(self.row(f"SELECT count(*) FROM {table}")[0], 0, table)
        self.assertEqual(self.handoff_count(), 0)
        self.assertEqual(self.row("SELECT value FROM meta WHERE key='rev'")[0], "5")   # 빈 DB 의 REV 씨앗만 읽는다

    def test_rev_seed_does_not_overwrite_db_rev(self):
        (self.root / "AIMEM.md").write_text("- **REV: 5**\n", encoding="utf-8")
        with aimem_db.connect() as con:
            con.execute("INSERT INTO meta(key,value) VALUES('rev','9')")
        aimem_db.migrate(verbose=False)
        self.assertEqual(self.row("SELECT value FROM meta WHERE key='rev'")[0], "9")


class ImportHandoffEntriesTest(DbFixture, unittest.TestCase):
    """복구용 적재: 본문에 `**REV N` 이 없는 항목도 rev 가 비지 않고, 파일 차례(최신 먼저)가 유지된다."""

    ENTRIES = [  # 최신 먼저 (`handoff_entries` 와 같은 차례)
        "- `2026-11-01 12:00` 관리자: **REV 101. 셋째 항목.**",
        "- `2026-11-01 11:00` 관리자: 둘째 항목 - 본문에 레브 글자가 없다.",
        "- `2026-11-01 10:00` 관리자: **REV 100. 첫째 항목.**",
    ]

    def _imported(self):
        with aimem_db.connect() as con:
            n = aimem_db._import_handoff_entries(con, self.ENTRIES)
            rows = con.execute("SELECT seq, rev, body FROM events ORDER BY seq").fetchall()
            rendered = [r["body"] for r in aimem_db._handoff_rows(con)]
            return n, rows, rendered

    def test_import_never_stores_null_rev(self):
        """고치기 전 코드는 REV 없는 항목의 rev 를 None 으로 넣었다 - 그러면 이 단언이 빨개진다."""
        n, rows, _ = self._imported()
        self.assertEqual(n, 3)
        self.assertNotIn(None, [r["rev"] for r in rows])
        self.assertEqual([r["rev"] for r in rows], sorted(r["rev"] for r in rows))

    def test_render_order_matches_file_order_when_rev_is_missing(self):
        """고치기 전에는 rev None 이 정렬키 -1 로 가라앉아 '둘째'가 맨 아래로 갔다 - 이 차례 단언이 빨개진다."""
        _, _, rendered = self._imported()
        self.assertEqual(rendered[0], self.ENTRIES[0])
        self.assertEqual(rendered[1], self.ENTRIES[1])
        self.assertEqual(rendered[2], self.ENTRIES[2])


class HandoffLogTest(DbFixture, unittest.TestCase):
    """REV 132: 핸드오프의 정본은 DB events 하나. .aimem/handoff.md 는 최신 12건 생성물, 밀려난 항목은 아카이브로 내보낸다."""

    def test_add_writes_event_and_generates_file(self):
        new, exported = aimem_db.handoff_add("**REV 1. first.** body", actor="t", bump=True, when="2026-11-10 19:00")
        self.assertEqual((new, exported), (1, 0))
        row = self.row("SELECT at, actor, rev, body FROM events WHERE kind='handoff'")
        self.assertEqual((row["at"], row["actor"], row["rev"], row["body"]), ("2026-11-10 19:00", "t", 1, "**REV 1. first.** body"))
        text = aimem_db.HANDOFF.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("# Handoff Log (generated)"))
        self.assertIn("- `2026-11-10 19:00` t: **REV 1. first.** body\n", text)
        self.assertEqual(aimem_db.handoff_entries(), ["- `2026-11-10 19:00` t: **REV 1. first.** body"])

    def test_add_refuses_long_entry_unless_allowed(self):
        with self.assertRaises(ValueError):
            aimem_db.handoff_add("x" * (aimem_db.HANDOFF_ENTRY_MAX + 1), actor="t")
        self.assertEqual(self.handoff_count(), 0)
        aimem_db.handoff_add("x" * (aimem_db.HANDOFF_ENTRY_MAX + 1), actor="t", allow_long=True)
        self.assertEqual(self.handoff_count(), 1)

    def test_hand_edit_is_overwritten_by_next_sync(self):
        aimem_db.handoff_add("real", actor="t", bump=True, when="2026-11-10 10:00")
        aimem_db.HANDOFF.write_text(aimem_db.HANDOFF.read_text(encoding="utf-8") + "- `2026-11-10 23:59` hand: typed\n", encoding="utf-8")
        aimem_db.handoff_sync()
        text = aimem_db.HANDOFF.read_text(encoding="utf-8")
        self.assertNotIn("typed", text)
        self.assertIn("real", text)

    def test_window_keeps_latest_and_exports_older_once(self):
        for i in range(1, 15):   # 14건 → 창 12, 아카이브 2
            aimem_db.handoff_add(f"entry {i:02d}", actor="t", bump=True, when=f"2026-11-{i:02d} 10:00")
        live = aimem_db.HANDOFF.read_text(encoding="utf-8")
        self.assertEqual(live.count("\n- `"), aimem_db.HANDOFF_MAX)
        self.assertLess(live.index("entry 14"), live.index("entry 03"))   # 최신이 위
        self.assertNotIn("entry 02", live)
        arch = (self.root / ".aimem" / "archive" / "handoff-2026-11.md").read_text(encoding="utf-8")
        self.assertEqual((arch.count("entry 01\n"), arch.count("entry 02\n"), arch.count("entry 03\n")), (1, 1, 0))
        aimem_db.handoff_sync(); aimem_db.handoff_sync()                    # 다시 돌려도 두 번 붙지 않는다
        arch = (self.root / ".aimem" / "archive" / "handoff-2026-11.md").read_text(encoding="utf-8")
        self.assertEqual(arch.count("entry 01\n"), 1)
        self.assertEqual(self.handoff_count(), 14)                         # DB 에는 전부 남는다
        self.assertEqual(len(aimem_db.handoff_entries()), 14)

    def test_order_follows_rev_not_hand_written_time(self):
        with aimem_db.connect() as con:   # 옛 항목: 손으로 적은 시각이 실제보다 늦다
            con.execute("INSERT INTO events(at,actor,rev,kind,body) VALUES('2026-11-10 17:55','관리자',5,'handoff','- `2026-11-10 17:55` old: REV 5')")
            con.execute("INSERT INTO meta(key,value) VALUES('rev','5')"); con.commit()
        aimem_db.handoff_add("REV 6", actor="t", bump=True, when="2026-11-10 17:00")
        self.assertEqual([e[:30] for e in aimem_db.handoff_entries()], ["- `2026-11-10 17:00` t: REV 6", "- `2026-11-10 17:55` old: REV 5"[:30]])

    def test_migrate_recovers_from_generated_file_without_duplicates(self):
        aimem_db.handoff_add("**REV 1. kept.** x", actor="t", bump=True, when="2026-11-10 19:00")
        aimem_db.migrate(verbose=False)                      # 이미 DB 에 있는 항목은 다시 넣지 않는다
        self.assertEqual(self.handoff_count(), 1)
        with aimem_db.connect() as con:                      # DB 를 잃었다고 치고
            con.execute("DELETE FROM events WHERE kind='handoff'"); con.commit()
        aimem_db.migrate(verbose=False)                      # 생성 파일에서 되살린다
        row = self.row("SELECT at, rev FROM events WHERE kind='handoff'")
        self.assertEqual((row["at"], row["rev"]), ("2026-11-10 19:00", 1))

    def test_sync_rev_updates_last_updated_line(self):
        aimem_db.AIMEM.write_text("# AIMEM.md\n\n- **REV: 1** (x)\n- Last updated: 2000-01-01 00:00 KST\n", encoding="utf-8")
        with aimem_db.connect() as con:
            con.execute("INSERT INTO meta(key,value) VALUES('rev','9') ON CONFLICT(key) DO UPDATE SET value=excluded.value"); con.commit()
        self.assertEqual(aimem_db.sync_rev_in_aimem(), 9)
        text = aimem_db.AIMEM.read_text(encoding="utf-8")
        self.assertIn("- **REV: 9**", text)
        self.assertRegex(text, r"- Last updated: \d{4}-\d{2}-\d{2} \d{2}:\d{2} KST")
        self.assertIsNone(aimem_db.sync_rev_in_aimem())


class HandoffConcurrencyTest(DbFixture, unittest.TestCase):
    """동시에 쓰는 handoff add: 항목을 잃지 않고, REV 가 겹치지 않고, 아카이브에 두 번 붙지 않는다 - 잠금 파일 없이 DB 트랜잭션만으로."""

    def test_parallel_adds_lose_nothing_and_revs_are_unique(self):
        import threading
        n, results, errors = 20, [], []
        start = threading.Barrier(n)

        def work(i):
            try:
                start.wait()
                results.append(aimem_db.handoff_add(f"parallel {i:02d}", actor="t", bump=True, when=f"2026-11-{i + 1:02d} 10:00")[0])
            except Exception as e:  # noqa: BLE001
                errors.append(e)

        ts = [threading.Thread(target=work, args=(i,)) for i in range(n)]
        [t.start() for t in ts]; [t.join() for t in ts]
        self.assertEqual(errors, [])
        self.assertEqual(sorted(results), list(range(1, n + 1)))            # REV 가 하나도 겹치지 않는다
        self.assertEqual(self.handoff_count(), n)                           # DB 에 전부 있다
        live = aimem_db.HANDOFF.read_text(encoding="utf-8")
        arch = "".join(f.read_text(encoding="utf-8") for f in (self.root / ".aimem" / "archive").glob("handoff-*.md"))
        for i in range(n):                                                  # 항목마다 정확히 한 곳에 한 번
            self.assertEqual(live.count(f"parallel {i:02d}\n") + arch.count(f"parallel {i:02d}\n"), 1, i)
        with aimem_db.connect() as con:                                     # 생성 파일이 DB 와 정확히 같다
            self.assertEqual(live, aimem_db.render_handoff_text(con))
        self.assertEqual(list(aimem_db.HANDOFF.parent.glob("handoff.md.*.tmp")), [])

    def test_expect_rev_refuses_stale_writer(self):
        aimem_db.handoff_add("first", actor="a", bump=True, when="2026-11-10 10:00")       # REV 0 → 1
        with self.assertRaises(ValueError) as cm:
            aimem_db.handoff_add("stale", actor="b", bump=True, expect_rev=0, when="2026-11-10 10:01")
        self.assertIn("REV 불일치", str(cm.exception))
        self.assertNotIn("stale", aimem_db.HANDOFF.read_text(encoding="utf-8"))             # 아무것도 쓰지 않았다
        self.assertEqual(self.handoff_count(), 1)
        with aimem_db.connect() as con:
            self.assertEqual(aimem_db.rev(con), 1)
        self.assertEqual(aimem_db.handoff_add("fresh", actor="b", bump=True, expect_rev=1, when="2026-11-10 10:02")[0], 2)

    def test_failed_file_write_rolls_back_the_row(self):
        with mock.patch.object(aimem_db, "render_handoff_text", side_effect=OSError("disk")):
            with self.assertRaises(OSError):
                aimem_db.handoff_add("lost?", actor="t", bump=True)
        self.assertEqual(self.handoff_count(), 0)                           # 파일을 못 만들면 행도 REV 도 되돌아간다
        with aimem_db.connect() as con:
            self.assertIsNone(aimem_db.rev(con))


class ArchiveAttachedRecordsTest(DbFixture, unittest.TestCase):
    """끝난 작업을 정리할 때 그 작업에 딸린 세션·이벤트·핸드오프·전달·로그도 함께 옮긴다."""

    OLD = "2026-01-01T00:00:00"

    def _task(self, tid, status, updated=None):
        updated = updated or self.OLD
        with aimem_db.connect() as con:
            con.execute("INSERT INTO tasks(id,title,slot,status,created,updated) VALUES(?,?,?,?,?,?)",
                        (tid, "제목", "S1", status, updated, updated))
            con.commit()

    def _event(self, body, at=None, kind="note", rev=None):
        with aimem_db.connect() as con:
            cur = con.execute("INSERT INTO events(at,actor,rev,kind,body) VALUES(?,?,?,?,?)",
                              (at or self.OLD, "t", rev, kind, body))
            con.commit()
            return cur.lastrowid

    def _handoff(self, i, at, rev=None):
        return self._event(f"entry {i:02d}", at=at, kind="handoff", rev=rev)

    def test_events_move_only_when_no_open_id_is_mentioned(self):
        self._task("T-900", "DONE")
        self._task("T-901", "TODO")
        only_finished = self._event("T-900 끝남\n둘째 줄", rev=150)
        only_open = self._event("T-901 열림")
        both = self._event("T-900 그리고 T-901 둘 다")
        plan = aimem_db.archive_plan(0)
        self.assertEqual([e["seq"] for e in plan["events"]], [only_finished])
        out = aimem_db.archive_apply(plan, actor="t")
        self.assertEqual(out["events"], [only_finished])
        self.assertIsNone(self.row("SELECT 1 FROM events WHERE seq=?", only_finished))
        self.assertIsNotNone(self.row("SELECT 1 FROM events WHERE seq=?", only_open))
        self.assertIsNotNone(self.row("SELECT 1 FROM events WHERE seq=?", both))
        f = self.root / ".aimem" / "archive" / "events-2026-01.jsonl"
        recs = [json.loads(ln) for ln in f.read_text(encoding="utf-8").splitlines() if ln.strip()]
        self.assertEqual([r["seq"] for r in recs], [only_finished])
        self.assertEqual(recs[0]["rev"], 150)
        self.assertEqual(recs[0]["body"], "T-900 끝남\n둘째 줄")
        self.assertNotIn(only_open, [r["seq"] for r in recs])
        self.assertNotIn(both, [r["seq"] for r in recs])

    def test_no_partial_id_match(self):
        self._task("T-900", "DONE")
        seq = self._event("T-9000", at="2999-01-01T00:00:00")
        plan = aimem_db.archive_plan(0)
        self.assertNotIn(seq, [e["seq"] for e in plan["events"]])
        aimem_db.archive_apply(plan, actor="t")
        self.assertIsNotNone(self.row("SELECT 1 FROM events WHERE seq=?", seq))

    def test_newest_12_handoffs_stay_in_db_and_file(self):
        seqs = [self._handoff(i, f"2026-01-{i:02d} 00:00") for i in range(1, 16)]
        plan = aimem_db.archive_plan(0)
        moved = {h["seq"] for h in plan["handoff"]}
        self.assertEqual(moved, {seqs[0], seqs[1], seqs[2]})
        out = aimem_db.archive_apply(plan, actor="t")
        self.assertEqual(len(out["handoff"]), 3)
        self.assertEqual(self.row("SELECT count(*) FROM events WHERE kind='handoff'")[0], aimem_db.HANDOFF_MAX)
        live = aimem_db.HANDOFF.read_text(encoding="utf-8")
        self.assertEqual(live.count("\n- `"), aimem_db.HANDOFF_MAX)
        arch = (self.root / ".aimem" / "archive" / "handoff-2026-01.md").read_text(encoding="utf-8")
        for i in (1, 2, 3):
            self.assertIn(f"entry {i:02d}", arch)
        self.assertNotIn("entry 04", arch)

    def test_logs_move_only_old_timestamped_lines(self):
        aimem = self.root / ".aimem"
        fleet = aimem / "fleet-mode.log"
        fleet.write_text("2026-01-01T00:00:00 old\n시각 없음\n2999-01-01T00:00:00 new\n", encoding="utf-8")
        access = aimem / "access.log"
        access.write_text("2026-01-01T00:00:00 access old\n", encoding="utf-8")
        plan = aimem_db.archive_plan(0)
        self.assertEqual([x["lines"] for x in plan["logs"] if x["file"] == "fleet-mode.log"], [1])
        self.assertFalse(any(x["file"] == "access.log" for x in plan["logs"]))
        aimem_db.archive_apply(plan, actor="t")
        self.assertEqual(fleet.read_text(encoding="utf-8"), "시각 없음\n2999-01-01T00:00:00 new\n")
        self.assertEqual(access.read_text(encoding="utf-8"), "2026-01-01T00:00:00 access old\n")
        arch = (aimem / "archive" / "logs-2026-01" / "fleet-mode.log").read_text(encoding="utf-8")
        self.assertIn("old", arch)
        self.assertNotIn("시각 없음", arch)

    def test_legacy_run_files_and_rows_are_left_alone(self):
        """옛 `.aimem/runs` 는 더 다루지 않는다 - 끝난 태스크의 실행 파일도 `runs` 표 행(이력)도 그대로 남는다."""
        self._task("T-900", "DONE")
        d = self.root / ".aimem" / "runs"
        d.mkdir(parents=True)
        for name in ("run-900.json", "run-900.rc"):
            (d / name).write_text("{}", encoding="utf-8")
        with aimem_db.connect() as con:
            con.execute("INSERT INTO runs(id,task_id,state,started) VALUES('run-900','T-900','done',?)", (self.OLD,))
        plan = aimem_db.archive_plan(0)
        self.assertNotIn("runs", plan)
        out = aimem_db.archive_apply(plan, actor="t")
        self.assertEqual(out["tasks"], ["T-900"])
        self.assertEqual(sorted(x.name for x in d.iterdir()), ["run-900.json", "run-900.rc"])
        self.assertIsNotNone(self.row("SELECT 1 FROM runs WHERE id='run-900'"))

    def test_missing_runs_dir_is_fine(self):
        self._task("T-900", "DONE")
        self.assertFalse((self.root / ".aimem" / "runs").exists())
        self.assertEqual(aimem_db.archive_apply(aimem_db.archive_plan(0), actor="t")["tasks"], ["T-900"])

    def test_rev_unchanged_and_archive_event_written(self):
        self._task("T-900", "DONE")
        self._event("T-900 note")
        with aimem_db.connect() as con:
            con.execute("INSERT INTO meta(key,value) VALUES('rev','42') ON CONFLICT(key) DO UPDATE SET value=excluded.value")
            con.commit()
        plan = aimem_db.archive_plan(0)
        out = aimem_db.archive_apply(plan, actor="t")
        self.assertEqual(self.row("SELECT value FROM meta WHERE key='rev'")[0], "42")
        rows = [r["body"] for r in self.rows("SELECT body FROM events WHERE kind='archive'")]
        self.assertEqual(len(rows), 1)
        self.assertEqual(len(out["events"]), 1)

    def test_dry_run_leaves_events_and_logs(self):
        self._task("T-900", "DONE")
        self._event("T-900 note")
        fleet = self.root / ".aimem" / "fleet-mode.log"
        fleet.write_text("2026-01-01T00:00:00 old\n", encoding="utf-8")
        out = self.run_cmd(aimem_db.cmd_archive, days=0, dry_run=True, actor="t")
        self.assertIn("이벤트 <- 1건", out)
        self.assertEqual(self.row("SELECT count(*) FROM events")[0], 1)
        self.assertIsNotNone(self.row("SELECT 1 FROM tasks WHERE id=?", "T-900"))
        self.assertEqual(fleet.read_text(encoding="utf-8"), "2026-01-01T00:00:00 old\n")
        self.assertFalse((self.root / ".aimem" / "archive").exists())

    def _graph(self, gid, nodes, round_=None, updated=None):
        updated = updated or self.OLD
        d = self.root / ".aimem" / "graph"
        d.mkdir(parents=True, exist_ok=True)
        rec = {"id": gid, "updated": updated, "nodes": nodes}
        if round_ is not None:
            rec["round"] = round_
        (d / f"{gid}.json").write_text(json.dumps(rec), encoding="utf-8")

    def _queue(self, task):
        with aimem_db.connect() as con:
            con.execute("INSERT INTO queue(pos,task) VALUES(1,?)", (task,))
            con.commit()

    def _handoff_entry(self, rev, body, at=None, actor="관리자"):
        with aimem_db.connect() as con:
            cur = con.execute("INSERT INTO events(at,actor,rev,kind,body) VALUES(?,?,?,?,?)",
                              (at or self.OLD, actor, rev, "handoff", body))
            con.commit()
            return cur.lastrowid

    def test_running_graph_protects_finished_node_task_row(self):
        self._task("T-1", "DONE")
        self._graph("G-1", [
            {"id": "T-1", "task": "T-1", "status": "done", "attempts": []},
            {"id": "T-2", "task": "T-2", "status": "running", "attempts": []},
        ])
        plan = aimem_db.archive_plan(0)
        self.assertEqual([t["id"] for t in plan["tasks"]], [])
        aimem_db.archive_apply(plan, actor="t")
        self.assertIsNotNone(self.row("SELECT 1 FROM tasks WHERE id=?", "T-1"))

    def test_queue_referenced_event_stays(self):
        self._queue("T-300 다음 할 일")
        seq = self._event("T-300 queue +1 다음 할 일")
        plan = aimem_db.archive_plan(0)
        self.assertNotIn(seq, [e["seq"] for e in plan["events"]])
        aimem_db.archive_apply(plan, actor="t")
        self.assertIsNotNone(self.row("SELECT 1 FROM events WHERE seq=?", seq))

    def test_db_only_open_request_event_stays(self):
        self._task("T-1", "DONE")
        with aimem_db.connect() as con:
            con.execute("INSERT INTO requests(id,title,status) VALUES(?,?,?)",
                        ("Q-OPEN", "열린 요청", "IN-PROGRESS"))
            con.commit()
        seq = self._event("T-1 끝남 그리고 Q-OPEN 진행 중")
        plan = aimem_db.archive_plan(0)
        self.assertEqual([t["id"] for t in plan["tasks"]], ["T-1"])
        self.assertNotIn(seq, [e["seq"] for e in plan["events"]])
        aimem_db.archive_apply(plan, actor="t")
        self.assertIsNotNone(self.row("SELECT 1 FROM events WHERE seq=?", seq))

    def test_open_round_and_graphless_relay_stay(self):
        relay = self.root / ".aimem" / "relay"
        relay.mkdir(parents=True)
        for n in (20, 21, 22):
            (relay / f"r{n}.json").write_text(json.dumps({"at": self.OLD}), encoding="utf-8")
        (relay / "r21.plan.md").write_text("x", encoding="utf-8")
        self._graph("G-9", [{"id": "T-9", "task": "T-9", "status": "running", "attempts": []}],
                    round_="21")
        plan = aimem_db.archive_plan(0)
        self.assertEqual(plan["relay"], [])
        aimem_db.archive_apply(plan, actor="t")
        for name in ("r20.json", "r21.json", "r21.plan.md", "r22.json"):
            self.assertTrue((relay / name).exists(), name)

    def test_apply_is_idempotent(self):
        self._task("T-900", "DONE")
        seq = self._event("T-900 끝남")
        for i in range(1, 14):
            self._handoff(i, f"2026-01-{i:02d} 00:00", rev=i)
        plan = aimem_db.archive_plan(0)
        aimem_db.archive_apply(plan, actor="t")
        aimem_db.archive_apply(plan, actor="t")
        board = (self.root / ".aimem" / "archive" / "board-2026-01.md").read_text(encoding="utf-8")
        self.assertEqual(board.count("| T-900 |"), 1)
        ev = (self.root / ".aimem" / "archive" / "events-2026-01.jsonl").read_text(encoding="utf-8")
        recs = [json.loads(ln) for ln in ev.splitlines() if ln.strip()]
        self.assertEqual(sum(1 for r in recs if r["seq"] == seq), 1)
        moved_line = plan["handoff"][0]["line"]
        arch = (self.root / ".aimem" / "archive" / "handoff-2026-01.md").read_text(encoding="utf-8")
        self.assertEqual(arch.splitlines().count(moved_line), 1)

    def test_handoff_archive_line_exact_match(self):
        self._handoff_entry(1, "… 작업 1")
        for rev in range(2, 14):
            self._handoff_entry(rev, f"… 작업 {rev}")
        archdir = self.root / ".aimem" / "archive"
        archdir.mkdir(parents=True)
        existing = "- `2026-01-01 00:00` 관리자: … 작업 12"
        (archdir / "handoff-2026-01.md").write_text(
            "# Handoff log archive - 2026-01\n\n" + existing + "\n", encoding="utf-8")
        plan = aimem_db.archive_plan(0)
        moved = [h for h in plan["handoff"] if h["seq"] == 1]
        self.assertEqual(len(moved), 1)
        line = moved[0]["line"]
        self.assertEqual(line, "- `2026-01-01 00:00` 관리자: … 작업 1")
        self.assertTrue(existing.startswith(line))   # 부분 문자열 확인이면 '있다' 로 오판한다
        aimem_db.archive_apply(plan, actor="t")
        text = (archdir / "handoff-2026-01.md").read_text(encoding="utf-8")
        self.assertIn(line, text.splitlines())
        self.assertIsNone(self.row("SELECT 1 FROM events WHERE seq=?", 1))

    def test_log_cut_keeps_same_inode_and_held_handle_writes(self):
        """정리 뒤에도 열어 둔 핸들의 새 줄이 파일에 남고 inode 가 같다."""
        fleet = self.root / ".aimem" / "fleet-mode.log"
        fleet.write_text("2026-01-01T00:00:00 old\n", encoding="utf-8")
        before = fleet.stat().st_ino
        with fleet.open("a", encoding="utf-8") as fh:
            plan = aimem_db.archive_plan(0)
            self.assertEqual([x["lines"] for x in plan["logs"] if x["file"] == "fleet-mode.log"], [1])
            aimem_db.archive_apply(plan, actor="t")
            fh.write("2999-01-01T00:00:00 after\n")
            fh.flush()
        self.assertEqual(fleet.stat().st_ino, before)   # os.replace 로 되돌리면 빨개진다
        self.assertEqual(fleet.read_text(encoding="utf-8"), "2999-01-01T00:00:00 after\n")
        arch = self.root / ".aimem" / "archive" / "logs-2026-01" / "fleet-mode.log"
        self.assertIn("old", arch.read_text(encoding="utf-8"))

    def test_monitor_log_held_is_left_alone(self):
        """모니터 서버가 monitor.log 를 쥐고 있으면 apply 도 손대지 않는다."""
        aimem = self.root / ".aimem"
        log = aimem / "monitor.log"
        log.write_text("2026-01-01T00:00:00 old\n", encoding="utf-8")
        (aimem / "monitor.pid").write_text(str(os.getpid()), encoding="utf-8")
        plan = aimem_db.archive_plan(0)
        entry = [x for x in plan["logs"] if x["file"] == "monitor.log"][0]
        self.assertEqual(entry["lines"], 0)
        aimem_db.archive_apply(plan, actor="t")
        self.assertEqual(log.read_text(encoding="utf-8"), "2026-01-01T00:00:00 old\n")

    def test_log_lines_appended_between_read_and_cut_survive(self):
        """로그를 읽은 뒤 자르기 전에 다른 프로세스가 `O_APPEND` 로 덧붙인 줄은 원본에 남는다."""
        fleet = self.root / ".aimem" / "fleet-mode.log"
        fleet.write_text("2026-01-01T00:00:00 old1\n2026-01-02T00:00:00 old2\n", encoding="utf-8")
        appended = "2999-01-01T00:00:00 끼어든 줄\n"
        real_iso = aimem_db._iso
        inserted = []

        def appending_iso(value):
            if not inserted:
                inserted.append(value)
                fd = os.open(fleet, os.O_WRONLY | os.O_APPEND)
                try:
                    os.write(fd, appended.encode("utf-8"))
                    os.fsync(fd)
                finally:
                    os.close(fd)
            return real_iso(value)

        plan = aimem_db.archive_plan(0)
        self.assertEqual([x["lines"] for x in plan["logs"] if x["file"] == "fleet-mode.log"], [2])
        with mock.patch.object(aimem_db, "_iso", appending_iso):
            aimem_db.archive_apply(plan, actor="t")
        self.assertEqual(fleet.read_text(encoding="utf-8"), appended)
        arch = self.root / ".aimem" / "archive" / "logs-2026-01" / "fleet-mode.log"
        text = arch.read_text(encoding="utf-8")
        self.assertIn("old1", text)
        self.assertIn("old2", text)
        self.assertNotIn("끼어든 줄", text)

    def test_task_reopened_after_plan_is_not_deleted(self):
        """계획 뒤 다시 열린 태스크 행은 apply 가 내리지 않는다."""
        self._task("T-900", "DONE")
        plan = aimem_db.archive_plan(0)
        self.assertEqual([t["id"] for t in plan["tasks"]], ["T-900"])
        with aimem_db.connect() as con:
            con.execute("UPDATE tasks SET status='ASSIGNED' WHERE id='T-900'")
            con.commit()
        out = aimem_db.archive_apply(plan, actor="t")
        self.assertIsNotNone(self.row("SELECT 1 FROM tasks WHERE id=?", "T-900"))
        self.assertNotIn("T-900", out["tasks"])

    def test_apply_rerenders_state_without_changing_aimem(self):
        """정리 뒤 AIMEM-state.md 는 다시 쓰이고 AIMEM.md 는 그대로다."""
        aimem = self.root / "AIMEM.md"
        aimem.write_text("# AIMEM.md\n\n- **REV: 1**\n", encoding="utf-8")
        self._task("T-900", "DONE")
        with aimem_db.connect() as con:
            con.execute("INSERT INTO meta(key,value) VALUES('rev','42') ON CONFLICT(key) DO UPDATE SET value=excluded.value")
            con.commit()
        plan = aimem_db.archive_plan(0)
        aimem_db.archive_apply(plan, actor="t")
        state = (self.root / "AIMEM-state.md").read_text(encoding="utf-8")
        self.assertIn("# AIMEM-state.md", state)
        self.assertNotIn("| T-900 |", state)
        self.assertEqual(aimem.read_text(encoding="utf-8"), "# AIMEM.md\n\n- **REV: 1**\n")

    def test_event_archive_keeps_rev_and_newlines(self):
        seq = self._event("첫줄\n둘째 줄", rev=150)
        plan = aimem_db.archive_plan(0)
        aimem_db.archive_apply(plan, actor="t")
        f = self.root / ".aimem" / "archive" / "events-2026-01.jsonl"
        recs = [json.loads(ln) for ln in f.read_text(encoding="utf-8").splitlines() if ln.strip()]
        row = [r for r in recs if r["seq"] == seq]
        self.assertEqual(len(row), 1)
        self.assertEqual(row[0]["rev"], 150)
        self.assertEqual(row[0]["body"], "첫줄\n둘째 줄")

    def test_long_node_task_is_not_taken_as_an_identifier(self):
        long_task = "# T-900 어떤 지시\n" + "가" * 3000
        self._graph("G-900", [
            {"id": "T-900", "task": long_task, "status": "running", "attempts": []},
        ])
        self._event("어떤 이벤트 본문")
        lengths = []
        real_mentions = aimem_db._mentions

        def spy(body, ident):
            lengths.append(len(ident))
            return real_mentions(body, ident)

        with mock.patch.object(aimem_db, "_mentions", spy):
            aimem_db.archive_plan(0)
        self.assertTrue(lengths)
        self.assertFalse([n for n in lengths if n > 80])

    def test_open_graph_node_id_is_still_protected(self):
        self._graph("G-900", [
            {"id": "T-900", "task": "T-900", "status": "running", "attempts": []},
        ])
        seq = self._event("T-900 열린 노드", kind="note")
        plan = aimem_db.archive_plan(0)
        self.assertNotIn(seq, [e["seq"] for e in plan["events"]])

    def test_archive_plan_scales_with_many_events_and_ids(self):
        """이벤트 300건 × 식별자 400개 - 본문마다 낱말을 한 번만 뽑으므로 몇 초 안에 끝난다 (예전엔 정규식 재컴파일로 30초+)."""
        with aimem_db.connect() as con:
            con.executemany("INSERT INTO tasks(id,title,status,created,updated) VALUES(?,?,?,?,?)",
                            [(f"T-{i}", "t", "DONE" if i % 2 else "TODO", self.OLD, self.OLD) for i in range(400)])
            con.executemany("INSERT INTO events(at,actor,rev,kind,body) VALUES(?,?,?,?,?)",
                            [(self.OLD, "t", 1, "task", f"T-{i % 400} T-{(i * 7) % 400} " + "본문 " * 200) for i in range(300)])
        start = time.monotonic()
        plan = aimem_db.archive_plan(0)
        self.assertLess(time.monotonic() - start, 5.0)
        self.assertEqual(len(plan["tasks"]), 200)


class QueueFindingIdsTest(DbFixture, unittest.TestCase):
    """큐의 검수 발견 번호에는 라운드를 붙인다 (2026-11-12) - 번호가 보고서마다 1부터 다시 세어져 섞였다."""

    def q(self, action, **kw):
        base = {"task": None, "slot_hint": None, "inherited": None, "note": None, "pos": None, "verbose": False}
        base.update(kw)
        return self.run_cmd(aimem_db.cmd_queue, action=action, **base)

    def tasks(self):
        with aimem_db.connect() as con:
            return [r["task"] for r in con.execute("SELECT task FROM queue ORDER BY pos")]

    def test_bare_ids_are_found_and_qualified_ones_pass(self):
        f = aimem_db.bare_finding_ids
        self.assertEqual(f("검수 N5·N6(낮음)"), ["N5", "N6"])
        self.assertEqual(f("(N7) 상한 ... M13 와 D5"), ["N7", "M13", "D5"])
        # 검수자마다 다른 글자도 쓴다 (R18·R19 실제 사례: A7·S8·G7·C2·B10·P2) - 글자를 가리지 않는다
        self.assertEqual(f("재검수 P2(중간)·A7·G7·C2·B10·SN5"), ["P2", "A7", "G7", "C2", "B10", "SN5"])
        for ok in ("R17-N5", "R17-N5·N6", "R17-N7, N8, N10", "R17-M13/M14", "R19-P2", "R18-A7·R18-S8·R18-B12",
                   "R18-A7·S8", "'생략 N건'", "60→3", "T-224", "G-045", "S2", "S1~S4 는 유료", "R17", "REV 160",
                   "R17 T-224 검수", "Q-261112-c3a1", "UTF-N8X", "UTF8", "N", "E2E"):
            self.assertEqual(f(ok), [], ok)
        self.assertEqual(f("R17-N5·N6 그리고 N9"), ["N9"])
        self.assertEqual(f("R19-P2 와 P3"), ["P3"])

    def test_add_refuses_bare_and_accepts_qualified(self):
        with self.assertRaises(SystemExit) as cm:
            self.q("add", task="검수 N5·N6(낮음): 고칠 것")
        self.assertIn("R17-N5", str(cm.exception))
        with self.assertRaises(SystemExit):
            self.q("add", task="R17 검수 결과", note="N3 참고")
        self.assertEqual(self.tasks(), [])
        self.q("add", task="R17-N5·N6(낮음): 고칠 것")
        self.assertEqual(self.tasks(), ["R17-N5·N6(낮음): 고칠 것"])

    def test_edit_in_place_keeps_order(self):
        for t in ("하나", "둘", "셋"):
            self.q("add", task=t)
        self.q("edit", pos=2, task="R17-N7: 둘 고침")
        self.assertEqual(self.tasks(), ["하나", "R17-N7: 둘 고침", "셋"])
        with self.assertRaises(SystemExit):
            self.q("edit", pos=1, task="N1 고침")
        self.assertEqual(self.q("edit", pos=9, task="R1-N1"), "큐에 9 번이 없습니다\n")


class SnapshotTest(DbFixture, unittest.TestCase):
    """`AIMEM-state.md` 는 명부·보드·큐·소유권·요청만 - 세션·실행·이벤트가 바뀌어도 그대로다."""

    def body(self):
        return [ln for ln in aimem_db.render_text().splitlines() if not ln.startswith(aimem_db.STAMP_PREFIX)]

    def test_sections(self):
        heads = [ln for ln in aimem_db.render_text().splitlines() if ln.startswith("## ")]
        self.assertEqual(heads, ["## 2. 세션 명부", "## 3. 작업 보드", "## 4.5 대기 큐", "## 6. 파일 소유권", "## 요청"])

    def test_unchanged_by_sessions_runs_and_events(self):
        before = self.body()
        with aimem_db.connect() as con:
            con.execute("INSERT INTO sessions(id,role,harness,state,started) VALUES('M-R1-000000','manager','claude','running',?)", (aimem_db._now(),))
            con.execute("INSERT INTO sessions(id,role,harness,state,started) VALUES('w1','worker','codex','running',?)", (aimem_db._now(),))
            con.execute("INSERT INTO runs(id,task_id,state,started) VALUES('r1','T-1','done',?)", (aimem_db._now(),))
            con.execute("INSERT INTO events(at,actor,rev,kind,body) VALUES(?,?,?,?,?)", (aimem_db._now(), "t", 1, "note", "x"))
        self.assertEqual(self.body(), before)
        self.run_cmd(aimem_db.cmd_task, action="set", id="T-1", title="보드는 싣는다")
        self.assertNotEqual(self.body(), before)

    def test_state_dict_still_gives_runs_and_sessions_including_manager(self):
        with aimem_db.connect() as con:
            con.execute("INSERT INTO sessions(id,role,harness,state,started,write_paths) VALUES('M-R1-000000','manager','claude','running','2026-01-01T00:00:00','[]')")
        st = aimem_db.state_dict()
        self.assertEqual([r["id"] for r in st["runs"]], ["M-R1-000000"])
        self.assertEqual([r["id"] for r in st["sessions"]], ["M-R1-000000"])


class UniqueTmpTest(DbFixture, unittest.TestCase):
    """같은 파일을 동시에 고쳐 써도 임시 파일이 겹치지 않는다 - 고정된 `.tmp` 이름이면 서로의 반쯤 쓴 파일을 바꿔 넣는다."""

    def _race(self, n, work):
        start, errors = threading.Barrier(n), []

        def run(i):
            try:
                start.wait()
                work(i)
            except Exception as e:  # noqa: BLE001
                errors.append(e)
        ts = [threading.Thread(target=run, args=(i,)) for i in range(n)]
        [t.start() for t in ts]; [t.join() for t in ts]
        self.assertEqual(errors, [])

    def test_write_atomic_uses_a_fresh_tmp_per_writer(self):
        f = self.root / "x.json"
        seen = []
        real = aimem_db.tempfile.mkstemp

        def spy(*a, **kw):
            fd, name = real(*a, **kw)
            seen.append(name)
            return fd, name
        with mock.patch.object(aimem_db.tempfile, "mkstemp", spy):
            self._race(16, lambda i: aimem_db._write_atomic(f, json.dumps({"i": i, "pad": "x" * 20000})))
        self.assertEqual(len(set(seen)), 16)
        self.assertEqual(sorted(x.name for x in self.root.iterdir() if x.name.startswith("x.json")), ["x.json"])
        self.assertIn(json.loads(f.read_text(encoding="utf-8"))["i"], range(16))   # 찢긴 내용이 아니다

    def test_concurrent_request_file_syncs_leave_valid_json(self):
        f = self.root / ".aimem" / "requests" / "Q-1.json"
        f.write_text(json.dumps({"id": "Q-1", "status": "NEW"}), encoding="utf-8")
        self._race(12, lambda i: aimem_db._sync_request_file("Q-1", detail=f"d{i}" * 500))
        self.assertTrue(json.loads(f.read_text(encoding="utf-8"))["detail"].startswith("d"))
        self.assertEqual([x.name for x in f.parent.iterdir()], ["Q-1.json"])

    def test_round_record_keeps_both_writers(self):
        """`note_round_request` 는 엔진과 같은 잠금(`fleet_rt.roundrec`)으로 쓴다 - 둘의 고침이 모두 남는다."""
        from fleet_rt import roundrec
        rd = self.root / "rounds" / "R3"
        rd.mkdir(parents=True)
        (rd / "round.json").write_text(json.dumps({"round": 3, "requests": [], "projects": []}), encoding="utf-8")

        def work(i):
            if i % 2:
                self.assertTrue(aimem_db.note_round_request(f"Q-{i}", n=3))
            else:
                roundrec.update(rd, lambda rec: {**rec, f"engine{i}": True})
        self._race(10, work)
        rec = json.loads((rd / "round.json").read_text(encoding="utf-8"))
        self.assertEqual(sorted(rec["requests"]), sorted(f"Q-{i}" for i in range(1, 10, 2)))
        self.assertEqual(sorted(k for k in rec if k.startswith("engine")), sorted(f"engine{i}" for i in range(0, 10, 2)))


if __name__ == "__main__":
    unittest.main()
