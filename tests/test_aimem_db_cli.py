"""`aimem_db.py` 의 task/request set 과 archive 회귀 테스트 (2026-11-10, 클로드 코드).

- `request set` 이 `--status` 없이 기존 요청을 고치면 NOT NULL 로 실패하던 것
- `task set` 이 `--status` 없이 고치면 기존 상태를 TODO 로 덮던 것
- `archive`: DONE 이 된 지 N일 지난 태스크를 아카이브 파일에 먼저 쓰고 DB 에서 내린다
- `request set` 이 `.aimem/requests/*.json` 도 맞춘다 (`migrate` 가 되돌리지 않게)
"""
import argparse
import contextlib
import io
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import aimem_db  # noqa: E402


def ns(**kw):
    base = {"actor": "test", "id": None, "request": None, "title": None, "slot": None, "status": None,
            "artifacts": None, "detail": None, "requester": None, "days": 14, "dry_run": False}
    base.update(kw)
    return argparse.Namespace(**base)


class AimemDbCliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        (self.root / ".aimem" / "requests").mkdir(parents=True)
        patches = [mock.patch.object(aimem_db, "ROOT", self.root),
                   mock.patch.object(aimem_db, "DB", self.root / ".aimem" / "aimem.db")]
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


if __name__ == "__main__":
    unittest.main()


class SlotCommandTest(AimemDbCliTest):
    """`aimem_db.py slot add|set|remove|list` (2026-11-10, 태석님 지시) - DB 정본 + fleet_slots.json 거울."""

    def _json(self):
        return json.loads((self.root / "tools" / "fleet_slots.json").read_text(encoding="utf-8"))

    def test_add_set_remove_roundtrip_and_mirror(self):
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
