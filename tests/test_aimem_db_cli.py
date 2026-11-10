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


class ArchiveRequestsGraphsTest(AimemDbCliTest):
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
