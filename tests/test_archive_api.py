"""`/api/archive` 계약 (2026-11-11, G-032): 미리보기·실행이 종류별 **건수**를 돌려준다."""
import contextlib
import io
import json
import pathlib
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import aimem_db  # noqa: E402
from aimem_monitor import server  # noqa: E402

WHEN = "2026-01-01T00:00:00"


class ArchiveApiTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name).resolve()
        (self.root / ".aimem" / "requests").mkdir(parents=True)
        (self.root / ".aimem" / "runs").mkdir(parents=True)
        for target, attr, value in (
            (aimem_db, "ROOT", self.root),
            (aimem_db, "DB", self.root / ".aimem" / "aimem.db"),
            (aimem_db, "AIMEM", self.root / "AIMEM.md"),
            (aimem_db, "HANDOFF", self.root / ".aimem" / "handoff.md"),
            (server, "ROOT", self.root),
        ):
            p = mock.patch.object(target, attr, value)
            p.start()
            self.addCleanup(p.stop)
        with contextlib.redirect_stdout(io.StringIO()):
            aimem_db.cmd_init()
        self.db = self.root / ".aimem" / "aimem.db"
        self.run_dir = self.root / ".aimem" / "runs"
        self.req_dir = self.root / ".aimem" / "requests"

    def _seed(self):
        con = sqlite3.connect(self.db)
        con.execute(
            "INSERT INTO tasks(id,request_id,title,slot,status,inherited,artifacts,created,updated) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            ("T-1", "Q-1", "t", "S1", "DONE", "", "[]", WHEN, WHEN),
        )
        con.execute(
            "INSERT INTO events(seq,at,actor,rev,kind,body) VALUES(?,?,?,?,?,?)",
            (1, WHEN, "웹", 157, "task", json.dumps({"task": "T-1"})),
        )
        con.commit()
        con.close()
        (self.req_dir / "Q-9.json").write_text(
            json.dumps({"id": "Q-9", "status": "DONE", "title": "t", "created": WHEN, "updated": WHEN}),
            encoding="utf-8",
        )
        rid = "T-1-S1-a1"
        (self.run_dir / f"{rid}.json").write_text(
            json.dumps({"id": rid, "slot": "S1", "harness": "opencode", "task": "T-1",
                        "attempt": 1, "date": "2026-01-01", "label": "a1", "rev": 157,
                        "started": WHEN}),
            encoding="utf-8",
        )
        (self.run_dir / f"{rid}.rc").write_text("0\n", encoding="utf-8")
        return rid

    def _preview(self):
        code, body = server.archive_action({"days": 0, "dry_run": True}, "웹", self.root)
        self.assertEqual(code, 200)
        return body["plan"]

    def test_records_shape(self):
        self._seed()
        plan = self._preview()
        records = plan["records"]
        self.assertEqual(set(records), {"runs", "events", "handoff", "relay", "log_lines"})
        for v in records.values():
            self.assertIs(type(v), int)
        self.assertIs(type(plan["total_records"]), int)

    def test_dry_run_counts_attached_runs_and_events(self):
        self._seed()
        records = self._preview()["records"]
        self.assertGreaterEqual(records["runs"], 1)
        self.assertGreaterEqual(records["events"], 1)

    def test_dry_run_moves_nothing(self):
        rid = self._seed()
        self._preview()
        self.assertTrue((self.run_dir / f"{rid}.json").exists())
        self.assertTrue((self.run_dir / f"{rid}.rc").exists())
        self.assertTrue((self.req_dir / "Q-9.json").exists())
        con = sqlite3.connect(self.db)
        self.assertEqual(con.execute("SELECT COUNT(*) FROM tasks").fetchone()[0], 1)
        self.assertEqual(con.execute("SELECT COUNT(*) FROM events").fetchone()[0], 1)
        con.close()

    def test_apply_returns_counts(self):
        self._seed()
        code, body = server.archive_action({"days": 0}, "웹", self.root)
        self.assertEqual(code, 200)
        self.assertIn("moved_counts", body)
        counts = body["moved_counts"]
        self.assertTrue(counts)
        for v in counts.values():
            self.assertIs(type(v), int)
        self.assertGreaterEqual(counts["runs"], 1)

    def test_invalid_days(self):
        self._seed()
        for days in ("x", True, -1, 4000):
            self.assertEqual(server.archive_action({"days": days}, "웹", self.root)[0], 400, days)

    def test_non_production_root(self):
        rid = self._seed()
        code, body = server.archive_action({"days": 0}, "웹", self.root / "other")
        self.assertEqual(code, 403)
        self.assertTrue((self.run_dir / f"{rid}.json").exists())
        self.assertTrue((self.run_dir / f"{rid}.rc").exists())
        self.assertTrue((self.req_dir / "Q-9.json").exists())
        con = sqlite3.connect(self.db)
        self.assertEqual(con.execute("SELECT COUNT(*) FROM tasks").fetchone()[0], 1)
        con.close()


if __name__ == "__main__":
    unittest.main()
